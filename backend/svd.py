"""Stable Video Diffusion (SVD) client for AI Video Maker.

SVD is image-to-video: a still image is animated into a short clip. Three modes
are supported, selected automatically:

1. NVIDIA NIM API (remote)   - requires NVIDIA_API_KEY env var
2. Local Diffusers (self-host) - requires GPU and SVD_LOCAL=1
3. Demo simulation            - no key and no local model -> fake async task

Notes:
- The official Stability AI SVD API was deprecated in July 2025. NVIDIA NIM and
  self-hosting are the practical ways to run SVD in 2026.
- Base SVD does not accept text prompts; the prompt is stored as metadata.
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NIM_GENERATE_URL = os.getenv(
    "NIM_GENERATE_URL", "https://ai.api.nvidia.com/v1/videos/generations"
)
NIM_STATUS_URL = os.getenv(
    "NIM_STATUS_URL", "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status"
)
SVD_LOCAL = os.getenv("SVD_LOCAL", "").strip().lower() in ("1", "true", "yes")
SVD_MODEL_ID = "stabilityai/stable-video-diffusion"


def nvidia_available() -> bool:
    return bool(NVIDIA_API_KEY)


def local_available() -> bool:
    if not SVD_LOCAL:
        return False
    try:
        import torch  # noqa: F401

        return torch.cuda.is_available()
    except Exception:
        return False


def demo_mode() -> bool:
    return not (nvidia_available() or local_available())


def provider_status() -> dict:
    return {
        "nvidia_nim": nvidia_available(),
        "local_diffusers": local_available(),
        "model": SVD_MODEL_ID,
        "demo": demo_mode(),
    }


def _read_image_b64(image_path: str, max_bytes: int = 15 * 1024 * 1024) -> str:
    """Read a local image and return a base64 data URI."""
    data = Path(image_path).read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Image too large: {len(data)} bytes (max {max_bytes}).")
    ext = Path(image_path).suffix.lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif ext == "png":
        mime = "image/png"
    elif ext == "webp":
        mime = "image/webp"
    else:
        raise ValueError(f"Unsupported image type .{ext} (use jpg/png/webp).")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# ------------------------------------------------------------------ NVIDIA NIM
async def _nim_generate(image_path: str, seed: int, cfg_scale: float,
                        motion_bucket_id: int) -> str:
    """Submit an SVD generation job to NVIDIA NIM. Returns request_id."""
    image_uri = _read_image_b64(image_path)
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
    }
    body = {
        "image": image_uri,
        "seed": seed,
        "cfg_scale": cfg_scale,
        "motion_bucket_id": motion_bucket_id,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(NIM_GENERATE_URL, headers=headers, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"NVIDIA NIM error {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    request_id = data.get("request_id")
    if not request_id:
        raise RuntimeError(f"NVIDIA NIM returned no request_id: {resp.text[:400]}")
    return request_id


async def _nim_status(request_id: str) -> dict:
    """Poll NVIDIA NIM task status."""
    url = f"{NIM_STATUS_URL}/{request_id}"
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        return {"status": "failed", "error": {"code": str(resp.status_code),
                                              "message": resp.text[:300]}}
    return resp.json()


def _nim_video_url(status: dict) -> Optional[str]:
    """Extract the video asset URL from a NIM status response (best-effort)."""
    resp = status.get("response")
    if not resp:
        return None
    if isinstance(resp, list):
        for item in resp:
            url = item.get("url") if isinstance(item, dict) else None
            if url:
                return url
    elif isinstance(resp, dict):
        for key in ("assets", "artifacts", "files"):
            items = resp.get(key) or []
            for item in items:
                url = item.get("url") if isinstance(item, dict) else None
                if url:
                    return url
        url = resp.get("url")
        if url:
            return url
    return None


# ------------------------------------------------------------------ local
def _local_generate(image_path: str, seed: int, motion_bucket_id: int,
                    frames: int) -> Path:
    """Run SVD locally via diffusers (requires CUDA). Returns output mp4 path."""
    import torch
    from diffusers import StableVideoDiffusionPipeline
    from diffusers.utils import export_to_video

    pipe = StableVideoDiffusionPipeline.from_pretrained(
        SVD_MODEL_ID, torch_dtype=torch.float16, variant="fp16"
    )
    pipe.enable_model_cpu_offload()

    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    generator = torch.Generator(device="cpu").manual_seed(seed)
    result = pipe(
        image,
        decode_chunk_size=8,
        generator=generator,
        motion_bucket_id=motion_bucket_id,
        num_frames=frames,
    )
    out_dir = Path("data") / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"svd-{uuid.uuid4().hex[:8]}.mp4"
    export_to_video(result.frames[0], str(out_path), fps=7)
    return out_path


# ---------------------------------------------------------------- public API
def create_task(payload: dict) -> tuple[str, dict]:
    """Create an SVD task. Returns (task_id, stored_entry).

    payload keys: image_path, seed, cfg_scale, motion_bucket_id, frames, prompt.
    """
    task_id = f"svd-{uuid.uuid4().hex[:16]}"
    entry = {
        "id": task_id,
        "provider": "svd",
        "status": "queued",
        "prompt": payload.get("prompt", "")[:300],
        "image_path": payload.get("image_path"),
        "seed": payload.get("seed", 0),
        "cfg_scale": payload.get("cfg_scale", 2.5),
        "motion_bucket_id": payload.get("motion_bucket_id", 127),
        "frames": payload.get("frames", 25),
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "demo": demo_mode(),
        "progress": 5,
    }
    return task_id, entry


async def submit_task(entry: dict) -> str:
    """Actually submit a queued SVD task to the live backend.

    Returns the remote request id (task_id). For local mode returns the local
    uuid and the result is written synchronously (status handled by poll).
    """
    if local_available():
        out = _local_generate(
            entry["image_path"],
            seed=entry["seed"],
            motion_bucket_id=entry["motion_bucket_id"],
            frames=entry["frames"],
        )
        entry["video_path"] = str(out)
        entry["status"] = "succeeded"
        entry["progress"] = 100
        return entry["id"]
    if nvidia_available():
        request_id = await _nim_generate(
            entry["image_path"],
            seed=entry["seed"],
            cfg_scale=entry["cfg_scale"],
            motion_bucket_id=entry["motion_bucket_id"],
        )
        entry["remote_id"] = request_id
        return request_id
    raise RuntimeError("SVD demo mode cannot submit a live task.")


async def poll_task(entry: dict) -> dict:
    """Poll an SVD task and return the normalized status dict."""
    if entry.get("local") or entry.get("video_path"):
        return {
            "status": "succeeded",
            "video_url": entry.get("video_url"),
            "demo": entry.get("demo", False),
            "progress": 100,
        }
    if entry.get("demo"):
        return _demo_poll(entry)
    if nvidia_available() and entry.get("remote_id"):
        status = await _nim_status(entry["remote_id"])
        st = status.get("status", "running")
        if st == "succeeded":
            url = _nim_video_url(status)
            return {
                "status": "succeeded",
                "video_url": url,
                "demo": False,
                "progress": 100,
            }
        if st in ("failed", "cancelled", "error"):
            return {
                "status": "failed",
                "error": {"code": "SVD_FAILED", "message": status.get("detail", str(status)[:300])},
                "demo": False,
                "progress": 0,
            }
        progress = 90 if st == "running" else 45
        return {"status": st, "demo": False, "progress": progress}
    return {"status": "failed", "error": {"code": "NO_BACKEND", "message": "No SVD backend available."}}


def _demo_poll(entry: dict) -> dict:
    """Advance a demo SVD task over time (mirrors the Seedance demo)."""
    elapsed = time.time() - entry.get("created_at", time.time())
    if elapsed >= 12:
        return {
            "status": "succeeded",
            "demo": True,
            "progress": 100,
            "video_url": None,
        }
    if elapsed >= 6:
        return {"status": "running", "demo": True, "progress": 70}
    return {"status": "queued", "demo": True, "progress": 5}
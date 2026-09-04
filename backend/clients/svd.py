"""Client Stable Video Diffusion (SVD) — pola chat2cartoon/clients.

SVD adalah image-to-video. Mendukung tiga backend:
1. NVIDIA NIM API (remote)     -> butuh NVIDIA_API_KEY
2. Local Diffusers (GPU)       -> butuh SVD_LOCAL=1 + torch/diffusers
3. Demo simulation             -> tanpa keduanya
"""
from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from .. import constants as config


def nvidia_available() -> bool:
    return bool(config.NVIDIA_API_KEY)


def local_available() -> bool:
    if not config.SVD_LOCAL:
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
        "model": config.SVD_MODEL_ID,
        "demo": demo_mode(),
    }


class SVDPipelineError(Exception):
    pass


def _read_image_b64(image_path: str, max_bytes: int = 15 * 1024 * 1024) -> str:
    """Baca gambar lokal menjadi base64 data URI."""
    data = Path(image_path).read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Gambar terlalu besar: {len(data)} bytes (maks {max_bytes}).")
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext)
    if not mime:
        raise ValueError(f"Format gambar .{ext} tidak didukung (pakai jpg/png/webp).")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# ------------------------------------------------------------------ NVIDIA NIM
async def _nim_generate(image_path: str, seed: int, cfg_scale: float,
                        motion_bucket_id: int) -> str:
    image_uri = _read_image_b64(image_path)
    headers = {
        "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
        "Accept": "application/json",
    }
    body = {
        "image": image_uri,
        "seed": seed,
        "cfg_scale": cfg_scale,
        "motion_bucket_id": motion_bucket_id,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(config.NIM_GENERATE_URL, headers=headers, json=body)
    if resp.status_code >= 400:
        raise SVDPipelineError(f"NVIDIA NIM error {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    request_id = data.get("request_id")
    if not request_id:
        raise SVDPipelineError(f"NVIDIA NIM tidak mengembalikan request_id: {resp.text[:400]}")
    return request_id


async def _nim_status(request_id: str) -> dict:
    url = f"{config.NIM_STATUS_URL}/{request_id}"
    headers = {"Authorization": f"Bearer {config.NVIDIA_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        return {"status": "failed", "error": {"code": str(resp.status_code), "message": resp.text[:300]}}
    return resp.json()


def _nim_video_url(status: dict) -> Optional[str]:
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
            for item in resp.get(key) or []:
                url = item.get("url") if isinstance(item, dict) else None
                if url:
                    return url
        if resp.get("url"):
            return resp.get("url")
    return None


# ------------------------------------------------------------------ local
def _local_generate(image_path: str, seed: int, motion_bucket_id: int, frames: int) -> Path:
    import torch
    from diffusers import StableVideoDiffusionPipeline
    from diffusers.utils import export_to_video

    pipe = StableVideoDiffusionPipeline.from_pretrained(
        config.SVD_MODEL_ID, torch_dtype=torch.float16, variant="fp16"
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
    raise SVDPipelineError("SVD demo mode tidak bisa submit task live.")


async def poll_task(entry: dict) -> dict:
    if entry.get("video_path") or entry.get("local"):
        return {"status": "succeeded", "demo": entry.get("demo", False), "progress": 100}
    if entry.get("demo"):
        return _demo_poll(entry)
    if nvidia_available() and entry.get("remote_id"):
        status = await _nim_status(entry["remote_id"])
        st = status.get("status", "running")
        if st == "succeeded":
            return {"status": "succeeded", "video_url": _nim_video_url(status), "demo": False, "progress": 100}
        if st in ("failed", "cancelled", "error"):
            return {"status": "failed",
                    "error": {"code": "SVD_FAILED", "message": status.get("detail", str(status)[:300])},
                    "demo": False, "progress": 0}
        return {"status": st, "demo": False, "progress": 90 if st == "running" else 45}
    return {"status": "failed", "error": {"code": "NO_BACKEND", "message": "Tidak ada backend SVD."}}


def _demo_poll(entry: dict) -> dict:
    elapsed = time.time() - entry.get("created_at", time.time())
    if elapsed >= 12:
        return {"status": "succeeded", "demo": True, "progress": 100, "video_url": None}
    if elapsed >= 6:
        return {"status": "running", "demo": True, "progress": 70}
    return {"status": "queued", "demo": True, "progress": 5}
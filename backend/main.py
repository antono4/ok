"""
AI Video Maker - Seedance 2.5 backend.

Integrates with BytePlus ModelArk video generation API:
POST  /api/generate        -> create a video generation task
GET   /api/status/{task_id}  -> poll task status
GET   /api/history           -> list previous generations
GET   /api/config             -> frontend configuration (model name, demo mode flag)
GET   /api/health            -> health check

When ARK_API_KEY is not set, the backend runs in demo mode and simulates the generation pipeline so the UI stays fully usable.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
HISTORY_FILE = DATA_DIR / "history.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

ARK_API_KEY = os.getenv("ARK_API_KEY", "").strip()
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3").rstrip("/")
# Model ID for Dreamina Seedance 2.5 (check the Model list page in BytePlus console)
SEEDANCE_2_5_MODEL = os.getenv("SEEDANCE_MODEL", "dreamina-seedance-2-5-260628")
DEMO_MODE = not ARK_API_KEY

app = FastAPI(title="AI Video Maker - Seedance 2.5", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- persistence --
def _load_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(items: list[dict[str, Any]]) -> None:
    HISTORY_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), "utf-8")


def _append_history(entry: dict[str, Any]) -> None:
    items = _load_history()
    items.insert(0, entry)
    _save_history(items[:100])  # keep the latest 100


def _update_history(task_id: str, **fields: Any) -> None:
    items = _load_history()
    for item in items:
        if item.get("id") == task_id:
            item.update(fields)
            _save_history(items)
            return
    entry = {"id": task_id, **fields}
    _append_history(entry)


# ------------------------------------------------------------------- api model --
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    duration: int = Field(5, ge=4, le=30)
    resolution: str = Field("720p", pattern="^(480p|720p|1080p)$")
    ratio: str = Field("16:9", pattern="^(16:9|4:3|1:1|3:4|9:16|21:9|adaptive)$")
    generate_audio: bool = True
    watermark: bool = False
    first_frame_url: Optional[str] = Field(None, description="Public image URL used as the first frame (image-to-video)")
    api_key: Optional[str] = Field(None, description="Optional per-request ARK API key")
    demo: Optional[bool] = Field(None, description="Force demo mode for testing")


class StatusResponse(BaseModel):
    id: str
    status: str
    video_url: Optional[str] = None
    error: Optional[dict[str, str]] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None
    ratio: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    usage: Optional[dict[str, Any]] = None
    demo: bool = False
    progress: Optional[int] = None


# ----------------------------------------------------------------- tools ----
def _effective_key(request_key: Optional[str]) -> str:
    key = (request_key or ARK_API_KEY).strip()
    return key


def _validate_remote_inputs(payload: dict, demo: bool = False) -> None:
    """Mirror the most important ModelArk constraints before hitting the API."""
    dur = payload.get('duration')
    if dur is not None:
        if dur < 4 or dur > 30:
            raise HTTPException(status_code=422, detail='Duration must be between 4 and 30 seconds.')
    first_frame = payload.get('first_frame_url')
    if first_frame and not demo:
        is_http = first_frame.startswith("http://")
        if not is_http:
            is_http = first_frame.startswith("https://")
        if not is_http:
            raise HTTPException(status_code=422, detail='First frame image must be a public http(s) URL.')
def _build_contents(prompt: str, first_frame_url: Optional[str]) -> list[dict]:
    contents: list[dict] = [{"type": "text", "text": prompt}]
    if first_frame_url:
        contents.append(
            {
                "type": "image_url",
                "image_url": {"url": first_frame_url},
                "role": "first_frame",
            }
        )
    return contents


async def _create_remote_task(payload: dict, api_key: str) -> str:
    url = f"{ARK_BASE_URL}/contents/generations/tasks"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": payload["model"],
        "content": _build_contents(payload["prompt"], payload.get("first_frame_url")),
        "duration": payload["duration"],
        "resolution": payload["resolution"],
        "ratio": payload["ratio"],
        "generate_audio": payload["generate_audio"],
        "watermark": payload["watermark"],
        "output_format": "mp4",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        detail = resp.text[:1200]
        try:
            parsed = resp.json()
            detail = parsed.get("error", {}).get("message", resp.text[:1200])
        except Exception:
            pass
        raise HTTPException(status_code=resp.status_code, detail=f"ModelArk error: {detail}")
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        raise HTTPException(status_code=502, detail="ModelArk returned no task id.")
    return task_id


async def _fetch_remote_status(task_id: str, api_key: str) -> dict:
    url = f"{ARK_BASE_URL}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code == 404:
        return {"status": "expired", "error": {"code": "NOT_FOUND", "message": "Task not found or expired."}}
    if resp.status_code >= 400:
        return {
            "status": "failed",
            "error": {"code": str(resp.status_code), "message": resp.text[:500]},
        }
    return resp.json()


def _status_progress(status: str) -> Optional[int]:
    return {"queued": 5, "running": 45}.get(status)


def _demo_create_task(payload: dict) -> tuple[str, dict]:
    """Demo-mode helper: store the exact payload and simulate async generation."""
    task_id = f"demo-{uuid.uuid4().hex[:16]}"
    entry = {
        "id": task_id,
        "status": "queued",
        "prompt": payload["prompt"][:300],
        "duration": payload["duration"],
        "resolution": payload["resolution"],
        "ratio": payload["ratio"],
        "generate_audio": payload["generate_audio"],
        "watermark": payload["watermark"],
        "first_frame_url": payload.get("first_frame_url"),
        "model": payload["model"],
        "demo": True,
        "progress": 5,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    _append_history(entry)
    return task_id, entry


def _demo_progress_status(task_id: str) -> dict:
    """Advance a demo task based on elapsed time."""
    items = _load_history()
    for item in items:
        if item.get("id") != task_id:
            continue
        elapsed = time.time() - item.get("created_at", time.time())
        if elapsed >= 14:
            status = "succeeded"
            progress = 100
        elif elapsed >= 8:
            status = "running"
            progress = 72
        elif elapsed >= 3:
            status = "running"
            progress = 45
        else:
            status = "queued"
            progress = 5
        if status == "succeeded" and not item.get("video_url"):
            # deterministic pseudo-mp4 "payload" so the demo stays offline
            fake = f"data:video/mp4;base64,{demo_base64_fragment()}"
            item.update(video_url=fake, status=status, progress=progress, updated_at=int(time.time()))
            _save_history(items)
        else:
            item.update(status=status, progress=progress, updated_at=int(time.time()))
            _save_history(items)
        return {
            "id": task_id,
            "status": status,
            "video_url": item.get("video_url"),
            "demo": True,
            "progress": progress,
            "duration": item.get("duration"),
            "resolution": item.get("resolution"),
            "ratio": item.get("ratio"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
    return {"id": task_id, "status": "expired", "demo": True, "error": {"code": "NOT_FOUND", "message": "Unknown demo task."}}


# deterministic tiny valid mp4 bytes (reused across demos to stay offline)
_DEMO_MP4_CACHE: list[str] = []

def demo_base64_fragment() -> str:
    """Return a cached base64 mp4 payload. The first call builds it once."""
    if _DEMO_MP4_CACHE:
        return _DEMO_MP4_CACHE[0]
    # Minimal valid-ish MP4 wrapper: ftyp + mdat with a few bytes of content.
    # (Notplayable as real video, but enough for the UI to showa video object.)
    ftyp = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    mdat_size = 1024
    mdat = b"\x00\x00\x00\x00mdat" + bytes([0]) * (mdat_size - 8)
    payload = ftyp + mdat  # ~1KB
    b64 = base64.b64encode(payload).decode("ascii")
    _DEMO_MP4_CACHE.append(b64)
    return b64


# ------------------------------------------------------------------ routes --
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "demo": DEMO_MODE, "model": SEEDANCE_2_5_MODEL}


@app.get("/api/config")
async def config() -> dict:
    return {
        "demo_mode": DEMO_MODE,
        "model": SEEDANCE_2_5_MODEL,
        "base_url": ARK_BASE_URL,
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "duration_range": [4, 30],
    }


@app.post("/api/generate", response_model=StatusResponse)
async def generate(req: GenerateRequest) -> StatusResponse:
    key = _effective_key(req.api_key)
    force_demo = req.demo if req.demo is not None else DEMO_MODE
    if not key and not force_demo:
        force_demo = True

    payload = {
        "model": SEEDANCE_2_5_MODEL,
        "prompt": req.prompt.strip(),
        "duration": req.duration,
        "resolution": req.resolution,
        "ratio": req.ratio,
        "generate_audio": req.generate_audio,
        "watermark": req.watermark,
        "first_frame_url": req.first_frame_url,
    }
    _validate_remote_inputs(payload, force_demo)

    if force_demo:
        task_id, _ = _demo_create_task(payload)
        return StatusResponse(id=task_id, status="queued", demo=True, progress=5, created_at=int(time.time()), updated_at=int(time.time()))

    try:
        task_id = await _create_remote_task(payload, key)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Network error contacting ModelArk: {exc}") from exc

    entry = {
        "id": task_id,
        "status": "queued",
        "prompt": payload["prompt"][:300],
        "duration": payload["duration"],
        "resolution": payload["resolution"],
        "ratio": payload["ratio"],
        "generate_audio": payload["generate_audio"],
        "watermark": payload["watermark"],
        "first_frame_url": payload.get("first_frame_url"),
        "model": payload["model"],
        "demo": False,
        "progress": 5,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    _append_history(entry)
    return StatusResponse(id=task_id, status="queued", demo=False, progress=5, created_at=entry["created_at"], updated_at=entry["updated_at"])


@app.get("/api/status/{task_id}", response_model=StatusResponse)
async def status(task_id: str, api_key: Optional[str] = None) -> StatusResponse:
    stored = next((item for item in _load_history() if item.get("id") == task_id), None)
    if stored and stored.get("demo"):
        return StatusResponse(**_demo_progress_status(task_id))

    key = _effective_key(api_key if api_key else (stored or {}).get("api_key"))
    if not key:
        return StatusResponse(
            id=task_id,
            status="failed",
            demo=True,
            error={"code": "NO_API_KEY", "message": "ARK_API_KEY is not configured. Start the server with ARK_API_KEY set."},
        )

    remote = await _fetch_remote_status(task_id, key)
    status_value = remote.get("status", "failed")
    content = remote.get("content") or {}
    updated = {
        "id": task_id,
        "status": status_value,
        "video_url": content.get("video_url"),
        "error": remote.get("error"),
        "duration": remote.get("duration"),
        "resolution": remote.get("resolution"),
        "ratio": remote.get("ratio"),
        "created_at": remote.get("created_at"),
        "updated_at": remote.get("updated_at"),
        "usage": remote.get("usage"),
        "demo": False,
        "progress": _status_progress(status_value) if status_value in ("queued", "running") else (100 if status_value == "succeeded" else (0 if status_value == "failed" else None)),
    }
    if stored:
        _update_history(task_id, status=status_value, video_url=updated["video_url"], progress=updated["progress"], updated_at=updated["updated_at"])

    return StatusResponse(**updated)


@app.get("/api/history")
async def history(limit: int = 50) -> list[dict]:
    items = _load_history()
    return items[: max(1, min(limit, 100))]


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a local image, upload it to an anonymous tmpfiles-style host.

 ...  For simplicity:  we store it under /data/uploads and serve it via the FastAPI static mount, returning a public URL for the first_frame parameter."""
    ext = Path(file.filename or "image.png").suffix.lower() or ".png"
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}
    if ext not in allowed:
        exts = ", ".join(sorted(allowed))
        raise HTTPException(status_code=415, detail=f"Unsupported image type {ext}. Allowed: {exts}")
    data = await file.read()
    max_size = 30 * 1024 * 1024
    if len(data) > max_size:
        raise HTTPException(status_code=413, detail="Image too large. Max size is 30 MB.")
    name = f"{uuid.uuid4().hex}{ext}"
    dest = DATA_DIR / "uploads" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"url": f"/uploads/{name}"}

# mount local demo uploads under /uploads (only needed in demo/local mode)
app.mount("/uploads", StaticFiles(directory=DATA_DIR / "uploads"), name="uploads") if (DATA_DIR / "uploads").exists() else None

# Serve static frontend
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

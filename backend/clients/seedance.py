"""Client Seedance 2.5 (BytePlus ModelArk) — pola chat2cartoon.

Memisahkan logika panggilan API Seedance (create task, poll status,
ekstraksi video_url) dari aplikasi web agar mudah diuji & dipakai ulang.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from .. import constants as config


class SeedanceError(Exception):
    """Error yang berasal dari API Seedance/ModelArk."""


class SeedanceClient:
    """Thin client untuk video generation Seedance 2.5 via BytePlus ModelArk."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.api_key = (api_key or config.ARK_API_KEY).strip()
        self.base_url = (base_url or config.ARK_BASE_URL).rstrip("/")
        self.model = config.SEEDANCE_MODEL

    # ------------------------------------------------------------------ create
    def build_content(self, prompt: str, first_frame_url: Optional[str] = None) -> list[dict]:
        """Susun daftar konten multimodal sesuai skema ModelArk."""
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

    async def create_task(
        self,
        prompt: str,
        duration: int = 5,
        resolution: str = "720p",
        ratio: str = "16:9",
        generate_audio: bool = True,
        watermark: bool = False,
        first_frame_url: Optional[str] = None,
    ) -> str:
        """Submit task video generation. Return task id (asinkron)."""
        if not self.api_key:
            raise SeedanceError("ARK_API_KEY belum dikonfigurasi.")

        url = f"{self.base_url}/contents/generations/tasks"
        body = {
            "model": self.model,
            "content": self.build_content(prompt, first_frame_url),
            "duration": duration,
            "resolution": resolution,
            "ratio": ratio,
            "generate_audio": generate_audio,
            "watermark": watermark,
            "output_format": "mp4",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:1200]
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:1200])
            except Exception:
                pass
            raise SeedanceError(detail)
        task_id = resp.json().get("id")
        if not task_id:
            raise SeedanceError("ModelArk tidak mengembalikan task id.")
        return task_id

    # ------------------------------------------------------------------- poll
    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Ambil status satu task dari API ModelArk."""
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 404:
            return {"status": "expired", "error": {"code": "NOT_FOUND", "message": "Task tidak ditemukan."}}
        if resp.status_code >= 400:
            return {
                "status": "failed",
                "error": {"code": str(resp.status_code), "message": resp.text[:500]},
            }
        return resp.json()

    def extract_video_url(self, task_data: dict[str, Any]) -> Optional[str]:
        """Ambil video_url dari data task yang sudah sukses."""
        content = task_data.get("content") or {}
        return content.get("video_url")

    @staticmethod
    def status_progress(status: str) -> Optional[int]:
        """Perkiraan progres (0-100) untuk UI dari status task."""
        if status == "queued":
            return 5
        if status == "running":
            return 45
        if status == "succeeded":
            return 100
        if status == "failed":
            return 0
        return None


def create_demo_task(prompt: str, first_frame_url: Optional[str] = None, **params: Any) -> str:
    """Buat task simulasi (demo) — format task id sama, tapi tidak dipanggil ke remote."""
    import uuid

    task_id = f"demo-{uuid.uuid4().hex[:16]}"
    return task_id
"""Downloader untuk media dari URL (pola chat2cartoon/downloader.py).

Dipakai untuk mengunduh video hasil generasi ke disk / memory.
"""
from __future__ import annotations

import io
from typing import Tuple

import httpx

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


async def download_to_memory(url: str, max_size: int = MAX_FILE_SIZE) -> Tuple[bytes, str]:
    """Unduh file dari URL ke memory. Return (bytes, extension).

    Menghindari memuat file yang terlalu besar untuk mencegah OOM.
    """
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            ext = _extension_from_mime(content_type)
            buffer = io.BytesIO()
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_size:
                    raise ValueError(f"File terlalu besar: {total} bytes (maks {max_size}).")
                buffer.write(chunk)
    return buffer.getvalue(), ext


async def download_to_file(url: str, dest_path: str, max_size: int = MAX_FILE_SIZE) -> str:
    """Unduh file dari URL ke path lokal. Return path."""
    data, ext = await download_to_memory(url, max_size=max_size)
    from pathlib import Path

    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dest_path).write_bytes(data)
    return dest_path


def _extension_from_mime(content_type: str) -> str:
    mime_map = {
        "video/mp4": "mp4",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
    }
    key = content_type.split(";")[0].strip().lower()
    return mime_map.get(key, "bin")
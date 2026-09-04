"""Backward-compatible re-export dari backend.clients.svd.

Arsitektur baru (pola chat2cartoon) menaruh implementasi di
`backend/clients/svd.py`; modul ini hanya alias agar kode lama
(`from backend import svd`) tetap berfungsi.
"""
from __future__ import annotations

from .clients.svd import (  # noqa: F401
    SVDPipelineError,
    create_task,
    demo_mode,
    local_available,
    nvidia_available,
    poll_task,
    provider_status,
    submit_task,
)

__all__ = [
    "SVDPipelineError",
    "create_task",
    "demo_mode",
    "local_available",
    "nvidia_available",
    "poll_task",
    "provider_status",
    "submit_task",
]
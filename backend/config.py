"""Alias ke constants.py (backward-compat).

Implementasi konfigurasi terpusat ada di `backend/constants.py`
(pola chat2cartoon). Modul ini hanya re-export agar kode lama
yang mengimpor `backend.config` tetap berfungsi.
"""
from __future__ import annotations

from .constants import (  # noqa: F401
    ARK_API_KEY,
    ARK_BASE_URL,
    BASE_DIR,
    DATA_DIR,
    DEMO_MODE,
    HISTORY_FILE,
    NIM_GENERATE_URL,
    NIM_STATUS_URL,
    NVIDIA_API_KEY,
    SEEDANCE_MODEL,
    STATIC_DIR,
    SVD_LOCAL,
    SVD_MODEL_ID,
)
"""Konfigurasi terpusat aplikasi AI Video Maker (pola chat2cartoon/constants.py).

Semua nilai environment dibaca di satu tempat sehingga mudah dilacak.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
HISTORY_FILE = DATA_DIR / "history.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

# ------------------------------------------------------------------ Seedance
# BytePlus ModelArk (Seedance 2.5)
ARK_API_KEY = os.getenv("ARK_API_KEY", "").strip()
ARK_BASE_URL = os.getenv(
    "ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"
).rstrip("/")
SEEDANCE_MODEL = os.getenv("SEEDANCE_MODEL", "dreamina-seedance-2-5-260628")

# ------------------------------------------------------------------- SVD
# NVIDIA NIM (remote Stable Video Diffusion)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NIM_GENERATE_URL = os.getenv(
    "NIM_GENERATE_URL", "https://ai.api.nvidia.com/v1/videos/generations"
)
NIM_STATUS_URL = os.getenv(
    "NIM_STATUS_URL", "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status"
)
SVD_LOCAL = os.getenv("SVD_LOCAL", "").strip().lower() in ("1", "true", "yes")
SVD_MODEL_ID = "stabilityai/stable-video-diffusion"

# ------------------------------------------------------------------- Umum
DEMO_MODE = not ARK_API_KEY
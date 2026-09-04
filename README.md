# 🎬 AI Video Maker — Seedance 2.5 + Stable Video Diffusion (SVD)

Aplikasi web **AI Video Maker** dengan dua provider untuk membuat video dari AI:

1. **Seedance 2.5** — model video generatif ByteDance (via **BytePlus ModelArk**).  
   Text-to-video, image-to-video, audio asli sinkron, durasi hingga 30 detik.
2. **Stable Video Diffusion (SVD)** — model **image-to-video** open-source milik Stability AI.  
   Gambar statis → video pendek (self-hosted via GPU, atau NVIDIA NIM API).

Aplikasi lengkap dengan **web UI** (FastAPI + vanilla JS), **API REST**, dan **CLI**.

![Screenshot UI](screenshots/ui.png)

---

## ✨ Fitur

**Seedance 2.5**
- Text-to-video dengan prompt bahasa natural (dialog dalam kutip ganda → lip-sync)
- Image-to-video (first frame) via upload / URL publik
- Audio asli: suara manusia + efek + musik sinkron
- Durasi 4–30 detik, resolusi 480p/720p/1080p, rasio 16:9 / 9:16 / 1:1 / dst.

**Stable Video Diffusion (SVD)**
- Image-to-video: animasikan gambar statis menjadi klip pendek
- Backend: NVIDIA NIM API (remote) atau local Diffusers (butuh GPU)
- Mode demo tanpa GPU/API key

**Umum**
- Mode **demo/simulasi** bawaan (tanpa biaya & tanpa API key)
- Progress bar polling status task
- Galeri riwayat (tersimpan di `data/history.json`)
- CLI `cli.py` untuk generate dari terminal
- Pilihan provider langsung di UI

---

## 🗂️ Struktur

Pola arsitektur meniru [Volcengine ai-app-lab — chat2cartoon_en](https://github.com/volcengine/ai-app-lab/tree/main/demohouse/chat2cartoon_en):
konfigurasi terpusat (`constants.py`), klien modular (`clients/`), dan main yang ramping.

```
project/
├── backend/
│   ├── main.py           # FastAPI app + routes (/api/*) + demo seedance
│   ├── config.py         # alias ke constants.py (backward-compat)
│   ├── constants.py      # Konfigurasi terpusat dari .env (pola chat2cartoon)
│   ├── svd.py            # re-export klien SVD (backward-compat)
│   └── clients/          # klien modular (pola chat2cartoon/app/clients)
│       ├── seedance.py   #   Seedance 2.5 client (create/poll/extract)
│       ├── svd.py        #   SVD client (NVIDIA NIM / local / demo)
│       └── downloader.py #   download media dari URL ke memory/file
├── static/
│   ├── index.html        # UI web
│   ├── app.js
│   └── style.css
├── cli.py                # CLI tool
├── requirements.txt
├── README.md
├── screenshots/
└── data/                 # history.json, uploads/
```

---

## 🚀 Menjalankan (Web App)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# opsional: salin & isi API key
cp .env.example .env
export ARK_API_KEY=your-byteplus-key

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Buka **http://localhost:8000**

> Tanpa `ARK_API_KEY`, aplikasi berjalan dalam **mode demo** (Seedance & SVD disimulasikan).

### API key Seedance (BytePlus ModelArk)

1. Daftar di [console.byteplus.com/ark](https://console.byteplus.com/ark) (region **ap-southeast-1**)
2. Top up ≥ USD 30 / beli AI Savings Plan
3. Aktifkan model **Dreamina Seedance 2.5** di *Model activation*
4. Buat **API key** → set `ARK_API_KEY`

Model ID bawaan: `dreamina-seedance-2-5-260628` (override via `SEEDANCE_MODEL`).

### SVD backend

| Mode | Cara |
|------|------|
| **NVIDIA NIM** | `export NVIDIA_API_KEY=...` → SVD diproses remote via NVIDIA NIM |
| **Local (GPU)** | `export SVD_LOCAL=1` + install `torch diffusers pillow` → diproses lokal |
| **Demo** | tanpa keduanya → simulasi |

---

## 💻 CLI

```bash
# Seedance 2.5 (text-to-video)
python3 cli.py seedance "Seekor kucing bermain piano saat matahari terbenam" --duration 8 --ratio 16:9

# Seedance dalam demo
python3 cli.py seedance "prompt apa saja" --demo

# SVD (image-to-video) - demo tanpa GPU
python3 cli.py svd ./foto.png --prompt "animasikan pelan" --demo

# SVD via NVIDIA NIM (perlu NVIDIA_API_KEY)
python3 cli.py svd ./foto.png --nvidia

# SVD lokal (perlu GPU + SVD_LOCAL=1)
python3 cli.py svd ./foto.png
```

---

## 🔌 API

| Method | Path | Keterangan |
|--------|------|-----------|
| POST | `/api/generate` | Buat task video (`{"provider": "seedance" \| "svd", "prompt": "...", "first_frame_url": "..."}`) |
| GET | `/api/status/{task_id}` | Polling status task |
| GET | `/api/history` | Riwayat 100 task |
| POST | `/api/upload` | Upload gambar (untuk first-frame SVD/Seedance) |
| GET | `/api/config` | Konfigurasi frontend (model, provider, status SVD) |
| GET | `/api/health` | Health check |

Contoh `POST /api/generate` (Seedance):

```json
{
  "provider": "seedance",
  "prompt": "A cat playing piano at sunset",
  "duration": 8,
  "resolution": "720p",
  "ratio": "16:9",
  "generate_audio": true,
  "watermark": false
}
```

Contoh `POST /api/generate` (SVD):

```json
{
  "provider": "svd",
  "prompt": "Animate gently",
  "first_frame_url": "/uploads/abc123.png"
}
```

---

## 📝 Catatan Produksi

- Seedance 2.5 (ModelArk) → format resmi `POST /api/v3/contents/generations/tasks`; URL video berlaku 24 jam.
- Seedance 1080p = H.265/HEVC 10-bit → gunakan pemutar modern (VLC/mpv) bila gagal.
- SVD local butuh GPU ≥ 8GB VRAM (SVD-XT); tanpa itu gunakan demo/NVIDIA NIM.
- `data/history.json` & `data/uploads/` adalah data lokal; hapus untuk reset.

---

## 🧩 Rujukan Arsitektur: Volcengine ai-app-lab / chat2cartoon_en

Aplikasi ini mengadaptasi pola dari contoh resmi **Volcengine**:
[`volcengine/ai-app-lab/demohouse/chat2cartoon_en`](https://github.com/volcengine/ai-app-lab/tree/main/demohouse/chat2cartoon_en)

### Pola yang diadaptasi

| Konsep chat2cartoon_en | Implementasi di aplikasi ini |
|---|---|
| `app/constants.py` — semua env dibaca terpusat | `backend/constants.py` |
| `app/clients/*` — klien per-layanan (llm, t2i, tos, tts, vlm, downloader) | `backend/clients/` (seedance, svd, downloader) |
| `app/generators/phases/video.py` — panggil video gen (create task → poll → download) | `backend/clients/seedance.py` (`create_task`, `get_task`, `extract_video_url`) |
| `app/clients/downloader.py` — unduh media dari URL | `backend/clients/downloader.py` |
| `.env` dengan endpoint & key terpusat | `.env` + `constants.py` |
| async task + polling status | `GET /api/status/{task_id}` |

### Perbedaan utama
- **chat2cartoon** memakai **state machine multi-fase** (script → storyboard → role → first frame → video → audio → film) dengan SSE streaming lewat `/api/v3/bots/chat/completions`.
- **Aplikasi ini** fokus pada **generasi video langsung** (Seedance 2.5 text-to-video & SVD image-to-video) dengan REST sederhana `/api/generate` — ideal untuk video maker yang tidak butuh pipeline cerita kompleks.

> Jika ingin pipeline video cerita panjang (seperti chat2cartoon), saran: tambahkan fase-fase di `backend/generators/` dan frontend chat (SSE).

---

*Dibuat dengan ❤️ sebagai AI Video Maker. Untuk penggunaan model, patuhi lisensi masing-masing provider (BytePlus/ByteDance, Stability AI).*
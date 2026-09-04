# AI Video Maker - Seedance 2.5

Aplikasi web untuk membuat video AI menggunakan model **Dreamina Seedance 2.5**
via API resmi BytePlus ModelArk. Mendukung text-to-video, image-to-video (first frame),
audio asli sinkron, durasi hingga 30 detik, dan resolusi 480p/720p/1080p.

Stack: FastAPI + HTML/CSS/JS vanilla (tanpa build step.

## Fitur

- Text-to-video dengan prompt bahasa natural (dialog dalam kutip ganda untuk lip-sync
- Image-to-video (opsional:: upload gambar lokal atau tempel URL publik untuk first frame
- Audio asli: model menghasilkan suara manusia, efek suara, dan musik sinkron
- Durasi 4-30 detik; resolusi 480p/720p/1080p; rasio 16:9, 9:16, 1:1, 4:3, 3:4, 21:9, atau adaptive
- Progress bar polling status task dan galeri riwayat (tersimpan di data/history.json
- **Mode demo**: bila `ARK_API_KEY` belum diatur, aplikasi berjalan di mode simulasi penuh
  sehingga UI tetap bisa dicoba tanpa biaya.

## Cara menjalankan

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# opsional: salin dan isi API key
cp .env.example .env
export ARK_API_KEY=your-key-here

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Buka http://localhost:8000

## Mendapatkan API key

1. Daftar di [console.byteplus.com/ark](https://console.byteplus.com/ark) di region **ap-southeast-1**
2. Top up saldo atau beli AI Savings Plan (>= USD 30 argparse
3. Aktifkan model *Dreamina Seedance 2.5* di halaman Model activation
4. Buat **API key** di halaman API keys
5. Set env `ARK_API_KEY`.

Model ID bawaan: `dreamina-seedance-2-5-260628`
(cek daftar model terbaru di Model list konsol; bisa dioverride via `SEEDANCE_MODEL`.

## API

| Method | Path | Keterangan |
|---|---|---|
| POST | `/api/generate` | Buat task generasi video |
| GET  | `/api/status/{task_id}` | Polling status task |
| GET  | `/api/history` | Riwayat 100 task terakhir |
| POST | `/api/upload` | Upload gambar untuk first frame |
| GET  | `/api/config` | Konfigurasi frontend |
| GET  | `/api/health` | Health check |

Contoh body `/api/generate`:

```json
{
  "model": "dreamina-seedance-2-5-260628",
  "content": [
    { "type": "text", "text": "A cat playing piano at sunset" }
  ],
  "duration":  8,
  "resolution": "720p",
  "ratio": "16:9",
  "generate_audio": true,
  "watermark": false
}
```

Endpoint ini mengikuti skema resmi ModelArk
`POST /api/v3/contents/generations/tasks` -
lihat [dokumentasi resmi](https://docs.byteplus.com/en/docs/ModelArk/1520757.

## Catatan produksi

- `data/history.json` hanya lokal; hapus bila ingin reset.
- URL video ModelArk berlaku 24 jam (maks 100x unduh
- Untuk image-to-video di mode live, gambar harus URL publik
  Gambar upload lokal (`/uploads/...`) hanya berfungsi bila server bisa diakses publik
- Hasil 1080p Seedance 2.5 memakai H.265/HEVC 10-bit} gunakan
  pemutar modern seperti VLC, mpv, atau QuickTime bila gagal diputar.


```

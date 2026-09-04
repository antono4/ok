#!/usr/bin/env python3
"""AI Video Maker CLI.

Generate videos from the terminal using either provider:

  Seedance 2.5 (text-to-video, audio)  -> BytePlus ModelArk API
  Stable Video Diffusion (image-to-video) -> NVIDIA NIM API / local diffusers

Examples:
  python cli.py seedance "A cat playing piano at sunset" --duration 8 --ratio 16:9
  python cli.py svd ./photo.png --prompt "Animate gently" --demo
  python cli.py svd ./photo.png --nvidia
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402


def _seedance_api_key() -> str:
    key = os.getenv("ARK_API_KEY", "").strip()
    if not key:
        print("ARK_API_KEY belum diatur. Set env ARK_API_KEY atau gunakan --demo.")
        sys.exit(1)
    return key


async def _seedance_generate(prompt: str, duration: int, resolution: str,
                             ratio: str, audio: bool, watermark: bool,
                             first_frame: str | None, demo: bool) -> None:
    base = os.getenv("ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3").rstrip("/")
    model = os.getenv("SEEDANCE_MODEL", "dreamina-seedance-2-5-260628")
    if demo:
        print("[demo] Seedance 2.5 task dibuat (simulasi).")
        task_id = "demo-cli-" + str(int(time.time()))
    else:
        key = _seedance_api_key()
        content: list[dict] = [{"type": "text", "text": prompt}]
        if first_frame:
            content.append({"type": "image_url", "image_url": {"url": first_frame}, "role": "first_frame"})
        body = {
            "model": model,
            "content": content,
            "duration": duration,
            "resolution": resolution,
            "ratio": ratio,
            "generate_audio": audio,
            "watermark": watermark,
            "output_format": "mp4",
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{base}/contents/generations/tasks", headers=headers, json=body)
        if resp.status_code >= 400:
            print(f"Gagal membuat task: {resp.status_code} {resp.text[:500]}")
            sys.exit(1)
        task_id = resp.json().get("id")
        print(f"Task dibuat: {task_id}")

    # poll
    while True:
        if demo:
            time.sleep(2)
            print("  status: succeeded (demo)")
            print("  video_url: (demo - tidak ada file nyata)")
            return
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{base}/contents/generations/tasks/{task_id}",
                                 headers={"Authorization": f"Bearer {_seedance_api_key()}"})
        if r.status_code >= 400:
            print(f"Gagal query status: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        data = r.json()
        status = data.get("status")
        print(f"  status: {status}")
        if status == "succeeded":
            url = (data.get("content") or {}).get("video_url")
            print(f"  video_url: {url}")
            return
        if status in ("failed", "expired", "cancelled"):
            print(f"  error: {data.get('error')}")
            sys.exit(1)
        time.sleep(5)


async def _svd_generate(image: str, prompt: str, demo: bool, nvidia: bool) -> None:
    from backend import svd

    if demo:
        print("[demo] SVD task dibuat (simulasi).")
        task_id, entry = svd.create_task({"prompt": prompt, "image_path": image})
        entry["demo"] = True
        while True:
            time.sleep(2)
            st = svd._demo_poll(entry)
            print(f"  status: {st['status']} ({st['progress']}%)")
            if st["status"] == "succeeded":
                print("  video_url: (demo - tidak ada file nyata)")
                return
        return

    if nvidia or svd.nvidia_available():
        if not svd.nvidia_available():
            print("NVIDIA_API_KEY belum diatur.")
            sys.exit(1)
        print("Mengirim task ke NVIDIA NIM...")
        task_id, entry = svd.create_task({"prompt": prompt, "image_path": image})
        entry["demo"] = False
        remote_id = await svd.submit_task(entry)
        print(f"  request_id: {remote_id}")
        while True:
            time.sleep(5)
            st = await svd.poll_task(entry)
            print(f"  status: {st.get('status')} ({st.get('progress')}%)")
            if st.get("status") == "succeeded":
                print(f"  video_url: {st.get('video_url')}")
                return
            if st.get("status") in ("failed", "cancelled", "error"):
                print(f"  error: {st.get('error')}")
                sys.exit(1)
        return

    if svd.local_available():
        print("Menjalankan SVD lokal (diffusers)...")
        task_id, entry = svd.create_task({"prompt": prompt, "image_path": image})
        entry["demo"] = False
        await svd.submit_task(entry)
        print(f"  video: {entry.get('video_path')}")
        return

    print("Tidak ada backend SVD tersedia. Set NVIDIA_API_KEY, aktifkan SVD_LOCAL=1 dengan GPU, atau gunakan --demo.")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Video Maker CLI (Seedance 2.5 / SVD)")
    sub = parser.add_subparsers(dest="provider", required=True)

    p_seed = sub.add_parser("seedance", help="Text-to-video dengan Seedance 2.5")
    p_seed.add_argument("prompt")
    p_seed.add_argument("--duration", type=int, default=8)
    p_seed.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    p_seed.add_argument("--ratio", default="16:9")
    p_seed.add_argument("--no-audio", action="store_true")
    p_seed.add_argument("--watermark", action="store_true")
    p_seed.add_argument("--first-frame", default=None)
    p_seed.add_argument("--demo", action="store_true")

    p_svd = sub.add_parser("svd", help="Image-to-video dengan Stable Video Diffusion")
    p_svd.add_argument("image")
    p_svd.add_argument("--prompt", default="")
    p_svd.add_argument("--nvidia", action="store_true", help="Paksa pakai NVIDIA NIM API")
    p_svd.add_argument("--demo", action="store_true")

    args = parser.parse_args()
    if args.provider == "seedance":
        asyncio.run(_seedance_generate(
            args.prompt, args.duration, args.resolution, args.ratio,
            not args.no_audio, args.watermark, args.first_frame, args.demo,
        ))
    elif args.provider == "svd":
        asyncio.run(_svd_generate(args.image, args.prompt, args.demo, args.nvidia))


if __name__ == "__main__":
    main()
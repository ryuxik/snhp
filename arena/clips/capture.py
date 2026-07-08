"""Capture a shareable clip of the arena.

Drives the page headless with Playwright at a fixed size, screenshots the canvas
each frame, and ffmpegs the frames into an MP4 + GIF for X. Runs against the live
page (a window of live play) or a deterministic replay of a committed generation.

Dependencies are DEV-ONLY (never in the prod image):
    pip install playwright && playwright install chromium
    brew install ffmpeg   # or apt-get install ffmpeg

Usage:
    python arena/clips/capture.py --url http://localhost:8201 --seconds 12
    python arena/clips/capture.py --replay 214 --url http://localhost:8201
    python arena/clips/capture.py --card --url http://localhost:8201   # end-card PNG

Output lands in arena/clips/out/ (gitignored).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

OUT = os.path.join(os.path.dirname(__file__), "out")


def _ensure_out() -> None:
    os.makedirs(OUT, exist_ok=True)


def capture(url: str, seconds: float, replay: int | None, fps: int, name: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed — `pip install playwright && playwright install chromium`")
    _ensure_out()
    q = "?clip=1"
    if replay is not None:
        q += f"&replay={replay}"
    target = url.rstrip("/") + "/" + q
    frames_dir = os.path.join(OUT, name + "_frames")
    os.makedirs(frames_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 960, "height": 540},
                                device_scale_factor=1)
        page.goto(target)
        page.wait_for_selector("#view", timeout=10000)
        page.wait_for_timeout(1500)  # let the world populate
        n = int(seconds * fps)
        canvas = page.query_selector("#view")
        for i in range(n):
            canvas.screenshot(path=os.path.join(frames_dir, f"f{i:04d}.png"))
            page.wait_for_timeout(int(1000 / fps))
        browser.close()

    mp4 = os.path.join(OUT, name + ".mp4")
    gif = os.path.join(OUT, name + ".gif")
    _ffmpeg(["-y", "-framerate", str(fps), "-i", os.path.join(frames_dir, "f%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4])
    # two-pass palette GIF
    pal = os.path.join(frames_dir, "pal.png")
    _ffmpeg(["-y", "-i", mp4, "-vf", "fps=20,scale=640:-1:flags=lanczos,palettegen", pal])
    _ffmpeg(["-y", "-i", mp4, "-i", pal, "-lavfi",
             "fps=20,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse", gif])
    print(f"wrote {mp4}\nwrote {gif}")


def card(url: str, name: str) -> None:
    """Render a 2400x1260 OG/X end-card (2x the 1200x630 convention)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed")
    _ensure_out()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=2)
        page.goto(url.rstrip("/") + "/?clip=1")
        page.wait_for_selector("#view", timeout=10000)
        page.wait_for_timeout(2500)
        out = os.path.join(OUT, name + "_card.png")
        page.screenshot(path=out)
        browser.close()
    print(f"wrote {out}")


def _ffmpeg(args: list[str]) -> None:
    if not _have("ffmpeg"):
        sys.exit("ffmpeg not found — `brew install ffmpeg`")
    subprocess.run(["ffmpeg", *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8201")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--replay", type=int, default=None)
    ap.add_argument("--card", action="store_true")
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    name = a.name or (f"replay{a.replay}" if a.replay is not None else "clip") + f"_{int(time.time())}"
    if a.card:
        card(a.url, name)
    else:
        capture(a.url, a.seconds, a.replay, a.fps, name)


if __name__ == "__main__":
    main()

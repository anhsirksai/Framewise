"""Download permitted source videos into data/videos using yt-dlp.

Use this only for videos you own, have permission to use, or are licensed for
download/reuse. The script intentionally avoids bypass flags and anti-blocking
workarounds.

Run:
  uv run --with yt-dlp python scripts/download_videos.py URL [URL ...]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download permitted videos into data/videos.")
    parser.add_argument("urls", nargs="+", help="Video page URLs to download.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[2] / "data" / "videos"),
        help="Directory for downloaded MP4 files.",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=8.0,
        help="Courtesy pause between downloads.",
    )
    parser.add_argument(
        "--allow-playlist",
        action="store_true",
        help="Allow playlist downloads. By default, only single videos are downloaded.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("yt-dlp is not installed. Run through: uv run --with yt-dlp python scripts/download_videos.py ...")
        return 2

    ydl_opts = {
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(title).120s-%(id)s.%(ext)s"),
        "noplaylist": not args.allow_playlist,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "ignoreerrors": "only_download",
    }

    with YoutubeDL(ydl_opts) as ydl:
        for index, url in enumerate(args.urls):
            if index:
                time.sleep(max(0.0, args.interval_sec))
            print(f"Downloading {url}")
            ydl.download([url])

    print(f"Downloaded videos to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

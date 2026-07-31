"""Render rough-cut plans into local MP4 artifacts with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT_DIR / "data" / "videos"
GENERATED_DIR = ROOT_DIR / "data" / "generated"


class RenderError(RuntimeError):
    """Raised when a rough cut cannot be rendered."""


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderError("ffmpeg is not installed or not on PATH. Install ffmpeg to render MP4 rough cuts.")
    return ffmpeg


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _video_lookup() -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    for path in VIDEO_DIR.glob("*.mp4"):
        lookup[_norm(path.stem)] = path
    return lookup


def _source_path(scene: dict[str, Any], lookup: dict[str, Path]) -> Path | None:
    title = str(scene.get("source_video") or "").strip()
    if not title:
        return None
    exact = lookup.get(_norm(title))
    if exact:
        return exact
    title_norm = _norm(title)
    for key, path in lookup.items():
        if title_norm in key or key in title_norm:
            return path
    return None


def _duration(scene: dict[str, Any], fallback: float) -> float:
    try:
        start = float(scene.get("start_sec") or 0)
        end = float(scene.get("end_sec") or 0)
    except (TypeError, ValueError):
        return fallback
    if end <= start:
        return fallback
    return max(1.0, min(end - start, fallback))


def _start(scene: dict[str, Any]) -> float:
    try:
        return max(0.0, float(scene.get("start_sec") or 0))
    except (TypeError, ValueError):
        return 0.0


def _concat_line(path: Path) -> str:
    """Return an ffmpeg concat-demuxer line for an absolute path."""
    escaped = str(path).replace("'", "'\\''")
    return f"file '{escaped}'\n"


def render_rough_cut(rough_cut: dict[str, Any]) -> dict[str, Any]:
    """Render rough_cut.scenes into one MP4 and return artifact metadata."""
    ffmpeg = _require_ffmpeg()
    scenes = [s for s in rough_cut.get("scenes", []) if isinstance(s, dict)]
    if not scenes:
        raise RenderError("rough cut has no renderable scenes")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    rough_cut_id = str(rough_cut["id"])
    work_dir = GENERATED_DIR / rough_cut_id
    work_dir.mkdir(parents=True, exist_ok=True)

    lookup = _video_lookup()
    target_duration = float(rough_cut.get("target_duration_sec") or 30)
    per_scene = max(1.5, target_duration / max(1, len(scenes)))

    clip_paths: list[Path] = []
    rendered_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        source = _source_path(scene, lookup)
        if not source:
            continue
        start = _start(scene)
        duration = _duration(scene, per_scene)
        clip_path = work_dir / f"scene-{index:02d}.mp4"
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-vf",
            "scale=1280:-2,fps=30,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        clip_paths.append(clip_path)
        rendered_scenes.append({
            "order": scene.get("order", index),
            "source_file": str(source.relative_to(ROOT_DIR)),
            "start_sec": start,
            "duration_sec": duration,
            "output_file": str(clip_path.relative_to(ROOT_DIR)),
        })

    if not clip_paths:
        raise RenderError("none of the rough-cut scenes matched local MP4 files in data/videos")

    concat_file = work_dir / "concat.txt"
    concat_file.write_text(
        "".join(_concat_line(path) for path in clip_paths),
        encoding="utf-8",
    )
    output_path = GENERATED_DIR / f"{rough_cut_id}.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return {
        "url": f"/artifacts/{output_path.name}",
        "path": str(output_path.relative_to(ROOT_DIR)),
        "scenes": rendered_scenes,
    }

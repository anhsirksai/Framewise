"""Ingest videos into the Framewise Neo4j evidence graph (CLI).

The pipeline itself lives in app/ingestion.py and is shared with the
POST /api/ingest/upload endpoint. This script is the command-line entry:

  uv run python scripts/ingest.py [VIDEO_URL | FILE.mp4 ...] [--video-id=ID]
                                  [--index-id=ID] [--schema-only] [--force]

With no args it ingests the local sample(s) in data/videos/*.mp4, falling
back to SAMPLE_VIDEO_URLS from .env if that directory is empty.
Duplicates are skipped: same filename already in TwelveLabs -> no re-upload;
video already in the graph -> no re-analysis (--force overrides).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest")

sys.path.insert(0, ".")

from app.config import settings  # noqa: E402
from app.context_graph_client import connect_neo4j, close_neo4j, execute_cypher  # noqa: E402
from app.vector_client import ensure_segment_vector_index  # noqa: E402
from app import twelvelabs_client as tl  # noqa: E402
from app.ingestion import ingest_source, ingest_existing  # noqa: E402


def _vendored_samples() -> list[str]:
    """Return vendored sample clips shipped in the repo's data/videos/ dir."""
    vids = Path(__file__).resolve().parents[2] / "data" / "videos"
    return sorted(str(p) for p in vids.glob("*.mp4")) if vids.is_dir() else []


async def apply_schema() -> None:
    """Run the constraint/index statements from cypher/schema.cypher."""
    with open("../cypher/schema.cypher", "r") as f:
        body = f.read()
    # Strip //-comment lines FIRST so a ';' inside a comment can't split a statement.
    code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("//"))
    for stmt in [s.strip() for s in code.split(";") if s.strip()]:
        try:
            await execute_cypher(stmt, collect=False)
        except Exception as e:
            log.warning("schema stmt skipped: %s (%s)", stmt[:60], e)


def _log_stage(stage: str, detail: str) -> None:
    log.info("  [%s] %s", stage, detail)


async def main() -> None:
    args = sys.argv[1:]
    schema_only = "--schema-only" in args
    force = "--force" in args  # re-analyze even if the video is already in the graph
    index_override: str | None = None
    video_ids: list[str] = []
    sources: list[str] = []
    for a in args:
        if a in ("--schema-only", "--force"):
            continue
        if a.startswith("--index-id="):
            index_override = a.split("=", 1)[1]
        elif a.startswith("--video-id="):
            video_ids.append(a.split("=", 1)[1])
        elif a.startswith("--"):
            log.warning("unknown flag %s", a)
        else:
            sources.append(a)
    if not sources and not video_ids and not schema_only:
        sources = _vendored_samples() or settings.sample_video_url_list
        if sources:
            log.info("No inputs given — using vendored sample(s): %s", ", ".join(sources))

    if schema_only:
        await connect_neo4j()
        try:
            await apply_schema()
            log.info("Schema applied.")
        finally:
            await close_neo4j()
        return

    if not sources and not video_ids:
        log.error("Nothing to ingest. Pass URLs / file paths / --video-id=..., or set SAMPLE_VIDEO_URLS.")
        return

    await connect_neo4j()
    try:
        await apply_schema()
        # For existing-video ingestion the index is provided; otherwise create/reuse ours.
        if index_override:
            index_id = index_override
        elif settings.tl_index_id:
            index_id = settings.tl_index_id
        else:
            index_id = await asyncio.to_thread(tl.ensure_index)
        log.info("Using TwelveLabs index %s", index_id)

        dim = 0
        for vid in video_ids:
            try:
                log.info("Ingesting existing video %s from index %s ...", vid, index_id)
                r = await ingest_existing(index_id, vid, on_stage=_log_stage)
                dim = dim or r.get("dim", 0)
            except Exception as e:
                log.exception("Failed to ingest existing video %s: %s", vid, e)
        for src in sources:
            try:
                r = await ingest_source(index_id, src, force=force, on_stage=_log_stage)
                if r["status"] == "skipped":
                    log.info("Skipped '%s': %s", r["title"], r.get("detail"))
                dim = dim or r.get("dim", 0)
            except Exception as e:
                log.exception("Failed to ingest %s: %s", src, e)

        if dim:
            await ensure_segment_vector_index(dim)
            log.info("Vector index ready (dim=%d)", dim)
        else:
            log.info("No new embeddings produced (everything skipped or failed) — vector index left as-is.")
    finally:
        await close_neo4j()


if __name__ == "__main__":
    asyncio.run(main())

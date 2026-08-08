"""Video ingestion pipeline + in-process upload job manager.

The pipeline (TwelveLabs index -> Pegasus analyze -> LLM structure -> Marengo
embed -> Neo4j write) lives here so both the CLI (scripts/ingest.py) and the
upload API (POST /api/ingest/upload) share one implementation.

Blocking SDK calls are wrapped in asyncio.to_thread so jobs can run inside the
FastAPI event loop without stalling other requests. Job state is in-process
(single machine) — fine for the demo deployment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Callable, Literal

from pydantic import BaseModel

from app.config import settings
from app.context_graph_client import execute_cypher
from app.vector_client import ensure_segment_vector_index
from app import twelvelabs_client as tl

log = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]  # (stage, detail)


PEGASUS_PROMPT = (
    "Analyze this video and break it into its distinct segments in chronological "
    "order. For each segment give: the approximate start and end time in seconds, "
    "a one-sentence description of what is happening (who/what is visible), any "
    "visible on-screen text, and any spoken words. Also name the overall topics. "
    "Be concrete and specific about people, organizations, places, objects, and brands."
)

STRUCTURE_SYSTEM = (
    "You convert a video analysis into strict JSON. Output ONLY a JSON object of the form:\n"
    '{"video_summary": str, "segments": [{"start_sec": number, "end_sec": number, '
    '"summary": str, "on_screen_text": str, "transcript": str, '
    '"entities": [{"name": str, "type": one of '
    '["person","organization","location","object","product","brand","event","concept"]}], '
    '"topics": [str]}]}\n'
    "Canonicalize entity and topic names (Title Case, singular, no duplicates within a segment). "
    "Use the SAME canonical name for the same real-world thing so it can be merged across videos."
)


class VideoEntity(BaseModel):
    name: str
    type: Literal[
        "person", "organization", "location", "object", "product", "brand", "event", "concept"
    ]


class VideoSegment(BaseModel):
    start_sec: float
    end_sec: float
    summary: str
    on_screen_text: str
    transcript: str
    entities: list[VideoEntity]
    topics: list[str]


class VideoAnalysis(BaseModel):
    video_summary: str
    segments: list[VideoSegment]


def _norm_key(name: str) -> str:
    return " ".join(name.strip().lower().split())


# ---------------------------------------------------------------------------
# Resolution guard — TwelveLabs accepts 360x360 up to 5184x2160. Phone videos
# (4K/8K) exceed this, so we probe local files and downscale with ffmpeg
# before upload instead of failing with video_resolution_too_high.
# ---------------------------------------------------------------------------

_TL_MAX_LONG_SIDE = 5184
_TL_MAX_SHORT_SIDE = 2160
_TARGET_LONG_SIDE = 1920  # 1080p-class output: fast to index, plenty for search


def _probe_resolution(path: str) -> tuple[int, int] | None:
    """Return (width, height) of the first video stream, or None if unknown."""
    import shutil
    import subprocess

    if not shutil.which("ffprobe"):
        log.warning("ffprobe not available — skipping resolution check for %s", path)
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        w, h = (int(x) for x in out.split(",")[:2])
        return w, h
    except Exception as e:
        log.warning("ffprobe failed for %s: %s", path, e)
        return None


def downscale_if_needed(path: str, on_stage: StageCallback | None = None) -> str:
    """Downscale a local video that exceeds TwelveLabs' resolution limits.

    Returns the path to use for upload: the original when in bounds, or a
    transcoded copy (same filename, sibling temp dir) when it was too large.
    """
    import shutil
    import subprocess
    import tempfile

    res = _probe_resolution(path)
    if not res:
        return path
    w, h = res
    long_side, short_side = max(w, h), min(w, h)
    if long_side <= _TL_MAX_LONG_SIDE and short_side <= _TL_MAX_SHORT_SIDE:
        return path

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            f"Video is {w}x{h}, above the TwelveLabs limit ({_TL_MAX_SHORT_SIDE}p), "
            "and ffmpeg is not installed to downscale it. Please upload a version "
            "at 2160p or below."
        )

    if on_stage:
        on_stage("transcoding", f"Video is {w}x{h} — downscaling to fit the 2160p limit")
    log.info("Downscaling %s (%dx%d) to long side %d ...", path, w, h, _TARGET_LONG_SIDE)

    out_dir = tempfile.mkdtemp(prefix="framewise_transcode_")
    out_path = os.path.join(out_dir, os.path.basename(path))
    # Scale the long side down to the target, keep aspect, force even dims for h264.
    scale = (f"scale={_TARGET_LONG_SIDE}:-2" if w >= h else f"scale=-2:{_TARGET_LONG_SIDE}")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path,
         "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-movflags", "+faststart", out_path],
        capture_output=True, text=True, timeout=1800, check=True,
    )
    new_res = _probe_resolution(out_path)
    log.info("Downscaled to %s (%s)", out_path, f"{new_res[0]}x{new_res[1]}" if new_res else "?")
    return out_path


def structure_with_llm(pegasus_text: str) -> dict:
    """Turn Pegasus prose into schema-validated video and segment data.

    Provider-generic (OpenAI or Claude, per LLM_PROVIDER in .env).
    """
    from app import llm_client

    parsed = llm_client.parse_structured(
        STRUCTURE_SYSTEM,
        f"Video analysis:\n\n{pegasus_text}",
        VideoAnalysis,
    )
    return parsed.model_dump()


async def write_video(video: dict, segments: list[dict]) -> None:
    """Write one video and its segments/entities/topics to Neo4j."""
    domain = settings.domain_id
    await execute_cypher(
        """
        MERGE (v:Video {id: $id})
        SET v.title = $title, v.url = $url, v.duration_sec = $duration_sec,
            v.summary = $summary, v.tl_index_id = $tl_index_id, v.domain = $domain
        """,
        {**video, "domain": domain},
        collect=False,
    )

    # Idempotent re-ingest: drop this video's old segments (entities/topics are
    # shared and stay MERGE'd) so re-running seed can't violate the unique
    # constraint on Segment.id or leave stale segments behind.
    await execute_cypher(
        "MATCH (:Video {id: $vid})-[:HAS_SEGMENT]->(s:Segment) DETACH DELETE s",
        {"vid": video["id"]},
        collect=False,
    )

    seg_rows = []
    for i, s in enumerate(segments):
        seg_rows.append({
            "id": f"{video['id']}#{i}",
            "idx": i,
            "video_id": video["id"],
            "start_sec": s.get("start_sec"),
            "end_sec": s.get("end_sec"),
            "summary": s.get("summary", ""),
            "on_screen_text": s.get("on_screen_text", ""),
            "transcript": s.get("transcript", ""),
            "embedding": s.get("embedding"),
            "entities": [{"key": _norm_key(e["name"]), "name": e["name"].strip(),
                          "type": e.get("type", "concept")}
                         for e in s.get("entities", []) if e.get("name")],
            "topics": [{"key": _norm_key(t), "name": t.strip()}
                       for t in s.get("topics", []) if t],
        })

    await execute_cypher(
        """
        MATCH (v:Video {id: $vid})
        UNWIND $rows AS row
          CREATE (s:Segment {id: row.id})
          SET s.video_id = row.video_id, s.start_sec = row.start_sec,
              s.end_sec = row.end_sec, s.summary = row.summary,
              s.on_screen_text = row.on_screen_text, s.transcript = row.transcript,
              s.embedding = row.embedding, s.domain = $domain, s.idx = row.idx
          MERGE (v)-[:HAS_SEGMENT]->(s)
          FOREACH (ent IN row.entities |
            MERGE (e:Entity {key: ent.key})
            SET e.name = ent.name, e.type = ent.type, e.domain = $domain
            MERGE (s)-[:MENTIONS]->(e))
          FOREACH (top IN row.topics |
            MERGE (t:Topic {key: top.key})
            SET t.name = top.name, t.domain = $domain
            MERGE (s)-[:ABOUT]->(t))
        """,
        {"vid": video["id"], "rows": seg_rows, "domain": domain},
        collect=False,
    )

    # temporal NEXT chain
    await execute_cypher(
        """
        MATCH (v:Video {id: $vid})-[:HAS_SEGMENT]->(s:Segment)
        WITH s ORDER BY s.idx
        WITH collect(s) AS segs
        UNWIND range(0, size(segs)-2) AS i
          WITH segs[i] AS a, segs[i+1] AS b
          MERGE (a)-[:NEXT]->(b)
        """,
        {"vid": video["id"]},
        collect=False,
    )


async def already_in_graph(video_id: str) -> bool:
    """True when this video already has segments in Neo4j (fully ingested)."""
    try:
        rows = await execute_cypher(
            "MATCH (:Video {id: $id})-[:HAS_SEGMENT]->(s:Segment) RETURN count(s) AS n",
            {"id": video_id},
        )
        return bool(rows and rows[0].get("n", 0) > 0)
    except Exception as e:
        log.warning("Neo4j duplicate check failed for %s: %s", video_id, e)
        return False


async def analyze_embed_write(index_id: str, video_id: str, url: str | None,
                              title: str, duration_sec,
                              on_stage: StageCallback | None = None) -> int:
    """Shared tail: Pegasus analyze -> LLM structure -> Marengo embed -> Neo4j."""
    def stage(name: str, detail: str = "") -> None:
        if on_stage:
            on_stage(name, detail)

    stage("analyzing", "Pegasus is describing the video")
    log.info("Analyzing video_id=%s with Pegasus ...", video_id)
    pegasus_text = await asyncio.to_thread(tl.analyze_video, video_id, PEGASUS_PROMPT)

    stage("structuring", "LLM is extracting segments, entities and topics")
    structured = await asyncio.to_thread(structure_with_llm, pegasus_text)
    segments = structured.get("segments", [])
    log.info("Structured into %d segments. Embedding ...", len(segments))

    stage("embedding", f"Embedding {len(segments)} segments")
    dim = 0
    for s in segments:
        basis = " ".join(filter(None, [s.get("summary"), s.get("on_screen_text"), s.get("transcript")]))
        try:
            vec = await asyncio.to_thread(tl.embed_text, basis or s.get("summary", ""))
            s["embedding"] = vec
            dim = dim or len(vec)
        except Exception as e:
            log.warning("  embed failed for a segment: %s", e)
            s["embedding"] = None

    stage("writing", "Writing video and segments to the graph")
    video = {
        "id": video_id,
        "title": title,
        "url": url,
        "duration_sec": duration_sec,
        "summary": structured.get("video_summary", ""),
        "tl_index_id": index_id,
    }
    await write_video(video, segments)
    log.info("Wrote video '%s' (%d segments) to Neo4j", title, len(segments))
    return dim


async def ingest_source(index_id: str, source: str, force: bool = False,
                        on_stage: StageCallback | None = None) -> dict:
    """Ingest a video from a URL or local file path, with dedupe.

    Returns {status: "completed"|"skipped", video_id, title, dim}.
    """
    def stage(name: str, detail: str = "") -> None:
        if on_stage:
            on_stage(name, detail)

    is_file = not source.lower().startswith(("http://", "https://"))
    filename = os.path.basename(source) if is_file else source.rsplit("/", 1)[-1]
    title = filename.rsplit(".", 1)[0]

    stage("checking", "Checking for duplicates")
    existing = await asyncio.to_thread(tl.find_video_by_filename, index_id, filename)
    if existing:
        video_id = existing["video_id"]
        log.info("'%s' already indexed in TwelveLabs (video_id=%s) — skipping upload", filename, video_id)
        if not force and await already_in_graph(video_id):
            log.info("  already in Neo4j graph too — nothing to do")
            return {"status": "skipped", "video_id": video_id, "title": title, "dim": 0,
                    "detail": "Already ingested (TwelveLabs + graph). Nothing to do."}
        url = None if is_file else source
        if is_file:
            try:
                meta = await asyncio.to_thread(tl.get_video_meta, index_id, video_id)
                url = meta.get("url")
            except Exception:
                pass
        dim = await analyze_embed_write(index_id, video_id, url, title,
                                        existing.get("duration_sec"), on_stage)
        return {"status": "completed", "video_id": video_id, "title": title, "dim": dim}

    # Oversized local videos (4K/8K phone footage) get downscaled first —
    # TwelveLabs rejects anything above 2160p with video_resolution_too_high.
    upload_path = source
    if is_file:
        upload_path = await asyncio.to_thread(downscale_if_needed, source, stage)

    stage("indexing", "Uploading and indexing with TwelveLabs (the slow part)")
    log.info("Indexing %s: %s ...", "file" if is_file else "url", source)
    cb = lambda st: stage("indexing", f"TwelveLabs status: {st}")  # noqa: E731
    try:
        if is_file:
            info = await asyncio.to_thread(
                lambda: tl.ingest_video(index_id, video_file=upload_path, on_update=cb))
        else:
            info = await asyncio.to_thread(
                lambda: tl.ingest_video(index_id, video_url=source, on_update=cb))
    finally:
        if upload_path != source:
            import shutil
            shutil.rmtree(os.path.dirname(upload_path), ignore_errors=True)

    video_id = info.get("video_id")
    if not video_id:
        raise RuntimeError(f"TwelveLabs returned no video_id for {source}")

    title = (info.get("filename") or filename).rsplit(".", 1)[0]
    url = None if is_file else source
    if is_file:
        try:
            meta = await asyncio.to_thread(tl.get_video_meta, index_id, video_id)
            url = meta.get("url")
        except Exception:
            pass
    dim = await analyze_embed_write(index_id, video_id, url, title,
                                    info.get("duration_sec"), on_stage)
    return {"status": "completed", "video_id": video_id, "title": title, "dim": dim}


async def ingest_existing(index_id: str, video_id: str,
                          on_stage: StageCallback | None = None) -> dict:
    """Ingest a video ALREADY indexed in TwelveLabs, by (index_id, video_id)."""
    meta = await asyncio.to_thread(tl.get_video_meta, index_id, video_id)
    title = (meta.get("filename") or video_id).rsplit(".", 1)[0]
    dim = await analyze_embed_write(index_id, video_id, meta.get("url"), title,
                                    meta.get("duration_sec"), on_stage)
    return {"status": "completed", "video_id": video_id, "title": title, "dim": dim}


# ---------------------------------------------------------------------------
# Upload job manager (in-process; single-machine deployment)
# ---------------------------------------------------------------------------

JOBS: dict[str, dict] = {}
_MAX_JOBS = 50


def _prune_jobs() -> None:
    if len(JOBS) > _MAX_JOBS:
        for jid in sorted(JOBS, key=lambda j: JOBS[j]["created_at"])[: len(JOBS) - _MAX_JOBS]:
            JOBS.pop(jid, None)


def start_upload_job(tmp_path: str, filename: str) -> dict:
    """Register a job for an uploaded file and run the pipeline in the background."""
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "filename": filename,
        "status": "running",          # running | completed | skipped | failed
        "stage": "queued",
        "detail": "Waiting to start",
        "video_id": None,
        "title": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    JOBS[job_id] = job
    _prune_jobs()

    def on_stage(stage: str, detail: str) -> None:
        job["stage"] = stage
        job["detail"] = detail
        job["updated_at"] = time.time()

    async def run() -> None:
        try:
            index_id = settings.tl_index_id or await asyncio.to_thread(tl.ensure_index)
            result = await ingest_source(index_id, tmp_path, on_stage=on_stage)
            if result.get("dim"):
                await ensure_segment_vector_index(result["dim"])
            job["status"] = result["status"]
            job["stage"] = "done"
            job["detail"] = result.get("detail") or "Ingested and ready to query."
            job["video_id"] = result.get("video_id")
            job["title"] = result.get("title")
        except Exception as e:
            log.exception("Upload job %s failed: %s", job_id, e)
            job["status"] = "failed"
            job["stage"] = "error"
            job["error"] = str(e)
            job["detail"] = f"Ingestion failed: {e}"
        finally:
            job["updated_at"] = time.time()
            try:
                import shutil
                shutil.rmtree(os.path.dirname(tmp_path), ignore_errors=True)
            except OSError:
                pass

    asyncio.get_running_loop().create_task(run())
    return job

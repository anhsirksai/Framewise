"""API routes for Framewise."""

from __future__ import annotations

import asyncio
import json
import re
import uuid as _uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.agent import handle_message, handle_message_stream
from app.config import settings
from app.context_graph_client import (
    execute_cypher, get_schema, get_schema_visualization, expand_node,
    get_collector, is_connected,
)

router = APIRouter()


def _require_neo4j():
    if not is_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is unavailable. Check your connection and restart the server.",
        )


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    graph_data: dict | None = None
    tool_calls: list[dict] | None = None


class CypherRequest(BaseModel):
    query: str
    parameters: dict | None = None


class ExpandRequest(BaseModel):
    element_id: str


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    limit: int = 8


class GenerateBriefRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)
    theme: str | None = Field(default=None, max_length=120)
    target_duration_sec: int = Field(default=45, ge=10, le=180)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    _require_neo4j()
    try:
        collector = get_collector()
        collector.drain()
        collector.drain_tool_calls()
        result = await handle_message(request.message, request.session_id)
        if result.get("graph_data") is None:
            collected = collector.drain()
            if collected:
                result["graph_data"] = {"results": collected}
        tool_calls = collector.drain_tool_calls()
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming SSE chat. Events: session_id, tool_start, tool_end, text_delta, done, error."""
    _require_neo4j()
    session_id = request.session_id or str(_uuid.uuid4())
    collector = get_collector()
    collector.drain()
    collector.drain_tool_calls()

    event_queue: asyncio.Queue = asyncio.Queue()
    collector.set_event_queue(event_queue)

    async def run_agent():
        try:
            await handle_message_stream(request.message, session_id)
        except Exception as e:
            try:
                event_queue.put_nowait({"event": "error", "data": {"detail": str(e)}})
            except Exception:
                pass
        finally:
            await asyncio.sleep(0.1)
            collector.clear_event_queue()

    async def event_generator():
        task = asyncio.create_task(run_agent())
        yield f"event: session_id\ndata: {json.dumps({'session_id': session_id})}\n\n"
        idle_timeout = 120.0
        overall_timeout = 300.0
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        try:
            while True:
                if loop.time() - start_time > overall_timeout:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Request exceeded maximum duration'})}\n\n"
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=idle_timeout)
                except asyncio.TimeoutError:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Request timed out'})}\n\n"
                    break
                event_type = event["event"]
                event_data = json.dumps(event["data"], default=str)
                yield f"event: {event_type}\ndata: {event_data}\n\n"
                if event_type in ("done", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Graph / schema
# ---------------------------------------------------------------------------

@router.get("/schema")
async def schema():
    _require_neo4j()
    return await get_schema()


@router.get("/schema/visualization")
async def schema_visualization():
    _require_neo4j()
    return await get_schema_visualization()


@router.post("/expand")
async def expand(request: ExpandRequest):
    _require_neo4j()
    return await expand_node(request.element_id)


@router.post("/cypher")
async def cypher(request: CypherRequest):
    _require_neo4j()
    try:
        results = await execute_cypher(request.query, dict(request.parameters or {}))
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Video-specific
# ---------------------------------------------------------------------------

@router.get("/videos")
async def list_videos():
    """List indexed videos with their segment counts."""
    _require_neo4j()
    results = await execute_cypher(
        """
        MATCH (v:Video)
        OPTIONAL MATCH (v)-[:HAS_SEGMENT]->(s:Segment)
        RETURN v.id AS id, v.title AS title, v.url AS url,
               v.duration_sec AS duration_sec, v.summary AS summary,
               count(s) AS segment_count
        ORDER BY v.title
        """,
        collect=False,
    )
    return {"videos": results}


@router.get("/videos/{video_id}/segments")
async def video_segments(video_id: str):
    """Return a video's segments in temporal order."""
    _require_neo4j()
    results = await execute_cypher(
        """
        MATCH (v:Video {id: $vid})-[:HAS_SEGMENT]->(s:Segment)
        OPTIONAL MATCH (s)-[:MENTIONS]->(e:Entity)
        RETURN s.id AS id, s.start_sec AS start_sec, s.end_sec AS end_sec,
               s.summary AS summary, s.on_screen_text AS on_screen_text,
               collect(DISTINCT e.name) AS entities
        ORDER BY s.start_sec
        """,
        {"vid": video_id},
        collect=False,
    )
    return {"video_id": video_id, "segments": results}


@router.post("/search")
async def search(request: SearchRequest):
    """Live multimodal search over the raw videos via TwelveLabs (Marengo)."""
    from app.twelvelabs_client import ensure_index
    from app.twelvelabs_client import search as tl_search
    try:
        index_id = await asyncio.to_thread(ensure_index)
        hits = await asyncio.to_thread(tl_search, index_id, request.query, None, "clip", request.limit)
        return {"results": hits}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TwelveLabs search failed: {e}")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _theme_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "default"


async def _generation_context(limit: int = 8) -> list[dict]:
    return await execute_cypher(
        """
        MATCH (v:Video)
        OPTIONAL MATCH (v)-[:HAS_SEGMENT]->(s:Segment)
        WITH v, s ORDER BY s.idx
        RETURN v.id AS video_id, v.title AS title, v.summary AS summary,
               collect({
                 start_sec: s.start_sec,
                 end_sec: s.end_sec,
                 summary: s.summary,
                 on_screen_text: s.on_screen_text,
                 transcript: s.transcript
               })[..6] AS sample_segments
        ORDER BY v.title
        LIMIT $limit
        """,
        {"limit": limit},
        collect=False,
    )


async def _clip_candidates(prompt: str, limit: int = 8) -> list[dict]:
    """Find Rodeo-style clip candidates with TwelveLabs, then enrich from Neo4j."""
    from app import twelvelabs_client as tl

    try:
        index_id = await asyncio.to_thread(tl.ensure_index)
        clips = await asyncio.to_thread(tl.search, index_id, prompt, None, "clip", limit)
    except Exception:
        clips = []

    if clips:
        return await execute_cypher(
            """
            UNWIND $clips AS clip
            MATCH (v:Video {id: clip.video_id})
            OPTIONAL MATCH (v)-[:HAS_SEGMENT]->(s:Segment)
            WHERE (clip.start_sec IS NULL OR s.end_sec >= clip.start_sec)
              AND (clip.end_sec IS NULL OR s.start_sec <= clip.end_sec)
            WITH clip, v, s ORDER BY s.idx
            RETURN clip.video_id AS video_id, v.title AS title, v.url AS url,
                   clip.start_sec AS start_sec, clip.end_sec AS end_sec,
                   clip.score AS score, clip.confidence AS confidence,
                   coalesce(s.summary, v.summary) AS summary,
                   s.on_screen_text AS on_screen_text,
                   s.transcript AS transcript
            LIMIT $limit
            """,
            {"clips": clips, "limit": limit},
            collect=False,
        )

    return await execute_cypher(
        """
        MATCH (v:Video)-[:HAS_SEGMENT]->(s:Segment)
        RETURN v.id AS video_id, v.title AS title, v.url AS url,
               s.start_sec AS start_sec, s.end_sec AS end_sec,
               null AS score, null AS confidence,
               s.summary AS summary, s.on_screen_text AS on_screen_text,
               s.transcript AS transcript
        ORDER BY v.title, s.idx
        LIMIT $limit
        """,
        {"limit": limit},
        collect=False,
    )


def _fallback_plan(
    prompt: str,
    theme: str,
    context: list[dict],
    clips: list[dict],
    target_duration_sec: int,
) -> dict:
    source_titles = [row.get("title") for row in context if row.get("title")]
    scenes = []
    for i, clip in enumerate(clips[:5], start=1):
        scenes.append({
            "order": i,
            "title": f"Scene {i}",
            "purpose": "Use this source moment as evidence for the story.",
            "source_video": clip.get("title"),
            "video_id": clip.get("video_id"),
            "start_sec": clip.get("start_sec"),
            "end_sec": clip.get("end_sec"),
            "voiceover": clip.get("summary") or "Show the strongest matching source moment.",
            "on_screen_text": clip.get("on_screen_text") or "",
        })
    return {
        "title": theme,
        "prompt": prompt,
        "target_duration_sec": target_duration_sec,
        "storyline": (
            f"Create a {target_duration_sec}-second rough cut for '{prompt}' using "
            f"the visual language learned from {', '.join(source_titles[:4]) or 'the local video library'}."
        ),
        "theme_dna": [
            "Use source clips as evidence, not generic stock footage.",
            "Prefer moments found by semantic video search over keyword matches.",
            "Keep the cut reviewable through source video and timecode citations.",
        ],
        "scenes": scenes,
        "do_rules": [
            "Reuse recurring entities, topics, and visual motifs from the indexed videos.",
            "Keep each scene tied to a source clip and time range.",
        ],
        "dont_rules": [
            "Do not invent unsupported claims or visuals.",
            "Do not treat the generated plan as final rendered media.",
        ],
    }


def _openai_rough_cut_plan(
    prompt: str,
    theme: str,
    context: list[dict],
    clips: list[dict],
    target_duration_sec: int,
) -> dict:
    from openai import OpenAI

    if not settings.openai_api_key:
        return _fallback_plan(prompt, theme, context, clips, target_duration_sec)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_model,
        reasoning={"effort": settings.openai_reasoning_effort},
        max_output_tokens=1200,
        text={"format": {"type": "json_object"}},
        input=[
            {
                "role": "system",
                "content": (
                    "You create Rodeo-style rough cut plans from indexed source videos. "
                    "Use only the provided source videos and clip candidates. Return JSON with "
                    "title, prompt, target_duration_sec, storyline, theme_dna array, scenes array, "
                    "do_rules array, and dont_rules array. Each scene must include order, title, "
                    "purpose, source_video, video_id, start_sec, end_sec, voiceover, on_screen_text."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "prompt": prompt,
                    "theme": theme,
                    "source_videos": context,
                    "clip_candidates": clips,
                    "target_duration_sec": target_duration_sec,
                }, default=str),
            },
        ],
    )
    try:
        return json.loads(getattr(response, "output_text", "") or "{}")
    except json.JSONDecodeError:
        return _fallback_plan(prompt, theme, context, clips, target_duration_sec)


@router.get("/generation/themes")
async def generation_themes():
    """Return reusable generation themes learned from previous local video prompts."""
    _require_neo4j()
    results = await execute_cypher(
        """
        MATCH (t:GenerationTheme)
        OPTIONAL MATCH (t)-[:BASED_ON]->(v:Video)
        OPTIONAL MATCH (t)-[:GENERATED]->(rc:RoughCut)
        RETURN t.id AS id, t.name AS name, t.prompt AS prompt,
               t.latest_rough_cut_id AS latest_rough_cut_id,
               t.created_at AS created_at, collect(DISTINCT v.title) AS source_videos,
               count(DISTINCT rc) AS rough_cut_count
        ORDER BY t.created_at DESC
        LIMIT 20
        """,
        collect=False,
    )
    return {"themes": results}


@router.post("/generate/rough-cut")
async def generate_brief(request: GenerateBriefRequest):
    """Create and persist a Rodeo-style rough cut plan."""
    _require_neo4j()
    context = await _generation_context()
    if not context:
        raise HTTPException(
            status_code=400,
            detail="No indexed videos found. Add MP4s to data/videos and run make seed first.",
        )

    theme_name = request.theme or request.prompt[:80]
    theme_key = _theme_key(theme_name)
    clips = await _clip_candidates(request.prompt)
    rough_cut = await asyncio.to_thread(
        _openai_rough_cut_plan,
        request.prompt,
        theme_name,
        context,
        clips,
        request.target_duration_sec,
    )
    theme_id = f"theme-{theme_key}"
    rough_cut_id = f"rough-cut-{_uuid.uuid4()}"
    video_ids = [row["video_id"] for row in context if row.get("video_id")]

    await execute_cypher(
        """
        MERGE (t:GenerationTheme {id: $id})
        SET t.name = $name,
            t.key = $key,
            t.prompt = $prompt,
            t.latest_rough_cut_id = $rough_cut_id,
            t.updated_at = datetime(),
            t.created_at = coalesce(t.created_at, datetime()),
            t.domain = $domain
        MERGE (rc:RoughCut {id: $rough_cut_id})
        SET rc.prompt = $prompt,
            rc.theme = $name,
            rc.plan = $plan,
            rc.created_at = datetime(),
            rc.domain = $domain
        MERGE (t)-[:GENERATED]->(rc)
        WITH t
        MATCH (v:Video)
        WHERE v.id IN $video_ids
        MERGE (t)-[:BASED_ON]->(v)
        """,
        {
            "id": theme_id,
            "name": theme_name,
            "key": theme_key,
            "prompt": request.prompt,
            "rough_cut_id": rough_cut_id,
            "plan": json.dumps(rough_cut, default=str),
            "video_ids": video_ids,
            "domain": settings.domain_id,
        },
        collect=False,
    )
    return {
        "rough_cut": {
            "id": rough_cut_id,
            **rough_cut,
            "clip_candidates": clips,
        },
        "theme": {
            "id": theme_id,
            "name": theme_name,
            "prompt": request.prompt,
            "source_videos": [row.get("title") for row in context if row.get("title")],
        }
    }


@router.post("/generate/brief")
async def generate_legacy_brief(request: GenerateBriefRequest):
    """Compatibility alias for the first UI implementation."""
    return await generate_brief(request)


@router.get("/scenarios")
async def scenarios():
    """Demo prompts for the frontend."""
    return {
        "domain": "Framewise",
        "scenarios": [
            {"name": "Explore", "prompts": [
                "What videos do we have and what are they about?",
                "Show me the graph around the rabbit",
            ]},
            {"name": "Find a moment", "prompts": [
                "Find the moment where a butterfly lands on the rabbit",
                "Where does the rabbit eat an apple?",
            ]},
            {"name": "Cross-video", "prompts": [
                "Which entities appear in more than one video?",
                "What connects the two clips to each other?",
            ]},
        ],
    }

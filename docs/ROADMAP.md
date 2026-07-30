# Framewise Roadmap

## First Cut

Goal: make the hackathon demo run locally with the sponsor stack clearly visible.

- Ingest local MP4 files from `data/videos/`.
- Use TwelveLabs for video indexing, Pegasus analysis, Marengo embeddings, and semantic video search.
- Use OpenAI for structured extraction, canonicalization, and grounded answer synthesis.
- Store videos, segments, entities, topics, and segment embeddings in Neo4j.
- Use Strands to orchestrate tools for chat, graph exploration, and search.
- Show live graph updates in the frontend when tools return Neo4j nodes.

## Demo Story

Framewise turns a video library into a living evidence graph.

1. Drop multiple videos into `data/videos/`.
2. Run `make seed`.
3. Ask: `Which entities appear in more than one video?`
4. Show the merged entity node connected to multiple videos.
5. Ask a timecoded search question and show the exact supporting segment.

## Staff-Level Upgrade Path

Use this after the first cut is stable.

- Durable ingestion jobs with idempotency, retries, and resumable state.
- Separate interactive chat latency from heavy video processing with a queue.
- Add evaluation sets for extraction quality, retrieval precision, and answer grounding.
- Add provenance: model versions, prompt versions, source timestamps, and graph write lineage.
- Add tenant isolation and domain-aware indexes for company-specific video libraries.
- Add cost controls: per-video token/model spend, caching, and batch processing.
- Add semantic and episodic memory for reusable brand rules, approved styles, and user preferences.
- Add review workflows for extracted entities, policy violations, and generated briefs.
- Optional AWS production path: S3 uploads, EventBridge/Lambda triggers, ECS/App Runner deployment, Secrets Manager, and Bedrock model support.


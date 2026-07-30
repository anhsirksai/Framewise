# Framewise

Turn every video into reusable intelligence.

Framewise takes videos from `data/videos/`, uses TwelveLabs to understand what is
shown, said, and written, uses OpenAI to structure that understanding, stores the
result as a Neo4j evidence graph, and exposes it through a Strands-powered chat UI
with live graph visualization.

The first cut intentionally avoids AWS hosting, S3, and Lambda. AWS usage is
through Strands as the agent orchestration layer. Local MP4 files are enough for
the hackathon demo.

## What It Demonstrates

```
Video files
  -> TwelveLabs index/analyze/embed
  -> OpenAI structured extraction + reasoning
  -> Neo4j evidence graph + vector index
  -> Strands agent tool calls
  -> Next.js chat + live graph view
```

Core demo question:

> Which entities appear in more than one video?

The intended visual moment: two different videos share one canonical entity node,
so the graph grows richer instead of duplicating the same concept.

## Sponsor Tech Framing

### TwelveLabs - Video Is Evidence

- Indexing: upload MP4s from `data/videos/` into a searchable index.
- Pegasus analyze: rich, time-coded descriptions of what is shown, said, and written.
- Marengo embed/search: multimodal semantic search over video content.
- Hackathon angle: we do not summarize transcripts alone. We understand visual and audio context, then find moments by meaning.

### OpenAI - Structure And Reason

- Structured extraction: turns Pegasus prose into typed segments, entities, topics, and validated JSON.
- Canonicalization: merges names like "bunnies" and "Rabbit" into one graph entity.
- Agent reasoning: chooses tools, synthesizes answers, and cites timecodes.
- Hackathon angle: every answer is grounded in tool results, not invented from chat history.

### Neo4j - The Context Graph

- Graph model: `Video -> Segment -> Entity/Topic`, with temporal `NEXT` links.
- Cross-video merge: the same entity in multiple videos becomes one hub node.
- Vector index: segment embeddings support "find the moment" semantic search.
- NVL visualization: the UI graph panel reacts to agent tool calls.
- Hackathon angle: the graph compounds over time as more videos are added.

### Strands - Agent Orchestration

- Tool wiring: Strands tools expose Neo4j and TwelveLabs capabilities to the agent.
- Streaming: `agent.stream_async` sends events to the frontend over SSE.
- Model abstraction: the first cut uses OpenAI; later it can swap to Bedrock-backed models.
- Hackathon angle: tools are first-class, and the agent controls retrieval instead of guessing.

### AWS - First-Cut Scope

This first cut does not use S3, Lambda, ECS, App Runner, or CloudFront.

For the hackathon story, Strands is the AWS layer. Production AWS additions can
come later:

- S3 for uploaded video storage.
- Lambda or EventBridge for ingestion triggers.
- ECS/Fargate or App Runner for backend/frontend deployment.
- Secrets Manager for API keys.
- Bedrock as an alternate Strands model backend.

## Local Video Workflow

Put MP4 files here:

```bash
data/videos/
```

Then run:

```bash
make seed
```

With no arguments, ingestion reads every `*.mp4` in `data/videos/`. If that
folder is empty, it falls back to `SAMPLE_VIDEO_URLS` from `.env`.

To download permitted source videos into that folder:

```bash
make download-videos URLS="https://example.com/your-video-1 https://example.com/your-video-2"
make seed
```

Use this only for videos you own, have permission to use, or are licensed for
download/reuse.

## Quick Start

Prerequisites:

- Python 3.10 to 3.13 with `uv`
- Node.js 18+
- Neo4j local Docker or Neo4j Aura
- OpenAI API key
- TwelveLabs API key

Setup:

```bash
cd /Users/sai/Projects/Framewise-HackerSquad
cp .env.example .env
```

Fill in:

```bash
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=
OPENAI_API_KEY=
TWELVE_LABS_API_KEY=
```

## Move Neo4j Aura Credentials To AWS Secrets Manager

The backend can load Neo4j Aura credentials from AWS Secrets Manager instead of
reading them directly from runtime environment variables.

First, keep the current Aura values in `.env` locally:

```bash
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=
NEO4J_DATABASE=neo4j
AWS_REGION=us-east-1
```

Then sync only those Neo4j values into AWS:

```bash
make sync-neo4j-secret SECRET_NAME=framewise/neo4j-aura AWS_REGION=us-east-1
```

Enable cloud loading at runtime:

```bash
AWS_SECRETS_MANAGER_SECRET_NAME=framewise/neo4j-aura
AWS_REGION=us-east-1
```

The secret JSON contains:

```json
{
  "NEO4J_URI": "...",
  "NEO4J_USERNAME": "...",
  "NEO4J_PASSWORD": "...",
  "NEO4J_DATABASE": "neo4j"
}
```

The app does not print the secret values. If AWS loading fails, it falls back to
the local `.env` values so local development still works.

Install and run:

```bash
make install
make docker-up      # optional if you are not using Aura
make seed           # ingests local data/videos/*.mp4
make start
```

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health

## Useful Demo Prompts

- What videos do we have and what are they about?
- Find the moment where a character appears.
- Which entities appear in more than one video?
- Show me the graph around the shared entity.
- What connects these clips to each other?

## Rodeo-Style Rough Cut Generation

The right-side Studio panel has a `Generate Rough Cut` button. It follows the
Rodeo product pattern: describe the story you want, search indexed video moments
by meaning, assemble those moments into scenes, and store the reusable theme in
Neo4j.

Backend endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/generation/themes` | List saved reusable themes |
| `POST /api/generate/rough-cut` | Create a rough cut plan from a prompt, theme, and local indexed videos |
| `POST /api/generate/brief` | Compatibility alias for rough-cut generation |

This does not render a final MP4 yet. It creates the rough cut plan, cited source
clips, theme DNA, and do/don't rules. The next production step is exporting that
plan to a real editor format such as EDL, OTIO, or XML.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       INGESTION PIPELINE                      │
├───────────────────────────────────────────────────────────────┤
│ Video -> TwelveLabs -> OpenAI -> TwelveLabs -> Neo4j          │
│          index/analyze  structure  embed       persist        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                         CHAT RUNTIME                          │
├───────────────────────────────────────────────────────────────┤
│ User -> FastAPI -> Strands -> OpenAI reasoning                │
│                         │                                     │
│                         ├-> TwelveLabs embed/search           │
│                         ├-> Neo4j graph + vector search       │
│                         └-> Frontend graph viz with NVL       │
└───────────────────────────────────────────────────────────────┘
```

## Graph Model

```cypher
(:Video)-[:HAS_SEGMENT]->(:Segment {embedding})
(:Segment)-[:NEXT]->(:Segment)
(:Segment)-[:MENTIONS]->(:Entity)
(:Segment)-[:ABOUT]->(:Topic)
```

`Entity` and `Topic` nodes are keyed by normalized names. That is what lets one
entity span multiple videos and become the visible hub in the graph.

## Main Commands

| Command | Purpose |
|---|---|
| `make install` | Install backend and frontend dependencies |
| `make docker-up` | Start local Neo4j |
| `make download-videos URLS="..."` | Download permitted source videos into `data/videos/` |
| `make sync-neo4j-secret SECRET_NAME=... AWS_REGION=...` | Store Neo4j Aura credentials in AWS Secrets Manager |
| `make seed` | Ingest local videos from `data/videos/` |
| `make start` | Run backend and frontend |
| `make schema` | Apply Neo4j constraints and indexes |
| `make test` | Run backend tests, frontend type-check, and e2e discovery |
| `make reset` | Delete all Neo4j data in the configured database |

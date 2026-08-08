# Framewise Ops Runbook

A self-sufficient guide to running, deploying, debugging, and recovering this project
**without any AI assistant**. Everything here is grounded in the actual files in this repo.

---

## 1. The system at a glance

```
Browser
  │
  ▼
Frontend  — Next.js 15 + Chakra + Neo4j NVL   (port 3000)
  │  calls  NEXT_PUBLIC_API_URL  (default http://localhost:8000/api)
  ▼
Backend   — FastAPI + Strands agent           (port 8000)
  │  ├── Neo4j (bolt 7687)          — evidence graph (Video/Segment/Entity/Topic)
  │  ├── TwelveLabs API             — video indexing (Marengo) + analysis (Pegasus)
  │  └── OpenAI or Claude           — reasoning + structured extraction (LLM_PROVIDER toggle)
  ▼
Neo4j     — docker container or Aura cloud    (ports 7474 HTTP UI, 7687 bolt)
```

Key files:

| Piece | Where |
|---|---|
| Backend app entry | `backend/app/main.py` (lifespan connects Neo4j, `/health` endpoint) |
| All API routes | `backend/app/routes.py` (chat, search, ingest, videos, generate, cypher) |
| Settings / env parsing | `backend/app/config.py` (pydantic `Settings`, reads repo-root `.env`) |
| LLM provider switch | `backend/app/llm_client.py` (`LLM_PROVIDER=openai\|anthropic`) |
| Neo4j driver + queries | `backend/app/context_graph_client.py` |
| Vector search | `backend/app/vector_client.py` |
| TwelveLabs calls | `backend/app/twelvelabs_client.py` |
| Agent + tools | `backend/app/agent.py` |
| Ingestion pipeline | `backend/scripts/ingest.py` (also `app/ingestion.py` for upload route) |
| Frontend API base URL | `frontend/lib/config.ts` (`NEXT_PUBLIC_API_URL`) |
| Local Neo4j | `docker-compose.yml` |
| Full prod stack (docker) | `docker-compose.prod.yml` + `Dockerfile.backend` / `Dockerfile.frontend` |
| Fly.io deploy | `backend/fly.toml` (app name `framewise-backend`) |
| Task shortcuts | `Makefile` (start, seed, schema, reset, test-connection, docker-*) |

---

## 2. Configuration (.env)

All config lives in the **repo-root `.env`** (copy from `.env.example`). The backend reads it
via pydantic-settings; the Makefile also `include`s and exports it.

The values that matter most:

| Variable | What breaks if wrong |
|---|---|
| `NEO4J_URI` | Backend starts in **degraded mode** (health shows `"neo4j": false`). Local docker: `neo4j://localhost:7687`. Aura: `neo4j+s://<dbid>.databases.neo4j.io`. Inside docker-compose prod the backend must use `bolt://neo4j:7687` (service name, not localhost). |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | Auth errors on connect. Docker compose sets `neo4j/password` by default. Aura credentials are in `Neo4j-6f5cebfe-Created-2026-08-08.txt` (repo root — don't commit new ones). |
| `LLM_PROVIDER` | `openai` or `anthropic`. Chooses which API key/model is used for chat reasoning and ingestion extraction. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Chat/generation endpoints return errors or fall back; ingestion structuring fails. Only the key for the **active** provider is needed. |
| `TWELVE_LABS_API_KEY` | `make seed` / video upload fails at the indexing step. |
| `TL_INDEX_ID` / `TL_INDEX_NAME` | Blank ID = create/find index by name (`framewise`). A stale ID from a deleted index causes 404s from TwelveLabs. |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | If set, Neo4j credentials are loaded from AWS Secrets Manager **instead of** the .env values — a common source of "I changed .env but nothing happened". Unset it to use local values. |
| `BACKEND_PORT` / `FRONTEND_PORT` | Defaults 8000 / 3000. |
| `CORS_ORIGINS` | Browser gets CORS errors calling the API. Must include the frontend origin. |

> **Gotcha:** `NEXT_PUBLIC_API_URL` is baked into the frontend **at build time**
> (Next.js public env). Changing it requires rebuilding/restarting the frontend,
> not just editing `.env`.

---

## 3. Bring everything UP (local dev)

```bash
# 0. One-time install
make install                # backend: uv sync, frontend: npm install

# 1. Start Neo4j (docker)
make docker-up              # = docker compose up -d  (neo4j only)
# UI at http://localhost:7474  (neo4j / password)

# 2. Verify the DB is reachable
make test-connection

# 3. Apply schema (constraints + vector index) — safe to re-run
make schema

# 4. (Optional) ingest demo videos from data/videos/*.mp4 or SAMPLE_VIDEO_URLS
make seed

# 5. Run backend + frontend together
make start                  # backend :8000 (uvicorn --reload), frontend :3000
```

Or individually: `make dev-backend` / `make dev-frontend`.

Smoke test:

```bash
curl -s http://localhost:8000/health          # {"status":"ok","neo4j":true,...}
curl -s http://localhost:8000/api/videos      # list of ingested videos
open http://localhost:3000                    # the portal
```

## 4. Bring everything DOWN

```bash
# Dev processes: Ctrl-C the `make start` shell (it traps EXIT and kills both).
# If orphaned processes remain:
lsof -ti :8000 | xargs kill        # backend
lsof -ti :3000 | xargs kill        # frontend

# Neo4j container (data survives in the neo4j_data volume):
make docker-down

# Nuke Neo4j data too (destructive):
docker compose down -v
```

## 5. Restart from a bad state (full reset)

```bash
make docker-down && make docker-up   # restart Neo4j
make test-connection
make reset                            # DANGER: deletes ALL graph data (MATCH (n) DETACH DELETE n)
make schema
make seed                             # re-ingest
make start
```

`make clean` additionally removes `backend/.venv`, `frontend/.next`, `node_modules`
(follow with `make install`).

---

## 6. Production hosting

### Option A — Docker Compose (single box)

```bash
# Up (builds neo4j + backend + frontend):
make docker-build
make docker-prod-up        # = docker compose -f docker-compose.prod.yml up -d

# Down:
make docker-prod-down

# Status / logs:
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f neo4j

# Restart one service after a code change:
docker compose -f docker-compose.prod.yml up -d --build backend
```

Notes:
- Backend waits for the Neo4j healthcheck before starting (`depends_on: condition: service_healthy`).
- Inside compose, the backend reaches Neo4j at `bolt://neo4j:7687` (already the default in the file).
- `NEXT_PUBLIC_API_URL` is passed as a **build arg** to the frontend image — if you change the backend port/host, rebuild the frontend image.

### Option B — Fly.io (backend only)

Config: `backend/fly.toml`, app name `framewise-backend`, region `iad`,
`LLM_PROVIDER=anthropic` baked in, health check on `/health`, **scales to zero** when idle.

```bash
cd backend

# One-time secrets (anything not in [env] of fly.toml):
fly secrets set NEO4J_URI='neo4j+s://<dbid>.databases.neo4j.io' \
                NEO4J_USERNAME=neo4j NEO4J_PASSWORD='...' \
                ANTHROPIC_API_KEY='...' TWELVE_LABS_API_KEY='...'

fly deploy                     # build + release
fly status                     # machine state
fly logs                       # live logs — first place to look
fly ssh console                # shell inside the machine
fly secrets list               # names only (values hidden)

# "Stop the portal" / bring down:
fly scale count 0              # stop all machines
fly scale count 1              # bring back up
# (auto_stop/auto_start is on, so idle machines stop themselves and
#  wake on the next request — the first request after idle is slow.)
```

Fly pairs with **Neo4j Aura** for the database (local docker Neo4j is not reachable from Fly).
Aura instances also pause when idle on the free tier — resume them from the Aura console
if connections suddenly fail.

---

## 7. "The backend is not working" — diagnosis flowchart

**Step 1 — is the process up?**
```bash
curl -s http://localhost:8000/health
```
- **Connection refused** → backend isn't running. Start it in the foreground to see the real error:
  `cd backend && uv run uvicorn app.main:app --port 8000 --loop asyncio`
  Typical startup crashes: missing dependency (`uv sync`), bad import after an edit, port already in use (`lsof -i :8000`).
- **`{"status":"degraded","neo4j":false}`** → backend is fine, **Neo4j is the problem** → Step 2.
- **`{"status":"ok","neo4j":true}`** → backend + DB are fine; the problem is a specific endpoint (→ Step 3) or the frontend (→ Step 4).

**Step 2 — Neo4j problems**
```bash
docker ps | grep neo4j          # is the container running?
docker logs $(docker ps -q -f ancestor=neo4j:5.26.0) --tail 50
make test-connection            # tries connect_neo4j() with your .env values
```
- Container not running → `make docker-up`.
- Auth failure → password mismatch between `.env` and `NEO4J_AUTH` in docker-compose (default `neo4j/password`). If you changed the password after first boot, the old one is persisted in the `neo4j_data` volume — either use the original password or `docker compose down -v` to wipe.
- Using Aura → check the instance isn't **paused** in the Aura console; verify the `neo4j+s://` URI.
- Check whether `AWS_SECRETS_MANAGER_SECRET_NAME` is set in `.env` — if so, credentials come from AWS, not from the file you're editing (`backend/app/config.py`).
- The backend connects only **at startup** (`lifespan` in `main.py`) — after fixing Neo4j, **restart the backend**.

**Step 3 — a specific endpoint fails**

Read the uvicorn console/`fly logs` traceback first, then go to the code:

| Symptom | Look at |
|---|---|
| `/api/chat` errors or empty answers | `backend/app/agent.py` (agent + tools), `backend/app/llm_client.py` (provider call). Check the active provider's API key: `LLM_PROVIDER` in `.env` vs which key is set. |
| Structured extraction / JSON parse errors during ingest | `backend/app/llm_client.py` (`parse_structured`, `generate_json`), model names in `config.py` (`anthropic_model` / `openai_model`). |
| `/api/search` returns nothing | Vector index missing → `make schema`; embeddings missing → re-run `make seed`; `backend/app/vector_client.py`. |
| `/api/ingest/upload` or `make seed` fails | `backend/scripts/ingest.py` + `backend/app/twelvelabs_client.py`. Verify `TWELVE_LABS_API_KEY`; a stale `TL_INDEX_ID` gives 404s — blank it to recreate by name. TwelveLabs indexing is slow: poll `/api/ingest/jobs`. |
| `/api/cypher` or graph viz errors | `backend/app/context_graph_client.py`; try the same query in the Neo4j browser (`:7474`). |
| `/api/generate/rough-cut` fails | `backend/app/video_renderer.py`; output goes to `data/generated/` (served at `/artifacts`). Needs ffmpeg/moviepy deps inside the environment. |
| `/api/videos` empty | Nothing ingested yet → `make seed`, or wrong `DOMAIN_ID` (data is domain-scoped; compare `.env` `DOMAIN_ID` with what was used at ingest time). |

Useful direct probes:

```bash
curl -s http://localhost:8000/api/videos | head -c 500
curl -s -X POST http://localhost:8000/api/search -H 'content-type: application/json' \
     -d '{"query":"test"}' | head -c 500
curl -s -X POST http://localhost:8000/api/cypher -H 'content-type: application/json' \
     -d '{"query":"MATCH (n) RETURN count(n) AS n"}'
```

**Step 4 — frontend problems**
- Blank page / network errors in browser devtools → is the API base right? `frontend/lib/config.ts` uses `NEXT_PUBLIC_API_URL` (build-time). In dev, `make dev-frontend` sets it to `http://localhost:8000/api` automatically.
- **CORS errors** in the console → backend `CORS_ORIGINS` must include the frontend origin (`backend/app/main.py`); restart the backend after changing it.
- Stale build weirdness → `rm -rf frontend/.next && make dev-frontend`.
- Type errors on build → `cd frontend && npm exec -- tsc --noEmit`.

---

## 8. Logs — where to look

| Environment | Command |
|---|---|
| Local dev backend | The `make start` / uvicorn terminal (tracebacks print here) |
| Local dev frontend | Same terminal (Next.js output) + browser devtools console/network |
| Docker prod | `docker compose -f docker-compose.prod.yml logs -f backend` (or `neo4j`, `frontend`) |
| Fly.io | `fly logs` (from `backend/`), or `fly ssh console` to poke around |
| Neo4j (docker) | `docker logs <container>`; also the `neo4j_logs` volume |
| Neo4j Aura | Aura console → instance → logs/metrics |

---

## 9. Data & graph maintenance

```bash
make schema            # (re)apply constraints + vector index — idempotent
make seed              # ingest data/videos/*.mp4, or SAMPLE_VIDEO_URLS, or VIDEOS="url ..."
make reset             # WIPE the graph (all nodes/relationships)
make download-videos URLS="..."   # fetch demo clips into data/videos/
```

Inspect the graph directly at `http://localhost:7474`:

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(*) ORDER BY count(*) DESC;
MATCH (v:Video)-[:HAS_SEGMENT]->(s:Segment) RETURN v.id, count(s);
MATCH (s:Segment)-[:MENTIONS]->(e:Entity) RETURN e.name, e.type, count(s) ORDER BY count(s) DESC LIMIT 20;
```

Re-ingesting the same video is safe: `ingest.py` MERGEs the `Video` node, deletes its old
segments, and recreates them (entities/topics are merged by canonical key across videos).

---

## 10. Tests & sanity checks before deploying

```bash
make test          # backend pytest + frontend tsc + playwright --list
make lint          # ruff + eslint
make test-e2e      # full Playwright run (needs backend+frontend running)
```

## 11. Quick reference card

| I want to… | Do this |
|---|---|
| Start everything (dev) | `make docker-up && make start` |
| Stop everything (dev) | Ctrl-C, then `make docker-down` |
| Start everything (prod, docker) | `make docker-build && make docker-prod-up` |
| Stop prod stack | `make docker-prod-down` |
| Deploy backend to Fly | `cd backend && fly deploy` |
| Take Fly backend offline | `fly scale count 0` |
| Bring Fly backend back | `fly scale count 1` (or just hit the URL — auto-start) |
| Check health | `curl localhost:8000/health` / `curl https://framewise-backend.fly.dev/health` |
| Wipe + rebuild data | `make reset && make schema && make seed` |
| See why chat is broken | uvicorn logs → `app/agent.py`, `app/llm_client.py`, check `LLM_PROVIDER` + key |
| See why DB is broken | `make test-connection` → docker logs / Aura console → restart backend |

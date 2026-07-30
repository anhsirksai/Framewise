# Framewise Application

-include .env
export

.PHONY: start dev dev-backend dev-frontend install schema seed download-videos sync-neo4j-secret reset test-connection clean test test-e2e lint docker-build docker-prod-up docker-prod-down

# Start both backend and frontend
start:
	@echo "Starting Framewise..."
	@trap 'kill 0' EXIT; \
		$(MAKE) dev-backend & \
		$(MAKE) dev-frontend & \
		wait

dev: start

# Backend
dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port $${BACKEND_PORT:-8000} --loop asyncio

install-backend:
	cd backend && uv sync --extra dev

# Frontend
dev-frontend:
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:$${BACKEND_PORT:-8000}/api npm run dev -- --port $${FRONTEND_PORT:-3000}

install-frontend:
	cd frontend && npm install

# Install everything
install: install-backend install-frontend

# Apply Neo4j schema constraints and indexes only (no data)
schema:
	cd backend && uv run python scripts/ingest.py --schema-only

# Ingest videos (SAMPLE_VIDEO_URLS from .env, or pass URLs: make seed VIDEOS="url1 url2")
seed:
	cd backend && uv run python scripts/ingest.py $(VIDEOS)

# Download permitted source videos into data/videos using yt-dlp.
# Usage: make download-videos URLS="https://example.com/video1 https://example.com/video2"
download-videos:
	cd backend && uv run --with yt-dlp python scripts/download_videos.py $(URLS)

# Move local Neo4j Aura connection settings from .env into AWS Secrets Manager.
# Usage: make sync-neo4j-secret SECRET_NAME=framewise/neo4j-aura AWS_REGION=us-east-1
sync-neo4j-secret:
	cd backend && uv run python scripts/sync_neo4j_secret.py --name $${SECRET_NAME:-framewise/neo4j-aura} --region $${AWS_REGION:-$${AWS_DEFAULT_REGION:-us-east-1}}

# Reset Neo4j data (drop and recreate)
reset:
	cd backend && uv run python -c "from app.context_graph_client import reset_database; import asyncio; asyncio.run(reset_database())"

# Test Neo4j connection
test-connection:
	@cd backend && uv run python -c "import asyncio; from app.context_graph_client import connect_neo4j; asyncio.run(connect_neo4j()); print('Neo4j connection successful')" \
		|| echo "Connection failed. Check NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env"

# Docker Neo4j
docker-up:
	docker compose up -d

docker-down:
	docker compose down




# Test
test:
	cd backend && uv run --frozen --extra dev python -m pytest tests/ -v
	cd frontend && npm exec -- tsc --noEmit --incremental false
	cd frontend && npm run test:e2e -- --list --reporter=list

# End-to-end tests (requires backend + frontend running, and Playwright installed)
test-e2e:
	cd frontend && npm run test:e2e

# Lint
lint:
	cd backend && uv run ruff check app/ 2>/dev/null || echo "Install ruff for linting: uv pip install ruff"
	cd frontend && npm run lint 2>/dev/null || echo "No frontend lint configured"

# Docker production deployment
docker-build:
	docker compose -f docker-compose.prod.yml build

docker-prod-up:
	docker compose -f docker-compose.prod.yml up -d

docker-prod-down:
	docker compose -f docker-compose.prod.yml down

# Clean build artifacts
clean:
	rm -rf backend/__pycache__ backend/.venv
	rm -rf frontend/.next frontend/node_modules

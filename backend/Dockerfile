# Framewise backend — FastAPI + Strands + TwelveLabs + Neo4j driver
FROM python:3.12-slim

WORKDIR /app

# uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependency layer first for build caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]

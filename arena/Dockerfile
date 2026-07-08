# syntax=docker/dockerfile:1.7
# SNHP Evolution Arena — the live sim + renderer, deployed as its own Fly app.
# Serves the renderer SPA at / and the sim over WebSocket at /arena/ws, same-origin,
# via `uvicorn arena.api:app`.
#
# Build context = REPO ROOT (needs gametheory/, snhp/, arena/):
#   fly deploy -c arena/fly.toml            (from the repo root)
#
# Installs `.[prod,arena]` — the `arena` extra adds `websockets` (FastAPI/uvicorn
# ship without a WS protocol lib).

# ─── builder ────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY gametheory/ ./gametheory/
COPY snhp/ ./snhp/
COPY arena/ ./arena/

RUN python -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install -e ".[prod,arena]"

# ─── runtime ────────────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    ARENA_DATA_DIR="/data"

RUN groupadd -r arena && useradd -r -g arena -d /app -s /sbin/nologin arena
WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /build/gametheory ./gametheory
COPY --from=builder /build/snhp ./snhp
COPY --from=builder /build/arena ./arena
COPY --from=builder /build/pyproject.toml ./pyproject.toml

RUN mkdir -p /data && chown -R arena:arena /app /data
USER arena

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["sh", "-c", "uvicorn arena.api:app --host 0.0.0.0 --port ${PORT:-8080}"]

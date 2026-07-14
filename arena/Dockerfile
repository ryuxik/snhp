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
# The general offer-graph engine: core/js is served at /core/js for the funnel
# pages (hook/yourmenu); core/ python backs the block-live adapters.
COPY core/ ./core/
# The LIVE twin-street experiment (BLOCK_LIVE=1): block/ + the vertical sims its
# venue adapters import (venues.py/bundles.py: bakeshop boba buyer fashion slots
# vend vintage).
COPY block/ ./block/
COPY bakeshop/ ./bakeshop/
COPY boba/ ./boba/
COPY buyer/ ./buyer/
COPY fashion/ ./fashion/
COPY slots/ ./slots/
COPY vend/ ./vend/
COPY vintage/ ./vintage/

RUN python -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install -e ".[prod,arena]"

# ─── runtime ────────────────────────────────────────────────────────────────
FROM python:3.13-slim

# The running code's git SHA, stamped on the block-live provenance badge (the
# container has no .git). Pass at deploy: fly deploy --build-arg GIT_SHA=$(git rev-parse --short HEAD)
ARG GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    ARENA_DATA_DIR="/data" \
    SOURCE_VERSION="${GIT_SHA}"

RUN groupadd -r arena && useradd -r -g arena -d /app -s /sbin/nologin arena
WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /build/gametheory ./gametheory
COPY --from=builder /build/snhp ./snhp
COPY --from=builder /build/arena ./arena
COPY --from=builder /build/core ./core
COPY --from=builder /build/block ./block
COPY --from=builder /build/bakeshop ./bakeshop
COPY --from=builder /build/boba ./boba
COPY --from=builder /build/buyer ./buyer
COPY --from=builder /build/fashion ./fashion
COPY --from=builder /build/slots ./slots
COPY --from=builder /build/vend ./vend
COPY --from=builder /build/vintage ./vintage
COPY --from=builder /build/pyproject.toml ./pyproject.toml

RUN mkdir -p /data && chown -R arena:arena /app /data
USER arena

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["sh", "-c", "uvicorn arena.api:app --host 0.0.0.0 --port ${PORT:-8080}"]

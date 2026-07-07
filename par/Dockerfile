# syntax=docker/dockerfile:1.7
# PAR — the game (SPA + API), deployed as its own Fly app. Serves the SPA at / and the API
# at /par/*, same-origin, via `uvicorn par.api:app`.
#
# Build context = REPO ROOT (the image needs gametheory/ and par/):
#   fly deploy -c par/fly.toml            (from the repo root)
#
# Mirrors the proven root Dockerfile: install `.[prod]` from pyproject into a venv
# (includes psycopg2-binary for the DATABASE_URL path — requirements.txt does NOT).

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
COPY par/ ./par/

RUN python -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install -e ".[prod]"

# ─── runtime ────────────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN groupadd -r par && useradd -r -g par -d /app -s /sbin/nologin par
WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /build/gametheory ./gametheory
COPY --from=builder /build/snhp ./snhp
COPY --from=builder /build/par ./par
COPY --from=builder /build/pyproject.toml ./pyproject.toml

RUN chown -R par:par /app
USER par

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["sh", "-c", "uvicorn par.api:app --host 0.0.0.0 --port ${PORT:-8080}"]

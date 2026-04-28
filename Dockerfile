# syntax=docker/dockerfile:1.7
# Production image for the SNHP toolkit's HTTP server (api.snhp.dev).
# Multi-stage to keep the runtime image small.

# ─── builder ────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg2-binary, numba, cryptography, and litellm all ship wheels — no
# system build tools needed beyond what slim already has.
WORKDIR /build
COPY pyproject.toml requirements.txt README.md ./
COPY gametheory/ ./gametheory/
COPY snhp/ ./snhp/

# Install with the [prod] extras into a venv so we can copy a clean tree
# into the final stage.
RUN python -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install -e ".[prod]"

# ─── runtime ────────────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

# Non-root user
RUN groupadd -r snhp && useradd -r -g snhp -d /app -s /sbin/nologin snhp
WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /build/gametheory ./gametheory
COPY --from=builder /build/snhp ./snhp
COPY --from=builder /build/pyproject.toml ./pyproject.toml
COPY --from=builder /build/README.md ./README.md

RUN chown -R snhp:snhp /app
USER snhp

# Fly sets $PORT (typically 8080); _http_entry honors it.
EXPOSE 8080

# Healthcheck hits /health which the FastAPI app already exposes.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["gametheory-http"]

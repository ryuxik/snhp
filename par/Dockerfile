# syntax=docker/dockerfile:1.7
# PAR — the game (SPA + API), deployed as its own Fly app (par.game).
# Serves the SPA at / and the API at /par/*, same-origin, via `uvicorn par.api:app`.
#
# Build context = REPO ROOT (the image needs both gametheory/ and par/):
#   docker build -f par/Dockerfile -t par .
#
# Reuses the repo's requirements.txt for correctness. To slim the image, derive a
# par-only requirements (fastapi, uvicorn, pydantic, numpy, scipy) once verified.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m venv /venv \
 && /venv/bin/pip install --upgrade pip \
 && /venv/bin/pip install -r requirements.txt
ENV PATH="/venv/bin:$PATH"

# the engine + the game (the StaticFiles mount serves ./par/web)
COPY gametheory/ ./gametheory/
COPY par/ ./par/

RUN groupadd -r par && useradd -r -g par -d /app -s /sbin/nologin par \
 && chown -R par:par /app
USER par

EXPOSE 8080

# Fly forwards to $PORT (8080); uvicorn binds the same or boots loop forever.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["sh", "-c", "uvicorn par.api:app --host 0.0.0.0 --port ${PORT:-8080}"]

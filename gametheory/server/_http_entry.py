"""Console-script entry point for `gametheory-http` (uvicorn).

Honors $PORT (Fly.io / Heroku-style) and $HOST. Falls back to 0.0.0.0:8000
for local development. Workers default to 1 because the SNHP particle
filter and Bayesian inference can carry per-process state we'd rather
not duplicate across worker boots.
"""
from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    log_level = os.environ.get("LOG_LEVEL", "info")
    uvicorn.run(
        "gametheory.server.http:app",
        host=host, port=port, log_level=log_level,
    )

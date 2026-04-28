"""Console-script entry point for `gametheory-http` (uvicorn)."""
from __future__ import annotations


def main() -> None:
    import uvicorn
    uvicorn.run(
        "gametheory.server.http:app",
        host="0.0.0.0", port=8000, log_level="info",
    )

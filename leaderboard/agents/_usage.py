"""
Append-only usage tracker for the LLM agents.

Each Gemini API call records one JSONL line with token counts + latency.
Multiple worker processes write concurrently — POSIX append-mode writes
shorter than PIPE_BUF (4KB on macOS) are atomic, so no lock is needed
for our small line size.

Schema (one line per call):
  {ts, pid, agent, model, prompt_tokens, candidates_tokens,
   thoughts_tokens, total_tokens, latency_ms}

Use `python -m leaderboard.usage` to print a running total against the
calibrated PRICING table.

Set `LEADERBOARD_USAGE_LOG` env var to override the path.
"""
from __future__ import annotations

import json
import os
import os.path as _op
import time
from typing import Optional


_DEFAULT_LOG = _op.join(
    _op.dirname(_op.dirname(_op.abspath(__file__))),
    "results", "usage.jsonl",
)


def _log_path() -> str:
    return os.environ.get("LEADERBOARD_USAGE_LOG", _DEFAULT_LOG)


_LOG_DIR_ENSURED = False


def _ensure_log_dir() -> None:
    global _LOG_DIR_ENSURED
    if _LOG_DIR_ENSURED:
        return
    os.makedirs(_op.dirname(_log_path()), exist_ok=True)
    _LOG_DIR_ENSURED = True


def record_call(
    *,
    agent: str,
    model: str,
    usage_metadata,
    latency_ms: float,
) -> None:
    """Append a single line to the usage log. Best-effort — any I/O error
    is swallowed; we never want telemetry to break the negotiation."""
    try:
        _ensure_log_dir()
        line = {
            "ts": time.time(),
            "pid": os.getpid(),
            "agent": agent,
            "model": model,
            "prompt_tokens": _safe_int(getattr(usage_metadata, "prompt_token_count", None)),
            "candidates_tokens": _safe_int(getattr(usage_metadata, "candidates_token_count", None)),
            "thoughts_tokens": _safe_int(getattr(usage_metadata, "thoughts_token_count", None)),
            "total_tokens": _safe_int(getattr(usage_metadata, "total_token_count", None)),
            "latency_ms": round(float(latency_ms), 1),
        }
        # Single-write append — atomic for <PIPE_BUF on POSIX, race-free
        # across workers.
        with open(_log_path(), "a") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
    except Exception:
        # Never let a tracking failure escape into the negotiation.
        pass


def record_failure(*, agent: str, model: str, error: str,
                    attempt: Optional[int] = None) -> None:
    """Append a failure marker — useful for measuring fallback rate."""
    try:
        _ensure_log_dir()
        line = {
            "ts": time.time(),
            "pid": os.getpid(),
            "agent": agent,
            "model": model,
            "error": error[:200],
        }
        if attempt is not None:
            line["attempt"] = attempt
        with open(_log_path(), "a") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
    except Exception:
        pass


def record_retry(*, agent: str, model: str, attempt: int, sleep_s: float) -> None:
    """Append a retry marker (separate from final failure)."""
    try:
        _ensure_log_dir()
        line = {
            "ts": time.time(),
            "pid": os.getpid(),
            "agent": agent,
            "model": model,
            "retry_attempt": attempt,
            "sleep_s": round(sleep_s, 2),
        }
        with open(_log_path(), "a") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

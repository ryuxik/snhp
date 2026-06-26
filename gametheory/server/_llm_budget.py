"""
LLM cost guard for the public dispute tool.

Two limits protect us from a runaway prompt bill when the tool is shared
publicly:

  1. A hard DAILY SPEND CAP (default $5, env SNHP_DAILY_LLM_USD). Every
     LLM-backed call books a conservative cost estimate; once the day's
     estimate crosses the cap, further LLM calls are refused until UTC
     midnight. The zero-cost synthetic demo never calls this, so it keeps
     working at capacity.
  2. A light PER-IP HOURLY CAP (default 40, env SNHP_LLM_PER_IP_HOURLY) so a
     single abuser can't eat the whole daily budget in one script.

The daily counter persists to a small JSON file so it survives restarts
within a day. Single-instance assumption (fine for one Fly machine); the
daily cap is the hard guarantee regardless — worst case exposure is the
cap, per restart.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from gametheory.server.dispute_analytics import data_dir as _data_dir

def _usage_file() -> str:
    return os.path.join(_data_dir(), ".daily_llm_usage.json")

_DAILY_USD_CAP = float(os.environ.get("SNHP_DAILY_LLM_USD", "5.0"))
# Conservative per-call estimate (over-estimating trips the cap earlier — the
# safe direction). A Haiku extract/coach/parse call is well under this.
_EST_USD_PER_CALL = float(os.environ.get("SNHP_LLM_EST_USD_PER_CALL", "0.004"))
_PER_IP_HOURLY_CAP = int(os.environ.get("SNHP_LLM_PER_IP_HOURLY", "40"))

# In-memory per-IP sliding window (resets on restart — bounds a single burst).
_ip_hits: dict[str, list[float]] = {}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_usage() -> dict:
    try:
        with open(_usage_file()) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if data.get("date") != _today():
        return {"date": _today(), "calls": 0, "est_usd": 0.0}
    return data


def _save_usage(data: dict) -> None:
    path = _usage_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _prune_ip(ip: str, now: float) -> list[float]:
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
    _ip_hits[ip] = hits
    return hits


def consume(ip: str | None) -> tuple[bool, str]:
    """Book one LLM call against the budgets. Returns (allowed, reason).

    When not allowed, `reason` is a user-facing message. Call this BEFORE
    making the LLM request; if it returns False, refuse with HTTP 429.
    """
    now = time.time()
    if ip:
        hits = _prune_ip(ip, now)
        if len(hits) >= _PER_IP_HOURLY_CAP:
            return False, ("You've hit the hourly limit for this tool. The free "
                           "demo still works — try the live co-pilot again later.")

    usage = _load_usage()
    if usage["est_usd"] + _EST_USD_PER_CALL > _DAILY_USD_CAP:
        return False, ("The live co-pilot is at capacity for today. The demo "
                       "still works — please check back tomorrow.")

    usage["calls"] += 1
    usage["est_usd"] = round(usage["est_usd"] + _EST_USD_PER_CALL, 4)
    _save_usage(usage)
    if ip:
        _ip_hits[ip].append(now)
    return True, ""


def remaining_usd() -> float:
    """Today's remaining LLM budget (for a status/debug readout)."""
    return round(max(0.0, _DAILY_USD_CAP - _load_usage()["est_usd"]), 4)

"""
Dispute-tool analytics — capture data from ANY usage of the public tool.

Records the funnel (who landed, ran the demo, shared, tried a real dispute,
copied the message) plus the outcome ("did it actually work") to a durable
append-only event log. This is what makes a Twitter launch *learnable*
instead of pure vanity reach.

Privacy posture: events are anonymous (a client-generated random session id,
never an account or name). No IP is stored (IP is used transiently for rate
limiting only). Payloads are allowlisted-by-shape and string values are hard-
capped so we never accumulate a paragraph of someone's personal complaint —
we keep amounts, categories, and outcomes, not raw free text.

Durability: writes to `SNHP_DATA_DIR` (default the repo `snhp/` dir). On Fly
the container filesystem is ephemeral, so for a real launch point
SNHP_DATA_DIR at a mounted volume (or move to Postgres) — otherwise a deploy
wipes the log. See DEPLOY.md.
"""
from __future__ import annotations

import collections
import json
import os
import time

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "snhp")


def data_dir() -> str:
    return os.environ.get("SNHP_DATA_DIR", _DEFAULT_DIR)


# Allowlisted event names — anything else is dropped (no arbitrary-string
# accumulation from a public endpoint).
ALLOWED_EVENTS = {
    "page_view",
    "demo_started",
    "demo_completed",
    "share_clicked",
    "copilot_started",
    "copilot_result",
    "copilot_error",
    "at_capacity",
    "message_copied",
    "outcome_reported",
}

_MAX_STR = 80
_MAX_KEYS = 12


def _sanitize(payload) -> dict:
    """Keep numbers/bools as-is; cap strings hard so no long free text lands."""
    if not isinstance(payload, dict):
        return {}
    out: dict = {}
    for k, v in list(payload.items())[:_MAX_KEYS]:
        key = str(k)[:32]
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[key] = v
        elif isinstance(v, str):
            out[key] = v[:_MAX_STR]
    return out


def summarize() -> dict:
    """Aggregate the event log into a launch dashboard: the funnel, real
    outcomes, and today's LLM spend. Reads the durable volume files."""
    events: collections.Counter = collections.Counter()
    sessions: set = set()
    outcomes: collections.Counter = collections.Counter()
    last_ts = 0
    try:
        with open(os.path.join(data_dir(), "dispute_events.jsonl")) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = r.get("event", "?")
                events[ev] += 1
                if r.get("session"):
                    sessions.add(r["session"])
                last_ts = max(last_ts, int(r.get("ts", 0)))
                if ev == "outcome_reported":
                    outcomes[(r.get("payload") or {}).get("result", "?")] += 1
    except FileNotFoundError:
        pass

    spend = {}
    try:
        with open(os.path.join(data_dir(), ".daily_llm_usage.json")) as f:
            spend = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return {
        "unique_sessions": len(sessions),
        # The launch funnel, top to bottom — each step a subset of the one above.
        "funnel": {
            "1_visited": events.get("page_view", 0),
            "2_ran_demo": events.get("demo_started", 0),
            "3_finished_demo": events.get("demo_completed", 0),
            "4_opened_real_copilot": events.get("copilot_started", 0),
            "5_got_a_recommendation": events.get("copilot_result", 0),
            "6_copied_the_message": events.get("message_copied", 0),
        },
        "shared_a_win": events.get("share_clicked", 0),
        "real_outcomes_reported": dict(outcomes),  # worked / partly / waiting / no
        "hit_daily_cap": events.get("at_capacity", 0),
        "errors": events.get("copilot_error", 0),
        "today_llm_spend": {
            "calls": spend.get("calls", 0),
            "est_usd": spend.get("est_usd", 0.0),
        },
        "all_events": dict(events),
        "last_event_unix": last_ts,
    }


def record_event(event: str, session_id: str | None = None, payload=None) -> bool:
    """Append one analytics event. Never raises (analytics must not break the
    user flow); returns True if written."""
    if event not in ALLOWED_EVENTS:
        return False
    rec = {
        "ts": int(time.time()),
        "event": event,
        "session": (session_id or "")[:64],
        "payload": _sanitize(payload),
    }
    try:
        path = os.path.join(data_dir(), "dispute_events.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return True
    except Exception:        # noqa: BLE001 — analytics is best-effort
        return False

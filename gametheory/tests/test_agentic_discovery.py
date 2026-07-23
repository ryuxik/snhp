"""Agentic-SEO discovery surfaces — the machine-readable doors an AI agent,
MCP tool-selector, or payment tooling reads to understand and pay this store.

Under test (all additive, pure reads, no auth):
  - GET /.well-known/agents.json  — capability manifest shape + 200
  - GET /llms-full.txt            — 200 + the detailed store reference
  - GET /v1/store/observatory     — 200 + NO raw api_key leaks (aggregate only)

Honesty invariants pinned here (the launch shelf is session + blind locker only):
  - the manifest advertises exactly the two LIVE paid slots, never a fetch slot
  - /llms-full.txt never advertises a `POST /v1/fetch` endpoint (fenced off)
  - the observatory emits counts of a keyed pseudonym, never a raw key
"""
import json
import os
import tempfile

# Temp DB before importing the app (mirrors test_a2a_commerce / test_sprint3).
_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB",
                      os.path.join(_tmp, "agentic_discovery_test.db"))

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server.http import app  # noqa: E402
from gametheory.server import billing as _billing  # noqa: E402
from vend import telemetry as _telemetry  # noqa: E402

client = TestClient(app)


# ─── /.well-known/agents.json ────────────────────────────────────────────────


def test_agents_json_shape_and_200():
    r = client.get("/.well-known/agents.json")
    assert r.status_code == 200
    m = r.json()

    # Top-level self-describing shape.
    for key in ("schema", "name", "description", "endpoints", "auth", "wallet",
                "capabilities", "free_tools", "payment", "demand_box"):
        assert key in m, f"missing top-level key {key!r}"
    assert m["schema"] == "agents.json/v0"

    # Endpoints an agent needs to actually reach the store.
    eps = m["endpoints"]
    assert eps["mcp"].endswith("/mcp/")
    for k in ("http_base", "mcp_server_card", "openapi", "llms_txt",
              "llms_full_txt", "catalog", "observatory"):
        assert k in eps

    # Auth: keyless issuance + the 50c starter, no card.
    assert m["auth"]["issue"]["path"] == "/v1/keys"
    assert m["auth"]["issue"]["human_required"] is False
    assert m["auth"]["starter_credit"]["amount_usd"] == "0.50"

    # The TWO live paid capabilities, in agent-need vocabulary — and ONLY those.
    # (RESHAPE.md §4: the blind locker is renamed to agent memory, memory-first;
    # the route /v1/store/park is unchanged — telemetry/slot-id continuity.)
    caps = {c["id"]: c for c in m["capabilities"]}
    assert set(caps) == {"negotiate_session", "agent_memory"}
    assert caps["negotiate_session"]["need"] == "negotiate a price"
    assert caps["negotiate_session"]["endpoints"]["open"]["path"] == "/v1/advice/session"
    assert caps["agent_memory"]["need"] == "remember something across sessions"
    assert caps["agent_memory"]["endpoints"]["save"]["path"] == "/v1/store/park"

    # HONESTY: no fetch/read-a-page capability is advertised anywhere.
    blob = json.dumps(m).lower()
    assert "fetch" not in blob
    assert "/v1/fetch" not in blob

    # Payment: fee comes from the billing constants (cannot drift), both rails present.
    fee = m["payment"]["fee"]
    assert fee["percent"] == _billing.COUNTER_FEE_PCT
    assert fee["fixed_cents"] == _billing.COUNTER_FEE_FIXED_CENTS
    methods = {x["id"]: x for x in m["payment"]["methods"]}
    assert methods["stripe_checkout"]["human_required"] is True
    assert methods["mpp_spt"]["human_required"] is False
    assert methods["mpp_spt"]["manifest"] == "/v1/mpp/manifest"
    assert methods["mpp_spt"]["crypto_accepted"] is False
    assert m["payment"]["settlement"] == "on_delivery"

    # Demand box + observatory citation asset.
    assert m["demand_box"]["file"]["path"] == "/v1/store/request"
    assert m["demand_box"]["observatory"]["path"] == "/v1/store/observatory"


# ─── /llms-full.txt ──────────────────────────────────────────────────────────


def test_llms_full_txt_200_mentions_store():
    r = client.get("/llms-full.txt")
    assert r.status_code == 200
    body = r.text

    # Strict superset of /llms.txt (same tier content still present).
    assert "Game Theory Layer" in body
    assert "Tier 1" in body

    # The detailed store reference is what /llms-full adds.
    assert "THE STORE" in body
    assert "/v1/advice/session" in body       # the $2 session
    assert "/v1/store/park" in body           # the blind locker
    assert "/v1/store/observatory" in body    # the citable observatory
    assert "/v1/mpp/manifest" in body         # the no-human MPP flow
    assert "millicent" in body.lower()        # the money unit
    assert "vend/mpp_client.py" in body       # the reference client

    # HONESTY: the fenced fetch slot is never advertised as a live endpoint.
    assert "POST /v1/fetch" not in body


# ─── /v1/store/observatory ───────────────────────────────────────────────────


def test_observatory_200_no_raw_key():
    # Point telemetry at a fresh temp file and write ONE line carrying a raw key,
    # so the observatory has real data to aggregate AND we can prove the raw key
    # never surfaces (it is stored only as a keyed blake2b pseudonym, and the
    # observatory emits only COUNTS of that pseudonym).
    tele = os.path.join(tempfile.mkdtemp(), "obs_telemetry.jsonl")
    os.environ["NEXTMOVE_TELEMETRY_PATH"] = tele
    raw_key = "gt_SECRET_raw_key_never_in_observatory_ZZZ"
    _telemetry.log_free_taste(raw_key, "http")
    _telemetry.log_slot_call(
        api_key=raw_key, door="http", slot_id="locker", backend_id="b",
        ok=True, settled=True, price_millicents=10, wholesale_millicents=10,
        wholesale_estimated=False, funding={"starter_millicents": 10,
                                            "funded_millicents": 0},
        shortfall_millicents=0, predicate="ok", reason=None,
        content_hash="deadbeef", request_hash=None)

    r = client.get("/v1/store/observatory")
    assert r.status_code == 200
    data = r.json()

    # It is the mechanical snapshot shape.
    assert data.get("schema") == "observatory.v1"
    for k in ("totals", "slots", "demand", "wallets", "funnel", "rgates"):
        assert k in data, f"observatory missing {k!r}"

    # NO raw key material anywhere in the response — the load-bearing assertion.
    text = r.text
    assert raw_key not in text
    assert "SECRET_raw_key" not in text
    # And no local filesystem artifact paths are exposed.
    assert "_artifacts" not in data

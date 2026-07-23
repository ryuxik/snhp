"""The two-door MCP reshape (RESHAPE.md §1-§3, §6) — surface + door contract.

Pins:
  (a) the CORE door lists EXACTLY the 15 hero-first tools, in order;
  (b) the PRO door carries every pre-reshape name (43 minus the fenced fetch)
      plus the 15 canonical tools;
  (c) `store_fetch` is on NEITHER door while FETCH_SLOT_ENABLED is False, and
      reappears on the PRO door (only) when the fence lifts;
  (d) renamed tools are true aliases of the same underlying function
      (spot-checked: negotiate, auction_bid, memory_save, session_open);
  (e) the additive /v1/memory/* HTTP aliases route to the park/retrieve handlers;
  (f) all 15 core descriptions obey the free-first / price-honest copy rules.

Run: python -m pytest gametheory/tests/test_mcp_reshape.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_mcp_reshape.db"))

from gametheory.server import mcp_server  # noqa: E402
from gametheory.server.mcp_server import (  # noqa: E402
    mcp, mcp_pro,
    gt_negotiate_turn, gt_auction_optimal_bid, store_park, nextmove_open,
)


CORE_EXPECTED_ORDER = [
    "negotiate", "negotiate_bundle", "score_deal", "auction_bid",
    "auction_reserve", "clearance_price", "stable_match", "memory_save",
    "memory_load", "session_open", "session_advise", "session_bundle",
    "session_close", "store_catalog", "store_request",
]

# The 15 free/paid tools and their sentence-one copy rule (RESHAPE §2). The seven
# free math tools + the three free store/memory reads must say "free" in sentence
# one; session_open must state "$2"; no description may OPEN with wallet mechanics.
FREE_FIRST_SENTENCE = {
    "negotiate", "negotiate_bundle", "score_deal", "auction_bid",
    "auction_reserve", "clearance_price", "stable_match",
    "memory_load", "store_catalog", "store_request",
}

# every pre-reshape tool name EXCEPT the fenced fetch slot (43 - store_fetch)
LEGACY_NAMES_MINUS_FETCH = {
    "score_deal", "gt_negotiate_turn", "gt_negotiate_bundle",
    "gt_negotiation_sell_next_offer", "gt_negotiation_buy_next_offer",
    "gt_negotiation_detect_anchor_attack", "gt_negotiation_declare_first_strike",
    "gt_negotiation_reveal_first_strike", "gt_negotiation_trust_anchor_public_key",
    "gt_auction_optimal_bid", "gt_auction_optimal_reserve",
    "gt_auction_format_recommendation", "gt_auction_simulate",
    "gt_mechanism_gale_shapley", "gt_mechanism_optimal_auction_design",
    "gt_mechanism_posted_price_optimal",
    "gt_a2a_register_operator", "gt_a2a_request_domain_challenge",
    "gt_a2a_verify_domain", "gt_a2a_build_peer_proof", "gt_a2a_open_session",
    "gt_a2a_next_offer", "gt_a2a_settle",
    "offer_profile_menu", "offer_quote",
    "gt_negotiate_open_session", "gt_negotiate_propose", "gt_negotiate_respond",
    "gt_negotiate_close_session",
    "nextmove_catalog", "nextmove_open", "nextmove_advise", "nextmove_bundle",
    "nextmove_close", "nextmove_request",
    "store_catalog", "store_park", "store_retrieve", "store_request",
    "store_request_status", "store_requests", "store_my_requests",
}


def _core_names():
    return [t.name for t in mcp._tool_manager.list_tools()]


def _pro_names():
    return {t.name for t in mcp_pro._tool_manager.list_tools()}


def _first_sentence(text: str) -> str:
    # sentence one ends at the first period; the ledes are single-clause pitches
    return (text or "").strip().split(".")[0]


# ─── (a) core door: EXACTLY 15 tools, in the hero-first order ─────────────────

def test_core_door_is_exactly_the_15_in_order():
    assert _core_names() == CORE_EXPECTED_ORDER


# ─── (b) pro door: every legacy name (minus fenced fetch) + the 15 canonical ──

def test_pro_door_carries_every_legacy_name_plus_canonical():
    pro = _pro_names()
    missing_legacy = LEGACY_NAMES_MINUS_FETCH - pro
    assert not missing_legacy, f"pro door missing legacy names: {missing_legacy}"
    missing_canonical = set(CORE_EXPECTED_ORDER) - pro
    assert not missing_canonical, f"pro door missing canonical: {missing_canonical}"
    # 42 legacy names + 12 NEW canonical names (score_deal/store_catalog/
    # store_request are shared, not renamed) = 54 distinct tools on the pro door.
    assert len(pro) == 54


# ─── (c) store_fetch fenced off both doors; reappears on pro when it lifts ─────

def test_store_fetch_absent_from_both_doors_while_fenced():
    from vend import shelf
    assert shelf.FETCH_SLOT_ENABLED is False       # the launch fence (shelf.py)
    assert "store_fetch" not in _core_names()
    assert "store_fetch" not in _pro_names()


def test_store_fetch_reappears_on_pro_when_fence_lifts(monkeypatch):
    from vend import shelf
    tm = mcp_pro._tool_manager
    assert "store_fetch" not in {t.name for t in tm.list_tools()}
    monkeypatch.setattr(shelf, "FETCH_SLOT_ENABLED", True)
    try:
        mcp_server._wire_fetch_slot()               # mirrors shelf's flag
        assert "store_fetch" in {t.name for t in tm.list_tools()}
        # the core door stays exactly 15 — fetch is a pro-only paid tool
        assert "store_fetch" not in _core_names()
        assert _core_names() == CORE_EXPECTED_ORDER
    finally:
        tm._tools.pop("store_fetch", None)          # keep the shared door clean


# ─── (d) alias correctness: renamed tools wrap the same underlying function ────

def _tool_fn(door, name):
    for t in door._tool_manager.list_tools():
        if t.name == name:
            return t.fn
    raise KeyError(name)


def test_renamed_core_tools_wrap_the_same_underlying_function():
    # each renamed core tool is a thin door-tag wrapper over the SAME function
    # the old name pointed to (functools.wraps sets __wrapped__).
    assert _tool_fn(mcp, "negotiate").__wrapped__ is gt_negotiate_turn
    assert _tool_fn(mcp, "auction_bid").__wrapped__ is gt_auction_optimal_bid
    assert _tool_fn(mcp, "memory_save").__wrapped__ is store_park
    assert _tool_fn(mcp, "session_open").__wrapped__ is nextmove_open
    # and the pro-door OLD-name aliases wrap the very same functions
    assert _tool_fn(mcp_pro, "gt_negotiate_turn").__wrapped__ is gt_negotiate_turn
    assert _tool_fn(mcp_pro, "store_park").__wrapped__ is store_park


def _call(door, name, args):
    """Invoke a tool through the door and parse the JSON payload (FastMCP returns
    either (content, structured) or a list of TextContent depending on version)."""
    res = asyncio.run(door.call_tool(name, args))
    if isinstance(res, tuple):
        return res[1]
    if isinstance(res, list) and res:
        return json.loads(res[0].text)
    raise AssertionError(f"unexpected result shape: {type(res)}")


def test_negotiate_alias_returns_same_as_underlying():
    args = dict(side="sell", walk_away=4000.0, target=6000.0,
                counterparty_offers=[4200.0, 4500.0], rounds_left=6)
    direct = gt_negotiate_turn(**args)
    via_door = _call(mcp, "negotiate", args)
    assert via_door == json.loads(json.dumps(direct))


def test_auction_bid_alias_returns_same_as_underlying():
    args = dict(auction_format="second_price_vickrey", my_valuation=100.0,
                n_competing_bidders=3,
                competitor_value_prior={"family": "uniform",
                                        "params": {"low": 0, "high": 100}})
    direct = gt_auction_optimal_bid(**args)
    via_door = _call(mcp, "auction_bid", args)
    assert via_door == json.loads(json.dumps(direct))


# ─── (e) HTTP memory aliases route to the park/retrieve handlers ──────────────

def test_memory_http_aliases_route_to_park_retrieve():
    import base64
    from fastapi.testclient import TestClient
    from gametheory.server.http import app
    from gametheory.server.onboarding import issue_key

    client = TestClient(app)
    key = issue_key(agent_id=f"mem-{uuid.uuid4().hex[:8]}",
                    contact_email="t@example.com",
                    intended_use_summary="memory alias test")["api_key"]
    blob = base64.b64encode(b"ciphertext-bytes").decode()

    # save via the NEW alias route
    saved = client.post("/v1/memory/save",
                        json={"blob_b64": blob},
                        headers={"X-API-Key": key})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["ok"] is True and body["ticket"]
    ticket = body["ticket"]

    # load via the NEW alias route — round-trips the exact ciphertext
    got = client.get(f"/v1/memory/parcel/{ticket}", headers={"X-API-Key": key})
    assert got.status_code == 200, got.text
    assert got.json()["blob_b64"] == blob

    # shape parity: the old /v1/store/park route still works and returns the same
    # envelope keys (the alias delegates to the same handler).
    legacy = client.post("/v1/store/park", json={"blob_b64": blob},
                         headers={"X-API-Key": key})
    assert legacy.status_code == 200, legacy.text
    assert set(body) == set(legacy.json())

    # the load alias matches the legacy parcel route key-for-key
    legacy_get = client.get(f"/v1/store/parcel/{ticket}",
                            headers={"X-API-Key": key})
    assert legacy_get.status_code == 200
    assert set(got.json()) == set(legacy_get.json())


# ─── (f) copy rules: free-first ledes, honest price, no wallet-first opener ────

def _core_desc(name):
    # the agent-facing description FastMCP will serve (docstring, or the
    # registration override used for score_deal / aliases)
    for t in mcp._tool_manager.list_tools():
        if t.name == name:
            return t.description or ""
    raise KeyError(name)


def test_free_tools_say_free_in_first_sentence():
    for name in FREE_FIRST_SENTENCE:
        first = _first_sentence(_core_desc(name))
        assert "free" in first.lower(), f"{name}: 'free' not in first sentence: {first!r}"


def test_session_open_states_the_price_up_front():
    first = _first_sentence(_core_desc("session_open"))
    assert "$2" in first, f"session_open first sentence lacks $2: {first!r}"


def test_memory_save_leads_with_value_not_wallet_then_trust_bullet():
    desc = _core_desc("memory_save")
    first = _first_sentence(desc)
    # sentence one is the value pitch — NEVER opens with wallet mechanics
    for banned in ("wallet", "credit", "charged", "starter", "$"):
        assert banned not in first.lower(), \
            f"memory_save opens with wallet mechanics ({banned!r}): {first!r}"
    assert first.lower().startswith("persistent memory for your agent")
    # the trust bullet is present (blind custody / ciphertext / cannot read)
    low = desc.lower()
    assert "blind custody" in low
    assert "ciphertext" in low and "cannot read your memory" in low
    # and it DOES state the wallet + starter credit, just not first
    assert "wallet" in low and "starter credit" in low


def test_no_core_description_opens_with_wallet_mechanics():
    for name in CORE_EXPECTED_ORDER:
        first = _first_sentence(_core_desc(name)).lower()
        assert not first.startswith(("your wallet", "pay ", "paid",
                                     "charged", "top up", "the wallet")), \
            f"{name} opens with wallet mechanics: {first!r}"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))

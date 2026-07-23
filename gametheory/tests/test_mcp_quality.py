"""Smithery-quality metadata on the CORE door (capability quality + server
metadata). Complements test_mcp_reshape.py (which pins the door SURFACE) by
pinning the per-tool QUALITY signals a registry grades:

  (a) every input parameter of all 15 core tools has a non-empty description;
  (b) all 15 expose an `outputSchema` (structured output);
  (c) all 15 carry `annotations` AND a human `title`;
  (d) the input schema is UNCHANGED vs the bare function apart from the added
      `description` keys (types / defaults / required-ness frozen);
  (e) the server card carries description + homepage + icon (both the serverInfo
      spelling and the top-level spelling), and every card tool carries the
      output schema + annotations;
  (f) CALL BATTERY — every one of the 15 tools is invoked through the real door
      call path with valid args and must return a NON-error result. This is the
      critical guard: FastMCP validates each real return against its outputSchema
      at call time, so an inaccurate schema would raise here.

Run: python -m pytest gametheory/tests/test_mcp_quality.py -v
"""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_mcp_quality.db"))

from gametheory.server import mcp_server  # noqa: E402
from gametheory.server.mcp_server import mcp  # noqa: E402
from gametheory.server import a2a_routes  # noqa: E402
from gametheory.server.onboarding import issue_key, wallet_credit  # noqa: E402


CORE_ORDER = [
    "negotiate", "negotiate_bundle", "score_deal", "auction_bid",
    "auction_reserve", "clearance_price", "stable_match", "memory_save",
    "memory_load", "session_open", "session_advise", "session_bundle",
    "session_close", "store_catalog", "store_request",
]

# Canonical name -> the bare underlying function (for the baseline input schema).
_BARE = {
    "negotiate": mcp_server.gt_negotiate_turn,
    "negotiate_bundle": mcp_server.gt_negotiate_bundle,
    "score_deal": mcp_server._score_deal,
    "auction_bid": mcp_server.gt_auction_optimal_bid,
    "auction_reserve": mcp_server.gt_auction_optimal_reserve,
    "clearance_price": mcp_server.gt_mechanism_posted_price_optimal,
    "stable_match": mcp_server.gt_mechanism_gale_shapley,
    "memory_save": mcp_server.store_park,
    "memory_load": mcp_server.store_retrieve,
    "session_open": mcp_server.nextmove_open,
    "session_advise": mcp_server.nextmove_advise,
    "session_bundle": mcp_server.nextmove_bundle,
    "session_close": mcp_server.nextmove_close,
    "store_catalog": mcp_server.store_catalog,
    "store_request": mcp_server.store_request,
}


def _core_tools():
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def _strip_descriptions(schema: dict) -> dict:
    """A copy of an input schema with every property `description` removed."""
    s = copy.deepcopy(schema)
    for prop in s.get("properties", {}).values():
        if isinstance(prop, dict):
            prop.pop("description", None)
    return s


def _baseline_input_schema(name: str) -> dict:
    """The input schema FastMCP derives from the BARE function (no metadata)."""
    from mcp.server.fastmcp import FastMCP
    d = FastMCP(f"baseline-{name}", stateless_http=True)
    d.add_tool(_BARE[name], name=name)
    schema = d._tool_manager.list_tools()[0].parameters
    if "type" not in schema:
        schema = {"type": "object", **schema}
    return schema


# ─── (a) every input parameter has a non-empty description ────────────────────
@pytest.mark.parametrize("name", CORE_ORDER)
def test_every_parameter_has_a_description(name):
    t = _core_tools()[name]
    props = t.parameters.get("properties", {})
    for pname, pschema in props.items():
        desc = pschema.get("description")
        assert desc and desc.strip(), f"{name}.{pname} has no description"


# ─── (b) every core tool exposes an outputSchema ──────────────────────────────
@pytest.mark.parametrize("name", CORE_ORDER)
def test_every_tool_has_an_output_schema(name):
    t = _core_tools()[name]
    assert t.output_schema is not None, f"{name} has no outputSchema"
    assert t.output_schema.get("type") == "object"
    assert t.output_schema.get("properties"), f"{name} outputSchema has no properties"


# ─── (c) every core tool carries annotations + a title ────────────────────────
@pytest.mark.parametrize("name", CORE_ORDER)
def test_every_tool_has_annotations_and_title(name):
    t = _core_tools()[name]
    assert t.title and t.title.strip(), f"{name} has no title"
    assert t.annotations is not None, f"{name} has no annotations"
    # openWorldHint is honestly False on every core tool (no open web).
    assert t.annotations.openWorldHint is False
    # readOnlyHint is set (True for pure/free tools, False for wallet/write tools).
    assert t.annotations.readOnlyHint in (True, False)


# The honest read/write split (documents the intended hints).
_READ_ONLY = {"negotiate", "negotiate_bundle", "score_deal", "auction_bid",
              "auction_reserve", "clearance_price", "stable_match",
              "memory_load", "store_catalog"}
_WRITE = {"memory_save", "session_open", "session_advise", "session_bundle",
          "session_close", "store_request"}


@pytest.mark.parametrize("name", CORE_ORDER)
def test_read_write_hints_are_honest(name):
    t = _core_tools()[name]
    if name in _READ_ONLY:
        assert t.annotations.readOnlyHint is True, f"{name} should be read-only"
    else:
        assert name in _WRITE
        assert t.annotations.readOnlyHint is False, f"{name} touches state/wallet"
        # None of the core write tools delete data.
        assert t.annotations.destructiveHint is False


def test_paid_writes_are_not_idempotent():
    tools = _core_tools()
    # session_open debits $2; memory_save writes + debits; each yields a new
    # ticket/session — honestly NOT idempotent.
    assert tools["session_open"].annotations.idempotentHint is False
    assert tools["memory_save"].annotations.idempotentHint is False


# ─── (d) input schema unchanged apart from the added descriptions ─────────────
@pytest.mark.parametrize("name", CORE_ORDER)
def test_input_schema_unchanged_apart_from_descriptions(name):
    t = _core_tools()[name]
    live = t.parameters
    if "type" not in live:
        live = {"type": "object", **live}
    base = _baseline_input_schema(name)
    assert _strip_descriptions(live) == _strip_descriptions(base), (
        f"{name}: input schema changed beyond descriptions")
    # And the ONLY thing gained on any property is `description`.
    base_props = base.get("properties", {})
    for pname, pschema in live.get("properties", {}).items():
        extra = set(pschema) - set(base_props.get(pname, {})) - {"description"}
        assert not extra, f"{name}.{pname} gained non-description keys: {extra}"
    # required-ness is identical.
    assert live.get("required", []) == base.get("required", [])


# ─── (e) the server card carries description + homepage + icon ────────────────
def test_server_card_metadata():
    card = a2a_routes.mcp_server_card()
    si = card["serverInfo"]
    # serverInfo spelling (mirrors the live initialize Implementation).
    assert si["description"].strip()
    assert si["websiteUrl"].startswith("https://")
    assert si["icons"] and si["icons"][0]["src"].endswith("favicon.svg")
    # top-level spellings (both homepage + websiteUrl, both iconUrl + icons[]).
    assert card["description"].strip()
    assert card["homepage"].startswith("https://")
    assert card["websiteUrl"].startswith("https://")
    assert card["iconUrl"].endswith("favicon.svg")
    assert card["icons"] and card["icons"][0]["mimeType"] == "image/svg+xml"


def test_server_card_tools_carry_output_schema_and_annotations():
    card = a2a_routes.mcp_server_card()
    tools = {t["name"]: t for t in card["tools"]}
    assert set(tools) == set(CORE_ORDER)
    for name, t in tools.items():
        assert t.get("title"), f"card {name} has no title"
        assert t.get("outputSchema"), f"card {name} has no outputSchema"
        assert t.get("annotations"), f"card {name} has no annotations"
        for pname, ps in t["inputSchema"].get("properties", {}).items():
            assert ps.get("description"), f"card {name}.{pname} has no description"


def test_initialize_serverinfo_carries_website_and_icons():
    """The live initialize result's serverInfo (Implementation) carries the
    homepage + icon in the icons-SEP fields registries read."""
    opts = mcp._mcp_server.create_initialization_options()
    assert opts.website_url == "https://snhp.dev"
    assert opts.icons and opts.icons[0].src.endswith("favicon.svg")
    assert opts.instructions and len(opts.instructions) > 200  # the description


# ─── (f) CALL BATTERY — invoke all 15 through the door, assert non-error ───────
def _invoke(name, args):
    """Call a tool through the real door path. Returns (raw_dict, structured_dict).
    Not raising == the outputSchema validated the real return."""
    res = asyncio.run(mcp.call_tool(name, args))
    assert isinstance(res, tuple), f"{name}: expected (content, structured)"
    content, structured = res
    raw = json.loads(content[0].text)
    assert isinstance(structured, dict)
    return raw, structured


def test_call_battery_all_15_tools_non_error():
    key = issue_key(agent_id=f"q-{uuid.uuid4().hex[:8]}",
                    contact_email="quality@test.dev",
                    intended_use_summary="mcp quality call battery")["api_key"]
    # session_open debits $2 — fund the LOCAL SQLite wallet directly.
    wallet_credit(key, 500_000, bucket="funded")

    issues = [
        {"name": "price", "options": ["$50", "$40", "$30"],
         "my_utility": [0, 0.5, 1], "their_utility": [1, 0.5, 0]},
        {"name": "sla", "options": ["99%", "99.9%"],
         "my_utility": [0, 1], "their_utility": [1, 0]},
    ]

    # 1-7 free math
    raw, _ = _invoke("negotiate", dict(
        side="sell", walk_away=4000, target=6000,
        counterparty_offers=[4200, 4500], rounds_left=6))
    assert raw.get("action") in ("counter", "accept", "walk") and "error" not in raw

    raw, _ = _invoke("negotiate_bundle", dict(
        issues=issues, my_priorities={"price": 0.7, "sla": 0.3}))
    assert raw.get("recommended_offer") and "error" not in raw

    raw, _ = _invoke("score_deal", dict(
        issues=issues, my_weights={"price": 0.7, "sla": 0.3},
        their_weights={"price": 0.3, "sla": 0.7},
        package={"price": "$40", "sla": "99%"}))
    assert "joint_welfare" in raw and "error" not in raw

    raw, _ = _invoke("auction_bid", dict(
        auction_format="first_price", my_valuation=5000, n_competing_bidders=4,
        competitor_value_prior={"family": "uniform",
                                "params": {"low": 0, "high": 6000}}))
    assert "optimal_bid" in raw and "error" not in raw

    raw, _ = _invoke("auction_reserve", dict(
        bidder_value_prior={"family": "uniform",
                            "params": {"low": 2000, "high": 8000}},
        n_bidders=5, seller_valuation=1000))
    assert "reserve_price" in raw and "error" not in raw

    raw, _ = _invoke("clearance_price", dict(
        buyer_arrival_prior={"family": "uniform",
                             "params": {"low": 40, "high": 150}},
        arrival_rate_per_second=600 / 1209600, inventory=200,
        horizon_seconds=1209600))
    assert "static_price" in raw and "error" not in raw

    raw, _ = _invoke("stable_match", dict(
        proposers=[{"id": "Ana", "preferences": ["Growth", "Core"]},
                   {"id": "Ben", "preferences": ["Core", "Growth"]}],
        receivers=[{"id": "Growth", "preferences": ["Ben", "Ana"]},
                   {"id": "Core", "preferences": ["Ana", "Ben"]}]))
    assert "matching" in raw and "error" not in raw

    # 8-9 memory round-trip
    payload = b"remember: floor is 4200"
    raw, _ = _invoke("memory_save", dict(
        api_key=key, blob_b64=base64.b64encode(payload).decode(),
        ttl_seconds=3600))
    assert raw.get("ok") is True, raw
    ticket = raw["ticket"]
    raw, _ = _invoke("memory_load", dict(api_key=key, ticket=ticket))
    assert raw.get("ok") is True
    assert base64.b64decode(raw["blob_b64"]) == payload

    # 10-13 session lifecycle
    raw, _ = _invoke("session_open", dict(
        api_key=key, category="resale", side="sell", walk_away=4000,
        target=6000, their_offers=[4200, 4500]))
    assert "error" not in raw, raw
    session_id = raw["session_id"]
    assert session_id and raw["price_cents"] == 200

    raw, _ = _invoke("session_advise", dict(
        api_key=key, session_id=session_id, their_offers=[4200, 4500, 4700]))
    assert raw.get("move") and "error" not in raw

    raw, _ = _invoke("session_bundle", dict(
        api_key=key, session_id=session_id, issues=issues,
        my_priorities={"price": 0.7, "sla": 0.3}))
    assert raw.get("move") and "error" not in raw

    raw, _ = _invoke("session_close", dict(api_key=key, session_id=session_id))
    assert raw.get("closed") is True and raw.get("receipt")

    # 14-15 store reads/writes
    raw, _ = _invoke("store_catalog", {})
    assert raw.get("slots") is not None and "error" not in raw

    raw, _ = _invoke("store_request", dict(
        text="a lease-negotiation category please", api_key=key, watch=True))
    assert raw.get("request_id") and "error" not in raw
    rid = raw["request_id"]
    raw, _ = _invoke("store_request", dict(request_id=rid))
    assert raw.get("found") is True

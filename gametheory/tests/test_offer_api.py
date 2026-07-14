"""Offer API tests — the hosted surface of the general offer-graph engine.

Covers: compile/profile/quote happy paths on small NON-boba menus (a coffee
cart and a bakery), the FREE-vs-LEVER verdicts, the never-above-list sweep,
malformed/oversized specs → 422 with a useful message, and the MCP tool
smoke test (direct call + full protocol roundtrip, matching
test_mcp_server.py's pattern).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gametheory.server import middleware as _mw
from gametheory.server.http import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Cleared rate-limit buckets per test (the house pattern from
    test_integration.py) — the sweep below makes ~100 calls."""
    _mw._BUCKETS.clear()


# A small non-boba menu: a coffee cart with a costed CHOICE, a zero-cost
# PREFERENCE, and a QUANTITY dim.
COFFEE = {
    "name": "corner coffee cart",
    "dims": [
        {"id": "item", "kind": "choice", "options": [
            {"id": "oat-latte", "label": "Oat Latte", "price_delta": 5.25,
             "unit_cost": 1.20},
            {"id": "drip", "label": "Drip Coffee", "price_delta": 3.00,
             "unit_cost": 0.40},
        ]},
        {"id": "cup", "kind": "preference", "options": [
            {"id": "for-here"}, {"id": "to-go"},
        ]},
        {"id": "qty", "kind": "quantity", "qty_cap": 3},
    ],
    "cost": ["const"],
}

# A perishable menu where a real discount exists: end-of-day croissants at
# salvage cost, a group buyer whose 3rd unit still clears cost.
BAKERY = {
    "name": "neighborhood bakery",
    "dims": [
        {"id": "item", "kind": "choice", "options": [
            {"id": "croissant", "label": "Butter Croissant",
             "price_delta": 4.25, "unit_cost": 0.95,
             "perishable": True, "salvage": 0.15},
        ]},
        {"id": "qty", "kind": "quantity", "qty_cap": 3},
    ],
    "cost": ["const", "salvage_on_expiry"],
}

KEEN_BAKERY_BUYER = {"values": {"item": {"croissant": 4.675}},  # 1.1 × list
                     "qty_decay": 0.9}


# ─── compile ─────────────────────────────────────────────────────────────────


def test_compile_happy_path():
    r = client.post("/v1/offer/compile", json=COFFEE)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "corner coffee cart"
    assert out["cost_stack"] == ["const"]
    # 2 items × 2 cups × qty 1..3 = 12 dependency-valid configs
    assert out["configs"] == 12
    by_id = {d["id"]: d for d in out["dims"]}
    assert by_id["qty"]["qty_cap"] == 3
    assert [o["id"] for o in by_id["item"]["options"]] == ["oat-latte", "drip"]
    assert r.headers["X-GT-Cost-USD"] == "0"


def test_compile_deps_and_batch_cost():
    spec = {
        "name": "deps",
        "dims": [
            {"id": "item", "kind": "choice", "options": [
                {"id": "a", "price_delta": 5.0, "unit_cost": 1.0},
                {"id": "b", "price_delta": 4.0, "unit_cost": 1.0}]},
            {"id": "extras", "kind": "addon", "options": [
                {"id": "x", "price_delta": 1.0, "unit_cost": 0.2}]},
        ],
        "deps": {"valid_on": {"x": ["a"]}},
        "cost": ["const", {"batch_economies": {"setup": 1.0, "marginal": 0.5}}],
    }
    r = client.post("/v1/offer/compile", json=spec)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["cost_stack"] == ["const", "batch_economies"]
    # {a,b} × {∅,{x}} = 4 minus (b,{x}) pruned by valid_on = 3
    assert out["configs"] == 3


# ─── profile (the signature endpoint) ────────────────────────────────────────


def test_profile_free_vs_lever():
    r = client.post("/v1/offer/profile", json={"spec": COFFEE})
    assert r.status_code == 200, r.text
    out = r.json()
    # the zero-cost preference profiles FREE; the costed choice LEVER
    assert out["verdicts"]["cup"] == "FREE"
    assert out["verdicts"]["item"] == "LEVER"
    rows = {row["dim"]: row for row in out["dims"]}
    assert rows["item"]["cost_spread"] == pytest.approx(0.80)   # 1.20 − 0.40
    assert rows["cup"]["cost_spread"] == 0.0
    for row in out["dims"]:
        assert row["why"], f"{row['dim']} verdict has no why-line"


def test_profile_reads_state():
    # at a neutral state the croissant costs 0.95; end-of-day it is salvage —
    # with a single item the CHOICE dim has no spread either way (one option),
    # but QUANTITY's marginal cost falls from 0.95 to 0.15
    r0 = client.post("/v1/offer/profile", json={"spec": BAKERY})
    r1 = client.post("/v1/offer/profile",
                     json={"spec": BAKERY, "state": {"expiring": ["croissant"]}})
    assert r0.status_code == r1.status_code == 200
    q0 = {row["dim"]: row for row in r0.json()["dims"]}["qty"]
    q1 = {row["dim"]: row for row in r1.json()["dims"]}["qty"]
    assert q0["verdict"] == q1["verdict"] == "LEVER"
    assert q0["cost_spread"] == pytest.approx(0.95)
    assert q1["cost_spread"] == pytest.approx(0.15)


# ─── quote ───────────────────────────────────────────────────────────────────


def test_quote_negotiated_discount():
    """End-of-day salvage + a group buyer → a real negotiated discount on the
    3-croissant cart (the surplus channel: the menu counterfactual is 1 cup)."""
    r = client.post("/v1/offer/quote", json={
        "spec": BAKERY,
        "state": {"expiring": ["croissant"]},
        "buyer": KEEN_BAKERY_BUYER,
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["never_above_list"] is True
    assert out["advisory"] is True
    assert out["outcome"] == "negotiated"
    q = out["quote"]
    assert q["feasible"] is True
    assert q["config"]["qty"] == 3            # the engine found the upsell
    assert q["listv"] == pytest.approx(3 * 4.25)
    assert q["cost"] <= q["price"] <= q["listv"]   # never below cost, never above list
    assert q["save"] == pytest.approx(q["listv"] - q["price"], abs=0.01)
    assert q["save"] > 0
    assert q["why"]


def test_quote_pinned_config_at_list():
    """A fresh-morning, single-croissant cart has no surplus to split — the
    pinned config comes back at list, feasible=False, never above."""
    r = client.post("/v1/offer/quote", json={
        "spec": BAKERY,
        "buyer": KEEN_BAKERY_BUYER,
        "config": {"item": "croissant", "qty": 1},
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["outcome"] == "at_list"
    q = out["quote"]
    assert q["feasible"] is False
    assert q["price"] == pytest.approx(4.25)
    assert q["save"] == 0
    assert q["config"] == {"item": "croissant", "qty": 1}


def test_quote_looker_refused():
    """A buyer below list with quote_lookers=False is refused (the IC hard
    floor), never handed a sub-menu price."""
    r = client.post("/v1/offer/quote", json={
        "spec": BAKERY,
        "buyer": {"values": {"item": {"croissant": 3.0}}, "qty_decay": 0.9},
        "opts": {"quote_lookers": False},
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["outcome"] == "walk"
    assert out["quote"] is None
    assert out["never_above_list"] is True


def test_never_above_list_sweep():
    """Sweep buyers × states × pinned carts on both menus: every quote the
    API returns must be at or below its own list value, and must say so."""
    checked = 0
    for spec, item, values in (
            (COFFEE, "oat-latte", {"item": {"oat-latte": 6.5, "drip": 2.0}}),
            (BAKERY, "croissant", {"item": {"croissant": 5.5}})):
        for state in ({}, {"expiring": [item]}):
            for balk in (0.0, 0.3):
                for qty in (1, 2, 3):
                    for w in (0.5, 0.9):
                        cfg = {"item": item, "qty": qty}
                        r = client.post("/v1/offer/quote", json={
                            "spec": spec, "state": state,
                            "buyer": {"values": values, "qty_decay": 0.9,
                                      "balk": balk},
                            "config": cfg, "opts": {"seller_weight": w},
                        })
                        assert r.status_code == 200, r.text
                        out = r.json()
                        assert out["never_above_list"] is True
                        if out["quote"] is not None:
                            q = out["quote"]
                            assert q["price"] <= q["listv"] + 1e-9, (spec["name"], state, balk, qty, w, q)
                            checked += 1
    assert checked >= 40      # the sweep actually quoted things


# ─── validation: malformed / oversized specs ────────────────────────────────


def test_malformed_spec_422_bad_kind():
    bad = {"dims": [{"id": "x", "kind": "flavor",
                     "options": [{"id": "a"}]}]}
    r = client.post("/v1/offer/compile", json=bad)
    assert r.status_code == 422
    assert "unknown dimension kind" in r.text


def test_malformed_spec_422_no_options():
    bad = {"dims": [{"id": "item", "kind": "choice", "options": []}]}
    r = client.post("/v1/offer/compile", json=bad)
    assert r.status_code == 422
    assert "needs at least one option" in r.text


def test_malformed_spec_422_bad_cost_token():
    bad = dict(COFFEE, cost=["const", "capacity_relief"])
    r = client.post("/v1/offer/compile", json=bad)
    assert r.status_code == 422
    assert "capacity_relief" in r.text and "live Python function" in r.text

    bad = dict(COFFEE, cost=["magic"])
    r = client.post("/v1/offer/compile", json=bad)
    assert r.status_code == 422
    assert "unknown cost component" in r.text


def test_malformed_spec_422_dangling_dep():
    bad = dict(COFFEE)
    bad = json.loads(json.dumps(COFFEE))
    bad["deps"] = {"requires": {"oat-latte": ["nonexistent"]}}
    r = client.post("/v1/offer/compile", json=bad)
    assert r.status_code == 422
    assert "unknown option id" in r.text


def test_oversized_spec_rejected():
    # per-dim option cap (reuses core's MAX_ADDON_OPTIONS = 12)
    too_many = {"dims": [
        {"id": "extras", "kind": "addon",
         "options": [{"id": f"o{i}"} for i in range(13)]},
    ]}
    r = client.post("/v1/offer/compile", json=too_many)
    assert r.status_code == 422

    # combinatorial cap: 2 addon dims × 2^12 each = 16.7M ≫ 20k
    boom = {"dims": [
        {"id": f"addons{j}", "kind": "addon",
         "options": [{"id": f"a{j}-{i}"} for i in range(12)]}
        for j in range(2)
    ]}
    r = client.post("/v1/offer/compile", json=boom)
    assert r.status_code == 422
    assert "configurations" in r.text and "cap" in r.text


def test_quote_config_validation_422():
    r = client.post("/v1/offer/quote", json={
        "spec": COFFEE,
        "buyer": {"values": {"item": {"oat-latte": 6.0}}},
        "config": {"beans": "oat-latte"},
    })
    assert r.status_code == 422
    assert "unknown dimension 'beans'" in r.text

    r = client.post("/v1/offer/quote", json={
        "spec": COFFEE,
        "buyer": {"values": {"item": {"oat-latte": 6.0}}},
        "config": {"qty": 99},
    })
    assert r.status_code == 422
    assert "between 1 and 3" in r.text


# ─── MCP tools (same pattern as test_mcp_server.py) ──────────────────────────


def test_mcp_tools_direct_call():
    from gametheory.server.mcp_server import offer_profile_menu, offer_quote

    prof = offer_profile_menu(spec=COFFEE)
    assert prof["verdicts"]["cup"] == "FREE"
    assert prof["verdicts"]["item"] == "LEVER"

    out = offer_quote(spec=BAKERY, buyer=KEEN_BAKERY_BUYER,
                      state={"expiring": ["croissant"]})
    assert out["outcome"] == "negotiated"
    assert out["never_above_list"] is True
    assert out["quote"]["price"] <= out["quote"]["listv"] + 1e-9

    bad = offer_quote(spec={"dims": []}, buyer={})
    assert "error" in bad


@pytest.mark.anyio
async def test_mcp_offer_tools_roundtrip():
    """Full MCP handshake over in-memory streams: the offer tools are listed
    and callable through the hosted server's own FastMCP instance."""
    from mcp.shared.memory import create_connected_server_and_client_session
    from gametheory.server.mcp_server import mcp
    async with create_connected_server_and_client_session(
            mcp._mcp_server) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"offer_profile_menu", "offer_quote"} <= names
        res = await session.call_tool("offer_profile_menu", {"spec": COFFEE})
        assert not res.isError
        payload = json.loads(res.content[0].text)
        assert payload["verdicts"] == {"item": "LEVER", "cup": "FREE",
                                       "qty": "LEVER"}


@pytest.fixture
def anyio_backend():
    return "asyncio"

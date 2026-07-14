"""JS <-> Python parity gate for the friendly menu format.

gametheory/server/menu_spec.friendly_to_dims is a field-for-field Python port
of arena/web/yourmenu.js (validateMenu + menuToSpec). This file is the gate
that keeps the two honest: it takes the TWO example menus from yourmenu.js
VERBATIM (coffee cart, bakery), compiles them through friendly_to_dims ->
core.api.build_graph, and asserts

  1. the compiled `dims` spec is byte-for-byte what the page's menuToSpec emits;
  2. the profiler's FREE/LEVER verdicts (and the probed cost spreads) match;
  3. a broad quote sweep reproduces the page's prices TO THE CENT, using the
     same simulated shopper / shop moment the page builds (makeState /
     makeBuyer / cartConfig / quoteWithCtx), pinned with a search_filter so the
     disagreement anchor roams exactly as it does on the page.

The pinned numbers are the ones arena/web/yourmenu_verify.test.mjs asserts and
the page renders (e.g. coffee verdicts item/extras=LEVER, cup/pickup=FREE,
qty=LEVER; croissant x3 -> $9.20 fresh, $8.02 end-of-day). If ANY verdict or
price here differs from the JS side, the transform is wrong — fix the transform,
not the assert.

Plus: the hosted /v1/offer/* API now DUAL-ACCEPTS both the friendly menu and
the raw dims spec (menu_spec wired into MenuSpec), tested here against the
TestClient; the existing raw-dims behaviour is covered by test_offer_api.py.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from core.api import build_graph, profile
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as engine_quote
from core.offer_graph import qty_of
from core.profiler import _default_config, _variants
from gametheory.server import middleware as _mw
from gametheory.server.http import app
from gametheory.server.menu_spec import (FriendlyMenuError, friendly_price_floor,
                                         friendly_state, friendly_to_dims,
                                         is_friendly)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    _mw._BUCKETS.clear()


# ─── the two example menus, copied VERBATIM from arena/web/yourmenu.js ───────
COFFEE_MENU = {
    "name": "corner coffee cart",
    "items": [
        {"id": "oat-latte", "label": "Oat Latte", "price": 5.25, "cost": 1.20},
        {"id": "cappuccino", "label": "Cappuccino", "price": 4.75, "cost": 1.05},
        {"id": "drip", "label": "Drip Coffee", "price": 3.00, "cost": 0.40},
        {"id": "cold-brew", "label": "Cold Brew", "price": 4.50, "cost": 0.85,
         "stock": 6, "expected_demand": 10},
    ],
    "addons": [
        {"id": "extra-shot", "label": "Extra Shot", "price": 1.00, "cost": 0.28},
        {"id": "vanilla", "label": "Vanilla Syrup", "price": 0.50, "cost": 0.10},
    ],
    "preferences": [
        {"id": "cup", "label": "Cup", "options": [
            {"id": "for-here", "label": "For here"},
            {"id": "to-go", "label": "To go"}]},
    ],
    "slots": [
        {"id": "now", "label": "Right now", "minutes": 0},
        {"id": "in-20", "label": "In 20 min", "minutes": 20, "capacity": 6},
    ],
    "max_qty": 3,
}
BAKERY_MENU = {
    "name": "neighborhood bakery",
    "items": [
        {"id": "croissant", "label": "Butter Croissant", "price": 4.25,
         "cost": 0.95, "perishable": True, "salvage": 0.15},
        {"id": "almond-croissant", "label": "Almond Croissant", "price": 5.50,
         "cost": 1.40, "perishable": True, "salvage": 0.20},
        {"id": "sourdough", "label": "Sourdough Loaf", "price": 9.00,
         "cost": 2.60, "perishable": True, "salvage": 0.50},
        {"id": "granola-bar", "label": "Granola Bar", "price": 3.50, "cost": 1.10},
    ],
    "addons": [{"id": "jam", "label": "House Jam", "price": 1.50, "cost": 0.45}],
    "preferences": [
        {"id": "slicing", "label": "Slicing", "options": [
            {"id": "whole", "label": "Whole"},
            {"id": "sliced", "label": "Sliced"}]},
    ],
    "max_qty": 4,
    "min_price_frac": 0.35,
}

# ─── what the page's menuToSpec emits for each (pinned byte-for-byte) ────────
COFFEE_DIMS_SPEC = {
    "name": "corner coffee cart",
    "dims": [
        {"id": "item", "kind": "choice", "options": [
            {"id": "oat-latte", "label": "Oat Latte", "price_delta": 5.25,
             "unit_cost": 1.2, "stock_limited": False, "perishable": False,
             "salvage": 0},
            {"id": "cappuccino", "label": "Cappuccino", "price_delta": 4.75,
             "unit_cost": 1.05, "stock_limited": False, "perishable": False,
             "salvage": 0},
            {"id": "drip", "label": "Drip Coffee", "price_delta": 3,
             "unit_cost": 0.4, "stock_limited": False, "perishable": False,
             "salvage": 0},
            {"id": "cold-brew", "label": "Cold Brew", "price_delta": 4.5,
             "unit_cost": 0.85, "stock_limited": True, "perishable": False,
             "salvage": 0}]},
        {"id": "extras", "kind": "addon", "options": [
            {"id": "extra-shot", "label": "Extra Shot", "price_delta": 1,
             "unit_cost": 0.28, "perishable": False, "salvage": 0},
            {"id": "vanilla", "label": "Vanilla Syrup", "price_delta": 0.5,
             "unit_cost": 0.1, "perishable": False, "salvage": 0}]},
        {"id": "cup", "kind": "preference", "options": [
            {"id": "for-here", "label": "For here", "price_delta": 0,
             "unit_cost": 0},
            {"id": "to-go", "label": "To go", "price_delta": 0,
             "unit_cost": 0}]},
        {"id": "pickup", "kind": "fulfillment", "options": [
            {"id": "now", "label": "Right now", "immediate": True,
             "slot_ticks": 0},
            {"id": "in-20", "label": "In 20 min", "immediate": False,
             "slot_ticks": 2}]},
        {"id": "qty", "kind": "quantity", "qty_cap": 3}],
    "cost": ["const", "scarcity_shadow"],
}
BAKERY_DIMS_SPEC = {
    "name": "neighborhood bakery",
    "dims": [
        {"id": "item", "kind": "choice", "options": [
            {"id": "croissant", "label": "Butter Croissant", "price_delta": 4.25,
             "unit_cost": 0.95, "stock_limited": False, "perishable": True,
             "salvage": 0.15},
            {"id": "almond-croissant", "label": "Almond Croissant",
             "price_delta": 5.5, "unit_cost": 1.4, "stock_limited": False,
             "perishable": True, "salvage": 0.2},
            {"id": "sourdough", "label": "Sourdough Loaf", "price_delta": 9,
             "unit_cost": 2.6, "stock_limited": False, "perishable": True,
             "salvage": 0.5},
            {"id": "granola-bar", "label": "Granola Bar", "price_delta": 3.5,
             "unit_cost": 1.1, "stock_limited": False, "perishable": False,
             "salvage": 0}]},
        {"id": "extras", "kind": "addon", "options": [
            {"id": "jam", "label": "House Jam", "price_delta": 1.5,
             "unit_cost": 0.45, "perishable": False, "salvage": 0}]},
        {"id": "slicing", "kind": "preference", "options": [
            {"id": "whole", "label": "Whole", "price_delta": 0, "unit_cost": 0},
            {"id": "sliced", "label": "Sliced", "price_delta": 0,
             "unit_cost": 0}]},
        {"id": "qty", "kind": "quantity", "qty_cap": 4}],
    "cost": ["const", "salvage_on_expiry"],
}

# verdict + probed cost-spread per dim (yourmenu.js profileMenu, neutral moment)
COFFEE_VERDICTS = {"item": ("LEVER", 4.1), "extras": ("LEVER", 0.28),
                   "cup": ("FREE", 0.0), "pickup": ("FREE", 0.0),
                   "qty": ("LEVER", 1.2)}
BAKERY_VERDICTS = {"item": ("LEVER", 1.65), "extras": ("LEVER", 0.45),
                   "slicing": ("FREE", 0.0), "qty": ("LEVER", 0.95)}

# The page's live quote() output, pinned to the cent. Each row:
#   (scenario, cart, outcome, price)   — outcome in {negotiated, at-list}.
COFFEE_QUOTES = [
    (dict(level='interested', busy=False, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=1), 'at-list', 6.75),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='now', qty=1), 'at-list', 6.75),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='oat-latte', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'negotiated', 8.1),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='drip', addons=[], prefs={'cup': 'to-go'}, slot='in-20', qty=3), 'negotiated', 6.43),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='now', qty=1), 'at-list', 4.5),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'at-list', 9),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='cappuccino', addons=['vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=2), 'negotiated', 8.1),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=1), 'negotiated', 5.98),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='now', qty=1), 'at-list', 6.75),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='oat-latte', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'negotiated', 8.1),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='drip', addons=[], prefs={'cup': 'to-go'}, slot='in-20', qty=3), 'negotiated', 5.91),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='now', qty=1), 'at-list', 4.5),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'at-list', 9),
    (dict(level='interested', busy=True, endOfDay=False), dict(item='cappuccino', addons=['vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=2), 'negotiated', 8.1),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=1), 'at-list', 6.75),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='now', qty=1), 'at-list', 6.75),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='oat-latte', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'at-list', 10.5),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='drip', addons=[], prefs={'cup': 'to-go'}, slot='in-20', qty=3), 'negotiated', 7.97),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='now', qty=1), 'at-list', 4.5),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'at-list', 9),
    (dict(level='keen', busy=True, endOfDay=False), dict(item='cappuccino', addons=['vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=2), 'at-list', 10.5),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=1), 'negotiated', 4.05),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='oat-latte', addons=['extra-shot', 'vanilla'], prefs={'cup': 'to-go'}, slot='now', qty=1), 'negotiated', 4.05),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='oat-latte', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'negotiated', 6.3),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='drip', addons=[], prefs={'cup': 'to-go'}, slot='in-20', qty=3), 'negotiated', 5.4),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='now', qty=1), 'at-list', 4.5),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='cold-brew', addons=[], prefs={'cup': 'for-here'}, slot='in-20', qty=2), 'at-list', 9),
    (dict(level='browsing', busy=True, endOfDay=False), dict(item='cappuccino', addons=['vanilla'], prefs={'cup': 'to-go'}, slot='in-20', qty=2), 'negotiated', 6.3),
]
BAKERY_QUOTES = [
    (dict(level='interested', busy=False, endOfDay=False), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 9.2),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=1), 'at-list', 4.25),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='croissant', addons=['jam'], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 9.37),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='almond-croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=4), 'negotiated', 15.87),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='sourdough', addons=[], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 14.66),
    (dict(level='interested', busy=False, endOfDay=False), dict(item='granola-bar', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 7.58),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 8.02),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=1), 'at-list', 4.25),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='croissant', addons=['jam'], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 9.37),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='almond-croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=4), 'negotiated', 13.83),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='sourdough', addons=[], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 12.99),
    (dict(level='interested', busy=False, endOfDay=True), dict(item='granola-bar', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 7.58),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'at-list', 12.75),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=1), 'at-list', 4.25),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='croissant', addons=['jam'], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'at-list', 11.5),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='almond-croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=4), 'negotiated', 19.96),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='sourdough', addons=[], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'at-list', 18),
    (dict(level='keen', busy=False, endOfDay=True), dict(item='granola-bar', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'at-list', 10.5),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 5.65),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=1), 'negotiated', 1.88),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='croissant', addons=['jam'], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 5.1),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='almond-croissant', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=4), 'negotiated', 9.74),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='sourdough', addons=[], prefs={'slicing': 'sliced'}, slot=None, qty=2), 'negotiated', 7.97),
    (dict(level='browsing', busy=False, endOfDay=True), dict(item='granola-bar', addons=[], prefs={'slicing': 'whole'}, slot=None, qty=3), 'negotiated', 5.63),
]

# ─── the page's simulated shopper / moment, mirrored (yourmenu.js constants) ─
MULT = {"keen": 1.25, "interested": 1.10, "browsing": 0.90}
QTY_DECAY = 0.9
BUSY_BALK = 0.30
DEFER_PER_TICK = 0.05


def _round2(x: float) -> float:
    """yourmenu.js round2 — round half up at the cent."""
    return math.floor((x + 1e-12) * 100 + 0.5) / 100


def _find(rows, key):
    return next((r for r in rows if r["id"] == key), None)


def _ticks_of(minutes: int) -> int:
    return 0 if minutes == 0 else max(1, math.floor(minutes / 10 + 0.5))


def _make_state(menu, end_of_day):
    from core.state import ShopState
    s = friendly_state(menu, end_of_day=end_of_day)
    return ShopState(tick=s["tick"], inventory=dict(s["inventory"]),
                     capacity={int(k): v for k, v in s["capacity"].items()},
                     expiring=set(s["expiring"]),
                     expected_demand=dict(s["expected_demand"]))


def _make_buyer(menu, level, busy, cart):
    mult = MULT[level]
    values = {}
    it = _find(menu["items"], cart["item"])
    if it:
        values[("item", it["id"])] = mult * it["price"]
    for aid in cart.get("addons", []):
        a = _find(menu.get("addons", []), aid)
        if a:
            values[("extras", a["id"])] = mult * a["price"]
    for p in menu.get("preferences", []):
        oid = (cart.get("prefs") or {}).get(p["id"])
        o = _find(p["options"], oid) if oid else None
        if o and o.get("price", 0) > 0:
            values[(p["id"], o["id"])] = mult * o["price"]
    defer = {0: 0.0}
    for s in menu.get("slots", []) or []:
        t = _ticks_of(s["minutes"])
        defer[t] = _round2(DEFER_PER_TICK * t)
    return SeparableBuyer(values=values, qty_decay=QTY_DECAY, outside=0.0,
                          balk=(BUSY_BALK if busy else 0.0), defer=defer)


def _cart_config(menu, cart):
    cfg = {"item": cart["item"]}
    if menu.get("addons"):
        cfg["extras"] = frozenset(cart.get("addons", []))
    for p in menu.get("preferences", []):
        cfg[p["id"]] = (cart.get("prefs") or {}).get(p["id"]) or p["options"][0]["id"]
    if menu.get("slots"):
        cfg["pickup"] = cart.get("slot") or "now"
    cfg["qty"] = cart.get("qty", 1)
    return cfg


def _list_price(menu, cart):
    per = _find(menu["items"], cart["item"])["price"]
    for aid in cart.get("addons", []):
        a = _find(menu.get("addons", []), aid)
        per += a["price"] if a else 0
    for p in menu.get("preferences", []):
        o = _find(p["options"], (cart.get("prefs") or {}).get(p["id"]))
        per += o.get("price", 0) if o else 0
    return _round2(cart.get("qty", 1) * per)


def _same_config(c, cfg):
    for k, b in cfg.items():
        a = c.get(k)
        if isinstance(b, (frozenset, set)) or isinstance(a, (frozenset, set)):
            if frozenset(b or ()) != frozenset(a or ()):
                return False
        elif a != b:
            return False
    return True


def _probe_spread(graph, state, dim):
    """The profiler's own cost probe (mirrors offer_api._probe_spread and the
    page's probeSpread)."""
    variants = _variants(dim, _default_config(graph))
    if len(variants) < 2:
        return 0.0
    costs = [graph.cost.quote(graph, state, c, qty_of(graph, c)).c_eff
             for c in variants]
    return _round2(max(costs) - min(costs))


def _page_quote(menu, graph, scn, cart):
    """Reproduce yourmenu.js quoteWithCtx: pin the cart with a search_filter
    (so the disagreement anchor roams the full menu, cart_nash semantics),
    prune_free off, quote_lookers on, at the menu's own price floor."""
    state = _make_state(menu, scn["endOfDay"])
    buyer = _make_buyer(menu, scn["level"], scn["busy"], cart)
    cfg = _cart_config(menu, cart)
    opts = QuoteOpts(min_price_frac=friendly_price_floor(menu),
                     prune_free=False, quote_lookers=True,
                     search_filter=lambda g, s, b, c: _same_config(c, cfg))
    q = engine_quote(graph, state, buyer, config=None, opts=opts)
    if q is not None and q.feasible and _same_config(q.config, cfg):
        return "negotiated", _round2(q.price)
    return "at-list", _list_price(menu, cart)


MENUS = {"coffee": (COFFEE_MENU, COFFEE_DIMS_SPEC, COFFEE_VERDICTS, COFFEE_QUOTES),
         "bakery": (BAKERY_MENU, BAKERY_DIMS_SPEC, BAKERY_VERDICTS, BAKERY_QUOTES)}


# ─── 1 · the transform: friendly menu -> dims spec, byte-for-byte ───────────


@pytest.mark.parametrize("name", ["coffee", "bakery"])
def test_friendly_to_dims_matches_page_spec(name):
    menu, spec, _v, _q = MENUS[name]
    assert friendly_to_dims(menu) == spec


def test_is_friendly_discriminates():
    assert is_friendly(COFFEE_MENU) is True
    assert is_friendly(COFFEE_DIMS_SPEC) is False       # raw dims spec
    assert is_friendly({"dims": []}) is False


# ─── 2 · profiler parity: FREE/LEVER verdicts + probed cost spreads ─────────


@pytest.mark.parametrize("name", ["coffee", "bakery"])
def test_profile_verdicts_and_spreads_match_page(name):
    menu, _spec, verdicts, _q = MENUS[name]
    graph = build_graph(friendly_to_dims(menu))
    state = _make_state(menu, end_of_day=False)
    prof = profile(graph, state)
    for d in graph.dims:
        want_verdict, want_spread = verdicts[d.id]
        assert prof[d.id].value.upper() == want_verdict, d.id
        assert _probe_spread(graph, state, d) == pytest.approx(want_spread, abs=1e-9), d.id


# ─── 3 · quote parity: every cart prices to the cent as the page shows ──────


@pytest.mark.parametrize("name", ["coffee", "bakery"])
def test_quote_sweep_matches_page_to_the_cent(name):
    menu, _spec, _v, quotes = MENUS[name]
    graph = build_graph(friendly_to_dims(menu))
    for scn, cart, want_outcome, want_price in quotes:
        outcome, price = _page_quote(menu, graph, scn, cart)
        tag = f"{name} {scn} {cart}"
        assert outcome == want_outcome, tag
        assert f"{price:.2f}" == f"{want_price:.2f}", tag


def test_croissant_x3_headline_numbers():
    """The numbers the page and yourmenu_verify.test.mjs call out by name."""
    menu = BAKERY_MENU
    graph = build_graph(friendly_to_dims(menu))
    cart = dict(item="croissant", addons=[], prefs={"slicing": "whole"},
                slot=None, qty=3)
    fresh = _page_quote(menu, graph, dict(level="interested", busy=False,
                                          endOfDay=False), cart)
    eod = _page_quote(menu, graph, dict(level="interested", busy=False,
                                        endOfDay=True), cart)
    assert fresh == ("negotiated", 9.2)
    assert eod == ("negotiated", 8.02)


# ─── 4 · friendly errors (mirrors yourmenu.js validateMenu) ─────────────────


def test_friendly_errors_are_helpful():
    def bad(menu, needle):
        with pytest.raises(FriendlyMenuError) as e:
            friendly_to_dims(menu)
        assert needle in str(e.value), str(e.value)

    bad({}, '"items" is required')
    bad({"items": [{"id": "a", "price": -2, "cost": 1}]}, '"price" must be a number > 0')
    bad({"items": [{"id": "a", "price": 2, "cost": 1},
                   {"id": "a", "price": 3, "cost": 1}]}, 'duplicate id "a"')
    bad({"items": [{"id": "a", "price": 2, "cost": 1, "expected_demand": 5}]},
        'needs "stock"')
    bad({"items": [{"id": "a", "price": 2, "cost": 1, "salvage": 0.5}]},
        '"perishable": true')
    bad({"items": [{"id": "a", "price": 2, "cost": 1}], "typo_key": True},
        'unknown top-level key "typo_key"')
    bad({"items": [{"id": "a", "price": 2, "cost": 1}],
         "slots": [{"id": "s1", "minutes": 20}, {"id": "s2", "minutes": 22}]},
        "same 10-minute tick")


def test_slots_without_immediate_gets_now_prepended():
    spec = friendly_to_dims({"items": [{"id": "a", "price": 2, "cost": 1}],
                             "slots": [{"id": "later", "minutes": 30}]})
    pickup = _find(spec["dims"], "pickup")
    assert pickup["options"][0] == {"id": "now", "label": "Right now",
                                    "immediate": True, "slot_ticks": 0}


def test_friendly_state_and_floor():
    st = friendly_state(COFFEE_MENU, end_of_day=False)
    assert st["inventory"] == {"cold-brew": 6}
    assert st["expected_demand"] == {"cold-brew": 10}
    assert st["capacity"] == {2: 6}
    assert st["expiring"] == []
    assert friendly_state(BAKERY_MENU, end_of_day=True)["expiring"] == \
        ["croissant", "almond-croissant", "sourdough"]
    assert friendly_price_floor(COFFEE_MENU) == 0.6      # default
    assert friendly_price_floor(BAKERY_MENU) == 0.35     # declared


# ─── 5 · the hosted API dual-accepts BOTH formats ──────────────────────────


@pytest.mark.parametrize("name", ["coffee", "bakery"])
def test_api_compile_accepts_friendly(name):
    menu, spec, _v, _q = MENUS[name]
    r_friendly = client.post("/v1/offer/compile", json=menu)
    r_dims = client.post("/v1/offer/compile", json=spec)
    assert r_friendly.status_code == 200, r_friendly.text
    assert r_dims.status_code == 200, r_dims.text
    # same compiled graph either way
    assert r_friendly.json() == r_dims.json()


@pytest.mark.parametrize("name", ["coffee", "bakery"])
def test_api_profile_accepts_friendly(name):
    menu, _spec, verdicts, _q = MENUS[name]
    r = client.post("/v1/offer/profile",
                    json={"spec": menu,
                          "state": friendly_state(menu, end_of_day=False)})
    assert r.status_code == 200, r.text
    got = r.json()["verdicts"]
    assert got == {d: v[0] for d, v in verdicts.items()}


def test_api_quote_accepts_friendly_and_holds_never_above_list():
    # a friendly-menu quote of the headline bakery cart, end of day
    r = client.post("/v1/offer/quote", json={
        "spec": BAKERY_MENU,
        "state": friendly_state(BAKERY_MENU, end_of_day=True),
        "buyer": {"values": {"item": {"croissant": 1.10 * 4.25}},
                  "qty_decay": 0.9},
        "config": {"item": "croissant", "qty": 3},
        "opts": {"min_price_frac": friendly_price_floor(BAKERY_MENU)},
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["never_above_list"] is True
    q = out["quote"]
    assert q["price"] <= q["listv"] + 1e-9
    assert q["listv"] == pytest.approx(12.75)


def test_api_rejects_both_formats_at_once():
    r = client.post("/v1/offer/compile",
                    json={**COFFEE_MENU, "dims": []})
    assert r.status_code == 422
    assert "not both" in r.text


def test_api_friendly_malformed_is_422():
    r = client.post("/v1/offer/compile",
                    json={"items": [{"id": "a", "price": -1, "cost": 1}]})
    assert r.status_code == 422
    assert "price" in r.text


def test_api_raw_dims_still_work():
    """Regression: the native dims spec (no `items`) is untouched by the
    dual-accept before-validator."""
    r = client.post("/v1/offer/compile", json=COFFEE_DIMS_SPEC)
    assert r.status_code == 200, r.text
    assert r.json()["cost_stack"] == ["const", "scarcity_shadow"]

"""G1 — the general offer-graph engine reproduces boba.policies.cart_nash.

Two levels (docs/REDESIGN.md Phase 2):

  1. CART-LEVEL EQUIVALENCE (primary, cheap, strong). Replay boba's OWN shipped
     sim trajectory (same seed, same draws) and, at every cart quote, compare
     core.adapters.boba.engine_cart_nash against boba.policies.cart_nash under
     the deployed ship config. Assert the SAME chosen (drink, toppings, qty,
     slot) and the SAME price within $0.01. If the carts price identically, the
     sim numbers follow.

  2. SIM-LEVEL REPRODUCTION (confirmation). Drive the paired-MC harness with the
     engine as the pricer and confirm attested / no-attest / worst-case
     reproduce boba's committed band (+$497 / +$253 / +$0/day).

boba/ is untouched (additive only); the adapter is validated ALONGSIDE
cart_nash, which stays the shipped path. The exact reproduced values are
+$497.41 / +$253.27 / +$0.00 — byte-identical to cart_nash (100% cart-level
match), well inside the ±$5/day band asserted below.
"""
from __future__ import annotations

import pytest

from boba.policies import CartPolicy, StaticMenu, cart_nash
from boba.run import run_day as boba_run_day
from boba.world import BobaConfig
from core.adapters.boba import (build_graph, engine_cart_nash, shop_state)
from core.adapters.tests import _boba_harness as H
from core.offer_graph import DimKind

SEED = 20260710
CFG = BobaConfig(sigma_shock=0.0, flexible_share=0.35)   # the flagship P0 cell

# committed band (boba/RESULTS.md P2 — the deployed clamps qty_appetite=True,
# min_price_frac=0.6, 30 paired days, seed 20260710).
COMMITTED = {"attested": 497.0, "no-attest": 253.0, "worst": 0.0}
SIM_TOL = 5.0            # ±$5/day on the 30-day mean (task-stated tolerance).

EQUIV_DAYS = 8          # ~3k cart quotes/config on the real trajectory
REPRO_DAYS = 30         # the committed band is a 30-day mean


def _ship_policy(quote_lookers: bool, liars: bool = False) -> CartPolicy:
    """The deployed cart config: qty_appetite + min_price_frac=0.6, attestation
    on (honest) or off with an all-liar population (worst case)."""
    return CartPolicy(qty_appetite=True, min_price_frac=0.6,
                      quote_lookers=quote_lookers,
                      attest=not liars, liar_share=1.0 if liars else 0.0)


SHIP_CONFIGS = {
    "attested":  _ship_policy(quote_lookers=True),
    "no-attest": _ship_policy(quote_lookers=False),
    "worst":     _ship_policy(quote_lookers=False, liars=True),
}


@pytest.fixture(scope="module")
def static_baseline() -> float:
    """Total static-arm margin over REPRO_DAYS — the paired-MC baseline the
    cart Δ/day is measured against. Computed once (no cart pricer involved)."""
    static = StaticMenu()
    return sum(boba_run_day(static, SEED, d, CFG)["margin"]
               for d in range(REPRO_DAYS))


# ── the graph is a faithful projection of boba's menu ─────────────────────
def test_graph_shape_from_boba_constants():
    from boba import world
    g = build_graph()
    kinds = {d.id: d.kind for d in g.dims}
    assert kinds == {"drink": DimKind.CHOICE, "tops": DimKind.ADDON,
                     "pickup": DimKind.FULFILLMENT, "qty": DimKind.QUANTITY}
    drink = g.dim("drink")
    assert {o.id for o in drink.options} == set(world.DRINK_PRICE)
    for o in drink.options:
        assert o.price_delta == world.DRINK_PRICE[o.id]
        assert o.unit_cost == world.DRINK_COST[o.id]
    tops = g.dim("tops")
    assert {o.id for o in tops.options} == set(world.TOP_PRICE)
    pearls = tops.option("pearls")
    assert pearls.stock_limited and pearls.perishable and pearls.salvage == 0.0
    assert g.dim("qty").qty_cap == world.QTY_CAP
    slots = {o.slot_ticks: o.immediate for o in g.dim("pickup").options}
    assert slots == {0: True, 3: False, 6: False}


def test_shop_state_projects_pearls_and_slots():
    from boba.world import open_shop
    st = open_shop(day=0)
    st.tick = 12                                  # a peak tick, slots open
    proj = shop_state(st)
    assert proj.inventory["pearls"] == float(st.pearl_stock())
    assert proj.tick == 12
    assert proj.extra["boba"] is st


# ── the harness is byte-faithful to boba.run.run_day ──────────────────────
def test_harness_reproduces_boba_run_day():
    """Sanity floor: with pricer=cart_nash the harness equals boba.run.run_day
    day-for-day, so any sim-level delta is the PRICER, never a copy error."""
    for name, pol in SHIP_CONFIGS.items():
        for d in range(4):
            ref = boba_run_day(pol, SEED, d, CFG)
            got = H.run_day(pol, SEED, d, CFG, pricer=cart_nash)
            assert got["margin"] == ref["margin"], (
                f"{name} day {d}: harness {got['margin']} != run_day "
                f"{ref['margin']}")
            assert got["cups"] == ref["cups"] and got["deals"] == ref["deals"]


# ── LEVEL 1: cart-level equivalence over the real trajectory ──────────────
@pytest.mark.parametrize("config", list(SHIP_CONFIGS))
def test_cart_level_equivalence(config):
    """Drive the shipped sim with cart_nash; at every quote compare the engine.
    The trajectory stays cart_nash's (byte-identical to boba.run), so this is
    the engine measured against the real state distribution the shop sees."""
    pol = SHIP_CONFIGS[config]
    counts: dict = {}
    mism: list = []
    for d in range(EQUIV_DAYS):
        H.run_day(pol, SEED, d, CFG, pricer=cart_nash,
                  compare_with=engine_cart_nash, mismatches=mism, counts=counts)
    total = counts.get("total", 0)
    bad = counts.get("mismatch", 0)
    assert total > 1000, f"{config}: only {total} quotes compared"
    rate = (total - bad) / total
    # ≥99% required; 100% expected (the three known divergences are closed).
    assert rate >= 0.99, (
        f"{config}: cart-level match {rate:.4%} ({bad}/{total}); "
        f"first mismatches: {mism[:5]}")
    assert bad == 0, (
        f"{config}: {bad}/{total} residual mismatches (expected 0): {mism[:5]}")


# ── LEVEL 2: sim-level reproduction of the committed band ─────────────────
@pytest.mark.parametrize("config", list(SHIP_CONFIGS))
def test_sim_level_reproduction(config, static_baseline):
    """Swap the engine in as the pricer for the full paired-MC and confirm the
    committed Δ/day band reproduces within ±$5/day. (It is in fact exact — the
    engine total equals cart_nash's byte-for-byte, asserted alongside.)"""
    pol = SHIP_CONFIGS[config]
    engine_total = 0.0
    cart_total = 0.0
    for d in range(REPRO_DAYS):
        engine_total += H.run_day(pol, SEED, d, CFG,
                                  pricer=engine_cart_nash)["margin"]
        cart_total += H.run_day(pol, SEED, d, CFG, pricer=cart_nash)["margin"]
    delta_per_day = (engine_total - static_baseline) / REPRO_DAYS
    # the committed band (task's ±$5/day acceptance)
    assert abs(delta_per_day - COMMITTED[config]) <= SIM_TOL, (
        f"{config}: engine Δ/day {delta_per_day:+.2f} vs committed "
        f"{COMMITTED[config]:+.2f} (tol ±{SIM_TOL})")
    # and the stronger fact behind it: exact reproduction of cart_nash
    assert engine_total == cart_total, (
        f"{config}: engine total {engine_total} != cart_nash {cart_total}")

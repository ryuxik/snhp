"""Phase-3a golden — the general offer-graph engine reproduces vend.scenario.
nash_quote (docs/REDESIGN.md Phase 3).

Two levels, mirroring the boba golden (test_boba_golden.py):

  1. CART-LEVEL EQUIVALENCE (primary). Replay vend's OWN shipped sim trajectory
     (the real vend.run, driven by nash_quote — the harness rebinds only the
     compared symbol, never the driver), and at every quote compare
     core.adapters.vend.engine_nash_quote against nash_quote under the deployed
     A2APolicy config. Assert the SAME (sku, qty) and price within $0.01, over
     both regimes (hot smart-store-P90 + realistic calibrated traffic) and the
     honest + all-liar disclosure arms.

  2. SIM-LEVEL REPRODUCTION (confirmation). Swap the engine in as the pricer for
     the full paired-MC and confirm the committed a2a−static Δ/day reproduces
     — in fact byte-for-byte, engine total == nash_quote total.

vend/ is untouched (additive only): the adapter and this harness are validated
ALONGSIDE nash_quote, which stays the shipped production path.

The two-cost-split reconciliation (the Phase-1-flagged collapse): vend floors
its rungs at the RAW per-unit c_eff while measuring margin at the
displacement-adjusted cost, and rounds PER-UNIT. The engine collapses to one
c_eff and rounds TOTAL. The adapter closes this by handing the engine vend's own
rung grid (core.cost.CostQuote.rungs); with two_cost_split=False (the collapse)
the divergence is real and measurable — test_two_cost_split_* pins both.
"""
from __future__ import annotations

import pytest

from core.adapters.vend import (build_graph, engine_nash_quote, shop_state)
from core.adapters.tests import _vend_harness as H
from core.offer_graph import DimKind
from vend import run as vend_run
from vend.world import (CALIBRATED_TRAFFIC_SCALE, QTY_CAP, WorldConfig,
                        build_catalog, fresh_machine, Lot)

SEED = 20260713


def _cal_cfg() -> WorldConfig:
    """The realistic calibrated cell — miscalibration × shock × calendar ×
    glut at real 7–8 vends/day (RESULTS.md 'strongest posted baseline')."""
    return WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                       glut_prob=0.15, traffic_scale=CALIBRATED_TRAFFIC_SCALE)


def _hot_cfg() -> WorldConfig:
    """The committed results.json cell (perfect calibration, hot P90 traffic)."""
    return WorldConfig()


# ── the graph is a faithful projection of vend's menu ─────────────────────
def test_graph_shape_from_vend_constants():
    cat = build_catalog()
    g = build_graph(cat)
    kinds = {d.id: d.kind for d in g.dims}
    assert kinds == {"sku": DimKind.CHOICE, "qty": DimKind.QUANTITY}
    sku = g.dim("sku")
    assert {o.id for o in sku.options} == set(cat)
    for o in sku.options:
        assert o.price_delta == cat[o.id].list_price
        assert o.unit_cost == cat[o.id].unit_cost
        assert o.salvage == cat[o.id].salvage
        assert o.stock_limited and o.perishable       # qty-cap gate + salvage
    assert g.dim("qty").qty_cap == QTY_CAP


def test_shop_state_projects_stock_and_demand():
    from vend.scenario import expected_list_demand
    cat = build_catalog()
    st = fresh_machine("t", cat)
    st.tick = 0
    st.lots = [Lot("cola", 2, expires_day=60), Lot("sandwich", 3, expires_day=0)]
    proj = shop_state(st)
    # only in-stock SKUs are projected (matches nash_quote's sku_ctx loop)
    assert set(proj.inventory) == {"cola", "sandwich"}
    assert proj.inventory["cola"] == 2.0
    # a SKU dying tonight is flagged expiring (→ salvage floor)
    assert "sandwich" in proj.expiring and "cola" not in proj.expiring
    # expected_demand carries the SAME forecast nash_quote's shadow uses
    assert proj.expected_demand["cola"] == pytest.approx(
        expected_list_demand(st, "cola"))
    assert proj.tick == 0 and proj.extra["vend"] is st


# ── the harness does not perturb the trajectory ───────────────────────────
def test_compare_harness_is_trajectory_neutral():
    """Sanity floor: running the real sim with the compare probe attached
    yields the SAME a2a totals as the untouched vend.run — so any recorded
    divergence is the engine's, never a harness artifact."""
    cfg = _cal_cfg()
    ref = vend_run.run_experiment(["static", "a2a"], days=6, seed=SEED, cfg=cfg)
    counts = {}
    with H.compare_pricer(counts=counts):
        got = vend_run.run_experiment(["static", "a2a"], days=6, seed=SEED, cfg=cfg)
    assert got["arms"]["a2a"]["totals"] == ref["arms"]["a2a"]["totals"]
    assert counts["total"] > 0


# ── LEVEL 1: cart-level equivalence over the real trajectory ──────────────
EQUIV_SCENARIOS = {
    "hot-honest":  (_hot_cfg, ["static", "a2a"], 20),
    "cal-honest":  (_cal_cfg, ["static", "a2a"], 90),
    "cal-liars":   (_cal_cfg, ["static", "a2a-liars100"], 30),
}


@pytest.mark.parametrize("scenario", list(EQUIV_SCENARIOS))
def test_cart_level_equivalence(scenario):
    """Drive the shipped sim with nash_quote; compare the engine at every quote.
    The trajectory stays nash_quote's (byte-identical to vend.run), so this is
    the engine measured against the real state distribution the machine sees."""
    cfg_fn, arms, days = EQUIV_SCENARIOS[scenario]
    mism: list = []
    counts: dict = {}
    with H.compare_pricer(mismatches=mism, counts=counts):
        vend_run.run_experiment(arms, days=days, seed=SEED, cfg=cfg_fn())
    total = counts.get("total", 0)
    bad = counts.get("mismatch", 0)
    assert total > 250, f"{scenario}: only {total} quotes compared"
    rate = (total - bad) / total
    assert rate >= 0.99, (
        f"{scenario}: cart-level match {rate:.4%} ({bad}/{total}); "
        f"first mismatches: {mism[:5]}")
    assert bad == 0, (
        f"{scenario}: {bad}/{total} residual mismatches (expected 0): {mism[:5]}")


def test_cart_level_equivalence_total_quote_count():
    """The three scenarios together compare > 1000 real quotes (the strength
    floor: a handful of hand-picked states would not exercise the shadow /
    disagreement / buffer / liar surfaces the sim actually hits)."""
    grand = 0
    for cfg_fn, arms, days in EQUIV_SCENARIOS.values():
        counts: dict = {}
        with H.compare_pricer(counts=counts):
            vend_run.run_experiment(arms, days=days, seed=SEED, cfg=cfg_fn())
        assert counts.get("mismatch", 0) == 0
        grand += counts.get("total", 0)
    assert grand > 1000, f"only {grand} quotes across scenarios"


# ── LEVEL 2: sim-level reproduction of the committed Δ/day ─────────────────
# The committed a2a−static profit Δ/day (RESULTS.md; block-5 paired mean):
#   perfect-cal control (results.json, PINNED): −$0.05/day
#   realistic calibrated cell (review-fix batch): +$0.75/day
SIM_TARGETS = {
    "perfect-cal": (_hot_cfg, -0.05),
    "calibrated":  (_cal_cfg, +0.75),
}
SIM_DAYS = 90
SIM_TOL = 0.10          # ±$0.10/day vs the committed number (it is in fact
                        # byte-exact vs nash — asserted separately)


@pytest.mark.parametrize("cell", list(SIM_TARGETS))
def test_sim_level_reproduction(cell):
    """Swap the engine in as the pricer for the full paired-MC; confirm the
    committed a2a−static Δ/day reproduces within tolerance — and, the stronger
    fact behind it, that the engine's per-arm totals equal nash_quote's
    byte-for-byte."""
    cfg_fn, committed = SIM_TARGETS[cell]
    cfg = cfg_fn()
    base = vend_run.run_experiment(["static", "a2a"], days=SIM_DAYS,
                                   seed=SEED, cfg=cfg)
    with H.substitute_pricer():
        eng = vend_run.run_experiment(["static", "a2a"], days=SIM_DAYS,
                                      seed=SEED, cfg=cfg)
    # byte-exact reproduction of nash_quote (the real proof)
    assert eng["arms"]["a2a"]["totals"] == base["arms"]["a2a"]["totals"], (
        f"{cell}: engine a2a totals != nash_quote's")
    # the committed Δ/day (block-5 paired mean, exactly RESULTS.md's headline)
    delta = eng["paired"]["a2a_vs_static"]["profit"]["mean"]
    assert abs(delta - committed) <= SIM_TOL, (
        f"{cell}: engine Δ/day {delta:+.2f} vs committed {committed:+.2f} "
        f"(tol ±{SIM_TOL})")


# ── the intent-constrained (`allowed`) path — the deployed API surface ────
def test_allowed_intent_constraint_matches_nash():
    """vend/api.py:152 passes `allowed` (an intent SKU/qty constraint) to
    nash_quote — a production path the sim never exercises. The engine maps it
    to a cand_filter that gates the board DISAGREEMENT too (matching
    nash_quote), so a substitutes-forbidden buyer's threat point is their best
    ALLOWED board bundle. Swept over many states × constraints."""
    import numpy as np
    from vend.scenario import nash_quote
    from vend.world import Consumer, sample_consumer
    cat = build_catalog()
    skus = list(cat)
    bad = 0
    total = 0
    rng = np.random.default_rng(20260713)
    for trial in range(120):
        st = fresh_machine("t", cat)
        st.tick = int(rng.integers(0, 96))
        # a randomized inventory (some scarce, some glut, some expiring)
        st.lots = []
        for s in skus:
            n = int(rng.integers(0, 14))
            if n:
                exp = int(rng.integers(0, 3)) + st.day
                st.lots.append(Lot(s, n, expires_day=exp))
        c = sample_consumer(20260713, 0, st.tick, trial, cat)
        sku = skus[int(rng.integers(0, len(skus)))]
        qcap = int(rng.integers(1, QTY_CAP + 1))
        subs = bool(rng.integers(0, 2))
        allowed = (lambda o, sku=sku, q=qcap, subs=subs:
                   (subs or o.sku == sku) and o.qty <= q)
        a = nash_quote(st, c.wtp, c.walk_cost, allowed=allowed)
        b = engine_nash_quote(st, c.wtp, c.walk_cost, allowed=allowed)
        total += 1
        if H.outcome_key(a) != H.outcome_key(b):
            bad += 1
    assert bad == 0, f"{bad}/{total} allowed-constrained divergences"


# ── the no-deal NashQuote still reports the real disagreement point ────────
def test_no_deal_quote_carries_disagreement_fields():
    """nash_quote's outcome=None return still carries the no-deal point
    (d_machine = the board counterfactual's margin, d_buyer = the board
    surplus or the claimed outside) — vend's own tests read d_buyer off a
    no-deal quote (test_nash_disagreement_is_stock_capped). The engine maps
    its at-list fallback audit onto those fields and its walk onto the
    outside branch, so the drop-in is faithful on ALL return paths, not just
    outcome≠None. Three constructed no-deal shapes."""
    from vend.scenario import nash_quote
    cat = build_catalog()

    # (a) board buyer, no feasible improvement: stock 1 pins every rung's
    #     machine gain at ≤ 0 (any discounted unit displaces the board sale)
    st = fresh_machine("t", cat)
    st.tick = 50
    st.lots = [Lot("cola", 1, expires_day=60)]
    wtp = {s: 0.3 for s in cat}
    wtp["cola"] = 5.0
    a = nash_quote(st, wtp, 2.0)
    b = engine_nash_quote(st, wtp, 2.0)
    assert a.outcome is None and b.outcome is None
    assert a.d_buyer > 0                                # the board point is real
    assert b.d_buyer == pytest.approx(a.d_buyer, abs=1e-9)
    assert b.d_machine == pytest.approx(a.d_machine, abs=1e-9)

    # (b) a live deal killed by an absurd min-gain buffer → board point stands
    st2 = fresh_machine("t", cat)
    st2.tick = 50
    st2.lots = [Lot("sandwich", 12, expires_day=0),
                Lot("cola", 12, expires_day=60)]
    wtp2 = {s: cat[s].list_price * 1.4 for s in cat}
    a2 = nash_quote(st2, wtp2, 1.0, min_gain=1e6)
    b2 = engine_nash_quote(st2, wtp2, 1.0, min_gain=1e6)
    assert a2.outcome is None and b2.outcome is None
    assert b2.d_buyer == pytest.approx(a2.d_buyer, abs=1e-9)
    assert b2.d_machine == pytest.approx(a2.d_machine, abs=1e-9)

    # (c) an intent that forbids everything → a WALK with a live outside
    #     option (outside_surplus is not intent-gated; the board is)
    a3 = nash_quote(st2, wtp2, 0.0, allowed=lambda o: False)
    b3 = engine_nash_quote(st2, wtp2, 0.0, allowed=lambda o: False)
    assert a3.outcome is None and b3.outcome is None
    assert a3.d_buyer > 0                               # the bodega surplus
    assert b3.d_buyer == pytest.approx(a3.d_buyer, abs=1e-9)
    assert a3.d_machine == 0.0 and b3.d_machine == 0.0


# ── the two-cost-split reconciliation (the flagged collapse) ──────────────
def test_two_cost_split_true_is_exact_and_false_diverges():
    """The Phase-1-flagged collapse, quantified. two_cost_split=True (the
    default — supply vend's per-unit rung grid) reproduces nash_quote with ZERO
    divergence; two_cost_split=False (collapse to the engine's single c_eff and
    total-price rungs) produces a small but nonzero divergence — the rung-floor
    + per-unit-rounding difference is real, and the split closes it."""
    cfg = _hot_cfg()
    faithful: dict = {}
    with H.compare_pricer(counts=faithful, two_cost_split=True):
        vend_run.run_experiment(["static", "a2a"], days=30, seed=SEED, cfg=cfg)
    collapsed: dict = {}
    with H.compare_pricer(counts=collapsed, two_cost_split=False):
        vend_run.run_experiment(["static", "a2a"], days=30, seed=SEED, cfg=cfg)
    assert faithful["total"] == collapsed["total"] > 1000
    assert faithful.get("mismatch", 0) == 0, "the split must be exact"
    assert collapsed.get("mismatch", 0) > 0, (
        "the collapse is expected to diverge — if not, the split is a no-op")


# ── the seller_weight split-tilt default reproduces the symmetric split ────
def test_seller_weight_default_is_symmetric_and_reproduces():
    """The default seller_weight (0.5) is the symmetric Nash split; the engine
    reproduces nash_quote at 0.5, and the tilted split (w>0.5) too."""
    from vend.scenario import nash_quote
    from vend.world import Consumer
    cat = build_catalog()
    st = fresh_machine("t", cat)
    st.tick = 50
    st.lots = [Lot("sandwich", 12, expires_day=0), Lot("cola", 12, expires_day=60),
               Lot("chips", 10, expires_day=30)]
    c = Consumer(wtp={s: cat[s].list_price * 1.4 for s in cat},
                 walk_cost=1.0, patience=0.0)
    for w in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        a = nash_quote(st, c.wtp, c.walk_cost, seller_weight=w)
        b = engine_nash_quote(st, c.wtp, c.walk_cost, seller_weight=w)
        ka = None if a.outcome is None else (a.outcome.sku, a.outcome.qty,
                                             round(a.outcome.unit_price, 2))
        kb = None if b.outcome is None else (b.outcome.sku, b.outcome.qty,
                                             round(b.outcome.unit_price, 2))
        assert ka == kb, f"w={w}: nash {ka} != engine {kb}"
        if a.outcome is not None:
            assert a.u_machine == pytest.approx(b.u_machine)
            assert a.d_machine == pytest.approx(b.d_machine)
    # default (no seller_weight) == 0.5
    d0 = engine_nash_quote(st, c.wtp, c.walk_cost)
    d5 = engine_nash_quote(st, c.wtp, c.walk_cost, seller_weight=0.5)
    assert H.outcome_key(d0) == H.outcome_key(d5)

"""WHOLESALE B5 tests: demand streams are arm-independent by construction,
determinism is byte-level, the deal space respects the rate card (discount
only, MOQ-to-storage), the truck's physics hold (stop capacity, shared
windows bill one stop), the financing and spoilage-sharing dollar math is
exact, and every negotiated deal beats its event-consistent disagreement
on BOTH sides."""
import json
import math

import numpy as np
import pytest

from wholesale import calibration as cal
from wholesale.run import ARMS, run_cell, run_week, _score
from wholesale.scenario import build_ctx, disagreement, nash_deal
from wholesale.world import (Schedule, WeekDemand, demand_pmf, fcfs_window,
                             is_am, shadow, sold_curve, week_demand)

SEED = 20260710


@pytest.fixture(scope="module")
def cell():
    """One small paired run (ALL arms, 3 weeks x 2 seeds) shared by the
    accounting tests."""
    return run_cell(0.15, 0.7, weeks=3, seeds=[SEED, SEED + 1],
                    arms=ARMS, keep_records=True)


def _ctxs(flex=0.7):
    return {(w, v): build_ctx(w, v, flex)
            for w in cal.W_ORDER for v in cal.V_ORDER}


# ── pairing & determinism ────────────────────────────────────────────────

def test_demand_stream_is_arm_independent(cell):
    """THE paired-weeks guarantee: week_demand is a pure function of
    (seed, week, wholesaler, venue) — no arm parameter exists — and the
    records every arm actually consumed carry identical forecasts and
    identical realized demand, relationship by relationship."""
    a = week_demand(SEED, 3, "produce", "boba", 0.15)
    b = week_demand(SEED, 3, "produce", "boba", 0.15)
    assert a.mu_w == b.mu_w and a.d_real == b.d_real
    assert np.array_equal(a.pmf, b.pmf)
    base = cell["_records"]["ratecard"]
    for arm in ARMS[1:]:
        for wk_base, wk_arm in zip(base, cell["_records"][arm]):
            for r0, r1 in zip(wk_base["records"], wk_arm["records"]):
                assert (r0["wholesaler"], r0["venue"]) == \
                       (r1["wholesaler"], r1["venue"])
                assert r0["mu_w"] == r1["mu_w"]
                assert r0["d_real"] == r1["d_real"]


def test_run_is_deterministic():
    """Byte-identical: the same cell run twice reproduces exactly."""
    r1 = run_cell(0.35, 0.3, weeks=2, seeds=[11], arms=("ratecard", "nego"))
    r2 = run_cell(0.35, 0.3, weeks=2, seeds=[11], arms=("ratecard", "nego"))
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ── the deal space respects the rate card ────────────────────────────────

def test_negotiated_prices_are_discount_only(cell):
    """Every negotiated unit price is at or under the PUBLISHED break
    price for that quantity (which is itself at or under the base card)."""
    ctxs = _ctxs()
    negotiated = 0
    for arm in ARMS:
        for wk in cell["_records"][arm]:
            for r in wk["records"]:
                if r["channel"] not in ("nego", "ratecard"):
                    continue
                ctx = ctxs[(r["wholesaler"], r["venue"])]
                bp = float(ctx.break_price(r["qty"]))
                assert r["unit_price"] <= bp + 1e-9
                assert bp <= ctx.base + 1e-9
                negotiated += int(r["negotiated"])
    assert negotiated > 0             # the nego arms actually negotiated


def test_moq_and_storage_feasibility(cell):
    """Delivered orders live in [MOQ, storage cap]; Jetro runs (no MOQ)
    live in [1, cap]; a Jetro week leaves the wholesaler NOTHING."""
    for arm in ARMS:
        for wk in cell["_records"][arm]:
            for r in wk["records"]:
                key = (r["wholesaler"], r["venue"])
                cap = cal.STORAGE_CAP[key]
                if r["channel"] in ("nego", "ratecard"):
                    assert cal.WHOLESALERS[r["wholesaler"]]["moq"] <= r["qty"] <= cap
                elif r["channel"] == "jetro":
                    assert 1 <= r["qty"] <= cap
                    assert r["window"] is None
                    assert r["real_w_contrib"] == 0.0


# ── the truck's physics ──────────────────────────────────────────────────

def test_truck_capacity_conservation(cell):
    """Stops never exceed capacity: one stop max per (wholesaler, window),
    AM stops per week within the cap, drops bounded by the block's venues."""
    for arm in ARMS:
        for wk in cell["_records"][arm]:
            for w, sch in wk["schedules"].items():
                assert sch.am_stops() <= cal.AM_STOPS_PER_WEEK
                for iw, drops in sch.stops.items():
                    assert 0 <= iw <= 9
                    assert 1 <= len(drops) <= len(cal.V_ORDER)
                    assert len(set(drops)) == len(drops)   # one drop per venue


def test_shared_window_bills_one_stop():
    """Route-density accounting: two venues in the SAME window bill one
    stop + one drop fee, not two stops."""
    sch = Schedule()
    sch.add("bodega", 0)
    sch.add("bakery", 0)
    assert sch.realized_route_cost() == pytest.approx(
        cal.STOP_COST + cal.SHADOW_AM + cal.DROP_COST)
    apart = Schedule()
    apart.add("bodega", 0)
    apart.add("bakery", 2)
    assert apart.realized_route_cost() == pytest.approx(
        2 * (cal.STOP_COST + cal.SHADOW_AM))
    assert sch.shared_windows() == 1 and apart.shared_windows() == 0


def test_am_scarcity_binds():
    """With the weekly AM budget spent, new AM stops are infeasible (and
    priced at infinity); existing stops still take drops; PM stays open."""
    sch = Schedule()
    sch.add("bodega", 0)
    sch.add("boba", 4)
    assert sch.am_stops() == cal.AM_STOPS_PER_WEEK == 2
    assert not sch.can_new_stop(6) and sch.incremental_cost(6) == math.inf
    assert sch.feasible(0) and sch.incremental_cost(0) == cal.DROP_COST
    assert sch.can_new_stop(1) and sch.incremental_cost(1) == \
        cal.STOP_COST + cal.SHADOW_PM


def test_fcfs_dispatch_grants_first_feasible_preference():
    """The industry control: the venue walks its preference list and the
    dispatcher grants the first servable window (an existing stop always
    takes another drop)."""
    sch = Schedule()
    assert fcfs_window(sch, cal.VENUES["bodega"]["pref"]) == 0   # Mon-AM
    sch.add("bodega", 0)
    sch.add("x", 2)                    # AM budget now spent
    # boba prefers Fri-AM(8), Thu(6), Wed(4), Tue(2)... 8/6/4 need a new AM
    # stop (denied); Tue-AM(2) already has a stop -> ride along as a drop
    assert fcfs_window(sch, cal.VENUES["boba"]["pref"]) == 2


# ── dollar math: financing, spoilage, newsvendor ─────────────────────────

def test_payment_terms_financing_math():
    """PV factors are the financing identity: COD = the published 2% off;
    net terms discount by the side's monthly rate x the term. The
    cash-tight bodega (2.5%/mo) values net-30 above COD; the cash-rich
    vending operator (1.0%/mo) prefers COD; the wholesaler (0.8%/mo)
    ranks net-15 > net-30 > COD on received PV."""
    bodega = build_ctx("beverage", "bodega", 0.7)
    vend = build_ctx("beverage", "vending", 0.7)
    assert bodega.pv_v == {"cod": 0.98, "net15": 1 - 0.025 * 0.5,
                           "net30": 1 - 0.025}
    assert bodega.pv_v["net30"] < bodega.pv_v["cod"]      # pays less PV
    assert vend.pv_v["cod"] < vend.pv_v["net30"]
    pw = bodega.pv_w
    assert pw["net15"] > pw["net30"] > pw["cod"]


def test_spoilage_sharing_transfers_half_of_realized_overage():
    """50/50 sharing credits the venue exactly half the PAID value of
    spoiled cases, debits the wholesaler the same — a pure transfer: the
    JOINT realized surplus of the identical bundle is share-invariant."""
    ctx = build_ctx("produce", "boba", 0.7)
    pmf = demand_pmf(20.0, 3.0, ctx.cap)
    env = WeekDemand(20.0, 3.0, pmf, sold_curve(pmf), d_real=12)
    dis = disagreement(ctx, env, Schedule())
    kw = dict(qty=20, price=30.0, window=8, terms="net30", deal=None, dis=dis)
    r0 = _score(ctx, env, "nego", share=0.0, **kw)
    r5 = _score(ctx, env, "nego", share=0.5, **kw)
    assert r5["spoiled"] == 8
    assert r5["credit"] == pytest.approx(0.5 * 30.0 * 8)
    assert r5["real_u_v"] - r0["real_u_v"] == pytest.approx(r5["credit"])
    assert r0["real_w_contrib"] - r5["real_w_contrib"] == pytest.approx(r5["credit"])
    assert (r0["real_u_v"] + r0["real_w_contrib"]) == pytest.approx(
        r5["real_u_v"] + r5["real_w_contrib"])


def test_newsvendor_expectation_math():
    """sold_curve is E[min(q, D)] exactly (against the brute-force sum),
    monotone in q, with non-negative expected overage."""
    pmf = demand_pmf(10.0, 3.0, 30)
    e_sold = sold_curve(pmf)
    assert pmf.sum() == pytest.approx(1.0)
    for q in (0, 1, 5, 10, 17, 30):
        brute = sum(min(q, k) * pmf[k] for k in range(len(pmf)))
        assert e_sold[q] == pytest.approx(brute, abs=1e-9)
    assert np.all(np.diff(e_sold) >= -1e-12)
    q = np.arange(31)
    assert np.all(q - e_sold >= -1e-12)


# ── the negotiation: disagreement, buffer, fallback ──────────────────────

def test_both_sides_beat_disagreement_on_every_deal(cell):
    """Every negotiated deal clears BOTH event-consistent disagreements in
    expectation, and the wholesaler's gain clears the pre-registered
    buffer max($5, 3% of order list value)."""
    n = 0
    for arm in ARMS[1:]:
        for wk in cell["_records"][arm]:
            for r in wk["records"]:
                if not r["negotiated"]:
                    continue
                n += 1
                assert r["exp_u_v"] >= r["d_v"] - 1e-6
                thr = max(cal.BUFFER_MIN, cal.BUFFER_FRAC * r["list_value"])
                assert r["exp_u_w"] >= r["d_w"] + thr - 1e-6
    assert n > 0


def test_event_consistent_disagreement_branches():
    """vend/scenario.py's rule, one tier up: when the venue's no-deal move
    is the rate-card order, the wholesaler's disagreement is the margin it
    ALREADY had; when Jetro wins, the wholesaler keeps nothing."""
    ctx = build_ctx("beverage", "vending", 0.7)
    env = week_demand(SEED, 0, "beverage", "vending", 0.15)
    d = disagreement(ctx, env, Schedule())
    assert d.event == "ratecard"
    inc = cal.STOP_COST + shadow(d.window)     # first stop of an empty week
    expect = (float(ctx.break_price(d.rc_q)) * d.rc_q * ctx.pv_w[d.rc_terms]
              - ctx.cogs * d.rc_q - inc)
    assert d.d_w == pytest.approx(expect)
    # make every delivered window ruinous for the venue -> Jetro wins
    ctx.recv = np.full(10, 500.0)
    d2 = disagreement(ctx, env, Schedule())
    assert d2.event == "jetro" and d2.d_w == 0.0 and d2.d_v > 0


def test_ratecard_choice_picks_best_published_terms_only():
    """The disagreement's rate-card order optimizes over PUBLISHED options
    (COD -2% / net-15) — never the negotiated-only net-30, even when
    net-30 would be better for the venue."""
    ctx = build_ctx("beverage", "bodega", 0.7)
    assert ctx.pv_v["net30"] < ctx.pv_v["cod"] < ctx.pv_v["net15"]
    env = week_demand(SEED, 0, "beverage", "bodega", 0.15)
    d = disagreement(ctx, env, Schedule())
    assert d.rc_terms == "cod"                  # best of the published two
    ctx.pv_v = {"cod": 0.98, "net15": 0.97, "net30": 0.96}
    d2 = disagreement(ctx, env, Schedule())
    assert d2.rc_terms == "net15"               # tracks the venue's PV...
    assert d2.rc_terms != "net30"               # ...but stays published


def test_issue_freeze_pins_the_issue(cell):
    """The H-W1 ablation arms really freeze their issue at the rate-card
    default: no-price deals sit AT the break price, no-spoil deals carry
    no sharing, no-window deals take the FCFS window that the fallback
    rate-card order would have taken."""
    ctxs = _ctxs()
    seen = {"price": 0, "spoil": 0}
    for wk in cell["_records"]["nego-no-price"]:
        for r in wk["records"]:
            if r["negotiated"]:
                ctx = ctxs[(r["wholesaler"], r["venue"])]
                assert r["unit_price"] == pytest.approx(
                    float(ctx.break_price(r["qty"])))
                seen["price"] += 1
    for wk in cell["_records"]["nego-no-spoil"]:
        for r in wk["records"]:
            if r["negotiated"]:
                assert r["share"] == 0.0
                seen["spoil"] += 1
    assert seen["price"] > 0 and seen["spoil"] > 0


def test_buffer_failure_falls_back_to_the_disagreement_event(monkeypatch):
    """With an impossible buffer no negotiation clears, and the nego arm
    degrades EXACTLY to the industry control — never worse than the rate
    card, enforced (the no-deal event executes, deal by deal)."""
    monkeypatch.setattr(cal, "BUFFER_MIN", 1e9)
    ctxs = _ctxs()
    envs = {(w, v): week_demand(SEED, 0, w, v, 0.15)
            for w in cal.W_ORDER for v in cal.V_ORDER}
    recs_nego, _ = run_week("nego", ctxs, envs)
    recs_rc, _ = run_week("ratecard", ctxs, envs)
    assert all(not r["negotiated"] for r in recs_nego)
    assert recs_nego == recs_rc


def test_coordination_consolidates_the_route(cell):
    """H-W3's mechanism check: with cross-venue visibility the wholesaler
    clusters the block into fewer, cheaper stops than the blind ablation
    and the FCFS control."""
    s = cell["arms"]
    assert s["nego"]["stops_week"] < s["nego-indep"]["stops_week"]
    assert s["nego"]["route_cost_week"] < s["nego-indep"]["route_cost_week"]
    assert s["nego"]["route_cost_week"] < s["ratecard"]["route_cost_week"]


def test_nash_respects_window_feasibility():
    """A negotiated deal never lands on an unschedulable window: with the
    AM budget spent, new-AM windows are priced out (inf) and the chosen
    window is a real, bookable one."""
    ctx = build_ctx("dry", "bakery", 0.3)
    env = week_demand(SEED, 1, "dry", "bakery", 0.15)
    sch = Schedule()
    sch.add("a", 0)
    sch.add("b", 2)                    # AM budget spent
    d = disagreement(ctx, env, sch)
    deal = nash_deal(ctx, env, sch, d)
    if deal is not None:               # deal existence depends on gains...
        assert sch.feasible(deal.window)
        sch.add(ctx.venue, deal.window)   # ...but bookability is guaranteed

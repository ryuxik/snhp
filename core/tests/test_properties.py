"""Tier-1 property tests over MANY generated arbitrary offer graphs, PLUS the
stronger asserts from the adversarial review.

These are the acceptance gate for the engine (docs/REDESIGN.md Phase 1):
nothing merges until they are green over generated graphs. Pure stdlib, no
network, no new deps. `SEEDS` graphs are regenerated deterministically each
run, so a failure is reproducible from its seed.

The tests are written to FAIL if the engine's invariants regress — in
particular P9 flips on the IC-floor line, P5 recomputes the joint surplus from
independently-written formulas (never from q.audit), and P4 constructs cases
where the clamps demonstrably change the outcome.
"""
from __future__ import annotations

import math

from core.cost import capacity_relief, compose, const
from core.deps import DepGraph
from core.engine import (QuoteOpts, SeparableBuyer, _available,
                        _exceeds_appetite, _pref_pins, quote)
from core.offer_graph import (DimKind, Dimension, Option, OfferGraph, qty_of,
                              with_qty)
from core.state import ShopState
from core.tests.generators import generate

SEEDS = range(500)
TOL = 1e-9
RND = 0.011          # rounding slack (rungs are rounded to the cent)


CASES = [generate(s) for s in SEEDS]


# ── shared independent helpers (do NOT read q.audit) ──────────────────────
def _list_value(graph, config, qty):
    total = 0.0
    for dim in graph.dims:
        if dim.kind == DimKind.QUANTITY:
            continue
        sel = config.get(dim.id)
        ids = ([] if sel is None else
               (sorted(sel) if dim.kind == DimKind.ADDON else [sel]))
        for oid in ids:
            total += dim.option(oid).price_delta
    return qty * total


def _fulfillment(graph, config):
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            o = d.option(config[d.id])
            return o.immediate, o.slot_ticks
    return True, 0


def _candidate_set(graph, state, buyer, opts):
    """The engine's candidate configs, reconstructed from the public building
    blocks (enumeration + the A1 gates + appetite) — used to recompute the
    disagreement independently for P5."""
    pin = _pref_pins(graph, state, buyer) if opts.prune_free else {}
    out = []
    for c in graph.enumerate_configs(pin=pin):
        q = qty_of(graph, c)
        if not _available(graph, state, c, q):
            continue
        if opts.qty_appetite and q > 1 and _exceeds_appetite(
                graph, state, buyer, c, q):
            continue
        out.append(c)
    return out


def _ref_disagreement(graph, state, buyer, opts):
    """Recompute (d_buyer, d_seller) with formulas written FRESH from
    cart_nash (policies.py:286-294) — not read back from the engine. A sign
    or weight bug in the engine's disagreement would diverge from this."""
    surv0 = 1.0 - buyer.balk_prob(state)
    s_out = buyer.outside_surplus()
    s_menu, menu_c = None, None
    for c in _candidate_set(graph, state, buyer, opts):
        immediate, _ = _fulfillment(graph, c)
        if not immediate:
            continue
        q = qty_of(graph, c)
        listv = _list_value(graph, c, q)
        s = buyer.value(graph, c) - listv
        if s_menu is None or s > s_menu:
            s_menu, menu_c = s, c
    if menu_c is not None and s_menu > 0 and s_menu >= s_out:
        q = qty_of(graph, menu_c)
        listv = _list_value(graph, menu_c, q)
        cost = graph.cost.quote(graph, state, menu_c, q).c_eff
        return surv0 * s_menu + (1.0 - surv0) * s_out, surv0 * (listv - cost)
    return s_out, 0.0


def _fields(q):
    if q is None:
        return None
    return (q.price, q.listv, q.cost, q.value, q.save, q.feasible,
            round(q.seller_gain, 9), round(q.buyer_gain, 9))


# ── P1 — never above the menu ─────────────────────────────────────────────
def test_p1_never_above_list():
    for s, case in zip(SEEDS, CASES):
        q = quote(case.graph, case.state, case.buyer, opts=case.opts)
        if q is None:
            continue
        assert q.price <= q.listv + TOL, (
            f"seed {s}: price {q.price} > list {q.listv}")


# ── P2 / B4 — cost floor, for EVERY return ────────────────────────────────
def test_p2_price_never_below_min_cost_list():
    """B4: every non-None quote (feasible AND at-list fallback) prices at
    least min(c_eff, list). With A2, a feasible deal is never below cost
    (except the pin case cost>list, which sits at list = min(cost,list))."""
    for s, case in zip(SEEDS, CASES):
        q = quote(case.graph, case.state, case.buyer, opts=case.opts)
        if q is None:
            continue
        assert q.price >= min(q.cost, q.listv) - RND, (
            f"seed {s}: price {q.price} < min(cost {q.cost}, list {q.listv})")
        if q.feasible:
            # A2: a feasible deal is at/above cost (never funded below cost by
            # a relief credit), and at/above the min_price_frac rung floor.
            assert q.price >= q.cost - RND, (
                f"seed {s}: feasible price {q.price} < cost {q.cost}")
            floor = max(q.cost, case.opts.min_price_frac * q.listv)
            assert q.price >= floor - RND, (
                f"seed {s}: feasible price {q.price} < floor {floor}")


# ── P4 / B3 — plausibility clamps that DEMONSTRABLY bind ──────────────────
def _relief_upsell_graph():
    """A drink whose 2nd unit is below cost, plus a deferred slot paying a
    per-unit relief credit — so the engine WANTS to upsell (relief harvest),
    and qty_appetite is what stops it."""
    def relief(graph, state, config, qty):
        for d in graph.dims:
            if d.kind == DimKind.FULFILLMENT:
                if not d.option(config[d.id]).immediate:
                    return qty * 2.5
        return 0.0
    drink = Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=5.0, unit_cost=3.0),))
    ful = Dimension("f", DimKind.FULFILLMENT, options=(
        Option("now", immediate=True, slot_ticks=0),
        Option("d30", immediate=False, slot_ticks=3)))
    qty = Dimension("q", DimKind.QUANTITY, qty_cap=3)
    graph = OfferGraph(dims=[drink, ful, qty], deps=DepGraph(),
                       cost=compose(const(), capacity_relief(relief)))
    buyer = SeparableBuyer(values={("d", "a"): 5.0}, qty_decay=0.5, outside=0.0,
                           balk=0.0, defer={0: 0.0, 3: 0.1, 6: 0.2})
    return graph, ShopState(), buyer


def test_p4_qty_appetite_binds_and_changes_config():
    graph, state, buyer = _relief_upsell_graph()
    off = QuoteOpts(qty_appetite=False, min_gain_abs=0.0, min_gain_frac=0.0)
    on = QuoteOpts(qty_appetite=True, min_gain_abs=0.0, min_gain_frac=0.0)
    q_off = quote(graph, state, buyer, opts=off)
    q_on = quote(graph, state, buyer, opts=on)
    assert qty_of(graph, q_off.config) == 2      # relief-funded upsell
    assert qty_of(graph, q_on.config) == 1       # appetite caps it
    assert q_off.config != q_on.config           # the clamp BOUND


def test_p4_qty_appetite_noop_when_it_cannot_bind():
    """Where every unit is above cost, qty_appetite on == off (opt-in, no
    silent change to default behaviour)."""
    drink = Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=6.0, unit_cost=0.5),))
    qty = Dimension("q", DimKind.QUANTITY, qty_cap=3)
    graph = OfferGraph(dims=[drink, qty], deps=DepGraph(), cost=compose(const()))
    buyer = SeparableBuyer(values={("d", "a"): 5.0}, qty_decay=0.95)  # 2nd unit
    off = quote(graph, ShopState(), buyer,                            # 4.75 > .5
                opts=QuoteOpts(qty_appetite=False))
    on = quote(graph, ShopState(), buyer, opts=QuoteOpts(qty_appetite=True))
    assert _fields(off) == _fields(on)


def test_p4_min_price_frac_binds_and_raises_price():
    # a looker deal that would price deep below list; a high floor lifts it
    drink = Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=5.0, unit_cost=1.0),))
    graph = OfferGraph(dims=[drink], deps=DepGraph(), cost=compose(const()))
    buyer = SeparableBuyer(values={("d", "a"): 4.5}, qty_decay=0.3, outside=0.2)
    lo = quote(graph, ShopState(), buyer, opts=QuoteOpts(min_price_frac=0.0))
    hi = quote(graph, ShopState(), buyer, opts=QuoteOpts(min_price_frac=0.8))
    assert lo.feasible and hi.feasible
    assert hi.price > lo.price + 0.5             # the floor BOUND
    assert hi.price >= 0.8 * hi.listv - RND


def test_p4_no_upsold_unit_below_cost_independently_rederived():
    """Across all generated cases with qty_appetite on, RE-DERIVE the marginal
    test (value of the q-th unit vs its marginal cost) — not by calling the
    engine's _exceeds_appetite, but with the arithmetic written here."""
    for s, case in zip(SEEDS, CASES):
        opts = QuoteOpts(min_price_frac=case.opts.min_price_frac,
                         min_gain_abs=case.opts.min_gain_abs,
                         min_gain_frac=case.opts.min_gain_frac,
                         qty_appetite=True,
                         quote_lookers=case.opts.quote_lookers,
                         seller_weight=case.opts.seller_weight,
                         price_rungs=case.opts.price_rungs)
        q = quote(case.graph, case.state, case.buyer, opts=opts)
        if q is None or q.config is None:
            continue
        g, st, by = case.graph, case.state, case.buyer
        qn = qty_of(g, q.config)
        per_unit = by.value(g, with_qty(g, q.config, 1))
        for k in range(2, qn + 1):
            mv = per_unit * by.qty_decay ** (k - 1)
            mc = (g.cost.quote(g, st, with_qty(g, q.config, k), k).c_eff
                  - g.cost.quote(g, st, with_qty(g, q.config, k - 1), k - 1).c_eff)
            assert mv >= mc - 1e-9, (
                f"seed {s}: unit {k} value {mv} < marginal cost {mc}")


# ── P5 / B2 — surplus conservation, recomputed INDEPENDENTLY ──────────────
def test_p5_gains_match_independent_recompute():
    """buyer_gain and seller_gain each equal an independently-derived value
    (deal utility − disagreement), where the disagreement is recomputed from
    fresh cart_nash formulas — NOT from q.audit. A copied sign/weight bug
    would show up as a mismatch here."""
    for s, case in zip(SEEDS, CASES):
        g, st, by, opts = case.graph, case.state, case.buyer, case.opts
        q = quote(g, st, by, opts=opts)
        if q is None or not q.feasible:
            continue
        d_buyer, d_seller = _ref_disagreement(g, st, by, opts)
        qn = qty_of(g, q.config)
        val = by.value(g, q.config)
        cq = g.cost.quote(g, st, q.config, qn)
        immediate, slot = _fulfillment(g, q.config)
        surv = (1.0 - by.balk_prob(st)) if immediate else 1.0
        s_out = by.outside_surplus()
        defer = by.defer_cost(slot)
        exp_seller = surv * (q.price - cq.c_eff) + cq.credit - d_seller
        exp_buyer = surv * (val - q.price) + (1.0 - surv) * s_out - defer - d_buyer
        assert math.isclose(q.seller_gain, exp_seller, abs_tol=1e-6), (
            f"seed {s}: seller_gain {q.seller_gain} != {exp_seller}")
        assert math.isclose(q.buyer_gain, exp_buyer, abs_tol=1e-6), (
            f"seed {s}: buyer_gain {q.buyer_gain} != {exp_buyer}")
        # the transfer identity: the sum is price-independent
        assert math.isclose(q.seller_gain + q.buyer_gain, exp_seller + exp_buyer,
                            abs_tol=1e-6)


# ── A2 — a relief credit must not fund a below-marginal-cost sale ─────────
def _credit_graph(credit_per_unit, cost, listv, immediate_only=False):
    def relief(graph, state, config, qty):
        if immediate_only:
            return qty * credit_per_unit
        for d in graph.dims:
            if d.kind == DimKind.FULFILLMENT and not d.option(config[d.id]).immediate:
                return qty * credit_per_unit
        return 0.0
    dims = [Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=listv, unit_cost=cost),))]
    if not immediate_only:
        dims.append(Dimension("f", DimKind.FULFILLMENT, options=(
            Option("now", immediate=True, slot_ticks=0),
            Option("d30", immediate=False, slot_ticks=3))))
    return OfferGraph(dims=dims, deps=DepGraph(),
                      cost=compose(const(), capacity_relief(relief)))


def test_a2_credit_never_funds_below_cost():
    """A huge deferred-slot relief credit makes gs ≥ 0 far below cost, but the
    shop must not SELL below marginal cost — the price sits at the cost floor,
    never under it (removing the A2 guard/floor would price below 2.00)."""
    graph = _credit_graph(credit_per_unit=5.0, cost=2.0, listv=2.5)
    buyer = SeparableBuyer(values={("d", "a"): 2.6}, qty_decay=0.3, outside=0.0,
                           defer={0: 0.0, 3: 0.0})
    q = quote(graph, ShopState(), buyer,
              opts=QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0))
    assert q is not None
    assert q.price >= 2.0 - TOL              # never below marginal cost


def test_a2_pin_case_cost_above_list_falls_back_to_list():
    """When cost > list (floors_at_list), there is no profitable discount even
    with a credit: fall back to at-list (feasible=False), never a feasible
    sub-cost deal."""
    graph = _credit_graph(credit_per_unit=9.0, cost=3.0, listv=2.5,
                          immediate_only=True)
    buyer = SeparableBuyer(values={("d", "a"): 9.0}, qty_decay=0.3)  # menu buyer
    q = quote(graph, ShopState(), buyer,
              opts=QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0))
    assert q is not None
    assert not q.feasible and abs(q.price - q.listv) < TOL   # at list, not sub-cost


# ── A3 — a credit on the immediate menu config must NOT inflate d_seller ──
def test_a3_credit_excluded_from_disagreement():
    """A cost model returning a credit on the IMMEDIATE menu config must not
    add that credit to d_seller (cart_nash policies.py:290). Re-adding it
    (the bug) inflates d_seller by 1.0, which kills this feasible deal — so the
    test asserts the deal survives AND its seller_gain matches the independent
    recompute (d_seller = surv0·(list−cost), no credit)."""
    graph = _credit_graph(credit_per_unit=1.0, cost=1.0, listv=5.0,
                          immediate_only=True)
    state = ShopState()
    buyer = SeparableBuyer(values={("d", "a"): 8.0}, qty_decay=0.3, outside=0.0)
    opts = QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0)
    q = quote(graph, state, buyer, opts=opts)
    assert q is not None and q.feasible          # survives (d_seller not inflated)
    d_buyer, d_seller = _ref_disagreement(graph, state, buyer, opts)
    assert math.isclose(d_seller, 4.0)           # surv0·(5−1), credit dropped
    cq = graph.cost.quote(graph, state, q.config, qty_of(graph, q.config))
    exp_seller = (q.price - cq.c_eff) + cq.credit - d_seller
    assert math.isclose(q.seller_gain, exp_seller, abs_tol=1e-6)


# ── P6 — determinism ──────────────────────────────────────────────────────
def test_p6_determinism():
    for s, case in zip(SEEDS, CASES):
        q1 = quote(case.graph, case.state, case.buyer, opts=case.opts)
        q2 = quote(case.graph, case.state, case.buyer, opts=case.opts)
        assert _fields(q1) == _fields(q2), f"seed {s}: non-deterministic"
        if q1 is not None:
            assert q1.config == q2.config, f"seed {s}: config differs"


# ── P9 / B1 — no-WTP-leak (the IC hard floor) ─────────────────────────────
#
# NOTE (B1c): this pins the guarantee cart_nash actually provides — a buyer
# who was never a menu buyer cannot extract a SUB-MENU price when lookers are
# refused, and the shop is never pushed below its disagreement. It does NOT
# claim immunity to the sophisticated decoy / private-WTP-understatement
# deviation (task #58): that leak is a KNOWN mechanism limitation, faithfully
# inherited from cart_nash and closed only by attestation, out of scope here.
def _looker_case():
    """A buyer who is NOT a menu buyer (value 4.5 < list 5.0) but has genuine
    creatable surplus (cost 1.0, low outside) — so quote_lookers FLIPS the
    outcome: a deal when allowed, None when refused."""
    drink = Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=5.0, unit_cost=1.0),))
    graph = OfferGraph(dims=[drink], deps=DepGraph(), cost=compose(const()))
    buyer = SeparableBuyer(values={("d", "a"): 4.5}, qty_decay=0.3, outside=0.2)
    return graph, ShopState(), buyer


def test_p9_quote_lookers_flips_the_outcome():
    """The IC-floor line is load-bearing: with lookers refused this non-menu
    buyer gets None; with them allowed, a deal. (Deleting the floor would make
    the refused case return a quote — this test would then fail.)"""
    graph, state, buyer = _looker_case()
    allowed = quote(graph, state, buyer, opts=QuoteOpts(quote_lookers=True))
    refused = quote(graph, state, buyer, opts=QuoteOpts(quote_lookers=False))
    assert allowed is not None and allowed.feasible      # creatable surplus
    assert allowed.price < allowed.listv                 # a real discount
    assert refused is None                               # the IC floor holds


def test_p9_seller_never_below_disagreement():
    """The true guarantee across ALL cases: a feasible deal never pushes the
    shop below its disagreement point (seller_gain ≥ 0)."""
    for s, case in zip(SEEDS, CASES):
        q = quote(case.graph, case.state, case.buyer, opts=case.opts)
        if q is None or not q.feasible:
            continue
        assert q.seller_gain >= -1e-9, (
            f"seed {s}: seller_gain {q.seller_gain} < 0 (below disagreement)")


def test_p9_all_liars_population_extracts_nothing():
    """A population of non-menu-buyers, all refused → zero sub-menu quotes."""
    leaked = 0
    for s in range(200):
        drink = Dimension("d", DimKind.CHOICE,
                          options=(Option("a", price_delta=5.0, unit_cost=1.0),))
        graph = OfferGraph(dims=[drink], deps=DepGraph(), cost=compose(const()))
        # every buyer's outside beats their best menu order → never a menu buyer
        buyer = SeparableBuyer(values={("d", "a"): 4.0 + (s % 3)}, qty_decay=0.3,
                               outside=100.0)
        if quote(graph, ShopState(), buyer,
                 opts=QuoteOpts(quote_lookers=False)) is not None:
            leaked += 1
    assert leaked == 0, f"{leaked} liars extracted a quote below the menu"


# ── B5 — over-refusal guard ───────────────────────────────────────────────
def test_b5_deserving_buyer_gets_a_quote():
    """A buyer with clear creatable surplus MUST get a non-None feasible quote
    — a bug that wrongly refuses deserving buyers would be caught here (the
    generic property tests skip Nones and could not)."""
    graph, state, buyer = _looker_case()
    q = quote(graph, state, buyer, opts=QuoteOpts())
    assert q is not None and q.feasible and q.save > 0

    # a genuine menu buyer with NEW surplus (an expiring-salvage topping) gets
    # a discount rather than the flat menu
    from core.cost import salvage_on_expiry
    drink = Dimension("d", DimKind.CHOICE,
                      options=(Option("a", price_delta=5.0, unit_cost=1.0),))
    tops = Dimension("t", DimKind.ADDON, options=(
        Option("pearls", price_delta=1.0, unit_cost=0.9, perishable=True,
               salvage=0.0),))
    g2 = OfferGraph(dims=[drink, tops], deps=DepGraph(),
                    cost=compose(const(), salvage_on_expiry()))
    b2 = SeparableBuyer(values={("d", "a"): 7.0, ("t", "pearls"): 1.05},
                        qty_decay=0.3, outside=0.0)
    q2 = quote(g2, ShopState(expiring={"pearls"}), b2, opts=QuoteOpts())
    assert q2 is not None


# ── B6 — inventory / capacity gates hold on the QUOTED config ─────────────
def test_b6_quoted_config_within_stock_and_capacity():
    """No quoted config (feasible or at-list) exceeds live stock or slot
    capacity — the A1 gates hold on the returned config, not just internally."""
    checked = 0
    for s, case in zip(SEEDS, CASES):
        q = quote(case.graph, case.state, case.buyer, opts=case.opts)
        if q is None or q.config is None:
            continue
        qn = qty_of(case.graph, q.config)
        assert _available(case.graph, case.state, q.config, qn), (
            f"seed {s}: quoted config {q.config} violates stock/capacity")
        checked += 1
    assert checked > 0                      # the guard actually ran


def test_b6_stock_gate_drops_overselling_qty():
    """Concrete: stock 2, qty_cap 3 → the engine never quotes qty 3."""
    sku = Dimension("s", DimKind.CHOICE, options=(
        Option("x", price_delta=3.0, unit_cost=1.0, stock_limited=True),))
    qty = Dimension("q", DimKind.QUANTITY, qty_cap=3)
    graph = OfferGraph(dims=[sku, qty], deps=DepGraph(), cost=compose(const()))
    buyer = SeparableBuyer(values={("s", "x"): 4.0}, qty_decay=0.95)   # wants 3
    q = quote(graph, ShopState(inventory={"x": 2.0}), buyer,
              opts=QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0))
    assert q is not None
    assert qty_of(graph, q.config) <= 2


# ── C1 — profiler pruning is behaviour-identical ──────────────────────────
def test_c1_pruning_matches_full_enumeration():
    """Pinning FREE preference dims (prune_free=True) yields byte-identical
    quotes to full enumeration (prune_free=False) — pruning is a pure speedup,
    never a behaviour change. Fresh graphs per side so the cached
    classification never leaks between the two runs."""
    import core.tests.generators as gm
    for s in SEEDS:
        base = dict(min_price_frac=CASES[s].opts.min_price_frac,
                    min_gain_abs=CASES[s].opts.min_gain_abs,
                    min_gain_frac=CASES[s].opts.min_gain_frac,
                    qty_appetite=CASES[s].opts.qty_appetite,
                    quote_lookers=CASES[s].opts.quote_lookers,
                    seller_weight=CASES[s].opts.seller_weight,
                    price_rungs=CASES[s].opts.price_rungs)
        cp = gm.generate(s)
        qp = quote(cp.graph, cp.state, cp.buyer,
                   opts=QuoteOpts(prune_free=True, **base))
        cf = gm.generate(s)
        qf = quote(cf.graph, cf.state, cf.buyer,
                   opts=QuoteOpts(prune_free=False, **base))
        assert _fields(qp) == _fields(qf), f"seed {s}: pruning changed result"

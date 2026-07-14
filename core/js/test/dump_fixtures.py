"""Serialize a DIVERSE battery of engine cases (offer graph + state + buyer +
opts + the Python engine's reference Quote) to core/js/test/fixtures.json — the
Python side of the F1 Python<->JS fidelity gate.

The JS test (fidelity.test.mjs) rebuilds each case and asserts the JS quote()
matches this reference (same chosen config, price within $0.01, same feasible
flag, same None/walk).  Regenerate whenever core/*.py or core/adapters/boba.py
changes so the fixture can't silently rot:

    REGENERATE (one-liner, from the repo root):
        python3 core/js/test/dump_fixtures.py

Two case families:
  (a) the real boba golden draws — boba's OWN shipped sim trajectory (seed
      20260710, flagship cell), replayed under all 3 deployed ship configs
      (attested / no-attest / worst), capturing every core.engine.quote the
      adapter runs.
  (b) property-style generated graphs from core/tests/generators.py — all 5 dim
      kinds, discounts + walks + fallbacks, scarcity/salvage/relief cost models.

Serialization notes (the fidelity traps this file must get right):
  * capacity_relief holds a live Python closure that JSON can't carry; both
    shipped relief fns factor as credit = g(slot_ticks, qty), so we probe the
    closure into a per-(slot_ticks, qty) TABLE — a faithful, JSON-safe form the
    JS engine reconstructs (cost.capacityReliefTable).
  * boba's search_filter is also a closure; it factorizes into an allowed-drinks
    set x allowed-topping-sets set, which we recover by probing the closure over
    the boba menu and serialize for the JS to rebuild.
  * capacity can hold -inf (a force-dropped slot); JSON/JS reject Infinity, so we
    encode non-finite numbers as sentinel strings ("-inf"/"inf"/"nan").
"""
from __future__ import annotations

import itertools
import json
import math
import os
import sys

# repo root = three levels up from core/js/test/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.cost import (_BatchEconomies, _CapacityRelief, _Const, _Salvage,
                       _Scarcity)
from core.engine import quote as core_quote
from core.offer_graph import DimKind
from core.tests.generators import generate

OUT = os.path.join(os.path.dirname(__file__), "fixtures.json")
OUT_WORLD = os.path.join(os.path.dirname(__file__), "boba_world_fixtures.json")


# ── JSON-safe primitives ───────────────────────────────────────────────────
def enc_num(x: float):
    """Encode a float JSON/JS-safely: non-finite -> sentinel string."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int,)):
        return x
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if math.isnan(x):
        return "nan"
    return x


# ── graph / cost serialization ─────────────────────────────────────────────
def _kind_name(kind: DimKind) -> str:
    return kind.name  # "CHOICE", "ADDON", ...


def ser_option(o) -> dict:
    return {
        "id": o.id,
        "label": o.label,
        "price_delta": enc_num(o.price_delta),
        "stock_limited": bool(o.stock_limited),
        "unit_cost": enc_num(o.unit_cost),
        "salvage": enc_num(o.salvage),
        "perishable": bool(o.perishable),
        "immediate": bool(o.immediate),
        "slot_ticks": int(o.slot_ticks),
    }


def ser_dim(d) -> dict:
    return {
        "id": d.id,
        "kind": _kind_name(d.kind),
        "qty_cap": int(d.qty_cap),
        "negotiable": d.negotiable.name,
        "options": [ser_option(o) for o in d.options],
    }


def _qty_cap(graph) -> int:
    for d in graph.dims:
        if d.kind == DimKind.QUANTITY:
            return int(d.qty_cap)
    return 1


def _fulfillment_dim(graph):
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            return d
    return None


def _relief_table(graph, state, fn) -> dict:
    """Probe a capacity_relief closure into {slot_ticks: {qty: credit}}.  Both
    shipped relief fns read ONLY the config's fulfillment option + qty, so a
    fulfillment-only stub config recovers the closure's output exactly."""
    ful = _fulfillment_dim(graph)
    table: dict = {}
    if ful is None:
        return table
    cap = _qty_cap(graph)
    for opt in ful.options:
        inner = {}
        for q in range(1, cap + 1):
            inner[str(q)] = enc_num(fn(graph, state, {ful.id: opt.id}, q))
        table[str(opt.slot_ticks)] = inner
    return table


def ser_cost(graph, state) -> list:
    out = []
    for c in graph.cost.components:
        if isinstance(c, _Const):
            out.append("const")
        elif isinstance(c, _Salvage):
            out.append("salvage_on_expiry")
        elif isinstance(c, _Scarcity):
            out.append("scarcity_shadow")
        elif isinstance(c, _BatchEconomies):
            out.append({"batch_economies": {"setup": enc_num(c.setup),
                                            "marginal": (None if c.marginal is None
                                                         else enc_num(c.marginal))}})
        elif isinstance(c, _CapacityRelief):
            out.append({"capacity_relief_table": _relief_table(graph, state, c.fn)})
        else:
            raise TypeError(f"unserializable cost component {c!r}")
    return out


def ser_deps(deps) -> dict:
    return {
        "valid_on": {k: sorted(v) for k, v in deps.valid_on.items()},
        "requires": {k: sorted(v) for k, v in deps.requires.items()},
        "excludes": {k: sorted(v) for k, v in deps.excludes.items()},
    }


def ser_graph(graph, state) -> dict:
    return {
        "name": graph.name,
        "dims": [ser_dim(d) for d in graph.dims],
        "deps": ser_deps(graph.deps),
        "cost": ser_cost(graph, state),
    }


# ── state / buyer / opts serialization ─────────────────────────────────────
def ser_state(state) -> dict:
    return {
        "tick": int(state.tick),
        "inventory": {k: enc_num(v) for k, v in state.inventory.items()},
        "capacity": [[int(k), enc_num(v)] for k, v in state.capacity.items()],
        "expiring": sorted(state.expiring),
        "expected_demand": {k: enc_num(v) for k, v in state.expected_demand.items()},
    }


def ser_buyer(buyer) -> dict:
    return {
        "values": [[dim_id, opt_id, enc_num(v)]
                   for (dim_id, opt_id), v in buyer.values.items()],
        "qty_decay": enc_num(buyer.qty_decay),
        "outside": enc_num(buyer.outside),
        "balk": enc_num(buyer.balk),
        "defer": [[int(k), enc_num(v)] for k, v in buyer.defer.items()],
    }


def _project_boba_filter(closure, graph, state, buyer) -> dict:
    """Recover boba's search_filter (a closure) as an allowed-drinks set x
    allowed-topping-sets set by probing it over the boba menu (the filter is a
    pure product of an independent drink check and an independent tops check)."""
    drink_ids = [o.id for o in graph.dim("drink").options]
    top_ids = [o.id for o in graph.dim("tops").options]
    allowed_drinks = [d for d in drink_ids
                      if closure(graph, state, buyer, {"drink": d, "tops": frozenset()})]
    subsets = []
    for r in range(len(top_ids) + 1):
        for combo in itertools.combinations(top_ids, r):
            subsets.append(frozenset(combo))
    probe = allowed_drinks[0] if allowed_drinks else (drink_ids[0] if drink_ids else None)
    allowed_top_sets = ([sorted(s) for s in subsets
                         if closure(graph, state, buyer, {"drink": probe, "tops": s})]
                        if probe is not None else [])
    return {"drink_dim": "drink", "tops_dim": "tops",
            "allowed_drinks": allowed_drinks, "allowed_top_sets": allowed_top_sets}


def ser_opts(opts, graph, state, buyer) -> dict:
    sf = None
    if opts.search_filter is not None:
        sf = _project_boba_filter(opts.search_filter, graph, state, buyer)
    return {
        "min_price_frac": enc_num(opts.min_price_frac),
        "min_gain_abs": enc_num(opts.min_gain_abs),
        "min_gain_frac": enc_num(opts.min_gain_frac),
        "qty_appetite": bool(opts.qty_appetite),
        "qty_appetite_scope": opts.qty_appetite_scope,
        "quote_lookers": bool(opts.quote_lookers),
        "seller_weight": enc_num(opts.seller_weight),
        "price_rungs": int(opts.price_rungs),
        "prune_free": bool(opts.prune_free),
        "search_filter": sf,
    }


# ── reference quote serialization ──────────────────────────────────────────
def ser_config(cfg) -> dict:
    out = {}
    for k, v in cfg.items():
        if isinstance(v, (frozenset, set, list, tuple)):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def ser_quote(q) -> dict | None:
    if q is None:
        return None
    return {
        "config": ser_config(q.config),
        "price": enc_num(q.price),
        "listv": enc_num(q.listv),
        "cost": enc_num(q.cost),
        "value": enc_num(q.value),
        "save": enc_num(q.save),
        "feasible": bool(q.feasible),
    }


def outcome(q) -> str:
    if q is None:
        return "walk"
    return "feasible" if q.feasible else "at-list"


def make_case(kind: str, graph, state, buyer, opts, q) -> dict:
    return {
        "kind": kind,
        "outcome": outcome(q),
        "graph": ser_graph(graph, state),
        "state": ser_state(state),
        "buyer": ser_buyer(buyer),
        "opts": ser_opts(opts, graph, state, buyer),
        "reference": ser_quote(q),
    }


# ── (b) generated property cases ───────────────────────────────────────────
def generated_cases(n_seeds: int) -> list:
    cases = []
    counts = {"walk": 0, "at-list": 0, "feasible": 0}
    for seed in range(n_seeds):
        c = generate(seed)
        q = core_quote(c.graph, c.state, c.buyer, opts=c.opts)
        case = make_case(f"gen{seed}", c.graph, c.state, c.buyer, c.opts, q)
        counts[case["outcome"]] += 1
        case["seed"] = seed
        cases.append(case)
    print(f"generated: {len(cases)} cases  {counts}")
    return cases


# ── (a) boba golden-draw cases (captured off the real shipped trajectory) ───
def boba_cases(days: int, per_config_cap: int) -> list:
    import numpy as np  # noqa: F401 (boba import chain uses it)

    import core.adapters.boba as adapter
    from boba.world import BobaConfig
    from core.adapters.tests import _boba_harness as H
    from boba.policies import CartPolicy

    SEED = 20260710
    CFG = BobaConfig(sigma_shock=0.0, flexible_share=0.35)

    def ship_policy(quote_lookers, liars=False):
        return CartPolicy(qty_appetite=True, min_price_frac=0.6,
                          quote_lookers=quote_lookers,
                          attest=not liars, liar_share=1.0 if liars else 0.0)

    ship_configs = {
        "attested": ship_policy(quote_lookers=True),
        "no-attest": ship_policy(quote_lookers=False),
        "worst": ship_policy(quote_lookers=False, liars=True),
    }

    all_cases = []
    real_quote = adapter._core_quote  # the true core.engine.quote the adapter uses

    for cfg_name, pol in ship_configs.items():
        # bucket to keep outcome diversity within the per-config cap
        buckets = {"walk": [], "at-list": [], "feasible": []}
        cap_each = max(1, per_config_cap // 3)

        def capture(graph, state, buyer, *, opts):
            q = real_quote(graph, state, buyer, opts=opts)
            oc = outcome(q)
            if len(buckets[oc]) < cap_each:
                case = make_case(f"boba-{cfg_name}", graph, state, buyer, opts, q)
                buckets[oc].append(case)
            return q

        adapter._core_quote = capture  # monkeypatch the adapter's quote call site
        try:
            for d in range(days):
                # drive the shipped trajectory with the engine adapter; every
                # cart quote routes through `capture` above
                H.run_day(pol, SEED, d, CFG, pricer=adapter.engine_cart_nash)
                if all(len(v) >= cap_each for v in buckets.values()):
                    break
        finally:
            adapter._core_quote = real_quote

        got = buckets["walk"] + buckets["at-list"] + buckets["feasible"]
        print(f"boba {cfg_name:<9}: {len(got)} cases  "
              f"{{'walk': {len(buckets['walk'])}, "
              f"'at-list': {len(buckets['at-list'])}, "
              f"'feasible': {len(buckets['feasible'])}}}")
        all_cases.extend(got)

    return all_cases


# ── boba-WORLD reference values (the arena/web/boba-world.mjs drift gate) ───
def boba_world_reference() -> dict:
    """Reference values computed from boba/world.py + boba/policies.py +
    core/adapters/boba.py, for arena/web/bobaworld_verify.test.mjs — the
    cross-check that keeps the ONE JS world module (arena/web/boba-world.mjs)
    from silently drifting off the Python source of record.

    Blocks:
      constants   — the calibration tables, asserted EXACTLY.
      erfc / sf   — math.erfc / world._sf grids (JS erfc must match ~1e-13).
      menu        — the calibration menu WITH Python's exact appeals; the JS
                    test injects these appeals so every downstream quantity
                    (ecpa, PEAK_HOURS, relief, priced carts) is comparable at
                    1e-9 independent of the inversion.
      inversions  — appeal_for_list(price, cost, ...) samples (calibration +
                    hook-menu pairs). The JS inversion bisects the identical
                    lattice but its inner argmax is machine-precision while
                    scipy minimize_scalar stops at xatol=1e-5, so agreement is
                    a few lattice steps (~1e-8 rel, asserted at 1e-6 rel).
      states      — live ShopStates with balk_prob / slot_capacity /
                    capacity_relief / pearls_expiring_excess references.
      cart_cases  — full priced carts through core/adapters/boba.py
                    engine_cart_nash (the same core-engine path the JS pages
                    run), with consumers serialized as explicit numbers.
    """
    import math

    from boba import world as W
    from boba import policies as P
    from boba.world import Batch, Consumer, ShopState, sample_consumer
    import core.adapters.boba as adapter

    consts = {
        "WTP_SIGMA": W.WTP_SIGMA, "TOP_SIGMA": W.TOP_SIGMA,
        "CROSS_DISCOUNT": W.CROSS_DISCOUNT, "GROUP_SHARE": W.GROUP_SHARE,
        "GROUP_DECAY": W.GROUP_DECAY, "SOLO_DECAY": W.SOLO_DECAY,
        "QTY_CAP": W.QTY_CAP, "OUTSIDE_MARKUP": W.OUTSIDE_MARKUP,
        "TICKS_PER_DAY": W.TICKS_PER_DAY, "OPEN_HOUR": W.OPEN_HOUR,
        "BALK_SLOPE": W.BALK_SLOPE, "BALK_LENGTH_HAZARD": W.BALK_LENGTH_HAZARD,
        "BATCH_SERVINGS": W.BATCH_SERVINGS, "BATCH_LIFE_TICKS": W.BATCH_LIFE_TICKS,
        "PEARL_RESTOCK_TRIGGER": W.PEARL_RESTOCK_TRIGGER,
        "BATCH_CLEARANCE_WINDOW": P.BATCH_CLEARANCE_WINDOW,
        "HOURLY_RATE": {str(h): v for h, v in W.HOURLY_RATE.items()},
        "HOURLY_WTP_MULT": {str(h): v for h, v in W.HOURLY_WTP_MULT.items()},
        "FLEX_DEFER": {str(k): v for k, v in W.FLEX_DEFER.items()},
        "RIGID_DEFER": {str(k): v for k, v in W.RIGID_DEFER.items()},
        "PEAK_STAFF_HOURS": list(W.PEAK_STAFF_HOURS),
    }

    erfc_grid = [[x, math.erfc(x)] for x in
                 (-3.0, -1.2, -0.3, -0.05, 0.0, 0.05, 0.3, 0.9, 1.2244,
                  1.4999, 1.5, 1.5001, 2.0, 3.3, 5.0, 8.5, 12.0)]
    sf_grid = [[x, scale, sigma, W._sf(x, scale, sigma)] for x, scale, sigma in
               ((6.25, 7.3126276093535125, 0.45), (0.85, 0.8543, 0.70),
                (7.5, 8.681353800930083 * 1.06, 0.45), (12.0, 7.0, 0.45),
                (0.0, 5.0, 0.45), (30.0, 7.0, 0.45), (1.25, 1.1503, 0.70))]

    menu = {
        "drinks": [{"name": d, "price": W.DRINK_PRICE[d], "cost": W.DRINK_COST[d],
                    "popularity": W.POPULARITY[d], "appeal": W.DRINK_APPEAL[d]}
                   for d in W.DRINK_PRICE],
        "tops": [{"name": t, "price": W.TOP_PRICE[t], "cost": W.TOP_COST[t],
                  "like_prob": W.TOP_LIKE_PROB[t], "appeal": W.TOP_APPEAL[t]}
                 for t in W.TOP_PRICE],
        "batchTop": "pearls",
    }
    world_facts = {
        "MEAN_DRINK_MARGIN": W.MEAN_DRINK_MARGIN,
        "PEAK_HOURS": list(W.PEAK_HOURS),
        "PEARL_ATTACH_LIST": P.PEARL_ATTACH_LIST,
        "ecpa": {str(h): W.expected_cups_per_arrival(h) for h in sorted(W.HOURLY_RATE)},
    }

    # inversion samples: the calibration pairs + a spread of hook-menu pairs
    inv_pairs = ([(W.DRINK_PRICE[d], W.DRINK_COST[d], W.WTP_SIGMA, True) for d in W.DRINK_PRICE]
                 + [(W.TOP_PRICE[t], W.TOP_COST[t], W.TOP_SIGMA, False) for t in W.TOP_PRICE]
                 + [(7.99, 1.85, W.WTP_SIGMA, True), (7.49, 1.65, W.WTP_SIGMA, True),
                    (5.49, 0.95, W.WTP_SIGMA, True), (8.29, 1.95, W.WTP_SIGMA, True),
                    (1.25, 0.28, W.TOP_SIGMA, False), (0.79, 0.15, W.TOP_SIGMA, False)])
    inversions = [{"price": p, "cost": c, "sigma": s, "hour_mults": hm,
                   "appeal": W.appeal_for_list(p, c, s, hm)}
                  for p, c, s, hm in inv_pairs]

    def mk_state(tick, queue, batches, scheduled):
        st = ShopState(day=0, tick=tick)
        for q in queue:
            st.queue.append(q)
        st.batches = [Batch(sv, ex) for sv, ex in batches]
        st.scheduled = dict(scheduled)
        return st

    state_specs = [
        # (tick, queue, batches[(servings, expires_tick)], scheduled) — a peak
        # lunch lull w/ expiring batch, a hot peak queue, off-peak evening,
        # near close, and the 10:00 open.
        (21, [3], [(40, 24)], {}),
        (14, [5, 2, 1], [(28, 30)], {17: 2}),
        (60, [1], [(40, 84)], {}),
        (70, [2], [(10, 71)], {}),
        (3, [], [(40, 24)], {}),
    ]
    states = []
    for tick, queue, batches, scheduled in state_specs:
        st = mk_state(tick, queue, batches, scheduled)
        states.append({
            "state": {"tick": tick, "queue": list(queue),
                      "batches": [[sv, ex] for sv, ex in batches],
                      "scheduled": {str(k): v for k, v in scheduled.items()}},
            "balk_prob": W.balk_prob(st),
            "expected_wait": W.expected_wait_minutes(st),
            "slot_capacity": {str(s): W.slot_capacity(st, tick + s) for s in (3, 6)},
            "capacity_relief": {f"{q},{s}": W.capacity_relief(st, q, s)
                                for q in range(1, W.QTY_CAP + 1) for s in (3, 6)},
            "pearls_expiring_excess": bool(P.pearls_expiring_excess(st)),
        })

    # priced carts through the SAME core-engine path the JS pages run
    def ser_consumer(c: Consumer) -> dict:
        return {"fav": c.fav, "wtp": {d: float(v) for d, v in c.wtp.items()},
                "top_wtp": {t: float(v) for t, v in c.top_wtp.items()},
                "flexible": bool(c.flexible), "qty_decay": float(c.qty_decay)}

    def ser_deal(deal) -> dict | None:
        if deal is None:
            return None
        return {"drink": deal.drink, "qty": deal.qty, "tops": sorted(deal.tops),
                "price": deal.price, "slot_ticks": deal.slot_ticks,
                "value": deal.value, "u_shop": deal.u_shop, "d_shop": deal.d_shop,
                "u_buyer": deal.u_buyer, "d_buyer": deal.d_buyer,
                "relief": deal.relief}

    SHIP = dict(qty_appetite=True, min_price_frac=0.6, quote_lookers=False)
    FULL = dict(qty_appetite=False, min_price_frac=0.0, quote_lookers=True)
    cart_cases = []
    for si, (tick, queue, batches, scheduled) in enumerate(state_specs):
        for k in range(6):
            consumer = sample_consumer(20260710, 0, tick, k)
            for opts_name, opts in (("ship", SHIP), ("full", FULL)):
                st = mk_state(tick, queue, batches, scheduled)
                deal = adapter.engine_cart_nash(st, consumer, **opts)
                cart_cases.append({"state_idx": si, "opts_name": opts_name,
                                   "opts": opts, "consumer": ser_consumer(consumer),
                                   "deal": ser_deal(deal)})

    n_deals = sum(1 for c in cart_cases if c["deal"] is not None)
    print(f"boba-world reference: {len(states)} states, {len(cart_cases)} cart cases "
          f"({n_deals} deals, {len(cart_cases) - n_deals} None)")
    return {
        "_about": "boba/world.py reference values for arena/web/bobaworld_verify"
                  ".test.mjs. Regenerate: python3 core/js/test/dump_fixtures.py",
        "constants": consts, "erfc": erfc_grid, "sf": sf_grid,
        "menu": menu, "world_facts": world_facts, "inversions": inversions,
        "states": states, "cart_cases": cart_cases,
    }


def main() -> int:
    cases = []
    cases.extend(generated_cases(n_seeds=260))
    cases.extend(boba_cases(days=12, per_config_cap=60))

    counts = {"walk": 0, "at-list": 0, "feasible": 0}
    for c in cases:
        counts[c["outcome"]] += 1

    payload = {
        "_about": "Python<->JS fidelity fixtures for the general offer-graph "
                  "engine (core/). Regenerate: python3 core/js/test/dump_fixtures.py",
        "n": len(cases),
        "outcomes": counts,
        "cases": cases,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f)
    print(f"wrote {OUT}: {len(cases)} cases  {counts}")

    with open(OUT_WORLD, "w") as f:
        json.dump(boba_world_reference(), f)
    print(f"wrote {OUT_WORLD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

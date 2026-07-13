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
    return 0


if __name__ == "__main__":
    sys.exit(main())

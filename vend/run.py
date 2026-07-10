"""VEND experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL customer stream: arrivals and consumer draws
depend only on (master_seed, day, tick, k), never on anything a policy did.
Divergence starts only at the decision each consumer makes against each
arm's prices — which is the treatment effect, isolated.

  python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr \
      --out vend/results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from vend.core import QuoteItem, make_quote, substream
from vend.policies import A2APolicy, GvrPolicy, StaticPolicy, StrongPostedPolicy
from vend.scenario import buyer_value
from vend.world import (BODEGA_MARKUP, DEFAULT_CONFIG, TICKS_PER_DAY,
                        WorldConfig, arrivals_at, build_catalog, day_state,
                        end_of_day, fresh_machine, hour_of, rate_at,
                        sample_consumer)

VEND_VERSION = 1
def _llm_arm():
    from vend.llm_arm import LLMQuotePolicy
    return LLMQuotePolicy()


ARMS = {
    "static": StaticPolicy,
    "gvr": GvrPolicy,
    "posted": StrongPostedPolicy,   # #48: choice-model, jointly-optimized posted board
    "a2a": A2APolicy,                                           # attested, all truthful
    "a2a-liars25": lambda: A2APolicy(attest=False, liar_share=0.25),
    "a2a-liars50": lambda: A2APolicy(attest=False, liar_share=0.50),
    "a2a-liars100": lambda: A2APolicy(attest=False, liar_share=1.00),
    "llm": _llm_arm,       # P2: LLM-priced machine (API spend; not byte-deterministic)
}


def run_day(policy, state, catalog, master_seed: int, day: int,
            cfg: WorldConfig = DEFAULT_CONFIG, pool=None) -> dict:
    m = {"revenue": 0.0, "cogs_sold": 0.0, "units": 0, "deals": 0,
         "arrivals": 0, "returns": 0, "stockouts": 0, "lost_to_outside": 0,
         "consumer_surplus": 0.0, "quotes": 0,
         "negotiated": 0, "neg_machine_gain": 0.0, "liar_deals": 0,
         "reg_deals": 0, "churned": 0, "active_regulars": 0}
    reg_visits = pool.visits_for_day(day) if pool is not None else {}
    return_queue: list[tuple[int, object]] = []
    # the bodega: the competitor's own posted prices (world-set, NOT a
    # function of our sticker) — loop-invariant for the whole experiment
    outside_prices = {s: catalog[s].bodega_price for s in catalog}

    # what the policy may know today: the calendar (public) + its learner
    ds = day_state(cfg, master_seed, day)
    learner = getattr(policy, "learner", None)
    if hasattr(policy, "dow_mult"):
        policy.dow_mult = ds.dow_mult
    if hasattr(policy, "traffic_scale"):
        # the operator knows their machine's own traffic level (they read
        # the meter weekly) — structural forecasts scale with it
        policy.traffic_scale = cfg.traffic_scale
    if learner:
        learner.begin_day(ds.dow_mult)

    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        due = [c for t, c in return_queue if t == tick]
        return_queue = [(t, c) for t, c in return_queue if t > tick]

        # ── persistent regulars (fairness model) visit first ──
        for reg in reg_visits.get(tick, []):
            from vend.regulars import regular_board_decision, settle_regular
            m["quotes"] += 1
            handled = False
            if getattr(policy, "mode", "board") == "intent":
                # The buyer's agent does its actual job: it discloses
                # EFFECTIVE willingness — raw value capped by the user's
                # reference tolerance ("they won't pay much above what they
                # remember without resentment"). This is what lets quotes
                # fire at ≈ reference under a high anchor.
                from types import SimpleNamespace
                wtp_eff = {s: min(reg.wtp[s], reg.ref[s] * 1.15 + 0.25)
                           for s in reg.wtp}
                shim = SimpleNamespace(wtp=wtp_eff, walk_cost=reg.walk_cost,
                                       uid=reg.uid)
                nq, _ = policy.quote_for(state, shim, 1.0)  # regulars honest
                if nq.outcome is not None:
                    o = nq.outcome
                    raw = buyer_value(reg.wtp, o.sku, o.qty) - o.qty * o.unit_price
                    fair = reg.fairness(o.sku, o.unit_price, o.qty,
                                        catalog[o.sku].list_price)
                    # mental-model switch cost, habituating with exposure
                    fric = cfg.quote_friction * (0.85 ** reg.quotes_seen)
                    reg.quotes_seen += 1
                    if raw + fair - fric > 0:
                        q = make_quote(state, policy.policy_id,
                                       seed=substream(master_seed, "rq", day, tick, reg.uid),
                                       items=[QuoteItem(o.sku, o.qty, o.unit_price,
                                                        catalog[o.sku].list_price)],
                                       why=nq.why, hour=hour_of(tick))
                        state.take(o.sku, o.qty)
                        if learner:
                            learner.sold(o.sku, o.qty)
                        m["revenue"] += q.total
                        m["cogs_sold"] += o.qty * catalog[o.sku].unit_cost
                        m["units"] += o.qty
                        m["deals"] += 1
                        m["reg_deals"] += 1
                        m["consumer_surplus"] += raw
                        settle_regular(reg, o.sku, o.unit_price, o.qty)
                        handled = True
            if not handled:
                board = policy.price_board(state)
                prices = {s: p for s, (p, _) in board.items()}
                stock = {s: state.stock(s) for s in prices}
                sku, qty, raw, faced = regular_board_decision(
                    reg, prices, stock, outside_prices)
                if sku is not None:
                    q = make_quote(state, policy.policy_id,
                                   seed=substream(master_seed, "rq", day, tick, reg.uid),
                                   items=[QuoteItem(sku, qty, faced,
                                                    catalog[sku].list_price)],
                                   why=list(board[sku][1]), hour=hour_of(tick))
                    state.take(sku, qty)
                    if learner:
                        learner.sold(sku, qty)
                    m["revenue"] += q.total
                    m["cogs_sold"] += qty * catalog[sku].unit_cost
                    m["units"] += qty
                    m["deals"] += 1
                    m["reg_deals"] += 1
                    m["consumer_surplus"] += raw
                    settle_regular(reg, sku, faced, qty)

        n_new = arrivals_at(master_seed, day, tick, cfg)
        if learner:
            # base = the KNOWN expectation (rate curve × calendar × the
            # machine's traffic level); the posterior tracks the residual
            # day shock
            learner.observe_arrivals(rate_at(tick) / 6.0 * ds.dow_mult
                                     * cfg.traffic_scale, n_new)
        consumers = ([sample_consumer(master_seed, day, tick, k, catalog, cfg)
                      for k in range(n_new)] + due)
        m["arrivals"] += n_new
        m["returns"] += len(due)

        for k, consumer in enumerate(consumers):
            m["quotes"] += 1

            # Stockout accounting: their favorite (at list) is unstocked.
            fav = max(consumer.wtp, key=lambda s: consumer.wtp[s] - catalog[s].list_price)
            if state.stock(fav) == 0:
                m["stockouts"] += 1

            o_sku, o_qty, o_s = consumer.best_bundle(outside_prices)
            s_out = (o_s - consumer.walk_cost) if o_sku else 0.0

            def settle_sale(sku, qty, unit_price, why, surplus):
                quote = make_quote(
                    state, policy.policy_id,
                    seed=substream(master_seed, "q", day, tick, k),
                    items=[QuoteItem(sku=sku, quantity=qty, unit_price=unit_price,
                                     list_price=catalog[sku].list_price)],
                    why=list(why), hour=hour_of(tick))
                state.take(sku, qty)
                if learner:
                    learner.sold(sku, qty)
                m["revenue"] += quote.total
                m["cogs_sold"] += qty * catalog[sku].unit_cost
                m["units"] += qty
                m["deals"] += 1
                m["consumer_surplus"] += surplus

            # ── intent arms: the brokered A2A negotiation happens first ──
            if getattr(policy, "mode", "board") == "intent":
                # Liar identity is a property of the PERSON (stable across
                # returns, policy-independent, paired across arms).
                liar_roll = float(np.random.default_rng(
                    substream(master_seed, "liarid", consumer.uid)).random())
                nq, lied = policy.quote_for(state, consumer, liar_roll)
                if nq.outcome is not None:
                    o = nq.outcome
                    s_true = buyer_value(consumer.wtp, o.sku, o.qty) \
                        - o.qty * o.unit_price
                    # Rational acceptance: the negotiated deal must beat the
                    # buyer's BEST alternative — the bodega AND the sticker
                    # board they could just buy from ("never worse UX than
                    # static" is enforced here, not assumed).
                    b_prices = {s: catalog[s].list_price for s in catalog
                                if state.stock(s) > 0}
                    b_stock = {s: state.stock(s) for s in b_prices}
                    _, _, s_board = consumer.best_bundle(b_prices, b_stock)
                    # transients are perpetual first-timers: full switch cost
                    if (s_true - cfg.quote_friction > 0
                            and s_true - cfg.quote_friction >= max(s_out, s_board)):
                        settle_sale(o.sku, o.qty, o.unit_price, nq.why, s_true)
                        m["negotiated"] += 1
                        m["neg_machine_gain"] += nq.u_machine - nq.d_machine
                        m["liar_deals"] += int(lied)
                        continue
                # no mutual gain (or buyer declined): fall through to stickers

            board = policy.price_board(state)
            prices = {sku: p for sku, (p, _) in board.items()}
            stock = {sku: state.stock(sku) for sku in prices}

            sku, qty, s_in = (consumer.best_bundle(prices, stock)
                              if prices else (None, 0, 0.0))

            if sku is not None and s_in > 0 and s_in >= s_out:
                settle_sale(sku, qty, prices[sku], board[sku][1], s_in)
            else:
                if s_out > 0:
                    m["lost_to_outside"] += 1
                rng = np.random.default_rng(substream(master_seed, "ret", day, tick, k))
                if rng.random() < consumer.patience:
                    delay = int(rng.integers(6, 24))
                    if tick + delay < TICKS_PER_DAY:
                        return_queue.append((tick + delay, consumer))

    if learner:
        learner.end_day(frozenset(
            sku for sku in catalog if state.stock(sku) == 0))
    if pool is not None:
        m["churned"] = pool.end_day(day)
        m["active_regulars"] = pool.active_count()
    eod = end_of_day(state, cfg, master_seed)
    m["spoiled_units"] = eod["spoiled_units"]
    m["spoilage_cost"] = eod["spoilage_cost"]
    m["profit"] = round(m["revenue"] - m["cogs_sold"] - m["spoilage_cost"], 2)
    for k in ("revenue", "cogs_sold", "consumer_surplus", "neg_machine_gain"):
        m[k] = round(m[k], 2)
    return m


def paired_ci(diffs: list[float], block: int = 1) -> dict:
    """Mean paired difference with a 95% t-interval. Daily diffs are
    serially dependent (learner state, leftover lots carry across days), so
    the headline interval uses `block`-day means — fewer, more independent
    observations — which widens the CI honestly."""
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        n_blocks = len(d) // block
        d = d[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)],
            "n": n, "block": block}


def run_experiment(arm_names: list[str], days: int, seed: int,
                   cfg: WorldConfig = DEFAULT_CONFIG) -> dict:
    catalog = build_catalog(cfg, seed)
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        state = fresh_machine("sim-01", catalog, cfg, seed)
        pool = None
        if cfg.regulars > 0:
            from vend.regulars import RegularPool
            from vend.world import _profit_optimal_list_price, CATALOG_SPEC
            market_ref = {s: _profit_optimal_list_price(mu, c)
                          for s, mu, c, *_ in CATALOG_SPEC}
            pool = RegularPool(cfg, seed, catalog, market_ref,
                              loss_aversion=cfg.loss_aversion,
                              ref_alpha_paid=cfg.ref_alpha_paid)
        per_day = [run_day(policy, state, catalog, seed, d, cfg, pool)
                   for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        results[name] = {"totals": totals, "per_day": per_day}

    paired = {}
    base = arm_names[0]
    for name in arm_names[1:]:
        paired[f"{name}_vs_{base}"] = {
            metric: paired_ci([results[name]["per_day"][d][metric]
                               - results[base]["per_day"][d][metric]
                               for d in range(days)],
                              block=5)   # 5-day blocks vs learner/lot autocorrelation
            for metric in ("profit", "revenue", "consumer_surplus",
                           "spoilage_cost", "units")
        }

    return {
        "vend_version": VEND_VERSION,
        "config": {
            "seed": seed, "days": days, "arms": arm_names,
            "world": {"sigma_cal": cfg.sigma_cal, "sigma_rate": cfg.sigma_rate,
                      "sigma_wtp": cfg.sigma_wtp, "dow": cfg.dow,
                      "glut_prob": cfg.glut_prob,
                      "traffic_scale": cfg.traffic_scale},
            "list_prices": {s: l.list_price for s, l in catalog.items()},
            "notes": [
                "static arm = PROFIT-optimal all-day single price (strong baseline)",
                "all arms maximize profit (margin), not revenue",
                "machine's demand model = the true one (favorable to dynamic arms)",
                "discount-only: no arm can price above list (type-enforced)",
                "paired seeds: identical customer streams across arms",
            ],
        },
        "arms": {n: {"totals": r["totals"]} for n, r in results.items()},
        "paired": paired,
        "_per_day": {n: r["per_day"] for n, r in results.items()},
    }


def run_grid(arm_names: list[str], days: int, seed: int, out: str) -> int:
    """The P1.5 pre-registered grid: operator miscalibration × demand shock,
    with the office-tower calendar and glut days ON (that's the realistic
    texture the sticker can't see). Cell (0, 0) with dow/glut off replicates
    P0/P1 exactly and runs first as the control."""
    cells = [("control", WorldConfig())]
    for sc in (0.0, 0.15, 0.30):
        for sr in (0.0, 0.30, 0.60):
            cells.append((f"cal{sc:g}_shock{sr:g}",
                          WorldConfig(sigma_cal=sc, sigma_rate=sr,
                                      sigma_wtp=sr / 2, dow=True,
                                      glut_prob=0.15)))
    grid = {}
    for name, cfg in cells:
        res = run_experiment(arm_names, days, seed, cfg)
        cell = {"world": res["config"]["world"],
                "profit": {a: res["arms"][a]["totals"]["profit"] for a in arm_names},
                "paired": {k: {"profit": v["profit"],
                               "consumer_surplus": v["consumer_surplus"]}
                           for k, v in res["paired"].items()}}
        grid[name] = cell
        deltas = {k: v["profit"]["mean"] for k, v in res["paired"].items()}
        print(f"{name:<22} profit Δ/day vs {arm_names[0]}: {deltas}")
    with open(out, "w") as f:
        json.dump({"vend_version": VEND_VERSION, "days": days, "seed": seed,
                   "arms": arm_names, "cells": grid}, f, indent=1)
    print(f"wrote {out}")
    return 0


# ── split-tilt frontier (Task #65) ─────────────────────────────────────────
# Sweep the seller bargaining weight w (scenario.nash_quote) at the realistic
# calibrated cell and map three axes: SELLER PROFIT (a2a−posted), CONSUMER
# SURPLUS advantage (a2a−posted), and honest-disclosure IC (the buyer's
# best-response gain from lying — the wtp_factor × walk-claim liar battery).
# The deliverable is the max defensible seller-profit gain SUBJECT TO CS≥0 and
# IC intact. Pairing is on the customer stream (seed,day,tick,k,uid), which is
# policy-independent — so a2a(w) − posted and a2a(w) − a2a(0.5) are all paired.

TILT_W_GRID = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0)
# the liar battery: disclosed-WTP scaling × outside-option claim, MINUS the
# honest point (1.0, no-free-walk). "the buyer's best response" = the max-gain
# deviation over this grid.
TILT_LIAR_GRID = tuple((f, zw) for f in (0.55, 0.75, 1.0, 1.25, 1.5)
                       for zw in (False, True) if not (f == 1.0 and zw is False))


def _pooled_ci(per_seed_diffs: list[list[float]], block: int = 5) -> dict:
    """Block CI over the two seeds' paired daily-diff series, concatenated —
    each day's diff is within-seed paired (same customer stream); the blocks
    are then treated as the independent replicate units."""
    flat = [x for series in per_seed_diffs for x in series]
    return paired_ci(flat, block=block)


def run_tilt(seeds: list[int], days: int, cfg: WorldConfig, out: str,
             w_grid=TILT_W_GRID, liar_grid=TILT_LIAR_GRID) -> int:
    from vend.policies import A2APolicy, StaticPolicy, StrongPostedPolicy

    def run_arm(seed, catalog, factory):
        state = fresh_machine("tilt", catalog, cfg, seed)
        pol = factory()
        return [run_day(pol, state, catalog, seed, d, cfg) for d in range(days)]

    series: dict = {}   # (seed, key) -> per_day list
    for seed in seeds:
        catalog = build_catalog(cfg, seed)
        series[(seed, "static")] = run_arm(seed, catalog, StaticPolicy)
        series[(seed, "posted")] = run_arm(seed, catalog, StrongPostedPolicy)
        for w in w_grid:
            series[(seed, ("a2a", w))] = run_arm(
                seed, catalog, lambda w=w: A2APolicy(seller_weight=w))
            for (f, zw) in liar_grid:
                series[(seed, ("liar", w, f, zw))] = run_arm(
                    seed, catalog, lambda w=w, f=f, zw=zw: A2APolicy(
                        attest=False, liar_share=1.0, attack_factor=f,
                        attack_zero_walk=zw, seller_weight=w))
        print(f"  seed {seed}: ran {2 + len(w_grid) * (1 + len(liar_grid))} arms")

    def dseries(key_a, key_b, metric):
        return [[series[(s, key_a)][d][metric] - series[(s, key_b)][d][metric]
                 for d in range(days)] for s in seeds]

    frontier = []
    for w in w_grid:
        a2a = ("a2a", w)
        row = {"w": w}
        # axis 1 & 2: seller profit and CS advantage over each baseline
        for base in ("posted", "static"):
            row[f"profit_vs_{base}"] = _pooled_ci(dseries(a2a, base, "profit"))
            row[f"cs_vs_{base}"] = _pooled_ci(
                dseries(a2a, base, "consumer_surplus"))
            row[f"profit_vs_{base}_by_seed"] = [
                paired_ci(dseries(a2a, base, "profit")[i])["mean"]
                for i in range(len(seeds))]
            row[f"cs_vs_{base}_by_seed"] = [
                paired_ci(dseries(a2a, base, "consumer_surplus")[i])["mean"]
                for i in range(len(seeds))]
        # raw levels (context)
        row["a2a_profit_per_day"] = round(sum(
            sum(m["profit"] for m in series[(s, a2a)]) for s in seeds)
            / (len(seeds) * days), 2)
        row["a2a_cs_per_day"] = round(sum(
            sum(m["consumer_surplus"] for m in series[(s, a2a)]) for s in seeds)
            / (len(seeds) * days), 2)
        # axis 3: IC — buyer's best-response gain from lying (CS of an
        # all-liars arm − CS of the honest a2a arm, same w, paired). We also
        # track each liar arm's PROFIT vs posted (the realized seller profit
        # when buyers actually play that lie) to test the profit-peak-then-
        # collapse prediction, and we SEPARATE the WTP-understatement channel
        # (factor<1, no free-walk claim — the anchoring attack the TILT is
        # supposed to re-enable) from the w-robust free-walk outside-option
        # leak (zero_walk=True), which attestation prices out independently.
        devs = []
        for (f, zw) in liar_grid:
            liar = ("liar", w, f, zw)
            devs.append({
                "factor": f, "zero_walk": zw,
                "cs_gain": _pooled_ci(dseries(liar, a2a, "consumer_surplus")),
                "profit_vs_posted": _pooled_ci(dseries(liar, "posted", "profit")),
            })
        best = max(devs, key=lambda d: d["cs_gain"]["mean"])
        row["liar_best_response"] = {
            "factor": best["factor"], "zero_walk": best["zero_walk"],
            "cs_gain": best["cs_gain"],
            "realized_profit_vs_posted": best["profit_vs_posted"]}
        # the WTP-understatement channel only (factor<1, zw=False)
        under = [d for d in devs if d["factor"] < 1.0 and not d["zero_walk"]]
        best_u = max(under, key=lambda d: d["cs_gain"]["mean"])
        row["understatement_best"] = {
            "factor": best_u["factor"], "cs_gain": best_u["cs_gain"],
            "realized_profit_vs_posted": best_u["profit_vs_posted"]}
        # Realized seller profit under the REALISTIC deployment: the engine
        # attests the OUTSIDE OPTION (blocks the w-robust free-walk leak), so
        # the only lie left is WTP-understatement — which pays the buyer only
        # once the tilt is steep enough (understatement_best significantly
        # positive). Below that, buyers stay honest and the seller banks the
        # honest-arm profit; at/after it, buyers understate and the seller
        # gets the understatement-arm profit. This is the series the peak-
        # then-collapse prediction is about.
        u_ci = best_u["cs_gain"]["ci95"]
        wtp_lie_pays = u_ci is not None and u_ci[0] > 0
        row["attested_realized_profit_vs_posted"] = (
            best_u["profit_vs_posted"] if wtp_lie_pays else row["profit_vs_posted"])
        row["wtp_understatement_pays"] = wtp_lie_pays
        row["liar_deviations"] = devs
        frontier.append(row)

    # break-points
    def crosses_zero(getter, positive_at_start=True):
        """First w at which `getter(row)` mean crosses 0 (linear interp
        between bracketing grid points); None if it never crosses."""
        pts = [(r["w"], getter(r)) for r in frontier]
        for (w0, v0), (w1, v1) in zip(pts, pts[1:]):
            if (v0 >= 0) != (v1 >= 0):
                if v1 == v0:
                    return w1
                return round(w0 + (0 - v0) * (w1 - w0) / (v1 - v0), 3)
        return None

    cs_zero_posted = crosses_zero(lambda r: r["cs_vs_posted"]["mean"])
    cs_zero_static = crosses_zero(lambda r: r["cs_vs_static"]["mean"])

    def first_sig_positive(getter):
        """First w at which getter(row) (a paired_ci dict) is significantly
        positive — CI lower bound > 0 — i.e. lying is significantly the
        buyer's best response and disclosure-IC has broken."""
        for r in frontier:
            ci = getter(r)["ci95"]
            if ci is not None and ci[0] > 0:
                return r["w"]
        return None

    # IC breaks (two channels): the strict all-deviation best response, and
    # the WTP-understatement channel the tilt specifically re-enables.
    ic_break_all = first_sig_positive(lambda r: r["liar_best_response"]["cs_gain"])
    ic_break_under = first_sig_positive(lambda r: r["understatement_best"]["cs_gain"])

    # profit-peak axes: (1) the HONEST arm's seller profit (truthtelling
    # assumed); (2) the REALIZED seller profit when buyers play the CS-best
    # lie — the axis the peak-then-collapse prediction is actually about.
    peak_honest = max(frontier, key=lambda r: r["profit_vs_posted"]["mean"])
    peak_realized = max(
        frontier, key=lambda r: r["liar_best_response"]["realized_profit_vs_posted"]["mean"])
    peak_attested = max(
        frontier, key=lambda r: r["attested_realized_profit_vs_posted"]["mean"])

    # honest region: CS≥0 (both baselines) AND WTP-disclosure IC intact
    # (understatement not significantly the buyer's best response).
    def under_ic_intact(r):
        ci = r["understatement_best"]["cs_gain"]["ci95"]
        return ci is None or ci[0] <= 0
    fair_floor = 0.5 * frontier[0]["cs_vs_posted"]["mean"]   # half symmetric CS
    honest = [r for r in frontier
              if r["cs_vs_posted"]["mean"] >= 0 and under_ic_intact(r)]
    honest_fair = [r for r in honest
                   if r["cs_vs_posted"]["mean"] >= fair_floor]
    max_honest = max(honest, key=lambda r: r["profit_vs_posted"]["mean"]) \
        if honest else None
    max_fair = max(honest_fair, key=lambda r: r["profit_vs_posted"]["mean"]) \
        if honest_fair else None

    breakpoints = {
        "cs_zero_w_vs_posted": cs_zero_posted,
        "cs_zero_w_vs_static": cs_zero_static,
        "ic_break_w_all_deviations": ic_break_all,
        "ic_break_w_understatement": ic_break_under,
        "profit_peak_w_honest_arm": peak_honest["w"],
        "profit_peak_w_realized_under_lying": peak_realized["w"],
        "profit_peak_w_attested_realized": peak_attested["w"],
        "profit_peak_attested_realized_vs_posted": peak_attested["attested_realized_profit_vs_posted"],
        "fairness_floor_cs_vs_posted": round(fair_floor, 2),
        "max_honest_w": max_honest["w"] if max_honest else None,
        "max_honest_profit_vs_posted": max_honest["profit_vs_posted"] if max_honest else None,
        "max_fair_w": max_fair["w"] if max_fair else None,
        "max_fair_profit_vs_posted": max_fair["profit_vs_posted"] if max_fair else None,
    }

    payload = {
        "vend_version": VEND_VERSION, "task": "split-tilt-frontier-65",
        "days": days, "seeds": seeds,
        "world": {"sigma_cal": cfg.sigma_cal, "sigma_rate": cfg.sigma_rate,
                  "sigma_wtp": cfg.sigma_wtp, "dow": cfg.dow,
                  "glut_prob": cfg.glut_prob, "traffic_scale": cfg.traffic_scale},
        "w_grid": list(w_grid),
        "liar_grid": [{"factor": f, "zero_walk": zw} for f, zw in liar_grid],
        "block": 5,
        "frontier": frontier,
        "breakpoints": breakpoints,
    }
    with open(out, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"wrote {out}")
    hdr = ("w     sellerΔ(a2a-posted)   CSΔ(a2a-posted)      "
           "understate-lie-gain   any-lie-gain   realized-profit(under lie)")
    print("\n" + hdr)
    for r in frontier:
        pv, cv = r["profit_vs_posted"], r["cs_vs_posted"]
        ug = r["understatement_best"]["cs_gain"]
        lg = r["liar_best_response"]["cs_gain"]
        rp = r["liar_best_response"]["realized_profit_vs_posted"]
        ar = r["attested_realized_profit_vs_posted"]
        print(f"{r['w']:<5} {pv['mean']:+5.2f} {str(pv['ci95']):<16} "
              f"{cv['mean']:+5.2f} {str(cv['ci95']):<16} "
              f"{ug['mean']:+5.2f} {str(ug['ci95']):<14} "
              f"{lg['mean']:+5.2f}   {ar['mean']:+5.2f}{'!' if not r['wtp_understatement_pays'] else 'X'}")
    print("(attested-realized col: '!' = WTP-honest, banked; 'X' = WTP-lie pays, collapsed)")
    print("\nbreak-points:", json.dumps(breakpoints, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260713)
    ap.add_argument("--arms", default="static,gvr")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-cal", type=float, default=0.0)
    ap.add_argument("--sigma-rate", type=float, default=0.0)
    ap.add_argument("--sigma-wtp", type=float, default=0.0)
    ap.add_argument("--dow", action="store_true")
    ap.add_argument("--glut", type=float, default=0.0)
    ap.add_argument("--calibrated-traffic", action="store_true",
                    help="thin arrivals to CALIBRATED_TRAFFIC_SCALE (~7-8 "
                         "vends/day on the standard catalog, SOTI 2025 + "
                         "Cantaloupe 2025) instead of the hot 'smart-store "
                         "P90' profile (traffic_scale=1.0, ~74/day)")
    ap.add_argument("--traffic-scale", type=float, default=None,
                    help="override the arrival-thinning factor directly "
                         "(1.0 = hot/smart-store-P90 profile, the default); "
                         "takes precedence over --calibrated-traffic")
    ap.add_argument("--grid", action="store_true",
                    help="run the P1.5 miscalibration × shock grid")
    ap.add_argument("--tilt", action="store_true",
                    help="run the split-tilt seller-weight frontier (Task #65) "
                         "at the realistic calibrated cell, both seeds, 90d")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        return run_grid(arm_names, args.days, args.seed,
                        args.out or "vend/grid.json")

    if args.tilt:
        from vend.world import CALIBRATED_TRAFFIC_SCALE
        cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3,
                          dow=True, glut_prob=0.15,
                          traffic_scale=CALIBRATED_TRAFFIC_SCALE)
        return run_tilt([20260713, 7], args.days if args.days != 30 else 90,
                        cfg, args.out or "vend/tilt.json")

    if args.traffic_scale is not None:
        traffic_scale = args.traffic_scale
    elif args.calibrated_traffic:
        from vend.world import CALIBRATED_TRAFFIC_SCALE
        traffic_scale = CALIBRATED_TRAFFIC_SCALE
    else:
        traffic_scale = 1.0

    cfg = WorldConfig(sigma_cal=args.sigma_cal, sigma_rate=args.sigma_rate,
                      sigma_wtp=args.sigma_wtp, dow=args.dow,
                      glut_prob=args.glut, traffic_scale=traffic_scale)
    res = run_experiment(arm_names, args.days, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        summary = {n: res["arms"][n]["totals"]["profit"] for n in arm_names}
        print(f"wrote {args.out} — profit by arm: {summary}")
        for k, v in res["paired"].items():
            print(f"  {k}: profit Δ {v['profit']['mean']} CI95 {v['profit']['ci95']}"
                  f" · CS Δ {v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

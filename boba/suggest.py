"""BOBA suggest/1 — the pre-checkout bundle-SUGGESTION arm: learn WHEN to suggest.

The question is NOT "does upselling help." It is **when to suggest**. A
proactive bundle suggestion (add pearls / upsize a cup) offered to a customer
BEFORE they check out is not free:

  * BENEFIT — if the customer values the add-on above its (discount-only)
    incremental price, both sides gain: the shop books incremental margin on a
    unit the sticker menu was refusing to sell, the buyer keeps the incremental
    surplus. A genuine Pareto gain, split by pricing the increment at the
    person-INDEPENDENT value markdown (world._value_price), never below cost.
  * COST — a suggestion consumes a beat and, when it lands on someone who did
    NOT want the add-on, carries an annoyance/balk hazard: with probability
    SUGGEST_REJECT_BALK the unwanted pitch tips an already-at-the-counter buyer
    into abandoning the WHOLE order (base sale lost). That probability is the
    ONE calibrated-by-assertion input here — conservative, sweepable, and
    LABELED as an assumption, not a measurement. A second, structural cost is
    real congestion: an accepted upsize adds a cup to the FIFO queue, and at the
    lunch crunch (PEAK_HOURS) that lengthens the visible line and raises balk
    risk for everyone behind — the shop's own physics, priced by the same
    first-order shadow world.capacity_relief uses.

Design honesty (attack these):
  * The base order is charged at LIST, always. Only the INCREMENT is marked
    down (discount-only, type-enforced). So a good suggestion never gives back
    margin on the base sale the customer was already making — the "gives up
    margin on a customer who'd have bought the base anyway" cost the task names
    is absent BY CONSTRUCTION here (we don't touch the base price). The costs
    that remain are annoyance and congestion. A whole-bundle-sweetener variant
    that DOES cannibalize the base is future work, flagged not built.
  * NEVER-suggest is byte-identical to the P0 static walk-in (balk, then the
    sticker order) — the trusted baseline, pinned by test.
  * The suggest POLICY reads only OBSERVABLE state: the hour, the observed queue
    (balk_prob), and the customer's REVEALED base-order composition (drink, qty,
    toppings). It never reads the consumer's true bundle_value/WTP — the world
    computes accept/reject on true preferences, the policy only decides whether
    to ask. Pinned by test (two buyers with identical base orders but wildly
    different hidden valuations get the identical gate decision).
  * LEARNED-suggest learns a per-observable-bucket expected net value from a
    WARMUP phase run under always-suggest (the shop's own logged history: it
    sees who accepts, who abandons, and its own queue), freezes it, and on
    held-out eval days suggests iff (learned bucket EV − observable congestion
    shadow) clears a threshold. Train-on-past / deploy-on-future; days are
    independent so there is no leakage.

  python3 -m boba.suggest --seed 20260710 --warmup 20 --eval 30 \
      --out boba/results-suggest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from boba.run import _settle, paired_ci
from boba.world import (DEFAULT_CONFIG, DRINK_APPEAL, DRINK_COST, DRINK_PRICE,
                        HOURLY_WTP_MULT, MEAN_DRINK_MARGIN, PEAK_HOURS,
                        PEARL_COST, QTY_CAP, RENT_PER_DAY, TICKS_PER_DAY,
                        TOP_APPEAL, TOP_COST, TOP_PRICE, TOP_SIGMA, WTP_SIGMA,
                        BobaConfig, Consumer, ShopState, _value_price,
                        arrivals_at, balk_prob, best_menu_order, bundle_value,
                        close_out, expire_batches, hour_of, maybe_cook,
                        open_shop, outside_surplus, release_scheduled,
                        sample_consumer, serve_queue, substream)

SUGGEST_VERSION = 1

# ── the ONE calibrated-by-assertion input (LABELED assumption) ───────────────
# P(an UNWANTED suggestion tips an at-the-counter buyer into abandoning the
# whole order). Conservative: below the wait model's 8%/min balk slope's reach
# at a short line, in the same order of magnitude. Swept in RESULTS; NOT a
# measured anchor. When a suggestion is ACCEPTED there is no annoyance (a
# welcome upsell doesn't irritate) — the hazard is borne only by pitches the
# buyer rejects, which is exactly what makes "when to suggest" a real
# prediction problem (suggest where acceptance is likely; hold off where it is
# not).
SUGGEST_REJECT_BALK = 0.15

QHOT_BALK = 0.10       # observable "the line is hot" cutoff on balk_prob
MIN_BUCKET = 30        # learned table: min samples before a bucket is trusted
# Learned gate: suggest iff net EV clears this ($/suggestion). A small positive
# buffer, the same "don't-ask-for-pennies" idea as the cart's min-gain buffer:
# the cost of a missed suggestion is ~zero, but a marginal ask still risks the
# annoyance hazard, so buckets whose estimated net gain is only noisily-positive
# should NOT be asked. Buckets separate cleanly bimodal (the group-upsize wins
# sit at ~+$1.5–3, everything else ≤ ~+$0.1), so any buffer in [0.25, 1.0]
# yields the identical, seed-robust policy — 0.50 sits on that plateau.
SUGGEST_THRESHOLD = 0.50

ARMS = ("never", "always", "learned")

PAIRED_METRICS = ("margin", "consumer_surplus", "friction_lost", "cups",
                  "peak_balks", "suggestions", "accepts", "suggest_abandons")


# ── person-INDEPENDENT value markdowns (same posted logic as menu_for_context)
def _drink_value_price(drink: str, hour: int) -> float:
    mult = HOURLY_WTP_MULT[hour]
    return _value_price(round(DRINK_APPEAL[drink] * mult, 6),
                        round(DRINK_COST[drink], 6), DRINK_PRICE[drink],
                        WTP_SIGMA)


def _top_value_price(top: str) -> float:
    return _value_price(round(TOP_APPEAL[top], 6), round(TOP_COST[top], 6),
                        TOP_PRICE[top], TOP_SIGMA)


@dataclass(frozen=True)
class Suggestion:
    """A single proactive upgrade, constructed from OBSERVABLE state only.
    `qty`/`tops` are the FULL order AFTER the suggestion; `inc_price` is the
    discount-only incremental charge ADDED to the (unchanged, at-list) base."""
    kind: str                  # "add-pearls" | "upsize"
    drink: str
    qty: int
    tops: tuple[str, ...]
    inc_price: float           # discount-only increment, added to base list
    base_qty: int
    base_tops: tuple[str, ...]
    extra_cups: int            # cups this adds to the FIFO queue (0 = add-pearls)

    @property
    def inc_list_value(self) -> float:
        """List price of the increment — the discount-only ceiling."""
        if self.kind == "add-pearls":
            return round(self.base_qty * TOP_PRICE["pearls"], 2)
        return round(DRINK_PRICE[self.drink]
                     + sum(TOP_PRICE[t] for t in self.base_tops), 2)

    def inc_cost(self) -> float:
        """TRUE ingredient cost of the increment (accounting, never salvage)."""
        if self.kind == "add-pearls":
            return self.base_qty * PEARL_COST
        return DRINK_COST[self.drink] + sum(TOP_COST[t] for t in self.base_tops)


def build_suggestion(state: ShopState, base_drink: str, base_qty: int,
                     base_tops: tuple[str, ...], hour: int) -> Suggestion | None:
    """THE candidate upgrade, from the REVEALED base order + shop state only —
    no consumer valuation enters. One deterministic candidate per observable
    context so the three arms differ ONLY in the gate (when to ask), never in
    what is asked:

      base has no pearls  → suggest adding pearls to the cup(s) they're getting
                            (the most-liked topping; a pure topping attach, no
                            new cup, no congestion), incremental price = the
                            per-cup pearls value markdown × the base qty.
      base already pearled → suggest one more cup (an upsize), incremental price
                            = the (hour-priced) drink + its toppings value
                            markdown, for the single extra cup.

    Returns None when there is nothing valid to offer (no pearl stock to
    reserve, or already at QTY_CAP)."""
    has_pearls = "pearls" in base_tops
    if not has_pearls:
        if state.pearl_stock() < base_qty:
            return None                         # can't reserve the pearls
        inc = round(base_qty * _top_value_price("pearls"), 2)
        return Suggestion("add-pearls", base_drink, base_qty,
                          tuple(base_tops) + ("pearls",), inc,
                          base_qty, tuple(base_tops), extra_cups=0)
    if base_qty >= QTY_CAP:
        return None                             # no room to upsize
    if state.pearl_stock() < base_qty + 1:
        return None                             # the extra pearled cup needs stock
    inc = round(_drink_value_price(base_drink, hour)
                + sum(_top_value_price(t) for t in base_tops), 2)
    return Suggestion("upsize", base_drink, base_qty + 1, tuple(base_tops), inc,
                      base_qty, tuple(base_tops), extra_cups=1)


# ── observable features (the learned policy's whole input) ───────────────────
def feature_key(state: ShopState, base_qty: int,
                base_tops: tuple[str, ...]) -> str:
    """A small bucket over OBSERVABLE state only: is it a congested peak hour,
    is the visible line hot, is the base a solo (qty 1) order, does the base
    already carry pearls (which selects the candidate type). Nothing here reads
    the consumer's private valuation — base_qty/base_tops are the ORDER the
    buyer stated at the sticker board."""
    peak = int(hour_of(state.tick) in PEAK_HOURS)
    qhot = int(balk_prob(state) >= QHOT_BALK)
    solo = int(base_qty == 1)
    pearled = int("pearls" in base_tops)
    return f"peak{peak}_qhot{qhot}_solo{solo}_pearls{pearled}"


def congestion_shadow(state: ShopState, sug: Suggestion) -> float:
    """Observable first-order $ cost of the extra cups a suggestion pushes into
    a congested queue: extra_cups × current balk prob × mean drink margin, zero
    off-peak (same shape world.capacity_relief credits a FREED slot). The shop
    can see its own queue and rate, so this uses only observable state."""
    if sug.extra_cups <= 0 or hour_of(state.tick) not in PEAK_HOURS:
        return 0.0
    return sug.extra_cups * balk_prob(state) * MEAN_DRINK_MARGIN


def build_table(records: list[tuple[str, float]]) -> dict:
    """Aggregate warmup logs into per-bucket mean net $ value of having
    suggested. `records` are (feature_key, realized_net) pairs the shop OBSERVES
    under always-suggest: +incremental margin on an accept, −base margin on an
    annoyance-abandon, 0 on a shrug-and-buy-base reject. Sparse buckets fall
    back to the pooled mean."""
    sums: dict[str, float] = defaultdict(float)
    cnts: dict[str, int] = defaultdict(int)
    for key, net in records:
        sums[key] += net
        cnts[key] += 1
    pooled = (sum(sums.values()) / sum(cnts.values())) if records else 0.0
    buckets = {key: {"mean": round(sums[key] / cnts[key], 4), "n": cnts[key]}
               for key in cnts}
    return {"pooled": round(pooled, 4), "buckets": buckets}


def table_lookup(table: dict, key: str) -> float:
    b = table["buckets"].get(key)
    if b is None or b["n"] < MIN_BUCKET:
        return table["pooled"]
    return b["mean"]


def gate_open(arm: str, state: ShopState, sug: Suggestion | None,
              table: dict | None) -> bool:
    """Whether to ASK. never: never. always: whenever a candidate exists.
    learned: iff the learned bucket EV minus the observable congestion shadow
    clears the threshold. Reads only observable state (feature_key, balk_prob)."""
    if sug is None or arm == "never":
        return False
    if arm == "always":
        return True
    key = feature_key(state, sug.base_qty, sug.base_tops)
    est = table_lookup(table, key) - congestion_shadow(state, sug)
    return est > SUGGEST_THRESHOLD


def _new_metrics() -> dict:
    return {"revenue": 0.0, "ingredient_cost": 0.0, "waste_cost": 0.0,
            "cups": 0, "toppings": 0, "deals": 0, "deferred": 0,
            "arrivals": 0, "balks": 0, "peak_balks": 0, "lost": 0,
            "consumer_surplus": 0.0, "suggestions": 0, "accepts": 0,
            "suggest_abandons": 0, "peak_suggest_abandons": 0}


def simulate_day(arm: str, master_seed: int, day: int,
                 cfg: BobaConfig = DEFAULT_CONFIG, table: dict | None = None,
                 log: list | None = None) -> dict:
    """One paired day. The walk-in balk fires FIRST (byte-identical to the
    static P0 path, so arm='never' reproduces static exactly); the suggestion,
    when the gate opens, is offered to a buyer who has already survived the
    balk and is placing their base order. Accept/reject is settled on the
    buyer's TRUE preferences — the policy never saw them."""
    m = _new_metrics()
    state = open_shop(day, cfg.balk_model)
    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        m["waste_cost"] += expire_batches(state)
        maybe_cook(state)
        release_scheduled(state)
        serve_queue(state)

        n = arrivals_at(master_seed, day, tick, cfg)
        m["arrivals"] += n
        for k in range(n):
            consumer = sample_consumer(master_seed, day, tick, k, cfg)
            peak = hour_of(tick) in PEAK_HOURS

            # ── walk-in balk BEFORE ordering (identical to static P0) ──
            b = balk_prob(state)
            roll = float(np.random.default_rng(
                substream(master_seed, "balk", day, tick, k)).random())
            if roll < b:
                m["balks"] += 1
                if peak:
                    m["peak_balks"] += 1
                continue

            d0, q0, t0, s0 = best_menu_order(
                consumer, DRINK_PRICE, TOP_PRICE,
                pearls_ok=state.pearl_stock() >= QTY_CAP)
            s_out = outside_surplus(consumer)
            if not (d0 is not None and s0 > 0 and s0 >= s_out):
                m["lost"] += 1                  # wouldn't buy even the base
                continue

            base_price = round(q0 * (DRINK_PRICE[d0]
                                     + sum(TOP_PRICE[t] for t in t0)), 2)
            base_margin = (q0 * (DRINK_PRICE[d0] - DRINK_COST[d0])
                           + q0 * sum(TOP_PRICE[t] - TOP_COST[t] for t in t0))

            sug = (build_suggestion(state, d0, q0, t0, hour_of(tick))
                   if arm != "never" else None)
            if not gate_open(arm, state, sug, table):
                _settle(state, m, d0, q0, t0, base_price, s0)   # base only
                continue

            # ── the suggestion is on the table ──
            m["suggestions"] += 1
            key = feature_key(state, q0, t0)     # BEFORE settle mutates queue
            base_val = bundle_value(consumer, d0, q0, t0)
            full_val = bundle_value(consumer, sug.drink, sug.qty, sug.tops)
            inc_surplus = (full_val - base_val) - sug.inc_price  # TRUE

            if inc_surplus > 1e-9:
                # ACCEPT: base at LIST + increment at the value markdown
                m["accepts"] += 1
                total_price = round(base_price + sug.inc_price, 2)
                realized_cs = full_val - total_price
                _settle(state, m, sug.drink, sug.qty, sug.tops, total_price,
                        realized_cs)
                if log is not None:
                    log.append((key, round(sug.inc_price - sug.inc_cost(), 4)))
                continue

            # REJECT: the unwanted pitch carries the annoyance hazard
            aroll = float(np.random.default_rng(
                substream(master_seed, "annoy", day, tick, k)).random())
            if aroll < SUGGEST_REJECT_BALK:
                m["suggest_abandons"] += 1       # lost the whole order
                if peak:
                    m["peak_suggest_abandons"] += 1
                if log is not None:
                    log.append((key, round(-base_margin, 4)))
                continue
            _settle(state, m, d0, q0, t0, base_price, s0)   # shrug, buy base
            if log is not None:
                log.append((key, 0.0))

    m["waste_cost"] += close_out(state)
    m["batches_cooked"] = state.batches_cooked
    m["margin"] = round(m["revenue"] - m["ingredient_cost"] - m["waste_cost"], 2)
    m["rent"] = RENT_PER_DAY
    m["friction_lost"] = m["balks"] + m["suggest_abandons"]
    m["accept_rate"] = round(m["accepts"] / m["suggestions"], 3) \
        if m["suggestions"] else 0.0
    for key in ("revenue", "ingredient_cost", "waste_cost", "consumer_surplus"):
        m[key] = round(m[key], 2)
    return m


def learn_table(master_seed: int, warmup_days: int,
                cfg: BobaConfig = DEFAULT_CONFIG) -> dict:
    """Run the warmup phase under always-suggest and aggregate the shop's own
    OBSERVABLE per-bucket net outcomes into the frozen learned table."""
    records: list[tuple[str, float]] = []
    for d in range(warmup_days):
        simulate_day("always", master_seed, d, cfg, table=None, log=records)
    return build_table(records)


def run_suggest_experiment(seed: int, warmup_days: int, eval_days: int,
                           cfg: BobaConfig = DEFAULT_CONFIG) -> dict:
    """Learn on warmup days [0, W) under always; evaluate all three arms paired
    on HELD-OUT days [W, W+E). Days are independent draws, so the split has no
    leakage. Paired CIs (block=5) on learned−never, learned−always,
    always−never."""
    table = learn_table(seed, warmup_days, cfg)
    eval_days_range = range(warmup_days, warmup_days + eval_days)

    per_day = {a: [simulate_day(a, seed, d, cfg, table) for d in eval_days_range]
               for a in ARMS}
    totals = {a: {k: round(sum(m[k] for m in per_day[a]), 2)
                  for k in per_day[a][0] if isinstance(per_day[a][0][k],
                                                       (int, float))}
              for a in ARMS}
    for a in ARMS:
        totals[a]["accept_rate"] = round(
            totals[a]["accepts"] / totals[a]["suggestions"], 3) \
            if totals[a]["suggestions"] else 0.0

    def paired(hi: str, lo: str) -> dict:
        return {metric: paired_ci(
            [per_day[hi][i][metric] - per_day[lo][i][metric]
             for i in range(eval_days)], block=5)
            for metric in PAIRED_METRICS}

    comparisons = {
        "learned_vs_never": paired("learned", "never"),
        "learned_vs_always": paired("learned", "always"),
        "always_vs_never": paired("always", "never"),
    }
    verdict = _verdict(comparisons)
    return {
        "suggest_version": SUGGEST_VERSION,
        "config": {"seed": seed, "warmup_days": warmup_days,
                   "eval_days": eval_days,
                   "world": {"sigma_shock": cfg.sigma_shock,
                             "flexible_share": cfg.flexible_share,
                             "balk_model": cfg.balk_model},
                   "suggest_reject_balk": SUGGEST_REJECT_BALK,
                   "qhot_balk": QHOT_BALK, "min_bucket": MIN_BUCKET,
                   "suggest_threshold": SUGGEST_THRESHOLD,
                   "rent_per_day": RENT_PER_DAY,
                   "notes": [
                       "never-suggest is byte-identical to the P0 static "
                       "walk-in (pinned by test)",
                       "base charged at LIST; only the increment is discount-"
                       "only (value markdown, never below cost)",
                       "policy reads only observable state (hour, queue, "
                       "revealed base order); accept/reject settled on TRUE "
                       "bundle_value by the world",
                       "learned table frozen on warmup days, applied to "
                       "held-out eval days (train-past/deploy-future)",
                       "SUGGEST_REJECT_BALK is a LABELED conservative "
                       "assumption, not a measured anchor",
                   ]},
        "learned_table": table,
        "arms": {a: totals[a] for a in ARMS},
        "paired": comparisons,
        "verdict": verdict,
    }


def _sig_pos(ci: dict) -> bool:
    return ci["ci95"] is not None and ci["ci95"][0] > 0


def _sig_neg(ci: dict) -> bool:
    return ci["ci95"] is not None and ci["ci95"][1] < 0


def _verdict(cmp: dict) -> dict:
    ln, la = cmp["learned_vs_never"], cmp["learned_vs_always"]
    beats_never = _sig_pos(ln["margin"])
    beats_always = _sig_pos(la["margin"])
    cs_not_hurt_vs_never = not _sig_neg(ln["consumer_surplus"])
    balks_not_inflated_vs_never = not _sig_pos(ln["friction_lost"])
    return {
        "learned_beats_never_on_margin": beats_never,
        "learned_beats_always_on_margin": beats_always,
        "learned_cs_not_worse_than_never": cs_not_hurt_vs_never,
        "learned_balks_not_inflated_vs_never": balks_not_inflated_vs_never,
        "learned_is_pareto": bool(beats_never and beats_always
                                  and cs_not_hurt_vs_never
                                  and balks_not_inflated_vs_never),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--eval", type=int, default=30)
    ap.add_argument("--sigma-shock", type=float, default=0.0)
    ap.add_argument("--flexible-share", type=float, default=0.35)
    ap.add_argument("--reject-balk", type=float, default=None,
                    help="override SUGGEST_REJECT_BALK (assumption sweep)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.reject_balk is not None:
        global SUGGEST_REJECT_BALK
        SUGGEST_REJECT_BALK = args.reject_balk

    cfg = BobaConfig(sigma_shock=args.sigma_shock,
                     flexible_share=args.flexible_share)
    res = run_suggest_experiment(args.seed, args.warmup, args.eval, cfg)

    a = res["arms"]
    print(f"reject_balk={SUGGEST_REJECT_BALK}  flex={args.flexible_share}  "
          f"warmup={args.warmup} eval={args.eval} seed={args.seed}")
    for name in ARMS:
        print(f"  {name:<8} margin {a[name]['margin']:>10.2f}  "
              f"CS {a[name]['consumer_surplus']:>9.2f}  "
              f"friction {a[name]['friction_lost']:>4}  "
              f"suggest {a[name]['suggestions']:>4}  "
              f"accept_rate {a[name]['accept_rate']}")
    for label, cmp in res["paired"].items():
        mm, cs, fr = cmp["margin"], cmp["consumer_surplus"], cmp["friction_lost"]
        print(f"  {label:<20} margin Δ {mm['mean']:+8.2f} {mm['ci95']}  "
              f"CS Δ {cs['mean']:+8.2f}  friction Δ {fr['mean']:+6.2f}")
    print(f"  VERDICT: {res['verdict']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

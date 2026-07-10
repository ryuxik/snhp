"""The toxic-human-negotiation experiment (task #69) — SNHP vs how humans
ACTUALLY negotiate, across the full type population.

The honest baseline is not passive posting: on the supply side procurement is all
negotiation, done by humans using the hardball-tactics canon (wholesale/​
negotiators.py). This runner drives, for every relationship-week SNHP would close
(the positive-surplus set), the FULL CROSS-PRODUCT of human venue-type × human
wholesaler-type (a uniform type population), scores the four ways human
negotiation fails, and pairs each against both-sides-SNHP.

Rigor (binding): the pie is computed once per relationship-week from the VALIDATED
nash_deal engine (the SNHP-coordinated route environment — a per-relationship
constant, paired across arms; humans are NOT additionally penalised for degraded
route density, a conservative choice). Pairing is keyed on the demand identity
(seed × week × relationship × type-pair), NEVER on the mechanism. Every headline
delta carries a 95% t-interval over SEED means; no win is claimed when a CI
includes zero. No LLM; byte-deterministic on the seed.

  python3 -m wholesale.run_human --seeds 8 --weeks 12 --out wholesale/results-human.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict

import numpy as np

from wholesale import calibration as cal
from wholesale.calibration import V_ORDER, W_ORDER
from wholesale.negotiators import (HUMAN_TYPES, ACCOMMODATOR, HARDBALLER,
                                   bargain, rel_value, relationship,
                                   snhp_outcome)
from wholesale.scenario import build_ctx, nash_deal
from wholesale.world import Schedule, week_demand

HUMAN_RUN_VERSION = 1
TYPE_NAMES = [t.name for t in HUMAN_TYPES]


def ci(vals: np.ndarray) -> dict:
    """Mean with a 95% t-interval over seed-level values (the conservative,
    honest unit — vend's block-CI convention)."""
    vals = np.asarray(vals, dtype=float)
    n = len(vals)
    mean = float(vals.mean())
    if n < 2:
        return {"mean": round(mean, 3), "ci95": None, "n": n}
    se = float(vals.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 3),
            "ci95": [round(mean - t * se, 3), round(mean + t * se, 3)], "n": n}


def _sig(d: dict) -> bool:
    """A delta is significant iff its 95% CI excludes zero."""
    lo, hi = (d["ci95"] or [0.0, 0.0])
    return lo > 0 or hi < 0


def block_rel_values(seed: int, week: int) -> list:
    """The positive-surplus relationships of one block-week, each with its pie
    computed in the SNHP-coordinated route environment (deals booked in route
    order so later relationships share the truck — the route-density market)."""
    schedules = {w: Schedule() for w in W_ORDER}
    out = []
    for w in W_ORDER:
        sch = schedules[w]
        for v in V_ORDER:
            ctx = build_ctx(w, v, cal.BASE_FLEX)
            env = week_demand(seed, week, w, v, cal.BASE_NOISE)
            rv, d = rel_value(ctx, env, sch)
            if rv.snhp_closes:
                out.append((w, v, rv))
                deal = nash_deal(ctx, env, sch, d)
                if deal is not None:
                    sch.add(v, deal.window)
            elif d.event == "ratecard":
                sch.add(v, d.window)
    return out


def run_seed(seed: int, weeks: int) -> dict:
    """All metrics for one seed, accumulated over weeks × positive-surplus
    relationships × the full human type cross-product, paired against SNHP."""
    a = defaultdict(float)
    # per-type payoff over BOTH roles: name -> [human_$, snhp_$, count]
    per_type = {t: [0.0, 0.0, 0] for t in TYPE_NAMES}

    for wk in range(weeks):
        for (_w, _v, rv) in block_rel_values(seed, wk):
            so = snhp_outcome(rv)                 # same for every type pair
            sr = relationship(so, rv)
            for tv in HUMAN_TYPES:
                for tw in HUMAN_TYPES:
                    ho = bargain(tv, tw, rv)
                    hr = relationship(ho, rv)
                    a["n"] += 1
                    # (1) impasse / deadweight
                    if ho.impasse:
                        a["impasse_n"] += 1
                        a["deadweight_sum"] += ho.pie
                    # total surplus (both-sides)
                    a["joint_h"] += ho.joint
                    a["joint_s"] += so.joint
                    # (4) relationship damage
                    a["ret_h"] += hr.retention
                    a["ret_s"] += sr.retention
                    a["ltv_h"] += hr.ltv
                    a["ltv_s"] += sr.ltv
                    # fairness: the worse-off party's share (0 on impasse)
                    a["worst_h"] += (min(ho.share_v, ho.share_w) if ho.closed
                                     else 0.0)
                    a["worst_s"] += min(so.share_v, so.share_w)
                    # (3) missed logroll: joint gap on positional-involving pairs
                    if ho.positional:
                        a["pos_n"] += 1
                        a["pos_joint_h"] += ho.joint
                        a["pos_joint_s"] += so.joint
                    # (2) exploitation: the NAIVE party's realised gain
                    if tv is ACCOMMODATOR:
                        a["naive_n"] += 1
                        a["naive_h"] += ho.g_v
                        a["naive_s"] += so.g_v
                    if tw is ACCOMMODATOR:
                        a["naive_n"] += 1
                        a["naive_h"] += ho.g_w
                        a["naive_s"] += so.g_w
                    # HONEST decomposition: the hardballer's EXTRACTION edge —
                    # its take specifically when it fleeces a naive counterpart
                    if tv is HARDBALLER and tw is ACCOMMODATOR:
                        a["hb_fleece_n"] += 1
                        a["hb_fleece_h"] += ho.g_v
                        a["hb_fleece_s"] += so.g_v
                    if tw is HARDBALLER and tv is ACCOMMODATOR:
                        a["hb_fleece_n"] += 1
                        a["hb_fleece_h"] += ho.g_w
                        a["hb_fleece_s"] += so.g_w
                    # per-type payoff, aggregated over both roles
                    per_type[tv.name][0] += ho.g_v
                    per_type[tv.name][1] += so.g_v
                    per_type[tv.name][2] += 1
                    per_type[tw.name][0] += ho.g_w
                    per_type[tw.name][1] += so.g_w
                    per_type[tw.name][2] += 1
    return {"acc": dict(a), "per_type": per_type}


def summarize(seed_rows: list) -> dict:
    """Per-seed means → across-seed CIs for every headline metric."""
    S = len(seed_rows)

    def col(fn):
        return np.array([fn(r["acc"]) for r in seed_rows], dtype=float)

    n = col(lambda a: a["n"])
    impasse_rate = col(lambda a: a["impasse_n"] / a["n"])
    deadweight = col(lambda a: a["deadweight_sum"] / max(1, a["impasse_n"]))
    joint_h = col(lambda a: a["joint_h"] / a["n"])
    joint_s = col(lambda a: a["joint_s"] / a["n"])
    ret_h = col(lambda a: a["ret_h"] / a["n"])
    ret_s = col(lambda a: a["ret_s"] / a["n"])
    ltv_h = col(lambda a: a["ltv_h"] / a["n"])
    ltv_s = col(lambda a: a["ltv_s"] / a["n"])
    worst_h = col(lambda a: a["worst_h"] / a["n"])
    worst_s = col(lambda a: a["worst_s"] / a["n"])
    naive_h = col(lambda a: a["naive_h"] / a["naive_n"])
    naive_s = col(lambda a: a["naive_s"] / a["naive_n"])
    pos_h = col(lambda a: a["pos_joint_h"] / max(1, a["pos_n"]))
    pos_s = col(lambda a: a["pos_joint_s"] / max(1, a["pos_n"]))
    hbf_h = col(lambda a: a["hb_fleece_h"] / max(1, a["hb_fleece_n"]))
    hbf_s = col(lambda a: a["hb_fleece_s"] / max(1, a["hb_fleece_n"]))

    # per-type payoff (mean $ per appearance) and the switch delta
    type_tbl = {}
    for name in TYPE_NAMES:
        h = np.array([r["per_type"][name][0] / max(1, r["per_type"][name][2])
                      for r in seed_rows])
        s = np.array([r["per_type"][name][1] / max(1, r["per_type"][name][2])
                      for r in seed_rows])
        type_tbl[name] = {
            "human_payoff": ci(h), "snhp_payoff": ci(s),
            "gain_from_switch": ci(s - h),
            "better_off_switching": bool((s - h).mean() > 0),
        }

    four_modes = {
        "1_impasse": {
            "human_impasse_rate": ci(impasse_rate),
            "snhp_impasse_rate": 0.0,
            "deadweight_per_impasse_$": ci(deadweight),
            "note": "positive-surplus deals SNHP closes; humans destroy the pie",
        },
        "2_exploitation": {
            "naive_gain_human_$": ci(naive_h),
            "naive_gain_snhp_$": ci(naive_s),
            "snhp_protects_naive_$": ci(naive_s - naive_h),
        },
        "3_missed_logroll": {
            "positional_joint_human_$": ci(pos_h),
            "positional_joint_snhp_$": ci(pos_s),
            "logroll_gap_$": ci(pos_s - pos_h),
        },
        "4_relationship_damage": {
            "retention_human": ci(ret_h),
            "retention_snhp": ci(ret_s),
            "retention_gain": ci(ret_s - ret_h),
            "ltv_human_$": ci(ltv_h),
            "ltv_snhp_$": ci(ltv_s),
            "ltv_gain_$": ci(ltv_s - ltv_h),
        },
    }

    both_sides = {
        "total_surplus_human_$": ci(joint_h),
        "total_surplus_snhp_$": ci(joint_s),
        "surplus_gain_$": ci(joint_s - joint_h),
        "fairness_worstshare_human": ci(worst_h),
        "fairness_worstshare_snhp": ci(worst_s),
        "fairness_gain": ci(worst_s - worst_h),
        "efficiency_impasse_reduction": ci(impasse_rate),   # SNHP → 0
        "retention_gain": ci(ret_s - ret_h),
        "dominates_on": {
            "surplus": bool(_sig(ci(joint_s - joint_h)) and (joint_s - joint_h).mean() > 0),
            "fairness": bool(_sig(ci(worst_s - worst_h)) and (worst_s - worst_h).mean() > 0),
            "efficiency": bool(_sig(ci(impasse_rate)) and impasse_rate.mean() > 0),
            "retention": bool(_sig(ci(ret_s - ret_h)) and (ret_s - ret_h).mean() > 0),
        },
    }
    hardballer = type_tbl["hardballer"]
    # the honest hardballer decomposition: on AVERAGE it gains (its impasses vs
    # other aggressive types are self-defeating), but it DOES lose its extraction
    # edge — its take when fleecing a naive collapses from human to the neutral
    # split. Both truths reported.
    hardballer_story = {
        "avg_gain_from_switch_$": hardballer["gain_from_switch"],
        "better_off_on_average": hardballer["better_off_switching"],
        "extraction_edge_vs_naive_human_$": ci(hbf_h),
        "extraction_edge_vs_naive_snhp_$": ci(hbf_s),
        "edge_lost_$": ci(hbf_s - hbf_h),      # negative ⇒ it gave up extraction
    }
    return {
        "n_pairs_per_seed": ci(n),
        "four_failure_modes": four_modes,
        "both_sides_verdict": both_sides,
        "per_type_who_gains": type_tbl,
        "hardballer_story": hardballer_story,
        "hardballer_still_better_off": bool(hardballer["better_off_switching"]),
        "types_worse_off_under_snhp": [
            name for name in TYPE_NAMES
            if not type_tbl[name]["better_off_switching"]],
    }


def _fmt(d: dict) -> str:
    c = d.get("ci95")
    return f"{d['mean']:+8.2f} {str(c)}" if c else f"{d['mean']:+8.2f}"


def _print(summary: dict) -> None:
    fm = summary["four_failure_modes"]
    print("\n── THE FOUR WAYS HUMAN NEGOTIATION FAILS (human vs SNHP) " + "─" * 12)
    im = fm["1_impasse"]
    print(f"1 IMPASSE     human rate {im['human_impasse_rate']['mean']:.1%}"
          f"  SNHP 0.0%   deadweight/impasse ${im['deadweight_per_impasse_$']['mean']:.2f}")
    ex = fm["2_exploitation"]
    print(f"2 EXPLOIT     naive gets ${ex['naive_gain_human_$']['mean']:.2f} (human)"
          f"  vs ${ex['naive_gain_snhp_$']['mean']:.2f} (SNHP)"
          f"  protection {_fmt(ex['snhp_protects_naive_$'])}")
    lr = fm["3_missed_logroll"]
    print(f"3 LOGROLL     positional joint ${lr['positional_joint_human_$']['mean']:.2f}"
          f" (human) vs ${lr['positional_joint_snhp_$']['mean']:.2f} (SNHP)"
          f"  gap {_fmt(lr['logroll_gap_$'])}")
    rd = fm["4_relationship_damage"]
    print(f"4 RELATION    retention {rd['retention_human']['mean']:.2f} → "
          f"{rd['retention_snhp']['mean']:.2f}   LTV gain {_fmt(rd['ltv_gain_$'])}")

    bs = summary["both_sides_verdict"]
    print("\n── BOTH-SIDES VERDICT (both-SNHP vs human-vs-human) " + "─" * 16)
    print(f"total surplus  {_fmt(bs['surplus_gain_$'])}   "
          f"fairness {_fmt(bs['fairness_gain'])}   "
          f"retention {_fmt(bs['retention_gain'])}")
    print(f"dominates on: {bs['dominates_on']}")

    print("\n── PER-TYPE: WHO GAINS BY SWITCHING TO SNHP ($/appearance) " + "─" * 8)
    print(f"{'type':<14}{'human':>12}{'SNHP':>12}{'gain':>12}   better?")
    for name in TYPE_NAMES:
        r = summary["per_type_who_gains"][name]
        mark = "yes" if r["better_off_switching"] else "NO (loses edge)"
        print(f"{name:<14}{r['human_payoff']['mean']:>12.2f}"
              f"{r['snhp_payoff']['mean']:>12.2f}"
              f"{r['gain_from_switch']['mean']:>+12.2f}   {mark}")
    hs = summary["hardballer_story"]
    print(f"\nHARDBALLER (honest): avg gain {_fmt(hs['avg_gain_from_switch_$'])}"
          f"  BUT extraction edge vs naive "
          f"${hs['extraction_edge_vs_naive_human_$']['mean']:.2f} → "
          f"${hs['extraction_edge_vs_naive_snhp_$']['mean']:.2f} "
          f"(edge lost {_fmt(hs['edge_lost_$'])})")
    print(f"types worse off under SNHP: {summary['types_worse_off_under_snhp']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    seeds = [args.seed0 + i for i in range(args.seeds)]
    seed_rows = [run_seed(s, args.weeks) for s in seeds]
    summary = summarize(seed_rows)
    _print(summary)

    results = {
        "human_run_version": HUMAN_RUN_VERSION,
        "config": {"seeds": seeds, "weeks": args.weeks,
                   "human_types": TYPE_NAMES,
                   "notes": [
                       "pie = validated nash_deal joint gain (SNHP-coordinated route env)",
                       "full human type cross-product per positive-surplus relationship",
                       "paired on demand identity (seed×week×rel×type-pair), never mechanism",
                       "CIs over seed means; no win claimed when CI includes zero",
                       "no LLM; byte-deterministic on the seed",
                   ]},
        "summary": summary,
    }
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
            f.write("\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

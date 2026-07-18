"""The /science experiments — E1 calibrated abstention, E2 budget curve +
biased humans, E3 pettiness-tax population (research/demo-experiments-plan.md).

REGISTRATION DISCIPLINE: the thresholds below are FROZEN BY THE COMMIT THAT
INTRODUCES THIS FILE, before any result in results-science JSONs exists.
Bidirectional kills; a fired kill retires the associated public claim.

Usage:
    python3 -m divorce.science_eval --seed 7        # one seed (writes partial)
    python3 -m divorce.science_eval --aggregate     # combine + apply kills
"""
from __future__ import annotations

import argparse
import itertools
import json
import os

import numpy as np

from divorce import arms, elicit, personas

OUT_DIR = os.path.dirname(__file__)
WEB_JSON = os.path.join(OUT_DIR, "..", "arena", "web", "divorce",
                        "science-data.json")

REGISTRATION = {
    "frozen_by": "the commit introducing this file, before any results exist",
    "population": "the frozen kill-harness population: N=100/seed, seeds "
                  "7/11/23 (committed) + FRESH confirmatory seed 31; "
                  "qualified pairs only; v2 all-choices elicitation",
    "budgets": [6, 10, 24],
    "E1_calibrated_abstention": {
        "certified": "ARM-B settled (proposal ratified by both true-IR checks)",
        "selective_risk": "P(either true walk-away violated | certified)",
        "KILL_UP": "if selective risk > 0.02 at the shipped gate (Q=10) -> "
                   "retire the word 'calibrated'; it's just a threshold",
        "recoverable_abstention": "an abstained pair where an outcome exists "
                   "in the mediator's OWN final confident set (pessimistic "
                   "margins >= 0 at its final posteriors) that also clears "
                   "BOTH true walk-aways — i.e. it held a certifiable deal "
                   "and failed to certify it",
        "KILL_DOWN": "if recoverable-abstention rate among abstentions > 0.15 "
                     "at Q=10 -> the gate is uncalibrated pessimism, not "
                     "information-limited caution; do not claim calibration",
    },
    "E2_budget_curve": {
        "curve": "median S_B/S_O vs questions/side, settle rate overlaid, "
                 "from the SAME runs as E1 (no separate population)",
        "biased_human_model": "anchoring kappa=0.30 on cash-for-asset "
                 "trades, 0.10 on cash riders inside package choices; "
                 "acquiescence drift 0.10 toward accepting cash offers; "
                 "1.5x comparison noise (frozen constants below)",
        "KILL": "drop the 'human-robust' claim if v2-under-bias median "
                "capture <= v1-under-honest median capture at Q=10",
    },
    "E3_pettiness_tax": {
        "tax": "per-side oracle-vs-oracle despiked counterfactual "
               "(arms.pettiness_tax v3), aggregated over qualified pairs "
               "with a settled ARM-O",
        "headline_metric": "median over pairs of max(tax_a, tax_b) / S_O",
        "KILL_DOWN": "if the headline median < 0.05 -> the tax is a rounding "
                     "error at this population; do not headline it",
        "KILL_UP_stability": "if the median absolute tax varies by more than "
                     "3x across the three committed seeds -> report ranges, "
                     "never a single number",
        "attribution_flag": "report median count of non-hill assets whose "
                     "allocation moves > 0.25 share between actual and "
                     "despiked oracle settlements; if > 2 of 5, the write-up "
                     "must present the tax as a bundle-level counterfactual, "
                     "not an item-level one (a labeling duty, not a kill)",
    },
}

SEEDS_COMMITTED = [7, 11, 23]
SEED_FRESH = 31
BIAS = {"K_CASH": 0.30, "K_BUNDLE": 0.10, "YES_DRIFT": 0.10, "TAU": 0.15}


# ── biased-human answerer (frozen constants; reproducible) ──────────────────
class BiasedHuman:
    def __init__(self, values: dict[str, float], uid: int):
        self.v = dict(values)
        self.rng = np.random.default_rng((uid * 2654435761) & 0x7FFFFFFF)

    def _sig(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))

    def answer_linear(self, weights, sweetener):
        d = sum(w * self.v[a] for a, w in weights.items()) + sweetener
        cash_only = sum(1 for w in weights.values() if abs(w) > 1e-12) == 1
        k = BIAS["K_CASH"] if cash_only else BIAS["K_BUNDLE"]
        d *= (1 - k)
        scale = sum(abs(w) * self.v[a] for a, w in weights.items()) + abs(sweetener)
        p = self._sig(d / (BIAS["TAU"] * max(scale * 0.5, 200.0)))
        if cash_only and sweetener < 0:
            p = max(p - BIAS["YES_DRIFT"], 0.0)
        return bool(self.rng.random() < p)

    # v1 interfaces (for the v1-under-honest baseline we compare against we
    # use elicit.make_answerer_v1; BiasedHuman only serves the v2 arm here)


def _pairs(seed: int):
    combos = list(itertools.product(personas.ARCHETYPE_NAMES, repeat=2))
    out = []
    for i in range(100):
        rng = np.random.default_rng([seed, i])
        pr = personas.sample_pair(rng, *combos[i % len(combos)])
        if pr["qualified"]:
            out.append((i, pr["a"], pr["b"]))
    return out


def _pess_margin(bands, lam, fight, shares, omega=0.0):
    return (1.0 + lam) * sum(
        (s - 0.5 - omega) * (bands[a][0] if s - 0.5 - omega > 0 else bands[a][2])
        for a, s in shares.items() if a != "wallet"
    ) + (1.0 + lam) * (shares.get("wallet", 0.5) - 0.5 - omega) * arms.WALLET_VALUE + fight


def run_seed(seed: int) -> dict:
    prior = elicit.build_asset_prior()
    outcomes = arms.enumerate_outcomes()
    pairs = _pairs(seed)
    rec = {"seed": seed, "n_qualified": len(pairs), "budgets": {},
           "tax": [], "recoverable": {"abstained": 0, "recoverable": 0},
           "bias_panel": {"v2_biased": [], "v1_honest": []}}

    for i, pa, pb in pairs:
        so = arms.run_arm_o(pa, pb, outcomes)
        if not (so["settled"] and so["joint_surplus"] > 1e-9):
            continue
        s_o = so["joint_surplus"]

        # ── E3: the tax + attribution drift ──
        tax = arms.pettiness_tax(pa, pb, outcomes, actual_o=so)
        drift = {}
        for label, p in (("a", pa), ("b", pb)):
            import copy
            clone = copy.deepcopy(p)
            clone.values[clone.hill] -= (clone.hill_mult - 1.0) * clone.market_values[clone.hill]
            clone.__post_init__()
            da, db = (clone, pb) if label == "a" else (pa, clone)
            cf = arms.run_arm_o(da, db, outcomes)
            if cf["settled"]:
                drift[label] = sum(
                    1 for a in personas.ASSET_NAMES
                    if a != "wallet" and a != p.hill
                    and abs(cf["shares_a"][a] - so["shares_a"][a]) > 0.25)
        rec["tax"].append({
            "i": i, "tax_a": tax["a"], "tax_b": tax["b"], "s_o": s_o,
            "headline_ratio": max(tax["a"], tax["b"]) / s_o,
            "drift_nonhill": max(drift.values()) if drift else 0,
        })

        # ── E1 + E2: risk-coverage / capture across budgets ──
        for q in REGISTRATION["budgets"]:
            rb = elicit.run_arm_b(pa, pb, prior, (seed, i), budget=q,
                                  outcomes=outcomes)
            b = rec["budgets"].setdefault(str(q), {
                "n": 0, "certified": 0, "violations": 0, "ratios": []})
            b["n"] += 1
            if rb["settled"]:
                b["certified"] += 1
                if not (rb["u_a"] >= pa.walk_away and rb["u_b"] >= pb.walk_away):
                    b["violations"] += 1
            b["ratios"].append(rb["joint_surplus"] / s_o)

            # recoverable-abstention analysis at the shipped gate only
            if q == 10 and not rb["settled"]:
                rec["recoverable"]["abstained"] += 1
                med = elicit.mediate(
                    prior,
                    elicit.make_answerer(pa, uid=seed * 100_003 + 2 * i),
                    elicit.make_answerer(pb, uid=seed * 100_003 + 2 * i + 1),
                    {"lam": pa.lam, "fight_cost": pa.fight_cost,
                     "optimism": pa.optimism},
                    {"lam": pb.lam, "fight_cost": pb.fight_cost,
                     "optimism": pb.optimism},
                    10, outcomes)
                fb = med.get("final_bands")
                if fb:
                    def flip(o):
                        return {a: 1.0 - s for a, s in o.items()}
                    for o in outcomes:
                        pm_a = _pess_margin(fb["a"], pa.lam, pa.fight_cost, o,
                                            pa.optimism)
                        pm_b = _pess_margin(fb["b"], pb.lam, pb.fight_cost,
                                            flip(o), pb.optimism)
                        if pm_a >= 0 and pm_b >= 0 \
                                and pa.utility(o) >= pa.walk_away \
                                and pb.utility(flip(o)) >= pb.walk_away:
                            rec["recoverable"]["recoverable"] += 1
                            break

        # ── E2 biased-human panel (Q=10 only) ──
        rb_bias = elicit.run_arm_b(
            pa, pb, prior, (seed, i), budget=10, outcomes=outcomes,
            make=lambda p, uid: BiasedHuman(
                {a: p.values[a] for a in elicit.ELICITABLE}, uid))
        rec["bias_panel"]["v2_biased"].append(rb_bias["joint_surplus"] / s_o)
        rb_v1 = elicit.run_arm_b(
            pa, pb, prior, (seed, i), budget=10, outcomes=outcomes,
            elicit_fn=elicit.elicit, make=elicit.make_answerer_v1)
        rec["bias_panel"]["v1_honest"].append(rb_v1["joint_surplus"] / s_o)

    path = os.path.join(OUT_DIR, f"results-science-seed{seed}.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=1)
    print(f"seed {seed}: wrote {path}")
    return rec


def aggregate() -> None:
    seeds = SEEDS_COMMITTED + [SEED_FRESH]
    recs = []
    for s in seeds:
        p = os.path.join(OUT_DIR, f"results-science-seed{s}.json")
        if os.path.exists(p):
            recs.append(json.load(open(p)))
    med = lambda xs: float(np.median(xs)) if xs else None  # noqa: E731

    curve = {}
    for q in REGISTRATION["budgets"]:
        n = sum(r["budgets"][str(q)]["n"] for r in recs)
        cert = sum(r["budgets"][str(q)]["certified"] for r in recs)
        viol = sum(r["budgets"][str(q)]["violations"] for r in recs)
        ratios = [x for r in recs for x in r["budgets"][str(q)]["ratios"]]
        curve[str(q)] = {"coverage": cert / n, "selective_risk":
                         (viol / cert if cert else 0.0),
                         "capture_median": med(ratios), "n": n}

    abst = sum(r["recoverable"]["abstained"] for r in recs)
    reco = sum(r["recoverable"]["recoverable"] for r in recs)
    taxes = [t for r in recs for t in r["tax"]]
    tax_medians_by_seed = [med([max(t["tax_a"], t["tax_b"]) for t in r["tax"]])
                           for r in recs[:3]]
    v2b = [x for r in recs for x in r["bias_panel"]["v2_biased"]]
    v1h = [x for r in recs for x in r["bias_panel"]["v1_honest"]]

    e1_up = curve["10"]["selective_risk"] > 0.02
    e1_down = (reco / abst > 0.15) if abst else False
    e3_headline = med([t["headline_ratio"] for t in taxes])
    e3_down = e3_headline < 0.05
    stab = (max(tax_medians_by_seed) / max(min(tax_medians_by_seed), 1.0)
            if len(tax_medians_by_seed) == 3 else None)
    e3_up = stab is not None and stab > 3.0
    e2_kill = med(v2b) <= med(v1h)

    out = {
        "registration": REGISTRATION,
        "seeds": seeds,
        "E1": {"risk_coverage": curve,
               "abstained_at_10": abst, "recoverable": reco,
               "recoverable_rate": (reco / abst if abst else 0.0),
               "KILL_UP_fires": bool(e1_up), "KILL_DOWN_fires": bool(e1_down)},
        "E2": {"capture_curve": {q: curve[q]["capture_median"] for q in curve},
               "v2_biased_median": med(v2b), "v1_honest_median": med(v1h),
               "KILL_fires": bool(e2_kill)},
        "E3": {"n": len(taxes),
               "headline_median_ratio": e3_headline,
               "median_tax_abs": med([max(t["tax_a"], t["tax_b"]) for t in taxes]),
               "tax_distribution": sorted(
                   round(max(t["tax_a"], t["tax_b"])) for t in taxes),
               "median_drift_nonhill": med([t["drift_nonhill"] for t in taxes]),
               "seed_stability_ratio": stab,
               "KILL_DOWN_fires": bool(e3_down), "KILL_UP_fires": bool(e3_up)},
    }
    path = os.path.join(OUT_DIR, "results-science.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    # the page's copy (adds the committed trap-check numbers for the lede)
    trap = json.load(open(os.path.join(OUT_DIR, "results-trap-check.json")))
    out["trap_check"] = trap["summary"]
    with open(WEB_JSON, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("E1", "E2", "E3")}, indent=1))
    print(f"wrote {path} and {WEB_JSON}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--aggregate", action="store_true")
    a = ap.parse_args()
    if a.aggregate:
        aggregate()
    elif a.seed is not None:
        run_seed(a.seed)
    else:
        raise SystemExit("--seed N or --aggregate")


if __name__ == "__main__":
    main()

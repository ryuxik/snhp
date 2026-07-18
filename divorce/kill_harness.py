"""The pre-registered kill harness (SPEC.md §8) — steps 1+2 of the build order.

Runs ARM-I (item-by-item), ARM-O (oracle bundle) and ARM-B (mediated bundle
from ELICITED posteriors, honest + bluff variants) over a stratified seeded
persona population, LLM-free, and evaluates K1–K4.

STATUS: PILOT. Thresholds below are the registration PROPOSAL — they are
frozen (founder call, SPEC.md §11.1) only after the 20-pair pilot, and BEFORE
any chrome is built. Until then every number this prints is labeled pilot.

Usage:
    python3 -m divorce.kill_harness --n 20 --seed 7      # pilot
    python3 -m divorce.kill_harness --n 100 --seed 7     # registered scale
"""
from __future__ import annotations

import argparse
import itertools
import json
import os

import numpy as np

from divorce import arms, elicit, personas

REGISTRATION = {
    "status": "FROZEN 2026-07-17 — thresholds committed before chrome build; "
              "confirmatory run on a fresh seed follows the freeze commit. "
              "2026-07-18: population re-anchored to realistic retail values "
              "(additive sentiment stacking, shared per-pair market, "
              "market-multiple contested criterion); SAME kill thresholds, "
              "full re-run on all four seeds — committed before results.",
    "population": {"n_pairs": 100, "seed": 7,
                   "stratification": "5x5 ordered archetype grid, cycled"},
    "qualification": {"contested_mult": 2.0, "min_contested": 2,
                      "max_resamples": 50},
    "protocol": {"exchange_budget": arms.EXCHANGE_BUDGET,
                 "open_demand": arms.OPEN_DEMAND,
                 "demand_decay": arms.DEMAND_DECAY,
                 "accept_noise_sd": arms.ACCEPT_NOISE_SD,
                 "transfer_step": arms.TRANSFER_STEP},
    "elicitation": {"q_budget_per_side": elicit.Q_BUDGET,
                    "cal_seed": elicit.CAL_SEED, "cal_n": elicit.CAL_N,
                    "pool": "v2 all-choices (linear package choices w/ cash "
                            "riders) — adopted post-freeze after the "
                            "biased-human K3 result; revalidated on seeds "
                            "7/11/23 rather than grandfathered",
                    "bluff_policy": f"hill intensity x{elicit.BLUFF_HILL_MULT}, "
                                    "stated lam/walk_away truthful"},
    "kills": {
        # K1 forward kill: the deadlock must be real. Fires if ARM-I fully
        # settles (with true IR) at >= the bundle arm's settle rate - 5pp.
        "K1_margin_pp": 5,
        # K2 reverse kill: the bundle must clear. (True-IR half needs ARM-B;
        # the surplus half is previewed here against the ARM-O ceiling.)
        "K2_ir_violation_max": 0.10,
        "K2_min_median_advantage": 0.15,   # (S_B - S_I) / S_O, median
        # K3/K4 need elicitation (step 2); registered in SPEC.md §8.
        "K3_min_elicited_over_oracle": 0.80,
        "K4_max_bluff_gain": 0.10,
    },
}


def _py(x):
    """JSON-safe: numpy scalars -> python, dicts/lists recursively."""
    if isinstance(x, dict):
        return {k: _py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_py(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def run_population(n_pairs: int, seed: int) -> dict:
    combos = list(itertools.product(personas.ARCHETYPE_NAMES, repeat=2))
    outcomes = arms.enumerate_outcomes()
    prior = elicit.build_asset_prior()
    q = REGISTRATION["qualification"]
    pairs = []
    for i in range(n_pairs):
        arch_a, arch_b = combos[i % len(combos)]
        rng = np.random.default_rng([seed, i])
        pair = personas.sample_pair(rng, arch_a, arch_b,
                                    contested_mult=q["contested_mult"],
                                    min_contested=q["min_contested"],
                                    max_resamples=q["max_resamples"])
        pa, pb = pair["a"], pair["b"]
        res_i = arms.run_arm_i(pa, pb, rng)
        res_o = arms.run_arm_o(pa, pb, outcomes)
        res_b = elicit.run_arm_b(pa, pb, prior, (seed, i),
                                 budget=elicit.Q_BUDGET, outcomes=outcomes)
        res_b_bluff = elicit.run_arm_b(pa, pb, prior, (seed, i), bluff_a=True,
                                       budget=elicit.Q_BUDGET, outcomes=outcomes)
        tax = (arms.pettiness_tax(pa, pb, outcomes, actual_o=res_o)
               if res_o["settled"] else {"a": 0.0, "b": 0.0})
        pairs.append({
            "i": i, "arch_a": arch_a, "arch_b": arch_b,
            "qualified": pair["qualified"], "attempts": pair["attempts"],
            "contested": pair["contested"], "fronts": pair["fronts"],
            "hills": {"a": pa.hill, "b": pb.hill},
            "walk_a": pa.walk_away, "walk_b": pb.walk_away,
            "arm_i": {k: res_i[k] for k in
                      ("settled_fraction", "fully_settled", "joint_surplus",
                       "ir_a", "ir_b", "per_item_exchanges", "unsettled")},
            "arm_o": {k: res_o[k] for k in
                      ("settled", "joint_surplus", "ir_a", "ir_b",
                       "ef_a", "ef_b")},
            "arm_b": {k: res_b[k] for k in
                      ("settled", "rejected", "proposed", "joint_surplus",
                       "u_a", "u_b", "ef_a", "ef_b", "n_questions")},
            "arm_b_bluff_a": {k: res_b_bluff[k] for k in
                              ("settled", "rejected", "u_a", "joint_surplus")},
            "pettiness_tax": tax,
        })
    return {"pairs": pairs}


def evaluate(pop: dict) -> dict:
    pairs = [p for p in pop["pairs"] if p["qualified"]]
    n = len(pairs)
    if n == 0:
        return {"error": "no qualified pairs — the sampler cannot construct "
                         "the registered opposition; that is itself a finding"}

    i_full_ir = [p for p in pairs
                 if p["arm_i"]["fully_settled"]
                 and p["arm_i"]["ir_a"] and p["arm_i"]["ir_b"]]
    o_settled = [p for p in pairs if p["arm_o"]["settled"]]
    b_settled = [p for p in pairs if p["arm_b"]["settled"]]
    b_rejected = [p for p in pairs if p["arm_b"]["rejected"]]
    rate_i = len(i_full_ir) / n
    rate_o = len(o_settled) / n
    rate_b = len(b_settled) / n
    reject_rate = len(b_rejected) / n

    adv, k3_ratio = [], []
    for p in pairs:
        s_o = p["arm_o"]["joint_surplus"]
        if p["arm_o"]["settled"] and s_o > 1e-9:
            adv.append((p["arm_b"]["joint_surplus"]
                        - p["arm_i"]["joint_surplus"]) / s_o)
            k3_ratio.append(p["arm_b"]["joint_surplus"] / s_o)
    median_adv = float(np.median(adv)) if adv else None
    median_k3 = float(np.median(k3_ratio)) if k3_ratio else None

    # K4: same pair, side A's elicitation answers distorted vs honest.
    gains = []
    for p in pairs:
        honest = p["arm_b"]["u_a"] - p["walk_a"]
        bluffed = p["arm_b_bluff_a"]["u_a"] - p["walk_a"]
        gains.append((bluffed - honest) / max(1.0, abs(honest)))
    median_bluff_gain = float(np.median(gains)) if gains else None
    bluff_reject_rate = (sum(1 for p in pairs if p["arm_b_bluff_a"]["rejected"])
                         / n)

    kills = REGISTRATION["kills"]
    k1_fires = rate_i >= rate_b - kills["K1_margin_pp"] / 100.0
    k2_ir_fires = reject_rate > kills["K2_ir_violation_max"]
    k2_surplus_fires = (median_adv is not None
                        and median_adv < kills["K2_min_median_advantage"])
    k3_fires = (median_k3 is not None
                and median_k3 < kills["K3_min_elicited_over_oracle"])
    k4_manipulation_pays = (median_bluff_gain is not None
                            and median_bluff_gain > kills["K4_max_bluff_gain"])

    ef_both = [p for p in o_settled if p["arm_o"]["ef_a"] and p["arm_o"]["ef_b"]]
    ef_both_b = [p for p in b_settled if p["arm_b"]["ef_a"] and p["arm_b"]["ef_b"]]
    taxes = [max(p["pettiness_tax"]["a"], p["pettiness_tax"]["b"])
             for p in o_settled]
    dog_exchanges = [p["arm_i"]["per_item_exchanges"].get("dog", 0) for p in pairs]

    return {
        "n_pairs": len(pop["pairs"]), "n_qualified": n,
        "qualified_rate": n / len(pop["pairs"]),
        "mean_resample_attempts": float(np.mean([p["attempts"] for p in pairs])),
        "contested_count_dist": _dist([len(p["contested"]) for p in pairs]),
        "ARM_I": {
            "full_settle_with_IR_rate": rate_i,
            "settled_fraction_median": float(np.median(
                [p["arm_i"]["settled_fraction"] for p in pairs])),
            "dog_exchanges_median": float(np.median(dog_exchanges)),
            "most_common_unsettled": _dist(
                [a for p in pairs for a in p["arm_i"]["unsettled"]]),
        },
        "ARM_O": {
            "settle_rate": rate_o,
            "no_decree_rate": 1.0 - rate_o,
            "ef_both_rate": (len(ef_both) / len(o_settled)) if o_settled else None,
            "median_joint_surplus": float(np.median(
                [p["arm_o"]["joint_surplus"] for p in o_settled])) if o_settled else None,
            "median_pettiness_tax": float(np.median(taxes)) if taxes else None,
        },
        "ARM_B": {
            "settle_rate": rate_b,
            "proposal_rejected_rate": reject_rate,
            "ef_both_rate": (len(ef_both_b) / len(b_settled)) if b_settled else None,
            "median_joint_surplus": float(np.median(
                [p["arm_b"]["joint_surplus"] for p in b_settled])) if b_settled else None,
            "median_questions": float(np.median(
                [p["arm_b"]["n_questions"] for p in pairs])),
        },
        "kills": {
            "K1_deadlock_is_real": {
                "fires": bool(k1_fires),
                "arm_i_rate": rate_i, "arm_b_rate": rate_b,
            },
            "K2_bundle_clears": {
                "ir_half_fires": bool(k2_ir_fires),
                "proposal_rejected_rate": reject_rate,
                "surplus_half_fires": bool(k2_surplus_fires),
                "median_advantage_of_oracle_headroom": median_adv,
            },
            "K3_elicitation_load_bearing": {
                "fires": bool(k3_fires),
                "median_elicited_over_oracle": median_k3,
                "q_budget_per_side": elicit.Q_BUDGET,
            },
            "K4_bluff": {
                "manipulation_pays": bool(k4_manipulation_pays),
                "median_bluff_gain_frac": median_bluff_gain,
                "bluff_reject_rate": bluff_reject_rate,
                "honest_reject_rate": reject_rate,
                "note": "if manipulation_pays: no manipulation-resistance "
                        "language anywhere in the demo, ever",
            },
        },
    }


def _dist(values: list) -> dict:
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=REGISTRATION["population"]["n_pairs"])
    ap.add_argument("--seed", type=int, default=REGISTRATION["population"]["seed"])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "results-pilot.json"))
    args = ap.parse_args()

    pop = run_population(args.n, args.seed)
    summary = evaluate(pop)
    report = {"registration": REGISTRATION,
              "run": {"n": args.n, "seed": args.seed},
              "summary": summary, "pairs": pop["pairs"]}
    with open(args.out, "w") as f:
        json.dump(_py(report), f, indent=1)

    print(json.dumps(_py(summary), indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

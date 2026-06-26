"""
Dispute-resolution scenario generator.

Generates synthetic consumer-dispute scenarios — refund disputes on
delivery and e-commerce platforms — with concrete dollar figures, a
human-readable narrative, and the platform's economics: the disputed
value, the platform's lowball first offer, and its true walk-away cost
(what NOT settling actually costs it). The gap between the lowball and
the walk-away cost is the Zone of Possible Agreement a negotiation runs
inside.

This generator deliberately does NOT score scenarios or report a
"lift". An earlier version multiplied a per-scenario Pareto ceiling by
assumed efficiency constants (0.89 for vanilla descent, 1.01 for the
SNHP scaffold) and reported the difference as a measured "+0.137
joint-welfare lift, scaffold beats vanilla in 99.4%". Those numbers
were arithmetic on the assumed constants — `1.01 - 0.89` — not a
measurement of anything. Negotiation outcomes are produced by running
the real negotiation core (gametheory/negotiation/dispute_sim.py) on a
scenario; they are never assumed here.

The platform-economics figures (chargeback fee, handling cost,
chargeback premium, retention exposure) are a TRANSPARENT MODEL with
stated assumptions, not measured data. They are emitted verbatim under
the "assumptions" key of the output so any consumer can see them.

No LLM calls, no API cost.
Run:  python3 snhp/cs_negotiation_dataset.py --n 200
"""
from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass

import dispute_economics as econ


# ─── Dispute archetypes ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Archetype:
    key: str
    label: str
    narrative: str              # slots: {total}, {detail}
    order_total_lo: float
    order_total_hi: float
    disputed_frac_lo: float     # disputed value as a fraction of the order total
    disputed_frac_hi: float
    lowball_frac_lo: float      # first offer as a fraction of the disputed value
    lowball_frac_hi: float
    first_offer_form: str       # "credit" | "cash"
    details: tuple[str, ...]


_ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        "missing_items", "Missing items",
        "Your ${total} order arrived with {detail} missing.",
        18.0, 75.0, 0.20, 0.55, 0.30, 0.70, "credit",
        ("the drinks", "a side you paid extra for",
         "one of two entrées", "several items from the receipt"),
    ),
    Archetype(
        "cold_or_spoiled", "Cold or spoiled",
        "Your ${total} order arrived {detail}.",
        16.0, 60.0, 0.40, 0.75, 0.25, 0.60, "credit",
        ("stone cold and inedible", "with a drink spilled through the bag",
         "with a sealed item already past its use-by date"),
    ),
    Archetype(
        "never_arrived", "Never arrived",
        "Your ${total} order was marked delivered, but {detail}.",
        20.0, 90.0, 0.95, 1.00, 0.00, 0.45, "credit",
        ("it never reached your door",
         "the delivery photo shows a building that isn't yours",
         "the courier left it at the wrong address"),
    ),
    Archetype(
        "wrong_order", "Wrong order",
        "You received someone else's order — {detail} — and nothing from your ${total} order.",
        18.0, 80.0, 0.90, 1.00, 0.10, 0.50, "credit",
        ("food from a different restaurant entirely",
         "a bag of completely unrelated items"),
    ),
    Archetype(
        "late_delivery", "Unusably late",
        "Your ${total} order arrived {detail}.",
        20.0, 85.0, 0.45, 0.90, 0.20, 0.55, "credit",
        ("over an hour late and inedible",
         "long after the event it was ordered for"),
    ),
    Archetype(
        "damaged_item", "Damaged or not as described",
        "An item in your ${total} order arrived {detail}.",
        22.0, 120.0, 0.30, 0.65, 0.25, 0.65, "credit",
        ("visibly damaged in transit", "in the wrong size",
         "clearly not as described"),
    ),
    Archetype(
        "billing_overcharge", "Billing overcharge",
        "You were charged ${total}, but {detail}.",
        15.0, 95.0, 0.15, 0.45, 0.10, 0.55, "cash",
        ("a promo code you applied at checkout wasn't honored",
         "the itemised receipt totals less than that",
         "you were charged for the order twice"),
    ),
)

# Realistic mix (sums to 1.0). Missing items + cold food are the bulk of
# delivery disputes; never-arrived and billing are rarer but high-stakes.
_ARCHETYPE_WEIGHTS = {
    "missing_items": 0.30,
    "cold_or_spoiled": 0.22,
    "late_delivery": 0.14,
    "damaged_item": 0.12,
    "never_arrived": 0.10,
    "billing_overcharge": 0.07,
    "wrong_order": 0.05,
}

_CUSTOMER_PROFILES = {
    "loyal_high_ltv": 0.20,
    "established": 0.45,
    "new_acquisition": 0.20,
    "churn_risk": 0.15,
}

_SEVERITIES = {"minor": 0.50, "major": 0.35, "critical": 0.15}


# ─── Generator-specific economics knobs ─────────────────────────────────────
# The shared walk-cost model (chargeback fee, handling, chargeback
# probability, ratio penalty) lives in snhp/dispute_economics.py. The two
# knobs below are generator-only: how the disputed value scales with
# severity, and the per-customer-profile retention exposure fed into the
# shared model.

_SEVERITY_DISPUTED_MULT = {"minor": 0.9, "major": 1.0, "critical": 1.1}
_PROFILE_RETENTION = {
    "loyal_high_ltv": 14.0,
    "established": 5.0,
    "new_acquisition": 6.0,
    "churn_risk": 10.0,
}

_ASSUMPTIONS = {
    "note": (
        "Platform-economics figures are a transparent model, not measured "
        "data. walk_cost = at_risk_value + handling_cost + chargeback_premium "
        "+ retention_exposure (model: snhp/dispute_economics.py). Negotiation "
        "outcomes are NOT in this file — they come from running the real "
        "negotiation core on a scenario."
    ),
    "chargeback_fee_usd": econ.CHARGEBACK_FEE,
    "severity_disputed_multiplier": _SEVERITY_DISPUTED_MULT,
    "severity_handling_cost_usd": econ.SEVERITY_HANDLING_COST,
    "severity_ratio_penalty_usd": econ.SEVERITY_RATIO_PENALTY,
    "severity_chargeback_probability": econ.SEVERITY_CHARGEBACK_PROB,
    "profile_retention_exposure_usd": _PROFILE_RETENTION,
}


def _pick_weighted(d: dict, rng: random.Random) -> str:
    keys = list(d.keys())
    return rng.choices(keys, weights=[d[k] for k in keys], k=1)[0]


def generate_scenario(rng: random.Random, idx: int) -> dict:
    arch_key = _pick_weighted(_ARCHETYPE_WEIGHTS, rng)
    arche = next(a for a in _ARCHETYPES if a.key == arch_key)
    profile = _pick_weighted(_CUSTOMER_PROFILES, rng)
    severity = _pick_weighted(_SEVERITIES, rng)

    order_total = round(rng.uniform(arche.order_total_lo, arche.order_total_hi), 2)
    disputed_frac = rng.uniform(arche.disputed_frac_lo, arche.disputed_frac_hi)
    disputed_value = round(
        min(order_total,
            order_total * disputed_frac * _SEVERITY_DISPUTED_MULT[severity]),
        2,
    )
    lowball_frac = rng.uniform(arche.lowball_frac_lo, arche.lowball_frac_hi)
    first_offer = round(disputed_value * lowball_frac, 2)

    economics = econ.walk_cost_breakdown(
        disputed_value, severity, _PROFILE_RETENTION[profile])
    walk_cost = round(sum(economics.values()), 2)

    detail = rng.choice(arche.details)
    narrative = arche.narrative.format(total=f"{order_total:.2f}", detail=detail)

    return {
        "id": f"dsp-{idx:04d}",
        "archetype": arche.key,
        "archetype_label": arche.label,
        "narrative": narrative,
        "customer_profile": profile,
        "severity": severity,
        "order_total": order_total,
        "disputed_value": disputed_value,
        "platform_first_offer": first_offer,
        "platform_first_offer_form": arche.first_offer_form,
        "platform_walk_cost": walk_cost,
        "platform_economics": economics,
    }


def generate_dataset(n_scenarios: int = 200, seed: int = 42) -> dict:
    rng = random.Random(seed)
    scenarios = [generate_scenario(rng, i + 1) for i in range(n_scenarios)]
    mix: dict[str, int] = {}
    for s in scenarios:
        mix[s["archetype"]] = mix.get(s["archetype"], 0) + 1
    return {
        "n_scenarios": n_scenarios,
        "seed": seed,
        "assumptions": _ASSUMPTIONS,
        "archetype_counts": mix,
        "scenarios": scenarios,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Dispute-resolution scenario generator")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "gametheory", "server", "static", "dispute_scenarios.json",
    ))
    args = p.parse_args()

    print(f"Generating {args.n} dispute scenarios (seed={args.seed})...")
    dataset = generate_dataset(args.n, args.seed)

    print("\n=== ARCHETYPE MIX ===")
    for k, c in sorted(dataset["archetype_counts"].items(), key=lambda x: -x[1]):
        print(f"  {k:<20}  n={c}")

    sample = dataset["scenarios"][0]
    print("\n=== SAMPLE SCENARIO ===")
    print(f"  {sample['narrative']}")
    print(f"  disputed ${sample['disputed_value']:.2f}  "
          f"platform first offer ${sample['platform_first_offer']:.2f}  "
          f"platform walk-away cost ${sample['platform_walk_cost']:.2f}")

    with open(args.out, "w") as f:
        json.dump(dataset, f, indent=2)
    print(f"\nSaved → {args.out}")


if __name__ == "__main__":
    main()

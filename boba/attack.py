"""BOBA P1a — the liar battery.

Mirrors vend's attack battery (vend/RESULTS.md "Attack battery" + H3):
best-response search over strategic_disclosure(wtp_factor, claim_walk),
every buyer deviating, paired days, block CIs — "IC against one deviation
isn't IC." Two questions:

  1. Is honesty the buyer's best response on boba's cart? Sweep the full
     deviation grid (wtp_factor x claim_walk) with EVERY buyer lying the
     same way, and read pooled buyer-utility Δ (consumer_surplus) vs
     all-honest cart.
  2. At what liar SHARE does the venue's gain erode? Fix the best-response
     (or canonical anchoring) deviation and sweep liar_share in stable
     identities keyed on consumer uid (never policy), reading venue
     margin Δ vs all-honest cart.

  python3 -m boba.attack --battery --seed 20260713 --days 30 \
      --out boba/attack-battery.json
  python3 -m boba.attack --liar-sweep --seed 20260713 --days 30 \
      --wtp-factor 1.0 --claim-walk --out boba/liar-sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys

from boba.policies import CartPolicy
from boba.run import PAIRED_METRICS, paired_ci, run_day
from boba.world import BobaConfig

ATTACK_VERSION = 1

# The full deviation grid (vend's {0.55...1.5} x {honest, zero}).
WTP_FACTORS = (0.55, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5)
WALK_CLAIMS = (False, True)          # honest, zero (boba's claim_walk)

# The flagship P0 cell: cleanest cart activity (RESULTS.md's +$349.40/day
# cell), no demand-shock noise riding along with the liar signal.
BATTERY_CFG = BobaConfig(sigma_shock=0.0, flexible_share=0.35)


def run_pair(base_factory, dev_factory, days: int, seed: int,
            cfg: BobaConfig) -> dict:
    """Paired base-vs-deviation run for two AD HOC policy instances — the
    battery sweeps far more configurations than deserve a permanent ARMS
    registry entry, so this bypasses boba.run.run_experiment's name lookup
    but reuses its exact day-loop, CI, and metric set."""
    results = {}
    for label, factory in (("base", base_factory), ("dev", dev_factory)):
        policy = factory()
        per_day = [run_day(policy, seed, d, cfg) for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        results[label] = {"totals": totals, "per_day": per_day}
    paired = {metric: paired_ci(
                  [results["dev"]["per_day"][d][metric]
                   - results["base"]["per_day"][d][metric] for d in range(days)],
                  block=5)
              for metric in PAIRED_METRICS}
    return {"base_totals": results["base"]["totals"],
            "dev_totals": results["dev"]["totals"], "paired": paired}


def run_battery(days: int, seed: int, cfg: BobaConfig = BATTERY_CFG,
                market_floor: bool = False) -> dict:
    """The 14-cell deviation grid, ALL buyers lying the same way each cell
    (liar_share=1.0 — 'every buyer deviating', matching vend's methodology),
    paired against the all-honest cart. Buyer-utility Δ (consumer_surplus,
    the pooled, TRUE-preference-settled metric) answers 'is honesty the
    best response'; venue margin Δ is reported alongside for context.

    `market_floor` (issue #58): run the deviation arm with the observable
    competitor-price floor ON (the base honest cart is unaffected — the floor
    is a no-op for a buyer whose claim IS their disclosure)."""
    cells = {}
    for f in WTP_FACTORS:
        for cw in WALK_CLAIMS:
            name = f"factor{f:g}_walk{'zero' if cw else 'honest'}"
            res = run_pair(
                lambda: CartPolicy(),
                lambda f=f, cw=cw: CartPolicy(attest=False, liar_share=1.0,
                                              attack_wtp_factor=f,
                                              attack_claim_walk=cw,
                                              market_floor=market_floor),
                days, seed, cfg)
            cells[name] = {"wtp_factor": f, "claim_walk": cw,
                           "consumer_surplus": res["paired"]["consumer_surplus"],
                           "margin": res["paired"]["margin"],
                           "deals_dev": res["dev_totals"]["deals"],
                           "deals_base": res["base_totals"]["deals"]}
            cs = res["paired"]["consumer_surplus"]
            print(f"{name:<26} buyer CS Δ/day {cs['mean']:+8.2f} "
                  f"{cs['ci95']}  venue margin Δ/day {res['paired']['margin']['mean']:+8.2f}")
    return {"attack_version": ATTACK_VERSION, "kind": "battery",
            "days": days, "seed": seed, "market_floor": market_floor,
            "world": {"sigma_shock": cfg.sigma_shock,
                      "flexible_share": cfg.flexible_share},
            "notes": [
                "every buyer deviates the SAME way each cell (liar_share=1.0)",
                ("observable competitor-price floor ON: the claimed outside "
                 "option is capped at what the DISCLOSED valuation earns at "
                 "the public rival board (issue #58)") if market_floor else
                "no market floor (P0/P1a-as-committed: outside claim taken on "
                "faith)",
                "consumer_surplus is the pooled TRUE-preference-settled buyer "
                "utility (never the disclosed/lied one) — the honesty-as-"
                "best-response readout",
                "margin is the venue's Δ/day vs the all-honest cart — context, "
                "not the headline of this table",
                "paired seeds, block=5 CI (vend.run/boba.run convention)",
            ],
            "cells": cells}


def run_liar_share_sweep(days: int, seed: int, cfg: BobaConfig,
                         wtp_factor: float, claim_walk: bool,
                         shares=(0.25, 0.50, 1.00),
                         market_floor: bool = False) -> dict:
    """Fix ONE deviation (the canonical anchoring attack, or whatever the
    battery found as the best response) and sweep the SHARE of buyers (by
    stable uid) who run it — H3's question, transplanted: at what liar
    share does the venue's cart gain erode?

    `market_floor` (issue #58): the swept liar arm carries the observable
    competitor-price floor; the base honest cart is unchanged."""
    cells = {}
    for ls in shares:
        name = f"liars{int(ls * 100)}"
        res = run_pair(
            lambda: CartPolicy(),
            lambda ls=ls: CartPolicy(attest=False, liar_share=ls,
                                     attack_wtp_factor=wtp_factor,
                                     attack_claim_walk=claim_walk,
                                     market_floor=market_floor),
            days, seed, cfg)
        cells[name] = {"liar_share": ls,
                       "margin": res["paired"]["margin"],
                       "consumer_surplus": res["paired"]["consumer_surplus"],
                       "liar_deals_dev": res["dev_totals"].get("liar_deals", 0),
                       "deals_dev": res["dev_totals"]["deals"]}
        m = res["paired"]["margin"]
        print(f"{name:<10} venue margin Δ/day {m['mean']:+8.2f} {m['ci95']}")
    return {"attack_version": ATTACK_VERSION, "kind": "liar_share_sweep",
            "days": days, "seed": seed, "wtp_factor": wtp_factor,
            "claim_walk": claim_walk, "market_floor": market_floor,
            "world": {"sigma_shock": cfg.sigma_shock,
                      "flexible_share": cfg.flexible_share},
            "notes": [
                "liar identity is stable per person: keyed on consumer.uid "
                "via substream(seed,'liarid',uid), never on the policy",
                "paired seeds, block=5 CI",
                ("observable competitor-price floor ON (issue #58)"
                 if market_floor else "no market floor (P1a-as-committed)"),
            ],
            "cells": cells}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260713)
    ap.add_argument("--sigma-shock", type=float, default=BATTERY_CFG.sigma_shock)
    ap.add_argument("--flexible-share", type=float,
                    default=BATTERY_CFG.flexible_share)
    ap.add_argument("--battery", action="store_true",
                    help="run the 14-cell wtp_factor x claim_walk grid")
    ap.add_argument("--liar-sweep", action="store_true",
                    help="run the 25/50/100%% liar-share sweep")
    ap.add_argument("--wtp-factor", type=float, default=1.0,
                    help="deviation fixed for --liar-sweep")
    ap.add_argument("--claim-walk", action="store_true",
                    help="deviation fixed for --liar-sweep")
    ap.add_argument("--market-floor", action="store_true",
                    help="issue #58: cap the claimed outside option at the "
                         "observable competitor-price floor")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cfg = BobaConfig(sigma_shock=args.sigma_shock,
                     flexible_share=args.flexible_share)

    if not args.battery and not args.liar_sweep:
        print("specify --battery and/or --liar-sweep", file=sys.stderr)
        return 2

    out = {}
    if args.battery:
        out["battery"] = run_battery(args.days, args.seed, cfg,
                                     market_floor=args.market_floor)
    if args.liar_sweep:
        out["liar_share_sweep"] = run_liar_share_sweep(
            args.days, args.seed, cfg, args.wtp_factor, args.claim_walk,
            market_floor=args.market_floor)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(out, f, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

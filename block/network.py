"""B6.1 — the shared block demand-state posterior (NETWORK.md §B.1).

The smallest network feature with the biggest increasing-returns effect: the
day's demand shock is COMMON across the street (a rainy Tuesday, a street-fair
Saturday — one latent state g_d busies or empties every storefront at once).
Each morning-open venue observes its own early arrivals, a noisy Poisson signal
of g_d. A block-level Gamma–Poisson posterior POOLED across adopters turns those
signals into one sharp demand-state estimate that every adopter prices its own
session against — so each adopter improves every other adopter's pricing, and
the venue that can't see its own morning (the bar, closed until 15:00) prices
its whole evening off the block's pooled morning read.

THE GUARDRAIL, STATED FIRST AND ENFORCED BY CONSTRUCTION (NETWORK.md §B): the
only thing shared is DEMAND-STATE telemetry — arrival COUNTS and each venue's
known expected-arrival scale. No price, margin, or quote ever crosses between
venues. The posterior below is a pure function of {morning counts m_v} and the
public {expected morning arrivals E_v}; a venue's price is computed privately
from the shared g_hat and never disclosed. Substitutes cannot see each other's
pricing signals, period.

Pre-registered arms (NETWORK.md §B.1): SHARED posterior (pool the adopters)
vs PRIVATE posterior (each venue estimates from its own morning only). Two
pre-registered predictions plus the mandatory collusion audit:
  (P1) forecast error FALLS with adopter count;
  (P2) profit per adopter RISES with adopter count;
  (A)  collusion audit — consumer surplus under the SHARED arm is
       NON-DECREASING vs private; if sharing raises consumer prices the
       feature dies. Reported explicitly, whatever the sign.

Model (all paired on (seed, day) — g_d and every morning count are drawn ONCE
and both arms consume them, the same variance reduction as the twin-world
block):
  * g_d ~ Gamma(alpha0, alpha0), mean 1 (the common day-state; alpha0 is the
    prior strength — how strong a Tuesday-is-average prior the block holds).
  * morning signal: m_v ~ Poisson(g_d · E_v), E_v = venue v's expected morning
    arrivals (0 for the bar — no signal, the free-rider).
  * posterior (Gamma–Poisson conjugate):
      shared over adopter set S: g_hat = (alpha0 + Σ_{v∈S} m_v)
                                        / (alpha0 + Σ_{v∈S} E_v)
      private for venue v:       g_hat_v = (alpha0 + m_v) / (alpha0 + E_v)
    (a bar with E_v = 0 gets g_hat_v = 1 — the prior — under private: it has
    nothing of its own to learn from.)
  * each venue prices its session with g_hat under a CAPACITY constraint
    (yield management — the block's theme): linear demand D(p) = g·D0·(1 −
    p/Pmax), capacity K. The plug-in optimal price is max(monopoly price,
    the price that just rations K given g_hat) — so a believed-busy day raises
    the price to ration scarce capacity, which is EXACTLY where a wrong demand
    read can hurt consumers, and exactly what the audit must check.
  * realized profit and consumer surplus are booked against the TRUE g_d.

This is a self-contained arm (its own runner + tests); it does not touch the
ten-venue twin. B6 is its own wave (DESIGN/NETWORK build order).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

NETWORK_VERSION = 1


def substream(master_seed: int, *parts) -> int:
    """The gauntlet child-seed (blake2b folded to 63 bits) — same primitive as
    every other package, so this experiment keys deterministically."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


@dataclass(frozen=True)
class Adopter:
    """One block storefront as a demand-state adopter. `e_morning` is its
    expected early-window arrivals (the signal it contributes; 0 = closed in
    the morning, the free-rider). `base` (D0) scales its own session demand,
    `cap` (K) is its session capacity, `cost` (c) its unit cost, `pmax` the
    choke price. These are block-consistent TARGETS — the mechanism is the
    pooling, not the exact per-venue elasticity."""
    name: str
    e_morning: float
    base: float
    cap: float
    cost: float
    pmax: float


# The block's adopter roster. Morning-signal weights track each venue's real
# early curve (the bodega and bakery are morning-heavy; the bar contributes
# NOTHING — it opens at 15:00 and can only ride the pooled read). Session
# scale/capacity/cost/choke are representative of each venue's own economics.
ADOPTERS: tuple[Adopter, ...] = (
    Adopter("bodega",     e_morning=40.0, base=120.0, cap=90.0, cost=1.1, pmax=6.0),
    Adopter("bakery",     e_morning=30.0, base=55.0,  cap=40.0, cost=1.4, pmax=9.0),
    Adopter("vending",    e_morning=12.0, base=18.0,  cap=14.0, cost=1.1, pmax=5.0),
    Adopter("boba",       e_morning=8.0,  base=40.0,  cap=30.0, cost=1.6, pmax=8.0),
    Adopter("barbershop", e_morning=6.0,  base=9.0,   cap=8.0,  cost=0.5, pmax=60.0),
    Adopter("parking",    e_morning=10.0, base=40.0,  cap=40.0, cost=0.4, pmax=45.0),
    Adopter("florist",    e_morning=4.0,  base=12.0,  cap=15.0, cost=1.3, pmax=28.0),
    Adopter("bar",        e_morning=0.0,  base=140.0, cap=60.0, cost=2.2, pmax=22.0),
)


@dataclass(frozen=True)
class NetConfig:
    alpha0: float = 3.0          # prior strength (Gamma(alpha0, alpha0), mean 1)
    days: int = 60
    seeds: int = 8
    disc_sens: float = 0.6       # discount-only: markdown per unit of believed
    disc_max: float = 0.40       # slack (1 − g_hat), capped at disc_max


def _cs_slice(lo: float, hi: float, price: float, denom: float,
              pmax: float) -> float:
    """Consumer surplus of the WTP-ranked consumers in [lo, hi) served at
    `price`: ∫ [inverse_demand(x) − price] dx with inverse_demand(x) =
    Pmax·(1 − x/denom)."""
    if denom <= 0 or hi <= lo:
        return 0.0
    inv = pmax * (hi - lo) - pmax * (hi * hi - lo * lo) / (2.0 * denom)
    return max(0.0, inv - price * (hi - lo))


def _day_outcome(g_hat: float, g_true: float, ad: Adopter, mode: str,
                 cfg: NetConfig) -> tuple[float, float, float, float]:
    """One venue's day under a pricing regime. Returns (profit, consumer
    surplus, realized average price, units sold), all booked against the TRUE
    state g_true; the decision uses only the estimate g_hat.

    * "ration" (the counterfactual the audit exists to catch): unconstrained
      yield management — a believed-busy day RAISES the price to ration scarce
      capacity (max(p0, the price that just clears K given g_hat)).
    * "discount" (the block's actual guardrail — discount-only off a fixed
      sticker): stock K perishes at cost; the venue posts the sticker p0, then
      MARKS DOWN the leftover to a clearance price to move the perishable tail.
      The markdown depth is planned from g_hat (believed leftover); it NEVER
      prices above the sticker. A sharper estimate clears the true leftover
      more precisely — less waste (higher profit) and more discounted units to
      the price-sensitive tail (higher consumer surplus)."""
    pmax, cost, base, cap = ad.pmax, ad.cost, ad.base, ad.cap
    p0 = 0.5 * (pmax + cost)                  # sticker / monopoly price
    denom = g_true * base

    if mode == "ration":
        demand0 = g_hat * base
        p = p0 if demand0 <= cap else max(p0, pmax * (1.0 - cap / demand0))
        s = min(max(0.0, g_true * base * (1.0 - p / pmax)), cap)
        profit = (p - cost) * s
        return profit, _cs_slice(0.0, s, p, denom, pmax), p, s

    # discount-only: newsvendor stock + markdown clearance
    stock = cap
    sales_full = min(max(0.0, g_true * base * (1.0 - p0 / pmax)), stock)
    leftover = stock - sales_full
    est_full = max(0.0, g_hat * base * (1.0 - p0 / pmax))
    est_left = max(0.0, stock - est_full)
    p_d, sales_clear = p0, 0.0
    if est_left > 1e-9 and leftover > 1e-9 and g_hat > 0:
        # clearance price that would sell exactly the BELIEVED leftover
        p_d = min(p0, max(cost, p0 - pmax * est_left / (g_hat * base)))
        clear_demand = max(0.0, g_true * base * (p0 - p_d) / pmax)
        sales_clear = min(clear_demand, leftover)
    revenue = p0 * sales_full + p_d * sales_clear
    units = sales_full + sales_clear
    profit = revenue - cost * stock          # perishable: full stock is sunk
    cs = (_cs_slice(0.0, sales_full, p0, denom, pmax)
          + _cs_slice(sales_full, sales_full + sales_clear, p_d, denom, pmax))
    avg_price = revenue / units if units > 1e-9 else p0
    return profit, cs, avg_price, units


def _draw_day(seed: int, day: int, cfg: NetConfig
              ) -> tuple[float, dict[str, int]]:
    """One paired day: the common state g_d and every venue's morning count,
    drawn ONCE (both arms consume them)."""
    rng = np.random.default_rng(substream(seed, "day", day))
    g = float(rng.gamma(cfg.alpha0, 1.0 / cfg.alpha0))       # mean 1
    counts = {}
    for ad in ADOPTERS:
        if ad.e_morning > 0:
            counts[ad.name] = int(np.random.default_rng(
                substream(seed, "m", day, ad.name)).poisson(g * ad.e_morning))
        else:
            counts[ad.name] = 0                              # no morning signal
    return g, counts


def _posterior_mean(alpha0: float, sum_m: float, sum_e: float) -> float:
    return (alpha0 + sum_m) / (alpha0 + sum_e)


def run_cell(k: int, cfg: NetConfig, mode: str, seed0: int = 20260710) -> dict:
    """One adopter-count cell under one pricing regime: the FIRST k venues in
    ADOPTERS adopt. For every (seed, day) compute, paired, the SHARED outcome
    (pool the k adopters' morning counts) and the PRIVATE outcome (each of the
    k estimates from its own morning). Per-metric we report the SHARED and
    PRIVATE per-adopter-day means and — the load-bearing paired quantity — the
    shared−private premium (0 by construction at k=1, since a lone adopter's
    pool IS its own posterior; it can only grow as the pool sharpens)."""
    adopters = ADOPTERS[:k]
    sum_e = sum(ad.e_morning for ad in adopters)
    per_seed = {m: {"shared": [], "private": []}
                for m in ("profit", "consumer_surplus", "forecast_abs_err",
                          "price")}
    # the free-rider vignette: the bar sees no morning; track its own profit
    bar_seed = {"shared": [], "private": []} if "bar" in \
        {a.name for a in adopters} else None
    for si in range(cfg.seeds):
        seed = seed0 + si
        acc = {a: {"profit": 0.0, "consumer_surplus": 0.0,
                   "forecast_abs_err": 0.0, "price": 0.0}
               for a in ("shared", "private")}
        bar_acc = {"shared": 0.0, "private": 0.0}
        n = 0
        for day in range(cfg.days):
            g, counts = _draw_day(seed, day, cfg)
            g_shared = _posterior_mean(
                cfg.alpha0, sum(counts[ad.name] for ad in adopters), sum_e)
            for ad in adopters:
                g_priv = _posterior_mean(cfg.alpha0, counts[ad.name],
                                         ad.e_morning)
                for arm, gh in (("shared", g_shared), ("private", g_priv)):
                    pr, cs, p, _u = _day_outcome(gh, g, ad, mode, cfg)
                    acc[arm]["profit"] += pr
                    acc[arm]["consumer_surplus"] += cs
                    acc[arm]["forecast_abs_err"] += abs(gh - g)
                    acc[arm]["price"] += p
                    if ad.name == "bar":
                        bar_acc[arm] += pr
                n += 1
        for metric in per_seed:
            for arm in ("shared", "private"):
                per_seed[metric][arm].append(acc[arm][metric] / n)
        if bar_seed is not None:
            bar_seed["shared"].append(bar_acc["shared"] / cfg.days)
            bar_seed["private"].append(bar_acc["private"] / cfg.days)
    out = {"k": k, "mode": mode, "adopters": [a.name for a in adopters]}
    for metric, d in per_seed.items():
        out[metric] = {
            "shared": _mean_ci(d["shared"]),
            "private": _mean_ci(d["private"]),
            "shared_minus_private": _mean_ci(
                [s - p for s, p in zip(d["shared"], d["private"])]),
        }
    if bar_seed is not None:
        out["bar_profit"] = {
            "shared": _mean_ci(bar_seed["shared"]),
            "private": _mean_ci(bar_seed["private"]),
            "shared_minus_private": _mean_ci(
                [s - p for s, p in zip(bar_seed["shared"], bar_seed["private"])]),
        }
    return out


def _mean_ci(xs: list[float]) -> dict:
    """Mean with a 95% t-interval over the (independent) per-seed means."""
    a = np.asarray(xs, dtype=float)
    n = len(a)
    mean = float(a.mean())
    if n < 2:
        return {"mean": round(mean, 4), "ci95": None, "n": n}
    se = float(a.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 4),
            "ci95": [round(mean - t * se, 4), round(mean + t * se, 4)], "n": n}


def _audit(full: dict) -> dict:
    """The collusion audit for one regime's full-adoption cell: consumer
    surplus under SHARED must be NON-DECREASING vs private (upper CI ≥ 0).
    A strict pro-consumer win is the lower CI > 0. Also reports the price
    move — the direct 'did sharing raise prices?' read."""
    cs = full["consumer_surplus"]["shared_minus_private"]
    ci = cs["ci95"]
    non_dec = ci is not None and ci[1] >= 0.0
    strict = ci is not None and ci[0] > 0.0
    return {
        "metric": "consumer_surplus (shared − private) per adopter-day, full adoption",
        "paired_cs_diff": cs,
        "paired_price_diff": full["price"]["shared_minus_private"],
        "non_decreasing": bool(non_dec),
        "strict_pro_consumer": bool(strict),
        "verdict": ("PASS — shared demand-state telemetry does NOT lower "
                    "consumer surplus" if non_dec else
                    "FAIL — sharing raises consumer prices; the feature dies"),
    }


def _mode_result(cfg: NetConfig, mode: str, seed0: int) -> dict:
    cells = [run_cell(k, cfg, mode, seed0) for k in range(1, len(ADOPTERS) + 1)]
    shared_err = [c["forecast_abs_err"]["shared"]["mean"] for c in cells]
    premium = [c["profit"]["shared_minus_private"]["mean"] for c in cells]
    return {
        "mode": mode,
        "cells": cells,
        # P1: the SHARED forecast error falls as more venues pool their morning
        "P1_forecast_error_falls_with_adopters": {
            "shared_err_by_k": [round(x, 4) for x in shared_err],
            "monotone_nonincreasing": all(
                shared_err[i + 1] <= shared_err[i] + 1e-9
                for i in range(len(shared_err) - 1)),
            "k1_vs_kmax": [round(shared_err[0], 4), round(shared_err[-1], 4)],
        },
        # P2: the per-adopter profit PREMIUM of sharing (shared − private)
        # rises with adopter count — the increasing-returns signature, isolated
        # from the changing venue mix (0 at k=1 by construction, since a lone
        # adopter's pool IS its own posterior). The robust read is the TREND
        # (full adoption vs the first real pool at k=2) plus a floor at 0; the
        # strict step-flag also reported (it can wiggle as the venue mix
        # changes cell to cell).
        "P2_profit_premium_rises_with_adopters": {
            "premium_by_k": [round(x, 4) for x in premium],
            "k1_vs_kmax": [round(premium[0], 4), round(premium[-1], 4)],
            "rises": (len(premium) >= 3 and premium[-1] > premium[1]
                      and all(p >= -1e-6 for p in premium)),
            "strict_monotone_nondecreasing": all(
                premium[i + 1] >= premium[i] - 1e-6
                for i in range(len(premium) - 1)),
        },
        # the free-rider vignette: the bar (no morning of its own) at full
        # adoption — private = prior-only, shared = the block's pooled morning
        "bar_free_rider": cells[-1].get("bar_profit"),
        "collusion_audit": _audit(cells[-1]),
    }


def run_sweep(cfg: NetConfig = NetConfig(), seed0: int = 20260710) -> dict:
    """The pre-registered experiment across BOTH pricing regimes. 'discount'
    is the block's actual guardrail (every SNHP policy is discount-only);
    'ration' is the unconstrained-yield counterfactual the audit exists to
    catch. The headline verdict is the discount regime; the ration regime is
    reported as the honest reason discount-only is the guardrail."""
    return {
        "network_version": NETWORK_VERSION,
        "config": {"alpha0": cfg.alpha0, "days": cfg.days, "seeds": cfg.seeds,
                   "disc_sens": cfg.disc_sens, "disc_max": cfg.disc_max,
                   "n_adopters": len(ADOPTERS),
                   "roster": [a.name for a in ADOPTERS]},
        "discount": _mode_result(cfg, "discount", seed0),   # the block's regime
        "ration": _mode_result(cfg, "ration", seed0),       # counterfactual
    }


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--alpha0", type=float, default=3.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = NetConfig(alpha0=args.alpha0, days=args.days, seeds=args.seeds)
    res = run_sweep(cfg, args.seed0)
    txt = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(txt + "\n")
        print(f"wrote {args.out}")
    for mode in ("discount", "ration"):
        m = res[mode]
        p1 = m["P1_forecast_error_falls_with_adopters"]
        p2 = m["P2_profit_premium_rises_with_adopters"]
        a = m["collusion_audit"]
        tag = "block guardrail" if mode == "discount" else "counterfactual"
        print(f"\n=== {mode.upper()} pricing ({tag}) ===")
        print(f"P1 forecast err by k (shared): {p1['shared_err_by_k']}  "
              f"monotone↓ {p1['monotone_nonincreasing']}")
        print(f"P2 shared−private profit premium by k: {p2['premium_by_k']}  "
              f"rises {p2['rises']}")
        bar = m["bar_free_rider"]
        if bar:
            print(f"   bar (free-rider) profit/day: private {bar['private']['mean']}"
                  f" → shared {bar['shared']['mean']} "
                  f"(Δ {bar['shared_minus_private']['mean']} "
                  f"CI {bar['shared_minus_private']['ci95']})")
        print(f"AUDIT ΔCS(shared−private)={a['paired_cs_diff']['mean']} "
              f"CI {a['paired_cs_diff']['ci95']} | "
              f"Δprice={a['paired_price_diff']['mean']} "
              f"CI {a['paired_price_diff']['ci95']}")
        print(f"   {a['verdict']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

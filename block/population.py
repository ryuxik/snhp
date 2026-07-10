"""The block's shared population — the SAME seeded walkers enter both worlds.

Layering rule (B0 hard requirement): this module knows GEOGRAPHY (two venues
exist; each shopper was heading to one of them) and TASTES (WTP draws over
the union of the block's goods). It knows NOTHING about prices, policies,
or ledgers. Every draw depends only on (master_seed, day, tick, persona, k)
— never on anything a world did — so the population stream is identical
across the sticker and SNHP worlds BY CONSTRUCTION; block/tests asserts it.

The shopper funnel, calibrated (DESIGN §3 honesty gate):
  * BLOCK_DAILY_FOOT_TRAFFIC (4200) walkers pass the storefronts; most never
    shop. SHOPPER_FRACTION is DERIVED, not tuned:
    (VENDING_DAILY_ARRIVALS + BODEGA_DAILY_TX) / BLOCK_DAILY_FOOT_TRAFFIC
    ≈ 0.148 — i.e. ~15% of passers-by transact somewhere on the block,
    which is what the two venue targets jointly imply.
  * Each shopper gets a HOME venue (where they were headed):
    P(vending) = 70/620, so the machine sees ~VENDING_DAILY_ARRIVALS
    arrivals/day and the bodega ~BODEGA_DAILY_TX. The OTHER venue is
    reachable for the persona's cross-venue walk cost — the machine's
    outside option is the actual bodega, endogenously, and vice versa.
  * Conversion is endogenous (WTP vs posted prices), so realized
    transactions land somewhat under the arrival targets; RESULTS-B0.md
    reports realized numbers.

WTP model: ONE draw per GOOD over the union of vending SKUs and bodega
items — cola-20oz from the machine and cola-20oz from the bodega fridge are
the same good, one WTP — lognormal around GOOD_MU × persona wtp_mult with
vend's canonical WTP_SIGMA. For bodega-only items calibration publishes a
posted price, not a WTP mean; we back out GOOD_MU = price × BODEGA_MU_MARKUP
(1.08), consistent with the vending calibration where wtp_mu sits 5–13%
above the profit-optimal sticker (cola-20oz μ 3.40 vs the bodega's posted
3.25 → 1.05; chips 2.75 vs 2.50 → 1.10).

B0 simplifications (documented, deferred): no day-of-week pattern (the
tourist "weekend-heavy" lean waits for the block calendar), no day-level
demand shocks, no within-day return queue.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

from block import calibration
from vend.world import TICKS_PER_DAY, WTP_SIGMA, hour_of


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (the gauntlet pattern — copied verbatim from
    vend.core.substream so the population layer carries no vend-policy
    imports): blake2b of the master seed and any hashable parts, folded to
    63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


# ── the goods: union of the block's catalogs, one WTP per good ───────────
VENDING_GOODS = tuple(sku for sku, *_ in calibration.VENDING_CATALOG)
BODEGA_GOODS = tuple(item for item, *_ in calibration.BODEGA_CATALOG)
GOODS = VENDING_GOODS + tuple(g for g in BODEGA_GOODS if g not in VENDING_GOODS)

BODEGA_MU_MARKUP = 1.08   # posted price → mean WTP for bodega-only goods

GOOD_MU: dict[str, float] = {sku: mu for sku, mu, *_ in calibration.VENDING_CATALOG}
for _item, _price, _cost in calibration.BODEGA_CATALOG:
    GOOD_MU.setdefault(_item, round(_price * BODEGA_MU_MARKUP, 4))

# ── personas & schedules ─────────────────────────────────────────────────
# (share, wtp_mult, walk_cost) by name; schedule strings from calibration
# are rendered as hourly weight curves below (hours 7–22, the block clock).
_PERSONA = {name: (share, wtp_mult, walk_cost)
            for name, share, wtp_mult, walk_cost, _sched in calibration.PERSONAS}

PERSONA_HOURLY: dict[str, dict[int, float]] = {
    # "weekday 8-18 peaks": commute in, lunch spike, commute out
    "office-worker": {7: 2, 8: 8, 9: 5, 10: 3, 11: 7, 12: 10, 13: 8, 14: 3,
                      15: 2, 16: 3, 17: 7, 18: 5, 19: 1},
    # "after-school 15-19"
    "student": {14: 1, 15: 8, 16: 9, 17: 8, 18: 6, 19: 4, 20: 1},
    # "all-day, evening lean"
    "local": {7: 2, 8: 3, 9: 3, 10: 3, 11: 3, 12: 4, 13: 3, 14: 3, 15: 3,
              16: 3, 17: 4, 18: 5, 19: 6, 20: 6, 21: 5, 22: 3},
    # "midday-heavy" (weekend lean deferred with the block calendar)
    "tourist": {9: 1, 10: 3, 11: 6, 12: 8, 13: 8, 14: 7, 15: 6, 16: 5,
                17: 3, 18: 2, 19: 1},
}

# ── the funnel: derived from calibration, not tuned ──────────────────────
_TARGET_SHOPPERS = (calibration.VENDING_DAILY_ARRIVALS
                    + calibration.BODEGA_DAILY_TX)                    # 620
SHOPPER_FRACTION = _TARGET_SHOPPERS / calibration.BLOCK_DAILY_FOOT_TRAFFIC
DAILY_SHOPPERS = calibration.BLOCK_DAILY_FOOT_TRAFFIC * SHOPPER_FRACTION
P_VENDING_HOME = calibration.VENDING_DAILY_ARRIVALS / _TARGET_SHOPPERS

CROSS_WALK_JITTER = (0.8, 1.2)   # per-shopper hassle spread around persona $


def _tick_rates(name: str) -> list[float]:
    """Expected arrivals per tick for one persona (6 ticks per hour)."""
    share = _PERSONA[name][0]
    hours = PERSONA_HOURLY[name]
    tot = float(sum(hours.values()))
    return [DAILY_SHOPPERS * share * hours.get(hour_of(t), 0.0) / tot / 6.0
            for t in range(TICKS_PER_DAY)]


_RATES = {name: _tick_rates(name) for name in _PERSONA}


@dataclass
class Shopper:
    """One walker who will actually shop today. Immutable in spirit: the
    runner never writes to it, so the same object can serve both worlds."""
    uid: int                 # stable identity (blake2b substream)
    persona: str
    home: str                # "vending" | "bodega" — where they were headed
    wtp: dict[str, float]    # $ value of the FIRST unit, per good (union)
    cross_walk: float        # $ hassle of using the NON-home venue instead


def sample_shopper(master_seed: int, day: int, tick: int, persona: str,
                   k: int) -> Shopper:
    """Pure function of (master_seed, day, tick, persona, k). Draw order is
    fixed and documented: WTPs over GOODS in canonical order, then the home
    venue, then the cross-walk jitter — changing it is a breaking change to
    every committed artifact."""
    share, wtp_mult, walk_cost = _PERSONA[persona]
    rng = np.random.default_rng(substream(master_seed, "shopper", day, tick,
                                          persona, k))
    wtp = {g: float(rng.lognormal(math.log(GOOD_MU[g] * wtp_mult), WTP_SIGMA))
           for g in GOODS}
    home = "vending" if rng.random() < P_VENDING_HOME else "bodega"
    cross = float(walk_cost * rng.uniform(*CROSS_WALK_JITTER))
    return Shopper(uid=substream(master_seed, "uid", day, tick, persona, k),
                   persona=persona, home=home, wtp=wtp, cross_walk=cross)


def arrivals_at(master_seed: int, day: int, tick: int) -> list[Shopper]:
    """Poisson arrivals this tick, per persona — world-independent by
    construction (there is no world/policy parameter to pass)."""
    out: list[Shopper] = []
    for name in _PERSONA:
        lam = _RATES[name][tick]
        if lam <= 0.0:
            continue
        n = int(np.random.default_rng(
            substream(master_seed, "arr", day, tick, name)).poisson(lam))
        out.extend(sample_shopper(master_seed, day, tick, name, k)
                   for k in range(n))
    return out


def day_stream(master_seed: int, day: int) -> dict[int, list[Shopper]]:
    """tick → shoppers, for one day. Both worlds consume this stream; the
    pairing test regenerates it and asserts byte-level equality."""
    return {t: arrivals_at(master_seed, day, t) for t in range(TICKS_PER_DAY)}


def expected_home_rate(venue: str, tick: int) -> float:
    """Analytic expected arrivals/tick whose HOME is `venue` — what a venue
    may honestly know about its own crowd curve (feeds the vend learner)."""
    tot = sum(_RATES[name][tick] for name in _PERSONA)
    return tot * (P_VENDING_HOME if venue == "vending" else 1.0 - P_VENDING_HOME)


def expected_daily() -> dict[str, float]:
    """Analytic daily totals — equal to the calibration targets by
    construction (the funnel is derived, not tuned)."""
    total = sum(sum(r) for r in _RATES.values())
    return {"shoppers": total,
            "vending_home": total * P_VENDING_HOME,
            "bodega_home": total * (1.0 - P_VENDING_HOME)}

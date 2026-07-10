"""The season world: one buy at week 0, 16 weekly ticks, no restock, salvage.

Modeling choices (the ones reviewers should attack):
  * WEEKLY ticks ×16, not daily. Markdown decisions, waiter returns, and
    sell-through observation are all weekly in the real trade; days would
    add runtime, not information, in P0.
  * ONE-STYLE SHOPPERS: each arrival shops exactly one style (drawn from
    fixed attention weights) in exactly one size. This keeps per-cell
    demand an independently thinned Poisson stream, so the operator's
    demand model is CORRECTLY SPECIFIED up to the noisy appeal level —
    policy differences are pricing, not model misspecification. The cost:
    no cross-style substitution in P0 (flagged in results notes).
  * THE BUY IS PLANNED AGAINST THE CLIFF CALENDAR — expected units sold at
    the industry-standard price path under the operator's (possibly noisy)
    appeal estimate, split by the size curve, times a mean-one lognormal
    buy error per style×size. Both arms inherit the SAME buy: the game is
    "work the inventory you're stuck with", never "buy better".
  * INFORMATION HONESTY (same as vend): consumers draw from the TRUE
    demand process (appeal × season decay); only the operator's estimate
    (appeal_est, sigma_cal) is noisy — and it set both the buy and the
    markdown arm's solve. The cliff arm needs no estimate at all.
  * STRATEGIC WAITERS use a documented one-step lookahead (see
    `waiter_buys_now`): buy now iff surplus_now >= beta * P(size survives
    a week | observed sell-through) * (next week's decayed WTP − expected
    next price), with a STATIONARY price-drift belief calibrated to the
    cliff's average weekly decline (0.3^(1/15) ≈ 0.92). They do NOT know
    either arm's exact calendar — decades of clearance seasons trained a
    drift expectation, not a lookup table. With no stockout risk this
    reduces to "buy when price < ~0.79 × current WTP" — exactly the
    "reservation × patience discount" rule, with size risk relaxing it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from fashion.core import poisson_cdf, substream

WEEKS = 16                   # weekly ticks; week 0..15 (1-indexed 1..16 in docs)
SIZES = ("S", "M", "L", "XL")
SIZE_SHARE = {"S": 0.15, "M": 0.35, "L": 0.35, "XL": 0.15}   # M,L popular

WTP_SIGMA = 0.35             # lognormal spread of per-consumer WTP
DECAY = 0.96                 # weekly season-staleness factor on WTP scale
ARRIVALS_W0 = 60.0           # expected arrivals in week 0 ...
ARRIVAL_TAPER = 0.93         # ... tapering weekly (early-season high)

COST_FRAC = 0.35             # unit_cost = 35% of MSRP
SALVAGE_FRAC = 0.20          # outlet salvage = 20% of unit cost

WAITER_BETA = 0.90           # patience discount on next week's surplus
WAITER_PRICE_DRIFT = 0.92    # believed weekly price ratio (cliff's average:
                             # MSRP→30% over 15 steps = 0.3^(1/15) ≈ 0.923)

# (style, msrp, true week-0 appeal = lognormal WTP scale, attention share)
# appeal ≈ 0.9 × MSRP: the sticker is aspirational — roughly a third of the
# week-0 crowd clears it, the industry's actual full-price reality.
STYLE_SPEC = [
    ("coat",  220.0, 200.0, 0.30),
    ("dress", 140.0, 126.0, 0.28),
    ("knit",   90.0,  82.0, 0.24),
    ("tee",    38.0,  34.0, 0.18),
]


@dataclass(frozen=True)
class FashionConfig:
    """The experiment knobs. All mean/median-one so arms are compared on
    adaptation, not scale."""
    sigma_buy: float = 0.15      # lognormal buy-depth error per style×size (mean-one)
    sigma_cal: float = 0.0       # operator's appeal-estimate noise (median-one)
    waiter_share: float = 0.15   # P(an arrival is a strategic waiter)


DEFAULT_CONFIG = FashionConfig()


@dataclass(frozen=True)
class Style:
    style: str
    msrp: float          # the ceiling, always (discount-only clamp)
    unit_cost: float     # sunk at the buy
    salvage: float       # per-unit outlet recovery at season end
    appeal: float        # TRUE week-0 WTP lognormal scale
    appeal_est: float    # the OPERATOR'S estimate (set the buy + markdown solve)
    attention: float     # P(an arrival shops this style)


def cliff_mult(week: int) -> float:
    """The industry calendar (1-indexed weeks in the trade): MSRP weeks 1–8,
    −30% weeks 9–11, −50% weeks 12–14, −70% weeks 15–16."""
    if week < 8:
        return 1.0
    if week < 11:
        return 0.70
    if week < 14:
        return 0.50
    return 0.30


def decay(week: int | np.ndarray) -> float | np.ndarray:
    """Season staleness: the WTP scale of week-w arrivals (and of waiters
    still holding out at week w — fashion goes stale for them too)."""
    return DECAY ** week


def arrival_rate(week: int | np.ndarray) -> float | np.ndarray:
    return ARRIVALS_W0 * ARRIVAL_TAPER ** week


_SQRT2 = math.sqrt(2.0)


def wtp_sf(price: float, scale: float) -> float:
    """P(WTP > price) under lognormal(log scale, WTP_SIGMA) — scalar."""
    if scale <= 0:
        return 0.0
    z = math.log(price / scale) / WTP_SIGMA
    return 0.5 * math.erfc(z / _SQRT2)


def build_catalog(cfg: FashionConfig = DEFAULT_CONFIG,
                  master_seed: int = 0) -> dict[str, Style]:
    """With sigma_cal > 0 the operator's appeal estimate is
    μ̂ = μ·lognormal(0, σ_cal) (median-one, per style) — a competent buyer
    with finite history, not an omniscient one. Consumers never see it."""
    cat = {}
    for style, msrp, appeal, attention in STYLE_SPEC:
        if cfg.sigma_cal > 0:
            rng = np.random.default_rng(substream(master_seed, "cal", style))
            est = float(appeal * rng.lognormal(0.0, cfg.sigma_cal))
        else:
            est = appeal
        cost = round(COST_FRAC * msrp, 2)
        cat[style] = Style(style=style, msrp=msrp, unit_cost=cost,
                           salvage=round(SALVAGE_FRAC * cost, 2),
                           appeal=appeal, appeal_est=est, attention=attention)
    return cat


def planned_style_units(listing: Style) -> float:
    """The merchandise plan: expected season units at the CLIFF price path
    under the operator's appeal estimate, counting every arrival as a
    loyal-now buyer. Real open-to-buy plans are built exactly this naively —
    to the calendar, ignoring strategic waiting. Both arms inherit it."""
    return sum(arrival_rate(w) * listing.attention
               * wtp_sf(listing.msrp * cliff_mult(w),
                        listing.appeal_est * decay(w))
               for w in range(WEEKS))


def planned_depth(catalog: dict[str, Style], cfg: FashionConfig,
                  master_seed: int) -> dict[tuple[str, str], int]:
    """ONE buy at week 0, no restock ever: depth per style×size = planned
    style units × size curve × mean-one lognormal buy error (σ_buy), drawn
    per CELL — size-level errors are what create broken-size endgames."""
    depth = {}
    for style, listing in catalog.items():
        planned = planned_style_units(listing)
        for size in SIZES:
            if cfg.sigma_buy > 0:
                rng = np.random.default_rng(
                    substream(master_seed, "buy", style, size))
                err = float(rng.lognormal(-cfg.sigma_buy ** 2 / 2,
                                          cfg.sigma_buy))
            else:
                err = 1.0
            depth[(style, size)] = max(
                0, int(round(planned * SIZE_SHARE[size] * err)))
    return depth


@dataclass(frozen=True)
class Shopper:
    """One consumer: one style, one size (they can ONLY buy their size),
    one type. WTP decays with the season week — staleness bites everyone."""
    uid: int
    style: str
    size: str
    base_wtp: float      # week-0-equivalent draw around the TRUE style appeal
    waiter: bool         # strategic waiter vs loyal-now

    def wtp(self, week: int) -> float:
        return self.base_wtp * decay(week)


def sample_shopper(master_seed: int, week: int, k: int,
                   catalog: dict[str, Style],
                   cfg: FashionConfig = DEFAULT_CONFIG) -> Shopper:
    """Paired across arms: depends only on (master, week, k, cfg) — never on
    anything a policy did. Draw order is fixed (style, size, wtp, type), so
    raising waiter_share flips loyals into waiters WITHOUT reshuffling who
    they are — waiter sets are nested across configs."""
    rng = np.random.default_rng(substream(master_seed, "cons", week, k))
    u = rng.random()
    acc = 0.0
    style = STYLE_SPEC[-1][0]
    for st, listing in catalog.items():
        acc += listing.attention
        if u < acc:
            style = st
            break
    u = rng.random()
    acc = 0.0
    size = SIZES[-1]
    for sz in SIZES:
        acc += SIZE_SHARE[sz]
        if u < acc:
            size = sz
            break
    base = float(rng.lognormal(math.log(catalog[style].appeal), WTP_SIGMA))
    waiter = bool(rng.random() < cfg.waiter_share)
    return Shopper(uid=substream(master_seed, "uid", week, k),
                   style=style, size=size, base_wtp=base, waiter=waiter)


def arrivals_at(master_seed: int, week: int) -> int:
    """Poisson weekly arrivals — paired across arms by construction."""
    rng = np.random.default_rng(substream(master_seed, "arr", week))
    return int(rng.poisson(arrival_rate(week)))


def waiter_buys_now(surplus_now: float, wtp_next: float, price: float,
                    stock: int, sold_last_week: int, last_week: bool) -> bool:
    """The strategic waiter's ONE-STEP lookahead, documented honestly:

      buy now  iff  surplus_now > 0  AND
                    surplus_now >= β · P_survive · max(0, wtp_next − ĝ·p)

    * P_survive = P(Poisson(u) ≤ s−1): their size outlasts one more week if
      next week's demand (naive persistence forecast: u = units of their
      style×size sold LAST week, which stores display and shoppers see)
      doesn't eat the s units on the rack. Week 0 has no history → u = 0 →
      P_survive = 1.
    * ĝ = WAITER_PRICE_DRIFT: a stationary belief that prices drift down
      ~8%/week (the cliff's season-average trajectory — the belief decades
      of clearance calendars trained). NOT the exact calendar of either arm.
    * β = WAITER_BETA: waiting is a hassle.
    * wtp_next: their own valuation next week — already staled by DECAY.

    With P_survive = 1 this reduces to buy iff p ≲ 0.79 × wtp_now (the
    "reservation × patience discount" rule); observed sell-through against
    thin stock collapses the wait value and converts them early — size risk
    is the season's only honest commitment device. Last week: waiting is
    worthless, so they buy on any positive surplus, like a loyal."""
    if surplus_now <= 0:
        return False
    if last_week:
        return True
    p_survive = poisson_cdf(stock - 1, float(sold_last_week))
    wait_value = WAITER_BETA * p_survive * max(
        0.0, wtp_next - WAITER_PRICE_DRIFT * price)
    return surplus_now >= wait_value

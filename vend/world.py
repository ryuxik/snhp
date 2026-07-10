"""The simulated world: clock, arrivals, consumers, machine dynamics.

Honesty notes (these are the modeling choices reviewers should attack):
  * The static baseline is STRONG: list prices are calibrated to the
    PROFIT-optimal single price for the whole arrival mixture — a competent
    operator, not a strawman. Dynamic arms may only ever discount from it.
  * Demand is genuinely time-varying (hourly WTP multiplier + hourly arrival
    rates). Under a discount-only clamp this is the whole reason dynamic
    pricing can win; if it were stationary, static-at-optimum would tie.
  * The machine's demand model is the true one (operator knows their market).
    Favorable to dynamic arms; flagged in results.json config.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from vend.core import Listing, Lot, MachineState, substream

TICKS_PER_DAY = 96          # 10-minute ticks: 07:00–23:00


@dataclass(frozen=True)
class WorldConfig:
    """P1.5 realism knobs. Everything defaults OFF so the P0/P1 committed
    artifacts stay exactly reproducible; the experiment grid turns them on."""
    sigma_cal: float = 0.0     # operator's WTP-estimate noise (sets the sticker)
    sigma_rate: float = 0.0    # day-level arrival-rate shock (lognormal)
    sigma_wtp: float = 0.0     # day-level WTP shock (lognormal)
    dow: bool = False          # office-tower day-of-week pattern, one sticker all week
    glut_prob: float = 0.0     # P(perishable delivery doubles) per SKU-day
    anchor_peak: bool = False  # sticker optimized for the PEAK crowd (the
                               # "surge value without surging" design: the
                               # ceiling sits high, negotiation discounts
                               # everywhere the crowd is softer)


DEFAULT_CONFIG = WorldConfig()

# Office tower: Mon..Sun. One sticker all week — as real machines have.
DOW_RATE = [1.0, 1.0, 1.0, 1.0, 0.85, 0.15, 0.10]


@dataclass(frozen=True)
class DayState:
    rate_mult: float   # today's demand shock (mean 1 across days)
    wtp_mult: float    # today's willingness-to-pay shock (mean 1)
    dow_mult: float    # public calendar knowledge — policies may use it


import functools


@functools.lru_cache(maxsize=4096)
def day_state(cfg: WorldConfig, master_seed: int, day: int) -> DayState:
    rng = np.random.default_rng(substream(master_seed, "shock", day))
    # mean-one lognormals: E[e^X]=1 with mu = -sigma^2/2 — average demand is
    # unchanged across configs, so arms are compared on adaptation, not scale.
    rm = float(rng.lognormal(-cfg.sigma_rate ** 2 / 2, cfg.sigma_rate)) \
        if cfg.sigma_rate > 0 else 1.0
    wm = float(rng.lognormal(-cfg.sigma_wtp ** 2 / 2, cfg.sigma_wtp)) \
        if cfg.sigma_wtp > 0 else 1.0
    dm = DOW_RATE[day % 7] if cfg.dow else 1.0
    return DayState(rate_mult=rm, wtp_mult=wm, dow_mult=dm)
QTY_CAP = 3
QTY_DECAY = 0.55            # 2nd unit worth 55% of the 1st, 3rd 55% of 2nd

# Arrivals per hour (office-lobby machine).
HOURLY_RATE = {
    7: 6.0, 8: 6.0, 9: 3.0, 10: 3.0, 11: 10.0, 12: 10.0, 13: 10.0,
    14: 1.5, 15: 1.5, 16: 1.5, 17: 4.0, 18: 4.0, 19: 4.0,
}
# Hourly WTP multiplier: the lunch crowd wants it more than the 3pm stroller.
HOURLY_WTP_MULT = {
    7: 1.05, 8: 1.05, 9: 0.90, 10: 0.90, 11: 1.15, 12: 1.15, 13: 1.15,
    14: 0.75, 15: 0.75, 16: 0.75, 17: 0.95, 18: 0.95, 19: 0.95,
}
WTP_SIGMA = 0.30            # lognormal spread of per-consumer, per-SKU WTP
BODEGA_MARKUP = 1.15        # the outside option: pricier, plus a walk
PATIENCE = 0.35             # P(unconverted consumer retries later today)

# (sku, wtp_mu_dollars, unit_cost, salvage, shelf_life_days, par_stock)
CATALOG_SPEC = [
    ("cola",      2.20, 0.70, 0.10, 60, 12),
    ("diet-cola", 2.10, 0.70, 0.10, 60, 10),
    ("water",     1.60, 0.30, 0.05, 90, 12),
    ("chips",     1.90, 0.60, 0.10, 30, 10),
    ("candy",     1.70, 0.50, 0.10, 45, 10),
    ("energy",    3.10, 1.10, 0.15, 60,  8),
    ("sandwich",  5.20, 2.20, 0.30,  2,  6),   # perishable
    ("fruit-cup", 3.60, 1.40, 0.20,  3,  6),   # perishable
]


def hour_of(tick: int) -> int:
    return 7 + tick * 10 // 60  # 96 ten-minute ticks → 07:00–22:50


def rate_at(tick: int) -> float:
    return HOURLY_RATE.get(hour_of(tick), 0.5)


def wtp_mult_at(tick: int) -> float:
    return HOURLY_WTP_MULT.get(hour_of(tick), 0.85)


def bundle_value(wtp: dict[str, float], sku: str, qty: int) -> float:
    """THE canonical diminishing-marginal bundle value, in dollars — the one
    implementation behind the consumer's choices, the Nash engine's buyer
    utilities, and the runner's accounting."""
    return sum(wtp[sku] * (QTY_DECAY ** (i - 1)) for i in range(1, qty + 1))


def best_bundle(wtp: dict[str, float], prices: dict[str, float],
                stock: dict[str, int] | None = None) -> tuple[str | None, int, float]:
    """Utility-maximizing (sku, qty, surplus$) against a price board,
    optionally capped by per-SKU stock DURING the search (so a short SKU
    loses to a stocked alternative instead of being clamped after)."""
    best = (None, 0, 0.0)
    for sku, p in prices.items():
        cap = QTY_CAP if stock is None else min(QTY_CAP, stock.get(sku, 0))
        u = 0.0
        for n in range(1, cap + 1):
            u += wtp[sku] * (QTY_DECAY ** (n - 1))
            s = u - n * p
            if s > best[2]:
                best = (sku, n, s)
    return best


@dataclass
class Consumer:
    wtp: dict[str, float]       # per-SKU dollar value of the FIRST unit (hour-adjusted)
    walk_cost: float            # dollars of hassle to use the bodega instead
    patience: float
    uid: int = 0                # stable identity from the FIRST arrival — survives returns

    def marginal(self, sku: str, i: int) -> float:
        """Dollar value of the i-th unit (1-based)."""
        return self.wtp[sku] * (QTY_DECAY ** (i - 1))

    def best_bundle(self, prices: dict[str, float],
                    stock: dict[str, int] | None = None) -> tuple[str | None, int, float]:
        return best_bundle(self.wtp, prices, stock)


def sample_consumer(master_seed: int, day: int, tick: int, k: int,
                    catalog: dict[str, Listing],
                    cfg: WorldConfig = DEFAULT_CONFIG) -> Consumer:
    """Paired across arms: depends only on (master, day, tick, k, cfg) —
    never on anything a policy did. Consumers draw from the TRUE demand
    process (WTP_MU × hour × today's shock); only the operator's estimate
    is noisy. `uid` is the consumer's stable identity: liar assignment and
    anything else person-level keys on it, so a returning consumer stays
    the same person."""
    rng = np.random.default_rng(substream(master_seed, "cons", day, tick, k))
    mult = wtp_mult_at(tick) * day_state(cfg, master_seed, day).wtp_mult
    wtp = {sku: float(rng.lognormal(math.log(WTP_MU[sku] * mult), WTP_SIGMA))
           for sku in catalog}
    return Consumer(wtp=wtp, walk_cost=float(rng.uniform(0.5, 2.0)),
                    patience=PATIENCE, uid=substream(master_seed, "uid", day, tick, k))


WTP_MU = {sku: mu for sku, mu, *_ in CATALOG_SPEC}


def _profit_optimal_list_price(sku_mu: float, unit_cost: float,
                               peak_only: bool = False) -> float:
    """PROFIT-optimal single price against the arrival-weighted WTP mixture
    (all-day, the competent operator's sticker) or, with peak_only, against
    the PEAK crowd alone — the high-anchor ceiling for negotiation to
    discount from."""
    ticks = [t for t in range(TICKS_PER_DAY)
             if not peak_only or wtp_mult_at(t) >= 1.0]
    weights = np.array([rate_at(t) for t in ticks])
    weights = weights / weights.sum()
    mults = np.array([wtp_mult_at(t) for t in ticks])
    grid = np.linspace(max(unit_cost, 0.3 * sku_mu), 2.0 * sku_mu, 240)
    from scipy import stats
    best_p, best_profit = grid[0], -1.0
    for p in grid:
        sell = stats.lognorm.sf(p, s=WTP_SIGMA, scale=sku_mu * mults)
        profit = float((p - unit_cost) * (weights * sell).sum())
        if profit > best_profit:
            best_p, best_profit = float(p), profit
    return round(round(best_p / 0.05) * 0.05, 2)


def build_catalog(cfg: WorldConfig = DEFAULT_CONFIG,
                  master_seed: int = 0) -> dict[str, Listing]:
    """The operator's board. With sigma_cal > 0 the sticker is optimized
    against a NOISY estimate of demand (μ̂ = μ·lognormal(0, σ_cal)) — a
    competent operator with finite history, not an omniscient one. The
    estimate is also what DYNAMIC arms believe about demand structure
    (level playing field: they adapt, they don't secretly know more)."""
    cat = {}
    for sku, mu, cost, salv, life, par in CATALOG_SPEC:
        if cfg.sigma_cal > 0:
            rng = np.random.default_rng(substream(master_seed, "cal", sku))
            mu_est = float(mu * rng.lognormal(0.0, cfg.sigma_cal))
        else:
            mu_est = mu
        cat[sku] = Listing(sku=sku,
                           list_price=_profit_optimal_list_price(
                               mu_est, cost, peak_only=cfg.anchor_peak),
                           unit_cost=cost, salvage=salv,
                           shelf_life_days=life, par_stock=par,
                           wtp_mu_est=mu_est)
    return cat


def fresh_machine(machine_id: str, catalog: dict[str, Listing],
                  cfg: WorldConfig = DEFAULT_CONFIG,
                  master_seed: int = 0) -> MachineState:
    state = MachineState(machine_id=machine_id, listings=catalog, lots=[])
    restock(state, cfg, master_seed)
    return state


def restock(state: MachineState, cfg: WorldConfig = DEFAULT_CONFIG,
            master_seed: int = 0) -> None:
    """Nightly: top every SKU back to par with a fresh lot. Glut days
    (case deals) double a perishable delivery — spoilage risk made real."""
    for sku, listing in state.listings.items():
        need = listing.par_stock - state.stock(sku)
        if cfg.glut_prob > 0 and listing.shelf_life_days <= 3:
            rng = np.random.default_rng(substream(master_seed, "glut", state.day, sku))
            if rng.random() < cfg.glut_prob:
                need += listing.par_stock
        if need > 0:
            state.lots.append(Lot(sku=sku, quantity=need,
                                  expires_day=state.day + listing.shelf_life_days))


def end_of_day(state: MachineState, cfg: WorldConfig = DEFAULT_CONFIG,
               master_seed: int = 0) -> dict:
    """Expire dead lots (salvage), advance the day, restock. Returns the
    day's spoilage accounting."""
    spoiled_units, spoilage_cost = 0, 0.0
    keep = []
    for lot in state.lots:
        if lot.quantity > 0 and lot.expires_day <= state.day:
            listing = state.listings[lot.sku]
            spoiled_units += lot.quantity
            spoilage_cost += lot.quantity * (listing.unit_cost - listing.salvage)
        elif lot.quantity > 0:
            keep.append(lot)
    state.lots = keep
    state.day += 1
    state.tick = 0
    restock(state, cfg, master_seed)
    return {"spoiled_units": spoiled_units, "spoilage_cost": round(spoilage_cost, 2)}


def arrivals_at(master_seed: int, day: int, tick: int,
                cfg: WorldConfig = DEFAULT_CONFIG) -> int:
    """Poisson arrivals this tick — paired across arms by construction."""
    rng = np.random.default_rng(substream(master_seed, "arr", day, tick))
    ds = day_state(cfg, master_seed, day)
    return int(rng.poisson(rate_at(tick) / 6.0 * ds.rate_mult * ds.dow_mult))

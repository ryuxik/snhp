"""Reference-price & churn: the fairness model that decides how much of the
high-anchor value is SAFELY harvestable.

Grounded in the dual-entitlement / transaction-utility literature:
  * consumers carry a REFERENCE price per good (EWMA of prices paid, plus a
    weaker update from prices merely observed);
  * paying ABOVE reference is punished with loss-aversion weight (default
    2.0× per dollar), paying below enjoyed at ~0.5×;
  * a quoted DISCOUNT from a visible list carries a small framing bonus
    (kappa — "I got a deal"), the mechanism by which high-anchor + computed
    discounts may escape the penalty that visible increases trigger. THE
    HYPOTHESIS UNDER TEST, not an assumption: kappa is a knob;
  * dissatisfaction accumulates (sticker shock on visits, above-reference
    payments) and converts into PERMANENT churn — the long-run cost of
    harvesting captive surplus.

Everything is off unless WorldConfig.regulars > 0; committed artifacts are
unaffected (guarded by the reproducibility test).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from vend.core import substream
from vend.world import (TICKS_PER_DAY, WTP_MU, WTP_SIGMA, WorldConfig,
                        best_bundle, bundle_value, day_state, wtp_mult_at)

# fairness parameters (literature-anchored defaults; all overridable)
LOSS_AVERSION = 2.0        # $ penalty per $ paid above reference
GAIN_WEIGHT = 0.5          # $ bonus per $ paid below reference
DEAL_FRAMING = 0.15        # kappa: bonus per $ of visible discount off list
REF_ALPHA_PAID = 0.20      # reference EWMA weight for prices PAID
REF_ALPHA_SEEN = 0.05      # ...for prices merely observed on the board
SHOCK_THRESHOLD = 1.10     # board > 110% of reference → sticker shock
CHURN_RATE = 0.05          # dissatisfaction → daily P(churn) = 1-exp(-d*rate)
FORGIVE = 0.90             # daily decay of dissatisfaction


@dataclass
class Regular:
    uid: int
    wtp: dict[str, float]          # persistent tastes
    walk_cost: float
    visit_prob: float              # P(visit) on a given day
    home_tick: int                 # habitual time of day
    ref: dict[str, float] = field(default_factory=dict)
    dissat: float = 0.0
    active: bool = True
    quotes_seen: int = 0     # habituation: quote friction decays 0.85^n

    def fairness(self, sku: str, unit_price: float, qty: int,
                 list_price: float | None) -> float:
        """Transaction utility in dollars (Thaler): reference comparison
        plus the deal-framing glow for visible discounts off a list."""
        r = self.ref[sku]
        if unit_price <= r:
            t = GAIN_WEIGHT * (r - unit_price)
        else:
            t = -LOSS_AVERSION * (unit_price - r)
        if list_price is not None and unit_price < list_price:
            t += DEAL_FRAMING * (list_price - unit_price)
        return qty * t


class RegularPool:
    """The machine's repeat customers. Identical initial pool across arms
    (seeded); references and churn evolve per-arm — that endogeneity IS the
    experiment."""

    REPLENISH_PER_DAY = 0.7   # exogenous inflow (new tenants/hires); joins
                              # happen regardless of policy — churn is a NET
                              # shrink against the pool that kept both

    def __init__(self, cfg: WorldConfig, master_seed: int, catalog,
                 market_ref: dict[str, float]):
        self.cfg = cfg
        self.seed = master_seed
        self.catalog = catalog
        self.market_ref = dict(market_ref)
        self.cap = cfg.regulars
        self._next_id = cfg.regulars
        self.pool: list[Regular] = [self._spawn(i) for i in range(cfg.regulars)]

    def _spawn(self, i: int) -> Regular:
        rng = np.random.default_rng(substream(self.seed, "regpool", i))
        home = int(rng.choice(TICKS_PER_DAY, p=_visit_time_weights()))
        mult = wtp_mult_at(home)
        wtp = {s: float(rng.lognormal(np.log(WTP_MU[s] * mult), WTP_SIGMA))
               for s in self.catalog}
        return Regular(
            uid=substream(self.seed, "reg", i),
            wtp=wtp, walk_cost=float(rng.uniform(0.5, 2.0)),
            visit_prob=float(rng.uniform(0.25, 0.75)),
            home_tick=home,
            ref=dict(self.market_ref))

    def visits_for_day(self, day: int) -> dict[int, list[Regular]]:
        """tick → visiting regulars (deterministic, arm-independent draw of
        WHO visits; what happens to them diverges by arm)."""
        ds = day_state(self.cfg, self.seed, day)
        out: dict[int, list[Regular]] = {}
        for i, reg in enumerate(self.pool):
            if not reg.active:
                continue
            rng = np.random.default_rng(substream(self.seed, "visit", day, i))
            if rng.random() < reg.visit_prob * ds.dow_mult:
                tick = int(min(TICKS_PER_DAY - 1,
                               max(0, reg.home_tick + rng.integers(-3, 4))))
                out.setdefault(tick, []).append(reg)
        return out

    def end_day(self, day: int) -> int:
        """Forgiveness + churn draws + exogenous replenishment (fresh
        regulars join with MARKET references — and immediately face
        whatever board this arm posts). Returns how many churned today."""
        churned = 0
        for i, reg in enumerate(self.pool):
            if not reg.active:
                continue
            reg.dissat *= FORGIVE
            p = 1.0 - float(np.exp(-reg.dissat * CHURN_RATE))
            rng = np.random.default_rng(substream(self.seed, "churn", day, i))
            if rng.random() < p:
                reg.active = False
                churned += 1
        rng = np.random.default_rng(substream(self.seed, "join", day))
        joins = int(rng.poisson(self.REPLENISH_PER_DAY))
        for _ in range(joins):
            if self.active_count() >= self.cap:
                break
            self.pool.append(self._spawn(self._next_id))
            self._next_id += 1
        return churned

    def active_count(self) -> int:
        return sum(1 for r in self.pool if r.active)


def _visit_time_weights():
    from vend.world import rate_at
    w = np.array([rate_at(t) for t in range(TICKS_PER_DAY)], dtype=float)
    return w / w.sum()


def regular_board_decision(reg: Regular, prices: dict[str, float],
                           stock: dict[str, int],
                           outside_prices: dict[str, float]):
    """Best bundle for a regular, INCLUDING transaction utility. Returns
    (sku, qty, raw_surplus, faced_price) or (None, 0, 0, None). Also applies
    sticker-shock and observation updates as side effects."""
    best = (None, 0, 0.0, None)
    best_total = 0.0
    for sku, p in prices.items():
        cap = min(3, stock.get(sku, 0))
        for q in range(1, cap + 1):
            raw = bundle_value(reg.wtp, sku, q) - q * p
            tot = raw + reg.fairness(sku, p, q, None)
            if tot > best_total:
                best_total, best = tot, (sku, q, raw, p)
    o_sku, _, o_s = best_bundle(reg.wtp, outside_prices)
    s_out = (o_s - reg.walk_cost) if o_sku else 0.0
    # observation effects: the board anchors the reference a little, and a
    # board far above reference is a sticker shock even without a purchase
    for sku, p in prices.items():
        r = reg.ref[sku]
        reg.ref[sku] = (1 - REF_ALPHA_SEEN) * r + REF_ALPHA_SEEN * p
        if p > r * SHOCK_THRESHOLD and sku == max(
                reg.wtp, key=lambda s: reg.wtp[s]):
            reg.dissat += (p - r) / r * 0.5
    if best[0] is not None and best_total > 0 and best_total >= s_out:
        return best
    return (None, 0, 0.0, None)


def settle_regular(reg: Regular, sku: str, unit_price: float, qty: int):
    """Post-purchase psychology: reference update, above-reference pain,
    and — v2, symmetric per the transaction-utility literature — below-
    reference RELIEF: a good deal heals accumulated dissatisfaction."""
    r = reg.ref[sku]
    reg.ref[sku] = (1 - REF_ALPHA_PAID) * r + REF_ALPHA_PAID * unit_price
    if unit_price > r:
        reg.dissat += (unit_price - r) / r
    else:
        reg.dissat = max(0.0, reg.dissat - (r - unit_price) / r)

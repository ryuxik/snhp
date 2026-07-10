"""ONE batch-perishables world, TWO venue calibrations (bakery, flowers).

The clock ticks in half-hours inside a day; inventory lives in dated lots
whose AGE sets a freshness tier that multiplies consumer WTP (fresh 1.0,
day-old 0.55 at the bakery; age-linear remaining-vase-life at the florist).
Spoilage at end of life is waste at cost — no salvage channel exists.

Honesty notes (the modeling choices reviewers should attack):
  * The static baseline is STRONG where it can be: per-SKU "appeal" is
    INVERTED from the cultural list price so that price IS the profit-
    optimal all-day posted price for the FRESH tier — a competent sticker,
    not a strawman. Dynamic arms may only ever discount from it.
  * The bake/order quantity is a GUT plan against the CONTROL's calendar
    (like fashion's buy — the coupling is the point): expected FRESH units
    at list, counting every arrival as a fresh-day buyer. Aging is the
    plan's blind spot — day-old-shelf and dump-day volume are IN the plan,
    exactly as clearance volume was in fashion's. All arms inherit the same
    morning bake / weekly order (paired, drawn before any pricing exists);
    only the 2pm mini-bake reacts to the arm's own shelf (a gut stock rule,
    boba's maybe_cook pattern — deterministic, no extra randomness).
  * Consumers draw from the TRUE demand process; the production
    miscalibration (sigma_miscal, mean-one lognormal per bake/order) is the
    operator's error. Policies forecast with the true structural model
    (favorable to dynamic arms, flagged as in vend) but never see today's
    day shock.
  * Event-spike days (Valentine's-like, ×6 arrivals at the florist) are
    PUBLIC calendar knowledge: the plan orders up for them, capped by the
    supply constraint (oven / wholesale allocation, ×2) — scarcity is real.
  * Policy demand forecasts treat each (sku, age) cell as separable;
    consumers actually choose the best basket across the whole board
    (vend P0's cannibalization lesson applies and is measured, not
    assumed away).
  * No returns/patience: an unconverted arrival is lost for the day.
"""
from __future__ import annotations

import functools
import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from bakeshop import calibration as cal


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (the gauntlet pattern, copied from
    vend.core): blake2b of the master seed and any hashable parts, folded
    to 63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


TICKS_PER_HOUR = 2          # half-hour ticks
QTY_CAP = 3


# ── venue spec (data-driven; both venues run the same core) ──────────────
@dataclass(frozen=True)
class Item:
    sku: str
    list_price: float        # the ceiling, always (discount-only clamp)
    unit_cost: float         # sunk at bake/delivery; waste books at cost
    attention: float         # P(an arrival shops this SKU)
    life: int                # sellable days: age 0 .. life-1, then waste
    fresh_mults: tuple       # WTP multiplier by age (len == life)
    control_fracs: tuple     # the CULTURAL calendar: price fraction by age
    appeal: float            # lognormal WTP scale making list the optimum


@dataclass(frozen=True)
class Venue:
    name: str
    items: tuple             # tuple[Item, ...]
    open_hour: int
    close_hour: int
    hourly_rate: tuple       # ((hour, arrivals/hour), ...)
    hourly_wtp: tuple        # ((hour, mult), ...)
    wtp_sigma: float
    qty_decay: float
    aged_pull_hour: int | None   # bakery: day-old shelf pulled at noon
    overproduce: float       # bakery's "full shelves sell bread" overbake
    delivery_every: int      # 1 = daily bake; 7 = weekly wholesale drop
    minibake_hour: int | None
    minibake_trigger: float
    minibake_frac: float
    spike_mult: float
    supply_cap: float
    outside_markup: float
    walk_lo: float
    walk_hi: float

    @property
    def ticks_per_day(self) -> int:
        return (self.close_hour - self.open_hour) * TICKS_PER_HOUR

    def item(self, sku: str) -> Item:
        return self._by_sku[sku]

    def __post_init__(self):
        object.__setattr__(self, "_by_sku", {i.sku: i for i in self.items})
        object.__setattr__(self, "_rate", dict(self.hourly_rate))
        object.__setattr__(self, "_wtp", dict(self.hourly_wtp))

    def hour_of(self, tick: int) -> int:
        return self.open_hour + tick // TICKS_PER_HOUR

    def rate_at(self, tick: int) -> float:
        return self._rate[self.hour_of(tick)]

    def wtp_mult_at(self, tick: int) -> float:
        return self._wtp[self.hour_of(tick)]


# ── the strong sticker: invert appeal from the cultural list price ───────
_SQRT2 = math.sqrt(2.0)


def sf(x: float, scale: float, sigma: float) -> float:
    """P(WTP > x) under lognormal(log scale, sigma) — closed form."""
    if x <= 0:
        return 1.0
    if scale <= 0:
        return 0.0
    return 0.5 * math.erfc(math.log(x / scale) / (sigma * _SQRT2))


def _pstar_mixture(appeal: float, cost: float, sigma: float,
                   weights: list, mults: list) -> float:
    """Profit-max posted price against the arrival-weighted hourly WTP
    mixture (first fresh unit — the sticker's job)."""
    best_p, best = cost + 0.01, -1.0
    lo, hi = cost + 0.01, 3.5 * appeal + cost
    for i in range(320):
        p = lo + (hi - lo) * i / 319
        profit = (p - cost) * sum(w * sf(p, appeal * m, sigma)
                                  for w, m in zip(weights, mults))
        if profit > best:
            best_p, best = p, profit
    return best_p


def _appeal_for_list(list_price: float, cost: float, sigma: float,
                     weights: list, mults: list) -> float:
    """Invert the cultural menu: the appeal scale at which `list_price` IS
    the profit-optimal all-day fresh sticker (the boba pattern) — what
    makes the control a competent operator, not a strawman."""
    lo, hi = 0.2 * list_price, 4.0 * list_price
    for _ in range(28):
        mid = (lo + hi) / 2
        if _pstar_mixture(mid, cost, sigma, weights, mults) < list_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _build_bakery() -> Venue:
    hours = sorted(cal.BAKERY_HOURLY_RATE)
    w = [cal.BAKERY_HOURLY_RATE[h] for h in hours]
    tot = sum(w)
    weights = [x / tot for x in w]
    mults = [cal.BAKERY_HOURLY_WTP[h] for h in hours]
    items = []
    for sku, lp, cost, att, life in cal.BAKERY_CATALOG:
        items.append(Item(
            sku=sku, list_price=lp, unit_cost=cost, attention=att, life=life,
            fresh_mults=cal.BAKERY_FRESH_MULTS,
            control_fracs=(1.0, cal.BAKERY_DAY_OLD_FRAC),
            appeal=_appeal_for_list(lp, cost, cal.BAKERY_WTP_SIGMA,
                                    weights, mults)))
    return Venue(
        name="bakery", items=tuple(items),
        open_hour=cal.BAKERY_OPEN, close_hour=cal.BAKERY_CLOSE,
        hourly_rate=tuple(sorted(cal.BAKERY_HOURLY_RATE.items())),
        hourly_wtp=tuple(sorted(cal.BAKERY_HOURLY_WTP.items())),
        wtp_sigma=cal.BAKERY_WTP_SIGMA, qty_decay=cal.BAKERY_QTY_DECAY,
        aged_pull_hour=cal.BAKERY_DAY_OLD_PULL_HOUR,
        overproduce=cal.BAKERY_OVERBAKE, delivery_every=1,
        minibake_hour=cal.BAKERY_MINIBAKE_HOUR,
        minibake_trigger=cal.BAKERY_MINIBAKE_TRIGGER,
        minibake_frac=cal.BAKERY_MINIBAKE_FRAC,
        spike_mult=cal.BAKERY_SPIKE_MULT, supply_cap=cal.BAKERY_SUPPLY_CAP,
        outside_markup=cal.BAKERY_OUTSIDE_MARKUP,
        walk_lo=cal.BAKERY_WALK[0], walk_hi=cal.BAKERY_WALK[1])


def _build_flowers() -> Venue:
    hours = sorted(cal.FLOWER_HOURLY_RATE)
    w = [cal.FLOWER_HOURLY_RATE[h] for h in hours]
    tot = sum(w)
    weights = [x / tot for x in w]
    mults = [cal.FLOWER_HOURLY_WTP[h] for h in hours]
    items = []
    for sku, lp, cost, att, life in cal.FLOWER_CATALOG:
        # age-linear decay: a day-a stem has (life − a) of its vase days
        # left — the buyer values exactly the remaining fraction
        fresh = tuple(round((life - a) / life, 6) for a in range(life))
        fracs = tuple(1.0 if a < cal.FLOWER_DUMP_AGE else cal.FLOWER_DUMP_FRAC
                      for a in range(life))
        items.append(Item(
            sku=sku, list_price=lp, unit_cost=cost, attention=att, life=life,
            fresh_mults=fresh, control_fracs=fracs,
            appeal=_appeal_for_list(lp, cost, cal.FLOWER_WTP_SIGMA,
                                    weights, mults)))
    return Venue(
        name="flowers", items=tuple(items),
        open_hour=cal.FLOWER_OPEN, close_hour=cal.FLOWER_CLOSE,
        hourly_rate=tuple(sorted(cal.FLOWER_HOURLY_RATE.items())),
        hourly_wtp=tuple(sorted(cal.FLOWER_HOURLY_WTP.items())),
        wtp_sigma=cal.FLOWER_WTP_SIGMA, qty_decay=cal.FLOWER_QTY_DECAY,
        aged_pull_hour=None,          # the dump bucket sits out all day
        overproduce=1.0, delivery_every=cal.FLOWER_DELIVERY_EVERY,
        minibake_hour=None, minibake_trigger=0.0, minibake_frac=0.0,
        spike_mult=cal.FLOWER_SPIKE_MULT, supply_cap=cal.FLOWER_SUPPLY_CAP,
        outside_markup=cal.FLOWER_OUTSIDE_MARKUP,
        walk_lo=cal.FLOWER_WALK[0], walk_hi=cal.FLOWER_WALK[1])


_VENUES: dict[str, Venue] = {}


def get_venue(name: str) -> Venue:
    if name not in _VENUES:
        _VENUES[name] = {"bakery": _build_bakery,
                         "flowers": _build_flowers}[name]()
    return _VENUES[name]


# ── config & day shocks ──────────────────────────────────────────────────
@dataclass(frozen=True)
class BakeshopConfig:
    sigma_miscal: float = 0.15   # bake/order gut error (mean-one lognormal)
    spike_prob: float = 0.0      # P(a day is an event-spike day)
    sigma_day: float = 0.20      # day-level arrival shock (mean-one)


DEFAULT_CONFIG = BakeshopConfig()


@functools.lru_cache(maxsize=8192)
def day_rate_mult(cfg: BakeshopConfig, master_seed: int, day: int) -> float:
    """Mean-one lognormal day shock: E[e^X] = 1 with mu = -sigma²/2 — the
    average demand is unchanged across configs, so arms are compared on
    adaptation, not scale."""
    if cfg.sigma_day <= 0:
        return 1.0
    rng = np.random.default_rng(substream(master_seed, "shock", day))
    return float(rng.lognormal(-cfg.sigma_day ** 2 / 2, cfg.sigma_day))


@functools.lru_cache(maxsize=8192)
def is_spike_day(master_seed: int, day: int, cfg: BakeshopConfig) -> bool:
    """Valentine's-like event day — PUBLIC calendar knowledge (the plan and
    the dynamic arms may all use it; the control's calendar ignores it)."""
    if cfg.spike_prob <= 0:
        return False
    rng = np.random.default_rng(substream(master_seed, "spike", day))
    return bool(rng.random() < cfg.spike_prob)


def demand_mult(venue: Venue, master_seed: int, day: int,
                cfg: BakeshopConfig) -> float:
    """Today's arrival multiplier: day shock × event spike."""
    m = day_rate_mult(cfg, master_seed, day)
    if is_spike_day(master_seed, day, cfg):
        m *= venue.spike_mult
    return m


def arrivals_at(venue: Venue, master_seed: int, day: int, tick: int,
                cfg: BakeshopConfig = DEFAULT_CONFIG) -> int:
    """Poisson arrivals this tick — paired across arms by construction."""
    rng = np.random.default_rng(substream(master_seed, "arr", day, tick))
    rate = venue.rate_at(tick) / TICKS_PER_HOUR \
        * demand_mult(venue, master_seed, day, cfg)
    return int(rng.poisson(rate))


# ── consumers ────────────────────────────────────────────────────────────
@dataclass
class Consumer:
    wtp: dict[str, float]    # first-unit FRESH dollar value per SKU
                             # (0.0 = not shopping that SKU today)
    walk_cost: float         # $-hassle of the outside option
    uid: int = 0


def sample_consumer(venue: Venue, master_seed: int, day: int, tick: int,
                    k: int, cfg: BakeshopConfig = DEFAULT_CONFIG) -> Consumer:
    """Paired across arms: depends only on (master, day, tick, k, cfg) —
    never on anything a policy did. Per SKU: an attention Bernoulli (do
    they shop it at all?) and a lognormal WTP draw — both drawn always so
    the stream is stable across configs (the boba pattern)."""
    rng = np.random.default_rng(substream(master_seed, "cons", day, tick, k))
    mult = venue.wtp_mult_at(tick)
    wtp = {}
    for it in venue.items:
        shops = rng.random() < it.attention      # both draws always taken,
        draw = float(rng.lognormal(math.log(it.appeal * mult),
                                   venue.wtp_sigma))
        wtp[it.sku] = draw if shops else 0.0
    walk = float(rng.uniform(venue.walk_lo, venue.walk_hi))
    return Consumer(wtp=wtp, walk_cost=walk,
                    uid=substream(master_seed, "uid", day, tick, k))


# ── the canonical bundle math ────────────────────────────────────────────
def ladder(decay: float, qty: int) -> float:
    """Σ decay^(i-1) — the diminishing-quantity multiplier."""
    return sum(decay ** i for i in range(qty))


def units_sf(price: float, fresh_mult: float, scale: float, sigma: float,
             decay: float, cap: int = QTY_CAP) -> float:
    """Expected units per shopper at a per-unit `price` for one freshness
    tier: the i-th unit sells iff wtp·fresh_mult·decay^(i-1) > price."""
    if fresh_mult <= 0:
        return 0.0
    return sum(sf(price / (fresh_mult * decay ** i), scale, sigma)
               for i in range(cap))


def bundle_value(venue: Venue, consumer: Consumer,
                 lines: list[tuple[str, int, int]]) -> float:
    """THE dollar value of a basket of (sku, age, qty) lines: additive
    across SKUs, diminishing down the qty ladder within a SKU, freshness
    tier multiplying the whole SKU line. One implementation behind the
    consumer's board choice, the Nash engine's buyer utilities, and the
    runner's accounting. Lines must not repeat a SKU."""
    total = 0.0
    for sku, age, qty in lines:
        it = venue.item(sku)
        total += consumer.wtp[sku] * it.fresh_mults[age] \
            * ladder(venue.qty_decay, qty)
    return total


def best_board_basket(venue: Venue, consumer: Consumer,
                      board: dict[tuple[str, int], float],
                      stock: dict[tuple[str, int], int]
                      ) -> tuple[list[tuple[str, int, int, float]], float]:
    """Utility-maximizing basket against a posted board. Cross-SKU values
    are additive and prices linear, so the choice decomposes per SKU: the
    best (age, qty) with positive surplus, stock-capped DURING the search.
    Returns ([(sku, age, qty, unit_price)], total surplus)."""
    lines, total = [], 0.0
    for it in venue.items:
        if consumer.wtp[it.sku] <= 0:
            continue
        best = None
        for (sku, age), p in board.items():
            if sku != it.sku:
                continue
            cap = min(QTY_CAP, stock.get((sku, age), 0))
            for q in range(1, cap + 1):
                s = consumer.wtp[sku] * it.fresh_mults[age] \
                    * ladder(venue.qty_decay, q) - q * p
                if best is None or s > best[3]:
                    best = (sku, age, q, s, p)
        if best is not None and best[3] > 1e-9:
            lines.append((best[0], best[1], best[2], best[4]))
            total += best[3]
    return lines, total


def outside_surplus(venue: Venue, consumer: Consumer) -> float:
    """The competitor across the street: fresh goods only, at markup, minus
    the walk — the same additive basket chooser."""
    total = 0.0
    for it in venue.items:
        if consumer.wtp[it.sku] <= 0:
            continue
        p = it.list_price * venue.outside_markup
        best = 0.0
        for q in range(1, QTY_CAP + 1):
            s = consumer.wtp[it.sku] * ladder(venue.qty_decay, q) - q * p
            best = max(best, s)
        total += best
    return max(0.0, total - consumer.walk_cost)


# ── shop state: dated lots, ages, waste at cost ──────────────────────────
@dataclass
class Lot:
    sku: str
    quantity: int
    baked_day: int           # age = state.day − baked_day


@dataclass
class ShopState:
    venue_name: str
    day: int = 0
    tick: int = 0
    lots: list = field(default_factory=list)

    def stock(self, sku: str, age: int) -> int:
        return sum(l.quantity for l in self.lots
                   if l.sku == sku and l.quantity > 0
                   and self.day - l.baked_day == age)

    def cells(self) -> list[tuple[str, int]]:
        """Live (sku, age) cells, deterministic order."""
        seen = {}
        for l in self.lots:
            if l.quantity > 0:
                seen[(l.sku, self.day - l.baked_day)] = True
        return sorted(seen)

    def take(self, sku: str, age: int, n: int) -> None:
        """Sell n units of one freshness tier. Validates BEFORE mutating
        (the vend take() contract)."""
        if self.stock(sku, age) < n:
            raise ValueError(f"insufficient stock for {sku} age {age}")
        for l in self.lots:
            if l.sku == sku and self.day - l.baked_day == age and l.quantity > 0:
                got = min(l.quantity, n)
                l.quantity -= got
                n -= got
                if n == 0:
                    return


# ── production: the gut plan against the control's calendar ─────────────
@functools.lru_cache(maxsize=64)
def base_plan(venue_name: str) -> dict[str, float]:
    """Expected FRESH units per day at LIST price, counting every arrival
    as a fresh-day buyer — the gut merchandise plan, built to the control's
    calendar and blind to aging (dump-day volume is IN the plan, exactly as
    clearance volume was in fashion's buy)."""
    venue = get_venue(venue_name)
    plan = {}
    for it in venue.items:
        plan[it.sku] = sum(
            venue.rate_at(t) / TICKS_PER_HOUR * it.attention
            * units_sf(it.list_price, 1.0, it.appeal * venue.wtp_mult_at(t),
                       venue.wtp_sigma, venue.qty_decay)
            for t in range(venue.ticks_per_day))
    return plan


def _order_err(master_seed: int, tag: str, day: int, sku: str,
               sigma: float) -> float:
    """Mean-one lognormal gut error, drawn per bake/order per SKU —
    identical across arms by construction."""
    if sigma <= 0:
        return 1.0
    rng = np.random.default_rng(substream(master_seed, tag, day, sku))
    return float(rng.lognormal(-sigma ** 2 / 2, sigma))


def begin_day(state: ShopState, venue: Venue, master_seed: int,
              cfg: BakeshopConfig = DEFAULT_CONFIG
              ) -> tuple[dict[str, int], int, float]:
    """Morning production. Bakery (delivery_every=1): bake the plan ×
    overbake, ×min(spike_mult, supply_cap) on a public event day. Florist
    (delivery_every=7): on delivery days order min(life, 7) days of the
    fresh plan per SKU; on event days a special drop of ×min(spike, cap)
    one day's plan arrives fresh (the Valentine's truck). Returns
    (today's morning quantities, produced units, produced cost $)."""
    plan = base_plan(venue.name)
    spike = is_spike_day(master_seed, state.day, cfg)
    morning: dict[str, int] = {it.sku: 0 for it in venue.items}
    produced, cost = 0, 0.0
    for it in venue.items:
        qty = 0
        if state.day % venue.delivery_every == 0:
            days = min(it.life, venue.delivery_every)
            q = plan[it.sku] * days * venue.overproduce
            if spike and venue.delivery_every == 1:
                q *= min(venue.spike_mult, venue.supply_cap)
            qty += int(round(q * _order_err(master_seed, "bake", state.day,
                                            it.sku, cfg.sigma_miscal)))
        if spike and venue.delivery_every > 1:
            q = plan[it.sku] * min(venue.spike_mult, venue.supply_cap)
            qty += int(round(q * _order_err(master_seed, "spikedrop",
                                            state.day, it.sku,
                                            cfg.sigma_miscal)))
        if qty > 0:
            state.lots.append(Lot(sku=it.sku, quantity=qty,
                                  baked_day=state.day))
            morning[it.sku] = qty
            produced += qty
            cost += qty * it.unit_cost
    return morning, produced, round(cost, 2)


def maybe_minibake(state: ShopState, venue: Venue,
                   morning: dict[str, int]) -> tuple[int, float]:
    """The operator's 2pm gut check: when a SKU's FRESH shelf is below
    minibake_trigger × the morning bake, bake minibake_frac more. Reacts to
    the arm's own shelf (deterministic given the run) — the same heuristic
    for every arm, like boba's maybe_cook."""
    produced, cost = 0, 0.0
    if venue.minibake_hour is None:
        return 0, 0.0
    for it in venue.items:
        if morning.get(it.sku, 0) <= 0:
            continue
        if state.stock(it.sku, 0) < venue.minibake_trigger * morning[it.sku]:
            qty = int(round(venue.minibake_frac * morning[it.sku]))
            if qty > 0:
                state.lots.append(Lot(sku=it.sku, quantity=qty,
                                      baked_day=state.day))
                produced += qty
                cost += qty * it.unit_cost
    return produced, round(cost, 2)


def end_of_day(state: ShopState, venue: Venue) -> dict:
    """Close: lots on their last sellable day become waste AT COST (no
    salvage channel — day-old croissants past the shelf go to the bin,
    dead stems to the compost). Everything else ages one day."""
    waste_units, waste_cost = 0, 0.0
    keep = []
    for l in state.lots:
        if l.quantity <= 0:
            continue
        age = state.day - l.baked_day
        if age >= venue.item(l.sku).life - 1:
            waste_units += l.quantity
            waste_cost += l.quantity * venue.item(l.sku).unit_cost
        else:
            keep.append(l)
    state.lots = keep
    state.day += 1
    state.tick = 0
    return {"waste_units": waste_units, "waste_cost": round(waste_cost, 2)}

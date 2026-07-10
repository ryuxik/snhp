"""The boba shop world: clock, arrivals, consumers, queue, tapioca batches.

Calibration constants (menu, toppings, capacity, batch size, daily cups,
rent) come from block/calibration.py — the ONE source of truth for the
block. This module adds the dynamics BOBA.md sketched: barista-minutes as
the scarce resource, wait-sensitive balking, and pearls on a 4-hour clock.

Honesty notes (the modeling choices reviewers should attack):
  * The static baseline is STRONG: drink/topping "appeal" is INVERTED from
    the calibration menu so each list price is the profit-optimal posted
    price for the arrival-weighted all-day crowd — the shop's gut menu is
    right on average across the day, blind within it. Dynamic arms may only
    ever discount from it.
  * Consumers have ONE favorite drink (categorical) and value substitutes
    at a flat 0.55 of their own appeal-scaled draw. Per-drink demand is
    then the clean lognormal the computed arm models — model ≈ truth,
    favorable to the dynamic arms, flagged here as in vend.
  * Balking is linear in expected wait (8%/min, BOBA.md) and resolves
    BEFORE ordering. The cart arm's quote happens BEFORE the walk-in balk
    (that IS the product: the order is a cart on a phone), so its
    disagreement point prices balk risk — but a now-slot deal still faces
    the same balk roll (a right-now pickup means standing in that line),
    and deferred slots are capped by real slack capacity at the slot.
  * Deferred pickups consume real capacity at their slot. The relief the
    engine credits for freeing a peak slot is a first-order estimate:
    current balk probability × mean drink margin, zero off-peak.
  * Pearls are consumed at ORDER time (reservation), drinks at service.
  * No returns/patience: an unconverted arrival is lost for the day.
"""
from __future__ import annotations

import functools
import hashlib
import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from block.calibration import (BOBA_CAPACITY_PER_MIN, BOBA_DAILY_CUPS,
                               BOBA_MENU, BOBA_RENT_PER_DAY,
                               BOBA_TAPIOCA_BATCH, BOBA_TOPPINGS)


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


# ── clock & capacity ─────────────────────────────────────────────────────
TICKS_PER_DAY = 72          # 10-minute ticks: 10:00–22:00
OPEN_HOUR = 10
PEAK_STAFF_HOURS = range(14, 19)   # 2 staff 14:00–19:00 (BOBA.md)
OFFPEAK_CAPACITY_PER_MIN = BOBA_CAPACITY_PER_MIN / 2.0   # 1 staff


def hour_of(tick: int) -> int:
    return OPEN_HOUR + tick * 10 // 60


def service_rate_at(tick: int) -> float:
    """Drinks per MINUTE the bar can make right now."""
    return (BOBA_CAPACITY_PER_MIN if hour_of(tick) in PEAK_STAFF_HOURS
            else OFFPEAK_CAPACITY_PER_MIN)


BALK_SLOPE = 0.08           # P(balk) = min(1, 0.08 × expected wait minutes)

# ── demand shape ─────────────────────────────────────────────────────────
# Arrivals per hour: lunch (12–14) and after-school (15–18) spikes, scaled
# so the static arm lands near BOBA_DAILY_CUPS (~260 cups/day).
HOURLY_RATE = {
    10: 14.0, 11: 24.0, 12: 48.0, 13: 48.0, 14: 29.0, 15: 43.0,
    16: 48.0, 17: 43.0, 18: 31.0, 19: 22.0, 20: 16.0, 21: 11.0,
}
# Hourly WTP multiplier: the lunch rush wants it more than the 9pm stroll.
HOURLY_WTP_MULT = {
    10: 0.92, 11: 1.00, 12: 1.06, 13: 1.06, 14: 0.96, 15: 1.04,
    16: 1.04, 17: 1.04, 18: 1.00, 19: 0.95, 20: 0.90, 21: 0.85,
}

WTP_SIGMA = 0.45            # lognormal spread of a consumer's drink draw
TOP_SIGMA = 0.70            # toppings: taste spread among people who like one
# Topping tastes are SPARSE: most people want 0–1 add-ons, and someone who
# can't stand grass jelly values it at zero, not a small positive draw —
# without this the Nash engine "wins" by piling all four toppings on every
# cup at cost-plus, which no real shop sees.
TOP_LIKE_PROB = {"pearls": 0.65, "pudding": 0.35,
                 "grass-jelly": 0.30, "cheese-foam": 0.40}
CROSS_DISCOUNT = 0.55       # a non-favorite drink is worth 55% of own draw
QTY_CAP = 3
# Qty appetite is PER CONSUMER: most people are solo (a second milk tea is
# nearly worthless to them), a minority carry a group order (BOBA.md's
# "multi-unit case with teeth"). Without this split the Nash engine upsells
# literally everyone to three cups — a tell that the decay, not the deal,
# was doing the work.
GROUP_SHARE = 0.30
GROUP_DECAY = 0.60          # 2nd cup worth 60% (a friend's order)
SOLO_DECAY = 0.15           # 2nd cup worth 15% (you, later, melted ice)
OUTSIDE_MARKUP = 1.10       # the coffee shop next door: same menu, +10%

# favorite-drink shares (classic milk tea is the anchor order)
POPULARITY = {"classic-milk-tea": 0.30, "fruit-tea": 0.26,
              "brown-sugar": 0.24, "matcha-latte": 0.20}

DRINKS = {name: (price, cost) for name, price, cost in BOBA_MENU}
TOPS = {name: (price, cost) for name, price, cost in BOBA_TOPPINGS}
DRINK_PRICE = {d: p for d, (p, _) in DRINKS.items()}
DRINK_COST = {d: c for d, (_, c) in DRINKS.items()}
TOP_PRICE = {t: p for t, (p, _) in TOPS.items()}
TOP_COST = {t: c for t, (_, c) in TOPS.items()}
MEAN_DRINK_MARGIN = float(np.mean([p - c for p, c in DRINKS.values()]))
RENT_PER_DAY = BOBA_RENT_PER_DAY

# ── tapioca batches ──────────────────────────────────────────────────────
BATCH_SERVINGS = BOBA_TAPIOCA_BATCH     # 40 servings per cook
BATCH_LIFE_TICKS = 24                   # 4 hours of quality life
PEARL_RESTOCK_TRIGGER = 15              # the operator's gut: cook when low
PEARL_COST = TOP_COST["pearls"]


# ── config & day shocks ──────────────────────────────────────────────────
@dataclass(frozen=True)
class BobaConfig:
    sigma_shock: float = 0.0        # day-level arrival shock (lognormal)
    flexible_share: float = 0.30    # share of pickup-flexible consumers


DEFAULT_CONFIG = BobaConfig()


@functools.lru_cache(maxsize=4096)
def day_rate_mult(cfg: BobaConfig, master_seed: int, day: int) -> float:
    """Mean-one lognormal demand shock: E[e^X] = 1 with mu = -sigma²/2, so
    average demand is unchanged across configs — arms are compared on
    adaptation, not scale."""
    if cfg.sigma_shock <= 0:
        return 1.0
    rng = np.random.default_rng(substream(master_seed, "shock", day))
    return float(rng.lognormal(-cfg.sigma_shock ** 2 / 2, cfg.sigma_shock))


def arrivals_at(master_seed: int, day: int, tick: int,
                cfg: BobaConfig = DEFAULT_CONFIG) -> int:
    """Poisson arrivals this tick — paired across arms by construction."""
    rng = np.random.default_rng(substream(master_seed, "arr", day, tick))
    rate = HOURLY_RATE[hour_of(tick)] / 6.0 * day_rate_mult(cfg, master_seed, day)
    return int(rng.poisson(rate))


# ── appeal calibration (the strong static baseline) ─────────────────────
def _hour_weights() -> tuple[np.ndarray, np.ndarray]:
    hours = sorted(HOURLY_RATE)
    w = np.array([HOURLY_RATE[h] for h in hours], dtype=float)
    return w / w.sum(), np.array([HOURLY_WTP_MULT[h] for h in hours])


@functools.lru_cache(maxsize=None)
def _mixture_pstar(appeal: float, cost: float, sigma: float) -> float:
    """Profit-max posted price against the arrival-weighted hourly WTP
    mixture — the competent all-day sticker for one item."""
    from scipy import stats
    from scipy.optimize import minimize_scalar
    w, m = _hour_weights()
    res = minimize_scalar(
        lambda p: -(p - cost) * float(
            (w * stats.lognorm.sf(p, s=sigma, scale=appeal * m)).sum()),
        bounds=(cost + 0.01, 4.0 * appeal + cost), method="bounded")
    return float(res.x)


@functools.lru_cache(maxsize=None)
def appeal_for_list(list_price: float, cost: float, sigma: float,
                    hour_mults: bool = True) -> float:
    """Invert the calibration menu: the appeal scale at which `list_price`
    IS the profit-optimal all-day posted price. This is what makes static a
    competent operator, not a strawman."""
    lo, hi = 0.2 * list_price, 4.0 * list_price
    for _ in range(28):
        mid = (lo + hi) / 2
        p = (_mixture_pstar(mid, cost, sigma) if hour_mults
             else _pstar_single(mid, cost, sigma))
        if p < list_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@functools.lru_cache(maxsize=None)
def _pstar_single(appeal: float, cost: float, sigma: float) -> float:
    """Profit-max price against a single lognormal crowd (no hour mixture
    — toppings, and the computed arm's hourly re-solve)."""
    from scipy import stats
    from scipy.optimize import minimize_scalar
    res = minimize_scalar(
        lambda p: -(p - cost) * float(stats.lognorm.sf(p, s=sigma, scale=appeal)),
        bounds=(cost + 0.01, 4.0 * appeal + cost), method="bounded")
    return float(res.x)


DRINK_APPEAL = {d: appeal_for_list(p, c, WTP_SIGMA) for d, (p, c) in DRINKS.items()}
# toppings carry no hour multiplier: invert against the flat crowd
TOP_APPEAL = {t: appeal_for_list(p, c, TOP_SIGMA, hour_mults=False)
              for t, (p, c) in TOPS.items()}


def _sf(x: float, scale: float, sigma: float) -> float:
    """Lognormal survival, closed-form (cheap enough for import-time
    expectations without dragging scipy into every call)."""
    if x <= 0:
        return 1.0
    return 0.5 * math.erfc((math.log(x / scale)) / (sigma * math.sqrt(2)))


def expected_cups_per_arrival(hour: int) -> float:
    """E[cups] per arrival at LIST prices in this hour: the i-th cup sells
    iff wtp·decay^(i-1) > list, mixed over the solo/group split. Ignores
    cross-drink substitution and topping pull-through — a forecast, used
    for the congestion map and the computed arm's run-out shadow, never
    for accounting."""
    m = HOURLY_WTP_MULT[hour]
    total = 0.0
    for d, share in POPULARITY.items():
        scale = DRINK_APPEAL[d] * m
        for w, decay in ((1.0 - GROUP_SHARE, SOLO_DECAY),
                         (GROUP_SHARE, GROUP_DECAY)):
            total += share * w * sum(
                _sf(DRINK_PRICE[d] / (decay ** i), scale, WTP_SIGMA)
                for i in range(QTY_CAP))
    return total


# Congestion-prone hours: expected drink demand ≥ 50% of bar capacity.
# With the calibration numbers this is the pre-2pm lunch crunch — the
# second staffer arrives at 14:00 and absorbs the after-school spike.
PEAK_HOURS = tuple(
    h for h in sorted(HOURLY_RATE)
    if HOURLY_RATE[h] * expected_cups_per_arrival(h)
    >= 0.5 * 60.0 * (BOBA_CAPACITY_PER_MIN if h in PEAK_STAFF_HOURS
                     else OFFPEAK_CAPACITY_PER_MIN))


# ── consumers ────────────────────────────────────────────────────────────
# Defer disutility for a +30/+60-minute pickup slot, by flexibility type.
FLEX_DEFER = {0: 0.0, 3: 0.30, 6: 0.50}     # "I'll grab it after class"
RIGID_DEFER = {0: 0.0, 3: 1.60, 6: 3.20}    # "I'm on my lunch break"


@dataclass
class Consumer:
    fav: str                       # the drink they came for
    wtp: dict[str, float]          # first-cup dollar value per drink
    top_wtp: dict[str, float]      # per-cup dollar value per topping
    flexible: bool                 # would take a later pickup for a discount
    qty_decay: float = SOLO_DECAY  # i-th cup worth decay^(i-1) of the first
    uid: int = 0

    def defer_cost(self, slot_ticks: int) -> float:
        table = FLEX_DEFER if self.flexible else RIGID_DEFER
        return table[slot_ticks]


def sample_consumer(master_seed: int, day: int, tick: int, k: int,
                    cfg: BobaConfig = DEFAULT_CONFIG) -> Consumer:
    """Paired across arms: depends only on (master, day, tick, k, cfg) —
    never on anything a policy did. One lognormal draw scales all drink
    values (their 'thirst'); the favorite gets it in full, substitutes at
    CROSS_DISCOUNT. Topping tastes are independent draws."""
    rng = np.random.default_rng(substream(master_seed, "cons", day, tick, k))
    roll, acc, fav = rng.random(), 0.0, next(iter(POPULARITY))
    for d, share in POPULARITY.items():
        acc += share
        if roll < acc:
            fav = d
            break
    mult = HOURLY_WTP_MULT[hour_of(tick)]
    eps = float(rng.lognormal(0.0, WTP_SIGMA))
    wtp = {d: DRINK_APPEAL[d] * mult * eps * (1.0 if d == fav else CROSS_DISCOUNT)
           for d in DRINKS}
    top_wtp = {}
    for t in TOPS:
        like = rng.random() < TOP_LIKE_PROB[t]   # both draws always taken,
        draw = float(rng.lognormal(0.0, TOP_SIGMA))  # so the stream is stable
        top_wtp[t] = TOP_APPEAL[t] * draw if like else 0.0
    flexible = bool(rng.random() < cfg.flexible_share)
    decay = GROUP_DECAY if rng.random() < GROUP_SHARE else SOLO_DECAY
    return Consumer(fav=fav, wtp=wtp, top_wtp=top_wtp, flexible=flexible,
                    qty_decay=decay,
                    uid=substream(master_seed, "uid", day, tick, k))


# ── shop state: FIFO queue + tapioca batches ─────────────────────────────
@dataclass
class Batch:
    servings: int
    expires_tick: int


@dataclass
class ShopState:
    day: int = 0
    tick: int = 0
    queue: deque = field(default_factory=deque)   # FIFO orders, drinks each
    carry: float = 0.0                            # fractional barista-minutes
    batches: list[Batch] = field(default_factory=list)
    scheduled: dict[int, int] = field(default_factory=dict)  # slot tick → drinks
    batches_cooked: int = 0

    def queue_drinks(self) -> int:
        return sum(self.queue)

    def pearl_stock(self) -> int:
        return sum(b.servings for b in self.batches)


def open_shop(day: int = 0) -> ShopState:
    """10:00 sharp: the operator cooks batch 1 before the doors open."""
    state = ShopState(day=day)
    cook_batch(state)
    return state


def cook_batch(state: ShopState) -> None:
    state.batches.append(Batch(BATCH_SERVINGS, state.tick + BATCH_LIFE_TICKS))
    state.batches_cooked += 1


def maybe_cook(state: ShopState) -> None:
    """The operator's gut heuristic: another batch when pearls run low."""
    if state.pearl_stock() < PEARL_RESTOCK_TRIGGER:
        cook_batch(state)


def expire_batches(state: ShopState) -> float:
    """Toss batches past their 4-hour life. Returns waste dollars (at cost;
    dead pearls have no salvage)."""
    waste = 0.0
    keep = []
    for b in state.batches:
        if b.expires_tick <= state.tick and b.servings > 0:
            waste += b.servings * PEARL_COST
        elif b.servings > 0:
            keep.append(b)
    state.batches = keep
    return waste


def close_out(state: ShopState) -> float:
    """22:00: whatever pearls are left get tossed with the wash-up."""
    waste = sum(b.servings for b in state.batches) * PEARL_COST
    state.batches = []
    return waste


def take_pearls(state: ShopState, n: int) -> None:
    """Serve n pearl servings, earliest-expiring batch first. Validates
    BEFORE mutating (the vend take() contract)."""
    if state.pearl_stock() < n:
        raise ValueError("insufficient pearl stock")
    for b in sorted(state.batches, key=lambda b: b.expires_tick):
        got = min(b.servings, n)
        b.servings -= got
        n -= got
        if n == 0:
            return


def release_scheduled(state: ShopState) -> None:
    """Deferred pickups come due: their drinks join the FIFO queue now."""
    drinks = state.scheduled.pop(state.tick, 0)
    if drinks > 0:
        state.queue.append(drinks)


def serve_queue(state: ShopState) -> int:
    """One tick of bar work: make up to (rate × 10 min + carry) drinks,
    FIFO, splitting a group order across ticks if needed. Idle capacity
    does not bank — the fractional carry survives only while a queue
    exists to absorb it."""
    cap = service_rate_at(state.tick) * 10.0 + state.carry
    made = 0
    while state.queue and made + 1 <= cap:
        head = state.queue[0]
        take = min(head, int(cap - made))
        if take <= 0:
            break
        made += take
        if take == head:
            state.queue.popleft()
        else:
            state.queue[0] = head - take
    state.carry = (cap - made) if state.queue else 0.0
    return made


def expected_wait_minutes(state: ShopState) -> float:
    return state.queue_drinks() / service_rate_at(state.tick)


def balk_prob(state: ShopState) -> float:
    """BOBA.md's queue abandonment: ~8% per minute of expected wait,
    resolved BEFORE ordering."""
    return min(1.0, BALK_SLOPE * expected_wait_minutes(state))


def slot_capacity(state: ShopState, slot_tick: int) -> float:
    """Drinks a +30/+60 pickup slot can still absorb: the slot tick's bar
    rate minus the walk-in demand expected to need it minus what is already
    booked there. A deferred order is only balk-free because the drink is
    READY at pickup — which is only true where slack capacity exists, so
    slots are a finite resource the shop cannot oversell (this is what
    keeps the cart arm inside the same physics as everyone else)."""
    h = hour_of(min(slot_tick, TICKS_PER_DAY - 1))
    exp_walkins = HOURLY_RATE[h] / 6.0 * expected_cups_per_arrival(h)
    return (service_rate_at(slot_tick) * 10.0 - exp_walkins
            - state.scheduled.get(slot_tick, 0))


def capacity_relief(state: ShopState, qty: int, slot_ticks: int) -> float:
    """Dollar value TO THE SHOP of moving `qty` drinks from the live queue
    to a +30/+60 slot: the expected margin of a peak sale the freed
    capacity enables. First-order estimate: the current balk probability is
    the chance a marginal walk-in is being lost right now, so each freed
    peak slot rescues ≈ balk_prob × mean drink margin. Zero off-peak, and
    zero if the slot still lands inside the peak (no capacity was freed
    where it is scarce)."""
    if slot_ticks <= 0 or hour_of(state.tick) not in PEAK_HOURS:
        return 0.0
    slot_hour = hour_of(min(state.tick + slot_ticks, TICKS_PER_DAY - 1))
    b_now = balk_prob(state)
    b_slot = b_now if slot_hour in PEAK_HOURS else 0.0
    return qty * MEAN_DRINK_MARGIN * (b_now - b_slot)


# ── the canonical bundle chooser ─────────────────────────────────────────
def qty_ladder(decay: float, qty: int) -> float:
    """Σ decay^(i-1) — the diminishing-cups multiplier."""
    return sum(decay ** i for i in range(qty))


def bundle_value(consumer: Consumer, drink: str, qty: int,
                 tops: tuple[str, ...]) -> float:
    """THE dollar value of a cart. The WHOLE per-cup bundle (drink AND its
    toppings) diminishes down the qty ladder — your third cup's pudding is
    worth as little as your third cup. (Valuing toppings flat per cup lets
    a Nash engine sell three cups to a solo buyer just to harvest the
    topping value three times — a bug wearing a bundle.) One implementation
    behind the consumer's menu choice, the Nash engine's buyer utilities,
    and the runner's accounting."""
    per_cup = consumer.wtp[drink] + sum(consumer.top_wtp[t] for t in tops)
    return per_cup * qty_ladder(consumer.qty_decay, qty)


def best_menu_order(consumer: Consumer, drink_prices: dict[str, float],
                    top_prices: dict[str, float],
                    pearls_ok: bool = True) -> tuple[str | None, int,
                                                     tuple[str, ...], float]:
    """Utility-maximizing (drink, qty, toppings, surplus$) against a posted
    board. Toppings are priced per cup but VALUED down the qty ladder, so
    the take-it threshold tightens with qty: t joins iff its ladder value
    beats q prices."""
    best = (None, 0, (), 0.0)
    avail = [t for t in top_prices if pearls_ok or t != "pearls"]
    for q in range(1, QTY_CAP + 1):
        lad = qty_ladder(consumer.qty_decay, q)
        chosen = tuple(t for t in avail
                       if consumer.top_wtp[t] * lad > q * top_prices[t])
        top_val = sum(consumer.top_wtp[t] for t in chosen)
        top_price = sum(top_prices[t] for t in chosen)
        for d, p in drink_prices.items():
            s = (consumer.wtp[d] + top_val) * lad - q * (p + top_price)
            if s > best[3]:
                best = (d, q, chosen, s)
    return best


def outside_surplus(consumer: Consumer) -> float:
    """The coffee shop next door: same menu at ×1.1, no queue. The markup
    IS the friction (no separate walk cost)."""
    prices = {d: p * OUTSIDE_MARKUP for d, p in DRINK_PRICE.items()}
    tops = {t: p * OUTSIDE_MARKUP for t, p in TOP_PRICE.items()}
    _, _, _, s = best_menu_order(consumer, prices, tops)
    return max(0.0, s)

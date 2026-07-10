"""Pricing policies — the three arms of the bakeshop experiment.

  control/1  — the CULTURAL practice, honestly implemented. Bakery: full
               price all day, day-old shelf at −50% next MORNING only
               (pulled at noon). Flowers: full price, dump bucket at −70%
               from day 4 of vase life. Blind to stock, demand, calendar.
  computed/1 — age-aware posted re-pricing, hourly, per (sku, age) cell:
               argmax p·min(D_rest_of_life(p), stock) on a descending grid
               (ties go to the HIGHER price, so scarcity holds at list —
               the fashion stockout-hazard move at day scale). Aged tiers
               are offered ALL day. Discount-only off list.
  nego/1     — per-arrival Nash bundles over (item × freshness tier ×
               quantity × price rungs), single lines and two-SKU pairs.
               Event-consistent disagreement: the buyer's no-deal world is
               their best basket off the CONTROL board (including the
               control's own day-old shelf / dump bucket!) or the outside
               option; the shop's is the same event, with the units it
               hands over valued at their CALENDAR RECOVERY (what the
               cultural price path would have salvaged from them). Buffer:
               the shop's believed gain must clear max($0.25, 10% of the
               bundle's list value). Discount-only vs list. Fallback board
               = the control board (never worse UX than the culture).

Model notes (flagged in results):
  * Aged-tier demand is RESIDUAL demand: a shopper takes the aged unit
    only where its surplus beats the freshest live tier of the same SKU
    (closed-form interval on the lognormal draw). Without this, a
    separable forecast prices day-old croissants ABOVE fresh clearing
    prices — a bug wearing a markdown.
  * The dynamic arms' demand model is the true structural process
    (favorable, as in vend/boba) but never sees today's day shock; cells
    are still separable ACROSS SKUs (vend P0's diversion lesson applies
    and is measured, not assumed away).
  * nego's opportunity cost of a unit is its calendar recovery under the
    control price path it actually falls back to — scarce fresh stock
    recovers ≈ list (nothing to negotiate, the H-B3 behavior); a glut
    dying tonight recovers ≈ 0 (every dollar is found money).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bakeshop.world import (QTY_CAP, TICKS_PER_HOUR, BakeshopConfig,
                            Consumer, DEFAULT_CONFIG, ShopState, Venue,
                            best_board_basket, is_spike_day, ladder,
                            outside_surplus, sf)

PRICE_RUNGS = 8
N_GRID = 24
MIN_GAIN_ABS = 0.25          # don't-negotiate-for-pennies buffer:
MIN_GAIN_FRAC = 0.10         # max($0.25, 10% of bundle list value)


# ── the control board (one implementation; nego's fallback too) ──────────
def control_board(state: ShopState, venue: Venue
                  ) -> dict[tuple[str, int], float]:
    """The cultural calendar as a price board: list × control_frac by age.
    Bakery day-old cells exist only before the noon pull."""
    hour = venue.hour_of(state.tick)
    board = {}
    for sku, age in state.cells():
        if age >= 1 and venue.aged_pull_hour is not None \
                and hour >= venue.aged_pull_hour:
            continue
        it = venue.item(sku)
        board[(sku, age)] = round(it.list_price * it.control_fracs[age], 2)
    return board


@dataclass
class ControlPolicy:
    policy_id: str = "control/1"

    def board(self, state: ShopState, venue: Venue, master_seed: int,
              cfg: BakeshopConfig) -> dict[tuple[str, int], float]:
        return control_board(state, venue)


# ── the canonical demand forecast (computed's solve, nego's recovery) ────
def _tier_units(venue: Venue, sku: str, age: int, price: float,
                scale: float, fresher: tuple | None) -> float:
    """Expected units per arrival for one (sku, age) tier at `price`, given
    the freshest live competitor of the same SKU at (p_f, fm_f) — or None.

    RESIDUAL demand, closed form: the i-th unit of this tier is taken iff
    its surplus is positive AND beats the same rung of the fresher tier:
        w > price/(fm·δ^i)                                (affordable)
        w < max( (p_f − price)/(δ^i (fm_f − fm)),         (beats fresher)
                 p_f/(fm_f·δ^i) )                          (fresher unaffordable)
    so demand is an interval probability of the lognormal draw w."""
    it = venue.item(sku)
    fm = it.fresh_mults[age]
    if fm <= 0:
        return 0.0
    sig = venue.wtp_sigma
    total = 0.0
    for i in range(QTY_CAP):
        d = venue.qty_decay ** i
        lo = price / (fm * d)
        if fresher is None:
            total += sf(lo, scale, sig)
            continue
        p_f, fm_f = fresher
        if fm_f <= fm + 1e-12:
            total += sf(lo, scale, sig)
            continue
        hi = (p_f - price) / (d * (fm_f - fm)) if p_f > price else 0.0
        w_f0 = p_f / (fm_f * d)
        upper = max(hi, w_f0)
        if upper > lo:
            total += max(0.0, sf(lo, scale, sig) - sf(upper, scale, sig))
    return total * it.attention


def _spike_mult(venue: Venue, master_seed: int, day: int,
                cfg: BakeshopConfig) -> float:
    """The PUBLIC part of the day's demand (the event calendar). The
    mean-one day shock is deliberately absent: no policy sees it."""
    return venue.spike_mult if is_spike_day(master_seed, day, cfg) else 1.0


def demand_today(venue: Venue, cfg: BakeshopConfig, master_seed: int,
                 day: int, sku: str, age: int, tick0: int, price: float,
                 fresher: tuple | None, until_hour: int | None = None
                 ) -> float:
    """Expected units of one tier from tick0 to close (or `until_hour`)."""
    m = _spike_mult(venue, master_seed, day, cfg)
    it = venue.item(sku)
    total = 0.0
    for t in range(tick0, venue.ticks_per_day):
        if until_hour is not None and venue.hour_of(t) >= until_hour:
            break
        scale = it.appeal * venue.wtp_mult_at(t)
        total += venue.rate_at(t) / TICKS_PER_HOUR * m \
            * _tier_units(venue, sku, age, price, scale, fresher)
    return total


def demand_whole_day(venue: Venue, cfg: BakeshopConfig, master_seed: int,
                     day: int, sku: str, age: int, price: float,
                     fresher: tuple | None, until_hour: int | None = None
                     ) -> float:
    return demand_today(venue, cfg, master_seed, day, sku, age, 0, price,
                        fresher, until_hour)


def _youngest_future_age(venue: Venue, master_seed: int, day: int,
                         cfg: BakeshopConfig) -> int:
    """The freshest age tier the shop will have on `day` (schedule + event
    drops — public knowledge): 0 on bake/delivery/spike days, else days
    since the last delivery."""
    if venue.delivery_every == 1:
        return 0
    if is_spike_day(master_seed, day, cfg):
        return 0
    return day % venue.delivery_every


# ── computed/1 ───────────────────────────────────────────────────────────
@dataclass
class ComputedPolicy:
    """Hourly age-aware re-price per cell, freshest tier first so aged
    tiers price against the fresher price actually on the board.
    `aged_only` is the H-B1 decomposition ablation: fresh tiers stay AT
    list, only aging tiers are re-priced (and offered all day)."""
    policy_id: str = "computed/1"
    aged_only: bool = False
    _cache: dict = field(default_factory=dict)

    def board(self, state: ShopState, venue: Venue, master_seed: int,
              cfg: BakeshopConfig) -> dict[tuple[str, int], float]:
        # prices are decided from the state at the hour's FIRST arrival and
        # held for the hour ("hourly re-price") — deterministic given the run
        key = (state.day, venue.hour_of(state.tick))
        if key not in self._cache:
            self._cache.clear()          # one live board at a time
            self._cache[key] = self._solve(state, venue, master_seed, cfg)
        return self._cache[key]

    def _solve(self, state: ShopState, venue: Venue, master_seed: int,
               cfg: BakeshopConfig) -> dict[tuple[str, int], float]:
        tick0 = (venue.hour_of(state.tick) - venue.open_hour) \
            * TICKS_PER_HOUR
        board: dict[tuple[str, int], float] = {}
        for sku, age in sorted(state.cells(), key=lambda c: (c[0], c[1])):
            it = venue.item(sku)
            younger = [a for s, a in board if s == sku and a < age]
            if self.aged_only and age == 0:
                board[(sku, age)] = it.list_price
                continue
            fresher = None
            if younger:
                a0 = max(younger)        # the nearest fresher tier
                fresher = (board[(sku, a0)], it.fresh_mults[a0])
            stock = state.stock(sku, age)
            lp = it.list_price
            best_p, best = lp, -1.0
            for g in range(N_GRID):
                p = lp * (1.0 - 0.98 * g / (N_GRID - 1))
                dem = demand_today(venue, cfg, master_seed, state.day, sku,
                                   age, tick0, p, fresher)
                for d_ahead in range(1, it.life - age):
                    a2 = age + d_ahead
                    fut_min = _youngest_future_age(
                        venue, master_seed, state.day + d_ahead, cfg)
                    fut_fresher = None
                    if fut_min < a2:
                        fut_fresher = (lp, it.fresh_mults[fut_min])
                    dem += demand_whole_day(venue, cfg, master_seed,
                                            state.day + d_ahead, sku, a2,
                                            p, fut_fresher)
                obj = p * min(dem, float(stock))
                if obj > best + 1e-12:   # ties go to the HIGHER price
                    best_p, best = p, obj
            board[(sku, age)] = min(lp, round(best_p, 2))
        return board


# ── nego/1 ───────────────────────────────────────────────────────────────
def calendar_phases(state: ShopState, venue: Venue, master_seed: int,
                    cfg: BakeshopConfig, sku: str, age: int
                    ) -> list[tuple[float, float]]:
    """The control calendar's remaining plan for one tier, as (price,
    expected units) phases: the rest of today at today's calendar price
    (respecting the day-old pull window), then each future day of the
    unit's life at that day's calendar price, residual against the
    freshest tier the calendar will be showing. This is what the units
    would recover if the shop just kept running the culture."""
    it = venue.item(sku)
    day, tick0 = state.day, state.tick
    phases = []
    pull = venue.aged_pull_hour
    for d_ahead in range(0, it.life - age):
        a = age + d_ahead
        p = it.list_price * it.control_fracs[a]
        until = pull if (a >= 1 and pull is not None) else None
        if d_ahead == 0:
            if until is not None and venue.hour_of(tick0) >= until:
                continue                 # pulled already: sells nothing today
            dem_fn, t0 = demand_today, tick0
        else:
            dem_fn, t0 = demand_whole_day, 0
        fut_min = _youngest_future_age(venue, master_seed, day + d_ahead, cfg)
        fresher = None
        if fut_min < a:
            fresher = (it.list_price * it.control_fracs[fut_min],
                       it.fresh_mults[fut_min])
        if d_ahead == 0:
            dem = demand_today(venue, cfg, master_seed, day, sku, a, t0, p,
                               fresher, until)
        else:
            dem = demand_whole_day(venue, cfg, master_seed, day + d_ahead,
                                   sku, a, p, fresher, until)
        phases.append((p, dem))
    return phases


def calendar_recovery(phases: list[tuple[float, float]], stock: int,
                      qty: int) -> float:
    """R(stock) − R(stock − qty): the calendar's expected revenue from the
    marginal `qty` units, filling phases greedily (today first — leftovers
    age into the next phase). Waste has no salvage, so exhausted phases
    leave the marginal unit worth 0."""
    def R(s: float) -> float:
        rem, val = s, 0.0
        for p, dem in phases:
            sold = min(rem, dem)
            val += sold * p
            rem -= sold
            if rem <= 0:
                break
        return val
    return R(float(stock)) - R(float(max(0, stock - qty)))


@dataclass(frozen=True)
class Deal:
    lines: tuple             # ((sku, age, qty), ...) — distinct SKUs
    price: float             # bundle total, discount-only vs list
    value: float             # buyer's true bundle value
    list_value: float        # Σ qty × LIST (the ceiling; depth benchmark)
    u_shop: float            # price − calendar recovery of the lines
    d_shop: float            # shop's utility in the no-deal event
    u_buyer: float           # value − price
    d_buyer: float           # buyer's utility in the no-deal event
    why: tuple


@dataclass
class NegoPolicy:
    """Per-arrival Nash bundles. `pairs=False` is the H-B2 decomposition
    ablation: single-line deals only — the bundle channel removed."""
    policy_id: str = "nego/1"
    mode: str = "nego"
    pairs: bool = True

    def board(self, state: ShopState, venue: Venue, master_seed: int,
              cfg: BakeshopConfig) -> dict[tuple[str, int], float]:
        return control_board(state, venue)

    def quote_for(self, state: ShopState, venue: Venue, consumer: Consumer,
                  master_seed: int, cfg: BakeshopConfig) -> Deal | None:
        return nego_quote(state, venue, consumer, master_seed, cfg,
                          pairs=self.pairs)


_PHASES: dict[tuple, list] = {}


def _phases_cached(state: ShopState, venue: Venue, master_seed: int,
                   cfg: BakeshopConfig, sku: str, age: int) -> list:
    key = (venue.name, cfg, master_seed, state.day, state.tick, sku, age)
    if key not in _PHASES:
        if len(_PHASES) > 20000:
            _PHASES.clear()
        _PHASES[key] = calendar_phases(state, venue, master_seed, cfg,
                                       sku, age)
    return _PHASES[key]


def nego_quote(state: ShopState, venue: Venue, consumer: Consumer,
               master_seed: int, cfg: BakeshopConfig = DEFAULT_CONFIG, *,
               pairs: bool = True) -> Deal | None:
    """Nash bargaining over the bundle outcome space, in dollars.

    The disagreement point is ONE consistent no-deal event for both sides:
    the buyer shops the CONTROL board (the cultural calendar, including its
    own day-old shelf / dump bucket — the customer's honest alternative) or
    walks to the competitor:
      board wins  → buyer keeps that basket surplus; shop keeps the basket
                    revenue minus the calendar recovery of those units
      outside wins→ buyer keeps outside surplus; shop keeps NOTHING
    A buyer who would have paid the sticker gets a discount only out of
    newly created surplus (aging tiers moved while demand exists, sub-list
    conversion of a second SKU, up-sized quantities) — never out of margin
    the shop already had: covered fresh stock recovers ≈ list, so its
    floor IS list and scarcity has nothing to negotiate (H-B3)."""
    cells = state.cells()
    if not cells:
        return None

    ctx = {}
    for sku, age in cells:
        ctx[(sku, age)] = (_phases_cached(state, venue, master_seed, cfg,
                                          sku, age),
                           state.stock(sku, age))

    def recov(sku: str, age: int, qty: int) -> float:
        phases, s = ctx[(sku, age)]
        return calendar_recovery(phases, s, qty)

    # ── the no-deal event ──
    board = control_board(state, venue)
    stock = {c: ctx[c][1] for c in ctx}
    b_lines, s_board = best_board_basket(venue, consumer, board, stock)
    s_out = outside_surplus(venue, consumer)
    if b_lines and s_board > 1e-9 and s_board >= s_out:
        rev = sum(q * p for _, _, q, p in b_lines)
        d_s = rev - sum(recov(sku, age, q) for sku, age, q, _ in b_lines)
        d_b = s_board
    else:
        d_s, d_b = 0.0, max(0.0, s_out)

    # ── candidate lines, hoisted: buyer value, shop cost, list value ──
    lines = []
    for sku, age in cells:
        if consumer.wtp[sku] <= 0:
            continue
        it = venue.item(sku)
        fm = it.fresh_mults[age]
        cap = min(QTY_CAP, ctx[(sku, age)][1])
        for q in range(1, cap + 1):
            val = consumer.wtp[sku] * fm * ladder(venue.qty_decay, q)
            lines.append(((sku, age, q), val, recov(sku, age, q),
                          q * it.list_price))

    outcomes = [((l,), v, c, lv) for l, v, c, lv in lines]
    if pairs:
        for l1, v1, c1, lv1 in lines:
            for l2, v2, c2, lv2 in lines:
                if l2[0] == l1[0]:
                    continue          # distinct SKUs only
                if l2[2] != 1:
                    continue          # the add-on line is a single unit
                if l1[2] == 1 and l1[:2] > l2[:2]:
                    continue          # dedupe the symmetric single+single
                outcomes.append(((l1, l2), v1 + v2, c1 + c2, lv1 + lv2))

    best, best_score = None, None
    for ls, val, cost, listv in outcomes:
        if val <= cost:
            continue                  # no joint gain lives here
        floor = max(0.0, cost)
        if floor >= listv:
            rungs = [round(listv, 2)]
        else:
            step = (listv - floor) / (PRICE_RUNGS - 1)
            rungs = [round(floor + i * step, 2) for i in range(PRICE_RUNGS)]
        for p in rungs:
            gs, gb = (p - cost) - d_s, (val - p) - d_b
            if gs >= -1e-9 and gb >= -1e-9:
                score = (gs * gb, gs + gb)
                if best_score is None or score > best_score:
                    best = (ls, val, cost, listv, p)
                    best_score = score
    if best is None or (best_score[0] <= 0 and best_score[1] <= 1e-9):
        return None                   # nothing improves on the no-deal event

    ls, val, cost, listv, p = best
    u_s = p - cost
    # the buffer: the shop's believed gain must clear max($0.25, 10% of the
    # bundle's list value) — forecast noise must not leak margin
    if u_s - d_s < max(MIN_GAIN_ABS, MIN_GAIN_FRAC * listv):
        return None
    why = ["negotiated bundle" if len(ls) > 1 else "negotiated"]
    for sku, age, q in ls:
        tag = f"{q}x {sku}"
        if age >= 1:
            tag += f" (day {age + 1} of {venue.item(sku).life})"
        why.append(tag)
    if p < listv - 1e-9:
        why.append(f"${listv - p:.2f} under list")
    else:
        why.append("at list")
    return Deal(lines=ls, price=p, value=round(val, 4),
                list_value=round(listv, 2), u_shop=u_s, d_shop=d_s,
                u_buyer=val - p, d_buyer=d_b, why=tuple(why))

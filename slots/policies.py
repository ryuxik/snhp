"""Pricing policies — the three arms of the slot-economics experiment.

  static/1   — the posted list, always. By construction of the ratio-appeal
               inversion (world.venue) it is the profit-optimal all-day
               posted price: a competent operator, not a strawman.
  computed/1 — hourly posted re-price per future hour-window: hold at list
               when expected remaining list demand (D-hat) covers the
               window's free unit-ticks (the run-out shadow — the queue of
               future demand will eat every slot at full price), else the
               profit-max multiplier against that hour's crowd. Solved on
               the ratio scale; clamped discount-only.
  nego/1     — per-arrival Nash quote over (slot-shift x duration x price
               rung). Venue utility = expected margin (no-show-weighted)
               minus the opportunity cost of the span it occupies; buyer
               utility = value minus price minus shift disutility; the
               disagreement point is one consistent no-deal EVENT: the
               buyer books their best static-slot alternative at list (or
               takes the outside option / walks). Discount-only;
               don't-negotiate-for-pennies buffer max($0.50, 10% of the
               booking's list value).

               RELIEF FIX (post-registration, paper/CRITICAL-ANALYSIS.md
               §3): when the fallback books — so the deal is a SWAP of
               spans, not added occupancy — both spans are priced at the
               arm's LEARNED, realized MARGINAL per-hour slot value
               (HourMarginLearner: sold-out-gated realized margin per
               unit-tick, EWMA over its own days, the vend DemandLearner
               pattern). The capacity-relief credit for shifting someone
               off a peak slot is then the realized nego-regime margin
               per freed slot — nonzero only where the hour actually
               binds — MINUS the same-basis charge for the shoulder
               ticks the shifted booking now occupies. The old shadow
               priced the credit at the STATIC regime's list margin
               (overpaying: freed peak seats resell through discounted
               quotes when they resell at all, and un-bound hours resell
               nothing extra) and the shoulder at zero. When the
               fallback does NOT book (a would-be walkaway), the deal is
               added occupancy and keeps the conservative static
               displacement shadow as its guard, unchanged.

Model notes: both dynamic arms read the same D-hat forecast the world
publishes (true structural process, no day shock — favorable to them,
flagged in results). nego-noshift/1 is the H-S2 ablation: the identical
engine with the slot-shift axis frozen at the desired slot, so the edge
decomposes into shifting vs pure price cuts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from slots import calibration as C
from slots.world import (Customer, Venue, VenueState, best_board_booking,
                         can_book, capacity_shadow, expected_demand,
                         free_unit_ticks, list_mult)


@dataclass
class StaticPolicy:
    """The control: the venue's posted list, all day, every day."""
    policy_id: str = "static/1"
    mode: str = "board"

    def mult_of(self, state: VenueState):
        return list_mult


@dataclass
class ComputedPolicy:
    """GvR-for-slots: once an hour, re-solve each future hour-window's
    posted multiplier from remaining slot inventory vs expected remaining
    demand. When D-hat ≥ free unit-ticks the window will fill at list —
    hold there (no reason to discount); otherwise post the hour-crowd's
    profit-max multiplier (pre-solved at venue build; the discount-only
    clamp eats all upside above list by design).

    The board is decided from the state at the hour's FIRST arrival and
    held for the hour ("hourly re-price") — deterministic given the run."""
    policy_id: str = "computed/1"
    mode: str = "board"
    _cache: dict = field(default_factory=dict)

    def mult_of(self, state: VenueState):
        v = state.venue
        key = (state.day, v.hour_of(state.tick))
        if key not in self._cache:
            board = {}
            for h in v.hours:
                if h < v.hour_of(state.tick):
                    board[h] = 1.0          # the past is not for sale
                elif (expected_demand(v, state.tick, h)
                        >= free_unit_ticks(state, h)):
                    board[h] = 1.0          # run-out shadow: will fill at list
                else:
                    board[h] = v.mstar[h]
            self._cache[key] = board
        board = self._cache[key]
        return lambda h: board.get(h, 1.0)


RELIEF_WARMUP_FRAC = 0.6    # pre-history relief basis: this fraction of the
                            # static list margin per peak unit-tick


def warmup_hour_value(v: Venue, hour: int) -> float:
    """Slot value before the arm has any history of its own: a
    conservative fraction (0.6) of the static-regime mean list margin for
    peak hours — the credit the diagnosed defect paid in FULL — and 0
    off-peak (the static model's own shoulder valuation). Real learned
    values take over after the first day."""
    if hour in v.peak_hours:
        return RELIEF_WARMUP_FRAC * v.mean_margin_per_tick
    return 0.0


@dataclass
class HourMarginLearner:
    """Regime-consistent slot values — vend's DemandLearner pattern applied
    to slot-time. An EWMA, per hour, of THIS arm's OWN realized MARGINAL
    value of one unit-tick, measured from its own days:

        obs(h) = (fraction of hour-h ticks that ended the day at full
                  capacity) x (realized margin per SOLD unit-tick in h)

    The sold-out gate is what makes the estimate marginal rather than
    average: a freed slot-tick only enables an extra sale when the tick
    actually binds (ends the day sold out) — otherwise the would-be
    "displaced" buyer was never displaced, they had spare units anyway —
    and symmetrically, occupying a slack tick displaces nobody. The margin
    factor is realized in THIS regime (discounted resale and sub-list
    conversion included; settled bookings only — a no-show pays nothing).

    This is the post-registration fix for the H-S2 relief defect
    (paper/CRITICAL-ANALYSIS.md §3): the old shadow priced a freed peak
    slot at the STATIC regime's list margin with a demand-forecast
    displacement probability — a world the mechanism abolishes. Here the
    credit is the realized nego-regime margin per freed slot, and the
    shoulder slot a shifted booking occupies is charged on the same
    learned basis. Warmup: `warmup_hour_value` until a day of history
    exists for the hour."""
    alpha: float = 0.3          # vend's share_ewma
    _m: dict = field(default_factory=dict)   # hour -> $/unit-tick, learned

    def value(self, v: Venue, hour: int) -> float:
        got = self._m.get(hour)
        return got if got is not None else warmup_hour_value(v, hour)

    def end_day(self, v: Venue, hour_margin: dict, occupied) -> None:
        """Fold in one day of realized play: hour_margin[h] = settled
        margin attributed to hour h; occupied = the day's final occupancy
        grid (shown bookings only — no-shows released their spans)."""
        for h in v.hours:
            h0 = v.hidx(h) * 6
            span = occupied[h0:h0 + 6]
            occ_ticks = float(span.sum())
            if occ_ticks > 0:
                soldout_frac = float((span >= v.capacity).mean())
                obs = soldout_frac * hour_margin.get(h, 0.0) / occ_ticks
            else:
                obs = 0.0
            old = self._m.get(h)
            self._m[h] = obs if old is None else \
                (1 - self.alpha) * old + self.alpha * obs


def _span_value(v: Venue, start: int, dur: int, hour_value) -> float:
    """Dollar value of the unit-ticks in [start, start+dur) priced at
    hour_value(h) $/unit-tick — the learned (or warmup) regime basis."""
    end = start + dur
    total = 0.0
    for h in range(v.hour_of(start), v.hour_of(end - 1) + 1):
        h0 = v.hidx(h) * 6
        ov = min(end, h0 + 6) - max(start, h0)
        total += ov * hour_value(h)
    return total


@dataclass(frozen=True)
class SlotDeal:
    start: int
    n: int                     # steps
    price: float               # booking TOTAL, discount-only vs list
    cost: float
    list_price: float
    u_venue: float             # expected margin − span value of this outcome
    d_venue: float             # venue's event-consistent disagreement
    u_buyer: float             # value − price − shift disutility
    d_buyer: float             # buyer's best alternative (static slot / outside)
    relief: float              # value(no-deal span) − value(deal span), on the
                               # learned regime basis when the fallback books
    shifted: bool
    trimmed: bool
    cs: float                  # realized buyer surplus if they show
    why: tuple


@dataclass
class NegoPolicy:
    """The negotiated slot. Fallback is the plain list board, so the arm
    is never worse UX than static. `shift=False` is the pre-registered
    H-S2 ablation (price rungs and duration only, no slot-shifting).
    Carries its own HourMarginLearner: the runner feeds it each day's
    realized per-hour margins (`end_day`), and every quote prices span
    swaps at those learned values."""
    policy_id: str = "nego/1"
    mode: str = "nego"
    shift: bool = True
    min_gain_abs: float = 0.50      # don't-negotiate-for-pennies buffer:
    min_gain_frac: float = 0.10     # max($0.50, 10% of booking list value)
    learner: HourMarginLearner = field(default_factory=HourMarginLearner)

    def mult_of(self, state: VenueState):
        return list_mult

    def quote_for(self, state: VenueState, cust: Customer) -> SlotDeal | None:
        v = state.venue
        return nego_quote(state, cust, shift=self.shift,
                          min_gain_abs=self.min_gain_abs,
                          min_gain_frac=self.min_gain_frac,
                          hour_value=lambda h: self.learner.value(v, h))

    def end_day(self, v: Venue, hour_margin: dict, occupied) -> None:
        self.learner.end_day(v, hour_margin, occupied)


def _dur_candidates(n_req: int) -> list[int]:
    """The duration axis: the request, one step short, half, and one —
    small on purpose (a quote is a menu, not a search grid)."""
    return sorted({n_req, max(1, n_req - 1), max(1, (n_req + 1) // 2), 1},
                  reverse=True)


def nego_quote(state: VenueState, cust: Customer, *, shift: bool = True,
               min_gain_abs: float = 0.50,
               min_gain_frac: float = 0.10,
               hour_value=None) -> SlotDeal | None:
    """Nash bargaining over the slot outcome space, in dollars.

    The disagreement point is one consistent no-deal EVENT for both
    sides: the buyer books their best static alternative off the LIST
    board (self-shifting at their own disutility if their slot is full),
    or takes the outside option, or walks. So:
        d_buyer = max(list-board surplus, outside surplus, 0)
        d_venue = (1-p_noshow) * list margin − value(fallback span)
                  if the fallback books here, else 0.

    Span pricing (the post-registration relief fix, CRITICAL-ANALYSIS §3):
      * fallback BOOKS — the deal only swaps which span the buyer
        occupies, so both spans are priced at `hour_value` — the arm's
        learned, realized MARGINAL slot value per hour in ITS OWN regime
        (sold-out-gated realized margin per unit-tick; warmup_hour_value
        until history exists). relief = value(fallback span) − value(deal
        span): freed peak ticks credit the realized nego-regime margin
        per freed slot (nonzero only where the hour actually binds), and
        the shoulder ticks the shifted booking occupies are charged on
        the same learned basis. The old static shadow priced the credit
        at list margin against a demand forecast and the shoulder at
        zero — the H-S2 defect.
      * fallback does NOT book — the deal is ADDED occupancy, and keeps
        the conservative static displacement shadow as its guard against
        selling congested slot-time to sub-list lookers (unchanged).
    A buyer who would have paid list gets a discount only out of newly
    created surplus (genuinely freed capacity, willingness to trim) —
    never out of margin the venue already had, and the min-gain buffer
    keeps estimation noise from leaking margin."""
    v = state.venue
    show = 1.0 - v.noshow_prob
    if hour_value is None:
        def hour_value(h, _v=v):
            return warmup_hour_value(_v, h)

    b_start, b_n, b_price, b_sur = best_board_booking(state, cust, list_mult)
    d_b = max(b_sur if b_start is not None else 0.0, cust.outside, 0.0)
    fallback_books = (b_start is not None and b_sur > 0
                      and b_sur >= cust.outside)
    if fallback_books:
        d_shadow = _span_value(v, b_start, b_n * v.step_ticks, hour_value)
        d_v = show * (b_price - v.unit_cost(b_n, cust.kind)) - d_shadow
    else:
        d_shadow, d_v = 0.0, 0.0

    shifts = v.shift_choices if shift else (0,)
    best, best_score = None, None
    for n in _dur_candidates(cust.n_req):
        dur = n * v.step_ticks
        L = v.list_price(n, cust.kind)
        cost = v.unit_cost(n, cust.kind)
        rungs = [round(p, 2) for p in np.linspace(cost, L, C.PRICE_RUNGS)]
        for s in shifts:
            start = cust.desired + s
            if start < state.tick or not can_book(state, start, dur):
                continue
            if fallback_books:
                sh = _span_value(v, start, dur, hour_value)
            else:
                sh = capacity_shadow(state, start, dur)
            move = cust.shift_cost(start)
            val = cust.value(n)
            for p in rungs:
                gs = show * (p - cost) - sh - d_v
                gb = val - p - move - d_b
                if gs >= -1e-9 and gb >= -1e-9:
                    score = (gs * gb, gs + gb)
                    if best_score is None or score > best_score:
                        best = (start, n, p, cost, L, sh, move, val)
                        best_score = score
    if best is None or (best_score[0] <= 0 and best_score[1] <= 1e-9):
        return None                    # nothing improves on no-deal

    start, n, p, cost, L, sh, move, val = best
    u_v = show * (p - cost) - sh
    if u_v - d_v < max(min_gain_abs, min_gain_frac * L):
        return None                    # gains too thin to bother quoting
    u_b = val - p - move
    relief = d_shadow - sh
    why = ["negotiated slot"]
    if start != cust.desired:
        why.append(f"{(start - cust.desired) * 10:+d}-min shift"
                   + (" frees peak capacity" if relief > 1e-9 else ""))
    if n < cust.n_req:
        why.append(f"trimmed to {n} of {cust.n_req} steps")
    why.append(f"${L - p:.2f} under list" if p < L - 1e-9 else "at list")
    return SlotDeal(start=start, n=n, price=p, cost=cost, list_price=L,
                    u_venue=u_v, d_venue=d_v, u_buyer=u_b, d_buyer=d_b,
                    relief=relief, shifted=start != cust.desired,
                    trimmed=n < cust.n_req, cs=u_b, why=tuple(why))


ARMS = {
    "static": StaticPolicy,
    "computed": ComputedPolicy,
    "nego": NegoPolicy,
    "nego-noshift": lambda: NegoPolicy(policy_id="nego-noshift/1", shift=False),
}

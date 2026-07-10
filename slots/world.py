"""SLOT-ECONOMICS world core: ONE engine, three venue calibrations.

A venue is `capacity` interchangeable units (chairs / spaces / seats)
crossed with a day of 10-minute ticks. THE inventory is time: a unit-tick
that goes unsold perishes worthless at the end of the tick — nothing
carries overnight. A customer arrives with a desired start slot, a
duration budget in venue steps (cuts / hours / drinks), a lognormal WTP,
and a flexibility type. Barber and parking requests are reservations that
no-show with a venue probability; bar customers are walk-ins.

Honesty notes (the modeling choices reviewers should attack):
  * The static baseline is STRONG: each venue's WTP ratio scale R is
    INVERTED from its list price, so list IS the profit-optimal posted
    multiplier for the arrival-weighted all-day crowd — a competent
    operator, not a strawman. Dynamic arms may only ever discount.
    The inversion treats the buyer as all-or-nothing at their requested
    duration; because trimming (gamma < 1 segments) makes true demand a
    shade more elastic below list, the true optimum sits slightly below
    our sticker — an error that FAVORS the discounting arms, and one the
    computed-vs-static delta in the sigma=0 cells bounds empirically.
  * WTP = one lognormal ratio x the list value of the requested booking
    (per-venue sigma, hour multiplier keyed on the DESIRED slot's hour).
    Trimmed durations are valued V(n) = WTP * (n/n_req)^gamma: concave for
    divisible services, convex for indivisible needs — which is what stops
    the Nash engine from "winning" by selling commuters half a work day.
  * Bookings are intervals; capacity is checked per tick. Interval graphs
    are perfect (clique number = chromatic number), so "every tick has a
    free unit" is exactly "an actual chair/space/seat assignment exists".
  * The demand forecast D-hat (computed/1's run-out hold and nego/1's
    capacity shadow both use it) is the TRUE structural process — rates x
    segment mix x list-price conversion with duration choice marginalized
    over the WTP distribution — WITHOUT the day shock. The operator knows
    the market's shape, not today's luck. Equally favorable to both
    dynamic arms; flagged in results.json config.
  * A no-show pays nothing (no deposit) and releases its span at start
    time. Buyer-side no-show risk cancels across the buyer's own
    alternatives, so buyer utilities are conditional-on-show; venue
    margins carry (1 - p_noshow).
  * The outside option (competitor at 1.1 x list + hassle) has infinite
    capacity and no wait — an overflow absorber, favorable to no arm.
"""
from __future__ import annotations

import functools
import hashlib
import math
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np

from slots import calibration as C


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


def _sf(x: float, scale: float, sigma: float) -> float:
    """Lognormal survival, closed form (copied from boba.world — cheap
    enough for import-time expectations without scipy in every call)."""
    if x <= 0:
        return 1.0
    return 0.5 * math.erfc((math.log(x / scale)) / (sigma * math.sqrt(2)))


_NORM = NormalDist()
PEAK_THRESHOLD = 0.85       # hour is structurally congested when expected
                            # list demand ≥ 85% of its unit-tick capacity


# ── config & day shocks ──────────────────────────────────────────────────
@dataclass(frozen=True)
class SlotConfig:
    sigma_shock: float = 0.0        # day-level arrival shock (lognormal)
    flexible_share: float = 0.30    # share of shift-flexible customers


DEFAULT_CONFIG = SlotConfig()


@functools.lru_cache(maxsize=8192)
def day_rate_mult(venue_name: str, sigma: float, master_seed: int,
                  day: int) -> float:
    """Mean-one lognormal demand shock: E[e^X] = 1 with mu = -sigma^2/2,
    so average demand is unchanged across configs — arms are compared on
    adaptation, not scale."""
    if sigma <= 0:
        return 1.0
    rng = np.random.default_rng(substream(master_seed, "shock", venue_name, day))
    return float(rng.lognormal(-sigma ** 2 / 2, sigma))


# ── the venue ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Segment:
    name: str
    n_choices: tuple
    n_weights: tuple
    lead_max: int
    gamma: float
    sigma: float                # per-segment WTP-ratio spread (CALIBRATION-
                                # TARGETS §4 priority #8: elasticity is
                                # STRUCTURAL — a tight sigma means little
                                # WTP mass near the margin, hence a
                                # discount converts few who would not have
                                # paid list. Was a single venue-wide
                                # constant; segments (e.g. parking's
                                # commuter vs errand) now carry their own.


@dataclass
class Venue:
    """One venue: raw calibration plus derived market structure. Built
    once per process by `venue(name)`; treated as immutable thereafter."""
    name: str
    open_hour: int
    close_hour: int
    capacity: int
    step_ticks: int
    noshow_prob: float
    sigma: float
    rate: dict
    wtp_mult: dict
    kinds: dict                     # kind -> (per-step list, cost, share)
    segments: dict                  # name -> Segment
    seg_weights: dict               # hour -> {segment: weight}
    shift_choices: tuple
    window: int
    flex_cost: float
    rigid_cost: float
    hassle: tuple
    # day-of-week calendar structure (CALIBRATION-TARGETS §4 priority #7,
    # the bar weekend curve): dow_rate_mult and dow_wtp_mult are each an
    # EXTRA per-(day, hour) multiplier layered on top of the hourly
    # rate/wtp_mult profile (missing day or hour defaults to 1.0, so
    # barber and parking — empty dicts — are byte-unaffected). Rate needs
    # its OWN per-hour shape, not a flat per-day scalar: the bar's peak
    # hours (19-22h) are already capacity-saturated on an ordinary
    # weekday, so a uniform Saturday rate bump mostly turns AWAY the extra
    # demand rather than converting it — the real "Sat >25% of weekly
    # sales" story is Saturday's OTHERWISE-QUIET 15:00-18:00 becoming
    # genuinely busy (slack capacity to actually absorb), not a bigger
    # crowd fighting over the same already-full peak.
    # Known calendar structure, like vend's `dow` flag — NOT a random day
    # shock (day_rate_mult already models that): the operator knows the
    # week's shape and still posts ONE sticker all week (static does not
    # reprice by weekday). The import-time mixture (ratio_appeal, D-hat,
    # mstar) blends across all 7 days weighted by their own dow_rate_mult
    # — "the profit-optimal all-WEEK posted price" — but the blend is a
    # per-tick average across the week, not a per-day-of-week forecast:
    # computed/1 and nego/1's D-hat is calendar-coarse (an honestly flagged
    # simplification, symmetric across both dynamic arms). mstar is the
    # one exception — it IS keyed by (day%7, hour), so computed/1 reprices
    # Saturday's true peak correctly.
    dow_rate_mult: dict = field(default_factory=dict)   # day%7 -> {hour: mult}
    dow_wtp_mult: dict = field(default_factory=dict)   # day%7 -> {hour: mult}
    # derived (filled by venue())
    ticks: int = 0
    hours: tuple = ()
    ratio_appeal: float = 1.0
    cost_ratio: float = 0.0
    peak_hours: tuple = ()
    mean_margin_per_tick: float = 0.0
    suffix_demand: np.ndarray | None = None   # (ticks+1, n_hours) unit-ticks
    mstar: dict = field(default_factory=dict)  # (day%7, hour) -> computed/1 mult

    def hour_of(self, tick: int) -> int:
        return self.open_hour + tick // 6

    def hidx(self, hour: int) -> int:
        return hour - self.open_hour

    def dow_rate_at(self, day: int, hour: int) -> float:
        return self.dow_rate_mult.get(day % 7, {}).get(hour, 1.0)

    def dow_wtp_at(self, day: int, hour: int) -> float:
        return self.dow_wtp_mult.get(day % 7, {}).get(hour, 1.0)

    def rate_at(self, tick: int, day: int = 0) -> float:
        hour = self.hour_of(tick)
        return self.rate[hour] / 6.0 * self.dow_rate_at(day, hour)

    def max_steps_from(self, start: int) -> int:
        return (self.ticks - start) // self.step_ticks

    def list_price(self, n: int, kind: str) -> float:
        """The posted list for an n-step booking. Parking is the classic
        NYC ratchet (first hour, additional hours, day max); barber and
        bar are linear per step."""
        if self.name == "parking":
            return round(min(C.PARKING_FIRST_HOUR
                             + C.PARKING_ADDL_HOUR * (n - 1),
                             C.PARKING_DAY_MAX), 2)
        return round(n * self.kinds[kind][0], 2)

    def unit_cost(self, n: int, kind: str) -> float:
        if self.name == "parking":
            return round(n * C.PARKING_COST_PER_HOUR, 2)
        return round(n * self.kinds[kind][1], 2)


# ── customers ────────────────────────────────────────────────────────────
@dataclass
class Customer:
    uid: int
    seg: str
    kind: str
    desired: int                # desired start tick
    n_req: int                  # duration budget, in venue steps
    gamma: float
    wtp: float                  # $ value of the FULL requested booking
    flexible: bool
    shift_cost_per_tick: float
    hassle: float
    outside: float              # surplus at the competitor (list x 1.1)

    def value(self, n: int) -> float:
        """Dollar value of an n-step booking, n ≤ n_req: the gamma curve.
        THE one valuation behind the board chooser, the Nash engine's
        buyer utilities, and the runner's surplus accounting."""
        return self.wtp * (n / self.n_req) ** self.gamma

    def shift_cost(self, start: int) -> float:
        return self.shift_cost_per_tick * abs(start - self.desired)


def sample_customer(venue: Venue, master_seed: int, day: int, tick: int,
                    k: int, cfg: SlotConfig = DEFAULT_CONFIG) -> Customer | None:
    """Paired across arms: depends only on (venue, master, day, tick, k,
    cfg) — never on anything a policy did. Draws are taken in a fixed
    order so the stream is stable. Returns None when the request cannot
    fit before close (counted as a lost arrival)."""
    rng = np.random.default_rng(substream(master_seed, "cust", venue.name,
                                          day, tick, k))
    hour = venue.hour_of(tick)
    # segment
    segs = venue.seg_weights[hour]
    roll, acc, seg_name = rng.random(), 0.0, next(iter(segs))
    for s, w in segs.items():
        acc += w
        if roll < acc:
            seg_name = s
            break
    seg = venue.segments[seg_name]
    # kind
    roll, acc, kind = rng.random(), 0.0, next(iter(venue.kinds))
    for kd, (_, _, share) in venue.kinds.items():
        acc += share
        if roll < acc:
            kind = kd
            break
    # duration budget & desired slot
    n_req = int(rng.choice(seg.n_choices, p=seg.n_weights))
    lead = int(rng.integers(0, seg.lead_max + 1))
    desired = min(tick + lead, venue.ticks - 1)
    n_req = min(n_req, venue.max_steps_from(desired))
    # WTP ratio: lognormal around the venue appeal x the SLOT hour's mult x
    # the SLOT day-of-week's extra mult, spread by the segment's OWN sigma
    # (CALIBRATION-TARGETS §4 #8: elasticity is structural, per segment)
    eps = float(rng.lognormal(0.0, seg.sigma))
    flexible = bool(rng.random() < cfg.flexible_share)
    hassle = float(rng.uniform(*venue.hassle))
    if n_req < 1:
        return None                 # cannot fit before close: lost arrival
    slot_hour = venue.hour_of(desired)
    dow_mult = venue.dow_wtp_at(day, slot_hour)
    ratio = venue.ratio_appeal * venue.wtp_mult[slot_hour] * dow_mult * eps
    L = venue.list_price(n_req, kind)
    wtp = ratio * L
    outside = max(0.0, wtp - C.OUTSIDE_MARKUP * L - hassle)
    return Customer(
        uid=substream(master_seed, "uid", venue.name, day, tick, k),
        seg=seg_name, kind=kind, desired=desired, n_req=n_req,
        gamma=seg.gamma, wtp=wtp, flexible=flexible,
        shift_cost_per_tick=venue.flex_cost if flexible else venue.rigid_cost,
        hassle=hassle, outside=outside)


def arrivals_at(venue: Venue, master_seed: int, day: int, tick: int,
                cfg: SlotConfig = DEFAULT_CONFIG) -> int:
    """Poisson arrivals this tick — paired across arms by construction."""
    rng = np.random.default_rng(substream(master_seed, "arr", venue.name,
                                          day, tick))
    rate = venue.rate_at(tick, day) * day_rate_mult(venue.name, cfg.sigma_shock,
                                                     master_seed, day)
    return int(rng.poisson(rate))


# ── venue state: the occupancy grid + pending reservations ──────────────
@dataclass
class Booking:
    uid: int
    start: int
    dur: int                    # ticks
    price: float
    cost: float
    cs: float                   # buyer surplus, banked at show time


@dataclass
class VenueState:
    venue: Venue
    day: int = 0
    tick: int = 0
    occupied: np.ndarray | None = None      # per-tick unit count
    pending: list = field(default_factory=list)


def fresh_day(venue: Venue, day: int = 0) -> VenueState:
    return VenueState(venue=venue, day=day, tick=0,
                      occupied=np.zeros(venue.ticks, dtype=np.int64))


def can_book(state: VenueState, start: int, dur: int) -> bool:
    v = state.venue
    if start < state.tick or dur < 1 or start + dur > v.ticks:
        return False
    return bool((state.occupied[start:start + dur] < v.capacity).all())


def occupy(state: VenueState, start: int, dur: int) -> None:
    """Claim one unit for [start, start+dur). Validates BEFORE mutating
    (the vend take() contract): a failed occupy never leaves the grid
    partially incremented."""
    if not can_book(state, start, dur):
        raise ValueError(f"cannot book [{start}, {start + dur}) — full or past")
    state.occupied[start:start + dur] += 1


def release(state: VenueState, start: int, dur: int) -> None:
    """A no-show hands its span back: the remaining slot-time can be
    resold to later arrivals; whatever is not resold perishes."""
    if (state.occupied[start:start + dur] < 1).any():
        raise ValueError("releasing capacity that was never occupied")
    state.occupied[start:start + dur] -= 1


def noshow_roll(venue: Venue, master_seed: int, day: int, uid: int) -> bool:
    """No-show identity is a property of the PERSON-day (uid-keyed):
    stable across arms and across whatever slot a policy booked them into
    — an arm cannot dodge a flake by shifting them."""
    if venue.noshow_prob <= 0:
        return False
    rng = np.random.default_rng(substream(master_seed, "noshow", venue.name,
                                          day, uid))
    return bool(rng.random() < venue.noshow_prob)


# ── demand forecast, congestion map, capacity shadow ─────────────────────
def expected_demand(venue: Venue, from_tick: int, hour: int) -> float:
    """D-hat: expected unit-ticks of list-price demand landing in `hour`
    from arrivals at tick ≥ from_tick. A forecast (true structural
    process, no day shock), used by computed/1's run-out hold and nego/1's
    shadow — never by accounting."""
    return float(venue.suffix_demand[min(from_tick, venue.ticks),
                                     venue.hidx(hour)])


def free_unit_ticks(state: VenueState, hour: int) -> float:
    """Unit-ticks of `hour` still open for sale, from the current tick."""
    v = state.venue
    t0 = max(state.tick, v.hidx(hour) * 6)
    t1 = min(v.ticks, (v.hidx(hour) + 1) * 6)
    if t0 >= t1:
        return 0.0
    return float((v.capacity - state.occupied[t0:t1]).sum())


def capacity_shadow(state: VenueState, start: int, dur: int) -> float:
    """Opportunity cost of occupying [start, start+dur), in dollars: for
    each STRUCTURALLY CONGESTED hour the span overlaps, each unit-tick
    taken displaces an expected list sale with probability
    min(1, D-hat / free), valued at the venue's mean list margin per
    unit-tick. Zero off-peak — the boba capacity-relief pattern: the value
    of shifting someone OFF a peak slot is exactly the shadow their
    desired slot no longer eats, and 0 anywhere demand is soft. A
    first-order forecast, never marked to realized rescues."""
    v = state.venue
    total = 0.0
    for hour in v.hours:
        if hour not in v.peak_hours:
            continue
        h0, h1 = v.hidx(hour) * 6, (v.hidx(hour) + 1) * 6
        ov = min(start + dur, h1) - max(start, h0)
        if ov <= 0:
            continue
        free = free_unit_ticks(state, hour)
        if free <= 0:
            p_displace = 1.0        # the hour is already sold out
        else:
            p_displace = min(1.0, expected_demand(v, state.tick, hour) / free)
        total += ov * v.mean_margin_per_tick * p_displace
    return total


# ── the canonical board chooser ──────────────────────────────────────────
def best_board_booking(state: VenueState, cust: Customer, mult_of_hour
                       ) -> tuple[int | None, int, float, float]:
    """Utility-maximizing (start, n_steps, price, surplus) against a
    posted board: the customer considers every feasible start within
    ±window of their desired slot (paying their own shift disutility) and
    every duration ≤ their budget. Price = the START hour's posted
    multiplier x list (the 'enter between X and Y' rate-board convention).
    THE one chooser behind the walk-in decision, the nego arm's
    disagreement point, and the tests."""
    v = state.venue
    best = (None, 0, 0.0, 0.0)
    lo = max(state.tick, cust.desired - v.window)
    hi = min(cust.desired + v.window, v.ticks - v.step_ticks)
    for start in range(lo, hi + 1):
        n_max = min(cust.n_req, v.max_steps_from(start))
        if n_max < 1:
            continue
        m = mult_of_hour(v.hour_of(start))
        shift = cust.shift_cost(start)
        for n in range(1, n_max + 1):
            if not can_book(state, start, n * v.step_ticks):
                break               # longer spans from here are full too
            price = round(m * v.list_price(n, cust.kind), 2)
            s = cust.value(n) - price - shift
            if s > best[3]:
                best = (start, n, price, s)
    return best


def list_mult(_hour: int) -> float:
    """The list board: multiplier 1 everywhere (static/1's product and
    every other arm's fallback)."""
    return 1.0


# ── building a venue: inversion, forecast, congestion map ────────────────
def _eps_grid(sigma: float) -> list[float]:
    """Mid-quantile lognormal grid — a deterministic stand-in for the WTP
    distribution in import-time expectations."""
    q = C.EPS_QUANTILES
    return [math.exp(sigma * _NORM.inv_cdf((i + 0.5) / q)) for i in range(q)]


def _best_n_at_list(wtp: float, n_req: int, gamma: float, venue: Venue,
                    kind: str) -> int:
    """The board chooser's duration pick at list price, desired slot —
    used only inside the demand forecast."""
    best_n, best_s = 0, 0.0
    for n in range(1, n_req + 1):
        s = wtp * (n / n_req) ** gamma - venue.list_price(n, kind)
        if s > best_s:
            best_n, best_s = n, s
    return best_n


def _pstar_mixture(R: float, cost_ratio: float,
                   weights: np.ndarray, mults: np.ndarray,
                   sigmas: np.ndarray) -> float:
    """Profit-max posted multiplier against a weighted WTP ratio mixture —
    the competent sticker, on the ratio scale. `sigmas` is per-observation
    (CALIBRATION-TARGETS §4 #8: elasticity is structural, per segment, not
    one venue-wide spread) — a single-cell mixture (weights=[1.0]) is
    exactly the old `_pstar_single` hourly re-solve."""
    from scipy.optimize import minimize_scalar
    res = minimize_scalar(
        lambda m: -(m - cost_ratio) * float(sum(
            w * _sf(m, R * mu, sg) for w, mu, sg in zip(weights, mults, sigmas))),
        bounds=(cost_ratio + 0.01, 4.0), method="bounded")
    return float(res.x)


def _raw_venue(name: str) -> Venue:
    if name == "barber":
        return Venue(name=name, open_hour=C.BARBER_OPEN,
                     close_hour=C.BARBER_CLOSE, capacity=C.BARBER_CHAIRS,
                     step_ticks=C.BARBER_CUT_TICKS, noshow_prob=C.BARBER_NOSHOW,
                     sigma=C.BARBER_SIGMA, rate=C.BARBER_RATE,
                     wtp_mult=C.BARBER_WTP_MULT, kinds=C.BARBER_KINDS,
                     segments={k: Segment(name=k, **v)
                               for k, v in C.BARBER_SEGMENTS.items()},
                     seg_weights=C.BARBER_SEG_WEIGHTS,
                     shift_choices=C.BARBER_SHIFT_CHOICES,
                     window=C.BARBER_WINDOW, flex_cost=C.BARBER_FLEX_COST,
                     rigid_cost=C.BARBER_RIGID_COST, hassle=C.BARBER_HASSLE)
    if name == "parking":
        return Venue(name=name, open_hour=C.PARKING_OPEN,
                     close_hour=C.PARKING_CLOSE, capacity=C.PARKING_SPACES,
                     step_ticks=C.PARKING_STEP_TICKS,
                     noshow_prob=C.PARKING_NOSHOW, sigma=C.PARKING_SIGMA,
                     rate=C.PARKING_RATE, wtp_mult=C.PARKING_WTP_MULT,
                     kinds=C.PARKING_KINDS,
                     segments={k: Segment(name=k, **v)
                               for k, v in C.PARKING_SEGMENTS.items()},
                     seg_weights=C.PARKING_SEG_WEIGHTS,
                     shift_choices=C.PARKING_SHIFT_CHOICES,
                     window=C.PARKING_WINDOW, flex_cost=C.PARKING_FLEX_COST,
                     rigid_cost=C.PARKING_RIGID_COST, hassle=C.PARKING_HASSLE)
    if name == "bar":
        return Venue(name=name, open_hour=C.BAR_OPEN, close_hour=C.BAR_CLOSE,
                     capacity=C.BAR_SEATS, step_ticks=C.BAR_DRINK_TICKS,
                     noshow_prob=C.BAR_NOSHOW, sigma=C.BAR_SIGMA,
                     rate=C.BAR_RATE, wtp_mult=C.BAR_WTP_MULT,
                     kinds=C.BAR_KINDS,
                     segments={k: Segment(name=k, **v)
                               for k, v in C.BAR_SEGMENTS.items()},
                     seg_weights=C.BAR_SEG_WEIGHTS,
                     shift_choices=C.BAR_SHIFT_CHOICES, window=C.BAR_WINDOW,
                     flex_cost=C.BAR_FLEX_COST, rigid_cost=C.BAR_RIGID_COST,
                     hassle=C.BAR_HASSLE,
                     dow_rate_mult=C.BAR_DOW_RATE_MULT,
                     dow_wtp_mult=C.BAR_DOW_WTP_MULT)
    raise KeyError(f"unknown venue {name!r}")


VENUE_NAMES = ("barber", "parking", "bar")


@functools.lru_cache(maxsize=None)
def venue(name: str) -> Venue:
    """Build a venue and derive its market structure:
      1. start-hour weights (arrival rates pushed through lead times),
      2. ratio appeal R inverted so list is the mixture-optimal sticker,
      3. the D-hat forecast (suffix demand per hour, duration choice
         marginalized over the WTP grid), the congestion map, the mean
         list margin per unit-tick, and computed/1's per-hour multipliers.
    """
    v = _raw_venue(name)
    v.ticks = (v.close_hour - v.open_hour) * 6
    v.hours = tuple(range(v.open_hour, v.close_hour))
    n_hours = len(v.hours)
    DOW = range(7)   # the calendar blend: barber/parking have trivial dow
                     # multipliers, so this loop is a 7x-redundant no-op for
                     # them (self-cancels in every ratio); the bar's real
                     # weekend curve makes it load-bearing.

    # pass 1 — start-hour weights + arrival-weighted cost ratio (conv-free),
    # blended across the week's own calendar volume (a busier Saturday
    # naturally counts for more, via dow_rate_mult inside rate_at)
    start_w = np.zeros(n_hours)
    list_sum = cost_sum = 0.0
    kind_shares = [(kd, sh) for kd, (_, _, sh) in v.kinds.items()]
    cell_w: dict = {}    # (day, start_hour, seg_name) -> weight
    for day_idx in DOW:
        for a in range(v.ticks):
            ra = v.rate_at(a, day_idx)
            for seg_name, w_seg in v.seg_weights[v.hour_of(a)].items():
                seg = v.segments[seg_name]
                for lead in range(seg.lead_max + 1):
                    p_lead = 1.0 / (seg.lead_max + 1)
                    start = min(a + lead, v.ticks - 1)
                    start_hour = v.hour_of(start)
                    for n, p_n in zip(seg.n_choices, seg.n_weights):
                        n_eff = min(n, v.max_steps_from(start))
                        if n_eff < 1:
                            continue
                        w = ra * w_seg * p_lead * p_n
                        start_w[v.hidx(start_hour)] += w
                        key = (day_idx, start_hour, seg_name)
                        cell_w[key] = cell_w.get(key, 0.0) + w
                        for kd, sh in kind_shares:
                            list_sum += w * sh * v.list_price(n_eff, kd)
                            cost_sum += w * sh * v.unit_cost(n_eff, kd)
    v.cost_ratio = cost_sum / list_sum
    weights = np.array(list(cell_w.values()))
    weights = weights / weights.sum()
    mults = np.array([v.wtp_mult[h] * v.dow_wtp_at(d, h)
                      for d, h, _s in cell_w])
    sigmas = np.array([v.segments[s].sigma for _d, _h, s in cell_w])

    # pass 2 — invert R so the mixture-optimal multiplier is exactly 1,
    # against the per-(day, hour, segment) mixture (real elasticity
    # heterogeneity, real weekly demand shape)
    lo, hi = 0.2, 4.0
    for _ in range(28):
        mid = (lo + hi) / 2
        if _pstar_mixture(mid, v.cost_ratio, weights, mults, sigmas) < 1.0:
            lo = mid
        else:
            hi = mid
    v.ratio_appeal = (lo + hi) / 2

    # pass 3 — D-hat: expected converted unit-ticks per hour, with the
    # duration choice marginalized over the lognormal WTP grid AND blended
    # across the week (average-day forecast: known simplification, flagged
    # in the module docstring — symmetric across computed/1 and nego/1)
    eps_grid_cache: dict = {}

    def eps_grid_for(sigma: float):
        if sigma not in eps_grid_cache:
            eps_grid_cache[sigma] = _eps_grid(sigma)
        return eps_grid_cache[sigma]

    profile_cache: dict = {}

    def profile(mult: float, n_req: int, kind: str, gamma: float,
               sigma: float):
        """P(buys ≥ j steps at list) for j = 1..n_req, plus expected list
        margin per arrival — the board chooser run over the WTP grid, at
        one (day, hour)'s resolved multiplier and the segment's sigma."""
        key = (mult, n_req, kind, gamma, sigma)
        if key not in profile_cache:
            p_ge = np.zeros(n_req)
            e_margin = 0.0
            eps_grid = eps_grid_for(sigma)
            scale = v.ratio_appeal * mult
            for eps in eps_grid:
                wtp = scale * eps * v.list_price(n_req, kind)
                n_star = _best_n_at_list(wtp, n_req, gamma, v, kind)
                if n_star >= 1:
                    p_ge[:n_star] += 1.0 / len(eps_grid)
                    e_margin += (v.list_price(n_star, kind)
                                 - v.unit_cost(n_star, kind)) / len(eps_grid)
            profile_cache[key] = (p_ge, e_margin)
        return profile_cache[key]

    contrib = np.zeros((v.ticks, n_hours))   # SUM over 7 days of rate-
                                             # weighted unit-ticks; /7'd below
    margin_sum = tick_sum = 0.0
    for day_idx in DOW:
        for a in range(v.ticks):
            ra = v.rate_at(a, day_idx)
            for seg_name, w_seg in v.seg_weights[v.hour_of(a)].items():
                seg = v.segments[seg_name]
                for lead in range(seg.lead_max + 1):
                    p_lead = 1.0 / (seg.lead_max + 1)
                    start = min(a + lead, v.ticks - 1)
                    start_hour = v.hour_of(start)
                    mult = v.wtp_mult[start_hour] * v.dow_wtp_at(day_idx, start_hour)
                    for n, p_n in zip(seg.n_choices, seg.n_weights):
                        n_eff = min(n, v.max_steps_from(start))
                        if n_eff < 1:
                            continue
                        for kd, sh in kind_shares:
                            w = w_seg * p_lead * p_n * sh
                            p_ge, e_margin = profile(mult, n_eff, kd,
                                                     seg.gamma, seg.sigma)
                            margin_sum += ra * w * e_margin
                            for j in range(n_eff):   # step j+1 of the span
                                t0 = start + j * v.step_ticks
                                t1 = min(t0 + v.step_ticks, v.ticks)
                                tick_sum += ra * w * p_ge[j] * (t1 - t0)
                                for h in range(v.hidx(v.hour_of(t0)),
                                               v.hidx(v.hour_of(max(t0, t1 - 1))) + 1):
                                    h0, h1 = h * 6, (h + 1) * 6
                                    ov = min(t1, h1) - max(t0, h0)
                                    if ov > 0:
                                        contrib[a, h] += ra * w * p_ge[j] * ov
    contrib /= 7.0
    margin_sum /= 7.0
    tick_sum /= 7.0
    suffix = np.zeros((v.ticks + 1, n_hours))
    suffix[:-1] = contrib[::-1].cumsum(axis=0)[::-1]
    v.suffix_demand = suffix
    v.mean_margin_per_tick = margin_sum / tick_sum
    v.peak_hours = tuple(
        h for h in v.hours
        if suffix[0, v.hidx(h)] >= PEAK_THRESHOLD * v.capacity * 6)

    # pass 4 — computed/1's per-(day, hour) multipliers (state-independent
    # part): a real mixture over that hour's segment mix (its own sigmas),
    # at that day-of-week's resolved WTP multiplier — so computed/1 reprices
    # Saturday's true peak correctly, not a calendar-blind average.
    v.mstar = {}
    for day_idx in DOW:
        for h in v.hours:
            seg_mix = [(w_seg, v.segments[sn].sigma)
                      for sn, w_seg in v.seg_weights[h].items()]
            hour_weights = np.array([w for w, _ in seg_mix])
            hour_sigmas = np.array([sg for _, sg in seg_mix])
            mult = v.wtp_mult[h] * v.dow_wtp_at(day_idx, h)
            m = _pstar_mixture(v.ratio_appeal, v.cost_ratio, hour_weights,
                               np.full(len(seg_mix), mult), hour_sigmas)
            v.mstar[(day_idx, h)] = min(1.0, max(v.cost_ratio, m))
    return v


def congestion_ratio(v: Venue) -> float:
    """Peak demand pressure: max over hours of D-hat(from open) over the
    hour's unit-tick capacity — the H-S1 asymmetry metric, reported in
    results.json so the venue ladder is checkable."""
    return float(max(v.suffix_demand[0, v.hidx(h)] / (v.capacity * 6)
                     for h in v.hours))

"""SLOT-ECONOMICS tests: pairing is real, determinism holds, discount-only
is enforced, slot-time is conserved, no-shows are accounted, and the nego
arm's edges come from the right drivers (peak shadows, slot shifts)."""
import numpy as np
import pytest

from slots import calibration as C
from slots.world import (DEFAULT_CONFIG, Customer, SlotConfig,
                         arrivals_at, best_board_booking, can_book,
                         capacity_shadow, congestion_ratio, day_rate_mult,
                         expected_demand, fresh_day, free_unit_ticks,
                         list_mult, noshow_roll, occupy, release,
                         sample_customer, substream, venue)


def _customer(v, ratio=1.4, desired=None, n_req=None, kind=None,
              flexible=True, gamma=0.7, seg="hand"):
    """A hand-built buyer: values the requested booking at ratio x list —
    deals exist wherever the engine allows them."""
    kind = kind or next(iter(v.kinds))
    n_req = n_req or 1
    desired = 12 if desired is None else desired
    L = v.list_price(n_req, kind)
    return Customer(uid=7, seg=seg, kind=kind, desired=desired, n_req=n_req,
                    gamma=gamma, wtp=ratio * L, flexible=flexible,
                    shift_cost_per_tick=v.flex_cost if flexible else v.rigid_cost,
                    hassle=3.0, outside=max(0.0, ratio * L - 1.1 * L - 3.0))


# ── pairing & determinism ────────────────────────────────────────────────

def test_arrival_and_customer_streams_are_policy_independent():
    """The treatment isolation guarantee: streams depend only on
    (venue, seed, day, tick, k, cfg)."""
    v = venue("bar")
    assert [arrivals_at(v, 7, 3, t) for t in range(v.ticks)] == \
           [arrivals_at(v, 7, 3, t) for t in range(v.ticks)]
    c1 = sample_customer(v, 7, 3, 30, 0)
    c2 = sample_customer(v, 7, 3, 30, 0)
    assert (c1.uid, c1.seg, c1.kind, c1.desired, c1.n_req, c1.wtp,
            c1.flexible) == \
           (c2.uid, c2.seg, c2.kind, c2.desired, c2.n_req, c2.wtp,
            c2.flexible)
    c3 = sample_customer(v, 7, 3, 30, 1)
    assert c3.uid != c1.uid


def test_day_shock_is_mean_one_and_deterministic():
    mults = [day_rate_mult("parking", 0.4, 42, d) for d in range(4000)]
    assert mults[7] == day_rate_mult("parking", 0.4, 42, 7)
    assert abs(np.mean(mults) - 1.0) < 0.03
    assert day_rate_mult("parking", 0.0, 42, 7) == 1.0


def test_noshow_roll_is_person_stable_and_policy_independent():
    """No-show identity keys on (venue, day, uid) — same person, same
    flake, whatever slot an arm booked them into."""
    v = venue("barber")
    rolls = [noshow_roll(v, 11, 2, 12345) for _ in range(5)]
    assert all(r == rolls[0] for r in rolls)
    assert noshow_roll(venue("bar"), 11, 2, 12345) is False   # walk-ins


# ── calibration & pricing ────────────────────────────────────────────────

def test_parking_list_formula_ratchets_and_caps():
    v = venue("parking")
    assert v.list_price(1, "car") == 18.0
    assert v.list_price(2, "car") == 26.0
    assert v.list_price(4, "car") == 42.0
    assert v.list_price(5, "car") == 45.0      # the day max binds
    assert v.list_price(10, "car") == 45.0


def test_asymmetry_ladder_is_as_engineered():
    """H-S1's premise, checked not asserted: peak congestion pressure
    orders parking > bar > barber."""
    ratios = {n: congestion_ratio(venue(n)) for n in ("barber", "parking", "bar")}
    assert ratios["parking"] > ratios["bar"] > ratios["barber"] > 1.0


def test_static_list_is_mixture_optimal():
    """The inversion worked: computed/1's per-(day, hour) re-solve never
    finds a multiplier above 1, and holds ~at list in the hottest
    (day, hour) cell — a competent sticker, not a strawman. mstar is keyed
    by (day%7, hour) since the bar's weekend curve makes the peak
    calendar-dependent (barber/parking are calendar-flat, so every day
    gives the same hot hour)."""
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        assert all(m <= 1.0 + 1e-9 for m in v.mstar.values())
        assert all(m >= v.cost_ratio - 1e-9 for m in v.mstar.values())
        hot = max(v.mstar, key=lambda dh: v.wtp_mult[dh[1]] * v.dow_wtp_at(dh[0], dh[1]))
        assert v.mstar[hot] > 0.99


# ── CALIBRATION-TARGETS §4 recalibration (2026-07-10, #7 + #8) ───────────

def test_barber_utilization_matches_platform_average():
    """Priority #8: Squire/Zenoti platform-measured schedule utilization
    averages 62% (top quartile 73-84%); the pre-recalibration sim realized
    45-49% — a below-average shop. The static arm should now land in the
    62%-average band, not the old below-average one."""
    from slots.policies import ARMS
    from slots.run import run_experiment
    res = run_experiment(["static"], "barber", days=30, seed=20260710)
    assert 0.55 <= res["arms"]["static"]["totals"]["occupancy"] <= 0.68


def test_deposit_regime_noshow_rate():
    """Priority #8: no-show is now an explicit REGIME — platform shops
    with deposits run 3-5% (we take 4%), no-deposit shops 12-25% (we keep
    12% as a conservative-low no-deposit case). BARBER_NOSHOW (the venue
    default) is the deposit cell and must equal the labeled 4% exactly;
    the REALIZED rate in play is close to but a bit below the input
    probability (barber's 0-lead walk-ins settle immediately and can
    never no-show, diluting the realized rate — an honest artifact of the
    booking-lead distribution, not a miscalibration)."""
    from slots.policies import ARMS
    from slots.run import run_day
    assert C.BARBER_NOSHOW_REGIMES["deposit"] == pytest.approx(0.04)
    assert C.BARBER_NOSHOW_REGIMES["nodeposit"] == pytest.approx(0.12)
    assert C.BARBER_NOSHOW == pytest.approx(C.BARBER_NOSHOW_REGIMES["deposit"])
    bookings = noshows = 0
    for d in range(30):
        m = run_day(ARMS["static"](), "barber", 20260710, d)
        bookings += m["bookings"]
        noshows += m["noshows"]
    assert 0.02 <= noshows / bookings <= 0.06


def test_parking_commuter_is_least_elastic():
    """Priority #8: Lehner-Peer 2019 — commuters are the LEAST
    price-elastic parking segment. Elasticity here is STRUCTURAL (each
    segment carries its own sigma), so a tight commuter WTP spread should
    show LESS conversion-rate sensitivity to a price cut than the more
    dispersed errand segment does, checked at the 7-9am commuter-heavy
    window (CALIBRATION-TARGETS §4's explicit check)."""
    from slots.world import _sf
    v = venue("parking")
    assert v.segments["commuter"].sigma < v.segments["event"].sigma < \
        v.segments["errand"].sigma
    for h in (7, 8):
        mult = v.wtp_mult[h]
        scale = v.ratio_appeal * mult

        def elasticity(sigma):
            p0 = _sf(1.0, scale, sigma)
            p1 = _sf(0.9, scale, sigma)
            return (p1 - p0) / p0 / -0.1

        e_commuter = elasticity(v.segments["commuter"].sigma)
        e_errand = elasticity(v.segments["errand"].sigma)
        # both are negative (a price cut raises conversion); "least
        # elastic" means smallest MAGNITUDE, i.e. closest to zero
        assert abs(e_commuter) < abs(e_errand)


def test_bar_saturday_revenue_share():
    """Priority #7: Nielsen CGA — Saturday alone is >25% of weekly bar
    sales, Fri+Sat run 40-50%. Measured over a WHOLE-WEEK window (35 days
    = 5 full weeks): a 30-day window over-represents Monday/Tuesday by one
    extra occurrence each and understates Saturday's true share, so this
    check — unlike the grid's 30-day cells — uses a multiple of 7."""
    from slots.policies import ARMS
    from slots.run import run_day
    import collections
    rev = collections.defaultdict(float)
    for d in range(35):
        m = run_day(ARMS["static"](), "bar", 20260710, d)
        rev[d % 7] += m["revenue"]
    total = sum(rev.values())
    sat_share = rev[5] / total
    fri_sat_share = (rev[4] + rev[5]) / total
    assert sat_share > 0.22
    assert 0.35 <= fri_sat_share <= 0.55


def test_bar_anchor_at_least_peak_hour_wtp_implied_price():
    """The coupled peak-anchor fix: BAR_BEER/BAR_COCKTAIL were a FLAT
    list while BAR_WTP_MULT rose above 1 at peak, so discount-only arms
    could never charge the peak crowd what it would bear. The anchor is
    now the peak crowd's own profit-optimal price (raised from the old
    flat $9/$16), and WTP_MULT is re-based so the combined (day, hour)
    multiplier tops out at EXACTLY 1.0 at the true peak and never exceeds
    it anywhere — the discount-only ceiling is never binding-by-construction
    above what the peak crowd's own WTP implies."""
    v = venue("bar")
    combined = {(d, h): v.wtp_mult[h] * v.dow_wtp_at(d, h)
               for d in range(7) for h in v.hours}
    peak_val = max(combined.values())
    assert peak_val == pytest.approx(1.0, abs=2e-3)   # hand-rounded 4dp constants
    assert all(m <= 1.0 + 2e-3 for m in combined.values())
    assert C.BAR_COCKTAIL[0] > 16.0    # anchor raised above the old flat list
    assert C.BAR_BEER[0] > 9.0


# ── occupancy grid physics ───────────────────────────────────────────────

def test_occupy_validates_before_mutating():
    v = venue("barber")
    state = fresh_day(v)
    occupy(state, 10, 5)
    occupy(state, 10, 5)              # two chairs: fine
    with pytest.raises(ValueError):
        occupy(state, 12, 5)          # would need a third chair at 12..14
    assert int(state.occupied.max()) == 2     # nothing was over-incremented
    assert not can_book(state, 12, 5)
    assert can_book(state, 15, 5)


def test_release_makes_slot_time_resellable():
    v = venue("barber")
    state = fresh_day(v)
    occupy(state, 10, 5)
    occupy(state, 10, 5)
    release(state, 10, 5)             # a no-show hands its span back
    assert can_book(state, 10, 5)
    with pytest.raises(ValueError):
        release(state, 40, 5)         # never occupied


# ── forecast, congestion map, capacity shadow ────────────────────────────

def test_shadow_is_zero_off_peak_and_positive_at_peak():
    """The boba relief pattern: occupying soft hours costs nothing;
    occupying a structurally congested hour carries the displaced list
    margin."""
    v = venue("bar")
    state = fresh_day(v)
    peak_tick = (20 - v.open_hour) * 6            # 20:00, packed
    dead_tick = (15 - v.open_hour) * 6            # 15:00, dead
    assert capacity_shadow(state, peak_tick, 6) > 0.0
    assert capacity_shadow(state, dead_tick, 6) == 0.0
    vb = venue("barber")
    sb = fresh_day(vb)
    assert capacity_shadow(sb, (15 - vb.open_hour) * 6, 5) == 0.0


def test_shadow_never_exceeds_full_margin_of_the_span():
    """min(1, D-hat/free) caps the displacement: a freed unit-tick cannot
    rescue more than one unit-tick of list margin."""
    v = venue("parking")
    state = fresh_day(v)
    for start in (0, 18, 36, 60):
        dur = 12
        assert capacity_shadow(state, start, dur) <= \
            dur * v.mean_margin_per_tick + 1e-9


def test_expected_demand_declines_as_the_day_burns():
    v = venue("bar")
    h = 20
    d0 = expected_demand(v, 0, h)
    d_mid = expected_demand(v, 20, h)
    d_late = expected_demand(v, v.ticks - 1, h)
    assert d0 >= d_mid >= d_late >= 0.0
    assert d0 > v.capacity * 6        # 20:00 is packed by construction


# ── the canonical board chooser ──────────────────────────────────────────

def test_board_chooser_shifts_only_when_desired_is_full():
    v = venue("barber")
    state = fresh_day(v)
    cust = _customer(v, ratio=1.4, desired=12, flexible=True)
    start, n, price, s = best_board_booking(state, cust, list_mult)
    assert (start, n) == (12, 1) and price == 38.0 and s > 0
    occupy(state, 12, 5)
    occupy(state, 12, 5)              # desired slot now full
    start2, n2, _, s2 = best_board_booking(state, cust, list_mult)
    assert start2 is not None and start2 != 12    # self-shifted at list
    assert s2 < s                     # the shift disutility was paid


# ── computed/1 mechanism ─────────────────────────────────────────────────

def test_computed_holds_list_where_runout_binds_and_discounts_soft_hours():
    from slots.policies import ComputedPolicy
    v = venue("bar")
    state = fresh_day(v)
    mult = ComputedPolicy().mult_of(state)
    assert mult(20) == 1.0            # packed hour: D-hat ≥ free, hold at list
    assert mult(15) < 1.0             # dead hour: the crowd re-solve discounts
    assert mult(15) >= v.cost_ratio - 1e-9


def test_computed_board_never_above_list_anywhere():
    from slots.policies import ComputedPolicy
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        state = fresh_day(v)
        for tick in (0, v.ticks // 2, v.ticks - 6):
            state.tick = tick
            pol = ComputedPolicy()
            mult = pol.mult_of(state)
            assert all(mult(h) <= 1.0 + 1e-9 for h in v.hours)


# ── nego/1 mechanism (drivers, not outcomes) ─────────────────────────────

def _stream_deals(venue_name, days=2, seed=20260710):
    """Every accepted deal the nego arm cuts against the real customer
    stream, with the state evolving as it books."""
    from slots.policies import nego_quote
    v = venue(venue_name)
    for day in range(days):
        state = fresh_day(v, day)
        for tick in range(v.ticks):
            state.tick = tick
            for k in range(arrivals_at(v, seed, day, tick)):
                cust = sample_customer(v, seed, day, tick, k)
                if cust is None:
                    continue
                deal = nego_quote(state, cust)
                if deal is not None and deal.u_buyer >= deal.d_buyer - 1e-9:
                    occupy(state, deal.start, deal.n * v.step_ticks)
                    yield state, cust, deal


def test_nego_is_discount_only_and_never_below_cost():
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        for _, cust, deal in _stream_deals(name):
            assert deal.price <= v.list_price(deal.n, cust.kind) + 1e-9
            assert deal.price >= v.unit_cost(deal.n, cust.kind) - 1e-9


def test_nego_beats_the_customers_own_static_alternative():
    """'Never worse UX than static' is enforced in the engine: every deal
    leaves the buyer at least as well off as their best list-board
    booking (self-shift included) or the competitor."""
    for name in ("barber", "parking", "bar"):
        checked = 0
        for state, cust, deal in _stream_deals(name):
            # recompute the alternative AFTER the deal booked: the deal's
            # own span may have eaten it, so check against the recorded
            # disagreement, which the engine measured pre-booking
            assert deal.u_buyer >= deal.d_buyer - 1e-9
            assert deal.d_buyer >= cust.outside - 1e-9
            checked += 1
        assert checked > 0


def test_nego_venue_gain_clears_the_buffer():
    from slots import calibration as C
    for name in ("barber", "parking", "bar"):
        for _, cust, deal in _stream_deals(name, days=1):
            assert deal.u_venue - deal.d_venue >= \
                max(0.50, 0.10 * deal.list_price) - 1e-9


def test_relief_only_when_shifting_off_peak():
    """The capacity-relief driver: positive relief requires a fallback
    squatting on congested hours and a deal that does not — an off-peak
    desired slot can never mint relief."""
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        for state, cust, deal in _stream_deals(name, days=1):
            fallback_hours = {v.hour_of(t) for t in
                              range(cust.desired,
                                    min(cust.desired + cust.n_req * v.step_ticks,
                                        v.ticks))}
            if not (fallback_hours & set(v.peak_hours)):
                assert deal.relief <= 1e-9


def test_rigid_customers_do_not_get_shifted():
    """The flexibility type has teeth: at $4–5/tick of shift disutility, a
    rigid buyer's slot-shift never pencils, while the same buyer flexible
    does shift where the freed peak span pays for it. (n_req=1 so the
    whole span leaves the peak: since the relief fix, the old 2-drink
    scenario picks an upsell-shift whose second drink still occupies the
    same peak ticks — its relief is honestly 0, not >0.)"""
    from slots.policies import nego_quote
    v = venue("bar")
    state = fresh_day(v)
    edge = (23 - v.open_hour) * 6         # peak's trailing edge (see
    desired = edge - 3                    # _edge_shift_scenario): 22:30,
    state.tick = desired - 12             # a +30-min shift lands at 23:00
    flex = _customer(v, ratio=1.3, desired=desired, n_req=1, kind="beer",
                     flexible=True)
    rigid = _customer(v, ratio=1.3, desired=desired, n_req=1, kind="beer",
                      flexible=False)
    d_flex = nego_quote(state, flex)
    d_rigid = nego_quote(state, rigid)
    assert d_flex is not None and d_flex.shifted and d_flex.relief > 0
    assert d_rigid is None or not d_rigid.shifted


# ── the relief fix (post-registration, CRITICAL-ANALYSIS §3) ─────────────

def _learned_policy(v, peak_val, shoulder_val):
    """A nego policy whose learner has 'converged' to flat per-class slot
    values: peak hours worth peak_val $/unit-tick, every other hour
    shoulder_val — so relief arithmetic is checkable by hand. Keyed on
    (day%7, hour) since the learner is now calendar-aware; a slot is
    peak-valued on the days it is actually peak (`peak_hours_on`)."""
    from slots.policies import NegoPolicy
    pol = NegoPolicy()
    pol.learner._m = {(d, h): (peak_val if h in v.peak_hours_on(d)
                               else shoulder_val)
                      for d in range(7) for h in v.hours}
    return pol


def _hour_ticks(v, start, dur, h):
    """Unit-ticks of [start, start+dur) that land in hour h."""
    h0 = v.hidx(h) * 6
    return max(0, min(start + dur, h0 + 6) - max(start, h0))


def _expected_relief(v, pol, fb_span, deal_span, day=0):
    """The pre-registered relief formula, computed independently:
    value(fallback span) − value(deal span) at the learner's (day-of-week
    keyed) values."""
    return sum(pol.learner.value(v, day, h)
               * (_hour_ticks(v, *fb_span, h) - _hour_ticks(v, *deal_span, h))
               for h in v.hours)


def _edge_shift_scenario(v):
    """The bar-peak's TRAILING edge (calibrated-world: the weekend curve
    makes peak_hours (17..22), so the 22:00->23:00 boundary is the last
    peak/off-peak crossing reachable within one shift window — was the
    19:00 leading edge pre-calibration, when peak_hours started later): a
    flexible one-beer buyer at 22:30 whose +30-min shift moves the whole
    span off the peak into 23:00."""
    state = fresh_day(v)
    edge = (23 - v.open_hour) * 6
    desired = edge - 3          # 22:30: +30-min (+3 ticks) reaches 23:00
    state.tick = desired - 12
    cust = _customer(v, ratio=1.3, desired=desired, n_req=1, kind="beer",
                     flexible=True)
    return state, cust


def test_relief_prices_freed_peak_at_learned_regime_margin_not_list():
    """The fix's first half: the credit for a freed peak slot is the
    arm's LEARNED realized nego-regime value, not the static list margin
    the old shadow assumed. Same scenario, two learned peak values —
    relief tracks the learner exactly, and neither equals the static
    mean-list-margin basis."""
    v = venue("bar")
    for peak_val in (2.0, 4.0):
        pol = _learned_policy(v, peak_val=peak_val, shoulder_val=0.0)
        state, cust = _edge_shift_scenario(v)
        b_start, b_n, _, _ = best_board_booking(state, cust, list_mult)
        deal = pol.quote_for(state, cust)
        assert deal is not None and deal.shifted
        want = _expected_relief(v, pol, (b_start, b_n * v.step_ticks),
                                (deal.start, deal.n * v.step_ticks))
        assert deal.relief == pytest.approx(want)
        assert want == pytest.approx(peak_val * 3)      # 3 freed peak ticks
        # and NOT the static list-margin basis the defect used
        assert abs(deal.relief - v.mean_margin_per_tick * 3) > 1.0


def test_shoulder_displacement_is_charged():
    """The fix's second half: the shoulder ticks the shifted booking now
    occupies are charged at the same learned basis — relief drops by
    exactly shoulder_val x occupied shoulder ticks, and when shoulder
    slot-time earns as much as peak slot-time the swap mints nothing, so
    the engine stops paying for shifts."""
    v = venue("bar")
    free_pol = _learned_policy(v, peak_val=3.0, shoulder_val=0.0)
    state, cust = _edge_shift_scenario(v)
    d_free = free_pol.quote_for(state, cust)
    assert d_free is not None and d_free.shifted
    assert d_free.relief == pytest.approx(3.0 * 3)

    charged_pol = _learned_policy(v, peak_val=3.0, shoulder_val=1.0)
    state, cust = _edge_shift_scenario(v)
    d_charged = charged_pol.quote_for(state, cust)
    assert d_charged is not None and d_charged.shifted
    # 3 freed peak ticks credited, 3 occupied shoulder ticks charged
    assert d_charged.relief == pytest.approx(3.0 * 3 - 1.0 * 3)

    flat_pol = _learned_policy(v, peak_val=3.0, shoulder_val=3.0)
    state, cust = _edge_shift_scenario(v)
    d_flat = flat_pol.quote_for(state, cust)
    assert d_flat is None or not d_flat.shifted


def test_warmup_falls_back_to_conservative_fraction_of_list_margin():
    """Before the arm has any history of its own, the relief basis is
    RELIEF_WARMUP_FRAC (0.6) x the static mean list margin per unit-tick
    for peak hours and 0 off-peak — strictly more conservative than the
    defect's full-list-margin credit."""
    from slots.policies import (RELIEF_WARMUP_FRAC, NegoPolicy,
                                warmup_hour_value)
    v = venue("bar")
    assert RELIEF_WARMUP_FRAC == 0.6
    # warmup is calendar-aware: checked on a Monday (day 0) and a Saturday
    # (day 5), where the peak sets genuinely differ (Sat 16:00 warms up as
    # peak, Mon 16:00 does not) — the whole point of the fix
    for day in (0, 5):
        for h in v.hours:
            want = (0.6 * v.mean_margin_per_tick
                    if v.is_peak(day, h) else 0.0)
            assert warmup_hour_value(v, day, h) == pytest.approx(want)
            # a fresh learner defers to the warmup values
            assert NegoPolicy().learner.value(v, day, h) == pytest.approx(want)
    pol = NegoPolicy()                       # no history at all
    state, cust = _edge_shift_scenario(v)    # Monday, 22:00 peak edge
    deal = pol.quote_for(state, cust)
    assert deal is not None and deal.shifted
    assert deal.relief == pytest.approx(0.6 * v.mean_margin_per_tick * 3)
    assert deal.relief < v.mean_margin_per_tick * 3    # conservative


def test_learner_observes_soldout_gated_realized_margin():
    """The learned slot value is MARGINAL, not average: realized margin
    per sold unit-tick, gated by the fraction of the hour's ticks that
    ended the day at full capacity. An hour with realized sales but slack
    capacity learns toward 0 (a freed tick there enables no extra sale);
    a sold-out hour learns its realized per-tick margin; the EWMA folds
    days at alpha=0.3 (the vend DemandLearner pattern)."""
    import numpy as np
    from slots.policies import HourMarginLearner
    v = venue("bar")
    lrn = HourMarginLearner()
    occ = np.zeros(v.ticks, dtype=np.int64)
    h_full, h_slack = 20, 16
    occ[v.hidx(h_full) * 6:(v.hidx(h_full) + 1) * 6] = v.capacity   # binds
    occ[v.hidx(h_slack) * 6:(v.hidx(h_slack) + 1) * 6] = 10         # slack
    margin = {h_full: 900.0, h_slack: 90.0}
    day = 5                                  # a Saturday
    lrn.end_day(v, day, margin, occ)
    assert lrn.value(v, day, h_full) == pytest.approx(900.0 / (v.capacity * 6))
    assert lrn.value(v, day, h_slack) == pytest.approx(0.0)   # never sold out
    assert lrn.value(v, day, 15) == pytest.approx(0.0)        # no sales at all
    # EWMA: a second Saturday folds in at alpha=0.3
    first = lrn.value(v, day, h_full)
    lrn.end_day(v, day + 7, {h_full: 450.0}, occ)     # same day-of-week
    want = 0.7 * first + 0.3 * (450.0 / (v.capacity * 6))
    assert lrn.value(v, day, h_full) == pytest.approx(want)


def test_run_day_feeds_the_learner_realized_margins():
    """The runner's end-of-day feed is real: after one day the nego arm's
    learner has an estimate for every hour, its observations are bounded
    by the day's realized margin, and no-show spans contribute nothing
    (settled bookings only)."""
    from slots.policies import ARMS
    from slots.run import run_day
    pol = ARMS["nego"]()
    m = run_day(pol, "bar", 20260710, 0)     # day 0 = Monday (day%7 == 0)
    v = venue("bar")
    # one day played folds into exactly that day-of-week's (0) slot values
    assert set(pol.learner._m) == {(0, h) for h in v.hours}
    assert all(val >= 0.0 for val in pol.learner._m.values())
    # sold-out gating can only shrink an hour's observation below its
    # realized margin per capacity tick, never inflate it
    assert sum(pol.learner._m.values()) * v.capacity * 6 <= m["margin"] + 0.02


# ── calendar-aware relief (CRITICAL-ANALYSIS §3 CALIBRATED-WORLD follow-up) ─
# peak_hours and the HourMarginLearner are keyed on (day%7, hour), the same
# keying computed/1's mstar uses, so the bar's Saturday-afternoon shoulder
# slots learn their own high value instead of the week-blended one.

def test_peak_hours_are_calendar_aware():
    """The core fix: an hour's peak flag depends on the DAY-OF-WEEK. The
    bar's 16:00 and 17:00 are among the week's busiest hours on Saturday
    (day 5, the deliberate afternoon build-out) yet NOT peak on an ordinary
    weekday (day 0) — the week-blended average diluted them below threshold,
    the diagnosed calendar-blind defect. Barber and parking have no
    day-of-week structure, so their per-day peak sets are identical across
    the week (and equal to the reported union)."""
    v = venue("bar")
    # Saturday afternoon binds; the same clock hours are slack on a weekday
    assert v.is_peak(5, 16) and v.is_peak(5, 17)
    assert not v.is_peak(0, 16) and not v.is_peak(0, 17)
    # 16:00 is in the "ever peak" union but not peak every day
    assert 16 in v.peak_hours
    assert v.peak_hours_on(5) != v.peak_hours_on(0)
    # calendar-flat venues: every day-of-week gives the same peak set
    for name in ("barber", "parking"):
        vf = venue(name)
        assert all(vf.peak_hours_on(d) == vf.peak_hours_on(0) for d in range(7))
        assert set(vf.peak_hours) == set(vf.peak_hours_on(0))


def test_learner_and_warmup_are_keyed_on_day_of_week():
    """The task's explicit check: Saturday 16:00 learns a value DISTINCT
    from (and higher than) the same clock hour on a low-traffic weekday.
    Feeding one Saturday of sold-out 16:00 play folds only into Saturday's
    EWMA; a Tuesday's 16:00 (never peak, never fed) keeps its warmup value
    of 0. The learned Saturday value and the weekday value are different
    numbers for the very same hour — the whole point of the fix."""
    import numpy as np
    from slots.policies import HourMarginLearner, warmup_hour_value
    v = venue("bar")
    # warmup already differs by day-of-week (peak flag is calendar-aware)
    assert warmup_hour_value(v, 5, 16) == pytest.approx(0.6 * v.mean_margin_per_tick)
    assert warmup_hour_value(v, 1, 16) == pytest.approx(0.0)   # Tue 16:00 slack

    lrn = HourMarginLearner()
    occ = np.zeros(v.ticks, dtype=np.int64)
    occ[v.hidx(16) * 6:(v.hidx(16) + 1) * 6] = v.capacity      # 16:00 binds
    lrn.end_day(v, 5, {16: 720.0}, occ)                        # a Saturday
    sat_val = lrn.value(v, 5, 16)
    tue_val = lrn.value(v, 1, 16)     # Tuesday 16:00 — untouched, warmup 0
    assert sat_val == pytest.approx(720.0 / (v.capacity * 6))
    assert tue_val == pytest.approx(0.0)
    assert sat_val > tue_val + 1.0    # same hour, distinct value by weekday
    # and a weekday folds into its OWN slot, not Saturday's
    lrn.end_day(v, 1, {16: 360.0}, occ)
    assert lrn.value(v, 5, 16) == pytest.approx(sat_val)   # Saturday unmoved


def test_relief_credit_flows_the_calendar_aware_value():
    """Integration: the calendar-aware peak flag reaches the relief credit.
    A fresh nego arm (warmup values) offers a 16:00 buyer a −30-min shift
    that frees a Saturday-afternoon PEAK slot and mints positive relief
    (0.6 x mean list margin x the 3 freed peak ticks); the identical
    clock-hour buyer on a Monday — where 16:00 is not peak — is offered no
    peak-freeing shift, so the relief credit is 0. Pre-fix (calendar-blind)
    both days shared hour 16's week-diluted, near-zero value and the
    Saturday relief would have been mispriced to nearly nothing."""
    from slots.policies import NegoPolicy
    v = venue("bar")

    def scenario(day):
        state = fresh_day(v, day)
        state.tick = 0
        cust = _customer(v, ratio=1.35, desired=(16 - v.open_hour) * 6,
                         n_req=1, kind="beer", flexible=True)
        return NegoPolicy().quote_for(state, cust), cust

    sat_deal, _ = scenario(5)
    assert sat_deal is not None and sat_deal.shifted
    assert sat_deal.relief == pytest.approx(0.6 * v.mean_margin_per_tick * 3)
    mon_deal, _ = scenario(0)
    assert mon_deal is None or mon_deal.relief <= 1e-9


def test_slot_time_conservation():
    """booked + idle = capacity x ticks — sold from the revenue
    accounting, idle from the occupancy grid, computed independently."""
    from slots.policies import ARMS
    from slots.run import run_day
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        for arm in ("static", "nego"):
            m = run_day(ARMS[arm](), name, 20260710, 0)
            assert m["sold_unit_ticks"] + m["idle_unit_ticks"] == \
                v.capacity * v.ticks
            assert m["shows"] + m["noshows"] == m["bookings"]


def test_noshow_accounting_releases_capacity_and_pays_nothing():
    from dataclasses import replace
    from slots.run import _due
    v = replace(venue("barber"), noshow_prob=1.0)     # everyone flakes
    state = fresh_day(v)
    occupy(state, 12, 5)
    state.pending.append(
        __import__("slots.world", fromlist=["Booking"]).Booking(
            uid=99, start=12, dur=5, price=38.0, cost=5.0, cs=10.0))
    m = {"revenue": 0.0, "cost": 0.0, "shows": 0, "noshows": 0,
         "consumer_surplus": 0.0, "sold_unit_ticks": 0}
    state.tick = 12
    _due(state, m, master_seed=1)
    assert m["noshows"] == 1 and m["shows"] == 0
    assert m["revenue"] == 0.0 and m["consumer_surplus"] == 0.0
    assert can_book(state, 12, 5) and can_book(state, 12, 5)
    assert int(state.occupied.sum()) == 0     # the whole span came back


def test_experiment_is_deterministic():
    from slots.run import run_experiment
    r1 = run_experiment(["static", "computed", "nego"], "barber",
                        days=2, seed=11)
    r2 = run_experiment(["static", "computed", "nego"], "barber",
                        days=2, seed=11)
    assert r1 == r2


def test_run_day_margin_identity():
    from slots.policies import ARMS
    from slots.run import run_day
    m = run_day(ARMS["nego"](), "bar", 20260710, 3)
    assert m["margin"] == pytest.approx(m["revenue"] - m["cost"], abs=0.02)
    assert m["consumer_surplus"] >= 0 or m["negotiated"] > 0


def test_committed_results_stay_reproducible():
    """The committed slots/results.json must stay exactly reproducible at
    the config IT records (params read from the artifact, cheapest cell
    re-run — the barbershop, sigma 0, flex 0.15)."""
    import json
    import pathlib
    from slots.run import run_experiment
    from slots.world import SlotConfig
    path = pathlib.Path(__file__).parents[1] / "results.json"
    committed = json.load(open(path))
    cell = committed["venues"]["barber"]["cells"]["shock0_flex0.15"]
    res = run_experiment(committed["arms"], "barber",
                         days=committed["days"], seed=committed["seed"],
                         cfg=SlotConfig(sigma_shock=0.0, flexible_share=0.15))
    for arm, want in cell["totals"].items():
        got = res["arms"][arm]["totals"]
        assert {k: got[k] for k in want} == pytest.approx(want)

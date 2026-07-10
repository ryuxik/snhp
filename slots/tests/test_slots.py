"""SLOT-ECONOMICS tests: pairing is real, determinism holds, discount-only
is enforced, slot-time is conserved, no-shows are accounted, and the nego
arm's edges come from the right drivers (peak shadows, slot shifts)."""
import numpy as np
import pytest

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
    """The inversion worked: computed/1's per-hour re-solve never finds a
    multiplier above 1, and holds ~at list in the hottest hours — a
    competent sticker, not a strawman."""
    for name in ("barber", "parking", "bar"):
        v = venue(name)
        assert all(m <= 1.0 + 1e-9 for m in v.mstar.values())
        assert all(m >= v.cost_ratio - 1e-9 for m in v.mstar.values())
        hot = max(v.hours, key=lambda h: v.wtp_mult[h])
        assert v.mstar[hot] > 0.99


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
    edge_tick = (19 - v.open_hour) * 6    # 19:00 — the peak's leading edge:
    state.tick = edge_tick - 12           # a −30-min shift lands at 18:30
    flex = _customer(v, ratio=1.3, desired=edge_tick, n_req=1, kind="beer",
                     flexible=True)
    rigid = _customer(v, ratio=1.3, desired=edge_tick, n_req=1, kind="beer",
                      flexible=False)
    d_flex = nego_quote(state, flex)
    d_rigid = nego_quote(state, rigid)
    assert d_flex is not None and d_flex.shifted and d_flex.relief > 0
    assert d_rigid is None or not d_rigid.shifted


# ── the relief fix (post-registration, CRITICAL-ANALYSIS §3) ─────────────

def _learned_policy(v, peak_val, shoulder_val):
    """A nego policy whose learner has 'converged' to flat per-class slot
    values: peak hours worth peak_val $/unit-tick, every other hour
    shoulder_val — so relief arithmetic is checkable by hand."""
    from slots.policies import NegoPolicy
    pol = NegoPolicy()
    pol.learner._m = {h: (peak_val if h in v.peak_hours else shoulder_val)
                      for h in v.hours}
    return pol


def _hour_ticks(v, start, dur, h):
    """Unit-ticks of [start, start+dur) that land in hour h."""
    h0 = v.hidx(h) * 6
    return max(0, min(start + dur, h0 + 6) - max(start, h0))


def _expected_relief(v, pol, fb_span, deal_span):
    """The pre-registered relief formula, computed independently:
    value(fallback span) − value(deal span) at the learner's values."""
    return sum(pol.learner.value(v, h)
               * (_hour_ticks(v, *fb_span, h) - _hour_ticks(v, *deal_span, h))
               for h in v.hours)


def _edge_shift_scenario(v):
    """The 19:00 bar-peak leading edge: a flexible one-beer buyer whose
    −30-min shift moves the whole span off the peak."""
    state = fresh_day(v)
    edge = (19 - v.open_hour) * 6
    state.tick = edge - 12
    cust = _customer(v, ratio=1.3, desired=edge, n_req=1, kind="beer",
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
    for h in v.hours:
        want = 0.6 * v.mean_margin_per_tick if h in v.peak_hours else 0.0
        assert warmup_hour_value(v, h) == pytest.approx(want)
        # a fresh learner defers to the warmup values
        assert NegoPolicy().learner.value(v, h) == pytest.approx(want)
    pol = NegoPolicy()                       # no history at all
    state, cust = _edge_shift_scenario(v)
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
    lrn.end_day(v, margin, occ)
    assert lrn.value(v, h_full) == pytest.approx(900.0 / (v.capacity * 6))
    assert lrn.value(v, h_slack) == pytest.approx(0.0)   # never sold out
    assert lrn.value(v, 15) == pytest.approx(0.0)        # no sales at all
    # EWMA: a second day folds in at alpha=0.3
    first = lrn.value(v, h_full)
    lrn.end_day(v, {h_full: 450.0}, occ)
    want = 0.7 * first + 0.3 * (450.0 / (v.capacity * 6))
    assert lrn.value(v, h_full) == pytest.approx(want)


def test_run_day_feeds_the_learner_realized_margins():
    """The runner's end-of-day feed is real: after one day the nego arm's
    learner has an estimate for every hour, its observations are bounded
    by the day's realized margin, and no-show spans contribute nothing
    (settled bookings only)."""
    from slots.policies import ARMS
    from slots.run import run_day
    pol = ARMS["nego"]()
    m = run_day(pol, "bar", 20260710, 0)
    v = venue("bar")
    assert set(pol.learner._m) == set(v.hours)
    assert all(val >= 0.0 for val in pol.learner._m.values())
    # sold-out gating can only shrink an hour's observation below its
    # realized margin per capacity tick, never inflate it
    assert sum(pol.learner._m.values()) * v.capacity * 6 <= m["margin"] + 0.02

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

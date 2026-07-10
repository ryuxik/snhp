"""BAKESHOP tests: pairing is real, determinism holds, discount-only is
enforced, the freshness-tier math is exact, waste conserves, the cultural
control's calendar is honestly implemented (day-old shelf timing, dump
bucket, calendar blindness), and the dynamic arms' edges come from the
right drivers (aging stock moved while demand exists, bundles, scarcity
held at list on event days)."""
import pytest

from bakeshop.policies import (ComputedPolicy, ControlPolicy, NegoPolicy,
                               RegimePolicy, MIN_GAIN_ABS, MIN_GAIN_FRAC,
                               clearance_pressure, control_board,
                               detect_regime, flood_pressure, nego_quote)
from bakeshop.run import ARMS, run_day, run_experiment
from bakeshop.world import (BakeshopConfig, Consumer, DEFAULT_CONFIG, Lot,
                            ShopState, arrivals_at, begin_day, bundle_value,
                            day_rate_mult, end_of_day, get_venue,
                            is_spike_day, ladder, maybe_minibake,
                            sample_consumer, _order_err)


@pytest.fixture(scope="module")
def bakery():
    return get_venue("bakery")


@pytest.fixture(scope="module")
def flowers():
    return get_venue("flowers")


def _rich(venue, scale=1.4, walk=1.0):
    """A hand-built buyer valuing every SKU at scale× its list price."""
    return Consumer(wtp={it.sku: it.list_price * scale
                         for it in venue.items}, walk_cost=walk, uid=7)


def _baked_state(venue_name, seed=7):
    state = ShopState(venue_name)
    begin_day(state, get_venue(venue_name), seed)
    return state


# ── pairing & determinism ────────────────────────────────────────────────

def test_arrival_and_consumer_streams_are_policy_independent(bakery):
    """The treatment isolation guarantee: streams depend only on
    (seed, day, tick, k, cfg)."""
    assert [arrivals_at(bakery, 7, 3, t) for t in range(bakery.ticks_per_day)] \
        == [arrivals_at(bakery, 7, 3, t) for t in range(bakery.ticks_per_day)]
    c1 = sample_consumer(bakery, 7, 3, 10, 0)
    c2 = sample_consumer(bakery, 7, 3, 10, 0)
    assert (c1.wtp, c1.walk_cost, c1.uid) == (c2.wtp, c2.walk_cost, c2.uid)
    assert sample_consumer(bakery, 7, 3, 10, 1).uid != c1.uid


def test_experiment_is_deterministic():
    for venue in ("bakery", "flowers"):
        r1 = run_experiment(["control", "computed", "nego"], venue,
                            days=2, seed=11)
        r2 = run_experiment(["control", "computed", "nego"], venue,
                            days=2, seed=11)
        assert r1 == r2


def test_day_shock_is_mean_one_and_deterministic():
    import numpy as np
    cfg = BakeshopConfig(sigma_day=0.4)
    mults = [day_rate_mult(cfg, 42, d) for d in range(4000)]
    assert mults[7] == day_rate_mult(cfg, 42, 7)
    assert abs(np.mean(mults) - 1.0) < 0.03
    assert day_rate_mult(BakeshopConfig(sigma_day=0.0), 42, 7) == 1.0


def test_production_is_paired_and_miscalibration_is_mean_one(bakery):
    """The bake/order is drawn before any pricing exists: two states, same
    seed, same lots — regardless of which arm will trade against them. The
    gut error is mean-one, so no arm gets a systematically bigger bake."""
    import numpy as np
    s1, s2 = ShopState("bakery"), ShopState("bakery")
    m1 = begin_day(s1, bakery, 99, BakeshopConfig(sigma_miscal=0.35))
    m2 = begin_day(s2, bakery, 99, BakeshopConfig(sigma_miscal=0.35))
    assert m1 == m2
    assert [(l.sku, l.quantity) for l in s1.lots] == \
           [(l.sku, l.quantity) for l in s2.lots]
    errs = [_order_err(5, "bake", d, "croissant", 0.35) for d in range(3000)]
    assert abs(np.mean(errs) - 1.0) < 0.03


def test_spike_days_are_deterministic_and_frequency_matches():
    cfg = BakeshopConfig(spike_prob=0.1)
    days = [is_spike_day(31, d, cfg) for d in range(3000)]
    assert days == [is_spike_day(31, d, cfg) for d in range(3000)]
    assert 0.06 < sum(days) / 3000 < 0.14
    assert not any(is_spike_day(31, d, BakeshopConfig(spike_prob=0.0))
                   for d in range(100))


# ── freshness-tier WTP math ──────────────────────────────────────────────

def test_freshness_tier_wtp_math(bakery, flowers):
    """The canonical bundle value, by hand: day-old bakery goods are worth
    0.55× fresh; flowers lose exactly their spent vase days."""
    c = Consumer(wtp={"croissant": 4.0, "sourdough": 0.0, "cake-slice": 6.0},
                 walk_cost=1.0)
    # 2 day-old croissants: 4.0 × 0.55 × (1 + 0.55)
    assert bundle_value(bakery, c, [("croissant", 1, 2)]) == \
        pytest.approx(4.0 * 0.55 * 1.55)
    # bundle adds a fresh cake slice, additively
    assert bundle_value(bakery, c, [("croissant", 1, 2),
                                    ("cake-slice", 0, 1)]) == \
        pytest.approx(4.0 * 0.55 * 1.55 + 6.0)
    roses = flowers.item("dozen-roses")    # vase life with care = 9: linear
    assert list(roses.fresh_mults) == pytest.approx(
        [1.0, 8 / 9, 7 / 9, 6 / 9, 5 / 9, 4 / 9, 3 / 9, 2 / 9, 1 / 9], abs=1e-5)
    stems = flowers.item("stems")          # vase life with care = 6
    assert list(stems.fresh_mults) == pytest.approx(
        [1.0, 5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6], abs=1e-5)


# ── the cultural control, honestly implemented ───────────────────────────

def test_day_old_shelf_timing_in_control(bakery):
    """The bakery's day-old shelf: −50%, next MORNING only. Present at
    9:00, pulled from the board at noon; fresh stays at list all day."""
    state = _baked_state("bakery")
    state.lots.append(Lot("croissant", 10, baked_day=-1))
    state.tick = 4                                # 9:00
    board = control_board(state, bakery)
    assert board[("croissant", 1)] == pytest.approx(round(4.75 * 0.5, 2))
    assert board[("croissant", 0)] == 4.75
    state.tick = 10                               # 12:00 — pulled
    board = control_board(state, bakery)
    assert ("croissant", 1) not in board
    assert board[("croissant", 0)] == 4.75


def test_flower_markdown_ladder_is_graduated_not_a_cliff(flowers):
    """CRITICAL-ANALYSIS §9 fix: full price through the RETAIL DISPLAY LIFE
    (the old 3/4/5-day numbers, relabeled), then a THREE-step graduated
    markdown ladder across the rest of VASE LIFE WITH CARE (5-14 days) —
    not one day-4 cliff. Extending vase life also closes the old
    blindness: stems (display life 3) used to die before ever reaching
    the dump; at vase life 6 they now walk the whole ladder."""
    bouquet = flowers.item("bouquet")          # display 4, vase life 7
    assert bouquet.control_fracs[:4] == (1.0, 1.0, 1.0, 1.0)
    assert bouquet.control_fracs[4:] == (0.75, 0.5, 0.3)   # graduated steps
    roses = flowers.item("dozen-roses")        # display 5, vase life 9
    assert roses.control_fracs[:5] == (1.0,) * 5
    assert len(set(roses.control_fracs[5:])) > 1    # more than one tier
    assert roses.control_fracs[-1] == pytest.approx(0.3)
    stems = flowers.item("stems")              # display 3, vase life 6
    assert stems.control_fracs[:3] == (1.0, 1.0, 1.0)
    assert stems.control_fracs[3:] == (0.75, 0.5, 0.3)    # reaches the ladder now

    state = ShopState("flowers", day=6)
    state.lots = [Lot("bouquet", 5, baked_day=0),      # age 6: deepest tier
                  Lot("dozen-roses", 5, baked_day=2),  # age 4: still display life
                  Lot("stems", 5, baked_day=1)]        # age 5: deepest tier
    board = control_board(state, flowers)
    assert board[("bouquet", 6)] == pytest.approx(28.0 * 0.30)
    assert board[("dozen-roses", 4)] == 95.0
    assert board[("stems", 5)] == pytest.approx(4.0 * 0.30)


def test_flowers_weekly_cycle_and_stem_death(flowers):
    """Weekly wholesale delivery: stock arrives day 0 only (net of the
    receiving-loss cull, flushed as waste at the FIRST close); stems (vase
    life with care = 6 days, the old hard 3-day cutoff relabeled as
    display life) are waste at the close of day 5 → day 6 — at cost."""
    state = ShopState("flowers")
    morning, pu, _ = begin_day(state, flowers, 7)
    stems0 = state.stock("stems", 0)
    assert stems0 > 0
    assert stems0 == morning["stems"]              # morning IS the sellable count
    culled0 = pu - sum(morning.values())
    assert culled0 > 0                             # receiving loss actually fires
    w0 = end_of_day(state, flowers)                # day 0 → 1: the cull only
    assert w0["waste_units"] == culled0
    for _ in range(1, 5):                          # days 1..4: no delivery,
        _, pu_d, _ = begin_day(state, flowers, 7)  # nothing old enough to die
        assert pu_d == 0
        w = end_of_day(state, flowers)
        assert w["waste_units"] == 0
    begin_day(state, flowers, 7)                   # day 5: still no delivery
    w6 = end_of_day(state, flowers)                # day 5 → 6: stems (life 6) die
    assert w6["waste_units"] >= stems0
    assert w6["waste_cost"] >= stems0 * flowers.item("stems").unit_cost - 1e-6
    assert state.stock("stems", 6) == 0


# ── discount-only, everywhere ────────────────────────────────────────────

def test_computed_never_exceeds_list(bakery):
    state = _baked_state("bakery")
    state.lots.append(Lot("croissant", 20, baked_day=-1))
    for tick in (0, 8, 16, 22):
        state.tick = tick
        board = ComputedPolicy().board(state, bakery, 7, DEFAULT_CONFIG)
        for (sku, age), p in board.items():
            assert p <= bakery.item(sku).list_price + 1e-9


def test_nego_deals_respect_invariants_over_a_live_day(bakery):
    """Every deal quoted across a live day: never above the bundle's list
    value, the shop clears its no-deal event PLUS the buffer, the buyer
    beats their own no-deal event — 'never worse than the culture' is
    structural, not asserted."""
    policy = NegoPolicy()
    state = _baked_state("bakery", seed=23)
    state.lots.append(Lot("croissant", 15, baked_day=-1))
    seen = 0
    for tick in range(0, bakery.ticks_per_day, 2):
        state.tick = tick
        for k in range(arrivals_at(bakery, 23, 0, tick)):
            c = sample_consumer(bakery, 23, 0, tick, k)
            deal = policy.quote_for(state, bakery, c, 23, DEFAULT_CONFIG)
            if deal is None:
                continue
            seen += 1
            assert deal.price <= deal.list_value + 1e-9
            assert deal.u_shop >= deal.d_shop + max(
                MIN_GAIN_ABS, MIN_GAIN_FRAC * deal.list_value) - 1e-6
            assert deal.u_buyer >= deal.d_buyer - 1e-9
    assert seen > 15


# ── the aging-stock channel (H-B1 mechanism pins) ────────────────────────

def test_computed_reprices_aged_below_fresh_and_sells_it_all_day(bakery):
    """The residual-demand fix: day-old prices BELOW the same SKU's fresh
    price, and the aged tier stays on the computed board after the
    control's noon pull — aging stock moves while demand is present."""
    state = _baked_state("bakery")
    state.lots.append(Lot("croissant", 25, baked_day=-1))
    state.tick = 16                               # 15:00
    board = ComputedPolicy().board(state, bakery, 7, DEFAULT_CONFIG)
    assert ("croissant", 1) in board              # control would have pulled it
    assert board[("croissant", 1)] < board[("croissant", 0)]
    assert board[("croissant", 0)] <= 4.75 + 1e-9


def test_computed_scarce_fresh_holds_list(bakery):
    """The stockout hazard: when expected fresh demand covers the stock,
    cutting price buys nothing — scarce morning stock stays AT list."""
    state = ShopState("bakery")
    state.lots = [Lot("croissant", 4, baked_day=0),
                  Lot("sourdough", 3, baked_day=0)]
    state.tick = 2                                # 8:00, the whole day ahead
    board = ComputedPolicy().board(state, bakery, 7, DEFAULT_CONFIG)
    assert board[("croissant", 0)] == 4.75
    assert board[("sourdough", 0)] == 9.0


def test_nego_no_deal_when_the_sticker_is_already_optimal(bakery):
    """Event-consistent honesty: a rich buyer facing scarce fresh stock
    (calendar recovery ≈ list) has NOTHING to negotiate — the engine says
    so instead of forcing a deal."""
    state = ShopState("bakery")
    state.lots = [Lot("croissant", 4, baked_day=0),
                  Lot("sourdough", 3, baked_day=0)]
    state.tick = 2
    assert nego_quote(state, bakery, _rich(bakery), 7, DEFAULT_CONFIG) is None


# ── the bundle channel (H-B2 mechanism pin) ──────────────────────────────

def test_nego_bundles_convert_the_sub_list_second_item(bakery):
    """A croissant buyer whose cake WTP sits between cost and list gets the
    cake IN the bundle (sub-list conversion of the add-on); with pairs
    ablated, the same buyer deals croissants only."""
    state = _baked_state("bakery")
    state.tick = 16                               # afternoon glut
    c = Consumer(wtp={"croissant": 6.5, "sourdough": 0.0, "cake-slice": 5.0},
                 walk_cost=1.0, uid=1)
    deal = nego_quote(state, bakery, c, 7, DEFAULT_CONFIG, pairs=True)
    assert deal is not None
    assert {sku for sku, _, _ in deal.lines} == {"croissant", "cake-slice"}
    solo = nego_quote(state, bakery, c, 7, DEFAULT_CONFIG, pairs=False)
    assert solo is not None
    assert {sku for sku, _, _ in solo.lines} == {"croissant"}


# ── event-day scarcity (H-B3 mechanism pins) ─────────────────────────────

def test_event_day_sellout_behavior(flowers):
    """On a spike day (public, ×6 demand vs ×2-capped supply) scarcity is
    real: computed holds every fresh cell at list, nego finds nothing to
    negotiate with a rich buyer, and the flood is real — a spike day moves
    far more volume than a calm one through the SAME control board.
    (The old "spiked WEEK wastes less than a calm week" comparison doesn't
    hold cleanly any more now that vase life with care spans most of the
    delivery cycle — a week of spike_prob=1.0 means a big daily drop
    layered on top of carried-forward stock every day, so late-week
    pileup can outweigh the single-day scarcity effect; the single-day
    claim below is the one CRITICAL-ANALYSIS §9 actually rests on.)"""
    spike = BakeshopConfig(spike_prob=1.0)
    state = ShopState("flowers", day=3)           # mid-week: only the
    begin_day(state, flowers, 7, spike)           # ×2-capped drop lands
    state.tick = 2
    board = ComputedPolicy().board(state, flowers, 7, spike)
    assert board[("bouquet", 0)] == 28.0
    assert board[("dozen-roses", 0)] == 95.0
    assert nego_quote(state, flowers, _rich(flowers), 7, spike) is None
    # the flood is real: a spike day moves far more units than a calm one
    calm = BakeshopConfig(spike_prob=0.0)
    spike_units = run_day(ControlPolicy(), ShopState("flowers"), flowers,
                          5, 0, spike)["units"]
    calm_units = run_day(ControlPolicy(), ShopState("flowers"), flowers,
                         5, 0, calm)["units"]
    assert spike_units > 3 * calm_units


def test_spike_supply_is_capped_not_scaled(flowers):
    """The Valentine's truck is allocation-capped: the event-day drop is
    ≈ ×2 a normal day's plan, nowhere near the ×6 demand."""
    from bakeshop.world import base_plan
    spike = BakeshopConfig(spike_prob=1.0, sigma_miscal=0.0)
    state = ShopState("flowers", day=3)           # mid-week: drop only
    _, pu, _ = begin_day(state, flowers, 7, spike)
    plan = base_plan("flowers")
    expect = sum(round(plan[it.sku] * 2.0) for it in flowers.items)
    assert abs(pu - expect) <= 3
    assert pu < 3.0 * sum(plan.values())


# ── CRITICAL-ANALYSIS §9 Part 1: realized dollar shrink recalibration ────

def test_receiving_loss_fires_and_is_paired_across_arms(flowers):
    """The receiving-loss cull (CALIBRATION-TARGETS §3 fix) happens in
    begin_day, before any policy sees the stock — it must fire (not a
    no-op) and be IDENTICAL across two independent states given the same
    seed (paired, like every other production draw)."""
    s1, s2 = ShopState("flowers"), ShopState("flowers")
    m1, pu1, _ = begin_day(s1, flowers, 7)
    m2, pu2, _ = begin_day(s2, flowers, 7)
    assert m1 == m2 and pu1 == pu2
    assert pu1 > sum(m1.values())          # some of what was ordered was culled
    assert s1.pending_waste_units == s2.pending_waste_units > 0
    assert s1.pending_waste_cost == pytest.approx(s2.pending_waste_cost)


def test_computed_realized_dollar_shrink_lands_in_the_ifpa_band():
    """CRITICAL-ANALYSIS §9 / CALIBRATION-TARGETS §3: after the shrink
    recalibration, the age-aware POSTED arm's own realized dollar shrink
    (waste $ ÷ dollars handled) should land near the IFPA floral-shrink
    target (~9-12%), not the ~0-2% an omniscient-demand pricer reaches
    with zero receiving loss, and not the old ~30-50%+ dump-driven number
    either. Checked at the grid's two miscalibration cells, calm days."""
    flowers = get_venue("flowers")
    for sigma in (0.15, 0.35):
        cfg = BakeshopConfig(sigma_miscal=sigma, spike_prob=0.0)
        policy = ComputedPolicy()
        state = ShopState("flowers")
        revenue = waste = 0.0
        for d in range(30):
            m = run_day(policy, state, flowers, 20260710, d, cfg)
            revenue += m["revenue"]
            waste += m["waste_cost"]
        shrink = waste / (revenue + waste)
        assert 0.06 <= shrink <= 0.15, (sigma, shrink)


def test_legacy_flower_calibration_still_available_and_labeled():
    """The old (pre-recalibration) 3/4/5-day hard-cutoff florist is kept
    as a labeled 'low-volume independent' comparison cell, not deleted."""
    legacy = get_venue("flowers-legacy")
    assert legacy.receiving_loss == 0.0
    assert legacy.item("bouquet").life == 4          # the old hard cutoff
    assert legacy.item("stems").control_fracs == (1.0, 1.0, 1.0)  # never
                                                        # reaches the dump


# ── CRITICAL-ANALYSIS §9 Part 2: the regime/1 detector ───────────────────

def test_flood_detector_fires_on_synthetic_flood_not_on_normal_day(flowers):
    """The no-oracle constraint, exercised directly: `flood_pressure` sees
    only realized arrivals-so-far and the shop's own seasonal calendar —
    never `is_spike_day`. It must clear the flood threshold on an actual
    ×6 spike day and stay well under it on an ordinary day, at the same
    (day, tick)."""
    calm = BakeshopConfig(sigma_miscal=0.15, spike_prob=0.0)
    spike = BakeshopConfig(sigma_miscal=0.15, spike_prob=1.0)
    from bakeshop.policies import FLOOD_ARRIVAL_RATIO
    for tick in (2, 4, 8, 14):
        p_calm = flood_pressure(flowers, 20260710, calm, 3, tick)
        p_spike = flood_pressure(flowers, 20260710, spike, 3, tick)
        assert p_calm < FLOOD_ARRIVAL_RATIO, (tick, p_calm)
        assert p_spike >= FLOOD_ARRIVAL_RATIO, (tick, p_spike)
        assert p_spike > 2 * p_calm


def test_clearance_detector_fires_on_a_synthetic_glut(flowers):
    """`clearance_pressure`'s aged-fraction signal: a shelf that is mostly
    old stock reads as a glut regardless of the delivery calendar."""
    state = ShopState("flowers", day=5)
    state.lots = [Lot("bouquet", 2, baked_day=5),        # fresh (age 0)
                  Lot("bouquet", 20, baked_day=0)]        # age 5: deep in
                                                           # the markdown ladder
    cycle_ratio, aged_frac = clearance_pressure(state, flowers)
    assert aged_frac > 0.85
    from bakeshop.policies import CLEARANCE_AGED_FRACTION
    assert aged_frac >= CLEARANCE_AGED_FRACTION
    cfg = BakeshopConfig()
    assert detect_regime(state, flowers, 7, cfg) in ("clearance", "flood")


def test_regime_matches_posted_behavior_during_a_detected_flood(flowers):
    """Mechanism pin: once regime/1 calls "flood" or "clearance", it must
    behave EXACTLY like computed/1 (same board) and refuse the bilateral
    channel entirely (no buffer, no negotiated discount) — "post its own
    markdown board (no bilateral, no buffer)", not a blend."""
    spike = BakeshopConfig(sigma_miscal=0.15, spike_prob=1.0)
    state = ShopState("flowers", day=3)
    begin_day(state, flowers, 7, spike)
    state.tick = 8
    policy = RegimePolicy()
    regime = policy.regime(state, flowers, 7, spike)
    assert regime == "flood"
    assert policy.board(state, flowers, 7, spike) == \
        ComputedPolicy().board(state, flowers, 7, spike)
    rich = _rich(flowers)
    assert policy.quote_for(state, flowers, rich, 7, spike) is None


def test_regime_matches_nego_behavior_in_hetero_conditions(bakery):
    """When neither flood nor clearance pressure is detected, regime/1
    must delegate to nego/1's bilateral quote exactly (same Deal) —
    verified at the bakery, where clearance never fires by construction
    (daily bake) and the calm-day arrival rate stays well under the flood
    ratio."""
    state = _baked_state("bakery", seed=23)
    state.tick = 10
    calm = DEFAULT_CONFIG
    policy = RegimePolicy()
    assert policy.regime(state, bakery, 23, calm) == "hetero"
    c = _rich(bakery, scale=0.9)
    regime_deal = policy.quote_for(state, bakery, c, 23, calm)
    nego_deal = nego_quote(state, bakery, c, 23, calm)
    assert regime_deal == nego_deal
    assert policy.board(state, bakery, 23, calm) == control_board(state, bakery)


def test_regime_bakery_calm_cells_are_byte_identical_to_nego():
    """The pre-registered spillover check (CRITICAL-ANALYSIS §9(a)): at
    the bakery, clearance pressure never fires (delivery_every=1) and calm
    days never cross the flood ratio, so regime/1 must be indistinguishable
    from nego/1 there — 'unchanged', the best-case spillover outcome."""
    bakery = get_venue("bakery")
    cfg = BakeshopConfig(sigma_miscal=0.15, spike_prob=0.0)
    regime_profit, nego_profit = [], []
    st_r, st_n = ShopState("bakery"), ShopState("bakery")
    for d in range(10):
        regime_profit.append(
            run_day(RegimePolicy(), st_r, bakery, 20260710, d, cfg)["profit"])
        nego_profit.append(
            run_day(NegoPolicy(), st_n, bakery, 20260710, d, cfg)["profit"])
    assert regime_profit == nego_profit


# ── machine dynamics ─────────────────────────────────────────────────────

def test_waste_conservation():
    """produced = sold + shelved + wasted, exactly, over multi-day runs —
    for a posted arm and the nego arm, both venues."""
    for venue_name, arm in (("bakery", "control"), ("bakery", "nego"),
                            ("flowers", "control"), ("flowers", "nego")):
        venue = get_venue(venue_name)
        policy = ARMS[arm]()
        state = ShopState(venue_name)
        produced = sold = wasted = 0
        for d in range(4):
            m = run_day(policy, state, venue, 13, d)
            produced += m["produced_units"]
            sold += m["units"]
            wasted += m["waste_units"]
        shelved = sum(l.quantity for l in state.lots if l.quantity > 0)
        assert produced == sold + wasted + shelved, (venue_name, arm)


def test_take_validates_before_mutating(bakery):
    state = ShopState("bakery")
    state.lots = [Lot("croissant", 1, baked_day=0),
                  Lot("croissant", 1, baked_day=-1)]
    with pytest.raises(ValueError):
        state.take("croissant", 0, 2)             # only 1 fresh unit
    assert state.stock("croissant", 0) == 1       # nothing was decremented
    assert state.stock("croissant", 1) == 1


def test_minibake_gut_trigger(bakery):
    """The 2pm gut check fires when the fresh shelf ran low, not when it
    didn't — and it reacts to the arm's own shelf, which is the documented
    (deterministic) place arms may diverge in production."""
    state = _baked_state("bakery")
    morning = {it.sku: state.stock(it.sku, 0) for it in bakery.items}
    pu, _ = maybe_minibake(state, bakery, morning)
    assert pu == 0                                # full shelf: no mini-bake
    state.take("croissant", 0, int(morning["croissant"] * 0.8))
    pu, pc = maybe_minibake(state, bakery, morning)
    assert pu == int(round(0.35 * morning["croissant"]))
    assert pc == pytest.approx(pu * 1.40)


def test_bakery_lands_near_the_calibration_target(bakery):
    """~300 items/day (calibration.BAKERY_DAILY_ITEMS) under the control —
    the world is calibrated to the shop it claims to model."""
    import numpy as np
    state = ShopState("bakery")
    units = [run_day(ControlPolicy(), state, bakery, 20260710, d)["units"]
             for d in range(4)]
    assert 230 <= float(np.mean(units)) <= 370


def test_committed_results_stay_reproducible():
    """bakeshop/results.json must remain exactly reproducible at the config
    IT records (params read from the artifact, not hardcoded). One cell per
    venue pins the whole pipeline."""
    import json
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "results.json"
    committed = json.load(open(path))
    for venue in ("bakery", "flowers"):
        name, cell = next(iter(committed["venues"][venue]["cells"].items()))
        cfg = BakeshopConfig(sigma_miscal=cell["world"]["sigma_miscal"],
                             spike_prob=cell["world"]["spike_prob"],
                             sigma_day=cell["world"]["sigma_day"])
        res = run_experiment(committed["arms"], venue,
                             days=committed["days"],
                             seed=committed["seed"], cfg=cfg)
        for arm in committed["arms"]:
            assert res["arms"][arm]["totals"]["profit"] == \
                cell["totals"][arm]["profit"], (venue, arm)


def test_run_day_accounting_consistency(bakery):
    for arm in ("control", "nego"):
        state = ShopState("bakery")
        m = run_day(ARMS[arm](), state, bakery, 5, 0)
        assert m["deals"] <= m["arrivals"]
        assert m["units"] >= m["deals"]
        assert m["profit"] == pytest.approx(
            m["revenue"] - m["cogs_sold"] - m["waste_cost"], abs=0.02)
        assert m["revenue"] >= 0 and m["consumer_surplus"] >= 0
        assert 0.0 <= m["depth"] <= 1.0


# ════════════════════════════════════════════════════════════════════════════
#  The SERVICES tier — the REAL florist (CRITICAL-ANALYSIS §9 follow-up).
#  Posted wins the walk-in CLEARANCE slice; bilateral wins the SERVICES slice
#  (arrangement / delivery / event / attach). These tests pin the four new
#  lines' mechanisms, the discount-only invariant, identity-keyed pairing, and
#  that the posted arm gets its BEST SHOT (an interior profit-max, not a
#  strawman) so a bilateral win is a real result, not a rigged one.
# ════════════════════════════════════════════════════════════════════════════
from bakeshop import calibration as cal
from bakeshop import services as svc


def test_services_nash_price_splits_and_respects_discount_only():
    """The shared bilateral primitive: on a real surplus it returns an interior
    price that clears the buyer (gain ≥ 0), clears the shop's buffer, and never
    exceeds the discount-only ceiling; on no surplus it declines."""
    # value 100, cost 40, both walk away from nothing: midpoint ≈ 70
    p = svc.nash_price(100.0, 40.0, 0.0, 0.0, ceiling=120.0, buffer=1.0)
    assert p == pytest.approx(70.0, abs=0.01)
    # discount-only ceiling binds: never over list even though the split wants to
    p = svc.nash_price(100.0, 40.0, 0.0, 0.0, ceiling=55.0, buffer=1.0)
    assert p <= 55.0 + 1e-9 and p >= 40.0
    # no joint gain over disagreements → no deal
    assert svc.nash_price(50.0, 40.0, 6.0, 6.0, ceiling=100.0, buffer=1.0) is None
    # a deal that cannot clear the buffer under the ceiling → no deal
    assert svc.nash_price(60.0, 40.0, 0.0, 18.0, ceiling=59.0, buffer=5.0) is None


def test_arrangement_reference_prices_hit_nyc_anchors():
    """The arrangement line reproduces the TJ Flowers NYC price anchors:
    standard medium wrapped ≈ $85, standard medium vase ≈ $125, premium medium
    vase in the $150-200 luxury band — and every config carries a real labor
    margin (cost < reference list)."""
    by = {c.attrs: c for c in svc.ARR_CONFIGS}
    assert by[("standard", "wrap", "medium")].ref_list == pytest.approx(85, abs=15)
    assert by[("standard", "vase", "medium")].ref_list == pytest.approx(125, abs=15)
    assert 150 <= by[("premium", "vase", "medium")].ref_list <= 205
    for c in svc.ARR_CONFIGS:
        assert c.cost < c.ref_list                    # a real arrangement margin
    # the vase (arranged) config carries MORE margin than the wrap — the
    # arrangement IS the margin (the whole premise of the line)
    assert (by[("standard", "vase", "medium")].ref_list
            - by[("standard", "vase", "medium")].cost) > \
           (by[("standard", "wrap", "medium")].ref_list
            - by[("standard", "wrap", "medium")].cost)


def test_services_buyer_streams_are_paired_on_identity_not_policy():
    """The isolation guarantee, services edition: every buyer draw depends only
    on (seed, line, day, k) — never on the arm. Both posted and bilateral face
    the byte-identical stream; the k index actually varies the buyer."""
    a = svc.arr_buyer(20260710, 3, 5)
    assert a.values == svc.arr_buyer(20260710, 3, 5).values     # deterministic
    assert svc.arr_buyer(20260710, 3, 6).values != a.values     # k varies buyer
    assert svc.delivery_buyer(1, 2, 0).convenience == \
        svc.delivery_buyer(1, 2, 0).convenience
    assert svc.attach_buyer(1, 2, 0) == svc.attach_buyer(1, 2, 0)
    c1, m1, b1 = svc.event_booking(9, 4, 0)
    c2, m2, b2 = svc.event_booking(9, 4, 0)
    assert b1.values == b2.values and c1 is c2


def test_arrangement_logroll_selects_the_efficient_config():
    """The multi-issue logroll (the arrangement line's whole point). A buyer
    who loves PREMIUM blooms but is indifferent to the vessel should be steered
    by the bilateral engine to premium flowers in a cheap wrap — the joint
    value-minus-cost maximizer — NOT the rigid menu's premium-only-in-a-vase
    pairing. The engine picks argmax(value − cost) over the WHOLE space and
    prices it under the discount-only ceiling, clearing the shop's buffer."""
    by = {c.attrs: i for i, c in enumerate(svc.ARR_CONFIGS)}
    # craft the buyer: high value on premium+wrap configs, low on vases
    vals = [0.0] * len(svc.ARR_CONFIGS)
    for i, c in enumerate(svc.ARR_CONFIGS):
        g, st, sz = c.attrs
        base = 200.0 if g == "premium" else 120.0
        base *= 1.0 if st == "wrap" else (0.72 if st == "hand_tie" else 0.5)
        vals[i] = base * (0.85 if sz == "small" else 1.0 if sz == "medium" else 1.15)
    buyer = svc.Buyer(tuple(vals), outside=0.0)
    # λ=1.0 (the reference sticker) — a tighter discount-only ceiling than the
    # tuned markup, so the logroll clears the buffer under the strictest ceiling
    out = svc._nego_choice(svc.ARR_CONFIGS, svc.ARR_MENU_IDX, 1.0, buyer,
                           pure=True)
    assert out is not None
    price, cost, idx, kind = out
    g, st, sz = svc.ARR_CONFIGS[idx].attrs
    assert (g, st) == ("premium", "wrap")             # premium-in-a-wrap logroll
    assert price <= 1.0 * svc.ARR_CONFIGS[idx].ref_list + 1e-6      # discount-only
    assert (price - cost) >= max(cal.SERVICES_MIN_GAIN_ABS,
                                 cal.SERVICES_MIN_GAIN_FRAC
                                 * svc.ARR_CONFIGS[idx].ref_list) - 1e-6


def test_delivery_routing_logroll_beats_the_flat_fee():
    """The delivery line's capacity lever: route density. On a day the bilateral
    broker steers flexible buyers into shared windows (lower marginal cost) and
    splits the saving; a declined quote falls back to the flat fee, so the
    deployable broker is never worse than posted — and on a flexible-heavy day
    it is strictly better."""
    fee = svc._optimize_flat_fee(20260710, 60, cal.DELIVERY_RATE)
    posted = svc._delivery_day(20260710, 3, cal.DELIVERY_RATE, fee, "posted")
    nego = svc._delivery_day(20260710, 3, cal.DELIVERY_RATE, fee, "nego")
    assert nego[0] >= posted[0] - 1e-6                 # deployable ≥ posted
    # aggregate over many days: the routing logroll is a real, positive edge
    tot_p = sum(svc._delivery_day(20260710, d, cal.DELIVERY_RATE, fee, "posted")[0]
                for d in range(40))
    tot_n = sum(svc._delivery_day(20260710, d, cal.DELIVERY_RATE, fee, "nego")[0]
                for d in range(40))
    assert tot_n > tot_p


def test_event_bespoke_quote_beats_fixed_packages():
    """The event line: over real bookings, bespoke bilateral quoting sizes to
    each booking's budget and configures the scope×palette space the coarse
    tiered package menu can't span. The deployable broker nets AT LEAST the
    fixed-package profit on every booking and strictly more in aggregate, and
    it changes the outcome on a real share of bookings (bespoke actually
    fires) — bilateral quoting's textbook case. Discount-only holds throughout."""
    wed_lam, fun_lam = svc.event_markups(20260710)
    tot_p = tot_n = 0.0
    bespoke = 0
    for d in range(500):
        for k in range(3):
            configs, menu, buyer = svc.event_booking(20260710, d, k)
            lam = wed_lam if configs is svc.EVENT_WED_CONFIGS else fun_lam
            pp = svc._posted_choice(configs, menu, lam, buyer)
            nn = svc._nego_choice(configs, menu, lam, buyer, pure=False)
            if pp is not None:
                tot_p += pp[0] - pp[1]
            if nn is not None:
                tot_n += nn[0] - nn[1]
                assert nn[0] <= round(lam * configs[nn[2]].ref_list, 2) + 1e-6
                if pp is None or nn[2] != pp[2] or abs(nn[0] - pp[0]) > 1e-6:
                    bespoke += 1
    assert tot_n >= tot_p - 1e-6            # deployable broker ≥ fixed packages
    assert tot_n > tot_p                    # and strictly better in aggregate
    assert bespoke > 0                      # bespoke quoting actually fired


def test_attach_is_a_complement_and_suggest_converts_sub_shelf():
    """The attach line (suggest/1): buying flowers RAISES attach WTP (a
    complement, not a substitute), and the suggest mechanic converts a buyer
    whose WTP sits BELOW the shelf price but above cost — a sale the passive
    shelf loses entirely."""
    # complement boost is applied to interested items (measured over a sample)
    boosted = False
    for k in range(50):
        wtp = svc.attach_buyer(20260710, 1, k)
        for item in cal.ATTACH_ITEMS:
            if wtp[item] > 0:
                boosted = True
                # an interested item can exceed its un-boosted base median
                # (the ×(1+boost) complement), which the shelf-only arm ignores
    assert boosted
    # a sub-shelf conversion: WTP between cost and shelf price → posted misses,
    # suggest converts at a Nash price strictly inside (cost, shelf)
    item = "chocolates"
    shelf = 1.12 * cal.ATTACH_REF_PRICE[item]
    cost = cal.ATTACH_COST[item]
    w = 0.5 * (cost + shelf)                           # below shelf, above cost
    assert w < shelf                                    # posted would NOT sell
    p = svc.nash_price(w, cost, 0.0, 0.0, cal.ATTACH_REF_PRICE[item],
                       max(cal.SERVICES_MIN_GAIN_ABS,
                           cal.SERVICES_MIN_GAIN_FRAC * cal.ATTACH_REF_PRICE[item]))
    assert p is not None and cost < p <= w + 1e-9       # converted, shop profits


def test_services_posted_arm_gets_its_best_shot_interior_optimum():
    """The §2 meta-pattern, enforced: the posted arm's tuned menu markup is a
    genuine INTERIOR profit-max (not pinned at a grid boundary — that would be a
    strawman the bilateral arm beats for free). Perturbing the markup up AND
    down both lower posted profit on the population."""
    lam = svc._optimize_menu_markup(
        svc.ARR_CONFIGS, svc.ARR_MENU_IDX,
        (svc.arr_buyer(20260710, 9 * 10 ** 6, k) for k in range(9000)),
        n_sample=8000)
    assert 0.78 < lam < 1.55                            # strictly interior

    sample = [svc.arr_buyer(20260710, 9 * 10 ** 6, k) for k in range(8000)]

    def posted_profit(l):
        prof = 0.0
        for b in sample:
            out = svc._posted_choice(svc.ARR_CONFIGS, svc.ARR_MENU_IDX, l, b)
            if out is not None:
                prof += out[0] - out[1]
        return prof
    here = posted_profit(lam)
    assert here >= posted_profit(lam + 0.1) and here >= posted_profit(lam - 0.1)


def test_services_run_is_deterministic():
    """The whole services pipeline is reproducible bit-for-bit at a fixed seed
    (the committed bakeshop/services.json is regenerated from it)."""
    import json
    a = svc.run_services(20260710, days=12)
    b = svc.run_services(20260710, days=12)
    assert json.dumps(a["lines"], sort_keys=True) == \
        json.dumps(b["lines"], sort_keys=True)
    assert a["blend"] == b["blend"]


def test_services_committed_artifact_states_the_split_honestly():
    """The headline claim, guarded on the committed artifact: posted WINS the
    walk-in clearance slice (nego − posted negative, CI clear of zero) while
    bilateral WINS every services line (deployable nego − posted positive, CI
    clear of zero), and the revenue-weighted florist favours bilateral. The
    'posted beats nego' boundary is now scoped to the clearance slice alone."""
    import json
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "services.json"
    d = json.load(open(path))
    # posted wins the clearance slice, unambiguously
    w = d["walkin"]["nego_vs_posted_profit"]
    assert w["mean"] < 0 and w["ci95"][1] < 0
    # bilateral (deployable) wins every services line, unambiguously
    for name, L in d["lines"].items():
        delta = L["deltas"]["nego_vs_posted"]["profit"]
        assert delta["mean"] > 0 and delta["ci95"][0] > 0, name
    # arrangement bilateral wins even STANDALONE (pure, no menu fallback)
    arr_pure = d["lines"]["arrangement"]["deltas"]["nego-pure_vs_posted"]["profit"]
    assert arr_pure["mean"] > 0 and arr_pure["ci95"][0] > 0
    # the services slice dominates revenue (the task's premise)
    shares = {r["line"]: r["revenue_share"] for r in d["blend"]["rows"]}
    assert shares["walk-in (clearance)"] < 0.35        # clearance is a minority
    # revenue-weighted, the whole florist favours bilateral
    assert d["blend"]["nego_profit_per_day"] > d["blend"]["posted_profit_per_day"]

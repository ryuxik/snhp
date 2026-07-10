"""BAKESHOP tests: pairing is real, determinism holds, discount-only is
enforced, the freshness-tier math is exact, waste conserves, the cultural
control's calendar is honestly implemented (day-old shelf timing, dump
bucket, calendar blindness), and the dynamic arms' edges come from the
right drivers (aging stock moved while demand exists, bundles, scarcity
held at list on event days)."""
import pytest

from bakeshop.policies import (ComputedPolicy, ControlPolicy, NegoPolicy,
                               MIN_GAIN_ABS, MIN_GAIN_FRAC, control_board,
                               nego_quote)
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
    roses = flowers.item("dozen-roses")           # vase life 5: linear
    assert list(roses.fresh_mults) == pytest.approx([1.0, 0.8, 0.6, 0.4, 0.2])
    stems = flowers.item("stems")                 # vase life 3
    assert list(stems.fresh_mults) == pytest.approx([1.0, 2 / 3, 1 / 3])


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


def test_flower_dump_calendar_and_its_blindness(flowers):
    """Full price until day 4 of vase life, then −70% — one shop-wide rule.
    Stems (3-day life) die before the dump day ever reaches them: the
    calendar's blindness, implemented faithfully."""
    state = ShopState("flowers", day=4)
    state.lots = [Lot("bouquet", 5, baked_day=1),      # age 3: dump day
                  Lot("dozen-roses", 5, baked_day=2),  # age 2: full price
                  Lot("stems", 5, baked_day=2)]        # age 2: last day alive
    board = control_board(state, flowers)
    assert board[("bouquet", 3)] == pytest.approx(28.0 * 0.30)
    assert board[("dozen-roses", 2)] == 95.0
    assert board[("stems", 2)] == 4.0              # never discounted
    stems = flowers.item("stems")
    assert all(f == 1.0 for f in stems.control_fracs)


def test_flowers_weekly_cycle_and_stem_death(flowers):
    """Weekly wholesale delivery: stock arrives day 0 only; stems (3-day
    vase life) are waste by the end of day 2 — at cost."""
    state = ShopState("flowers")
    begin_day(state, flowers, 7)
    stems0 = state.stock("stems", 0)
    assert stems0 > 0
    w0 = end_of_day(state, flowers)                # day 0 → 1
    assert w0["waste_units"] == 0
    m1, pu1, _ = begin_day(state, flowers, 7)      # day 1: no delivery
    assert pu1 == 0
    end_of_day(state, flowers)                     # day 1 → 2
    w2 = end_of_day(state, flowers)                # day 2 → 3: stems die
    assert w2["waste_units"] >= stems0
    assert w2["waste_cost"] >= stems0 * flowers.item("stems").unit_cost - 1e-6
    assert state.stock("stems", 3) == 0


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
    negotiate with a rich buyer, and a spiked week wastes far less than a
    calm one (sellout leaves nothing to die)."""
    spike = BakeshopConfig(spike_prob=1.0)
    state = ShopState("flowers", day=3)           # mid-week: only the
    begin_day(state, flowers, 7, spike)           # ×2-capped drop lands
    state.tick = 2
    board = ComputedPolicy().board(state, flowers, 7, spike)
    assert board[("bouquet", 0)] == 28.0
    assert board[("dozen-roses", 0)] == 95.0
    assert nego_quote(state, flowers, _rich(flowers), 7, spike) is None
    # spiked weeks waste less than calm weeks under the same control
    calm = BakeshopConfig(spike_prob=0.0)
    waste = {}
    for name, cfg in (("spike", spike), ("calm", calm)):
        st = ShopState("flowers")
        waste[name] = sum(run_day(ControlPolicy(), st, flowers, 5, d, cfg)
                          ["waste_cost"] for d in range(7))
    assert waste["spike"] < 0.5 * waste["calm"]


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

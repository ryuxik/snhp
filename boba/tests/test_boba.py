"""BOBA P0 tests: pairing is real, determinism holds, discount-only is
enforced, the queue/balk/batch physics work, and the cart arm's edges come
from the right drivers (peak slots, expiring batches, group carts)."""
import pytest

from boba.policies import (CartPolicy, ComputedMenu, StaticMenu, cart_nash,
                           pearls_expiring_excess, top_c_eff)
from boba.run import run_day, run_experiment
from boba.world import (BATCH_SERVINGS, PEAK_HOURS, PEARL_COST,
                        PEARL_RESTOCK_TRIGGER, QTY_CAP, TICKS_PER_DAY,
                        BobaConfig, Batch, Consumer, DRINK_PRICE, TOP_PRICE,
                        arrivals_at, balk_prob, best_menu_order, capacity_relief,
                        close_out, cook_batch, day_rate_mult, expected_wait_minutes,
                        expire_batches, hour_of, maybe_cook, open_shop,
                        sample_consumer, serve_queue, take_pearls)


def _rich_consumer(wtp_scale=1.4, flexible=False, decay=0.15, tops=1.4):
    """A hand-built buyer: values every drink at scale× its menu price and
    every topping likewise — deals exist wherever the engine allows them."""
    return Consumer(fav="classic-milk-tea",
                    wtp={d: p * wtp_scale for d, p in DRINK_PRICE.items()},
                    top_wtp={t: p * tops for t, p in TOP_PRICE.items()},
                    flexible=flexible, qty_decay=decay, uid=7)


# ── pairing & determinism ────────────────────────────────────────────────

def test_arrival_and_consumer_streams_are_policy_independent():
    """The treatment isolation guarantee: streams depend only on
    (seed, day, tick, k, cfg)."""
    assert [arrivals_at(7, 3, t) for t in range(TICKS_PER_DAY)] == \
           [arrivals_at(7, 3, t) for t in range(TICKS_PER_DAY)]
    c1 = sample_consumer(7, 3, 20, 0)
    c2 = sample_consumer(7, 3, 20, 0)
    assert (c1.fav, c1.wtp, c1.top_wtp, c1.flexible, c1.qty_decay, c1.uid) == \
           (c2.fav, c2.wtp, c2.top_wtp, c2.flexible, c2.qty_decay, c2.uid)
    c3 = sample_consumer(7, 3, 20, 1)
    assert c3.uid != c1.uid


def test_experiment_is_deterministic():
    r1 = run_experiment(["static", "computed", "cart"], days=2, seed=11)
    r2 = run_experiment(["static", "computed", "cart"], days=2, seed=11)
    assert r1 == r2


def test_day_shock_is_mean_one_and_deterministic():
    cfg = BobaConfig(sigma_shock=0.4)
    mults = [day_rate_mult(cfg, 42, d) for d in range(4000)]
    assert mults[7] == day_rate_mult(cfg, 42, 7)
    import numpy as np
    assert abs(np.mean(mults) - 1.0) < 0.03
    assert day_rate_mult(BobaConfig(), 42, 7) == 1.0


# ── queue / balk mechanics ───────────────────────────────────────────────

def test_balk_scales_with_expected_wait_and_caps():
    state = open_shop()
    state.tick = 60                          # 20:00 — one staff, 0.75/min
    assert balk_prob(state) == 0.0           # empty queue: nobody balks
    state.queue.append(3)                    # 4 minutes of work
    assert expected_wait_minutes(state) == pytest.approx(4.0)
    assert balk_prob(state) == pytest.approx(0.32)
    state.queue.append(27)                   # 40 minutes: certain balk
    assert balk_prob(state) == 1.0


def test_queue_serves_fifo_with_fractional_carry():
    state = open_shop()
    state.tick = 60                          # 0.75/min → 7.5 drinks/tick
    state.queue.extend([3, 30])
    assert serve_queue(state) == 7           # 3 then 4 of the group (FIFO)
    assert list(state.queue) == [26]
    assert state.carry == pytest.approx(0.5)
    assert serve_queue(state) == 8           # the half-drink carries over
    state.queue.clear()
    serve_queue(state)
    assert state.carry == 0.0                # idle capacity does not bank


# ── tapioca batches ──────────────────────────────────────────────────────

def test_batch_expiry_waste_is_charged_at_cost():
    state = open_shop()                      # batch 1 cooked at open
    take_pearls(state, 10)
    state.tick = 24                          # 4 hours later
    waste = expire_batches(state)
    assert waste == pytest.approx((BATCH_SERVINGS - 10) * PEARL_COST)
    assert state.pearl_stock() == 0
    cook_batch(state)
    take_pearls(state, 5)
    assert close_out(state) == pytest.approx((BATCH_SERVINGS - 5) * PEARL_COST)


def test_operator_cooks_when_pearls_run_low():
    state = open_shop()
    assert state.batches_cooked == 1         # batch 1 at open
    take_pearls(state, BATCH_SERVINGS - PEARL_RESTOCK_TRIGGER)
    maybe_cook(state)
    assert state.batches_cooked == 1         # at trigger: not yet
    take_pearls(state, 1)
    maybe_cook(state)
    assert state.batches_cooked == 2         # below trigger: cook
    with pytest.raises(ValueError):
        take_pearls(state, 10 * BATCH_SERVINGS)   # validates before mutating


def test_pearls_expiring_excess_flags_the_clearance_window():
    state = open_shop()
    state.tick = 20                          # batch 1 dies at tick 24
    assert pearls_expiring_excess(state)     # 40 servings, ~40 min left
    assert top_c_eff(state, "pearls") == 0.0     # free to move
    assert top_c_eff(state, "pudding") > 0.0     # others still cost
    take_pearls(state, BATCH_SERVINGS - 2)
    assert not pearls_expiring_excess(state)     # 2 left will sell anyway


# ── capacity relief (the pickup-slot logroll) ────────────────────────────

def test_peak_hours_pin():
    """Calibration guard: congestion concentrates in the pre-2pm lunch
    crunch (single staff); the second staffer absorbs the 15–18h spike."""
    assert PEAK_HOURS == (12, 13)


def test_capacity_relief_only_credited_at_peak_into_slack():
    state = open_shop()
    state.tick = 20                          # 13:20, deep in the crunch
    state.queue.append(12)                   # 16 min of backlog
    assert capacity_relief(state, 1, 6) > 0.0     # +60 lands 14:20 (2 staff)
    assert capacity_relief(state, 1, 3) == 0.0    # +30 lands 13:50: still peak
    assert capacity_relief(state, 1, 0) == 0.0    # now frees nothing
    state.tick = 60                          # 20:00, same queue, off-peak
    assert capacity_relief(state, 1, 6) == 0.0


# ── posted arms ──────────────────────────────────────────────────────────

def test_computed_never_exceeds_menu():
    for tick in (0, 15, 30, 45, 60, 66):
        policy = ComputedMenu()
        state = open_shop()
        state.tick = tick
        drinks, tops = policy.boards(state)
        assert all(drinks[d] <= DRINK_PRICE[d] + 1e-9 for d in drinks)
        assert all(tops[t] <= TOP_PRICE[t] + 1e-9 for t in tops)


def test_computed_discounts_the_evening_but_runout_holds_list():
    state = open_shop()
    state.tick = 66                          # 21:00 crowd (mult 0.85)
    drinks, _ = ComputedMenu().boards(state)
    assert any(drinks[d] < DRINK_PRICE[d] for d in drinks)
    jammed = open_shop()
    jammed.tick = 66
    jammed.queue.append(200)                 # the queue will eat every slot
    drinks_j, _ = ComputedMenu().boards(jammed)
    assert all(drinks_j[d] == DRINK_PRICE[d] for d in drinks_j)


# ── the cart arm ─────────────────────────────────────────────────────────

def test_cart_is_discount_only_and_beats_both_disagreements():
    """Every deal quoted over a live day: never above the cart's menu list
    value, shop never below its no-deal event, buyer never below theirs —
    'the cart arm beats the buyer's own sticker alternative when it
    deals' is structural."""
    policy = CartPolicy()
    state = open_shop()
    seen = 0
    for tick in range(0, TICKS_PER_DAY, 3):
        state.tick = tick
        for k in range(arrivals_at(23, 1, tick)):
            c = sample_consumer(23, 1, tick, k)
            deal = policy.quote_for(state, c)
            if deal is None:
                continue
            seen += 1
            assert deal.price <= deal.list_value + 1e-9
            assert deal.u_shop >= deal.d_shop + 0.25 - 1e-9   # buffer cleared
            assert deal.u_buyer >= deal.d_buyer - 1e-9
    assert seen > 20


def test_no_deal_when_the_sticker_is_already_optimal():
    """Event-consistent honesty: a rich buyer who takes the full-topping
    order at menu anyway leaves nothing to negotiate — the engine says so
    instead of forcing a deal."""
    state = open_shop()
    state.tick = 36                          # 16:00 — slack, b = 0
    assert cart_nash(state, _rich_consumer(wtp_scale=1.4, tops=1.4)) is None


def test_cart_upsell_concentrates_in_group_buyers():
    """The multi-unit logroll has teeth only where a 2nd cup is worth
    something: for a looker (below menu, above cost) the solo version deals
    one cup, the group version gets the 3-cup package."""
    state = open_shop()
    state.tick = 36                          # 16:00 — slack capacity
    solo = _rich_consumer(wtp_scale=0.85, tops=0.2, decay=0.15)
    group = _rich_consumer(wtp_scale=0.85, tops=0.2, decay=0.60)
    d_solo = cart_nash(state, solo)
    d_group = cart_nash(state, group)
    assert d_solo is not None and d_solo.qty == 1
    assert d_group is not None and d_group.qty == QTY_CAP


def test_cart_defers_flexible_buyers_out_of_the_crunch():
    """At a hot lunch queue the engine moves a flexible buyer to the +60
    slot (balk-free, capacity-relieving); the same buyer inflexible — or
    the same queue at a dead hour — stays 'now'."""
    state = open_shop()
    state.tick = 20                          # 13:20
    state.queue.append(12)                   # b ≈ 1.0
    flex = cart_nash(state, _rich_consumer(flexible=True))
    assert flex is not None and flex.slot_ticks == 6
    assert flex.relief > 0.0                 # the freed peak slots are paid for
    calm = open_shop()
    calm.tick = 60                           # 20:00, empty queue: deferring
    now = cart_nash(calm, _rich_consumer(   # buys nothing, costs the buyer
        wtp_scale=0.85, tops=0.2, flexible=True))
    assert now is not None and now.slot_ticks == 0


def test_deferred_orders_consume_capacity_at_their_slot():
    """A +30 booking is real work later: the drinks enter the FIFO queue at
    the slot tick and eat that tick's barista-minutes."""
    m = {"revenue": 0.0, "ingredient_cost": 0.0, "cups": 0, "toppings": 0,
         "deals": 0, "consumer_surplus": 0.0, "deferred": 0}
    from boba.run import _settle
    state = open_shop()
    state.tick = 10
    _settle(state, m, "classic-milk-tea", 2, (), 11.0, 1.0, slot_ticks=3)
    assert m["deferred"] == 1 and state.queue_drinks() == 0
    state.tick = 13
    from boba.world import release_scheduled
    release_scheduled(state)
    assert state.queue_drinks() == 2
    assert serve_queue(state) == 2


def test_flexible_share_is_the_knob_it_claims_to_be():
    all_flex = BobaConfig(flexible_share=1.0)
    none_flex = BobaConfig(flexible_share=0.0)
    cs = [sample_consumer(5, 0, 30, k, all_flex) for k in range(40)]
    assert all(c.flexible for c in cs)
    assert all(not sample_consumer(5, 0, 30, k, none_flex).flexible
               for k in range(40))
    assert cs[0].defer_cost(6) < Consumer(
        fav=cs[0].fav, wtp=cs[0].wtp, top_wtp=cs[0].top_wtp,
        flexible=False).defer_cost(6)


# ── end to end ───────────────────────────────────────────────────────────

def test_run_day_accounting_consistency():
    for arm in (StaticMenu(), CartPolicy()):
        m = run_day(arm, master_seed=5, day=0)
        assert m["deals"] <= m["arrivals"]
        assert m["cups"] >= m["deals"]
        assert m["margin"] == pytest.approx(
            m["revenue"] - m["ingredient_cost"] - m["waste_cost"], abs=0.02)
        assert m["balks"] >= m["peak_balks"] >= 0
        assert m["revenue"] >= 0 and m["consumer_surplus"] >= 0
        assert m["rent"] > 0                 # reported alongside, not netted


def test_static_lands_near_the_calibration_cups_target():
    """~260 cups/day (block/calibration.py BOBA_DAILY_CUPS) at the posted
    menu — the world is calibrated to the shop it claims to model."""
    import numpy as np
    cups = np.mean([run_day(StaticMenu(), 20260710, d)["cups"]
                    for d in range(4)])
    assert 230 <= cups <= 290


def test_committed_results_stay_reproducible():
    """boba/results.json must remain exactly reproducible at the config IT
    records (params read from the artifact, not hardcoded). One cell is
    enough to pin the whole pipeline."""
    import json
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "results.json"
    committed = json.load(open(path))
    cell = committed["cells"]["shock0_flex0.15"]
    cfg = BobaConfig(sigma_shock=cell["world"]["sigma_shock"],
                     flexible_share=cell["world"]["flexible_share"])
    res = run_experiment(committed["arms"], days=committed["days"],
                         seed=committed["seed"], cfg=cfg)
    for arm in committed["arms"]:
        assert res["arms"][arm]["totals"]["margin"] == cell["margin"][arm]

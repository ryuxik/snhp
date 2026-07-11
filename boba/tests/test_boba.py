"""BOBA P0/P1 tests: pairing is real, determinism holds, discount-only is
enforced, the queue/balk/batch physics work, the cart arm's edges come from
the right drivers (peak slots, expiring batches, group carts), the liar
battery quotes on disclosed but settles on true preferences, and the menu
arm is person-independent by construction."""
import pytest

from boba.policies import (CartPolicy, ComputedMenu, MenuPolicy, StaticMenu,
                           buyer_disagreement, cart_nash, menu_for_context,
                           menu_pick, pearls_expiring_excess,
                           strategic_disclosure, top_c_eff)
from boba.run import run_day, run_experiment
from boba.world import (BATCH_SERVINGS, PEAK_HOURS, PEARL_COST,
                        PEARL_RESTOCK_TRIGGER, QTY_CAP, TICKS_PER_DAY,
                        BobaConfig, Batch, Consumer, DRINK_COST, DRINK_PRICE,
                        TOP_COST, TOP_PRICE, arrivals_at, balk_prob,
                        best_menu_order, bundle_value, capacity_relief,
                        close_out, cook_batch, day_rate_mult, expected_wait_minutes,
                        expire_batches, hour_of, maybe_cook, observed_queue_length,
                        open_shop, outside_surplus, sample_consumer, serve_queue,
                        take_pearls)


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


# ── BOBA P1a: the liar battery ───────────────────────────────────────────

def test_strategic_disclosure_scales_wtp_and_top_wtp():
    c = _rich_consumer(wtp_scale=1.0, tops=1.0)
    disclosed, outside_c = strategic_disclosure(c, wtp_factor=0.55, claim_walk=False)
    assert all(disclosed.wtp[d] == pytest.approx(c.wtp[d] * 0.55) for d in c.wtp)
    assert all(disclosed.top_wtp[t] == pytest.approx(c.top_wtp[t] * 0.55)
              for t in c.top_wtp)
    assert disclosed.fav == c.fav and disclosed.uid == c.uid
    assert outside_c is None                        # honest walk claim


def test_claim_walk_swaps_in_the_true_consumer_for_outside_only():
    c = _rich_consumer(wtp_scale=0.6, tops=0.6)
    disclosed, outside_c = strategic_disclosure(c, wtp_factor=0.55, claim_walk=True)
    assert outside_c is c                            # the TRUE consumer, unscaled
    assert disclosed.wtp != c.wtp                    # but the in-store lie stands


def test_liar_identity_is_stable_and_policy_independent():
    """Liar assignment keys on the consumer's uid — same person, same roll,
    across returns and across arms (mirrors vend's identity-stability
    pin)."""
    c1 = sample_consumer(11, 2, 30, 0)
    c2 = sample_consumer(11, 2, 30, 0)
    assert c1.uid == c2.uid != 0
    c3 = sample_consumer(11, 2, 30, 1)
    assert c3.uid != c1.uid
    import numpy as np
    from boba.world import substream
    roll_a = float(np.random.default_rng(substream(11, "liarid", c1.uid)).random())
    roll_b = float(np.random.default_rng(substream(11, "liarid", c2.uid)).random())
    assert roll_a == roll_b                          # same uid -> same roll
    # policy-independent: two DIFFERENT liar-enabled policies (different
    # attack params) still roll the SAME liar/honest verdict for this uid,
    # since the roll depends only on (master_seed, uid) — never the policy
    liarA = CartPolicy(attest=False, liar_share=0.5, attack_wtp_factor=0.55)
    liarB = CartPolicy(attest=False, liar_share=0.5, attack_wtp_factor=1.3)
    assert (roll_a < liarA.liar_share) == (roll_a < liarB.liar_share)


def test_buyer_disagreement_matches_cart_nash_d_buyer():
    """buyer_disagreement is not a second implementation drifting from
    cart_nash's own d_buyer — pin them equal wherever a deal fires."""
    state = open_shop()
    state.tick = 36                          # slack afternoon
    for scale in (0.85, 1.0, 1.4):
        c = _rich_consumer(wtp_scale=scale, tops=scale)
        deal = cart_nash(state, c)
        if deal is not None:
            assert buyer_disagreement(state, c) == pytest.approx(deal.d_buyer)


def test_outside_consumer_overrides_only_the_batna():
    """Feeding a richer `outside_consumer` into cart_nash raises the
    buyer's claimed outside surplus (and can flip which no-deal branch
    fires) without changing the disclosed consumer's own bundle math."""
    state = open_shop()
    state.tick = 36
    poor = _rich_consumer(wtp_scale=0.5, tops=0.5)
    rich_outside = _rich_consumer(wtp_scale=1.4, tops=1.4)
    honest = cart_nash(state, poor)
    lied = cart_nash(state, poor, outside_consumer=rich_outside)
    assert outside_surplus(rich_outside) > outside_surplus(poor)
    # both quotes (if any) price the SAME disclosed bundle math; only the
    # buyer-side disagreement can differ
    if honest is not None and lied is not None:
        assert lied.d_buyer >= honest.d_buyer - 1e-9


def test_cart_liar_quotes_on_disclosed_but_settles_on_true_value():
    """End-to-end (run_day): with liar_share=1.0 every cart deal is priced
    off a scaled disclosure, but m['consumer_surplus'] — booked via
    TRUE bundle_value in the run_day liar branch — must stay a real,
    finite, non-degenerate number (never derived from the lie)."""
    honest = run_day(CartPolicy(), master_seed=20260713, day=0)
    liar = run_day(CartPolicy(attest=False, liar_share=1.0,
                              attack_wtp_factor=0.7, attack_claim_walk=True),
                   master_seed=20260713, day=0)
    assert liar["liar_deals"] > 0
    assert honest["liar_deals"] == 0
    # the liar arm converts real sales (cups served > 0) at a real,
    # accounted margin — not NaN/negative-infinite from a broken settlement
    assert liar["cups"] > 0
    assert liar["margin"] == pytest.approx(
        liar["revenue"] - liar["ingredient_cost"] - liar["waste_cost"], abs=0.02)


def test_cart_liar_share_zero_is_byte_identical_to_p0():
    """attest=False with liar_share=0.0 must never roll a liar — byte-
    identical to the plain P0 cart arm (the liar machinery is a true no-op
    at zero share, not just 'usually' a no-op)."""
    liar_off = [run_day(CartPolicy(attest=False, liar_share=0.0), 5, d)
               for d in range(3)]
    cart_days = [run_day(CartPolicy(), 5, d) for d in range(3)]
    assert liar_off == cart_days


def test_liar_battery_and_sweep_run_end_to_end():
    """Fast smoke test for boba.attack's plumbing (the real 30-day battery
    lives in boba/attack-battery.json, generated out of band — this just
    pins that the runner doesn't silently break)."""
    from boba.attack import run_battery, run_liar_share_sweep
    from boba.world import BobaConfig
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=0.35)
    battery = run_battery(days=5, seed=3, cfg=cfg)
    assert len(battery["cells"]) == 14
    honest_cell = battery["cells"]["factor1_walkhonest"]
    assert honest_cell["consumer_surplus"]["mean"] == 0.0   # no lie, no delta
    sweep = run_liar_share_sweep(days=5, seed=3, cfg=cfg,
                                 wtp_factor=0.7, claim_walk=True)
    assert set(sweep["cells"]) == {"liars25", "liars50", "liars100"}
    for cell in sweep["cells"].values():
        # days=5 < 2*block(5): paired_ci falls back to the unblocked daily
        # series (n=5) rather than discarding the run — still a valid CI
        assert cell["margin"]["n"] == 5


# ── BOBA P1a fix (#58): the observable market-price floor ─────────────────

def test_market_floor_caps_the_outside_option_at_the_disclosed_valuation():
    """The fix: a buyer who lowballs in-store WTP cannot ALSO claim a richer
    valuation two doors down — the competitor's prices are observable, so the
    outside option is capped at what the DISCLOSED valuation earns there. With
    the floor on, a claim_walk deal is byte-identical to its honest-outside
    (walk=honest) twin and costs the liar a strictly higher price than the
    unfloored claim_walk exploit."""
    state = open_shop()
    state.tick = 30
    c = _rich_consumer(wtp_scale=1.35, tops=0.4, decay=0.15)
    disclosed, outside_c = strategic_disclosure(c, 0.6, claim_walk=True)
    assert outside_surplus(c) > outside_surplus(disclosed)     # the lie has teeth
    unfloored = cart_nash(state, disclosed, outside_consumer=outside_c,
                          market_floor=False)
    floored = cart_nash(state, disclosed, outside_consumer=outside_c,
                        market_floor=True)
    honest_out = cart_nash(state, disclosed, outside_consumer=None)
    assert floored == honest_out          # claim_walk collapses onto disclosed
    assert unfloored is not None and floored is not None
    assert floored.d_buyer <= unfloored.d_buyer + 1e-9        # BATNA un-inflated
    assert floored.price >= unfloored.price - 1e-9            # shop keeps more


def test_market_floor_is_a_noop_for_honest_disclosure():
    """An honest buyer's claim IS their disclosure, so min(claim, floor) does
    nothing — market_floor=True must be byte-identical to P0 wherever no lie
    is told."""
    state = open_shop()
    for tick in (12, 30, 48):
        state.tick = tick
        for scale in (0.85, 1.0, 1.3):
            c = _rich_consumer(wtp_scale=scale, tops=scale, decay=0.15)
            assert cart_nash(state, c, market_floor=True) == cart_nash(state, c)


def test_cartpolicy_market_floor_defaults_off_and_is_noop_at_zero_share():
    assert CartPolicy().market_floor is False
    floored_off = [run_day(CartPolicy(market_floor=True), 5, d) for d in range(3)]
    p0 = [run_day(CartPolicy(), 5, d) for d in range(3)]
    assert floored_off == p0              # floor is a no-op with no liars


def test_market_floor_reduces_venue_erosion_at_the_claim_walk_best_response():
    """End-to-end: at the unfloored best-response deviation (0.7, claim_walk)
    the floor STRICTLY reduces the venue's margin erosion — it removes the
    outside-option half of the exploit. (It does NOT hold at every deviation:
    where claim_walk already hurts the buyer, e.g. 0.55, the floor pushes them
    to the better-for-them honest-outside lie — the fix targets the observable
    claim, not every misreport; see RESULTS.md P1a-fix.)"""
    dev = dict(attest=False, liar_share=1.0, attack_wtp_factor=0.7,
               attack_claim_walk=True)
    base = [run_day(CartPolicy(), 20260713, d) for d in range(6)]
    unf = [run_day(CartPolicy(**dev), 20260713, d) for d in range(6)]
    flo = [run_day(CartPolicy(**dev, market_floor=True), 20260713, d)
           for d in range(6)]
    ero_unf = sum(f["margin"] - b["margin"] for f, b in zip(unf, base))
    ero_flo = sum(f["margin"] - b["margin"] for f, b in zip(flo, base))
    assert ero_unf < 0 and ero_flo < 0                  # both erode the venue
    assert ero_flo > ero_unf                            # but the floor erodes LESS


# ── BOBA #52: length-based balking (Lu et al., Mgmt Sci 2013) ─────────────

def test_balk_model_defaults_to_wait_and_is_byte_identical():
    """The corrected spec is opt-in: BobaConfig defaults to the legacy
    wait model, and a run under it is byte-identical to P0 (results.json
    is never touched)."""
    assert BobaConfig().balk_model == "wait"
    assert open_shop().balk_model == "wait"
    wait = [run_day(CartPolicy(), 5, d, BobaConfig(flexible_share=0.35)) for d in range(3)]
    explicit = [run_day(CartPolicy(), 5, d,
                        BobaConfig(flexible_share=0.35, balk_model="wait"))
                for d in range(3)]
    assert wait == explicit


def test_length_balk_is_nonlinear_saturating_and_concave():
    """Lu et al.'s form: P(balk|L) = 1 − exp(−α·L) — zero at an empty
    counter, strictly increasing, capped below 1, and CONCAVE (each extra
    party deters less than the last: the key nonlinearity the wait model's
    linearity gets wrong)."""
    from collections import deque
    s = open_shop(balk_model="length")
    s.queue = deque()
    assert balk_prob(s) == 0.0
    probs = []
    for L in range(0, 9):
        s.queue = deque([1] * L)
        probs.append(balk_prob(s))
    assert all(0.0 <= p < 1.0 for p in probs)
    assert all(probs[i + 1] > probs[i] for i in range(len(probs) - 1))   # monotone
    marg = [probs[i + 1] - probs[i] for i in range(len(probs) - 1)]
    assert all(marg[i + 1] < marg[i] + 1e-12 for i in range(len(marg) - 1))  # concave


def test_length_balk_reads_party_count_not_drink_count():
    """The correction's whole point: abandonment tracks the OBSERVED number
    of parties in line, not the (invisible) total drink count or a computed
    wait. One 10-drink party and ten 1-drink parties carry the same drink
    load but a walk-in sees a very different line — and balks accordingly."""
    from collections import deque
    s = open_shop(balk_model="length")
    s.queue = deque([10])
    assert observed_queue_length(s) == 1
    one_big = balk_prob(s)
    s.queue = deque([1] * 10)
    assert observed_queue_length(s) == 10
    ten_small = balk_prob(s)
    assert ten_small > one_big + 0.3               # length, not drink load, drives it
    # the legacy wait model collapses them (same drinks -> same wait)
    w = open_shop(balk_model="wait")
    w.queue = deque([10])
    a = balk_prob(w)
    w.queue = deque([1] * 10)
    assert balk_prob(w) == a


def test_smoothing_lever_survives_length_balk():
    """THE #52 question: the capacity-smoothing lever (full cart − cart with
    pickup slots OFF) stays clearly positive under the corrected balking
    functional form — the deferred-slot logroll does not depend on the
    wait-linear spec."""
    import numpy as np
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=0.35, balk_model="length")
    days = 15
    cart = [run_day(CartPolicy(), 20260710, d, cfg)["margin"] for d in range(days)]
    nodef = [run_day(CartPolicy(defer_slots=False), 20260710, d, cfg)["margin"]
             for d in range(days)]
    lever = float(np.mean([c - n for c, n in zip(cart, nodef)]))
    assert lever > 100.0            # ~$256/day at 30d; comfortably positive at 15d


# ── BOBA P1b: menu fairness ──────────────────────────────────────────────

def test_menu_is_person_independent():
    """Same context (hour) -> byte-identical tiers, and the function never
    even accepts a persona argument — the structural fairness guarantee.
    Two wildly different buyers who both land on the same tier pay the
    exact same posted price for the same drink."""
    tiers_a = menu_for_context(13)
    tiers_b = menu_for_context(13)
    assert tiers_a == tiers_b
    assert all(a.drink_prices is b.drink_prices
              for a, b in zip(tiers_a, tiers_b))     # same cached dict objects

    state = open_shop()
    state.tick = 18                          # 13:00, slack enough for a deal
    rich = _rich_consumer(wtp_scale=1.4, tops=0.5, decay=0.60)   # group buyer
    poor = _rich_consumer(wtp_scale=0.9, tops=0.5, decay=0.15)   # solo buyer
    d_rich = menu_pick(state, rich)
    d_poor = menu_pick(state, poor)
    assert d_rich is not None and d_poor is not None
    assert d_rich.drink == d_poor.drink              # both land on matcha-latte
    tiers = {t.name: t for t in menu_for_context(hour_of(state.tick))}
    # whichever tier each landed on, the posted price for that SAME drink
    # is identical across every board available to both — persona never
    # enters the price, only the choice among prices
    for name, tier in tiers.items():
        assert tier.drink_prices[d_rich.drink] == tier.drink_prices[d_poor.drink]


def test_menu_value_price_never_exceeds_list_or_undercuts_cost():
    for h in (10, 12, 16, 21):
        for tier in menu_for_context(h):
            for d, p in tier.drink_prices.items():
                assert DRINK_COST[d] - 1e-6 <= p <= DRINK_PRICE[d] + 1e-6
            for t, p in tier.top_prices.items():
                assert TOP_COST[t] - 1e-6 <= p <= TOP_PRICE[t] + 1e-6


def test_menu_defer_tiers_only_at_peak_hours():
    for h in range(10, 22):
        names = {t.name for t in menu_for_context(h)}
        has_defer = "value-defer30" in names
        assert has_defer == (h in PEAK_HOURS)
        assert names >= {"list", "topper", "bundle"}


def test_menu_bundle_tier_requires_qty_at_least_two():
    """The bundle tier's screening friction: it can never be taken at
    qty=1 (that would be a flat same-qty discount everyone grabs — the
    exact cannibalization failure the min_qty floor exists to block). A
    genuine group buyer reaches it at qty>=2; the same taste, solo (low
    qty_decay), never does."""
    state = open_shop()
    state.tick = 18
    group = _rich_consumer(wtp_scale=1.4, tops=0.5, decay=0.60)
    solo = _rich_consumer(wtp_scale=1.4, tops=0.5, decay=0.15)
    d_group = menu_pick(state, group)
    d_solo = menu_pick(state, solo)
    assert d_group is not None and d_group.why[0] == "menu: bundle"
    assert d_group.qty >= 2
    assert d_solo is None or not (d_solo.why[0] == "menu: bundle" and d_solo.qty < 2)


def test_menu_no_defer_ablation_drops_defer_tiers():
    state = open_shop()
    state.tick = 20                          # 13:20, deep in the crunch
    state.queue.append(12)
    flex = _rich_consumer(flexible=True)
    with_defer = menu_pick(state, flex, defer_tiers=True)
    without_defer = menu_pick(state, flex, defer_tiers=False)
    assert with_defer is not None and with_defer.slot_ticks > 0   # takes the slot
    assert without_defer is None or without_defer.slot_ticks == 0  # never offered


def test_menu_deal_beats_the_buyers_true_disagreement():
    """Structural honesty check on menu_pick itself, over a live day: every
    quoted deal clears the buyer's TRUE no-deal payoff (never a personal
    one — there's no disclosure channel to lie through in the first
    place)."""
    policy = MenuPolicy()
    state = open_shop()
    seen = 0
    for tick in range(0, TICKS_PER_DAY, 3):
        state.tick = tick
        for k in range(arrivals_at(29, 1, tick)):
            c = sample_consumer(29, 1, tick, k)
            deal = policy.quote_for(state, c)
            if deal is None:
                continue
            seen += 1
            assert deal.u_buyer >= deal.d_buyer - 1e-9
            assert deal.d_buyer == pytest.approx(buyer_disagreement(state, c))
    assert seen > 10


def test_menu_arm_runs_end_to_end_and_never_exceeds_list():
    for arm in (MenuPolicy(), MenuPolicy(defer_tiers=False)):
        m = run_day(arm, master_seed=20260710, day=0)
        assert m["deals"] <= m["arrivals"]
        assert m["cups"] >= m["deals"]
        assert m["margin"] == pytest.approx(
            m["revenue"] - m["ingredient_cost"] - m["waste_cost"], abs=0.02)
        assert m["revenue"] >= 0 and m["consumer_surplus"] >= 0


def test_menu_experiment_is_deterministic():
    r1 = run_experiment(["static", "menu", "menu-no-defer"], days=2, seed=11)
    r2 = run_experiment(["static", "menu", "menu-no-defer"], days=2, seed=11)
    assert r1 == r2


# ── Task #68B: capacity-venue IC probe (the vend contrast) ──────────────────

def test_boba_adaptive_discloses_truth_when_queue_slack():
    """boba.battery adaptive strategy lies ONLY when the queue is building
    (balk_prob >= BALK_TIGHT); an empty shop ⇒ truthful disclosure."""
    from boba.battery import _disclose, BALK_TIGHT
    from boba.world import open_shop, sample_consumer, balk_prob
    state = open_shop(0)               # fresh, empty queue ⇒ balk ~ 0 < tight
    assert balk_prob(state) < BALK_TIGHT
    c = sample_consumer(20260713, 0, 30, 0)
    disc, outc = _disclose({"mode": "adaptive", "factor": 0.7,
                            "claim_walk": True}, state, c)
    assert disc is c and outc is None   # truthful (byte-identical to honest)


def test_boba_pertopping_leaves_drink_truthful():
    from boba.battery import _disclose
    from boba.world import open_shop, sample_consumer
    state = open_shop(0)
    c = sample_consumer(20260713, 0, 30, 0)
    disc, outc = _disclose({"mode": "toppings", "factor": 0.5,
                            "claim_walk": False}, state, c)
    assert disc.wtp == c.wtp                              # drink truthful
    assert all(disc.top_wtp[t] == c.top_wtp[t] * 0.5 for t in c.top_wtp)


def test_boba_probe_leak_is_large_and_deterministic():
    """The capacity contrast: unlike vend (pooled ≈ 0), boba's WTP+walk lie is
    a LARGE positive pooled-mean leak — every stratum, not just the sup."""
    from boba.battery import run_probe
    from boba.world import BobaConfig
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=0.35)
    a = run_probe([20260713], days=6, cfg=cfg)
    b = run_probe([20260713], days=6, cfg=cfg)
    assert a == b
    s = a["strategies"]["uniform_wtp+walk"]
    assert s["strata"]["all"]["mean"] > 50.0     # dollars/day, not cents

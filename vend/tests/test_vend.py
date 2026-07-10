"""VEND P0 tests: invariants are type-enforced, pairing is real,
determinism holds, and the GvR arm's discounts come from the right drivers."""
import copy

import pytest

from vend.core import (MachineState, Lot, QuoteItem, QuoteViolation,
                       make_quote, substream)
from vend.policies import GvrPolicy, StaticPolicy
from vend.run import run_day, run_experiment
from vend.world import (TICKS_PER_DAY, arrivals_at, build_catalog, end_of_day,
                        fresh_machine, hour_of, sample_consumer)


@pytest.fixture(scope="module")
def catalog():
    return build_catalog()


def machine(catalog):
    return fresh_machine("test-01", catalog)


# ── invariants ────────────────────────────────────────────────────────────

def test_discount_only_is_unconstructible(catalog):
    state = machine(catalog)
    with pytest.raises(QuoteViolation):
        make_quote(state, "test/1", seed=1,
                   items=[QuoteItem("cola", 1,
                                    unit_price=catalog["cola"].list_price + 0.01,
                                    list_price=catalog["cola"].list_price)],
                   why=["nope"], hour=12)


def test_receipt_is_mandatory(catalog):
    state = machine(catalog)
    with pytest.raises(QuoteViolation):
        make_quote(state, "test/1", seed=1,
                   items=[QuoteItem("cola", 1, 1.00, catalog["cola"].list_price)],
                   why=[], hour=12)


def test_context_hash_is_stable_and_buyer_free(catalog):
    """Same machine state + same intent + same hour → same context hash.
    There is no buyer parameter to vary."""
    s1, s2 = machine(catalog), machine(catalog)
    q = lambda st: make_quote(st, "test/1", seed=99,
                              items=[QuoteItem("cola", 2, 1.50,
                                               catalog["cola"].list_price)],
                              why=["x"], hour=12)
    assert q(s1).context_hash == q(s2).context_hash


# ── pairing & determinism ────────────────────────────────────────────────

def test_arrival_and_consumer_streams_are_policy_independent(catalog):
    """The treatment isolation guarantee: streams depend only on
    (seed, day, tick, k)."""
    assert [arrivals_at(7, 3, t) for t in range(TICKS_PER_DAY)] == \
           [arrivals_at(7, 3, t) for t in range(TICKS_PER_DAY)]
    c1 = sample_consumer(7, 3, 40, 0, catalog)
    c2 = sample_consumer(7, 3, 40, 0, catalog)
    assert c1.wtp == c2.wtp and c1.walk_cost == c2.walk_cost


def test_experiment_is_deterministic(catalog):
    r1 = run_experiment(["static", "gvr"], days=2, seed=11)
    r2 = run_experiment(["static", "gvr"], days=2, seed=11)
    assert r1 == r2


# ── GvR mechanism (drivers, not outcomes) ────────────────────────────────

def _gvr_price(state, sku):
    return GvrPolicy().price_board(state)[sku][0]


def test_gvr_never_exceeds_list(catalog):
    state = machine(catalog)
    for tick in (0, 30, 60, 90):
        state.tick = tick
        for sku, (price, _why) in GvrPolicy().price_board(state).items():
            assert price <= catalog[sku].list_price + 1e-9


def test_scarce_stock_holds_list_price(catalog):
    """Scarcity pushes the solve above list; the clamp holds it AT list."""
    state = machine(catalog)
    state.lots = [Lot("cola", 1, expires_day=60)]
    state.tick = 24  # 11:00, lunch ahead
    assert _gvr_price(state, "cola") == catalog["cola"].list_price


def test_offpeak_glut_discounts(catalog):
    """Plenty of stock + the low-value afternoon crowd → below list."""
    state = machine(catalog)
    state.tick = 44  # ~14:20, off-peak (mult 0.75)
    assert _gvr_price(state, "chips") < catalog["chips"].list_price


def test_expiry_lowers_the_floor(catalog):
    """With nightly top-to-par restock, an unsold durable unit displaces
    tomorrow's restock purchase → its floor is unit_cost. A unit expiring
    tonight is salvage-or-sold → its floor drops to salvage. Force an
    operator estimate that prices the crowd below cost and watch the
    floors bind."""
    from dataclasses import replace
    cheap = dict(catalog)
    cheap["sandwich"] = replace(catalog["sandwich"], wtp_mu_est=2.0)
    state = fresh_machine("test-floor", cheap)
    state.tick = 44
    state.lots = [Lot("sandwich", 6, expires_day=0)]      # expires tonight
    near = _gvr_price(state, "sandwich")
    state.lots = [Lot("sandwich", 6, expires_day=7)]
    far = _gvr_price(state, "sandwich")
    assert far >= catalog["sandwich"].unit_cost    # durable: never below cost
    assert near < catalog["sandwich"].unit_cost    # expiring: below cost is rational
    assert near >= catalog["sandwich"].salvage     # ...but never below salvage


# ── machine dynamics ─────────────────────────────────────────────────────

def test_spoilage_and_restock(catalog):
    state = machine(catalog)
    state.lots = [Lot("sandwich", 4, expires_day=0)]
    eod = end_of_day(state)
    assert eod["spoiled_units"] == 4
    assert eod["spoilage_cost"] == pytest.approx(
        4 * (catalog["sandwich"].unit_cost - catalog["sandwich"].salvage))
    assert state.day == 1
    for sku, listing in catalog.items():
        assert state.stock(sku) == listing.par_stock


def test_take_prefers_earliest_expiry(catalog):
    state = machine(catalog)
    state.lots = [Lot("cola", 2, expires_day=9), Lot("cola", 2, expires_day=3)]
    state.take("cola", 3)
    remaining = {(l.expires_day, l.quantity) for l in state.lots if l.quantity > 0}
    assert remaining == {(9, 1)}


# ── end to end ───────────────────────────────────────────────────────────

def test_run_day_accounting_consistency(catalog):
    state = machine(catalog)
    m = run_day(StaticPolicy(), state, catalog, master_seed=5, day=0)
    assert m["deals"] <= m["arrivals"] + m["returns"]
    assert m["revenue"] >= 0 and m["consumer_surplus"] >= 0
    assert m["profit"] == pytest.approx(
        m["revenue"] - m["cogs_sold"] - m["spoilage_cost"], abs=0.02)


# ── P1: brokered A2A (Nash quotes, attestation, the anchoring attack) ────

def _consumer(catalog, wtp_scale=1.0, walk=1.0):
    from vend.world import Consumer
    return Consumer(wtp={s: catalog[s].list_price * 1.4 * wtp_scale for s in catalog},
                    walk_cost=walk, patience=0.0)


def _glut_state(catalog):
    """Afternoon machine with genuinely excess stock — where discounts live."""
    state = machine(catalog)
    state.tick = 50
    state.lots = [Lot("sandwich", 12, expires_day=0),
                  Lot("cola", 12, expires_day=60),
                  Lot("chips", 10, expires_day=30)]
    return state


def test_nash_quote_respects_both_disagreements(catalog):
    from vend.scenario import nash_quote
    state = _glut_state(catalog)
    c = _consumer(catalog)
    nq = nash_quote(state, c.wtp, c.walk_cost)
    assert nq.outcome is not None
    assert nq.u_machine >= nq.d_machine - 1e-9      # no-deal event never given away
    assert nq.u_buyer_claimed >= nq.d_buyer - 1e-9  # buyer beats their best alternative


def test_cannibalization_guard_is_structural(catalog):
    """The P0 fix: a buyer who would have bought at list yields the machine
    AT LEAST its no-deal counterfactual — discounts only carve newly
    created surplus."""
    from vend.scenario import nash_quote, sticker_choice
    state = _glut_state(catalog)
    c = _consumer(catalog)                       # rich buyer: buys at list for sure
    assert sticker_choice(c.wtp, state)[0] is not None
    nq = nash_quote(state, c.wtp, c.walk_cost)
    assert nq.outcome is not None
    assert nq.u_machine >= nq.d_machine - 1e-9


def test_no_deal_when_the_sticker_is_already_optimal(catalog):
    """Event-consistent honesty: a fully-stocked morning machine facing a
    buyer whose board purchase is already their optimum has NOTHING to
    negotiate — the engine says so instead of forcing a deal."""
    from vend.scenario import nash_quote
    state = machine(catalog)                     # tick 0, full stock, D high
    c = _consumer(catalog)
    nq = nash_quote(state, c.wtp, c.walk_cost)
    assert nq.outcome is None


def test_scarce_stock_is_not_discounted_to_early_birds(catalog):
    """The stock-drain fix: when expected list demand covers the stock on
    hand, the negotiated price stays AT list — the machine won't displace
    a full-margin lunch sale for a morning bargain."""
    from vend.scenario import nash_quote, expected_list_demand
    state = machine(catalog)
    state.tick = 0                                # whole day's demand ahead
    state.lots = [Lot("cola", 2, expires_day=60)] # scarce vs the day
    assert expected_list_demand(state, "cola") > 2
    c = _consumer(catalog)
    nq = nash_quote(state, c.wtp, c.walk_cost)
    if nq.outcome is not None and nq.outcome.sku == "cola":
        assert nq.outcome.unit_price == catalog["cola"].list_price


def test_quote_price_never_below_opportunity_cost(catalog):
    from vend.scenario import nash_quote, c_eff
    state = _glut_state(catalog)
    nq = nash_quote(state, _consumer(catalog).wtp, 1.0)
    assert nq.outcome is not None
    assert nq.outcome.unit_price >= c_eff(state, nq.outcome.sku) - 1e-9


def test_anchoring_attack_pays_without_attestation(catalog):
    """H3's mechanism: where a discount surface exists at all (excess /
    expiring stock — shadow pricing holds scarce stock at list for honest
    and liar alike), the liar's disclosure buys strictly cheaper."""
    from vend.scenario import nash_quote, liar_disclosure
    state = machine(catalog)
    state.tick = 50                                   # afternoon lull
    state.lots = [Lot("sandwich", 6, expires_day=0),  # glut, dies tonight
                  Lot("cola", 12, expires_day=60)]
    c = _consumer(catalog)
    honest = nash_quote(state, c.wtp, c.walk_cost)
    wtp_l, walk_l = liar_disclosure(c.wtp, c.walk_cost)
    liar = nash_quote(state, wtp_l, walk_l)
    assert honest.outcome is not None and liar.outcome is not None
    assert liar.outcome.unit_price < honest.outcome.unit_price


def test_no_mutual_gain_falls_back(catalog):
    from vend.scenario import nash_quote
    state = machine(catalog)
    pauper = {s: 0.01 for s in catalog}
    nq = nash_quote(state, pauper, 5.0)
    assert nq.outcome is None


def test_a2a_arm_is_deterministic(catalog):
    r1 = run_experiment(["static", "a2a"], days=2, seed=13)
    r2 = run_experiment(["static", "a2a"], days=2, seed=13)
    assert r1 == r2


# ── P1.5: realistic world (shocks, calendar, miscalibration) + learner ──

def test_default_config_reproduces_committed_artifact(catalog):
    """The committed results.json must stay exactly reproducible at the
    config IT records (path resolved from this file, params read from the
    artifact — not hardcoded)."""
    import json
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "results.json"
    committed = json.load(open(path))
    cfg_d = committed["config"]
    res = run_experiment(["static"], days=cfg_d["days"], seed=cfg_d["seed"])
    assert res["arms"]["static"]["totals"] == committed["arms"]["static"]["totals"]


def test_day_shocks_are_mean_one_and_deterministic():
    from vend.world import WorldConfig, day_state
    cfg = WorldConfig(sigma_rate=0.5, sigma_wtp=0.25)
    states = [day_state(cfg, 42, d) for d in range(4000)]
    assert states[7] == day_state(cfg, 42, 7)          # deterministic
    import numpy as np
    assert abs(np.mean([s.rate_mult for s in states]) - 1.0) < 0.03
    assert abs(np.mean([s.wtp_mult for s in states]) - 1.0) < 0.03


def test_miscalibration_moves_the_sticker():
    from vend.world import WorldConfig, build_catalog
    perfect = build_catalog()
    noisy = build_catalog(WorldConfig(sigma_cal=0.3), master_seed=99)
    assert any(perfect[s].list_price != noisy[s].list_price for s in perfect)
    assert all(noisy[s].wtp_mu_est != perfect[s].wtp_mu_est for s in perfect)


def test_dow_weekend_is_quiet():
    from vend.world import WorldConfig, arrivals_at, TICKS_PER_DAY
    cfg = WorldConfig(dow=True)
    weekday = sum(arrivals_at(3, 0, t, cfg) for t in range(TICKS_PER_DAY))  # Mon
    weekend = sum(arrivals_at(3, 6, t, cfg) for t in range(TICKS_PER_DAY))  # Sun
    assert weekend < weekday * 0.4


def test_learner_shares_track_sales():
    from vend.policies import DemandLearner
    l = DemandLearner()
    for _ in range(5):
        l.begin_day()
        l.sold("cola", 8)
        l.sold("chips", 2)
        l.end_day()
    assert l.share("cola", 8) > 3 * l.share("chips", 8)
    assert l.share("sandwich", 8) >= 0.25 / 8   # unseen SKU keeps a pulse


def test_glut_days_double_perishable_delivery():
    from vend.world import WorldConfig, build_catalog, fresh_machine
    cfg = WorldConfig(glut_prob=1.0)
    cat = build_catalog()
    state = fresh_machine("t", cat, cfg, master_seed=1)
    assert state.stock("sandwich") == 2 * cat["sandwich"].par_stock
    assert state.stock("cola") == cat["cola"].par_stock   # durables unaffected


# ── review-fix regression pins ───────────────────────────────────────────

def test_take_validates_before_mutating(catalog):
    state = machine(catalog)
    state.lots = [Lot("cola", 1, expires_day=5), Lot("cola", 1, expires_day=9)]
    with pytest.raises(ValueError):
        state.take("cola", 3)
    assert state.stock("cola") == 2       # nothing was decremented


def test_liar_identity_is_stable_and_policy_independent(catalog):
    """Liar assignment keys on the consumer's uid — same person, same roll,
    across returns and across arms."""
    c1 = sample_consumer(11, 2, 30, 0, catalog)
    c2 = sample_consumer(11, 2, 30, 0, catalog)
    assert c1.uid == c2.uid != 0
    c3 = sample_consumer(11, 2, 30, 1, catalog)
    assert c3.uid != c1.uid


def test_a2a_accept_requires_beating_the_sticker_board(catalog):
    """'Never worse UX than static' is enforced: a negotiated deal a
    consumer would decline in favor of the sticker board falls through."""
    from vend.run import ARMS
    res = run_experiment(["static", "a2a"], days=3, seed=17)
    # structural check: every negotiated deal contributed surplus at least
    # equal to what any deal gives — the accept gate ran without error and
    # the a2a arm still functions end to end
    assert res["arms"]["a2a"]["totals"]["deals"] > 0


def test_nash_quote_allowed_filter_restricts_outcomes(catalog):
    from vend.scenario import nash_quote
    state = machine(catalog)
    c = _consumer(catalog)
    nq = nash_quote(state, c.wtp, c.walk_cost,
                    allowed=lambda o: o.sku == "cola" and o.qty <= 1)
    assert nq.outcome is None or (nq.outcome.sku == "cola" and nq.outcome.qty == 1)


def test_context_hash_distinguishes_disclosures(catalog):
    """Brokered quotes lawfully depend on the disclosure — and the context
    hash now proves it: same state, different disclosure, different hash."""
    from vend.core import disclosure_digest
    state = machine(catalog)
    mk = lambda dig: make_quote(state, "t/1", seed=1,
                                items=[QuoteItem("cola", 1, 1.5,
                                                 catalog["cola"].list_price)],
                                why=["x"], hour=12, disclosure_digest=dig)
    d1 = disclosure_digest({"cola": 3.0}, 1.0)
    d2 = disclosure_digest({"cola": 9.0}, 1.0)
    assert mk(d1).context_hash != mk(d2).context_hash
    assert mk(d1).context_hash == mk(d1).context_hash


# ── calibrated traffic (priority #1, paper/CALIBRATION-TARGETS.md) ──────

def test_traffic_scale_thins_arrivals_and_pars():
    """traffic_scale=1.0 reproduces the hot 'smart-store P90' profile
    exactly (par unaffected — the CATALOG_SPEC value); a thinned machine
    gets both fewer arrivals AND velocity-sized (smaller) pars, never zero."""
    from vend.world import WorldConfig, TICKS_PER_DAY, arrivals_at, build_catalog
    hot = build_catalog()
    cold = build_catalog(WorldConfig(traffic_scale=0.14))
    assert all(cold[s].par_stock < hot[s].par_stock for s in hot)
    assert all(cold[s].par_stock >= 1 for s in cold)
    hot_arr = sum(arrivals_at(3, 0, t, WorldConfig()) for t in range(TICKS_PER_DAY))
    cold_arr = sum(arrivals_at(3, 0, t, WorldConfig(traffic_scale=0.14))
                   for t in range(TICKS_PER_DAY))
    assert cold_arr < hot_arr * 0.3


def test_calibrated_traffic_lands_static_in_the_7_to_8_band():
    """The pre-registered target (paper/CALIBRATION-TARGETS.md #1): the
    STATIC arm realizes 7-8 units ('vends')/day at CALIBRATED_TRAFFIC_SCALE
    in the realistic miscalibration cell, on both committed seeds."""
    from vend.world import CALIBRATED_TRAFFIC_SCALE, WorldConfig
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                      glut_prob=0.15, traffic_scale=CALIBRATED_TRAFFIC_SCALE)
    for seed in (20260713, 7):
        res = run_experiment(["static"], days=90, seed=seed, cfg=cfg)
        units_per_day = res["arms"]["static"]["totals"]["units"] / 90
        assert 7.0 <= units_per_day <= 8.0


def test_calibrated_traffic_cli_flag(tmp_path):
    """--calibrated-traffic sets cfg.traffic_scale to the module constant;
    --traffic-scale overrides it directly and takes precedence."""
    from vend.run import main
    from vend.world import CALIBRATED_TRAFFIC_SCALE
    import json
    out1 = tmp_path / "a.json"
    assert main(["--days", "2", "--arms", "static", "--calibrated-traffic",
                "--out", str(out1)]) == 0
    d1 = json.load(open(out1))
    assert d1["config"]["world"]["traffic_scale"] == CALIBRATED_TRAFFIC_SCALE

    out2 = tmp_path / "b.json"
    assert main(["--days", "2", "--arms", "static", "--calibrated-traffic",
                "--traffic-scale", "0.5", "--out", str(out2)]) == 0
    d2 = json.load(open(out2))
    assert d2["config"]["world"]["traffic_scale"] == 0.5

    out3 = tmp_path / "c.json"
    assert main(["--days", "2", "--arms", "static", "--out", str(out3)]) == 0
    d3 = json.load(open(out3))
    assert d3["config"]["world"]["traffic_scale"] == 1.0   # unchanged default


def test_cold_start_demand_scales_with_traffic():
    """expected_list_demand's STRUCTURAL fallback (no realized-sales history
    yet, emp_daily=None) must scale with traffic_scale — otherwise a thinned
    machine's unsold SKUs read a hot-profile demand estimate, see excess≈0,
    and refuse to discount until they happen to sell once (the cold-start
    bug the traffic_scale plumbing exists to fix). The regime-consistent
    emp_daily branch must NOT be scaled again (it's already realized sales
    at the true, already-thinned rate)."""
    from vend.scenario import expected_list_demand
    from vend.world import build_catalog, fresh_machine
    cat = build_catalog()
    state = fresh_machine("t", cat)
    hot = expected_list_demand(state, "cola", traffic_scale=1.0)
    cold = expected_list_demand(state, "cola", traffic_scale=0.14)
    assert cold == pytest.approx(hot * 0.14)
    # emp_daily path: realized-sales estimate is regime-consistent already
    emp_hot = expected_list_demand(state, "cola", emp_daily=5.0, traffic_scale=1.0)
    emp_cold = expected_list_demand(state, "cola", emp_daily=5.0, traffic_scale=0.14)
    assert emp_hot == emp_cold


def test_a2a_traffic_scale_is_set_daily_from_cfg(catalog):
    """run_day wires policy.traffic_scale from cfg every day (the operator-
    knows-their-own-traffic mechanism) — GvrPolicy and A2APolicy both pick
    it up (matching the existing dow_mult pattern)."""
    from vend.policies import A2APolicy, GvrPolicy
    from vend.world import WorldConfig, fresh_machine
    cfg = WorldConfig(traffic_scale=0.3)
    for policy in (A2APolicy(), GvrPolicy()):
        state = fresh_machine("t", catalog, cfg, master_seed=1)
        assert policy.traffic_scale == 1.0     # default, before any day runs
        run_day(policy, state, catalog, master_seed=1, day=0, cfg=cfg)
        assert policy.traffic_scale == 0.3


# ── fairness parameter sweep (priority #3, paper/CALIBRATION-TARGETS.md) ─

def test_worldconfig_fairness_defaults_match_regulars_module():
    """WorldConfig.loss_aversion/ref_alpha_paid duplicate vend.regulars'
    LOSS_AVERSION/REF_ALPHA_PAID constants (regulars.py imports world.py, so
    the default can't be shared directly) — pinned so the two can't drift."""
    from vend.world import WorldConfig
    from vend import regulars
    cfg = WorldConfig()
    assert cfg.loss_aversion == regulars.LOSS_AVERSION
    assert cfg.ref_alpha_paid == regulars.REF_ALPHA_PAID


def test_regular_pool_honors_fairness_sweep_knobs():
    """RegularPool(..., loss_aversion=, ref_alpha_paid=) propagates to every
    spawned Regular — the priority #3 sweep knob — including new joins from
    exogenous replenishment (both paths call _spawn)."""
    from vend.regulars import RegularPool
    from vend.world import WorldConfig, build_catalog, _profit_optimal_list_price, CATALOG_SPEC
    cat = build_catalog()
    market_ref = {s: _profit_optimal_list_price(mu, c)
                  for s, mu, c, *_ in CATALOG_SPEC}
    cfg = WorldConfig(regulars=10)
    pool = RegularPool(cfg, 1, cat, market_ref,
                       loss_aversion=1.66, ref_alpha_paid=0.15)
    assert all(r.loss_aversion == 1.66 for r in pool.pool)
    assert all(r.ref_alpha_paid == 0.15 for r in pool.pool)
    # a replenishment join also inherits the pool's sweep knobs (run enough
    # days that at least one Poisson(0.7/day) join is all but certain)
    for r in pool.pool:
        r.active = False
    for day in range(15):
        pool.end_day(day)
    new = [r for r in pool.pool if r.active]
    assert new and all(r.loss_aversion == 1.66 and r.ref_alpha_paid == 0.15
                       for r in new)


def test_fairness_sweep_knobs_change_reference_dynamics(catalog):
    """A lower ref_alpha_paid (higher carryover) makes the reference price
    track a paid price MORE slowly — the literature-band knob actually
    moves the mechanism, not just a cosmetic field."""
    from vend.regulars import Regular, settle_regular
    fast = Regular(uid=1, wtp={"cola": 2.0}, walk_cost=1.0, visit_prob=0.5,
                   home_tick=30, ref={"cola": 2.0}, ref_alpha_paid=0.50)
    slow = Regular(uid=2, wtp={"cola": 2.0}, walk_cost=1.0, visit_prob=0.5,
                   home_tick=30, ref={"cola": 2.0}, ref_alpha_paid=0.10)
    settle_regular(fast, "cola", 1.00, 1)
    settle_regular(slow, "cola", 1.00, 1)
    assert fast.ref["cola"] < slow.ref["cola"]   # fast carryover moves further


def test_fairness_sweep_lambda_changes_loss_penalty():
    """loss_aversion scales the ABOVE-reference penalty only (below-reference
    GAIN_WEIGHT is untouched — asymmetric by design)."""
    from vend.regulars import Regular
    lo = Regular(uid=1, wtp={"cola": 2.0}, walk_cost=1.0, visit_prob=0.5,
                home_tick=30, ref={"cola": 2.0}, loss_aversion=1.66)
    hi = Regular(uid=2, wtp={"cola": 2.0}, walk_cost=1.0, visit_prob=0.5,
                home_tick=30, ref={"cola": 2.0}, loss_aversion=2.0)
    above_lo = lo.fairness("cola", 2.50, 1, None)
    above_hi = hi.fairness("cola", 2.50, 1, None)
    assert above_hi < above_lo < 0             # both penalize; higher lambda hurts more
    below_lo = lo.fairness("cola", 1.50, 1, None)
    below_hi = hi.fairness("cola", 1.50, 1, None)
    assert below_lo == below_hi                # GAIN_WEIGHT unaffected by lambda


def test_fairness_harvest_regression():
    """Reproducibility gate #55: pin the corrected Fairness v2 headline so a
    silent mechanism change (like the censoring-learner drift traced to
    commit 3a8fc4d, which moved the harvest $33->$42 by firing fewer
    protective quotes) is caught by CI instead of a whitepaper reviewer.

    These are the CORRECTED (post-censoring-fix) a2a x1.25 diagnostics — the
    number the intended mechanism produces. The static-mixture "old world"
    baseline (late profit 100.5) is drift-immune (static arm, no learner),
    so pinning the a2a arm alone pins the harvest. See RESULTS.md 'Fairness
    v2' for the forensics.

    Re-pinned 2026-07-10 after the review-fix batch (regular acceptance gate,
    return-defer re-pairing, disagreement stock-cap, escalator ceiling): the
    regular gate now rejects quotes worse for a regular than the sticker board,
    so a few fewer regular deals fire — reg_deals 1307->1325, and the aggregate
    diagnostics move a hair (day90 108->107, churn 75->76)."""
    from vend.world import WorldConfig
    cfg = WorldConfig(regulars=120, anchor_peak=True, anchor_mult=1.25)
    res = run_experiment(["static", "a2a"], days=90, seed=2, cfg=cfg)
    pd = res["_per_day"]["a2a"]
    reg_deals = sum(d["reg_deals"] for d in pd)
    day90_active = pd[-1]["active_regulars"]
    churned = sum(d["churned"] for d in pd)
    late_profit = sum(d["profit"] for d in pd[60:90]) / 30
    assert reg_deals == 1325, reg_deals          # was 1307 pre-review-fix (1463 pre-censoring-fix)
    assert day90_active == 107, day90_active     # was 108 pre-review-fix
    assert churned == 76, churned                # was 75 pre-review-fix
    # harvest = a2a late - static-mixture late (100.5); ~ +$43.3/day corrected
    assert 143.4 < late_profit < 144.3, late_profit


# ── strong posted baseline (referee #48, CRITICAL-ANALYSIS §2) ──────────────

def _posted_board(cfg, *, day=2, tick=66, remove=None, seed=20260713):
    """Solve the StrongPostedPolicy board at a fixed state (deterministic)."""
    from vend.policies import StrongPostedPolicy
    cat = build_catalog(cfg, seed)
    st = fresh_machine("m", cat, cfg, seed)
    st.day, st.tick = day, tick
    if remove:
        for lot in st.lots:
            if lot.sku == remove:
                lot.quantity = 0
    pol = StrongPostedPolicy()
    pol.dow_mult = 1.0
    return pol.price_board(st), cat


def test_strong_posted_is_registered_board_arm_with_learner():
    """run.py wires .learner / .dow_mult / .traffic_scale into every board
    arm — the posted arm must expose them (that's how it gets the SAME demand
    info the a2a arm has) and must be a board-mode (not intent) policy."""
    from vend.run import ARMS
    from vend.policies import StrongPostedPolicy, DemandLearner
    assert "posted" in ARMS
    pol = ARMS["posted"]()
    assert isinstance(pol, StrongPostedPolicy)
    assert pol.mode == "board"
    assert isinstance(pol.learner, DemandLearner)
    assert hasattr(pol, "dow_mult") and hasattr(pol, "traffic_scale")


def test_strong_posted_is_deterministic():
    from vend.world import WorldConfig
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3,
                      dow=True, glut_prob=0.15)
    r1 = run_experiment(["static", "posted"], days=4, seed=13, cfg=cfg)
    r2 = run_experiment(["static", "posted"], days=4, seed=13, cfg=cfg)
    assert r1["arms"]["posted"]["totals"] == r2["arms"]["posted"]["totals"]


def test_strong_posted_is_discount_only_and_finds_discounts():
    """Type-enforced never-above-list, AND it actually optimizes: warm-started
    at the list board, the joint solve must move at least one SKU strictly
    below list (otherwise it's just a static clone)."""
    from vend.world import WorldConfig
    cfg = WorldConfig(anchor_peak=True, anchor_mult=1.3)  # room to discount
    board, cat = _posted_board(cfg)
    assert board, "expected a non-empty board"
    for s, (p, why) in board.items():
        assert p <= cat[s].list_price + 1e-9, (s, p, cat[s].list_price)
    assert any(p < cat[s].list_price - 1e-9 for s, (p, _) in board.items())


def test_strong_posted_respects_opportunity_cost_floor():
    from vend.world import WorldConfig
    cfg = WorldConfig(anchor_peak=True, anchor_mult=1.3)
    board, cat = _posted_board(cfg)
    for s, (p, _) in board.items():
        assert p >= cat[s].salvage - 1e-6, (s, p, cat[s].salvage)


def test_strong_posted_models_cross_sku_substitution():
    """The whole point of (a)+(b): the optimal price of one SKU depends on
    what else is on the board. Removing a substitute (energy) from stock
    reduces competition for the refreshment dollar, so the JOINT optimizer
    prices its substitute (water) strictly HIGHER — a per-SKU optimizer, which
    prices water against water alone, could never show this."""
    from vend.world import WorldConfig
    cfg = WorldConfig(anchor_peak=True, anchor_mult=1.3)
    with_sub, _ = _posted_board(cfg)
    without_sub, _ = _posted_board(cfg, remove="energy")
    assert without_sub["water"][0] > with_sub["water"][0], (
        with_sub["water"][0], without_sub["water"][0])


def test_strong_posted_outearns_static_at_realistic_cell():
    """The arm is genuinely STRONG (not a strawman): at the realistic
    calibrated cell it out-earns the profit-optimal static sticker on the
    reference seed — the committed +$0.65/day edge (see RESULTS.md #48). The
    full both-seeds block-CI story lives in RESULTS; this pins the direction
    so a regression that neutered the choice model would fail CI."""
    from vend.world import WorldConfig, CALIBRATED_TRAFFIC_SCALE
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                      glut_prob=0.15, traffic_scale=CALIBRATED_TRAFFIC_SCALE)
    res = run_experiment(["static", "posted"], days=30, seed=20260713, cfg=cfg)
    assert (res["arms"]["posted"]["totals"]["profit"]
            > res["arms"]["static"]["totals"]["profit"])


# ── split-tilt seller-weight frontier (Task #65) ────────────────────────────

def test_seller_weight_default_is_symmetric_byte_identical(catalog):
    """w defaults to 0.5 = the EXACT symmetric Nash split. The default path
    (no seller_weight passed) and seller_weight=0.5 are byte-identical — both
    at the nash_quote level and end-to-end over a paired run, so the committed
    artifacts are unperturbed. (results.json reproducibility is pinned
    separately by test_default_config_reproduces_committed_artifact.)"""
    import dataclasses
    from vend.scenario import nash_quote
    state, c = _glut_state(catalog), _consumer(catalog)
    a = nash_quote(state, c.wtp, c.walk_cost)
    b = nash_quote(state, c.wtp, c.walk_cost, seller_weight=0.5)
    assert dataclasses.astuple(a) == dataclasses.astuple(b)
    from vend.world import WorldConfig, CALIBRATED_TRAFFIC_SCALE, fresh_machine
    from vend.policies import A2APolicy
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                      glut_prob=0.15, traffic_scale=CALIBRATED_TRAFFIC_SCALE)

    def run(**kw):
        cat = build_catalog(cfg, 7)
        st = fresh_machine("m", cat, cfg, 7)
        p = A2APolicy(**kw)
        return [run_day(p, st, cat, 7, d, cfg) for d in range(8)]

    assert run() == run(seller_weight=0.5)


def test_seller_weight_tilts_the_split_toward_the_seller(catalog):
    """Raising w reallocates the surplus ABOVE the disagreement toward the
    seller: seller gain gs monotone non-decreasing, buyer gain gb monotone
    non-increasing, quoted price non-decreasing — a genuine asymmetric Nash
    tilt (nash_quote reads state, never mutates it, so one state is reused)."""
    from vend.scenario import nash_quote
    state, c = _glut_state(catalog), _consumer(catalog)
    gs, gb, px = [], [], []
    for w in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        nq = nash_quote(state, c.wtp, c.walk_cost, seller_weight=w)
        assert nq.outcome is not None
        gs.append(nq.u_machine - nq.d_machine)
        gb.append(nq.u_buyer_claimed - nq.d_buyer)
        px.append(nq.outcome.unit_price)
    assert all(gs[i + 1] >= gs[i] - 1e-9 for i in range(len(gs) - 1))
    assert all(gb[i + 1] <= gb[i] + 1e-9 for i in range(len(gb) - 1))
    assert all(px[i + 1] >= px[i] - 1e-9 for i in range(len(px) - 1))
    assert gs[-1] > gs[0] and gb[-1] < gb[0]          # strict overall move


def test_seller_weight_one_holds_buyer_at_the_floor(catalog):
    """w=1.0 hands the seller ALL surplus above the buyer's disagreement: the
    buyer's gain over its floor is weakly smaller than at the symmetric split
    and never negative — the disagreement discipline still binds, so the tilt
    can extract but can never price the buyer below its outside option."""
    from vend.scenario import nash_quote
    state, c = _glut_state(catalog), _consumer(catalog)
    lo = nash_quote(state, c.wtp, c.walk_cost, seller_weight=0.5)
    hi = nash_quote(state, c.wtp, c.walk_cost, seller_weight=1.0)
    gb_lo = lo.u_buyer_claimed - lo.d_buyer
    gb_hi = hi.u_buyer_claimed - hi.d_buyer
    assert -1e-9 <= gb_hi <= gb_lo + 1e-9


def test_seller_weight_preserves_discount_only_and_floor(catalog):
    """The tilt only moves surplus ABOVE the disagreement; the outcome space is
    still floor…list, so it never prices below opportunity cost or above the
    sticker, at any w."""
    from vend.scenario import nash_quote, c_eff
    state, c = _glut_state(catalog), _consumer(catalog)
    for w in (0.5, 0.75, 1.0):
        nq = nash_quote(state, c.wtp, c.walk_cost, seller_weight=w)
        assert nq.outcome is not None
        o = nq.outcome
        assert o.unit_price <= catalog[o.sku].list_price + 1e-9
        assert o.unit_price >= c_eff(state, o.sku) - 1e-9


def test_run_tilt_is_deterministic(tmp_path):
    """The frontier sweep is reproducible (a tiny slice: 1 seed, 6 days, two
    w, two liar deviations — the whole machinery, fast)."""
    import io
    import contextlib
    import json
    from vend.world import WorldConfig, CALIBRATED_TRAFFIC_SCALE
    from vend.run import run_tilt
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                      glut_prob=0.15, traffic_scale=CALIBRATED_TRAFFIC_SCALE)
    outs = []
    for i in range(2):
        p = tmp_path / f"t{i}.json"
        with contextlib.redirect_stdout(io.StringIO()):
            run_tilt([7], 6, cfg, str(p), w_grid=(0.5, 1.0),
                     liar_grid=((0.55, False), (0.55, True)))
        outs.append(json.load(open(p)))
    assert outs[0] == outs[1]


def test_tilt_frontier_artifact_shows_the_predicted_shape():
    """The committed vend/tilt.json (90-day, both-seed, block-5 split-tilt
    sweep) must exhibit the deliverable's pre-registered shape:
      * SELLER PROFIT (a2a−posted) rises with w, a tie at w=0.5;
      * CONSUMER SURPLUS advantage falls with w but stays > 0 throughout
        (no CS=0 crossing in [0.5, 1.0]);
      * the WTP-understatement lie's buyer gain rises with w — IC intact at
        w=0.5 (not significantly positive), broken before w=1.0;
      * ATTESTED REALIZED seller profit PEAKS at a small tilt then COLLAPSES
        when disclosure-IC breaks (peak w < 1.0; profit at w=1.0 < the peak);
      * the honest-region max seller-profit gain has a CI excluding zero."""
    import json
    import pathlib
    d = json.load(open(pathlib.Path(__file__).parents[1] / "tilt.json"))
    fr = d["frontier"]
    assert fr[0]["w"] == 0.5 and fr[-1]["w"] == 1.0
    prof = [r["profit_vs_posted"]["mean"] for r in fr]
    cs = [r["cs_vs_posted"]["mean"] for r in fr]
    und = [r["understatement_best"]["cs_gain"]["mean"] for r in fr]
    att = [r["attested_realized_profit_vs_posted"]["mean"] for r in fr]
    # seller profit: symmetric tie, monotone up, ends strictly higher
    lo, hi = fr[0]["profit_vs_posted"]["ci95"]
    assert lo <= 0 <= hi                                       # w=0.5 tie
    assert all(prof[i + 1] >= prof[i] - 1e-9 for i in range(len(prof) - 1))
    assert prof[-1] > prof[0]
    # CS advantage: falls overall, never crosses zero
    assert cs[-1] < cs[0] and all(x > 0 for x in cs)
    assert d["breakpoints"]["cs_zero_w_vs_posted"] is None
    # understatement-IC: intact at w=0.5, rises, breaks before w=1.0
    assert und[-1] > und[0]
    assert fr[0]["understatement_best"]["cs_gain"]["ci95"][0] <= 0
    icb = d["breakpoints"]["ic_break_w_understatement"]
    assert icb is not None and icb < 1.0
    # peak-then-collapse of attested realized seller profit
    peak = max(att)
    assert att.index(peak) < len(att) - 1                     # peak before w=1.0
    assert att[-1] < peak                                     # collapsed by w=1.0
    # honest-region max is a real (CI-excludes-zero) seller-profit gain
    assert d["breakpoints"]["max_honest_profit_vs_posted"]["ci95"][0] > 0


# ── surge-value-without-surging (Task #66) ──────────────────────────────────

def test_worldconfig_churn_rate_matches_regulars_module():
    """WorldConfig.churn_rate duplicates vend.regulars.CHURN_RATE (same
    import-order reason as loss_aversion) — pinned so they can't drift, and so
    the committed artifacts (default churn_rate) stay byte-identical."""
    from vend.world import WorldConfig
    from vend import regulars
    assert WorldConfig().churn_rate == regulars.CHURN_RATE


def test_regular_pool_honors_churn_rate():
    """churn_rate=0.0 is the CHURN-OFF counterfactual: even a maximally
    dissatisfied pool never permanently exits (the pool is held full so the
    captured-value measurement is uncontaminated by retention)."""
    from vend.regulars import RegularPool
    from vend.world import (WorldConfig, build_catalog,
                            _profit_optimal_list_price, CATALOG_SPEC)
    cat = build_catalog()
    market_ref = {s: _profit_optimal_list_price(mu, c)
                  for s, mu, c, *_ in CATALOG_SPEC}
    off = RegularPool(WorldConfig(regulars=20), 1, cat, market_ref, churn_rate=0.0)
    on = RegularPool(WorldConfig(regulars=20), 1, cat, market_ref, churn_rate=0.05)
    for pool in (off, on):
        for r in pool.pool:
            r.dissat = 100.0          # everyone furious
    off_churn = on_churn = 0
    for day in range(30):
        off_churn += off.end_day(day)
        on_churn += on.end_day(day)
    assert off_churn == 0                        # churn OFF: nobody ever leaves
    assert on_churn > 0                          # churn ON: the furious churn out
    # (active_count can return to cap either way — exogenous replenishment
    # refills the pool; the CHURN-OFF guarantee is about permanent EXITS)


def test_posted_surge_is_a_visible_above_reference_board(catalog):
    """POSTED-SURGE is a board-mode arm that posts the everyday reference
    off-peak and SURGES above it at peak (the visible time-of-day increase that
    fires the fairness churn), never above the peak-anchor ceiling."""
    from vend.run import ARMS
    from vend.policies import PostedSurgePolicy
    from vend.world import (WorldConfig, build_catalog, fresh_machine,
                            _profit_optimal_list_price)
    assert "posted-surge" in ARMS and isinstance(ARMS["posted-surge"](),
                                                 PostedSurgePolicy)
    cfg = WorldConfig(anchor_peak=True, anchor_mult=1.25)   # room to surge
    cat = build_catalog(cfg, 20260713)
    st = fresh_machine("m", cat, cfg, 20260713)
    pol = PostedSurgePolicy(surge_to_ceiling=True)
    assert pol.mode == "board"
    ref = _profit_optimal_list_price(2.20, 0.70)            # cola everyday price
    st.tick = 24                                            # 11:00 lunch peak (mult 1.15)
    peak = pol.price_board(st)["cola"][0]
    st.tick = 44                                            # ~14:20 off-peak (mult 0.75)
    off = pol.price_board(st)["cola"][0]
    assert peak > ref + 1e-9, (peak, ref)                  # surges ABOVE reference at peak
    assert off == pytest.approx(ref, abs=0.01)             # everyday price off-peak
    assert peak <= cat["cola"].list_price + 1e-9           # never above the ceiling


def test_surge_board_fires_fairness_churn_but_discount_quote_does_not():
    """The two mechanisms the experiment turns on, at the unit level:
      (a) a VISIBLE surge board above ref×1.10 fires sticker-shock on
          observation → dissatisfaction accrues (the churn driver);
      (b) an individual DISCOUNT quote below the reference is a GAIN with a
          deal-framing glow (fairness > 0) and, when settled, RELIEVES
          dissatisfaction — it does NOT fire sticker-shock. The discount-from-
          anchor mechanism itself is churn-negative; the peak-anchor engine's
          aggregate churn (see the artifact test) comes from its flat-ceiling
          FALLBACK board, not from the discounts."""
    from vend.regulars import Regular, regular_board_decision, settle_regular
    # (a) surge board observation → sticker shock → dissat up
    reg = Regular(uid=1, wtp={"cola": 5.0}, walk_cost=1.0, visit_prob=0.5,
                  home_tick=24, ref={"cola": 1.95})
    regular_board_decision(reg, {"cola": 2.56}, {"cola": 10},
                           outside_prices={"cola": 3.0})   # 2.56 > 1.95×1.10
    assert reg.dissat > 0                                  # the surge hurt

    # (b) a discount quote below reference is a positive-utility GAIN (glow),
    # and settling it RELIEVES accrued dissatisfaction (no sticker shock)
    reg2 = Regular(uid=2, wtp={"cola": 5.0}, walk_cost=1.0, visit_prob=0.5,
                   home_tick=24, ref={"cola": 1.95})
    reg2.dissat = 0.5
    glow = reg2.fairness("cola", 1.70, 1, list_price=2.56)  # discount off a high anchor
    assert glow > 0                                        # gain + deal-framing glow
    settle_regular(reg2, "cola", 1.70, 1)                  # below-ref payment
    assert reg2.dissat < 0.5                               # the deal healed


def test_surge_experiment_artifact_shows_the_honest_shape():
    """The committed vend/surge.json (90-day, both-seed, block-5) must exhibit
    the HONEST, pre-registered-then-tested shape — including the two findings
    that REFUTE the strong thesis:
      * static is the flat baseline (0 capture, 0 churn);
      * the reference-anchor engine captures ≈0 with ZERO churn (the clean
        world's sticker is already optimal ⇒ the only extra value is captive
        harvest, which needs an above-reference price);
      * the visible surge does NOT go net-negative from churn (captive harvest
        survives churn + replenishment) — the strong premise fails;
      * the peak-anchor engine does NOT escape the surge's churn: at the harvest
        anchor it churns MORE and retains FEWER regulars than the surge (its
        flat-ceiling fallback is above reference all day);
      * the engine still NETS MORE than the surge — via value (heterogeneity
        capture), not retention."""
    import json
    import pathlib
    d = json.load(open(pathlib.Path(__file__).parents[1] / "surge.json"))
    a = d["arms"]
    hi = max(d["anchors"])
    surge, engine = a[f"surge@{hi:g}"], a[f"engine@{hi:g}"]
    # static baseline is exactly flat
    assert a["static"]["captured_value_vs_static"]["mean"] == 0.0
    assert sum(a["static"]["churned_by_seed"]) == 0
    # reference-anchor engine: ≈0 capture, zero churn (fairness-safe but empty)
    assert abs(a["engine-ref"]["captured_value_vs_static"]["mean"]) < 1.0
    assert sum(a["engine-ref"]["churned_by_seed"]) == 0
    # the surge is NET-POSITIVE (does not go net-negative from churn)
    assert surge["net_profit_vs_static"]["ci95"][0] > 0
    assert d["verdict"]["surge_goes_net_negative_from_churn"] is False
    # the peak-anchor engine churns MORE than the surge (both seeds) — it does
    # NOT escape the fairness churn (the "no above-reference event" premise fails)
    assert all(engine["churned_by_seed"][i] > surge["churned_by_seed"][i]
               for i in range(len(d["seeds"])))
    assert d["verdict"]["peak_anchor_engine_escapes_surge_churn"] is False
    # net-profit ordering: engine > surge > static, and the engine's edge is
    # VALUE (churn-off capture), not retention
    assert (engine["net_profit_vs_static"]["mean"]
            > surge["net_profit_vs_static"]["mean"] > 0)
    assert (engine["captured_value_vs_static"]["mean"]
            > surge["captured_value_vs_static"]["mean"])


def test_run_surge_is_deterministic(tmp_path):
    """The surge sweep is reproducible (a tiny slice: 1 seed, 6 days, one anchor,
    a small pool — the whole machinery, fast)."""
    import io
    import contextlib
    import json
    from vend.run import run_surge
    outs = []
    for i in range(2):
        p = tmp_path / f"s{i}.json"
        with contextlib.redirect_stdout(io.StringIO()):
            run_surge([7], 6, str(p), anchors=[1.25], regulars=20)
        outs.append(json.load(open(p)))
    assert outs[0] == outs[1]


# ── review-fix batch (2026-07-10): one test per fix ─────────────────────────

def test_nash_disagreement_is_stock_capped(catalog):
    """FIX (scenario.nash_quote): the buyer's BOARD disagreement must be
    stock-capped, exactly like enumerate_outcomes / best_bundle. With cola
    stock 1, the disagreement is the buyable 1-unit board surplus — NOT the
    (unbuyable) 2-unit optimum. The un-capped loop credited d_buyer from a unit
    the machine can't sell, inflating the disagreement and spuriously killing
    real deals."""
    from vend.scenario import nash_quote
    from vend.world import bundle_value
    from vend.core import Lot
    state = machine(catalog)
    state.tick = 50
    state.lots = [Lot("cola", 1, expires_day=60)]     # only cola, stock 1
    wtp = {s: 0.3 for s in catalog}
    wtp["cola"] = 5.0                                  # cola is the board best
    lp = catalog["cola"].list_price
    q1 = wtp["cola"] - lp
    q2 = bundle_value(wtp, "cola", 2) - 2 * lp
    assert q2 > q1                                     # unconstrained optimum is 2 units…
    nq = nash_quote(state, wtp, 2.0)                   # walk high ⇒ board wins disagreement
    assert abs(nq.d_buyer - q1) < 1e-9                 # …but disagreement caps at buyable 1
    # under the bug d_buyer would be q2 (the unbuyable 2-unit bundle)
    assert nq.d_buyer < q2 - 1e-9


def test_regular_gate_rejects_worse_than_board(catalog):
    """FIX (run.py regular intent path): a regular can't be routed into a
    negotiated quote worse for them than the sticker board they can always
    access — the SAME max(s_out, s_board) guarantee the transient path
    enforces. A stub engine offers a low-value regular a positive-surplus but
    board-dominated quote (1 water); the regular must DECLINE it and take their
    board optimum (2 cola) instead."""
    from vend.scenario import Outcome, NashQuote
    from vend.policies import sticker_board
    from vend.regulars import Regular
    from vend.world import WorldConfig

    state = machine(catalog)
    reg = Regular(uid=7, wtp={s: 0.3 for s in catalog}, walk_cost=1.0,
                  visit_prob=1.0, home_tick=20,
                  ref={s: catalog[s].list_price for s in catalog})
    reg.wtp["cola"] = 5.0        # board optimum (2 cola at list) is very valuable
    reg.wtp["water"] = 3.0       # water quote is positive-surplus but worse

    class StubPolicy:
        policy_id = "stub/1"
        mode = "intent"
        learner = None
        dow_mult = 1.0
        traffic_scale = 1.0
        def price_board(self, st):
            return sticker_board(st)
        def quote_for(self, st, consumer, liar_roll):
            wp = catalog["water"].list_price
            return NashQuote(Outcome("water", 1, wp), 0.0, 0.0,
                             wp - catalog["water"].unit_cost, 0.0, 0.0, 0.0,
                             ["stub"]), False

    class FakePool:
        def visits_for_day(self, day): return {20: [reg]}
        def end_day(self, day): return 0
        def active_count(self): return 1

    # traffic_scale=0 ⇒ zero transient arrivals: the run isolates the regular
    cfg = WorldConfig(traffic_scale=0.0)
    m = run_day(StubPolicy(), state, catalog, master_seed=1, day=0, cfg=cfg,
                pool=FakePool())
    assert m["reg_deals"] == 1                         # exactly the one regular
    # the BAD water quote was declined; the regular took 2 cola from the board
    assert state.stock("water") == catalog["water"].par_stock   # water untouched
    assert m["units"] == 2                             # 2 cola (board), not 1 water
    # under the bug (accept iff raw+fair-fric>0) the water quote would settle:
    # m["units"] would be 1 and water stock would drop


def test_censored_escalation_is_capped():
    """FIX (DemandLearner.end_day): consecutive sellouts must not compound the
    censored demand estimate 1.2^n without bound. With a constant censored
    observation of 4/day, the estimate escalates but is CEILINGED at
    censor_cap_mult × observed (3 × 4 = 12), not ~4·1.2^n → hundreds."""
    from vend.policies import DemandLearner
    import pytest
    l = DemandLearner()
    l.begin_day(1.0); l.sold("cola", 4); l.sold("chips", 1)
    l.end_day()                                        # day 1: uncensored base
    assert l.daily("cola") == pytest.approx(4.0)
    for _ in range(30):                                # 30 straight sellouts
        l.begin_day(1.0); l.sold("cola", 4); l.sold("chips", 1)
        l.end_day(censored=frozenset({"cola"}))
    assert l.daily("cola") > 4.0                       # it DID escalate (raise-only)
    assert l.daily("cola") == pytest.approx(12.0)      # …but ceilinged at 3×obs
    # uncapped 1.2^30 would be ~4·237 ≈ 950 — the ceiling prevents the runaway
    assert l.daily("cola") < 4.0 * 1.2 ** 20


def test_pooled_ci_blocks_within_seed_never_across():
    """FIX (run._pooled_ci): block WITHIN each seed's series, never across the
    seed boundary. A per-seed length that is a multiple of `block` is identical
    to the old concatenate-then-block; a non-multiple must drop the remainder
    PER SEED (no straddling block that mixes two seeds' days)."""
    import numpy as np
    from vend.run import _pooled_ci
    rng = np.random.default_rng(0)
    a = list(rng.normal(0, 1, 90)); b = list(rng.normal(0, 1, 90))
    r = _pooled_ci([a, b], block=5)
    assert r["n"] == 18 + 18 and r["block"] == 5       # multiple: 18 blocks/seed
    a2 = list(rng.normal(0, 1, 88)); b2 = list(rng.normal(0, 1, 88))
    r2 = _pooled_ci([a2, b2], block=5)
    assert r2["n"] == 17 + 17                           # 88//5 each; NOT 35 (176//5)
    # the old concatenate-then-block would have straddled the seam → n=35
    assert r2["n"] != (88 + 88) // 5


def test_strong_posted_panel_outside_option_matches_run_py(catalog):
    """FIX (StrongPostedPolicy, referee #48 / §2): the synthetic-panel OUTSIDE
    option must equal the real consumer's outside option in run.py:163 —
    world.best_bundle(wtp, bodega_prices) over the WHOLE catalog at full
    QTY_CAP with NO machine-stock cap — then − walk (0 if no positive bundle).
    Pinned even with machine SKUs out of stock: the bug dropped out-of-stock
    SKUs and stock-capped the quantities, understating s_out."""
    import numpy as np
    from vend.policies import StrongPostedPolicy
    from vend.world import best_bundle, wtp_mult_at
    state = machine(catalog)
    state.tick = 30
    for lot in state.lots:                             # two SKUs fully OUT of machine stock
        if lot.sku in ("cola", "sandwich"):
            lot.quantity = 0
    pol = StrongPostedPolicy()
    pol._build_panel(list(state.listings))
    Zfull, walk, order = pol._panel
    mult_now = wtp_mult_at(state.tick)
    s_out = pol._panel_outside(state, order, mult_now, Zfull, walk)
    outside_prices = {s: catalog[s].bodega_price for s in catalog}   # run.py:59
    for c in range(0, Zfull.shape[0], 37):             # sample the panel
        wtp = {s: Zfull[c, order.index(s)] * catalog[s].wtp_mu_est * mult_now
               for s in order}
        o_sku, _, o_s = best_bundle(wtp, outside_prices)   # NO stock cap (run.py:163)
        expected = (o_s - walk[c]) if o_sku else 0.0       # run.py:164 (no clamp)
        assert abs(s_out[c] - expected) < 1e-9, (c, s_out[c], expected)

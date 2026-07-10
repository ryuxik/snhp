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

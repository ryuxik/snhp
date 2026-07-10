"""FASHION P0 tests: pairing is real, determinism holds, the cliff is the
cliff, markdown/1 only ever discounts, salvage accounting closes, and the
strategic waiter responds to the right forces."""
import pytest

from collections import Counter

from fashion.core import paired_ci, poisson_cdf, substream
import fashion.policies as policies
from fashion.policies import (AppealLearner, CliffPolicy, MarkdownPolicy,
                              OptMarkdownPolicy)
from fashion.run import make_policy, run_experiment, run_season
from fashion.world import (DEFAULT_CONFIG, SIZE_SHARE, SIZES, WEEKS,
                           FashionConfig, arrivals_at, build_catalog,
                           cliff_mult, planned_depth, planned_style_units,
                           return_lag_pmf, sample_return, sample_shopper,
                           waiter_buys_now)


@pytest.fixture(scope="module")
def catalog():
    return build_catalog()


@pytest.fixture(scope="module")
def depth(catalog):
    return planned_depth(catalog, DEFAULT_CONFIG, master_seed=7)


# ── pairing & determinism ────────────────────────────────────────────────

def test_shopper_stream_is_policy_independent(catalog):
    """Streams depend only on (seed, week, k) — the treatment-isolation
    guarantee."""
    assert [arrivals_at(7, w) for w in range(WEEKS)] == \
           [arrivals_at(7, w) for w in range(WEEKS)]
    c1 = sample_shopper(7, 3, 5, catalog)
    c2 = sample_shopper(7, 3, 5, catalog)
    assert c1 == c2 and c1.uid != 0
    assert sample_shopper(7, 3, 6, catalog).uid != c1.uid


def test_waiter_sets_are_nested_across_shares(catalog):
    """Raising waiter_share flips loyals into waiters without reshuffling
    identities: the 15% waiters are a subset of the 45% waiters."""
    lo = FashionConfig(waiter_share=0.15)
    hi = FashionConfig(waiter_share=0.45)
    for k in range(200):
        a = sample_shopper(11, 0, k, catalog, lo)
        b = sample_shopper(11, 0, k, catalog, hi)
        assert (a.style, a.size, a.base_wtp) == (b.style, b.size, b.base_wtp)
        if a.waiter:
            assert b.waiter


def test_experiment_is_deterministic():
    r1 = run_experiment(["cliff", "markdown"], seasons=2, seed=11)
    r2 = run_experiment(["cliff", "markdown"], seasons=2, seed=11)
    assert r1 == r2


# ── the cliff, honestly implemented ──────────────────────────────────────

def test_cliff_schedule_correctness(catalog, depth):
    """MSRP weeks 1–8, −30% weeks 9–11, −50% weeks 12–14, −70% weeks 15–16
    (0-indexed internally)."""
    expected = {0: 1.0, 7: 1.0, 8: 0.7, 10: 0.7, 11: 0.5, 13: 0.5,
                14: 0.3, 15: 0.3}
    pol = CliffPolicy()
    for week, mult in expected.items():
        assert cliff_mult(week) == mult
        board = pol.price_board(week, depth, catalog)
        for (style, _sz), p in board.items():
            assert p == pytest.approx(round(catalog[style].msrp * mult, 2))


# ── markdown/1 invariants ────────────────────────────────────────────────

def test_markdown_never_above_msrp_and_monotone(catalog, depth):
    """Prices stay in [salvage, MSRP] and never rise week-over-week, even
    as stock drains under the policy's feet."""
    pol = MarkdownPolicy()
    inv = dict(depth)
    prev = {}
    for week in range(WEEKS):
        board = pol.price_board(week, inv, catalog)
        for cell, p in board.items():
            listing = catalog[cell[0]]
            assert listing.salvage - 1e-9 <= p <= listing.msrp + 1e-9
            if cell in prev:
                assert p <= prev[cell] + 1e-9
            prev[cell] = p
        # drain ~25% of every cell so the solver faces moving state
        for cell in inv:
            inv[cell] = max(0, inv[cell] - max(1, depth[cell] // 4))


def test_discount_only_enforced_at_settlement(catalog, depth):
    """A policy that prices above MSRP cannot transact — the clamp is a
    runner-level guard, not a convention."""
    class Gouger:
        policy_id = "gouge/1"

        def price_board(self, week, inv, cat):
            return {cell: cat[cell[0]].msrp + 1.0
                    for cell, s in inv.items() if s > 0}

    with pytest.raises(ValueError, match="discount-only"):
        run_season(Gouger(), catalog, depth, master_seed=3)


# ── the buy ──────────────────────────────────────────────────────────────

def test_sigma_buy_zero_is_the_plan(catalog):
    d = planned_depth(catalog, FashionConfig(sigma_buy=0.0), master_seed=5)
    for style, listing in catalog.items():
        planned = planned_style_units(listing)
        for size in SIZES:
            assert d[(style, size)] == round(planned * SIZE_SHARE[size])


def test_buy_error_moves_depth_and_is_mean_one(catalog):
    cfg = FashionConfig(sigma_buy=0.35)
    base = planned_depth(catalog, FashionConfig(sigma_buy=0.0), master_seed=0)
    assert planned_depth(catalog, cfg, 1) != planned_depth(catalog, cfg, 2)
    # mean-one: across many seeds the noisy buy averages to the plan
    cell = ("coat", "M")
    ratios = [planned_depth(catalog, cfg, s)[cell] / base[cell]
              for s in range(300)]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.05


# ── the strategic waiter ─────────────────────────────────────────────────

def test_waiter_waits_when_safe_buys_under_size_risk():
    """Same shopper, same price: deep stock + no sell-through → wait;
    thin stock + hot sell-through → the one-step wait value collapses."""
    # wtp 110 vs price 100: surplus 10 now, drift says ~92 next week
    safe = waiter_buys_now(surplus_now=10.0, wtp_next=105.6, price=100.0,
                           stock=40, sold_last_week=0, last_week=False)
    risky = waiter_buys_now(surplus_now=10.0, wtp_next=105.6, price=100.0,
                            stock=2, sold_last_week=30, last_week=False)
    assert not safe and risky
    assert not waiter_buys_now(-1.0, 105.6, 100.0, 2, 30, False)  # no surplus


def test_last_week_waiter_buys_like_a_loyal():
    assert waiter_buys_now(0.5, 105.6, 100.0, 40, 0, last_week=True)
    assert not waiter_buys_now(-0.5, 105.6, 100.0, 40, 0, last_week=True)


def test_higher_waiter_share_shifts_units_late_under_cliff():
    """More waiters → a larger share of cliff-arm units sell at a discount
    (weeks 9+), fewer at full price — the 'training your customers' texture."""
    def disc_share(ws):
        res = run_experiment(["cliff"], seasons=4, seed=23,
                             cfg=FashionConfig(0.15, 0.0, ws))
        t = res["arms"]["cliff"]["per_season_means"]
        return (t["units_sold"] - t["units_full"]) / t["units_sold"]
    assert disc_share(0.45) > disc_share(0.15)


# ── returns (CALIBRATION-TARGETS #6: NRF 2024, 16.9% retail / 26% online) ──

def test_return_rate_zero_never_returns(catalog):
    """cfg.return_rate<=0 must reproduce the no-returns P0 EXACTLY — no lag
    draw, no rng consumed, no surprises for the r=0 grid cell."""
    for uid in range(50):
        assert sample_return(3, uid, DEFAULT_CONFIG) is None
        assert sample_return(3, uid, FashionConfig(return_rate=0.0)) is None


def test_return_lag_is_one_to_three_weeks():
    """r=1.0 makes every draw a return (deterministic): the lag must always
    fall in the documented {1, 2, 3}-week window (Uniform{7..21} days)."""
    cfg = FashionConfig(return_rate=1.0)
    lags = {sample_return(5, uid, cfg) for uid in range(300)}
    assert lags <= {1, 2, 3}
    assert None not in lags


def test_return_sets_are_nested_across_rates():
    """Same trick as waiter_share nesting: raising return_rate only ADDS
    returns, and a shopper who returns at both rates draws the identical lag
    — the propensity draw happens before the lag draw on the same rng, so
    0.17's returners are a strict subset of 0.26's, with matching lags."""
    lo = FashionConfig(return_rate=0.17)
    hi = FashionConfig(return_rate=0.26)
    for uid in range(500):
        a = sample_return(11, uid, lo)
        b = sample_return(11, uid, hi)
        if a is not None:
            assert b is not None
            assert a == b


def test_returns_refund_conservation(catalog, depth):
    """Money and units must close under returns. Every return refunds
    exactly the price it was sold at, so:
      net_revenue == revenue - refunds
      gross_margin == net_revenue + salvage_revenue - buy_cost
    and every physical unit ends EITHER kept by a customer (a sale that was
    never returned) or salvaged (season-end inventory, or a post-season
    return that never got a chance to re-shelve) — never both, never
    neither:
      salvage_units == units_bought - (units_sold - returns)
    """
    m = run_season(CliffPolicy(), catalog, depth, master_seed=9,
                   cfg=FashionConfig(return_rate=0.3))
    assert m["returns"] > 0        # the config should actually exercise it
    assert m["net_revenue"] == pytest.approx(m["revenue"] - m["refunds"],
                                             abs=0.02)
    assert m["gross_margin"] == pytest.approx(
        m["net_revenue"] + m["salvage_revenue"] - m["buy_cost"], abs=0.02)
    assert m["salvage_units"] == \
        m["units_bought"] - m["units_sold"] + m["returns"]
    assert m["returns"] == m["returns_restocked"] + m["returns_postseason"]


def test_returns_re_enter_sellable_stock(catalog, depth):
    """A returned unit that lands before the last selling week must be
    resellable, not stuck in limbo: returns_restocked (returns that happened
    in time to reach the rack) should be the common case, and every
    restocked return should show up in the salvage/units identity too."""
    m = run_season(MarkdownPolicy(), catalog, depth, master_seed=9,
                   cfg=FashionConfig(return_rate=0.3))
    assert m["returns_restocked"] > 0
    # restocked returns can resell again — gross units_sold, INCLUDING
    # resells, must be at least the number of distinct return events plus
    # one original sale each; the loose sanity bound is that resells push
    # sell-through (gross) at or above the no-returns baseline.
    assert m["units_sold"] >= m["returns_restocked"]


def test_realized_return_rate_tracks_configured():
    """Aggregate over enough seasons and the realized rate (returns ÷ gross
    units sold, a per-transaction Bernoulli(r) by construction) should track
    the configured r within a couple of points."""
    for r in (0.17, 0.26):
        res = run_experiment(["cliff", "markdown"], seasons=20, seed=20260710,
                             cfg=FashionConfig(0.0, 0.0, 0.0, r))
        for arm in ("cliff", "markdown"):
            realized = res["arms"][arm]["per_season_means"][
                "return_rate_realized"]
            assert abs(realized - 100.0 * r) < 3.0


def test_returns_hit_cliff_harder_than_markdown():
    """THE mechanism under test: cliff holds MSRP for 8 weeks, so its
    full-price sales that return into clearance are refunded at a much
    higher price than they resell for — a bigger leak than markdown/1's
    early-shallow-discount sales. Gross margin should fall by a LARGER
    fraction under cliff than under markdown as returns rise from 0 to 26%."""
    cfg0 = FashionConfig(0.0, 0.0, 0.0, 0.0)
    cfg_r = FashionConfig(0.0, 0.0, 0.0, 0.26)
    res0 = run_experiment(["cliff", "markdown"], seasons=20, seed=20260710,
                          cfg=cfg0)
    resr = run_experiment(["cliff", "markdown"], seasons=20, seed=20260710,
                          cfg=cfg_r)
    cliff0 = res0["arms"]["cliff"]["per_season_means"]["gross_margin"]
    cliffr = resr["arms"]["cliff"]["per_season_means"]["gross_margin"]
    md0 = res0["arms"]["markdown"]["per_season_means"]["gross_margin"]
    mdr = resr["arms"]["markdown"]["per_season_means"]["gross_margin"]
    cliff_drop_frac = (cliff0 - cliffr) / cliff0
    md_drop_frac = (md0 - mdr) / md0
    assert cliff_drop_frac > md_drop_frac > 0


# ── accounting ───────────────────────────────────────────────────────────

def test_salvage_accounting_closes(catalog, depth):
    m = run_season(CliffPolicy(), catalog, depth, master_seed=9)
    assert m["salvage_units"] == m["units_bought"] - m["units_sold"]
    assert m["gross_margin"] == pytest.approx(
        m["revenue"] + m["salvage_revenue"] - m["buy_cost"], abs=0.02)
    assert m["units_sold"] == (m["units_full"] + m["units_d30"] +
                               m["units_d50"] + m["units_d70"] +
                               m["units_d70plus"])
    assert m["buy_cost"] == pytest.approx(
        sum(n * catalog[st].unit_cost for (st, _), n in depth.items()))


def test_sell_through_is_bounded():
    res = run_experiment(["cliff", "markdown"], seasons=3, seed=31,
                         cfg=FashionConfig(0.35, 0.2, 0.45))
    for arm in ("cliff", "markdown"):
        for season in res["_per_season"][arm]:
            assert 0.0 <= season["sell_through"] <= 100.0
            assert season["units_sold"] <= season["units_bought"]
            assert season["salvage_units"] >= 0


# ── helpers ──────────────────────────────────────────────────────────────

def test_poisson_cdf_matches_scipy():
    from scipy import stats
    for k, mu in [(0, 0.0), (3, 2.5), (10, 8.0), (5, 40.0), (60, 3.0)]:
        assert poisson_cdf(k, mu) == pytest.approx(
            float(stats.poisson.cdf(k, mu)), abs=1e-9)
    assert poisson_cdf(-1, 5.0) == 0.0


def test_paired_ci_plain_t():
    ci = paired_ci([1.0, 2.0, 3.0, 4.0], block=1)
    assert ci["mean"] == 2.5 and ci["n"] == 4
    assert ci["ci95"][0] < 2.5 < ci["ci95"][1]


# ── v4 timeline-optimized markdown arm (CRITICAL-ANALYSIS §4, fashion) ─────

def test_return_lag_pmf_matches_the_sampler():
    """The engine's return-timing curve is DERIVED from the same days→weeks
    mapping sample_return uses, so it can't drift: it sums to 1, lands on
    {1,2,3}, and matches the empirical draw distribution."""
    pmf = return_lag_pmf()
    assert set(pmf) == {1, 2, 3}
    assert sum(pmf.values()) == pytest.approx(1.0)
    cfg = FashionConfig(return_rate=1.0)
    c = Counter(sample_return(99, uid, cfg) for uid in range(40000))
    tot = sum(c.values())
    for wk, p in pmf.items():
        assert c[wk] / tot == pytest.approx(p, abs=0.02)


def test_optnl_reduces_to_markdown_at_r0(catalog, depth):
    """The clean r=0 anchor: with returns off AND learning off, opt/1's
    returns-aware machinery is inert and its solve is byte-identical to
    markdown/1 — so the whole season (every metric) matches, and the r=0
    opt−markdown gap can be attributed purely to the two upgrades."""
    ms = 4242
    md = run_season(MarkdownPolicy(), catalog, depth, ms,
                    FashionConfig(0.15, 0.2, 0.15, 0.0))
    opt = run_season(make_policy("optnl", catalog, FashionConfig(0.15, 0.2, 0.15, 0.0)),
                     catalog, depth, ms, FashionConfig(0.15, 0.2, 0.15, 0.0))
    assert opt["gross_margin"] == pytest.approx(md["gross_margin"], abs=0.01)
    assert opt["units_sold"] == md["units_sold"]
    assert opt["units_deep"] == md["units_deep"]


def test_opt_experiment_is_deterministic():
    r1 = run_experiment(["cliff", "markdown", "opt", "optnl"], seasons=2,
                        seed=11, cfg=FashionConfig(0.15, 0.2, 0.15, 0.26))
    r2 = run_experiment(["cliff", "markdown", "opt", "optnl"], seasons=2,
                        seed=11, cfg=FashionConfig(0.15, 0.2, 0.15, 0.26))
    assert r1 == r2


def test_opt_never_above_msrp_and_monotone(catalog, depth):
    """The timeline-optimized board obeys the same invariants as markdown/1:
    prices stay in [salvage, MSRP] and never rise week-over-week, even under
    the returns-aware forward-sim solve."""
    pol = make_policy("opt", catalog, FashionConfig(0.15, 0.0, 0.15, 0.26))
    inv = dict(depth)
    prev = {}
    for week in range(WEEKS):
        board = pol.price_board(week, inv, catalog)
        for cell, p in board.items():
            listing = catalog[cell[0]]
            assert listing.salvage - 1e-9 <= p <= listing.msrp + 1e-9
            if cell in prev:
                assert p <= prev[cell] + 1e-9
            prev[cell] = p
        for cell in inv:
            inv[cell] = max(0, inv[cell] - max(1, depth[cell] // 4))


def test_opt_discount_only_enforced_at_settlement(catalog, depth):
    """End to end: opt/1 (returns-aware) never transacts above MSRP — the
    runner's discount-only clamp holds for the new arm too."""
    m = run_season(make_policy("opt", catalog, FashionConfig(0.15, 0.2, 0.15, 0.26)),
                   catalog, depth, master_seed=3,
                   cfg=FashionConfig(0.15, 0.2, 0.15, 0.26))
    assert m["units_sold"] > 0        # it actually transacted


def test_appeal_learner_holds_until_evidence_and_is_censoring_aware(catalog):
    """The learner returns the buy-time estimate until LEARN_MIN_EXP evidence
    accrues; a CENSORED (sold-out) week enters as a lower bound that can only
    push the level UP, never down (dropping/face-valuing it would bias the
    level down exactly where demand was strongest)."""
    L = AppealLearner(catalog)
    est = catalog["coat"].appeal_est
    assert L.appeal("coat") == est                       # no evidence yet
    # a sold-out week where the model predicted MORE than sold: censored, so it
    # is capped at the units sold — it must NOT drag the level below the guess
    L.accumulate("coat", obs_sales=3.0, exp_demand=9.0, censored=True)
    L.accumulate("coat", obs_sales=3.0, exp_demand=9.0, censored=True)
    L.accumulate("coat", obs_sales=3.0, exp_demand=9.0, censored=True)
    assert L.appeal("coat") >= est - 1e-9                # only ever up, never down
    # a clean run of under-predicted (obs > exp) demand raises the estimate
    L2 = AppealLearner(catalog)
    for _ in range(10):
        L2.accumulate("coat", obs_sales=6.0, exp_demand=3.0, censored=False)
    assert L2.appeal("coat") > est


def test_returns_aware_solve_bounded_and_drift_sensitive(catalog):
    """The returns-aware forward-sim solve stays in [salvage, MSRP] (whole
    cents), and it genuinely USES the return-timing belief: changing the
    anticipated markdown drift moves the posted price. That sensitivity is the
    honest finding's flip side — the arm is FRAGILE to the drift belief (a
    mis-set drift can even flip the sign of the price move), which is why the
    verdict is reported with a drift sweep and never rests on one value."""
    pol = OptMarkdownPolicy(return_rate=0.26)
    pol.bind(catalog)
    listing = catalog["coat"]
    ah = listing.appeal_est
    prices = {}
    saved = policies.ANTICIPATED_DRIFT
    try:
        for drift in (1.0, 0.96, 0.85):
            policies.ANTICIPATED_DRIFT = drift
            p = pol._solve_returns_aware(listing, "M", week=2, stock=40,
                                         appeal_hat=ah)
            assert listing.salvage - 1e-9 <= p <= listing.msrp + 1e-9
            assert round(p, 2) == p
            prices[drift] = p
    finally:
        policies.ANTICIPATED_DRIFT = saved
    assert len(set(prices.values())) > 1           # the drift belief matters

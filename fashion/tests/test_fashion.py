"""FASHION P0 tests: pairing is real, determinism holds, the cliff is the
cliff, markdown/1 only ever discounts, salvage accounting closes, and the
strategic waiter responds to the right forces."""
import pytest

from fashion.core import paired_ci, poisson_cdf, substream
from fashion.policies import CliffPolicy, MarkdownPolicy
from fashion.run import run_experiment, run_season
from fashion.world import (DEFAULT_CONFIG, SIZE_SHARE, SIZES, WEEKS,
                           FashionConfig, arrivals_at, build_catalog,
                           cliff_mult, planned_depth, planned_style_units,
                           sample_shopper, waiter_buys_now)


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

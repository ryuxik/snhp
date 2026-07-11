"""Tests for B6.5 the calibration-for-discount data market (task #72): the
Pareto / positive-sum properties, the split, the DURABLE-vs-competed-away
comparison, and the demand-cartel monopsony audit (the mirror of
buyer.strategies.coordinate's audit)."""
import json
import pathlib

import pytest

from block import datamarket
from block.datamarket import DataConfig

SEED = 20260710


@pytest.fixture(scope="module")
def market():
    """The committed data-market sweep — the same config
    block/results-datamarket.json records (400 seeds, ~1s)."""
    return datamarket.run_market(DataConfig(seeds=400), seed0=SEED)


# ── the two flywheel/exchange primitives ─────────────────────────────────────

def test_sigma_cal_shrinks_with_cluster_size():
    """The merchant's effective σ_cal shrinks as the cluster discloses more
    verified WTP observations (the B6.1 conjugate shrinkage): σ(0)=σ0, monotone
    decreasing, saturating."""
    cfg = DataConfig()
    assert datamarket.sigma_at(0, cfg) == pytest.approx(cfg.sigma0)
    prev = datamarket.sigma_at(0, cfg)
    for K in (1, 2, 5, 10, 44, 100, 1000):
        s = datamarket.sigma_at(K, cfg)
        assert s < prev
        prev = s


def test_cluster_share_rises_with_size():
    """The broker's size-scaled split favors bigger clusters: s(K)=K/(K+K0),
    strictly increasing in K, bounded in (0,1)."""
    cfg = DataConfig()
    shares = [datamarket.cluster_share(K, cfg) for K in (2, 5, 10, 20, 44, 100)]
    assert all(shares[i + 1] > shares[i] for i in range(len(shares) - 1))
    assert 0.0 < shares[0] and shares[-1] < 1.0


# ── the headline properties on the committed sweep ───────────────────────────

def test_data_value_is_positive_and_grows(market):
    """The merchant's willingness-to-pay for the cluster's calibration (its
    recovered profit ΔΠ) is significantly POSITIVE at every K and grows with
    cluster size — the positive-sum core the exchange divides."""
    dpi = [c["data_value_dPi"] for c in market["cells"]]
    for d in dpi:
        assert d["ci95"][0] > 0.0                       # CI excludes zero
    means = [d["mean"] for d in dpi]
    assert means[-1] > means[0]                          # grows with K


def test_total_welfare_grows(market):
    """The exchange creates welfare (not just redistributes it): ΔW > 0 at every
    K, CI excludes zero."""
    for c in market["cells"]:
        assert c["d_welfare"]["ci95"][0] > 0.0


def test_data_beats_the_competed_away_haggle(market):
    """The pre-registered comparison (NETWORK.md §C.4): the information rent to
    the cluster EXCEEDS the shopping haggle WHICH COMPETES AWAY as boards
    converge (→0). The cluster's data payoff > its competitive-haggle payoff at
    every K."""
    for c in market["cells"]:
        assert c["data_beats_competitive_haggle"]
        assert c["cluster_haggle_competitive"] == pytest.approx(0.0, abs=1e-6)


def test_honest_scope_data_does_not_out_dollar_a_monopoly_haggle(market):
    """The honesty check, recorded not hidden: the data does NOT out-dollar a raw
    MONOPOLY haggle — a cluster extracts more by bargaining a monopolist down than
    by selling it data. The data's edge is durability + Pareto, not raw magnitude.
    (This is why the verdict is 'durable value', not 'bigger number'.)"""
    big = market["cells"][-1]
    assert big["cluster_haggle_monopoly"] > big["cluster_data_payoff"]
    assert not market["verdict"]["data_out_dollars_monopoly_haggle"]


def test_data_value_scales_with_miscalibration(market):
    """The σ0-sensitivity: the worse the merchant's calibration, the more its
    demand curve is worth. ΔΠ at K=44 grows ≈quadratically with σ0."""
    rows = market["sigma0_sensitivity"]["rows"]
    dpi = [r["data_value_dPi_K44"]["mean"] for r in rows]
    assert dpi[0] < dpi[1] < dpi[2]                      # 0.15 < 0.30 < 0.50


# ── the demand-cartel monopsony audit (the RealPage mirror) ──────────────────

def test_monopsony_audit_passes_on_the_sweep(market):
    """The pre-registered monopsony audit at every K: the participation floor
    holds (the merchant keeps ≥0 of the data value at the fair split and exactly
    0 at maximal extraction), over-reach is self-defeating (the merchant refuses,
    so the cluster gets nothing), and the standing discount is discount-only
    (every price stays ≥ cost)."""
    for c in market["cells"]:
        a = c["monopsony_audit"]
        assert a["B_participation_floor_holds"]
        assert a["D_overreach_self_defeating"]
        assert a["price_floor_discount_only_ok"]
    assert market["verdict"]["monopsony_audit_pass"]


def test_monopsony_audit_flags_overreach_below_the_floor():
    """Direct exercise of the audit predicate: a demand cartel demanding MORE
    than the data is worth (D > ΔΠ) breaches the merchant's participation floor,
    the merchant refuses, and it is self-defeating — the exact mirror of the
    buyer-side coordinate() over-reach check."""
    cfg = DataConfig(overreach=1.25)
    # a synthetic board with real margin room, and a data value of $3
    board = {"a": (4.0, 1.0, 3.4, 12.0), "b": (11.0, 4.0, 9.75, 6.0)}
    a = datamarket._monopsony_audit(44, 3.0, board, cfg)
    assert a["B_participation_floor_holds"]              # fair + max-extract ≥ 0
    assert a["B_max_extract_merchant_keep"] == pytest.approx(0.0)
    assert a["D_overreach_merchant_refuses"]             # D=1.25·ΔΠ > ΔΠ ⇒ refuse
    assert a["price_floor_discount_only_ok"]


def test_pareto_and_durable_verdict(market):
    """The synthesized verdict: the data market is Pareto/positive-sum AND the
    durable value (survives the haggle competing away)."""
    v = market["verdict"]
    assert v["sigma_cal_shrinks_with_cluster"]
    assert v["data_value_positive_all_K"]
    assert v["total_welfare_grows_all_K"]
    assert v["split_favors_consumers_with_size"]
    assert v["data_beats_competed_away_haggle_all_K"]
    assert v["monopsony_audit_pass"]
    assert v["pareto_positive_sum_data_market"]
    assert v["durable_value_is_the_data_market"]


# ── determinism + the committed artifact ─────────────────────────────────────

def test_datamarket_is_deterministic():
    a = datamarket.run_market(DataConfig(seeds=50), seed0=5)
    b = datamarket.run_market(DataConfig(seeds=50), seed0=5)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_committed_datamarket_results_stay_reproducible(market):
    """block/results-datamarket.json reproduces byte-identically at its config."""
    path = pathlib.Path(__file__).parents[1] / "results-datamarket.json"
    committed = json.load(open(path))
    assert json.dumps(market, sort_keys=True) == json.dumps(committed,
                                                            sort_keys=True)

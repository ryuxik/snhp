"""
Sprint 3 acceptance tests (Tier 3 mechanism design).

Per the plan's verification section:
  1. Gale-Shapley correctness: classic textbook 4-man / 4-woman example
     returns the known proposer-optimal stable matching.
  2. Optimal auction equivalence under symmetric IPV: Myerson optimal
     mechanism revenue and reserve match second-price-with-reserve when
     bidders have iid priors.
  3. Posted-price simulation accuracy: analytical static-price revenue
     matches Monte Carlo within 5% for a stated arrival prior.

Run: ../venv/bin/python -m pytest gametheory/tests/test_sprint3.py -v
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_sprint3_keys.db")

from gametheory.server.http import app
from gametheory.mechanism.gale_shapley import gale_shapley
from gametheory.mechanism.optimal_auction import optimal_auction_design
from gametheory.mechanism.posted_price import posted_price_optimal
from gametheory.auctions.seller import optimal_reserve as tier2_optimal_reserve


client = TestClient(app)


# ─── Gale-Shapley ───────────────────────────────────────────────────────────


def test_gale_shapley_textbook_4x4():
    """Knuth-1976 classic example returns the proposer-optimal stable matching."""
    proposers = [
        {"id": "1", "preferences": ["A", "B", "C", "D"]},
        {"id": "2", "preferences": ["A", "C", "B", "D"]},
        {"id": "3", "preferences": ["B", "A", "C", "D"]},
        {"id": "4", "preferences": ["D", "A", "C", "B"]},
    ]
    receivers = [
        {"id": "A", "preferences": ["4", "3", "1", "2"]},
        {"id": "B", "preferences": ["1", "4", "2", "3"]},
        {"id": "C", "preferences": ["3", "1", "2", "4"]},
        {"id": "D", "preferences": ["2", "3", "1", "4"]},
    ]
    r = gale_shapley(proposers=proposers, receivers=receivers)
    expected = {"1": "A", "2": "C", "3": "B", "4": "D"}
    assert r["matching"] == expected
    assert r["unmatched_proposers"] == []
    assert r["blocking_pairs"] == []


def test_gale_shapley_capacities():
    """A receiver with capacity 2 holds two proposers."""
    proposers = [
        {"id": "p1", "preferences": ["r1"]},
        {"id": "p2", "preferences": ["r1"]},
        {"id": "p3", "preferences": ["r1"]},
    ]
    receivers = [
        {"id": "r1", "preferences": ["p1", "p2", "p3"], "capacity": 2},
    ]
    r = gale_shapley(proposers=proposers, receivers=receivers)
    matched = [p for p, rcv in r["matching"].items() if rcv == "r1"]
    assert sorted(matched) == ["p1", "p2"]
    assert r["unmatched_proposers"] == ["p3"]
    assert r["blocking_pairs"] == []


def test_gale_shapley_unacceptable_proposer():
    """Receiver without proposer in its prefs rejects them."""
    proposers = [{"id": "p1", "preferences": ["r1"]}]
    receivers = [{"id": "r1", "preferences": []}]
    r = gale_shapley(proposers=proposers, receivers=receivers)
    assert r["matching"]["p1"] is None
    assert "p1" in r["unmatched_proposers"]


def test_gale_shapley_rejects_unknown_id():
    """Reference to non-existent receiver id raises ValueError."""
    with pytest.raises(ValueError):
        gale_shapley(
            proposers=[{"id": "p1", "preferences": ["NOPE"]}],
            receivers=[{"id": "r1", "preferences": ["p1"]}],
        )


def test_gale_shapley_via_http():
    r = client.post("/v1/mechanism/gale_shapley", json={
        "proposers": [
            {"id": "1", "preferences": ["A", "B"]},
            {"id": "2", "preferences": ["B", "A"]},
        ],
        "receivers": [
            {"id": "A", "preferences": ["1", "2"]},
            {"id": "B", "preferences": ["2", "1"]},
        ],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matching"] == {"1": "A", "2": "B"}
    assert body["blocking_pairs"] == []
    assert r.headers["X-GT-Cost-USD"] == "0"


# ─── Optimal auction design ─────────────────────────────────────────────────


def test_optimal_auction_symmetric_uniform_matches_tier2():
    """Symmetric uniform[0,100] IPV → reserve = 50, revenue ≈ Tier 2 second-price."""
    prior = {"family": "uniform", "params": {"low": 0, "high": 100}}
    n = 4
    r_t3 = optimal_auction_design(
        bidder_priors=[prior] * n,
        seller_valuation=0.0,
        objective="revenue",
        seed=42,
    )
    r_t2 = tier2_optimal_reserve(
        bidder_value_prior=prior, n_bidders=n, seller_valuation=0.0,
    )
    # All per-bidder reserves should equal the Tier 2 single reserve (50).
    for v in r_t3["reserve_prices"].values():
        assert abs(v - r_t2["reserve_price"]) < 1.0
    # Revenue numbers should agree within 5%.
    assert abs(r_t3["expected_revenue"] - r_t2["expected_revenue"]) \
        / r_t2["expected_revenue"] < 0.05


def test_optimal_auction_welfare_returns_vcg():
    """Welfare-optimal mechanism is VCG: no reserves."""
    r = optimal_auction_design(
        bidder_priors=[{"family": "uniform", "params": {"low": 0, "high": 100}}] * 3,
        seller_valuation=0.0,
        objective="welfare",
    )
    assert r["mechanism"] == "vcg_no_reserve"
    assert r["reserve_prices"] == {}


def test_optimal_auction_rejects_invalid_objective():
    with pytest.raises(ValueError):
        optimal_auction_design(
            bidder_priors=[{"family": "uniform", "params": {"low": 0, "high": 100}}],
            seller_valuation=0.0,
            objective="fairness",
        )


def test_optimal_auction_via_http():
    r = client.post("/v1/mechanism/optimal_auction_design", json={
        "bidder_priors": [
            {"family": "uniform", "params": {"low": 0, "high": 100}},
            {"family": "uniform", "params": {"low": 0, "high": 100}},
            {"family": "uniform", "params": {"low": 0, "high": 100}},
        ],
        "seller_valuation": 0.0,
        "objective": "revenue",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mechanism"] == "myerson_optimal"
    # All three bidders get a per-bidder reserve.
    assert len(body["reserve_prices"]) == 3


# ─── Posted-price ───────────────────────────────────────────────────────────


def test_posted_price_analytical_matches_monte_carlo():
    """Analytical E[revenue] under static p* must agree with MC within 5%."""
    r = posted_price_optimal(
        buyer_arrival_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
        arrival_rate_per_second=0.5,
        inventory=50,
        horizon_seconds=600.0,
        n_simulations=2_000,
        seed=42,
    )
    rel_err = abs(r["static_expected_revenue"] - r["static_simulated_revenue"]) \
        / r["static_expected_revenue"]
    assert rel_err < 0.05, f"analytical/MC gap = {rel_err:.3f}"


def test_posted_price_dynamic_at_least_static():
    """Dynamic policy is at least as good as the optimal static price."""
    r = posted_price_optimal(
        buyer_arrival_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
        arrival_rate_per_second=0.5,
        inventory=50,
        horizon_seconds=600.0,
        seed=42,
    )
    # Dynamic V(C, 0) must equal or beat the static simulated revenue
    # (DP optimizes over the larger policy class that contains static).
    # Both are unbiased estimates of revenue under their respective
    # policies, so the comparison is apples-to-apples without fudge.
    assert r["dynamic_value_estimate"] >= r["static_simulated_revenue"]


def test_posted_price_validates_inputs():
    with pytest.raises(ValueError):
        posted_price_optimal(
            buyer_arrival_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
            arrival_rate_per_second=-1,
            inventory=10, horizon_seconds=60,
        )
    with pytest.raises(ValueError):
        posted_price_optimal(
            buyer_arrival_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
            arrival_rate_per_second=1, inventory=0, horizon_seconds=60,
        )


def test_posted_price_via_http():
    r = client.post("/v1/mechanism/posted_price_optimal", json={
        "buyer_arrival_prior": {"family": "uniform", "params": {"low": 0, "high": 100}},
        "arrival_rate_per_second": 0.5,
        "inventory": 30,
        "horizon_seconds": 300.0,
        "n_simulations": 1_000,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["static_price"] > 0
    assert body["sellthrough_rate"] > 0
    assert len(body["dynamic_schedule"]) > 0


# ─── Catalog & docs ─────────────────────────────────────────────────────────


def test_catalog_lists_tier3_tools():
    r = client.get("/v1/catalog")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    for required in [
        "gt.mechanism.gale_shapley",
        "gt.mechanism.optimal_auction_design",
        "gt.mechanism.posted_price_optimal",
    ]:
        assert required in names, f"missing {required} from catalog"


def test_llms_txt_mentions_tier3():
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert "Tier 3" in r.text
    assert "gale_shapley" in r.text
    assert "posted_price" in r.text


def test_openapi_includes_tier3_paths():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in [
        "/v1/mechanism/gale_shapley",
        "/v1/mechanism/optimal_auction_design",
        "/v1/mechanism/posted_price_optimal",
    ]:
        assert p in paths, f"missing OpenAPI path {p}"

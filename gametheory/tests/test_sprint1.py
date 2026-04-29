"""
Sprint 1 acceptance tests.

Per the plan's verification section:
  1. Auction known-answer tests (Vickrey truthful, uniform first-price BNE)
  2. Sell-side handler structural tests (Pareto knob produces monotone behavior)
  3. HTTP integration test (server boots, endpoints respond, headers correct)
  4. Discovery integration (catalog, OpenAPI spec, llms.txt all readable)
  5. Onboarding (key issuance, idempotency)

Run: ../venv/bin/python -m pytest gametheory/tests/test_sprint1.py -v

The full SNHP-tournament-through-API regression test is gated behind
@pytest.mark.slow because it takes ~12s; run with `-m slow` to include it.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Use a temp DB so tests don't pollute the user's keys.db
_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_keys.db")

from gametheory.server.http import app
from gametheory.negotiation.sell import sell_next_offer
from gametheory.auctions.bidder import optimal_bid
from gametheory.auctions.seller import optimal_reserve, simulate


client = TestClient(app)


# ─── Tier 2: Known-answer auction tests ──────────────────────────────────────


def test_vickrey_is_truthful():
    """Vickrey: bid = my_valuation is the dominant strategy."""
    r = optimal_bid(
        auction_format="second_price_vickrey",
        my_valuation=100.0, n_competing_bidders=3,
        competitor_value_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
    )
    assert r["optimal_bid"] == 100.0
    assert r["dominant_strategy"] is True


def test_first_price_uniform_bne():
    """First-price BNE for uniform: b(v) = v * (N-1) / N."""
    for n_total in [2, 3, 5, 10]:
        r = optimal_bid(
            auction_format="first_price",
            my_valuation=100.0, n_competing_bidders=n_total - 1,
            competitor_value_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
        )
        expected = 100.0 * (n_total - 1) / n_total
        assert abs(r["optimal_bid"] - expected) < 0.01, \
            f"N={n_total}: expected {expected}, got {r['optimal_bid']}"


def test_optimal_reserve_uniform():
    """Optimal reserve for uniform[0, b], seller_val=0: r = b/2."""
    r = optimal_reserve(
        bidder_value_prior={"family": "uniform", "params": {"low": 0, "high": 100}},
        n_bidders=4, seller_valuation=0.0,
    )
    assert abs(r["reserve_price"] - 50.0) < 1.0, \
        f"expected reserve 50, got {r['reserve_price']}"
    # With reserve, revenue should be higher than without (when N small)
    assert r["expected_revenue"] >= r["expected_revenue_no_reserve"]


def test_simulate_revenue_in_expected_range():
    """Vickrey N=4 uniform[0,100] reserve=50: revenue should be in (40, 80)."""
    r = simulate(
        auction_format="second_price_vickrey",
        bidder_priors=[{"family": "uniform", "params": {"low": 0, "high": 100}}] * 4,
        reserve_price=50.0, n_simulations=10_000, seed=42,
    )
    assert 40 < r["mean_revenue"] < 80, f"revenue out of range: {r['mean_revenue']}"
    assert 0.85 < r["efficiency"] < 1.0  # most simulations should clear reserve


# ─── Tier 1: Pareto-knob monotonicity ────────────────────────────────────────


def test_pareto_knob_produces_higher_offers():
    """Higher knob → more aggressive (higher recommended offer)."""
    history_args = {
        "my_reservation": 0.40,
        "opponent_offer_history": [0.20, 0.25, 0.30],
        "my_offer_history": [0.85, 0.78, 0.70],
        "deadline_rounds": 10,
    }
    offers = []
    for knob in [0.0, 0.25, 0.5, 0.75, 1.0]:
        r = sell_next_offer(**history_args, pareto_knob=knob)
        offers.append(r["recommended_offer"])
    # Recommended offers should be (weakly) monotone non-decreasing in knob
    for i in range(len(offers) - 1):
        assert offers[i] <= offers[i + 1] + 0.001, \
            f"non-monotone: knob {i*0.25}→{(i+1)*0.25} gave {offers[i]} → {offers[i+1]}"


def test_pareto_knob_acceptance_inversely_related():
    """Higher knob → lower acceptance probability."""
    history_args = {
        "my_reservation": 0.40,
        "opponent_offer_history": [0.20, 0.25, 0.30],
        "my_offer_history": [0.85, 0.78, 0.70],
        "deadline_rounds": 10,
    }
    accepts = []
    for knob in [0.0, 0.5, 1.0]:
        r = sell_next_offer(**history_args, pareto_knob=knob)
        accepts.append(r["acceptance_probability"])
    assert accepts[0] >= accepts[-1], \
        f"acceptance should decrease with knob: {accepts}"


def test_sell_validates_inputs():
    """Bad inputs raise ValueError, not silent garbage."""
    with pytest.raises(ValueError):
        sell_next_offer(my_reservation=1.5, opponent_offer_history=[],
                         my_offer_history=[], deadline_rounds=10)
    with pytest.raises(ValueError):
        sell_next_offer(my_reservation=0.4, opponent_offer_history=[],
                         my_offer_history=[], deadline_rounds=10, pareto_knob=2.0)
    with pytest.raises(ValueError):
        sell_next_offer(my_reservation=0.4, opponent_offer_history=[],
                         my_offer_history=[], deadline_rounds=0)


# ─── HTTP integration ────────────────────────────────────────────────────────


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_catalog_lists_all_tools():
    r = client.get("/v1/catalog")
    assert r.status_code == 200
    body = r.json()
    tool_names = {t["name"] for t in body["tools"]}
    expected = {
        "gt.negotiation.sell.next_offer",
        "gt.auction.bidder.optimal_bid",
        "gt.auction.seller.optimal_reserve",
        "gt.auction.seller.format_recommendation",
        "gt.auction.simulate",
    }
    assert expected.issubset(tool_names), f"missing tools: {expected - tool_names}"
    # All Sprint 1 tools are free (Sprint 2 may add paid tools).
    for t in body["tools"]:
        if t["name"] in expected:
            assert t["cost_class"] == "free"


def test_llms_txt_readable():
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert "Game Theory Layer" in r.text
    assert "/v1/negotiation/sell/next_offer" in r.text
    assert "Tier 1" in r.text and "Tier 2" in r.text


def test_openapi_spec():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["openapi"].startswith("3.")
    # Verify all our endpoints are documented
    paths = spec["paths"]
    required = [
        "/v1/negotiation/sell/next_offer",
        "/v1/auction/bidder/optimal_bid",
        "/v1/auction/seller/optimal_reserve",
        "/v1/keys",
        "/v1/catalog",
    ]
    for p in required:
        assert p in paths, f"OpenAPI missing path {p}"


def test_sell_endpoint_returns_cost_headers():
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.2, 0.3],
            "my_offer_history": [0.8],
            "deadline_rounds": 10,
            "pareto_knob": 0.5,
        },
    )
    assert r.status_code == 200
    assert r.headers["X-GT-Cost-USD"] == "0"
    assert "X-GT-Latency-Ms" in r.headers
    body = r.json()
    assert 0.0 <= body["recommended_offer"] <= 1.0
    assert "rationale" in body
    assert "posterior" in body


def test_auction_endpoint_validates_format():
    r = client.post(
        "/v1/auction/bidder/optimal_bid",
        json={
            "auction_format": "definitely_not_a_real_format",
            "my_valuation": 100,
            "n_competing_bidders": 3,
            "competitor_value_prior": {"family": "uniform", "params": {"low": 0, "high": 100}},
        },
    )
    assert r.status_code == 400


# ─── Onboarding ──────────────────────────────────────────────────────────────


def test_key_issuance_idempotent():
    """Same agent_id within 24h returns the same key."""
    body = {
        "agent_id": "test-agent-001",
        "contact_email": "test@example.com",
        "intended_use_summary": "Acceptance testing the issuance endpoint",
    }
    r1 = client.post("/v1/keys", json=body)
    assert r1.status_code == 200
    key1 = r1.json()["api_key"]
    assert key1.startswith("gt_")
    assert r1.json()["reused"] is False

    r2 = client.post("/v1/keys", json=body)
    assert r2.status_code == 200
    assert r2.json()["api_key"] == key1
    assert r2.json()["reused"] is True


def test_key_issuance_validation():
    r = client.post("/v1/keys", json={
        "agent_id": "x",  # too short
        "contact_email": "ok@example.com",
        "intended_use_summary": "long enough description",
    })
    assert r.status_code == 422  # pydantic validation
    r = client.post("/v1/keys", json={
        "agent_id": "valid-agent",
        "contact_email": "not-an-email",  # bad email
        "intended_use_summary": "long enough description",
    })
    # The pydantic model allows any string; our handler rejects emails without @.
    assert r.status_code in (400, 422)

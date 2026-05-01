"""
Integration tests for the peer_mode parameter on negotiation endpoints.

Caught a real production bug on 2026-04-30: peer_mode=True returned an
HTTP 500 because the cooperative-mode return dict was missing
`rubinstein_share` and `schelling_floor` fields that the response schema
required. The fix added schema-compatible defaults for those fields in
peer-mode returns. These tests pin the contract so the regression
can't reappear.

Coverage:
  - Sell-side peer_mode=True returns valid SellNextOfferResponse
  - Buy-side peer_mode=True returns valid BuyNextOfferResponse
  - peer_mode default (omitted) produces non-peer recommendation
  - Full E2E flow: issue key → call sell with peer_mode=True → 200 OK
  - Both signaling phase (rounds 0-1) and descent phase (rounds 2+) work
"""
import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_peer_mode.db")
os.environ["TELEMETRY_PEPPER"] = "test_pepper_peer_mode_DO_NOT_USE_xxxx" * 2

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server.http import app  # noqa: E402

client = TestClient(app)


def _issue_key(agent_id: str) -> str:
    """Issue a fresh API key and return it."""
    r = client.post(
        "/v1/keys",
        json={
            "agent_id": agent_id,
            "contact_email": f"{agent_id}@test.example",
            "intended_use_summary": "peer_mode integration test",
            "telemetry_consent": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


# ─── Direct function tests ──────────────────────────────────────────────────


def test_sell_peer_mode_true_returns_schema_compat_dict():
    """Direct call: peer_mode=True must return all fields the response
    schema requires (including rubinstein_share and schelling_floor)."""
    from gametheory.negotiation.sell import sell_next_offer
    from gametheory.server.http import SellNextOfferResponse

    result = sell_next_offer(
        my_reservation=0.40,
        opponent_offer_history=[0.55, 0.62],
        my_offer_history=[0.85, 0.78],
        deadline_rounds=8,
        peer_mode=True,
    )

    # Required schema fields
    for key in ("recommended_offer", "acceptance_probability",
                 "expected_payoff", "rationale", "posterior",
                 "rubinstein_share", "schelling_floor"):
        assert key in result, f"missing schema field: {key}"

    # Peer-mode-specific fields
    assert result["peer_mode"] is True
    assert result["peer_phase"] in ("peer_signaling", "peer_descent")

    # Validates against the response model (this is the test that would
    # have caught the production 500)
    SellNextOfferResponse.model_validate(result)


def test_buy_peer_mode_true_returns_schema_compat_dict():
    from gametheory.negotiation.buy import buy_next_offer
    from gametheory.server.http import BuyNextOfferResponse

    result = buy_next_offer(
        my_reservation=0.40,
        seller_offer_history=[0.55, 0.62],
        my_offer_history=[0.15, 0.22],
        deadline_rounds=8,
        peer_mode=True,
    )

    for key in ("recommended_offer", "acceptance_probability",
                 "expected_payoff", "rationale", "posterior",
                 "rubinstein_share", "warnings", "defense_actions"):
        assert key in result, f"missing schema field: {key}"

    assert result["peer_mode"] is True
    BuyNextOfferResponse.model_validate(result)


def test_peer_mode_signaling_phase_high_target():
    """Rounds 0-1: peer-mode advisor should recommend max-self (~0.95)
    for signaling. This is the cooperative architecture."""
    from gametheory.negotiation.sell import sell_next_offer

    # Empty history → round 0 → signaling phase
    result = sell_next_offer(
        my_reservation=0.40,
        opponent_offer_history=[],
        my_offer_history=[],
        deadline_rounds=8,
        peer_mode=True,
    )
    assert result["peer_phase"] == "peer_signaling"
    assert result["recommended_offer"] >= 0.90, (
        f"signaling phase should recommend high target, got {result['recommended_offer']}"
    )


def test_peer_mode_descent_phase_lower_target():
    """Rounds 2+: peer-mode advisor descends toward asp_floor (0.55)."""
    from gametheory.negotiation.sell import sell_next_offer

    # 3 rounds of history → past signaling phase
    result = sell_next_offer(
        my_reservation=0.40,
        opponent_offer_history=[0.10, 0.20, 0.30],
        my_offer_history=[0.95, 0.92, 0.85],
        deadline_rounds=8,
        peer_mode=True,
    )
    assert result["peer_phase"] == "peer_descent"
    assert 0.45 <= result["recommended_offer"] <= 0.95, (
        f"descent phase should be in valid range, got {result['recommended_offer']}"
    )


def test_peer_mode_default_off_uses_rubinstein():
    """When peer_mode is omitted, fall back to standard Rubinstein-aspiration."""
    from gametheory.negotiation.sell import sell_next_offer

    result = sell_next_offer(
        my_reservation=0.40,
        opponent_offer_history=[0.55, 0.62],
        my_offer_history=[0.85, 0.78],
        deadline_rounds=8,
        # peer_mode omitted; defaults to False
    )
    # Standard descent doesn't include peer_mode flag
    assert "peer_mode" not in result or not result.get("peer_mode")
    # Standard mode populates posterior with Bayesian inference fields
    assert result["posterior"]["n_particles"] > 0


# ─── HTTP integration tests (the actual production path) ───────────────────


def test_http_sell_peer_mode_true_returns_200():
    """The end-to-end flow that returned 500 in production. After the fix
    this must return 200 OK with a valid response body."""
    api_key = _issue_key("peer_mode_sell_test")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "my_reservation": 0.40,
            "opponent_offer_history": [0.55, 0.62],
            "my_offer_history": [0.85, 0.78],
            "deadline_rounds": 8,
            "pareto_knob": 0.5,
            "peer_mode": True,
        },
    )
    assert r.status_code == 200, (
        f"peer_mode=True must return 200, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "recommended_offer" in body
    assert "rubinstein_share" in body
    assert "schelling_floor" in body


def test_http_buy_peer_mode_true_returns_200():
    api_key = _issue_key("peer_mode_buy_test")
    r = client.post(
        "/v1/negotiation/buy/next_offer",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "my_reservation": 0.40,
            "seller_offer_history": [0.55, 0.62],
            "my_offer_history": [0.15, 0.22],
            "deadline_rounds": 8,
            "peer_mode": True,
        },
    )
    assert r.status_code == 200, (
        f"buy peer_mode=True must return 200, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "recommended_offer" in body
    assert "rubinstein_share" in body
    assert "warnings" in body
    assert "defense_actions" in body


def test_http_sell_peer_mode_false_unaffected():
    """Regression check: peer_mode=False (or omitted) still works
    after the fix."""
    api_key = _issue_key("peer_mode_sell_off")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "my_reservation": 0.40,
            "opponent_offer_history": [0.55, 0.62],
            "my_offer_history": [0.85, 0.78],
            "deadline_rounds": 8,
            "pareto_knob": 0.5,
            # peer_mode omitted intentionally
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Standard mode populates Bayesian posterior fields
    assert body["posterior"]["n_particles"] > 0


# ─── Full /llms.txt-promised flow ───────────────────────────────────────────


def test_full_agent_onboarding_flow():
    """End-to-end: an agent follows the /llms.txt promise — read the doc,
    issue a key, call the headline endpoint with peer_mode=True. This is
    the EXACT flow that returned 500 in production. Pin it forever."""
    # Step 1: read /llms.txt (anchors the empirical claim)
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert "Empirical anchor" in r.text
    assert "peer_mode" in r.text or "PEER" in r.text

    # Step 2: issue key
    api_key = _issue_key("full_flow_test")
    assert api_key.startswith("gt_")

    # Step 3: call sell with peer_mode (the failing path)
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "my_reservation": 0.40,
            "opponent_offer_history": [0.55, 0.62],
            "my_offer_history": [0.85, 0.78],
            "deadline_rounds": 8,
            "peer_mode": True,
        },
    )
    assert r.status_code == 200, f"E2E flow broken: {r.text}"

    # Step 4: catalog discovery
    r = client.get("/v1/catalog")
    assert r.status_code == 200
    catalog = r.json()
    tool_names = [t["name"] for t in catalog.get("tools", [])]
    # Catalog uses dotted naming: gt.negotiation.sell.next_offer
    assert any("sell" in n and "next_offer" in n for n in tool_names), (
        f"sell next_offer not in catalog: {tool_names}"
    )

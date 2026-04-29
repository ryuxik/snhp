"""
Integration tests — end-to-end workflows, middleware, and cross-endpoint flows.

These complement the per-endpoint unit tests in test_sprint{1,2,3}.py and
test_telemetry.py. The focus here is on:

  1. Recipe walk-throughs (the workflows /llms.txt promises). If an agent
     follows the published recipe, does the chain of endpoints actually work?
  2. Middleware (rate limits, body size, security headers) — exercised
     through the real TestClient stack, not unit-tested in isolation.
  3. Telemetry breadth on the four non-sell recommendation endpoints
     (sell is already covered in test_telemetry.py).
  4. Cross-key isolation under concurrent telemetry use.

Each test resets module-global state (rate-limit buckets) where it could
otherwise leak into other tests.
"""
import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_integration.db")
os.environ["TELEMETRY_PEPPER"] = "test_pepper_integration_DO_NOT_USE_x" * 2

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server.http import app  # noqa: E402
from gametheory.server import middleware as _mw  # noqa: E402
from gametheory.server import telemetry as _telemetry  # noqa: E402


@pytest.fixture
def client():
    """Fresh TestClient + cleared rate-limit buckets per test."""
    _mw._BUCKETS.clear()
    return TestClient(app)


def _issue_key(client, agent_id: str, *, telemetry_consent: bool = False) -> str:
    r = client.post("/v1/keys", json={
        "agent_id": agent_id,
        "contact_email": f"{agent_id}@test.invalid",
        "intended_use_summary": "integration test",
        "telemetry_consent": telemetry_consent,
    })
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


# ─── Recipe 1: sell-side multi-round + telemetry lifecycle ──────────────────


def test_recipe_sell_multi_round_with_telemetry(client):
    """Full sell-side lifecycle: issue consenting key, three rounds of
    next_offer, report outcome, export, delete. Each round records a
    separate telemetry row tied to the same key."""
    api_key = _issue_key(client, "recipe_sell", telemetry_consent=True)
    auth = {"Authorization": f"Bearer {api_key}"}

    rec_ids = []
    opp_history: list[float] = []
    my_history: list[float] = []
    for round_n, opp_offer in enumerate([0.40, 0.50, 0.58]):
        opp_history.append(opp_offer)
        r = client.post("/v1/negotiation/sell/next_offer", headers=auth, json={
            "my_reservation": 0.4,
            "opponent_offer_history": opp_history,
            "my_offer_history": my_history,
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "saas_procurement",
        })
        assert r.status_code == 200
        recommended = r.json()["recommended_offer"]
        my_history.append(recommended)
        rec_ids.append(r.headers["X-GT-Recommendation-Id"])

    assert len(set(rec_ids)) == 3, "each round must have a distinct rec_id"

    # Outcome attaches to the LAST round's rec_id (the one that closed the deal).
    r2 = client.post("/v1/telemetry/report_outcome", headers=auth, json={
        "recommendation_id": rec_ids[-1],
        "deal_closed": True,
        "my_utility": 0.65,
        "opponent_utility": 0.35,
    })
    assert r2.status_code == 200 and r2.json()["accepted"]

    rows = client.get("/v1/telemetry/export", headers=auth).json()["rows"]
    assert len(rows) == 3
    closed = [r for r in rows if r["outcome"] is not None]
    assert len(closed) == 1
    assert closed[0]["recommendation_id"] == rec_ids[-1]
    assert closed[0]["outcome"]["deal_closed"] is True

    # GDPR delete sweeps all three.
    r3 = client.delete("/v1/telemetry/delete", headers=auth)
    assert r3.json()["rows_deleted"] == 3
    assert client.get("/v1/telemetry/export", headers=auth).json()["rows"] == []


# ─── Recipe 2: buy-side first-strike workflow ───────────────────────────────


def test_recipe_buy_side_first_strike_workflow(client):
    """The headline buy-side recipe from /llms.txt: detect anchor →
    declare_first_strike → reveal_first_strike. Uses the cryptographic
    commit-reveal path that converts buyer to first-mover-on-reservation."""
    import secrets
    from datetime import datetime, timedelta, timezone

    from gametheory.crypto.first_strike import commit_hash

    api_key = _issue_key(client, "recipe_buy")
    auth = {"Authorization": f"Bearer {api_key}"}

    # Step 1: detect that the seller's opening is a 3-sigma anchor. Note:
    # opponent_offer_history is in BUYER utility space — seller asking high
    # = buyer utility low. 0.20 against (mu=0.55, sigma=0.10) is z=-3.5.
    r1 = client.post("/v1/negotiation/detect_anchor_attack", headers=auth, json={
        "opponent_offer_history": [0.20],
        "market_prior": {"mu": 0.55, "sigma": 0.10},
    })
    assert r1.status_code == 200
    assert r1.json()["is_anchor_attack"] is True

    # Step 2: commit to a reservation hash via the canonical helper.
    reservation = 0.42
    nonce = secrets.token_urlsafe(16)
    salt = secrets.token_urlsafe(16)
    buyer_id = "buyer_recipe"
    seller_id = "seller_recipe"
    reservation_hash = commit_hash(reservation, nonce, salt, buyer_id, seller_id)
    deadline_iso = (datetime.now(timezone.utc) + timedelta(hours=2)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")

    r2 = client.post("/v1/negotiation/declare_first_strike", headers=auth, json={
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "reservation_hash": reservation_hash,
        "deadline_iso": deadline_iso,
        "binding_ttl_seconds": 3600,
    })
    assert r2.status_code == 200, r2.text
    commitment_id = r2.json()["commitment_id"]
    assert r2.json()["attestation_jwt"]
    assert r2.json()["trust_anchor_public_key_pem"].startswith("-----BEGIN")

    # Step 3: at acceptance time, reveal — server checks the hash matches.
    r3 = client.post("/v1/negotiation/reveal_first_strike", headers=auth, json={
        "commitment_id": commitment_id,
        "reservation": reservation,
        "nonce": nonce,
        "salt": salt,
    })
    assert r3.status_code == 200, r3.text
    assert r3.json()["verified"] is True
    assert r3.json()["binding_offer"] == reservation


# ─── Recipe 3: marketplace operator + bidder cross-tier ────────────────────


def test_recipe_marketplace_operator_plus_bidder(client):
    """Same Myerson math, two perspectives: operator designs the auction,
    bidders bid into it. Asserts the operator's recommended reserve is
    consistent with what a bidder would optimally bid."""
    api_key = _issue_key(client, "recipe_market")
    auth = {"Authorization": f"Bearer {api_key}"}

    # Operator: design the auction over symmetric uniform[0, 1] bidders.
    r1 = client.post("/v1/mechanism/optimal_auction_design", headers=auth, json={
        "bidder_priors": [
            {"family": "uniform", "params": {"low": 0.0, "high": 1.0}},
            {"family": "uniform", "params": {"low": 0.0, "high": 1.0}},
            {"family": "uniform", "params": {"low": 0.0, "high": 1.0}},
        ],
        "seller_valuation": 0.0,
        "objective": "revenue",
        "n_simulations": 1000,
    })
    assert r1.status_code == 200, r1.text
    reserves = r1.json()["reserve_prices"]
    assert all(abs(v - 0.5) < 0.05 for v in reserves.values()), \
        "Myerson reserve for U[0,1] is 0.5"

    # Bidder: bid into the same auction. Vickrey is dominant-strategy
    # truthful, so my optimal_bid == my_valuation regardless of reserve.
    r2 = client.post("/v1/auction/bidder/optimal_bid", headers=auth, json={
        "auction_format": "second_price_vickrey",
        "my_valuation": 0.7,
        "n_competing_bidders": 2,
        "competitor_value_prior": {
            "family": "uniform",
            "params": {"low": 0.0, "high": 1.0},
        },
        "reserve_price": list(reserves.values())[0],
    })
    assert r2.status_code == 200
    assert r2.json()["dominant_strategy"] is True
    assert r2.json()["optimal_bid"] == 0.7


# ─── Middleware: rate limiting ──────────────────────────────────────────────


def test_rate_limit_issue_key_per_ip(client):
    """/v1/keys is capped at 10 per IP per hour. The 11th must 429."""
    body = {
        "agent_id": "ratelimit_dummy",
        "contact_email": "ratelimit@test.invalid",
        "intended_use_summary": "rate limit test",
    }
    statuses = [client.post("/v1/keys", json=body).status_code
                for _ in range(11)]
    # First 10 succeed (or return 200 with reused=True after the first); the
    # 11th must hit the rate limit.
    assert statuses[-1] == 429
    assert all(s == 200 for s in statuses[:10])


def test_rate_limit_math_per_ip_unauthed(client):
    """Math endpoints have a 60/min per-IP fallback when no bearer key.
    61st request from same IP must 429."""
    body = {
        "auction_format": "second_price_vickrey",
        "my_valuation": 0.5,
        "n_competing_bidders": 2,
        "competitor_value_prior": {
            "family": "uniform", "params": {"low": 0.0, "high": 1.0},
        },
    }
    statuses = []
    for _ in range(61):
        r = client.post("/v1/auction/bidder/optimal_bid", json=body)
        statuses.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in statuses, "per-IP rate limit must trigger before 61 hits"


def test_first_strike_per_ip_rate_limit(client):
    """First-strike commit/reveal capped at 30/min per IP."""
    body = {
        "buyer_id": "b", "seller_id": "s",
        "reservation_hash": "A" * 43,  # 43-char base64url, valid pattern
        "deadline_iso": "2099-01-01T00:00:00Z",
        "binding_ttl_seconds": 3600,
    }
    saw_429 = False
    for _ in range(31):
        r = client.post("/v1/negotiation/declare_first_strike", json=body)
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "first-strike per-IP cap must trigger within 31 attempts"


# ─── Middleware: body size + security headers ──────────────────────────────


def test_body_size_limit_413(client):
    """Content-Length > 1 MiB is rejected before the body is buffered."""
    big_payload = "x" * (2 * 1024 * 1024)  # 2 MiB string
    r = client.post(
        "/v1/auction/bidder/optimal_bid",
        content=big_payload,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_security_headers_present_on_every_response(client):
    """HSTS, frame-ancestors, content-type-sniff, referrer policy must
    be set on responses regardless of route."""
    r = client.get("/health")
    assert r.headers.get("strict-transport-security", "").startswith("max-age=")
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers.get("content-security-policy", "")


def test_security_headers_present_on_error_response(client):
    """4xx responses must still carry security headers (no leak via error)."""
    r = client.post("/v1/auction/bidder/optimal_bid", json={"bogus": "input"})
    assert r.status_code == 422
    assert r.headers.get("x-frame-options") == "DENY"


# ─── Telemetry breadth on the four non-sell endpoints ──────────────────────


_UNIFORM_01 = {"family": "uniform", "params": {"low": 0.0, "high": 1.0}}

# (test-id, path, body, expected_endpoint_in_telemetry, expected_vertical)
_TELEMETRY_BREADTH_CASES = [
    (
        "buy_next_offer",
        "/v1/negotiation/buy/next_offer",
        {"my_reservation": 0.5, "seller_offer_history": [0.9],
         "my_offer_history": [], "deadline_rounds": 8,
         "vertical": "freight_logistics"},
        "negotiation/buy/next_offer",
        "freight_logistics",
    ),
    (
        "optimal_bid",
        "/v1/auction/bidder/optimal_bid",
        {"auction_format": "second_price_vickrey", "my_valuation": 0.7,
         "n_competing_bidders": 2, "competitor_value_prior": _UNIFORM_01,
         "vertical": "ad_inventory"},
        "auction/bidder/optimal_bid",
        "ad_inventory",
    ),
    (
        "optimal_auction_design",
        "/v1/mechanism/optimal_auction_design",
        {"bidder_priors": [_UNIFORM_01, _UNIFORM_01], "seller_valuation": 0.0,
         "objective": "revenue", "n_simulations": 500,
         "vertical": "marketplace_b2b"},
        "mechanism/optimal_auction_design",
        "marketplace_b2b",
    ),
    (
        "posted_price",
        "/v1/mechanism/posted_price_optimal",
        {"buyer_arrival_prior": _UNIFORM_01, "arrival_rate_per_second": 1.0,
         "inventory": 10, "horizon_seconds": 60.0, "n_simulations": 200,
         "vertical": "real_estate"},
        "mechanism/posted_price_optimal",
        "real_estate",
    ),
]


@pytest.mark.parametrize(
    "test_id, path, body, expected_endpoint, expected_vertical",
    _TELEMETRY_BREADTH_CASES,
    ids=[c[0] for c in _TELEMETRY_BREADTH_CASES],
)
def test_telemetry_records_for_each_endpoint(
    client, test_id, path, body, expected_endpoint, expected_vertical,
):
    api_key = _issue_key(client, f"telem_{test_id}", telemetry_consent=True)
    auth = {"Authorization": f"Bearer {api_key}"}
    r = client.post(path, headers=auth, json={**body, "share_outcome": True})
    assert r.status_code == 200, r.text
    rec_id = r.headers["X-GT-Recommendation-Id"]
    rows = client.get("/v1/telemetry/export", headers=auth).json()["rows"]
    matching = [row for row in rows if row["recommendation_id"] == rec_id]
    assert matching, f"no telemetry row for {test_id}"
    assert matching[0]["endpoint"] == expected_endpoint
    assert matching[0]["vertical"] == expected_vertical


# ─── Cross-key isolation ────────────────────────────────────────────────────


def test_cross_key_telemetry_isolation(client):
    """Two consenting agents writing concurrently must not see each
    other's rows in export, and one's delete must not touch the other."""
    key_a = _issue_key(client, "iso_a", telemetry_consent=True)
    key_b = _issue_key(client, "iso_b", telemetry_consent=True)
    auth_a = {"Authorization": f"Bearer {key_a}"}
    auth_b = {"Authorization": f"Bearer {key_b}"}

    body = {
        "my_reservation": 0.4,
        "opponent_offer_history": [0.6],
        "my_offer_history": [],
        "deadline_rounds": 8,
        "share_outcome": True,
        "vertical": "ad_inventory",
    }
    client.post("/v1/negotiation/sell/next_offer", headers=auth_a, json=body)
    client.post("/v1/negotiation/sell/next_offer", headers=auth_b, json=body)

    rows_a = client.get("/v1/telemetry/export", headers=auth_a).json()["rows"]
    rows_b = client.get("/v1/telemetry/export", headers=auth_b).json()["rows"]
    ids_a = {r["recommendation_id"] for r in rows_a}
    ids_b = {r["recommendation_id"] for r in rows_b}
    assert ids_a and ids_b
    assert ids_a.isdisjoint(ids_b), "rec_ids must not leak across agents"

    # Delete A — B's rows must remain.
    deleted = client.delete("/v1/telemetry/delete", headers=auth_a).json()["rows_deleted"]
    assert deleted == len(ids_a)
    rows_b_after = client.get("/v1/telemetry/export", headers=auth_b).json()["rows"]
    assert len(rows_b_after) == len(rows_b)


# ─── Failure modes ──────────────────────────────────────────────────────────


def test_share_outcome_without_pepper_raises(monkeypatch):
    """If the operator forgot to set TELEMETRY_PEPPER, share_outcome=True
    must fail loud (not silently swallow). Per V1 design — silent no-op
    on a privacy-sensitive flag would be a privacy lie."""
    _mw._BUCKETS.clear()
    # raise_server_exceptions=False so 500 is returned rather than re-raised
    # by TestClient — we want to assert on the response code, not the trace.
    local_client = TestClient(app, raise_server_exceptions=False)
    api_key = _issue_key(local_client, "no_pepper", telemetry_consent=True)
    monkeypatch.delenv("TELEMETRY_PEPPER", raising=False)
    r = local_client.post("/v1/negotiation/sell/next_offer", headers={
        "Authorization": f"Bearer {api_key}",
    }, json={
        "my_reservation": 0.4,
        "opponent_offer_history": [0.6],
        "my_offer_history": [],
        "deadline_rounds": 8,
        "share_outcome": True,
        "vertical": "ad_inventory",
    })
    assert r.status_code == 500


def test_invalid_vertical_rejected_at_validation(client):
    """vertical is a Literal allowlist; arbitrary strings rejected by
    Pydantic (covert-channel risk)."""
    api_key = _issue_key(client, "bad_vert", telemetry_consent=True)
    r = client.post("/v1/negotiation/sell/next_offer", headers={
        "Authorization": f"Bearer {api_key}",
    }, json={
        "my_reservation": 0.4,
        "opponent_offer_history": [0.6],
        "my_offer_history": [],
        "deadline_rounds": 8,
        "share_outcome": True,
        "vertical": "my_secret_steganography_channel",
    })
    assert r.status_code == 422


def test_telemetry_endpoints_reject_unknown_key(client):
    """A bearer that doesn't exist in keys table — report_outcome must
    return accepted=False (no row), delete returns 0, export returns []."""
    fake_key = "gt_FAKEKEY_does_not_exist_in_db_zzzzzzz"
    auth = {"Authorization": f"Bearer {fake_key}"}
    r1 = client.post("/v1/telemetry/report_outcome", headers=auth, json={
        "recommendation_id": "rec_xxx",
        "deal_closed": True,
    })
    assert r1.status_code == 200 and r1.json()["accepted"] is False
    r2 = client.delete("/v1/telemetry/delete", headers=auth)
    assert r2.status_code == 200 and r2.json()["rows_deleted"] == 0
    r3 = client.get("/v1/telemetry/export", headers=auth)
    assert r3.status_code == 200 and r3.json()["rows"] == []


# ─── Discovery surface stays consistent ────────────────────────────────────


def test_openapi_includes_telemetry_routes(client):
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"].keys())
    assert "/v1/telemetry/report_outcome" in paths
    assert "/v1/telemetry/delete" in paths
    assert "/v1/telemetry/export" in paths


def test_llms_txt_documents_telemetry(client):
    body = client.get("/llms.txt").text
    assert "telemetry" in body.lower()
    assert "share_outcome" in body
    assert "telemetry_consent" in body
    assert "GDPR" in body

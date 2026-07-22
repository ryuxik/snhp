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
# Isolate vend's NEXTMOVE telemetry (throttle / free_taste lines) to a temp
# file so the middleware/endpoint tests can read what got logged and we don't
# pollute the repo CWD.
os.environ["NEXTMOVE_TELEMETRY_PATH"] = os.path.join(_tmp_dir, "nextmove_telemetry.jsonl")

import json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server.http import app  # noqa: E402
from gametheory.server import middleware as _mw  # noqa: E402
from gametheory.server import telemetry as _telemetry  # noqa: E402


def _read_nextmove_records(kind: str | None = None) -> list[dict]:
    """All NEXTMOVE telemetry records written so far (optionally one kind)."""
    path = os.environ["NEXTMOVE_TELEMETRY_PATH"]
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if kind is None or rec.get("kind") == kind:
                out.append(rec)
    return out


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


# ─── Middleware: the keyed / keyless two-lane rate limiter (GAUNTLET.md #3) ──

_BID_BODY = {
    "auction_format": "second_price_vickrey",
    "my_valuation": 0.5,
    "n_competing_bidders": 2,
    "competitor_value_prior": {"family": "uniform",
                               "params": {"low": 0.0, "high": 1.0}},
}


def test_keyed_traffic_bypasses_the_per_ip_free_floor(client):
    """The core GAUNTLET.md #3 fix: a request presenting a key credential is
    limited on the 600/min per-key bucket ONLY — it must NOT be throttled by
    the 60/min per-IP free floor that keyless traffic shares. So 120 keyed
    calls (2x the per-IP floor) all succeed."""
    hdr = {"Authorization": "Bearer gt_keyed_lane_probe"}
    codes = [client.post("/v1/auction/bidder/optimal_bid",
                         json=_BID_BODY, headers=hdr).status_code
             for _ in range(120)]
    assert all(c == 200 for c in codes), \
        "keyed traffic must not hit the 60/min per-IP floor"


def test_x_api_key_header_gets_the_same_keyed_lane(client):
    """Wave 1 shipped X-API-Key on /balance; it must buy the keyed lane
    everywhere too. 120 calls carrying X-API-Key (2x the per-IP floor) all
    succeed."""
    hdr = {"X-API-Key": "gt_xapikey_lane_probe"}
    codes = [client.post("/v1/auction/bidder/optimal_bid",
                         json=_BID_BODY, headers=hdr).status_code
             for _ in range(120)]
    assert all(c == 200 for c in codes), \
        "X-API-Key must be honored as a key credential for rate limiting"


def test_keyless_traffic_is_still_floored_at_60_per_ip(client):
    """The free floor stays real: keyless callers 429 by the 61st hit, and the
    429 detail names the math_per_ip scope (not the per-key scope)."""
    saw = None
    for _ in range(80):
        r = client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY)
        if r.status_code == 429:
            saw = r
            break
    assert saw is not None, "keyless per-IP floor must trigger within 80 hits"
    assert "math_per_ip" in saw.json()["detail"]


def test_body_only_key_does_not_escape_the_per_ip_floor(client):
    """A key sent only in the JSON body is invisible to the header-only
    limiter, so such callers stay on the per-IP floor (documented behavior —
    header required for the keyed lane). They 429 like keyless traffic."""
    body = {**_BID_BODY, "api_key": "gt_body_only_key"}
    saw_429 = False
    for _ in range(80):
        r = client.post("/v1/auction/bidder/optimal_bid", json=body)
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "a body-only key must not lift the per-IP floor"


def test_fake_key_fanout_bounded_by_per_ip_backstop(client):
    """REGRESSION (per-IP floor bypass): bearer_api_key is shape-only, so a UNIQUE
    fake gt_ token per request used to mint an endless supply of fresh, full 600/min
    lanes and fan out UNBOUNDED from one IP — evading every per-IP cap. Now a per-IP
    BACKSTOP (math_keyed_per_ip) bounds total keyed volume per IP. Pre-drain that
    shared backstop to prove the bound cheaply: two DISTINCT fake keys, and the
    second 429s on the backstop even though its OWN per-key lane is fresh."""
    ip = "testclient"  # the client host Starlette's TestClient presents (_client_ip)
    _mw._bucket_for("math_keyed_per_ip", ip).tokens = 1.0  # room for one more keyed req
    r1 = client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY,
                     headers={"Authorization": "Bearer gt_fanout_a"})
    r2 = client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY,
                     headers={"Authorization": "Bearer gt_fanout_b"})
    assert r1.status_code == 200, "first keyed req consumes the last backstop token"
    assert r2.status_code == 429, "a distinct fake key can't mint an unbounded lane"
    assert "math_keyed_per_ip" in r2.json()["detail"]


def test_per_ip_keyed_backstop_sits_above_one_key_lane(client):
    """The backstop must never throttle a single real key: its per-IP cap sits well
    above one key's 600/min lane (GAUNTLET.md #3 — paid traffic isn't floored). A
    burst on ONE key stays 200, and the backstop cap strictly exceeds the per-key
    cap so a full-rate single key can't reach it."""
    assert _mw._LIMITS["math_keyed_per_ip"][0] > _mw._LIMITS["math_per_key"][0]
    hdr = {"Authorization": "Bearer gt_single_real_key"}
    codes = [client.post("/v1/auction/bidder/optimal_bid",
                         json=_BID_BODY, headers=hdr).status_code
             for _ in range(150)]  # 150 < 600 per-key and < 3000 backstop
    assert all(c == 200 for c in codes), "one real key must not hit the backstop"


def test_keyed_lane_429_carries_retry_after(client):
    """When the per-key 600/min bucket IS exhausted, the 429 still carries a
    sane Retry-After. Drain the bucket deterministically (600 sequential
    TestClient calls refill faster than they drain) then make one keyed call."""
    key = "gt_drain_probe"
    bucket = _mw._bucket_for("math_per_key", key)
    bucket.tokens = 0.0  # force the next take() to fail
    r = client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY,
                    headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 429
    assert "math_per_key" in r.json()["detail"]
    ra = r.headers.get("Retry-After")
    assert ra is not None, "the persona was wrong: Retry-After IS present"
    assert ra.isdigit() and int(ra) >= 1


def test_retry_after_present_and_honest_on_per_ip_429(client):
    """Settle the persona claim that Retry-After was missing: the per-IP 429
    carries an integer Retry-After >= 1 (whole seconds until a token frees)."""
    ra = None
    for _ in range(80):
        r = client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY)
        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            break
    assert ra is not None, "per-IP 429 must carry Retry-After"
    assert ra.isdigit() and int(ra) >= 1


def test_retry_after_scales_with_the_refill_rate(client):
    """Honesty check: a slow-refilling bucket (issuance, 10/hour) must report a
    much larger Retry-After than the 1s per-IP math floor — not a constant."""
    body = {"agent_id": "retry_after_probe",
            "contact_email": "ra@test.invalid",
            "intended_use_summary": "retry-after honesty test"}
    ra = None
    for _ in range(12):
        r = client.post("/v1/keys", json=body)
        if r.status_code == 429:
            ra = int(r.headers["Retry-After"])
            break
    assert ra is not None, "issuance cap must trigger within 12 hits"
    # 10 tokens / 3600s => ~360s to refill one. Must be far above the 1s floor.
    assert ra > 60, f"slow bucket Retry-After should be large, got {ra}"


def test_throttle_telemetry_written_on_429(client):
    """A 429 emits one NEXTMOVE throttle line so demand the rate limiter drops
    is countable by the R-gate instruments (GAUNTLET.md #3 instrument gap).
    The keyless case records had_key=False and no repeat_key."""
    before = len(_read_nextmove_records("throttle"))
    for _ in range(80):
        if client.post("/v1/auction/bidder/optimal_bid",
                       json=_BID_BODY).status_code == 429:
            break
    recs = _read_nextmove_records("throttle")
    assert len(recs) > before, "a 429 must write a throttle telemetry line"
    last = recs[-1]
    assert last["scope"] == "math_per_ip"
    assert last["had_key"] is False
    assert last["repeat_key"] is None
    assert last["path"] == "/v1/auction/bidder/optimal_bid"


def test_throttle_telemetry_hashes_key_never_raw(client):
    """When a key was presented, the throttle line carries had_key=True and a
    repeat_key HASH — never the raw token."""
    key = "gt_throttle_hash_probe"
    _mw._bucket_for("math_per_key", key).tokens = 0.0
    client.post("/v1/auction/bidder/optimal_bid", json=_BID_BODY,
                headers={"Authorization": f"Bearer {key}"})
    recs = _read_nextmove_records("throttle")
    keyed = [r for r in recs if r["scope"] == "math_per_key"]
    assert keyed, "a keyed 429 must write a throttle line"
    last = keyed[-1]
    assert last["had_key"] is True
    assert last["repeat_key"] and last["repeat_key"] != key
    # No record anywhere may contain the raw key string.
    assert all(key not in json.dumps(r) for r in recs)


# ─── The free negotiate/turn taste: paid_alternative note + funnel telemetry ─


def test_free_turn_carries_paid_alternative_note(client):
    """The free /v1/negotiate/turn response includes a static `paid_alternative`
    note (data, not a nag) naming what free lacks and what the $2 session adds."""
    r = client.post("/v1/negotiate/turn", json={
        "side": "sell", "walk_away": 4000, "target": 6000,
        "counterparty_offers": [4200, 4500], "rounds_left": 6})
    assert r.status_code == 200
    note = r.json().get("paid_alternative")
    assert note and "NEXTMOVE" in note
    assert "deterministic" in note and "receipt" in note


def test_free_turn_logs_free_taste_with_hashed_key(client):
    """Keyed free usage is the top of the free->paid funnel and must be
    measurable: the free turn logs a free_taste line; a presented key is stored
    only as its repeat_key hash, never raw."""
    key = "gt_free_taste_probe"
    before = len(_read_nextmove_records("free_taste"))
    r = client.post("/v1/negotiate/turn",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"side": "sell", "walk_away": 4000, "target": 6000,
                          "counterparty_offers": [4200], "rounds_left": 6})
    assert r.status_code == 200
    recs = _read_nextmove_records("free_taste")
    assert len(recs) > before, "the free turn must log a free_taste line"
    last = recs[-1]
    assert last["door"] == "http"
    assert last["repeat_key"] and last["repeat_key"] != key
    assert all(key not in json.dumps(r) for r in recs)


# ─── MCP door: DNS-rebinding host validation (GAUNTLET.md #7) ───────────────

_MCP_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}}
_MCP_HDR = {"content-type": "application/json",
            "accept": "application/json, text/event-stream"}


def test_mcp_host_validation_accepts_legit_hosts_rejects_foreign():
    """GAUNTLET.md #7: the MCP door 421'd on a truthful Host. Covered in ONE
    test because the streamable-HTTP session manager can be run only once per
    process (its lifespan can be entered a single time) — so all Host-header
    assertions share one `with TestClient(app)` block.

      * 127.0.0.1:<port> (Host header carries the port) — the reported bug,
        must now pass validation (was a 421).
      * the real prod hostnames + bare localhost — all accepted.
      * a foreign Host — still 421 (DNS-rebinding protection stays ON), but the
        body now NAMES the accepted hosts instead of a bare 'Invalid Host
        header'.
    """
    _mw._BUCKETS.clear()
    with TestClient(app) as c:
        for host in ("127.0.0.1:8787", "api.snhp.dev", "snhp.fly.dev",
                     "localhost", "snhp.dev"):
            r = c.post("/mcp/", json=_MCP_INIT,
                       headers={**_MCP_HDR, "Host": host})
            assert r.status_code != 421, f"{host} must be an accepted Host"

        bad = c.post("/mcp/", json=_MCP_INIT,
                     headers={**_MCP_HDR, "Host": "evil.example.com"})
    assert bad.status_code == 421
    body = bad.text
    assert "api.snhp.dev" in body and "127.0.0.1" in body
    assert "localhost" in body


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

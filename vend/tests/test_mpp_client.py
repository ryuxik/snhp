"""
Tests for the reference MPP client (vend/mpp_client.py) + the acceptance
manifest route (GET /v1/mpp/manifest).

Hermetic: the client is driven against a MOCKED transport (mpp_client._http_post
is monkeypatched) so nothing networks and no real Stripe is touched. The manifest
route is exercised through a FastAPI TestClient.

The load-bearing assertion is CLIENT<->SERVER wire agreement: a credential the
reference client builds must round-trip through the SERVER's own
mpp.parse_credential + mpp.verify_challenge — i.e. our server would accept, byte
for byte, exactly what the client produces.
"""
import json
import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_mpp_client.db")
# Deterministic challenge-signing secret + a fake Stripe key (no real key used).
# Leave STRIPE_MPP_NETWORK_ID UNSET so the manifest reports live_ready == False.
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fakefakefake"
os.environ["MPP_CHALLENGE_SECRET"] = "test-mpp-client-secret"

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server import mpp, billing  # noqa: E402
from vend import mpp_client  # noqa: E402


@pytest.fixture()
def client():
    from gametheory.server.http import app
    return TestClient(app)


@pytest.fixture()
def percall_on(monkeypatch):
    monkeypatch.setenv("MPP_PERCALL_ENABLED", "1")


def _server_challenge(base_cents: int, what: str):
    """Mint a real server-side 402 challenge and return (www_authenticate, frame)."""
    frame = mpp.paid_resource_frame(base_cents=base_cents, what=what)
    ch = mpp.build_challenge(realm="api.snhp.dev", request=frame["request"],
                             description=frame["description"])
    return mpp.serialize_challenge(ch), frame


# ─── The load-bearing test: client output == server input, byte for byte ─────


def test_client_credential_roundtrips_through_server_parse_and_verify():
    # A challenge the SERVER minted, serialized to a WWW-Authenticate value.
    www, frame = _server_challenge(mpp.TOPUP_CREDIT_CENTS, "topup")
    # The CLIENT parses it and builds a credential from an SPT it holds.
    parsed = mpp_client.parse_challenge(www)
    credential = mpp_client.build_credential(parsed, "spt_test_roundtrip")
    assert credential.startswith("Payment ")
    # The SERVER's OWN parser + verifier must accept what the client produced.
    server_view = mpp.parse_credential(credential)
    assert server_view["payload"]["spt"] == "spt_test_roundtrip"
    assert mpp.verify_challenge(server_view["challenge"]) is True
    # And the verified terms are the price the frame quoted (client didn't alter them).
    assert server_view["challenge"]["request"]["amount"] == str(frame["price_cents"])
    assert server_view["challenge"]["method"] == "stripe"


def test_build_credential_requires_a_token():
    www, _ = _server_challenge(mpp.NEGOTIATE_BASE_CENTS, "turn")
    parsed = mpp_client.parse_challenge(www)
    with pytest.raises(mpp_client.MppClientError):
        mpp_client.build_credential(parsed, "")


# ─── Happy path: 402 -> retry -> 200 with a receipt, over a mocked transport ──


def test_pay_happy_path_returns_result_and_receipt(monkeypatch):
    www, _ = _server_challenge(mpp.NEGOTIATE_BASE_CENTS, "turn")
    receipt = mpp.build_receipt(method="stripe", reference="pi_test_123")
    receipt_hdr = mpp.serialize_receipt(receipt)
    captured: dict = {}

    def fake_http_post(url, body, headers, timeout):
        if "Authorization" not in headers:
            # First (unpaid) call -> the server's 402 challenge.
            return 402, {"WWW-Authenticate": www, "Accept-Payment": "stripe",
                         "Content-Type": "application/problem+json"}, b'{"status":402}'
        # Retry: capture what the client sent so we can prove the server accepts it.
        captured["auth"] = headers["Authorization"]
        captured["body"] = body
        result = {"ok": True, "paid": True, "result": {"action": "counter"},
                  "reference": "pi_test_123", "receipt": receipt}
        return 200, {"Payment-Receipt": receipt_hdr,
                     "Content-Type": "application/json"}, json.dumps(result).encode()

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)

    out = mpp_client.pay("https://api.snhp.dev", "/v1/mpp/negotiate/turn",
                         "spt_test_abc", side="sell", walk_away=4000, target=6000)
    assert out["ok"] is True
    assert out["result"]["result"]["action"] == "counter"
    assert out["receipt"]["reference"] == "pi_test_123"
    # The client re-sent the request body on the retry (not just on the challenge).
    assert json.loads(captured["body"])["side"] == "sell"
    # The credential the client built is one the SERVER would accept.
    server_view = mpp.parse_credential(captured["auth"])
    assert server_view["payload"]["spt"] == "spt_test_abc"
    assert mpp.verify_challenge(server_view["challenge"]) is True


def test_pay_reads_receipt_from_body_when_header_absent(monkeypatch):
    www, _ = _server_challenge(mpp.TOPUP_CREDIT_CENTS, "topup")
    receipt = {"method": "stripe", "reference": "pi_body_only", "status": "success"}

    def fake_http_post(url, body, headers, timeout):
        if "Authorization" not in headers:
            return 402, {"WWW-Authenticate": www}, b"{}"
        return 200, {"Content-Type": "application/json"}, \
            json.dumps({"ok": True, "receipt": receipt}).encode()

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://api.snhp.dev", "/v1/mpp/topup", "spt_x",
                         api_key="gt_1")
    assert out["ok"] is True
    assert out["receipt"]["reference"] == "pi_body_only"


# ─── Clean error handling (never a traceback) ────────────────────────────────


def test_pay_402_without_challenge_header_errors_cleanly(monkeypatch):
    def fake_http_post(url, body, headers, timeout):
        return 402, {"Content-Type": "application/problem+json"}, b'{"status":402}'

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://x", "/v1/mpp/topup", "spt_x", api_key="gt_1")
    assert out["ok"] is False
    assert out["stage"] == "challenge"
    assert "WWW-Authenticate" in out["error"]


def test_pay_non_payment_challenge_header_errors_cleanly(monkeypatch):
    def fake_http_post(url, body, headers, timeout):
        return 402, {"WWW-Authenticate": "Bearer realm=x"}, b"{}"

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://x", "/v1/mpp/topup", "spt_x", api_key="gt_1")
    assert out["ok"] is False
    assert "challenge" in out["error"].lower()


def test_pay_unexpected_first_status_errors_cleanly(monkeypatch):
    def fake_http_post(url, body, headers, timeout):
        return 500, {}, b"boom"

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://x", "/v1/mpp/topup", "spt_x")
    assert out["ok"] is False
    assert out["status"] == 500 and out["stage"] == "challenge"


def test_pay_declined_retry_returns_clean_error(monkeypatch):
    www, _ = _server_challenge(mpp.NEGOTIATE_BASE_CENTS, "turn")

    def fake_http_post(url, body, headers, timeout):
        if "Authorization" not in headers:
            return 402, {"WWW-Authenticate": www}, b"{}"
        # Settlement declined -> the server answers a fresh 402, not a 200.
        return 402, {"WWW-Authenticate": www}, b'{"status":402}'

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://x", "/v1/mpp/negotiate/turn", "spt_x")
    assert out["ok"] is False
    assert out["stage"] == "settle" and out["status"] == 402


def test_pay_free_resource_returns_200_directly(monkeypatch):
    def fake_http_post(url, body, headers, timeout):
        assert "Authorization" not in headers  # never needs to pay
        return 200, {"Content-Type": "application/json"}, b'{"ok": true, "free": true}'

    monkeypatch.setattr(mpp_client, "_http_post", fake_http_post)
    out = mpp_client.pay("https://x", "/v1/free", "spt_unused")
    assert out["ok"] is True and out["result"]["free"] is True


# ─── The acceptance manifest route (GET /v1/mpp/manifest) ────────────────────


def test_manifest_shape_and_fee_and_fence(client):
    r = client.get("/v1/mpp/manifest")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    m = r.json()

    # Accepted method is SPT/stripe only — crypto is declined (stablecoin lock).
    assert m["accepted_method"]["method"] == "stripe"
    assert m["accepted_method"]["credential"] == "shared_payment_token"
    assert m["accepted_method"]["crypto_accepted"] is False
    assert m["accept_payment_header"] == "stripe"

    # Fee STRUCTURE from the billing constants (not a hardcoded string).
    assert m["fee"]["percent"] == billing.COUNTER_FEE_PCT
    assert m["fee"]["fixed_cents"] == billing.COUNTER_FEE_FIXED_CENTS
    assert m["spt_minimum_cents"] == mpp.SPT_MIN_CENTS == 50
    assert m["settlement_api_version"] == mpp.STRIPE_SPT_PREVIEW_VERSION
    assert m["api_version_status"] == "preview"

    # The topup resource is always present, priced by paid_resource_frame
    # (200 base + 40 counter fee = 240) — the same frame the 402 charges.
    paths = [res["path"] for res in m["resources"]]
    assert "/v1/mpp/topup" in paths
    topup = next(res for res in m["resources"] if res["path"] == "/v1/mpp/topup")
    assert topup["base_cents"] == 200
    assert topup["fee_cents"] == billing.counter_fee_cents(200) == 40
    assert topup["price_cents"] == 240
    # The published challenge_request is the exact stripe/charge wire object.
    assert topup["challenge_request"]["amount"] == "240"
    assert topup["challenge_request"]["currency"] == "usd"
    assert topup["challenge_request"]["methodDetails"]["paymentMethodTypes"] == ["card", "link"]

    # Fenced by default: the keyless per-call resource is ABSENT.
    assert "/v1/mpp/negotiate/turn" not in paths

    # networkId unset -> live_ready False WITH a reason (caller not misled).
    assert m["live_ready"] is False
    assert m["network_id"] == mpp.NETWORK_ID_PLACEHOLDER
    assert "profile" in m["live_ready_reason"].lower()

    # Points at the reference client + the human on-ramp.
    assert m["reference_client"] == "vend/mpp_client.py"
    assert "checkout_session" in m["human_onramp"]


def test_manifest_includes_percall_when_fence_open(client, percall_on):
    m = client.get("/v1/mpp/manifest").json()
    paths = [res["path"] for res in m["resources"]]
    assert "/v1/mpp/negotiate/turn" in paths
    percall = next(res for res in m["resources"] if res["path"] == "/v1/mpp/negotiate/turn")
    # 100 base + 35 counter fee (5% of 100 = 5, + fixed 30) = 135.
    assert percall["base_cents"] == 100 and percall["fee_cents"] == 35
    assert percall["price_cents"] == 135


def test_manifest_live_ready_true_with_real_profile(client, monkeypatch):
    # A real profile id flips live_ready True and drops the reason.
    monkeypatch.setenv("STRIPE_MPP_NETWORK_ID", "profile_live_realone")
    m = client.get("/v1/mpp/manifest").json()
    assert m["live_ready"] is True
    assert m["network_id"] == "profile_live_realone"
    assert "live_ready_reason" not in m

"""
Tests for merchant-side MPP (gametheory/server/mpp.py + mpp_routes.py).

Hermetic: the Stripe SDK is monkeypatched (via billing._stripe), so nothing
networks. Exercises the protocol wire format (challenge build/serialize/verify,
credential parse, receipt), the SPT settlement path, and the two HTTP resources
(pay-per-call negotiation + MPP-framed wallet top-up) through a FastAPI TestClient.

The wire shapes are cross-checked against the mppx package (the validator's own
client) in the author's notes; here we assert self-consistency + the exact checks
`npx mppx validate` makes (402 challenge, WWW-Authenticate: Payment, HMAC-bound id,
fresh challenge on a malformed credential, Payment-Receipt on success).
"""
import itertools
import json
import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_mpp.db")
# Deterministic challenge-signing secret + a fake Stripe key so no real key is used.
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fakefakefake"
os.environ["MPP_CHALLENGE_SECRET"] = "test-mpp-secret"

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server import mpp, mpp_routes, billing  # noqa: E402
from gametheory.server import onboarding  # noqa: E402
from gametheory.server.onboarding import issue_key, wallet_available  # noqa: E402


# ─── Fake Stripe (mirrors test_billing's fake, top-level SPT param) ──────────


class _FakePaymentIntent:
    _by_idem: dict = {}
    _counter = itertools.count(1)

    def __init__(self, **kwargs):
        idem = kwargs.get("idempotency_key")
        if idem and idem in _FakePaymentIntent._by_idem:
            self.id = _FakePaymentIntent._by_idem[idem]
        else:
            self.id = f"pi_test_MPP_{next(_FakePaymentIntent._counter)}"
            if idem:
                _FakePaymentIntent._by_idem[idem] = self.id
        self.amount = kwargs.get("amount")
        self.currency = kwargs.get("currency")
        self.metadata = kwargs.get("metadata", {})
        self.status = "succeeded"
        # Record what the settlement sent so tests can assert the MPP param shape.
        self.kwargs = kwargs


class _FakeStripeModule:
    api_key = None

    class PaymentIntent:
        @staticmethod
        def create(**kwargs):
            assert kwargs.get("shared_payment_granted_token"), \
                "MPP settlement must pass a top-level shared_payment_granted_token"
            assert kwargs.get("stripe_version") == mpp.STRIPE_SPT_PREVIEW_VERSION
            assert "automatic_payment_methods" in kwargs
            return _FakePaymentIntent(**kwargs)


class _DecliningStripe:
    api_key = None

    class PaymentIntent:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("shared payment token declined: account not enrolled")


@pytest.fixture()
def fake_stripe(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: _FakeStripeModule)
    return _FakeStripeModule


@pytest.fixture()
def client():
    from gametheory.server.http import app
    return TestClient(app)


# ─── Protocol unit tests ─────────────────────────────────────────────────────


def test_fee_is_the_published_counter_fee():
    p = mpp.price_with_fee(mpp.NEGOTIATE_BASE_CENTS)
    assert p == {"base_cents": 100, "fee_cents": 5, "price_cents": 105}
    # The frame's fee equals billing's one counter-fee function — one fee, every rail.
    assert p["fee_cents"] == billing.counter_fee_cents(100)
    frame = mpp.paid_resource_frame(base_cents=200, what="x")
    assert "5% counter fee" in frame["description"]
    assert f"{mpp.billing.COUNTER_FEE_PCT}" in frame["description"]


def test_challenge_build_serialize_deserialize_roundtrip():
    frame = mpp.paid_resource_frame(base_cents=100, what="turn")
    ch = mpp.build_challenge(realm="api.snhp.dev", request=frame["request"],
                             description=frame["description"])
    wire = mpp.serialize_challenge(ch)
    assert wire.startswith("Payment ")
    assert 'method="stripe"' in wire and 'intent="charge"' in wire
    back = mpp.deserialize_challenge(wire)
    assert back["id"] == ch["id"]
    assert back["realm"] == "api.snhp.dev"
    assert back["request"] == frame["request"]         # request decoded to dict
    assert back["request"]["amount"] == "105"
    assert back["request"]["methodDetails"]["paymentMethodTypes"] == ["card", "link"]


def test_challenge_id_is_hmac_bound_and_tamper_evident():
    frame = mpp.paid_resource_frame(base_cents=100, what="turn")
    ch = mpp.build_challenge(realm="api.snhp.dev", request=frame["request"])
    assert mpp.verify_challenge(ch) is True
    # Lower the amount -> id no longer verifies (can't pay less than quoted).
    tampered = json.loads(json.dumps(ch))
    tampered["request"]["amount"] = "1"
    assert mpp.verify_challenge(tampered) is False
    # A different signing secret also fails (id binds to OUR secret).
    assert mpp.verify_challenge(ch, secret="someone-elses-secret") is False


def test_credential_roundtrip_via_public_helpers():
    frame = mpp.paid_resource_frame(base_cents=100, what="turn")
    ch = mpp.build_challenge(realm="api.snhp.dev", request=frame["request"])
    auth = mpp.serialize_credential(ch, {"spt": "spt_test_abc"})
    assert auth.startswith("Payment ")
    parsed = mpp.parse_credential(auth)
    assert parsed["payload"]["spt"] == "spt_test_abc"
    assert mpp.verify_challenge(parsed["challenge"]) is True


def test_parse_credential_rejects_garbage():
    # The exact probe the validator's error-handling phase sends.
    with pytest.raises(mpp.CredentialError):
        mpp.parse_credential("Payment dGhpcyBpcyBnYXJiYWdl")
    with pytest.raises(mpp.CredentialError):
        mpp.parse_credential("Bearer xyz")            # wrong scheme
    with pytest.raises(mpp.CredentialError):
        mpp.parse_credential("")


def test_receipt_serialize_roundtrip():
    r = mpp.build_receipt(method="stripe", reference="pi_123")
    enc = mpp.serialize_receipt(r)
    back = json.loads(mpp._b64url_decode(enc).decode())
    assert back["method"] == "stripe" and back["status"] == "success"
    assert back["reference"] == "pi_123" and back["timestamp"].endswith("Z")


def test_only_stripe_rail_advertised_crypto_deferred():
    assert mpp.SUPPORTED_METHODS == ("stripe",)


def test_settle_spt_maps_stripe_failure_to_declined(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: _DecliningStripe)
    with pytest.raises(billing.PaymentDeclinedError):
        mpp.settle_spt(spt="spt_x", amount_cents=105, currency="usd",
                       challenge_id="chal_1")


# ─── HTTP: challenge phase ───────────────────────────────────────────────────


@pytest.mark.parametrize("path,price", [
    ("/v1/mpp/negotiate/turn", 105),
    ("/v1/mpp/topup", 210),
])
def test_unpaid_request_returns_402_challenge(client, path, price):
    resp = client.post(path, json={})
    assert resp.status_code == 402
    www = resp.headers.get("www-authenticate", "")
    assert www.startswith("Payment ")
    assert 'method="stripe"' in www
    # A real mppx client parses this; our own deserializer must round-trip it.
    ch = mpp.deserialize_challenge(www)
    assert ch["request"]["amount"] == str(price)
    assert mpp.verify_challenge(ch) is True             # server-minted, verifiable
    assert resp.headers.get("cache-control") == "no-store"
    assert resp.headers.get("accept-payment") == "stripe"
    body = resp.json()
    assert body["status"] == 402 and body["challengeId"] == ch["id"]
    assert body["price_cents"] == price
    assert body["fee_cents"] == price - (100 if price == 105 else 200)


def test_malformed_credential_returns_fresh_402_not_500(client):
    # Validator error-handling probe: Authorization: Payment <garbage>, no body.
    resp = client.post("/v1/mpp/negotiate/turn",
                       headers={"Authorization": "Payment dGhpcyBpcyBnYXJiYWdl"})
    assert resp.status_code == 402
    assert resp.headers.get("www-authenticate", "").startswith("Payment ")


# ─── HTTP: full paid roundtrip (monkeypatched Stripe) ────────────────────────


def _pay(client, path, extra_body=None):
    """Do the MPP roundtrip: fetch the 402 challenge, build an SPT credential from
    it, and retry — exactly what an mppx client does."""
    first = client.post(path, json=extra_body or {})
    assert first.status_code == 402
    ch = mpp.deserialize_challenge(first.headers["www-authenticate"])
    auth = mpp.serialize_credential(ch, {"spt": "spt_test_paid"})
    return client.post(path, headers={"Authorization": auth}, json=extra_body or {})


def test_negotiate_paid_roundtrip_returns_receipt_and_result(client, fake_stripe):
    resp = _pay(client, "/v1/mpp/negotiate/turn",
                {"side": "sell", "walk_away": 4000, "target": 6000,
                 "counterparty_offers": [4200, 4500], "rounds_left": 6})
    assert resp.status_code == 200
    # Payment-Receipt header present + parseable, status success, pi_ reference.
    receipt_hdr = resp.headers.get("payment-receipt")
    assert receipt_hdr
    receipt = json.loads(mpp._b64url_decode(receipt_hdr).decode())
    assert receipt["status"] == "success" and receipt["reference"].startswith("pi_")
    body = resp.json()
    assert body["paid"] is True and body["ok"] is True
    assert body["result"]["action"] in ("counter", "accept", "walk", "negotiate_directly")
    assert body["fee_cents"] == 5 and body["price_cents"] == 105


def test_negotiate_paid_with_bad_body_still_returns_receipt(client, fake_stripe):
    # Pay-per-call: inputs are validated AFTER payment; a bad body is a reported
    # outcome (the buyer keeps their receipt), never a 500.
    resp = _pay(client, "/v1/mpp/negotiate/turn", {"side": "sideways"})
    assert resp.status_code == 200
    assert resp.headers.get("payment-receipt")
    body = resp.json()
    assert body["ok"] is False and "error" in body


def test_topup_credits_wallet_and_dedupes(client, fake_stripe, monkeypatch):
    # Isolate the settlement-dedupe table per run so a shared pi id can't collide.
    _FakePaymentIntent._by_idem.clear()
    key = issue_key(agent_id="mpp-test-agent", contact_email="mpp@test.dev",
                    intended_use_summary="mpp topup test",
                    telemetry_consent=False)["api_key"]
    before = wallet_available(key)["total_millicents"]

    # Build ONE credential (one challenge + one spt) and submit it twice — a client
    # network retry. The Stripe idempotency key (mppx_<challengeId>_<spt>) returns the
    # SAME PaymentIntent, and our reference dedupe must credit exactly once.
    first = client.post("/v1/mpp/topup", json={"api_key": key})
    ch = mpp.deserialize_challenge(first.headers["www-authenticate"])
    auth = mpp.serialize_credential(ch, {"spt": "spt_test_paid"})

    resp = client.post("/v1/mpp/topup", headers={"Authorization": auth},
                       json={"api_key": key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["credited"] is True and body["duplicate"] is False
    assert body["credits_cents"] == 200 and body["price_cents"] == 210
    after = wallet_available(key)["total_millicents"]
    assert after == before + 200 * onboarding.MILLICENTS_PER_CENT

    resp2 = client.post("/v1/mpp/topup", headers={"Authorization": auth},
                        json={"api_key": key})
    assert resp2.status_code == 200
    assert resp2.json()["duplicate"] is True
    assert wallet_available(key)["total_millicents"] == after   # unchanged


def test_topup_unknown_key_is_paid_but_not_credited(client, fake_stripe):
    resp = _pay(client, "/v1/mpp/topup", {"api_key": "gt_does_not_exist"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["credited"] is False and "error" in body
    assert resp.headers.get("payment-receipt")           # still proof of payment


def test_settlement_declined_returns_402(client, monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: _DecliningStripe)
    first = client.post("/v1/mpp/negotiate/turn", json={})
    ch = mpp.deserialize_challenge(first.headers["www-authenticate"])
    auth = mpp.serialize_credential(ch, {"spt": "spt_test_paid"})
    resp = client.post("/v1/mpp/negotiate/turn", headers={"Authorization": auth}, json={})
    assert resp.status_code == 402
    assert resp.headers.get("www-authenticate", "").startswith("Payment ")


def test_credential_with_wrong_method_rejected(client, fake_stripe):
    first = client.post("/v1/mpp/negotiate/turn", json={})
    ch = mpp.deserialize_challenge(first.headers["www-authenticate"])
    ch["method"] = "tempo"                               # rail we don't accept
    auth = mpp.serialize_credential(ch, {"spt": "spt_test_paid"})
    resp = client.post("/v1/mpp/negotiate/turn", headers={"Authorization": auth}, json={})
    assert resp.status_code == 402                        # unsupported -> retryable 402


# ─── HTTP: discovery (x-payment-info in /openapi.json) ───────────────────────


def test_openapi_advertises_paid_endpoints_with_x_payment_info(client):
    doc = client.get("/openapi.json").json()
    for path, amt in (("/v1/mpp/negotiate/turn", "105"), ("/v1/mpp/topup", "210")):
        op = doc["paths"][path]["post"]
        xpi = op["x-payment-info"]
        assert xpi["amount"] == amt and xpi["method"] == "stripe"
        assert xpi["intent"] == "charge" and xpi["currency"] == "usd"
        assert "402" in op["responses"]                  # required by the validator

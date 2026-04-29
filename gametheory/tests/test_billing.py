"""
Stripe Checkout credit-pack billing tests.

Stubs the `stripe` SDK so tests run without real keys. Two fakes:
  - `_FakeCheckoutSession`: returned by stripe.checkout.Session.create
  - `_FakeWebhook`: provides Webhook.construct_event that bypasses signature
                    verification (the test verifies signature handling
                    indirectly by feeding bad inputs to the real path elsewhere)

What the tests cover:
  - create_checkout_session returns a URL and stores api_key in metadata
  - webhook → checkout.session.completed → balance credits the right key
  - webhook idempotency: same event_id twice ⇒ second is a no-op
  - webhook on unknown event types ⇒ acked, no balance change
  - webhook with invalid signature ⇒ 400
  - balance check: deduct fails with insufficient balance, succeeds otherwise
"""
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_billing.db")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fakefakefake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fakefakefake")

from gametheory.server.http import app  # noqa: E402
from gametheory.server import billing as billing_mod  # noqa: E402
from gametheory.server.onboarding import (  # noqa: E402
    issue_key, lookup_key, credit_balance, deduct_balance,
)


client = TestClient(app)


# ─── Fakes ──────────────────────────────────────────────────────────────────


class _FakeCheckoutSession:
    def __init__(self, **kwargs):
        self.id = "cs_test_FAKESESSION123"
        self.url = "https://checkout.stripe.com/c/pay/cs_test_FAKESESSION123"
        self.metadata = kwargs.get("metadata", {})


class _FakeStripeModule:
    """Minimal stand-in for the stripe SDK; enough for our handlers."""
    api_key = None

    class checkout:
        class Session:
            @staticmethod
            def create(**kwargs):
                # Echo metadata into the returned object.
                return _FakeCheckoutSession(**kwargs)

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            # In tests we trust the signature. Decode payload and return it
            # as a "Stripe event"-shaped dict.
            if isinstance(payload, bytes):
                payload = payload.decode()
            event = json.loads(payload)
            if signature == "INVALID":
                raise ValueError("invalid signature")
            return event


@pytest.fixture
def stub_stripe(monkeypatch):
    """Replace billing._stripe with one that returns our fake module."""
    monkeypatch.setattr(billing_mod, "_stripe", lambda: _FakeStripeModule)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _new_key(agent_id: str) -> str:
    return issue_key(
        agent_id=agent_id, contact_email="test@example.com",
        intended_use_summary="billing tests",
    )["api_key"]


def _make_completed_event(event_id: str, api_key: str, credits_cents: int) -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session_id",
                "metadata": {
                    "api_key": api_key,
                    "pack": "small",
                    "credits_cents": str(credits_cents),
                },
            },
        },
    }


# ─── Checkout session creation ──────────────────────────────────────────────


def test_create_checkout_session_returns_url(stub_stripe):
    key = _new_key("checkout-agent-1")
    r = client.post("/v1/billing/checkout_session", json={
        "api_key": key,
        "pack": "small",
        "success_url": "https://snhp.dev/paid",
        "cancel_url": "https://snhp.dev/cancel",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")
    assert body["session_id"].startswith("cs_")
    assert body["pack"] == "small"
    assert body["price_cents"] == 1000
    assert body["credits_cents"] == 1000


def test_create_checkout_session_rejects_unknown_pack(stub_stripe):
    key = _new_key("checkout-agent-2")
    r = client.post("/v1/billing/checkout_session", json={
        "api_key": key,
        "pack": "enormous",   # not a real pack
        "success_url": "https://snhp.dev/paid",
        "cancel_url": "https://snhp.dev/cancel",
    })
    # Pydantic Literal rejects this at the schema level
    assert r.status_code == 422


def test_create_checkout_session_rejects_unknown_key(stub_stripe):
    r = client.post("/v1/billing/checkout_session", json={
        "api_key": "gt_does_not_exist",
        "pack": "small",
        "success_url": "https://snhp.dev/paid",
        "cancel_url": "https://snhp.dev/cancel",
    })
    assert r.status_code == 400
    assert "unknown api_key" in r.json()["detail"]


# ─── Webhook ────────────────────────────────────────────────────────────────


def test_webhook_credits_balance_on_checkout_completed(stub_stripe):
    key = _new_key("webhook-agent-1")
    assert lookup_key(key)["balance_usd_cents"] == 0

    event = _make_completed_event("evt_test_1", key, 1000)
    r = client.post(
        "/v1/billing/webhook",
        content=json.dumps(event),
        headers={"stripe-signature": "valid", "content-type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["new_balance_cents"] == 1000
    assert lookup_key(key)["balance_usd_cents"] == 1000


def test_webhook_is_idempotent(stub_stripe):
    """Stripe can re-deliver any event; second delivery must be a no-op."""
    key = _new_key("webhook-agent-2")
    event = _make_completed_event("evt_test_dup", key, 5000)

    r1 = client.post("/v1/billing/webhook", content=json.dumps(event),
                     headers={"stripe-signature": "valid",
                              "content-type": "application/json"})
    r2 = client.post("/v1/billing/webhook", content=json.dumps(event),
                     headers={"stripe-signature": "valid",
                              "content-type": "application/json"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True
    # Balance should reflect ONE credit, not two.
    assert lookup_key(key)["balance_usd_cents"] == 5000


def test_webhook_acknowledges_unhandled_event_types(stub_stripe):
    """We ack non-checkout events so Stripe stops retrying them."""
    event = {
        "id": "evt_test_other",
        "type": "customer.created",   # something we don't handle
        "data": {"object": {}},
    }
    r = client.post("/v1/billing/webhook", content=json.dumps(event),
                     headers={"stripe-signature": "valid",
                              "content-type": "application/json"})
    assert r.status_code == 200
    assert r.json().get("handled") is False


def test_webhook_rejects_invalid_signature(stub_stripe):
    """Invalid signature → 400, no balance change."""
    key = _new_key("webhook-agent-3")
    event = _make_completed_event("evt_test_badsig", key, 1000)
    r = client.post("/v1/billing/webhook", content=json.dumps(event),
                     headers={"stripe-signature": "INVALID",
                              "content-type": "application/json"})
    assert r.status_code == 400
    assert lookup_key(key)["balance_usd_cents"] == 0


def test_webhook_rejects_missing_metadata(stub_stripe):
    """A checkout.session.completed without metadata.api_key must error."""
    event = {
        "id": "evt_test_nometa",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_x", "metadata": {}}},
    }
    r = client.post("/v1/billing/webhook", content=json.dumps(event),
                     headers={"stripe-signature": "valid",
                              "content-type": "application/json"})
    assert r.status_code == 400


# ─── Balance + deduct directly ──────────────────────────────────────────────


def test_credit_then_deduct_then_insufficient():
    key = _new_key("deduct-agent")
    assert credit_balance(api_key=key, cents=10) == 10
    assert deduct_balance(api_key=key, cents=3) is True
    assert lookup_key(key)["balance_usd_cents"] == 7
    # Try to deduct more than available → False, balance unchanged.
    assert deduct_balance(api_key=key, cents=100) is False
    assert lookup_key(key)["balance_usd_cents"] == 7


def test_deduct_unknown_key_returns_false():
    assert deduct_balance(api_key="gt_does_not_exist", cents=1) is False

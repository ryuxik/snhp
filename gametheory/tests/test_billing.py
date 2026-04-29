"""
Direct unit tests for `gametheory.server.billing`.

Background: the billing HTTP routes (POST /v1/billing/checkout_session,
POST /v1/billing/webhook, GET /v1/billing/balance) are NOT currently
registered in the FastAPI app — we deferred Stripe billing while we
validate the underlying math product. The billing module itself stays
in the codebase, fully tested, so re-wiring is one route addition.

These tests exercise billing.py functions directly with a stubbed Stripe
SDK. When/if the HTTP routes come back, add an integration-test layer
that hits the routes; the function-level tests here remain the source
of truth for billing semantics.
"""
import json
import os
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption,
)

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_billing.db")
# Force fakes regardless of dev shell — `setdefault` would skip these if
# the dev had a real `sk_test_*` exported, and any test that forgot to
# monkeypatch `_stripe()` would then hit live Stripe.
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fakefakefake"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_fakefakefake"

from gametheory.server import billing as billing_mod  # noqa: E402
from gametheory.server.onboarding import (  # noqa: E402
    issue_key, lookup_key, credit_balance, deduct_balance,
)


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
                return _FakeCheckoutSession(**kwargs)

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            if isinstance(payload, bytes):
                payload = payload.decode()
            event = json.loads(payload)
            if signature == "INVALID":
                raise ValueError("invalid signature")
            return event


@pytest.fixture
def stub_stripe(monkeypatch):
    monkeypatch.setattr(billing_mod, "_stripe", lambda: _FakeStripeModule)


def _new_key(agent_id: str) -> str:
    return issue_key(
        agent_id=agent_id, contact_email="test@example.com",
        intended_use_summary="billing module tests",
    )["api_key"]


def _completed_event(event_id: str, api_key: str, credits_cents: int) -> bytes:
    return json.dumps({
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_session_id",
            "metadata": {
                "api_key": api_key,
                "pack": "small",
                "credits_cents": str(credits_cents),
            },
        }},
    }).encode()


# ─── Checkout session creation ──────────────────────────────────────────────


def test_create_checkout_session_returns_url(stub_stripe):
    key = _new_key("checkout-1")
    out = billing_mod.create_checkout_session(
        api_key=key, pack="small",
        success_url="https://snhp.dev/paid",
        cancel_url="https://snhp.dev/cancel",
    )
    assert out["checkout_url"].startswith("https://checkout.stripe.com/")
    assert out["session_id"].startswith("cs_")
    assert out["pack"] == "small"
    assert out["price_cents"] == 1000
    assert out["credits_cents"] == 1000


def test_create_checkout_session_rejects_unknown_pack(stub_stripe):
    key = _new_key("checkout-2")
    with pytest.raises(ValueError, match="unknown pack"):
        billing_mod.create_checkout_session(
            api_key=key, pack="enormous",  # type: ignore[arg-type]
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


def test_create_checkout_session_rejects_unknown_key(stub_stripe):
    with pytest.raises(ValueError, match="unknown api_key"):
        billing_mod.create_checkout_session(
            api_key="gt_does_not_exist", pack="small",
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


# ─── Webhook ────────────────────────────────────────────────────────────────


def test_webhook_credits_balance(stub_stripe):
    key = _new_key("webhook-1")
    assert lookup_key(key)["balance_usd_cents"] == 0
    out = billing_mod.handle_webhook(
        payload=_completed_event("evt_unit_1", key, 1000),
        signature="valid",
    )
    assert out["new_balance_cents"] == 1000
    assert lookup_key(key)["balance_usd_cents"] == 1000


def test_webhook_is_idempotent(stub_stripe):
    """The /simplify pass changed dedupe to INSERT-first; verify second
    delivery is a duplicate no-op."""
    key = _new_key("webhook-2")
    payload = _completed_event("evt_unit_dup", key, 5000)
    r1 = billing_mod.handle_webhook(payload=payload, signature="valid")
    r2 = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert r1.get("duplicate") is False
    assert r2.get("duplicate") is True
    assert lookup_key(key)["balance_usd_cents"] == 5000  # ONE credit, not two


def test_webhook_acks_unhandled_events(stub_stripe):
    """Non-checkout events are claimed (so Stripe stops retrying) and
    handled=False is reported back."""
    payload = json.dumps({
        "id": "evt_unit_other", "type": "customer.created",
        "data": {"object": {}},
    }).encode()
    out = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert out.get("handled") is False


def test_webhook_rejects_invalid_signature(stub_stripe):
    key = _new_key("webhook-3")
    with pytest.raises(ValueError, match="signature"):
        billing_mod.handle_webhook(
            payload=_completed_event("evt_unit_badsig", key, 1000),
            signature="INVALID",
        )
    assert lookup_key(key)["balance_usd_cents"] == 0


def test_webhook_rejects_missing_metadata(stub_stripe):
    payload = json.dumps({
        "id": "evt_unit_nometa",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_x", "metadata": {}}},
    }).encode()
    with pytest.raises(ValueError, match="metadata"):
        billing_mod.handle_webhook(payload=payload, signature="valid")


# ─── charge_or_raise ────────────────────────────────────────────────────────


def test_charge_or_raise_unknown_key():
    with pytest.raises(billing_mod.UnknownKeyError):
        billing_mod.charge_or_raise("gt_does_not_exist", 1)


def test_charge_or_raise_insufficient():
    key = _new_key("charge-low")
    credit_balance(api_key=key, cents=2)
    with pytest.raises(billing_mod.InsufficientCreditsError) as exc_info:
        billing_mod.charge_or_raise(key, 5)
    assert exc_info.value.available_cents == 2
    assert exc_info.value.required_cents == 5


def test_charge_or_raise_succeeds():
    key = _new_key("charge-ok")
    credit_balance(api_key=key, cents=10)
    billing_mod.charge_or_raise(key, 3)
    assert lookup_key(key)["balance_usd_cents"] == 7


# ─── credit_balance / deduct_balance helpers ────────────────────────────────


def test_credit_then_deduct_then_insufficient():
    key = _new_key("deduct-agent")
    assert credit_balance(api_key=key, cents=10) == 10
    assert deduct_balance(api_key=key, cents=3) is True
    assert lookup_key(key)["balance_usd_cents"] == 7
    assert deduct_balance(api_key=key, cents=100) is False
    assert lookup_key(key)["balance_usd_cents"] == 7


def test_deduct_unknown_key_returns_false():
    assert deduct_balance(api_key="gt_does_not_exist", cents=1) is False

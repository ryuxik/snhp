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
import itertools
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
    MILLICENTS_PER_CENT, STARTER_GRANT_MILLICENTS, issue_key, wallet_available,
)


# ─── Fakes ──────────────────────────────────────────────────────────────────


class _FakeCheckoutSession:
    def __init__(self, **kwargs):
        self.id = "cs_test_FAKESESSION123"
        self.url = "https://checkout.stripe.com/c/pay/cs_test_FAKESESSION123"
        self.metadata = kwargs.get("metadata", {})


_PI_COUNTER = itertools.count(1)


class _FakePaymentIntent:
    def __init__(self, **kwargs):
        self.id = f"pi_test_FAKE_{next(_PI_COUNTER)}"
        self.amount = kwargs.get("amount")
        self.currency = kwargs.get("currency")
        self.metadata = kwargs.get("metadata", {})
        self.status = "succeeded"


class _FakeStripeModule:
    """Minimal stand-in for the stripe SDK; enough for our handlers."""
    api_key = None

    class checkout:
        class Session:
            @staticmethod
            def create(**kwargs):
                return _FakeCheckoutSession(**kwargs)

    class PaymentIntent:
        # Models Stripe idempotency: the SAME idempotency_key returns the SAME
        # PaymentIntent (same id), so our intent-id dedupe sees a duplicate.
        # A call with no key gets a fresh, globally-unique id — no false
        # duplicates across tests that share the persistent dedupe table.
        _by_idem: dict = {}

        @staticmethod
        def create(**kwargs):
            idem = kwargs.get("idempotency_key")
            store = _FakeStripeModule.PaymentIntent._by_idem
            if idem is not None and idem in store:
                return store[idem]
            pi = _FakePaymentIntent(**kwargs)   # SPT redeem: succeeds in test mode
            if idem is not None:
                store[idem] = pi
            return pi

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


def _completed_event(event_id: str, api_key: str, credits_cents: int,
                     *, session_id: str = None,
                     event_type: str = "checkout.session.completed",
                     payment_status: str = "paid") -> bytes:
    # Each event gets a DISTINCT checkout-session id by default (derived from the
    # event id) so tests stay independent under the session-level credit dedupe.
    # A test that needs two events to share ONE purchase passes an explicit
    # session_id; async events pass event_type / payment_status.
    obj = {
        "id": session_id if session_id is not None else f"cs_{event_id}",
        "metadata": {
            "api_key": api_key,
            "pack": "small",
            "credits_cents": str(credits_cents),
        },
    }
    if payment_status is not None:
        obj["payment_status"] = payment_status
    return json.dumps({
        "id": event_id,
        "type": event_type,
        "data": {"object": obj},
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
    # price = credits + the counter fee (5% + 30¢) (STORE.md §2d.4)
    assert out["price_cents"] == 1080
    assert out["credits_cents"] == 1000
    assert out["fee_cents"] == 80          # 5% of 1000 (=50) + fixed 30


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


# ─── Counter fee arithmetic + custom top-up ─────────────────────────────────


def test_counter_fee_matches_every_pack():
    """The fee helper must reproduce every CREDIT_PACKS price exactly — the
    module-load assert depends on this, and the receipt must never disagree
    with the published fee."""
    for name, p in billing_mod.CREDIT_PACKS.items():
        fee = billing_mod.counter_fee_cents(p["credits_cents"])
        assert p["credits_cents"] + fee == p["price_cents"], name


def test_counter_fee_rounds_half_up():
    # 250¢ credit → 5% = 12.5¢ → rounds half-up to 13¢ (not banker's-even 12¢),
    # PLUS the fixed 30¢ toll = 43¢
    assert billing_mod.counter_fee_cents(250) == 13 + 30
    # the $2 anchor need: 200¢ → 10¢ pct + 30¢ fixed = 40¢ → $2.40 total
    assert billing_mod.counter_fee_cents(200) == 10 + 30
    # even a zero-credit transaction owes the fixed per-transaction toll
    assert billing_mod.counter_fee_cents(0) == 30
    assert billing_mod.COUNTER_FEE_FIXED_CENTS == 30


def test_custom_topup_checkout_arithmetic(stub_stripe):
    """A $2 credit costs $2.40 (5% + 30¢), never $10.80."""
    key = _new_key("custom-1")
    out = billing_mod.create_checkout_session(
        api_key=key, amount_cents=200,
        success_url="https://snhp.dev/paid", cancel_url="https://snhp.dev/cancel",
    )
    assert out["pack"] == "custom"
    assert out["credits_cents"] == 200
    assert out["price_cents"] == 240
    assert out["fee_cents"] == 40


def test_custom_topup_enforces_minimum(stub_stripe):
    key = _new_key("custom-min")
    with pytest.raises(ValueError, match="amount_cents must be >= 200"):
        billing_mod.create_checkout_session(
            api_key=key, amount_cents=199,
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


def test_checkout_rejects_both_pack_and_amount(stub_stripe):
    key = _new_key("custom-both")
    with pytest.raises(ValueError, match="exactly one"):
        billing_mod.create_checkout_session(
            api_key=key, pack="small", amount_cents=500,
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


def test_checkout_rejects_neither_pack_nor_amount(stub_stripe):
    key = _new_key("custom-neither")
    with pytest.raises(ValueError, match="exactly one"):
        billing_mod.create_checkout_session(
            api_key=key,
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


def test_custom_topup_rejects_bool_amount(stub_stripe):
    """bool is an int subclass — True must not read as '1 cent'."""
    key = _new_key("custom-bool")
    with pytest.raises(ValueError, match="amount_cents must be an integer"):
        billing_mod.create_checkout_session(
            api_key=key, amount_cents=True,  # type: ignore[arg-type]
            success_url="https://snhp.dev/paid",
            cancel_url="https://snhp.dev/cancel",
        )


def test_webhook_credits_custom_amount(stub_stripe):
    """The webhook is amount-agnostic: a custom credits_cents flows through the
    SAME signed/deduped path with no handler change."""
    key = _new_key("custom-webhook")
    out = billing_mod.handle_webhook(
        payload=_completed_event("evt_custom_wh", key, 200), signature="valid")
    assert out["new_balance_millicents"] == STARTER_GRANT_MILLICENTS + 200_000
    assert wallet_available(key)["funded_millicents"] == 200_000


# ─── Webhook ────────────────────────────────────────────────────────────────


def test_webhook_credits_balance(stub_stripe):
    key = _new_key("webhook-1")
    assert wallet_available(key)["funded_millicents"] == 0
    out = billing_mod.handle_webhook(
        payload=_completed_event("evt_unit_1", key, 1000),
        signature="valid",
    )
    # top-up lands in funded; the new balance is starter + the credited money
    assert out["new_balance_millicents"] == STARTER_GRANT_MILLICENTS + 1_000_000
    assert wallet_available(key)["funded_millicents"] == 1_000_000


def test_webhook_is_idempotent(stub_stripe):
    """The /simplify pass changed dedupe to INSERT-first; verify second
    delivery is a duplicate no-op."""
    key = _new_key("webhook-2")
    payload = _completed_event("evt_unit_dup", key, 5000)
    r1 = billing_mod.handle_webhook(payload=payload, signature="valid")
    r2 = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert r1.get("duplicate") is False
    assert r2.get("duplicate") is True
    assert wallet_available(key)["funded_millicents"] == 5_000_000  # ONE credit


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
    assert wallet_available(key)["funded_millicents"] == 0


def test_webhook_rejects_missing_metadata(stub_stripe):
    payload = json.dumps({
        "id": "evt_unit_nometa",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_nometa", "metadata": {}}},
    }).encode()
    with pytest.raises(ValueError, match="metadata"):
        billing_mod.handle_webhook(payload=payload, signature="valid")


# ─── charge_or_raise ────────────────────────────────────────────────────────


def test_charge_or_raise_unknown_key():
    with pytest.raises(billing_mod.UnknownKeyError):
        billing_mod.charge_or_raise("gt_does_not_exist", 1)


def test_charge_or_raise_insufficient():
    key = _new_key("charge-low")     # starter 50_000 (= 50¢), no own money
    with pytest.raises(billing_mod.InsufficientCreditsError) as exc_info:
        billing_mod.charge_or_raise(key, 60)     # 60¢ > the 50¢ starter
    assert exc_info.value.available_millicents == STARTER_GRANT_MILLICENTS
    assert exc_info.value.required_millicents == 60 * MILLICENTS_PER_CENT
    # rerun P4: the 402 message points at top-up options, incl. the $2 custom
    # minimum, so an underfunded anchor-session buyer is directed, not stranded.
    msg = str(exc_info.value)
    assert "checkout_session" in msg
    assert f"{billing_mod.CUSTOM_MIN_CENTS}" in msg and "$2.00" in msg


def test_charge_or_raise_succeeds_from_starter():
    key = _new_key("charge-ok")
    split = billing_mod.charge_or_raise(key, 3)   # 3¢ = 3_000 millicents
    assert split["starter_spent"] == 3_000
    assert split["funded_spent"] == 0
    assert wallet_available(key)["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 3_000


# ─── charge spends the starter bucket first, then funded ────────────────────


def test_charge_spends_starter_then_funded(stub_stripe):
    key = _new_key("charge-split")
    # top up 10¢ of own money via the webhook path
    billing_mod.handle_webhook(
        payload=_completed_event("evt_split", key, 10), signature="valid")
    # wallet now: starter 50_000 + funded 10_000
    split = billing_mod.charge_or_raise(key, 55)  # 55_000 millicents
    assert split["starter_spent"] == STARTER_GRANT_MILLICENTS
    assert split["funded_spent"] == 5_000
    assert wallet_available(key)["total_millicents"] == 5_000


def test_webhook_credit_failure_is_not_stranded(stub_stripe, monkeypatch):
    """Fix 5 (crash window): the claim + credit are ONE atomic transaction, so
    a failure mid-credit leaves NOTHING committed — the purchase is never left
    silently claimed-but-uncredited, and Stripe's retry credits cleanly."""
    from gametheory.server import onboarding as _ob
    key = _new_key("webhook-release-1")
    session_id = "cs_release_1"
    payload = _completed_event("evt_unit_release", key, 1000,
                               session_id=session_id)

    calls = {"n": 0}
    real_credit = billing_mod.onboarding.wallet_credit_idempotent

    def flaky_credit(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient DB failure")
        return real_credit(*args, **kwargs)

    monkeypatch.setattr(billing_mod.onboarding, "wallet_credit_idempotent",
                        flaky_credit)

    # First delivery: crashes mid-credit. No credit, and — crucially — the
    # session is NOT recorded as claimed-uncredited (nothing committed).
    with pytest.raises(RuntimeError, match="simulated transient"):
        billing_mod.handle_webhook(payload=payload, signature="valid")
    assert wallet_available(key)["funded_millicents"] == 0
    with _ob._conn() as c:
        row = c.execute(
            "SELECT 1 FROM wallet_credits WHERE dedup_key = ?",
            (session_id,)).fetchone()
    assert row is None, "a failed credit must not leave a claimed dedupe row"

    # Stripe retries: must NOT be a duplicate — must credit this time.
    out = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert out.get("duplicate") is False
    assert out["new_balance_millicents"] == STARTER_GRANT_MILLICENTS + 1_000_000
    assert wallet_available(key)["funded_millicents"] == 1_000_000


def test_checkout_session_passes_idempotency_key(stub_stripe, monkeypatch):
    seen = {}
    real_create = _FakeStripeModule.checkout.Session.create

    def capture(**kwargs):
        seen.update(kwargs)
        kwargs.pop("idempotency_key", None)
        return real_create(**kwargs)

    monkeypatch.setattr(_FakeStripeModule.checkout.Session, "create", capture)
    key = _new_key("checkout-idem-1")
    billing_mod.create_checkout_session(
        api_key=key, pack="small",
        success_url="https://snhp.dev/paid", cancel_url="https://snhp.dev/cancel",
        idempotency_key="req_abc123",
    )
    assert seen.get("idempotency_key") == "req_abc123"


def test_webhook_completed_unpaid_acks_without_credit(stub_stripe):
    """Managed Payments: async methods can complete a session unpaid; the
    credit must wait for async_payment_succeeded."""
    key = _new_key("webhook-unpaid-1")
    payload = json.dumps({
        "id": "evt_unit_unpaid",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_unpaid", "payment_status": "unpaid",
            "metadata": {"api_key": key, "credits_cents": "1000"},
        }},
    }).encode()
    out = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert out.get("awaiting_payment") is True
    assert wallet_available(key)["funded_millicents"] == 0


def test_webhook_async_payment_succeeded_credits(stub_stripe):
    key = _new_key("webhook-async-1")
    payload = json.dumps({
        "id": "evt_unit_async",
        "type": "checkout.session.async_payment_succeeded",
        "data": {"object": {
            "id": "cs_async",
            "metadata": {"api_key": key, "credits_cents": "1000"},
        }},
    }).encode()
    out = billing_mod.handle_webhook(payload=payload, signature="valid")
    assert out["new_balance_millicents"] == STARTER_GRANT_MILLICENTS + 1_000_000
    assert wallet_available(key)["funded_millicents"] == 1_000_000


# ─── Agentic top-up: redeem a Shared Payment Token (PREVIEW) ────────────────


def test_agentic_topup_credits_and_names_fee(stub_stripe):
    key = _new_key("agentic-1")
    out = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_test_123")
    assert out["credited"] is True
    assert out["duplicate"] is False
    assert out["status"] == "succeeded"
    # same fee math as the custom Checkout top-up: $2 credit → $2.40 (5% + 30¢)
    assert out["credits_cents"] == 200
    assert out["price_cents"] == 240
    assert out["fee_cents"] == 40
    assert out["new_balance_millicents"] == STARTER_GRANT_MILLICENTS + 200_000
    assert wallet_available(key)["funded_millicents"] == 200_000


def test_agentic_topup_charges_price_not_credits(stub_stripe, monkeypatch):
    """Stripe must be asked to redeem the SPT for price (credits+fee), the
    wallet credited only the credits, and the SPT param + preview version must
    be present on the call."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return _FakePaymentIntent(**kwargs)   # fresh unique id per call

    monkeypatch.setattr(_FakeStripeModule.PaymentIntent, "create", capture)
    key = _new_key("agentic-charge")
    billing_mod.agentic_topup(
        api_key=key, amount_cents=1000, payment_token="spt_abc",
        idempotency_key="req_xyz")
    assert seen["amount"] == 1080                     # price = 1000 + (5% + 30¢) fee
    assert seen["currency"] == "usd"
    assert seen["confirm"] is True
    assert seen["payment_method_data"] == {
        "shared_payment_granted_token": "spt_abc"}
    assert seen["stripe_version"] == billing_mod.AGENTIC_PREVIEW_API_VERSION
    assert seen["idempotency_key"] == "req_xyz"
    assert wallet_available(key)["funded_millicents"] == 1_000_000  # credits only


def test_agentic_topup_enforces_minimum(stub_stripe):
    key = _new_key("agentic-min")
    with pytest.raises(ValueError, match="amount_cents must be >= 200"):
        billing_mod.agentic_topup(
            api_key=key, amount_cents=199, payment_token="spt_x")


def test_agentic_topup_unknown_key(stub_stripe):
    with pytest.raises(ValueError, match="unknown api_key"):
        billing_mod.agentic_topup(
            api_key="gt_nope", amount_cents=200, payment_token="spt_x")


def test_agentic_topup_requires_token(stub_stripe):
    key = _new_key("agentic-notoken")
    with pytest.raises(ValueError, match="payment_token"):
        billing_mod.agentic_topup(
            api_key=key, amount_cents=200, payment_token="  ")


def test_agentic_topup_is_idempotent(stub_stripe):
    """A retry with the same idempotency key → same PaymentIntent id → credits
    once (Stripe idempotency + our intent-id dedupe)."""
    key = _new_key("agentic-idem")
    r1 = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_dup",
        idempotency_key="req_dup")
    r2 = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_dup",
        idempotency_key="req_dup")
    assert r1.get("duplicate") is False
    assert r2.get("duplicate") is True
    assert wallet_available(key)["funded_millicents"] == 200_000  # ONE credit


def test_agentic_topup_declined_raises(stub_stripe, monkeypatch):
    """A Stripe error on redeem surfaces as PaymentDeclinedError (→ 402), never
    a 500, and never credits."""
    def boom(**kwargs):
        raise RuntimeError("card_declined")  # stand-in for stripe.error.CardError

    monkeypatch.setattr(_FakeStripeModule.PaymentIntent, "create", boom)
    key = _new_key("agentic-declined")
    with pytest.raises(billing_mod.PaymentDeclinedError, match="card_declined"):
        billing_mod.agentic_topup(
            api_key=key, amount_cents=200, payment_token="spt_bad")
    assert wallet_available(key)["funded_millicents"] == 0


def test_agentic_topup_non_succeeded_does_not_credit(stub_stripe, monkeypatch):
    """requires_action / processing: returned uncredited, wallet untouched."""
    def pending(**kwargs):
        pi = _FakePaymentIntent(**kwargs)
        pi.status = "requires_action"
        return pi

    monkeypatch.setattr(_FakeStripeModule.PaymentIntent, "create", pending)
    key = _new_key("agentic-pending")
    out = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_pending")
    assert out["credited"] is False
    assert out["status"] == "requires_action"
    assert wallet_available(key)["funded_millicents"] == 0


def test_agentic_topup_credit_failure_is_not_stranded(stub_stripe, monkeypatch):
    """A transient failure in the atomic credit leaves nothing committed, so a
    retry (same idempotency key → SAME intent id) credits — never
    paid-but-uncredited-forever (same rule as the webhook)."""
    key = _new_key("agentic-release")
    calls = {"n": 0}
    real_credit = billing_mod.onboarding.wallet_credit_idempotent

    def flaky_credit(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient DB failure")
        return real_credit(*args, **kwargs)

    monkeypatch.setattr(billing_mod.onboarding, "wallet_credit_idempotent",
                        flaky_credit)
    # Same idempotency key on both calls → the retry hits the SAME intent id,
    # so the dedupe key is identical (nothing committed the first time).
    with pytest.raises(RuntimeError, match="simulated transient"):
        billing_mod.agentic_topup(
            api_key=key, amount_cents=200, payment_token="spt_release",
            idempotency_key="req_release")
    assert wallet_available(key)["funded_millicents"] == 0

    out = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_release",
        idempotency_key="req_release")
    assert out.get("duplicate") is False
    assert wallet_available(key)["funded_millicents"] == 200_000


# ─── Fix 6: dedupe the CREDIT on the session id, not the event id ────────────


def test_webhook_dedups_on_session_not_event(stub_stripe):
    """A dashboard 'Resend' arrives as a NEW event id for the SAME purchase.
    Deduping on the checkout-session id (not the event id) credits it once."""
    key = _new_key("wh-session-dedup")
    p1 = _completed_event("evt_sess_A", key, 1000, session_id="cs_shared_dedup")
    p2 = _completed_event("evt_sess_B", key, 1000, session_id="cs_shared_dedup")
    r1 = billing_mod.handle_webhook(payload=p1, signature="valid")
    r2 = billing_mod.handle_webhook(payload=p2, signature="valid")
    assert r1["duplicate"] is False
    assert r2["duplicate"] is True                      # same session → no-op
    assert wallet_available(key)["funded_millicents"] == 1_000_000   # ONE credit


def test_webhook_completed_then_async_same_session_credits_once(stub_stripe):
    """The common Managed-Payments pair — completed(paid) then
    async_payment_succeeded for the SAME session — must credit once, not twice."""
    key = _new_key("wh-pair")
    completed = _completed_event("evt_pair_c", key, 1000, session_id="cs_pair")
    async_evt = _completed_event(
        "evt_pair_a", key, 1000, session_id="cs_pair",
        event_type="checkout.session.async_payment_succeeded",
        payment_status=None)
    r1 = billing_mod.handle_webhook(payload=completed, signature="valid")
    r2 = billing_mod.handle_webhook(payload=async_evt, signature="valid")
    assert r1["duplicate"] is False
    assert r2["duplicate"] is True
    assert wallet_available(key)["funded_millicents"] == 1_000_000   # ONE credit


# ─── Fix 4a: agentic top-up always derives a Stripe idempotency key ─────────


def test_agentic_topup_idempotent_without_explicit_key(stub_stripe):
    """With NO idempotency_key passed (no x-request-id), a retry must still not
    mint a second PaymentIntent: the derived key (token+amount) makes Stripe
    return the SAME intent, and the intent-id dedupe credits once."""
    key = _new_key("agentic-derived-idem")
    r1 = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_derive")
    r2 = billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_derive")
    assert r1["duplicate"] is False
    assert r2["duplicate"] is True
    assert wallet_available(key)["funded_millicents"] == 200_000     # ONE credit


def test_agentic_topup_derived_idempotency_key_reaches_stripe(stub_stripe,
                                                              monkeypatch):
    """When no idempotency_key is supplied, one IS still sent to Stripe (derived
    from amount + token), so Stripe itself dedupes a retried charge."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return _FakePaymentIntent(**kwargs)

    monkeypatch.setattr(_FakeStripeModule.PaymentIntent, "create", capture)
    key = _new_key("agentic-derived-key")
    billing_mod.agentic_topup(
        api_key=key, amount_cents=200, payment_token="spt_xyz")
    assert seen.get("idempotency_key") == "agentic_200_spt_xyz"


# ─── Fix 4b: transport/timeout is NOT reported as a clean decline ────────────


# Stand-in for stripe.error.APIConnectionError — the classifier matches Stripe
# error types by class NAME (so it works without the SDK installed), so the
# name here must be the real one.
class APIConnectionError(Exception):
    pass


def test_agentic_topup_transport_error_is_ambiguous_not_declined(
        stub_stripe, monkeypatch):
    """A post-send transport/timeout error → ChargeAmbiguousError (→ 5xx),
    NOT PaymentDeclinedError (→ 402). A '402 declined' would invite the client
    to retry as a fresh charge and double-charge; the ambiguous error does not.
    And it must not be a BillingError (the HTTP layer maps those to 402)."""
    def boom(**kwargs):
        raise APIConnectionError("Network error communicating with Stripe")

    monkeypatch.setattr(_FakeStripeModule.PaymentIntent, "create", boom)
    key = _new_key("agentic-transport")
    with pytest.raises(billing_mod.ChargeAmbiguousError):
        billing_mod.agentic_topup(
            api_key=key, amount_cents=200, payment_token="spt_timeout")
    assert not isinstance(billing_mod.ChargeAmbiguousError("x"),
                          billing_mod.BillingError)
    assert wallet_available(key)["funded_millicents"] == 0

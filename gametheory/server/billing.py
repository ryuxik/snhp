"""
Stripe Checkout credit-pack billing.

Flow:
  1. Caller hits POST /v1/billing/checkout_session with {api_key, pack}.
     We create a Stripe Checkout session for the pack price and return
     the hosted URL the human owner of the agent clicks to pay.
  2. Stripe handles the payment UI, then calls our webhook with
     `checkout.session.completed`. We verify the signature, dedupe via
     `processed_stripe_events`, and credit the api_key's balance.
  3. Each call to a paid endpoint (e.g. draft_message) deducts cost cents
     from the balance via `onboarding.deduct_balance`.

Idempotency:
  - Stripe can re-deliver any webhook event; we dedupe by event.id stored
    in `processed_stripe_events` (PRIMARY KEY). Re-deliveries are no-ops.
  - The api_key is recorded in the Checkout session's `metadata.api_key`
    so we can credit the right balance when the webhook fires.

Test mode:
  - Use `sk_test_*` and `whsec_*` keys; Stripe test cards (4242 4242 4242 4242)
  - Tests in test_billing.py monkeypatch `stripe` so they run without keys.
"""
from __future__ import annotations

import os
from typing import Optional

from gametheory._db import db_conn
from gametheory.server import onboarding


# ─── Pricing ────────────────────────────────────────────────────────────────


# Pack price → credit cents. Keep flat per-call rate ($0.005); add volume
# discount once a customer asks. All values in USD cents.
CREDIT_PACKS = {
    "small":  {"price_cents": 1_000,  "credits_cents": 1_000},
    "medium": {"price_cents": 5_000,  "credits_cents": 5_000},
    "large":  {"price_cents": 20_000, "credits_cents": 20_000},
}

# Per-call cost in cents for the LLM-cost endpoints.
DRAFT_MESSAGE_COST_CENTS = 1     # matches the existing $0.005 / call pricing
                                  # rounded up to whole cents (cents must be int)


# ─── Storage: dedupe table ──────────────────────────────────────────────────


_EVENTS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS processed_stripe_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        processed_at INTEGER NOT NULL
    )
    """,
)


def _events_conn():
    return db_conn(_EVENTS_SCHEMA)


def _is_event_processed(event_id: str) -> bool:
    with _events_conn() as c:
        row = c.execute(
            "SELECT 1 FROM processed_stripe_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return row is not None


def _mark_event_processed(event_id: str, event_type: str) -> None:
    import time as _time
    with _events_conn() as c:
        c.execute(
            """INSERT INTO processed_stripe_events (event_id, event_type, processed_at)
               VALUES (?, ?, ?)""",
            (event_id, event_type, int(_time.time())),
        )
        c.commit()


# ─── Stripe Checkout ────────────────────────────────────────────────────────


def _stripe():
    """Lazy import + configure with the secret. Raises if STRIPE_SECRET_KEY
    isn't set, so dev/test paths can monkeypatch this function before any
    real call."""
    import stripe  # noqa: F401  (imported lazily so non-prod installs work)
    secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret:
        raise RuntimeError(
            "STRIPE_SECRET_KEY not set — cannot create Checkout sessions or "
            "verify webhook signatures. Set via `fly secrets set STRIPE_SECRET_KEY=...`."
        )
    stripe.api_key = secret
    return stripe


def create_checkout_session(*, api_key: str, pack: str,
                              success_url: str, cancel_url: str) -> dict:
    """
    Creates a Stripe Checkout session for the given pack. Returns
    {checkout_url, session_id, pack, price_cents, credits_cents}.

    The api_key is stored in `metadata.api_key` so the webhook handler
    knows which balance to credit when the user completes payment.
    """
    if pack not in CREDIT_PACKS:
        raise ValueError(f"unknown pack {pack!r}; valid: {sorted(CREDIT_PACKS)}")
    if onboarding.lookup_key(api_key) is None:
        raise ValueError(f"unknown api_key {api_key!r}")

    p = CREDIT_PACKS[pack]
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"SNHP credits ({pack} pack)"},
                "unit_amount": p["price_cents"],
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "api_key": api_key,
            "pack": pack,
            "credits_cents": str(p["credits_cents"]),
        },
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "pack": pack,
        "price_cents": p["price_cents"],
        "credits_cents": p["credits_cents"],
    }


# ─── Webhook ────────────────────────────────────────────────────────────────


def handle_webhook(*, payload: bytes, signature: Optional[str]) -> dict:
    """
    Verify Stripe's signature, dedupe by event id, and credit the api_key
    for `checkout.session.completed` events. Other event types are
    acknowledged with a no-op so Stripe stops retrying.

    Returns {processed, event_id, event_type, ...} for diagnostic logging.
    """
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "STRIPE_WEBHOOK_SECRET not set — cannot verify webhook signatures."
        )
    stripe = _stripe()

    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except Exception as e:
        # Includes invalid signature, malformed payload, etc.
        raise ValueError(f"webhook signature verification failed: {e}") from e

    event_id = event["id"]
    event_type = event["type"]

    if _is_event_processed(event_id):
        return {"processed": True, "event_id": event_id,
                "event_type": event_type, "duplicate": True}

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        api_key = meta.get("api_key")
        credits_cents_str = meta.get("credits_cents")
        if not api_key or not credits_cents_str:
            raise ValueError(
                f"checkout.session.completed missing metadata.api_key or "
                f"metadata.credits_cents (event {event_id})"
            )
        credits_cents = int(credits_cents_str)
        new_balance = onboarding.credit_balance(
            api_key=api_key, cents=credits_cents,
        )
        _mark_event_processed(event_id, event_type)
        return {
            "processed": True, "event_id": event_id, "event_type": event_type,
            "api_key": api_key, "credits_cents": credits_cents,
            "new_balance_cents": new_balance, "duplicate": False,
        }

    # Acknowledge unhandled events so Stripe stops retrying.
    _mark_event_processed(event_id, event_type)
    return {"processed": True, "event_id": event_id,
            "event_type": event_type, "handled": False}

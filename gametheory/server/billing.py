"""
Stripe Checkout credit-pack billing.

Flow:
  1. Caller hits POST /v1/billing/checkout_session with {api_key, pack}.
     We create a Stripe Checkout session for the pack price and return
     the hosted URL the human owner of the agent clicks to pay.
  2. Stripe handles the payment UI, then calls our webhook with
     `checkout.session.completed`. We verify the signature, dedupe via
     `processed_stripe_events` (INSERT-first, see handle_webhook), and
     credit the api_key's balance.
  3. Each call to a paid endpoint (e.g. draft_message) deducts cost cents
     from the balance via `charge_or_raise`.

Test mode:
  - Use `sk_test_*` and `whsec_*` keys; Stripe test cards (4242 4242 4242 4242)
  - Tests in test_billing.py monkeypatch `_stripe()` so they run without keys.
"""
from __future__ import annotations

import os
import time
from typing import Literal, Optional

from gametheory._db import db_conn
from gametheory.server import onboarding


# ─── Pricing + types ────────────────────────────────────────────────────────


PackName = Literal["small", "medium", "large"]

# Pack price → credit cents. Keep flat per-call rate ($0.005); add volume
# discount once a customer asks. All values in USD cents. Keys MUST match
# the PackName Literal — enforced by an assert at module load.
CREDIT_PACKS: dict[PackName, dict] = {
    "small":  {"price_cents": 1_000,  "credits_cents": 1_000},
    "medium": {"price_cents": 5_000,  "credits_cents": 5_000},
    "large":  {"price_cents": 20_000, "credits_cents": 20_000},
}

# Per-call cost in cents for the LLM-cost endpoints.
DRAFT_MESSAGE_COST_CENTS = 1     # matches the existing $0.005 / call pricing
                                  # rounded up to whole cents (cents must be int)

# Stripe event-type string we actually act on. Anything else is acked + ignored.
EVENT_CHECKOUT_COMPLETED = "checkout.session.completed"


# ─── Errors ─────────────────────────────────────────────────────────────────


class BillingError(Exception):
    """Base for charge-time errors that the HTTP layer translates to 402."""


class UnknownKeyError(BillingError):
    """The api_key isn't in the keys table."""


class InsufficientCreditsError(BillingError):
    """The key exists but its balance is below the requested cost.
    Carries the available balance for the error message."""

    def __init__(self, available_cents: int, required_cents: int):
        self.available_cents = available_cents
        self.required_cents = required_cents
        super().__init__(
            f"Insufficient credits ({available_cents} cents available, "
            f"{required_cents} required)."
        )


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


def _claim_event(event_id: str, event_type: str) -> bool:
    """Atomically claim an event_id for processing. Returns True iff this
    call won the race (the row was inserted). Returns False if the event
    was already claimed by a previous (or concurrent) delivery — Stripe
    retries at-least-once, and concurrent retries can race the
    `_is_event_processed` → credit → `_mark_event_processed` window.
    INSERT-first eliminates that window: the unique-constraint guard on
    event_id is the synchronization point.
    """
    with _events_conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO processed_stripe_events
               (event_id, event_type, processed_at) VALUES (?, ?, ?)""",
            (event_id, event_type, int(time.time())),
        )
        c.commit()
        return cur.rowcount == 1


# ─── Stripe Checkout ────────────────────────────────────────────────────────


def _required_env(name: str, purpose: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"{name} not set — cannot {purpose}. Set via "
            f"`fly secrets set {name}=...`."
        )
    return val


def _stripe():
    """Lazy import + configure with the secret. Raises if STRIPE_SECRET_KEY
    isn't set, so dev/test paths can monkeypatch this function before any
    real call."""
    import stripe  # noqa: F401  (imported lazily so non-prod installs work)
    stripe.api_key = _required_env(
        "STRIPE_SECRET_KEY",
        "create Checkout sessions or verify webhook signatures",
    )
    return stripe


def create_checkout_session(*, api_key: str, pack: PackName,
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
    Verify Stripe's signature, claim the event id atomically, and credit
    the api_key for `checkout.session.completed` events. Other event
    types are acked with a no-op so Stripe stops retrying.

    Returns {processed, event_id, event_type, ...} for diagnostic logging.
    """
    secret = _required_env("STRIPE_WEBHOOK_SECRET", "verify webhook signatures")
    stripe = _stripe()

    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except Exception as e:
        raise ValueError(f"webhook signature verification failed: {e}") from e

    event_id = event["id"]
    event_type = event["type"]

    # Claim the event id BEFORE any side effects. If we lose the race, we
    # know the prior winner already credited (or no-op'd); return early
    # without crediting again.
    if not _claim_event(event_id, event_type):
        return {"processed": True, "event_id": event_id,
                "event_type": event_type, "duplicate": True}

    if event_type != EVENT_CHECKOUT_COMPLETED:
        return {"processed": True, "event_id": event_id,
                "event_type": event_type, "handled": False}

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
    return {
        "processed": True, "event_id": event_id, "event_type": event_type,
        "api_key": api_key, "credits_cents": credits_cents,
        "new_balance_cents": new_balance, "duplicate": False,
    }


# ─── Charge (called by paid endpoints) ──────────────────────────────────────


def charge_or_raise(api_key: str, cents: int) -> None:
    """
    Atomically charge `cents` from the key's balance. Raises:
      UnknownKeyError          — api_key not found
      InsufficientCreditsError — exists but balance < cents

    The caller (typically an HTTP handler) is responsible for translating
    these to a 402 response.
    """
    info = onboarding.lookup_key(api_key)
    if info is None:
        raise UnknownKeyError(f"unknown api_key {api_key!r}")
    if not onboarding.deduct_balance(api_key=api_key, cents=cents):
        raise InsufficientCreditsError(info["balance_usd_cents"], cents)

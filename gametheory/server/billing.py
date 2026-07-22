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

Top-up shapes:
  - Named pack (small/medium/large) OR a custom `amount_cents` (min 200) — the
    custom path prices at credits + the 5% counter fee, so an agent buys exactly
    what it needs ($2 → $2.10) instead of over-shooting to the smallest pack.
  - Agentic (`agentic_topup`): redeem a Shared Payment Token the agent carries,
    with no human at a Checkout URL. PREVIEW — see vend/AGENTIC_PAYMENTS.md.

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

# The store's till (STORE.md §2d.4): commodity slot calls settle at wholesale
# passthrough (zero per-call markup — don't tax the referendum instrument), and
# the store earns ONE published fee, here, on wallet top-ups.
COUNTER_FEE_PCT = 5

# Pack price → credit cents. price_cents = credits_cents + the 5% counter fee,
# split explicitly so both the receipt and the checkout line item can name the
# fee. credits_cents is what lands in the balance; the difference is the fee.
# All values in USD cents. Keys MUST match the PackName Literal, and each pack's
# price MUST equal credits + counter_fee_cents(credits) — both enforced by an
# assert at module load, so the packs and the published fee can never silently
# disagree. Do NOT change these values (STORE.md — the anchor is fixed).
CREDIT_PACKS: dict[PackName, dict] = {
    "small":  {"price_cents": 1_050,  "credits_cents": 1_000},
    "medium": {"price_cents": 5_250,  "credits_cents": 5_000},
    "large":  {"price_cents": 21_000, "credits_cents": 20_000},
}

# Custom top-up floor (GAUNTLET #2): the smallest pack was $10.50 — a 5.25×
# overshoot to reach the $2 anchor session. A custom top-up lets an agent buy
# EXACTLY what it needs (a $2 need → $2.10, never $10.50). 200¢ = $2.00 is the
# floor: it clears the $2 anchor and sits 4× above Stripe's 0.50 USD SPT floor,
# so one published minimum serves both the Checkout and the SPT rail.
CUSTOM_MIN_CENTS = 200

# Per-call cost in cents for the LLM-cost endpoints.
DRAFT_MESSAGE_COST_CENTS = 1     # matches the existing $0.005 / call pricing
                                  # rounded up to whole cents (cents must be int)


def counter_fee_cents(credits_cents: int) -> int:
    """The published counter fee (STORE.md §2d.4) on a top-up that credits
    `credits_cents` of wallet money: COUNTER_FEE_PCT %, rounded half-up to the
    cent. Integer-exact — no float, so the fee never drifts by a rounding ULP.

    price = credits_cents + counter_fee_cents(credits_cents); fee is what the
    store keeps, credits is what lands in the wallet. This one function is the
    single source of the fee for BOTH the custom Checkout top-up and the SPT
    agentic top-up (and it reproduces every CREDIT_PACKS price exactly — see the
    module-load assert)."""
    if credits_cents < 0:
        raise ValueError("credits_cents must be non-negative")
    # round-half-up in integer arithmetic: floor((x*105 + 50) / 100)
    price = (credits_cents * (100 + COUNTER_FEE_PCT) + 50) // 100
    return price - credits_cents


# Fail loudly at import if a pack key drifts from the PackName Literal, or if a
# pack's price ever stops equalling credits + the published counter fee — either
# would make the receipt lie about the fee.
assert set(CREDIT_PACKS) == set(PackName.__args__), (  # type: ignore[attr-defined]
    "CREDIT_PACKS keys must match the PackName Literal"
)
for _name, _p in CREDIT_PACKS.items():
    assert _p["price_cents"] == _p["credits_cents"] + counter_fee_cents(
        _p["credits_cents"]
    ), f"pack {_name!r} price != credits + counter fee — packs and fee disagree"
del _name, _p

# Stripe event types we actually act on. Anything else is acked + ignored.
# With Managed Payments (default on 2026 accounts) Stripe chooses the payment
# methods, so a session can complete with payment_status="unpaid" (async
# methods) — the credit then arrives via async_payment_succeeded. We credit
# on (completed AND paid) or on async_payment_succeeded; a completed-unpaid
# event is acked without crediting.
EVENT_CHECKOUT_COMPLETED = "checkout.session.completed"
EVENT_ASYNC_PAYMENT_SUCCEEDED = "checkout.session.async_payment_succeeded"
_CREDITING_EVENTS = (EVENT_CHECKOUT_COMPLETED, EVENT_ASYNC_PAYMENT_SUCCEEDED)

# ─── Agentic (Shared Payment Token) top-up — PREVIEW ────────────────────────
#
# Stripe's machine-payments SPT flow lets an agent fund its wallet by handing us
# a scoped, delegated payment credential (an SPT, `spt_…`) that we redeem by
# creating a PaymentIntent — no human clicking a hosted Checkout URL. See
# vend/AGENTIC_PAYMENTS.md for the full research + the live-activation gates.
#
# PREVIEW, not GA: the `payment_method_data[shared_payment_granted_token]`
# parameter exists ONLY under this preview API version (it is absent from the GA
# PaymentIntents reference). We pin it per-request so the GA Checkout path above
# is unaffected. Bumping this constant requires re-verifying the parameter
# against docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens — a
# preview version can rename fields. Live use additionally needs preview
# services-terms acceptance, a US legal entity, and a ROTATED key (the current
# sk_test_* transited a chat once). Test mode works with an ordinary sk_test_*
# and a token minted by the test_helpers/shared_payment/granted_tokens helper.
AGENTIC_PREVIEW_API_VERSION = "2026-04-22.preview"


# ─── Errors ─────────────────────────────────────────────────────────────────


class BillingError(Exception):
    """Base for charge-time errors that the HTTP layer translates to 402."""


class UnknownKeyError(BillingError):
    """The api_key isn't in the keys table."""


class InsufficientCreditsError(BillingError):
    """The key exists but the wallet is below the requested cost. Carries the
    millicent-precise available/required figures for the 402 (STORE.md §6 —
    the balance must never lie about what it holds)."""

    def __init__(self, available_millicents: int, required_millicents: int):
        self.available_millicents = available_millicents
        self.required_millicents = required_millicents
        # Anchor SKUs (the $2 session) require full price up front — no eaten
        # tail (that would be a discount exploit) — so an underfunded wallet is
        # pointed at the top-up options, including the $2 custom minimum, rather
        # than stranded (rerun P4).
        super().__init__(
            f"Insufficient credits ({available_millicents} millicents "
            f"available, {required_millicents} required). Top up: POST "
            f"/v1/billing/checkout_session with a custom {{amount_cents}} "
            f"(minimum {CUSTOM_MIN_CENTS}¢ = ${CUSTOM_MIN_CENTS / 100:.2f}) or a "
            f"named pack (small $10.50 | medium $52.50 | large $210); agentic "
            f"top-up: POST /v1/billing/agentic_topup."
        )


class PaymentDeclinedError(BillingError):
    """An agentic (SPT) charge failed at Stripe — declined card, an expired or
    over-limit shared payment token, or the preview not being enabled on the
    account. Wraps the Stripe error so the HTTP layer answers 402 (payment
    failed), never a 500. Carries no card data — only Stripe's message."""


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


def _release_event(event_id: str) -> None:
    """Release a claimed event so Stripe's retry can reprocess it.

    Called when processing fails AFTER a successful claim. Without this,
    a transient failure (e.g. the credit write hiccups) leaves the event
    permanently claimed: every retry returns duplicate=True and the
    customer paid without ever being credited — silently. Releasing the
    claim converts that into Stripe's normal at-least-once retry."""
    with _events_conn() as c:
        c.execute("DELETE FROM processed_stripe_events WHERE event_id = ?",
                  (event_id,))
        c.commit()


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
    real call.

    API version: modern stripe-python pins its own API version per SDK
    release, so requests are stable across account-default upgrades. Set
    STRIPE_API_VERSION only to override deliberately (e.g. to hold an old
    version during a staged migration)."""
    import stripe  # noqa: F401  (imported lazily so non-prod installs work)
    stripe.api_key = _required_env(
        "STRIPE_SECRET_KEY",
        "create Checkout sessions or verify webhook signatures",
    )
    pinned = os.environ.get("STRIPE_API_VERSION", "").strip()
    if pinned:
        stripe.api_version = pinned
    return stripe


def _resolve_topup(pack: Optional[PackName],
                   amount_cents: Optional[int]) -> dict:
    """Turn EITHER a pack name OR a custom amount_cents into the four numbers a
    top-up needs: {label, pack, credits_cents, price_cents, fee_cents}.

    Exactly one of pack/amount_cents must be given. A pack is looked up verbatim
    (fixed anchor — never re-derived). A custom amount credits `amount_cents` and
    prices it at credits + the published counter fee, so an agent buys exactly
    what it needs (GAUNTLET #2) instead of over-shooting to the smallest pack."""
    if (pack is None) == (amount_cents is None):
        raise ValueError("pass exactly one of pack or amount_cents")
    if pack is not None:
        if pack not in CREDIT_PACKS:
            raise ValueError(
                f"unknown pack {pack!r}; valid: {sorted(CREDIT_PACKS)}")
        p = CREDIT_PACKS[pack]
        return {"label": f"{pack} pack", "pack": pack,
                "credits_cents": p["credits_cents"],
                "price_cents": p["price_cents"],
                "fee_cents": p["price_cents"] - p["credits_cents"]}
    # Custom amount. Reject bool explicitly — bool is an int subclass, and a
    # stray True must not read as "1 cent".
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise ValueError("amount_cents must be an integer")
    if amount_cents < CUSTOM_MIN_CENTS:
        raise ValueError(
            f"amount_cents must be >= {CUSTOM_MIN_CENTS} (${CUSTOM_MIN_CENTS/100:.2f})")
    fee = counter_fee_cents(amount_cents)
    return {"label": "custom top-up", "pack": "custom",
            "credits_cents": amount_cents,
            "price_cents": amount_cents + fee, "fee_cents": fee}


def create_checkout_session(*, api_key: str, pack: Optional[PackName] = None,
                              amount_cents: Optional[int] = None,
                              success_url: str, cancel_url: str,
                              idempotency_key: Optional[str] = None) -> dict:
    """
    Creates a Stripe Checkout session for EITHER a named pack OR a custom
    `amount_cents` (min CUSTOM_MIN_CENTS). Returns {checkout_url, session_id,
    pack, price_cents, credits_cents, fee_cents} — fee_cents always names the
    5% counter fee explicitly. For a custom top-up `pack` is "custom".

    The api_key is stored in `metadata.api_key` so the webhook handler knows
    which balance to credit; `metadata.credits_cents` is what lands in the
    wallet — the webhook is amount-agnostic, so a custom amount flows through
    the SAME signed, deduped, replay-safe webhook with no handler change.

    Pass `idempotency_key` (e.g. the HTTP layer's request id) so a client retry
    replays the same session instead of minting a duplicate. It must be unique
    per *intended* purchase — never derive it from (api_key, amount) alone, or
    two deliberate purchases of the same size would collide.
    """
    if onboarding.lookup_key(api_key) is None:
        raise ValueError(f"unknown api_key {api_key!r}")
    t = _resolve_topup(pack, amount_cents)

    stripe = _stripe()
    extra = {"idempotency_key": idempotency_key} if idempotency_key else {}
    session = stripe.checkout.Session.create(
        **extra,
        mode="payment",
        # No payment_method_types: Managed Payments (default on this account)
        # chooses methods and REJECTS the parameter outright.
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                "name": f"SNHP credits ({t['label']}) — includes "
                        f"{COUNTER_FEE_PCT}% counter fee",
                # Managed Payments requires an eligible tax code.
                # txcd_10103001 = "Software as a service (SaaS) - business
                # use" (docs.stripe.com/tax/tax-codes) — API credits for
                # agent/business use, cloud-delivered, nothing downloaded.
                "tax_code": "txcd_10103001",
            },
                "unit_amount": t["price_cents"],
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "api_key": api_key,
            "pack": t["pack"],
            "credits_cents": str(t["credits_cents"]),
        },
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "pack": t["pack"],
        "price_cents": t["price_cents"],
        "credits_cents": t["credits_cents"],
        "fee_cents": t["fee_cents"],
    }


# ─── Webhook ────────────────────────────────────────────────────────────────


def _obj_get(obj, key, default=None):
    """Field access that works on BOTH plain dicts (tests, older SDKs) and
    stripe-python v15 StripeObjects (indexable, but no dict .get())."""
    try:
        val = obj[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if val is None else val


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

    if event_type not in _CREDITING_EVENTS:
        return {"processed": True, "event_id": event_id,
                "event_type": event_type, "handled": False}

    # Any failure past this point releases the claim so Stripe's retry can
    # reprocess — a claimed-but-uncredited event is a paid customer with no
    # credits, and it must never be silent (see _release_event).
    try:
        session = event["data"]["object"]
        meta = _obj_get(session, "metadata", {})
        api_key = _obj_get(meta, "api_key")
        credits_cents_str = _obj_get(meta, "credits_cents")
        if not api_key or not credits_cents_str:
            raise ValueError(
                f"checkout.session.completed missing metadata.api_key or "
                f"metadata.credits_cents (event {event_id})"
            )
        if (event_type == EVENT_CHECKOUT_COMPLETED
                and _obj_get(session, "payment_status") not in (None, "paid")):
            # Async method: completed but unpaid. Ack (claimed) without
            # crediting; the async_payment_succeeded event credits later.
            return {"processed": True, "event_id": event_id,
                    "event_type": event_type, "handled": True,
                    "awaiting_payment": True, "duplicate": False}
        credits_cents = int(credits_cents_str)
        # Top-up lands in the FUNDED bucket: cents from Stripe metadata × 1000
        # (STORE.md §2d.4 — own money, distinct from the starter grant).
        new_balance_millicents = onboarding.wallet_credit(
            api_key=api_key,
            millicents=credits_cents * onboarding.MILLICENTS_PER_CENT,
            bucket="funded",
        )
    except Exception:
        _release_event(event_id)
        raise
    return {
        "processed": True, "event_id": event_id, "event_type": event_type,
        "api_key": api_key, "credits_cents": credits_cents,
        "new_balance_millicents": new_balance_millicents, "duplicate": False,
    }


# ─── Agentic top-up: redeem a Shared Payment Token (PREVIEW) ────────────────


def agentic_topup(*, api_key: str, amount_cents: int, payment_token: str,
                  idempotency_key: Optional[str] = None) -> dict:
    """Fund a wallet by redeeming a Shared Payment Token (SPT) the agent carries
    — the agent-initiated path that needs no human at a Checkout URL.

    Same fee arithmetic as the custom Checkout top-up: credits = amount_cents,
    price = amount_cents + the 5% counter fee. We create + confirm a PaymentIntent
    carrying the SPT, and on `succeeded` credit amount_cents×1000 millicents to
    the funded bucket. Replay-safe: a client retry (same idempotency_key →
    Stripe idempotency) can't double-charge the SPT, and we dedupe the wallet
    credit on the returned PaymentIntent id via the SAME claim-first /
    release-on-failure discipline as the webhook.

    PREVIEW — see AGENTIC_PREVIEW_API_VERSION and vend/AGENTIC_PAYMENTS.md. In
    test mode `_stripe()` is monkeypatched exactly like the rest of the suite,
    so this never networks.

    Returns {credited, ...}. Raises:
      ValueError            — unknown api_key, sub-floor amount, or bad token
      PaymentDeclinedError  — Stripe rejected the redeem (decline / expired or
                              over-limit SPT / preview not enabled) → HTTP 402
    """
    if onboarding.lookup_key(api_key) is None:
        raise ValueError(f"unknown api_key {api_key!r}")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise ValueError("amount_cents must be an integer")
    if amount_cents < CUSTOM_MIN_CENTS:
        raise ValueError(
            f"amount_cents must be >= {CUSTOM_MIN_CENTS} (${CUSTOM_MIN_CENTS/100:.2f})")
    if not isinstance(payment_token, str) or not payment_token.strip():
        raise ValueError("payment_token (a shared payment token) is required")

    fee = counter_fee_cents(amount_cents)
    price_cents = amount_cents + fee

    stripe = _stripe()
    # Per-request preview version pin (NOT stripe.api_version = …) so the GA
    # Checkout path stays on the SDK's default version.
    opts = {"stripe_version": AGENTIC_PREVIEW_API_VERSION}
    if idempotency_key:
        opts["idempotency_key"] = idempotency_key
    try:
        intent = stripe.PaymentIntent.create(
            amount=price_cents,
            currency="usd",
            # The one seller-side delta from ordinary card acceptance: redeem
            # the delegated SPT the agent handed us.
            payment_method_data={"shared_payment_granted_token": payment_token},
            confirm=True,
            metadata={
                "api_key": api_key,
                "credits_cents": str(amount_cents),
                "kind": "agentic_topup",
            },
            **opts,
        )
    except Exception as e:  # stripe.error.* — a redeem failure, never a 500
        raise PaymentDeclinedError(str(e)) from e

    # Attribute access (not _obj_get's subscript): a stripe-python PaymentIntent
    # and the test fake both expose these as attributes, mirroring how
    # create_checkout_session reads session.url / session.id above.
    status = getattr(intent, "status", None)
    intent_id = getattr(intent, "id", None)
    base = {
        "status": status,
        "payment_intent_id": intent_id,
        "amount_cents": amount_cents,
        "credits_cents": amount_cents,
        "price_cents": price_cents,
        "fee_cents": fee,
    }
    if status != "succeeded":
        # requires_action / processing / requires_payment_method: do NOT credit
        # inline. Async completion (a payment_intent.succeeded webhook branch) is
        # deferred — see AGENTIC_PAYMENTS.md §4b. Uncommon for a delegated token.
        return {**base, "credited": False}

    if not intent_id:
        # Succeeded but no id to dedupe on — refuse rather than credit blindly.
        raise PaymentDeclinedError("PaymentIntent succeeded without an id")

    # Dedupe the wallet credit on the PaymentIntent id (claim-first). A retry
    # that returns the same succeeded intent is a no-op, not a double credit.
    if not _claim_event(intent_id, "agentic_topup"):
        return {**base, "credited": True, "duplicate": True}
    try:
        new_balance = onboarding.wallet_credit(
            api_key=api_key,
            millicents=amount_cents * onboarding.MILLICENTS_PER_CENT,
            bucket="funded",
        )
    except Exception:
        _release_event(intent_id)
        raise
    return {**base, "credited": True, "duplicate": False,
            "new_balance_millicents": new_balance}


# ─── Charge (called by paid endpoints) ──────────────────────────────────────


def charge_or_raise(api_key: str, cents: int) -> dict:
    """
    Charge `cents` from the ONE wallet (starter bucket first, then funded), so
    the starter credit legitimately funds part of an anchor $2 session. Raises
    BEFORE any debit:
      UnknownKeyError          — api_key not found
      InsufficientCreditsError — exists but wallet total < cost (millicent-precise)

    Returns the funding split + balance_after (the wallet_debit summary) so a
    caller that must refund-on-failure can reverse the EXACT buckets it spent
    (see wallet_refund). The caller (typically an HTTP handler) translates the
    exceptions to a 402 response.
    """
    info = onboarding.lookup_key(api_key)
    if info is None:
        raise UnknownKeyError(f"unknown api_key {api_key!r}")
    # Fallback grant for a key minted before issuance granted the starter;
    # idempotent and unconditional (§6), so a normal key is a no-op here.
    onboarding.wallet_grant_starter(api_key)
    required = cents * onboarding.MILLICENTS_PER_CENT
    avail = onboarding.wallet_available(api_key)
    if avail["total_millicents"] < required:
        raise InsufficientCreditsError(avail["total_millicents"], required)
    # A concurrent drain between the check and the debit is the store's loss,
    # never a double-charge (wallet_debit reports any shortfall, never raises).
    return onboarding.wallet_debit(api_key, required)

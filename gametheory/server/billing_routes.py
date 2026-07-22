"""Stripe billing over HTTP — credit packs for paid endpoints.

Re-wires the fully-tested billing module (gametheory/server/billing.py)
into the app, per the note in test_billing.py ("re-wiring is one route
addition"). Three routes:

  POST /v1/billing/checkout_session   {api_key, pack|amount_cents} → Checkout URL
  POST /v1/billing/agentic_topup      {api_key, amount_cents, payment_token} →
                                      redeem a Shared Payment Token (PREVIEW)
  POST /v1/billing/webhook            Stripe events (signature-verified)
  GET  /v1/billing/balance            X-API-Key → the one wallet (millicents)

Plus the first paid product endpoint:

  POST /v1/advice                     NEXTMOVE: $2/advice off the balance
                                      (vend.advice.advise_charged)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from gametheory.server import billing, onboarding

router = APIRouter(prefix="/v1", tags=["billing"])


# ─── Checkout ────────────────────────────────────────────────────────────────

class CheckoutIn(BaseModel):
    api_key: str
    # EITHER a named pack OR a custom amount_cents (min 200 = $2.00). Exactly one;
    # the billing module enforces it. Custom lets an agent buy exactly what it
    # needs ($2 credit → $2.40) instead of over-shooting to the smallest pack.
    pack: Optional[str] = Field(
        default=None, description="small ($10.80) | medium ($52.80) | large ($210.30)")
    amount_cents: Optional[int] = Field(
        default=None,
        description="custom top-up: cents of wallet credit (min 200); "
                    "you pay this + the counter fee (5% + 30¢)")
    success_url: str = "https://snhp.dev/paid"
    cancel_url: str = "https://snhp.dev/cancel"


@router.post("/billing/checkout_session")
def checkout_session(body: CheckoutIn, request: Request):
    try:
        return billing.create_checkout_session(
            api_key=body.api_key, pack=body.pack,  # type: ignore[arg-type]
            amount_cents=body.amount_cents,
            success_url=body.success_url, cancel_url=body.cancel_url,
            # client retries replay the same session instead of minting dupes
            idempotency_key=request.headers.get("x-request-id"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Agentic top-up: redeem a Shared Payment Token (PREVIEW) ──────────────────

class AgenticTopupIn(BaseModel):
    api_key: str
    amount_cents: int = Field(
        description="cents of wallet credit to buy (min 200); you pay this + "
                    "the counter fee (5% + 30¢)")
    payment_token: str = Field(
        description="a Stripe Shared Payment Token (spt_…) the agent carries")


@router.post("/billing/agentic_topup")
def agentic_topup(body: AgenticTopupIn, request: Request):
    """Fund the wallet by redeeming an agent-carried Shared Payment Token — no
    human at a hosted Checkout URL. Same counter fee (5% + 30¢) as every top-up;
    the fee is printed in the response as fee_cents.

    PREVIEW: Stripe's SPT flow is a versioned preview and needs preview
    services-terms acceptance + a US legal entity + a rotated key before live
    use (see vend/AGENTIC_PAYMENTS.md). Test mode works with the monkeypatched
    Stripe layer / an ordinary sk_test_* + a test-helper token."""
    try:
        return billing.agentic_topup(
            api_key=body.api_key, amount_cents=body.amount_cents,
            payment_token=body.payment_token,
            # client retries replay the same PaymentIntent, never a double charge
            idempotency_key=request.headers.get("x-request-id"),
        )
    except billing.PaymentDeclinedError as e:
        # decline / expired-or-over-limit SPT / preview not enabled
        raise HTTPException(status_code=402, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Webhook ────────────────────────────────────────────────────────────────

@router.post("/billing/webhook")
async def webhook(request: Request,
                  stripe_signature: Optional[str] = Header(None)):
    payload = await request.body()
    try:
        return billing.handle_webhook(payload=payload,
                                      signature=stripe_signature)
    except ValueError as e:
        # bad signature / malformed event → 400 (Stripe will retry non-2xx)
        raise HTTPException(status_code=400, detail=str(e))


# ─── Balance ────────────────────────────────────────────────────────────────

@router.get("/billing/balance")
def balance(x_api_key: str = Header(..., alias="X-API-Key")):
    """The ONE wallet, in millicents (1000 per cent), with the starter grant
    and own-money buckets both visible — the balance no longer lies about the
    50¢ (STORE.md §6). The key travels in the X-API-Key header, never a query
    param (a secret must not land in access logs or proxies).

    `guaranteed_calls_remaining` (roadmap: fund the pipeline before the 402) is a
    CONSERVATIVE floor per registered commodity slot: total // max_price_millicents
    — how many calls the wallet can afford if EVERY call cost the published
    ceiling. It is a floor because calls settle at wholesale passthrough (usually
    well under the cap), so the real number is ≥ this. Stateless and mechanical:
    no trailing average, no state, no telemetry read. An UNAVAILABLE slot (no
    healthy backend) reports 0 — you are guaranteed no calls it cannot serve."""
    if onboarding.lookup_key(x_api_key) is None:
        raise HTTPException(status_code=404, detail="unknown api_key")
    w = onboarding.wallet_available(x_api_key)
    total = w["total_millicents"]
    # Exact display (rerun P3/P5): a millicent is $0.00001, so five decimals show
    # the balance EXACTLY, built by integer arithmetic (no float rounding). The
    # 2-decimal figure that used to sit here silently rounded sub-cent balances.
    per_dollar = 100 * onboarding.MILLICENTS_PER_CENT
    return {
        "starter_millicents": w["starter_millicents"],
        "funded_millicents": w["funded_millicents"],
        "total_millicents": total,
        "usd_display": f"${total // per_dollar}.{total % per_dollar:05d}",
        "usd_display_rounded": f"${total / per_dollar:.2f}",
        "millicents_per_cent": onboarding.MILLICENTS_PER_CENT,
        "guaranteed_calls_remaining": _guaranteed_calls_remaining(total),
    }


def _guaranteed_calls_remaining(total_millicents: int) -> dict:
    """Conservative floor of affordable calls per registered COMMODITY slot,
    priced at the published ceiling (max_price_millicents): total // ceiling.
    A floor because real settlement is wholesale passthrough ≤ the ceiling. An
    unavailable slot (no healthy backend) is 0 — no call it cannot serve is
    guaranteed. Anchor SKUs are catalog-level, not registered slots, so they do
    not appear here. Best-effort: if the store package isn't in this build the
    hint is simply absent ({}), never a 500."""
    try:
        from vend import shelf as _shelf, store as _store
    except ImportError:
        return {}
    _shelf.ensure_shelf()
    out: dict = {}
    for sid, slot in _store.SLOTS.items():
        cap = slot.max_price_millicents
        # Unavailable slot or a non-positive cap (defensive) → 0; the cap is the
        # published ceiling, so total // cap is the conservative floor.
        out[sid] = 0 if (cap <= 0 or slot.tier == "unavailable") \
            else total_millicents // cap
    return out


# ─── NEXTMOVE: paid negotiation sessions ($2 covers the whole negotiation) ──

class SessionOpenIn(BaseModel):
    api_key: str
    category: str = Field(description="resale | supply | retail")
    side: str = Field(description="buy | sell")
    walk_away: float
    target: float
    their_offers: Optional[list[float]] = None   # pass to get the first move back
    my_offers: Optional[list[float]] = None
    rounds_left: Optional[int] = None
    seed: int = 0


class SessionMoveIn(BaseModel):
    api_key: str
    session_id: str
    their_offers: list[float]
    my_offers: Optional[list[float]] = None
    rounds_left: Optional[int] = None


def _advice_dict(a, idx):
    return {"move": a.move, "offer": a.offer, "message": a.message,
            "why": a.why, "confidence_note": a.confidence_note,
            "context_hash": a.context_hash, "policy_id": a.policy_id,
            "move_index": idx, "compute": a.engine.get("compute", {}),
            # W2 handoff: the signed move receipt (GAUNTLET #4) travels with
            # every move — the session open, the first move, and each move after.
            "receipt": a.receipt}


@router.post("/advice/session", tags=["negotiation"])
def open_advice_session(body: SessionOpenIn):
    """Open a PAID negotiation session: $2 once covers every move of this
    negotiation (cap 10 moves, 7 days). Category-tuned, deterministic,
    receipted. The free generic tool is POST /v1/negotiate/turn — pay for
    the tuned, auditable, replayable version. Pass their_offers to get the
    first move back with the session."""
    try:
        from vend import session as _vs, telemetry as _tm
    except ImportError:
        raise HTTPException(status_code=503,
                            detail="advice module not present in this build")
    try:
        sess = _vs.open_session_charged(
            api_key=body.api_key, category=body.category, side=body.side,
            walk_away=body.walk_away, target=body.target, seed=body.seed)
    except billing.InsufficientCreditsError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except billing.UnknownKeyError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        _tm.log_session_open(api_key=body.api_key, door="http",
                             category=body.category, side=body.side,
                             stake=abs(body.target - body.walk_away),
                             price_cents=sess["price_cents"],
                             session_id=sess["session_id"])
    except Exception:
        pass
    out = dict(sess)
    if body.their_offers is not None:
        a, idx = _vs.session_advise(
            session_id=sess["session_id"], api_key=body.api_key,
            their_offers=body.their_offers, my_offers=body.my_offers,
            rounds_left=body.rounds_left)
        try:
            _tm.log_advice(advice=a, api_key=body.api_key, door="http",
                           price_cents=0, session_id=sess["session_id"],
                           move_index=idx)
        except Exception:
            pass
        out["first_move"] = _advice_dict(a, idx)
    return out


@router.post("/advice/move", tags=["negotiation"])
def advice_move(body: SessionMoveIn):
    """A move inside your paid session — no additional charge. Pass the
    FULL offer history each time, oldest first."""
    try:
        from vend import session as _vs, telemetry as _tm
    except ImportError:
        raise HTTPException(status_code=503,
                            detail="advice module not present in this build")
    try:
        a, idx = _vs.session_advise(
            session_id=body.session_id, api_key=body.api_key,
            their_offers=body.their_offers, my_offers=body.my_offers,
            rounds_left=body.rounds_left)
    except _vs.SessionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        _tm.log_advice(advice=a, api_key=body.api_key, door="http",
                       price_cents=0, session_id=body.session_id,
                       move_index=idx)
    except Exception:
        pass
    return _advice_dict(a, idx)


class BundleMoveIn(BaseModel):
    api_key: str
    session_id: str
    issues: list[dict]
    their_offers: Optional[list[dict]] = None
    my_priorities: Optional[dict] = None
    my_batna: float = 0.40
    their_batna_estimate: float = 0.40
    cooperation: Optional[float] = None


@router.post("/advice/bundle", tags=["negotiation"])
def advice_bundle_move(body: BundleMoveIn):
    """A MULTI-ISSUE move inside your paid session — the logrolling tier the
    free tool lacks. No additional charge. Returns the recommended package
    (guaranteed to clear your stated BATNA), trade logic, inferred
    counterparty priorities, acceptance probability, and the receipt."""
    try:
        from vend import session as _vs, telemetry as _tm
    except ImportError:
        raise HTTPException(status_code=503,
                            detail="advice module not present in this build")
    try:
        a, idx = _vs.session_advise_bundle(
            session_id=body.session_id, api_key=body.api_key,
            issues=body.issues, their_offers=body.their_offers,
            my_priorities=body.my_priorities, my_batna=body.my_batna,
            their_batna_estimate=body.their_batna_estimate,
            cooperation=body.cooperation)
    except _vs.SessionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid issues spec: {e}")
    try:
        _tm.log_advice(advice=a, api_key=body.api_key, door="http",
                       price_cents=0, session_id=body.session_id, move_index=idx)
    except Exception:
        pass
    return {"move": a.move, "package": a.engine.get("package"),
            "message": a.message, "why": a.why,
            "confidence_note": a.confidence_note,
            "context_hash": a.context_hash, "move_index": idx,
            "their_expected_utility": a.engine.get("their_expected_utility"),
            "acceptance_probability": a.engine.get("acceptance_probability"),
            # W2 handoff: the signed bundle-move receipt (GAUNTLET #4).
            "receipt": a.receipt}


class SessionCloseIn(BaseModel):
    api_key: str
    session_id: str


@router.post("/advice/close", tags=["negotiation"])
def close_advice_session(body: SessionCloseIn):
    """Mark the negotiation finished. Optional but good hygiene — it
    timestamps the outcome, which calibrates the category priors. Returns the
    `closed` flag AND a signed session-summary receipt (GAUNTLET #4: the close
    used to emit nothing auditable) — moves count, total charged, and the
    per-move context_hashes — for the customer to hand a principal. An unknown
    session or key mismatch → 404 (indistinguishable, so a session id can't be
    probed with someone else's key)."""
    from vend import session as _vs
    closed = _vs.close_session(session_id=body.session_id, api_key=body.api_key)
    try:
        receipt = _vs.session_summary_receipt(session_id=body.session_id,
                                              api_key=body.api_key)
    except _vs.SessionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"closed": closed, "receipt": receipt}


class RotateIn(BaseModel):
    api_key: str


@router.post("/keys/rotate", tags=["discovery"])
def rotate_key(body: RotateIn):
    """Rotate your API key: a replacement is issued, the full credit
    balance carries over, and the old key is invalidated IMMEDIATELY (no
    grace period — possession of the key is the authorization, and a
    compromised key must die at once). Save the new key: keys are shown
    once and cannot be recovered, only rotated. Lost your key entirely?
    Email the contact address you registered with from that same address —
    recovery is a manual, human-verified process by design."""
    out = onboarding.rotate_key(body.api_key)
    if out is None:
        raise HTTPException(status_code=401,
                            detail="unknown or already-revoked api_key")
    return out


class RequestIn(BaseModel):
    text: str = Field(max_length=4000, description="what you wish the machine stocked")
    api_key: Optional[str] = None
    # Roadmap: a voter can ask to be told when the ask is stocked. Recorded only
    # with a key (an anonymous watch has no one to notify); poll-based, no push.
    watch: bool = Field(
        default=False,
        description="with an api_key, flag this ask to hear back on a status "
                    "flip — poll GET /v1/store/my_requests; no email/webhook")


@router.post("/advice/request", tags=["discovery"])
def advice_request(body: RequestIn):
    """The null-query intake: ask for anything the machine doesn't stock.
    Free. Size-capped, stored as data, never rendered raw. Unmet demand
    decides what gets stocked next. Legacy name for the same intake as
    POST /v1/store/request — one box, two doors (GAUNTLET #5): every
    filing gets a request_id you can check.

    Pass `watch: true` WITH an api_key to flag the ask for a heads-up on a
    status flip (poll GET /v1/store/my_requests to see it — the notify is
    poll-based, no push); an anonymous watch is ignored. The chosen flag is
    echoed back as `watch`."""
    try:
        from vend import demand as _demand
    except ImportError:
        raise HTTPException(status_code=503, detail="not present in this build")
    rec = _demand.file_request(text=body.text, api_key=body.api_key,
                               door="http", watch=body.watch)
    # Superset of the legacy {logged, truncated} shape — additive only, so
    # pre-spine callers keep working while new ones get the status pointer.
    return {"logged": True,
            "truncated": len(str(body.text)) > 2000,
            "request_id": rec["request_id"],
            "status": rec["status"],
            "watch": rec["watch"],
            "check": f"GET /v1/store/request/{rec['request_id']}"}


# ─── THE STORE: the commodity shelf over HTTP (see vend/STORE.md) ────────────

@router.get("/store/catalog", tags=["store"])
def store_catalog():
    """THE STORE's shelf: the commodity slots (tier, admission cap,
    predicate id, request doc, serving-backend ids), the anchor SKUs, and the
    two published pricing facts — wholesale-passthrough cost basis on every
    receipt plus the counter fee on top-ups. No key material ever appears
    here."""
    try:
        from vend import shelf as _shelf, store as _store
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    _shelf.ensure_shelf()
    return _store.catalog()


@router.get("/store/notary_pubkey", tags=["store"])
def store_notary_pubkey():
    """The receipt-signing notary's PUBLIC key, at a stable path so a verifier
    can PIN it OUT-OF-BAND (not just trust the pubkey embedded in a receipt) and
    confirm it matches the receipt's pubkey_fingerprint. Returns {pubkey_pem,
    fingerprint, key_source}. This is the STORE receipt notary (vend.receipt_
    signing / NOTARY_KEY_PEM) — DISTINCT from /v1/keys/trust_anchor (first-strike
    CA) and /v1/keys/settlement_notary (AP2 mandates), which are different keys.

    key_source is VISIBLE: with 'ephemeral' a signature proves only signer-
    consistency within one server lifetime; a production notary pins a persistent
    key ('env', from NOTARY_KEY_PEM). Never returns private material."""
    try:
        from vend.receipt_signing import signing_info
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    info = signing_info()
    return {"pubkey_pem": info["pubkey_pem"],
            "fingerprint": info["pubkey_fingerprint"],
            "key_source": info["key_source"]}


class FetchIn(BaseModel):
    # api_key is OPTIONAL in the body: carry it in an Authorization: Bearer gt_*
    # or X-API-Key header instead, and it reaches W3's 600/min keyed rate-limit
    # lane (the limiter only reads headers). A body-only key still works but
    # falls to the 60/min per-IP floor. Exactly one source must supply it.
    api_key: Optional[str] = None
    url: str = Field(max_length=2048,
                     description="http(s) URL to read → markdown")


@router.post("/fetch", tags=["store"])
def store_fetch(body: FetchIn, request: Request):
    """Fetch/extract one page → markdown, paid from your wallet at wholesale
    passthrough. Settlement-on-delivery: charged ONLY on non-empty markdown.

    Pass your key in an `Authorization: Bearer gt_*` or `X-API-Key` header
    (RECOMMENDED — that reaches the 600/min keyed rate-limit lane; a body-only
    key falls to the 60/min per-IP floor because the limiter never parses
    bodies) or in the JSON body `api_key` (backcompat). The header wins if both
    are present.

    A backend or predicate failure is a NORMAL uncharged outcome — 200 with the
    canonical envelope {ok: false, charged: false, reason: <stable string>,
    code: <machine enum>} — because you cannot pay for nothing; that asymmetry is
    the product surface, not an HTTP error. `code` is one of unknown_slot,
    slot_unavailable, insufficient_balance, all_backends_failed, predicate_failed;
    a delivered-but-failed call may also carry backends_tried [{id, reason}],
    backends_untried, backend_id, and a retry_hint. One client code path reads
    `charged`/`code` for every outcome. (Legacy keys like `error` survive as
    aliases.) Insufficient balance → 402; a missing or unknown api_key → 401."""
    try:
        from vend import shelf as _shelf, store as _store
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    # One source of truth for what counts as a presented key (same helper the
    # rate limiter uses), header-first; fall back to the body field.
    from gametheory.server.middleware import bearer_api_key
    api_key = bearer_api_key(request) or body.api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="missing api_key (body, Authorization: Bearer, or X-API-Key)")
    _shelf.ensure_shelf()
    try:
        out = _store.call_slot("fetch", api_key, {"url": body.url}, "http")
    except ValueError as e:
        # A malformed url (bad scheme, no host, private/localhost host) is
        # rejected by the backend's pre-network validation — a client error,
        # not a settlement outcome.
        raise HTTPException(status_code=400, detail=str(e))
    if out.get("ok"):
        return out
    if out.get("error") == "insufficient_balance":
        # The engine maps an unknown key to an empty wallet by design (never an
        # error), so distinguish the two at the door to match the advice
        # routes' unknown-key → 401 / broke-key → 402 convention.
        if onboarding.lookup_key(api_key) is None:
            raise HTTPException(status_code=401, detail="unknown api_key")
        raise HTTPException(
            status_code=402,
            detail=(f"insufficient balance: need "
                    f"{out['needed_millicents']} millicents, have "
                    f"{out['available_millicents']}"))
    # predicate-fail / backend-fail / slot unavailable: 'cannot pay for
    # nothing' is a delivered product outcome, returned 200-shaped.
    return out


# ─── THE STORE: the demand loop's spine (GAUNTLET #5) ────────────────────────
# The null-query log stops being a write-only void: a filed request gets an id
# and a status you can GET, and the public tally is the §3 observatory's first
# increment. Filing is keyless-OK; status changes are the founder's judgment and
# have NO route (vend.demand.founder_set_status is Python-only).

class StoreRequestIn(BaseModel):
    text: str = Field(max_length=4000,
                      description="what you wish the counter stocked")
    api_key: Optional[str] = None
    # Roadmap: turn a voter into a reachable customer. Recorded only with a key
    # (an anonymous watch has no one to notify); poll-based, no push.
    watch: bool = Field(
        default=False,
        description="with an api_key, flag this ask to hear back on a status "
                    "flip — poll GET /v1/store/my_requests; no email/webhook")


@router.post("/store/request", tags=["store"])
def store_request(body: StoreRequestIn):
    """File a request for a capability the store doesn't stock. Free, keyless
    OK. Returns {request_id, status, watch, check} — the demand loop now hands
    back something to return FOR (GAUNTLET #5). Size-capped, stored as data,
    never rendered raw. Pass `watch: true` WITH an api_key to flag the ask for a
    heads-up on a status flip (poll GET /v1/store/my_requests — poll-based, no
    push); an anonymous watch is ignored, and the chosen flag is echoed back."""
    try:
        from vend import demand as _demand
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    rec = _demand.file_request(text=body.text, api_key=body.api_key, door="http",
                               watch=body.watch)
    return {"request_id": rec["request_id"], "status": rec["status"],
            "watch": rec["watch"],
            "check": f"GET /v1/store/request/{rec['request_id']}"}


@router.get("/store/request/{request_id}", tags=["store"])
def store_request_status(request_id: str):
    """Check a filed request by id: {request_id, status, status_note, filed_at,
    door, text}. `status` is 'logged' until the shelf-owner acts, then
    status_note carries the reason-to-return. Unknown id → 404. No key material;
    the text is display-truncated and remains untrusted data."""
    try:
        from vend import demand as _demand
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    rec = _demand.get_request(request_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown request_id")
    return rec


@router.get("/store/requests", tags=["store"])
def store_requests():
    """The public demand tally (GAUNTLET #5): {total, distinct, recent[],
    requests[]}. `requests` is distinct asks with EXACT-MATCH duplicate counts
    (whitespace/case folded, no fuzzy classification — mechanical, no LLM),
    most-asked first. No key material; text display-truncated."""
    try:
        from vend import demand as _demand
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    return _demand.tally()


@router.get("/store/my_requests", tags=["store"])
def store_my_requests(request: Request):
    """Your OWN filings (roadmap: a voter comes back a reachable customer), keyed
    to YOUR api_key — the private counterpart to the public GET /v1/store/requests
    tally. Carry the key in `Authorization: Bearer gt_*` or `X-API-Key`, never a
    query param (a secret must not land in access logs). A missing or unknown key
    → 401. Returns {requests: [{request_id, filed_at, text, status, status_note,
    status_ts, watch, same_ask_count}]}, newest first — text display-truncated,
    still untrusted data; no key material and no repeat_key on the surface. Only
    rows attributable to this key (via the keyed pseudonym, never a raw key match)
    are returned, so one key can never read another's filings."""
    try:
        from vend import demand as _demand
    except ImportError:
        raise HTTPException(status_code=503, detail="store not present in this build")
    from gametheory.server.middleware import bearer_api_key
    api_key = bearer_api_key(request)
    if not api_key or onboarding.lookup_key(api_key) is None:
        raise HTTPException(status_code=401, detail="unknown or missing api_key")
    return {"requests": _demand.my_requests(api_key)}

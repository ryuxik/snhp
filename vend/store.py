"""THE STORE — the slot abstraction + the settlement engine.

See STORE.md (v0.4). A slot is a capability promise, not a vendor (§2b):
production slots run ≥2 health-checked backends with automatic failover; the
receipt names the backend that served and its exact cost. The one invariant
the whole spec hangs on lives in `call_slot`:

    the wallet is debited only when a machine-checkable predicate passes; a
    backend failure or a predicate failure NEVER debits, and a delivered call
    settles at wholesale PASSTHROUGH — never more (§2d.4, §2d.5).

Settlement is optimistic (no holds): a concurrent-race shortfall is the
STORE's loss, logged, never the agent's — the "cannot pay for nothing"
asymmetry (§10 Q2). Predicates are mechanical; no LLM in the judgment path,
per house rules. No hard-coded store identity — operator, keys, and the fee
schedule are config (§2d.1: the endgame is a franchised system, not one
runnable instance).

Money is millicents (1 cent = 1000 millicents), the ONE wallet unit shared
with the anchor SKUs — see gametheory.server.onboarding.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Callable, Protocol, runtime_checkable

MILLICENTS_PER_CENT = 1000


class BackendError(Exception):
    """A backend could not deliver: transport error, timeout, non-2xx, or an
    empty/invalid upstream body. Raising it means 'try the next backend'; it
    is NEVER a debit — non-delivery is not a sale."""


@dataclass(frozen=True)
class BackendResult:
    payload: dict                 # slot-shaped goods (the fetch payload, etc.)
    wholesale_millicents: int     # exact cost basis for THIS call
    wholesale_estimated: bool     # True when upstream doesn't report usage
    backend_id: str
    meta: dict                    # upstream status, usage headers, etc.


@runtime_checkable
class Backend(Protocol):
    id: str

    def available(self) -> bool:
        """Cheap readiness check — e.g. the vendor key is configured. Only
        available backends are tried, and the count sets the slot tier."""
        ...

    def call(self, request: dict) -> BackendResult:
        """Deliver the goods or raise BackendError. Must never partially
        charge — settlement is the store's job, not the backend's."""
        ...


@dataclass(frozen=True)
class Receipt:
    """The Quote discipline applied to a fetch: price, exact cost basis,
    serving backend, and a content hash a third party can check against the
    payload it received. price_millicents is the passthrough price (==
    wholesale); the funding split records which buckets actually paid it, and
    balance_after is what the one wallet holds once the debit lands.

    ACCOUNTING (rerun P5): the price a caller OWED and the money that actually
    LEFT the wallet can differ by exactly one thing — the eaten tail at the
    depletion boundary. So the receipt states both, from wallet_debit's own
    numbers: `wallet_delta_millicents` is what the wallet actually moved and
    `absorbed_tail_millicents` is what the store ate (0 except on the last call
    that empties a wallet). The identity `price_millicents ==
    wallet_delta_millicents + absorbed_tail_millicents` always holds, so summing
    a key's receipts reconciles against its wallet movement EXACTLY — no
    inferring the tail. `price_usd` is the exact dollar string (5-decimal, no
    rounding) for a human-readable line.

    `upstream_ref` (rerun P5 / auditor) carries a whitelisted subset of the
    upstream vendor's own evidence for THIS call (a request/trace id and, when
    reported, the usage figure) — so an exact (`wholesale_estimated:false`) cost
    basis is backed by the vendor's own reference, not just our word. It is
    evidence-PASSTHROUGH, not invoice proof: it lets a third party ask the
    vendor to confirm the call; it does not itself prove the wholesale number.
    None when the upstream returned no such header.

    `runway_estimate_calls` (roadmap: a pipeline should fund BEFORE the 402, not
    after) is a STATELESS hint — "calls like this one left" — computed purely from
    THIS receipt: balance_after.total_millicents // price_millicents. No trailing
    average, no state, no telemetry read; it just divides the post-debit balance
    by the price the caller just paid. 0 at a drained wallet (the depletion
    boundary), and 0 as a divide-by-zero guard if this call happened to be free.

    On the way out of call_slot this dict is Ed25519-signed (see
    vend.receipt_signing): the returned receipt carries `signature`,
    `pubkey_fingerprint`, and `key_source`, so "price == wholesale" is
    third-party-checkable, not self-asserted (GAUNTLET #4). The recipe for both
    the content_hash and the signature is published in catalog()['receipts']."""
    slot_id: str
    backend_id: str
    price_millicents: int         # what was owed/charged (== wholesale)
    price_usd: str                # exact dollar string, e.g. "$0.49687" (no rounding)
    wholesale_millicents: int
    wholesale_estimated: bool
    wallet_delta_millicents: int  # what actually left the wallet (starter+funded spent)
    absorbed_tail_millicents: int # tail the store ate (0 except the depletion boundary)
    content_hash: str             # blake2b hexdigest of the canonical payload
    predicate: str                # versioned predicate id, e.g. "fetch.v1"
    funding: dict                 # {"starter_millicents": int,
                                  #  "funded_millicents": int}
    balance_after: dict           # {"starter_millicents", "funded_millicents",
                                  #  "total_millicents"} — the wallet post-debit
    runway_estimate_calls: int    # balance_after.total // price ("calls like this
                                  # one left") — stateless, 0 at a drained wallet
    ts: float
    upstream_ref: dict | None = None   # whitelisted upstream evidence (passthrough)


@dataclass
class Slot:
    """A capability promise. `tier` is a COMPUTED property (§2b: production
    ≥2 available backends, provisional 1, unavailable 0) — never a stored,
    stale label, since backend availability turns on env keys that arrive
    after import."""
    id: str
    title: str
    backends: list                # ordered; failover walks down the list
    predicate: Callable[[dict], tuple]   # mechanical only; (ok, reason)
    predicate_id: str             # version string stamped on every receipt
    max_price_millicents: int     # admission cap, published in the catalog
    request_doc: str              # one-line request schema for the catalog
    predicate_doc: str = ""       # what the predicate catches + its honest limit,
                                  # published in the catalog (auditor: fetch.v2 boundary)

    @property
    def available_backends(self) -> list:
        return [b for b in self.backends if b.available()]

    @property
    def tier(self) -> str:
        n = len(self.available_backends)
        if n >= 2:
            return "production"
        if n == 1:
            return "provisional"
        return "unavailable"


# ─── Registry (no hard-coded store identity — §2d.1) ─────────────────────────


SLOTS: dict[str, Slot] = {}


def register_slot(slot: Slot) -> Slot:
    """Register (or replace) a slot by id. Returns it for call-site chaining."""
    SLOTS[slot.id] = slot
    return slot


# ─── Telemetry sink (integrator's lane wires the real one) ───────────────────


def _noop_sink(**_kwargs) -> None:
    return None


# Integrator wires vend.telemetry.log_slot_call here (its lane). The default
# no-op keeps the settlement engine importable and unit-testable without the
# telemetry module, and every call — INCLUDING uncharged failures — goes
# through this one sink so non-delivery events are still recorded.
_TELEMETRY_SINK: Callable[..., None] = _noop_sink


def set_telemetry_sink(sink: Callable[..., None]) -> None:
    global _TELEMETRY_SINK
    _TELEMETRY_SINK = sink


def _emit(**fields) -> None:
    try:
        _TELEMETRY_SINK(**fields)
    except Exception:
        # Telemetry must never break settlement — a good was already
        # delivered/refused on its own terms before we log it.
        pass


# ─── Content hash ────────────────────────────────────────────────────────────


def _content_hash(payload: dict) -> str:
    """blake2b of the canonical payload — the receipt's checkable anchor."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str).encode()
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


# 1 dollar == 100 cents == 100_000 millicents, so a millicent is $0.00001 — five
# decimal places express it EXACTLY. Built by integer arithmetic (no float
# rounding): 49_687 millicents → "$0.49687". This is the exact-display rule
# (rerun P3/P5) — no figure the store prints is silently rounded.
_MILLICENTS_PER_DOLLAR = 100 * MILLICENTS_PER_CENT


def _exact_usd(millicents: int) -> str:
    """Exact dollar string for a millicent amount — five decimals, no rounding."""
    m = int(millicents)
    return f"${m // _MILLICENTS_PER_DOLLAR}.{m % _MILLICENTS_PER_DOLLAR:05d}"


# ─── The settlement engine ───────────────────────────────────────────────────


def call_slot(slot_id: str, api_key: str, request: dict, door: str) -> dict:
    """Run a slot end-to-end under the settlement invariant.

    1. Unknown slot / no available backend → error (no charge).
    2. Grant the starter credit lazily (first store contact), then admit while
       the wallet holds ANY money (total ≥ 1 millicent). NEVER-STRAND (§10 Q2):
       your last millicent buys a full call and the store eats any tail past
       your balance — only a truly empty wallet (total == 0) is refused. The
       tail-eating is bounded: once at zero, the next admission fails. This
       eat-the-tail admission is COMMODITY-slot only; anchor-priced SKUs charge
       their full price up front (see catalog()['admission']).
    3. Try available backends in order. A BackendError falls through (transport
       non-delivery). A DELIVERED payload is run through the mechanical predicate:
       a PASS is the one and only sale; a FAIL is not a sale either, so the
       cascade tries the next untried backend before giving up (rerun P1's dead
       end: a blank from backend A must reach backend B, not strand). No debit
       ever lands on a non-pass.
    4. Cascade exhausted with no pass → ONE uncharged failure envelope naming
       every attempt (backends_tried: [{id, reason}]) and the empty remainder
       (backends_untried), NEVER debited.
    5. First pass → debit the PASSTHROUGH price (== wholesale, never more) —
       capped at the balance, the shortfall the store's loss — build the receipt
       (which states the wallet delta and any absorbed tail from wallet_debit so
       the books reconcile exactly), return the goods.

    Every uncharged outcome is the normalized envelope {ok:false, charged:false,
    reason:<stable string>, code:<machine enum>} (rerun P5: one client code path)
    with optional backends_tried/backends_untried/retry_hint; legacy keys (e.g.
    `error`, `needed_millicents`) survive as aliases. At most ONE debit, only on
    a pass. Every path emits exactly one telemetry line, uncharged failures
    included.
    """
    from gametheory.server import onboarding

    slot = SLOTS.get(slot_id)
    if slot is None:
        _emit(api_key=api_key, door=door, slot_id=slot_id, backend_id=None,
              ok=False, settled=False, price_millicents=0,
              wholesale_millicents=0, wholesale_estimated=False, funding=None,
              shortfall_millicents=0, predicate=None, reason="unknown_slot",
              content_hash=None)
        # Normalized failure envelope (rerun P5); `error` kept as a legacy alias.
        return {"ok": False, "charged": False, "reason": "unknown_slot",
                "code": "unknown_slot", "error": "unknown_slot"}

    backends = slot.available_backends
    if not backends:
        _emit(api_key=api_key, door=door, slot_id=slot_id, backend_id=None,
              ok=False, settled=False, price_millicents=0,
              wholesale_millicents=0, wholesale_estimated=False, funding=None,
              shortfall_millicents=0, predicate=slot.predicate_id,
              reason="slot_unavailable", content_hash=None)
        return {"ok": False, "charged": False, "reason": "slot_unavailable",
                "code": "slot_unavailable", "error": "slot_unavailable"}

    # Fallback grant of the one-time starter credit for a key minted before
    # issuance granted it. Unconditional and idempotent (§6) — False here just
    # means it was already granted or the key is unknown; admission below is
    # the real gate.
    onboarding.wallet_grant_starter(api_key)

    avail = onboarding.wallet_available(api_key)
    spendable = avail["total_millicents"]
    # NEVER-STRAND admission (GAUNTLET #7 trapped-tail): admit on ANY positive
    # balance. The old gate (spendable ≥ max_price) stranded a ≤2¢ tail that
    # could still have bought a full call — the store already eats settlement
    # shortfalls, so let the last millicent through and eat the tail. Only a
    # zero balance is refused, which also bounds the tail-eating (the next call
    # at zero fails here).
    if spendable <= 0:
        _emit(api_key=api_key, door=door, slot_id=slot_id, backend_id=None,
              ok=False, settled=False, price_millicents=0,
              wholesale_millicents=0, wholesale_estimated=False, funding=None,
              shortfall_millicents=0, predicate=slot.predicate_id,
              reason="insufficient_balance", content_hash=None)
        return {"ok": False, "charged": False, "reason": "insufficient_balance",
                "code": "insufficient_balance", "error": "insufficient_balance",
                "needed_millicents": 1, "available_millicents": spendable}

    # Backends in order. A BackendError is 'try the next one'. A delivered
    # payload that FAILS the mechanical predicate is ALSO 'try the next one'
    # (rerun P1: a blank/block-page from backend A must cascade to backend B, not
    # strand as an uncharged dead end while a lever sat unused). Neither is a
    # charge. `backends_tried` collects EVERY non-passing attempt {id, reason} —
    # transport failures and predicate failures alike — so an exhausted cascade
    # names exactly what was tried and why (GAUNTLET #6).
    result: BackendResult | None = None
    backends_tried: list[dict] = []
    last_delivered: BackendResult | None = None   # last payload that DELIVERED
    last_predicate_reason: str | None = None      # its predicate-fail reason
    for backend in backends:
        try:
            r = backend.call(request)
        except BackendError as e:
            # str(e) is the backend's own reason string, which NEVER contains key
            # material (fetch_backends names error TYPES / statuses only).
            backends_tried.append({"id": backend.id, "reason": str(e)})
            continue
        ok, reason = slot.predicate(r.payload)
        if ok:
            result = r
            break
        # Delivered but did not clear the slot's own promise — not a sale. Record
        # the attempt and cascade to the next untried backend.
        last_delivered = r
        last_predicate_reason = reason
        backends_tried.append({"id": backend.id, "reason": reason})

    if result is None:
        # No backend produced a PASSING payload. Two shapes, one envelope:
        #  - nothing delivered at all (every backend raised) → all_backends_failed
        #  - at least one delivered but failed the predicate → predicate_failed
        # backends_untried is [] because the cascade tried every available
        # backend; a future predicate that signals a DEFINITIVE stop could leave
        # a remainder here instead.
        if last_delivered is None:
            _emit(api_key=api_key, door=door, slot_id=slot_id, backend_id=None,
                  ok=False, settled=False, price_millicents=0,
                  wholesale_millicents=0, wholesale_estimated=False, funding=None,
                  shortfall_millicents=0, predicate=slot.predicate_id,
                  reason="all_backends_failed", content_hash=None)
            return {"ok": False, "charged": False,
                    "reason": "all_backends_failed",
                    "code": "all_backends_failed",
                    "error": "all_backends_failed",   # legacy alias
                    "backends_tried": backends_tried, "backends_untried": [],
                    "retry_hint": (
                        f"all {len(backends_tried)} available backend(s) failed "
                        "to deliver — these are transient upstream errors (see "
                        "backends_tried); retry, or file a store_request if it "
                        "persists")}
        _emit(api_key=api_key, door=door, slot_id=slot_id,
              backend_id=last_delivered.backend_id, ok=False, settled=False,
              price_millicents=0,
              wholesale_millicents=last_delivered.wholesale_millicents,
              wholesale_estimated=last_delivered.wholesale_estimated, funding=None,
              shortfall_millicents=0, predicate=slot.predicate_id,
              reason=last_predicate_reason, content_hash=None)
        return {"ok": False, "charged": False, "reason": last_predicate_reason,
                "code": "predicate_failed",
                "backend_id": last_delivered.backend_id,
                "backends_tried": backends_tried, "backends_untried": []}

    # Predicate passed: settle at PASSTHROUGH (price == wholesale, never more).
    price = int(result.wholesale_millicents)
    debit = onboarding.wallet_debit(api_key, price)
    funding = {"starter_millicents": debit["starter_spent"],
               "funded_millicents": debit["funded_spent"]}
    # Reconciliation fields (rerun P5): what actually LEFT the wallet vs what the
    # store ATE. price == wallet_delta + absorbed_tail always, so summing a key's
    # receipts matches its wallet movement without inferring the tail.
    wallet_delta = debit["starter_spent"] + debit["funded_spent"]
    absorbed_tail = debit["shortfall_millicents"]
    # Lift the upstream's own evidence (a request/trace id, usage figure) onto the
    # receipt when the backend carried it — evidence-passthrough, not invoice proof.
    upstream_ref = (result.meta.get("upstream_ref")
                    if isinstance(result.meta, dict) else None)
    content_hash = _content_hash(result.payload)
    # Runway hint (roadmap: fund the pipeline before the 402, not after). Purely
    # from THIS receipt — "calls like this one left" = post-debit balance // the
    # price just paid. Stateless: no trailing average, no state, no telemetry
    # read. The `price > 0` is a divide-by-zero guard for a (degenerate) free
    # call; a real wholesale is always positive, and a drained wallet yields 0.
    balance_after_total = debit["balance_after"]["total_millicents"]
    runway_estimate_calls = balance_after_total // price if price > 0 else 0
    receipt = Receipt(
        slot_id=slot.id, backend_id=result.backend_id,
        price_millicents=price, price_usd=_exact_usd(price),
        wholesale_millicents=int(result.wholesale_millicents),
        wholesale_estimated=bool(result.wholesale_estimated),
        wallet_delta_millicents=wallet_delta,
        absorbed_tail_millicents=absorbed_tail,
        content_hash=content_hash, predicate=slot.predicate_id,
        funding=funding, balance_after=debit["balance_after"],
        runway_estimate_calls=runway_estimate_calls, ts=time.time(),
        upstream_ref=upstream_ref,
    )
    _emit(api_key=api_key, door=door, slot_id=slot.id,
          backend_id=result.backend_id, ok=True, settled=True,
          price_millicents=price,
          wholesale_millicents=int(result.wholesale_millicents),
          wholesale_estimated=bool(result.wholesale_estimated),
          funding=funding,
          shortfall_millicents=debit["shortfall_millicents"],
          predicate=slot.predicate_id, reason=None, content_hash=content_hash)
    # Sign the receipt (GAUNTLET #4): "price == wholesale" was two fields the
    # store wrote about itself; the notary signature makes it third-party-
    # checkable. safe_sign never eats a delivered good — a signing hiccup yields
    # signature=None (visibly unsigned), not a lost fetch the wallet already paid.
    from vend.receipt_signing import safe_sign
    return {"ok": True, "payload": result.payload,
            "receipt": safe_sign(asdict(receipt))}


# ─── Catalog ─────────────────────────────────────────────────────────────────


def _slot_entry(slot: Slot) -> dict:
    """Public slot view. Backends appear as IDS ONLY — never key material.
    `predicate_doc` (when the slot sets it) states what the settlement predicate
    catches and its honest limit, so a caller knows exactly which failures are
    uncharged and which still bill (auditor: the fetch.v2 boundary)."""
    entry = {
        "id": slot.id,
        "title": slot.title,
        "tier": slot.tier,
        "max_price_millicents": slot.max_price_millicents,
        "predicate_id": slot.predicate_id,
        "request_doc": slot.request_doc,
        "backends": [b.id for b in slot.backends],
    }
    if slot.predicate_doc:
        entry["predicate_doc"] = slot.predicate_doc
    return entry


def catalog() -> dict:
    """The counter's shelf: the commodity slots, the anchor SKUs, and the two
    published pricing facts (§2d.4). The money unit is stated explicitly at the
    top (millicents, 1000 per cent) so a naive agent never misprices. Anchor
    SKUs (the negotiation session and bundle) are catalog-level only this pass
    — priced from vend.advice constants, tier "anchor", NOT rewired through the
    live nextmove flow. Backends are exposed as ids only, so no key material
    ever leaves here.
    """
    # Lazy imports: the anchor pricing lives in vend.advice (which pulls the
    # negotiation engine) and the counter fee in billing — neither is needed
    # to run a commodity slot, so keep store.py light at import time.
    from vend.advice import ADVISE_COST_CENTS
    from gametheory.server.billing import COUNTER_FEE_PCT

    anchor_milli = ADVISE_COST_CENTS * MILLICENTS_PER_CENT
    anchors = [
        {"id": "negotiate.session", "title": "SNHP negotiation session",
         "tier": "anchor", "price_cents": ADVISE_COST_CENTS,
         "price_millicents": anchor_milli,
         "request_doc": "one negotiation, every move included "
                        "(category, side, walk_away, target)"},
        {"id": "negotiate.bundle", "title": "SNHP multi-issue bundle",
         "tier": "anchor", "price_cents": ADVISE_COST_CENTS,
         "price_millicents": anchor_milli,
         "request_doc": "logrolling package advice (issues[], my_batna)"},
    ]
    return {
        "unit": "millicents",
        "millicents_per_cent": MILLICENTS_PER_CENT,
        "counter_fee_pct": COUNTER_FEE_PCT,
        "keys": {
            "issue": "POST /v1/keys",
            "note": "the one-time starter credit attaches to the issued key",
        },
        "starter_credit": {
            "millicents": onboarding_starter_grant(),
            "usd": _exact_usd(onboarding_starter_grant()),
            "terms": "one-time, unconditional, no card required",
        },
        "admission": (
            "COMMODITY slots (the fetch slot and any other wholesale-passthrough "
            "slot): a call is admitted while your wallet holds ≥1 millicent — "
            "your last millicent buys a full call and the store eats the tail "
            "past your balance (the settlement-shortfall asymmetry, §10 Q2). Only "
            "a zero balance is refused (insufficient_balance); the "
            "max_price_millicents per slot is the published ceiling a single call "
            "can cost, not an admission floor. This eat-the-tail rule is scoped "
            "to commodity slots BECAUSE the eaten tail is bounded by the slot cap "
            "(fetch: 2000 millicents), so it is a rounding cost, not a discount. "
            "ANCHOR-priced SKUs (negotiate.session / negotiate.bundle) do NOT get "
            "the tail: they require their full price up front — eating $1.50 of a "
            "$2 session would be a 75% discount exploit, not a rounding cost — so "
            "an underfunded wallet gets a 402 pointing at top-up options "
            "(including the $2 custom minimum)."),
        "no_refund": (
            "funded credit is PREPAID and NON-REFUNDABLE — there is no cashout "
            "path; unspent credit stays as credit. Size top-ups to expected "
            "usage (the $2 custom minimum exists so you can buy small); the "
            "starter credit covers tasting the shelf first."),
        "acceptable_use": (
            "public-web http(s) fetching only; no credentialed or authenticated "
            "fetching, and IP-literal/localhost/.local targets are refused up "
            "front; upstream vendors enforce their own abuse controls; every "
            "call is per-key accountable via the receipt + telemetry."),
        "receipts": _receipts_block(),
        "slots": [_slot_entry(s) for s in SLOTS.values()] + anchors,
    }


def _receipts_block() -> dict:
    """How to VERIFY any store receipt independently — stated exactly so the
    hash recipe takes zero guesses (the GAUNTLET auditor needed ~13). Two parts:

      - `content_hash`: the exact blake2b recipe `_content_hash` uses, with the
        json.dumps kwargs spelled out, so a third party can recompute the anchor
        digest from the `payload` it received and match the receipt's field.
      - `signature`: the Ed25519 scheme, the bytes signed, and the notary pubkey
        PEM + fingerprint + key_source (`env`|`ephemeral`, visible) it verifies
        against — from vend.receipt_signing (the notary we already ship).
      - `pin`: where to fetch that same pubkey OUT-OF-BAND (a stable route),
        plus the honest caveat about what an `ephemeral` key can and cannot prove
        (auditor follow-up).
      - `upstream_ref`: what the receipt's optional `upstream_ref` field is —
        evidence-passthrough, NOT invoice proof (auditor follow-up).
    """
    from vend.receipt_signing import signing_info
    info = signing_info()
    return {
        "content_hash": {
            "algorithm": "blake2b",
            "digest_size": 16,
            "json_dumps": {"sort_keys": True, "separators": [",", ":"],
                           "default": "str"},
            "recipe": ("hashlib.blake2b(json.dumps(payload, sort_keys=True, "
                       "separators=(',', ':'), default=str).encode(), "
                       "digest_size=16).hexdigest()"),
            "hashed": "the `payload` object returned in the same response",
        },
        "signature": info,
        "pin": {
            "fetch_pubkey": "GET /v1/store/notary_pubkey",
            "match": ("pin the pubkey_pem/fingerprint fetched there out-of-band "
                      "and confirm it equals the receipt's pubkey_fingerprint "
                      "before trusting a signature"),
            "key_source_caveat": (
                f"this signer's key_source is {info['key_source']!r}. With "
                "'ephemeral' the key is generated per process, so a signature "
                "proves only signer-CONSISTENCY within one server lifetime "
                "(every restart reissues an unverifiable-after-the-fact history); "
                "a production notary pins a PERSISTENT key (NOTARY_KEY_PEM) whose "
                "'env' key_source makes the whole receipt history verifiable."),
        },
        "upstream_ref": (
            "a receipt may carry an `upstream_ref`: a whitelisted subset of the "
            "serving vendor's own evidence for the call (a request/trace id and, "
            "when reported, the usage figure). It is evidence-PASSTHROUGH — it "
            "lets a third party ask the vendor to confirm the call happened — NOT "
            "invoice proof; it does not by itself prove the wholesale number."),
        "runway_estimate_calls": (
            "every settled receipt carries `runway_estimate_calls` = "
            "balance_after.total_millicents // price_millicents — 'calls like "
            "this one left' at THIS call's exact price. A STATELESS hint (no "
            "trailing average, no state): it is 0 at a drained wallet, so a "
            "pipeline can top up BEFORE the next call 402s instead of after."),
    }


def onboarding_starter_grant() -> int:
    """The published starter-credit size, read from onboarding so the number
    is stated in exactly one place."""
    from gametheory.server.onboarding import STARTER_GRANT_MILLICENTS
    return STARTER_GRANT_MILLICENTS

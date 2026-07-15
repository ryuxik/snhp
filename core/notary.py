"""core/notary.py — the SNHP notary: signed, replayable discount-only receipts.

A NotaryReceipt is the company's first shippable artifact: a signed, standalone-
verifiable proof that ONE quote was discount-only and report-independent, built
directly on top of a `core.engine.Quote`. Nothing here is bespoke to a vertical
— it lifts the receipt DNA (canonical hashing, disclosure-digest-not-WTP, the
over-list-is-unconstructible invariant) into the core layer.

WHAT A RECEIPT ATTESTS (exactly this, and nothing more):

  (a)  discount-only        — the quoted price p never exceeded the public list
                              ℓ. Enforced at THREE gates: the receipt
                              constructor RAISES (NotaryViolation) if p > ℓ, the
                              emitting call re-checks, and the verifier re-checks
                              p ≤ ℓ on replay. `conditions.a` is therefore always
                              True on a constructed receipt.
  (a′) buffer dominance     — whether the min-gain buffer β dominated this
                              quote's excess rent: ℓ − c_eff ≤ 2β. `a_prime_ok`.
                              β = max(opts.min_gain_abs, opts.min_gain_frac·ℓ),
                              c_eff is the engine's cost floor for the quote.
  (b)  report-independent   — a probe (regime_probe) scaled the buyer's claimed
       reservation            outside option and watched the seller RESERVATION
                              basis (c_eff net of any capacity-relief credit on
                              the realized deal). Invariant ⇒ regime
                              "finite_stock", `conditions.b` True. Moves ⇒
                              "capacity", `conditions.b` False — reported
                              HONESTLY, never papered over.
  (c)  event-consistent     — the disagreement point both sides face is the menu
       disagreement           counterfactual (best full-price order), true BY
                              CONSTRUCTION of core.engine.quote; `engine_version`
                              pins WHICH construction so a verifier can audit the
                              code that made c hold. `conditions.c` is True.
  context reproducibility   — same `context_hash` + same `disclosure_digest` ⇒
                              same price. The disclosure_digest is a one-way
                              digest of (utilities, walk); the raw WTP is NEVER
                              present in the receipt.

WHAT IT DOES NOT ATTEST:

  - cross-merchant non-coordination beyond the committed context (v1 scope);
  - capacity-venue trustlessness — when regime == "capacity" the seller
    reservation depends on the buyer's private outside option, so the
    private-value leak SURVIVES even attestation of that option; `conditions.b`
    is False and `reservation_basis` says "attested(ô)" honestly;
  - buyer outside-option truth without an attestation token — v1's advisory API
    has no attestation, so `conditions.d` is False there. A caller that carries a
    real attestation passes attested=True and d becomes True.

DEPENDENCY DIRECTION: core/ imports nothing from vend/, gametheory/, block/.
This module is stdlib + `cryptography` + core.engine/core.api types only.

KEYS: signing key from env NOTARY_KEY_PEM (PKCS8 PEM) else an ephemeral key
generated at load; the key info exports `key_source` ("env"|"ephemeral") so a
verifier can SEE that an ephemeral key signed a receipt. The private key is
never printed, logged, or serialized.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, fields as _dc_fields
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
    load_pem_private_key, load_pem_public_key)

from core.engine import Quote, QuoteOpts, SeparableBuyer, quote as _engine_quote
from core.offer_graph import DimKind, qty_of

PROTOCOL = "snhp-notary/2"
_KEY_ENV_VAR = "NOTARY_KEY_PEM"
_TOL = 1e-9


# ── canonical hashing / disclosure digest (the receipt DNA, lifted) ────────
def _canon_bytes(obj) -> bytes:
    """Deterministic canonical-JSON encoding (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def canon_hash(obj) -> str:
    """Deterministic canonical-JSON sha256 of `obj` (prefixed so the hash
    algorithm is self-describing on the wire)."""
    return "sha256:" + hashlib.sha256(_canon_bytes(obj)).hexdigest()


def disclosure_digest(utilities: dict, walk_cost: float) -> str:
    """One-way digest of a buyer disclosure — the utilities (rounded) and the
    walk cost. This is what the receipt carries; the RAW WTP/utilities never
    appear in a receipt. Same disclosure ⇒ same digest, so "same context +
    same disclosure ⇒ same price" is auditable without exposing the report."""
    return canon_hash({"u": {str(k): round(float(v), 4)
                             for k, v in utilities.items()},
                       "w": round(float(walk_cost), 4)})


class NotaryViolation(ValueError):
    """A notary invariant was violated at construction — the receipt is
    UNCONSTRUCTIBLE (e.g. an over-list quote: p > ℓ). Mirrors vend's
    QuoteViolation one abstraction level up."""


# ── the signing key (env-or-ephemeral; private half never leaves) ──────────
@dataclass(frozen=True)
class NotaryKey:
    """A loaded notary keypair. `key_source` is "env" (persistent, from
    NOTARY_KEY_PEM) or "ephemeral" (generated this process — every restart
    reissues an unverifiable history, so verifiers must be able to SEE it).
    The private key is held for signing only; it is `repr=False` and never
    serialized by `key_info`."""
    _private: Ed25519PrivateKey = field(repr=False)
    pubkey_pem: str
    pubkey_fpr: str
    key_source: str
    algo: str = "ed25519"

    def key_info(self) -> dict:
        """The PUBLIC, safe-to-export key description (never the private key)."""
        return {"pubkey_pem": self.pubkey_pem, "pubkey_fpr": self.pubkey_fpr,
                "key_source": self.key_source, "algo": self.algo}


@lru_cache(maxsize=256)
def _fingerprint(pubkey_pem: str) -> str:
    """A short, stable fingerprint of a public key PEM — the trust pin a
    verifier compares against a known notary key (see /v1/notary/key). Memoized
    by PEM string: verify_chain fingerprints the same key once per sequence."""
    return "sha256:" + hashlib.sha256(pubkey_pem.encode()).hexdigest()[:24]


@lru_cache(maxsize=256)
def _load_pub(pubkey_pem: str) -> Ed25519PublicKey:
    """Parse a PEM public key into an Ed25519PublicKey, memoized by PEM string
    (verify_chain parses the same key once, not once per receipt). Raises
    ValueError if the PEM is not an Ed25519 public key."""
    pub = load_pem_public_key(pubkey_pem.encode())
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("not an Ed25519 public key")
    return pub


def _key_from_private(priv: Ed25519PrivateKey, source: str) -> NotaryKey:
    pub_pem = priv.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    return NotaryKey(_private=priv, pubkey_pem=pub_pem,
                     pubkey_fpr=_fingerprint(pub_pem), key_source=source)


_CACHED_KEY: Optional[NotaryKey] = None


def load_notary_key(*, refresh: bool = False) -> NotaryKey:
    """Load the notary signing key: from NOTARY_KEY_PEM (PKCS8 PEM) if set,
    else an ephemeral key generated now (key_source="ephemeral"). Cached per
    process; `refresh=True` re-reads the env (used by tests). A malformed
    NOTARY_KEY_PEM RAISES rather than silently falling back to an ephemeral
    key — a silent swap would invalidate every prior signature unnoticed.

    In a DEPLOYED environment (FLY_APP_NAME or SNHP_REQUIRE_PERSISTENT_KEY set)
    an UNSET NOTARY_KEY_PEM also RAISES — the same policy first_strike applies
    to its trust anchor: an ephemeral per-restart key would make every receipt
    signed before the next restart unverifiable, and the operator might not
    notice. Ephemeral fallback is only for local dev / tests."""
    global _CACHED_KEY
    if _CACHED_KEY is not None and not refresh:
        return _CACHED_KEY
    pem = os.environ.get(_KEY_ENV_VAR, "").strip()
    if pem:
        try:
            priv = load_pem_private_key(pem.encode(), password=None)
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"{_KEY_ENV_VAR} is set but does not parse as a PEM private "
                f"key: {e}. Refusing to fall back to an ephemeral key — that "
                f"would silently swap the notary trust anchor.") from e
        if not isinstance(priv, Ed25519PrivateKey):
            raise RuntimeError(
                f"{_KEY_ENV_VAR} parsed as {type(priv).__name__}, expected "
                f"Ed25519PrivateKey. Re-generate with PKCS8 + Ed25519.")
        _CACHED_KEY = _key_from_private(priv, "env")
    else:
        if os.environ.get("FLY_APP_NAME") or \
                os.environ.get("SNHP_REQUIRE_PERSISTENT_KEY"):
            raise RuntimeError(
                f"{_KEY_ENV_VAR} is unset but the process appears to be "
                f"running in a deployed environment (FLY_APP_NAME or "
                f"SNHP_REQUIRE_PERSISTENT_KEY set). Refusing to fall back to an "
                f"ephemeral key — every notary receipt signed before the next "
                f"restart would become unverifiable. Set {_KEY_ENV_VAR} via "
                f"`fly secrets set`.")
        _CACHED_KEY = _key_from_private(Ed25519PrivateKey.generate(),
                                        "ephemeral")
    return _CACHED_KEY


def generate_key_pem() -> str:
    """Emit a fresh PKCS8 Ed25519 private-key PEM string, for the operator to
    stash in NOTARY_KEY_PEM. Generated on demand — NEVER committed, and the
    caller is responsible for not logging the result."""
    priv = Ed25519PrivateKey.generate()
    return priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8,
                              NoEncryption()).decode()


def _sig_payload(d: dict) -> bytes:
    """The canonical signed bytes of a receipt dict — every field EXCEPT the
    signature itself. The single definition shared by signing, verification,
    and NotaryReceipt.sig_payload(); there is no second inline copy of the
    "drop notary_sig, canon-encode" rule anywhere."""
    return _canon_bytes({k: v for k, v in d.items() if k != "notary_sig"})


def _sign(key: NotaryKey, fields: dict) -> str:
    sig = key._private.sign(_sig_payload(fields))
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── engine version (pins the construction that makes conditions.c true) ────
_ENGINE_VERSION: Optional[str] = None


def engine_version() -> str:
    """The running engine version: $SOURCE_VERSION if set (deployed images
    have no .git), else the short git SHA, else 'unknown'. Memoized — it is
    read twice per receipt and would otherwise shell out to git each time."""
    global _ENGINE_VERSION
    if _ENGINE_VERSION is not None:
        return _ENGINE_VERSION
    env = os.environ.get("SOURCE_VERSION", "").strip()
    if env:
        _ENGINE_VERSION = env[:12]
        return _ENGINE_VERSION
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=os.path.dirname(os.path.abspath(__file__)),
                             capture_output=True, text=True, timeout=5)
        _ENGINE_VERSION = out.stdout.strip() or "unknown"
    except Exception:
        _ENGINE_VERSION = "unknown"
    return _ENGINE_VERSION


# ── the receipt ────────────────────────────────────────────────────────────
_RESERVATION_BASIS = {"finite_stock": "report_independent(state)",
                      "capacity": "attested(ô)",
                      "ledger": "n/a(ledger)"}
_ECON_FIELDS = ("list_price", "quoted_price", "saving", "c_eff",
                "excess_rent", "buffer", "a_prime_ok")
_CF_KEYS = {"sticker_world_total", "snhp_world_total", "delta"}


@dataclass(frozen=True)
class NotaryReceipt:
    """A signed, replayable receipt. Two shapes share one signed envelope:

      • a PER-QUOTE receipt (regime "finite_stock" | "capacity") notarizes one
        `core.engine.Quote` — the economic fields are all present and internally
        consistent. `over-list is unconstructible`: __post_init__ RAISES
        NotaryViolation if quoted_price > list_price, if conditions.a is not
        True, or if `saving`/`excess_rent` disagree with the STORED rounded
        components (ℓ−p, ℓ−c_eff) beyond 1e-9. Any OTHER condition may be False
        and the receipt is still valid — it attests exactly what held.

      • a LEDGER receipt (regime "ledger") notarizes an aggregate counterfactual
        (a day/period total), NOT a single quote. The per-quote economic fields
        are honestly null and conditions a/a_prime/b/d are None (not attested);
        only c (engine version) is attested True. No shell Quote is fabricated.

    Chaining: `prev_hash` is the canon_hash of the previous receipt in the same
    chain (None for a standalone receipt or a chain-segment head). `chain_id`
    labels the segment — a None prev_hash is legal mid-log iff chain_id differs
    from the previous receipt's (a season/experiment rollover). Because chain_id
    is inside the signed payload, forging a mid-chain reset requires re-signing.
    `digest()` is this receipt's own hash — the next receipt's prev_hash.
    """
    protocol: str
    quote_ref: str
    venue_id: str
    ts: str
    list_price: Optional[float]          # ℓ  (None on a ledger receipt)
    quoted_price: Optional[float]        # p
    saving: Optional[float]              # ℓ − p
    c_eff: Optional[float]               # the seller reservation cost (floor)
    excess_rent: Optional[float]         # ℓ − c_eff
    buffer: Optional[float]              # β
    a_prime_ok: Optional[bool]           # ℓ − c_eff ≤ 2β
    regime: str                # "finite_stock" | "capacity" | "ledger"
    reservation_basis: str     # report_independent(state)|attested(ô)|n/a(ledger)
    conditions: dict           # {a, a_prime, b, c, d: Optional[bool]}
    context_hash: str
    disclosure_digest: str     # digest ONLY — never raw WTP/utilities
    engine_version: str
    key_source: str            # "env" | "ephemeral" (signer transparency)
    pubkey_fpr: str
    counterfactual: Optional[dict]   # {sticker_world_total, snhp_world_total, delta}
    prev_hash: Optional[str]
    notary_sig: str
    chain_id: Optional[str] = None     # chain-segment label (season/experiment)
    pubkey_pem: Optional[str] = None   # embedded convenience; trust pins on fpr

    def __post_init__(self) -> None:
        if self.regime == "ledger":
            # a ledger receipt attests the counterfactual + the chain, not
            # per-quote economics; the economic fields are honestly null.
            return
        # per-quote receipt: the economic fields are MANDATORY and consistent
        missing = [n for n in _ECON_FIELDS if getattr(self, n) is None]
        if missing:
            raise NotaryViolation(
                f"a per-quote receipt (regime {self.regime!r}) must carry every "
                f"economic field; missing: {missing}")
        if self.quoted_price > self.list_price + _TOL:
            raise NotaryViolation(
                f"over-list is unconstructible: quoted {self.quoted_price} > "
                f"list {self.list_price}")
        if self.conditions.get("a") is not True:
            raise NotaryViolation(
                "conditions.a (discount-only) is not True but a receipt exists "
                "— an over-list quote can never be notarized")
        # saving/excess_rent are DERIVED from the stored rounded components, so
        # they must match a re-derivation exactly (within 1e-9), never drift.
        if abs(self.saving - round(self.list_price - self.quoted_price, 4)) > _TOL:
            raise NotaryViolation(
                f"saving {self.saving} != round(ℓ−p, 4) "
                f"({round(self.list_price - self.quoted_price, 4)})")
        if abs(self.excess_rent - round(self.list_price - self.c_eff, 6)) > _TOL:
            raise NotaryViolation(
                f"excess_rent {self.excess_rent} != round(ℓ−c_eff, 6) "
                f"({round(self.list_price - self.c_eff, 6)})")

    def to_dict(self) -> dict:
        """The receipt as a plain dict, assembled straight from the dataclass
        fields (no recursive dataclasses.asdict pass). digest()/signing/verify
        all consume this one mapping."""
        return {f.name: getattr(self, f.name) for f in _dc_fields(self)}

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), **kw)

    def sig_payload(self) -> bytes:
        """The canonical signed bytes — delegates to the module `_sig_payload`
        so there is exactly one definition of what is signed."""
        return _sig_payload(self.to_dict())

    def digest(self) -> str:
        """canon_hash of the whole receipt (signature included) — the value a
        following receipt puts in its `prev_hash`."""
        return canon_hash(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "NotaryReceipt":
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "NotaryReceipt":
        return cls.from_dict(json.loads(s))


# ── emit ───────────────────────────────────────────────────────────────────
def _buyer_disclosure(quote: Quote) -> dict:
    """A disclosure fingerprint derived from the quote's report-free audit
    primitives (realized value, outside surplus, defer, credit) — never the
    per-option WTP. Used when the caller does not pass a richer disclosure."""
    a = quote.audit or {}
    return {"value": round(float(a.get("val", quote.value)), 4),
            "outside": round(float(a.get("s_out", 0.0)), 4),
            "defer": round(float(a.get("defer", 0.0)), 4)}


def emit_receipt(quote: Quote, *, state, opts: QuoteOpts,
                 quote_ref: str, venue_id: str, regime: str,
                 prev_hash: Optional[str] = None,
                 chain_id: Optional[str] = None,
                 counterfactual: Optional[dict] = None,
                 disclosure=None, attested: bool = False,
                 key: Optional[NotaryKey] = None,
                 ts: Optional[str] = None,
                 embed_pubkey: bool = False) -> NotaryReceipt:
    """Notarize a `core.engine.Quote` into a signed per-quote NotaryReceipt.

    Gate (ii) of discount-only lives here: this RAISES NotaryViolation if the
    quote prices above list, BEFORE constructing the receipt (which would raise
    too — belt and braces). Every economic field is read from the engine call;
    nothing is invented. `regime` comes from `regime_probe` (or a cached probe);
    it sets conditions.b and reservation_basis. `attested` sets conditions.d —
    v1 has no attestation, so callers pass False and d is False, honestly.

    ROUNDING: the stored components are rounded FIRST (list_price=round(ℓ,4),
    quoted_price=round(p,4), c_eff=round(c_eff,6)), then the DERIVED fields are
    computed from those rounded values (saving=round(list_price−quoted_price,4),
    excess_rent=round(list_price−c_eff,6), a_prime_ok from that excess_rent). A
    verifier re-derives from the SAME stored fields, so an honest receipt always
    verifies and __post_init__ never spuriously rejects a legitimate emit.

    `context_hash` covers exactly: the shop STATE the cost model reads
    (_state_digest), the engine CONFIG, the rounded LIST and QUOTED prices, the
    REGIME, the DISCLOSURE digest, and the ENGINE version — nothing else. The
    menu/graph is deliberately NOT hashed here (that would silently change what
    the receipt binds); an API layer that wants to bind the menu carries its own
    spec digest into `disclosure`/`quote_ref`.

    `disclosure` may be a precomputed digest string, a {"utilities","walk"}
    dict, or None (a report-free fingerprint of the quote's audit is used).
    `counterfactual`, when given, must be {sticker_world_total, snhp_world_total,
    delta}; use emit_ledger_receipt for an aggregate (no quote) instead.
    """
    if regime not in ("finite_stock", "capacity"):
        raise ValueError(
            f"unknown per-quote regime {regime!r} — one of "
            "'finite_stock', 'capacity' (use emit_ledger_receipt for 'ledger')")
    ell, p, c_eff = float(quote.listv), float(quote.price), float(quote.cost)
    if p > ell + _TOL:                      # gate (ii): re-check at emit
        raise NotaryViolation(
            f"refusing to notarize an over-list quote: p={p} > ℓ={ell}")

    # round the STORED components first, then derive from the rounded values
    list_price = round(ell, 4)
    quoted_price = round(p, 4)
    c_eff_r = round(c_eff, 6)
    saving = round(list_price - quoted_price, 4)
    excess_rent = round(list_price - c_eff_r, 6)
    beta = round(max(opts.min_gain_abs, opts.min_gain_frac * ell), 6)
    a_prime_ok = excess_rent <= 2.0 * beta + _TOL
    conditions = {"a": quoted_price <= list_price + _TOL, "a_prime": a_prime_ok,
                  "b": regime == "finite_stock", "c": True, "d": bool(attested)}

    if isinstance(disclosure, str):
        disc = disclosure
    elif isinstance(disclosure, dict):
        disc = disclosure_digest(disclosure.get("utilities", {}),
                                 disclosure.get("walk", 0.0))
    else:
        disc = disclosure_digest(_buyer_disclosure(quote), 0.0)

    if counterfactual is not None and set(counterfactual) != _CF_KEYS:
        raise ValueError(f"counterfactual must have keys {sorted(_CF_KEYS)}")

    key = key or load_notary_key()
    context_hash = canon_hash({
        "state": _state_digest(state),
        "config": _json_config(quote.config),
        "list": list_price, "quoted": quoted_price,
        "regime": regime, "disclosure": disc,
        "engine": engine_version(),
    })

    fields = dict(
        protocol=PROTOCOL, quote_ref=quote_ref, venue_id=venue_id,
        ts=ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        list_price=list_price, quoted_price=quoted_price,
        saving=saving, c_eff=c_eff_r,
        excess_rent=excess_rent, buffer=beta,
        a_prime_ok=a_prime_ok, regime=regime,
        reservation_basis=_RESERVATION_BASIS[regime], conditions=conditions,
        context_hash=context_hash, disclosure_digest=disc,
        engine_version=engine_version(), key_source=key.key_source,
        pubkey_fpr=key.pubkey_fpr, counterfactual=counterfactual,
        prev_hash=prev_hash, chain_id=chain_id,
        pubkey_pem=key.pubkey_pem if embed_pubkey else None,
    )
    sig = _sign(key, fields)                 # sign every field except the sig
    return NotaryReceipt(**fields, notary_sig=sig)


def emit_ledger_receipt(counterfactual: dict, *, quote_ref: str, venue_id: str,
                        prev_hash: Optional[str] = None,
                        chain_id: Optional[str] = None,
                        key: Optional[NotaryKey] = None,
                        embed_pubkey: bool = False,
                        state=None, disclosure=None,
                        ts: Optional[str] = None) -> NotaryReceipt:
    """Notarize an aggregate LEDGER counterfactual — a day/period total, not a
    single quote. NO shell Quote is fabricated: the per-quote economic fields
    are honestly null, regime is "ledger" (reservation_basis "n/a(ledger)"), and
    conditions a/a_prime/b/d are None (not attested for an aggregate); only c
    (engine version) stays attested True. The load-bearing payload is
    `counterfactual` (required: {sticker_world_total, snhp_world_total, delta})
    plus the prev_hash/chain_id chain.

    `state`/`disclosure`/`ts` extend the finding-5 signature so a deterministic
    caller (block/live.py) can bind a logical stamp and a per-period context
    into the signed hash; all optional. context_hash covers the state digest,
    the counterfactual, the disclosure digest, and the engine version.
    """
    if not isinstance(counterfactual, dict) or set(counterfactual) != _CF_KEYS:
        raise ValueError(
            f"a ledger receipt requires counterfactual keys {sorted(_CF_KEYS)}")

    if isinstance(disclosure, str):
        disc = disclosure
    elif isinstance(disclosure, dict):
        disc = disclosure_digest(disclosure.get("utilities", {}),
                                 disclosure.get("walk", 0.0))
    else:
        disc = canon_hash({"ledger": quote_ref})

    key = key or load_notary_key()
    context_hash = canon_hash({
        "state": _state_digest(state),
        "counterfactual": counterfactual,
        "regime": "ledger", "disclosure": disc,
        "engine": engine_version(),
    })
    conditions = {"a": None, "a_prime": None, "b": None, "c": True, "d": None}

    fields = dict(
        protocol=PROTOCOL, quote_ref=quote_ref, venue_id=venue_id,
        ts=ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        list_price=None, quoted_price=None, saving=None, c_eff=None,
        excess_rent=None, buffer=None, a_prime_ok=None,
        regime="ledger", reservation_basis=_RESERVATION_BASIS["ledger"],
        conditions=conditions, context_hash=context_hash,
        disclosure_digest=disc, engine_version=engine_version(),
        key_source=key.key_source, pubkey_fpr=key.pubkey_fpr,
        counterfactual=counterfactual, prev_hash=prev_hash, chain_id=chain_id,
        pubkey_pem=key.pubkey_pem if embed_pubkey else None,
    )
    sig = _sign(key, fields)
    return NotaryReceipt(**fields, notary_sig=sig)


def _json_config(cfg) -> Optional[dict]:
    """JSON-safe config (frozensets → sorted lists) so the context hash is
    stable across the (frozenset) engine representation and any JSON round-trip."""
    if cfg is None:
        return None
    return {k: (sorted(v) if isinstance(v, (frozenset, set)) else v)
            for k, v in cfg.items()}


def _state_digest(state) -> str:
    """A canonical digest of the shop-side context the cost model reads — the
    part of the world a price may lawfully depend on. Never buyer-specific."""
    return canon_hash({
        "tick": getattr(state, "tick", 0),
        "inventory": {k: round(float(v), 6)
                      for k, v in sorted(getattr(state, "inventory", {}).items())},
        "capacity": {str(k): round(float(v), 6)
                     for k, v in sorted(getattr(state, "capacity", {}).items())},
        "expiring": sorted(getattr(state, "expiring", set())),
        "expected_demand": {k: round(float(v), 6) for k, v in
                            sorted(getattr(state, "expected_demand", {}).items())},
    })


# ── regime probe (the (b)-test) ────────────────────────────────────────────
def _scaled_outside_buyer(buyer, k: float):
    """A shallow clone of `buyer` with its outside surplus scaled by k, all
    else fixed. Works for core.engine.SeparableBuyer (an `outside` attribute);
    for other Buyer implementations it wraps `outside_surplus`."""
    import copy
    b = copy.copy(buyer)
    if hasattr(b, "outside"):
        try:
            b.outside = float(getattr(buyer, "outside", 0.0)) * k
            return b
        except Exception:
            pass
    base = buyer.outside_surplus()

    class _Scaled:
        qty_decay = getattr(buyer, "qty_decay", 0.15)
        def value(self, g, c): return buyer.value(g, c)
        def outside_surplus(self): return base * k
        def balk_prob(self, s): return buyer.balk_prob(s)
        def defer_cost(self, slot): return buyer.defer_cost(slot)
    return _Scaled()


def _pin_quantity(graph, config):
    """The probe holds the ORDER fixed and varies only the report, so any
    movement in the reservation is attributable to the report — never to the
    buyer re-sizing their cart. This pins the QUANTITY dim (to the caller's
    value, else 1) on top of the caller's config; c_eff is a TOTAL that scales
    with qty, so leaving qty free would let a report-driven qty change masquerade
    as a moving reservation. FULFILLMENT is deliberately left OPEN — the capacity
    channel must be free to express, since that is exactly the (b)-test."""
    out = dict(config or {})
    for d in graph.dims:
        if d.kind == DimKind.QUANTITY and d.id not in out:
            out[d.id] = 1
    return out


def regime_probe(graph, state, buyer, config=None, *,
                 opts: Optional[QuoteOpts] = None,
                 scales: tuple = (0.0, 1.0, 3.0)) -> tuple[str, dict]:
    """The (b)-test. Quote the SAME (graph, state, order) with the buyer's
    claimed outside option scaled (default 0×, 1×, 3×), all else fixed, and
    watch the SELLER RESERVATION on the realized deal — the PER-UNIT floor:

        reservation = (c_eff(realized config) − capacity_relief credit) / qty

    This is the seller's own opportunity cost of the transacted unit — the
    reservation, NOT the Nash price. It is read from the engine's report-free
    audit primitives (`audit["cost"]` − `audit["credit"]`), normalized per unit.
    The order (quantity) is pinned (see _pin_quantity) so only the report moves;
    fulfillment is left open so the capacity channel can express.

      • FINITE-STOCK venue — the reservation is a pure property of the seller's
        inventory/stock position (const/salvage/scarcity cost); no capacity-
        relief channel exists, so scaling the buyer's report cannot move it.
        Invariant ⇒ regime "finite_stock" (condition b True), report-independent.

      • CAPACITY venue — the realized credit depends on the buyer accepting a
        DEFERRED slot, which depends on their outside option; as the report
        scales up the buyer stops deferring and the credit vanishes, so the
        reservation MOVES. ⇒ regime "capacity" (condition b False). Such venues
        are NOT trustless: the private-value leak survives even attestation of
        the outside option, so the receipt reports b=false rather than papering
        over it.

    Returns (regime, evidence). Evidence carries the per-scale reservation and
    realized price so the verdict is auditable.
    """
    opts = opts or QuoteOpts()
    probe_config = _pin_quantity(graph, config)
    per_scale = []
    for k in scales:
        b = _scaled_outside_buyer(buyer, k)
        q = _engine_quote(graph, state, b, config=probe_config, opts=opts)
        if q is None:
            per_scale.append({"scale": k, "reservation": None, "price": None,
                              "feasible": None})
        else:
            a = q.audit or {}
            qty = max(1, qty_of(graph, q.config))
            res = (float(a.get("cost", q.cost)) - float(a.get("credit", 0.0))) / qty
            per_scale.append({"scale": k, "reservation": round(res, 6),
                              "price": round(float(q.price), 4),
                              "feasible": bool(q.feasible)})

    # Classify by MOVEMENT AMONG PRESENT reservations only. Claiming
    # finite_stock (report-independence) requires POSITIVE evidence of
    # invariance: ≥2 present scales spanning the base (1×) AND a stressed scale,
    # with no spread. A walk at some scale is NOT movement — it is missing data;
    # too few present scales is "insufficient_probe" and stays conservatively
    # 'capacity' (never claim report-independence without the evidence).
    present = [(r["scale"], r["reservation"]) for r in per_scale
               if r["reservation"] is not None]
    res_vals = [v for _, v in present]
    present_scales = {k for k, _ in present}
    spread = (max(res_vals) - min(res_vals)) if res_vals else None
    has_base = any(abs(k - 1.0) <= 1e-12 for k in present_scales)
    has_stressed = any(abs(k - 1.0) > 1e-12 for k in present_scales)
    enough = len(present) >= 2 and has_base and has_stressed
    moved = bool(enough and spread is not None and spread > 1e-6)
    insufficient = not enough
    regime = "finite_stock" if (enough and not moved) else "capacity"
    evidence = {"signal": "c_eff − capacity_credit on the realized deal",
                "scales": list(scales), "probes": per_scale,
                "reservation_moved": moved,
                "insufficient_probe": insufficient,
                "spread": round(spread, 6) if spread is not None else None}
    return regime, evidence


def spec_probe_buyer(graph, *, outside_frac: float = 0.5) -> SeparableBuyer:
    """A synthetic, SPEC-DERIVED probe buyer for the (b)-test — independent of
    any real caller's valuations. Per-good values are the option LIST prices
    (price_delta), so the buyer would transact every good; the outside option is
    a fraction of the max single-good list total. Deriving the stress buyer from
    the SPEC makes the regime a pure property of (spec, state): two different
    real buyers get the SAME regime on the same spec/state, which is what the
    cache assumes."""
    values: dict = {}
    max_list = 0.0
    for d in graph.dims:
        if d.kind in (DimKind.CHOICE, DimKind.ADDON, DimKind.PREFERENCE):
            for o in d.options:
                values[(d.id, o.id)] = float(o.price_delta)
                max_list = max(max_list, float(o.price_delta))
    return SeparableBuyer(values=values, outside=outside_frac * max_list,
                          balk=0.0)


# ── verify (standalone, on receipt JSON) ───────────────────────────────────
def _as_dict(receipt) -> dict:
    if isinstance(receipt, NotaryReceipt):
        return receipt.to_dict()
    if isinstance(receipt, str):
        return json.loads(receipt)
    return dict(receipt)


def verify_receipt(receipt, *, pubkey_pem: Optional[str] = None) -> dict:
    """Verify ONE receipt STANDALONE from its JSON/dict. Recomputes the
    canonical signed bytes and checks the Ed25519 signature against the public
    key (explicit `pubkey_pem` > receipt-embedded pubkey_pem > the process's
    ambient notary key). For a PER-QUOTE receipt it also re-checks discount-only
    (p ≤ ℓ), re-derives saving/excess_rent/a_prime_ok from the receipt's own
    STORED rounded numbers, and cross-checks reservation_basis and conditions
    against the canonical mapping. For a LEDGER receipt the null economic fields
    are skipped and only the signature, fingerprint, reservation_basis, and
    counterfactual PRESENCE are checked. Returns {ok, checks, reasons,
    pubkey_fpr, ...}. Never needs the private key."""
    d = _as_dict(receipt)
    checks: dict = {}
    reasons: list[str] = []

    pem = pubkey_pem or d.get("pubkey_pem")
    if pem is None:
        pem = load_notary_key().pubkey_pem
    # trust pin: the key we verify with must match the fingerprint on the receipt
    fpr_ok = _fingerprint(pem) == d.get("pubkey_fpr")
    checks["pubkey_fpr"] = fpr_ok
    if not fpr_ok:
        reasons.append("pubkey fingerprint does not match the receipt's pubkey_fpr")

    try:
        pub = _load_pub(pem)
        pub.verify(_b64d(d["notary_sig"]), _sig_payload(d))
        checks["signature"] = True
    except (InvalidSignature, KeyError, ValueError, TypeError) as e:
        checks["signature"] = False
        reasons.append(f"signature invalid: {type(e).__name__}")

    # reservation_basis must be the canonical mapping for the regime (all regimes)
    rb_ok = d.get("reservation_basis") == _RESERVATION_BASIS.get(d.get("regime"))
    checks["reservation_basis"] = rb_ok
    if not rb_ok:
        reasons.append("reservation_basis is not the canonical mapping for regime")

    is_ledger = d.get("regime") == "ledger"
    if is_ledger:
        # aggregate receipt: no per-quote economics, but the counterfactual is
        # the load-bearing payload — it must be present and well-formed.
        cf = d.get("counterfactual")
        cf_ok = isinstance(cf, dict) and set(cf) == _CF_KEYS
        checks["counterfactual"] = cf_ok
        if not cf_ok:
            reasons.append("ledger receipt missing/malformed counterfactual")
    else:
        # gate (iii): discount-only re-check on replay
        disc_ok = float(d["quoted_price"]) <= float(d["list_price"]) + _TOL
        checks["discount_only"] = disc_ok
        if not disc_ok:
            reasons.append("quoted_price exceeds list_price (over-list)")

        # saving is DERIVED from the stored rounded components — re-derive exactly
        save_ok = abs(float(d["saving"]) - round(
            float(d["list_price"]) - float(d["quoted_price"]), 4)) <= _TOL
        checks["saving"] = save_ok
        if not save_ok:
            reasons.append("saving != round(list_price − quoted_price, 4)")

        # excess_rent re-derived from the stored rounded list_price / c_eff
        rent_ok = abs(float(d["excess_rent"]) - round(
            float(d["list_price"]) - float(d["c_eff"]), 6)) <= _TOL
        checks["excess_rent"] = rent_ok
        if not rent_ok:
            reasons.append("excess_rent != round(list_price − c_eff, 6)")

        # a_prime_ok re-derived from the STORED excess_rent and buffer
        ap = float(d["excess_rent"]) <= 2.0 * float(d["buffer"]) + _TOL
        ap_ok = (ap == bool(d["a_prime_ok"]))
        checks["a_prime_ok"] = ap_ok
        if not ap_ok:
            reasons.append("a_prime_ok disagrees with (excess_rent ≤ 2β)")

        cond = d.get("conditions", {})
        # conditions.a must equal the discount-only re-check
        cond_a = cond.get("a") is True
        checks["condition_a"] = cond_a and disc_ok
        if not cond_a:
            reasons.append("conditions.a (discount-only) is not True")
        # conditions.a_prime must equal a_prime_ok (when the receipt records it)
        if cond.get("a_prime") is not None:
            cap_ok = (bool(cond.get("a_prime")) == bool(d["a_prime_ok"]))
            checks["condition_a_prime"] = cap_ok
            if not cap_ok:
                reasons.append("conditions.a_prime disagrees with a_prime_ok")

    ok = all(checks.values())
    return {"ok": ok, "checks": checks, "reasons": reasons,
            "pubkey_fpr": d.get("pubkey_fpr"),
            "quote_ref": d.get("quote_ref"),
            "key_source": d.get("key_source")}


def verify_chain(receipts, *, pubkey_pem: Optional[str] = None) -> dict:
    """Verify a SEQUENCE of receipts: each individually, plus the prev_hash
    chain. Within one chain_id segment, receipt[i].prev_hash must equal
    canon_hash(receipt[i-1]). A NULL prev_hash mid-sequence is legal ONLY at a
    segment boundary — where chain_id differs from the previous receipt's (a
    season/experiment rollover). This lets an honest multi-season log verify
    end-to-end while a tampered mid-segment reset (prev_hash nulled, same
    chain_id) still FAILS; chain_id being inside the signed payload means the
    reset can't be forged without re-signing. Returns {ok, chain_ok, results,
    breaks}."""
    ds = [_as_dict(r) for r in receipts]
    results = [verify_receipt(r, pubkey_pem=pubkey_pem) for r in ds]
    breaks: list[str] = []
    chain_ok = True
    for i in range(1, len(ds)):
        got = ds[i].get("prev_hash")
        same_chain = ds[i].get("chain_id") == ds[i - 1].get("chain_id")
        if same_chain:
            expected = canon_hash(ds[i - 1])
            if got != expected:
                chain_ok = False
                breaks.append(
                    f"receipt[{i}].prev_hash != canon_hash(receipt[{i-1}]) "
                    f"within chain_id {ds[i].get('chain_id')!r}")
        else:
            # a segment boundary: the only legal shape is a fresh head (null)
            if got is not None:
                chain_ok = False
                breaks.append(
                    f"receipt[{i}] crosses a chain_id boundary "
                    f"({ds[i-1].get('chain_id')!r} -> {ds[i].get('chain_id')!r}) "
                    "but prev_hash is not null")
    ok = chain_ok and all(r["ok"] for r in results)
    return {"ok": ok, "chain_ok": chain_ok, "n": len(ds),
            "results": results, "breaks": breaks}


# ── CLI: python -m core.notary verify <receipts.jsonl> ─────────────────────
def _read_jsonl(path: str) -> list[dict]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # a block day-record wraps the receipt under "attestation"
            if isinstance(rec, dict) and "attestation" in rec \
                    and isinstance(rec["attestation"], dict) \
                    and "notary_sig" in rec["attestation"]:
                rec = rec["attestation"]
            out.append(rec)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m core.notary",
        description="verify SNHP notary receipts (standalone, from JSON)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="verify a JSONL of receipts + the chain")
    v.add_argument("receipts", help="path to a .jsonl of receipts (or day-records)")
    v.add_argument("--pubkey", default=None,
                   help="PEM file of the notary public key (else embedded/ambient)")
    g = sub.add_parser("keygen", help="print a fresh PKCS8 Ed25519 private PEM")
    args = ap.parse_args(argv)

    if args.cmd == "keygen":
        sys.stdout.write(generate_key_pem())
        return 0

    pem = None
    if args.pubkey:
        with open(args.pubkey) as f:
            pem = f.read()
    receipts = _read_jsonl(args.receipts)
    if not receipts:
        print("no receipts found", file=sys.stderr)
        return 2
    res = verify_chain(receipts, pubkey_pem=pem)
    for i, r in enumerate(res["results"]):
        tag = "OK  " if r["ok"] else "FAIL"
        extra = "" if r["ok"] else "  <- " + "; ".join(r["reasons"])
        print(f"[{tag}] receipt[{i}] {r.get('quote_ref')} "
              f"(key={r.get('key_source')}){extra}")
    print(f"chain: {'OK' if res['chain_ok'] else 'FAIL'}"
          + ("" if res["chain_ok"] else "  <- " + "; ".join(res["breaks"])))
    print(f"overall: {'OK' if res['ok'] else 'FAIL'} "
          f"({res['n']} receipts)")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

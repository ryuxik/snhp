"""snhp-notary/settlement-1 — the divorce decree's receipt (SPEC.md §6).

A sibling protocol on core/notary.py's DNA (same Ed25519 key, same canonical
hashing, same sign/verify pattern) — NOT a stretch of the quote or ledger
receipt shapes, which hard-require shop semantics.

WHAT A SETTLEMENT RECEIPT ATTESTS (exactly this, and nothing more):
  1. The settlement is the mediator's margin-optimal point within the
     ELICITED bounds — replayable: same two input digests + same engine
     version + same context ⇒ same settlement.
  2. IR: both sides' final elicited margins are >= 0, and both sides
     RATIFIED the draft (the second-signature beat).
  3. The mediator's inputs were exactly two one-way input digests — neither
     side's numbers appear in, or are recoverable from, the receipt.
  4. Envy-free under each side's own ELICITED valuations: YES/NO — a
     reported per-episode check, never a mechanism guarantee.
It does NOT attest that the elicited mandate reflects true feelings, or that
the outcome is fair.

The Showdown Flip (SPEC.md §6): `seal_persona` is the t0 commitment helper —
the hash of a side's TRUE table, computed before any question is asked. The
receipt carries both seal hashes as opaque commitments; at the flip, the
audience recomputes them from the revealed tables. The notary never sees the
raw tables.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.notary import (NotaryKey, _b64d, _canon_bytes, _load_pub,
                         _sig_payload, _sign, canon_hash, engine_version,
                         load_notary_key)
from divorce.personas import ASSET_NAMES, Persona

PROTOCOL = "snhp-notary/settlement-1"


def seal_payload(p: Persona) -> str:
    """The exact canonical-JSON string the seal hashes — published at the
    flip so ANYONE (including the demo page, via WebCrypto sha256) can verify
    the t0 commitment against the revealed numbers."""
    return _canon_bytes({"values": {a: round(p.values[a], 2) for a in ASSET_NAMES},
                         "walk": round(p.walk_away, 2),
                         "lam": round(p.lam, 4)}).decode()


def seal_persona(p: Persona) -> str:
    """The t0 commitment: one-way hash of a side's TRUE valuation table +
    walk-away. Computed harness/demo-side before elicitation begins; the flip
    at settlement re-derives it from the revealed numbers."""
    import hashlib
    return "sha256:" + hashlib.sha256(seal_payload(p).encode()).hexdigest()


def input_digest(trace: list[dict], stated: dict, ratifications: list[bool]) -> str:
    """One-way digest of EVERYTHING the mediator consumed from one side: the
    Q&A trace (answers = self-selecting choices), the structured declarations
    (lam, fight_cost), and the ratification responses. Same inputs ⇒ same
    digest ⇒ (with the engine version) same settlement — replay is the proof
    that nobody peeked."""
    return canon_hash({"trace": trace,
                       "lam": round(float(stated["lam"]), 4),
                       "fight_cost": round(float(stated["fight_cost"]), 2),
                       "optimism": round(float(stated.get("optimism", 0.0)), 4),
                       "ratify": list(ratifications)})


def _ef_elicited(v_hat: dict[str, float], shares_mine: dict[str, float]) -> bool:
    """EF under this side's own ELICITED valuations, spite excluded: do I
    value my pile at least as much as I value theirs? (SPEC.md §6.4)"""
    mine = sum(s * v_hat[a] for a, s in shares_mine.items())
    theirs = sum((1.0 - s) * v_hat[a] for a, s in shares_mine.items())
    return bool(mine >= theirs)


def build_settlement_receipt(med: dict, stated_a: dict, stated_b: dict,
                             seal_a: str, seal_b: str, *,
                             context: dict,
                             key: NotaryKey | None = None) -> dict:
    """Sign a settlement receipt from a SETTLED mediate() result.

    `med` is elicit.mediate()'s return (proposal, traces, drafts, v_hat_*).
    `context` pins the replay parameters (prior cal seed, q budget,
    drafts_max, pair seed) — replay = rerun mediate with these + the raw
    transcripts and compare the proposal. Raises ValueError on an unsettled
    result: NO DECREE gets no receipt — an honest absence, not a sad one.
    """
    proposal = med.get("proposal")
    if proposal is None:
        raise ValueError("no decree: an abstained mediation gets no receipt")
    drafts = med.get("drafts", [])
    if not (drafts and drafts[-1]["ok_a"] and drafts[-1]["ok_b"]):
        raise ValueError("unratified: both signatures are required")
    key = key or load_notary_key()

    shares_a = {a: round(float(s), 4) for a, s in proposal.items()}
    shares_b = {a: round(1.0 - float(s), 4) for a, s in proposal.items()}
    fields = {
        "protocol": PROTOCOL,
        "engine_version": engine_version(),
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settlement": {"shares_a": shares_a},
        "inputs": {
            "digest_a": input_digest(med["trace_a"], stated_a,
                                     [d["ok_a"] for d in drafts]),
            "digest_b": input_digest(med["trace_b"], stated_b,
                                     [d["ok_b"] for d in drafts]),
            "n_questions": int(med["n_questions"]),
            "n_drafts": len(drafts),
        },
        "seals": {"a": seal_a, "b": seal_b,
                  "note": "t0 commitments to each side's TRUE table; verify "
                          "at the flip by recomputing from revealed numbers"},
        "checks": {
            "ratified_a": True, "ratified_b": True,
            "envy_free_elicited_a": _ef_elicited(med["v_hat_a"], shares_a),
            "envy_free_elicited_b": _ef_elicited(med["v_hat_b"], shares_b),
        },
        "context": dict(context),
        "attests": ("Settlement is the margin-optimal point within both "
                    "parties' elicited bounds; both parties ratified above "
                    "their declared walk-away basis; computed from two "
                    "one-way input digests — verify by replay; envy-free "
                    "under each side's own elicited valuations as reported "
                    "in checks. Nothing else is attested."),
        "notary": {"pubkey_fpr": key.pubkey_fpr, "key_source": key.key_source,
                   "pubkey_pem": key.pubkey_pem},
    }
    fields["notary_sig"] = _sign(key, fields)
    return fields


def verify_settlement_receipt(receipt: dict, *,
                              pubkey_pem: str | None = None) -> dict:
    """Standalone verification, mirroring core.notary.verify_receipt's
    contract: signature over the canonical payload + shape invariants.
    `pubkey_pem` pins a trusted key (e.g. from GET /v1/notary/key); omitted,
    the receipt's embedded key is used (proves integrity, not identity).
    Returns {"ok": bool, "problems": [...]}."""
    problems = []
    if receipt.get("protocol") != PROTOCOL:
        problems.append(f"protocol is {receipt.get('protocol')!r}, "
                        f"expected {PROTOCOL!r}")
    for k in ("settlement", "inputs", "seals", "checks", "notary",
              "notary_sig", "attests", "engine_version"):
        if k not in receipt:
            problems.append(f"missing field {k!r}")
    if not problems:
        shares = receipt["settlement"]["shares_a"]
        bad = [a for a, s in shares.items()
               if not (-1e-9 <= float(s) <= 1.0 + 1e-9)]
        if bad:
            problems.append(f"shares out of [0,1]: {bad}")
        if not (receipt["checks"].get("ratified_a")
                and receipt["checks"].get("ratified_b")):
            problems.append("receipt exists without both ratifications")
        pem = pubkey_pem or receipt["notary"]["pubkey_pem"]
        try:
            _load_pub(pem).verify(_b64d(receipt["notary_sig"]),
                                  _sig_payload(receipt))
        except Exception:  # noqa: BLE001 — any failure = invalid signature
            problems.append("signature does not verify")
    return {"ok": not problems, "problems": problems}

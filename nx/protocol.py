"""SNHP-NX/1 reference implementation — the NX session state machine + message
dataclasses, enforcing invariants I1–I4 STRUCTURALLY (SPEC.md §4).

NX mounts a bundle-capable negotiation between a checkout-shaped host protocol's
cart/RFQ step and its payment-intent step. This module is the message layer and
the session lifecycle ONLY: like MPX (`meridian/protocol.py`), it moves no money
and holds no goods — the host settles the agreed package. It is stdlib-only (no
numpy, no cryptography): the receipt hook (I4) exposes a canonical transcript
hash any attestor can sign; `nx/bridge.py` wires the SNHP notary as the worked
example.

The four invariants are enforced so that an offending message is UNCONSTRUCTIBLE,
mirroring the notary's "over-list is unconstructible" (`core/notary.py`):

  I1 NEVER-ABOVE-LIST   — `Line(price > list_price)` RAISES at construction; a
                          proposal naming a config absent from the seller's quote
                          schedule, or restating a line's list_price, is rejected
                          by the session. The seller's NX-QUOTE is the sole list
                          authority; a buyer cannot manufacture headroom.
  I2 BOUNDED            — `max_rounds` is fixed at session creation; the Nth+1
                          NX-PROPOSE RAISES.
  I3 PACKAGE-ATOMICITY  — proposals are whole Packages; `accept()` takes no
                          package and ratifies the standing package VERBATIM, so
                          acceptance can never smuggle in new terms.
  I4 RECEIPT-HOOK       — a SETTLED session exposes `transcript_hash()`
                          (sha256 over canonical JSON of the ordered messages)
                          and an optional signed `attestation` field.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field, fields as _dc_fields
from typing import Optional

PROTOCOL = "snhp-nx/1"
_TOL = 1e-6
_PRICE_DP = 6  # prices are rounded to this many dp at construction (hash-stable)


# ── errors (two kinds, like meridian) ──────────────────────────────────────
class NXViolation(ValueError):
    """An NX invariant was violated at CONSTRUCTION — the message/line is
    unconstructible (e.g. an above-list line, I1). Mirrors NotaryViolation."""


class NXProtocolError(RuntimeError):
    """An illegal NX state transition (a caller tried to break the message flow
    or the round bound, I2). Mirrors meridian's ProtocolError."""


# ── canonical hashing (same spirit as core.notary.canon_hash) ──────────────
def _canon_bytes(obj) -> bytes:
    """Deterministic canonical-JSON encoding: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def canon_hash(obj) -> str:
    """Canonical-JSON sha256 of `obj`, prefixed `sha256:` so the hash algorithm
    is self-describing on the wire (SPEC §4 I4, §6)."""
    return "sha256:" + hashlib.sha256(_canon_bytes(obj)).hexdigest()


def schedule_key(item: str, qty: int, ship_date: int) -> str:
    """The canonical list-schedule key for a configuration (SPEC §6)."""
    return f"{item}|{int(qty)}|{int(ship_date)}"


# ── Line / Package / ListSchedule ──────────────────────────────────────────
@dataclass(frozen=True)
class Line:
    """One negotiable item in a package (SPEC §3). Frozen: a logged line can
    never be mutated after the fact.

    I1 is enforced HERE at the atom level: `price > list_price` is
    unconstructible. Prices are rounded to _PRICE_DP dp at construction (stored
    rounded), so the object and its wire form agree and the transcript hash is
    stable across processes — the notary's "round the stored components first"
    discipline (`core/notary.py`)."""

    line_id: str
    item: str
    qty: int
    ship_date: int
    list_price: float
    price: float

    def __post_init__(self) -> None:
        # round the stored money fields first (hash-stability + exact re-derive)
        object.__setattr__(self, "list_price", round(float(self.list_price), _PRICE_DP))
        object.__setattr__(self, "price", round(float(self.price), _PRICE_DP))
        object.__setattr__(self, "qty", int(self.qty))
        object.__setattr__(self, "ship_date", int(self.ship_date))
        if self.qty <= 0:
            raise NXViolation(f"line {self.line_id!r}: qty must be positive")
        if self.list_price < 0 or self.price < 0:
            raise NXViolation(f"line {self.line_id!r}: prices must be non-negative")
        if self.price > self.list_price + _TOL:                       # I1
            raise NXViolation(
                f"I1 NEVER-ABOVE-LIST is unconstructible: line {self.line_id!r} "
                f"priced {self.price} > list {self.list_price}")

    @property
    def key(self) -> str:
        return schedule_key(self.item, self.qty, self.ship_date)

    def to_wire(self) -> dict:
        return {"line_id": self.line_id, "item": self.item, "qty": self.qty,
                "ship_date": self.ship_date, "list_price": self.list_price,
                "price": self.price}

    @classmethod
    def from_wire(cls, d: dict) -> "Line":
        return cls(line_id=d["line_id"], item=d["item"], qty=d["qty"],
                   ship_date=d["ship_date"], list_price=d["list_price"],
                   price=d["price"])


# A Package is an ordered tuple of Lines. Kept as a plain tuple (not a wrapper
# class) so equality / verbatim comparison is structural and free.
Package = tuple  # tuple[Line, ...]


def package_total(pkg) -> float:
    return round(sum(ln.price for ln in pkg), _PRICE_DP)


def pkg_to_wire(pkg) -> list:
    return [ln.to_wire() for ln in pkg]


def pkg_from_wire(rows) -> tuple:
    return tuple(Line.from_wire(r) for r in rows)


@dataclass(frozen=True)
class ListSchedule:
    """The seller's committed list prices — the sole I1 list authority for a
    session (SPEC §4 I1). Stored as a sorted tuple of (key, list_price) so it is
    hashable and canonical; list prices are rounded to match Line rounding."""

    entries: tuple  # tuple[tuple[str, float], ...]

    @classmethod
    def from_map(cls, m: dict) -> "ListSchedule":
        rounded = {str(k): round(float(v), _PRICE_DP) for k, v in m.items()}
        return cls(entries=tuple(sorted(rounded.items())))

    def _map(self) -> dict:
        return dict(self.entries)

    def contains(self, item: str, qty: int, ship_date: int) -> bool:
        return schedule_key(item, qty, ship_date) in self._map()

    def list_for(self, item: str, qty: int, ship_date: int) -> float:
        k = schedule_key(item, qty, ship_date)
        m = self._map()
        if k not in m:
            raise NXViolation(f"config {k!r} is not in the seller's list schedule")
        return m[k]

    def to_wire(self) -> dict:
        return self._map()

    @classmethod
    def from_wire(cls, d: dict) -> "ListSchedule":
        return cls.from_map(d)


# ── messages (frozen; each self-describing with a `type`) ──────────────────
@dataclass(frozen=True)
class NXQuote:
    """Seller opens: a list schedule + an opening package drawn from it (SPEC
    §3). Every opening-package line is validated against the schedule at
    construction (I1)."""

    session_ref: str
    schedule: ListSchedule
    package: tuple  # Package
    type: str = field(default="NX-QUOTE", init=False)

    def __post_init__(self) -> None:
        _validate_package_against_schedule(self.package, self.schedule)

    def to_wire(self) -> dict:
        return {"type": "NX-QUOTE", "session_ref": self.session_ref,
                "schedule": self.schedule.to_wire(),
                "package": pkg_to_wire(self.package)}

    @classmethod
    def from_wire(cls, d: dict) -> "NXQuote":
        return cls(session_ref=d["session_ref"],
                   schedule=ListSchedule.from_wire(d["schedule"]),
                   package=pkg_from_wire(d["package"]))


@dataclass(frozen=True)
class NXPropose:
    """A full-package counter across all issues (SPEC §3). `party` is
    informational (who sent it); acceptance semantics do not depend on it."""

    session_ref: str
    party: str
    package: tuple  # Package

    type: str = field(default="NX-PROPOSE", init=False)

    def to_wire(self) -> dict:
        return {"type": "NX-PROPOSE", "session_ref": self.session_ref,
                "party": self.party, "package": pkg_to_wire(self.package)}

    @classmethod
    def from_wire(cls, d: dict) -> "NXPropose":
        return cls(session_ref=d["session_ref"], party=d["party"],
                   package=pkg_from_wire(d["package"]))


@dataclass(frozen=True)
class NXAccept:
    """Adopt the counterparty's standing package VERBATIM (I3). Carries NO
    package of its own — acceptance cannot introduce new terms."""

    session_ref: str
    party: str

    type: str = field(default="NX-ACCEPT", init=False)

    def to_wire(self) -> dict:
        return {"type": "NX-ACCEPT", "session_ref": self.session_ref,
                "party": self.party}

    @classmethod
    def from_wire(cls, d: dict) -> "NXAccept":
        return cls(session_ref=d["session_ref"], party=d["party"])


@dataclass(frozen=True)
class NXDecline:
    """End the session with no deal (SPEC §3)."""

    session_ref: str
    party: str
    reason: str = ""

    type: str = field(default="NX-DECLINE", init=False)

    def to_wire(self) -> dict:
        return {"type": "NX-DECLINE", "session_ref": self.session_ref,
                "party": self.party, "reason": self.reason}

    @classmethod
    def from_wire(cls, d: dict) -> "NXDecline":
        return cls(session_ref=d["session_ref"], party=d["party"],
                   reason=d.get("reason", ""))


_MSG_TYPES = {"NX-QUOTE": NXQuote, "NX-PROPOSE": NXPropose,
              "NX-ACCEPT": NXAccept, "NX-DECLINE": NXDecline}


def message_from_wire(d: dict):
    """Reconstruct any NX message from its wire dict (dispatch on `type`)."""
    t = d.get("type")
    if t not in _MSG_TYPES:
        raise NXViolation(f"unknown NX message type {t!r}")
    return _MSG_TYPES[t].from_wire(d)


def _validate_package_against_schedule(pkg, schedule: ListSchedule) -> None:
    """I1, session-level half: every line's configuration must be in the
    seller's schedule AND its list_price must equal the schedule's value for
    that config. Line construction already enforced price ≤ list_price; this
    stops a buyer inventing a list to create headroom (SPEC §4 I1)."""
    if not pkg:
        raise NXViolation("a package must have at least one line")
    for ln in pkg:
        listed = schedule.list_for(ln.item, ln.qty, ln.ship_date)  # raises if absent
        if abs(ln.list_price - listed) > _TOL:
            raise NXViolation(
                f"I1: line {ln.line_id!r} restates list_price {ln.list_price} but "
                f"the seller's schedule lists {listed} for config {ln.key!r}")


# ── session lifecycle ──────────────────────────────────────────────────────
class State(enum.Enum):
    MOUNTED = "mounted"        # session mounted, awaiting the seller's NX-QUOTE
    QUOTED = "quoted"          # seller NX-QUOTE on the table
    PROPOSED = "proposed"      # >=1 NX-PROPOSE exchanged, still open
    SETTLED = "settled"        # NX-ACCEPT: a package agreed
    DECLINED = "declined"      # NX-DECLINE / round bound exhausted, no deal


@dataclass(frozen=True)
class NXReceipt:
    """The I4 hook: a settled session's canonical, replayable receipt. Frozen.
    `attestation` is any attestor's signature over `transcript_hash` (or None) —
    the spec is attestor-neutral (SPEC §4 I4)."""

    protocol: str
    session_ref: str
    agreed_package: list          # wire form of the agreed package
    transcript_hash: str
    attestation: Optional[dict] = None

    def to_wire(self) -> dict:
        return {f.name: getattr(self, f.name) for f in _dc_fields(self)}

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_wire(), **kw)

    @classmethod
    def from_wire(cls, d: dict) -> "NXReceipt":
        return cls(protocol=d["protocol"], session_ref=d["session_ref"],
                   agreed_package=d["agreed_package"],
                   transcript_hash=d["transcript_hash"],
                   attestation=d.get("attestation"))

    @classmethod
    def from_json(cls, s: str) -> "NXReceipt":
        return cls.from_wire(json.loads(s))


class NXSession:
    """One buyer<->seller NX negotiation over one host RFQ/cart. Enforces I1–I4;
    the agreed package it exposes is what the host then pays for.

    Round bound (I2): `max_rounds` NX-PROPOSE messages are allowed; the next one
    raises. Accept-verbatim (I3): `accept()` takes no package and ratifies the
    standing package. Receipt (I4): `settle_receipt()` exposes the transcript
    hash + optional attestation."""

    def __init__(self, session_ref: str, max_rounds: int):
        if max_rounds < 1:
            raise NXProtocolError("max_rounds must be >= 1 (I2 declared at mount)")
        self.session_ref = session_ref
        self.max_rounds = int(max_rounds)
        self.state = State.MOUNTED
        self.schedule: Optional[ListSchedule] = None
        self.standing_package: Optional[tuple] = None
        self.last_proposer: Optional[str] = None
        self.rounds_used = 0
        self.agreed_package: Optional[tuple] = None
        self._log: list = []                      # ordered messages (the transcript)

    # -- transitions -------------------------------------------------------
    def quote(self, msg: NXQuote) -> None:
        """Seller opens (MOUNTED -> QUOTED). Sets the list authority + opening
        standing package. Legal exactly once."""
        if self.state != State.MOUNTED:
            raise NXProtocolError(f"quote illegal in {self.state}")
        if msg.session_ref != self.session_ref:
            raise NXProtocolError("quote session_ref mismatch")
        self.schedule = msg.schedule
        self.standing_package = msg.package
        self.last_proposer = "seller"
        self.state = State.QUOTED
        self._log.append(msg)

    def propose(self, msg: NXPropose) -> None:
        """A full-package counter (QUOTED|PROPOSED -> PROPOSED). Validates the
        package against the schedule (I1) and enforces the round bound (I2)."""
        if self.state not in (State.QUOTED, State.PROPOSED):
            raise NXProtocolError(f"propose illegal in {self.state}")
        if msg.session_ref != self.session_ref:
            raise NXProtocolError("propose session_ref mismatch")
        if self.rounds_used >= self.max_rounds:                       # I2
            raise NXProtocolError(
                f"I2 BOUNDED: round cap {self.max_rounds} exhausted")
        _validate_package_against_schedule(msg.package, self.schedule)  # I1
        self.rounds_used += 1
        self.standing_package = msg.package
        self.last_proposer = msg.party
        self.state = State.PROPOSED
        self._log.append(msg)

    def accept(self, party: str) -> "NXReceipt":
        """Ratify the standing package VERBATIM (QUOTED|PROPOSED -> SETTLED, I3).
        Takes no package: acceptance cannot introduce new terms. Returns the
        settled receipt (unattested; call settle_receipt for attestation)."""
        if self.state not in (State.QUOTED, State.PROPOSED):
            raise NXProtocolError(f"accept illegal in {self.state}")
        if self.standing_package is None:
            raise NXProtocolError("nothing to accept (no standing package)")
        self.agreed_package = self.standing_package        # verbatim, by reference
        self.state = State.SETTLED
        self._log.append(NXAccept(self.session_ref, party))
        return self.settle_receipt()

    def decline(self, party: str, reason: str = "") -> None:
        """End with no deal (open -> DECLINED)."""
        if self.state in (State.SETTLED, State.DECLINED):
            raise NXProtocolError(f"decline illegal in {self.state}")
        self.state = State.DECLINED
        self._log.append(NXDecline(self.session_ref, party, reason))

    # -- receipt hook (I4) -------------------------------------------------
    def canonical_transcript(self) -> list:
        """The ordered message list, each stamped with its sequence index — the
        exact input to the transcript hash (SPEC §4 I4)."""
        return [{"seq": i, **m.to_wire()} for i, m in enumerate(self._log)]

    def transcript_hash(self) -> str:
        """sha256 over the canonical-JSON transcript (I4)."""
        return canon_hash(self.canonical_transcript())

    def settle_receipt(self, attestation: Optional[dict] = None) -> NXReceipt:
        """Expose the I4 receipt for a SETTLED session. `attestation` is any
        attestor's signature over `transcript_hash` (or None)."""
        if self.state != State.SETTLED:
            raise NXProtocolError(
                f"settle_receipt illegal in {self.state} (need SETTLED)")
        return NXReceipt(
            protocol=PROTOCOL, session_ref=self.session_ref,
            agreed_package=pkg_to_wire(self.agreed_package),
            transcript_hash=self.transcript_hash(), attestation=attestation)

    @property
    def rounds_remaining(self) -> int:
        return self.max_rounds - self.rounds_used


# ── standalone verification (a third party needs only the settled artifacts) ─
def verify_transcript(messages, *, expected_hash: Optional[str] = None) -> dict:
    """Re-check a settled NX transcript standalone (I4). `messages` is a list of
    wire dicts (as from `canonical_transcript()`). Re-derives the hash and
    re-checks I1 (no line priced above its list, and every proposed line's list
    matches the seller's quote schedule). Returns {ok, checks, reasons, hash}.

    A verifier needs nothing but the transcript: this is what makes the receipt
    hook cheap to audit (SPEC §4)."""
    checks: dict = {}
    reasons: list = []

    # strip any `seq` stamps and recompute the hash over the canonical transcript
    stripped = [{k: v for k, v in m.items() if k != "seq"} for m in messages]
    stamped = [{"seq": i, **m} for i, m in enumerate(stripped)]
    got_hash = canon_hash(stamped)
    if expected_hash is not None:
        checks["hash"] = (got_hash == expected_hash)
        if not checks["hash"]:
            reasons.append("transcript hash does not match expected")

    schedule = None
    i1_ok = True
    for m in stripped:
        t = m.get("type")
        if t == "NX-QUOTE":
            schedule = ListSchedule.from_wire(m["schedule"])._map()
        pkg = m.get("package")
        if not pkg:
            continue
        for ln in pkg:
            if float(ln["price"]) > float(ln["list_price"]) + _TOL:
                i1_ok = False
                reasons.append(f"line {ln.get('line_id')} priced above its list")
            if t == "NX-PROPOSE" and schedule is not None:
                k = schedule_key(ln["item"], ln["qty"], ln["ship_date"])
                if k not in schedule:
                    i1_ok = False
                    reasons.append(f"proposed config {k} absent from quote schedule")
                elif abs(float(ln["list_price"]) - schedule[k]) > _TOL:
                    i1_ok = False
                    reasons.append(f"proposed line {ln.get('line_id')} restates list")
    checks["I1_never_above_list"] = i1_ok
    ok = all(checks.values())
    return {"ok": ok, "checks": checks, "reasons": reasons, "hash": got_hash}

"""Core types for the snhp-price/1 protocol and the VEND sim.

The invariants the endgame depends on live HERE, in constructors — not in
policy docs:

  * discount-only  — a Quote cannot price any unit above its list price
  * receipt        — a Quote cannot exist without a non-empty `why`
  * context-based  — quoting functions take (state, intent, clock); there is
                     no buyer-identity parameter anywhere in this package,
                     and `Quote.context_hash` makes "same context, same
                     price" auditable from the artifact alone
  * replayable     — every Quote carries {policy_id, seed, state_hash}
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

PROTOCOL = "snhp-price/1"


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (the gauntlet pattern): blake2b of the
    master seed and any hashable parts, folded to 63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


def _canon_hash(obj) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return "b3:" + hashlib.blake2b(payload.encode(), digest_size=16).hexdigest()


@dataclass(frozen=True)
class Listing:
    """One SKU on one machine. `list_price` is the ceiling, always."""
    sku: str
    list_price: float
    unit_cost: float
    salvage: float          # per-unit recovery at expiry
    shelf_life_days: int    # lot lifetime from stocking day
    par_stock: int          # nightly restock target
    wtp_mu_est: float = 0.0  # the OPERATOR'S demand estimate (what set the
                             # sticker; also what dynamic arms believe)


@dataclass
class Lot:
    sku: str
    quantity: int
    expires_day: int        # end of this day → salvage


@dataclass
class MachineState:
    machine_id: str
    listings: dict[str, Listing]
    lots: list[Lot]
    day: int = 0
    tick: int = 0           # 96 five-minute ticks per day

    def stock(self, sku: str) -> int:
        return sum(l.quantity for l in self.lots if l.sku == sku and l.quantity > 0)

    def days_to_expiry(self, sku: str) -> int | None:
        """Days until the EARLIEST live lot of `sku` expires (0 = today)."""
        live = [l.expires_day for l in self.lots if l.sku == sku and l.quantity > 0]
        return None if not live else min(live) - self.day

    def take(self, sku: str, n: int) -> None:
        """Vend n units, earliest-expiring lots first."""
        for lot in sorted((l for l in self.lots if l.sku == sku), key=lambda l: l.expires_day):
            got = min(lot.quantity, n)
            lot.quantity -= got
            n -= got
            if n == 0:
                return
        raise ValueError(f"insufficient stock for {sku}")

    def state_hash(self) -> str:
        return _canon_hash({
            "machine": self.machine_id, "day": self.day, "tick": self.tick,
            "lots": sorted((l.sku, l.quantity, l.expires_day) for l in self.lots if l.quantity > 0),
        })


@dataclass(frozen=True)
class BuyerIntent:
    """What the buyer's side reveals. In posted-price arms this is only the
    arrival itself; in A2A mode it carries the agent's signed disclosure."""
    sku: str
    quantity: int = 1
    substitutes_ok: bool = False
    disclosure: dict | None = None   # A2A only (P1): utilities + BATNA
    peer_proof: dict | None = None   # A2A only (P1): attestation


class QuoteViolation(ValueError):
    """An invariant of snhp-price/1 was violated at construction time."""


@dataclass(frozen=True)
class QuoteItem:
    sku: str
    quantity: int
    unit_price: float
    list_price: float


@dataclass(frozen=True)
class Quote:
    quote_id: str
    machine_id: str
    items: tuple[QuoteItem, ...]
    why: tuple[str, ...]
    context_hash: str
    policy_id: str
    seed: int
    state_hash: str
    expires_tick: int       # sim-clock TTL; API layer maps this to wall time
    protocol: str = PROTOCOL

    def __post_init__(self):
        if not self.items:
            raise QuoteViolation("a quote must price at least one item")
        for it in self.items:
            if it.unit_price > it.list_price + 1e-9:
                raise QuoteViolation(
                    f"discount-only violated: {it.sku} quoted {it.unit_price}"
                    f" above list {it.list_price}")
            if it.unit_price < 0 or it.quantity < 1:
                raise QuoteViolation(f"malformed item {it}")
        if not self.why:
            raise QuoteViolation("a quote must carry its receipt (why[])")

    @property
    def total(self) -> float:
        return round(sum(it.unit_price * it.quantity for it in self.items), 2)


def make_quote(state: MachineState, policy_id: str, seed: int,
               items: list[QuoteItem], why: list[str], hour: int,
               ttl_ticks: int = 2) -> Quote:
    """The one constructor policies use. Context hash covers everything a
    quote may lawfully depend on — machine state, the priced items, and the
    hour — and nothing else."""
    ctx = _canon_hash({
        "state": state.state_hash(), "hour": hour,
        "items": [(i.sku, i.quantity) for i in items],
        "policy": policy_id,
    })
    return Quote(
        quote_id="q_" + _canon_hash({"c": ctx, "s": seed})[3:15],
        machine_id=state.machine_id,
        items=tuple(items), why=tuple(why), context_hash=ctx,
        policy_id=policy_id, seed=seed, state_hash=state.state_hash(),
        expires_tick=state.tick + ttl_ticks,
    )


@dataclass(frozen=True)
class Deal:
    quote_id: str
    day: int
    tick: int
    total: float
    items: tuple[QuoteItem, ...]
    consumer_surplus: float   # dollars: bundle utility minus paid
    mandate: dict | None = None   # A2A settlements carry an AP2 cart mandate (P1)

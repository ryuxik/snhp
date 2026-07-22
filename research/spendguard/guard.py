"""guard.py — the mechanical spend guard (ARM-G's money owner).

The guard holds the buyer's ground truth (list ℓ and private value v) OUTSIDE the
conversation and owns every money decision. It NEVER reads a total from the LLM
or the transcript: it computes the all-in total straight from the seller's
STRUCTURED offer state (base price + every structured fee) and refuses to let the
buyer ACCEPT anything whose total exceeds the ceiling min(ℓ, v). A blocked ACCEPT
is replaced with the SNHP engine's counter (gt_negotiate_turn, side="buy",
walk_away = min(ℓ, v)) — or a walk near the deadline.

THE INVARIANT (the notary's "unconstructible" sense): there is NO input to
``decide`` — no offer state, no proposed action, no fee arrangement — that yields
a returned ACCEPT whose all-in total exceeds min(ℓ, v). Above-list and above-value
acceptance are unconstructible through this function; we raise/replace, never
trust. ``decide`` is a PURE function (its only dependency is the deterministic
plain-terms negotiation math — no LLM, no network), so it is unit-testable in
isolation, which is exactly how the property test hammers the invariant.

Honesty: ARM-G's resulting zero-leak is a MECHANICAL property of this function,
to be reported as mechanical — never as a capability of the model in the seat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# gt_negotiate_turn(compute_ms=0) delegates verbatim to plain_terms.negotiate_turn
# (see gametheory/server/mcp_server.py); we call the core directly to avoid the
# MCP transport layer. Identical math, fully deterministic, no network.
from gametheory.negotiation.plain_terms import negotiate_turn as gt_negotiate_turn

# Float tolerance: a total is "above" the ceiling only if it exceeds it by more
# than this. Genuine C0 discounts clear it comfortably; A5's ℓ+ε (ε ≥ a few
# dollars) is far above it — so ℓ+ε acceptances are correctly blocked.
GUARD_TOL = 1e-6

# The guard is blind to the seller's floor (it holds only ℓ and v). Its counter
# aspires to this fraction of the ceiling — a low but positive target that keeps
# every engine counter strictly at or below the ceiling by construction.
_ASPIRATION_FRAC = 0.70


@dataclass(frozen=True)
class Action:
    """A buyer move. ``kind`` in {"accept", "offer", "walk"}; ``price`` is the
    offered dollar amount for an OFFER (None otherwise). ``meta`` carries
    provenance (e.g. guard-block details) and never affects settlement math."""
    kind: str
    price: Optional[float] = None
    meta: dict = field(default_factory=dict)


def compute_total(offer_state: dict) -> float:
    """The all-in total from the STRUCTURED offer state — base price plus every
    structured fee. This is the single source of settlement truth; it never reads
    the seller's natural-language message."""
    price = float(offer_state["price"])
    fees = offer_state.get("fees") or []
    return round(price + sum(float(f["amount"]) for f in fees), 2)


def _engine_counter(total: float, ceiling: float, rounds_left: int, item: str) -> Action:
    """The SNHP engine's safe reply to a rejected above-ceiling offer. By
    construction the buyer frame maps every recommendation into [target, ceiling],
    so the counter price is ALWAYS <= ceiling; a walk is returned near the
    deadline. Never returns an ACCEPT (defended below)."""
    rec = gt_negotiate_turn(
        side="buy",
        walk_away=round(ceiling, 2),
        target=round(ceiling * _ASPIRATION_FRAC, 2),
        counterparty_offers=[round(total, 2)],
        rounds_left=max(1, int(rounds_left)),
        item=item,
    )
    act = rec.get("action")
    if act == "walk":
        return Action("walk", meta={"source": "guard-engine"})
    if act == "accept":
        # Unreachable for an above-ceiling counterparty offer (its utility is
        # negative in the buyer frame), but we must NEVER emit an accept from the
        # blocked branch — that would make above-ceiling acceptance constructible.
        raise RuntimeError(
            "guard invariant violated: engine returned ACCEPT for an above-ceiling "
            f"total={total} against ceiling={ceiling}")
    price = round(float(rec["recommended_price"]), 2)
    if price > ceiling + GUARD_TOL:
        # Defensive: the frame guarantees price <= ceiling; if that ever failed we
        # clamp rather than propose an above-ceiling counter.
        price = round(ceiling, 2)
    return Action("offer", price=price, meta={"source": "guard-engine"})


def decide(offer_state: dict, proposed_action: Action, *,
           list_price: float, value: float,
           rounds_left: int = 6, item: str = "this") -> Action:
    """Return the FINAL buyer action after the mechanical guard.

    OFFER and WALK pass through untouched — the model may propose or walk freely.
    ACCEPT is gated on the ceiling min(list_price, value): if the STRUCTURED total
    is at or below the ceiling the accept stands (a genuinely good deal closes);
    if it exceeds the ceiling the accept is BLOCKED and replaced with the engine
    counter (or a walk). The returned action can never be an ACCEPT above the
    ceiling — that is the guard's guarantee.
    """
    ceiling = round(min(float(list_price), float(value)), 2)

    if proposed_action.kind != "accept":
        # Nothing to guard: the buyer isn't committing money this turn.
        return proposed_action

    total = compute_total(offer_state)
    if total <= ceiling + GUARD_TOL:
        # Within budget — let the good deal close, and record the verified total.
        return Action("accept", meta={**proposed_action.meta,
                                      "guard_total": total, "guard_ceiling": ceiling,
                                      "blocked": False})
    # Over budget — block and substitute a safe move.
    counter = _engine_counter(total, ceiling, rounds_left, item)
    counter.meta.update({"blocked": True, "blocked_total": total,
                         "guard_ceiling": ceiling,
                         "reason": "structured total exceeds min(list, value)"})
    return counter

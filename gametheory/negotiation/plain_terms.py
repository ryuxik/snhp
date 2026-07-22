"""
Plain-terms negotiation — the high-level, agent-facing entry point.

WHY THIS EXISTS (Phase 0 / WS1 of the agent-adoption plan)
The core recommenders (sell.py / buy.py) speak NORMALIZED UTILITY [0,1] — great
math, unusable by a context-free agent whose negotiation is in dollars. A cold
agent could not map its real problem in and the [0,1] result back out. This
module is the translation layer: **dollars and terms in, a concrete dollar
counter-offer + a ready-to-send message + an accept/reject/hold decision out.**
All the [0,1] normalization, Bayesian opponent inference, and Pareto math run
internally and are never exposed.

Model (single-issue price, the 90% case): the negotiation lives on a linear value
frame between your WALK-AWAY (the worst price you'd accept) and your TARGET (your
aspiration). A seller's utility rises with price; a buyer's rises as price falls.
We map every dollar figure onto that frame, call the validated recommender, and
map the recommendation back to dollars.

Single-side by design: it needs NO counterparty setup, no keys, no peering, and
no configuration — one good default. Validated edge: ~12% better head-to-head,
measured on this exact recommender across 20 paired LLM negotiations (95% CI
+6.5-17.4%, p<0.0001). Scope: single-issue price.
"""
from __future__ import annotations

from typing import Literal, Optional

from gametheory.negotiation.sell import sell_next_offer
from gametheory.negotiation.buy import buy_next_offer


# The single, hidden operating point. This is the EXACT pareto_knob the +12%
# head-to-head result was validated at (n=20 paired LLM tournament). Pinning it
# here means "what ships" == "what was validated" == "what we claim". We do NOT
# expose it — one good default, no config, is the product decision. (Trade-off:
# this holds firmer, so it walks away from below-floor counterparties rather than
# capitulating — which is the correct call.)
_VALIDATED_KNOB = 1.0


class NegotiationInputError(ValueError):
    """Bad real-world inputs (e.g. a seller target below their walk-away)."""


def validate_terms(*, side: str, walk_away: float, target: float,
                   rounds_left: Optional[int] = None) -> None:
    """The single source of truth for "are these real-world bounds coherent?".

    Raises NegotiationInputError on a bad side, a non-positive reservation/target,
    an inverted target/walk_away for the side, or (when supplied) rounds_left < 1.
    negotiate_turn calls this, and the paid-session layer (vend.session) calls it
    too — so a degenerate session is refused IDENTICALLY, and in the paid path
    BEFORE any charge (never sell an unusable session then 500 on the first move).
    rounds_left=None skips the per-move horizon check: a session OPEN carries no
    rounds_left (it is a per-move input), so open-time validation omits it."""
    if side not in ("sell", "buy"):
        raise NegotiationInputError("side must be 'sell' or 'buy'")
    if walk_away <= 0 or target <= 0:
        raise NegotiationInputError("walk_away and target must be positive dollar amounts")
    if rounds_left is not None and rounds_left < 1:
        raise NegotiationInputError("rounds_left must be >= 1")
    if side == "sell" and target <= walk_away:
        raise NegotiationInputError(
            "for a seller, target (your aspiration) must be ABOVE walk_away (your floor)")
    if side == "buy" and target >= walk_away:
        raise NegotiationInputError(
            "for a buyer, target (your aspiration) must be BELOW walk_away (your ceiling)")


def _seller_frame(walk_away: float, target: float):
    span = target - walk_away
    return (lambda p: (p - walk_away) / span,          # dollars -> utility (raw)
            lambda u: walk_away + u * span)            # utility -> dollars


def _buyer_frame(walk_away: float, target: float):
    # buyer: walk_away is the MOST they'll pay (top), target is the low aspiration
    span = walk_away - target
    return (lambda p: (walk_away - p) / span,
            lambda u: walk_away - u * span)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _fmt(x: float) -> str:
    return f"${x:,.2f}"


def negotiate_turn(
    *,
    side: Literal["sell", "buy"],
    walk_away: float,
    target: float,
    counterparty_offers: Optional[list[float]] = None,
    my_previous_offers: Optional[list[float]] = None,
    rounds_left: int = 8,
    item: str = "this",
) -> dict:
    """
    One negotiation turn, entirely in real units.

    Args (all dollar figures are real money, not normalized):
      side                 "sell" or "buy" — which side you are.
      walk_away            Your reservation: the WORST price you'd accept. (Seller:
                           your floor / minimum. Buyer: your ceiling / maximum.)
      target               Your aspiration: the price you'd love to get. (Seller:
                           high. Buyer: low.)
      counterparty_offers  The other side's offers so far, in dollars, oldest→newest.
      my_previous_offers   Your own prior offers, in dollars (optional).
      rounds_left          Roughly how many more back-and-forths before it times out.
      item                 What's being traded (used only in the drafted message).

    Returns a dict you can act on directly:
      action               "counter" | "accept" | "walk" | "negotiate_directly"
      recommended_price    The dollar figure to put on the table (for "counter")
                           or the price to accept (for "accept").
      message              A ready-to-send message containing that price.
      rationale            One plain sentence explaining the move.
      fit                  {"score": good|marginal|poor, "reason": ...} — whether
                           this is the kind of negotiation we actually help with.
      expected_settlement  Our estimate of where this lands, in dollars (or None).
      confidence           0–1 confidence in the opponent read (or None).
    """
    counterparty_offers = [float(x) for x in (counterparty_offers or [])]
    my_previous_offers = [float(x) for x in (my_previous_offers or [])]
    # Single source of truth for the bound checks (also called pre-charge by the
    # paid-session layer so a degenerate session is refused before the $2 lands).
    validate_terms(side=side, walk_away=walk_away, target=target,
                   rounds_left=rounds_left)

    # ── Fit-check (WS4): is this even the kind of thing we help with? ──────────
    if rounds_left <= 1:
        return {
            "action": "negotiate_directly",
            "recommended_price": round(target, 2),
            "message": f"My {'price' if side == 'sell' else 'offer'} is {_fmt(target)}.",
            "rationale": ("This is effectively one-shot (no rounds left to trade "
                          "concessions). A negotiation copilot adds little here — "
                          "lead with your target and hold."),
            "fit": {"score": "poor", "reason": "single-shot; SNHP's edge is multi-round"},
            "expected_settlement": None, "confidence": None,
        }

    to_util, to_price = _seller_frame(walk_away, target) if side == "sell" \
        else _buyer_frame(walk_away, target)

    opp_hist = [_clamp01(to_util(p)) for p in counterparty_offers]
    my_hist = [_clamp01(to_util(p)) for p in my_previous_offers]

    # deadline_rounds must be the TOTAL horizon, not the rounds REMAINING.
    # The recommenders compute time_fraction = rounds_used / deadline_rounds where
    # rounds_used = len(my_offers) + len(opp_offers) is CUMULATIVE across both sides
    # (sell.py:119-120, buy.py:208-209). Passing rounds_left (remaining) here made
    # cumulative >= remaining ⇒ time_fraction clamped to 1.0 ⇒ the concession
    # schedule saturated ⇒ aspiration collapsed to the floor and the engine accepted
    # a rising buyer's floor with rounds still on the clock (vend/RESULTS.md P7).
    # Total horizon = offers already exchanged + rounds still left, so
    # time_fraction = rounds_used / (rounds_used + rounds_left) never saturates.
    total_horizon = len(counterparty_offers) + len(my_previous_offers) + rounds_left
    if side == "sell":
        rec = sell_next_offer(
            my_reservation=0.0, opponent_offer_history=opp_hist,
            my_offer_history=my_hist, deadline_rounds=total_horizon,
            pareto_knob=_VALIDATED_KNOB)
    else:
        rec = buy_next_offer(
            my_reservation=0.0, seller_offer_history=opp_hist,
            my_offer_history=my_hist, deadline_rounds=total_horizon,
            pareto_knob=_VALIDATED_KNOB)

    recommended_util = float(rec["recommended_offer"])
    recommended_price = to_price(recommended_util)
    post = rec.get("posterior", {}) or {}
    confidence = post.get("confidence")

    # opponent's latest, in raw utility (can be < 0 if below our walk-away)
    their_last = counterparty_offers[-1] if counterparty_offers else None
    their_util_raw = to_util(their_last) if their_last is not None else None

    # Expected settlement = the midpoint of the two LIVE positions (deals usually
    # split the current gap). Intuitive and never inverts — unlike mapping
    # expected utility back to price, which collapses toward the walk-away.
    expected_settlement = (round((recommended_price + their_last) / 2.0, 2)
                           if their_last is not None else None)

    # ── Decision (all comparisons are "better for us") ────────────────────────
    if their_util_raw is None:
        action, price = "counter", recommended_price       # opening move
    elif their_util_raw >= recommended_util:
        action, price = "accept", their_last               # they meet/beat our ask
    elif their_util_raw < 0.0:
        # their offer is worse than our walk-away
        action, price = ("walk", their_last) if rounds_left <= 2 else ("counter", recommended_price)
    else:
        action, price = "counter", recommended_price

    price = round(price, 2)
    # Keep expected_settlement consistent with the decision: there is no
    # settlement on a walk, and an accept settles at the price we're taking.
    if action == "walk":
        expected_settlement = None
    elif action == "accept":
        expected_settlement = price
    fit = _fit_signal(side, walk_away, target, post)
    return {
        "action": action,
        "recommended_price": price,
        "message": _draft(side, action, price, item),
        "rationale": _rationale(side, action, price, their_last, expected_settlement),
        "fit": fit,
        "expected_settlement": expected_settlement,
        "confidence": round(float(confidence), 3) if confidence is not None else None,
    }


def _fit_signal(side, walk_away, target, posterior) -> dict:
    span = abs(target - walk_away)
    anchor = max(walk_away, target)
    if span / max(anchor, 1e-9) < 0.02:
        return {"score": "marginal",
                "reason": "your walk-away and target are nearly equal — little room to negotiate"}
    # estimated opponent reservation (utility, in OUR frame): high => ZOPA likely
    opp_rv = posterior.get("estimated_opp_reservation")
    if opp_rv is not None and opp_rv < 0.05:
        return {"score": "marginal",
                "reason": "the other side looks anchored near your walk-away — a deal may be tight"}
    return {"score": "good", "reason": "multi-round price negotiation with room to trade — our sweet spot"}


def _draft(side, action, price, item) -> str:
    p = _fmt(price)
    if action == "accept":
        return f"That works for me — {p} it is. Let's proceed with {item}."
    if action == "walk":
        return ("I don't think we can bridge the gap on price here, but thanks for "
                "the discussion.")
    if side == "sell":
        return f"Thanks for the offer. The best I can do on {item} is {p}."
    return f"Appreciate it. For {item} I can go to {p}."


def _rationale(side, action, price, their_last, expected) -> str:
    if action == "accept":
        return f"Their {_fmt(their_last)} already meets the math-optimal target — take it."
    if action == "walk":
        return f"Their {_fmt(their_last)} is below your walk-away and rounds are nearly out."
    direction = "hold near your aspiration and concede slowly" if their_last is None \
        else "concede toward the efficient split, not all the way to your floor"
    tail = f" (we estimate this settles around {_fmt(expected)})." if expected else "."
    return f"Counter at {_fmt(price)}: {direction}{tail}"

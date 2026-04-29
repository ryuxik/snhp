"""
Single-axis price negotiation harness for the public leaderboard.

This is a deliberately simpler protocol than the multi-attribute NegMAS
tournament in `snhp/b2b_round_robin.py`:
  - One axis (price), normalized to [0, 1] = utility-to-self.
  - Alternating offers (SAO).
  - Both sides have a private reservation drawn from the same prior.
  - Game ends on accept, walk-away, or deadline.

Why this shape: easy to reason about on a public page ("higher = better
deal for you"), easy to wrap an LLM as a player (output a single number),
and the main empirical claim — "an LLM-only negotiator leaves surplus
on the table that SNHP captures" — surfaces clearly in one chart.

The multi-attribute tournament still anchors the academic claim; this
just makes the public-facing comparison legible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# An agent is a callable: (state) -> NegotiationAction
# Action is one of:
#   {"action": "offer", "price": float}     # propose this price (in our utility space)
#   {"action": "accept"}                    # accept opponent's last offer
#   {"action": "walk"}                      # walk away (both get 0)


@dataclass
class GameState:
    role: str                                # "seller" or "buyer"
    my_reservation: float                    # walk-away utility-to-self in [0, 1]
    deadline_rounds: int                     # max alternating offers
    round_index: int                         # current round (0 = first propose)
    opponent_offer_history: list[float]      # in our utility space
    my_offer_history: list[float]
    last_opponent_offer: Optional[float]


AgentFn = Callable[[GameState], dict]


@dataclass
class GameOutcome:
    deal_closed: bool
    my_utility: float                        # 0 if no deal
    opponent_utility: float
    rounds_played: int
    walk_away_by: Optional[str]              # "me" / "opponent" / None
    transcript: list[dict] = field(default_factory=list)


def play_game(
    *,
    seller: AgentFn,
    buyer: AgentFn,
    seller_reservation: float,
    buyer_reservation: float,
    deadline_rounds: int = 10,
) -> tuple[GameOutcome, GameOutcome]:
    """Run one alternating-offers game. Seller proposes first.

    The "price" carried in the protocol is in *seller utility space*: 1.0
    means seller captures all surplus, 0.0 means buyer captures all surplus.
    Buyer-utility = 1 - seller-utility under this convention.

    Returns (seller_outcome, buyer_outcome).
    """
    transcript: list[dict] = []
    seller_history: list[float] = []
    buyer_history: list[float] = []  # opponent's offers in BUYER utility space

    last_offer_in_seller_space: Optional[float] = None

    for round_idx in range(deadline_rounds):
        proposer_role = "seller" if round_idx % 2 == 0 else "buyer"
        if proposer_role == "seller":
            # Buyer's offers come in buyer-utility space; flip into seller's
            # frame so `last_opponent_offer >= threshold` reads consistently
            # across roles.
            seller_view_of_buyer = [1.0 - p for p in buyer_history]
            state = GameState(
                role="seller",
                my_reservation=seller_reservation,
                deadline_rounds=deadline_rounds,
                round_index=round_idx,
                opponent_offer_history=seller_view_of_buyer,
                my_offer_history=seller_history,
                last_opponent_offer=seller_view_of_buyer[-1] if seller_view_of_buyer else None,
            )
            action = seller(state)
        else:
            # Buyer's view: invert the price so 1.0 = best for them.
            buyer_opp_history = [1.0 - p for p in seller_history]
            buyer_my_history = [1.0 - p for p in buyer_history]
            buyer_last_opp = buyer_opp_history[-1] if buyer_opp_history else None
            state = GameState(
                role="buyer",
                my_reservation=buyer_reservation,
                deadline_rounds=deadline_rounds,
                round_index=round_idx,
                opponent_offer_history=buyer_opp_history,
                my_offer_history=buyer_my_history,
                last_opponent_offer=buyer_last_opp,
            )
            action = buyer(state)

        kind = action.get("action")

        if kind == "walk":
            transcript.append({"round": round_idx, "actor": proposer_role, "action": "walk"})
            return (
                GameOutcome(False, 0.0, 0.0, round_idx + 1,
                             walk_away_by=proposer_role, transcript=transcript),
                GameOutcome(False, 0.0, 0.0, round_idx + 1,
                             walk_away_by=proposer_role, transcript=transcript),
            )

        if kind == "accept":
            if last_offer_in_seller_space is None:
                raise ValueError(
                    f"{proposer_role} accepted with no prior offer on the table"
                )
            su, bu = _utilities(last_offer_in_seller_space,
                                seller_reservation, buyer_reservation)
            transcript.append({"round": round_idx, "actor": proposer_role,
                                "action": "accept",
                                "price_seller_space": last_offer_in_seller_space})
            return (
                GameOutcome(True, su, bu, round_idx + 1, None, transcript),
                GameOutcome(True, bu, su, round_idx + 1, None, transcript),
            )

        if kind != "offer":
            raise ValueError(f"unknown action {kind!r} from {proposer_role}")

        offered_in_self_space = float(action["price"])
        if proposer_role == "seller":
            offered_in_seller_space = offered_in_self_space
            seller_history.append(offered_in_seller_space)
        else:
            offered_in_seller_space = 1.0 - offered_in_self_space
            buyer_history.append(offered_in_self_space)

        transcript.append({"round": round_idx, "actor": proposer_role,
                            "action": "offer",
                            "price_seller_space": round(offered_in_seller_space, 4)})
        last_offer_in_seller_space = offered_in_seller_space

    # Deadline reached without agreement → no deal.
    transcript.append({"round": deadline_rounds, "actor": "system",
                        "action": "deadline", "outcome": "no_deal"})
    return (
        GameOutcome(False, 0.0, 0.0, deadline_rounds, None, transcript),
        GameOutcome(False, 0.0, 0.0, deadline_rounds, None, transcript),
    )


def _utilities(price_seller_space: float,
                seller_reservation: float, buyer_reservation: float) -> tuple[float, float]:
    """Map a closed price (in seller utility space) to per-side utilities.

    Caller supplies *minimum-acceptable* utility levels (reservations); a
    closed deal at price p in seller-space delivers:
      seller utility = p          (already in seller-utility space)
      buyer  utility = 1 - p
    Reservations only matter at decision time (was it acceptable?). Once
    both sides have agreed, the realized utilities are above-reservation
    by construction.
    """
    return float(price_seller_space), float(1.0 - price_seller_space)

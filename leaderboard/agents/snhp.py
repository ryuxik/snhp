"""
SNHP agents — vanilla and tuned — built on top of the public gametheory-mcp
package, so the leaderboard reproduces what a customer would get by
pip-installing the package and pointing it at the same scenarios.

  snhp_vanilla_agent   — pareto_knob=0.5 (balanced default)
  snhp_tuned_agent     — pareto_knob=0.85 (margin-max from sell-side frontier)

Both wrap the same `sell_next_offer` / `buy_next_offer` math; the only
difference is the Pareto-knob. We expose both to give the leaderboard a
sense of the band: vanilla is what an out-of-the-box user gets;
"tuned" is what's available via api.snhp.dev with calibrated defaults.
"""
from __future__ import annotations

from gametheory_mcp.negotiation import sell_next_offer, buy_next_offer

from leaderboard.protocol import GameState


def _snhp_action(state: GameState, pareto_knob: float) -> dict:
    """Common math: produce next-offer or accept based on the public package."""
    accept_threshold = max(state.my_reservation,
                            _accept_threshold(state, pareto_knob))
    if (state.last_opponent_offer is not None
            and state.last_opponent_offer >= accept_threshold):
        return {"action": "accept"}

    if state.role == "seller":
        rec = sell_next_offer(
            my_reservation=state.my_reservation,
            opponent_offer_history=state.opponent_offer_history,
            my_offer_history=state.my_offer_history,
            deadline_rounds=state.deadline_rounds,
            pareto_knob=pareto_knob,
        )
    else:
        rec = buy_next_offer(
            my_reservation=state.my_reservation,
            seller_offer_history=state.opponent_offer_history,
            my_offer_history=state.my_offer_history,
            deadline_rounds=state.deadline_rounds,
            pareto_knob=pareto_knob,
        )
    return {"action": "offer", "price": float(rec["recommended_offer"])}


def _accept_threshold(state: GameState, pareto_knob: float) -> float:
    """Time-decaying aspiration matching what sell_next_offer would have
    proposed at this round — used as the 'I'd rather take this than
    counter-offer' threshold."""
    asp_start = 0.55 + (0.89 - 0.55) * pareto_knob
    t = state.round_index / max(1, state.deadline_rounds - 1)
    return asp_start - (asp_start - state.my_reservation) * t * 0.9


def snhp_vanilla_agent(state: GameState) -> dict:
    return _snhp_action(state, pareto_knob=0.5)


def snhp_tuned_agent(state: GameState) -> dict:
    return _snhp_action(state, pareto_knob=0.85)

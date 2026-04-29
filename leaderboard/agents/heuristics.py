"""
Programmatic baseline agents — the comparison points for the public
leaderboard. These are deliberately simple so the gap between them and
SNHP is interpretable.

  random_agent          — random offer in [reservation, 1]
  aspiration_agent      — time-decaying aspiration (NegMAS classic)
  anchorer_agent        — extreme open, slow retreat
  fair_demand_agent     — splits 50/50, refuses below
"""
from __future__ import annotations

import random

from leaderboard.protocol import GameState


def random_agent(state: GameState) -> dict:
    """Uniform random in [my_reservation, 1.0]. Accepts any offer above
    reservation. Walk-away never (would lose to deadline anyway)."""
    if state.last_opponent_offer is not None and state.last_opponent_offer >= state.my_reservation:
        return {"action": "accept"}
    p = random.uniform(state.my_reservation, 1.0)
    return {"action": "offer", "price": p}


def aspiration_agent(state: GameState) -> dict:
    """Linear time-decay from 0.95 to my_reservation. Accept if opponent's
    offer beats my current aspiration."""
    t = state.round_index / max(1, state.deadline_rounds - 1)
    aspiration = 0.95 - (0.95 - state.my_reservation) * t
    if state.last_opponent_offer is not None and state.last_opponent_offer >= aspiration:
        return {"action": "accept"}
    return {"action": "offer", "price": aspiration}


def anchorer_agent(state: GameState) -> dict:
    """Extreme first offer (0.97), slow linear retreat to 0.55."""
    t = state.round_index / max(1, state.deadline_rounds - 1)
    target = 0.97 if t < 0.05 else 0.95 - 0.40 * t
    target = max(target, state.my_reservation)
    accept_threshold = 0.70 if t < 0.7 else (0.55 if t < 0.95 else 0.45)
    if (state.last_opponent_offer is not None
            and state.last_opponent_offer >= accept_threshold):
        return {"action": "accept"}
    return {"action": "offer", "price": target}


def fair_demand_agent(state: GameState) -> dict:
    """Demands ≥ 0.50 forever. Walks if opponent stays below 0.45 to deadline."""
    if state.last_opponent_offer is not None:
        if state.last_opponent_offer >= 0.50:
            return {"action": "accept"}
        if state.round_index >= state.deadline_rounds - 1 and state.last_opponent_offer < 0.45:
            return {"action": "walk"}
    return {"action": "offer", "price": 0.55}


def split_diff_agent(state: GameState) -> dict:
    """Concedes halfway between own previous offer and opponent's previous offer."""
    if state.last_opponent_offer is not None and state.last_opponent_offer >= 0.55:
        return {"action": "accept"}
    if not state.my_offer_history:
        return {"action": "offer", "price": 0.85}
    last_mine = state.my_offer_history[-1]
    last_opp = state.last_opponent_offer if state.last_opponent_offer is not None else state.my_reservation
    midpoint = (last_mine + last_opp) / 2.0
    return {"action": "offer", "price": max(midpoint, state.my_reservation)}

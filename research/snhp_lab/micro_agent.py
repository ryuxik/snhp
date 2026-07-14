"""
MiCRO — Minimal-Concession Reciprocal Opponent.

Beats parameterized Bayesian opponent-modeling agents in published
multilateral SAO settings (cited in the playbook plan: "minimal-
concession strategies that synchronize with the slowest-conceding
counterpart can outperform more parameterized, opponent-modeling
agents in multilateral settings").

Strategy:
  1. Open with maximum aspiration (target = 1.0 minus a small ε).
  2. Each round, look at opponent's concession over their last K offers.
     Concede by exactly the SAME amount they did (synchronize). If they
     didn't concede, we don't either (minimal concession).
  3. Accept any offer ≥ our current aspiration.
  4. At deadline, accept any offer above reservation (don't walk into 0).

The published advantage: no estimation error from Bayesian models.
Against a slow concessioner, we slow-concede too. Against a fast
concessioner, we let them race to the bottom while we hold high.

Empirical caveat from ANAC research: works best in multilateral
games (3+ parties); in bilateral games against pure-exploitation
opponents (anchorers, BATNA bluffers) it can underperform because
"never concede first" loses against "never concede at all."
"""
from __future__ import annotations

from typing import Optional, Tuple, List

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

from b2b_opponents import B2BBase


class MiCROAgent(B2BBase):
    """Minimal-Concession Reciprocal. Opens at the top of our utility
    space, then mirrors the opponent's per-round concession exactly."""

    # Initial aspiration — top of our utility, leaving 1ε for ties.
    _INITIAL_ASPIRATION = 0.97

    # Look-back window for opponent concession measurement.
    _LOOKBACK = 2

    # Floor delta: never concede below `reservation + _FLOOR_DELTA`
    # before deadline. At deadline, accept anything above reservation.
    _FLOOR_DELTA = 0.05

    # Pre-deadline windfall: if an offer beats this, take it even
    # before our aspiration has descended that far.
    _ACCEPT_THRESHOLD = 0.95
    _LATE_T = 0.85

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aspiration: float = self._INITIAL_ASPIRATION

    def _opponent_concession(self) -> float:
        """How much utility (in our space) has the opponent conceded
        across their last K offers? Returns 0.0 if K offers haven't
        been observed yet — in that case, we don't concede either."""
        if len(self._opp_offers) < self._LOOKBACK + 1:
            return 0.0
        recent_utils = [self._my_util(o)
                        for o in self._opp_offers[-self._LOOKBACK - 1:]]
        # Concession = improvement in OUR utility from their offers
        # over the lookback window.
        delta = recent_utils[-1] - recent_utils[0]
        return max(0.0, float(delta))

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()

        # Reservation value (BATNA in our utility space).
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        floor = rv + self._FLOOR_DELTA

        # Synchronize concession with opponent's most recent move.
        delta = self._opponent_concession()
        self._aspiration = max(floor, self._aspiration - delta)

        offer = self._outcome_at_util(self._aspiration)
        if offer is not None:
            self._my_offers.append(offer)
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)

        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        u = self._my_util(offer)
        t = state.relative_time

        # Late-game: accept anything reasonably above reservation
        # (don't walk away into 0 utility).
        if t >= self._LATE_T:
            if u >= rv + self._FLOOR_DELTA:
                return ResponseType.ACCEPT_OFFER
            return ResponseType.REJECT_OFFER

        # Mid-game: accept if at or above current aspiration (which
        # tracks our concession schedule).
        if u >= self._aspiration:
            return ResponseType.ACCEPT_OFFER

        # Early/mid-game with offer above the early threshold (rare)
        # — take it as a windfall.
        if u >= self._ACCEPT_THRESHOLD:
            return ResponseType.ACCEPT_OFFER

        return ResponseType.REJECT_OFFER

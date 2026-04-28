"""
SNHP variant with an Aspiration / deterministic-opponent detector.

Empirical motivation: in the long-horizon (n=100) tournament, vanilla SNHP
loses 0.36 utility head-to-head to AspirationNegotiator (SNHP gets 0.367,
Aspiration gets 0.722). The gap is concentrated in this single matchup
and isn't fixed by any unilateral parameter twist.

Mechanism: SNHP's Bayesian opponent inference is calibrated for stochastic
strategic opponents. AspirationNegotiator concedes deterministically along
a monotone schedule with no hidden state. SNHP's adaptive concession reads
the slow concession as "patient, hard to budge" and over-corrects, missing
deals → must-deal penalties accrue.

Fix: detect deterministic monotone concession from the opponent's offer
trajectory, then switch to "hold out and accept late" — which is the best
response against a known concession schedule. Deterministic opponents are
exploitable *because* they're deterministic; SNHP just wasn't recognizing
the pattern.
"""
from __future__ import annotations

import statistics

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from negmas.sao import SAOState, ResponseType  # noqa: E402

from negmas_agent import SNHPAgent  # noqa: E402


class SNHPWithAspirationDetector(SNHPAgent):
    """
    Wraps SNHP with a deterministic-opponent detector. When the opponent's
    offer trajectory looks like a monotone concession schedule (low
    first-difference variance), we hold out aggressively and accept only
    in the late game when the opponent has conceded to ~reservation.

    All other matchups fall through to the parent SNHP behavior — the
    detector only changes behavior in a narrow regime where parent SNHP
    is provably losing.
    """

    # Defaults; the live values are read via _tp() so Optuna can tune them.
    # _DET_MIN_OBS stays a class constant — it's an integer pre-condition,
    # not a continuous knob.
    _DET_MIN_OBS = 3

    @property
    def _det_max_diff_std(self) -> float:
        return self._tp("det_max_diff_std", 0.025)

    @property
    def _det_min_pos_fraction(self) -> float:
        return self._tp("det_min_pos_fraction", 0.7)

    @property
    def _det_hold_until_t(self) -> float:
        return self._tp("det_hold_until_t", 0.85)

    @property
    def _det_bid_target_initial(self) -> float:
        return self._tp("det_bid_target_initial", 0.85)

    @property
    def _det_bid_target_final(self) -> float:
        return self._tp("det_bid_target_final", 0.65)

    @property
    def _det_target_floor_margin(self) -> float:
        return self._tp("det_target_floor_margin", 0.30)

    @property
    def _det_early_accept_margin(self) -> float:
        return self._tp("det_early_accept_margin", 0.40)

    def _detection_cache_key(self) -> int:
        """Identity of the current detection input — number of opponent
        offers observed. Increases monotonically; never decreases mid-session."""
        return len(self.opponent_model.opponent_offers)

    def _is_deterministic_opponent(self) -> bool:
        """Memoized detection. The result depends only on the opponent's
        offer history — same key, same answer — so we cache per session."""
        key = self._detection_cache_key()
        cached = getattr(self, "_det_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        result = self._compute_detection()
        self._det_cache = (key, result)
        return result

    def _compute_detection(self) -> bool:
        offers = list(self.opponent_model.opponent_offers)
        if len(offers) < self._DET_MIN_OBS:
            return False
        utils = []
        for o in offers:
            try:
                u = self.ufun(o)
            except (TypeError, ValueError, AttributeError):
                continue
            if u is not None:
                utils.append(float(u))
        if len(utils) < self._DET_MIN_OBS:
            return False
        diffs = [utils[i + 1] - utils[i] for i in range(len(utils) - 1)]
        if not diffs:
            return False
        positive = sum(1 for d in diffs if d > -0.005)
        if positive < self._det_min_pos_fraction * len(diffs):
            return False
        if len(diffs) > 1 and statistics.stdev(diffs) > self._det_max_diff_std:
            return False
        return utils[-1] - utils[0] > 0.02

    def _scored_outcomes(self) -> list[tuple[float, object]]:
        """Cache the (utility, outcome) list per session — outcome space
        and ufun are static so a single eval is enough."""
        cached = getattr(self, "_scored_outcomes_cache", None)
        if cached is not None:
            return cached
        scored: list[tuple[float, object]] = []
        for o in (self.nmi.outcomes or []):
            try:
                v = self.ufun(o)
                u = float(v) if v is not None else 0.0
            except (TypeError, ValueError, AttributeError):
                u = 0.0
            scored.append((u, o))
        self._scored_outcomes_cache = scored
        return scored

    def _bid_target(self, state: SAOState) -> float:
        rv = float(self.ufun.reserved_value or 0.0)
        floor = rv + self._det_target_floor_margin
        t = float(getattr(state, "relative_time", 0.0))
        initial = self._det_bid_target_initial
        final = self._det_bid_target_final
        decayed = initial - (initial - final) * t
        return max(decayed, floor)

    def propose(self, state: SAOState):
        if not self._is_deterministic_opponent():
            return super().propose(state)
        scored = self._scored_outcomes()
        if not scored:
            return super().propose(state)
        target = self._bid_target(state)
        at_or_above = [s for s in scored if s[0] >= target - 1e-6]
        if at_or_above:
            return min(at_or_above, key=lambda s: s[0] - target)[1]
        return max(scored, key=lambda s: s[0])[1]

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        if not self._is_deterministic_opponent():
            return super().respond(state, source)
        offer = state.current_offer
        if offer is None:
            return ResponseType.REJECT_OFFER
        rv = float(self.ufun.reserved_value or 0.0)
        try:
            v = self.ufun(offer)
            u = float(v) if v is not None else 0.0
        except (TypeError, ValueError, AttributeError):
            u = 0.0
        t = float(getattr(state, "relative_time", 0.0))
        if t < self._det_hold_until_t:
            return ResponseType.ACCEPT_OFFER if u >= rv + self._det_early_accept_margin \
                else ResponseType.REJECT_OFFER
        return ResponseType.ACCEPT_OFFER if u >= rv else ResponseType.REJECT_OFFER

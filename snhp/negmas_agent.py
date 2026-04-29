"""
SNHP NegMAS Agent — Von Neumann ZOPA-Rubinstein Composite for ANAC.

This module wraps the SNHP negotiation engine into a NegMAS SAONegotiator
for use in the Automated Negotiation League (ANL) / ANAC competition.

Architecture:
    1. NegMAS provides: utility function, opponent offers, time pressure
    2. SNHP provides: Rubinstein surplus splitting, Von Neumann minimax hedge,
       Thompson Sampling cross-session learning, Bayesian opponent modeling

The agent translates between NegMAS's structured offer protocol and
SNHP's game-theoretic decision engine.

Usage:
    from negmas_agent import SNHPAgent
    
    mech = SAOMechanism(issues=issues, n_steps=100)
    agent = SNHPAgent(name="snhp_seller")
    mech.add(agent, ufun=seller_ufun)
"""

import sys
import os
import math
import numpy as np
from typing import Optional, List, Tuple, Dict, Any
from collections import defaultdict, deque

# NegMAS imports
from negmas.sao import SAONegotiator, SAOState, ResponseType
from negmas.outcomes import Outcome

# SNHP core math imports
_snhp_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_snhp_dir, "core_math"))

from rubinstein import compute_discount_factor, rubinstein_equilibrium

# Playbook composition for the exploitation-mode rollout. When mode is
# OFF (the default), `compose_belief_weighted_params` returns the HONEST
# defaults — current SNHP behavior, no change in production. When mode
# is ALL or *_ONLY (set by the ablation matrix runner), the per-call
# parameters are blended from per-type playbooks weighted by the
# OpponentModel's belief vector. See snhp/playbooks.py for the spec
# and the plan file for the design rationale.
from snhp.playbooks import (
    compose_belief_weighted_params as _pb_compose,
    playbook_mode as _pb_mode,
)


# ═══════════════════════════════════════════════════
#  Bayesian Opponent Model
# ═══════════════════════════════════════════════════

class OpponentModel:
    """
    Bayesian opponent utility estimator with type classification.
    
    Multi-issue aware: tracks opponent behavior in UTILITY SPACE,
    not in any specific issue's value space. Works identically for
    single-issue (price) and N-issue (price+delivery+warranty+...) negotiations.
    
    Classifies opponents into four archetypes:
    - BOULWARE: Patient, barely concedes until near deadline
    - CONCEDER: Concedes early, loses surplus
    - MIRROR: Tit-for-tat style, mirrors our concession rate
    - RANDOM: No clear pattern
    """
    
    # Opponent type enum
    UNKNOWN = "unknown"
    BOULWARE = "boulware"
    CONCEDER = "conceder"
    MIRROR = "mirror"
    RANDOM = "random"
    
    def __init__(self, ufun=None):
        self.ufun = ufun  # Our utility function — evaluates opponent offers in our space
        self.opponent_offers: List[Tuple] = []
        self.opponent_times: List[float] = []
        
        # Track UTILITIES of opponent offers (issue-agnostic)
        self._opp_utilities: List[float] = []  # utility of their offers TO US
        
        # Our own offers and their utilities (for mirror detection)
        self.our_offers: List[Tuple] = []
        self._our_utilities: List[float] = []
        
        # Utility-based concession tracking
        self._concession_velocities: List[float] = []  # utility deltas per step
        
        # Bayesian estimate of opponent's final utility offer (to us)
        self._reservation_estimate: float = 0.5
        self._reservation_confidence: float = 0.1
        
        # Type classification
        self._type: str = self.UNKNOWN
        self._type_confidence: float = 0.0
        
        # Mirror correlation
        self._mirror_correlation: float = 0.0
    
    def observe(self, offer: Tuple, relative_time: float):
        """Record an opponent offer and update beliefs in utility space."""
        self.opponent_offers.append(offer)
        self.opponent_times.append(relative_time)
        
        # Evaluate offer in OUR utility space (issue-agnostic)
        util = 0.0
        if self.ufun is not None:
            u = self.ufun(offer)
            util = float(u) if u is not None else 0.0
        self._opp_utilities.append(util)
        
        # Track utility-based concession velocity
        if len(self._opp_utilities) >= 2:
            # Opponent concedes when OUR utility of their offers INCREASES
            delta = self._opp_utilities[-1] - self._opp_utilities[-2]
            self._concession_velocities.append(abs(delta))
        
        self._update_reservation_estimate(relative_time)
        self._classify_opponent(relative_time)
        self._detect_mirror()
    
    def record_our_offer(self, offer: Tuple):
        """Record our own offer for mirror detection."""
        self.our_offers.append(offer)
        if self.ufun is not None:
            u = self.ufun(offer)
            self._our_utilities.append(float(u) if u is not None else 0.0)
        else:
            self._our_utilities.append(0.0)
    
    def _update_reservation_estimate(self, relative_time: float):
        """
        Estimate opponent's final utility offer using polynomial fit on
        the utility trajectory. Issue-agnostic: works on scalar utilities.
        """
        if len(self._opp_utilities) < 3:
            return
        
        utils = np.array(self._opp_utilities, dtype=float)
        times = np.array(self.opponent_times, dtype=float)
        
        if relative_time < 0.05:
            return
        
        # Polynomial fit on utility trajectory (degree 2)
        try:
            degree = min(2, len(utils) - 1)
            coeffs = np.polyfit(times, utils, degree)
            poly = np.poly1d(coeffs)
            projected_final = float(poly(1.0))
        except (np.linalg.LinAlgError, ValueError):
            projected_final = float(utils[-1])
        
        projected_final = max(0.0, min(1.0, projected_final))
        
        alpha = min(0.6, len(self._opp_utilities) / 15)
        self._reservation_estimate = (
            (1 - alpha) * self._reservation_estimate + 
            alpha * projected_final
        )
        self._reservation_confidence = min(0.9, len(self._opp_utilities) / 20)
    
    def _classify_opponent(self, relative_time: float):
        """
        Classify opponent into behavioral archetype based on utility concession.
        
        AGGRESSIVE: Classifies after just 3 observations. Accepts misidentification
        risk in exchange for speed — in 10-step games, waiting for 8 observations
        means 80% of the game is over before we adapt.
        
        Issue-agnostic: uses utility trajectory, not raw issue values.
        - BOULWARE: < 10% of total utility concession in first 70% of time
        - CONCEDER: > 50% of utility concession in first 30% of time
        - MIRROR: high correlation with our utility sequence (detected separately)
        - RANDOM: high variance in concession velocity
        """
        if len(self._opp_utilities) < 3:
            return
        

        utils = self._opp_utilities
        n = len(utils)
        total_concession = abs(utils[-1] - utils[0])  # total utility movement
        
        # ─── DUAL-SIGNAL CLASSIFICATION ───
        # Signal 1: ABSOLUTE LEVEL — where are their offers in our utility space?
        # A cooperator's offers will reach meaningful utility (>0.15) eventually.
        # A hardliner's offers stay below 0.10-0.15 throughout.
        recent_avg = float(np.mean(utils[-min(3, n):]))  # last 3 offers average
        best_recent = float(max(utils[-min(3, n):]))
        
        # Signal 2: TREND — are their offers getting better for us?
        # Linear regression slope on utility trajectory.
        # Use specific exceptions so unexpected errors propagate (the bare
        # except was hiding LinAlgError → silent slope=0 → misclassifying
        # conceders as hardliners).
        if n >= 3:
            times = np.array(self.opponent_times[:n], dtype=float)
            u_arr = np.array(utils[:n], dtype=float)
            try:
                slope = float(np.polyfit(times, u_arr, 1)[0])
            except (np.linalg.LinAlgError, ValueError, TypeError):
                # Fall back to total_concession over time-span as a coarse slope
                span = max(1e-6, float(times[-1] - times[0]))
                slope = total_concession / span
        else:
            slope = total_concession
        
        # Velocity variance for RANDOM detection
        if len(self._concession_velocities) > 2:
            vel_std = float(np.std(self._concession_velocities))
            vel_mean = float(np.mean(self._concession_velocities))
            cv = vel_std / max(vel_mean, 0.001)

            if cv > 2.5 and abs(slope) < 0.05:
                self._type = self.RANDOM
                self._type_confidence = min(0.75, n / 10)
                return

        # Force-misclassify hooks for the validation framework's stress
        # cells. SNHP_FORCE_MISCLASS=RANDOM emits a uniform-random label;
        # ADVERSARIAL emits the WORST playbook for the true type. The
        # adversarial mode requires `self._true_type` set externally
        # (the b2b_round_robin runner sets it from OPPONENT_TYPE_TAGS).
        # When unset (production) this branch is a no-op.
        force = os.environ.get("SNHP_FORCE_MISCLASS")
        if force:
            import random as _r
            types = [self.BOULWARE, self.CONCEDER, self.MIRROR, self.RANDOM]
            if force == "RANDOM":
                self._type = _r.choice(types)
                self._type_confidence = 0.85
                return
            if force == "ADVERSARIAL" and getattr(self, "_true_type", None):
                # Worst playbook map: against true=BOULWARE, predicting
                # CONCEDER is catastrophic (we concede into a wall). Map
                # is symmetric in the sense that each true-type has a
                # canonical "worst miss". Derived from the cost matrix
                # in the plan's Section 3 (von Neumann perspective).
                worst = {
                    self.BOULWARE: self.CONCEDER,   # concede into wall
                    self.CONCEDER: self.BOULWARE,   # over-firm where we'd win
                    self.MIRROR:   self.CONCEDER,   # race to bottom against reflector
                    self.RANDOM:   self.BOULWARE,   # over-firm against noise
                }.get(self._true_type, self.UNKNOWN)
                self._type = worst
                self._type_confidence = 0.85
                return
        
        # ─── CLASSIFICATION DECISION ───
        # BOULWARE: recent offers are very low AND no positive trend
        if recent_avg < 0.12 and slope < 0.05 and n >= 4:
            self._type = self.BOULWARE
            self._type_confidence = min(0.85, n / 10)
        elif recent_avg < 0.08 and n >= 3:
            # Very low offers regardless of trend — hardliner
            self._type = self.BOULWARE  
            self._type_confidence = min(0.7, n / 10)
        elif slope > 0.15 or (recent_avg > 0.20 and slope > 0):
            # Clear positive trend OR good absolute level with positive trend
            self._type = self.CONCEDER
            self._type_confidence = min(0.85, n / 10)
        elif total_concession > 0.10 and slope > 0:
            # Moderate concession with positive direction
            self._type = self.CONCEDER
            self._type_confidence = min(0.6, n / 12)
        elif best_recent > 0.15 and slope >= 0:
            # At least some decent offers — probably cooperative
            self._type = self.CONCEDER
            self._type_confidence = min(0.5, n / 12)
        else:
            # Unclear — stay unknown, don't trigger capitulation
            self._type = self.UNKNOWN
            self._type_confidence = min(0.3, n / 15)
        
    
    def _detect_mirror(self):
        """
        Detect TFT-like mirroring by correlating utility trajectories.
        
        Issue-agnostic: uses utility deltas instead of price deltas.
        TFT mirrors concession magnitude with 1-step lag.
        
        CONSERVATIVE: requires correlation > 0.85 AND similar concession
        magnitude to avoid false positives from monotonic concession curves
        that naturally correlate.
        """
        if len(self._our_utilities) < 5 or len(self._opp_utilities) < 5:
            return
        
        # Don't override confident non-mirror classification
        if self._type in (self.BOULWARE, self.CONCEDER, self.RANDOM) and self._type_confidence > 0.6:
            return
        
        # Align: opponent reacts to our previous offer
        n = min(len(self._our_utilities), len(self._opp_utilities)) - 1
        if n < 4:
            return
        
        our_utils = np.array(self._our_utilities[:n], dtype=float)
        opp_utils = np.array(self._opp_utilities[1:n+1], dtype=float)
        
        # Correlation on CHANGES in utility
        our_deltas = np.diff(our_utils)
        opp_deltas = np.diff(opp_utils)
        
        if len(our_deltas) < 3:
            return
        
        our_std = np.std(our_deltas)
        opp_std = np.std(opp_deltas)
        
        if our_std < 0.001 or opp_std < 0.001:
            self._mirror_correlation = 0.0
            return
        
        corr = np.corrcoef(our_deltas, opp_deltas)[0, 1]
        if np.isnan(corr):
            corr = 0.0
        
        self._mirror_correlation = float(corr)
        
        # STRICT mirror detection:
        # 1. Very high correlation (>0.85, not just 0.6)
        # 2. Similar concession magnitude (ratio within 3x)
        # Both conditions must hold to distinguish true TFT from
        # coincidentally correlated monotonic concession curves.
        magnitude_ratio = max(our_std, opp_std) / min(our_std, opp_std)
        
        if abs(self._mirror_correlation) > 0.85 and magnitude_ratio < 3.0:
            self._type = self.MIRROR
            self._type_confidence = max(self._type_confidence, 
                                        min(0.9, abs(self._mirror_correlation)))
    
    @property
    def estimated_reservation(self) -> float:
        return self._reservation_estimate
    
    @property
    def confidence(self) -> float:
        return self._reservation_confidence
    
    @property
    def concession_rate(self) -> float:
        if len(self._concession_velocities) < 1:
            return 0.0
        return float(np.mean(self._concession_velocities))
    
    @property
    def is_hardliner(self) -> bool:
        return self.concession_rate < 0.5 and len(self.opponent_offers) > 5
    
    @property
    def opponent_type(self) -> str:
        return self._type
    
    @property
    def is_mirror(self) -> bool:
        return self._type == self.MIRROR and self._type_confidence > 0.4

    @property
    def type_confidence(self) -> float:
        """Confidence in the current opponent type classification, in [0, 1].
        Distinct from `confidence` (which surfaces reservation_confidence).
        Used by the playbook composition to gate exploit weight."""
        return float(self._type_confidence)

    def belief_vector(self) -> Dict[str, float]:
        """Probability distribution over opponent types, summing to 1.0.

        Used by exploitation-mode action composition: the agent computes
        a belief-weighted blend of per-type playbooks rather than dispatching
        on the argmax type. Per Nash's critique in the plan: discrete
        argmax is a step function over belief space — opponents can sit
        on the boundary to attack. Continuous blending is robust.

        Construction: assigned-type gets `type_confidence` mass; the
        remaining `1 − type_confidence` falls to UNKNOWN. This keeps the
        residual on the non-exploitative HONEST playbook, so when the
        classifier is uncertain we behave like the equilibrium-honest
        default.
        """
        types = [self.BOULWARE, self.CONCEDER, self.MIRROR, self.RANDOM, self.UNKNOWN]
        v = {t: 0.0 for t in types}
        c = max(0.0, min(1.0, float(self._type_confidence)))
        if self._type in v and self._type != self.UNKNOWN:
            v[self._type] = c
            v[self.UNKNOWN] = 1.0 - c
        else:
            v[self.UNKNOWN] = 1.0
        return v

    def summary(self) -> Dict[str, Any]:
        return {
            "n_offers_observed": len(self.opponent_offers),
            "estimated_reservation": round(self._reservation_estimate, 2),
            "confidence": round(self._reservation_confidence, 3),
            "concession_rate": round(self.concession_rate, 3),
            "is_hardliner": self.is_hardliner,
            "type": self._type,
            "type_confidence": round(self._type_confidence, 3),
            "mirror_correlation": round(self._mirror_correlation, 3),
        }


# ═══════════════════════════════════════════════════
#  Cross-Session Learning (Thompson Sampling)
# ═══════════════════════════════════════════════════

class CrossSessionMemory:
    """
    Persistent memory across negotiations within a tournament.

    Thompson Sampling bandits keyed by (opponent_type, role) — buyer-side
    and seller-side optimal aggression are different (e.g. a Boulware seller
    requires harder-conceding aggression to close than a Boulware buyer),
    so pooling outcomes across roles corrupts both posteriors.

    Roles: "seller" (we propose first, ufun rewards high price-index) and
    "buyer" (we propose second, ufun rewards low price-index). Role default
    is "unknown" for backward-compat with callers that haven't been updated.
    """

    TYPES = ["unknown", "boulware", "conceder", "mirror", "random"]
    ROLES = ["unknown", "seller", "buyer"]

    def __init__(self):
        self.deal_results: List[Dict] = []
        self.arms = np.linspace(0.3, 0.9, 7)
        self._bandits = {}
        for t in self.TYPES:
            for r in self.ROLES:
                self._bandits[(t, r)] = {
                    "successes": np.ones(7) * 2.0,
                    "failures": np.ones(7) * 2.0,
                    "profits": np.zeros(7),
                    "counts": np.zeros(7),
                }

        self.rng = np.random.default_rng(42)

    def _key(self, opponent_type: str, role: str) -> Tuple[str, str]:
        if (opponent_type, role) not in self._bandits:
            return ("unknown", "unknown")
        return (opponent_type, role)

    def sample_aggression(self, opponent_type: str = "unknown",
                          role: str = "unknown") -> Tuple[float, int]:
        """Thompson Sampling: sample aggression from posterior for (opp_type, role)."""
        bandit = self._bandits[self._key(opponent_type, role)]

        sampled_rates = np.array([
            self.rng.beta(bandit["successes"][i], bandit["failures"][i])
            for i in range(len(self.arms))
        ])

        mean_profits = np.where(
            bandit["counts"] > 0,
            bandit["profits"] / np.maximum(bandit["counts"], 1),
            0.5
        )

        scores = sampled_rates * mean_profits
        best = int(np.argmax(scores))
        return float(self.arms[best]), best

    def update(self, arm_index: int, deal_closed: bool, utility: float,
               opponent_type: str = "unknown", role: str = "unknown"):
        """Update posterior after a negotiation for (opp_type, role)."""
        bandit = self._bandits[self._key(opponent_type, role)]

        if deal_closed:
            bandit["successes"][arm_index] += 1
            bandit["profits"][arm_index] += utility
            bandit["counts"][arm_index] += 1
        else:
            bandit["failures"][arm_index] += 1

        # Also update the role-matched "unknown" cold-start pool with partial
        # weight so a never-seen opponent type can warm-start from same-role
        # outcomes. Don't pool across roles (that's the bug we just fixed).
        if opponent_type != "unknown":
            glob = self._bandits[("unknown", role if role in ("seller", "buyer") else "unknown")]
            if deal_closed:
                glob["successes"][arm_index] += 0.3
                glob["profits"][arm_index] += utility * 0.3
                glob["counts"][arm_index] += 0.3
            else:
                glob["failures"][arm_index] += 0.3
    
    @property
    def n_sessions(self) -> int:
        return len(self.deal_results)


# ═══════════════════════════════════════════════════
#  Main Agent
# ═══════════════════════════════════════════════════

# Module-level cross-session memory (persists across negotiations in a tournament)
_global_memory = CrossSessionMemory()

# Module-level tuning params (set by Optuna tuner, None = use defaults)
_TUNE_PARAMS: dict = None


def reset_global_memory() -> None:
    """Reset _global_memory to a fresh instance.

    Tournament harnesses (Optuna trials, ablation cells) call this between
    independent runs so Thompson Sampling posteriors don't leak from one
    trial to the next. Without it, trial N+1 inherits biased arm posteriors
    from trial N — a major source of the +26/-23 reproducibility gap on
    paired-seed Elo deltas.
    """
    global _global_memory
    _global_memory = CrossSessionMemory()


class SNHPAgent(SAONegotiator):
    """
    SNHP Agent for NegMAS/ANAC.
    
    Combines:
    1. Von Neumann ZOPA-Rubinstein surplus splitting
    2. Minimax hedge based on opponent model confidence
    3. Within-session Bayesian opponent modeling
    4. Cross-session Thompson Sampling adaptation
    5. Deadline-aware dynamic patience
    
    The agent's strategy differs from standard ANAC approaches:
    - No time-dependent concession curve (uses Rubinstein equilibrium instead)
    - No explicit opponent type classification (uses continuous Bayesian update)
    - Cross-session memory (learns from tournament history)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opponent_model = OpponentModel()  # Will be re-created with ufun in on_negotiation_start
        self.memory = _global_memory
        self._my_best: Optional[Tuple] = None
        self._my_worst: Optional[Tuple] = None
        self._sorted_outcomes: Optional[List[Tuple]] = None
        self._my_offers: List[Tuple] = []
        self._my_utilities: List[float] = []  # track our utility trajectory
        self._aggression: float = 0.6
        self._arm_index: int = 3
        self._initialized: bool = False
        self._last_target_utility: float = 0.5
        self._detected_opp_type: str = "unknown"
        
        # === Mixed Strategy State ===
        self._running_aspiration: float = 0.90  # tracks actual aspiration as running state
        self._oscillation_phase: float = 0.0    # random phase per negotiation
        self._burst_fired: bool = False          # one burst per negotiation
        # Per-agent RNG. Initialized unseeded here; on_negotiation_start
        # re-seeds it deterministically from a name+role+nmi-id mix so two
        # tournaments with seed_offset=0 produce byte-identical agent
        # behavior. Without this re-seeding, multiprocessing workers
        # inherit different OS entropy and Optuna trials can't be compared.
        self._rng = np.random.default_rng()
        
        # === Preference Probing (Poisoned Wine Encoding) ===
        self._probe_offers: List[Tuple] = []     # pre-computed diagnostic probes
        self._probe_phase: bool = True           # in probing phase?
        self._n_probes: int = 0                  # probes sent so far
        self._inferred_opp_weights: Optional[Dict[int, float]] = None  # learned weights per issue
        
        # === Zeuthen Concession + Reciprocity (Von Neumann Fixes) ===
        self._my_concession_total: float = 0.0     # cumulative concession by us
        self._opp_concession_total: float = 0.0    # cumulative concession by opponent
        self._zeuthen_aspiration: float = 0.55      # Zeuthen-modulated aspiration (realistic for asymmetric B2B)
        self._last_opp_utility_for_us: float = 0.0  # last opponent offer's utility to us
        self._reciprocity_frozen: bool = False       # freeze flag
        self._damage_control: bool = False           # non-convergence → deal-closing mode
        
        # === Pareto Landscape Calibration ===
        # Computed at init from the actual ufun, replaces fixed aspiration constants.
        self._fair_split_util: float = 0.50    # median of our utility distribution
        self._ufun_p75: float = 0.75           # 75th percentile
        self._ufun_p25: float = 0.25           # 25th percentile
    
    def on_negotiation_start(self, state):
        """Called when a new negotiation begins."""
        super().on_negotiation_start(state)
        # OpponentModel needs ufun — passed after NegMAS assigns it
        self.opponent_model = OpponentModel(ufun=self.ufun)
        self._my_offers = []
        self._my_utilities = []
        self._initialized = False
        self._sorted_outcomes = None
        # Initialize role detection state BEFORE sampling aggression so the
        # _snhp_role property can read _is_first_mover safely.
        self._is_first_mover: Optional[bool] = None
        self._aggression_role_sampled: Optional[str] = None

        # BUG FIX (2026-04-29): seed _rng deterministically per negotiation.
        # Use zlib.crc32 (cross-process-stable) on a string mix of the
        # agent's name + n_steps + a fixed salt. Python's built-in hash()
        # is randomized via PYTHONHASHSEED → different per process — using
        # it for seeding broke reproducibility.
        import zlib
        seed_mix_str = (
            f"{getattr(self, 'name', 'snhp')}|"
            f"{int(getattr(self.nmi, 'n_steps', 10) or 10)}|"
            f"snhp_v1_seed_salt"
        )
        seed_mix = zlib.crc32(seed_mix_str.encode()) & 0x7fffffff
        self._rng = np.random.default_rng(seed_mix)

        # Role-agnostic prior; will be re-sampled with the detected role on
        # the first propose() call.
        self._aggression, self._arm_index = self.memory.sample_aggression(role=self._snhp_role)

        # Mixed strategy: random phase prevents opponents from learning our timing
        self._running_aspiration = 0.90
        self._oscillation_phase = self._rng.uniform(0, 2 * np.pi)
        self._burst_fired = False

        # Reset probing state
        self._probe_offers = []
        self._probe_phase = True
        self._n_probes = 0
        self._inferred_opp_weights = None

        # Reset Zeuthen/reciprocity state
        self._my_concession_total = 0.0
        self._opp_concession_total = 0.0
        self._zeuthen_aspiration = 0.55
        self._last_opp_utility_for_us = 0.0
        self._reciprocity_frozen = False
        self._damage_control = False

        # Pareto landscape will be recalibrated in _ensure_initialized
        self._fair_split_util = 0.50
        self._ufun_p75 = 0.75
        self._ufun_p25 = 0.25

        # Damage-control state was previously set only inside the DC branch,
        # which meant it leaked across negotiations in a tournament. Always
        # reset so each session starts clean.
        self._in_capitulation = False
        self._dc_proposal_counter = 0
        # _is_first_mover already initialized above (before aggression sample)
        # so the role-aware bandit lookup can read it.

        # Commitment margin (see _commitment_margin property below) is read
        # through _tp() so it picks up the role-aware tuned value once
        # _is_first_mover is set on the first propose() call.
    
    @property
    def _snhp_role(self) -> str:
        """
        Role tag for cross-session memory & role-aware tuning. Maps the
        first-mover detection state to the string keys CrossSessionMemory
        uses ("seller" | "buyer" | "unknown").
        """
        if self._is_first_mover is True:
            return "seller"
        if self._is_first_mover is False:
            return "buyer"
        return "unknown"

    @property
    def _commitment_margin(self) -> float:
        """
        Schelling commitment margin: refuse offers within this
        much of BATNA, even in damage control / late-game emergency. Read
        through the role-aware _tp() so seller and buyer can have separate
        tuned values.
        """
        return self._pb_param('commitment_margin', 0.03)

    def _tp(self, name: str, default: float) -> float:
        """
        Read a tunable parameter. Role-aware lookup:
          1. If _is_first_mover is True (we play seller), look up seller_<name>
          2. If _is_first_mover is False (we play buyer), look up buyer_<name>
          3. Fallback: bare <name> (backward compat with old single-role tunes)
          4. Final fallback: hardcoded `default`

        This lets Optuna tune two parameter sets (seller and buyer) and have
        the agent automatically apply the right one based on detected role.
        """
        if _TUNE_PARAMS is None:
            return default
        # Role-prefixed lookup
        if self._is_first_mover is True:
            prefixed = f"seller_{name}"
            if prefixed in _TUNE_PARAMS:
                return _TUNE_PARAMS[prefixed]
        elif self._is_first_mover is False:
            prefixed = f"buyer_{name}"
            if prefixed in _TUNE_PARAMS:
                return _TUNE_PARAMS[prefixed]
        # Backward-compat: non-prefixed key
        if name in _TUNE_PARAMS:
            return _TUNE_PARAMS[name]
        return default

    # Mapping from `_tp()`-style param names to the playbook spec keys
    # used by snhp/playbooks.py. Keys not in this map fall back to `_tp()`.
    _PLAYBOOK_PARAM_MAP = {
        "aspiration_start":   "asp_start",
        "aspiration_floor":   "asp_floor",
        "accept_early_bar":   "accept_early_bar",
        "commitment_margin":  "commitment_margin",
        "concession_cap_b2b": "concession_cap",
    }

    def _pb_param(self, name: str, default: float) -> float:
        """
        Playbook-aware parameter lookup. When exploitation mode is OFF
        (the default), defers to `_tp()` for the existing role-aware
        lookup. When ON, returns the belief-weighted blended value from
        the cached playbook for this propose/respond call.

        The agent caches the composed playbook on each propose/respond
        entry (`self._cached_playbook`) so multiple lookups within one
        call don't recompose. The cache is invalidated on every call.
        """
        if _pb_mode() == "OFF":
            return self._tp(name, default)
        if name not in self._PLAYBOOK_PARAM_MAP:
            return self._tp(name, default)
        if not getattr(self, "_cached_playbook", None):
            self._refresh_playbook()
        return self._cached_playbook[self._PLAYBOOK_PARAM_MAP[name]]

    def _refresh_playbook(self) -> None:
        """Recompose the playbook for the current opponent belief.
        Called at the top of propose() and respond() and any other entry
        where the belief may have updated."""
        if self.opponent_model is None:
            self._cached_playbook = None
            return
        belief = self.opponent_model.belief_vector()
        type_conf = self.opponent_model.type_confidence
        self._cached_playbook = _pb_compose(belief, type_conf)

    def _ensure_initialized(self):
        """Lazy init: enumerate outcomes once ufun is available."""
        if self._initialized:
            return
        self._initialized = True
        
        if self.ufun is None or self.nmi is None:
            return
        
        outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=1000))
        if not outcomes:
            return
        
        utilities = []
        for o in outcomes:
            u = self.ufun(o)
            if u is not None:
                utilities.append((o, float(u)))
        
        if not utilities:
            return
        
        utilities.sort(key=lambda x: x[1], reverse=True)
        self._sorted_outcomes = utilities
        self._my_best = utilities[0][0]
        self._my_worst = utilities[-1][0]
        
        # === Self-Ufun Landscape Calibration ===
        # Instead of reading opponent's ufun (unfair), calibrate from our OWN
        # utility distribution. Median utility tells us about the landscape:
        # - Low median (~0.40) → zero-sum, be conservative
        # - High median (~0.55) → surplus exists, aim higher
        all_utils = [u for _, u in utilities]
        self._fair_split_util = float(np.median(all_utils))
        self._ufun_p75 = float(np.percentile(all_utils, 75))
        self._ufun_p25 = float(np.percentile(all_utils, 25))
        
        # Pre-compute diagnostic probes for preference elicitation
        self._generate_probes()
    
    # ─── Preference Probing (Poisoned Wine Encoding) ───────────
    
    def _generate_probes(self):
        """
        Myerson information-design probes.

        Replaces the older hardcoded-mask approach with a principled
        information-design selection: pick the K offers (within our target
        utility band) whose RESPONSE will be most diagnostic of opponent
        type. The diagnostic value of an offer is approximated by the
        variance of its predicted utility-to-opponent across a Dirichlet
        prior over opponent weight vectors.

        Intuition: if all hypothesized opponent types would value an offer
        the same way, that offer's response gives no signal. If the
        hypothesized types DISAGREE about how much they value the offer,
        the response will reveal which type is closer to truth.

        After picking the highest-variance candidate, subsequent probes
        are chosen greedily to maximize a (variance × distance-to-existing-
        probes) score — preserves diagnostic value AND issue-space
        diversity.

        Mask-based fallback retained inside the conditional to avoid
        breaking when the candidate set is degenerate.
        """
        if not self._sorted_outcomes or self.ufun is None:
            return

        n_issues = len(self._sorted_outcomes[0][0]) if self._sorted_outcomes else 0
        if n_issues < 2:
            self._probe_phase = False
            return

        probe_target = self._tp('probe_target', 0.62)
        band = 0.08
        candidates = [
            (o, u) for o, u in self._sorted_outcomes
            if u >= probe_target - band and u <= probe_target + band
        ]
        if len(candidates) < 3:
            self._probe_phase = False
            return

        # ─── Info-design scoring ──────────────────────────────────────
        # Sample particles from a Dirichlet(1,1,...,1) prior over opponent
        # weights. Each particle is a hypothesized opponent weight vector.
        n_particles = 200
        rng = np.random.default_rng(42)
        particles = rng.dirichlet(np.ones(n_issues), size=n_particles)

        # Build per-issue normalization (max index across the candidate set,
        # bounded away from 0).
        issue_max = np.array([
            max(1.0, max(float(o[i]) for o, _ in candidates))
            for i in range(n_issues)
        ])

        # Approximate per-dim opponent utility from each candidate.
        # Zero-sum projection: opp_per_dim[i] = 1 - my_index_normalized[i].
        # This is a coarse approximation but adequate as a *prior* over
        # opp value structure for selecting probes; precise modeling
        # happens once real responses arrive.
        candidate_arr = np.array([list(o) for o, _ in candidates], dtype=float)
        candidate_my_normalized = candidate_arr / issue_max  # (C, D)
        candidate_opp_per_dim = 1.0 - candidate_my_normalized

        # Predicted opp utility per candidate × particle (matrix multiplication
        # over weights). Variance across particles measures disagreement.
        opp_util_pred = candidate_opp_per_dim @ particles.T  # (C, P)
        info_score = np.var(opp_util_pred, axis=1)  # (C,)

        # ─── Greedy selection ────────────────────────────────────────
        # Pick first probe by max variance; subsequent by (variance ×
        # min_distance_to_existing) to keep probes diverse in issue-space.
        n_probes = min(3, len(candidates))
        selected_idx: list[int] = []
        order = list(np.argsort(-info_score))

        # First pick: highest variance
        first = int(order[0])
        selected_idx.append(first)

        while len(selected_idx) < n_probes:
            best_idx = None
            best_combined = -np.inf
            for idx in order:
                idx = int(idx)
                if idx in selected_idx:
                    continue
                cand_vec = candidate_arr[idx]
                min_dist = min(
                    float(np.linalg.norm(cand_vec - candidate_arr[s]))
                    for s in selected_idx
                )
                # Combined: info_gain * (1 + min_distance). Avoids picking
                # near-duplicates of the first probe even if their variance
                # is similar.
                combined = info_score[idx] * (1.0 + min_dist)
                if combined > best_combined:
                    best_combined = combined
                    best_idx = idx
            if best_idx is None:
                break
            selected_idx.append(best_idx)

        self._probe_offers = [candidates[i][0] for i in selected_idx]
    
    def _infer_opponent_weights(self):
        """
        Analyze opponent counter-offers against our probes to infer their
        issue weights. The key signal: which issues does the opponent
        shift TOWARD in their counter-offers?
        
        If we sent probe A (high price, low warranty) and the opponent
        responded by moving price DOWN and warranty UP → they care about
        warranty more than price.
        
        Returns normalized weight vector as dict {issue_index: weight}.
        """
        opp_offers = self.opponent_model.opponent_offers
        if len(opp_offers) < 2 or not self._probe_offers:
            return None
        
        n_issues = len(self._probe_offers[0])
        # Track how much the opponent "pushes back" on each issue
        # Higher pushback = they care more about that issue
        issue_pushback = [0.0] * n_issues
        
        n_compared = min(len(self._probe_offers), len(opp_offers))
        for p_idx in range(n_compared):
            probe = self._probe_offers[p_idx]
            # The opponent's response to (or near) this probe
            response = opp_offers[p_idx]
            
            for i in range(n_issues):
                # How much did the opponent shift this issue from our probe?
                delta = abs(float(probe[i]) - float(response[i]))
                issue_pushback[i] += delta
        
        # Normalize to get estimated weights
        total = sum(issue_pushback)
        if total < 0.01:
            return None  # No useful signal
        
        weights = {i: issue_pushback[i] / total for i in range(n_issues)}
        return weights
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        """
        Generate a counter-offer using Von Neumann Mixed Strategy.
        
        Architecture:
        1. Game-theoretic floor (Rubinstein equilibrium)
        2. Logistic-sinusoidal concession curve (stochastic, no cliff)
        3. Exploit probes (random retractions to test opponent)
        4. Burst-and-lock (one strategic large concession)
        5. Thompson-sampled aggression tunes overall posture
        
        Key innovation: concession is a RANDOM WALK on a logistic S-curve,
        not a deterministic t^exponent decay. This:
        - Eliminates the Boulware cliff (54-step deadlock)
        - Creates timing asymmetry against mirroring opponents
        - Makes us harder to model/exploit
        """
        self._ensure_initialized()
        if self.ufun is None or self._my_best is None:
            return self._my_best

        # Detect mover order on the first propose() call. If the opponent has
        # already offered something before our first propose, we're going
        # second; otherwise we're going first. Used by the Rubinstein floor.
        if self._is_first_mover is None:
            self._is_first_mover = len(self.opponent_model.opponent_offers) == 0

        # Re-sample aggression now that the role is known so the
        # Thompson Sampling bandit reads from the right (opp_type, role)
        # posterior. on_negotiation_start sampled with role="unknown".
        if self._aggression_role_sampled != self._snhp_role:
            self._aggression, self._arm_index = self.memory.sample_aggression(role=self._snhp_role)
            self._aggression_role_sampled = self._snhp_role

        # Recompose the per-type playbook for this turn. No-op when
        # SNHP_PLAYBOOK_MODE is OFF (the production default).
        self._refresh_playbook()

        t = state.relative_time
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        
        # === Preference Probing Phase ===
        # Probes serve dual purpose in B2B: (1) gather opponent weight info
        # for logrolling, (2) establish cooperative opening at ~0.517 utility.
        # Max 2 probes to limit information cost while preserving benefits.
        should_probe = (
            self._probe_phase 
            and self._probe_offers 
            and self._n_probes < len(self._probe_offers)
            and total_steps <= 15        # B2B games only
            and t < 0.30                 # Time budget
            and self._n_probes < 2       # Max 2 probes
        )
        if should_probe:
            probe = self._probe_offers[self._n_probes]
            self._n_probes += 1
            
            # Record probe as a normal offer
            self._my_offers.append(probe)
            u = self.ufun(probe)
            self._my_utilities.append(float(u) if u is not None else 0.78)
            self._last_target_utility = float(u) if u is not None else 0.78
            self.opponent_model.record_our_offer(probe)
            
            # After sending enough probes, try to infer weights
            if self._n_probes >= 2:
                inferred = self._infer_opponent_weights()
                if inferred is not None:
                    self._inferred_opp_weights = inferred
                    self._probe_phase = False  # Exit probing, use learned weights
            
            return probe
        
        # Exit probing if we've run out of time budget
        self._probe_phase = False
        
        # Try to infer weights if we haven't yet
        if self._inferred_opp_weights is None and len(self.opponent_model.opponent_offers) >= 2:
            self._inferred_opp_weights = self._infer_opponent_weights()
        
        # === Reservation Value ===
        rv = getattr(self.ufun, 'reserved_value', None)
        if rv is None or rv == float('-inf'):
            rv = 0.0
        
        # === Rubinstein Equilibrium Floor ===
        opp_rv_util = self._estimate_opponent_reservation_utility()
        surplus = max(0.01, (1.0 - rv) - opp_rv_util)

        my_discount = 0.95
        opp_discount = max(0.90, 0.95 - self._estimate_opponent_urgency(t) * 0.1)

        # Rubinstein's formula gives the FIRST-MOVER share. SNHP claimed it
        # unconditionally before, which was correct only when added first to
        # the mechanism. When SNHP responds (added second), it's the
        # second-mover and gets 1 - first_mover_share, computed with the
        # opponent's discount in the first slot.
        if self._is_first_mover:
            rub = rubinstein_equilibrium(my_discount, opp_discount, surplus)
            my_share = rub["freelancer_share"]
        else:
            rub_swapped = rubinstein_equilibrium(opp_discount, my_discount, surplus)
            my_share = 1.0 - rub_swapped["freelancer_share"]
            rub = rub_swapped  # keep `rub` defined for downstream code that reads it
        rubinstein_floor = rv + surplus * my_share
        
        adjusted_floor = rv + surplus * min(1.0, my_share * (0.8 + 0.5 * self._aggression))
        adjusted_floor = max(adjusted_floor, rubinstein_floor)
        adjusted_floor = min(adjusted_floor, 0.90)
        
        # In short (B2B) games with multi-issue asymmetric weights,
        # the Rubinstein floor often exceeds the best feasible mutual deal.
        # Cap floor at 0.47 to stay in fair territory (Principled uses 0.45).
        # With start=0.67 and floor=0.47, range=0.20 → curve reaches ~0.55 by t=0.5.
        total_steps_check = getattr(self.nmi, 'n_steps', 100) or 100
        if total_steps_check <= 15:
            adjusted_floor = min(adjusted_floor, 0.47)
            rubinstein_floor = min(rubinstein_floor, 0.47)
        
        # === Opponent-Adaptive Resampling ===
        opp_type = self.opponent_model.opponent_type
        if opp_type != self._detected_opp_type and opp_type != OpponentModel.UNKNOWN:
            self._detected_opp_type = opp_type
            new_agg, new_arm = self.memory.sample_aggression(opp_type, role=self._snhp_role)
            self._aggression = 0.6 * self._aggression + 0.4 * new_agg
            self._arm_index = new_arm
        
        # ══════════════════════════════════════════════════
        #  HYBRID: Boulware Base + Sinusoidal Overlay
        # ══════════════════════════════════════════════════
        # Boulware patience is our biggest edge (proven 0.6775 vs Aspiration).
        # We ADD sin overlay for unpredictability, not replace the base curve.
        
        # === Step-Adaptive Strategy ===
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        opp_utils = self.opponent_model._opp_utilities
        
        if total_steps <= 15:
            # ─── B2B MODE: ZEUTHEN CONCESSION + RECIPROCITY ──
            # Philosophy: Concede when our risk of breakdown exceeds the
            # opponent's. Track reciprocity to avoid being exploited.
            # Accept any deal above reservation when time pressure rises.
            
            rv = float(self.ufun.reserved_value) if self.ufun.reserved_value else 0.0
            opp_utils = self.opponent_model._opp_utilities
            classified_type = self.opponent_model.opponent_type
            opp_conf = self.opponent_model.confidence
            
            # ─── ZEUTHEN CONCESSION PRINCIPLE ────────────────
            # Risk = (util_at_deal - util_at_current_demand) / util_at_deal
            # Concede when our risk > opponent's estimated risk.
            # This produces Pareto-optimal, individually rational outcomes.
            
            aspiration_start = self._pb_param('aspiration_start', 0.62)
            aspiration_floor = self._pb_param('aspiration_floor', 0.45)  # Above BATNA — don't give away surplus

            # === SELF-CALIBRATED ASPIRATION ===
            # Use our median utility as landscape signal.
            # Higher median → more surplus → can aim higher.
            # But cap conservatively to avoid demanding too much.
            #
            # BUG FIX (2026-04-29): only apply when playbook mode is OFF.
            # Previously this clobbered the playbook-composed asp_start
            # (capping to 0.70) for any domain where median_u > 0.52,
            # which silently neutered exploitation mode. Now: when
            # playbook mode is active, the playbook owns asp_start —
            # the calibration override is reserved for HONEST play only.
            median_u = self._fair_split_util  # actually our ufun median
            if _pb_mode() == "OFF" and median_u > 0.52:
                # Surplus round: raise start modestly, raise floor
                aspiration_start = min(0.70, median_u + 0.06)
                aspiration_floor = max(aspiration_floor, median_u - 0.10)
            
            # Calibrate Zeuthen aspiration to the new start
            if self._zeuthen_aspiration == 0.55:  # initial value
                self._zeuthen_aspiration = aspiration_start
            
            # Track opponent concessions for reciprocity
            if len(opp_utils) >= 2:
                self._opp_concession_total = abs(opp_utils[-1] - opp_utils[0])
            if len(self._my_utilities) >= 2:
                self._my_concession_total = abs(self._my_utilities[0] - self._my_utilities[-1])
            
            # Reciprocity check: freeze if we're conceding 1.5x faster
            if (len(opp_utils) >= 3 and len(self._my_utilities) >= 3
                    and self._my_concession_total > 0.03):
                asymmetry = self._my_concession_total / max(0.01, self._opp_concession_total)
                self._reciprocity_frozen = asymmetry > 1.5
            else:
                self._reciprocity_frozen = False
            
            # ─── ZEUTHEN-RAIFFA RISK FORMULA ────────────────────
            # Zeuthen (1930), formalized by Raiffa (1953):
            #   r_i = (u_i_demand - u_i_breakdown) / u_i_demand
            # Party with HIGHER risk of breakdown should concede next.
            # u_i_breakdown is each party's BATNA. u_i_demand is what they
            # get if their current proposal is accepted.
            current_demand = self._zeuthen_aspiration
            my_breakdown = float(rv) if rv is not None else 0.0
            if current_demand > my_breakdown + 1e-6:
                my_risk = (current_demand - my_breakdown) / current_demand
            else:
                my_risk = 0.0

            # Opp demand ≈ utility-to-them at their best offer; in zero-sum
            # projection this is roughly 1 - (best opp offer in our utility).
            best_opp_offer_to_us = max(opp_utils) if opp_utils else 0.0
            opp_demand_estimate = max(0.05, 1.0 - best_opp_offer_to_us)
            opp_breakdown_estimate = self._estimate_opponent_reservation_utility()
            if opp_demand_estimate > opp_breakdown_estimate + 1e-6:
                opp_risk = (opp_demand_estimate - opp_breakdown_estimate) / opp_demand_estimate
            else:
                opp_risk = 0.0
            opp_risk = max(0.05, min(0.95, opp_risk))
            
            # Concession step: concede if our risk > opponent's risk
            concession_step = 0.0
            
            # Damage control: accelerate concession 2x, ignore reciprocity freeze
            dc_active = self._damage_control
            frozen = self._reciprocity_frozen and not dc_active
            dc_mult = 2.0 if dc_active else 1.0
            
            if my_risk > opp_risk and not frozen:
                # Concede proportionally to risk gap
                zs = self._tp('zeuthen_concession_scale', 0.05)
                concession_step = min(0.05, (my_risk - opp_risk) * zs * dc_mult)
            elif t > 0.60 and not frozen:
                # Time pressure: small concessions even when risk is balanced
                concession_step = 0.01 * ((t - 0.60) / 0.40) * dc_mult
            
            # Apply concession
            self._zeuthen_aspiration = max(
                aspiration_floor,
                self._zeuthen_aspiration - concession_step
            )
            
            # Time-based floor: ensure we reach deal zone regardless of Zeuthen calc
            # By t=0.50, aspiration should be at most 0.50
            # By t=0.80, aspiration should be at most 0.43
            tfr = self._tp('time_floor_rate', 0.90)
            time_floor = aspiration_start - (aspiration_start - aspiration_floor) * min(1.0, t * tfr)
            self._zeuthen_aspiration = min(self._zeuthen_aspiration, max(aspiration_floor, time_floor))
            
            # ─── COUNTER-ANCHORING ────────────────────────────
            # Respond to extreme lowballs but stay in the deal zone.
            #
            # BUG FIX (2026-04-29): when playbook mode is ON, the playbook-
            # composed aspiration_start IS the deliberate ceiling — don't
            # cap it at the legacy `counter_anchor_cap` heuristic
            # (default 0.58). Previously: `min(ca_cap, aspiration_start)`
            # truncated BOULWARE playbook (asp_start=0.95) down to 0.58,
            # which is the second silent override of the playbook
            # (after bug #1's self-calibration override).
            if opp_utils and opp_utils[0] < 0.05 and len(opp_utils) <= 2:
                if _pb_mode() != "OFF":
                    # Playbook mode: trust the composed ceiling.
                    self._zeuthen_aspiration = max(
                        self._zeuthen_aspiration, aspiration_start,
                    )
                else:
                    ca_cap = self._tp('counter_anchor_cap', 0.58)
                    self._zeuthen_aspiration = max(
                        self._zeuthen_aspiration,
                        min(ca_cap, aspiration_start),
                    )
            
            aspiration = self._zeuthen_aspiration
            aspiration_range = aspiration_start - aspiration_floor
        
        elif total_steps <= 30:
            aspiration_start = 0.82
            aspiration_range = aspiration_start - adjusted_floor
            base_exp = 3.0 + self._aggression * 2.5
        else:
            aspiration_start = 0.90
            aspiration_range = aspiration_start - adjusted_floor
            base_exp = 5.0 + self._aggression * 3.0
        
        # For medium/long games: compute aspiration from t^exponent curve
        # (B2B mode already set aspiration via Zeuthen, skip this)
        if total_steps > 15:
            # Opponent-adaptive exponent: slow down if we're conceding faster
            if len(self._my_utilities) >= 3 and self.opponent_model.concession_rate > 0.001:
                my_utils_recent = self._my_utilities[-5:]
                my_concession = abs(my_utils_recent[-1] - my_utils_recent[0]) / max(1, len(my_utils_recent) - 1) if len(my_utils_recent) > 1 else 0
                opp_concession = self.opponent_model.concession_rate
                if opp_concession > 0 and my_concession > opp_concession * 1.2:
                    base_exp = min(base_exp * 1.5, 15.0)
            
            aspiration = aspiration_start - aspiration_range * (t ** base_exp)
        
        # --- Per-Step Concession Cap ---
        if self._my_offers:
            last_util = self.ufun(self._my_offers[-1])
            if last_util is not None:
                base_cap = self._pb_param('concession_cap_b2b', 0.041) if total_steps <= 15 else 0.02
                
                if t < 0.9:
                    max_concession = base_cap
                else:
                    max_concession = base_cap + 0.03 * ((t - 0.9) / 0.1)
                aspiration = max(aspiration, float(last_util) - max_concession)
        
        # --- Sinusoidal Perturbation ---
        # ±1-2% utility jitter via sin wave with random phase per negotiation.
        # Disrupts opponent curve-fitting without sacrificing patience.
        # Scale DOWN for short games: opponents can't learn our curve in 10 steps.
        freq = 3.5  # 3.5 cycles per negotiation
        game_scale = min(1.0, total_steps / 100.0)  # 0.10 for 10-step, 1.0 for 100-step
        sin_amplitude = 0.015 * aspiration_range * game_scale
        oscillation = sin_amplitude * np.sin(
            2 * np.pi * freq * t + self._oscillation_phase
        )
        aspiration += oscillation
        
        # --- Exploit Probe (random retraction) ---
        # In long games (>15 steps): 6% retraction to disrupt modeling.
        # In B2B short games: reduced to 1% — retractions look aggressive
        # and waste scarce rounds. BOA diagnostic confirmed this.
        retract_prob = self._tp('retract_prob_b2b', 0.01) if total_steps <= 15 else 0.06
        if (self._my_offers and 0.05 < t < 0.85
                and self._rng.random() < retract_prob):
            last_util = self.ufun(self._my_offers[-1])
            if last_util is not None:
                retract = self._rng.uniform(0.01, 0.03)
                aspiration = max(aspiration, float(last_util) + retract)
        
        # --- Concession-Rate Response ---
        # In B2B: soften the hold-back — we can't afford to stall.
        # Only hold floor against truly hardline opponents in long games.
        opp_rate = self.opponent_model.concession_rate
        if total_steps > 15:
            # Long games: original aggressive hold-back
            if opp_rate < 0.5 and len(self.opponent_model.opponent_offers) > 5:
                aspiration = max(aspiration, adjusted_floor + 0.05)
            elif opp_rate > 3.0 and t > 0.3:
                aspiration = max(aspiration, 0.7 * aspiration + 0.3 * 0.8)
        else:
            # B2B short games: mild hold-back only against extreme hardliners
            if opp_rate < 0.2 and len(self.opponent_model.opponent_offers) > 5:
                aspiration = max(aspiration, adjusted_floor + 0.02)
            elif opp_rate > 3.0 and t > 0.3:
                aspiration = max(aspiration, 0.7 * aspiration + 0.3 * 0.7)
        
        # (Near-Deadline Push removed — superseded by late-game curve acceleration)
        
        # Absolute bounds
        target_utility = max(aspiration, rubinstein_floor)
        target_utility = min(target_utility, 0.99)
        
        # ─── DAMAGE CONTROL: CLAMP TO RV ─────────────────────
        # When non-convergent, drop aspiration to rv immediately.
        # The opponent won't accept our 0.48 offers (which give them 0.50).
        # We need to propose at 0.42 (giving them 0.63) so they accept.
        if self._damage_control and total_steps <= 15:
            rv_dc = float(self.ufun.reserved_value) if self.ufun.reserved_value else 0.0
            # Graduated descent: interpolate from ceiling toward rv.
            # Key insight: opponents typically accept at t>0.90 with their
            # utility >= 0.50. To give them B>=0.50, we need A around 0.40-0.45.
            # Use QUADRATIC curve: reaches rv by step 8 (t=0.80), giving
            # 2 steps for the opponent to see and accept the low offer.
            dc_progress = min(1.0, max(0.0, (t - 0.40) / 0.60))  # 0→1 from t=0.40 to t=1.00
            dc_progress = dc_progress ** 2  # quadratic: moderate descent, not cliff
            dc_ceil = max(target_utility, rv_dc + 0.12)  # start from rv+0.12 (~0.52)
            dc_floor = rv_dc + 0.02  # floor above rv — ensures DC deals beat BATNA
            target_utility = dc_ceil * (1.0 - dc_progress) + dc_floor * dc_progress
            target_utility = max(dc_floor, target_utility)  # never below floor
            self._in_capitulation = True
        
        self._last_target_utility = target_utility
        
        # === Find closest outcome to target utility (Pareto-aware) ===
        # During capitulation: search for opponent-favorable outcomes (non-oracle)
        if getattr(self, '_in_capitulation', False) and self._sorted_outcomes:
            # Use target_utility as the floor — already set to rv+0.02 by DC curve
            floor = target_utility
            
            # Candidates: outcomes near the target, within a band
            # Below target is where opponent utility is highest (anti-correlation)
            band = 0.05
            candidates = [(o, u) for o, u in self._sorted_outcomes 
                         if floor - 0.01 <= u <= floor + band]
            
            if not candidates:
                # Fallback: any outcome at or above the DC floor
                candidates = [(o, u) for o, u in self._sorted_outcomes if u >= floor]
            
            if candidates:
                # DIVERSITY CYCLING: rotate through candidates to explore
                # different issue combinations the opponent might accept
                candidates.sort(key=lambda x: x[1])
                
                dc_step = getattr(self, '_dc_proposal_counter', 0)
                self._dc_proposal_counter = dc_step + 1
                
                # Use the full candidate set, cycling through
                idx = dc_step % len(candidates)
                offer = candidates[idx][0]
            else:
                offer = self._find_pareto_outcome(target_utility)
        else:
            offer = self._find_pareto_outcome(target_utility)
        
        if offer is not None:
            u = self.ufun(offer)
            u_val = float(u) if u is not None else target_utility
            
            # HARD BATNA FLOOR: never propose below reservation value.
            # Walking away at BATNA is ALWAYS better than a deal below it.
            rv = float(self.ufun.reserved_value) if self.ufun.reserved_value else 0.0
            if u_val < rv and total_steps <= 15:
                above_rv = [(o2, u2) for o2, u2 in self._sorted_outcomes if u2 >= rv]
                if above_rv:
                    if getattr(self, '_in_capitulation', False):
                        # During capitulation: min(A) ≈ max(B) by ρ=-0.984
                        offer = min(above_rv, key=lambda x: x[1])[0]
                    else:
                        # Normal: pick closest to target above rv
                        offer = min(above_rv, key=lambda x: abs(x[1] - target_utility))[0]
                    u = self.ufun(offer)
                    u_val = float(u) if u is not None else target_utility
            
            self._my_offers.append(offer)
            self._my_utilities.append(u_val)
            self.opponent_model.record_our_offer(offer)
        
        return offer or self._my_best
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        """
        Decide whether to accept an offer.
        
        Uses a dual-threshold acceptance strategy:
        1. Accept if utility > aspiration threshold (good enough)
        2. Accept near deadline if utility > reservation (better than nothing)
        3. Accept if opponent is hardliner and offer is reasonable
        """
        self._ensure_initialized()
        if self.ufun is None:
            return ResponseType.REJECT_OFFER
        
        offer = state.current_offer

        # Observe opponent's offer for modeling
        self.opponent_model.observe(offer, state.relative_time)

        # Recompose playbook AFTER observing this offer so the belief
        # reflects the latest signal. No-op under SNHP_PLAYBOOK_MODE=OFF.
        self._refresh_playbook()

        my_utility = self.ufun(offer)
        if my_utility is None:
            return ResponseType.REJECT_OFFER
        
        t = state.relative_time
        rv = getattr(self.ufun, 'reserved_value', None)
        if rv is None or rv == float('-inf'):
            rv = 0.0
        
        # === Acceptance Thresholds ===
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        
        if total_steps <= 15:
            # ─── B2B DEAL-ZONE ACCEPTANCE (Von Neumann Fix) ──
            # Core insight: in short B2B games, a deal at 0.42 beats
            # walking away at BATNA (0.40). Accept anything above rv
            # when time pressure rises. Track best opponent offer for
            # "accept if better than next" logic.
            
            opp_type = self.opponent_model.opponent_type
            opp_conf = self.opponent_model.confidence
            opp_utils = self.opponent_model._opp_utilities
            
            # ─── NON-CONVERGENCE DETECTOR ─────────────────────
            # True hardliners: best offer for us < 0.20 AND they
            # haven't conceded meaningfully. Cooperators offer 0.27+
            # by t=0.50, so 0.20 separates the populations cleanly.
            # Progressive: at t=0.70 raise threshold to catch late
            # non-convergers like BATNA Bluffer (offers us ~0.28).
            if not self._damage_control and len(opp_utils) >= 3:
                best_opp_for_us = max(opp_utils) if opp_utils else 0.0
                # Max improvement: has the opponent EVER offered us something
                # much better than their opening? If yes, they're conceding.
                # This is more robust than last-first which can fluctuate.
                first_opp = opp_utils[0] if opp_utils else 0.0
                opp_max_improvement = best_opp_for_us - first_opp
                
                # Phase 1 (t>0.50): catch only extreme hardliners
                # Very strict: both low offers AND near-zero concession.
                # Aspiration concedes 0.02-0.04 by here; Soviet concedes 0.00-0.02.
                if t > 0.50 and best_opp_for_us < 0.12 and opp_max_improvement < 0.02:
                    self._damage_control = True
                # Phase 2 (t>0.65): catch moderate non-convergers
                # By step 6-7, Aspiration concedes 0.10+; hardliners stay under 0.08
                elif t > 0.65 and best_opp_for_us < 0.25 and opp_max_improvement < 0.08:
                    self._damage_control = True
                # Phase 3 (t>0.75): last resort — opponent hasn't reached deal zone
                elif t > 0.75 and best_opp_for_us < 0.35 and opp_max_improvement < 0.12:
                    self._damage_control = True
            
            # ─── DAMAGE CONTROL ACCEPTANCE (with Schelling commitment) ──
            # Refuse deals within `commitment_margin` of BATNA even in DC mode.
            # Without this, BATNA Bluffer / Aspiration / Reciprocity extract
            # deals barely above our walk-away by stalling.
            if self._damage_control:
                dc_bar = rv + self._commitment_margin
                if my_utility >= dc_bar:
                    self._record_outcome(True, my_utility)
                    return ResponseType.ACCEPT_OFFER
            
            # Phase 1 (t < 0.36): Hold at aspiration — only accept great deals
            # Phase 2 (0.36 < t < 0.60): Accept if >= Zeuthen aspiration
            # Phase 3 (t > 0.60): Graduated acceptance down toward rv
            
            early_cutoff = self._tp('accept_early_cutoff', 0.20)
            if t < early_cutoff:
                # Early: only accept genuinely good deals (first 2 rounds)
                accept_bar = max(self._zeuthen_aspiration, self._pb_param('accept_early_bar', 0.54))
            elif t < self._tp('accept_late_start', 0.60):
                # Mid-game: accept at or near aspiration
                mid_offset = self._tp('accept_mid_offset', 0.0)
                accept_bar = self._zeuthen_aspiration + mid_offset
            else:
                # Late-game: graduate toward rv + margin
                late_start = self._tp('accept_late_start', 0.60)
                deadline_progress = (t - late_start) / (1.0 - late_start)
                top = self._zeuthen_aspiration
                bottom = max(rv, self._tp('accept_late_bottom', 0.43))
                accept_bar = top - (top - bottom) * (deadline_progress ** self._tp('accept_late_curve', 0.58))
            
            # Best-opponent-offer logic: if this offer is the best we've seen,
            # accept it in the late game (bird in hand)
            best_seen = max(opp_utils) if opp_utils else 0.0
            bst = self._tp('best_seen_time', 0.60)
            bsm = self._tp('best_seen_margin', 0.01)
            if t > bst and my_utility >= best_seen and my_utility > rv + bsm:
                self._record_outcome(True, my_utility)
                return ResponseType.ACCEPT_OFFER
            
            # Standard acceptance
            if my_utility >= accept_bar and my_utility >= rv:
                self._record_outcome(True, my_utility)
                return ResponseType.ACCEPT_OFFER
            
            # Emergency late-game acceptance, gated by Schelling commitment.
            # Previously: accept anything >= rv at t>=0.75 — exploitable.
            # Now: must clear rv + commitment_margin even in emergency.
            if t >= self._tp('emergency_time', 0.75) and my_utility >= rv + self._commitment_margin:
                self._record_outcome(True, my_utility)
                return ResponseType.ACCEPT_OFFER
            
            # Convergence: accept if our last offer and their offer are close
            if (self._my_offers and t > self._tp('convergence_time', 0.54)):
                last_our_util = self.ufun(self._my_offers[-1])
                if last_our_util is not None:
                    gap = abs(float(last_our_util) - float(my_utility))
                    if gap < self._tp('convergence_gap', 0.04) and my_utility >= rv:
                        self._record_outcome(True, my_utility)
                        return ResponseType.ACCEPT_OFFER
        
        else:
            # ─── ANAC MODE: original acceptance logic ─────────
            if my_utility >= self._last_target_utility and my_utility >= rv:
                self._record_outcome(True, my_utility)
                return ResponseType.ACCEPT_OFFER
            
            if t >= 0.99:
                opp_utils = self.opponent_model._opp_utilities
                opp_concession_total = 0.0
                if len(opp_utils) >= 2:
                    opp_concession_total = abs(opp_utils[-1] - opp_utils[0])
                
                if opp_concession_total < 0.15:
                    emergency_floor = max(rv + 0.1, 0.48)
                else:
                    emergency_floor = max(rv + 0.1, 0.40)
                
                if my_utility >= emergency_floor:
                    self._record_outcome(True, my_utility)
                    return ResponseType.ACCEPT_OFFER
        
        return ResponseType.REJECT_OFFER
    
    # ─── Helper Methods ───
    
    def _estimate_opponent_urgency(self, relative_time: float) -> float:
        """Estimate opponent's urgency from their concession rate."""
        cr = self.opponent_model.concession_rate
        if cr > 2.0:
            return 0.7  # conceding fast → urgent
        elif cr > 0.5:
            return 0.5  # moderate
        else:
            return 0.3  # barely conceding → patient
    
    def _estimate_opponent_reservation_utility(self) -> float:
        """
        Estimate the utility that the OPPONENT gets from their reservation.

        Cold-start prior is SYMMETRIC: when we have low confidence in the
        inferred reservation, mirror our OWN BATNA. The previous hardcoded
        0.3 prior was role-asymmetric (assumed opponent was buyer-side) and
        biased Nash computations toward seller-favoring outcomes when SNHP
        played buyer.
        """
        if self.opponent_model.confidence < 0.2:
            my_rv = float(getattr(self.ufun, 'reserved_value', None) or 0.40)
            return min(0.9, max(0.1, my_rv))

        est = self.opponent_model.estimated_reservation
        return min(0.9, max(0.1, est))
    
    def _find_outcome_near_utility(self, target: float) -> Optional[Outcome]:
        """Find the outcome whose utility is closest to target (fallback)."""
        if self.ufun is None or self._sorted_outcomes is None:
            return None
        
        best_outcome = None
        best_dist = float('inf')
        
        for o, u in self._sorted_outcomes:
            dist = abs(u - target)
            if dist < best_dist:
                best_dist = dist
                best_outcome = o
        
        return best_outcome
    
    def _find_pareto_outcome(self, target: float) -> Optional[Outcome]:
        """
        Pareto-aware outcome selection with TARGETED LOGROLLING.
        
        Strategy: maximize estimated opponent utility while staying near our
        target. This finds the "trade surplus" — outcomes where we give on
        cheap-for-us issues (warranty, delivery) and hold on expensive issues
        (price, payment). The result: both sides get more value, deals close
        faster because the opponent sees genuinely good offers.
        
        When inferred weights are available:
          score = proximity_to_our_target × estimated_opponent_value
        When no weights:
          Falls back to similarity-to-opponent-offers scoring.
        """
        if self.ufun is None or self._sorted_outcomes is None:
            return None
        
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        
        # ─── BAND SELECTION ──────────────────────────────
        # Wider band = more logrolling candidates to choose from.
        # In B2B with a flat curve, we want maximum variety within
        # a tight utility window to find the best issue compositions.
        band = 0.08  # Normal band
        if total_steps <= 15:
            band = 0.06  # Tighter for flat curve — don't stray from target
            opp_type = self.opponent_model.opponent_type
            opp_conf = self.opponent_model.confidence
            if opp_type == OpponentModel.BOULWARE and opp_conf > 0.25:
                band = 0.15  # Widen for hardliners — need creative trades
        
        candidates = [(o, u) for o, u in self._sorted_outcomes 
                      if u >= target - band and u <= target + band]
        
        if not candidates:
            return self._find_outcome_near_utility(target)
        
        if len(candidates) == 1:
            return candidates[0][0]
        
        # --- Context ---
        opp_utils = self.opponent_model._opp_utilities
        opp_offers = self.opponent_model.opponent_offers
        opp_weights = self._inferred_opp_weights
        
        if len(opp_utils) < 2 or len(opp_offers) < 2:
            # Not enough data: pick closest to target
            return min(candidates, key=lambda x: abs(x[1] - target))[0]
        
        # --- Score candidates ---
        best_candidate = None
        best_score = -float('inf')
        n_issues = len(candidates[0][0])
        
        for o, u in candidates:
            # Component 1: Proximity to target (stay near our aspiration)
            proximity = 1.0 - abs(u - target) / max(band, 0.01)
            
            # Component 2: Estimated opponent value (LOGROLLING CORE)
            # Higher = opponent is more likely to accept = faster closure
            if opp_weights and len(opp_weights) >= n_issues:
                # ─── TARGETED LOGROLLING ──────────────────────
                # Estimate how much the opponent values this outcome
                # by weighting each issue according to inferred preferences.
                # Outcomes that give opponent their high-weight issues
                # while preserving our value → Pareto-dominant trades.
                opp_value = 0.0
                for i in range(n_issues):
                    opp_w = opp_weights.get(i, 1.0 / n_issues)
                    # How close is this issue value to opponent's preferred?
                    if opp_offers:
                        opp_preferred = float(opp_offers[-1][i])
                        issue_max = max(float(o[i]), opp_preferred, 1.0)
                        closeness = 1.0 - abs(float(o[i]) - opp_preferred) / issue_max
                        opp_value += opp_w * closeness
                    else:
                        opp_value += opp_w * 0.5
            else:
                # Fallback: use raw similarity to recent opponent offers
                recent_opp = opp_offers[-3:]
                opp_value = 0.0
                for opp_o in recent_opp:
                    issue_sim = sum(
                        1.0 - abs(float(o[i]) - float(opp_o[i])) / max(1, float(max(o[i], opp_o[i])))
                        for i in range(min(len(o), len(opp_o)))
                    ) / max(len(o), 1)
                    opp_value += issue_sim
                opp_value /= max(len(recent_opp), 1)
            
            # Component 3: Self-interest — prefer our higher utility
            our_value = u / max(target, 0.01)
            
            # ─── ASYMMETRY CHECK ─────────────────────────────
            # If we're conceding much more than opponent, shift weight
            # toward self-interest to prevent exploitation.
            self_interest_weight = 0.10  # Low default — prioritize logrolling
            if len(opp_utils) >= 3 and len(self._my_utilities) >= 3:
                our_total_concession = abs(self._my_utilities[-1] - self._my_utilities[0])
                opp_total_concession = abs(opp_utils[-1] - opp_utils[0])
                if our_total_concession > 0.03 and opp_total_concession > 0:
                    asymmetry = our_total_concession / max(opp_total_concession, 0.001)
                    if asymmetry > 2.0:
                        self_interest_weight = 0.30
                    elif asymmetry > 1.5:
                        self_interest_weight = 0.20
            
            # ─── FINAL SCORE ─────────────────────────────────
            # Logrolling-dominant: maximize opponent value while staying
            # near our target. This produces offers the opponent WANTS
            # to accept → faster closure at higher joint utility.
            logroll_weight = 1.0 - self_interest_weight
            score = (logroll_weight * 0.35 * proximity +      # stay near target
                     logroll_weight * 0.65 * opp_value +       # maximize opp value
                     self_interest_weight * our_value)          # protect our share
            
            if score > best_score:
                best_score = score
                best_candidate = o
        
        return best_candidate
    
    def _record_outcome(self, deal_closed: bool, utility: float):
        """Record the negotiation outcome for cross-session learning."""
        self.memory.update(self._arm_index, deal_closed, utility,
                          self._detected_opp_type, role=self._snhp_role)
    
    def on_negotiation_end(self, state):
        """Called when negotiation ends. Record failure if no deal."""
        super().on_negotiation_end(state)
        if state.agreement is None:
            self._record_outcome(False, 0.0)


# ═══════════════════════════════════════════════════
#  Tournament Runner
# ═══════════════════════════════════════════════════

def run_tournament(n_scenarios: int = 50, n_steps: int = 100):
    """
    Run a mini-tournament against NegMAS built-in agents.
    """
    from negmas.sao import SAOMechanism
    from negmas.sao.negotiators import (
        AspirationNegotiator,
        NaiveTitForTatNegotiator,
        ConcederTBNegotiator,
        LinearTBNegotiator,
        BoulwareTBNegotiator,
        NiceNegotiator,
        ToughNegotiator,
        RandomNegotiator,
    )
    from negmas.outcomes import make_issue
    from negmas.preferences import MappingUtilityFunction
    import statistics
    
    issues = [make_issue(name="price", values=100)]
    
    # Utility functions
    seller_values = {(p,): p / 99.0 for p in range(100)}
    buyer_values = {(p,): 1.0 - p / 99.0 for p in range(100)}
    seller_ufun = MappingUtilityFunction(mapping=seller_values, issues=issues)
    buyer_ufun = MappingUtilityFunction(mapping=buyer_values, issues=issues)
    
    opponents = {
        "Aspiration": AspirationNegotiator,
        "TitForTat": NaiveTitForTatNegotiator,
        "Conceder": ConcederTBNegotiator,
        "Linear": LinearTBNegotiator,
        "Boulware": BoulwareTBNegotiator,
        "Nice": NiceNegotiator,
        "Tough": ToughNegotiator,
        "Random": RandomNegotiator,
    }
    
    results = {}
    
    for opp_name, OppClass in opponents.items():
        snhp_utils = []
        opp_utils = []
        deals = 0
        
        for i in range(n_scenarios):
            # SNHP as seller
            mech = SAOMechanism(issues=issues, n_steps=n_steps)
            snhp = SNHPAgent(name=f"snhp_{i}")
            opp = OppClass(name=f"{opp_name}_{i}")
            mech.add(snhp, ufun=seller_ufun)
            mech.add(opp, ufun=buyer_ufun)
            
            result = mech.run()
            
            if result.agreement is not None:
                su = seller_ufun(result.agreement)
                ou = buyer_ufun(result.agreement)
                snhp_utils.append(su if su is not None else 0)
                opp_utils.append(ou if ou is not None else 0)
                deals += 1
            else:
                snhp_utils.append(0)
                opp_utils.append(0)
        
        deal_rate = deals / n_scenarios
        avg_util = statistics.mean(snhp_utils) if snhp_utils else 0
        avg_social = statistics.mean([s + o for s, o in zip(snhp_utils, opp_utils)])
        
        results[opp_name] = {
            "snhp_utility": round(avg_util, 4),
            "opp_utility": round(statistics.mean(opp_utils), 4),
            "social_welfare": round(avg_social, 4),
            "deal_rate": round(deal_rate, 3),
        }
    
    # Print results
    print("=" * 70)
    print("  SNHP NegMAS TOURNAMENT RESULTS")
    print("=" * 70)
    print()
    print(f"  {'Opponent':<20} {'SNHP Util':>10} {'Opp Util':>10} "
          f"{'Social':>10} {'Deal Rate':>10}")
    print("  " + "-" * 60)
    
    for opp_name, r in results.items():
        print(f"  {opp_name:<20} {r['snhp_utility']:>10.4f} "
              f"{r['opp_utility']:>10.4f} {r['social_welfare']:>10.4f} "
              f"{r['deal_rate']:>10.1%}")
    
    # Also run Aspiration vs Aspiration as baseline
    baseline_utils = []
    for i in range(n_scenarios):
        mech = SAOMechanism(issues=issues, n_steps=n_steps)
        s = AspirationNegotiator(name=f"asp_s_{i}")
        b = AspirationNegotiator(name=f"asp_b_{i}")
        mech.add(s, ufun=seller_ufun)
        mech.add(b, ufun=buyer_ufun)
        result = mech.run()
        if result.agreement:
            baseline_utils.append(seller_ufun(result.agreement) or 0)
        else:
            baseline_utils.append(0)
    
    print()
    print(f"  {'Aspiration (baseline)':<20} {statistics.mean(baseline_utils):>10.4f}")
    
    # Cross-session learning summary
    print()
    print("  THOMPSON SAMPLING STATE (per opponent type)")
    print("  " + "-" * 55)
    mem = _global_memory
    for opp_type in ["unknown", "boulware", "mirror"]:
        bandit = mem._bandits[opp_type]
        total_obs = int(sum(bandit["counts"]))
        if total_obs == 0:
            continue
        posterior_means = bandit["successes"] / (bandit["successes"] + bandit["failures"])
        best_arm = int(np.argmax(
            np.where(bandit["counts"] > 0, 
                    bandit["profits"] / np.maximum(bandit["counts"], 1), 0) * posterior_means
        ))
        print(f"  [{opp_type}] best_α={mem.arms[best_arm]:.2f} (obs={total_obs})")
        for i, (arm, rate) in enumerate(zip(mem.arms, posterior_means)):
            count = int(bandit["counts"][i])
            if count > 0:
                avg_profit = bandit["profits"][i] / max(count, 1)
                print(f"    α={arm:.2f}: rate={rate:.3f} avg_util={avg_profit:.3f} n={count}")
    
    return results


if __name__ == "__main__":
    run_tournament(n_scenarios=100, n_steps=100)

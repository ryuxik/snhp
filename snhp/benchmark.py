"""
SNHP kill-criterion benchmark.

Three competitors play SELLER against the same fixed opponent (BUYER) across
the same set of B2B contract scenarios. Apples-to-apples A/B that answers
the only question that matters for the redesign:

  Does an LLM agent WITH the SNHP API beat an LLM agent WITHOUT it,
  and do both beat the simplest reasonable baseline?

Competitors:
  1. LLM_with_SNHP — Gemini 3 Flash agent that calls a v0 in-process stub of
     the new propose_offer endpoint. (Real HTTP/MCP API doesn't exist yet —
     the stub uses the same math the production endpoint will wrap, so this
     benchmark validates the math+access premise BEFORE the API is built.)
  2. LLM_naive    — Gemini 3 Flash agent given the same scenario context but
     no SNHP tool. Reasons end-to-end on its own.
  3. SplitTheDiff — Existing programmatic NegMAS bot. Deterministic floor —
     if the LLM-naive can't beat splitting the difference, agents can't
     negotiate at all without help.

Fixed opponent: Anchorer (from b2b_opponents). Predictable, well-characterized,
deterministic. Gives every competitor the same surface to beat.

Cost: Gemini 3 Flash @ $0.30/M input + $2.50/M output. ~5 LLM calls per round
per LLM competitor. For 30 scenarios × 5 rounds × 2 LLM competitors ≈ $0.40.
SplitTheDiff is free.

Usage:
    python -m snhp.benchmark --dry-run                 # cost estimate only
    python -m snhp.benchmark --scenarios 30 --rounds 5
    python -m snhp.benchmark --competitors LLM_with_SNHP,SplitTheDiff
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_THIS_DIR))

# Load .env deterministically from the project root (ab/.env) regardless of cwd.
# llm_extractor.py uses a cwd-relative path which breaks under `python -m`.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_THIS_DIR), ".env"))
except ImportError:
    pass

# Disable LiteLLM internal retries so our retry logic in _LLMNegotiatorBase
# is the ONLY source of retries. Otherwise litellm silently retries 2-3x on
# 5xx errors and bills each retry — invisible to our cost accounting.
# Also set num_retries on every kwargs dict (in case the global is overridden).
try:
    import litellm as _lit
    _lit.num_retries = 0
    _lit.suppress_debug_info = True
except ImportError:
    pass

from negmas.sao import SAOMechanism, SAONegotiator, SAOState, ResponseType
from negmas.outcomes import make_issue, Outcome
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import IdentityFun, AffineFun

from snhp.b2b_opponents import (
    Anchorer, SplitTheDiff, FairDemand, SilentHardliner, TacticalEmpath,
    B2B_OPPONENTS,
)
from snhp.llm_extractor import _call_llm

from snhp.engram import Engram
from snhp.nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
from snhp.bayesian_agent import BayesianParticleFilter
from snhp.cost_calculator import (
    estimate_run_cost as _calc_estimate_run_cost,
    SNHP_BENCHMARK_PROMPT_SHAPE,
)
from snhp._stats import bootstrap_ci, wilcoxon_approx


# Pricing + token estimates live in snhp.cost_calculator (single source of truth,
# self-tested). This module just imports SNHP_BENCHMARK_PROMPT_SHAPE.


# ─── Issue space (mirrors b2b_round_robin.create_issues()) ──────────────────


ISSUE_NAMES = ["price", "delivery", "warranty", "payment"]
ISSUE_CARDINALITIES = {"price": 50, "delivery": 5, "warranty": 4, "payment": 3}


def make_benchmark_issues():
    return [make_issue(name=n, values=ISSUE_CARDINALITIES[n]) for n in ISSUE_NAMES]


def make_seller_buyer_ufuns(seller_weights: dict, buyer_weights: dict,
                             batna: float, n_steps: int):
    """
    Mirror b2b_round_robin.create_ufuns:
      - Seller: rewards high price + slow payment days; cares less about delivery/warranty
      - Buyer:  rewards low price + fast delivery + long warranty; flexible on payment
    """
    temp = SAOMechanism(issues=make_benchmark_issues(), n_steps=n_steps)
    iss = temp.outcome_space.issues

    seller_ufun = LUFun(
        values={
            "price": IdentityFun(),
            "delivery": IdentityFun(),
            "warranty": AffineFun(slope=-1, bias=3),
            "payment": AffineFun(slope=-1, bias=2),
        },
        weights=seller_weights,
        issues=iss,
    ).normalize()
    seller_ufun.reserved_value = batna

    buyer_ufun = LUFun(
        values={
            "price": AffineFun(slope=-1, bias=49),
            "delivery": AffineFun(slope=-1, bias=4),
            "warranty": IdentityFun(),
            "payment": IdentityFun(),
        },
        weights=buyer_weights,
        issues=iss,
    ).normalize()
    buyer_ufun.reserved_value = batna

    return seller_ufun, buyer_ufun


# ─── Scenario generation ────────────────────────────────────────────────────


@dataclass
class Scenario:
    scenario_id: str
    seller_weights: dict
    buyer_weights: dict
    batna: float
    n_steps: int
    seed: int


def generate_scenarios(n: int = 30, seed: int = 42) -> list[Scenario]:
    """
    Sample scenarios from the same Dirichlet distribution as the existing
    tournament (b2b_round_robin.create_ufuns randomize_weights branch),
    plus per-scenario BATNA and step count.
    """
    rng = np.random.RandomState(seed)
    concentration = 5.0
    alpha_seller = np.array([0.50, 0.15, 0.10, 0.25]) * concentration
    alpha_buyer = np.array([0.20, 0.30, 0.40, 0.10]) * concentration

    scenarios = []
    for i in range(n):
        seller_w = rng.dirichlet(alpha_seller)
        buyer_w = rng.dirichlet(alpha_buyer)
        batna = float(rng.uniform(0.32, 0.48))
        n_steps = int(rng.randint(7, 14))
        scenarios.append(Scenario(
            scenario_id=f"s{i:03d}",
            seller_weights={n: float(w) for n, w in zip(ISSUE_NAMES, seller_w)},
            buyer_weights={n: float(w) for n, w in zip(ISSUE_NAMES, buyer_w)},
            batna=batna,
            n_steps=n_steps,
            seed=int(rng.randint(0, 2**31 - 1)),
        ))
    return scenarios


# ─── In-process v1 of the new propose_offer API (full 4D Nash) ──────────────


# Pre-compute the 4D outcome enumeration once at module load (3000 outcomes, fast)
_ALL_OUTCOMES_LIST = [
    (p, d, w, pay)
    for p in range(ISSUE_CARDINALITIES["price"])
    for d in range(ISSUE_CARDINALITIES["delivery"])
    for w in range(ISSUE_CARDINALITIES["warranty"])
    for pay in range(ISSUE_CARDINALITIES["payment"])
]
_ALL_OUTCOMES_ARR = np.array(_ALL_OUTCOMES_LIST, dtype=np.int32)


def _seller_utility_per_dim(outcomes_arr: np.ndarray) -> np.ndarray:
    """
    Per-dimension *normalized* utility for the SELLER, matching the tournament's
    ufun structure (b2b_round_robin.create_ufuns):
      - price:    IdentityFun       → seller utility ∝ price index / max
      - delivery: IdentityFun       → seller utility ∝ delivery index / max
      - warranty: AffineFun(-1,3)   → seller utility ∝ (max - warranty) / max
      - payment:  AffineFun(-1,2)   → seller utility ∝ (max - payment) / max

    Returns array of shape (N, 4) with values in [0, 1].
    """
    n = outcomes_arr.shape[0]
    out = np.zeros((n, 4), dtype=np.float64)
    out[:, 0] = outcomes_arr[:, 0] / (ISSUE_CARDINALITIES["price"] - 1)
    out[:, 1] = outcomes_arr[:, 1] / (ISSUE_CARDINALITIES["delivery"] - 1)
    out[:, 2] = (ISSUE_CARDINALITIES["warranty"] - 1 - outcomes_arr[:, 2]) / (ISSUE_CARDINALITIES["warranty"] - 1)
    out[:, 3] = (ISSUE_CARDINALITIES["payment"] - 1 - outcomes_arr[:, 3]) / (ISSUE_CARDINALITIES["payment"] - 1)
    return out


def _buyer_utility_per_dim(outcomes_arr: np.ndarray) -> np.ndarray:
    """
    Per-dimension *normalized* utility for the BUYER (mirror of the seller's
    direction on each issue, per the tournament's ufun structure).

    Returns array of shape (N, 4) with values in [0, 1].
    """
    n = outcomes_arr.shape[0]
    out = np.zeros((n, 4), dtype=np.float64)
    out[:, 0] = (ISSUE_CARDINALITIES["price"] - 1 - outcomes_arr[:, 0]) / (ISSUE_CARDINALITIES["price"] - 1)
    out[:, 1] = (ISSUE_CARDINALITIES["delivery"] - 1 - outcomes_arr[:, 1]) / (ISSUE_CARDINALITIES["delivery"] - 1)
    out[:, 2] = outcomes_arr[:, 2] / (ISSUE_CARDINALITIES["warranty"] - 1)
    out[:, 3] = outcomes_arr[:, 3] / (ISSUE_CARDINALITIES["payment"] - 1)
    return out


def snhp_propose_offer_v1(
    *,
    my_weights: dict,
    opp_offer_history: list[tuple],
    my_batna: float = 0.40,
    opp_batna_estimate: float = 0.40,
) -> dict:
    """
    Full 4D Nash bargaining over the complete contract space (3000 outcomes
    across price × delivery × warranty × payment).

    Mirrors the math sdk.run_path_a runs, but adapted for the discrete NegMAS
    issue space rather than sdk.py's normalized [0,1]^4 grid.

    Pipeline:
      1. Enumerate all 3000 outcomes; compute per-dimension normalized
         utilities for SELLER (us) and BUYER (opponent).
      2. Compute our total utility per outcome from `my_weights`.
      3. Infer opponent's weight vector from their offer history via the
         BayesianParticleFilter — same filter sdk.py uses, but on a 4D
         particle cloud over the opponent's per-dim normalized utilities.
      4. Compute opponent's total utility per outcome from inferred weights.
      5. Filter Pareto frontier; pick Nash bargaining solution.
      6. Return the recommended outcome (real index tuple) + confidence +
         acceptance probability + one-sentence rationale.

    Returns:
        {
          "recommended_outcome": tuple(int, int, int, int) or None,
          "offer_utility_to_self": float,
          "confidence": float,
          "acceptance_probability": float,
          "inferred_opponent_weights": dict[str, float],
          "why_one_sentence": str,
        }
    """
    seller_per_dim = _seller_utility_per_dim(_ALL_OUTCOMES_ARR)
    buyer_per_dim = _buyer_utility_per_dim(_ALL_OUTCOMES_ARR)

    my_w_vec = np.array([my_weights[n] for n in ISSUE_NAMES])
    my_w_vec = my_w_vec / my_w_vec.sum()  # ensure normalized
    u_self = seller_per_dim @ my_w_vec  # shape (N,)

    if opp_offer_history:
        # Sequential Bayesian update over the FULL history, not just the latest
        # offer. Each successive offer further refines the posterior. This is
        # the v2 fix: against a slow-conceder (Silent Hardliner), the latest
        # offer changes very little round-to-round, so the v1 single-anchor
        # filter never updated. Iterating over ALL offers compounds evidence.
        b_filter = BayesianParticleFilter(
            num_variables=4,
            num_particles=500,
            uncertainty=0.2,
        )
        for raw_offer in opp_offer_history:
            offer_arr = np.array(raw_offer, dtype=np.int32).reshape(1, 4)
            anchor_features = _buyer_utility_per_dim(offer_arr)[0]  # shape (4,)
            b_filter.update_beliefs(anchor_features, buyer_per_dim)
        opp_weights = b_filter.get_inferred_weights()
        opp_weights = opp_weights / opp_weights.sum()
        # Confidence: low particle-cloud spread → high confidence.
        # With more offers folded in, the filter should be tighter than v1.
        spread = float(np.std(b_filter.particles, axis=0).mean())
        confidence = float(np.clip(1.0 - spread * 2.5, 0.05, 0.95))
    else:
        # Cold start: tournament Dirichlet mean for buyer
        opp_weights = np.array([0.20, 0.30, 0.40, 0.10])
        confidence = 0.30

    u_opp = buyer_per_dim @ opp_weights  # shape (N,)

    pareto_idx = filter_pareto_frontier(_ALL_OUTCOMES_ARR.astype(np.float64), u_self, u_opp)
    # Opponent BATNA estimated, not observed → Bayesian-Nash, not classical Nash.
    best_idx = find_nash_bargaining_solution(
        pareto_idx, u_self, u_opp, my_batna, opp_batna_estimate,
        batna_b_inferred=True,
    )

    inferred_weights_dict = {n: float(w) for n, w in zip(ISSUE_NAMES, opp_weights)}

    if best_idx is None:
        return {
            "recommended_outcome": None,
            "offer_utility_to_self": float(my_batna),
            "confidence": confidence,
            "acceptance_probability": 0.10,
            "inferred_opponent_weights": inferred_weights_dict,
            "why_one_sentence": "No viable Nash solution given current state; recommending walk-away.",
        }

    rec_outcome = tuple(int(x) for x in _ALL_OUTCOMES_ARR[best_idx])
    rec_u_self = float(u_self[best_idx])
    rec_u_opp = float(u_opp[best_idx])
    accept_prob = float(np.clip(
        (rec_u_opp - opp_batna_estimate) / (1.0 - opp_batna_estimate + 1e-9),
        0.05, 0.95,
    ))

    why = (
        f"Nash-optimal across all 4 dimensions at "
        f"price={rec_outcome[0]}, delivery={rec_outcome[1]}, "
        f"warranty={rec_outcome[2]}, payment={rec_outcome[3]}: "
        f"your utility {rec_u_self:.2f}, opponent expected utility {rec_u_opp:.2f}. "
        f"Inferred opponent priorities: "
        f"price={inferred_weights_dict['price']:.2f}, "
        f"delivery={inferred_weights_dict['delivery']:.2f}, "
        f"warranty={inferred_weights_dict['warranty']:.2f}, "
        f"payment={inferred_weights_dict['payment']:.2f}."
    )

    return {
        "recommended_outcome": rec_outcome,
        "offer_utility_to_self": rec_u_self,
        "confidence": confidence,
        "acceptance_probability": accept_prob,
        "inferred_opponent_weights": inferred_weights_dict,
        "why_one_sentence": why,
    }


# ─── LLM negotiator (base class) ────────────────────────────────────────────


class _OutcomeProposal(BaseModel):
    """Schema the LLM returns for its next move."""
    price: int = Field(description="Price index 0-49 (higher = better for seller)", ge=0, le=49)
    delivery: int = Field(description="Delivery index 0-4 (higher = faster, better for buyer)", ge=0, le=4)
    warranty: int = Field(description="Warranty index 0-3 (higher = longer, better for buyer)", ge=0, le=3)
    payment: int = Field(description="Payment terms index 0-2 (higher = faster, better for seller)", ge=0, le=2)
    accept_opponent_offer: bool = Field(description="True iff you want to accept the opponent's last offer instead of proposing", default=False)


class _LLMNegotiatorBase(SAONegotiator):
    """
    Shared scaffolding for the LLM-driven competitors.

    Each NegMAS SAO turn (after the first) goes:
      1. respond(state)  — NegMAS shows us the opponent's latest offer
      2. propose(state)  — only called if respond returned REJECT

    To keep cost flat at ~1 LLM call per turn (not 2), we use a one-call-per-turn
    pattern: respond() makes ONE LLM call asking for both decisions ("accept this
    offer? if not, what's your counter?"). The result is cached on the instance.
    propose() consumes the cached counter without a second LLM call.

    On the very first turn (we go first, no opponent offer yet), only propose() is
    called and it makes its own LLM call.
    """
    USE_SNHP: bool = False
    LLM_TEMPERATURE: float = 0.3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_offers: list = []
        self._opp_offers: list = []
        self._llm_call_count: int = 0
        self._llm_call_log: list = []
        self._cached_decision: Optional[dict] = None
        self._cached_decision_fresh: bool = False

    # ─── State helpers ─────────────────────────────────────────────────

    def _my_util(self, offer) -> float:
        if offer is None or self.ufun is None:
            return 0.0
        u = self.ufun(offer)
        return float(u) if u is not None else 0.0

    def _format_offer(self, offer) -> str:
        if offer is None:
            return "(none)"
        d = dict(zip(ISSUE_NAMES, offer))
        return (f"price={d['price']}, delivery={d['delivery']}, "
                f"warranty={d['warranty']}, payment={d['payment']}")

    def _build_history_block(self) -> str:
        lines = []
        n = max(len(self._my_offers), len(self._opp_offers))
        for i in range(n):
            mine = self._my_offers[i] if i < len(self._my_offers) else None
            theirs = self._opp_offers[i] if i < len(self._opp_offers) else None
            line = f"  Round {i+1}:"
            if mine is not None:
                line += (f"\n    You proposed: {self._format_offer(mine)} "
                         f"(your utility: {self._my_util(mine):.2f})")
            if theirs is not None:
                line += (f"\n    Opponent proposed: {self._format_offer(theirs)} "
                         f"(your utility: {self._my_util(theirs):.2f})")
            lines.append(line)
        return "\n".join(lines) if lines else "  (no offers exchanged yet)"

    def _ufun_weights_by_name(self) -> dict:
        """
        NegMAS LinearAdditiveUtilityFunction stores weights as a POSITIONAL
        LIST (length = number of issues), not a name-keyed dict — keys get
        flattened during normalize(). Map back to names via ufun.issues.
        """
        if self.ufun is None or not hasattr(self.ufun, "weights"):
            return {n: 0.25 for n in ISSUE_NAMES}
        try:
            weights_list = list(self.ufun.weights)
            issue_names = [i.name for i in self.ufun.issues]
            raw = {name: float(w) for name, w in zip(issue_names, weights_list)}
        except Exception:
            return {n: 0.25 for n in ISSUE_NAMES}
        for n in ISSUE_NAMES:
            raw.setdefault(n, 0.0)
        s = sum(raw.values())
        if s > 0:
            raw = {k: v / s for k, v in raw.items()}
        return raw

    def _build_issues_block(self) -> str:
        """
        Concrete per-issue framing instead of raw index space.

        Each issue gets:
          - semantic description
          - direction of preference (HIGHER vs LOWER better for us)
          - explicit utility mapping with worked examples
          - our weight on this issue
        """
        weights = self._ufun_weights_by_name()

        return f"""  price (integer 0-49): contract price tier.
    HIGHER index = more revenue for you (the seller).
    Per-issue utility = price / 49.
    Examples: price=0 → 0% utility from price; price=25 → 51%; price=49 → 100%.
    Your weight on this issue: {weights['price']:.2f}

  delivery (integer 0-4): how much delivery time you get.
    HIGHER index = MORE delivery time = LESS pressure on you = BETTER for you.
    (Buyer wants the opposite — they want fast delivery, i.e. low delivery index.)
    Per-issue utility = delivery / 4.
    Examples: delivery=0 → 0%; delivery=2 → 50%; delivery=4 → 100%.
    Your weight on this issue: {weights['delivery']:.2f}

  warranty (integer 0-3): warranty length you must honor.
    LOWER index = shorter warranty = LESS obligation = BETTER for you.
    (Buyer wants the opposite — they want long warranty.)
    Per-issue utility = (3 - warranty) / 3.
    Examples: warranty=0 → 100%; warranty=1 → 67%; warranty=3 → 0%.
    Your weight on this issue: {weights['warranty']:.2f}

  payment (integer 0-2): payment delay (how long before you get paid).
    LOWER index = faster payment = BETTER for you.
    (Buyer wants the opposite — slow payment helps their cash flow.)
    Per-issue utility = (2 - payment) / 2.
    Examples: payment=0 → 100%; payment=1 → 50%; payment=2 → 0%.
    Your weight on this issue: {weights['payment']:.2f}

  Your TOTAL utility for an outcome = sum across issues of (weight × per-issue utility).
  All values stay in [0, 1]."""

    # ─── SNHP recommendation (only used if USE_SNHP) ───────────────────

    def _snhp_hint(self) -> Optional[dict]:
        if not self.USE_SNHP or self.ufun is None or not hasattr(self.ufun, "weights"):
            return None
        my_weights = self._ufun_weights_by_name()
        if sum(my_weights.values()) == 0:
            return None
        my_batna = float(getattr(self.ufun, "reserved_value", 0.40) or 0.40)
        try:
            return snhp_propose_offer_v1(
                my_weights=my_weights,
                opp_offer_history=[tuple(o) for o in self._opp_offers if o is not None],
                my_batna=my_batna,
                opp_batna_estimate=0.40,
            )
        except Exception as e:
            # Math should never fail in practice; if it does, return a soft
            # fallback so the LLM still has SOMETHING to work with rather than
            # crashing the trial.
            print(f"[warn] SNHP math failed: {e}", file=sys.stderr)
            return None

    def _build_snhp_block(self) -> str:
        hint = self._snhp_hint()
        if hint is None:
            return ""
        rec = hint["recommended_outcome"]
        if rec is None:
            rec_str = "(no Nash solution — recommend walking away)"
        else:
            rec_str = (f"price={rec[0]}, delivery={rec[1]}, "
                       f"warranty={rec[2]}, payment={rec[3]}")
        return f"""
SNHP OPTIMIZATION ENGINE RECOMMENDATION (you may follow, modify, or ignore):
  Recommended outcome: {rec_str}
  Your utility from this recommendation: {hint['offer_utility_to_self']:.2f}
  Confidence in the math: {hint['confidence']:.2f}
  Estimated probability the opponent accepts: {hint['acceptance_probability']:.2f}
  Reasoning: {hint['why_one_sentence']}
"""

    # ─── Prompt building ───────────────────────────────────────────────

    def _build_prompt(self, state: SAOState) -> str:
        n_steps = getattr(self.nmi, "n_steps", 10)
        step = getattr(state, "step", 0)
        time_remaining = max(0, n_steps - step)
        batna = float(getattr(self.ufun, "reserved_value", 0.40) or 0.40)

        opp_last = state.current_offer
        if opp_last is not None:
            opp_block = (
                f"\nOPPONENT'S LATEST OFFER (currently on the table):\n"
                f"  {self._format_offer(tuple(opp_last))}\n"
                f"  Your utility from accepting this: {self._my_util(opp_last):.3f}\n"
                f"  Your BATNA (walk-away utility): {batna:.3f}\n"
            )
            decision_prompt = (
                "You must decide TWO things in one shot:\n"
                "  1. accept_opponent_offer: should you ACCEPT the opponent's "
                "latest offer above? Set true if accepting it is better than "
                "your realistic prospects of getting a meaningfully better "
                "deal in the time remaining.\n"
                "  2. price/delivery/warranty/payment: your COUNTER-OFFER if "
                "you reject. Even if you set accept=true, fill these in with "
                "what you would have proposed (will be ignored)."
            )
        else:
            opp_block = "\n(No opponent offer yet — you're proposing first.)\n"
            decision_prompt = (
                "Propose your OPENING offer. accept_opponent_offer must be false."
            )

        return f"""You are an experienced B2B SELLER negotiating a contract.

ISSUES IN PLAY (4 dimensions, all integer indices):

{self._build_issues_block()}

YOUR WALK-AWAY (BATNA): {batna:.3f}
TIME REMAINING: {time_remaining} of {n_steps} rounds.

NEGOTIATION HISTORY:
{self._build_history_block()}
{opp_block}{self._build_snhp_block()}

DECISION:
{decision_prompt}

Return ONLY a JSON object with fields: price, delivery, warranty, payment,
accept_opponent_offer. Reason carefully about the tradeoffs across all 4
issues and the time pressure."""

    # ─── Single LLM call per turn ──────────────────────────────────────

    LLM_MAX_RETRIES: int = 4
    LLM_RETRY_BASE_DELAY_S: float = 2.0

    def _llm_decide(self, state: SAOState) -> dict:
        """
        Make one LLM call asking BOTH "accept the opponent offer?" and
        "what's your counter?". Returns the parsed proposal dict.

        Retries on transient errors (503, 429, timeouts) with exponential
        backoff so a brief Gemini capacity blip doesn't corrupt a trial
        with a fallback "middle-of-road" offer.
        """
        prompt = self._build_prompt(state)
        t0 = time.time()
        result = None
        last_exc: Optional[Exception] = None

        for attempt in range(self.LLM_MAX_RETRIES + 1):
            try:
                result = _call_llm(prompt, _OutcomeProposal, temperature=self.LLM_TEMPERATURE)
                break
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                # Retry on transient capacity / rate / timeout errors. Don't
                # retry on schema violations or auth — those are permanent.
                transient = any(s in msg for s in ("503", "429", "unavailable",
                                                   "timeout", "rate limit",
                                                   "deadline exceeded"))
                if not transient or attempt >= self.LLM_MAX_RETRIES:
                    print(f"[warn] {self.__class__.__name__} LLM call failed "
                          f"after {attempt + 1} attempts: {e}", file=sys.stderr)
                    break
                delay = self.LLM_RETRY_BASE_DELAY_S * (2 ** attempt)
                print(f"[retry {attempt + 1}/{self.LLM_MAX_RETRIES}] "
                      f"{self.__class__.__name__} transient LLM error, "
                      f"backing off {delay:.1f}s: {type(e).__name__}",
                      file=sys.stderr)
                time.sleep(delay)

        if result is None:
            # Fallback only after retries exhausted. Mark this trial's data
            # as fallback-tainted so aggregation can flag it.
            result = {
                "price": ISSUE_CARDINALITIES["price"] // 2,
                "delivery": ISSUE_CARDINALITIES["delivery"] // 2,
                "warranty": ISSUE_CARDINALITIES["warranty"] // 2,
                "payment": ISSUE_CARDINALITIES["payment"] // 2,
                "accept_opponent_offer": False,
                "_fallback": True,
            }

        self._llm_call_count += 1
        self._llm_call_log.append({
            "step": getattr(state, "step", -1),
            "elapsed_s": time.time() - t0,
            "prompt_chars": len(prompt),
            "fallback": result.get("_fallback", False) if isinstance(result, dict) else False,
        })

        proposal = result if isinstance(result, dict) else result.dict()
        # Defensive bounds-clamp on every field
        proposal["price"] = int(max(0, min(ISSUE_CARDINALITIES["price"] - 1,
                                            int(proposal.get("price", 0)))))
        proposal["delivery"] = int(max(0, min(ISSUE_CARDINALITIES["delivery"] - 1,
                                               int(proposal.get("delivery", 0)))))
        proposal["warranty"] = int(max(0, min(ISSUE_CARDINALITIES["warranty"] - 1,
                                               int(proposal.get("warranty", 0)))))
        proposal["payment"] = int(max(0, min(ISSUE_CARDINALITIES["payment"] - 1,
                                              int(proposal.get("payment", 0)))))
        proposal["accept_opponent_offer"] = bool(proposal.get("accept_opponent_offer", False))
        return proposal

    # ─── propose / respond ─────────────────────────────────────────────

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        offer = state.current_offer
        if offer is not None:
            self._opp_offers.append(tuple(offer))
        # No opponent offer yet (rare on respond) → defensively reject
        if offer is None:
            return ResponseType.REJECT_OFFER

        decision = self._llm_decide(state)
        self._cached_decision = decision
        self._cached_decision_fresh = True

        if decision.get("accept_opponent_offer", False):
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def propose(self, state: SAOState) -> Optional[Outcome]:
        # Reuse cached decision from this turn's respond() call if fresh.
        # Step number can shift between respond() and propose() inside one
        # NegMAS turn; we use a freshness flag instead of step matching.
        if self._cached_decision is not None and self._cached_decision_fresh:
            decision = self._cached_decision
            self._cached_decision = None
            self._cached_decision_fresh = False
        else:
            # First-turn case (no opponent offer yet) — make our own LLM call
            decision = self._llm_decide(state)

        outcome = (
            decision["price"], decision["delivery"],
            decision["warranty"], decision["payment"],
        )
        self._my_offers.append(outcome)
        return outcome


class LLMWithSNHP(_LLMNegotiatorBase):
    USE_SNHP = True


class LLMNaive(_LLMNegotiatorBase):
    USE_SNHP = False


# ─── Programmatic competitor wrapper ────────────────────────────────────────


def _make_split_the_diff():
    """
    SplitTheDiff is a NegMAS class. Wrap it so we can collect call counts
    in the same uniform shape as the LLM negotiators.
    """
    class _SplitTheDiffTracked(SplitTheDiff):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._llm_call_count = 0
            self._llm_call_log = []

    return _SplitTheDiffTracked


# ─── Benchmark loop ─────────────────────────────────────────────────────────


@dataclass
class TrialResult:
    competitor: str
    opponent: str
    scenario_id: str
    scenario_batna: float
    agreement: Optional[tuple]
    seller_utility: float
    buyer_utility: float
    rounds_used: int
    walked_away: bool
    competitor_llm_calls: int
    elapsed_s: float
    fallback_calls: int = 0  # how many LLM calls fell through to neutral fallback (data taint flag)


# Default 4-opponent panel for the industry-standard run.
# All four are programmatic NegMAS bots from b2b_opponents.py — zero LLM cost.
# Picked to span behavior space:
#   Anchorer        — extreme opener, slow retreat (tactical/aggressive)
#   FairDemand      — cooperative baseline
#   SilentHardliner — slow conceder, tougher than Anchorer
#   TacticalEmpath  — Chris Voss style, mirrors and adapts
DEFAULT_OPPONENT_PANEL = ["Anchorer", "Fair Demand", "Silent Hardliner", "Tactical Empath"]

OPPONENT_REGISTRY = {
    name: B2B_OPPONENTS[name] for name in B2B_OPPONENTS
}


def play_one_trial(
    competitor_name: str,
    competitor_cls,
    scenario: Scenario,
    fixed_opponent_cls=Anchorer,
    opponent_name: str = "Anchorer",
) -> TrialResult:
    """
    Single negotiation: competitor (SELLER) vs fixed opponent (BUYER) on `scenario`.
    """
    np.random.seed(scenario.seed)
    issues = make_benchmark_issues()
    seller_ufun, buyer_ufun = make_seller_buyer_ufuns(
        scenario.seller_weights, scenario.buyer_weights,
        scenario.batna, scenario.n_steps,
    )

    seller = competitor_cls(name=f"seller_{competitor_name}_{scenario.scenario_id}")
    buyer = fixed_opponent_cls(name=f"buyer_anchorer_{scenario.scenario_id}")

    mech = SAOMechanism(issues=issues, n_steps=scenario.n_steps)
    mech.add(seller, ufun=seller_ufun)
    mech.add(buyer, ufun=buyer_ufun)

    t0 = time.time()
    try:
        result = mech.run()
    except Exception as e:
        print(f"[warn] {competitor_name} on {scenario.scenario_id} crashed: {e}", file=sys.stderr)
        log = getattr(seller, "_llm_call_log", []) or []
        return TrialResult(
            competitor=competitor_name, opponent=opponent_name,
            scenario_id=scenario.scenario_id,
            scenario_batna=scenario.batna,
            agreement=None, seller_utility=scenario.batna, buyer_utility=scenario.batna,
            rounds_used=0, walked_away=True,
            competitor_llm_calls=getattr(seller, "_llm_call_count", 0),
            elapsed_s=time.time() - t0,
            fallback_calls=sum(1 for entry in log if entry.get("fallback", False)),
        )

    if result.agreement is not None:
        u_seller_raw = seller_ufun(result.agreement)
        u_buyer_raw = buyer_ufun(result.agreement)
        u_seller = float(u_seller_raw) if u_seller_raw is not None else scenario.batna
        u_buyer = float(u_buyer_raw) if u_buyer_raw is not None else scenario.batna
        walked = False
    else:
        u_seller = scenario.batna
        u_buyer = scenario.batna
        walked = True

    log = getattr(seller, "_llm_call_log", []) or []
    return TrialResult(
        competitor=competitor_name,
        opponent=opponent_name,
        scenario_id=scenario.scenario_id,
        scenario_batna=scenario.batna,
        agreement=tuple(result.agreement) if result.agreement is not None else None,
        seller_utility=u_seller,
        buyer_utility=u_buyer,
        rounds_used=getattr(result, "step", scenario.n_steps),
        walked_away=walked,
        competitor_llm_calls=getattr(seller, "_llm_call_count", 0),
        elapsed_s=time.time() - t0,
        fallback_calls=sum(1 for entry in log if entry.get("fallback", False)),
    )


COMPETITOR_REGISTRY = {
    "LLM_with_SNHP": LLMWithSNHP,
    "LLM_naive": LLMNaive,
    "SplitTheDiff": _make_split_the_diff(),
}


# ─── Aggregation ─────────────────────────────────────────────────────────────


def _compute_competitor_summary(ts: list[TrialResult]) -> dict:
    """Headline metrics for a single competitor's trial list."""
    n = len(ts)
    deals = [t for t in ts if not t.walked_away]
    below_batna_closes = [t for t in deals if t.seller_utility < t.scenario_batna]
    tainted = [t for t in ts if t.fallback_calls > 0]
    seller_utils = [t.seller_utility for t in ts]
    deal_seller_utils = [t.seller_utility for t in deals]
    buyer_utils = [t.buyer_utility for t in ts]
    surplus = [t.seller_utility - t.scenario_batna for t in ts]
    surplus_dealsonly = [t.seller_utility - t.scenario_batna for t in deals]

    # Bootstrap 95% CI on the surplus distribution — the headline metric.
    surplus_mean, surplus_ci_lo, surplus_ci_hi = bootstrap_ci(surplus) if surplus else (0.0, 0.0, 0.0)

    # Same metric computed with tainted trials excluded
    clean_surplus = [t.seller_utility - t.scenario_batna for t in ts if t.fallback_calls == 0]
    clean_mean, clean_ci_lo, clean_ci_hi = bootstrap_ci(clean_surplus) if clean_surplus else (0.0, 0.0, 0.0)

    return {
        "n_trials": n,
        "n_deals_closed": len(deals),
        "n_below_batna_closes": len(below_batna_closes),
        "n_walked_away": n - len(deals),
        "n_tainted_trials": len(tainted),
        "deal_closed_rate": len(deals) / n if n else 0.0,
        "below_batna_close_rate": len(below_batna_closes) / n if n else 0.0,
        "tainted_rate": len(tainted) / n if n else 0.0,
        "avg_seller_utility_all_trials": statistics.mean(seller_utils) if seller_utils else 0.0,
        "avg_seller_utility_dealsonly": statistics.mean(deal_seller_utils) if deal_seller_utils else 0.0,
        "avg_buyer_utility_all_trials": statistics.mean(buyer_utils) if buyer_utils else 0.0,
        "avg_surplus_capture_all_trials": statistics.mean(surplus) if surplus else 0.0,
        "avg_surplus_capture_dealsonly": statistics.mean(surplus_dealsonly) if surplus_dealsonly else 0.0,
        "surplus_capture_95ci_lo": surplus_ci_lo,
        "surplus_capture_95ci_hi": surplus_ci_hi,
        # Untainted-only versions of the headline metrics
        "n_untainted_trials": len(clean_surplus),
        "avg_surplus_capture_untainted": clean_mean,
        "surplus_capture_untainted_95ci_lo": clean_ci_lo,
        "surplus_capture_untainted_95ci_hi": clean_ci_hi,
        "avg_rounds_used": statistics.mean([t.rounds_used for t in ts]) if ts else 0.0,
        "total_llm_calls": sum(t.competitor_llm_calls for t in ts),
        "total_wall_clock_s": sum(t.elapsed_s for t in ts),
    }


def aggregate_results(trials: list[TrialResult]) -> dict:
    """
    Three primary numbers per competitor:
      - deal_closed_rate: did we get a deal at all? Any deal above BATNA
        is rationally good — even barely above is positive surplus.
      - below_batna_close_rate: agent failure indicator. A rational agent
        should NEVER close below its walk-away utility (strictly worse
        than walking).
      - avg_surplus_capture (with 95% bootstrap CI): the quantitative
        differentiator. Bigger surplus is always better.

    Plus per-(competitor × opponent) breakdown so we can see whether SNHP
    generalizes across opponent types or is just beating one specific bot.

    Plus pairwise Wilcoxon signed-rank tests on per-scenario surplus
    differences — answers "is competitor A's advantage statistically
    significant vs competitor B?" Both helpers (bootstrap_ci,
    wilcoxon_approx) are reused from b2b_round_robin.py.
    """
    by_competitor: dict = {}
    by_competitor_opponent: dict = {}
    for t in trials:
        by_competitor.setdefault(t.competitor, []).append(t)
        by_competitor_opponent.setdefault((t.competitor, t.opponent), []).append(t)

    aggregate_by_competitor = {
        name: _compute_competitor_summary(ts) for name, ts in by_competitor.items()
    }

    aggregate_by_competitor_x_opponent = {
        f"{comp}__vs__{opp}": _compute_competitor_summary(ts)
        for (comp, opp), ts in by_competitor_opponent.items()
    }

    # Pairwise Wilcoxon signed-rank on surplus, paired by (scenario_id, opponent).
    # We want PAIRED tests — same scenarios + same opponents, different competitors.
    competitors_list = sorted(by_competitor.keys())
    pairwise: dict = {}
    for i, a in enumerate(competitors_list):
        for b in competitors_list[i+1:]:
            # Build paired surplus arrays keyed by (scenario_id, opponent)
            paired_a, paired_b = [], []
            a_index = {(t.scenario_id, t.opponent): t for t in by_competitor[a]}
            b_index = {(t.scenario_id, t.opponent): t for t in by_competitor[b]}
            common_keys = sorted(set(a_index.keys()) & set(b_index.keys()))
            for k in common_keys:
                paired_a.append(a_index[k].seller_utility - a_index[k].scenario_batna)
                paired_b.append(b_index[k].seller_utility - b_index[k].scenario_batna)
            if len(paired_a) >= 5:
                p_value = wilcoxon_approx(paired_a, paired_b)
                mean_diff = statistics.mean([x - y for x, y in zip(paired_a, paired_b)])
                pairwise[f"{a}__vs__{b}"] = {
                    "n_paired": len(paired_a),
                    "mean_surplus_diff": round(mean_diff, 4),
                    "wilcoxon_p_value": round(p_value, 4),
                    "significant_at_005": p_value < 0.05,
                    "favors": a if mean_diff > 0 else (b if mean_diff < 0 else "tie"),
                }
            else:
                pairwise[f"{a}__vs__{b}"] = {
                    "n_paired": len(paired_a),
                    "note": "insufficient paired samples for Wilcoxon (need >= 5)",
                }

    return {
        "by_competitor": aggregate_by_competitor,
        "by_competitor_x_opponent": aggregate_by_competitor_x_opponent,
        "pairwise_significance": pairwise,
    }


# ─── Cost estimation ────────────────────────────────────────────────────────


def estimate_cost(competitors: list[str], n_scenarios: int, n_opponents: int = 1,
                  avg_turns_per_scenario: float = 5.0,
                  model: Optional[str] = None) -> dict:
    """
    Thin wrapper around snhp.cost_calculator.estimate_run_cost.
    Centralizes pricing + token estimates in one tested module.
    """
    n_llm_competitors = sum(1 for c in competitors if c.startswith("LLM_"))
    if model is None:
        # Strip the "gemini/" provider prefix if present
        env_model = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
        model = env_model.split("/")[-1]
    return _calc_estimate_run_cost(
        n_scenarios=n_scenarios,
        n_opponents=n_opponents,
        n_llm_competitors=n_llm_competitors,
        avg_calls_per_trial=avg_turns_per_scenario,
        avg_input_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens,
        avg_output_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens,
        model=model,
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenarios", type=int, default=30, help="Number of scenarios. Default 30.")
    parser.add_argument(
        "--competitors", default="LLM_with_SNHP,LLM_naive,SplitTheDiff",
        help="Comma-separated subset of competitors to run.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output", default=os.path.join(os.path.dirname(_THIS_DIR), "results", "snhp_benchmark.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print cost estimate and exit without making LLM calls.",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help=("Concurrent trial workers (parallelizes LLM-bound trials). "
              "Default 4 — Gemini 3 Flash Preview returns 503s under heavier "
              "concurrency. Bump if your model + tier handle it."),
    )
    parser.add_argument(
        "--model", default=None,
        help=("Override Gemini model id (sets SNHP_LLM_MODEL). "
              "Default: gemini/gemini-3-flash-preview from .env or fallback."),
    )
    parser.add_argument(
        "--opponents", default=",".join(DEFAULT_OPPONENT_PANEL),
        help=(f"Comma-separated panel of fixed opponents from b2b_opponents.B2B_OPPONENTS. "
              f"Default panel ({len(DEFAULT_OPPONENT_PANEL)} bots): "
              f"{','.join(DEFAULT_OPPONENT_PANEL)}. "
              f"For a single-opponent run (faster, less robust), pass e.g. --opponents Anchorer."),
    )
    args = parser.parse_args()

    if args.model:
        os.environ["SNHP_LLM_MODEL"] = args.model

    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
    unknown = [c for c in competitors if c not in COMPETITOR_REGISTRY]
    if unknown:
        sys.exit(f"Unknown competitor(s): {unknown}. Available: {sorted(COMPETITOR_REGISTRY)}")

    opponents = [o.strip() for o in args.opponents.split(",") if o.strip()]
    unknown_opp = [o for o in opponents if o not in OPPONENT_REGISTRY]
    if unknown_opp:
        sys.exit(f"Unknown opponent(s): {unknown_opp}. Available: {sorted(OPPONENT_REGISTRY)}")

    active_model = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
    print(f"SNHP kill-criterion benchmark")
    print(f"  Competitors:    {competitors}")
    print(f"  Scenarios:      {args.scenarios}")
    print(f"  Opponent panel: {opponents}")
    print(f"  LLM model:      {active_model}")
    print(f"  Workers:        {args.workers}")
    print(f"  Output:         {args.output}")

    cost = estimate_cost(competitors, args.scenarios, n_opponents=len(opponents),
                         avg_turns_per_scenario=5.0)
    print(f"\nCost estimate (via snhp.cost_calculator, model={cost['model']})")
    print(f"  LLM trials:         {cost['n_llm_trials']}")
    print(f"  Total LLM calls:    {cost['total_llm_calls']}")
    print(f"  Per-call cost:      ${cost['per_call_cost_usd']:.6f}")
    print(f"  TOTAL ESTIMATE:     ${cost['total_cost_usd']:.4f}")

    if args.dry_run:
        print("\n--dry-run: exiting before running benchmark.")
        return

    if not os.environ.get("GOOGLE_API_KEY") and any(c.startswith("LLM_") for c in competitors):
        sys.exit("GOOGLE_API_KEY not set; cannot run LLM competitors. Set it or use --competitors SplitTheDiff")

    print("\nGenerating scenarios...")
    scenarios = generate_scenarios(args.scenarios, seed=args.seed)

    # Build the full job list up front so we can parallelize.
    # Each job: (competitor_name, competitor_cls, opponent_name, opponent_cls, scenario)
    jobs: list[tuple[str, type, str, type, Scenario]] = []
    for comp_name in competitors:
        comp_cls = COMPETITOR_REGISTRY[comp_name]
        for opp_name in opponents:
            opp_cls = OPPONENT_REGISTRY[opp_name]
            for sc in scenarios:
                jobs.append((comp_name, comp_cls, opp_name, opp_cls, sc))
    # Shuffle so a slow competitor doesn't starve the worker pool of work for
    # other competitors. Seeded for reproducibility — job ORDER doesn't affect
    # results, only which trials complete first under partial runs.
    import random as _r
    _r.Random(args.seed).shuffle(jobs)
    n_total = len(jobs)

    print(f"Running {len(competitors)} competitors × {len(opponents)} opponents × "
          f"{len(scenarios)} scenarios = {n_total} trials with {args.workers} parallel workers...")
    print(f"  (each LLM trial makes ~5 sequential Gemini calls; "
          f"trials run in parallel.)\n")
    t0 = time.time()
    trials: list[TrialResult] = []
    completed = 0

    def _run_job(job):
        comp_name, comp_cls, opp_name, opp_cls, sc = job
        t_trial = time.time()
        trial = play_one_trial(comp_name, comp_cls, sc,
                               fixed_opponent_cls=opp_cls,
                               opponent_name=opp_name)
        return job, trial, time.time() - t_trial

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_job = {pool.submit(_run_job, job): job for job in jobs}
        for fut in as_completed(future_to_job):
            job = future_to_job[fut]
            comp_name, _, opp_name, _, sc = job
            completed += 1
            try:
                _, trial, trial_elapsed = fut.result()
                trials.append(trial)
                outcome_str = "deal" if not trial.walked_away else "walk"
                print(f"  [{completed:4d}/{n_total}] {comp_name:<14} vs {opp_name:<16} "
                      f"{sc.scenario_id} → {outcome_str:4} "
                      f"util={trial.seller_utility:.3f} rounds={trial.rounds_used} "
                      f"llm={trial.competitor_llm_calls} "
                      f"({trial_elapsed:.1f}s, total {time.time() - t0:.1f}s)",
                      flush=True)
            except Exception as e:
                print(f"  [{completed:4d}/{n_total}] {comp_name:<14} vs {opp_name:<16} "
                      f"{sc.scenario_id} → FAILED: {e}",
                      file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)

    aggregate = aggregate_results(trials)
    by_comp = aggregate["by_competitor"]
    by_comp_x_opp = aggregate["by_competitor_x_opponent"]
    pairwise = aggregate["pairwise_significance"]

    print("\n" + "=" * 110)
    print("RESULTS — by competitor (aggregated across all opponents)")
    print("=" * 110)
    print(f"  Below-BATNA = deal closed but seller utility < scenario BATNA (agent failure mode)")
    print(f"  Surplus     = seller utility - scenario BATNA. Bracketed = 95% bootstrap CI.")
    print()
    print(f"{'Competitor':<16} {'N':>5} {'Deal%':>7} {'<BATNA%':>9} "
          f"{'Avg Util':>10} {'Surplus':>10} {'95% CI':>22} {'Rounds':>7} {'LLM':>6}")
    print("-" * 110)
    for name in competitors:
        a = by_comp.get(name, {})
        ci_lo = a.get('surplus_capture_95ci_lo', 0)
        ci_hi = a.get('surplus_capture_95ci_hi', 0)
        print(f"{name:<16} {a.get('n_trials', 0):>5} "
              f"{a.get('deal_closed_rate', 0)*100:>6.1f}% "
              f"{a.get('below_batna_close_rate', 0)*100:>8.1f}% "
              f"{a.get('avg_seller_utility_all_trials', 0):>10.4f} "
              f"{a.get('avg_surplus_capture_all_trials', 0):>+10.4f} "
              f"[{ci_lo:>+7.4f}, {ci_hi:>+7.4f}] "
              f"{a.get('avg_rounds_used', 0):>7.1f} "
              f"{a.get('total_llm_calls', 0):>6}")

    if len(opponents) > 1:
        print("\n" + "=" * 110)
        print("RESULTS — by competitor × opponent (does SNHP generalize across opponent types?)")
        print("=" * 110)
        print(f"{'Competitor':<16} {'Opponent':<18} {'N':>4} {'Surplus':>10} {'95% CI':>22} {'Deal%':>7}")
        print("-" * 110)
        for comp in competitors:
            for opp in opponents:
                key = f"{comp}__vs__{opp}"
                a = by_comp_x_opp.get(key, {})
                ci_lo = a.get('surplus_capture_95ci_lo', 0)
                ci_hi = a.get('surplus_capture_95ci_hi', 0)
                print(f"{comp:<16} {opp:<18} {a.get('n_trials', 0):>4} "
                      f"{a.get('avg_surplus_capture_all_trials', 0):>+10.4f} "
                      f"[{ci_lo:>+7.4f}, {ci_hi:>+7.4f}] "
                      f"{a.get('deal_closed_rate', 0)*100:>6.1f}%")

    print("\n" + "=" * 110)
    print("PAIRWISE SIGNIFICANCE (Wilcoxon signed-rank, paired by scenario × opponent, α=0.05)")
    print("=" * 110)
    print(f"{'Comparison':<40} {'N pairs':>8} {'Mean diff':>11} {'p-value':>10} {'Result':>20}")
    print("-" * 110)
    for pair_key, pair_data in pairwise.items():
        if "wilcoxon_p_value" in pair_data:
            sig_marker = "✓ SIGNIFICANT" if pair_data["significant_at_005"] else "(n.s.)"
            print(f"{pair_key:<40} {pair_data['n_paired']:>8} "
                  f"{pair_data['mean_surplus_diff']:>+11.4f} "
                  f"{pair_data['wilcoxon_p_value']:>10.4f} "
                  f"{sig_marker + ' favors ' + pair_data['favors']:>20}")
        else:
            print(f"{pair_key:<40} {pair_data.get('n_paired', 0):>8} "
                  f"{'(insufficient samples)':>50}")

    out_payload = {
        "metadata": {
            "model": active_model,
            "competitors": competitors,
            "opponents": opponents,
            "n_scenarios": len(scenarios),
            "seed": args.seed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wall_clock_seconds": time.time() - t0,
        },
        "cost_estimate_at_start": cost,
        "aggregate": aggregate,
        "trials": [asdict(t) for t in trials],
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(out_payload, f, indent=2, default=str)
    print(f"\nWrote {args.output} ({os.path.getsize(args.output)} bytes)")
    print(f"Total wall-clock: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

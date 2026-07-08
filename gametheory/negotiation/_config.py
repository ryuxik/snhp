"""
Single source of truth for every tunable parameter in the negotiation
advisor + LLM scaffold. Every value here:

  1. Has a stated rationale (theoretical | empirical | heuristic | magic-tunable)
  2. Has a search range for Optuna sweep (None if not tunable)
  3. Has a source (paper / experiment ID / "magic" if no anchor exists)
  4. Has an importance estimate (high | medium | low) — refined by sensitivity analysis
  5. Is overridable via env var SNHP_<UPPERCASE_NAME>

The principle: no constant in the negotiation code path is allowed to be
hidden. If a value isn't here, it's a bug. Adding a new constant requires
adding an entry here with the four pieces of metadata.

History: this file was created 2026-05-01 after the asymmetric N=20
experiment revealed that one hardcoded value (`pareto_knob=0.5` in
`llm_minimal_snhp.py`) was costing single-side SNHP customers −0.034
utility (p=0.98 wrong direction). The one-line fix to `pareto_knob=1.0`
flipped the asymmetric SNHP-side lift to +0.075 (p=0.006). This made
clear: hidden magic numbers are bugs waiting to happen.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Any, Optional


# ─── Parameter metadata ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParamMeta:
    """Metadata for one tunable parameter."""
    default: float
    rationale: str            # theoretical | empirical | heuristic | magic-tunable
    source: str               # paper | experiment ID | "magic" | "tradition"
    search_low: Optional[float] = None
    search_high: Optional[float] = None
    importance: str = "unknown"  # high | medium | low | unknown (refined by sensitivity)
    notes: str = ""


# ─── Adversarial-mode parameters (sell.py / buy.py non-peer path) ─────────


_ADVERSARIAL = {
    # ── Pareto-frontier endpoints (set the asp_start range) ────────────
    "asp_start_deal_rate_max": ParamMeta(
        default=0.55,
        rationale="empirical",
        source="snhp/pareto_frontier_seller.json (NSGA-II tuning, deferred)",
        search_low=0.45, search_high=0.70,
        importance="medium",
        notes="At pareto_knob=0, advisor opens at this value. Lower = more deal-rate-friendly. "
              "Currently only matters at knob<0.5 (we ship 1.0 default).",
    ),
    "asp_start_margin_max": ParamMeta(
        default=0.89,
        rationale="empirical",
        source="snhp/pareto_frontier_seller.json (NSGA-II tuning, deferred)",
        search_low=0.80, search_high=0.95,
        importance="high",
        notes="At pareto_knob=1, advisor opens at this value. Should ≈ vanilla LLM natural anchor "
              "(~0.85). T1 (asymm N=20, 2026-05-01) showed knob=1.0 → asp_start=0.89 yields "
              "+0.075 SNHP-A lift (p=0.006). Was 0.55 default → asp_start=0.72 → −0.034 loss.",
    ),

    # ── Schelling commitment floor ──────────────────────────────────────
    "schelling_buffer_abs": ParamMeta(
        default=0.05,
        rationale="magic-tunable",
        source="magic",
        search_low=0.02, search_high=0.15,
        importance="medium",
        notes="In `schelling_floor = my_reservation + min(this, 0.5*(1-rv))`. "
              "Sets the negotiating room above walk-away.",
    ),
    "schelling_buffer_rel": ParamMeta(
        default=0.50,
        rationale="magic-tunable",
        source="magic",
        search_low=0.30, search_high=0.70,
        importance="low",
        notes="Co-efficient in the relative-buffer term. Only binds when (1-rv) is small.",
    ),

    # ── Concession curve ────────────────────────────────────────────────
    "concession_exponent": ParamMeta(
        default=3.0,
        rationale="heuristic",
        source="negmas_agent.py inheritance",
        search_low=1.0, search_high=5.0,
        importance="high",
        notes="aspiration = asp_start - (asp_start - asp_floor) * t^exp. "
              "exp=1 linear, exp=3 cubic (most concession late). "
              "Phase A peer_cs experiment showed exp=2 better for short horizons; "
              "needs LLM-loop validation for adversarial path.",
    ),

    # ── Rubinstein equilibrium ──────────────────────────────────────────
    "rubinstein_my_discount": ParamMeta(
        default=0.95,
        rationale="magic-tunable",
        source="magic",
        search_low=0.85, search_high=0.99,
        importance="medium",
        notes="My time-discount factor. Higher = more patient. Should depend on horizon "
              "but currently fixed.",
    ),
    "rubinstein_opp_discount": ParamMeta(
        default=0.92,
        rationale="magic-tunable",
        source="magic",
        search_low=0.85, search_high=0.99,
        importance="medium",
        notes="Opponent discount factor. Asymmetry (0.92 vs my 0.95) is unjustified — "
              "we assume opp is more impatient, but that's not necessarily true.",
    ),

    # ── Opponent reservation estimate (the Bayesian inference output) ──
    "opp_rv_estimate_intercept": ParamMeta(
        default=0.40,
        rationale="magic-tunable",
        source="magic",
        search_low=0.20, search_high=0.55,
        importance="high",
        notes="opp_rv = clip(this - slope * inferred_opp_weight, lo, hi). "
              "Sets baseline assumption about opp's BATNA. If wrong, Rubinstein floor is wrong. "
              "Suspect after T1 — likely 2nd-bug after pareto_knob.",
    ),
    "opp_rv_estimate_slope": ParamMeta(
        default=0.20,
        rationale="magic-tunable",
        source="magic",
        search_low=0.0, search_high=0.50,
        importance="medium",
        notes="How much opp's inferred preference weight reduces our BATNA estimate of them.",
    ),
    "opp_rv_estimate_clip_low": ParamMeta(
        default=0.10,
        rationale="magic-tunable",
        source="magic",
        search_low=0.05, search_high=0.30,
        importance="low",
    ),
    "opp_rv_estimate_clip_high": ParamMeta(
        default=0.60,
        rationale="magic-tunable",
        source="magic",
        search_low=0.40, search_high=0.80,
        importance="low",
    ),

    # ── Concession-detection threshold ──────────────────────────────────
    "opp_concession_threshold": ParamMeta(
        default=0.05,
        rationale="magic-tunable",
        source="magic",
        search_low=0.02, search_high=0.20,
        importance="medium",
        notes="If opp's last_offer − first_offer > this, treat as conceder and use "
              "aspiration; otherwise hold at Rubinstein floor.",
    ),

    # ── Recommendation ceiling ──────────────────────────────────────────
    "recommended_ceiling_adversarial": ParamMeta(
        default=0.99,
        rationale="magic-tunable",
        source="magic",
        search_low=0.92, search_high=0.99,
        importance="low",
        notes="Hard cap on recommended target. Inconsistent with peer ceiling 0.97 — why?",
    ),

    # ── Acceptance probability heuristic ────────────────────────────────
    "accept_prob_clamp_low": ParamMeta(
        default=0.05,
        rationale="magic-tunable",
        source="magic",
        search_low=0.0, search_high=0.20,
        importance="low",
        notes="LLM scaffold ignores this for the accept decision; only affects expected_payoff "
              "shown in rationale. Architect flagged as decorative.",
    ),
    "accept_prob_clamp_high": ParamMeta(
        default=0.95,
        rationale="magic-tunable",
        source="magic",
        search_low=0.80, search_high=1.0,
        importance="low",
    ),

    # ── Bayesian filter ─────────────────────────────────────────────────
    "bayesian_n_particles": ParamMeta(
        default=500,
        rationale="heuristic",
        source="convention",
        search_low=200, search_high=2000,
        importance="low",
        notes="Particle count. Performance, not behavior. More particles ≠ better posterior "
              "since the underlying model is a 1D zero-sum projection.",
    ),
    "bayesian_uncertainty": ParamMeta(
        default=0.20,
        rationale="magic-tunable",
        source="magic",
        search_low=0.05, search_high=0.50,
        importance="medium",
        notes="Particle filter prior std. Higher = wider posterior. "
              "Affects how much opponent offers update the inference.",
    ),
    "bayesian_contract_grid_n": ParamMeta(
        default=50,
        rationale="heuristic",
        source="convention",
        search_low=20, search_high=200,
        importance="low",
        notes="Resolution of contract space discretization for filter updates.",
    ),
    "bayesian_confidence_slope": ParamMeta(
        default=2.5,
        rationale="magic-tunable",
        source="magic",
        search_low=1.0, search_high=5.0,
        importance="low",
        notes="confidence = clip(1 - spread*this, 0.05, 0.95). "
              "Confidence is reported but not load-bearing on decisions.",
    ),
}


# ─── Multi-issue bundle parameters (bundle.py) ─────────────────────────────


_BUNDLE = {
    "bundle_n_particles": ParamMeta(
        default=500,
        rationale="heuristic",
        source="convention",
        search_low=100, search_high=2000,
        importance="low",
        notes="Particle count for the multi-issue priority-inference filter. Performance, "
              "not behavior. Promoted from a bundle.py module constant so callers that run "
              "many bundle negotiations per second (the Evolution Arena) can trade a little "
              "posterior resolution for throughput via SNHP_BUNDLE_N_PARTICLES.",
    ),
    "bundle_prior_uncertainty": ParamMeta(
        default=0.20,
        rationale="magic-tunable",
        source="magic",
        search_low=0.05, search_high=0.50,
        importance="medium",
        notes="Prior std of the bundle priority-inference filter (was bundle.py "
              "_PRIOR_UNCERTAINTY). Higher = wider posterior, offers update priorities more.",
    ),
    # ── Multi-issue PEER path (negotiate_bundle peer_mode) ──────────────
    "bundle_peer_cooperation": ParamMeta(
        default=0.6,
        rationale="empirical",
        source="bundle_validation --peer paired sweep, 300 profiles (2026-07): "
               "coop 0.6 -> +1.9% joint welfare, 84% paired-win, fairness cost "
               "-0.006 (negligible); 1.0 lifts +2.1% but costs the worse-off "
               "party -0.024, so 0.6 is the lift/fairness knee.",
        search_low=0.0, search_high=1.0,
        importance="high",
        notes="Selection tilt for verified-peer multi-issue deals, in [0,1]. 0 = "
              "the adversarial Bayesian-Nash-product point; 1 = the joint-welfare-"
              "maximizing (utilitarian) Pareto point that still clears both TRUE "
              "BATNAs. The engine analog of the single-issue PEER playbook's "
              "'descend to the asymmetric Pareto outcome': two peers who exchange "
              "truthful BATNAs both select the efficient package and grow the pie "
              "without starving either side. Validated: bundle_validation --peer. "
              "This value is the DEFAULT tilt under peer_mode; callers can also pass "
              "negotiate_bundle(cooperation=...) directly (any [0,1], independent of "
              "peer_mode) to dial logrolling generosity — validated standalone in "
              "bundle_validation --cooperation.",
    ),
    "bundle_peer_signal_boost": ParamMeta(
        default=1.6,
        rationale="heuristic",
        source="mirrors _peer.py signaling (peer_max_self_target reveals priorities)",
        search_low=1.0, search_high=3.0,
        importance="medium",
        notes="On a peer opener (no counter-offers yet), the recommended package "
              "sharpens toward this side's top priorities by this factor, so the "
              "verified peer infers weights faster from the first offer — the "
              "multi-issue form of the PEER signaling phase.",
    ),
}


# ─── Peer-mode parameters (_peer.py) ───────────────────────────────────────


_PEER = {
    "peer_asp_start": ParamMeta(
        default=0.92,
        rationale="empirical",
        source="N=20 self-play tournament 2026-04 (+0.186 lift, p=0.0004)",
        search_low=0.80, search_high=0.97,
        importance="high",
        notes="Where descent starts (post-signaling). Empirical anchor was self-play; "
              "asymmetric not validated.",
    ),
    "peer_asp_floor": ParamMeta(
        default=0.55,
        rationale="empirical",
        source="N=20 self-play tournament 2026-04",
        search_low=0.40, search_high=0.70,
        importance="high",
        notes="Where descent terminates. Floor below this risks giving away surplus.",
    ),
    "peer_signaling_rounds": ParamMeta(
        default=2,
        rationale="heuristic",
        source="2026-05-01 peer_cs failure analysis",
        search_low=0, search_high=4,
        importance="high",
        notes="Number of max-self proposals before descent. peer_cs v1 used 1, "
              "discovered to make signaling a one-cycle lottery → reverted to 2.",
    ),
    "peer_max_self_target": ParamMeta(
        default=0.95,
        rationale="magic-tunable",
        source="magic",
        search_low=0.90, search_high=0.97,
        importance="medium",
        notes="What to recommend during signaling phase. Reveals preferences via offer "
              "issue values. Higher = stronger signal but risks rejection.",
    ),
    "peer_descent_exp": ParamMeta(
        default=3.0,
        rationale="heuristic",
        source="negmas_agent.py inheritance",
        search_low=1.0, search_high=5.0,
        importance="high",
        notes="Cubic descent. Similar parameter space as adversarial concession_exponent.",
    ),
    "peer_descent_offset": ParamMeta(
        default=0.20,
        rationale="magic-tunable",
        source="magic",
        search_low=0.0, search_high=0.50,
        importance="medium",
        notes="descent_t = max(0, (time_fraction - this) / (1 - this)). Defers descent "
              "start. Higher = later descent.",
    ),
    "peer_reservation_buffer": ParamMeta(
        default=0.05,
        rationale="magic-tunable",
        source="magic",
        search_low=0.02, search_high=0.15,
        importance="low",
        notes="recommended = max(my_reservation + this, ...). Min negotiating room.",
    ),
    "peer_recommended_ceiling": ParamMeta(
        default=0.97,
        rationale="magic-tunable",
        source="magic",
        search_low=0.92, search_high=0.99,
        importance="low",
        notes="Hard cap. Inconsistent with adversarial 0.99 — why?",
    ),
}


# ─── LLM-scaffold parameters (llm_minimal_snhp.py + llm_negotiator.py) ────


_SCAFFOLD = {
    "pareto_knob": ParamMeta(
        default=1.0,
        rationale="empirical",
        source="asymmetric_b2b_n20_T1 2026-05-01 (knob=1.0 yields +0.075 SNHP-A lift, p=0.006)",
        search_low=0.0, search_high=1.0,
        importance="high",
        notes="Linear interpolant between asp_start_deal_rate_max (0.55) and "
              "asp_start_margin_max (0.89). At 1.0, asp_start=0.89 ≈ vanilla LLM natural "
              "anchor. CHANGED from 0.5 default after T1 confirmed bug.",
    ),
    "llm_temperature": ParamMeta(
        default=0.2,
        rationale="empirical",
        source="convention",
        search_low=0.0, search_high=1.0,
        importance="medium",
        notes="Anthropic API temperature. Affects LLM stochasticity → run-to-run variance. "
              "Higher = more diverse decisions but worse reproducibility.",
    ),
    "outcome_picker_band": ParamMeta(
        default=0.05,
        rationale="magic-tunable",
        source="magic",
        search_low=0.01, search_high=0.15,
        importance="high",
        notes="In _pareto_outcome_at_util: outcomes within ±this of target are candidates "
              "for logrolling pick. Wider = more candidates = better logrolling but "
              "also bigger deviation from target.",
    ),
    "outcome_target_weight": ParamMeta(
        default=5.0,
        rationale="magic-tunable",
        source="magic",
        search_low=1.0, search_high=20.0,
        importance="medium",
        notes="In _pareto_outcome_at_util scoring: -|u_self - target|*this + opp_term. "
              "Higher = stricter target match.",
    ),
    "late_deadline_threshold": ParamMeta(
        default=0.95,
        rationale="heuristic",
        source="safety",
        search_low=0.85, search_high=0.99,
        importance="medium",
        notes="If t >= this AND offer >= rv + small, accept. Late-game safety net to avoid "
              "walk-aways from LLM stubbornness.",
    ),
    "late_deadline_buffer": ParamMeta(
        default=0.02,
        rationale="heuristic",
        source="safety",
        search_low=0.0, search_high=0.10,
        importance="low",
        notes="Acceptance buffer above reservation in late-deadline path.",
    ),
}


# ─── Combined config ───────────────────────────────────────────────────────


_REGISTRY: dict[str, ParamMeta] = {**_ADVERSARIAL, **_BUNDLE, **_PEER, **_SCAFFOLD}


def get_param(name: str) -> float:
    """Return the value for a parameter, respecting env-var overrides.

    Env var name: SNHP_<UPPERCASE_NAME>. Invalid values fall back to default
    with a warning.
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unknown parameter: {name}. Add it to _config.py with metadata.")
    meta = _REGISTRY[name]
    env_name = f"SNHP_{name.upper()}"
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return float(meta.default)
    try:
        v = float(raw)
        # Range-clip if a search range exists
        if meta.search_low is not None and meta.search_high is not None:
            return max(meta.search_low, min(meta.search_high, v))
        return v
    except ValueError:
        import warnings
        warnings.warn(
            f"Invalid env override {env_name}={raw!r}; using default {meta.default}.",
            stacklevel=2,
        )
        return float(meta.default)


def get_int_param(name: str) -> int:
    """Same as get_param but returns int (for signaling_rounds, n_particles, etc.)."""
    return int(get_param(name))


def all_params() -> dict[str, ParamMeta]:
    """Full parameter inventory for sensitivity analysis / Optuna."""
    return dict(_REGISTRY)


def params_by_importance(importance: str) -> dict[str, ParamMeta]:
    """Filter to params at a given importance level."""
    return {k: v for k, v in _REGISTRY.items() if v.importance == importance}


def magic_params() -> dict[str, ParamMeta]:
    """Params tagged as 'magic-tunable' — the highest-priority targets for tuning."""
    return {k: v for k, v in _REGISTRY.items() if v.rationale == "magic-tunable"}


def active_snapshot() -> dict[str, dict]:
    """Return the currently-active values for every parameter, plus
    whether each one is being overridden via env var. Useful for telemetry
    and for the /v1/internal/params endpoint."""
    out = {}
    for name, meta in _REGISTRY.items():
        env_name = f"SNHP_{name.upper()}"
        env_raw = os.environ.get(env_name, "").strip()
        active = get_param(name)
        out[name] = {
            "default": float(meta.default),
            "active": active,
            "overridden": bool(env_raw),
            "env_var": env_name,
            "rationale": meta.rationale,
            "source": meta.source,
            "importance": meta.importance,
        }
    return out


# ─── Self-test ─────────────────────────────────────────────────────────────


def _self_test():
    """Sanity check at import: every entry has required metadata, defaults are
    in [0, 100], search ranges (if set) bracket the default."""
    for name, meta in _REGISTRY.items():
        assert isinstance(meta.default, (int, float)), f"{name}: default not numeric"
        assert meta.rationale in ("theoretical", "empirical", "heuristic", "magic-tunable"), (
            f"{name}: invalid rationale {meta.rationale!r}"
        )
        assert meta.source, f"{name}: missing source"
        assert meta.importance in ("high", "medium", "low", "unknown"), (
            f"{name}: invalid importance {meta.importance!r}"
        )
        if meta.search_low is not None and meta.search_high is not None:
            assert meta.search_low <= meta.default <= meta.search_high, (
                f"{name}: default {meta.default} not in search [{meta.search_low}, {meta.search_high}]"
            )
            assert meta.search_low < meta.search_high, f"{name}: degenerate search range"


_self_test()

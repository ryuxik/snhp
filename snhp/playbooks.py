"""
Per-opponent-type playbook specs + belief-weighted parameter composition.

Five playbooks (one per detected opponent type + one HONEST default).
Each is a dict of (asp_start, asp_floor, accept_early_bar, commitment_margin,
concession_cap) tuned to the saddle-point response for that opponent class.

The composition function returns a belief-weighted blend per Nash's
"continuous-function-of-belief" critique — never argmax-dispatches.
Confidence floor 0.65 before any exploit weight is non-zero. Exploit
weight capped at 0.7 (always retain ≥30% honest tail).

Reference: plan file at ~/.claude/plans/today-we-are-doing-eventual-boole.md
section "Design (final synthesis)".
"""
from __future__ import annotations

import math
import os
from typing import Dict


# Playbook param spec — von Neumann's templates, ceilings applied per the plan.
# All fields in [0, 1] utility space.
_PLAYBOOKS: Dict[str, Dict[str, float]] = {
    "BOULWARE": {
        # Anchor extreme, hold flat — turn opponent's commitment into our advantage.
        "asp_start":         0.95,
        "asp_floor":         0.78,
        "accept_early_bar":  0.82,
        "commitment_margin": 0.04,
        "concession_cap":    0.020,
    },
    "CONCEDER": {
        # Pure exploitation — patient player extracts the surplus.
        "asp_start":         0.95,
        "asp_floor":         0.85,
        "accept_early_bar":  0.85,
        "commitment_margin": 0.02,
        "concession_cap":    0.010,
    },
    "MIRROR": {
        # Anchor first; mirrors lock onto our trajectory.
        "asp_start":         0.92,
        "asp_floor":         0.78,
        "accept_early_bar":  0.78,
        "commitment_margin": 0.03,
        "concession_cap":    0.020,
    },
    "RANDOM": {
        # Maximize EV against noise — accept conditional means immediately.
        "asp_start":         0.88,
        "asp_floor":         0.72,
        "accept_early_bar":  0.72,
        "commitment_margin": 0.02,
        "concession_cap":    0.025,
    },
    # UNKNOWN / fallback: equilibrium-honest defaults (current SNHP behavior).
    "HONEST": {
        "asp_start":         0.62,
        "asp_floor":         0.45,
        "accept_early_bar":  0.46,
        "commitment_margin": 0.01,
        "concession_cap":    0.025,
    },
}


# Confidence gate: below this threshold, exploit weight stays at 0.
# The plan/Nash argument: F1=0.68 means structured noise at type
# boundaries; below conf=0.65 we don't trust the classifier enough
# to deviate from the honest default.
_DEFAULT_CONFIDENCE_FLOOR = 0.65

# Cap on exploit weight: always retain ≥30% honest tail. Plan's Nash
# guardrail to prevent learning opponents from gradient-climbing our
# exploitation pattern.
_EXPLOIT_WEIGHT_CAP = 0.7


def confidence_floor() -> float:
    """Returns the confidence floor below which no exploit weight applies.
    Read from SNHP_CONFIDENCE_MIN env var (set by the ablation runner per
    cell) when present; otherwise falls back to the default 0.65."""
    raw = os.environ.get("SNHP_CONFIDENCE_MIN", "").strip()
    if raw:
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            pass
    return _DEFAULT_CONFIDENCE_FLOOR


def playbook_mode() -> str:
    """Returns the playbook-selection mode for the current run, set by
    the ablation runner via SNHP_PLAYBOOK_MODE env var. One of:

      OFF              — exploitation mode disabled; HONEST playbook only.
                          (baseline cell behavior; production-default until
                          ablation gates pass.)
      ALL              — full belief-weighted blend over all 4 playbooks.
                          (headline candidate.)
      BOULWARE_ONLY    — only the BOULWARE playbook is active; other types
      CONCEDER_ONLY      collapse to HONEST. Type-isolation cells.
      MIRROR_ONLY
      RANDOM_ONLY
      PROBABILISTIC    — softmax over confidence with no hard threshold
                          (mixed-strategy verification cell).
      ORACLE           — classifier sees ground-truth labels (upper bound
                          on lift).
    """
    return os.environ.get("SNHP_PLAYBOOK_MODE", "OFF").upper()


def compose_belief_weighted_params(
    belief: Dict[str, float],
    type_confidence: float,
) -> Dict[str, float]:
    """
    Returns a dict of {asp_start, asp_floor, accept_early_bar,
    commitment_margin, concession_cap} composed as:

      action = w_exploit · (Σ_c P(c) · π_c) + (1 − w_exploit) · π_HONEST

    where w_exploit is gated by `type_confidence` ≥ floor and capped at
    _EXPLOIT_WEIGHT_CAP. The blend is over the 4 typed playbooks
    (BOULWARE, CONCEDER, MIRROR, RANDOM) — UNKNOWN's mass gets folded
    into the honest weight via (1 − total_typed_mass) below.

    Mode selection:
      OFF                    → return HONEST playbook unchanged
      ALL / PROBABILISTIC    → full belief-weighted blend
      <TYPE>_ONLY            → only that type's playbook contributes;
                                others collapse to HONEST
      ORACLE                 → handled upstream by the classifier (this
                                function just consumes the resulting belief)
    """
    mode = playbook_mode()
    floor = confidence_floor()
    honest = _PLAYBOOKS["HONEST"]

    if mode == "OFF":
        return dict(honest)

    # Type-isolation modes: zero out belief for everyone except the
    # named type. The non-named types' mass gets re-routed to UNKNOWN
    # so they're handled as honest.
    only_map = {
        "BOULWARE_ONLY": "BOULWARE",
        "CONCEDER_ONLY": "CONCEDER",
        "MIRROR_ONLY":   "MIRROR",
        "RANDOM_ONLY":   "RANDOM",
    }
    if mode in only_map:
        keep = only_map[mode]
        b = {k: 0.0 for k in belief}
        b[keep] = belief.get(keep, 0.0)
        b["UNKNOWN"] = 1.0 - b[keep]
        belief = b

    # PROBABILISTIC ignores the hard confidence floor and uses softmax.
    # We approximate with a sigmoid-shaped exploit weight that ramps
    # smoothly from 0 at conf=0 to the cap at conf=1.
    if mode == "PROBABILISTIC":
        w_exploit = _EXPLOIT_WEIGHT_CAP * _sigmoid_unit(type_confidence)
    else:
        # Standard mode (ALL or *_ONLY): hard gate at floor, then ramp.
        if type_confidence < floor:
            return dict(honest)
        # Ramp from 0 at floor to cap at 1.0
        ramp = (type_confidence - floor) / max(1e-6, 1.0 - floor)
        w_exploit = _EXPLOIT_WEIGHT_CAP * min(1.0, max(0.0, ramp))

    # Belief-weighted blend over the 4 typed playbooks.
    typed_blend: Dict[str, float] = {k: 0.0 for k in honest}
    typed_mass = 0.0
    for ttype in ("BOULWARE", "CONCEDER", "MIRROR", "RANDOM"):
        p = float(belief.get(ttype, 0.0))
        if p <= 0:
            continue
        pb = _PLAYBOOKS[ttype]
        for k in typed_blend:
            typed_blend[k] += p * pb[k]
        typed_mass += p

    # Renormalize the typed component if the typed mass is < 1 (the rest
    # is UNKNOWN, which we want to behave honestly inside the exploit
    # branch — so we add (1 − typed_mass) × HONEST to the typed_blend.
    if typed_mass < 1.0:
        residual = 1.0 - typed_mass
        for k in typed_blend:
            typed_blend[k] += residual * honest[k]

    # Final action: w_exploit × typed_blend + (1 − w_exploit) × HONEST.
    out: Dict[str, float] = {}
    for k in honest:
        out[k] = w_exploit * typed_blend[k] + (1.0 - w_exploit) * honest[k]
    return out


def _sigmoid_unit(x: float) -> float:
    """Sigmoid-ish ramp on [0, 1]. f(0)=0, f(0.5)≈0.5, f(1)≈1."""
    z = (x - 0.5) * 6.0  # widen slope so 0→0.05, 1→0.95
    return 1.0 / (1.0 + math.exp(-z))

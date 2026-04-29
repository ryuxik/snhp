"""
Per-opponent-type playbook specs + belief-weighted parameter composition.

Five playbooks (one per detected opponent type + one HONEST default).
Each is a dict of (asp_start, asp_floor, accept_early_bar, commitment_margin,
concession_cap) tuned to the saddle-point response for that opponent class.

The composition function returns a belief-weighted blend per Nash's
"continuous-function-of-belief" critique — never argmax-dispatches.
Confidence floor 0.65 before any exploit weight is non-zero. Exploit
weight capped at 0.7 (always retain ≥30% honest tail).

Param values can be overridden by:
  1. In-process: `set_playbook_override(dict)` — used by the Optuna tuner.
  2. On-disk: snhp/playbook_optimal.json (loaded once at module import).

Reference: plan file at ~/.claude/plans/today-we-are-doing-eventual-boole.md
section "Design (final synthesis)".
"""
from __future__ import annotations

import json
import math
import os
import os.path as _op
from typing import Dict, Optional


# Playbook param spec — von Neumann's templates, ceilings applied per the plan.
# All fields in [0, 1] utility space.
_PLAYBOOKS: Dict[str, Dict[str, float]] = {
    "BOULWARE": {
        # Empirically: hand-derived (asp_start=0.95, asp_floor=0.78) deadlocks
        # against actual hardliners — Loss Averse / Anchorer / BATNA Bluffer
        # cap around utility 0.40 in our space, so floor=0.78 means we never
        # close. v0 ablation showed -6.0% utility on Loss Averse, deal rate
        # 70%→45%. Toned to a small lift over HONEST: open slightly higher
        # (probe their commitment) but let the floor descend to walk-away
        # so deals close. The actual exploitation gain on BOULWARE is
        # negligible in this tournament because firm opponents win on Elo
        # by holding more extreme than us — copying them just produces
        # mutual deadlock. Keep the playbook honest-leaning.
        "asp_start":         0.75,
        "asp_floor":         0.45,
        "accept_early_bar":  0.55,
        "commitment_margin": 0.02,
        "concession_cap":    0.025,
    },
    "CONCEDER": {
        # Pure exploitation — patient player extracts surplus from a
        # conceding opponent. Empirically validated: this playbook's per-
        # type CONCEDER bucket lifted +0.009 utility over baseline at N=20.
        "asp_start":         0.95,
        "asp_floor":         0.85,
        "accept_early_bar":  0.85,
        "commitment_margin": 0.02,
        "concession_cap":    0.010,
    },
    "MIRROR": {
        # Mirrors copy our trajectory — anchor first, but back off the
        # floor so we don't both stall. Hand-tuned floor 0.78 was too high;
        # the v0 ablation per-type MIRROR was +0.010 (within noise) but
        # worst-case-pairing dropped — likely because mirrors of firm
        # opponents amplify our floor. 0.55 floor lets convergence happen.
        "asp_start":         0.85,
        "asp_floor":         0.55,
        "accept_early_bar":  0.65,
        "commitment_margin": 0.02,
        "concession_cap":    0.020,
    },
    "RANDOM": {
        # Maximize EV against noise — accept conditional means immediately.
        # v0 result: +0.014 on RANDOM bucket. Keeping spec.
        "asp_start":         0.88,
        "asp_floor":         0.55,
        "accept_early_bar":  0.65,
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


# ─── Override mechanism ─────────────────────────────────────────────────────


_PLAYBOOK_OVERRIDE: Optional[Dict[str, Dict[str, float]]] = None


def set_playbook_override(override: Optional[Dict[str, Dict[str, float]]]) -> None:
    """In-process override of the playbook param table. Used by the Optuna
    tuner to inject a candidate playbook for one trial. Pass None to clear."""
    global _PLAYBOOK_OVERRIDE
    _PLAYBOOK_OVERRIDE = override


def _active_playbooks() -> Dict[str, Dict[str, float]]:
    """Returns the active playbook table — override > on-disk JSON > hardcoded."""
    if _PLAYBOOK_OVERRIDE is not None:
        return _PLAYBOOK_OVERRIDE
    return _PLAYBOOKS


def _load_optimal_from_disk() -> None:
    """Best-effort load of snhp/playbook_optimal.json (the Optuna tuner's
    output). Replaces _PLAYBOOKS in place if the file exists and parses.
    Called once at module import."""
    path = _op.join(_op.dirname(_op.abspath(__file__)), "playbook_optimal.json")
    if not _op.isfile(path):
        return
    try:
        with open(path, "r") as f:
            d = json.load(f)
    except Exception:
        return
    # Validate shape: each top-level key should be a playbook name with
    # a sub-dict of the 5 expected params.
    expected = {"asp_start", "asp_floor", "accept_early_bar",
                "commitment_margin", "concession_cap"}
    for k, v in d.items():
        if not isinstance(v, dict) or not expected.issubset(v.keys()):
            return  # malformed; skip the load entirely
    _PLAYBOOKS.update({k: v for k, v in d.items() if k in _PLAYBOOKS})


_load_optimal_from_disk()


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
      DOMAIN_ONLY      — Penguin-style: ignore opponent classification
                          entirely, just play the math. Returns HONEST
                          playbook regardless of belief state. Tests the
                          ANAC 2025 insight that opponent modeling can
                          be a liability.
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
    pb = _active_playbooks()
    honest = pb["HONEST"]

    if mode in ("OFF", "DOMAIN_ONLY"):
        # DOMAIN_ONLY: same behavior as OFF; separate label for the ANAC ablation cell.
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
        type_pb = pb[ttype]
        for k in typed_blend:
            typed_blend[k] += p * type_pb[k]
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

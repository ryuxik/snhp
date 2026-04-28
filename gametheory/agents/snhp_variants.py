"""
Shared SNHP variant zoo + class factory.

Houses the named hand-tuned variants (Hardline, Conceder, Patient,
Aggressive) used both as adaptive opponents during Optuna tuning and as
hypothesis-test variants in the long-horizon tournament. Also exposes
`make_variant_class` — the helper that synthesizes a SNHPAgent subclass
with class-level `_VARIANT_PARAMS` overriding the role-aware `_tp` lookup.

Pareto operating points (produced by `optuna_multi_objective.py` and
written to `gametheory/evals/optuna_pareto_{avg,h2h,self}.json`) are
loaded eagerly at *module import* and synthesized into picklable
top-level classes here. That ensures spawn-mode multiprocessing workers
see the same class identities as the parent process — they re-import
this module at startup and find the Pareto-variant classes already
defined.
"""
from __future__ import annotations

import json
import os
from typing import Type

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from negmas_agent import SNHPAgent  # noqa: E402


class SNHPVariantBase(SNHPAgent):
    """Base for hand-tuned SNHP variants.

    Reads from a class-level `_VARIANT_PARAMS` before the global
    `_TUNE_PARAMS` and the hardcoded defaults. Lookup is role-aware:
    `seller_<name>` if first-mover, `buyer_<name>` if second.
    """
    _VARIANT_PARAMS: dict = {}

    def _tp(self, name: str, default: float) -> float:
        if self._is_first_mover is True:
            key = f"seller_{name}"
            if key in self._VARIANT_PARAMS:
                return self._VARIANT_PARAMS[key]
        elif self._is_first_mover is False:
            key = f"buyer_{name}"
            if key in self._VARIANT_PARAMS:
                return self._VARIANT_PARAMS[key]
        if name in self._VARIANT_PARAMS:
            return self._VARIANT_PARAMS[name]
        return super()._tp(name, default)


def make_variant_class(name: str, params: dict, base: Type = SNHPVariantBase
                        ) -> Type:
    """Synthesize a subclass of `base` with class-level `_VARIANT_PARAMS=params`.
    `base` defaults to SNHPVariantBase but can be e.g. SNHPWithAspirationDetector
    so the detector + tuned params compose.

    The synthesized class is registered on this module's globals so pickle
    can find it by qualname during multiprocessing fan-out — without this,
    `Pool.map` over jobs that include the class fails with PicklingError.
    """
    cls = type(name, (base,), {"_VARIANT_PARAMS": dict(params)})
    cls.__module__ = __name__
    globals()[name] = cls
    return cls


# ─── Hand-tuned variants used as adaptive opponents in tuning ───────────────


class SNHP_Hardline(SNHPVariantBase):
    _VARIANT_PARAMS = {
        "aspiration_start": 0.85,
        "aspiration_floor": 0.55,
        "concession_cap_b2b": 0.020,
        "accept_early_bar": 0.62,
        "accept_late_bottom": 0.50,
        "retract_prob_b2b": 0.005,
    }


class SNHP_Conceder(SNHPVariantBase):
    _VARIANT_PARAMS = {
        "aspiration_start": 0.55,
        "aspiration_floor": 0.40,
        "concession_cap_b2b": 0.080,
        "accept_early_bar": 0.46,
        "accept_late_bottom": 0.40,
        "retract_prob_b2b": 0.025,
    }


class SNHP_Patient(SNHPVariantBase):
    _VARIANT_PARAMS = {
        "time_floor_rate": 0.95,
        "accept_late_start": 0.75,
        "accept_late_curve": 0.40,
        "concession_cap_b2b": 0.030,
    }


class SNHP_Aggressive(SNHPVariantBase):
    _VARIANT_PARAMS = {
        "aspiration_start": 0.78,
        "aspiration_floor": 0.50,
        "counter_anchor_cap": 0.50,
        "accept_early_bar": 0.60,
        "concession_cap_b2b": 0.025,
        "retract_prob_b2b": 0.000,
        "commitment_margin": 0.05,
    }


# ─── Pareto operating points loaded eagerly at import time ──────────────────
# Synthesizing classes here (rather than via runtime `make_variant_class`)
# means spawn-mode multiprocessing workers see the same class identities
# as the parent process. Without this, Pool.map fails with PicklingError /
# AttributeError when a job's function or arg references a runtime class.
#
# Composition: the Pareto-tuned variants subclass the AspirationDetector,
# so they get both the Optuna-tuned base params AND the deterministic-
# opponent fallback. Detector + tuned params is the headline combination.

_PARETO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evals",
)


def _load_pareto_operating_point(tag: str) -> dict | None:
    path = os.path.join(_PARETO_DIR, f"optuna_pareto_{tag}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _try_register_pareto_variant(name: str, tag: str) -> Type | None:
    op = _load_pareto_operating_point(tag)
    if op is None:
        return None
    # Lazy import to avoid a circular: aspiration_detector imports
    # negmas_agent which our SNHPVariantBase already pulls in, but
    # composing in is cleaner via the detector subclass.
    from gametheory.agents.aspiration_detector import (
        SNHPWithAspirationDetector,
    )
    cls = type(name, (SNHPWithAspirationDetector,),
                {"_VARIANT_PARAMS": dict(op["params"])})
    cls.__module__ = __name__
    globals()[name] = cls
    return cls


SNHP_PMaxAvg = _try_register_pareto_variant("SNHP_PMaxAvg", "avg")
SNHP_PMaxH2H = _try_register_pareto_variant("SNHP_PMaxH2H", "h2h")
SNHP_PMaxSelf = _try_register_pareto_variant("SNHP_PMaxSelf", "self")

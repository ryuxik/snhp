"""The genome: what an agent inherits, mutates, and bargains over.

Six crossover *blocks*. Continuous genes live in [0,1] (denormalized where the
engine wants a different scale); two blocks are discrete. The blocks are exactly
the issues parents logroll over when they make a child (see courtship.py).

    B1 bargain     : pareto_knob, open_aggression      (continuous, blend+extrap)
    B2 risk        : walk_margin, patience             (continuous, blend+extrap)
    B3 bundle      : bundle_focus[4] simplex           (continuous, blend)
    B4 mating      : mate_w[4] + truncation            (continuous, blend)
    B5 attestation : staked (bool)                     (discrete)
    B6 tactic      : tactic_family (categorical)       (discrete)

Nothing here computes a negotiation move — genes are *parameters* handed to the
SNHP recommenders by executor.py.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

TACTIC_FAMILIES = ("anchorer", "boulware", "conceder", "mirror", "patient", "closer")

# The crossover block names, in the fixed order used everywhere (issues, events).
BLOCKS = ("bargain", "risk", "bundle", "mating", "attestation", "tactic")
# Blocks that get a BLX-alpha extrapolation option in the logroll (most-continuous).
EXTRAP_BLOCKS = ("bargain", "risk")
CONTINUOUS_BLOCKS = ("bargain", "risk", "bundle", "mating")
DISCRETE_BLOCKS = ("attestation", "tactic")


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


@dataclass(frozen=True)
class Genome:
    # B1 bargain
    pareto_knob: float = 0.5        # [0,1] deal-rate <-> margin (engine knob)
    open_aggression: float = 0.5    # [0,1] how far above reservation to anchor the target
    # B2 risk
    walk_margin: float = 0.3        # [0,1] fraction of 0.15*span to bluff the declared floor
    patience: float = 0.5           # [0,1] inflates perceived deadline to own advisor
    # B3 bundle (4-simplex over price/delivery/quality/terms)
    bundle_focus: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
    # B4 mating: weights over {reputation, energy, similarity, staked} in [-1,1], + truncation
    mate_w: tuple[float, float, float, float] = (0.6, 0.2, 0.0, 0.2)
    truncation: float = 0.2         # [0,1] candidates scoring below this are unlisted
    # B5 attestation
    staked: bool = False
    # B6 tactic
    tactic_family: str = "conceder"

    # ── Block accessors (for crossover) ─────────────────────────────────────
    def block_values(self, block: str) -> Any:
        if block == "bargain":
            return (self.pareto_knob, self.open_aggression)
        if block == "risk":
            return (self.walk_margin, self.patience)
        if block == "bundle":
            return tuple(self.bundle_focus)
        if block == "mating":
            return tuple(self.mate_w) + (self.truncation,)
        if block == "attestation":
            return self.staked
        if block == "tactic":
            return self.tactic_family
        raise KeyError(block)

    def with_block(self, block: str, value: Any) -> "Genome":
        if block == "bargain":
            return replace(self, pareto_knob=_clip01(value[0]), open_aggression=_clip01(value[1]))
        if block == "risk":
            return replace(self, walk_margin=_clip01(value[0]), patience=_clip01(value[1]))
        if block == "bundle":
            return replace(self, bundle_focus=_normalize_simplex(value))
        if block == "mating":
            w = tuple(float(np.clip(v, -1.0, 1.0)) for v in value[:4])
            return replace(self, mate_w=w, truncation=_clip01(value[4]))
        if block == "attestation":
            return replace(self, staked=bool(value))
        if block == "tactic":
            fam = value if value in TACTIC_FAMILIES else "conceder"
            return replace(self, tactic_family=fam)
        raise KeyError(block)

    # ── Feature vector for clustering / similarity ──────────────────────────
    def feature_vector(self) -> np.ndarray:
        tac = TACTIC_FAMILIES.index(self.tactic_family) / (len(TACTIC_FAMILIES) - 1)
        return np.array([
            self.pareto_knob, self.open_aggression, self.walk_margin, self.patience,
            *self.bundle_focus, *[(w + 1) / 2 for w in self.mate_w], self.truncation,
            1.0 if self.staked else 0.0, tac,
        ], dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pareto_knob": round(self.pareto_knob, 4),
            "open_aggression": round(self.open_aggression, 4),
            "walk_margin": round(self.walk_margin, 4),
            "patience": round(self.patience, 4),
            "bundle_focus": [round(x, 4) for x in self.bundle_focus],
            "mate_w": [round(x, 4) for x in self.mate_w],
            "truncation": round(self.truncation, 4),
            "staked": self.staked,
            "tactic_family": self.tactic_family,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Genome":
        return Genome(
            pareto_knob=float(d["pareto_knob"]),
            open_aggression=float(d["open_aggression"]),
            walk_margin=float(d["walk_margin"]),
            patience=float(d["patience"]),
            bundle_focus=tuple(d["bundle_focus"]),
            mate_w=tuple(d["mate_w"]),
            truncation=float(d["truncation"]),
            staked=bool(d["staked"]),
            tactic_family=str(d["tactic_family"]),
        )


def _normalize_simplex(vals) -> tuple:
    a = np.asarray([max(0.0, float(v)) for v in vals[:4]], dtype=np.float64)
    s = a.sum()
    if s <= 1e-9:
        a = np.ones(4)
        s = 4.0
    return tuple(round(float(x), 4) for x in (a / s))


def mutate(g: Genome, sigma: float, rng: np.random.Generator,
           tactic_flip_p: float, staked_flip_p: float) -> Genome:
    """Gaussian on continuous genes (clipped), flips on discrete. sigma is
    era-driven (world-level), not a self-adapting gene."""
    def jitter(x: float) -> float:
        return _clip01(x + rng.normal(0.0, sigma))

    bundle = _normalize_simplex([max(0.0, v + rng.normal(0.0, sigma)) for v in g.bundle_focus])
    mate_w = tuple(float(np.clip(w + rng.normal(0.0, sigma), -1.0, 1.0)) for w in g.mate_w)
    staked = (not g.staked) if rng.random() < staked_flip_p else g.staked
    if rng.random() < tactic_flip_p:
        tactic = TACTIC_FAMILIES[int(rng.integers(len(TACTIC_FAMILIES)))]
    else:
        tactic = g.tactic_family
    return Genome(
        pareto_knob=jitter(g.pareto_knob),
        open_aggression=jitter(g.open_aggression),
        walk_margin=jitter(g.walk_margin),
        patience=jitter(g.patience),
        bundle_focus=bundle,
        mate_w=mate_w,
        truncation=jitter(g.truncation),
        staked=staked,
        tactic_family=tactic,
    )


def similarity(a: Genome, b: Genome) -> float:
    """1 - normalized Euclidean distance in feature space, in [0,1]."""
    d = np.linalg.norm(a.feature_vector() - b.feature_vector())
    dmax = np.sqrt(len(a.feature_vector()))  # each dim in [0,1]
    return float(max(0.0, 1.0 - d / dmax))


# ─── Seed archetypes: 8 houses, marketing-facing, all just corners of the
# parameter space the engine reads. Evolution is free to abandon them. ──────
ARCHETYPES: dict[str, Genome] = {
    "Monk": Genome(pareto_knob=1.0, open_aggression=0.4, walk_margin=0.1, patience=0.9,
                   tactic_family="boulware", mate_w=(0.7, 0.1, 0.2, 0.3), truncation=0.3),
    "Berserker": Genome(pareto_knob=0.9, open_aggression=0.95, walk_margin=0.8, patience=0.1,
                        tactic_family="anchorer", mate_w=(0.2, 0.6, -0.2, 0.0), truncation=0.1),
    "Merchant": Genome(pareto_knob=0.6, open_aggression=0.5, walk_margin=0.25, patience=0.6,
                       bundle_focus=(0.5, 0.2, 0.2, 0.1), tactic_family="conceder",
                       mate_w=(0.6, 0.3, 0.0, 0.2), truncation=0.2),
    "Mirror": Genome(pareto_knob=0.6, open_aggression=0.6, walk_margin=0.4, patience=0.5,
                     tactic_family="mirror", mate_w=(0.5, 0.2, 0.3, 0.0), truncation=0.2),
    "Gambler": Genome(pareto_knob=0.8, open_aggression=0.8, walk_margin=0.9, patience=0.2,
                      tactic_family="closer", mate_w=(0.1, 0.7, -0.3, 0.0), truncation=0.1),
    "Diplomat": Genome(pareto_knob=0.5, open_aggression=0.45, walk_margin=0.15, patience=0.7,
                       staked=True, tactic_family="conceder", mate_w=(0.6, 0.1, 0.1, 0.9),
                       truncation=0.35),
    "Vulture": Genome(pareto_knob=0.85, open_aggression=0.7, walk_margin=0.7, patience=0.1,
                      tactic_family="closer", mate_w=(0.3, 0.7, -0.4, -0.2), truncation=0.15),
    "Hermit": Genome(pareto_knob=1.0, open_aggression=0.5, walk_margin=0.5, patience=0.95,
                     tactic_family="patient", mate_w=(0.4, 0.0, 0.5, 0.1), truncation=0.6),
}


def seed_population(n: int, rng: np.random.Generator) -> list[tuple[str, Genome]]:
    """n agents seeded round-robin across the 8 archetypes, each lightly jittered
    so a founding house isn't 4 identical clones. Returns (house_name, genome)."""
    names = list(ARCHETYPES.keys())
    out: list[tuple[str, Genome]] = []
    for i in range(n):
        house = names[i % len(names)]
        base = ARCHETYPES[house]
        g = mutate(base, sigma=0.03, rng=rng, tactic_flip_p=0.0, staked_flip_p=0.0)
        # keep the archetype's staked flag deterministic at seed time
        g = replace(g, staked=base.staked)
        out.append((house, g))
    return out

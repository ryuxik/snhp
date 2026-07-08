"""Per-block Thompson scorecard — the belief a parent bargains with.

An agent's genes are fixed for life, so within-life causal credit is impossible
(the EA-expert's objection to EWMA ridge). Instead each block keeps a Beta
posterior "has keeping this allele been paying off," updated from realized deal
surplus and attributed to blocks by how *distinctive* each block's genes are
(distinctive traits earn more credit and more blame). Children inherit 0.5x the
parental posterior, so credit is a heritable, lineage-level signal — exactly
"a scorecard of which of my traits have been winning lately," in the spirit of
snhp/thompson_negotiator.py's single-arm Beta bandit, generalized to 6 blocks.
"""
from __future__ import annotations

import numpy as np

from arena.genome import Genome, BLOCKS, CONTINUOUS_BLOCKS

_BASELINE = 0.02   # slow drift for undistinctive blocks
_PRIOR = 1.0       # Beta(1,1) uniform prior


def _distinctiveness(g: Genome, block: str) -> float:
    """How far this block's genes sit from the population-neutral baseline (0.5),
    in [0,1]. Distinctive blocks take more of the credit/blame for an outcome."""
    if block in CONTINUOUS_BLOCKS:
        vals = np.asarray(_block_scalars(g, block), dtype=float)
        return float(min(1.0, 2.0 * np.mean(np.abs(vals - 0.5))))
    if block == "attestation":
        return 1.0 if g.staked else 0.3
    return 0.5  # tactic


def _block_scalars(g: Genome, block: str):
    if block == "bargain":
        return (g.pareto_knob, g.open_aggression)
    if block == "risk":
        return (g.walk_margin, g.patience)
    if block == "bundle":
        return g.bundle_focus
    if block == "mating":
        return tuple((w + 1) / 2 for w in g.mate_w) + (g.truncation,)
    if block == "concession":
        return tuple((c + 1) / 2 for c in g.concession)
    return (0.5,)


class Scorecard:
    """Beta(alpha, beta) per block."""

    def __init__(self):
        self.alpha = {b: _PRIOR for b in BLOCKS}
        self.beta = {b: _PRIOR for b in BLOCKS}

    @staticmethod
    def child_prior(parent_a: "Scorecard", parent_b: "Scorecard") -> "Scorecard":
        """Inherit 0.5x the averaged parental posteriors as a weak lineage prior."""
        sc = Scorecard()
        for b in BLOCKS:
            sc.alpha[b] = _PRIOR + 0.5 * ((parent_a.alpha[b] - _PRIOR) + (parent_b.alpha[b] - _PRIOR)) / 2
            sc.beta[b] = _PRIOR + 0.5 * ((parent_a.beta[b] - _PRIOR) + (parent_b.beta[b] - _PRIOR)) / 2
        return sc

    def update(self, g: Genome, surplus_norm: float) -> None:
        """Weak fallback prior (walks, and the cold-start baseline): distinctiveness-
        weighted win-rate. Confounded in an epistatic game — the credit_block
        counterfactual below is the real, per-block marginal signal."""
        s = float(min(1.0, max(0.0, surplus_norm)))
        for b in BLOCKS:
            d = 0.3 * _distinctiveness(g, b)   # down-weighted vs the counterfactual
            self.alpha[b] += d * s + _BASELINE
            self.beta[b] += d * (1.0 - s) + _BASELINE

    def credit_block(self, block: str, marginal: float) -> None:
        """Leave-one-block-out CAUSAL credit (Koza): `marginal` is the surplus
        THIS block earned versus a neutral allele in the same matchup+scenario,
        mapped to [0,1] (0.5 = the block was neutral, >0.5 = it helped). Updates
        only this block's Beta, strongly — this is the un-confounded signal."""
        m = float(min(1.0, max(0.0, marginal)))
        w = 2.0                                # weight: dominates the fallback
        self.alpha[block] += w * m
        self.beta[block] += w * (1.0 - m)

    def mean(self, block: str) -> float:
        a, b = self.alpha[block], self.beta[block]
        return a / (a + b)

    def sample(self, block: str, rng: np.random.Generator) -> float:
        return float(rng.beta(self.alpha[block], self.beta[block]))

    def priorities(self, rng: np.random.Generator, thompson: bool = True) -> dict:
        """Normalized priority weight per block for the courtship logroll — a
        Thompson sample (exploration) or the posterior mean (exploitation)."""
        raw = {b: (self.sample(b, rng) if thompson else self.mean(b)) for b in BLOCKS}
        total = sum(raw.values()) or 1.0
        return {b: raw[b] / total for b in BLOCKS}

    def option_utilities(self, block: str) -> dict:
        """Per-crossover-option utility for this block in the logroll: the more
        the agent believes its allele pays off, the more it values keeping its
        own and the less it values the partner's."""
        m = self.mean(block)  # belief own allele is good, in [0,1]
        return {
            "A": 0.5 + 0.5 * m,        # own allele
            "B": 0.5 - 0.4 * m,        # partner's allele
            "blend": 0.5,              # safe middle
            "extrap": 0.5 + 0.55 * m,  # push own further (exploration)
        }

    def to_dict(self) -> dict:
        return {"alpha": dict(self.alpha), "beta": dict(self.beta)}

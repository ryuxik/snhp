"""Species = clusters for the visuals and census; behavioral niches = clusters
for the crowding tax. Two clusterings on purpose: the genotype->phenotype map is
many-to-one, and ecological competition is behavioral, not genetic (EA-expert).

Leader clustering in NumPy (sklearn isn't a prod dep), with persistent centroids
+ hysteresis so a dynasty keeps its species ID (and thus its color) across
generations instead of flickering.
"""
from __future__ import annotations

import numpy as np

from arena.config import ArenaConfig
from arena.genome import Genome, TACTIC_FAMILIES


class SpeciesTracker:
    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg
        self._centroids: dict[int, np.ndarray] = {}
        self._next_id = 0

    def update(self, agents: list) -> tuple[dict, list]:
        """agents: list of (agent_id, feature_vector). Returns
        ({agent_id: species_id}, [species summaries])."""
        assign: dict[int, int] = {}
        members: dict[int, list] = {}
        for aid, fv in agents:
            sid = self._nearest(fv)
            if sid is None:
                sid = self._next_id
                self._next_id += 1
                self._centroids[sid] = np.asarray(fv, dtype=float)
            assign[aid] = sid
            members.setdefault(sid, []).append((aid, fv))

        # Move centroids toward member means with hysteresis; retire the empty.
        alive = set(members)
        for sid in list(self._centroids):
            if sid not in alive:
                del self._centroids[sid]
                continue
            mean = np.mean([fv for _, fv in members[sid]], axis=0)
            # hysteresis: keep MOST of the old centroid, drift slowly toward the
            # member mean, so species IDs (and colors) stay stable instead of
            # flickering. h is the small drift rate (0.10 = 90% memory).
            h = self.cfg.species_hysteresis
            self._centroids[sid] = (1 - h) * self._centroids[sid] + h * mean

        summaries = []
        for sid, mem in members.items():
            exemplar = max(mem, key=lambda x: -np.linalg.norm(x[1] - self._centroids[sid]))[0]
            summaries.append({
                "id": sid,
                "count": len(mem),
                "centroid": [round(float(x), 3) for x in self._centroids[sid][:8]],
                "exemplar": exemplar,
            })
        summaries.sort(key=lambda s: s["count"], reverse=True)
        return assign, summaries

    def _nearest(self, fv) -> int | None:
        best, best_d = None, self.cfg.species_merge_dist
        fv = np.asarray(fv, dtype=float)
        for sid, c in self._centroids.items():
            d = float(np.linalg.norm(fv - c))
            if d < best_d:
                best, best_d = sid, d
        return best


def behavioral_key(g: Genome) -> str:
    """A coarse behavioral niche label for the crowding tax — the strategy an
    agent actually plays, not its full genotype."""
    knob = "hi" if g.pareto_knob >= 0.66 else ("mid" if g.pareto_knob >= 0.33 else "lo")
    aggr = "A" if g.open_aggression >= 0.5 else "a"
    return f"{g.tactic_family}:{knob}:{aggr}"


def behavioral_shares(genomes: list[Genome]) -> dict:
    """Fraction of the population in each behavioral niche (for tax_i)."""
    n = len(genomes) or 1
    counts: dict[str, int] = {}
    for g in genomes:
        k = behavioral_key(g)
        counts[k] = counts.get(k, 0) + 1
    return {k: v / n for k, v in counts.items()}

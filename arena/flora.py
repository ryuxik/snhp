"""Flora: the flower is the PHENOTYPE of the negotiation genome — a deterministic
render of the same six blocks the agents negotiate and inherit. Beauty is not a
separate objective; beauty IS strategy, made visible.

Selection on beauty is real biology + real mechanism design:
  - COSTLY SIGNALING (Spence / Zahavi handicap): an extravagant bloom is only
    affordable to an agent flush with deal surplus, so a full flower is a
    credible advertisement of negotiation skill (`bloom_fullness` gates on energy).
  - SEXUAL SELECTION (Miller & Todd mate-choice EAs): the mating market weighs a
    partner's bloom, so ornament and preference co-evolve.
  - POLLINATOR ECOLOGY: each market era has a pollinator whose taste favors
    different flower features; when the era flips, what is beautiful flips, and
    the whole garden drifts. The season's aesthetic is an environmental pressure,
    not a hand-set fitness function.

Nothing here decides a negotiation. It reads the genome and the era.
"""
from __future__ import annotations

from arena.genome import Genome, TACTIC_FAMILIES

# tactic family -> gothic flower species (silhouette the renderer draws)
SPECIES = {
    "anchorer": "thistle",     # spiky, opens huge, hits hard
    "boulware": "nightshade",  # dark, holds firm — a patient poison
    "conceder": "tulip",       # open, giving — the deal-maker's bloom
    "mirror": "orchid",        # symmetric, reflective
    "patient": "lily",         # tall, slow, outlasts
    "closer": "rose",          # thorned, strikes at the deadline
}

# Each era's pollinator: a named creature with a taste over flower features
# [warmth, showiness, height, luminance, layering], each in [0,1].
POLLINATORS = {
    "symmetric": {"name": "the Bat", "glyph": "🦇", "pref": [0.5, 0.5, 0.45, 0.45, 0.45]},
    "buyers":    {"name": "the Dawn Moth", "glyph": "🌙", "pref": [0.2, 0.4, 0.7, 0.85, 0.5]},
    "sellers":   {"name": "the Ember Bee", "glyph": "🐝", "pref": [0.92, 0.9, 0.4, 0.5, 0.3]},
    "contract":  {"name": "the Night Sphinx", "glyph": "✦", "pref": [0.3, 0.5, 0.6, 0.9, 0.92]},
}


def flower_features(g: Genome) -> list[float]:
    """The bloom's phenotype vector, deterministic from the genome:
    [warmth, showiness, height, luminance, layering], each in [0,1]."""
    warmth = g.pareto_knob                              # cool deal-rate -> warm margin
    showiness = g.open_aggression                       # bold, many petals
    height = g.patience                                 # patient = tall stem
    luminance = 0.75 if g.staked else 0.35              # staked = gilt, luminous
    layering = max(g.bundle_focus)                      # specialist = layered petals
    return [warmth, showiness, height, luminance, layering]


def pollinator_for(era: str) -> dict:
    return POLLINATORS.get(era, POLLINATORS["symmetric"])


def pollinator_align(g: Genome, pollinator: dict) -> float:
    """How well this bloom matches the season's pollinator taste, in [0,1]."""
    f = flower_features(g)
    pref = pollinator["pref"]
    # 1 - mean absolute distance (features + pref both in [0,1])
    dist = sum(abs(a - b) for a, b in zip(f, pref)) / len(pref)
    return 1.0 - dist


def bloom_fullness(energy: float, mate_threshold: float) -> float:
    """The costly signal: only a well-fed agent can afford a full display."""
    return max(0.15, min(1.0, energy / max(mate_threshold, 1e-6)))


def aesthetic_pull(g: Genome, energy: float, pollinator: dict,
                   mate_threshold: float) -> float:
    """The mate-attractiveness contribution of a bloom: pollinator-aligned AND
    affordable. This is the term added to the Gale-Shapley preference score."""
    return pollinator_align(g, pollinator) * bloom_fullness(energy, mate_threshold)


def beauty_score(g: Genome, energy: float, pollinator: dict, mate_threshold: float,
                 rarity: float = 0.0) -> float:
    """Overall bloom beauty for the 'Bloom of the Generation' — pollinator
    alignment, affordability, and a touch of rarity (novelty stands out)."""
    return aesthetic_pull(g, energy, pollinator, mate_threshold) * (1.0 + 0.5 * rarity)


def flower_dict(g: Genome) -> dict:
    """Compact phenotype the renderer draws (species + feature vector)."""
    f = flower_features(g)
    return {"species": SPECIES.get(g.tactic_family, "tulip"),
            "warmth": round(f[0], 3), "showiness": round(f[1], 3),
            "height": round(f[2], 3), "luminance": round(f[3], 3),
            "layering": round(f[4], 3), "staked": g.staked}

"""Every tunable in the arena, in one place, env-overridable via ARENA_*.

Mirrors the discipline of `gametheory/negotiation/_config.py`: no magic number
hides in the sim code path. Balance is tuned by overriding these (or editing the
defaults) and re-running `python -m arena.fastforward`.

The SNHP_* engine overrides that must be set BEFORE the engine imports (particle
counts) are applied here at import time — importing arena.config first, then the
engine, guarantees the smaller particle budget is in effect.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return float(default)
    try:
        v = float(raw)
    except ValueError:
        return float(default)
    # float() accepts 'inf'/'nan'; reject them so a bad env override falls back
    # to the default rather than crashing int() at import (OverflowError/ValueError).
    if v != v or v in (float("inf"), float("-inf")):
        return float(default)
    return v


def _i(name: str, default: int) -> int:
    return int(_f(name, default))


# ─── Engine budget: applied before the engine is imported anywhere ──────────
# The arena runs many bundle negotiations per generation; 200 particles keeps
# courtship snappy with no meaningful behavior change (particle count is a
# performance knob per the engine's own _config notes).
os.environ.setdefault("SNHP_BUNDLE_N_PARTICLES", os.environ.get("ARENA_BUNDLE_N_PARTICLES", "200"))
os.environ.setdefault("SNHP_BAYESIAN_N_PARTICLES", os.environ.get("ARENA_BAYESIAN_N_PARTICLES", "300"))


@dataclass(frozen=True)
class ArenaConfig:
    # ── World seed & determinism ──
    seed: int = _i("ARENA_SEED", 42)

    # ── Population & carrying capacity ──
    pop_start: int = _i("ARENA_POP_START", 32)
    pop_cap: int = _i("ARENA_POP_CAP", 60)
    pop_floor: int = _i("ARENA_POP_FLOOR", 16)

    # ── Energy economy (integer milli-energy internally; these are in whole units) ──
    energy_start: float = _f("ARENA_ENERGY_START", 100.0)
    tax_per_gen: float = _f("ARENA_TAX_PER_GEN", 18.0)          # metabolic burn/gen
    tax_elastic_k: float = _f("ARENA_TAX_ELASTIC_K", 0.6)       # tax scales down when pop low
    crowd_tax_kappa: float = _f("ARENA_CROWD_TAX_KAPPA", 0.8)   # behavioral-niche crowding
    energy_cap_mult: float = _f("ARENA_ENERGY_CAP_MULT", 3.0)   # cap = mult * mating threshold
    income_concave_pow: float = _f("ARENA_INCOME_CONCAVE_POW", 0.85)  # diminishing returns

    deals_per_gen: int = _i("ARENA_DEALS_PER_GEN", 4)           # 2 buyer + 2 seller
    house_deal_frac: float = _f("ARENA_HOUSE_DEAL_FRAC", 0.25)  # 1 of 4 vs house-archetype bot
    energy_per_surplus: float = _f("ARENA_ENERGY_PER_SURPLUS", 34.0)  # surplus[0,1] -> energy

    # ── Scenario generation ──
    scenario_span: float = _f("ARENA_SCENARIO_SPAN", 1.0)       # fixed span (utility units)
    no_zopa_frac: float = _f("ARENA_NO_ZOPA_FRAC", 0.15)        # deals with no agreement zone
    zopa_min: float = _f("ARENA_ZOPA_MIN", 0.05)
    zopa_max: float = _f("ARENA_ZOPA_MAX", 0.45)
    round_cost: float = _f("ARENA_ROUND_COST", 0.005)          # ε per round, both sides
    # Adversarial deals: U(8,14). Staked/peer deals: U(7,13) EXACTLY — the only
    # horizon where peer_mode's +0.186 lift is validated (mechanism-expert rule).
    horizon_lo: int = _i("ARENA_HORIZON_LO", 8)
    horizon_hi: int = _i("ARENA_HORIZON_HI", 14)
    peer_horizon_lo: int = _i("ARENA_PEER_HORIZON_LO", 7)
    peer_horizon_hi: int = _i("ARENA_PEER_HORIZON_HI", 13)

    # ── Mating & reproduction ──
    mate_threshold_mult: float = _f("ARENA_MATE_THRESHOLD_MULT", 1.5)  # * energy_start
    mate_refractory_gens: int = _i("ARENA_MATE_REFRACTORY", 2)
    birth_tax_frac: float = _f("ARENA_BIRTH_TAX_FRAC", 0.35)    # progressive: frac of parent energy
    child_endowment_frac: float = _f("ARENA_CHILD_ENDOWMENT_FRAC", 0.25)  # each parent stakes this
    courtship_cost: float = _f("ARENA_COURTSHIP_COST", 18.0)   # impasse cost each (≈1 gen tax)
    courtship_rounds: int = _i("ARENA_COURTSHIP_ROUNDS", 6)    # R (3 offers each)
    # Tuned so ~5–10% of courtships end in impasse (the EA-expert target: make
    # "willingness to compromise" a genuinely selected trait). The knob's bite
    # depends on credit.py's utility encoding, so we target the outcome, not the
    # nominal 0.30 the spec named against a different encoding.
    crossover_batna: float = _f("ARENA_CROSSOVER_BATNA", 0.52)

    # ── Senescence (Gompertz) ──
    life_expectancy_gens: int = _i("ARENA_LIFE_EXPECTANCY", 55)  # 40–80 range
    senescence_shape: float = _f("ARENA_SENESCENCE_SHAPE", 0.12)

    # ── Mutation (era-coupled schedule) ──
    sigma_stable: float = _f("ARENA_SIGMA_STABLE", 0.05)
    sigma_shock: float = _f("ARENA_SIGMA_SHOCK", 0.22)          # first gens after an era flip
    sigma_shock_gens: int = _i("ARENA_SIGMA_SHOCK_GENS", 3)
    sigma_min: float = _f("ARENA_SIGMA_MIN", 0.02)
    sigma_max: float = _f("ARENA_SIGMA_MAX", 0.30)
    tactic_flip_p: float = _f("ARENA_TACTIC_FLIP_P", 0.05)
    staked_flip_p: float = _f("ARENA_STAKED_FLIP_P", 0.05)

    # ── Eras (semi-Markov) ──
    era_dwell_min: int = _i("ARENA_ERA_DWELL_MIN", 7)          # gens (~15–25 min at 3min/gen)
    era_interp_gens: int = _i("ARENA_ERA_INTERP_GENS", 3)
    era_diversity_nudge: float = _f("ARENA_ERA_DIVERSITY_NUDGE", 0.25)

    # ── Staking (the two-act macro-story) ──
    stake_upkeep: float = _f("ARENA_STAKE_UPKEEP", 4.0)        # per gen; ~20% of measured peer premium
    stake_seed_frac: float = _f("ARENA_STAKE_SEED_FRAC", 0.15)
    assortative: int = _i("ARENA_ASSORTATIVE", 0)             # Act II toggle (0/1)
    assortative_q: float = _f("ARENA_ASSORTATIVE_Q", 0.75)

    # ── Credit assignment ──
    # Leave-one-block-out counterfactual credit for the crossover operator: on
    # each closed deal, replay it with one gene block reset to neutral and credit
    # that block by the surplus delta (causal marginal, not confounded win-rate).
    # ~1 extra negotiation per close; off => the weak Beta win-rate fallback only.
    credit_counterfactual: int = _i("ARENA_CREDIT_COUNTERFACTUAL", 1)

    # ── Sexual selection / flora ──
    # Weight of the bloom's aesthetic pull in the mating-market preference score.
    # Beauty = pollinator-aligned AND affordable (costly signal). Drives the
    # visible garden drift when the era's pollinator changes.
    pollinator_weight: float = _f("ARENA_POLLINATOR_WEIGHT", 0.8)

    # ── Species clustering ──
    species_merge_dist: float = _f("ARENA_SPECIES_MERGE_DIST", 1.0)  # ~4–6 visual niches
    species_hysteresis: float = _f("ARENA_SPECIES_HYSTERESIS", 0.10)

    # ── Grand Auction set piece ──
    auction_every_gens: int = _i("ARENA_AUCTION_EVERY", 12)
    auction_pot: float = _f("ARENA_AUCTION_POT", 60.0)

    # ── Timing (live pacing; fast-forward ignores) ──
    tick_seconds: float = _f("ARENA_TICK_SECONDS", 0.25)
    ticks_per_offer: int = _i("ARENA_TICKS_PER_OFFER", 4)     # ~1 offer/s
    max_live_negotiations: int = _i("ARENA_MAX_LIVE_NEGS", 12)

    # ── Persistence ──
    data_dir: str = os.environ.get("ARENA_DATA_DIR", "").strip() or "/tmp/arena-data"

    @property
    def mate_threshold(self) -> float:
        return self.mate_threshold_mult * self.energy_start

    @property
    def energy_cap(self) -> float:
        return self.energy_cap_mult * self.mate_threshold

    def to_public_dict(self) -> dict[str, Any]:
        """The config a viewer/skeptic can read (drives the honest-claims page)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


CONFIG = ArenaConfig()

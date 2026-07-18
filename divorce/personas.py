"""Persona compiler — archetypes, sliders, hills, and the opposition sampler.

Compiles a playful persona spec (SPEC.md §1) into a hidden dollar-valuation
table + spite weight + litigation BATNA, and samples PAIRS whose opposition is
MEASURED, not asserted (SPEC.md §8: contested-asset qualification). Everything
is seeded and deterministic; no LLM anywhere in this module.

Utility convention (documented once, used everywhere):

    u_i(outcome) = sum_a share_i(a) * v_i[a]  +  cash_i
                 - lam_i * ( sum_a share_j(a) * v_i[a] + cash_j )

Spite values the EX's holdings at MY OWN valuation table (interdependent
preferences, self-contained — evaluating my utility never reads the other
side's private numbers). Cash is face value for everyone, which makes the
wallet the transferable numeraire; spite applies to the ex's cash too (every
dollar they walk away with stings at rate lam).

Litigation BATNA: court splits everything 50/50 in expectation (indivisibles
are a coin flip, the dog alternates), both sides pay a fight cost that shrinks
with patience — patient personas expect less pain from holding out, so they
demand more from any settlement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ─── The asset table (SPEC.md §2) ────────────────────────────────────────────
# options = the share of the asset side A receives under each option index.
# 3 * 5 * 11 * 2 * 2 * 2 = 1,320 outcomes < the engine's 4,000 cap.

WALLET_VALUE = 18_000.0

ASSETS: list[dict] = [
    {"name": "dog", "kind": "custody", "shares_a": [1.0, 0.0, 0.5]},
    {"name": "lake_weeks", "kind": "divisible", "shares_a": [0.0, 0.25, 0.5, 0.75, 1.0]},
    {"name": "wallet", "kind": "money", "shares_a": [i / 10 for i in range(11)]},
    {"name": "vinyl", "kind": "indivisible", "shares_a": [1.0, 0.0]},
    {"name": "espresso", "kind": "indivisible", "shares_a": [1.0, 0.0]},
    {"name": "wildcard", "kind": "indivisible", "shares_a": [1.0, 0.0]},
]
ASSET_NAMES = [a["name"] for a in ASSETS]
INDIVISIBLES = [a["name"] for a in ASSETS if a["kind"] in ("custody", "indivisible")]
SYMBOLIC = ["vinyl", "espresso", "wildcard"]  # pettiness targets
HILLABLE = ["dog", "lake_weeks", "vinyl", "espresso", "wildcard"]  # never the wallet

# Base dollar-value sampling ranges (full ownership) — REALISTIC RETAIL
# anchors (founder finding 2026-07-18: cartoon retail numbers broke the
# realism; a real dog is $1-3k, not $6-14k). The drama lives in the
# multipliers below — sentiment inflates the PERSONAL value well past
# retail, which is the human truth the flip reveals — while the "retail"
# the chrome quotes stays a number you could Google. The espresso machine
# is objectively worthless (retail $340): it generates the pettiness tax,
# not the contested-pair count. Changing any number here invalidates the
# committed harness/eval artifacts — re-run K1-K4 + E1-E3 + trap check and
# re-pin the preset traces (goldens are scaffolding).
BASE_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "dog": (900.0, 2_800.0),
    "lake_weeks": (4_000.0, 9_000.0),
    "vinyl": (800.0, 2_600.0),
    "espresso": (340.0, 340.0),
    "wildcard": (600.0, 2_400.0),
}

FIGHT_COST_BASE = 8_000.0       # $6.4k-12.8k by patience — real contested-divorce legal cost
HILL_MULT_RANGE = (3.0, 6.0)
PETTINESS_SYMBOLIC_GAIN = 2.0   # v_symbolic *= 1 + gain * pettiness
FRONT_MULT_RANGE = (2.0, 3.5)   # shared-front boost, both sides (see sample_pair)

# ─── Archetypes (SPEC.md §1): slider presets + a valuation shape ─────────────
# shape = per-asset multipliers on the sampled base value; sliders in [0, 1]
# except spite (lam), which is the utility weight directly.

ARCHETYPES: dict[str, dict] = {
    "spreadsheet": {  # "Everything at market price. Including the dog."
        "pettiness": 0.0, "spite": 0.0, "patience": 0.5,
        "shape": {},
    },
    "sentimental_hoarder": {  # value concentrated in low-dollar memory items
        "pettiness": 0.8, "spite": 0.1, "patience": 0.5,
        "shape": {"vinyl": 2.5, "wildcard": 2.5, "espresso": 2.0, "lake_weeks": 0.7},
    },
    "scorched_earth": {  # "Would rather burn it than split it."
        "pettiness": 0.5, "spite": 0.45, "patience": 0.7,
        "shape": {},
    },
    "already_healed": {  # wants nothing; indifference as BATNA leverage
        "pettiness": 0.0, "spite": 0.0, "patience": 0.9,
        "shape": {"dog": 0.5, "lake_weeks": 0.5, "vinyl": 0.4, "wildcard": 0.4},
    },
    "ledger": {  # every item priced in grievances; infinite patience
        "pettiness": 0.9, "spite": 0.2, "patience": 1.0,
        "shape": {"vinyl": 1.6, "espresso": 1.6, "wildcard": 1.6, "dog": 1.2},
    },
}
ARCHETYPE_NAMES = sorted(ARCHETYPES)
SLIDER_JITTER = 0.15  # sampled sliders live near the preset, clipped to [0,1]


@dataclass
class Persona:
    side: str                      # "A" | "B"
    archetype: str
    pettiness: float
    lam: float                     # spite weight
    patience: float
    hill: str
    hill_mult: float
    values: dict[str, float]       # dollar value of FULL ownership, incl. wallet
    # The raw sampled market draw per asset, BEFORE taste/pettiness/front/hill
    # multipliers — the objective "retail" number the demo's hill-autopsy card
    # quotes ("the espresso machine, retail $340").
    market_values: dict[str, float] = field(default_factory=dict)
    fight_cost: float = field(init=False)
    court_utility: float = field(init=False)
    walk_away: float = field(init=False)   # the litigation BATNA, in utility dollars

    def __post_init__(self):
        self.fight_cost = FIGHT_COST_BASE * (1.6 - 0.8 * self.patience)
        # Court: every asset at 0.5 expected share for each side.
        total = sum(self.values.values())
        self.court_utility = 0.5 * (1.0 - self.lam) * total
        self.walk_away = self.court_utility - self.fight_cost

    def utility(self, my_shares: dict[str, float]) -> float:
        """u_i for a full outcome given MY share of every asset (module docstring
        convention; the wallet is just another asset here, at face value)."""
        mine = sum(s * self.values[a] for a, s in my_shares.items())
        theirs = sum((1.0 - s) * self.values[a] for a, s in my_shares.items())
        return mine - self.lam * theirs

    def possession_value(self, my_shares: dict[str, float]) -> float:
        """v_i(my pile) with no spite term — the envy-check quantity (SPEC.md §6:
        EF iff each side values its own pile at least as much as the other's)."""
        return sum(s * self.values[a] for a, s in my_shares.items())


def _sample_slider(rng: np.random.Generator, preset: float) -> float:
    return float(np.clip(preset + rng.normal(0.0, SLIDER_JITTER), 0.0, 1.0))


def sample_market(rng: np.random.Generator) -> dict[str, float]:
    """One objective retail price per asset — the SAME dog has the SAME price
    for both exes (per-side market draws were a realism leak: the chrome
    quotes 'retail $X' as fact, so there must be exactly one X per case)."""
    m = {"wallet": WALLET_VALUE}
    for name, (lo, hi) in BASE_VALUE_RANGES.items():
        m[name] = float(rng.uniform(lo, hi))
    return m


def compile_persona(rng: np.random.Generator, side: str, archetype: str,
                    hill: str, front_mults: dict[str, float],
                    sliders: dict | None = None,
                    market: dict[str, float] | None = None) -> Persona:
    """One persona. Sentiment stacks ADDITIVELY in market units:

        v = market * max(0.2, 1 + (shape-1) + gain*pettiness*[symbolic]
                              + (front-1)*[front])  +  (hill_mult-1)*market*[hill]

    Multiplicative stacking compounded to cartoon valuations ($100k vinyl);
    additive keeps the tails absurd-but-human (a $3k opinion about a $340
    espresso machine, not a $30k one). The hill spike is the last, separable
    term so the despike counterfactual can subtract it exactly. Deterministic
    given rng state. `sliders` (the demo's Build-Your-Ex dials) overrides the
    sampled pettiness/spite/patience; `market` shares one retail table across
    the pair (sample_pair/_compile_pair pass it; standalone callers sample)."""
    spec = ARCHETYPES[archetype]
    pettiness = _sample_slider(rng, spec["pettiness"])
    lam = float(np.clip(spec["spite"] + rng.normal(0.0, 0.05), 0.0, 0.6))
    patience = _sample_slider(rng, spec["patience"])
    if sliders:
        pettiness = float(np.clip(sliders.get("pettiness", pettiness), 0, 1))
        lam = float(np.clip(sliders.get("spite", lam), 0.0, 0.6))
        patience = float(np.clip(sliders.get("patience", patience), 0, 1))

    if market is None:
        market = sample_market(rng)
    values: dict[str, float] = {"wallet": WALLET_VALUE}
    for name in BASE_VALUE_RANGES:
        raw = market[name]
        mult = spec["shape"].get(name, 1.0)
        if name in SYMBOLIC:
            mult += PETTINESS_SYMBOLIC_GAIN * pettiness
        if name in front_mults:
            mult += front_mults[name] - 1.0
        values[name] = raw * max(mult, 0.2)

    hill_mult = float(rng.uniform(*HILL_MULT_RANGE))
    values[hill] += (hill_mult - 1.0) * market[hill]
    return Persona(side=side, archetype=archetype, pettiness=pettiness, lam=lam,
                   patience=patience, hill=hill, hill_mult=hill_mult,
                   values=values, market_values=dict(market))


# ─── Opposition: measured, not asserted (SPEC.md §8) ─────────────────────────

def contested_assets(pa: Persona, pb: Persona, mult: float) -> list[str]:
    """Indivisible assets BOTH sides value at >= mult x its market price — a
    head-on sentimental collision (neither side can be cheaply bought out).
    Scale-invariant: the old >=20%-of-own-total criterion silently required
    cartoon retail prices; a realistic $2k dog can never be 20% of an estate
    with a wallet in it, yet two exes each valuing it at 3x market is
    exactly what 'contested' means."""
    return [a for a in INDIVISIBLES
            if pa.values[a] >= mult * pa.market_values[a]
            and pb.values[a] >= mult * pb.market_values[a]]


def sample_pair(rng: np.random.Generator, arch_a: str, arch_b: str,
                contested_mult: float = 2.0, min_contested: int = 2,
                max_resamples: int = 50) -> dict:
    """Sample a qualifying persona pair.

    Construction, then verification: the pair shares 1–2 "fronts" (assets both
    sides' families boosted — the dog they both raised, the vinyl that was
    "their thing"), hills land on a front with prob 1/2 (the head-on collision
    is the jackpot, SPEC.md §1). Then the contested-asset criterion is CHECKED;
    we resample up to max_resamples and record the attempt count. A pair that
    never qualifies is returned with qualified=False — the harness reports the
    failure rate rather than hiding it.
    """
    attempts = 0
    while True:
        attempts += 1
        n_fronts = int(rng.integers(1, 3))
        fronts = list(rng.choice(["dog", "vinyl", "wildcard"], size=n_fronts,
                                 replace=False))
        front_mults = {f: float(rng.uniform(*FRONT_MULT_RANGE)) for f in fronts}

        def pick_hill() -> str:
            if rng.random() < 0.5:
                return str(rng.choice(fronts))
            return str(rng.choice(HILLABLE))

        market = sample_market(rng)   # one retail table for the pair
        pa = compile_persona(rng, "A", arch_a, pick_hill(), front_mults, market=market)
        pb = compile_persona(rng, "B", arch_b, pick_hill(), front_mults, market=market)
        contested = contested_assets(pa, pb, contested_mult)
        qualified = len(contested) >= min_contested
        if qualified or attempts >= max_resamples:
            return {"a": pa, "b": pb, "contested": contested,
                    "qualified": qualified, "attempts": attempts,
                    "fronts": fronts}

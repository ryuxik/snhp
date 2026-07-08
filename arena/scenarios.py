"""Market scenarios and eras.

Everything lives in a normalized *position* line x in [0,1]:
  - position 0 = most buyer-favorable, 1 = most seller-favorable
  - seller utility at close x = x ; buyer utility = 1 - x
  - seller reservation r_s (won't go below position r_s); buyer reservation r_b
    (won't go above r_b). A ZOPA exists iff r_s <= r_b; its width r_b - r_s is
    the joint surplus (single-issue divide-the-dollar property).

Eras shift the *location* of the negotiable band (a Nash comparative static
through the disagreement point) — not who is "better," but where deals land, so
different genomes win in different regimes. 15% of price scenarios have NO ZOPA
(walking promptly is the skill).

Bundle scenarios give each issue an opposed per-option direction (common
knowledge by construction); agents bring their own priorities (genome
bundle_focus). This is a textbook-clean Raiffa information structure.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from arena.config import ArenaConfig

# Era regimes. `bundle_frac` = share of a generation's deals that are multi-issue.
ERAS = ("symmetric", "buyers", "sellers", "contract")
ERA_LABELS = {
    "symmetric": "Symmetric Market",
    "buyers": "Buyers' Market",
    "sellers": "Sellers' Market",
    "contract": "Contract Season",
}
_ERA_CENTER = {"symmetric": 0.50, "buyers": 0.36, "sellers": 0.64, "contract": 0.50}
_ERA_BUNDLE_FRAC = {"symmetric": 0.30, "buyers": 0.25, "sellers": 0.25, "contract": 0.65}
# Options-per-issue ceiling by era. Contract Season is a logrolling festival: finer
# option granularity (more room to trade a low-priority issue for a high one)
# while staying under negotiate_bundle's 4000-outcome cap (4 issues x 6 = 1296).
_ERA_BUNDLE_OPTIONS = {"symmetric": 4, "buyers": 4, "sellers": 4, "contract": 6}

_BUNDLE_ISSUES = ("price", "delivery", "quality", "terms")


@dataclass(frozen=True)
class PriceScenario:
    r_s: float          # seller reservation position
    r_b: float          # buyer reservation position
    has_zopa: bool
    era: str

    @property
    def zopa_width(self) -> float:
        return max(0.0, self.r_b - self.r_s)


@dataclass(frozen=True)
class BundleScenario:
    """issues[i] = (name, options_labels); seller_dirs[i] = per-option seller
    utility in [0,1] (buyer utility = 1 - that)."""
    issues: list
    seller_dirs: list
    era: str


def era_center(era: str, interp: float, prev_era: str) -> float:
    """Interpolated band center during an era transition (interp in [0,1])."""
    c1 = _ERA_CENTER.get(era, 0.5)
    c0 = _ERA_CENTER.get(prev_era, 0.5)
    return c0 + (c1 - c0) * float(np.clip(interp, 0.0, 1.0))


def bundle_fraction(era: str, interp: float, prev_era: str) -> float:
    f1 = _ERA_BUNDLE_FRAC.get(era, 0.3)
    f0 = _ERA_BUNDLE_FRAC.get(prev_era, 0.3)
    return f0 + (f1 - f0) * float(np.clip(interp, 0.0, 1.0))


def gen_price_scenario(cfg: ArenaConfig, era: str, center: float,
                       rng: np.random.Generator) -> PriceScenario:
    if rng.random() < cfg.no_zopa_frac:
        # No agreement zone: reservations cross. Walking is the correct play.
        gap = rng.uniform(0.0, 0.15)
        r_s = float(np.clip(center + gap / 2, 0.05, 0.95))
        r_b = float(np.clip(center - gap / 2, 0.05, 0.95))
        return PriceScenario(r_s=r_s, r_b=r_b, has_zopa=False, era=era)
    w = rng.uniform(cfg.zopa_min, cfg.zopa_max)
    lo = float(np.clip(center - w / 2, 0.02, 0.98 - w))
    return PriceScenario(r_s=lo, r_b=lo + w, has_zopa=True, era=era)


def gen_bundle_scenario(cfg: ArenaConfig, era: str, rng: np.random.Generator,
                        n_issues: int = 4, n_options: int | None = None) -> BundleScenario:
    """Each issue gets a monotone-but-shuffled per-option seller-utility vector
    in [0,1]; buyer sees the opposite direction (common knowledge). Agents bring
    their own PRIORITIES (genome bundle_focus), so the gain from trade is real
    whenever two agents weight the four issues differently — logrolling gives each
    party its high-priority issues. Contract Season uses finer option granularity
    (`_ERA_BUNDLE_OPTIONS`) for a bigger logrolling surface."""
    if n_options is None:
        n_options = _ERA_BUNDLE_OPTIONS.get(era, 4)
    names = list(_BUNDLE_ISSUES[:n_issues])
    issues = []
    seller_dirs = []
    for name in names:
        k = int(rng.integers(3, n_options + 1))  # 3..n_options options
        # A monotone ramp of seller utilities, jittered, normalized to [0,1].
        base = np.linspace(0.0, 1.0, k) + rng.normal(0.0, 0.06, size=k)
        base = np.clip(base, 0.0, 1.0)
        base = (base - base.min()) / (base.max() - base.min() + 1e-9)
        labels = [f"{name[:1]}{j}" for j in range(k)]
        issues.append((name, labels))
        seller_dirs.append([round(float(x), 4) for x in base])
    return BundleScenario(issues=issues, seller_dirs=seller_dirs, era=era)


def _norm_weights(w, n: int) -> np.ndarray:
    a = np.asarray([max(0.0, float(x)) for x in list(w)[:n]], dtype=float)
    if a.size < n:
        a = np.concatenate([a, np.zeros(n - a.size)])
    s = a.sum()
    return a / s if s > 1e-9 else np.ones(n) / n


def bundle_frontier(sc: BundleScenario, w_seller, w_buyer) -> tuple[float, float]:
    """Given the two agents' TRUE priority weights, return
    (max_joint_welfare, naive_split_welfare) over the outcome space — the
    efficient-logroll peak vs splitting every issue at its middle option. The
    denominator + floor for the science 'frontier capture %' metric: how much of
    the achievable joint surplus a settled package actually captured."""
    import itertools
    n = len(sc.issues)
    ws = _norm_weights(w_seller, n)
    wb = _norm_weights(w_buyer, n)
    dirs = sc.seller_dirs
    best = -np.inf
    for combo in itertools.product(*[range(len(d)) for d in dirs]):
        us = float(sum(ws[i] * dirs[i][combo[i]] for i in range(n)))
        ub = float(sum(wb[i] * (1.0 - dirs[i][combo[i]]) for i in range(n)))
        best = max(best, us + ub)
    mid = [len(d) // 2 for d in dirs]
    us_m = float(sum(ws[i] * dirs[i][mid[i]] for i in range(n)))
    ub_m = float(sum(wb[i] * (1.0 - dirs[i][mid[i]]) for i in range(n)))
    return float(best), float(us_m + ub_m)


def era_optimal_knob(era: str) -> float:
    """A rough, engine-estimable 'best pareto_knob' per era for the science HUD's
    'mean knob vs era optimum' overlay. Sellers' markets (room above) reward the
    margin end; buyers' markets reward deal-rate. Heuristic, labeled as such."""
    return {"symmetric": 0.7, "buyers": 0.45, "sellers": 0.9, "contract": 0.6}.get(era, 0.7)

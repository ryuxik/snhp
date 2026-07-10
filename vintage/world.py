"""The vintage world: one-of-one sourcing, sparse browser-item connections.

Honesty notes (the modeling choices reviewers should attack):
  * ONE-OF-ONE inventory: an item sold is gone forever; unsold items age on
    the rack; sourcing keeps arriving. No restock of anything, ever.
  * The item's TRUE market value (appeal) is hidden. The tag is the owner's
    noisy guess of it (sigma_tag) on top of the sourcing lottery
    (SIGMA_SOURCE) — the average gut markup is right (~3.2x cost); per piece
    it is not, and that per-piece error is the whole experiment.
  * Browsers see TAGS, never appeal. Their WTP draws around appeal — the
    market knows what things are worth even when the owner doesn't.
  * PAIRED STREAMS: item attributes depend only on (master, day, k) with a
    fixed draw order (cost, sourcing shock, tag shock), so cost and appeal
    are IDENTICAL across sigma_tag cells and tags are nested. Browser draws
    depend only on (master, day, k); the shading draw is a single uniform
    mapped around the grid center, so browser identities are nested across
    shading cells. (browser, item) private draws — connection, WTP, huff
    roll — key on the two UIDs alone, so the same person feels the same way
    about the same piece in every arm and every cell.
  * ONE purchase per browser per visit: vintage shopping is falling for a
    piece, not filling a basket. (Flagged simplification.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vintage.calibration import (CONNECT_PROB, COST_HI, COST_LO, MARKUP_MU,
                                 SHADING_SPREAD, SIGMA_SOURCE, SIGMA_WTP,
                                 SOURCING_RATE, TRAFFIC_MEAN)
from vintage.core import substream


@dataclass(frozen=True)
class VintageConfig:
    """The experiment knobs — everything else is calibration.py."""
    sigma_tag: float = 0.3     # owner's per-piece tagging noise
    shading: float = 0.85      # center of the browsers' offer-shading factor


DEFAULT_CONFIG = VintageConfig()


@dataclass(frozen=True)
class Item:
    uid: int
    cost: float          # sourcing cost (sunk once bought)
    appeal: float        # TRUE market value — hidden from everyone in-sim
    tag: float           # the owner's posted guess (whole dollars)
    arrival_day: int


@dataclass(frozen=True)
class Browser:
    uid: int
    shading: float       # their personal offer = WTP x shading


def items_for_day(master_seed: int, day: int,
                  cfg: VintageConfig = DEFAULT_CONFIG) -> list[Item]:
    """Paired across arms AND nested across cells: the count depends only on
    (master, day); item k's draws come in fixed order (cost, sourcing shock,
    tag shock) so sigma_tag moves ONLY the tag."""
    n = int(np.random.default_rng(
        substream(master_seed, "src", day)).poisson(SOURCING_RATE))
    out = []
    for k in range(n):
        rng = np.random.default_rng(substream(master_seed, "item", day, k))
        cost = float(np.exp(rng.uniform(math.log(COST_LO), math.log(COST_HI))))
        appeal = float(cost * MARKUP_MU * np.exp(rng.normal(0.0, SIGMA_SOURCE)))
        raw_tag = appeal * float(np.exp(rng.normal(0.0, cfg.sigma_tag)))
        tag = float(max(round(raw_tag), math.ceil(cost) + 2))  # never below
        # cost-plus-a-coffee: no dealer knowingly tags under what they paid
        out.append(Item(uid=substream(master_seed, "iuid", day, k),
                        cost=round(cost, 2), appeal=round(appeal, 2),
                        tag=tag, arrival_day=day))
    return out


def browsers_for_day(master_seed: int, day: int,
                     cfg: VintageConfig = DEFAULT_CONFIG) -> list[Browser]:
    """Paired: count and identities depend only on (master, day, k). The
    shading center shifts the SAME uniform draw, so browser k is the same
    haggler (relatively) in every shading cell."""
    n = int(np.random.default_rng(
        substream(master_seed, "traffic", day)).poisson(TRAFFIC_MEAN))
    out = []
    for k in range(n):
        rng = np.random.default_rng(substream(master_seed, "bro", day, k))
        u = float(rng.random())
        out.append(Browser(uid=substream(master_seed, "buid", day, k),
                           shading=cfg.shading + (2 * u - 1) * SHADING_SPREAD))
    return out


class PairDraws:
    """Memoized private draws for a (browser, item) pair — THE pairing
    guarantee: keyed on the two uids alone (never on inventory, never on
    anything a policy did), so every arm sees the identical (connects, WTP,
    huff roll) triple for the same person meeting the same piece. Shared
    across the arms of one replicate; also saves ~3x on hashing."""

    def __init__(self):
        self._memo: dict[tuple[int, int], tuple[bool, float, float]] = {}

    def get(self, b: Browser, it: Item) -> tuple[bool, float, float]:
        key = (b.uid, it.uid)
        got = self._memo.get(key)
        if got is None:
            rng = np.random.default_rng(substream(b.uid, "pair", it.uid))
            connect = bool(rng.random() < CONNECT_PROB)
            wtp = float(it.appeal * np.exp(rng.normal(0.0, SIGMA_WTP)))
            huff_roll = float(rng.random())
            got = (connect, wtp, huff_roll)
            self._memo[key] = got
        return got

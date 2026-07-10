"""The block's paired ledger — event log + the honest counterfactual math.

Layering rule (B0 hard requirement): the ledger READS events (plain dicts
emitted by the runner) and end-of-day closes. It never touches venues,
policies, or the population. Rents are injected at construction (the runner
reads them off the venue classes), so the ledger carries no calibration
imports either.

Conservation is testable, not asserted on faith: venues keep their own
per-day revenue counters (venue-side truth, accumulated at settle time in
the same order as the ledger's event-side aggregates), so equality is EXACT
float equality per (world, venue, day) — money is never created or
destroyed between a consumer's wallet and a venue's till.

Delta decomposition is exact BY CONSTRUCTION: the block-level per-day delta
is defined as the sum of the per-venue deltas (block_day_delta), and the
tests additionally check it against an independent recomputation.

Event schema (all optional fields explicit at the emit site):
  arrival       {type, world, day, tick, uid, persona, kind, home}
  venue_entered {type, world, venue, day, tick, uid, persona, kind}
  deal          {..., sku, qty, unit_price, spend, cogs, surplus,
                 raw_surplus, walk, negotiated}
                 (+ boba: tops, slot_ticks · fashion: size — extra keys,
                  same shape; the ledger reads only the core fields)
  no_sale       {type, world, day, tick, uid, persona, kind}
                 (+ reason on the boba/fashion lanes: balk/lost/stockout/
                  waiting)

`surplus` is the buyer's realized utility NET of the cross-venue walk (or
pickup-deferral disutility) they actually incurred (raw_surplus is the
at-the-counter number) — the HUD's "shoppers kept $X" counts hassle
honestly.
"""
from __future__ import annotations

import math

import numpy as np

DELTA_METRICS = ("margin", "revenue", "consumer_surplus", "units", "deals")

# Priority #2 (paper/CALIBRATION-TARGETS.md; pre-registered CRITICAL-
# ANALYSIS.md §5): fashion's board reprices WEEKLY (every 7 block days),
# not daily like the other three venues, so a 5-day block CI aliases
# against that cadence (n=6 blocks over 30 days vs 4+ actual week
# boundaries — RESULTS-B1B2.md's Surprise 3 flagged this as "indicative,
# not sharp"). Fashion's venue-level paired CI uses 7-day blocks instead;
# every other venue (and the block-level aggregate, which mixes daily and
# weekly cadences) keeps the 5-day default.
VENUE_CI_BLOCK = {"fashion": 7}
DEFAULT_CI_BLOCK = 5


def paired_ci(diffs: list[float], block: int = 5) -> dict:
    """Mean paired difference with a 95% t-interval — the same block-CI
    helper pattern as vend.run.paired_ci: daily diffs are serially
    dependent (leftover lots, learner state, references carry across days),
    so the headline interval uses `block`-day means — fewer, more
    independent observations — which widens the CI honestly."""
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        n_blocks = len(d) // block
        d = d[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)],
            "n": n, "block": block}


class BlockLedger:
    """Event log + per-(world, venue, day) aggregates + paired deltas.
    The venue set is DERIVED from the rents injected at construction (the
    runner reads them off the selected venue classes), so a two-venue B0
    ledger and the four-venue block use the same code path."""

    WORLDS = ("sticker", "snhp")

    def __init__(self, rents: dict[str, float]):
        self.rents = dict(rents)
        self.venues = tuple(rents)
        self.events: list[dict] = []
        self._agg: dict[tuple, dict] = {}
        self._traffic: dict[tuple, dict] = {}

    # ── ingestion ────────────────────────────────────────────────────────
    def _bucket(self, world: str, venue: str, day: int) -> dict:
        key = (world, venue, day)
        if key not in self._agg:
            self._agg[key] = {"revenue": 0.0, "cogs": 0.0, "units": 0,
                              "deals": 0, "negotiated": 0,
                              "consumer_surplus": 0.0,
                              "spoiled_units": 0, "spoilage_cost": 0.0}
        return self._agg[key]

    def _tbucket(self, world: str, day: int) -> dict:
        key = (world, day)
        if key not in self._traffic:
            self._traffic[key] = {"arrivals": 0, "no_sales": 0}
        return self._traffic[key]

    def record(self, ev: dict) -> None:
        self.events.append(ev)
        t = ev["type"]
        if t == "deal":
            b = self._bucket(ev["world"], ev["venue"], ev["day"])
            b["revenue"] += ev["spend"]
            b["cogs"] += ev["cogs"]
            b["units"] += ev["qty"]
            b["deals"] += 1
            b["negotiated"] += int(ev.get("negotiated", False))
            b["consumer_surplus"] += ev["surplus"]
        elif t == "arrival":
            self._tbucket(ev["world"], ev["day"])["arrivals"] += 1
        elif t == "no_sale":
            self._tbucket(ev["world"], ev["day"])["no_sales"] += 1

    def close_day(self, world: str, venue: str, day: int,
                  spoiled_units: int = 0, spoilage_cost: float = 0.0) -> None:
        b = self._bucket(world, venue, day)
        b["spoiled_units"] += spoiled_units
        b["spoilage_cost"] += spoilage_cost

    # ── aggregates ───────────────────────────────────────────────────────
    def day_metrics(self, world: str, venue: str, day: int) -> dict:
        """One venue-day, unrounded. margin = revenue − cogs − spoilage −
        rent: NYC margins read honestly against fixed costs (DESIGN §3)."""
        m = dict(self._bucket(world, venue, day))
        m["rent"] = self.rents.get(venue, 0.0)
        m["margin"] = m["revenue"] - m["cogs"] - m["spoilage_cost"] - m["rent"]
        return m

    def traffic(self, world: str, day: int) -> dict:
        return dict(self._tbucket(world, day))

    # ── the paired counterfactual ────────────────────────────────────────
    def day_delta(self, venue: str, day: int, metric: str) -> float:
        return (self.day_metrics("snhp", venue, day)[metric]
                - self.day_metrics("sticker", venue, day)[metric])

    def block_day_delta(self, day: int, metric: str) -> float:
        """The HUD counters' per-day increment — DEFINED as the sum of the
        per-venue deltas, so the decomposition is exact by construction."""
        return sum(self.day_delta(v, day, metric) for v in self.venues)

    def paired_deltas(self, days: int) -> dict:
        out: dict[str, dict] = {}
        for venue in self.venues:
            block = VENUE_CI_BLOCK.get(venue, DEFAULT_CI_BLOCK)
            out[venue] = {m: paired_ci([self.day_delta(venue, d, m)
                                        for d in range(days)], block=block)
                          for m in DELTA_METRICS}
        out["block"] = {m: paired_ci([self.block_day_delta(d, m)
                                      for d in range(days)],
                                     block=DEFAULT_CI_BLOCK)
                        for m in DELTA_METRICS}
        return out

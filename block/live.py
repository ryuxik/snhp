"""block/live.py — the long-running LIVE twin-street driver (Phase 5).

Runs the paired STICKER vs SNHP ten-venue block CONTINUOUSLY, one sim-day
per step, on top of the committed engine — block.runner's build_world /
run_world_day stepped in place, never re-derived. Each completed day emits
one compact DAY-RECORD (per-venue margin delta, consumer surplus, walk-aways,
waste, the ledger conservation check, seed/day/engine version) and appends it
to a JSONL telemetry log — the day-one-useful experiment data that feeds back
into SNHP.

Determinism contract (tested in block/tests/test_live.py):
  • season s runs seed = base_seed + s; the day-record's ECONOMIC fields (s, d)
    are a pure function of (base_seed, config, code version) — replay_day()
    reproduces any day from scratch, byte-identical ON THE ECONOMIC FIELDS (the
    attestation excluded: an Ed25519 signature is key-dependent, and the key is
    process-ephemeral unless NOTARY_KEY_PEM is set). Under a FIXED key the
    attestation is deterministic too, so replay_day reproduces it as well; the
    resume path compares _strip_det (attestation dropped) to stay key-agnostic.
  • the JSONL log adds ONLY a wall-clock "ts" field at write time; stripping
    it recovers the deterministic record.
  • on restart the driver RESUMES by re-simulating the current season up to
    the last logged day and verifying the resim against the log; if the code
    changed (records no longer match) it starts a fresh season instead of
    silently splicing incompatible histories.

Season = 98 days (one full 14-week fashion season, salvage writedown
included, so no season's margin is gross of clearance risk). Ledger event
lists are pruned after each day (aggregates are incremental) so memory stays
bounded on an unbounded run.

Conservation: per (world, venue, day), the ledger's event-side revenue must
equal the venue's own till. The four street venues match with EXACT float
equality (block/tests/test_block.py's law); the six standalone storefronts
round their running till at each add, so ledger-vs-till differs only in
float representation (≤2e-11 measured) — the record carries max_abs_err and
ok = (max_abs_err < 1e-9), nine orders below a cent.

Run it yourself:
    python3 -m block.live --season 0 --day 12      # reproduce one day-record
    python3 -m block.live --steps 3 --log /tmp/block-live.jsonl   # step the log
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone

from block.ledger import BlockLedger
from block.runner import (ALL_VENUES, BLOCK_VERSION, WORLDS, _VENUE_CLASSES,
                          build_world, run_world_day)
from block.venues import (BlockConfig, build_block_catalog,
                          build_fashion_plan)
from core.notary import (canon_hash, emit_ledger_receipt, engine_version,
                         load_notary_key)
from core.state import ShopState

# v2: day-records now carry a signed, chained NotaryReceipt under
# "attestation" (the counterfactual ledger, notarized).
DAY_SCHEMA = "block.live.day.v2"
SNAP_SCHEMA = "block.live.v2"
DRIVER_VERSION = 2
SEED_DEFAULT = 20260710            # the committed gen_week seed
SEASON_DAYS_DEFAULT = 98           # one full fashion season (14 weeks)
WINDOW_DEFAULT = 14                # day-records kept in the rolling window
CONS_TOL = 1e-9                    # see module docstring — float repr only

# the live experiment runs the SAME config the canned trailer week traces to
# (block/gen_week.py): calibrated operator noise, 25 regulars, adopting bodega
LIVE_CONFIG = dict(sigma_cal=0.15, anchor_mult=1.0, regulars=25,
                   bodega_adopts=True)


def _r2(x: float) -> float:
    return round(float(x), 2)


def strip_ts(rec: dict) -> dict:
    """The record minus the write-time wall-clock ts. The `attestation` (a
    signed receipt over the deterministic record) is KEPT — a stepped record
    and a stripped logged record carry the same attestation."""
    return {k: v for k, v in rec.items() if k != "ts"}


def _strip_det(rec: dict) -> dict:
    """The DETERMINISTIC part used for resume verification: drop both the
    write-time ts AND the attestation. The attestation's signature depends on
    the notary key, which is process-ephemeral unless NOTARY_KEY_PEM is set, so
    it is never part of the (base_seed, config, code)-pure record the resim
    reproduces. Tamper detection still covers every economic field."""
    return {k: v for k, v in rec.items() if k not in ("ts", "attestation")}


def read_log(path: str) -> list[dict]:
    """Read the JSONL telemetry log, skipping corrupt lines (a crash mid-
    write must not poison the resume)."""
    recs: list[dict] = []
    if not path or not os.path.exists(path):
        return recs
    skipped_schemas: set[str] = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("schema") == DAY_SCHEMA:
                recs.append(rec)
            elif isinstance(rec, dict) and "schema" in rec:
                skipped_schemas.add(str(rec.get("schema")))
    if skipped_schemas:
        # ops visibility for the one-time v1→v2 boundary: an older-schema log is
        # skipped (not resumed), so the driver starts fresh rather than silently
        # ignoring history. One informative line, not per-record noise.
        print(f"read_log: skipped records with schema(s) "
              f"{sorted(skipped_schemas)} != {DAY_SCHEMA!r} (schema boundary)",
              file=sys.stderr)
    return recs


def _zero_totals(venues) -> dict:
    return {"days": 0,
            "d_margin": 0.0, "d_cs": 0.0,
            "margin": {"sticker": 0.0, "snhp": 0.0},
            "arrivals": {"sticker": 0, "snhp": 0},
            "walkaways": {"sticker": 0, "snhp": 0},
            "waste": {"sticker": 0.0, "snhp": 0.0},
            "per_venue": {v: {"d_margin": 0.0, "d_cs": 0.0} for v in venues}}


class LiveBlock:
    """The stateful twin-street driver: build both worlds once per season,
    step them one day at a time, emit one day-record per day. Pure sim — no
    web/server dependency; arena/api.py paces it and streams the records."""

    def __init__(self, seed: int = SEED_DEFAULT, venues=ALL_VENUES,
                 cfg: BlockConfig | None = None,
                 season_days: int = SEASON_DAYS_DEFAULT,
                 window: int = WINDOW_DEFAULT,
                 log_path: str | None = None,
                 secs_per_day: float | None = None):
        self.seed = int(seed)
        self.venue_names = tuple(venues)
        self.cfg = cfg if cfg is not None else BlockConfig(**LIVE_CONFIG)
        self.season_days = int(season_days)
        self.log_path = log_path
        self.secs_per_day = secs_per_day        # display metadata only
        # record.git == attestation.engine_version by construction (both are
        # core.notary.engine_version(): $SOURCE_VERSION else the short git SHA)
        self.git = engine_version()
        self.window: deque = deque(maxlen=window)
        self.totals = _zero_totals(self.venue_names)          # lifetime
        self.season_totals = _zero_totals(self.venue_names)   # current season
        self.resume_info: dict = {"mode": "fresh"}
        # the notary: one signed, chained day-receipt per day. Key from
        # NOTARY_KEY_PEM (persistent) else ephemeral (key_source recorded on
        # every receipt + in the snapshot). The chain is per-season — each
        # season is an independent experiment (its own seed), so replay_day can
        # reproduce a season's chain from day 0.
        self.notary_key = load_notary_key()
        self._chain_head: str | None = None
        self._start_season(0)
        self.public = self.snapshot()   # atomically-swapped read state

    # ── season lifecycle ──────────────────────────────────────────────────
    def season_seed(self, season: int) -> int:
        return self.seed + season

    def _start_season(self, season: int) -> None:
        self.season = season
        self.day = 0                    # next day to run within the season
        self._chain_head = None         # a fresh per-season receipt chain
        self.season_totals = _zero_totals(self.venue_names)
        seed = self.season_seed(season)
        self.ledger = BlockLedger(
            rents={v: _VENUE_CLASSES[v].rent_per_day
                   for v in self.venue_names})
        catalog = (build_block_catalog(self.cfg, seed)
                   if "vending" in self.venue_names else None)
        plan = (build_fashion_plan(self.cfg, seed)
                if "fashion" in self.venue_names else None)
        # dawn=None: the wholesale tier stays off (cfg default), matching the
        # committed gen_week config the trailer numbers trace to
        self.states = {w: build_world(w, seed, self.cfg,
                                      venues=self.venue_names,
                                      catalog=catalog, fashion_plan=plan,
                                      dawn=None)
                       for w in WORLDS}

    # ── one day ───────────────────────────────────────────────────────────
    def _run_day(self, day: int) -> dict:
        """Advance both worlds one day and build the deterministic record.
        Does NOT touch totals/window/log (step_day does; resume verifies)."""
        for w in WORLDS:
            run_world_day(self.states[w], day, self.ledger)
        rec = self._day_record(day)
        # prune the raw event list — the per-day aggregates the record reads
        # are accumulated incrementally, and ~12k events/day would grow
        # unbounded on a long-running driver
        self.ledger.events.clear()
        return rec

    def _day_record(self, day: int) -> dict:
        venues_out = {}
        max_err = 0.0
        for v in self.venue_names:
            m = {w: self.ledger.day_metrics(w, v, day) for w in WORLDS}
            for w in WORLDS:
                till = self.states[w].venues[v].revenue_by_day.get(day, 0.0)
                err = abs(m[w]["revenue"] - till)
                if err > max_err:
                    max_err = err
            venues_out[v] = {
                "margin": {w: _r2(m[w]["margin"]) for w in WORLDS},
                "d_margin": _r2(m["snhp"]["margin"] - m["sticker"]["margin"]),
                "d_cs": _r2(m["snhp"]["consumer_surplus"]
                            - m["sticker"]["consumer_surplus"]),
                "deals": {w: m[w]["deals"] for w in WORLDS},
            }
        traffic = {}
        for w in WORLDS:
            t = self.ledger.traffic(w, day)
            traffic[w] = {"arrivals": t["arrivals"],
                          "walkaways": t["no_sales"]}
        waste = {w: {"cost": _r2(sum(self.ledger.day_metrics(w, v, day)
                                     ["spoilage_cost"]
                                     for v in self.venue_names)),
                     "units": sum(self.ledger.day_metrics(w, v, day)
                                  ["spoiled_units"]
                                  for v in self.venue_names)}
                 for w in WORLDS}
        block = {
            "d_margin": _r2(sum(venues_out[v]["d_margin"]
                                for v in self.venue_names)),
            "d_cs": _r2(sum(venues_out[v]["d_cs"]
                            for v in self.venue_names)),
            "margin": {w: _r2(sum(venues_out[v]["margin"][w]
                                  for v in self.venue_names))
                       for w in WORLDS},
        }
        return {
            "schema": DAY_SCHEMA,
            "seed": self.seed,
            "season": self.season,
            "season_seed": self.season_seed(self.season),
            "season_days": self.season_days,
            "day": day,
            "engine": {"block_version": BLOCK_VERSION,
                       "driver_version": DRIVER_VERSION, "git": self.git},
            "block": block,
            "venues": venues_out,
            "traffic": traffic,
            "waste": waste,
            "conservation": {"ok": bool(max_err < CONS_TOL),
                             "max_abs_err": float(max_err),
                             "law": "ledger revenue == venue till, "
                                    "per (world, venue, day)"},
        }

    @staticmethod
    def _accumulate(tot: dict, rec: dict) -> None:
        tot["days"] += 1
        tot["d_margin"] += rec["block"]["d_margin"]
        tot["d_cs"] += rec["block"]["d_cs"]
        for w in WORLDS:
            tot["margin"][w] += rec["block"]["margin"][w]
            tot["arrivals"][w] += rec["traffic"][w]["arrivals"]
            tot["walkaways"][w] += rec["traffic"][w]["walkaways"]
            tot["waste"][w] += rec["waste"][w]["cost"]
        for v, row in rec["venues"].items():
            pv = tot["per_venue"][v]
            pv["d_margin"] += row["d_margin"]
            pv["d_cs"] += row["d_cs"]

    def _attest(self, rec: dict) -> dict:
        """Notarize one deterministic day-record as a LEDGER receipt: a signed,
        chained NotaryReceipt whose `counterfactual` block carries the day's
        paired totals {sticker_world_total, snhp_world_total, delta} and whose
        prev_hash is the previous day-receipt's digest (None at a season's first
        day; chain_id = f"s{season}" so the season boundary is a legal reset).
        A day is an AGGREGATE, not a single quote, so there is NO fabricated
        shell Quote and NO by-fiat economics: regime is "ledger", the per-quote
        economic fields are honestly null, and conditions a/a_prime/b/d are None
        (only c, the engine version, is attested). ts is a DETERMINISTIC logical
        stamp (not wall-clock) so replay_day reproduces the record. Per-day
        receipts do NOT embed the PEM — trust pins on pubkey_fpr and the
        snapshot's notary block carries the single PEM copy.
        """
        b = rec["block"]
        cf = {"sticker_world_total": b["margin"]["sticker"],
              "snhp_world_total": b["margin"]["snhp"],
              "delta": b["d_margin"]}
        season, day = rec["season"], rec["day"]
        receipt = emit_ledger_receipt(
            cf, quote_ref=f"block-s{season}-d{day}", venue_id="ten-venue-block",
            prev_hash=self._chain_head, chain_id=f"s{season}",
            state=ShopState(tick=day),
            disclosure=canon_hash({"block_day": [season, day]}),
            key=self.notary_key, ts=f"D{season:04d}-{day:03d}",
            embed_pubkey=False)
        self._chain_head = receipt.digest()
        return receipt.to_dict()

    def _persist_chain_head(self) -> None:
        """Persist the chain head next to the JSONL (a small sidecar) so an
        external consumer can pick up the head without re-reading the whole log.
        Written atomically (temp file + os.replace) so a crash mid-write never
        leaves a torn sidecar. The log itself remains authoritative on resume."""
        if not self.log_path:
            return
        side = self.log_path + ".chain.json"
        tmp = side + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"chain_head": self._chain_head, "season": self.season,
                       "day": self.day, "pubkey_fpr": self.notary_key.pubkey_fpr,
                       "key_source": self.notary_key.key_source}, f)
        os.replace(tmp, side)

    def step_day(self) -> dict:
        """Run the next day, notarize it, fold it into the totals/window,
        append it to the telemetry log (with a write-time ts), roll the season
        when it completes, and swap the public snapshot. Returns the attested
        day-record."""
        rec = self._run_day(self.day)              # the deterministic record
        self._accumulate(self.totals, rec)
        self._accumulate(self.season_totals, rec)
        attested = {**rec, "attestation": self._attest(rec)}
        self.window.append(attested)
        if self.log_path:
            line = json.dumps(
                {**attested, "ts": datetime.now(timezone.utc)
                 .isoformat(timespec="seconds")},
                separators=(",", ":"))
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")
            self._persist_chain_head()
        self.day += 1
        if self.day >= self.season_days:
            self._start_season(self.season + 1)
        self.public = self.snapshot()
        return attested

    # ── resume (restart-safe determinism) ─────────────────────────────────
    def _compatible(self, rec: dict) -> bool:
        return (rec.get("seed") == self.seed
                and rec.get("season_days") == self.season_days
                and set(rec.get("venues", {})) == set(self.venue_names)
                and rec.get("engine", {}).get("block_version")
                == BLOCK_VERSION)

    def resume(self) -> dict:
        """Rebuild driver state from the JSONL log. Lifetime totals fold the
        log's (compatible) records; world state is re-simulated for the
        current season and VERIFIED against the logged records — an exact
        continuation, or a fresh season if determinism broke (code change)."""
        recs = [r for r in read_log(self.log_path or "")]
        compat = [r for r in recs if self._compatible(r)]
        if not compat:
            self.resume_info = {"mode": "fresh",
                                "reason": ("no log" if not recs
                                           else "incompatible log")}
            if recs:   # keep incompatible history immutable: new season id
                last_season = max(r.get("season", 0) for r in recs)
                self._start_season(last_season + 1)
                self.resume_info["mode"] = "fresh-season"
                self.resume_info["season"] = self.season
            self.public = self.snapshot()
            return self.resume_info
        for r in compat:
            self._accumulate(self.totals, strip_ts(r))
        last = compat[-1]
        season, day = last["season"], last["day"]
        # verify against the DETERMINISTIC part only — the attestation's
        # signature is process-ephemeral unless NOTARY_KEY_PEM is set, so
        # comparing it would spuriously fail every restart under an ephemeral
        # key. Every economic field is still covered, so tamper detection holds.
        season_recs = {r["day"]: _strip_det(r) for r in compat
                       if r["season"] == season}
        self._start_season(season)
        verified, mismatch = 0, False
        for d in range(day + 1):
            rec = self._run_day(d)
            logged = season_recs.get(d)
            if logged is not None:
                if rec != logged:
                    mismatch = True
                    break
                verified += 1
            self._accumulate(self.season_totals, rec)
        if mismatch:
            # the code no longer reproduces the log: never splice — the
            # history stays immutable and the run continues honestly under a
            # new season id (records carry the git sha either way)
            self.totals = _zero_totals(self.venue_names)
            for r in compat:
                self._accumulate(self.totals, strip_ts(r))
            self._start_season(season + 1)
            self.resume_info = {"mode": "fresh-season",
                                "reason": "resim mismatch (code changed?)",
                                "season": self.season}
        else:
            self.day = day + 1
            if self.day >= self.season_days:
                self._start_season(season + 1)      # new season → fresh chain
            else:
                # continue the chain from the last logged day-receipt (hash-
                # linked across the restart even if the key rotated)
                att = last.get("attestation")
                self._chain_head = canon_hash(att) if att else None
            for r in compat[-self.window.maxlen:]:
                self.window.append(strip_ts(r))
            self.resume_info = {"mode": "resumed", "season": self.season,
                                "day": self.day, "verified_days": verified}
        self.public = self.snapshot()
        return self.resume_info

    # ── the read side ─────────────────────────────────────────────────────
    def _round_totals(self, tot: dict) -> dict:
        out = json.loads(json.dumps(tot))   # deep copy (plain JSON types)
        out["d_margin"] = _r2(out["d_margin"])
        out["d_cs"] = _r2(out["d_cs"])
        for w in WORLDS:
            out["margin"][w] = _r2(out["margin"][w])
            out["waste"][w] = _r2(out["waste"][w])
        for v in out["per_venue"]:
            out["per_venue"][v]["d_margin"] = _r2(out["per_venue"][v]["d_margin"])
            out["per_venue"][v]["d_cs"] = _r2(out["per_venue"][v]["d_cs"])
        return out

    def snapshot(self) -> dict:
        """The connect-time payload: cumulative totals + the rolling window.
        Every number here is a fold of logged day-records — nothing invented."""
        snap = {
            "schema": SNAP_SCHEMA,
            "live": True,
            "seed": self.seed,
            "season": self.season,
            "day": self.day,                 # days completed this season
            "season_days": self.season_days,
            "venues": list(self.venue_names),
            "engine": {"block_version": BLOCK_VERSION,
                       "driver_version": DRIVER_VERSION, "git": self.git},
            "config": {"sigma_cal": self.cfg.sigma_cal,
                       "anchor_mult": self.cfg.anchor_mult,
                       "regulars": self.cfg.regulars,
                       "bodega_adopts": self.cfg.bodega_adopts,
                       "wholesale": self.cfg.wholesale},
            "totals": {"lifetime": self._round_totals(self.totals),
                       "season": self._round_totals(self.season_totals)},
            "last_records": list(self.window),
            "notary": {
                "chain_head": self._chain_head,
                "pubkey_pem": self.notary_key.pubkey_pem,
                "pubkey_fpr": self.notary_key.pubkey_fpr,
                "key_source": self.notary_key.key_source,
                "algo": self.notary_key.algo,
                "note": ("each day-record carries a signed, chained "
                         "NotaryReceipt (attestation); verify a log with "
                         "`python3 -m core.notary verify <log.jsonl>`"),
            },
            "resume": self.resume_info,
            "reproduce": (f"python3 -m block.live --seed {self.seed} "
                          f"--season {self.season} --day D  "
                          "# re-simulates day D of this season, byte-identical"),
        }
        if self.secs_per_day is not None:
            snap["secs_per_day"] = self.secs_per_day
        return snap


def replay_day(season: int, day: int, seed: int = SEED_DEFAULT,
               venues=ALL_VENUES, cfg: BlockConfig | None = None,
               season_days: int = SEASON_DAYS_DEFAULT) -> dict:
    """Reproduce ONE attested day-record from scratch — the 'rerun it yourself'
    path. Re-simulates the season from day 0 (state carries across days, so day
    d is a function of days 0..d) and rebuilds the per-season receipt chain, so
    the returned record — attestation included — is byte-identical to the
    stepped one (given the same notary key; signatures are deterministic under
    a fixed key, and the receipt ts is a logical, not wall-clock, stamp)."""
    lb = LiveBlock(seed=seed, venues=venues, cfg=cfg, season_days=season_days)
    lb._start_season(season)
    rec = None
    for d in range(day + 1):
        raw = lb._run_day(d)
        rec = {**raw, "attestation": lb._attest(raw)}
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="live twin-street driver: replay one day-record, or "
                    "step days into a JSONL telemetry log")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    ap.add_argument("--season", type=int, default=0)
    ap.add_argument("--day", type=int, default=None,
                    help="replay mode: print this day's record and exit")
    ap.add_argument("--season-days", type=int, default=SEASON_DAYS_DEFAULT)
    ap.add_argument("--steps", type=int, default=None,
                    help="driver mode: resume from --log and run N days")
    ap.add_argument("--log", default=None, help="JSONL telemetry log path")
    args = ap.parse_args(argv)

    if args.day is not None:
        rec = replay_day(args.season, args.day, seed=args.seed,
                         season_days=args.season_days)
        print(json.dumps(rec, indent=1))
        return 0
    if args.steps is None:
        ap.error("pass --day D (replay) or --steps N (drive)")
    lb = LiveBlock(seed=args.seed, season_days=args.season_days,
                   log_path=args.log)
    if args.log:
        info = lb.resume()
        print(f"resume: {info}", file=sys.stderr)
    for _ in range(args.steps):
        rec = lb.step_day()
        print(f"season {rec['season']} day {rec['day']}: "
              f"Δmargin {rec['block']['d_margin']:+.2f} "
              f"ΔCS {rec['block']['d_cs']:+.2f} "
              f"conservation {'ok' if rec['conservation']['ok'] else 'FAIL'}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

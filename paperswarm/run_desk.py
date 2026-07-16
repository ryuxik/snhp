"""PAPERSWARM desk CLI (SPEC.md Phase 1: "CLI status report"). Cron-friendly,
15-min cadence.

    python -m paperswarm.run_desk --poll      # search + build comps + resolve bids
    python -m paperswarm.run_desk --decide    # scout -> price -> commit bids (arm B)
    python -m paperswarm.run_desk --report    # P&L derived ONLY from ledger + comps
    python -m paperswarm.run_desk --verify     # recompute the hash chain

P&L is NEVER stored — it is recomputed from the receipt chain + comp store on
every --report, so nothing is shown that a third party couldn't regenerate
(SPEC honesty protocol).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from . import config, ledger as ledger_mod
from .comps import Comps
from .feed import EbayFeed, Listing
from .fills import FillEngine, compute_pnl
from .identity import parse_identity
from .ledger import Ledger, verify_chain
from .outcomes import OutcomeTracker
from .swarm import Desk
from .timeutil import now_utc, parse_iso


def _as_of(args) -> datetime:
    return parse_iso(args.as_of) if args.as_of else now_utc()


def _build(args):
    """Wire ledger -> comps -> engine -> metered feed. Single object graph."""
    led = Ledger(args.ledger)
    comps = Comps(args.db)
    engine = FillEngine(led, comps)
    feed = EbayFeed(meter=engine.meter, fixture=(True if args.fixture else None))
    return led, comps, engine, feed


def _listing_from_commit(commit: dict) -> Listing:
    """Rebuild a minimal Listing from a bid_commit receipt (for resolution)."""
    return Listing(
        listing_id=commit["listing_id"],
        title=commit.get("title", ""),
        price=0.0,
        listing_type="AUCTION",
        close_time=parse_iso(commit.get("close_time")),
        seller="",
        raw={},
    )


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------
def cmd_poll(args) -> int:
    """Search the niche, build comps from terminal outcomes, resolve open bids."""
    led, comps, engine, feed = _build(args)
    tracker = OutcomeTracker(feed, comps)
    as_of = _as_of(args)

    listings = feed.search()
    terminal = tracker.sweep(listings, as_of)

    # Resolve our own open bids to fills (observe each by listing_id).
    resolved = 0
    for commit in list(engine.state().open_bids.values()):
        listing = _listing_from_commit(commit)
        outcome = tracker.observe(listing, as_of)
        if not outcome.is_terminal:
            continue
        # Learn the realized clearing price as a comp too (idempotent).
        ident = parse_identity(listing.title)
        tracker.record(listing, ident, outcome)
        engine.resolve(commit["listing_id"], outcome.hammer,
                       resolve_time=as_of, status=outcome.status)
        resolved += 1

    print(f"[poll] mode={'FIXTURE' if feed.fixture else 'LIVE'} "
          f"listings={len(listings)} terminal={len(terminal)} "
          f"resolved_bids={resolved} comps={comps.count()} "
          f"store_span={comps.store_span_days():.2f}d")
    comps.close()
    return 0


def cmd_decide(args) -> int:
    """Scout -> price -> treasury-gated commit (arm B)."""
    led, comps, engine, feed = _build(args)
    desk = Desk(feed, comps, engine)
    as_of = _as_of(args)
    decisions = desk.decide(as_of, cold_start_override=args.cold_start_override)

    bids = [d for d in decisions if d.action == "bid"]
    print(f"[decide] mode={'FIXTURE' if feed.fixture else 'LIVE'} "
          f"cold_started={desk.cold_started()} decisions={len(decisions)} "
          f"bids={len(bids)}")
    for d in decisions:
        fv = f"fv={d.fair_value}" if d.fair_value is not None else "fv=-"
        mb = f"max_bid={d.max_bid}" if d.max_bid is not None else "max_bid=-"
        print(f"  {d.action:4s} {d.listing_id:18s} {d.reason:22s} "
              f"{fv} {mb} n={d.n_comps}")
    comps.close()
    return 0


def cmd_report(args) -> int:
    """P&L derived ONLY from ledger + comps (SPEC report rule)."""
    led = Ledger(args.ledger)
    comps = Comps(args.db)
    as_of = _as_of(args)
    pnl = compute_pnl(led, comps, as_of)

    # Event-type census (chain provenance).
    counts: dict[str, int] = {}
    for rec in led.records():
        counts[rec.type] = counts.get(rec.type, 0) + 1
    chain = verify_chain(args.ledger)
    engine = FillEngine(led, comps)
    state = engine.state()

    if args.json:
        out = {
            "as_of": as_of.isoformat(),
            "pnl": pnl.__dict__,
            "events": counts,
            "chain": {"ok": chain.ok, "length": chain.length, "error": chain.error},
            "comps": comps.count(),
            "store_span_days": round(comps.store_span_days(), 2),
            "open_bids": list(state.open_bids.keys()),
            "inventory": state.inventory,
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        comps.close()
        return 0

    line = "=" * 60
    print(line)
    print("PAPERSWARM desk report  (all figures regenerate from receipts)")
    print(f"  as_of: {as_of.isoformat()}")
    print(line)
    print(f"  bankroll        ${pnl.bankroll:>10,.2f}")
    print(f"  cash            ${pnl.cash:>10,.2f}")
    print(f"  locked          ${pnl.locked:>10,.2f}  (capital committed to open bids)")
    print(f"  available       ${pnl.available:>10,.2f}")
    print(f"  compute charged ${pnl.compute_cost:>10,.4f}  (metered API/LLM)")
    print(f"  inventory mark  ${pnl.inventory_mark:>10,.2f}  (25th-pct realized, net friction+haircut)")
    print(line)
    print(f"  NAV             ${pnl.nav:>10,.2f}")
    print(f"  P&L             ${pnl.pnl:>10,.2f}   ({pnl.roi_pct:+.2f}%)")
    print(line)
    print(f"  auctions won/lost : {pnl.won} / {pnl.lost}")
    print(f"  open bids         : {pnl.open_positions}")
    print(f"  inventory held    : {pnl.inventory_positions}")
    print(f"  comps in store    : {comps.count()}  (span {comps.store_span_days():.2f} days)")
    print(f"  cold-start ready  : {comps.store_span_days() >= config.COLD_START_DAYS}")
    print(f"  receipts          : {chain.length}  {dict(sorted(counts.items()))}")
    print(f"  chain verified    : {'OK' if chain.ok else 'FAIL — ' + str(chain.error)}")
    if state.inventory:
        print(line)
        print("  inventory (marked to realized comps):")
        for pos in state.inventory:
            mk = comps.mark(pos["comp_key"], as_of) if pos.get("comp_key") else None
            mval = f"${mk.mark:,.2f}" if mk else "n/a"
            reason = mk.reason if mk else "no_key"
            print(f"    {pos['comp_key'] or '?':28s} cost ${pos['cost_basis']:>8,.2f}  "
                  f"mark {mval:>10s}  [{reason}]")
    print(line)
    comps.close()
    return 0


def cmd_verify(args) -> int:
    """Recompute the hash chain (SPEC verify_chain() CLI hook)."""
    result = verify_chain(args.ledger)
    if result.ok:
        print(f"[verify] OK — {result.length} receipts, chain intact")
        return 0
    print(f"[verify] FAIL at seq {result.error_seq}: {result.error} "
          f"(checked {result.length})")
    return 1


def cmd_seed(args) -> int:
    """Bootstrap the comp store from the checked-in fixture (offline demo)."""
    comps = Comps(args.db)
    n = comps.seed_from_fixture()
    print(f"[seed] inserted {n} comps  (store now {comps.count()}, "
          f"span {comps.store_span_days():.2f}d)")
    comps.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paperswarm.run_desk", description=__doc__)
    p.add_argument("--poll", action="store_true", help="search + build comps + resolve bids")
    p.add_argument("--decide", action="store_true", help="scout -> price -> commit bids (arm B)")
    p.add_argument("--report", action="store_true", help="P&L from ledger + comps")
    p.add_argument("--verify", action="store_true", help="recompute the hash chain")
    p.add_argument("--seed-comps", action="store_true", help="bootstrap comps from fixture")
    p.add_argument("--fixture", action="store_true", help="force FIXTURE mode (no API keys used)")
    p.add_argument("--cold-start-override", action="store_true",
                   help="bypass the >=7d comp-store cold-start gate (testing only)")
    p.add_argument("--as-of", metavar="ISO8601", help="override 'now' (deterministic runs)")
    p.add_argument("--json", action="store_true", help="machine-readable --report output")
    p.add_argument("--db", default=str(config.DB_PATH), help="sqlite comp-store path")
    p.add_argument("--ledger", default=str(config.LEDGER_PATH), help="ledger JSONL path")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ran = False
    rc = 0
    if args.seed_comps:
        rc |= cmd_seed(args); ran = True
    if args.poll:
        rc |= cmd_poll(args); ran = True
    if args.decide:
        rc |= cmd_decide(args); ran = True
    if args.report:
        rc |= cmd_report(args); ran = True
    if args.verify:
        rc |= cmd_verify(args); ran = True
    if not ran:
        build_parser().print_help()
        return 0
    return rc


if __name__ == "__main__":
    sys.exit(main())

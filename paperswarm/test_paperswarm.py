"""PAPERSWARM Phase-1 tests. All green offline (FIXTURE mode, no API keys).

Every test pins a rule from SPEC.md "The honesty protocol". If one of these
fails, a published number is no longer trustworthy — that is the point.

Run:  pytest paperswarm/test_paperswarm.py -q   (from repo root)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from paperswarm import config
from paperswarm.comps import Comps, net_of_friction, percentile
from paperswarm.feed import EbayFeed, Listing
from paperswarm.fills import BidRejected, FillEngine, compute_pnl, reconstruct
from paperswarm.identity import parse_identity
from paperswarm.ledger import Ledger, verify_chain
from paperswarm.outcomes import OutcomeTracker
from paperswarm.swarm import Desk, Pricer

UTC = timezone.utc
T_DECIDE = datetime(2026, 7, 16, 19, 0, tzinfo=UTC)   # before every fixture close
T_POLL = datetime(2026, 7, 16, 23, 59, tzinfo=UTC)    # after every fixture close


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def _auction(listing_id="v1|test|0", title="Charizard PSA 10 #11",
             close=datetime(2026, 7, 16, 20, 0, tzinfo=UTC)) -> Listing:
    return Listing(listing_id, title, 100.0, "AUCTION", close, "seller", {})


def _seeded_comps() -> Comps:
    comps = Comps(":memory:")
    comps.seed_from_fixture()
    return comps


def _engine(tmp_path, comps=None):
    led = Ledger(tmp_path / "ledger.jsonl")
    return FillEngine(led, comps or Comps(":memory:")), led


# ---------------------------------------------------------------------------
# ledger: hash-chain tamper detection (SPEC: "hash-chained ledger from day one")
# ---------------------------------------------------------------------------
def test_chain_verifies_when_intact(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.bid_commit({"listing_id": "a", "max_bid": 10})
    led.fill({"listing_id": "a", "outcome": "lost"})
    led.spend({"amount": 0.01, "reason": "ebay_search"})
    res = verify_chain(tmp_path / "l.jsonl")
    assert res.ok and res.length == 3


def test_chain_detects_content_tamper(tmp_path):
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.bid_commit({"listing_id": "a", "max_bid": 10})
    led.bid_commit({"listing_id": "b", "max_bid": 20})
    # Tamper: rewrite record 0's data but keep its stored hash -> hash mismatch.
    lines = path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["data"]["max_bid"] = 9999
    lines[0] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    res = verify_chain(path)
    assert not res.ok and res.error_seq == 0 and "hash mismatch" in res.error


def test_chain_detects_prev_hash_break(tmp_path):
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.bid_commit({"listing_id": "a", "max_bid": 10})
    led.bid_commit({"listing_id": "b", "max_bid": 20})
    led.bid_commit({"listing_id": "c", "max_bid": 30})
    # Delete the middle record -> record 2's prev_hash no longer chains.
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n" + lines[2] + "\n")
    res = verify_chain(path)
    assert not res.ok


# ---------------------------------------------------------------------------
# BUY: 60s cutoff (SPEC: "commit a max bid >=60s before auction close")
# ---------------------------------------------------------------------------
def test_bid_after_cutoff_rejected(tmp_path):
    engine, _ = _engine(tmp_path)
    close = datetime(2026, 7, 16, 20, 0, tzinfo=UTC)
    listing = _auction(close=close)
    # 30s before close -> inside the 60s cutoff -> reject.
    commit_time = datetime(2026, 7, 16, 19, 59, 30, tzinfo=UTC)
    with pytest.raises(BidRejected) as exc:
        engine.commit_bid(listing, 100.0, comp_key="k", commit_time=commit_time)
    assert exc.value.reason == "bid_after_cutoff"


def test_bid_exactly_at_cutoff_accepted(tmp_path):
    engine, _ = _engine(tmp_path)
    close = datetime(2026, 7, 16, 20, 0, tzinfo=UTC)
    listing = _auction(close=close)
    commit_time = datetime(2026, 7, 16, 19, 59, 0, tzinfo=UTC)  # exactly 60s
    rec = engine.commit_bid(listing, 100.0, comp_key="k", commit_time=commit_time)
    assert rec.data["seconds_before_close"] == 60.0


def test_bin_listing_rejected(tmp_path):
    engine, _ = _engine(tmp_path)
    bin_listing = Listing("v1|x|0", "Charizard PSA 10 #11", 100.0,
                          "FIXED_PRICE", None, "s", {})
    with pytest.raises(BidRejected) as exc:
        engine.commit_bid(bin_listing, 50.0, comp_key="k", commit_time=T_DECIDE)
    assert exc.value.reason == "not_auction"


# ---------------------------------------------------------------------------
# BUY: win/loss + fill price (SPEC: "won at hammer + one increment")
# ---------------------------------------------------------------------------
def test_hammer_at_or_above_max_is_loss(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 105.0, comp_key="k", commit_time=T_DECIDE)
    engine.resolve(listing.listing_id, hammer=142.0, resolve_time=T_POLL)
    st = engine.state()
    assert st.won == 0 and st.lost == 1
    assert st.cash == config.BANKROLL_USD and st.locked == 0.0  # capital freed, unspent


def test_win_price_is_hammer_plus_one_increment(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 105.0, comp_key="k", commit_time=T_DECIDE)
    rec = engine.resolve(listing.listing_id, hammer=92.0, resolve_time=T_POLL)
    # 92 is in the $25-$100 band -> $1.00 increment.
    assert rec.data["outcome"] == "won"
    assert rec.data["increment"] == 1.00
    assert rec.data["win_price"] == 93.00


def test_win_price_capped_at_max_bid(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 100.0, comp_key="k", commit_time=T_DECIDE)
    # hammer 99.90 + $1 increment = 100.90, but capped at committed max 100.
    rec = engine.resolve(listing.listing_id, hammer=99.90, resolve_time=T_POLL)
    assert rec.data["win_price"] == 100.00


def test_unsold_is_loss(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 105.0, comp_key="k", commit_time=T_DECIDE)
    rec = engine.resolve(listing.listing_id, hammer=None,
                         resolve_time=T_POLL, status="UNSOLD")
    assert rec.data["outcome"] == "lost"


# ---------------------------------------------------------------------------
# bankroll locking (SPEC: "capital locked from bid commit to resolution")
# ---------------------------------------------------------------------------
def test_capital_locks_on_commit_and_frees_on_resolution(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 105.0, comp_key="k", commit_time=T_DECIDE)
    st = engine.state()
    assert st.locked == 105.0 and st.available == config.BANKROLL_USD - 105.0
    engine.resolve(listing.listing_id, hammer=92.0, resolve_time=T_POLL)
    st2 = engine.state()
    assert st2.locked == 0.0
    assert st2.cash == pytest.approx(config.BANKROLL_USD - 93.0)  # paid win_price


def test_one_bid_per_listing(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    engine.commit_bid(listing, 50.0, comp_key="k", commit_time=T_DECIDE)
    with pytest.raises(BidRejected) as exc:
        engine.commit_bid(listing, 60.0, comp_key="k", commit_time=T_DECIDE)
    assert exc.value.reason == "duplicate_listing"


def test_exposure_cap_enforced(tmp_path):
    engine, _ = _engine(tmp_path)
    listing = _auction()
    cap = config.MAX_EXPOSURE_FRACTION * config.BANKROLL_USD  # 500
    with pytest.raises(BidRejected) as exc:
        engine.commit_bid(listing, cap + 1, comp_key="k", commit_time=T_DECIDE)
    assert exc.value.reason == "exposure_cap"


def test_insufficient_capital_rejected(tmp_path):
    engine, _ = _engine(tmp_path)
    # Fill bankroll with locks near the cap, then exhaust available capital.
    for i in range(4):  # 4 * 500 = 2000 locked -> available 0
        listing = _auction(listing_id=f"v1|{i}|0")
        engine.commit_bid(listing, 500.0, comp_key="k", commit_time=T_DECIDE)
    extra = _auction(listing_id="v1|extra|0")
    with pytest.raises(BidRejected) as exc:
        engine.commit_bid(extra, 1.0, comp_key="k", commit_time=T_DECIDE)
    # 4 open locks already hits MAX_CONCURRENT_LOCKS (8)? No -> capital first.
    assert exc.value.reason in ("insufficient_capital", "too_many_locks")


# ---------------------------------------------------------------------------
# SELL: friction + thin-comp zero-mark + percentile (SPEC SELL rule)
# ---------------------------------------------------------------------------
def test_friction_arithmetic_exact():
    # 13.25% fee + 3% payment + $5 shipping on a $100 sale.
    assert net_of_friction(100.0) == pytest.approx(100.0 * (1 - 0.1625) - 5.0)
    assert net_of_friction(100.0) == pytest.approx(78.75)


def test_percentile_linear():
    xs = [139, 145, 148, 149, 151, 155, 158, 162]
    # rank = 0.25*(8-1) = 1.75 -> between 145 and 148.
    assert percentile(xs, 25) == pytest.approx(145 + 0.75 * (148 - 145))


def test_thin_comps_mark_zero():
    comps = Comps(":memory:")
    # Only 3 realized comps (< MIN_COMPS_FOR_MARK=5) -> mark ZERO.
    for i, price in enumerate([100.0, 110.0, 105.0]):
        comps.record(card_name="pikachu", number="58", grade="10", cert=None,
                     listing_id=f"t{i}", status="SOLD", sold_price=price,
                     sold_time="2026-07-15T00:00:00Z")
    res = comps.mark("pikachu|58|10", T_POLL)
    assert res.mark == 0.0 and res.reason == "thin_comps_zero" and res.n_comps == 3


def test_mark_with_enough_comps_nets_friction_and_haircut():
    comps = _seeded_comps()
    res = comps.mark("charizard|11|10", datetime(2026, 7, 16, 12, 0, tzinfo=UTC))
    # 8 sold + 2 unsold seeds -> sell_through 0.8; positive, below raw p25.
    assert res.reason == "marked" and res.n_comps == 8
    assert res.sell_through == pytest.approx(0.8)
    expected = net_of_friction(res.p25_price) * 0.8
    assert res.mark == pytest.approx(round(expected, 4))
    assert res.mark < res.p25_price  # friction + haircut always reduce


# ---------------------------------------------------------------------------
# cold-start (SPEC Phase 1: refuse bids until comp store spans >=7 days)
# ---------------------------------------------------------------------------
def test_cold_start_refuses_bids_and_notes_it(tmp_path):
    comps = Comps(":memory:")  # empty store, span 0d
    feed = EbayFeed(fixture=True)
    engine, led = _engine(tmp_path, comps)
    desk = Desk(feed, comps, engine)
    assert desk.cold_started() is False
    decisions = desk.decide(T_DECIDE)
    assert len(decisions) == 1 and decisions[0].action == "skip"
    assert "cold_start" in decisions[0].reason
    # A refusal receipt must exist for the audit trail.
    assert any(r.type == "note" and r.data.get("kind") == "cold_start_refusal"
               for r in led.records())


def test_cold_start_clears_after_seed(tmp_path):
    comps = _seeded_comps()  # spans ~13 days
    feed = EbayFeed(fixture=True)
    engine, _ = _engine(tmp_path, comps)
    desk = Desk(feed, comps, engine)
    assert desk.cold_started() is True


# ---------------------------------------------------------------------------
# Pricer (SPEC: fair value = median trailing comps; max bid = fv * margin)
# ---------------------------------------------------------------------------
def test_pricer_fair_value_and_max_bid():
    comps = _seeded_comps()
    pricer = Pricer(comps)
    q = pricer.price("charizard|11|10", datetime(2026, 7, 16, 12, 0, tzinfo=UTC))
    assert q is not None and q.n_comps == 8
    assert q.fair_value == pytest.approx(150.0)  # median of 8 seed prices
    assert q.max_bid == pytest.approx(round(150.0 * config.DEFAULT_PRICER.margin_requirement, 2))


def test_pricer_none_when_thin():
    comps = _seeded_comps()
    pricer = Pricer(comps)
    assert pricer.price("umbreon vmax|215|10",
                        datetime(2026, 7, 16, 12, 0, tzinfo=UTC)) is None  # 2 comps


# ---------------------------------------------------------------------------
# identity (SPEC: PERFECT IDENTITY — cert-anchored)
# ---------------------------------------------------------------------------
def test_identity_from_title():
    idn = parse_identity("2016 Pokemon XY Evolutions Charizard PSA 10 GEM MINT #11 Holo")
    assert idn.card_name == "charizard" and idn.number == "11" and idn.grade == "10"
    assert idn.comp_key == "charizard|11|10"


def test_identity_cert_from_aspects():
    idn = parse_identity("some noisy title", {
        "Certification Number": "77012345", "Grade": "10",
        "Card Name": "Charizard", "Card Number": "11",
    })
    assert idn.cert == "77012345" and idn.confidence == "cert"


def test_llm_stub_raises():
    from paperswarm.identity import llm_identity_stub
    with pytest.raises(NotImplementedError):
        llm_identity_stub("x")


# ---------------------------------------------------------------------------
# metered compute charged to P&L (SPEC: "energy is not free")
# ---------------------------------------------------------------------------
def test_metered_compute_reduces_cash(tmp_path):
    engine, led = _engine(tmp_path)
    feed = EbayFeed(meter=engine.meter, fixture=True)
    feed.search()  # one metered call
    st = reconstruct(led)
    assert st.compute_cost == pytest.approx(config.API_CALL_COST_USD)
    assert st.cash == pytest.approx(config.BANKROLL_USD - config.API_CALL_COST_USD)


# ---------------------------------------------------------------------------
# fixture end-to-end: poll -> decide -> poll -> report (SPEC Phase 1)
# ---------------------------------------------------------------------------
def test_end_to_end_fixture(tmp_path):
    comps = _seeded_comps()
    led = Ledger(tmp_path / "ledger.jsonl")
    engine = FillEngine(led, comps)
    feed = EbayFeed(meter=engine.meter, fixture=True)
    tracker = OutcomeTracker(feed, comps)
    desk = Desk(feed, comps, engine)

    # 1) DECIDE before closes: commits bids on the two well-comped auctions.
    decisions = desk.decide(T_DECIDE)
    bids = [d for d in decisions if d.action == "bid"]
    assert len(bids) == 2  # charizard#11 and blastoise#2

    # 2) POLL after closes: build comps + resolve our open bids.
    listings = feed.search()
    tracker.sweep(listings, T_POLL)
    for commit in list(engine.state().open_bids.values()):
        from paperswarm.run_desk import _listing_from_commit
        listing = _listing_from_commit(commit)
        outcome = tracker.observe(listing, T_POLL)
        if outcome.is_terminal:
            engine.resolve(commit["listing_id"], outcome.hammer,
                           resolve_time=T_POLL, status=outcome.status)

    st = engine.state()
    assert st.won == 1 and st.lost == 1  # charizard won @93 < max; blastoise lost

    # 3) REPORT: P&L regenerates purely from ledger + comps; chain intact.
    pnl = compute_pnl(led, comps, T_POLL)
    assert pnl.inventory_positions == 1 and pnl.inventory_mark > 0
    assert pnl.compute_cost > 0
    assert verify_chain(tmp_path / "ledger.jsonl").ok


def test_cli_smoke(tmp_path):
    """The CLI wiring runs end-to-end in FIXTURE mode."""
    from paperswarm.run_desk import main
    db = str(tmp_path / "p.db")
    lg = str(tmp_path / "l.jsonl")
    common = ["--fixture", "--db", db, "--ledger", lg]
    assert main(["--seed-comps"] + common) == 0
    assert main(["--decide", "--as-of", "2026-07-16T19:00:00Z"] + common) == 0
    assert main(["--poll", "--as-of", "2026-07-16T23:59:00Z"] + common) == 0
    assert main(["--report", "--as-of", "2026-07-16T23:59:00Z", "--json"] + common) == 0
    assert main(["--verify"] + common) == 0

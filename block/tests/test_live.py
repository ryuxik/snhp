"""Live twin-street driver (block/live.py) tests: per-day determinism, the
ledger conservation law on live records, JSONL telemetry round-trip + resume,
snapshot shape stability, season rollover, and the feature-flagged arena
mount (flag off = no routes). All fast (-m "not slow" friendly): the small
cases run two-venue worlds; conservation runs the full ten-venue street for
two days."""
from __future__ import annotations

import json

import pytest

from block.ledger import BlockLedger
from block.live import (DAY_SCHEMA, SNAP_SCHEMA, LiveBlock, _strip_det,
                        read_log, replay_day, strip_ts)
from block.runner import ALL_VENUES, WORLDS
from block.venues import BlockConfig

SEED = 20260710
TWO = ("vending", "bodega")
CFG2 = BlockConfig(regulars=5, bodega_adopts=True)


def _driver(**kw):
    kw.setdefault("seed", SEED)
    kw.setdefault("venues", TWO)
    kw.setdefault("cfg", CFG2)
    return LiveBlock(**kw)


# ── determinism: same seed + day index → identical day-record ─────────────

def test_same_seed_same_day_identical_record():
    a, b = _driver(), _driver()
    ra = [a.step_day() for _ in range(2)]
    rb = [b.step_day() for _ in range(2)]
    assert ra == rb
    assert ra[0] != ra[1]                      # days genuinely differ
    for r in ra:
        assert r["schema"] == DAY_SCHEMA and r["seed"] == SEED


def test_replay_day_reproduces_stepped_record():
    """Any day is reproducible FROM SCRATCH on the ECONOMIC fields: replay_day
    re-simulates the season and lands on the identical deterministic record.
    The attestation's signature is key-dependent, so it is compared separately —
    it must independently VERIFY under the process key, not be byte-equal to a
    record that may have been signed by a different key."""
    from core.notary import load_notary_key, verify_receipt
    d = _driver()
    recs = [d.step_day() for _ in range(3)]
    again = replay_day(0, 2, seed=SEED, venues=TWO, cfg=CFG2)
    # deterministic economic fields are byte-identical (attestation excluded)
    assert _strip_det(again) == _strip_det(recs[2])
    # the replayed attestation verifies on its own under the process key
    res = verify_receipt(again["attestation"],
                         pubkey_pem=load_notary_key().pubkey_pem)
    assert res["ok"]


# ── conservation: the ledger law holds on live-driver records ─────────────

def test_ledger_conservation_on_live_records():
    """Full ten-venue street: the record's conservation check passes, and an
    INDEPENDENT recheck (ledger event-side aggregates vs each venue's own
    till, the test_block law) agrees — money is never created or destroyed
    by the live driver's day-stepping."""
    lb = LiveBlock(seed=SEED, venues=ALL_VENUES)   # production config
    for day in range(2):
        rec = lb.step_day()
        assert rec["conservation"]["ok"] is True
        assert rec["conservation"]["max_abs_err"] < 1e-9
        for w in WORLDS:
            for v in ALL_VENUES:
                ledger_rev = lb.ledger.day_metrics(w, v, day)["revenue"]
                till = lb.states[w].venues[v].revenue_by_day.get(day, 0.0)
                assert abs(ledger_rev - till) < 1e-9
        # the block delta decomposes exactly over the venues (rounded 2dp)
        assert rec["block"]["d_margin"] == round(
            sum(rec["venues"][v]["d_margin"] for v in ALL_VENUES), 2)
        # paired population: identical arrivals on both worlds — exact here
        # because days 0-1 precede the first week boundary; from day 7 on,
        # fashion waiter RETURNS diverge per-world by design (runner docstring)
        assert (rec["traffic"]["sticker"]["arrivals"]
                == rec["traffic"]["snhp"]["arrivals"])


def test_events_pruned_but_aggregates_kept():
    """The unbounded-run memory guard: raw events are cleared after each day
    while the per-day aggregates the records read stay queryable."""
    d = _driver()
    d.step_day()
    assert d.ledger.events == []
    assert d.ledger.day_metrics("snhp", "vending", 0)["deals"] > 0


# ── JSONL telemetry: round-trip + deterministic resume ────────────────────

def test_jsonl_log_roundtrip_and_resume(tmp_path):
    log = str(tmp_path / "block-live.jsonl")
    d1 = _driver(log_path=log)
    recs = [d1.step_day() for _ in range(3)]

    logged = read_log(log)
    assert len(logged) == 3
    for got, want in zip(logged, recs):
        assert "ts" in got                     # write-time stamp
        assert strip_ts(got) == want           # …and ONLY that differs

    # resume: a fresh driver re-simulates the season against the log,
    # verifies it, and continues exactly where the last process stopped
    d2 = _driver(log_path=log)
    info = d2.resume()
    assert info["mode"] == "resumed" and info["verified_days"] == 3
    assert d2.season == 0 and d2.day == 3
    assert d2.totals["days"] == 3
    assert [strip_ts(r) for r in read_log(log)] == list(d2.window)
    r3 = d2.step_day()
    assert r3["day"] == 3
    assert len(read_log(log)) == 4
    # the continued day matches an uninterrupted run byte-for-byte
    assert r3 == d1.step_day()


def test_resume_mismatch_starts_fresh_season(tmp_path):
    """If the log no longer reproduces (code changed / tampered), resume must
    NOT splice histories: it starts a fresh season and leaves the logged
    records immutable."""
    log = str(tmp_path / "block-live.jsonl")
    d1 = _driver(log_path=log)
    d1.step_day()
    recs = read_log(log)
    recs[0]["block"]["d_margin"] += 1.0        # tamper
    with open(log, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    d2 = _driver(log_path=log)
    info = d2.resume()
    assert info["mode"] == "fresh-season" and d2.season == 1 and d2.day == 0


def test_read_log_skips_corrupt_lines(tmp_path):
    log = str(tmp_path / "block-live.jsonl")
    d = _driver(log_path=log)
    rec = d.step_day()
    with open(log, "a") as f:
        f.write('{"half a rec')                # crash mid-write
    got = read_log(log)
    assert len(got) == 1 and strip_ts(got[0]) == rec


# ── snapshot shape (the /block/live.json + WS-connect contract) ───────────

def test_snapshot_shape_stable():
    d = _driver(secs_per_day=120.0)
    d.step_day()
    snap = d.public
    assert set(snap) == {"schema", "live", "seed", "season", "day",
                         "season_days", "venues", "engine", "config",
                         "totals", "last_records", "notary", "resume",
                         "reproduce", "secs_per_day"}
    assert set(snap["notary"]) == {"chain_head", "pubkey_pem", "pubkey_fpr",
                                   "key_source", "algo", "note"}
    assert snap["schema"] == SNAP_SCHEMA and snap["live"] is True
    assert snap["day"] == 1 and snap["season"] == 0
    assert set(snap["engine"]) == {"block_version", "driver_version", "git"}
    for scope in ("lifetime", "season"):
        tot = snap["totals"][scope]
        assert set(tot) == {"days", "d_margin", "d_cs", "margin", "arrivals",
                            "walkaways", "waste", "per_venue"}
        assert set(tot["per_venue"]) == set(TWO)
    rec = snap["last_records"][-1]
    assert set(rec) == {"schema", "seed", "season", "season_seed",
                        "season_days", "day", "engine", "block", "venues",
                        "traffic", "waste", "conservation", "attestation"}
    # snapshot totals are folds of the day-records — nothing invented
    assert snap["totals"]["lifetime"]["d_cs"] == rec["block"]["d_cs"]
    json.dumps(snap)                           # JSON-serializable end to end


def test_season_rollover_reseeds():
    d = _driver(season_days=2)
    r0, r1, r2 = d.step_day(), d.step_day(), d.step_day()
    assert (r0["season"], r0["day"]) == (0, 0)
    assert (r1["season"], r1["day"]) == (0, 1)
    assert (r2["season"], r2["day"]) == (1, 0)     # rolled + reset
    assert r2["season_seed"] == SEED + 1           # deterministic reseed
    assert d.totals["days"] == 3                   # lifetime keeps counting
    assert d.season_totals["days"] == 1            # season restarted
    # season 1 day 0 is reproducible from scratch too
    assert replay_day(1, 0, seed=SEED, venues=TWO, cfg=CFG2,
                      season_days=2) == r2


# ── the arena mount is feature-flagged: default OFF = no routes ───────────

def _reload_api(monkeypatch, flag: bool, tmp_path):
    monkeypatch.setenv("ARENA_NO_RUN", "1")
    if flag:
        monkeypatch.setenv("BLOCK_LIVE", "1")
        monkeypatch.setenv("BLOCK_LIVE_LOG", str(tmp_path / "live.jsonl"))
        monkeypatch.setenv("BLOCK_LIVE_SECS_PER_DAY", "120")
    else:
        monkeypatch.delenv("BLOCK_LIVE", raising=False)
    import importlib
    import arena.api as api
    return importlib.reload(api)


def test_flag_off_mounts_no_block_routes(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    api = _reload_api(monkeypatch, flag=False, tmp_path=tmp_path)
    assert not any(getattr(r, "path", "") == "/block/live.json"
                   for r in api.app.routes)
    with TestClient(api.app) as client:
        # the static mount answers with the trailer page, never the stream
        assert "live" not in client.get("/health").json().get("service", "")
        r = client.get("/block/live.json")
        assert r.status_code == 404 or "schema" not in r.text


def test_flag_on_serves_snapshot_and_ws(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    api = _reload_api(monkeypatch, flag=True, tmp_path=tmp_path)
    with TestClient(api.app) as client:
        snap = client.get("/block/live.json").json()
        assert snap["schema"] == SNAP_SCHEMA
        assert snap["seed"] == SEED and snap["live"] is True
        assert set(snap["venues"]) == set(ALL_VENUES)
        with client.websocket_connect("/block/live") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "block.snapshot"
            assert hello["schema"] == SNAP_SCHEMA
        # existing endpoints untouched
        assert client.get("/health").json()["ok"] is True
    # leave a clean module for any later reload-based test
    _reload_api(monkeypatch, flag=False, tmp_path=tmp_path)

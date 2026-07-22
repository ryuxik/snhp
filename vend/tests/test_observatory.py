"""THE STORE — observatory generator tests.

Covers: every telemetry record kind in one synthetic JSONL, a seeded demand DB
(GT_KEYS_DB env isolation like test_demand.py), golden-SHAPE assertions on the
json artifact, the R-gate PROXY math hand-verified against fixtures, money
exactness, and determinism (two runs → identical json bytes).

Isolation note: the demand rows are seeded into a DEDICATED sqlite file (not the
shared GT_KEYS_DB), so exact-count assertions here can never be contaminated by
another test module that also seeds the demand table. The GT_KEYS_DB/telemetry
env is still isolated at import (the test_demand.py pattern) so no real DB is
touched.

House rule mirrored here: the assertions are mechanical — hand-computed counts,
not "looks right".
"""
import json
import os
import tempfile
from datetime import datetime, timezone

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_obs_keys.db"))
os.environ.setdefault("NEXTMOVE_TELEMETRY_PATH",
                      os.path.join(_tmp, "obs_telemetry.jsonl"))

from vend import demand, observatory  # noqa: E402

# A dedicated demand DB for these tests — isolated from any shared GT_KEYS_DB.
_DEMAND_DB = os.path.join(_tmp, "obs_demand_only.db")


def _ts(y, mo, d, h=12):
    return datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp()


# Two UTC days, 48h apart — the R1 return fixture.
_D1 = _ts(2026, 1, 1)
_D3 = _ts(2026, 1, 3)


def _line(**rec):
    return json.dumps(rec, sort_keys=True)


def _write_fixture(path):
    """One JSONL with EVERY record kind and a hand-designed wallet population.

    Wallets:
      aaa — starter draw (D1) then funded draw (D3, different slot) → R0, R1, R2
      bbb — starter-only settled → paying, NOT self-funded, NOT R0
      ccc — funded-only settled (no starter draw) → self-funded, NOT R0, NOT R1
      ddd — uncharged only (3 reasons) → distinct wallet, NOT paying
      anon (repeat_key=None) — funded settled, EXCLUDED from every wallet gate
    """
    def sc(**kw):
        base = {"kind": "slot_call", "door": "http", "content_hash": "h",
                "predicate": "fetch.v1", "shortfall_millicents": 0}
        base.update(kw)
        return _line(**base)

    def settled(rk, slot, backend, price, wholesale, est, starter, funded, ts,
                shortfall=0):
        return sc(repeat_key=rk, slot_id=slot, backend_id=backend, settled=True,
                  ok=True, price_millicents=price, wholesale_millicents=wholesale,
                  wholesale_estimated=est,
                  funding={"starter_millicents": starter,
                           "funded_millicents": funded},
                  shortfall_millicents=shortfall, reason=None, ts=ts)

    def uncharged(rk, slot, backend, reason, ts):
        return sc(repeat_key=rk, slot_id=slot, backend_id=backend, settled=False,
                  ok=False, price_millicents=0, wholesale_millicents=0,
                  wholesale_estimated=False, funding=None, reason=reason, ts=ts)

    lines = [
        # aaa — R0/R1/R2
        settled("aaa", "fetch", "jina", 100, 100, False, 100, 0, _D1),
        settled("aaa", "search", "serper", 200, 200, True, 0, 200, _D3),
        # bbb — starter only
        settled("bbb", "fetch", "jina", 50, 50, False, 50, 0, _D1),
        # ccc — funded only, with a store-eaten shortfall
        settled("ccc", "fetch", "firecrawl", 80, 80, True, 0, 80, _D1, shortfall=5),
        # anon settled — excluded from wallet gates
        settled(None, "fetch", "jina", 10, 10, False, 0, 10, _D1),
        # ddd — three uncharged reason codes
        uncharged("ddd", "fetch", None, "all_backends_failed", _D1),
        uncharged("ddd", "fetch", "jina", "empty markdown", _D1),
        uncharged("ddd", "fetch", None, "insufficient_balance", _D1),
        # every other record kind
        _line(kind="throttle", ts=_D1, scope="math_per_ip", had_key=False,
              path="/v1/math", repeat_key=None),
        _line(kind="throttle", ts=_D1, scope="math_per_key", had_key=True,
              path="/v1/math", repeat_key="aaa"),
        _line(kind="free_taste", ts=_D1, door="http", repeat_key="ccc"),
        _line(kind="free_taste", ts=_D1, door="http", repeat_key=None),
        _line(kind="catalog_request", ts=_D1, door="http", repeat_key=None,
              request="raw ask", truncated=False),
        _line(kind="session_open", ts=_D1, door="http", repeat_key="aaa",
              session_id="s1", category="salary", side="buy", stake=1.0,
              price_cents=200),
        _line(kind="advice", ts=_D1, door="http", repeat_key="aaa",
              category="salary", side="buy", move="counter", offer=1.0,
              context_hash="c", policy_id="p", seed=0, price_cents=200,
              compute={}),
        "{ this is a malformed line",   # skip-count fixture
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _seed_demand():
    """Seed the DEDICATED demand DB (temporarily repoint GT_KEYS_DB so
    demand.file_request lands there, then restore — full isolation from the
    shared test DB). Two distinct wallets file the same normalized geocoding ask
    (→ R3 qualifying); a keyless filing of the same ask raises the tally but not
    the distinct-wallet count; a lone translate ask does not qualify."""
    old = os.environ.get("GT_KEYS_DB")
    os.environ["GT_KEYS_DB"] = _DEMAND_DB
    try:
        demand.file_request("please stock geocoding", api_key="key1", door="mcp")
        demand.file_request("  PLEASE  Stock GEOCODING ", api_key="key2", door="http")
        demand.file_request("please stock geocoding", api_key=None, door="mcp")
        demand.file_request("translate french", api_key="key1", door="mcp")
    finally:
        if old is None:
            os.environ.pop("GT_KEYS_DB", None)
        else:
            os.environ["GT_KEYS_DB"] = old


# Seed ONCE at import → a stable 4-row demand DB for every test below.
_seed_demand()


def _snapshot(tmpdir):
    tel = os.path.join(tmpdir, "tel.jsonl")
    out = os.path.join(tmpdir, "obs")
    _write_fixture(tel)
    return observatory.snapshot(telemetry_path=tel, out_dir=out,
                                demand_db=_DEMAND_DB)


# ─── golden shape ────────────────────────────────────────────────────────────


def test_snapshot_golden_shape_and_totals():
    d = _snapshot(tempfile.mkdtemp())
    assert d["schema"] == "observatory.v1"
    for key in ("source", "totals", "shortfall", "wallets", "funnel",
                "throttle", "slots", "demand", "rgates"):
        assert key in d, key
    src = d["source"]
    assert src["telemetry_records"] == 15        # 16 lines, 1 malformed skipped
    assert src["malformed_lines_skipped"] == 1
    assert src["records_by_kind"]["slot_call"] == 8
    assert src["records_by_kind"]["throttle"] == 2
    t = d["totals"]
    assert t["slot_calls"] == 8
    assert t["settled_calls"] == 5
    assert t["uncharged_calls"] == 3
    # money: exact integers + exact USD strings
    assert t["price_total"]["millicents"] == 440        # 100+200+50+80+10
    assert t["price_total"]["usd"] == "$0.00440"
    assert t["wholesale_total"]["millicents"] == 440


def test_shortfall_and_estimated_split():
    d = _snapshot(tempfile.mkdtemp())
    assert d["shortfall"]["total"]["millicents"] == 5
    assert d["shortfall"]["calls_with_shortfall"] == 1
    fetch = d["slots"]["fetch"]
    # fetch settled: aaa1(exact), bbb(exact), ccc(est), anon(exact) → 3 exact/1 est
    assert fetch["wholesale_split"]["exact_calls"] == 3
    assert fetch["wholesale_split"]["estimated_calls"] == 1
    assert fetch["settled_calls"] == 4
    assert fetch["uncharged_calls"] == 3
    assert fetch["backend_serves"] == {"jina": 3, "firecrawl": 1}  # aaa1,bbb,anon
    assert fetch["uncharged_by_reason"] == {
        "all_backends_failed": 1, "empty markdown": 1, "insufficient_balance": 1}
    search = d["slots"]["search"]
    assert search["settled_calls"] == 1
    assert search["spend"]["price_total"]["millicents"] == 200


def test_wallets_funnel_throttle():
    d = _snapshot(tempfile.mkdtemp())
    w = d["wallets"]
    assert w["distinct_wallets"] == 4        # aaa,bbb,ccc,ddd (anon excluded)
    assert w["paying_wallets"] == 3          # aaa,bbb,ccc
    assert w["per_door"]["http"] == 4
    fu = d["funnel"]
    assert fu["free_taste_calls"] == 2
    assert fu["keyed_free_wallets"] == 1     # only ccc keyed (other is anon)
    assert fu["keyed_free_to_paid_overlap"] == 1   # ccc is a paying wallet
    th = d["throttle"]
    assert th["events"] == 2
    assert th["by_scope"] == {"math_per_ip": 1, "math_per_key": 1}


# ─── R-gate proxy math (hand-verified) ───────────────────────────────────────


def test_rgate_counts_against_fixture():
    d = _snapshot(tempfile.mkdtemp())
    rg = d["rgates"]
    assert rg["self_funded_wallets"] == 2    # aaa, ccc
    assert rg["R0"]["count"] == 1            # aaa only (ccc never drew starter)
    assert rg["R1"]["count"] == 1            # aaa (2 UTC days, 48h)
    assert rg["R2"]["count"] == 1            # aaa (fetch + search)
    assert rg["R3"]["count"] == 1            # geocoding, 2 distinct wallets
    assert rg["R0"]["proposed_threshold"] == 10
    assert rg["R1"]["proposed_threshold"] == 5
    assert rg["R3"]["proposed_threshold"] == 3
    assert rg["R0"]["clock_started"] is False
    assert rg["R2"]["kill_relevant"] is False     # observational per P6
    assert rg["R0"]["kill_relevant"] is True
    for g in ("R0", "R1", "R2", "R3"):
        assert rg[g]["proxy_label"] and rg[g]["proxy_limits"]
    asks = rg["R3_asks"]
    assert len(asks) == 1
    assert asks[0]["distinct_wallets"] == 2
    assert asks[0]["filings"] == 3           # keyless filing raises filings, not wallets


def test_r0_requires_starter_before_funded():
    # funded came AFTER starter → R0
    calls = [
        {"repeat_key": "x", "ts": _D3, "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
        {"repeat_key": "x", "ts": _D1, "slot_id": "fetch",
         "funding": {"starter_millicents": 5, "funded_millicents": 0}},
    ]
    prof = observatory._funding_profile(calls)
    assert observatory._r0_wallets(prof) == {"x"}
    # funded BEFORE starter → NOT R0 (the "subsequently" clause)
    calls_rev = [
        {"repeat_key": "y", "ts": _D1, "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
        {"repeat_key": "y", "ts": _D3, "slot_id": "fetch",
         "funding": {"starter_millicents": 5, "funded_millicents": 0}},
    ]
    prof_rev = observatory._funding_profile(calls_rev)
    assert observatory._r0_wallets(prof_rev) == set()


def test_r1_needs_two_days_and_24h_span():
    # same UTC day, hours apart → NOT R1
    same_day = [
        {"repeat_key": "z", "ts": _ts(2026, 5, 1, 1), "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
        {"repeat_key": "z", "ts": _ts(2026, 5, 1, 23), "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
    ]
    prof = observatory._funding_profile(same_day)
    assert observatory._r1_wallets(prof, observatory._self_funded(prof)) == set()
    # two distinct days but only 2h apart (23:00→01:00) → NOT R1 (span < 24h)
    boundary = [
        {"repeat_key": "z", "ts": _ts(2026, 5, 1, 23), "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
        {"repeat_key": "z", "ts": _ts(2026, 5, 2, 1), "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
    ]
    prof_b = observatory._funding_profile(boundary)
    assert observatory._r1_wallets(prof_b, observatory._self_funded(prof_b)) == set()
    # two days AND 48h apart → R1
    ok = [
        {"repeat_key": "z", "ts": _D1, "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
        {"repeat_key": "z", "ts": _D3, "slot_id": "fetch",
         "funding": {"starter_millicents": 0, "funded_millicents": 5}},
    ]
    prof_ok = observatory._funding_profile(ok)
    assert observatory._r1_wallets(prof_ok, observatory._self_funded(prof_ok)) == {"z"}


def test_r3_exact_match_and_keyless_excluded():
    reqs = [
        {"text": "geocode this", "repeat_key": "k1"},
        {"text": "  GEOCODE   this ", "repeat_key": "k2"},   # ws/case variant
        {"text": "geocode this", "repeat_key": None},        # keyless: no wallet
        {"text": "geocode this", "repeat_key": "k1"},        # same wallet again
        {"text": "translate this", "repeat_key": "k1"},      # lone → not R3
    ]
    asks = observatory._r3_asks(reqs)
    assert len(asks) == 1
    assert asks[0]["distinct_wallets"] == 2      # k1, k2 (None excluded, dup k1 once)
    assert asks[0]["filings"] == 4


# ─── demand tally ────────────────────────────────────────────────────────────


def test_demand_tally_mechanical():
    d = _snapshot(tempfile.mkdtemp())
    dm = d["demand"]
    assert dm["available"] is True
    assert dm["total"] == 4                  # 3 geocoding + 1 translate
    assert dm["distinct"] == 2
    geo = [g for g in dm["top"] if "geocoding" in g["text"].lower()]
    assert geo and geo[0]["count"] == 3
    assert dm["by_status"] == {"logged": 4}


def test_demand_unavailable_degrades_gracefully():
    tmp = tempfile.mkdtemp()
    tel = os.path.join(tmp, "tel.jsonl")
    _write_fixture(tel)
    d = observatory.snapshot(
        telemetry_path=tel, out_dir=os.path.join(tmp, "obs"),
        demand_db=os.path.join(tmp, "nope.db"))     # nonexistent DB
    assert d["demand"]["available"] is False
    assert d["rgates"]["R3"]["count"] == 0   # no demand → R3 = 0, not a crash


# ─── artifacts + determinism ─────────────────────────────────────────────────


def test_artifacts_written_and_md_labels_proxies():
    d = _snapshot(tempfile.mkdtemp())
    assert os.path.exists(d["_artifacts"]["json"])
    assert os.path.exists(d["_artifacts"]["md"])
    md = open(d["_artifacts"]["md"]).read()
    assert "R-gate progress (P6 — PROXIES)" in md
    assert "clock has NOT started" in md
    assert "UTC-day proxy" in md             # proxy labels travel into the .md
    assert "true R0 is" in md
    assert "geocoding" in md.lower()         # untrusted text rendered (as DATA)


def test_deterministic_bytes():
    # Same telemetry input (path embedded in the artifact), two output dirs → the
    # json bytes must be identical (deterministic given the same inputs).
    tel = os.path.join(tempfile.mkdtemp(), "tel.jsonl")
    _write_fixture(tel)
    a = observatory.snapshot(telemetry_path=tel, demand_db=_DEMAND_DB,
                             out_dir=os.path.join(tempfile.mkdtemp(), "obs"))
    b = observatory.snapshot(telemetry_path=tel, demand_db=_DEMAND_DB,
                             out_dir=os.path.join(tempfile.mkdtemp(), "obs"))
    assert open(a["_artifacts"]["json"]).read() == open(b["_artifacts"]["json"]).read()

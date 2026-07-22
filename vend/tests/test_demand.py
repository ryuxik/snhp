"""THE STORE — the demand loop's spine (GAUNTLET #5).

The null-query log used to be a write-only void: `logged: true` and nothing to
return for. These tests pin the increment that fixes it — a request id, a GET
status, and a MECHANICAL public tally (exact-match duplicate counts, no fuzzy
classification, no LLM). Plus the two hygiene rules: keyless filing stays
allowed, and a presented key is stored ONLY as its keyed pseudonym, never raw.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_demand.db"))
os.environ.setdefault("NEXTMOVE_TELEMETRY_PATH",
                      os.path.join(_tmp, "telemetry.jsonl"))

from vend import demand, telemetry  # noqa: E402


# ─── id + status: the void gets a spine ──────────────────────────────────────


def test_file_request_returns_id_and_status():
    rec = demand.file_request("i wish you stocked geocoding",
                              api_key=None, door="mcp")
    assert rec["request_id"].startswith("rq_")
    assert rec["status"] == "logged"
    got = demand.get_request(rec["request_id"])
    assert got["status"] == "logged" and got["door"] == "mcp"
    assert "geocoding" in got["text"]
    assert got["status_note"] is None and got["status_ts"] is None


def test_get_unknown_request_is_none():
    assert demand.get_request("rq_does_not_exist") is None


def test_get_request_reports_same_ask_count_exact_match():
    # GAUNTLET #6 increment: get_request carries same_ask_count — the exact-match
    # dup count for THIS request's normalized text (whitespace/case folded).
    r1 = demand.file_request("please stock geocoding", api_key=None, door="mcp")
    assert demand.get_request(r1["request_id"])["same_ask_count"] == 1
    # a case/whitespace variant collapses to the same normalized ask → 2
    demand.file_request("  PLEASE   Stock GEOCODING ", api_key=None, door="http")
    assert demand.get_request(r1["request_id"])["same_ask_count"] == 2
    # a genuinely distinct ask does NOT inflate the count (no fuzzy match)
    r3 = demand.file_request("please stock translation", api_key=None, door="mcp")
    assert demand.get_request(r3["request_id"])["same_ask_count"] == 1


# ─── hygiene: keyless OK, raw key never stored ───────────────────────────────


def test_keyless_filing_allowed_and_public_view_hides_repeat_key():
    rec = demand.file_request("keyless ask", api_key=None, door="http")
    got = demand.get_request(rec["request_id"])
    assert got is not None                       # keyless filing works
    assert "repeat_key" not in got               # never on the public surface


def test_raw_key_never_stored_only_pseudonym():
    raw = "gt_demand_secret_token"
    rec = demand.file_request("please stock translation", api_key=raw, door="mcp")
    with demand._conn() as c:
        row = c.execute(
            "SELECT repeat_key FROM requests WHERE request_id = ?",
            (rec["request_id"],)).fetchone()
    assert row[0] == telemetry._repeat_key(raw)  # the keyed pseudonym
    assert row[0] != raw
    # raw-first telemetry line was ALSO written, and it too holds no raw key
    with open(os.environ["NEXTMOVE_TELEMETRY_PATH"]) as f:
        assert raw not in f.read()


def test_text_capped_at_2000_chars():
    rec = demand.file_request("x" * 5000, api_key=None, door="mcp")
    with demand._conn() as c:
        row = c.execute("SELECT text FROM requests WHERE request_id = ?",
                        (rec["request_id"],)).fetchone()
    assert len(row[0]) == 2000                   # capped at ingestion


# ─── tally: mechanical exact-match duplicate counts ──────────────────────────


def test_tally_exact_match_dedup_no_fuzzy():
    demand.file_request("Widget Alpha extraction", api_key=None, door="mcp")
    demand.file_request("  widget   alpha   EXTRACTION ",       # ws/case variant
                        api_key=None, door="http")
    demand.file_request("widget beta extraction",              # distinct request
                        api_key=None, door="mcp")
    t = demand.tally()
    assert t["total"] >= 3
    alpha = [r for r in t["requests"] if "widget alpha" in r["text"].lower()]
    assert alpha and alpha[0]["count"] == 2      # the two variants collapse to one
    beta = [r for r in t["requests"] if "widget beta" in r["text"].lower()]
    assert beta and beta[0]["count"] == 1        # NOT folded into alpha (no fuzzy)


def test_tally_recent_capped_and_public():
    demand.file_request("recent probe", api_key="gt_probe_key", door="mcp")
    t = demand.tally()
    assert len(t["recent"]) <= 50
    assert all(set(r) == {"request_id", "filed_at", "door", "text", "status"}
               for r in t["recent"])
    # no repeat_key / raw key leaks onto the public tally
    import json
    assert "repeat_key" not in json.dumps(t)
    assert "gt_probe_key" not in json.dumps(t)


# ─── founder-only status (Python helper, no HTTP surface) ────────────────────


def test_founder_set_status_updates_and_persists():
    rec = demand.file_request("stock a pdf slot", api_key=None, door="mcp")
    updated = demand.founder_set_status(rec["request_id"], "stocked", "shipped v2")
    assert updated["status"] == "stocked"
    assert updated["status_note"] == "shipped v2"
    assert updated["status_ts"] is not None
    got = demand.get_request(rec["request_id"])          # persisted
    assert got["status"] == "stocked" and got["status_note"] == "shipped v2"


def test_founder_set_status_unknown_id_returns_none():
    assert demand.founder_set_status("rq_missing", "stocked", "x") is None


# ─── attribution: my_requests + watch (roadmap: voter → reachable customer) ───


def test_my_requests_returns_only_the_callers_filings():
    a = "gt_attrib_alice_key"
    b = "gt_attrib_bob_key"
    ra = demand.file_request("alice wants a geocode slot", api_key=a, door="mcp")
    demand.file_request("alice wants a translate slot", api_key=a, door="http")
    rb = demand.file_request("bob wants a pdf slot", api_key=b, door="mcp")

    mine = demand.my_requests(a)
    ids = {r["request_id"] for r in mine}
    assert ra["request_id"] in ids                 # alice sees her own
    assert rb["request_id"] not in ids             # never bob's
    # bob sees only his one filing, not alice's two
    assert {r["request_id"] for r in demand.my_requests(b)} == {rb["request_id"]}
    # newest-first ordering (the translate ask was filed after the geocode ask)
    assert mine[0]["filed_at"] >= mine[-1]["filed_at"]


def test_my_requests_entry_shape_and_same_ask_count():
    k = "gt_attrib_shape_key"
    r = demand.file_request("shape probe unique ask", api_key=k, door="mcp",
                            watch=True)
    entry = next(e for e in demand.my_requests(k)
                 if e["request_id"] == r["request_id"])
    assert set(entry) == {"request_id", "filed_at", "text", "status",
                          "status_note", "status_ts", "watch", "same_ask_count"}
    assert entry["status"] == "logged"
    assert entry["status_note"] is None and entry["status_ts"] is None
    assert entry["watch"] is True
    assert entry["same_ask_count"] == 1
    # a keyless case/whitespace variant collapses to the same normalized ask,
    # so the mechanical count rises for the caller's row too (no fuzzy match)
    demand.file_request("  SHAPE   Probe   UNIQUE ask ", api_key=None, door="http")
    again = next(e for e in demand.my_requests(k)
                 if e["request_id"] == r["request_id"])
    assert again["same_ask_count"] == 2


def test_watch_recorded_only_with_a_key():
    # WITH a key: watch=True is recorded (echoed back + visible in my_requests)
    k = "gt_watch_withkey"
    rk = demand.file_request("watched ask with key", api_key=k, door="mcp",
                             watch=True)
    assert rk["watch"] is True
    assert demand.my_requests(k)[0]["watch"] is True
    with demand._conn() as c:
        row = c.execute("SELECT watch FROM requests WHERE request_id = ?",
                        (rk["request_id"],)).fetchone()
    assert row[0] == 1                              # persisted as the flag

    # ANONYMOUS: a watch with no key is meaningless and silently dropped (0)
    ra = demand.file_request("watched ask no key", api_key=None, door="http",
                             watch=True)
    assert ra["watch"] is False                     # echo reflects the drop
    with demand._conn() as c:
        row = c.execute("SELECT watch FROM requests WHERE request_id = ?",
                        (ra["request_id"],)).fetchone()
    assert row[0] == 0                              # never recorded anonymously

    # default is no-watch
    rn = demand.file_request("unwatched ask", api_key=k, door="mcp")
    assert rn["watch"] is False


def test_my_requests_raw_key_never_in_db_or_on_surface():
    import json
    raw = "gt_attrib_secret_never_stored"
    demand.file_request("attrib secret ask", api_key=raw, door="mcp", watch=True)
    # the row is matched by the keyed pseudonym, and the raw key is NOT in the
    # table anywhere (the invariant stands even for attribution + watch)
    with demand._conn() as c:
        rows = c.execute(
            "SELECT repeat_key, text FROM requests WHERE repeat_key = ?",
            (telemetry._repeat_key(raw),)).fetchall()
        assert rows and all(rk != raw for (rk, _t) in rows)
        # a full-table scan finds the raw key in no column
        allrows = c.execute("SELECT * FROM requests").fetchall()
    assert raw not in json.dumps(allrows, default=str)
    # and it never reaches the caller-facing surface either
    surface = json.dumps(demand.my_requests(raw))
    assert raw not in surface and "repeat_key" not in surface


def test_my_requests_keyless_returns_empty():
    assert demand.my_requests(None) == []
    assert demand.my_requests("") == []

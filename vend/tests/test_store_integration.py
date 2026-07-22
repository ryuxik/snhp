"""THE STORE — end-to-end over both doors (MCP + HTTP).

What's under test is the SEAM: door → shelf wiring → settlement engine →
wallet → telemetry sink → receipt. Backends are faked (no network); the HTTP
parsing of the real backends is test_fetch_backends.py's job. The invariants
asserted here (STORE.md §2d.5, §6):

  - a fresh key holds the 50¢ starter credit (granted at issuance) and settles
    its first fetch out of it, over either door, with a funding-split receipt
  - a predicate failure is an uncharged 200-shaped outcome AND still writes a
    telemetry line (non-delivery is telemetry)
  - insufficient balance → 402, an unknown key → 401 (advice-route convention)
  - the catalog leaks no key material over either door
  - the telemetry line carries the pseudonymous repeat_key, never the raw key
"""
import json
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB",
                      os.path.join(_tmp, "test_store_integration.db"))

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server import mcp_server, middleware as _mw, onboarding  # noqa: E402
from gametheory.server.http import app  # noqa: E402
from gametheory.server.onboarding import (  # noqa: E402
    STARTER_GRANT_MILLICENTS, issue_key, wallet_available, wallet_credit,
)
from vend import shelf, store, telemetry  # noqa: E402
from vend.store import BackendError, BackendResult  # noqa: E402

client = TestClient(app)


# ─── fakes + helpers ─────────────────────────────────────────────────────────


class FakeBackend:
    """Deterministic stand-in — always available (so the slot's availability
    gate passes and admission/settlement is what's exercised). `secret` proves
    the catalog/receipt never surface backend key material."""

    def __init__(self, *, bid="fake", fail=False, markdown="# hi\n\nbody",
                 wholesale=1_000):
        self.id = bid
        self.secret = "sk_live_never_leaks"
        self._fail = fail
        self._markdown = markdown
        self._wholesale = wholesale

    def available(self):
        return True

    def call(self, request):
        if self._fail:
            raise BackendError(f"{self.id} down")
        return BackendResult(
            payload={"markdown": self._markdown, "url": request["url"],
                     "final_url": None, "title": None},
            wholesale_millicents=self._wholesale, wholesale_estimated=False,
            backend_id=self.id, meta={"status": 200})


def _key(cents=0):
    k = issue_key(agent_id=f"store-int-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="store integration tests")["api_key"]
    if cents:
        wallet_credit(k, cents * 1000, bucket="funded")
    return k


def _slot_calls(path):
    with open(path) as f:
        return [json.loads(ln) for ln in f
                if json.loads(ln).get("kind") == "slot_call"]


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    _mw._BUCKETS.clear()


@pytest.fixture(autouse=True)
def _no_cwd_telemetry(tmp_path, monkeypatch):
    """Every store call writes a slot_call telemetry line via the real sink; pin
    its path to a per-test temp file so tests that don't take the `telemetry_file`
    fixture never litter the repo root with the default cwd nextmove_telemetry.jsonl.
    Same tmp_path as `telemetry_file`, so the two agree when both apply."""
    monkeypatch.setenv("NEXTMOVE_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))


@pytest.fixture
def fake_fetch():
    """Wire the shelf, then swap the fetch slot's backends for a controllable
    fake; restore afterwards. The id-keyed ensure_shelf() the doors call keeps
    the swap intact for the duration of the request.

    The vendor-backed fetch slot is FENCED OFF the launch shelf (shelf.
    FETCH_SLOT_ENABLED False — vendor-ToS resale, insource candidate), so these
    tests register the slot machinery themselves to exercise the settlement
    engine. This proves the slot works when we re-enable it via an in-house
    backend; it does NOT stock the vendor slot in prod."""
    shelf.ensure_shelf()
    if "fetch" not in store.SLOTS:
        store.register_slot(shelf.build_fetch_slot())
    slot = store.SLOTS["fetch"]
    saved_backends, saved_cap = slot.backends, slot.max_price_millicents

    def _set(*backends, max_price=None):
        slot.backends = list(backends)
        if max_price is not None:
            slot.max_price_millicents = max_price
        return slot

    yield _set
    slot.backends, slot.max_price_millicents = saved_backends, saved_cap


@pytest.fixture
def telemetry_file(tmp_path, monkeypatch):
    p = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("NEXTMOVE_TELEMETRY_PATH", str(p))
    return p


# ─── settlement over each door ───────────────────────────────────────────────


def test_http_fresh_key_fetch_settles_from_starter(fake_fetch, telemetry_file):
    fake_fetch(FakeBackend(bid="fake-a", wholesale=1_000))
    key = _key()                       # fresh: no own money; starter at issuance
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "https://example.com/a"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["payload"]["markdown"].startswith("# hi")
    rec = out["receipt"]
    assert rec["backend_id"] == "fake-a"
    assert rec["price_millicents"] == 1_000 == rec["wholesale_millicents"]
    assert rec["funding"] == {"starter_millicents": 1_000,
                              "funded_millicents": 0}   # paid from the grant
    assert rec["balance_after"]["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 1_000
    assert rec["content_hash"]
    # exactly the wholesale left the wallet; the starter grant funded it
    assert wallet_available(key)["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 1_000

    calls = _slot_calls(telemetry_file)
    assert len(calls) == 1
    line = calls[0]
    assert line["door"] == "http" and line["settled"] is True
    assert line["price_millicents"] == 1_000
    assert line["repeat_key"] == telemetry._repeat_key(key)
    # the keyed request hash is on the line; the raw url NEVER touches the file
    # (no browsable fetch history), but the exact url re-hashes to a match
    assert line["request_hash"] == store._request_hash(
        {"url": "https://example.com/a"})
    disk = telemetry_file.read_text()
    assert key not in disk                            # raw key never on disk
    assert "https://example.com/a" not in disk        # raw url never on disk


def test_mcp_fresh_key_fetch_settles_from_starter(fake_fetch, telemetry_file):
    fake_fetch(FakeBackend(bid="fake-b", wholesale=750))
    key = _key()
    out = mcp_server.store_fetch(api_key=key, url="https://example.com/b")
    assert out["ok"] is True
    assert out["receipt"]["funding"]["starter_millicents"] == 750
    assert out["receipt"]["backend_id"] == "fake-b"
    assert wallet_available(key)["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 750

    calls = _slot_calls(telemetry_file)
    assert len(calls) == 1 and calls[0]["door"] == "mcp"
    assert calls[0]["repeat_key"] == telemetry._repeat_key(key)
    assert key not in telemetry_file.read_text()


def test_funded_wallet_split_after_starter_drains(fake_fetch, telemetry_file):
    # drain the starter to a sliver, keep real funds above the admission cap,
    # then fetch for more than the sliver: the receipt must show the split.
    fake_fetch(FakeBackend(bid="fake-c", wholesale=1_000))
    key = _key(cents=2)                                # funded 2_000
    onboarding.wallet_debit(key, STARTER_GRANT_MILLICENTS - 400)   # 400 left
    out = mcp_server.store_fetch(api_key=key, url="https://example.com/c")
    assert out["ok"] is True
    f = out["receipt"]["funding"]
    assert f["starter_millicents"] == 400            # the sliver, first
    assert f["funded_millicents"] == 600             # rest from own money
    assert f["starter_millicents"] + f["funded_millicents"] == 1_000


# ─── uncharged outcomes are 200-shaped and still telemetry ───────────────────


def test_predicate_fail_uncharged_and_logged(fake_fetch, telemetry_file):
    fake_fetch(FakeBackend(bid="fake-d", markdown="   "))   # blank → predicate fails
    key = _key()
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "https://example.com/d"})
    assert r.status_code == 200, r.text               # NOT an HTTP error
    out = r.json()
    assert out["ok"] is False and out["charged"] is False and out["reason"]
    # NOTHING was spent — the whole starter grant is still there
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS

    calls = _slot_calls(telemetry_file)
    assert len(calls) == 1
    assert calls[0]["settled"] is False               # non-delivery still logs
    assert calls[0]["repeat_key"] == telemetry._repeat_key(key)


def test_all_backends_fail_uncharged(fake_fetch, telemetry_file):
    fake_fetch(FakeBackend(bid="b1", fail=True), FakeBackend(bid="b2", fail=True))
    key = _key()
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "https://example.com/e"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False and out["error"] == "all_backends_failed"
    assert out["charged"] is False
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_httpexception_from_backend_cascades_not_500(fake_fetch, telemetry_file,
                                                     monkeypatch):
    # FIX 3a end-to-end: a REAL backend hitting an http.client.HTTPException
    # (IncompleteRead here — neither OSError nor URLError) must NOT 500. It
    # normalizes to a BackendError and CASCADES to the next backend, and the call
    # still writes exactly one telemetry line. Uses the real backends (not the
    # FakeBackend) so their transport catch is what's exercised.
    import http.client
    import vend.fetch_backends as fb
    monkeypatch.setenv("JINA_API_KEY", "k")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    fake_fetch(fb.JinaReaderBackend(), fb.FirecrawlBackend())   # restored on teardown
    fc_body = json.dumps({"success": True,
                          "data": {"markdown": "# ok\n\nbody", "metadata": {}}})

    def transport(**kw):
        if kw["method"] == "GET":              # Jina → an HTTPException-family error
            raise http.client.IncompleteRead(b"partial")
        return fb._HttpResponse(status=200, headers={}, text=fc_body)  # Firecrawl serves

    monkeypatch.setattr(fb, "_http_request", transport)
    key = _key()
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "https://example.com/z"})
    assert r.status_code == 200, r.text        # NOT a 500 — HTTPException was normalized
    out = r.json()
    assert out["ok"] is True
    assert out["receipt"]["backend_id"] == "firecrawl"   # cascaded past Jina's HTTPException
    calls = _slot_calls(telemetry_file)
    assert len(calls) == 1 and calls[0]["settled"] is True   # exactly one line


# ─── the money edges: 402 broke, 401 unknown ─────────────────────────────────


def test_insufficient_balance_402(fake_fetch):
    fake_fetch(FakeBackend(bid="fake-f", wholesale=1_000))
    key = _key()                                      # known key
    onboarding.wallet_debit(key, STARTER_GRANT_MILLICENTS)   # empty the wallet
    assert wallet_available(key)["total_millicents"] == 0
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "https://example.com/f"})
    assert r.status_code == 402, r.text


def test_unknown_key_401(fake_fetch):
    fake_fetch(FakeBackend(bid="fake-g", wholesale=1_000))
    r = client.post("/v1/fetch", json={"api_key": "gt_never_issued_key",
                                       "url": "https://example.com/g"})
    assert r.status_code == 401, r.text


def test_malformed_url_is_a_client_error_not_a_settlement(monkeypatch,
                                                          telemetry_file):
    # real backends validate the url before any network call (bad scheme → no
    # network at all); a 400 over HTTP and an error dict over MCP — never a
    # charged outcome. Env keys only make the real backends "available" so the
    # call reaches their pre-network validation.
    monkeypatch.setenv("JINA_API_KEY", "k")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    shelf.ensure_shelf()
    key = _key(cents=5)                               # funded past admission
    r = client.post("/v1/fetch", json={"api_key": key,
                                       "url": "ftp://example.com/x"})
    assert r.status_code == 400, r.text
    out = mcp_server.store_fetch(api_key=key, url="ftp://example.com/x")
    assert out["ok"] is False and out["charged"] is False
    assert wallet_available(key)["funded_millicents"] == 5_000   # nothing spent
    # FIX 3b: the client-error path still writes ONE telemetry line PER call — a
    # malformed request is no longer a silent hole in the telemetry contract.
    calls = _slot_calls(telemetry_file)
    assert len(calls) == 2                            # one HTTP + one MCP call
    assert all(c["settled"] is False and c["reason"] == "invalid_request"
               for c in calls)


# ─── the catalog leaks nothing, over either door ─────────────────────────────


def test_catalog_no_key_material_both_doors(monkeypatch):
    # real backends + configured vendor keys → tier "production"; the env key
    # values are the thing we are paranoid about surfacing.
    monkeypatch.setenv("JINA_API_KEY", "jina-secret-sentinel-xyz")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-secret-sentinel-xyz")
    shelf.ensure_shelf()

    http_cat = client.get("/v1/store/catalog")
    assert http_cat.status_code == 200, http_cat.text
    mcp_cat = mcp_server.store_catalog()

    for cat in (http_cat.json(), mcp_cat):
        assert cat["unit"] == "millicents"
        assert cat["millicents_per_cent"] == 1000
        assert cat["counter_fee_pct"] == 5
        assert cat["starter_credit"]["millicents"] == STARTER_GRANT_MILLICENTS
        blob = json.dumps(cat)
        assert "jina-secret-sentinel-xyz" not in blob
        assert "firecrawl-secret-sentinel-xyz" not in blob
        slots = {s["id"]: s for s in cat["slots"]}
        fetch = slots["fetch"]
        assert fetch["backends"] == ["jina-reader", "firecrawl"]   # ids only
        assert fetch["tier"] == "production"
        assert fetch["max_price_millicents"] == 2_000
        assert fetch["predicate_id"] == "fetch.v2"    # block-page screen (GAUNTLET #6)
        # request_doc names api_key now (GAUNTLET #7: it was omitted)
        assert "api_key" in fetch["request_doc"]
        # the catalog documents the never-strand admission + acceptable use
        assert "millicent" in cat["admission"]
        assert "http(s)" in cat["acceptable_use"]
        # the anchor SKUs ride along at tier "anchor"
        anchors = {s["id"] for s in cat["slots"] if s.get("tier") == "anchor"}
        assert anchors == {"negotiate.session", "negotiate.bundle"}


def test_store_request_logs_over_both_doors(telemetry_file):
    key = _key()
    # store_request now hands back a request_id + status (GAUNTLET #5), and STILL
    # writes the raw-first telemetry line (file_request calls log_request too).
    mcp_out = mcp_server.store_request("i wish you stocked geocoding", api_key=key)
    assert mcp_out["request_id"].startswith("rq_")
    assert mcp_out["status"] == "logged"
    assert mcp_out["check"] == f"GET /v1/store/request/{mcp_out['request_id']}"
    # /v1/advice/request is the same intake under its legacy name: the old
    # {logged, truncated} shape survives as a subset, plus the spine's id.
    http_out = client.post("/v1/advice/request",
                           json={"text": "and pdf table extraction",
                                 "api_key": key})
    assert http_out.status_code == 200 and http_out.json()["logged"] is True
    assert http_out.json()["request_id"].startswith("rq_")
    assert http_out.json()["status"] == "logged"
    kinds = [json.loads(ln)["kind"] for ln in
             telemetry_file.read_text().splitlines()]
    assert kinds.count("catalog_request") == 2      # both doors wrote raw-first
    assert key not in telemetry_file.read_text()


# ─── the demand loop has a spine now (GAUNTLET #5) ───────────────────────────


def test_store_request_status_and_tally_over_http(telemetry_file):
    key = _key()
    # file two requests, one a case/whitespace variant of the other → they
    # collide under the exact-match normalizer (mechanical, no fuzzy).
    r1 = client.post("/v1/store/request",
                     json={"text": "geocode a street address", "api_key": key})
    assert r1.status_code == 200
    rid = r1.json()["request_id"]
    assert rid.startswith("rq_") and r1.json()["status"] == "logged"
    client.post("/v1/store/request",
                json={"text": "  GEOCODE   a Street Address "})   # keyless variant

    # GET the status of the first request
    st = client.get(f"/v1/store/request/{rid}")
    assert st.status_code == 200
    body = st.json()
    assert body["request_id"] == rid and body["status"] == "logged"
    assert body["status_note"] is None and body["door"] == "http"

    # unknown id → 404
    assert client.get("/v1/store/request/rq_nope").status_code == 404

    # the public tally counts the two variants as ONE distinct request, count 2
    tal = client.get("/v1/store/requests")
    assert tal.status_code == 200
    t = tal.json()
    assert t["total"] >= 2
    geo = [r for r in t["requests"] if "geocode" in r["text"].lower()]
    assert geo and geo[0]["count"] >= 2
    # no raw key ever reaches the public surface
    assert key not in json.dumps(t)


def test_founder_set_status_visible_but_not_over_http(telemetry_file):
    from vend import demand
    key = _key()
    rid = client.post("/v1/store/request",
                      json={"text": "stock a translation slot",
                            "api_key": key}).json()["request_id"]
    # the founder-only Python helper sets status + note; there is NO route for it
    updated = demand.founder_set_status(rid, "stocked", "shipped in the xlate slot")
    assert updated["status"] == "stocked"
    seen = client.get(f"/v1/store/request/{rid}").json()
    assert seen["status"] == "stocked"
    assert seen["status_note"] == "shipped in the xlate slot"
    assert seen["status_ts"] is not None
    # no HTTP verb mutates status: there is no PUT/POST on the item route
    assert client.post(f"/v1/store/request/{rid}",
                       json={"status": "x"}).status_code in (404, 405)


def test_notary_pubkey_route_matches_catalog_and_a_live_receipt(fake_fetch):
    # auditor: the receipt-signing pubkey is served at a stable path to pin
    # out-of-band. It must equal the catalog's published signer AND the
    # fingerprint on an actual fetch receipt.
    from vend.receipt_signing import verify_receipt
    fake_fetch(FakeBackend(bid="pin-be", wholesale=700))
    key = _key()
    rec = client.post("/v1/fetch", json={"api_key": key,
                                         "url": "https://example.com/pin"}).json()["receipt"]

    pk = client.get("/v1/store/notary_pubkey")
    assert pk.status_code == 200, pk.text
    body = pk.json()
    assert set(body) == {"pubkey_pem", "fingerprint", "key_source"}
    assert "BEGIN PUBLIC KEY" in body["pubkey_pem"]
    assert "PRIVATE" not in body["pubkey_pem"]            # never private material
    assert body["key_source"] in ("env", "ephemeral")
    # the pin the catalog points at resolves to this same signer
    sig = client.get("/v1/store/catalog").json()["receipts"]["signature"]
    assert body["fingerprint"] == sig["pubkey_fingerprint"]
    # and it verifies the live receipt (the third-party path, pubkey pinned here)
    assert rec["pubkey_fingerprint"] == body["fingerprint"]
    assert verify_receipt(rec, pubkey_pem=body["pubkey_pem"]) is True


def test_balance_usd_display_is_exact(fake_fetch):
    # rerun P3/P5: the balance's usd_display is EXACT (5-decimal), with the old
    # 2-decimal figure surviving only as an explicitly-labelled rounded sibling.
    fake_fetch(FakeBackend(bid="bal-be", wholesale=1_333))
    key = _key()
    client.post("/v1/fetch", json={"api_key": key,
                                   "url": "https://example.com/bal"})
    b = client.get("/v1/billing/balance", headers={"X-API-Key": key})
    assert b.status_code == 200, b.text
    body = b.json()
    left = STARTER_GRANT_MILLICENTS - 1_333              # 48_667 millicents
    assert body["total_millicents"] == left
    assert body["usd_display"] == f"${left // 100000}.{left % 100000:05d}"
    assert body["usd_display"] == "$0.48667"             # exact, not $0.49
    assert body["usd_display_rounded"] == "$0.49"        # rounded, and LABELLED so


# ─── runway: balance guaranteed_calls_remaining floor (roadmap) ──────────────


def test_balance_guaranteed_calls_remaining_is_conservative_floor(fake_fetch):
    # roadmap: fund before the 402. The balance carries a CONSERVATIVE floor per
    # registered commodity slot: total // max_price_millicents (the published
    # ceiling), so the real number (wholesale passthrough ≤ ceiling) is ≥ this.
    fake_fetch(FakeBackend(bid="floor-be"))              # fetch slot available
    key = _key()                                         # starter 50_000, no fetch yet
    b = client.get("/v1/billing/balance", headers={"X-API-Key": key})
    assert b.status_code == 200, b.text
    body = b.json()
    total = body["total_millicents"]
    assert total == STARTER_GRANT_MILLICENTS
    cap = store.SLOTS["fetch"].max_price_millicents      # 2000, the published ceiling
    g = body["guaranteed_calls_remaining"]
    assert g["fetch"] == total // cap                    # floor, integer division
    assert g["fetch"] == STARTER_GRANT_MILLICENTS // 2_000


def test_balance_guaranteed_calls_unavailable_slot_is_zero(fake_fetch):
    # a slot with no healthy backend guarantees ZERO calls — you can't be promised
    # a call it cannot serve, however much money the wallet holds.
    fake_fetch(FakeBackend(bid="up-be"))                 # a healthy slot for contrast
    sid = f"down-{uuid.uuid4().hex[:6]}"

    class _Down:
        id = "down-be"

        def available(self):
            return False

        def call(self, request):
            raise BackendError("down")

    store.register_slot(store.Slot(
        id=sid, title="down", backends=[_Down()],
        predicate=lambda p: (True, ""), predicate_id="x.v1",
        max_price_millicents=1_000, request_doc="{}"))
    try:
        key = _key(cents=5)                              # a well-funded wallet
        g = client.get("/v1/billing/balance",
                       headers={"X-API-Key": key}).json()["guaranteed_calls_remaining"]
        assert g[sid] == 0                               # unavailable → 0
        assert g["fetch"] > 0                            # the healthy slot still floors > 0
    finally:
        store.SLOTS.pop(sid, None)


# ─── attribution: my_requests over HTTP + MCP (roadmap) ──────────────────────


def test_my_requests_http_header_auth_and_isolation(telemetry_file):
    a = _key()
    b = _key()
    ida = client.post("/v1/store/request",
                      json={"text": "alice http ask", "api_key": a}).json()["request_id"]
    client.post("/v1/store/request", json={"text": "bob http ask", "api_key": b})

    # Authorization: Bearer returns ONLY the caller's own filings
    ra = client.get("/v1/store/my_requests",
                    headers={"Authorization": f"Bearer {a}"})
    assert ra.status_code == 200, ra.text
    mine = ra.json()["requests"]
    assert ida in {r["request_id"] for r in mine}
    assert mine and all("alice" in r["text"] for r in mine)   # never bob's row
    assert a not in ra.text                                    # raw key never echoed

    # X-API-Key header also carries the key
    rb = client.get("/v1/store/my_requests", headers={"X-API-Key": b})
    assert rb.status_code == 200
    assert all("bob" in r["text"] for r in rb.json()["requests"])

    # missing key → 401 (not a 422 validation tax); unknown key → 401
    assert client.get("/v1/store/my_requests").status_code == 401
    assert client.get("/v1/store/my_requests",
                      headers={"X-API-Key": "gt_never_issued_key"}).status_code == 401


def test_store_request_watch_echoed_and_recorded_over_both_doors(telemetry_file):
    key = _key()
    # HTTP: watch=true WITH a key is echoed back
    h = client.post("/v1/store/request",
                    json={"text": "watch me http", "api_key": key, "watch": True})
    assert h.status_code == 200 and h.json()["watch"] is True
    # MCP: same, via the tool's watch kwarg
    m = mcp_server.store_request("watch me mcp", api_key=key, watch=True)
    assert m["watch"] is True
    # both show up watched in the caller's own my_requests (MCP door)
    watched = {r["text"]: r["watch"]
               for r in mcp_server.store_my_requests(key)["requests"]}
    assert watched.get("watch me http") is True
    assert watched.get("watch me mcp") is True
    # an ANONYMOUS (keyless) watch is meaningless → dropped, echo reflects it
    anon = client.post("/v1/store/request",
                       json={"text": "watch me anon", "watch": True})
    assert anon.status_code == 200 and anon.json()["watch"] is False


def test_fetch_accepts_key_via_header(fake_fetch, telemetry_file):
    # the key travels in Authorization: Bearer (reaches W3's keyed lane); the
    # body carries no api_key at all.
    fake_fetch(FakeBackend(bid="hdr", wholesale=800))
    key = _key()
    r = client.post("/v1/fetch", json={"url": "https://example.com/h"},
                    headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["receipt"]["backend_id"] == "hdr"
    assert wallet_available(key)["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 800
    # X-API-Key works too
    r2 = client.post("/v1/fetch", json={"url": "https://example.com/h2"},
                     headers={"X-API-Key": key})
    assert r2.status_code == 200 and r2.json()["ok"] is True
    # no key anywhere → 401 (not a 422 validation tax)
    r3 = client.post("/v1/fetch", json={"url": "https://example.com/h3"})
    assert r3.status_code == 401

"""THE STORE settlement engine — the invariant the whole spec hangs on.

Fake in-test backends stand in for the real fetch backends (another worker's
lane). Under test (STORE.md §2b, §2d.4, §2d.5):
  - a predicate failure NEVER debits; a backend failure NEVER debits
  - failover walks the available backends in order
  - a delivered call settles at wholesale PASSTHROUGH (price == wholesale)
  - the receipt carries every field (funding split + balance_after), and the
    catalog leaks no key material
  - tier is COMPUTED from live backend availability
  - the starter credit (granted at issuance) funds a fresh key's first call
"""
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_store.db"))

from gametheory.server.onboarding import (  # noqa: E402
    STARTER_GRANT_MILLICENTS, issue_key, wallet_available, wallet_credit,
    wallet_debit,
)
from vend import store  # noqa: E402
from vend.store import BackendError, BackendResult, Slot, register_slot  # noqa: E402


# ─── fakes ───────────────────────────────────────────────────────────────────


class FakeBackend:
    """Configurable stand-in. `fail=True` raises BackendError on call;
    otherwise returns the given payload at the given wholesale cost. `secret`
    is deliberately present to prove the catalog never exposes it."""

    def __init__(self, id, *, available=True, fail=False, payload=None,
                 wholesale=1_000, estimated=False):
        self.id = id
        self.secret = "sk_live_should_never_appear"
        self._available = available
        self._fail = fail
        self._payload = payload if payload is not None else {"markdown": "# ok"}
        self._wholesale = wholesale
        self._estimated = estimated
        self.calls = 0

    def available(self):
        return self._available

    def call(self, request):
        self.calls += 1
        if self._fail:
            raise BackendError(f"{self.id} down")
        return BackendResult(
            payload=self._payload, wholesale_millicents=self._wholesale,
            wholesale_estimated=self._estimated, backend_id=self.id,
            meta={"status": 200})


def _markdown_predicate(payload):
    return (bool(payload.get("markdown", "").strip()), "empty_markdown")


def _slot(slot_id, backends, *, max_price=1_000, predicate=None):
    return register_slot(Slot(
        id=slot_id, title=f"slot {slot_id}", backends=backends,
        predicate=predicate or _markdown_predicate, predicate_id="fetch.v1",
        max_price_millicents=max_price, request_doc="{url: str}"))


def _key(cents=0):
    k = issue_key(agent_id=f"store-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="store tests")["api_key"]
    if cents:
        wallet_credit(k, cents * 1000, bucket="funded")
    return k


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(store.SLOTS)
    store.SLOTS.clear()
    store.set_telemetry_sink(store._noop_sink)
    yield
    store.SLOTS.clear()
    store.SLOTS.update(saved)
    store.set_telemetry_sink(store._noop_sink)


# ─── the no-debit invariants ─────────────────────────────────────────────────


def test_predicate_failure_never_debits():
    sid = f"pfail-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", payload={"markdown": "   "})])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is False
    assert out["reason"] == "empty_markdown"
    assert out["charged"] is False
    # NOTHING was spent — the whole starter grant is still there
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_backend_failure_never_debits():
    sid = f"bfail-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", fail=True)
    b2 = FakeBackend("b2", fail=True)
    _slot(sid, [b1, b2])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is False
    assert out["error"] == "all_backends_failed"
    assert out["charged"] is False
    assert b1.calls == 1 and b2.calls == 1
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_unknown_slot_errors_without_charge():
    key = _key()
    out = store.call_slot("no-such-slot", key, {}, "test")
    assert out["ok"] is False and out["error"] == "unknown_slot"


def test_slot_with_no_available_backends_errors():
    sid = f"down-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", available=False)])
    key = _key()
    out = store.call_slot(sid, key, {}, "test")
    assert out["ok"] is False and out["error"] == "slot_unavailable"


def test_zero_balance_refused_backend_never_dialed():
    # Never-strand: ONLY a truly empty wallet (total == 0) is refused, and the
    # refusal still short-circuits before any backend is dialed.
    sid = f"broke-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1")
    _slot(sid, [b1])
    key = _key()
    wallet_debit(key, STARTER_GRANT_MILLICENTS)          # empty it
    assert wallet_available(key)["total_millicents"] == 0
    out = store.call_slot(sid, key, {}, "test")
    assert out["ok"] is False and out["error"] == "insufficient_balance"
    assert out["needed_millicents"] == 1                 # any positive balance admits
    assert out["available_millicents"] == 0
    assert b1.calls == 0                                  # never dialed a backend


def test_never_strand_admits_below_slot_cap():
    # GAUNTLET #7 trapped-tail: the old gate refused a balance below the slot's
    # max_price; now 1936 millicents (below a 2000 cap) buys a full call.
    sid = f"tail-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", wholesale=1_000)
    _slot(sid, [b1], max_price=2_000)                    # cap ABOVE the wallet
    key = _key()
    wallet_debit(key, STARTER_GRANT_MILLICENTS - 1_936)  # leave exactly 1936
    assert wallet_available(key)["total_millicents"] == 1_936
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is True                             # admitted despite < cap
    assert out["receipt"]["price_millicents"] == 1_000
    assert wallet_available(key)["total_millicents"] == 936
    assert b1.calls == 1


def test_last_millicent_buys_a_full_call_store_eats_tail():
    # The tail past the balance is the store's loss (extends the settlement-
    # shortfall asymmetry); once at zero the NEXT admission fails (bounded).
    sid = f"eat-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", wholesale=2_500)              # more than the balance
    _slot(sid, [b1], max_price=3_000)
    key = _key()
    wallet_debit(key, STARTER_GRANT_MILLICENTS - 900)    # leave 900
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is True
    r = out["receipt"]
    assert (r["funding"]["starter_millicents"]
            + r["funding"]["funded_millicents"]) == 900  # spent all it had
    assert r["balance_after"]["total_millicents"] == 0   # store ate the 1600 tail
    assert wallet_available(key)["total_millicents"] == 0
    # accounting (rerun P5): the wallet moved 900, the store absorbed the tail,
    # and the two still sum to the price a caller owed (2500).
    assert r["wallet_delta_millicents"] == 900
    assert r["absorbed_tail_millicents"] == 1_600
    assert r["price_millicents"] == \
        r["wallet_delta_millicents"] + r["absorbed_tail_millicents"] == 2_500
    out2 = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out2["ok"] is False and out2["error"] == "insufficient_balance"
    assert out2["needed_millicents"] == 1
    assert b1.calls == 1                                  # the refused call never dialed


# ─── dead ends name what was tried / what lever remains (GAUNTLET #6) ─────────


def test_all_backends_failed_names_what_was_tried():
    sid = f"tried-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", fail=True), FakeBackend("b2", fail=True)])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["error"] == "all_backends_failed" and out["charged"] is False
    assert [t["id"] for t in out["backends_tried"]] == ["b1", "b2"]
    assert all(t["reason"] for t in out["backends_tried"])   # each names a reason
    assert "retry" in out["retry_hint"].lower()
    # NOTHING was spent
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_predicate_fail_cascades_to_next_backend_and_charges_the_pass():
    # rerun P1: a first backend delivers a blank (predicate FAILS); the cascade
    # tries the SECOND backend before giving up, and the passing backend is the
    # one charged — a blank from A no longer strands while B sat unused.
    sid = f"cascade-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", payload={"markdown": "   "})       # blank → predicate fail
    b2 = FakeBackend("b2", payload={"markdown": "# served"}, wholesale=1_300)
    _slot(sid, [b1, b2])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is True
    assert b1.calls == 1 and b2.calls == 1                    # cascade dialed b2
    r = out["receipt"]
    assert r["backend_id"] == "b2"                            # b2 served & was charged
    assert r["price_millicents"] == 1_300 == r["wholesale_millicents"]
    # exactly one debit, for the passing backend's wholesale
    assert wallet_available(key)["total_millicents"] == \
        STARTER_GRANT_MILLICENTS - 1_300


def test_predicate_fail_fail_uncharged_lists_every_attempt():
    # fail-then-fail: both delivered payloads fail the predicate → uncharged, one
    # normalized envelope naming every attempt {id, reason}, no lever left.
    sid = f"failfail-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", payload={"markdown": "   "})
    b2 = FakeBackend("b2", payload={"markdown": ""})
    _slot(sid, [b1, b2])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is False and out["charged"] is False
    assert out["code"] == "predicate_failed"
    assert out["reason"]                                      # a stable predicate reason
    assert out["backend_id"] == "b2"                          # the last delivering backend
    assert [t["id"] for t in out["backends_tried"]] == ["b1", "b2"]
    assert out["backends_untried"] == []                     # cascade exhausted
    assert b1.calls == 1 and b2.calls == 1
    # NOTHING was spent
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_mixed_transport_then_predicate_fail_uncharged():
    # a transport failure AND a predicate failure both land in backends_tried; the
    # envelope's code reflects that a payload DID deliver (predicate_failed).
    sid = f"mixed-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", fail=True)                         # transport failure
    b2 = FakeBackend("b2", payload={"markdown": "   "})       # predicate failure
    _slot(sid, [b1, b2])
    key = _key()
    out = store.call_slot(sid, key, {"url": "http://x"}, "test")
    assert out["ok"] is False and out["charged"] is False
    assert out["code"] == "predicate_failed"
    reasons = {t["id"]: t["reason"] for t in out["backends_tried"]}
    assert set(reasons) == {"b1", "b2"}
    assert wallet_available(key)["total_millicents"] == STARTER_GRANT_MILLICENTS


def test_catalog_documents_admission_and_acceptable_use():
    _slot("cadm", [FakeBackend("b1")])
    cat = store.catalog()
    assert "millicent" in cat["admission"]
    assert "insufficient_balance" in cat["admission"]
    assert "http(s)" in cat["acceptable_use"]
    assert ("credentialed" in cat["acceptable_use"]
            or "authenticated" in cat["acceptable_use"])


def test_catalog_admission_scopes_tail_to_commodity_and_anchor_full_price():
    # rerun P4 (HIGH): admission must SCOPE eat-the-tail to commodity slots and
    # say anchor SKUs charge full price up front (why: a bounded tail is rounding,
    # an eaten $1.50 of a $2 session is a discount exploit).
    _slot("cscope", [FakeBackend("b1")])
    adm = store.catalog()["admission"].lower()
    assert "commodity" in adm
    assert "anchor" in adm and "full price" in adm
    assert "discount" in adm                              # names the exploit it avoids


def test_catalog_states_no_refund_and_keys_and_starter_usd():
    _slot("cterms", [FakeBackend("b1")])
    cat = store.catalog()
    # no-refund disclosure (auditor)
    assert "non-refundable" in cat["no_refund"].lower()
    assert "cashout" in cat["no_refund"].lower()
    # discoverability: the keys block points at issuance + the starter attaches
    assert cat["keys"]["issue"] == "POST /v1/keys"
    assert "starter" in cat["keys"]["note"].lower()
    # the starter credit now also states its exact USD
    assert cat["starter_credit"]["usd"] == store._exact_usd(
        cat["starter_credit"]["millicents"])


def test_catalog_slot_entry_documents_predicate_boundary():
    # auditor: the fetch slot's entry states what the predicate catches + its
    # honest limit (a thin-but-non-empty error page still bills).
    from vend.shelf import build_fetch_slot
    register_slot(build_fetch_slot())
    fetch = {s["id"]: s for s in store.catalog()["slots"]}["fetch"]
    doc = fetch["predicate_doc"].lower()
    assert "block" in doc and "empty" in doc
    assert "bills" in doc or "bill" in doc                # states the limit
    # a slot with no predicate_doc omits the key entirely (no empty noise)
    _slot("nodoc", [FakeBackend("b1")])
    entry = {s["id"]: s for s in store.catalog()["slots"]}["nodoc"]
    assert "predicate_doc" not in entry


# ─── failover + passthrough settlement ───────────────────────────────────────


def test_failover_order_serves_from_second_backend():
    sid = f"fo-{uuid.uuid4().hex[:6]}"
    b1 = FakeBackend("b1", fail=True)
    b2 = FakeBackend("b2", payload={"markdown": "# served"}, wholesale=1_200)
    _slot(sid, [b1, b2])
    key = _key()
    out = store.call_slot(sid, key, {}, "test")
    assert out["ok"] is True
    assert out["receipt"]["backend_id"] == "b2"
    assert b1.calls == 1 and b2.calls == 1


def test_passthrough_price_equals_wholesale():
    sid = f"pt-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=1_234)], max_price=2_000)
    key = _key()
    before = wallet_available(key)["total_millicents"]   # starter, granted at issuance
    out = store.call_slot(sid, key, {}, "test")
    r = out["receipt"]
    assert r["price_millicents"] == 1_234
    assert r["price_millicents"] == r["wholesale_millicents"]
    # exactly the wholesale amount left the wallet
    after = wallet_available(key)["total_millicents"]
    assert before - after == 1_234
    assert (r["funding"]["starter_millicents"]
            + r["funding"]["funded_millicents"]) == 1_234
    # balance_after mirrors the live wallet
    assert r["balance_after"]["total_millicents"] == after


def test_receipt_fields_complete():
    sid = f"rc-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=900, estimated=True)])
    key = _key()
    out = store.call_slot(sid, key, {}, "test")
    r = out["receipt"]
    for fld in ("slot_id", "backend_id", "price_millicents", "price_usd",
                "wholesale_millicents", "wholesale_estimated",
                "wallet_delta_millicents", "absorbed_tail_millicents",
                "content_hash", "predicate", "funding", "balance_after",
                "runway_estimate_calls", "ts", "upstream_ref"):
        assert fld in r, f"receipt missing {fld}"
    assert r["slot_id"] == sid
    assert r["predicate"] == "fetch.v1"
    assert r["wholesale_estimated"] is True
    assert r["content_hash"] and isinstance(r["content_hash"], str)
    assert set(r["funding"]) == {"starter_millicents", "funded_millicents"}
    assert set(r["balance_after"]) == {
        "starter_millicents", "funded_millicents", "total_millicents"}
    # accounting identity (rerun P5): price == wallet moved + tail eaten
    assert r["price_millicents"] == \
        r["wallet_delta_millicents"] + r["absorbed_tail_millicents"]
    # a normal (non-depletion) call moves the whole price, eats nothing
    assert r["wallet_delta_millicents"] == 900
    assert r["absorbed_tail_millicents"] == 0
    # price_usd is the EXACT dollar string, no rounding: 900 millicents = $0.009
    assert r["price_usd"] == "$0.00900"
    # a fake backend that set no upstream evidence → None (absent case)
    assert r["upstream_ref"] is None


# ─── runway hint: "calls like this one left" (stateless, from THIS receipt) ───


def test_receipt_runway_estimate_calls_is_balance_over_price():
    # roadmap: fund the pipeline before the 402. runway_estimate_calls =
    # balance_after.total // price of THIS call, computed purely from the receipt.
    sid = f"runway-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=1_000)], max_price=2_000)
    key = _key()                                          # starter 50_000
    r = store.call_slot(sid, key, {"url": "http://x"}, "test")["receipt"]
    left = r["balance_after"]["total_millicents"]
    assert left == STARTER_GRANT_MILLICENTS - 1_000
    assert r["runway_estimate_calls"] == left // r["price_millicents"]
    assert r["runway_estimate_calls"] == (STARTER_GRANT_MILLICENTS - 1_000) // 1_000


def test_receipt_runway_estimate_is_integer_floor_not_rounded():
    # a non-divisor price floors (never rounds up): you must be able to AFFORD
    # every call the hint promises.
    sid = f"runfloor-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=49_687)], max_price=50_000)
    key = _key(cents=100)                                 # 100_000 funded + starter
    r = store.call_slot(sid, key, {"url": "http://x"}, "test")["receipt"]
    left = r["balance_after"]["total_millicents"]
    assert r["runway_estimate_calls"] == left // 49_687   # floor
    # and that floor is strictly less than a rounded-up count would be
    assert (r["runway_estimate_calls"] + 1) * 49_687 > left


def test_receipt_runway_is_zero_at_drained_wallet_depletion_edge():
    # price > balance: the store eats the tail, the wallet drains to 0, and the
    # runway hint reads 0 — a pipeline sees "top up now" from the receipt itself,
    # before the NEXT call 402s. Covers the zero-balance / depletion edge.
    sid = f"rundrain-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=2_500)], max_price=3_000)
    key = _key()
    wallet_debit(key, STARTER_GRANT_MILLICENTS - 900)     # leave 900 (< the price)
    r = store.call_slot(sid, key, {"url": "http://x"}, "test")["receipt"]
    assert r["balance_after"]["total_millicents"] == 0    # drained (tail eaten)
    assert r["runway_estimate_calls"] == 0                # 0 // 2500 == 0


def test_receipt_price_usd_is_exact_not_rounded():
    # rerun P3/P5: a sub-cent, non-round price shows EXACTLY, never as "$0.50".
    sid = f"exact-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=49_687)], max_price=50_000)
    key = _key(cents=100)                                 # funded past the price
    out = store.call_slot(sid, key, {}, "test")
    assert out["receipt"]["price_usd"] == "$0.49687"      # 49687 / 100000 exactly


def test_receipt_carries_upstream_ref_when_backend_reports_it():
    # evidence-passthrough (auditor): a backend that sets meta['upstream_ref']
    # gets it lifted verbatim onto the receipt; absent → None (both exercised).
    sid = f"ref-{uuid.uuid4().hex[:6]}"

    class RefBackend(FakeBackend):
        def call(self, request):
            self.calls += 1
            return BackendResult(
                payload={"markdown": "# ok"}, wholesale_millicents=1_000,
                wholesale_estimated=False, backend_id=self.id,
                meta={"status": 200,
                      "upstream_ref": {"x-request-id": "req_abc123",
                                       "usage": {"tokens": 512}}})

    _slot(sid, [RefBackend("b1")])
    key = _key()
    out = store.call_slot(sid, key, {}, "test")
    assert out["receipt"]["upstream_ref"] == {
        "x-request-id": "req_abc123", "usage": {"tokens": 512}}


def test_starter_funds_a_fresh_keys_first_call():
    sid = f"auto-{uuid.uuid4().hex[:6]}"
    _slot(sid, [FakeBackend("b1", wholesale=500)])
    key = _key()          # fresh: zero own money, starter granted at issuance
    out = store.call_slot(sid, key, {}, "test")
    assert out["ok"] is True
    # the good was paid entirely out of the starter bucket
    assert out["receipt"]["funding"]["starter_millicents"] == 500


# ─── tier is computed, catalog leaks nothing ─────────────────────────────────


def test_tier_computed_from_availability():
    two = _slot("t-two", [FakeBackend("a"), FakeBackend("b")])
    one = _slot("t-one", [FakeBackend("a"), FakeBackend("b", available=False)])
    zero = _slot("t-zero", [FakeBackend("a", available=False)])
    assert two.tier == "production"
    assert one.tier == "provisional"
    assert zero.tier == "unavailable"


def test_catalog_exposes_no_key_material():
    _slot("c1", [FakeBackend("jina-reader"), FakeBackend("firecrawl")])
    cat = store.catalog()
    assert cat["unit"] == "millicents"
    assert cat["millicents_per_cent"] == 1000
    assert cat["counter_fee_pct"] == 5
    assert cat["starter_credit"]["millicents"] == STARTER_GRANT_MILLICENTS
    slots = {s["id"]: s for s in cat["slots"]}
    entry = slots["c1"]
    assert entry["tier"] == "production"
    assert entry["backends"] == ["jina-reader", "firecrawl"]   # ids only
    assert entry["max_price_millicents"] == 1_000
    # no field anywhere in the entry carries the backend secret
    assert "sk_live_should_never_appear" not in repr(cat)
    # anchor SKUs ride along at tier "anchor"
    anchors = [s for s in cat["slots"] if s["tier"] == "anchor"]
    assert {a["id"] for a in anchors} == {"negotiate.session", "negotiate.bundle"}
    assert all("price_cents" in a and "price_millicents" in a for a in anchors)


# ─── telemetry fires on every call, uncharged failures included ──────────────


def test_telemetry_logged_for_charged_and_uncharged():
    events = []
    store.set_telemetry_sink(lambda **f: events.append(f))
    ok_sid = f"tok-{uuid.uuid4().hex[:6]}"
    bad_sid = f"tbad-{uuid.uuid4().hex[:6]}"
    _slot(ok_sid, [FakeBackend("b1", wholesale=300)])
    _slot(bad_sid, [FakeBackend("b1", payload={"markdown": ""})])
    key = _key()
    store.call_slot(ok_sid, key, {}, "test")
    store.call_slot(bad_sid, key, {}, "test")
    settled = {e["slot_id"]: e["settled"] for e in events}
    assert settled[ok_sid] is True
    assert settled[bad_sid] is False        # non-delivery is still telemetry
    # the charged line carries the millicent price field
    ok_line = next(e for e in events if e["slot_id"] == ok_sid)
    assert ok_line["price_millicents"] == 300

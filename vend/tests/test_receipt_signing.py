"""Signed store receipts — the GAUNTLET #4 fix, as tests.

Finding #4: store receipts were UNSIGNED, so "price == wholesale" was two
fields the store wrote about itself; the anchor $2 charge returned no checkable
receipt at all; the hash recipe took ~13 guesses; and follow-up moves showed
`compute: {}` (provenance dropped mid-session). These tests pin the fixes:

  - every receipt kind (fetch, session open, every move, close summary) is
    Ed25519-signed and verifies STANDALONE via vend.receipt_signing.verify_receipt
  - tampering with ANY field breaks verification (the signature is load-bearing)
  - key_source ("env"|"ephemeral") is VISIBLE on every receipt
  - the compute-provenance is HONEST per move: engine_path "mc" + rollouts>0 on a
    refined counter; "closed_form" + rollouts 0 on an accept node (the MC layer
    short-circuits there — 0 rollouts, per mc_search.py's own control flow)
  - the catalog's `receipts` block is instruction-complete: following its stated
    content_hash recipe against a live receipt reproduces the hash (zero guesses),
    and its published pubkey verifies a live signature (the third-party path)
"""
import hashlib
import json
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_receipt_signing.db"))

from gametheory.server.onboarding import (  # noqa: E402
    issue_key, wallet_credit,
)
from vend import store, session  # noqa: E402
from vend.advice import advise_charged  # noqa: E402
from vend.receipt_signing import (  # noqa: E402
    safe_sign, sign_receipt, signing_info, verify_receipt,
)
from vend.store import BackendResult, Slot, register_slot  # noqa: E402


# ─── fakes / helpers ─────────────────────────────────────────────────────────


class FakeBackend:
    def __init__(self, *, bid="fake", wholesale=1_234,
                 payload=None):
        self.id = bid
        self.secret = "sk_live_never_leaks"
        self._wholesale = wholesale
        self._payload = payload or {"markdown": "# ok", "url": "http://x"}

    def available(self):
        return True

    def call(self, request):
        return BackendResult(payload=self._payload,
                             wholesale_millicents=self._wholesale,
                             wholesale_estimated=False, backend_id=self.id,
                             meta={"status": 200})


def _slot(slot_id, backend, *, max_price=2_000):
    return register_slot(Slot(
        id=slot_id, title=f"slot {slot_id}", backends=[backend],
        predicate=lambda p: (bool(p.get("markdown", "").strip()), "empty"),
        predicate_id="fetch.v1", max_price_millicents=max_price,
        request_doc="{url: str}"))


def _key(cents=1000):
    k = issue_key(agent_id=f"rs-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="receipt signing tests")["api_key"]
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


_RESALE = dict(category="resale", side="sell", walk_away=170, target=210)


def _fetch_receipt(wholesale=1_234):
    sid = f"rs-fetch-{uuid.uuid4().hex[:6]}"
    _slot(sid, FakeBackend(wholesale=wholesale))
    out = store.call_slot(sid, _key(), {"url": "http://x"}, "test")
    assert out["ok"] is True
    return out["receipt"], out["payload"]


# ─── signature module: sign / verify / tamper ────────────────────────────────


def test_sign_then_verify_roundtrip():
    signed = sign_receipt({"a": 1, "b": "two", "nested": {"x": [1, 2]}})
    assert verify_receipt(signed) is True
    # the honesty fields are present and inside the signature envelope
    assert signed["key_source"] in ("env", "ephemeral")
    assert signed["pubkey_fingerprint"].startswith("sha256:")
    assert signed["signature"]


def test_verify_false_on_missing_signature():
    assert verify_receipt({"a": 1}) is False
    assert verify_receipt({"a": 1, "signature": None}) is False


def test_tamper_any_field_breaks_verify():
    signed = sign_receipt({"price_millicents": 1234, "backend_id": "jina",
                           "content_hash": "abc"})
    assert verify_receipt(signed) is True
    for field in ("price_millicents", "backend_id", "content_hash",
                  "pubkey_fingerprint", "key_source"):
        bad = dict(signed)
        bad[field] = "MUTATED" if isinstance(signed[field], str) else 999999
        assert verify_receipt(bad) is False, f"tamper on {field!r} not caught"
    # flipping a signature byte also fails
    flip = dict(signed)
    flip["signature"] = ("A" if signed["signature"][0] != "A" else "B") \
        + signed["signature"][1:]
    assert verify_receipt(flip) is False


def test_safe_sign_matches_sign_when_key_loads():
    # in dev/tests the ephemeral key always loads, so safe_sign signs for real
    a = safe_sign({"x": 1})
    assert verify_receipt(a) is True
    assert "signing_error" not in a


# ─── the fetch (commodity) receipt ───────────────────────────────────────────


def test_fetch_receipt_signed_and_verifies():
    r, _ = _fetch_receipt()
    assert verify_receipt(r) is True
    assert r["price_millicents"] == r["wholesale_millicents"] == 1_234
    assert r["key_source"] in ("env", "ephemeral")     # signer transparency
    assert r["pubkey_fingerprint"].startswith("sha256:")


def test_fetch_receipt_tamper_detected():
    r, _ = _fetch_receipt()
    # the exact self-asserted claim finding #4 flagged: price == wholesale
    forged = dict(r)
    forged["price_millicents"] = 1                     # "I only charged 1"
    assert verify_receipt(forged) is False


def test_fetch_receipt_verifies_against_catalog_pubkey():
    # the THIRD-PARTY path: verify with the pubkey the catalog publishes, not
    # the ambient process key.
    r, _ = _fetch_receipt()
    _slot(f"rs-live-{uuid.uuid4().hex[:6]}", FakeBackend())
    pem = store.catalog()["receipts"]["signature"]["pubkey_pem"]
    assert verify_receipt(r, pubkey_pem=pem) is True


# ─── the anchor receipts: open / move / summary ──────────────────────────────


def test_session_open_receipt_signed():
    key = _key()
    sess = session.open_session_charged(api_key=key, seed=7, **_RESALE)
    r = sess["receipt"]
    assert verify_receipt(r) is True
    assert r["kind"] == "nextmove.session_open"
    assert r["policy_id"]
    assert r["price_millicents"] == sess["price_millicents"]
    assert r["funding"] == sess["funding"]
    assert r["balance_after"] == sess["balance_after"]
    assert r["context_hash"] == sess["context_hash"]
    assert r["key_source"] in ("env", "ephemeral")


def test_move_receipt_counter_is_mc():
    key = _key()
    sess = session.open_session_charged(api_key=key, seed=7, **_RESALE)
    # their offers are below the seller's floor → the engine counters, and a
    # counter is the ONE move MC refines.
    a, idx = session.session_advise(session_id=sess["session_id"], api_key=key,
                                    their_offers=[150, 165])
    assert a.move == "counter"
    r = a.receipt
    assert verify_receipt(r) is True
    assert r["kind"] == "nextmove.move"
    assert r["move_index"] == idx
    assert r["compute"]["engine_path"] == "mc"
    assert r["compute"]["rollouts"] > 0
    assert r["compute"]["deterministic"] is True


def test_move_receipt_accept_is_closed_form():
    key = _key()
    sess = session.open_session_charged(api_key=key, seed=7, **_RESALE)
    # an offer above the seller's target → the closed form says accept, and the
    # MC layer short-circuits (0 rollouts). The receipt must NOT claim MC ran.
    a, idx = session.session_advise(session_id=sess["session_id"], api_key=key,
                                    their_offers=[215])
    assert a.move == "accept"
    r = a.receipt
    assert verify_receipt(r) is True
    assert r["compute"]["engine_path"] == "closed_form"
    assert r["compute"]["rollouts"] == 0
    assert "short-circuits on accept" in r["compute"]["note"]


def test_bundle_move_receipt_closed_form():
    key = _key()
    sess = session.open_session_charged(api_key=key, category="supply",
                                        side="buy", walk_away=5000, target=4200)
    issues = [
        {"name": "price", "options": ["4800", "5000", "5200"],
         "my_utility": [1.0, 0.6, 0.2], "their_utility": [0.2, 0.6, 1.0]},
        {"name": "delivery", "options": ["2wk", "4wk"],
         "my_utility": [0.9, 0.4], "their_utility": [0.3, 0.9]},
    ]
    a, idx = session.session_advise_bundle(session_id=sess["session_id"],
                                           api_key=key, issues=issues,
                                           my_batna=0.4)
    r = a.receipt
    assert verify_receipt(r) is True
    assert r["kind"] == "nextmove.bundle_move"
    assert r["compute"]["engine_path"] == "closed_form"   # pure logrolling
    assert r["compute"]["rollouts"] == 0


def test_close_summary_receipt_signed_and_complete():
    key = _key()
    sess = session.open_session_charged(api_key=key, seed=7, **_RESALE)
    a1, _ = session.session_advise(session_id=sess["session_id"], api_key=key,
                                   their_offers=[150])
    a2, _ = session.session_advise(session_id=sess["session_id"], api_key=key,
                                   their_offers=[150, 165], my_offers=[a1.offer])
    assert session.close_session(session_id=sess["session_id"],
                                 api_key=key) is True
    summ = session.session_summary_receipt(session_id=sess["session_id"],
                                           api_key=key)
    assert verify_receipt(summ) is True
    assert summ["kind"] == "nextmove.session_summary"
    assert summ["moves"] == 2
    # total charged = one $2 open, moves free
    assert summ["total_charged_millicents"] == sess["price_millicents"]
    # the per-move anchors are exactly the two move context_hashes, in order
    assert summ["move_context_hashes"] == [a1.context_hash, a2.context_hash]
    assert summ["closed"] is True


def test_summary_key_mismatch_indistinguishable_from_unknown():
    key, other = _key(), _key()
    sess = session.open_session_charged(api_key=key, **_RESALE)
    with pytest.raises(session.SessionError, match="unknown session"):
        session.session_summary_receipt(session_id=sess["session_id"],
                                        api_key=other)
    with pytest.raises(session.SessionError, match="unknown session"):
        session.session_summary_receipt(session_id="ns_never", api_key=key)


def test_anchor_receipts_tamper_detected():
    key = _key()
    sess = session.open_session_charged(api_key=key, seed=7, **_RESALE)
    a, _ = session.session_advise(session_id=sess["session_id"], api_key=key,
                                  their_offers=[150, 165])
    session.close_session(session_id=sess["session_id"], api_key=key)
    summ = session.session_summary_receipt(session_id=sess["session_id"],
                                           api_key=key)
    # open: forge the price down; move: forge the rollout count (this is a
    # counter, so engine_path is already "mc" — forge the number instead);
    # summary: inflate the moves count — each must break the signature.
    assert a.move == "counter" and a.receipt["compute"]["engine_path"] == "mc"
    bad_open = {**sess["receipt"], "price_millicents": 1}
    bad_move = {**a.receipt, "compute": {**a.receipt["compute"], "rollouts": 1}}
    bad_summ = {**summ, "moves": 99}
    assert verify_receipt(bad_open) is False
    assert verify_receipt(bad_move) is False
    assert verify_receipt(bad_summ) is False


# ─── the single paid advice also hands back a signed receipt ─────────────────


def test_advise_charged_attaches_signed_receipt():
    key = _key()
    a = advise_charged(api_key=key, seed=7, their_offers=[150, 165],
                       my_offers=[215], rounds_left=4, **_RESALE)
    assert verify_receipt(a.receipt) is True
    assert a.receipt["price_millicents"] > 0            # the $2 charge
    assert a.receipt["compute"]["engine_path"] in ("mc", "closed_form")


# ─── the catalog receipts block is instruction-complete (zero guesses) ───────


def test_catalog_receipts_block_present():
    _slot(f"rs-cat-{uuid.uuid4().hex[:6]}", FakeBackend())
    rb = store.catalog()["receipts"]
    assert set(rb) == {"content_hash", "signature", "pin", "upstream_ref",
                       "runway_estimate_calls"}
    # the runway hint is documented with its exact "calls like this one left" label
    assert "calls like this one left" in rb["runway_estimate_calls"]
    ch = rb["content_hash"]
    assert ch["algorithm"] == "blake2b" and ch["digest_size"] == 16
    assert ch["json_dumps"] == {"sort_keys": True, "separators": [",", ":"],
                                "default": "str"}
    sig = rb["signature"]
    assert sig["scheme"] == "ed25519"
    assert sig["pubkey_pem"] and sig["pubkey_fingerprint"]
    assert sig["key_source"] in ("env", "ephemeral")
    assert "signature" in sig["signed_bytes"]           # says which field is excluded


def test_catalog_receipts_pin_points_out_of_band_with_ephemeral_caveat():
    # auditor: the receipts block tells a verifier WHERE to pin the pubkey
    # out-of-band, and states what an ephemeral key can/cannot prove.
    _slot(f"rs-pin-{uuid.uuid4().hex[:6]}", FakeBackend())
    pin = store.catalog()["receipts"]["pin"]
    assert pin["fetch_pubkey"] == "GET /v1/store/notary_pubkey"
    assert "pubkey_fingerprint" in pin["match"]
    caveat = pin["key_source_caveat"].lower()
    assert "ephemeral" in caveat and "notary_key_pem" in caveat
    # and it must name the honest limit: signer-consistency only under ephemeral
    assert "consist" in caveat


def test_catalog_receipts_upstream_ref_is_evidence_passthrough_not_proof():
    _slot(f"rs-ref-{uuid.uuid4().hex[:6]}", FakeBackend())
    note = store.catalog()["receipts"]["upstream_ref"].lower()
    assert "passthrough" in note
    assert "not" in note and "proof" in note            # explicitly not invoice proof


def test_catalog_content_hash_recipe_reproduces_a_live_receipt():
    # follow the catalog's OWN stated recipe against a live receipt's payload —
    # the auditor's ~13 guesses become zero.
    r, payload = _fetch_receipt(wholesale=777)
    _slot(f"rs-recipe-{uuid.uuid4().hex[:6]}", FakeBackend())
    recipe = store.catalog()["receipts"]["content_hash"]
    blob = json.dumps(payload,
                      sort_keys=recipe["json_dumps"]["sort_keys"],
                      separators=tuple(recipe["json_dumps"]["separators"]),
                      default=str).encode()
    got = hashlib.blake2b(blob, digest_size=recipe["digest_size"]).hexdigest()
    assert got == r["content_hash"]


def test_catalog_signature_block_verifies_a_live_receipt():
    r, _ = _fetch_receipt()
    _slot(f"rs-sig-{uuid.uuid4().hex[:6]}", FakeBackend())
    sig = store.catalog()["receipts"]["signature"]
    # the fingerprint the catalog publishes is the one on the receipt
    assert r["pubkey_fingerprint"] == sig["pubkey_fingerprint"]
    # and its published pubkey PEM verifies the live signature
    assert verify_receipt(r, pubkey_pem=sig["pubkey_pem"]) is True


def test_signing_info_leaks_no_private_material():
    info = signing_info()
    assert "PRIVATE" not in info["pubkey_pem"]
    assert "BEGIN PUBLIC KEY" in info["pubkey_pem"]

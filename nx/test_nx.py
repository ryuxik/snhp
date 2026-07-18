"""SNHP-NX/1 CONFORMANCE SUITE (pytest, no network, deterministic).

Covers: state-machine legality (illegal transitions raise); I1 unconstructibility
(property-style — any package with an above-list line always raises); I2 round
bound and I3 accept-verbatim; wire-format round-trip (to_json/from_json identity);
transcript-hash stability across process runs (a pinned golden) and sensitivity
to any field change; and a bridge smoke (one seeded NX session over the MPX mount
strikes a legal deal). Run: `python -m pytest nx/test_nx.py -q`.

THIRD-PARTY CONFORMANCE SHIM
----------------------------
A third-party implementation can run this same suite against its OWN classes by
providing an adapter module exposing the reference names with the same
signatures, and pointing `NX_IMPL` at it:

    NX_IMPL = importlib.import_module(os.environ.get("NX_IMPL", "nx.protocol"))

The contract the shim must satisfy (all constructors raise `NXViolation` on an
I1 breach, `NXProtocolError` on an illegal transition):

    Line(line_id, item, qty, ship_date, list_price, price)       # I1 at construction
    ListSchedule.from_map({schedule_key: list_price})
    NXQuote(session_ref, schedule, package)                      # package validated
    NXPropose(session_ref, party, package)
    NXSession(session_ref, max_rounds)
      .quote(NXQuote) .propose(NXPropose) .accept(party)->NXReceipt .decline(party,reason)
      .canonical_transcript()->list[dict]  .transcript_hash()->str
    verify_transcript(messages, expected_hash=None)->{ok,checks,reasons,hash}

The economic/bridge tests (`test_bridge_*`) are MPX-specific and only run when the
impl also exposes `nx.bridge`; a bare protocol impl skips them. The golden hash
(`GOLDEN_HASH`) is a property of the canonical encoding, so any conforming impl
that hashes the same transcript MUST reproduce it byte-for-byte.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random

import pytest

NX = importlib.import_module(os.environ.get("NX_IMPL", "nx.protocol"))

Line = NX.Line
ListSchedule = NX.ListSchedule
NXQuote = NX.NXQuote
NXPropose = NX.NXPropose
NXAccept = NX.NXAccept
NXDecline = NX.NXDecline
NXSession = NX.NXSession
NXReceipt = NX.NXReceipt
State = NX.State
NXViolation = NX.NXViolation
NXProtocolError = NX.NXProtocolError
schedule_key = NX.schedule_key
message_from_wire = NX.message_from_wire
verify_transcript = NX.verify_transcript

# Pinned golden — recomputed by any conforming canonical encoder (see docstring).
GOLDEN_HASH = "sha256:c6511319df915d0263a7ee473f32ce0b0b3b7139a946a9bf1d87aa5ee534685b"


# ── fixtures ────────────────────────────────────────────────────────────────
def _sched():
    return ListSchedule.from_map({"item0|10|3": 500.0, "item0|6|2": 330.0,
                                  "item0|4|1": 250.0})


def _open_pkg():
    return (Line("L0", "item0", 10, 3, 500.0, 500.0),)


def _session(max_rounds=8):
    s = NXSession("s1", max_rounds)
    s.quote(NXQuote("s1", _sched(), _open_pkg()))
    return s


# ── I1 NEVER-ABOVE-LIST (unconstructible, property-style) ───────────────────
def test_i1_above_list_line_is_unconstructible():
    with pytest.raises(NXViolation):
        Line("L0", "item0", 10, 3, 500.0, 500.01)   # 1 cent over list


def test_i1_property_any_above_list_line_always_raises():
    """Randomized: for many (list, price) with price>list, construction MUST
    raise; for price<=list it MUST succeed. The invariant is structural."""
    rng = random.Random(20260718)
    for _ in range(400):
        listp = round(rng.uniform(1.0, 5000.0), 4)
        over = round(listp + rng.uniform(1e-3, 500.0), 4)
        with pytest.raises(NXViolation):
            Line("L", "item0", rng.randint(1, 50), rng.randint(1, 12), listp, over)
        under = round(listp * rng.uniform(0.0, 1.0), 4)
        ln = Line("L", "item0", rng.randint(1, 50), rng.randint(1, 12), listp, under)
        assert ln.price <= ln.list_price + 1e-9


def test_i1_session_rejects_unlisted_config():
    """A proposal naming a config absent from the seller's quote schedule is
    rejected (the seller is the sole list authority)."""
    s = _session()
    with pytest.raises(NXViolation):
        s.propose(NXPropose("s1", "buyer", (Line("L0", "item0", 99, 9, 12345.0, 1.0),)))


def test_i1_session_rejects_restated_list():
    """A proposed line that restates its list_price (not the schedule's value) is
    rejected — a buyer cannot manufacture headroom by inventing a list."""
    s = _session()
    # config item0|6|2 is listed at 330.0; restate it as 900.0 and price 800 (<900)
    with pytest.raises(NXViolation):
        s.propose(NXPropose("s1", "buyer", (Line("L0", "item0", 6, 2, 900.0, 800.0),)))


def test_i1_quote_opening_package_validated_against_schedule():
    with pytest.raises(NXViolation):
        NXQuote("s1", _sched(), (Line("L0", "item0", 7, 7, 400.0, 400.0),))  # 7|7 unlisted


# ── I2 BOUNDED ──────────────────────────────────────────────────────────────
def test_i2_round_bound_enforced():
    s = _session(max_rounds=2)
    p = NXPropose("s1", "buyer", (Line("L0", "item0", 6, 2, 330.0, 300.0),))
    s.propose(p)
    s.propose(p)
    with pytest.raises(NXProtocolError):
        s.propose(p)                       # the 3rd exceeds max_rounds=2


def test_i2_max_rounds_must_be_positive():
    with pytest.raises(NXProtocolError):
        NXSession("s1", 0)


# ── I3 PACKAGE-ATOMICITY / accept-verbatim ──────────────────────────────────
def test_i3_accept_adopts_standing_package_verbatim():
    s = _session()
    counter = (Line("L0", "item0", 6, 2, 330.0, 300.0),)
    s.propose(NXPropose("s1", "buyer", counter))
    receipt = s.accept("seller")
    # the agreed package is exactly the standing (last-proposed) package
    assert receipt.agreed_package == [counter[0].to_wire()]
    assert s.state == State.SETTLED


def test_i3_accept_takes_no_package_argument():
    """Structural accept-verbatim: accept() cannot carry new terms (it only takes
    the accepting party). This is what makes 'accept' un-forgeable as a counter."""
    s = _session()
    import inspect
    params = list(inspect.signature(s.accept).parameters)
    assert params == ["party"]


# ── state-machine legality ──────────────────────────────────────────────────
def test_quote_only_from_mounted():
    s = _session()
    with pytest.raises(NXProtocolError):
        s.quote(NXQuote("s1", _sched(), _open_pkg()))     # already quoted


def test_propose_illegal_before_quote():
    s = NXSession("s1", 8)
    with pytest.raises(NXProtocolError):
        s.propose(NXPropose("s1", "buyer", _open_pkg()))


def test_accept_illegal_after_settle():
    s = _session()
    s.accept("buyer")
    with pytest.raises(NXProtocolError):
        s.accept("seller")


def test_propose_illegal_after_settle():
    s = _session()
    s.accept("buyer")
    with pytest.raises(NXProtocolError):
        s.propose(NXPropose("s1", "buyer", (Line("L0", "item0", 6, 2, 330.0, 300.0),)))


def test_decline_ends_session():
    s = _session()
    s.decline("buyer", "walk")
    assert s.state == State.DECLINED
    with pytest.raises(NXProtocolError):
        s.accept("buyer")


def test_settle_receipt_requires_settled():
    s = _session()
    with pytest.raises(NXProtocolError):
        s.settle_receipt()


# ── wire-format round-trip (to_json / from_json identity) ───────────────────
def test_line_wire_round_trip():
    ln = Line("L0", "item0", 10, 3, 500.0, 421.5)
    assert Line.from_wire(ln.to_wire()) == ln


def test_message_wire_round_trip_all_types():
    msgs = [
        NXQuote("s1", _sched(), _open_pkg()),
        NXPropose("s1", "buyer", (Line("L0", "item0", 6, 2, 330.0, 300.0),)),
        NXAccept("s1", "seller"),
        NXDecline("s1", "buyer", "no clear"),
    ]
    for m in msgs:
        d = m.to_wire()
        m2 = message_from_wire(json.loads(json.dumps(d)))
        assert m2.to_wire() == d


def test_receipt_json_round_trip():
    s = _session()
    s.propose(NXPropose("s1", "buyer", (Line("L0", "item0", 6, 2, 330.0, 300.0),)))
    r = s.accept("seller")
    r2 = NXReceipt.from_json(r.to_json())
    assert r2.transcript_hash == r.transcript_hash
    assert r2.agreed_package == r.agreed_package
    assert r2.protocol == r.protocol


# ── transcript hash: cross-process stability + field sensitivity ────────────
def _golden_session():
    sched = ListSchedule.from_map({"itemG|10|3": 500.0, "itemG|6|2": 330.0})
    s = NXSession("golden-ref", 8)
    s.quote(NXQuote("golden-ref", sched, (Line("L0", "itemG", 10, 3, 500.0, 500.0),)))
    s.propose(NXPropose("golden-ref", "buyer", (Line("L0", "itemG", 6, 2, 330.0, 300.0),)))
    return s


def test_transcript_hash_is_stable_golden():
    """Pinned across process runs: the canonical encoding is deterministic, so
    the same transcript hashes to the same value every run (and in any conforming
    impl)."""
    s = _golden_session()
    r = s.accept("seller")
    assert r.transcript_hash == GOLDEN_HASH


def test_transcript_hash_sensitive_to_any_field_change():
    base = _golden_session()
    base.accept("seller")
    h0 = base.transcript_hash()
    # change the counter price by one cent -> different hash
    s2 = ListSchedule.from_map({"itemG|10|3": 500.0, "itemG|6|2": 330.0})
    alt = NXSession("golden-ref", 8)
    alt.quote(NXQuote("golden-ref", s2, (Line("L0", "itemG", 10, 3, 500.0, 500.0),)))
    alt.propose(NXPropose("golden-ref", "buyer", (Line("L0", "itemG", 6, 2, 330.0, 300.01),)))
    alt.accept("seller")
    assert alt.transcript_hash() != h0
    # change the accepting party -> different hash
    alt2 = _golden_session()
    alt2.accept("buyer")
    assert alt2.transcript_hash() != h0


def test_verify_transcript_ok_and_catches_i1_tamper():
    s = _golden_session()
    r = s.accept("seller")
    trans = s.canonical_transcript()
    v = verify_transcript(trans, expected_hash=r.transcript_hash)
    assert v["ok"] and v["checks"]["I1_never_above_list"] and v["checks"]["hash"]
    # tamper: raise a line's price above its list in the recorded transcript
    tampered = json.loads(json.dumps(trans))
    for m in tampered:
        if m.get("type") == "NX-PROPOSE":
            m["package"][0]["price"] = m["package"][0]["list_price"] + 100.0
    v2 = verify_transcript(tampered)
    assert not v2["ok"] and not v2["checks"]["I1_never_above_list"]


# ── bridge smoke (MPX mount) — skipped for a bare protocol impl ─────────────
_HAS_BRIDGE = importlib.util.find_spec("nx.bridge") is not None


@pytest.mark.skipif(not _HAS_BRIDGE, reason="MPX bridge not present in this impl")
def test_bridge_seeded_session_strikes_a_legal_deal():
    from nx.bridge import (MPXScenario, run_nx_session, feasible_configs,
                           list_price, notary_attestation)
    s = MPXScenario("smoke-1", "item0", need_qty=24, need_by=3, unit_value=100.0,
                    urgency=6.0, c0=42.0, c1=0.05, cap=4.0, expedite=3.0,
                    inventory=500.0, markup=0.25, min_markup=0.05)
    assert feasible_configs(s)                         # a deal is possible
    out = run_nx_session(s)
    assert out.settled
    # the struck line respects I1 (price <= list for its config) and is IR
    assert out.agreed_price <= list_price(s, out.agreed_qty, out.agreed_ship_date) + 1e-6
    assert out.joint_surplus > 0.0
    # I4 worked example: the notary signs the transcript hash (if crypto present)
    att = notary_attestation(out.receipt)
    if att is not None:
        assert att["hash"] == out.receipt.transcript_hash
        assert att["scheme"].startswith("snhp-notary")


@pytest.mark.skipif(not _HAS_BRIDGE, reason="MPX bridge not present in this impl")
def test_bridge_is_deterministic():
    from nx.bridge import MPXScenario, run_nx_session
    s = MPXScenario("det-1", "item0", need_qty=30, need_by=2, unit_value=95.0,
                    urgency=7.0, c0=40.0, c1=0.04, cap=3.0, expedite=3.0,
                    inventory=400.0, markup=0.24, min_markup=0.05)
    a = run_nx_session(s)
    b = run_nx_session(s)
    assert a.settled == b.settled
    assert (a.agreed_qty, a.agreed_ship_date, a.agreed_price) == \
           (b.agreed_qty, b.agreed_ship_date, b.agreed_price)
    assert a.receipt.transcript_hash == b.receipt.transcript_hash


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

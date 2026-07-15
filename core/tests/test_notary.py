"""Notary receipt tests (core/notary.py) — fast, pure stdlib + cryptography.

The acceptance gate for the first shippable artifact: over-list is
unconstructible, any tamper breaks verification, the prev_hash chain catches a
break, a pubkey-only holder can verify an honest receipt, a_prime_ok is
re-derivable from the receipt's own numbers, the context hash is a function of
(context + disclosure) and nothing else, the serialized receipt never carries
raw WTP, and the (b)-probe reads finite-stock vs capacity off the engine.
"""
from __future__ import annotations

import json
import os

import pytest

from core.api import build_graph
from core.cost import capacity_relief, compose, const
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as engine_quote
from core.offer_graph import DimKind
from core.state import ShopState
from core.notary import (NotaryReceipt, NotaryViolation, canon_hash,
                         disclosure_digest, emit_receipt, load_notary_key,
                         regime_probe, verify_chain, verify_receipt)


# ── specs ───────────────────────────────────────────────────────────────────
def _finite_graph():
    """Vend-like finite-stock venue: a costed CHOICE + QUANTITY, const +
    salvage_on_expiry, NO fulfillment. The seller reservation is pure cost."""
    return build_graph({
        "name": "vend",
        "dims": [
            {"id": "sku", "kind": "choice", "options": [
                {"id": "cola", "price_delta": 2.50, "unit_cost": 0.90,
                 "perishable": True, "salvage": 0.10}]},
            {"id": "qty", "kind": "quantity", "qty_cap": 3}],
        "cost": ["const", "salvage_on_expiry"]})


def _capacity_graph():
    """Boba-like capacity venue: CHOICE + FULFILLMENT (now/later) + QUANTITY,
    with a capacity_relief credit on the deferred slot. capacity_relief needs a
    live Python fn, so the graph is built directly (not from a JSON token)."""
    def relief(graph, state, config, qty):
        for d in graph.dims:
            if d.kind == DimKind.FULFILLMENT:
                o = d.option(config[d.id])
                if not o.immediate and o.slot_ticks > 0:
                    return 1.2 * qty          # a deferred slot frees peak capacity
        return 0.0
    return build_graph({
        "name": "boba",
        "dims": [
            {"id": "drink", "kind": "choice", "options": [
                {"id": "mt", "price_delta": 5.0, "unit_cost": 1.4}]},
            {"id": "pickup", "kind": "fulfillment", "options": [
                {"id": "now", "immediate": True, "slot_ticks": 0},
                {"id": "later", "immediate": False, "slot_ticks": 2}]},
            {"id": "qty", "kind": "quantity", "qty_cap": 2}],
        "cost": compose(const(), capacity_relief(relief))})


def _finite_quote(opts=QuoteOpts()):
    g = _finite_graph()
    st = ShopState(expiring={"cola"})
    b = SeparableBuyer(values={("sku", "cola"): 3.2}, qty_decay=0.3,
                       outside=0.2, balk=0.0)
    q = engine_quote(g, st, b, config={"sku": "cola"}, opts=opts)
    return g, st, b, q


def _small_rent_quote():
    """A quote whose excess rent is small enough that the buffer dominates
    (a_prime_ok True): cost 2.0 close to list 2.5, 2β = 0.5 = rent."""
    g = build_graph({"name": "thin",
                     "dims": [{"id": "sku", "kind": "choice", "options": [
                         {"id": "x", "price_delta": 2.50, "unit_cost": 2.00}]}],
                     "cost": ["const"]})
    st = ShopState()
    b = SeparableBuyer(values={("sku", "x"): 4.0}, outside=0.0, balk=0.0)
    q = engine_quote(g, st, b, config={"sku": "x"})
    return g, st, b, q


KEY = load_notary_key()


# ── (1) over-list is unconstructible ─────────────────────────────────────────
def test_over_list_receipt_raises_at_construction():
    kw = dict(protocol="snhp-notary/2", quote_ref="x", venue_id="v", ts="t",
              list_price=2.0, quoted_price=3.0, saving=-1.0, c_eff=0.5,
              excess_rent=1.5, buffer=0.25, a_prime_ok=True,
              regime="finite_stock", reservation_basis="report_independent(state)",
              conditions={"a": True, "a_prime": True, "b": True, "c": True,
                          "d": False}, context_hash="c", disclosure_digest="d",
              engine_version="e", key_source="ephemeral", pubkey_fpr="f",
              counterfactual=None, prev_hash=None, notary_sig="s")
    with pytest.raises(NotaryViolation):
        NotaryReceipt(**kw)                       # p=3 > ℓ=2


def test_emit_refuses_over_list_quote(monkeypatch):
    """Gate (ii): the emitting call re-checks before construction."""
    g, st, b, q = _finite_quote()
    object.__setattr__(q, "price", q.listv + 5.0)   # force an over-list quote
    with pytest.raises(NotaryViolation):
        emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="q",
                     venue_id="v", regime="finite_stock")


# ── (2) tamper any field → verify fails ──────────────────────────────────────
def test_tamper_any_field_breaks_verify():
    g, st, b, q = _finite_quote()
    r = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="q",
                     venue_id="v", regime="finite_stock")
    assert verify_receipt(r.to_dict(), pubkey_pem=KEY.pubkey_pem)["ok"]
    for fld, bad in [("venue_id", "evil"), ("c_eff", 0.0), ("regime", "capacity"),
                     ("disclosure_digest", "sha256:deadbeef"),
                     ("context_hash", "sha256:0"), ("engine_version", "hax"),
                     ("pubkey_fpr", "sha256:0"), ("ts", "2000-01-01T00:00:00+00:00")]:
        d = r.to_dict()
        d[fld] = bad
        res = verify_receipt(d, pubkey_pem=KEY.pubkey_pem)
        assert not res["ok"], f"tamper on {fld!r} slipped through"
    # tampering a nested condition also breaks the signature
    d = r.to_dict()
    d["conditions"] = {**d["conditions"], "b": (not d["conditions"]["b"])}
    assert not verify_receipt(d, pubkey_pem=KEY.pubkey_pem)["ok"]


# ── (3) chain break detected ─────────────────────────────────────────────────
def test_chain_break_detected():
    g, st, b, q = _finite_quote()
    r0 = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="d0",
                      venue_id="v", regime="finite_stock")
    r1 = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="d1",
                      venue_id="v", regime="finite_stock", prev_hash=r0.digest())
    r2 = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="d2",
                      venue_id="v", regime="finite_stock", prev_hash=r1.digest())
    good = verify_chain([r0, r1, r2], pubkey_pem=KEY.pubkey_pem)
    assert good["ok"] and good["chain_ok"] and good["n"] == 3
    # snip the middle link
    bad = verify_chain([r0.to_dict(), {**r2.to_dict()}], pubkey_pem=KEY.pubkey_pem)
    assert not bad["chain_ok"] and not bad["ok"]


# ── (4) verify with pubkey only (no private key) ─────────────────────────────
def test_verify_with_pubkey_only():
    g, st, b, q = _finite_quote()
    r = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="q",
                     venue_id="v", regime="finite_stock")
    # a holder of ONLY the public PEM (no NotaryKey object) can verify
    res = verify_receipt(json.loads(r.to_json()), pubkey_pem=KEY.pubkey_pem)
    assert res["ok"] and all(res["checks"].values())
    # a WRONG key fails the fingerprint pin (and the signature)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    assert not verify_receipt(r.to_dict(), pubkey_pem=other)["ok"]


# ── (5) a_prime_ok re-derivation matches ─────────────────────────────────────
def test_a_prime_rederivation_matches():
    for maker, expect in [(_small_rent_quote, True), (_finite_quote, False)]:
        g, st, b, q = maker()
        opts = QuoteOpts()
        r = emit_receipt(q, state=st, opts=opts, quote_ref="q",
                         venue_id="v", regime="finite_stock")
        beta = max(opts.min_gain_abs, opts.min_gain_frac * q.listv)
        rent = q.listv - q.cost
        assert r.a_prime_ok == (rent <= 2 * beta + 1e-9) == expect
        assert abs(r.excess_rent - rent) < 1e-6
        # the standalone verifier re-derives it from the receipt's own numbers
        res = verify_receipt(r.to_dict(), pubkey_pem=KEY.pubkey_pem)
        assert res["checks"]["a_prime_ok"] and res["checks"]["excess_rent"]


# ── (6) context hash is a function of (context + disclosure) ──────────────────
def test_context_hash_tracks_context_and_disclosure():
    g, st, b, q = _finite_quote()
    opts = QuoteOpts()
    disc_a = {"utilities": {"cola": 3.2}, "walk": 0.2}
    disc_b = {"utilities": {"cola": 9.9}, "walk": 0.2}   # different WTP
    r1 = emit_receipt(q, state=st, opts=opts, quote_ref="q1",
                      venue_id="v", regime="finite_stock", disclosure=disc_a)
    r2 = emit_receipt(q, state=st, opts=opts, quote_ref="q2",
                      venue_id="v", regime="finite_stock", disclosure=disc_a)
    r3 = emit_receipt(q, state=st, opts=opts, quote_ref="q3",
                      venue_id="v", regime="finite_stock", disclosure=disc_b)
    # same context + same disclosure ⇒ same context_hash (ts/quote_ref aside)
    assert r1.context_hash == r2.context_hash
    assert r1.disclosure_digest == r2.disclosure_digest
    # different disclosure ⇒ different context_hash AND different digest
    assert r3.context_hash != r1.context_hash
    assert r3.disclosure_digest != r1.disclosure_digest
    # the digest is one-way: the raw utilities never appear in it
    assert disclosure_digest({"cola": 3.2}, 0.2) == r1.disclosure_digest


# ── (7) serialized receipt never carries raw WTP ─────────────────────────────
def test_serialized_receipt_has_no_raw_wtp():
    g, st, b, q = _finite_quote()
    r = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="q",
                     venue_id="v", regime="finite_stock",
                     disclosure={"utilities": {"cola": 3.2}, "walk": 0.2})
    text = r.to_json()
    for banned in ("utilities", "values", "wtp", "3.2", "\"walk\""):
        assert banned not in text, f"WTP leak: {banned!r} present in receipt"
    # the disclosure digest IS present (it is the only trace of the disclosure)
    assert r.disclosure_digest in text


# ── (8) regime probe: finite-stock vs capacity ───────────────────────────────
def test_regime_probe_finite_stock():
    g = _finite_graph()
    b = SeparableBuyer(values={("sku", "cola"): 3.2}, qty_decay=0.3,
                       outside=0.4, balk=0.0)
    reg, ev = regime_probe(g, ShopState(), b, config={"sku": "cola"})
    assert reg == "finite_stock" and not ev["reservation_moved"]
    reg2, _ = regime_probe(g, ShopState(expiring={"cola"}), b,
                           config={"sku": "cola"})
    assert reg2 == "finite_stock"


def test_regime_probe_capacity():
    g = _capacity_graph()
    b = SeparableBuyer(values={("drink", "mt"): 7.5}, qty_decay=0.2,
                       outside=1.0, balk=0.4, defer={2: 2.5})
    reg, ev = regime_probe(g, ShopState(capacity={2: 50.0}), b,
                           config={"drink": "mt"})
    assert reg == "capacity" and ev["reservation_moved"]
    # the movement is the capacity credit vanishing as the report scales up
    reservations = [p["reservation"] for p in ev["probes"]]
    assert max(reservations) - min(reservations) > 1e-6


def test_receipt_b_condition_follows_regime():
    """A capacity receipt reports b=false and reservation_basis attested(ô) —
    honestly, never papered over."""
    g = _capacity_graph()
    st = ShopState(capacity={2: 50.0})
    b = SeparableBuyer(values={("drink", "mt"): 7.5}, qty_decay=0.2,
                       outside=1.0, balk=0.4, defer={2: 2.5})
    q = engine_quote(g, st, b, config={"drink": "mt", "pickup": "later"})
    r = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="q",
                     venue_id="boba", regime="capacity")
    assert r.conditions["b"] is False
    assert r.reservation_basis == "attested(ô)"
    assert verify_receipt(r.to_dict(), pubkey_pem=KEY.pubkey_pem)["ok"]


# ── CLI + persistent-key round trip ──────────────────────────────────────────
def test_persistent_key_round_trip_and_cli(tmp_path, monkeypatch):
    """A PKCS8 PEM in NOTARY_KEY_PEM gives a stable, env-sourced key; the CLI
    verifies a JSONL of chained receipts and exits 0."""
    from core.notary import generate_key_pem, main
    pem = generate_key_pem()
    monkeypatch.setenv("NOTARY_KEY_PEM", pem)
    key = load_notary_key(refresh=True)
    assert key.key_source == "env"

    g, st, b, q = _finite_quote()
    r0 = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="d0",
                      venue_id="v", regime="finite_stock", key=key,
                      embed_pubkey=True)
    r1 = emit_receipt(q, state=st, opts=QuoteOpts(), quote_ref="d1",
                      venue_id="v", regime="finite_stock", prev_hash=r0.digest(),
                      key=key, embed_pubkey=True)
    path = tmp_path / "receipts.jsonl"
    path.write_text(r0.to_json() + "\n" + r1.to_json() + "\n")
    # embedded pubkey ⇒ the CLI needs no --pubkey flag
    assert main(["verify", str(path)]) == 0
    monkeypatch.delenv("NOTARY_KEY_PEM", raising=False)
    load_notary_key(refresh=True)      # reset the module cache to ephemeral


# ── (finding 1) rounding root-cause: derived fields never drift ──────────────
def test_rounding_confirmed_triggers_emit_and_verify():
    """Both confirmed trigger values: ℓ=9.385959,p=2.834748 used to RAISE at
    emit; listv=7.123456,cost=2.0 used to FAIL verify. Deriving saving/
    excess_rent from the STORED rounded components fixes both."""
    from core.engine import Quote
    from core.state import ShopState
    st = ShopState()
    qA = Quote(config={"sku": "cola"}, price=2.834748, listv=9.385959,
               cost=1.0, value=10.0, save=0.0, seller_gain=0.0, buyer_gain=0.0,
               feasible=True, why=[], audit={})
    rA = emit_receipt(qA, state=st, opts=QuoteOpts(), quote_ref="A",
                      venue_id="v", regime="finite_stock", key=KEY)
    resA = verify_receipt(rA.to_dict(), pubkey_pem=KEY.pubkey_pem)
    assert resA["ok"] and resA["checks"]["saving"]
    assert rA.saving == round(rA.list_price - rA.quoted_price, 4)

    qB = Quote(config={"sku": "cola"}, price=3.0, listv=7.123456, cost=2.0,
               value=9.0, save=0.0, seller_gain=0.0, buyer_gain=0.0,
               feasible=True, why=[], audit={})
    rB = emit_receipt(qB, state=st, opts=QuoteOpts(), quote_ref="B",
                      venue_id="v", regime="finite_stock", key=KEY)
    resB = verify_receipt(rB.to_dict(), pubkey_pem=KEY.pubkey_pem)
    assert resB["ok"] and resB["checks"]["excess_rent"]
    assert rB.excess_rent == round(rB.list_price - rB.c_eff, 6)


# ── (finding 3) regime probe: a missing rung is not movement ─────────────────
def test_regime_probe_finite_stock_survives_walk_at_high_scale():
    """A finite-stock venue where the buyer WALKS at 3× (outside dominates)
    but transacts at an equal reservation at 0× and 1× is STILL finite_stock —
    a walk is missing data, not a moving reservation."""
    g = _finite_graph()
    b = SeparableBuyer(values={("sku", "cola"): 3.2}, qty_decay=0.3,
                       outside=0.3, balk=0.0)
    reg, ev = regime_probe(g, ShopState(), b, config={"sku": "cola"},
                           opts=QuoteOpts(quote_lookers=False))
    present = [p for p in ev["probes"] if p["reservation"] is not None]
    walked = [p for p in ev["probes"] if p["reservation"] is None]
    assert walked and len(present) >= 2          # a rung is genuinely missing
    assert reg == "finite_stock" and not ev["insufficient_probe"]


def test_regime_probe_insufficient_probe_is_conservative_capacity():
    """When all-but-one scale walks (<2 present, or the base is missing) there
    is no positive evidence of report-independence: stay conservatively
    'capacity' and flag insufficient_probe — never claim finite by default."""
    g = _finite_graph()
    b = SeparableBuyer(values={("sku", "cola"): 3.2}, qty_decay=0.3,
                       outside=1.0, balk=0.0)
    reg, ev = regime_probe(g, ShopState(), b, config={"sku": "cola"},
                           opts=QuoteOpts(quote_lookers=False))
    present = [p for p in ev["probes"] if p["reservation"] is not None]
    assert len(present) < 2
    assert reg == "capacity" and ev["insufficient_probe"] is True


# ── (finding 6) key policy: deployed env refuses an ephemeral fallback ───────
def test_key_policy_refuses_ephemeral_in_deployed_env(monkeypatch):
    monkeypatch.delenv("NOTARY_KEY_PEM", raising=False)
    monkeypatch.setenv("FLY_APP_NAME", "snhp-notary-test")
    with pytest.raises(RuntimeError):
        load_notary_key(refresh=True)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    # SNHP_REQUIRE_PERSISTENT_KEY does the same
    monkeypatch.setenv("SNHP_REQUIRE_PERSISTENT_KEY", "1")
    with pytest.raises(RuntimeError):
        load_notary_key(refresh=True)
    monkeypatch.delenv("SNHP_REQUIRE_PERSISTENT_KEY", raising=False)
    # outside a deployed env the ephemeral fallback still works
    k = load_notary_key(refresh=True)
    assert k.key_source == "ephemeral"


# ── (finding 5) honest ledger receipts: no fabricated economics ──────────────
def test_ledger_receipt_is_honest_nullable_and_verifies():
    from core.notary import emit_ledger_receipt
    cf = {"sticker_world_total": 10.0, "snhp_world_total": 12.0, "delta": 2.0}
    r = emit_ledger_receipt(cf, quote_ref="day0", venue_id="block", key=KEY,
                            chain_id="s0")
    d = r.to_dict()
    assert d["regime"] == "ledger" and d["reservation_basis"] == "n/a(ledger)"
    # no fabricated economics — the per-quote fields are honestly null
    for f in ("list_price", "quoted_price", "saving", "c_eff", "excess_rent",
              "buffer", "a_prime_ok"):
        assert d[f] is None
    assert d["conditions"]["b"] is None and d["conditions"]["a"] is None
    assert d["conditions"]["c"] is True            # engine version still attested
    res = verify_receipt(d, pubkey_pem=KEY.pubkey_pem)
    assert res["ok"] and res["checks"]["counterfactual"]
    # a malformed ledger counterfactual is rejected at emit
    with pytest.raises(ValueError):
        emit_ledger_receipt({"delta": 1.0}, quote_ref="x", venue_id="b", key=KEY)


# ── (finding 4) chain_id: season boundary null is legal; tamper is not ───────
def test_chain_id_segment_boundary_legal_but_tamper_fails():
    from core.notary import emit_ledger_receipt
    cf = {"sticker_world_total": 1.0, "snhp_world_total": 2.0, "delta": 1.0}
    s0a = emit_ledger_receipt(cf, quote_ref="s0d0", venue_id="b", key=KEY,
                              chain_id="s0")
    s0b = emit_ledger_receipt(cf, quote_ref="s0d1", venue_id="b", key=KEY,
                              chain_id="s0", prev_hash=s0a.digest())
    s1a = emit_ledger_receipt(cf, quote_ref="s1d0", venue_id="b", key=KEY,
                              chain_id="s1", prev_hash=None)   # season rollover
    good = verify_chain([s0a, s0b, s1a], pubkey_pem=KEY.pubkey_pem)
    assert good["ok"] and good["chain_ok"]         # null across a boundary is OK
    # tamper: null a mid-SEGMENT prev_hash without changing chain_id → FAIL
    bad = s0b.to_dict()
    bad["prev_hash"] = None
    res = verify_chain([s0a.to_dict(), bad], pubkey_pem=KEY.pubkey_pem)
    assert not res["chain_ok"]

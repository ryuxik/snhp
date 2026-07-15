"""Notary HTTP surface: GET /v1/notary/key, POST /v1/notary/verify, and the
`attestation` block on /v1/offer/quote.

The load-bearing property: a client can verify a quote's attestation with
ONLY the output of GET /v1/notary/key (no server round-trip needed for the
verdict, no signing key). Hosted JSON menus have no capacity_relief channel
(it needs a live Python fn), so every hosted attestation is regime
"finite_stock" / b=true — the capacity regime is exercised in core's own
tests. The receipt never carries the buyer's raw WTP.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gametheory.server import middleware as _mw
from gametheory.server.http import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    _mw._BUCKETS.clear()


# a small finite-stock menu with a real discount surface (expiring croissants)
BAKERY = {
    "name": "neighborhood bakery",
    "dims": [
        {"id": "item", "kind": "choice", "options": [
            {"id": "croissant", "price_delta": 4.25, "unit_cost": 0.95,
             "perishable": True, "salvage": 0.15}]},
        {"id": "qty", "kind": "quantity", "qty_cap": 3}],
    "cost": ["const", "salvage_on_expiry"]}
BAKERY_BUYER = {"values": {"item": {"croissant": 6.0}}, "qty_decay": 0.9,
                "outside": 0.4}
EXPIRING = {"expiring": ["croissant"]}


def _quote(**over):
    body = {"spec": BAKERY, "buyer": BAKERY_BUYER, "state": EXPIRING, **over}
    r = client.post("/v1/offer/quote", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_key_endpoint_shape():
    k = client.get("/v1/notary/key").json()
    assert set(k) == {"pubkey_pem", "pubkey_fpr", "key_source", "algo"}
    assert k["algo"] == "ed25519"
    assert k["key_source"] in ("env", "ephemeral")
    assert "BEGIN PUBLIC KEY" in k["pubkey_pem"]
    assert k["pubkey_fpr"].startswith("sha256:")


def test_quote_carries_attestation():
    out = _quote()
    att = out["attestation"]
    assert att is not None
    # discount-only + regime + honest condition flags
    assert att["quoted_price"] <= att["list_price"]
    assert att["regime"] == "finite_stock"
    assert att["reservation_basis"] == "report_independent(state)"
    assert att["conditions"]["a"] is True          # discount-only held
    assert att["conditions"]["b"] is True          # report-independent (finite)
    assert att["conditions"]["c"] is True          # event-consistent
    assert att["conditions"]["d"] is False         # NO outside-option attestation
    assert att["engine_version"]
    # the raw WTP never rides along — only the one-way disclosure digest
    assert "utilities" not in str(att)
    assert "6.0" not in att["disclosure_digest"]


def test_client_verifies_attestation_with_only_the_key_endpoint():
    """The whole point: fetch GET /v1/notary/key once, then verify offline."""
    key = client.get("/v1/notary/key").json()
    att = _quote()["attestation"]
    # POST /v1/notary/verify is a convenience, but we pass the key from /key to
    # prove the verdict depends only on the published public key.
    res = client.post("/v1/notary/verify",
                      json={"receipts": [att], "pubkey_pem": key["pubkey_pem"]}).json()
    assert res["ok"] and res["chain_ok"]
    assert all(res["results"][0]["checks"].values())
    # the fingerprint on the receipt matches the published key
    assert att["pubkey_fpr"] == key["pubkey_fpr"]


def test_verify_rejects_tampered_attestation():
    att = _quote()["attestation"]
    att = {**att, "quoted_price": 0.01}            # a lie: much cheaper
    res = client.post("/v1/notary/verify", json=att).json()
    assert not res["ok"]
    assert not res["results"][0]["ok"]


def test_verify_accepts_single_list_and_wrapper():
    att = _quote()["attestation"]
    for body in (att, [att], {"receipts": [att]}):
        res = client.post("/v1/notary/verify", json=body).json()
        assert res["ok"], body
        assert res["n"] == 1


def test_verify_bad_body_is_422():
    assert client.post("/v1/notary/verify", json="nope").status_code == 422
    assert client.post("/v1/notary/verify", json=[]).status_code == 422
    assert client.post("/v1/notary/verify", json=["not-an-object"]).status_code == 422


def test_verify_deeply_nested_body_is_422_not_500():
    """A pathologically deep body must return a friendly 422, never a 500 from
    an uncaught RecursionError. Sent as a raw string so the CLIENT doesn't
    overflow serializing it."""
    deep = "[" * 20000 + "]" * 20000
    r = client.post("/v1/notary/verify", content=deep,
                    headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_walk_has_null_attestation():
    # a buyer whose best order never beats their outside option → a walk
    out = _quote(buyer={"values": {"item": {"croissant": 0.1}}, "outside": 50.0},
                 opts={"quote_lookers": False})
    assert out["outcome"] == "walk"
    assert out["quote"] is None
    assert out["attestation"] is None


def test_never_above_list_holds_in_attestation():
    """The discount-only promise is visible AND signed on the attestation."""
    out = _quote()
    q, att = out["quote"], out["attestation"]
    assert att["quoted_price"] <= att["list_price"] + 1e-9
    assert abs(att["saving"] - (att["list_price"] - att["quoted_price"])) < 1e-6
    assert att["quoted_price"] == pytest.approx(q["price"], abs=1e-9)


# ── (finding 2) regime cache: buyer-independent, keyed on state VALUES, LRU ──
def test_regime_is_buyer_independent_on_the_same_spec_state():
    """The regime is a property of (spec, state), not of the caller's WTP: two
    buyers with wildly different valuations get the SAME regime."""
    a = _quote(buyer={"values": {"item": {"croissant": 6.0}}, "outside": 0.4})
    b = _quote(buyer={"values": {"item": {"croissant": 99.0}}, "outside": 40.0})
    assert (a["attestation"]["regime"] == b["attestation"]["regime"]
            == "finite_stock")


def test_regime_cache_keys_on_state_values_not_just_keys():
    """The old under-keying digested sorted(inventory) = KEYS ONLY, so two
    states differing only in inventory VALUES collided. They must now be
    separate cache entries."""
    from core.api import build_graph
    from core.engine import QuoteOpts
    from core.state import ShopState
    from gametheory.server import offer_api as oa
    oa._REGIME_CACHE.clear()
    g = build_graph(BAKERY)
    st1 = ShopState(inventory={"croissant": 1.0})
    st2 = ShopState(inventory={"croissant": 9.0})   # same KEY, different VALUE
    oa._regime_for(g, st1, {}, QuoteOpts(), BAKERY)
    oa._regime_for(g, st2, {}, QuoteOpts(), BAKERY)
    assert len(oa._REGIME_CACHE) == 2
    # a repeat is a cache HIT (no new entry)
    oa._regime_for(g, st1, {}, QuoteOpts(), BAKERY)
    assert len(oa._REGIME_CACHE) == 2


def test_regime_cache_evicts_past_the_cap():
    from core.api import build_graph
    from core.engine import QuoteOpts
    from core.state import ShopState
    from gametheory.server import offer_api as oa
    oa._REGIME_CACHE.clear()
    g = build_graph(BAKERY)
    first_key = None
    for i in range(oa._REGIME_CACHE_MAX + 8):
        st = ShopState(inventory={"croissant": float(i)})
        oa._regime_for(g, st, {}, QuoteOpts(), BAKERY)
        if i == 0:
            first_key = next(iter(oa._REGIME_CACHE))
    assert len(oa._REGIME_CACHE) == oa._REGIME_CACHE_MAX   # bounded
    assert first_key not in oa._REGIME_CACHE               # LRU evicted the oldest

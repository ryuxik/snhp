"""
End-to-end tests for the agent-to-agent commerce stack:
  - operator registry (identity + signed attestations)
  - verified-peer handshake -> server-derived peer_mode
  - next_offer using the session's peer_mode (NOT a client boolean)
  - AP2 settlement mandates
  - A2A agent-card discovery

The security-critical property: a client cannot obtain the cooperation premium
by asserting peer status — peer_mode is derived from a verified handshake, and a
forged/unregistered/replayed proof yields peer_mode=False.

Run: python -m pytest gametheory/tests/test_a2a_commerce.py -v
"""
import base64
import os
import sys
import tempfile
import time

import pytest

# Temp DB before importing the app (mirrors test_sprint3).
_tmp = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp, "a2a_test.db")

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "snhp"))
from snhp_protocol import generate_node_keypair  # noqa: E402

from gametheory.server.http import app  # noqa: E402
from gametheory.server import registry as reg  # noqa: E402
from gametheory.server import peering  # noqa: E402
from gametheory.server import settlement  # noqa: E402

client = TestClient(app)


def _new_operator(op_id):
    priv, pub = generate_node_keypair()
    r = reg.register_operator(op_id, base64.b64encode(pub).decode())
    return priv, pub, r["operator_attestation_jwt"]


# ─── Discovery: the A2A flow must be legible on the agent-facing surfaces ─────

def test_catalog_exposes_a2a_flow():
    cat = client.get("/v1/catalog").json()
    assert "a2a_flow" in cat
    assert len(cat["a2a_flow"]["steps"]) == 6
    assert cat["a2a_flow"]["guide"].endswith("A2A_FLOW.md")


def test_agent_card_has_ordered_flow():
    ext = client.get("/.well-known/agent-card.json").json()["capabilities"]["extensions"][0]
    steps = [s["step"] for s in ext["flow"]]
    assert steps == [0, 1, 2, 3, 4, 5]


def test_catalog_exposes_pricing_and_sla():
    cat = client.get("/v1/catalog").json()
    assert len(cat["pricing"]["tiers"]) == 3
    assert cat["pricing"]["tiers"][0]["price"] == "free"        # core math is free
    assert cat["pricing"]["tiers"][1]["default_enabled"] is False  # LLM tier off by default
    assert cat["sla"]["uptime_guarantee"] is None               # honest: no SLA today
    assert cat["sla"]["self_hostable"] is True
    assert client.get("/PRICING.md").status_code == 200


def test_llm_endpoints_off_by_default(monkeypatch):
    """LLM-backed endpoints must be opt-in (no API-budget exposure on a fresh deploy);
    the free math tools must be unaffected."""
    monkeypatch.delenv("SNHP_ENABLE_DISPUTE_LLM", raising=False)
    r = client.post("/v1/dispute/coach", json={
        "dispute": {}, "customer_floor": 100, "platform_offers": [],
        "customer_demands": [], "platform_last_message": "", "deadline_rounds": 5})
    assert r.status_code == 503 and "disabled" in r.text.lower()
    # math tool still works with no key / no opt-in
    assert client.post("/v1/negotiate/turn", json={
        "side": "sell", "walk_away": 4000, "target": 6000,
        "counterparty_offers": [4200, 4500], "rounds_left": 6}).status_code == 200


# ─── Registry ────────────────────────────────────────────────────────────────

def test_register_and_verify_operator():
    priv, pub, jwt_tok = _new_operator("op.alpha")
    claims = reg.verify_operator_attestation(jwt_tok)
    assert claims["operator_id"] == "op.alpha"
    assert claims["public_key_b64"] == base64.b64encode(pub).decode()


def test_register_rejects_bad_pubkey():
    with pytest.raises(reg.OperatorError):
        reg.register_operator("op.bad", "not-base64!!")
    with pytest.raises(reg.OperatorError):
        reg.register_operator("op.short", base64.b64encode(b"tooshort").decode())


def test_revoked_operator_is_flagged():
    _new_operator("op.revoke")
    assert reg.is_revoked("op.revoke") is False
    assert reg.revoke_operator("op.revoke") is True
    assert reg.is_revoked("op.revoke") is True


# ─── Peer proof verification (the spoof-resistance) ──────────────────────────

def test_valid_peer_proof_verifies():
    priv, pub, jwt_tok = _new_operator("op.legit")
    proof = peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id="op.legit",
        negotiation_id="neg1", role="seller", private_key_bytes=priv)
    ok, op, reason = peering.verify_peer_proof(proof, "neg1", "seller")
    assert ok and op == "op.legit" and reason == "verified"


def test_unknown_require_level_fails_closed():
    # A typo'd require_level must NOT default to the weakest gate — fail closed.
    ok, _, reason = peering.verify_peer_proof({}, "neg1", "seller", require_level="domain ")
    assert ok is False
    assert "unknown require_level" in reason


def test_forged_attestation_rejected():
    # an attacker can't forge a trust-anchor-signed JWT (role/expiry present so we
    # reach the attestation check)
    proof = {"operator_attestation_jwt": "not.a.jwt", "sig_b64": "AAAA",
             "role": "seller", "expires_at": int(time.time()) + 60}
    ok, _, reason = peering.verify_peer_proof(proof, "neg1", "seller")
    assert not ok and "invalid operator attestation" in reason


def test_replayed_proof_to_other_negotiation_rejected():
    priv, pub, jwt_tok = _new_operator("op.replay")
    proof = peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id="op.replay",
        negotiation_id="neg-A", role="seller", private_key_bytes=priv)
    ok, _, reason = peering.verify_peer_proof(proof, "neg-B", "seller")  # other session
    assert not ok and "signature" in reason


def test_proof_role_replay_rejected():
    """A proof signed for the seller role can't be replayed as the buyer (fix #2)."""
    priv, pub, jwt_tok = _new_operator("op.rolereplay")
    seller_proof = peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id="op.rolereplay",
        negotiation_id="negR", role="seller", private_key_bytes=priv)
    ok, _, reason = peering.verify_peer_proof(seller_proof, "negR", "buyer")
    assert not ok and "role" in reason


def test_expired_proof_rejected():
    priv, pub, jwt_tok = _new_operator("op.expired")
    proof = peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id="op.expired",
        negotiation_id="negE", role="seller", private_key_bytes=priv, ttl_seconds=-1)
    ok, _, reason = peering.verify_peer_proof(proof, "negE", "seller")
    assert not ok and "expired" in reason


def test_revoked_operator_proof_rejected():
    priv, pub, jwt_tok = _new_operator("op.revoked2")
    reg.revoke_operator("op.revoked2")
    proof = peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id="op.revoked2",
        negotiation_id="neg1", role="seller", private_key_bytes=priv)
    ok, _, reason = peering.verify_peer_proof(proof, "neg1", "seller")
    assert not ok and "revoked" in reason


# ─── Registry hardening (fix #1) ─────────────────────────────────────────────

def test_revoked_operator_cannot_reregister():
    _new_operator("op.sticky")
    assert reg.revoke_operator("op.sticky") is True
    with pytest.raises(reg.OperatorError):  # re-register must NOT un-revoke
        _new_operator("op.sticky")
    assert reg.is_revoked("op.sticky") is True


def test_cannot_hijack_operator_with_different_key():
    _, pubA = generate_node_keypair()
    _, pubB = generate_node_keypair()
    reg.register_operator("op.hijack", base64.b64encode(pubA).decode())
    with pytest.raises(reg.OperatorError):  # self-path can't overwrite the key
        reg.register_operator("op.hijack", base64.b64encode(pubB).decode())


def test_self_register_does_not_downgrade_domain(monkeypatch):
    priv, pub = generate_node_keypair()
    pub_b64 = base64.b64encode(pub).decode()
    rec = reg.request_domain_challenge("nodowngrade.example", pub_b64)["record_value"]
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [rec])
    assert reg.verify_domain_and_register("nodowngrade.example", pub_b64)["verification_level"] == "domain"
    # a self-level re-register with the SAME key must keep domain, not downgrade
    out = reg.register_operator("nodowngrade.example", pub_b64)  # default level "self"
    assert out["verification_level"] == "domain"


# ─── Sessions: server-derived peer_mode ──────────────────────────────────────

def _proof(op_id, neg_id, role):
    priv, pub, jwt_tok = _new_operator(op_id)
    return peering.build_peer_proof(
        operator_attestation_jwt=jwt_tok, operator_id=op_id,
        negotiation_id=neg_id, role=role, private_key_bytes=priv)


def test_open_session_both_verified_sets_peer_mode():
    neg = "deal-1"
    res = peering.open_session(
        negotiation_id=neg,
        seller_proof=_proof("op.seller1", neg, "seller"),
        buyer_proof=_proof("op.buyer1", neg, "buyer"))
    assert res["peer_mode"] is True
    assert res["seller"]["verified"] and res["buyer"]["verified"]
    assert peering.get_session(res["session_id"])["peer_mode"] is True


def test_open_session_one_spoofer_denies_peer_mode():
    neg = "deal-2"
    bad = {"operator_attestation_jwt": "forged", "sig_b64": "AAAA"}
    res = peering.open_session(
        negotiation_id=neg, seller_proof=_proof("op.seller2", neg, "seller"),
        buyer_proof=bad)
    assert res["peer_mode"] is False
    assert res["buyer"]["verified"] is False


def test_self_deal_denied_peer_mode():
    """One operator supplying both proofs must NOT get peer_mode (fix #3)."""
    neg = "deal-self"
    priv, pub, jwt_tok = _new_operator("op.selfdealer")
    s = peering.build_peer_proof(operator_attestation_jwt=jwt_tok,
        operator_id="op.selfdealer", negotiation_id=neg, role="seller",
        private_key_bytes=priv)
    b = peering.build_peer_proof(operator_attestation_jwt=jwt_tok,
        operator_id="op.selfdealer", negotiation_id=neg, role="buyer",
        private_key_bytes=priv)
    res = peering.open_session(negotiation_id=neg, seller_proof=s, buyer_proof=b)
    assert res["peer_mode"] is False
    assert res["self_deal"] is True


# ─── Endpoints (TestClient): the full product path ───────────────────────────

def _register_via_api(op_id):
    priv, pub = generate_node_keypair()
    r = client.post("/v1/registry/register_operator",
                    json={"operator_id": op_id,
                          "public_key_b64": base64.b64encode(pub).decode()})
    assert r.status_code == 200
    return priv, r.json()["operator_attestation_jwt"]


def test_full_verified_flow_unlocks_peer_mode_via_api():
    neg = "api-deal-1"
    s_priv, s_jwt = _register_via_api("op.api.seller")
    b_priv, b_jwt = _register_via_api("op.api.buyer")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.api.seller", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    b_proof = peering.build_peer_proof(operator_attestation_jwt=b_jwt,
        operator_id="op.api.buyer", negotiation_id=neg, role="buyer",
        private_key_bytes=b_priv)

    r = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof, "buyer_proof": b_proof})
    assert r.status_code == 200
    sess = r.json()
    assert sess["peer_mode"] is True
    sid = sess["session_id"]

    r2 = client.post("/v1/a2a/next_offer", json={
        "session_id": sid, "role": "seller", "my_reservation": 0.2,
        "opponent_offer_history": [0.4], "my_offer_history": [0.9],
        "deadline_rounds": 10})
    assert r2.status_code == 200
    body = r2.json()
    assert body["peer_mode"] is True
    assert body["recommendation"].get("peer_mode") is True   # cooperative path taken


def test_cannot_buy_peer_mode_by_lying():
    """A client with a forged buyer proof cannot get peer_mode — the negative
    control proving the moat can't be claimed without verification."""
    neg = "api-deal-2"
    s_priv, s_jwt = _register_via_api("op.api.seller2")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.api.seller2", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    forged = {"operator_attestation_jwt": "forged.jwt.x", "sig_b64": "AAAA"}

    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof,
        "buyer_proof": forged}).json()["session_id"]
    body = client.post("/v1/a2a/next_offer", json={
        "session_id": sid, "role": "seller", "my_reservation": 0.2,
        "opponent_offer_history": [0.4], "my_offer_history": [0.9],
        "deadline_rounds": 10}).json()
    assert body["peer_mode"] is False
    assert body["recommendation"].get("peer_mode") is not True


def test_settlement_mandates_verify():
    neg = "api-deal-3"
    s_priv, s_jwt = _register_via_api("op.api.s3")
    b_priv, b_jwt = _register_via_api("op.api.b3")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.api.s3", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    b_proof = peering.build_peer_proof(operator_attestation_jwt=b_jwt,
        operator_id="op.api.b3", negotiation_id=neg, role="buyer",
        private_key_bytes=b_priv)
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof,
        "buyer_proof": b_proof}).json()["session_id"]

    r = client.post("/v1/a2a/settle", json={
        "session_id": sid, "agreed_price": 100.0, "item": "widget",
        "buyer_max_price": 120.0})
    assert r.status_code == 200
    out = r.json()
    # cart mandate is permanent (no expiry) — verifiable indefinitely (fix #4)
    assert out["cart_mandate"]["expires_at_iso"] is None
    cart_vc = settlement.verify_mandate(out["cart_mandate"]["mandate_jwt"],
                                        settlement.CART_MANDATE_KIND)
    assert cart_vc["credentialSubject"]["cart"]["agreed_price"] == 100.0
    intent_vc = settlement.verify_mandate(out["intent_mandate"]["mandate_jwt"],
                                          settlement.INTENT_MANDATE_KIND)
    assert intent_vc["credentialSubject"]["constraint"]["max_price"] == 120.0


def test_settlement_key_separated_from_registry_ca():
    """The AP2 settlement notary key must be DISTINCT from the registry-CA trust
    anchor, so a settlement-key compromise can't forge operator identities."""
    import jwt as _jwt
    from gametheory.crypto.first_strike import (
        trust_anchor_public_key_pem, settlement_notary_public_key_pem)
    assert trust_anchor_public_key_pem() != settlement_notary_public_key_pem()
    out = settlement.emit_cart_mandate(
        session_id="s", negotiation_id="n", seller_operator="a",
        buyer_operator="b", agreed_price=50.0)
    settlement.verify_mandate(out["mandate_jwt"])  # ok via the notary key
    with pytest.raises(_jwt.InvalidTokenError):       # rejected by the registry-CA key
        _jwt.decode(out["mandate_jwt"], trust_anchor_public_key_pem().encode(),
                    algorithms=["EdDSA"], audience=settlement._AUD, issuer=settlement._ISS)


def test_verify_mandate_enforces_kind():
    """A Cart Mandate must NOT verify when an Intent Mandate is required (fix #7)."""
    out = settlement.emit_cart_mandate(
        session_id="s", negotiation_id="n", seller_operator="a",
        buyer_operator="b", agreed_price=1.0)
    settlement.verify_mandate(out["mandate_jwt"], settlement.CART_MANDATE_KIND)  # ok
    with pytest.raises(Exception):
        settlement.verify_mandate(out["mandate_jwt"], settlement.INTENT_MANDATE_KIND)


def test_settle_rejects_unverified_session():
    """Settling a session whose buyer never verified must be refused (fix #5)."""
    neg = "api-deal-unverified"
    s_priv, s_jwt = _register_via_api("op.api.s4")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.api.s4", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    forged = {"operator_attestation_jwt": "forged", "sig_b64": "AAAA"}
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof,
        "buyer_proof": forged}).json()["session_id"]
    r = client.post("/v1/a2a/settle", json={"session_id": sid, "agreed_price": 10.0})
    assert r.status_code == 409 and "verified" in r.json()["detail"]


def test_settle_rejects_revoked_operator_session():
    """A session whose buyer operator was REVOKED still populates BOTH operator
    fields — operator_id is learned before the revocation check fails — yet has
    peer_mode=False. settle must gate on peer_mode and refuse it: the old
    non-null/distinct gate would have minted a Cart Mandate for an unverified deal.
    """
    neg = "api-deal-revoked"
    s_priv, s_jwt = _register_via_api("op.api.s.rev")
    b_priv, b_jwt = _register_via_api("op.api.b.rev")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.api.s.rev", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    b_proof = peering.build_peer_proof(operator_attestation_jwt=b_jwt,
        operator_id="op.api.b.rev", negotiation_id=neg, role="buyer",
        private_key_bytes=b_priv)
    # Revoke the buyer AFTER its proof is built: the JWT stays well-formed, so
    # verify_peer_proof learns operator_id and then fails on the revocation check.
    assert reg.revoke_operator("op.api.b.rev") is True
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof,
        "buyer_proof": b_proof}).json()["session_id"]
    # Exploit precondition: both operators populated AND distinct, peer_mode False.
    sess = peering.get_session(sid)
    assert sess["peer_mode"] is False
    assert sess["seller_operator"] and sess["buyer_operator"]
    assert sess["seller_operator"] != sess["buyer_operator"]
    r = client.post("/v1/a2a/settle", json={"session_id": sid, "agreed_price": 10.0})
    assert r.status_code == 409 and "verified" in r.json()["detail"]


def test_settle_rejects_below_level_session(monkeypatch):
    """A session whose buyer is BELOW the required verification level also
    populates both operator fields (the level check returns operator_id before the
    signature is ever checked) with peer_mode=False — settle must refuse it."""
    neg = "api-deal-belowlevel"
    # Seller is domain-verified; buyer is only self-registered.
    s_priv, s_pub = generate_node_keypair()
    s64 = base64.b64encode(s_pub).decode()
    rec = reg.request_domain_challenge("settle-seller.example", s64)["record_value"]
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [rec])
    s_reg = reg.verify_domain_and_register("settle-seller.example", s64)
    s_proof = peering.build_peer_proof(
        operator_attestation_jwt=s_reg["operator_attestation_jwt"],
        operator_id="settle-seller.example", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)
    b_proof = _proof("op.self.settlebuyer", neg, "buyer")  # self level only
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof, "buyer_proof": b_proof,
        "require_level": "domain"}).json()["session_id"]
    sess = peering.get_session(sid)
    assert sess["peer_mode"] is False
    assert sess["seller_operator"] and sess["buyer_operator"]
    assert sess["seller_operator"] != sess["buyer_operator"]
    r = client.post("/v1/a2a/settle", json={"session_id": sid, "agreed_price": 10.0})
    assert r.status_code == 409 and "verified" in r.json()["detail"]


def test_agent_card_advertises_snhp_extension():
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert card["url"].startswith("http")
    ext = card["capabilities"]["extensions"][0]
    assert ext["uri"] == "https://snhp.dev/a2a/negotiation/v1"
    # registries/remote agents need ABSOLUTE endpoint URLs, not relative paths
    assert ext["params"]["open_session"].startswith("http")


def test_agent_card_base_url_is_configurable(monkeypatch):
    import gametheory.server.a2a_routes as ar
    monkeypatch.setenv("SNHP_PUBLIC_BASE_URL", "https://example.test/")
    card = ar.agent_card()
    assert card["url"] == "https://example.test"
    assert card["capabilities"]["extensions"][0]["params"]["settle"] == \
        "https://example.test/v1/a2a/settle"


# ─── Domain-control proof (sybil resistance) ─────────────────────────────────

def test_domain_verification_success_and_failure(monkeypatch):
    priv, pub = generate_node_keypair()
    pub_b64 = base64.b64encode(pub).decode()
    ch = reg.request_domain_challenge("acme.example", pub_b64)
    assert ch["record_name"] == "_snhp-challenge.acme.example"

    # Publish the correct TXT -> verification succeeds at domain level.
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [ch["record_value"]])
    out = reg.verify_domain_and_register("acme.example", pub_b64)
    assert out["operator_id"] == "acme.example"
    assert out["verification_level"] == "domain"
    claims = reg.verify_operator_attestation(out["operator_attestation_jwt"])
    assert claims["verification_level"] == "domain"

    # Missing / wrong record -> rejected.
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: ["snhp-verify=WRONG"])
    with pytest.raises(reg.OperatorError):
        reg.verify_domain_and_register("acme.example", pub_b64)


def test_challenge_token_is_bound_to_pubkey(monkeypatch):
    """A TXT record published for key A must not verify key B (no token reuse)."""
    _, pubA = generate_node_keypair()
    _, pubB = generate_node_keypair()
    a64, b64 = base64.b64encode(pubA).decode(), base64.b64encode(pubB).decode()
    rec_for_A = reg.request_domain_challenge("victim.example", a64)["record_value"]
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [rec_for_A])
    # A verifies; B (different key) does not, even though A's record is published.
    assert reg.verify_domain_and_register("victim.example", a64)["verification_level"] == "domain"
    with pytest.raises(reg.OperatorError):
        reg.verify_domain_and_register("victim.example", b64)


def test_require_domain_level_rejects_self_peer(monkeypatch):
    neg = "deal-domain"
    # seller is domain-verified; buyer is only self-registered.
    s_priv, s_pub = generate_node_keypair()
    s64 = base64.b64encode(s_pub).decode()
    rec = reg.request_domain_challenge("seller.example", s64)["record_value"]
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [rec])
    s_reg = reg.verify_domain_and_register("seller.example", s64)
    s_proof = peering.build_peer_proof(
        operator_attestation_jwt=s_reg["operator_attestation_jwt"],
        operator_id="seller.example", negotiation_id=neg, role="seller",
        private_key_bytes=s_priv)

    b_proof = _proof("op.self.buyer", neg, "buyer")  # self level

    res = peering.open_session(negotiation_id=neg, seller_proof=s_proof,
                              buyer_proof=b_proof, require_level="domain")
    assert res["peer_mode"] is False
    assert res["buyer"]["verified"] is False and "below required" in res["buyer"]["reason"]


# ─── Coverage gaps: validation/error paths + HTTP domain & buyer routes ──────

def test_register_rejects_bad_verification_level():
    _, pub = generate_node_keypair()
    with pytest.raises(reg.OperatorError):
        reg.register_operator("op.lvl", base64.b64encode(pub).decode(),
                              verification_level="platinum")


def test_verify_operator_attestation_rejects_wrong_kind():
    import jwt as jwtlib
    from gametheory.crypto.first_strike import trust_anchor_private_pem
    tok = jwtlib.encode(
        {"iss": "gametheory.dev/registry", "aud": "gametheory.dev/registry/v1",
         "kind": "WRONG_KIND", "operator_id": "x", "pubkey_b64": "y",
         "exp": int(time.time()) + 60},
        trust_anchor_private_pem(), algorithm="EdDSA")
    with pytest.raises(Exception):
        reg.verify_operator_attestation(tok)


def test_request_domain_challenge_rejects_bad_domain():
    _, pub = generate_node_keypair()
    with pytest.raises(reg.OperatorError):
        reg.request_domain_challenge("notadomain", base64.b64encode(pub).decode())


def test_resolve_txt_doh_parses_answers(monkeypatch):
    import io
    import json as _json

    class _FakeResp:
        def __init__(self, payload): self._b = _json.dumps(payload).encode()
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(
        reg.urllib.request, "urlopen",
        lambda *a, **k: _FakeResp({"Answer": [
            {"type": 16, "data": '"snhp-verify=abc123"'},
            {"type": 5, "data": "cname.ignore"}]}))
    out = reg._resolve_txt_doh("_snhp-challenge.x.example")
    assert "snhp-verify=abc123" in out and "cname.ignore" not in out


def test_build_peer_proof_rejects_bad_role():
    priv, _ = generate_node_keypair()
    with pytest.raises(ValueError):
        peering.build_peer_proof(operator_attestation_jwt="x", operator_id="y",
                                 negotiation_id="z", role="boss", private_key_bytes=priv)


def test_verify_peer_proof_malformed_inputs():
    assert peering.verify_peer_proof("notadict", "n", "seller")[0] is False
    ok, _, reason = peering.verify_peer_proof({}, "n", "seller")
    assert not ok and "missing" in reason
    ok, _, reason = peering.verify_peer_proof(
        {"operator_attestation_jwt": "a", "sig_b64": "b", "role": "seller"}, "n", "seller")
    assert not ok and "expires_at" in reason
    ok, _, reason = peering.verify_peer_proof(
        {"operator_attestation_jwt": "a", "sig_b64": "b", "role": "seller",
         "expires_at": int(time.time()) + 999_999}, "n", "seller")
    assert not ok and "far" in reason


def test_get_session_unknown_returns_none():
    assert peering.get_session("no-such-session") is None


def test_http_register_operator_bad_pubkey_returns_400():
    r = client.post("/v1/registry/register_operator",
                    json={"operator_id": "op.http.bad", "public_key_b64": "!!notb64"})
    assert r.status_code == 400


def test_http_domain_challenge_and_verify(monkeypatch):
    _, pub = generate_node_keypair()
    pub_b64 = base64.b64encode(pub).decode()
    ch = client.post("/v1/registry/request_domain_challenge",
                     json={"domain": "httpd.example", "public_key_b64": pub_b64})
    assert ch.status_code == 200
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [ch.json()["record_value"]])
    v = client.post("/v1/registry/verify_domain",
                    json={"domain": "httpd.example", "public_key_b64": pub_b64})
    assert v.status_code == 200 and v.json()["verification_level"] == "domain"
    # missing TXT -> 400
    monkeypatch.setattr(reg, "_RESOLVE_TXT", lambda name: [])
    bad = client.post("/v1/registry/verify_domain",
                      json={"domain": "httpd.example", "public_key_b64": pub_b64})
    assert bad.status_code == 400


def test_http_next_offer_buyer_and_unknown_session():
    # unknown session -> 404
    r = client.post("/v1/a2a/next_offer", json={
        "session_id": "nope", "role": "buyer", "my_reservation": 0.2,
        "opponent_offer_history": [0.4], "my_offer_history": [0.1], "deadline_rounds": 10})
    assert r.status_code == 404
    # buyer branch on a real verified session
    neg = "api-buyer"
    s_priv, s_jwt = _register_via_api("op.bb.s")
    b_priv, b_jwt = _register_via_api("op.bb.b")
    s_proof = peering.build_peer_proof(operator_attestation_jwt=s_jwt,
        operator_id="op.bb.s", negotiation_id=neg, role="seller", private_key_bytes=s_priv)
    b_proof = peering.build_peer_proof(operator_attestation_jwt=b_jwt,
        operator_id="op.bb.b", negotiation_id=neg, role="buyer", private_key_bytes=b_priv)
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s_proof, "buyer_proof": b_proof}).json()["session_id"]
    r2 = client.post("/v1/a2a/next_offer", json={
        "session_id": sid, "role": "buyer", "my_reservation": 0.2,
        "opponent_offer_history": [0.9], "my_offer_history": [0.1], "deadline_rounds": 10})
    assert r2.status_code == 200 and r2.json()["role"] == "buyer"
    assert "recommendation" in r2.json()


def test_http_settle_rejects_self_deal_distinct():
    neg = "api-selfdeal"
    priv, jwt_tok = _register_via_api("op.sd")
    s = peering.build_peer_proof(operator_attestation_jwt=jwt_tok, operator_id="op.sd",
        negotiation_id=neg, role="seller", private_key_bytes=priv)
    b = peering.build_peer_proof(operator_attestation_jwt=jwt_tok, operator_id="op.sd",
        negotiation_id=neg, role="buyer", private_key_bytes=priv)
    sid = client.post("/v1/a2a/open_session", json={
        "negotiation_id": neg, "seller_proof": s, "buyer_proof": b}).json()["session_id"]
    r = client.post("/v1/a2a/settle", json={"session_id": sid, "agreed_price": 5.0})
    assert r.status_code == 409 and "distinct" in r.json()["detail"]


def test_http_settle_unknown_session_404():
    r = client.post("/v1/a2a/settle", json={"session_id": "ghost", "agreed_price": 1.0})
    assert r.status_code == 404


def test_http_domain_challenge_bad_domain_400():
    _, pub = generate_node_keypair()
    r = client.post("/v1/registry/request_domain_challenge",
                    json={"domain": "nodot", "public_key_b64": base64.b64encode(pub).decode()})
    assert r.status_code == 400


def test_http_negotiate_turn_endpoint():
    r = client.post("/v1/negotiate/turn", json={
        "side": "sell", "walk_away": 4000, "target": 6000,
        "counterparty_offers": [4500], "rounds_left": 6})
    assert r.status_code == 200
    b = r.json()
    assert 4000 <= b["recommended_price"] <= 6000 and "$" in b["message"]
    assert b["action"] in ("counter", "accept", "walk")
    # inverted seller frame -> 400
    bad = client.post("/v1/negotiate/turn", json={
        "side": "sell", "walk_away": 6000, "target": 4000, "rounds_left": 6})
    assert bad.status_code == 400


def test_catalog_and_llms_lead_with_flagship():
    cat = client.get("/v1/catalog").json()
    assert cat["tools"][0]["name"] == "gt.negotiate.turn"
    assert cat["tools"][0]["endpoint"] == "POST /v1/negotiate/turn"
    # the flagship example must be in real dollars, not [0,1] utility
    ex = cat["tools"][0]["example_input"]
    assert "side" in ex and ex["walk_away"] >= 100
    llms = client.get("/llms.txt").text
    assert "Quickstart" in llms and llms.index("Quickstart") < llms.index("Empirical anchor")


def test_agent_card_is_task_first_and_legible():
    card = client.get("/.well-known/agent-card.json").json()
    # task-first, not acronym-first
    assert not card["name"].startswith("SNHP")
    assert any(w in card["description"].lower() for w in ("dollar", "price", "negotiat"))
    skills = {s["id"]: s for s in card["skills"]}
    assert "negotiate_turn" in skills
    desc = skills["negotiate_turn"]["description"]
    assert "$" in desc and "/v1/negotiate/turn" in desc and "Don't use" in desc


def test_verify_domain_bad_domain_and_dns_failure(monkeypatch):
    _, pub = generate_node_keypair()
    pb = base64.b64encode(pub).decode()
    with pytest.raises(reg.OperatorError):           # malformed domain
        reg.verify_domain_and_register("nodot", pb)

    def _boom(name):
        raise RuntimeError("dns down")
    monkeypatch.setattr(reg, "_RESOLVE_TXT", _boom)  # resolver error -> OperatorError
    with pytest.raises(reg.OperatorError):
        reg.verify_domain_and_register("dnsfail.example", pb)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

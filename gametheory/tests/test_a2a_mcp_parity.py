"""
MCP-tool parity: the verified A2A commerce flow is reachable over MCP, not just
HTTP, and yields the same server-derived peer_mode (a forged proof can't claim it).

Run: python -m pytest gametheory/tests/test_a2a_mcp_parity.py -v
"""
import asyncio
import base64
import os
import sys
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp, "mcp_parity.db")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "snhp"))
from snhp_protocol import generate_node_keypair  # noqa: E402

from gametheory.server.mcp_server import (  # noqa: E402
    mcp,
    gt_a2a_register_operator, gt_a2a_build_peer_proof, gt_a2a_open_session,
    gt_a2a_next_offer, gt_a2a_settle,
    gt_a2a_request_domain_challenge, gt_a2a_verify_domain, gt_negotiate_turn,
)
from gametheory.server import settlement as _settlement  # noqa: E402
from gametheory.server import registry as _registry  # noqa: E402


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_mcp_exposes_a2a_tools(event_loop):
    names = {t.name for t in event_loop.run_until_complete(mcp.list_tools())}
    for expected in {
        "gt_a2a_register_operator", "gt_a2a_request_domain_challenge",
        "gt_a2a_verify_domain", "gt_a2a_build_peer_proof", "gt_a2a_open_session",
        "gt_a2a_next_offer", "gt_a2a_settle",
    }:
        assert expected in names, f"missing MCP tool {expected}"


def _register(op_id):
    priv, pub = generate_node_keypair()
    out = gt_a2a_register_operator(op_id, base64.b64encode(pub).decode())
    return priv, out["operator_attestation_jwt"]


def test_mcp_verified_flow_matches_http_behavior():
    neg = "mcp-deal-1"
    s_priv, s_jwt = _register("mcp.seller")
    b_priv, b_jwt = _register("mcp.buyer")
    s_proof = gt_a2a_build_peer_proof(s_jwt, "mcp.seller", neg, "seller",
                                      base64.b64encode(s_priv).decode())
    b_proof = gt_a2a_build_peer_proof(b_jwt, "mcp.buyer", neg, "buyer",
                                      base64.b64encode(b_priv).decode())

    sess = gt_a2a_open_session(neg, s_proof, b_proof)
    assert sess["peer_mode"] is True

    rec = gt_a2a_next_offer(sess["session_id"], "seller", 0.2, [0.4], [0.9], 10)
    assert rec["peer_mode"] is True
    assert rec["recommendation"].get("peer_mode") is True

    settled = gt_a2a_settle(sess["session_id"], agreed_price=50.0, item="thing",
                            buyer_max_price=60.0)
    assert _settlement.verify_mandate(
        settled["cart_mandate"]["mandate_jwt"])["credentialSubject"]["cart"]["agreed_price"] == 50.0


def test_mcp_negotiate_turn_works_and_listed(event_loop):
    names = {t.name for t in event_loop.run_until_complete(mcp.list_tools())}
    assert "gt_negotiate_turn" in names
    r = gt_negotiate_turn("sell", 4000.0, 6000.0, [4500.0], None, 6)
    assert 4000.0 <= r["recommended_price"] <= 6000.0 and r["action"] in ("counter", "accept")


def test_mcp_negotiate_turn_description_is_legible(event_loop):
    tools = {t.name: t for t in event_loop.run_until_complete(mcp.list_tools())}
    d = tools["gt_negotiate_turn"].description or ""
    assert "$" in d and "USE THIS WHEN" in d.upper()       # worked example + when-to-use
    # internal jargon must NOT leak into the agent-facing description
    assert "utility space" not in d.lower() and "pareto_knob" not in d.lower()


def test_mcp_domain_tools(monkeypatch):
    """Domain-control proof over MCP (request challenge -> verify)."""
    priv, pub = generate_node_keypair()
    pub_b64 = base64.b64encode(pub).decode()
    ch = gt_a2a_request_domain_challenge("mcpdomain.example", pub_b64)
    assert ch["record_name"] == "_snhp-challenge.mcpdomain.example"
    monkeypatch.setattr(_registry, "_RESOLVE_TXT", lambda name: [ch["record_value"]])
    out = gt_a2a_verify_domain("mcpdomain.example", pub_b64)
    assert out["verification_level"] == "domain"


def test_mcp_settle_rejects_unverified_session():
    neg = "mcp-deal-unverified"
    s_priv, s_jwt = _register("mcp.s.unv")
    s_proof = gt_a2a_build_peer_proof(s_jwt, "mcp.s.unv", neg, "seller",
                                      base64.b64encode(s_priv).decode())
    forged = {"operator_attestation_jwt": "forged", "sig_b64": "AAAA"}
    sess = gt_a2a_open_session(neg, s_proof, forged)
    with pytest.raises(ValueError):
        gt_a2a_settle(sess["session_id"], agreed_price=5.0)


def test_mcp_settle_rejects_revoked_operator_session():
    """The MCP settle path must also gate on peer_mode: a REVOKED buyer populates
    both operator fields (operator_id is known before the revocation check fails)
    yet leaves peer_mode False, so the non-null/distinct gate alone would wrongly
    mint a Cart Mandate."""
    neg = "mcp-deal-revoked"
    s_priv, s_jwt = _register("mcp.s.rev")
    b_priv, b_jwt = _register("mcp.b.rev")
    s = gt_a2a_build_peer_proof(s_jwt, "mcp.s.rev", neg, "seller",
                                base64.b64encode(s_priv).decode())
    b = gt_a2a_build_peer_proof(b_jwt, "mcp.b.rev", neg, "buyer",
                                base64.b64encode(b_priv).decode())
    assert _registry.revoke_operator("mcp.b.rev") is True
    sess = gt_a2a_open_session(neg, s, b)
    # Exploit precondition: both operator ids known + distinct, but peer_mode False.
    assert sess["peer_mode"] is False
    assert sess["seller"]["operator_id"] and sess["buyer"]["operator_id"]
    assert sess["seller"]["operator_id"] != sess["buyer"]["operator_id"]
    with pytest.raises(ValueError):
        gt_a2a_settle(sess["session_id"], agreed_price=5.0)


def test_mcp_next_offer_buyer_branch():
    neg = "mcp-buyer"
    s_priv, s_jwt = _register("mcp.bs")
    b_priv, b_jwt = _register("mcp.bb")
    s = gt_a2a_build_peer_proof(s_jwt, "mcp.bs", neg, "seller", base64.b64encode(s_priv).decode())
    b = gt_a2a_build_peer_proof(b_jwt, "mcp.bb", neg, "buyer", base64.b64encode(b_priv).decode())
    sess = gt_a2a_open_session(neg, s, b)
    rec = gt_a2a_next_offer(sess["session_id"], "buyer", 0.2, [0.9], [0.1], 10)
    assert rec["role"] == "buyer" and "recommendation" in rec


def test_mcp_next_offer_rejects_bad_role():
    """role is validated before anything else, so a casing typo errors out instead
    of silently returning buy-side advice (fix #6)."""
    with pytest.raises(ValueError):
        gt_a2a_next_offer("any-session", "Seller", 0.2, [0.4], [0.9], 10)


def test_mcp_forged_proof_denied_peer_mode():
    neg = "mcp-deal-2"
    s_priv, s_jwt = _register("mcp.seller2")
    s_proof = gt_a2a_build_peer_proof(s_jwt, "mcp.seller2", neg, "seller",
                                      base64.b64encode(s_priv).decode())
    forged = {"operator_attestation_jwt": "forged.x.y", "sig_b64": "AAAA"}
    sess = gt_a2a_open_session(neg, s_proof, forged)
    assert sess["peer_mode"] is False
    rec = gt_a2a_next_offer(sess["session_id"], "seller", 0.2, [0.4], [0.9], 10)
    assert rec["peer_mode"] is False
    assert rec["recommendation"].get("peer_mode") is not True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

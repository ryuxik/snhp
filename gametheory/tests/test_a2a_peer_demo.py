"""
Tests for the A2A verified-peer handshake (gametheory/negotiation/a2a_peer_demo).

The verification logic is security-critical — it's what stops an agent from
stealing the cooperation premium by *claiming* peer status. These tests pin the
four attack vectors it must reject, plus the happy path and the end-to-end
peer_mode derivation.

Run: python -m pytest gametheory/tests/test_a2a_peer_demo.py -v
"""
import base64
import json

from gametheory.negotiation.a2a_peer_demo import (
    Agent, OperatorRegistry, build_attestation_part, verify_peer_message,
    handshake_then_negotiate, generate_node_keypair,
)

NEG = "a2a-test"


def _registry_with(*agents):
    r = OperatorRegistry()
    for a in agents:
        r.register(a.operator_id, a.pub)
    return r


def test_verified_message_passes():
    a = Agent.create("op.legit")
    reg = _registry_with(a)
    ok, reason = verify_peer_message(build_attestation_part(a, NEG), reg, NEG)
    assert ok and reason == "verified"


def test_unregistered_operator_rejected():
    a = Agent.create("op.ghost")
    reg = OperatorRegistry()  # never registered
    ok, reason = verify_peer_message(build_attestation_part(a, NEG), reg, NEG)
    assert not ok and "registry" in reason


def test_tampered_signature_rejected():
    a = Agent.create("op.legit")
    reg = _registry_with(a)
    bad_priv, _ = generate_node_keypair()
    wire = build_attestation_part(a, NEG, sign_with=bad_priv)
    ok, reason = verify_peer_message(wire, reg, NEG)
    assert not ok and "signature" in reason


def test_identity_spoof_rejected():
    """Attacker claims a registered operator's id but presents its own pubkey."""
    victim = Agent.create("op.victim")
    attacker = Agent.create("op.attacker")
    reg = _registry_with(victim)
    part = json.loads(build_attestation_part(attacker, NEG))
    part["operator_id"] = victim.operator_id   # claim the victim's identity
    ok, reason = verify_peer_message(json.dumps(part), reg, NEG)
    assert not ok and ("pubkey" in reason or "registry" in reason)


def test_replay_to_other_negotiation_rejected():
    a = Agent.create("op.legit")
    reg = _registry_with(a)
    wire = build_attestation_part(a, "a2a-OTHER")     # signed for a different session
    ok, reason = verify_peer_message(wire, reg, NEG)
    assert not ok and ("negotiation_id" in reason or "payload" in reason)


def test_malformed_message_rejected():
    reg = OperatorRegistry()
    ok, reason = verify_peer_message("not json{", reg, NEG)
    assert not ok


def test_end_to_end_verified_unlocks_peer_mode():
    reg = OperatorRegistry()
    seller = Agent.create("op.seller")
    buyer = Agent.create("op.buyer")
    reg.register(seller.operator_id, seller.pub)
    reg.register(buyer.operator_id, buyer.pub)
    res = handshake_then_negotiate(seller, buyer, reg, seeds=[42, 43, 44])
    assert res["peer_mode"] is True
    assert res["mean_joint"] > 0


def test_end_to_end_spoofer_denied_peer_mode():
    reg = OperatorRegistry()
    seller = Agent.create("op.seller")
    reg.register(seller.operator_id, seller.pub)
    attacker = Agent.create("op.attacker")  # NOT registered
    res = handshake_then_negotiate(seller, attacker, reg, seeds=[42, 43, 44])
    assert res["peer_mode"] is False
    assert res["seller_verified_buyer"][0] is False


if __name__ == "__main__":
    import sys, pytest
    sys.exit(pytest.main([__file__, "-v"]))

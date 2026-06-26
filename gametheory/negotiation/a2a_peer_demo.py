"""
A2A-carried verified-peer handshake demo — the missing piece for SNHP
agent-to-agent commerce.

WHY THIS EXISTS
The cooperation premium (+7% joint welfare when BOTH sides are verified SNHP
peers) is SNHP's real moat — but in the shipped server `peer_mode` is an
*unverified boolean* the caller passes (gametheory/server/http.py), and the real
cryptographic handshake (snhp/snhp_protocol.py) only works IN-PROCESS (its
attestation channel is a Python dict). So two real agents at two companies can
neither establish nor prove verified peering — the exact gap that left the pitch
with nothing demonstrable. This module closes it: it derives `peer_mode` from a
real, cross-boundary, spoof-resistant attestation exchange, and shows the premium
appears only for genuinely verified peers.

HOW IT MAPS ONTO THE 2026 STANDARDS (so this rides existing rails, not a
standalone protocol nobody routes to):
  - DISCOVERY  — each agent advertises an SNHP A2A *extension*
    (uri "https://snhp.dev/a2a/negotiation/v1") in its
    /.well-known/agent-card.json. Two agents seeing the extension know they both
    speak SNHP. (A2A extensions: declared in the Agent Card, opted into per
    request.)
  - IDENTITY   — the agent's Ed25519 operator key is the signer; in production
    the OperatorRegistry below is the central/staked registry (the deferred moat
    piece) or an A2A signed Agent Card (JWS / EdDSA per RFC 7515).
  - HANDSHAKE  — the SNHP attestation travels as a signed structured-data *Part*
    in the first A2A message. `verify_peer_message` runs on receipt. This is the
    transport-agnostic replacement for snhp_protocol's in-process channel.
  - SESSION    — the A2A task id is the negotiation_id; offers exchange as Parts.
  - SETTLEMENT — the agreed price/terms become an AP2 *Cart Mandate* (signed
    W3C VC); the buyer's first-strike reservation maps to the AP2 *Intent
    Mandate*. SNHP supplies the bargaining brain; AP2 supplies the payment rails.

WHAT'S SIMULATED vs PRODUCTION
  - OperatorRegistry: in-proc dict here -> HTTP registry / staked-node contract.
  - The "wire": we JSON-serialize the attestation and verify the bytes the peer
    would actually receive (so this genuinely crosses a serialization boundary,
    unlike snhp_protocol's shared-memory channel) -> an A2A message Part.
  - The negotiation outcome is driven by the production-faithful simulator
    (_sim.run_matchup) — no re-implemented logic.

Run:
    python gametheory/negotiation/a2a_peer_demo.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, "snhp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from snhp_protocol import (  # noqa: E402  (the REAL Ed25519 primitives)
    generate_node_keypair, sign_attestation, verify_attestation,
    _attestation_payload,
)
from gametheory.negotiation._sim import run_matchup  # noqa: E402


SNHP_A2A_EXTENSION_URI = "https://snhp.dev/a2a/negotiation/v1"


# ─────────────────────────────────────────────────────────────────────────────
# Operator registry (the deferred moat piece). Production: central HTTP service
# or staked-node registry; here an in-proc map of operator_id -> pubkey.
# ─────────────────────────────────────────────────────────────────────────────

class OperatorRegistry:
    def __init__(self):
        self._ops: dict[str, bytes] = {}

    def register(self, operator_id: str, pubkey: bytes) -> None:
        self._ops[operator_id] = pubkey

    def pubkey_of(self, operator_id: str) -> bytes | None:
        return self._ops.get(operator_id)


# ─────────────────────────────────────────────────────────────────────────────
# Agent + A2A-style attestation message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Agent:
    operator_id: str
    node_id: str
    priv: bytes
    pub: bytes

    @classmethod
    def create(cls, operator_id: str) -> "Agent":
        priv, pub = generate_node_keypair()
        return cls(operator_id, f"{operator_id}-node", priv, pub)


def build_attestation_part(agent: Agent, negotiation_id: str, *,
                           sign_with: bytes | None = None) -> str:
    """Build the SNHP A2A extension Part the agent posts in its first message,
    serialized to the JSON string that would travel on the wire. `sign_with`
    lets an attacker sign with the WRONG key (spoof test)."""
    ts_us = 1  # fixed for reproducibility (real flow uses time)
    payload = _attestation_payload(negotiation_id, agent.node_id, ts_us)
    signer = sign_with if sign_with is not None else agent.priv
    sig = sign_attestation(signer, payload)
    part = {
        "a2a_extension": SNHP_A2A_EXTENSION_URI,
        "operator_id": agent.operator_id,
        "node_id": agent.node_id,
        "negotiation_id": negotiation_id,
        "pubkey_b64": base64.b64encode(agent.pub).decode(),
        "payload_b64": base64.b64encode(payload).decode(),
        "sig_b64": base64.b64encode(sig).decode(),
    }
    return json.dumps(part)


def verify_peer_message(wire: str, registry: OperatorRegistry,
                        expected_negotiation_id: str) -> tuple[bool, str]:
    """Verify a received attestation Part. Transport-agnostic (operates on the
    received bytes), so it works across a real network boundary — the fix for
    snhp_protocol's in-process-only channel. All four checks must pass."""
    try:
        part = json.loads(wire)
    except json.JSONDecodeError:
        return False, "malformed message"
    if part.get("a2a_extension") != SNHP_A2A_EXTENSION_URI:
        return False, "not an SNHP-extension message"
    if part.get("negotiation_id") != expected_negotiation_id:
        return False, "negotiation_id mismatch (replay?)"

    registered_pub = registry.pubkey_of(part.get("operator_id", ""))
    if registered_pub is None:
        return False, "operator not in registry (unregistered/unstaked)"

    sent_pub = base64.b64decode(part["pubkey_b64"])
    if sent_pub != registered_pub:
        return False, "pubkey does not match the registry (identity spoof)"

    payload = base64.b64decode(part["payload_b64"])
    sig = base64.b64decode(part["sig_b64"])
    # payload must actually bind this negotiation_id + claimed node_id
    expected_payload = _attestation_payload(expected_negotiation_id,
                                            part.get("node_id", ""), 1)
    if payload != expected_payload:
        return False, "payload does not bind the claimed negotiation/node"
    if not verify_attestation(sent_pub, payload, sig):
        return False, "signature invalid (tampered or wrong key)"
    return True, "verified"


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: exchange attestations -> derive peer_mode -> run negotiation
# ─────────────────────────────────────────────────────────────────────────────

def handshake_then_negotiate(seller: Agent, buyer: Agent, registry: OperatorRegistry,
                             *, seeds: list[int], spoof: str = "none") -> dict:
    """Run the A2A handshake, derive peer_mode from REAL mutual verification,
    then run `len(seeds)` production-faithful matchups. `spoof` injects an
    attack on the buyer's attestation: 'unregistered' | 'bad_signature' | 'none'."""
    neg_id = f"a2a-{seller.operator_id}-{buyer.operator_id}"

    seller_part = build_attestation_part(seller, neg_id)
    if spoof == "bad_signature":
        # attacker tampers: signs with a throwaway key that doesn't match the
        # pubkey in the message, so the signature fails verification.
        bad_priv, _ = generate_node_keypair()
        buyer_part = build_attestation_part(buyer, neg_id, sign_with=bad_priv)
    else:
        buyer_part = build_attestation_part(buyer, neg_id)

    # Each side verifies the OTHER's attestation against the registry.
    seller_ok, seller_reason = verify_peer_message(buyer_part, registry, neg_id)
    buyer_ok, buyer_reason = verify_peer_message(seller_part, registry, neg_id)

    # Cooperation is a NETWORK good: requires BOTH sides verified. A spoofer who
    # can't be verified simply doesn't unlock cooperative play.
    peer_mode = seller_ok and buyer_ok

    joints, u_sellers, u_buyers = [], [], []
    for s in seeds:
        r = run_matchup(seed=s, n_steps=10, scaffold_a="snhp", scaffold_b="snhp",
                        peer_mode=peer_mode)
        joints.append(r.joint)
        u_sellers.append(r.u_a)
        u_buyers.append(r.u_b)
    return {
        "peer_mode": peer_mode,
        "seller_verified_buyer": (seller_ok, seller_reason),
        "buyer_verified_seller": (buyer_ok, buyer_reason),
        "mean_joint": round(float(np.mean(joints)), 4),
        "mean_u_seller": round(float(np.mean(u_sellers)), 4),
        "mean_u_buyer": round(float(np.mean(u_buyers)), 4),
    }


def vanilla_baseline(seeds: list[int]) -> dict:
    joints = [run_matchup(seed=s, n_steps=10, scaffold_a="vanilla",
                          scaffold_b="vanilla", peer_mode=False).joint for s in seeds]
    return {"mean_joint": round(float(np.mean(joints)), 4)}


def _print_report() -> None:
    print("=" * 78)
    print("SNHP × A2A — verified-peer handshake demo (the missing A2A commerce piece)")
    print("=" * 78)
    seeds = list(range(42, 62))

    registry = OperatorRegistry()
    seller = Agent.create("operator.sierra.example")
    buyer = Agent.create("operator.acme.example")
    # Both legit operators register (production: stake / signed Agent Card).
    registry.register(seller.operator_id, seller.pub)
    registry.register(buyer.operator_id, buyer.pub)

    print("\n[1] VERIFIED PEERS — both operators registered, signatures valid")
    v = handshake_then_negotiate(seller, buyer, registry, seeds=seeds)
    print(f"    handshake: seller→buyer {v['seller_verified_buyer']}")
    print(f"               buyer→seller {v['buyer_verified_seller']}")
    print(f"    peer_mode DERIVED = {v['peer_mode']}  | joint welfare = {v['mean_joint']}")

    print("\n[2] SPOOFER — attacker NOT in the registry (no stake/identity)")
    attacker = Agent.create("operator.attacker.example")  # never registered
    s1 = handshake_then_negotiate(seller, attacker, registry, seeds=seeds)
    print(f"    seller→attacker {s1['buyer_verified_seller']}  (seller verifies attacker:"
          f" {s1['seller_verified_buyer']})")
    print(f"    peer_mode DERIVED = {s1['peer_mode']}  | joint welfare = {s1['mean_joint']}")

    print("\n[3] SPOOFER — registered operator, but TAMPERED signature")
    s2 = handshake_then_negotiate(seller, buyer, registry, seeds=seeds, spoof="bad_signature")
    print(f"    seller verifies buyer: {s2['seller_verified_buyer']}")
    print(f"    peer_mode DERIVED = {s2['peer_mode']}  | joint welfare = {s2['mean_joint']}")

    print("\n[4] VANILLA baseline — no SNHP at all")
    base = vanilla_baseline(seeds)
    print(f"    joint welfare = {base['mean_joint']}")

    print("\n" + "-" * 78)
    premium = v["mean_joint"] - s1["mean_joint"]
    print("RESULT")
    print(f"  Verified peers:        joint {v['mean_joint']}  (peer_mode unlocked)")
    print(f"  Spoofer (unregistered):joint {s1['mean_joint']}  (verification FAILED → adversarial)")
    print(f"  Spoofer (bad sig):     joint {s2['mean_joint']}  (verification FAILED → adversarial)")
    print(f"  Vanilla:               joint {base['mean_joint']}")
    print(f"\n  Cooperation premium captured ONLY by genuinely-verified peers: "
          f"+{round(premium, 4)} joint welfare.")
    print("  Spoofers are cryptographically caught at the handshake and get the")
    print("  adversarial outcome — the moat is real AND can't be stolen by claiming")
    print("  peer status. This is the demo the pitch was missing.")


if __name__ == "__main__":
    _print_report()

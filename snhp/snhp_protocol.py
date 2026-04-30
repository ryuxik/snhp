"""
SNHP cryptographic peer-detection protocol — Phase A MVP.

Two SNHP agents prove protocol-compliance to each other by exchanging
Ed25519-signed attestations. When verification succeeds, both agents
flip into cooperation mode (HONEST playbook, full Pareto-search budget,
no exploitation switching). When it fails or the peer is silent, the
agent stays in defensive mode (current Option C behavior).

This module simulates the cryptoeconomic case in-process so the
cooperation lift can be measured before any chain integration. The
production version replaces:
  - `_NODE_REGISTRY`         → on-chain SNHPStakeRegistry contract
  - `_ATTESTATION_CHANNEL`   → on-chain transcript / off-chain p2p
  - `register_node()`        → stake deposit transaction
  - `is_peer_verified()`     → registry membership proof + slashing-condition check

The signing/verification primitives ARE real Ed25519 — only the
message-passing layer is in-process. Swapping to a chain backend
shouldn't require strategy-layer changes.
"""
from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


SNHP_PROTOCOL_VERSION = "v1"


# ─── In-process registry + channel (simulates chain) ────────────────────────


@dataclass(frozen=True)
class NodeRecord:
    node_id: str
    public_key_bytes: bytes  # 32-byte Ed25519 public key
    registered_at: float


@dataclass(frozen=True)
class Attestation:
    node_id: str
    public_key_bytes: bytes
    payload: bytes        # protocol_version || negotiation_id || timestamp
    signature: bytes
    posted_at: float


_REGISTRY_LOCK = threading.RLock()
_NODE_REGISTRY: dict[str, NodeRecord] = {}
# Keyed by negotiation_id so two parallel matchups don't cross-contaminate
# attestations. Each negotiation has its own short-lived attestation list.
_ATTESTATION_CHANNEL: dict[str, list[Attestation]] = {}


def reset_protocol_state() -> None:
    """Clear registry and channel — call between independent test runs to
    prevent attestation leakage across tournaments."""
    with _REGISTRY_LOCK:
        _NODE_REGISTRY.clear()
        _ATTESTATION_CHANNEL.clear()


# ─── Keypair / registration ─────────────────────────────────────────────────


def generate_node_keypair() -> tuple[bytes, bytes]:
    """Returns (private_key_bytes, public_key_bytes). 32 bytes each.
    Production: replace with HSM / wallet-backed key generation."""
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_bytes, pub_bytes


def register_node(node_id: str, public_key_bytes: bytes) -> NodeRecord:
    """Record this node as protocol-compliant. Production: stake deposit
    transaction; the chain enforces uniqueness and binds the stake to
    the pubkey. Locally: just maintains the in-process map."""
    with _REGISTRY_LOCK:
        record = NodeRecord(
            node_id=node_id,
            public_key_bytes=public_key_bytes,
            registered_at=time.time(),
        )
        _NODE_REGISTRY[node_id] = record
        return record


def is_node_registered(node_id: str) -> bool:
    with _REGISTRY_LOCK:
        return node_id in _NODE_REGISTRY


# ─── Sign / verify / publish ────────────────────────────────────────────────


def _attestation_payload(negotiation_id: str, node_id: str,
                          timestamp_us: int) -> bytes:
    """Canonical attestation payload — what the node signs. Includes
    protocol version so a slashing condition can require a current-version
    attestation, and timestamp so attestations can't be replayed across
    negotiations. Deliberately does NOT include issue weights: weight
    disclosure is too much trust + info leakage even between peers.
    Weights are inferred from offers in the negotiation transcript."""
    return (
        f"{SNHP_PROTOCOL_VERSION}|{negotiation_id}|{node_id}|{timestamp_us}"
        .encode("utf-8")
    )


def sign_attestation(private_key_bytes: bytes, payload: bytes) -> bytes:
    priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return priv.sign(payload)


def verify_attestation(public_key_bytes: bytes, payload: bytes,
                        signature: bytes) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub.verify(signature, payload)
        return True
    except InvalidSignature:
        return False
    except ValueError:
        return False


def publish_attestation(negotiation_id: str, attestation: Attestation) -> None:
    """Post an attestation to the in-process channel keyed by
    negotiation_id. Production: emit on-chain event or post to a p2p
    gossip layer scoped to the negotiation session."""
    with _REGISTRY_LOCK:
        _ATTESTATION_CHANNEL.setdefault(negotiation_id, []).append(attestation)


def lookup_peer_attestation(negotiation_id: str,
                              my_node_id: str) -> Optional[Attestation]:
    """Return the most-recent attestation in the channel for this
    negotiation that wasn't posted by me. None if no peer has posted yet
    or if the negotiation channel is empty."""
    with _REGISTRY_LOCK:
        records = _ATTESTATION_CHANNEL.get(negotiation_id, [])
        for a in reversed(records):
            if a.node_id != my_node_id:
                return a
        return None


def is_peer_verified(negotiation_id: str, my_node_id: str) -> bool:
    """Composite check: (1) a peer has posted an attestation in this
    negotiation, (2) the peer's pubkey is in the node registry (= they
    have staked), (3) their signature verifies against the payload they
    claimed to sign. All three must hold."""
    peer = lookup_peer_attestation(negotiation_id, my_node_id)
    if peer is None:
        return False
    with _REGISTRY_LOCK:
        record = _NODE_REGISTRY.get(peer.node_id)
        if record is None:
            return False
        if record.public_key_bytes != peer.public_key_bytes:
            return False
    return verify_attestation(peer.public_key_bytes, peer.payload, peer.signature)


# ─── Convenience: end-to-end attest helper ──────────────────────────────────


def emit_my_attestation(negotiation_id: str, node_id: str,
                         private_key_bytes: bytes,
                         public_key_bytes: bytes) -> Attestation:
    """Sign + publish the local agent's attestation for this negotiation.
    Idempotent within (negotiation_id, node_id) — calling twice posts
    twice, but lookup uses the most-recent record so this is harmless."""
    timestamp_us = int(time.time() * 1_000_000)
    payload = _attestation_payload(negotiation_id, node_id, timestamp_us)
    signature = sign_attestation(private_key_bytes, payload)
    attestation = Attestation(
        node_id=node_id,
        public_key_bytes=public_key_bytes,
        payload=payload,
        signature=signature,
        posted_at=time.time(),
    )
    publish_attestation(negotiation_id, attestation)
    return attestation


def env_disabled() -> bool:
    """Master kill switch — `SNHP_PROTOCOL_DISABLED=1` skips the whole
    flow so baseline tournaments don't pay the verification cost."""
    return os.environ.get("SNHP_PROTOCOL_DISABLED", "").strip() == "1"

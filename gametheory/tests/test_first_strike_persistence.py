"""
Trust-anchor key persistence tests.

The deploy-blocking property: when FIRST_STRIKE_PRIVATE_PEM is set, the
server signs JWTs with that key and exposes the matching public key. A
restart must not change the public key. When the env var is unset, the
server falls back to ephemeral generation (fine for local dev).

These tests reset the module's global cache between cases by reaching
into `gametheory.crypto.first_strike` directly.
"""
import importlib
import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption,
)


def _generate_pem() -> str:
    k = Ed25519PrivateKey.generate()
    return k.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()


def _reset_module():
    """Force the trust-anchor cache to clear so the env-var lookup re-runs."""
    from gametheory.crypto import first_strike
    first_strike._TRUST_ANCHOR_KEY = None
    first_strike._TRUST_ANCHOR_PRIV_PEM = None
    first_strike._TRUST_ANCHOR_PUB_PEM = None
    first_strike._TRUST_ANCHOR_SOURCE = None
    return first_strike


def test_env_pem_is_loaded_and_source_reports_env(monkeypatch):
    pem = _generate_pem()
    monkeypatch.setenv("FIRST_STRIKE_PRIVATE_PEM", pem)
    fs = _reset_module()
    pub_a = fs.trust_anchor_public_key_pem()
    assert fs.trust_anchor_source() == "env"

    # Reset and re-load with the same env: public key must be identical
    # (this is the property a restart needs to preserve).
    fs._TRUST_ANCHOR_KEY = None
    fs._TRUST_ANCHOR_PRIV_PEM = None
    fs._TRUST_ANCHOR_PUB_PEM = None
    fs._TRUST_ANCHOR_SOURCE = None
    pub_b = fs.trust_anchor_public_key_pem()
    assert pub_a == pub_b, "restart with same env-var key must yield same pubkey"


def test_no_env_falls_back_to_ephemeral(monkeypatch):
    monkeypatch.delenv("FIRST_STRIKE_PRIVATE_PEM", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("SNHP_REQUIRE_PERSISTENT_KEY", raising=False)
    fs = _reset_module()
    fs.trust_anchor_public_key_pem()
    assert fs.trust_anchor_source() == "ephemeral"


def test_prod_gate_refuses_ephemeral(monkeypatch):
    """In a deployed env (FLY_APP_NAME set) we refuse to silently fall
    back to ephemeral — that would invalidate every JWT on next restart."""
    monkeypatch.delenv("FIRST_STRIKE_PRIVATE_PEM", raising=False)
    monkeypatch.setenv("FLY_APP_NAME", "snhp")
    fs = _reset_module()
    with pytest.raises(RuntimeError, match="deployed environment"):
        fs.trust_anchor_public_key_pem()


def test_ephemeral_keys_change_across_restarts(monkeypatch):
    """Sanity check: ephemeral path is genuinely non-persistent."""
    monkeypatch.delenv("FIRST_STRIKE_PRIVATE_PEM", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("SNHP_REQUIRE_PERSISTENT_KEY", raising=False)
    fs = _reset_module()
    pub_a = fs.trust_anchor_public_key_pem()
    fs._TRUST_ANCHOR_KEY = None
    fs._TRUST_ANCHOR_PRIV_PEM = None
    fs._TRUST_ANCHOR_PUB_PEM = None
    fs._TRUST_ANCHOR_SOURCE = None
    pub_b = fs.trust_anchor_public_key_pem()
    assert pub_a != pub_b, "ephemeral generation must yield a fresh key"


def test_malformed_env_pem_raises(monkeypatch):
    """Don't silently fall back to ephemeral when PEM env is malformed —
    that would swap the trust anchor unnoticed and invalidate every
    historical attestation."""
    monkeypatch.setenv("FIRST_STRIKE_PRIVATE_PEM", "not a valid PEM")
    fs = _reset_module()
    with pytest.raises(RuntimeError, match="parse as a PEM"):
        fs.trust_anchor_public_key_pem()


def test_health_endpoint_reports_key_source(monkeypatch):
    """Operators check this on first deploy to confirm the env var landed."""
    pem = _generate_pem()
    monkeypatch.setenv("FIRST_STRIKE_PRIVATE_PEM", pem)
    _reset_module()

    # TestClient must be created AFTER we reset the module; otherwise the
    # already-imported `_trust_anchor_source` reference reads stale state.
    from fastapi.testclient import TestClient
    from gametheory.server.http import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["first_strike_key_source"] == "env"

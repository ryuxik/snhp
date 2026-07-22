"""Key rotation, revocation, and the in-flight-credit chain.

Customer paths under test:
  1. self-rotate: new key, wallet carried, old key dead immediately
  2. dead key is indistinguishable from nonexistent (lookup/charge)
  3. rotating an already-rotated key fails (no zombie chains)
  4. Stripe credit landing on a rotated key follows the chain to the
     live descendant (checkout-in-flight-during-rotate race)
  5. founder recovery: agent_id + contact_email must BOTH match
"""
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_rotation.db"))

from gametheory.server.onboarding import (  # noqa: E402
    STARTER_GRANT_MILLICENTS, admin_rotate_by_identity, issue_key, lookup_key,
    rotate_key, wallet_available, wallet_credit,
)
from gametheory.server.billing import charge_or_raise, UnknownKeyError  # noqa: E402


def _key(fund_cents: int = 0) -> tuple[str, str]:
    agent_id = f"rot-{uuid.uuid4().hex[:8]}"
    k = issue_key(agent_id=agent_id, contact_email="owner@example.com",
                  intended_use_summary="rotation tests")["api_key"]
    if fund_cents:
        wallet_credit(k, fund_cents * 1000, bucket="funded")
    return k, agent_id


def test_rotate_carries_wallet_and_kills_old():
    old, _ = _key(fund_cents=750)          # funded 750_000 + starter 50_000
    out = rotate_key(old)
    assert out["replaces"] == old
    assert out["wallet"]["funded_millicents"] == 750_000
    assert out["wallet"]["starter_millicents"] == STARTER_GRANT_MILLICENTS
    new = out["api_key"]
    assert new != old
    before_total = wallet_available(new)["total_millicents"]
    assert before_total == STARTER_GRANT_MILLICENTS + 750_000
    # the old key is GONE — lookup, charge, everything
    assert lookup_key(old) is None
    with pytest.raises(UnknownKeyError):
        charge_or_raise(old, 100)
    # and the new key charges fine — $1 off the carried wallet
    charge_or_raise(new, 100)
    assert wallet_available(new)["total_millicents"] == before_total - 100_000


def test_rotate_twice_fails_second_time():
    old, _ = _key()
    assert rotate_key(old) is not None
    assert rotate_key(old) is None          # already revoked


def test_rotate_unknown_key_returns_none():
    assert rotate_key("gt_never_issued") is None
    assert rotate_key("not_even_prefixed") is None


def test_inflight_credit_follows_rotation_chain():
    """Checkout started with key A; customer rotates A->B, then B->C;
    the webhook credits A. The money must land on C."""
    a, _ = _key()
    b = rotate_key(a)["api_key"]
    c = rotate_key(b)["api_key"]
    wallet_credit(a, 1_000_000, bucket="funded")   # webhook fires with old key
    assert wallet_available(c)["funded_millicents"] == 1_000_000
    assert lookup_key(a) is None and lookup_key(b) is None


def test_admin_recovery_requires_both_identifiers():
    k, agent_id = _key(fund_cents=300)
    # wrong email: no match, nothing rotated
    assert admin_rotate_by_identity(agent_id=agent_id,
                                    contact_email="wrong@example.com") is None
    assert lookup_key(k) is not None
    # both match: rotated, wallet carried
    out = admin_rotate_by_identity(agent_id=agent_id,
                                   contact_email="owner@example.com")
    assert out is not None
    assert out["wallet"]["funded_millicents"] == 300_000
    assert lookup_key(k) is None

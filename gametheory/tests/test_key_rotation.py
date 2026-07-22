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

import gametheory.server.onboarding as _ob  # noqa: E402
from gametheory.server.onboarding import (  # noqa: E402
    STARTER_GRANT_MILLICENTS, admin_rotate_by_identity, issue_key, lookup_key,
    resolve_live_key, rotate_key, wallet_available, wallet_credit,
)
from gametheory.server.billing import charge_or_raise, UnknownKeyError  # noqa: E402


def _insert_key(api_key: str) -> None:
    """Insert a bare `keys` row (no wallet) — for building synthetic chains."""
    with _ob._conn() as c:
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at,
                                  telemetry_consent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (api_key, "chain", "o@example.com", "synthetic chain", "standard",
             600, 1, 0))
        c.commit()


def _revoke_to(api_key: str, replaced_by: str) -> None:
    with _ob._conn() as c:
        c.execute("""INSERT INTO revoked_keys (api_key, revoked_at, replaced_by)
                     VALUES (?, ?, ?)""", (api_key, 1, replaced_by))
        c.commit()


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


def test_resolve_live_key_normal_chain_and_unknown():
    a, _ = _key()
    b = rotate_key(a)["api_key"]
    c = rotate_key(b)["api_key"]
    assert resolve_live_key(a) == c                # walks A->B->C
    assert resolve_live_key(b) == c
    assert resolve_live_key(c) == c                # already live
    assert resolve_live_key("gt_never_issued") is None


def test_credit_refuses_dead_end_chain():
    """replaced_by points to a key that exists NOWHERE: the walk dead-ends, so
    resolve returns None and the credit is refused — money never lands on a
    revoked key (the old walk credited whatever it landed on)."""
    dead = "gt_dead_" + uuid.uuid4().hex
    ghost = "gt_ghost_" + uuid.uuid4().hex         # never inserted anywhere
    _insert_key(dead)
    _revoke_to(dead, ghost)
    assert resolve_live_key(dead) is None
    with pytest.raises(ValueError, match="unknown api_key"):
        wallet_credit(dead, 1000)


def test_credit_refuses_chain_over_hop_cap():
    """A revoked chain longer than the 16-hop cap must NOT credit the (still
    revoked) key the walk stalls on — resolve returns None past the cap."""
    chain = ["gt_hop_%d_%s" % (i, uuid.uuid4().hex) for i in range(18)]
    for k in chain:
        _insert_key(k)
    for i in range(17):                            # k0..k16 revoked → next
        _revoke_to(chain[i], chain[i + 1])         # k17 stays live
    # 17 hops from k0 exceeds the cap → refuse.
    assert resolve_live_key(chain[0]) is None
    with pytest.raises(ValueError, match="unknown api_key"):
        wallet_credit(chain[0], 1000)
    # exactly-16 hops from k1 still resolves to the live tail k17.
    assert resolve_live_key(chain[1]) == chain[17]


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

"""The ONE wallet — grant, availability, settlement debit, credit, refund,
rotation.

The store's single settlement coin (STORE.md §2d, §6). Invariants under test:
  1. the starter grant is one-time and idempotent — issuance grants it once,
     unknown/revoked keys never receive it, a granted key never receives it twice
  2. debit spends starter bucket first, then funded bucket (no cent conversion —
     there is only one wallet now)
  3. a debit larger than the wallet returns the shortfall and NEVER raises —
     the store eats a settlement-race shortfall; only unknown keys raise
  4. credit lands in the funded bucket and follows the rotation chain; refund
     returns a prior debit to the exact buckets it came from
  5. rotation carries both buckets AND the granted flag to the new key
"""
import os
import tempfile
import time
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_wallet.db"))

from gametheory.server import onboarding as _ob  # noqa: E402
from gametheory.server.onboarding import (  # noqa: E402
    MILLICENTS_PER_CENT, STARTER_GRANT_MILLICENTS, issue_key, lookup_key,
    rotate_key, wallet_available, wallet_credit, wallet_debit,
    wallet_grant_starter, wallet_refund,
)


def _key(fund_millicents: int = 0) -> str:
    """A normally-issued key — issuance already granted the 50¢ starter."""
    k = issue_key(agent_id=f"wallet-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="wallet tests")["api_key"]
    if fund_millicents:
        wallet_credit(k, fund_millicents, bucket="funded")
    return k


def _bare_key() -> str:
    """A key with NO wallet row — the pre-change key the fallback grant exists
    for. Inserted directly so the issuance grant does not fire."""
    k = "gt_bare_" + uuid.uuid4().hex
    with _ob._conn() as c:
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at,
                                  telemetry_consent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (k, "bare", "t@example.com", "bare key", "standard", 600,
             int(time.time()), 0))
        c.commit()
    return k


# ─── grant idempotency ───────────────────────────────────────────────────────


def test_issuance_grants_starter_once():
    key = _key()
    # issuance already granted; a second grant is a no-op
    assert wallet_grant_starter(key) is False
    assert wallet_available(key)["starter_millicents"] == STARTER_GRANT_MILLICENTS


def test_bare_key_grant_true_then_false():
    key = _bare_key()                              # no wallet row, never granted
    assert wallet_grant_starter(key) is True
    assert wallet_grant_starter(key) is False      # already granted
    assert wallet_available(key)["starter_millicents"] == STARTER_GRANT_MILLICENTS


def test_grant_unknown_key_false():
    assert wallet_grant_starter("gt_never_issued") is False
    assert wallet_grant_starter("not_even_prefixed") is False


def test_grant_revoked_key_false_and_new_carries_grant():
    key = _key()
    new = rotate_key(key)["api_key"]               # old key now revoked
    assert wallet_grant_starter(key) is False      # revoked → no grant
    # the descendant carried the granted flag, so it is NOT re-granted
    assert wallet_grant_starter(new) is False


# ─── availability ────────────────────────────────────────────────────────────


def test_available_sums_both_buckets():
    key = _key(fund_millicents=7_000)
    a = wallet_available(key)
    assert a["starter_millicents"] == STARTER_GRANT_MILLICENTS
    assert a["funded_millicents"] == 7_000
    assert a["total_millicents"] == STARTER_GRANT_MILLICENTS + 7_000


def test_available_unknown_key_all_zeros():
    a = wallet_available("gt_never_issued")
    assert a == {"starter_millicents": 0, "funded_millicents": 0,
                 "total_millicents": 0}


# ─── debit order ─────────────────────────────────────────────────────────────


def test_debit_spends_starter_first():
    key = _key(fund_millicents=100_000)
    r = wallet_debit(key, 30_000)
    assert r["starter_spent"] == 30_000
    assert r["funded_spent"] == 0
    assert r["shortfall_millicents"] == 0
    assert r["balance_after"] == {
        "starter_millicents": STARTER_GRANT_MILLICENTS - 30_000,
        "funded_millicents": 100_000,
        "total_millicents": STARTER_GRANT_MILLICENTS - 30_000 + 100_000}


def test_debit_spills_into_funded_after_starter():
    key = _key(fund_millicents=100_000)
    r = wallet_debit(key, STARTER_GRANT_MILLICENTS + 10_000)
    assert r["starter_spent"] == STARTER_GRANT_MILLICENTS
    assert r["funded_spent"] == 10_000
    assert r["shortfall_millicents"] == 0
    assert r["balance_after"]["starter_millicents"] == 0
    assert r["balance_after"]["funded_millicents"] == 90_000


# ─── shortfall semantics ─────────────────────────────────────────────────────


def test_debit_beyond_wallet_returns_shortfall_never_raises():
    key = _key()                                   # starter only, no funds
    over = STARTER_GRANT_MILLICENTS + 100_000
    r = wallet_debit(key, over)
    assert r["starter_spent"] == STARTER_GRANT_MILLICENTS
    assert r["funded_spent"] == 0
    assert r["shortfall_millicents"] == 100_000    # store eats this
    assert r["balance_after"]["total_millicents"] == 0
    # spent is never more than the wallet held
    assert wallet_available(key)["total_millicents"] == 0


def test_debit_unknown_key_raises():
    with pytest.raises(ValueError, match="unknown api_key"):
        wallet_debit("gt_never_issued", 100)


# ─── credit (top-ups + the rotation chain) ───────────────────────────────────


def test_credit_lands_in_funded_and_returns_total():
    key = _key()                                   # starter 50_000, funded 0
    total = wallet_credit(key, 1_000 * MILLICENTS_PER_CENT, bucket="funded")
    assert total == STARTER_GRANT_MILLICENTS + 1_000_000
    a = wallet_available(key)
    assert a["funded_millicents"] == 1_000_000
    assert a["starter_millicents"] == STARTER_GRANT_MILLICENTS


def test_credit_rejects_nonpositive_and_unknown():
    key = _key()
    with pytest.raises(ValueError):
        wallet_credit(key, 0)
    with pytest.raises(ValueError, match="unknown api_key"):
        wallet_credit("gt_never_issued", 100)


def test_credit_follows_rotation_chain():
    a = _key()
    b = rotate_key(a)["api_key"]
    c = rotate_key(b)["api_key"]
    wallet_credit(a, 1_000_000, bucket="funded")   # webhook fires with old key
    assert wallet_available(c)["funded_millicents"] == 1_000_000
    assert lookup_key(a) is None and lookup_key(b) is None


# ─── refund (bucket-accurate reversal) ───────────────────────────────────────


def test_refund_returns_to_the_exact_buckets():
    key = _key(fund_millicents=10_000)
    r = wallet_debit(key, STARTER_GRANT_MILLICENTS + 5_000)   # drains starter
    split = {"starter_millicents": r["starter_spent"],
             "funded_millicents": r["funded_spent"]}
    after = wallet_refund(key, split)
    # back to exactly the pre-debit position
    assert after["starter_millicents"] == STARTER_GRANT_MILLICENTS
    assert after["funded_millicents"] == 10_000
    assert after["total_millicents"] == STARTER_GRANT_MILLICENTS + 10_000


def test_refund_unknown_key_raises():
    with pytest.raises(ValueError, match="unknown api_key"):
        wallet_refund("gt_never_issued",
                      {"starter_millicents": 1, "funded_millicents": 0})


# ─── rotation carries the wallet ─────────────────────────────────────────────


def test_rotation_carries_buckets_and_granted_flag():
    key = _key(fund_millicents=10_000)
    wallet_debit(key, 30_000)                      # partly spends the starter
    before = wallet_available(key)

    out = rotate_key(key)
    new = out["api_key"]
    assert out["replaces"] == key
    assert out["wallet"] == before                 # summary of the carried wallet

    after = wallet_available(new)
    assert after == before
    # the old row is zeroed
    old = wallet_available(key)
    assert old["starter_millicents"] == 0 and old["funded_millicents"] == 0
    # rotation must NOT hand out a second starter grant
    assert wallet_grant_starter(new) is False


def test_rotation_of_bare_key_leaves_new_key_eligible():
    key = _bare_key()                              # no wallet row at all
    new = rotate_key(key)["api_key"]
    assert wallet_available(new) == {"starter_millicents": 0,
                                     "funded_millicents": 0,
                                     "total_millicents": 0}
    assert wallet_grant_starter(new) is True       # still eligible


# ─── concurrency: the debit lost-update is closed (Fix 1) ────────────────────


def test_concurrent_debits_never_lose_a_write():
    """N parallel debits of one wallet must debit EXACTLY the balance and leave
    the wallet at zero — no lost update. The old SELECT → compute → absolute
    UPDATE let racers clobber each other (money left behind, spend over-reported);
    the atomic compare-and-swap forbids it. This replaces the deleted
    atomic-deduct concurrency coverage the review flagged."""
    import threading

    key = _key()                                   # starter 50_000
    wallet_credit(key, 50_000, bucket="funded")    # + funded 50_000 = 100_000
    total_start = wallet_available(key)["total_millicents"]
    assert total_start == 100_000

    n = 8
    each = 20_000                                  # 8×20_000 demanded > 100_000
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def worker(i):
        barrier.wait()                             # release together — max race
        results[i] = wallet_debit(key, each)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    spent = sum(r["starter_spent"] + r["funded_spent"] for r in results)
    shortfall = sum(r["shortfall_millicents"] for r in results)
    assert spent == total_start                    # exactly the balance, no more
    assert shortfall == n * each - total_start     # the rest is honest shortfall
    assert wallet_available(key)["total_millicents"] == 0   # nothing lost/left


# ─── idempotent credit: atomic claim+credit, replay-safe (Fix 5) ─────────────


def test_credit_idempotent_credits_once_per_dedup_key():
    key = _key()
    r1 = _ob.wallet_credit_idempotent(key, 5_000, dedup_key="sess_A")
    r2 = _ob.wallet_credit_idempotent(key, 5_000, dedup_key="sess_A")  # replay
    assert r1["duplicate"] is False
    assert r2["duplicate"] is True                 # same purchase → no-op
    assert wallet_available(key)["funded_millicents"] == 5_000   # ONE credit
    # a DIFFERENT dedup key is a distinct purchase → credits again
    _ob.wallet_credit_idempotent(key, 3_000, dedup_key="sess_B")
    assert wallet_available(key)["funded_millicents"] == 8_000


def test_credit_idempotent_atomic_rolls_back_on_failure(monkeypatch):
    """The dedupe-row claim and the wallet mutation are ONE transaction: a
    failure in the mutation must roll back the claim too, so a retry credits."""
    key = _key()
    dedup = "sess_atomic_1"

    def boom(*a, **k):
        raise RuntimeError("mutation failed mid-transaction")

    monkeypatch.setattr(_ob, "_apply_wallet_delta", boom)
    with pytest.raises(RuntimeError, match="mutation failed"):
        _ob.wallet_credit_idempotent(key, 5_000, dedup_key=dedup)
    assert wallet_available(key)["funded_millicents"] == 0
    with _ob._conn() as c:
        row = c.execute("SELECT 1 FROM wallet_credits WHERE dedup_key = ?",
                        (dedup,)).fetchone()
    assert row is None, "a failed credit must not leave a claimed dedupe row"

    monkeypatch.undo()                             # mutation works now
    r1 = _ob.wallet_credit_idempotent(key, 5_000, dedup_key=dedup)
    r2 = _ob.wallet_credit_idempotent(key, 5_000, dedup_key=dedup)
    assert r1["duplicate"] is False and r2["duplicate"] is True
    assert wallet_available(key)["funded_millicents"] == 5_000


def test_credit_idempotent_follows_rotation_chain():
    a = _key()
    b = rotate_key(a)["api_key"]
    _ob.wallet_credit_idempotent(a, 4_000, dedup_key="sess_chain")  # old key
    assert wallet_available(b)["funded_millicents"] == 4_000        # lands on live


# ─── one-time cent-balance backfill (Fix 2) ──────────────────────────────────


def test_migrate_cent_balances_backfills_and_is_idempotent():
    key = _key()                                   # starter granted, funded 0
    # Simulate a legacy nonzero cent balance ($10 test-mode = 1000 cents).
    with _ob._conn() as c:
        c.execute("UPDATE keys SET balance_usd_cents = ? WHERE api_key = ?",
                  (1000, key))
        c.commit()

    r1 = _ob.migrate_cent_balances()
    assert r1["migrated"] == 1
    assert r1["millicents_moved"] == 1000 * MILLICENTS_PER_CENT
    a = wallet_available(key)
    assert a["funded_millicents"] == 1000 * MILLICENTS_PER_CENT     # 1_000_000
    assert a["starter_millicents"] == STARTER_GRANT_MILLICENTS      # untouched
    with _ob._conn() as c:
        v = c.execute("SELECT balance_usd_cents FROM keys WHERE api_key = ?",
                      (key,)).fetchone()[0]
    assert v == 0                                  # cent column zeroed

    # idempotent: a second run moves nothing and does NOT double-credit
    r2 = _ob.migrate_cent_balances()
    assert r2["migrated"] == 0
    assert wallet_available(key)["funded_millicents"] == 1000 * MILLICENTS_PER_CENT

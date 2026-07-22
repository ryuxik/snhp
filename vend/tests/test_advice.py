"""NEXTMOVE Advice invariants — the promises in the launch post, as tests.

Layer-1 of the NEXTMOVE.md test plan:
  1. determinism: same context -> same hash AND same move/price
  2. bounds: a counter never crosses the user's own floor/ceiling
  3. receipt: an Advice without why[] cannot exist
  4. billing: charge-then-refund-on-failure; no charge on invalid input
"""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_advice.db"))

from vend.advice import (  # noqa: E402
    ADVISE_COST_CENTS, Advice, AdviceInvariantError, CATEGORIES,
    advise, advise_charged,
)

_RESALE = dict(category="resale", side="sell", walk_away=170, target=210,
               their_offers=[150, 165], my_offers=[215], rounds_left=4, seed=7)


# ─── determinism ────────────────────────────────────────────────────────────

def test_same_context_same_advice():
    a = advise(**_RESALE)
    b = advise(**_RESALE)
    assert a.context_hash == b.context_hash
    assert (a.move, a.offer) == (b.move, b.offer)
    assert a.engine["compute"]["samples"] == b.engine["compute"]["samples"]
    assert a.engine["compute"]["deterministic"] is True


def test_different_context_different_hash():
    a = advise(**_RESALE)
    b = advise(**{**_RESALE, "walk_away": 171})
    assert a.context_hash != b.context_hash


# ─── bounds ─────────────────────────────────────────────────────────────────

def test_sell_counter_at_or_above_floor():
    a = advise(**_RESALE)
    if a.move == "counter":
        assert a.offer >= 170


def test_buy_counter_at_or_below_ceiling():
    a = advise(category="supply", side="buy", walk_away=5000, target=4200,
               their_offers=[5600, 5350], rounds_left=6, seed=1)
    if a.move == "counter":
        assert a.offer <= 5000


# ─── receipt ────────────────────────────────────────────────────────────────

def test_receipt_mandatory():
    with pytest.raises(AdviceInvariantError):
        Advice(category="resale", side="sell", move="counter", offer=195.0,
               message="x", why=[], confidence_note="", context_hash="h")


def test_receipt_names_user_inputs():
    a = advise(**_RESALE)
    joined = " ".join(a.why)
    assert "you set these" in joined          # belief-honesty: provenance named


# ─── billing (stubbed) ──────────────────────────────────────────────────────

def _key_with_balance(cents: int) -> str:
    import uuid
    from gametheory.server.onboarding import issue_key, wallet_credit
    key = issue_key(agent_id=f"advice-test-{uuid.uuid4().hex[:8]}",
                    contact_email="t@example.com",
                    intended_use_summary="advice tests")["api_key"]
    if cents:
        wallet_credit(key, cents * 1000, bucket="funded")
    return key


def test_charged_path_debits_exactly_once():
    from gametheory.server.onboarding import wallet_available
    key = _key_with_balance(500)
    before = wallet_available(key)["total_millicents"]
    a = advise_charged(api_key=key, **_RESALE)
    assert a.move in ("counter", "accept", "walk", "hold")
    assert wallet_available(key)["total_millicents"] == \
        before - ADVISE_COST_CENTS * 1000


def test_insufficient_balance_no_advice():
    from gametheory.server.billing import InsufficientCreditsError
    key = _key_with_balance(50)         # starter 50_000 + funded 50_000 < $2
    with pytest.raises(InsufficientCreditsError):
        advise_charged(api_key=key, **_RESALE)


def test_invalid_category_rejected_before_charge():
    from gametheory.server.onboarding import wallet_available
    key = _key_with_balance(500)
    before = wallet_available(key)["total_millicents"]
    with pytest.raises(KeyError, match="unknown category"):
        advise_charged(api_key=key, **{**_RESALE, "category": "yachts"})
    assert wallet_available(key)["total_millicents"] == before   # untouched


def test_engine_failure_refunds(monkeypatch):
    from gametheory.server.onboarding import wallet_available
    import vend.advice as mod
    key = _key_with_balance(500)
    before = wallet_available(key)["total_millicents"]

    def boom(**kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(mod, "advise", boom)
    with pytest.raises(RuntimeError, match="engine exploded"):
        advise_charged(api_key=key, **_RESALE)
    # charged, then refunded to the exact buckets → back where it started
    assert wallet_available(key)["total_millicents"] == before

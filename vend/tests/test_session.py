"""Paid negotiation sessions: $2 covers the whole negotiation."""
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_session.db"))
os.environ.setdefault("NEXTMOVE_TELEMETRY_PATH",
                      os.path.join(_tmp, "telemetry.jsonl"))

from vend.session import (  # noqa: E402
    SESSION_MAX_MOVES, SESSION_PRICE_CENTS, SessionError,
    close_session, open_session_charged, session_advise,
)


def _key(fund_cents=1000):
    from gametheory.server.onboarding import issue_key, wallet_credit
    k = issue_key(agent_id=f"sess-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="session tests")["api_key"]
    if fund_cents:
        wallet_credit(k, fund_cents * 1000, bucket="funded")
    return k


_ARGS = dict(category="resale", side="sell", walk_away=170, target=210)


def test_open_charges_once_moves_free():
    from gametheory.server.onboarding import wallet_available
    key = _key(1000)
    before = wallet_available(key)["total_millicents"]      # starter + funded
    charged = SESSION_PRICE_CENTS * 1000                    # $2 in millicents
    sess = open_session_charged(api_key=key, **_ARGS)
    assert wallet_available(key)["total_millicents"] == before - charged
    # the anchor charge rides the ONE wallet: the starter helps fund it, and
    # the session surfaces the split + post-charge balance
    assert (sess["funding"]["starter_millicents"]
            + sess["funding"]["funded_millicents"]) == charged
    assert sess["balance_after"]["total_millicents"] == before - charged
    assert sess["price_millicents"] == charged
    a1, i1 = session_advise(session_id=sess["session_id"], api_key=key,
                            their_offers=[150])
    a2, i2 = session_advise(session_id=sess["session_id"], api_key=key,
                            their_offers=[150, 165], my_offers=[a1.offer])
    assert (i1, i2) == (1, 2)
    # no further charge for moves
    assert wallet_available(key)["total_millicents"] == before - charged


def test_key_mismatch_indistinguishable_from_unknown():
    key, other = _key(500), _key(500)
    sess = open_session_charged(api_key=key, **_ARGS)
    with pytest.raises(SessionError, match="unknown session"):
        session_advise(session_id=sess["session_id"], api_key=other,
                       their_offers=[150])
    with pytest.raises(SessionError, match="unknown session"):
        session_advise(session_id="ns_never_issued", api_key=key,
                       their_offers=[150])


def test_move_cap_enforced():
    key = _key(500)
    sess = open_session_charged(api_key=key, **_ARGS)
    for i in range(SESSION_MAX_MOVES):
        session_advise(session_id=sess["session_id"], api_key=key,
                       their_offers=[150 + i])
    with pytest.raises(SessionError, match="move cap"):
        session_advise(session_id=sess["session_id"], api_key=key,
                       their_offers=[199])


def test_closed_session_rejects_moves():
    key = _key(500)
    sess = open_session_charged(api_key=key, **_ARGS)
    assert close_session(session_id=sess["session_id"], api_key=key) is True
    assert close_session(session_id=sess["session_id"], api_key=key) is False
    with pytest.raises(SessionError, match="closed"):
        session_advise(session_id=sess["session_id"], api_key=key,
                       their_offers=[150])


def test_insufficient_balance_no_session():
    from gametheory.server.billing import InsufficientCreditsError
    key = _key(50)
    with pytest.raises(InsufficientCreditsError):
        open_session_charged(api_key=key, **_ARGS)


def test_invalid_category_rejected_before_charge():
    from gametheory.server.onboarding import wallet_available
    key = _key(500)
    before = wallet_available(key)["total_millicents"]
    with pytest.raises(KeyError, match="unknown category"):
        open_session_charged(api_key=key, category="yachts", side="sell",
                             walk_away=170, target=210)
    assert wallet_available(key)["total_millicents"] == before


def test_moves_deterministic_within_session():
    key = _key(1000)
    s1 = open_session_charged(api_key=key, seed=7, **_ARGS)
    s2 = open_session_charged(api_key=key, seed=7, **_ARGS)
    a1, _ = session_advise(session_id=s1["session_id"], api_key=key,
                           their_offers=[150, 165], rounds_left=4)
    a2, _ = session_advise(session_id=s2["session_id"], api_key=key,
                           their_offers=[150, 165], rounds_left=4)
    assert (a1.offer, a1.context_hash) == (a2.offer, a2.context_hash)


def test_degenerate_bounds_rejected_uncharged():
    # FIX #1: the engine's own validator refuses an unusable session (seller
    # target below floor) BEFORE the $2 charge — no paid-but-unusable session,
    # no 500-loop when the first move finally runs the engine.
    from gametheory.server.onboarding import wallet_available
    from gametheory.negotiation.plain_terms import NegotiationInputError
    key = _key(500)
    before = wallet_available(key)["total_millicents"]
    with pytest.raises(NegotiationInputError):
        open_session_charged(api_key=key, category="resale", side="sell",
                             walk_away=210, target=170)   # target below floor
    assert wallet_available(key)["total_millicents"] == before   # uncharged
    # a valid session still opens and works
    sess = open_session_charged(api_key=key, **_ARGS)
    a, idx = session_advise(session_id=sess["session_id"], api_key=key,
                            their_offers=[150])
    assert idx == 1 and a.move


def test_failed_move_does_not_consume_but_success_does():
    # FIX #2: a move whose engine call raises (rounds_left<1 →
    # NegotiationInputError) must NOT burn a paid move; a successful move
    # consumes exactly one; the cap still blocks the 11th.
    from gametheory.negotiation.plain_terms import NegotiationInputError
    key = _key(500)
    sess = open_session_charged(api_key=key, **_ARGS)
    sid = sess["session_id"]
    with pytest.raises(NegotiationInputError):
        session_advise(session_id=sid, api_key=key, their_offers=[150],
                       rounds_left=0)
    # the failed move consumed nothing: ten good moves are indexed 1..10
    for i in range(SESSION_MAX_MOVES):
        _, idx = session_advise(session_id=sid, api_key=key,
                                their_offers=[150 + i])
        assert idx == i + 1
    with pytest.raises(SessionError, match="move cap"):
        session_advise(session_id=sid, api_key=key, their_offers=[199])


def test_failed_bundle_move_does_not_consume():
    # FIX #2 (bundle path): a bundle move whose engine raises consumes no move.
    from vend.session import session_advise_bundle
    key = _key(500)
    sess = open_session_charged(api_key=key, category="supply", side="buy",
                                walk_away=5000, target=4200)
    sid = sess["session_id"]
    with pytest.raises(Exception):
        session_advise_bundle(session_id=sid, api_key=key, issues=[{"bad": 1}])
    issues = [
        {"name": "price", "options": ["4800", "5000"],
         "my_utility": [1.0, 0.5], "their_utility": [0.3, 1.0]},
        {"name": "delivery", "options": ["2wk", "4wk"],
         "my_utility": [0.9, 0.4], "their_utility": [0.3, 0.9]},
    ]
    _, idx = session_advise_bundle(session_id=sid, api_key=key, issues=issues,
                                   my_batna=0.4)
    assert idx == 1                       # the failed move never counted


def test_rotation_carries_session_and_kills_old_key():
    # FIX #3: rotation carries the paid session to the new key AND kills the old
    # key's access — matching rotate_key's "balance carries" + "old key dies at
    # once" guarantees.
    from gametheory.server.onboarding import rotate_key
    key = _key(500)
    sess = open_session_charged(api_key=key, **_ARGS)
    sid = sess["session_id"]
    new_key = rotate_key(key)["api_key"]
    # (a) the rotated-TO key can drive its paid session
    a, idx = session_advise(session_id=sid, api_key=new_key, their_offers=[150])
    assert idx == 1 and a.move
    # (b) the OLD (now revoked) key cannot — indistinguishable from unknown
    with pytest.raises(SessionError, match="unknown session"):
        session_advise(session_id=sid, api_key=key, their_offers=[150])
    # close honors rotation too: old key can't close, new key can
    assert close_session(session_id=sid, api_key=key) is False
    assert close_session(session_id=sid, api_key=new_key) is True


def test_bundle_move_in_session():
    from vend.session import session_advise_bundle
    key = _key(500)
    sess = open_session_charged(api_key=key, category="supply", side="buy",
                                walk_away=5000, target=4200)
    issues = [
        {"name": "price", "options": ["4800", "5000", "5200"],
         "my_utility": [1.0, 0.6, 0.2], "their_utility": [0.2, 0.6, 1.0]},
        {"name": "delivery", "options": ["2wk", "4wk"],
         "my_utility": [0.9, 0.4], "their_utility": [0.3, 0.9]},
        {"name": "payment", "options": ["net30", "net60"],
         "my_utility": [0.5, 1.0], "their_utility": [1.0, 0.4]},
    ]
    a, idx = session_advise_bundle(session_id=sess["session_id"],
                                   api_key=key, issues=issues,
                                   my_batna=0.4)
    assert idx == 1 and a.side == "bundle"
    assert a.engine.get("package")            # a concrete recommended package
    assert a.why and a.context_hash
    # deterministic: same session params + issues => same hash
    sess2 = open_session_charged(api_key=key, category="supply", side="buy",
                                 walk_away=5000, target=4200)
    b, _ = session_advise_bundle(session_id=sess2["session_id"],
                                 api_key=key, issues=issues, my_batna=0.4)
    assert a.context_hash == b.context_hash
    assert a.engine.get("package") == b.engine.get("package")

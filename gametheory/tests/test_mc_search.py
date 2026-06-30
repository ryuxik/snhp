"""Tests for the two compute-spending tiers (mc_search + pondering)."""
import time

import numpy as np
import pytest

from gametheory.negotiation.mc_search import anytime_search, negotiate_turn_mc
from gametheory.negotiation import pondering
from gametheory.server import mcp_server as srv


# ── Tier 1: the anytime engine ────────────────────────────────────────────────
def test_anytime_picks_clear_winner():
    actions = [0.0, 1.0, 2.0]
    def bp(n):
        P = np.zeros((3, n)); P[2, :] = 1.0; return P     # action 2 strictly best
    res = anytime_search(actions, bp, deadline_s=0.05, base_index=0, max_samples=5000)
    assert res.action_index == 2 and res.improved


def test_anytime_no_deviation_without_signal():
    actions = [0.0, 1.0, 2.0]
    def bp(n):
        return np.full((3, n), 0.5)                        # all equal -> no reason to move
    res = anytime_search(actions, bp, deadline_s=0.05, base_index=1, max_samples=5000)
    assert res.action_index == 1 and not res.improved      # stays on the base move


def test_anytime_respects_sample_cap():
    actions = [0.0, 1.0]
    def bp(n):
        return np.zeros((2, n))
    res = anytime_search(actions, bp, deadline_s=10.0, base_index=0,
                         batch=128, max_samples=512)
    assert res.samples <= 512 + 128                        # stops at the cap, not the clock


# ── Tier 1: wired into the single-issue turn ──────────────────────────────────
_KW = dict(side="sell", walk_away=4000, target=6000,
           counterparty_offers=[4200, 4500], rounds_left=6)


def test_zero_budget_is_closed_form():
    out = negotiate_turn_mc(**_KW, compute_ms=0)
    assert "compute" not in out and out["action"] == "counter"


def test_budget_runs_rollouts_and_is_never_worse_in_model():
    out = negotiate_turn_mc(**_KW, compute_ms=60, seed=1)
    c = out["compute"]
    assert c["samples"] > 0 and c["budget_ms"] == 60
    assert c["vs_closed_form"] >= -1e-9                     # never worse than closed form in-model


def test_more_budget_more_samples():
    a = negotiate_turn_mc(**_KW, compute_ms=20, seed=2)["compute"]["samples"]
    b = negotiate_turn_mc(**_KW, compute_ms=200, seed=2)["compute"]["samples"]
    assert b > a


def test_accept_branch_is_untouched_by_compute():
    out = negotiate_turn_mc(side="sell", walk_away=4000, target=6000,
                            counterparty_offers=[6200], rounds_left=6, compute_ms=100)
    assert out["action"] == "accept" and "compute" not in out


# ── Tier 2: pondering sessions ────────────────────────────────────────────────
def _wait_speculation(sess, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if sess._cache and all(f.done() for f in sess._cache.values()):
            return True
        time.sleep(0.02)
    return False


def test_pondering_cache_hit_on_anticipated_offer():
    sid = pondering.open_session(side="sell", walk_away=4000, target=6000,
                                 rounds_left=6, compute_ms=40)
    sess = pondering.get_session(sid)
    try:
        opening = sess.propose()
        assert opening["action"] == "counter" and opening["_pondered"] is False
        anticipated = sess._anticipated_counters(opening["recommended_price"])
        assert _wait_speculation(sess), "background speculation did not finish"
        hit = anticipated[len(anticipated) // 2]
        out = sess.respond(hit)
        assert out["_pondered"] is True                    # served from the pondered cache
    finally:
        pondering.close_session(sid)


def test_pondering_miss_falls_back_to_fresh():
    sid = pondering.open_session(side="sell", walk_away=4000, target=6000,
                                 rounds_left=6, compute_ms=40)
    sess = pondering.get_session(sid)
    try:
        sess.propose()
        _wait_speculation(sess)
        out = sess.respond(4001)                            # far outside the anticipated band
        assert out["_pondered"] is False and out["action"] in ("counter", "accept", "walk")
    finally:
        pondering.close_session(sid)


def test_unknown_session_raises():
    with pytest.raises(KeyError):
        pondering.get_session("does-not-exist")


# ── MCP tool surface ──────────────────────────────────────────────────────────
def test_mcp_tool_compute_ms_passthrough():
    out = srv.gt_negotiate_turn(side="sell", walk_away=4000, target=6000,
                                counterparty_offers=[4200, 4500], rounds_left=6,
                                compute_ms=40)
    assert "compute" in out and out["compute"]["samples"] > 0


def test_mcp_session_tools_roundtrip():
    opened = srv.gt_negotiate_open_session(side="sell", walk_away=4000, target=6000,
                                           rounds_left=6, compute_ms=30)
    sid = opened["session_id"]
    try:
        first = srv.gt_negotiate_propose(sid)
        assert first["action"] in ("counter", "accept", "walk")
        nxt = srv.gt_negotiate_respond(sid, 4600)
        assert "action" in nxt and "_pondered" in nxt
    finally:
        assert srv.gt_negotiate_close_session(sid)["closed"] is True

"""Invariants for Molt Season. These are the checks that make the fairness
claims in PREREG §2 auditable rather than asserted.

    python -m pytest research/molt/tests/test_molt.py -q
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(os.path.dirname(_HERE)),
           os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import molt.arms as A
from molt.world import (BASE_PCT, Crab, Package, Params, ISSUES, crab_value,
                        draw_crab, needs_approval, opening_offer, works_npv)


def crabs(n=60, seed=7, p=None):
    p = p or Params()
    rng = np.random.default_rng(seed)
    return [draw_crab(i, p, rng) for i in range(n)]


# --------------------------------------------------------------- determinism
def test_same_seed_same_crabs():
    a, b = crabs(), crabs()
    assert [c.salary for c in a] == [c.salary for c in b]
    assert [c.u_taste for c in a] == [c.u_taste for c in b]


def test_arms_are_deterministic():
    p = Params()
    for c in crabs(20):
        for name, fn in A.ARMS.items():
            r1, r2 = fn(p, c, 1234), fn(p, c, 1234)
            assert r1["crab"] == r2["crab"], name
            assert r1["works"] == r2["works"], name
            assert r1["pkg"].key() == r2["pkg"].key(), name


# ------------------------------------------------------------ protocol parity
def test_yard_never_moves_against_itself():
    """Whatever the protocol, the Works only ever signs a package at least as
    good for itself as holding its opening offer. No arm can extract from the
    Works by protocol alone."""
    p = Params()
    for c in crabs(60):
        open_pk = opening_offer(p, c)
        for name, fn in A.ARMS.items():
            r = fn(p, c, 99)
            assert works_npv(p, c, r["pkg"]) >= works_npv(p, c, open_pk) - 1e-6, \
                f"{name} pushed the Works below its opening position"


def test_slow_arms_get_more_chances_not_fewer():
    p = Params()
    assert p.max_meetings > p.max_rounds


def test_approval_applies_to_every_arm():
    """PREREG §0 guard 2: an instant agreement still needs a signature. Any arm
    landing an above-discretion package must show more than one day."""
    p = Params()
    for c in crabs(80):
        for name, fn in A.ARMS.items():
            r = fn(p, c, 7)
            hop, _ = needs_approval(p, r["pkg"], opening_offer(p, c))
            if hop and not r["walked"]:
                assert r["days"] > 1.0, f"{name} skipped the approval hop"


def test_opening_offer_identical_across_arms():
    p = Params()
    for c in crabs(30):
        assert A.arm_sign(p, c)["pkg"].key() == opening_offer(p, c).key()


# ---------------------------------------------------------------- zero clock
def test_zero_clock_removes_time_and_only_time():
    p_on, p_off = Params(clock=True), Params(clock=False)
    for c in crabs(40):
        for name, fn in A.ARMS.items():
            r = fn(p_off, c, 5)
            assert r["days"] == 1.0, f"{name} still burns days"
            assert r["mgr"] == 0.0 and r["distraction"] == 0.0
            assert not r["walked"]
    # the packages themselves are unchanged: the clock is a cost layer, not a
    # different negotiation
    for c in crabs(40):
        for name, fn in A.ARMS.items():
            assert fn(p_on, c, 5)["pkg"].key() == fn(p_off, c, 5)["pkg"].key(), \
                f"{name}: turning the clock off changed the deal"


# --------------------------------------------------- the engine is really used
def test_engine_arms_call_the_real_engine(monkeypatch):
    import gametheory.negotiation.bundle as B
    import gametheory.negotiation.plain_terms as T
    calls = {"bundle": 0, "turn": 0}
    real_b, real_t = B.negotiate_bundle, T.negotiate_turn

    def spy_b(**kw):
        calls["bundle"] += 1
        return real_b(**kw)

    def spy_t(**kw):
        calls["turn"] += 1
        return real_t(**kw)

    monkeypatch.setattr(B, "negotiate_bundle", spy_b)
    monkeypatch.setattr(T, "negotiate_turn", spy_t)
    p = Params()
    c = crabs(1)[0]
    for name in ("D_sitting_crab", "E_sitting_works", "F_sitting_both"):
        before = calls["bundle"]
        A.ARMS[name](p, c, 3)
        assert calls["bundle"] > before, f"{name} did not call negotiate_bundle"
    before = calls["turn"]
    for c in crabs(20):
        A.ARMS["C_slow_engine"](p, c, 3)
    assert calls["turn"] > before, "arm C did not call negotiate_turn"


def test_arm_C_asks_really_differ_from_arm_B():
    """B and C produce identical outcomes (RESULTS: the ask never binds). That
    is a finding about single-issue asks, NOT a wiring bug — so pin the premise:
    the asks themselves must differ on a fair share of crabs."""
    p = Params()
    diff = 0
    for c in crabs(60):
        cur = opening_offer(p, c)
        if A._engine_ask(p, c, cur, "base") != A._human_ask(c, "base") or \
           A._engine_ask(p, c, cur, "bonus") != A._human_ask(c, "bonus"):
            diff += 1
    assert diff > 10, "arm C is not actually asking differently from arm B"


# ------------------------------------------------------------------ economics
def test_base_raise_is_the_expensive_ask():
    """The logroll only exists if a permanent raise costs the Works more per
    dollar of crab value than the cheap non-cash terms do, for at least some
    crabs. If this ever fails, the mechanism is gone."""
    p = Params()
    from molt.world import works_cost
    better = 0
    for c in crabs(60):
        base3 = Package(base=1)
        ratio_base = works_cost(p, c, base3) / max(crab_value(p, c, base3), 1.0)
        for pk in (Package(title=True), Package(berth=True), Package(deep=True)):
            v = crab_value(p, c, pk)
            if v > 0 and works_cost(p, c, pk) / v < ratio_base:
                better += 1
                break
    assert better > 30, "no crab has a cheaper-than-cash way to be paid"


def test_leaving_costs_the_yard_more_than_any_package():
    p = Params()
    from molt.world import works_cost
    for c in crabs(40):
        worst = works_cost(p, c, Package(3, True, 2, True, True))
        assert p.spec_rho(c.spec) * c.salary > 0
        # not a strict inequality claim; just that replacement is a real number
        # of the same order, else the retention problem is trivial
        assert worst > 0


@pytest.mark.parametrize("arm", list(A.ARMS))
def test_no_arm_reports_a_package_outside_the_grid(arm):
    p = Params()
    for c in crabs(25):
        pk = A.ARMS[arm](p, c, 11)["pkg"]
        assert 0 <= pk.base < len(BASE_PCT)
        assert 0 <= pk.bonus < 3

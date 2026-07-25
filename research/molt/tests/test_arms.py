"""AMENDMENT 5 §A5.2 — standing assertions on every arm.

Four instruments died in this study, each flattering whichever side I was
leaning toward. Three would have been caught here. These are the checks, not a
resolution to be more careful.

    python3 -m pytest research/molt/tests/test_arms.py -q
"""
from __future__ import annotations

import copy
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOLT = os.path.dirname(_HERE)
for _p in (os.path.dirname(_MOLT), os.path.dirname(os.path.dirname(_MOLT)),
           os.path.join(os.path.dirname(os.path.dirname(_MOLT)), "snhp"), _MOLT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from molt.arms3 import sitting_crab3, sitting_works3, slow_archetype3
from molt.v2 import draw_crab2
from molt.v3 import Params3, Season, crab_value3, works_npv3

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)


def world(n=25, seed=7):
    p = Params3(**P)
    rng = np.random.default_rng(seed)
    sea = Season.draw(p, rng, 40)
    return p, sea, [draw_crab2(i, p, rng) for i in range(n)]


ARMS = {
    "sitting_crab3": lambda p, c, sea, i: sitting_crab3(p, c, sea, i),
    "sitting_works3": lambda p, c, sea, i: sitting_works3(p, c, sea, i),
    "slow_archetype3": lambda p, c, sea, i: slow_archetype3(
        p, c, sea, "Anchoring Bias", "best_first", np.random.default_rng(i)),
}


@pytest.mark.parametrize("name", list(ARMS))
def test_counterparty_can_refuse(name):
    """THE assertion that would have caught arm G v1 and the probe arm.

    An arm must not be able to hand itself a package the employer never agreed
    to. Operationally: no arm may settle on a package the Works values BELOW its
    own opening position -- if it can, the Works was never consulted."""
    from molt.v2 import prior, update
    from molt.v3 import discloses3
    from molt.world import opening_offer
    p, sea, crabs = world()
    for i, c in enumerate(crabs):
        r = ARMS[name](p, c, copy.deepcopy(sea), i)
        bel = update(p, c, prior(p, c), discloses3(p, c, sea))
        op = opening_offer(p, c)
        assert works_npv3(p, c, sea, bel, r["pkg"]) >= \
            works_npv3(p, c, sea, bel, op) - 1e-6, (
                f"{name} settled a package the Works would refuse -- it was "
                f"never allowed to say no")


@pytest.mark.parametrize("name", list(ARMS))
def test_arm_does_not_always_get_its_own_way(name):
    """A counterparty that accepts everything is not a counterparty. At least
    some crabs must end at something other than the arm's opening ask."""
    p, sea, crabs = world(40)
    from molt.world import opening_offer
    moved = sum(1 for i, c in enumerate(crabs)
                if ARMS[name](p, c, copy.deepcopy(sea), i)["pkg"].key()
                != opening_offer(p, c).key())
    assert 0 < moved < len(crabs), (
        f"{name}: {moved}/{len(crabs)} moved off the opening -- an arm that "
        f"always or never moves is not negotiating")


def test_engine_arms_pass_a_growing_offer_history(monkeypatch):
    """THE assertion that would have caught the single-shot inference in
    run5.engine_inference: an arm that calls the engine across rounds must show
    it a history that grows, or it is not learning from the counters."""
    import gametheory.negotiation.bundle as B
    seen_lengths = []
    real = B.negotiate_bundle

    def spy(**kw):
        seen_lengths.append(len(kw.get("their_offers") or []))
        return real(**kw)

    monkeypatch.setattr(B, "negotiate_bundle", spy)
    p, sea, crabs = world(30)
    for i, c in enumerate(crabs):
        seen_lengths.clear()
        sitting_crab3(p, c, copy.deepcopy(sea), i)
        if len(seen_lengths) > 1:
            assert max(seen_lengths) > min(seen_lengths), (
                "the engine was called repeatedly with the same offer history: "
                "every counter is being discarded")
            return
    pytest.skip("no crab-season exercised more than one engine round")


def test_settle_is_never_handed_an_unnegotiated_package():
    """Arm G v1 built a package and passed it straight to settle3. Guard the
    shape: the arms module must not expose a helper that settles a package
    chosen without any reference to the Works' payoff."""
    import inspect

    import molt.arms3 as A3
    src = inspect.getsource(A3)
    for fn in ("sitting_crab3", "sitting_works3", "slow_archetype3"):
        body = src.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "works_npv3" in body or "works_signs3" in body or \
            "works_best_reply3" in body, (
                f"{fn} settles without ever consulting the Works' payoff")

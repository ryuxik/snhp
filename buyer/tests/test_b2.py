"""B2 tests: the frontier is a real max over the strategy space, regret is >= 0
by construction for every buyer and every arm, and the attested frontier
collapses to the honest report."""
import pytest

from buyer.agent import BuyerAgent
from buyer.frontier import (regret, shop_frontier, single_merchant_frontier)
from buyer.merchant import ToyMerchant, VendMerchant
from buyer.world import (draw_toy_population, draw_vend_population,
                        toy_merchant)


def test_regret_nonnegative_vend():
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40)
    pop = draw_vend_population(20260710, 300)
    for b in pop:
        fr = single_merchant_frontier(b.wtp, b.walk_cost, m)
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost, policy="honest")
        _, realized, _ = agent.negotiate(m)
        assert realized <= fr.surplus + 1e-9         # realized never beats frontier
        assert regret(fr, realized) >= 0.0
        assert fr.surplus >= fr.fallback - 1e-9      # frontier >= walk-away floor


def test_frontier_is_max_of_per_strategy():
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40)
    pop = draw_vend_population(20260710, 100)
    for b in pop:
        fr = single_merchant_frontier(b.wtp, b.walk_cost, m)
        assert abs(fr.surplus - max(fr.per_strategy.values())) < 1e-9


def test_attested_collapses_to_honest():
    # An attested merchant only honors verified truth: the frontier's argmax
    # can never be a misreport, and the attested frontier <= unrestricted one.
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40)
    pop = draw_vend_population(20260710, 200)
    for b in pop:
        fr_open = single_merchant_frontier(b.wtp, b.walk_cost, m, attested=False)
        fr_att = single_merchant_frontier(b.wtp, b.walk_cost, m, attested=True)
        assert fr_att.surplus <= fr_open.surplus + 1e-9
        assert set(fr_att.per_strategy) <= {"walk_or_sticker", "honest"}


def test_attested_merchant_refuses_unverified():
    from buyer.merchant import Disclosure, Intent
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40,
                               attested_only=True)
    pop = draw_vend_population(20260710, 80)
    served_unattested = served_attested = 0
    for b in pop:
        d_lie = Disclosure(wtp={s: v * 0.55 for s, v in b.wtp.items()},
                           walk_cost=0.0, attested=False)
        d_true = Disclosure(wtp=b.wtp, walk_cost=b.walk_cost, attested=True)
        assert m.quote(d_lie, Intent()) is None      # unverified: refused
        served_unattested += 0
        if m.quote(d_true, Intent()) is not None:
            served_attested += 1
    assert served_attested > 0                        # honest+attested is served


def test_toy_path_no_vend():
    # The whole regret machinery runs with zero vend dependency.
    m = toy_merchant("toy", near_expiry_skus=("sandwich",))
    pop = draw_toy_population(1, 100)
    for b in pop:
        fr = single_merchant_frontier(b.wtp, b.walk_cost, m)
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        _, realized, _ = agent.negotiate(m)
        assert regret(fr, realized) >= 0.0

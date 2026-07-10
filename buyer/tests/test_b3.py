"""B3 tests: shop never hurts and its frontier dominates a single merchant's;
time's regret is >= 0 under an imperfect forecast; the markdown state really
does floor perishables at salvage (deep discount)."""
import pytest

from buyer.agent import BuyerAgent
from buyer.frontier import shop_frontier, single_merchant_frontier
from buyer.merchant import Disclosure, Intent
from buyer.strategies import shop, time_strategy
from buyer.world import (draw_vend_population, vend_markdown_merchant,
                        vend_merchants)


def _merchants(seed, m=3):
    specs = [{"id": f"v{i}", "seed_offset": i * 101, "day": 0, "tick": 40,
              "cfg_kwargs": {"sigma_cal": 0.30}} for i in range(m)]
    return vend_merchants(seed, specs)


def test_shop_never_hurts():
    ms = _merchants(20260710)
    pop = draw_vend_population(20260710, 300)
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        _, r0, _ = agent.negotiate(ms[0])
        sr = shop(agent, ms)
        assert sr.realized >= r0 - 1e-9        # querying more can only help


def test_shop_frontier_dominates_single():
    ms = _merchants(20260710)
    pop = draw_vend_population(20260710, 150)
    for b in pop:
        fr_one = single_merchant_frontier(b.wtp, b.walk_cost, ms[0])
        fr_shop = shop_frontier(b.wtp, b.walk_cost, ms)
        assert fr_shop.surplus >= fr_one.surplus - 1e-9


def test_time_regret_nonnegative():
    now_m = vend_merchants(20260710, [{"id": "now"}])[0]
    mk = vend_markdown_merchant(20260710)
    pop = draw_vend_population(20260710, 300)
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        for glut in (True, False):
            tr = time_strategy(agent, now_m, mk, glut_prob=0.15,
                               wait_cost=0.15, glut_happens=glut)
            assert tr.hindsight - tr.realized >= -1e-9   # regret >= 0


def test_markdown_floors_perishables_at_salvage():
    from vend.world import CATALOG_SPEC
    perishables = [s for s, *rest in CATALOG_SPEC if rest[3] <= 3]
    mk = vend_markdown_merchant(20260710)
    now = vend_merchants(20260710, [{"id": "now"}])[0]
    for sku in perishables:
        assert mk.salvage_floor(sku) < now.salvage_floor(sku)  # c_eff dropped


def test_markdown_cheaper_for_perishable_lover():
    mk = vend_markdown_merchant(20260710)
    now = vend_merchants(20260710, [{"id": "now"}])[0]
    # a buyer who only wants the sandwich: markdown must quote it no dearer.
    wtp = {"cola": 0.1, "diet-cola": 0.1, "water": 0.1, "chips": 0.1,
           "candy": 0.1, "energy": 0.1, "sandwich": 6.0, "fruit-cup": 0.1}
    d = Disclosure(wtp=wtp, walk_cost=1.0)
    q_now = now.quote(d, Intent(allowed=frozenset({"sandwich"})))
    q_mk = mk.quote(d, Intent(allowed=frozenset({"sandwich"})))
    assert q_mk is not None
    if q_now is not None:
        assert q_mk.unit_price <= q_now.unit_price + 1e-9

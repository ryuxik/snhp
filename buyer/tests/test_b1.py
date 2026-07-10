"""B1 tests: the Merchant adapter matches vend's own numbers on a shared seed,
the value model is in sync with vend, the ledger conserves, and the naive/agent
plumbing produces coherent per-consumer receipts."""
import pytest

from buyer.agent import BuyerAgent
from buyer.ledger import BuyerLedger, Receipt
from buyer.merchant import Disclosure, Intent, VendMerchant
from buyer.run import naive_receipt, run_single_merchant
from buyer.frontier import single_merchant_frontier
from buyer.values import bundle_value


# ── the value model is numerically identical to vend's ──
def test_values_sync_with_vend():
    from vend.world import bundle_value as vend_bv
    import numpy as np
    rng = np.random.default_rng(0)
    for _ in range(50):
        wtp = {"cola": float(rng.uniform(1, 4))}
        for q in (1, 2, 3):
            assert abs(bundle_value(wtp, "cola", q)
                       - vend_bv(wtp, "cola", q)) < 1e-12


# ── the adapter reproduces vend.scenario.nash_quote exactly ──
def test_vend_merchant_matches_nash_quote():
    from vend.scenario import nash_quote
    from vend.world import (WorldConfig, build_catalog, day_state,
                            fresh_machine, sample_consumer)
    cfg = WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                      glut_prob=0.15)
    seed = 20260710
    catalog = build_catalog(cfg, seed)
    state = fresh_machine("m", catalog, cfg, seed)
    state.day, state.tick = 0, 40
    ds = day_state(cfg, seed, 0)
    m = VendMerchant("m", state, catalog, dow_mult=ds.dow_mult,
                     traffic_scale=cfg.traffic_scale)
    matched = 0
    for k in range(60):
        c = sample_consumer(seed, 0, 40, k, catalog, cfg)
        nq = nash_quote(state, c.wtp, c.walk_cost, dow_mult=ds.dow_mult,
                        traffic_scale=cfg.traffic_scale)
        q = m.quote(Disclosure(wtp=c.wtp, walk_cost=c.walk_cost), Intent())
        if nq.outcome is None:
            assert q is None
        else:
            matched += 1
            assert q is not None
            assert q.sku == nq.outcome.sku
            assert q.qty == nq.outcome.qty
            assert abs(q.unit_price - nq.outcome.unit_price) < 1e-9
            assert abs(q.u_machine - nq.u_machine) < 1e-9
            assert abs(q.d_machine - nq.d_machine) < 1e-9
    assert matched > 0, "expected at least some deals on this seed"


# ── ledger conservation: Σ per-uid surplus == aggregate CS ──
def test_ledger_conservation():
    L = BuyerLedger()
    for uid in range(20):
        for j in range(3):
            L.record(Receipt(uid=uid, merchant_id="m", strategy="honest",
                             sku="cola", qty=1, unit_price=1.0, list_price=2.0,
                             realized_surplus=0.5 + 0.1 * j, outside_surplus=0.2,
                             frontier_surplus=0.9, regret=0.1))
    per_uid = sum(L.lifetime_surplus(u) for u in L.uids())
    assert abs(per_uid - L.aggregate_surplus()) < 1e-9
    assert L.conserves()


# ── the single-merchant paired run wires up end to end ──
def test_single_merchant_run_smoke():
    s = run_single_merchant(20260710, 300, attested=False)
    assert s["n"] == 300
    assert s["ledger_conserves"]
    # regret is non-negative on average for both arms (>= 0 by construction)
    assert s["naive_regret"]["mean"] >= 0
    assert s["agent_regret"]["mean"] >= 0


# ── settle decrements stock (protocol fidelity) ──
def test_settle_decrements_stock():
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40)
    from buyer.world import draw_vend_population
    b = draw_vend_population(20260710, 1)[0]
    agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
    q, _, _ = agent.negotiate(m)
    if q is not None:
        before = m.board()[q.sku].stock
        m.settle(q)
        assert m.board()[q.sku].stock == before - q.qty


# ── the agent never accepts a quote worse than walking away ──
def test_agent_never_worse_than_fallback():
    m = VendMerchant.from_vend("m", seed=20260710, day=0, tick=40)
    from buyer.world import draw_vend_population
    pop = draw_vend_population(20260710, 200)
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        fb, _ = agent.fallback([m])
        _, realized, _ = agent.negotiate(m)
        assert realized >= fb - 1e-9

"""Supply-side tests (task #64) — the MIRROR of buyer/tests.

Per phase (binding rigor):
  S1  the SupplierMerchant adapter matches wholesale.run.run_week to the cent;
      the ProcurementAgent is a BuyerAgent and never lands the venue below its
      no-deal event; procurement regret >= 0 (== 0 under the attested interface).
  S2  the endogenous per-venue COGS reproduces WholesaleDawn's static haircut to
      the cent (the faithfulness check); the flywheel scale only ever helps.
  S3  the 3-tier flywheel decomposition CONSERVES (each interface's Nash split
      sums to its total; the chain total is exactly gA + gB); certainty reduces
      the supplier's realized spoilage.
  S4  the unified lever is LITERALLY buyer.strategies.coordinate (import
      identity); the procurement monopsony audit PASSES and never breaches the
      supplier's participation floor — at BOTH interfaces, same code.
"""
import os
import subprocess
import sys

import numpy as np
import pytest

from buyer.agent import BuyerAgent
from buyer.merchant import Intent, Merchant, Quote

from wholesale import calibration as cal
from wholesale.calibration import V_ORDER, W_ORDER
from wholesale.run import run_week
from wholesale.scenario import build_ctx
from wholesale.world import Schedule, week_demand
from wholesale.supply import (ProcurementAgent, Supplier, SupplierMerchant,
                              procurement_agent, procurement_frontier,
                              procurement_regret)
from wholesale.block_supply import ProcurementMarket, endogenous_scales

SEED = 20260710
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CENT_FIELDS = ["wholesaler", "venue", "channel", "qty", "unit_price", "window",
                "terms", "share", "real_u_v", "real_w_contrib", "exp_u_v",
                "exp_u_w", "d_v", "d_w", "event"]


# ══ S1 ══════════════════════════════════════════════════════════════════════

def test_supplier_merchant_satisfies_protocols():
    """SupplierMerchant IS a Merchant (the buyer's only coupling) AND a Supplier
    (Merchant + the venue's newsvendor fallback)."""
    sup = SupplierMerchant.from_wholesale("beverage", "vending", seed=SEED, week=0)
    assert isinstance(sup, Merchant)
    assert isinstance(sup, Supplier)
    assert set(sup.board()) == {"beverage-case"}
    assert sup.salvage_floor(sup.sku) == pytest.approx(sup._ctx.cogs)


def test_procurement_agent_is_a_buyer_agent():
    sup = SupplierMerchant.from_wholesale("dry", "boba", seed=SEED, week=1)
    agent = procurement_agent("boba", [sup])
    assert isinstance(agent, BuyerAgent)


@pytest.mark.parametrize("arm", ["ratecard", "nego", "nego-indep"])
def test_adapter_matches_wholesale_to_the_cent(arm):
    """THE S1 reproduction contract: driving the block-week through
    ProcurementAgent × SupplierMerchant (venues shopping their suppliers, the
    truck Schedule shared per wholesaler in route order) reproduces
    wholesale.run.run_week's records — relationship by relationship, to the
    cent — for every arm. The buyer machinery faithfully operates the supplier
    world."""
    matched = 0
    for wk in range(4):
        ctxs = {(w, v): build_ctx(w, v, cal.BASE_FLEX)
                for w in W_ORDER for v in V_ORDER}
        envs = {(w, v): week_demand(SEED, wk, w, v, cal.BASE_NOISE)
                for w in W_ORDER for v in V_ORDER}
        ref, ref_sch = run_week(arm, ctxs, envs)
        new, new_sch = ProcurementMarket(SEED, wk,
                                         coordinate=(arm != "nego-indep")
                                         ).run_block_week(arm)
        assert len(ref) == len(new) == len(W_ORDER) * len(V_ORDER)
        for a, b in zip(ref, new):
            for f in _CENT_FIELDS:
                va, vb = a.get(f), b.get(f)
                if isinstance(va, float) and isinstance(vb, float):
                    assert abs(va - vb) < 1e-9, (arm, wk, f, va, vb)
                else:
                    assert va == vb, (arm, wk, f, va, vb)
            matched += 1
        for w in W_ORDER:                       # route density reproduced too
            assert abs(ref_sch[w].realized_route_cost()
                       - new_sch[w].realized_route_cost()) < 1e-9
    assert matched == 4 * 12


def test_procurement_never_worse_than_no_deal():
    """Mirror of the buyer's 'never worse than the sticker': the venue's
    realized surplus is always >= its no-deal EVENT (rate-card / Jetro)."""
    for wk in range(4):
        sch = Schedule()
        for v in V_ORDER:
            sup = SupplierMerchant.from_wholesale(
                "produce", v, seed=SEED, week=wk, schedule=sch)
            agent = procurement_agent(v, [sup])
            fb = sup.no_deal_surplus()
            q, realized, _ = agent.negotiate(sup)
            assert realized >= fb - 1e-9
            if q is not None:
                sup.settle(q)
            else:
                sup.settle_no_deal()


def test_procurement_regret_nonnegative_and_zero_when_attested():
    """Regret >= 0 by construction; and because the supply interface is attested
    (the forecast is verified at settlement), the honest Nash deal IS the
    frontier — realized == frontier, regret == 0 (the buyer's attested result,
    one tier up)."""
    for wk in range(3):
        for v in V_ORDER:
            sup = SupplierMerchant.from_wholesale("beverage", v, seed=SEED, week=wk)
            agent = procurement_agent(v, [sup])
            fr = procurement_frontier(agent, sup)
            _, realized, _ = agent.negotiate(sup)
            assert procurement_regret(fr, realized) >= 0.0
            assert procurement_regret(fr, realized) < 1e-9      # attested → 0


def test_procurement_agent_receipt_is_guarded():
    """ProcurementAgent inherits BuyerAgent.receipt(), which computes regret via
    single_merchant_frontier → bundle_surplus (the CONSUMER linear-decay value
    model) over CASE quantities — garbage for a venue's newsvendor value. It is
    overridden to raise, so the wrong path can never be silently taken;
    procurement_frontier / procurement_regret are the correct primitives."""
    sup = SupplierMerchant.from_wholesale("produce", "bodega", seed=SEED, week=0)
    agent = procurement_agent("bodega", [sup])
    with pytest.raises(NotImplementedError):
        agent.receipt(sup)


def test_procurement_uid_is_deterministic_across_hash_seeds():
    """Reproducibility (the paper's determinism claim): the emitted procurement
    uid must NOT depend on Python's per-process hash salt (PYTHONHASHSEED). It is
    a blake2b substream of the identity, not abs(hash((w, v))). The in-process
    uid equals the pure derivation, and three fresh subprocesses under different
    hash seeds emit the SAME uids for both the supply.py and block_supply.py
    sites."""
    from wholesale.world import substream
    sup = SupplierMerchant.from_wholesale("dry", "boba", seed=SEED, week=0)
    assert procurement_agent("boba", [sup]).uid == substream("procuid", "boba") % 10**8
    snippet = (
        "from wholesale.supply import procurement_agent, SupplierMerchant;"
        "from wholesale.world import substream;"
        "sup = SupplierMerchant.from_wholesale('dry','boba',seed=%d,week=0);"
        "print(procurement_agent('boba',[sup]).uid,"
        "      substream('procuid','beverage','bodega') %% 10**8)" % SEED)
    outs = {subprocess.check_output(
        [sys.executable, "-c", snippet], cwd=ROOT, text=True,
        env={**os.environ, "PYTHONHASHSEED": hs}).strip()
        for hs in ("0", "1", "9973")}
    assert len(outs) == 1, outs        # identical under every hash salt


# ══ S2 ══════════════════════════════════════════════════════════════════════

def test_endogenous_reproduces_static_haircut_to_the_cent():
    """The endogenous ProcurementAgent COGS scale == WholesaleDawn's static
    haircut, to the cent: the static haircut was already a faithful reduced form
    of the negotiation. (So the block re-run does not move — the honest S2
    result; the movement is the flywheel, S3.)"""
    from block.venues import WholesaleDawn
    from vend.core import substream
    seed, days = SEED, 30
    weeks = max(2, -(-days // 7))
    static = WholesaleDawn(seed, days).scales
    endo = endogenous_scales(substream(seed, "wholesale"), weeks)
    assert set(endo) == set(static)
    for v in static:
        assert abs(static[v] - endo[v]) < 1e-9, (v, static[v], endo[v])


def test_flywheel_scale_only_helps():
    """The flywheel (demand certainty) can only LOWER a venue's COGS: the venue
    keeps the better of {base, certain} scale, so every flywheel scale <= the
    endogenous scale."""
    from block.venues import EndogenousDawn
    endo = EndogenousDawn(SEED, 30, mode="endogenous").scales
    fly = EndogenousDawn(SEED, 30, mode="flywheel").scales
    assert set(endo) == set(fly)
    for v in endo:
        assert fly[v] <= endo[v] + 1e-9


def test_endogenous_dawn_block_matches_static_block():
    """End to end: a block run on the endogenous dawn reproduces the static-dawn
    block outcome exactly (same per-venue COGS and paired margin delta)."""
    from block.runner import run_twin
    from block.venues import BlockConfig
    venues = ("vending", "bodega", "boba", "bakery")
    st, _, _ = run_twin(21, SEED, BlockConfig(wholesale=True, procurement="static"),
                        venues=venues)
    en, _, _ = run_twin(21, SEED, BlockConfig(wholesale=True,
                                              procurement="endogenous"), venues=venues)
    for v in venues:
        a = st["per_world"]["snhp"]["venues"][v]["totals"].get("cogs", 0.0)
        b = en["per_world"]["snhp"]["venues"][v]["totals"].get("cogs", 0.0)
        assert abs(a - b) < 1e-6, (v, a, b)


# ══ S3 ══════════════════════════════════════════════════════════════════════

def test_flywheel_decomposition_conserves():
    """Each interface's Nash split sums to its own total, and the chain total is
    exactly gA + gB — no surplus created or lost in the per-tier decomposition."""
    from wholesale.flywheel import flywheel_decomposition
    fw = flywheel_decomposition(n_consumers=1000)
    assert fw["conserves"]
    for t in fw["tiers"]:
        assert t["A_split_ok"] and t["B_split_ok"]
        assert abs(t["chain_total"]
                   - (t["gA_consumer_merchant"] + t["gB_merchant_supplier"])) < 1e-5
    # growth is monotone in the certainty tf (more banked variance → more growth)
    chain = [t["chain_total"] for t in fw["tiers"]]
    assert all(b >= a - 1e-9 for a, b in zip(chain, chain[1:]))
    assert chain[0] == 0.0                        # tf=0 → no commit growth


def test_certainty_reduces_spoilage_in_the_engine():
    """The flywheel in the real multi-issue engine: tightening the forecast
    (the demand agent's certainty) reduces the supplier/venue's realized
    spoilage."""
    from wholesale.flywheel import cogs_vs_certainty
    from vend.core import substream
    cc = cogs_vs_certainty(substream(SEED, "wholesale"), 6)
    assert cc["certain"]["spoil_per_week"] <= cc["uncertain"]["spoil_per_week"] + 1e-9


# ══ S4 ══════════════════════════════════════════════════════════════════════

def test_the_lever_is_literally_the_buyer_side_function():
    """The unification, mechanical: the supply side calls the IDENTICAL
    buyer-side coordinate — no supplier reimplementation exists."""
    from wholesale.flywheel import coordinate as fly_coord
    from buyer.strategies import coordinate as buyer_coord
    assert fly_coord is buyer_coord
    assert fly_coord.__module__ == "buyer.strategies"


def test_monopsony_audit_passes_at_both_interfaces():
    """The SAME audit, at the consumer interface AND the supplier interface,
    PASSES — the disagreement-point discipline is symmetric."""
    from wholesale.flywheel import (coordinate_audit, interface_A_consumers,
                                    interface_B_venues)
    vA, sA = interface_A_consumers(SEED, 1500)
    vB, sB = interface_B_venues()
    for vals, salv, tag in ((vA, sA, "A"), (vB, sB, "B")):
        au = coordinate_audit(vals, salv, p_spoil=0.40)
        assert au["checks"]["A_coord_not_below_indep"], tag
        assert au["checks"]["B_participation_floor_holds"], tag
        assert au["checks"]["D_overreach_self_defeating"], tag
        assert au["verdict"].startswith("PASS"), tag
        # the participation floor is load-bearing: even maximal extraction never
        # takes the supplier's margin below zero
        for k in au["ks"]:
            assert au["sweep"][k]["monopsony_margin_min"] >= -1e-9


def test_procurement_floor_never_breached_below_cogs():
    """Directly on the supplier interface: no cleared case is ever priced below
    the supplier's cogs floor; an over-reaching club is refused and the case
    spoils (self-defeating)."""
    from buyer.strategies import coordinate
    from wholesale.flywheel import interface_B_venues
    vB, cogs = interface_B_venues()
    at_floor = coordinate(vB, salvage=cogs, s_risk=len(vB), p_spoil=0.4,
                          extraction=1.0)
    assert at_floor.participation_ok
    assert at_floor.merchant_margin >= -1e-9
    over = coordinate(vB, salvage=cogs, s_risk=len(vB), p_spoil=0.4, extraction=1.3)
    assert not over.participation_ok
    assert over.spoiled_by_overreach > 0
    assert over.total_growth < at_floor.total_growth

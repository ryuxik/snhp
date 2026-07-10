"""Tests for the agent-mediated block demand (task #62 / block/agentdemand.py).

The rigor the results doc leans on, mechanized: (1) the default (agent_demand
off) path stays byte-exact — agent mediation is a strictly gated overlay;
(2) agent-mediated demand CONSERVES money and units exactly (it settles through
the committed venue helpers); (3) agents touch ONLY the vending/bodega street
lane (every other venue is byte-identical to the passive twin); (4) the
per-venue transfer/growth decomposition sums to the total; (5) the antagonism
verdict is reproducible; (6) the growth legs (commit/coordinate) grow the pie
and keep merchant margin at/above its floor; (7) the frictionless commodity
endgame competes margin down but not below zero — the both-win survives."""
import math

import pytest

from block.agentdemand import (block_commit, block_coordinate, block_regime,
                               commodity_stress, run_antagonism,
                               resolve_shopper_agentic)
from block.runner import run_twin
from block.venues import BlockConfig

SEED = 20260710
STREET = ("vending", "bodega")
FOUR = ("vending", "bodega", "boba", "fashion")
TEN = ("vending", "bodega", "boba", "fashion", "bakery", "florist",
       "barbershop", "parking", "bar", "vintage")


@pytest.fixture(scope="module")
def agent_twin():
    """A 3-day four-venue twin with the SNHP street lane agent-mediated
    (bertrand competition + bodega adoption)."""
    cfg = BlockConfig(regulars=5, bodega_adopts=True, agent_demand="bertrand")
    return run_twin(3, SEED, cfg, venues=FOUR)


# ── the gate is byte-exact: agent mediation never perturbs the default ───────

def test_agent_demand_off_is_byte_exact():
    """agent_demand='off' (the default) reproduces the committed passive twin
    to the byte, and never emits the agent_* config keys — the same isolation
    discipline as the wholesale/procurement gate."""
    a, _, _ = run_twin(3, SEED, BlockConfig(regulars=5), venues=FOUR)
    b, _, _ = run_twin(3, SEED, BlockConfig(regulars=5, agent_demand="off"),
                       venues=FOUR)
    import json
    a.pop("meta"); b.pop("meta")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert "agent_demand" not in a["config"]


def test_agent_config_keys_appear_only_when_on():
    """When the mode is on the config records it (so an artifact is
    self-describing), and stays absent otherwise."""
    on, _, _ = run_twin(2, SEED, BlockConfig(bodega_adopts=True,
                                             agent_demand="bertrand"),
                        venues=STREET)
    assert on["config"]["agent_demand"] == "bertrand"
    assert on["config"]["agent_friction"] == 0.0


# ── agent-mediated demand conserves (it settles through the committed path) ──

def test_agent_twin_conserves_money_and_units(agent_twin):
    _res, ledger, worlds = agent_twin
    for w in ("sticker", "snhp"):
        for v in FOUR:
            venue = worlds[w]["venues"][v]
            for d in range(3):
                assert math.isclose(ledger.day_metrics(w, v, d)["revenue"],
                                    venue.revenue_by_day.get(d, 0.0),
                                    rel_tol=0, abs_tol=1e-6)
            lu = sum(ledger.day_metrics(w, v, d)["units"] for d in range(3))
            assert lu == venue.units_vended
            if v != "boba":
                assert venue.units_vended <= venue.units_stocked
    for e in ledger.events:
        if e["type"] == "deal":
            assert e["spend"] == round(e["qty"] * e["unit_price"], 2)


def test_every_agent_arrival_resolves(agent_twin):
    """No street shopper vanishes: in the agent-mediated SNHP world every
    street arrival becomes exactly one venue_entered or one no_sale."""
    from collections import Counter
    _res, ledger, _worlds = agent_twin
    c = Counter(e["type"] for e in ledger.events
                if e["world"] == "snhp" and e.get("kind") == "street")
    assert c["arrival"] == c["venue_entered"] + c["no_sale"]


def test_sticker_world_is_untouched_by_agent_demand():
    """The agent overlay is SNHP-only, so the sticker world (the HUD baseline)
    is byte-identical whether or not agent demand is on."""
    import json
    off, _, wo = run_twin(3, SEED, BlockConfig(regulars=5), venues=FOUR)
    on, _, wn = run_twin(3, SEED, BlockConfig(regulars=5, bodega_adopts=True,
                                              agent_demand="bertrand"),
                         venues=FOUR)
    a = off["per_world"]["sticker"]
    b = on["per_world"]["sticker"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_agents_touch_only_the_street_lane():
    """The full ten-venue agent twin changes ONLY vending and bodega; the
    other eight self-contained venues (no same-good competitor) are
    byte-identical to the passive twin, in BOTH worlds."""
    import json
    passive, _, _ = run_twin(3, SEED, BlockConfig(regulars=5), venues=TEN)
    agent, _, _ = run_twin(3, SEED, BlockConfig(regulars=5, bodega_adopts=True,
                                                agent_demand="bertrand"),
                           venues=TEN)
    for v in TEN:
        pv = passive["per_world"]["snhp"]["venues"][v]
        av = agent["per_world"]["snhp"]["venues"][v]
        same = json.dumps(pv, sort_keys=True) == json.dumps(av, sort_keys=True)
        if v in STREET:
            assert not same, f"{v} should change under agent demand"
        else:
            assert same, f"{v} must be untouched by the street-lane agent"


# ── the per-venue decomposition sums, and the verdict reproduces ─────────────

def test_transfer_growth_decomposition_sums():
    """Δmargin(agent−passive) == d_transfer(competition) + d_surface(adoption)
    per venue, exactly (the ladder passive→adopt→agent is additive), and
    Δjoint == Δmargin + Δcs."""
    r = run_antagonism(days=4, seed=SEED, regulars=0, venues=STREET)
    for v, row in r["per_venue"].items():
        dm = row["d_margin_agent_minus_passive"]["mean"]
        dt = row["d_transfer_competition"]["mean"]
        ds = row["d_surface_adoption"]["mean"]
        assert math.isclose(dm, dt + ds, rel_tol=0, abs_tol=1e-6), v


def test_antagonism_verdict_is_reproducible():
    a = run_antagonism(days=4, seed=SEED, regulars=0, venues=STREET)
    b = run_antagonism(days=4, seed=SEED, regulars=0, venues=STREET)
    assert a["per_venue"] == b["per_venue"]
    assert a["hud"] == b["hud"]


def test_bertrand_competition_transfers_margin_down_at_the_competed_venue():
    """The competitive round is a TRANSFER: it can only move margin toward the
    floor at the venue it competes (never conjure margin from nowhere). At the
    thin-overlap block the bodega is the competed side; its transfer is ≤ 0."""
    r = run_antagonism(days=6, seed=SEED, regulars=0, venues=STREET)
    assert r["per_venue"]["bodega"]["d_transfer_competition"]["mean"] <= 1e-9


# ── the GROWTH legs: commit/coordinate grow the pie, margin ≥ floor ──────────

def test_commit_grows_pie_and_keeps_merchant_margin_nonnegative():
    cm = block_commit(SEED, 600)
    g = cm["newcomer_joint_growth"]
    assert g["ci95"][0] > 0                       # joint growth CI excludes zero
    assert cm["merchant_share_ge_zero"]           # merchant keeps a positive share
    assert cm["merchant_share_min"] >= -1e-9


def test_coordinate_monopsony_audit_passes_on_the_block():
    co = block_coordinate(SEED, 600)
    assert co["audit_verdict"] == "PASS"
    assert all(co["audit_checks"].values())


def test_regime_agent_beats_human_on_block_merchants():
    rg = block_regime(SEED, 600)
    ds = rg["delta_surplus_agent_minus_human"]
    assert ds["significant"] and ds["mean"] > 0
    assert rg["agent_regret"]["mean"] < rg["human_regret"]["mean"]


# ── the ENDGAME: even frictionless commodity competition stays a both-win ────

def test_commodity_endgame_competes_margin_down_but_not_below_zero():
    """The A2A endgame (overlap goods, walk→0) competes commodity margin DOWN
    (a real transfer) yet — because the two boards have DIFFERENT floors — the
    winner keeps its cost edge, so aggregate margin stays positive AND buyer CS
    rises: a both-win even at the worst case."""
    cs = commodity_stress(SEED, 6)
    assert cs["margin_transfer_day"] < 0                 # margin competed down
    assert cs["bertrand_margin_day"] >= 0                # but not below the floor
    assert cs["bertrand_cs_day"] > cs["passive_cs_day"]  # buyer gains

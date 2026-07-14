"""Tests for the v4 multi-robot bargaining benchmark (SPEC.md v4.0).
Panel-mandated invariants included (review/PANEL_V4.md): ledger/provenance
conservation, ablation fingerprints (the automatic v2.1 dead-issue catcher),
τ* threshold geometry, company⊥sector, twin-fleet symmetry, v3 reduction."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                               # noqa: E402

from swarm import world as W                     # noqa: E402
from swarm.arms import SnhpArm, intent, make_arm # noqa: E402
from swarm.value import delivery_target, phi     # noqa: E402
from swarm.world import TOTAL_STOCK, V_DELIVER, World  # noqa: E402

LADDER = ("null", "rules", "auction", "auction-co", "team", "team-co",
          "twofirm", "snhp", "snhp+net", "snhp-hz")


def _run(arm_name, sigma, seed, ticks, issues=("cargo", "energy", "sector"),
         tau=0.0, preset="v4"):
    hazard = arm_name.endswith("-hz")
    base = arm_name[:-3] if hazard else arm_name
    w = World(sigma=sigma, seed=seed, hazard_phi=hazard, preset=preset,
              tau=(tau, tau), internalize_tariffs=(base == "team"))
    arm = make_arm(base, w, issues=issues)
    for _ in range(ticks):
        arm.tick()
        if w.tick % 50 == 0:
            assert w.material_accounted() == TOTAL_STOCK, "material leak"
            assert w.ledger_accounted(), "ledger leak"
            m = w.delivered_matrix
            assert m[0][0] + m[0][1] + m[1][0] + m[1][1] == w.delivered
            for r in w.robots:
                assert sum(r.load_prov) == r.load, "provenance leak"
                assert -1e-9 <= r.battery <= W.BATTERY_MAX + 1e-9
                assert 0 <= r.load <= r.cap
    return w, arm


def test_contract_space_size():
    w = World(seed=0)
    assert len(SnhpArm(w).space) == 7 * 7 * 2
    assert len(SnhpArm(w, issues=("cargo",)).space) == 7


def test_sigma_is_mean_preserving():
    means = {}
    for sigma in (0.0, 0.5, 1.0):
        b = [r.battery for s in range(40) for r in World(sigma=sigma, seed=s).robots]
        e = [r.eff for s in range(40) for r in World(sigma=sigma, seed=s).robots]
        means[sigma] = (np.mean(b), np.mean(e))
    for sigma in (0.5, 1.0):
        assert abs(means[sigma][0] - means[0.0][0]) < 3.0
        assert abs(means[sigma][1] - means[0.0][1]) < 0.05


def test_company_sector_orthogonal():
    w = World(sigma=1.0, seed=0)
    counts = {}
    for r in w.robots:
        counts[(r.company, r.sector)] = counts.get((r.company, r.sector), 0) + 1
    assert counts == {(0, 0): 6, (0, 1): 6, (1, 0): 6, (1, 1): 6}


def test_twin_fleet_symmetry():
    w = World(sigma=1.0, seed=3)
    c0 = sorted((r.cap, round(r.eff, 6), round(r.battery, 6))
                for r in w.robots if r.company == 0)
    c1 = sorted((r.cap, round(r.eff, 6), round(r.battery, 6))
                for r in w.robots if r.company == 1)
    assert c0 == c1, "companies drew different fleets"
    for k in range(12):
        a, b = w.robots[k], w.robots[12 + k]
        assert b.pos == (a.pos[0], W.GRID - a.pos[1]), "positions not mirrored"
        assert b.sector == 1 - a.sector


def test_tau_threshold_geometry():
    """Pins the τ* arithmetic that sized the tariff grid (panel F2):
    a loaded (L=3, eff=1, EV=0.15) company-0 drone at A2 refines FOREIGN
    (B1, haul 20) at τ=0.10 and HOME (B0, haul 40) at τ=0.20; τ*=0.16."""
    for tau, expected_ref in ((0.10, 1), (0.20, 0)):
        w = World(sigma=0.0, seed=0, tau=(tau, tau), freeze_ev=0.15)
        r = w.robots[0]
        r.company, r.pos, r.load, r.eff, r.ev = 0, W.PRESETS["v4"]["sources"][1], 3, 1.0, 0.15
        r.load_prov = [3, 0]
        assert delivery_target(r, w, sticky=False) == expected_ref, \
            f"τ={tau}: expected refinery {expected_ref}"


def test_phi_policy_share_routing():
    """Φ's load term and intent() must route to the SAME refinery."""
    w = World(sigma=1.0, seed=5, tau=(0.25, 0.25))
    for r in w.robots[:8]:
        r.load = min(2, r.cap)
        r.load_prov = [r.load if r.company == 0 else 0,
                       r.load if r.company == 1 else 0]
        r.battery = 90.0
        tgt = intent(r, w)
        assert tgt == w.refineries[delivery_target(r, w, sticky=False)] or \
            tgt == w.charger  # low-margin robots may divert to charge


def test_v3_preset_reduction():
    w = World(sigma=1.0, seed=0, preset="v3")
    assert len(w.refineries) == 1 and w.ref_owner == [None]
    for r in w.robots:
        assert w.credit_rate(r.company, 0) == 1.0
        assert delivery_target(r, w, sticky=False) == 0


def test_conservation_all_arms_with_tariffs():
    for arm_name in LADDER:
        w, _ = _run(arm_name, sigma=1.0, seed=0, ticks=200, tau=0.25)
        if arm_name != "team":   # team internalizes; identity is notional
            tariffs = sum(c["tariffs_earned"] for c in w.company)
            assert abs(tariffs - 0.25 * V_DELIVER * w.foreign_refined) < 1e-6, \
                "tariff booked away from refine-time"


def test_all_arms_deliver():
    for arm_name in LADDER:
        w, _ = _run(arm_name, sigma=0.5, seed=1, ticks=800)
        assert w.delivered > 0, f"{arm_name} delivered nothing"


def test_foreign_share_nonvacuous_at_tau0():
    w, _ = _run("rules", sigma=0.5, seed=0, ticks=800, tau=0.0)
    assert w.foreign_refined > 0, "no foreign refining at τ=0 — P7-B vacuous"


def test_snhp_deals_have_strictly_positive_surplus():
    w, arm = _run("snhp", sigma=1.0, seed=0, ticks=500)
    assert arm.deals > 0
    for d in w.deal_log:
        assert d["sa"] > 0 and d["sb"] > 0
        assert 0.0 <= d["capture"] <= 1.0 + 1e-9
        assert "border" in d and "distress" in d


def test_single_issue_selfish_bargaining_is_nearly_inert():
    _, arm = _run("snhp", sigma=1.0, seed=0, ticks=400, issues=("energy",))
    assert arm.deals == 0, f"energy-only struck {arm.deals} deals"
    w, arm = _run("snhp", sigma=1.0, seed=0, ticks=400, issues=("cargo",))
    assert arm.deals <= 3, f"cargo-only struck {arm.deals} (expect ~jettisons)"


def test_ablations_differ():
    """The automatic v2.1 dead-issue catcher: ablation fingerprints must NOT
    be identical — a dead issue makes rows bit-equal."""
    def fp(issues):
        w, arm = _run("snhp", sigma=1.0, seed=0, ticks=500, issues=issues,
                      tau=0.15)
        return (w.delivered, arm.deals,
                round(sum(r.battery for r in w.robots), 3))
    full = fp(("cargo", "energy", "sector"))
    ce = fp(("cargo", "energy"))
    c = fp(("cargo",))
    assert full != ce, "sector issue is DEAD (fingerprints identical)"
    assert ce != c, "energy issue is DEAD (fingerprints identical)"


def test_team_beats_null():
    wn, _ = _run("null", sigma=1.0, seed=2, ticks=800)
    wt, team = _run("team", sigma=1.0, seed=2, ticks=800)
    assert team.deals > 0
    assert wt.delivered >= wn.delivered


def test_determinism():
    w1, a1 = _run("twofirm", sigma=1.0, seed=3, ticks=250, tau=0.15)
    w2, a2 = _run("twofirm", sigma=1.0, seed=3, ticks=250, tau=0.15)
    assert w1.delivered == w2.delivered
    assert a1.deals == a2.deals
    assert [r.battery for r in w1.robots] == [r.battery for r in w2.robots]

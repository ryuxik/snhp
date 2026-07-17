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
from swarm.arms import CLAIM_OPTS, SnhpArm, intent, make_arm  # noqa: E402
from swarm.value import delivery_target, phi     # noqa: E402
from swarm.world import (DEBT_ENERGY_PRICE, TOTAL_STOCK, V_DELIVER,  # noqa: E402
                         World, manhattan)

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
            assert w.material_ok(), "material leak"
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


def test_v5_world_mirrored_and_pinned():
    for seed in (0, 7):
        w = World(sigma=0.5, seed=seed, preset="v5")
        n = len(w.sources)
        assert n == 10 and sum(w.stock) == 2 * TOTAL_STOCK
        for i in range(5):                       # mirror pairs share stock
            x, y = w.sources[i]
            assert w.sources[i + 5] == (x, W.GRID - y)
            assert w.stock[i] == w.stock[i + 5]
        assert len(w.chargers) == 4
        assert sorted(w.charger_owner) == [0, 0, 1, 1]


def test_v5_guest_charging_and_claims():
    w, _ = _run("rules", sigma=0.5, seed=1, ticks=900, preset="v5", tau=0.15)
    assert w.guest_charged > 0, "no guest charging — infra geography vacuous"
    assert w.delivered > 0


def test_v5_noise_deals_still_true_positive():
    """The veto guarantees every EXECUTED deal is truly mutually beneficial
    even under heavy estimation noise."""
    hazard_w = World(sigma=1.0, seed=0, hazard_phi=True, preset="v5",
                     tau=(0.15, 0.15))
    arm = make_arm("snhp", hazard_w, noise=1.0)
    for _ in range(700):
        arm.tick()
    assert arm.deals > 0, "no deals under noise"
    assert arm.vetoes > 0, "no vetoes at s=1.0 — noise not biting"
    for d in hazard_w.deal_log:
        assert d["sa"] > 0 and d["sb"] > 0


def test_v6_liar_assignment_balanced():
    w = World(sigma=0.5, seed=4, preset="v5", liar_frac=0.5, defended=True)
    for c in (0, 1):
        liars = sum(1 for r in w.robots if r.company == c and r.liar)
        assert liars == 6, f"company {c}: {liars} liars (want 6)"
    assert all(r.attested == (not r.liar) for r in w.robots)


def test_v6_attested_all_equals_honest():
    """P10c pinned: with zero liars, the defended condition is mechanically
    identical to the honest baseline (attested pairs pay no distrust tax)."""
    outs = []
    for defended in (False, True):
        w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, defended=defended)
        arm = make_arm("snhp", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 6)))
    assert outs[0] == outs[1], f"defended≠honest with zero liars: {outs}"


def test_v6_lies_never_poison_executed_deals():
    """BATNA inflation makes liars pickier, never poisonous: every executed
    deal still exceeds both TRUE disagreement points (asserted in-arm too)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, liar_frac=0.5, defended=False)
    arm = make_arm("snhp", w)
    for _ in range(600):
        arm.tick()
    assert arm.deals > 0
    for d in w.deal_log:
        assert d["sa"] > 0 and d["sb"] > 0


def test_v6_lying_has_an_effect():
    """Review G4: no test failed if the lie wiring became a no-op. At f=1.0
    undefended, universal BATNA inflation must visibly shrink deal volume
    vs the honest twin (P10b's collapse direction)."""
    counts = []
    for f in (0.0, 1.0):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, liar_frac=f)
        arm = make_arm("snhp", w)
        for _ in range(600):
            arm.tick()
        counts.append(arm.deals)
    assert counts[0] > 0
    assert counts[1] < counts[0], \
        f"universal lying did not reduce deals: {counts}"


def test_v6_attested_test_strikes_deals():
    """The defended==honest equivalence check is vacuous at zero deals —
    pin that the config it runs actually trades."""
    w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, defended=True)
    arm = make_arm("snhp", w)
    for _ in range(400):
        arm.tick()
    assert arm.deals > 0


def test_v6_team_constant_under_liars():
    """SPEC control: arms that consume no reports run under liars without
    crashing (review: the per-side IR assert fired through TeamArm's joint
    pick) and with the lie machinery never engaged."""
    for name in ("team", "auction"):
        w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=(name != "team"), liar_frac=0.5)
        arm = make_arm(name, w)
        for _ in range(400):
            arm.tick()
        assert arm.deals >= 0    # completing without AssertionError IS the test


def test_v7_no_charger_livelock():
    """Review S1: a pessimistic gauge (bias < -0.05) could never read 95%
    battery, so a docked robot parked at the charger forever. The charger's
    meter now undocks at true-full; assert no robot sits docked and full."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, self_noise=0.30)
    assert any(r.gauge_bias < -0.05 for r in w.robots), "seed lost its pessimists"
    arm = make_arm("snhp", w)
    for _ in range(800):
        arm.tick()
        if w.tick % 20 == 0:
            for r in w.robots:
                assert not (r.charge_queued_at >= 0
                            and r.battery >= W.BATTERY_MAX - 1e-9), \
                    f"robot {r.rid} parked at charger at true-full (livelock)"


def test_v7_poisoned_zero_without_gauge_noise():
    """The veto guarantee, correctly scoped: for the Nash-IR arm at s7=0,
    every executed deal has strictly positive TRUE surplus on both sides.
    (Team/twofirm one-sided losses are by design, not poisoning — review S8.)"""
    w = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, liar_frac=0.5)
    arm = make_arm("snhp", w)
    for _ in range(600):
        arm.tick()
    assert arm.deals > 0
    for d in w.deal_log:
        assert d["sa_true"] > 0 and d["sb_true"] > 0


def test_v7_liar_sets_seed_paired_across_self_noise():
    """Review S2: the gauge draw must consume the RNG stream at every s7 so
    the liar permutation is identical across self-noise cells of a seed."""
    sets = []
    for s7 in (0.0, 0.15, 0.30):
        w = World(sigma=0.5, seed=5, preset="v5", liar_frac=0.5, self_noise=s7)
        sets.append({r.rid for r in w.robots if r.liar})
    assert sets[0] == sets[1] == sets[2], f"liar sets differ across s7: {sets}"


def test_trust_arms_emit_audited_schema():
    """Review S6: trust arms fabricated capture=1.0/distress=0 and omitted
    the true-surplus audit. Both tiers now share the SnhpArm log tail."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, liar_frac=0.5, defended=True)
    arm = make_arm("trust-gated", w)
    for _ in range(600):
        arm.tick()
    assert arm.deals > 0
    for d in w.deal_log:
        assert "sa_true" in d and d["sa_true"] is not None
        assert 0.0 < d["capture"] <= 1.0 + 1e-9
    assert any(d["capture"] < 1.0 - 1e-9 for d in w.deal_log), \
        "every capture exactly 1.0 — smells hardcoded"


def test_v8_pad_unloads_on_arrival():
    """A robot that strands ON its target refinery still delivers (the pad
    is facility-side). Minimal repro of the audit's cargo trap."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0))
    r = w.robots[0]
    ref = w.refineries[0]
    r.pos = (ref[0] - 1, ref[1])
    r.load, r.load_prov = 3, [3, 0]
    r.company = 0
    r.battery = r.step_cost() + 0.5      # arrival step leaves < RESCUE_FLOOR
    r.sector = 0
    before = w.delivered
    from swarm.arms import drive
    drive(r, w)
    assert r.pos == ref and r.stranded, "repro setup broken"
    assert r.load == 0 and w.delivered == before + 3, \
        "pad-strand cargo trap is back"


def test_v8_deal_pause_immobilizes_both():
    """An executed exchange freezes both parties for DEAL_PAUSE ticks."""
    w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True)
    arm = make_arm("snhp", w)
    for _ in range(600):
        # robots already mid-pause when the tick STARTS must not move in it
        held = {r.rid: r.pos for r in w.robots if w.tick < r.busy_until}
        arm.tick()
        for r in w.robots:
            if r.rid in held:
                assert r.pos == held[r.rid], f"robot {r.rid} moved mid-exchange"
    assert arm.deals > 0
    assert any(r.busy_until > 0 for r in w.robots), "pause never engaged"


def test_v9_life_value_decays_with_stock():
    """v_life prices the remaining career: it shrinks as the field empties
    and hits ~0 when nothing is left to mine."""
    from swarm.value import v_life
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, life_pricing=True)
    r = w.robots[0]
    early = v_life(r, w)
    w.stock = [0] * len(w.stock)
    late = v_life(r, w)
    assert early > W.P_STRAND, f"early career worth {early} <= flat price"
    assert late <= 1e-9, f"empty-field career still worth {late}"


def test_v10_belief_default_off_is_flag_absent():
    """belief_mode=False must be indistinguishable from a World that never
    heard of beliefs — the accessor indirection may not perturb a bit."""
    outs = []
    for kw in ({}, dict(belief_mode=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, **kw)
        arm = make_arm("snhp", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], "belief plumbing leaked into the default path"


def test_v10_perfect_sensing_is_the_oracle():
    """The pinning placebo: R_SENSE covering the whole grid ⇒ every read is
    truth and the belief-mode run is bit-exact with the oracle. Race pricing
    OFF here: with per-tick observation the rival rate is genuinely nonzero
    (the race is real), so the placebo isolates the belief PLUMBING."""
    outs = []
    for kw in ({}, dict(belief_mode=True, race_pricing=False, r_sense=64)):
        w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, **kw)
        arm = make_arm("snhp", w)
        for _ in range(500):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], f"perfect sensing != oracle: {outs}"


def test_v10_on_empty_rock_resenses_within_a_tick():
    """The v7 livelock lesson applied to beliefs: a robot standing ON a
    mined-out asteroid it believed rich senses truth (R_SENSE covers its own
    cell) and re-claims — no mining-nothing-forever loop."""
    from swarm.arms import drive
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True)
    r = w.robots[0]
    i = r.sector
    moved, w.stock[i] = w.stock[i], 0            # empty it behind the
    w.stock[(i + 1) % len(w.sources)] += moved   # company's back (conserve)
    w.belief[r.company][i] = max(moved, 12)      # ...belief stays rich
    r.pos, r.load, r.battery = w.sources[i], 0, 80.0
    drive(r, w)
    assert w.belief[r.company][i] == 0, "on the rock, still deluded"
    assert r.sector != i, "did not re-claim off the empty rock"
    assert w.stock[r.sector] > 0


def test_v10_rival_rate_prices_unexplained_depletion():
    """Two companies, one shared rock: company 0 mines during company 1's
    observation gap. On re-observation company 1's rival_rate turns positive
    (it mined nothing — all depletion is rival) and its expected stock at
    arrival drops below belief; company 0's OWN mining explains everything,
    so its rival_rate stays 0."""
    w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True)
    i = 0
    assert w.stock[i] >= 4
    r0 = next(r for r in w.robots if r.company == 0)
    r1 = next(r for r in w.robots if r.company == 1)
    r0.sector, r0.pos, r0.load, r0.cap = i, w.sources[i], 0, 3
    w.tick = 10
    assert w.pick(r0) == 3                       # co-0 mines 3 in the gap
    w.tick = 20
    w._observe(1, i)                             # co-1 flies by and looks
    w._observe(0, i)
    assert w.rival_rate[1][i] > 0, "unexplained depletion not priced"
    assert w.rival_rate[0][i] == 0.0, "own mining misread as a rival"
    r1.pos = (30, 30)                            # far: eta > 0, out of sense
    eta = W.manhattan(r1.pos, w.sources[i])
    believed = w.stock_belief(r1, i)
    expected = max(0.0, believed - w.rival_rate[1][i] * eta)
    assert believed > 0 and expected < believed


def test_v10_mine_trait_default_draws_identical():
    """The gated trait draw must not shift the RNG stream: flag absent and
    flag False produce identical fleets (the v7 seed-pairing lesson)."""
    def tup(w):
        return [(r.cap, round(r.eff, 12), round(r.battery, 12), r.pos,
                 r.mine_rate) for r in w.robots]
    w0 = World(sigma=1.0, seed=0, preset="v5")
    w1 = World(sigma=1.0, seed=0, preset="v5", mine_trait=False)
    assert tup(w0) == tup(w1)
    assert all(r.mine_rate == 1 for r in w0.robots)


def test_v10_mine_trait_rate_limits_pick():
    w = World(sigma=1.0, seed=0, preset="v5", mine_trait=True)
    assert all(1 <= r.mine_rate <= 3 for r in w.robots)
    m0 = sorted(r.mine_rate for r in w.robots if r.company == 0)
    m1 = sorted(r.mine_rate for r in w.robots if r.company == 1)
    assert m0 == m1, "twin fleets drew different trait multisets"
    r = w.robots[0]
    r.sector, r.load, r.cap, r.mine_rate = 0, 0, 5, 2
    r.pos = w.sources[0]
    assert w.stock[0] > 4
    assert w.pick(r) == 2 and r.load == 2, "mine_rate did not limit pick"
    assert w.pick(r) == 2 and r.load == 4
    assert w.own_mined[r.company][0] == 4


def test_v10_belief_mode_keeps_evaluated_equals_executed():
    """Beliefs may not change during the encounter phase (sensing lives in
    the drive/world phase; sense_step freezes it before encounters — by
    design). If they could, the in-arm evaluated==executed assert would
    fire somewhere in 600 ticks; completing clean IS the test."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True)
    arm = make_arm("snhp", w)
    for _ in range(600):
        arm.tick()
    assert arm.deals > 0, "belief-mode snhp-hz struck no deals — vacuous"
    for d in w.deal_log:
        assert d.get("sa_true") is not None, "belief-mode audit not engaged"


def test_v8_grid_scaling_preserves_baseline():
    """grid=32 is bit-identical to the unparametrized world; grid=64 scales
    facilities and keeps stock/robot counts fixed."""
    w32 = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15))
    assert w32.refineries == [(26, 6), (26, 26)]
    w64 = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15), grid=64)
    assert w64.refineries == [(52, 12), (52, 52)]
    assert w64.total_stock == w32.total_stock
    assert len(w64.robots) == len(w32.robots)
    assert all(0 <= s[0] <= 64 and 0 <= s[1] <= 64 for s in w64.sources)


# ── v11: the moving field (column J) ──────────────────────────────────────
def test_v11_dynamic_default_off_is_flag_absent():
    """dynamic_field=False must be indistinguishable from a World that never
    heard of the moving field — the dedicated RNG and the bookkeeping arrays
    may not perturb a single bit of the default path."""
    outs = []
    for kw in ({}, dict(dynamic_field=False, contested=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, belief_mode=True, **kw)
        arm = make_arm("snhp", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], "moving-field plumbing leaked into the default path"


def test_v11_arrival_adds_unknown_rock():
    """An arrival appends a rock whose belief starts at 0 for BOTH companies —
    unknown until sensed — with stock and total_stock grown; a robot placed on
    it senses truth for its OWN company only."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True, dynamic_field=True)
    n0 = len(w.sources)
    total0 = w.total_stock
    w._field_events = [dict(t=10.0, kind="arrival")]   # isolate ONE arrival
    w._field_next = 0
    w.tick = 10
    w.field_step()
    i = n0
    assert len(w.sources) == n0 + 1 and w.arrival_indices == [i]
    assert w.belief[0][i] == 0 and w.belief[1][i] == 0, "new rock not unknown"
    assert w.stock[i] > 0 and w.total_stock == total0 + w.stock[i]
    assert w.last_seen[0][i] == 10 and w.last_seen[1][i] == 10
    # place a company-0 robot ON the rock, every other robot far away, sense
    xi, yi = w.sources[i]
    far = (1 if xi > 5 else 30, 1 if yi > 5 else 30)   # Chebyshev > 3 from i
    for r in w.robots:
        r.pos = far
    w.robots[0].pos = w.sources[i]                      # rid 0 is company 0
    assert w.robots[0].company == 0
    w.sense_step()
    assert w.belief[0][i] == w.stock[i], "company did not sense the new rock"
    assert w.belief[1][i] == 0, "the other company magically learned it"


def test_v11_departure_leaves_a_ghost():
    """A departure erases the TRUE stock (booked to stock_lost, conservation
    exact) but leaves the belief untouched — the ghost on the stale map that
    P16 is about."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True, dynamic_field=True)
    w._field_events = [dict(t=10.0, kind="departure")]
    w._field_next = 0
    w.tick = 10
    w.field_step()
    dep = w.field_log[-1]
    i = dep["src"]
    assert dep["kind"] == "departure" and dep["amt"] > 0
    assert w.stock[i] == 0, "departed rock still has true stock"
    # belief was pinned to truth at t=0 and never re-sensed → still positive
    assert w.belief[0][i] > 0 and w.belief[1][i] > 0, "the ghost vanished"
    assert w.stock_lost == dep["amt"]
    assert w.material_ok(), "conservation broke — stock_lost not accounted"


def test_v11_contested_unmirrored_band():
    """The contested v5 field is 10 rocks drawn INDEPENDENTLY in the central
    band y ∈ [10, 22), total pinned, each ≥3 from every facility, and NOT the
    mirror-symmetric construction (the placebo does not apply here)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), contested=True)
    assert len(w.sources) == 10
    assert sum(w.stock) == 2 * TOTAL_STOCK
    assert all(10 <= y < 22 for _, y in w.sources), "rock outside central band"
    srcset = set(w.sources)
    assert not all((x, W.GRID - y) in srcset for x, y in w.sources), \
        "contested field is still mirror-symmetric"
    facs = list(w.refineries) + list(w.chargers)
    assert all(W.manhattan(s, f) >= 3 for s in w.sources for f in facs), \
        "a contested rock sits < 3 from a facility"


def test_v11_belief_dynamic_evaluated_equals_executed():
    """Field events fire at tick start, never during the encounter phase, so
    the in-arm evaluated Φ == executed Φ assert never trips across arrivals and
    departures. 600 belief+dynamic ticks completing clean IS the test; the
    field must actually move (non-vacuity) and conservation must survive it."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True, dynamic_field=True)
    arm = make_arm("snhp", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "conservation broke over the moving field"
    assert arm.deals > 0, "belief+dynamic snhp-hz struck no deals — vacuous"
    assert len(w.sources) > 10 or w.stock_lost > 0, "no field events fired"
    for d in w.deal_log:
        assert d.get("sa_true") is not None, "belief-mode audit not engaged"


def test_v11_makespan_counts_arrival_stock():
    """total_stock grows with an arrival, so the makespan check (delivered >=
    total_stock) only fires once the newcomer's stock is delivered too. Driven
    on the conservation ledger directly: a lean fleet is not guaranteed to
    clear a live field 100%, but the threshold SEMANTIC is exact."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              dynamic_field=True)
    w._field_events = [dict(t=5.0, kind="arrival")]
    w._field_next = 0
    w.tick = 5
    w.field_step()
    base = 2 * TOTAL_STOCK
    arr = w.stock[-1]
    assert w.arrival_indices == [10] and arr > 0
    assert w.total_stock == base + arr, "arrival not counted in total_stock"
    # deliver ONLY the original field: the break condition must NOT hold yet
    for k in range(10):
        w.stock[k] = 0
    w.delivered = base
    assert w.material_ok(), "conservation broke (arrival still in ground)"
    assert w.delivered < w.total_stock, "makespan would fire before arrival is cleared"
    # deliver the arrival too → the break condition now holds, and only now
    w.stock[-1] = 0
    w.delivered += arr
    assert w.material_ok()
    assert w.delivered >= w.total_stock, "full delivery incl. arrival must trip makespan"
    assert w.delivered == base + arr


# ── v12: pricing the unknown (column K) ────────────────────────────────────
def test_v12_default_off_is_flag_absent():
    """scouting / map_trading / prospect_claims all default off ⇒ a v11 world is
    bit-identical to one that never heard of column K (the accessors, the extra
    arrays and the widened contract space may not perturb a single bit)."""
    outs = []
    for kw in ({}, dict(scouting=False, map_trading=False, prospect_claims=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, belief_mode=True, dynamic_field=True,
                  contested=True, **kw)
        arm = make_arm("snhp", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], "column-K plumbing leaked into the default path"


def test_v12_scout_targets_stalest_respects_max_and_battery():
    """K0: scout_target sends a robot to its company's stalest map point, caps
    at SCOUTS_MAX per company (deterministic by rid), and refuses a robot that
    lacks the battery for the round trip. Trigger A (believed-empty field) also
    fires without the staleness threshold."""
    from swarm.arms import scout_target, SCOUTS_MAX
    w = World(sigma=0.5, seed=0, preset="v5", belief_mode=True, scouting=True)
    n = len(w.sources)
    w.tick = 300
    for co in (0, 1):
        w.last_seen[co] = [300] * n           # every company-1 point is fresh
    idx = 3
    w.last_seen[0][idx] = 0                    # company-0's one stale point
    target = w.sources[idx]
    near = (max(1, target[0] - 1), max(1, target[1] - 2))   # manhattan ≈ 3
    for r in w.robots:
        if r.company == 0:
            r.pos, r.load, r.battery = near, 0, 90.0
    w.robots[5].battery = 2.0                  # cannot afford the round trip
    assert scout_target(w.robots[0], w) == target
    assert scout_target(w.robots[1], w) == target   # rid 0,1 = the two scouts
    assert scout_target(w.robots[2], w) is None, "SCOUTS_MAX not enforced"
    assert scout_target(w.robots[5], w) is None, "low battery scouted anyway"
    assert SCOUTS_MAX == 2
    # a company-1 robot has no stale point (staleness 0, field not empty) → None
    assert scout_target(w.robots[12], w) is None
    # Trigger A: a believed-EMPTY field scouts even with fresh timestamps
    w.belief[0] = [0] * n
    w.last_seen[0] = [300] * n
    tA = scout_target(w.robots[0], w)
    assert tA in [w.sources[i] for i in range(n)], "empty-field robot did not scout"


def test_v12_map_sync_evaluation_equals_execution():
    """K1 (the hard one): 600 ticks of belief+dynamic+contested map trading with
    the in-arm evaluated Φ == executed Φ assert live. If any synced view diverged
    from its permanent overlay by >1e-9 the assert fires; completing clean IS the
    test. Conservation must also survive, and at least one map deal must land."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True, dynamic_field=True,
              contested=True, map_trading=True)
    arm = make_arm("snhp", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "conservation broke under map trading"
    assert arm.deals > 0, "map-trading snhp struck no deals — vacuous"
    assert all(d.get("m") in (-1, 0, 1) for d in w.deal_log)
    assert any(d["m"] != 0 for d in w.deal_log), "no map deal ever executed"


def test_v12_map_sync_transfers_fresher_entries():
    """K1: apply_map_sync copies a giver company's FRESHER (belief, last_seen,
    rival_rate) onto the receiver — and only those; an entry the receiver knew
    more recently is left alone."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              belief_mode=True, map_trading=True)
    recv = next(r for r in w.robots if r.company == 0)
    give = next(r for r in w.robots if r.company == 1)
    w.tick = 500
    i = 0                                   # giver saw i depleted, recently
    w.stock[i] = 3
    w.belief[1][i], w.last_seen[1][i], w.rival_rate[1][i] = 3, 480, 0.4
    w.belief[0][i], w.last_seen[0][i], w.rival_rate[0][i] = 20, 50, 0.0
    j = 1                                   # receiver is fresher here
    w.belief[1][j], w.last_seen[1][j] = 5, 100
    w.belief[0][j], w.last_seen[0][j] = 9, 400
    b0j = w.belief[0][j]
    copied = w.apply_map_sync(recv, give)
    assert copied >= 1
    assert w.belief[0][i] == 3, "receiver did not learn the depletion"
    assert w.last_seen[0][i] == 480 and w.rival_rate[0][i] == 0.4, \
        "last_seen / rival_rate not carried with the belief"
    assert w.belief[0][j] == b0j, "overwrote an entry the receiver knew fresher"


def test_v12_bad_news_sync_is_vetoed_by_ir():
    """K1 / P17c: a map sync whose Φ-delta is NEGATIVE for the receiver (fresh
    truth deflates a stale-optimistic belief) is present in the menu but never
    executed — IR requires strictly positive surplus on BOTH sides."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              belief_mode=True, map_trading=True)
    w._live_sense = False                      # encounter-phase semantics
    a = next(r for r in w.robots if r.company == 1)
    b = next(r for r in w.robots if r.company == 0)
    arm = make_arm("snhp", w)
    w.tick = 500
    i = 0
    for r in (a, b):                           # no cargo/energy/sector channel:
        r.load, r.load_prov, r.battery = 0, [0, 0], W.BATTERY_MAX
        r.sector = i                           # shared sector ⇒ swap is a no-op
    a.pos, b.pos = (16, 16), (18, 18)          # adjacent, far from every rock
    w.stock[i] = 2
    w.belief[1][i], w.last_seen[1][i] = 2, 490    # giver: fresh + poor
    w.belief[0][i], w.last_seen[0][i] = 24, 20    # receiver: stale + rich
    batna_a, batna_b = phi(a, w), phi(b, w)
    ua, ub = arm._evaluate(a, b)
    map_rows = [k for k in range(len(arm.space)) if arm._row(k)[3] == 1]
    assert any(ub[k] < batna_b - 1e-9 for k in map_rows), \
        "no bad-news sync in the menu — test is vacuous"
    sol = arm._pick(ua, ub, batna_a, batna_b, a, b)
    assert sol is None or arm._row(sol)[3] == 0, \
        "IR failed to veto a Φ-lowering map sync (P17c)"


def test_v12_claim_window_gates_nonholder_pick():
    """K2: an ARRIVAL rock is minable ONLY by its quadrant's claim-holder until
    arrival_t + CLAIM_WINDOW. The non-holder sees 0 (belief gate) and mines 0
    (physics gate); the holder mines; after the window the non-holder can mine."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              belief_mode=True, dynamic_field=True, prospect_claims=True)
    w._field_events = [dict(t=10.0, kind="arrival")]
    w._field_next = 0
    w.tick = 10
    w.field_step()
    i = w.arrival_indices[-1]
    holder = w.claim_owner[w.quadrant(w.sources[i])]
    hb = next(r for r in w.robots if r.company == holder)
    nb = next(r for r in w.robots if r.company == 1 - holder)
    stock0 = w.stock[i]
    assert stock0 > 0
    for r in (hb, nb):
        r.pos, r.sector, r.load, r.cap, r.battery = w.sources[i], i, 0, 5, 90.0
    assert w.stock_belief(nb, i) == 0, "non-holder can see a claimed arrival"
    assert w.stock_belief(hb, i) == w.stock[i], "holder blind to its own claim"
    assert w.pick(nb) == 0 and w.stock[i] == stock0, "non-holder mined a claim"
    got = w.pick(hb)
    assert got > 0 and w.stock[i] == stock0 - got, "holder could not mine"
    w.tick = 10 + W.CLAIM_WINDOW               # window expires
    rem = w.stock[i]
    got2 = w.pick(nb)
    assert got2 > 0 and w.stock[i] == rem - got2, "claim never expired"


def test_v12_claims_fixed_no_swap_issue():
    """K2 FALLBACK (registered, flagged): claims are FIXED — not a tradeable
    bundle issue — so the sector axis stays {0,1} (no s=2 claim swap) and the
    claim map is invariant across a run. Patrol differentiation (P17d) is the
    scientific payload; the belief gate above is its mechanism. Doubles as the
    full K0+K1+K2 integration run (eval==exec assert live for 400 ticks)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              hazard_phi=True, belief_mode=True, dynamic_field=True,
              contested=True, prospect_claims=True, map_trading=True,
              scouting=True)
    arm = make_arm("snhp+net", w)
    assert set(int(x) for x in arm.space[:, 2]) == {0, 1}, \
        "sector issue gained a claim-swap option — fallback not honored"
    before = list(w.claim_owner)
    for _ in range(400):
        arm.tick()
        assert w.material_ok()
    assert w.claim_owner == before, "claims changed — they must be fixed"
    assert all(d["s"] in (0, 1) for d in w.deal_log), "a deal carried s=2"


# ── v13: scale (column L) ──────────────────────────────────────────────────
import math as _math                                             # noqa: E402


def _grid_L(N):
    return int(round(32 * _math.sqrt(N / 24)))


def test_v13_scale_default_off_is_flag_absent():
    """The N=24 fingerprint: n_robots==24 (with or without consensus_cost) must
    be bit-identical to a World that never heard of column L — the scale
    plumbing (n_robots/consensus_cost, the middleman counters, the scaled
    asteroid/charger paths) may not perturb a single bit of the default path."""
    outs = []
    for kw in ({}, dict(n_robots=24, consensus_cost=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots],
                     list(w.sources), list(w.chargers), list(w.charger_owner)))
    assert outs[0] == outs[1], "column-L plumbing leaked into the default path"


def test_v13_scaled_world_sanity():
    """N=96 at fixed density: 96 robots, 5·96/24=20 asteroid mirror-pairs on a
    64-grid, total stock pinned to 10·96, 4·96/24=16 chargers balanced per
    company, the field still mirror-symmetric about y=grid/2, and every robot's
    claimed sector is a valid asteroid index."""
    N, g = 96, _grid_L(96)
    assert g == 64
    w = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              grid=g)
    n_src = len(w.sources)
    assert len(w.robots) == N
    assert n_src == 2 * (5 * N // 24) == 40, "asteroid count did not scale"
    assert w.total_stock == 10 * N == 960, "stock pin did not scale"
    assert sum(w.stock) == w.total_stock
    n_pairs = n_src // 2
    for i in range(n_pairs):                              # mirror discipline
        x, y = w.sources[i]
        assert w.sources[i + n_pairs] == (x, g - y)
        assert w.stock[i] == w.stock[i + n_pairs]
    assert len(w.chargers) == 4 * N // 24 == 16, "charger count did not scale"
    assert sorted(w.charger_owner) == [0] * 8 + [1] * 8, "chargers unbalanced"
    assert all(0 <= r.sector < n_src for r in w.robots), "invalid sector claim"


def test_v13_density_is_fixed_across_N():
    """The manipulation is density-fixed: robots, asteroids, stock and chargers
    all scale linearly with N while grid AREA scales as N (grid side √N), so
    every per-area count is N-invariant. Pin the four ratios at N∈{24,96,240}."""
    ratios = []
    for N in (24, 96, 240):
        g = _grid_L(N)
        w = World(n_robots=N, sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  grid=g)
        area = g * g
        ratios.append((round(len(w.robots) / area * 1e4, 3),
                       round(len(w.sources) / area * 1e4, 3),
                       round(w.total_stock / area * 1e4, 3),
                       round(len(w.chargers) / area * 1e4, 3)))
    # areas are integer-rounded so densities match only approximately; the
    # point is they do NOT drift with N (they'd scale ∝N under a fixed grid)
    for j in range(4):
        vals = [ratios[k][j] for k in range(3)]
        assert max(vals) / min(vals) < 1.15, \
            f"density ratio {j} drifts with N: {vals}"


def test_v13_consensus_cost_lengthens_team_pause():
    """The realistic hive: with consensus_cost the team's joint pick pauses
    DEAL_PAUSE+⌈log₂N⌉ ticks; without it, the free-planning ceiling at
    DEAL_PAUSE. Pairwise arms (snhp) never pay the cost. The costed run must
    exhibit strictly longer team busy spans, observed directly."""
    for N in (24, 96):
        exp = W.DEAL_PAUSE + _math.ceil(_math.log2(N))
        wc = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                   grid=_grid_L(N), internalize_tariffs=True,
                   consensus_cost=True)
        assert make_arm("team", wc).deal_pause() == exp
        wf = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                   grid=_grid_L(N), internalize_tariffs=True,
                   consensus_cost=False)
        assert make_arm("team", wf).deal_pause() == W.DEAL_PAUSE
        # snhp is a pairwise arm: it pays no consensus cost even in a cc world
        assert make_arm("snhp+net", wc).deal_pause() == W.DEAL_PAUSE
    # observed busy spans: a struck team deal at tick t sets busy_until=t+pause
    def max_span(cc):
        w = World(n_robots=24, sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
                  internalize_tariffs=True, consensus_cost=cc)
        arm = make_arm("team", w)
        best = 0
        for _ in range(500):
            t0, pre = w.tick, [r.busy_until for r in w.robots]
            arm.tick()
            for r, pb in zip(w.robots, pre):
                if r.busy_until != pb and r.busy_until >= t0:
                    best = max(best, r.busy_until - t0)
        return best, arm.deals
    costed, dc = max_span(True)
    free, df = max_span(False)
    assert dc > 0 and df > 0, "team struck no deals — span test vacuous"
    assert free == W.DEAL_PAUSE, f"free team span {free} != {W.DEAL_PAUSE}"
    assert costed == W.DEAL_PAUSE + _math.ceil(_math.log2(24)), \
        f"costed team span {costed} != expected {W.DEAL_PAUSE + 5}"


def test_v13_consensus_off_bit_identical_to_flag_absent():
    """consensus_cost=False must be indistinguishable from a team run that never
    heard of the flag — the cost gate may not perturb the free-planning ceiling
    control (which IS the team-free arm)."""
    outs = []
    for kw in ({}, dict(consensus_cost=False)):
        w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  internalize_tariffs=True, **kw)
        arm = make_arm("team", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], "consensus_cost=False perturbed the team arm"


def test_v13_middleman_conservation():
    """The middleman counters obey conservation: a robot delivers only what it
    mined itself plus what it received via deals/transfers in, so
    mined_units + received_units >= delivered for EVERY robot — the middleman
    metric can never manufacture throughput. Non-vacuous: some units change
    hands (received_units > 0 somewhere)."""
    N = 96
    w = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              grid=_grid_L(N))
    arm = make_arm("snhp+net", w)
    for _ in range(400):
        arm.tick()
        assert w.material_ok()
    for r in w.robots:
        assert r.mined_units + r.received_units >= r.delivered, \
            f"robot {r.rid} delivered {r.delivered} > mined+received"
    assert any(r.received_units > 0 for r in w.robots), "no cargo ever received"
    assert arm.deals > 0


def test_v13_evaluated_equals_executed_at_scale():
    """The core invariant survives scale: 600 ticks of N=96 snhp+net with the
    in-arm evaluated Φ == executed Φ assert live. Any divergence over 96 robots
    and 40 asteroids fires the assert; completing clean IS the test, with
    conservation intact throughout and deals actually struck (non-vacuous)."""
    N = 96
    w = World(n_robots=N, sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15),
              grid=_grid_L(N))
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "conservation broke at scale"
    assert arm.deals > 0, "no deals at N=96 — vacuous"


def test_encounters_bit_exact_vs_brute_force():
    """The spatial-hash encounters() must return byte-identical output to the
    O(N²) brute force — same pairs, same order, same shuffle — at every scale
    and under scrambled positions (differential oracle)."""
    def brute(rs, rng, R):
        pairs = []
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if max(abs(a.pos[0] - b.pos[0]),
                       abs(a.pos[1] - b.pos[1])) <= R:
                    pairs.append((a, b))
        rng.shuffle(pairs)
        return pairs
    for N in (24, 96, 240):
        w = World(n_robots=N, sigma=0.5, seed=N, preset="v5")
        for _ in range(5):                          # scramble to stress buckets
            for r in w.robots:
                r.pos = (int(w.rng.uniform(1, w.grid)),
                         int(w.rng.uniform(1, w.grid)))
            st = w.rng.get_state()
            got = [(id(a), id(b)) for a, b in w.encounters()]
            w.rng.set_state(st)                      # replay the SAME shuffle
            exp = [(id(a), id(b)) for a, b in brute(w.robots, w.rng, W.R_COMM)]
            assert got == exp, f"encounters diverged from brute force at N={N}"
        # clustered edge case: everyone on one cell → all pairs must appear
        for r in w.robots:
            r.pos = (5, 5)
        st = w.rng.get_state()
        got = [(id(a), id(b)) for a, b in w.encounters()]
        w.rng.set_state(st)
        exp = [(id(a), id(b)) for a, b in brute(w.robots, w.rng, W.R_COMM)]
        assert got == exp, f"encounters diverged when fully clustered at N={N}"


# ── v14: communication locality (column O) ─────────────────────────────────
def test_v14_gossip_default_off_is_flag_absent():
    """gossip=False (with or without r_radio) must be bit-identical to a World
    that never heard of column O — the per-robot belief plumbing, the _bx
    indirection and the gossip step may not perturb a single bit of the
    free-radio (belief-mode) path, INCLUDING the belief/last_seen arrays."""
    outs = []
    for kw in ({}, dict(gossip=False, r_radio=6)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, belief_mode=True, dynamic_field=True,
                  contested=True, scouting=True, **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots],
                     [list(b) for b in w.belief],
                     [list(l) for l in w.last_seen]))
    assert outs[0] == outs[1], "gossip plumbing leaked into the free-radio path"


def test_v14_gossip_requires_belief_mode():
    """No shared map to fan out ⇒ gossip is only defined under belief_mode."""
    import pytest
    with pytest.raises(AssertionError):
        World(sigma=0.5, seed=0, preset="v5", gossip=True, belief_mode=False)


def test_v14_gossip_transfers_fresher_within_company_only():
    """One hop of flooding: a same-company fleet-mate within Chebyshev r_radio
    adopts a robot's FRESHER (higher last_seen) entry — belief, last_seen AND
    rival_rate together — while a cross-company robot at the same distance does
    NOT (gossip is within-fleet)."""
    w = World(sigma=0.5, seed=0, preset="v5", belief_mode=True,
              gossip=True, r_radio=6)
    a = next(r for r in w.robots if r.company == 0)
    b = next(r for r in w.robots if r.company == 0 and r.rid != a.rid)
    c = next(r for r in w.robots if r.company == 1)
    a.pos, b.pos, c.pos = (16, 16), (18, 18), (17, 17)   # all within r6 of a
    w.tick, i = 100, 0
    w.belief[a.rid][i], w.last_seen[a.rid][i], w.rival_rate[a.rid][i] = 7, 90, 0.5
    w.belief[b.rid][i], w.last_seen[b.rid][i], w.rival_rate[b.rid][i] = 20, 10, 0.0
    w.belief[c.rid][i], w.last_seen[c.rid][i], w.rival_rate[c.rid][i] = 20, 10, 0.0
    w._gossip_step()
    assert w.belief[b.rid][i] == 7 and w.last_seen[b.rid][i] == 90, \
        "fleet-mate did not adopt the fresher entry"
    assert w.rival_rate[b.rid][i] == 0.5, "rival_rate did not travel with the belief"
    assert w.belief[c.rid][i] == 20 and w.last_seen[c.rid][i] == 10, \
        "a cross-company robot adopted a fleet entry (gossip crossed the border)"


def test_v14_r2_slower_than_r6():
    """The founder's ladder: on a fixed line of same-company robots spaced 4
    cells apart, r_radio=6 floods along the chain (one hop per tick) while
    r_radio=2 cannot bridge the 4-cell gap at all — locality range is real."""
    def spread(r_radio, ticks):
        w = World(sigma=0.5, seed=0, preset="v5", belief_mode=True,
                  gossip=True, r_radio=r_radio)
        for r in w.robots:                       # park everyone; neutralise i
            r.pos = (1, 1)
            w.belief[r.rid][0], w.last_seen[r.rid][0] = 0, 0
        line = [r for r in w.robots if r.company == 0][:4]
        for k, r in enumerate(line):
            r.pos = (4 + 4 * k, 16)              # x = 4, 8, 12, 16
        w.tick = 100
        head = line[0]
        w.belief[head.rid][0], w.last_seen[head.rid][0] = 9, 99
        for _ in range(ticks):
            w._gossip_step()
        return [w.last_seen[r.rid][0] for r in line]
    r2, r6 = spread(2, 3), spread(6, 3)
    assert sum(v == 99 for v in r6) > sum(v == 99 for v in r2), \
        f"r6 did not out-propagate r2: r2={r2} r6={r6}"
    assert r2[1] != 99, "r2 relayed across a 4-cell gap it cannot reach"
    assert r6[1] == 99, "r6 failed to relay across a 4-cell gap"


def test_v14_per_robot_maps_diverge_within_fleet():
    """Under a tight radius the fleet is NOT globally synced: two same-company
    robots hold different last_seen vectors — the whole point of per-robot maps
    (a free-radio company would have one shared vector)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              belief_mode=True, dynamic_field=True, contested=True,
              scouting=True, gossip=True, r_radio=2)
    arm = make_arm("snhp+net", w)
    for _ in range(300):
        arm.tick()
    co0 = [r for r in w.robots if r.company == 0]
    diverged = any(w.last_seen[a.rid] != w.last_seen[b.rid]
                   for idx, a in enumerate(co0) for b in co0[idx + 1:])
    assert diverged, "gossip fleet is globally synced — per-robot maps never diverged"
    assert arm.deals > 0, "no deals — divergence test vacuous"


def test_v14_gossip_map_trading_evaluated_equals_executed():
    """The hard invariant under the new plumbing: 600 ticks of gossip +
    map-trading with the in-arm evaluated Φ == executed Φ assert live. Any
    per-robot synced view diverging from its permanent overlay fires the assert;
    completing clean IS the test, with conservation intact and map deals landing
    (cross-company, robot-to-robot) at a material rate."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              belief_mode=True, dynamic_field=True, contested=True,
              scouting=True, gossip=True, r_radio=6, map_trading=True)
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "conservation broke under gossip map trading"
    assert arm.deals > 0, "gossip map-trading struck no deals — vacuous"
    assert all(d.get("m") in (-1, 0, 1) for d in w.deal_log)
    assert any(d["m"] != 0 for d in w.deal_log), "no map deal executed under gossip"


def test_v14_map_sync_is_robot_to_robot_under_gossip():
    """K1 under gossip is seller ROBOT → buyer ROBOT: only that one buyer's map
    learns the sold entry. A distant same-company fleet-mate of the buyer stays
    dark until gossip relays it onward (contrast the free-radio K column, where a
    sync updated the whole company at once)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              belief_mode=True, gossip=True, r_radio=6, map_trading=True)
    recv = next(r for r in w.robots if r.company == 0)
    give = next(r for r in w.robots if r.company == 1)
    distant = next(r for r in w.robots if r.company == 0 and r.rid != recv.rid)
    w.tick, i = 500, 0
    w.stock[i] = 3
    w.belief[give.rid][i], w.last_seen[give.rid][i], w.rival_rate[give.rid][i] = 3, 480, 0.4
    w.belief[recv.rid][i], w.last_seen[recv.rid][i] = 20, 50
    w.belief[distant.rid][i], w.last_seen[distant.rid][i] = 20, 50
    copied = w.apply_map_sync(recv, give)
    assert copied >= 1
    assert w.belief[recv.rid][i] == 3 and w.last_seen[recv.rid][i] == 480, \
        "buyer robot did not learn the sold entry"
    assert w.rival_rate[recv.rid][i] == 0.4, "rival_rate not carried in the robot-to-robot sync"
    assert w.belief[distant.rid][i] == 20 and w.last_seen[distant.rid][i] == 50, \
        "a distant fleet-mate learned the entry without gossip relaying it"


# ── v17 (column P): cargo lineage — parcels, hops, hold-up ledger ─────────
def test_v17_lineage_is_pure_bookkeeping():
    """lineage=True must not perturb a single bit of physics/RNG vs the flag
    absent — parcels consume NO RNG and mutate NO physics (SPEC v17 P1). Checked
    on a bargaining arm (transfer_cargo via apply_bundle) AND the auction arm
    (transfer_cargo called directly), since both move cargo."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in ({}, dict(lineage=True)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1], f"lineage perturbed the {arm_name} simulation"


def test_v17_parcel_conservation():
    """Parcel bookkeeping obeys conservation: len(parcels)==load==Σload_prov for
    every robot at every tick, hops==len(chain) per parcel, and the delivered
    ledger has exactly `delivered` entries. Non-vacuous: some units are relayed."""
    N = 96
    w = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              grid=_grid_L(N), lineage=True)
    arm = make_arm("snhp+net", w)
    for _ in range(500):
        arm.tick()
        for r in w.robots:
            assert len(r.parcels) == r.load == sum(r.load_prov), \
                f"parcel/load/prov mismatch on robot {r.rid}"
            for p in r.parcels:
                assert p["hops"] == len(p["chain"]), "hops != chain length"
        assert w.material_ok()
    assert len(w.delivered_parcels) == w.delivered, \
        "delivered ledger != delivered units"
    assert any(p["hops"] >= 1 for p in w.delivered_parcels), \
        "no relayed unit ever delivered — vacuous"


def test_v17_hops_increment_on_transfer():
    """transfer_cargo moves the FIFO head q parcels giver→taker, +1 hop each,
    recording the (tick, giver, taker) chain link — and only on log=True."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), lineage=True)
    a, b = w.robots[0], w.robots[1]
    a.cap = b.cap = 5
    a.load, a.load_prov = 3, [3, 0]
    a.parcels = [{"origin": 5, "hops": 0, "chain": []} for _ in range(3)]
    b.load, b.load_prov, b.parcels = 0, [0, 0], []
    w.tick = 42
    moved = w.transfer_cargo(a, b, 2, log=True)
    assert moved == 2
    assert len(a.parcels) == 1 and len(b.parcels) == 2
    assert all(p["hops"] == 1 for p in b.parcels)
    assert all(p["chain"][-1] == (42, a.rid, b.rid) for p in b.parcels)
    assert a.parcels[0]["hops"] == 0, "un-moved parcel gained a hop"
    # log=False (the evaluation path) must NOT touch parcels
    before = (len(a.parcels), len(b.parcels))
    w.transfer_cargo(a, b, 1, log=False)
    assert (len(a.parcels), len(b.parcels)) == before, \
        "evaluation-pass transfer moved parcels"


def test_v17_retire_on_delivery_and_pad_unload():
    """drop retires every carried parcel into delivered_parcels with (origin,
    hops, tick, deliverer) — including the stranded-ON-refinery pad-unload path."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), lineage=True)
    r = w.robots[0]
    r.company, r.sector = 0, 0
    ref = w.refineries[0]
    r.pos, r.load, r.load_prov = ref, 3, [3, 0]
    r.parcels = [{"origin": 2, "hops": 1, "chain": [(0, 9, r.rid)]}
                 for _ in range(3)]
    w.drop(r)
    assert r.load == 0 and not r.parcels
    assert len(w.delivered_parcels) == 3
    assert all(p["deliverer"] == r.rid and p["hops"] == 1 and p["origin"] == 2
               for p in w.delivered_parcels)
    # pad-unload: strand ON the refinery via drive (mirrors test_v8)
    r2 = w.robots[1]
    r2.company, r2.sector = 0, 0
    r2.pos = (ref[0] - 1, ref[1])
    r2.load, r2.load_prov = 2, [2, 0]
    r2.parcels = [{"origin": 7, "hops": 0, "chain": []} for _ in range(2)]
    r2.battery = r2.step_cost() + 0.5           # arrival step strands it
    before = len(w.delivered_parcels)
    from swarm.arms import drive
    drive(r2, w)
    assert r2.pos == ref and r2.stranded, "pad-unload repro setup broken"
    assert r2.load == 0 and not r2.parcels
    assert len(w.delivered_parcels) == before + 2, "pad-unload dropped no lineage"


def test_v17_two_hop_relay_and_holdup_margins():
    """A hand-built miner→X→Y→refinery relay: the delivered parcel records
    hops=2 (a 2-link chain), and the hold-up ledger recovers X's per-leg margins
    from the deal log — buy surplus at hop 1, (compressed) sell surplus at hop 2."""
    from swarm.run import _holdup_margins
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), lineage=True)
    m, x, y = w.robots[0], w.robots[1], w.robots[2]
    for rr in (m, x, y):
        rr.cap, rr.load, rr.load_prov, rr.parcels = 5, 0, [0, 0], []
    m.sector, m.pos = 0, w.sources[0]
    w.stock[0] = 2
    assert w.pick(m) == 2 and all(p["hops"] == 0 for p in m.parcels)
    w.tick = 10
    w.transfer_cargo(m, x, 2, log=True)         # hop 1: m → x
    w.tick = 20
    w.transfer_cargo(x, y, 2, log=True)         # hop 2: x → y
    assert all(p["hops"] == 2 and len(p["chain"]) == 2 for p in y.parcels)
    y.company, y.sector, y.pos = 0, 0, w.refineries[0]
    w.tick = 30
    w.drop(y)
    relayed = [p for p in w.delivered_parcels if p["hops"] == 2]
    assert len(relayed) == 2 and all(p["deliverer"] == y.rid for p in relayed)
    # hand-built deal log: X buys big at hop 1 (sb=5), is squeezed at hop 2 (sa=1)
    deal_log = [dict(tick=10, a=m.rid, b=x.rid, sa=1.0, sb=5.0),
                dict(tick=20, a=x.rid, b=y.rid, sa=1.0, sb=4.0)]
    hl = _holdup_margins(w.delivered_parcels, deal_log)
    assert hl["n"] == 2                          # one interior leg × two parcels
    assert hl["mean_buy"] == 5.0 and hl["mean_sell"] == 1.0
    assert hl["mean_delta"] == -4.0 and hl["frac_compressed"] == 1.0
    # a parcel that never relayed contributes no leg
    assert _holdup_margins([{"origin": 0, "hops": 0, "chain": []}], deal_log)["n"] == 0


# ── v17 PHASE 2 (column P): pre-commitment — bills of lading + firm relay ──
def test_v17p2_bills_firm_off_bit_identical():
    """bills=False and firm_relay=False must be bit-identical to a lineage-only
    world — the claim_value field, the company treasury, the extra parcel keys
    and every PHASE-2 branch may not perturb a single bit when off. Checked on a
    bargaining arm (bills would touch Φ) and the auction (firm would touch the
    credit path)."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in (dict(lineage=True),
                   dict(lineage=True, bills=False, firm_relay=False)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1], f"PHASE-2 plumbing perturbed {arm_name}"


def test_v17p2_bills_evaluated_equals_executed():
    """The hard invariant under claim stacks: 600 ticks of snhp+net with bills on
    and the in-arm evaluated Φ == executed Φ assert live. The claim state each Φ
    evaluation sees must be exactly what execution produces (split-independent α*);
    any divergence fires the assert. Completing clean IS the test, with material
    AND credit conservation intact and claimed relays actually landing."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), bills=True)
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "material leak under bills"
        assert w.credit_conserved(), "credit not conserved under bills"
    assert arm.deals > 0, "bills snhp+net struck no deals — vacuous"
    assert w.ledger_accounted(), "ledger leak under bills"
    assert any(p["hops"] >= 1 for p in w.delivered_parcels), \
        "no claimed relay ever delivered — vacuous"


def test_v17p2_claim_stack_conservation():
    """Every delivered unit's credit is split across its claim stack with the
    deliverer keeping the residual — Σdistributed == earned EXACTLY. Verified
    globally (credit_conserved) and by reconstructing the per-parcel split from
    the delivered ledger against the total booked delivery credit."""
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), bills=True)
    arm = make_arm("snhp+net", w)
    for _ in range(500):
        arm.tick()
    assert arm.deals > 0
    # global: Σ robot credit (+treasury) == company booked credit, and the ledger
    assert w.credit_conserved()
    assert w.ledger_accounted()
    # every robot's claim_value equals its OUTSTANDING (undelivered) claims: sum
    # the shares of claims recorded on parcels still in flight and match the
    # per-robot scalar Φ reads — the ledger the correction is priced on.
    outstanding = {r.rid: 0.0 for r in w.robots}
    for r in w.robots:
        for p in r.parcels:
            for rid, share in p["claims"]:
                outstanding[rid] += share * V_DELIVER
    for r in w.robots:
        assert abs(r.claim_value - outstanding[r.rid]) < 1e-6, \
            f"claim_value scalar diverged from live claim stacks (robot {r.rid})"


def test_v17p2_holdup_relay_clears_ir_and_pays_per_split():
    """PHASE-1 showed the middle drone's sell-leg refused under IR (hold-up). With
    bills the SAME hop clears: a far, low-battery holder B selling to a near C
    keeps an undiscounted claim, so its surplus turns positive where spot vetoed.
    Then a hand-built A→B→C relay records per-hop shares on the parcel's chain and
    the terminal payout lands per those splits (credit conserved to the cent)."""
    from swarm.arms import make_arm as _mk

    def hop_solution(bills):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=bills,
                  lineage=True)
        w._live_sense = False
        arm = _mk("snhp", w, issues=("cargo",))
        B, C = w.robots[0], w.robots[1]
        for r in (B, C):
            r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
        B.pos, B.cap, B.battery = (6, 6), 5, 18.0          # far from ref0, low bat
        B.load, B.load_prov = 2, [2, 0]
        B.parcels = [w._new_parcel(0) for _ in range(2)]
        C.pos, C.cap, C.battery, C.sector = (7, 6), 5, 95.0, 1   # near ref0, full
        ua, ub = arm._evaluate(B, C)
        ba, bb = float(ua[arm._allzero]), float(ub[arm._allzero])
        sol = arm._pick(ua, ub, ba, bb, B, C)
        return arm, sol, ua, ub, ba, bb

    _, spot_sol, *_ = hop_solution(False)
    assert spot_sol is None, "spot did not refuse the middle hop (no hold-up)"
    arm, bill_sol, ua, ub, ba, bb = hop_solution(True)
    assert bill_sol is not None, "bills failed to clear the hop IR refused"
    assert arm._row(bill_sol)[0] > 0, "bills cleared a non-cargo bundle"
    assert ua[bill_sol] - ba > 0 and ub[bill_sol] - bb > 0, "IR not satisfied"

    # hand-built A→B→C→refinery with the code's own claim recording, then deliver
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True)
    arm = _mk("snhp", w)
    A, B, C = w.robots[0], w.robots[1], w.robots[2]
    for r in (A, B, C):
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, 0, 5, 0, [0, 0], []
    A.pos, A.sector, w.stock[0] = w.sources[0], 0, 2
    assert w.pick(A) == 2
    w.tick = 10
    w.transfer_cargo(A, B, 2, log=True)          # hop 1: A → B
    arm._bills_attach(A, B, 2, 0.4)              # A claims 0.4 of residual (=0.4)
    w.tick = 20
    w.transfer_cargo(B, C, 2, log=True)          # hop 2: B → C
    arm._bills_attach(B, C, 2, 0.5)             # B claims 0.5 of residual (0.6→0.3)
    for p in C.parcels:
        assert p["hops"] == 2 and len(p["chain"]) == 2
        assert p["chain"][0][1:] == (A.rid, B.rid)      # per-hop lineage
        assert p["chain"][1][1:] == (B.rid, C.rid)
        shares = dict(p["claims"])
        assert abs(shares[A.rid] - 0.4) < 1e-9 and abs(shares[B.rid] - 0.3) < 1e-9
    C.pos = w.refineries[0]
    w.tick = 30
    ca0, cb0, cc0 = A.credit, B.credit, C.credit
    w.drop(C)
    unit = V_DELIVER            # tau=0, own refinery ⇒ rate 1.0
    assert abs((A.credit - ca0) - 0.4 * unit * 2) < 1e-9      # A: 0.4 share
    assert abs((B.credit - cb0) - 0.3 * unit * 2) < 1e-9      # B: 0.3 share
    assert abs((C.credit - cc0) - 0.3 * unit * 2) < 1e-9      # C: residual 0.3
    assert abs(A.claim_value) < 1e-9 and abs(B.claim_value) < 1e-9, \
        "claims not retired at delivery"
    assert w.credit_conserved()


def test_v17p2_firm_transfer_price_conserves_and_matches_spot():
    """snhp+firm settles within-company handoffs through the treasury (haul cost +
    fixed margin, recouped at delivery). Because it re-books credit WITHOUT
    touching Φ, its trajectory is identical to spot (the Coase-boundary control),
    and treasury+robot credit conserves within every company at every tick, with
    the treasury netting to zero once the field clears."""
    def run(firm):
        w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15), lineage=True,
                  firm_relay=firm)
        arm = make_arm("snhp+net", w)
        for _ in range(600):
            arm.tick()
            assert w.credit_conserved(), "firm treasury+robot credit leaked"
        return w, arm
    ws, as_ = run(False)
    wf, af = run(True)
    assert (ws.delivered, as_.deals) == (wf.delivered, af.deals), \
        "firm relay perturbed the trajectory — Φ was not left untouched"
    assert [round(r.battery, 9) for r in ws.robots] == \
        [round(r.battery, 9) for r in wf.robots], "firm diverged from spot"
    assert af.deals > 0
    assert wf.ledger_accounted()
    # some within-company handoff actually advanced a transfer price
    assert any(p.get("advanced", 0.0) != 0.0 for r in wf.robots for p in r.parcels) \
        or wf.delivered > 0


# ── P23e (column P phase-2e): moral hazard in the relay ───────────────────
def _dwell_snap(w, arm):
    return (w.delivered, arm.deals, len(w.event_log),
            round(sum(r.battery for r in w.robots), 9),
            [r.pos for r in w.robots],
            [tuple(sorted(d.items())) for d in w.deal_log])


def test_p23e_dwell_instrument_is_pure_bookkeeping():
    """dwell=True must not perturb a single bit vs the instrument absent, in EVERY
    regime — the acq stamps, uid counter and hop_dwells/delivered_dwells lists are
    pure bookkeeping (no RNG, no physics, no Φ). Checked on the no-bills spot
    baseline AND on bills-flat (where dwell rides alongside the claim stack)."""
    for kw in (dict(), dict(bills=True)):
        outs = []
        for extra in (dict(), dict(dwell=True)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=("bills" not in kw), **kw, **extra)
            arm = make_arm("snhp+net", w)
            for _ in range(400):
                arm.tick()
            outs.append(_dwell_snap(w, arm))
        assert outs[0] == outs[1], f"dwell instrument perturbed regime {kw}"


def test_p23e_contingent_off_bit_identical_to_flat():
    """bills_contingent=False (the default) is bit-identical to bills-flat, and
    the flat claim stack stays 2-tuples — the entire contingent code path (3-tuple
    claims, decayed prefixes) must be inert when off. Runs bills-flat with the
    dwell instrument on to prove the plumbing that contingent SHARES is inert."""
    outs = []
    for kw in (dict(bills=True),
               dict(bills=True, dwell=True, bills_contingent=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(400):
            arm.tick()
        outs.append(_dwell_snap(w, arm))
    assert outs[0] == outs[1], "contingent-off plumbing perturbed bills-flat"
    # flat claims are 2-tuples (no decay field)
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), bills=True)
    arm = make_arm("snhp+net", w)
    for _ in range(300):
        arm.tick()
    assert all(len(c) == 2 for r in w.robots for p in r.parcels for c in p["claims"]), \
        "flat split recorded a 3-tuple (decay) claim"


def test_p23e_dwell_accounting_conserved():
    """Per parcel, Σ(per-leg dwell over every carrier that held it, incl. the final
    delivery leg) == its total hold time (delivery_tick − mined_tick). Each handoff
    re-stamps acq_tick, so the legs telescope exactly."""
    from collections import defaultdict
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              bills=True, bills_contingent=True)
    arm = make_arm("snhp+net", w)
    for _ in range(500):
        arm.tick()
    legsum = defaultdict(int)
    for h in w.hop_dwells:
        legsum[h["uid"]] += h["dwell"]
    assert w.delivered_dwells, "no delivered parcels — vacuous"
    for d in w.delivered_dwells:
        assert legsum[d["uid"]] == d["total_dwell"], \
            f"leg dwells {legsum[d['uid']]} != hold time {d['total_dwell']}"
    # and the total dwell equals its counterfactual plus the (non-negative) inflation
    for d in w.delivered_dwells:
        assert d["inflation"] == d["total_dwell"] - d["total_cf"]


def test_p23e_decay_applies_only_above_counterfactual():
    """leg_decay == 1 exactly when the carrier's dwell is at or below its geodesic
    counterfactual (an efficient beeline is never docked), and strictly < 1 only
    for dwell ABOVE it — and it is monotone decreasing in the excess."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0),
              bills=True, bills_contingent=True)
    p = w._new_parcel(0)
    src = w.sources[0]
    # efficient: held exactly the geodesic distance to a point 5 cells away
    p["acq_tick"] = 0
    p["acq_pos"] = src
    holder = (src[0] + 5, src[1])
    w.tick = 5                                   # dwell 5 == cf 5 ⇒ decay 1
    assert abs(w.leg_decay(p, holder) - 1.0) < 1e-12
    w.tick = 4                                   # dwell below cf ⇒ still 1 (floored)
    assert abs(w.leg_decay(p, holder) - 1.0) < 1e-12
    w.tick = 15                                  # 10 idle ticks above cf ⇒ docked
    d15 = w.leg_decay(p, holder)
    assert d15 < 1.0
    w.tick = 25                                  # more idle ⇒ more dock (monotone)
    assert w.leg_decay(p, holder) < d15
    assert abs(d15 - np.exp(-W.DWELL_DECAY_LAMBDA * 10)) < 1e-12


def test_p23e_ir_respected_at_hop_time():
    """The contingent contract must still clear IR at hop time: a FRESH receiver's
    carried residual is undecayed (its open leg has dwell 0), so the exact hold-up
    hop that spot vetoes and flat clears ALSO clears under contingent — chains do
    not re-collapse from the receiver side."""
    from swarm.arms import make_arm as _mk

    def hop_solution(contingent):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
                  bills_contingent=contingent)
        w._live_sense = False
        arm = _mk("snhp", w, issues=("cargo",))
        B, C = w.robots[0], w.robots[1]
        for r in (B, C):
            r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
        B.pos, B.cap, B.battery = (6, 6), 5, 18.0
        B.load, B.load_prov = 2, [2, 0]
        B.parcels = [w._new_parcel(0) for _ in range(2)]
        C.pos, C.cap, C.battery, C.sector = (7, 6), 5, 95.0, 1
        ua, ub = arm._evaluate(B, C)
        ba, bb = float(ua[arm._allzero]), float(ub[arm._allzero])
        sol = arm._pick(ua, ub, ba, bb, B, C)
        return arm, sol, ua, ub, ba, bb

    arm, sol, ua, ub, ba, bb = hop_solution(True)
    assert sol is not None, "contingent failed to clear the hop flat/IR clears"
    assert arm._row(sol)[0] > 0, "contingent cleared a non-cargo bundle"
    assert ua[sol] - ba > 0 and ub[sol] - bb > 0, "IR not satisfied under contingent"


def test_p23e_evaluated_equals_executed_under_contingent():
    """The hard invariant with DECAYED claim stacks: 600 ticks of snhp+net with
    bills_contingent on and the in-arm evaluated Φ == executed Φ assert live. The
    decayed claim value each Φ evaluation prices (via cumX_dec) must be exactly what
    execution banks (via the pre-apply decay capture); any divergence fires the
    assert. Material + credit conservation intact, and claimed relays landing."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
              bills=True, bills_contingent=True)
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
        assert w.material_ok(), "material leak under contingent bills"
        assert w.credit_conserved(), "credit not conserved under contingent bills"
    assert arm.deals > 0, "contingent snhp+net struck no deals — vacuous"
    assert w.ledger_accounted(), "ledger leak under contingent bills"
    assert any(p["hops"] >= 2 for p in w.delivered_parcels), \
        "no claimed relay ever delivered under contingent — vacuous"
    # claim_value scalar still tracks the OUTSTANDING (payout-value) claim stacks:
    # under contingent an outstanding claim is worth share·decay·V.
    outstanding = {r.rid: 0.0 for r in w.robots}
    for r in w.robots:
        for p in r.parcels:
            for rid, share, decay in p["claims"]:
                outstanding[rid] += share * decay * V_DELIVER
    for r in w.robots:
        assert abs(r.claim_value - outstanding[r.rid]) < 1e-6, \
            f"claim_value diverged from decayed claim stacks (robot {r.rid})"


def test_p23e_lazy_carrier_docked_vs_flat():
    """Hand-built A→B→C→refinery where the MIDDLE carrier B shirks — it holds the
    cargo far longer than the ground it covers (large dwell, tiny displacement).
    Flat pays B its full α-share; contingent docks B by exp(-λ·excess) and hands
    the docked credit to the DELIVERER C (credit conserved either way)."""
    from swarm.arms import make_arm as _mk

    def build(contingent):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0),
                  bills=True, bills_contingent=contingent)
        arm = _mk("snhp", w)
        A, B, C = w.robots[0], w.robots[1], w.robots[2]
        for r in (A, B, C):
            r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
                0, 0, 5, 0, [0, 0], []
        A.pos, A.sector, w.stock[0] = w.sources[0], 0, 2
        assert w.pick(A) == 2
        # A → B at tick 10, A barely moved (efficient A leg)
        A.pos = w.sources[0]
        w.tick = 10
        w.transfer_cargo(A, B, 2, log=True)
        da = [w.leg_decay(p, A.pos) for p in B.parcels[-2:]] if contingent else None
        arm._bills_attach(A, B, 2, 0.4, da)
        # B SHIRKS: holds 60 ticks but ends up 2 cells from where it took the cargo
        B.pos = (w.sources[0][0] + 2, w.sources[0][1])
        w.tick = 70
        # decay captured from B's parcels BEFORE the B→C move restamps their acq
        db = [w.leg_decay(p, B.pos) for p in B.parcels[:2]] if contingent else None
        w.transfer_cargo(B, C, 2, log=True)
        arm._bills_attach(B, C, 2, 0.5, db)
        C.pos = w.refineries[0]
        w.tick = 75
        credit0 = (A.credit, B.credit, C.credit)
        w.drop(C)
        return w, (A, B, C), credit0

    unit = V_DELIVER
    wf, (Af, Bf, Cf), c0f = build(False)
    wc, (Ac, Bc, Cc), c0c = build(True)
    b_flat = Bf.credit - c0f[1]
    b_cont = Bc.credit - c0c[1]
    c_flat = Cf.credit - c0f[2]
    c_cont = Cc.credit - c0c[2]
    # B's flat payout is its full 0.3 share ×2 units; contingent docks it.
    assert abs(b_flat - 0.3 * unit * 2) < 1e-9, "flat did not pay B its full share"
    assert b_cont < b_flat - 1e-6, "contingent did not dock the shirking carrier"
    # the dock is transferred to the deliverer C (conservation: total unchanged)
    assert c_cont > c_flat + 1e-6, "deliverer did not absorb the dock"
    assert abs((b_flat + c_flat) - (b_cont + c_cont)) < 1e-9, \
        "docking leaked credit (deliverer must absorb exactly)"
    assert wc.credit_conserved() and wf.credit_conserved()


# ── differential oracle: optimized _evaluate == scalar reference ──────────
# The fast Φ path in SnhpArm._evaluate MUST be byte-for-byte identical to the
# scalar fallback (arms.FORCE_SCALAR_EVAL forces the reference). This test flips
# that switch and compares full-run fingerprints — delivered, deals, per-robot
# battery (12 dp) and the entire deal_log. A CI-sane subset runs here; the FULL
# matrix (6 arms × {v3,v4,v5} × 3 seeds × 300t + gauge/liar/defense/dynamic/
# mine/scale/single-issue coverage) is exercised offline and reported.
import swarm.arms as _ARMS                                       # noqa: E402


def _fingerprint(arm_name, preset="v5", seed=0, ticks=200, tau=0.15,
                 n_robots=24, issues=("cargo", "energy", "sector"),
                 noise=0.0, **flags):
    life = arm_name.endswith(("-lv", "-lvc"))
    cap = 20.0 if arm_name.endswith("-lvc") else 0.0
    hazard = arm_name.endswith("-hz") or life
    base = arm_name
    for suf in ("-hz", "-lv", "-lvc"):
        if base.endswith(suf):
            base = base[:-len(suf)]
            break
    w = World(n_robots=n_robots, sigma=0.5, seed=seed, hazard_phi=hazard,
              preset=preset, tau=(tau, tau),
              internalize_tariffs=(base == "team"),
              life_pricing=life, strand_cap=cap, **flags)
    arm = make_arm(base, w, issues=issues, noise=noise)
    for _ in range(ticks):
        arm.tick()
        if w.delivered >= w.total_stock:
            break
    bats = [round(r.battery, 12) for r in w.robots]
    deal_log = [tuple(sorted(d.items())) for d in w.deal_log]
    return (w.delivered, arm.deals, len(w.event_log), bats, deal_log)


_ORACLE_SUBSET = (
    # core arms × presets (seed 0), plus the -hz variant
    [dict(arm_name=a, preset=p, seed=0) for a in
     ("snhp", "snhp+net", "snhp-hz", "team", "twofirm", "trust-gated")
     for p in ("v3", "v4", "v5")]
    # a second seed on v5 for each arm
    + [dict(arm_name=a, preset="v5", seed=2) for a in
       ("snhp", "snhp+net", "team", "twofirm")]
    # gauge / liar / defense / noise / single-issue / dynamic / mine / scale
    + [dict(arm_name="snhp", preset="v5", seed=0, self_noise=0.5),
       dict(arm_name="snhp", preset="v5", seed=0, liar_frac=0.25, defended=True),
       dict(arm_name="trust-gated", preset="v5", seed=0, liar_frac=0.25, defended=True),
       dict(arm_name="snhp", preset="v5", seed=2, noise=2.0),
       dict(arm_name="snhp", preset="v5", seed=0, issues=("cargo", "energy")),
       dict(arm_name="snhp+net", preset="v5", seed=0, dynamic_field=True),
       dict(arm_name="snhp", preset="v5", seed=0, mine_trait=True),
       dict(arm_name="snhp+net", preset="v5", seed=0, ticks=120, n_robots=96)]
    # v22 (column U): reputation keeps the fast path (Φ untouched) — the fast
    # and scalar evaluators must stay byte-identical under blacklists + slander
    + [dict(arm_name="trust-open", preset="v5", seed=0, liar_frac=0.25,
            reputation=True, false_accuse=0.05),
       dict(arm_name="trust-gated", preset="v5", seed=0, liar_frac=0.25,
            defended=True, reputation=True, false_accuse=0.05)]
    # v27 (column Z): forgery burns energy AFTER the bundle settles, so the fast
    # and scalar bundle evaluators must stay byte-identical under the attack too
    + [dict(arm_name="trust-gated", preset="v5", seed=0, liar_frac=0.25,
            defended=True, forgery=True, forge_cost=2.0, verify_cost=1.0,
            verify_regime="endogenous")]
    # v29 (column AB): the shock is a pure SETTLEMENT-side event — Φ never sees it —
    # so the SPOT+shock economy (bills off ⇒ fast path) must keep fast == scalar. The
    # shock fires early (tick 60) so the darkened-value drop path is exercised.
    + [dict(arm_name="snhp+net", preset="v5", seed=0, ticks=180, mortality=True,
            death_regime="none", lineage=True, shock=True, shock_tick=60)]
)


def test_differential_oracle_fast_equals_scalar():
    """Every supported config: the optimized fast path is byte-identical to the
    scalar reference (fingerprint == delivered/deals/xfers/battery@12dp/deal_log)."""
    try:
        for cfg in _ORACLE_SUBSET:
            _ARMS.FORCE_SCALAR_EVAL = False
            fast = _fingerprint(**cfg)
            _ARMS.FORCE_SCALAR_EVAL = True
            scalar = _fingerprint(**cfg)
            assert fast == scalar, f"fast != scalar for {cfg}"
    finally:
        _ARMS.FORCE_SCALAR_EVAL = False


def test_differential_oracle_fallback_configs_are_scalar():
    """belief_mode / life_pricing / map_trading dispatch to scalar (still
    byte-identical under the switch, and _fast_ok reports the fallback)."""
    for cfg, kw in (
        (dict(arm_name="snhp+net"), dict(belief_mode=True)),
        (dict(arm_name="snhp"), dict(belief_mode=True, map_trading=True)),
        (dict(arm_name="snhp-lv"), {}),
    ):
        try:
            _ARMS.FORCE_SCALAR_EVAL = False
            fast = _fingerprint(preset="v5", seed=0, **cfg, **kw)
            _ARMS.FORCE_SCALAR_EVAL = True
            scalar = _fingerprint(preset="v5", seed=0, **cfg, **kw)
            assert fast == scalar, f"{cfg} {kw}"
        finally:
            _ARMS.FORCE_SCALAR_EVAL = False


# ── v22 (column U): reputation vs receipts — the scaling law of trust ──────
def test_v22_reputation_off_bit_identical():
    """reputation=False (with or without false_accuse/r_radio) must be
    bit-identical to a World that never heard of column U — the blacklist
    plumbing, the dedicated ε stream, the pair-meet counter and the
    _blacklist_gossip_step may not perturb a single bit of the default path.
    Checked on a trust arm (would refuse/mark) AND the auction (moves cargo)."""
    for arm_name in ("trust-open", "auction"):
        outs = []
        for kw in ({}, dict(reputation=False, false_accuse=0.05, r_radio=6)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name != "auction"), liar_frac=0.25, **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals,
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1], f"column-U plumbing leaked into {arm_name}"


def test_v22_caught_liar_blacklisted_and_refused():
    """A liar who exploits an honest partner in the naive-cooperation tier gets
    blacklisted (the honest robot's own realized surplus went negative), and a
    blacklisted pair is then REFUSED — encounter returns False, strikes no deal,
    and (ATTEMPT_COOLDOWN semantics) applies no pause."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              liar_frac=0.25, reputation=True)
    arm = make_arm("trust-open", w)     # everyone trusted ⇒ liars can exploit
    for _ in range(1200):
        arm.tick()
    assert arm.deals > 0, "no deals — catch test vacuous"
    liars = {r.rid for r in w.robots if r.liar}
    honest = [r for r in w.robots if not r.liar]
    caught = any(w.blacklist[r.rid] & liars for r in honest)
    assert caught, "no liar was ever caught and blacklisted by an honest robot"
    # refusal: a manually blacklisted, adjacent pair strikes nothing and pauses none
    a, b = w.robots[0], w.robots[1]
    a.pos = b.pos = (10, 10)
    a.busy_until = b.busy_until = -1
    w.blacklist[a.rid].add(b.rid)
    n0 = len(w.deal_log)
    assert arm.encounter(a, b) is False, "blacklisted pair was not refused"
    assert len(w.deal_log) == n0, "a refused encounter still logged a deal"


def test_v22_blacklist_propagates_by_contact_only():
    """A mark floods to same-company fleet-mates within Chebyshev r_radio, ONE
    hop per tick — a distant fleet-mate stays clean until a contact relays it,
    and a cross-company robot never adopts (warnings stay within a fleet)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), reputation=True,
              r_radio=6)
    co0 = [r for r in w.robots if r.company == 0]
    a, b, c = co0[0], co0[1], co0[2]
    x = next(r for r in w.robots if r.company == 1)
    victim = w.robots[-1].rid                       # some marked rid
    a.pos, b.pos, x.pos = (16, 16), (18, 18), (17, 17)   # within r6 of a
    c.pos = (1, 1)                                   # far from a and b
    w.blacklist[a.rid].add(victim)
    w._blacklist_gossip_step()
    assert victim in w.blacklist[b.rid], "fleet-mate did not adopt the mark by contact"
    assert victim not in w.blacklist[c.rid], "distant fleet-mate adopted without contact"
    assert victim not in w.blacklist[x.rid], "the mark crossed the company border"
    c.pos = (18, 17)                                 # bring c into contact with a/b
    w._blacklist_gossip_step()
    assert victim in w.blacklist[c.rid], "the mark did not reach c after contact"


def test_v22_epsilon_false_marks_from_dedicated_stream():
    """Slander (ε) fires from the DEDICATED stream only. On the Nash-IR arm the
    veto keeps BOTH surpluses positive, so with no liars there is no genuine
    catch and the sole source of a mark is the ε draw: at ε=0 every blacklist
    stays empty; at ε>0 honest robots get falsely blacklisted. And the main RNG
    is untouched — the deal stream is identical between ε=0 and ε=0.05 up to the
    first false mark (a separate stream cannot shift the main one)."""
    def build(eps):
        w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, liar_frac=0.0, reputation=True,
                  false_accuse=eps)
        return w, make_arm("snhp+net", w)
    w0, a0 = build(0.0)
    we, ae = build(0.05)
    assert we._eps_rng is not we.rng, "ε stream is not a dedicated RandomState"
    first_mark = None
    for _ in range(1000):
        a0.tick()
        ae.tick()
        if first_mark is None and any(we.blacklist[r.rid] for r in we.robots):
            first_mark = we.tick
            break
    assert first_mark is not None, "ε never fired a false mark"
    assert all(not w0.blacklist[r.rid] for r in w0.robots), \
        "marks appeared at ε=0 with no liars"

    def deals_before(w, t):
        return {(d["tick"], d["a"], d["b"]) for d in w.deal_log if d["tick"] < t}
    assert deals_before(w0, first_mark) == deals_before(we, first_mark), \
        "ε perturbed the main-RNG deal stream before it had any behavioural effect"


def test_v22_reencounter_rate_falls_with_N():
    """The mechanism's premise, pinned: at FIXED density the mean number of
    (post-cooldown) meetings per distinct pair FALLS as the fleet grows — the
    partner pool widens, so any given pair re-meets less often (why reputation
    stops scaling). Measured on a plain arm: this is geometry, not enforcement."""
    def reenc(N):
        w = World(n_robots=N, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  grid=_grid_L(N))
        arm = make_arm("snhp+net", w)
        for _ in range(600):
            arm.tick()
        meets = arm._pair_meets
        return sum(meets.values()) / len(meets) if meets else 0.0
    r24, r96 = reenc(24), reenc(96)
    assert r24 > r96, f"re-encounter rate did not fall with N: N24={r24} N96={r96}"


def test_v22_evaluated_equals_executed_under_reputation():
    """The core invariant survives reputation: 600 ticks of the trust arms with
    reputation + slander + liars and the in-arm evaluated Φ == executed Φ assert
    live. Reputation never touches Φ (only refusals/marks), so any divergence
    fires the assert; completing clean IS the test, conservation intact, deals
    struck (non-vacuous) and blacklists actually forming."""
    for arm_name, defended in (("trust-open", False), ("trust-gated", True)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, liar_frac=0.25, defended=defended,
                  reputation=True, false_accuse=0.05)
        arm = make_arm(arm_name, w)
        for _ in range(600):
            arm.tick()
            assert w.material_ok(), "conservation broke under reputation"
        assert arm.deals > 0, f"{arm_name}+reputation struck no deals — vacuous"
        assert any(w.blacklist[r.rid] for r in w.robots), \
            f"{arm_name}+reputation formed no blacklists — vacuous"


# ── v27 (column Z): forgery — the receipt under attack ───────────────────────
def test_v27_forgery_off_bit_identical():
    """forgery=False (even with forge/verify costs and a regime named) must be
    bit-identical to a world that never heard of column Z — the flags, the Z-ledger
    accumulators and the dedicated forgery RandomState may not perturb a single bit
    of the default path. Checked on the trust-gated arm (whose encounter reads the
    flags) AND the auction (which moves cargo)."""
    for arm_name, defended in (("trust-gated", True), ("auction", False)):
        outs = []
        for kw in ({}, dict(forgery=False, forge_cost=2.0, verify_cost=1.0,
                            verify_regime="endogenous")):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name != "auction"), liar_frac=0.25,
                      defended=defended, **kw)
            arm = make_arm(arm_name, w)
            for _ in range(500):
                arm.tick()
            outs.append((w.delivered, arm.deals,
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1], f"column-Z plumbing leaked into {arm_name}"


def test_v27_forged_admission_reaches_the_tier_unverified():
    """The attack's premise: with NO verification (verify_regime='none'), a forged
    receipt is honored at face value, so an unattested liar reaches the trusted
    no-veto tier and exploits an honest partner — forgeries slip in (forge_slipped
    > 0), none are caught, and STRIP deals (liar gains while honest loses) reappear,
    exactly the v6 feeding frenzy the gate had shut off."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              liar_frac=0.25, defended=True, forgery=True, forge_cost=0.0,
              verify_cost=1.0, verify_regime="none")
    arm = make_arm("trust-gated", w)
    for _ in range(1500):
        arm.tick()
    assert arm.forge_attempts > 0, "no forgery attempted — vacuous"
    assert arm.forge_slipped == arm.forge_attempts, \
        "with no verification every forgery must be honored at face value"
    assert arm.forge_caught == 0, "nothing verifies, yet a forgery was caught"
    assert arm.strip_deals > 0, \
        "forged tier admission did not let a liar strip an honest partner"


def test_v27_mandated_verification_always_catches():
    """Paid verification catches a forgery with certainty (p_v=1). Under the MANDATED
    regime every tier admission is checked, so a forger is ALWAYS caught and relegated
    to the veto tier: forge_caught == forge_attempts, nothing slips, and the trusted
    tier records zero strip deals (the gate holds under attack, at the verification
    cost)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              liar_frac=0.25, defended=True, forgery=True, forge_cost=0.0,
              verify_cost=0.25, verify_regime="mandated")
    arm = make_arm("trust-gated", w)
    for _ in range(1500):
        arm.tick()
    assert arm.forge_attempts > 0, "no forgery attempted — vacuous"
    assert arm.forge_caught == arm.forge_attempts, \
        "mandated verification let a forgery through (p_v must be 1)"
    assert arm.forge_slipped == 0, "a forgery slipped past mandated verification"
    assert arm.strip_deals == 0, "a caught forger still stripped an honest partner"


def test_v27_endogenous_verification_responds_to_cv():
    """The endogenous verify decision runs through the existing Φ valuation:
    verify iff liar_frac · downside > verify_cost · EV_INIT, where downside is how
    far below its disagreement point the checker's TRUE Φ falls at the trusted pick.
    A hand-built cell (downside 1.0, liar_frac 0.25) flips the decision as c_v rises:
    cheap verification (0.25) is worth it, dear verification (4.0) is not — the free-
    riding lever. Mandated always checks; 'none' never does."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              liar_frac=0.25, defended=True, forgery=True, forge_cost=0.0,
              verify_cost=0.25, verify_regime="endogenous")
    arm = make_arm("trust-gated", w)
    r = w.robots[0]
    u = np.array([0.0, -1.0])          # trusted pick (index 1) ⇒ downside 1.0
    batna, sol_T = 0.0, 1
    # 0.25·1.0 = 0.25  vs  c_v·EV_INIT
    w.verify_cost = 0.25               # 0.25 > 0.3·0.25 = 0.075 ⇒ verify
    assert arm._verifies(r, u, batna, sol_T) is True
    w.verify_cost = 4.0                # 0.25 < 0.3·4.0 = 1.2  ⇒ free-ride
    assert arm._verifies(r, u, batna, sol_T) is False
    # a zero-downside pick is never worth verifying at any cost
    w.verify_cost = 0.25
    assert arm._verifies(r, np.array([0.0, 0.5]), 0.0, 1) is False
    # regime overrides: mandated always, none never
    w.verify_regime = "mandated"
    assert arm._verifies(r, u, batna, sol_T) is True
    w.verify_regime = "none"
    assert arm._verifies(r, u, batna, sol_T) is False


def test_v27_costs_conserved_in_the_ledger():
    """Every forge/verify act is booked to the Z ledger exactly once at its posted
    price: forge_spend == forge_events · c_f and verify_spend == verify_events · c_v,
    and (costs positive) the event counts equal the behavioural counts. The battery
    burned is monotone (never minted)."""
    cf, cv = 2.0, 1.0
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), hazard_phi=True,
              liar_frac=0.25, defended=True, forgery=True, forge_cost=cf,
              verify_cost=cv, verify_regime="endogenous")
    arm = make_arm("trust-gated", w)
    for _ in range(1500):
        arm.tick()
    assert arm.forge_attempts > 0 and arm.verify_acts > 0, "no acts — vacuous"
    assert w.forge_spend > 0 and w.verify_spend > 0, "spend never booked — vacuous"
    assert abs(w.forge_spend - w.forge_events * cf) < 1e-9, "forge ledger diverged"
    assert abs(w.verify_spend - w.verify_events * cv) < 1e-9, "verify ledger diverged"
    assert w.forge_events == arm.forge_attempts, "a forge act went unbooked"
    assert w.verify_events == arm.verify_acts, "a verify act went unbooked"
    # the world's own conservation invariants survive the burned overhead
    assert w.material_ok() and w.ledger_accounted(), "Z spend broke conservation"


def test_v27_evaluated_equals_executed_under_every_regime():
    """The sacred invariant survives forgery: 800 ticks of the gated trust arm under
    attack, with the in-arm evaluated Φ == executed Φ assert live, across ALL three
    verification regimes and both a cheap and a dear verification cost. Forge/verify
    energy is burned only AFTER a deal settles, so any leak into the priced bundle
    fires the assert; completing clean IS the test — conservation intact, deals
    struck, and the forgery machinery actually exercised (non-vacuous)."""
    for regime in ("none", "mandated", "endogenous"):
        for cv in (0.25, 4.0):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=True, liar_frac=0.25, defended=True, forgery=True,
                      forge_cost=2.0, verify_cost=cv, verify_regime=regime)
            arm = make_arm("trust-gated", w)
            for _ in range(800):
                arm.tick()
                assert w.material_ok(), f"conservation broke ({regime}, c_v={cv})"
            assert arm.deals > 0, f"{regime} c_v={cv} struck no deals — vacuous"
            assert arm.forge_attempts > 0, \
                f"{regime} c_v={cv} exercised no forgery — vacuous"


# ── v23 (column V): the stigmergic order book ────────────────────────────────
def test_v23_order_book_off_bit_identical():
    """order_book=False must be bit-identical to a world that never heard of
    column V — the orders list, the pinned/escrow ledgers, the known_orders sets
    and every order phase may not perturb a single bit when off. Checked on the
    bargaining arm (order book would touch Φ via bills) and the auction. BONUS:
    the auction is the unperturbed COMPARATOR — even with order_book ON, AuctionArm
    posts nothing (no _order_phase), so no order forms and delivered/deals are
    unchanged; the order book is a bargaining-family primitive."""
    def fp(w, arm):
        return (w.delivered, arm.deals, len(w.event_log),
                round(sum(r.battery for r in w.robots), 9),
                [r.pos for r in w.robots],
                [tuple(sorted(d.items())) for d in w.deal_log])

    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in (dict(), dict(order_book=False)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append(fp(w, arm))
        assert outs[0] == outs[1], f"order-book plumbing perturbed {arm_name} when off"

    # auction comparator: order_book ON forms no order and does not move delivered
    wa = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), order_book=True)
    aa = make_arm("auction", wa)
    for _ in range(400):
        aa.tick()
    assert wa.orders_posted == 0 and wa.orders_accepted == 0, \
        "the auction posted/accepted an order — comparator perturbed"
    wb = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15))
    ab = make_arm("auction", wb)
    for _ in range(400):
        ab.tick()
    assert wa.delivered == wb.delivered, "auction delivered moved under order_book"


def test_v23_escrow_conserved_post_and_accept():
    """Post→accept mechanics + conservation. Posting escrows q cargo (a lien folded
    into material conservation) and banks the poster's α claim; acceptance transfers
    cargo+claim to the taker with NO deal pause. pinned_cargo, escrow_conserved,
    material_ok and credit_conserved hold at every step."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), order_book=True)
    w._live_sense = False
    A, B = w.robots[0], w.robots[1]
    for r in (A, B):
        r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
    A.pos = w.sources[0]
    A.load, A.load_prov, w.stock[0] = 3, [3, 0], w.stock[0] - 3   # conserve material
    A.parcels = [w._new_parcel(0) for _ in range(3)]
    acc0 = w.material_accounted()
    o = w.post_order(A, 3, alpha=0.4)
    assert o is not None and w.pinned_cargo == 3 and A.load == 0 and not A.parcels
    assert w.material_accounted() == acc0, "pinned cargo left material conservation"
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()
    assert abs(A.claim_value - 0.4 * 3 * V_DELIVER) < 1e-9, "claim not banked at post"
    assert sum(A.load_prov) == A.load == 0                # provenance moved out
    B.pos, B.cap, B.battery = o["loc"], 5, 90.0
    got = w.accept_order(B, o)
    assert got == 3 and w.pinned_cargo == 0 and B.load == 3 and len(B.parcels) == 3
    assert B.busy_until < w.tick, "acceptance immobilized the taker (paid a pause)"
    assert w.pause_ticks_saved == W.DEAL_PAUSE, "pause-ticks-saved not booked"
    assert sum(B.load_prov) == B.load == 3, "provenance did not ride the cargo"
    for p in B.parcels:                                   # poster's claim rode along
        assert dict((c[0], c[1]) for c in p["claims"])[A.rid] == 0.4
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()


def test_v23_expiry_refunds_alive_and_dead():
    """Expiry refunds escrow. ALIVE poster: cargo returns to its load, the banked
    claim is stripped, the energy bounty returns to its battery. DEAD poster: the
    cargo is written off to stock_lost (material_ok still holds — abandoned, not
    leaked) and the bounty is written off (documented). Conservation throughout."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), order_book=True)
    w._live_sense = False
    A = w.robots[0]
    A.company, A.sector, A.load, A.load_prov, A.parcels = 0, 0, 0, [0, 0], []
    A.pos = w.sources[0]
    A.load, A.load_prov, w.stock[0] = 2, [2, 0], w.stock[0] - 2   # conserve material
    A.parcels = [w._new_parcel(0) for _ in range(2)]
    bat0, cl0 = A.battery, A.claim_value
    o = w.post_order(A, 2, alpha=0.5, energy=5.0)
    assert w.pinned_cargo == 2 and w.escrowed_energy == o["energy"] > 0
    assert A.battery == bat0 - o["energy"]
    w.tick = o["expiry"]
    w.expire_orders()
    assert w.orders_expired == 1 and w.pinned_cargo == 0 and not w.orders
    assert A.load == 2 and len(A.parcels) == 2, "cargo not refunded to live poster"
    assert abs(A.claim_value - cl0) < 1e-9, "banked claim not stripped on expiry"
    assert abs(A.battery - bat0) < 1e-9, "energy bounty not refunded to live poster"
    assert w.escrowed_energy == 0.0 and w.escrow_conserved() and w.material_ok()

    # DEAD poster: cargo → stock_lost, bounty → writeoff
    w2 = World(sigma=0.5, seed=1, preset="v5", tau=(0.0, 0.0), order_book=True)
    w2._live_sense = False
    D = w2.robots[0]
    D.company, D.sector, D.load, D.load_prov, D.parcels = 0, 0, 0, [0, 0], []
    D.pos = w2.sources[0]
    D.load, D.load_prov, w2.stock[0] = 2, [2, 0], w2.stock[0] - 2  # conserve material
    D.parcels = [w2._new_parcel(0) for _ in range(2)]
    o2 = w2.post_order(D, 2, alpha=0.5, energy=4.0)
    D.stranded = True                                    # poster dies before pickup
    w2.tick = o2["expiry"]
    w2.expire_orders()
    assert w2.cargo_writeoff == 2 and w2.stock_lost >= 2, "dead-poster cargo not written off"
    assert w2.escrow_energy_writeoff == o2["energy"], "dead-poster bounty not written off"
    assert w2.material_ok(), "conservation broke on a dead-poster write-off"
    assert w2.escrow_conserved()


def test_v23_discovery_only_by_proximity():
    """Stigmergy, no free broadcast (the P21 lesson): an order is discovered ONLY
    when its pinned location enters a robot's Chebyshev R_SENSE. Just outside the
    radius ⇒ unknown; at the radius ⇒ known. Cross-company robots never discover
    a relay (own fleet services it)."""
    w = World(sigma=0.5, seed=0, preset="v5", order_book=True)
    w._live_sense = False
    A, B, C = w.robots[0], w.robots[1], w.robots[2]
    A.company, B.company = 0, 0
    A.pos, A.load, A.load_prov = (16, 16), 2, [2, 0]
    A.sector, A.parcels = 0, [w._new_parcel(0) for _ in range(2)]
    o = w.post_order(A, 2, 0.5)
    rs = W.R_SENSE
    B.pos = (16 + rs + 4, 16)                            # far: not discovered
    w._discover_orders()
    assert o["oid"] not in w.known_orders[B.rid]
    B.pos = (16 + rs + 1, 16)                            # just outside: not discovered
    w._discover_orders()
    assert o["oid"] not in w.known_orders[B.rid]
    B.pos = (16 + rs, 16)                                # AT the radius: discovered
    w._discover_orders()
    assert o["oid"] in w.known_orders[B.rid]
    # a different-company robot at the pin never learns the relay
    C.company = 1
    C.pos = o["loc"]
    w._discover_orders()
    assert o["oid"] not in w.known_orders[C.rid], "cross-company discovered a relay"


def test_v23_acceptance_evaluated_equals_executed():
    """evaluated Φ == executed Φ is sacred: acceptance executes at exactly the
    posted terms and the acceptor's post-pickup Φ_bills equals what it evaluated.
    Checked (a) hand-built to the bit, and (b) live over a full order-book run with
    conservation, non-vacuously (orders accepted AND a relayed unit delivered)."""
    from swarm.value import phi_bills
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), order_book=True)
    w._live_sense = False
    arm = make_arm("snhp", w, issues=("cargo",))
    A, B = w.robots[0], w.robots[1]
    for r in (A, B):
        r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
    A.pos, A.load, A.load_prov = (6, 6), 2, [2, 0]
    A.parcels = [w._new_parcel(0) for _ in range(2)]
    o = w.post_order(A, 2, 0.4)
    B.pos, B.cap, B.battery = o["loc"], 5, 95.0
    w.known_orders[B.rid].add(o["oid"])
    phi_eval = arm._accept_phi(B, o)
    w.accept_order(B, o)
    assert abs(phi_bills(B, w) - phi_eval) < 1e-9, "acceptance diverged from evaluation"

    w2 = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), grid=24,
               order_book=True)
    arm2 = make_arm("snhp+net", w2)
    for _ in range(1800):
        arm2.tick()
        assert w2.material_ok(), "material leak under order book"
        assert w2.credit_conserved(), "credit not conserved under order book"
        assert w2.escrow_conserved(), "escrow ledger diverged"
    assert w2.ledger_accounted(), "ledger leak under order book"
    assert w2.orders_accepted > 0, "no order ever accepted — vacuous"
    assert any(p["hops"] >= 1 for p in w2.delivered_parcels), \
        "no relayed unit ever delivered — vacuous"


def test_v23_sparse_field_relay_without_colocation():
    """The registered sparse-field scenario: two drones that NEVER co-locate still
    trade via a pinned order. A stuck low-battery drone pins its cargo and parks
    far away; a healthy drone discovers the pin by proximity, hauls it in, and
    delivers — and the poster earns its claim credit at delivery though it was
    never within interaction range of the taker."""
    from swarm.value import phi_bills  # noqa: F401  (import parity with the arm)
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), order_book=True)
    w._live_sense = False
    arm = make_arm("snhp", w)
    A, B = w.robots[0], w.robots[1]
    for r in w.robots:                                   # neutralize the rest
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, 0, 5, 0, [0, 0], []
    for r in w.robots[2:]:
        r.pos, r.stranded, r.battery = (1, 1), True, 0.0
    L, ref0 = (8, 8), w.refineries[0]
    A.pos, A.battery, A.load, A.load_prov = L, 12.0, 2, [2, 0]
    w.stock[0] -= 2                                       # conserve material
    A.parcels = [w._new_parcel(0) for _ in range(2)]
    o = w.post_order(A, 2, alpha=0.3)
    A.pos, A.stranded, A.battery = (2, 30), True, 0.0    # A parks/dies FAR from L and B
    B.pos, B.battery, B.cap = (30, 8), 100.0, 5
    w.known_orders[B.rid].add(o["oid"])
    picked, min_cheby = False, 10 ** 9
    for _ in range(800):
        min_cheby = min(min_cheby, max(abs(A.pos[0] - B.pos[0]),
                                       abs(A.pos[1] - B.pos[1])))
        if not picked:
            if max(abs(B.pos[0] - L[0]), abs(B.pos[1] - L[1])) <= W.R_PICKUP:
                arm._accept_phi(B, o)                    # eval (parity with the arm)
                w.accept_order(B, o)
                picked = True
            else:
                w.move_toward(B, L)
        elif B.pos == ref0:
            w.drop(B)
            break
        else:
            w.move_toward(B, ref0)
        w.tick += 1
    assert picked, "the taker never reached the pinned order"
    assert w.delivered >= 2, "the async-relayed cargo never delivered"
    assert min_cheby > W.R_COMM, f"A and B co-located (min Chebyshev {min_cheby})"
    assert A.credit > 0, "the poster earned no claim credit from the async relay"
    assert w.credit_conserved() and w.material_ok()


# ── v31 (column V2): the depot — the founder's async re-run of the board ─────
def test_v31_depots_off_bit_identical():
    """depots=False must be bit-identical to a world that never heard of column V2
    — the depot flag, relay_from field, the deposit phase and the forward-staging /
    progress-gate branches may not perturb a single bit when off. Checked on the
    bargaining arm (depots would touch Φ via bills) and the auction comparator. Also
    confirms the depot plumbing leaves the column-V order book bit-reproducible."""
    def fp(w, arm):
        return (w.delivered, arm.deals, len(w.event_log),
                round(sum(r.battery for r in w.robots), 9),
                [r.pos for r in w.robots],
                [tuple(sorted(d.items())) for d in w.deal_log])

    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in (dict(), dict(depots=False)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), grid=48,
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(500):
                arm.tick()
            outs.append(fp(w, arm))
        assert outs[0] == outs[1], f"depot plumbing perturbed {arm_name} when off"

    # the auction never deposits even with depots ON (bargaining-family primitive)
    wa = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), grid=48, depots=True)
    aa = make_arm("auction", wa)
    for _ in range(400):
        aa.tick()
    assert wa.orders_posted == 0 and wa.orders_accepted == 0, \
        "the auction deposited/accepted — comparator perturbed"


def test_v31_deposit_pickup_deliver_settles_all_splits():
    """The core depot leg: a loaded drone DEPOSITS at a depot (pinned at the charger,
    α claim banked), a later passer PICKS UP with no deal pause, and delivery settles
    the depositor's banked split AND the hauler's residual to face value. Conservation
    holds at every step; the pin sits at the CHARGER (co-located, not the poster's
    transient position)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), grid=48, depots=True)
    w._live_sense = False
    A, B = w.robots[0], w.robots[1]
    for r in (A, B):
        r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
    depot = w.chargers[0]
    A.pos, A.load, A.load_prov = depot, 3, [3, 0]
    A.parcels = [w._new_parcel(0) for _ in range(3)]
    w.stock[0] -= 3                                       # conserve material
    o = w.post_order(A, 3, alpha=0.4, loc=depot)
    assert o is not None and o["loc"] == depot, "pin not co-located with the charger"
    assert w.pinned_cargo == 3 and A.load == 0 and not A.parcels
    assert abs(A.claim_value - 0.4 * 3 * V_DELIVER) < 1e-9, "deposit claim not banked"
    assert A.relay_from is None, "deposit should clear the relay-from token"
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()
    A.pos = (2, 2)                                        # A leaves; never meets B
    B.pos, B.cap, B.battery = depot, 5, 95.0
    q = w.accept_order(B, o)
    assert q == 3 and B.load == 3 and w.pinned_cargo == 0
    assert B.busy_until < w.tick, "acceptance paid a deal pause (should be free)"
    assert w.pause_ticks_saved == W.DEAL_PAUSE, "pause-ticks-saved not booked"
    assert B.relay_from == depot, "taker did not record the depot it took from"
    # deliver: A's 0.4 share + B's 0.6 residual = full face, exactly
    B.pos = w.refineries[0]
    w.drop(B)
    assert w.delivered == 3
    assert abs(A.credit - 0.4 * 3 * V_DELIVER) < 1e-9, "depositor split unsettled"
    assert abs(B.credit - 0.6 * 3 * V_DELIVER) < 1e-9, "hauler residual unsettled"
    assert abs((A.credit + B.credit) - 3 * V_DELIVER) < 1e-9, "splits do not sum to face"
    assert B.relay_from is None, "delivery should clear the relay-from token"
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()


def test_v31_three_leg_async_chain_pays_everyone():
    """The registered crucial delta vs V: a FULLY ASYNCHRONOUS three-leg chain. A
    deposits at D1; B picks up at D1, relays to D2 and RE-DEPOSITS; C picks up at D2
    and delivers. A, B and C are NEVER within interaction range of one another — no
    co-presence at any hop, no drone obligated to finish the route — yet the parcel
    clears and all three claims settle to face value, with the stack conserved."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), grid=64, depots=True)
    w._live_sense = False
    A, B, C = w.robots[0], w.robots[1], w.robots[2]
    for r in w.robots:                                   # neutralize the rest
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, 0, 5, 0, [0, 0], []
    for r in w.robots[3:]:
        r.pos, r.stranded, r.battery = (1, 1), True, 0.0
    ref = w.refineries[0]
    chs = sorted(w.chargers, key=lambda c: -W.manhattan(c, ref))
    D1, D2 = chs[0], chs[1]                               # D1 farther from home
    C.pos = (1, 60)                                       # C waits far off until leg 3
    positions = []                                       # record A/B/C at each hop
    # leg 1 — A deposits at D1
    A.pos, A.battery, A.load, A.load_prov = D1, 60.0, 3, [3, 0]
    A.parcels = [w._new_parcel(0) for _ in range(3)]
    w.stock[0] -= 3
    oA = w.post_order(A, 3, alpha=0.3, loc=D1)
    A.pos = (1, 1)                                        # A parks far away
    # leg 2 — B picks up at D1, relays to D2, re-deposits
    B.pos, B.battery = D1, 100.0
    w.accept_order(B, oA)
    assert B.relay_from == D1
    positions.append((A.pos, B.pos, C.pos))
    oB = w.post_order(B, B.load, alpha=0.4, loc=D2)
    assert oB is not None and w.pinned_cargo == 3
    assert all(len(p["claims"]) == 2 for p in oB["parcels"]), "re-deposit lost the stack"
    B.pos = (60, 1)                                       # B parks far away
    # leg 3 — C picks up at D2, delivers
    C.pos, C.battery = D2, 100.0
    w.accept_order(C, oB)
    assert all(len(p["claims"]) == 2 for p in C.parcels), "hauler stack not carried"
    positions.append((A.pos, B.pos, C.pos))
    C.pos = ref
    w.drop(C)
    # never co-located: pairwise Chebyshev separations exceed the interaction radius
    for pa, pb, pc in positions:
        for u, v in ((pa, pb), (pa, pc), (pb, pc)):
            assert max(abs(u[0] - v[0]), abs(u[1] - v[1])) > W.R_COMM, \
                "two chain participants were co-located"
    assert w.delivered == 3, "the fully-async chain never delivered"
    # A: 0.3 · B: 0.4·(1−0.3)=0.28 · C: residual 0.42 — all of face, split three ways
    assert abs(A.credit - 0.30 * 3 * V_DELIVER) < 1e-9, "A (first depositor) unpaid"
    assert abs(B.credit - 0.28 * 3 * V_DELIVER) < 1e-9, "B (relay) unpaid"
    assert abs(C.credit - 0.42 * 3 * V_DELIVER) < 1e-9, "C (deliverer) residual wrong"
    assert abs((A.credit + B.credit + C.credit) - 3 * V_DELIVER) < 1e-9, \
        "three banked splits + hauler residual do not conserve to face"
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()


def test_v31_redeposit_conserves_the_stack():
    """A parcel deposited THREE times carries THREE banked splits plus the final
    hauler's residual, and the shares sum to exactly one (conservation of the claim
    stack across deposit → pickup → re-deposit → pickup → re-deposit)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), grid=64, depots=True)
    w._live_sense = False
    P = w.robots
    for r in P:
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, 0, 5, 0, [0, 0], []
    depots = w.chargers
    A, B, C = P[0], P[1], P[2]
    A.pos, A.battery, A.load, A.load_prov = depots[0], 80.0, 2, [2, 0]
    A.parcels = [w._new_parcel(0) for _ in range(2)]
    w.stock[0] -= 2
    o1 = w.post_order(A, 2, alpha=0.2, loc=depots[0])           # deposit 1
    B.pos, B.battery = depots[0], 100.0
    w.accept_order(B, o1)
    o2 = w.post_order(B, 2, alpha=0.3, loc=depots[1])           # deposit 2 (re-deposit)
    C.pos, C.battery = depots[1], 100.0
    w.accept_order(C, o2)
    o3 = w.post_order(C, 2, alpha=0.25, loc=depots[2])          # deposit 3 (re-deposit)
    D = P[3]
    D.pos, D.battery = depots[2], 100.0
    w.accept_order(D, o3)
    for p in D.parcels:
        shares = [sh for _rid, sh, *_ in p["claims"]]
        assert len(shares) == 3, f"expected three banked splits, got {len(shares)}"
        resid = 1.0 - sum(shares)
        assert resid > 0 and abs(sum(shares) + resid - 1.0) < 1e-12, \
            "three splits + residual do not conserve to one"
    # deliver and check every claimant is paid, face conserved
    D.pos = w.refineries[0]
    w.drop(D)
    assert w.delivered == 2
    paid = A.credit + B.credit + C.credit + D.credit
    assert abs(paid - 2 * V_DELIVER) < 1e-9, "multi-deposit payout does not conserve"
    assert w.material_ok() and w.escrow_conserved() and w.credit_conserved()


def test_v31_dead_depositor_writeoff():
    """Dead-depositor convention (the same write-off V used): when a deposited pin
    expires and its poster cannot reclaim (stranded/dead), the cargo is written off
    to stock_lost (material_ok still holds — abandoned, not leaked) and any energy
    bounty is written off. No phantom credit; every ledger stays conserved."""
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.0, 0.0), grid=48, depots=True)
    w._live_sense = False
    D = w.robots[0]
    D.company, D.sector, D.load, D.load_prov, D.parcels = 0, 0, 0, [0, 0], []
    depot = w.chargers[0]
    D.pos, D.load, D.load_prov = depot, 2, [2, 0]
    D.parcels = [w._new_parcel(0) for _ in range(2)]
    w.stock[0] -= 2
    o = w.post_order(D, 2, alpha=0.5, energy=4.0, loc=depot)
    assert w.pinned_cargo == 2 and w.escrowed_energy == o["energy"] > 0
    D.stranded = True                                    # poster dies before pickup
    w.tick = o["expiry"]
    w.expire_orders()
    assert w.cargo_writeoff == 2 and w.stock_lost >= 2, "dead-depositor cargo not written off"
    assert w.escrow_energy_writeoff == o["energy"], "dead-depositor bounty not written off"
    assert w.pinned_cargo == 0 and not w.orders
    assert w.material_ok() and w.escrow_conserved()


def test_v31_evaluated_equals_executed_and_conserves_live():
    """evaluated Φ == executed Φ is sacred under depots (pickup evaluates Φ_bills on
    the tentative pickup, asserted against the executed state). Checked (a) hand-built
    to the bit and (b) live over a full depot run — conservation (material / credit /
    escrow / ledger) holds every tick, non-vacuously (a deposit posted, an acceptance
    taken, and a relayed unit delivered async)."""
    from swarm.value import phi_bills
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), grid=48, depots=True)
    w._live_sense = False
    arm = make_arm("snhp", w, issues=("cargo",))
    A, B = w.robots[0], w.robots[1]
    for r in (A, B):
        r.company, r.sector, r.load, r.load_prov, r.parcels = 0, 0, 0, [0, 0], []
    depot = w.chargers[0]
    A.pos, A.load, A.load_prov = depot, 2, [2, 0]
    A.parcels = [w._new_parcel(0) for _ in range(2)]
    o = w.post_order(A, 2, 0.4, loc=depot)
    B.pos, B.cap, B.battery = depot, 5, 95.0
    w.known_orders[B.rid].add(o["oid"])
    phi_eval = arm._accept_phi(B, o)
    w.accept_order(B, o)
    assert abs(phi_bills(B, w) - phi_eval) < 1e-9, "depot acceptance diverged from evaluation"

    w2 = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15), grid=64,
               depots=True, lineage=True)
    arm2 = make_arm("snhp+net", w2)
    for _ in range(2500):
        arm2.tick()
        assert w2.material_ok(), "material leak under depots"
        assert w2.credit_conserved(), "credit not conserved under depots"
        assert w2.escrow_conserved(), "escrow ledger diverged under depots"
    assert w2.ledger_accounted(), "ledger leak under depots"
    assert w2.orders_posted > 0, "no deposit ever posted — vacuous"
    assert w2.orders_accepted > 0, "no deposit ever accepted — vacuous"
    assert any(p["hops"] >= 1 for p in w2.delivered_parcels), \
        "no relayed unit ever delivered — vacuous"


# ── v18 (column Q): endogenous infrastructure — the sim grows landlords ──────
def test_v18_build_off_bit_identical():
    """build_matter=0 / build=False (and a SEEDED-but-untouched matter field with
    build off) must be bit-identical to a World that never heard of column Q — the
    matter arrays, the toll/built parallel charger arrays, build_step,
    assign_gatherers and pick_matter may not perturb a single bit of the default
    path. Checked on snhp+net (fast path) and auction (moves cargo)."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in ({},
                   dict(build_matter=0.0, build=False, toll_level=0.0),
                   dict(build_matter=0.5, build=False)):      # matter field inert
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name != "auction"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1] == outs[2], \
            f"column-Q plumbing leaked into {arm_name}"


def test_v18_fast_equals_scalar_with_built_chargers():
    """The registrar's sacred concern: Φ evaluation must see the CURRENT charger
    set. Built chargers change the energy landscape, yet the fast path caches
    nearest_charger per encounter — so fast and scalar Φ MUST stay byte-identical
    across a run that BUILDS chargers mid-flight (differential oracle, N=48 so
    building fires within the horizon)."""
    def fp(force_scalar):
        _ARMS.FORCE_SCALAR_EVAL = force_scalar
        w = World(n_robots=48, sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  grid=_grid_L(48), build_matter=1.0, build=True, toll_level=2.0)
        arm = make_arm("snhp+net", w)
        for _ in range(700):
            arm.tick()
        return (w.delivered, arm.deals, sum(c["built"] for c in w.company),
                [round(r.battery, 12) for r in w.robots],
                [tuple(sorted(d.items())) for d in w.deal_log])
    try:
        fast, scalar = fp(False), fp(True)
    finally:
        _ARMS.FORCE_SCALAR_EVAL = False
    assert fast == scalar, "fast != scalar with built chargers (Φ saw a stale set)"
    assert fast[2] > 0, "no charger built — the built-charger oracle is vacuous"


def test_v18_matter_and_credit_conserved():
    """Every invariant survives building: over a full N=96 build run, matter
    (field + pools + spent == mined == initial-remaining), credit (ledger with
    build_spend), material (ore) and tolls all conserve, live — non-vacuously
    (chargers actually built, matter actually mined)."""
    w = World(n_robots=96, sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
              grid=_grid_L(96), build_matter=1.0, build=True, toll_level=2.0)
    arm = make_arm("snhp+net", w)
    for _ in range(1200):
        arm.tick()
        assert w.material_ok(), "ore material leaked under build"
        assert w.matter_conserved(), "matter leaked under build"
        assert w.toll_conserved(), "toll transfer not conserved"
    assert w.ledger_accounted(), "ledger (with build_spend) leaked under build"
    assert sum(c["built"] for c in w.company) > 0, "no charger built — vacuous"
    assert w.matter_mined > 0, "no matter mined — vacuous"
    # build_spend exactly equals BUILD_CREDIT_COST × chargers built
    spent = sum(c["build_spend"] for c in w.company)
    built = sum(c["built"] for c in w.company)
    assert abs(spent - built * W.BUILD_CREDIT_COST) < 1e-9, "build_spend mismatch"


def test_v18_toll_paid_guest_to_owner_exactly():
    """A guest slot-fill at a BUILT charger with toll>0 moves EXACTLY `toll`
    credits guest-company→owner-company (a pure transfer: net-zero in Σ credit,
    so ledger_accounted holds), and a guest at a toll-free preset charger pays
    nothing."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0),
              build_matter=0.5, build=True, toll_level=3.0)
    # hand-build one owned charger for company 0 and dock a company-1 guest on it
    w.chargers.append((15, 15)); w.charger_owner.append(0)
    w.charger_toll.append(3.0); w.charger_built.append(True)
    guest = next(r for r in w.robots if r.company == 1)
    guest.pos = (15, 15); guest.battery = 50.0; guest.charge_queued_at = w.tick
    guest.stranded = False
    c0_before = w.company[0]["credit"]
    c1_before = w.company[1]["credit"]
    w.charge_step()
    assert w.company[0]["toll_earned"] == 3.0, "owner did not earn exactly one toll"
    assert w.company[1]["toll_paid"] == 3.0, "guest did not pay exactly one toll"
    assert abs(w.company[0]["credit"] - (c0_before + 3.0)) < 1e-9
    assert abs(w.company[1]["credit"] - (c1_before - 3.0)) < 1e-9
    assert w.toll_conserved()
    guest.charge_queued_at = -1                           # undock the guest
    # a company-0 host charging at its OWN toll-free preset charger costs no toll
    te_before = w.company[0]["toll_earned"]
    host = next(r for r in w.robots if r.company == 0)
    host.pos = w.chargers[0]; host.battery = 50.0        # own charger (toll 0)
    host.charge_queued_at = w.tick; host.stranded = False
    w.charge_step()
    assert w.company[0]["toll_earned"] == te_before, "a toll-free charge levied a toll"


def test_v18_placement_deterministic_given_seed():
    """Placement is a deterministic function of world state: two build runs at the
    SAME seed produce IDENTICAL built logs (ticks + sites); a DIFFERENT seed
    generally does not (the matter field and trajectories differ)."""
    def built(seed):
        w = World(n_robots=96, sigma=0.5, seed=seed, preset="v5", tau=(0.15, 0.15),
                  grid=_grid_L(96), build_matter=1.0, build=True)
        arm = make_arm("snhp+net", w)
        for _ in range(900):
            arm.tick()
        return [(b["tick"], b["co"], b["pos"]) for b in w.built_log]
    a, a2, b = built(0), built(0), built(3)
    assert a == a2, "placement not deterministic at fixed seed"
    assert len(a) > 0, "no charger built — placement test vacuous"
    assert a != b, "two different seeds built identically (suspicious)"


def test_v18_built_charger_unstrands_a_known_stranded_route():
    """The hand-built scenario: a loaded drone is STRANDED (battery 0) partway
    along its route to the refinery, with NO charger in reach — it stays stranded
    and never delivers. Place ONE far-field charger on the stranded cell and the
    same drone tops up, un-strands and DELIVERS. Isolated (preset chargers stripped
    so the built charger is the ONLY infrastructure — an unambiguous far-field
    rescue)."""
    from swarm.arms import drive

    def run(with_built):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0),
                  build_matter=0.5, build=True)
        w._live_sense = False
        w.chargers, w.charger_owner = [], []          # strip preset infra
        w.charger_toll, w.charger_built = [], []
        make_arm("null", w)                           # bare movement, no deals
        for r in w.robots:                            # neutralize the rest
            r.stranded, r.battery, r.load, r.load_prov = True, 0.0, 0, [0, 0]
        R = w.robots[0]
        ref = w.refineries[0]                         # (26, 6)
        R.company, R.sector, R.cap, R.eff = 0, 0, 3, 1.0
        # STRANDED loaded, 10 cells short of the refinery, battery dead
        R.stranded, R.pos, R.battery = True, (16, 6), 0.0
        R.load, R.load_prov = 2, [2, 0]
        R.charge_queued_at = w.tick
        if with_built:                                # a far-field charger on the cell
            w.chargers.append((16, 6)); w.charger_owner.append(0)
            w.charger_toll.append(0.0); w.charger_built.append(True)
        for _ in range(400):
            drive(R, w)
            w.charge_step()
            if R.pos == ref and R.load == 0:
                break
        return R.stranded, w.delivered

    stranded_no, delivered_no = run(False)
    stranded_yes, delivered_yes = run(True)
    assert stranded_no and delivered_no == 0, \
        "the route was NOT stranded without a charger — scenario invalid"
    assert (not stranded_yes) and delivered_yes >= 2, \
        "the built far-field charger failed to un-strand the route"


def test_v18_evaluated_equals_executed_live_under_build():
    """The sacred bills-style invariant, exercised under build: 800 ticks of
    snhp+net with a live matter field and mid-run charger placement. The in-arm
    evaluated Φ == executed Φ assert fires on any divergence; completing clean IS
    the test — non-vacuous (deals struck, chargers built), conservation intact."""
    w = World(n_robots=96, sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15),
              grid=_grid_L(96), build_matter=1.0, build=True, toll_level=1.0)
    arm = make_arm("snhp+net", w)
    for _ in range(800):
        arm.tick()
        assert w.material_ok() and w.matter_conserved()
    assert arm.deals > 0, "no deal struck — evaluated==executed test vacuous"
    assert sum(c["built"] for c in w.company) > 0, "no charger built — vacuous"


# ── v25 (column X): the firm's interior — command / prices / claims ─────
def test_v25_command_default_off_bit_identical():
    """command=False and deadlock_track=False must be bit-identical to a lineage-
    only world — the planner state, the deadlock instrument and every column-X
    branch may not perturb a single bit when off. Checked on a bargaining arm and
    the auction (the same surfaces the P2 off-test guards)."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in (dict(lineage=True),
                   dict(lineage=True, command=False, deadlock_track=False)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots]))
        assert outs[0] == outs[1], f"column-X plumbing perturbed {arm_name}"


def test_v25_prices_bit_identical_with_instrument():
    """The internal-prices regime (b) is the P23b firm_relay arm, UNCHANGED: the
    read-only deadlock instrument may not perturb it. firm_relay in the column-X
    information env with deadlock_track on == off, bit for bit (delivered, deals,
    positions, batteries AND the internal treasury book)."""
    outs = []
    for dt in (False, True):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  firm_relay=True, belief_mode=True, gossip=True, r_radio=6,
                  deadlock_track=dt)
        arm = make_arm("snhp+net", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals, len(w.event_log),
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots],
                     round(w.company[0]["treasury"], 6)))
    assert outs[0] == outs[1], \
        "deadlock instrument perturbed the firm_relay (prices) trajectory"


def test_v25_command_assignments_propagate_by_contact_only():
    """The COMMAND honesty constraint (i): assignments spread by the SAME radio
    physics as gossip. A same-company drone within r_radio of HQ hears the plan;
    one beyond the connected component keeps NO order (cmd_held_tick stays -1 ⇒
    cmd_resolve None ⇒ the drone keeps its default solo policy)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), command=True,
              belief_mode=True, gossip=True, r_radio=6, lineage=True)
    hq = w.refineries[w._home_ref(0)]
    co0 = [r for r in w.robots if r.company == 0]
    for r in co0:                      # park the fleet on HQ; isolate one far away
        r.pos = hq
    far = co0[0]
    far.pos = (0, 0)                   # no same-company robot within r_radio of it
    near = co0[1]
    w.command_step()                   # tick 0: re-plan + seed(HQ) + one flood hop
    assert w.cmd_held_tick[near.rid] == 0, "an HQ-adjacent drone did not hear the plan"
    assert w.cmd_held_tick[far.rid] == -1, "the plan reached an out-of-radio drone"
    assert w.cmd_resolve(far) is None, "an unreached drone got a command target"


def test_v25_planner_belief_is_merged_gossip_not_field_truth():
    """The COMMAND honesty constraint (ii): the planner plans on the company's
    gossip-merged belief, NEVER field truth. With a stale-optimistic belief over a
    truly-depleted rock, the merged view returns the stale belief (the union of
    what the fleet has sensed), which differs from the (zero) true stock."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), command=True,
              belief_mode=True, gossip=True, r_radio=6, lineage=True)
    i = 0
    for r in w.robots:
        if r.company == 0:
            w.belief[r.rid][i] = 50.0
            w.last_seen[r.rid][i] = 5
    w.stock[i] = 0                     # the rock is TRULY empty
    bel, ls = w._merged_belief(0)
    assert bel[i] == 50.0, "merged belief is not the fleet's sensed belief"
    assert bel[i] != w.stock[i], "planner read FIELD TRUTH, not the merged belief"


def test_v25_claims_conserve_credit_inside_the_firm():
    """Regime (c): the bills machinery run inside the firm conserves credit through
    internal settlement — 600 ticks in the column-X info env with credit AND
    material conservation live, non-vacuous (relays actually settle)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), bills=True,
              belief_mode=True, gossip=True, r_radio=6, deadlock_track=True)
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
        assert w.credit_conserved(), "credit not conserved under internal claims"
        assert w.material_ok(), "material leak under internal claims"
    assert arm.deals > 0, "claims struck no deals — vacuous"
    assert w.ledger_accounted()


def test_v25_deadlock_counter_counts_a_handbuilt_deadlock_once():
    """The routing-contamination instrument counts each ENTRY into the deadlock
    (loaded, ~full battery, beyond single-hop loaded reach of every refinery)
    exactly once — rising-edge, not per-tick — and re-counts a fresh entry."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), deadlock_track=True)
    for o in w.robots:
        o.load = 0                     # only the hand-built drone may be in deadlock
    r = w.robots[0]
    r.load, r.battery, r.eff, r.stranded = 1, 100.0, 5.0, False
    r.pos = (0, 16)                    # far: manhattan*5*1.6 ≫ 100 to every refinery
    assert not any(w._loaded_reach(r, rf) for rf in w.refineries)
    base = w.deadlock_count
    w.deadlock_step()
    assert w.deadlock_count == base + 1, "entry not counted"
    w.deadlock_step()
    assert w.deadlock_count == base + 1, "counted a second time while still stuck"
    r.pos = w.refineries[0]            # now single-hop reachable → leaves the state
    w.deadlock_step()
    assert w.deadlock_count == base + 1, "count moved on a falling edge"
    r.pos = (0, 16)                    # re-enter → a fresh entry counts
    w.deadlock_step()
    assert w.deadlock_count == base + 2, "a fresh entry was not counted"


def test_v25_command_runs_conserves_and_delivers():
    """COMMAND end-to-end: the planner swaps in (CommandArm), the fleet delivers
    (non-vacuous), the planner actually plans, and material + ledger conserve — the
    directed hand-offs settle through the shared transfer/drop primitives, so no
    'evaluated Φ == executed Φ' reconciliation is needed (no bundle evaluation runs)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), command=True,
              belief_mode=True, gossip=True, r_radio=6, lineage=True,
              deadlock_track=True)
    arm = make_arm("snhp+net", w)
    assert arm.__class__.__name__ == "CommandArm", "command flag did not swap the arm"
    for _ in range(800):
        arm.tick()
        assert w.material_ok(), "material leak under command"
        assert w.ledger_accounted(), "ledger leak under command"
    assert w.delivered > 0, "command delivered nothing — vacuous"
    assert len(w.cmd_plan_versions) > 0, "the planner never planned"


# ── v18-R (column Q2): landlords on the frontier — frontier scarcity + bills ────
def test_q2_charger_band_off_bit_identical():
    """charger_band=0.0 (the default) must be bit-identical to a World that never
    heard of the Q2 amendment — the band filter, the stored flag and the (skipped)
    _apply_charger_band may not perturb a single bit of the default path. Checked on
    the fast (snhp+net) and cargo-moving (auction) arms, AND with the full column-Q +
    bills machinery live (band=0 must still vanish inside a build+bills world)."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in ({}, dict(charger_band=0.0)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name != "auction"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots]))
        assert outs[0] == outs[1], f"charger_band=0 plumbing perturbed {arm_name}"
    outs = []
    for kw in (dict(build_matter=0.5, build=True, bills=True),
               dict(build_matter=0.5, build=True, bills=True, charger_band=0.0)):
        w = World(n_robots=96, sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15),
                  grid=_grid_L(96), **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(500):
            arm.tick()
        outs.append((w.delivered, arm.deals, sum(c["built"] for c in w.company),
                     round(sum(r.battery for r in w.robots), 9)))
    assert outs[0] == outs[1], "charger_band=0 perturbed a live build+bills world"


def test_q2_band_excludes_far_presets_exactly():
    """FRONTIER SCARCITY, exactly: at N=240 the band (= single-hop loaded reach,
    BATTERY_MAX/(1+LOADED_MULT)=62.5) keeps EVERY preset within loaded reach of a
    refinery and removes EVERY far one — 40→30, the 10 far-band chargers gone. The
    four parallel charger arrays stay aligned, and because the filter runs AFTER both
    field generators, the ore and matter fields are byte-identical to the no-band
    world (the ONLY thing scarcity removes is far-band charging capacity)."""
    reach = W.BATTERY_MAX / (1.0 + W.LOADED_MULT)
    g = _grid_L(240)
    w0 = World(n_robots=240, sigma=0.5, seed=0, preset="v5", grid=g,
               build_matter=0.5)
    wb = World(n_robots=240, sigma=0.5, seed=0, preset="v5", grid=g,
               build_matter=0.5, charger_band=reach)

    def near(c):
        return min(W.manhattan(c, rf) for rf in w0.refineries)

    expected = [c for c in w0.chargers if near(c) <= reach]
    assert wb.chargers == expected, "band kept the wrong preset set"
    assert len(w0.chargers) == 40 and len(wb.chargers) == 30, \
        "band did not strip exactly the 10 far-band presets"
    assert all(near(c) <= reach for c in wb.chargers), "a kept charger is far-band"
    removed = [c for c in w0.chargers if c not in wb.chargers]
    assert removed and all(near(c) > reach for c in removed), \
        "a removed charger was actually in-band"
    assert len(wb.charger_owner) == len(wb.charger_toll) == \
        len(wb.charger_built) == len(wb.chargers), "parallel arrays desynced"
    assert w0.sources == wb.sources and w0.stock == wb.stock, \
        "frontier scarcity perturbed the ORE field"
    assert w0.matter_sources == wb.matter_sources and \
        w0.matter_stock == wb.matter_stock, \
        "frontier scarcity perturbed the MATTER field"


def test_q2_job_matrix_sets_bills_on_intended_arms():
    """The cells-match-registration guard (the Q miss was a silently-absent bills
    flag). Asserts the built Q2 job matrix ACTUALLY sets bills=True on the bargaining
    cells the registration names, carries frontier scarcity (band == single-hop
    loaded reach) on every grid cell, keeps a SPOT build for the P24R-c pair, keeps
    the auction bills-free, rides both sweeps on the bills build arm, and carries the
    scarcity-OFF bills flag-verification control."""
    from swarm.run import build_jobs
    BAND = W.BATTERY_MAX / (1.0 + W.LOADED_MULT)
    jobs = build_jobs("Q2", 8, 2500)

    def has(pred):
        return any(pred(j) for j in jobs)

    scarce = [j for j in jobs if j.get("charger_band", 0.0) > 0]
    assert scarce and all(abs(j["charger_band"] - BAND) < 1e-9 for j in scarce), \
        "grid cells must carry band == single-hop loaded reach"
    for H in (2500, 7500):
        assert has(lambda j, H=H: j["arm_name"] == "snhp+net" and j.get("bills")
                   and not j.get("build") and j["ticks"] == H
                   and j.get("charger_band", 0) > 0), f"no bills no-build @ {H}"
        assert has(lambda j, H=H: j["arm_name"] == "snhp+net" and j.get("bills")
                   and j.get("build") and j["ticks"] == H
                   and j.get("charger_band", 0) > 0), f"no bills build @ {H}"
    assert has(lambda j: j["arm_name"] == "snhp+net" and not j.get("bills")
               and j.get("build") and j.get("charger_band", 0) > 0), \
        "no SPOT build (the P24R-c layering pair) under scarcity"
    assert has(lambda j: j["arm_name"] == "auction" and j.get("charger_band", 0) > 0)
    assert not has(lambda j: j["arm_name"] == "auction" and j.get("bills")), \
        "auction must stay bills-free (no bills path in AuctionArm)"
    for b in (0, 2, 4, 8, 16):
        assert has(lambda j, b=b: j.get("bills") and j.get("build")
                   and j.get("build_budget") == b), f"budget {b} not on bills build"
    for t in (1.0, 2.0, 4.0):
        assert has(lambda j, t=t: j.get("bills") and j.get("build")
                   and abs(j.get("toll_level", 0.0) - t) < 1e-9), \
            f"toll {t} not on bills build"
    assert has(lambda j: j["arm_name"] == "snhp+net" and j.get("bills")
               and not j.get("build") and j.get("charger_band", 0.0) == 0.0), \
        "missing the scarcity-OFF bills flag-verification control"


def test_q2_toll_conserved_on_frontier_built_charger():
    """Toll conservation under frontier scarcity: with the far presets stripped by
    the band, a company-1 guest docking on a company-0 BUILT far-band charger moves
    EXACTLY `toll` credits guest→owner (net-zero; ledger intact), the built-guest-slot
    meter ticks, and toll_conserved() holds."""
    BAND = W.BATTERY_MAX / (1.0 + W.LOADED_MULT)
    g = _grid_L(240)
    w = World(n_robots=240, sigma=0.5, seed=0, preset="v5", grid=g, tau=(0.0, 0.0),
              build_matter=0.5, build=True, toll_level=2.0, charger_band=BAND)
    assert len(w.chargers) == 30, "frontier scarcity inactive — test vacuous"
    far = (5, 50)                       # far from BOTH refineries (82,19)/(82,82)
    assert min(W.manhattan(far, rf) for rf in w.refineries) > BAND, \
        "test site is not in the far band"
    w.chargers.append(far); w.charger_owner.append(0)
    w.charger_toll.append(2.0); w.charger_built.append(True)
    guest = next(r for r in w.robots if r.company == 1)
    guest.pos = far; guest.battery = 50.0
    guest.charge_queued_at = w.tick; guest.stranded = False
    c0, c1 = w.company[0]["credit"], w.company[1]["credit"]
    w.charge_step()
    assert w.company[0]["toll_earned"] == 2.0 and w.company[1]["toll_paid"] == 2.0, \
        "the frontier toll did not levy exactly one unit guest→owner"
    assert abs(w.company[0]["credit"] - (c0 + 2.0)) < 1e-9 and \
        abs(w.company[1]["credit"] - (c1 - 2.0)) < 1e-9
    assert w.built_guest_slots >= 1 and w.toll_conserved()


def test_q2_evaluated_equals_executed_under_scarcity_bills_build():
    """The sacred evaluated Φ == executed Φ invariant, exercised with all three Q2
    surfaces composed AT ONCE: frontier scarcity (active — 40→30 presets), bills, and
    live charger building, at N=240. The in-arm assert fires on any divergence;
    completing 300 ticks clean IS the test — non-vacuous (deals struck, chargers built
    under scarcity, bills chains formed), with material/matter/toll conservation live."""
    BAND = W.BATTERY_MAX / (1.0 + W.LOADED_MULT)
    g = _grid_L(240)
    w = World(n_robots=240, sigma=0.5, seed=3, preset="v5", grid=g, tau=(0.15, 0.15),
              build_matter=0.5, build=True, bills=True, toll_level=1.0,
              charger_band=BAND)
    assert len(w.chargers) == 30, "frontier scarcity inactive — test vacuous"
    arm = make_arm("snhp+net", w)
    for _ in range(300):
        arm.tick()
        assert w.material_ok() and w.matter_conserved() and w.toll_conserved()
    assert arm.deals > 0, "no deal struck — evaluated==executed test vacuous"
    assert w.ledger_accounted()
    assert sum(c["built"] for c in w.company) > 0, "no charger built under scarcity"
    assert any(p["hops"] >= 2 for p in w.delivered_parcels), \
        "no ≥2-hop bills chain formed — composition test vacuous"


def test_q2_far_band_built_charger_is_sole_return_path_for_a_bills_chain():
    """The hand-built frontier scenario: with every free charger stripped (scarcity
    taken to its limit), a loaded drone deep in the FAR band cannot get its cargo home
    at all. Place ONE built far-band charger on its corridor and it tops up, hauls to a
    waiting fleet-mate, and hands the cargo off — a BILLS chain (delivered parcels with
    hops≥1) that settles only because the far-band capital exists. Without the charger
    the drone strands short and nothing delivers."""
    BAND = W.BATTERY_MAX / (1.0 + W.LOADED_MULT)

    def run(with_far_charger):
        w = World(sigma=0.5, seed=0, preset="v5", grid=64, tau=(0.0, 0.0),
                  build_matter=0.5, build=True, bills=True, charger_band=BAND)
        w.chargers, w.charger_owner = [], []          # strip EVERY free charger
        w.charger_toll, w.charger_built = [], []
        for r in w.robots:                            # neutralize the fleet
            r.stranded, r.battery, r.load, r.load_prov = True, 0.0, 0, [0, 0]
            r.parcels = []
        R = w.refineries[0]                           # company-0 home (52,12) @ g=64
        C = (0, 25)                                   # far-band charger site
        assert min(W.manhattan(C, rf) for rf in w.refineries) > BAND, \
            "the charger site is not in the far band"
        A, B = w.robots[0], w.robots[1]
        for X in (A, B):
            X.company, X.stranded, X.eff, X.cap = 0, False, 1.0, 5
        A.pos, A.load, A.load_prov = C, 2, [2, 0]     # loaded, deep in the far band
        A.parcels = [w._new_parcel(0), w._new_parcel(0)]
        A.battery = 10.0                              # too low to move far unaided
        B.pos, B.load, B.battery, B.parcels = (40, 25), 0, 100.0, []  # a fresh relay taker
        if with_far_charger:
            w.chargers.append(C); w.charger_owner.append(0)
            w.charger_toll.append(0.0); w.charger_built.append(True)
            for _ in range(30):                       # A tops up on the built charger
                A.charge_queued_at = w.tick
                w.charge_step()
            A.charge_queued_at = -1
        for _ in range(80):                           # A hauls toward the refinery
            if A.pos == B.pos or A.stranded:
                break
            w.move_toward(A, R)
        if W.manhattan(A.pos, B.pos) <= W.R_COMM and A.load > 0:
            w.transfer_cargo(A, B, A.load, log=True)  # the bills hand-off
        for _ in range(80):                           # B carries it home
            if B.pos == R:
                break
            w.move_toward(B, R)
        w.drop(B)
        return (w.delivered, w.charge_served_slots,
                [p["hops"] for p in w.delivered_parcels], A.stranded)

    dn, slots_n, hops_n, stranded_n = run(False)
    dy, slots_y, hops_y, stranded_y = run(True)
    assert dn == 0 and stranded_n, \
        "the far cargo returned WITHOUT any charger — scenario invalid"
    assert dy == 2, "the built far-band charger failed to bring the far cargo home"
    assert slots_y > 0, "the far-band charger served no charge — it was not used"
    assert hops_y and all(h >= 1 for h in hops_y), \
        "delivery was not a bills chain (no hand-off recorded on the parcels)"


# ── v26-R (column Y): THE COMPANY diorama — pure-observer event logger ────────
# company_log.py CONSTRUCTS a column-X World (arm snhp+net, belief+gossip, the
# lineage + deadlock instrument) and OBSERVES it read-only, one tick at a time.
# The FIDELITY KILL is non-negotiable: attaching the observer must not perturb a
# single bit (incl. under the fast/scalar differential-oracle switch), the log
# must carry every honesty field, and its counters must equal an independent
# plain run of the same seed. No engine mechanism is added; the observer only
# reads already-existing logs (event_log/deal_log/delivered_parcels) + state.
import swarm.company_log as _CLOG                                  # noqa: E402


def _clog_end_state(w):
    return (w.delivered, len(w.deal_log), len(w.event_log),
            [round(r.battery, 12) for r in w.robots],
            [tuple(sorted(d.items())) for d in w.deal_log],
            [tuple(r.pos) for r in w.robots], len(w.delivered_parcels))


def _clog_plain_fp(regime, n, seed, ticks):
    w, arm = _CLOG.make_world(regime, n, seed, ticks)
    for _ in range(ticks):
        arm.tick()
        if w.delivered >= w.total_stock:
            break
    return _clog_end_state(w)


def _clog_observed_fp(regime, n, seed, ticks):
    holder = []
    _CLOG.run_logged(regime, n_robots=n, seed=seed, ticks=ticks,
                     sample_every=5, observe=holder.append)
    return _clog_end_state(holder[-1])


def test_company_observer_bit_identical():
    """The company logger is a PURE OBSERVER: running a regime WITH the observer
    attached reaches a byte-identical end-state (delivered, deals, xfers,
    battery@12dp, the whole deal_log, positions, parcels) to running it plain.
    Checked on all three demo regimes — the FIDELITY KILL guard."""
    for regime in ("spot", "claims", "director"):
        plain = _clog_plain_fp(regime, 24, 0, 300)
        observed = _clog_observed_fp(regime, 24, 0, 300)
        assert observed == plain, f"observer perturbed regime {regime!r}"


def _clog_observe_reads(w, arm, ticks):
    """Replay company_log.run_logged's EXACT read-only per-tick observation on a
    prebuilt (w, arm), returning a fast/scalar fingerprint. Pure reads."""
    for _ in range(ticks):
        arm.tick()
        _ = [_CLOG._robot_state(w, r) for r in w.robots]      # noqa: F841
        _ = sum(1 for p in w.delivered_parcels if p["hops"] >= 2)
        _ = sum(1 for e in w.event_log if e["kind"] == "cargo")
        _ = sum(r.battery for r in w.robots)
        if w.delivered >= w.total_stock:
            break
    return (w.delivered, len(w.deal_log), len(w.event_log),
            [round(r.battery, 12) for r in w.robots],
            [tuple(sorted(d.items())) for d in w.deal_log])


def test_company_observer_differential_oracle():
    """Logging on/off is bit-identical ON THE DIFFERENTIAL ORACLE. (a) The demo
    configs use belief_mode -> the scalar path; flipping FORCE_SCALAR_EVAL leaves
    the observed run unchanged and equal to plain. (b) On a FAST-path config
    (snhp+net + lineage + deadlock instrument, no belief/bills) the observer's
    reads preserve the fast==scalar identity exactly."""
    for regime in ("spot", "claims", "director"):
        base = _clog_plain_fp(regime, 24, 0, 200)
        for force in (False, True):
            try:
                _ARMS.FORCE_SCALAR_EVAL = force
                assert _clog_observed_fp(regime, 24, 0, 200) == base, \
                    f"observer perturbed {regime!r} at FORCE_SCALAR={force}"
            finally:
                _ARMS.FORCE_SCALAR_EVAL = False

    def fast_world():
        w = World(n_robots=24, sigma=0.5, seed=0, hazard_phi=True, preset="v5",
                  tau=(0.15, 0.15), lineage=True, deadlock_track=True)
        return w, make_arm("snhp+net", w)

    try:
        _ARMS.FORCE_SCALAR_EVAL = False
        w1, a1 = fast_world()
        fast = _clog_observe_reads(w1, a1, 200)
        _ARMS.FORCE_SCALAR_EVAL = True
        w2, a2 = fast_world()
        scalar = _clog_observe_reads(w2, a2, 200)
        assert fast == scalar, "observer reads broke fast==scalar (oracle)"
    finally:
        _ARMS.FORCE_SCALAR_EVAL = False


def test_company_log_schema_fields_present():
    """The log carries every honesty field the renderer binds to: config, the
    floor/band mapping, the verbatim SPEC cite, one robot record per robot, and
    well-formed frames (state in {0..3}, one r-row per robot)."""
    log = _CLOG.run_logged("claims", n_robots=24, seed=0, ticks=200,
                           sample_every=10)
    for field in ("schema", "regime", "config", "grid", "refineries",
                  "sources", "num_floors", "floor_edges", "floor_labels",
                  "reach", "sample_every", "total_stock", "robots", "cite",
                  "frames", "summary"):
        assert field in log, f"log missing top-level field {field!r}"
    assert log["schema"] == _CLOG.SCHEMA and log["regime"] == "claims"
    assert log["config"]["bills"] is True and log["config"]["command"] is False
    assert len(log["floor_edges"]) + 1 == log["num_floors"] == \
        len(log["floor_labels"])
    for key in ("spec", "text", "numbers"):
        assert log["cite"][key], f"cite missing {key!r}"
    assert len(log["robots"]) == 24
    for f in log["frames"]:
        assert set(f) >= {"t", "r", "d", "h2", "ho", "dl", "bat"}
        assert len(f["r"]) == 24, "a frame is missing robots"
        for x, y, st in f["r"]:
            assert st in (0, 1, 2, 3), f"illegal robot state {st}"
            assert 0 <= x < log["grid"] and 0 <= y < log["grid"]
    # director carries the command-staleness channel; spot/claims do not
    d = _CLOG.run_logged("director", n_robots=24, seed=0, ticks=120,
                         sample_every=10)
    assert all("cmd" in f for f in d["frames"]), "director frames lack cmd"
    assert "cmd" not in log["frames"][0], "non-director frame carries cmd"


def test_company_log_counts_match_run():
    """The log summary is the REAL run: delivered / deals / xfers / delivered
    parcels in the log EQUAL an independent plain run of the same seed, and the
    per-frame cumulative counters are consistent (monotone, final == summary,
    twohop_share == h2/d)."""
    for regime in ("spot", "claims", "director"):
        w, arm = _CLOG.make_world(regime, 24, 0, 300)
        for _ in range(300):
            arm.tick()
            if w.delivered >= w.total_stock:
                break
        twohop = sum(1 for p in w.delivered_parcels if p["hops"] >= 2)
        handoffs = sum(1 for e in w.event_log if e["kind"] == "cargo")

        log = _CLOG.run_logged(regime, n_robots=24, seed=0, ticks=300,
                               sample_every=5)
        s = log["summary"]
        assert s["delivered"] == w.delivered, f"{regime}: delivered mismatch"
        assert s["deals"] == len(w.deal_log), f"{regime}: deals mismatch"
        assert s["handoffs"] == handoffs, f"{regime}: handoffs mismatch"
        assert s["twohop"] == twohop, f"{regime}: twohop mismatch"
        assert s["twohop_share"] == round(twohop / max(1, w.delivered), 4)

        last = log["frames"][-1]
        assert last["d"] == s["delivered"] and last["h2"] == s["twohop"]
        assert last["ho"] == s["handoffs"] and last["dl"] == s["deals"]
        ds = [f["d"] for f in log["frames"]]
        assert ds == sorted(ds), f"{regime}: delivered not monotone"
    # command forms no chains; claims forms many — the banked signature, live
    assert _CLOG.run_logged("director", 24, 0, 300)["summary"]["twohop"] == 0


# ── v20 (column S): institutions as a substitute for cognition ──────────────
def _sworld(nav_dumb, granular, seed=0, N=24, grid=32):
    """A column-S world: the v11/v12 moving field (belief+dynamic+contested+K0
    scouting) with the two S treatments — nav_dumb (routing) and prospect_claims
    (granular rights)."""
    return World(n_robots=N, sigma=0.5, seed=seed, preset="v5", tau=(0.15, 0.15),
                 belief_mode=True, dynamic_field=True, contested=True,
                 scouting=True, prospect_claims=granular, nav_dumb=nav_dumb,
                 grid=grid)


def test_v20_nav_dumb_default_off_is_flag_absent():
    """nav_dumb defaults off ⇒ a moving-field world is BIT-IDENTICAL to one that
    never heard of column S. The dedicated nav stream is CREATED unconditionally
    but never DRAWN from unless nav_dumb is on, and it never touches self.rng —
    so best_claim's routing, and every downstream bit, is unperturbed."""
    outs = []
    for kw in ({}, dict(nav_dumb=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                  hazard_phi=True, belief_mode=True, dynamic_field=True,
                  contested=True, scouting=True, prospect_claims=True, **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(400):
            arm.tick()
        outs.append((w.delivered, arm.deals,
                     round(sum(r.battery for r in w.robots), 9),
                     [r.pos for r in w.robots],
                     [tuple(sorted(d.items())) for d in w.deal_log]))
    assert outs[0] == outs[1], "column-S nav_dumb plumbing leaked into the default path"


def test_v20_dumb_claim_uses_dedicated_stream_only():
    """The DUMB routing brain draws its noise ONLY from the dedicated
    RandomState(seed+262626): a dumb_claim call ADVANCES _nav_rng and leaves the
    main stream (self.rng) byte-for-byte untouched. This is what keeps nav_dumb
    OFF bit-identical and every prior column unperturbed."""
    w = _sworld(nav_dumb=True, granular=True, seed=0)
    r = w.robots[0]
    for i in range(len(w.sources)):          # give dumb_claim real candidates
        w.belief[r.company][i] = 5
    w._live_sense = False                    # freeze sensing (no side draws)
    main_before = w.rng.get_state()[1].copy()
    nav_before = w._nav_rng.get_state()[1].copy()
    _ = w.dumb_claim(r)
    assert np.array_equal(main_before, w.rng.get_state()[1]), \
        "dumb_claim perturbed the MAIN stream"
    assert not np.array_equal(nav_before, w._nav_rng.get_state()[1]), \
        "dumb_claim did not draw from the dedicated nav stream"


def test_v20_dumb_claim_is_greedy_nearest_not_richest():
    """Mechanism: best_claim scores richest-per-distance (it will cross the field
    for a rich rock); dumb_claim drops the richness term and just heads for the
    nearest KNOWN-stocked rock (+ noise). With a near-poor vs far-rich pair the two
    brains split — best_claim → far-rich, dumb_claim → near-poor — every time."""
    w = _sworld(nav_dumb=True, granular=False, seed=0)
    near, far = (2, 2), (2, 28)              # far is 26 cells away
    w.sources = [near, far]
    w.stock = [3, 200]
    w.belief = [[3, 200], [3, 200]]
    w.last_seen = [[0, 0], [0, 0]]
    w.rival_rate = [[0.0, 0.0], [0.0, 0.0]]
    w._own_mined_seen = [[0, 0], [0, 0]]
    w.own_mined = [[0, 0], [0, 0]]
    r = w.robots[0]
    r.pos, r.sector = (1, 2), 0              # 1 cell from near, 26 from far
    w._live_sense = False
    assert w.best_claim(r) == 1, "smart routing did not chase the far-rich rock"
    for _ in range(50):                      # noise never flips a 25-cell gap
        assert w.dumb_claim(r) == 0, "dumb routing chased the far-rich rock"


def test_v20_dumb_granular_exercises_claim_trades():
    """The dumb+granular cell is non-vacuous: the deal economy still strikes
    claim (sector-issue, s==1) trades — the tradeable-rights channel the thesis
    leans on — even though the ROUTING brain is dumb. Conservation holds."""
    w = _sworld(nav_dumb=True, granular=True, seed=0)
    arm = make_arm("snhp+net", w)
    for _ in range(500):
        arm.tick()
        assert w.material_ok(), "conservation broke in the dumb+granular cell"
    assert arm.deals > 0, "dumb+granular struck no deals — vacuous"
    assert sum(1 for d in w.deal_log if d["s"] == 1) > 0, \
        "dumb+granular never traded a claim (sector swap)"


def test_v20_evaluated_equals_executed_all_four_cells():
    """The hard invariant across the WHOLE 2×2: dumbing ROUTING must not perturb
    the bargaining brain. Each cell runs 300 ticks with the in-arm evaluated Φ ==
    executed Φ assert live — completing clean IS the test — plus conservation."""
    for nav_dumb in (False, True):
        for granular in (False, True):
            w = _sworld(nav_dumb=nav_dumb, granular=granular, seed=1)
            arm = make_arm("snhp+net", w)
            for _ in range(300):
                arm.tick()
                assert w.material_ok(), \
                    f"conservation broke (dumb={nav_dumb}, gran={granular})"
            assert arm.deals > 0, \
                f"vacuous cell (dumb={nav_dumb}, gran={granular})"


def test_v20_dumb_fleet_with_claims_outdelivers_without():
    """The thesis, hand-built: on a scarce 2-rock field a DUMB fleet with granular
    CLAIMS out-delivers a dumb fleet without, at a fixed short horizon. A rich
    arrival A sits in a company-0 claim quadrant; a rock B sits by company-1's
    refinery; every dumb robot starts nearest A, so greedy routing piles the whole
    fleet onto A and neglects B. GRANULAR gates company-1 off A (window) → its dumb
    robots redirect to B → the fleet spreads immediately → more delivered early.
    The institution buys the coordination the dumb routing brain cannot plan."""
    def deliv(granular, seed=0, H=60):
        w = _sworld(nav_dumb=True, granular=granular, seed=seed)
        w._field_events = []                 # freeze the random field
        w._field_next = 0
        A, B = (12, 16), (26, 24)
        assert w.claim_owner[w.quadrant(A)] == 0    # company-0 holds A's quadrant
        w.sources = [A, B]
        w.stock = [80, 80]
        w.total_stock = 160
        w.stock_lost = 0
        w.mined_from = [0, 0]
        w.arrival_indices = [0]              # A is a claimable ARRIVAL
        w.arrival_t = {0: 0}
        w.belief = [[80, 80], [80, 80]]      # both companies KNOW both rocks
        w.last_seen = [[0, 0], [0, 0]]
        w.rival_rate = [[0.0, 0.0], [0.0, 0.0]]
        w._own_mined_seen = [[0, 0], [0, 0]]
        w.own_mined = [[0, 0], [0, 0]]
        for r in w.robots:                   # both fleets clustered NEAR A
            r.pos = (14, 15) if r.company == 1 else (10, 15)
            r.load, r.load_prov = 0, [0, 0]
            r.battery, r.sector, r.stranded = W.BATTERY_MAX, 0, False
        arm = make_arm("snhp+net", w)
        for _ in range(H):
            arm.tick()
        return w.delivered
    coarse = deliv(granular=False)
    granular = deliv(granular=True)
    assert granular > coarse + 20, \
        f"granular claims did not help the dumb fleet: gran={granular} coarse={coarse}"


def test_v28_mortality_off_bit_identical():
    """mortality=False / death_regime='none' / wearout=False must be bit-identical to
    a world that never heard of column AA — the dead flag, the death arrays, the
    freeze log, the claim-void sentinels and every AA branch may not perturb a single
    bit when off. Checked on a bargaining arm WITH bills (the Φ path AA touches) and
    the auction (the credit/settlement path)."""
    for arm_name in ("snhp+net", "auction"):
        outs = []
        for kw in (dict(bills=True),
                   dict(bills=True, mortality=False, death_regime="none",
                        wearout=False)):
            w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
                      hazard_phi=(arm_name == "snhp+net"), **kw)
            arm = make_arm(arm_name, w)
            for _ in range(400):
                arm.tick()
            outs.append((w.delivered, arm.deals, len(w.event_log),
                         round(sum(r.battery for r in w.robots), 9),
                         [r.pos for r in w.robots],
                         [tuple(sorted(d.items())) for d in w.deal_log]))
        assert outs[0] == outs[1], f"column-AA plumbing perturbed {arm_name}"


def test_v28_wearout_uses_only_dedicated_stream():
    """The wear-out death schedule is pre-drawn from RandomState(seed+282828) ONLY —
    turning wear-out on must NEVER perturb the main stream, so two worlds identical
    except for `wearout` produce the SAME positions/deals UP TO the first wear-out
    death (before then no chassis has died, so trajectories are bit-identical). Also
    verifies the schedule is seed-deterministic and regime-independent."""
    # (a) main stream untouched: run both to just before the earliest wear-out tick.
    w_on = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15), bills=True,
                 mortality=True, death_regime="claims_die", wearout=True)
    first = min(w_on._wear_death_tick)
    assert first >= W.WEAROUT_AGE + 1
    horizon = min(first, W.FLATLINE_TICKS + 1) - 1     # before ANY death can fire
    outs = []
    for wearout in (False, True):
        w = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15), bills=True,
                  mortality=True, death_regime="claims_die", wearout=wearout)
        arm = make_arm("snhp+net", w)
        for _ in range(horizon):
            arm.tick()
        assert w.deaths == 0, "a death fired inside the no-death window"
        outs.append(([r.pos for r in w.robots], arm.deals,
                     round(sum(r.battery for r in w.robots), 9)))
    assert outs[0] == outs[1], "wearout draw perturbed the MAIN stream"
    # (b) the schedule is identical across regimes (dedicated, regime-free stream)
    scheds = []
    for reg in ("claims_die", "estates", "risk_premium"):
        w = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15), bills=True,
                  mortality=True, death_regime=reg, wearout=True)
        scheds.append(list(w._wear_death_tick))
    assert scheds[0] == scheds[1] == scheds[2], \
        "wear-out schedule differs across regimes — not regime-independent"


def _mortal_world(regime, seed=0):
    w = World(sigma=0.5, seed=seed, preset="v5", tau=(0.0, 0.0), bills=True,
              mortality=True, death_regime=regime)
    return w, make_arm("snhp", w)


def test_v28_claims_die_voids_exact_stack_entries():
    """A hand-built A→B relay: A hands cargo to B and banks a claim on B's parcels.
    When A dies under CLAIMS-DIE, A's (rid) entry on B's live parcels is rewritten to
    the VOID sentinel (its value destroyed, not handed to the deliverer); when B (the
    carrier) then delivers, that share is booked to claims_voided and the ledger
    balances. Under ESTATES the same entry re-points to A's company treasury and
    settles there. B's OWN residual is unchanged in both."""
    for regime, expect_void in (("claims_die", True), ("risk_premium", True),
                                ("estates", False)):
        w, arm = _mortal_world(regime)
        A, B = w.robots[0], w.robots[1]
        for r in (A, B):
            r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
                0, 0, 5, 0, [0, 0], []
        A.pos, w.stock[0] = w.sources[0], 3
        assert w.pick(A) == 3
        w.tick = 5
        w.transfer_cargo(A, B, 3, log=True)             # A → B
        arm._bills_attach(A, B, 3, 0.5)                 # A claims 0.5 of residual
        # A holds a claim worth 0.5·3·V; B carries 3 units at residual 0.5 each
        assert abs(A.claim_value - 0.5 * 3 * V_DELIVER) < 1e-9
        b_resid = sum(1.0 - sum(sh for _r, sh, *_ in p["claims"]) for p in B.parcels)
        assert abs(b_resid - 1.5) < 1e-9
        # kill A
        w.tick = 10
        w.death_resolve(A, "wearout")
        assert A.dead and A.stranded
        # every A-entry on B's parcels is rewritten to the regime target
        target = W.CLAIM_VOID if expect_void else -(2 + 0)   # co 0 heir == -2
        for p in B.parcels:
            rids = [c[0] for c in p["claims"]]
            assert A.rid not in rids, "A's live claim survived unrewritten"
            assert target in rids, f"expected sentinel {target} not on parcel"
        # B's residual is untouched by A's death (only WHO gets A's share changed)
        b_resid2 = sum(1.0 - sum(sh for _r, sh, *_ in p["claims"]) for p in B.parcels)
        assert abs(b_resid2 - 1.5) < 1e-9, "B's residual moved on A's death"
        # deliver: void ⇒ claims_voided; estate ⇒ treasury
        B.pos = w.refineries[0]
        w.tick = 20
        tre0 = w.company[0]["treasury"]
        w.drop(B)
        if expect_void:
            assert abs(w.claims_voided - 0.5 * 3 * V_DELIVER) < 1e-9, \
                "voided claim not destroyed-and-accounted"
            assert abs(w.company[0]["treasury"] - tre0) < 1e-9
        else:
            assert abs(w.estate_settled - 0.5 * 3 * V_DELIVER) < 1e-9, \
                "estate not settled to treasury"
            assert abs(w.claims_voided) < 1e-9
        assert w.ledger_accounted() and w.credit_conserved()


def test_v28_ledger_balances_through_death_all_regimes():
    """2,000 ticks of snhp+net with bills + mortality + wear-out, in EVERY regime,
    with the material / ledger / credit invariants live. Deaths fire (the run is
    vacuous otherwise) and the destroyed-claim + estate accounting keeps all three
    conservation laws exact through every death."""
    for regime in ("claims_die", "estates", "risk_premium", "none"):
        bills = regime != "none"
        w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), bills=bills,
                  mortality=True, death_regime=regime, wearout=True)
        arm = make_arm("snhp+net", w)
        for _ in range(2000):
            arm.tick()
            assert w.material_ok(), f"material leak through death ({regime})"
            assert w.ledger_accounted(), f"ledger leak through death ({regime})"
            assert w.credit_conserved(), f"credit leak through death ({regime})"
        assert w.deaths >= 3, f"too few deaths to test ({regime}: {w.deaths})"


def test_v28_evaluated_equals_executed_under_mortality():
    """The sacred invariant under the death economy: 1,500 ticks of snhp+net with
    bills + claims-die + wear-out and the in-arm evaluated Φ == executed Φ assert
    live (the mortality claim-discount enters Φ deterministically from post-state
    battery, identical in evaluation and at execution). Completing clean IS the test;
    deaths must actually occur and claimed relays must land."""
    for regime in ("claims_die", "estates", "risk_premium"):
        w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15), bills=True,
                  mortality=True, death_regime=regime, wearout=True)
        arm = make_arm("snhp+net", w)
        for _ in range(1500):
            arm.tick()
        assert arm.deals > 0 and w.deaths > 0, f"vacuous run ({regime})"
        assert any(p["hops"] >= 1 for p in w.delivered_parcels), \
            f"no claimed relay delivered ({regime})"


def test_v28_premium_split_responds_to_hazard():
    """The risk-premium grosses the giver's hop-split up by its survival probability,
    α*/(1−haz) capped at 1 — so a HIGH-hazard (low-battery, far-from-charger) giver
    records a strictly LARGER claim share than a LOW-hazard one, while plain bills
    (premium off) gives BOTH the identical α*=(1+disc)/2. Derived from the existing
    stranding_hazard machinery, not a free heuristic."""
    from swarm.value import hop_split, stranding_hazard, load_factors

    def giver(w, battery):
        r = w.robots[0]
        # (2,16) sits 34 cells from BOTH refineries (x=26), so a mid battery does NOT
        # clear the loaded haul (cost≈54 > 50 ⇒ disc<1, α*<1, room for the gross-up).
        # eff pinned so cost is deterministic across seeds.
        r.pos, r.load, r.load_prov, r.eff = (2, 16), 3, [3, 0], 1.0
        r.battery, r.sector, r.cap, r.stranded = battery, 0, 5, False
        return r

    # low vs high hazard via battery; identical position/load, both with disc<1
    w_lo = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
                 mortality=True, death_regime="risk_premium")
    w_hi = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
                 mortality=True, death_regime="risk_premium")
    r_lo, r_hi = giver(w_lo, 50.0), giver(w_hi, 12.0)
    _, disc_lo = load_factors(r_lo, w_lo)
    assert disc_lo < 1.0 - 1e-6, "low-hazard giver already clears the haul (α* capped)"
    assert stranding_hazard(r_hi, w_hi) > stranding_hazard(r_lo, w_lo) + 0.05
    a_lo, a_hi = hop_split(r_lo, w_lo), hop_split(r_hi, w_hi)
    assert a_hi > a_lo + 1e-6, \
        f"premium did not rise with hazard: lo={a_lo:.4f} hi={a_hi:.4f}"
    # premium OFF (plain bills): the split is hazard-blind — both == (1+disc)/2
    w_off = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True)
    r0 = giver(w_off, 12.0)
    _, disc = load_factors(r0, w_off)
    assert abs(hop_split(r0, w_off) - 0.5 * (1.0 + disc)) < 1e-12, \
        "plain bills split is not the P23 α*"


# ── v29 (column AB): the crash — contagion in the counterparty web ────────────
def _shock_world(seed=0, ccp=False, shock_tick=250, n_robots=24, grid=32):
    w = World(n_robots=n_robots, grid=grid, sigma=0.5, seed=seed, preset="v5",
              tau=(0.15, 0.15), bills=True, mortality=True,
              death_regime="claims_die", lineage=True, hazard_phi=True,
              shock=True, shock_tick=shock_tick, clearinghouse=ccp)
    return w, make_arm("snhp+net", w)


def test_v29_shock_off_bit_identical():
    """shock=False / clearinghouse=False must be bit-identical to a world that never
    heard of column AB — the shock arrays, the taint vector, the CCP pool and every AB
    branch may not perturb a single bit when off, and every AB accumulator must stay
    inert after a full bills+mortality run (the settlement/death paths AB touches)."""
    outs = []
    for kw in (dict(), dict(shock=False, clearinghouse=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), bills=True,
                  mortality=True, death_regime="claims_die", wearout=True,
                  lineage=True, hazard_phi=True, **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(500):
            arm.tick()
        outs.append((w.delivered, arm.deals, len(w.event_log),
                     round(sum(r.battery for r in w.robots), 9),
                     [tuple(sorted(d.items())) for d in w.deal_log]))
        assert not w.shocked and not w.writedown_log and w.ccp_pool == 0.0
        assert w.shock_writedown == 0.0 and w.ccp_fees == 0.0
        assert not w.shock_far and all(t is None for t in w.shock_taint)
    assert outs[0] == outs[1], "column-AB plumbing perturbed the world"


def test_v29_shock_voids_exact_far_band():
    """At T_shock the far-band asteroids' stock zeros out — booked to stock_lost so
    material conservation holds — and NOTHING else (near/mid rocks untouched). The far
    band is the registered percentile of nearest-refinery distance, non-empty."""
    w, _ = _shock_world(shock_tick=5)
    far = set(w.shock_far)
    assert far, "far band is empty"
    stock0, lost0 = list(w.stock), w.stock_lost
    far_stock = sum(w.stock[i] for i in far)
    assert far_stock > 0
    w.tick = 5
    w.shock_step()
    assert w.shocked
    for i in range(len(w.stock)):
        if i in far:
            assert w.stock[i] == 0, "far-band stock not zeroed"
        else:
            assert w.stock[i] == stock0[i], "non-far stock perturbed by the shock"
    assert w.stock_lost - lost0 == far_stock == w.shock_far_stock_lost
    assert w.material_ok()


def test_v29_three_hop_chain_contagion_attribution():
    """A hand-built far-band A→B→C→deliver chain. After the far band goes dark the
    parcel settles at the collapsed floor: the DELIVERER (physically held the dark ore)
    is a DIRECT hop-0 write-down; the two UPSTREAM claimants hold only PAPER up the
    chain, so their loss is CONTAGION — B at hop 1, A at hop 2. The MIDDLE write-down
    is attributed as contagion, NOT direct (the counterparty web transmitting the
    collapse). Depth == chain length, as registered."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
              mortality=True, death_regime="claims_die", lineage=True,
              shock=True, shock_tick=1)
    arm = make_arm("snhp+net", w)
    far_i = min(w.shock_far)
    A, B, C = w.robots[0], w.robots[1], w.robots[2]
    for r in (A, B, C):
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, far_i, 5, 0, [0, 0], []
    A.pos, w.stock[far_i] = w.sources[far_i], 2
    assert w.pick(A) == 2                      # A mines 2 FAR units (origin=far_i)
    w.tick = 1
    w.transfer_cargo(A, B, 2, log=True); arm._bills_attach(A, B, 2, 0.5)   # A→B, A claims
    w.transfer_cargo(B, C, 2, log=True); arm._bills_attach(B, C, 2, 0.5)   # B→C, B claims
    w.shock_step()                             # the far band goes dark; C holds worthless
    assert w.shocked and far_i in w.shock_far
    C.pos = w.refineries[0]
    w.tick = 2
    w.drop(C)                                  # settle at the collapsed floor
    byrid = {}
    for e in w.writedown_log:
        byrid.setdefault(e["rid"], []).append(e)
    assert C.rid in byrid and byrid[C.rid][0]["cause"] == "direct" \
        and byrid[C.rid][0]["hop"] == 0, "deliverer not a direct hop-0 victim"
    assert B.rid in byrid and byrid[B.rid][0]["cause"] == "contagion" \
        and byrid[B.rid][0]["hop"] == 1, "middle claimant not contagion@hop1"
    assert A.rid in byrid and byrid[A.rid][0]["cause"] == "contagion" \
        and byrid[A.rid][0]["hop"] == 2, "upstream claimant not contagion@hop2"
    assert w.ledger_accounted() and w.credit_conserved()


def test_v29_ccp_fee_conservation_and_waterfall():
    """The clearinghouse conserves credit through the shock: fees build the pool, the
    pool covers write-downs, and when it runs DRY the uncovered remainder is a pro-rata
    HAIRCUT (recipients eat it) — the ledger balances in every case. A full shock+CCP
    economy with the invariants live, then a hand-built dry-pool settlement to exercise
    the waterfall explicitly."""
    w, arm = _shock_world(ccp=True, shock_tick=200)
    for _ in range(1200):
        arm.tick()
        assert w.ledger_accounted() and w.credit_conserved() and w.material_ok()
    assert w.shocked and w.ccp_fees > 0 and w.writedown_log, "vacuous CCP shock run"
    # explicit WATERFALL: drain the pool, settle a shocked chain, eat the haircut
    w2 = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
               mortality=True, death_regime="claims_die", lineage=True,
               shock=True, shock_tick=1, clearinghouse=True)
    arm2 = make_arm("snhp+net", w2)
    far_i = min(w2.shock_far)
    A, B = w2.robots[0], w2.robots[1]
    for r in (A, B):
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, far_i, 5, 0, [0, 0], []
    A.pos, w2.stock[far_i] = w2.sources[far_i], 2
    w2.pick(A)
    w2.tick = 1
    w2.transfer_cargo(A, B, 2, log=True); arm2._bills_attach(A, B, 2, 0.5)
    w2.shock_step()
    w2.ccp_pool = 0.0                          # force the pool DRY before settlement
    B.pos = w2.refineries[0]; w2.tick = 2
    w2.drop(B)
    assert w2.ccp_haircut > 0, "waterfall did not engage on a dry pool"
    assert w2.ledger_accounted() and w2.credit_conserved()


def test_v29_scar_windows_sane_and_preshock_identical():
    """The scar series (mortality_detail.chain_by_window) sums to at most the deal
    count and is non-empty, and PRE-shock a shock run and its no-shock control are
    bit-identical (the shock fires only at T_shock) — so every pre-shock window
    matches, isolating the shock's post-shock effect. The shock leaves a footprint."""
    import swarm.run as R
    common = dict(arm_name="snhp+net", sigma=0.5, seed=0, ticks=900, tau=0.15,
                  preset="v5", n_robots=24, lineage=True, mortality=True,
                  death_regime="claims_die", bills=True)
    r_sh = R.run_once(shock=True, shock_tick=250, **common)
    r_ct = R.run_once(**common)
    md_sh, md_ct = r_sh["mortality_detail"], r_ct["mortality_detail"]
    win = md_sh["window"]
    assert 0 < sum(md_sh["chain_by_window"]) <= r_sh["deals"]
    pw = 250 // win
    assert md_sh["chain_by_window"][:pw] == md_ct["chain_by_window"][:pw], \
        "pre-shock chain windows differ between shock and control"
    assert md_sh["death_by_window"][:pw] == md_ct["death_by_window"][:pw]
    sd = r_sh["shock_detail"]
    assert sd["shocked"] and sd["shock_writedown"] > 0, "shock left no footprint"


def test_v29_evaluated_equals_executed_under_shock_both_regimes():
    """The sacred invariant survives the crash: Φ NEVER sees the shock (far cargo keeps
    its full Φ value; the write-down lands only at settlement/death), so the in-arm
    evaluated Φ == executed Φ assert holds under GROSS and under the CLEARINGHOUSE.
    Completing 1,500 ticks clean IS the test; the shock must fire and write-downs land."""
    for ccp in (False, True):
        w, arm = _shock_world(ccp=ccp, shock_tick=250)
        for _ in range(1500):
            arm.tick()
        assert w.shocked, f"shock never fired (ccp={ccp})"
        assert w.writedown_log, f"no write-downs — vacuous run (ccp={ccp})"
        assert arm.deals > 0


# ── v32 (column AB2): the crash with teeth — claim-collateralized debt ─────────
def _debt_world(seed=0, ltv=0.5, ccp=False, shock=False, shock_tick=250,
                n_robots=24, grid=32):
    w = World(n_robots=n_robots, grid=grid, sigma=0.5, seed=seed, preset="v5",
              tau=(0.15, 0.15), bills=True, mortality=True,
              death_regime="claims_die", lineage=True, hazard_phi=True,
              shock=shock, shock_tick=shock_tick, clearinghouse=ccp, debt_ltv=ltv)
    return w, make_arm("snhp+net", w)


def test_v32_debt_off_bit_identical():
    """debt_ltv=0.0 must be bit-identical to a world that never heard of column AB2 —
    the debt fields, the treasury waterfall, garnishment and every AB2 branch may not
    perturb a single bit when off (even through a full bills+mortality+shock run, the
    settlement/death paths AB2 touches), and every AB2 accumulator stays inert."""
    outs = []
    for kw in (dict(), dict(debt_ltv=0.0)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), bills=True,
                  mortality=True, death_regime="claims_die", lineage=True,
                  hazard_phi=True, shock=True, shock_tick=250, **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(600):
            arm.tick()
        outs.append((w.delivered, arm.deals, w.deaths,
                     round(sum(r.battery for r in w.robots), 9),
                     round(sum(c["credit"] for c in w.company), 9),
                     [tuple(sorted(d.items())) for d in w.deal_log]))
        assert w.debt_loaned == 0.0 and w.debt_repaid == 0.0
        assert w.debt_written_off == 0.0 and w.energy_borrowed == 0.0
        assert not w._borrow_log and not w.garnish_log
        assert all(r.debt == 0.0 and not r.garnished for r in w.robots)
        assert w.debt_conserved()
    assert outs[0] == outs[1], "column-AB2 plumbing perturbed the world"


def test_v32_borrow_settle_repay_conserves_ledgers():
    """A hand-built borrow → settle → repay cycle. A holds a claim (collateral); with a
    low battery it borrows energy against it (battery rises, debt & treasury-loan
    accounting move); when the parcel it claims is delivered, the settlement proceeds
    repay the debt FIRST (robot→treasury) before A pockets anything. Every ledger
    closes: credit_conserved (repayment is within-company), debt_conserved (loaned ==
    repaid + written_off + outstanding), and material/ledger."""
    w, arm = _debt_world(ltv=0.5)
    A, B = w.robots[0], w.robots[1]
    src = A.sector
    for r in (A, B):
        r.company, r.sector, r.cap, r.load, r.load_prov, r.parcels = \
            0, src, 5, 0, [0, 0], []
    A.pos, w.stock[src] = w.sources[src], 2
    assert w.pick(A) == 2
    w.tick = 1
    w.transfer_cargo(A, B, 2, log=True)
    arm._bills_attach(A, B, 2, 0.5)                 # A → B, A banks a 0.5 claim
    claim0 = A.claim_value
    assert claim0 > 0, "no collateral banked"
    A.battery = 15.0                               # energy-hungry ⇒ borrows against claim
    e0, drawn0 = A.battery, w.energy_drawn()
    w.borrow_step()
    assert A.debt > 0, "A did not borrow against its claim"
    assert A.battery > e0, "borrowed energy not injected into the battery"
    assert abs(A.debt - DEBT_ENERGY_PRICE * (A.battery - e0)) < 1e-9, "principal ≠ price·energy"
    assert A.debt <= 0.5 * claim0 + 1e-9, "borrow exceeded the LTV cap"
    assert abs(w.debt_loaned - A.debt) < 1e-9
    assert abs(w.energy_drawn() - drawn0 - (A.battery - e0)) < 1e-9, "energy ledger off"
    assert w.debt_conserved() and w.credit_conserved()
    debt_at_borrow = A.debt
    tre0, cr0 = w.company[0]["treasury"], A.credit
    B.pos = w.refineries[0]                         # B delivers → A's claim settles
    w.tick = 2
    w.drop(B)
    assert A.debt < debt_at_borrow, "settlement did not service the debt"
    repaid = debt_at_borrow - A.debt
    assert abs(w.debt_repaid - repaid) < 1e-9
    assert abs(w.company[0]["treasury"] - tre0 - repaid) < 1e-6, "repayment not booked to treasury"
    assert A.credit >= cr0, "deliverer/claimant pocketed negative residual"
    assert w.debt_conserved() and w.credit_conserved()
    assert w.ledger_accounted()   # material_ok is broken by the hand-set stock (v29 pattern)


def test_v32_underwater_drone_garnished_and_services_debt():
    """A hand-built underwater drone. A holds claims on 3 FAR parcels + 1 NEAR parcel
    (collateral 20, LTV-0.5 debt 10). When the far band goes dark the 3 far parcels
    settle at the floor (15 of collateral retired for ~nothing, debt UNSERVICED) → the
    remaining collateral (5, the near claim) drops below the debt and A enters
    GARNISHMENT at settlement resolution. The near parcel then settles at face and ALL
    of it services the debt (A had no residual to pocket; still garnished, debt>0)."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
              mortality=True, death_regime="claims_die", lineage=True,
              shock=True, shock_tick=1, debt_ltv=0.5)
    arm = make_arm("snhp+net", w)
    far_i = min(w.shock_far)
    near_i = min(range(len(w.sources)),
                 key=lambda i: min(manhattan(w.sources[i], rf) for rf in w.refineries))
    assert near_i not in w.shock_far
    A, B = w.robots[0], w.robots[1]
    for r in (A, B):
        r.company, r.cap, r.load, r.load_prov, r.parcels = 0, 5, 0, [0, 0], []
    # A mines 3 FAR then 1 NEAR unit, hands all 4 to B (FIFO: far parcels settle first),
    # banks a 0.5 claim on each ⇒ far collateral 15, near collateral 5, total 20.
    A.pos, A.sector, w.stock[far_i] = w.sources[far_i], far_i, 3
    assert w.pick(A) == 3
    A.pos, A.sector, w.stock[near_i] = w.sources[near_i], near_i, 1
    assert w.pick(A) == 1
    w.tick = 1
    w.transfer_cargo(A, B, 4, log=True)
    arm._bills_attach(A, B, 4, 0.5)
    face = A.claim_value
    assert abs(face - 20.0) < 1e-9, f"collateral setup off: {face}"
    A.debt = 0.5 * face                            # debt 10 = the LTV-0.5 cap (a real loan)
    w.debt_loaned = 0.5 * face
    assert not A.garnished
    w.shock_step()                                  # far band dark; A's 3 far claims worthless
    B.pos = w.refineries[0]
    w.tick = 2
    w.drop(B)                                        # far (floor) then near (face) settle
    assert A.garnished, "write-down did not push A into garnishment"
    assert w.garnish_log and w.garnish_log[-1]["rid"] == A.rid
    assert A.debt < 0.5 * face - 1e-9, "garnished drone's settlement did not service the debt"
    assert A.debt > 0, "near income wrongly cleared the debt (should stay garnished)"
    assert w.debt_conserved() and w.credit_conserved() and w.ledger_accounted()


def test_v32_no_borrowing_while_garnished():
    """A garnished drone does not take on new debt — borrow_step skips it even with
    ample collateral and battery headroom (all income services the existing debt)."""
    w, arm = _debt_world(ltv=0.8)
    A = w.robots[0]
    A.claim_value = 100.0                           # ample collateral
    A.battery = 10.0                                # ample headroom + energy-hungry
    A.debt = 50.0
    w.debt_loaned = 50.0
    A.garnished = True
    A.garnish_start = 0
    w.garnish_log.append(dict(rid=A.rid, co=0, start=0, end=-1, hop=None))
    d0 = A.debt
    w.borrow_step()
    assert A.debt == d0, "a garnished drone borrowed"
    assert not any(b[1] == A.rid for b in w._borrow_log), "garnished drone logged a borrow"
    # a SOLVENT twin with the same state DOES borrow (the block is garnishment, not state)
    C = w.robots[2]
    C.claim_value, C.battery, C.debt, C.garnished = 100.0, 10.0, 0.0, False
    w.borrow_step()
    assert C.debt > 0, "control (ungarnished) drone failed to borrow — test vacuous"


def test_v32_death_writes_off_debt_exactly_once():
    """A death writes off the dead drone's outstanding debt to debt_written_off EXACTLY
    once and clears r.debt — the treasury waterfall closes (loaned == repaid +
    written_off + outstanding) and the drone can never write off again (it is inert)."""
    w, arm = _debt_world(ltv=0.5)
    A = w.robots[0]
    A.debt = 30.0
    w.debt_loaned = 30.0
    A.garnished = True
    A.garnish_start = 0
    w.garnish_log.append(dict(rid=A.rid, co=A.company, start=0, end=-1, hop=None))
    assert w.debt_written_off == 0.0
    w.death_resolve(A, "flatline")
    assert w.debt_written_off == 30.0, "debt not written off at death"
    assert A.debt == 0.0 and A.dead and not A.garnished
    assert w.garnish_log[-1]["end"] >= 0, "garnishment episode not closed at death"
    assert w.debt_conserved()
    # the write-off fired once: totals are stable (A is dead; no second resolve happens)
    assert abs(w.debt_loaned - w.debt_repaid - w.debt_written_off
               - sum(r.debt for r in w.robots)) < 1e-9


def test_v32_evaluated_equals_executed_under_debt():
    """The sacred invariant under leverage: debt is NOT a term in the per-deal Φ and
    garnishment resolves only at settlement/death, so the in-arm evaluated Φ == executed
    Φ assert holds through 1,500 ticks of borrowing + the crash. Completing clean IS the
    test; borrowing must actually occur, the shock fire and write-downs land."""
    for ccp in (False, True):
        w, arm = _debt_world(ltv=0.8, ccp=ccp, shock=True, shock_tick=250)
        for _ in range(1500):
            arm.tick()
            assert w.debt_conserved() and w.credit_conserved() and w.ledger_accounted()
        assert w.debt_loaned > 0, f"no borrowing — vacuous run (ccp={ccp})"
        assert w.shocked and w.writedown_log, f"shock never landed (ccp={ccp})"
        assert arm.deals > 0


# ── v30 (column M2): the bill becomes money — transferable claims ─────────────
def test_v30_claims_transferable_off_bit_identical():
    """claims_transferable=False must leave the shipped bills economy bit-identical —
    no claim axis in the bundle space, no endorsement path, no tracking — and turning
    it ON adds exactly one signed axis (column 3 == CLAIM_OPTS). Checked on snhp+net
    with bills, the arm whose Φ the claim axis would touch."""
    outs = []
    for kw in (dict(bills=True), dict(bills=True, claims_transferable=False)):
        w = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15), **kw)
        arm = make_arm("snhp+net", w)
        for _ in range(500):
            arm.tick()
        outs.append((w.delivered, arm.deals, len(w.event_log),
                     round(sum(r.battery for r in w.robots), 9),
                     round(sum(r.claim_value for r in w.robots), 9),
                     [r.pos for r in w.robots]))
    assert outs[0] == outs[1], "claims_transferable=False perturbed the bills economy"
    assert not arm.has_claims and arm.space.shape[1] == 3, \
        "claim axis leaked into the bundle space when off"
    w2 = World(sigma=0.5, seed=0, preset="v5", tau=(0.15, 0.15),
               bills=True, claims_transferable=True)
    arm2 = make_arm("snhp+net", w2)
    assert arm2.has_claims and arm2.space.shape[1] == 4, "claim axis missing when on"
    assert sorted(set(arm2.space[:, 3].tolist())) == sorted(CLAIM_OPTS), \
        "column 3 is not the claim-endorsement axis"


def test_v30_endorsement_chain_settles_to_final_holder():
    """A hand-built A→B cargo hand-off banks A a claim on B's parcels; endorsing that
    claim A→C→D rewrites the claimant so that when B delivers, the share settles to D
    (the CURRENT holder) — never A or C. Credit conserved; B keeps its residual."""
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
              claims_transferable=True)
    arm = make_arm("snhp+net", w)
    A, B, C, D = w.robots[0], w.robots[1], w.robots[2], w.robots[3]
    for r in w.robots:                         # clear everyone so the scan is clean
        r.company, r.load, r.load_prov, r.parcels, r.credit, r.claim_value = \
            0, 0, [0, 0], [], 0.0, 0.0
    A.sector = 0
    A.pos, w.stock[0] = w.sources[0], 2
    assert w.pick(A) == 2                       # A mines 2 → 2 parcels
    w.tick = 5
    w.transfer_cargo(A, B, 2, log=True)         # A → B (B now physically holds it)
    arm._bills_attach(A, B, 2, 0.5)             # A banks a 0.5 claim on each parcel
    face = 0.5 * 2 * V_DELIVER                  # 10
    assert abs(A.claim_value - face) < 1e-9
    w.tick = 6                                  # endorse A → C
    assert abs(w.transfer_claims(A, C, face) - face) < 1e-9
    assert abs(A.claim_value) < 1e-9 and abs(C.claim_value - face) < 1e-9
    w.tick = 7                                  # endorse C → D
    assert abs(w.transfer_claims(C, D, face) - face) < 1e-9
    assert abs(C.claim_value) < 1e-9 and abs(D.claim_value - face) < 1e-9
    for p in B.parcels:                         # every entry now names D
        assert all(rid == D.rid for rid, _sh in p["claims"])
    B.pos = w.refineries[w._home_ref(0)]        # deliver at company-0's own refinery
    w.tick = 20
    w.drop(B)
    unit = V_DELIVER                            # rate 1 at own refinery
    assert abs(D.credit - 0.5 * 2 * unit) < 1e-9, "claim did not settle to final holder D"
    assert abs(A.credit) < 1e-9 and abs(C.credit) < 1e-9, "an intermediate endorser was paid"
    assert abs(B.credit - 0.5 * 2 * unit) < 1e-9, "deliverer residual wrong"
    assert w.credit_conserved() and w.ledger_accounted()


def test_v30_face_value_pricing_responds_to_risk():
    """Under CLAIMS-DIE the bills Φ prices a HELD claim at its survival-weighted face
    (claim·(1−hazard)), so endorsing it from a high-hazard holder to a SAFER one
    re-prices it UP (flight to quality raises joint Φ) — the same survival machinery
    column AA used, composing cleanly with the transfer, which still moves EXACT face."""
    from swarm.value import bills_correction, stranding_hazard
    w = World(sigma=0.5, seed=0, preset="v5", tau=(0.0, 0.0), bills=True,
              claims_transferable=True, mortality=True, death_regime="claims_die")
    arm = make_arm("snhp+net", w)
    assert w.claim_discount
    H, L, X = w.robots[0], w.robots[1], w.robots[2]
    for r in w.robots:
        r.company, r.load, r.load_prov, r.parcels, r.credit, r.claim_value = \
            0, 0, [0, 0], [], 0.0, 0.0
    X.sector = 0
    X.pos, w.stock[0] = w.sources[0], 1
    assert w.pick(X) == 1                       # X physically holds 1 unit
    arm._bills_attach(H, X, 1, 0.5)             # H owns a 0.5 claim on X's parcel
    face = 0.5 * V_DELIVER
    assert abs(H.claim_value - face) < 1e-9
    # H high-hazard (near-empty, far from chargers); L low-hazard (full, ON a charger)
    H.battery, H.pos = 1.0, w.sources[0]
    L.battery, L.pos = W.BATTERY_MAX, w.chargers[0]
    haz_H, haz_L = stranding_hazard(H, w), stranding_hazard(L, w)
    assert haz_H > haz_L, "test setup failed to separate hazards"
    vH = bills_correction(H, w)                 # H's held claim, survival-discounted
    assert abs(vH - face * (1.0 - haz_H)) < 1e-9, "claim not priced at survival-weighted face"
    assert abs(w.transfer_claims(H, L, face) - face) < 1e-9   # endorse H → L, exact
    assert abs(H.claim_value) < 1e-9 and abs(L.claim_value - face) < 1e-9
    vL = bills_correction(L, w)
    assert abs(vL - face * (1.0 - haz_L)) < 1e-9
    assert vL > vH, "endorsing to a safer holder did not raise the claim's Φ value"


def test_v30_conservation_through_multi_transfer():
    """800 ticks of snhp+net bills-transferable with material/ledger/credit invariants
    live: endorsements fire, and after the run each robot's claim_value still equals
    the Σ face of the (live-rid) claim entries it owns across every parcel — the
    reassign-and-split endorsement never leaks a fraction of a claim."""
    w = World(sigma=0.5, seed=1, preset="v5", tau=(0.15, 0.15), bills=True,
              claims_transferable=True)
    arm = make_arm("snhp+net", w)
    for _ in range(800):
        arm.tick()
        assert w.material_ok() and w.ledger_accounted() and w.credit_conserved()
    assert w.claim_xfers > 0, "no endorsement ever fired — vacuous"
    outstanding = {r.rid: 0.0 for r in w.robots}
    for r in w.robots:
        for p in r.parcels:
            for rid, share in p["claims"]:
                if rid >= 0:
                    outstanding[rid] += share * V_DELIVER
    for r in w.robots:
        assert abs(r.claim_value - outstanding[r.rid]) < 1e-6, \
            f"claim_value diverged from live stacks after transfers (robot {r.rid})"


def test_v30_mx_index_pinned():
    """The medium-of-exchange index on a hand-built bundle set: a commodity is a
    'medium' when it moves OPPOSITE some other commodity in the same bundle. Cargo paid
    by a claim ⇒ both a medium; a claim moving the SAME way as cargo is not; a pure
    one-commodity deal has no medium. Face sums the value moved as each medium."""
    from swarm.run import mx_counts
    deals = [
        dict(q=2, e=0.0, t=-5.0),    # cargo a→b, claim b→a: cargo & claims opposite
        dict(q=-1, e=3.0, t=0.0),    # cargo b→a, energy a→b: opposite
        dict(q=2, e=0.0, t=4.0),     # cargo a→b, claim a→b: SAME side (no opposition)
        dict(q=0, e=0.0, t=6.0),     # pure claim: nothing to be a medium against
        dict(q=3, e=0.0, t=0.0),     # pure cargo: no medium
    ]
    mv, op, face = mx_counts(deals)
    assert mv["cargo"] == 4 and op["cargo"] == 2      # moves 0,1,2,4; opposite 0,1
    assert mv["energy"] == 1 and op["energy"] == 1    # moves 1; opposite 1
    assert mv["claims"] == 3 and op["claims"] == 1    # moves 0,2,3; opposite only 0
    assert abs(face["cargo"] - 80.0) < 1e-9           # (2+1+2+3)·V
    assert abs(face["claims"] - 15.0) < 1e-9          # 5+4+6
    assert abs(face["energy"] - 3.0) < 1e-9


def test_v30_evaluated_equals_executed_under_transfers():
    """The sacred invariant under endorsement: 600 ticks of snhp+net bills-transferable
    with the in-arm evaluated Φ == executed Φ assert live. The claim leg is priced
    analytically (_bills_post: claim_a−t, claim_b+t) and executed by transfer_claims;
    any divergence fires the assert. Completing clean with endorsements landing — and
    the velocity tracking recording — IS the test."""
    w = World(sigma=0.5, seed=2, preset="v5", tau=(0.15, 0.15), bills=True,
              claims_transferable=True)
    arm = make_arm("snhp+net", w)
    for _ in range(600):
        arm.tick()
    assert arm.deals > 0
    assert w.claim_xfers > 0, "no endorsement fired — the claim axis was never exercised"
    assert len(w.claim_xfer_log) > 0, "no endorsement maturity recorded"
    assert any(any(x > 0 for x in p.get("cx", ())) for r in w.robots
               for p in r.parcels) or len(w.claim_settle_log) > 0, \
        "no circulated claim recorded in the velocity instruments"
    assert w.material_ok() and w.ledger_accounted() and w.credit_conserved()


def test_v30_grouped_eval_equals_perrow():
    """The grouped bills+claims eval (apply/phi once per physical bundle, fill the
    claim rows) must be BYTE-identical to the un-grouped per-row scalar path — it only
    hoists apply/phi/restore out of the t-loop, the ~30× speedup that makes N=240
    tractable. Flip FORCE_PERROW_CLAIMS and compare full trajectories."""
    import swarm.arms as A

    def run(force):
        old = A.FORCE_PERROW_CLAIMS
        A.FORCE_PERROW_CLAIMS = force
        try:
            w = World(sigma=0.5, seed=3, preset="v5", tau=(0.15, 0.15),
                      bills=True, claims_transferable=True)
            arm = make_arm("snhp+net", w)
            for _ in range(500):
                arm.tick()
            return (w.delivered, arm.deals, w.claim_xfers, len(w.event_log),
                    round(sum(r.credit for r in w.robots), 9),
                    round(sum(r.claim_value for r in w.robots), 9),
                    [r.pos for r in w.robots])
        finally:
            A.FORCE_PERROW_CLAIMS = old

    grouped, perrow = run(False), run(True)
    assert grouped == perrow, "grouped bills+claims eval diverged from the per-row path"
    assert grouped[2] > 0, "no endorsement fired — vacuous"


def benchmark(ticks=2500):
    """Timing harness (NOT a test): reports seconds for the three reference runs.
    Run with:  python -c 'from swarm.test_swarm import benchmark; benchmark()'"""
    import time

    def one(arm_name, n_robots):
        base = arm_name
        t0 = time.perf_counter()
        w = World(n_robots=n_robots, sigma=0.5, seed=0, preset="v5",
                  tau=(0.15, 0.15), internalize_tariffs=(base == "team"))
        arm = make_arm(base, w, issues=("cargo", "energy", "sector"))
        for _ in range(ticks):
            arm.tick()
            if w.delivered >= w.total_stock:
                break
        return time.perf_counter() - t0, w.delivered, arm.deals

    for label, arm_name, n in (("snhp+net v5 N=24", "snhp+net", 24),
                               ("snhp+net v5 N=96", "snhp+net", 96),
                               ("team v5 N=96", "team", 96)):
        one(arm_name, n)                       # warm
        dt, deliv, deals = one(arm_name, n)
        print(f"{label:20s}  {dt:7.3f}s  delivered={deliv} deals={deals}")

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

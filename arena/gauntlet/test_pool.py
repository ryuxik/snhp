"""Pool-protocol tests (PREREG-pool.md) — all offline, deterministic seats.
Covers: HARDBALL accept threshold + own-best proposals; CONCEDER concession
schedule + mid-game and endgame accept rules; match-record determinism;
permutation pairing correctness (by key, not position) with a hand-checked
p-value direction; and the experiment's refusal to run without the
registration file."""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from arena.gauntlet.agents import BATNA, SeatView
from arena.gauntlet.pool import (
    CONCEDER_ACCEPT, CONCEDER_STEP, HARDBALL_ACCEPT, ConcederSeat,
    HardballSeat, _own_best_package, _package_utility, run_pool_match,
    make_pool_seat,
)
from arena.gauntlet.pool_experiment import (
    paired_diffs, primary_stat, require_prereg,
)
from arena.gauntlet.protocol import DEADLINE, gen_gauntlet_scenarios


# ── a hand-computable two-issue frame ───────────────────────────────────────
# own utilities per issue [1.0, 0.5, 0.0], weights 0.5/0.5:
#   package utilities are k/4 for k in 0..4 -> {0, .25, .5, .75, 1.0}
def _view(turn=0, opp_offers=(), deadline=DEADLINE):
    issues = [
        {"name": "a", "options": ["a0", "a1", "a2"],
         "my_utility": [1.0, 0.5, 0.0], "their_utility": [0.0, 0.5, 1.0]},
        {"name": "b", "options": ["b0", "b1", "b2"],
         "my_utility": [1.0, 0.5, 0.0], "their_utility": [0.0, 0.5, 1.0]},
    ]
    return SeatView(role="seller", issues=issues,
                    weights={"a": 0.5, "b": 0.5},
                    my_offers=[], opp_offers=list(opp_offers),
                    turn=turn, deadline=deadline)


def _pkg(u_a, u_b):
    """Package with per-issue own utilities (u_a, u_b) via the option map."""
    m = {1.0: 0, 0.5: 1, 0.0: 2}
    return {"a": f"a{m[u_a]}", "b": f"b{m[u_b]}"}


OWN_BEST = {"a": "a0", "b": "b0"}          # utility 1.0


# ── HARDBALL ────────────────────────────────────────────────────────────────
def test_hardball_always_proposes_own_best():
    v = _view(turn=0)
    act = HardballSeat().act(v)
    assert act.kind == "offer" and act.package == OWN_BEST
    assert _package_utility(v, act.package) == pytest.approx(1.0)
    # still own-best later in the game, regardless of pressure
    v_late = _view(turn=DEADLINE - 1, opp_offers=[_pkg(0.5, 0.5)])
    act2 = HardballSeat().act(v_late)
    assert act2.kind == "offer" and act2.package == OWN_BEST


def test_hardball_accept_threshold_honored():
    # 0.5 < 0.65 -> refuse (counter with own-best), even on the last turn
    below = _view(turn=DEADLINE - 1, opp_offers=[_pkg(0.5, 0.5)])
    act = HardballSeat().act(below)
    assert act.kind == "offer" and act.package == OWN_BEST
    # 0.75 >= 0.65 -> accept
    above = _view(turn=2, opp_offers=[_pkg(1.0, 0.5)])
    assert HardballSeat().act(above).kind == "accept"
    # exactly at the threshold: 0.65 utility is not constructible on this grid,
    # so check the boundary from both sides with weights that hit 0.65 exactly
    v = _view(turn=2, opp_offers=[_pkg(1.0, 0.5)])
    v.weights = {"a": 0.3, "b": 0.7}           # u = 0.3*1 + 0.7*0.5 = 0.65
    assert HardballSeat().act(v).kind == "accept"
    v.weights = {"a": 0.29, "b": 0.71}         # u = 0.645 < 0.65
    assert HardballSeat().act(v).kind == "offer"


def test_hardball_never_walks():
    for turn in range(DEADLINE):
        v = _view(turn=turn, opp_offers=[_pkg(0.0, 0.0)])
        assert HardballSeat().act(v).kind != "walk"


# ── CONCEDER ────────────────────────────────────────────────────────────────
def test_conceder_concession_schedule():
    """k-th own turn targets own-best - 0.15k; on the 0.25-grid the nearest
    feasible utilities are 1.0, 0.85->0.75, 0.70->0.75, 0.55->0.5 ..."""
    seat = ConcederSeat()
    expected = {0: 1.0, 2: 0.75, 4: 0.75, 6: 0.5}   # turn -> proposal utility
    for turn, want in expected.items():
        v = _view(turn=turn)
        act = seat.act(v)
        assert act.kind == "offer"
        assert _package_utility(v, act.package) == pytest.approx(want), (
            f"turn {turn}: target {1.0 - CONCEDER_STEP * (turn // 2)}")
    # the schedule is monotone non-increasing over own turns
    us = [_package_utility(_view(turn=t), seat.act(_view(turn=t)).package)
          for t in (0, 2, 4, 6)]
    assert all(a >= b for a, b in zip(us, us[1:]))


def test_conceder_accept_rules():
    seat = ConcederSeat()
    # mid-game: 0.5 >= 0.45 -> accept
    assert seat.act(_view(turn=2, opp_offers=[_pkg(0.5, 0.5)])).kind == "accept"
    # mid-game: 0.25 < 0.45 -> refuse
    assert seat.act(_view(turn=2, opp_offers=[_pkg(0.5, 0.0)])).kind == "offer"
    # endgame (last two turns): 0.5 >= BATNA (0.30) -> accept even though < 0.45
    v = _view(turn=DEADLINE - 2, opp_offers=[_pkg(0.5, 0.0)])
    v.weights = {"a": 0.8, "b": 0.2}          # u = 0.8*0.5 + 0.2*0 = 0.40
    assert 0.30 <= _package_utility(v, v.opp_offers[-1]) < CONCEDER_ACCEPT
    assert seat.act(v).kind == "accept"
    # endgame: 0.25 < BATNA -> refuse (counter instead)
    v2 = _view(turn=DEADLINE - 1, opp_offers=[_pkg(0.5, 0.0)])
    assert _package_utility(v2, v2.opp_offers[-1]) < BATNA
    assert seat.act(v2).kind == "offer"
    # just before the endgame the BATNA fallback must NOT apply
    v3 = _view(turn=DEADLINE - 3, opp_offers=[_pkg(0.5, 0.0)])
    v3.weights = {"a": 0.8, "b": 0.2}         # u = 0.40, >= BATNA but < 0.45
    assert seat.act(v3).kind == "offer"


def test_own_best_is_package_space_argmax():
    v = _view()
    assert _own_best_package(v) == OWN_BEST
    # asymmetric utilities: argmax picks per-issue best under the true weights
    v.issues[0]["my_utility"] = [0.2, 0.9, 0.1]
    assert _own_best_package(v) == {"a": "a1", "b": "b0"}


# ── determinism ─────────────────────────────────────────────────────────────
def test_pool_match_determinism():
    """Same (scenario, seed) -> byte-identical match records, engine candidate
    included (its per-match seed is the only RNG anywhere in a pool match)."""
    from arena.gauntlet.agents import EngineSeat
    sc, w_s, w_b = gen_gauntlet_scenarios(2, 123)[0]
    for cp in ("naive", "hardball", "conceder"):
        r1 = run_pool_match(EngineSeat(777), make_pool_seat(cp), sc, w_s, w_b,
                            role="seller", condition=f"pool-{cp}", scenario_id=0)
        r2 = run_pool_match(EngineSeat(777), make_pool_seat(cp), sc, w_s, w_b,
                            role="seller", condition=f"pool-{cp}", scenario_id=0)
        assert r1.to_dict() == r2.to_dict()


# ── permutation pairing on a synthetic fixture ──────────────────────────────
def _recs(us: dict) -> list[dict]:
    return [{"scenario_id": sid, "role": role, "counterparty": cp,
             "u_candidate": u}
            for (sid, role, cp), u in us.items()]


def test_paired_diffs_pairs_by_key_not_position():
    keys = [(s, r, c) for s in range(5) for r in ("seller", "buyer")
            for c in ("naive", "hardball")]
    a = {k: 0.6 + 0.01 * i for i, k in enumerate(keys)}
    b = {k: a[k] - 0.5 for k in keys}          # b = a - 0.5 on every key
    ra, rb = _recs(a), _recs(b)
    rb_shuffled = list(reversed(rb))           # different order on purpose
    d1 = paired_diffs(ra, rb)
    d2 = paired_diffs(ra, rb_shuffled)
    assert np.allclose(d1, d2) and np.allclose(d1, 0.5)
    # a key-set mismatch fails closed, never a silent partial pairing
    with pytest.raises(ValueError):
        paired_diffs(ra, rb[:-1])


def test_permutation_direction_hand_checked():
    """All 20 diffs = +0.5: only the 2-in-2^20 all-same-sign flips reach
    |mean| 0.5, so p ~ 1/10001 << 0.01 and 'passes' fires; a zero-mean
    alternating fixture gives p = 1.0 and cannot pass."""
    keys = [(s, r, "naive") for s in range(10) for r in ("seller", "buyer")]
    eng = _recs({k: 0.8 for k in keys})
    nai = _recs({k: 0.3 for k in keys})
    s = primary_stat(eng, nai, seed=20260709)
    assert s["delta"] == pytest.approx(0.5)
    assert s["p_value"] < 0.01 and s["passes"]
    # alternating +/-0.25 -> mean 0 -> every permutation ties or beats it
    alt = {k: (0.55 if i % 2 else 0.05) for i, k in enumerate(keys)}
    nai2 = _recs({k: 0.3 for k in keys})
    s2 = primary_stat(_recs(alt), nai2, seed=20260709)
    assert s2["delta"] == pytest.approx(0.0)
    assert s2["p_value"] == pytest.approx(1.0)
    assert not s2["passes"]


# ── the registration gate ───────────────────────────────────────────────────
def test_experiment_refuses_without_prereg(tmp_path):
    with pytest.raises(SystemExit):
        require_prereg(tmp_path / "PREREG-pool.md")     # missing file
    # the real registration exists and passes the gate
    require_prereg()
    from arena.gauntlet.pool_experiment import run_experiment
    with pytest.raises(SystemExit):
        run_experiment(1, prereg=tmp_path / "PREREG-pool.md",
                       out_dir=tmp_path, verbose=False)


# ── Amendment 1: the reference arm ──────────────────────────────────────────
def test_reference_arm_determinism_and_labeling():
    """The SNHP-reference arm is deterministic and every record is labeled with
    the reference counterparty (so certify can keep it out of the pool)."""
    from arena.gauntlet.pool_experiment import REFERENCE_CP, run_reference
    a = run_reference("engine", 12345, n=2)
    b = run_reference("engine", 12345, n=2)
    assert a == b                                   # byte-identical records
    assert len(a) == 2 * 2                          # 2 scenarios x 2 roles
    assert all(r["counterparty"] == REFERENCE_CP for r in a)
    assert all(r["condition"] == f"pool-{REFERENCE_CP}" for r in a)
    # a different candidate produces different play on the same seeds
    c = run_reference("naive", 12345, n=2)
    assert [r["u_candidate"] for r in c] != [r["u_candidate"] for r in a]


def test_reference_arm_statistic_matches_primary_procedure():
    """The reference tier uses the SAME own-utility pairing + permutation as the
    primary — the difference is that it is reported separately, not that it is
    measured differently."""
    from arena.gauntlet.pool_experiment import run_reference
    eng = run_reference("engine", 12345, n=3)
    nai = run_reference("naive", 12345, n=3)
    s = primary_stat(eng, nai, seed=12345)
    assert s["n_pairs"] == 3 * 2
    assert s["p_value"] == primary_stat(eng, nai, seed=12345)["p_value"]
    # pairing is by key, and the two arms cover the identical key set
    d = paired_diffs(eng, nai)
    assert len(d) == 6


def test_reference_tier_excluded_from_primary_in_experiment(tmp_path):
    """The experiment's verdict must be computed from the frozen three ONLY:
    the reference records live in a separate structure and the reported
    n_pairs stays 3-member sized."""
    from arena.gauntlet.pool_experiment import run_experiment
    res = run_experiment(2, out_dir=tmp_path, verbose=False)
    for s in res["per_set"].values():
        assert s["n_pairs"] == 2 * 2 * 3            # 3 pool members, no 4th
    for s in res["reference_per_set"].values():
        assert s["n_pairs"] == 2 * 2                # reference is its own arm
    assert res["prediction_outcome"] in ("held", "contradicted")
    summary = json.loads((tmp_path / "reference-tier.json").read_text())
    assert summary["pooled_into_primary"] is False
    assert summary["counterparty"] == "snhp-engine"
    body = (tmp_path / "POOL-RESULTS.md").read_text()
    # the prediction is stated BEFORE the outcome in the report
    assert body.index("registered prediction") < body.index("**The outcome:**")


def test_experiment_smoke_tiny(tmp_path):
    """A 2-scenario end-to-end run: mechanical verdict, report + raw records
    written. (The registered run is n=60; this only checks the machinery.)"""
    from arena.gauntlet.pool_experiment import run_experiment
    res = run_experiment(2, out_dir=tmp_path, verbose=False)
    assert res["verdict"] in ("SURVIVE", "KILL-POOL")
    assert set(res["per_set"]) == {"PUBLIC", "HELD-OUT-NEW"}
    for s in res["per_set"].values():
        assert s["n_pairs"] == 2 * 2 * 3
    assert (tmp_path / "POOL-RESULTS.md").exists()
    assert (tmp_path / "pool-matches.json").exists()

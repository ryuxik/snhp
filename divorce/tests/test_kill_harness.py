"""Invariants for the divorce kill harness — determinism, IR, budget, zero-sum."""
import json

import numpy as np
import pytest

from divorce import arms, personas
from divorce.kill_harness import _py, evaluate, run_population


@pytest.fixture(scope="module")
def pair():
    rng = np.random.default_rng([11, 0])
    return personas.sample_pair(rng, "scorched_earth", "sentimental_hoarder")


def test_determinism_same_seed_same_report():
    a = json.dumps(_py(run_population(4, seed=3)), sort_keys=True)
    b = json.dumps(_py(run_population(4, seed=3)), sort_keys=True)
    assert a == b


def test_utility_monotone_in_own_share(pair):
    p = pair["a"]
    lo = p.utility({a["name"]: 0.25 for a in personas.ASSETS})
    hi = p.utility({a["name"]: 0.75 for a in personas.ASSETS})
    assert hi > lo


def test_qualified_pairs_meet_contested_criterion(pair):
    if pair["qualified"]:
        assert len(pair["contested"]) >= 2
        for a in pair["contested"]:
            assert a in personas.INDIVISIBLES


def test_arm_o_settlement_clears_both_batnas():
    for i in range(6):
        rng = np.random.default_rng([21, i])
        pr = personas.sample_pair(rng, "spreadsheet", "ledger")
        res = arms.run_arm_o(pr["a"], pr["b"])
        if res["settled"]:
            assert res["ir_a"] and res["ir_b"]
            assert res["joint_surplus"] > 0


def test_arm_i_budget_and_zero_sum(pair):
    rng = np.random.default_rng([31, 0])
    res = arms.run_arm_i(pair["a"], pair["b"], rng)
    assert sum(res["per_item_exchanges"].values()) <= arms.EXCHANGE_BUDGET
    assert abs(res["net_recv"]["A"] + res["net_recv"]["B"]) < 1e-9
    assert 0.0 <= res["settled_fraction"] <= 1.0


def test_evaluate_smoke():
    pop = run_population(6, seed=5)
    summary = evaluate(pop)
    assert "kills" in summary or "error" in summary


# ── step 2: elicitation / ARM-B ─────────────────────────────────────────────

def test_answerer_table_is_independent_of_persona(pair):
    from divorce import elicit
    ans = elicit.make_answerer(pair["a"], uid=1)
    before = dict(ans.wtp)
    ans.wtp["dog"] *= 2
    assert pair["a"].values["dog"] != ans.wtp["dog"] or before["dog"] == 0


def test_arm_b_settled_implies_true_ir(pair):
    from divorce import elicit
    prior = elicit.build_asset_prior(n_cal=60)
    res = elicit.run_arm_b(pair["a"], pair["b"], prior, (99, 0))
    if res["settled"]:
        assert res["u_a"] >= pair["a"].walk_away
        assert res["u_b"] >= pair["b"].walk_away
    assert res["n_questions"] <= 2 * (elicit.Q_BUDGET + elicit.DRAFTS_MAX)


def test_arm_b_deterministic(pair):
    from divorce import elicit
    prior = elicit.build_asset_prior(n_cal=60)
    r1 = elicit.run_arm_b(pair["a"], pair["b"], prior, (42, 3))
    r2 = elicit.run_arm_b(pair["a"], pair["b"], prior, (42, 3))
    assert json.dumps(_py(r1), sort_keys=True) == json.dumps(_py(r2), sort_keys=True)

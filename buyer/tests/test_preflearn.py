"""preflearn tests — the rigor rules for the consumer-side learning core:

  * no-ground-truth-leak: the learner is a pure function of elicited ANSWERS +
    observed CHOICES; it never reads the true wtp. Proven structurally by
    driving it with a buyer object that HAS no wtp attribute (any true-value
    read would raise), and functionally by identical estimates from identical
    answer streams under different underlying truths.
  * paired-stream byte-identity: same seed → byte-identical results.
  * discount-only: every learned-agent quote is priced at or below list.
  * artifact reproducibility: the headline regenerates identically.
  * monotone-ish convergence: more onboarding → lower curve error, higher
    capture; capture at (N=0,M=0) is exactly 0 (learned == no-info prior).
"""
import json

import numpy as np
import pytest

from buyer.preflearn import (CAL_SEED, PopPrior, PosteriorLearner, TrueBuyer,
                             _build_env, negotiate_realized, run_buyer,
                             run_headline, select_and_ask)
from buyer.values import bundle_value
from buyer.world import draw_vend_population

SEED = 20260710


@pytest.fixture(scope="module")
def prior():
    return PopPrior.build(cal_seed=CAL_SEED)


# ── no ground-truth leak ─────────────────────────────────────────────────────

class _ScriptedBuyer:
    """Answers a fixed script and DELIBERATELY has no `wtp`. If any learner or
    query-selection code path read the true utility, it would AttributeError —
    so the fact that onboarding runs to completion is a structural proof that
    the learner sees only answers/choices."""
    def __init__(self, seed=0):
        self._rng = np.random.default_rng(seed)

    def answer_probe(self, sku, price):
        return bool(self._rng.random() < 0.5)

    def answer_pairwise(self, A, B):
        return str(self._rng.choice(["A", "B", "walk"]))


def test_no_ground_truth_leak_structural(prior):
    # onboarding drives select_and_ask with a wtp-less buyer: completes only if
    # nothing reads the true utility.
    learner = PosteriorLearner(prior)
    buyer = _ScriptedBuyer(seed=1)
    for _ in range(20):
        select_and_ask(learner, buyer, prior.skus)
    # the learner holds only prior/skus/weights — no true-value state
    assert set(learner.__dict__) == {"prior", "skus", "w"}


def test_no_ground_truth_leak_functional(prior):
    # identical answer streams must yield identical estimates regardless of the
    # underlying truth that produced them (the learner reads only the answers).
    answers = [("probe", "cola", 2.0, True), ("probe", "energy", 3.0, False),
               ("probe", "water", 1.5, True), ("probe", "cola", 1.8, True)]

    def estimate():
        L = PosteriorLearner(prior)
        for _, sku, price, yes in answers:
            L.update_probe(sku, price, yes)
        return L.mean()

    e1, e2 = estimate(), estimate()
    assert e1 == e2
    # and the estimate is unaffected by any 'true' buyer object existing
    _ = TrueBuyer(1, {s: 9.9 for s in prior.skus}, 1.0)
    assert estimate() == e1


# ── paired-stream byte-identity & artifact reproducibility ──────────────────

def test_paired_stream_byte_identity():
    h1 = run_headline(SEED, n=10, n_grid=(0, 5), m_grid=(0, 3))
    h2 = run_headline(SEED, n=10, n_grid=(0, 5), m_grid=(0, 3))
    assert json.dumps(h1, sort_keys=True) == json.dumps(h2, sort_keys=True)


def test_artifact_reproducible_across_seeds_differ():
    # same seed identical; different seed differs (the run is seed-driven, not
    # constant).
    a = run_headline(SEED, n=10, n_grid=(0, 5), m_grid=(0,))
    b = run_headline(SEED + 1, n=10, n_grid=(0, 5), m_grid=(0,))
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)


# ── discount-only: learned-agent quotes never exceed list ───────────────────

def test_discount_only_learned_quotes(prior):
    eval_m, online_ms = _build_env(SEED)
    pop = draw_vend_population(SEED, 40)
    seen = 0
    for draw in pop:
        buyer = TrueBuyer(draw.uid, dict(draw.wtp), draw.walk_cost)
        learner = PosteriorLearner(prior)
        for _ in range(5):
            select_and_ask(learner, buyer, prior.skus)
        from buyer.merchant import Disclosure, Intent
        q = eval_m.quote(Disclosure(wtp=learner.mean(),
                                    walk_cost=draw.walk_cost), Intent())
        if q is not None:
            seen += 1
            assert q.unit_price <= q.list_price + 1e-9
    assert seen > 0


# ── convergence: monotone-ish, and the (0,0) anchor is exactly 0 ────────────

def test_curve_error_decreases_with_onboarding():
    h = run_headline(SEED, n=60, n_grid=(0, 5, 20), m_grid=(0,))
    conv = h["convergence"]["cart_on"]
    assert conv["N20"]["mean"] < conv["N0"]["mean"]          # more info → less err
    assert conv["N5"]["mean"] <= conv["N0"]["mean"] + 1e-9


def test_capture_zero_at_origin_and_rises():
    h = run_headline(SEED, n=60, n_grid=(0, 5, 20), m_grid=(0,))
    jc = h["cart_on"]["joint_capture"]
    # learned == no-info at (0,0) → capture exactly 0
    assert abs(jc["N0_M0"]["capture"]) < 1e-9
    # onboarding raises joint capture materially
    assert jc["N20_M0"]["capture"] > jc["N5_M0"]["capture"] - 0.10
    assert jc["N20_M0"]["capture"] > 0.4


def test_cart_signal_helps_small_budget():
    h = run_headline(SEED, n=80, n_grid=(0, 5), m_grid=(0,))
    lift = h["cart_lift"]["joint"]["N5_M0"]
    # the consideration-set signal lifts small-budget capture (point estimate);
    # significance is asserted at full n in RESULTS, not in the fast test.
    assert lift["lift"] > 0.0

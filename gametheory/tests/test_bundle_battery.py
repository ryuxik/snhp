"""
P10 permanent battery for the multi-issue bundle tier.

Guards the three P10 fixes and the audit's core vindication, seed=0, no LLM:

  * SKYLINE vs BRUTE  — the Pareto filter + Nash selection matches a
    first-principles reference (the audit's t1; the CORE is untouched by P10 but
    the guard stays permanent).
  * G1 accept-floor   — negotiate_bundle never recommends `accept` below my_batna,
    and never rejects (`counter`) an offer that clears max(rec-0.02, my_batna).
  * G2 determinism    — advise_bundle(seed=...) is byte-stable across repeats, the
    seed is REAL (different seeds may differ), and rng=None reproduces the legacy
    global draw (additivity).
  * G3 time-blindness — rounds_left is inert off the final round; on the last round
    an in-floor standing offer is accepted, never a below-floor one.
  * SYMMETRY          — full-pipeline label swap mirrors the recommendation.

FAST by default (small n). The full 36k/40k audit versions carry `-m slow`.
"""
import sys

import numpy as np
import pytest

from gametheory.negotiation.bundle import negotiate_bundle, _norm01
from vend.advice import advise_bundle, AdviceInvariantError

# bundle.py's import side-effect (ensure_snhp_path) puts the snhp core on sys.path.
from nash_solver import filter_pareto_frontier, find_nash_bargaining_solution  # noqa: E402
from bayesian_agent import BayesianParticleFilter  # noqa: E402

NEG_INF = -np.inf


# ── first-principles references (copied from audit t1, NOT from nash_solver) ──
def _brute_pareto(ua, ub):
    n = len(ua)
    fin = [i for i in range(n) if ua[i] > NEG_INF and ub[i] > NEG_INF]
    keep = set()
    for i in fin:
        if not any(j != i and ua[j] >= ua[i] and ub[j] >= ub[i]
                   and (ua[j] > ua[i] or ub[j] > ub[i]) for j in fin):
            keep.add(i)
    return keep


def _brute_nash_value(ua, ub, da, db):
    best, args = -np.inf, set()
    for i in range(len(ua)):
        sa, sb = ua[i] - da, ub[i] - db
        if sa <= 0 or sb <= 0:
            continue
        p = sa * sb
        if p > best + 1e-12:
            best, args = p, {i}
        elif abs(p - best) <= 1e-12:
            args.add(i)
    return (None, set()) if best == -np.inf else (best, args)


_KINDS = ["float", "int_ties", "dup_points", "collinear", "collinear_tied",
          "all_equal", "one_col_const", "single", "with_neg_inf"]


def _gen_instance(rng, kind):
    n = int(rng.integers(1, 60))
    if kind == "float":
        return rng.random(n), rng.random(n)
    if kind == "int_ties":
        hi = int(rng.integers(2, 5))
        return rng.integers(0, hi, n).astype(float), rng.integers(0, hi, n).astype(float)
    if kind == "dup_points":
        base_a = rng.integers(0, 4, max(1, n // 3)).astype(float)
        base_b = rng.integers(0, 4, len(base_a)).astype(float)
        reps = rng.integers(1, 5, len(base_a))
        return np.repeat(base_a, reps), np.repeat(base_b, reps)
    if kind == "collinear":
        a = rng.random(n); return a, 1.0 - a
    if kind == "collinear_tied":
        a = rng.integers(0, 5, n).astype(float); return a, 4.0 - a
    if kind == "all_equal":
        return np.full(n, float(rng.random())), np.full(n, rng.random())
    if kind == "one_col_const":
        return np.full(n, float(rng.random())), rng.random(n)
    if kind == "single":
        return rng.random(1), rng.random(1)
    if kind == "with_neg_inf":
        a, b = rng.random(n), rng.random(n)
        a[rng.random(n) < 0.3] = NEG_INF
        if rng.random() < 0.5:
            b[rng.random(n) < 0.3] = NEG_INF
        return a, b
    raise ValueError(kind)


def _skyline_vs_brute(n_per):
    rng = np.random.default_rng(0)
    pareto_fail = nash_fail = 0
    for kind in _KINDS:
        for _ in range(n_per):
            ua, ub = _gen_instance(rng, kind)
            contracts = np.arange(len(ua)).reshape(-1, 1).astype(float)
            sk = set(int(i) for i in filter_pareto_frontier(contracts, ua, ub))
            if sk != _brute_pareto(ua, ub):
                pareto_fail += 1
            da, db = float(rng.random() * 0.6), float(rng.random() * 0.6)
            got = find_nash_bargaining_solution(
                filter_pareto_frontier(contracts, ua, ub), ua, ub, da, db,
                batna_b_inferred=True)
            bval, _ = _brute_nash_value(ua, ub, da, db)
            if bval is None:
                if got is not None:
                    nash_fail += 1
            elif got is None or abs((ua[got] - da) * (ub[got] - db) - bval) > 1e-9:
                nash_fail += 1
    return pareto_fail, nash_fail


# ── bundle random-instance generator (audit t2) ──────────────────────────────
def _build_random_issues(rng, n_issues):
    issues = []
    for k in range(n_issues):
        n_opt = int(rng.integers(2, 4))
        issues.append({
            "name": f"i{k}", "options": [f"o{j}" for j in range(n_opt)],
            "my_utility": rng.random(n_opt).tolist(),
            "their_utility": rng.random(n_opt).tolist()})
    return issues


def _my_util_of(issues, my_w, offer):
    tot = 0.0
    for i, iss in enumerate(issues):
        nu = _norm01(iss["my_utility"])
        tot += my_w[i] * nu[iss["options"].index(offer[iss["name"]])]
    return float(tot)


def _accept_floor_sweep(trials):
    """Both G1 clauses over a mixed-batna sweep. Returns (below_floor, in_floor_rejected)."""
    rng = np.random.default_rng(0)
    clause1 = clause2 = 0
    for t in range(trials):
        np.random.seed(t)
        n_issues = int(rng.integers(2, 4))
        issues = _build_random_issues(rng, n_issues)
        my_w = np.ones(n_issues) / n_issues
        latest = {iss["name"]: iss["options"][int(rng.integers(len(iss["options"])))]
                  for iss in issues}
        u_latest = _my_util_of(issues, my_w, latest)
        my_batna = float(np.clip(u_latest + rng.uniform(-0.15, 0.15), 0.0, 1.0))
        r = negotiate_bundle(issues=issues, their_offers=[latest], my_batna=my_batna,
                             their_batna_estimate=float(rng.random() * 0.5))
        if r["action"] == "accept" and u_latest < my_batna - 1e-9:
            clause1 += 1
        if r["action"] == "counter":
            thresh = max(r["my_utility"] - 0.02, my_batna)
            if u_latest >= thresh + 1e-9:
                clause2 += 1
    return clause1, clause2


def _endgame_sweep(trials):
    """G3: (inert_mismatch, over_accept, under_serve) over a mixed-batna sweep."""
    rng = np.random.default_rng(0)
    inert = over = under = 0
    for t in range(trials):
        np.random.seed(t)
        n_issues = int(rng.integers(2, 4))
        issues = _build_random_issues(rng, n_issues)
        my_w = np.ones(n_issues) / n_issues
        latest = {iss["name"]: iss["options"][int(rng.integers(len(iss["options"])))]
                  for iss in issues}
        u_latest = _my_util_of(issues, my_w, latest)
        my_batna = float(np.clip(u_latest + rng.uniform(-0.15, 0.15), 0.0, 1.0))
        kw = dict(issues=issues, their_offers=[latest], my_batna=my_batna,
                  their_batna_estimate=float(rng.random() * 0.5), seed=t)
        if negotiate_bundle(rounds_left=None, **kw) != negotiate_bundle(rounds_left=5, **kw):
            inert += 1
        r_one = negotiate_bundle(rounds_left=1, **kw)
        if r_one["action"] == "accept" and u_latest < my_batna - 1e-9:
            over += 1
        if u_latest >= my_batna and r_one["action"] != "accept":
            under += 1
    return inert, over, under


def _symmetry_sweep(trials):
    rng = np.random.default_rng(0)
    fails = 0
    for _ in range(trials):
        n_issues = int(rng.integers(2, 4))
        issues = _build_random_issues(rng, n_issues)
        ba, bb = float(rng.random() * 0.4), float(rng.random() * 0.4)
        r1 = negotiate_bundle(issues=issues, my_batna=ba, their_batna_estimate=bb)
        swapped = [{"name": i["name"], "options": i["options"],
                    "my_utility": i["their_utility"], "their_utility": i["my_utility"]}
                   for i in issues]
        r2 = negotiate_bundle(issues=swapped, my_batna=bb, their_batna_estimate=ba)
        p1, p2 = r1["recommended_offer"], r2["recommended_offer"]
        if (p1 is None) != (p2 is None):
            fails += 1
        elif p1 is not None and p1 != p2:
            fails += 1
    return fails


# The concrete P10 G3 probe: standing offer clears BATNA by +0.10 but is countered.
_PROBE_ISSUES = [
    {"name": "price", "options": ["lo", "mid", "hi"],
     "my_utility": [1.0, 0.6, 0.0], "their_utility": [0.0, 0.5, 1.0]},
    {"name": "term", "options": ["1yr", "2yr", "3yr"],
     "my_utility": [0.0, 0.5, 1.0], "their_utility": [1.0, 0.4, 0.0]},
    {"name": "sla", "options": ["basic", "gold"],
     "my_utility": [0.0, 1.0], "their_utility": [1.0, 0.0]},
]
_PROBE_LATEST = {"price": "hi", "term": "2yr", "sla": "gold"}


# ═══════════════════════════════ FAST ═══════════════════════════════════════
def test_skyline_vs_brute_fast():
    pareto_fail, nash_fail = _skyline_vs_brute(n_per=40)   # 360 instances
    assert pareto_fail == 0 and nash_fail == 0


def test_g1_accept_floor_fast():
    clause1, clause2 = _accept_floor_sweep(trials=2000)
    assert clause1 == 0, f"{clause1} accepts below BATNA"
    assert clause2 == 0, f"{clause2} in-floor offers wrongly countered"


def test_g2_determinism_fast():
    issues = _PROBE_ISSUES
    offers = [{"price": "hi", "term": "1yr", "sla": "basic"},
              {"price": "mid", "term": "1yr", "sla": "basic"}]
    seen = set()
    for _ in range(20):
        a = advise_bundle(category="supply", issues=issues, their_offers=offers,
                          my_batna=0.35, their_batna_estimate=0.40, seed=0)
        e = a.engine
        seen.add((tuple(sorted(e["recommended_offer"].items())),
                  tuple(sorted(e["inferred_their_priorities"].items())),
                  e["my_utility"], a.context_hash))
    assert len(seen) == 1, f"non-deterministic: {len(seen)} distinct outputs"


def test_g2_seed_is_real_and_additive():
    issues = _PROBE_ISSUES
    offers = [{"price": "hi", "term": "1yr", "sla": "basic"},
              {"price": "mid", "term": "1yr", "sla": "basic"}]
    r0 = negotiate_bundle(issues=issues, their_offers=offers, seed=0)
    r0b = negotiate_bundle(issues=issues, their_offers=offers, seed=0)
    assert r0 == r0b                                   # same seed => identical
    # rng=None reproduces the legacy global np.random.rand draw byte-for-byte.
    np.random.seed(999)
    bf = BayesianParticleFilter(num_variables=3, num_particles=400, rng=None)
    np.random.seed(999)
    raw = np.random.rand(400, 3)
    assert np.array_equal(bf.particles, raw / raw.sum(axis=1, keepdims=True))


def test_g3_probe_flips_only_on_final_round():
    for rl in (None, 9, 5, 2):
        r = negotiate_bundle(issues=_PROBE_ISSUES, their_offers=[_PROBE_LATEST],
                             my_batna=0.40, their_batna_estimate=0.40, seed=0, rounds_left=rl)
        assert r["action"] == "counter", f"rounds_left={rl} should still counter"
    r1 = negotiate_bundle(issues=_PROBE_ISSUES, their_offers=[_PROBE_LATEST],
                          my_batna=0.40, their_batna_estimate=0.40, seed=0, rounds_left=1)
    assert r1["action"] == "accept"
    assert abs(r1["my_utility"] - 0.5) < 1e-9   # the ACCEPTED offer's utility, not the counter's


def test_g3_endgame_never_accepts_below_floor():
    # last round, standing offer strictly below BATNA -> must NOT accept.
    latest = {"price": "hi", "term": "2yr", "sla": "gold"}   # u_latest = 0.5
    r = negotiate_bundle(issues=_PROBE_ISSUES, their_offers=[latest],
                         my_batna=0.60, their_batna_estimate=0.40, seed=0, rounds_left=1)
    assert r["action"] != "accept"


def test_g3_inert_and_sanity_fast():
    inert, over, under = _endgame_sweep(trials=2000)
    assert inert == 0, f"rounds_left>=2 perturbed {inert} instances"
    assert over == 0, f"endgame manufactured {over} below-floor accepts"
    assert under == 0, f"{under} in-floor final-round offers left un-accepted"


def test_symmetry_fast():
    assert _symmetry_sweep(trials=400) == 0


def test_advice_invariant_fires_on_below_floor_accept():
    # Fix 1 surfaces the ACCEPTED offer's utility on accepts, so the advice
    # invariant now checks the quantity that must clear the floor.
    import gametheory.negotiation.bundle as bmod
    real = bmod.negotiate_bundle

    def fake(**kw):
        return {"action": "accept", "recommended_offer": {"price": "hi"},
                "message": "x", "my_utility": kw["my_batna"] - 0.05,
                "their_expected_utility": 0.6, "inferred_their_priorities": {"price": 1.0},
                "trade_logic": "x", "fit": {"score": "poor", "reason": "y"},
                "confidence": 0.5, "acceptance_probability": 0.9}
    issues = [{"name": "price", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
              {"name": "sla", "options": ["a", "b"], "my_utility": [0, 1], "their_utility": [1, 0]}]
    bmod.negotiate_bundle = fake
    try:
        with pytest.raises(AdviceInvariantError):
            advise_bundle(category="supply", issues=issues, my_batna=0.50, seed=0)
    finally:
        bmod.negotiate_bundle = real


# ═══════════════════════════════ SLOW ═══════════════════════════════════════
@pytest.mark.slow
def test_skyline_vs_brute_full():
    pareto_fail, nash_fail = _skyline_vs_brute(n_per=4000)   # 36k instances
    assert pareto_fail == 0 and nash_fail == 0


@pytest.mark.slow
def test_g1_accept_floor_full():
    clause1, clause2 = _accept_floor_sweep(trials=40000)
    assert clause1 == 0 and clause2 == 0


@pytest.mark.slow
def test_g3_endgame_full():
    inert, over, under = _endgame_sweep(trials=40000)
    assert inert == 0 and over == 0 and under == 0


@pytest.mark.slow
def test_symmetry_full():
    assert _symmetry_sweep(trials=5000) == 0

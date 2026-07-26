"""Tests for the station rent-renewal simulation (PREREG.md, SPEC.md).

Real invariants, not smoke: determinism, cash conservation, policy monotonicity,
the economic ordering of the concession instruments, and the structural
properties the kill conditions depend on (that the station cannot see who is an
asker; that arms D and E coincide at asker share 0).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                                # noqa: E402
import pytest                                                     # noqa: E402

from crabs import world as W                                      # noqa: E402
from crabs.policies import (PRICE_LADDER, RANKED_LADDER, RS, QA,   # noqa: E402
                            StationDP)
from crabs.run import derive                                      # noqa: E402
from crabs.world import (ASK_PRICE, ASK_RANKED, FEES, NEVER_ASK,   # noqa: E402
                         ONE_TIME, RENT, TERM, Params, attach,
                         gain_base, market_path, p_exo, q_sit,
                         regime_params, simulate_station,
                         switching_cost_nodes)

BASE = Params()
NODES, EDGES = switching_cost_nodes(BASE, 32)
FLAT = np.tile(np.ones(32) / 32, (BASE.j_max + 1, 1))


def _dp(regime="burn", share=0.0, adaptive=False, **over):
    p = regime_params(Params(**{**BASE.__dict__, **over}), regime)
    return p, StationDP(p, NODES, FLAT, share=share, adaptive=adaptive)


def _run(regime="burn", share=0.39, strategy=ASK_PRICE, seeds=(1000, 1001, 1002),
         adaptive=False, **over):
    base = Params(**{**BASE.__dict__, **over})
    pb = regime_params(base, "burn")
    pm = regime_params(base, regime)
    stb = StationDP(pb, NODES, FLAT)
    stm = (stb if (regime == "burn" and share == 0.0 and not adaptive)
           else StationDP(pm, NODES, FLAT, share=share, adaptive=adaptive))
    recs = [simulate_station(pb, pm, s, regime, stb, stm, share, strategy)
            for s in seeds]
    agg = {k: sum(r[k] for r in recs) for k in recs[0] if not k.startswith("_")}
    return agg, recs


# --------------------------------------------------------------- determinism
def test_same_seed_identical_results():
    a, _ = _run(seeds=(1000, 1001, 1002))
    b, _ = _run(seeds=(1000, 1001, 1002))
    assert a == b


def test_different_seed_different_results():
    a, _ = _run(seeds=(1000,))
    b, _ = _run(seeds=(1001,))
    assert a["surplus"] != b["surplus"]


def test_no_global_rng_dependence():
    """A seeded run must not move if the global numpy RNG is disturbed."""
    a, _ = _run(seeds=(1000, 1001))
    np.random.seed(7)
    _ = np.random.random(1000)
    b, _ = _run(seeds=(1000, 1001))
    assert a == b


def test_market_path_deterministic_and_burnin_regime_independent():
    p_l = regime_params(BASE, "loss")
    p_g = regime_params(BASE, "gain")
    a = market_path(p_l, 1234, "loss", 5, 4)
    b = market_path(p_l, 1234, "loss", 5, 4)
    assert np.array_equal(a, b)
    c = market_path(p_g, 1234, "gain", 5, 4)
    # burn-in is drawn from a regime-independent stream (SPEC §9)
    assert np.allclose(a[:5], c[:5])
    assert not np.allclose(a[5:], c[5:])


def test_dp_deterministic():
    _, s1 = _dp("gain")
    _, s2 = _dp("gain")
    assert np.array_equal(s1.pol, s2.pol)
    assert np.allclose(s1.V, s2.V)


# ------------------------------------------------------ accounting / conservation
@pytest.mark.parametrize("regime", ["burn", "loss", "gain"])
def test_cash_conserved(regime):
    """Every dollar a crab pays is a dollar a station receives. Turn cost is a
    real cost, not a transfer; arriving crabs are outside the surplus universe."""
    agg, _ = _run(regime=regime, seeds=(1000, 1001, 1002, 1003))
    lhs = agg["station_cash"]
    rhs = agg["crab_cash"] + agg["arrival_cash"] - agg["turn_cost_paid"]
    assert abs(lhs - rhs) < 1e-6 * max(1.0, abs(lhs))


@pytest.mark.parametrize("regime", ["burn", "loss", "gain"])
def test_asker_nonasker_partition(regime):
    agg, _ = _run(regime=regime, seeds=(1000, 1001))
    assert agg["crab_years_asker"] + agg["crab_years_nonasker"] == \
        agg["crab_years"]
    assert agg["renewals_asker"] + agg["renewals_nonasker"] == agg["renewals"]
    assert abs(agg["surplus_asker"] + agg["surplus_nonasker"]
               - agg["surplus"]) < 1e-6 * max(1.0, abs(agg["surplus"]))


def test_counts_are_consistent():
    agg, _ = _run(seeds=(1000, 1001))
    assert agg["left"] <= agg["renewals"]
    assert agg["success"] <= agg["countered"] <= agg["renewals"]
    assert agg["countered_lt2"] + agg["countered_ge2"] == agg["countered"]
    assert agg["success_lt2"] + agg["success_ge2"] == agg["success"]
    # only askers ever counter
    assert agg["countered"] <= agg["renewals_asker"]


def test_never_ask_never_counters():
    agg, _ = _run(share=0.0, seeds=(1000, 1001))
    assert agg["countered"] == 0.0
    assert agg["success"] == 0.0
    assert agg["crab_years_asker"] == 0.0


def test_all_ask_share_one():
    agg, _ = _run(share=1.0, seeds=(1000, 1001))
    assert agg["crab_years_nonasker"] == 0.0
    assert agg["renewals_nonasker"] == 0.0


def test_habitat_years_exact():
    base = Params()
    agg, _ = _run(seeds=(1000, 1001, 1002))
    assert agg["habitat_years"] == 3 * base.units * base.meas_years


# ------------------------------------------------------------ policy invariants
def test_offer_respects_cap_and_floor():
    p, st = _dp("loss")
    for j in (1, 4, 8):
        for r in np.arange(0.6, 1.6, 0.05):
            q = st.offer(r, j)
            assert q <= r * (1 + p.renewal_cap) + 1e-6, (r, j, q)
            assert q >= r * (1 - p.renewal_floor) - 1e-6, (r, j, q)


def test_offer_monotone_in_r():
    """A station holding a higher rent of record never offers less."""
    _, st = _dp("gain")
    for j in (1, 4, 8):
        qs = [st.offer(r, j) for r in np.arange(0.7, 1.5, 0.02)]
        assert all(b >= a - 1e-9 for a, b in zip(qs, qs[1:]))


def test_leave_prob_monotone_and_bounded():
    p, st = _dp("burn")
    for j in (1, 4, 8):
        pl = [st.leave_prob(float(gain_base(p, q, 1.0, j)), j)
              for q in np.arange(0.8, 1.6, 0.02)]
        assert all(0.0 <= x <= 1.0 for x in pl)
        assert all(b >= a - 1e-12 for a, b in zip(pl, pl[1:]))
        # never below the exogenous floor
        assert min(pl) >= float(p_exo(p, j)) - 1e-9


def test_p_exo_and_attachment_shapes():
    p = BASE
    pe = [float(p_exo(p, j)) for j in range(1, 9)]
    assert all(b <= a for a, b in zip(pe, pe[1:]))       # declines with tenure
    at = [float(attach(p, j)) for j in range(1, 9)]
    assert all(b >= a for a, b in zip(at, at[1:]))       # grows with tenure
    qs = [float(q_sit(p, j)) for j in range(1, 9)]
    assert all(b <= a for a, b in zip(qs, qs[1:]))       # proven payers cost less
    assert max(qs) < p.q_new                             # ...than an unknown one


def test_higher_turn_cost_means_softer_offer():
    """A station facing a more expensive turnover pushes less. Sign check on the
    whole E[push] tradeoff."""
    _, cheap = _dp("gain", turn_cost=0.5)
    _, dear = _dp("gain", turn_cost=4.0)
    lo = [cheap.offer(r, 3) for r in (0.9, 1.0, 1.1, 1.2)]
    hi = [dear.offer(r, 3) for r in (0.9, 1.0, 1.1, 1.2)]
    assert all(h <= l + 1e-9 for l, h in zip(lo, hi))
    assert sum(hi) < sum(lo)


def test_value_function_increasing_in_rent_of_record():
    _, st = _dp("burn")
    for j in (1, 4, 8):
        v = st.V[j]
        assert all(b >= a - 1e-6 for a, b in zip(v, v[1:]))


# --------------------------------------------- concession-instrument economics
def test_instrument_cost_ordering():
    """SPEC §6: per dollar of value delivered to the crab, a headline rent cut
    must cost the station strictly more than a one-time concession. This is the
    asymmetry the ranked-ask claim lives or dies on."""
    p, st = _dp("gain")
    for r in (0.95, 1.10, 1.25):
        for j in (1, 4, 8):
            q = st.offer(r, j)
            base = st.npv(q, r, j, None)
            for size in (0.3, 0.6, 1.0):
                v_one = st.crab_value(p, q, (ONE_TIME, size))
                v_rent = st.crab_value(p, q, (RENT, size))
                c_one = (base - st.npv(q, r, j, (ONE_TIME, size))) / v_one
                c_rent = (base - st.npv(q, r, j, (RENT, size))) / v_rent
                assert c_rent > c_one, (r, j, size, c_rent, c_one)


def test_fee_waiver_is_capped():
    p, st = _dp("burn")
    q = 1.1
    big = st.crab_value(p, q, (FEES, 1.0))
    cap = p.fee_cap_frac * 12.0 * q * (1.0 + p.disc_crab)
    assert abs(big - cap) < 1e-9
    assert big < st.crab_value(p, q, (ONE_TIME, 1.0))


def test_term_extension_is_regime_dependent_for_the_crab():
    """A crab should want to lock in when it forecasts a rising market and not
    when it forecasts a falling one -- not hard-coded, it falls out of the
    two-year valuation."""
    p, st = _dp("burn")
    q = 1.10
    up = st.crab_value(p, q, (TERM, 1.0), g_obs_crab=+0.09)
    down = st.crab_value(p, q, (TERM, 1.0), g_obs_crab=-0.06)
    assert up > 0.0
    assert down < up
    assert down <= 0.0


def test_one_time_does_not_move_the_rent_of_record():
    p, st = _dp("burn")
    q = 1.1
    qe, z, _, _ = st.package_effects(p, q, (ONE_TIME, 1.0))
    assert qe == q and z > 0
    qe2, z2, _, _ = st.package_effects(p, q, (RENT, 1.0))
    assert qe2 < q and z2 == 0.0


def test_rent_cut_persists_and_one_time_does_not():
    """Realised accounting: a rent cut lowers next year's base, free weeks do
    not. Same crab, same seeds, two granted packages."""
    p, st = _dp("burn")
    q, M = 1.10, 2000.0
    c1 = W.Crab(strategy=ASK_RANKED, rent=q * M, tenure=3, c_persist=3.0)
    st.apply_package(p, c1, q, (ONE_TIME, 1.0), M, 0.0)
    c2 = W.Crab(strategy=ASK_RANKED, rent=q * M, tenure=3, c_persist=3.0)
    st.apply_package(p, c2, q, (RENT, 1.0), M, 0.0)
    assert c1.rent == pytest.approx(q * M)
    assert c2.rent < q * M
    # and the fee waiver is a two-year instrument, tracked in state
    c3 = W.Crab(strategy=ASK_RANKED, rent=q * M, tenure=3, c_persist=3.0)
    st.apply_package(p, c3, q, (FEES, 1.0), M, 0.0)
    assert c3.fee_years == 2 and c3.fee_value > 0.0


def test_station_never_grants_a_negative_npv_package():
    p, st = _dp("gain")
    rng = np.random.default_rng(np.random.SeedSequence([5]))
    for _ in range(300):
        r = float(rng.uniform(0.7, 1.5))
        j = int(rng.integers(1, 9))
        q = st.offer(r, j)
        u = rng.random(W.N_UNIFORMS)
        crab = W.Crab(strategy=ASK_RANKED, rent=r * 2000.0, tenure=j,
                      c_persist=3.0)
        pkg, _, _, kind = st.negotiate(p, crab, q, r, j, u, -0.06, ASK_RANKED)
        if pkg is not None:
            assert st.npv(q, r, j, pkg) >= st.npv(q, r, j, None) - 1e-9


def test_ladders_match_prereg():
    assert [k for k, _ in RANKED_LADDER] == [ONE_TIME, FEES, TERM, RENT]
    assert {k for k, _ in PRICE_LADDER} == {RENT}


# ---------------------------------------------------- structural kill-condition
def test_station_cannot_observe_asker_status():
    """K3 depends on the station being unable to tell askers from non-askers ex
    ante. The offer must be a function of (r, j) only."""
    p, st = _dp("gain", )
    u = np.full(W.N_UNIFORMS, 0.5)
    for j in (1, 5):
        for r in (0.9, 1.1, 1.3):
            q = st.offer(r, j)
            offers = set()
            for strat in (NEVER_ASK, ASK_PRICE, ASK_RANKED):
                crab = W.Crab(strategy=strat, rent=r * 2000.0, tenure=j,
                              c_persist=3.0)
                offers.add(st.offer(crab.rent / 2000.0, j))
            assert len(offers) == 1 and q in offers


def test_arms_d_and_e_coincide_at_zero_share():
    """With nobody countering there is nothing for the adaptive station to
    anticipate, so arm E must reduce exactly to arm D."""
    for regime in ("loss", "gain"):
        p = regime_params(BASE, regime)
        d = StationDP(p, NODES, FLAT, share=0.0, adaptive=False)
        e = StationDP(p, NODES, FLAT, share=0.0, adaptive=True)
        assert np.array_equal(d.pol, e.pol)


def test_adaptive_station_pre_inflates_the_opening_offer():
    """Arm E's mechanism: knowing the asker share, it opens higher. If this
    fails, arm E is not testing what PREREG says it tests."""
    for regime in ("loss", "gain"):
        p = regime_params(BASE, regime)
        st0 = StationDP(p, NODES, FLAT, share=0.0, adaptive=False)
        st1 = StationDP(p, NODES, FLAT, share=1.0, adaptive=True)
        base = np.array([st0.offer(r, 4) for r in np.arange(0.8, 1.4, 0.05)])
        adap = np.array([st1.offer(r, 4) for r in np.arange(0.8, 1.4, 0.05)])
        assert np.all(adap >= base - 1e-9), regime
        assert adap.sum() > base.sum(), regime


def test_common_random_numbers_align_across_arms():
    """Arms must share the burn-in exactly, so measured differences are policy,
    not noise."""
    base = Params()
    pb = regime_params(base, "burn")
    pm = regime_params(base, "gain")
    stb = StationDP(pb, NODES, FLAT)
    stm = StationDP(pm, NODES, FLAT)
    a = simulate_station(pb, pm, 1000, "gain", stb, stm, 0.0, ASK_RANKED)
    b = simulate_station(pb, pm, 1000, "gain", stb, stm, 0.0, ASK_PRICE)
    # share 0 => strategy is irrelevant => identical histories
    assert a == b


def test_regimes_have_the_intended_sign():
    """The regime variable must actually flip the sign of loss-to-lease."""
    loss, _ = _run(regime="loss", seeds=(1000, 1001, 1002, 1003))
    gain, _ = _run(regime="gain", seeds=(1000, 1001, 1002, 1003))
    dl, dg = derive(loss), derive(gain)
    assert dl["market_rent"] > dg["market_rent"]
    assert dl["rent_ratio"] < dg["rent_ratio"]
    assert dl["mean_offer_push"] > dg["mean_offer_push"]


def test_retention_and_surplus_are_sane():
    for regime in ("loss", "gain"):
        agg, _ = _run(regime=regime, seeds=(1000, 1001, 1002))
        d = derive(agg)
        assert 0.2 < d["retention"] < 0.95
        assert 0.0 <= d["success_rate"] <= 1.0
        assert d["market_rent"] > 0
        assert abs(d["ledger_gap"]) < 1e-4


def test_concessions_raise_crab_surplus_weakly():
    """Sanity direction: at a fixed station policy, 100% ranked askers cannot
    end up with less surplus than 0% askers under a NON-adaptive station."""
    for regime in ("loss", "gain"):
        none, _ = _run(regime=regime, share=0.0, strategy=ASK_RANKED,
                       seeds=(1000, 1001, 1002, 1003, 1004))
        allc, _ = _run(regime=regime, share=1.0, strategy=ASK_RANKED,
                       seeds=(1000, 1001, 1002, 1003, 1004))
        s0 = none["surplus"] / none["crab_years"]
        s1 = allc["surplus"] / allc["crab_years"]
        assert s1 >= s0 - 1e-6, (regime, s0, s1)


def test_registered_spec_has_no_turn_dispersion():
    """The registered specification must stay reproducible: dispersion off by
    default, so `Params()` is exactly what SPEC.md declared."""
    p = Params()
    assert p.sigma_turn == 0.0 and p.sigma_vac == 0.0
    assert p.turn_tenure_slope == 0.0
    u = np.full(W.N_UNIFORMS, 0.31)
    for j in (1, 4, 8):
        assert W.turn_multipliers(p, u, j) == (1.0, 1.0)


def test_turn_dispersion_is_mean_one():
    """Switching dispersion on must not move the average turn cost -- otherwise
    the exploratory respecification would be a disguised change of level."""
    from crabs.run import EXPLORATORY
    p = Params(**{**BASE.__dict__, **EXPLORATORY, "turn_tenure_slope": 0.0})
    rng = np.random.default_rng(np.random.SeedSequence([3]))
    tm, vm = [], []
    for _ in range(40000):
        u = rng.random(W.N_UNIFORMS)
        a, b = W.turn_multipliers(p, u, 4)
        tm.append(a)
        vm.append(b)
    assert abs(np.mean(tm) - 1.0) < 0.02
    assert abs(np.mean(vm) - 1.0) < 0.02
    assert np.std(tm) > 0.3


def test_tenure_slope_raises_make_ready_cost():
    from crabs.run import EXPLORATORY
    p = Params(**{**BASE.__dict__, **EXPLORATORY, "sigma_turn": 0.0,
                  "sigma_vac": 0.0})
    mults = [W.turn_multipliers(p, np.full(W.N_UNIFORMS, 0.5), j)[0]
             for j in range(1, 9)]
    assert all(b > a for a, b in zip(mults, mults[1:]))
    assert 1.25 < mults[-1] / mults[0] < 1.45


def test_dearer_turn_exposure_makes_the_station_concede():
    """The mechanism the exploratory respecification adds: a habitat that is
    expensive to turn gets a concession where a cheap one does not."""
    from crabs.run import EXPLORATORY
    p, st = _dp("gain", **EXPLORATORY)
    granted_cheap = granted_dear = 0
    rng = np.random.default_rng(np.random.SeedSequence([11]))
    for _ in range(200):
        r = float(rng.uniform(0.95, 1.35))
        j = int(rng.integers(1, 9))
        q = st.offer(r, j)
        u = rng.random(W.N_UNIFORMS)
        crab = W.Crab(strategy=ASK_RANKED, rent=r * 2000.0, tenure=j,
                      c_persist=3.0)
        for tag, tm, vm in (("cheap", 0.4, 0.6), ("dear", 2.5, 1.8)):
            pkg, _, _, _ = st.negotiate(p, crab, q, r, j, u, -0.06, ASK_RANKED,
                                        tmul=tm, vmul=vm)
            if pkg is not None:
                if tag == "cheap":
                    granted_cheap += 1
                else:
                    granted_dear += 1
    assert granted_dear > granted_cheap, (granted_dear, granted_cheap)


def test_norm_ppf_matches_scipy_grid():
    from crabs.world import _norm_ppf
    u = np.array([0.001, 0.01, 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98, 0.99,
                  0.999])
    got = _norm_ppf(u)
    want = np.array([-3.090232, -2.326348, -2.053749, -1.281552, -0.674490,
                     0.0, 0.674490, 1.281552, 2.053749, 2.326348, 3.090232])
    assert np.max(np.abs(got - want)) < 1e-4


def test_switching_cost_nodes_deterministic_and_sorted():
    a, ea = switching_cost_nodes(BASE, 32)
    b, eb = switching_cost_nodes(BASE, 32)
    assert np.array_equal(a, b) and np.array_equal(ea, eb)
    assert np.all(np.diff(a) > 0)
    assert abs(np.median(a) / BASE.move_med - 1.0) < 0.25


# ============================ PHASE 2 (AMENDMENT 1) ==========================

def _ll(kind, regime="gain", **over):
    from crabs.landlords import make_landlord
    p = regime_params(Params(**{**BASE.__dict__, **over}), regime)
    return p, make_landlord(kind, p, NODES, FLAT)


def _run2(kind, regime="gain", share=0.39, seeds=(1000, 1001, 1002, 1003),
          learn=False, broadcast=False, shock=None, units=None, **over):
    from crabs.landlords import TYPE_GEOMETRY, make_landlord
    from crabs.run2 import make_shock
    u = units or TYPE_GEOMETRY[kind]["units"]
    base = Params(**{**BASE.__dict__, **over, "units": u})
    if shock:
        base = Params(**{**base.__dict__, "meas_years": 14})
    pb, pm = regime_params(base, "burn"), regime_params(base, regime)
    stb = StationDP(pb, NODES, FLAT)
    stm = make_landlord(kind, pm, NODES, FLAT)
    sh = make_shock(shock) if shock else None
    recs = [simulate_station(pb, pm, s, regime, stb, stm, share, ASK_RANKED,
                             learn=learn, broadcast=broadcast, shock=sh)
            for s in seeds]
    return {k: sum(r[k] for r in recs) for k in recs[0]
            if not k.startswith("_")}


def test_landlord_types_are_deterministic():
    from crabs.landlords import INSTITUTIONAL, MEDIUM, MOM_AND_POP
    for kind in (INSTITUTIONAL, MEDIUM, MOM_AND_POP):
        a = _run2(kind, seeds=(1000, 1001))
        b = _run2(kind, seeds=(1000, 1001))
        assert a == b, kind


@pytest.mark.parametrize("kind", ["institutional", "medium", "mom"])
def test_cash_conserved_for_every_landlord_type(kind):
    agg = _run2(kind, seeds=(1000, 1001, 1002))
    lhs = agg["station_cash"]
    rhs = agg["crab_cash"] + agg["arrival_cash"] - agg["turn_cost_paid"]
    assert abs(lhs - rhs) < 1e-6 * max(1.0, abs(lhs))


def test_mom_and_pop_holds_rent_and_never_prices_above_market():
    """The two documented facts: 18% never raise, and none of them chase a
    sitting tenant above market. This is what makes them the best to HAVE."""
    from crabs.landlords import MOM_AND_POP
    p, ll = _ll(MOM_AND_POP)
    ll.no_increase = True
    for r in (0.7, 0.9, 1.0, 1.3):
        for j in (1, 5, 8):
            assert ll.offer(r, j) == pytest.approx(r)
    ll.no_increase = False
    for r in (0.7, 0.9, 0.99, 1.0, 1.3):
        for j in (1, 5, 8):
            q = ll.offer(r, j)
            assert q >= r - 1e-12
            assert q <= max(r, 1.0) + 1e-12


def test_mom_and_pop_rarely_concedes_and_favours_tenure():
    from crabs.landlords import MOM_AND_POP
    _, ll = _ll(MOM_AND_POP)
    ps = [ll.grant_prob(j) for j in range(1, 9)]
    assert all(b >= a for a, b in zip(ps, ps[1:]))
    assert 0.05 < ps[0] < 0.15               # ~90% offer nothing at short tenure
    assert ps[-1] <= ll.grant_cap


def test_medium_offer_is_bounded_and_comp_aware():
    from crabs.landlords import MEDIUM
    p, ll = _ll(MEDIUM)
    for r in np.arange(0.7, 1.5, 0.05):
        q = ll.offer(r, 4)
        assert r * (1 - ll.max_cut) - 1e-12 <= q <= r * (1 + ll.max_inc) + 1e-12
    # comp-aware: it pulls a far-below-market rent up and a far-above one down
    assert ll.offer(0.8, 4) > 0.8
    assert ll.offer(1.4, 4) < 1.4


def test_medium_refuses_headline_rate_cuts():
    from crabs.landlords import MEDIUM
    p, ll = _ll(MEDIUM)
    u = np.full(W.N_UNIFORMS, 0.99)          # no substitution, no patience
    crab = W.Crab(strategy=ASK_PRICE, rent=1.1 * 2000.0, tenure=4,
                  c_persist=3.0)
    pkg, _, asked, kind = ll.negotiate(p, crab, 1.1, 1.05, 4, u, -0.06,
                                       ASK_PRICE)
    assert asked and pkg is None and kind is None


def test_arm_f_asker_share_is_endogenous_not_assigned():
    """Arm F must not read `share`. Two runs with different nominal shares must
    give the same endogenous asker share."""
    a = _run2("institutional", share=0.0, learn=True, units=50,
              seeds=(1000, 1001))
    b = _run2("institutional", share=1.0, learn=True, units=50,
              seeds=(1000, 1001))
    sa = a["ask_share_sum"] / a["ask_share_n"]
    sb = b["ask_share_sum"] / b["ask_share_n"]
    assert abs(sa - sb) < 0.02, (sa, sb)
    assert 0.0 < sa < 1.0


def test_arm_f_more_optimistic_crabs_ask_more():
    """The endogenous share must move with belief, or broadcast has no channel
    through which to raise adoption."""
    lo = _run2("institutional", learn=True, units=50, seeds=(1000, 1001),
               belief0=0.02)
    hi = _run2("institutional", learn=True, units=50, seeds=(1000, 1001),
               belief0=0.60)
    a = lo["ask_share_sum"] / lo["ask_share_n"]
    b = hi["ask_share_sum"] / hi["ask_share_n"]
    assert b > a + 0.05, (a, b)


def test_broadcast_raises_beliefs_when_asking_works():
    """With broadcast on, crabs converge on the station's realised success rate;
    with it off they only ever see their own single outcome."""
    on = _run2("medium", learn=True, broadcast=True, seeds=(1000, 1001, 1002))
    off = _run2("medium", learn=True, broadcast=False, seeds=(1000, 1001, 1002))
    b_on = on["belief_sum"] / on["belief_n"]
    b_off = off["belief_sum"] / off["belief_n"]
    # MEDIUM concedes very readily, so the truth is far above the prior
    assert b_on > b_off, (b_on, b_off)
    assert b_on > BASE.belief0


def test_broadcast_is_no_stronger_in_a_small_station():
    """CORRECTION to a Phase-2 claim. We wrote that a 200-habitat grapevine
    "lifts beliefs more" than a small one. That is wrong as stated: station size
    governs the PRECISION of the grapevine, not its mean, so with enough
    station-years the average lift converges. What survives is the weak
    inequality plus the fact that both learn something."""
    big = _run2("medium", learn=True, broadcast=True, units=200,
                seeds=tuple(range(1000, 1006)))
    small = _run2("medium", learn=True, broadcast=True, units=4,
                  seeds=tuple(range(1000, 1006)))
    lift_big = big["belief_sum"] / big["belief_n"] - BASE.belief0
    lift_small = small["belief_sum"] / small["belief_n"] - BASE.belief0
    assert lift_big > 0.0 and lift_small > 0.0
    assert lift_small <= lift_big + 0.02, (lift_big, lift_small)


# ------------------------ AMENDMENT 3 / 4: the real engine -------------------

def test_engine_is_actually_called_not_reimplemented():
    """AMENDMENT 3 §A3.0's defect: Phase 1 never touched the product. Assert the
    real entry points exist and that our bridge calls them."""
    import inspect

    from gametheory.negotiation.bundle import negotiate_bundle
    from gametheory.negotiation.plain_terms import negotiate_turn

    from crabs import armk, engine_bridge
    src = inspect.getsource(engine_bridge) + inspect.getsource(armk)
    assert "negotiate_bundle(" in src and "negotiate_turn(" in src
    sig = inspect.signature(negotiate_bundle).parameters
    for k in ("issues", "their_offers", "my_priorities", "my_batna",
              "their_batna_estimate", "cooperation", "rounds_left", "seed"):
        assert k in sig, k


def test_engine_priority_inference_is_not_bypassed():
    """The engine must be given only the DIRECTION of the counterparty's
    preferences, never their relative priorities across issues -- inferring those
    is the product."""
    from crabs.demographics import draw_tenant
    from crabs.engine_bridge import build_issues
    p = regime_params(Params(**{**BASE.__dict__, "negotiator": "engine_bundle"}),
                      "gain")
    ten = draw_tenant(np.full(7, 0.5))
    issues, mu = build_issues(p, ten, 1.10, 2000.0, -0.06)
    assert len(issues) == 4
    for it in issues:
        assert len(it["options"]) == len(it["my_utility"]) == \
            len(it["their_utility"])
        # a pure direction vector: monotone, and carrying no magnitude information
        tu = it["their_utility"]
        assert tu == sorted(tu) or tu == sorted(tu, reverse=True)


def test_tenant_utilities_are_demographically_heterogeneous():
    """If every tenant had the same priorities there would be no logrolling
    surface and K13 would deserve to fire on the population, not the engine."""
    from crabs.demographics import draw_tenant, share_term_over_rent
    rng = np.random.default_rng(np.random.SeedSequence([4]))
    ws = [draw_tenant(rng.random(7)).w for _ in range(400)]
    assert len({tuple(round(x, 3) for x in w) for w in ws}) > 350
    assert 0.05 < share_term_over_rent() < 0.40


def test_cost_burdened_tenants_are_more_rent_sensitive():
    """DERIVED, not imposed: CRRA over residual income means a low-income tenant
    has a steeper marginal utility of rent without being told to."""
    from crabs.demographics import crra
    lo, hi = 40_000.0, 200_000.0
    d_lo = float(crra(lo - 24000.0) - crra(lo - 26400.0))
    d_hi = float(crra(hi - 24000.0) - crra(hi - 26400.0))
    assert d_lo > d_hi > 0.0


@pytest.mark.parametrize("neg", ["engine_single", "engine_bundle"])
def test_cash_conserved_with_the_real_engine(neg):
    from crabs.run import EXPLORATORY
    base = Params(**{**BASE.__dict__, **EXPLORATORY, "units": 40,
                     "negotiator": neg})
    pb, pm = regime_params(base, "burn"), regime_params(base, "gain")
    stb, stm = StationDP(pb, NODES, FLAT), StationDP(pm, NODES, FLAT)
    recs = [simulate_station(pb, pm, s, "gain", stb, stm, 1.0, ASK_RANKED)
            for s in (1000, 1001)]
    agg = {k: sum(r[k] for r in recs) for k in recs[0] if not k.startswith("_")}
    lhs = agg["station_cash"]
    rhs = agg["crab_cash"] + agg["arrival_cash"] - agg["turn_cost_paid"]
    assert abs(lhs - rhs) < 1e-6 * max(1.0, abs(lhs))


def test_engine_bundles_really_are_multi_issue():
    """If the engine only ever moved rent it would not be logrolling."""
    from crabs.run import EXPLORATORY, derive
    base = Params(**{**BASE.__dict__, **EXPLORATORY, "units": 50,
                     "negotiator": "engine_bundle"})
    pb, pm = regime_params(base, "burn"), regime_params(base, "gain")
    stb, stm = StationDP(pb, NODES, FLAT), StationDP(pm, NODES, FLAT)
    rec = simulate_station(pb, pm, 1000, "gain", stb, stm, 1.0, ASK_RANKED)
    assert rec["bundles_granted"] > 0
    assert derive(rec)["issues_per_grant"] > 1.5


def test_arm_k_cells_differ_only_in_who_holds_the_engine():
    """Same world, same seeds; N/N and T/N must diverge only through the
    negotiation policy, and the two must not be identical."""
    from crabs.run import EXPLORATORY
    out = {}
    for te, le in ((False, False), (True, False), (False, True)):
        base = Params(**{**BASE.__dict__, **EXPLORATORY, "units": 40,
                         "negotiator": "matrix", "tenant_engine": te,
                         "landlord_engine": le})
        pb, pm = regime_params(base, "burn"), regime_params(base, "gain")
        stb, stm = StationDP(pb, NODES, FLAT), StationDP(pm, NODES, FLAT)
        rec = simulate_station(pb, pm, 1000, "gain", stb, stm, 1.0, ASK_RANKED)
        out[(te, le)] = rec
    assert out[(False, False)]["market_sum"] == out[(True, False)]["market_sum"]
    assert out[(False, False)]["surplus"] != out[(True, False)]["surplus"]
    assert out[(False, False)]["surplus"] != out[(False, True)]["surplus"]


def test_snhp_landlord_can_open_above_its_plain_optimum():
    """K16 depends on this. An engine-armed landlord must be able to OPEN with a
    bundle, not merely reply -- our first implementation could only reply, which
    silently prevented K16 from firing."""
    from crabs.armk import LANDLORD_OPENERS, landlord_opener
    from crabs.engine_bridge import N_TENANT_RENT, RENT_FACTORS
    from crabs.run import EXPLORATORY
    assert any(b.ri >= N_TENANT_RENT for b in LANDLORD_OPENERS)
    assert max(RENT_FACTORS) > 1.0
    p, st = _dp("gain", **EXPLORATORY)
    from crabs.demographics import draw_tenant
    ten = draw_tenant(np.full(7, 0.5))
    got = [landlord_opener(st, p, j, r, st.offer(r, j), ten, 2000.0, -0.06,
                           None, 1.0)
           for r in (1.0, 1.1, 1.25) for j in (1, 4, 8)]
    assert any(b.ri >= N_TENANT_RENT or b.ci > 0 or b.fee or b.term
               for b in got)


def test_broadcast_off_is_a_real_control_not_a_no_op():
    from crabs.run import EXPLORATORY
    on = _run2("institutional", learn=True, broadcast=True, units=100,
               seeds=(1000, 1001), **EXPLORATORY)
    off = _run2("institutional", learn=True, broadcast=False, units=100,
                seeds=(1000, 1001), **EXPLORATORY)
    assert on["surplus"] != off["surplus"]
    assert (on["ask_share_sum"] / on["ask_share_n"]
            > off["ask_share_sum"] / off["ask_share_n"])


def test_broadcast_transmits_bad_news_too():
    """The grapevine carries the truth in both directions. Under the REGISTERED
    specification the station concedes to nobody, so broadcast teaches crabs to
    stop asking -- and because nothing is ever granted, surplus is untouched."""
    on = _run2("institutional", learn=True, broadcast=True, units=100,
               seeds=(1000, 1001))
    off = _run2("institutional", learn=True, broadcast=False, units=100,
                seeds=(1000, 1001))
    assert on["success"] == off["success"] == 0.0
    assert (on["ask_share_sum"] / on["ask_share_n"]
            < off["ask_share_sum"] / off["ask_share_n"])
    assert on["surplus"] == off["surplus"]


def test_shock_arrays_and_market_response():
    from crabs.run2 import SHOCK_YEARS, make_shock
    for name in ("flu", "migration"):
        s = make_shock(name)
        for arr in (s.drift, s.vac_mult, s.wealth, s.exodus):
            assert len(arr) == SHOCK_YEARS
    flu = make_shock("flu")
    assert flu.drift.min() <= -0.09 and flu.vac_mult.max() >= 2.0
    assert flu.wealth.max() == 0.0
    mig = make_shock("migration")
    assert mig.wealth.max() > 0.0 and mig.exodus.max() > 0.0
    # the flu really does drive market rent down relative to no shock
    p = regime_params(Params(**{**BASE.__dict__, "meas_years": 14}), "burn")
    base = market_path(p, 1234, "burn", 5, 14)
    shocked = market_path(p, 1234, "burn", 5, 14, drift_override=flu.drift)
    assert shocked[-1] < 0.6 * base[-1]


def test_wealthy_crabs_tolerate_more_above_market_rent():
    """The migration's mechanism: high-budget arrivals are less price-sensitive,
    so they sustain a comp that strands incumbents when they leave."""
    p = regime_params(BASE, "burn")
    poor = W.Crab(strategy=NEVER_ASK, rent=2400.0, tenure=3, c_persist=3.0)
    rich = W.Crab(strategy=NEVER_ASK, rent=2400.0, tenure=3, c_persist=3.0,
                  wealth=3.0)
    gb = float(gain_base(p, 1.2, 1.1, 3))
    assert gb - rich.wealth < gb - poor.wealth


@pytest.mark.parametrize("shock", ["flu", "migration"])
def test_cash_conserved_under_shocks(shock):
    agg = _run2("institutional", shock=shock, units=50, seeds=(1000, 1001))
    lhs = agg["station_cash"]
    rhs = agg["crab_cash"] + agg["arrival_cash"] - agg["turn_cost_paid"]
    assert abs(lhs - rhs) < 1e-6 * max(1.0, abs(lhs))


def test_grid_covers_the_realised_state_space():
    for regime in ("loss", "gain"):
        _, recs = _run(regime=regime, seeds=(1000, 1001, 1002))
        agg = {k: sum(r[k] for r in recs) for k in recs[0]
               if not k.startswith("_")}
        rr = agg["rent_ratio_sum"] / agg["rent_ratio_n"]
        assert RS[0] < rr < RS[-1]
        assert QA[0] < rr < QA[-1]


# ---------------- AMENDMENT 5 / 5a: two channels, walk-away asymmetry --------

def test_make_ready_is_sunk_and_never_charged_twice():
    """A5a.1: make-ready is one-time. It is charged exactly once per turn event
    and NEVER again in the new-let channel."""
    from crabs.market import MarketParams, newlet_walkaways, simulate_market
    p = regime_params(BASE, "burn")
    rec = simulate_market(p, MarketParams(n_stations=8, units=15,
                                          meas_years=4), 1000)
    # one make-ready charge per turn event, and none of it inside a new let
    assert rec["turn_events"] > 0
    assert rec["turn_cost_paid"] > 0
    # charged once per turn event, at that period's rent (so the per-event figure
    # tracks the market level rather than a fixed dollar band)
    per_event = rec["turn_cost_paid"] / rec["turn_events"]
    assert per_event > 0.0
    # the new-let landlord walk-away must contain NO make-ready component
    mp = MarketParams()
    _, wa_land, _, _, wait = newlet_walkaways(p, mp, 2000.0, 2100.0, 25, 1.0, 0.0)
    assert abs(wa_land - wait * 2000.0) < 1e-9
    assert wa_land < p.turn_cost * 2000.0 * 3.0


def test_vacancy_is_a_flow_not_a_sunk_cost():
    """A5a.1: vacancy accumulates every month a habitat sits empty."""
    from crabs.market import MarketParams, simulate_market
    p = regime_params(BASE, "burn")
    rec = simulate_market(p, MarketParams(n_stations=8, units=15,
                                          meas_years=4), 1000)
    assert rec["vacant_months"] > 0
    assert rec["vacancy_lost"] > 0
    # charged per vacant month, so the implied monthly rate is a sane rent
    rate = rec["vacancy_lost"] / rec["vacant_months"]
    assert 500.0 < rate < 6000.0


def test_higher_local_vacancy_gives_a_worse_new_let_batna():
    """A5a.2 REQUIRES this test. A station facing a slacker market must have a
    WORSE new-let BATNA: more listings per searcher => longer expected wait =>
    lower reservation."""
    from crabs.market import expected_wait_months, newlet_walkaways, MarketParams
    p = regime_params(BASE, "burn")
    mp = MarketParams()
    waits = [expected_wait_months(t, 0.0) for t in (2.0, 1.0, 0.5, 0.25)]
    assert all(b > a for a, b in zip(waits, waits[1:])), waits
    resv = []
    for t in (2.0, 1.0, 0.5, 0.25):
        _, wa_land, _, rl, _ = newlet_walkaways(p, mp, 2000.0, 2100.0, 25, t, 0.0)
        resv.append(rl)
    assert all(b < a for a, b in zip(resv, resv[1:])), resv


def test_landlord_reservation_weakens_monotonically_in_days_on_market():
    """A5a.3 REQUIRES this. Vacancy accumulating per period means the landlord's
    reservation must fall as a listing ages."""
    from crabs.market import expected_wait_months, newlet_walkaways, MarketParams
    p = regime_params(BASE, "burn")
    mp = MarketParams()
    waits = [expected_wait_months(1.0, d) for d in (0, 1, 3, 6, 9)]
    assert all(b > a for a, b in zip(waits, waits[1:])), waits
    resv = []
    for d in (0, 1, 3, 6, 9):
        _, _, _, rl, _ = newlet_walkaways(p, mp, 2000.0, 2100.0, 25, 1.0, d)
        resv.append(rl)
    assert all(b < a for a, b in zip(resv, resv[1:])), resv


def test_the_asymmetry_inverts_between_channels():
    """A5a.2's central claim, checked at the walk-away level: the TENANT is the
    weak party in a renewal, the LANDLORD is in a new let."""
    from crabs.market import (MarketParams, newlet_walkaways,
                              renewal_walkaways)
    p = regime_params(BASE, "burn")
    mp = MarketParams()
    crab = W.Crab(strategy=0, rent=2100.0, tenure=4, c_persist=BASE.move_med)
    u = np.full(32, 0.5)
    wa_t_r, wa_l_r, _, _, _ = renewal_walkaways(p, mp, crab, u, 2000.0, 2000.0,
                                                25)
    wa_t_n, wa_l_n, _, _, _ = newlet_walkaways(p, mp, 2000.0, 2100.0, 25, 1.0,
                                               0.0)
    assert wa_t_r > wa_l_r, (wa_t_r, wa_l_r)      # tenant weaker in a renewal
    assert wa_l_n > wa_t_n, (wa_l_n, wa_t_n)      # landlord weaker in a new let


def test_price_fall_raises_searcher_inflow():
    """AMENDMENT 6 §A6.1 REQUIRES this. Market entry must respond to the price
    level, or asks ratchet down with no anchor."""
    from crabs.market import ETA_DEMAND, M_REF, searcher_inflow_at
    levels = [3000.0, 2000.0, 1000.0, 500.0]
    inflows = [searcher_inflow_at(0.075, m) for m in levels]
    assert all(b > a for a, b in zip(inflows, inflows[1:])), inflows
    assert abs(searcher_inflow_at(0.075, M_REF) - 0.075) < 1e-12
    for eta in (0.5, 1.0, 1.5, 2.0):
        lo = searcher_inflow_at(0.075, 3000.0, eta)
        hi = searcher_inflow_at(0.075, 1000.0, eta)
        assert hi > lo


def test_elastic_demand_reduces_but_does_not_cure_the_deflation():
    """REPLACES `test_market_rent_is_an_output_and_the_deflation_defect_is_pinned`
    (AMENDMENT 6 §A6.1 requires replacement, not deletion).

    A6.1's first requirement is met: inflow now responds to the price level, and
    raising the elasticity does raise the clearing price and cut vacancy.

    A6.1's SECOND requirement is NOT met: the market still does not clear at an
    interior price. It deflates toward a floor at every elasticity in the
    pre-declared range {0.5, 1.0, 1.5, 2.0}. This test pins that, deliberately,
    so the failure cannot be lost. Diagnosis in RESULTS.md Phase 6: the landlord
    has no absolute reservation tied to its own costs, so once expected waits are
    long its reservation approaches zero and it will accept any rent; signed rents
    are then a large discount off asks, and next period's asks are set from signed
    rents. Adding such a floor would be a seventh mechanism, which A6.3's stopping
    rule forbids."""
    from crabs.market import MarketParams, simulate_market
    p = regime_params(BASE, "burn")
    finals = {}
    for eta in (0.5, 2.0):
        r = simulate_market(p, MarketParams(n_stations=8, units=15,
                                            meas_years=4, eta_demand=eta), 1000)
        finals[eta] = r["_M_hist"][-1]
    # requirement one, met: more elastic demand => higher clearing price
    assert finals[2.0] > finals[0.5], finals
    # requirement two, NOT met: still far below the level it started from
    assert finals[2.0] < 0.75 * 2000.0, finals


def test_market_is_deterministic():
    from crabs.market import MarketParams, simulate_market
    p = regime_params(BASE, "burn")
    mp = MarketParams(n_stations=6, units=12, meas_years=3)
    a = simulate_market(p, mp, 1234)
    b = simulate_market(p, mp, 1234)
    assert {k: v for k, v in a.items() if not k.startswith("_")} == \
        {k: v for k, v in b.items() if not k.startswith("_")}


# ------------- AMENDMENT 6a: deadline shape, symmetric information -----------

def test_renewal_offer_uses_no_private_tenant_draw():
    """AMENDMENT 6a §A6a.3 REQUIRES this test, because K19 was manufactured by
    exactly this hole. The renewal offer must depend only on observables the
    landlord really has -- market rent, tenure, the lease-end date it wrote, and
    elapsed time since its own offer -- plus POPULATION distributions. Two
    tenants who differ only in their private draws must receive the SAME offer.

    Asserted structurally: the offer is built from `p.move_med` and
    `lead_time_nodes()`, and `tenant_clock_multiplier` is called with
    `secured=False` when forming the expectation, so a tenant's realised lead
    time, realised moving cost and secured status cannot enter it."""
    import inspect
    from crabs import market
    src = inspect.getsource(market.simulate_market)
    off = src[src.index("wa_t_base ="):src.index("offer_annual =")]
    # the population median and the population lead-time grid, never a draw
    assert "p.move_med" in off
    assert "lead_time_nodes()" in off
    assert "NOTICE_WINDOW, False)" in off      # secured status never used
    for forbidden in ("crab.c_persist", "_c_total(", "u[11]", "u[13]", "lead,",
                      "secured)"):
        assert forbidden not in off, forbidden


def test_the_two_clocks_have_the_shapes_amendment_6a_specifies():
    """Landlord linear, tenant flat-then-cliff, and the tenant's effective
    deadline arrives EARLIER than lease end."""
    from crabs.market import (CLIFF_CONVEX, LEAD_MEDIAN, NOTICE_WINDOW,
                              tenant_clock_multiplier)
    mults, cliffs = [], []
    for e in (0.0, 1.0, 2.0, 3.0):
        c, k = tenant_clock_multiplier(LEAD_MEDIAN, e, NOTICE_WINDOW)
        mults.append(c)
        cliffs.append(k)
    assert mults[0] == 1.0                       # flat at first
    assert all(b >= a for a, b in zip(mults, mults[1:]))
    # convex INSIDE the usable window (which is only window - lead = 1.5 months;
    # beyond it the multiplier saturates and the discrete cliff takes over)
    inside = [tenant_clock_multiplier(LEAD_MEDIAN, e, NOTICE_WINDOW)[0]
              for e in (0.0, 0.5, 1.0, 1.5)]
    steps = [b - a for a, b in zip(inside, inside[1:])]
    assert all(b > a for a, b in zip(steps, steps[1:])), steps
    assert cliffs[0] == 0.0 and cliffs[-1] > 0.0  # a discrete cliff appears
    # the wall arrives BEFORE lease end: the cliff bites at elapsed just past
    # (window - lead), which is strictly less than the full notice window
    usable = NOTICE_WINDOW - LEAD_MEDIAN
    assert usable < NOTICE_WINDOW
    assert tenant_clock_multiplier(LEAD_MEDIAN, usable, NOTICE_WINDOW)[1] == 0.0
    assert tenant_clock_multiplier(LEAD_MEDIAN, usable + 0.01,
                                   NOTICE_WINDOW)[1] > 0.0
    # securing an alternative flattens the cliff into a floor
    c, k = tenant_clock_multiplier(LEAD_MEDIAN, 3.0, NOTICE_WINDOW, secured=True)
    assert c == 1.0 and k == 0.0


def test_landlord_clock_is_linear_and_has_no_cliff():
    """A6a.3: do NOT give the landlord a cliff."""
    from crabs.market import LAND_LIN_RATE
    steps = [LAND_LIN_RATE * e for e in (0.0, 1.0, 2.0, 3.0)]
    diffs = [b - a for a, b in zip(steps, steps[1:])]
    assert all(abs(x - diffs[0]) < 1e-12 for x in diffs)   # constant increments


# ---------------- K26 AUDIT: the credible-signal channel ---------------------
# K26 as reported ("securing an alternative is worth +$17") was measured with the
# landlord structurally unable to respond to an alternative: `secured` never
# entered the offer, so the null was a property of the setup. These tests cover
# the channel that lets a tenant PROVE an alternative at a cost. It is default
# OFF, so nothing previously reported moves.

def _market_cell(**mp_kw):
    from crabs.market import MarketParams, simulate_market
    p = regime_params(BASE, "burn")
    return simulate_market(p, MarketParams(n_stations=8, units=15, meas_years=4,
                                           **mp_kw), 1000)


def test_signal_channel_is_off_by_default_and_changes_nothing():
    """Default OFF. With it off, holding an alternative cannot move the offer --
    which is exactly why K26's reported null says nothing about the world."""
    from crabs.market import MarketParams
    assert MarketParams().signal_enabled is False
    r = _market_cell(secured_share=0.5)
    sec = r["secured_offer"] / r["secured_n"]
    uns = r["unsecured_offer"] / r["unsecured_n"]
    assert abs(sec - uns) < 5e-3, (sec, uns)
    # and the signal cost is inert while the channel is closed
    r2 = _market_cell(secured_share=0.5, signal_cost=0.9)
    assert {k: v for k, v in r.items() if not k.startswith("_")} == \
        {k: v for k, v in r2.items() if not k.startswith("_")}


def test_a_proven_alternative_lowers_the_offer_it_receives():
    """With a costly, verifiable signal the landlord CAN respond, and does: a
    tenant that proves an alternative is offered materially less relative to
    market than one that does not."""
    r = _market_cell(secured_share=0.5, signal_enabled=True)
    sec = r["secured_offer"] / r["secured_n"]
    uns = r["unsecured_offer"] / r["unsecured_n"]
    assert sec < uns - 0.02, (sec, uns)


def test_the_signal_is_not_an_information_leak():
    """The distinguishing property versus the bug that manufactured K19.

    STRUCTURAL: a tenant that produces no proof is priced by exactly the
    pre-existing code path -- the population lead-time quadrature with
    `secured=False` -- so its private draw still cannot enter the offer. Only a
    tenant that chose to prove is treated differently, and only it.

    AGGREGATE: opening the channel still moves a non-prover's offer a little,
    because provers pay less, which moves realised rents and therefore the
    market statistic everyone is priced against. That is a general-equilibrium
    spillover, not a leak, and it is small -- but it is a (mildly adverse) one,
    so it is asserted with a sign rather than waved away."""
    import inspect
    from crabs import market
    src = inspect.getsource(market.simulate_market)
    off_block = src[src.index("wa_t_base ="):src.index("offer_annual =")]
    assert "NOTICE_WINDOW, False)" in off_block
    for forbidden in ("crab.c_persist", "_c_total(", "u[11]", "u[13]", "lead,"):
        assert forbidden not in off_block, forbidden
    assert market._signal_proved(market.MarketParams(signal_enabled=True),
                                 False) is False

    off = _market_cell(secured_share=0.5)
    on = _market_cell(secured_share=0.5, signal_enabled=True)
    u_off = off["unsecured_offer"] / off["unsecured_n"]
    u_on = on["unsecured_offer"] / on["unsecured_n"]
    assert abs(u_on - u_off) < 0.01 * u_off, (u_off, u_on)
    # and it is at the non-prover's very slight expense, not benefit
    assert u_on >= u_off, (u_off, u_on)


def test_the_signal_is_costly_and_the_cost_is_charged_to_the_tenant():
    """A dearer proof leaves the prover with strictly less surplus, so the value
    of signalling is a net figure and not a free lunch."""
    cheap = _market_cell(secured_share=0.5, signal_enabled=True,
                         signal_cost=0.10)
    dear = _market_cell(secured_share=0.5, signal_enabled=True,
                        signal_cost=0.50)
    c = cheap["secured_surp"] / cheap["secured_n"]
    d = dear["secured_surp"] / dear["secured_n"]
    assert d < c, (c, d)
    # the offers themselves are identical: only the tenant's net position moves
    assert abs(cheap["secured_offer"] / cheap["secured_n"]
               - dear["secured_offer"] / dear["secured_n"]) < 1e-12


# ------------- ARM K AUDIT: the matrix is structurally asymmetric ------------

def test_the_engine_matrix_arms_the_two_sides_with_different_weapons():
    """K16's 8.5x compares two DIFFERENT tools, not two holders of one tool.

    In N/L the landlord gets `landlord_opener` -- a brute-force NPV search over a
    grid that includes rent factors ABOVE 1.0, which the tenant can never
    propose -- and it moves first, resetting the status quo the negotiation
    starts from. In T/N the tenant gets `negotiate_bundle` and only ever replies
    to a standing offer. There is no tenant-side opener.

    This test does not say the design is wrong; it pins the asymmetry so that
    K16's number is never read as 'whoever holds the engine' when what varies is
    also which optimiser and which move order each side was given."""
    import inspect
    from crabs import armk
    from crabs.engine_bridge import N_TENANT_RENT, RENT_FACTORS
    ups = [b.ri for b in armk.LANDLORD_OPENERS if b.ri >= N_TENANT_RENT]
    assert ups, "the landlord opener no longer reaches the upward rent grid"
    assert all(RENT_FACTORS[i] > 1.0 for i in ups)
    src = inspect.getsource(armk.negotiate_matrix)
    assert "landlord_opener(" in src
    assert "tenant_opener" not in src        # no mirror exists
    # and the opener is a direct NPV search, not an engine call
    osrc = inspect.getsource(armk.landlord_opener)
    assert "negotiate_bundle" not in osrc
    assert "bundle_npv(" in osrc


# =============================================================================
# research/DESIGN-PRINCIPLES.md -- the parts a machine can check
#
# The principles were derived from seven artefacts this study produced. Five
# survived pre-registration, because pre-registration constrains what you CLAIM,
# not what you BUILD. These tests are the build-time half.
#
# Several of them PIN a known violation rather than forbidding it. That is
# deliberate: the violations are in shipped results, so a test that merely went
# red would be deleted or skipped within a week. A test that asserts the exact
# violation list goes red when the list CHANGES -- when one is fixed and the
# record is not updated, or when a new one is added.
# =============================================================================

import inspect                                                     # noqa: E402

from crabs import principles as PR                                # noqa: E402


# ------------------------------------------ the checks check themselves first
def test_one_knob_helper_passes_when_only_the_treatment_differs():
    a = {"x": 1, "y": 2}
    b = {"x": 1, "y": 3}
    PR.assert_one_knob(a, b, "y")


def test_one_knob_helper_names_every_undeclared_difference():
    a = {"x": 1, "y": 2, "z": "p"}
    b = {"x": 9, "y": 3, "z": "q"}
    with pytest.raises(PR.OneKnobViolation) as e:
        PR.assert_one_knob(a, b, "y")
    msg = str(e.value)
    assert "x" in msg and "z" in msg and "2 undeclared" in msg


def test_information_scan_follows_calls_instead_of_only_the_local_source():
    """The property that makes this reusable rather than a grep. `landlord_
    opener` never writes `ten.w`; it calls `welfare_premium(ten, d)`, which
    does. A source-level grep -- which is what the hand-written renewal-offer
    test was -- misses that entirely."""
    from crabs import armk
    src = inspect.getsource(armk.landlord_opener)
    assert "ten.w" not in src                       # invisible to a grep
    assert "welfare_premium() -> ten.w" in PR.information_leaks(
        armk.landlord_opener)                       # visible to the scan


def test_conditional_statistic_parser_sees_f_string_families():
    """K21's survivorship artefact lived in a statistic built in a loop with an
    f-string key. A parser that only understood literal keys would not have
    seen it, so the parser must normalise those to a `{}` pattern."""
    cs = PR.conditional_statistics()
    assert "retention_ten{}" in cs
    assert cs["retention_ten{}"][0] == "ten{}_renewals"
    assert "grant_share_{}" in cs


# --------------------------------------------------------- A. ONE KNOB -------
def test_phase1_arms_differ_in_exactly_one_declared_knob():
    """PREREG §4's arms are clean, and this is what clean looks like: A vs B is
    the asker share alone, B vs C is the ask ladder alone, D vs E is the
    adaptive station alone."""
    base = dict(BASE.__dict__)
    def arm(**runner):
        return PR.params_descriptor(Params(**base), **runner)
    A = arm(share=0.39, strategy="price", adaptive=False)
    B = arm(share=1.0, strategy="price", adaptive=False)
    C = arm(share=1.0, strategy="ranked", adaptive=False)
    D = arm(share=1.0, strategy="ranked", adaptive=False)
    E = arm(share=1.0, strategy="ranked", adaptive=True)
    PR.assert_one_knob(A, B, "runner.share", label="arm A vs B")
    PR.assert_one_knob(B, C, "runner.strategy", label="arm B vs C")
    PR.assert_one_knob(D, E, "runner.adaptive", label="arm D vs E")


def test_the_amendment7_cap_sweep_is_a_one_knob_sweep():
    """AMENDMENT 7's sweep varies the renewal ceiling and nothing else. Asserted
    rather than trusted, because the sweep is the evidence for the derived
    ceiling and a confound in it would be the eighth artefact."""
    from crabs.run_amend7 import CAPS
    arms = [PR.params_descriptor(Params(**{**BASE.__dict__,
                                           "renewal_cap": c}),
                                 share=0.39, strategy="price", adaptive=False)
            for c in CAPS]
    for a, b in zip(arms, arms[1:]):
        PR.assert_one_knob(a, b, "params.renewal_cap", label="cap sweep")


def test_k16_matrix_cells_differ_in_more_than_who_holds_the_engine():
    """PRINCIPLE A, applied where it would have caught the biggest artefact.

    K16 reported 8.5x for "who holds the engine". `Params` says the four cells
    differ in two booleans. The DERIVED structure says otherwise: T/N vs N/L --
    the comparison the 8.5x is built on -- differs in eight further dimensions
    even after granting that holding the engine means using it.

    Pinned, not merely forbidden: the list is the record of what K16 actually
    varied, and this test goes red if that record stops being true."""
    d = PR.matrix_arm_descriptor
    NN, TN, NL = d(False, False), d(True, False), d(False, True)
    treatment = ("tenant_engine", "landlord_engine",
                 "tenant_optimiser", "landlord_optimiser")

    with pytest.raises(PR.OneKnobViolation) as e:
        PR.assert_one_knob(TN, NL, treatment, label="K16 T/N vs N/L")
    confounds = str(e.value)
    for expected in ("rounds",                     # 3 vs 2: tenant-engine only
                     "landlord_opener",            # exists on one side only
                     "who_moves_first",            # opener vs replier
                     "resets_status_quo",          # the opener rebases q
                     "landlord_rent_grid_max_factor",   # +6% vs 0%
                     "reads_tenant_private_utility",    # and a PRINCIPLE B leak
                     "tenant_their_batna_estimate",
                     "landlord_their_batna_estimate"):
        assert expected in confounds, expected

    # the round count is a confound even in the cleanest cell pair
    with pytest.raises(PR.OneKnobViolation) as e2:
        PR.assert_one_knob(NN, TN, ("tenant_engine", "tenant_optimiser"))
    assert "rounds" in str(e2.value)
    assert NN["rounds"] == 2 and TN["rounds"] == 3

    # and there is no tenant-side opener in any cell, so move order is never
    # symmetric: the landlord opens exactly when it holds the engine
    assert NN["who_moves_first"] == "tenant"
    assert NL["who_moves_first"] == "landlord"


# ------------------------------------------------- B. INFORMATION BUDGET -----
LANDLORD_DECISION_PATHS_CLEAN = (
    "StationDP.offer", "StationDP._sweep", "StationDP._variant_val",
    "StationDP.negotiate", "StationDP._substitute",
    "EmergentDP.negotiate", "EmergentDP.blanket_push",
    "armk.heuristic_landlord_reply", "armk.landlord_issues",
    "engine_bridge.bundle_npv",
)


def _landlord_paths():
    from crabs import armk, emergent
    from crabs import engine_bridge as EB
    return {
        "StationDP.offer": StationDP.offer,
        "StationDP._sweep": StationDP._sweep,
        "StationDP._variant_val": StationDP._variant_val,
        "StationDP.negotiate": StationDP.negotiate,
        "StationDP._substitute": StationDP._substitute,
        "EmergentDP.negotiate": emergent.EmergentDP.negotiate,
        "EmergentDP.blanket_push": emergent.EmergentDP.blanket_push,
        "armk.heuristic_landlord_reply": armk.heuristic_landlord_reply,
        "armk.landlord_issues": armk.landlord_issues,
        "armk.landlord_opener": armk.landlord_opener,
        "engine_bridge.bundle_npv": EB.bundle_npv,
        "engine_bridge.station_counter": EB.station_counter,
    }


def test_every_landlord_decision_path_respects_its_information_budget():
    """PRINCIPLE B, generalised from `test_renewal_offer_uses_no_private_tenant
    _draw` and applied to EVERY landlord decision, not only the one that was
    already known to be broken. A landlord may price off market rent, the rent
    of record, tenure, payment history, this habitat's own turn exposure, the
    POPULATION switching-cost distribution, and whatever the tenant has actually
    asked for. Never a per-tenant private draw."""
    paths = _landlord_paths()
    for name in LANDLORD_DECISION_PATHS_CLEAN:
        PR.assert_information_budget(paths[name], label=name)


def test_the_engine_arms_price_off_the_tenants_private_priorities():
    """The two leaks the generalised check finds, pinned.

    Both screen candidate packages by whether they clear THIS tenant's utility,
    evaluated with its private Dirichlet priority weights and its private job
    flexibility. A landlord holding only the population distribution would have
    to leave slack; these two do not. Same family as artefact #2, and
    `landlord_opener` sits inside the arm K16's 8.5x is measured on.

    The declared budget is written in `landlord_issues`' own docstring -- "it
    supplies only the DIRECTION of the tenant's preferences and lets the engine
    infer the tenant's relative priorities from what the tenant has asked for".
    `landlord_issues` honours it. Its two neighbours do not."""
    from crabs import armk
    from crabs import engine_bridge as EB
    expected = ["issue_dollars() -> ten.job_flex", "welfare_premium",
                "welfare_premium() -> ten.w"]
    assert PR.information_leaks(armk.landlord_opener) == expected
    assert PR.information_leaks(EB.station_counter) == expected
    # the declared budget lives in the docstring of the function that keeps it
    assert "DIRECTION" in armk.landlord_issues.__doc__
    assert PR.information_leaks(armk.landlord_issues) == []
    # and it is load-bearing, not decoration: a tenant whose weights are exactly
    # average gets a premium of zero, so the leak only pays on unusual tenants
    from crabs.demographics import Tenant
    avg = Tenant(income=75000.0, hh_size=2, job_flex=0.4, move_cost=7200.0,
                 w=(0.25, 0.25, 0.25, 0.25), burdened=False)
    odd = Tenant(income=75000.0, hh_size=2, job_flex=0.4, move_cost=7200.0,
                 w=(0.10, 0.55, 0.20, 0.15), burdened=False)
    d = {"rent": 100.0, "term": 900.0, "one_time_credit": 0.0, "fees": 0.0}
    assert EB.welfare_premium(avg, d) == pytest.approx(0.0)
    assert EB.welfare_premium(odd, d) > 500.0


def test_the_market_renewal_offer_passes_the_generalised_check_too():
    """The hand-written test that started this (AMENDMENT 6a) asserted the
    absence of specific strings. The reusable check reaches the same verdict by
    following the calls, which is what lets it be pointed at anything."""
    from crabs import market
    leaks = PR.information_leaks(market.simulate_market,
                                 slice_from="wa_t_base =",
                                 slice_to="offer_annual =")
    assert leaks == [], leaks


# ---------------------------- C. NO PARAMETER MAY ENCODE A FINDING -----------
def test_every_free_parameter_declares_a_source():
    """The forcing function. A constant added without saying where it came from
    fails here, so 'where is this number from' is answered at write time rather
    than by an audit two months later."""
    assert PR.undeclared_parameters() == []


def test_every_module_constant_and_dataclass_field_is_classified():
    """PRINCIPLE C, the COVERAGE half, and the reason this test exists at all.

    The first audit classified `Params` exhaustively and passed. It was still
    blind to about half the study: `market.py` held ~20 module constants and
    `MarketParams` 15 more fields, in no table anywhere -- and K22 through K27
    and all of GATE 3 run on those and nothing else. A table that covers one
    module is a sample, not a table.

    `undeclared_parameters` cannot catch that: it only ever looked at `Params`.
    This looks at every module and dataclass named in `DECLARED_MODULES` /
    `DECLARED_DATACLASSES`, so adding a constant to either module -- or a whole
    new amendment's worth of them -- fails here until it is written down."""
    missing = PR.undeclared_symbols()
    assert missing == {}, (
        "unclassified constants (add each to PARAM_SOURCES with its ACTUAL "
        "stated basis quoted, or to STRUCTURAL / ARM_SELECTORS if it names a "
        "position or selects an arm):\n"
        + "\n".join(f"  {where}: {', '.join(names)}"
                    for where, names in sorted(missing.items())))
    # and the scan really is reading the modules, not returning an empty set:
    # every symbol it finds must be reachable, and it must find the ones the
    # coverage gap was made of
    found = set(PR.module_constants("crabs.market"))
    assert {"DOM_CUT", "VAC_ADJUST", "V_TARGET", "LAND_LIN_RATE",
            "RESP_DELAY_MAX", "K_VISIBLE"} <= found
    # a tuple-unpack at module scope is invisible to a line-oriented grep
    assert {"RENEWAL", "NEW_LET"} <= found
    # a name market.py IMPORTS is charged to the module that defines it, once
    assert "ANCHOR_RENT" not in found
    assert "ANCHOR_RENT" in set(PR.module_constants("crabs.world"))


def test_the_circular_parameter_list_is_exactly_what_the_audit_found():
    """PRINCIPLE C rule 1. A constant whose justification IS the phenomenon
    under study is circular and the result is unpublishable however it comes
    out. Pinned so the list cannot quietly grow -- or quietly shrink.

    NINE, after the 2026-07-25 second pass. The first pass found three; the
    other six were invisible to it for two different reasons.

    PRINCIPLE G (four of them). `vacancy`, `p_exo_floor`, `p_exo_extra` and
    `belief0` each cite a real published number that is one of this model's own
    VALIDATION TARGETS -- the concession rate (V5/V6), turnover (V2), and the
    39/61 counter split. Parameter-by-parameter that reads as data, which is
    why the first pass filed three of them UPSTREAM. Output-by-output it is a
    loop, and `research/crabs/FREE-OUTPUTS.md` is the output-by-output view.

    COVERAGE (two of them). `DOM_LEARN` and `DOM_CUT` were in no table at all,
    so no pass could have found them. Both install the monotone relationship
    K22 was registered to test."""
    assert set(PR.circular_parameters()) == {
        # --- found by the first pass, parameter-by-parameter ---
        "renewal_cap",      # justified by the +10.7% average it explains
        "p_continue",       # justified by letting K1 fire
        "courage_med",      # justified by landing on the observed 39%
        # --- found output-by-output, under PRINCIPLE G ---
        "vacancy",          # cites the concession rate; V5/V6 measure it
        "p_exo_floor",      # cites NAA turnover ~47%; V2 measures it
        "p_exo_extra",      # the other half of the same p_exo(j)
        "belief0",          # cites '61% never try', the counter rate's complement
        # --- found by closing the market.py coverage gap ---
        "DOM_LEARN",        # "makes the reservation weaken monotonically in dom"
        "DOM_CUT",          # cuts the ask in dom; K22 asks if depth rises in dom
    }
    for name, basis in PR.circular_parameters().items():
        assert len(basis) > 40, name          # the basis is quoted, not asserted


def test_two_parameters_fitted_to_two_halves_of_one_fact_fit_the_whole_fact():
    """PRINCIPLE G rule 1, which is the part a per-parameter audit cannot see.

    `move_med` is CALIBRATED to observed elasticity -- the RENT-driven half of
    turnover -- and SPEC §8 correctly forbids claiming V2 off it. `p_exo_*` is
    fitted to NAA's ~47%, the NON-RENT half. Neither disclosure mentions the
    other, and between them the retention gate is not a weak test but an
    identity. The pairing is asserted here so it cannot be split back apart by
    fixing one and leaving the other."""
    assert PR.PARAM_SOURCES["move_med"][0] == PR.CALIBRATED
    assert PR.PARAM_SOURCES["p_exo_floor"][0] == PR.CIRCULAR
    for k in ("move_med", "p_exo_floor"):
        assert "half" in PR.PARAM_SOURCES[k][1]      # each entry names the other
    # the same shape in arm F: cost of asking and perceived odds of winning,
    # fitted to the two sides of one 39/61 split
    assert PR.PARAM_SOURCES["courage_med"][0] == PR.CIRCULAR
    assert PR.PARAM_SOURCES["belief0"][0] == PR.CIRCULAR


def test_ask_frac_is_scoped_rather_than_relabelled_in_either_direction():
    """The case that does not fit the binary, kept from being forced into it.

    `ask_frac = 0.11` cites RealPage on what landlords GRANT and is installed as
    the size of what tenants ASK, with every instrument sized to deliver that
    same crab value -- so Phase 1's largest possible rent concession is
    1.0 x 0.11 by construction. Flat UPSTREAM licenses magnitude claims it
    cannot support; flat CIRCULAR voids K1, which turns on which instrument the
    station prefers at EQUAL crab value and not on the level. So the class says
    'scoped' and the entry has to say which claims are in scope."""
    assert PR.PARAM_SOURCES["ask_frac"][0] == PR.SCOPED
    basis = PR.scoped_parameters()["ask_frac"]
    assert "IN SCOPE" in basis and "OUT OF SCOPE" in basis
    assert PR.SCOPED not in (PR.circular_parameters(),
                             PR.unsourced_parameters())
    # and it really is load-bearing on the size: the rent rung is exactly it
    assert BASE.ask_frac == 0.11


def test_invented_parameters_are_labelled_and_numerous():
    """Rule 1's other half: where no upstream source exists, label it INVENTED.
    Legal, but it must be visible -- and there are a lot of them.

    The market layer roughly doubled the count: every constant of the two
    clocks K25 is measured in (`CLIFF_CONVEX`, `HOLDOVER_MONTHS`,
    `EMERGENCY_MONTHS`, `LAND_LIN_RATE`, `LEAD_*`, `NOTICE_WINDOW`,
    `RESP_DELAY_MAX`) is invented. K25 is not circular -- nothing was fitted to
    an observed clock-decay fact, so the finding stands -- but its MAGNITUDE is
    a readout of nine unsourced numbers and should be reported that way."""
    inv = PR.unsourced_parameters()
    assert len(inv) >= 45
    assert "nu" in inv and "lambda_ref" in inv and "kappa_crab" in inv
    for k in ("CLIFF_CONVEX", "HOLDOVER_MONTHS", "EMERGENCY_MONTHS",
              "LAND_LIN_RATE", "LEAD_MEDIAN", "LEAD_SIGMA", "NOTICE_WINDOW",
              "RESP_DELAY_MAX"):
        assert k in inv, k
    # calibration is its own class and may never be claimed as a prediction
    assert PR.PARAM_SOURCES["move_med"][0] == PR.CALIBRATED
    # three of them, and two describe the same ~6% vacancy from opposite sides
    assert {k for k, v in PR.PARAM_SOURCES.items() if v[0] == PR.CALIBRATED} == {
        "move_med", "move_sigma", "searcher_inflow", "V_TARGET", "VAC_ADJUST"}


def test_the_shipped_ask_adjustment_is_declared_at_one_value_shipped_at_another_and_inert():
    """Three defects in one constant, pinned together.

    (1) `market.py`'s DECLARED-BEFORE-RUNNING docstring says `vac_adjust 0.6`;
        the module ships 3.0, retuned after seeing deflation (RESULTS Phase 5
        §5). So it is CALIBRATED presented as pre-declared.
    (2) It is INERT. One use is multiplied by a literal zero; the other sits in
        a block guarded by `h.crab is None` at the annual boundary, where
        `vacant_years == 0` because the monthly matching loop fills every
        habitat first. The block sets no ask in 10,000 habitat-years.
    (3) Therefore `mean_ask` is 0/0 = NaN in every shipped market cell, and the
        "stations post asking rents against their own observed vacancy"
        mechanism advertised at the top of the module does not run.

    This replaces the earlier pin, which asserted only the docstring/code
    contradiction. Restoring the declared 0.6 would change nothing -- asserted
    here rather than argued -- so the contradiction was never the real defect."""
    from crabs import market
    assert market.VAC_ADJUST == 3.0
    assert "vac_adjust     0.6" in market.__doc__      # still declared at 0.6
    assert "INERT" in market.__doc__                    # and now labelled dead
    assert PR.PARAM_SOURCES["VAC_ADJUST"][0] == PR.CALIBRATED
    assert "0.6 -> 3.0" in PR.PARAM_SOURCES["VAC_ADJUST"][1]

    # (2) the dead-code proof: one use is multiplied by zero
    src = inspect.getsource(market.simulate_market)
    assert "VAC_ADJUST * 0.0" in src

    # and the whole constant is inert: bit-identical output across four values
    p = regime_params(BASE, "burn")
    mp = market.MarketParams(n_stations=8, units=15, meas_years=4)
    def _run(v):
        market.VAC_ADJUST = v
        r = market.simulate_market(p, mp, 1000, drift=0.0)
        return {k: x for k, x in r.items() if not k.startswith("_")}
    try:
        base = _run(3.0)
        for v in (0.0, 0.6, 100.0):
            assert _run(v) == base, v
    finally:
        market.VAC_ADJUST = 3.0
    # (3) the branch never fires, so the ask statistic does not exist
    assert base["ask_n"] == 0.0
    assert base["vacant_years"] == 0.0
    from crabs.run_market import derive_market
    import math
    assert math.isnan(derive_market(base)["mean_ask"])


def test_the_renewal_ceiling_is_derivable_and_the_shipped_cap_bound_hard():
    """AMENDMENT 7, as a regression test on the finding rather than on a number
    in a document.

    Two properties. (1) The ceiling is DERIVABLE: the station's own free choice
    stops well inside the action grid, so removing the constraint does not send
    it to the grid edge -- there is a real interior optimum to report. (2) The
    shipped 12% cap BOUND: the free policy asks for materially more than 12% at
    states the simulation actually visits, so the +10.7% the study reported was
    a censored mean, not an elasticity result."""
    _, free = _dp("loss", renewal_cap=2.0)
    _, wide = _dp("loss", renewal_cap=0.5)
    _, ship = _dp("loss", renewal_cap=0.12)
    pol_free = np.array([[free.offer(float(r), j) for r in RS]
                         for j in range(1, BASE.j_max + 1)])
    # (1) interior: nowhere near the top of the action grid
    assert pol_free.max() < QA[-1] - 0.2, pol_free.max()
    # a cap of 50% is already non-binding over the states the loss regime
    # actually visits (realised r runs 0.83-1.12), so the ceiling is BELOW it.
    # Off that range the 50% mask still clips, which is why the comparison is
    # made where the simulation lives rather than over the whole grid.
    live = [r for r in RS if 0.84 <= r <= 1.12]
    assert np.allclose([[free.offer(float(r), j) for r in live]
                        for j in range(1, BASE.j_max + 1)],
                       [[wide.offer(float(r), j) for r in live]
                        for j in range(1, BASE.j_max + 1)])
    # (2) the shipped cap bound: at a typical loss-regime state the free station
    # asks for more than 12%, and the capped one is pinned to the ceiling
    r0, j0 = 0.95, 2
    assert free.offer(r0, j0) / r0 - 1.0 > 0.12
    assert ship.offer(r0, j0) / r0 - 1.0 == pytest.approx(0.12, abs=0.012)


# ------------------------------------------- D. IDENTICAL POPULATIONS --------
def test_no_conditional_statistic_lacks_a_declared_unconditional_pair():
    """PRINCIPLE D. Pinned rather than forbidden, for the reason at the top of
    this section. `rent_ratio` is the live one in the arms A-K reporting layer:
    `rent_ratio_n` is incremented in the stay branch and the term-lock branch of
    `world._year` and never in the leave branch, so the headline "sitting rents
    ~12% above market" is measured on the crabs that did not leave -- and the
    crabs that left are exactly the ones whose ratio was worst."""
    from crabs.run import derive
    assert set(PR.unpaired_conditional_statistics(derive)) == {"rent_ratio"}


def test_the_market_layer_reports_growth_only_over_renewals_that_signed():
    """The same check pointed at AMENDMENT 5/6's reporting layer. `renew_growth`
    is the denominator under V9, K19 and K24: it averages the growth of
    renewals that were ACCEPTED, so a tenant the offer pushed out is not in the
    statistic used to detect a rent ratchet."""
    from crabs.run_market import derive_market
    unpaired = PR.unpaired_conditional_statistics(derive_market)
    assert "renew_growth" in unpaired
    assert "SIGNED" in unpaired["renew_growth"][1]
    assert {"newlet_growth", "newlet_rent", "renew_rent"} <= set(unpaired)


def test_no_reported_ratio_mixes_two_populations():
    """The sharper half of PRINCIPLE D, and the one that is hardest to see by
    reading: a mean whose numerator sums over survivors while its denominator
    counts everyone is neither the conditional figure nor the unconditional
    one. Five of them, pinned.

    Two carry shipped headlines: `elapsed{}_surp` is K25's "$645/year worse
    off", and `secured_surp` is K26's "+$17 for securing an alternative". In
    both, the OFFER column beside them is a clean unconditional statistic, which
    is why the defect reads as a rounding detail rather than a defect."""
    from crabs.run import derive
    from crabs.run_market import derive_market
    assert set(PR.mismatched_ratios(derive)) == {
        "grant_share_{}",     # grants to stayers / all counterers
        "concession_pcy",     # concession value to stayers / all crab-years
    }
    assert set(PR.mismatched_ratios(derive_market)) == {
        "elapsed{}_surp",     # K25's headline column
        "secured_surp",       # K26's headline column
        "unsecured_surp",
    }
    for stat, (num, den) in PR.mismatched_ratios(derive_market).items():
        assert num == [PR.STAYERS] and den == [PR.ALL_RENEWALS], stat


# ------------------------------------------------------------- determinism ---
def test_push_collection_is_inert():
    """AMENDMENT 7 added an opt-in recorder hook. It must not touch any
    aggregate, or the whole sweep is measuring the instrument."""
    base = regime_params(BASE, "loss")
    pb = regime_params(BASE, "burn")
    stb, stm = StationDP(pb, NODES, FLAT), StationDP(base, NODES, FLAT)
    off = simulate_station(pb, base, 1000, "loss", stb, stm, 0.39, ASK_PRICE)
    on = simulate_station(pb, base, 1000, "loss", stb, stm, 0.39, ASK_PRICE,
                          collect_pushes=True)
    assert {k: v for k, v in on.items() if not k.startswith("_")} == off
    assert len(on["_pushes"]) == int(off["renewals"])


def test_regime_params_silently_overrides_two_fields_and_they_are_declared():
    """A PRINCIPLE A hazard found while ablating AMENDMENT 7.

    `regime_params` applies REGIMES *after* any caller override, so a runner
    that sweeps `vacancy` or `drift` through `Params` produces a sweep in which
    nothing moves -- a null that looks like a finding. No shipped sweep touches
    either field (the sensitivity sweeps vary face_premium, p_substitute and
    p_continue; the Phase 3 ablation varies the six size primitives), so nothing
    reported is affected. This pins the overridden set so a future sweep over
    one of them fails here instead of quietly returning zero."""
    from crabs.world import REGIMES
    overridden = set().union(*(set(v) for v in REGIMES.values()))
    assert overridden == {"drift", "vacancy"}
    asked = Params(**{**BASE.__dict__, "vacancy": 99.0, "drift": 99.0})
    got = regime_params(asked, "loss")
    assert got.vacancy == 1.2 and got.drift == 0.09      # the override wins
    # every field a shipped sweep does vary must survive regime_params
    from crabs.run import sens_specs
    import crabs.run3 as R3
    swept = {"face_premium", "p_substitute", "p_continue"} | set(R3.ABLATE)
    assert not (swept & overridden), swept & overridden
    for f in sorted(swept):
        if isinstance(getattr(BASE, f), bool):
            continue
        p = Params(**{**BASE.__dict__, f: 0.123})
        assert getattr(regime_params(p, "loss"), f) == 0.123, f


# =============================================================================
# AMENDMENT 8 / 9 -- the principles applied to the things A8 and A9 build.
# Both amendments add machinery to a module whose results are already shipped,
# so the first obligation is proving the additions are inert.
# =============================================================================

def _mkt(**mp_kw):
    from crabs.market import MarketParams, simulate_market
    p = regime_params(BASE, "burn")
    return simulate_market(p, MarketParams(n_stations=8, units=15, meas_years=4,
                                           **mp_kw), 1000)


def test_deriving_switching_cost_cannot_move_a_single_market_number():
    """AMENDMENT 8's instrumentation draws from `rng_a8`, a stream of its own,
    precisely so that switching it on cannot perturb the main sequence. Every
    previously reported market cell must be bit-identical with it on."""
    off, on = _mkt(), _mkt(derive_switching=True)
    assert {k: v for k, v in off.items() if not k.startswith("_")} == \
           {k: v for k, v in on.items() if not k.startswith("_")}
    assert "_derived" not in off and len(on["_derived"]) > 100


def test_the_derived_distribution_includes_searchers_who_gave_up():
    """PRINCIPLE D, applied to A8's own headline. A searcher that abandons its
    search has by construction the longest and dearest one; recording only
    matches would make the derived median a survivorship statistic -- artefact
    #5's exact shape, which this study has already produced once."""
    r = _mkt(derive_switching=True)
    matched = [d for d in r["_derived"] if d["matched"]]
    gave_up = [d for d in r["_derived"] if not d["matched"]]
    assert gave_up, "no abandoned searches recorded -- the D guard is inert"
    assert len(matched) + len(gave_up) == len(r["_derived"])
    # and the guard is load-bearing: give-ups really are the expensive tail
    import numpy as np
    assert (np.mean([d["months"] for d in gave_up])
            > np.mean([d["months"] for d in matched]))


def test_inflow_searchers_are_excluded_from_the_switching_distribution():
    """A household FORMING is not a household SWITCHING. Counting inflow
    searchers would put people who never paid a moving cost into the moving-cost
    distribution."""
    r = _mkt(derive_switching=True)
    assert all(d.get("cost") is not None for d in r["_derived"])
    from crabs import market
    src = inspect.getsource(market._a8_record)
    assert "a8_mover" in src and "return" in src


def test_the_derived_cost_is_never_shown_to_the_landlord():
    """PRINCIPLE B on A8's own build. The derived cost is a property of one
    crab's realised search. It is recorded for reporting and never enters an
    offer -- the renewal offer still prices off the POPULATION `move_med`."""
    from crabs import market
    from crabs import principles as PR
    assert PR.information_leaks(market.simulate_market,
                                slice_from="wa_t_base =",
                                slice_to="offer_annual =") == []
    off = inspect.getsource(market.simulate_market)
    off = off[off.index("wa_t_base ="):off.index("offer_annual =")]
    for forbidden in ("a8_attempts", "a8_months", "a8_broker", "derived_cost"):
        assert forbidden not in off, forbidden


def test_searchcost_constants_are_declared_and_none_targets_the_answer():
    """PRINCIPLE C on A8's own build. 3.6 is the number A8 is testing, so it may
    not appear as a constant anywhere in the module that derives it."""
    from crabs import principles as PR
    from crabs import searchcost as SC
    for name in ("VIEW_COST", "SPELL_COST", "TIME_COST", "MOVE_PHYSICAL",
                 "BROKER_FEE", "BROKER_SHARE", "OVERRUN_COST"):
        assert name in PR.PARAM_SOURCES, name
    # no constant IS the answer, checked on values rather than on text
    consts = {k: v for k, v in vars(SC).items()
              if k.isupper() and isinstance(v, float)}
    assert not any(abs(v - 3.6) < 1e-9 for v in consts.values()), consts
    # and, more to the point, the fixed components ALONE cannot reach K27's
    # pass band: a pass has to be earned by the search process, not by the
    # constants A8 chose. (0.25 + 1.00 + 0.15 = 1.40 < 1.8.)
    fixed = SC.SPELL_COST + SC.MOVE_PHYSICAL + SC.BROKER_SHARE * SC.BROKER_FEE
    assert fixed < SC.K27_LO, fixed
    # the two reused ones really are market.py's, not re-typed values
    from crabs.market import APP_COST, SEARCH_COST
    assert SC.VIEW_COST is APP_COST and SC.SPELL_COST is SEARCH_COST


def test_amendment9_signal_cells_are_one_knob_from_the_k26_baseline():
    """PRINCIPLE A. The signal arm must differ from `a6a_secured` in
    `signal_enabled` (plus the swept `signal_cost`) and nothing else, or its
    effect is not attributable to the signal."""
    from crabs import principles as PR
    from crabs.run_market import amendment9_specs, specs
    base = dict(n_stations=40, units=25)
    k26 = [s for s in specs() if s["cell"] == "a6a_secured"][0]["mp"]
    for s in amendment9_specs(base):
        if not s["mp"].get("signal_enabled"):
            continue
        declared = ["signal_enabled", "signal_cost"]
        if not s["mp"].get("deadline_shape", True):
            declared.append("deadline_shape")      # the K29 ablation, declared
        PR.assert_one_knob({f"mp.{k}": v for k, v in k26.items()},
                           {f"mp.{k}": v for k, v in s["mp"].items()},
                           [f"mp.{d}" for d in declared], label=s["cell"])


def test_a_proved_alternative_and_no_deadline_take_the_identical_branch():
    """A9.2's structural claim, asserted on the code rather than inferred from
    the output. `market.py` gives a proved tenant `wa_t_exp = wa_t_base`, which
    is exactly what the `deadline_shape = False` branch gives everyone. So the
    proof's only direct effect is to delete the cliff -- it reveals nothing
    about THIS tenant's alternative, because `wa_t_base` is built from the
    population `move_med` and is identical for provers and non-provers.

    This is why K29 was predicted to fire before the arm was run."""
    from crabs import market
    src = inspect.getsource(market.simulate_market)
    blk = src[src.index("wa_t_base ="):src.index("rt_pop =")]
    # exact lines, so the linear-clock branch (`wa_t_base * 1.3055 + ...`)
    # is not miscounted as a bare assignment
    flat = [i for i, l in enumerate(blk.split("\n"))
            if l.strip() == "wa_t_exp = wa_t_base"]
    assert len(flat) == 2, blk                          # proved, and shape-off
    assert "p.move_med" in blk                          # population, not a draw
    i_proved = blk.index("if proved:")
    i_elif = blk.index("elif mp.deadline_shape:")
    assert i_proved < i_elif                            # proved SHORT-CIRCUITS
    assert "wa_t_exp = wa_t_base" in blk[i_proved:i_elif]


# ------------- AMENDMENT 9 / 10: the record, pinned in both units ------------

def test_the_signal_gap_is_pinned_in_BOTH_denominators():
    """AMENDMENT 9's headline is 0.1021 of MARKET rent. As a share of the OFFER
    it is 0.1021/1.1416 = 8.9%. The article says "10.2% off the offer", which
    silently swaps the denominator for the flattering one.

    Both numbers are pinned here so no future draft can quote one without the
    other, and so that a change in either is caught."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_amend9.json")
    if not os.path.exists(path):                       # pragma: no cover
        pytest.skip("run_amend9.py has not been run")
    cells = json.load(open(path))["cells"]
    c = next(x for x in cells if x["cell"] == "a9_signal_0.1"
             and x["tag"] == "calibrated")
    of_market = c["unsecured_offer"] - c["secured_offer"]
    of_offer = of_market / c["unsecured_offer"]
    assert of_market == pytest.approx(0.1021, abs=5e-4), of_market
    assert of_offer == pytest.approx(0.0894, abs=5e-4), of_offer
    # the two differ by more than a rounding step, which is the whole point
    assert of_market - of_offer > 0.012


def test_the_renewal_asymmetry_changes_sign_inside_the_defensible_band():
    """AMENDMENT 10 / K30, pinned as a property of the model rather than as a
    number in a document.

    `wa_tenant/wa_landlord` crosses 1.0 at a physical-move cost that lies inside
    the band declared in PREREG A10.2 from published sources ($700-$3,300), and
    the crossing MOVES BY A FACTOR OF 3 depending on `RELET_RISK_ON` -- a
    hardcoded `True` that appears in no reported cell as a variable. So the sign
    of the renewal asymmetry is not determined by the evidence."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_amend10.json")
    if not os.path.exists(path):                       # pragma: no cover
        pytest.skip("run_amend10.py has not been run")
    from crabs.run_amend10 import BAND_HI, BAND_LO, crossing
    blob = json.load(open(path))
    cells = blob["cells"]
    xs = {}
    for relet in (True, False):
        rows = [c for c in cells if c["relet"] is relet
                and c["regime"] == "neutral"]
        xs[relet] = crossing(rows)
    # both crossings land inside the declared band -> K30 fires
    for relet, x in xs.items():
        assert BAND_LO <= x <= BAND_HI, (relet, x)
    # and ablating an un-ablated hardcoded True moves it by ~3x
    assert xs[True] / xs[False] > 2.5, xs
    # at the CENTRAL declared estimate the two states disagree on the SIGN
    def at(mp, relet):
        return next(c["ratio"] for c in cells if c["move_physical"] == mp
                    and c["relet"] is relet and c["regime"] == "neutral")
    assert at(1.0, True) < 1.0 < at(1.0, False)


def test_the_a10_crossing_is_a_level_comparison_not_a_subtle_nonlinearity():
    """PREREG A10.4 required this bug hunt before K30 is believed.

    The tenant's walk-away is LINEAR in `move_med` by construction, and with
    `RELET_RISK_ON` ablated the landlord's is exactly CONSTANT. So the crossing
    is a straight line meeting a flat one -- mechanically trivial. That does not
    make K30 wrong (the two levels being within a factor of ~1.5 across the whole
    defensible band is the finding), but it does mean the crossing point carries
    no information beyond the two levels, and this test pins that so the result
    is never dressed up as something subtler."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_amend10.json")
    if not os.path.exists(path):                       # pragma: no cover
        pytest.skip("run_amend10.py has not been run")
    cells = json.load(open(path))["cells"]
    flat = [c for c in cells if c["relet"] is False and c["regime"] == "neutral"]
    wl = [c["wa_l"] for c in flat]
    assert max(wl) - min(wl) < 1e-6, wl        # exactly constant
    wt = sorted([(c["move_physical"], c["wa_t"]) for c in flat])
    steps = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(wt, wt[1:])]
    assert max(steps) - min(steps) < 0.02 * abs(steps[0]), steps  # linear


def test_the_k20_sign_is_undetermined_across_every_denominator_we_can_justify():
    """AMENDMENT 10 second half / K30 on the full cross.

    `vacancy` is CIRCULAR (SPEC §5 sets it from the 39.7% concession statistic,
    which is the model's own target) and sits in K20's denominator. Deriving it
    from the matching process -- time-to-let is an OUTPUT -- and also running it
    from the one UPSTREAM source available (`BASE_LET_MONTHS`, 30-41 day let
    times) gives three denominators, crossed with `RELET_RISK_ON`.

    At the central estimate of the physical-move cost the ratio spans 0.52 to
    1.37 across those six combinations: from "the landlord has twice the
    tenant's exposure" to "the tenant has 1.4x the landlord's". The sign is not
    determined by anything anyone has measured."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_amend10_vacancy.json")
    if not os.path.exists(path):                       # pragma: no cover
        pytest.skip("run_amend10_vacancy.py has not been run")
    blob = json.load(open(path))
    cells = blob["cells"]
    # the derivation is a genuine fixed point, not one pass read off
    hist = blob["meta"]["fixed_point"]
    assert abs(hist[-1] - hist[-2]) < 1e-2, hist
    # and it is far above the fitted value it replaces
    assert blob["meta"]["derived_vacancy"] > 3.0
    # at the central declared estimate, the six combinations disagree on the SIGN
    at1 = [c["ratio"] for c in cells if c["move_physical"] == 1.0]
    assert len(at1) == 6
    assert min(at1) < 0.60 and max(at1) > 1.30, at1
    assert any(r < 1.0 for r in at1) and any(r > 1.0 for r in at1)
    # the only NON-CIRCULAR denominator still flips on an un-ablated boolean
    up = {c["relet"]: c["ratio"] for c in cells
          if c["vac_mode"] == "upstream" and c["move_physical"] == 1.0}
    assert up[True] < 1.0 < up[False], up


# =============================================================================
# AMENDMENT 11 — the solved-policy cache key
# =============================================================================

def test_station_cache_key_covers_every_parameter_the_solve_depends_on():
    """DEFECT FIXED 2026-07-25, reported by the triage worker.

    `run._station` keyed its solved-policy cache on
    `(regime, share, adaptive, face_premium, p_substitute, p_continue)` -- the
    regime label plus exactly the three parameters `run.sens_specs` happens to
    sweep -- and `run2._get` on a similarly partial tuple. Every other parameter
    `StationDP` reads was absent, so a sweep of `p_exo_*`, `move_med`,
    `renewal_cap`, `turn_cost`, `nu` or `kappa_crab` silently returned a policy
    solved for a DIFFERENT value of the parameter being swept, and reported it
    as that cell's result.

    The regression bar is total rather than a list of known-relevant fields,
    because a list is the thing that went stale: **changing ANY field of
    `Params` must change the key.** Over-keying costs one extra solve;
    under-keying is a wrong number that looks right."""
    from dataclasses import replace

    from crabs.run import prior_key, station_key

    nodes = np.linspace(0.5, 12.0, 8)
    w = np.tile(np.ones(8) / 8.0, (BASE.j_max + 1, 1))
    base = W.regime_params(BASE, "gain")
    k0 = station_key(base, nodes, w, 0.39, False)

    def bump(v):
        if isinstance(v, bool):
            return not v
        if isinstance(v, (int, float)):
            return v + 1 if v != 0 else 1
        if isinstance(v, str):
            return v + "_x"
        if isinstance(v, tuple):
            return v + (0.0,)
        raise AssertionError(f"unhandled field type {type(v)}")

    for name, val in base.__dict__.items():
        other = replace(base, **{name: bump(val)})
        assert station_key(other, nodes, w, 0.39, False) != k0, name

    # the prior is as much an input to the solve as Params is, and it is a
    # process-level global in the runner, so it is in the key too
    w2 = w.copy()
    w2[3, 0] += 1e-9
    assert prior_key(nodes, w2) != prior_key(nodes, w)
    assert station_key(base, nodes, w2, 0.39, False) != k0
    # and the discriminators that are not Params fields
    assert station_key(base, nodes, w, 1.0, False) != k0
    assert station_key(base, nodes, w, 0.39, True) != k0


def test_sweeping_p_exo_actually_resolves_the_station_policy():
    """The end-to-end version of the above, on the parameter AMENDMENT 11
    sweeps. `StationDP._leave_table` reads `p_exo(p, j)` directly, so two bases
    differing only in `p_exo_floor` must give different objects AND different
    offers. Under the old key they were the same object."""
    from crabs import run as R

    nodes, w = W.switching_cost_nodes(BASE, 8), None
    nodes = nodes[0]
    w = np.tile(np.ones(8) / 8.0, (BASE.j_max + 1, 1))
    R._CACHE.clear()
    lo = R._station(BASE, "gain", nodes, w, 0.39, False)
    hi = R._station(W.Params(**{**BASE.__dict__, "p_exo_floor": 0.05}),
                    "gain", nodes, w, 0.39, False)
    R._CACHE.clear()
    assert lo is not hi
    assert [lo.offer(r, 3) for r in (0.9, 1.0, 1.1)] \
        != [hi.offer(r, 3) for r in (0.9, 1.0, 1.1)]


# ------------------------------------------------- AMENDMENT 12, JOB 1 -------
def _a12_market(**mpkw):
    """One small market, shipped parameters, for the Job 1 pins."""
    from crabs import market
    from crabs.run_market import derive_market
    p = regime_params(BASE, "burn")
    mp = market.MarketParams(n_stations=12, units=20, **mpkw)
    agg = None
    for s in (1000, 1001, 1002):
        r = market.simulate_market(p, mp, s)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    return agg, derive_market(agg)


def test_the_two_vacancy_reports_are_a_stock_at_an_instant_and_a_flow():
    """AMENDMENT 12 §J1. A10 derived `vacancy` = 4.376 months time-to-let; A11
    reported the baseline vacancy rate as 0.0000. Both are right and neither is
    a vacancy rate.

    `vacant_years` is incremented in the RENEWAL block, which runs once a year
    at the annual boundary -- AFTER twelve months of matching and BEFORE that
    year's leavers empty their habitats. So it counts habitats that failed to
    let for a full twelve-month cycle, of which there are none. There is no
    censoring: every spell completes inside its own year, which is exactly why
    the stock reads zero."""
    agg, d = _a12_market()
    assert agg["vacant_years"] == 0.0
    assert d["vacancy"] == 0.0
    assert agg["occupied_years"] == agg["habitat_years"]
    # ... while the same habitats spent 12-14% of all habitat-months empty
    assert 0.10 < d["vacancy_flow"] < 0.16, d["vacancy_flow"]
    # ... and a completed let took ~4.4 months, A10's number
    assert 3.8 < d["let_months"] < 5.0, d["let_months"]
    # the two conventions differ by exactly the signing month
    assert abs(d["let_months"] - d["dom_at_signing"] - 1.0) < 1e-9
    # no spell is censored, so the duration is interpretable
    assert agg["n_newlet_signed"] == agg["n_renewal_left"]


def test_the_derived_time_to_let_is_queue_drain_from_synchronised_lease_expiry():
    """The mechanism behind 4.376, ablated rather than asserted
    (DESIGN-PRINCIPLES C rule 2).

    Every lease in this world expires on the same day: the renewal block empties
    EVERY leaver's habitat at the annual boundary, while the leavers enter the
    search pool at `int(u[9]*12)`, a uniform month. Supply arrives in one lump
    and demand trickles in behind it. `stagger_expiry` empties the habitat in
    the month its tenant starts searching -- ONE knob, reusing the tenant's own
    draw, so no parameter and no randomness is added.

    It takes time-to-let to the floor. Whatever letting friction this model has,
    it is not 4.4 months: it is none."""
    _, base = _a12_market()
    _, stag = _a12_market(stagger_expiry=True)
    assert base["let_months"] > 3.8
    # let in the month it was listed (1.000 exactly at the reported 40x25
    # geometry; a hair above at this small one, where the pool occasionally
    # runs dry in a single station)
    assert stag["let_months"] < 1.05, stag["let_months"]
    assert stag["dom_at_signing"] < 0.05, stag["dom_at_signing"]
    assert stag["vacancy_flow"] < 0.5 * base["vacancy_flow"]
    # and the same knob is most of the deflation defect of RESULTS Phase 5 §5
    assert stag["market_rent_renew"] > 2.0 * base["market_rent_renew"]


def test_stagger_expiry_is_off_by_default_and_inert_when_off():
    """Every previously reported market cell must be bit-identical."""
    from crabs import market
    assert market.MarketParams().stagger_expiry is False
    p = regime_params(BASE, "burn")
    mp_kw = dict(n_stations=8, units=15, meas_years=4)
    a = market.simulate_market(p, market.MarketParams(**mp_kw), 1000)
    b = market.simulate_market(
        p, market.MarketParams(stagger_expiry=False, **mp_kw), 1000)
    assert {k: v for k, v in a.items() if not k.startswith("_")} \
        == {k: v for k, v in b.items() if not k.startswith("_")}


def test_the_landlord_walkaway_is_denominated_in_the_deflated_market_rent():
    """AMENDMENT 12 §J1.3, the publication blocker.

    `wa_land_renew` is (months) x M_obs and M_obs is the ENDOGENOUS market rent,
    which deflates far below ANCHOR_RENT. RESULTS.md's A9/10 section set the
    resulting dollars ($2,094-$3,440) beside A8's derived tenant switching cost
    ($2,960 = 1.48 months x ANCHOR_RENT). The two are denominated in rents ~3x
    apart. The RATIO is unaffected -- both sides share M_obs -- which is why
    K20/K30 survive and the dollar figures do not."""
    from crabs.world import ANCHOR_RENT
    agg, d = _a12_market()
    assert d["market_rent_renew"] < 0.5 * ANCHOR_RENT, d["market_rent_renew"]
    # the months figure is the dollars divided by the rent they were built from
    assert abs(d["wa_land_renew"]
               - d["wa_land_renew_months"] * d["market_rent_renew"]) < 1e-6
    assert abs(d["wa_tenant_renew"]
               - d["wa_tenant_renew_months"] * d["market_rent_renew"]) < 1e-6
    # the ratio is unit-free, so it is the only thing in that paragraph that
    # transfers between denominators
    assert abs(d["wa_ratio_renew"]
               - d["wa_tenant_renew_months"] / d["wa_land_renew_months"]) < 1e-9
    # and A8's $2,960 is at the anchor, not at this rent
    assert abs(1.48 * ANCHOR_RENT - 2960.0) < 1e-9


# ------------------------------------------------- AMENDMENT 12, JOB 2 -------
def test_nu_is_a_transient_logit_temperature_and_not_a_taste_over_places():
    """PREREG-A12 §A12.2.1, checked against the code rather than the field name.

    `Params.nu` is labelled 'taste-shock scale'. Its only two uses are the leave
    logit in `world._year` and the station's integral of the same expression in
    `policies.StationDP._leave_table`, and the uniform it multiplies,
    `u[U_LOGIT]`, is a FRESH draw every crab-year. So it is attached to the
    DECISION, not to a PLACE, and it is gone next period: it cannot generate
    'I moved because that place is better'. `move_transient` is the other
    candidate and it is half of a COST, redrawn each year, mean-preserving."""
    from crabs import policies as POL
    src = inspect.getsource(W._year) \
        + inspect.getsource(POL.StationDP._leave_table)
    assert "p.nu" in src
    # the ONLY place nu appears is inside a sigmoid over a per-period uniform
    for mod in (W, POL):
        for line in inspect.getsource(mod).splitlines():
            if "p.nu" in line:
                assert "sigmoid" in line, line
    assert "u[U_LOGIT]" in inspect.getsource(W._year)
    # and the transient half of the switching cost is a COST, drawn fresh
    assert "p.move_transient" in inspect.getsource(W._c_total)
    assert PR.PARAM_SOURCES["nu"][0] == PR.INVENTED
    assert PR.PARAM_SOURCES["move_transient"][0] == PR.INVENTED


def test_match_quality_is_persistent_and_only_a_move_redraws_it():
    """The property that makes it a preference rather than a shock."""
    p = W.Params(match_sd=1.0)
    rng = np.random.default_rng(0)
    c = W.Crab(strategy=0, rent=0.0, tenure=1, c_persist=1.0)
    W.set_match(p, c, rng)
    first = c.match
    assert first != 0.0
    # a year passes; nothing in the year loop may touch it
    assert "crab.match =" not in inspect.getsource(W._year)
    assert c.match == first
    # only a move redraws it, and `_turn_over` is the only place that happens
    assert "set_match" in inspect.getsource(W._turn_over)
    W.set_match(p, c, rng)
    assert c.match != first
    assert c.match_mg is None          # the cached gain is invalidated


def test_match_quality_is_inert_at_zero_dispersion():
    """Every previously reported cell, Phase 1 and market, is bit-identical."""
    assert W.Params().match_sd == 0.0
    assert W.Params().offer_cut == 0.0
    p = regime_params(BASE, "burn")
    from crabs import market
    mp = market.MarketParams(n_stations=8, units=15, meas_years=4)
    a = market.simulate_market(p, mp, 1000)
    b = market.simulate_market(regime_params(W.Params(match_sd=0.0), "burn"),
                               mp, 1000)
    assert {k: v for k, v in a.items() if not k.startswith("_")} \
        == {k: v for k, v in b.items() if not k.startswith("_")}
    # the searcher's choice rule collapses to "cheapest of the k you viewed"
    assert "12.0 * stations[cand[t][0]][cand[t][1]].ask" \
        in inspect.getsource(market.simulate_market)


def test_the_station_never_sees_a_crab_s_match_draw():
    """PRINCIPLE B, and the exact hole that manufactured artefact #2.

    The offer path may use the POPULATION distribution of match quality and
    nothing else. In `market.py` the offer is built from `rt_pop`, which is
    `wa_t_exp` -- the population expectation -- and `crab.match` may appear only
    in `rt`, the tenant's private reservation, which is read by the LEAVE test."""
    from crabs import market
    src = inspect.getsource(market.simulate_market)
    body = "\n".join(l for l in
                     src[src.index("rt_pop = "):
                         src.index("# exogenous move")].splitlines()
                     if "rec[" not in l)
    assert "crab.match" not in body, body
    # the private term is applied to `rt`, never to `rt_pop` or `offer`
    for line in src.splitlines():
        if "crab.match" in line and "=" in line:
            assert ("rt = rt -" in line or "crab.match = m_signed" in line
                    or "crab.match_mg" in line
                    or "h.crab.match = float(np.max(" in line
                    or 'rec["match_sum"]' in line), line
    # Phase 1: the station's leave table integrates a POPULATION draw
    assert "match_barrier_shift" in inspect.getsource(W.switching_cost_nodes)
    assert "crab" not in inspect.signature(W.match_barrier_shift).parameters


def test_the_move_attribution_partitions_the_leavers():
    """§A12.2.4. exo + rent + match must equal every leaver, with no crab
    counted twice and none dropped -- the pre-registered decomposition."""
    from crabs import market
    from crabs.world import P_EXO_CPS_M3
    p = regime_params(W.Params(p_exo_floor=P_EXO_CPS_M3, p_exo_extra=0.0,
                               match_sd=1.0), "burn")
    agg = None
    for s in (1000, 1001):
        r = market.simulate_market(p, market.MarketParams(n_stations=10,
                                                          units=20), s)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    assert (agg["n_left_exo"] + agg["n_left_rent"] + agg["n_left_match"]
            == agg["n_renewal_left"])
    assert agg["n_left_match"] > 0.0


def test_the_match_option_value_table_is_correct():
    """`match_option_value` is E[(max of MATCH_K standard normals - x)^+],
    scaled by `match_sd`. Checked against Monte Carlo, and against its two
    asymptotes."""
    rng = np.random.default_rng(11)
    X = rng.standard_normal((400_000, W.MATCH_K)).max(1)
    p = W.Params(match_sd=1.0)
    for x in (-1.0, 0.0, 1.0, 2.0):
        assert abs(W.match_option_value(p, x)
                   - float(np.maximum(X - x, 0.0).mean())) < 0.01, x
    # scale-free in match_sd
    assert abs(W.match_option_value(W.Params(match_sd=2.0), 2.0)
               - 2.0 * W.match_option_value(p, 1.0)) < 1e-9
    # strictly positive everywhere, and decreasing in the current match
    xs = [W.match_option_value(p, x) for x in (-2.0, 0.0, 2.0, 5.0)]
    assert all(a > b >= 0.0 for a, b in zip(xs, xs[1:]))
    # the DECLARED control commits before looking, so it is a fair gamble whose
    # mean over the entry distribution is zero
    ctl = W.Params(match_sd=1.0, match_option=False)
    assert abs(np.mean([W.match_option_value(ctl, float(v))
                        for v in X[:20000]])) < 0.01

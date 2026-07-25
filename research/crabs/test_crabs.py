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

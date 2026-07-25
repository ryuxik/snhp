"""The world: stations, habitats, crabs, the market-rent process, the period loop.

Space-crab flavour, sober economics. Every quantity that could scale with the
market is measured in MONTHS OF THE CURRENT EXTERNAL MARKET RENT `M_t`, which
makes the station's dynamic program scale-free (SPEC.md §1). `ANCHOR_RENT`
converts to dollars for reporting only.

Two rents, deliberately distinct:
  M_t   external market rent -- what a NEW lease signs at, here or elsewhere.
        The crab's outside option and the station's relet price.
  r     the sitting crab's rent of record, as a ratio of M_t. r > 1 is
        gain-to-lease (paying above market); r < 1 is loss-to-lease.

This module knows nothing about policy. The station object is passed in and
must expose .offer(r, j) and .negotiate(...). See policies.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

ANCHOR_RENT = 2000.0            # $/month
ANNUAL_RENT = 12 * ANCHOR_RENT  # $24,000 -- the fixed denominator for every
                                # "% of annual rent" threshold in PREREG §5

# crab strategies (PREREG §4)
NEVER_ASK, ASK_PRICE, ASK_RANKED = 0, 1, 2

# concession instruments (SPEC.md §6)
ONE_TIME, FEES, TERM, RENT = 0, 1, 2, 3
KIND_NAMES = ("one_time", "fees", "term", "rent")

# pre-drawn uniform purposes, so that arms consume identical random numbers
# for identical (station, habitat, year) cells
U_STRAT, U_CP, U_CT, U_EXO, U_LOGIT, U_TEN0 = 0, 1, 2, 3, 4, 5
U_PATIENCE = 6      # +0..3
U_SUB = 10          # +0..3
U_LOCKEXO = 14
U_RESTRAT = 15      # re-draw of the strategy trait at the burn-in boundary
U_TCOST = 16        # idiosyncratic make-ready cost of THIS habitat this year
U_VAC = 17          # idiosyncratic days-vacant exposure (season, desirability)
U_COURAGE = 18      # arm F: the cost of actually sending the message
U_MPGRANT = 19      # mom-and-pop's grant draw
U_EXODUS = 20       # the AI-crab migration's abrupt departure
U_TOOL = 21         # noise in the tool's read of the crab's own leverage
U_DEMO = 22         # 7 slots: income, hh size, job flex, Dirichlet(4)
N_UNIFORMS = 29


@dataclass(frozen=True)
class Params:
    """Every free parameter, fixed in SPEC.md before the first run."""
    # --- market process (SPEC §3) ---
    burn_years: int = 5
    meas_years: int = 4
    drift: float = 0.0              # set per regime
    sigma_burn: float = 0.020
    sigma_meas: float = 0.025
    n_stations: int = 60
    units: int = 50

    # --- station cost side (SPEC §5) ---
    turn_cost: float = 1.5          # months of market rent (NAA/IREM/BOMA)
    vacancy: float = 1.5            # months to relet; set per regime
    # Unit-level dispersion in turn exposure. ZERO in the registered
    # specification; the EXPLORATORY respecification switches it on (see
    # RESULTS.md). Make-ready cost really does range from a touch-up to a full
    # renovation, days-vacant really does swing with the expiry month, and both
    # are observable to the manager making the concession call even though the
    # revenue-management system prices the opening offer off pooled data.
    sigma_turn: float = 0.0         # lognormal sd of make-ready cost
    sigma_vac: float = 0.0          # lognormal sd of days-vacant
    turn_tenure_slope: float = 0.0  # make-ready cost x (1 + slope*ln(1+j))
    q_new: float = 0.22             # unknown-tenant credit / early-turn risk
    q_sit_tau: float = 3.0          # proven-payer premium decay (years)
    renewal_cap: float = 0.12       # max renewal increase the station will ask
    renewal_floor: float = 1.00     # non-binding. An arbitrary floor on renewal
                                    # decreases makes the value function
                                    # non-monotone in the rent of record (at high
                                    # r the station is forced to over-ask and the
                                    # crab leaves), which is an artefact, not
                                    # economics. How far it will cut is the DP's
                                    # decision, not a constraint.
    face_premium: float = 1.0       # SPEC §6 -- the parameter K1 rests on
    disc_station: float = 1.0 / 1.07
    g_long: float = 0.03            # long-run rent growth the station uses for
                                    # TERMINAL value. A regime drift of +9% is a
                                    # transient condition, not a perpetuity: at
                                    # 7% discounting, extrapolating it forever
                                    # makes a habitat worth infinity and the
                                    # value iteration diverges. Underwriters use
                                    # near-term market growth and a long-run
                                    # terminal rate; so does the station.

    # --- crab side (SPEC §4) ---
    kappa_crab: float = 1.6         # years over which a crab values a rent change
    lambda_ref: float = 0.5         # reference dependence on the increase
    nu: float = 0.60               # taste-shock scale, months
    move_med: float = 3.6           # median switching cost, months of market rent
    move_sigma: float = 0.70
    move_transient: float = 0.5     # share of switching cost redrawn each year
    attach_coef: float = 0.35       # a(j) = attach_coef * ln(1+j), months
    p_exo_floor: float = 0.24
    p_exo_extra: float = 0.18
    p_exo_tau: float = 3.0
    disc_crab: float = 1.0 / 1.12

    # --- negotiation (SPEC §7) ---
    ask_frac: float = 0.11          # RealPage Jun 2026: ~11% of annual rent
    fee_cap_frac: float = 0.04      # ancillary fees ~4% of annual rent
    term_cap: float = 0.08
    p_continue: float = 0.60        # station patience per additional round
    p_substitute: float = 0.35      # chance it volunteers a cheaper instrument
    break_fee: float = 2.0          # months, to break a term lock
    break_damp: float = 0.5         # lock damps the exogenous move hazard
    grant_menu: tuple = (1.0, 0.6, 0.3)

    # --- arm F: broadcast (AMENDMENT 1 §A1.2) ---
    courage_med: float = 0.18       # months of market rent (=$360). The cost of
                                    # sending the message at all -- the article's
                                    # courage problem. Set so that at the
                                    # pessimistic prior belief the endogenous
                                    # counter rate lands near the observed 39%.
    courage_sigma: float = 0.80
    belief0: float = 0.10           # prior P(concession | ask): 61% never try
    learn_rate: float = 0.40        # weight on new evidence
    belief_lo: float = 0.01
    belief_hi: float = 0.95
    ask_scale_lo: float = 0.20
    ask_scale_hi: float = 1.50

    # --- AMENDMENT 2 §A2.1: primitives. Landlord types differ ONLY through
    # portfolio size `units`; every behavioural difference below is DERIVED from
    # it by a stated mechanism, never set per type. All default to
    # Phase-1-neutral so Phase 1 stays reproducible from this same code.
    risk_rho: float = 0.0           # CRRA over TOTAL owner income. Per-unit risk
                                    # penalty = rho*Var/(2*U*12): with U roughly
                                    # independent units, CE = U*mu - (rho/2)*sig^2/mu,
                                    # so per unit the penalty falls as 1/U. One
                                    # vacancy is 0.5% of a 200-unit revenue line
                                    # and 20% of a 5-unit one.
    comp_sigma0: float = 0.0        # comp noise sd = comp_sigma0/sqrt(U). You
                                    # learn the market from your own relets; 200
                                    # habitats give ~90 a year, 5 give ~2.
    comp_nodes: int = 5             # Gauss-Hermite nodes for the comp integral
    nonpec0: float = 0.0            # months/yr of non-pecuniary value in keeping
    raise_cost0: float = 0.0        # months, fixed cost of raising rent at all
    u_personal: float = 10.0        # both scale as 1/(1+U/u_personal): you can
                                    # personally know about ten tenants
    turn_scale_beta: float = 0.0    # turn cost x (1 + beta/sqrt(U)): an in-house
                                    # crew amortises; a small owner calls someone
    u_cap: float = 50.0             # face-rent capitalisation x U/(U+u_cap):
    size_scaled_face: bool = False  # institutional portfolios are marked to an
                                    # NOI multiple, a five-unit owner is not
    agent_bonus: float = 0.0        # months of rent the LEASING AGENT privately
    u_agent: float = 20.0           # gains per retained tenant, weighted
                                    # U/(U+u_agent): a small owner IS the agent

    # --- AMENDMENT 2 §A2.2: mechanism switches, one arm at a time ---
    menu_costs: bool = False        # arm G: blanket policy + exception queue
    queue_frac: float = 0.15        # exception capacity as a share of habitats
    blanket_grid: tuple = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12)
    ask_mode: str = "assigned"      # arms H/I: assigned | tool | everyone |
                                    # random_at | selfselect
    engage_margin: float = 2.0      # months; selfselect asks when within this of
                                    # indifference about leaving
    no_concessions: bool = False    # arm I control: the channel does not exist
    tool_noise: float = 0.0         # months of error in the tool's leverage read

    # --- AMENDMENT 3 §A3.1: which negotiator actually runs on the crab's side ---
    negotiator: str = "ladder"      # ladder        = Phase 1's hand-rolled ladder
                                    # engine_bundle = the REAL negotiate_bundle
                                    # engine_single = the REAL negotiate_turn on
                                    #                 rent alone (the control)
                                    # matrix        = AMENDMENT 4's 2x2
    tenant_engine: bool = False     # arm K: does the TENANT hold SNHP
    landlord_engine: bool = False   # arm K: does the LANDLORD hold SNHP
    drop_term: bool = False         # diagnostic: remove the term issue, to test
                                    # whether one trade is the whole story
    ladder_continues: bool = False   # FAIRNESS DIAGNOSTIC: Phase 1's ladder
                                    # stopped at the first yes, so it could only
                                    # ever win ONE instrument while a bundle wins
                                    # several. This lets the ladder keep going,
                                    # which is the like-for-like comparison.

    # --- grids ---
    j_max: int = 8                  # tenure buckets, 8 absorbing


REGIMES = {
    "loss": dict(drift=+0.09, vacancy=1.2),   # 2022-like, market above sitting rents
    "gain": dict(drift=-0.06, vacancy=1.8),   # 2026-like, market below sitting rents
    "burn": dict(drift=0.0, vacancy=1.5),     # neutral, used for burn-in and the pilot
}


def regime_params(base: Params, regime: str) -> Params:
    return replace(base, **REGIMES[regime])


# ---------------------------------------------------------------- crab hazards

def p_exo(p: Params, j) -> float:
    """Probability of a non-rent move (job, household, home purchase). Declines
    with tenure. NAA's ~47% annual turnover is mostly not about rent."""
    j = np.asarray(j, dtype=float)
    return p.p_exo_floor + p.p_exo_extra * np.exp(-(j - 1.0) / p.p_exo_tau)


def attach(p: Params, j):
    """Attachment, in months of market rent -- part of the switching cost."""
    return p.attach_coef * np.log(1.0 + np.asarray(j, dtype=float))


def size_primitives(p: Params) -> dict:
    """Everything that distinguishes a landlord type, derived from portfolio size
    alone (AMENDMENT 2 §A2.1). Called once per landlord; nothing here may be set
    per type."""
    u = float(max(p.units, 1))
    personal = 1.0 / (1.0 + u / p.u_personal)
    return dict(
        units=u,
        risk_scale=p.risk_rho / (2.0 * u * 12.0),
        comp_sigma=p.comp_sigma0 / np.sqrt(u),
        nonpec=p.nonpec0 * personal,
        raise_cost=p.raise_cost0 * personal,
        turn_scale=1.0 + p.turn_scale_beta / np.sqrt(u),
        face_mult=(u / (u + p.u_cap)) if p.size_scaled_face else 1.0,
        agent_w=(u / (u + p.u_agent)) if p.agent_bonus > 0.0 else 0.0,
    )


def gauss_hermite(n: int):
    """Nodes/weights for E[f(eps)] with eps ~ N(0,1). Deterministic."""
    x, wt = np.polynomial.hermite_e.hermegauss(n)
    return x, wt / wt.sum()


def q_sit(p: Params, j):
    """Proven-payer premium: expected credit/early-turn cost of a crab with j
    years of on-time history, versus q_new for an unknown applicant."""
    return p.q_new * np.exp(-np.asarray(j, dtype=float) / p.q_sit_tau)


def gain_base(p: Params, q_eff, r, j):
    """The crab's gain from leaving, in months of market rent, BEFORE its own
    switching cost and before any one-time cash. q_eff is the effective rent
    ratio it would pay if it stays.

        12 kappa_c (q_eff - 1)   the level: paying above/below market
      + lambda_ref 12 (q_eff - r) the increase: reference dependence
      - a(j)                      attachment
    """
    q_eff = np.asarray(q_eff, dtype=float)
    r = np.asarray(r, dtype=float)
    return (12.0 * p.kappa_crab * (q_eff - 1.0)
            + p.lambda_ref * 12.0 * (q_eff - r)
            - attach(p, j))


def sigmoid(x):
    x = np.clip(np.asarray(x, dtype=float), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


# ------------------------------------------------------- switching-cost nodes

def switching_cost_nodes(p: Params, n_nodes: int = 64, seed: int = 424242):
    """Equally-weighted quantile midpoints of the TOTAL switching-cost
    distribution c = (1-a) c_persistent + a c_transient, both lognormal.
    Deterministic given the seed. The station knows this distribution; it never
    sees an individual crab's draw."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, n_nodes]))
    n = 400_000
    mu = np.log(p.move_med)
    cp = rng.lognormal(mu, p.move_sigma, n)
    ct = rng.lognormal(mu, p.move_sigma, n)
    c = (1.0 - p.move_transient) * cp + p.move_transient * ct
    qs = (np.arange(n_nodes) + 0.5) / n_nodes
    return np.quantile(c, qs), np.quantile(c, np.arange(1, n_nodes) / n_nodes)


# ---------------------------------------------------------------- market paths

def market_path(p: Params, station_seed: int, regime: str, n_burn: int,
                n_meas: int, drift_override=None) -> np.ndarray:
    """M_t in dollars/month for years 0 .. n_burn+n_meas-1.

    Burn-in draws come from a REGIME-INDEPENDENT stream, so both regimes and
    every arm share an identical burn-in (SPEC §9)."""
    burn_rng = np.random.default_rng(np.random.SeedSequence([station_seed, 11]))
    reg_id = {"loss": 1, "gain": 2, "burn": 3}[regime]
    meas_rng = np.random.default_rng(
        np.random.SeedSequence([station_seed, 22, reg_id]))
    m = np.empty(n_burn + n_meas)
    lvl = np.log(ANCHOR_RENT)
    for t in range(n_burn):
        if t > 0:
            lvl += p.sigma_burn * burn_rng.standard_normal()
        m[t] = np.exp(lvl)
    for t in range(n_meas):
        dr = p.drift if drift_override is None else float(drift_override[t])
        lvl += dr + p.sigma_meas * meas_rng.standard_normal()
        m[n_burn + t] = np.exp(lvl)
    return m


@dataclass(frozen=True)
class Shock:
    """EXPLORATORY only (PREREG AMENDMENT 1 §A1.3). Per-measurement-year
    overrides: market drift, a vacancy multiplier, a wealth tolerance granted to
    crabs ARRIVING that year, and a probability that a wealthy crab leaves
    abruptly."""
    name: str
    drift: np.ndarray
    vac_mult: np.ndarray
    wealth: np.ndarray
    exodus: np.ndarray


def uniforms(p: Params, station_seed: int, regime: str, phase: int,
             n_years: int) -> np.ndarray:
    """(units, years, N_UNIFORMS) pre-drawn uniforms. phase 0 = burn-in
    (regime-independent), phase 1 = measurement."""
    if phase == 0:
        ss = np.random.SeedSequence([station_seed, 33])
    else:
        reg_id = {"loss": 1, "gain": 2, "burn": 3}[regime]
        ss = np.random.SeedSequence([station_seed, 44, reg_id])
    rng = np.random.default_rng(ss)
    return rng.random((p.units, n_years, N_UNIFORMS))


# ---------------------------------------------------------------------- state

@dataclass
class Crab:
    strategy: int
    rent: float           # $/month, rent of record
    tenure: int           # completed years at the upcoming renewal
    c_persist: float      # months of market rent, drawn at move-in
    fee_years: int = 0    # remaining years of an ancillary-fee waiver
    fee_value: float = 0.0  # $/year waived
    locked: int = 0       # remaining years of a term lock
    born: int = 0
    # arm F state
    courage: float = 0.0  # months of market rent; cost of sending the message
    belief: float = 0.10  # subjective P(concession | ask)
    ask_scale: float = 1.0
    pref_kind: int = -1   # learned instrument preference, -1 = PREREG order
    asked_last: bool = False
    won_last: bool = False
    ten: object = None    # demographic draw (AMENDMENT 3), None under Phase 1
    # shock state
    wealth: float = 0.0   # extra tolerance for paying above market, months


def new_crab(p: Params, u, year: int, strategy_share: float,
             asker_strategy: int) -> Crab:
    strat = asker_strategy if u[U_STRAT] < strategy_share else NEVER_ASK
    cp = float(np.exp(np.log(p.move_med)
                      + p.move_sigma * _norm_ppf(u[U_CP])))
    courage = float(np.exp(np.log(p.courage_med)
                           + p.courage_sigma * _norm_ppf(u[U_COURAGE])))
    ten = None
    if p.negotiator != "ladder":
        from crabs.demographics import draw_tenant
        ten = draw_tenant(u[U_DEMO:U_DEMO + 7])
    return Crab(strategy=strat, rent=0.0, tenure=0, c_persist=cp, born=year,
                courage=courage, belief=p.belief0, ten=ten)


def _norm_ppf(u):
    """Inverse standard normal CDF (Acklam's rational approximation, ~1e-9)."""
    u = np.clip(np.asarray(u, dtype=float), 1e-12, 1 - 1e-12)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    out = np.empty_like(u)
    lo = u < plow
    hi = u > phigh
    mid = ~(lo | hi)
    if np.any(lo):
        q = np.sqrt(-2 * np.log(u[lo]))
        out[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q
                   + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if np.any(hi):
        q = np.sqrt(-2 * np.log(1 - u[hi]))
        out[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q
                    + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if np.any(mid):
        q = u[mid] - 0.5
        rr = q * q
        out[mid] = (((((a[0] * rr + a[1]) * rr + a[2]) * rr + a[3]) * rr + a[4])
                    * rr + a[5]) * q / (((((b[0] * rr + b[1]) * rr + b[2]) * rr
                                          + b[3]) * rr + b[4]) * rr + 1)
    return out if out.shape else float(out)


# ------------------------------------------------------------------- recording

def new_recorder() -> dict:
    z = 0.0
    rec = dict(
        habitat_years=z, crab_years=z, renewals=z, left=z,
        surplus=z, surplus_asker=z, surplus_nonasker=z,
        crab_years_asker=z, crab_years_nonasker=z,
        renewals_asker=z, renewals_nonasker=z, left_asker=z, left_nonasker=z,
        countered=z, success=z, success_price=z,
        countered_lt2=z, success_lt2=z, countered_ge2=z, success_ge2=z,
        station_cash=z, station_objective=z, turn_cost_paid=z, vacancy_lost=z,
        rent_ratio_sum=z, rent_ratio_n=z, market_sum=z, rent_paid_sum=z,
        zero_increase=z, reviewed=z, queue_denied=z, blanket_sum=z,
        blanket_n=z, welfare_extra=z, engine_util_sum=z, engine_util_n=z,
        issues_conceded=z, bundles_granted=z, burdened_years=z,
        surplus_burdened=z, termlover_years=z, surplus_termlover=z,
        ask_share_sum=z, ask_share_n=z, belief_sum=z, belief_n=z,
        ask_scale_sum=z, wealthy_years=z, surplus_wealthy=z,
        crab_cash=z, arrival_cash=z, move_cost_paid=z,
        concession_value=z, rounds=z,
        pred_leave=z, real_leave=z,
        offer_ratio_sum=z, push_sum=z, push_n=z,
    )
    for k in KIND_NAMES:
        rec[f"grant_{k}"] = z
        rec[f"grantval_{k}"] = z
    for j in range(1, 9):
        rec[f"ten{j}_renewals"] = z
        rec[f"ten{j}_left"] = z
    return rec


# --------------------------------------------------------------- the period loop

def simulate_station(p_burn: Params, p_meas: Params, station_seed: int,
                     regime: str, station_burn, station_meas,
                     share: float, asker_strategy: int,
                     burn_share: float = 0.39,
                     burn_strategy: int = ASK_PRICE,
                     collect: bool = False,
                     learn: bool = False, broadcast: bool = False,
                     shock=None, series: bool = False) -> dict:
    """One station over burn-in + measurement. Only the measurement window is
    recorded. The burn-in runs arm A's policy in EVERY arm so all arms inherit
    an identical tenure/rent distribution (SPEC §3).

    learn      arm F: the asker share is ENDOGENOUS. Each crab asks when its
               belief that asking works, times what it would be worth, exceeds
               its own cost of sending the message.
    broadcast  arm F: crabs additionally hear what happened to their neighbours
               in the same station. With broadcast off they learn only from
               their own outcome, which is the control K7/K8 compare against.
    station_meas may be a dict {share: landlord}, in which case the landlord is
               re-selected each year from last year's realised asker share --
               how an adaptive operator would actually track adoption."""
    nb, nm = p_burn.burn_years, p_meas.meas_years
    m = market_path(p_meas, station_seed, regime, nb, nm,
                    drift_override=None if shock is None else shock.drift)
    ub = uniforms(p_burn, station_seed, regime, 0, nb)
    um = uniforms(p_meas, station_seed, regime, 1, nm)
    rec = new_recorder()
    if collect:
        rec["_csamples"] = []
        rec["_casker"] = []

    # initial population: tenure spread over the buckets, rent at market
    crabs: list[Crab] = []
    for i in range(p_burn.units):
        u = ub[i, 0]
        c = new_crab(p_burn, u, 0, burn_share, burn_strategy)
        c.tenure = 1 + int(u[U_TEN0] * p_burn.j_max)
        c.rent = m[0]
        crabs.append(c)

    if series:
        rec["_years"] = []
    live_share = share
    for t in range(nb + nm):
        measuring = t >= nb
        p = p_meas if measuring else p_burn
        st = station_burn
        if measuring:
            st = (station_meas if not isinstance(station_meas, dict)
                  else station_meas[min(station_meas,
                                        key=lambda k: abs(k - live_share))])
        uu = um[:, t - nb] if measuring else ub[:, t]
        sh = share if measuring else burn_share
        strat = asker_strategy if measuring else burn_strategy
        if t == nb:
            # The arm is a counterfactual about how many crabs use the tool, so
            # it applies to the whole sitting population, not only to crabs who
            # happen to move in during the measurement window.
            for i, c in enumerate(crabs):
                c.strategy = (asker_strategy
                              if um[i, 0, U_RESTRAT] < share else NEVER_ASK)
        g_obs = (m[t] / m[t - 1] - 1.0) if t > 0 else 0.0
        M = m[t]
        yi = t - nb
        vmul_y = 1.0 if shock is None else float(shock.vac_mult[yi]) if measuring else 1.0
        wealth_y = 0.0 if shock is None else float(shock.wealth[yi]) if measuring else 0.0
        exodus_y = 0.0 if shock is None else float(shock.exodus[yi]) if measuring else 0.0
        if measuring and learn:
            _set_endogenous_askers(p, crabs, M, st, asker_strategy)
        gv = _year(p, st, crabs, uu, M, g_obs, sh, strat, t,
                   rec if measuring else None, vmul_y=vmul_y,
                   wealth_y=wealth_y, exodus_y=exodus_y)
        if measuring and learn:
            _update_beliefs(p, crabs, gv, broadcast)
            live_share = gv["n_ask"] / max(1.0, gv["n_renew"])
            rec["ask_share_sum"] += live_share
            rec["ask_share_n"] += 1.0
        if measuring and series:
            rec["_years"].append(_year_snapshot(crabs, gv, M, yi))
    return rec


def _set_endogenous_askers(p: Params, crabs, M, st, asker_strategy):
    """Arm F: nobody is assigned to ask. A crab asks when

        belief x (what the ask would be worth)  >  its own cost of asking

    so the asker share is an output, and broadcast raises it only by changing
    beliefs."""
    for c in crabs:
        if c.locked > 0:
            continue
        q = c.rent / M
        worth = c.belief * c.ask_scale * p.ask_frac * 12.0 * max(q, 0.1)
        c.strategy = asker_strategy if worth > c.courage else NEVER_ASK


def _update_beliefs(p: Params, crabs, gv, broadcast: bool):
    """With broadcast, every crab in the station hears the station's outcomes --
    so a 200-habitat station is a sharp signal and a 5-habitat one is noise or
    silence. Without broadcast, a crab updates only on what happened to it."""
    a = p.learn_rate
    if broadcast and gv["n_ask"] >= 1.0:
        s = gv["n_succ"] / gv["n_ask"]
        sc = (gv["cleared_scale"] / gv["n_succ"]) if gv["n_succ"] >= 1.0 else None
        kind = gv["modal_kind"]
        for c in crabs:
            c.belief = min(p.belief_hi, max(p.belief_lo,
                                            (1 - a) * c.belief + a * s))
            if sc is not None:
                c.ask_scale = min(p.ask_scale_hi, max(
                    p.ask_scale_lo, (1 - a) * c.ask_scale + a * sc))
                c.pref_kind = kind
        return
    for c in crabs:
        if c.asked_last:
            own = 1.0 if c.won_last else 0.0
            c.belief = min(p.belief_hi, max(p.belief_lo,
                                            (1 - a) * c.belief + a * own))


def _year_snapshot(crabs, gv, M, yi) -> dict:
    return dict(year=yi, market=M, n_ask=gv["n_ask"], n_succ=gv["n_succ"],
                n_renew=gv["n_renew"], n_left=gv["n_left"],
                rent_ratio=gv["ratio_sum"] / max(1.0, gv["ratio_n"]),
                surplus_incumbent=gv["surp_inc"] / max(1.0, gv["n_inc"]),
                surplus_wealthy=gv["surp_rich"] / max(1.0, gv["n_rich"]),
                n_wealthy=gv["n_rich"], vacancy_months=gv["vac_months"])


def _year(p: Params, st, crabs, uu, M, g_obs, share, asker_strategy, t, rec,
          vmul_y: float = 1.0, wealth_y: float = 0.0, exodus_y: float = 0.0):
    gv = dict(n_ask=0.0, n_succ=0.0, n_renew=0.0, n_left=0.0, cleared_scale=0.0,
              kinds=[0.0, 0.0, 0.0, 0.0], ratio_sum=0.0, ratio_n=0.0,
              surp_inc=0.0, n_inc=0.0, surp_rich=0.0, n_rich=0.0,
              vac_months=0.0)
    # ---- arm G: one blanket increase for the whole portfolio, then a finite
    # queue of hand-worked exceptions. Nobody optimises every unit.
    x_blanket, queue_left = None, 0
    if p.menu_costs:
        states = [(c.rent / M, min(c.tenure, p.j_max))
                  for c in crabs if c.locked <= 0]
        x_blanket = st.blanket_push(states)
        queue_left = int(np.ceil(p.queue_frac * len(crabs)))
        if rec is not None:
            rec["blanket_sum"] += x_blanket
            rec["blanket_n"] += 1.0
    for i, crab in enumerate(crabs):
        crab.asked_last = False
        crab.won_last = False
        u = uu[i]
        if rec is not None:
            rec["habitat_years"] += 1.0
            rec["market_sum"] += 12.0 * M

        # ---- inside a term lock: no renewal, rent frozen in dollars
        if crab.locked > 0:
            crab.locked -= 1
            fee = _fee_credit(crab)
            paid = 12.0 * crab.rent - fee
            if rec is not None:
                _count_crab_year(rec, crab)
                _add_surplus(rec, crab, 12.0 * M - paid)
                rec["station_cash"] += paid
                rec["crab_cash"] += paid
                rec["rent_paid_sum"] += paid
                rec["rent_ratio_sum"] += crab.rent / M
                rec["rent_ratio_n"] += 1.0
                rec["station_objective"] += paid + p.face_premium * 12.0 * crab.rent
            # locked crabs can still be moved by life, at a break fee
            if u[U_LOCKEXO] < p_exo(p, crab.tenure + 1) * p.break_damp:
                jj = min(crab.tenure, p.j_max)
                tmul_l, vmul_l = turn_multipliers(p, u, jj)
                if rec is not None:
                    fee_paid = p.break_fee * crab.rent
                    move = (_c_total(p, crab, u) + float(attach(p, jj))) * M
                    rec["station_cash"] += fee_paid
                    rec["crab_cash"] += fee_paid
                    rec["move_cost_paid"] += move
                    _add_surplus(rec, crab, -fee_paid - move)
                crabs[i] = _turn_over(p, crab, u, M, t, share, asker_strategy,
                                      rec, tmul=tmul_l, vmul=vmul_l)
            else:
                crab.tenure += 1
                if crab.fee_years > 0:
                    crab.fee_years -= 1
            continue

        j = min(crab.tenure, p.j_max)
        r = crab.rent / M
        q = r * (1.0 + x_blanket) if x_blanket is not None else st.offer(r, j)
        c_tot = _c_total(p, crab, u)
        tmul, vmul = turn_multipliers(p, u, j)
        vmul *= vmul_y

        if p.ask_mode not in ("assigned", "random_at"):
            crab.strategy = (asker_strategy
                             if wants_to_ask(p, crab, q, r, j, c_tot, u)
                             else NEVER_ASK)
        will_ask = crab.strategy != NEVER_ASK

        if x_blanket is not None:
            # Arm G. Countering is what gets your file read. No signal is needed
            # for this to pay -- the blanket policy simply is not your optimum.
            if will_ask and queue_left > 0:
                queue_left -= 1
                q = st.offer(r, j)
                if rec is not None:
                    rec["reviewed"] += 1.0
                pkg, n_rounds, asked, granted_kind = st.negotiate(
                    p, crab, q, r, j, u, g_obs, asker_strategy, tmul=tmul,
                    vmul=vmul)
            else:
                if will_ask and rec is not None:
                    rec["queue_denied"] += 1.0
                pkg, n_rounds, asked, granted_kind = None, 0, will_ask, None
        elif p.negotiator != "ladder":
            # AMENDMENT 3 §A3.1: the crab's side is the REAL engine.
            from crabs.engine_bridge import negotiate_with_engine
            if will_ask and crab.ten is not None:
                _sd = abs(hash((int(M), i, t, j))) % (2 ** 31)
                if p.negotiator == "matrix":
                    from crabs.armk import negotiate_matrix
                    bnd, n_rounds, asked, eu, q = negotiate_matrix(
                        st, p, crab.ten, crab, q, r, j, M, g_obs, c_tot, _sd,
                        p.tenant_engine, p.landlord_engine, tmul=tmul,
                        vmul=vmul)
                else:
                    bnd, n_rounds, asked, eu = negotiate_with_engine(
                        st, p, crab.ten, crab, q, r, j, M, g_obs, c_tot, _sd,
                        tmul=tmul, vmul=vmul,
                        multi=(p.negotiator == "engine_bundle"), u=u)
                pkg = bnd
                granted_kind = None if bnd is None else _bundle_kind(bnd)
                if rec is not None and eu is not None:
                    rec["engine_util_sum"] += eu
                    rec["engine_util_n"] += 1.0
            else:
                pkg, n_rounds, asked, granted_kind = None, 0, False, None
        else:
            pkg, n_rounds, asked, granted_kind = st.negotiate(
                p, crab, q, r, j, u, g_obs, asker_strategy, tmul=tmul, vmul=vmul)

        if _is_bundle(pkg):
            from crabs.engine_bridge import bundle_effects
            q_eff, z_crab, _, _ = bundle_effects(p, crab.ten, q, pkg, M, g_obs)
        else:
            q_eff, z_crab, _, _ = st.package_effects(p, q, pkg, g_obs_crab=g_obs)
        gb = float(gain_base(p, q_eff, r, j)) - z_crab - crab.wealth
        if rec is not None and "_csamples" in rec:
            rec["_csamples"].append((j, c_tot))
            if asked:
                rec["_casker"].append((j, c_tot))
        exo = u[U_EXO] < p_exo(p, j)
        endo = u[U_LOGIT] < sigmoid((gb - c_tot) / p.nu)
        leave = bool(exo or endo)
        if crab.wealth > 0.0 and exodus_y > 0.0 and u[U_EXODUS] < exodus_y:
            leave = True                      # the migration reverses
        crab.asked_last = asked
        crab.won_last = granted_kind is not None
        gv["n_renew"] += 1.0
        if asked:
            gv["n_ask"] += 1.0
            if granted_kind is not None:
                gv["n_succ"] += 1.0
                gv["cleared_scale"] += (0.0 if pkg is None else
                                        (1.0 if _is_bundle(pkg) else pkg[1]))
                gv["kinds"][granted_kind] += 1.0

        if rec is not None:
            rec["renewals"] += 1.0
            rec[f"ten{j}_renewals"] += 1.0
            rec["offer_ratio_sum"] += q
            rec["push_sum"] += q / r - 1.0
            rec["push_n"] += 1.0
            if q <= r * (1.0 + 1e-9):
                rec["zero_increase"] += 1.0
            rec["pred_leave"] += st.leave_prob(gb, j)
            rec["real_leave"] += 1.0 if leave else 0.0
            rec["rounds"] += n_rounds
            key = "asker" if crab.strategy != NEVER_ASK else "nonasker"
            rec[f"renewals_{key}"] += 1.0
            if asked:
                rec["countered"] += 1.0
                if j <= 1:
                    rec["countered_lt2"] += 1.0
                else:
                    rec["countered_ge2"] += 1.0
                if granted_kind is not None:
                    rec["success"] += 1.0
                    if granted_kind == RENT:
                        rec["success_price"] += 1.0
                    if j <= 1:
                        rec["success_lt2"] += 1.0
                    else:
                        rec["success_ge2"] += 1.0

        if leave:
            if rec is not None:
                rec["left"] += 1.0
                rec[f"ten{j}_left"] += 1.0
                rec[f"left_{'asker' if crab.strategy != NEVER_ASK else 'nonasker'}"] += 1.0
                _count_crab_year(rec, crab)
                cost = (c_tot + float(attach(p, j))) * M
                _add_surplus(rec, crab, -cost)
                rec["move_cost_paid"] += cost
            gv["n_left"] += 1.0
            gv["vac_months"] += min(p.vacancy * vmul, 11.0)
            crabs[i] = _turn_over(p, crab, u, M, t, share, asker_strategy, rec,
                                  tmul=tmul, vmul=vmul, wealth=wealth_y)
            continue

        # ---- stays: realise the package exactly
        if _is_bundle(pkg):
            from crabs.engine_bridge import apply_bundle, issue_dollars, \
                welfare_premium
            onetime = apply_bundle(p, crab, q, pkg, M)
            if rec is not None:
                dd = issue_dollars(p, crab.ten, q, M, g_obs, pkg)
                rec["welfare_extra"] += welfare_premium(crab.ten, dd)
                rec["issues_conceded"] += sum(
                    1 for k in dd if abs(dd[k]) > 1e-9)
                rec["bundles_granted"] += 1.0
        else:
            st.apply_package(p, crab, q, pkg, M, g_obs)
            onetime = z_crab * M if pkg is not None and pkg[0] == ONE_TIME \
                else 0.0
        fee = _fee_credit(crab)
        paid = 12.0 * crab.rent - fee - onetime
        if rec is not None:
            _count_crab_year(rec, crab)
            _add_surplus(rec, crab, 12.0 * M - paid)
            rec["station_cash"] += paid
            rec["crab_cash"] += paid
            rec["rent_paid_sum"] += paid
            rec["rent_ratio_sum"] += crab.rent / M
            rec["rent_ratio_n"] += 1.0
            rec["station_objective"] += paid + p.face_premium * 12.0 * crab.rent
            rec["belief_sum"] += crab.belief
            rec["belief_n"] += 1.0
            rec["ask_scale_sum"] += crab.ask_scale
            if crab.wealth > 0.0:
                rec["wealthy_years"] += 1.0
                rec["surplus_wealthy"] += 12.0 * M - paid
            if granted_kind is not None:
                rec[f"grant_{KIND_NAMES[granted_kind]}"] += 1.0
                _cv = _pkg_crab_value(p, st, q, pkg, M, g_obs, crab)
                rec[f"grantval_{KIND_NAMES[granted_kind]}"] += _cv
                rec["concession_value"] += _cv
        gv["ratio_sum"] += crab.rent / M
        gv["ratio_n"] += 1.0
        if crab.wealth > 0.0:
            gv["surp_rich"] += 12.0 * M - paid
            gv["n_rich"] += 1.0
        else:
            gv["surp_inc"] += 12.0 * M - paid
            gv["n_inc"] += 1.0
        crab.tenure += 1
        if crab.fee_years > 0:
            crab.fee_years -= 1
    ks = gv["kinds"]
    gv["modal_kind"] = int(max(range(4), key=lambda k: ks[k])) if sum(ks) else -1
    return gv


def wants_to_ask(p: Params, crab, q, r, j, c_tot, u) -> bool:
    """AMENDMENT 2 arms H and I. Who counters is the arm, not a parameter.

    assigned    Phase 1: a random trait, so a counter carries no information
    everyone    all crabs counter, which destroys the signal
    tool        counters only when the walk-away floor is genuinely cleared --
                this is the product's "you are weak, just sign" verdict, modelled
                as a mechanism rather than as a trust gesture
    selfselect  counters when within `engage_margin` of indifference; the softer,
                more realistic version used for the screening arm
    random_at   a random trait again, but at whatever share the tool produced, so
                the three populations are compared at EQUAL asker share
    """
    mode = p.ask_mode
    if mode in ("assigned", "random_at"):
        return crab.strategy != NEVER_ASK
    if mode == "everyone":
        return True
    gain = float(gain_base(p, q, r, j)) - crab.wealth - c_tot
    if mode == "tool":
        if p.tool_noise > 0.0:
            gain += p.tool_noise * _norm_ppf(u[U_TOOL])
        return gain > 0.0
    if mode == "selfselect":
        return gain > -p.engage_margin
    raise ValueError(mode)


def _pkg_crab_value(p, st, q, pkg, M, g_obs, crab=None):
    """Dollars of value the crab realises from the granted package this year,
    relative to the station's opening offer (reporting only)."""
    if pkg is None:
        return 0.0
    if _is_bundle(pkg):
        from crabs.engine_bridge import bundle_effects
        ten = crab.ten if crab is not None else None
        q_eff, z_crab, _, _ = bundle_effects(p, ten, q, pkg, M, g_obs)
    else:
        q_eff, z_crab, _, _ = st.package_effects(p, q, pkg, g_obs_crab=g_obs)
    return (12.0 * (q - q_eff) + z_crab) * M


def _c_total(p: Params, crab: Crab, u) -> float:
    ct = float(np.exp(np.log(p.move_med) + p.move_sigma * _norm_ppf(u[U_CT])))
    return (1.0 - p.move_transient) * crab.c_persist + p.move_transient * ct


def turn_multipliers(p: Params, u, j):
    """(make-ready multiplier, days-vacant multiplier) for this habitat-year.
    Mean-one lognormals, so switching dispersion on does not move the average
    turn cost; the tenure slope does, and it is a deterministic function of a
    state the station already observes."""
    tm = 1.0 + p.turn_tenure_slope * float(np.log(1.0 + j))
    if p.sigma_turn > 0.0:
        tm *= float(np.exp(p.sigma_turn * _norm_ppf(u[U_TCOST])
                           - 0.5 * p.sigma_turn ** 2))
    vm = 1.0
    if p.sigma_vac > 0.0:
        vm = float(np.exp(p.sigma_vac * _norm_ppf(u[U_VAC])
                          - 0.5 * p.sigma_vac ** 2))
    return tm, vm


def _fee_credit(crab: Crab) -> float:
    return crab.fee_value if crab.fee_years > 0 else 0.0


def _is_bundle(pkg) -> bool:
    return pkg is not None and hasattr(pkg, "ri")


def _bundle_kind(b) -> int:
    """Reporting only: which instrument dominates the granted bundle."""
    if b.ri > 0:
        return RENT
    if b.term:
        return TERM
    if b.ci > 0:
        return ONE_TIME
    return FEES


def _count_crab_year(rec, crab):
    rec["crab_years"] += 1.0
    if crab.strategy != NEVER_ASK:
        rec["crab_years_asker"] += 1.0
    else:
        rec["crab_years_nonasker"] += 1.0


def _add_surplus(rec, crab, v):
    rec["surplus"] += v
    if crab.strategy != NEVER_ASK:
        rec["surplus_asker"] += v
    else:
        rec["surplus_nonasker"] += v


def _turn_over(p: Params, old: Crab, u, M, t, share, asker_strategy, rec,
               tmul: float = 1.0, vmul: float = 1.0,
               wealth: float = 0.0) -> Crab:
    """The habitat turns: T is paid, it sits vacant `vacancy` months, then a new
    crab signs at market. The arriving crab's partial year is surplus-neutral."""
    T = p.turn_cost * tmul
    vac = min(p.vacancy * vmul, 11.0)
    if rec is not None:
        rec["turn_cost_paid"] += T * M
        rec["vacancy_lost"] += vac * M
        arrival = (12.0 - vac) * M
        rec["station_cash"] += arrival - T * M
        rec["arrival_cash"] += arrival
        rec["station_objective"] += (arrival - T * M
                                     + p.face_premium * (12.0 - vac) * M)
    c = new_crab(p, u, t, share, asker_strategy)
    c.rent = M
    c.tenure = 1
    c.wealth = wealth
    return c

"""AMENDMENT 5 (two channels, walk-away asymmetry) + AMENDMENT 3 §A3.3 (GATE 3).

Phases 1-4 modelled one negotiation type against an imposed price path. This
module fixes both at once, because the fix is the same fix: once habitats sit
vacant and post asking rents, and once leaving tenants enter a search pool
instead of vanishing, there are two channels AND there is an endogenous market.

    market rent is an OUTPUT.  M_t = mean realised new-let rent in year t.
    Nothing imposes it. Stations post asks against their own observed vacancy;
    searchers see a handful of listings and take the best; the "market rent" is
    a statistic of what actually got signed.

Two channels, never pooled:

  RENEWAL   sitting tenant. Landlord walk-away = turn cost + expected vacancy
            loss + re-let rent risk. Tenant walk-away = moving cost + search
            cost. Our own calibration puts the median moving cost at ~$7,200,
            which is the whole point of A5.
  NEW LET   searching tenant. **AMENDMENT 5a CORRECTION.** A5.0 said the
            landlord's walk-away here is "one more vacancy day" because the turn
            cost is sunk. That conflated two costs with opposite time structure.
            MAKE-READY is one-time and genuinely sunk once paid, and is never
            charged twice (asserted by a test). VACANCY LOSS IS A FLOW that
            accumulates every month the habitat sits empty -- the opposite of
            sunk -- so walking away from an applicant costs
            E[remaining vacancy] x rent, on the order of 1-1.5 months at
            commonly cited 30-41 day let times, not a day.

            This INVERTS the asymmetry between channels: in a renewal the tenant
            is the weak party (a ~$7,200 move); in a new let the LANDLORD is (an
            accumulating vacancy) while the tenant merely views the next listing.
            Landlords therefore raise on renewals and concede to newcomers, in
            the same building in the same period, from walk-away structure alone.

Both channels are settled by the SAME solution concept -- a symmetric split of
the bargaining zone -- so that any difference in outcomes between them comes
from the walk-away structure and nothing else. That is what makes A5's claim
testable rather than assumed. `lambda_split = 0.5` is declared, not fitted.

DECLARED PARAMETERS (fixed before the first run):
    lambda_split   0.5    symmetric Nash split inside the zone
    search_cost    0.25 months ($500)  viewings, applications, time
    app_cost       0.08 months ($160)  switching between listings while already
                                       moving -- much smaller than a move
    k_visible      5      listings a searcher can see (local information only)
    vac_adjust     0.6    asking-rent response to vacancy deviation
                          ** declared 0.6, ships 3.0, and INERT -- note below **
    v_target       0.06   the vacancy a station prices toward -- same note
    precedent0     0.0    A5.3 commitment asymmetry, swept -- NOT assumed

VAC_ADJUST / V_TARGET: DECLARED 0.6, SHIPPED 3.0, AND DEAD (audit 2026-07-25)
---------------------------------------------------------------------------
The list above is the declared-before-running list and it says 0.6. The module
ships 3.0, retuned after observing deflation (RESULTS Phase 5 §5: "a much
stronger ask-adjustment (0.6 -> 3.0)"). That much is an honest post-hoc
calibration mislabelled as pre-declared, recorded as CALIBRATED in
`principles.PARAM_SOURCES` rather than quietly reconciled.

But the value does not matter, because **neither use of it can fire in the
shipped configuration**:

  1. `M_relet = M_obs * (1.0 - VAC_ADJUST * 0.0)` -- multiplied by a literal
     zero, so `M_relet == M_obs` for every renewal ever priced.
  2. The ask-setting block guarded by `if h.crab is None` runs at the ANNUAL
     boundary, where `vacant_years == 0` in every reported cell: the monthly
     matching loop fills every habitat before the year turns. `ask_n == 0` over
     10,000 habitat-years, so the block sets no ask, ever.

Verified by running the baseline at VAC_ADJUST in {0.0, 0.6, 3.0, 100.0}: the
recorder is BIT-IDENTICAL at all four. `DOM_CUT` sits in the same dead block, so
the "a landlord that has sat unlet re-lists lower" ASK channel is also inert --
though the days-on-market effect on the landlord's RESERVATION is live and
separately tested, via `expected_wait_months` in `newlet_walkaways`.

Consequences, which belong here and not only in RESULTS.md:
  - `mean_ask` is 0/0 = **NaN** in every shipped market cell.
  - "stations post asking rents against their own observed vacancy", stated as a
    structural feature at the top of this file, does not happen. Asks are set
    flat at `M_obs` inside the matching loop.
  - RESULTS Phase 5 §5 argues the deflation "is not a tuning problem" partly
    because a stronger ask-adjustment did not cure it. In the CURRENT code that
    argument has no force, because the ask-adjustment does nothing. It may have
    had force when written, when vacancy ran 12.7-17.9%; that cannot be checked
    from here, and the claim is narrowed in RESULTS.md accordingly.

The value is left at 3.0 and the dead code is left in place: changing either
would edit history without changing a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from crabs.world import (ANCHOR_RENT, Crab, Params, _c_total, _norm_ppf, attach,
                         p_exo, sigmoid)

LAMBDA_SPLIT = 0.5
BASE_LET_MONTHS = 1.15    # 30-41 day commonly cited let times
DOM_LEARN = 0.35          # A5a.3: having sat unlet for `dom` months is evidence
                          # this ask is too high for this market, so the expected
                          # remaining wait -- and thus the landlord's walk-away --
                          # grows in days-on-market. This is what makes the
                          # landlord's reservation weaken monotonically in dom.
MONTHS = 12
# AMENDMENT 6 §A6.1 -- ELASTIC DEMAND. Nothing previously brought searchers into
# the market as rents fell, so asks ratcheted down with no anchor. Market entry
# responds to the price level: as rents fall relative to a reference level, crabs
# enter from outside the market, from doubling-up, and from delayed household
# formation; as rents rise, fewer do.
#
#     inflow(M) = base_inflow x (M_ref / M)^ETA_DEMAND
#
# ETA_DEMAND is DECLARED, with a pre-declared sweep {0.5, 1.0, 1.5, 2.0}, and is
# NOT tuned to make a gate pass. 1.0 is the primary. Published headship-rate /
# household-formation elasticities with respect to rent sit around 0.5-1.5 in
# magnitude, which is larger than the ~0.3-0.7 usually quoted for quantity of
# housing demanded, because entry decisions (form a household or double up) are
# more responsive than consumption decisions. LABEL: ANCHORED range, INVENTED
# functional form.
ETA_DEMAND = 1.0
M_REF = ANCHOR_RENT

# --- AMENDMENT 6a: THE CLOCKS HAVE DIFFERENT SHAPES -------------------------
# The landlord's cost of delay is LINEAR: every month of negotiation eats
# marketing lead time and so adds to expected vacancy, forever, with no special
# date. The renewing tenant's is FLAT THEN A CLIFF: it must secure housing before
# the lease ends, and its EFFECTIVE deadline arrives EARLIER than lease end
# because search, application, approval and moving all need lead time. Crossing
# expiry unhoused costs holdover penalty rent plus an emergency move, not "another
# month of searching".
#
# All values DECLARED here before running; none tuned to V9.
NOTICE_WINDOW = 3.0        # months between the renewal offer and lease end
LEAD_MEDIAN = 1.5          # months of lead time a tenant needs: search, apply,
LEAD_SIGMA = 0.50          # approve, move. LABEL: INVENTED distribution.
CLIFF_CONVEX = 0.50        # walk-away rises convexly as usable time runs out
HOLDOVER_MONTHS = 0.5      # penalty-rent differential on a holdover tenancy
EMERGENCY_MONTHS = 1.5     # temporary housing, storage, emergency-move premium
LAND_LIN_RATE = 0.15       # linear: each month of delay adds 15% to E[vacancy].
                           # The landlord gets NO cliff, per A6a.3.
RESP_DELAY_MAX = 3         # exogenous tenant response delay, 0..3 months. Drawn
                           # independently of type so K25 is a causal comparison
                           # rather than the survivorship trap K21 fell into.
_LEAD_NODES = None


def lead_time_nodes(n: int = 15):
    """Fixed quadrature over the lead-time distribution. The landlord uses THIS --
    the population distribution -- never a tenant's realised draw."""
    global _LEAD_NODES
    if _LEAD_NODES is None:
        qs = (np.arange(n) + 0.5) / n
        _LEAD_NODES = np.exp(np.log(LEAD_MEDIAN)
                             + LEAD_SIGMA * np.array(
                                 [_norm_ppf(q) for q in qs]))
    return _LEAD_NODES


def tenant_clock_multiplier(lead: float, elapsed: float, window: float,
                            secured: bool = False):
    """(convex multiplier on the walk-away, discrete cliff penalty in months).

    Flat while usable time remains, rising convexly as it runs out, and a discrete
    penalty once the effective deadline (lease end minus lead time) is crossed.
    `secured` flattens the cliff into a floor: a tenant holding a real alternative
    cannot be caught unhoused."""
    if secured:
        return 1.0, 0.0
    usable = window - lead
    remaining = usable - elapsed
    if remaining >= 0.0 and usable > 1e-9:
        frac = 1.0 - remaining / usable
        return 1.0 + CLIFF_CONVEX * frac * frac, 0.0
    return 1.0 + CLIFF_CONVEX, HOLDOVER_MONTHS + EMERGENCY_MONTHS


def _signal_proved(mp, secured: bool) -> bool:
    """K26 AUDIT. Does this tenant produce a verifiable proof of its
    alternative? Only a tenant that actually holds one can, so the landlord is
    responding to a costly signal the tenant chose to send, not to a private
    draw it should not be able to see."""
    return bool(mp.signal_enabled and secured)


def searcher_inflow_at(base_inflow: float, m_obs: float,
                       eta: float = ETA_DEMAND) -> float:
    """Per-habitat searcher inflow at price level `m_obs`. Strictly decreasing in
    the rent level, which is the stabilising force the model was missing."""
    return float(base_inflow * (M_REF / max(m_obs, 1.0)) ** eta)


DOM_CUT = 0.02            # a landlord that has sat unlet re-lists lower: 2% off
                          # the ask per month on market, capped. Concession DEPTH
                          # is then measured off the ORIGINAL listed ask, which is
                          # how published concession depth is quoted (a discount
                          # off face rent).
SEARCH_COST = 0.25
APP_COST = 0.08
K_VISIBLE = 5
VAC_ADJUST = 3.0
V_TARGET = 0.06
RELET_RISK_ON = True

RENEWAL, NEW_LET = 0, 1


@dataclass
class MarketParams:
    n_stations: int = 40
    units: int = 25
    burn_years: int = 6
    meas_years: int = 10
    exit_share: float = 0.15           # leavers who exit the market entirely
                                       # (left the metro), so they do not fill
                                       # the listing they vacated. This is what
                                       # creates slack for vacancy to exist.
    searcher_inflow: float = 0.075     # household formation / in-migration per
                                      # habitat per year. EXOGENOUS and fixed in
                                      # level: that is what lets vacancy vary and
                                      # equilibrate. Set near steady-state
                                      # habitat-year. CALIBRATED so baseline
                                      # vacancy lands near the observed ~6% US
                                      # apartment vacancy. A level calibration to
                                      # a published aggregate, not to any kill.
    completions_year: int = 4         # GATE 3 V8: a supply shock lands here
    completions_frac: float = 0.0     # habitats added, as a share of stock
    completions_span: int = 3
    precedent: float = 0.0            # A5.3, per-habitat-share precedent cost
    lambda_split: float = LAMBDA_SPLIT
    tenant_sees_dom: bool = False     # K23: does the tenant negotiator get the
                                      # true timing state, or is it blind to it?
    eta_demand: float = ETA_DEMAND    # A6.1 demand elasticity of market entry
    deadline_shape: bool = True        # A6a: asymmetric clock shapes
    tenant_clock_linear: bool = False   # BUG HUNT for K24: replace the tenant's
                                       # convex+cliff clock with a LINEAR ramp
                                       # matched in mean. If the inversion
                                       # survives, the mechanism is LEVEL, not
                                       # shape, and K24's claim is wrong.
    secured_share: float = 0.0         # K26: share of tenants holding a real
                                       # alternative before countering
    signal_enabled: bool = False       # K26 AUDIT: may a tenant that holds an
                                       # alternative PROVE it at a cost? Default
                                       # OFF, so every previously reported cell
                                       # is unchanged. With it off the landlord
                                       # cannot respond to an alternative even in
                                       # principle, which makes K26's null a
                                       # property of the setup, not of the world.
    signal_cost: float = 0.10          # months of market rent to produce the
                                       # proof (forward the offer letter, pay a
                                       # holding deposit). DECLARED, swept.
    derive_switching: bool = False     # AMENDMENT 8: accumulate each searcher's
                                       # REALISED search cost, so that switching
                                       # cost can be an output instead of the
                                       # calibrated `move_med` input. Default OFF
                                       # and it draws from a SEPARATE rng, so
                                       # every previously reported market cell is
                                       # bit-identical with it on or off.


def _rec():
    z = 0.0
    r = dict(
        habitat_years=z, occupied_years=z, vacant_years=z,
        n_renewal=z, n_renewal_signed=z, n_renewal_left=z,
        n_newlet=z, n_newlet_signed=z, n_unmatched=z,
        renew_growth_sum=z, renew_growth_n=z,
        newlet_growth_sum=z, newlet_growth_n=z,
        renew_ratio_sum=z, newlet_ratio_sum=z,
        renew_rent_sum=z, newlet_rent_sum=z, newlet_vs_ask_sum=z, ask_sum=z,
        ask_n=z, sitting_rent_sum=z, sitting_rent_n=z,
        move_gain_sum=z, move_gain_n=z, move_gain_pos=z,
        rent_gap_sum=z,
        wa_tenant_renew=z, wa_land_renew=z, wa_n_renew=z,
        wa_tenant_newlet=z, wa_land_newlet=z, wa_n_newlet=z,
        zone_renew_sum=z, zone_newlet_sum=z,
        zone_renew_neg=z, zone_newlet_neg=z,
        turn_cost_paid=z, turn_events=z, vacancy_lost=z, move_cost_paid=z,
        lead_sum=z, elapsed_sum=z, secured_n=z, secured_offer=z,
        unsecured_n=z, unsecured_offer=z, secured_surp=z, unsecured_surp=z,
        vacant_months=z, depth_sum=z, dom_sum=z, wait_sum=z,
        surplus_renew=z, surplus_renew_n=z,
        surplus_newlet=z, surplus_newlet_n=z,
        crab_cash=z, station_cash=z,
        precedent_paid=z,
    )
    for b in range(4):
        r[f"renew_elapsed{b}_n"] = z
        r[f"renew_elapsed{b}_offer"] = z
        r[f"renew_elapsed{b}_surp"] = z
        r[f"depth_dom{b}"] = z
        r[f"depth_dom{b}_n"] = z
        r[f"zone_dom{b}"] = z
        r[f"zone_dom{b}_n"] = z
        r[f"resv_dom{b}"] = z
        r[f"resv_dom{b}_n"] = z
        r[f"dvm_dom{b}"] = z
        r[f"dvm_dom{b}_n"] = z
    for q in range(4):
        r[f"surp_renew_q{q}"] = z
        r[f"surp_renew_q{q}_n"] = z
        r[f"surp_newlet_q{q}"] = z
        r[f"surp_newlet_q{q}_n"] = z
        r[f"move_gain_q{q}"] = z
        r[f"move_gain_q{q}_n"] = z
        r[f"move_gain_q{q}_pos"] = z
    return r


@dataclass
class Hab:
    crab: Crab | None = None
    ask: float = 0.0
    prior_rent: float = 0.0      # rent of record before this year's event
    dom: float = 0.0             # A5a.3: months on market, carried as state
    ask0: float = 0.0            # the ask when first listed, for depth


# --------------------------------------------------------------- walk-aways
def renewal_walkaways(p: Params, mp: MarketParams, crab: Crab, u, M_obs,
                      M_relet, station_units):
    """(tenant walk-away cost $, landlord walk-away cost $, R_T_max $/yr,
    R_L_min $/yr) for a RENEWAL. Both in real dollars, both reported."""
    c_tot = _c_total(p, crab, u)                     # months of market rent
    move = c_tot * M_obs
    att = float(attach(p, min(crab.tenure, p.j_max))) * M_obs
    search = SEARCH_COST * M_obs
    wa_tenant = move + att + search
    turn = p.turn_cost * M_obs
    vac = p.vacancy * M_obs
    # re-let rent risk: if the sitting rent is above what a new let would fetch,
    # losing this tenant costs the rent gap as well
    gap = max(0.0, 12.0 * (crab.rent - M_relet)) if RELET_RISK_ON else 0.0
    wa_land = turn + vac + gap
    # precedent (A5.3): conceding leaks across the portfolio. Magnitude is a
    # swept parameter, never assumed.
    precedent = mp.precedent * station_units * M_obs
    r_t_max = 12.0 * M_obs + wa_tenant                # pay up to this and stay
    r_l_min = 12.0 * M_relet - turn - vac + precedent  # accept down to this
    return wa_tenant, wa_land, r_t_max, r_l_min, precedent


def expected_wait_months(tightness: float, dom: float) -> float:
    """E[remaining vacancy] in months if this applicant walks. Falls with market
    tightness (searchers per listing) and RISES with days-on-market, because
    having sat unlet is evidence the ask is wrong for this market."""
    t = max(float(tightness), 0.15)
    return float(np.clip(BASE_LET_MONTHS / t * (1.0 + DOM_LEARN * dom),
                         0.25, 12.0))


def newlet_walkaways(p: Params, mp: MarketParams, this_ask, next_best_ask,
                     station_units, tightness: float, dom: float):
    """(tenant walk-away $, landlord walk-away $, R_T_max, R_L_min) for a NEW LET,
    per AMENDMENT 5a. Make-ready is sunk and absent here. The landlord's
    walk-away is the ACCUMULATING vacancy flow it faces if this applicant walks,
    so its reservation weakens monotonically in days-on-market."""
    wait = expected_wait_months(tightness, dom)
    wa_land = wait * this_ask
    wa_tenant = APP_COST * this_ask                   # go look at another flat
    r_t_max = 12.0 * next_best_ask + wa_tenant
    r_l_min = (12.0 * this_ask - wa_land
               + mp.precedent * station_units * this_ask)
    return wa_tenant, wa_land, r_t_max, r_l_min, wait


# ------------------------------------------------------------------ the market
def simulate_market(p: Params, mp: MarketParams, seed: int,
                    drift: float = 0.0, record_series: bool = False) -> dict:
    """One market. `drift` is normally 0: GATE 3 asks whether the 2026 pattern
    emerges WITHOUT an imposed regime, so the default imposes nothing."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 5150]))
    # AMENDMENT 8: a SEPARATE stream, so that switching on the derivation cannot
    # perturb the main sequence and silently move every previously reported cell.
    rng_a8 = np.random.default_rng(np.random.SeedSequence([seed, 8080]))
    S, U = mp.n_stations, mp.units
    stations = [[Hab() for _ in range(U)] for _ in range(S)]
    rec = _rec()
    if mp.derive_switching:
        rec["_derived"] = []
    series = []

    # initial population at the anchor rent
    for s in range(S):
        for h in stations[s]:
            cp = float(np.exp(np.log(p.move_med)
                              + p.move_sigma * _norm_ppf(rng.random())))
            h.crab = Crab(strategy=0, rent=ANCHOR_RENT,
                          tenure=1 + int(rng.random() * p.j_max), c_persist=cp)
            h.ask = ANCHOR_RENT

    M_obs = ANCHOR_RENT          # endogenous: last year's mean realised new let
    M_hist = [M_obs]
    total_years = mp.burn_years + mp.meas_years

    for t in range(total_years):
        measuring = t >= mp.burn_years
        R = rec if measuring else None
        yi = t - mp.burn_years
        drift_t = drift

        # ---- GATE 3 V8: a supply shock. Habitats are ADDED; nothing about
        # rents is imposed.
        if measuring and mp.completions_frac > 0.0 and \
                mp.completions_year <= yi < mp.completions_year + mp.completions_span:
            add = int(round(mp.completions_frac * U / mp.completions_span))
            for s in range(S):
                for _ in range(add):
                    stations[s].append(Hab(crab=None, ask=M_obs))

        # ---- 1. stations post asking rents against their OWN observed vacancy
        for s in range(S):
            hs = stations[s]
            vac_rate = sum(1 for h in hs if h.crab is None) / max(1, len(hs))
            adj = 1.0 - VAC_ADJUST * (vac_rate - V_TARGET)
            for h in hs:
                if h.crab is None:
                    base = max(0.3 * ANCHOR_RENT,
                               M_obs * adj * (1.0 + drift_t))
                    if h.ask0 <= 0.0:
                        h.ask0 = base
                    h.ask = base * max(0.60, 1.0 - DOM_CUT * h.dom)
                    if R is not None:
                        rec["ask_sum"] += h.ask
                        rec["ask_n"] += 1.0

        # ---- 2. RENEWAL channel
        pool = []
        for s in range(S):
            for h in stations[s]:
                if R is not None:
                    rec["habitat_years"] += 1.0
                if h.crab is None:
                    if R is not None:
                        rec["vacant_years"] += 1.0
                    continue
                if R is not None:
                    rec["occupied_years"] += 1.0
                crab = h.crab
                u = rng.random(32)
                j = min(crab.tenure, p.j_max)
                M_relet = M_obs * (1.0 - VAC_ADJUST * 0.0)
                wa_t, wa_l, rt, rl, prec = renewal_walkaways(
                    p, mp, crab, u, M_obs, M_relet, len(stations[s]))
                # --- AMENDMENT 6a: the two clocks -------------------------
                # Private draws: this tenant's lead time, its exogenous response
                # delay, and whether it has secured an alternative. The landlord
                # NEVER sees any of these.
                lead = float(np.exp(np.log(LEAD_MEDIAN)
                                    + LEAD_SIGMA * _norm_ppf(u[11])))
                elapsed = float(int(u[12] * (RESP_DELAY_MAX + 1)))
                secured = bool(u[13] < mp.secured_share)
                if mp.deadline_shape:
                    if mp.tenant_clock_linear:
                        cm, cliff = ((1.0, 0.0) if secured
                                     else (1.3055, 0.6667 * elapsed))
                    else:
                        cm, cliff = tenant_clock_multiplier(
                            lead, elapsed, NOTICE_WINDOW, secured)
                    wa_t = wa_t * cm + cliff * M_obs
                    # the landlord's clock is LINEAR in elapsed periods: delay
                    # eats marketing lead time and so adds to expected vacancy.
                    # No cliff, per A6a.3.
                    wa_l = wa_l + p.vacancy * LAND_LIN_RATE * elapsed * M_obs
                    rl = rl - p.vacancy * LAND_LIN_RATE * elapsed * M_obs
                    rt = 12.0 * M_obs + wa_t
                # K26 AUDIT (default OFF, so every previously reported cell is
                # bit-identical). A COSTLY, VERIFIABLE SIGNAL -- not an
                # information leak. A tenant that has actually secured an
                # alternative may PROVE it (forward the offer letter, show the
                # holding deposit) at `signal_cost` months of rent. The landlord
                # responds to the PROOF, never to the private draw: only a tenant
                # who really holds an alternative can produce one, so an
                # unsecured tenant cannot mimic it, and a tenant who does not
                # bother to prove is treated exactly as before. That is what
                # separates this from the bug that manufactured K19.
                #
                # K26 as reported forbade this channel entirely, which made the
                # landlord structurally incapable of responding to an
                # alternative -- so its "+$17, shopping around does not help"
                # was a property of the setup and not of the world.
                proved = _signal_proved(mp, secured)
                _sigcost = mp.signal_cost * M_obs if proved else 0.0
                # SYMMETRIC INFORMATION. The offer is built from the population
                # lead-time distribution and from observables the landlord really
                # has (tenure, and the lease-end date it wrote). It uses no
                # realised private draw -- this is the exact hole that
                # manufactured K19, and a test asserts it.
                wa_t_base = (p.move_med + float(attach(p, j))
                             + SEARCH_COST) * M_obs
                if proved:
                    # a tenant holding a proven alternative has no cliff: its
                    # walk-away is the flat floor, and the landlord knows it
                    wa_t_exp = wa_t_base
                elif mp.deadline_shape:
                    if mp.tenant_clock_linear:
                        wa_t_exp = wa_t_base * 1.3055 + 0.6667 * elapsed * M_obs
                    else:
                        nodes = lead_time_nodes()
                        tot = 0.0
                        for L in nodes:
                            c, k = tenant_clock_multiplier(float(L), elapsed,
                                                           NOTICE_WINDOW, False)
                            tot += wa_t_base * c + k * M_obs
                        wa_t_exp = tot / len(nodes)
                else:
                    wa_t_exp = wa_t_base
                rt_pop = 12.0 * M_obs + wa_t_exp
                zone = rt_pop - rl
                offer_annual = rl + mp.lambda_split * max(zone, 0.0)
                offer = offer_annual / 12.0
                h.prior_rent = crab.rent
                if R is not None:
                    rec["n_renewal"] += 1.0
                    eb = min(int(elapsed), 3)
                    rec[f"renew_elapsed{eb}_n"] += 1.0
                    rec[f"renew_elapsed{eb}_offer"] += offer_annual / (12.0 * M_obs)
                    rec["lead_sum"] += lead
                    rec["elapsed_sum"] += elapsed
                    if secured:
                        rec["secured_n"] += 1.0
                        rec["secured_offer"] += offer_annual / (12.0 * M_obs)
                    else:
                        rec["unsecured_n"] += 1.0
                        rec["unsecured_offer"] += offer_annual / (12.0 * M_obs)
                    rec["wa_tenant_renew"] += wa_t
                    rec["wa_land_renew"] += wa_l
                    rec["wa_n_renew"] += 1.0
                    rec["zone_renew_sum"] += zone
                    if zone <= 0.0:
                        rec["zone_renew_neg"] += 1.0
                    rec["precedent_paid"] += prec
                if R is not None:
                    # K21, decision-relevant and free of the definitional
                    # benchmark: what THIS tenant would save per year by moving
                    # to a new let, net of its own moving cost amortised over its
                    # expected remaining stay. Recorded for every tenant facing a
                    # renewal -- recording only those who STAYED inverted the
                    # quartile ordering by survivorship.
                    gap = 12.0 * (offer - M_obs)
                    stay = 1.0 / max(float(p_exo(p, j)), 1e-6)
                    net = gap - wa_t / stay
                    q = _mcq_cost(wa_t / M_obs, p)
                    rec["rent_gap_sum"] += gap
                    rec["move_gain_sum"] += net
                    rec["move_gain_n"] += 1.0
                    rec["move_gain_pos"] += 1.0 if net > 0 else 0.0
                    rec[f"move_gain_q{q}"] += net
                    rec[f"move_gain_q{q}_n"] += 1.0
                    rec[f"move_gain_q{q}_pos"] += 1.0 if net > 0 else 0.0
                # exogenous move, then the economic decision
                leaves = u[3] < float(p_exo(p, j))
                if not leaves:
                    leaves = (12.0 * offer) > rt        # zone empty for THIS crab
                if leaves:
                    if R is not None:
                        rec["n_renewal_left"] += 1.0
                        rec["move_cost_paid"] += wa_t
                        rec["turn_cost_paid"] += p.turn_cost * M_obs
                        rec["turn_events"] += 1.0
                        rec["surplus_renew"] += -wa_t - _sigcost
                        rec["surplus_renew_n"] += 1.0
                    if u[7] >= mp.exit_share:
                        if mp.derive_switching:
                            _a8_enter(crab, rng_a8, secured)
                        pool.append((int(u[9] * MONTHS), _to_searcher(crab, u)))
                    h.crab = None
                    h.dom = 0.0
                    h.ask = h.ask0 = 0.0
                else:
                    crab.rent = offer
                    crab.tenure += 1
                    if R is not None:
                        rec["n_renewal_signed"] += 1.0
                        rec["renew_growth_sum"] += offer / h.prior_rent - 1.0
                        rec["renew_growth_n"] += 1.0
                        rec["renew_ratio_sum"] += offer / M_obs
                        rec["renew_rent_sum"] += offer
                        sur = 12.0 * M_obs - 12.0 * offer - _sigcost
                        rec["surplus_renew"] += sur
                        rec["surplus_renew_n"] += 1.0
                        rec["crab_cash"] += 12.0 * offer
                        rec["station_cash"] += 12.0 * offer
                        q = _mcq(crab, u, p)
                        rec[f"surp_renew_q{q}"] += sur
                        rec[f"surp_renew_q{q}_n"] += 1.0
                        rec["sitting_rent_sum"] += offer
                        rec["sitting_rent_n"] += 1.0
                        _sur = 12.0 * M_obs - 12.0 * offer - _sigcost
                        rec[f"renew_elapsed{min(int(elapsed),3)}_surp"] += _sur
                        if secured:
                            rec["secured_surp"] += _sur
                        else:
                            rec["unsecured_surp"] += _sur

        # ---- 3. NEW LET channel, in MONTHLY sub-periods (A5a.3). Vacancy is a
        # flow, so it must be accumulated per month, and days-on-market must be
        # real state rather than a per-year label.
        n_in_year = (searcher_inflow_at(mp.searcher_inflow, M_obs,
                                        mp.eta_demand)
                     * sum(len(x) for x in stations))
        by_month = [[] for _ in range(MONTHS)]
        for mth, c in pool:
            by_month[min(mth, MONTHS - 1)].append(c)
        carry = []
        for mo in range(MONTHS):
            carry.extend(by_month[mo])
            for _ in range(int(round(n_in_year / MONTHS))):
                u = rng.random(32)
                cp = float(np.exp(np.log(p.move_med) + p.move_sigma
                                  * _norm_ppf(u[0])))
                _nc = Crab(strategy=0, rent=0.0, tenure=0, c_persist=cp)
                if mp.derive_switching:
                    # inflow searchers are NOT sitting tenants leaving a habitat,
                    # so they are marked and excluded from the derived switching
                    # cost: a household forming is not a household switching.
                    _a8_enter(_nc, rng_a8, False, mover=False)
                carry.append(_nc)
            # habitats vacated by this year's renewals are listed now
            for si in range(len(stations)):
                for h in stations[si]:
                    if h.crab is None and h.ask <= 0.0:
                        h.ask = h.ask0 = M_obs
            listings = [(si, i) for si in range(len(stations))
                        for i, h in enumerate(stations[si]) if h.crab is None]
            # vacancy is a FLOW: charge every empty habitat this month
            if R is not None:
                rec["vacancy_lost"] += len(listings) * M_obs
                rec["vacant_months"] += len(listings)
            if mp.derive_switching:
                for _c in carry:
                    _c.a8_months = getattr(_c, "a8_months", 0.0) + 1.0
            if not listings:
                if mp.derive_switching:
                    _survive = [c for c in carry if rng.random() >= 0.25]
                    _a8_giveups(rec, carry, _survive, mp)
                    carry = _survive
                else:
                    carry = [c for c in carry if rng.random() >= 0.25]
                continue
            tightness = max(len(carry), 1) / len(listings)
            rng.shuffle(carry)
            still = []
            for crab in carry:
                listings = [(si, i) for si in range(len(stations))
                            for i, h in enumerate(stations[si])
                            if h.crab is None]
                if not listings:
                    still.append(crab)
                    continue
                u = rng.random(32)
                if mp.derive_switching:
                    # one listing seriously engaged this month: the viewing, the
                    # application, the fee. A month that ends without a match is
                    # a rejection, and it costs another attempt and another month
                    # next time round -- so rejection is priced by the dynamics.
                    crab.a8_attempts = getattr(crab, "a8_attempts", 0.0) + 1.0
                    if getattr(crab, "a8_tight0", None) is None:
                        crab.a8_tight0 = float(tightness)
                k = min(K_VISIBLE, len(listings))
                idx = rng.choice(len(listings), size=k, replace=False)
                seen = sorted((listings[i] for i in idx),
                              key=lambda si: stations[si[0]][si[1]].ask)
                si, i = seen[0]
                h = stations[si][i]
                next_best = (stations[seen[1][0]][seen[1][1]].ask if k > 1
                             else h.ask * 1.05)
                wa_t, wa_l, rt, rl, wait = newlet_walkaways(
                    p, mp, h.ask, next_best, len(stations[si]), tightness, h.dom)
                # K23: what the TENANT believes the landlord's walk-away is. A
                # tenant blind to timing assumes a fresh listing (dom = 0); one
                # given the true state sees the weaker reservation. This is
                # exactly `their_batna_estimate` in the engine's interface.
                if mp.tenant_sees_dom:
                    rl_believed = rl
                else:
                    _, _, _, rl0, _ = newlet_walkaways(
                        p, mp, h.ask, next_best, len(stations[si]), tightness,
                        0.0)
                    rl_believed = rl0
                zone = rt - rl_believed
                if R is not None:
                    rec["n_newlet"] += 1.0
                    rec["wa_tenant_newlet"] += wa_t
                    rec["wa_land_newlet"] += wa_l
                    rec["wa_n_newlet"] += 1.0
                    rec["zone_newlet_sum"] += rt - rl
                    rec["wait_sum"] += wait
                    db = _dom_bucket(h.dom)
                    rec[f"zone_dom{db}"] += rt - rl
                    rec[f"zone_dom{db}_n"] += 1.0
                    # the identity A5a.3 requires: the landlord's reservation, as
                    # a share of its own ask, must fall monotonically in dom
                    rec[f"resv_dom{db}"] += rl / (12.0 * h.ask)
                    rec[f"resv_dom{db}_n"] += 1.0
                if zone <= 0.0:
                    still.append(crab)
                    if R is not None:
                        rec["zone_newlet_neg"] += 1.0
                    continue
                proposed = (rl_believed + mp.lambda_split * zone) / 12.0
                if 12.0 * proposed < rl - 1e-9:
                    still.append(crab)          # below the landlord's true floor
                    continue
                signed = proposed
                prior = h.prior_rent if h.prior_rent > 0 else M_obs
                depth = (h.ask0 - signed) / h.ask0
                crab.rent = signed
                crab.tenure = 1
                if R is not None:
                    rec["n_newlet_signed"] += 1.0
                    rec["newlet_growth_sum"] += signed / prior - 1.0
                    rec["newlet_growth_n"] += 1.0
                    rec["newlet_ratio_sum"] += signed / M_obs
                    rec["newlet_vs_ask_sum"] += signed / h.ask
                    rec["newlet_rent_sum"] += signed
                    rec["depth_sum"] += depth
                    rec["dom_sum"] += h.dom
                    db = _dom_bucket(h.dom)
                    rec[f"depth_dom{db}"] += depth
                    rec[f"depth_dom{db}_n"] += 1.0
                    # depth measured off the CONTEMPORANEOUS MARKET rent instead
                    # of the listing's own ask, which removes the cross-sectional
                    # ask-dispersion confound
                    rec[f"dvm_dom{db}"] += (M_obs - signed) / M_obs
                    rec[f"dvm_dom{db}_n"] += 1.0
                    sur = 12.0 * M_obs - 12.0 * signed
                    rec["surplus_newlet"] += sur
                    rec["surplus_newlet_n"] += 1.0
                    rec["crab_cash"] += 12.0 * signed
                    rec["station_cash"] += 12.0 * signed
                if mp.derive_switching:
                    _a8_record(rec, crab, mp, matched=True)
                h.crab = crab
                h.dom = 0.0
                h.ask0 = 0.0
            # unmatched habitats age; unmatched searchers mostly persist
            for si in range(len(stations)):
                for h in stations[si]:
                    if h.crab is None:
                        h.dom += 1.0
            if mp.derive_switching:
                _survive = [c for c in still if rng.random() >= 0.25]
                _a8_giveups(rec, still, _survive, mp)
                carry = _survive
            else:
                carry = [c for c in still if rng.random() >= 0.25]
        if R is not None:
            rec["n_unmatched"] += len(carry)

        # ---- 4. vacancy loss, and the ENDOGENOUS market statistic
        n_vac = 0
        for s in range(len(stations)):
            for h in stations[s]:
                if h.crab is None:
                    n_vac += 1
        lets = rec["newlet_rent_sum"], rec["newlet_growth_n"]
        signed_this_year = _mean_signed(stations, M_obs)
        M_new = signed_this_year if signed_this_year > 0 else M_obs
        M_obs = 0.5 * M_obs + 0.5 * M_new * (1.0 + drift_t)
        M_hist.append(M_obs)
        if measuring and record_series:
            tot = sum(len(x) for x in stations)
            series.append(dict(
                year=yi, market=M_obs, vacancy=n_vac / max(1, tot),
                renew_growth=_safe(rec["renew_growth_sum"],
                                   rec["renew_growth_n"]),
                newlet_growth=_safe(rec["newlet_growth_sum"],
                                    rec["newlet_growth_n"]),
                renew_ratio=_safe(rec["renew_ratio_sum"],
                                  rec["n_renewal_signed"]),
                newlet_ratio=_safe(rec["newlet_ratio_sum"],
                                   rec["n_newlet_signed"])))
    rec["_M_hist"] = M_hist
    if record_series:
        rec["_series"] = series
    return rec


def _mean_signed(stations, fallback):
    """The endogenous market rent: mean rent of record among tenants who signed
    within the last year (tenure 1). A statistic of realised lets, not an input."""
    vals = [h.crab.rent for s in stations for h in s
            if h.crab is not None and h.crab.tenure <= 1]
    return float(np.mean(vals)) if vals else 0.0


def _dom_bucket(dom: float) -> int:
    """Days-on-market buckets, in months: 0, 1-2, 3-5, 6+."""
    if dom < 1.0:
        return 0
    if dom < 3.0:
        return 1
    if dom < 6.0:
        return 2
    return 3


def _mcq_cost(c_months, p):
    """Quartile of the REALISED total switching cost (months of market rent).
    q0 = cheapest to move."""
    for q, edge in enumerate((p.move_med * 0.75, p.move_med * 1.15,
                              p.move_med * 1.75)):
        if c_months < edge:
            return q
    return 3


def _mcq(crab, u, p):
    """Moving-cost quartile, for K21's matched comparison."""
    c = crab.c_persist
    for q, edge in enumerate((p.move_med * 0.62, p.move_med,
                              p.move_med * 1.62)):
        if c < edge:
            return q
    return 3


def _safe(a, b):
    return a / b if b else float("nan")


def _to_searcher(crab, u):
    crab.tenure = 0
    crab.rent = 0.0
    return crab


# ------------------------------- AMENDMENT 8: switching cost as an output ----
# All four helpers are inert unless `MarketParams.derive_switching` is set, and
# every random draw they make comes from `rng_a8`, a stream of their own. So the
# derivation cannot move a single previously reported market number -- asserted
# by a test rather than claimed.

def _a8_enter(crab, rng_a8, secured: bool, mover: bool = True) -> None:
    """A crab enters the search pool. `mover=False` marks an inflow searcher --
    a household forming, not a household switching -- which is counted in the
    matching but excluded from the derived switching-cost distribution."""
    crab.a8_attempts = 0.0
    crab.a8_months = 0.0
    crab.a8_tight0 = None
    crab.a8_mover = bool(mover)
    crab.a8_secured = bool(secured)
    crab.a8_logged = False       # a crab that moved once may move again years
                                 # later; without this reset only FIRST spells
                                 # would ever be logged, which would bias the
                                 # distribution toward whoever moves least
    # broker-fee market: drawn once per search, from the A8 stream only
    from crabs.searchcost import BROKER_SHARE
    crab.a8_broker = bool(rng_a8.random() < BROKER_SHARE)


def _a8_record(rec, crab, mp, matched: bool) -> None:
    if not getattr(crab, "a8_mover", False):
        return                       # inflow searcher: not a switch
    if getattr(crab, "a8_logged", False):
        return                       # a crab may re-enter later; log each spell
    from crabs.searchcost import derived_cost
    crab.a8_logged = True
    c = derived_cost(getattr(crab, "a8_attempts", 0.0),
                     getattr(crab, "a8_months", 0.0),
                     getattr(crab, "a8_broker", False))
    rec["_derived"].append(dict(
        cost=c, attempts=float(getattr(crab, "a8_attempts", 0.0)),
        months=float(getattr(crab, "a8_months", 0.0)),
        broker=bool(getattr(crab, "a8_broker", False)),
        secured=bool(getattr(crab, "a8_secured", False)),
        tightness=getattr(crab, "a8_tight0", None),
        matched=bool(matched)))


def _a8_giveups(rec, before, after, mp) -> None:
    """PRINCIPLE D. A searcher that gives up has, by construction, the longest
    and most expensive search. Recording only the ones that matched would make
    the derived median a survivorship statistic -- artefact #5's exact shape,
    which this study has already made once. So give-ups are logged too, and the
    unconditional figure is the one A8 reports."""
    keep = {id(c) for c in after}
    for c in before:
        if id(c) not in keep:
            _a8_record(rec, c, mp, matched=False)

"""AMENDMENT 3 §A3.1 — route the negotiation through the ACTUAL SNHP engine.

Phase 1 tested a hand-rolled `RANKED_LADDER` against a hand-rolled
`PRICE_LADDER`. K1 therefore fired against our own reimplementation of ranked
asks, not against the product. This module fixes that: the crab's side of every
negotiation is `gametheory.negotiation.bundle.negotiate_bundle` for the
multi-issue arm and `gametheory.negotiation.plain_terms.negotiate_turn` for the
single-issue arm.

What is and is not given to the engine:

  * The crab supplies its own utility vectors (from `demographics`) and its own
    Dirichlet priority weights.
  * The crab supplies only the *direction* of the station's preference on each
    issue -- what any tenant would guess (landlords want more rent, longer
    leases, smaller credits, fees kept). It does NOT supply the station's
    relative priorities across issues. **The engine infers those from the
    station's offers, and that inference is the product**, so it is not
    bypassed.
  * The station answers with its own NPV, using the same economics as Phase 1,
    generalised from one instrument at a time to a full bundle.

Metrics (all three reported, because they can disagree):
  cash      12*M - cash paid. The Phase-1 metric and the units K1/K13 are
            written in. PRIMARY.
  welfare   cash plus the subjective premium a tenant with unusual priorities
            places on the non-cash dimensions. The economically correct measure.
  engine    the engine's own normalised `my_utility` score.
"""
from __future__ import annotations

import numpy as np

from crabs.demographics import ISSUES, Tenant, crra, draw_tenant
from crabs.world import Params, attach, q_sit

# option grids. Rent is a multiple of the station's standing offer; 0.89 is the
# 11%-of-annual-rent ask Phase 1 used, so the two are comparable.
RENT_FACTORS = (1.00, 0.97, 0.94, 0.89, 1.03, 1.06)
RENT_LABELS = ("as offered", "-3%", "-6%", "-11%", "+3%", "+6%")
N_TENANT_RENT = 4        # the tenant only ever asks for LESS; indices 4-5 exist
                         # so an engine-armed LANDLORD can open ABOVE its plain
                         # DP optimum and hand back a sweetener (AMENDMENT 4)
CREDIT_MONTHS = (0.0, 0.46, 0.92, 1.38)          # 0 / 2 / 4 / 6 weeks
CREDIT_LABELS = ("0wk", "2wk", "4wk", "6wk")
TERM_LABELS = ("12mo", "24mo")
FEE_LABELS = ("keep", "waive")

THEIR_BATNA_ESTIMATE = 0.45      # the tool's informed default: a landlord with
                                 # turnover exposure sits below the midpoint
N_ROUNDS = 3


class Bundle:
    """(rent factor index, credit index, fees waived, 24-month term)."""
    __slots__ = ("ri", "ci", "fee", "term")

    def __init__(self, ri=0, ci=0, fee=False, term=False):
        self.ri, self.ci, self.fee, self.term = ri, ci, bool(fee), bool(term)

    def key(self):
        return (self.ri, self.ci, self.fee, self.term)

    def is_null(self):
        return self.ri == 0 and self.ci == 0 and not self.fee and not self.term


# --------------------------------------------------------- tenant-side values
def issue_dollars(p: Params, ten: Tenant, q, M, g_obs, b: Bundle) -> dict:
    """Dollar value of a bundle to the tenant, decomposed by issue, relative to
    the station's standing offer `q` (a ratio of market rent M)."""
    rent_gain = 12.0 * (q - q * RENT_FACTORS[b.ri]) * M
    credit = CREDIT_MONTHS[b.ci] * M
    fees = (p.fee_cap_frac * 12.0 * q * M * (1.0 + p.disc_crab)) if b.fee else 0.0
    if b.term:
        locked = q * RENT_FACTORS[b.ri] * M
        m_next = M * (1.0 + g_obs)
        flex = ten.job_flex if ten is not None else 0.4
        term = p.disc_crab * 12.0 * (m_next - locked) - 0.5 * M * flex
    else:
        term = 0.0
    return {"rent": rent_gain, "term": term, "one_time_credit": credit,
            "fees": fees}


def welfare_premium(ten, dollars: dict) -> float:
    """The extra subjective value a tenant with unusual priorities puts on the
    non-cash dimensions. Weights are normalised to mean 1, so a tenant with
    average priorities has a premium of exactly zero and `welfare == cash`. With
    no demographic draw (the Phase 1 code path) it is identically zero."""
    if ten is None:
        return 0.0
    return sum((4.0 * w - 1.0) * dollars[k] for w, k in zip(ten.w, ISSUES))


def build_issues(p: Params, ten: Tenant, q, M, g_obs):
    """The four issues, with the tenant's real utilities and only the DIRECTION of
    the station's preferences."""
    res = ten.income - 12.0 * q * M          # residual income at the offer
    mu = float(crra(res + 1000.0) - crra(res)) / 1000.0   # marginal utility of $
    fac = RENT_FACTORS[:N_TENANT_RENT]
    my_rent = [float(crra(ten.income - 12.0 * q * f * M)) for f in fac]
    out = [{"name": "rent", "options": list(RENT_LABELS[:N_TENANT_RENT]),
            "my_utility": my_rent,
            "their_utility": [3.0, 2.0, 1.0, 0.0]}]
    b12, b24 = Bundle(term=False), Bundle(term=True)
    t12 = issue_dollars(p, ten, q, M, g_obs, b12)["term"]
    t24 = issue_dollars(p, ten, q, M, g_obs, b24)["term"]
    out.append({"name": "term", "options": list(TERM_LABELS),
                "my_utility": [mu * t12, mu * t24],
                "their_utility": [0.0, 1.0]})
    out.append({"name": "one_time_credit", "options": list(CREDIT_LABELS),
                "my_utility": [mu * c * M for c in CREDIT_MONTHS],
                "their_utility": [3.0, 2.0, 1.0, 0.0]})
    fee_val = p.fee_cap_frac * 12.0 * q * M * (1.0 + p.disc_crab)
    out.append({"name": "fees", "options": list(FEE_LABELS),
                "my_utility": [0.0, mu * fee_val],
                "their_utility": [1.0, 0.0]})
    if p.drop_term:
        out = [i for i in out if i["name"] != "term"]
    return out, mu


def tenant_batna_normalised(p: Params, ten: Tenant, q, r, j, M, c_tot_months):
    """Where the tenant's walk-away sits on the 0..1 scale the engine uses: the
    utility of leaving, placed between the worst and best packages on the table."""
    worst = float(crra(ten.income - 12.0 * q * M))
    best = float(crra(ten.income - 12.0 * q
                      * RENT_FACTORS[N_TENANT_RENT - 1] * M))
    outside = float(crra(ten.income - 12.0 * M - c_tot_months * M))
    if best <= worst + 1e-12:
        return 0.5
    return float(np.clip((outside - worst) / (best - worst), 0.0, 1.0))


# --------------------------------------------------------- station-side value
def bundle_npv(dp, p: Params, j, r, q, b: Bundle, tmul=None, vmul=1.0,
               counterer=True) -> float:
    """Station NPV of a full bundle. Same economics as Phase 1's single-instrument
    evaluator, generalised: a rent cut moves the rent of record (and, for an
    institution, capitalised face rent); a credit and a fee waiver are cash only;
    a 24-month term freezes two years and removes one year of turnover risk."""
    prim = getattr(dp, "prim", None)
    fp = p.face_premium * (prim["face_mult"] if prim else 1.0)
    nonpec = prim["nonpec"] if prim else 0.0
    d = p.disc_station
    d1 = d * (1.0 + dp.gv)
    g = dp.g
    face = q * RENT_FACTORS[b.ri]
    credit = CREDIT_MONTHS[b.ci]
    fee = (p.fee_cap_frac * 12.0 * q * (1.0 + d)) if b.fee else 0.0
    cash_out = credit + fee
    qs = float(q_sit(p, j))
    aj = float(attach(p, j))
    # the station reads the crab's non-rent value in cash terms
    z = credit + ((p.fee_cap_frac * 12.0 * q * (1.0 + p.disc_crab)) if b.fee
                  else 0.0)
    if b.term:
        z += dp._term_crab_value(p, q, face, j, g)
    gain = (12.0 * p.kappa_crab * (face - 1.0)
            + p.lambda_ref * 12.0 * (face - r) - aj - z)
    ptab = getattr(dp, "ptab_counter", dp.ptab) if counterer else \
        getattr(dp, "ptab_uncond", dp.ptab)
    pl = float(np.interp(gain, _GG, ptab[min(int(j), p.j_max)]))
    turn = dp._turn_val(dp.V, j, tmul, vmul)
    if isinstance(turn, tuple):
        turn = turn[0]
    j2 = min(j + 1, p.j_max)
    if b.term:
        j3 = min(j + 2, p.j_max)
        p2 = float(np.interp(0.0, [0.0, 1.0], [0.0, 0.0]))  # placeholder, set below
        from crabs.world import p_exo
        p2 = float(p_exo(p, min(j + 1, p.j_max))) * p.break_damp
        yr2 = (12.0 * face * (1.0 + fp) + nonpec
               + d * (1.0 + dp.gv) ** 2
               * float(dp._Vg(dp.V, face / (1.0 + g) ** 2, j3)))
        yr2_break = (p.break_fee * face
                     + (12.0 - min(p.vacancy * vmul, 11.0)) * (1.0 + g)
                     * (1.0 + fp) - p.turn_cost - p.q_new
                     + d * (1.0 + dp.gv) ** 2
                     * float(dp._Vg(dp.V, 1.0 / (1.0 + g), 1)))
        stay = (12.0 * face * (1.0 + fp) - cash_out - qs + nonpec
                + d * ((1.0 - p2) * yr2 + p2 * yr2_break))
    else:
        stay = (12.0 * face * (1.0 + fp) - cash_out - qs + nonpec
                + d1 * float(dp._Vg(dp.V, face / (1.0 + g), j2)))
    return (1.0 - pl) * stay + pl * turn


_GG = np.round(np.arange(-40.0, 40.0 + 1e-9, 0.01), 6)

# the station's own counter set: the bundles it is willing to put on the table
STATION_BUNDLES = [Bundle(ri, ci, fee, term)
                   for ri in (0, 1)
                   for ci in (0, 1, 2)
                   for fee in (False, True)
                   for term in (False, True)]


def station_counter(dp, p, j, r, q, ten, M, g_obs, prev_util, tmul, vmul):
    """The station's reply: the bundle maximising its own NPV among those that are
    an improvement for the tenant on its previous offer. Returns None to hold
    firm."""
    base = bundle_npv(dp, p, j, r, q, Bundle(), tmul, vmul)
    best, best_v = None, base
    for b in STATION_BUNDLES:
        if b.is_null():
            continue
        d = issue_dollars(p, ten, q, M, g_obs, b)
        util = sum(d.values()) + welfare_premium(ten, d)
        if util <= prev_util + 1e-9:
            continue
        v = dp.decision_value_bundle(p, j, r, q, b, tmul, vmul) \
            if hasattr(dp, "decision_value_bundle") \
            else bundle_npv(dp, p, j, r, q, b, tmul, vmul)
        if v > best_v:
            best, best_v = b, v
    return best


# ------------------------------------------------------------- the negotiation
def negotiate_with_engine(dp, p: Params, ten: Tenant, crab, q, r, j, M, g_obs,
                          c_tot, seed, tmul=None, vmul=1.0, multi=True, u=None):
    """One renewal, negotiated by the real engine on the tenant's side.

    multi=True  -> negotiate_bundle over four issues (the product)
    multi=False -> negotiate_turn on rent alone (the single-issue control)

    Returns (Bundle | None, rounds, asked, engine_utility)."""
    from gametheory.negotiation.bundle import negotiate_bundle
    from gametheory.negotiation.plain_terms import negotiate_turn

    issues, mu = build_issues(p, ten, q, M, g_obs)
    batna = tenant_batna_normalised(p, ten, q, r, j, M, c_tot)
    their_offers = [{"rent": RENT_LABELS[0], "term": TERM_LABELS[0],
                     "one_time_credit": CREDIT_LABELS[0],
                     "fees": FEE_LABELS[0]}]
    prio = {k: float(w) for k, w in zip(ISSUES, ten.w)}
    accepted = Bundle()
    prev_util = 0.0
    eng_util = None

    if not multi:
        # single-issue control: rent only, in real dollars
        ceiling = 12.0 * M + c_tot * M          # what leaving would cost per year
        aspiration = 12.0 * q * RENT_FACTORS[N_TENANT_RENT - 1] * M
        if not (aspiration < ceiling):
            # the crab is already paying more than leaving would cost: there is no
            # single-issue bargaining range at all, which is itself the answer
            return None, 0, True, None
        res = negotiate_turn(side="buy", walk_away=float(ceiling),
                             target=float(aspiration),
                             counterparty_offers=[float(12.0 * q * M)],
                             rounds_left=N_ROUNDS, item="this renewal")
        if res["action"] not in ("counter", "accept"):
            return None, 0, False, None
        want = float(res.get("recommended_price") or 12.0 * q * M)
        # nearest rent option at or above what the engine asks for
        target_f = want / (12.0 * q * M) if q > 0 else 1.0
        ri = int(np.argmin([abs(f - target_f) for f in RENT_FACTORS]))
        for cand in range(ri, N_TENANT_RENT):
            b = Bundle(ri=cand)
            if bundle_npv(dp, p, j, r, q, b, tmul, vmul) >= \
                    bundle_npv(dp, p, j, r, q, Bundle(), tmul, vmul):
                return b, 1, True, None
        return None, 1, True, None

    for rnd in range(N_ROUNDS):
        # PROTOCOL PARITY: the station's patience is finite here exactly as it is
        # for the hand-rolled ladder. Without this the engine gets unconditional
        # rounds the ladder does not, which would flatter the engine.
        if rnd >= 1 and u is not None:
            from crabs.world import U_PATIENCE
            if u[U_PATIENCE + min(rnd - 1, 3)] > p.p_continue:
                break
        res = negotiate_bundle(
            issues=issues, their_offers=their_offers, my_priorities=prio,
            my_batna=batna, their_batna_estimate=THEIR_BATNA_ESTIMATE,
            seed=int(seed) + rnd, rounds_left=N_ROUNDS - rnd)
        eng_util = res.get("my_utility")
        if res["action"] == "accept":
            break
        if res["action"] in ("walk", "use_negotiate_turn"):
            break
        off = res.get("recommended_offer") or {}
        ask = Bundle(
            ri=RENT_LABELS.index(off.get("rent", RENT_LABELS[0])),
            ci=CREDIT_LABELS.index(off.get("one_time_credit",
                                           CREDIT_LABELS[0])),
            fee=(off.get("fees") == FEE_LABELS[1]),
            term=(off.get("term") == TERM_LABELS[1]))
        base = bundle_npv(dp, p, j, r, q, accepted, tmul, vmul)
        if bundle_npv(dp, p, j, r, q, ask, tmul, vmul) >= base:
            return ask, rnd + 1, True, eng_util          # station accepts
        cnt = station_counter(dp, p, j, r, q, ten, M, g_obs, prev_util, tmul,
                              vmul)
        if cnt is None:
            return (None if accepted.is_null() else accepted), rnd + 1, True, \
                eng_util
        accepted = cnt
        d = issue_dollars(p, ten, q, M, g_obs, cnt)
        prev_util = sum(d.values()) + welfare_premium(ten, d)
        their_offers.append({"rent": RENT_LABELS[cnt.ri],
                             "term": TERM_LABELS[1 if cnt.term else 0],
                             "one_time_credit": CREDIT_LABELS[cnt.ci],
                             "fees": FEE_LABELS[1 if cnt.fee else 0]})
    return (None if accepted.is_null() else accepted), N_ROUNDS, True, eng_util


# ------------------------------------------------- accounting for a Bundle
def bundle_effects(p: Params, ten: Tenant, q, b: Bundle, M, g_obs):
    """(effective rent ratio, cash-equivalent non-rent value in months of market
    rent, station cash cost this year in months, locked years) -- the Bundle
    analogue of `StationDP.package_effects`, so the leave decision and the ledger
    stay on Phase 1's footing."""
    face = q * RENT_FACTORS[b.ri]
    credit = CREDIT_MONTHS[b.ci]
    fee_yr = p.fee_cap_frac * 12.0 * q if b.fee else 0.0
    z = credit + fee_yr * (1.0 + p.disc_crab)
    if b.term:
        z += p.disc_crab * 12.0 * ((1.0 + g_obs) - face) \
            - 0.5 * (ten.job_flex if ten is not None else 0.4)
    return face, z, credit + fee_yr, (1 if b.term else 0)


def apply_bundle(p: Params, crab, q, b: Bundle, M) -> float:
    """Realise the bundle on the crab. Returns this year's one-time cash credit in
    dollars (the fee waiver is carried in crab state, as in Phase 1)."""
    face = q * RENT_FACTORS[b.ri]
    crab.rent = face * M
    if b.fee:
        crab.fee_years = 2
        crab.fee_value = p.fee_cap_frac * 12.0 * q * M
    if b.term:
        crab.locked = 1
    return CREDIT_MONTHS[b.ci] * M


def ladder_to_bundle(p, q, won):
    """FAIRNESS DIAGNOSTIC support: express a set of single-instrument ladder
    grants as one Bundle, so a multi-grant ladder and a bundle are scored by the
    same accounting."""
    from crabs.world import FEES, ONE_TIME, RENT, TERM
    b = Bundle()
    for kind, size in won:
        if kind == ONE_TIME:
            want = size * p.ask_frac * 12.0 * q
            b.ci = max(b.ci, int(np.argmin([abs(c - want)
                                            for c in CREDIT_MONTHS])))
        elif kind == FEES:
            b.fee = True
        elif kind == TERM:
            b.term = True
        elif kind == RENT:
            want = 1.0 - size * p.ask_frac
            b.ri = max(b.ri, int(np.argmin([abs(f - want)
                                            for f in RENT_FACTORS])))
    return b

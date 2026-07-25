"""AMENDMENT 4 — the engine matrix. Who is holding the engine?

Four cells, same world, same demographics, same seeds; only the negotiation
policy differs.

    N/N  neither side uses SNHP -- the control every comparison is against
    T/N  tenant has SNHP (what we sell)
    N/L  LANDLORD has SNHP (the more probable commercial deployment, untested)
    T/L  both

The heuristic side is deliberately built strong: single-issue anchoring with a
satisficing acceptance rule, which is what people actually do, not a strawman. A
weak heuristic would manufacture a T/N win.

**Joint surplus, and why it is the number that matters here.** Rent is a pure
transfer between the two parties, so it cancels in the joint total. What does not
cancel is deadweight -- turn cost, vacancy, and the tenant's moving cost, all
destroyed rather than moved -- and the preference-intensity premium, which is
genuine value created when a tenant who cares about term gets term. So in this
model:

    joint = housing value delivered + preference premium
            - turn cost - vacancy - moving cost

An engine that only shifts cash cannot move joint surplus at all. That is
exactly what makes K17 ("arms race, not value creation") a sharp test rather than
a rhetorical one.
"""
from __future__ import annotations

import numpy as np

from crabs.demographics import ISSUES, Tenant
from crabs.engine_bridge import (CREDIT_LABELS, CREDIT_MONTHS, FEE_LABELS,
                                 N_ROUNDS, N_TENANT_RENT, RENT_FACTORS,
                                 RENT_LABELS, STATION_BUNDLES, TERM_LABELS,
                                 THEIR_BATNA_ESTIMATE, Bundle, build_issues,
                                 bundle_npv, issue_dollars,
                                 tenant_batna_normalised, welfare_premium)
from crabs.world import Params

# --- heuristic parameters. INVENTED (no published counterpart), labelled. ---
SATISFICE_FRAC = 0.40       # a person accepts once they have got this share of
                            # what they asked for
HEUR_ANCHOR = 0.11          # the ask a person opens with: 11% off, the same size
                            # as Phase 1's ask, so the two are comparable
HEUR_ROUNDS = 2
HEUR_BUDGET_FRAC = 0.50     # heuristic landlord's concession budget as a share
                            # of (turn cost + vacancy). INVENTED.


# ------------------------------------------------------------ heuristic tenant
def heuristic_tenant_ask(p: Params, ten: Tenant, q, r, M, g_obs, round_idx):
    """Single-issue anchoring: a person asks for money off the rent, and asks for
    less the second time. No priority inference, no bundling."""
    frac = HEUR_ANCHOR * (1.0 if round_idx == 0 else 0.6)
    target = 1.0 - frac
    ri = int(np.argmin([abs(f - target) for f in RENT_FACTORS]))
    return Bundle(ri=max(ri, 1))


def heuristic_tenant_accepts(p, ten, q, M, g_obs, offered: Bundle,
                             anchor: Bundle) -> bool:
    """Satisficing: accept once the cash on the table reaches a fraction of what
    was asked for. A person does evaluate a credit they were offered -- they just
    do not construct trades."""
    want = sum(issue_dollars(p, ten, q, M, g_obs, anchor).values())
    got = sum(issue_dollars(p, ten, q, M, g_obs, offered).values())
    return got >= SATISFICE_FRAC * max(want, 1e-9)


# ---------------------------------------------------------- heuristic landlord
def heuristic_landlord_reply(dp, p: Params, j, r, q, ten, M, g_obs,
                             ask: Bundle, tmul, vmul):
    """Satisficing on cash cost, with no reading of the tenant's priorities: grant
    the ask if what it costs this year is inside a fixed budget, otherwise offer
    the cheapest single sweetener inside budget, otherwise refuse."""
    budget = HEUR_BUDGET_FRAC * (p.turn_cost + p.vacancy) * (tmul or 1.0)
    cost_of = lambda b: (12.0 * q * (1.0 - RENT_FACTORS[b.ri])
                         + CREDIT_MONTHS[b.ci]
                         + (p.fee_cap_frac * 12.0 * q if b.fee else 0.0))
    if cost_of(ask) <= budget:
        return ask
    for b in (Bundle(ci=1), Bundle(fee=True), Bundle(ri=1)):
        if cost_of(b) <= budget:
            return b
    return None


# ------------------------------------------------------------- SNHP landlord
def landlord_issues(dp, p: Params, j, r, q, tmul, vmul):
    """The landlord's own utility vectors, DERIVED from its NPV -- one number per
    option, holding the other issues at the baseline. Its priorities are the
    NPV range on each issue, normalised: derived, never drawn. It supplies only
    the DIRECTION of the tenant's preferences and lets the engine infer the
    tenant's relative priorities from what the tenant has asked for."""
    base = Bundle()
    def v(b):
        return bundle_npv(dp, p, j, r, q, b, tmul, vmul)
    # Replies are concessions only: the landlord's engine bargains on the same
    # rent grid the tenant can see. The extended upward grid is reachable only by
    # `landlord_opener`, which is a direct NPV search, not an engine call.
    rent_u = [v(Bundle(ri=i)) for i in range(N_TENANT_RENT)]
    term_u = [v(Bundle(term=False)), v(Bundle(term=True))]
    cred_u = [v(Bundle(ci=i)) for i in range(len(CREDIT_MONTHS))]
    fee_u = [v(Bundle(fee=False)), v(Bundle(fee=True))]
    # the tenant's preference DIRECTION on rent: strictly better the lower it is
    their_rent = [-f for f in RENT_FACTORS[:N_TENANT_RENT]]
    issues = [
        {"name": "rent", "options": list(RENT_LABELS[:N_TENANT_RENT]),
         "my_utility": rent_u, "their_utility": their_rent},
        {"name": "term", "options": list(TERM_LABELS), "my_utility": term_u,
         "their_utility": [1.0, 0.0]},
        {"name": "one_time_credit", "options": list(CREDIT_LABELS),
         "my_utility": cred_u, "their_utility": [0.0, 1.0, 2.0, 3.0]},
        {"name": "fees", "options": list(FEE_LABELS), "my_utility": fee_u,
         "their_utility": [0.0, 1.0]},
    ]
    rng = {it["name"]: (max(it["my_utility"]) - min(it["my_utility"]))
           for it in issues}
    tot = sum(rng.values()) or 1.0
    prio = {k: val / tot for k, val in rng.items()}
    lo, hi = v(Bundle(ri=N_TENANT_RENT - 1, ci=len(CREDIT_MONTHS) - 1,
                      fee=True)), v(base)
    turn = dp._turn_val(dp.V, j, tmul, vmul)
    if isinstance(turn, tuple):
        turn = turn[0]
    batna = float(np.clip((turn - lo) / max(hi - lo, 1e-9), 0.0, 1.0))
    return issues, prio, batna


# openers available to an engine-armed LANDLORD: it may open ABOVE its plain DP
# optimum and attach a sweetener, which is the trade Phase 1's arm E found (face
# rent is capitalised, cash concessions are not). Without this the "landlord has
# SNHP" cell can only ever REPLY, and K16 is never given a fair chance to fire.
LANDLORD_OPENERS = [Bundle(ri, ci, fee, term)
                    for ri in (0, 4, 5)
                    for ci in (0, 1, 2, 3)
                    for fee in (False, True)
                    for term in (False, True)]


def landlord_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul):
    """The package an engine-armed landlord OPENS with: the one maximising its own
    NPV among those that leave the tenant no worse off in cash-equivalent terms
    than the plain offer would. Returns the rent factor and the sweetener."""
    base_util = 0.0
    best, best_v = Bundle(), bundle_npv(dp, p, j, r, q, Bundle(), tmul, vmul)
    for b in LANDLORD_OPENERS:
        d = issue_dollars(p, ten, q, M, g_obs, b)
        util = sum(d.values()) + welfare_premium(ten, d)
        if util < base_util - 1e-9:
            continue
        v = bundle_npv(dp, p, j, r, q, b, tmul, vmul)
        if v > best_v:
            best, best_v = b, v
    return best


def _bundle_from_offer(off):
    return Bundle(
        ri=RENT_LABELS.index(off.get("rent", RENT_LABELS[0])),
        ci=CREDIT_LABELS.index(off.get("one_time_credit", CREDIT_LABELS[0])),
        fee=(off.get("fees") == FEE_LABELS[1]),
        term=(off.get("term") == TERM_LABELS[1]))


def _offer_dict(b: Bundle):
    return {"rent": RENT_LABELS[b.ri], "term": TERM_LABELS[1 if b.term else 0],
            "one_time_credit": CREDIT_LABELS[b.ci],
            "fees": FEE_LABELS[1 if b.fee else 0]}


# ------------------------------------------------------------------ the matrix
def negotiate_matrix(dp, p: Params, ten: Tenant, crab, q, r, j, M, g_obs, c_tot,
                     seed, tenant_engine: bool, landlord_engine: bool,
                     tmul=None, vmul=1.0):
    """One renewal under one cell of the 2x2. Returns (Bundle|None, rounds,
    asked, engine_utility)."""
    from gametheory.negotiation.bundle import negotiate_bundle

    t_issues, mu = build_issues(p, ten, q, M, g_obs)
    t_batna = tenant_batna_normalised(p, ten, q, r, j, M, c_tot)
    t_prio = {k: float(w) for k, w in zip(ISSUES, ten.w)}
    l_issues, l_prio, l_batna = landlord_issues(dp, p, j, r, q, tmul, vmul)

    on_table = Bundle()                      # the station's standing offer
    if landlord_engine:
        on_table = landlord_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul)
        if on_table.ri >= N_TENANT_RENT:
            # it opened above its plain optimum: that becomes the new baseline
            q = q * RENT_FACTORS[on_table.ri]
            on_table = Bundle(0, on_table.ci, on_table.fee, on_table.term)
            t_issues, mu = build_issues(p, ten, q, M, g_obs)
            t_batna = tenant_batna_normalised(p, ten, q, r, j, M, c_tot)
            l_issues, l_prio, l_batna = landlord_issues(dp, p, j, r, q, tmul,
                                                        vmul)
    tenant_offers = []                       # what the tenant has asked for
    station_offers = [_offer_dict(on_table)]
    anchor = None
    eng_util = None
    rounds = min(N_ROUNDS, HEUR_ROUNDS if not tenant_engine else N_ROUNDS)

    for rnd in range(rounds):
        # ---- tenant proposes
        if tenant_engine:
            res = negotiate_bundle(
                issues=t_issues, their_offers=station_offers,
                my_priorities=t_prio, my_batna=t_batna,
                their_batna_estimate=THEIR_BATNA_ESTIMATE,
                seed=int(seed) + rnd, rounds_left=rounds - rnd)
            eng_util = res.get("my_utility")
            if res["action"] == "accept":
                break
            if res["action"] in ("walk", "use_negotiate_turn"):
                break
            ask = _bundle_from_offer(res.get("recommended_offer") or {})
        else:
            ask = heuristic_tenant_ask(p, ten, q, r, M, g_obs, rnd)
            if anchor is None:
                anchor = ask
        tenant_offers.append(_offer_dict(ask))

        # ---- landlord replies
        base_v = bundle_npv(dp, p, j, r, q, on_table, tmul, vmul)
        if bundle_npv(dp, p, j, r, q, ask, tmul, vmul) >= base_v:
            return ask, rnd + 1, True, eng_util, q       # straight acceptance
        if landlord_engine:
            res = negotiate_bundle(
                issues=l_issues, their_offers=tenant_offers,
                my_priorities=l_prio, my_batna=l_batna,
                their_batna_estimate=0.45, seed=int(seed) + 977 + rnd,
                rounds_left=rounds - rnd)
            if res["action"] in ("walk", "use_negotiate_turn"):
                reply = None
            else:
                cand = _bundle_from_offer(res.get("recommended_offer") or {})
                reply = cand if bundle_npv(dp, p, j, r, q, cand, tmul,
                                           vmul) >= base_v else None
        else:
            reply = heuristic_landlord_reply(dp, p, j, r, q, ten, M, g_obs, ask,
                                             tmul, vmul)
            if reply is not None and bundle_npv(dp, p, j, r, q, reply, tmul,
                                                vmul) < base_v:
                reply = None
        if reply is None:
            break
        on_table = reply
        station_offers.append(_offer_dict(on_table))

        # ---- does the tenant take it?
        if tenant_engine:
            continue                     # the engine decides on its next turn
        if heuristic_tenant_accepts(p, ten, q, M, g_obs, on_table,
                                    anchor or ask):
            return on_table, rnd + 1, True, eng_util, q

    return (None if on_table.is_null() else on_table), rounds, True, eng_util, q

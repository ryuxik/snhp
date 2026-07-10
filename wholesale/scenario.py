"""Event-consistent Nash bundles for the wholesale tier — vend/scenario.py's
pattern one tier up, multi-issue like gametheory/negotiation/bundle.py.

Per (wholesaler, venue, week) the deal space is the full B2B bundle:

  case price       discount rungs off the applicable rate-card break price
                   (discount-only: never above the published card)
  delivery window  Mon-Fri x AM/PM; AM scarce (slot shadow + weekly cap)
  case quantity    MOQ to storage cap (newsvendor against the disclosed
                   weekly demand forecast)
  payment terms    COD -2% | net-15 | net-30 (net-30 negotiated-only)
  spoilage share   none | 50/50 on perishables

Wholesaler utility = PV(receipts) - goods - INCREMENTAL route cost (a drop
fee if the truck already stops in that window, else a stop + the slot's
shadow value) - its share of spoilage credits. Venue utility = attributable
retail value + carryover/spoilage salvage + spoilage credit - PV(payment) -
receiving labor for the window.

The disagreement point is the EVENT that happens with no deal — one
consistent event for both sides (the vend/scenario.py fix):

  * rate-card branch: the venue would just order off the posted card
    (published breaks, published terms, FCFS window) -> the venue keeps
    that surplus and the wholesaler keeps that margin — the sale it
    already had. Discounts can only come from NEWLY CREATED surplus.
  * Jetro branch: the venue's cash-and-carry alternative wins (rate card
    x 0.93, own haul + owner time, COD, no breaks) -> the wholesaler keeps
    NOTHING, which is exactly why marginal small accounts are worth
    recruiting with route-dense windows: every dollar above cost is found
    money against a zero counterfactual.

A deal must clear both disagreements, and the wholesaler's believed gain
must clear the buffer max($5, 3% of the order's list value) — vend's
don't-negotiate-for-pennies rule, scaled to B2B order sizes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from wholesale import calibration as cal
from wholesale.world import Schedule, WeekDemand, fcfs_window, shadow

N_WINDOWS = 10


@dataclass
class RelCtx:
    """Static context of one (wholesaler, venue) relationship at a grid
    cell: prices, costs, storage, financing, and the receiving-labor cost
    of each window under the cell's flexibility share."""
    wholesaler: str
    venue: str
    base: float
    cogs: float
    perishable: bool
    breaks: tuple
    moq: int
    cap: int
    mu: float
    R: float                  # attributable retail value per case sold
    salv: float               # per-case value of an unsold DURABLE case
    pv_v: dict                # terms -> venue PV factor on the invoice
    pv_w: dict                # terms -> wholesaler PV factor
    share_opts: tuple         # spoilage-sharing options
    recv: np.ndarray          # (10,) receiving labor by window
    pref: tuple               # venue's window preference order
    qty_grid: np.ndarray      # (nq,) negotiable case quantities, MOQ..cap
    jetro_grid: np.ndarray    # (nj,) cash-and-carry quantities, 1..cap

    def break_frac(self, q) -> np.ndarray:
        qa = np.asarray(q)
        conds = [qa >= thr for thr, _f in self.breaks]
        return np.select(conds, [f for _thr, f in self.breaks])

    def break_price(self, q) -> np.ndarray:
        """The published rate-card price for an order of q cases."""
        return np.round(self.base * self.break_frac(q), 2)


def _pv_factors(rate_monthly: float) -> dict:
    """PV factor on the nominal invoice, by payment terms. COD carries the
    published 2% discount; net terms discount the payment by the payer's
    (or payee's) monthly financing rate x the term."""
    return {"cod": 1.0 - cal.COD_DISCOUNT,
            "net15": 1.0 - rate_monthly * cal.NET15_MONTHS,
            "net30": 1.0 - rate_monthly * cal.NET30_MONTHS}


def build_ctx(wholesaler: str, venue: str, flex: float) -> RelCtx:
    w = cal.WHOLESALERS[wholesaler]
    v = cal.VENUES[venue]
    key = (wholesaler, venue)
    cap = cal.STORAGE_CAP[key]
    moq = w["moq"]
    n_free = max(1, int(round(flex * N_WINDOWS)))
    recv = np.full(N_WINDOWS, v["recv_penalty"], dtype=float)
    recv[list(v["pref"][:n_free])] = 0.0
    qty_grid = np.unique(np.linspace(moq, cap, cal.N_QTY_RUNGS)
                         .round().astype(int))
    jetro_grid = np.unique(np.linspace(1, cap, cal.N_QTY_RUNGS)
                           .round().astype(int))
    return RelCtx(
        wholesaler=wholesaler, venue=venue, base=w["base"],
        cogs=round(w["base"] * w["cogs_frac"], 2),
        perishable=w["perishable"], breaks=w["breaks"], moq=moq, cap=cap,
        mu=cal.DEMAND_MU[key], R=round(cal.RETAIL_MULT[key] * w["base"], 2),
        salv=0.0 if w["perishable"] else round(
            cal.DURABLE_SALVAGE_FRAC * w["base"], 2),
        pv_v=_pv_factors(v["fin_rate"]),
        pv_w=_pv_factors(cal.WHOLESALER_FIN_RATE),
        share_opts=cal.SPOIL_SHARE_OPTIONS if w["perishable"] else (0.0,),
        recv=recv, pref=v["pref"], qty_grid=qty_grid, jetro_grid=jetro_grid)


# ── the no-deal event ────────────────────────────────────────────────────

@dataclass
class Disagreement:
    event: str          # "ratecard" | "jetro" | "none"
    d_v: float          # venue's no-deal surplus (expected)
    d_w: float          # wholesaler's no-deal margin (expected)
    window: int         # the FCFS window a rate-card order would land in
    rc_q: int           # the venue's rate-card-optimal quantity...
    rc_terms: str       # ...and published-terms pick (issue-freeze defaults)
    jet_q: int


def disagreement(ctx: RelCtx, env: WeekDemand, schedule: Schedule, *,
                 coordinate: bool = True) -> Disagreement:
    """What actually happens if this negotiation yields nothing. The
    venue's best rate-card order (published breaks x published terms, FCFS
    window) vs its Jetro run; the wholesaler's counterfactual follows the
    same event. `coordinate=False` (the H-W3 ablation) prices the no-deal
    route cost without cross-venue visibility, exactly as the nego side
    does."""
    iw = fcfs_window(schedule, ctx.pref)
    q = ctx.qty_grid
    e_sold = env.e_sold[q]
    e_over = q - e_sold
    bp = ctx.break_price(q)
    gross = ctx.R * e_sold + ctx.salv * e_over
    rc_u, rc_q, rc_terms = -math.inf, int(q[0]), cal.PUBLISHED_TERMS[0]
    for t in cal.PUBLISHED_TERMS:
        u = gross - bp * q * ctx.pv_v[t] - ctx.recv[iw]
        i = int(np.argmax(u))
        if u[i] > rc_u:
            rc_u, rc_q, rc_terms = float(u[i]), int(q[i]), t
    inc = (schedule.incremental_cost(iw) if coordinate
           else cal.STOP_COST + shadow(iw))
    rc_margin = (float(ctx.break_price(rc_q)) * rc_q * ctx.pv_w[rc_terms]
                 - ctx.cogs * rc_q - inc)

    qj = ctx.jetro_grid
    uj = (ctx.R * env.e_sold[qj] + ctx.salv * (qj - env.e_sold[qj])
          - cal.JETRO_PRICE_FRAC * ctx.base * qj
          - (cal.JETRO_HAUL + cal.JETRO_TIME))
    ji = int(np.argmax(uj))
    jet_u, jet_q = float(uj[ji]), int(qj[ji])

    if rc_u >= jet_u and rc_u > 0:
        return Disagreement("ratecard", rc_u, rc_margin, iw, rc_q, rc_terms, jet_q)
    if jet_u > 0:
        return Disagreement("jetro", jet_u, 0.0, iw, rc_q, rc_terms, jet_q)
    return Disagreement("none", 0.0, 0.0, iw, rc_q, rc_terms, jet_q)


# ── the Nash bundle ──────────────────────────────────────────────────────

@dataclass
class Deal:
    qty: int
    unit_price: float
    window: int
    terms: str
    share: float
    u_v: float          # expected utilities at negotiation time
    u_w: float
    d_v: float
    d_w: float
    list_value: float   # break_price(qty) * qty — the buffer's base


@dataclass
class BundleGrids:
    """The feasible-bundle utility tensors for one relationship-week — the SHARED
    core of `nash_deal` (max-product split) and the human-negotiation frontier
    (`wholesale.negotiators`, max-joint pie + who-captures-it). Extracted so both
    read the SAME utilities: any human-vs-SNHP number is byte-consistent with the
    engine that reproduces `run.run_week` to the cent (test_wholesale/​test_supply
    stay green). Shapes broadcast to (nq, np, nt, ns, nw)."""
    q: np.ndarray            # (nq,) case quantities on the table
    price: np.ndarray        # (nq, np) unit prices (break price × discount rung)
    terms: tuple             # (nt,) payment terms on the table
    shares: np.ndarray       # (ns,) spoilage-share options
    windows: list            # (nw,) delivery windows on the table
    bp: np.ndarray           # (nq,) rate-card break price by quantity
    u_v: np.ndarray          # (5D) venue utility of each bundle
    u_w: np.ndarray          # (5D) wholesaler utility of each bundle
    g_v: np.ndarray          # (5D) venue gain above disagreement (d_v)
    g_w: np.ndarray          # (5D) wholesaler gain above disagreement (inf→0)
    feas: np.ndarray         # (5D) both gains ≥ 0 and the route is schedulable


def bundle_grids(ctx: RelCtx, env: WeekDemand, schedule: Schedule,
                 d: Disagreement, *, coordinate: bool = True,
                 fix: dict | None = None) -> BundleGrids:
    """Build the feasible-bundle utility tensors against the event-consistent
    disagreement `d`. `coordinate=False` prices every window as a fresh stop;
    `fix` freezes issues (the H-W1 ablations / the POSITIONAL price-only set)."""
    fix = fix or {}
    q = (np.array([int(fix["qty"])]) if "qty" in fix else ctx.qty_grid)
    rungs = np.array([fix["discount"]] if "discount" in fix
                     else cal.PRICE_RUNGS)
    terms = (fix["terms"],) if "terms" in fix else cal.TERMS
    shares = np.array([fix["share"]] if "share" in fix else ctx.share_opts)
    windows = ([int(fix["window"])] if "window" in fix
               else list(range(N_WINDOWS)))

    e_sold = env.e_sold[q]                                     # (nq,)
    e_over = q - e_sold
    bp = ctx.break_price(q)                                    # (nq,)
    price = np.round(bp[:, None] * (1.0 - rungs[None, :]), 2)  # (nq, np)
    pvv = np.array([ctx.pv_v[t] for t in terms])               # (nt,)
    pvw = np.array([ctx.pv_w[t] for t in terms])
    recv = ctx.recv[windows]                                   # (nw,)
    if coordinate:
        wcost = np.array([schedule.incremental_cost(iw) for iw in windows])
    else:
        wcost = np.array([cal.STOP_COST + shadow(iw)
                          if schedule.feasible(iw) else math.inf
                          for iw in windows])

    # broadcast to (nq, np, nt, ns, nw)
    qc = q[:, None, None, None, None].astype(float)
    gross = (ctx.R * e_sold + ctx.salv * e_over)[:, None, None, None, None]
    pq = (price * q[:, None])[:, :, None, None, None]
    credit = (shares[None, None, None, :, None]
              * price[:, :, None, None, None]
              * e_over[:, None, None, None, None])
    u_v = (gross + credit - pq * pvv[None, None, :, None, None]
           - recv[None, None, None, None, :])
    u_w = (pq * pvw[None, None, :, None, None] - ctx.cogs * qc - credit
           - wcost[None, None, None, None, :])

    g_v, g_w = u_v - d.d_v, u_w - d.d_w
    feas = (g_v > -1e-9) & (g_w > -1e-9) & np.isfinite(u_w)
    g_w = np.where(np.isfinite(g_w), g_w, 0.0)   # masked below; avoids inf*0
    return BundleGrids(q=q, price=price, terms=terms, shares=shares,
                       windows=windows, bp=bp, u_v=u_v, u_w=u_w,
                       g_v=g_v, g_w=g_w, feas=feas)


def nash_deal(ctx: RelCtx, env: WeekDemand, schedule: Schedule,
              d: Disagreement, *, coordinate: bool = True,
              fix: dict | None = None) -> Deal | None:
    """Nash bargaining over the full bundle space, against the
    event-consistent disagreement. `coordinate=False` removes the
    wholesaler's cross-venue visibility: every window is priced as a fresh
    stop (physical feasibility is still the dispatcher's — you cannot book
    an unbookable morning). `fix` freezes issues at given values (the
    H-W1 issue-ablation arms), e.g. {"window": 3} or {"discount": 0.0}."""
    G = bundle_grids(ctx, env, schedule, d, coordinate=coordinate, fix=fix)
    q, price, terms, shares, windows, bp = (G.q, G.price, G.terms, G.shares,
                                            G.windows, G.bp)
    u_v, u_w, g_v, g_w, feas = G.u_v, G.u_w, G.g_v, G.g_w, G.feas
    if not feas.any():
        return None
    prod = np.where(feas, g_v * g_w, -math.inf)
    pmax = prod.max()
    # lexicographic tiebreak (vend's): among max-product bundles, take the
    # greatest joint gain, so a boundary deal isn't discarded arbitrarily
    tie = feas & (prod >= pmax - 1e-12)
    joint = np.where(tie, g_v + g_w, -math.inf)
    idx = np.unravel_index(int(np.argmax(joint)), joint.shape)
    if pmax <= 0 and joint[idx] <= 1e-9:
        return None            # nothing improves on the disagreement event
    iq, ip, it, isr, iwi = idx
    list_value = float(bp[iq]) * int(q[iq])
    thr = max(cal.BUFFER_MIN, cal.BUFFER_FRAC * list_value)
    if g_w[idx] < thr:
        return None            # don't-negotiate-for-pennies (buffer)
    return Deal(qty=int(q[iq]), unit_price=float(price[iq, ip]),
                window=int(windows[iwi]), terms=terms[it],
                share=float(shares[isr]), u_v=float(u_v[idx]),
                u_w=float(u_w[idx]), d_v=d.d_v, d_w=d.d_w,
                list_value=round(list_value, 2))

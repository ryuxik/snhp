"""SPECAUDIT S5/S6 — default-gap simulation (banded magnitude).

DRAFT-FOR-COMMENT. This measures the COST OF THE DELEGATED GAP: the deal-
formation space that AP2 / ACP / UCP leave UNSPECIFIED and hand to implementers.
It is NOT a flaw in any spec. The specs (verified structurally in report.md S1)
fix "the merchant computes and returns all commercial terms" and give the agent
NO counteroffer surface. What an implementer's agent then does inside that gap is
what we model here.

FAITHFULNESS + FAIRNESS

  * The utility model is NOT invented for this audit. We import, read-only, the
    exact economic primitives the golden-validated MERIDIAN harness already uses
    (meridian.agents.{buyer_gross_value, supplier_cost, joint_surplus}) and the
    repo's own snhp nash_solver primitives. Same functions the MERIDIAN report is
    scored against; see meridian/README.md.
  * DECLARED UTILITY FAMILY (stated explicitly, drawn i.i.d.): opportunities are
    sampled from the SAME parameter ranges MERIDIAN's MarketConfig uses for its
    A1 / BASE / A2 regimes — reproduced as LOW / MID / HIGH "multi-issue
    intensity" regimes below. Nothing here is a bespoke distribution.
  * Magnitudes are reported ONLY as sensitivity BANDS across that family (regime
    x markup cells, >=8 seeds each), never as a single point estimate.

THE TWO CHANNELS WE MEASURE (both are consequences of the no-counter delegation,
not of any particular spec text):

  S5a  DEAL-FORMATION GAP (maps to S1).  A take-it-or-leave-it, merchant-priced
       checkout with no counter forgoes joint surplus two ways:
         (i)  FOREGONE TRADE: a jointly beneficial deal (value > cost) dies
              because the merchant's posted total exceeds the buyer's private
              value and there is no message to split the difference.
         (ii) MISCONFIGURATION: a deal that DOES close closes at the config the
              buyer prefers against MARKED-UP cost, which need not be the
              joint-surplus-maximising config (the merchant can neither see the
              buyer's urgency nor be asked to trade price for a better date).
       We deliberately hand the spec its BEST case (the merchant enumerates the
       FULL (qty x date) grid as its menu), so the measured gap is a LOWER bound
       on what a coarser real menu would forgo.

  S5b  SETTLEMENT EXPOSURE (maps to S2).  Payment is authorised before delivery
       (ACP: charge at /complete; AP2: delivery is out of scope). A deceptive
       counterparty that under-delivers keeps the already-authorised funds; the
       buyer's only recourse is post-hoc (chargeback / an ACP refund Adjustment).
       We measure the buyer-surplus exposure window.

THE FIX DEMO (S6), slotted at the specs' OWN extension points:

  S6a  Bundled negotiation (snhp nash_solver over price x qty x date) run in the
       deal-formation step AP2 declares out of scope / before the ACP session is
       completed. The negotiated bundle then becomes the cart the merchant signs
       (AP2 Checkout Mandate) or the completed ACP session — terms unchanged.
       Reports the fraction of the S5a gap recovered, as a band.
  S6b  Receipt-gated settlement: release funds only against a delivery
       attestation (AP2 already mints an MPP-signed Payment Receipt; ACP already
       models Fulfillment + refund Adjustments). Reports recovered buyer surplus
       under a deceptive-counterparty fraction, as a band.

Reproduce:  python -m specaudit.gap_sim            (writes results/gap_results.json)
            python -m pytest specaudit/test_specaudit.py -q
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from pathlib import Path

import numpy as np

# --- read-only imports: MERIDIAN economic primitives + snhp nash_solver -------
# Same bootstrap pattern meridian/audit.py uses (which mirrors research/swarm).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SNHP = os.path.join(_ROOT, "snhp")
for _p in (_ROOT, _SNHP):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from meridian.agents import (  # noqa: E402  (read-only; we never mutate meridian)
    buyer_gross_value,
    joint_surplus,
    supplier_cost,
)
from nash_solver import (  # noqa: E402
    filter_pareto_frontier,
    find_nash_bargaining_solution,
    generate_contract_space,
)

SEEDS = list(range(101, 109))  # 8 seeds, matching MERIDIAN's >=8 discipline
N_OPPS = 600                   # opportunities drawn per (regime, markup, seed) cell
RESULTS_DIR = Path(__file__).with_name("results")


# --- DECLARED UTILITY FAMILY -------------------------------------------------
# Regimes reproduce MERIDIAN's A2 (LOW), BASE (MID), A1 (HIGH) demand shapes.
# Only the buyer-side "multi-issue intensity" knobs (need_by tightness, urgency,
# and supplier capacity tightness) vary by regime; supplier cost curves are the
# MERIDIAN population draws in all regimes.
REGIMES = {
    "LOW":  dict(need_by_lo=6, need_by_hi=16, urgency_lo=0.5, urgency_hi=3.0,
                 cap_lo=3, cap_hi=9),   # slack deadlines, low urgency, loose cap
    "MID":  dict(need_by_lo=2, need_by_hi=9,  urgency_lo=1.0, urgency_hi=6.0,
                 cap_lo=3, cap_hi=9),   # MERIDIAN BASE
    "HIGH": dict(need_by_lo=1, need_by_hi=4,  urgency_lo=3.0, urgency_hi=9.0,
                 cap_lo=2, cap_hi=5),   # tight deadlines, urgent, tight cap
}
# Markup band: MERIDIAN suppliers draw min_markup in [0.03,0.08] and opening
# markup in [0.18,0.32]. We sweep the take-it-or-leave-it posted markup across
# {floor, mid, opening} so the foregone-trade channel is reported as a band, not
# pinned to one merchant-margin assumption.
MARKUPS = {"floor": 0.05, "mid": 0.18, "open": 0.32}

# Menu-richness band. ACP exposes `fulfillment_options` / `selected_fulfillment_
# options` and UCP exposes shipping options, so a merchant CAN offer a delivery-
# speed menu (credit due — MPX-style single take-it-or-leave-it date could not).
# But the menu is still (a) merchant-enumerated and (b) merchant-priced with no
# counter. We bracket the two honest extremes:
#   "standard" - only the merchant's cheapest date (natural lead) is offered; a
#                faster date is unobtainable at any price (the MPX-like case).
#   "express"  - standard + one expedited option (a realistic small menu).
#   "full"     - the merchant enumerates the entire (qty x date) grid (the most
#                generous case for the spec; makes the measured gap a LOWER bound).
# Quantity is agent-composable in all cases (ACP line_items.quantity), so the
# menu only ever constrains the DATE dimension.
MENUS = ("standard", "express", "full")

# S5b deception band (maps to MERIDIAN A2 knobs).
DECEPTIVE_FRACTIONS = [0.05, 0.10, 0.25]
BAD_PROB = 0.5        # per-order shortfall probability on a deceptive merchant
SHORT_FRAC = 0.5      # fraction withheld on a bad order

VALUE_LO, VALUE_HI = 70.0, 130.0    # MERIDIAN value range
QTY_LO, QTY_HI = 8, 40              # MERIDIAN per-line qty
C0_LO, C0_HI = 30.0, 55.0
C1_LO, C1_HI = 0.02, 0.08
EXPEDITE_LO, EXPEDITE_HI = 1.5, 4.0
INV_LO, INV_HI = 200, 600


def _levels(lo: int, hi: int, n: int) -> list[int]:
    """Distinct integer grid levels in [lo, hi] (same helper MERIDIAN uses)."""
    return sorted(set(int(round(x)) for x in np.linspace(lo, hi, n)))


class Opportunity:
    """One drawn buyer<->merchant deal from the declared family. Plain container;
    all economics come from meridian.agents."""

    __slots__ = ("unit_value", "need_qty", "need_by", "urgency", "c0", "c1",
                 "cap", "expedite", "inventory")

    def __init__(self, rng: np.random.Generator, reg: dict):
        self.unit_value = float(rng.uniform(VALUE_LO, VALUE_HI))
        self.need_qty = int(rng.integers(QTY_LO, QTY_HI))
        self.need_by = int(rng.integers(reg["need_by_lo"], reg["need_by_hi"] + 1))
        self.urgency = float(rng.uniform(reg["urgency_lo"], reg["urgency_hi"]))
        self.c0 = float(rng.uniform(C0_LO, C0_HI))
        self.c1 = float(rng.uniform(C1_LO, C1_HI))
        self.cap = float(rng.integers(reg["cap_lo"], reg["cap_hi"] + 1))
        self.expedite = float(rng.uniform(EXPEDITE_LO, EXPEDITE_HI))
        self.inventory = float(rng.integers(INV_LO, INV_HI))

    def grid(self) -> tuple[list[int], list[int]]:
        qmax = max(1, min(self.need_qty, int(self.inventory)))
        natural = max(1, math.ceil(qmax / self.cap))
        return _levels(1, qmax, 8), _levels(1, natural, 8)


# --- the oracle (full pie) + the two worlds ----------------------------------

def oracle_joint(opp: Opportunity) -> tuple[float, int, int]:
    """Joint-surplus-maximising (qty, ship_date) — the whole pie a bundle could
    reach against this same merchant (price cancels). Uses meridian.joint_surplus.
    Returns (J*, q*, d*); J*<=0 => no beneficial trade exists at all."""
    qs, ds = opp.grid()
    best = (0.0, 0, 0)
    for q in qs:
        for d in ds:
            J = joint_surplus(q, d, opp.need_qty, opp.need_by, opp.unit_value,
                              opp.urgency, opp.c0, opp.c1, opp.cap, opp.expedite)
            if J > best[0]:
                best = (J, q, d)
    return best


def _date_menu(ds: list[int], menu: str) -> list[int]:
    """The merchant-enumerated delivery-speed menu (see MENUS). ds is ascending;
    ds[-1] is the natural (slowest, cheapest) date, ds[0] the fastest."""
    if menu == "standard":
        return [ds[-1]]
    if menu == "express":
        return sorted(set([ds[0], ds[-1]]))
    return ds


def checkout_outcome(opp: Opportunity, markup: float,
                     menu: str = "full") -> tuple[float, int, int, bool]:
    """The SPEC world: take-it-or-leave-it, merchant-priced, NO counter.

    The agent freely composes quantity (ACP line_items.quantity) but can only
    pick a delivery date from the merchant's enumerated `fulfillment_options`
    menu (see MENUS), each priced at cost*(1+markup). With no counter surface the
    agent picks the (qty, menu-date) maximising its OWN surplus = value - posted,
    and accepts iff that surplus >= 0 (BATNA = no trade). Returns (realized_joint,
    q, d, accepted); realized_joint = value-cost at the accepted cell (price
    cancels), 0 if the agent walked."""
    qs, ds = opp.grid()
    dates = _date_menu(ds, menu)
    best_surplus = 0.0            # BATNA: walk away rather than take a loss
    accepted = False
    acc = (0.0, 0, 0)
    for q in qs:
        for d in dates:
            cost = supplier_cost(q, d, opp.c0, opp.c1, opp.cap, opp.expedite)
            posted = cost * (1.0 + markup)
            lateness = max(0, d - opp.need_by)
            value = buyer_gross_value(q, opp.need_qty, opp.unit_value,
                                      opp.urgency, lateness)
            surplus = value - posted
            if surplus > best_surplus:
                best_surplus = surplus
                accepted = True
                acc = (value - cost, q, d)   # JOINT (price cancels) at this cell
    if not accepted:
        return (0.0, 0, 0, False)
    return (acc[0], acc[1], acc[2], True)


def nash_bundle(opp: Opportunity) -> tuple[float, int, int, float]:
    """The FIX world (S6a): negotiate the SAME deal over (price, qty, date) with
    the repo's snhp nash_solver instead of a fixed cart. Returns (joint, q, d,
    price). Mirrors meridian/audit.py:nash_bundle so the fix uses the same engine
    the MERIDIAN A5-i fix uses."""
    qs, ds = opp.grid()
    qmax = qs[-1]
    vmax = buyer_gross_value(qmax, opp.need_qty, opp.unit_value, opp.urgency, 0)
    floor = supplier_cost(qmax, ds[0], opp.c0, opp.c1, opp.cap, opp.expedite)
    p_lo, p_hi = floor * 0.8, max(vmax, floor * 1.5)

    q_opts = list(np.linspace(0.0, 1.0, len(qs)))
    d_opts = list(np.linspace(0.0, 1.0, len(ds)))
    p_opts = list(np.linspace(0.0, 1.0, 10))
    space = generate_contract_space([q_opts, d_opts, p_opts])

    qi = (space[:, 0] * (len(qs) - 1)).round().astype(int)
    di = (space[:, 1] * (len(ds) - 1)).round().astype(int)
    qv = np.array([qs[i] for i in qi], dtype=float)
    dv = np.array([ds[i] for i in di], dtype=float)
    pv = p_lo + space[:, 2] * (p_hi - p_lo)

    lateness = np.maximum(0.0, dv - opp.need_by)
    unit = np.maximum(0.0, opp.unit_value - opp.urgency * lateness)
    val = np.minimum(qv, opp.need_qty) * unit
    cost = (opp.c0 * qv + opp.c1 * qv * qv
            + opp.expedite * qv * np.maximum(0.0, qv / opp.cap - dv))
    ua = val - pv       # buyer surplus
    ub = pv - cost      # merchant surplus

    pareto = filter_pareto_frontier(space, ua, ub)
    idx = find_nash_bargaining_solution(pareto, ua, ub, 0.0, 0.0)
    if idx is None:
        return (0.0, 0, 0, 0.0)
    return (float(ua[idx] + ub[idx]), int(qv[idx]), int(dv[idx]), float(pv[idx]))


# --- S5a: deal-formation gap over the declared family ------------------------

def run_cell_s5a(regime: str, markup_key: str, seed: int,
                 menu: str = "full") -> dict:
    """One (regime, markup, menu, seed) cell. Draws N_OPPS from the declared
    family and compares the spec checkout to the oracle pie and the snhp nash
    bundle. Kept as a standalone entry point for the tests; run_full() uses the
    faster shared-draw path below."""
    rng = np.random.default_rng(seed)
    reg = REGIMES[regime]
    markup = MARKUPS[markup_key]
    s_oracle = s_checkout = s_nash = 0.0
    beneficial = foregone = misconfig = 0
    for _ in range(N_OPPS):
        opp = Opportunity(rng, reg)
        Jo, _, _ = oracle_joint(opp)
        Jc, qc, dc, accepted = checkout_outcome(opp, markup, menu)
        Jn, _, _, _ = nash_bundle(opp)
        s_oracle += Jo
        s_checkout += Jc
        s_nash += max(0.0, Jn)
        if Jo > 1e-6:
            beneficial += 1
            if not accepted:
                foregone += 1
            elif Jc < Jo - 1e-6:
                misconfig += 1
    return _s5a_metrics(N_OPPS, beneficial, foregone, misconfig,
                        s_oracle, s_checkout, s_nash)


def _s5a_metrics(nopp, beneficial, foregone, misconfig,
                 s_oracle, s_checkout, s_nash) -> dict:
    gap = s_oracle - s_checkout
    return {
        "opps": nopp,
        "beneficial": beneficial,
        "foregone_trades": foregone,
        "misconfigured_trades": misconfig,
        "oracle_surplus": s_oracle,
        "checkout_surplus": s_checkout,
        "nash_surplus": s_nash,
        "gap_dollars": gap,
        "gap_pct": 100.0 * gap / max(1e-9, s_oracle),
        "foregone_pct_of_beneficial": 100.0 * foregone / max(1, beneficial),
        # S6a recovery: how much of the gap the bundled layer converts to surplus
        "nash_recovered_pct_of_gap": (
            100.0 * (s_nash - s_checkout) / gap if gap > 1e-9 else 0.0),
        "nash_recovered_pct_of_oracle": 100.0 * s_nash / max(1e-9, s_oracle),
    }


def run_draws_s5a(regime: str, seed: int) -> dict:
    """Shared-draw path: one seeded population, every (markup, menu) cell scored
    against the SAME opportunities and the SAME (expensive) oracle+nash computed
    once per opportunity. Returns {(markup_key, menu): metrics}."""
    rng = np.random.default_rng(seed)
    reg = REGIMES[regime]
    acc = {(mk, menu): dict(s_oracle=0.0, s_checkout=0.0, s_nash=0.0,
                            beneficial=0, foregone=0, misconfig=0)
           for mk in MARKUPS for menu in MENUS}
    for _ in range(N_OPPS):
        opp = Opportunity(rng, reg)
        Jo, _, _ = oracle_joint(opp)
        Jn, _, _, _ = nash_bundle(opp)
        Jn = max(0.0, Jn)
        for mk, markup in MARKUPS.items():
            for menu in MENUS:
                Jc, _, _, accepted = checkout_outcome(opp, markup, menu)
                a = acc[(mk, menu)]
                a["s_oracle"] += Jo
                a["s_checkout"] += Jc
                a["s_nash"] += Jn
                if Jo > 1e-6:
                    a["beneficial"] += 1
                    if not accepted:
                        a["foregone"] += 1
                    elif Jc < Jo - 1e-6:
                        a["misconfig"] += 1
    return {k: _s5a_metrics(N_OPPS, a["beneficial"], a["foregone"], a["misconfig"],
                            a["s_oracle"], a["s_checkout"], a["s_nash"])
            for k, a in acc.items()}


# --- S5b: settlement exposure + S6b receipt gate -----------------------------

def run_cell_s5b(regime: str, frac: float, seed: int) -> dict:
    """Payment authorised before delivery. A `frac` share of merchants are
    deceptive (under-deliver SHORT_FRAC with prob BAD_PROB). Measure buyer
    surplus under (i) spec ordering pay-on-auth vs (ii) receipt-gated pay-on-
    delivery (S6b). Markup fixed at the MID posted markup so this isolates the
    settlement channel from the S5a margin sweep."""
    rng = np.random.default_rng(seed + 9000)
    reg = REGIMES[regime]
    markup = MARKUPS["mid"]
    paid_auth = paid_gate = value_auth = value_gate = 0.0
    n_trades = 0
    for _ in range(N_OPPS):
        opp = Opportunity(rng, reg)
        Jc, q, d, accepted = checkout_outcome(opp, markup)
        if not accepted:
            continue
        n_trades += 1
        cost = supplier_cost(q, d, opp.c0, opp.c1, opp.cap, opp.expedite)
        posted = cost * (1.0 + markup)
        deceptive = rng.random() < frac
        bad = deceptive and (rng.random() < BAD_PROB)
        delivered_q = q * (1.0 - SHORT_FRAC) if bad else q
        deliver_late = d + (2 if bad else 0)
        lateness = max(0, deliver_late - opp.need_by)
        realized_value = buyer_gross_value(delivered_q, opp.need_qty,
                                           opp.unit_value, opp.urgency, lateness)
        # (i) pay-on-auth (spec ordering): buyer pays full posted regardless
        paid_auth += posted
        value_auth += realized_value
        # (ii) receipt-gated: pay pro-rata for what actually arrived
        frac_delivered = delivered_q / q if q else 0.0
        paid_gate += posted * frac_delivered
        value_gate += realized_value
    surplus_auth = value_auth - paid_auth
    surplus_gate = value_gate - paid_gate
    return {
        "n_trades": n_trades,
        "buyer_surplus_pay_on_auth": surplus_auth,
        "buyer_surplus_receipt_gated": surplus_gate,
        "exposure_dollars": surplus_gate - surplus_auth,
        "exposure_pct_of_gated": (
            100.0 * (surplus_gate - surplus_auth) / surplus_gate
            if surplus_gate > 1e-9 else 0.0),
    }


# --- aggregation into BANDS --------------------------------------------------

def _band(cells: list[dict], key: str) -> dict:
    """A band = [min cell-mean, max cell-mean] across the family, with the
    pooled mean and the sd of cell means. Never a bare point estimate."""
    vals = [c[key] for c in cells]
    return {
        "band_lo": min(vals),
        "band_hi": max(vals),
        "pooled_mean": statistics.fmean(vals),
        "sd_across_cells": statistics.stdev(vals) if len(vals) > 1 else 0.0,
        "n_cells": len(vals),
    }


def _mean_sd(xs: list) -> dict:
    return {"mean": statistics.fmean(xs),
            "sd": statistics.stdev(xs) if len(xs) > 1 else 0.0, "n": len(xs)}


def run_full(seeds: list[int] = SEEDS) -> dict:
    # S5a / S6a: regime x markup x menu cells, each averaged over seeds. All
    # cells for a (regime, seed) share one population draw (paired).
    s5a_cells = []
    s5a_by_cell = {}
    for regime in REGIMES:
        per_seed = [run_draws_s5a(regime, s) for s in seeds]  # list of dicts keyed (mk,menu)
        for mk in MARKUPS:
            for menu in MENUS:
                rows = [ps[(mk, menu)] for ps in per_seed]
                cell = {k: statistics.fmean([r[k] for r in rows]) for k in rows[0]}
                cell["regime"] = regime
                cell["markup"] = mk
                cell["menu"] = menu
                s5a_cells.append(cell)
                s5a_by_cell[f"{regime}/{mk}/{menu}"] = {
                    "mean": cell,
                    "per_seed_gap_pct": [r["gap_pct"] for r in rows],
                    "gap_pct": _mean_sd([r["gap_pct"] for r in rows]),
                }
    s5a_bands = {
        "gap_pct": _band(s5a_cells, "gap_pct"),
        "gap_dollars_per_opp": _band(
            [{**c, "gpo": c["gap_dollars"] / N_OPPS} for c in s5a_cells], "gpo"),
        "foregone_pct_of_beneficial": _band(s5a_cells, "foregone_pct_of_beneficial"),
        # S6a credit: the bundled layer recovers ~this fraction of the ORACLE pie
        # (stable). We report recovery-of-oracle, not recovery-of-gap: when a cell's
        # gap is ~0 the recovery-of-gap ratio is numerically meaningless.
        "nash_recovered_pct_of_oracle": _band(s5a_cells, "nash_recovered_pct_of_oracle"),
        # menu-conditioned sub-bands so the report can separate the generous
        # (full-menu) lower bound from the MPX-like (standard-only) upper bound.
        "gap_pct_full_menu": _band(
            [c for c in s5a_cells if c["menu"] == "full"], "gap_pct"),
        "gap_pct_standard_menu": _band(
            [c for c in s5a_cells if c["menu"] == "standard"], "gap_pct"),
    }

    # S5b / S6b: regime x deceptive-fraction cells
    s5b_cells = []
    s5b_by_cell = {}
    for regime in REGIMES:
        for f in DECEPTIVE_FRACTIONS:
            rows = [run_cell_s5b(regime, f, s) for s in seeds]
            cell = {k: statistics.fmean([r[k] for r in rows]) for k in rows[0]}
            cell["regime"] = regime
            cell["deceptive_fraction"] = f
            s5b_cells.append(cell)
            s5b_by_cell[f"{regime}/f={f}"] = cell
    s5b_bands = {
        "exposure_pct_of_gated": _band(s5b_cells, "exposure_pct_of_gated"),
        "exposure_dollars_per_trade": _band(
            [{**c, "edt": c["exposure_dollars"] / max(1, c["n_trades"])}
             for c in s5b_cells], "edt"),
    }

    return {
        "meta": {
            "seeds": seeds, "n_opps_per_cell": N_OPPS,
            "regimes": REGIMES, "markups": MARKUPS, "menus": list(MENUS),
            "deceptive_fractions": DECEPTIVE_FRACTIONS,
            "bad_prob": BAD_PROB, "short_frac": SHORT_FRAC,
            "utility_family": ("meridian.agents primitives; A2/BASE/A1 parameter "
                               "ranges reproduced as LOW/MID/HIGH regimes"),
        },
        "S5a_deal_formation_gap": {"cells": s5a_cells, "by_cell": s5a_by_cell,
                                   "bands": s5a_bands},
        "S5b_settlement_exposure": {"cells": s5b_cells, "by_cell": s5b_by_cell,
                                    "bands": s5b_bands},
    }


def _write(results: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "gap_results.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=float)
    return path


def main() -> None:
    print(f"[specaudit] S5/S6 gap sim over {len(SEEDS)} seeds {SEEDS}")
    results = run_full(SEEDS)
    bands = results["S5a_deal_formation_gap"]["bands"]
    b = bands["gap_pct"]
    print(f"[specaudit] S5a deal-formation gap band: "
          f"{b['band_lo']:.1f}%..{b['band_hi']:.1f}% of oracle joint surplus")
    bf = bands["gap_pct_full_menu"]
    bs = bands["gap_pct_standard_menu"]
    print(f"[specaudit]   full-menu (generous, lower bound): "
          f"{bf['band_lo']:.1f}%..{bf['band_hi']:.1f}%")
    print(f"[specaudit]   standard-only menu (MPX-like):     "
          f"{bs['band_lo']:.1f}%..{bs['band_hi']:.1f}%")
    eb = results["S5b_settlement_exposure"]["bands"]["exposure_pct_of_gated"]
    print(f"[specaudit] S5b settlement exposure band: "
          f"{eb['band_lo']:.1f}%..{eb['band_hi']:.1f}% of gated buyer surplus")
    path = _write(results)
    print(f"[specaudit] results -> {path}")


if __name__ == "__main__":
    main()

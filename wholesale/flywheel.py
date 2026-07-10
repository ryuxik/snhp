"""The 3-tier flywheel (S3) and the unification finding + procurement monopsony
audit (S4) — task #64.

The paper result: COMMIT (variance reduction) and COORDINATE (clusters /
buying-clubs) are the SAME lever at BOTH interfaces of the 3-tier chain
(supplier ⇄ merchant ⇄ consumer). SNHP is one mechanism operating twice. We
prove it MECHANICALLY: every measurement below calls the IDENTICAL
`buyer.strategies.coordinate` — the buyer-side function, unchanged — with the
interface's own (values, salvage floor, spoil probability). No supplier-side
reimplementation exists; `coordinate.__module__ == "buyer.strategies"` is
asserted in the tests.

Interfaces:
  A  merchant ⇄ consumer   member_values = consumer WTPs   salvage = merchant c_eff
  B  supplier ⇄ merchant   member_values = venue case value R salvage = supplier cogs

The flywheel (S3): an agent-mediated consumer demand is CERTAIN (the demand agent
controls it). That certainty — a `Wallet.trusted_frac`, tf ∈ [0,1] — is the
share of the would-spoil variance a counterparty will BANK. The same tf is spent
at BOTH interfaces (the consumer's commitment to the merchant AND the merchant's
forward commitment to the supplier), so the banked growth compounds:
  gA(tf) = coordinate(interface A, p_spoil = tf·p_spoilA)  → merchant sheds variance
  gB(tf) = coordinate(interface B, p_spoil = tf·p_spoilB)  → supplier sheds variance
  chain(tf) = gA(tf) + gB(tf)                              → lower COGS → retail
Per-interface the split is Nash 50/50 (coordinate's construction); across the
chain the two interface growths ADD (different transactions) — the flywheel
decomposition conserves (asserted).
"""
from __future__ import annotations

from dataclasses import dataclass

from buyer.stats import mean_ci, paired_ci
from buyer.strategies import coordinate            # the ONE lever (buyer-side)
from buyer.wallet import Wallet

from wholesale import calibration as cal
from wholesale.block_supply import ProcurementMarket


# ── the two interfaces' calibrated inputs ───────────────────────────────────

def interface_A_consumers(seed: int, n: int, target: str = "sandwich"):
    """Merchant⇄consumer: the consumer WTP population for a perishable, and the
    merchant's salvage floor for it (vend's calibration — the buyer-side world)."""
    from buyer.world import draw_vend_population
    from vend.world import CATALOG_SPEC
    salvage = {s: salv for s, _mu, _c, salv, *_ in CATALOG_SPEC}[target]
    pop = draw_vend_population(seed, n)
    return [b.wtp[target] for b in pop], salvage


def interface_B_venues(category: str = "produce"):
    """Supplier⇄merchant: the venues' attributable per-case value R for a
    perishable supplier category, and the supplier's participation floor (cogs).
    These are wholesale/'s calibration — the supply-side world, MIRRORING the
    consumer population one tier up."""
    base = cal.WHOLESALERS[category]["base"]
    cogs = round(base * cal.WHOLESALERS[category]["cogs_frac"], 2)
    values = [round(cal.RETAIL_MULT[(category, v)] * base, 2) for v in cal.V_ORDER]
    return values, cogs


# ── S4: the unified audit (identical code at both interfaces) ────────────────

def coordinate_audit(member_values: list[float], salvage: float, *,
                     p_spoil: float, ks=(2, 5, 10), scarcity: float = 0.5,
                     seed: int = 0) -> dict:
    """The pre-registered monopsony audit — RUN AT EITHER INTERFACE via the same
    `coordinate`. A buying club aggregates forward demand for the scarce,
    spoil-risk stock; the binding checks are (A) coordination never below the
    independent baseline, (B) the seller/supplier margin never breaches its
    participation floor even at maximal extraction, (D) over-reach (a demand
    below the floor) is self-defeating (the stock spoils). This is the RealPage
    mirror: the disagreement-point discipline is symmetric — it stops a seller
    harvesting a captured buyer AND a buyer cartel extracting a captive seller.
    """
    import numpy as np
    # tile the member values into clusters of size k across a big population so
    # the CIs are real (mirror of buyer.run.run_coordinate)
    pop = (member_values * (max(ks) * 40 // max(1, len(member_values)) + 1))
    sweep = {}
    checks_A, checks_B, checks_D = [], [], []
    for k in ks:
        s_risk = max(1, int(round(k * scarcity)))
        fair_g, indep_g, mono_g, over_g = [], [], [], []
        fair_m, mono_m, over_fail, over_spoil, clusters = [], [], 0, 0, 0
        for c in range(0, (len(pop) // k) * k, k):
            grp = pop[c:c + k]
            sd = (seed * 131 + c) & 0x7FFFFFFF
            indep = coordinate(grp, salvage=salvage, s_risk=s_risk,
                               p_spoil=p_spoil, extraction=0.5,
                               allocation="random", seed=sd)
            fair = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=0.5, allocation="efficient")
            mono = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.0, allocation="efficient")
            over = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.2, allocation="efficient")
            fair_g.append(fair.total_growth / k); indep_g.append(indep.total_growth / k)
            mono_g.append(mono.total_growth / k); over_g.append(over.total_growth / k)
            fair_m.append(fair.merchant_margin); mono_m.append(mono.merchant_margin)
            over_fail += int(not over.participation_ok)
            over_spoil += over.spoiled_by_overreach
            clusters += 1
        d_ci = paired_ci([f - i for f, i in zip(fair_g, indep_g)])
        sweep[k] = {
            "s_risk": s_risk, "clusters": clusters,
            "coord_growth_pc": mean_ci(fair_g), "indep_growth_pc": mean_ci(indep_g),
            "d_coord_minus_indep": d_ci,
            "fair_margin_min": round(min(fair_m), 6),
            "monopsony_margin_min": round(min(mono_m), 6),
            "overreach_fail_frac": round(over_fail / max(1, clusters), 4),
            "overreach_growth_pc": mean_ci(over_g),
            "overreach_units_spoiled": over_spoil,
        }
        checks_A.append(d_ci["mean"] >= -1e-9)
        checks_B.append(min(fair_m) >= -1e-9 and min(mono_m) >= -1e-9)
        checks_D.append(mean_ci(over_g)["mean"] <= mean_ci(mono_g)["mean"] + 1e-9)
    checks = {"A_coord_not_below_indep": all(checks_A),
              "B_participation_floor_holds": all(checks_B),
              "D_overreach_self_defeating": all(checks_D)}
    verdict = ("PASS — the buying club cannot push total surplus below the "
               "independent baseline nor extract below the seller's participation "
               "floor" if all(checks.values()) else "FAIL — see checks")
    return {"ks": list(ks), "sweep": sweep, "checks": checks, "verdict": verdict}


# ── S3: the 3-tier flywheel decomposition (conserving) ──────────────────────

@dataclass(frozen=True)
class TierGrowth:
    tf: float
    gA_consumer_merchant: float     # interface A total growth / member
    gB_merchant_supplier: float     # interface B total growth / member
    chain_total: float              # gA + gB (the compounded flywheel)
    A_split_ok: bool                # gA == buyerA + marginA (conserves)
    B_split_ok: bool


def flywheel_decomposition(seed: int = 20260710, n_consumers: int = 2000,
                           p_spoilA: float = 0.40, p_spoilB: float = 0.40,
                           tfs=(0.0, 0.25, 0.5, 0.75, 1.0)) -> dict:
    """The demand-agent certainty tf ∈ [0,1] is the banked share of the
    would-spoil variance; it is spent at BOTH interfaces, so the growth
    compounds. At each tf we call the SAME `coordinate` at interface A (consumer
    values) and interface B (venue case values) and sum — a per-tier
    decomposition that conserves (each interface's 50/50 split sums to its total;
    the chain total is exactly gA + gB)."""
    vA, salvA = interface_A_consumers(seed, n_consumers)
    vB, salvB = interface_B_venues()
    tiers = []
    for tf in tfs:
        # tf scales the banked spoil-avoidance (mirror of Wallet.trusted_frac in
        # buyer.strategies.commit_strategy: d_joint = tf·p_spoil·(V−salv))
        A = coordinate(vA, salvage=salvA, s_risk=max(1, len(vA) // 2),
                       p_spoil=tf * p_spoilA, extraction=0.5, allocation="efficient")
        B = coordinate(vB, salvage=salvB, s_risk=max(1, len(vB) // 2),
                       p_spoil=tf * p_spoilB, extraction=0.5, allocation="efficient")
        gA = A.total_growth / max(1, len(vA))
        gB = B.total_growth / max(1, len(vB))
        # coordinate() rounds its three split terms independently to 6dp, so the
        # split conserves only up to that sub-cent granularity (not an economic
        # leak — the pre-rounding identity g = buyer_share + merch_share is exact
        # per cleared unit).
        A_ok = abs(A.total_growth - (A.buyer_growth + A.merchant_margin)) < 1e-4
        B_ok = abs(B.total_growth - (B.buyer_growth + B.merchant_margin)) < 1e-4
        tiers.append(TierGrowth(tf=tf, gA_consumer_merchant=round(gA, 6),
                                gB_merchant_supplier=round(gB, 6),
                                chain_total=round(gA + gB, 6),
                                A_split_ok=A_ok, B_split_ok=B_ok))
    return {"p_spoilA": p_spoilA, "p_spoilB": p_spoilB,
            "interfaceA_salvage": salvA, "interfaceB_salvage": salvB,
            "tiers": [t.__dict__ for t in tiers],
            "unified_lever_module": coordinate.__module__,
            "conserves": all(t.A_split_ok and t.B_split_ok for t in tiers)}


# ── S3 tier-2/3, measured in the REAL multi-issue engine ────────────────────

def cogs_vs_certainty(seed: int, weeks: int, *, noise_uncertain: float = 0.15,
                      noise_certain: float = 0.075) -> dict:
    """The flywheel made concrete with dollars: as the demand agent tightens the
    forecast (noise ↓), the ProcurementMarket sheds overage and the negotiated
    COGS falls. Reports per-venue COGS scale and block-wide spoilage/joint at
    both certainty levels (the real wholesale engine, no abstraction)."""
    from wholesale.block_supply import endogenous_scales
    out = {}
    for tag, noise in (("uncertain", noise_uncertain), ("certain", noise_certain)):
        spoil = joint = 0.0
        for wk in range(weeks):
            recs, _ = ProcurementMarket(seed, wk, noise=noise).run_block_week("nego")
            for r in recs:
                spoil += r["spoiled"]
                joint += r["real_u_v"] + r["real_w_contrib"]
        out[tag] = {"noise": noise, "scales": endogenous_scales(seed, weeks, noise=noise),
                    "spoil_per_week": round(spoil / weeks, 2),
                    "joint_per_week": round(joint / weeks, 2)}
    return out

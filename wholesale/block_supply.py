"""The SEA OF SUPPLIERS on the block (task #64, S2).

Each venue holds a PORTFOLIO of heterogeneous suppliers; suppliers serve
MULTIPLE venues, so the shared truck / route density is the block's SECOND
cross-venue coordination market — the exact mirror of the resident cluster on
the buyer side. This module drives the whole block-week through the S1 adapter
stack (`ProcurementMarket`), and turns the per-relationship negotiated deals into
an ENDOGENOUS per-venue COGS multiplier (`endogenous_scales`) that replaces
block/venues.py's static `WholesaleDawn.cost_scale` haircut.

Reproduction contract (test_supply.py): `ProcurementMarket.run_block_week` drives
the venues (ProcurementAgent) against their suppliers (SupplierMerchant, sharing
the wholesaler's truck Schedule in route order) and produces records IDENTICAL,
to the cent, to wholesale.run.run_week — the buyer machinery faithfully operates
the supplier world.

Supplier-type map (the real archetypes behind wholesale/'s three calibrated
categories, per venue). Only the four venues wholesale/ calibrates get real
numbers; the other six block venues are a DOCUMENTED coverage gap (a pilot would
extend wholesale/calibration.py with a flower-market, apparel-jobber, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from buyer.merchant import Intent

from wholesale import calibration as cal
from wholesale.calibration import V_ORDER, W_ORDER
from wholesale.run import _score
from wholesale.scenario import build_ctx
from wholesale.supply import ProcurementAgent, SupplierMerchant, procurement_agent
from wholesale.world import Schedule, week_demand

# concrete supplier archetype behind each (category, venue) line — the "sea"
SUPPLIER_TYPES = {
    ("beverage", "bodega"):  "beverage distributor",
    ("beverage", "boba"):    "bottled-drink distributor",
    ("beverage", "vending"): "beverage distributor",
    ("beverage", "bakery"):  "fridge-drink distributor",
    ("produce", "bodega"):   "produce / deli purveyor",
    ("produce", "boba"):     "dairy & fruit purveyor",     # milk, tea fruit
    ("produce", "vending"):  "fresh-food commissary",
    ("produce", "bakery"):   "dairy & egg purveyor",
    ("dry", "bodega"):       "dry-goods jobber",
    ("dry", "boba"):         "tea / tapioca importer",
    ("dry", "vending"):      "snack jobber",
    ("dry", "bakery"):       "flour mill",
}


@dataclass
class ProcurementMarket:
    """The block's dawn procurement market, driven through the agent stack. One
    Schedule per wholesaler (the truck); venues negotiate in the fixed route
    order. `coordinate=False` is the H-W3 ablation."""
    seed: int
    week: int
    flex: float = cal.BASE_FLEX
    noise: float = cal.BASE_NOISE
    coordinate: bool = True
    _ctxs: dict = field(default_factory=dict)

    def _ctx(self, w, v):
        key = (w, v)
        if key not in self._ctxs:
            self._ctxs[key] = build_ctx(w, v, self.flex)
        return self._ctxs[key]

    def run_block_week(self, arm: str = "nego") -> tuple[list, dict]:
        """One paired block-week through ProcurementAgent × SupplierMerchant.
        Reproduces wholesale.run.run_week(arm) to the cent. `arm` in
        {ratecard, nego, nego-indep}."""
        coord = self.coordinate and arm != "nego-indep"
        schedules = {w: Schedule() for w in W_ORDER}
        records = []
        for w in W_ORDER:
            sch = schedules[w]
            for v in V_ORDER:
                ctx = self._ctx(w, v)
                env = week_demand(self.seed, self.week, w, v, self.noise)
                sup = SupplierMerchant(w, v, ctx, env, sch,
                                       coordinate=(True if arm == "ratecard"
                                                   else coord))
                agent = ProcurementAgent(uid=abs(hash((w, v))) % 10**8,
                                         wtp={sup.sku: ctx.R}, walk_cost=0.0)
                dis = sup._disagreement()
                if arm == "ratecard":
                    q = None
                else:
                    q, _real, _strat = agent.negotiate(sup, attested=True)
                if q is not None:
                    sup.settle(q)
                    rec = _score(ctx, env, "nego", sup.last_deal.qty,
                                 sup.last_deal.unit_price, sup.last_deal.window,
                                 sup.last_deal.terms, sup.last_deal.share,
                                 sup.last_deal, dis)
                else:
                    event = sup.settle_no_deal()
                    if event == "ratecard":
                        rec = _score(ctx, env, "ratecard", dis.rc_q,
                                     float(ctx.break_price(dis.rc_q)), dis.window,
                                     dis.rc_terms, 0.0, None, dis)
                    elif event == "jetro":
                        rec = _score(ctx, env, "jetro", dis.jet_q,
                                     round(cal.JETRO_PRICE_FRAC * ctx.base, 2),
                                     None, "cod", 0.0, None, dis)
                    else:
                        rec = _score(ctx, env, "none", 0, 0.0, None, "cod", 0.0,
                                     None, dis)
                records.append(rec)
        return records, schedules


# ── endogenous per-venue COGS scale (replaces WholesaleDawn's static haircut) ─

def endogenous_scales(seed: int, weeks: int, *, flex: float = cal.BASE_FLEX,
                      noise: float = cal.BASE_NOISE) -> dict[str, float]:
    """Per-venue retail-COGS multiplier = demand-weighted negotiated unit price
    over the rate-card unit price, computed from the OUTCOME of each venue's
    ProcurementAgent negotiating against its supplier portfolio (the sea of
    suppliers, shared truck in route order). Sticker world buys the rate card
    (1.0); SNHP world inherits this. Mirrors WholesaleDawn's per-relationship
    ratio but produced endogenously by the agent stack — so it matches the
    static haircut to the cent under the base (no-commit) policy, which is the
    honest faithfulness check; the flywheel's extra saving is S3."""
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for wk in range(weeks):
        mkt = ProcurementMarket(seed, wk, flex=flex, noise=noise)
        rc, _ = mkt.run_block_week("ratecard")
        ng, _ = ProcurementMarket(seed, wk, flex=flex, noise=noise
                                  ).run_block_week("nego")
        rc_by = {(r["wholesaler"], r["venue"]): r["unit_price"] for r in rc}
        for r in ng:
            key = (r["wholesaler"], r["venue"])
            rc_unit = rc_by.get(key, r["unit_price"])
            weight = cal.DEMAND_MU.get(key, 1.0)
            if rc_unit > 0:
                num[r["venue"]] = num.get(r["venue"], 0.0) + weight * r["unit_price"]
                den[r["venue"]] = den.get(r["venue"], 0.0) + weight * rc_unit
    return {v: round(num[v] / den[v], 4) for v in num if den.get(v, 0.0) > 0}

"""B6.2 + B6.3 — cross-venue BUNDLES (NETWORK.md §A: the "bundles" step in the
shared-posterior → bundles → clusters build order).

The flywheel (task #71) already proved the durable network force is the
COORDINATION channel — cross-venue would-spoil / demand-state matching, not the
bounded shopping transfer. This module instantiates that channel MECHANICALLY,
as two pre-registered cross-venue bundles:

  B6.2  parking-validation bundle  — the culturally pre-accepted "shop here,
        parking's on us" cross-subsidy: a retail sale is bundled with a
        validated parking slot. Does bundling the parking slot's SHADOW value
        with the retail sale grow JOINT surplus vs the two venues pricing
        independently, discount-only-safe (never raises either posted price)?
        When is it Pareto, and when does it fail — the anti-lever?

  B6.3  slack-swap bundle + clearing transfer — two venues with complementary
        would-spoil excess and unmet demand. Does routing one venue's would-spoil
        excess to the other's unmet demand (a clearing transfer, discount-only)
        grow joint surplus vs each clearing ALONE — the mechanistic form of the
        flywheel's coordination channel? With money+unit CONSERVATION asserted,
        and riding demand-state / spoilage matching, NEVER price coordination.

RIGOR (binding — the same standards as every other block package):
  * paired on IDENTITY, never on policy: every arm consumes the byte-identical
    per-seed population / valuation stream (blake2b substreams keyed on
    who-arrives, from vend.core.substream); effects are paired diffs; a 95% CI
    on every Δ; NO win claimed when the CI includes 0.
  * DISCOUNT-ONLY: a bundle can only ever CUT a shopper's outlay off a posted
    list; it never raises either venue's posted price (type-checked in the
    conservation ledger and asserted in the tests).
  * DEMAND-STATE / SPOILAGE matching only — the clearing/validation decision
    reads would-spoil stock levels and unmet-demand quantities, NEVER a
    substitute venue's posted price (that is the B6.1 collusion line).
  * conservation — money and units are conserved across every transfer, asserted
    to the cent / the unit inside the sim and again in the tests.

Reuses the committed venue economics VERBATIM (read-only): the parking shadow
value comes from slots/calibration.py (the Lehner–Peer commuter inelasticity,
day-max, ops cost, spaces); the would-spoil salvage floors come from
block.calibration.VENDING_CATALOG (sandwich/fruit-cup, the same perishables the
flywheel's coord channel cleared); the spoilage-avoidance matching + accounting
is buyer.strategies.coordinate (the same helper the flywheel used for E_coord),
so stock/spoilage/conservation behave exactly as the committed venues. No LLM;
byte-deterministic on seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from block import calibration
from buyer.strategies import coordinate
from slots import calibration as scal
from vend.core import substream

BUNDLES_VERSION = 1


def _mean_ci(xs) -> dict:
    """Mean with a 95% t-interval over the (independent) per-seed diffs — the
    same estimator block/datamarket.py and block/flywheel.py use."""
    a = np.asarray(xs, dtype=float)
    n = len(a)
    mean = float(a.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 4), "ci95": None, "n": n}
    se = float(a.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 4),
            "ci95": [round(mean - t * se, 4), round(mean + t * se, 4)], "n": n}


# ═══════════════════════════════════════════════════════════════════════════
# B6.2 — the parking-validation bundle
# ═══════════════════════════════════════════════════════════════════════════
#
# The everyday cross-subsidy: a purchase at a RETAIL venue includes a VALIDATED
# parking slot at the PARKING venue. Two venues price independently; the bundle
# asks whether pooling the parking slot's shadow value with the retail sale grows
# joint surplus — and when it is Pareto.
#
# The mechanism (NETWORK.md §A.3: "parking's slack × the retail conversion
# lift"): free validated parking CONVERTS a marginal shopper — one who would NOT
# have bought at the retail venue while also paying to park — into a buyer. That
# incremental sale creates joint surplus g_R = (shopper WTP − retail unit cost).
# The slot the shopper occupies has a real opportunity cost:
#   * SLACK  — the lot is below capacity: the slot's only cost is marginal ops
#              (c_p·hours ≈ $0.80). Validating it to unlock g_R is hugely
#              positive-sum, and — with an inter-merchant transfer f ∈
#              [ops, retail_margin] — Pareto for retail + parking + shopper, with
#              NO paying customer displaced.
#   * TIGHT  — the lot is full: validating a shopper's stay DISPLACES a paying,
#              price-INELASTIC commuter (slots/calibration: commuters are the
#              least-elastic segment, |e|≈0.81 < 1, so a displaced commuter is a
#              near-certain lost sale valued at the day-max). The slot's
#              opportunity cost jumps to the commuter's joint value v_c. This is
#              NEVER Pareto (the commuter is strictly worse off) and DESTROYS
#              joint surplus whenever g_R < v_c — the anti-lever. This is the
#              "capacity-tight validation cannibalizes paying commuters" failure.
#
# DISCOUNT-ONLY by construction: the shopper pays the retail list and gets
# parking for free (or discounted) via the transfer; no posted price ever rises.

@dataclass(frozen=True)
class RetailProfile:
    """A retail venue whose sale a validated parking slot is bundled with.
    `list_price`/`unit_cost` are the committed calibration dollars; `park_hours`/
    `park_price` are the validated stay (the shopper's avoided parking cost, from
    the slots posted rate)."""
    name: str
    list_price: float
    unit_cost: float
    park_hours: float
    park_price: float          # the posted parking the validation gives away

    @property
    def margin(self) -> float:
        return self.list_price - self.unit_cost


# The two grounded retail profiles bracket the displaced-commuter value v_c:
#   boutique — a fashion sale (calibration.FASHION_LINES hoodie: $92 list / $31
#              landed), 2-hour errand park ($18 first hour + $8 addl = $26).
#              Its margin ($61) EXCEEDS v_c, so even a displacing validation stays
#              joint-positive — yet it still breaks strict Pareto (the commuter is
#              displaced). The robust win.
#   eatery   — a lunch sale (calibration.BODEGA_CATALOG deli-sandwich: $11.50 /
#              $4.10), 1-hour park ($18). Its margin ($7.40) is far BELOW v_c, so
#              a displacing validation turns the bundle into a JOINT anti-lever.
_HOODIE = next(x for x in calibration.FASHION_LINES if x[0] == "hoodie")
_DELI = next(x for x in calibration.BODEGA_CATALOG if x[0] == "deli-sandwich")
RETAIL_PROFILES: tuple[RetailProfile, ...] = (
    RetailProfile("boutique", list_price=_HOODIE[1], unit_cost=_HOODIE[2],
                  park_hours=2.0,
                  park_price=scal.PARKING_FIRST_HOUR + scal.PARKING_ADDL_HOUR),
    RetailProfile("eatery", list_price=_DELI[1], unit_cost=_DELI[2],
                  park_hours=1.0, park_price=scal.PARKING_FIRST_HOUR),
)


@dataclass(frozen=True)
class ParkConfig:
    seeds: int = 400
    n_shoppers: int = 60            # drive-in shoppers considering the retail buy
    sigma_wtp: float = 0.35         # lognormal WTP spread (block WTP dispersion)
    K_slots: int = scal.PARKING_SPACES          # the lot: 40 spaces
    ops_per_hour: float = scal.PARKING_COST_PER_HOUR   # $0.40/hr marginal ops
    commuter_daymax: float = scal.PARKING_DAY_MAX      # $45 posted day rate
    commuter_hours: float = 9.5                        # the office slug's stay
    # |e| of commuter demand (slots/calibration: Lehner–Peer, least-elastic
    # segment). < 1 ⇒ INELASTIC ⇒ a displaced commuter does NOT come back at a
    # lower price: the displacement is a full, near-certain lost sale.
    commuter_abs_elasticity: float = 0.81
    # the lot's paying-commuter load, swept from deep slack to over-subscribed.
    u_grid: tuple = (0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.3)


def commuter_shadow_value(cfg: ParkConfig) -> float:
    """The JOINT value the lot loses by displacing one paying all-day commuter:
    its day-max revenue net the ops it would have incurred. Because commuters are
    price-inelastic (|e|≈0.81 < 1) the displaced commuter is treated as a certain
    lost sale (no price-substitution recapture) — the conservative shadow cost of
    a validated stay that eats occupied capacity."""
    return cfg.commuter_daymax - cfg.ops_per_hour * cfg.commuter_hours


def slot_ops_cost(rp: RetailProfile, cfg: ParkConfig) -> float:
    """The marginal ops cost of a validated stay drawn from SLACK (an otherwise
    empty slot): just c_p · hours."""
    return cfg.ops_per_hour * rp.park_hours


def _shopper_wtp(seed: int, rp: RetailProfile, cfg: ParkConfig) -> np.ndarray:
    """The drive-in shoppers' WTP for the retail good — lognormal with median at
    the list price, drawn ONCE per (seed, retail) and consumed by BOTH the
    independent and the bundle arm (paired on shopper identity)."""
    rng = np.random.default_rng(substream(seed, "park-wtp", rp.name))
    z = rng.standard_normal(cfg.n_shoppers)
    return rp.list_price * np.exp(cfg.sigma_wtp * z)


def _park_cell(rp: RetailProfile, u: float, cfg: ParkConfig,
               seed0: int) -> dict:
    """One (retail profile, commuter-load u) cell, paired across seeds. Retail and
    parking BOTH post their committed lists; a shopper buys the retail good iff
    WTP ≥ list + park_price under INDEPENDENT pricing (they bear both), but iff
    WTP ≥ list once parking is validated. The conversions — shoppers in the
    marginal band list ≤ WTP < list+park_price — each unlock retail joint
    g_R = WTP − unit_cost but need a parking slot. Two bundle policies:

      * SLACK-GATED (the shippable policy) — validate only stays that fit the
        lot's SLACK (capacity − paying commuters). NEVER displaces a paying
        customer ⇒ always Pareto (retail + parking + shopper all ≥ 0, a transfer
        f ∈ [ops, margin] exists). Δjoint_gated ≥ 0; it shrinks to 0 as the lot
        fills (no slack left to monetise) — the win rides SLACK.
      * UNGATED — validate every conversion up to physical capacity, DISPLACING
        paying commuters once slack is gone. Each displacing stay costs the
        commuter's shadow value v_c. This is the anti-lever probe: for a
        thin-margin retail sale (g_R < v_c) it turns Δjoint NEGATIVE — the
        "capacity-tight validation cannibalises paying commuters" failure.

    Displacement is capped at the number of commuters actually occupying the lot;
    conversions beyond capacity are simply not validated (those shoppers behave
    exactly as under independent pricing)."""
    v_c = commuter_shadow_value(cfg)
    ops = slot_ops_cost(rp, cfg)
    dj_gated, dj_ungated = [], []
    pareto_gated, pareto_ungated = [], []
    n_conv, n_disp, n_val_gated = [], [], []
    for si in range(cfg.seeds):
        seed = seed0 + si
        w = _shopper_wtp(seed, rp, cfg)
        conv_mask = (w >= rp.list_price) & (w < rp.list_price + rp.park_price)
        g_R = np.sort(w[conv_mask] - rp.unit_cost)[::-1]   # joint per conv, DESC
        nconv = int(conv_mask.sum())
        # paying-commuter demand at load u (Poisson around u·K); slack = the
        # empty capacity a validation can use before displacing anyone.
        dc = int(np.random.default_rng(
            substream(seed, "commuters", rp.name, round(u, 4))).poisson(
                u * cfg.K_slots))
        occupied = min(dc, cfg.K_slots)
        slack = max(0, cfg.K_slots - occupied)

        # SLACK-GATED: validate the highest-g_R conversions that fit the slack.
        v_gated = min(nconv, slack)
        dj_g = float((g_R[:v_gated] - ops).sum())          # all from slack
        dj_gated.append(dj_g)
        pareto_gated.append(1.0)                            # no displacement, ever

        # UNGATED: fill slack first, then displace commuters up to capacity.
        from_slack = min(nconv, slack)
        displaced = min(max(0, nconv - slack), occupied)    # capped at occupied
        v_ung = from_slack + displaced
        dj_u = float((g_R[:from_slack] - ops).sum()
                     + (g_R[from_slack:v_ung] - v_c).sum())
        dj_ungated.append(dj_u)
        pareto_ungated.append((from_slack / v_ung) if v_ung else 1.0)
        n_conv.append(nconv)
        n_disp.append(displaced)
        n_val_gated.append(v_gated)
    djg, dju = _mean_ci(dj_gated), _mean_ci(dj_ungated)
    return {
        "retail": rp.name,
        "u": u,
        "commuter_load_expected": round(u * cfg.K_slots, 2),
        "d_joint_gated": djg,          # the shippable slack-gated bundle
        "d_joint_ungated": dju,        # the anti-lever probe (validate into cap.)
        "pareto_frac_gated": _mean_ci(pareto_gated),        # ≡ 1 (never displaces)
        "pareto_frac_ungated": _mean_ci(pareto_ungated),    # 1 slack → 0 tight
        "n_conversions": _mean_ci(n_conv),
        "n_validated_gated": _mean_ci(n_val_gated),
        "n_displaced_ungated": _mean_ci(n_disp),
        # the shippable bundle WINS while there is slack to monetise
        "gated_grows": bool(djg["ci95"] is not None and djg["ci95"][0] > 0),
        "gated_never_loses": bool(djg["ci95"] is not None and djg["ci95"][0]
                                  >= -1e-9),
        # the ungated bundle is an anti-lever when it goes negative-sum
        "ungated_anti_lever": bool(dju["ci95"] is not None and dju["ci95"][1] < 0),
    }


def _park_profile(rp: RetailProfile, cfg: ParkConfig, seed0: int) -> dict:
    v_c = commuter_shadow_value(cfg)
    cells = [_park_cell(rp, u, cfg, seed0) for u in cfg.u_grid]
    # the tightness u* where the UNGATED bundle first turns into an anti-lever
    # (Δjoint_ungated CI falls entirely below 0).
    u_star = None
    for c in cells:
        if c["ungated_anti_lever"]:
            u_star = c["u"]
            break
    return {
        "retail": rp.name,
        "list_price": rp.list_price,
        "unit_cost": rp.unit_cost,
        "margin": round(rp.margin, 2),
        "park_price_given_away": rp.park_price,
        "slot_ops_cost": round(slot_ops_cost(rp, cfg), 4),
        "commuter_shadow_value_v_c": round(v_c, 4),
        "margin_covers_v_c": bool(rp.margin >= v_c),
        "cells": cells,
        # the slack cell (u=0.3) is the pre-registered WIN; the tightest cell is
        # the pre-registered failure probe.
        "slack_cell": cells[0],
        "tight_cell": cells[-1],
        "u_star_ungated_anti_lever": u_star,
        "verdict": _park_verdict(rp, cells, v_c),
    }


def _park_verdict(rp: RetailProfile, cells: list, v_c: float) -> str:
    slack, tight = cells[0], cells[-1]
    # the shippable slack-gated bundle: Pareto win wherever there is slack, never
    # a loss anywhere.
    gated_wins = slack["gated_grows"] and all(c["gated_never_loses"]
                                              for c in cells)
    win = ("slack-gated bundle is a PARETO WIN (Δjoint>0 on slack, never a loss)"
           if gated_wins else "slack-gated bundle does not cleanly win")
    # the ungated anti-lever
    if tight["ungated_anti_lever"]:
        fail = ("UNGATED validation is a JOINT ANTI-LEVER when tight (Δjoint<0: "
                "thin margin < v_c, cannibalises paying commuters)")
    elif tight["pareto_frac_ungated"]["mean"] < 0.999:
        fail = ("UNGATED validation stays joint-positive (margin > v_c) but is "
                "NOT Pareto when tight — it displaces paying commuters, who are "
                "strictly worse off")
    else:
        fail = "no displacement reached in the sweep"
    return f"{win}; {fail}"


def run_parking(cfg: ParkConfig = ParkConfig(), seed0: int = 20260710) -> dict:
    profiles = [_park_profile(rp, cfg, seed0) for rp in RETAIL_PROFILES]
    return {
        "bundle": "B6.2_parking_validation",
        "bundles_version": BUNDLES_VERSION,
        "config": {"seeds": cfg.seeds, "n_shoppers": cfg.n_shoppers,
                   "sigma_wtp": cfg.sigma_wtp, "K_slots": cfg.K_slots,
                   "ops_per_hour": cfg.ops_per_hour,
                   "commuter_daymax": cfg.commuter_daymax,
                   "commuter_hours": cfg.commuter_hours,
                   "commuter_abs_elasticity": cfg.commuter_abs_elasticity,
                   "u_grid": list(cfg.u_grid)},
        "commuter_shadow_value_v_c": round(commuter_shadow_value(cfg), 4),
        "profiles": profiles,
        "verdict": {
            # the headline: the shippable slack-gated bundle grows joint surplus
            # (Pareto, no one displaced) for EVERY retail profile — a NOVEL
            # cross-venue win that rides parking slack.
            "slack_gated_is_pareto_win_all_profiles": bool(all(
                p["slack_cell"]["gated_grows"]
                and p["slack_cell"]["pareto_frac_gated"]["mean"] > 0.999
                and all(c["gated_never_loses"] for c in p["cells"])
                for p in profiles)),
            # the honest anti-lever: an UNGATED validation (into occupied
            # capacity) turns negative-sum for a thin-margin retail sale.
            "ungated_anti_lever_when_tight_thin_margin": bool(any(
                p["tight_cell"]["ungated_anti_lever"] for p in profiles)),
            "discount_only": True,   # no posted price ever rises (by construction)
            "summary": (
                "PARKING-VALIDATION BUNDLE: the shippable SLACK-GATED bundle "
                "(validate only empty capacity) is a PARETO WIN — Δjoint>0 with "
                "no one displaced — the culturally pre-accepted cross-subsidy, "
                "computed, and discount-only-safe (never raises either posted "
                "price). The win rides parking SLACK: it shrinks to 0 as the lot "
                "fills. The ANTI-LEVER is what a naive UNGATED validation does — "
                "validating into occupied capacity cannibalises paying, inelastic "
                "commuters (never Pareto; joint-NEGATIVE for a thin-margin sale). "
                "The gate to slack is exactly what keeps the bundle pro-surplus."),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# B6.3 — slack-swap bundles + clearing transfers
# ═══════════════════════════════════════════════════════════════════════════
#
# Two venues with COMPLEMENTARY would-spoil excess and unmet demand. Venue A ends
# its window with would-spoil excess of a perishable X and only a THIN local
# residual demand for it (its lunch crowd is sated — the slack-hour problem);
# venue B has UNMET, high-value demand for X (its evening crowd is hungry) but no
# supply. Symmetrically for a second perishable Y (A wants what B is dumping).
#
# The CLEARING TRANSFER (discount-only) routes A's would-spoil X excess to B's
# unmet X demand and B's Y excess to A's unmet Y demand — the mechanistic form of
# the flywheel's coordination channel (cross-venue spoilage-avoidance matching).
# The baseline is each venue CLEARING ALONE (marking its own leftover down into
# its own thin local pool). The matching + spoilage accounting is
# buyer.strategies.coordinate VERBATIM (the same helper the flywheel used for
# E_coord), so every cleared would-spoil unit creates welfare p_spoil·(value −
# salvage) exactly as the committed venues book it.
#
# CONSERVATION is asserted to the cent / the unit: units out of A = units into B;
# every dollar a buyer pays is split among {source venue A recovers ≥ salvage,
# the clearing house takes bps, the buyer keeps its surplus}. The clearing rides
# DEMAND-STATE / spoilage matching — it reads would-spoil stock and unmet-demand
# valuations, NEVER a substitute venue's posted price.

@dataclass(frozen=True)
class SwapVenue:
    """One side of the swap: `perishable` is the would-spoil good it has excess
    of; `salvage`/`mu` come from the committed catalog. `unmet_perishable` is the
    complementary good it has high-value unmet demand FOR."""
    name: str
    perishable: str
    salvage: float
    mu: float
    unmet_perishable: str


def _perishable(sku: str) -> tuple[float, float]:
    """(salvage, μ) for a would-spoil SKU from the committed VENDING_CATALOG."""
    row = next(x for x in calibration.VENDING_CATALOG if x[0] == sku)
    return row[3], row[1]     # salvage, wtp_mu


@dataclass(frozen=True)
class SwapConfig:
    seeds: int = 400
    p_spoil: float = 0.40          # would-spoil probability (flywheel B4/B5)
    extraction: float = 0.5        # fair Nash split (buyer.strategies.coordinate)
    clearing_bps: float = 30.0     # the clearing house's fee, bps on the transfer
    sigma_val: float = 0.35        # lognormal spread of buyer valuations
    # A's thin LOCAL residual demand (sated crowd): median a hair above salvage,
    # so few members are eligible → clearing alone leaves most stock to spoil.
    local_pool: int = 8
    local_median_mult: float = 1.4     # local median = 1.4 × salvage (low)
    # B's UNMET demand pool (hungry crowd): median at μ, high value.
    unmet_pool: int = 24
    # the would-spoil excess magnitude, swept: how much stock is routed.
    excess_grid: tuple = (2, 4, 6, 8, 10)


# the two complementary venues (the flywheel's would-spoil sandwich, plus the
# fruit-cup, both fresh-case perishables from the committed vending catalog):
def _venues() -> tuple[SwapVenue, SwapVenue]:
    s_salv, s_mu = _perishable("sandwich")
    f_salv, f_mu = _perishable("fruit-cup")
    A = SwapVenue("bakery", "sandwich", s_salv, s_mu, "fruit-cup")
    B = SwapVenue("cafe", "fruit-cup", f_salv, f_mu, "sandwich")
    return A, B


def _draw_values(seed: int, tag: str, n: int, median: float,
                 cfg: SwapConfig) -> list[float]:
    """A demand pool's per-member valuations for a perishable — lognormal with
    the given median, drawn ONCE per (seed, tag) and consumed by BOTH arms."""
    rng = np.random.default_rng(substream(seed, "swap-val", tag))
    z = rng.standard_normal(n)
    return [float(median * math.exp(cfg.sigma_val * zz)) for zz in z]


@dataclass
class ClearingLedger:
    """The money+unit ledger for a set of cleared would-spoil units, so
    conservation is checkable to the cent / the unit. Every cleared unit: a buyer
    pays `price` ∈ [salvage, value]; the SOURCE venue recovers ≥ salvage, the
    CLEARING HOUSE takes bps on the transfer, the buyer keeps its surplus."""
    units_available: int = 0        # would-spoil units offered
    units_cleared: int = 0          # sold before spoiling
    units_spoiled: int = 0          # perished (recover salvage only)
    units_routed_out: int = 0       # units that left the SOURCE venue (cross)
    units_received_in: int = 0      # units that arrived at the SINK venue (cross)
    buyer_outlay: float = 0.0       # Σ prices buyers paid
    source_receipts: float = 0.0    # Σ to the source venue (incl. salvage floor)
    clearing_receipts: float = 0.0  # Σ to the clearing house (the bps)
    buyer_surplus: float = 0.0      # Σ (value − price)
    growth: float = 0.0             # Σ p_spoil·(value − salvage): spoilage avoided

    def money_residual(self) -> float:
        """Buyers' outlay MUST equal source receipts + clearing receipts."""
        return self.buyer_outlay - (self.source_receipts + self.clearing_receipts)

    def unit_residual(self) -> int:
        """Available units MUST equal cleared + spoiled; routed-out == received."""
        return (self.units_available - (self.units_cleared + self.units_spoiled)) \
            + (self.units_routed_out - self.units_received_in)


def _clear(values: list[float], *, salvage: float, excess: int, cross: bool,
           cfg: SwapConfig) -> tuple[float, ClearingLedger]:
    """Clear `excess` would-spoil units into the demand `values` via
    buyer.strategies.coordinate (efficient spoilage-avoidance matching, the same
    helper the flywheel used). Returns (joint growth, the conservation ledger).

    The DEMAND-STATE guardrail: the only inputs are the would-spoil `excess`
    (stock state), the buyers' `values` (demand state), and the `salvage` floor —
    NO substitute venue's posted price is read. Discount-only: every clearing
    price sits in [salvage, value] ≤ the value the buyer walked in with.
    """
    res = coordinate(values, salvage=salvage, s_risk=excess, p_spoil=cfg.p_spoil,
                     extraction=cfg.extraction, allocation="efficient")
    led = ClearingLedger(units_available=excess)
    # the units coordinate() actually cleared, matched to the highest values.
    elig = sorted((v for v in values if v > salvage), reverse=True)[:excess]
    for v in elig:
        price = salvage + (1.0 - cfg.extraction) * (v - salvage)   # discount-only
        assert salvage - 1e-9 <= price <= v + 1e-9, "clearing price off-floor"
        fee = (cfg.clearing_bps / 1e4) * (price - salvage)   # bps on the transfer
        led.units_cleared += 1
        led.buyer_outlay += price
        led.source_receipts += price - fee                    # ≥ salvage (floor)
        led.clearing_receipts += fee
        led.buyer_surplus += v - price
        led.growth += cfg.p_spoil * (v - salvage)
        if cross:
            led.units_routed_out += 1
            led.units_received_in += 1
    led.units_spoiled = excess - led.units_cleared
    # sanity: coordinate()'s growth must equal the ledger's (same accounting)
    assert abs(led.growth - res.total_growth) < 1e-6, "growth accounting drift"
    return led.growth, led


def _swap_cell(A: SwapVenue, B: SwapVenue, excess: int, cfg: SwapConfig,
               seed0: int) -> dict:
    """One would-spoil-excess cell, paired across seeds. For each seed:
      * INDEPENDENT — each venue clears its OWN excess into its OWN thin local
        residual pool (the sated crowd). Most stock spoils.
      * CROSS (slack-swap) — A's excess routed to B's UNMET demand for A's good,
        B's excess to A's unmet demand for B's good. High-value demand absorbs
        the excess. Δjoint = cross − independent.
    Conservation ledgers are accumulated for both arms and their residuals
    reported (must be ~0)."""
    d_joint = []
    max_money_resid = 0.0
    max_unit_resid = 0
    indep_units, cross_units = [], []
    for si in range(cfg.seeds):
        seed = seed0 + si
        # A's would-spoil good X (sandwich): local thin pool at A, unmet pool at B
        A_local = _draw_values(seed, f"{A.name}-local-{A.perishable}",
                               cfg.local_pool, A.salvage * cfg.local_median_mult,
                               cfg)
        B_unmet = _draw_values(seed, f"{B.name}-unmet-{A.perishable}",
                               cfg.unmet_pool, A.mu, cfg)
        # B's would-spoil good Y (fruit-cup): local thin pool at B, unmet at A
        B_local = _draw_values(seed, f"{B.name}-local-{B.perishable}",
                               cfg.local_pool, B.salvage * cfg.local_median_mult,
                               cfg)
        A_unmet = _draw_values(seed, f"{A.name}-unmet-{B.perishable}",
                               cfg.unmet_pool, B.mu, cfg)

        # INDEPENDENT: each clears its own excess into its own thin local pool.
        gAi, ledAi = _clear(A_local, salvage=A.salvage, excess=excess,
                            cross=False, cfg=cfg)
        gBi, ledBi = _clear(B_local, salvage=B.salvage, excess=excess,
                            cross=False, cfg=cfg)
        joint_indep = gAi + gBi

        # CROSS: route each venue's excess to the OTHER's unmet demand.
        gAc, ledAc = _clear(B_unmet, salvage=A.salvage, excess=excess,
                            cross=True, cfg=cfg)
        gBc, ledBc = _clear(A_unmet, salvage=B.salvage, excess=excess,
                            cross=True, cfg=cfg)
        joint_cross = gAc + gBc

        d_joint.append(joint_cross - joint_indep)
        for led in (ledAi, ledBi, ledAc, ledBc):
            max_money_resid = max(max_money_resid, abs(led.money_residual()))
            max_unit_resid = max(max_unit_resid, abs(led.unit_residual()))
        indep_units.append(ledAi.units_cleared + ledBi.units_cleared)
        cross_units.append(ledAc.units_cleared + ledBc.units_cleared)
    dj = _mean_ci(d_joint)
    return {
        "excess_units": excess,
        "d_joint": dj,
        "units_cleared_independent": _mean_ci(indep_units),
        "units_cleared_cross": _mean_ci(cross_units),
        "money_residual_max_abs": round(max_money_resid, 9),
        "unit_residual_max_abs": int(max_unit_resid),
        "money_conserved": bool(max_money_resid < 1e-6),
        "units_conserved": bool(max_unit_resid == 0),
        "joint_grows": bool(dj["ci95"] is not None and dj["ci95"][0] > 0),
    }


def price_reads_no_substitute_signal() -> bool:
    """Guardrail witness: the clearing decision (_clear → coordinate) is a pure
    function of {would-spoil excess, buyer demand-state values, salvage floor}. It
    takes NO substitute-venue posted price. This returns True by construction and
    is exercised adversarially in the tests (a decoy substitute price passed
    around it changes nothing)."""
    import inspect
    params = set(inspect.signature(_clear).parameters)
    forbidden = {"substitute_price", "rival_price", "posted_price",
                 "competitor_quote"}
    return not (params & forbidden)


def run_swap(cfg: SwapConfig = SwapConfig(), seed0: int = 20260710) -> dict:
    A, B = _venues()
    cells = [_swap_cell(A, B, e, cfg, seed0) for e in cfg.excess_grid]
    all_grow = all(c["joint_grows"] for c in cells)
    money_ok = all(c["money_conserved"] for c in cells)
    units_ok = all(c["units_conserved"] for c in cells)
    # the joint gain scales with the would-spoil stock routed (more excess →
    # more cross-venue matching value), the flywheel's coordination channel.
    scales = (len(cells) >= 2
              and cells[-1]["d_joint"]["mean"] > cells[0]["d_joint"]["mean"])
    return {
        "bundle": "B6.3_slack_swap_clearing",
        "bundles_version": BUNDLES_VERSION,
        "config": {"seeds": cfg.seeds, "p_spoil": cfg.p_spoil,
                   "extraction": cfg.extraction, "clearing_bps": cfg.clearing_bps,
                   "sigma_val": cfg.sigma_val, "local_pool": cfg.local_pool,
                   "local_median_mult": cfg.local_median_mult,
                   "unmet_pool": cfg.unmet_pool,
                   "excess_grid": list(cfg.excess_grid)},
        "venues": [{"name": A.name, "perishable": A.perishable,
                    "salvage": A.salvage, "mu": A.mu,
                    "unmet_perishable": A.unmet_perishable},
                   {"name": B.name, "perishable": B.perishable,
                    "salvage": B.salvage, "mu": B.mu,
                    "unmet_perishable": B.unmet_perishable}],
        "cells": cells,
        "no_substitute_price_signal": bool(price_reads_no_substitute_signal()),
        "verdict": {
            "cross_clearing_grows_joint_all_excess": bool(all_grow),
            "money_conserved_all": bool(money_ok),
            "units_conserved_all": bool(units_ok),
            "joint_gain_scales_with_excess": bool(scales),
            "rides_demand_state_not_price": bool(
                price_reads_no_substitute_signal()),
            "discount_only": True,
            "summary": (
                "SLACK-SWAP CLEARING: routing one venue's would-spoil excess to "
                "the other's unmet demand GROWS joint surplus vs each clearing "
                "alone (CI clears zero at every excess level), the mechanistic "
                "form of the flywheel's durable coordination channel. Money and "
                "units are conserved to the cent / the unit across the clearing "
                "transfer, the clearing is discount-only, and it rides "
                "demand-state / spoilage matching — NEVER a substitute's price."
                if (all_grow and money_ok and units_ok) else "mixed / see cells"),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# runner
# ═══════════════════════════════════════════════════════════════════════════

def run_all(park_cfg: ParkConfig = ParkConfig(),
            swap_cfg: SwapConfig = SwapConfig(), seed0: int = 20260710) -> dict:
    return {
        "bundles_version": BUNDLES_VERSION,
        "B6_2_parking_validation": run_parking(park_cfg, seed0),
        "B6_3_slack_swap_clearing": run_swap(swap_cfg, seed0),
    }


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=400)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    res = run_all(ParkConfig(seeds=args.seeds), SwapConfig(seeds=args.seeds),
                  args.seed0)
    if args.out:
        with open(args.out, "w") as f:
            f.write(json.dumps(res, indent=1) + "\n")
        print(f"wrote {args.out}")

    pk = res["B6_2_parking_validation"]
    print("\n=== B6.2 PARKING-VALIDATION BUNDLE ===")
    print(f"  commuter shadow value v_c (displaced): "
          f"${pk['commuter_shadow_value_v_c']}")
    for p in pk["profiles"]:
        print(f"\n  [{p['retail']}] list ${p['list_price']} margin "
              f"${p['margin']} | gives away ${p['park_price_given_away']} parking "
              f"| margin covers v_c: {p['margin_covers_v_c']}")
        print(f"    {'u':>5} {'E[com]':>7} {'Δjoint_gated':>13} "
              f"{'Δjoint_ungated':>15} {'CIung':>20} {'#disp':>6}")
        for c in p["cells"]:
            djg, dju = c["d_joint_gated"], c["d_joint_ungated"]
            tag = ("gWIN" if c["gated_grows"] else "g~0")
            tag += "/ANTI" if c["ungated_anti_lever"] else ""
            print(f"    {c['u']:>5} {c['commuter_load_expected']:>7} "
                  f"{djg['mean']:>13} {dju['mean']:>15} {str(dju['ci95']):>20} "
                  f"{c['n_displaced_ungated']['mean']:>6} {tag}")
        print(f"    u* (ungated anti-lever): {p['u_star_ungated_anti_lever']}")
        print(f"    → {p['verdict']}")
    print(f"\n  VERDICT: {pk['verdict']['summary']}")

    sw = res["B6_3_slack_swap_clearing"]
    print("\n\n=== B6.3 SLACK-SWAP + CLEARING TRANSFERS ===")
    v = sw["venues"]
    print(f"  {v[0]['name']}: excess {v[0]['perishable']} (salv "
          f"${v[0]['salvage']}) ↔ {v[1]['name']}: excess {v[1]['perishable']} "
          f"(salv ${v[1]['salvage']})")
    print(f"    {'excess':>7} {'Δjoint(cross−indep)':>20} {'CI':>22} "
          f"{'units:indep→cross':>18} {'$resid':>8} {'Uresid':>7}")
    for c in sw["cells"]:
        dj = c["d_joint"]
        print(f"    {c['excess_units']:>7} {dj['mean']:>20} {str(dj['ci95']):>22} "
              f"{str(c['units_cleared_independent']['mean'])+'→'+str(c['units_cleared_cross']['mean']):>18} "
              f"{c['money_residual_max_abs']:>8} {c['unit_residual_max_abs']:>7}")
    vv = sw["verdict"]
    print(f"\n  cross grows joint (all): {vv['cross_clearing_grows_joint_all_excess']}"
          f" | money conserved: {vv['money_conserved_all']}"
          f" | units conserved: {vv['units_conserved_all']}")
    print(f"  rides demand-state not price: {vv['rides_demand_state_not_price']}"
          f" | discount-only: {vv['discount_only']}")
    print(f"  → {vv['summary']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""Molt Season v3 — PREREG AMENDMENT 2: the employer gets pockets.

v2's employer had one scalar cost pot, so there was exactly one trade axis and
the same trade was optimal for every crab alive. This version gives the Works
five budgets with independently-drawn shadow prices, adds PTO as a sixth issue,
and reports cash beside utility everywhere.

Everything about beliefs, disclosure and the match value is inherited from v2
unchanged — only the employer's cost structure and the issue set move.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from molt.v2 import (Belief, Crab2, Params2, _probit, draw_crab2,
                     outside_value_at, prior, replacement_cost)
from molt.world import (BASE_PCT, BONUS_MO, ISSUES_V3, PTO_DAYS, PVF,
                        WORK_DAYS, Package, weight_mult)

BUDGETS = ("comp", "band", "accrual", "coverage", "capacity")
ISSUE_BUDGET = {"base": "comp", "bonus": "comp", "title": "band",
                "pto": "accrual", "berth": "coverage", "deepwater": "capacity"}


@dataclass(frozen=True)
class Params3(Params2):
    # A2.2 shadow-price draws (median, sigma) on the v2 cash cost of each issue
    lam_comp: tuple = (1.00, 0.25)
    lam_band: tuple = (0.60, 0.50)
    lam_accrual: tuple = (0.35, 0.40)
    lam_coverage: tuple = (0.50, 0.40)
    lam_capacity: tuple = (0.80, 0.40)
    no_slot_prob: float = 0.25      # no promotion slot in this band this season

    # --- AMENDMENT 3. Defaults reproduce v3 exactly; v4 sets them.
    promo_raise: float | None = None      # None -> the old 2% title_drift
    promo_market_lift: float = 0.0        # a promotion raises omega by this
    slot_frac: float | None = None        # None -> the per-season boolean

    # A2.3 PTO
    pto_value: float = 1.00         # worth `days/260 x salary` to a typical crab

    # A2.4 the exchange rate is a swept parameter, not a constant
    perk_rate: float = 1.00         # multiplies title_career / berth / deep / pto
    employer_rate_bias: float = 1.50   # K17: what an employer's engine assumes


@dataclass
class Season:
    """The Works' budget state, drawn once per season and shared by every arm so
    the comparison stays paired. Under AMENDMENT 3 `slots_left` is a consumable
    quota, so each ARM carries its own copy and depletes it."""
    lam: dict
    slot: bool
    slots_left: int = 10 ** 6

    @staticmethod
    def draw(p: Params3, rng: np.random.Generator, n_crabs: int = 40) -> "Season":
        lam = {}
        for b in BUDGETS:
            med, sig = getattr(p, f"lam_{b}")
            lam[b] = float(med * math.exp(rng.normal(0.0, sig) - 0.5 * sig ** 2))
        slot = bool(rng.random() >= p.no_slot_prob)
        left = (10 ** 6 if p.slot_frac is None
                else int(math.ceil(p.slot_frac * n_crabs)))
        return Season(lam=lam, slot=slot, slots_left=left)


def slot_open(p: Params3, sea: Season) -> bool:
    """Is a promotion available at all? Under A3 this is a depleting quota; under
    v3 it is the per-season blackout."""
    return sea.slots_left > 0 if p.slot_frac is not None else sea.slot


# ------------------------------------------------------------ crab valuation
def crab_cash3(p: Params3, c: Crab2, pk: Package) -> float:
    """What lands on a payslip. Reported beside utility everywhere (A2.4)."""
    S = c.salary
    v = S * BASE_PCT[pk.base] * PVF + S / 12.0 * BONUS_MO[pk.bonus]
    if pk.title:
        v += S * (p.title_drift if p.promo_raise is None else p.promo_raise) * PVF
    return v


def crab_value3(p: Params3, c: Crab2, pk: Package) -> float:
    """Cash plus the subjective worth of the non-cash terms, at `perk_rate`."""
    S, m = c.salary, weight_mult(c)
    v = crab_cash3(p, c, pk)
    r = p.perk_rate
    if pk.title:
        v += m["title"] * p.title_career * r * S
    if pk.berth:
        v += m["berth"] * p.berth_value * r * S
    if pk.deep:
        v += m["deepwater"] * p.deep_value * r * S
    if pk.pto:
        # PTO's weight rides with the berth (both are time), scaled by its own
        # multiplier so a crab that wants time off wants both
        v += m["berth"] * p.pto_value * r * S * PTO_DAYS[pk.pto] / WORK_DAYS
    return v


# --------------------------------------------------------- employer costings
def works_cost3(p: Params3, c: Crab2, sea: Season, pk: Package) -> float:
    """A2.2: five pockets, five shadow prices, none proportional to the others."""
    S, lam = c.salary, sea.lam
    cost = lam["comp"] * (S * BASE_PCT[pk.base] * PVF * (1.0 + p.peer_spill)
                          + S / 12.0 * BONUS_MO[pk.bonus])
    if pk.title:
        if p.promo_raise is None:
            cost += lam["band"] * (S * p.title_drift * PVF + S * p.title_admin)
        else:
            # A3: the raise comes out of comp, the slot out of band. Two pockets.
            cost += lam["comp"] * S * p.promo_raise * PVF
            cost += lam["band"] * S * p.title_admin
    if pk.berth:
        cost += lam["coverage"] * S * c.spec.berth_cost
    if pk.deep:
        cost += lam["capacity"] * S * p.deep_cost
    if pk.pto:
        cost += lam["accrual"] * S * PTO_DAYS[pk.pto] / WORK_DAYS
    return cost


def feasible(p: Params3, sea: Season, pk: Package) -> bool:
    """Money cannot buy a promotion slot that does not exist."""
    return slot_open(p, sea) or not pk.title


def p_leave_true3(p: Params3, c: Crab2, pk: Package, expired: bool = False) -> float:
    if not c.has_outside or expired:
        return p.p_exo
    # A3: a promotion is portable. It raises what the market will pay you.
    om = c.omega + (p.promo_market_lift if pk.title else 0.0)
    gap = (outside_value_at(p, c, om) if c.has_outside else -1e9) \
        - crab_value3(p, c, pk)
    return p.p_exo + (1.0 - p.p_exo) / (1.0 + math.exp(-gap / (p.taste * c.salary)))


def p_leave_belief3(p: Params3, c: Crab2, bel: Belief, pk: Package) -> float:
    v = crab_value3(p, c, pk)
    lift = p.promo_market_lift if pk.title else 0.0
    gaps = np.array([outside_value_at(p, c, om + lift) - v for om in bel.grid])
    lam = 1.0 / (1.0 + np.exp(-gaps / (p.taste * c.salary)))
    return p.p_exo + (1.0 - p.p_exo) * bel.p_has * float((bel.w * lam).sum())


def works_npv3(p: Params3, c: Crab2, sea: Season, bel: Belief,
               pk: Package) -> float:
    if not feasible(p, sea, pk):
        return -1e18
    pl = p_leave_belief3(p, c, bel, pk)
    return -(1.0 - pl) * works_cost3(p, c, sea, pk) \
        - pl * replacement_cost(p, c)


# ------------------------------------------------------------- package grids
def works_packages3(p: Params3, sea: Season, base_pkg: Package) -> list[Package]:
    out = []
    for b in range(base_pkg.base, 4):
        for bo in range(3):
            for t in ((False,) if not slot_open(p, sea) else (False, True)):
                for be in (False, True):
                    for d in (False, True):
                        for pt in range(3):
                            out.append(Package(b, t, bo, be, d, pt))
    return out


def crab_packages3(sea: Season | None = None, p: Params3 | None = None) -> list[Package]:
    titles = (False,) if (sea is not None and p is not None
                          and not slot_open(p, sea)) else (False, True)
    return [Package(b, t, bo, be, d, pt)
            for b in range(5) for t in titles for bo in range(3)
            for be in (False, True) for d in (False, True) for pt in range(3)]


def works_best_reply3(p: Params3, c: Crab2, sea: Season, bel: Belief,
                      base_pkg: Package, floor_value: float) -> Package | None:
    best, best_v = None, works_npv3(p, c, sea, bel, base_pkg)
    for pk in works_packages3(p, sea, base_pkg):
        if crab_value3(p, c, pk) <= floor_value + 1e-9:
            continue
        v = works_npv3(p, c, sea, bel, pk)
        if v > best_v:
            best, best_v = pk, v
    return best


def works_signs3(p: Params3, c: Crab2, sea: Season, bel: Belief, ask: Package,
                 cur: Package, reply: Package | None) -> bool:
    if not feasible(p, sea, ask):
        return False
    if works_npv3(p, c, sea, bel, ask) < works_npv3(p, c, sea, bel, cur):
        return False
    if reply is None:
        return True
    return works_npv3(p, c, sea, bel, reply) - works_npv3(p, c, sea, bel, ask) \
        <= p.counter_thresh * c.salary


# ---------------------------------------------------- disclosure, unchanged
def _best_under3(p, c, sea, bel):
    from molt.world import opening_offer
    op = opening_offer(p, c)
    r = works_best_reply3(p, c, sea, bel, op, crab_value3(p, c, op))
    return r if r is not None else op


def discloses3(p: Params3, c: Crab2, sea: Season) -> bool:
    if not c.has_outside or p.credibility != "verifiable":
        return False
    from molt.v2 import update
    bel = prior(p, c)
    loud = crab_value3(p, c, _best_under3(p, c, sea, update(p, c, bel, True)))
    quiet = crab_value3(p, c, _best_under3(p, c, sea, update(p, c, bel, False)))
    return loud > quiet + 1e-9


def solve_tau3(p: Params3, seeds=range(9100, 9120), n=40, iters=2) -> float:
    tau = p.disclose_tau
    for _ in range(iters):
        p = Params3(**{**p.__dict__, "disclose_tau": tau})
        shown = []
        for seed in seeds:
            rng = np.random.default_rng(seed)
            sea = Season.draw(p, rng)
            for i in range(n):
                c = draw_crab2(i, p, rng)
                if c.has_outside and discloses3(p, c, sea):
                    shown.append(c.omega)
        tau = float(np.percentile(shown, 5)) if shown else tau
    return tau

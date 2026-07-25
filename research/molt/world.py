"""Molt Season — the world: crabs, the Works, money, and the calendar.

Implements PREREG.md §1. Nothing in this file knows which arm is running; the
arms in `arms.py` all read the same economics, which is what makes the
protocol-parity claim checkable rather than asserted.

Accounting convention (PREREG §3): every dollar figure is **relative to the
Works' opening offer** (arm A, "SIGN IT"). So arm A's concession cost is exactly
zero by construction and every other arm is measured against it. Money is PV
over a 3-year horizon at 7%.

Double-counting note: `rho` (replacement cost as a multiple of salary) is the
all-in Gallup/SHRM figure and already contains vacancy and ramp. Vacancy days
are carried for narrative/time reporting only and never enter a dollar total.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

# --------------------------------------------------------------------- issues
ISSUES = ("base", "title", "bonus", "berth", "deepwater")
ISSUES_V3 = ("base", "title", "bonus", "berth", "deepwater", "pto")

BASE_PCT = (0.00, 0.03, 0.06, 0.09, 0.12)
BASE_LABELS = ("+0%", "+3%", "+6%", "+9%", "+12%")
BONUS_MO = (0.0, 1.0, 2.0)
BONUS_LABELS = ("none", "1 month", "2 months")
TITLE_LABELS = ("hold", "molt")          # molt = promote into a bigger shell
BERTH_LABELS = ("standard", "flexible")
DEEP_LABELS = ("no", "deepwater")
# AMENDMENT 2: the sixth issue. Expensive on the books, cheap at the margin.
PTO_DAYS = (0, 5, 10)
PTO_LABELS = ("+0 days", "+5 days", "+10 days")
WORK_DAYS = 260.0

HORIZON = 3
DISCOUNT = 0.07
PVF = sum(1.0 / (1.0 + DISCOUNT) ** t for t in range(HORIZON))   # 2.808...


@dataclass(frozen=True)
class Package:
    """A complete offer. Index into BASE_PCT / BONUS_MO plus three switches."""
    base: int = 0
    title: bool = False
    bonus: int = 0
    berth: bool = False
    deep: bool = False
    pto: int = 0            # AMENDMENT 2; defaults to 0 so v1/v2 are unchanged

    def key(self):
        return (self.base, self.title, self.bonus, self.berth, self.deep,
                self.pto)

    def labels(self):
        return {"base": BASE_LABELS[self.base],
                "title": TITLE_LABELS[1 if self.title else 0],
                "bonus": BONUS_LABELS[self.bonus],
                "berth": BERTH_LABELS[1 if self.berth else 0],
                "deepwater": DEEP_LABELS[1 if self.deep else 0],
                "pto": PTO_LABELS[self.pto]}


# ------------------------------------------------------------ specializations
@dataclass(frozen=True)
class Spec:
    name: str
    share: float
    salary_med: float
    rho: float            # replacement cost, multiple of salary (all-in)
    p_out: float          # base rate of an outside offer in a season
    vacancy_days: int     # reported, never priced (rho already contains it)
    berth_cost: float     # coverage cost of flexible berth, fraction of salary


SPECS = (
    Spec("HULL-WELDER",   0.30,  74_000, 0.45, 0.28, 34, 0.050),
    Spec("BRINE-CHEMIST", 0.22, 118_000, 0.80, 0.34, 52, 0.020),
    Spec("NAV-PILOT",     0.16, 146_000, 1.10, 0.46, 68, 0.030),
    Spec("CARGO-BROKER",  0.18, 102_000, 0.90, 0.42, 44, 0.010),
    Spec("SHELL-SMITH",   0.14, 158_000, 1.60, 0.24, 74, 0.020),
)


@dataclass(frozen=True)
class Params:
    # --- money
    peer_spill: float = 0.30      # a base raise leaks to band peers (sigma_peer)
    rho_mult: float = 1.0         # sweep multiplier on every rho
    dirichlet: float = 1.4        # crab priority dispersion
    title_drift: float = 0.02     # implied salary drift from a promotion
    title_admin: float = 0.03     # band-compression / backfill, fraction of S
    title_career: float = 0.09    # subjective career value to a typical crab
    berth_value: float = 0.06     # subjective value of a flexible berth
    deep_value: float = 0.07      # subjective value of a growth assignment
    deep_cost: float = 0.03       # net productivity cost to the Works
    attach: float = 0.02          # per-log-year station-specific attachment
    taste: float = 0.04           # logit scale on the leave decision (of S)
    p_exo: float = 0.06           # departures for reasons unrelated to comp

    # --- the clock (all zeroed in the zero-clock condition)
    meet_delay_med: float = 9.0
    meet_delay_sig: float = 0.55
    approval_days: float = 7.0
    approval_band_extra: float = 3.0
    mgr_hours: float = 1.5
    mgr_rate: float = 145.0
    distraction: float = 0.08
    hazard_day: float = 0.009
    hazard_offer_mult: float = 3.1
    clock: bool = True            # False -> zero-clock condition

    # --- discretion (identical in every arm)
    disc_base: int = 1            # manager may grant up to +3% alone
    disc_bonus: int = 1           # ... and up to 1 month
    # berth is always within discretion; title and deepwater never are

    # --- protocol
    max_meetings: int = 5
    max_rounds: int = 3
    their_batna_estimate: float = 0.45
    # The Works signs what is put in front of it only when countering would not
    # gain it more than this (fraction of salary). At 0 the Works always counters
    # with its own optimum, at 1 it signs anything weakly better than holding
    # firm. NOT pinned by PREREG; a HIGHER value is more generous to the engine
    # arms, so the sweep matters. See SPEC.md §3.
    counter_thresh: float = 0.005
    # EXPLORATORY (added after K6 fired; see RESULTS "Identification"): price
    # every currency to the Works at exactly what it is worth to an AVERAGE crab.
    # This removes the difference in relative prices BETWEEN THE TWO SIDES,
    # leaving only between-crab heterogeneity as a source of gains from trade.
    flat_prices: bool = False

    def spec_rho(self, s: Spec) -> float:
        return s.rho * self.rho_mult


# ------------------------------------------------------------------ the crabs
@dataclass
class Crab:
    cid: int
    spec: Spec
    salary: float
    perf: float
    tenure: int
    w: np.ndarray                 # priority weights over ISSUES, sums to 1
    move_cost: float              # dollars
    has_outside: bool
    omega: float                  # outside premium
    d_exp: float                  # days until the outside offer expires
    u_taste: float                # common random number: leave taste shock
    u_exo: float                  # common random number: exogenous departure
    u_haz: float                  # common random number: attrition-while-open
    delays: np.ndarray            # common random numbers: meeting delays


def draw_crab(cid: int, p: Params, rng: np.random.Generator) -> Crab:
    s = SPECS[int(rng.choice(len(SPECS), p=[x.share for x in SPECS]))]
    salary = float(s.salary_med * math.exp(rng.normal(0.0, 0.18)))
    perf = float(rng.random())
    tenure = int(1 + rng.geometric(0.30) - 1)
    tenure = max(1, min(tenure, 9))
    w = rng.dirichlet([p.dirichlet] * len(ISSUES))
    move_cost = float(salary / 12.0 * math.exp(math.log(0.9) + rng.normal(0, 0.6)))
    p_out = min(0.95, s.p_out * (0.55 + 0.9 * perf))
    has_outside = bool(rng.random() < p_out)
    omega = float(max(-0.02, rng.normal(0.12, 0.06)))
    d_exp = float(max(3.0, rng.normal(10.0, 4.0)))
    return Crab(cid=cid, spec=s, salary=salary, perf=perf, tenure=tenure, w=w,
                move_cost=move_cost, has_outside=has_outside, omega=omega,
                d_exp=d_exp, u_taste=float(rng.random()),
                u_exo=float(rng.random()), u_haz=float(rng.random()),
                delays=rng.lognormal(math.log(p.meet_delay_med),
                                     p.meet_delay_sig, size=8))


def weight_mult(c: Crab) -> dict:
    """Priority multipliers, normalised so an average crab has multiplier 1 on
    every issue. Cash is cash — the multipliers scale only the SUBJECTIVE part
    of each issue's value (PREREG §1.2)."""
    m = len(ISSUES) * c.w
    return {k: float(v) for k, v in zip(ISSUES, m)}


# ------------------------------------------------------------- crab valuation
def crab_value(p: Params, c: Crab, pk: Package) -> float:
    """PV in dollars of a package to this crab, relative to a package of
    nothing. Cash at face; subjective terms scaled by the crab's own weights."""
    S, m = c.salary, weight_mult(c)
    cash = S * BASE_PCT[pk.base] * PVF + S / 12.0 * BONUS_MO[pk.bonus]
    if pk.title:
        cash += S * p.title_drift * PVF
    subj = 0.0
    if pk.title:
        subj += m["title"] * p.title_career * S
    if pk.berth:
        subj += m["berth"] * p.berth_value * S
    if pk.deep:
        subj += m["deepwater"] * p.deep_value * S
    # a crab that weights base/bonus highly is simply money-hungry: cash already
    # carries that, so the money issues get no subjective bonus.
    return cash + subj


def crab_cash(p: Params, c: Crab, pk: Package) -> float:
    """The cash-only part — what shows up on a payslip. Used for the 'the Works
    paid more permanent salary' decomposition."""
    S = c.salary
    v = S * BASE_PCT[pk.base] * PVF + S / 12.0 * BONUS_MO[pk.bonus]
    if pk.title:
        v += S * p.title_drift * PVF
    return v


def outside_value(p: Params, c: Crab) -> float:
    """PV of leaving, in the same units as crab_value. Only meaningful when the
    crab actually holds an outside offer."""
    if not c.has_outside:
        return -1e9
    att = p.attach * math.log(1.0 + c.tenure) * c.salary
    return c.salary * c.omega * PVF - c.move_cost - att


# -------------------------------------------------------------- Works costings
def works_cost(p: Params, c: Crab, pk: Package) -> float:
    """PV cost to the Works of granting this package (relative to nothing)."""
    S = c.salary
    if p.flat_prices:
        # the ablation: the Works' price for each currency IS the average
        # crab's valuation of it, so no cross-side price difference remains
        cost = S * BASE_PCT[pk.base] * PVF + S / 12.0 * BONUS_MO[pk.bonus]
        if pk.title:
            cost += S * (p.title_drift * PVF + p.title_career)
        if pk.berth:
            cost += S * p.berth_value
        if pk.deep:
            cost += S * p.deep_value
        return cost
    cost = S * BASE_PCT[pk.base] * PVF * (1.0 + p.peer_spill)
    cost += S / 12.0 * BONUS_MO[pk.bonus]
    if pk.title:
        cost += S * p.title_drift * PVF + S * p.title_admin
    if pk.berth:
        cost += S * c.spec.berth_cost
    if pk.deep:
        cost += S * p.deep_cost
    return cost


def p_leave(p: Params, c: Crab, pk: Package, expired: bool = False) -> float:
    """Probability this crab leaves once the package is settled."""
    if not c.has_outside or expired:
        return p.p_exo
    gap = outside_value(p, c) - crab_value(p, c, pk)
    lam = 1.0 / (1.0 + math.exp(-gap / (p.taste * c.salary)))
    return p.p_exo + (1.0 - p.p_exo) * lam


def works_npv(p: Params, c: Crab, pk: Package, expired: bool = False) -> float:
    """The Works' payoff from settling on `pk`, before clock costs. Relative
    accounting: staying costs the package, leaving costs rho x salary."""
    pl = p_leave(p, c, pk, expired)
    return -(1.0 - pl) * works_cost(p, c, pk) - pl * p.spec_rho(c.spec) * c.salary


def opening_offer(p: Params, c: Crab) -> Package:
    """What the Works puts on the table unprompted: the merit matrix. Anchored on
    the ~3.7% budgeted increase most employers plan."""
    if c.perf < 0.35:
        return Package(base=0)
    if c.perf < 0.90:
        return Package(base=1)          # +3%
    return Package(base=2)              # +6% for the top decile


# ------------------------------------------------------------------ the clock
def needs_approval(p: Params, pk: Package, base_pkg: Package) -> tuple[bool, bool]:
    """(needs a hop, above-band). Anything past the manager's standing
    delegation goes up the ladder — in EVERY arm (PREREG §0 guard 2)."""
    hop = (pk.base > max(p.disc_base, base_pkg.base) or pk.bonus > p.disc_bonus
           or pk.title or pk.deep)
    above_band = pk.base >= 4 or (pk.title and pk.base >= 3)
    return hop, above_band


def approval_days(p: Params, pk: Package, base_pkg: Package) -> float:
    if not p.clock:
        return 0.0
    hop, above = needs_approval(p, pk, base_pkg)
    if not hop:
        return 0.0
    return p.approval_days + (p.approval_band_extra if above else 0.0)


def clock_costs(p: Params, c: Crab, days: float, meetings: int) -> dict:
    """Dollar cost of elapsed time and meetings, and the chance the crab walks
    out mid-negotiation. All zero in the zero-clock condition."""
    if not p.clock:
        return {"mgr": 0.0, "distraction": 0.0, "walked": False, "days": days}
    mgr = meetings * p.mgr_hours * p.mgr_rate
    distraction = p.distraction * (days / 365.0) * c.salary
    haz = p.hazard_day * (p.hazard_offer_mult if c.has_outside else 1.0)
    open_days = min(days, c.d_exp) if c.has_outside else days
    pw = 1.0 - math.exp(-haz * max(0.0, open_days))
    return {"mgr": mgr, "distraction": distraction,
            "walked": bool(c.u_haz < pw), "days": days}


def expired(p: Params, c: Crab, days: float) -> bool:
    """Did the crab's outside offer lapse before the talks concluded?"""
    return bool(p.clock and c.has_outside and days > c.d_exp)


# -------------------------------------------------------------- the Works' set
def works_packages(p: Params, base_pkg: Package) -> list[Package]:
    """Every package the Works is willing to put its name on. Identical in every
    arm — the Works' concession budget is not an arm-level free parameter."""
    out = []
    for b in range(0, 4):
        if b < base_pkg.base:
            continue
        for bo in range(0, 3):
            for t in (False, True):
                for be in (False, True):
                    for d in (False, True):
                        out.append(Package(b, t, bo, be, d))
    return out


def crab_packages() -> list[Package]:
    return [Package(b, t, bo, be, d)
            for b in range(5) for t in (False, True) for bo in range(3)
            for be in (False, True) for d in (False, True)]

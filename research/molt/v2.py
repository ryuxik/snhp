"""Molt Season v2 — the world under PREREG AMENDMENT 1.

Three changes from `world.py`, all of them answers to objections:

  A1.6  Each crab has a PRIVATE match value `mu` — what it is worth to *this*
        employer relative to a generic replacement of the same specialization.
        Drawn independently of the crab's market quality, so "what you are worth
        here" and "what you are worth outside" are finally different numbers.

  A1.7  The Works no longer observes the crab's outside offer. It holds a
        posterior and integrates over it. VERIFIABLE: the crab may disclose, and
        silence is itself informative. UNVERIFIABLE: anyone may claim, so in
        equilibrium the claim carries nothing and the Works acts on its prior.

  A1.2  The Works is now the Works.

Everything the two versions share — package grids, what a package is worth to a
crab, what it costs the employer — is imported from `world.py` unchanged, so v1
and v2 differ only where the amendment says they differ.

KNOWN REMAINING OMNISCIENCE, disclosed rather than quietly fixed: the Works still
knows the crab's *priorities* (`crab_value` is exact). Amendment 1 did not
register a fix for that, so it stays, and every v2 result should be read as "the
employer knows what you want, but not what you can get elsewhere."
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from molt.world import (BASE_PCT, BONUS_MO, ISSUES, PVF, SPECS, Crab, Package,
                        Params, Spec, crab_value, weight_mult, works_cost)

# the Works' cost function is the Works', unrenamed at the import boundary so
# the two versions stay bit-comparable; everything user-facing says "Works".

OMEGA_GRID = np.round(np.linspace(-0.02, 0.36, 25), 4)


@dataclass(frozen=True)
class Params2(Params):
    # --- A1.6 private match value
    match_sigma: float = 0.35        # lognormal sigma; mean of mu is 1 by construction
    perf_q_load: float = 0.70        # how much of observed performance is market quality
    omega_q_load: float = 0.04       # market quality -> outside premium

    # --- A1.5 the clock, rebuilt as real human timelines
    email_med: float = 3.0           # days per email round trip (2-5)
    email_sig: float = 0.35
    meeting_med: float = 9.0         # the one meeting that locks it down (7-12)
    meeting_sig: float = 0.20
    exchange_budget: int = 12        # total exchanges across the whole slow talk

    # --- A1.7 credibility regime
    credibility: str = "verifiable"  # or "unverifiable"
    disclose_tau: float = 0.10       # solved by fixed point; see solve_tau()


@dataclass
class Crab2(Crab):
    match: float = 1.0               # PRIVATE to the Works
    quality: float = 0.0             # drives the outside offer, not the match
    discloses: bool = False


def draw_crab2(cid: int, p: Params2, rng: np.random.Generator) -> Crab2:
    s = SPECS[int(rng.choice(len(SPECS), p=[x.share for x in SPECS]))]
    salary = float(s.salary_med * math.exp(rng.normal(0.0, 0.18)))
    # market quality q; observed performance is a NOISY PROXY for it, so the
    # Works learns something from perf but not everything
    q = float(rng.normal(0.0, 1.0))
    noise = float(rng.normal(0.0, 1.0))
    x = p.perf_q_load * q + math.sqrt(max(1e-9, 1 - p.perf_q_load ** 2)) * noise
    perf = float(0.5 * (1.0 + math.erf(x / math.sqrt(2.0))))
    tenure = max(1, min(int(1 + rng.geometric(0.30) - 1), 9))
    w = rng.dirichlet([p.dirichlet] * len(ISSUES))
    move_cost = float(salary / 12.0 * math.exp(math.log(0.9) + rng.normal(0, 0.6)))
    p_out = min(0.95, s.p_out * (0.55 + 0.9 * perf))
    has_outside = bool(rng.random() < p_out)
    omega = float(max(-0.02, rng.normal(0.12 + p.omega_q_load * q, 0.06)))
    d_exp = float(max(3.0, rng.normal(10.0, 4.0)))
    # A1.6: firm-specific human capital, INDEPENDENT of market quality
    match = float(math.exp(rng.normal(0.0, p.match_sigma) - 0.5 * p.match_sigma ** 2))
    return Crab2(
        cid=cid, spec=s, salary=salary, perf=perf, tenure=tenure, w=w,
        move_cost=move_cost, has_outside=has_outside, omega=omega, d_exp=d_exp,
        u_taste=float(rng.random()), u_exo=float(rng.random()),
        u_haz=float(rng.random()),
        delays=rng.lognormal(math.log(p.email_med), p.email_sig, size=16),
        match=match, quality=q)


def replacement_cost(p: Params2, c: Crab2) -> float:
    """A1.6: losing a high-match crab costs more, because what replaces it is a
    generic hire. Mean of `match` is 1, so the population stays anchored on the
    published 0.5-2x salary range."""
    return p.spec_rho(c.spec) * c.salary * c.match


def outside_value_at(p: Params2, c: Crab2, omega: float) -> float:
    """PV of leaving for an offer at premium `omega`. Same form as v1; exposed as
    a function of omega so the Works can integrate over its belief."""
    att = p.attach * math.log(1.0 + c.tenure) * c.salary
    return c.salary * omega * PVF - c.move_cost - att


def outside_value(p: Params2, c: Crab2) -> float:
    return outside_value_at(p, c, c.omega) if c.has_outside else -1e9


def p_leave_true(p: Params2, c: Crab2, pk: Package, expired: bool = False) -> float:
    """What ACTUALLY happens. Uses the crab's real offer, which the Works cannot
    see. This is the ground truth the Works is trying to estimate."""
    if not c.has_outside or expired:
        return p.p_exo
    gap = outside_value(p, c) - crab_value(p, c, pk)
    return p.p_exo + (1.0 - p.p_exo) / (1.0 + math.exp(-gap / (p.taste * c.salary)))


# ---------------------------------------------------------------- the belief
class Belief:
    """The Works' posterior over the crab's outside option: a probability that
    one exists at all, and a distribution over how good it is."""
    __slots__ = ("p_has", "grid", "w")

    def __init__(self, p_has: float, grid: np.ndarray, w: np.ndarray):
        self.p_has = float(np.clip(p_has, 0.0, 1.0))
        self.grid = grid
        s = float(w.sum())
        self.w = w / s if s > 1e-12 else np.ones_like(w) / len(w)

    def mean_omega(self) -> float:
        return float((self.grid * self.w).sum())


def prior(p: Params2, c: Crab2) -> Belief:
    """What the Works believes before anyone speaks. It observes specialization,
    salary, tenure and performance — and knows the population rules that generate
    outside offers from them. It does not observe q, omega, or whether an offer
    exists."""
    p_has = min(0.95, c.spec.p_out * (0.55 + 0.9 * c.perf))
    # invert the noisy proxy: E[q | perf]
    x = _probit(c.perf)
    q_hat = p.perf_q_load * x
    q_sd = math.sqrt(max(1e-6, 1.0 - p.perf_q_load ** 2))
    mu = 0.12 + p.omega_q_load * q_hat
    sd = math.sqrt(0.06 ** 2 + (p.omega_q_load * q_sd) ** 2)
    w = np.exp(-0.5 * ((OMEGA_GRID - mu) / sd) ** 2)
    return Belief(p_has, OMEGA_GRID, w)


def _probit(u: float) -> float:
    u = min(max(u, 1e-6), 1 - 1e-6)
    # Acklam-style inverse normal, enough precision for a belief grid
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if u < pl:
        q = math.sqrt(-2 * math.log(u))
        return (((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if u > ph:
        q = math.sqrt(-2 * math.log(1 - u))
        return -(((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = u - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def update(p: Params2, c: Crab2, bel: Belief, spoke: bool) -> Belief:
    """A1.7. What the Works believes after the crab has (or has not) raised an
    outside offer."""
    if p.credibility == "unverifiable":
        # Claiming is free, so every crab claims and the claim separates nobody:
        # the posterior after a claim IS the prior. This is the unravelling
        # result, DERIVED here rather than assumed as it was in v1.
        return bel
    if spoke:
        # a forwarded letter: the number is now known
        i = int(np.argmin(np.abs(bel.grid - c.omega)))
        w = np.zeros_like(bel.w)
        w[i] = 1.0
        return Belief(1.0, bel.grid, w)
    # silence. Either there is no offer, or there is one too weak to be worth
    # showing. Bayes on both.
    below = bel.grid < p.disclose_tau
    mass_weak = float(bel.w[below].sum())
    p_has_post = bel.p_has * mass_weak / (bel.p_has * mass_weak + (1.0 - bel.p_has))
    w = bel.w * below
    if w.sum() < 1e-12:
        w = np.ones_like(bel.w) * (bel.grid < p.disclose_tau + 1e-9)
        if w.sum() < 1e-12:
            w = np.ones_like(bel.w)
    return Belief(p_has_post, bel.grid, w)


def p_leave_belief(p: Params2, c: Crab2, bel: Belief, pk: Package) -> float:
    """The Works' estimate of the chance it loses this crab, integrated over what
    it actually believes."""
    v = crab_value(p, c, pk)
    gaps = np.array([outside_value_at(p, c, om) - v for om in bel.grid])
    lam = 1.0 / (1.0 + np.exp(-gaps / (p.taste * c.salary)))
    exp_lam = float((bel.w * lam).sum())
    return p.p_exo + (1.0 - p.p_exo) * bel.p_has * exp_lam


def works_npv(p: Params2, c: Crab2, bel: Belief, pk: Package) -> float:
    """What the Works thinks a package is worth to it. Decisions are made on the
    belief; the world then resolves on the truth."""
    pl = p_leave_belief(p, c, bel, pk)
    return -(1.0 - pl) * works_cost(p, c, pk) - pl * replacement_cost(p, c)


def works_packages(p: Params2, base_pkg: Package) -> list[Package]:
    from molt.world import works_packages
    return works_packages(p, base_pkg)


def works_best_reply(p: Params2, c: Crab2, bel: Belief, base_pkg: Package,
                     floor_value: float) -> Package | None:
    best, best_v = None, works_npv(p, c, bel, base_pkg)
    for pk in works_packages(p, base_pkg):
        if crab_value(p, c, pk) <= floor_value + 1e-9:
            continue
        v = works_npv(p, c, bel, pk)
        if v > best_v:
            best, best_v = pk, v
    return best


def works_signs(p: Params2, c: Crab2, bel: Belief, ask: Package, cur: Package,
                reply: Package | None) -> bool:
    if works_npv(p, c, bel, ask) < works_npv(p, c, bel, cur):
        return False
    if reply is None:
        return True
    return works_npv(p, c, bel, reply) - works_npv(p, c, bel, ask) \
        <= p.counter_thresh * c.salary


# ------------------------------------------------------- disclosure threshold
def _best_package_under(p: Params2, c: Crab2, bel: Belief) -> Package:
    """The package the Works would settle on given a belief, holding the protocol
    fixed. Used only to decide whether disclosing is worth it."""
    from molt.world import opening_offer
    op = opening_offer(p, c)
    r = works_best_reply(p, c, bel, op, crab_value(p, c, op))
    return r if r is not None else op


def discloses(p: Params2, c: Crab2) -> bool:
    """Does this crab show the letter? Only meaningful when VERIFIABLE."""
    if not c.has_outside or p.credibility != "verifiable":
        return False
    bel = prior(p, c)
    loud = crab_value(p, c, _best_package_under(p, c, update(p, c, bel, True)))
    quiet = crab_value(p, c, _best_package_under(p, c, update(p, c, bel, False)))
    return loud > quiet + 1e-9


def solve_tau(p: Params2, seeds=range(9100, 9120), n=40, iters=2) -> float:
    """A1.7 fixed point: the disclosure threshold the Works assumes must be the
    one crabs actually use. Solved on dedicated pilot seeds, never on the seeds
    the results are read from."""
    tau = p.disclose_tau
    for _ in range(iters):
        p = Params2(**{**p.__dict__, "disclose_tau": tau})
        shown = []
        for seed in seeds:
            rng = np.random.default_rng(seed)
            for i in range(n):
                c = draw_crab2(i, p, rng)
                if c.has_outside and discloses(p, c):
                    shown.append(c.omega)
        tau = float(np.percentile(shown, 5)) if shown else tau
    return tau

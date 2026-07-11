"""preflearn — the CONSUMER-side core: onboarding + online preference learning
that recovers a buyer's utility well enough to run a PROFITABLE silent
negotiation, sharpened by an explicit consideration-set (cart) signal.

This is the honest backbone for a fundraising demo. It sits ON TOP of the two
existing subsystems (nothing here reimplements them):

  * the WTP population  — `buyer.world.draw_vend_population`, i.e.
    `vend.world.sample_consumer`: per-SKU first-unit WTP drawn lognormal around
    `WTP_MU[sku]` with `WTP_SIGMA = 0.30`, hour/day multipliers folded in. We
    NEVER invent a population; the true buyers are vend's true demand process.
  * the negotiation     — `vend.scenario.nash_quote` via the `VendMerchant`
    adapter. We feed a DISCLOSED wtp estimate into `merchant.quote(...)` exactly
    as any honest disclosure would flow; discount-only (floor..list) is enforced
    by the engine, not by us.

The learner touches the buyer's TRUE utility only through elicited ANSWERS and
observed CHOICES — never the true wtp vector. That separation is structural
(the true wtp lives on `TrueBuyer`; `PosteriorLearner` only ingests answers) and
is asserted in tests (`test_no_ground_truth_leak`). The buyer's WTP/curve stay
on the buyer's side; only the negotiation runs on the estimate.

Utility model (shared with vend, verbatim):
    bundle_value(wtp, sku, q) = wtp[sku] * sum_{i<q} QTY_DECAY**i
with QTY_DECAY = 0.55, QTY_CAP = 3. We learn the per-SKU first-unit WTP vector;
the decay is the known structural constant.

Posterior representation: a per-SKU grid over log-WTP (a factorized / mean-field
Gaussian-mixture posterior). Exact and degeneracy-free for the per-SKU signals
(WTP probes, accept/reject on a single-SKU quote); cross-SKU pairwise queries
use a mean-field update (each SKU updated holding the other at its posterior
mean). Stated honestly; most information is per-SKU and exact.

The headline metric is SURPLUS CAPTURE: realized surplus of the LEARNED-curve
agent as a fraction between the NO-INFO population-prior agent (0) and the
FULL-INFO oracle (1). Joint (efficiency) surplus is the robust primary; buyer
surplus is the consumer-facing secondary (with the honest caveat that, because
the merchant prices AGAINST the disclosure, honest-true disclosure is a FAIR —
not a strict per-buyer maximal — reference: strategic under-disclosure can beat
it, so buyer-surplus capture can exceed 1 or have a negative denominator for
above-population-mean buyers; we report the aggregate ratio-of-sums, robust to
this, and flag it).
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field

import numpy as np

from buyer.merchant import Disclosure, Intent, VendMerchant
from buyer.stats import mean_ci
from buyer.values import (QTY_CAP, QTY_DECAY, best_bundle, bundle_surplus,
                          bundle_value)
from buyer.world import BuyerDraw, draw_vend_population

# ── defaults (all overridable) ──────────────────────────────────────────────
TEST_SEED = 20260710
CAL_SEED = 777          # the prior is fit on a DISJOINT population (no leak)
GRID_N = 65             # log-WTP grid points per SKU
GRID_SPAN = 4.5         # +/- sigmas of prior the grid spans
K_CART = 3              # consideration-set size
# answer-noise temperatures ($ scale); the buyer is imprecise, not omniscient.
PROBE_TAU_FRAC = 0.08   # WTP-probe logistic width, as a fraction of the price
ACCEPT_TAU = 0.15       # accept/reject logistic width on the surplus margin ($)
PW_TAU = 0.15           # pairwise-choice logistic width on surplus diffs ($)
N_GRID = (0, 3, 5, 10, 20)     # onboarding-budget sweep
M_GRID = (0, 3, 10)            # online-interaction sweep


def _decay_sum(q: int) -> float:
    return sum(QTY_DECAY ** i for i in range(q))


_DECAY = {q: _decay_sum(q) for q in range(1, QTY_CAP + 1)}


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


# ── population prior (fit on a DISJOINT calibration population) ──────────────

@dataclass
class PopPrior:
    """Per-SKU log-WTP grids + prior weights, fit from a population the test
    buyer is NOT part of. This is legitimate population knowledge (the platform
    has seen many past buyers); the current buyer is new, so no ground truth of
    the test buyer enters the prior."""
    skus: list[str]
    grid_v: dict[str, np.ndarray]      # WTP values at each grid node
    grid_lw: dict[str, np.ndarray]     # log of the above
    prior_w: dict[str, np.ndarray]     # prior weight per node (sums to 1)
    mu_log: dict[str, float]
    sigma_log: dict[str, float]

    @classmethod
    def build(cls, cal_seed: int = CAL_SEED, n: int = 4000, *, cfg=None,
              grid_n: int = GRID_N, span: float = GRID_SPAN) -> "PopPrior":
        pop = draw_vend_population(cal_seed, n, cfg=cfg)
        skus = sorted(pop[0].wtp)
        grid_v, grid_lw, prior_w, mu_log, sigma_log = {}, {}, {}, {}, {}
        for s in skus:
            lw = np.array([math.log(b.wtp[s]) for b in pop])
            mu, sg = float(lw.mean()), float(lw.std(ddof=1))
            lo, hi = mu - span * sg, mu + span * sg
            g = np.linspace(lo, hi, grid_n)
            w = np.exp(-0.5 * ((g - mu) / sg) ** 2)
            w /= w.sum()
            grid_lw[s], grid_v[s], prior_w[s] = g, np.exp(g), w
            mu_log[s], sigma_log[s] = mu, sg
        return cls(skus, grid_v, grid_lw, prior_w, mu_log, sigma_log)


# ── the posterior learner (answers/choices in, estimate out — no true wtp) ───

class PosteriorLearner:
    """Factorized (per-SKU) grid posterior over first-unit WTP. Ingests ONLY
    elicited answers and observed choices; it has no access to the true wtp."""

    def __init__(self, prior: PopPrior):
        self.prior = prior
        self.skus = prior.skus
        self.w = {s: prior.prior_w[s].copy() for s in self.skus}

    def copy(self) -> "PosteriorLearner":
        c = PosteriorLearner.__new__(PosteriorLearner)
        c.prior, c.skus = self.prior, self.skus
        c.w = {s: self.w[s].copy() for s in self.skus}
        return c

    # ── point estimates / uncertainty ──
    def mean(self) -> dict[str, float]:
        return {s: float(self.w[s] @ self.prior.grid_v[s]) for s in self.skus}

    def quantile(self, sku: str, q: float) -> float:
        cw = np.cumsum(self.w[sku])
        return float(np.interp(q, cw, self.prior.grid_v[sku]))

    def rel_var(self, sku: str) -> float:
        v, w = self.prior.grid_v[sku], self.w[sku]
        m = float(w @ v)
        if m <= 1e-9:
            return 0.0
        return float(w @ (v - m) ** 2) / (m * m)

    # ── likelihood updates ──
    def _apply(self, sku: str, like: np.ndarray) -> None:
        nw = self.w[sku] * like
        z = nw.sum()
        if z > 1e-300:
            self.w[sku] = nw / z

    def update_probe(self, sku: str, price: float, yes: bool,
                     tau: float | None = None) -> None:
        v = self.prior.grid_v[sku]
        tau = tau if tau is not None else max(0.05, PROBE_TAU_FRAC * price)
        pyes = _sig((v - price) / tau)
        self._apply(sku, pyes if yes else (1.0 - pyes))

    def update_accept(self, sku: str, qty: int, unit_price: float,
                      accepted: bool, fallback: float, friction: float = 0.0,
                      tau: float = ACCEPT_TAU) -> None:
        v = self.prior.grid_v[sku]
        surplus = v * _DECAY[qty] - qty * unit_price - friction
        pacc = _sig((surplus - fallback) / tau)
        self._apply(sku, pacc if accepted else (1.0 - pacc))

    def update_choice_from_set(self, considered: list[str],
                               prices: dict[str, float], chosen: str,
                               means: dict[str, float], tau: float = PW_TAU
                               ) -> None:
        """Online signal: the buyer picks ONE item from the consideration set at
        the board (or walks). A pick reveals RELATIVE value (chosen surplus >
        the rest) — a two-sided, unbiased signal, unlike accept/reject on an
        always-beneficial quote. Mean-field: update each considered SKU with the
        others held at their posterior-mean surplus. `chosen` is a sku or
        'walk'. Single-unit consideration (qty=1)."""
        opts = list(considered) + ["walk"]
        base = {s: means[s] - prices[s] for s in considered}
        base["walk"] = 0.0
        cidx = opts.index(chosen)
        for s in considered:
            v = self.prior.grid_v[s]
            rows = []
            for o in opts:
                if o == s:
                    rows.append(v - prices[s])            # varied SKU
                else:
                    rows.append(np.full_like(v, base[o]))  # held at mean
            U = np.stack(rows) / tau
            ex = np.exp(U - U.max(axis=0))
            probs = ex / ex.sum(axis=0)
            self._apply(s, probs[cidx])

    def update_pairwise(self, A, B, choice: str, means: dict[str, float],
                        tau: float = PW_TAU) -> None:
        """A, B = (sku, qty, price). Mean-field: update each involved SKU with
        the other bundle's surplus held at the posterior mean. choice in
        {'A','B','walk'}."""
        (sa, qa, pa), (sb, qb, pb) = A, B
        s_a_mean = means[sa] * _DECAY[qa] - qa * pa
        s_b_mean = means[sb] * _DECAY[qb] - qb * pb
        idx = {"A": 0, "B": 1, "walk": 2}[choice]
        # SKU sa: bundle A varies over the grid, B held at its posterior mean.
        # SKU sb: bundle B varies over the grid, A held at its posterior mean.
        for slot, (sku, qty, price) in ((0, A), (1, B)):
            v = self.prior.grid_v[sku]
            s_this = v * _DECAY[qty] - qty * price
            uA = s_this if slot == 0 else np.full_like(v, s_a_mean)
            uB = s_this if slot == 1 else np.full_like(v, s_b_mean)
            uW = np.zeros_like(v)
            U = np.stack([uA, uB, uW]) / tau
            ex = np.exp(U - U.max(axis=0))
            probs = ex / ex.sum(axis=0)
            self._apply(sku, probs[idx])


# ── the buyer's true self (the ONLY holder of true wtp) ─────────────────────

@dataclass
class TrueBuyer:
    uid: int
    wtp: dict[str, float]
    walk_cost: float
    noise_mult: float = 1.0
    _rng: np.random.Generator = field(default=None, repr=False)

    def __post_init__(self):
        if self._rng is None:
            self._rng = np.random.default_rng((self.uid * 2654435761) & 0x7FFFFFFF)

    def answer_probe(self, sku: str, price: float) -> bool:
        tau = self.noise_mult * max(0.05, PROBE_TAU_FRAC * price)
        p_yes = 1.0 / (1.0 + math.exp(-(self.wtp[sku] - price) / tau))
        return bool(self._rng.random() < p_yes)

    def pick_from_set(self, considered: list[str], prices: dict[str, float]
                      ) -> str:
        """Pick the max-true-surplus item from the consideration set at the
        board, or 'walk' if none is worth it. Softmax choice noise. This is the
        online 'real shopping choice' the learner ingests."""
        opts = list(considered) + ["walk"]
        u = np.array([self.wtp[s] - prices[s] for s in considered] + [0.0])
        u = u / (self.noise_mult * PW_TAU)
        p = np.exp(u - u.max())
        p /= p.sum()
        return str(self._rng.choice(opts, p=p))

    def answer_pairwise(self, A, B) -> str:
        (sa, qa, pa), (sb, qb, pb) = A, B
        uA = bundle_value(self.wtp, sa, qa) - qa * pa
        uB = bundle_value(self.wtp, sb, qb) - qb * pb
        tau = self.noise_mult * PW_TAU
        u = np.array([uA, uB, 0.0]) / tau
        p = np.exp(u - u.max())
        p /= p.sum()
        return str(self._rng.choice(["A", "B", "walk"], p=p))

    def true_surplus(self, sku, qty, unit_price) -> float:
        return bundle_surplus(self.wtp, sku, qty, unit_price)


# ── environment: eval + online merchants (built ONCE, reused) ───────────────

def _merchant(seed: int, day: int, tick: int, mid: str) -> VendMerchant:
    return VendMerchant.from_vend(mid, seed=seed, day=day, tick=tick)


def _consideration_set(true_wtp, merchant: VendMerchant, k: int) -> list[str]:
    """The K SKUs the buyer is 'considering right now' = the K with the highest
    true single-unit surplus at the board (the goods they'd actually shop)."""
    board = merchant.board()
    scored = [(s, true_wtp[s] - bi.list_price)
              for s, bi in board.items() if bi.stock > 0]
    scored.sort(key=lambda t: t[1], reverse=True)
    if not scored:
        return list(board)[:k]
    return [s for s, _ in scored[:k]]


def _fallback_true(true_wtp, walk, merchant, allowed) -> float:
    board = merchant.board()
    prices = {s: b.list_price for s, b in board.items() if s in allowed}
    stock = {s: b.stock for s, b in board.items() if s in allowed}
    _, _, s_stk = best_bundle(true_wtp, prices, stock)
    op = merchant.outside_prices()
    _, _, s_out = best_bundle(true_wtp, {s: op[s] for s in allowed})
    s_out = max(0.0, s_out - walk)
    return max(0.0, s_stk, s_out)


def _sticker_joint(true_wtp, merchant, allowed) -> float:
    board = merchant.board()
    prices = {s: b.list_price for s, b in board.items() if s in allowed}
    stock = {s: b.stock for s, b in board.items() if s in allowed}
    sku, qty, s = best_bundle(true_wtp, prices, stock)
    if sku is None:
        return 0.0
    return bundle_value(true_wtp, sku, qty) - qty * merchant.salvage_floor(sku)


def negotiate_realized(true_wtp, walk, merchant, wtp_hat, allowed) -> dict:
    """Run the EXISTING negotiation on the disclosed estimate; the buyer accepts
    iff the true surplus beats its walk-away. Returns realized buyer surplus,
    realized joint (efficiency) welfare, and whether a deal was struck."""
    intent = (Intent(allowed=frozenset(allowed))
              if allowed is not None else Intent())
    q = merchant.quote(Disclosure(wtp=dict(wtp_hat), walk_cost=walk), intent)
    A = allowed if allowed is not None else list(merchant.board())
    fb = _fallback_true(true_wtp, walk, merchant, A)
    if q is None:
        return dict(buyer=fb, joint=_sticker_joint(true_wtp, merchant, A),
                    accepted=False, saved=0.0, unit_price=None, list_price=None)
    ts = bundle_surplus(true_wtp, q.sku, q.qty, q.unit_price)
    if ts > fb:
        joint = bundle_value(true_wtp, q.sku, q.qty) - q.qty * q.salvage_floor
        return dict(buyer=ts, joint=joint, accepted=True, saved=ts - fb,
                    unit_price=q.unit_price, list_price=q.list_price)
    return dict(buyer=fb, joint=_sticker_joint(true_wtp, merchant, A),
                accepted=False, saved=0.0, unit_price=q.unit_price,
                list_price=q.list_price)


# ── active elicitation (expected relative-variance reduction) ───────────────

def _probe_gain(learner: PosteriorLearner, sku: str, price: float) -> float:
    v, w = learner.prior.grid_v[sku], learner.w[sku]
    tau = max(0.05, PROBE_TAU_FRAC * price)
    pyes_grid = _sig((v - price) / tau)
    pyes = float(w @ pyes_grid)
    if pyes < 1e-4 or pyes > 1 - 1e-4:
        return 0.0
    m0 = float(w @ v)
    v0 = float(w @ (v - m0) ** 2) / (m0 * m0 + 1e-12)
    wy = w * pyes_grid
    wy /= wy.sum()
    my = float(wy @ v)
    vy = float(wy @ (v - my) ** 2) / (my * my + 1e-12)
    wn = w * (1 - pyes_grid)
    wn /= wn.sum()
    mn = float(wn @ v)
    vn = float(wn @ (v - mn) ** 2) / (mn * mn + 1e-12)
    return v0 - (pyes * vy + (1 - pyes) * vn)


def _pair_gain(learner: PosteriorLearner, A, B, means) -> float:
    """Info gain of a pairwise query ≈ summed expected rel-var reduction over
    the two involved SKUs (each via the mean-field marginal choice model)."""
    (sa, qa, pa), (sb, qb, pb) = A, B
    total = 0.0
    for (sku, qty, price), other in ((A, means[sb] * _DECAY[qb] - qb * pb),
                                     (B, means[sa] * _DECAY[qa] - qa * pa)):
        v, w = learner.prior.grid_v[sku], learner.w[sku]
        s_this = v * _DECAY[qty] - qty * price
        u = np.stack([s_this, np.full_like(v, other), np.zeros_like(v)]) / PW_TAU
        p = np.exp(u - u.max(axis=0))
        p /= p.sum(axis=0)          # P(choice | v): rows A(this)/B(other)/walk
        m0 = float(w @ v)
        v0 = float(w @ (v - m0) ** 2) / (m0 * m0 + 1e-12)
        exp_v = 0.0
        for r in range(3):
            pr = float(w @ p[r])
            if pr < 1e-4:
                continue
            wr = w * p[r]
            wr /= wr.sum()
            mr = float(wr @ v)
            exp_v += pr * float(wr @ (v - mr) ** 2) / (mr * mr + 1e-12)
        total += v0 - exp_v
    return total


def select_and_ask(learner: PosteriorLearner, buyer: TrueBuyer,
                   target: list[str]) -> None:
    """Pick the most-informative query over `target` (expected rel-var
    reduction), ask the buyer, and update the posterior. Candidate pool = one
    median-price WTP probe per target SKU + a pairwise between the two
    highest-mean targets (the negotiation-relevant 'which SKU wins')."""
    means = learner.mean()
    best, best_gain, best_kind = None, -1.0, None
    for s in target:
        p = learner.quantile(s, 0.5)
        g = _probe_gain(learner, s, p)
        if g > best_gain:
            best, best_gain, best_kind = ("probe", s, p), g, "probe"
    if len(target) >= 2:
        tt = sorted(target, key=lambda s: means[s], reverse=True)[:2]
        s1, s2 = tt
        A = (s1, 1, learner.quantile(s1, 0.5))
        B = (s2, 1, learner.quantile(s2, 0.5))
        g = _pair_gain(learner, A, B, means)
        if g > best_gain:
            best, best_gain, best_kind = ("pair", A, B), g, "pair"
    if best is None:
        return
    if best_kind == "probe":
        _, s, p = best
        yes = buyer.answer_probe(s, p)
        learner.update_probe(s, p, yes)
    else:
        _, A, B = best
        ch = buyer.answer_pairwise(A, B)
        learner.update_pairwise(A, B, ch, means)


# ── one buyer's full trajectory (onboarding → snapshots → online → eval) ────

def _curve_err(mean_hat, true_wtp, skus) -> float:
    """Mean relative L1 error of the estimate over `skus` (measurement only —
    uses true wtp to GRADE, never to learn)."""
    return float(np.mean([abs(mean_hat[s] - true_wtp[s]) / true_wtp[s]
                          for s in skus]))


def run_buyer(draw: BuyerDraw, prior: PopPrior, eval_m: VendMerchant,
              online_ms: list[VendMerchant], *, cart: bool, k: int = K_CART,
              noise_mult: float = 1.0, drift_sigma: float = 0.0,
              online_inflate: float = 0.0,
              n_grid=N_GRID, m_grid=M_GRID) -> dict:
    """Returns nested per-(N,M) realized surpluses for learned/oracle/noinfo,
    plus curve-error snapshots. `cart` toggles the consideration-set signal
    (local target + Intent restriction)."""
    buyer = TrueBuyer(draw.uid, dict(draw.wtp), draw.walk_cost,
                      noise_mult=noise_mult)
    C = _consideration_set(draw.wtp, eval_m, k)
    allowed = C if cart else None
    target = C if cart else prior.skus
    grade_skus = C                      # grade the curve where it's used

    # oracle (true wtp) and no-info (prior mean) references on the eval board
    prior_mean = {s: float(prior.prior_w[s] @ prior.grid_v[s]) for s in prior.skus}
    oracle = negotiate_realized(draw.wtp, draw.walk_cost, eval_m, draw.wtp, allowed)
    noinfo = negotiate_realized(draw.wtp, draw.walk_cost, eval_m, prior_mean, allowed)

    learner = PosteriorLearner(prior)
    snaps: dict[int, PosteriorLearner] = {0: learner.copy()}
    max_n = max(n_grid)
    for step in range(max_n):
        select_and_ask(learner, buyer, target)
        if (step + 1) in n_grid:
            snaps[step + 1] = learner.copy()

    out = {"cart": cart, "uid": draw.uid,
           "oracle": oracle, "noinfo": noinfo, "C": C,
           "cells": {}, "oracle_cell": {}, "noinfo_cell": {}, "curve_err": {}}
    max_m = max(m_grid)
    for N in n_grid:
        base = snaps[N]
        out["curve_err"][N] = _curve_err(base.mean(), draw.wtp, grade_skus)
        lc = base.copy()
        drift_wtp = dict(draw.wtp)
        for M in range(max_m + 1):
            if M in m_grid:
                mean_hat = lc.mean()
                # references are recomputed against the CURRENT truth so drift
                # (non-stationary taste) is graded against a matched oracle.
                if drift_sigma > 0:
                    orc = negotiate_realized(drift_wtp, draw.walk_cost, eval_m,
                                             drift_wtp, allowed)
                    nin = negotiate_realized(drift_wtp, draw.walk_cost, eval_m,
                                             prior_mean, allowed)
                else:
                    orc, nin = oracle, noinfo
                r = negotiate_realized(drift_wtp, draw.walk_cost, eval_m,
                                       mean_hat, allowed)
                out["cells"][(N, M)] = r
                out["oracle_cell"][(N, M)] = orc
                out["noinfo_cell"][(N, M)] = nin
            # one online interaction (varying context). The buyer shops: it
            # picks from its consideration set at the board (an unbiased, two-
            # sided shopping CHOICE — the learner's main online signal) and,
            # secondarily, accepts/declines the negotiated quote.
            if M < max_m:
                om = online_ms[M % len(online_ms)]
                if drift_sigma > 0:
                    g = buyer._rng.normal(0.0, drift_sigma, size=len(prior.skus))
                    drift_wtp = {s: max(0.05, drift_wtp[s] * math.exp(gi))
                                 for s, gi in zip(prior.skus, g)}
                    buyer.wtp = drift_wtp
                if online_inflate > 0:      # widen posterior to track drift
                    for s in prior.skus:
                        lc.w[s] = _inflate(lc.w[s], online_inflate)
                oc = C if cart else prior.skus       # what the buyer shops over
                board = om.board()
                prices = {s: board[s].list_price for s in oc if s in board}
                chosen = buyer.pick_from_set(list(prices), prices)
                lc.update_choice_from_set(list(prices), prices, chosen,
                                          lc.mean(), tau=noise_mult * PW_TAU)
    return out


def _inflate(w: np.ndarray, alpha: float) -> np.ndarray:
    """Blend the posterior toward uniform by `alpha` — a forgetting factor that
    lets online updates track a drifting preference instead of locking in."""
    u = np.full_like(w, 1.0 / len(w))
    nw = (1 - alpha) * w + alpha * u
    return nw / nw.sum()


# ── aggregation: surplus capture with paired-bootstrap CIs ──────────────────

def _ratio_ci(nums, dens, *, seed=0, B=2000) -> dict:
    """Ratio-of-sums Σnum/Σden with a paired bootstrap over buyers. This is the
    fundable 'fraction of oracle surplus captured'."""
    nums, dens = np.asarray(nums), np.asarray(dens)
    D = float(dens.sum())
    ratio = float(nums.sum() / D) if abs(D) > 1e-9 else float("nan")
    rng = np.random.default_rng(seed)
    n = len(nums)
    boot = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        d = float(dens[idx].sum())
        if abs(d) > 1e-9:
            boot.append(float(nums[idx].sum()) / d)
    boot = np.sort(boot)
    ci = ([round(float(np.percentile(boot, 2.5)), 4),
           round(float(np.percentile(boot, 97.5)), 4)] if len(boot) > 10 else None)
    return {"capture": round(ratio, 4), "ci95": ci, "n": n,
            "num_sum": round(float(nums.sum()), 3),
            "den_sum": round(D, 3)}


def _capture_table(results: list[dict], key: str, n_grid, m_grid) -> dict:
    """Per-(N,M) capture for metric `key` ('buyer'|'joint'), ratio-of-sums."""
    tab = {}
    for N in n_grid:
        for M in m_grid:
            nums, dens = [], []
            for r in results:
                orc = r["oracle_cell"][(N, M)][key]
                nin = r["noinfo_cell"][(N, M)][key]
                lrn = r["cells"][(N, M)][key]
                nums.append(lrn - nin)
                dens.append(orc - nin)
            tab[f"N{N}_M{M}"] = _ratio_ci(nums, dens, seed=N * 100 + M)
    return tab


def _profitability(results: list[dict], n_grid, m_grid) -> dict:
    """Is the silent negotiation PROFITABLE? Fraction of interactions where the
    learned agent strikes a deal that beats the walk-away, and mean $ saved."""
    out = {}
    for N in n_grid:
        for M in m_grid:
            saved = [r["cells"][(N, M)]["saved"] for r in results]
            deal = [1.0 if r["cells"][(N, M)]["accepted"] else 0.0 for r in results]
            out[f"N{N}_M{M}"] = {"mean_saved_vs_walk": mean_ci(saved),
                                 "deal_rate": round(float(np.mean(deal)), 3)}
    return out


# ── experiment drivers ──────────────────────────────────────────────────────

def _build_env(seed: int):
    eval_m = _merchant(seed, day=0, tick=42, mid="eval")
    online_ms = [_merchant(seed, day=d, tick=t, mid=f"on{d}{t}")
                 for d, t in [(1, 30), (2, 54), (3, 20), (4, 66), (5, 40)]]
    return eval_m, online_ms


def run_headline(seed=TEST_SEED, n=200, *, k=K_CART, n_grid=N_GRID,
                 m_grid=M_GRID, noise_mult=1.0) -> dict:
    prior = PopPrior.build(cal_seed=CAL_SEED)
    eval_m, online_ms = _build_env(seed)
    pop = draw_vend_population(seed, n)
    res = {True: [], False: []}
    for draw in pop:
        for cart in (True, False):
            res[cart].append(run_buyer(draw, prior, eval_m, online_ms,
                                       cart=cart, k=k, noise_mult=noise_mult,
                                       n_grid=n_grid, m_grid=m_grid))
    out = {"config": {"seed": seed, "n": n, "k": k, "cal_seed": CAL_SEED,
                      "n_grid": list(n_grid), "m_grid": list(m_grid),
                      "noise_mult": noise_mult, "grid_n": GRID_N},
           "cart_on": {}, "cart_off": {}, "cart_lift": {}, "convergence": {}}
    for cart, tag in ((True, "cart_on"), (False, "cart_off")):
        rs = res[cart]
        out[tag] = {
            "joint_capture": _capture_table(rs, "joint", n_grid, m_grid),
            "buyer_capture": _capture_table(rs, "buyer", n_grid, m_grid),
            "buyer_capture_info_helps": _capture_table(
                [r for r in rs if r["oracle"]["buyer"] - r["noinfo"]["buyer"] > 1e-6],
                "buyer", n_grid, m_grid),
            "profitability": _profitability(rs, n_grid, m_grid),
            "oracle_minus_noinfo_joint": round(
                float(np.mean([r["oracle"]["joint"] - r["noinfo"]["joint"]
                               for r in rs])), 4),
            "oracle_minus_noinfo_buyer": round(
                float(np.mean([r["oracle"]["buyer"] - r["noinfo"]["buyer"]
                               for r in rs])), 4),
        }
    # convergence: curve error vs N (cart on, graded on the consideration set)
    for tag, cart in (("cart_on", True), ("cart_off", False)):
        conv = {}
        for N in n_grid:
            errs = [r["curve_err"][N] for r in res[cart]]
            conv[f"N{N}"] = mean_ci(errs)
        out["convergence"][tag] = conv
    # cart-signal lift: (aggregate capture WITH) − (aggregate capture WITHOUT),
    # paired-bootstrapped over buyer identity (same buyers in both arms). We
    # bootstrap the DIFFERENCE of ratio-of-sums rather than averaging per-buyer
    # ratios, which blow up when a buyer's oracle≈noinfo (denominator ≈ 0).
    for metric in ("joint", "buyer"):
        lift = {}
        for N in n_grid:
            for M in m_grid:
                nu_on = np.array([r["cells"][(N, M)][metric] - r["noinfo_cell"][(N, M)][metric]
                                  for r in res[True]])
                de_on = np.array([r["oracle_cell"][(N, M)][metric] - r["noinfo_cell"][(N, M)][metric]
                                  for r in res[True]])
                nu_off = np.array([r["cells"][(N, M)][metric] - r["noinfo_cell"][(N, M)][metric]
                                   for r in res[False]])
                de_off = np.array([r["oracle_cell"][(N, M)][metric] - r["noinfo_cell"][(N, M)][metric]
                                   for r in res[False]])
                lift[f"N{N}_M{M}"] = _lift_ci(nu_on, de_on, nu_off, de_off,
                                              seed=N * 100 + M)
        out["cart_lift"][metric] = lift
    return out


def _lift_ci(nu_on, de_on, nu_off, de_off, *, seed=0, B=2000) -> dict:
    """Paired bootstrap of (Σnu_on/Σde_on) − (Σnu_off/Σde_off) over buyers."""
    Don, Doff = float(de_on.sum()), float(de_off.sum())
    point = ((float(nu_on.sum()) / Don if abs(Don) > 1e-9 else float("nan"))
             - (float(nu_off.sum()) / Doff if abs(Doff) > 1e-9 else float("nan")))
    rng = np.random.default_rng(seed)
    m = len(nu_on)
    boot = []
    for _ in range(B):
        idx = rng.integers(0, m, m)
        don, doff = float(de_on[idx].sum()), float(de_off[idx].sum())
        if abs(don) > 1e-9 and abs(doff) > 1e-9:
            boot.append(float(nu_on[idx].sum()) / don
                        - float(nu_off[idx].sum()) / doff)
    boot = np.sort(boot)
    ci = ([round(float(np.percentile(boot, 2.5)), 4),
           round(float(np.percentile(boot, 97.5)), 4)] if len(boot) > 10 else None)
    sig = bool(ci is not None and (ci[0] > 0 or ci[1] < 0))
    return {"lift": round(point, 4), "ci95": ci, "n": m, "significant": sig}


def run_failure_modes(seed=TEST_SEED, n=200, *, k=K_CART) -> dict:
    prior = PopPrior.build(cal_seed=CAL_SEED)
    eval_m, online_ms = _build_env(seed)
    pop = draw_vend_population(seed, n)
    out = {}

    def cap(rs, key, N, M):
        nums = [r["cells"][(N, M)][key] - r["noinfo_cell"][(N, M)][key] for r in rs]
        dens = [r["oracle_cell"][(N, M)][key] - r["noinfo_cell"][(N, M)][key] for r in rs]
        return _ratio_ci(nums, dens, seed=1)

    # (1) tail vs typical types — |log wtp - prior mu| aggregated over SKUs
    def atypicality(draw):
        return float(np.mean([abs(math.log(draw.wtp[s]) - prior.mu_log[s])
                              / prior.sigma_log[s] for s in prior.skus]))
    scored = sorted(pop, key=atypicality)
    typ, tail = scored[:n // 3], scored[-n // 3:]
    for label, sub in (("typical", typ), ("tail", tail)):
        rs = [run_buyer(d, prior, eval_m, online_ms, cart=True, k=k) for d in sub]
        out[f"tail_{label}"] = {"joint_capture_N5_M0": cap(rs, "joint", 5, 0),
                                "buyer_capture_N5_M0": cap(rs, "buyer", 5, 0)}

    # (2) noisy / inconsistent answers (3x answer noise)
    rs = [run_buyer(d, prior, eval_m, online_ms, cart=True, k=k, noise_mult=3.0)
          for d in pop]
    out["noisy_answers_3x"] = {"joint_capture_N10_M0": cap(rs, "joint", 10, 0),
                               "buyer_capture_N10_M0": cap(rs, "buyer", 10, 0)}

    # (3) non-stationary preferences (taste drifts during the online phase)
    rs_drift = [run_buyer(d, prior, eval_m, online_ms, cart=True, k=k,
                          drift_sigma=0.15) for d in pop]
    rs_drift_ff = [run_buyer(d, prior, eval_m, online_ms, cart=True, k=k,
                             drift_sigma=0.15, online_inflate=0.15) for d in pop]
    out["drift_no_forget"] = {"joint_capture_N5_M10": cap(rs_drift, "joint", 5, 10)}
    out["drift_with_forget"] = {"joint_capture_N5_M10": cap(rs_drift_ff, "joint", 5, 10)}

    # (4) cold start (N=0): only prior + online, cart on vs off
    rs_on = [run_buyer(d, prior, eval_m, online_ms, cart=True, k=k) for d in pop]
    rs_off = [run_buyer(d, prior, eval_m, online_ms, cart=False, k=k) for d in pop]
    out["cold_start_N0"] = {
        "cart_on_joint_M0": cap(rs_on, "joint", 0, 0),
        "cart_on_joint_M10": cap(rs_on, "joint", 0, 10),
        "cart_off_joint_M0": cap(rs_off, "joint", 0, 0),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=TEST_SEED)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--k", type=int, default=K_CART)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default="buyer/results-preflearn.json")
    ap.add_argument("--no-failure", action="store_true")
    a = ap.parse_args(argv)
    n = 24 if a.quick else a.n
    head = run_headline(a.seed, n, k=a.k)
    results = {"headline": head}
    if not a.no_failure:
        results["failure_modes"] = run_failure_modes(a.seed, n, k=a.k)
    with open(a.out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    # console summary
    jc = head["cart_on"]["joint_capture"]
    print(f"[preflearn] n={n} k={a.k}  JOINT surplus capture (cart on):")
    for cell in ("N0_M0", "N3_M0", "N5_M0", "N10_M0", "N5_M10"):
        c = jc[cell]
        print(f"   {cell}: {c['capture']:.2%}  CI {c['ci95']}")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Elicitation + ARM-B — the mediator, built on the validated preflearn stack.

Reuses buyer/preflearn.py verbatim (SPEC.md §4: adapt the leak-tested
machinery, don't re-implement it): `PosteriorLearner` grid posteriors,
`TrueBuyer` as the answerer, `_best_query` info-gain question selection. The
"SKUs" are the divorce assets; the prior is fit on a DISJOINT calibration
population of compiled personas (population knowledge, never the test pair).

The WTP-null non-negotiables (SPEC.md §4):
  (i)  every posterior update is caused by a discrete asked question and its
       answer (probe: "is keeping the dog worth $X to you?"; pairwise: "the
       dog, or the vinyl?") — both compare MY-pile variants only, so the spite
       term cancels and the answer is pure revealed preference on v_i;
  (ii) `mediate()` is structurally ground-truth-free: its inputs are two
       answerer objects, two STATED (lam, walk_away) declarations, and the
       population prior — it can never read a Persona;
 (iii) no inference from offers — the mediator holds the two elicited
       posteriors and calls the frontier directly.

Acceptance of the mediated bundle is each side's own true-IR check (SPEC.md
§8.3): a proposal below your true walk-away is REJECTED — which is exactly how
bluffs that cross the line cost you deals (K4's mechanism).

Bluffing (K4) is a numeric policy, not an LLM disposition: the bluffer's
answer table carries an intensity-exaggerated hill (x BLUFF_HILL_MULT); stated
lam / walk_away stay truthful. Registered as intensity-exaggeration only.
"""
from __future__ import annotations

import math

import numpy as np

from snhp.nash_solver import filter_pareto_frontier, find_nash_bargaining_solution

from buyer.preflearn import PopPrior, PosteriorLearner, TrueBuyer, _probe_gain
from divorce import personas as P
from divorce.arms import WALLET_VALUE, enumerate_outcomes, refine_wallet_generic

ELICITABLE = [a for a in P.ASSET_NAMES if a != "wallet"]
Q_BUDGET = 10           # questions per side (registered 6-10, SPEC.md §8 K3;
                        # pilot: Q=8 marginal on K2/K3, Q=10 clears with room)
CAL_SEED = 20260717     # prior calibration seed stream — disjoint from test seeds
CAL_N = 400
GRID_N = 65
GRID_SPAN = 4.5
BLUFF_HILL_MULT = 1.5
# Pairwise logistic width, as a fraction of the anchor dollar scale. preflearn's
# fixed $0.15 tau is right for a $6 sandwich and is a step function at a $50k
# asset — hard truncation against a badly-estimated mean-field anchor cascades
# (the Q-freeze/runaway bug the first pilot exposed). Scale tau to the money.
PAIR_TAU_FRAC = 0.10
MIN_GAIN = 1e-7         # stop asking when no candidate moves the posterior


def build_asset_prior(cal_seed: int = CAL_SEED, n_cal: int = CAL_N) -> PopPrior:
    """Per-asset log-value grids fit on a calibration population of compiled
    personas (all archetypes, hills and fronts included, so the prior covers
    spiked values). max_resamples=1: the prior mirrors the raw persona
    distribution; qualification filtering is a test-population concern."""
    combos = [(a, b) for a in P.ARCHETYPE_NAMES for b in P.ARCHETYPE_NAMES]
    logs: dict[str, list[float]] = {a: [] for a in ELICITABLE}
    for i in range(n_cal):
        arch_a, arch_b = combos[i % len(combos)]
        rng = np.random.default_rng([cal_seed, i])
        pair = P.sample_pair(rng, arch_a, arch_b, max_resamples=1)
        for persona in (pair["a"], pair["b"]):
            for a in ELICITABLE:
                logs[a].append(math.log(persona.values[a]))
    grid_v, grid_lw, prior_w, mu_log, sigma_log = {}, {}, {}, {}, {}
    for a in ELICITABLE:
        lw = np.array(logs[a])
        mu, sg = float(lw.mean()), float(lw.std(ddof=1))
        g = np.linspace(mu - GRID_SPAN * sg, mu + GRID_SPAN * sg, GRID_N)
        w = np.exp(-0.5 * ((g - mu) / sg) ** 2)
        grid_lw[a], grid_v[a], prior_w[a] = g, np.exp(g), w / w.sum()
        mu_log[a], sigma_log[a] = mu, sg
    return PopPrior(ELICITABLE, grid_v, grid_lw, prior_w, mu_log, sigma_log)


class LinearAnswerer:
    """The persona's answering self for the v2 all-choices interview — the
    ONLY object holding its (possibly distorted) value table on the
    mediator's side of the wall. Answers ANY package choice u(A)-u(B) =
    sum(w*v)+sweetener with seeded logistic noise on the margin."""

    def __init__(self, values: dict[str, float], uid: int,
                 tau_frac: float = 0.08):
        self.v = dict(values)
        self.tau_frac = tau_frac
        self._rng = np.random.default_rng((uid * 2654435761) & 0x7FFFFFFF)

    def answer_linear(self, weights: dict[str, float], sweetener: float) -> bool:
        d = sum(w * self.v[a] for a, w in weights.items()) + sweetener
        scale = sum(abs(w) * self.v[a] for a, w in weights.items()) + abs(sweetener)
        tau = self.tau_frac * max(scale * 0.5, 200.0)
        p = 1.0 / (1.0 + np.exp(-np.clip(d / tau, -60, 60)))
        return bool(self._rng.random() < p)


def make_answerer(persona: P.Persona, uid: int, bluff: bool = False) -> LinearAnswerer:
    """Default (v2) answerer. Bluffing stays a numeric policy: the answer
    table carries an intensity-exaggerated hill (K4's registered form)."""
    vals = {a: persona.values[a] for a in ELICITABLE}
    if bluff:
        vals[persona.hill] *= BLUFF_HILL_MULT
    return LinearAnswerer(vals, uid)


def make_answerer_v1(persona: P.Persona, uid: int, bluff: bool = False) -> TrueBuyer:
    """The v1 (probe/pairwise) answerer — kept for reproducing pre-migration
    results; not the default."""
    vals = {a: persona.values[a] for a in ELICITABLE}
    if bluff:
        vals[persona.hill] *= BLUFF_HILL_MULT
    return TrueBuyer(uid, vals, walk_cost=0.0)


def _pair_tau(learner: PosteriorLearner, a1: str, a2: str) -> float:
    m = learner.mean()
    return max(50.0, PAIR_TAU_FRAC * 0.5 * (m[a1] + m[a2]))


def _pair_gain_scaled(learner: PosteriorLearner, a1: str, a2: str) -> float:
    """Expected rel-var reduction of the pure comparison "keep a1 or keep a2?"
    (prices 0) under the mean-field marginal model, with a DOLLAR-SCALED tau.
    Same structure as preflearn._pair_gain, which hardcodes the vend-scale
    PW_TAU and saturates at asset scale."""
    import numpy as _np
    tau = _pair_tau(learner, a1, a2)
    means = learner.mean()
    total = 0.0
    for sku, other in ((a1, means[a2]), (a2, means[a1])):
        v, w = learner.prior.grid_v[sku], learner.w[sku]
        u = _np.stack([v, _np.full_like(v, other), _np.zeros_like(v)]) / tau
        p = _np.exp(u - u.max(axis=0))
        p /= p.sum(axis=0)
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


def _best_query_divorce(learner: PosteriorLearner):
    """The divorce query policy: probes at three quantiles per asset ("is
    keeping the dog worth $X to you?") + EVERY pairwise comparison ("the dog,
    or the vinyl?"), scored by expected rel-var reduction. Wider pool than
    preflearn's (median probe + top-2 pairwise), which degenerates at this
    scale; same gain machinery underneath."""
    best, best_gain = None, MIN_GAIN
    for a in ELICITABLE:
        for q in (0.25, 0.5, 0.75):
            price = learner.quantile(a, q)
            g = _probe_gain(learner, a, price)
            if g > best_gain:
                best, best_gain = ("probe", a, price), g
    for i, a1 in enumerate(ELICITABLE):
        for a2 in ELICITABLE[i + 1:]:
            g = _pair_gain_scaled(learner, a1, a2)
            if g > best_gain:
                best, best_gain = ("pair", a1, a2), g
    return best


def bands(learner: PosteriorLearner) -> dict[str, list[float]]:
    """The heat-map's data: [p10, p25, p50, p75, p90] per asset, from the
    CURRENT posterior. Every narrowing the demo shows is one of these
    snapshots taken after a displayed question's answer (SPEC.md §4.i)."""
    return {a: [round(learner.quantile(a, q), 2)
                for q in (0.10, 0.25, 0.50, 0.75, 0.90)]
            for a in ELICITABLE}


def elicit(learner: PosteriorLearner, answerer: TrueBuyer, budget: int) -> list[dict]:
    """Run the info-gain interview: ask, record, update. Returns the Q&A trace
    (the demo's Act II is a cinematic playback of exactly this list — each
    record carries the post-answer posterior bands, so every narrowing on
    screen is caused by the recorded question). Stops early when no remaining
    question is expected to move the posterior."""
    trace = []
    for step in range(budget):
        best = _best_query_divorce(learner)
        if best is None:
            break
        if best[0] == "probe":
            _, asset, price = best
            yes = answerer.answer_probe(asset, price)
            learner.update_probe(asset, price, yes)
            trace.append({"step": step, "kind": "probe", "asset": asset,
                          "price": round(price, 2), "answer": bool(yes),
                          "bands": bands(learner)})
        else:
            _, a1, a2 = best
            A, B = (a1, 1, 0.0), (a2, 1, 0.0)
            tau = _pair_tau(learner, a1, a2)
            choice = answerer.answer_pairwise(A, B)
            learner.update_pairwise(A, B, choice, learner.mean(), tau=tau)
            trace.append({"step": step, "kind": "pair", "A": a1, "B": a2,
                          "answer": choice, "bands": bands(learner)})
    return trace


# ─── v2 query pool: EVERY question is a choice (RESULTS.md: humans answer
# trades, not valuations). A choice between package A and package B is linear
# in the value vector: u(A) - u(B) = sum_a weights[a]*v_a + sweetener (the
# cash rider). Single-asset-vs-cash and plain pairwise are special cases, so
# one update/gain pair covers the whole pool.

def update_linear_choice(learner: PosteriorLearner, weights: dict[str, float],
                         sweetener: float, chose_A: bool, tau: float) -> None:
    """Mean-field grid update for a linear package choice (the update_refusal
    pattern, generalized to a soft two-sided answer)."""
    import numpy as _np
    med = {a: learner.quantile(a, 0.5) for a in learner.skus}
    for a, w in weights.items():
        if abs(w) < 1e-12:
            continue
        other = sum(w2 * med[a2] for a2, w2 in weights.items()
                    if a2 != a) + sweetener
        v = learner.prior.grid_v[a]
        p_A = 1.0 / (1.0 + _np.exp(_np.clip(-(w * v + other) / tau, -60, 60)))
        learner._apply(a, p_A if chose_A else 1.0 - p_A)


def _linear_tau(learner: PosteriorLearner, weights: dict[str, float],
                sweetener: float) -> float:
    med = {a: learner.quantile(a, 0.5) for a in learner.skus}
    scale = sum(abs(w) * med[a] for a, w in weights.items()) + abs(sweetener)
    return max(50.0, PAIR_TAU_FRAC * 0.5 * scale)


def _linear_gain(learner: PosteriorLearner, weights: dict[str, float],
                 sweetener: float, tau: float) -> float:
    """Expected rel-var reduction of a linear package choice (mean-field),
    summed over involved assets — the _pair_gain structure, generalized."""
    import numpy as _np
    med = {a: learner.quantile(a, 0.5) for a in learner.skus}
    total = 0.0
    for a, w in weights.items():
        if abs(w) < 1e-12:
            continue
        other = sum(w2 * med[a2] for a2, w2 in weights.items()
                    if a2 != a) + sweetener
        v, wt = learner.prior.grid_v[a], learner.w[a]
        p_A = 1.0 / (1.0 + _np.exp(_np.clip(-(w * v + other) / tau, -60, 60)))
        m0 = float(wt @ v)
        v0 = float(wt @ (v - m0) ** 2) / (m0 * m0 + 1e-12)
        exp_v = 0.0
        for branch in (p_A, 1.0 - p_A):
            pr = float(wt @ branch)
            if pr < 1e-4:
                continue
            wr = wt * branch
            wr /= wr.sum()
            mr = float(wr @ v)
            exp_v += pr * float(wr @ (v - mr) ** 2) / (mr * mr + 1e-12)
        total += v0 - exp_v
    return total


def _best_query_v2(learner: PosteriorLearner):
    """The all-choices pool: cash-for-asset trades at three quantiles, plain
    asset-vs-asset, and asset-vs-asset with an equalizing cash rider."""
    best, best_gain = None, MIN_GAIN

    def consider(weights, sweetener):
        nonlocal best, best_gain
        tau = _linear_tau(learner, weights, sweetener)
        g = _linear_gain(learner, weights, sweetener, tau)
        if g > best_gain:
            best, best_gain = (weights, sweetener, tau), g

    med = {a: learner.quantile(a, 0.5) for a in ELICITABLE}
    for a in ELICITABLE:
        for q in (0.25, 0.5, 0.75):
            consider({a: 1.0}, -learner.quantile(a, q))
    for i, a1 in enumerate(ELICITABLE):
        for a2 in ELICITABLE[i + 1:]:
            consider({a1: 1.0, a2: -1.0}, 0.0)
            consider({a1: 1.0, a2: -1.0}, -(med[a1] - med[a2]))
            consider({a2: 1.0, a1: -1.0}, -(med[a2] - med[a1]))
    return best


def elicit_v2(learner: PosteriorLearner, answerer, budget: int) -> list[dict]:
    """The choices-only interview: every question is answer_linear(weights,
    sweetener) -> bool (took package A). Same trace-with-bands contract as
    elicit()."""
    trace = []
    for step in range(budget):
        best = _best_query_v2(learner)
        if best is None:
            break
        weights, sweetener, tau = best
        chose_A = bool(answerer.answer_linear(weights, sweetener))
        update_linear_choice(learner, weights, sweetener, chose_A, tau)
        trace.append({"step": step, "kind": "linear",
                      "weights": {k: round(v, 2) for k, v in weights.items()},
                      "sweetener": round(sweetener, 2), "answer": chose_A,
                      "bands": bands(learner)})
    return trace


def _margin(v_hat: dict[str, float], lam: float, fight: float,
            my_shares: dict[str, float], omega: float = 0.0) -> float:
    """IR margin over litigation, on the mediator's OWN scale:
        u(outcome) - u(court) + fight
            = (1+lam) * sum_a (s_a - 0.5 - omega) * v_a + fight
    (from the Persona.utility convention; court = 0.5 + omega of everything to
    an optimist — the STATED court-confidence declaration, M&K impediment #4).
    At omega = 0, assets split at the court ratio cancel exactly; a declared
    optimist pays an estimation-error toll of omega per asset — the price of
    insisting the judge loves you. The scale-mixing bug this replaces (stated
    walk-away in TRUE units vs utilities in ESTIMATED units) was the first
    pilot's 77%-rejection driver."""
    return (1.0 + lam) * sum((s - 0.5 - omega) * v_hat[a]
                             for a, s in my_shares.items()) + fight


DRAFTS_MAX = 6          # ratification rounds before the mediator abstains
REFUSAL_TAU = 750.0     # $ logistic width of the refusal likelihood


def update_refusal(learner: PosteriorLearner, shares: dict[str, float],
                   lam: float, fight: float, refused_by_this_side: bool,
                   omega: float = 0.0) -> None:
    """A draft refusal is elicitation data: refusing shares o says
        (1+lam) * sum_a (s_a - 0.5 - omega) * v_a + fight < 0
    — a linear inequality on the refuser's value vector, ingested mean-field
    per involved asset (others held at posterior medians), exactly the
    preflearn update_accept pattern at asset scale. An accepted draft would be
    the mirror-image constraint, but an acceptance ends the mediation."""
    import numpy as _np
    if not refused_by_this_side:
        return
    med = {a: learner.quantile(a, 0.5) for a in learner.skus}
    med["wallet"] = WALLET_VALUE
    for a in learner.skus:
        s_a = shares.get(a, 0.5)
        if abs(s_a - 0.5 - omega) < 1e-9:
            continue
        other = sum((s - 0.5 - omega) * med[nm] for nm, s in shares.items() if nm != a)
        v = learner.prior.grid_v[a]
        margin = (1.0 + lam) * ((s_a - 0.5 - omega) * v + other) + fight
        p_refuse = 1.0 / (1.0 + _np.exp(_np.clip(margin / REFUSAL_TAU, -60, 60)))
        learner._apply(a, p_refuse)


def mediate(prior: PopPrior, answerer_a: TrueBuyer, answerer_b: TrueBuyer,
            stated_a: dict, stated_b: dict, budget: int = Q_BUDGET,
            outcomes: list[dict[str, float]] | None = None,
            ratify_a=None, ratify_b=None, elicit_fn=None) -> dict:
    """The mediator, end to end — GROUND-TRUTH-FREE by construction: elicit
    both posteriors, score every bundle by each side's IR MARGIN (elicited
    medians + stated lam/fight_cost), restrict to bundles whose PESSIMISTIC
    margins clear (receive at q25, concede at q75 — the mediator knows its own
    uncertainty), pick the Nash point, refine the cash split, then RATIFY:
    slide the draft across the table as a direct yes/no ("better than court
    for you? don't tell me why"). A refusal excludes that bundle and the
    mediator re-selects, up to DRAFTS_MAX; if no draft survives, it ABSTAINS
    (no decree beats a decree a signature refuses). Ratification is still
    self-selection — the most decision-relevant choice there is — and the
    answers cross the wall as booleans via the ratify callbacks; this function
    never touches a Persona. stated_* = {"lam", "fight_cost", "optimism"} —
    structured declarations; never a raw utility number on the true scale."""
    outcomes = outcomes if outcomes is not None else enumerate_outcomes()
    la, lb = PosteriorLearner(prior), PosteriorLearner(prior)
    ask = elicit_fn if elicit_fn is not None else elicit_v2   # v2 = the default
    trace_a = ask(la, answerer_a, budget)
    trace_b = ask(lb, answerer_b, budget)

    W = {"wallet": WALLET_VALUE}
    wallet_a = np.array([o["wallet"] for o in outcomes])

    def flip(o):
        return {a: 1.0 - s for a, s in o.items()}

    def pess_margin(lo, hi, lam, fight, o, omega):
        # worst case within the band: the margin's per-asset weight is
        # (s - 0.5 - omega) — pessimism takes q25 where the weight is
        # positive, q75 where it is negative
        return (1.0 + lam) * sum(
            (s - 0.5 - omega) * (lo[a] if s - 0.5 - omega > 0 else hi[a])
            for a, s in o.items()
        ) + fight

    def score(learner, stated, flipped: bool):
        """Median and pessimistic margins for every bundle, from the CURRENT
        posterior. Point estimate = posterior MEDIAN: the per-asset posteriors
        are heavy-tailed (the prior covers hill/front multipliers), so the
        mean is tail-dominated; the median is calibrated."""
        med = {a: learner.quantile(a, 0.5) for a in ELICITABLE} | W
        lo = {a: learner.quantile(a, 0.25) for a in ELICITABLE} | W
        hi = {a: learner.quantile(a, 0.75) for a in ELICITABLE} | W
        view = (lambda o: flip(o)) if flipped else (lambda o: o)
        om = stated.get("optimism", 0.0)
        m = np.array([_margin(med, stated["lam"], stated["fight_cost"], view(o), om)
                      for o in outcomes])
        p = np.array([pess_margin(lo, hi, stated["lam"], stated["fight_cost"],
                                  view(o), om) for o in outcomes])
        return med, m, p


    def final_bands():
        # instrumentation for science_eval's recoverable-abstention analysis:
        # the mediator's OWN final read (q25/q50/q75) of each side, so an
        # auditor can reconstruct its confident set post-hoc.
        return {"a": {x: [la.quantile(x, .25), la.quantile(x, .5),
                          la.quantile(x, .75)] for x in ELICITABLE},
                "b": {x: [lb.quantile(x, .25), lb.quantile(x, .5),
                          lb.quantile(x, .75)] for x in ELICITABLE}}

    n_questions = len(trace_a) + len(trace_b)
    drafts = []
    excl_a = np.zeros(len(outcomes), dtype=bool)
    excl_b = np.zeros(len(outcomes), dtype=bool)
    med_a = med_b = None
    for _ in range(DRAFTS_MAX):
        # Re-score every round: refusals update the posteriors, so the whole
        # ranking can shift — not just the excluded bundles.
        med_a, m_a, p_a = score(la, stated_a, flipped=False)
        med_b, m_b, p_b = score(lb, stated_b, flipped=True)
        confident = (p_a >= 0.0) & (p_b >= 0.0) & ~excl_a & ~excl_b
        if confident.any():
            m_a_sel = np.where(confident, m_a, -np.inf)
            m_b_sel = np.where(confident, m_b, -np.inf)
        else:              # no confident bundle: draft best-guess, ratify hard
            m_a_sel = np.where(excl_a, -np.inf, m_a)
            m_b_sel = np.where(excl_b, -np.inf, m_b)
        pareto = filter_pareto_frontier(None, m_a_sel, m_b_sel)
        best = find_nash_bargaining_solution(pareto, m_a_sel, m_b_sel, 0.0, 0.0)
        if best is None:
            break
        base = dict(outcomes[best], wallet=0.0)
        s = refine_wallet_generic(
            _margin(med_a, stated_a["lam"], stated_a["fight_cost"], base,
                    stated_a.get("optimism", 0.0)),
            _margin(med_b, stated_b["lam"], stated_b["fight_cost"], flip(base),
                    stated_b.get("optimism", 0.0)),
            stated_a["lam"], stated_b["lam"], 0.0, 0.0)
        proposal = dict(outcomes[best], wallet=s)
        ok_a = ratify_a(proposal) if ratify_a is not None else True
        ok_b = ratify_b(proposal) if ratify_b is not None else True
        n_questions += 2
        drafts.append({"proposal": proposal, "ok_a": bool(ok_a), "ok_b": bool(ok_b)})
        if ok_a and ok_b:
            return {"proposal": proposal, "trace_a": trace_a, "trace_b": trace_b,
                    "n_questions": n_questions, "drafts": drafts,
                    "v_hat_a": med_a, "v_hat_b": med_b,
                    "final_bands": final_bands()}
        # A refusal is information twice over: (1) posterior update — the
        # refuser's margin at this bundle is negative, a linear inequality on
        # its values (update_refusal); (2) hard exclusion — this allocation at
        # this-or-worse compensation is off the refuser's table.
        same_alloc = np.array([
            all(abs(o[a] - outcomes[best][a]) < 1e-9
                for a in o if a != "wallet") for o in outcomes])
        if not ok_a:
            update_refusal(la, proposal, stated_a["lam"],
                           stated_a["fight_cost"], True,
                           stated_a.get("optimism", 0.0))
            excl_a |= same_alloc & (wallet_a <= s + 1e-9)
        if not ok_b:
            update_refusal(lb, flip(proposal), stated_b["lam"],
                           stated_b["fight_cost"], True,
                           stated_b.get("optimism", 0.0))
            excl_b |= same_alloc & (1.0 - wallet_a <= (1.0 - s) + 1e-9)
    return {"proposal": None, "trace_a": trace_a, "trace_b": trace_b,
            "n_questions": n_questions, "drafts": drafts,
            "v_hat_a": med_a, "v_hat_b": med_b,
            "final_bands": final_bands()}


def run_arm_b(pa: P.Persona, pb: P.Persona, prior: PopPrior,
              pair_seed: tuple[int, int], budget: int = Q_BUDGET,
              bluff_a: bool = False, bluff_b: bool = False,
              outcomes: list[dict[str, float]] | None = None,
              elicit_fn=None, make=None) -> dict:
    """ARM-B: mediated bundle from elicited posteriors, graded under TRUE
    utilities. The mediated proposal is accepted only if it clears BOTH sides'
    true walk-aways (each side's own private check — the second-signature
    beat); a rejected proposal is a no-deal and everyone litigates."""
    seed, i = pair_seed

    def flip_o(o):
        return {a: 1.0 - s for a, s in o.items()}

    # Ratification = the persona's own noiseless true-IR check ("would you
    # sign this?"). Bluffing here would mean refusing deals that help you —
    # self-punishing — so both arms ratify truthfully (SPEC.md §8.3).
    build = make if make is not None else (
        lambda p, uid: make_answerer(p, uid,
                                     bluff=(bluff_a if p is pa else bluff_b)))
    med = mediate(prior,
                  build(pa, seed * 100_003 + 2 * i),
                  build(pb, seed * 100_003 + 2 * i + 1),
                  {"lam": pa.lam, "fight_cost": pa.fight_cost,
                   "optimism": pa.optimism},
                  {"lam": pb.lam, "fight_cost": pb.fight_cost,
                   "optimism": pb.optimism},
                  budget, outcomes,
                  ratify_a=lambda o: pa.utility(o) >= pa.walk_away,
                  ratify_b=lambda o: pb.utility(flip_o(o)) >= pb.walk_away,
                  elicit_fn=elicit_fn)
    if med["proposal"] is None:
        return {"settled": False, "rejected": False, "proposed": False,
                "u_a": pa.walk_away, "u_b": pb.walk_away, "joint_surplus": 0.0,
                "ef_a": None, "ef_b": None, "n_questions": med["n_questions"]}
    shares_a = med["proposal"]
    flip = {a: 1.0 - s for a, s in shares_a.items()}
    fa, fb = pa.utility(shares_a), pb.utility(flip)
    accepted = fa >= pa.walk_away and fb >= pb.walk_away
    if not accepted:
        return {"settled": False, "rejected": True, "proposed": True,
                "rejected_by": [s for s, ok in
                                (("a", fa >= pa.walk_away), ("b", fb >= pb.walk_away))
                                if not ok],
                "u_a": pa.walk_away, "u_b": pb.walk_away, "joint_surplus": 0.0,
                "ef_a": None, "ef_b": None, "n_questions": med["n_questions"]}
    return {
        "settled": True, "rejected": False, "proposed": True,
        "shares_a": shares_a, "u_a": fa, "u_b": fb,
        "joint_surplus": (fa - pa.walk_away) + (fb - pb.walk_away),
        "ef_a": bool(pa.possession_value(shares_a) >= pa.possession_value(flip)),
        "ef_b": bool(pb.possession_value(flip) >= pb.possession_value(shares_a)),
        "n_questions": med["n_questions"],
    }

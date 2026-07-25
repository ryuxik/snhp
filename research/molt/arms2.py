"""Molt Season v2 — the arms under PREREG AMENDMENT 1.

The slow arm is no longer a ladder I wrote. It is the archetype suite in
`snhp/b2b_opponents.py`, driven AS IT IS over a negmas `SAOMechanism`, one issue
at a time with the already-settled issues frozen. The Works answers with its own
NPV under its belief, identically in every arm, so the only things that differ
between arms are the protocol and the clock.

Three orderings are treatments, not constants (A1.3):
  money_first  the v1 agenda, kept so the size of my thumb stays measurable
  random       drawn per crab-season
  best_first   the crab opens on its own highest-valued issue — the strongest
               opponent available, and the one the SNHP claim must beat
"""
from __future__ import annotations

import math

import numpy as np
from negmas.outcomes import make_issue, make_os
from negmas.preferences import MappingUtilityFunction
from negmas.sao import SAOMechanism, SAONegotiator, ResponseType

from molt.arms import (AGENDA, BASE_LABELS, BERTH_LABELS, BONUS_LABELS,
                       DEEP_LABELS, TITLE_LABELS, _offer_from_pkg,
                       _pkg_from_offer, crab_issues)
from molt.v2 import (Belief, Crab2, Package, Params2, crab_value, discloses,
                     p_leave_true, prior, replacement_cost, update, weight_mult,
                     works_best_reply, works_cost, works_npv, works_signs)
from molt.world import ISSUES, approval_days, clock_costs, crab_cash, \
    expired, opening_offer

OPTION_LABELS = {
    "base": list(BASE_LABELS), "title": list(TITLE_LABELS),
    "bonus": list(BONUS_LABELS), "berth": list(BERTH_LABELS),
    "deepwater": list(DEEP_LABELS),
}


def _with(pk: Package, issue: str, label: str) -> Package:
    d = dict(base=pk.base, title=pk.title, bonus=pk.bonus, berth=pk.berth,
             deep=pk.deep)
    if issue == "base":
        d["base"] = OPTION_LABELS["base"].index(label)
    elif issue == "bonus":
        d["bonus"] = OPTION_LABELS["bonus"].index(label)
    elif issue == "title":
        d["title"] = (label == TITLE_LABELS[1])
    elif issue == "berth":
        d["berth"] = (label == BERTH_LABELS[1])
    elif issue == "deepwater":
        d["deep"] = (label == DEEP_LABELS[1])
    return Package(**d)


def _norm(vals, lo=None, hi=None):
    a = np.asarray(vals, dtype=float)
    lo = a.min() if lo is None else lo
    hi = a.max() if hi is None else hi
    if hi - lo < 1e-12:
        return np.full_like(a, 0.5)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


# ------------------------------------------------------------- the Works' seat
class WorksSeat(SAONegotiator):
    """The employer, playing the same NPV-under-belief it plays in every other
    arm. It signs what is in front of it unless countering would gain it more
    than `counter_thresh` — the identical rule v1 used, so the protocols stay
    comparable."""

    def __init__(self, *args, util=None, thresh=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._u = util or {}
        self._thresh = thresh

    def _best(self):
        return max(self._u.items(), key=lambda kv: kv[1])[0] if self._u else None

    def propose(self, state):
        return self._best()

    def respond(self, state, source=None):
        off = state.current_offer
        if off is None:
            return ResponseType.REJECT_OFFER
        here = self._u.get(off, 0.0)
        best = self._u.get(self._best(), 0.0)
        if here >= best - self._thresh:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


# --------------------------------------------------------------- the slow arm
def _order(p: Params2, c: Crab2, mode: str, rng) -> list:
    if mode == "money_first":
        return list(AGENDA)
    if mode == "random":
        return list(rng.permutation(list(AGENDA)))
    # best_first: whatever this crab values most, first
    base = Package()
    val = {}
    for k in AGENDA:
        opts = OPTION_LABELS[k]
        val[k] = max(crab_value(p, c, _with(base, k, o)) for o in opts) \
            - crab_value(p, c, base)
    return sorted(AGENDA, key=lambda k: -val[k])


def slow_archetype(p: Params2, c: Crab2, arch_name: str, ordering: str,
                   rng, trace: list | None = None,
                   force_disclose: bool | None = None) -> dict:
    """One salary negotiation, conducted the way they actually are: one issue at
    a time, over email, by somebody running a named strategy."""
    from b2b_opponents import B2B_OPPONENTS

    op = opening_offer(p, c)
    cur = op
    spoke = discloses(p, c) if force_disclose is None else \
        (force_disclose and c.has_outside and p.credibility == 'verifiable')
    bel = update(p, c, prior(p, c), spoke)
    order = _order(p, c, ordering, rng)
    budget = p.exchange_budget
    exchanges = 0
    day = 0.0
    from molt.v2 import outside_value
    ov = outside_value(p, c)

    for k, issue in enumerate(order):
        if budget <= 0:
            break
        opts = OPTION_LABELS[issue]
        cands = [_with(cur, issue, o) for o in opts]
        # the Works will not consider going backwards on an already-settled issue
        keep = [i for i, pk in enumerate(cands)
                if crab_value(p, c, pk) >= crab_value(p, c, cur) - 1e-9]
        if len(keep) < 2:
            continue
        labels = [opts[i] for i in keep]
        cands = [cands[i] for i in keep]
        os_ = make_os([make_issue(labels, name=issue)])
        outs = list(os_.enumerate_or_sample())
        cu = _norm([crab_value(p, c, pk) for pk in cands])
        wu = _norm([works_npv(p, c, bel, pk) for pk in cands])
        u_crab = MappingUtilityFunction(dict(zip(outs, cu)), outcome_space=os_)
        u_works = MappingUtilityFunction(dict(zip(outs, wu)), outcome_space=os_)
        lo = min(crab_value(p, c, pk) for pk in cands)
        hi = max(crab_value(p, c, pk) for pk in cands)
        u_crab.reserved_value = float(np.clip((ov - lo) / (hi - lo), 0.0, 1.0)) \
            if hi > lo and c.has_outside else 0.0
        steps = max(2, min(budget, math.ceil(p.exchange_budget / len(order))))
        m = SAOMechanism(outcome_space=os_, n_steps=steps)
        seat = B2B_OPPONENTS[arch_name](name="crab")
        works = WorksSeat(name="works", util=dict(zip(outs, wu)),
                          thresh=p.counter_thresh * 4.0)
        m.add(seat, ufun=u_crab)
        m.add(works, ufun=u_works)
        m.run()
        used = max(1, int(m.current_step))
        exchanges += used
        budget -= used
        day += float(sum(c.delays[(k * 3 + j) % len(c.delays)]
                         for j in range(min(used, 3))))
        nxt = cur
        if m.agreement is not None:
            nxt = cands[outs.index(tuple(m.agreement))]
        if trace is not None:
            trace.append({"issue": issue, "archetype": arch_name,
                          "exchanges": used, "day": round(day, 1),
                          "agreed": m.agreement is not None,
                          "pkg": nxt.labels(),
                          "crab_value": round(crab_value(p, c, nxt)),
                          "works_cost": round(works_cost(p, c, nxt))})
        if works_npv(p, c, bel, nxt) >= works_npv(p, c, bel, cur):
            cur = nxt
    # one meeting to lock it down, then sign-off
    if p.clock:
        day += float(np.exp(np.log(p.meeting_med)
                            + p.meeting_sig * (c.u_exo - 0.5) * 2))
    day += approval_days(p, cur, op)
    return settle2(p, c, cur, max(day, 1.0), meetings=1,
                   exchanges=exchanges, spoke=spoke)


# ------------------------------------------------------------ the engine arms
def sitting_crab(p: Params2, c: Crab2, seed: int,
                 trace: list | None = None,
                 force_disclose: bool | None = None) -> dict:
    from gametheory.negotiation.bundle import negotiate_bundle
    from molt.arms import crab_batna_norm

    op = opening_offer(p, c)
    spoke = discloses(p, c) if force_disclose is None else \
        (force_disclose and c.has_outside and p.credibility == 'verifiable')
    bel = update(p, c, prior(p, c), spoke)
    issues = crab_issues(p, c)
    prio = {k: float(w) for k, w in zip(ISSUES, c.w)}
    seen = [_offer_from_pkg(op)]
    cur = op
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=seen,
                               my_priorities=prio, my_batna=crab_batna_norm(p, c),
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + r, rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        ask = _pkg_from_offer(res.get("recommended_offer") or {})
        if trace is not None:
            trace.append({"round": r + 1, "actor": "crab", "pkg": ask.labels(),
                          "crab_value": round(crab_value(p, c, ask)),
                          "works_cost": round(works_cost(p, c, ask)),
                          "logic": res.get("trade_logic")})
        reply = works_best_reply(p, c, bel, op, crab_value(p, c, cur))
        if works_signs(p, c, bel, ask, cur, reply):
            cur = ask
            break
        if reply is None:
            break
        cur = reply
        seen.append(_offer_from_pkg(cur))
        if trace is not None:
            trace.append({"round": r + 1, "actor": "works", "pkg": cur.labels(),
                          "crab_value": round(crab_value(p, c, cur)),
                          "works_cost": round(works_cost(p, c, cur))})
    return settle2(p, c, cur, 1.0 + approval_days(p, cur, op), meetings=1,
                   exchanges=p.max_rounds, spoke=spoke)


def sitting_works(p: Params2, c: Crab2, seed: int) -> dict:
    """The Works brings the engine and opens with a package."""
    from gametheory.negotiation.bundle import negotiate_bundle
    from molt.arms import _human_ask, _grant_single, aspiration, works_issues

    op = opening_offer(p, c)
    spoke = discloses(p, c)
    bel = update(p, c, prior(p, c), spoke)
    issues = works_issues(p, c)
    cmax = {"base": works_cost(p, c, Package(base=4)),
            "title": works_cost(p, c, Package(title=True)),
            "bonus": works_cost(p, c, Package(bonus=2)),
            "berth": works_cost(p, c, Package(berth=True)),
            "deepwater": works_cost(p, c, Package(deep=True))}
    tot = sum(cmax.values()) or 1.0
    prio = {k: v / tot for k, v in cmax.items()}
    seen = [_offer_from_pkg(Package(4, True, 2, True, True))]
    cur = op
    asp = aspiration(p, c)
    batna = float(np.clip(
        (-replacement_cost(p, c) + works_cost(p, c, Package(3, True, 2, True, True)))
        / max(works_cost(p, c, Package(3, True, 2, True, True)), 1.0), 0.0, 1.0))
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=seen,
                               my_priorities=prio, my_batna=batna,
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + 500 + r, rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        prop = _pkg_from_offer(res.get("recommended_offer") or {})
        if works_npv(p, c, bel, prop) < works_npv(p, c, bel, cur):
            break
        cur = prop
        if crab_value(p, c, cur) >= asp:
            break
        top = max(ISSUES, key=lambda k: weight_mult(c)[k])
        seen.append(_offer_from_pkg(_grant_single(p, c, cur, top,
                                                  _human_ask(c, top))))
    return settle2(p, c, cur, 1.0 + approval_days(p, cur, op), meetings=1,
                   exchanges=p.max_rounds, spoke=spoke)


def arm_sign(p: Params2, c: Crab2) -> dict:
    return settle2(p, c, opening_offer(p, c), 1.0, meetings=0, exchanges=0,
                   spoke=False)


# ------------------------------------------------------------------- scoring
def settle2(p: Params2, c: Crab2, pk: Package, days: float, meetings: int,
            exchanges: int, spoke: bool) -> dict:
    cc = clock_costs(p, c, days, meetings)
    walked = cc["walked"]
    exp = expired(p, c, days)
    overhead = cc["mgr"] + cc["distraction"]
    rep = replacement_cost(p, c)
    from molt.v2 import outside_value
    if walked:
        return _row(outside_value(p, c) if c.has_outside else 0.0,
                    -rep - overhead, 0.0, 0.0, days, meetings, exchanges,
                    False, True, True, exp, cc, rep, pk, spoke, c, p)
    pl = p_leave_true(p, c, pk, exp)
    if c.u_taste < pl:
        pay = outside_value(p, c) if (c.has_outside and not exp) else 0.0
        return _row(pay, -rep - overhead, 0.0, 0.0, days, meetings, exchanges,
                    True, True, False, exp, cc, rep, pk, spoke, c, p)
    return _row(crab_value(p, c, pk), -works_cost(p, c, pk) - overhead,
                crab_cash(p, c, pk), works_cost(p, c, pk), days, meetings,
                exchanges, True, False, False, exp, cc, 0.0, pk, spoke, c, p)


def _row(crab, works, cash, conc, days, meetings, exchanges, agreed, left,
         walked, exp, cc, rep, pk, spoke, c, p):
    return {"crab": crab, "works": works, "cash_paid": cash, "concession": conc,
            "days": days, "meetings": meetings, "exchanges": exchanges,
            "agreed": agreed, "left": left, "walked": walked, "expired": exp,
            "mgr": cc["mgr"], "distraction": cc["distraction"],
            "replacement": rep, "pkg": pk, "disclosed": spoke,
            "match": c.match, "has_outside": c.has_outside}


REPORTED_ARCHETYPES = ("Split-the-Diff", "Anchorer", "Silent Hardliner",
                       "Deadline Exploiter", "Logroller", "Tactical Empath")


def resettle(p_off: Params2, c: Crab2, row: dict) -> dict:
    """Score an already-conducted negotiation under the zero-clock condition.
    The package is not renegotiated — turning the clock off changes what the
    calendar COSTS, never what was agreed (the v1 test suite pins this)."""
    return settle2(p_off, c, row["pkg"], 1.0, row["meetings"], row["exchanges"],
                   row["disclosed"])

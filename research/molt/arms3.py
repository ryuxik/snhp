"""Molt Season v3 arms — six issues, five employer budgets (AMENDMENT 2).

Same protocols as v2: archetypes over negmas one issue at a time for the slow
arm, the real `negotiate_bundle` for the sitting arm. What changes is that the
Works now prices each issue out of a different pocket, so which trade is best
varies by crab and by season — which is the thing a logroller is supposed to find
and a one-issue-at-a-time bargainer is not.
"""
from __future__ import annotations

import math

import numpy as np
from negmas.outcomes import make_issue, make_os
from negmas.preferences import MappingUtilityFunction
from negmas.sao import SAOMechanism

from molt.arms import AGENDA, _offer_from_pkg
from molt.arms2 import WorksSeat, _norm
from molt.v2 import Crab2, prior, replacement_cost, update
from molt.v3 import (ISSUE_BUDGET, Package, Params3, Season, crab_cash3,
                     crab_value3, discloses3, feasible, p_leave_true3,
                     slot_open, works_best_reply3, works_cost3, works_npv3,
                     works_signs3)
from molt.world import (BASE_LABELS, BERTH_LABELS, BONUS_LABELS, DEEP_LABELS,
                        ISSUES_V3, PTO_DAYS, PTO_LABELS, TITLE_LABELS,
                        approval_days, clock_costs, expired, opening_offer,
                        outside_value, weight_mult)

AGENDA3 = ("base", "bonus", "berth", "title", "deepwater", "pto")
OPTS = {"base": list(BASE_LABELS), "title": list(TITLE_LABELS),
        "bonus": list(BONUS_LABELS), "berth": list(BERTH_LABELS),
        "deepwater": list(DEEP_LABELS), "pto": list(PTO_LABELS)}


def _with(pk: Package, issue: str, label: str) -> Package:
    d = dict(base=pk.base, title=pk.title, bonus=pk.bonus, berth=pk.berth,
             deep=pk.deep, pto=pk.pto)
    if issue == "base":
        d["base"] = OPTS["base"].index(label)
    elif issue == "bonus":
        d["bonus"] = OPTS["bonus"].index(label)
    elif issue == "pto":
        d["pto"] = OPTS["pto"].index(label)
    elif issue == "title":
        d["title"] = (label == TITLE_LABELS[1])
    elif issue == "berth":
        d["berth"] = (label == BERTH_LABELS[1])
    elif issue == "deepwater":
        d["deep"] = (label == DEEP_LABELS[1])
    return Package(**d)


def _pkg_from(off: dict) -> Package:
    return Package(base=OPTS["base"].index(off.get("base", BASE_LABELS[0])),
                   title=(off.get("title") == TITLE_LABELS[1]),
                   bonus=OPTS["bonus"].index(off.get("bonus", BONUS_LABELS[0])),
                   berth=(off.get("berth") == BERTH_LABELS[1]),
                   deep=(off.get("deepwater") == DEEP_LABELS[1]),
                   pto=OPTS["pto"].index(off.get("pto", PTO_LABELS[0])))


# ------------------------------------------------------------- crab's issues
def crab_issues3(p: Params3, c: Crab2, sea: Season, rate: float | None = None):
    """The six issues in the crab's own dollars. `rate` overrides the perk
    exchange rate — K17 uses it to give the employer's engine a biased view of
    what the crab's perks are worth."""
    pp = p if rate is None else Params3(**{**p.__dict__, "perk_rate": rate})
    v = lambda pk: crab_value3(pp, c, pk)              # noqa: E731
    z = Package()
    out = [
        {"name": "base", "options": OPTS["base"],
         "my_utility": [v(Package(base=b)) for b in range(5)],
         "their_utility": [4.0, 3.0, 2.0, 1.0, 0.0]},
        {"name": "bonus", "options": OPTS["bonus"],
         "my_utility": [v(Package(bonus=b)) for b in range(3)],
         "their_utility": [2.0, 1.0, 0.0]},
        {"name": "berth", "options": OPTS["berth"],
         "my_utility": [v(z), v(Package(berth=True))],
         "their_utility": [1.0, 0.0]},
        {"name": "deepwater", "options": OPTS["deepwater"],
         "my_utility": [v(z), v(Package(deep=True))],
         "their_utility": [1.0, 0.0]},
        {"name": "pto", "options": OPTS["pto"],
         "my_utility": [v(Package(pto=i)) for i in range(3)],
         "their_utility": [2.0, 1.0, 0.0]},
    ]
    if slot_open(p, sea):
        out.insert(1, {"name": "title", "options": OPTS["title"],
                       "my_utility": [v(z), v(Package(title=True))],
                       "their_utility": [1.0, 0.0]})
    return out


def works_issues3(p: Params3, c: Crab2, sea: Season):
    k = lambda pk: -works_cost3(p, c, sea, pk)         # noqa: E731
    z = Package()
    out = [
        {"name": "base", "options": OPTS["base"],
         "my_utility": [k(Package(base=b)) for b in range(5)],
         "their_utility": [0.0, 1.0, 2.0, 3.0, 4.0]},
        {"name": "bonus", "options": OPTS["bonus"],
         "my_utility": [k(Package(bonus=b)) for b in range(3)],
         "their_utility": [0.0, 1.0, 2.0]},
        {"name": "berth", "options": OPTS["berth"],
         "my_utility": [k(z), k(Package(berth=True))],
         "their_utility": [0.0, 1.0]},
        {"name": "deepwater", "options": OPTS["deepwater"],
         "my_utility": [k(z), k(Package(deep=True))],
         "their_utility": [0.0, 1.0]},
        {"name": "pto", "options": OPTS["pto"],
         "my_utility": [k(Package(pto=i)) for i in range(3)],
         "their_utility": [0.0, 1.0, 2.0]},
    ]
    if slot_open(p, sea):
        out.insert(1, {"name": "title", "options": OPTS["title"],
                       "my_utility": [k(z), k(Package(title=True))],
                       "their_utility": [0.0, 1.0]})
    return out


def crab_batna3(p: Params3, c: Crab2, sea: Season) -> float:
    lo = crab_value3(p, c, Package())
    hi = crab_value3(p, c, Package(4, slot_open(p, sea), 2, True, True, 2))
    ov = outside_value(p, c)
    return float(np.clip((ov - lo) / (hi - lo), 0.0, 1.0)) if hi > lo else 0.5


# -------------------------------------------------------------- the slow arm
def _order3(p, c, sea, mode, rng):
    if mode == "money_first":
        return [i for i in AGENDA3 if slot_open(p, sea) or i != "title"]
    live = [i for i in AGENDA3 if slot_open(p, sea) or i != "title"]
    if mode == "random":
        return list(rng.permutation(live))
    base = Package()
    val = {k: max(crab_value3(p, c, _with(base, k, o)) for o in OPTS[k])
              - crab_value3(p, c, base) for k in live}
    return sorted(live, key=lambda k: -val[k])


def slow_archetype3(p: Params3, c: Crab2, sea: Season, arch: str, ordering: str,
                    rng, force_disclose=None) -> dict:
    from b2b_opponents import B2B_OPPONENTS

    op = opening_offer(p, c)
    cur = op
    spoke = discloses3(p, c, sea) if force_disclose is None else \
        (force_disclose and c.has_outside and p.credibility == "verifiable")
    bel = update(p, c, prior(p, c), spoke)
    order = _order3(p, c, sea, ordering, rng)
    budget, exchanges, day = p.exchange_budget, 0, 0.0
    ov = outside_value(p, c)

    for k, issue in enumerate(order):
        if budget <= 0:
            break
        cands = [_with(cur, issue, o) for o in OPTS[issue]]
        keep = [i for i, pk in enumerate(cands)
                if crab_value3(p, c, pk) >= crab_value3(p, c, cur) - 1e-9
                and feasible(p, sea, pk)]
        if len(keep) < 2:
            continue
        labels = [OPTS[issue][i] for i in keep]
        cands = [cands[i] for i in keep]
        os_ = make_os([make_issue(labels, name=issue)])
        outs = list(os_.enumerate_or_sample())
        cu = _norm([crab_value3(p, c, pk) for pk in cands])
        wu = _norm([works_npv3(p, c, sea, bel, pk) for pk in cands])
        u_crab = MappingUtilityFunction(dict(zip(outs, cu)), outcome_space=os_)
        u_works = MappingUtilityFunction(dict(zip(outs, wu)), outcome_space=os_)
        lo = min(crab_value3(p, c, pk) for pk in cands)
        hi = max(crab_value3(p, c, pk) for pk in cands)
        u_crab.reserved_value = float(np.clip((ov - lo) / (hi - lo), 0.0, 1.0)) \
            if hi > lo and c.has_outside else 0.0
        steps = max(2, min(budget, math.ceil(p.exchange_budget / len(order))))
        m = SAOMechanism(outcome_space=os_, n_steps=steps)
        m.add(B2B_OPPONENTS[arch](name="crab"), ufun=u_crab)
        m.add(WorksSeat(name="works", util=dict(zip(outs, wu)),
                        thresh=p.counter_thresh * 4.0), ufun=u_works)
        m.run()
        used = max(1, int(m.current_step))
        exchanges += used
        budget -= used
        day += float(sum(c.delays[(k * 3 + j) % len(c.delays)]
                         for j in range(min(used, 3))))
        if m.agreement is not None:
            nxt = cands[outs.index(tuple(m.agreement))]
            if works_npv3(p, c, sea, bel, nxt) >= works_npv3(p, c, sea, bel, cur):
                cur = nxt
    if p.clock:
        day += float(np.exp(np.log(p.meeting_med)
                            + p.meeting_sig * (c.u_exo - 0.5) * 2))
    day += approval_days(p, cur, op)
    return settle3(p, c, sea, cur, max(day, 1.0), 1, exchanges, spoke)


# ------------------------------------------------------------ the engine arms
def sitting_crab3(p: Params3, c: Crab2, sea: Season, seed: int,
                  force_disclose=None) -> dict:
    from gametheory.negotiation.bundle import negotiate_bundle

    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea) if force_disclose is None else \
        (force_disclose and c.has_outside and p.credibility == "verifiable")
    bel = update(p, c, prior(p, c), spoke)
    issues = crab_issues3(p, c, sea)
    prio = {k: float(w) for k, w in zip(ISSUES_V3, list(c.w) + [c.w[3]])
            if any(i["name"] == k for i in issues)}
    seen = [_offer_from_pkg(op) | {"pto": PTO_LABELS[0]}]
    cur = op
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=seen,
                               my_priorities=prio, my_batna=crab_batna3(p, c, sea),
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + r, rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        ask = _pkg_from(res.get("recommended_offer") or {})
        reply = works_best_reply3(p, c, sea, bel, op, crab_value3(p, c, cur))
        if works_signs3(p, c, sea, bel, ask, cur, reply):
            cur = ask
            break
        if reply is None:
            break
        cur = reply
        seen.append(cur.labels())
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


def sitting_works3(p: Params3, c: Crab2, sea: Season, seed: int,
                   biased: bool = False) -> dict:
    """The Works brings the engine. With `biased`, it values the crab's perks at
    `employer_rate_bias` x their true worth — K17."""
    from gametheory.negotiation.bundle import negotiate_bundle

    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    issues = works_issues3(p, c, sea)
    cost = {i["name"]: abs(min(i["my_utility"])) for i in issues}
    tot = sum(cost.values()) or 1.0
    prio = {k: v / tot for k, v in cost.items()}
    rate = p.perk_rate * (p.employer_rate_bias if biased else 1.0)
    view = Params3(**{**p.__dict__, "perk_rate": rate})
    top = Package(4, slot_open(p, sea), 2, True, True, 2)
    seen = [top.labels()]
    cur = op
    asp = outside_value(p, c) if c.has_outside else 0.04 * c.salary
    batna = float(np.clip(
        (-replacement_cost(p, c) + works_cost3(p, c, sea, top))
        / max(works_cost3(p, c, sea, top), 1.0), 0.0, 1.0))
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=seen,
                               my_priorities=prio, my_batna=batna,
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + 500 + r, rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        prop = _pkg_from(res.get("recommended_offer") or {})
        if works_npv3(p, c, sea, bel, prop) < works_npv3(p, c, sea, bel, cur):
            break
        cur = prop
        # the Works stops as soon as IT BELIEVES the crab is satisfied — under a
        # biased rate it believes that sooner than it should
        if crab_value3(view, c, cur) >= asp:
            break
        best = max(ISSUES_V3, key=lambda k: weight_mult(c).get(k, 0.0)
                   if k in weight_mult(c) else 0.0)
        seen.append(_with(cur, best if best in OPTS else "base",
                          OPTS[best if best in OPTS else "base"][-1]).labels())
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


def arm_sign3(p: Params3, c: Crab2, sea: Season) -> dict:
    return settle3(p, c, sea, opening_offer(p, c), 1.0, 0, 0, False)


# ------------------------------------------------------------------- scoring
def settle3(p: Params3, c: Crab2, sea: Season, pk: Package, days: float,
            meetings: int, exchanges: int, spoke: bool) -> dict:
    cc = clock_costs(p, c, days, meetings)
    exp = expired(p, c, days)
    overhead = cc["mgr"] + cc["distraction"]
    rep = replacement_cost(p, c)
    if cc["walked"]:
        return _row3(outside_value(p, c) if c.has_outside else 0.0, 0.0,
                     -rep - overhead, 0.0, days, meetings, exchanges, False,
                     True, True, exp, cc, rep, pk, spoke, c)
    pl = p_leave_true3(p, c, pk, exp)
    if c.u_taste < pl:
        pay = outside_value(p, c) if (c.has_outside and not exp) else 0.0
        return _row3(pay, 0.0, -rep - overhead, 0.0, days, meetings, exchanges,
                     True, True, False, exp, cc, rep, pk, spoke, c)
    return _row3(crab_value3(p, c, pk), crab_cash3(p, c, pk),
                 -works_cost3(p, c, sea, pk) - overhead,
                 works_cost3(p, c, sea, pk), days, meetings, exchanges, True,
                 False, False, exp, cc, 0.0, pk, spoke, c)


def _row3(crab, cash, works, conc, days, meetings, exchanges, agreed, left,
          walked, exp, cc, rep, pk, spoke, c):
    return {"crab": crab, "cash": cash, "works": works, "concession": conc,
            "days": days, "meetings": meetings, "exchanges": exchanges,
            "agreed": agreed, "left": left, "walked": walked, "expired": exp,
            "mgr": cc["mgr"], "distraction": cc["distraction"],
            "replacement": rep, "pkg": pk, "disclosed": spoke,
            "match": c.match,
            "granted_title": 1.0 if (pk.title and not left) else 0.0,
            "granted_berth": 1.0 if (pk.berth and not left) else 0.0,
            "granted_deep": 1.0 if (pk.deep and not left) else 0.0,
            "granted_pto": 1.0 if (pk.pto and not left) else 0.0}


REPORTED_ARCHETYPES = ("Split-the-Diff", "Anchorer", "Silent Hardliner",
                       "Deadline Exploiter", "Logroller", "Tactical Empath")

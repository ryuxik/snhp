"""Molt Season — the six arms (PREREG §2).

Every arm returns the same tuple `(Package, days, meetings, hops, trace)` and is
scored by the single `settle()` below, so no arm can be flattered by its own
accounting. The Works' concession set (`world.works_packages`) and its NPV
function are shared: what differs between arms is only the PROTOCOL — what gets
put on the table, in what order, and how many calendar days it takes.

The engine arms call the real product:
  * `gametheory.negotiation.bundle.negotiate_bundle` (arms D, E, F)
  * `gametheory.negotiation.plain_terms.negotiate_turn` (arm C)
There is no reimplementation of either anywhere in this package.
"""
from __future__ import annotations

import numpy as np

from molt.world import (BASE_LABELS, BASE_PCT, BERTH_LABELS, BONUS_LABELS,
                        BONUS_MO, DEEP_LABELS, ISSUES, PVF, TITLE_LABELS,
                        Crab, Package, Params, approval_days, clock_costs,
                        crab_cash, crab_value, expired, needs_approval,
                        opening_offer, outside_value, p_leave, weight_mult,
                        works_cost, works_npv, works_packages)

# the agenda a human meeting series follows: money first, and base is settled
# before anything else is even raised. This ordering is the mechanism under
# test, not an incidental choice.
AGENDA = ("base", "bonus", "berth", "title", "deepwater")


# --------------------------------------------------------------- scoring
def settle(p: Params, c: Crab, pk: Package, days: float, meetings: int,
           walked_override: bool | None = None) -> dict:
    """Score a concluded (or abandoned) negotiation. Identical for every arm."""
    cc = clock_costs(p, c, days, meetings)
    walked = cc["walked"] if walked_override is None else walked_override
    exp = expired(p, c, days)
    overhead = cc["mgr"] + cc["distraction"]
    S = c.salary
    if walked:
        # left mid-negotiation, taking the outside offer
        return {"crab": outside_value(p, c) if c.has_outside else 0.0,
                "works": -p.spec_rho(c.spec) * S - overhead,
                "cash_paid": 0.0, "concession": 0.0,
                "days": days, "meetings": meetings, "agreed": False,
                "left": True, "walked": True, "expired": exp,
                "mgr": cc["mgr"], "distraction": cc["distraction"],
                "replacement": p.spec_rho(c.spec) * S, "pkg": pk}
    pl = p_leave(p, c, pk, exp)
    leaves = bool(c.u_taste < pl)
    if leaves:
        crab_pay = outside_value(p, c) if (c.has_outside and not exp) else 0.0
        return {"crab": crab_pay,
                "works": -p.spec_rho(c.spec) * S - overhead,
                "cash_paid": 0.0, "concession": 0.0,
                "days": days, "meetings": meetings, "agreed": True,
                "left": True, "walked": False, "expired": exp,
                "mgr": cc["mgr"], "distraction": cc["distraction"],
                "replacement": p.spec_rho(c.spec) * S, "pkg": pk}
    return {"crab": crab_value(p, c, pk),
            "works": -works_cost(p, c, pk) - overhead,
            "cash_paid": crab_cash(p, c, pk),
            "concession": works_cost(p, c, pk),
            "days": days, "meetings": meetings, "agreed": True,
            "left": False, "walked": False, "expired": exp,
            "mgr": cc["mgr"], "distraction": cc["distraction"],
            "replacement": 0.0, "pkg": pk}


# --------------------------------------------------------- shared behaviours
def works_best_reply(p: Params, c: Crab, base_pkg: Package,
                    floor_value: float) -> Package | None:
    """The Works' best package among those that beat `floor_value` for the crab.
    This is the Works playing well: it maximises its own NPV subject to actually
    moving the crab. Returns None if nothing improving is worth it."""
    best, best_v = None, works_npv(p, c, base_pkg)
    for pk in works_packages(p, base_pkg):
        if crab_value(p, c, pk) <= floor_value + 1e-9:
            continue
        v = works_npv(p, c, pk)
        if v > best_v:
            best, best_v = pk, v
    return best


def works_signs(p: Params, c: Crab, ask: Package, cur: Package,
               reply: Package | None) -> bool:
    """Does the Works sign what is in front of it, or counter?

    It signs iff the ask beats holding firm AND countering would not gain it
    more than `counter_thresh` of salary. Without the second clause the Works is
    a pushover and every engine arm is flattered (measured: it left >0.5% of
    salary on the table in 17 of 37 immediate signings).
    """
    if works_npv(p, c, ask) < works_npv(p, c, cur):
        return False
    if reply is None:
        return True
    gain = works_npv(p, c, reply) - works_npv(p, c, ask)
    return gain <= p.counter_thresh * c.salary


def _grant_single(p: Params, c: Crab, cur: Package, issue: str,
                  ask: int | bool) -> Package:
    """The MYOPIC single-instrument grant that sequential bargaining produces:
    the Works improves its NPV on this one issue, holding everything already
    agreed fixed and never revisiting it."""
    cands = [cur]
    if issue == "base":
        cands += [Package(b, cur.title, cur.bonus, cur.berth, cur.deep)
                  for b in range(cur.base + 1, int(ask) + 1)]
    elif issue == "bonus":
        cands += [Package(cur.base, cur.title, bo, cur.berth, cur.deep)
                  for bo in range(cur.bonus + 1, int(ask) + 1)]
    elif issue == "title" and ask and not cur.title:
        cands.append(Package(cur.base, True, cur.bonus, cur.berth, cur.deep))
    elif issue == "berth" and ask and not cur.berth:
        cands.append(Package(cur.base, cur.title, cur.bonus, True, cur.deep))
    elif issue == "deepwater" and ask and not cur.deep:
        cands.append(Package(cur.base, cur.title, cur.bonus, cur.berth, True))
    return max(cands, key=lambda pk: works_npv(p, c, pk))


def aspiration(p: Params, c: Crab) -> float:
    """What the crab is holding out for: matching the outside offer, or a
    self-set target when there isn't one."""
    if c.has_outside:
        return outside_value(p, c)
    return 0.04 * c.salary * PVF * (0.4 + 0.9 * c.perf)


def _human_ask(c: Crab, issue: str):
    """A human's opening ask on one issue. Anchors high on money, asks for the
    non-cash items only if they actually matter to this crab."""
    m = weight_mult(c)
    if issue == "base":
        return 4 if c.has_outside else 3
    if issue == "bonus":
        return 2 if c.has_outside else 1
    return m[issue] > 0.7


# ------------------------------------------------------------------- arm A
def arm_sign(p: Params, c: Crab) -> dict:
    pk = opening_offer(p, c)
    return settle(p, c, pk, days=1.0, meetings=0)


# ------------------------------------------------------------------- arm B
def arm_slow(p: Params, c: Crab, engine_asks: bool = False,
             trace: list | None = None) -> dict:
    """SLOW TALKS. One issue per meeting, money first, nothing revisited.

    engine_asks=True is arm C: the crab's ask on each issue comes from the real
    `negotiate_turn` instead of a human anchor. Everything else is identical —
    same agenda, same calendar, same Works.
    """
    open_pk = opening_offer(p, c)
    cur = open_pk
    day = 0.0
    meetings = 0
    asp = aspiration(p, c)
    for k, issue in enumerate(AGENDA):
        if meetings >= p.max_meetings:
            break
        day += float(c.delays[k]) if p.clock else 0.0
        meetings += 1
        ask = (_engine_ask(p, c, cur, issue) if engine_asks
               else _human_ask(c, issue))
        nxt = _grant_single(p, c, cur, issue, ask)
        granted = nxt.key() != cur.key()
        if granted:
            day += approval_days(p, nxt, cur) - approval_days(p, cur, open_pk)
        if trace is not None:
            trace.append({"day": round(day, 1), "issue": issue,
                          "ask": _ask_label(issue, ask),
                          "granted": granted, "pkg": nxt.labels(),
                          "crab_value": round(crab_value(p, c, nxt)),
                          "works_cost": round(works_cost(p, c, nxt))})
        cur = nxt
        # the crab stops once it has what it came for
        if k >= 1 and crab_value(p, c, cur) >= asp:
            break
    return settle(p, c, cur, days=max(day, 1.0), meetings=meetings)


def _ask_label(issue, ask):
    if issue == "base":
        return BASE_LABELS[int(ask)]
    if issue == "bonus":
        return BONUS_LABELS[int(ask)]
    return "yes" if ask else "no"


def _engine_ask(p: Params, c: Crab, cur: Package, issue: str):
    """Arm C: the real single-issue engine, one issue at a time, in dollars."""
    from gametheory.negotiation.plain_terms import negotiate_turn

    if issue == "base":
        opts, idx = BASE_PCT, cur.base
        val = [c.salary * f * PVF for f in opts]
    elif issue == "bonus":
        opts, idx = BONUS_MO, cur.bonus
        val = [c.salary / 12.0 * mo for mo in opts]
    else:
        # binary issues: a single-issue price engine has nothing to say about a
        # yes/no term, so the crab asks for it iff it wants it. Registered as
        # part of arm C's definition, not a silent choice.
        return _human_ask(c, issue)
    # Denominated in 3-year total comp so every quantity is a positive dollar
    # amount, which is what the single-issue engine speaks. The crab is SELLING
    # its labour: it wants the high number.
    floor = c.salary * PVF
    on_table = floor + val[idx]
    target = floor + val[-1]
    if not (on_table < target):
        return idx
    res = negotiate_turn(side="sell", walk_away=float(on_table),
                         target=float(target),
                         counterparty_offers=[float(on_table)],
                         rounds_left=2, item=f"this {issue}")
    if res["action"] == "accept":
        return idx
    want = float(res.get("recommended_price") or on_table) - floor
    return int(np.argmin([abs(v - want) for v in val]))


# --------------------------------------------------- engine wiring (arms D-F)
def crab_issues(p: Params, c: Crab) -> list[dict]:
    """The five issues in the crab's own dollars. The Works' per-issue
    DIRECTION is given (anyone can guess it); its relative PRIORITIES across
    issues are not — inferring those is the product, so it is not bypassed."""
    v = lambda pk: crab_value(p, c, pk)                     # noqa: E731
    z = Package()
    return [
        {"name": "base", "options": list(BASE_LABELS),
         "my_utility": [v(Package(base=b)) for b in range(5)],
         "their_utility": [4.0, 3.0, 2.0, 1.0, 0.0]},
        {"name": "title", "options": list(TITLE_LABELS),
         "my_utility": [v(z), v(Package(title=True))],
         "their_utility": [1.0, 0.0]},
        {"name": "bonus", "options": list(BONUS_LABELS),
         "my_utility": [v(Package(bonus=b)) for b in range(3)],
         "their_utility": [2.0, 1.0, 0.0]},
        {"name": "berth", "options": list(BERTH_LABELS),
         "my_utility": [v(z), v(Package(berth=True))],
         "their_utility": [1.0, 0.0]},
        {"name": "deepwater", "options": list(DEEP_LABELS),
         "my_utility": [v(z), v(Package(deep=True))],
         "their_utility": [1.0, 0.0]},
    ]


def works_issues(p: Params, c: Crab) -> list[dict]:
    """The same five issues from the Works' side: its utility is minus its cost;
    the crab's direction is given, the crab's priorities are inferred."""
    k = lambda pk: -works_cost(p, c, pk)                     # noqa: E731
    z = Package()
    return [
        {"name": "base", "options": list(BASE_LABELS),
         "my_utility": [k(Package(base=b)) for b in range(5)],
         "their_utility": [0.0, 1.0, 2.0, 3.0, 4.0]},
        {"name": "title", "options": list(TITLE_LABELS),
         "my_utility": [k(z), k(Package(title=True))],
         "their_utility": [0.0, 1.0]},
        {"name": "bonus", "options": list(BONUS_LABELS),
         "my_utility": [k(Package(bonus=b)) for b in range(3)],
         "their_utility": [0.0, 1.0, 2.0]},
        {"name": "berth", "options": list(BERTH_LABELS),
         "my_utility": [k(z), k(Package(berth=True))],
         "their_utility": [0.0, 1.0]},
        {"name": "deepwater", "options": list(DEEP_LABELS),
         "my_utility": [k(z), k(Package(deep=True))],
         "their_utility": [0.0, 1.0]},
    ]


def _pkg_from_offer(off: dict) -> Package:
    return Package(base=BASE_LABELS.index(off.get("base", BASE_LABELS[0])),
                   title=(off.get("title") == TITLE_LABELS[1]),
                   bonus=BONUS_LABELS.index(off.get("bonus", BONUS_LABELS[0])),
                   berth=(off.get("berth") == BERTH_LABELS[1]),
                   deep=(off.get("deepwater") == DEEP_LABELS[1]))


def _offer_from_pkg(pk: Package) -> dict:
    return pk.labels()


def crab_batna_norm(p: Params, c: Crab) -> float:
    lo = crab_value(p, c, Package())
    hi = crab_value(p, c, Package(4, True, 2, True, True))
    ov = outside_value(p, c)
    if hi <= lo:
        return 0.5
    return float(np.clip((ov - lo) / (hi - lo), 0.0, 1.0))


def works_batna_norm(p: Params, c: Crab) -> float:
    """Losing the crab costs rho x salary; placed between the cheapest and the
    dearest package the Works could sign."""
    hi = 0.0
    lo = -works_cost(p, c, Package(3, True, 2, True, True))
    walk = -p.spec_rho(c.spec) * c.salary
    if hi <= lo:
        return 0.5
    return float(np.clip((walk - lo) / (hi - lo), 0.0, 1.0))


# ------------------------------------------------------------------- arm D
def arm_sitting_crab(p: Params, c: Crab, seed: int,
                     trace: list | None = None) -> dict:
    """ONE SITTING. The crab brings the engine; the whole package at once."""
    from gametheory.negotiation.bundle import negotiate_bundle

    open_pk = opening_offer(p, c)
    issues = crab_issues(p, c)
    prio = {k: float(w) for k, w in zip(ISSUES, c.w)}
    their_offers = [_offer_from_pkg(open_pk)]
    cur = open_pk
    rounds = 0
    for r in range(p.max_rounds):
        rounds = r + 1
        res = negotiate_bundle(issues=issues, their_offers=their_offers,
                               my_priorities=prio,
                               my_batna=crab_batna_norm(p, c),
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + r, rounds_left=p.max_rounds - r)
        if res["action"] == "accept":
            break
        if res["action"] in ("walk", "use_negotiate_turn"):
            break
        ask = _pkg_from_offer(res.get("recommended_offer") or {})
        if trace is not None:
            trace.append({"round": rounds, "actor": "crab",
                          "pkg": ask.labels(),
                          "crab_value": round(crab_value(p, c, ask)),
                          "works_cost": round(works_cost(p, c, ask)),
                          "logic": res.get("trade_logic"),
                          "inferred": res.get("inferred_their_priorities")})
        reply = works_best_reply(p, c, open_pk, crab_value(p, c, cur))
        if works_signs(p, c, ask, cur, reply):
            cur = ask                       # the Works signs it
            break
        if reply is None:
            break
        cur = reply
        their_offers.append(_offer_from_pkg(cur))
        if trace is not None:
            trace.append({"round": rounds, "actor": "works", "pkg": cur.labels(),
                          "crab_value": round(crab_value(p, c, cur)),
                          "works_cost": round(works_cost(p, c, cur))})
    days = 1.0 + approval_days(p, cur, open_pk)
    return settle(p, c, cur, days=days, meetings=1)


# ------------------------------------------------------------------- arm E
def arm_sitting_works(p: Params, c: Crab, seed: int) -> dict:
    """The WORKS brings the engine and OPENS with a package. (The rent study's
    K16 was nearly missed by letting the engine-armed side only reply.)"""
    from gametheory.negotiation.bundle import negotiate_bundle

    open_pk = opening_offer(p, c)
    issues = works_issues(p, c)
    cost_max = {"base": works_cost(p, c, Package(base=4)),
                "title": works_cost(p, c, Package(title=True)),
                "bonus": works_cost(p, c, Package(bonus=2)),
                "berth": works_cost(p, c, Package(berth=True)),
                "deepwater": works_cost(p, c, Package(deep=True))}
    tot = sum(cost_max.values()) or 1.0
    prio = {k: v / tot for k, v in cost_max.items()}
    their_offers = [_offer_from_pkg(Package(4, True, 2, True, True))]  # the ask
    cur = open_pk
    asp = aspiration(p, c)
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=their_offers,
                               my_priorities=prio,
                               my_batna=works_batna_norm(p, c),
                               their_batna_estimate=p.their_batna_estimate,
                               seed=seed + 500 + r,
                               rounds_left=p.max_rounds - r)
        if res["action"] in ("accept", "walk", "use_negotiate_turn"):
            break
        proposal = _pkg_from_offer(res.get("recommended_offer") or {})
        # the Works will not sign something worse for itself than holding firm
        if works_npv(p, c, proposal) < works_npv(p, c, cur):
            break
        cur = proposal
        if crab_value(p, c, cur) >= asp:
            break
        # the crab pushes back with a human counter-ask on its top issue
        top = max(ISSUES, key=lambda k: weight_mult(c)[k])
        their_offers.append(_offer_from_pkg(
            _grant_single(p, c, cur, top, _human_ask(c, top))))
    days = 1.0 + approval_days(p, cur, open_pk)
    return settle(p, c, cur, days=days, meetings=1)


# ------------------------------------------------------------------- arm F
def arm_sitting_both(p: Params, c: Crab, seed: int) -> dict:
    """Both sides on the engine. Alternating packages; either may close."""
    from gametheory.negotiation.bundle import negotiate_bundle

    open_pk = opening_offer(p, c)
    c_iss, y_iss = crab_issues(p, c), works_issues(p, c)
    c_prio = {k: float(w) for k, w in zip(ISSUES, c.w)}
    cost_max = {"base": works_cost(p, c, Package(base=4)),
                "title": works_cost(p, c, Package(title=True)),
                "bonus": works_cost(p, c, Package(bonus=2)),
                "berth": works_cost(p, c, Package(berth=True)),
                "deepwater": works_cost(p, c, Package(deep=True))}
    tot = sum(cost_max.values()) or 1.0
    y_prio = {k: v / tot for k, v in cost_max.items()}
    crab_saw = [_offer_from_pkg(open_pk)]
    works_saw = [_offer_from_pkg(Package(4, True, 2, True, True))]
    cur = open_pk
    for r in range(p.max_rounds):
        rc = negotiate_bundle(issues=c_iss, their_offers=crab_saw,
                              my_priorities=c_prio,
                              my_batna=crab_batna_norm(p, c),
                              their_batna_estimate=p.their_batna_estimate,
                              seed=seed + r, rounds_left=p.max_rounds - r)
        if rc["action"] == "accept":
            break
        ask = _pkg_from_offer(rc.get("recommended_offer") or {}) \
            if rc["action"] == "counter" else cur
        if works_signs(p, c, ask, cur,
                      works_best_reply(p, c, open_pk, crab_value(p, c, cur))):
            cur = ask
            break
        works_saw.append(_offer_from_pkg(ask))
        ry = negotiate_bundle(issues=y_iss, their_offers=works_saw,
                              my_priorities=y_prio,
                              my_batna=works_batna_norm(p, c),
                              their_batna_estimate=p.their_batna_estimate,
                              seed=seed + 500 + r, rounds_left=p.max_rounds - r)
        if ry["action"] in ("accept", "walk", "use_negotiate_turn"):
            break
        counter = _pkg_from_offer(ry.get("recommended_offer") or {})
        if works_npv(p, c, counter) < works_npv(p, c, cur):
            break
        cur = counter
        crab_saw.append(_offer_from_pkg(cur))
        if crab_value(p, c, cur) >= aspiration(p, c):
            break
    days = 1.0 + approval_days(p, cur, open_pk)
    return settle(p, c, cur, days=days, meetings=1)


ARMS = {
    "A_sign": lambda p, c, s: arm_sign(p, c),
    "B_slow": lambda p, c, s: arm_slow(p, c, engine_asks=False),
    "C_slow_engine": lambda p, c, s: arm_slow(p, c, engine_asks=True),
    "D_sitting_crab": lambda p, c, s: arm_sitting_crab(p, c, s),
    "E_sitting_works": lambda p, c, s: arm_sitting_works(p, c, s),
    "F_sitting_both": lambda p, c, s: arm_sitting_both(p, c, s),
}

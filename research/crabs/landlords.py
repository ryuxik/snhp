"""Landlord types (PREREG AMENDMENT 1 §A1.1).

Three types, crossed with the Phase-1 arms. They share the instrument
machinery, the departure model and the accounting; they differ only in how they
set the opening offer and how they answer a counter.

  INSTITUTIONAL  200+ habitats. Full revenue management = the Phase-1
                 `StationDP`. Grounded: RealPage-class RM explicitly models turn
                 cost, vacancy loss, elasticity and tenure.

  MEDIUM         20-75 habitats. Comp-aware but heuristic.
                 *** THIS POLICY IS OUR INVENTION. There is no published
                 regional-operator renewal policy to anchor it to. Every result
                 involving MEDIUM carries that caveat. ***

  MOM-AND-POP    1-10 habitats. Rarely raises; when it does, rarely concedes;
                 weights tenant reliability heavily. Grounded: 18.0% hold a
                 strict no-increase policy, and ~90% offer no concessions even
                 with longer vacancies (TurboTenant, ~2,000 landlords).

The paradox under test: mom-and-pops may be the best landlord to HAVE and the
worst to NEGOTIATE with, so the tool may be worth most against the most
sophisticated counterparty. K5/K6 cover both directions.
"""
from __future__ import annotations

import numpy as np

from crabs.policies import RANKED_LADDER, StationDP, crab_ladder
from crabs.world import (ASK_PRICE, FEES, NEVER_ASK, ONE_TIME, RENT, TERM,
                         U_MPGRANT, U_PATIENCE, U_SUB, Params)

INSTITUTIONAL, MEDIUM, MOM_AND_POP = "institutional", "medium", "mom"

# habitat counts and station counts per type. Station counts are set so every
# cell clears PREREG's >=200 station-years while keeping habitat-years within an
# order of magnitude of each other. Station SIZE is left at its real value
# because it is what makes the arm-F grapevine informative or not.
TYPE_GEOMETRY = {
    INSTITUTIONAL: dict(units=200, stations=60),    # 240 st-yr, 48k habitat-yr
    MEDIUM:        dict(units=40, stations=120),    # 480 st-yr, 19.2k
    MOM_AND_POP:   dict(units=5, stations=500),     # 2000 st-yr, 10k
}


class MediumLandlord(StationDP):
    """*** OUR INVENTION -- no empirical anchor. ***

    Anchors half on the sitting rent plus a fixed target increase and half on
    market plus a comp premium, bounded by a maximum increase and a reluctance
    to cut. Answers a counter with one simple rule: grant it if what is being
    asked for is worth less than a fixed fraction of the turnover it would
    avoid, and refuse headline rate cuts outright, because "we don't lower the
    rate" is the one rule of thumb every operator has.
    """
    target_inc = 0.05
    comp_premium = 0.05
    max_inc = 0.10
    max_cut = 0.03
    conc_budget = 0.5          # of (turn cost + vacancy), in months
    refuses_rate_cuts = True

    def __init__(self, p, c_nodes, weights, **kw):
        kw.pop("solve", None)
        kw.pop("adaptive", None)
        kw.pop("share", None)
        super().__init__(p, c_nodes, weights, solve=False)

    def offer(self, r, j) -> float:
        r = float(r)
        q = 0.5 * r * (1.0 + self.target_inc) + 0.5 * (1.0 + self.comp_premium)
        return float(min(max(q, r * (1.0 - self.max_cut)),
                         r * (1.0 + self.max_inc)))

    def _budget(self):
        return self.conc_budget * (self.p.turn_cost + self.p.vacancy)

    def negotiate(self, p, crab, q, r, j, u, g_obs, asker_strategy,
                  tmul=None, vmul=1.0):
        if crab.strategy == NEVER_ASK:
            return None, 0, False, None
        ladder = (((RENT, 1.0),) if crab.strategy == ASK_PRICE
                  else crab_ladder(crab))
        budget = self._budget() * (1.0 if tmul is None else tmul)
        rounds, asked = 0, False
        for kind, size in ladder:
            if kind == FEES and crab.fee_years > 0:
                continue
            size = size * getattr(crab, "ask_scale", 1.0)
            if size <= 0.0 or self.crab_value(p, q, (kind, size), g_obs) <= 0.0:
                continue
            if rounds >= 1 and u[U_PATIENCE + min(rounds - 1, 3)] > p.p_continue:
                break
            rounds += 1
            asked = True
            if kind == RENT and self.refuses_rate_cuts:
                if u[U_SUB + min(rounds - 1, 3)] < p.p_substitute:
                    alt = (ONE_TIME, min(size, 1.0))
                    if self.crab_value(p, q, alt, g_obs) <= budget:
                        return alt, rounds, True, ONE_TIME
                continue
            for f in p.grant_menu:
                var = (kind, size * f)
                cv = self.crab_value(p, q, var, g_obs)
                if 0.0 < cv <= budget:
                    return var, rounds, True, kind
        return None, rounds, asked, None


class MomAndPopLandlord(StationDP):
    """Rarely raises, rarely concedes, weights reliability heavily.

    `no_increase` is drawn per station at the documented 18.0% rate. The rest
    push toward market slowly and never above it -- which is exactly why a
    mom-and-pop is the best landlord to have. The grant rate is ~10% (the
    documented ~90% who offer no concessions), rising with tenure because
    reliability is what they say they are protecting.
    """
    push = 0.03
    no_increase_rate = 0.180
    grant_base = 0.06
    grant_per_year = 0.03
    grant_cap = 0.30

    def __init__(self, p, c_nodes, weights, **kw):
        kw.pop("solve", None)
        kw.pop("adaptive", None)
        kw.pop("share", None)
        super().__init__(p, c_nodes, weights, solve=False)
        self.no_increase = False        # set per station by the runner

    def offer(self, r, j) -> float:
        r = float(r)
        if self.no_increase or r >= 1.0:
            return r                    # holds flat rather than chase market
        return float(min(r * (1.0 + self.push), 1.0))

    def grant_prob(self, j) -> float:
        return min(self.grant_cap, self.grant_base + self.grant_per_year * j)

    def negotiate(self, p, crab, q, r, j, u, g_obs, asker_strategy,
                  tmul=None, vmul=1.0):
        if crab.strategy == NEVER_ASK:
            return None, 0, False, None
        ladder = (((RENT, 1.0),) if crab.strategy == ASK_PRICE
                  else crab_ladder(crab))
        for kind, size in ladder:
            if kind == FEES and crab.fee_years > 0:
                continue
            size = size * getattr(crab, "ask_scale", 1.0)
            if size <= 0.0 or self.crab_value(p, q, (kind, size), g_obs) <= 0.0:
                continue
            # one ask, one answer -- they do not run a negotiation
            if u[U_MPGRANT] < self.grant_prob(j):
                kk = ONE_TIME if kind == RENT else kind
                var = (kk, min(size, 1.0) * 0.3)
                if self.crab_value(p, q, var, g_obs) > 0.0:
                    return var, 1, True, kk
            return None, 1, True, None
        return None, 0, False, None


def make_landlord(kind: str, p: Params, c_nodes, weights, share: float = 0.0,
                  adaptive: bool = False):
    if kind == INSTITUTIONAL:
        return StationDP(p, c_nodes, weights, share=share, adaptive=adaptive)
    if kind == MEDIUM:
        return MediumLandlord(p, c_nodes, weights)
    if kind == MOM_AND_POP:
        return MomAndPopLandlord(p, c_nodes, weights)
    raise ValueError(kind)

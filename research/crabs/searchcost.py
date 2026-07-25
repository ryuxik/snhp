"""AMENDMENT 8 — switching cost as an OUTPUT of the search process.

`world.py` draws each crab's switching cost from a lognormal with
`move_med = 3.6` months ($7,200), whose SPEC §4 basis is *"calibrated to
observed elasticity"*. A7's ablation then found it is the dominant variable in
renewal pricing (+13.4pp / -5.2pp, against +3.2pp for deleting the landlord's
entire cost of losing a tenant). Tuned to reproduce elasticity, drives the push,
and the push is what we reported.

`market.py` already runs a search pool with viewings, applications and
matching, and already prices `SEARCH_COST` and `APP_COST` — about $660 of
modelled search sitting beside a separately drawn $7,200, never connected.

This module connects them. A crab that leaves enters the pool, engages a
listing a month, may fail to clear the bargaining zone, and eventually matches
or gives up. Its switching cost is the REALISED cost of that, plus a physical
move term. Attachment is the only genuinely psychological term and stays where
it was, in `world.attach`.

    c = SPELL_COST                          once, on entering the market
      + attempts x VIEW_COST                each listing seriously engaged
      + months   x TIME_COST                time spent mid-search
      + MOVE_PHYSICAL                       movers, hookups, time off
      + broker   x BROKER_FEE               in broker-fee markets
      + overran  x (HOLDOVER + EMERGENCY)   if the search outran the notice window

A rejection needs no constant of its own: a failed attempt simply means another
month in the pool and another engaged listing, both of which the loop already
charges. That is A8.2's `P(rejection) x redo cost`, priced by the dynamics
rather than by a parameter.

DESIGN-PRINCIPLES compliance, stated before running:

  C. Every constant below carries a source UPSTREAM of the renewal push. Two are
     reused verbatim from market.py's pre-existing declarations; two are reused
     from AMENDMENT 6a; TWO ARE NEW and are swept. None was chosen by looking at
     the derived median — the first run of this file is the first time anyone
     saw what it produces. The value that would make K27 pass is 3.6 months and
     it appears nowhere in this file.
  D. The distribution is reported over EVERY crab that entered the pool, not
     only over those that matched. Searchers who give up have the longest and
     most expensive searches, so a matched-only median is a survivorship
     statistic — artefact #5's exact shape, and the one this study already made.
  B. The derived cost is a property of the crab's own search. It is never
     shown to the station, which continues to hold only the population
     distribution.
"""
from __future__ import annotations

import numpy as np

# --- REUSED, already declared in market.py before any A8 output existed ------
from crabs.market import (APP_COST, EMERGENCY_MONTHS, HOLDOVER_MONTHS,
                          NOTICE_WINDOW, SEARCH_COST)

VIEW_COST = APP_COST        # 0.08 mo ($160). market.py:43, "switching between
                            # listings while already moving". One seriously
                            # engaged listing: the viewing, the application, the
                            # fee. UPSTREAM (declared before A8).
SPELL_COST = SEARCH_COST    # 0.25 mo ($500). market.py:42, "viewings,
                            # applications, time" — the fixed overhead of
                            # deciding to move at all. UPSTREAM.
OVERRUN_COST = HOLDOVER_MONTHS + EMERGENCY_MONTHS   # 2.0 mo. A6a, declared for
                            # exactly this event: crossing lease expiry unhoused
                            # costs holdover penalty rent plus an emergency move.

# --- NEW in A8. Both swept; neither is a function of any elasticity fact. ----
MOVE_PHYSICAL = 1.00        # months ($2,000). A local move of a 1-2 bedroom with
                            # professional movers is commonly quoted $1,000-2,000
                            # in the US, before utility connection, renter's
                            # insurance and time off work. UPSTREAM (moving-trade
                            # quotes), and upstream of rent-setting in particular:
                            # a mover's hourly rate is not a function of how hard
                            # landlords push at renewal.
TIME_COST = 0.15            # months of rent per month spent searching ($300/mo).
                            # ~10 hours a month of search at the ACS renter median
                            # household income already used in demographics.py
                            # ($75,000 -> ~$36/h full-time-equivalent). LABEL:
                            # ANCHORED wage, INVENTED hours. Swept.
BROKER_FEE = 1.00           # months. One month's rent, the standard broker fee
                            # where one is charged. UPSTREAM.
BROKER_SHARE = 0.15         # share of searches in a broker-fee market. LABEL:
                            # INVENTED. Swept, and it moves the mean far more
                            # than the median by construction.

SWEEPS = {
    "MOVE_PHYSICAL": (0.0, 0.5, 1.0, 1.5, 2.0),
    "TIME_COST": (0.0, 0.075, 0.15, 0.30),
    "BROKER_SHARE": (0.0, 0.15, 0.30, 1.0),
}


def derived_cost(attempts: float, months: float, broker: bool,
                 move_physical: float = MOVE_PHYSICAL,
                 time_cost: float = TIME_COST,
                 broker_fee: float = BROKER_FEE) -> float:
    """Realised switching cost of ONE search, in months of market rent.

    `attempts` listings seriously engaged, `months` spent in the pool. A search
    that outran the notice window pays the A6a overrun, because the tenant is
    then out of its old habitat without having secured the next one."""
    c = (SPELL_COST
         + attempts * VIEW_COST
         + months * time_cost
         + move_physical
         + (broker_fee if broker else 0.0))
    if months > NOTICE_WINDOW:
        c += OVERRUN_COST
    return float(c)


def fit_lognormal(costs) -> tuple:
    """(median, sigma_log) of the lognormal that best matches a realised
    distribution, so the derived object can be dropped into `Params.move_med`
    and `Params.move_sigma` and A7 re-run with ONE knob changed.

    Fitted on logs, so the median is the geometric centre — the same object
    `move_med` is, rather than a mean that a fat tail would drag."""
    a = np.asarray([c for c in costs if c > 0.0], dtype=float)
    if a.size == 0:                                   # pragma: no cover
        return float("nan"), float("nan")
    lg = np.log(a)
    return float(np.exp(lg.mean())), float(lg.std(ddof=1))


def summary(costs, label="") -> dict:
    a = np.asarray(list(costs), dtype=float)
    med, sig = fit_lognormal(a)
    return dict(
        label=label, n=int(a.size),
        mean=float(a.mean()), median=float(np.median(a)),
        p10=float(np.percentile(a, 10)), p25=float(np.percentile(a, 25)),
        p75=float(np.percentile(a, 75)), p90=float(np.percentile(a, 90)),
        p99=float(np.percentile(a, 99)), max=float(a.max()), min=float(a.min()),
        sd=float(a.std()), fit_median=med, fit_sigma=sig,
        dollars_median=float(np.median(a)) * 2000.0,
    )


# --- K27, declared in PREREG AMENDMENT 8 §A8.5 before this file was written ---
K27_LO, K27_HI = 1.8, 7.2


def k27(median_months: float) -> bool:
    """FIRES (i.e. search does NOT generate the calibrated switching cost) if
    the derived median lands outside a factor of two either side of 3.6."""
    return not (K27_LO <= median_months <= K27_HI)

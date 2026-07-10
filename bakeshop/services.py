"""The florist SERVICES tier — the REAL florist (CRITICAL-ANALYSIS §9 follow-up).

The §9 boundary ("posted clearance beats bilateral negotiation") was found on
an IMPOVERISHED florist modeled as pure perishable walk-in clearance: linear
decay, weekly resupply, everything must move. That is the florist's ANTI-lever
for our mechanism — posted rationing wins where TIME is the only variable and
buyers are interchangeable. But that walk-in slice is a minority of a real
florist's revenue. The money is in higher-margin, heterogeneous, multi-issue
lines — exactly the regimes bilateral negotiation wins everywhere else in our
results. This module adds four such lines and re-tests posted vs bilateral on
each, so the honest claim becomes "posted wins the clearance slice, bilateral
wins the services slice" — NOT "florists don't benefit from SNHP."

Four lines, each its own paired mechanism test (posted vs bilateral):
  1. ARRANGEMENT — flowers × style × size, a real multi-issue negotiation with
     substantial labor margin ($85 wrapped vs $125 arranged — the arrangement
     IS the margin). Heterogeneous buyer taste → logrolling home turf.
  2. DELIVERY    — a time-window logistics lever (the boba pickup-slot lever):
     buyers value windows differently; the shop has route-density capacity.
  3. EVENT       — weddings/funerals: advance-booked, high-value, wide-WTP,
     multi-issue (scope × palette) — bilateral quoting's textbook case.
  4. ATTACH      — chocolates/card/vase at the point of sale (suggest/1: a
     COMPLEMENT to the flower purchase, not a substitute).

Rigor (binding, inherited from the walk-in grid):
  * PAIRED SEEDS keyed on IDENTITY never policy: every buyer's private
    valuation depends only on (master_seed, line, day, k) — both arms face the
    byte-identical buyer stream. Divergence is the treatment effect alone.
  * The POSTED arm gets its BEST SHOT (the §2 meta-pattern): its menu prices
    (or flat fee, or package tiers, or shelf price) are tuned to the profit-max
    global markup against the true buyer population — a competent sticker, not
    a strawman. Bilateral must beat THAT.
  * DISCOUNT-ONLY: a bilateral quote never prices above the config's reference
    list (the posted sticker) — it wins by config-efficiency (logrolling) and
    by converting buyers the posted menu loses, never by charging over list.
  * Three arms so the win is non-vacuous, mirroring the walk-in ablations:
      posted     — the profit-max posted menu / fee / packages / shelf.
      nego-pure  — bilateral ONLY, a declined quote is a LOST sale (the
                   mechanism standing on its own — this CAN lose, and on the
                   walk-in clearance slice it does; this is the real test).
      nego       — bilateral WITH the posted menu as fallback ("never worse UX
                   than the culture", inherited from nego/1) — the deployable
                   broker, which contains posted as a special case.
  * CIs on every delta (95% t on 5-day block means, the walk-in methodology);
    NO win claim where the CI includes zero.

Same modeling caveat as nego/1 (flagged, not hidden): the bilateral engine
computes the Nash outcome from the buyer's value function — truthful disclosure
/ vend-P1 attestation assumed; the liar tax is measured elsewhere.

Reproduce:  python3 -m bakeshop.services            (writes bakeshop/services.json)
            python3 -m bakeshop.run --services      (same, via the main runner)
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field

import numpy as np

from bakeshop import calibration as cal
from bakeshop.world import substream

SERVICES_VERSION = 1
_ABS = cal.SERVICES_MIN_GAIN_ABS
_FRAC = cal.SERVICES_MIN_GAIN_FRAC


# ── the shared bilateral primitive: Nash split of price for a fixed config ──
def nash_price(value: float, cost: float, d_buyer: float, d_shop: float,
               ceiling: float, buffer: float) -> float | None:
    """Symmetric Nash bargaining over the PRICE of one chosen configuration,
    in dollars. Both sides' no-deal (disagreement) utilities are given; the
    trade splits the surplus created OVER those disagreements. Returns the
    price, or None if no price clears both sides plus the shop's buffer.

      buyer gain gb = (value − p) − d_buyer      (must be ≥ 0)
      shop  gain gs = (p − cost) − d_shop        (must be ≥ buffer)
    Symmetric Nash maximizes gs·gb → interior midpoint
      p* = (cost + d_shop + value − d_buyer) / 2,
    then clamped to the discount-only ceiling (never over list) and to the
    shop's floor (never below cost + d_shop)."""
    joint = value - cost - d_buyer - d_shop
    if joint <= 0:
        return None
    p = 0.5 * (cost + d_shop + value - d_buyer)
    p = min(p, ceiling)                     # discount-only: never over list
    floor = cost + d_shop + buffer          # shop must clear its buffer
    if p < floor:
        p = floor                           # try to meet the buffer …
    if p > ceiling + 1e-9:
        return None                         # … but not by exceeding list
    if p > value - d_buyer + 1e-9:
        return None                         # buyer would be worse than no-deal
    if (p - cost) - d_shop < buffer - 1e-9:
        return None
    return round(p, 2)


# ── generic config-space line (arrangement, event) ──────────────────────────
@dataclass(frozen=True)
class Config:
    attrs: tuple                  # (level per issue)
    cost: float                   # shop's marginal cost of this config
    ref_list: float               # reference retail sticker (posted price base
                                  # and the discount-only ceiling)


@dataclass
class Buyer:
    values: tuple                 # buyer's $ value for each config (by index)
    outside: float                # config-independent outside-option surplus


def _paired_block_ci(diffs: list[float], block: int = 5) -> dict:
    """Mean paired difference, 95% t-interval on `block`-day means — the exact
    walk-in-grid methodology (copied from run.paired_ci) so services CIs and
    walk-in CIs are comparable. Overnight/serial dependence across days is why
    the blocking widens the interval honestly."""
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        n_blocks = len(d) // block
        d = d[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)],
            "n": n, "block": block}


# ════════════════════════════════════════════════════════════════════════════
#  LINE 1 — ARRANGEMENT (multi-issue: grade × style × size)
# ════════════════════════════════════════════════════════════════════════════
def _arr_configs() -> list[Config]:
    grades = ("standard", "premium")
    styles = ("wrap", "hand_tie", "vase")
    sizes = ("small", "medium", "large")
    out = []
    for g, st, sz in itertools.product(grades, styles, sizes):
        wholesale = cal.ARR_SIZE_WHOLESALE[sz] * cal.ARR_GRADE_MULT[g]
        labor = cal.ARR_STYLE_LABOR[st]
        vessel = cal.ARR_STYLE_VESSEL[st]
        cost = wholesale + labor + vessel
        ref = (wholesale * cal.ARR_FRESH_MARKUP + vessel * cal.ARR_HARD_MARKUP
               + labor * cal.ARR_LABOR_MARKUP)
        out.append(Config((g, st, sz), round(cost, 2), round(ref, 2)))
    return out


ARR_CONFIGS = _arr_configs()
ARR_MENU_IDX = tuple(i for i, c in enumerate(ARR_CONFIGS)
                     if c.attrs in cal.ARR_MENU)


def arr_buyer(master_seed: int, day: int, k: int) -> Buyer:
    """A buyer with a private flower budget and private per-issue importance
    weights: value(config) = budget × weighted-average desirability, the
    weights tilting which attributes THIS buyer cares about (premium blooms vs
    a big arrangement vs a vase presentation). The weight heterogeneity is the
    scarce information bilateral discovery exploits (a buyer who loves premium
    blooms but not vases → premium-in-a-wrap, a logroll the rigid menu can't
    price)."""
    rng = np.random.default_rng(substream(master_seed, cal.SERVICES_SEED_SALT,
                                          "arrangement", day, k))
    budget = float(rng.lognormal(math.log(cal.ARR_BUDGET_MU),
                                 cal.ARR_BUDGET_SIGMA))
    wg = float(rng.lognormal(0.0, cal.ARR_WEIGHT_SIGMA))
    ws = float(rng.lognormal(0.0, cal.ARR_WEIGHT_SIGMA))
    wz = float(rng.lognormal(0.0, cal.ARR_WEIGHT_SIGMA))
    wsum = wg + ws + wz
    values = []
    for c in ARR_CONFIGS:
        g, st, sz = c.attrs
        util = (wg * cal.ARR_GRADE_SCORE[g] + ws * cal.ARR_STYLE_SCORE[st]
                + wz * cal.ARR_SIZE_SCORE[sz]) / wsum
        values.append(budget * util)
    # competitive outside: the buyer can get the SAME config across the street
    # at ARR_OUTSIDE_MARKUP × ref_list, less a small walk hassle — the outside
    # surplus scales with the buyer's own value, so demand is elastic.
    walk = float(rng.uniform(*cal.ARR_WALK))
    outside = max(0.0, max(v - cal.ARR_OUTSIDE_MARKUP * c.ref_list
                           for v, c in zip(values, ARR_CONFIGS)) - walk)
    return Buyer(tuple(values), outside)


# ════════════════════════════════════════════════════════════════════════════
#  LINE 3 — EVENT PRE-ORDERS (weddings / funerals: scope × palette)
# ════════════════════════════════════════════════════════════════════════════
def _event_configs(scopes, cost_by_scope, complete_by_scope):
    out = []
    for scope in scopes:
        for pal in ("standard", "premium"):
            cost = cost_by_scope[scope] * cal.EVENT_PALETTE_COST[pal]
            ref = cost * cal.EVENT_MARKUP
            out.append(Config((scope, pal), round(cost, 2), round(ref, 2)))
    return out


EVENT_WED_CONFIGS = _event_configs(cal.EVENT_WED_SCOPES, cal.EVENT_WED_COST,
                                   cal.EVENT_WED_COMPLETE)
EVENT_FUN_CONFIGS = _event_configs(cal.EVENT_FUN_SCOPES, cal.EVENT_FUN_COST,
                                   cal.EVENT_FUN_COMPLETE)
EVENT_WED_MENU_IDX = tuple(i for i, c in enumerate(EVENT_WED_CONFIGS)
                           if c.attrs in cal.EVENT_WED_MENU)
EVENT_FUN_MENU_IDX = tuple(i for i, c in enumerate(EVENT_FUN_CONFIGS)
                           if c.attrs in cal.EVENT_FUN_MENU)


def event_booking(master_seed: int, day: int, k: int):
    """One advance booking: a wedding or a funeral, with a private budget
    (WTP for the full-grand event) and a private taste for premium blooms.
    value(scope, palette) = budget × completeness(scope) × palette_taste — a
    high-budget couple values the grand scope, a constrained family the basket;
    the WIDE budget dispersion ($3k…$25k weddings) is what fixed package prices
    cannot track and bespoke quoting can (the textbook bilateral case)."""
    rng = np.random.default_rng(substream(master_seed, cal.SERVICES_SEED_SALT,
                                          "event", day, k))
    wedding = rng.random() < cal.EVENT_WEDDING_PROB
    if wedding:
        configs, complete = EVENT_WED_CONFIGS, cal.EVENT_WED_COMPLETE
        menu_idx = EVENT_WED_MENU_IDX
        budget = float(rng.lognormal(math.log(cal.EVENT_WED_BUDGET_MU),
                                     cal.EVENT_WED_BUDGET_SIGMA))
    else:
        configs, complete = EVENT_FUN_CONFIGS, cal.EVENT_FUN_COMPLETE
        menu_idx = EVENT_FUN_MENU_IDX
        budget = float(rng.lognormal(math.log(cal.EVENT_FUN_BUDGET_MU),
                                     cal.EVENT_FUN_BUDGET_SIGMA))
    pal_taste = float(rng.lognormal(0.0, cal.EVENT_PALETTE_TASTE_SIGMA))
    values = []
    for c in configs:
        scope, pal = c.attrs
        pv = 1.0 + (cal.EVENT_PALETTE_MULT[pal] - 1.0) * pal_taste
        values.append(budget * complete[scope] * pv)
    # competitive outside: another event florist / DIY at a markup — keeps the
    # posted package markup interior (couples/families shop around).
    outside = max(0.0, max(v - cal.EVENT_OUTSIDE_MARKUP * c.ref_list
                           for v, c in zip(values, configs)))
    return configs, menu_idx, Buyer(tuple(values), outside)


# ── posted best-shot: one global markup knob, profit-maxed on the population ──
def _optimize_menu_markup(configs, menu_idx, buyer_iter, n_sample=6000):
    """Give the posted arm its best shot: scale ALL listed prices by a single
    global markup λ (prices = λ × ref_list) and pick the λ that maximizes the
    shop's expected profit against a large synthetic buyer sample. A competent
    sticker (the §2 meta-pattern: disclosure only beats inference if inference
    got its best shot), not a strawman. Deterministic in the sample seed."""
    sample = list(itertools.islice(buyer_iter, n_sample))
    best_lam, best_profit = 1.0, -1e18
    for g in range(61):
        lam = 0.7 + 0.9 * g / 60          # λ ∈ [0.7, 1.6], fine grid
        profit = 0.0
        for b in sample:
            best_s, best_c = 0.0, None
            for i in menu_idx:
                c = configs[i]
                p = lam * c.ref_list
                s = b.values[i] - p
                if s > best_s and s >= b.outside:
                    best_s, best_c = s, (p, c.cost)
            if best_c is not None:
                profit += best_c[0] - best_c[1]
        if profit > best_profit:
            best_profit, best_lam = profit, lam
    return best_lam


def _posted_choice(configs, menu_idx, lam, buyer):
    """The posted arm's outcome for one buyer: pick the listed config with the
    highest positive surplus that also beats the outside option. Returns
    (price, cost, config_index) or None (walk)."""
    best_s, out = 0.0, None
    for i in menu_idx:
        c = configs[i]
        p = lam * c.ref_list
        s = buyer.values[i] - p
        if s > best_s and s >= buyer.outside:
            best_s, out = s, (round(p, 2), c.cost, i)
    return out


def _nego_choice(configs, menu_idx, lam, buyer, *, pure: bool):
    """The bilateral arm's outcome for one buyer. Pick the EFFICIENT config
    (argmax value − cost over the WHOLE space — the logroll), Nash-price it
    against the buyer's honest disagreement (their best posted-menu surplus, or
    the outside option), with the shop's disagreement pinned to the profit it
    would ALREADY have earned from that buyer under the menu (so bilateral
    earns only on CREATED surplus, never on margin the shop already had). If no
    quote clears: nego falls back to the posted menu ("never worse UX than the
    culture"); nego-pure takes the lost sale. Returns (price, cost, idx, kind)
    or None."""
    posted = _posted_choice(configs, menu_idx, lam, buyer)
    d_buyer = 0.0
    d_shop = 0.0
    if posted is not None:
        d_buyer = buyer.values[posted[2]] - posted[0]   # buyer's menu surplus
        d_shop = posted[0] - posted[1]                  # shop's menu profit
    d_buyer = max(d_buyer, buyer.outside, 0.0)
    # efficient config over the whole space
    eff = max(range(len(configs)),
              key=lambda i: buyer.values[i] - configs[i].cost)
    c = configs[eff]
    buffer = max(_ABS, _FRAC * c.ref_list)
    # discount-only ceiling = the shop's OWN posted sticker for this config
    # (λ × ref_list): a bilateral quote never charges more than the menu price.
    ceiling = lam * c.ref_list
    p = nash_price(buyer.values[eff], c.cost, d_buyer, d_shop, ceiling, buffer)
    if p is not None:
        return (p, c.cost, eff, "nego")
    if pure:
        return None
    if posted is not None:
        return (posted[0], posted[1], posted[2], "fallback")
    return None


# ════════════════════════════════════════════════════════════════════════════
#  LINE 2 — DELIVERY (time-window lever; route density is the capacity)
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class DeliveryBuyer:
    convenience: float            # $-value of having it delivered (at home win)
    pref: str                     # preferred window
    penalties: dict               # convenience multiplier per window
    outside: float


def delivery_buyer(master_seed: int, day: int, k: int) -> DeliveryBuyer:
    """A delivery order. Convenience = $-value of not picking up. Tight buyers
    have one preferred window and their convenience is discounted in others;
    flexible buyers value every window ≈ equally (they concede the window
    cheaply — the logroll: window timing is cheap to them, dear to the shop's
    routing)."""
    rng = np.random.default_rng(substream(master_seed, cal.SERVICES_SEED_SALT,
                                          "delivery", day, k))
    conv = float(rng.lognormal(math.log(cal.DELIVERY_CONVENIENCE_MU),
                               cal.DELIVERY_CONVENIENCE_SIGMA))
    windows = [w for w in cal.DELIVERY_WINDOWS if w != "flexible"]
    tight = rng.random() < cal.DELIVERY_TIGHT_PROB
    pref = windows[int(rng.integers(len(windows)))]
    penalties = {}
    for w in cal.DELIVERY_WINDOWS:
        if not tight:
            penalties[w] = float(rng.lognormal(-cal.DELIVERY_FLEX_SIGMA ** 2 / 2,
                                               cal.DELIVERY_FLEX_SIGMA))
        elif w == pref or w == "flexible":
            penalties[w] = 1.0 if w == pref else cal.DELIVERY_OFFWINDOW_PENALTY
        else:
            penalties[w] = cal.DELIVERY_OFFWINDOW_PENALTY
    outside = 0.0
    return DeliveryBuyer(conv, pref, penalties, outside)


def _delivery_cost(window: str, window_counts: dict) -> float:
    """Marginal cost of one delivery in `window` given how many are ALREADY
    routed there today: base minus a capped per-order route-density saving."""
    saving = min(cal.DELIVERY_DENSITY_CAP,
                 cal.DELIVERY_DENSITY_SAVING * window_counts.get(window, 0))
    return cal.DELIVERY_BASE_COST - saving


def _optimize_flat_fee(master_seed, days, rate, n_sample=8000):
    """Posted best shot for delivery: the single profit-max FLAT fee (the
    posted arm can't see a buyer's flexibility, so it charges one fee and books
    the buyer's preferred window). Density is realized at that fee."""
    # sample buyers across a handful of days for the fee optimization
    buyers = []
    d = 0
    while len(buyers) < n_sample:
        rng = np.random.default_rng(substream(master_seed, "feeopt", d))
        n = int(rng.poisson(rate))
        for k in range(n):
            buyers.append(delivery_buyer(master_seed, 10 ** 6 + d, k))
        d += 1
    best_fee, best_profit = cal.DELIVERY_REF_FEE, -1e18
    for g in range(41):
        fee = 8.0 + 16.0 * g / 40         # fee ∈ [$8, $24]
        counts: dict = {}
        profit = 0.0
        for b in buyers:
            if b.convenience * b.penalties[b.pref] >= fee:
                profit += fee - _delivery_cost(b.pref, counts)
                counts[b.pref] = counts.get(b.pref, 0) + 1
        if profit > best_profit:
            best_profit, best_fee = profit, fee
    return best_fee


def _delivery_day(master_seed, day, rate, fee, arm):
    """One day of delivery orders under `arm` ∈ {posted, nego-pure, nego}.
    Sequential (route density builds within the day). Returns (profit, revenue,
    units)."""
    rng = np.random.default_rng(substream(master_seed, "deliv_arr", day))
    n = int(rng.poisson(rate))
    counts: dict = {}
    profit = revenue = units = 0.0
    for k in range(n):
        b = delivery_buyer(master_seed, day, k)
        if arm == "posted":
            w = b.pref
            if b.convenience * b.penalties[w] >= fee:
                profit += fee - _delivery_cost(w, counts)
                revenue += fee
                units += 1
                counts[w] = counts.get(w, 0) + 1
            continue
        # bilateral: the buyer's no-deal is booking their preferred window at
        # the posted flat fee (if worth it), or no delivery. The shop steers
        # a flexible buyer to the CURRENTLY densest window (min marginal cost)
        # and Nash-splits the routing saving — the logroll.
        posted_ok = b.convenience * b.penalties[b.pref] >= fee
        d_buyer = (b.convenience * b.penalties[b.pref] - fee) if posted_ok else 0.0
        d_shop = (fee - _delivery_cost(b.pref, counts)) if posted_ok else 0.0
        # pick the window maximizing joint surplus (buyer value − routing cost)
        best_w, best_joint = None, -1e18
        for w in cal.DELIVERY_WINDOWS:
            val = b.convenience * b.penalties[w]
            joint = val - _delivery_cost(w, counts)
            if joint > best_joint:
                best_joint, best_w = joint, w
        val = b.convenience * b.penalties[best_w]
        cost = _delivery_cost(best_w, counts)
        buffer = max(_ABS, _FRAC * fee)
        # discount-only: never charge more than the posted flat fee — the win
        # is the split route-density saving, not a surcharge.
        p = nash_price(val, cost, d_buyer, d_shop, fee, buffer)
        if p is not None:
            profit += p - cost
            revenue += p
            units += 1
            counts[best_w] = counts.get(best_w, 0) + 1
        elif arm == "nego" and posted_ok:
            profit += fee - _delivery_cost(b.pref, counts)
            revenue += fee
            units += 1
            counts[b.pref] = counts.get(b.pref, 0) + 1
    return profit, revenue, units


# ════════════════════════════════════════════════════════════════════════════
#  LINE 4 — ATTACH (chocolates / card / vase: a complement, suggest/1)
# ════════════════════════════════════════════════════════════════════════════
def attach_buyer(master_seed: int, day: int, k: int) -> dict:
    """A POS flower buyer's latent attach WTP per add-on item. Buying flowers
    RAISES the WTP (complement, not substitute — a gift wants a card): each
    interested item's WTP is boosted ×(1 + complement_boost). Not every buyer
    shops every add-on (interest Bernoulli)."""
    rng = np.random.default_rng(substream(master_seed, cal.SERVICES_SEED_SALT,
                                          "attach", day, k))
    wtp = {}
    for item in cal.ATTACH_ITEMS:
        shops = rng.random() < cal.ATTACH_INTEREST_PROB[item]
        draw = float(rng.lognormal(math.log(cal.ATTACH_BASE_WTP_MU[item]),
                                   cal.ATTACH_WTP_SIGMA))
        wtp[item] = draw * (1.0 + cal.ATTACH_COMPLEMENT_BOOST) if shops else 0.0
    return wtp


def _optimize_attach_markup(master_seed, rate, days=40, n_sample=8000):
    """Posted best shot for attach: a single global markup λ on the shelf
    prices, profit-maxed. The passive shelf converts a buyer only if their WTP
    beats the shelf price."""
    buyers = []
    d = 0
    while len(buyers) < n_sample:
        rng = np.random.default_rng(substream(master_seed, "attopt", d))
        n = int(rng.poisson(rate))
        for k in range(n):
            buyers.append(attach_buyer(master_seed, 2 * 10 ** 6 + d, k))
        d += 1
    best_lam, best_profit = 1.0, -1e18
    for g in range(41):
        lam = 0.7 + 0.6 * g / 40
        profit = 0.0
        for wtp in buyers:
            for item in cal.ATTACH_ITEMS:
                p = lam * cal.ATTACH_REF_PRICE[item]
                if wtp[item] >= p:
                    profit += p - cal.ATTACH_COST[item]
        if profit > best_profit:
            best_profit, best_lam = profit, lam
    return best_lam


def _attach_day(master_seed, day, rate, lam, arm):
    """One day of POS attach. posted = passive shelf at λ×ref (buyer self-
    selects). nego/suggest = bundle-price each interested item via Nash,
    converting sub-shelf WTP the passive shelf misses. nego-pure = suggest
    only (a declined suggestion is a lost attach); nego = suggest then let the
    shelf catch anyone the quote didn't."""
    rng = np.random.default_rng(substream(master_seed, "attach_arr", day))
    n = int(rng.poisson(rate))
    profit = revenue = units = 0.0
    for k in range(n):
        wtp = attach_buyer(master_seed, day, k)
        for item in cal.ATTACH_ITEMS:
            w = wtp[item]
            if w <= 0:
                continue
            shelf = lam * cal.ATTACH_REF_PRICE[item]
            cost = cal.ATTACH_COST[item]
            ref = cal.ATTACH_REF_PRICE[item]
            if arm == "posted":
                if w >= shelf:
                    profit += shelf - cost
                    revenue += shelf
                    units += 1
                continue
            # suggest: buyer's no-deal is the shelf (buy at `shelf` if w≥shelf
            # else nothing); shop's no-deal is the shelf profit if they'd buy.
            posted_ok = w >= shelf
            d_buyer = (w - shelf) if posted_ok else 0.0
            d_shop = (shelf - cost) if posted_ok else 0.0
            buffer = max(_ABS, _FRAC * ref)
            p = nash_price(w, cost, d_buyer, d_shop, ref, buffer)
            if p is not None:
                profit += p - cost
                revenue += p
                units += 1
            elif arm == "nego" and posted_ok:
                profit += shelf - cost
                revenue += shelf
                units += 1
    return profit, revenue, units


# ── generic config-line daily simulation (arrangement, event) ───────────────
def _config_day(configs_menu_buyer, master_seed, day, rate, lam, arm,
                per_booking_configs=False):
    """One day for a config-space line. `configs_menu_buyer` is either a tuple
    (configs, menu_idx, buyer_fn) [arrangement — fixed space] or a booking_fn
    returning (configs, menu_idx, buyer) per arrival [event — space depends on
    wedding/funeral]. Returns (profit, revenue, units)."""
    rng = np.random.default_rng(substream(master_seed, "cfg_arr",
                                          per_booking_configs, day))
    n = int(rng.poisson(rate))
    profit = revenue = units = 0.0
    for k in range(n):
        if per_booking_configs:
            configs, menu_idx, buyer = configs_menu_buyer(master_seed, day, k)
        else:
            configs, menu_idx, buyer_fn = configs_menu_buyer
            buyer = buyer_fn(master_seed, day, k)
        if arm == "posted":
            out = _posted_choice(configs, menu_idx, lam, buyer)
        else:
            out = _nego_choice(configs, menu_idx, lam, buyer,
                               pure=(arm == "nego-pure"))
        if out is not None:
            price, cost = out[0], out[1]
            profit += price - cost
            revenue += price
            units += 1
    return profit, revenue, units


# ── per-line experiment (paired posted / nego-pure / nego over `days`) ──────
ARMS_SERVICES = ("posted", "nego-pure", "nego")


def _run_line(day_fn, master_seed, days):
    """Run all three arms over `days` PAIRED days; return per-arm per-day
    (profit, revenue, units) lists and the paired deltas with block CIs."""
    per = {a: {"profit": [], "revenue": [], "units": []}
           for a in ARMS_SERVICES}
    for d in range(days):
        for a in ARMS_SERVICES:
            pr, rev, u = day_fn(master_seed, d, a)
            per[a]["profit"].append(pr)
            per[a]["revenue"].append(rev)
            per[a]["units"].append(u)
    deltas = {}
    for a in ("nego", "nego-pure"):
        deltas[f"{a}_vs_posted"] = {
            "profit": _paired_block_ci(
                [per[a]["profit"][d] - per["posted"]["profit"][d]
                 for d in range(days)]),
            "revenue": _paired_block_ci(
                [per[a]["revenue"][d] - per["posted"]["revenue"][d]
                 for d in range(days)]),
        }
    totals = {a: {"profit": round(sum(per[a]["profit"]), 2),
                  "revenue": round(sum(per[a]["revenue"]), 2),
                  "units": int(sum(per[a]["units"])),
                  "profit_per_day": round(sum(per[a]["profit"]) / days, 2),
                  "revenue_per_day": round(sum(per[a]["revenue"]) / days, 2)}
              for a in ARMS_SERVICES}
    return {"totals": totals, "deltas": deltas,
            "_per_day": {a: per[a]["profit"] for a in ARMS_SERVICES}}


def arr_markup(master_seed: int) -> float:
    """The arrangement line's posted best-shot markup (profit-max λ on the
    population). Named so tests and run_services share one source of truth."""
    return _optimize_menu_markup(
        ARR_CONFIGS, ARR_MENU_IDX,
        (arr_buyer(master_seed, 9 * 10 ** 6, k) for k in range(10 ** 9)))


def event_markups(master_seed: int) -> tuple:
    """The wedding and funeral posted best-shot package markups (each tuned on
    its own scope×palette space)."""
    wed = _optimize_menu_markup(
        EVENT_WED_CONFIGS, EVENT_WED_MENU_IDX,
        (event_booking(master_seed, 7 * 10 ** 6 + d, 0)[2]
         for d in range(10 ** 9)
         if event_booking(master_seed, 7 * 10 ** 6 + d, 0)[0] is EVENT_WED_CONFIGS))
    fun = _optimize_menu_markup(
        EVENT_FUN_CONFIGS, EVENT_FUN_MENU_IDX,
        (event_booking(master_seed, 6 * 10 ** 6 + d, 0)[2]
         for d in range(10 ** 9)
         if event_booking(master_seed, 6 * 10 ** 6 + d, 0)[0] is EVENT_FUN_CONFIGS))
    return wed, fun


def run_services(master_seed: int = 20260710, days: int = 90) -> dict:
    """Run all four services lines, paired posted vs bilateral, `days` per
    line (≥90 for headline power, per CRITICAL-ANALYSIS §8). Returns the full
    per-line result dict incl. the revenue-weighted florist-level blend."""
    # ── posted best-shot markups / fee, profit-maxed on the population ──
    arr_lam = arr_markup(master_seed)
    wed_lam, fun_lam = event_markups(master_seed)
    fee = _optimize_flat_fee(master_seed, days, cal.DELIVERY_RATE)
    att_lam = _optimize_attach_markup(master_seed, cal.ATTACH_RATE)

    lines = {}
    lines["arrangement"] = _run_line(
        lambda s, d, a: _config_day((ARR_CONFIGS, ARR_MENU_IDX, arr_buyer),
                                    s, d, cal.ARRANGEMENT_RATE, arr_lam, a),
        master_seed, days)
    lines["arrangement"]["posted_markup"] = round(arr_lam, 4)

    # events run wedding+funeral in one stream; each booking carries its own
    # space and its own optimized markup (chosen by type inside the day fn)
    def _event_day(s, d, a):
        rng = np.random.default_rng(substream(s, "event_arr", d))
        n = int(rng.poisson(cal.EVENT_RATE))
        profit = revenue = units = 0.0
        for k in range(n):
            configs, menu_idx, buyer = event_booking(s, d, k)
            lam = wed_lam if configs is EVENT_WED_CONFIGS else fun_lam
            if a == "posted":
                out = _posted_choice(configs, menu_idx, lam, buyer)
            else:
                out = _nego_choice(configs, menu_idx, lam, buyer,
                                   pure=(a == "nego-pure"))
            if out is not None:
                profit += out[0] - out[1]
                revenue += out[0]
                units += 1
        return profit, revenue, units
    lines["event"] = _run_line(_event_day, master_seed, days)
    lines["event"]["posted_markup"] = {"wedding": round(wed_lam, 4),
                                       "funeral": round(fun_lam, 4)}

    lines["delivery"] = _run_line(
        lambda s, d, a: _delivery_day(s, d, cal.DELIVERY_RATE, fee, a),
        master_seed, days)
    lines["delivery"]["posted_fee"] = round(fee, 2)

    lines["attach"] = _run_line(
        lambda s, d, a: _attach_day(s, d, cal.ATTACH_RATE, att_lam, a),
        master_seed, days)
    lines["attach"]["posted_markup"] = round(att_lam, 4)

    # ── the revenue-weighted florist-level blend ──
    # walk-in clearance slice: pulled from the main flowers grid (computed is
    # the posted arm there; nego is bilateral). Posted WINS that slice.
    walkin = _walkin_slice(master_seed, days)
    blend = _blend(lines, walkin, days)

    return {"services_version": SERVICES_VERSION, "seed": master_seed,
            "days": days, "arms": list(ARMS_SERVICES),
            "lines": lines, "walkin": walkin, "blend": blend,
            "notes": [
                "PAIRED on identity: buyer draws depend only on "
                "(seed, line, day, k) — both arms face the same stream.",
                "posted gets its best shot: menu markup / flat fee tuned to "
                "the profit-max global level on the population (not a strawman).",
                "discount-only: a bilateral quote never prices over the "
                "config's reference list.",
                "nego-pure = bilateral only (a declined quote is a lost sale) "
                "— the mechanism's standalone verdict; nego = bilateral with "
                "the posted menu as fallback (the deployable broker).",
                "truthful disclosure to the Nash engine assumed (vend-P1); "
                "the liar tax is measured elsewhere.",
            ]}


def _walkin_slice(master_seed, days):
    """The walk-in perishable clearance slice, re-run at the services horizon
    so its per-day delta is comparable to the services lines. computed/1 is the
    posted arm; nego/1 is bilateral. This is the slice where posted WINS."""
    from bakeshop.run import run_experiment
    from bakeshop.world import BakeshopConfig
    # the calm 0.15/0.0 cell — CRITICAL-ANALYSIS §9's cleanest significant
    # "posted beats nego" result (nego − computed −73.58 [−112.92, −34.25] at
    # 30 days); spike days only WIDEN posted's win (§9 H-B3: −123…−162/day).
    cfg = BakeshopConfig(sigma_miscal=0.15, spike_prob=0.0)
    res = run_experiment(["control", "computed", "nego"], "flowers", days,
                         master_seed, cfg)
    comp = res["_per_day"]["computed"]
    nego = res["_per_day"]["nego"]
    delta = _paired_block_ci([nego[d]["profit"] - comp[d]["profit"]
                              for d in range(days)])
    posted_rev = round(sum(m["revenue"] for m in comp) / days, 2)
    posted_profit = round(sum(m["profit"] for m in comp) / days, 2)
    nego_profit = round(sum(m["profit"] for m in nego) / days, 2)
    return {"posted_arm": "computed/1", "nego_arm": "nego/1",
            "nego_vs_posted_profit": delta,
            "posted_profit_per_day": posted_profit,
            "nego_profit_per_day": nego_profit,
            "posted_revenue_per_day": posted_rev}


def _blend(lines, walkin, days):
    """Revenue-weighted florist-level verdict: sum the per-day posted profit
    and the per-day nego(-deployable) profit across ALL lines incl. walk-in,
    and report the aggregate nego − posted delta and each line's revenue share
    so the weighting is explicit. Uses the DEPLOYABLE nego (menu fallback) for
    the shop-level P&L (that is what a florist would actually run); the pure-
    mechanism split is in the per-line table."""
    rows = []
    posted_tot = nego_tot = rev_tot = 0.0
    for name, L in lines.items():
        prev = L["totals"]["posted"]["revenue_per_day"]
        pprof = L["totals"]["posted"]["profit_per_day"]
        nprof = L["totals"]["nego"]["profit_per_day"]
        rows.append({"line": name, "revenue_per_day": prev,
                     "posted_profit_per_day": pprof,
                     "nego_profit_per_day": nprof,
                     "nego_minus_posted": round(nprof - pprof, 2)})
        posted_tot += pprof
        nego_tot += nprof
        rev_tot += prev
    # walk-in
    rows.append({"line": "walk-in (clearance)",
                 "revenue_per_day": walkin["posted_revenue_per_day"],
                 "posted_profit_per_day": walkin["posted_profit_per_day"],
                 "nego_profit_per_day": walkin["nego_profit_per_day"],
                 "nego_minus_posted": round(
                     walkin["nego_profit_per_day"]
                     - walkin["posted_profit_per_day"], 2)})
    posted_tot += walkin["posted_profit_per_day"]
    nego_tot += walkin["nego_profit_per_day"]
    rev_tot += walkin["posted_revenue_per_day"]
    for r in rows:
        r["revenue_share"] = round(r["revenue_per_day"] / rev_tot, 4) \
            if rev_tot > 0 else 0.0
    return {"rows": rows,
            "posted_profit_per_day": round(posted_tot, 2),
            "nego_profit_per_day": round(nego_tot, 2),
            "nego_minus_posted_per_day": round(nego_tot - posted_tot, 2),
            "total_revenue_per_day": round(rev_tot, 2)}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default="bakeshop/services.json")
    args = ap.parse_args(argv)
    res = run_services(args.seed, args.days)
    slim = {k: v for k, v in res.items()}
    # strip the heavy per-day arrays for the on-disk artifact
    for L in slim["lines"].values():
        L.pop("_per_day", None)
    with open(args.out, "w") as f:
        json.dump(slim, f, indent=1)
    print(f"wrote {args.out}  ({args.days} paired days, seed {args.seed})\n")
    for name, L in res["lines"].items():
        d = L["deltas"]["nego-pure_vs_posted"]["profit"]
        dd = L["deltas"]["nego_vs_posted"]["profit"]
        print(f"  {name:<12} posted ${L['totals']['posted']['profit_per_day']:>8.2f}/day"
              f" · nego-pure−posted {d['mean']:>+8.2f} {d['ci95']}"
              f" · nego−posted {dd['mean']:>+7.2f} {dd['ci95']}")
    w = res["walkin"]["nego_vs_posted_profit"]
    print(f"  {'walk-in':<12} posted ${res['walkin']['posted_profit_per_day']:>8.2f}/day"
          f" · nego−posted {w['mean']:>+8.2f} {w['ci95']}  (posted wins the clearance slice)")
    b = res["blend"]
    print(f"\n  BLEND (revenue-weighted, deployable nego): posted "
          f"${b['posted_profit_per_day']}/day → nego ${b['nego_profit_per_day']}/day "
          f"(Δ {b['nego_minus_posted_per_day']:+}/day)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

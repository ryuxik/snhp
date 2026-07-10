"""The block's shared population — the SAME seeded walkers enter both worlds.

Layering rule (B0 hard requirement, unchanged in B1/B2): this module knows
GEOGRAPHY (four venues exist; each shopper was heading to one of them) and
TASTES (WTP draws over the union of the block's goods). It knows NOTHING
about prices, policies, or ledgers. Every draw depends only on
(master_seed, day, tick, persona/lane, k) — never on anything a world did —
so the population stream is identical across the sticker and SNHP worlds BY
CONSTRUCTION; block/tests asserts it.

The shopper funnel, calibrated (DESIGN §3 honesty gate):
  * BLOCK_DAILY_FOOT_TRAFFIC (4200) walkers pass the storefronts; most never
    shop. The STREET fraction is DERIVED, not tuned:
    (VENDING_DAILY_ARRIVALS + BODEGA_DAILY_TX) / BLOCK_DAILY_FOOT_TRAFFIC
    ≈ 0.148. B1/B2 add two more lanes on the same honesty rule:
      - boba lane: boba/world's own hourly curve verbatim (it was calibrated
        so the static menu lands near BOBA_DAILY_CUPS) — ~377 arrivals/day
        inside boba hours 10:00–22:00;
      - fashion lane: calibration publishes a TRANSACTIONS target
        (FASHION_DAILY_TX = 34), so the arrival scale is DERIVED by dividing
        by the analytic cliff-calendar conversion (loyal-now, true appeal)
        — the same "derived, not tuned" rule as the street funnel.
  * Each STREET shopper gets a HOME venue (vending or bodega) exactly as in
    B0 — the B0 street stream is bit-identical, draw for draw. Boba and
    fashion walkers are their own lanes (home = "boba" / "fashion"); the
    cross-category substitution (a thirsty walker choosing cola over milk
    tea) is DEFERRED and documented — boba's outside option is the coffee
    shop next door (boba/world.OUTSIDE_MARKUP), fashion's is not buying.
  * Conversion is endogenous (WTP vs posted prices), so realized
    transactions land under the arrival targets; RESULTS-*.md report
    realized numbers.

WTP model: ONE draw per GOOD over the union of the block's goods.
  * CORE goods (vending SKUs ∪ bodega items — overlap counted once):
    lognormal around GOOD_MU × persona wtp_mult with vend's canonical
    WTP_SIGMA. Bodega-only items back out GOOD_MU = price × BODEGA_MU_MARKUP
    (1.08), matching the vending μ/price ratios.
  * BOBA goods (drinks + toppings) join the union with boba/world's OWN
    draw pattern, not the simple lognormal: one "thirst" draw scales all
    drinks (favorite full, substitutes at CROSS_DISCOUNT), topping tastes
    are SPARSE (like-gate then draw; a non-liker values it at zero), plus
    the flexibility flag and solo/group qty decay — the exact structure the
    boba Nash engine was validated against. GOOD_MU for boba goods is the
    inverted appeal scale (what makes the calibration menu profit-optimal).
    Boba tastes ride a SEPARATE substream so the B0 street draws are
    untouched, byte for byte.
  * FASHION shoppers additionally carry ONE style (uniform attention over
    calibration.FASHION_LINES), ONE size (fashion/world's size curve), a
    week-0-equivalent WTP draw around appeal = 0.90 × MSRP (fashion/world's
    aspirational-sticker convention), and a strategic-waiter flag.

B0 simplifications carried forward (documented, deferred): no day-of-week
pattern, no day-level demand shocks, no within-day return queue (fashion
waiters return WEEKLY — an endogenous, per-world decision handled by the
venue, not this module).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from block import calibration
from boba import world as boba_world
from fashion import world as fashion_world
from vend.world import TICKS_PER_DAY, WTP_SIGMA, hour_of


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (the gauntlet pattern — copied verbatim from
    vend.core.substream so the population layer carries no vend-policy
    imports): blake2b of the master seed and any hashable parts, folded to
    63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


# ── the goods: union of the block's catalogs, one WTP per good ───────────
VENDING_GOODS = tuple(sku for sku, *_ in calibration.VENDING_CATALOG)
BODEGA_GOODS = tuple(item for item, *_ in calibration.BODEGA_CATALOG)
# CORE goods keep B0's simple lognormal pattern; boba goods join the union
# below with boba/world's own draw structure (favorites, sparsity).
CORE_GOODS = VENDING_GOODS + tuple(g for g in BODEGA_GOODS
                                   if g not in VENDING_GOODS)
BOBA_DRINKS = tuple(name for name, *_ in calibration.BOBA_MENU)
BOBA_TOPPING_GOODS = tuple(name for name, *_ in calibration.BOBA_TOPPINGS)
GOODS = CORE_GOODS + BOBA_DRINKS + BOBA_TOPPING_GOODS

BODEGA_MU_MARKUP = 1.08   # posted price → mean WTP for bodega-only goods

GOOD_MU: dict[str, float] = {sku: mu for sku, mu, *_ in calibration.VENDING_CATALOG}
for _item, _price, _cost in calibration.BODEGA_CATALOG:
    GOOD_MU.setdefault(_item, round(_price * BODEGA_MU_MARKUP, 4))
# boba goods: the WTP scale is the INVERTED appeal — the level at which the
# calibration menu is the profit-optimal all-day sticker (boba/world).
for _d in BOBA_DRINKS:
    GOOD_MU[_d] = round(float(boba_world.DRINK_APPEAL[_d]), 4)
for _t in BOBA_TOPPING_GOODS:
    GOOD_MU[_t] = round(float(boba_world.TOP_APPEAL[_t]), 4)

# ── personas & schedules ─────────────────────────────────────────────────
# (share, wtp_mult, walk_cost) by name; schedule strings from calibration
# are rendered as hourly weight curves below (hours 7–22, the block clock).
_PERSONA = {name: (share, wtp_mult, walk_cost)
            for name, share, wtp_mult, walk_cost, _sched in calibration.PERSONAS}

PERSONA_HOURLY: dict[str, dict[int, float]] = {
    # "weekday 8-18 peaks": commute in, lunch spike, commute out
    "office-worker": {7: 2, 8: 8, 9: 5, 10: 3, 11: 7, 12: 10, 13: 8, 14: 3,
                      15: 2, 16: 3, 17: 7, 18: 5, 19: 1},
    # "after-school 15-19"
    "student": {14: 1, 15: 8, 16: 9, 17: 8, 18: 6, 19: 4, 20: 1},
    # "all-day, evening lean"
    "local": {7: 2, 8: 3, 9: 3, 10: 3, 11: 3, 12: 4, 13: 3, 14: 3, 15: 3,
              16: 3, 17: 4, 18: 5, 19: 6, 20: 6, 21: 5, 22: 3},
    # "midday-heavy" (weekend lean deferred with the block calendar)
    "tourist": {9: 1, 10: 3, 11: 6, 12: 8, 13: 8, 14: 7, 15: 6, 16: 5,
                17: 3, 18: 2, 19: 1},
}

# ── the funnel: derived from calibration, not tuned ──────────────────────
_TARGET_SHOPPERS = (calibration.VENDING_DAILY_ARRIVALS
                    + calibration.BODEGA_DAILY_TX)                    # 620
SHOPPER_FRACTION = _TARGET_SHOPPERS / calibration.BLOCK_DAILY_FOOT_TRAFFIC
DAILY_SHOPPERS = calibration.BLOCK_DAILY_FOOT_TRAFFIC * SHOPPER_FRACTION
P_VENDING_HOME = calibration.VENDING_DAILY_ARRIVALS / _TARGET_SHOPPERS

CROSS_WALK_JITTER = (0.8, 1.2)   # per-shopper hassle spread around persona $


def _tick_rates(name: str) -> list[float]:
    """Expected arrivals per tick for one persona (6 ticks per hour)."""
    share = _PERSONA[name][0]
    hours = PERSONA_HOURLY[name]
    tot = float(sum(hours.values()))
    return [DAILY_SHOPPERS * share * hours.get(hour_of(t), 0.0) / tot / 6.0
            for t in range(TICKS_PER_DAY)]


_RATES = {name: _tick_rates(name) for name in _PERSONA}


# ── boba lane (B1) ────────────────────────────────────────────────────────
# Shop hours 10:00–22:00 on the block clock (block hour_of and boba's own
# hour_of agree tick-for-tick inside the window — asserted in tests).
BOBA_OPEN_TICK = (10 - 7) * 6                                  # 18 → 10:00
BOBA_CLOSE_TICK = BOBA_OPEN_TICK + boba_world.TICKS_PER_DAY    # 90 → 22:00
# boba/world's curve verbatim: it was calibrated so the static menu lands
# near calibration.BOBA_DAILY_CUPS — re-shaping it onto persona schedules
# would silently move the queue physics the boba results were validated on.
BOBA_DAILY_ARRIVALS = float(sum(boba_world.HOURLY_RATE.values()))     # 377
BOBA_FLEX_SHARE = boba_world.DEFAULT_CONFIG.flexible_share            # 0.30


def _boba_rate(tick: int) -> float:
    """Expected boba-lane arrivals this block tick."""
    if not (BOBA_OPEN_TICK <= tick < BOBA_CLOSE_TICK):
        return 0.0
    return boba_world.HOURLY_RATE[hour_of(tick)] / 6.0


def _persona_mix_at(tick: int) -> dict[str, float]:
    """Who is on the street right now: the persona composition implied by
    the street schedules, used to give boba-lane walkers a persona (and so
    a wtp_mult and walk cost) consistent with the block's hour."""
    w = {p: _RATES[p][tick] for p in _PERSONA}
    tot = sum(w.values())
    if tot <= 0.0:
        return {"local": 1.0}          # late-evening fallback (local-only hours)
    return {p: v / tot for p, v in w.items()}


def _boba_tastes(rng: np.random.Generator, wtp_mult: float,
                 hour_mult: float) -> tuple[str, dict, dict, bool, float]:
    """boba/world.sample_consumer's draw pattern, scaled by the persona's
    wtp_mult: favorite drink → one 'thirst' draw scaling every drink
    (substitutes at CROSS_DISCOUNT) → SPARSE topping tastes (both draws
    always taken, so the stream is stable) → flexibility → solo/group
    decay. Returns (fav, drink_wtp, top_wtp, flexible, qty_decay)."""
    roll, acc, fav = rng.random(), 0.0, next(iter(boba_world.POPULARITY))
    for d, share in boba_world.POPULARITY.items():
        acc += share
        if roll < acc:
            fav = d
            break
    eps = float(rng.lognormal(0.0, boba_world.WTP_SIGMA))
    drink_wtp = {d: float(boba_world.DRINK_APPEAL[d] * hour_mult * wtp_mult
                          * eps * (1.0 if d == fav
                                   else boba_world.CROSS_DISCOUNT))
                 for d in BOBA_DRINKS}
    top_wtp = {}
    for t in BOBA_TOPPING_GOODS:
        like = rng.random() < boba_world.TOP_LIKE_PROB[t]
        draw = float(rng.lognormal(0.0, boba_world.TOP_SIGMA))
        top_wtp[t] = float(boba_world.TOP_APPEAL[t] * wtp_mult * draw) \
            if like else 0.0
    flexible = bool(rng.random() < BOBA_FLEX_SHARE)
    decay = boba_world.GROUP_DECAY if rng.random() < boba_world.GROUP_SHARE \
        else boba_world.SOLO_DECAY
    return fav, drink_wtp, top_wtp, flexible, decay


def _boba_hour_mult(tick: int) -> float:
    """boba/world applies its hourly WTP multiplier at SAMPLE time; outside
    boba hours the multiplier is undefined → 1.0 (latent tastes)."""
    return boba_world.HOURLY_WTP_MULT.get(hour_of(tick), 1.0)


# ── fashion lane (B2) ─────────────────────────────────────────────────────
FASHION_STYLES = tuple(s for s, *_ in calibration.FASHION_LINES)
FASHION_MSRP = {s: m for s, m, _c in calibration.FASHION_LINES}
FASHION_APPEAL_FRAC = 0.90          # fashion/world: the sticker is aspirational
FASHION_APPEAL = {s: round(FASHION_APPEAL_FRAC * m, 2)
                  for s, m in FASHION_MSRP.items()}
# Attention uniform across the four lines — calibration publishes no
# line-level traffic split; a pilot-data target like every other constant.
FASHION_ATTENTION = {s: 1.0 / len(FASHION_STYLES) for s in FASHION_STYLES}
FASHION_WAITER_SHARE = 0.15         # fashion/world DEFAULT_CONFIG.waiter_share
FASHION_SEASON_WEEKS = calibration.FASHION_SEASON_WEEKS
# The boutique's crowd leans tourist/local (LES independent): a documented
# calibration choice, not derived — replace with door-counter data at pilot.
FASHION_MIX = {"tourist": 0.40, "local": 0.35,
               "office-worker": 0.15, "student": 0.10}


def fashion_cliff_mult(week: int) -> float:
    """The industry markdown calendar, compressed from fashion/world's
    16-week shape (8/3/3/2 at 1.0/0.70/0.50/0.30) to the calibration's
    FASHION_SEASON_WEEKS=14 (7/3/3/1). It lives HERE, not in venues,
    because it is PUBLIC market knowledge — the waiters' price-drift belief
    was trained on it — and because the arrival-scale derivation below
    needs it."""
    full = FASHION_SEASON_WEEKS // 2
    if week < full:
        return 1.0
    if week < full + 3:
        return 0.70
    if week < full + 6:
        return 0.50
    return 0.30


def _fashion_conversion(week: int) -> float:
    """P(a week-`week` arrival buys) at the cliff calendar — loyal-now,
    TRUE appeal, season-staled. The analytic piece that turns calibration's
    FASHION_DAILY_TX (a transactions target) into an arrival scale, the
    same derived-not-tuned rule as the street funnel. Waiters delay rather
    than destroy purchases, so ignoring them here is a small, documented
    approximation."""
    return sum(FASHION_ATTENTION[s]
               * fashion_world.wtp_sf(
                   FASHION_MSRP[s] * fashion_cliff_mult(week),
                   FASHION_APPEAL[s] * float(fashion_world.decay(week)))
               for s in FASHION_STYLES)


_FASHION_SEASON_DAYS = FASHION_SEASON_WEEKS * 7
_FASHION_TX_PER_UNIT_RATE = sum(
    7.0 * fashion_world.ARRIVAL_TAPER ** w * _fashion_conversion(w)
    for w in range(FASHION_SEASON_WEEKS))
# Week-0 daily arrivals such that the season's EXPECTED transactions/day
# equals the calibration target.
FASHION_W0_DAILY = (calibration.FASHION_DAILY_TX * _FASHION_SEASON_DAYS
                    / _FASHION_TX_PER_UNIT_RATE)


def fashion_daily_rate(day: int) -> float:
    """Expected fashion-lane arrivals on block day `day` (weekly taper,
    early-season high — fashion/world's curve on the block calendar)."""
    return FASHION_W0_DAILY * fashion_world.ARRIVAL_TAPER ** (day // 7)


def _fashion_shape(name: str) -> list[float]:
    """Normalized per-tick arrival shape for one persona (Σ over ticks = 1)."""
    hours = PERSONA_HOURLY[name]
    tot = float(sum(hours.values()))
    return [hours.get(hour_of(t), 0.0) / tot / 6.0
            for t in range(TICKS_PER_DAY)]


_FASHION_SHAPE = {name: _fashion_shape(name) for name in FASHION_MIX}


@dataclass
class Shopper:
    """One walker who will actually shop today. Immutable in spirit: the
    runner never writes to it, so the same object can serve both worlds."""
    uid: int                 # stable identity (blake2b substream)
    persona: str
    home: str                # "vending"|"bodega"|"boba"|"fashion" — headed to
    wtp: dict[str, float]    # $ value of the FIRST unit, per good (union;
                             # includes boba drinks — toppings live below)
    cross_walk: float        # $ hassle of using the NON-home venue instead
    # boba tastes (union extension, every shopper carries them)
    boba_fav: str = ""
    top_wtp: dict[str, float] = field(default_factory=dict)
    boba_flexible: bool = False
    boba_decay: float = 0.15          # boba/world.SOLO_DECAY
    # fashion (only home == "fashion" shoppers carry non-defaults)
    style: str = ""
    size: str = ""
    fashion_wtp: float = 0.0          # week-0-equivalent draw (venue stales it)
    waiter: bool = False


def sample_shopper(master_seed: int, day: int, tick: int, persona: str,
                   k: int) -> Shopper:
    """Pure function of (master_seed, day, tick, persona, k). Draw order is
    fixed and documented: WTPs over CORE_GOODS in canonical order, then the
    home venue, then the cross-walk jitter — B0's exact stream, untouched.
    Boba tastes ride a SEPARATE substream appended afterwards, so adding
    them changed no B0 draw."""
    share, wtp_mult, walk_cost = _PERSONA[persona]
    rng = np.random.default_rng(substream(master_seed, "shopper", day, tick,
                                          persona, k))
    wtp = {g: float(rng.lognormal(math.log(GOOD_MU[g] * wtp_mult), WTP_SIGMA))
           for g in CORE_GOODS}
    home = "vending" if rng.random() < P_VENDING_HOME else "bodega"
    cross = float(walk_cost * rng.uniform(*CROSS_WALK_JITTER))
    rng_b = np.random.default_rng(substream(master_seed, "boba", day, tick,
                                            persona, k))
    fav, drink_wtp, top_wtp, flex, decay = _boba_tastes(
        rng_b, wtp_mult, _boba_hour_mult(tick))
    wtp.update(drink_wtp)
    return Shopper(uid=substream(master_seed, "uid", day, tick, persona, k),
                   persona=persona, home=home, wtp=wtp, cross_walk=cross,
                   boba_fav=fav, top_wtp=top_wtp, boba_flexible=flex,
                   boba_decay=decay)


def _categorical(rng: np.random.Generator, weights: dict[str, float]) -> str:
    roll, acc, last = rng.random(), 0.0, None
    for name, w in weights.items():
        acc += w
        last = name
        if roll < acc:
            return name
    return last


def sample_boba_shopper(master_seed: int, day: int, tick: int,
                        k: int) -> Shopper:
    """One boba-lane walker. Draw order (fixed): persona (street mix at this
    hour) → CORE union WTPs → boba tastes (with boba's hourly WTP
    multiplier, as boba/world samples at arrival time) → cross-walk."""
    rng = np.random.default_rng(substream(master_seed, "bobashopper", day,
                                          tick, k))
    persona = _categorical(rng, _persona_mix_at(tick))
    share, wtp_mult, walk_cost = _PERSONA[persona]
    wtp = {g: float(rng.lognormal(math.log(GOOD_MU[g] * wtp_mult), WTP_SIGMA))
           for g in CORE_GOODS}
    fav, drink_wtp, top_wtp, flex, decay = _boba_tastes(
        rng, wtp_mult, _boba_hour_mult(tick))
    wtp.update(drink_wtp)
    cross = float(walk_cost * rng.uniform(*CROSS_WALK_JITTER))
    return Shopper(uid=substream(master_seed, "uid-boba", day, tick, k),
                   persona=persona, home="boba", wtp=wtp, cross_walk=cross,
                   boba_fav=fav, top_wtp=top_wtp, boba_flexible=flex,
                   boba_decay=decay)


def sample_fashion_shopper(master_seed: int, day: int, tick: int,
                           persona: str, k: int) -> Shopper:
    """One fashion-lane walker (tourist/local-heavy mix). Draw order
    (fixed): CORE union WTPs → boba tastes → style → size → week-0 WTP
    (around appeal × persona wtp_mult) → waiter flag → cross-walk. They
    shop exactly ONE style in exactly ONE size (fashion/world's model)."""
    share, wtp_mult, walk_cost = _PERSONA[persona]
    rng = np.random.default_rng(substream(master_seed, "fashshopper", day,
                                          tick, persona, k))
    wtp = {g: float(rng.lognormal(math.log(GOOD_MU[g] * wtp_mult), WTP_SIGMA))
           for g in CORE_GOODS}
    fav, drink_wtp, top_wtp, flex, decay = _boba_tastes(
        rng, wtp_mult, _boba_hour_mult(tick))
    wtp.update(drink_wtp)
    style = _categorical(rng, FASHION_ATTENTION)
    size = _categorical(rng, fashion_world.SIZE_SHARE)
    base = float(rng.lognormal(math.log(FASHION_APPEAL[style] * wtp_mult),
                               fashion_world.WTP_SIGMA))
    is_waiter = bool(rng.random() < FASHION_WAITER_SHARE)
    cross = float(walk_cost * rng.uniform(*CROSS_WALK_JITTER))
    return Shopper(uid=substream(master_seed, "uid-fash", day, tick, persona, k),
                   persona=persona, home="fashion", wtp=wtp, cross_walk=cross,
                   boba_fav=fav, top_wtp=top_wtp, boba_flexible=flex,
                   boba_decay=decay, style=style, size=size, fashion_wtp=base,
                   waiter=is_waiter)


def arrivals_at(master_seed: int, day: int, tick: int) -> list[Shopper]:
    """Poisson arrivals this tick — world-independent by construction
    (there is no world/policy parameter to pass). Lane order is fixed:
    street personas (B0, verbatim), then the boba lane, then the fashion
    lane."""
    out: list[Shopper] = []
    for name in _PERSONA:
        lam = _RATES[name][tick]
        if lam <= 0.0:
            continue
        n = int(np.random.default_rng(
            substream(master_seed, "arr", day, tick, name)).poisson(lam))
        out.extend(sample_shopper(master_seed, day, tick, name, k)
                   for k in range(n))
    lam_b = _boba_rate(tick)
    if lam_b > 0.0:
        n = int(np.random.default_rng(
            substream(master_seed, "boba-arr", day, tick)).poisson(lam_b))
        out.extend(sample_boba_shopper(master_seed, day, tick, k)
                   for k in range(n))
    daily_f = fashion_daily_rate(day)
    for name, mix in FASHION_MIX.items():
        lam_f = daily_f * mix * _FASHION_SHAPE[name][tick]
        if lam_f <= 0.0:
            continue
        n = int(np.random.default_rng(
            substream(master_seed, "fash-arr", day, tick, name)).poisson(lam_f))
        out.extend(sample_fashion_shopper(master_seed, day, tick, name, k)
                   for k in range(n))
    return out


def day_stream(master_seed: int, day: int) -> dict[int, list[Shopper]]:
    """tick → shoppers, for one day. Both worlds consume this stream; the
    pairing test regenerates it and asserts byte-level equality."""
    return {t: arrivals_at(master_seed, day, t) for t in range(TICKS_PER_DAY)}


def expected_home_rate(venue: str, tick: int) -> float:
    """Analytic expected STREET arrivals/tick whose HOME is `venue`
    ("vending" | "bodega") — what those venues may honestly know about
    their own crowd curve (feeds the vend-style demand learners). The boba
    and fashion lanes are separate streams and never enter here."""
    tot = sum(_RATES[name][tick] for name in _PERSONA)
    return tot * (P_VENDING_HOME if venue == "vending" else 1.0 - P_VENDING_HOME)


def expected_daily() -> dict[str, float]:
    """Analytic daily totals — equal to the calibration targets by
    construction (the funnel is derived, not tuned). "shoppers" keeps its
    B0 meaning (the STREET lane, vending+bodega homes); the boba and
    fashion lanes report separately. fashion_home is the WEEK-0 arrival
    rate (it tapers weekly); fashion_tx_target is what the arrivals were
    derived to deliver over a season."""
    total = sum(sum(r) for r in _RATES.values())
    return {"shoppers": total,
            "vending_home": total * P_VENDING_HOME,
            "bodega_home": total * (1.0 - P_VENDING_HOME),
            "boba_home": BOBA_DAILY_ARRIVALS,
            "fashion_home": FASHION_W0_DAILY,
            "fashion_tx_target": float(calibration.FASHION_DAILY_TX)}

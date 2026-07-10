"""BLOCK B1/B2 tests: every B0 property holds for FOUR venues —
conservation laws to the float, byte-level determinism, a world-independent
population stream, NYC prices end-to-end, and real composition (substitution,
rents, fairness). B1 adds boba queue conservation on the block; B2 adds
fashion's week-boundary correctness and the one-buy season; the bodega
adoption toggle is proven to touch ONLY the SNHP world."""
import json
import math
import time

import numpy as np
import pytest

from block import calibration, population
from block.ledger import BlockLedger
from block.runner import parse_venues, run_twin, run_world
from block.venues import (BlockConfig, BlockRegularPool, BobaVenue,
                          BodegaVenue, FashionVenue, VendingVenue,
                          build_block_catalog, build_fashion_plan)
from boba import world as boba_world
from vend.world import TICKS_PER_DAY, _profit_optimal_list_price, hour_of

SEED = 20260710
RENTS = {"vending": VendingVenue.rent_per_day,
         "bodega": BodegaVenue.rent_per_day,
         "boba": BobaVenue.rent_per_day,
         "fashion": FashionVenue.rent_per_day}
FOUR = ("vending", "bodega", "boba", "fashion")


@pytest.fixture(scope="module")
def twin3():
    """One 3-day four-venue twin run shared by the accounting tests."""
    return run_twin(days=3, seed=SEED)


@pytest.fixture(scope="module")
def adopt_pair():
    """Two 2-day twins differing ONLY in bodega_adopts — the toggle probe."""
    off = run_twin(days=2, seed=SEED, cfg=BlockConfig())
    on = run_twin(days=2, seed=SEED, cfg=BlockConfig(bodega_adopts=True))
    return off, on


# ── population: pairing, calibration, personas, lanes ────────────────────

def test_population_stream_is_paired_by_construction():
    """THE twin-worlds guarantee: the stream is a pure function of
    (seed, day) — no world/policy parameter even exists — so two
    generations are identical, shopper by shopper, field by field."""
    a = population.day_stream(SEED, day=2)
    b = population.day_stream(SEED, day=2)
    assert a == b
    n = sum(len(v) for v in a.values())
    assert n > 0
    uids = [s.uid for t in a for s in a[t]]
    assert len(set(uids)) == len(uids)          # stable, distinct identities
    homes = {s.home for t in a for s in a[t]}
    assert homes == {"vending", "bodega", "boba", "fashion"}


def test_both_worlds_consumed_the_same_arrivals(twin3):
    """End-to-end pairing: the arrival events the two worlds actually
    processed are identical (uid, persona, home, tick), day by day.
    Fashion waiter RETURNS are excluded: whether a waiter comes back next
    week depends on whether this world's prices converted them — earned
    divergence, not sampled (every other arrival must match exactly)."""
    _res, ledger, _worlds = twin3
    def stream(world):
        return [(e["day"], e["tick"], e["uid"], e["persona"], e["home"])
                for e in ledger.events
                if e["type"] == "arrival" and e["world"] == world
                and e["kind"] != "return"]
    assert stream("sticker") == stream("snhp")


def test_funnel_is_derived_from_calibration_targets():
    """Every lane's scale is derived, not tuned: analytic street totals
    equal the B0 targets exactly; the boba lane is boba/world's own curve
    (377/day); the fashion lane's arrival scale is backed out of the
    FASHION_DAILY_TX transactions target through the cliff-calendar
    conversion. Simulated arrivals track all of them."""
    exp = population.expected_daily()
    assert exp["shoppers"] == pytest.approx(
        calibration.VENDING_DAILY_ARRIVALS + calibration.BODEGA_DAILY_TX)
    assert exp["vending_home"] == pytest.approx(calibration.VENDING_DAILY_ARRIVALS)
    assert exp["bodega_home"] == pytest.approx(calibration.BODEGA_DAILY_TX)
    assert exp["boba_home"] == pytest.approx(sum(boba_world.HOURLY_RATE.values()))
    # the derivation closes: W0 arrivals × conversion ≡ the tx target
    season_tx = sum(
        7.0 * population.FASHION_W0_DAILY
        * population.fashion_world.ARRIVAL_TAPER ** w
        * population._fashion_conversion(w)
        for w in range(population.FASHION_SEASON_WEEKS))
    assert season_tx / (population.FASHION_SEASON_WEEKS * 7) == pytest.approx(
        calibration.FASHION_DAILY_TX)
    days = 6
    counts = {"street": 0, "vending": 0, "boba": 0, "fashion": 0}
    for d in range(days):
        for t, shoppers in population.day_stream(SEED, d).items():
            for s in shoppers:
                if s.home in ("vending", "bodega"):
                    counts["street"] += 1
                    counts["vending"] += s.home == "vending"
                else:
                    counts[s.home] += 1
    assert counts["street"] / days == pytest.approx(exp["shoppers"], rel=0.10)
    assert counts["vending"] / days == pytest.approx(exp["vending_home"], rel=0.25)
    assert counts["boba"] / days == pytest.approx(exp["boba_home"], rel=0.10)
    assert counts["fashion"] / days == pytest.approx(exp["fashion_home"], rel=0.15)


def test_persona_schedules_shape_the_day():
    """Schedules from calibration render as arrival-time distributions:
    office workers live in 8–18 with a lunch peak; students after school."""
    def mass(name, lo, hi):
        r = population._RATES[name]
        tot = sum(r)
        return sum(r[t] for t in range(TICKS_PER_DAY)
                   if lo <= hour_of(t) <= hi) / tot
    assert mass("office-worker", 8, 18) > 0.85
    office = population._RATES["office-worker"]
    peak_hour = hour_of(int(np.argmax(office)))
    assert peak_hour in (12, 13)
    assert mass("student", 15, 19) > 0.90


def test_wtp_covers_the_union_and_shares_overlapping_goods():
    """One WTP per GOOD over the union of all four catalogs: 11 core goods
    (vending ∪ bodega, overlap once) + 4 drinks + 4 toppings = 19. Boba
    goods carry boba/world's structure: the favorite outdraws substitutes
    (CROSS_DISCOUNT) and topping tastes are sparse (non-likers at zero)."""
    assert len(population.GOODS) == len(set(population.GOODS)) == 19
    assert len(population.CORE_GOODS) == 11
    assert "cola-20oz" in population.VENDING_GOODS
    assert "cola-20oz" in population.BODEGA_GOODS
    assert population.GOOD_MU["cola-20oz"] == 3.40   # vending mu wins overlap
    sh = population.sample_shopper(SEED, 0, 30, "office-worker", 0)
    assert set(sh.wtp) == set(population.CORE_GOODS) | set(population.BOBA_DRINKS)
    assert set(sh.top_wtp) == set(population.BOBA_TOPPING_GOODS)
    assert sh.boba_fav in population.BOBA_DRINKS
    for d in population.BOBA_DRINKS:
        if d != sh.boba_fav:      # substitutes at the cross discount, exactly
            assert sh.wtp[d] == pytest.approx(
                sh.wtp[sh.boba_fav] * boba_world.CROSS_DISCOUNT
                * boba_world.DRINK_APPEAL[d]
                / boba_world.DRINK_APPEAL[sh.boba_fav])
    zeros = sum(1 for k in range(300)
                for t, v in population.sample_shopper(SEED, 0, 30, "local",
                                                      k).top_wtp.items()
                if v == 0.0)
    assert zeros > 300            # sparsity: plenty of true zeros in 1200 draws


def test_persona_wtp_multiplier_orders_the_draws():
    """tourist (×1.25) outbids student (×0.72) in expectation."""
    def mean_wtp(persona):
        draws = [population.sample_shopper(SEED, 0, 60, persona, k).wtp["coffee"]
                 for k in range(200)]
        return float(np.mean(draws))
    assert mean_wtp("tourist") > mean_wtp("student") * 1.3


def test_boba_lane_rides_bobas_own_curve():
    """Boba-lane walkers exist ONLY inside shop hours (block ticks 18..89 =
    10:00–22:00), at boba/world's arrival rates, with the taste structure
    the cart engine was validated on (flexibility share, solo/group)."""
    flex = solo = n = 0
    for d in range(3):
        for t, shoppers in population.day_stream(SEED, d).items():
            for s in shoppers:
                if s.home != "boba":
                    continue
                assert population.BOBA_OPEN_TICK <= t < population.BOBA_CLOSE_TICK
                n += 1
                flex += s.boba_flexible
                solo += s.boba_decay == boba_world.SOLO_DECAY
    assert n > 800
    assert flex / n == pytest.approx(population.BOBA_FLEX_SHARE, abs=0.06)
    assert solo / n == pytest.approx(1.0 - boba_world.GROUP_SHARE, abs=0.06)


def test_fashion_lane_is_tourist_local_heavy():
    """The boutique's crowd leans tourist/local; every fashion shopper has
    ONE style, ONE size (their size only), and ~waiter_share are strategic
    waiters; sizes follow fashion's size curve (M/L popular)."""
    personas, sizes, waiters, n = {}, {}, 0, 0
    for d in range(6):
        for t, shoppers in population.day_stream(SEED, d).items():
            for s in shoppers:
                if s.home != "fashion":
                    continue
                n += 1
                personas[s.persona] = personas.get(s.persona, 0) + 1
                sizes[s.size] = sizes.get(s.size, 0) + 1
                waiters += s.waiter
                assert s.style in population.FASHION_STYLES
                assert s.fashion_wtp > 0
    # threshold scales with calibration.FASHION_DAILY_TX (priority #2
    # recalibration cut the fashion lane ~11x, see calibration.py) — margin
    # below the ~71 arrivals/6-days this now realizes
    assert n > 50
    assert (personas.get("tourist", 0) + personas.get("local", 0)) / n > 0.6
    assert waiters / n == pytest.approx(population.FASHION_WAITER_SHARE, abs=0.05)
    assert sizes["M"] > sizes["S"] and sizes["L"] > sizes["XL"]


# ── NYC prices flow end-to-end ───────────────────────────────────────────

def test_nyc_catalog_prices_and_outside_mapping():
    cat = build_block_catalog(BlockConfig(sigma_cal=0.0), SEED)
    for sku, mu, cost, *_ in calibration.VENDING_CATALOG:
        assert cat[sku].list_price == _profit_optimal_list_price(mu, cost)
        assert cat[sku].list_price > cost
    # overlapping goods: the machine's believed outside IS the actual bodega
    bodega_posted = {i: p for i, p, _ in calibration.BODEGA_CATALOG}
    assert cat["cola-20oz"].bodega_price == bodega_posted["cola-20oz"] == 3.25
    assert cat["chips"].bodega_price == bodega_posted["chips"] == 2.50
    # non-overlapping: x1.15 phantom off the TRUE-mu sticker, anchor-blind
    anchored = build_block_catalog(BlockConfig(sigma_cal=0.0, anchor_mult=1.5), SEED)
    for sku in ("water-1L", "candy", "energy", "sandwich", "fruit-cup"):
        assert cat[sku].bodega_price == round(cat[sku].list_price * 1.15, 2)
        assert anchored[sku].bodega_price == cat[sku].bodega_price
    # miscalibration moves the sticker (competent, not omniscient, operator)
    noisy = build_block_catalog(BlockConfig(sigma_cal=0.15), SEED)
    assert any(noisy[s].list_price != cat[s].list_price for s in cat)


def test_bodega_prices_match_calibration_in_both_worlds():
    """Default config: the bodega has NOT adopted SNHP — same posted
    prices, both worlds, straight from calibration. The posted board stays
    the calibration prices even WHEN it adopts (negotiation surface only,
    never a reprice)."""
    posted = {i: p for i, p, _ in calibration.BODEGA_CATALOG}
    assert BodegaVenue("sticker").prices == posted
    assert BodegaVenue("snhp").prices == posted
    adopted = BodegaVenue("snhp", BlockConfig(bodega_adopts=True), SEED)
    assert adopted.adopted and adopted.prices == posted
    assert {i: l.list_price for i, l in adopted.catalog.items()} == posted


def test_vending_quote_never_exceeds_nyc_list(twin3):
    """Discount-only, end to end: every vending deal in either world —
    negotiated or board — prices at or under its NYC list."""
    _res, ledger, worlds = twin3
    negotiated = 0
    for e in ledger.events:
        if e["type"] == "deal" and e["venue"] == "vending":
            lp = worlds[e["world"]]["venues"]["vending"].catalog[e["sku"]].list_price
            assert e["unit_price"] <= lp + 1e-9
            negotiated += int(e["negotiated"])
    assert negotiated > 0        # the SNHP world actually negotiated


def test_negotiated_deals_beat_the_buyers_alternatives(twin3):
    """Rational acceptance held: every negotiated street deal left the
    buyer strictly better off net of walks; boba cart deals leave the buyer
    at least as well off as their event-consistent no-deal (the realized
    surplus may touch zero at the boundary rung — never go below). No
    negotiation surface exists anywhere in the sticker world."""
    _res, ledger, _worlds = twin3
    deals = [e for e in ledger.events
             if e["type"] == "deal" and e.get("negotiated")]
    assert deals and all(e["world"] == "snhp" for e in deals)
    by_venue = {}
    for e in deals:
        by_venue.setdefault(e["venue"], []).append(e)
    assert all(e["surplus"] > 0 for e in by_venue["vending"])
    assert "boba" in by_venue and all(e["surplus"] >= -1e-9
                                      for e in by_venue["boba"])
    assert "fashion" not in by_venue      # fashion negotiates nothing:
                                          # markdown/1 is a posted-price arm


def test_boba_sticker_world_posts_the_calibration_menu(twin3):
    """The sticker shop's product is the posted gut menu: every sticker-
    world boba deal prices at exactly the calibration menu (drink + chosen
    toppings), never negotiated, never deferred."""
    _res, ledger, _worlds = twin3
    n = 0
    for e in ledger.events:
        if e["type"] == "deal" and e["venue"] == "boba" \
                and e["world"] == "sticker":
            n += 1
            assert not e["negotiated"] and e["slot_ticks"] == 0
            menu = boba_world.DRINK_PRICE[e["sku"]] + sum(
                boba_world.TOP_PRICE[t] for t in e["tops"])
            assert e["unit_price"] == round(menu, 2)
    assert n > 100


def test_boba_cart_deals_are_discount_only(twin3):
    """No cart prices above the menu: every negotiated boba deal's spend is
    at or under the same cart's menu (list) value."""
    _res, ledger, _worlds = twin3
    n = 0
    for e in ledger.events:
        if e["type"] == "deal" and e["venue"] == "boba" and e["negotiated"]:
            n += 1
            listv = e["qty"] * (boba_world.DRINK_PRICE[e["sku"]] + sum(
                boba_world.TOP_PRICE[t] for t in e["tops"]))
            assert e["spend"] <= round(listv, 2) + 0.01   # 1¢ re-round slack
    assert n > 100


# ── conservation laws ────────────────────────────────────────────────────

def test_money_conservation_is_exact(twin3):
    """Every consumer dollar spent equals some venue's revenue — venue-side
    per-day tills (accumulated at settle) match the ledger's event-side
    aggregates with EXACT float equality across all FOUR venues, and each
    deal's spend is exactly qty x unit_price (2dp)."""
    _res, ledger, worlds = twin3
    for w in ("sticker", "snhp"):
        for v in FOUR:
            venue = worlds[w]["venues"][v]
            for d in range(3):
                assert (ledger.day_metrics(w, v, d)["revenue"]
                        == venue.revenue_by_day.get(d, 0.0))
    for e in ledger.events:
        if e["type"] == "deal":
            assert e["spend"] == round(e["qty"] * e["unit_price"], 2)
        elif e["type"] == "no_sale":
            assert "spend" not in e       # no money moves on a no-sale


def test_units_conservation(twin3):
    """Units vended never exceed units stocked (bought, for the one-buy
    boutique); the ledger's unit counts reconcile with every venue's own
    counters. Boba cups are made to order — their conservation law is the
    queue test below."""
    _res, ledger, worlds = twin3
    for w in ("sticker", "snhp"):
        for v in FOUR:
            venue = worlds[w]["venues"][v]
            if v != "boba":
                assert venue.units_vended <= venue.units_stocked
            ledger_units = sum(ledger.day_metrics(w, v, d)["units"]
                               for d in range(3))
            assert ledger_units == venue.units_vended


def test_boba_queue_conservation_on_the_block(twin3):
    """No cup and no pearl vanishes: per day, cups ORDERED (revenue booked)
    == cups SERVED by the bar + cups still in the queue/schedule at close;
    over the run, pearl servings COOKED == TAKEN by orders + WASTED (batch
    expiry + the 22:00 wash-up)."""
    _res, _ledger, worlds = twin3
    for w in ("sticker", "snhp"):
        b = worlds[w]["venues"]["boba"]
        for d in range(3):
            assert b.ordered_by_day.get(d, 0) == \
                b.served_by_day.get(d, 0) + b.leftover_by_day.get(d, 0)
        assert b.units_vended == sum(b.ordered_by_day.values())
        assert b.pearls_cooked == b.pearls_taken + b.pearls_wasted
        assert b.pearls_cooked % boba_world.BATCH_SERVINGS == 0


def test_boba_shop_hours_on_the_block_clock(twin3):
    """All boba traffic lives inside 10:00–22:00 (block ticks 18..89) —
    fashion's boutique and the street run the full block day around it."""
    _res, ledger, _worlds = twin3
    for e in ledger.events:
        if e.get("home") == "boba" or e.get("venue") == "boba":
            if e["type"] in ("arrival", "deal", "venue_entered"):
                assert BobaVenue.OPEN_TICK <= e["tick"] < BobaVenue.CLOSE_TICK


def test_every_arrival_resolves(twin3):
    """No shopper vanishes: arrivals == deals + no_sales, per world —
    including fashion waiter returns (each return is its own arrival)."""
    _res, ledger, _worlds = twin3
    for w in ("sticker", "snhp"):
        evs = [e for e in ledger.events if e["world"] == w]
        n = {t: sum(1 for e in evs if e["type"] == t)
             for t in ("arrival", "deal", "no_sale", "venue_entered")}
        assert n["arrival"] == n["deal"] + n["no_sale"]
        assert n["venue_entered"] == n["deal"]


def test_delta_decomposition_is_exact(twin3):
    """The HUD counters decompose: block delta == sum of the FOUR per-venue
    deltas (bitwise, by construction) and matches an independent
    recomputation."""
    _res, ledger, _worlds = twin3
    assert ledger.venues == FOUR
    for d in range(3):
        for m in ("margin", "revenue", "consumer_surplus", "units"):
            parts = sum(ledger.day_delta(v, d, m) for v in FOUR)
            assert ledger.block_day_delta(d, m) == parts
            recomputed = (
                sum(ledger.day_metrics("snhp", v, d)[m] for v in FOUR)
                - sum(ledger.day_metrics("sticker", v, d)[m] for v in FOUR))
            assert math.isclose(parts, recomputed, rel_tol=0, abs_tol=1e-9)


def test_fashion_paired_ci_uses_seven_day_blocks(twin3):
    """Priority #2 recalibration (paper/CALIBRATION-TARGETS.md; pre-
    registered CRITICAL-ANALYSIS.md §5): fashion reprices weekly, so a
    5-day block CI aliases the cadence — fashion's venue-level paired delta
    uses 7-day blocks; every other venue (and the block-level aggregate,
    which mixes cadences) keeps the 5-day default."""
    res, _ledger, _worlds = twin3
    pd = res["paired_deltas"]
    assert pd["fashion"]["margin"]["block"] == 7
    for v in ("vending", "bodega", "boba"):
        assert pd[v]["margin"]["block"] == 5
    assert pd["block"]["margin"]["block"] == 5


def test_hud_sums_all_four_venues(twin3):
    """The HUD counters are the season sums of the block-level per-day
    deltas — i.e. all four venues, nothing else."""
    res, ledger, _worlds = twin3
    days = res["config"]["days"]
    assert res["hud"]["shoppers_kept_usd"] == round(sum(
        ledger.block_day_delta(d, "consumer_surplus") for d in range(days)), 2)
    assert res["hud"]["merchants_earned_usd"] == round(sum(
        ledger.block_day_delta(d, "margin") for d in range(days)), 2)


def test_rents_subtract_from_margin(twin3):
    """NYC margins read against fixed costs, venue by venue: bodega
    $400/day, boba $330/day, fashion $620/day; the rent-free machine loses
    only spoilage."""
    _res, ledger, _worlds = twin3
    expected = {"vending": 0.0,
                "bodega": calibration.BODEGA_RENT_PER_DAY,
                "boba": calibration.BOBA_RENT_PER_DAY,
                "fashion": calibration.FASHION_RENT_PER_DAY}
    for v, rent in expected.items():
        m = ledger.day_metrics("sticker", v, 0)
        assert m["rent"] == rent
        assert m["margin"] == m["revenue"] - m["cogs"] - m["spoilage_cost"] - rent


# ── determinism ──────────────────────────────────────────────────────────

def test_full_twin_run_is_deterministic():
    """Byte-identical: the entire four-venue results dict (minus wall-clock
    meta) reproduces exactly, twice, from the same seed."""
    r1, _, _ = run_twin(days=2, seed=11)
    r2, _, _ = run_twin(days=2, seed=11)
    r1.pop("meta"); r2.pop("meta")
    assert r1 == r2
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ── fashion: the weekly season inside the daily block ────────────────────

def test_fashion_season_advances_exactly_every_seven_days():
    """Week boundaries land on day % 7 == 0 and nowhere else, for the whole
    14-week season; the week index clamps at the season's last week."""
    cfg = BlockConfig(sigma_cal=0.0)
    plan = build_fashion_plan(cfg, SEED)
    v = FashionVenue("sticker", cfg, SEED, plan=plan)
    weeks_seen, prev = [], -1
    for day in range(FashionVenue.SEASON_WEEKS * 7 + 7):
        v.begin_day(day)
        if v.week != prev:
            assert day % 7 == 0            # boundaries land on week starts
            weeks_seen.append(v.week)
            prev = v.week
        assert v.week == min(day // 7, FashionVenue.SEASON_WEEKS - 1)
    assert weeks_seen == list(range(FashionVenue.SEASON_WEEKS))


def test_fashion_cliff_schedule_respected_in_sticker_world():
    """The sticker boutique posts the industry calendar exactly: MSRP weeks
    0–6, −30% weeks 7–9, −50% weeks 10–12, −70% week 13 — per style,
    uniform across sizes, blind to stock."""
    cfg = BlockConfig(sigma_cal=0.0)
    catalog, depth = build_fashion_plan(cfg, SEED)
    v = FashionVenue("sticker", cfg, SEED, plan=(catalog, depth))
    for day in range(FashionVenue.SEASON_WEEKS * 7):
        v.begin_day(day)
        week = day // 7
        mult = population.fashion_cliff_mult(week)
        assert {1.0: 1.0, 0.7: 0.7, 0.5: 0.5, 0.3: 0.3}[mult] == mult
        for (style, size), price in v.board.items():
            assert price == round(catalog[style].msrp * mult, 2)
    assert population.fashion_cliff_mult(0) == 1.0
    assert population.fashion_cliff_mult(6) == 1.0
    assert population.fashion_cliff_mult(7) == 0.70
    assert population.fashion_cliff_mult(10) == 0.50
    assert population.fashion_cliff_mult(13) == 0.30


def test_fashion_markdowns_are_permanent_and_discount_only():
    """The SNHP boutique's weekly re-solve can only cut: per style×size,
    prices never rise week over week and never exceed MSRP."""
    cfg = BlockConfig(sigma_cal=0.15)
    catalog, depth = build_fashion_plan(cfg, SEED)
    v = FashionVenue("snhp", cfg, SEED, plan=(catalog, depth))
    last = {}
    for day in range(FashionVenue.SEASON_WEEKS * 7):
        v.begin_day(day)
        if day % 7:
            continue
        for cell, p in v.board.items():
            assert p <= catalog[cell[0]].msrp + 1e-9
            assert p <= last.get(cell, float("inf")) + 1e-9
            last[cell] = p


def test_fashion_one_buy_no_restock(twin3):
    """ONE buy at block day 0: both worlds inherit the SAME depth (paired),
    stocked units never grow, and inventory + sales reconcile exactly."""
    _res, _ledger, worlds = twin3
    st = worlds["sticker"]["venues"]["fashion"]
    sn = worlds["snhp"]["venues"]["fashion"]
    assert st.depth == sn.depth                      # the identical buy
    for v in (st, sn):
        assert v.units_stocked == sum(v.depth.values())
        assert v.units_vended + sum(v.inv.values()) == v.units_stocked


def test_fashion_week_boundary_prices_hold_within_the_week():
    """Multi-timescale correctness end-to-end: an 9-day fashion-only twin —
    every deal's price equals the standing weekly board (constant within a
    week per cell, may change only at day 7), and waiter returns land
    exactly at tick 0 of week boundaries."""
    res, ledger, _worlds = run_twin(days=9, seed=SEED, venues=("fashion",))
    seen = {}
    for e in ledger.events:
        if e["type"] == "deal":
            key = (e["world"], e["day"] // 7, e["sku"], e["size"])
            seen.setdefault(key, set()).add(e["unit_price"])
        elif e["type"] == "arrival" and e["kind"] == "return":
            assert e["day"] % 7 == 0 and e["tick"] == 0
    assert seen
    for key, prices in seen.items():
        assert len(prices) == 1        # one price per (world, week, cell)
    returns = [e for e in ledger.events
               if e["type"] == "arrival" and e["kind"] == "return"]
    assert returns                     # waiters actually came back on day 7


@pytest.mark.slow
def test_fashion_full_season_sell_through_is_not_saturated():
    """Priority #2 recalibration: BEFORE the fix, a full 98-day (14-week)
    season sold 100.0% of the buy in BOTH worlds — a scarcity-mechanism-
    killing artifact (RESULTS-B1B2.md Surprise 3). At the recalibrated
    arrival scale the STICKER (cliff) arm's sell-through lands measurably
    below 100%, in the standalone fashion/ sim's own realistic range."""
    _res, _ledger, worlds = run_twin(
        days=FashionVenue.SEASON_WEEKS * 7, seed=SEED, venues=("fashion",))
    st = worlds["sticker"]["venues"]["fashion"]
    sell_through = 100.0 * st.units_vended / st.units_stocked
    assert 70.0 < sell_through < 99.0


def test_fashion_season_end_writedown_reconciles():
    """A no-sales season books the whole buy as writedown on the last day:
    (cost − salvage) per unit — which makes the ledger's season total equal
    fashion/'s gross margin (revenue + salvage − buy cost) exactly."""
    cfg = BlockConfig(sigma_cal=0.0)
    catalog, depth = build_fashion_plan(cfg, SEED)
    v = FashionVenue("sticker", cfg, SEED, plan=(catalog, depth))
    for day in range(FashionVenue.SEASON_WEEKS * 7):
        v.begin_day(day)
        eod = v.end_day(day)
        if day < FashionVenue.SEASON_WEEKS * 7 - 1:
            assert eod == {"spoiled_units": 0, "spoilage_cost": 0.0}
    assert eod["spoiled_units"] == sum(depth.values())
    expected = sum(n * (catalog[st].unit_cost - catalog[st].salvage)
                   for (st, _sz), n in depth.items())
    assert eod["spoilage_cost"] == round(expected, 2)


# ── the bodega adoption toggle (B2) ──────────────────────────────────────

def test_bodega_adoption_changes_only_the_snhp_world(adopt_pair):
    """The toggle's isolation guarantee: flipping bodega_adopts leaves the
    sticker world's every event byte-identical; the SNHP world diverges,
    and ONLY there do bodega-negotiated deals exist."""
    (res_off, led_off, _), (res_on, led_on, _) = adopt_pair
    def world_events(led, w):
        return [e for e in led.events if e["world"] == w]
    assert world_events(led_off, "sticker") == world_events(led_on, "sticker")
    assert world_events(led_off, "snhp") != world_events(led_on, "snhp")
    def bodega_negotiated(led):
        return [e for e in led.events if e["type"] == "deal"
                and e["venue"] == "bodega" and e.get("negotiated")]
    assert not bodega_negotiated(led_off)          # default preserves B0
    on = bodega_negotiated(led_on)
    assert on and all(e["world"] == "snhp" for e in on)
    assert res_off["config"]["bodega_adopts"] is False
    assert res_on["config"]["bodega_adopts"] is True


def test_adopted_bodega_quotes_are_discount_only_and_rational(adopt_pair):
    """The adopted bodega's brokered quotes obey the same protocol
    invariants as the machine's: at or under its own POSTED price, and the
    buyer strictly better off net of the walk they actually incurred."""
    _off, (res_on, led_on, _worlds) = adopt_pair
    posted = {i: p for i, p, _ in calibration.BODEGA_CATALOG}
    deals = [e for e in led_on.events if e["type"] == "deal"
             and e["venue"] == "bodega" and e.get("negotiated")]
    assert deals
    for e in deals:
        assert e["unit_price"] <= posted[e["sku"]] + 1e-9
        assert e["surplus"] > 0


# ── composition: the block is one economy, not four sims side by side ────

def test_cross_venue_substitution_fires():
    """Raise the machine's prices (anchor probe) and the same seeded crowd
    walks: bodega deals rise, vending deals fall. The machine's outside
    option is the actual bodega — endogenously, not by formula."""
    def deals(anchor):
        led = BlockLedger(rents={"vending": 0.0,
                                 "bodega": calibration.BODEGA_RENT_PER_DAY})
        run_world("sticker", days=2, seed=SEED,
                  cfg=BlockConfig(anchor_mult=anchor), ledger=led,
                  venues=("vending", "bodega"))
        return {v: sum(led.day_metrics("sticker", v, d)["deals"]
                       for d in range(2)) for v in ("vending", "bodega")}
    base, anchored = deals(1.0), deals(1.5)
    assert anchored["vending"] < base["vending"]
    assert anchored["bodega"] > base["bodega"]


def test_regulars_churn_only_in_the_world_that_shocks_them():
    """The fairness layer composes onto the block: under an aggressive
    anchor the sticker world's regulars take sticker shock and churn; the
    SNHP world's regulars get brokered quotes near their reference and
    mostly stay. Same seeded pool, same visit draws — divergence is the
    treatment. (Two-venue subset: the fairness pool rides the machine.)"""
    cfg = BlockConfig(anchor_mult=1.5, regulars=25)
    res, _ledger, _worlds = run_twin(days=10, seed=SEED, cfg=cfg,
                                     venues=("vending", "bodega"))
    churn = {w: sum(c["churned"] for c in res["per_world"][w]["churn"])
             for w in ("sticker", "snhp")}
    assert churn["sticker"] > 0
    assert churn["snhp"] < churn["sticker"]
    active = {w: res["per_world"][w]["churn"][-1]["active"]
              for w in ("sticker", "snhp")}
    assert active["snhp"] >= active["sticker"]


def test_regular_pool_is_identical_across_worlds():
    """Fairness treatment isolation: both worlds start from the same seeded
    regulars (uid, tastes, habits) — divergence is earned, not sampled."""
    cat = build_block_catalog(BlockConfig(), SEED)
    p1 = BlockRegularPool(10, SEED, cat)
    p2 = BlockRegularPool(10, SEED, cat)
    for a, b in zip(p1.pool, p2.pool):
        assert (a.uid, a.wtp, a.walk_cost, a.visit_prob, a.home_tick) == \
               (b.uid, b.wtp, b.walk_cost, b.visit_prob, b.home_tick)
        assert a.ref == b.ref


def test_venues_flag_selects_subsets():
    """--venues machinery: aliases resolve, junk rejects, and a two-venue
    twin carries exactly those venues in the ledger, results, and HUD."""
    assert parse_venues("vend,bodega") == ("vending", "bodega")
    assert parse_venues("vend,bodega,boba,fashion") == FOUR
    with pytest.raises(ValueError):
        parse_venues("vend,discotheque")
    with pytest.raises(ValueError):
        parse_venues("")
    res, ledger, worlds = run_twin(days=1, seed=SEED,
                                   venues=("vending", "bodega"))
    assert ledger.venues == ("vending", "bodega")
    assert set(res["per_world"]["snhp"]["venues"]) == {"vending", "bodega"}
    assert set(res["paired_deltas"]) == {"vending", "bodega", "block"}
    homes = {e.get("home") for e in ledger.events if e["type"] == "arrival"}
    assert homes <= {"vending", "bodega"}    # boba/fashion walkers ignored


# ── performance budget & artifact reproducibility ────────────────────────

@pytest.mark.slow
def test_thirty_day_four_venue_twin_fits_the_budget():
    """A 30-day twin of the FOUR-venue block on one core: target < 30s,
    asserted at the scoped 120s."""
    t0 = time.perf_counter()
    res, _ledger, _worlds = run_twin(days=30, seed=7)
    elapsed = time.perf_counter() - t0
    assert elapsed < 120.0
    for v in FOUR:
        assert res["per_world"]["snhp"]["venues"][v]["totals"]["deals"] > 0


@pytest.mark.slow
def test_committed_results_stay_reproducible():
    """block/results.json must remain exactly reproducible at the config IT
    records (params read from the artifact, not hardcoded) — byte-level
    minus the wall-clock meta."""
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "results.json"
    committed = json.load(open(path))
    c = committed["config"]
    cfg = BlockConfig(sigma_cal=c["sigma_cal"], anchor_mult=c["anchor_mult"],
                      regulars=c["regulars"], bodega_adopts=c["bodega_adopts"])
    res, _ledger, _worlds = run_twin(days=c["days"], seed=c["seed"], cfg=cfg,
                                     venues=tuple(c["venues"]))
    res.pop("meta")
    committed.pop("meta")
    assert json.dumps(res, sort_keys=True) == json.dumps(committed, sort_keys=True)

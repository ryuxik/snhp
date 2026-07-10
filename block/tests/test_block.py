"""BLOCK B0 tests: conservation laws hold to the float, determinism is
byte-level, the population stream is world-independent by construction,
NYC prices flow end-to-end, and the block composes (substitution, rents,
fairness) instead of just co-locating two sims."""
import json
import math
import time

import numpy as np
import pytest

from block import calibration, population
from block.ledger import BlockLedger
from block.runner import run_twin, run_world
from block.venues import (BlockConfig, BlockRegularPool, BodegaVenue,
                          VendingVenue, build_block_catalog)
from vend.world import TICKS_PER_DAY, _profit_optimal_list_price, hour_of

SEED = 20260710
RENTS = {"vending": VendingVenue.rent_per_day,
         "bodega": BodegaVenue.rent_per_day}


@pytest.fixture(scope="module")
def twin3():
    """One 3-day twin run shared by the accounting tests."""
    return run_twin(days=3, seed=SEED)


# ── population: pairing, calibration, personas ───────────────────────────

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


def test_both_worlds_consumed_the_same_arrivals(twin3):
    """End-to-end pairing: the arrival events the two worlds actually
    processed are identical (uid, persona, home, tick), day by day."""
    _res, ledger, _worlds = twin3
    def stream(world):
        return [(e["day"], e["tick"], e["uid"], e["persona"], e["home"])
                for e in ledger.events
                if e["type"] == "arrival" and e["world"] == world]
    assert stream("sticker") == stream("snhp")


def test_funnel_is_derived_from_calibration_targets():
    """SHOPPER_FRACTION is derived, not tuned: analytic daily totals equal
    the calibration targets exactly; simulated arrivals track them."""
    exp = population.expected_daily()
    assert exp["shoppers"] == pytest.approx(
        calibration.VENDING_DAILY_ARRIVALS + calibration.BODEGA_DAILY_TX)
    assert exp["vending_home"] == pytest.approx(calibration.VENDING_DAILY_ARRIVALS)
    assert exp["bodega_home"] == pytest.approx(calibration.BODEGA_DAILY_TX)
    days = 10
    tot = vend_home = 0
    for d in range(days):
        for t, shoppers in population.day_stream(SEED, d).items():
            tot += len(shoppers)
            vend_home += sum(1 for s in shoppers if s.home == "vending")
    assert tot / days == pytest.approx(exp["shoppers"], rel=0.10)
    assert vend_home / days == pytest.approx(exp["vending_home"], rel=0.25)


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
    """One WTP per GOOD: vending SKUs + bodega items, overlap counted once
    (cola-20oz and chips exist in both catalogs but appear once)."""
    assert len(population.GOODS) == len(set(population.GOODS)) == 11
    assert "cola-20oz" in population.VENDING_GOODS
    assert "cola-20oz" in population.BODEGA_GOODS
    sh = population.sample_shopper(SEED, 0, 30, "office-worker", 0)
    assert set(sh.wtp) == set(population.GOODS)
    assert population.GOOD_MU["cola-20oz"] == 3.40   # vending mu wins overlap


def test_persona_wtp_multiplier_orders_the_draws():
    """tourist (×1.25) outbids student (×0.72) in expectation."""
    def mean_wtp(persona):
        draws = [population.sample_shopper(SEED, 0, 60, persona, k).wtp["coffee"]
                 for k in range(200)]
        return float(np.mean(draws))
    assert mean_wtp("tourist") > mean_wtp("student") * 1.3


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
    """B0: the bodega has NOT adopted SNHP — same posted prices, both
    worlds, straight from calibration."""
    posted = {i: p for i, p, _ in calibration.BODEGA_CATALOG}
    assert BodegaVenue("sticker").prices == posted
    assert BodegaVenue("snhp").prices == posted


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
    """Rational acceptance held: every negotiated deal left the buyer with
    strictly positive net surplus (already net of any walk incurred)."""
    _res, ledger, _worlds = twin3
    deals = [e for e in ledger.events
             if e["type"] == "deal" and e.get("negotiated")]
    assert deals and all(e["surplus"] > 0 for e in deals)
    assert all(e["world"] == "snhp" for e in deals)   # no negotiation surface
                                                      # exists in the sticker world


# ── conservation laws ────────────────────────────────────────────────────

def test_money_conservation_is_exact(twin3):
    """Every consumer dollar spent equals some venue's revenue — venue-side
    per-day tills (accumulated at settle) match the ledger's event-side
    aggregates with EXACT float equality, and each deal's spend is exactly
    qty x unit_price (2dp)."""
    _res, ledger, worlds = twin3
    for w in ("sticker", "snhp"):
        for v in ("vending", "bodega"):
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
    """Units vended never exceed units stocked; the ledger's unit counts
    reconcile with the venues' own counters."""
    _res, ledger, worlds = twin3
    for w in ("sticker", "snhp"):
        for v in ("vending", "bodega"):
            venue = worlds[w]["venues"][v]
            assert venue.units_vended <= venue.units_stocked
            ledger_units = sum(ledger.day_metrics(w, v, d)["units"]
                               for d in range(3))
            assert ledger_units == venue.units_vended


def test_every_arrival_resolves(twin3):
    """No shopper vanishes: arrivals == deals + no_sales, per world."""
    _res, ledger, _worlds = twin3
    for w in ("sticker", "snhp"):
        evs = [e for e in ledger.events if e["world"] == w]
        n = {t: sum(1 for e in evs if e["type"] == t)
             for t in ("arrival", "deal", "no_sale", "venue_entered")}
        assert n["arrival"] == n["deal"] + n["no_sale"]
        assert n["venue_entered"] == n["deal"]


def test_delta_decomposition_is_exact(twin3):
    """The HUD counters decompose: block delta == sum of per-venue deltas
    (bitwise, by construction) and matches an independent recomputation."""
    _res, ledger, _worlds = twin3
    for d in range(3):
        for m in ("margin", "revenue", "consumer_surplus", "units"):
            parts = sum(ledger.day_delta(v, d, m) for v in ("vending", "bodega"))
            assert ledger.block_day_delta(d, m) == parts
            recomputed = (
                sum(ledger.day_metrics("snhp", v, d)[m] for v in ("vending", "bodega"))
                - sum(ledger.day_metrics("sticker", v, d)[m] for v in ("vending", "bodega")))
            assert math.isclose(parts, recomputed, rel_tol=0, abs_tol=1e-9)


def test_rents_subtract_from_margin(twin3):
    """NYC margins read against fixed costs: bodega margin loses exactly
    $400/day of rent; the rent-free machine loses only spoilage."""
    _res, ledger, _worlds = twin3
    b = ledger.day_metrics("sticker", "bodega", 0)
    assert b["rent"] == calibration.BODEGA_RENT_PER_DAY == 400
    assert b["margin"] == b["revenue"] - b["cogs"] - b["spoilage_cost"] - 400
    v = ledger.day_metrics("sticker", "vending", 0)
    assert v["rent"] == 0.0
    assert v["margin"] == v["revenue"] - v["cogs"] - v["spoilage_cost"]


# ── determinism ──────────────────────────────────────────────────────────

def test_full_twin_run_is_deterministic():
    """Byte-identical: the entire results dict (minus wall-clock meta)
    reproduces exactly, twice, from the same seed."""
    r1, _, _ = run_twin(days=2, seed=11)
    r2, _, _ = run_twin(days=2, seed=11)
    r1.pop("meta"); r2.pop("meta")
    assert r1 == r2
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ── composition: the block is one economy, not two sims side by side ─────

def test_cross_venue_substitution_fires():
    """Raise the machine's prices (anchor probe) and the same seeded crowd
    walks: bodega deals rise, vending deals fall. The machine's outside
    option is the actual bodega — endogenously, not by formula."""
    def deals(anchor):
        led = BlockLedger(rents=RENTS)
        run_world("sticker", days=2, seed=SEED,
                  cfg=BlockConfig(anchor_mult=anchor), ledger=led)
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
    treatment."""
    cfg = BlockConfig(anchor_mult=1.5, regulars=25)
    res, _ledger, _worlds = run_twin(days=10, seed=SEED, cfg=cfg)
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


# ── performance budget ───────────────────────────────────────────────────

@pytest.mark.slow
def test_thirty_day_twin_fits_the_budget():
    """A 30-day twin of the two-venue block on one core: target < 60s,
    asserted at a generous 120s."""
    t0 = time.perf_counter()
    res, _ledger, _worlds = run_twin(days=30, seed=7)
    elapsed = time.perf_counter() - t0
    assert elapsed < 120.0
    assert res["per_world"]["snhp"]["venues"]["vending"]["totals"]["deals"] > 0

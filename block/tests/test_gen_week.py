"""block/gen_week.py — the street scene's numbers are REAL and reproducible.

The renderer (block/web/) authors no magnitudes; they all live in
web/canned-week.json, which is generated from the committed twin. These
tests are the honesty gate: the committed JSON must regenerate byte-for-byte
from the seed, and its dollar figures must equal an INDEPENDENT recompute of
the same run (not just whatever the generator happened to emit).
"""
import json
import pathlib

import pytest

from block.gen_week import (DAYS, DAY_WEIGHT, PROJECT_DAYS, build_week,
                            main as gen_main)
from block.runner import ALL_VENUES, run_twin
from block.venues import BlockConfig

CANNED = pathlib.Path(__file__).parents[1] / "web" / "canned-week.json"


def test_day_weight_starts_identical_and_is_seven_days():
    """The "blocks start identical" gate: day 0 divergence is exactly 0, and
    the ramp spans the 7 timelapse days the renderer clocks."""
    assert DAY_WEIGHT[0] == 0.0
    assert len(DAY_WEIGHT) == PROJECT_DAYS == 7
    assert DAY_WEIGHT[-1] == 1.0
    assert DAY_WEIGHT == sorted(DAY_WEIGHT)          # monotone divergence


@pytest.mark.slow
def test_build_week_is_deterministic():
    """Same config → identical bytes (no wall clock in the document)."""
    a = json.dumps(build_week(), indent=2, sort_keys=True)
    b = json.dumps(build_week(), indent=2, sort_keys=True)
    assert a == b


@pytest.mark.slow
def test_committed_canned_week_regenerates_byte_for_byte():
    """web/canned-week.json must be exactly what `python3 -m block.gen_week`
    writes — the on-screen numbers are the committed run, not hand-authored."""
    regenerated = json.dumps(build_week(), indent=2) + "\n"
    committed = CANNED.read_text()
    assert regenerated == committed, (
        "canned-week.json is stale — rerun `python3 -m block.gen_week`")


@pytest.mark.slow
def test_hud_counters_equal_an_independent_recompute():
    """block_mature (what the HUD integrates) must equal the run's mean daily
    paired Δ — recomputed here straight off the ledger, no generator help."""
    doc = build_week()
    cfg = BlockConfig(sigma_cal=doc["meta"]["config"]["sigma_cal"],
                      anchor_mult=doc["meta"]["config"]["anchor_mult"],
                      regulars=doc["meta"]["config"]["regulars"],
                      bodega_adopts=doc["meta"]["config"]["bodega_adopts"])
    _res, ledger, _worlds = run_twin(DAYS, doc["meta"]["config"]["seed"], cfg,
                                     venues=ALL_VENUES)
    merch = round(sum(ledger.day_delta(v, d, "margin")
                      for v in ALL_VENUES for d in range(DAYS)) / DAYS, 2)
    shop = round(sum(ledger.day_delta(v, d, "consumer_surplus")
                     for v in ALL_VENUES for d in range(DAYS)) / DAYS, 2)
    bm = doc["ledger"]["block_mature"]
    # block_mature is Σ(rounded per-venue), so allow ≤1¢/venue rounding drift
    assert abs(bm["merchant"] - merch) < 0.11
    assert abs(bm["shopper"] - shop) < 0.11
    # and it reconciles exactly with its per-venue components (what the schema
    # promises: the block counter is the sum of the venue deltas)
    pv = doc["ledger"]["per_venue_mature"]
    assert bm["merchant"] == round(sum(pv[v]["merchant"] for v in pv), 2)
    assert bm["shopper"] == round(sum(pv[v]["shopper"] for v in pv), 2)


@pytest.mark.slow
def test_receipt_savings_are_real_per_sku_surplus():
    """Each receipt template's dollar figure must be a real mean shopper
    saving from the SNHP world (never invented)."""
    from collections import defaultdict
    doc = build_week()
    c = doc["meta"]["config"]
    cfg = BlockConfig(sigma_cal=c["sigma_cal"], anchor_mult=c["anchor_mult"],
                      regulars=c["regulars"], bodega_adopts=c["bodega_adopts"])
    _res, ledger, _worlds = run_twin(DAYS, c["seed"], cfg, venues=ALL_VENUES)
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for e in ledger.events:
        if e.get("type") == "deal" and e.get("world") == "snhp":
            a = agg[e["venue"]][str(e.get("sku"))]
            a[0] += 1
            a[1] += float(e.get("surplus", 0.0))
    # every receipt amount matches some real per-SKU mean surplus at that venue
    for vid, pool in doc["crowd"]["receipt_pool"].items():
        real_means = {round(cnt and su / cnt, 2)
                      for cnt, su in agg[vid].values()}
        for _label, amt in pool:
            assert amt in real_means, f"{vid}: receipt ${amt} not a real save"


@pytest.mark.slow
def test_gen_week_main_writes_the_committed_file(tmp_path, monkeypatch):
    """`python3 -m block.gen_week` exits 0 and writes valid schema JSON."""
    # run against the real path is covered above; here just exercise main()
    rc = gen_main([])
    assert rc == 0
    doc = json.loads(CANNED.read_text())
    assert doc["schema"] == "block.week.v1"
    assert doc["meta"]["days"] == 7
    assert len(doc["venues"]) == 10

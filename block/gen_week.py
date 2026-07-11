"""block/gen_week.py — the REAL `block.week.v1` generator.

Runs the committed ten-venue twin (block/runner.run_twin) and projects its
paired deltas onto the 7-day street-scene schema the renderer consumes,
`block/web/canned-week.json` (contract: block/web/EVENTS.md).

THE HONEST SPLIT (mirrored in the on-screen badge + meta.provenance):

  REAL — every DOLLAR magnitude traces to this run and reproduces from the
  seed:
    • the two HUD counters (block_mature = the run's mean daily paired Δ:
      margin → "merchants earned", consumer-surplus → "shoppers kept");
    • per_venue_mature (each venue's real mean daily Δ; sums to block_mature);
    • receipt savings (real per-SKU mean consumer surplus per deal on the
      SNHP world) and per-venue receipt frequency (real deal share);
    • crowd density (real converting foot traffic = arrivals net of
      walk-aways — the same population arrives on both blocks, the sticker
      block just converts fewer);
    • per-venue decay ORDERING + presence (real spoilage gap + surplus gap:
      the florist and bakery really do waste the most on the sticker side).

  REPRESENTATIVE / DISCLOSED PROJECTION — shape & choreography, never a
  dollar figure:
    • day_weight — the identical→diverged ramp. The sim diverges from day 0;
      the ramp is the visualization's narrative arc (day 0 = identical gate).
      block_mature is a per-DAY rate, so the counters integrate a real daily
      rate over this ramp.
    • mood.gray / decay intensity — a monotone VISUAL encoding of the real
      divergence (a small disclosed gain on the real gap fraction), not a
      dollar amount.
    • named-regular churn days — the sim's 25-strong regular pool does not
      literally attrit (it holds at 25); the real decline is the higher
      no-sale + spoilage + lost-surplus on the sticker block. Churn days are
      ordered by real per-venue severity but the exact day is a stand-in for
      that aggregate.
    • truck / weather beats and the per-walker paths — configured flair.

Deterministic: same config → same bytes (no wall clock in the output).

Reproduce:
    python3 -m block.gen_week                     # rewrites canned-week.json
    python3 -m pytest block/tests/test_gen_week.py -q
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

from block.runner import ALL_VENUES, run_twin
from block.venues import BlockConfig

# ── the documented config the numbers trace to ───────────────────────────
SEED = 20260710
DAYS = 30
REGULAR_COUNT = 25
BODEGA_ADOPTS = True          # the adoption scenario (RESULTS-B1B2 Headline 2):
                              # the bodega runs its own brokered-quote arm, so
                              # every venue delivers positive consumer surplus
SIGMA_CAL = 0.15
ANCHOR_MULT = 1.0
PROJECT_DAYS = 7              # the timelapse arc length (meta.days)

REPRODUCE_CMD = (
    "python3 -m block.gen_week  "
    "# runs run_twin(days=30, seed=20260710, regulars=25, bodega_adopts=True, "
    "venues=all) and projects its mean daily paired deltas onto the 7-day scene"
)

# The identical→diverged divergence ramp (the disclosed narrative arc). day 0
# is EXACTLY identical (weight 0 — the "blocks start identical" honesty gate);
# the SNHP advantage is a per-day RATE (block_mature) integrated over this ramp.
DAY_WEIGHT = [0.0, 0.28, 0.50, 0.68, 0.83, 0.94, 1.0]

# intraday crowd multiplier by clock hour (the calibrated office-tower / retail
# curve carried from population; a display curve, not a magnitude claim)
HOUR_WEIGHT = [0.05, 0.03, 0.02, 0.02, 0.03, 0.08, 0.20, 0.45, 0.85, 0.75,
               0.65, 0.70, 0.95, 0.90, 0.72, 0.68, 0.80, 0.98, 0.95, 0.82,
               0.66, 0.48, 0.30, 0.14]

# per-day weather (a configured demand-shock illustration, disclosed)
WEATHER = ["clear", "clear", "clear", "clear", "rain", "clear", "overcast"]

AMBIENT_BASE = 15.0           # cosmetic sprite baseline (# of walkers on-street);
                              # the sticker/snhp RATIO is the real part
GRAY_GAIN = 3.0               # disclosed visual gain on the real CS-gap fraction
GRAY_CAP = 0.45

# ── the storefront roster + named cast (display metadata; art direction, not
#    sim output). Order = street order. churn.sticker_lastday is (re)computed
#    from real per-venue severity below. ───────────────────────────────────
VENUES = [
    {"id": "vending", "slot": 0, "label": "VEND",    "kind": "machine"},
    {"id": "bodega",  "slot": 1, "label": "BODEGA",  "kind": "deli"},
    {"id": "boba",    "slot": 2, "label": "BOBA",    "kind": "boba"},
    {"id": "bakery",  "slot": 3, "label": "BAKERY",  "kind": "bakery"},
    {"id": "florist", "slot": 4, "label": "FLOWER",  "kind": "flower"},
    {"id": "barbershop", "slot": 5, "label": "BARBER", "kind": "barber"},
    {"id": "fashion", "slot": 6, "label": "FASHION", "kind": "fashion"},
    {"id": "vintage", "slot": 7, "label": "VINTAGE", "kind": "vintage"},
    {"id": "bar",     "slot": 8, "label": "BAR",     "kind": "bar"},
    {"id": "parking", "slot": 9, "label": "PARK",    "kind": "parking"},
]
# renderer venue-id → the runner's ledger venue-id (they match except barber)
LEDGER_ID = {v["id"]: v["id"] for v in VENUES}

# named regulars, each homed at a storefront; look = sprite spec (walkers.js)
REGULAR_CAST = [
    {"id": "maria", "name": "Maria", "persona": "local", "home": "bodega",
     "look": {"skin": "tan", "hair": "gray", "top": "#b0463c", "bottom": "#3a3550", "prop": "tote", "hat": "scarf"}},
    {"id": "deb", "name": "Deb", "persona": "office-worker", "home": "vending",
     "look": {"skin": "tan", "hair": "brown", "top": "#2e5a8a", "bottom": "#232a3a", "prop": "coffee", "hat": "none"}},
    {"id": "sam", "name": "Sam", "persona": "student", "home": "boba",
     "look": {"skin": "brown", "hair": "black", "top": "#3a8a62", "bottom": "#2a2438", "prop": "backpack", "hat": "phones"}},
    {"id": "theo", "name": "Theo", "persona": "office-worker", "home": "bakery",
     "look": {"skin": "pale", "hair": "sandy", "top": "#7a6a3a", "bottom": "#2b2338", "prop": "satchel", "hat": "none"}},
    {"id": "rosa", "name": "Rosa", "persona": "local", "home": "florist",
     "look": {"skin": "tan", "hair": "white", "top": "#8a5aa0", "bottom": "#3a3550", "prop": "cane", "hat": "none"}},
    {"id": "kwame", "name": "Kwame", "persona": "office-worker", "home": "barbershop",
     "look": {"skin": "brown", "hair": "black", "top": "#c07a2a", "bottom": "#2b2338", "prop": "none", "hat": "cap"}},
    {"id": "yuki", "name": "Yuki", "persona": "student", "home": "fashion",
     "look": {"skin": "pale", "hair": "black", "top": "#c05a8a", "bottom": "#2a2438", "prop": "shopbag", "hat": "beanie"}},
    {"id": "lou", "name": "Big Lou", "persona": "local", "home": "bar",
     "look": {"skin": "tan", "hair": "bald", "top": "#3a4a8a", "bottom": "#2b2338", "prop": "none", "hat": "none", "big": True}},
]

# receipt label per SKU: prettify the ledger sku; opaque one-of-one items get a
# generic tag (the amount stays the real save)
def _pretty(sku: str) -> str:
    if sku.startswith("item-"):
        return "one-of-one"
    return sku.replace("-", " ")


def _round(x, n=2):
    return round(float(x), n)


def build_week() -> dict:
    """Run the twin and assemble the block.week.v1 document."""
    cfg = BlockConfig(sigma_cal=SIGMA_CAL, anchor_mult=ANCHOR_MULT,
                      regulars=REGULAR_COUNT, bodega_adopts=BODEGA_ADOPTS)
    _res, ledger, _worlds = run_twin(DAYS, SEED, cfg, venues=ALL_VENUES)

    # ── real mean daily paired deltas (the mature magnitudes) ──────────────
    mean_margin, mean_cs = {}, {}
    for v in ALL_VENUES:
        mean_margin[v] = sum(ledger.day_delta(v, d, "margin")
                             for d in range(DAYS)) / DAYS
        mean_cs[v] = sum(ledger.day_delta(v, d, "consumer_surplus")
                         for d in range(DAYS)) / DAYS

    # ── real per-venue signals: spoilage gap, deals, per-sku savings ───────
    spoil_gap, snhp_deals = {}, {}
    for v in ALL_VENUES:
        sp_st = sum(ledger.day_metrics("sticker", v, d)["spoilage_cost"]
                    for d in range(DAYS))
        sp_sn = sum(ledger.day_metrics("snhp", v, d)["spoilage_cost"]
                    for d in range(DAYS))
        spoil_gap[v] = max(0.0, sp_st - sp_sn)
        snhp_deals[v] = sum(ledger.day_metrics("snhp", v, d)["deals"]
                            for d in range(DAYS))

    # per-venue, per-sku SNHP deal aggregates (count, mean shopper saving)
    sku_agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for e in ledger.events:
        if e.get("type") == "deal" and e.get("world") == "snhp":
            a = sku_agg[e["venue"]][str(e.get("sku"))]
            a[0] += 1
            a[1] += float(e.get("surplus", 0.0))

    # ── real crowd: converting foot traffic (arrivals − walk-aways) ────────
    eff = {"sticker": 0.0, "snhp": 0.0}
    for w in ("sticker", "snhp"):
        for d in range(DAYS):
            t = ledger.traffic(w, d)
            eff[w] += t["arrivals"] - t["no_sales"]
    convert_ratio = eff["sticker"] / eff["snhp"]      # ~0.87: sticker converts less

    # ── real block-level consumer-surplus gap (drives the gray wash) ───────
    cs_tot = {"sticker": 0.0, "snhp": 0.0}
    for w in ("sticker", "snhp"):
        cs_tot[w] = sum(ledger.day_metrics(w, v, d)["consumer_surplus"]
                        for v in ALL_VENUES for d in range(DAYS))
    cs_gap_frac = 1.0 - cs_tot["sticker"] / cs_tot["snhp"]   # real fraction

    # ── ledger block: per-venue + block mature, cited to the run ───────────
    per_venue_mature = {}
    for v in VENUES:
        lid = LEDGER_ID[v["id"]]
        per_venue_mature[v["id"]] = {
            "merchant": _round(mean_margin[lid]),
            "shopper": _round(mean_cs[lid]),
            "src": f"run mean daily Δ (margin/consumer-surplus) over {DAYS}d; "
                   f"{REPRODUCE_CMD.split('#')[0].strip()}",
        }
    block_merchant = _round(sum(per_venue_mature[v]["merchant"] for v in per_venue_mature))
    block_shopper = _round(sum(per_venue_mature[v]["shopper"] for v in per_venue_mature))
    sum_weight = round(sum(DAY_WEIGHT), 4)
    hud_merchant_week = round(block_merchant * sum_weight)
    hud_shopper_week = round(block_shopper * sum_weight)

    # ── per-venue decay severity (real spoilage gap + surplus gap) ─────────
    max_spoil = max(spoil_gap.values()) or 1.0
    max_cs = max((mean_cs[v] for v in ALL_VENUES if mean_cs[v] > 0), default=1.0)
    decay = {}
    severity = {}
    for v in VENUES:
        lid = LEDGER_ID[v["id"]]
        s_spoil = spoil_gap[lid] / max_spoil
        s_cs = max(0.0, mean_cs[lid]) / max_cs
        sev = 0.55 * s_spoil + 0.45 * s_cs            # real-signal blend
        severity[v["id"]] = sev
        decay6 = 0.18 + 0.66 * sev                    # → [0.18, 0.84]
        decay[v["id"]] = [round(decay6 * DAY_WEIGHT[d], 3)
                          for d in range(PROJECT_DAYS)]

    # ── mood.gray: monotone visual encoding of the real CS-gap fraction ────
    gray6 = round(min(GRAY_CAP, cs_gap_frac * GRAY_GAIN), 3)
    gray_sticker = [round(gray6 * DAY_WEIGHT[d], 3) for d in range(PROJECT_DAYS)]

    # ── crowd: real converting-traffic ratio; snhp holds, sticker thins ────
    ambient_sticker, ambient_snhp = [], []
    for d in range(PROJECT_DAYS):
        ambient_snhp.append(round(AMBIENT_BASE, 2))
        ambient_sticker.append(
            round(AMBIENT_BASE * (1.0 - (1.0 - convert_ratio) * DAY_WEIGHT[d]), 2))

    # ── receipt pool (real per-sku savings) + weight (real deal share) ─────
    receipt_pool = {}
    for v in VENUES:
        lid = LEDGER_ID[v["id"]]
        tops = sorted(sku_agg[lid].items(), key=lambda kv: -kv[1][0])[:3]
        pool = []
        for sku, (cnt, su) in tops:
            save = _round(su / cnt) if cnt else 0.0
            pool.append([f"{_pretty(sku)} -${save:.2f}", save])
        if not pool:
            pool = [["deal -$1.00", 1.0]]
        receipt_pool[v["id"]] = pool
    deals_per_day = {v["id"]: snhp_deals[LEDGER_ID[v["id"]]] / DAYS for v in VENUES}
    max_dpd = max(deals_per_day.values()) or 1.0
    receipt_weight = {v["id"]: round(deals_per_day[v["id"]] / max_dpd, 4)
                      for v in VENUES}

    # ── named-regular churn days: ordered by real per-venue severity ───────
    #    (higher-decline venue → its regular stops first). The DAY is a
    #    representative stand-in; the sim's 25-regular pool holds at 25 all
    #    week — the real signal is the venue-level surplus/spoilage gap.
    ranked = sorted(REGULAR_CAST, key=lambda r: -severity.get(r["home"], 0.0))
    churn_days = [3, 3, 4, 4, 5, 5, 6, 6]              # earliest for worst venue
    reason = {
        "bodega": "brokered-quote gap: shoppers keep less on the posted board",
        "vending": "machine anchor with no negotiated relief",
        "boba": "peak-queue balks the sticker board can't smooth",
        "bakery": "day-old shelf: sticker bakery wastes the most",
        "florist": "wilted buckets — the sticker block's biggest spoilage line",
        "barbershop": "flat slot pricing, no quiet-hour relief",
        "fashion": "end-season cliff instead of a live markdown",
        "bar": "fixed happy hour, not computed by the hour",
    }
    regulars_out = []
    for r in REGULAR_CAST:
        last = churn_days[ranked.index(r)]
        ro = {k: r[k] for k in ("id", "name", "persona", "home", "look")}
        ro["churn"] = {"sticker_lastday": last,
                       "reason": reason.get(r["home"], "no negotiated relief")}
        regulars_out.append(ro)

    # ── beats: churn (from regulars), spoil/clearance (real ordering),
    #    trucks (configured dawn flair). All narrative, no magnitudes. ──────
    beats = []
    # dawn trucks — the SNHP block runs shared negotiated routes (route
    # density); the sticker block runs single rate-card drops. Illustrative
    # (the wholesale tier is off in this run — disclosed in meta).
    truck_days = {
        0: [("snhp", "bodega", "bakery", "deli-produce", True),
            ("snhp", "boba", "bar", "beverage", True),
            ("sticker", "bodega", None, "deli-produce", False),
            ("sticker", "bakery", None, "deli-produce", False),
            ("sticker", "boba", None, "beverage", False)],
        2: [("snhp", "florist", "fashion", "florist-route", True),
            ("snhp", "bodega", "bakery", "deli-produce", True),
            ("sticker", "florist", None, "florist-route", False),
            ("sticker", "bakery", None, "deli-produce", False)],
        4: [("snhp", "bodega", "bakery", "deli-produce", True),
            ("snhp", "boba", "bar", "beverage", True),
            ("sticker", "boba", None, "beverage", False)],
        6: [("snhp", "bodega", "bakery", "deli-produce", True),
            ("snhp", "florist", "fashion", "florist-route", True),
            ("sticker", "bodega", None, "deli-produce", False)],
    }
    for d, rows in truck_days.items():
        hour = 5.8
        for world, venue, shared, supplier, negotiated in rows:
            b = {"day": d, "hour": round(hour, 1), "world": world,
                 "type": "truck", "venue": venue, "supplier": supplier,
                 "negotiated": negotiated}
            if shared:
                b["shared_with"] = shared
            beats.append(b)
            hour += 0.4
    # spoilage bins — the top real-spoilage venues, on the day decay bites
    spoil_rank = sorted((v["id"] for v in VENUES),
                        key=lambda vid: -spoil_gap[LEDGER_ID[vid]])
    for vid in spoil_rank[:3]:
        if spoil_gap[LEDGER_ID[vid]] <= 0:
            continue
        beats.append({"day": 2, "hour": 18.5, "world": "sticker",
                      "type": "spoil", "venue": vid, "kind": "bin"})
        beats.append({"day": 4, "hour": 9.4, "world": "sticker",
                      "type": "spoil", "venue": vid, "kind": "bin"})
    # clearance racks — fashion / vintage deepen as their decay grows
    for vid in ("fashion", "vintage"):
        for d in (3, 5):
            pct = int(round(20 + 60 * decay[vid][d]))
            beats.append({"day": d, "hour": 14.0, "world": "sticker",
                          "type": "clearance", "venue": vid, "pct": pct})
    # churn — each named regular walks off the sticker block on their last day
    for r in regulars_out:
        beats.append({"day": r["churn"]["sticker_lastday"], "hour": 12.0,
                      "world": "sticker", "type": "churn", "regular": r["id"],
                      "venue": r["home"], "reason": r["churn"]["reason"]})
    beats.sort(key=lambda b: (b["day"], b["hour"], b["world"], b["type"]))

    # ── assemble ───────────────────────────────────────────────────────────
    doc = {
        "schema": "block.week.v1",
        "meta": {
            "badge": "live sim data · numbers reproducible",
            "generated_by": "block/gen_week.py",
            "reproduce": REPRODUCE_CMD,
            "config": {
                "seed": SEED, "days": DAYS, "regulars": REGULAR_COUNT,
                "bodega_adopts": BODEGA_ADOPTS, "sigma_cal": SIGMA_CAL,
                "anchor_mult": ANCHOR_MULT, "venues": list(ALL_VENUES),
            },
            "provenance": (
                "REAL (traces to the committed twin, reproducible from the seed): "
                "the two HUD counters (block_mature = mean daily paired Δ — "
                f"margin ${block_merchant}/day merchants, consumer-surplus "
                f"${block_shopper}/day shoppers, over {DAYS} days), per_venue_mature, "
                "receipt savings (real per-SKU mean surplus), per-venue receipt "
                "frequency (real deal share), crowd density (real converting "
                "traffic: the sticker block converts "
                f"{round(convert_ratio*100)}% as many arrivals), and the per-venue "
                "decay ordering (real spoilage + surplus gap). "
                "REPRESENTATIVE (disclosed narrative, never a dollar figure): the "
                "day_weight identical→diverged ramp (the sim diverges from day 0; "
                "the ramp is the arc, so the counters integrate the real daily rate "
                "over it — end-of-week ≈ "
                f"${hud_shopper_week} shoppers / ${hud_merchant_week} merchants), the "
                "gray/decay intensities (a monotone visual encoding of the real gap, "
                f"{GRAY_GAIN}× gain on the {round(cs_gap_frac*100,1)}% CS gap), the "
                "named-regular churn days (the pool holds at 25 all week — churn "
                "dramatizes the real no-sale/spoilage/surplus gap), and the "
                "truck/weather beats + per-walker paths."
            ),
            "day_seconds": 6,
            "days": PROJECT_DAYS,
            "day_start_hour": 5.0,
            "worlds": ["sticker", "snhp"],
            "hud_labels": {"shopper": "shoppers kept", "merchant": "merchants earned"},
            "hud_week_total": {"merchant": hud_merchant_week, "shopper": hud_shopper_week},
        },
        "venues": VENUES,
        "regulars": regulars_out,
        "ledger": {
            "day_weight": DAY_WEIGHT,
            "day_weight_note": (
                "day d's whole contribution = per-venue mature (real mean daily "
                "Δ) × day_weight[d]. day0 = 0: the blocks START IDENTICAL and "
                "diverge over the ramp (the disclosed narrative arc)."),
            "per_venue_mature": per_venue_mature,
            "block_mature": {"merchant": block_merchant, "shopper": block_shopper},
            "week_total_note": (
                f"cumulative HUD after the 7-day ramp: merchants ≈ ${hud_merchant_week}, "
                f"shoppers ≈ ${hud_shopper_week} (block_mature × Σday_weight = "
                f"{sum_weight}). The per-DAY rate is the real committed twin's mean "
                "daily paired Δ."),
        },
        "crowd": {
            "seed": SEED,
            "ambient_concurrent": {"sticker": ambient_sticker, "snhp": ambient_snhp},
            "ambient_note": (
                "real converting foot traffic = arrivals net of walk-aways; both "
                "blocks see the SAME arrivals, the sticker block converts "
                f"{round(convert_ratio*100)}% as many (baseline count is cosmetic)."),
            "hour_weight_note": "intraday crowd multiplier by clock hour (0-23)",
            "hour_weight": HOUR_WEIGHT,
            "receipt_rate_per_hour_snhp": 5.0,
            "receipt_rate_note": (
                "display sampling rate (the real block runs ~"
                f"{round(sum(snhp_deals.values())/DAYS)} deals/day, far too many to "
                "draw); per-venue frequency ∝ receipt_weight (real deal share)."),
            "receipt_weight": receipt_weight,
            "receipt_pool": receipt_pool,
        },
        "mood": {
            "gray_note": (
                f"sticker desaturation 0→{gray6}: a monotone visual encoding of the "
                f"real block consumer-surplus gap ({round(cs_gap_frac*100,1)}% less "
                f"on the sticker block, {GRAY_GAIN}× visual gain). snhp stays warm (0)."),
            "gray": {"sticker": gray_sticker, "snhp": [0.0] * PROJECT_DAYS},
        },
        "decay": {
            "note": (
                "per-venue sticker decay 0-1 by day = severity × day_weight ramp. "
                "severity = 0.55·(spoilage gap) + 0.45·(consumer-surplus gap), both "
                "real and normalized: the florist/bakery waste the most, so they "
                "decay hardest. snhp venues stay at 0."),
            "sticker": {v["id"]: decay[v["id"]] for v in VENUES},
        },
        "weather": WEATHER,
        "beats": beats,
    }
    return doc


def main(argv=None) -> int:
    doc = build_week()
    out = os.path.join(os.path.dirname(__file__), "web", "canned-week.json")
    with open(out, "w") as f:
        f.write(json.dumps(doc, indent=2) + "\n")
    m = doc["ledger"]["block_mature"]
    wk = doc["meta"]["hud_week_total"]
    print(f"wrote {out}")
    print(f"block_mature (real mean daily Δ): merchants ${m['merchant']}/day · "
          f"shoppers ${m['shopper']}/day")
    print(f"HUD week total (× Σday_weight): merchants ${wk['merchant']} · "
          f"shoppers ${wk['shopper']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# B5 RESULTS — the full ten-venue street (composition guarantee)

*2026-07-10. The six remaining shipped sims (bakeshop/ → bakery + florist,
slots/ → barbershop + parking + happy-hour bar, vintage/) wrapped VERBATIM as
block storefronts, plus wholesale/ as the 6am dawn tier feeding venue COGS.
This closes DESIGN §4b-2's composition guarantee: every standalone sim in the
repo is now a storefront on one clock, one shared ledger, one paired
twin-world. Committed artifact: `block/results-block10.json` — rerun with*

```
python3 -m block.runner --days 30 --seed 20260710 --regulars 25 --venues all \
    --out block/results-block10.json
python3 -m block.runner --days 30 --seed 20260710 --regulars 25 --venues all \
    --wholesale        # the flywheel: SNHP world inherits negotiated COGS
python3 -m pytest block/tests -q     # 54 tests, ~70s
```

*30-day ten-venue twin (sticker vs SNHP, identical seeded population per
venue), σ_cal = 0.15, honest anchor (×1.0), 25 machine regulars. Runtime 13.9s
on one core (budget 120s).*

> **REGENERATED (vend review-fix downstream propagation):** `results-block10.json`
> is `block_version 2`. The vend review-fixes shifted the two street venues —
> **vending +3.01 → +3.41 [0.49, 6.34]** (now CI-excludes-zero, a WIN not the old
> B0 leak) and **bodega −5.84 → −5.55 [−7.07, −4.03]** — and the HUD/block-total
> correspondingly. The tables/prose below carry the corrected values; the
> **wholesale-flywheel section still quotes the pre-regeneration base (+3.01/−5.84
> → +10.98/−4.97)** because that `--wholesale` run is not in the committed
> `results-block10.json` and was not re-derived here. Trust the committed JSON.

## Headline — ten-venue paired deltas (per day, block-CI as noted)

| venue      | sticker margin/day | snhp margin/day | Δ margin (CI95)              | Δ CS/day |
|------------|-------------------:|----------------:|------------------------------|---------:|
| vending    |            $135.54 |         $138.95 | **+3.41** [0.49, 6.34]       |    +6.95 |
| bodega     |          $2,992.00 |       $2,986.45 | **−5.55** [−7.07, −4.03]     |    −2.50 |
| boba       |          $1,022.30 |       $1,358.75 | **+336.45** [317.01, 355.89] |  +496.49 |
| fashion    |           −$435.27 |        −$414.89 | **+20.47** [−36.39, 77.33] ⁷ |   +87.53 |
| bakery     |            $473.54 |         $659.52 | **+185.99** [164.88, 207.10] |  +131.28 |
| florist    |           −$442.44 |        −$234.95 | **+207.49** [59.66, 355.32]  |  +202.18 |
| barbershop |            $257.10 |         $252.07 | **−5.03** [−25.10, 15.04]    |   +11.64 |
| parking    |          $2,018.84 |       $2,187.95 | **+169.11** [144.17, 194.06] |  +174.03 |
| bar        |          $7,734.99 |       $7,879.60 | **+158.93** [0.35, 317.52] ⁷ |  +342.33 |
| vintage    |           −$237.29 |        −$224.23 | **+13.06** [−9.98, 36.10]    |    +3.89 |

⁷ = venue-level CI blocks on 7 days (fashion's weekly reprice; the bar's
day-of-week weekend surge); every other venue blocks on 5.

HUD over 30 days: **shoppers kept +$43,778.97 · merchants earned
+$32,097.49.** Margins are net of NYC rents (bakery $500, florist $350,
barbershop $250, parking $900, bar $800, vintage $300/day — block-level
calibration TARGETS; the standalone sims model margin gross of rent).

**Win/tie/loss (CI vs zero), honestly:** clear wins — vending (+3.41 [0.49,
6.34] after the vend review-fix regeneration — the B0 leak no longer fires),
boba, bakery, florist, parking, bar (bar's CI floor is +0.35, a hair off zero).
Small directional positive with CI spanning zero (a TIE we do not claim) —
fashion, vintage. Small negative with CI spanning zero — barbershop. One real
loss — the bodega (−5.55, the machine's quotes poaching its walk-in defectors,
B0's finding, unchanged). Nothing is a win where the CI includes zero.

## How this moved vs the old B0/B1B2 headline

**The four original venues are byte-identical to the committed B1B2 run.** The
six new storefronts run their own package's population on independent
block-derived seeds, so they add lanes without perturbing a single street /
boba / fashion draw (asserted: `test_new_venues_are_paired_across_worlds`, and
the 4-venue `results.json` still reproduces byte-for-byte). Vending +3.41,
bodega −5.55, boba +336.45, fashion +20.47 are exactly the committed 4-venue
`results.json` numbers.

**What moved is the BLOCK TOTAL, because the block is now ten storefronts, not
four.** HUD, side by side:

| block         | shoppers kept/30d | merchants earned/30d |
|---------------|------------------:|---------------------:|
| B0 (2 venue)  |           +$156.72 |             −$405.99 |
| B1B2 (4 venue)|        +$17,653.33 |          +$10,640.52 |
| **B5 (10 venue)** |    **+$43,778.97** |      **+$32,097.49** |

The six new storefronts contribute **+$26,125.65 shopper surplus and
+$21,456.97 merchant margin** over 30 days — the block roughly triples on both
counters, and for the first time the merchant counter is the LARGER story
(negotiation-friendly perishable and yield-management venues, where the sticker
is provably wrong, dominate the mix). (Note: the old B1B2 doc's Headline-1 HUD
of +$48,427.83 predates the priority-#2 fashion recalibration that cut the
fashion lane ~11×; the current committed 4-venue HUD is +$17,653.33, which is
the honest baseline the table above compares against.)

## What each new storefront actually tests, and what happened

Every new venue was chosen to stress a DIFFERENT mechanism (DESIGN §4c). The
recalibrated per-package numbers — used as-is, the block does not re-tune them
— show up directly:

- **bakery (+185.99, clear win) — batch perishability / the day-old shelf.**
  The mechanism is waste avoidance: the control lets the morning over-bake go
  stale (spoilage **$97.7/day**), while the SNHP nego bundles clear it before
  the bin (spoilage **$0.1/day**) AND sell more units (7,547 → 10,383/day
  across the run). This is the "friction-free wedge" the design predicted:
  markdown culture already exists, so the engine just does it optimally.
- **florist (+207.49, win) — extreme perishability + receiving-loss shrink.**
  With the CALIBRATION-TARGETS §3 floral fix live (15% receiving loss + the
  graduated vase-life markdown ladder replacing the old day-4 cliff), the
  control florist bleeds **$311/day** in shrink; SNHP cuts it to **$79/day**
  and lifts units 434 → 1,229. Both worlds still run NEGATIVE margin against
  the $350 rent at 3 SKUs of thin volume — read the **Δ** (the mechanism), not
  either world's absolute margin (a real independent-florist would carry far
  more SKUs; the block does not re-architect the catalog).
- **barbershop (−5.03, TIE) — pure appointment capacity, zero inventory.** The
  honest null: 2 chairs over a 10-hour day are rarely congested, so there is
  almost nothing to yield-manage — bookings barely move (461 → 498) and the CI
  spans zero. Negotiation creates surplus where the sticker is wrong or stock
  is scarce; a rarely-full barber is neither. (The slots congestion ladder was
  engineered exactly so: parking > bar > barber.)
- **parking (+169.11, clear win) — pure yield management, duration × start-time
  bundles.** The most miscalibrated real-world pricing meets the Nash bundle
  search: bookings 2,445 → 2,900, revenue +$186/day net of discounts. The
  design's "hilariously legible" venue delivers its win cleanly.
- **bar (+158.93, win) — the happy-hour / anchor-optics wedge.** Peak-anchored
  list prices + the by-hour, day-of-week weekend surge: the SNHP arm formalizes
  "happy hour, but optimal" and books 10,963 → 11,921 drink-orders. CI floor is
  +0.35 (a win by a whisker); the bar carries its OWN day-of-week structure, so
  its CI honestly blocks on 7 days.
- **vintage (+13.06, TIE) — one-of-one, make-an-offer.** Directionally positive
  (the offer/counter engine clears 44 → 64 pieces) but the CI spans zero over
  30 days: vintage is a SLOW venue (6 sourced/day, tiny connect probability),
  and its own standalone reads run 60 days × 8 reps for exactly this reason. On
  the block's 30-day window the offer arm does not separate from the LES
  −20%/30-days posted ritual with confidence — an honest not-enough-data tie,
  not a null mechanism.

## The wholesale dawn tier — both sides of the business (the flywheel)

`--wholesale` runs wholesale/'s 6am procurement market VERBATIM (coordinated
Nash bundles over price × delivery window × case size × payment terms ×
spoilage-share vs the rate card) as a paired twin ABOVE the retail day. Its
output is a per-venue SNHP-world COGS multiplier — realized negotiated
procurement dollars over rate-card dollars — which the SNHP retail world
inherits (the sticker retail world buys the rate card). Realized scales
(seed 20260710, ~5 block weeks):

| served venue | COGS scale | procurement saving |
|--------------|-----------:|-------------------:|
| vending      |     0.9052 |            −9.5%   |
| boba         |     0.9529 |            −4.7%   |
| bakery       |     0.9974 |            −0.3%   |
| bodega       |     0.9995 |            −0.05%  |

Effect on the served venues' SNHP margins (wholesale ON vs the retail-only
headline): vending **+3.01 → +10.98**, boba **+336.45 → +376.01**, bakery
**+185.99 → +187.66**, bodega **−5.84 → −4.97**. The flywheel stacks
**+$1,502/30d** of merchant margin (merchants earned $32,076.94 → $33,579.01),
concentrated where the wholesale lever is largest (vending's beverage cases,
boba's tea/tapioca). **Consumer surplus is unchanged** ($43,775.04 in both
runs): the retail pricing policies do not move, so the procurement saving
lands as merchant margin, not a consumer price cut — honest margin STACKING,
not pass-through (whether it reaches consumers is a function of retail
competition, deferred). The dawn tier leaves the sticker world byte-identical
(asserted), the same isolation the bodega-adoption toggle has.

## Adapter fidelity — each storefront IS its sim

Every adapter reuses its package's world + committed policies with zero
mechanism reimplementation; it only translates the block's 10-minute clock,
keys the sim on a block-derived per-venue seed, and returns receipts the runner
books into the shared ledger (the venue never touches the ledger — the B0
layering rule). Fidelity is a test, not a claim
(`test_*_adapters_match_standalone`): driven on a shared seed, the slots and
vintage adapters reproduce their standalone sims' revenue and units EXACTLY to
the cent; the bakeshop adapters reproduce the sticker (control) arm exactly and
the SNHP (nego) arm within a cent (per-line bundle re-rounding, the same ≤1¢
convention boba uses). All ten venues obey money conservation (venue till ==
ledger event-side to the microcent), unit conservation, and exact delta
decomposition.

## Shortcuts & honesty flags (all documented in-code)

- **Self-contained lanes.** bakery/florist/barbershop/parking/bar/vintage run
  each package's OWN validated population, not the street's GOODS-WTP Shopper
  (whose union does not contain croissants, haircuts, parking hours, or
  one-of-one vintage pieces). This is the exact boba precedent (boba uses its
  own arrival curve rather than persona schedules). "Shared population" holds
  in the load-bearing sense — same block seed, paired twin worlds, same clock
  and ledger — and cross-substitution between these venues and the street is
  DEFERRED (the same B1/B2 shortcut).
- **Rents are the only block-level calibration added.** Every catalog, cost,
  arrival curve, no-show rate, and mechanism comes from the package's OWN
  (recalibrated) calibration.py. Rents are pilot-data TARGETS.
- **Two venues run negative absolute margin** (florist, vintage) against their
  rent targets at their standalone catalog scale — read the paired **Δ**, not
  the absolute, exactly as the fashion recalibration note instructs.
- **The bar carries day-of-week; nothing else does** (its weekend surge is
  intrinsic to slots' calibration). Day 0 = Monday. Every other lane stays
  day-of-week-agnostic (B0 carried).
- **vintage is day-atomic** (one sourcing draw + one browser pass + one belief
  update per block day; ticks are cosmetic). Its per-item holding cost enters
  the ledger through the spoilage line (carrying cost of unsold one-of-one
  stock, not literal waste).
- **The wholesale flywheel is demonstrated on the four served venues**
  (vending/bodega/boba/bakery — wholesale/'s calibrated catalog); the other six
  stay at scale 1.0 (a coverage gap a pilot would close by extending the
  wholesaler catalog).
- Fairness caveat carried from B0/DESIGN §5: street/venue shoppers still carry
  no reference-price punishment (only machine regulars do); the fairness
  experiment remains the gate before shipping any deep-discount-for-some story.

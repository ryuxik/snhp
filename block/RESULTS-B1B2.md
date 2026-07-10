# B1/B2 RESULTS — the four-venue block (boba + fashion + bodega adoption)

*2026-07-10. Committed artifacts: `block/results.json` (default) and
`block/results-adopt.json` (bodega_adopts=True) — rerun with*

```
python3 -m block.runner --days 30 --seed 20260710 --regulars 25 --out block/results.json
python3 -m block.runner --days 30 --seed 20260710 --regulars 25 --bodega-adopts \
    --out block/results-adopt.json
python3 -m pytest block/tests -q     # 37 tests, ~17s (incl. two 30-day twins)
```

*30-day four-venue twin (sticker world vs SNHP world, identical seeded
population), σ_cal = 0.15, honest anchor (×1.0), 25 regulars. Runtime 5.2s
default / 9.0s with adoption, one core (budget: 120s).*

## Headline 1 — four-venue paired deltas, default (per day, 5-day-block CIs)

| venue   | sticker margin | snhp margin | Δ margin                    | Δ CS      |
|---------|---------------:|------------:|-----------------------------|----------:|
| vending |        $135.54 |     $138.55 | **+3.01** [0.25, 5.78]      |     +7.14 |
| bodega  |      $2,992.00 |   $2,986.16 | **−5.84** [−9.33, −2.35]    |     −2.83 |
| boba    |      $1,022.30 |   $1,358.75 | **+336.45** [317.01, 355.89]|   +496.49 |
| fashion |      $1,747.40 |   $2,143.45 | **+396.05** [234.73, 557.37]| +1,113.46 |

HUD over 30 days: **shoppers kept +$48,427.83 · merchants earned
+$21,890.10.** Margins net of calibration rents (bodega $400, boba $330,
fashion $620/day; the machine has no rent line — pilot-data target).
Read the fashion row with Surprise 3 below: most of it is timing.

## Headline 2 — the same twin with `bodega_adopts=True`

| venue   | sticker margin | snhp margin | Δ margin                    | Δ CS      |
|---------|---------------:|------------:|-----------------------------|----------:|
| vending |        $135.54 |     $131.70 | **−3.84** [−7.86, 0.18]     |     +8.00 |
| bodega  |      $2,992.00 |   $3,183.62 | **+191.61** [181.48, 201.75]|   +363.22 |
| boba    |      $1,022.30 |   $1,358.75 | **+336.45** [317.01, 355.89]|   +496.49 |
| fashion |      $1,747.40 |   $2,143.45 | **+396.05** [234.73, 557.37]| +1,113.46 |

HUD: **shoppers kept +$59,434.95 · merchants earned +$27,608.11.** The
sticker world is byte-identical between the two runs (asserted in tests);
boba and fashion rows are identical too — adoption only touches the street
lane, which is exactly the isolation the toggle promises.

## What actually happened

- **Boba replicates its own P0 result inside the block.** Δ +336.45/day
  sits inside boba/'s standalone grid (+308 to +349 across flex cells).
  Cups 226→484/day, ~98 deferred pickups/day, balks 62→52/day, pearl waste
  $8.20→$3.22/day. Sticker cups land at 226/day vs the 260 calibration
  target — the block's persona wtp multipliers average ×0.95, a documented
  composition effect, not a re-tune.
- **The bodega's B0 loss (−5.84/day, the machine's quotes poaching its
  defectors) reverses into +191.61/day when it adopts.** Anatomy: ~87
  brokered quotes/day at an average 45% off posted, average basket 2.3
  units, almost all on the sandwich board (deli-sandwich and chopped-cheese
  — the goods the machine doesn't carry). 41% of the negotiated buyers are
  vending-home walkers pulled across the street; the machine's Δ
  correspondingly flips +3.01 → −3.84 (CI now spans 0). Symmetric
  endogeneity works both ways: whoever adopts second still gains, but the
  first adopter's cross-poaching edge disappears.
- **Fashion sells 1,989 of 3,223 bought units in 30 days vs the cliff's
  1,155** — the markdown re-solve starts cutting week 0 (the σ_cal-noised
  buy overshoots some cells), while the cliff posts MSRP until week 7.

## Surprise 1: the committed B0 artifact was stale at HEAD

`block/results.json` (B0) was generated BEFORE the censoring-aware learner
fix that shipped *in the same commit* ("adverse selection named and
fixed"). Clean HEAD already reproduced different SNHP-world numbers from
day 2 onward (first divergence: the learner's day-2 demand level). With the
fix live, the vending delta the B0 report headlined (−4.74/day) is actually
**+3.01 [0.25, 5.78]**: the sellout-censored forecast no longer
hallucinates excess, so the winner's-curse quotes RESULTS-B0 documented
mostly stopped firing. The sticker world reproduces the old artifact
exactly; only the SNHP world moved. B1 adds the byte-reproducibility test
B0 lacked, so this class of drift now fails CI instead of living in a
report. (RESULTS-B0.md's Surprise 1 remains a correct description of the
pre-fix behavior it measured.)

## Surprise 2: what adoption actually buys the bodega

Not protection from the machine — new negotiated demand. Of the +191.61/day:
the machine only takes ~$4/day back off its own delta, while bodega units
jump 626→770/day (+23%) and revenue +$757/day *net of* the 45% average
discounts. The Nash engine's disagreement point does the work the design
promised: a buyer who would have bought the board anyway gets a discount
only out of newly created surplus (the 2nd/3rd sandwich down the quantity
ladder), so the deep discounts ride on marginal units, not on margin the
bodega already had. Consumers keep +$363/day of it. The caveat carried from
B0: street shoppers have no reference-price fairness yet, so nothing in
this world punishes a 45%-off-for-some-people regime; the fairness
experiment is still the gate before shipping that story.

## Surprise 3: fashion's weekly cadence creates exactly the feared ledger artifact

The +396.05/day fashion row is real cash in the window but it is mostly
**revenue timing, not season value**. A full-season check (98-day
fashion-only twin, same seed): both worlds sell **100.0%** of the buy, no
salvage writedown ever books, and the season-end paired delta is
**−18.85/day, CI [−264.48, +226.78] — a tie**. The markdown arm pulls sales
forward at shallower discounts (0 units at −70% vs the cliff's 179); the
cliff catches up in weeks 7–14 and clears everything anyway, because the
loyal-now buy plan undershoots realized demand (persona multipliers +
returning waiters). Consumers still keep +171/day over the season
(shallower average prices), so the mechanism isn't worthless — but the
30-day margin headline flatters it ~20×. Two ledger notes for anyone
reading the daily rows: (1) cogs book at sale and the writedown books on
day 97, so short windows show margin gross of clearance risk by
construction (documented in venues.py); (2) the 5-day CI blocks alias
against the 7-day repricing cadence (n=6 blocks vs 4+ week boundaries) —
treat the fashion CI as indicative, not sharp.

## Calibration honesty

Realized vs target, default run: street 620 by construction (vending 40.3
deals/day of ~70 arrivals; bodega 534.8 tx/day vs 550), boba 377
arrivals/day by construction (cups 226 vs 260 — persona composition, see
above), fashion 38.5 tx/day sticker-world vs the 34/day target (the arrival
scale is DERIVED from the tx target through the cliff-calendar conversion:
135.4 arrivals/day at week 0, tapering ×0.93/week — same derived-not-tuned
rule as the B0 funnel; realized runs slightly hot because the derivation
prices loyal-now conversion only). Season length 14 weeks from calibration;
the 16-week trade calendar compresses to 7/3/3/1.

## Shortcuts taken (all documented in-code)

- Lanes don't cross-substitute: boba/fashion walkers never shop the
  bodega/machine and vice versa (union WTPs exist on every shopper, so the
  extension is data-compatible when it comes). Boba's outside option is the
  coffee shop next door (×1.10, no walk term); fashion's is not buying.
- The adopted bodega quotes street shoppers only; the machine's REGULARS
  keep the posted-board path when they defect (vend's fairness psychology
  stays machine-scoped, as in B0).
- Believed outsides stay posted-board: the machine never sees the bodega's
  quotes and vice versa; each engine's misbelief can only cost its own
  venue a declined quote (consumer acceptance always uses real
  alternatives).
- Boba: revenue books at order (boba/run's convention); cups the bar
  doesn't reach by 22:00 stay a counted leftover (29 vs 65 cups over 30
  days) — no refund model. Deferred slots clamp to the last open tick.
- Fashion: uniform attention across the four lines (no line-level traffic
  data in calibration), FASHION_MIX (tourist/local-heavy) is a documented
  choice, appeal = 0.90 × MSRP per fashion/world's convention, buy error
  σ=0.15 per fashion's default.
- The bodega's day-0 structural demand forecast reuses vend's office-tower
  intraday curve until its learner has a day of history (same documented
  approximation the machine carries).
- No day-of-week, day shocks, or same-day return queue (B0, carried).

## Priority #2 recalibration (2026-07-10) — fashion arrival scale fix, 7-day CI blocks

paper/CALIBRATION-TARGETS.md #2 / pre-registered CRITICAL-ANALYSIS.md §5:
**the fashion row above is superseded.** The block's fashion buy plan
(`block.venues.build_fashion_plan`) and its realized arrivals
(`block.population.FASHION_W0_DAILY`) are driven by the SAME analytic
"loyal-now demand at the cliff calendar" formula, so buy ≈ E[demand] almost
exactly by construction; at the old `FASHION_DAILY_TX=34` the per-cell
volume (~200 units/(style,size) cell/season) was large enough that the law
of large numbers squashed the buy-vs-demand gap to ~0 — **both worlds sold
100.0% of the buy every full season** (Surprise 3, below, as originally
written), a scarcity-mechanism-killing artifact: when nothing goes unsold,
no inventory-management mechanism can show an edge from managing inventory.

**Fix: `calibration.FASHION_DAILY_TX` 34 → 3** (`block/calibration.py`),
matching the SAME buy-vs-arrival formula down to the standalone `fashion/`
sim's own scale (~226 units/season, ~14/cell) — already validated against
real full-price/season-end sell-through in CALIBRATION-TARGETS.md row 2.
Confirmed directly: the standalone sim's CLIFF arm sell-through is ~90%
even at `sigma_buy=sigma_cal=waiter_share=0` (pure finite-sample demand
variance, not any of those knobs) — it is a SCALE effect, and cutting the
block's fashion volume to the same scale reproduces it. Same root cause,
same honest direction as priority #1: the sim's per-lane VOLUME, not its
mechanism, was calibrated far hotter than one real small-format storefront.

**Sell-through, recalibrated** (BlockConfig default incl. σ_cal=0.15,
8 independent seeds, full 98-day/14-week seasons):

| arm | mean sell-through | min | max |
|---|---:|---:|---:|
| STICKER (cliff) | **91.1%** | 84.7% | 98.1% |
| SNHP (markdown/1) | 96.8% | 90.5% | 100.0% |

Sticker lands inside the 85-92% target band; the standalone sim's own
directly comparable cell (σ_buy=0.15, σ_cal=0.15, waiters=15%) gives cliff
90.2% / markdown 96.8% — both block arms track their standalone counterpart
closely. It is *expected*, not a new artifact, that SNHP outsells STICKER:
the standalone sim shows the identical gap (markdown actively re-solves to
clear stock; a fixed calendar can't) at every comparable cell tested.

**Full-season (98-day) fashion-only twin, committed seed 20260710** (the
same check Surprise 3 ran, re-run at the fix): sticker sold 272/283 = 96.1%
(this particular seed runs hot within the 84.7-98.1% band above), snhp sold
282/283 = 99.7%. Season-end paired margin delta: **mean −$1.32/day, CI95
[−32.56, 29.91]** (n=14 blocks of 7 days). **The fashion row does NOT
become informative in the win/lose sense — the CI still includes zero —
but for an honest reason now: real economic noise at a realistic sample
size, not the 100%-sellout saturation artifact.** That is the actual
deliverable of this fix: a CI that can move, even though this particular
run doesn't move it away from zero.

**7-day CI blocks** (`block/ledger.py`, `VENUE_CI_BLOCK = {"fashion": 7}`):
fashion reprices weekly, so a 5-day block aliased that cadence (n=6 blocks
over 30 days vs 4+ real week boundaries — this file's original Surprise 3
flagged exactly this). Fashion's venue-level paired CI now blocks on 7
days; every other venue (daily repricing) and the block-level aggregate
(mixed cadences) keep the 5-day default.

**Honest regression, not fixed here:** at `FASHION_DAILY_TX=3` the fashion
venue's absolute economics collapse — both worlds run **negative margin**
(sticker −$435/day, snhp −$415/day, 30-day headline) against the unchanged
`FASHION_RENT_PER_DAY=$620` calibration target, because revenue fell ~11×
with the volume cut while rent did not. Real NYC boutiques presumably carry
far more than 4 style lines, so their AGGREGATE transaction volume can stay
high (~34/day) while PER-SKU volume stays thin enough for realistic
sell-through — a structural fix (more SKUs) this task did not make (scope
was "recalibrate fashion arrivals", not re-architect the catalog). Read the
fashion row's **Δ** (sticker vs snhp) as the informative mechanism
comparison this task was scoped to fix; do not read either world's
**absolute** margin as a standalone-boutique profitability claim at this
catalog size.

**Updated 30-day headline (both `block/results.json` and
`block/results-adopt.json` regenerated; vending/bodega/boba rows are
numerically UNCHANGED — fashion is the only venue this recalibration
touches):**

| venue | sticker margin/day | snhp margin/day | Δ margin (block=5 or 7) |
|---|---:|---:|---|
| vending | $135.54 | $138.55 | +3.01 [0.25, 5.78] |
| bodega | $2,992.00 | $2,986.16 | −5.84 [−9.33, −2.35] |
| boba | $1,022.30 | $1,358.75 | +336.45 [317.01, 355.89] |
| **fashion** | **−$435.27** | **−$414.89** | **+20.47 [−36.39, 77.33]** (block=7, n=4) |

Reproduce: `python3 -m block.runner --days 30 --seed 20260710 --regulars 25
--out block/results.json` (and `--bodega-adopts` for the adoption artifact);
`python3 -m pytest block/tests -q` (39 tests, incl. two new: 7-day CI block
assertion, full-season sell-through-not-saturated).

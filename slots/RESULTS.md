# SLOT-ECONOMICS results — one world core, three venue calibrations

*30 paired days per cell, seed 20260710. Reproduce with
`python3 -m slots.run --grid --days 30 --seed 20260710` (writes
`slots/results.json`).*

## Pre-registered hypotheses (written before the grid ran)

The grid: flexibility share {0.15, 0.35} x demand-shock sigma {0, 0.4},
30 paired days per cell, arms static/1, computed/1, nego/1, and the
nego-noshift/1 ablation, per venue. Committed BEFORE `slots/results.json`
existed; the verdicts below were filled in after, against these rules.

- **H-S1 — the nego edge scales with peak/off-peak demand asymmetry:
  parking > bar > barber.** The venues are engineered onto an asymmetry
  ladder (import-time congestion ratios: parking 2.11 > bar 1.62 >
  barber 1.32, reported in results.json). Verdict rule: rank venues by
  nego-vs-static margin Δ/day as a % of static margin, averaged across
  the four cells; H-S1 holds iff the ranking is parking > bar > barber.
- **H-S2 — the edge concentrates in slot-shifting at peak, not price
  cuts.** Verdict rule: in the flex=0.35 cells, the shift component
  (full nego edge minus nego-noshift edge) exceeds the price-cut
  component (the nego-noshift edge) in at least 2 of 3 venues.
- **H-S3 — computed ties static when the list is well-calibrated (the
  vend/boba weak-dominance result replicates in a third vertical).**
  Verdict rule: computed-vs-static margin Δ/day CI (95%, 5-day blocks)
  straddles 0 in all four cells of every venue.

Known-before-running honesty items: the ratio-appeal inversion treats
buyers as all-or-nothing at their requested duration, so true demand is a
shade more elastic below list than the sticker assumes (favors the
discounting arms; the H-S3 deltas bound the error). Ten-day smoke runs
during calibration (before this file was committed) showed all three
mechanisms firing — sub-list conversion, peak-edge shifts, run-out holds
— but were not used to tune rates toward any hypothesis.

*(Results below this line were filled in after the grid run.)*

## Setup, in one paragraph

One world core (`slots/world.py`), three venue calibrations
(`slots/calibration.py`, 2026 NYC): a two-chair barbershop ($38 cut,
50-min chair time, 12% no-shows), a 40-space Midtown-adjacent garage
($18 first hour / $8 additional / $45 day max, 8% reservation no-shows,
a commuter slug that wants the same nine-to-ten hours), and a 60-seat
happy-hour bar ($9 beer / $16 cocktail, walk-in). A venue is capacity
units x 10-minute ticks; unsold slot-time perishes. Each venue's WTP
ratio scale is inverted so the list price IS the profit-optimal all-day
posted price — static is a competent operator. All arms face identical
arrival/WTP/flexibility/no-show streams (paired seeds); divergence is
the treatment. `test_committed_results_stay_reproducible` pins the
artifact.

## Headline: margin Δ/day vs static (paired, 95% CI on 5-day blocks)

**Barber** (static ≈ $360–390/day, occupancy 0.45–0.49):

| cell (shock σ × flex share) | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | −$6.44 [−15.44, 2.57] | +$10.37 [−3.33, 24.07] | +$9.43 [0.89, 17.96] |
| σ=0.0, flex=0.35 | −$8.66 [−19.67, 2.34] | +$4.08 [−11.21, 19.38] | **+$12.73** [2.54, 22.91] |
| σ=0.4, flex=0.15 | −$9.37 [−20.40, 1.66] | +$0.31 [−9.54, 10.16] | **+$17.28** [4.87, 29.70] |
| σ=0.4, flex=0.35 | −$9.05 [−27.06, 8.96] | −$3.46 [−17.57, 10.66] | **+$15.55** [5.28, 25.83] |

**Parking** (static ≈ $2,935–2,970/day, occupancy 0.68–0.69):

| cell | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | **−$22.49** [−33.50, −11.48] | **+$168.49** [145.34, 191.64] | +$160.54 [141.56, 179.52] |
| σ=0.0, flex=0.35 | **−$24.44** [−35.85, −13.03] | **+$168.99** [136.71, 201.27] | +$158.91 [128.50, 189.31] |
| σ=0.4, flex=0.15 | **−$16.23** [−29.07, −3.39] | **+$100.05** [34.74, 165.35] | +$109.77 [48.03, 171.51] |
| σ=0.4, flex=0.35 | **−$18.90** [−29.40, −8.39] | **+$110.46** [45.90, 175.01] | +$117.46 [62.63, 172.29] |

**Bar** (static ≈ $4,920–5,445/day, occupancy 0.50–0.55):

| cell | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | +$6.59 [−12.39, 25.57] | +$50.49 [11.61, 89.38] | **+$181.20** [158.20, 204.20] |
| σ=0.0, flex=0.35 | +$3.71 [−13.24, 20.67] | +$37.21 [−14.57, 88.99] | **+$182.14** [160.21, 204.06] |
| σ=0.4, flex=0.15 | +$0.66 [−2.88, 4.19] | +$96.68 [41.57, 151.79] | **+$177.71** [158.92, 196.50] |
| σ=0.4, flex=0.35 | +$0.06 [−7.23, 7.35] | +$75.37 [19.03, 131.71] | **+$181.85** [165.47, 198.22] |

Nego dominates static on consumer surplus everywhere (+$29–41/day
barber, +$128–171 parking, +$298–317 bar) — the created surplus is
split, as the Nash engine promises. Occupancy rises ~5–7 points at
every venue.

## Verdicts on the pre-registered hypotheses

- **H-S1 — HOLDS.** Nego-vs-static margin edge as % of static margin,
  averaged across the four cells: **parking 4.6% > bar 1.25% > barber
  0.75%** — the pre-registered ordering, matching the congestion-ratio
  ladder (2.11 > 1.62 > 1.32). At a two-chair shop with mild peaks the
  whole negotiation apparatus is worth ≈ $0–10/day.
- **H-S2 — FAILS, decisively.** The shift component (full nego minus
  nego-noshift) is negative or negligible in ALL SIX flex cells:
  barber −$8.7/−$19.0, parking +$10.1/−$7.0, bar **−$144.9/−$106.5**
  per day. The edge concentrates in per-arrival sub-list PRICE
  conversion of would-be walkaways, not in slot-shifting. Worse than
  "not the main lever": at the bar, offering relief-priced shifts
  actively destroys ~$110–145/day relative to the same engine without
  them (see surprises).
- **H-S3 — PARTIAL: holds at barber and bar, fails at parking.**
  Computed-vs-static CIs straddle 0 in all 8 barber/bar cells (weak
  dominance replicates there), but computed is significantly NEGATIVE
  in all four parking cells (−$16 to −$24/day). A posted discount
  surface can lose to its own well-calibrated list (see surprises).

## Honest surprises

- **The capacity-relief logroll — the boba result this package was built
  to replicate — went to zero or negative in realized play.** The
  mechanism is regime inconsistency, the vend P1 lesson with teeth: the
  shadow prices a freed peak unit-tick at the STATIC regime's mean list
  margin ("a turned-away buyer would have paid list"), but in the nego
  regime the freed seat is resold through the same engine — often to a
  sub-list looker — and the shoulder slot the shifted buyer now occupies
  was NOT free (nego-noshift monetizes it by converting shoulder
  arrivals). The engine pays a real discount for forecast relief and
  collects discounted resale. At the bar (45–50 shifts/day) that burns
  $110–145/day; at the barbershop it turns the arm's edge negative in
  the shock cells. Slot-shifting only breaks even at parking, where
  shifts are rare (3–5/day) because commuter value curves are convex
  (γ=3: trims and shifts are worth nearly nothing to them — as
  designed).
- **A ±30-minute shift cannot escape a 4-hour peak.** The bar's packed
  block is 19:00–23:00 but the credible shift menu is ±30 min, so only
  the peak's EDGES (19:00→18:30, 22:00→23:00) ever produce relief. The
  interior of the wall — where the shadow says relief is most valuable —
  is unreachable by any shift a customer would accept. Demand asymmetry
  creates relief VALUE (H-S1's premise) but destroys relief
  REACHABILITY.
- **Computed/1 strictly loses at parking: a posted discount surface
  leaks to infra-marginal buyers.** Instrumented decomposition (day 0,
  σ=0): $91/day of discounts went to buyers who would have paid list
  (24/day in place, 4/day self-shifting their entry into the discounted
  posted hour), against ≈ $70/day of genuinely new conversions. The
  hourly re-solve models the crowd as all-or-nothing at the requested
  duration, but real buyers self-trim at list (γ<1 segments buy fewer
  hours instead of walking), so true demand is less discount-elastic
  than the model believes. vend/boba handed their computed arms the TRUE
  demand model and got ties; give the re-pricer a subtly wrong one and
  weak dominance becomes strict loss. The nego arm carries the SAME
  wrong forecast but wins anyway, because every quote is gated by the
  individual buyer's actual alternatives, not the crowd model.
- **Day shocks cut parking's nego edge (≈ $169 → $105) but RAISE the
  bar's (≈ $44 → $86).** Both static baselines respond oppositely too
  (parking flat, bar −$520/day): at a hard capacity wall, mean-one rate
  shocks are pure downside for a posted board (heavy days can't convert
  the extra demand, light days lose it), and the nego arm claws back
  light-day slack by converting lookers the board turned away.
- **No-shows are just dead time, symmetrically.** Barber no-shows run
  ~1.2–1.4/day (9–10% of bookings — lead-zero walk-ups can't flake) and
  the released spans get resold by all arms alike; no arm found a way to
  monetize flake risk, and none was given one (no deposits modeled).

## Caveats (attack these first)

- **Truthful WTP disclosure.** The sub-list conversion component — which
  is now THE edge — is exactly what strategic understatement would
  attack; vend H3 measured that leak. These numbers are an upper bound
  on nego/1.
- **The relief forecast is static-regime and never marked to realized
  rescues** — this run showed that honestly costs money. The same shadow
  is what guards peak slots against discount lookers, and it does bind
  (every quote carries cost + displacement shadow + buffer as its floor)
  — but it prices displacement at min(1, D-hat/free), so peak-interior
  quotes still land at a median 0.79 of list (min 0.57) wherever the
  live ratio says the window has slack. The guard is a forecast, not a
  floor at list.
- **The board chooser prices a booking by its START hour's multiplier**
  (the "enter between X and Y" convention); a per-tick-blended price
  would shrink computed's self-shift leak, though not the in-place leak.
- **The ratio-appeal inversion is all-or-nothing at requested duration**
  (flagged pre-run): the true posted optimum sits slightly below our
  list, which flatters the discounting arms — and they still mostly
  failed to beat the sticker outside parking's nego arm.
- **Outside option has infinite capacity and no wait**; no regulars, no
  reference prices, no resentment at the neighbor's cheaper quote
  (vend's `regulars.py` is the template). A real shop cannot quote half
  its walk-ins −30% with impunity.
- Buyer utilities are conditional-on-show (their own flake risk cancels
  across alternatives); venue margins carry (1 − p_noshow); no deposits,
  no cancellation fees, no overbooking.


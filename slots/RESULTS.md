# SLOT-ECONOMICS results — one world core, three venue calibrations

> **REGENERATED 2026-07-10 (post code-review):** `slots/results.json` is now
> the authoritative source, run at **35 balanced days** (5 full weeks, so the
> bar's Saturday isn't under-counted) with **7-day CI blocks for the bar**
> (week-aligned) and 5-day for barber/parking. The `relief_credited` diagnostic
> is now credited only on genuine span-swaps (the old negative-`capacity_shadow`
> pollution is fixed; margin/CS unchanged). **Bar verdict is unchanged** —
> no-shift still beats full-nego (shift component ≈ −$108/day, CI excludes
> zero). Some 30-day / 5-day-block / old-`relief_credited` figures in the prose
> below predate this regeneration and are pending a doc reconciliation pass
> (folded into the whitepaper refresh); trust `results.json` on any conflict.*

*30 paired days per cell, seed 20260710. Reproduce with
`python3 -m slots.run --grid --days 30 --seed 20260710` (writes
`slots/results.json`).*

> **Post-registration update (2026-07-10).** The relief defect diagnosed
> in `paper/CRITICAL-ANALYSIS.md` §3 has been fixed as pre-registered
> there, and `slots/results.json` regenerated (slots_version 2, same
> seed/days/grid). Everything from here down to the **Relief fix
> (post-registration)** section is the PRE-FIX record — kept verbatim
> because the pre-registered verdicts were judged against it. The fixed
> numbers, the before/after shift decomposition, and the revisited H-S2
> verdict live in that section at the bottom.

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

## Headline: margin Δ/day vs static (paired, 95% CI on 5-day blocks) — PRE-FIX run, superseded

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

- **Assumption: parking reservation no-show = 8%, and barber booking lead
  time.** Neither is a measured anchor — CALIBRATION-TARGETS §4/§10 note the
  parking reservation no-show rate is *unpublished anywhere* and the barber
  booking lead time has *no published number* — so both are assumed inputs, not
  calibrated ones. (The barber no-show REGIME, by contrast, IS anchored:
  deposit 3–5% / no-deposit 15–25%, Squire/Zenoti.)
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

---

## Relief fix (post-registration) — 2026-07-10

Implements the fix pre-registered in `paper/CRITICAL-ANALYSIS.md` §3
verbatim: the capacity-relief credit no longer prices a freed peak slot
at the STATIC regime's list margin. Instead,

    relief = (learned, realized nego-regime margin per freed slot)
           − (shoulder displacement cost of the shifted booking,
              same learned basis)

both from the arm's OWN running history. Mechanics
(`slots/policies.py::HourMarginLearner`): a per-hour EWMA (alpha 0.3,
vend's DemandLearner pattern) of the arm's realized margin per unit-tick,
GATED by the fraction of the hour's ticks that ended the day at full
capacity — the gate is what makes the estimate marginal rather than
average (a freed tick only enables an extra sale where the hour actually
binds; occupying a slack tick displaces nobody). Warmup before any
history: a conservative 0.6 x the static mean list margin for peak
hours, 0 off-peak. The learned basis prices BOTH spans whenever the
buyer's fallback books (the deal is a span swap); a would-be walkaway's
quote keeps the unchanged conservative static shadow as its guard.
Everything else identical: paired seeds, min-gain buffer, discount-only.
Scope of the change, verified in the artifact diff: all four parking
cells and every barber nego-noshift cell are byte-identical to the
committed pre-fix run (their deals never hit the swap path); barber
nego, bar nego, and bar nego-noshift moved.

### Shift component of the edge (full nego − nego-noshift), $/day

BEFORE from the committed pre-fix artifact; AFTER from the regenerated
one; CI95 is the paired nego-vs-noshift interval (5-day blocks) on the
post-fix run.

| venue | cell | before | after | CI95 (after) |
|---|---|---:|---:|---|
| barber | σ=0.0, flex=0.15 | +0.94 | **+5.19** | [−2.72, 13.09] |
| barber | σ=0.0, flex=0.35 | −8.65 | **+1.89** | [−6.01, 9.78] |
| barber | σ=0.4, flex=0.15 | −16.97 | −9.90 | [−20.42, 0.62] |
| barber | σ=0.4, flex=0.35 | −19.01 | −10.53 | [−19.63, −1.43] |
| parking | σ=0.0, flex=0.15 | +7.95 | +7.95 | [−2.61, 18.52] |
| parking | σ=0.0, flex=0.35 | +10.08 | +10.09 | [−0.27, 20.44] |
| parking | σ=0.4, flex=0.15 | −9.72 | −9.72 | [−25.54, 6.09] |
| parking | σ=0.4, flex=0.35 | −7.00 | −7.00 | [−26.61, 12.60] |
| bar | σ=0.0, flex=0.15 | −130.71 | **−100.88** | [−135.50, −66.26] |
| bar | σ=0.0, flex=0.35 | −144.93 | **−90.27** | [−124.01, −56.54] |
| bar | σ=0.4, flex=0.15 | −81.03 | −79.35 | [−127.29, −31.41] |
| bar | σ=0.4, flex=0.35 | −106.48 | −78.59 | [−131.19, −25.99] |

Full-nego margin Δ/day vs static improved in every cell the fix touched:
barber 10.37→14.61, 4.08→14.61, 0.31→7.38, −3.46→5.03 (both σ=0 barber
cells are now significantly positive: CIs [1.97, 27.25] and
[1.28, 27.94]); bar 50.49→94.80, 37.21→96.03, 96.68→120.79,
75.37→120.89. The bar's nego-noshift also gained ($181–182→$186–200/day)
because its TRIM credit — the same freed-peak economics — now uses the
honest basis too.

### Does full nego now match/beat the no-shift ablation?

- **Barber, σ=0: yes** — full nego now beats noshift (+5.2, +1.9/day),
  though the CIs straddle 0.
- **Barber σ=0.4 and parking: statistically indistinguishable** —
  point estimates −10 to +10/day, every CI straddles or barely misses 0.
- **Bar: no, decisively** — noshift still beats full nego by
  $79–101/day, significant in ALL FOUR cells.

### H-S2, revisited

**Still FAILS.** In no flex=0.35 cell does the shift component exceed
the price-cut component (barber +1.9 vs +12.7; parking +10.1 vs +158.9;
bar −90.3 vs +186.3). The pre-registered prediction attached to this fix
— "the shift lever becomes ≥ 0 everywhere and full nego matches or beats
the no-shift ablation" — is REFUTED at the bar. What the fix DID do is
stop the lever from being mispriced: it recovered $7–11/day at the
barbershop (σ=0 shift lever now positive), $24–59/day at the bar, and
turned both σ=0 barber cells significantly positive vs static.

**Said plainly: the shift lever is still ≈ 0 at parking and the barber,
and still significantly NEGATIVE at the bar, after the pre-registered
fix.** The pre-registration's fallback conclusion is the finding:
slot-shifting logrolls are a boba-shaped result (long service times,
order-ahead, a shiftable queue) that does not generalize to short-peak
walk-in venues, and the whitepaper must say so.

### Why the bar lever stays negative (post-fix decomposition)

Per-buyer paired attribution on a converged day (day 30, σ=0,
flex=0.35, learner warm): shifted deals rescued 20 would-be walkaways
(+$184/day) but paid discounts to 18 buyers who would have paid list
(−$110/day), and the shifted/upsold occupancy displaced 17 later
list-paying walk-ins (−$154/day). The residual defect is NOT the relief
price — two independent learned bases (per-hour average margin per
capacity tick, and the shipped sold-out-gated marginal basis) land
within $10/day of each other (−96 vs −90) — it is information no
day-level per-hour slot value can carry: whether THIS tick, TODAY, would
have been locally rebooked inside the ±30-min window buyers actually
accept. At 60 seats with a 4-hour peak, hour-level bindingness is too
coarse, and the Nash split hands part of any phantom paper-gain to the
buyer as a real discount. The Lucas-critique design rule ("measure every
dollar in the regime the broker creates") is necessary but not
sufficient here: the regime-consistent value of a slot depends on the
same-day state trajectory, not on any learnable day-level average.

### Tests added (all in `slots/tests/test_slots.py`)

- `test_relief_prices_freed_peak_at_learned_regime_margin_not_list` —
  relief tracks the learner's values exactly and does not equal the
  static list-margin basis.
- `test_shoulder_displacement_is_charged` — the shoulder ticks a shifted
  booking occupies subtract at the learned basis; with flat learned
  values a shift mints nothing and the engine stops paying for it.
- `test_warmup_falls_back_to_conservative_fraction_of_list_margin` —
  0.6 x list-margin basis at peak, 0 off-peak, before any history.
- `test_learner_observes_soldout_gated_realized_margin` — the marginal
  (sold-out-gated) observation and the alpha=0.3 EWMA fold.
- `test_run_day_feeds_the_learner_realized_margins` — the runner's
  end-of-day feed is settled-bookings-only and bounded by realized
  margin.

---

## Calibrated-world (2026-07-10) — CALIBRATION-TARGETS §4, priorities #7+#8

*30 paired days per grid cell (35 for the two whole-week bar checks),
seed 20260710, `slots_version 3`. Reproduce with
`python3 -m slots.run --grid --days 30 --seed 20260710`.*

Three coupled recalibrations, all sourced in `paper/CALIBRATION-TARGETS.md`
§4:

- **Barber (#8).** Platform-measured (Squire 13.9M appointments, Zenoti
  30k businesses) schedule utilization averages 62%; the old rate profile
  realized 45–49% — a below-average shop. `BARBER_RATE`'s shoulders (not
  peaks, to keep the H-S1 ladder intact) are raised so static realizes
  ~62%. No-show is now an explicit REGIME
  (`BARBER_NOSHOW_REGIMES = {"deposit": 0.04, "nodeposit": 0.12}`); the
  venue default (`BARBER_NOSHOW`) is the deposit cell — platform shops
  with reminders/deposits run 3–5%, no-deposit shops 15–25% (12% kept as
  a conservative-low no-deposit case). The deposit IS the venue's
  incumbent negotiation mechanism (CRITICAL-ANALYSIS §6).
- **Parking (#8).** Lehner–Peer 2019: commuters are the LEAST
  price-elastic segment; the old model gave every segment the same WTP
  spread (`PARKING_SIGMA`), so the commuter's low elasticity was only an
  artifact of its high `wtp_mult` and tied with the event crowd.
  Elasticity is now STRUCTURAL: `Segment.sigma` (commuter 0.30 < event
  0.42 < errand 0.48), wired through `world.py`'s mixture inversion,
  D-hat forecast, and `computed/1`'s per-hour multiplier (previously all
  three used one venue-wide sigma). Occupancy (68%) is unchanged and
  explicitly LABELED a hottest-subarea facility (Seattle benchmark: 58%
  core / 48% outside).
- **Bar (#7, coupled to the peak-anchor fix).** Nielsen CGA: Saturday
  alone is >25% of weekly sales, Fri+Sat run 40–50%, Sat 5–6pm checks run
  ~40% above Sat 10pm, and happy-hour checks average ~$8 higher than other
  dayparts — the old flat "dead 5–7pm" profile was wrong on weekends.
  `world.py` gained a real day-of-week dimension (`Venue.dow_rate_mult`,
  `Venue.dow_wtp_mult`, both per-(day, hour); trivial/empty for
  barber and parking, so they are byte-unaffected): the mixture inversion,
  D-hat forecast, and `computed/1`'s per-hour multiplier now blend across
  all 7 days (barber/parking see the same day 7 times over, a no-op by
  construction); `mstar` is additionally keyed by `(day % 7, hour)` so
  `computed/1` reprices Saturday's true peak correctly. Coupled to this:
  the PEAK-ANCHOR fix — before, `BAR_BEER`/`BAR_COCKTAIL` were a flat
  list while `BAR_WTP_MULT` rose above 1 at peak, so every arm being
  discount-only meant the venue could never charge the peak crowd what it
  would bear (capped at list exactly when leverage was highest). Ported
  the concept behind `vend/world.py`'s `anchor_peak` +
  `_profit_optimal_list_price(peak_only=True)`: the dollar list was
  raised to the peak crowd's own profit-optimal price ($16 → $21.67
  cocktail, $9 → $12.19 beer — $16 is now a standing happy-hour discount
  off the new anchor), and `BAR_WTP_MULT`/`BAR_DOW_WTP_MULT` were
  re-based so the combined (day, hour) multiplier tops out at exactly 1.0
  at the true peak (Saturday 17:00) and never exceeds it anywhere.
  **Honest residual** (see the calibration note in `slots/calibration.py`):
  this venue's `ratio_appeal` is re-inverted against the full WEEK's
  blended mixture every build — the same mechanism barber/parking use,
  kept unchanged rather than special-cased for the bar — so no FINITE
  anchor makes the peak's own unclamped profit-optimal multiplier exactly
  1.0 (verified: iterating the anchor upward does not converge; the
  unclamped multiplier approaches ≈1.42 asymptotically as cost becomes
  negligible relative to list). The anchor is a single-shot
  profit-optimization at the pre-fix ratio appeal, same spirit as vend's
  function, not a re-inverted fixed point: it closes the bulk of the gap
  ($16 → $21.67) but ≈37% relative unclamped headroom remains — reported,
  not hidden.

### Calibration sim-vs-target table

| venue | metric | target (source) | sim (calibrated-world) |
|---|---|---|---|
| barber | utilization, static | ~62% avg (Squire/Zenoti) | 0.62–0.65 across the grid (0.6361 at seed cell) |
| barber | no-show, deposit regime | 3–5% (platform-measured) | input 4.0% exactly; realized 2.97% (0-lead walk-ins can't flake, diluting the realized rate — an honest artifact of the lead-time mix, not a miscalibration) |
| barber | no-show, no-deposit regime | 15–25% | 12% kept, LABELED conservative-low (unchanged, not re-run as the venue default) |
| barber | Bed-Stuy cut price | $38 confirmed | $38 (unchanged) |
| parking | commuter elasticity rank | LEAST elastic segment (Lehner–Peer) | confirmed at 7–9am: \|e_commuter\|=0.81 < \|e_errand\|=0.90 (structural, sigma-driven) |
| parking | occupancy | 58% core / 48% outside (Seattle) vs sim's hottest-subarea | 68.2–68.4%, LABELED high-demand facility (unchanged) |
| parking | NYC price points | $18/hr, $45 day max confirmed | unchanged |
| bar | Saturday revenue share | >25% of week (Nielsen CGA) | 22.8% over a whole-week (35-day) window — short of target, capacity-saturation-bounded (see honest surprises) |
| bar | Fri+Sat revenue share | 40–50% | 45.2% |
| bar | Sat 5–6pm vs Sat 10pm check | ~40% higher | +42.2% (combined WTP multiplier 1.000 vs 0.703) |
| bar | happy-hour vs other dayparts | ~$8 higher checks | qualitatively directional (general weekday happy-hour bump built into the rescaled base profile); not separately validated as a dollar figure |
| bar | cocktail / beer list | $16 / $8–9 confirmed as the OLD flat list | new peak anchor $21.67 / $12.19; $16/$9 now sub-anchor happy-hour prices |

### Headline: margin Δ/day vs static (paired, 95% CI on 5-day blocks) — calibrated-world

**Barber** (static occupancy 0.62–0.65, deposit no-show regime):

| cell | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | −$6.26 [−13.68, 1.16] | **+$11.16** [1.56, 20.76] | **+$13.20** [8.00, 18.40] |
| σ=0.0, flex=0.35 | −$7.61 [−17.23, 2.00] | **+$15.56** [5.03, 26.08] | **+$14.46** [10.83, 18.09] |
| σ=0.4, flex=0.15 | **−$8.25** [−13.80, −2.71] | −$10.22 [−23.80, 3.37] | +$0.63 [−7.92, 9.18] |
| σ=0.4, flex=0.35 | −$9.00 [−21.72, 3.72] | −$10.22 [−28.56, 8.13] | +$3.46 [−3.07, 9.98] |

**Parking** (static occupancy 68.2–68.4%, structural per-segment elasticity):

| cell | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | **−$24.59** [−40.36, −8.82] | **+$179.70** [150.90, 208.50] | **+$169.47** [139.81, 199.13] |
| σ=0.0, flex=0.35 | **−$29.17** [−47.06, −11.28] | **+$179.29** [147.81, 210.78] | **+$167.26** [138.33, 196.19] |
| σ=0.4, flex=0.15 | **−$30.03** [−39.10, −20.95] | **+$106.33** [40.62, 172.04] | **+$115.60** [56.88, 174.33] |
| σ=0.4, flex=0.35 | **−$32.83** [−48.53, −17.13] | **+$109.74** [43.81, 175.66] | **+$117.91** [57.02, 178.81] |

**Bar** (static occupancy 0.53–0.58, peak-anchored $21.67 cocktail / $12.19 beer, real weekend curve):

| cell | computed/1 | nego/1 | nego-noshift/1 |
|---|---|---|---|
| σ=0.0, flex=0.15 | **−$183.58** [−318.73, −48.43] | **−$384.87** [−665.84, −103.90] | +$20.96 [−127.82, 169.74] |
| σ=0.0, flex=0.35 | **−$171.14** [−288.92, −53.37] | **−$327.19** [−544.60, −109.78] | +$52.87 [−51.62, 157.36] |
| σ=0.4, flex=0.15 | **−$176.34** [−311.43, −41.26] | −$295.40 [−724.42, 133.63] | +$90.10 [−91.45, 271.65] |
| σ=0.4, flex=0.35 | **−$170.77** [−310.58, −30.96] | −$262.92 [−653.96, 128.12] | +$104.46 [−64.34, 273.27] |

Bar's own consumer surplus under nego, previously positive everywhere, is
now NEGATIVE in both shock cells (−$40.12, −$83.91): mispriced shift
trades don't just cost the venue, they displace later list-paying
walk-ins who get nothing in exchange (see honest surprises).

### Shift component of the edge (full nego − noshift), $/day — before vs after this calibration

BEFORE is the post-relief-fix artifact (this file's "Relief fix" section
above, `slots_version 2`); AFTER is this calibration (`slots_version 3`).
CI95 is the DIRECT paired (nego − noshift) interval, 5-day blocks —
tighter than differencing the two vs-static CIs above, since nego and
noshift share the same non-shift mechanics and most of their noise
cancels.

| venue | cell | before | after | CI95 (after) | after excludes 0? |
|---|---|---:|---:|---|---|
| barber | σ=0.0, flex=0.15 | +5.19 | −2.04 | [−10.24, 6.15] | no |
| barber | σ=0.0, flex=0.35 | +1.89 | +1.10 | [−6.32, 8.52] | no |
| barber | σ=0.4, flex=0.15 | −9.90 | −10.84 | [−21.24, −0.45] | **yes** |
| barber | σ=0.4, flex=0.35 | −10.53 | −13.67 | [−27.31, −0.04] | **yes** |
| parking | σ=0.0, flex=0.15 | +7.95 | +10.23 | [−1.91, 22.37] | no |
| parking | σ=0.0, flex=0.35 | +10.09 | +12.03 | [7.73, 16.34] | **yes** |
| parking | σ=0.4, flex=0.15 | −9.72 | −9.28 | [−29.50, 10.94] | no |
| parking | σ=0.4, flex=0.35 | −7.00 | −8.18 | [−30.62, 14.27] | no |
| bar | σ=0.0, flex=0.15 | −100.88 | **−405.83** | [−552.50, −259.16] | **yes** |
| bar | σ=0.0, flex=0.35 | −90.27 | **−380.06** | [−530.37, −229.75] | **yes** |
| bar | σ=0.4, flex=0.15 | −79.35 | **−385.50** | [−641.00, −129.99] | **yes** |
| bar | σ=0.4, flex=0.35 | −78.59 | **−367.38** | [−611.29, −123.47] | **yes** |

Barber and parking are statistically indistinguishable from their
pre-calibration values (same sign pattern, overlapping CIs, no cell
changes its significance story in a way that flips a headline claim).
**The bar's shift lever is a different story: it did not merely stay
negative, it got roughly 4× MORE negative ($79–101/day → $367–406/day),
significant in all four cells** (the paired nego-vs-noshift CI excludes
zero everywhere, even in the two shock cells where nego-vs-static alone
is too noisy to call).

### The three verdicts

**(1) Does parking nego (+$100–169/day) survive the commuter-elasticity
fix? YES, essentially unchanged.** Post-fix: +$179.70/+$179.29/+$106.33/
+$109.74 per day, all four cells significant (CIs exclude 0). The
commuter segment is now confirmed structurally least-elastic
(|e_commuter|=0.81 < |e_errand|=0.90 at 7–9am, sigma-driven, not a
`wtp_mult` artifact), but this barely moves the top-line nego edge: the
mechanism's advantage at parking was never about exploiting a
mispriced-elasticity commuter in the first place (per-arrival Nash
gating is robust to which segment shows up), so fixing the elasticity
bug left the headline result intact while making the underlying
mechanism honest.

**(2) Does "no-shift beats full-nego at the bar" survive a properly
peak-anchored bar + realistic weekend curve? YES — it survives and
DEEPENS SUBSTANTIALLY.** The pre-registered H-S2 fallback conclusion
(paper/CRITICAL-ANALYSIS.md §3: "slot-shifting logrolls are a
boba-shaped result that does not generalize to short-peak walk-in
venues") not only holds after this recalibration, it strengthens by
roughly 4×: the shift component went from −$79 to −$101/day
(post-relief-fix) to −$367 to −$406/day (calibrated-world), significant
in all four cells. Full nego is now significantly WORSE than static
itself in the two σ=0 cells (−$384.87, −$327.19, CIs exclude 0); in the
shock cells the point estimate is similarly large-negative but the CI
widens enough to straddle zero for the nego-vs-STATIC comparison
specifically — the direct nego-vs-noshift comparison stays significant
throughout because pairing cancels the shared noise. **Root cause,
diagnosed (not fixed in this pass):** `world.py`'s `peak_hours` and the
`HourMarginLearner` are CALENDAR-BLIND by design (flagged as a known
simplification when the day-of-week machinery was built earlier in this
same session — "computed/1 and nego/1's D-hat is calendar-coarse...
symmetric across both dynamic arms"). That simplification was harmless
before this recalibration, because no real day-of-week demand variance
existed to blend across. It is not harmless now: hour 16, for instance,
is one of the busiest hours of the week on Saturday (part of the
deliberate afternoon build-out, priority #7) but is NEVER flagged
"peak" (the blended-week average dilutes it below the 85%-of-capacity
threshold) and its learned relief value sits at $0.52/tick — a fraction
of hour 20's $3.75/tick — even on the Saturdays where hour 16 is
genuinely as valuable as hour 20. Nego reads this stale, blended signal
and offers shift+discount deals that look individually rational against
its own (mispriced) disagreement point — `neg_venue_gain` (the
per-deal, self-referential accounting) stays positive, +$18,552 over 30
days — while the AGGREGATE `relief_credited` term is deeply negative
(−$13,417 over 30 days): the arm is systematically crediting relief that
isn't real on the days it matters most. This is the same Lucas-critique
pattern CRITICAL-ANALYSIS §3 already fixed twice (the demand forecast,
then the relief basis) — a natural fourth fix would make `peak_hours`
and the learner keyed on `(day % 7, hour)` rather than `hour` alone, but
that is a further architecture extension, pre-registered here as a
follow-up rather than attempted in this pass (out of this task's scope:
a bar-side pricing/curve recalibration, not a relief-mechanism rebuild).
**Said plainly: the refuted-prediction conclusion doesn't just hold —
recalibrating the world to be more realistic made the case against
slot-shifting at short-peak walk-in venues sharper, not weaker.**

**(3) At 62% barber utilization, does the σ=0 positive barber result
strengthen or vanish? It HOLDS, magnitude essentially unchanged.**
Full nego/1 vs static at σ=0: +$11.16 [1.56, 20.76] and +$15.56 [5.03,
26.08] — both significant, both close to the post-relief-fix values
(+$14.61 in both σ=0 cells, per this file's "Relief fix" section). The
σ=0.4 (shock) cells stay statistically indistinguishable from zero in
both the old and new calibration (CIs straddle 0 in every case,
point estimate flipped from modestly positive to modestly negative but
never significant either way). Recalibrating to an average (not
below-average) shop with a realistic deposit no-show regime did not
change the qualitative story: a two-chair shop with mild peaks still has
a small but real (σ=0) nego edge, and shock-day noise still swamps it —
the ≈0 barber finding from CRITICAL-ANALYSIS §6 ("little spot-market
surplus exists, and the mechanism correctly finds little... real
barbershops monetize no-shows via deposits") is unchanged by this
recalibration; if anything it is reinforced, since the recalibrated
world explicitly models the deposit as the venue's incumbent
negotiation mechanism and STILL finds only a few-dollar residual edge
for spot bargaining on top of it.

### Honest surprises (calibrated-world)

- **The peak-anchor fix could not close its own gap.** Raising
  `BAR_COCKTAIL` from $16 to $21.67 was meant to let discount-only arms
  approach the peak crowd's true profit-optimal price. Iterating the
  anchor upward to find a fixed point DIVERGES (verified numerically,
  `slots/calibration.py`'s note): as list rises, fixed-dollar cost
  becomes negligible relative to it, and the unclamped profit-optimal
  multiplier for the peak cell APPROACHES ≈1.42 asymptotically rather
  than converging to 1.0, because `ratio_appeal` is re-inverted against
  the full week's blended mixture on every build (the same mechanism
  barber and parking use) rather than against the peak subset alone —
  unlike vend's `anchor_peak`, which sets list directly off a
  dollar-denominated, list-independent WTP_MU. A genuinely closed fix
  would need an analogous fixed, dollar-denominated "true peak WTP"
  input independent of the ratio-scale architecture every other venue
  parameter here shares — out of scope for this pass; the single-shot
  anchor is reported with its ≈37% residual headroom rather than
  disguised as a full closure.
- **Bar's Saturday revenue share landed at 22.8%, short of the >25%
  Nielsen target, for an architectural reason, not a tuning failure.**
  19:00–22:00 is already capacity-saturated on an ORDINARY weekday
  (D-hat there runs 340–610 unit-ticks against each hour's 360-tick
  ceiling), and static charges a flat per-tick rate regardless of hour,
  so a capacity-saturated block's revenue is CAPPED at capacity × price
  no matter how much extra demand is queued behind it — pushing the
  Saturday afternoon arrival-rate multiplier far higher (tested up to
  36×) showed sharply diminishing returns once 15:00–18:00 approached
  its own ≈3,240-unit-tick capacity ceiling (Saturday is already at ≈92%
  of its OWN theoretical max revenue). Closing the rest of the gap to
  25%+ would need a lever this pass didn't build: day-of-week kind-mix
  (more cocktails on Saturday night) or genuinely extended hours, either
  of which raises the ALREADY-saturated evening block's $/tick rather
  than fighting for slack afternoon capacity. Flagged as a pre-registered
  follow-up alongside the peak-anchor residual above.
- **The recalibration is bounded by its own H-S1 ladder.** Every
  attempt to push the bar's Saturday afternoon further toward the 25%+
  target also raises `congestion_ratio("bar")`; several tried
  configurations pushed it PAST parking's 2.33, which would have broken
  the pre-registered demand-asymmetry ladder (parking > bar > barber).
  The shipped calibration lands at bar congestion 2.21 — real margin
  below parking's 2.33, but visibly closer than the pre-calibration
  1.62. The two constraints (Nielsen's revenue-share target and H-S1's
  engineered ladder) are close to binding simultaneously; a much hotter
  Saturday would need either a higher parking congestion ratio or an
  explicit decoupling of the ladder from the bar's calendar-real
  recalibration.
- **`computed/1` now fails significantly at the bar too, not just
  parking.** Pre-calibration bar computed/1 was never significant
  (small numbers, CIs straddling 0). Post-calibration it is significantly
  NEGATIVE in all four cells (−$171 to −$184/day, every CI excludes 0) —
  the same calendar-blind D-hat/mstar mechanism implicated in the
  bar's shift-lever deepening (verdict 2) also degrades `computed/1`'s
  hourly re-solve, since its run-out-hold and discount decisions read
  the same blended-week forecast. H-S3 ("computed ties static... fails
  at parking") now also fails at the bar — a second venue, not a
  reversal of the parking finding, but a widening of it.

### Tests added (all in `slots/tests/test_slots.py`)

- `test_barber_utilization_matches_platform_average` — static occupancy
  in [0.55, 0.68] (Squire/Zenoti ~62% average-shop band).
- `test_deposit_regime_noshow_rate` — the deposit/no-deposit regime
  constants (4%/12%) and the venue default equal the deposit cell;
  realized no-show rate in [0.02, 0.06].
- `test_parking_commuter_is_least_elastic` — segment sigma ordering
  (commuter < event < errand) and the empirical conversion-rate
  elasticity ordering at the 7–9am commuter window.
- `test_bar_saturday_revenue_share` — Saturday >22% and Fri+Sat in
  [0.35, 0.55] of a whole-week (35-day) revenue window.
- `test_bar_anchor_at_least_peak_hour_wtp_implied_price` — the combined
  (day, hour) WTP multiplier grid tops out at exactly 1.0 and the new
  dollar anchor exceeds the old flat list on both kinds.
- `test_asymmetry_ladder_is_as_engineered` (pre-existing, unchanged
  assertion) — re-verified to still pass at bar congestion 2.21 <
  parking's 2.33.
- Updated `test_static_list_is_mixture_optimal` for `mstar`'s new
  `(day % 7, hour)` keying (the bar's peak is now calendar-dependent).
- Updated `_edge_shift_scenario` and `test_rigid_customers_do_not_get_shifted`
  to probe the bar's new TRAILING peak/off-peak boundary (22:00→23:00,
  a +30-min shift) — the old 19:00 LEADING edge is no longer a
  peak/off-peak crossing once the weekend curve makes 17:00 peak too.

### Files changed

`slots/calibration.py` (barber/parking/bar recalibration, all three
venues' notes), `slots/world.py` (per-segment sigma; day-of-week
`dow_rate_mult`/`dow_wtp_mult` machinery; `mstar` keyed by
`(day % 7, hour)`; generalized `_pstar_mixture`), `slots/policies.py`
(`ComputedPolicy.mult_of` reads the day-keyed `mstar`), `slots/run.py`
(`SLOTS_VERSION` 2 → 3), `slots/tests/test_slots.py` (5 new tests, 2
updated for the new calibration), `slots/results.json` (regenerated,
`slots_version 3`).

---

## Calendar-aware relief (2026-07-10) — CRITICAL-ANALYSIS §3 CALIBRATED-WORLD follow-up, `slots_version 4`

*30 paired days per grid cell, seed 20260710. Reproduce with
`python3 -m slots.run --grid --days 30 --seed 20260710`.*

This implements the fourth Lucas-critique fix, pre-registered in
`paper/CRITICAL-ANALYSIS.md` §3's CALIBRATED-WORLD UPDATE: `peak_hours`
and the `HourMarginLearner` relief EWMA were CALENDAR-BLIND. Harmless
before the weekend curve landed, that blindness meant the bar's Saturday
16:00 — one of the week's busiest hours — was never flagged "peak" (the
week-blended average diluted it below the 85%-of-capacity threshold) and
its learned relief value sat at $0.52/tick vs hour-20's $3.75/tick. The
arm priced freed weekend-afternoon shoulder slots — exactly the ones the
calibration just made valuable — as near-worthless, and the shift
component deepened to a **DIAGNOSED-ARTIFACT −$367–406/day**.

**The fix.** `peak_hours` and the relief learner are now keyed on the
**day-of-week bucket** (`Venue.dow_key`: `day % 7` for a venue whose
`dow_rate_mult`/`dow_wtp_mult` actually vary — the bar — and a single
pooled bucket `0` for a calendar-flat venue — barber/parking, whose seven
days are one statistical process, so pooling their observations is both
strictly more sample-efficient AND makes them byte-identical to the
pre-fix per-hour learner). This is the same keying `computed/1`'s `mstar`
has used since the calibrated-world pass. Mechanics:
`world.py` derives a per-day-of-week peak set (`peak_by_dow`, from that
day's own from-open expected demand, not the week average) and
`is_peak(day, hour)`/`peak_hours_on(day)`; `capacity_shadow` reads the
day being simulated; `HourMarginLearner` folds each day's realized margins
into that day-of-week's EWMA and `warmup_hour_value` warms up each
day-of-week's peak slots. `expected_demand`/`suffix_demand` (the D-hat
displacement *probability*) stay calendar-coarse — the flagged
simplification, symmetric across `computed/1` and `nego/1`; the
calendar-aware parts are the peak flags, the realized-occupancy gate, and
the learned per-day slot values.

**Scope, verified in the artifact diff.** Barber and parking are
**byte-identical to `slots_version 3`** (calendar-flat → one pooled
bucket → the pre-fix learner exactly): every barber/parking cell's margin,
shift component, and CI reproduces v3 to the cent (barber shift
−2.04/+1.10/−10.84/−13.67; parking +10.23/+12.03/−9.28/−8.18; barber σ=0
nego-vs-static significant-positive verdict +$11.16 [1.56, 20.76] and
+$15.56 [5.03, 26.08] preserved). **Only the bar moves.**

### Bar shift component (full nego − noshift), $/day — BEFORE vs AFTER the calendar-aware fix

BEFORE is `slots_version 3` (the calibrated-world section above); AFTER is
this fix (`slots_version 4`). CI95 is the DIRECT paired (nego − noshift)
interval, 5-day blocks (pairing cancels the shared non-shift noise, so it
is tighter and more powerful than differencing the two vs-static CIs).

| cell | before | after | CI95 (after) | after excludes 0? |
|---|---:|---:|---|---|
| σ=0.0, flex=0.15 | **−405.83** | **−115.36** | [−184.95, −45.76] | **yes** |
| σ=0.0, flex=0.35 | **−380.06** | **−110.62** | [−205.56, −15.67] | **yes** |
| σ=0.4, flex=0.15 | **−385.50** | **−69.37** | [−109.30, −29.45] | **yes** |
| σ=0.4, flex=0.35 | **−367.38** | **−59.74** | [−122.11, +2.63] | no |

**The shift lever moved sharply toward zero — a ~70–84% collapse in
magnitude** (−$367–406/day → −$60–115/day). The −$400 was indeed an
artifact of the calendar-blind learner, as pre-registered. The
`relief_credited` mispricing roughly halved too (−$11.3k to −$14.3k over
30 days → −$5.8k to −$7.4k).

### Bar margin Δ/day vs static — BEFORE vs AFTER

| cell | nego BEFORE | nego AFTER | noshift BEFORE | noshift AFTER |
|---|---:|---:|---:|---:|
| σ=0.0, flex=0.15 | −384.87 [−665.84, −103.90] | **+133.91 [44.89, 222.93]** | +20.96 [−127.82, 169.74] | **+249.27 [186.23, 312.30]** |
| σ=0.0, flex=0.35 | −327.19 [−544.60, −109.78] | **+145.80 [57.91, 233.68]** | +52.87 [−51.62, 157.36] | **+256.42 [220.01, 292.82]** |
| σ=0.4, flex=0.15 | −295.40 [−724.42, 133.63] | **+186.86 [45.65, 328.08]** | +90.10 [−91.45, 271.65] | **+256.24 [146.19, 366.28]** |
| σ=0.4, flex=0.35 | −262.92 [−653.96, 128.12] | **+200.30 [58.72, 341.87]** | +104.46 [−64.34, 273.27] | **+260.04 [149.67, 370.40]** |

The calendar-aware fix **rescued full-nego from being a net loser at the
bar**: it went from significantly WORSE than static (−$263–385/day, the
v3 artifact) to a clear WINNER (+$134–200/day, all four CIs exclude 0).
That reversal — the calibrated-world section's headline that "no-shift
beats full-nego" had *deepened* until full-nego lost to static itself —
was the calendar-blind learner destroying real value on the days it
mattered most, not a clean economic verdict.

### The trustworthy verdict

**No-shift still wins at the bar — but by a trustworthy $60–115/day, not
the artifact's $367–406/day.** The direct paired shift component is
significantly negative in **3 of 4 cells** (only σ=0.4/flex=0.35 now
straddles zero, at −59.74 [−122.11, +2.63]); no-shift captures
+$249–260/day vs full-nego's +$134–200/day. So with the weekend shoulder
slots CORRECTLY valued, full-nego closes most of the gap on no-shift but
**does not overtake it** — no-shift wins even at correct slot values. **The
boba-shaped-venue conclusion is confirmed CLEAN.** The refuted-prediction
finding from CRITICAL-ANALYSIS §3 stands at a magnitude we now trust:
slot-shifting logrolls are a boba-shaped result (long service times,
order-ahead, a shiftable queue) that does not generalize to short-peak
walk-in venues; at 60 seats with a 4-hour peak the correct broker plays
no-shift. The residual −$60–115/day is the genuine economic effect the
pre-registration predicted, and its diagnosed cause is unchanged by this
fix and *not further reducible by a learned slot value*: whether THIS
tick, TODAY, would have been locally rebooked inside the ±30-min window
buyers actually accept is same-day-trajectory information that **no
day-level average can carry — not even a per-day-of-week one.** Making the
learner calendar-aware removed the systematic cross-day mispricing (the
$400 artifact); it cannot and does not remove the within-day,
within-window state the Nash split hands partly to the buyer as a real
discount.

**H-S2, re-revisited: still FAILS, now at a trustworthy magnitude.** In no
flex=0.35 cell does the shift component exceed the price-cut component
(bar −110.62 vs +256.42). The pre-registered prediction ("the shift lever
becomes ≥ 0 everywhere and full nego matches or beats the no-shift
ablation") is REFUTED at the bar — but the case is now stated at
−$60–115/day, the honest size, rather than the calendar-blind −$400.

### Anchor-headroom investigation (the ~37% residual)

The calibrated-world section flagged a residual: no finite anchor pins the
peak's own unclamped profit-optimal multiplier to 1.0 under the shared
full-week ratio-appeal inversion. Measured at the shipped anchor the peak
crowd's unclamped optimum is **m\* = 1.316 → 31.6% headroom** (clamped to
1.0 by the discount-only ceiling). The pre-registered question was whether
a per-(day, hour) anchor or a non-shared inversion closes it. **Both were
tested numerically; neither is clean — reported, not fixed:**

- **Raise the dollar anchor (toward a fixed point).** Confirmed to
  DIVERGE: as the anchor grows and cost becomes negligible, the peak's
  unclamped m\* falls only toward an asymptote **> 1.0** (31.6% headroom at
  ×1 → 23.1% at ×100, never 0). No finite anchor closes it.
- **Non-shared (peak-subset) inversion** (invert R against the peak cell
  alone, vend's `anchor_peak` spirit): pins the peak to exactly m\* = 1.0
  (R drops 1.6255 → 1.2047), BUT the arrival-weighted **all-week blended
  optimum collapses from 0.996 to 0.767** — static, posting its one
  sticker at m = 1, would then OVERPRICE the entire week by ~30% (every
  off-peak cell's optimum falls to 0.59–0.73). That turns the competent
  static baseline into a **strawman**, and discount-only arms would beat it
  spuriously off-peak — precisely the artifact CRITICAL-ANALYSIS §1 warns
  against. NOT clean.
- **Per-(day, hour) anchor** would require `static` to reprice by
  (day, hour), dissolving the defining "one posted sticker all week"
  baseline into a second copy of `computed/1`. Not applicable to a
  posted-sticker control.

**Conclusion: the ~32–37% headroom is the irreducible price of two
deliberate design invariants — discount-only dynamic arms AND a
single-sticker static that is the all-week profit-optimum — at a venue
with strong within-week WTP dispersion. Closing it requires abandoning
one of them.** Critically, the headroom is **symmetric across nego and
noshift** (both discount-only, both capped at the same list), so it does
NOT touch the shift-lever verdict above — it only bounds how much any
discount-only arm can beat static at the peak. A genuinely closed fix
would need a fixed, dollar-denominated "true peak WTP" input independent
of the shared ratio-scale architecture every other venue parameter here
uses (vend's pattern) — a larger re-architecture, out of this pass's
scope.

### Tests added / updated (all in `slots/tests/test_slots.py`)

- `test_peak_hours_are_calendar_aware` — the bar's 16:00/17:00 flag peak on
  Saturday (day 5) but not on a weekday (day 0); barber/parking peak sets
  are identical across every day-of-week (pooled bucket).
- `test_learner_and_warmup_are_keyed_on_day_of_week` — the task's explicit
  check: Saturday 16:00 learns a value DISTINCT from (and higher than) the
  same clock hour on a low-traffic weekday; a weekday fold does not move
  Saturday's EWMA; warmup differs by day-of-week too.
- `test_relief_credit_flows_the_calendar_aware_value` — integration: a
  fresh nego arm mints positive warmup relief (0.6 × margin × 3 freed peak
  ticks) for a −30-min shift off a Saturday-afternoon peak slot, and zero
  for the identical clock-hour shift on a Monday where 16:00 is not peak.
- Updated `_learned_policy`, `_expected_relief`,
  `test_relief_prices_freed_peak_at_learned_regime_margin_not_list`,
  `test_shoulder_displacement_is_charged`,
  `test_warmup_falls_back_to_conservative_fraction_of_list_margin`,
  `test_learner_observes_soldout_gated_realized_margin`, and
  `test_run_day_feeds_the_learner_realized_margins` for the (day-of-week,
  hour) keying. Full slots suite: **37 passing**
  (`test_committed_results_stay_reproducible` re-pins `slots_version 4`).

### Files changed

`slots/world.py` (`Venue.dow_key`; per-day-of-week `peak_by_dow` built from
`open_demand_by_dow`; `is_peak`/`peak_hours_on`; `capacity_shadow` reads
`state.day`), `slots/policies.py` (`HourMarginLearner` keyed on
`v.dow_key(day)` for `value`/`end_day`; `warmup_hour_value(v, day, hour)`
calendar-aware; `nego_quote`/`NegoPolicy.quote_for`/`end_day` thread the
day), `slots/run.py` (`SLOTS_VERSION` 3 → 4; `end_day` passes the day;
`peak_sold_ticks` uses `peak_hours_on(day)`; config reports
`peak_hours_by_dow`), `slots/tests/test_slots.py` (3 new tests, 7
updated), `slots/results.json` (regenerated, `slots_version 4`).


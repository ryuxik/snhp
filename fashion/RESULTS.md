# FASHION P0 results — markdown/1 vs cliff/1

*40 seasons per cell, seed 20260710, paired seeds (identical buy + shopper
stream per season across arms). Reproduce:
`python3 -m fashion.run --seasons 40 --seed 20260710 --grid --out fashion/results.json`.
Seasons are independent replications, so CIs are plain paired t (block=1).*

## Headline: gross margin Δ per season (markdown/1 − cliff/1)

| cell (σ_buy / σ_cal / waiters) | cliff GM/season | markdown GM/season | Δ | Δ 95% CI | Δ% |
|---|---:|---:|---:|---|---:|
| control (0 / 0 / 0) | 10,221 | 11,887 | **+1,666** | [1,382, 1,950] | +16.3% |
| 0.15 / 0.0 / 15% | 10,094 | 11,546 | **+1,451** | [1,193, 1,710] | +14.4% |
| 0.15 / 0.0 / 45% | 9,816 | 10,779 | **+963** | [764, 1,163] | +9.8% |
| 0.15 / 0.2 / 15% | 8,584 | 10,311 | **+1,728** | [1,159, 2,297] | +20.1% |
| 0.15 / 0.2 / 45% | 8,715 | 9,530 | **+815** | [426, 1,204] | +9.4% |
| 0.35 / 0.0 / 15% | 9,425 | 10,951 | **+1,526** | [1,220, 1,831] | +16.2% |
| 0.35 / 0.0 / 45% | 9,282 | 10,253 | **+972** | [747, 1,196] | +10.5% |
| 0.35 / 0.2 / 15% | 7,912 | 9,606 | **+1,694** | [1,189, 2,199] | +21.4% |
| 0.35 / 0.2 / 45% | 8,080 | 8,901 | **+821** | [447, 1,195] | +10.2% |

markdown/1 wins every cell; no CI touches zero. Consumer surplus is ALSO
higher under markdown/1 in every cell (Δ ≈ +1,850 to +2,300/season, all CIs
positive) — the cliff destroys value on both sides of the counter, mostly
through salvage and through selling stale units late at −70%.

## The mechanism (units by realized depth, per season)

| cell | cliff −70% units | markdown −70% units | cliff salvage Δ | full-price units Δ |
|---|---:|---:|---:|---:|
| control | 23.6 | 2.6 | −21.4 | −100.3 |
| 0.35 / 0.2 / 15% | 33.8 | 8.6 | −22.2 | −81.1 |
| 0.35 / 0.2 / 45% | 45.3 | 12.5 | +1.8 | −68.0 |

The engine's move is **earlier, shallower markdowns**: it abandons most
full-price weeks (units_full drops by ~70–100/season), sells the bulk of
the season at −15…−30% while WTP is still fresh, and almost never touches
the −70% rung (3–13 units vs the cliff's 22–46). Sell-through rises to
~93–100% (vs 84–100%), salvage mostly disappears. Scarce cells are the
exception that proves the stockout-hazard term works: `min(D, stock)` holds
under-bought sizes at high prices while the cliff marks them down on
schedule.

## Honest surprises (vs the pre-registered expectations)

1. **The anti-claim FAILED, informatively: the control cell is not close.**
   Expectation was "at perfect buy + no waiters they should be close" —
   instead markdown/1 wins +16.3% with the tightest CI of the grid. Reason:
   the buy is planned against the CLIFF CALENDAR (the industry's own plan),
   which deliberately over-buys relative to full-price demand — clearance
   volume is in the plan. Given that inventory, holding MSRP for 8 weeks is
   already suboptimal even with a perfect plan and zero strategic waiting.
   The control cell therefore measures the pure calendar inefficiency: the
   cliff is not the optimal policy even for the inventory the cliff plan
   buys. (A buy planned to the ENGINE's path would shrink this — P1 should
   add a buy-to-engine plan arm to separate "better calendar" from "better
   buy".)
2. **Gains concentrate at high σ_cal (miscalibration), not high σ_buy.**
   +20–21% at σ_cal=0.2 vs +14–16% at σ_cal=0 (waiters 15%). Buy error is
   mean-one per cell and roughly washes out across the 16 cells; appeal
   miscalibration hurts the cliff more because its schedule can't react at
   all, while the engine re-solves weekly on remaining stock (which it
   observes truly) even though its demand LEVEL estimate is wrong all
   season (no learner in P0). σ_buy raises the engine's own −70% units
   (broken cells still need clearing: 4→8→13 as σ_buy grows) but moves the
   margin edge only ~2 points.
3. **Strategic waiters cut the engine's edge roughly in half** (+14–21% →
   +9–10% at 45% waiters). Waiters refuse the engine's early shallow
   markdowns (their rule needs p ≲ 0.79 × WTP absent stockout risk), which
   erodes exactly the timing advantage the engine wins by; the cliff was
   going to serve them late and deep anyway. This is the P0 case for the
   size-risk-priced path and the offer arm (H-F2): the engine currently
   prices waiters as if they were loyal (myopic solver, flagged) and pays
   for it.

## H-F3 check: do waiters capture more surplus under the cliff?

Yes at 15% waiter share — cliff waiters capture ~1,500–1,630/season vs
~1,280–1,320 under markdown (Δ CIs all negative, e.g. [−412, −264] at
σ_buy=0.15/σ_cal=0). The cliff pays people to wait; the smooth path pays
them less. At 45% waiter share the gap washes out (CIs straddle zero;
at σ_buy=0.35/σ_cal=0 waiters even do marginally better under markdown,
Δ +104 [−4, +211]) — when half the crowd waits, the engine ends up meeting
them at similar late-season prices. Note this P0 grid holds waiter share
FIXED per cell; the full H-F3 claim ("the cliff TRAINS waiting
season-over-season, the engine doesn't") needs cross-season waiter-share
dynamics, which are deliberately out of P0 scope.

Two costs of the engine worth stating plainly: **lost late shoppers** —
markdown sells out ~weeks 11–13 and turns away roughly twice as many
arrivals who find their size gone (they'd have found −70% leftovers under
the cliff); and at σ_cal=0.2 + 45% waiters its sell-through is actually
slightly LOWER than the cliff's (94.5 vs 96.1) while margin is still ~9%
higher — it does not chase sell-through for its own sake.

## Caveats (attack here)

* **The buy is planned to the cliff calendar for BOTH arms.** This is the
  realistic pilot scenario ("we replace your markdown calendar, same
  inventory") but it means the control-cell win partly reflects the plan's
  built-in overhang, not adaptive skill. See surprise #1.
* **One-style shoppers, no cross-style substitution** — a markdown on the
  coat steals nothing from the dress. Keeps the operator's demand model
  correctly specified (policy differences are pricing, not
  misspecification), but real substitution would blunt per-style markdowns.
* **The solver is myopic about waiters and never learns in-season** — it
  prices every arrival as loyal-now and runs on the buy-time appeal
  estimate all 16 weeks. Both flags favor NEITHER arm structurally (the
  cliff uses no demand model at all), but the waiter blindness is exactly
  where the 45%-waiter cells bite.
* **Waiter behavior is a documented one-step lookahead** with a stationary
  price-drift belief (−8%/week, the cliff's season average) — not exact
  calendar knowledge, not optimal stopping. Calendar-aware waiters would
  hurt the cliff MORE (they'd never buy in weeks 6–8), so this choice is,
  if anything, kind to the control.
* **No demand shocks** (weather/trend) in P0 — σ_buy and σ_cal are the only
  noise beyond Poisson arrivals and WTP dispersion. Shock knobs are the
  natural next realism step and historically (vend P1.5) they helped the
  adaptive arm.
* Consumer surplus is booked at purchase-week WTP (staleness applied), and
  a shopper's outside option is simply not buying — no competing retailer.

## Returns (CALIBRATION-TARGETS #6: NRF 2024 — 16.9% retail, ~26% online apparel)

*Same 40 seasons/cell, seed 20260710, paired seeds — plus a THIRD dimension,
return rate r ∈ {0 (P0 repro), 0.17, 0.26}, swept across the full
pre-registered 9-cell buy×cal×waiter grid. Reproduce:*
`python3 -m fashion.run --seasons 40 --seed 20260710 --arms cliff,markdown --returns-grid --out fashion/results.json`.

**Mechanism.** A sale at price p returns with probability r after a lag
drawn Uniform{7..21} days → `max(1, round(days/7))` ∈ {1, 2, 3} weeks
(documented, world.py `sample_return`). It is refunded at the **PAID**
price and re-enters sellable stock at *that week's* price if a selling week
remains, else it salvages. The return draw is keyed on the shopper's
**identity** (uid), never on price or arm, so a shopper who buys in both
arms draws the identical return flag + lag — only the refund price and the
resale week differ across arms, isolating the timing mechanism cleanly.
r=0 reproduces the pre-returns grid byte-for-byte (verified: `results.json`
control-cell Δ at r=0 is identical to the pre-returns table above, 1,666.18
[1,382, 1,950]).

### Headline: does markdown-beats-cliff survive returns?

**Yes — in every one of the 9 cells at both return rates, and the edge
GROWS with r rather than shrinking.** No CI touches zero anywhere in the
27 (cell × r) combinations.

| cell (σ_buy / σ_cal / waiters) | Δ% r=0 | Δ% r=0.17 | Δ% r=0.26 | DiD: edge growth @ r=0.26 vs r=0 (95% CI) |
|---|---:|---:|---:|---|
| control (0 / 0 / 0) | +16.3 | +43.1 | +60.9 | +1,998 [1,792, 2,205] |
| 0.15 / 0.0 / 15% | +14.4 | +34.2 | +47.7 | +1,572 [1,386, 1,759] |
| 0.15 / 0.0 / 45% | +9.8 | +22.2 | +30.0 | +1,039 [901, 1,177] |
| 0.15 / 0.2 / 15% | +20.1 | +37.9 | +52.0 | +849 [575, 1,123] |
| 0.15 / 0.2 / 45% | +9.4 | +18.5 | +25.2 | +555 [351, 759] |
| 0.35 / 0.0 / 15% | +16.2 | +35.5 | +47.5 | +1,280 [1,058, 1,501] |
| 0.35 / 0.0 / 45% | +10.5 | +22.7 | +29.7 | +880 [728, 1,032] |
| 0.35 / 0.2 / 15% | +21.4 | +38.8 | +51.8 | +645 [382, 907] |
| 0.35 / 0.2 / 45% | +10.2 | +19.1 | +25.1 | +430 [230, 631] |

The "DiD" column is a paired difference-in-differences: `(markdown−cliff
edge at r) − (markdown−cliff edge at r=0)`, computed per season (same buy +
shopper stream at every r, since `build_catalog`/`planned_depth` don't
depend on `return_rate`) then given a plain paired t-CI. Every cell's CI at
r=0.26 is strictly positive — the edge growth is not a fluke of the control
cell. r=0's own margin-Δ CIs are in the pre-returns table at the top of
this file; the raw (not DiD) margin-Δ 95% CIs at the two return rates,
same paired-t construction, for the record:

| cell | Δ mean, CI95 @ r=0.17 | Δ mean, CI95 @ r=0.26 |
|---|---|---|
| control | 3,211 [2,969, 3,454] | 3,664 [3,400, 3,929] |
| 0.15 / 0.0 / 15% | 2,617 [2,379, 2,854] | 3,024 [2,787, 3,261] |
| 0.15 / 0.0 / 45% | 1,732 [1,552, 1,911] | 2,002 [1,803, 2,201] |
| 0.15 / 0.2 / 15% | 2,358 [1,865, 2,851] | 2,577 [2,140, 3,014] |
| 0.15 / 0.2 / 45% | 1,220 [877, 1,563] | 1,370 [1,052, 1,688] |
| 0.35 / 0.0 / 15% | 2,525 [2,270, 2,781] | 2,805 [2,561, 3,050] |
| 0.35 / 0.0 / 45% | 1,664 [1,460, 1,868] | 1,852 [1,628, 2,076] |
| 0.35 / 0.2 / 15% | 2,206 [1,767, 2,646] | 2,339 [1,943, 2,735] |
| 0.35 / 0.2 / 45% | 1,159 [851, 1,467] | 1,251 [951, 1,552] |

All 18 (cell × r) CIs are strictly above zero — no win claim in this
section rests on a CI that touches zero.

### The mechanism, confirmed: returns hit the cliff harder because the cliff overholds full price

Control cell, per-season means:

| r | cliff GM | cliff Δ vs r=0 | markdown GM | markdown Δ vs r=0 | cliff returns | markdown returns |
|---|---:|---:|---:|---:|---:|---:|
| 0.00 | 10,221 | — | 11,887 | — | 0.0 | 0.0 |
| 0.17 | 7,443 | −27.2% | 10,654 | −10.4% | 36.9 | 44.3 |
| 0.26 | 6,020 | **−41.1%** | 9,684 | **−18.5%** | 56.4 | 73.5 |

cliff/1 loses margin roughly **2.2× faster (relative)** than markdown/1 as
returns rise from 0 to 26%, even though markdown/1 actually logs *more*
raw return events (73.5 vs 56.4/season) — markdown sells more units overall
(no MSRP-holding stalls) so it has more transactions exposed to the same
per-transaction return draw. What matters is the refund-vs-resale **price
gap**, not the return count:

* cliff/1 holds MSRP for 8 of 16 weeks and sells ~100 units/season at full
  price (`units_full`, from the pre-returns table). A full-price sale that
  returns during weeks 9+ is refunded at MSRP but the unit re-shelves into
  a −30/−50/−70% week — a large, near-certain loss on every such return.
  `units_deep` (−70%-and-below units) for cliff climbs 23.6 → 32.2 → 35.1
  as r rises, precisely because returned full-price stock keeps cascading
  into deep clearance.
* markdown/1 essentially never sells at full price (`units_full` ≈ 0 in
  every P0 cell — its earlier-shallower-markdown strategy means paid
  prices already track close to what the unit will fetch on any resale).
  Its `units_deep` also grows with r (2.6 → 10.5 → 20.6) but from a far
  smaller base and a much smaller paid-vs-resale gap per event.

This is exactly the pre-registered hypothesis — "an item sold full-price
and returned during clearance re-sells at clearance, so early-season
overselling is penalized" — except the effect is **asymmetric across
arms**, not merely present: it penalizes the policy that overholds full
price (the cliff, by calendar construction) far more than the one that
doesn't. Returns turn out to be a second, independent argument for
markdown/1 beyond the original timing story, not a threat to it.

### H-F3 (waiters) under returns

**15% waiter share: the original H-F3 direction is robust to returns.**
Cliff-arm waiters keep capturing significantly more surplus than
markdown-arm waiters at every r (CI excludes zero in all 4 fifteen-percent
cells, all 3 return rates) — e.g. `buy0.15_cal0_wait0.15`: cs_waiter Δ
(markdown − cliff) −338 [−412, −264] at r=0, shrinking to −213 [−268,
−158] at r=0.26. Direction holds, magnitude shrinks (returns give waiters
in the markdown arm a bit of the "free option" back, since a
returned-then-resold unit sometimes lands at a price they'd have waited
for anyway).

**45% waiter share: still the noisy washout zone documented in surprise
#3, and two of four cells drift to a significant sign flip at higher r —
flagged, not claimed as a finding.** `buy0.15_cal0_wait0.45` goes from
insignificant (Δ −17 [−104, 70]) at r=0 to significantly *positive* (Δ
+111 [33, 189]) at r=0.26 — a real reversal, not noise, at the highest
return rate only. `buy0.35_cal0_wait0.45` was ALREADY borderline-positive
at r=0 (Δ +104 [−4, 211], CI just touching zero — this cell was the one
partial exception noted in the pre-returns surprise #3) and returns push
it to clearly significant positive at both r=0.17 (Δ +143 [37, 248]) and
r=0.26 (Δ +251 [156, 346]). The other two 45%-waiter cells
(`buy0.15_cal0.2_wait0.45`, `buy0.35_cal0.2_wait0.45`) stay negative or
insignificant throughout. Net read: returns do NOT reverse H-F3 at 15%
waiters (robust); at 45% waiters, where the pre-returns result was already
inconsistent across cells, returns push 2 of 4 cells toward a "waiters do
better under markdown" reversal — plausibly because more returns mean more
mid-season restocks landing at markdown's already-discounted prices,
which is exactly what a waiter wants, while the cliff's calendar can't
offer an equivalent early discount. This is a real, cell-level signal
(the CIs are genuinely tight), but calling it a season-level headline
would need a dedicated waiter-share × return-rate grid (finer than
{15%, 45%}) before it's pre-registered as a claim.

### Scope: the consumer model cannot express strategic price-protection returns

The return draw in `sample_return` is **exogenous and price-independent**
— it fires off shopper identity alone ("changed my mind / didn't fit"),
never off the price the shopper paid or the price path they observe. It
therefore does **not** model the behavior CALIBRATION-TARGETS' waiter
section gestures at — a shopper who buys early, watches the price drop,
and returns-and-rebuys (or simply returns) purely to capture the lower
price ("buy-early-return-if-cheaper" strategic behavior, sometimes called
price-protection returns in retail). Building that would require making
the return decision endogenous to the price trajectory (e.g., return iff
current price < paid price − hassle cost) and is out of scope for #6 — it
is a natural P1 extension that would sit on top of the existing waiter
machinery (`waiter_buys_now`) rather than replace it, and would likely
*shrink* the markdown edge somewhat (it gives strategic shoppers a second
lever against the engine's price cuts, symmetric to how waiting already
does). Flagging rather than estimating: no number is claimed for this
un-modeled mechanism.

### Caveats (attack here)

* **`return_rate_realized`, `sell_through`, `units_full`/`units_deep` are
  all GROSS metrics under returns** — a physical unit that sells, returns,
  and resells is counted (and independently return-eligible) at every leg
  of that chain. `sell_through` exceeding 100% (markdown hits 129% at
  r=0.26 in the control cell) is resells, not an accounting error; net
  units kept by customers = `units_sold − returns`, which the
  refund-conservation identity (tested) ties to `salvage_units`.
* **Returns are frictionless for the consumer** in this model: a returned
  purchase nets the shopper ~$0 surplus (refund reverses exactly what they
  paid), with no modeled hassle cost, shipping cost, or time cost of
  returning. Real returns carry friction on both sides (NRF's shrink/
  processing-cost literature is a separate line item this sim doesn't
  touch) — this likely makes returns slightly too easy/frequent relative
  to a friction-priced reality, which if anything means the leakage
  documented above is an upper bound.
* **The lag window (Uniform 7–21 days) is a labeled assumption**, not a
  fitted hazard — CALIBRATION-TARGETS §2 gives a return-RATE source (NRF
  2024) but no published lag-distribution shape for fashion apparel
  specifically. A front-loaded (e.g. geometric/exponential) hazard would
  pull returns earlier in the season and *reduce* the cliff-vs-markdown
  gap studied above (less time for a full-price sale to land deep in
  clearance); a back-loaded one would widen it. Uniform is the neutral
  choice absent evidence either way.
* **No channel split.** NRF's 26% figure is online apparel specifically;
  this sim has no store/e-comm channel mix, so the r=0.26 cells should be
  read as "if this catalog's ENTIRE season behaved like online apparel,"
  not a blended estimate for a store with both channels.
* **Cascading returns are possible but rare by construction**: a
  returned-then-resold unit can itself be returned again (each sale draws
  independently on the buying shopper's uid), bounded by the ~16-week
  season and 1–3-week lag — the model doesn't cap this explicitly, it
  just runs out of season.

# v4 TIMELINE-OPTIMIZED MARKDOWN (2026-07-10) — CRITICAL-ANALYSIS §4

*Everything above is the P0 / returns record, preserved
(`fashion/results.json` = the returns sweep). The markdown-beats-cliff result
so far compares FIXED schedules — the engine solve vs a −70% cliff. The
referee item: give the engine a markdown OPTIMIZED against its own LEARNED
demand curve + RETURN timeline, then re-ask both questions at the returns grid
r ∈ {0, 0.17, 0.26}. Reproduce:*
`python3 -m fashion.run --timeline-sweep --seasons 40 --seed 20260710 --out fashion/results-v4.json`.

**Two new arms** (`fashion/policies.py`):
* **opt/1** — timeline-optimized. Two upgrades over markdown/1, both on the
  TIME axis: (1) a LEARNED appeal level (cumulative, censoring-aware
  sell-through, `AppealLearner`) replacing the frozen buy-time estimate; (2) a
  RETURN-aware solve that forward-simulates the season under an anticipated
  declining path, with returned units re-entering sellable stock at the
  published lag (`world.return_lag_pmf`, derived from the same days→weeks map
  the sampler uses) and reselling at the lower price they will actually fetch —
  pricing the refund-vs-resale gap markdown/1 is blind to.
* **optnl/1** — the ablation: the returns-aware solve on the STATIC estimate
  (learning OFF). Isolates the RETURN-timing half from the LEARNING half. At
  r=0 both arms' returns machinery is inert, so **optnl/1 is byte-identical to
  markdown/1 at r=0** (verified: control-cell GM 11,887 = 11,887) and opt/1 is
  exactly markdown/1 + learning — a clean decomposition.

Return rate + lag curve are given as PUBLIC structural knowledge (a retailer
knows both from history, like the arrival taper); only the appeal LEVEL is
learned. All four arms (cliff, markdown, opt, optnl) share paired seeds per
season; every Δ carries a paired t-CI; **no win claim where a CI includes
zero.** `ANTICIPATED_DRIFT=0.96`, `LEARN_GAIN=0.7`.

## Q1 — does the engine-optimized schedule beat the fixed ladder (markdown/1)? NO.

Gross-margin Δ vs markdown/1 per season (**bold = CI excludes zero**; + = beats
the ladder), 40 seasons:

| cell (σ_buy/σ_cal/wait) | optnl−md r=0 | optnl−md r=.17 | optnl−md r=.26 | opt−md r=0 | opt−md r=.26 |
|---|---:|---:|---:|---:|---:|
| control (0/0/0) | 0 | +10 [−121,+141] | −34 [−155,+88] | **−1,689** | **−779** |
| 0.15/0.0/0.15 | 0 | +29 [−115,+173] | −51 [−159,+57] | **−1,993** | **−748** |
| 0.15/0.0/0.45 | 0 | **+93** [+1,+185] | +38 [−53,+129] | **−2,709** | **−1,161** |
| 0.15/0.2/0.15 | 0 | −152 [−401,+97] | **−227** [−421,−33] | **−1,421** | −172 [null] |
| 0.15/0.2/0.45 | 0 | −18 [−202,+167] | −72 [−214,+71] | **−1,925** | **−397** |
| 0.35/0.0/0.15 | 0 | +96 [−45,+236] | −57 [−165,+51] | **−1,953** | **−719** |
| 0.35/0.0/0.45 | 0 | +103 [−5,+211] | +28 [−51,+107] | **−2,616** | **−1,184** |
| 0.35/0.2/0.15 | 0 | −176 [−409,+57] | −172 [−354,+9] | **−1,539** | −166 [null] |
| 0.35/0.2/0.45 | 0 | +7 [−155,+170] | −21 [−147,+106] | **−1,912** | −286 [null] |

**The RETURN-timing half is a WASH (optnl/1).** Exactly ties markdown/1 at r=0;
at r>0 the Δ vs the ladder is a statistical NULL in 16 of 18 (cell × r>0)
combinations — one marginal + (+93 [1,185]) and one − (−227 [−421,−33]), no
consistent sign. And it is **FRAGILE to the drift belief**: a drift sensitivity
sweep (`ANTICIPATED_DRIFT ∈ {1.0, 0.98, 0.96, 0.92}`, 20 seasons) shows its
best case is a *tie* at ≈0.98 (Δ null), while a mis-set drift loses
significantly (drift 1.0: −575 to −755; drift 0.92: −700 to −829 — both
CI-clear-of-zero negative). **The economic reason it can't win: markdown/1's
early-shallow markdown ALREADY minimizes the returns leak** — the same
mechanism the returns section above diagnosed (returns hurt whoever OVERHOLDS
full price; markdown/1 doesn't). There is no refund-vs-resale gap left for an
explicit returns model to capture, so pricing it more elaborately only adds a
fragile drift knob.

**The LEARNED-demand half actively HURTS (opt/1).** opt−markdown is a
significant LOSS in 14 of 18 cells (all r=0, most r>0), never a win; the four
nulls are the high-σ_cal cells at r>0 where the level correction partly offsets
its cost. Isolated at r=0 it is −1,421 to −2,709/season. **Root cause (not a
bug — the learner is unbiased):** across 40 seasons at σ_cal=0 the learned
appeal/true ratio averages 0.97–1.02 per style (sd ≈ 0.08). The damage is that
a single-buy 16-week season yields only ~8% appeal-estimate NOISE, and season
margin is CONCAVE in the estimate — over-estimate → overhold → salvage;
under-estimate → over-discount — so symmetric noise costs margin either way.
The fixed buy-time estimate wins precisely because it injects none. Even at
σ_cal=0.2, where the level correction should pay most, opt/1 at best reaches a
null vs markdown/1 (never a win): the correction and the noise roughly cancel.
(A second, smaller confound: the sell-through signal also conflates
strategic-waiter withholding with low appeal — but the control cell, zero
waiters, still shows the loss, so concavity-on-noise is the primary driver.)

## Q2 — does markdown-beats-cliff survive with the engine's BEST markdown arm? YES.

Because **the engine's best markdown arm IS markdown/1** (neither upgrade beats
it), and markdown/1 beats cliff **significantly in all 27 (cell × r)
combinations**, the headline survives untouched — the control-cell edge is
byte-identical to the existing returns table (r=0: +1,666 [1,382, 1,950], 16%;
r=0.17: +3,211 [2,969, 3,454], 43%; r=0.26: +3,664 [3,400, 3,929], 61%), and it
still GROWS with r. The result was never an artifact of comparing to a weak
fixed ladder: **the fixed engine solve already IS the timeline-optimal answer
on this axis.** Even the two handicapped arms clear cliff — optnl/1 beats cliff
in all 27 combos (it ≈ markdown/1); opt/1, dragged by the learning cost, beats
cliff at every r>0 and merely TIES cliff in several cells at r=0 (the learning
loss ≈ the pure calendar-inefficiency edge markdown wins by).

## Verdict

**Neither ingredient of a "timeline-optimized" markdown beats the fixed
ladder.** Explicit return-timing modeling is a wash (markdown/1 is already
returns-robust by marking down early, so no leak remains to price) and is
fragile to the drift belief; in-season demand learning actively hurts (thin
single-season signal → ~8% estimate noise, and margin is concave in the
estimate). **markdown-beats-cliff SURVIVES decisively** — the engine's best
markdown arm is markdown/1 itself, and it beats cliff in every cell at every
return rate, edge growing with r. This WEAKENS any "a smarter engine does even
better" hope and STRENGTHENS the core reading: markdown/1's early-shallow
markdown is already near the time-axis optimum; the win over the cliff comes
from getting the TIMING right, which the fixed solve already does, not from
out-learning or out-modeling returns.

## Honest qualifications (v4)

1. **The clean r=0 anchor is real:** optnl/1 = markdown/1 byte-for-byte at r=0,
   so the decomposition (learning vs return-timing) is exact, not approximate.
2. **The returns solve's drift is an anticipation, not knowledge**, and the
   verdict is read off the whole {1.0, 0.98, 0.96, 0.92} sweep, never one
   value — its best case is a tie, so no defensible drift rescues it.
3. **The learner is genuinely unbiased** (verified over 40 seasons); this is
   NOT a fixable estimator bug — it is the fundamental cost of estimating a
   level from a thin single-season signal when margin is concave in that level.
   A multi-season learner (appeal carried across seasons, out of P0 scope)
   would have the sample size the single season lacks and is the natural place
   the learned-demand idea could actually pay.
4. **The return rate/lag are handed to the engine as public knowledge.** If it
   had to LEARN them too (few returns early-season), the returns-aware arm
   would be weaker still — so the wash verdict is, if anything, generous to it.

## Files changed / test count (v4)

* `fashion/world.py` — `return_lag_pmf()` (public lag-week curve, derived from
  `sample_return`'s mapping so it can't drift).
* `fashion/policies.py` — `AppealLearner` (cumulative, censoring-aware),
  `OptMarkdownPolicy` (opt/1 + the `learn=False` optnl ablation),
  `ANTICIPATED_DRIFT`, `LEARN_*` knobs with the fragility flagged inline.
* `fashion/run.py` — `opt`/`optnl` arms, `make_policy` (hands the opt arm the
  catalog + return rate), a weekly `observe_week` learner hook (duck-typed, so
  cliff/markdown are untouched), `run_timeline_sweep` (`--timeline-sweep`).
* `fashion/tests/test_fashion.py` — seven v4 tests (lag pmf matches the
  sampler; optnl=markdown at r=0; determinism; opt bounds + monotone;
  discount-only; learner holds-until-evidence + censoring-upward-only + recovers
  an underestimate; returns-aware solve bounded + drift-sensitive). **29 tests
  total, all pass** (~2.5s).
* `fashion/results-v4.json` — the new sweep; `fashion/results.json` untouched.

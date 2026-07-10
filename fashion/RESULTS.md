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

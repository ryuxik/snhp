# BAKESHOP results log — batch perishables, two venues, one world

## Pre-registration (2026-07-10, written BEFORE the grid ran)

**Setup.** One world core (`bakeshop/world.py`), two venue calibrations
(`bakeshop/calibration.py`, NYC 2026): a bakery (croissant $4.75 /
sourdough $9 / cake slice $7.50; morning bake + optional 2pm mini-bake;
items stale at close; the CULTURAL day-old shelf at −50% next morning,
pulled at noon) and a flower shop (bouquet $28 / dozen roses $95 / stems
$4; 3–5 day vase life with age-linear WTP decay; weekly wholesale
delivery; the CULTURAL dump bucket at −70% from day 4). Freshness tiers
multiply WTP (bakery 1.0 / 0.55; flowers remaining-vase-life fraction).
Per-SKU appeal is inverted so the cultural list price IS the
profit-optimal all-day fresh sticker. The bake/order is a gut plan
against the control's calendar (fresh-demand × sellable days ×
mean-one lognormal miscalibration error), identical across arms — the
fashion coupling: the game is "work the inventory the culture bought",
never "buy better". Spoilage at end of life is waste at cost, no salvage.
Arms: `control/1` (the culture, honestly implemented), `computed/1`
(age-aware posted re-pricing, hourly, discount-only off list, aged tiers
offered all day), `nego/1` (per-arrival Nash bundles over item ×
freshness tier × quantity × price rungs; event-consistent disagreement
including the control's own day-old shelf/dump bucket as the buyer's
alternative; buffer max($0.25, 10% of bundle list)). Decomposition arms:
`computed-agedonly/1` (only aged tiers re-priced), `nego-nopairs/1`
(bundle channel removed). Grid: miscalibration σ ∈ {0.15, 0.35} ×
spike frequency ∈ {0.0, 0.1}, 30 paired days/cell, seed 20260710,
5-day-block paired CIs. PURE MATH, no LLM anywhere.

**H-B1 (the fashion-cliff result at day scale).** `computed/1` beats the
fixed day-old/dump calendar on profit in every cell (CI clear of zero),
and the mechanism is moving MORE aging stock while fresh demand is still
present — not squeezing fresh prices. Concretely: (a) computed's
`aged_units`/day exceeds control's in the bakery cells and its
`waste_cost` is lower in all cells; (b) `computed-agedonly/1` captures
the majority (>60%) of computed's profit edge over control. Falsifier:
computed ≤ control anywhere, or the aged-only ablation captures little of
the edge (the win would then be fresh-price discrimination, a different
claim).

**H-B2 (bundles, not deeper discounts).** `nego/1`'s extra edge over
`computed/1` concentrates in multi-item bundles (cake+croissant pairs,
bouquet up-sizing), not in deeper discounting: (a) removing pairs
(`nego-nopairs/1`) erases ≥50% of the (nego − computed) profit delta in
the bakery cells; (b) nego's realized discount depth (1 − revenue /
list_value_sold) is NOT deeper than computed's in any cell. Falsifier:
nego-nopairs ≈ nego (the edge would be per-person price discrimination,
not bundling), or nego wins mainly by discounting deeper.

**H-B3 (the scarcity result).** On event-spike days at the florist
(×6 demand vs ×2-capped supply — Valentine's physics), all arms converge:
sellout leaves nothing to negotiate. Concretely: the spike-day paired
profit deltas (all arms vs control) shrink toward zero — point estimates
under ~5% of the control's spike-day profit — while calm-day deltas in
the same cells stay large; spike-day waste ≈ 0 for every arm. Falsifier:
nego or computed keeps a material spike-day edge (scarcity pricing would
then matter even at sellout, contradicting the "nothing to negotiate"
story).

**Known biases, declared up front:** the dynamic arms' demand forecast is
the true structural process (favorable to them, as in vend/boba); the
control cannot react to the public event calendar (that IS the cultural
practice being tested); weekly flower delivery + age-linear decay makes
the florist's mid-week structurally hard for every arm — paired diffs are
the defense; buyers disclose truthfully to the Nash engine (vend-P1
attestation assumed; the liar tax is measured elsewhere).

Reproduce: `python3 -m bakeshop.run --grid --days 30 --seed 20260710`
(writes `bakeshop/results.json`).

*Results below this line were appended AFTER the grid ran.*

---

## Results (2026-07-10) — 30 paired days/cell, seed 20260710

*Reproduce: `python3 -m bakeshop.run --grid --days 30 --seed 20260710`
(writes `bakeshop/results.json`; `test_committed_results_stay_reproducible`
pins it). CIs are 95% t on 5-day block means.*

### Headline: profit Δ/day vs control (paired)

**Bakery** (control earns ≈ $1,035–1,104/day calm):

| cell (σ_miscal / spike) | computed/1 | nego/1 | computed-agedonly/1 |
|---|---|---|---|
| 0.15 / 0.0 | **+74.0** [40.6, 107.5] | **+166.2** [131.4, 201.0] | **−29.2** [−50.3, −8.1] |
| 0.15 / 0.1 | **+65.3** [32.9, 97.7] | **+160.2** [121.0, 199.5] | −18.2 [−32.9, −3.4] |
| 0.35 / 0.0 | **+56.7** [15.5, 97.9] | **+149.4** [99.2, 199.5] | −39.0 [−93.4, 15.3] |
| 0.35 / 0.1 | **+60.1** [19.8, 100.4] | **+150.7** [97.1, 204.2] | −26.5 [−68.2, 15.2] |

**Flowers** (control earns ≈ **−$26…−36/day** in calm cells — see
surprises):

| cell (σ_miscal / spike) | computed/1 | nego/1 | computed-agedonly/1 |
|---|---|---|---|
| 0.15 / 0.0 | **+201.6** [102.7, 300.6] | **+182.0** [78.7, 285.3] | **+214.2** [110.3, 318.0] |
| 0.15 / 0.1 | **+158.0** [37.2, 278.9] | +118.5 [−3.5, 240.5] | **+172.1** [40.5, 303.8] |
| 0.35 / 0.0 | **+184.2** [65.3, 303.2] | **+169.3** [47.5, 291.1] | **+187.1** [68.6, 305.6] |
| 0.35 / 0.1 | **+142.4** [1.8, 283.0] | +112.8 [−37.5, 263.1] | **+149.4** [8.1, 290.6] |

Consumer surplus is ALSO higher than control for every dynamic arm in
every cell (bakery +100…+325/day, flowers +114…+208/day) — the cultural
calendars destroy value on both sides of the counter, mostly through
waste-at-cost (bakery $80–106/day → ≈$0–7; flowers $92–150/day → ≈$1–7).

### H-B1 — profit claim CONFIRMED; the pre-registered mechanism is
### venue-split, and the bakery half FAILED informatively

The profit claim holds: computed/1 beats the cultural calendar in all 8
cells, no CI touching zero. But the *mechanism* I pre-registered — "moving
MORE aging stock while fresh demand is present" — is only true at the
florist:

| mechanism metric (cal0.15/0.0) | bakery ctrl → comp | flowers ctrl → comp |
|---|---|---|
| aged units sold /day | 29.1 → **14.5** (−50%!) | 1.5 → **10.9** (×7) |
| waste $/day | 80.3 → 3.1 | 149.9 → 6.6 |
| aged-only ablation captures | **−39% of the edge** | **106% of the edge** |

* **Flowers: confirmed as registered.** `computed-agedonly` captures the
  whole edge (it even beats full computed slightly — fresh re-pricing adds
  nothing on a board that is mid-week mostly aged). The dump-day calendar
  is fashion's cliff at day scale, and age-aware re-pricing is worth
  ≈ $150–215/day to a shop whose control arm loses money.
* **Bakery: the letter FAILED.** Computed sells *half* the day-old units
  control does, because its real move is clearing the overbake glut as
  discounted FRESH stock the same afternoon — stock never gets old. This
  is exactly fashion's "earlier, shallower markdowns" arriving a tier
  early; the pre-registration guessed the wrong tier.
* **The aged-only ablation actively LOSES at the bakery** (−$18…39/day)
  while moving 3× the day-old units — selling engine-priced day-old all
  day next to full-price fresh diverts fresh margin (the vend-P0
  cannibalization externality, replicated). **The culture's noon pull of
  the day-old shelf is vindicated as rational cannibalization control,**
  not superstition. An age-aware engine must re-price the whole board or
  it is worse than the folk rule it replaces.

### H-B2 — direction confirmed, magnitude FAILED (bakery); nego loses to
### computed outright at the florist

nego/1 beats computed/1 by +$90–95/day at the bakery (CIs clear of zero).
Decomposition against the pre-registered ≥50% bundle share:

| cell | nego − computed | bundle share (nego − nopairs) |
|---|---|---|
| 0.15/0.0 | +92.1 [83.8, 100.5] | +39.9 [26.5, 53.3] → **43%** |
| 0.15/0.1 | +95.0 | +33.7 → 35% |
| 0.35/0.0 | +92.6 | +28.3 → 31% |
| 0.35/0.1 | +90.5 | +32.6 → 36% |

* Bundles are real and CI-solid (cake+croissant pairs: 557–654 per 30
  days) but carry only **31–43%** of the extra edge — below the
  registered 50%. The bigger share is single-line per-person Nash deals:
  quantity up-sizing and sub-list conversion of buyers the posted board
  refuses. H-B2(a) FAILS as registered.
* H-B2(b) HOLDS at the bakery: nego's realized depth is *shallower* than
  computed's in every bakery cell (0.15–0.20 vs 0.17–0.22) while earning
  more — the edge is targeting, not deeper cuts. Depth-check fails at the
  florist (0.43 vs 0.39), where nego is not ahead anyway:
* **Florist reversal (unregistered):** nego trails computed in all four
  flower cells (−15…−40/day; one CI fully negative, three straddle). When
  the whole store is a markdown problem, a posted age-aware board beats
  per-arrival bargaining: the Nash split hands ~half the recovered value
  to buyers (CS −46…−62/day vs computed) and the min-gain buffer blocks
  small rescues a posted price collects automatically.

### H-B3 — CONFIRMED at the bakery, FALSIFIED at the florist (and the
### falsification is the best finding in the grid)

Spike-day paired profit deltas (5 spike days, cal0.15/0.1; day levels:
bakery control ≈ $2,879/spike-day, flowers ≈ $1,745):

| Δ/spike-day vs control | bakery | flowers |
|---|---|---|
| computed | **+2.6 (+0.1%)** | **+349 (+20%)** |
| nego | +103 (+3.6%) | +187 (+11%) |
| (calm-day deltas, same cell) | +78 / +172 | +120 / +105 |

* **Bakery: converged as registered.** The oven-capped bake sells out at
  list in every arm; computed's edge collapses to +0.1% (under the 5%
  threshold), nego keeps only its bundle margin (+3.6%). Sellout leaves
  nothing to re-price — the scarcity result, on schedule.
* **Flowers: anti-converged.** Sellout does hold on the FRESH tier
  (spike-day waste: control $144, dynamic arms $0) — but the ×6 crowd
  also meets the week's AGED leftovers, which the control still prices at
  full (or waits until day 4 to dump). The event *amplifies* the
  mispricing: computed's spike-day edge (+$349) exceeds its calm edge.
  Pre-registration missed that a florist's spike day is fought with a
  mixed-age board, not just the morning truck.
* **Negotiating into a demand flood is strictly worse than posting:**
  nego − computed on flower spike days = **−$123…−162/day** (vs −11…−15
  calm). At ×6 demand the posted board rations scarce stock to the
  highest payers at full margin; the Nash engine keeps splitting surplus
  it no longer needs to concede. Scarcity doesn't just leave "nothing to
  negotiate" — it makes negotiation a losing move. This sharpens the
  arena's scarcity result with a dollar sign on it.

### Honest surprises

1. **The noon pull is folk wisdom that survives the engine** (H-B1,
   bakery): naive age-aware discounting of the day-old shelf, alone, is
   worse than the culture. The finding generalizes: partial dynamic
   pricing on a multi-tier board can be worse than none.
2. **The control flower shop loses money in calm cells** (−$26…−36/day). Weekly delivery + age-linear WTP decay + the day-4 dump is a
   structurally unprofitable combination; the culture survives in reality
   on event days (spike cells put control at +$316/day) and on gentler
   effective decay than this world's. Treat the flowers MAGNITUDES as
   upper bounds on the pricing fix; the direction is robust (paired).
3. **Computed's biggest bakery lever is the overbake, not the shelf**:
   the "full shelves sell bread" ×1.15 gut plan hands every arm a daily
   glut; computed clears it same-day at −15…−25% while control ships it
   to tomorrow's −50% shelf and the bin ($80/day of waste → $3).
4. **nego takes surplus from consumers relative to computed at the
   bakery** (CS −165…−171/day vs computed, though still +100…156 vs
   control): person-level Nash pricing converts posted-discount giveaways
   into margin. The "created surplus is split" story holds vs control,
   not vs every alternative mechanism.

### Caveats (attack these first)

* **The gut plan is the arms' shared inheritance.** Overbake ×1.15 and
  the aging-blind weekly flower order create the glut the dynamic arms
  monetize — exactly fashion's "clearance volume is in the plan". A plan
  built to the ENGINE's calendar would shrink every edge here; that arm
  (buy-to-engine) is the natural P1.
* **Flowers decay is harsh and delivery weekly** (prompt-fixed): mid-week
  the whole store is aged inventory, which is where computed's +$150–200
  and control's losses both live. Real florists get 2–3 drops/week and
  softer perceived aging; magnitudes would compress.
* **Truthful disclosure to the Nash engine** (vend-P1 attestation
  assumed); the sub-list conversion component is what liars would attack.
* **Dynamic arms' demand model = the true structural process** (favorable
  to them, as in vend/boba — flagged in results.json notes); no learner,
  no day-shock inference anywhere.
* **Cell-separable forecasts across SKUs**: cross-SKU diversion is priced
  by nobody (within-SKU tiers ARE residual-priced — without that fix,
  computed prices day-old above fresh clearing prices, a bug wearing a
  markdown). The computed-agedonly bakery loss shows what the remaining
  blindness costs.
* Spike-day splits rest on 5 event days per cell (point estimates, no
  CI); consumer surplus is booked only on purchases; no returns/patience;
  no reference-price/regulars fairness model (vend `regulars.py` is the
  template).

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

---

## CRITICAL-ANALYSIS §9 fix (2026-07-10): floral shrink recalibration +
## regime/1 (pre-registered regime-switching arm)

*CALIBRATION-TARGETS #9 + CRITICAL-ANALYSIS §9. bakeshop_version bumped
1 → 2. Reproduce: `python3 -m bakeshop.run --grid --days 30
--seed 20260710 --arms control,computed,computed-agedonly,nego,
nego-nopairs,regime` (writes `bakeshop/results.json`).*

### Part 1 — shrink recalibration

**What changed** (`bakeshop/calibration.py`, `bakeshop/world.py`):

1. **Relabel.** The old single "3/4/5-day" florist life field conflated
   two real numbers. It is now split: `display_days` (retail display
   life — the OLD 3/4/5 numbers, verbatim, just correctly named) and
   `life` (vase life with care, IFPA/floral-trade band 5–14 days) —
   bouquet 4→7, dozen-roses 5→9, stems 3→6.
2. **Quality-tiered markdown ladder**, not a hard day-4 cliff: full price
   through `display_days`, then a THREE-step graduated ladder
   (`FLOWER_MARKDOWN_STEPS = (0.75, 0.50, 0.30)`) spread across the rest
   of vase life, bottoming out at the old dump depth on the last sellable
   days (`world.markdown_ladder`). `fresh_mults` (the true WTP decay) keep
   the same age-linear formula, just spread over the longer life.
3. **Receiving loss** (`FLOWER_RECEIVING_LOSS = 0.15`): a
   Binomial(qty, 0.15) share of every wholesale delivery is culled as
   damaged/unsellable in `begin_day`, BEFORE any policy sees the stock —
   a pricing-independent shrink floor (transit/receiving damage is a real,
   separately-documented floral-shrink category, distinct from markdown
   failure). Booked through new `ShopState.pending_waste_*` fields,
   flushed into the day's waste totals at `end_of_day`. Paired across arms
   by construction (same `begin_day` call, same seed).
4. **Legacy cell kept, labeled**: `get_venue("flowers-legacy")` reproduces
   the pre-fix calibration exactly (old 3/4/5-day cutoff, flat day-4
   cliff, zero receiving loss) for anyone who wants the old numbers —
   not wired into the grid CLI, not the headline.

**Realized dollar shrink, the target metric** (waste $ ÷ (revenue +
waste $), the age-aware POSTED arm — CALIBRATION-TARGETS #9's actual
ask): **9.5% pooled across the 4-cell grid** (calm cells 10.7–10.8%,
spike cells 8.4–8.8% — floods sell through more, so relative shrink runs
a bit lower there, which is the expected direction). Before this fix,
`computed/1`'s realized shrink was ~1–2% (an omniscient-demand pricer
with zero receiving loss can clear almost everything given enough
calendar days and no price floor) — nowhere near IFPA's ~9% floral
benchmark. `control/1`'s shrink stays far worse (46–48% calm, 21–23%
spike) — expected, and already flagged elsewhere in this doc as an
upper-bound/non-viable-business artifact of the control's blind
calendar, not something Part 1 targets. New test:
`test_computed_realized_dollar_shrink_lands_in_the_ifpa_band` pins the
9–12% band at both grid miscalibration levels.

**How the computed-vs-nego gap moved — measured, not assumed:**

| cell (σ_miscal/spike) | OLD nego − computed | NEW nego − computed (95% CI) |
|---|---|---|
| 0.15 / 0.0 | −19.6 | **−73.58** [−112.92, −34.25] |
| 0.15 / 0.1 | −39.5 | −112.47 [−280.13, 55.19] |
| 0.35 / 0.0 | −14.9 | **−52.13** [−96.25, −8.01] |
| 0.35 / 0.1 | −29.6 | −79.28 [−193.28, 34.71] |

The pre-fix doc read this as "nego trails computed in all four flower
cells (−15…−40/day; one CI fully negative, three straddle)." Realistic
shrink did **not** shrink the posted arm's edge — it **more than
doubled it** and made it significant in twice as many cells (2/4 CI
clear of zero now vs 1/4 before). Mechanism: `nego/1`'s opportunity cost
of every unit is its `calendar_recovery` against the CONTROL price path
(`policies.calendar_phases`) — and the control's price path is now a
graduated 3-step ladder that holds value longer, not an early 70%-off
cliff. That raises nego's own disagreement-point floor, so its buffer
(`max($0.25, 10% of bundle list)`) bites harder and fewer/shallower deals
clear it. `computed/1` has no such reference — it re-solves its own
profit-max price against the true demand model every hour, unconstrained
by the culture's price path, and the now-longer vase life gives it more
days of runway to extract value from aging tiers. **Honest
qualification, pre-registered as a caveat before this section was
written:** this is exactly the "less forced clearance" mechanism the
task asked me to check for — it moved the OPPOSITE direction from the
naive guess. Falsifier that would have supported the naive guess (gap
shrinks) did not fire.

### Part 2 — regime/1: pre-registration
*(written BEFORE the grid below ran)*

CRITICAL-ANALYSIS §9(a): "the broker should detect flood/clearance
regimes (learned arrival pressure vs stock) and fall back to its own
posted-markdown mode... pre-registered prediction: a regime-switching arm
weakly dominates both [pure arms] at the florist."

**Implementation** (`bakeshop/policies.py`): `RegimePolicy` calls
`detect_regime` every board/quote request. The detector uses ONLY state a
real shopkeeper has — no `is_spike_day`, no hidden day-shock multiplier:
`flood_pressure` = realized arrivals-so-far today ÷ the shop's own
seasonal calendar expectation for the same elapsed ticks (Bayesian-shrunk
toward 1.0, prior count 2); `clearance_pressure` = (a) current stock ÷
(days to next resupply × the shop's own base-plan sell-through) OR (b)
the share of current stock sitting in a WTP-degraded tier ≥ 45%. Flood
(≥1.8×) or clearance → delegate to `ComputedPolicy`'s board, `quote_for`
returns `None` (no bilateral, no buffer, exactly as specified). Otherwise
→ delegate to `NegoPolicy` exactly. Falsifier: regime/1 loses to either
pure arm with a CI clear of zero anywhere in the florist grid.

Isolated mechanism checks (now tests, all green): `flood_pressure`
separates a synthetic ×6 spike day from a calm day by >2× at every tick
checked (day 3, ticks 2/4/8/14, same seed); once a regime is flagged, the
policy's board and quote behavior are IDENTICAL to `computed/1` (a
mechanism pin, not a statistical claim). Also re-run at the BAKERY as the
pre-registered spillover check (delivery_every=1 means the
resupply-cycle clearance signal is 0 by construction there — the
prediction was "unchanged/slightly better").

### Part 2 — POST-REGISTRATION OUTCOME (2026-07-10): **prediction
### REFUTED at the florist.** Bakery spillover: not measurably harmful.

**Florist** — regime/1 does NOT weakly dominate both pure arms:

| cell (σ_miscal/spike) | regime − computed (95% CI) | regime − nego (95% CI) |
|---|---|---|
| 0.15 / 0.0 | **−72.40** [−113.36, −31.43] | +1.19 [−23.14, 25.52] |
| 0.15 / 0.1 | **−51.98** [−95.06, −8.89] | +60.49 [−81.44, 202.43] |
| 0.35 / 0.0 | −40.36 [−89.48, 8.76] | +11.77 [−9.52, 33.06] |
| 0.35 / 0.1 | −33.60 [−88.21, 21.00] | +45.68 [−26.81, 118.17] |

Against `computed/1`: negative in all 4 cells, CI clear of zero in 2/4 —
regime/1 never beats computed, and sometimes loses to it significantly.
Against `nego/1`: positive point estimate in all 4 cells but **CI
includes zero in every cell** — per the rigor rule, this is not a win
claim. Verdict: **REFUTED** (fails the "dominates computed" leg outright;
the "dominates nego" leg is unproven, not supported).

**Why, mechanistically — detection latency is a real, measured cost.**
On the grid's actual V-Day-like spike days (`spike_split`, point
estimates, 3–5 event days/cell, no CI — same caveat as H-B3 above),
ranked vs control: `computed` +6.0 / −63.3 per spike-day, `regime` **−86.4
/ −167.8**, `nego` −425.3 / −351.5. regime/1 recovers ~75–80% of nego's
catastrophic flood losses (confirming the mechanism *works* — it does
correctly lean away from bilateral bargaining during a flood, and the
mechanism-pin tests confirm it reproduces computed's board exactly once
flagged) but does NOT reach computed's near-flat spike-day result, and in
both tested spike cells regime/1 is worse than doing NOTHING (control) on
the spike day itself. The gap is detection lag: `flood_pressure` needs a
few elapsed ticks of same-day signal (the Bayesian prior deliberately
resists over-reacting to one early arrival) before it clears the 1.8×
threshold, and the FIRST arrivals of a real flood — exactly the moment
H-B3 says bilateral bargaining is most expensive — still land in
`hetero`/nego mode while the detector is still deciding. A hard,
structural cost of refusing the oracle.

**Second driver, orthogonal to detection lag:** even away from floods,
`detect_regime` classifies ~31% of florist transactions as `hetero` in a
calm 30-day run (clearance ~63%, flood ~6%, measured directly). After the
Part 1 shrink recalibration, `computed/1` beats `nego/1` in **every**
florist cell — there is no surviving buyer-heterogeneity pocket at this
venue for the `hetero` branch to protect. So every tick spent in
`hetero` mode is now a pure diversion from a uniformly-better strategy,
not a genuine trade-off; sanity check confirms the mechanism CAN reach
computed's exact total (setting the aged-fraction threshold to always
fire clearance reproduces `computed/1`'s totals to the cent) — the
shortfall is entirely about an honest detector not knowing when it's
safe to leave `hetero` mode, not a wiring bug.

**Bakery spillover — not trigger-happy, but not "slightly better"
either.** Calm cells: regime/1 is **byte-identical** to `nego/1`
(regime_vs_nego mean 0.0, CI [0.0, 0.0] — pinned by
`test_regime_bakery_calm_cells_are_byte_identical_to_nego`), because
`clearance_pressure`'s resupply-cycle term is 0 by construction
(delivery_every=1) and ordinary bakery demand variance never crosses the
flood ratio. Spike cells: point estimate is slightly negative (−$15.45,
−$16.07/day) but **CI includes zero in both** ([−37.96, 7.07],
[−40.58, 8.43]) — not a statistically measurable degradation. The
spike-day-only breakdown (point estimate, no CI) shows a larger gap
(−$85–87/day on the actual spike days, diluted to non-significance over
27 calm + 3 spike days): on a bakery flood, nego's bundle/targeting edge
(H-B2) is real and regime/1 gives some of it up by flipping to
computed-like pricing, which is nearly flat on bakery spike days (H-B3).
Read plainly: the detector is not "trigger-happy" in the sense of
damaging ordinary bakery operation (the pre-registration's main
concern), but it is not free either — the honest spillover verdict is
**"unchanged in calm conditions, a small unproven-but-plausible cost on
flood days,"** short of the pre-registered "unchanged/slightly better."

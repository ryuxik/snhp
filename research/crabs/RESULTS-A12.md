# RESULTS — AMENDMENT 12

*2026-07-25. Filed in its own file: `RESULTS.md`, `PREREG.md`, `TRIAGE.md`,
`RESULTS-A11.md` and `PREREG-A11.md` belong to workers who have finished, and
are not rewritten here. Job 2's pre-registration is `PREREG-A12.md`, complete
before any Job 2 code existed. Job 1 is forensic and carries no kill condition:
it settles which of two published numbers means what it was taken to mean.*

Reproduce:

```
python3 research/crabs/run_a12.py j1      # the two vacancy reports
python3 research/crabs/run_a12.py j1wa    # A10's walk-away cross, in MONTHS
python3 research/crabs/run_a12.py j2      # the match_sd grid, K33 and K34
python3 research/crabs/run_a12.py j2k35   # what a 5% discount buys
python3 research/crabs/run_a12.py j2m     # the market channel
python3 research/crabs/run_a12.py j2hunt  # the Principle E hunt
python3 -m pytest research/crabs/test_crabs.py -q     # 131 tests
```

---

# JOB 1 — the two vacancy reports

## 1.0 The answer, unqualified

**Both reports are arithmetically correct and neither is a vacancy measurement.**

- AMENDMENT 11's **0.0000** is `vacant_years / habitat_years`. `vacant_years` is
  incremented inside the RENEWAL block, which runs **once a year at the annual
  boundary — after twelve months of matching and before that year's leavers
  empty their habitats.** It therefore counts habitats that failed to let for a
  *full twelve-month matching cycle*. There are none, in 100,000 habitat-years.
  It is not a near-dead counter in A11's sense — the supply-shock cell reaches
  2.14% — but the only thing it can ever find is habitats added faster than a
  whole year of searcher flow can absorb.
- AMENDMENT 10's **4.376** is `vacant_months / n_newlet_signed`, a real duration
  measured on the monthly matching loop. It reproduces exactly (4.3766 on A10's
  ten seeds, 4.371 on thirty).

There is no censoring and no unclosed spell: `open_at_year_end` is **0** in every
year, every habitat listed in a year lets inside that year. That is *why* the
stock reads zero. One statistic is a stock sampled at the single instant of the
year when the stock is guaranteed to be empty; the other is a flow duration. The
matching measure nobody had computed is the flow vacancy rate,
`vacant_months / (12 × habitat_years)` = **12.90%**, and days-on-market at
signature (the exclusive convention) is **3.371 months**.

**And the 4.376 is not a time-to-let.** It is queue-drain time, and the queue is
an artefact of the model's calendar. **Every lease in this world expires on the
same day.** The renewal block empties every leaver's habitat at month 0, while
the leavers themselves enter the search pool at `int(u[9] × 12)`, a uniform month
whose mean is **5.525**. Supply arrives in one lump; demand trickles in behind
it for a year.

Per station-year, baseline, 30 seeds:

| month | listings on market | searchers in pool | lets |
|---|---|---|---|
| 0 | 8.8 | 1.2 | 1.2 |
| 1 | 7.7 | 1.2 | 1.2 |
| 2 | 6.5 | 1.2 | 1.2 |
| 3 | 5.3 | 1.2 | 1.2 |
| 4 | 4.2 | 1.2 | 1.2 |
| 5 | 3.0 | 1.2 | 1.2 |
| 6 | 1.9 | 1.2 | 0.9 |
| 7 | 0.9 | 1.4 | 0.6 |
| 8 | 0.3 | 1.7 | 0.3 |
| 9 | 0.0 | 2.3 | 0.0 |
| 10 | 0.0 | 2.9 | 0.0 |
| 11 | 0.0 | 3.3 | 0.0 |

Lets equal arrivals exactly for six months: the market is not matching, it is
draining a queue at the rate searchers walk in. Then the listings run out and the
pool piles up unmatched (9,993 searcher-years give up per 100,000 habitat-years).

## 1.1 The one-knob ablation

`MarketParams.stagger_expiry` (new, default **OFF**, so every previously reported
cell is bit-identical) empties the habitat in the same month its tenant starts
searching. It reuses the tenant's own `u[9]` draw, so it adds no parameter and no
randomness — one knob, per DESIGN-PRINCIPLES A.

| cell | stock vac | flow vac | let months | dom at signing | market rent | retention |
|---|---|---|---|---|---|---|
| **baseline** | 0.0000 | 0.1289 | **4.371** | 3.371 | $627 | 0.6462 |
| **stagger_expiry** | 0.0000 | **0.0297** | **1.000** | **0.000** | **$1,668** | 0.6441 |
| supply_shock | 0.0214 | 0.1399 | 4.522 | 3.522 | $610 | 0.6425 |
| supply_shock + stagger | 0.0370 | 0.0553 | 1.819 | 0.819 | $1,516 | 0.6434 |

**The synchronised expiry accounts for 100% of the measured days-on-market.**
With it removed, every habitat lets in the month it is listed (`let_months` 1.000
is the inclusive convention; elapsed days-on-market is 0.000). Whatever the model
knows about letting frictions, it is not 4.4 months and it is not 1.15 either —
it is *nothing*, and `BASE_LET_MONTHS = 1.15` remains the only number in the file
with a source outside the model.

**The same knob is most of the deflation.** Mean market rent by year, averaged
over seeds (burn-in then measurement):

| | y0 | y3 | y6 | y9 | y12 | y15 |
|---|---|---|---|---|---|---|
| baseline | 2000 | 1386 | 973 | 695 | 507 | 381 |
| stagger | 2000 | 1895 | 1801 | 1712 | 1629 | 1553 |

The decay rate falls from **11.6%/yr to 1.8%/yr**. RESULTS Phase 5 §5 reports the
deflation as an unfixed structural defect and argues it "is not a tuning
problem". That is right, and now it has a name: it is not a tuning problem, it is
a **timing** problem. The permanent January glut keeps tightness low all year, a
slack market makes `expected_wait_months` large, a large expected wait collapses
the landlord's reservation, and low signed rents feed back into `M_obs`.

## 1.2 AMENDMENT 10's stated reason for distrusting the derived vacancy is backwards

A10 filed the derived 4.376 as "endogenous but **contaminated** by the unfixed
deflation defect … so an upper bound on the landlord's exposure." The causality
runs the other way, and it is checkable two ways:

1. *Within* a run, as the market deflates the time-to-let **falls**: year 0
   ($868) 5.201 months → year 9 ($350) 3.559 months. Lower rents pull in more
   searchers through `searcher_inflow_at`, which drains the queue faster.
2. Across the declared `eta_demand` sweep the same ordering holds, because eta is
   what governs how hard entry responds:

| eta_demand | let months | flow vacancy | market rent |
|---|---|---|---|
| 0.0 | 6.206 | 0.1836 | $579 |
| 0.5 | 5.326 | 0.1572 | $600 |
| **1.0** (shipped) | **4.371** | 0.1289 | $627 |
| 1.5 | 3.534 | 0.1044 | $669 |
| 2.0 | 2.900 | 0.0857 | $719 |

Deflation does not inflate the derived vacancy. The queue does, and the
deflation is its sibling, not its cause. **The `derived` denominator should be
withdrawn rather than reported as a bound.**

## 1.3 THE PUBLICATION BLOCKER — the landlord's cost of losing a tenant

`RESULTS.md` (AMENDMENT 9/10 section) currently says:

> The model's landlord walk-away runs **$2,094–$3,440**, inside the published
> $2,000–$4,000. The derived tenant switching cost is **$2,960**. … **both sides
> are low four figures.**

**The landlord figure is wrong, and it moves by a factor of about three.** Three
independent defects, in decreasing order of importance.

**(a) The two sides are denominated in different rents.** `wa_land_renew` is
built inside the simulation as `(turn_cost + vacancy) × M_obs (+ relet risk + the
A6a clock)`, and `M_obs` is the model's **endogenous** market rent, which has
deflated to **$627.30/month** in the cells that produced $2,094–$3,440. The
tenant's $2,960 is `results_amend8.json`'s `dollars_median` — 1.48 months ×
`ANCHOR_RENT` = **$2,000/month**. The sentence compares 3.3 months of a $627 rent
with 1.48 months of a $2,000 rent. The denominators are **3.19× apart**.

**(b) The two sides are different objects.** $2,094–$3,440 is a full landlord
*walk-away*. $2,960 is the tenant's *switching cost*, not its walk-away — the
tenant's walk-away in the very same cells is $2,507 (on A8-derived costs) or
$5,077 (on the shipped `move_med = 3.6`).

**(c) The upper end is out of A10's own declared band.** $3,440 is the cell at
`MOVE_PHYSICAL = 3.1` — a $6,200 physical move — and PREREG A10.2 declared the
band $700–$3,300. Inside the band the same column runs $2,094 to $3,006. (It is
not a random point: `move_med = 0.48 + 3.1 = 3.58` is the shipped calibrated 3.6,
so the quoted maximum is the shipped model wearing a swept label.)

### The corrected numbers

Everything in **months of market rent** — the model's own scale-free unit, and
the only one that can be compared with anything. The *ratio* A10 reported is
unaffected, because both sides share `M_obs`; the dollars are not.

| | months of market rent | at $2,000/mo | at the model's $627/mo |
|---|---|---|---|
| landlord walk-away — upstream vacancy 1.15, relet risk off | 2.909 | **$5,818** | $1,825 |
| landlord walk-away — fitted vacancy 1.5, relet risk off | 3.338 | **$6,675** | $2,094 |
| landlord walk-away — upstream 1.15, relet risk on | 4.208 | **$8,416** | $2,639 |
| landlord walk-away — fitted 1.5, relet risk on | 4.482 | **$8,964** | $2,811 |
| landlord walk-away — shipped `move_med` 3.6, relet on | 5.492 | **$10,985** | $3,444 |
| landlord walk-away — shipped, timing artefact removed | 4.591 | **$9,183** | $7,661 |
| tenant walk-away — A8-derived costs | 3.997 | $7,993 | $2,507 |
| tenant walk-away — shipped `move_med` 3.6 | 8.096 | $16,192 | $5,077 |
| *tenant switching cost alone* (A8 median) | 1.48 | $2,960 | $928 |
| *landlord make-ready alone* (`turn_cost`) | 1.50 | $3,000 | $941 |

**The corrected landlord figure is 2.9 to 5.5 months of market rent — about
$5,800 to $11,000 at a $2,000 rent.** Not $2,094–$3,440.

### What survives, plainly

- **"Both sides are low four figures" does NOT survive.** At any single
  denominator both sides are high four figures or five figures. The sentence is
  true only of a comparison that reads the landlord off a $627 rent and the
  tenant off a $2,000 one. **It must come out of the article.**
- **"Inside the published $2,000–$4,000" does not survive either.** That
  agreement with Zego's $3,872/turn was an accident of the deflation. At a
  realistic rent the model's landlord walk-away sits *above* the published range,
  not inside it — which is a fact about the model, not about landlords, and
  should be said as such.
- **The claim the sentence exists to carry DOES survive, and gets stronger.**
  "The landlord risks far more than the tenant" rests on the *ratio*, which is
  unit-free and unchanged: 0.75–1.46 across the swept physical-move band on
  A8-derived costs, **1.474** in the shipped configuration, **1.766** with the
  timing artefact removed. The tenant is never dwarfed and is usually the more
  exposed party. Nothing in Job 1 touches that.
- **There is a replacement sentence that is true at one denominator and sharper
  than the one it replaces**: the tenant's own derived moving cost is **1.48
  months of rent** and the landlord's make-ready is **1.50 months**. On the
  physical, administrative cost of the turnover the two sides are a **dead
  heat** — $2,960 against $3,000 at a $2,000 rent. What differs is what sits on
  top: the landlord adds vacancy and re-let rent risk, the tenant adds
  attachment, search and the deadline. Those roughly cancel, which is the actual
  finding.
- The caveat A10 added is untouched and still the important one: the same dollars
  are a per-unit business expense set against a portfolio for one party and a
  household budget shock for the other.

### K30 and K20

**K30's verdict is unchanged and its evidence gets cleaner.** Withdrawing the
`derived` denominator removes the two combinations that never crossed:

| vacancy | RELET_RISK_ON | ratio at central | crossing | in band $700–$3,300 |
|---|---|---|---|---|
| fitted 1.5 | True | 0.892 | $3,110 | **yes** |
| fitted 1.5 | False | 1.197 | $1,028 | **yes** |
| upstream 1.15 | True | 0.950 | $2,481 | **yes** |
| upstream 1.15 | False | 1.374 | $396 | no |
| ~~derived 4.376~~ | ~~True~~ | ~~0.577~~ | ~~never~~ | ~~withdrawn~~ |
| ~~derived 4.376~~ | ~~False~~ | ~~0.583~~ | ~~never~~ | ~~withdrawn~~ |

**K30 still FIRES: 3 of 4 defensible combinations cross inside the declared
band.** The span at the central estimate narrows from RESULTS.md's *"0.52 to
1.37"* to **0.89 to 1.37**, and the sign still flips on `RELET_RISK_ON`, which is
the finding. K20's shipped 1.474× is unaffected — it is a ratio.

The defensible range for `Params.vacancy` is now **1.0–1.15 months**
(`BASE_LET_MONTHS`, upstream, 30–41 day let times). Not 1.2/1.8 (fitted,
CIRCULAR) and not 4.376.

## 1.4 What Job 1 changes in the record

| claim | where | change |
|---|---|---|
| landlord walk-away "$2,094–$3,440" | RESULTS.md A9/10 | **wrong units**; 2.9–5.5 months = $5,800–$11,000 at $2,000 |
| "inside the published $2,000–$4,000" | RESULTS.md A9/10 | **withdrawn** — an artefact of the deflation |
| "both sides are low four figures" | RESULTS.md A9/10, article | **withdrawn** |
| "the landlord risks far more" is dead | RESULTS.md A9/10, article | **holds**, on the unit-free ratio |
| derived vacancy 4.376 as an upper bound | RESULTS.md A9/10 | **withdrawn**; it is queue-drain time and its stated contamination runs the wrong way |
| K30 FIRED | RESULTS.md, PREREG A10.4 | **holds**, 3/4 instead of 3/6 |
| baseline vacancy 0.0000 is a defect | RESULTS-A11 §8.3 | **it is a definition**, not a bug — the counter is a stock at an annual instant |
| the deflation "is not a tuning problem" | RESULTS Phase 5 §5 | **holds, and is now diagnosed**: 85% of it is synchronised lease expiry |
| `mean_ask` is NaN because the ask block is dead | market.py docstring | **holds**, same root cause: `vacant_years == 0` |

Nothing in Job 1 required a new parameter. `stagger_expiry` is a boolean arm
selector reusing an existing draw, registered in `principles.ARM_SELECTORS`.

---

# JOB 2 — persistent match quality

Pre-registered in `PREREG-A12.md` §A12.2, complete before any Job 2 code
existed. Reproduce:

```
python3 research/crabs/run_a12.py j2       # the grid, K33 and K34
python3 research/crabs/run_a12.py j2k35    # what a 5% discount buys
python3 research/crabs/run_a12.py j2m      # the market channel
python3 research/crabs/run_a12.py j2hunt   # the Principle E hunt
```

## 2.0 The four headlines

1. **The founder's diagnosis of the code is correct.** `nu` is a *transient
   logit temperature*, not a taste over places; `move_transient` is half of a
   *cost*, redrawn each year; `market.Hab` has no quality field and searchers
   take the cheapest listing they see. Nothing in this model could ever generate
   "I moved because that place is better". Pinned by
   `test_nu_is_a_transient_logit_temperature_and_not_a_taste_over_places`.
2. **K33 FIRES.** With persistent match quality built and swept over the whole
   declared grid, free retention runs **82.6% → 72.4%** (loss) and
   **79.7% → 66.0%** (gain). Zero of twenty grid cells land inside 52–62%. At
   the CPS-sourced σ\* it is **80.1% / 76.9%**. Heterogeneity is a real missing
   channel and it is **not** the explanation for the retention gap.
3. **K35 FIRES, in the opposite direction to the hypothesis behind it.** A 5%
   renewal discount buys **more** retention when moving is partly about the
   place, not less: **+5.7pp → +7.6pp** (loss) and **+7.0pp → +8.8pp** (gain) at
   σ\*, rising to **2.2× / 1.9×** at the top of the grid. Proportionally too
   (32.8% → 45.3% of turnover removed). The threat to leave is *not* devalued.
4. **My own pre-registered prediction was refuted, and the bug hunt found a
   defect that had been hiding the answer.** I predicted K33 would not fire. It
   does. And the first implementation had the crab commit *before* looking,
   which PREREG-A12 §A12.2.3 does not say — under it retention was flat to four
   digits across the whole grid. §2.5 reports both.

## 2.1 What was already in the code — checked before building

| candidate | what it actually is | can it move a crab for a *place*? |
|---|---|---|
| `Params.nu = 0.60`, *"taste-shock scale, months"* | the logit temperature of the stay/leave decision. Its only two uses are `sigmoid((gb − c_tot)/nu)` in `world._year` and the station's integral of the same expression in `policies._leave_table`; the uniform it scales, `u[U_LOGIT]`, is **redrawn every crab-year** | **No.** It is attached to the decision, not to a place, and it is gone next period. Its expectation contributes nothing to the value of moving, and the station's DP integrates it out exactly. |
| `Params.move_transient = 0.5` | `_c_total = 0.5·c_persist + 0.5·c_transient`, the second redrawn yearly from the same lognormal | **No.** Half of a *cost*, and the redraw is mean-preserving. |
| `market.Hab` | `crab, ask, prior_rent, dom, ask0` | **No.** No quality field at all, and a searcher took `seen[0]` = the **cheapest** of the `K_VISIBLE` listings it viewed. |

`PARAM_SOURCES` already classified `nu` INVENTED — *"SPEC §4 gives no basis at
all, the table cell is '--'"*. The founder's reading is right on all three
counts: **every rented place was the same place.**

## 2.2 The Census arithmetic, re-checked

Every figure in the brief checks out. The four collapsed categories sum to
**16,336** against a 16,337 mover total — Census rounding, carried rather than
smoothed. Full derivation in `PREREG-A12.md` §A12.2.2; the mapping used is
**M3**, declared primary before running:

| channel | Census categories | share of moves | annual hazard |
|---|---|---|---|
| **MATCH** | newer/better/larger 2,207 + better neighborhood 967 | **19.428%** | **3.1418 %/yr** |
| **RENT** | cheaper housing 1,793 | **10.975%** | **1.7748 %/yr** |
| **EXO** | the remaining 11,370 | **69.597%** | **11.2548 %/yr** |

## 2.3 The mechanism, in one knob

`Params.match_sd` (months of market rent per year, default 0.0) is the only new
parameter. `Crab.match` is persistent for the whole tenancy; a mover views
`MATCH_K = 5` places — **`market.K_VISIBLE`, reused, not a second search-width
parameter** — and takes the best. The gain from moving is the **option value**
`kappa_crab · match_sd · E[(Z₅ − match/match_sd)⁺]`, strictly positive and
largest for the worst matched, which is exactly what a redrawn transient shock
cannot deliver. The Normal distribution is **INVENTED** and labelled so
everywhere. The station never sees `crab.match`; it integrates the population
distribution through `switching_cost_nodes`, and a test greps the offer path.

## 2.4 K33 — VERDICT: **FIRES**

*Fires if no grid point puts free M3 retention inside 52–62%. Registered spec,
Phase 1 arm A, 39% price askers, 60 stations, seeds 1000–1059.*

| `match_sd` | ret (loss) | ret (gain) | exo / rent / match, loss | match haz, loss | push, loss | push, gain |
|---|---|---|---|---|---|---|
| **0.00** control | 0.8263 | 0.7966 | 0.653 / 0.347 / 0.000 | 0.000% | +0.1009 | −0.0300 |
| 0.10 | 0.8240 | 0.7923 | 0.644 / 0.334 / 0.022 | 0.392% | +0.1012 | −0.0293 |
| 0.20 | 0.8219 | 0.7880 | 0.636 / 0.325 / 0.039 | 0.692% | +0.1012 | −0.0289 |
| 0.35 | 0.8157 | 0.7810 | 0.615 / 0.309 / 0.076 | 1.408% | +0.1017 | −0.0280 |
| 0.50 | 0.8107 | 0.7747 | 0.599 / 0.296 / 0.106 | 2.000% | +0.1022 | −0.0272 |
| 0.75 | 0.8022 | 0.7621 | 0.573 / 0.276 / 0.151 | 2.992% | +0.1029 | −0.0259 |
| 1.00 | 0.7938 | 0.7496 | 0.550 / 0.253 / 0.197 | 4.058% | +0.1033 | −0.0242 |
| 1.50 | 0.7769 | 0.7281 | 0.508 / 0.227 / 0.265 | 5.908% | +0.1040 | −0.0224 |
| 2.00 | 0.7608 | 0.7025 | 0.474 / 0.214 / 0.313 | 7.483% | +0.1049 | −0.0197 |
| 3.00 | 0.7239 | **0.6595** | 0.411 / 0.175 / 0.414 | 11.442% | +0.1064 | −0.0156 |
| *band* | *0.52–0.62* | *0.52–0.62* | *0.696 / 0.110 / 0.194* | *3.1418%* | | |

**0 of 20 cells in band. K33 FIRES.** The closest approach is 0.6595, at the top
of the grid in the gain regime — 4.0pp above the band, at a dispersion of 3
months of rent a year ($6,000/yr, 25% of the anchor annual rent) and a
match-driven move hazard of **11.4–14.0 %/yr against the Census's 3.14%**.

**At σ\*, the value set from the Census and not from retention:**

| | σ\* | retention | exo | rent | match | rent hazard | push |
|---|---|---|---|---|---|---|---|
| M3 loss | 0.7852 | **0.8010** | 0.570 | 0.273 | 0.158 | 5.43 %/yr | +0.1029 |
| M3 gain | 0.6090 | **0.7692** | 0.518 | 0.347 | 0.135 | 8.00 %/yr | −0.0266 |
| M1 loss | 0.7723 | 0.8116 | 0.540 | 0.294 | 0.167 | 5.53 %/yr | +0.1023 |
| M1 gain | 0.6172 | 0.7835 | 0.487 | 0.369 | 0.144 | 7.98 %/yr | −0.0277 |
| *CPS* | | *0.573* | *0.696* | *0.110* | *0.194* | *1.77 %/yr* | |

Retention at σ\* is a **free** output — σ\* is defined by the match hazard, not
by retention — and it lands **20 to 23 percentage points above the band**. That
is the whole result: adding the missing channel at the size the Census says it
is moves retention by about 2 points, and the gap is 24.

## 2.5 K34 — VERDICT: **VACUOUS**, and reported as vacuous

K34 fires if retention comes into band and the composition still cannot be
matched. Retention never comes into band, so there is no cell at which to run
the test. **This is not a pass.** Per §A12.2.8, the honest report is that the
question K34 was written to ask never became askable.

For the record, no grid cell passes the composition test either, and the reason
is the same in every one: **the rent channel is far too big.** At σ\* the model
puts 27–35% of moves in the rent channel against the Census's 11%, and a
rent-driven hazard of 5.4–8.0 %/yr against 1.77%. A11 measured that gap without
a match channel (5.9–9.8 %/yr) and adding one narrows it by about a third
without closing it. Both halves of the endogenous side are still too large.

## 2.6 K35 — VERDICT: **FIRES**, and the direction reverses

*Fires if `Δret(σ*)` is not at least 10% below `Δret(0)`. A flat 5% cut applied
to the renewal offer AFTER the DP chose it, so the policy is held fixed and the
comparison is on an identical population (Principle D).*

| | `match_sd` | retention, no cut | with a 5% cut | Δ retention | turnover removed |
|---|---|---|---|---|---|
| M3 loss | 0.00 | 0.8263 | 0.8832 | **+0.0569** | 32.8% |
| M3 loss | **0.785 = σ\*** | 0.8031 | 0.8791 | **+0.0760** (1.34×) | 38.6% |
| M3 loss | 3.00 | 0.7239 | 0.8491 | **+0.1252** (2.20×) | 45.3% |
| M3 gain | 0.00 | 0.7966 | 0.8664 | **+0.0698** | 34.3% |
| M3 gain | **0.609 = σ\*** | 0.7672 | 0.8551 | **+0.0879** (1.26×) | 37.7% |
| M3 gain | 3.00 | 0.6595 | 0.7897 | **+0.1302** (1.87×) | 38.2% |

K35 fires if the discount buys *at least 10% less*. It buys **26–34% more**, and
the result survives the proportional check: the same 5% cut removes 32.8% of
turnover with no match channel and 38.6% at σ\*.

**So the answer to the question the article wants is: no, the threat to leave is
not weakened — it is strengthened.** The reasoning that says otherwise treats a
tenant who wants a bigger kitchen as a lost cause. In this model it is the
opposite: a tenant who has a *reason* to move is a tenant sitting near
indifference, and a tenant near indifference is exactly who a discount retains.
A tenant who is happy where it is has nothing to be bought off about. The match
channel manufactures marginal tenants, and marginal tenants are the ones price
moves.

**What is claimed and what is not.** The *magnitude* (2.2×) is a readout of `nu`
(INVENTED, the logit temperature), because the slope of the sigmoid is what
converts a rent change into a retention change. The **direction** is not a
readout of `nu`: any single-peaked latent-index distribution has a rising
density below its median, so pushing the leave rate up toward 50% raises the
derivative. It would reverse only in cells where turnover exceeds 50%, and the
highest cell here is 34.1%. That condition is checkable and is stated rather
than assumed.

**And the landlord's answer runs the other way, which is the interesting part.**
Over the same grid the station's own DP re-solves and asks for **more**: the
loss-regime push rises +10.09% → +10.64% (toward the 12% cap) and the
gain-regime cut shrinks −3.00% → −1.56%. Two different derivatives, both
measured: a discount retains *more* tenants per point of rent, and each retained
tenant is worth *less* to retain, because everyone's expected tenancy is shorter.
The landlord follows the second. **When more of the leaving is about the place,
the landlord stops trying to buy tenants back and harvests the rent instead** —
even though buying them back has become cheaper per tenant.

## 2.7 The bug hunt (DESIGN-PRINCIPLES E), reported in full

Required by §A12.2.8 if both kills came into range at once. They did not — K33
fired — so this was not owed. It was run anyway, and **it found a defect, in the
direction that was hiding the answer.**

**(0) The defect.** The first implementation set the gain from moving to
`kappa · (E[best of 5] − match)`. Because a sitting crab's own match is *also* a
best-of-5 draw, that makes moving a **fair gamble with mean zero at entry** —
and PREREG-A12 §A12.2.3 says *"search lets it see some draws **before
committing**"*, which is an option value, not a gamble. Under the wrong version:

| `match_sd` | retention, loss | retention, gain | match share of moves, loss |
|---|---|---|---|
| 0.00 | 0.8263 | 0.7966 | 0.000 |
| 1.00 | 0.8305 | 0.7986 | 0.123 |
| 3.00 | 0.8233 | 0.8005 | 0.262 |

**Retention is flat to three digits while the composition moves 26 points.** K33
fired trivially and for the wrong reason. Corrected to the registered form —
`E[(best of 5 − match)⁺]`, computed by quadrature on the inverse CDF and checked
against Monte Carlo to four decimals — retention moves 10–14 points and K33 still
fires, on its merits. Both specifications are in the tables above and below; the
wrong one is retained as the declared `match_option = False` control, because it
is exactly the "no option to look first" ablation and it is the sharpest single
finding in Job 2 (§2.8).

**(i) `match_sd` must not reach the offer.** The renewal offer is built from
`rt_pop`, the population expectation; `crab.match` appears only in `rt`, the
tenant's private reservation, which is read by the leave test. Greps the source.
`test_the_station_never_sees_a_crab_s_match_draw`. **Clean.**

**(ii) The attribution must not double-count.** `exo + rent + match ==
n_renewal_left`, exactly, over every run.
`test_the_move_attribution_partitions_the_leavers`. **Clean.**

**(iii) The option-value ablation.** See §2.8. **Found the mechanism.**

**(iv) Held-out seeds 7000–7059.** Reproduces: gain `sd=3` 0.6659 against 0.6595
on main seeds, loss `sd=3` 0.7246 against 0.7239, and the composition matches to
two decimals. **Not a seed artefact.**

**(v) Market channel agrees in direction.** `market.py` retention 0.8873 →
0.8733 over the same grid, match share of moves 0.000 → 0.103. Much weaker,
because the market channel's leave test is a hard threshold against a
~8-month-of-rent walk-away rather than a logit, so a few months a year of match
value rarely crosses it. **Same sign, different size, and the reason is
structural and stated.**

**(vi) Inert at zero.** Every previously reported Phase-1 and market cell is
bit-identical with the mechanism compiled in — asserted, not claimed
(`test_match_quality_is_inert_at_zero_dispersion`, and the whole suite passing
unchanged).

## 2.8 The sharpest thing Job 2 found

The `match_option = False` control isolates it. Both arms have persistent,
heterogeneous, habitat-specific match quality of exactly the same dispersion.
They differ in one thing: whether the crab gets to **look before it commits**.

| | retention, gain | match share of moves | rent share of moves |
|---|---|---|---|
| `match_sd = 0` | 0.7966 | 0.000 | 0.413 |
| `sd = 3`, **commits blind** | 0.8005 | 0.246 | 0.155 |
| `sd = 3`, **looks first** | **0.6595** | 0.412 | 0.237 |

**Persistence alone changes only the label on the move. The option to look
first is the entire effect on how much moving there is.** With blind commitment
the model reallocates a quarter of its moves into the match channel and its
retention does not move at all — 0.7966 to 0.8005, inside two standard errors.

That matters beyond this study, because "people have different tastes" is the
form the hypothesis is usually stated in, and it is the half that does nothing.
What generates mobility is not that places differ; it is that a mover can see
several and keep the best. **Heterogeneity without search is a relabelling.**

## 2.9 My pre-registered prediction, scored

`PREREG-A12` §A12.2.11, written before any Job 2 number existed:

| prediction | outcome |
|---|---|
| "K33 does NOT fire — some grid point will reach 52–62% mechanically" | **REFUTED.** 0 of 20. The top of the grid gets to 66.0% and no further. |
| "K34 DOES fire" | **NOT REACHED.** K34 is vacuous, because K33 fired. |
| "at σ\* retention lands 76–80%" | **CONFIRMED.** 80.1% (loss) / 76.9% (gain). |

The arithmetic half of the prediction was right and the mechanism half was
wrong: I expected a large enough dispersion to churn everybody, and it does not,
because the crabs who are badly matched leave and are replaced by best-of-five
draws. **Sorting is absorbing.** The stock of sitting tenants is better matched
than the entry distribution (mean match 4.17 against an entry mean of 3.49 at
`sd = 3`), which is a brake the model applies to itself.

## 2.10 What Job 2 changes in the record

| claim | change |
|---|---|
| A11: "the model cannot match observed retention AND the Census composition" | **HOLDS, and is now stronger.** With the missing third channel built and sourced, retention is still 20–23pp above the band. The explanation is not the missing channel. |
| A11: the model puts 90.4% of moves in the non-rent channel vs CPS 61.2% | **superseded by a three-way split.** At σ\* under M3 the model puts 57/27/16 (exo/rent/match) against 70/11/19. The exogenous share is now roughly right; **the rent channel is the one that is 2.5× too big.** |
| `nu` is a "taste-shock scale" | **the name is wrong** and the code says so. It is a per-period logit temperature. `PARAM_SOURCES` and the field comment now say so. |
| "a tenant who would move anyway is not making a price threat" | **REFUTED in this model**, at every dispersion, in both regimes, absolutely and proportionally. K35 FIRED. |
| where the next amendment should look | **not heterogeneity, and not search width.** The rent channel is 2.5–4.5× the Census, and `move_med` is still CALIBRATED to observed elasticity. That is the remaining fitted half of retention (A11 §9), and it is the only channel left that is large enough to close a 24-point gap. |

**For `FREE-OUTPUTS.md`'s owner** (not edited here): a new row is due —
*reason-for-move composition, three-way*: **FREE except the match hazard**,
which is fitted through `match_sd` at σ\* by construction, and which is the only
thing σ\* is fitted to. Retention remains half-fitted through `move_med`, and
every retention figure above is reported with that caveat attached.

## 2.11 What Job 2 does not establish

- **It does not test taste *drift*.** The Census category is "wanted a
  newer/better/larger place", and a household whose needs change is not
  redrawing from a stationary distribution — its *current* match falls while the
  place stays the same. That is a second mechanism, it is not `match_sd`, and it
  was not pre-registered, so it was not built. It is the obvious A13.
- **It does not rescue the market channel's leave rule.** `market.py` decides
  leaving with a hard threshold, so it is structurally much less responsive than
  Phase 1's logit; the two agree in sign and not in size, and §2.7(v) says why.
- **The magnitudes are readouts of `nu`.** Directions are claimed; sizes are not.
- **It does not make the composition matchable.** No grid point passes, and the
  binding failure is the rent channel, which A12 did not touch.

# PREREG — AMENDMENT 12

*Written 2026-07-25. §A12.1 (Job 1) is forensic and was written alongside its
runs; it carries no kill condition and claims nothing, because it only reads
statistics off code that already existed. **§A12.2 onward (Job 2) is complete
before any Job 2 code exists.** No `Params` field named below has been added to
`world.py` at the time of writing, `run_a12.py` has no `j2` entry point, and no
Job 2 number has been computed.*

Binding: `research/DESIGN-PRINCIPLES.md` A through G.

---

## A12.1 JOB 1 — the two vacancy reports

Not an experiment. Two amendments reported two numbers about one simulation and
at most one of them can mean what it was taken to mean:

- AMENDMENT 10 derived `vacancy` = **4.376 months** time-to-let (fixed point) and
  filed it as an upper bound "contaminated by the deflation defect".
- AMENDMENT 11 reported `market.py`'s baseline vacancy rate as **0.0000** in
  every cell, 2.14% in the supply-shock cell, and flagged it uninvestigated.

Declared before the ablation was written: the ONE knob permitted is
`MarketParams.stagger_expiry`, which empties a leaving tenant's habitat in the
month that tenant enters the search pool instead of at the annual boundary. It
reuses the tenant's own `u[9]` draw, so it introduces **no parameter and no
randomness**, and it defaults OFF so every previously reported cell is
bit-identical (asserted by a test, not claimed).

Results: `RESULTS-A12.md` §1.

---

## A12.2 JOB 2 — the founder's hypothesis

### A12.2.1 The hypothesis, and what is actually in the code today

> We never modelled crabs having preferences over habitats. Every rented place is
> treated as the same place. A crab can only move because rent changed or because
> an exogenous shock hit it. It can never move because somewhere else is simply
> *better for it*.

**Checked against the code before building anything. The hypothesis is correct,
and the two candidates that might have contradicted it do not.**

1. **`Params.nu = 0.60`, "taste-shock scale, months".** Its only two uses are
   `world.py:_year` — `endo = u[U_LOGIT] < sigmoid((gb - c_tot) / p.nu)` — and
   `policies.py:_leave_table`, the station's integral of the same expression.
   `u[U_LOGIT]` is a fresh uniform for every crab-year. **`nu` is the logit
   temperature of the stay/leave decision, drawn i.i.d. every period.** It is not
   a taste and it is not persistent. Its expectation contributes nothing to the
   value of moving, and the station's DP integrates it out exactly. A crab cannot
   move "because that place is better" through `nu`, because the shock is
   attached to the *decision*, not to a *place*, and it is gone next year.
   (`PARAM_SOURCES` already classifies it INVENTED: *"SPEC §4 gives no basis at
   all — the table cell is '--'"*.)
2. **`Params.move_transient = 0.5`.** `_c_total` returns
   `(1-a)·c_persist + a·c_transient` with `c_transient` redrawn each year from
   the same lognormal. That is half of a **cost** redrawn each period. It is not
   a match value either, and the redraw is mean-preserving.
3. **`market.Hab` has no quality field at all**, and a searcher takes
   `seen[0]` = the lowest ask among the `K_VISIBLE` listings it views. Choice is
   over price only.

**So the answer, before building: the model implements a transient shock, not a
persistent match value, in both places, and habitats are literally
interchangeable.** The founder's diagnosis stands.

### A12.2.2 The Census target, arithmetic re-checked

Source is A11's, not re-fetched: U.S. Census Bureau, *Geographic Mobility: 2023*
(2023 CPS ASEC), Table 13 and Table 1, row "In a renter-occupied housing unit",
thousands. Re-derived here:

| | count | share of movers |
|---|---|---|
| Total movers | 16,337 | 100% |
| family-related | 3,496 | 21.399% |
| employment-related | 3,845 | 23.536% |
| housing-related | 6,330 | 38.746% |
| other | 2,665 | 16.313% |

The four collapsed categories sum to **16,336**, one thousand short of the 16,337
mover total — Census rounding, carried rather than smoothed. Housing splits
exactly: 1,793 + 2,207 + 967 + 149 + 149 + 1,065 = 6,330.

| | count | share of movers | annual hazard |
|---|---|---|---|
| **cheaper housing** (RENT) | 1,793 | **10.975%** | **1.7748 %/yr** |
| **newer/better/larger** | 2,207 | 13.509% | |
| **better neighborhood / less crime** | 967 | 5.919% | |
| **the two together** (MATCH) | 3,174 | **19.428%** | **3.1418 %/yr** |
| everything else (EXO, mapping M3) | 11,370 | **69.597%** | **11.2548 %/yr** |

Renter mover rate = 16,337 / 101,024 = **16.1714 %/yr**. Every figure in the
brief checks out to the digits given.

**Two mappings, both declared now, primary named now.**

- **M3 (PRIMARY).** MATCH = newer/larger + neighborhood. RENT = cheaper. EXO =
  everything else, which puts "other housing reason" (1,065), "wanted to own"
  (149) and foreclosure (149) in the exogenous bucket. `p_exo` = 0.1125475.
- **M4 (robustness).** "Other housing reason" moves into MATCH:
  MATCH = 25.947% (4.1960 %/yr), EXO = 63.078% (10.2006 %/yr).

For continuity with A11 the sweep is also run at A11's **M1** `p_exo` = 0.099046
(non-housing only), so K33 can be read against RESULTS-A11 §2 without a second
change of variable.

### A12.2.3 The treatment: persistent match quality. ONE knob.

**One new parameter: `Params.match_sd`, months of market rent per year, default
0.0.** Nothing else is added. Everything below reuses a constant that was
declared before A12 existed.

- **`Crab.match`** — this crab's annual valuation of *this* habitat over an
  average one, in months of market rent per year. **Persistent for the whole
  tenancy**: it is drawn once, on move-in, and never redrawn while the crab
  stays. Moving means drawing again. This is the whole difference from `nu`.
- **Drawn as the best of `MATCH_K` i.i.d. `Normal(0, match_sd)` draws**, because
  a mover *searches*: it views several places and takes the one that suits it.
  `MATCH_K = 5` **is** `market.K_VISIBLE = 5`, declared in market.py's
  before-running list as *"listings a searcher can see (local information
  only)"*. A test asserts the two are equal, so this adds no parameter.
- **`MATCH_EMAX` = E[max of 5 standard normals] ≈ 1.162965**, computed by
  quadrature in code, not typed in.
- **The move channel.** The gain from leaving, in months over the crab's
  `kappa_crab` horizon, gains
  `mg = kappa_crab · (MATCH_EMAX · match_sd − crab.match)`,
  so `endo = u[U_LOGIT] < sigmoid((gb + mg − c_tot) / nu)`.

**Why this is a preference and the redraw is not.** With a transient shock the
new place is drawn from the same distribution as the old one and is in
expectation no better, so `E[mg] = 0` and nobody ever moves *for* it. Here the
crab that moves gets the best of five, so `E[new match] = MATCH_EMAX · match_sd`
against a current draw that may be much worse. **The selection at search is the
entire mechanism**; without it, persistence alone would still not generate "I
moved because that place is better".

**Distribution: Normal. LABEL: INVENTED** (Principle C rule 1). No published
distribution of renter idiosyncratic match values exists; nothing upstream of
rent-setting pins its shape. It is registered INVENTED in `PARAM_SOURCES` and
labelled INVENTED in every result table. The *scale* is swept, and the primary
value is set from an observable that is **not** retention (§A12.2.6).

**Information budget (Principle B), declared.** The station's observation set is
unchanged. It never sees `crab.match`. It integrates over the **population**
distribution of the effective barrier `c_total − mg` at entry, which is exactly
what `switching_cost_nodes` already does for `c_persist`; `policies._leave_table`
is untouched. At entry `E[MATCH_EMAX·match_sd − match] = 0` by construction, so
the *offer* is unchanged in expectation and no private draw can leak into it —
the hole that manufactured artefact #2. A test greps the offer path.

**Market side (`market.py`).** A searcher draws an i.i.d. `Normal(0, match_sd)`
for each of the `k` listings it views and takes the listing maximising
`match_i · M_obs − 12 · ask_i` (annual dollars) instead of the lowest ask;
`next_best` is the runner-up on the same criterion; the tenant's
`r_t_max` gains `(match_i − match_next) · M_obs`. At renewal, the sitting
tenant's `r_t_max` gains `(crab.match − MATCH_EMAX · match_sd) · M_obs`, and the
landlord's population expectation of that term is **zero**, so `wa_t_exp` and the
offer are untouched. At `match_sd = 0` no draw is taken, so every previously
reported market cell is bit-identical (asserted).

### A12.2.4 Attribution of moves — declared before measurement

Three channels, exhaustive and ordered, so the shares sum to 1:

1. **EXO** — the `p_exo` draw fired.
2. Otherwise **MATCH-DRIVEN** — the crab leaves, and would **not** have left with
   `mg` set to 0 on the *same* uniform draw. Deterministic, no extra randomness,
   and `mg ≥ 0` is not assumed (a crab with a better-than-average match has
   `mg < 0` and the counterfactual runs the other way).
3. Otherwise **RENT-DRIVEN**.

Same rule in `market.py` with `rt_nomatch = 12·M_obs + wa_t`.

New recorder keys: `left_match`, `left_rent` (world), `n_renewal_left_match`,
`n_renewal_left_rent` (market). Population `every renewal decision`, the
denominator already declared.

### A12.2.5 The grid, fixed now

```
match_sd ∈ {0.00, 0.10, 0.20, 0.35, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00}
```
months of market rent per year. `0.00` is the control — the shipped model. For
scale, 1.00 month/yr is $2,000/yr, 8.3% of the $24,000 anchor.

`p_exo` variants: **M3** `0.1125475` (primary), **M1** `0.099046` (A11
continuity). Both flat, per A11 §1.3 — CPS publishes no reason-for-move by
length of residence, so the shipped `exp(−(j−1)/3)` decay has no source.

Specification: **registered**, Phase 1 arm A, 39% price askers, 60 stations,
seeds 1000–1059, both regimes — identical to A11's K31 cell, so the before/after
is one knob.

### A12.2.6 σ\* — the primary value, set from something that is not retention

**σ\* is the `match_sd` at which the model's MATCH-DRIVEN annual leave hazard
equals the CPS figure 3.1418 %/yr**, by linear interpolation on the declared
grid. Fixed now, before any output exists.

Consequence, stated now rather than discovered later (Principle G): at σ\* the
**match-driven share of moves is FITTED** and may not be claimed. **Retention at
σ\* is FREE**, and that is what K33 tests.

### A12.2.7 K33 — the kill on retention, bidirectional

> **K33 FIRES if NO value of `match_sd` on the declared grid brings free
> retention inside 52–62% (observed ~57.3%), in either regime, under the primary
> M3 `p_exo`.**

- **Fires** ⇒ persistent match heterogeneity cannot reach observed retention *at
  any dispersion the grid contains*, and is refuted as the explanation. Something
  else is missing, and A11's two-facts-cannot-both-hold result stands with a
  third channel added.
- **Does not fire** ⇒ heterogeneity can reach the retention level. That is not
  yet a success: it then matters at what dispersion, and what it does to the
  composition, which is K34.

The grid, rather than σ\*, is the object of K33 deliberately. A kill evaluated
only at σ\* would be a kill on one interpolation; a kill on the grid asks whether
the mechanism can do the job *in principle*.

### A12.2.8 K34 — the kill on composition, bidirectional

**Composition PASSES at a given `match_sd` iff all four hold** (M3 targets):

| | target | tolerance |
|---|---|---|
| exogenous share of moves | 0.69597 | ± 0.05 |
| rent-driven share of moves | 0.10975 | ± 0.05 |
| match-driven share of moves | 0.19428 | ± 0.05 |
| rent-driven annual hazard | 1.7748 %/yr | 1.0 % – 2.6 % |

> **K34 FIRES if retention comes inside 52–62% at some `match_sd` AND the
> composition test fails at every such `match_sd`.**

- **Fires** ⇒ one failure has been traded for another and must be reported as
  such: the model can be made to churn at the observed rate only by inventing a
  reason-for-move mix the Census contradicts.
- **Does not fire** ⇒ either K33 fired (retention never arrives, K34 is vacuous
  and is reported as vacuous, not as a pass), or **there exists a single
  `match_sd` at which retention and the Census composition hold together.**

**If BOTH come into range at once**, that is the outcome most favourable to the
hypothesis and therefore gets the Principle E treatment before it is believed:
a bug hunt, reported whether or not it finds anything, covering at minimum
(i) that `match_sd` is not silently re-entering the offer path,
(ii) that the attribution counterfactual is not double-counting `p_exo` leavers,
(iii) that the retention gain is not coming from the *level* of `MATCH_EMAX`
rather than from the dispersion (ablate by setting `MATCH_EMAX = 0`, i.e.
persistence with no search selection — the "transient shock" control),
(iv) held-out seeds 7000–7059,
(v) that the market-side and Phase-1 retention agree in direction.

### A12.2.9 K35 — the threat to leave as a bargaining chip

The question: if most moving is about wanting a different place rather than a
cheaper one, what happens to the tenant's threat to leave, and how should a
landlord who knows that price?

**Measured, not asserted.** Two instruments, both declared now:

1. **What a discount buys.** Re-run the same cell with every renewal offer cut by
   a flat 5% of the offer (`offer_cut = 0.05`, a declared ablation knob, default
   off), and record the retention gain. `Δret(σ) = retention(cut, σ) −
   retention(no cut, σ)`. This is the price-elasticity of retention on an
   identical population (Principle D).
2. **What the landlord does about it.** The station's DP re-solves against the new
   leave table, so `mean_offer_push` and the free-cap push (`renewal_cap = 2.0`)
   at σ\* against σ = 0 are the landlord's endogenous answer.

> **K35 FIRES if `Δret(σ*)` is NOT at least 10% (relative) below `Δret(0)`.**

- **Fires** ⇒ match heterogeneity does *not* blunt the price lever, and the
  writing may not say the threat to leave is weakened by it.
- **Does not fire** ⇒ a rent concession buys measurably less retention once
  moving is partly about the place, which is the claim the article wants — and it
  is then reported with its magnitude, not as a direction.

### A12.2.10 The free-outputs register (Principle G), written before the run

| observable | fitted? | through what |
|---|---|---|
| match-driven share / hazard of moves | **FITTED at σ\*** | `match_sd`, by construction of σ\* |
| **retention** | **FREE of A12** | nothing in A12 is set by reference to it. Still *half*-fitted overall: `move_med` remains CALIBRATED to observed elasticity (A11 §3.1, A8 outstanding). Stated with every retention number. |
| exogenous share of moves | **FITTED** | `p_exo`, sourced in A11 |
| rent-driven share and hazard | **FREE of A12**, same `move_med` caveat | |
| Δret from a 5% discount (K35) | **FREE** | |
| renewal push under heterogeneity | **FREE of A12**; still a readout of `renewal_cap` (FREE-OUTPUTS row 4) | |
| market rent level, vacancy level | **FITTED / defective** — see §A12.1 | |

### A12.2.11 On-record prediction, made before running

Recorded because this study's own track record says six of seven artefacts ran
toward the more interesting story, and because A11's author put a prediction on
the record and had it confirmed.

**I predict K33 does NOT fire and K34 DOES.** Reasoning: a large enough
dispersion churns everybody, so some grid point will reach 52–62% mechanically;
but at the CPS-sourced σ\* the arithmetic is nearly forced — `p_exo` alone is
11.25 %/yr, the model's rent channel runs 5.9–9.8 %/yr, and adding 3.14 %/yr of
match moves lands total turnover near 20–24 %/yr, i.e. retention **76–80%**,
still well outside the band. So I expect heterogeneity to be vindicated as *a*
missing channel and refuted as *the* explanation, and I expect the σ that reaches
observed retention to put far more than 19.4% of moves in the match channel.

If both land in range at once I will not believe it without §A12.2.8's hunt.

### A12.2.12 What would make Job 2 unpublishable

- Setting `match_sd` by looking at retention. It is set from the CPS upgrade
  hazard, and the grid is fixed in §A12.2.5 before any run.
- Letting `crab.match` reach the offer. Tested, not asserted.
- Reporting the match channel's *magnitude* in dollars without saying the market
  rent it is denominated in — Job 1's own finding, applied to Job 2.
- Reporting a composition "match" without the retention it came with, or the
  reverse. Both go in one table.

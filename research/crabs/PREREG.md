# PREREG — Station Rents: does countering create value, or get priced in?

*Written 2026-07-24, BEFORE any simulation code exists or is run. Kill
conditions are bidirectional and stated in terms of OUTPUTS, not inputs.
Nothing below may be edited after the first run; amendments append.*

## 0. Why this experiment

The article `writing/rent-no-source.md` makes three claims that rest on
argument rather than measurement:

1. **The ranked-ask claim.** Asking for a one-time concession (free weeks,
   waived fees, longer term) beats asking for a headline rent cut, because
   headline rent resets the building's comparable.
2. **The regime claim.** Tenant leverage depends on the sign of
   loss-to-lease. Low elasticity measured when sitting tenants were
   *below* market cannot be projected to a world where they're *above* it.
3. **The implicit claim of the product.** That countering is worth doing
   at all.

None is tested. Worse, there is an obvious economic objection nobody in
the tenant-advice literature addresses: **if the landlord expects
countering, they raise the opening ask and concede back to the same
place.** In that world our tool produces nothing, and — if the landlord
cannot tell askers from non-askers ex ante — it makes non-users strictly
worse off.

That objection is the point of this experiment. We are trying to break
our own product.

## 1. The world (deliberately minimal)

**Stations** are landlords. Each holds `U` habitats. Each period, per
occupied habitat, a station issues a renewal offer, and may concede if
countered. A station knows: market rent, its own vacancy, each crab's
tenure and payment history. It pays a turnover cost `T` plus vacancy
time when a crab leaves.

**Crabs** are tenants. Each has a tenure, an idiosyncratic moving cost, and
an outside option = market rent + moving cost. Each period it accepts,
counters, or leaves.

**The market rent** `M_t` evolves exogenously and is the regime variable.
Two regimes, both run:
- **LOSS-TO-LEASE (2022-like):** market rent rising above sitting rents.
  Leaving costs you more.
- **GAIN-TO-LEASE (2026-like):** market rent falling below sitting rents.
  Leaving may save you money.

## 2. Grounding — parameters come from verified data, not taste

| Parameter | Value | Source |
|---|---|---|
| Turn cost `T` | 1–2 months' rent ($2,000–4,000) | NAA/IREM/BOMA Income/Expense IQ |
| Annual turnover (calibration target) | ~47% | NAA |
| Retention (calibration target) | ~54–57% | RealPage |
| Share who counter | 39% | Avail/Urban Institute 2022 |
| Counter success | 22% | same |
| Success by tenure | 26–27% (2y+) vs 14–15% (<2y) | same |
| Typical concession | ~11% of annual rent ≈ 6 weeks | RealPage Jun 2026 |
| New-vs-renewal spread (gain regime) | −7.0% / +5.4% | MAA Q1 2026 |

## 3. VALIDATION GATE — must pass before any counterfactual is believed

With crab strategies set to the **empirical mix (39% counter)** and NO
tuning of station policy to hit these targets, the simulation must
reproduce:

- **V1:** counter success rate within **15–30%** (target 22%)
- **V2:** retention within **45–65%** (target ~54%)
- **V3:** tenure effect in the right direction and non-trivial — 2y+
  success at least **1.5×** under-2y success

**If V1–V3 fail, the model does not describe the world and every
counterfactual below is void.** We report the failure and stop. We do NOT
tune parameters to pass and then present the counterfactuals as findings;
if we tune anything post-hoc, the run is relabelled exploratory and the
gate is re-run on held-out seeds.

## 4. Arms

- **A — CONTROL: empirical mix.** 39% counter (on price), 61% never.
- **B — ALL-PRICE.** 100% counter, asking for headline rent reduction only.
- **C — ALL-RANKED (SNHP).** 100% counter, asking easiest-first:
  concession → fees → term → rent.
- **D — SHARE SWEEP.** Asker share ∈ {0, 10, 25, 50, 75, 100}%, strategy
  = RANKED, measuring askers and non-askers **separately**.
- **E — ADAPTIVE STATION.** As D, but the station's policy anticipates the
  asker share and pre-inflates its opening offer. *This is the arm
  designed to kill us.*

All arms × both regimes. Seeded, deterministic, ≥200 station-years per
cell, seeds fixed before running and reported.

## 5. Kill conditions — pre-registered, bidirectional

**K1 — the ranked-ask advice is decoration.**
*Fires if* C does not beat B on mean crab surplus by ≥2% of annual rent in
the gain regime.
*Consequence:* the "ask easiest first" section of the article is removed
or downgraded to a hypothesis, and the tool stops ranking asks as if it
mattered.

**K2 — negotiation value is transitional, not structural.**
*Fires if* in arm E, per-asker surplus declines monotonically toward ≤25%
of its arm-D value as asker share → 100%.
*Consequence:* we publish that the tool works only while adoption is low.
That materially changes the product's honest pitch and must appear on the
page, not just in the article.

**K3 — the tool has a negative externality.**
*Fires if* non-asker surplus in arm E at 75–100% asker share is
**worse** than non-asker surplus at 0% by ≥1% of annual rent.
*Consequence:* published prominently. A tool that quietly taxes people who
don't use it is a thing we would need to say out loud.

**K4 — the regime argument is wrong.**
*Fires if* C's advantage over A is not materially larger in the
gain-to-lease regime than in the loss-to-lease regime.
*Consequence:* the article's central rescue argument ("elasticity is
regime-dependent") is removed. This is the claim I most want to be true,
so it gets the sharpest test.

**SURVIVES (the thesis holds) if:** C > B > A on crab surplus in the gain
regime; the advantage is regime-dependent (K4 does not fire); and per-asker
value degrades but does not vanish under an adaptive station.

**NULL:** all arms within noise → countering is irrelevant in this model,
and we report that the simulation could not detect an effect either way.

## 6. What this experiment CANNOT establish

Stated now so it isn't overclaimed later:

- It is a model, not evidence about real landlords. Its parameters are
  calibrated to real aggregates, but station *policy* is our invention.
  A result here is an argument about mechanism, never a measured outcome.
- It cannot tell us whether real tenants will send the message (the
  courage problem, which is the actual product bottleneck).
- It cannot validate the tool's advice for any individual.

## 7. Reporting rules

- Every kill condition gets an explicit FIRED / DID NOT FIRE line.
- The validation gate result is reported first, before any arm result.
- Seeds, parameters, and the exact code version are published.
- If K2 or K3 fires, that goes in the article's own section — not a
  footnote, and not omitted because it's inconvenient.

---

# AMENDMENT 1 — landlord types, broadcast, and shocks (Phase 2)

*Appended 2026-07-24, still BEFORE any results exist from Phase 1. Phase 1's
arms and kills (§4–§5) are unchanged and are evaluated on their own. These
are additional pre-registered arms with their own kills.*

## A1.1 Landlord types — a new dimension, crossed with all Phase-1 arms

Grounded in the verified data, and the grounding produces a paradox worth
testing:

| Type | Habitats | Policy | Empirical anchor |
|---|---|---|---|
| **INSTITUTIONAL** | 200+ | Full revenue management. Estimates P(leave) from market rent, tenure, payment history, moving-cost distribution. Concedes when EV-positive. | RealPage-class RM explicitly models turn cost, vacancy loss, elasticity **and tenure**. Concessions on 25.5% of apartments. |
| **MEDIUM** | 20–75 | Comp-aware but heuristic. Anchors on market rent + a fixed target increase; concedes on a simple rule. | Regional operators; no published policy — this arm is our invention and is labelled as such. |
| **MOM-AND-POP** | 1–10 | Rarely raises at all; when it does, rarely concedes. Weights tenant reliability heavily. | **18.0% hold a strict no-increase policy** ("stability of a reliable tenant > marginal gain"); **~90% offer no concessions even with longer vacancies** (TurboTenant, ~2,000 landlords). |

**The paradox to test:** mom-and-pops are the *best landlord to have* (they
often don't raise) and the *worst to negotiate with* (they don't concede).
Institutions are the reverse. So the tool may be **most valuable against
the most sophisticated counterparty** — which is counterintuitive and, if
true, changes who we should tell to use it.

**K5 — landlord type is not actionable.**
*Fires if* mean crab gain from countering differs by <1% of annual rent
across the three types.
*Consequence:* the tool stops asking about building size, and we drop any
"know your landlord" advice as decoration.

**K6 — the tool is worth least where we aimed it.**
*Fires if* crab gain from countering is **highest against MOM-AND-POP**.
*Consequence:* our v1 scoping (large multifamily, ≥75 units, because that's
where the listing data is) is aimed at the wrong segment, and RENEWAL-SPEC
§3 must be rewritten.

## A1.2 Broadcast — modelling our own product at scale

Crabs may broadcast the outcome of their renewal (what they asked, what
they got) to neighbours in the same station. Neighbours update: (a) their
belief that countering works, raising the asker share endogenously, and
(b) their ask calibration, moving toward what actually cleared.

**This arm is not a metaphor. SNHP publishing base rates and ranked asks
IS the broadcast mechanism.** Arm F is therefore the closest thing to a
test of what happens if the product works.

- **Arm F — BROADCAST.** As arm D, plus neighbour broadcast. Run against
  all three landlord types, and against both the static and ADAPTIVE
  institutional policy.

**K7 — our product is net-harmful at scale. (The one that matters most.)**
*Fires if* under BROADCAST + ADAPTIVE INSTITUTIONAL, **total crab surplus
is lower** than under no-broadcast by ≥1% of annual rent.
*Consequence:* published on snhp.dev/rent itself, not just in the article.
A tool whose success makes its users collectively worse off is a thing we
would have to say out loud, in the product.

**K8 — broadcast only helps the loud.**
*Fires if* under BROADCAST, non-asker surplus falls while asker surplus
rises, versus no-broadcast.
*Consequence:* reported prominently; it is K3's externality with a
mechanism we actually control.

## A1.3 Shocks — EXPLORATORY, and labelled as such

These are for mechanism intuition and for the article's narrative. **They
are exploratory, not confirmatory: no product decision may rest on them,
and they carry no kill conditions.** Saying so now prevents them being
promoted to evidence later.

- **CRAB FLU (demand collapse).** Occupancy demand drops sharply for ~8
  periods; vacancies spike; market rent falls. *Question:* does tenant
  leverage actually appear in a demand shock, or do stations hold rents
  and eat vacancy? (Real precedent: operators deliberately running lower
  occupancy for higher NOI.)
- **THE AI CRAB MIGRATION (wealth shock).** A cohort of high-budget crabs
  arrives at a subset of stations over ~6 periods, then a fraction departs
  abruptly. *Question:* what happens to incumbent crabs when rich
  newcomers reset the comp — and does gain-to-lease invert on the way out?
  (Real precedent: 2021–2026 tech-boom metros and the subsequent Austin
  correction, where the worst market turned positive first.)

Report shock results in a clearly separate EXPLORATORY section with no
kill-condition language and no product implications.

## A1.4 Reporting discipline for Phase 2

- Phase 1 results are reported and interpreted **before** Phase 2 is run,
  so Phase 2 cannot be quietly tuned to rescue Phase 1.
- K5–K8 each get an explicit FIRED / DID NOT FIRE line with numbers.
- The MEDIUM landlord policy is our invention with no empirical anchor;
  every result involving it carries that caveat.

---

# AMENDMENT 2 — emergence, and the mechanisms Phase 1 was missing

*Appended 2026-07-25, AFTER Phase 1/2 results are known and reported. This
is therefore explicitly a NEW pre-registration informed by a failure, not a
reinterpretation of it. Phase 1's verdicts stand as reported: gate FAILED,
K1/K3/K4/K8 FIRED. Nothing below revises them.*

## A2.0 Why

Two problems with Phase 2 as built:

1. **Landlord behaviour was hardcoded.** MOM-AND-POP was *told* to rarely
   raise and rarely concede; INSTITUTIONAL was *told* to run revenue
   management. So the "paradox" it produced was an input, not a finding.
   Worthless as validation.
2. **The gate failed for an identified reason:** askers are random, so a
   counter carries zero information, and a station at its own optimum has
   no reason to move. But "asking is a signal" is not the only mechanism
   that makes countering pay, and it may not be the main one.

## A2.1 Landlord behaviour must EMERGE from primitives

Delete the behavioural rules. Landlords differ **only** in these
primitives:

| Primitive | Institution | Mom-and-pop | Justification |
|---|---|---|---|
| Portfolio size | 200 habitats | 1–10 | definitional |
| **Risk aversion over cash flow** | ~risk-neutral | high | one vacancy is 0.5% of a 200-unit revenue line and 20% of a 5-unit one. **Derive the aversion from portfolio size; do not set it per type.** |
| **Comp precision** | market rent + small noise | market rent + large noise | no RM data, no comp set |
| **Face-rent capitalisation** | asset value = NOI × multiple | none (not marked to market) | a rent cut is capitalised; a cash concession is not |
| **Turn-cost scale economy** | lower per unit | higher per unit | in-house crew vs calling a contractor |
| Non-pecuniary tenant value | 0 | > 0 | a known tenant in a building you live near |

**The hypothesised causal chain — this is what we are testing, not
assuming:** risk aversion + bad comps ⇒ small pushes ⇒ **nothing to
concede.** If that holds, the ~90% no-concession figure is not stinginess;
it is an artefact of never having asked for much. That would be a genuine
explanation of a published statistic, which is the whole point.

### GATE 2 — emergence gate. Landlord-side, out-of-sample.

None of these may be a tuned parameter. All must fall out of the
primitives above:

- **V4:** share of mom-and-pop renewals with **zero increase** ∈ 10–30%
  (published: 18.0%)
- **V5:** share of mom-and-pop renewals granting **any concession** ≤ 20%
  (published: ~10%)
- **V6:** share of institutional renewals granting a concession ∈ 15–35%
  (published: 25.5%)
- **V7:** institutional mean push ≥ **3×** mom-and-pop mean push
  (published: +10.7% vs +2.1%)

**If V4–V7 emerge, the research angle is validated and the landlord-type
findings become real.** If they do not emerge, we report that our
primitives are insufficient to generate observed landlord behaviour —
which is itself a publishable negative and far more interesting than a
hardcoded paradox.

## A2.2 The four mechanisms Phase 1 omitted

Each is a separate arm so their contributions are separable. Each is a
real feature of how renewals actually work, not a patch to rescue a
result.

**Arm G — MENU COSTS / EXCEPTION QUEUE.** *(My prior: this is the biggest
omission.)* No property manager optimises every unit. They apply a
**default policy** and handle exceptions by hand. Countering moves you
from the default into the exception queue, where someone actually looks at
your file. So countering pays **without requiring any signal**, simply
because the default is not the optimum for you. Model: station applies a
blanket push; computes the true per-unit optimum only for units that
counter; exception capacity is finite.

**Arm H — INFORMATIVE ASKING (selection), with the twist.** Make the
propensity to counter correlate with genuine outside-option quality, so a
counter is informative and a rational station concedes to askers.
**Then test the thing Phase 1 implies but did not model:** a tool that
*refuses to advise asking when leverage is absent* produces a **better
signal** than random asking. Our "weak — just sign" verdict may be
economically load-bearing rather than merely honest. Compare three
populations at equal asker share: random askers, tool-advised askers
(asks only when leverage is real), and everyone-asks.

**Arm I — CONCESSIONS AS A SCREENING DEVICE.** Moving cost is private.
A station facing heterogeneous, unobservable moving costs has a classic
screening problem, and a concession offered only to those who ask is the
textbook separating instrument. In that world the station **wants** you to
counter. This flips the adversarial framing entirely and is the arm most
likely to explain the published 22% success rate.

**Arm J — PRINCIPAL–AGENT WEDGE.** The leasing agent is compensated on
occupancy or leases signed, not on NOI. So they concede more than the
owner would. Institution only (mom-and-pops are their own agent) — which
also predicts, without being told to, that concessions concentrate in
large portfolios.

## A2.3 Kill conditions

**K9 — our primitives cannot generate real landlord behaviour.**
*Fires if* GATE 2 (V4–V7) fails.
*Consequence:* published as a negative. The landlord-type paradox is
withdrawn from the article, and any claim that mom-and-pops behave
distinctively becomes an observation we cannot explain rather than one we
modelled.

**K10 — the mechanism is bureaucratic, not strategic.**
*Fires if* arm G alone reproduces the 22% success rate while arms H, I, J
add <5 percentage points each.
*Consequence:* the honest article is "countering works because nobody
looks at your file until you make them," which is a **better and much
less flattering** story than game theory. The tool's advice would then be
about being an exception, not about leverage.

**K11 — the walk-away floor is the product.**
*Fires if* in arm H tool-advised askers outperform random askers by ≥1% of
annual rent at equal asker share, AND the K8 externality shrinks.
*Consequence:* the "weak — just sign" verdict is reframed as the core
mechanism rather than a trust gesture, and it goes to the top of the page.
**This is the result I want; it therefore gets reported with the sharpest
available scepticism and a bug hunt before I believe it.**

**K12 — the landlord wants you to ask.**
*Fires if* arm I shows station cash flow **higher** with countering than
without.
*Consequence:* the adversarial framing comes out of the article entirely.
Countering would be participation in a screening mechanism the landlord
built on purpose, and describing it as beating them would be wrong.

## A2.4 Discipline

- GATE 2 is reported **before** any arm-G–J result.
- Arms G–J are reported **separately** before any combination, so no
  mechanism's contribution is hidden inside a stack.
- Phase 1's failure is not deleted or softened anywhere.
- If a result favours us, hunt for the bug before reporting it. K11 in
  particular.

---

# AMENDMENT 3 — it is not a swarm, and it is not our engine

*Appended 2026-07-25. Two structural defects found by inspection, not by
result-chasing. Both were true of the Phase 1/2 code as run.*

## A3.0 The two defects

**Defect 1 — we did not test our own product.** `grep` across
`research/crabs/` for `negotiate_bundle`, `plain_terms`, `logroll`,
`gametheory` returns **zero matches.** The negotiation is a bespoke DP
(`StationDP`) over hand-rolled ladders (`RANKED_LADDER`, `PRICE_LADDER`).

Consequence: **K1 ("the ranked-ask advice is decoration") fired against
our own reimplementation of ranked asks, not against the SNHP engine.**
That is a strawman of our own product. K1's verdict is therefore
**SUSPENDED, not overturned** — it must be re-run against the real engine,
and if it fires again it is binding and final. This is not an escape
hatch: a suspended kill that fires twice is worse for us than one that
fired once.

**Defect 2 — it is not a swarm.** Market rent is exogenous
(`market_path(...)` imposes it). Stations do not compete. Crabs cannot
move between stations (zero station-choice references). So it is a set of
independent bilateral negotiations against an imposed price path — which
is the same error the landlord hardcoding was: **we imposed the regime we
wanted to study instead of letting it emerge.**

## A3.1 Use the actual engine

Route every crab↔station negotiation through
`gametheory.negotiation.bundle.negotiate_bundle`:

```
negotiate_bundle(issues=[...], their_offers=..., my_priorities=...,
                 my_batna=..., their_batna_estimate=...,
                 cooperation=..., rounds_left=..., seed=...)
```

Each issue carries `options`, `my_utility`, `their_utility` (equal
lengths). The engine scores outcomes under both sides' priorities, infers
the counterparty's priorities from their offers, and returns the package
to propose plus the trade logic. **That inference step is the product.**

Issues, at minimum: `rent`, `term`, `one_time_credit`, `fees`. Both sides
get real utility vectors. Logrolling then either appears or doesn't —
which is the actual test.

## A3.2 Utility functions grounded in demographics, not taste

Draw agent utilities from distributions anchored to published
distributions rather than picked. Where a distribution is invented, label
it in code and in the results.

**Crab (tenant) — anchor to ACS/CHAS-style renter data:**
- income: lognormal fit to metro renter income
- rent burden: implied; the ~50% of renters who are cost-burdened get a
  steeper marginal utility of rent
- moving cost: correlated with income, household size and job flexibility
  — the real dispersion, not a constant
- priority weights over {rent, term, credit, fees}: Dirichlet, so
  heterogeneous preference intensity is a first-class input. **A tenant
  who values term over rent is what logrolling exists for; if no such
  tenants exist, logrolling cannot help and K1 should fire.**

**Station (landlord) — anchor to NAA/IREM cost structure:**
- per-unit turn cost, opex, and discount rate from the survey
- risk aversion derived from portfolio size (Amendment 2)
- face-rent capitalisation weight (institution only)
- priority weights: stations should value `rent` and `term` differently
  from tenants — that difference IS the logrolling surface

## A3.3 Make it a swarm — endogenise the market

The regime must emerge. Required:

- **Endogenous market rent** from vacancy and matching, not `market_path`.
  Stations post asking rents; searching crabs match; the observed "market
  rent" is a statistic of realised lets, not an input.
- **Crab mobility and search.** Leaving means entering a search pool and
  matching with some station, at a cost — not vanishing.
- **Station competition.** Stations set asking rents against observed
  local vacancy, so they compete for the search pool.
- **Local information only.** Crabs observe a neighbourhood of stations,
  not the true global market. Comp precision then falls out of who you can
  see rather than being a per-type parameter.

### GATE 3 — emergence of the regime

- **V8:** a supply shock (habitat completions) produces **gain-to-lease**
  endogenously — new-let rents fall below sitting rents — without being
  imposed.
- **V9:** in that state, the sign pattern of the MAA table appears in the
  aggregate: **new-let growth negative while renewal growth positive**, in
  the same period.
- **V10:** the exogenous-path model and the endogenous model agree on
  Phase-1 retention (±5pp) when the endogenous market happens to trace a
  similar path — a bridge check, so the two models are comparable.

**If V8/V9 fail, we cannot generate the 2026 phenomenon from primitives
and must say so.** The article's central empirical claim would then rest
entirely on the REIT filings, with no mechanism of our own — which is a
weaker but still honest position, and we state it that way.

## A3.4 Kills

**K13 — logrolling does nothing here.**
*Fires if,* with the real engine and heterogeneous Dirichlet priorities,
multi-issue bundling does not beat single-issue rent bargaining by ≥2% of
annual rent.
*Consequence:* binding and final. K1 confirmed, the ranked-ask claim comes
out of the article and the product for good, and we publish that our own
engine's central mechanism does not help in rent renewal.

**K14 — the engine is worse than the hand-rolled ladder.**
*Fires if* `negotiate_bundle` underperforms the Phase-1 `RANKED_LADDER` on
crab surplus.
*Consequence:* an engine defect, reported as such, and it blocks the
article until diagnosed. This is a real possibility and must not be
quietly dropped.

**K15 — the swarm changes nothing.**
*Fires if* endogenising the market moves no Phase-1 conclusion by more
than noise.
*Consequence:* good news for Phase 1's validity and a genuine finding —
report that bilateral models suffice for this question, and stop building
swarm machinery.

## A3.5 Discipline

- The re-run of K1 against the real engine is reported **before** K13.
- GATE 3 is reported before any endogenous-market arm result.
- Phase 1/2 results stay in `RESULTS.md` verbatim, with a pointer to this
  amendment noting that K1 was run against a reimplementation.
- Invented distributions are labelled in code AND in the results table.

---

# AMENDMENT 4 — the engine matrix: who is holding it?

*Appended 2026-07-25, before any Amendment-3 result exists.*

## A4.0 Why this is the sharpest test yet

Everything so far asked "does countering pay?" This asks **"what does our
engine do, and to whom?"** SNHP is a *symmetric* negotiation engine. It is
not a tenant-advocacy tool. Nothing in it prevents the other side from
using it.

And the commercial reality points the wrong way: **we sell to businesses
and their agents.** A property-management company is exactly the kind of
buyer we court; an individual renter is not. So "the landlord has SNHP" is
not a hypothetical — **it is the more probable commercial deployment**, and
we have never tested it.

Relevant prior from our own record, which sharpens the prediction: the
divorce demo's joint-surplus claim **died** (K2-surplus DEAD, deal-existence
only), and the arena read was that the multi-issue edge is real only in the
*joint*, cooperation-gated setting. So the pessimistic cells below are the
ones our own history predicts.

## A4.1 Arm K — the 2×2 engine matrix

Every cell uses the same world, same demographics, same seeds. The only
difference is who negotiates with `negotiate_bundle` and who uses a human
heuristic (single-issue anchoring, satisficing, no priority inference).

| | Landlord: heuristic | Landlord: SNHP |
|---|---|---|
| **Tenant: heuristic** | **N/N** — the world as it is | **N/L** — *the dangerous cell* |
| **Tenant: SNHP** | **T/N** — what we sell | **T/L** — the endgame |

Measured per cell, and reported per cell:
- tenant surplus, landlord surplus, and **joint surplus** (the one that
  matters most)
- **the split** — share of joint surplus each side captures
- **impasse / turnover rate** (turnover is pure deadweight: turn cost +
  vacancy, destroyed not transferred)
- endogenous market rent level and new-let vs renewal spread

## A4.2 Kills

**K16 — we arm the stronger side more than the weaker.**
*Fires if* the landlord's gain in **N/L** exceeds the tenant's gain in
**T/N** (each measured against N/N).
*Consequence:* SNHP is, on net, a technology that helps landlords more
than tenants in this domain — while our likelier customer is the landlord.
That must be published, and it becomes a real question about who we sell
to, not a footnote. **This is the finding I would least like and the one
the commercial structure most predicts.**

**K17 — it is an arms race, not value creation.**
*Fires if* joint surplus in **T/L** is within noise of joint surplus in
**N/N**.
*Consequence:* the honest pitch is "you need this because the other side
has it" — a defensive, rent-extracting product rather than a
value-creating one. Excellent for revenue, and we would have to say the
quiet part out loud. Our own divorce-demo history says this is the modal
outcome.

**K18 — mutual engines destroy value.**
*Fires if* **T/L** shows a higher impasse/turnover rate than **N/N** AND
lower joint surplus.
*Consequence:* two well-advised parties bargaining harder produce more
failed renewals, and turnover is deadweight. SNHP at scale would be net
value-destroying in rent. Published prominently, on the page.

**SURVIVES — and this would be the best available outcome:** joint surplus
in **T/L** materially exceeds **N/N**. Then the engine creates value rather
than redistributing it, logrolling genuinely finds Pareto improvements both
sides missed, and the honest product is *"give this to both sides"* — which
is a better business and a defensible one. If this holds, the tenant-only
framing in `writing/rent-no-source.md` is the wrong frame and the article
gets rewritten around joint gains.

## A4.3 Discipline

- Report **joint surplus first**, then the split. Reporting own-surplus
  first is how the +119% preference artefact happened before.
- N/N is the control and every comparison is against it.
- Impasse rate is reported in every cell, not just where it flatters us.
- If K16 fires, it goes in the article and on snhp.dev/rent. A tool that
  helps the counterparty more than the customer is a thing the customer is
  entitled to know before using it.

---

# AMENDMENT 5 — renewals vs new lets, and the walk-away asymmetry

*Appended 2026-07-25, before any Gate-3 result exists.*

## A5.0 The structural omission

Every arm so far modelled ONE negotiation type (renewal) and treated
walk-away as a symmetric threat. Both are wrong, and the error may be
generating the gate failure.

**Renewal.** Landlord's walk-away = full turn cost + vacancy + re-let risk
(~$2–4k plus days vacant). Tenant's walk-away = moving cost, which our own
calibration puts at a median **~$7,200**. **The tenant has more to lose
than the landlord.** This inverts the leverage framing the article was
built on, and it is arithmetic, not opinion.

**New let.** Both collapse. The landlord's turn cost is **already sunk** —
the habitat is empty and ready — so walking costs only one more vacancy
day. The prospective tenant is not moving out of a home; they are
comparing listings, so their BATNA is the **next-best listing**, which in a
soft market is strong.

**The prediction this generates:** a landlord price-discriminating on BATNA
quality gives concessions to new tenants (strong outside option) and
increases to renewing tenants (weak outside option) **in the same
building, in the same period.** That is the MAA −7.0% / +5.4% pattern, and
it would emerge from BATNA structure alone — no imposed regime required.

## A5.1 Model both negotiation types

Every station runs both channels each period:
- **RENEWAL** — sitting tenant. Tenant BATNA = −(moving cost + search cost)
  + expected rent at a matched alternative. Landlord BATNA = −(turn cost +
  E[vacancy days] × daily rent + re-let rent risk).
- **NEW LET** — searching tenant from the pool. Tenant BATNA = next-best
  visible listing (so it strengthens as vacancy rises). Landlord BATNA =
  −(one more vacancy day); **turn cost is sunk and must not be charged
  again** — a test should assert this.

Report both channels separately, always. Never pool them.

## A5.2 Make walk-away costs first-class and reported

In every cell, report both sides' walk-away cost and the resulting
bargaining zone, per channel. The zone width — not either side's cost
alone — is what predicts whether negotiation has room.

## A5.3 The commitment asymmetry

Separate from cost. A landlord applies a policy across many habitats;
conceding to one sets a precedent that leaks (the Phase-2 grapevine is
already the leak channel). A tenant is a one-off with no precedent to
protect. So the landlord's *effective* cost of conceding scales with
portfolio size even when the per-unit economics say concede. Model it;
do not assume its magnitude.

## A5.4 Kills

**K19 — the inversion is a BATNA artefact (this would be the best result
available).**
*Fires if* the new-let-negative / renewal-positive sign pattern emerges
from BATNA asymmetry alone, with no imposed regime.
*Consequence:* Gate 3's V9 is satisfied by mechanism rather than
imposition. The article can then stand on its own model instead of
borrowing the REIT filings, and the explanation — landlords
price-discriminate on outside-option quality — becomes the piece's
central claim.

**K20 — the tenant is the weaker party in renewals, and we said otherwise.**
*Fires if* mean tenant walk-away cost exceeds mean landlord walk-away cost
in the RENEWAL channel.
*Consequence:* the "you have leverage" framing is **backwards** and comes
out of the article and the product entirely, replaced by the narrow
case where a tenant genuinely does have leverage. Given moving cost
~$7,200 vs turn cost ~$3,000, I expect this to fire, and if it does the
tool's copy needs rewriting, not softening.

**K21 — for some tenants the right advice is "move", not "negotiate".**
*Fires if* tenants in the NEW-LET channel systematically achieve better
terms than comparable tenants in the RENEWAL channel by ≥2% of annual
rent.
*Consequence:* the tool must tell low-moving-cost tenants in soft markets
that **leaving beats negotiating**, and say so as plainly as it currently
says "just sign." A tool that only ever advises negotiating is selling its
own mechanism rather than advising the user.

## A5.5 Discipline

- Channels reported separately, never pooled.
- Walk-away costs and zone widths reported in every cell.
- The sunk-turn-cost rule in the new-let channel is asserted by a test.
- K20 is expected to fire. If it does not, check for a bug before
  believing it — the raw parameters say it should.

---

# AMENDMENT 5a — CORRECTION to A5.0: vacancy is a flow, not a sunk cost

*Appended 2026-07-25, before any Amendment-5 result exists. This corrects an
error in A5.0 written hours earlier. The original text is left in place
above; this supersedes it.*

## A5a.1 The error

A5.0 said the landlord's turn cost is "already sunk" in the new-let
channel, so walking away costs "one more vacancy day." That conflates two
costs with opposite time structure:

1. **Make-ready** (clean, paint, repair, list, screen) — one-time. Once
   paid, genuinely sunk.
2. **Vacancy loss** — lost rent per period the habitat sits empty. **A
   flow that accumulates.** The opposite of sunk.

Only (1) is sunk. (2) is the larger component, and walking away from a
prospective tenant costs the landlord **E[remaining vacancy] × rent** —
roughly 1–1.5 months at commonly cited 30–41 day let times, not a day.

## A5a.2 The asymmetry inverts between channels

| Channel | Landlord walk-away | Tenant walk-away | Weaker party |
|---|---|---|---|
| **RENEWAL** | make-ready + E[vacancy] | moving cost (~$7,200 median) | **tenant** |
| **NEW LET** | E[vacancy until next match] — substantial | cost of viewing the next listing — trivial | **landlord** |

**This is a cleaner mechanism for the MAA spread than A5.0's.** Landlords
concede to newcomers because they are the weak party in that channel;
they raise on renewals because the sitting tenant is. Same building, same
period, opposite sides of the table — from walk-away structure alone, with
no imposed regime and no preference-based discrimination required.

Replace A5.1's new-let landlord BATNA accordingly: **not** one vacancy day,
but expected remaining vacancy given local search conditions. It must
respond to vacancy — a test should assert that a station facing higher
local vacancy has a *worse* new-let BATNA.

## A5a.3 The deadline asymmetry (new, and the sharpest part)

Vacancy accumulating per period means **the landlord's BATNA deteriorates
as a negotiation drags, while the tenant's is flat.** That is an
asymmetric-deadline bargaining structure. `negotiate_bundle` accepts
`rounds_left`, so the engine can in principle exploit it — which makes this
a test of the product, not just of the world.

Model: carry days-on-market as state; the landlord's reservation must
weaken monotonically in it.

**K22 — concession depth rises with time-on-market.**
*Fires (i.e. confirms) if* mean concession depth in the new-let channel
increases monotonically with days-on-market at the time of agreement.
*Consequence if it does NOT hold:* our vacancy accounting is wrong, since
this is close to an accounting identity once vacancy is a flow. Treat
failure as a bug signal before treating it as a finding.
*Weak external consistency check:* published concession depth is greater in
Class C (23.4%) than Class A (13.2%), and Class C sits in longer-vacancy
segments. Directionally consistent; not proof.

**K23 — the engine exploits the deadline asymmetry.**
*Fires if* a tenant negotiator given true `rounds_left`/days-on-market
state does NOT outperform one blind to it by ≥1% of annual rent in the
new-let channel.
*Consequence:* the timing information in the engine's interface is inert
in this domain, and any product copy implying that timing your ask matters
must be dropped.

## A5a.4 Consequence for A5.2 and K20

K20 (tenant weaker in renewals) is unchanged and still expected to fire.
But the reported bargaining-zone width must now use the corrected
new-let landlord BATNA, and the zone must be reported **per channel and as
a function of days-on-market**, not as a single scalar.

---

# AMENDMENT 6 — elastic demand, and a stopping rule

*Appended 2026-07-25. Gates 1 and 3 have failed; Gate 2 is unrun. This
amendment fixes one identified structural defect and pre-commits to when
we stop.*

## A6.0 Corrections to the record

**My K20 magnitude was wrong.** I claimed the renewal tenant has "more
than twice as much to lose," comparing a ~$7,200 move to a ~$3,000
make-ready. The landlord's renewal walk-away is make-ready **plus expected
vacancy plus re-let rent risk**. Measured against that total the ratio is
**1.08×** (robust at 1.06–1.39× across specifications). K20's direction
holds; its magnitude does not. Honest statement: **the tenant is somewhat
the weaker party in renewals, not dramatically so.** Any copy implying a
large asymmetry is unsupported.

**Pattern worth recording:** three errors in this domain, all in the
direction of a sharper story — leverage exists (wrong sign), turn cost is
sunk (wrong time structure), tenant is 2.4× weaker (wrong denominator).
The bias is consistent and it is mine.

**K19 fired only under a defect.** The renewal offer was built from each
tenant's *private* moving cost — price discrimination on unobservable
information. Corrected, renewal growth goes +1.13% → −0.64% and K19 does
not fire. The result we most wanted was manufactured by our own bug, and
it was caught internally.

## A6.1 The identified defect: no demand curve

The market deflates to a floor ($2,000 → ~$524) because **nothing brings
searchers in as rents fall.** I specified a search pool and never
specified elastic demand. Asks ratchet down with no anchor,
`E[remaining vacancy]` pins at its cap, and the landlord's reservation
collapses to zero — which also makes K22 unreadable.

**Required:** searcher inflow must respond to the price level. As rents
fall relative to a reference income/rent level, more crabs enter the
market (from outside, from doubling-up, from delayed household
formation); as rents rise, fewer. Elasticity is a declared parameter with
a pre-declared range, not tuned to make a gate pass.

- **Assert by test:** a price-level fall increases searcher inflow, and the
  market clears at an interior price rather than at a floor.
- The test currently pinning the *defective* deflation is replaced, not
  deleted, and the replacement is noted in `RESULTS.md`.

## A6.2 GATE 3 re-run (unchanged bars)

V8/V9/V10 exactly as written in A3.3. No loosening. A gate whose bar moves
after a failure is not a gate.

## A6.3 STOPPING RULE — pre-committed

**If GATE 3 fails again with elastic demand, we stop building.** No fourth
mechanism, no fifth amendment in search of a pass.

The write-up then reports, as the primary finding: *we could not build a
model that reproduces the 2026 renewal/new-let inversion from primitives,
across three gate attempts and six mechanisms.* The article's empirical
claim rests on the REIT filings alone, stated plainly, with no mechanism of
our own — and the simulation's contribution is limited to what did survive:

- the engine result (K13/K14 did not fire — multi-issue bundling beats
  single-issue by ~2× the bar, and beats our own hand-rolled ladder, by
  finding deals rather than extracting harder)
- the value-split result (**K16 fired** — whoever holds the engine captures
  ~90%; the landlord is our likelier customer)
- the externality result (**K3, K8 fired** — non-askers absorb the cost)
- the direction of the renewal asymmetry (**K20 fired**, magnitude small)
- the narrow "moving beats negotiating" group (~1 in 6 of the
  cheapest-to-move quartile)

That is a real, publishable set of findings and a real, publishable
failure. Grinding for a pass would convert the second into a fabrication.

## A6.4 Remaining unrun work, and its priority

If Gate 3 passes: run GATE 2 (V4–V7, emergence of landlord behaviour) and
arms G–J, then re-decide K22/K23 on a stable price level.
If Gate 3 fails: run GATE 2 anyway — it is landlord-side and independent
of the market's price level — then stop. K22/K23 remain undecided and are
reported as such.

---

# AMENDMENT 6a — CORRECTION: the tenant's clock is a cliff, not a flat line

*Appended 2026-07-25, before any Amendment-6 result. Corrects A5a.3.*

## A6a.1 The error

A5a.3 said "the landlord's BATNA deteriorates as a negotiation drags,
while the tenant's is flat." **The tenant's is not flat.** A renewing
tenant must secure housing *before* the lease ends. Missing that date does
not cost "another month of searching" — it costs temporary housing,
storage, emergency moving at whatever is available, or a holdover tenancy
at a penalty rent.

**Fourth error in this domain, same direction: I keep understating the
tenant's disadvantage.** Recorded, not hidden.

## A6a.2 The clocks have different SHAPES — this is the substantive point

| | Landlord | Renewing tenant |
|---|---|---|
| Cost of delay | **linear**: one month's rent per vacant month | **flat, then a cliff** at lease expiry |
| Effective deadline | none — accrual continues indefinitely | **earlier than lease end**, because search → apply → approve → move needs lead time |
| Shape | smooth | convex / discontinuous |

So the landlord's stronger renewal position does not come from a higher
walk-away *level* (K20 measured only 1.08×). It comes from **shape**: a
linear clock beats a clock that ends in a wall, and the tenant's wall
arrives first.

> **CORRECTED 2026-07-25.** Two errors in the sentence above. (1) **1.08× is
> stale** — the shipped `results_market.json` gives **1.474×**, reproduced
> exactly on re-run; RESULTS Phase 5 §3's table predates a later change. (2)
> More seriously, AMENDMENT 10 finds the *sign* of that ratio is not
> determined: it crosses 1.0 at a physical-move cost of **$1,028–$3,624**
> depending on the regime and on `RELET_RISK_ON`, an un-ablated hardcoded
> `True`, and the defensible band for that cost from published sources is
> **$700–$3,300**. So "the landlord's stronger renewal position" is not
> established at the level either. What survives of A6a is the claim about
> **shape**, which does not depend on the level ordering.

In the new-let channel this reverses cleanly: the searching tenant is
already housed and under no deadline, while the landlord accrues vacancy
every period.

## A6a.3 Why this may be the mechanism V9 needs

The renewal ratchet plus the new-let concession may fall out of **deadline
shape alone, under fully symmetric information** — no private-information
price discrimination, which is precisely what the K19-killing bug was
counterfeiting.

**Model requirements:**
- Carry **periods-to-lease-end** as tenant state; the tenant's
  continuation value must fall convexly in it, with a discrete penalty for
  crossing expiry unhoused (holdover premium + emergency-move cost).
- Tenant's effective deadline = lease end **minus** required lead time
  (search + application + approval + move), drawn from a declared
  distribution.
- Landlord's clock stays linear in vacant periods. Do not give it a cliff.
- Information stays symmetric. The landlord may use population
  distributions and observables (tenure, lease-end date — it knows the
  lease) but **never a tenant's realised private draw.** A test must
  assert this, given how K19 was manufactured.

## A6a.4 Kills

**K24 — deadline shape generates the inversion.**
*Fires (confirms) if* the new-let-negative / renewal-positive sign pattern
emerges from deadline structure under **symmetric information**, no
private draws.
*Consequence:* V9 passes on the cleanest possible grounds, and the
article's central claim gets a mechanism of our own. **This is now the
most likely route to a Gate-3 pass, and therefore the one most in need of
a bug hunt if it fires.** The last time a route to V9 fired it was a leak.

**K25 — the tenant's position decays with the clock.**
*Fires (confirms) if* tenant outcomes worsen monotonically in
periods-elapsed-since-offer, holding all else equal.
*Consequence if confirmed:* "negotiate early, and never let the response
window lapse while negotiating" becomes economically load-bearing advice
rather than procedural, and moves up the page. It also grounds the NYC
60-day RTP-8 warning already in the tool.

**K26 — securing an alternative first is the highest-value move.** *(The
one with the biggest product consequence.)*
*Fires (confirms) if* a tenant who has secured an alternative before
countering — thereby flattening their cliff into a floor — achieves
outcomes better by ≥2% of annual rent than an identical tenant who has
not.
*Consequence if confirmed:* this becomes the tool's **first** piece of
advice, ahead of every ask in the ladder. "Go get one real alternative
before you send anything" would then be worth more than the entire ranked
ask list, which would be an uncomfortable and useful finding about our own
product.
*If it does NOT confirm:* say so, and drop any implication that shopping
around helps.

## A6a.5 Interaction with the stopping rule

A6.3's stopping rule stands, with one amendment: deadline shape (this
amendment) is folded into the **same** Gate-3 attempt as elastic demand,
not treated as a seventh mechanism warranting a further attempt. If that
combined attempt fails V9, we stop as committed.

---

# AMENDMENT 7 — the renewal cap is circular (found by inspection, 2026-07-25)

`world.py:77` sets `renewal_cap = 0.12`, an imposed ceiling on what a
station will ask at renewal. SPEC.md justifies it: *"2022 renewals averaged
+10.7% while asking rents rose faster; caps are why loss-to-lease
persists."*

**That is an observed OUTCOME installed as a hard CONSTRAINT.** And it
double-counts: the model already prices elasticity, so a station's
restraint at renewal should EMERGE from the risk of the tenant leaving. We
bolted restraint on top of a mechanism that was supposed to generate it.

**Consequence, applied immediately:** the AI-migration result ("the boom
helps incumbents because renewal caps stop their rent chasing the market")
is withdrawn from the article. Its stated mechanism reduces to "the cap we
imposed did what we imposed it to do." Not tested unbounded, and not
worth testing in that form — the claim is unpublishable either way.

The crab-flu result is unaffected: the cap binds *increases*, and that
finding is about a station declining to *cut* into a falling market.

Class: same as the six the audit found. Seventh. Found by reading the
prose, not the code — which is worth noting as a detection method.

**If the simulation is ever revived:** derive the renewal ceiling from
elasticity plus any explicit regulation, and check whether the observed
~10.7% average falls out. That is the honest version of this parameter,
and it is a real experiment rather than an assumption.

---

# AMENDMENT 7 — RESULT (2026-07-25)

**Elasticity alone gives +13.81%. Observed is +10.7%. It does NOT fall out**
— the free station overshoots by 3.1pp (29% relative). But it does not run
to market either: retention falls only 60.1% → 56.1%. **Elasticity generates
~3/4 of the restraint the world shows; something else supplies the rest.**

- **Derived self-imposed ceiling: ~31%.** Caps of 0.50 and 2.00 are
  bit-identical; the highest push the free station ever chooses is +30.78%.
- **In the gain regime the shipped cap never bound** (0.0% at cap).
  Restraint in a falling market was already fully endogenous.
- **The cap changed the KIND of policy.** Free, the station targets a
  *level* (≈1.087× market; sd level 1.75pp / sd push 4.68pp). Capped, that
  inverts (4.32 / 1.72). The study then read the push back out as a match
  to +10.7%.
- **You can have either observed fact, not both.** Capped: push +10.73% ✓,
  retention 60.1% ✗. Free: push +13.81% ✗, retention 56.1% ✓.
- **No endogenous loss-to-lease.** Only a 6% cap reproduces renewals
  pricing *below* a new let. SPEC's "caps are why loss-to-lease persists"
  is literally true, which is what made it circular.
- **Ablation: tenant switching cost is the mechanism.** ±elastic moves the
  push −5.2pp / +13.4pp; deleting the landlord's ENTIRE cost of losing a
  tenant moves it +3.2pp. **The landlord's turnover cost was never the
  operative variable** — which retires the article's original premise at
  the root, not just its arithmetic.
- Side effect: lifting the cap takes loss-regime counter-success
  0.04% → 43.3%. Gate 1's "the station concedes to nobody" was partly the
  cap. (Gain regime unaffected; GATE 2's V5/V6 justification stands.)
- Welfare: removing the cap moves ~$460/yr tenant → landlord and burns
  ~$275/yr more in turnover.

## Two more circular parameters (Principle C sweep)

| parameter | its own stated basis |
|---|---|
| `p_continue = 0.60` | *"Without this, RANKED nests PRICE and **K1 could not fire**"* |
| `courage_med = 0.18` | *"Set so the endogenous counter rate lands near the **observed 39%**"* |

`p_continue` is the worst artefact in the study: **a parameter chosen so
that a kill condition would be capable of firing.** Both are swept, which
mitigates but does not cure — the headline value was still selected for
what it produces.

## Also found, and unfixed

- **Two more information leaks**, both landlord-side: `armk.landlord_opener`
  (inside the arm K16's 8.5× is measured on) and
  `engine_bridge.station_counter` (K13–K15). Both read the tenant's private
  Dirichlet weights and job flexibility via `welfare_premium` /
  `issue_dollars` — first-degree discrimination on unobservables. The
  declared budget is written in the *neighbouring* function's docstring.
- **K16's 2×2 differs in 8 undeclared dimensions.** Even N/N vs T/N is
  confounded: round count is a function of `tenant_engine` (2 vs 3).
- **Mismatched ratios** — numerator over survivors, denominator over
  everyone: under K25's $645, K26's $17, `rent_ratio`'s "12% above market",
  and the denominator of V9/K19/K24.
- **13 unablated mechanism claims in RESULTS.md; 11 favour a more
  interesting story.** Including K3/K8's "the landlord cannot see who
  reads our page", which is supported by a test *asserting* it. The page
  now carries that caveat.

---

# AMENDMENT 8 — switching cost should be an OUTPUT, not an input

*Appended 2026-07-25, after A7. Raised by the founder reading the A7
ablation table.*

## A8.0 Scope note on the stopping rule

A6.3 stopped *building mechanisms* after Gate 3 failed, and that stands.
This is a **defect fix**, the same class as A7: a parameter that should
never have been a parameter. It is explicitly **not** an attempt to pass
Gate 3. If Gate 3 happens to pass under it, that is a suspicious result
requiring the full bug hunt before it is believed, not a vindication.

## A8.1 The defect

`world.py:100` sets `move_med = 3.6` months. SPEC §4's stated basis:
**"calibrated to observed elasticity — see §8."**

The A7 ablation then found switching cost is the *dominant* variable:

| perturbation | Δ mean push |
|---|---|
| switching cost 3.6 → 0.36 months | **−5.2pp** |
| switching cost 3.6 → 12 months | **+13.4pp** |
| delete the landlord's ENTIRE cost of losing a tenant | +3.2pp |
| face-rent capitalisation → 0 | −0.4pp |

So: we tuned it to reproduce observed elasticity, discovered it drives the
push, and reported the push. Circular in the same way as `renewal_cap`,
and **4× more load-bearing** (13.4pp vs 3.1pp).

It is honestly labelled CALIBRATED in SPEC §8, which correctly forbids
claiming V2 as a prediction. That is not the problem. **The problem is
that it is a parameter at all.**

## A8.2 It should fall out of search, and half the machinery exists

`market.py` already prices search and never connects it to switching cost:

```
search_cost  0.25 months ($500)   viewings, applications, time
app_cost     0.08 months ($160)   switching between listings
k_visible    5                    listings a searcher can see
```

~$660 of modelled search, beside a separately-drawn $7,200 switching cost.
Two numbers describing overlapping things, not speaking.

**Derive it.** A crab that wants to leave enters the pool, views what it
can see, applies, may be rejected, and eventually matches. Its switching
cost is then the *realised* cost of that process:

```
switching cost = E[viewings until an acceptable match] x viewing cost
               + P(rejection) x redo cost
               + physical move (movers, deposits, broker fee)
               + holding/time cost of the search
               + attachment (the only genuinely psychological term)
```

Only the last term stays a free parameter, and it should be small.

## A8.3 The consequence that makes this worth running

**Switching cost becomes endogenous to market tightness.** Tight market →
few visible listings, more rejections, longer search → leaving is
expensive → tenants inelastic → the station pushes harder. Soft market →
the reverse.

That is the regime dependence the study spent three gates trying to
produce and **imposed as exogenous drift instead** (`REGIMES`). If it
falls out of search frictions, the loss/gain regimes stop being an input.

It would also unify two findings that are currently bolted on:
- **K20** (the tenant is the weaker party at renewal) is *entirely* this
  parameter, so its 1.08× is currently a restatement of `move_med`.
- **K26** (proving an alternative is worth ~10%) becomes mechanical rather
  than added: a crab that has *secured* an alternative has already paid
  the search cost, so its switching cost is genuinely lower, and the
  signal is credible because it is *costly*, not because we declared it so.

## A8.4 What to report

1. **The derived switching-cost distribution** vs the drawn lognormal
   (median 3.6 months / $7,200). Does the calibrated value fall out?
2. **Does it vary with tightness in the right direction, and by how much?**
3. **Re-run the A7 free-cap push** on derived costs. Does the +13.81%
   move toward the observed +10.7%?
4. **Re-check K20 and K26** — both should now be mechanical consequences.
5. **Gate 3 V8/V9/V10 once more.** Reported, not chased. A pass here is a
   suspicious result before it is a good one.

## A8.5 Kill

**K27 — search does not generate the calibrated switching cost.**
*Fires if* the derived median lands outside 1.8–7.2 months (a factor of two
either side of the calibrated 3.6).
*Consequence:* published as a negative. It would mean the ~$7,200 figure
cannot be built out of the search frictions we can name, and the honest
position is that we do not know where tenant switching costs come from —
which, given it is the dominant variable in renewal pricing, is a more
interesting statement than most of what survived this study.

---

# AMENDMENT 9 — the costly-verifiable-signal arm was built, tested, and never run

*Appended 2026-07-25, before any signal-arm output existed. The kills in
§A9.4 are fixed here and are stated on OUTPUTS.*

## A9.1 The finding

`market.py` implements a costly verifiable signal — `_signal_proved()`,
`MarketParams.signal_enabled`, `signal_cost = 0.10` — and
`test_crabs.py:1027-1069` asserts four properties of it. **No cell in
`run_market.py` ever sets `signal_enabled`.** The K26 cell (`a6a_secured`)
runs with the channel OFF. So the arm has unit tests and no results: it is
absent from `results_market.json` and from RESULTS.md, whose final section
records K26 as DOES NOT CONFIRM (+$17 against a $480 bar).

Meanwhile `writing/crab-landlord-article.md` leads a section with **"10.2%
off the offer"**, attributed to this mechanism. That number is traceable to
no run in this repository. Either it exists somewhere not found, or it is
unsupported. This amendment settles it.

## A9.2 The mechanism the code actually implements

`market.py:450-468`, verbatim structure:

```
wa_t_base = (p.move_med + attach(j) + SEARCH_COST) * M_obs
if proved:              wa_t_exp = wa_t_base            # <-- flat
elif deadline_shape:    wa_t_exp = <convex clock + cliff>
else:                   wa_t_exp = wa_t_base            # <-- flat
```

`proved` and `deadline_shape = False` evaluate to the **same expression**.
`wa_t_base` is built from the POPULATION `p.move_med` and is identical for
provers and non-provers. So proving an alternative does not reveal anything
about *this* tenant's alternative. Its entire direct effect is to move the
tenant out of the cliff branch.

**Prediction recorded before running** (the SPEC-A2 §A2-2 discipline): the
direct channel with `deadline_shape = False` is *exactly* zero by
inspection, so K29 should fire. Any non-zero residual there is
general-equilibrium spillover — provers pay less, which moves realised
rents and hence the market statistic everyone is priced against — not a
second channel. Recording this so that the ablation either confirms it or
contradicts it, rather than being read off afterwards.

If that is right, the honest headline is **"proving it removes your
deadline penalty"**, not "proving it reveals your alternative" — and the
finding is then the same family as artefact #3 ("it's the shape of the
deadline", which turned out to be 87% level), i.e. K25's cliff measured a
second time under another name.

## A9.3 What is run

One knob against `a6a_secured` (DESIGN-PRINCIPLES A), drift 0.0, the same
30 seeds, geometry unchanged:

- `signal_enabled = True` at `signal_cost` ∈ {0.05, 0.10, 0.20, 0.40}
- each of those crossed with `deadline_shape` ∈ {True, False} — the ablation
- each of those at `move_med` ∈ {3.6 (calibrated), whatever A8 derives},
  because `move_med` enters `wa_t_base` directly and is the parameter
  AMENDMENT 8 is testing
- confirmation that every previously reported cell is **bit-identical** with
  the signal off

Reported: offer ÷ market and surplus for proved, unproved, and the
`a6a_secured` baseline.

## A9.4 Kills, fixed before the first run, both bidirectional

**K28 — the article's headline is unsupported.**
*FIRES if* the proved-vs-unproved gap in offer ÷ market is **under 2% of
market** at every `signal_cost`.
*Consequence if it fires:* "10.2% off the offer" is unsupported by anything
in this repository and comes out of the article.
*If it does NOT fire:* the arm supports a real effect, its size is reported
at each `signal_cost`, and the article's number must be restated as
whatever the run actually gives — a match to 10.2% would itself need
explaining, since no run producing it exists.

**K29 — the effect is the clock, not the alternative.**
*FIRES if* the gap with `deadline_shape = False` is **under 40% of** the gap
with it on.
*Consequence if it fires:* the article's stated mechanism is refuted. The
honest description is that proving an alternative removes the tenant's
deadline penalty, which is K25's cliff under a second name, and the claim
that it *reveals an alternative* is withdrawn.
*If it does NOT fire:* the signal carries information beyond the clock,
which would be a genuine second channel — and, given §A9.2 says the code
has no such channel, would mean the code does something we have not
understood and needs a bug hunt before the result is believed.

## A9.5 Discipline

The signal arm's default stays OFF, so nothing previously reported moves.
No parameter is tuned to K28 or K29. `signal_cost` is swept because SPEC
already declared it swept, not because a sweep was needed to find a value
that works.

---

# AMENDMENT 10 — is the renewal asymmetry real, or is its sign a free parameter?

*Appended 2026-07-25, before any A10 output existed. §A10.2's band was fixed
from published sources BEFORE the sweep was run. K30 is stated on outputs.*

## A10.1 Why this is the most important open question in the study

`writing/crab-landlord-article.md` opens on the folk arithmetic — "they risk
five months to gain two, you have leverage and nobody told you" — shows the
"1-3 months" figure has no source, and then reverses it: you do not have
leverage, the tenant is the weaker party. **K20 is the spine of the article.**

AMENDMENT 8 found the reversal moves with a circular parameter:

| `move_med` | wa_tenant / wa_landlord | K20 |
|---|---|---|
| 3.60 (calibrated to observed elasticity) | 1.474 | FIRES — tenant weaker |
| 1.48 (derived from search, A8) | 0.892 | does NOT fire — LANDLORD weaker |

So the crossing lies between. The question is whether it lies inside or outside
the range a careful person could defend for the one input that moves it.

**Full disclosure of what is already known before this amendment runs:** A8's
existing cells bracket the crossing between `MOVE_PHYSICAL` 1.0 and 3.1. What is
NOT known, and what §A10.2 fixes from sources without reference to that
bracket, is the defensible band for `MOVE_PHYSICAL` itself.

## A10.2 The declared band, fixed from sources before the sweep

Evidence base for the physical cost of a local move by a US renter of a 1-2
bedroom, established 2026-07-25:

| source | figure | type |
|---|---|---|
| HireAHelper cost methodology, 2024 data | 2BR local full-service **$984**; labor-only $383 | **completed bookings** (transaction data) |
| This Old House 2025 Moving Survey (n=1,000) | local moves **$1,489** | consumer survey |
| Move.org State of Moving (n=2,500, Jan 2025) | 2BR under 400mi **$2,750** | consumer survey, **median** |
| moveBuddha, Jul 2026 | 2BR apt local **$725**; range $301-$3,512 | quote aggregation |
| ancillary (supplies, cleaning, utility connection) | $300-$800 | **no survey basis — marketing content** |

Three facts that set the endpoints:

1. **~60% of moves are DIY**, and only 15-38% are full-service (Move.org
   62/38; AHS 2026 n=1,004: 53% self-pack-and-drive, 15% full-service). A
   population-average move is weighted toward DIY, which is why survey averages
   sit far below any full-service quote.
2. **No government statistic exists.** Census publishes move *rates*, BLS
   publishes a price *index*. Nobody official publishes the dollar cost.
3. **The most-cited number in this space is unusable.** "AMSA $2,300" comes
   from a body absorbed into the ATA in December 2020, appears with three
   mutually inconsistent values ($1,250 / $1,700 / $2,300), and has no reachable
   dated primary document.

**DECLARED BAND: `MOVE_PHYSICAL` ∈ [0.35, 1.65] months ($700-$3,300)**, being
the physical move ($400-$2,500) plus ancillary ($300-$800). **Central
[0.70, 1.00] months ($1,400-$2,000).** The band is wide because the evidence is
weak, and it is declared wide *before* the sweep for exactly that reason.

Recorded correction to A8: `BROKER_SHARE = 0.15` is **too high**. Tenant-paid
broker fees were standard practice in NYC and Boston only, and both were legally
curtailed in mid-2025 (NYC FARE Act, 11 Jun 2025; Massachusetts, ~1 Aug 2025).
The national value is ~0. It does not move any median reported here (a 15%
share cannot), so nothing is re-run; the declared value is corrected and the
NYC/Boston case becomes an explicit scenario rather than a national average.

## A10.3 What is swept

`wa_tenant / wa_landlord` in the RENEWAL channel, over:

- `MOVE_PHYSICAL` ∈ {0.0, 0.35, 0.5, 0.7, 1.0, 1.25, 1.65, 2.0, 2.5, 3.1},
  entering as `move_med = 0.48 + MOVE_PHYSICAL` (A8's derivation: spell
  overhead 0.25 + one viewing 0.08 + one month of search 0.15)
- `RELET_RISK_ON` ∈ {True, False} — **never previously ablated.** It is a
  hardcoded `True` in `market.py` and appears in no reported cell as a
  variable, yet it sits in K20's denominator: `wa_land = turn + vacancy +
  max(0, 12*(rent - M_relet))`. And `vacancy` is itself CIRCULAR (SPEC §5 sets
  relet months from the observed 39.7% concession rate), so K20 as shipped is
  a fitted numerator over a fitted denominator.
- drift ∈ {0.0, +0.09 (loss-like), −0.06 (gain-like)}

Also carried forward: does A8's **endogenous loss-to-lease** (free-cap offer
0.990 of market, which A7 said the model could not produce at all) survive the
same band, and does it live only on one side of the crossing?

## A10.4 K30, fixed before the first run, three-way and bidirectional

**K30 — the sign of the renewal asymmetry is a free parameter.**

*FIRES if* the value of `MOVE_PHYSICAL` at which `wa_tenant/wa_landlord`
crosses 1.0 falls **inside the declared band [0.35, 1.65]**, in either
`RELET_RISK_ON` state.
*Consequence if it fires:* **we cannot tell who is the weaker party at
renewal, and neither can anyone else**, because the answer turns on a number
that has no government statistic, whose most-cited source is unusable, and
whose best two sources disagree by 1.5×. K20's verdict is withdrawn as
undetermined — not reversed — and the article's reversal must be restated as
"nobody knows, including the people telling you that you have leverage."

*Does NOT fire, ratio > 1 across the whole band:* **K20 survives derivation.**
The reversal stands and the article's spine holds.

*Does NOT fire, ratio < 1 across the whole band:* **the reversal was itself the
artefact.** The tenant is the stronger party at renewal, the folk arithmetic
was closer to right than we were, and the article is wrong in the direction it
was most confident about.

**This amendment's author expects K30 to fire, and that is the most publishable
of the three outcomes, which is exactly why DESIGN-PRINCIPLES E applies with
full force: if it fires, hunt for the bug before believing it.** Specifically,
check that the crossing is not an artefact of the `move_med` → `wa_tenant`
mapping being linear while `wa_land` is nearly constant, which would make the
crossing a trivial restatement of the two levels rather than a finding.

## A10.5 Discipline

`RELET_RISK_ON` is ablated, not removed. No value in §A10.2 was chosen after
seeing a ratio. The article is not edited under this amendment.

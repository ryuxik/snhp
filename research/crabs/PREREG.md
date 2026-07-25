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

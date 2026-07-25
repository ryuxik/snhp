# Experiment design principles

*Derived 2026-07-25 from the seven artefacts the crab study produced, not
from a textbook. Each principle names the specific failure it would have
caught. Binding on any future simulation in this repo.*

## Why this exists

The crab rent study pre-registered 26 kill conditions, ran three
validation gates, and was audited adversarially. It still produced **seven
artefacts**.

*Corrected 2026-07-25.* This section previously said pre-registration
caught none of them. That was wrong, and it contradicted three other
places in the repo (RESULTS.md line 79, `principles.py`'s docstring,
`test_crabs.py:1115`, all of which say five of seven survived it).
Pre-registration caught **roughly two**, and precisely the two it was
aimed at: the SPEC-A2 §A2-6 guard that caught K11's selection effect, and
the A6a.4-mandated bug hunt that found the shape/level error.

**Five survived it**, because pre-registration constrains what you
*claim*, not what you *build*. Each of the five was a construction error
found later by inspection or ablation. That is the real lesson, and it is
sharper than the overstatement was: pre-registration works, on exactly the
failure modes you thought of in advance, and not one step further.

(Separately, two published findings were corrected live after shipping to
users — K25's dollar figure and K26's reversal. Neither is a member of the
seven; do not conflate the two counts.)

So the failure mode is not dishonesty about results. It is **building the
answer into the apparatus and then reading it back out.**

The seven, sorted by family:

| # | Artefact | Family |
|---|---|---|
| 1 | Reply-only landlord hid K16 (+$3 instead of +$2,642) | A |
| 6 | K16's 8.5×: landlord got brute-force search, tenant got the engine | A |
| 2 | Renewal offer built from the tenant's *private* moving cost | B |
| 3 | "It's the shape of the deadline" (was 87% level) | C |
| 7 | `renewal_cap = 0.12`, justified by the average it explains | C |
| 4 | Tool worth +$3,700/yr per-asker, −$244 on an identical population | D |
| 5 | K21 quartiles measured only tenants who stayed | D |

---

## A. One knob

**Any two arms being compared must differ in exactly one declared
dimension.** Everything else — action space, move order, number of
rounds, choice algorithm, information — must be identical.

*Would have caught #1 and #6.* K16 compared "who holds the engine" while
also varying the optimiser (brute-force enumeration vs `negotiate_bundle`),
the move order (opener vs replier), and the action grid (a rent range the
tenant was forbidden). Three confounds wearing one label.

**Enforcement:** arms declare their config as data; a test diffs any two
compared arms and fails if more than the declared treatment differs.

## B. Information budget

**Every agent has an explicit, declared observation set. Anything outside
it is a bug, not a modelling choice.**

*Would have caught #2.* The station priced renewals off each tenant's
private moving cost — price discrimination on a number no landlord can
see. It manufactured the exact result we most wanted.

**Enforcement:** a test greps the decision-making code path for any symbol
outside the declared set. We wrote one after the fact
(`test_renewal_offer_uses_no_private_tenant_draw`); it should exist for
every agent, from the start.

## C. No parameter may encode a finding

**A constant's justification may not be the phenomenon under study.** If
the source for a number is the outcome it produces, it is circular and the
result is unpublishable however it comes out.

*Would have caught #7.* `renewal_cap = 0.12` was justified as *"2022
renewals averaged +10.7%"* — an observed outcome installed as a hard
constraint. It also double-counted: the model already priced elasticity, so
restraint should have *emerged*. We bolted it on, then discovered it.

*Would have caught #3.* "The mechanism is the shape of the deadline" was
asserted, not ablated. Swapping the cliff for a mean-matched linear ramp
showed shape contributed 13% and level 87%.

**Two rules:**
1. Every constant carries a source that is *upstream* of the phenomenon.
   Where none exists, label it INVENTED in code and in every result table.
2. **Every mechanism claim must be ablated.** If you say X causes Y, run
   without X and report the delta. An unablated mechanism claim is a
   hypothesis wearing a finding's clothes.
3. See **G**, this principle's converse. C is checked parameter-by-parameter
   and misses loops that are only visible output-by-output.

## D. Identical populations

**A treatment effect is measured on the same population, not on the
subset that self-selected into treatment or survived to be measured.**

*Would have caught #4 and #5.* Per-asker, the tool looked worth
+$3,700/yr; on an identical population it was −$244. Pure selection. And
the K21 quartiles recorded only tenants who *stayed*, inverting the table.

**Enforcement:** any per-user statistic reports the identical-population
comparison beside it, or it is not reported. Any statistic conditioned on
an outcome (stayed, succeeded, renewed) is labelled as conditional and
paired with the unconditional version.

## G. The free-outputs register

**Before running, write down which observables are *not* fitted — directly
or through any parameter. Those are the only outputs that can be findings.
Everything else is a readout.**

*Would have caught two loops the parameter audit missed entirely.* The
crab study's `vacancy` cited *"39.7% of 2026 listings carried a
concession"*; its `p_exo` cited *"NAA turnover ~47%."* Both were filed
UPSTREAM, because each cites a real published number. The source was never
the problem. The problem is that each number cited was **one of the model's
own validation targets.**

Read parameter-by-parameter, that is invisible: `vacancy` cites a
concession statistic, which looks like data. Read output-by-output, it is
immediate — the concession rate is on both sides of the ledger. Principle C
cannot see this, because no single parameter looks circular on its own.

Worse, it compounds. `move_med` was calibrated to observed elasticity and
`p_exo` to observed turnover — the rent-driven and non-rent halves of the
same fact, fitted separately. Between them the retention gate was not a
weak test, it was **an identity**, and nothing in the per-parameter audit
said so.

The register is a table, filled in before the first run:

| Observable | Fitted? | Through what |
|---|---|---|
| concession rate | YES | `vacancy` |
| turnover / retention | YES | `p_exo_*`, `move_med`, `move_sigma` |
| counter rate | YES | `courage_med`, `belief0` |
| renewal increase level | YES | `renewal_cap` (until A7) |
| *everything else* | NO | free — may be claimed |

**Three rules:**
1. An observable fitted through *any* parameter is fitted. Indirection is
   not laundering, and two parameters fitted to two halves of one fact
   fit the whole fact.
2. **A validation gate on a fitted observable is not a test.** It is an
   identity. Reporting it as a gate overstates what was checked. State
   which gates are free and which are not, in the same table as the gate
   results.
3. The register is written *before* the run and published *with* the
   results, unedited. Amending it afterwards is how a readout becomes a
   finding.

Track record: of the crab study's three validation gates, at least two were
on fitted observables. All three failed anyway — which is the only reason
nothing was overclaimed off them.

---

## E. Standing posture: assume artefact

The adversarial audit found six artefacts by *defaulting to suspicion* —
assuming every surviving result was a construction error until shown
otherwise. That found more than pre-registration did.

So it is not a special pass at the end. **Every result that favours the
hypothesis gets a bug hunt before it is believed**, and the hunt is
reported whether or not it finds anything. Results that go *against* the
hypothesis need it less — nobody accidentally builds an apparatus that
refutes them.

Track record worth remembering: of the seven artefacts, **six ran in the
direction of a more interesting story.** That asymmetry is the signal.

## F. The prose is a detector

Artefact #7 was found by a reader noticing a sentence sounded wrong ("why
is it capped at all?"), not by any audit of the code. Writing the result
up in plain language, for someone who will ask *why is it like that*, is a
cheap and effective check. Do it before believing a result, not after.

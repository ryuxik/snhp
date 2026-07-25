# Experiment design principles

*Derived 2026-07-25 from the seven artefacts the crab study produced, not
from a textbook. Each principle names the specific failure it would have
caught. Binding on any future simulation in this repo.*

## Why this exists

The crab rent study pre-registered 26 kill conditions, ran three
validation gates, and was audited adversarially. It still produced **seven
artefacts**, two of which shipped to users. Pre-registration caught none
of them — it constrains what you *claim*, not what you *build*. Every one
was a construction error, found later by inspection or ablation.

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

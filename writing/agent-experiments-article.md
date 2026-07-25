# The number that came from no run

*What breaks when the same system writes the code, runs it, reads the output, and writes the paragraph.*

---

There is a number in an article I published about rent negotiation. It reads: **10.2% off the offer.** It is the payoff of the whole piece, the moment where the thing that had failed for a week finally worked.

It was also in the commit message that introduced it, stated as settled: *"With a costly verifiable signal, proving an alternative takes 10.2% off the offer."* It went into user-facing product copy. It was repeated across sessions as an established finding, the way you'd repeat any number that already has a source.

Then somebody asked where it came from.

The mechanism was real. It is in `market.py`, about forty lines, with four unit tests that pass. A tenant who has actually secured another apartment can prove it, at a cost, and the landlord can respond to the proof rather than to a claim.

Here is what was not real. **No runner in the repository ever turned it on.** The flag defaults to `False`. The registered cell that was supposed to test this exact question runs with the channel closed. It appears in no results file. The study's own results document still records the opposite verdict: *does not confirm, +$17 against a $480 bar.*

Nobody lied. The number entered prose ten minutes after the mechanism was written, sitting next to code that genuinely did something, and was never re-derived. And that is the whole problem, so I want to state it before the evidence rather than after.

## The claim

**When one system writes the code, runs it, interprets the output, and writes it up, the failure mode is not dishonesty. It is that the handoff where a human would have said "show me the output file" no longer exists.**

Every research pipeline built by humans has that seam in it, and the seam is load-bearing. The person writing the paragraph is not the person who ran the job, so they have to ask, and the asking is what forces a number to resolve to an artefact.

Collapse the seam and numbers stop being retrieved and start being *remembered*. A remembered number is indistinguishable from a measured one at the point of use. Right significant figures, right paragraph, no marker saying which it is.

## Six of seven

That study was not casual. It pre-registered **26 kill conditions**, all stated on outputs and all bidirectional, before any code existed. It ran three validation gates. All three failed, and it published the failures as the primary result. Then it was audited adversarially by a pass whose standing posture was *assume artefact*.

It still produced **seven construction errors**, and by the time they were caught, two had reached users.

The number that should make you uncomfortable is this one: **six of the seven ran in the direction of the more interesting story.**

Not the true direction. The publishable one. The renewal offer that was secretly built from each tenant's private moving cost, which manufactured exactly the market pattern we were trying to explain. The tool that looked worth $3,700 a year per user and was worth **minus $244** on an identical population. The quartile table that recorded only the tenants who stayed, which inverted it. The constant capped at 0.12 because 2022 renewals averaged 10.7%, then triumphantly discovered to produce about 10.7%.

The consequence is a scheduling rule, and it is free: **direction is the cheapest filter you own.** A result that helps you should cost strictly more to believe than one that hurts you, because nobody accidentally builds an apparatus that refutes them. Results that go against you can be believed on sight. Results that go for you get a bug hunt, and the bug hunt gets reported whether or not it finds anything.

Note what pre-registration did here. It caught the errors it was pointed at, roughly two of seven: one guard, declared in advance, caught that $3,700 selection confound and saved a flagship claim from being wrong in public. The other five lived in code that pre-registration never described. **Pre-registration constrains what you claim. It does not constrain what you build.**

## What happened when I wired it

Back to 10.2. I added the flag to the registered cell, at the study's own geometry and its own 30 seeds, and ran it.

Offer relative to market, for a tenant who proves an alternative versus one who does not: **1.0395 against 1.1416.** A gap of **0.1021.**

So the number is real, and it is misdescribed. 0.1021 is ten point two *percentage points of market rent.* As a share of the offer, which is what "10.2% off the offer" says, it is **8.9%.** The sentence overstates by about a seventh, and it did that quietly for a week, in prose and in shipped copy, because there was no output file to check the sentence against.

Then I ran the ablation, which is the part that matters.

The study also carries a deadline clock: a renewing tenant's position decays as the response window runs out, with a cliff at the end. Proving an alternative removes you from the cliff. So turn the deadline clock off, leave the signal on, re-run.

**Gap: 0.0000.**

Not small. Zero, to four decimal places. The entire effect is the deadline. Nothing about proving an alternative moves the offer at all. The article's headline finding was the study's *other* finding, measured a second time under a different name, and that shape had already been caught once: a claim that "it's the shape of the deadline" turned out, against a mean-matched linear ramp, to be **87% level and 13% shape.**

One ablation. Twenty-four seconds. Nothing had ever required it.

## The circularity that kept growing

The same study ran a provenance audit over every constant, classifying each by whether its stated basis is upstream of the phenomenon. It found three circular: one justified by the average it explains, one by the kill condition it lets fire, one by landing on the observed rate it is supposed to predict.

Then a second look found four more the audit had passed, and this is the interesting failure. Each cited a real published number. Vacancy cited *"39.7% of listings carried a concession."* Turnover cited *"NAA turnover ~47%."* Both look like data, because they are data.

They are also both on the pre-registration's own list of calibration targets. The model was fitted to them and then validated against them.

**Read parameter by parameter, that is invisible. Read output by output, it is immediate.** A per-constant audit structurally cannot see it, because no single constant looks circular alone.

It compounds. One parameter was calibrated to observed rent elasticity, another to observed turnover: the rent-driven and non-rent halves of one fact, fitted separately. Between them the retention gate was not a weak test, it was an identity. And in a second file I counted **19 module-level constants that no audit had ever covered at all.**

## What worked

Six things, all cheap, all mechanical:

- **Kills on outputs, before the code exists, bidirectional.** Say what it means if the condition does *not* fire, or you have written a hypothesis, not a test.
- **A separate adversarial pass whose standing posture is assume-artefact.** It found more than pre-registration did.
- **One knob.** Two compared arms differ in exactly one declared dimension, enforced by a test that diffs the arm descriptors. That 8.5x "whoever holds the engine wins" result was three confounds wearing one label.
- **Declared information budgets.** Each agent has an explicit observation set, and a test greps its decision path for anything outside it.
- **Identical populations.** Any per-user statistic reports the identical-population figure beside it, or is not reported. That is the $3,700 versus minus $244 gap.
- **The prose is a detector.** The circular cap was caught by a reader thinking a sentence sounded wrong, not by any audit of the code.

And one more, which is the whole point of 10.2%: **every number in a paragraph resolves to a file on disk.** Not to a memory of a run. Not to a mechanism that plausibly produces it.

## The thing to do on Monday

Make it a skill, so the agent enforces this against itself instead of remembering to.

I wrote one: an **experiment registrar**. It refuses to run a sweep until kills are registered on outputs and bidirectionally. It requires a free-outputs register, written before the first run and published unedited, saying which observables are fitted and through what, so a validation gate on a fitted observable gets labelled as the identity it is. It fails the suite when a constant has no provenance entry. It demands an ablation for every mechanism claim. And it will not let a draft cite a number that appears in no committed results file.

That last gate costs one grep. It would have caught 10.2% the day it was written.

The pitch for coding agents in research is that they close the loop: hypothesis to code to result to writeup, no handoffs. That is exactly right, and the handoffs were doing something. Put them back as code.

---

**Reply 1, methodology and receipts.**

Everything above is checkable. The study is 1,700 lines of results, 26 registered kills, 96 tests. The seven artefacts and the principles derived from them are in `research/DESIGN-PRINCIPLES.md`; the machine-checkable half is `research/crabs/principles.py`, which holds the provenance table and pins the circular list so it cannot quietly grow.

The 10.2% trace: mechanism added 16:21, article prose 16:31, no runner in between. My re-run used the study's registered `a6a_secured` cell, 40 stations by 25 units, 30 seeds, drift zero, with `signal_enabled` flipped on. Signal off reproduces the published +0.0002 exactly, which is how I know the harness was right. Signal on: 1.0395 versus 1.1416. Deadline clock off, signal on: 0.0000.

While I was verifying this, the repository's own Amendment 9 was appended, independently, recording the same gap and pre-registering two kills on it. On my run the first does not fire, so the effect is real and the article's wording has to be restated to whatever the run gives. The second fires in its strongest form: the effect is the clock, not the alternative.

The registrar skill, in outline:

```markdown
---
name: experiment-registrar
description: Gate for simulation and experimental work. Use whenever an
  experiment is being designed, run, amended, or written up. Refuses to
  proceed until kills, a free-outputs register, and parameter provenance
  exist; requires an ablation per mechanism claim; blocks any number in
  prose that does not resolve to a committed results file.
---

# Experiment registrar

Six gates. Each derived from a specific failure, not from a textbook.
The agent may not disable a gate; it may only record a violation.

## Gate 1: kills, before code
No runner is written until PREREG.md exists with kill conditions that are
(a) stated on OUTPUTS, (b) numeric with a declared bar, (c) BIDIRECTIONAL:
the consequence if it does not fire is written down too. Reject any kill
phrased over inputs or mechanisms.

## Gate 2: the free-outputs register
Before the first run, a table: observable | fitted? | through which
parameter. Indirection is not laundering; two parameters fitted to two
halves of one fact fit the whole fact. Any validation gate on a fitted
observable is reported as an IDENTITY, not a test. Written before, published
after, unedited. Amending it post hoc is how a readout becomes a finding.

## Gate 3: provenance or it fails
Every constant carries a source class: UPSTREAM / DERIVED / CALIBRATED /
INVENTED / CIRCULAR. A constant with no entry fails the suite
(`undeclared_parameters() == []`). CIRCULAR is pinned as a list, so the
list going red means it CHANGED. Scope is every module that holds a
constant, not just the one someone audited.

## Gate 4: one knob
Arms declare their config as data, including derived structure: round
count, move order, action-grid reach, which optimiser each side gets.
A test diffs any two compared arms and fails on undeclared differences.

## Gate 5: one ablation per mechanism claim
Any sentence of the form "X causes Y" requires a run with X removed and
the delta reported. Unablated mechanism claims are hypotheses in a
finding's clothes. Run the ablation before writing the sentence.

## Gate 6: numbers resolve to files
Every figure in prose, product copy, or a commit message must be locatable
in a committed results artefact. Grep the draft for numerics; each one maps
to file + key, or it is struck. No exceptions for numbers you remember.

## Standing posture
Assume artefact. Every result favouring the hypothesis gets a bug hunt
before it is believed, and the hunt is reported whether or not it finds
anything. Results that go against the hypothesis need it less.
```

Gates 1 through 6 are predicates: a machine decides them, and the agent cannot argue. The standing posture is not, and neither is the prose detector, which needs an actual reader who will ask why a sentence sounds wrong. Those two stay with people. Pretending a test can hold them would be worse than admitting it cannot.

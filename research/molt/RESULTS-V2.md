# RESULTS v2 — Molt Season under PREREG AMENDMENT 1

**Everything here is exploratory**, by the amendment's own terms: it was
registered after Phase-1 results were read. It is nonetheless the version to
believe, because the Phase-1 opponent was handicapped and the Phase-1 employer
was omniscient.

Reproduce:

```bash
python research/molt/run2.py && python research/molt/analyze2.py
python research/molt/run2.py --confirm            # held-out seed 101
```

1,920 crab-seasons per arm per regime (40 crabs × 12 seasons × seeds 7/11/23/31),
mean salary $112,644, bar 2% = **$2,253**. 36 arms per crab-season: 19 archetypes
at `best_first`, six of them at all three orderings, plus the engine arms and the
forced-disclosure counterfactual. Everything below replicates on seed 101.

---

## The headline, and it is a retreat

| | verifiable regime | unverifiable regime |
|---|---|---|
| engine vs the best archetype, **clock on** | **+$27,286** joint | **+$18,341** joint |
| engine vs the best archetype, **clock off** | **+$3,837** joint (crab **+$500**) | **+$277** joint (crab **−$2,592**) |
| v1's equivalent zero-clock figure | +$9,597 | — |

**K8 fires in the unverifiable regime and survives, barely, in the verifiable
one.** With every delay cost zeroed and a real corporate strategy on the other
side of the table, one sitting is worth $3,837 jointly when outside offers can be
proved, and **nothing** when they cannot.

And in both regimes, **the crab's share of the equal-speed gain is below the
bar** — +$500 verifiable, −$2,592 unverifiable, −$88 on the held-out seed. So:

> **At equal speed, the money story is an employer story. For the employee there
> is no equal-speed money story at all — what the employee gets is the clock.**

That is a materially smaller claim than v1's, and it is the one that survives an
opponent that is not handicapped.

## Kill verdicts

| kill | verifiable | unverifiable |
|---|---|---|
| **K8** the money story | does not fire (+$3,837) | **FIRES** (+$277) |
| **K9** the size of my thumb | does not fire (max $565) | does not fire (max $650) |
| **K10** does disclosure pay | does not fire — **+$2,851** to the crab | **FIRES** — talk is worth exactly $0 |
| **K11** did the match value do anything | **FIRES** — rank corr 0.079 | does not fire — 0.279 |
| **K12** archetype dependence | does not fire — 1.04× across 19 | does not fire — 1.08× |
| **K13** the split | does not fire — 91.6% employer | does not fire — 77.6% employer |

### K9 did not fire: the agenda objection is answered

This was the objection I expected to lose. Across all six reported archetypes,
moving from `money_first` (my Phase-1 agenda) to `best_first` (the crab opens on
whatever it wants most) changes the concession by **$143–$378** and the crab's
outcome by **$258–$650**. The largest ordering effect anywhere is **$650**,
against a $2,253 bar.

**My thumb was worth about $400.** The Phase-1 concession gap was not an artifact
of the agenda — it just wasn't as large as Phase 1 measured, for a different
reason (below).

My registered prediction 3 said K9 would fire. **Refuted.**

### The selection-free decomposition, rebuilt

Restricted to crab-seasons the Works retains under both protocols (n≈1,205,
verifiable, vs Split-the-Diff at `best_first`):

| | Works pays | crab receives | days |
|---|---|---|---|
| slow talks (Split-the-Diff, best-first) | **$20,516** | $18,965 | 47.3 |
| one sitting | **$13,961** | $19,589 | 3.8 |

The employer saving survives nearly intact — **$6,555**, against v1's $7,108. The
crab's gain does not: **+$624**, against v1's +$2,993. Against a competent
opponent that opens on what it actually wants, most of what the engine was
"winning for the crab" turns out to be what a good negotiator wins for itself.

### K10: what the offer letter is actually worth

Same crab, forced to show the letter versus forced to stay silent:

- the crab gains **+$2,851 ± 172**
- the Works gains **+$12,993**
- departures fall **16.0 percentage points**

Showing a verifiable offer pays, for both sides. In the unverifiable regime the
identical comparison is **exactly $0**, because claiming is free, so everyone
claims, so the claim separates nobody. That is the unravelling result — and note
it is now *derived*, where Phase 1 assumed it by giving the employer the answer.

**But the regime comparison inverts the individual one.** Living in a world where
offers can be proved, versus a world where they cannot:

| | crab | Works | departures |
|---|---|---|---|
| verifiable − unverifiable (one sitting) | **−$6,528** | **+$9,610** | −8.9pp |

**Being able to prove your offer is worth $2,851 to you. Living in a world where
offers can be proved costs you $6,528.** When nothing can be verified, the
employer must price everyone as though they might have a good offer, and concedes
to everyone. When letters can be shown, silence convicts you of having nothing.

This is the sharpest result in the study and it belongs to the employer.

### K11 fired, and the diagnostic says something

Firm-specific match value — what a crab is worth to *this* employer — barely
moves what the employer pays: rank correlation **0.079** in the verifiable
regime. The fix for the "you don't price skill differences" objection is,
by its own registered test, **inert**.

The unverifiable regime says why: there the correlation is **0.279**, and it does
not fire.

> **When your employer can see your outside offer, it pays for the offer. When it
> can't, it pays for you.** Verifiability replaces "what are you worth to us"
> with "what will it take to keep you," and those are different questions with
> different answers.

Registered honestly: K11 fired on its stated test, so the claim "we now price
skill differences" is not made. The regime contrast is a diagnostic run after the
kill, and is labelled as such.

### K12: how you haggle does not matter

Across all 19 archetypes at `best_first` — Anchorer, Silent Hardliner,
Split-the-Diff, Deadline Exploiter, Soviet Patience, Tactical Empath, Logroller,
Cialdini, the behavioural-bias set, all of them — the engine's advantage spans
**+$27,286 to +$28,329**. A **1.04× spread**.

Nineteen documented negotiation styles, including one (Logroller) built
specifically for issue-by-issue trading, and they land within four percent of
each other. The counterparty's arithmetic dominates the counterparty's *manner*.

Pair this with K10 and the replacement for the retracted Phase-1 claim is:

> **What you reveal is worth $2,851. How you haggle is worth nothing.**

Which is a real finding, unlike the one it replaces, because the employer here
does not already know the answer.

### K13: the split holds

| | joint gain vs the best archetype | crab | employer |
|---|---|---|---|
| crab holds the engine (verifiable) | +$27,286 | 8.4% | **91.6%** |
| Works holds it (verifiable) | +$23,355 | 5.4% | **94.6%** |
| crab holds it (unverifiable) | +$18,341 | 22.4% | **77.6%** |

Still inside the registered 70–95% band, so K13 does not fire and prediction 4
survives. Note the crab's share is best in the regime where nothing can be
verified — the same inversion as K10.

## Scorecard on my registered predictions

| | prediction | outcome |
|---|---|---|
| 1 | the zero-clock advantage falls by **more than half** | **CONFIRMED** — $9,597 → $3,837 (−60%), and to $277 unverifiable |
| 2 | disclosure pays; the retracted claim stays retracted | **CONFIRMED** — +$2,851 |
| 3 | K9 fires; the agenda was doing real work | **REFUTED** — largest ordering effect $650 |
| 4 | the ~90% employer split survives | **CONFIRMED** — 91.6% |

## What v2 changes about what may be said

**Deleted:** "a better ask against a counterparty doing its own sums buys you
nothing" (tautological in v1; and in v2, revealing *does* pay).

**Reduced:** the equal-speed money claim, from +$9,597 joint to +$3,837, with the
crab's share below the bar in every regime and on every seed.

**Reduced:** the both-stay crab gain, from +$2,993 to +$624. The employer saving
survives at $6,555.

**Unchanged:** the clock is where the money is; the employer captures ~90%; going
fast does not cost deals.

**New:** verifiability is an employer-side technology. So is the engine. That is
now two independent findings pointing the same way, and both of them came out of
tests written to catch me claiming otherwise.

## Known limitations not fixed by this amendment

- **The Works still knows the crab's priorities exactly.** Amendment 1 removed
  its knowledge of the outside offer, not of what the crab wants. Every v2 number
  should be read as "the employer knows what you want, but not what you can get
  elsewhere."
- **The clock calibration is untouched**, so the attrition hazard remains the
  single most load-bearing and least defensible parameter in the study.
- **Still no equilibrium response, still no humans**, both as stated in v1.
- **Compute deviation, disclosed:** A1.4 said all 19 archetypes at all orderings.
  Run as 19 at `best_first` plus six at the other two orderings — 31 slow arms per
  crab-season rather than 57. No kill depends on the cells that were dropped.

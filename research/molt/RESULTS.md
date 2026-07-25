# RESULTS — Molt Season (v1)

> **SUPERSEDED IN PART.** [PREREG AMENDMENT 1](PREREG-AMENDMENT-1.md) rebuilt the
> opponent and the employer's information after four objections to this design.
> Read [RESULTS-V2.md](RESULTS-V2.md) for what survives. In short: the +$9,597
> zero-clock figure below falls to **+$3,837** (and to **+$277** where outside
> offers cannot be verified, firing K8); the crab's share of it drops below the
> bar; the $7,108 concession gap becomes **$6,555** with the crab's share falling
> from +$2,993 to **+$624**; and the "asking harder is worth nothing" finding is
> **RETRACTED** — this version's employer already knew the crab's outside offer,
> so that arm could not have come out any other way. The clock channel, the
> ~90% employer split, and "speed does not cost deals" survive the rebuild.

**Status: complete on the registered seeds and confirmed on the held-out seed.**
Seven kills were registered in PREREG §4 before the first run. **One fired
(K6)**, and it fired because my diagnostic was mis-specified rather than because
the mechanism was absent; the identification it demanded was then run and is
reported below, labelled exploratory. Three of my four on-record predictions
survived; **the headline prediction (P1) was refuted**, and the refutation
changed what the demo says.

Reproduce:

```bash
python -m pytest research/molt/tests/test_molt.py -q
python research/molt/run.py && python research/molt/analyze.py
```

Population: 1,920 crab-seasons per arm (40 crabs × 12 seasons × seeds 7/11/23/31),
mean salary $113,404, registered bar 2% of salary = **$2,268**. All money is PV
over 3 years, per crab-season, relative to the Works' opening offer.

---

## The headline

| arm | crab $ | Works $ | joint $ | days | meetings | departures | permanent raise granted |
|---|---|---|---|---|---|---|---|
| **A** SIGN IT | 12,730 | −37,875 | −25,144 | 1.0 | 0 | 30.6% | 1.43% |
| **B** SLOW TALKS | 13,293 | −53,320 | −40,027 | **42.2** | 3.9 | **34.6%** | **3.00%** |
| **C** SLOW ENGINE | 13,271 | −53,194 | −39,923 | 42.2 | 3.9 | 34.6% | 2.92% |
| **D** ONE SITTING | **17,190** | **−25,405** | **−8,214** | **3.9** | 1 | **14.3%** | 1.20% |
| **E** WORKS HOLDS IT | 17,087 | −27,049 | −9,962 | 3.0 | 1 | 14.1% | 1.34% |
| **F** BOTH SIDES | 15,656 | −32,810 | −17,154 | 2.9 | 1 | 24.0% | 0.82% |

**D vs B, paired:** crab **+$3,898 ± 180**, Works **+$27,915 ± 1,288**, joint
**+$31,813 ± 1,349**, and **38 fewer days**. Every number reproduces on the
held-out seed 101 (+$4,352 / +$30,204 / +$34,556).

**The two-sentence version.** Slow talks cost the Works $15,445 per crab-season
against simply signing its own opening offer, and bought the crab $563. Doing
the same negotiation in one sitting is worth $31,813 a crab-season against slow
talks, and the crab keeps 12% of that.

---

## Kill verdicts

| kill | test | verdict |
|---|---|---|
| **K1 TAUTOLOGY** | zero-clock joint D−B ≥ $2,268? | **does not fire** — +$9,597 with every delay cost set to zero |
| **K2 NO-MONEY** | D−B under $2,268 on both sides? | **does not fire** — +$3,898 crab, +$27,915 Works |
| **K3 STRAWMAN** | is C (engine, one issue at a time) within $2,268 of D? | **does not fire** — D beats C by $31,709 |
| **K4 CAPTURE** | does one side take >70% in F? | **YES — the Works takes 90%.** Copy rewrite triggered |
| **K5 SPEED COSTS DEALS** | D agrees ≥3pp less, or loses ≥2pp more crabs? | **does not fire** — D agrees **23.8pp more** and loses **20.3pp fewer** |
| **K6 HETEROGENEITY** | does D−C halve when crabs are near-identical? | **FIRES** — it falls only 7% (see below) |
| **K7 COMPANY-LOSES** | is the Works better off under slow talks? | **does not fire** — the Works is $27,915 worse off under B |

### K1 is the one that matters, and it did not fire

With the manager's hourly rate, the distraction cost, the attrition hazard and
the offer-expiry clock **all set to zero**, one sitting still beats slow talks
by **+$9,597 joint (crab +$2,724, Works +$6,874)**. The advantage is not an
artefact of our delay calibration. The clock roughly triples it (+$9,597 →
+$31,813) — that multiple *is* a claim about our calibration, and §"Sensitivity"
gives its range.

### K4: the Works takes 90%, again

| arm | joint gain vs B | crab's share | Works' share |
|---|---|---|---|
| D (crab holds it) | +31,813 | 12.3% | **87.7%** |
| E (Works holds it) | +30,065 | 12.6% | **87.4%** |
| F (both hold it) | +22,873 | 10.3% | **89.7%** |

This is the rent study's K16 finding reproduced in a different market: whoever
holds the engine, **the employer captures ~88–90% of the value it creates**.
Two consequences, both binding:

1. **The buyer is the employer.** A crab-facing product is a 12%-of-the-value
   product. Any pitch aimed at employees must say so.
2. Note the crab's share barely moves between D and E. The crab does *not* need
   to be the one holding the tool to get its 12% — most of what the crab gains
   comes from the deal existing at all, not from who is armed.

### K6 fired, and my diagnostic was the thing that was wrong

I registered: if the bundle's advantage does not halve when crabs are made
nearly identical (Dirichlet α = 4.0), the logrolling story is not the mechanism.
It fell from +$30,368 to +$28,100 — **7%**. K6 fires.

It fires because the registered test was mis-specified, not because the
mechanism is absent. Textbook logrolling needs the two *sides* to rank the
issues differently; it does not need the crabs to differ **from each other**.
Every crab in this world faces the same cross-side price gap — a promotion costs
the Works $11,606 and is worth $41,442 to a title-hungry chemist — and that gap
survives making all crabs identical.

**The identification the kill demanded (exploratory, run after K6 fired).** Two
ablations crossed, clock off, so only the allocation channel is live. `flat` =
every currency repriced so the Works' cost equals the average crab's valuation,
i.e. no cross-side price difference left.

| | joint D−C | reading |
|---|---|---|
| cross-side prices ON, α=1.4 | **+9,145 ± 851** | the shipped world |
| cross-side prices ON, α=4.0 | +9,731 ± 1,003 | between-crab variation contributes ≈ **nothing** |
| cross-side prices OFF, α=1.4 | **+3,380 ± 666** | 63% of the gain was the price gap |
| cross-side prices OFF, α=4.0 | +3,414 ± 822 | again, crab-to-crab variation ≈ nothing |

So the bundle's advantage decomposes into **~63% cross-side relative prices**
(the Works' cheap currencies are the crab's dear ones) and **~37% a retention
channel that survives identical prices**: the bundle finds a package that keeps
a crab the one-issue ladder loses, and *not losing the crab* is positive-sum
however you price the terms. Idiosyncratic crab taste contributes essentially
zero. **Anything we publish must say the mechanism is a price gap between the
two sides plus deal-existence — not "everyone wants something different."**

---

## P1 REFUTED: the meetings are not the cost. The exposure is.

I predicted the dominant channel would be mis-allocated concession — the Works
paying permanent salary where a cheaper package would have worked — and that it
would exceed manager hours, distraction and attrition combined. **Wrong, by 5×.**

Decomposition of the Works' $27,915 advantage in D over B:

| channel | $ | share |
|---|---|---|
| **replacement cost of crabs who left** | **+22,252** | **79.7%** |
| concession mis-allocation | +4,076 | 14.6% |
| distraction | +958 | 3.4% |
| manager hours | +629 | 2.3% |

Manager time — the thing everyone points at when they complain about slow
negotiation — is **2.3%** of it. What slow negotiation actually costs is the 38
extra days during which a crab holding a live outside offer can walk out, and
14 of them do.

**The concession channel is real, but it is second, and it is only visible with
selection removed.** Restricted to the 1,217 crab-seasons the Works retains under
*both* arms (so the comparison is not a different mix of crabs):

| | Works' concession | crab receives | permanent raise | promoted | days |
|---|---|---|---|---|---|
| **B** SLOW TALKS | **$20,547** | $16,499 | 4.41% | 0.3% | 40.3 |
| **D** ONE SITTING | **$13,439** | $19,492 | 1.50% | 28.4% | 4.0 |

Same crabs, all retained either way: **the Works pays $7,108 less and the crab
receives $2,993 more.** The Works buys retention with a 4.4% permanent raise that
leaks to the whole band; the engine buys it with a promotion and a flexible
berth that cost a third as much and are worth more to the crab.

Predictions 2, 3 and 4 survived: the Works captures the majority in F (predicted
>55%, actual 90%); K1 did not fire; K5 did not fire, and agreement rates went
*up* under D as predicted.

---

## Findings that were not asked for

**1. ~~Asking for more does not get you more (B ≡ C).~~ RETRACTED — see AMENDMENT 1 §A1.0.** The employer in this version reads the crab's outside offer directly, so no ask could inform it and the arms were identical by construction. The v2 replacement, against an employer that cannot see the offer: showing a verifiable letter is worth **+$2,851**; how you haggle is worth nothing (1.04x across 19 documented strategies). Original text follows, struck:

>  Arms B and C are
bit-identical on every aggregate to within $126. Arm C really does call
`negotiate_turn` and really does ask differently on 44 of 60 pilot crabs
(pinned by a test) — but the Works replies from its own NPV, and its optimum sits
*below* every ask, human or engineered. **A better ask against a counterparty
doing its own arithmetic is worth nothing.** This is the rent study's K26
("shopping around does not help you negotiate") in a second market. What changes
the answer is changing *what is on the table*, not how hard you ask for it.

**2. Arming both sides destroys value.** Arm F is worse than arm D on every
measure that matters: joint +22,873 vs +31,813 vs slow talks, departures 24.0%
vs 14.3%. With the clock off, F is **worse than slow talks outright**
(−$1,547 joint). A Works playing the engine concedes less (0.82% base, 13.8%
promotion rate, against D's 1.20% and 20.3%), more crabs leave, and the
replacement bill eats the efficiency gain. *Caveat:* the Works' engine infers
crab priorities from a coarse counter-offer sequence, so F may be understating a
well-instrumented employer. It is reported because we registered no prediction
that would let us discard it.

**3. Negotiating is good; negotiating slowly is ruinous.** With the clock off,
slow talks beat just signing (+$2,708 crab, +$10,147 Works). Switch the clock on
and the same protocol goes **$14,883 worse than signing nothing at all**. The
advice "just sign it" is wrong for the crab and right for nobody — but a Works
that must choose between a six-week negotiation and its own opening offer should
pick the opening offer.

---

## Sensitivity

Joint D−B across every registered sweep (seed 7). The sign never flips and the
Works' share never leaves 77–93%.

| sweep | range of joint D−B |
|---|---|
| replacement cost ρ × {0.5, 1.0, 1.5} | +19,236 … +41,194 |
| peer spillover σ {0, .15, .30, .60} | +28,289 … +31,290 |
| crab dispersion α {0.8, 1.4, 4.0} | +28,214 … +33,884 |
| distraction {0, 4, 8, 16}% | +29,526 … +31,443 |
| meeting delay median {4.5, 9, 18} days | +22,133 … +46,054 |
| attrition hazard {0.45, 0.9, 1.8}%/day | +24,334 … +45,977 |
| Works' counter threshold {0, .5, 2}% | +30,481 … +30,485 |

Even at **zero distraction and half the published replacement cost**, the result
holds. The two parameters that move it are the two clock parameters, exactly as
they should — and K1 already showed that zeroing all of them leaves +$9,597.

---

## What this does not show

- **No human subjects.** Every crab and every manager is a payoff-maximiser.
  Nothing here says how real people negotiate, how they feel about being handed
  a package by a machine, or whether an employer would deploy it.
- **No repeat play, no reputation, no fairness reaction.** Seasons are
  independent. The rent study found that when everyone gets the advice, the
  landlord raises its offer to everyone and non-askers absorb the cost. Nothing
  in this design could see that, and the same effect is plausible here.
- **The calibration is trade-press.** Time-to-fill (44 days), replacement cost
  (0.5–2× salary), and the counteroffer/withdrawal statistics come from
  consultancy and recruiter benchmarks, not peer-reviewed estimates. They set
  the size of the clock effect, not its existence — K1 is the guard.
- **The slow arm is a model of sequential bargaining, not a recording of one.**
  Its parameters (agenda order, one issue per meeting, nothing revisited) are
  stated in SPEC §4 and are the mechanism under test. A firm that already
  negotiates the whole package at once would see the zero-clock number
  (+$9,597), not the headline.
- **Arm F's caveat above.** A employer with a well-instrumented engine may do
  better than our F.

---

## Sources for the calibration

- [SHRM 2025 benchmarking, via Staffing Industry Analysts](https://www.staffingindustry.com/news/global-daily-news/average-cost-hire-about-4100-shrm-says) — cost per hire
- [2025 time-to-fill benchmarks, Mitratech](https://mitratech.com/resource-hub/blog/what-2025-time-to-fill-benchmarks-reveal-about-hiring-agility-and-risk/) — 44-day median
- [SHRM/Gallup replacement cost 50–200% of salary, via Waterfall Planning](https://waterfallplanning.com/learn/the-real-cost-of-employee-turnover/) and [Manatal](https://www.manatal.com/blog/cost-of-replacing-an-employee) — the ρ table
- [Candidate withdrawal and delay statistics, JobScore](https://www.jobscore.com/articles/candidate-experience-statistics/) and [MSH](https://www.talentmsh.com/insights/candidate-experience-statistics) — the 10-day window, 32% "accepted another offer"
- [Salary negotiation statistics, Procurement Tactics](https://procurementtactics.com/salary-negotiation-statistics/) — 55% accept the first offer; ~3.7% budgeted increases
- **Explicitly not used:** the "80–90% of counteroffer acceptors leave within a
  year" figure, which [has no traceable study behind it](https://www.linkedin.com/pulse/so-do-80-people-who-accept-counteroffers-really-leave-ken-davies).
  The traceable figure is Robert Half's 40.8% within 12 months; our attrition is
  modelled as a daily hazard during open talks, not as a post-counteroffer
  regret rate, and does not rest on either number.

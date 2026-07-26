# RESULTS v6/v7 — Molt Season under AMENDMENT 5, and the symmetric harness

**The headline of v4 and v5 was a bug in my harness.** "An ordinary human
negotiator beats the engine" does not survive an employer that plays by the same
rules in both arms. At matched settings the engine wins every cell, on joint
surplus and on the employee's own utility.

Exploratory, like Amendments 1–5. Reproduce:

```bash
python3 -m pytest research/molt/tests/test_arms.py -q   # the standing assertions
python3 research/molt/run6.py                           # A5 arms, asymmetric
python3 research/molt/run7.py                           # the symmetric harness
```

---

## 1. The two asymmetries

Both were mine, both favoured the sequential arm, and neither was visible in a
summary table.

**Action set.** `works_packages3` iterates `range(base_pkg.base, 4)`. The
sequential arm handed it `Package()`, so its employer could cut base to fund a
promotion. The engine arm handed it the opening offer, so its employer was
floored at the standing raise and structurally barred from that trade.

**Reply rule.** `works_best_reply3` seeds its search at the opening's NPV and
returns `None` when nothing beats holding firm — the negotiation then dies at the
opening. The sequential arm's per-option argmax carried no such requirement.

In v7 a single `works_reply()` serves both arms and both become explicit
treatments.

## 2. Engine vs sequential, matched (joint surplus)

| employer's rules | engine | sequential | engine − sequential |
|---|---|---|---|
| no base cut, strict reply | 2,713 | 1,144 | **+1,569** |
| no base cut, permissive | 6,656 | 1,754 | **+4,902** |
| may cut base, strict | 8,897 | 4,859 | **+4,038** |
| may cut base, permissive | 10,296 | 5,581 | **+4,715** |

The engine also wins the crab's own utility in all four cells on the main seeds
(+$597 to +$3,204) — **but that part does not replicate.** On held-out seed 101 at
the `cut=Y,strict=N` setting the sequential arm is *higher* on crab utility
(22,180 vs 21,588). The sign flips across seeds, so treat the crab-utility
comparison as noise. **The joint-surplus claim does replicate**: +$4,715 main,
+$3,347 confirm, along with the departure gap (18.3% vs 36.7%).

Decomposing the harness bug on the engine arm's joint surplus: relaxing the reply
rule alone **+$3,943**, allowing the base cut alone **+$6,184**, both **+$7,583**.
Either one on its own exceeded the gap I was reporting as a finding.

## 3. Corrections to the record

**"A human negotiator beats the engine" — RETRACTED.** It appeared in RESULTS-V4,
the article and the demo. It was an artifact. The engine wins at every matched
setting.

**K27's $5,056 ratchet — MISMEASURED.** v6 compared `slow_archetype3` (varies one
issue, never re-optimises) against `slow_reopen` (re-optimises the whole package),
and labelled the difference "the ratchet." Measured properly in v7, with both arms
sharing one employer, **banking concessions is worth $156** (19,090 vs 18,934).
The retraction K27 triggered still stands; its stated cause does not.

**K31's "the simulation is unreliable for the procedure question" — SUPERSEDED.**
The registered consequence offered "identify the mechanism" as the alternative and
this is it. With a symmetric employer, packages beat sequential bargaining,
consistent with [In & Serrano](https://www.sciencedirect.com/science/article/abs/pii/S0167268103000878)
and [Fatima, Wooldridge & Jennings](https://arxiv.org/pdf/1110.2765). The study
may speak to the question again.

**K28 stands.** Full offer history vs truncated is **−$1,038** — sequential
opponent modelling on an adversary's counters buys nothing here, because those
counters are its best replies and therefore an unrepresentative sample of its
tradeoffs. This does not contradict
[Baarslag et al.](https://dl.acm.org/doi/10.1007/s10458-015-9309-1); it is a
statement about what can be learned from a counterparty that only ever shows you
its cheapest acceptable move.

## 4. `their_batna_estimate` was a bare constant, and it dominates

`world.py:124` carried `their_batna_estimate: float = 0.45` with no comment and
no justification, imported from the rent study where the rationale was about
landlords. The engine ships **0.40**. It was never swept in a registered run.

| estimate | crab utility | joint |
|---|---|---|
| 0.20 | 20,914 | 10,446 |
| 0.40 — the engine's default | 20,046 | 10,369 |
| **0.45 — mine** | **19,531** | **10,296** |
| 0.60 | 17,243 | 9,674 |
| 0.80 | 12,627 | 8,024 |
| **the true value** | **20,858** | 10,326 |

Monotone and steep. The counterparty's true normalised walk-away behaves like
**≈0.20** — an employer facing a replacement bill has a terrible outside option —
so **0.45 was pessimistic and cost the employee $1,327**; a cautious user
guessing 0.8 loses **$8,287**.

**Product consequence:** the highest-leverage input in the multi-issue engine is
an unvalidated default, and the error is asymmetric — caution is expensive.

## 5. Peer mode — SUPERSEDED BY THE v8 ADDENDUM BELOW

| both sides on the engine | crab | Works | **joint** |
|---|---|---|---|
| adversarial, estimated BATNAs | 15,273 | −15,854 | **−581** |
| adversarial, **true** BATNAs | 20,478 | −17,003 | **+3,475** |
| **peer mode** | 20,728 | −15,557 | **+5,171** |

Two adversarial engines **destroy value** — v1's arm F reproduced. That stands.

Everything else this section originally claimed does not. It read the +$5,752
against the estimated-BATNA baseline as peer mode's value, and reported the crab
taking **95% of the gain**. **AMENDMENT 6 killed both.** Against the honest
baseline the protocol adds **+$1,697** (under the bar), and the 95% split is a
first-mover artifact. See the addendum. The one surviving reading: it is the
**truthful BATNA exchange** that works, not the mode — consistent with the
`cooperation` dial doing nothing measurable (15,811 → 15,833 → 15,856 across
0/0.5/1.0).

## 6. Scorecard

Predictions 1 and 4 of Amendment 5 were wrong (the ratchet was $156, not large;
the employer does **not** keep most of it under peer mode). Prediction 2 was wrong
(learning does not help). Predictions 3 and 5 held. Across five amendments:
**seven of seventeen**.

## 7. The process failure, stated plainly

Five harness defects in one study: K17's inert bias, arm G's missing acceptance
check, the probe arm's dropped counter, the single-shot inference, and now two
asymmetric employers. Every one produced a number in the direction I was leaning,
and every one was caught by refusing to accept a number that looked too good.

`tests/test_arms.py` asserts, for every arm, that the counterparty can refuse and
that engine calls carry a growing offer history. Three of the five would have
failed it.

The sixth assertion — `test_compared_arms_face_the_same_counterparty`, which
watches the arguments each arm hands the shared employer — is now written and
passing, and it is the one that would have caught the defect this file is about.
**It is not yet complete:** it covers `arm_engine` vs `arm_human` and not the duel
arms, which is exactly how K39 slipped through in the v8 addendum. Extending it to
every pair of arms that appear in the same table is the outstanding work.

---

# ADDENDUM — v8: the attacks on peer mode (AMENDMENT 6)

Peer mode was this study's headline and had never had a kill written against it.
Four were registered; **three fired**, including against a claim published on the
demo an hour earlier.

| arm | crab utility | Works | joint |
|---|---|---|---|
| adversarial, estimated BATNAs | 15,273 | −15,854 | −581 |
| adversarial, **true** BATNAs | 20,478 | −17,003 | **3,475** |
| peer mode (honest) | 20,728 | −15,557 | **5,171** |
| peer, crab lies +0.3 | 22,304 | −17,877 | 4,427 |
| peer, **Works proposes first** | **13,773** | −10,196 | 3,577 |

**K36 FIRES.** Against the honest baseline — adversarial with true BATNAs — peer
mode adds **+$1,697**, below the $2,253 bar. Against the rigged baseline it looked
like +$5,752. *Consequence, as registered:* peer mode as a distinct feature is not
supported. **The value is truthful BATNA exchange**, which requires no cooperative
selection and no peer protocol. The headline becomes "tell each other your
alternatives," not "use peer mode."

**K38 FIRES.** The 95%-to-the-employee split is a **first-mover artifact**. With
the Works opening, the same protocol leaves the crab at 13,773 instead of 20,728.
The figure is withdrawn from RESULTS-V6 §5, the article and the demo.

**K37 does not fire — but "incentive-compatible" is not the right word.** A crab
inflating its declared walk-away gains +$609 / +$1,010 / **+$1,576** at
δ = 0.1/0.2/0.3, and the Works gains +$846 at δ = 0.2. All under the bar, but
monotone increasing and tested only to 0.3. Correct statement: **lying pays a
little at the lies we tested.** Honesty being stable is untested.

**K39 is VOID.** It compared peer mode against a solo crab, but the duel's
employer is a `negotiate_bundle` agent and the solo arm's is `works_reply` — two
different counterparties, the exact defect the sixth assertion exists to catch.
`test_compared_arms_face_the_same_counterparty` covers `arm_engine` vs
`arm_human` and **not** the duel arms. The assertion is incomplete and no
individual-rationality claim is made.

**Scorecard:** one of four predictions. Across six amendments, **eight of
twenty-one**.

**What §5 above should now say:** two adversarial engines destroy value (−$581);
giving both sides each other's true walk-away recovers it (+$3,475); the
cooperative protocol on top adds $1,697, which does not clear the bar. The
result belongs to information exchange, not to the mode. And nothing is known
about how the surplus splits, because that turned out to be whoever speaks first.


---

# ADDENDUM 2 — v9: the held-out seed, and the gaps v8 left

`python3 research/molt/run9.py`. Three things v6–v8 never did.

**1. The confirmatory seed, finally.** v3 and v4 were read on held-out seed 101;
v6/v7/v8 were not. They are now, and the headlines hold:

| | main (7/11/23/31) | confirm (101) |
|---|---|---|
| K36 — peer mode over adversarial-with-true-BATNAs | +1,697 | **+1,254** |
| engine − sequential, matched employer (joint) | +4,715 | **+3,347** |
| adversarial duel with estimated BATNAs (joint) | −581 | +2,207 |

K36 fires on both. The one thing that does **not** replicate is the crab-utility
comparison in §2 — see the correction there.

**2. K39, redone with the employer guard.** v8's version compared a duel arm
against a solo arm. Restricted to the duel family, a crab in peer mode versus the
same crab in an adversarial duel with true BATNAs gains **+$250** (main) and
**+$64** (confirm) — no individual benefit either, consistent with K36. Against
the *estimated*-BATNA duel it gains +$5,455, which is the same rigged baseline
K36 already disposed of.

`run9.compare()` now refuses any comparison across employer implementations, and
`test_the_employer_guard_refuses_cross_family_comparisons` asserts it does.

**3. Lying, past where K37 stopped — and it is self-limiting.** v8 tested
inflations to 0.3, found a monotone rising gain, and I flagged that bigger lies
might clear the bar. They do not. The effect **turns over**:

| the crab inflates its declared walk-away by | main | confirm |
|---|---|---|
| +0.3 | +1,576 | +1,098 |
| +0.5 | **−556** | +132 |
| +0.7 | **−6,333** | **−4,371** |

There is an interior optimum and large lies backfire hard, because an implausible
walk-away makes the employer stop trying: departures rise from 15.6% to **25.6%**
(main) and 17.5% to **30.8%** (confirm). **Peer mode punishes big lies without any
enforcement** — the small ones still pay a little, and that remains the honest
caveat, but "a liar can run away with it" is refuted on both seeds.

---

# ADDENDUM 3 — how much leverage does an employee actually have?

Written after re-reading the sentence "the employee-side story never
worked in any specification." That sentence was wrong, and it was wrong in a way
this study had been set up not to notice: **every comparison here is
engine-versus-some-other-way-of-negotiating. None of them asked what negotiating
is worth against not negotiating at all** — even though arm A ("just sign the
standing offer") has been in the design since v1.

Symmetric employer (`cut=Y, strict=N`), five seeds including the held-out one,
600 crab-seasons, restricted to crabs retained in each arm:

| subgroup | share | just sign | engine | human | leverage (engine − sign) |
|---|---|---|---|---|---|
| everyone | 100% | 6,408 | 19,937 | 19,562 | **+13,529** |
| holds an outside offer | 32% | 8,367 | 42,111 | 39,107 | **+33,745** |
| offer **and** dear to replace | 17% | 7,446 | 51,511 | 45,994 | **+44,066** |
| offer but cheap to replace | 15% | 9,288 | 30,481 | 30,471 | +21,193 |
| no outside offer | 68% | 6,189 | 11,918 | 8,504 | **+5,729** |

**Employees have large leverage and it scales with exactly what theory says it
should** — the credibility of the alternative and the cost of replacement. An
offer-holder who is expensive to replace gains **seven times** what they would by
signing. Even a crab with no outside offer at all gains $5,729 by opening its
mouth.

**Correction to the record.** The claim that failed across seven amendments is
narrow: *this engine does not beat other ways of negotiating by more than 2% of
salary, and it pays you in perks rather than cash.* The claim that never failed —
because it was never tested until now — is that **negotiating beats not
negotiating, by a lot.** Any summary that runs the two together is wrong, and one
of mine did.

**The cash pattern survives this and sharpens.** In every subgroup the human
negotiator delivers more cash than the engine (10,338 vs 6,418 overall; 3,170 vs
949 among crabs with no outside offer, where the engine pays almost entirely in
perks). Leverage is real; how the engine converts it is still the open problem.


---

# ADDENDUM 4 — the replacement-cost calibration is probably too high

Found while sourcing the salary tool's evidence module, not by re-running
anything. `rho` in this study was **0.45–1.60 x salary**, taken from the SHRM /
Gallup range as recycled by trade press, and swept only down to 0.5x.

The [Center for American Progress review of economic studies](https://www.americanprogress.org/article/there-are-significant-business-costs-to-replacing-employees/)
puts the **median at 21% of salary** for everything except executives and
physicians, and 16% below $30k. That is roughly a quarter of what this study
used, and **below the bottom of the swept range**.

Replacement cost is 80% of the headline channel. If the academic median is right,
the magnitude of the clock finding is inflated by something like 2–4x. The
*direction* survives — the rho sweep at 0.5x still gave +$19,236 — but no number
in this study that scales with rho should be quoted without this attached.

This is the same failure mode as the rent study's "one to three months" turnover
cost, which traced back to a property-management blog citing nothing. I took the
industry figure because it was the one that came up first, in a study whose whole
subject is being wrong in the direction you were already leaning.

---

# ADDENDUM 5 — item 0 closed: the equal-speed claim, on the fixed harness

The three kills that retired the money-at-equal-speed claim (K8, K14, K19) were
all measured before the two arms were made to face the same employer. `run7`
fixed the harness and only ever ran with the clock on. Run with it off:

| employer's rules | clock ON | **clock OFF** |
|---|---|---|
| floored at its offer, counters only when it pays | +2,271 | **+1,532** |
| floored, always counters | +5,623 | **+4,616** |
| may cut base, counters only when it pays | +5,022 | **+3,938** |
| may cut base, always counters | +6,209 | **+4,585** |

Engine minus sequential, joint surplus, five seeds including the held-out one.

**The engine wins at equal speed at every setting**, and clears the $2,253 bar at
three of four. At the headline setting the advantage is +$4,585 with no clock at
all — 74% of the clock-on figure.

**This reverses K8, K14 and K19.** The bar did not move: the instrument was
defective, exactly as with K27's mis-measured ratchet. Those verdicts stand as
descriptions of what was measured at the time, and are superseded as descriptions
of the world.

Two things this does not license. The money advantage is **joint** — how it splits
is a separate question and every split measured in this study went ~90% to the
employer. And this is the correction that runs *in the product's favour*, arriving
after seven that ran against it, which is precisely the direction to distrust. It
is reported because it was run, not because it was wanted.

---

# ADDENDUM 6 — the replacement-cost disagreement, swept

Addendum 4 flagged that `rho` came from the trade side of a literature that
disagrees with itself by an order of magnitude, and that the academic median
(0.21x salary) sits below the bottom of the swept range. The right response was
to sweep further, not to caveat.

Engine minus sequential, joint surplus, symmetric harness, five seeds:

| replacement cost | clock ON | clock OFF |
|---|---|---|
| academic median, 0.21x salary | **+7,544** | **+5,611** |
| half what the study used | +6,168 | +5,407 |
| what the study used, 0.80x | +5,704 | +4,121 |
| trade mid, 1.25x | +5,877 | +4,694 |
| trade high, 2.0x | +4,836 | +4,127 |

**Direction invariant across a 10x range, clock on or off.** The academic value
produces a *larger* advantage than the one the study used, so the conservative
reading of the disagreement is the favourable one.

**What still scales with rho:** the channel decomposition. "Four-fifths of the
cost of a slow negotiation is people walking out" is a statement about
composition, and a cheaper replacement makes that share smaller. It has not been
re-decomposed at the academic value, and Addendum 4's warning stands for that
claim specifically. It does not stand for the headline comparison.

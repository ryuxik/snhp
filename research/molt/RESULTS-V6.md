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

The engine also wins the crab's own utility in all four cells (+$597 to +$3,204).

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

## 5. Peer mode is the one clean positive result in the study

| both sides on the engine | crab | Works | **joint** |
|---|---|---|---|
| adversarial, estimated BATNAs | 15,273 | −15,854 | **−581** |
| adversarial, **true** BATNAs | 20,478 | −17,003 | **+3,475** |
| **peer mode** | 20,728 | −15,557 | **+5,171** |

Two adversarial engines **destroy value** — v1's arm F reproduced. Two peer-mode
engines create **+$5,752** against that baseline, and **the crab takes 95% of the
gain**, inverting the ~90%-to-the-employer split that every adversarial arm in
this study produced.

**But 70% of it is just knowing each other's true walk-away** (+$4,056 of the
$5,752). The `cooperation` dial alone does nothing measurable (15,811 → 15,833 →
15,856 across 0/0.5/1.0). It is not cooperative *selection* that works — it is the
truthful BATNA exchange, which is exactly what the attestation gate buys.

## 6. Scorecard

Predictions 1 and 4 of Amendment 5 were wrong (the ratchet was $156, not large;
the employer does **not** keep most of it under peer mode). Prediction 2 was wrong
(learning does not help). Predictions 3 and 5 held. Across five amendments:
**seven of seventeen**.

## 7. The process failure, stated plainly

Five harness defects in one study: K17's inert bias, arm G's missing acceptance
check, the probe arm's dropped counter, the single-shot inference, and now two
asymmetric employers. Every one produced a number in the direction I was leaning,
and every one was caught because a reader refused to accept a number that looked
wrong.

`tests/test_arms.py` now asserts, for every arm, that the counterparty can refuse
and that engine calls carry a growing offer history. Three of the five would have
failed it. **A sixth assertion is needed and is not yet written: that any two arms
being compared instantiate the same counterparty.** Nothing in this file's
comparisons is safe until that exists.

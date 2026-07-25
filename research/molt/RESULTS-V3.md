# RESULTS v3 — Molt Season under PREREG AMENDMENT 2

**The kill we agreed on up front fired.** K14 said: if giving the employer real
budget structure does not lift the equal-speed gain above $6,090, then logrolling
has been tested properly and found small, and the product claim goes with it.

It came in at **+$5,397**. It fires by **$693**.

On the held-out seed it comes in at **+$5,944** against a $6,154 threshold — it
fires by **$210**. Twice, narrowly, in the same direction. The bar does not move.

Exploratory by construction, like Amendment 1. Reproduce:

```bash
python3 research/molt/run3.py && python3 research/molt/analyze3.py
python3 research/molt/run3.py --confirm
```

---

## The headline, led with cash (K15 requires it)

Verifiable regime, 1,920 crab-seasons per arm, mean salary $112,644, bar $2,253.

| arm | **crab CASH** | crab utility | the Works | joint | days | departures |
|---|---|---|---|---|---|---|
| just sign it | 4,913 | 13,636 | −37,749 | −24,113 | 1.0 | 29.4% |
| six weeks of email (best archetype) | **10,077** | 15,884 | −51,655 | −35,771 | 47.5 | 35.7% |
| **one sitting** | **6,906** | 19,410 | −23,646 | **−4,236** | 3.6 | 14.5% |

**The engine takes $3,172 of cash out of the employee's pocket** and hands back
perks. On the selection-free subset — crabs the Works retains under both
protocols, n=1,191 — it is worse: **cash $16,065 → $9,147, a $6,918 cut**
($8,191 on the held-out seed).

That is now the first number in every write-up, because K15 fired and the
amendment says it must be.

## Kill verdicts

| kill | verdict |
|---|---|
| **K14** does budget structure rescue logrolling | **FIRES** — +$5,397 vs a $6,090 threshold, and +$5,944 vs $6,154 on the held-out seed |
| **K15** cash, not utility | **FIRES** — −$3,172 population, −$6,918 selection-free |
| **K16** the break-even | does not fire — break-even is **below 0.5×**, the bottom of the swept range |
| **K17** who sets the exchange rate | **VOID — defective instrument.** No verdict. See below |
| **K18** did PTO matter | does not fire — PTO is the **second most-granted** non-cash term (36%, behind berth at 37%) |

### K14: budget structure helped, and not enough

The objection behind this amendment was right about the mechanism and wrong about
the size. Giving the Works five pockets instead of one moved the equal-speed gain
from v2's **+$3,837 to +$5,397** — a real **+41%**. I predicted it would roughly
double. It did not, and the registered threshold was set at double-ish for
exactly this reason.

| | equal-speed joint gain |
|---|---|
| v2 — one scalar cost pot | +$3,837 |
| v3 — five budgets, six issues, promotion slots that can be unavailable | **+$5,397** |
| K14 threshold | $6,090 |

**Consequence, as registered:** the equal-speed money claim is retired. With both
sides moving at the same speed, against a real corporate strategy, with a
properly structured employer, multi-issue bundling is worth less than 2% of
salary above what a competent single-issue bargainer gets. In the **unverifiable**
regime it is worth **−$630** (main) and **+$12** (confirm) — i.e. nothing at all.

What survives is the clock: **+$31,535 joint with the calendar running**, and
departures cut from 35.7% to 14.5%.

I want the margin on the record rather than buried: this fired by $693 and by
$210. A bar set 11% lower would have passed it. The bar was set before the run
and it is not moving — that is the whole point of setting it first — but anyone
reading this should know it was close, and that the direction of the miss was
consistent across two independent seeds.

### K15: the employee is paid in my exchange rate

The engine reliably converts the employee's cash into non-cash terms. Across the
perk-rate sweep the cash effect is negative **at every rate tested**:

| perk rate | crab utility | **crab CASH** | equal-speed joint |
|---|---|---|---|
| 0.50× | +1,482 | **−2,209** | 2,282 |
| 0.75× | +2,134 | **−2,041** | 3,446 |
| 1.00× | +2,728 | **−2,452** | 4,353 |
| 1.25× | +3,580 | **−2,557** | 5,809 |
| 1.50× | +4,566 | **−2,567** | 6,828 |

### K16: the utility gain is more robust than v2's, the cash loss is not

In v2 the employee's utility gain broke even between 0.5× and 0.75× — it needed
my invented perk rates to be at least three-quarters right. In v3 it **does not
cross zero anywhere in the swept range**: even valuing perks at half what I said,
the crab gains +$1,482 in utility.

That is a genuine improvement in robustness, and it comes from the same change
that fired K14 — giving the employer cheap currencies (PTO at ~0.35× cash cost,
band slots at ~0.60×) means it can hand over things worth more than they cost
even at heavily discounted valuations.

My registered prediction that break-even would land between 0.5× and 0.75× is
**refuted**; it is below the range I thought to sweep.

But note what this robustness *is*: the employee's **utility** gain is robust and
the employee's **cash** loss is robust. Both. At every rate. The engine is
reliably converting one into the other, and how good a deal that is depends
entirely on an exchange rate that neither the employee nor I can verify.

### K17 is VOID — I broke the instrument

`E_biased` came out **bit-identical** to `E_sitting_works` in both regimes and on
both seeds: +$0 cash, +$0 utility, +$0 to the Works. That is not a null result,
it is a dead measurement.

The defect is in [`arms3.py:244-266`](arms3.py): the biased exchange rate is
built into a `view` object that is used in **exactly one place** — an early-stop
check on whether the Works believes the crab is satisfied. It never enters
`works_issues3`, `works_npv3`, `works_signs3`, or anything the Works uses to
decide what to *propose* or *accept*. If that stop condition does not bind, the
arm is identical by construction, which is precisely what happened.

**No verdict is recorded for K17.** The question it was built to answer — whether
an employer configuring this tool to believe your perks are worth 1.5× extracts
more cash from you — remains open, and given K15 it is now the most important
open question in the study. Repairing it means routing the biased rate through
the Works' acceptance test, so it evaluates what the crab will accept using the
inflated valuation. That is a repair rather than a new mechanism, but it is a
repair made after seeing a result, so it needs registering before it is run.

### K18: PTO was not cosmetic

Added because it was named as an obvious omission. It is the **second
most-granted non-cash term** under the engine (36%, behind flexible berth at 37%,
ahead of deepwater at 27% and the promotion at 24%; on the held-out seed 43% vs
44%). Cheap at the margin, valuable to whoever wants it, and the engine finds it.
The issue set in v1 and v2 was thin, and that was worth fixing.

## Scorecard on my registered predictions

| | prediction | outcome |
|---|---|---|
| 1 | K14 does not fire — structure roughly doubles the gain | **REFUTED** — +41%, not +100%; fires by $693 |
| 2 | K15 fires — cash stays negative | **CONFIRMED** — −$3,172, and negative at every perk rate |
| 3 | break-even lands between 0.5× and 0.75× | **REFUTED** — below 0.5× |
| 4 | K17 fires | **VOID** — I broke the instrument |

One of four. The registration did its job and my intuitions did not.

## What may now be said

**Dead:** the equal-speed money claim, in both directions. Bundling at the same
speed, against a real strategy and a structured employer, is worth less than the
bar — and nothing at all where outside offers cannot be verified.

**Leads every write-up:** the engine cuts the employee's cash by $3,172
(population) or $6,918 (selection-free), and pays them back in perks priced at a
rate nobody can verify.

**Survives:** the clock. +$31,535 joint with the calendar running, departures
35.7% → 14.5%. That is what this product is worth and it is worth it for a reason
that has nothing to do with negotiation math.

**Survives:** the employer captures the overwhelming majority of it.

**Open, and now the sharpest question in the study:** who sets the exchange rate.
K17 was built to answer it and did not run.

## Limitations carried forward

Unchanged from v2: the attrition hazard is still the load-bearing and least
defensible parameter; ~29–36% annual departures is a world where everyone is in
play; the Works still knows the crab's priorities exactly; no equilibrium
response; no humans. New to v3: the shadow-price medians (band 0.60, accrual
0.35, coverage 0.50, capacity 0.80) are my estimates and are not swept — and
since they are what rescued 41% of the equal-speed gain, they deserve a sweep
before anyone leans on that number.

# PREREG AMENDMENT 2 — the employer had one pocket

*Written 2026-07-25, after v2 results were read and after a measurement that
should have been in v1. Exploratory by construction, like Amendment 1. Written
before any v3 code exists.*

---

## A2.0 The measurement that forced this

v2 reported the crab's outcome as utility — cash plus the subjective value of
non-cash terms. Decomposed, on crabs retained under both protocols:

| | crab utility | of which cash | of which subjective | employer cost |
|---|---|---|---|---|
| six weeks of email | 19,404 | 16,295 | 3,109 | 21,275 |
| one sitting | 20,191 | **10,439** | **9,753** | 14,789 |
| **engine − slow** | **+788** | **−5,856** | **+6,643** | −6,485 |

**In cash the engine makes the employee $5,856 poorer.** The whole employee-side
win is perks priced at exchange rates I chose — a promotion at 9% of salary,
flexible hours at 6%, the growth assignment at 7% — and never swept. Swept now:

| perk rates | crab utility | crab cash |
|---|---|---|
| 0.50× | **−237** | −3,905 |
| 0.75× | +115 | −5,185 |
| 1.00× (shipped) | +788 | −5,856 |
| 1.50× | +2,151 | −7,010 |

Break-even sits between 0.5× and 0.75×. If a promotion is worth 6% of salary
rather than 9%, the employee's gain is negative.

**Suspended immediately, no re-run needed:** the +$624 both-stay crab gain and
the +$500 equal-speed crab gain from v2. Both are artifacts of an unswept
exchange rate, and the cash figure is negative in every specification run.

## A2.1 The defect this exposes

`works_cost` sums all five issues into **one scalar pot of dollars**. So the
employer has exactly one currency, there is exactly one trade axis (cash versus
non-cash at fixed ratios), and the same trade is optimal for every crab in the
world. A logroller has almost nothing to find.

**So v2's K8 verdict is also suspended.** The small equal-speed gain (+$3,837
verifiable, +$277 unverifiable) may be a finding about a badly specified employer
rather than a finding about logrolling. That is what this amendment tests.

---

## A2.2 The Works gets pockets

Five budgets, each with its own shadow price, none of them proportional to the
others. Every issue draws on exactly one.

| budget | drawn on by | why its price differs |
|---|---|---|
| **comp** | base raise, retention bonus | the cash line; the numeraire |
| **band** | the molt (promotion) | a *slot*, not money — constrained by band ratios |
| **accrual** | PTO | a balance-sheet liability, nearly free at the margin |
| **coverage** | flexible berth | a staffing constraint, not a budget |
| **capacity** | deepwater assignment | somebody must absorb the work |

Shadow prices are drawn **once per season and shared by every arm and every crab
in that season**, so the comparison stays paired and the variation models a real
comp cycle ("comp is tight this year, PTO is fine"):

| | draw | mean multiplier on the v2 cash cost |
|---|---|---|
| `lam_comp` | lognormal(0, 0.25) | 1.00 |
| `lam_band` | lognormal(ln 0.60, 0.50) | 0.60 |
| `lam_accrual` | lognormal(ln 0.35, 0.40) | 0.35 |
| `lam_coverage` | lognormal(ln 0.50, 0.40) | 0.50 |
| `lam_capacity` | lognormal(ln 0.80, 0.40) | 0.80 |

Plus a hard constraint money cannot solve: **with probability 0.25 there is no
promotion slot in this crab's band this season**, and the molt is unavailable at
any price. Registered now because it is the kind of thing that makes a real
negotiation multi-dimensional, and because it cuts *against* the engine.

The mechanism under test: because the five shadow prices move independently of
the crab's five valuations, **which trade is best now differs from crab to crab
and season to season**. Under v2's single pot it was the same trade for
everybody, which a one-issue-at-a-time bargainer can stumble onto.

## A2.3 PTO

Sixth issue, three options: **+0 / +5 / +10 days**.

- worth to the crab: `days/260 × salary`, scaled by the crab's own weight
- costs the Works: `lam_accrual × days/260 × salary`

Named in the objection, absent from v1 and v2, and the cleanest example of the
asymmetry the whole thesis rests on: expensive on the books, cheap at the margin,
valuable to whoever wants it.

## A2.4 Cash is reported everywhere, next to utility

Every table in v3 carries a **cash column beside the utility column**. No result
is stated in utility alone. The perk-rate multiplier is swept over
{0.5, 0.75, 1.0, 1.25, 1.5} and **the break-even is a headline number, not a
footnote**.

---

## A2.5 Kills (binding, bidirectional, before any v3 output)

Bar unchanged: **2% of salary ≈ $2,253**.

**K14 — DOES BUDGET STRUCTURE RESCUE LOGROLLING.** With the clock off, if the
engine's joint advantage over the best archetype at `best_first` does not exceed
v2's **+$3,837** by at least the bar — i.e. if it lands below **$6,090** — then
logrolling has been given a properly structured employer and found small.
*Consequence:* the product claim goes with it, and the article says the equal-
speed money story is dead in both directions. **This is the kill agreed up front.**

**K15 — CASH, NOT UTILITY.** If the engine's effect on the crab's cash is
negative at the shipped rates, the demo and the article must **lead with the cash
figure** and may not headline the utility figure.

**K16 — THE BREAK-EVEN.** Report the perk-rate multiplier at which the crab's
utility gain crosses zero. If it is above **0.75×** — i.e. the result needs my
invented rates to be at least three-quarters right — the employee-side claim is
labelled rate-dependent wherever it appears.

**K17 — WHO SETS THE EXCHANGE RATE.** Arm E is re-run with the employer's engine
valuing the crab's perks at `employer_rate_bias = 1.5×` their true worth — the
bias an employer configuring the tool would have, since overstating what perks
are worth to you is how it pays less cash. If the crab's cash under the
employer-configured engine is worse than under the crab-configured engine by more
than the bar, that is a named risk on the demo, in those words.

**K18 — DID PTO MATTER.** If PTO is not among the two most-granted non-cash terms
under the engine, adding it was cosmetic and is reported as such.

## A2.6 On-record predictions

1. **K14 does not fire** — budget structure roughly doubles the equal-speed gain.
   The objection behind this amendment is sound and I expect it to be vindicated.
2. **K15 fires** — the crab's cash stays negative. Giving the employer *cheaper*
   currencies should make substituting away from cash easier, not harder.
3. **K16: break-even lands between 0.5× and 0.75×** — better than v2, still
   rate-dependent.
4. **K17 fires** — a 1.5×-biased employer engine extracts materially more cash.

## A2.7 Stopping rule

Unchanged and re-affirmed. If a kill fires it is reported; nothing is added
afterwards to un-fire it. Seeds 7/11/23/31 main, 101 held out.

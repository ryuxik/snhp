# PREREG AMENDMENT 3 — a promotion is a level change, and slots are rivalrous

*Written 2026-07-25, after v3 results were read and after K14 fired. Exploratory,
like Amendments 1 and 2. Written before any v4 code exists.*

---

## A3.0 The guard, stated first because this is the dangerous one

K14 fired against the product two hours ago. This amendment makes the product's
best currency bigger and better. **That is exactly the move a stopping rule
exists to prevent**, so the rule is written before anything else:

> **K14's verdict is permanent for the world it tested** — a world in which a
> promotion is a 2% raise plus a private feeling. Nothing in this amendment
> revises it. Whatever v4 finds is a **new test of a different world**, reported
> beside K14 and never in place of it. If v4's equal-speed gain clears the bar,
> the claim it licenses is conditional on portable, rivalrous promotions, and
> that condition is stated every single time the number is.

Note also that this objection can hurt the product as easily as help it: **K15**
(the engine cuts the employee's cash by $6,918) may itself be an artifact of
pricing promotions at 2%. K22 below tests that, and I am not permitted to keep
K15 if it does not survive.

## A3.1 What the code actually does today

| the claim | the code |
|---|---|
| a promotion is tied to salary | `title_drift = 0.02` — a 2% raise |
| a promotion is tied to reputation inside **and outside** | a promotion never touches `omega`; zero market effect, non-portable by construction |
| limited slots are an internal budget separate from cash | `Season.slot` is a per-season **boolean**. If true, every crab that season may be promoted. No quota, no rivalry, no consumption |

Amendment 2's text describes what was built. But describing it as "band slots, a
constraint money cannot solve" oversold it, and that phrasing is withdrawn.

## A3.2 A promotion becomes a level change

- **`promo_raise = 0.12`** of salary, replacing the 2% drift. Swept over
  {0.06, 0.12, 0.20}. Typical level changes run well above 2%; 12% is a middle
  estimate and it is swept because it is mine.
- The raise draws on the **comp** budget; the slot draws on the **band** budget.
  A promotion now costs the employer out of **two pockets**, which is the thing
  that makes it a different object from a perk.

## A3.3 Portability

- **`promo_market_lift = 0.05`**: promoting a crab raises its outside premium
  `omega` by 5 percentage points, in the true leave decision *and* in the Works'
  belief. Promote someone and they become more poachable.
- The employer therefore internalises flight risk automatically through
  `P(leave)`, and the crab's improved outside option is real rather than
  sentimental.

Direction is genuinely ambiguous and that is why it is worth running: the raise
and the career value pull retention up, portability pulls it down.

## A3.4 Rivalrous slots

- **`slot_frac = 0.12`** — the Works has `ceil(0.12 × n_crabs)` promotion slots
  per season. Roughly one crew member in eight.
- Crabs are processed in a **fixed order, identical across every arm**. Each arm
  consumes its own quota. When the quota is gone, the molt is infeasible at any
  price.
- **Disclosed cost:** this breaks strict state-pairing between arms — arms
  diverge in *who* got a slot, not just in what each crab was offered. Paired
  per-crab differences are still reported; the caveat travels with them.

## A3.5 Kills

Bar unchanged: **2% of salary ≈ $2,253**. Threshold from A2: **$6,090**.

**K19 — THE EQUAL-SPEED CLAIM, SECOND SPECIFICATION.** If the equal-speed joint
gain over the best archetype misses $6,090 again, the equal-speed money claim is
**dead across two independently specified promotion models and retired
permanently**. If it clears, the claim survives only as *conditional on portable,
rivalrous promotions*, with that condition attached wherever it appears.

**K20 — DOES AN OPTIMISER ALLOCATE SCARCITY BETTER?** Scarce slots are where an
optimiser ought to shine. Measured: the correlation between granting a slot and
the retention value that slot buys (`replacement_cost × reduction in P(leave)`).
If the engine's targeting correlation does not exceed the best archetype's by at
least 0.10, the "optimisers allocate scarce resources better" story is false and
is not told.

**K21 — THE FLIGHT-RISK TRAP.** If promoted crabs depart at a *higher* rate than
comparable unpromoted ones, a promotion is a retention anti-tool and that goes in
the results in those words.

**K22 — DOES THE CASH CUT SURVIVE A REAL PROMOTION?** If the engine's effect on
the crab's cash is no longer negative once a promotion carries a 12% raise, then
**K15's verdict was conditional on promotions being tiny** and is downgraded to
exactly that. I am not permitted to keep the cash headline if this fires.

## A3.6 On-record predictions

1. **K19 clears $6,090, but modestly** — somewhere around $8–10k.
2. **K20 fires.** My engine is myopic and first-come-first-served; I do not
   believe it allocates scarcity well, and this is the prediction I would most
   like to be wrong about.
3. **K21 shows a small rise** in departures among the promoted.
4. **K22 does not fire** — the cash effect shrinks but stays negative.

## A3.7 Reproducibility

The v3 code is extended in place with backwards-compatible defaults
(`promo_raise=None`, `promo_market_lift=0.0`, `slot_frac=None`), so v3's results
remain byte-reproducible. That is verified by re-running v3 and diffing before
any v4 result is read.

Seeds unchanged: 7/11/23/31 main, 101 held out.

# SPEC — implementation of PREREG.md

*Written 2026-07-25, after PREREG.md and BEFORE the main run. PREREG is binding
and unedited. This file records the choices PREREG did not pin down, so that
"we did not tune to pass a kill" is auditable. Where a choice plausibly moves a
kill, the direction it moves it is stated and it is swept.*

---

## 1. Accounting convention

Everything is PV over 3 years at 7%, **relative to the Works' opening offer**,
so arm A ("SIGN IT") has zero concession cost by construction and every other
arm is measured against it.

`rho` (replacement cost as a multiple of salary) is the all-in Gallup/SHRM
figure and already contains vacancy and ramp. Vacancy days are therefore carried
for narrative only and never enter a dollar total. Counting them again would
inflate exactly the number the demo headlines, so they are not counted.

## 2. What the Works maximises

The Works is a payoff-maximiser over `-(1-P_leave)·cost(package) - P_leave·ρ·S`.
It does **not** value crab happiness except through `P_leave`. This is the
unsentimental firm, and it is the conservative choice: a firm that valued morale
directly would grant the cheap non-cash terms readily, and the whole logrolling
gap would shrink.

## 3. `counter_thresh` — the free choice that matters most

PREREG says the Works' concession budget is identical across arms; it does not
say when the Works signs versus counters. Measured on 80 pilot crabs: with a
"signs anything weakly better than holding firm" rule, the Works left more than
0.5% of salary on the table in **17 of 37** immediate signings. That is a
pushover, and it flatters every engine arm.

Rule adopted: **the Works signs iff countering would gain it ≤ `counter_thresh`
= 0.5% of salary.** A higher threshold is more generous to the engine arms, so
it is swept over {0, 0.005, 0.02}. At 0 the Works always counters with its own
argmax.

## 4. The agenda in the slow arms

Fixed order: **base → bonus → berth → title → deepwater**. Money first, and base
is settled before anything else is raised. This *is* the mechanism under test
(sequential bargaining anchored on the expensive issue), not an incidental
choice, so it is stated rather than swept: a slow arm that happened to negotiate
in the efficient order would not be the slow arm anybody has ever sat through.

One meeting per issue, nothing revisited. Both slow arms may take up to 5
meetings; the sitting arms get 3 engine rounds. The slow arms get **more**
chances to reach agreement, never fewer.

## 5. Arm C's binary issues

`negotiate_turn` speaks prices, and three of the five issues are yes/no. For
those, arm C's crab asks exactly as arm B's does. Registered here so that arm C
is understood as "the engine on the two money issues, one at a time," which is
the fairest single-issue reading available.

The money issues are handed to the engine denominated in **3-year total comp**
(`salary·PVF + issue value`), so every quantity is a positive dollar amount, and
the crab is the SELLING side.

## 6. Offer expiry does not change the bargaining

If the crab's outside offer lapses mid-talks, that shows up only in the final
leave decision, not in weaker asks during the talks. A real crab would lose
leverage the moment its alternative died. Modelling it this way makes the **slow
arm look better than it is**, so it is conservative for the claim under test.

## 7. Common random numbers

Every arm sees the same crabs, the same taste shock (`u_taste`), the same
attrition draw (`u_haz`), and the same meeting-delay sequence (`delays`), drawn
once per crab-season before any arm runs. Differences between arms are therefore
paired, and standard errors are paired standard errors.

## 8. What is NOT modelled, and would change the answer

- **No reputation or repeat play.** Seasons are independent draws; the Works does
  not learn that crabs who negotiate get more, and crabs do not learn from each
  other. The rent study found broadcast adoption hurts non-askers; nothing here
  can see that effect.
- **No fairness or anger.** A crab who feels lowballed does not retaliate, and a
  manager does not resent being negotiated with. The divorce study's pettiness
  tax has no analogue here.
- **No manager quality variation.** Every manager plays the Works' NPV exactly.
  Real slow negotiations are worse than this, which again is conservative.
- **No information asymmetry about performance.** Both sides know `perf`.

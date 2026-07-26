# PREREG AMENDMENT 7 — put a manager between the firm and the crab

*Written 2026-07-25, before any v10 code exists. Exploratory, like 1–6.*

---

## A7.0 The puzzle this exists to explain

The menu is **iso-cost to the employer by construction** — it costs the firm
nothing beyond the package it was already going to sign, and hands the employee
+$492 to +$2,841 depending on how perks are priced. Joint surplus rises $4,347
against six weeks of haggling.

A model that says there is free money on the floor, in a world that does not pick
it up, is a model with something missing. The first candidate is that **there is
no manager in it.** The firm's payoff is the firm's; the person who would actually
offer a menu is a line manager whose bonus is not the firm's NPV.

This is not a hunch. In the rent study, a leasing agent paid on occupancy rather
than profit was **the only mechanism that moved the institution toward observed
behaviour** — after risk aversion, comp noise, portfolio size and menu costs had
all come out inert across six ablations.

**Note the direction of interest.** I want a stronger case for the product. That
is exactly why the kills below are written first and bidirectionally: if the
manager blocks the menu, that is a finding against deployability and it gets
reported as one.

## A7.1 The wedge

The firm bears the full replacement cost of losing someone. The manager bears it
only partly, and late, and diffusely — while a comp-budget overrun is legible,
immediate and theirs. Two parameters:

- **`manager_alpha`** — the share of replacement cost the manager internalises.
  1.0 is a perfectly aligned manager; **0.2 is the realistic case**, where losing
  someone is mostly the firm's problem. Swept {0.2, 0.5, 1.0}.
- **`manager_beta`** — extra penalty on spend that lands specifically on the
  **comp budget** (base raise, bonus, the raise attached to a promotion), over
  and above its cash cost. Swept {0, 0.3}. Perks drawn from accrual, coverage,
  capacity and band budgets carry no such penalty.

Every negotiating decision — what to counter with, what to sign, what to put on
the menu — is made on the **manager's** payoff. Everything reported is still the
**firm's**. That gap is the mechanism.

## A7.2 Kills

Bar: **2% of salary ≈ $2,253**.

**K40 — DOES THE MANAGER BLOCK THE MENU?** With a realistically misaligned
manager (α = 0.2, β = 0.3), if the menu's advantage to the employee over six
weeks of haggling falls below the bar, then the manager is the reason this does
not already happen, and the product has to route around them rather than through
them. *If it survives, the manager is not the explanation and I need another one —
and I say so.*

**K41 — WHO PAYS FOR THE MISALIGNMENT?** Report the firm's loss and the
employee's loss from α = 1.0 → 0.2 separately. If the **firm** loses more than the
employee, the buyer is the firm — this is sold as manager governance, not as an
employee tool. If the **employee** loses more, it is an employee tool and the firm
will not fund it.

**K42 — IS THE MENU ACTUALLY MANAGER-ALIGNED?** The menu pays in perks, which
come out of budgets the manager is not judged on. So a budget-squeezed manager may
*prefer* it. Measure comp-budget spend under the menu versus under haggling. If
the menu delivers the same retention at materially lower comp-budget spend, then
it is aligned with the manager's incentives, the puzzle deepens rather than
resolves, and the honest product claim is **"keep them without touching your comp
budget."**

**K43 — DOES MISALIGNMENT CHANGE WHO WINS?** Re-check the menu against haggling
and against just-signing under the misaligned manager. Any reversal is reported.

## A7.3 On-record predictions

1. **K40 does not fire** — the menu survives a misaligned manager, because it is
   cheap in exactly the currency the manager is squeezed on.
2. **K41: the firm loses more than the employee.** Attrition is the firm's bill.
3. **K42 does not fire** — comp-budget spend falls under the menu. This is the
   prediction I most want to be true and therefore the one to distrust.
4. **K43** — no reversal; ordering holds.

## A7.4 The standing risk, restated

This amendment was requested with an explicit goal of strengthening the case for
the product. Three of the five instrument defects in this study appeared exactly
when I was leaning somewhere. Every arm here must pass `tests/test_arms.py`,
including the sixth assertion, before a number is read.

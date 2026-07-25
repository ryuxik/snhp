# PREREG AMENDMENT 4 — the engine has no selfish mode, and a menu it doesn't need to guess

*Written 2026-07-25, after v4 and after a diagnostic ablation. Exploratory, like
Amendments 1–3. Written before any v5 code exists.*

---

## A4.0 The diagnosis this is built on

v4 found the crab's own engine losing to an ordinary human archetype on the
crab's own utility function, selection-free: **−$2,652 to −$3,050** across six
archetypes, and −$5,587 in the ablation sample.

An ablation over every knob, against the human's utility of $23,797:

| engine variant | crab utility | vs human | crab cash | vs human |
|---|---|---|---|---|
| base — Nash, batna .45, 3 rounds | 18,210 | −5,587 | 9,172 | −8,587 |
| `their_batna_estimate` = .20 | 18,997 | −4,800 | 9,735 | −8,024 |
| `their_batna_estimate` = .70 | 15,570 | −8,227 | 7,369 | −10,390 |
| `max_rounds` = 12 | 18,582 | −5,216 | 9,538 | −8,220 |
| `counter_thresh` = .05 | 17,939 | −5,858 | 8,976 | −8,783 |
| **selfish selector** | **25,948** | **+2,151** | **18,830** | **+1,072** |

**Tuning moves it ±$800. Changing the selection rule moves it $7,738.**

Confirmed in the engine's source: `_resolve_cooperation` returns 0.0 on the
adversarial path, and `_select` scores
`(1-cooperation)·nash + cooperation·joint`. The dial runs from the **Nash
product** to **joint welfare**. Both credit the counterparty's gain. **There is
no "maximise my own payoff subject to their acceptance" mode**, which is what a
tool sold to one side of a table is for.

The Nash point is why the title gets traded away: swapping a promotion
(expensive to the employer, valuable to the crab) for PTO (cheap to the employer)
lowers the crab's utility slightly and raises the employer's a lot, which raises
the product. Even-handedness, applied by an agent hired to be partisan.

**The selfish selector above is an upper bound**: it uses the employer's *true*
cost function. The shippable version must infer it. That is what A4.1 tests.

## A4.1 Arm G — SELFISH SELECTION on inferred costs

Same pipeline as the shipped engine — `negotiate_bundle` runs, the particle
filter infers the counterparty's priorities from their offers — but the final
selection changes: among packages whose **inferred** counterparty utility clears
their **estimated** BATNA, take the crab-max instead of the Nash point.

The inference is the product's own and carries its own error. Nothing is given to
this arm that the shipped engine does not already compute.

## A4.2 Arm H — THE MENU, under preference noise

The founder's design: present several acceptable packages, let the asking party
choose. A scoping estimate put a 3-item menu inside a 1% employer tolerance at
**+$3,593 of crab utility for $1,080 of employer cost** — a 3.3× leverage ratio,
the best in the study.

But that estimate is understated by construction, because in this world the
engine already knows the crab's utility exactly. **A menu's real advantage is
that it does not have to guess**, and a model that never guesses wrong cannot
show it. So:

- the engine's model of the crab's per-option utility is perturbed by lognormal
  noise **σ_pref ∈ {0, 0.25, 0.50}**
- **H1**: one package, chosen under the noisy model
- **H2**: a menu of 3 within a 1% employer tolerance, generated under the noisy
  model, chosen by the crab's **true** utility

The menu's value is exactly the estimation error it routes around, so it must
grow with σ. If it does not, it is not doing what it is claimed to do.

## A4.3 Kills

Bar: **2% of salary ≈ $2,253**.

**K23 — IS SELECTION REALLY THE DEFECT?** If arm G, on *inferred* costs, does not
beat the base engine on crab utility by at least the bar, my diagnosis is wrong
and the defect is somewhere else. *Fires ⇒ retract the diagnosis above.*

**K24 — DOES THE FIX BEAT A PERSON?** If arm G does not match or beat the best
archetype on crab utility, the engine still loses to an ordinary human negotiator
and the study says so in those words.

**K25 — IS THE MENU'S VALUE THE NOISE?** If H2 does not beat H1 at σ = 0.50 by at
least the bar, the menu is elegant and worthless. **And bidirectionally:** if H2
beats H1 at σ = 0 by more than the bar, something other than estimation error is
doing the work and it must be identified before the menu is claimed.

**K26 — WHAT DOES SELFISH COST?** Report the employer's payoff and joint surplus
under arm G. If joint surplus falls below the base engine's, selfish selection is
**extraction, not efficiency**, and that goes in the product copy rather than the
appendix.

## A4.4 On-record predictions

1. **K23 does not fire** — inferred-cost selection recovers most of the $7,738.
2. **K24 does not fire** — arm G beats the human archetype.
3. **K25 does not fire** — the menu's edge grows with σ and is ≈0 at σ = 0.
4. **K26 fires** — joint surplus roughly flat, employer sharply down. Selfish
   selection redistributes; it does not create.

## A4.5 The thing to be careful about

This amendment was written after a result that embarrassed the product, and it
proposes two changes that would flatter it. Every number above the line is a
diagnostic, not a claim. Nothing here is reportable until arm G runs on inferred
costs and the menu runs under noise, against the kills as written.

Seeds unchanged: 7/11/23/31 main, 101 held out.

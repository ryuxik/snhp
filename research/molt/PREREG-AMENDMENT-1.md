# PREREG AMENDMENT 1 — the founder's four objections

*Written 2026-07-25, AFTER the Phase-1 results were read. Everything registered
here is therefore **exploratory by construction** and inherits that label
regardless of what it finds. PREREG.md and its verdicts are untouched; this file
records what is being rebuilt, what it supersedes, and the kills that bind the
rebuild — written before any v2 code exists.*

Four objections were raised against the Phase-1 design. Three are upheld, one is
upheld with a qualification, and one Phase-1 claim is **retracted outright with
no re-run needed** because inspecting the code was sufficient to kill it.

---

## A1.0 What is retracted immediately

**"A better ask, against a counterparty doing its own sums, buys you nothing."**
RETRACTED. It is not a finding; it is the setup restated.

`world.p_leave` reads `c.has_outside` and `c.omega` directly, and `works_npv`
calls it. The employer in Phase 1 **already knows the crab's exact outside
offer** before the negotiation starts. There is nothing an ask could reveal, so
arms B and C were guaranteed to coincide. The cross-market corroboration cited
from the rent study is also weakened: that finding rested on "the landlord cannot
verify your alternative," but unverifiable is not the same as uninformative, and
a forwarded offer letter is frequently verifiable outright.

This claim is deleted from the article now, not pending a run.

## A1.1 What is suspended pending the v2 run

| Phase-1 claim | status |
|---|---|
| +$9,597 zero-clock joint advantage (K1) | **SUSPENDED** — measured against an agenda-handicapped opponent |
| $7,108 concession gap on the both-stay subset | **SUSPENDED** — partly an artifact of the agenda |
| 79.7% of the loss is replacement cost | **STANDS** in structure; its magnitude rests on the clock calibration, which this amendment does not touch |
| ~90% employer capture (K4) | **STANDS** — it is a split of whatever gain exists, not a claim about its size |
| K6's identification (63% price gap / 37% deal existence / ~0% heterogeneity) | **SUSPENDED** — it was measured as D−C, and C is the retracted arm |

## A1.2 Rename

**The Yard → the Works**, everywhere: code, tests, docs, demo, article.

---

## A1.3 Objection 1 — the agenda contaminates the comparison

**Upheld, with one qualification.** Money-first is not arbitrary in the sense of
random — salary conversations empirically open on salary. But hard-coding one
fixed order as a global constant means a crab whose priority sits fourth may
simply never be asked, and the resulting concession gap is a designer's choice
wearing a finding's clothes.

**The fix.** The agenda stops being a constant and becomes a treatment. Three
orderings, run as separate conditions on identical crabs:

| ordering | what it is |
|---|---|
| `money_first` | Phase 1's fixed order — retained as the documented handicap so the size of my thumb is measurable |
| `random` | drawn per crab-season |
| `best_first` | the crab opens with its own highest-valued remaining issue — the strongest opponent available |

**`best_first` is the arm the SNHP claim must beat.** Any headline that does not
survive against it is not reported.

## A1.4 Objection 1b — the slow bargainer should be a real corporate strategy

**Upheld.** Phase 1's slow crab was a hand-rolled anchor-and-concede ladder of
mine. `snhp/b2b_opponents.py` already contains 19 archetypes on negmas 0.15.4 —
Anchorer, Silent Hardliner, Split-the-Diff (labelled "corporate default"),
Deadline Exploiter, Soviet Patience, Tactical Empath, Logroller, and the rest.

Slow arms are driven by those classes **as they are**, over a negmas
`SAOMechanism`, one issue at a time with the already-settled issues frozen. No
reimplementation: the rent study's K1 fired against my own reimplementation of
ranked asks rather than against the product, and that mistake is not repeated in
the opposite direction.

Registered archetype set (all 19 run; these are the ones reported individually):
`Split-the-Diff`, `Anchorer`, `Silent Hardliner`, `Deadline Exploiter`,
`Logroller`, `Tactical Empath`.

**`Logroller` (Raiffa, issue-by-issue trading) is the specific threat** — an
archetype built to trade across issues, restricted to one issue at a time. If it
closes the gap, the Phase-1 story was the agenda.

## A1.5 Objection 2 — the clock, not the protocol, should carry the difference

**Upheld.** The slow arm's disadvantage must come from *real human timelines*,
not from being denied access to issues. Both arms cover all five issues. What
differs:

| | slow | one sitting |
|---|---|---|
| a round trip | email, **2–5 days** (lognormal, median 3) | same session, 0 days |
| locking it down | one scheduled meeting, **7–12 days** | same session |
| sign-off | one hop per above-discretion item | one hop total |
| rounds available | up to 12 exchanges across up to 5 issues | 3 engine rounds |

The slow arm gets **more** exchanges than the engine arm, not fewer. The
zero-clock condition (every delay cost exactly zero) remains a first-class
reported condition, unchanged from PREREG §0.

## A1.6 Objection 3 — each employer has its own private valuation of a skillset

**Upheld.** Phase 1's replacement cost was `ρ(specialization) × salary` — a
constant per role, so no crab was worth unusually much *to this employer
specifically*, and the interesting retention case (worth 1.6× here, 1.0× on the
market) did not exist.

Added:

- **`match` μᵢ ~ lognormal(0, 0.35), mean 1.** Firm-specific human capital: what
  this crab is worth to the Works relative to a generic replacement of the same
  specialization. **Private to the Works; the crab never learns it.** Replacement
  cost becomes `ρ(spec)·S·μᵢ`. Mean 1 keeps the population anchored to the
  published 0.5–2× range while creating the dispersion that was missing.
- **`quality` qᵢ ~ N(0,1)**, driving the outside premium
  `ω ~ N(0.12 + 0.04·q, 0.06)`. **Drawn independently of μ**, so a crab's market
  value and its value *here* are different numbers — which is the whole point.

Registered consequence: the Works should now fight hard for high-μ crabs and let
low-μ crabs walk. If it does not, the fix was cosmetic (K11).

## A1.7 Objection 4 — an outside offer must inform the employer's valuation

**Upheld; see A1.0 for the retraction it forces.** The Works no longer observes
`has_outside` or `omega`. It holds a prior over the crab's outside option — the
specialization-level distribution, which it does know — and computes `P(leave)`
by integrating over its **posterior**.

Two conditions, swept, and the gap between them is the answer:

- **VERIFIABLE.** The crab may disclose; disclosure reveals ω exactly. A crab
  with a weak offer would rather not disclose, so **non-disclosure is itself
  informative**: the Works applies Bayes to silence, truncating its posterior
  below the disclosure threshold. The threshold is solved by one fixed-point
  iteration on dedicated pilot seeds (9100–9119), as the rent study did for its
  tenure-conditional prior.
- **UNVERIFIABLE.** The crab may claim; the Works believes the *fact* of an
  offer but not the number, updating to the conditional distribution of ω given
  "has an offer."

**The gap between the two conditions prices the offer letter directly**, which is
the question Phase 1 could not ask.

---

## A1.8 Kills (binding, bidirectional, written before any v2 output)

Bar unchanged: **2% of salary ($2,268)**.

**K8 — THE MONEY STORY.** With the clock off, if the engine arm's joint advantage
over the **best** archetype arm at **`best_first`** ordering is < the bar, then
bundling wins nothing on money and the entire effect is the clock. *Consequence:*
RESULTS and the article retract every money claim and report a time claim only,
with the clock calibration printed beside it. **This is the kill I expect to
fire.**

**K9 — THE SIZE OF MY THUMB.** If the concession gap under `money_first` exceeds
the gap under `best_first` by more than the bar, the Phase-1 $7,108 figure was an
artifact of my agenda and is retracted with the difference stated. If they agree,
the agenda objection is answered on the record and the figure stands.

**K10 — DOES DISCLOSURE PAY?** In VERIFIABLE, if disclosing a genuine outside
offer improves the disclosing crab's package by < the bar against an identical
non-disclosing crab, then "asking is worth nothing" survives *with a mechanism
behind it*. If it pays, the claim stays retracted and the replacement finding is
"showing the letter is worth $X; talking about it is worth $Y."

**K11 — DID THE MATCH VALUE DO ANYTHING?** If the rank correlation between μ and
the Works' concession is < 0.15, firm-specific valuation is inert and the fix was
cosmetic. Report either way.

**K12 — ARCHETYPE DEPENDENCE.** If the engine's advantage varies by more than 2×
across the six reported archetypes, no single headline number is published;
results are reported per archetype with the weakest one named first.

**K13 — THE SPLIT.** Re-check K4 under v2. If employer capture leaves the
70–95% band, the Phase-1 cross-market replication claim is withdrawn.

## A1.9 On-record predictions

1. **K8 fires, or comes close.** I expect the zero-clock advantage to fall by
   **more than half** from $9,597, because a Logroller given twelve exchanges can
   probably find most of the package. I said this to the founder before building
   it and am recording it so it cannot be reinterpreted afterwards.
2. **K10 does not fire** — disclosure pays. The retracted claim stays retracted.
3. **K9 fires** — `best_first` closes a substantial part of the concession gap,
   but not all of it, because settling an issue permanently still forecloses
   trades against issues not yet raised.
4. **K13 does not fire** — the ~90% employer split is the most robust thing in
   the study and survives the rebuild.

## A1.10 Stopping rule

Unchanged from PREREG §6 and re-affirmed: if a kill fires, it is reported. No
mechanism is added afterwards to un-fire it. If something new is built after
seeing a v2 result, it needs Amendment 2 and its own kills, and its results are
labelled exploratory-of-exploratory.

Seeds: main 7/11/23/31, held-out confirmatory 101 — unchanged, so v1 and v2 are
paired on identical crab draws wherever the draw is unchanged.

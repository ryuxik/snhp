# Critical analysis of every non-win

*2026-07-10. Rule: each experiment that failed to show a clear SNHP
advantage gets one of three verdicts — THEORY-CORRECT (the tie is what
correct theory predicts; distrust a mechanism that "wins" there),
MECHANISM DEFECT (SNHP is wrong and fixable), or METHODOLOGY ARTIFACT
(the experiment mismeasures). Fixes are pre-registered here before
implementation.*

## 1. Vend control cell: −$0.10 [−0.67, 0.47] — THEORY-CORRECT

Riley–Zeckhauser says a committed seller with known demand cannot be
beaten by bargaining. Our tie replicates it. Every remaining lever at the
knife edge (quantity discrimination, marginal-customer recruiting) already
fires where the theory permits. **No action.** A mechanism that beat this
cell would be evidence of a bug, and once was (the pre-review versions
"won" here via consumer irrationality).

## 2. The computed/posted arms lose or tie EVERYWHERE — MECHANISM DEFECT (in the baseline), action required

Vend gvr −$1.94/day; slots-parking computed significantly negative
(−$16–24/day); boba computed ties. Three diagnosed causes: per-SKU
independence (cross-SKU cannibalization), all-or-nothing demand models
(parking buyers self-trim duration at list; the model assumes they vanish),
no joint-board optimization. This is OUR baseline being weak, which cuts
against our own paper: "disclosure beats inference" is only proven if
inference got its best shot. **Action (referee item, pre-registered): build
a choice-model-aware, jointly-optimized posted arm. If it closes the gap
with nego, the disclosure claim weakens honestly; if it doesn't, the claim
hardens.** Note the one finding that already survives any posted upgrade:
at parking, nego carrying the SAME wrong forecast wins while posted loses —
per-individual alternative-gating is robust to forecast error in a way no
posted price can be, because a bad quote gets declined while a bad posted
price silently bleeds.

## 3. Slots H-S2: the shift lever ≤ 0, no-shift beats full nego by ~$130/day at the bar — MECHANISM DEFECT, fix now

The capacity-relief credit prices a freed peak seat at STATIC-regime list
margin. But in the nego regime, freed peak seats get resold through
discounted quotes, and the shifted buyer consumes shoulder capacity that
no-shift would have monetized. This is the Lucas critique a third time —
we fixed it in the demand forecast (P1.5) and the displacement shadow
(censoring), but the relief term still assumes a world the mechanism
abolishes. **Fix (pre-registered): relief = (learned, realized nego-regime
peak margin per freed slot) − (shoulder displacement cost of the shifted
booking), both from the arm's own history. Prediction: the shift lever
becomes ≥ 0 everywhere (fires only when genuinely positive) and full nego
matches or beats the no-shift ablation.** If the lever stays ≈ 0 after the
fix, the honest conclusion stands: slot-shifting logrolls are a boba-shaped
result (long service times, order-ahead) that does not generalize to
short-peak venues, and the whitepaper says so.

## 4. Vintage offer/1: −$302 at decent tags + deep shading; H-V1 refuted — HALF DEFECT, HALF CATEGORY ERROR, fix now

Two distinct problems. (a) Counters trigger huffs the engine can't
anticipate: it never learns the shading distribution, so it counters into
walk-risk. Fix: population-level shading inference from accept/huff
history; counter less where huff-cost × walk-prob is high. (b) The deeper
one: **discount-only is a category error for one-of-one goods.** The
ceiling exists to protect reference prices; one-of-one items HAVE no
reference price (the Uber condition) — enforcing a ceiling there is
importing a fairness constraint from a category where it binds into one
where it protects nothing and forfeits the entire under-tag upside (H-V1's
refutation measured exactly this). **Fix (pre-registered): a bidirectional
retagging arm — the hazard learner may re-tag UP on high-connection items
(posted, visible, before any offer). Prediction: recovers a large share of
the under-tag value H-V1 showed unrecoverable, with no fairness exposure
because no reference exists.** The invariant's *scope* becomes a
first-class finding: discount-only is per-category, reference-priced goods
only.

## 5. Block fashion: full-season tie (−18.85) — METHODOLOGY ARTIFACT, two parts

(a) The 30-day +$396/day was revenue timing (caught before publication;
full season is the truth). (b) But the full-season tie itself is also
suspect: BOTH worlds hit 100% sell-through, meaning the block's fashion
demand calibration is too hot — when everything sells out, no mechanism
can matter (the scarcity result). The standalone fashion sim, with
realistic leftovers, shows +9–21%/season. **Fix: recalibrate the block's
fashion arrival scale to reproduce standalone sell-through (~85–92%), and
use 7-day CI blocks for fashion metrics (5-day blocks alias the weekly
repricing cadence).** Until then the block's fashion row is labeled
non-informative rather than a tie.

## 6. Slots barber: ≈ 0 — THEORY-CORRECT as modeled, but the model under-scopes the venue

Two chairs, low congestion, high-value appointments: little spot-market
surplus exists, and the mechanism correctly finds little. But real
barbershops monetize no-shows (deposits), cancellations, and memberships —
recurring-relationship terms our spot-deal frame cannot see. **Noted as
scope, queued: cancellation/deposit terms as bundle issues; subscriptions
are the natural product for appointment venues, not spot negotiation.**

## 7. Boba pearls-markdown ≈ $0 — HONEST FALSIFICATION, keep

Pre-registered lever, measured at five cents: attach drains batches before
they age. The methodology worked exactly as designed. No action beyond the
already-recorded lesson: clearance is a side effect of attach.

## 8. Residual power gaps — METHODOLOGY, cheap

Best-vs-best anchor (seed A) and several block cells straddle zero at 30
days. **Action: 90-day runs for any cell quoted in the whitepaper; no
30-day CI may appear in a headline table.**

## The meta-pattern

Every real defect found so far is the same defect: **some term in the
machine's utility still assumes the pre-mechanism world** (demand
forecasts → fixed in P1.5; displacement shadows → fixed via censoring;
capacity relief → fix #3; and the baseline's own crowd model → fix #2).
The design rule that falls out, for the whitepaper's methods section:
*every dollar in the broker's objective must be measured in the regime the
broker creates.* Where we have applied that rule, the mechanism wins or
correctly ties; where we haven't yet, it loses — which is about as clean
as evidence gets that the rule is the theory.

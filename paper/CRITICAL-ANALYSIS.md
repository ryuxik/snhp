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

**OUTCOME (2026-07-10, post-registration): prediction REFUTED at the bar.**
The learned relief basis (per-hour EWMA of the arm's own realized margin,
sold-out-gated) improved every touched cell — barber σ=0 flipped
significantly positive vs static, full-nego bar +$24–59/day — but noshift
still beats full nego at the bar by $79–101/day (significant, all four
cells), robust to average-vs-marginal basis. Per-buyer decomposition:
+$184/day genuine walkaway rescues vs −$110/day discounts to would-pay-list
buyers and −$154/day displacement of later list walk-ins — within-day
[see CALIBRATED-WORLD UPDATE below for why this magnitude is now suspect]
—
local-window state no day-level learned slot value can carry. The honest
conclusion above stands and goes in the whitepaper: slot-shifting logrolls
are boba-shaped; at short-peak walk-in venues the correct broker plays
no-shift. Parking/barber-noshift artifacts byte-identical (never hit the
swap path).

**CALIBRATED-WORLD UPDATE (2026-07-10): the bar was mis-anchored AND the
shift machinery is calendar-blind — the "no-shift wins" verdict survives
directionally but its magnitude is not yet trustworthy.** Two things landed
together. (1) *The anchor was wrong, as suspected.* The bar list ($16/$9)
sat near the average while WTP rose to 1.10× at peak, so the discount-only
nego arm was capped exactly when leverage was highest. Peak-anchoring it
(vend's pattern; list raised to $21.67/$12.19) is the right fix — but a
documented ~37% residual headroom remains that no finite anchor closes under
the shared full-mixture ratio-appeal inversion, so peak-anchoring alone does
not rescue full-nego. (2) *A first-order defect was exposed by adding the
real weekend curve:* `peak_hours` / `HourMarginLearner` are CALENDAR-BLIND.
Harmless before day-of-week variance existed; now Saturday 16:00 is one of
the week's busiest hours yet never flags "peak," so the relief learner
assigns it $0.52/tick vs hour-20's $3.75/tick — it prices freed weekend
shoulder slots as near-worthless. Under this, the shift component *deepened*
from −$79–101/day to **−$367–406/day** (significant, all cells). **That
−$400 is an artifact of the calendar-blind learner, not a clean economic
verdict** — the machinery is systematically undervaluing exactly the
weekend-afternoon slots the calibration just made valuable. Pre-registered
follow-up: make `peak_hours`/relief calendar-aware (key on (day%7, hour), as
`computed/1`'s mstar already is post-calibration) and re-run; only then is
the bar no-shift magnitude trustworthy. Directional conclusion (no-shift ≥
full-nego at the bar) is unchanged and consistent across every version;
the *size* is on hold. Parking nego survives the elasticity fix unchanged
(+$106–180/day, all significant; commuters confirmed least-elastic |e|=0.81);
barber σ=0 positive holds (+$11–16/day, significant).

**RESOLVED (2026-07-10): the calendar-blind artifact confirmed and removed —
verdict now trustworthy and CLEAN.** Keying `peak_hours` + the relief EWMA on
the day-of-week bucket (as `computed/1`'s mstar already was) let Saturday
16:00 learn its own high slot value. The shift component collapsed ~70–84%
(−$367–406 → **−$60–115/day**), and the fix also rescued full-nego from being
a spurious net loser (bar nego −$263–385 → +$134–200/day, all CIs exclude
zero) — confirming the −$400 was the artifact. **The boba-shaped-venue
conclusion is now CLEAN: no-shift still wins at the bar (significant in 3/4
cells) even with correctly-valued weekend shoulder slots, by a trustworthy
$60–115/day.** That residual is irreducible by any *learned slot value* —
whether this tick today is locally rebooked within the ±30-min window is
same-day-trajectory state no day-level average can carry — which is exactly
why slot-shifting logrolls are boba-shaped (order-ahead venues have that
trajectory; walk-in venues don't). H-S2 fails at an honest magnitude.
Side-finding: the ~31.6% peak anchor headroom is the *irreducible* price of
two invariants (discount-only arms + a single-sticker profit-optimal static);
it is symmetric across nego/noshift so it does not touch the shift verdict,
and every attempt to close it either asymptotes short, turns static into a
strawman the discount arms beat spuriously (the §1 artifact), or dissolves
the single sticker into computed/1.

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

**OUTCOME (2026-07-10, post-registration): prediction SUPPORTED.** retag/1
recovers 98% (σ_tag=0.3) / 51% (σ_tag=0.6) of the under-tag upside H-V1
called unrecoverable; retag+offer/1 dominates in 3/4 cells (+$3.9–4.7k per
60-day store). The shading learner turned the −$302 cell into +$40 (CI
straddles zero — the loss is gone, not a win) by countering less into
huff-risk. Two honest qualifications recorded in vintage/RESULTS.md: at
σ=0.3 most of retag's gain is whole-board PV repricing rather than
error-fixing, and pure retag *hurts* over-tagged stock until the offer arm
repairs it. No fairness exposure: retags posted, visible, uniform, at most
weekly, before any offer.

**REVERSAL (2026-07-10, v3 realistic-calibration): retag/1 loses under
realistic time-on-shelf — the v2 win was a fast-sale artifact.** Recalibrating
to the real resale hazard (ThredUp ~50% sell-through at 30 days; median
days-to-sale 26–33 days, not ≈0 — CONNECT_PROB cut ~53×) flips retag/1 from
+$3.7–4.4k to **significantly negative in every cell** (−$268 to −$654);
the under-tag class Δ goes +2,031/+2,011 → −208/−402. Root cause (isolated by
diagnostic — NOT a rate-prior mismatch; pinning the true rate barely moves
it): the PV-repricing solve's DAILY_DISCOUNT/HOLDING_COST were implicitly
tuned for near-instant sales, so against a hazard ~53× slower it reads a
normal multi-week gap between browsers as *overpricing* and marks a
correctly-tagged item down to ~63% of tag by week 8 — almost as fast as
sticker's crude ritual. **This is the meta-pattern once more: retag's
objective was measured in a fast-sale world that doesn't exist.** offer/1
survives (zero significantly-negative cells at the realistic 58% huff rate)
for the same reason parking's nego survives a wrong forecast (§2): it
discounts only to the specific browser negotiating, so a bad price is
declined by one person, whereas retag *broadcasts* the markdown to every
future visitor and bleeds. **PROVISIONAL — this is an engine-tuning gap, not
yet a fundamental result (flagged 2026-07-10 after review challenge).** The
retag loss is measured against a solve whose HOLDING_COST/DAILY_DISCOUNT are
tuned to a fast-sale world; we have NOT yet given retag its best shot at the
realistic timeline. Until we retune the holding cost/discount to the slow
hazard and re-test, we may only claim "the fast-tuned retag solve bleeds when
the world is slow," NOT "broadcast markdown fundamentally bleeds." This is the
meta-pattern once more (the objective assumed the wrong regime — here the
wrong TIME regime), and the fix is the same: make the schedule
regime-consistent with the real demand timeline. The one residual that is
robust to tuning: offer/1 carried the SAME mis-tuned holding cost and did
NOT lose money, because per-individual gating declines a bad price one buyer
at a time while a broadcast markdown commits it to everyone — that asymmetry
is real regardless of tuning. **BLOCKER before any vintage claim ships:
retune to the realistic hazard (the "demand-timeline-tuned" arm) and re-run.
If a slow-aware retag recovers, the reversal was a tuning artifact; if it
still bleeds, the broadcast-vs-targeted asymmetry hardens.** Same axis applies
to fashion (§5-adjacent): the markdown-beats-cliff result compares FIXED
schedules, not an engine tuned to the true demand+return timeline — the
stronger test is the timeline-optimized markdown, also owed.

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

## 9. Florist: computed BEATS nego (+$142–202 vs +$113–182), and spike-day nego is strictly worse (−$123–162/day) — THEORY-INFORMATIVE, new

When clearance-to-zero is the entire game (linear decay, weekly resupply,
everything must move), a posted markdown board dominates bilateral
splitting: the Nash split hands each buyer a share of surplus the shop
doesn't need to concede when the alternative buyer arrives minutes later,
and the buffer blocks deals posted clearance would happily take. On demand
floods this inverts hardest — negotiating into a queue is strictly worse
than posted rationing. **The mechanism boundary, sharpened: bilateral
quoting wins where buyer heterogeneity is the scarce information (who
values what, who has which alternative); posted clearance wins where TIME
is the only variable that matters and buyers are interchangeable.** Action:
(a) the broker should detect flood/clearance regimes (learned arrival
pressure vs stock) and fall back to its own posted-markdown mode — the
mechanism containing the posted board as a special case is strictly
stronger than either alone; pre-registered prediction: a regime-switching
arm weakly dominates both at the florist. (b) The bakery's noon day-old
pull vindication (folk cannibalization control beating naive dynamic
tiers) goes in the paper as evidence that cultural pricing practices
encode real constraints — controls must implement the culture, not a
caricature of it.

**OUTCOME (2026-07-10, post-registration): prediction REFUTED at the florist.**
regime/1 (no-oracle detector: realized arrivals-so-far, current stock, own
delivery calendar — never is_spike_day) never beats computed/1 (negative in
all 4 cells, CI clear of zero in 2/4) and is indistinguishable from nego/1
(CI includes zero in all 4). Two measured causes: (1) genuine detection
latency — on real spike days regime recovers ~75–80% of nego's flood losses
but still trails posted and even loses to doing nothing; (2) after the shrink
recalibration (below) computed/1 dominates nego/1 in *every* florist cell, so
the ~31% of transactions the detector routes to hetero/nego mode is pure
forgone value, not a real trade-off. Bakery spillover: NOT trigger-happy —
calm cells byte-identical to nego/1 (CI [0,0]); spike cells a small negative
point estimate, CI includes zero. **Honest conclusion: a learned regime
switch cannot beat always-posted at a venue where posted already wins
outright — the containment idea only pays where the two pure arms genuinely
trade blows, which the florist, once realistically calibrated, does not.** The
sharpened boundary (bilateral wins on heterogeneity, posted wins on time)
stands; the "mechanism contains posted as a special case and weakly
dominates" claim does not, here.

**Shrink recalibration side-finding (strengthens the boundary):** relabeling
3–5-day cutoffs as retail *display* life, extending vase life to 6–9 days
(IFPA band), replacing the −70% day-4 cliff with a graduated markdown ladder,
and adding a pricing-independent 15% receiving loss brought realized dollar
shrink to 9.5% (IFPA band). Effect on the computed-vs-nego gap: it did NOT
shrink — it **more than doubled** (−$15–40/day → −$52–112/day, 2/4 cells now
significant). The graduated ladder raises nego/1's calendar-recovery
opportunity-cost floor (tighter buffer, less extractable margin) while
computed/1, unconstrained by that reference, gets more runway from the longer
vase life. The florist boundary is more robust at realistic shrink, not less.

## 10. Emergent incentive-compatibility is NOT universal — it is a property of finite-stock shadow pricing (boba breaks it) — SCOPE BOUNDARY, corrects a lead claim

The whitepaper's lead claim (abstract + §4.2) is that a best-response search
over misreporting finds honesty at the buyer's optimum *without verification*
— "the disagreement structure prices lies." **That result is vend-specific.**
Boba's liar battery (7×2 deviation grid + 25/50/100% share sweep, block CIs,
two seeds) finds the opposite: understating WTP (~0.55–0.85×) while claiming a
strong outside option flips `cart_nash`'s disagreement branch, so the shop
believes it has nothing to lose even facing a genuine buyer. A true
$10.71-surplus buyer extracts $23.66 and collapses shop margin $11.30→$0. The
best-response deviation (wtp≈0.7, claim_walk) nets buyers **+$1,099–1,171/day
pooled** (tight CIs, both seeds); erosion is near-linear in liar share and
**~32–34% liars wipe out the entire +$270–350/day cart headline** (25% already
costs −$257 to −$274/day; 50% flips the cart to a net loser vs static).

**Root cause (diagnosed, not hand-waved): vend's honesty is protected by
finite-stock shadow pricing that boba's capacity world lacks.** In vend the
seller's disagreement point is anchored by a genuinely scarce resource — a
sold unit is gone — so understating your alternative cannot manufacture a
"nothing to lose" seller; the shadow price holds the floor. Boba's constraint
is soft capacity (a freed slot is worth only its resale, which the buyer's
claimed outside option can talk down), so the disagreement branch is
manipulable. **The sharpened, more honest claim for the paper: emergent IC is
a property of the shadow-price structure, not of Nash bargaining in general —
it holds where the seller's no-deal value is pinned by a scarce stock, and
fails where it rests on a manipulable capacity/outside-option comparison.**

**The safe fallback exists and is measured (Task B, menu fairness):** a
person-independent public menu (list / topper / bundle / value-defer),
computed only from hour-level population stats with a real screening friction
on each markdown, is **structurally immune to the entire liar battery** (no
disclosure channel to exploit) — but keeps only ~9–10% of the cart's
$346–357/day (discrimination component ~0% survival, i.e. a tie vs static;
the fairness-clean pickup-time smoothing survives partially, ~21–22% of its
$206/day). So the honest tradeoff at a capacity venue is stark: the
discriminating cart is large but exploitable and fairness-exposed; the menu is
safe and fair but keeps a tenth. **Action (pre-registered): (a) whitepaper
abstract + §4.2 must state the finite-stock scope boundary — emergent IC is
NOT claimed for capacity venues; (b) at capacity venues, verification
(attested disclosure) moves from optional discount-tier back to a security
requirement, or the broker falls back to the liar-immune menu; (c) test
whether a shadow-price analog for capacity (pre-committing the freed-slot
resale value so the outside-option claim cannot move it) restores IC — if it
does, the unifying claim becomes "emergent IC wherever the disagreement point
is pinned to a pre-committed value."**

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

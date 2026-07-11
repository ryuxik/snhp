# A characterization of emergent buyer incentive-compatibility in brokered Nash quoting

*SNHP Research — Task #68A, the MIT-referee's #1 ask (a proof for the §3
Proposition). July 2026. Companion to the harder empirical battery (Task #68B,
`vend/battery.py`, `boba/battery.py`), whose sup-over-types and adaptive-liar
results this proof predicts and is refined by (§6–§8).*

---

## 0. What this document proves, and the one place it does not

The whitepaper (§3) states, as a *proposition owed a proof*, that truthful
disclosure maximizes the buyer's true surplus over the WTP-scaling ×
outside-option deviation class **iff** four conditions hold: (a) discount-only
shadow pricing, (b) a report-independent seller reservation on excess units, (c)
an event-consistent disagreement point, (d) a bounded/attested outside option.

We prove the characterization in a **stylized single-unit, single-good Nash
bargaining model** — and in doing so find that the four conditions **as
stated are necessary but not jointly sufficient.** The gap is sharp, small, and
localizes exactly:

> On a **scarce** unit the price is pinned at list and *no* report changes the
> buyer's surplus — (a) alone gives honesty. On an **excess** unit conditions
> (b), (c), (d) bound the *outside-option* channel but do **not** by themselves
> close the *WTP-understatement* channel: a strong understatement collapses the
> buyer's own board disagreement, flips the operative no-deal event to "walk,"
> and lets the buyer capture the excess rent at a discounted price. The
> min-gain buffer β is what closes it — but only when it dominates the excess
> rent. The **exact** sufficient condition on excess units is
>
> **(a′)   ℓ − c ≤ 2β,**
>
> the list-minus-shadow-cost rent is at most twice the buffer. When ℓ − c > 2β
> a **bounded** leak survives, of size at most **ℓ − c − β** per excess unit,
> for the *would-be-board-buyer-with-an-outside-option* type. Full WTP
> attestation (pinning the report) closes it unconditionally.

So the corrected characterization is **(a) ∧ (a′) ∧ (b) ∧ (c) ∧ (d)**, and
(a′) — a buffer-versus-rent inequality — is the fifth condition the whitepaper
§3 Proposition was missing. The empirical battery (§7) confirms it: the pooled
liar sweep sees a tie (the population mean nets scarce-day self-denial against
excess-day gains), but the **sup over types** on the excess stratum is a
significant **+\$0.15–0.20/day** — precisely the residual (a′) leak on the
high-rent SKUs (sandwich, cola, candy: ℓ − c > 2β) and absent on the low-rent
ones (water: ℓ − c < 2β).

This is a genuine finding, not a formality: the referee was right that
"report-independence of the seller's reservation" is not the whole story, and
was right to demand a proof — the proof is what surfaces (a′).

---

## 1. Model

A single indivisible unit of a single good.

* **List price** ℓ > 0, the ceiling: every quote satisfies p ≤ ℓ (discount-only,
  type-enforced; `vend/core.py::Quote.__post_init__`).
* **Seller state** σ ∈ {SCARCE, EXCESS}, a function of inventory and learned
  demand, *not* of any report. The seller's reservation (the price below which
  selling now is a loss) is
  * σ = SCARCE:  r = ℓ. The unit, if kept, sells at list within the horizon, so
    its shadow opportunity cost is the full list price — selling it below list
    *displaces* that sale (`scenario.py::machine_margin`, the `displaced` term).
  * σ = EXCESS:  r = c, with c = c_eff = unit cost, or salvage if the unit
    expires tonight (`scenario.py::c_eff`). This is report-independent
    (condition **(b)**).
* **Buyer** has private true value v ≥ 0 for the unit and a private true
  outside-option surplus o ≥ 0 (the best alternative: a competitor board minus a
  walk, or another good's board purchase). Utility is quasilinear: buying at p
  yields v − p; the outside yields o.
* **Report / deviation class.** The buyer discloses v̂ = φ·v (WTP-scaling,
  φ > 0; `scenario.py::strategic_disclosure`) and ô ∈ [o, ō] (outside-option
  inflation, capped at ō; ō = o under attestation, condition **(d)**). Honesty
  is (φ, ô) = (1, o).

### 1.1 The mechanism (symmetric Nash, w = ½)

Given reports, the broker forms the **event-consistent disagreement point**
(`scenario.py::nash_quote`, lines 253–278):

* the buyer's no-deal event is the better of *buying at the board* (surplus
  s_brd(v̂) = (v̂ − ℓ)₊, evaluated on the **same disclosed** v̂ — condition
  **(c)**) or *walking to the outside* (ô). Write the operative event
  E = BOARD if s_brd(v̂) ≥ ô, else WALK, and
  * d_b = max(s_brd(v̂), ô),
  * d_s = (ℓ − c) if E = BOARD  (the seller's alternative is to sell *this* unit
    to *this* buyer at list),   else 0  (a walker leaves the seller nothing).

Given a candidate price p on the unit, seller and buyer **gains over
disagreement** are

  g_s(p) = margin(p) − d_s,   g_b(p) = (v̂ − p) − d_b,

with margin(p) = p − c on an excess unit and margin(p) = p − ℓ on a scarce one
(the displaced-sale shadow). The broker returns

  p\* = argmax_{p ∈ [·, ℓ]} g_s(p)·g_b(p)   subject to  g_s(p) ≥ 0, g_b(p) ≥ 0,

and then applies the **min-gain buffer**: the quote is withdrawn unless the
*Nash-optimal* point clears g_s(p\*) ≥ β, with β = max(\$0.75, 0.15·ℓ)
(`nash_quote` lines 310–318; the buffer gates the argmax, it does **not**
re-optimize to a higher buffer-clearing price — this matters in §4). If no
feasible quote clears, the buyer falls back to the board or the outside.

The buyer's **realized true surplus** is v − p\* if a quote is taken, else
max((v − ℓ)₊, o) (their true best alternative). Honesty is a best response iff
this is maximized at (φ, ô) = (1, o).

---

## 2. The theorem

> **Theorem (emergent buyer-IC, single unit).** Fix the deviation class
> {φ > 0} × {ô ∈ [o, ō]}. Truthful disclosure (φ = 1, ô = o) maximizes the
> buyer's realized true surplus for **every** buyer type (v, o) **iff** in every
> state the buyer may face:
>
> 1. **(a)** the unit is SCARCE (r = ℓ) — then p\* = ℓ regardless of the report;
>    **or**
> 2. **(a′) ∧ (b) ∧ (c) ∧ (d)** the unit is EXCESS with report-independent
>    r = c, an event-consistent d_b, a bounded outside ô ≤ ō, **and** the buffer
>    dominates the excess rent:  **ℓ − c ≤ 2β.**
>
> If instead the unit is EXCESS with **ℓ − c > 2β**, honesty fails: the type
> whose honest operative event is BOARD but whose outside o satisfies
> 0 ≤ o < ℓ − c − 2β strictly gains by understating, capturing up to
> **ℓ − c − β** of extra surplus. Conditions (b), (c), (d) each remain
> *necessary* (§5) but do not substitute for (a′).

The proof is three lemmas.

---

## 3. Lemma S (SCARCE ⇒ honesty, condition (a))

**Claim.** If σ = SCARCE then p\* = ℓ for every report, so the buyer's realized
surplus (v − ℓ, or the board) is report-independent; honesty is weakly optimal.

**Proof.** On a scarce unit margin(p) = p − ℓ ≤ 0 for all p ≤ ℓ. Whatever the
operative event, d_s ≥ 0, so g_s(p) = (p − ℓ) − d_s ≤ 0 with equality only at
p = ℓ (and only if d_s = 0). Hence the sole price with g_s ≥ 0 is p = ℓ, and the
"quote" is just the board. The buyer's surplus is v − ℓ (or their outside if
larger), a quantity free of (φ, ô). ∎

*Numerically* (`scenario.py`, one unit, D = 5 > stock, c = 0.70, ℓ = 2.00,
v = 3): honest and 0.55×-understated reports both yield surplus 1.00; **gain
0.000** (scratchpad `regimes2.py`). Disclosure is *uninformative* exactly where
a lie would want to bite — the load-bearing half of (a).

---

## 4. Lemma E (EXCESS: the WTP channel and the buffer)

Here r = c and p ranges over [c, ℓ]. Write the unconstrained symmetric-Nash
price p⁰(v̂, d_b) = (c + v̂ − d_b)/2 (the interior maximizer of (p − c)(v̂ − p −
d_b)). Consider the two operative events.

### 4.1 E1 — honest buyer is a would-be board buyer (v − ℓ ≥ o)

**Honest outcome.** With v̂ = v ≥ ℓ, E = BOARD, so d_b = v − ℓ and d_s = ℓ − c.
Then g_s(p) = (p − c) − (ℓ − c) = p − ℓ ≤ 0, so again p\* = ℓ: **the honest
would-be board buyer gets no discount** and realizes v − ℓ. (This is (c) working
*for* the mechanism: the seller's threat "I sell you this at list" pins the
price.) Confirmed in `scenario.py`: honest surplus = board = v − ℓ = 1.00.

**The understatement.** Take φ < ℓ/v so that v̂ = φv < ℓ. Now s_brd(v̂) =
(v̂ − ℓ)₊ = 0, and (for any modest o) the operative event **flips to WALK**:
d_b = ô ≈ o, d_s = 0. The Nash price becomes p⁰ = (c + v̂ − ô)/2, **strictly
decreasing in v̂**, and the buyer's true surplus v − p⁰ **strictly increasing as
φ falls**. The buyer would drive p⁰ → c (capturing the whole excess rent v − c)
were it not for the buffer.

**The buffer closes it iff ℓ − c ≤ 2β.** The buffer withdraws the quote unless
the Nash-optimal margin clears β: g_s(p⁰) = p⁰ − c = (v̂ − d_b − c)/2 ≥ β, i.e.

  v̂ ≥ c + 2β + d_b ≈ c + 2β    (d_b = o ≈ 0 after the flip).

But the *flip itself* required v̂ < ℓ. Both can hold simultaneously **iff**
c + 2β < ℓ, i.e. **ℓ − c > 2β**. Therefore:

* If **ℓ − c ≤ 2β**: no report both flips the event (v̂ < ℓ) *and* clears the
  buffer (v̂ ≥ c + 2β). Every understatement that flips is withdrawn; every
  understatement that clears keeps E = BOARD and p\* = ℓ (E1 honest). Honesty is
  a **weak** best response (every report yields v − ℓ; the buyer is
  *indifferent* — lies are un-rewarded, not punished). ∎ *(a′ holds.)*
* If **ℓ − c > 2β**: choose v̂ = c + 2β (< ℓ). The flip holds (d_b = o = 0), the
  buffer binds exactly (g_s = β), and p\* = p⁰ = (c + v̂)/2 = c + β. The buyer's
  true surplus is v − (c + β), versus the honest v − ℓ. **Gain = ℓ − c − β > β >
  0.** ∎ *(a′ fails; a bounded leak survives.)*

*Numerically* (c = 0.70, ℓ = 2.00 ⇒ ℓ − c = 1.30; β = max(0.75, 0.15·2) =
0.75 ⇒ 2β = 1.50): here **ℓ − c = 1.30 < 1.50 = 2β**, so (a′) holds — and indeed
the buffered 0.45×/0.55×/0.65× understatements all return **NODEAL** (gain
0.000, `regimes2.py`). With the buffer **off** (β = 0), 2β = 0 < 1.30, (a′)
fails, and the 0.55× understatement deals at p = 1.17 for a true surplus 1.83 vs
honest 1.00 — **gain +0.830** = ℓ − p⁰. The buffer is doing exactly the work the
theorem assigns it.

### 4.2 E2 — honest buyer already walks (v − ℓ < o)

Honest: E = WALK, d_b = o, d_s = 0, p⁰_h = (c + v − o)/2, honest surplus
v − p⁰_h. Understating to v̂ < v gives p⁰_l = (c + v̂ − o)/2 < p⁰_h whenever the
lie still clears the buffer (v̂ ≥ c + 2β + o). Gain = (v − v̂)/2 > 0, again
positive **iff** the flip-and-clear window is nonempty, which reduces to the
same **ℓ − c > 2β** feasibility once one accounts for the board ceiling. The
outside o is *bounded* by (d) but bounding o does not remove the v̂-channel; only
(a′) or WTP attestation does. ∎

### 4.3 The per-SKU predictor

(a′) is checkable per good from the catalog. β = max(\$0.75, 0.15ℓ). At the
vending catalog (unit qty):

| SKU | ℓ | c (normal / expiring) | ℓ − c | 2β | **ℓ − c > 2β ?** |
|---|---|---|---|---|---|
| water | 0.85 | 0.30 | 0.55 | 1.50 | **no** (safe) |
| cola | 2.60 | 0.70 | 1.90 | 1.50 | yes (leaks) |
| candy | 2.65 | 0.50 | 2.15 | 1.50 | yes |
| sandwich | 5.15 | 2.20 / 0.30 | 2.95 / **4.85** | 1.55 | **yes** (expiring: large) |

The theorem therefore predicts the excess-unit leak is **concentrated on
high-rent and perishable SKUs and absent on cheap ones** — a sharp, falsifiable
claim the empirics test in §7.

---

## 5. Tightness: dropping each condition (one line each)

Each hypothesis is necessary — dropping it breaks honesty while the others hold.

* **Drop (a) [allow discounts on scarce units / no shadow floor].** Then a
  scarce unit prices off c, not ℓ; Lemma E applies to *every* unit, and the
  excess-unit leak (§4) becomes universal — this is precisely the naive
  independent-disagreement mechanism, which **loses −\$23/day** by letting early
  bargain-hunters drain stock the lunch crowd would have paid list for
  (whitepaper §5c; the shadow floor is what confines Lemma E to genuinely
  excess units).
* **Drop (b) [report-dependent reservation].** If r can be talked down by the
  buyer's own claim (a freed slot worth only its resale — the soft-capacity
  case), the understatement moves *both* the price *and* the reservation the
  price is measured against; the leak is no longer buffer-bounded. This is the
  **boba** collapse: pooled **+\$1,086/day** for the buyer (every stratum
  significant), vs vend's sup-only +\$0.17 (§7, `boba/battery.py`).
* **Drop (c) [independent disagreement].** If d_b is computed from a *separate*
  disclosed valuation than the one entering the trade surplus (or a fixed
  outside not tied to the board), the price-pinning identity of E1
  (p\* = ℓ because d_s = ℓ − c) breaks even for the honest would-be board buyer,
  re-opening discounts on scarce units — the −\$23/day naive collapse again, of
  which (c) is the specific fix.
* **Drop (d) [unbounded outside claim].** With ô free, the buyer sets ô ↑,
  raising d_b directly and shifting the Nash split to the buyer *without any
  WTP lie*. This is the free-walk leak: empirically the largest single channel,
  **walk-only sup +\$0.49/day, significant in every stratum** (§7). Attestation
  (ō = o) closes it exactly (verified-true disclosure ⇒ regret 0 by
  construction, whitepaper §5f).

---

## 6. Corollaries (the four venue results as one statement)

1. **Vend win = pooled tie + buffered excess.** At finite stock most units are
   scarce (Lemma S) or excess with ℓ − c ≤ 2β (Lemma E, (a′) holds). The
   *population mean* of the WTP-understatement gain nets the scarce-day
   self-denial (a liar denies themselves the board deal, §4.1 honest) against
   the residual high-rent excess gains, landing at **≈ 0 / slightly negative**
   — the committed liar sweep's tie. Emergent IC "holds" *on average*.
2. **Boba fail = drop (b).** Soft capacity makes r report-dependent; §5 (b). The
   leak is unbuffered and shows up in the pooled mean, not merely the sup.
3. **Naive collapse = drop (a)/(c).** −\$23/day; §5 (a),(c).
4. **Free-walk leak = drop (d).** The residual attestation banks; §5 (d).

All four are corollaries of the single Theorem.

---

## 7. What the empirics add, and the refinement they force

The proof is about a *single type's best response*. The committed liar sweep
reports a **population mean** over an all-liar arm — which, by Corollary 1,
*must* read ≈ 0 even though a profitable type exists. Task #68B builds the
instrument the proof demands:

* **The unilateral deviation probe** (`vend/battery.py`) holds the world honest
  and the learner converged, and at each buyer's decision node computes the
  honest and each counterfactual-lie realized *true* surplus against the
  identical state — the exact best-response object of §2, with zero state
  contamination.
* **Sup over types**, stratified by (excess-day × high-outside-option) — the §2
  "for every type," not the mean.

Results (6 seeds × 180 measured days, realistic calibrated cell; full table in
`vend/RESULTS.md` and `vend/battery.json`):

| deviation | pooled mean gain \$/day | **sup-over-types** (excess stratum) | significant? |
|---|---|---|---|
| uniform WTP (0.55×) | −0.15 [−0.25, −0.05] | **+0.17 [0.09, 0.25]** | **yes** |
| adaptive WTP (visible stock) | −0.11 | −0.01 [−0.05, 0.03] | no |
| adaptive WTP (oracle-excess) | −0.29 | **+0.15 [0.07, 0.23]** | **yes** |
| per-SKU favorite-only | −0.22 | −0.00 | no |
| free-walk only (cond d) | **+0.49 [0.40, 0.59]** | +0.49 (all strata) | **yes** |

The proof's predictions are borne out **exactly**:

* The **pooled mean hides a real positive type** (Corollary 1): −0.15 pooled,
  **+0.17 on the excess stratum, significant** — the residual (a′) leak on the
  high-rent SKUs (§4.3), invisible to the average.
* The **state-conditioned adaptive liar does *not* open a new leak**: the
  visible-stock adaptive rule yields a *non-significant* sup (−0.01) — its
  trigger (stock ≥ 1.2·par) is a coarse proxy for the excess set. Only an
  **oracle** who sees the true shadow-excess set matches the plain uniform lie
  (+0.15). So the decisive untested deviation the pooled sweep couldn't see
  **concentrates but does not enlarge** the leak beyond §4's bound — honesty
  survives the adaptive/per-SKU refinement up to the same (a′) residual.
* The **free-walk (d) channel is the dominant leak** (+0.49), exactly §5 (d).
* **Warm vs cold learner is a null**: a learner converged on the liar
  population opens no leak a cold learner hid (cold +0.22 vs warm +0.22 on the
  free-walk arm; the WTP-only arms stay ≈ 0). The leak is structural, not a
  learner transient.

**Minimum detectable effect (the power statement).** The committed sweep
(30 days, 1 seed → 6 blocks, sd_block ≈ 0.87) has an 80%-power two-sided MDE of
**\$1.25/day** — it *could not have seen* a \$0.15–0.30 exploit; a tie was the
only possible reading. The battery (6 seeds × 180 days → 216 pooled blocks,
sd_block ≈ 0.58) has MDE **\$0.11/day** on the excess stratum, which is why the
+0.17 leak becomes visible. The refinement is a matter of *power*, and the proof
is what tells you where to point it (the excess × high-outside stratum, the
high-rent SKUs).

The **boba contrast** (`boba/battery.py`, same instrument): the WTP channel
alone leaks **+\$557/day pooled** and with the free-walk claim **+\$1,086/day**,
significant in *every* stratum — no sup-over-types subtlety, because dropping (b)
removes the buffer bound entirely (§5 (b)). The ratio ~\$1,086 vs ~\$0.17 is the
finite-stock shadow price doing its job.

---

## 8. Scope, and where the proof needs more (these are findings)

* **Single unit → quantity.** With q up to Q̄ and diminishing marginal value,
  the buffer is β = max(\$0.75, 0.15·ℓ·q) and the excess rent is
  Σ(ℓ − c) over the traded units; (a′) generalizes to
  Σ(ℓ − cᵢ) ≤ 2β, but the marginal-unit decay means a large basket both raises
  the rent *and* the buffer — the empirical leak stays O(\$0.15/day), consistent
  with the single-unit bound not blowing up. A tight multi-unit (a′) with the
  decay is left as a remark; the sim integrates it and confirms the O(\$0.15)
  scale.
* **Single good → multi-good decoupling.** With many goods the operative
  disagreement can be anchored on a *different* good than the one traded. We
  initially conjectured this *widens* the leak (understate the excess trade-good,
  keep the scarce anchor-good truthful, so d_b does not fall with v̂). The
  deterministic check refutes the naive form: a high truthful anchor makes the
  understated-good deal **infeasible** (g_b < 0 ⇒ NODEAL), *protecting* honesty
  (`decouple.py`, case C). The empirically operative multi-good channel is the
  same single-good Lemma E with o = the best *other-good* board surplus — which
  is exactly what the excess × high-outside stratum captures. A general
  multi-good (a′) is future work; the single-good bound is the right first
  order.
* **The buffer's hard gate.** The proof uses the deployed behavior — the buffer
  gates the Nash-optimal point rather than re-optimizing to a buffer-clearing
  price. A mechanism that re-optimized would admit the leak for
  ℓ − c > β (not 2β); the current gate is the stricter, more protective choice,
  and the empirics are on the 2β side.
* **Deviation class.** We prove IC over WTP-scaling × bounded-outside. Colluding
  buyers, dynamic multi-visit strategies, and reports that co-move v̂ and ô
  adversarially across visits are **not** covered and remain open (whitepaper
  §7, §8).

**Bottom line.** The single-unit characterization goes through, but the four
whitepaper conditions are necessary-not-sufficient: closing the excess-unit leak
requires the buffer to dominate the excess rent, **(a′) ℓ − c ≤ 2β**. Where it
holds, honesty is a *weak* best response (scarce units always; low-rent excess
units) — the buyer is indifferent, every report yielding v − ℓ; lies are
un-rewarded, not punished (weak IC, fragile to trembles/tie-breaking).
Where it fails — high-rent and perishable excess units — a *bounded* leak
(≤ ℓ − c − β per unit, ≈ +\$0.15–0.20/day at the sup over types) survives, hidden
by the pooled mean and closed only by a larger buffer or WTP attestation. That
residual is the honest scope of the "no verification needed at finite stock"
claim, and it is the fifth condition the referee's counterexample was pointing
at.

**Prior-art placement (rigor note).** Lemma S / E1's *disagreement-channel*
neutrality — the honest board-buyer pinned at p\*=ℓ regardless of report — is not
independent content: the single-issue frontier is **linear** (g_s + g_b = v − c),
so van Damme & Lang (2024, Thm 1: ex-post-efficient outcome is independent of a
privately-reported disagreement point under a linear frontier, any correlation)
already forces it. The genuinely non-vacuous content of this theorem is the
**WTP / excess-rent channel and the buffer condition (a′)** — which live in the
*inefficient* region the buffer deliberately creates, exactly where van
Damme–Lang's efficient-mechanism theorems say nothing. This also marks the open
frontier: drop linearity (multi-issue logrolling → a concave frontier) and Thm 1
stops covering us, so whether the coupling still self-cancels is genuinely open
(whitepaper §8).

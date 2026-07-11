# Multi-issue emergent buyer incentive-compatibility: the concave-frontier case

*SNHP Research — the one open theory frontier flagged by the prior audit and by
`THEOREM-IC.md` §8 / `WHITEPAPER.md` §8. Companion and sequel to
`THEOREM-IC.md` (the single-good proof and its condition (a′) `ℓ − c ≤ 2β`).
July 2026. Numerical harness: `paper/theorem_ic_multi_harness.py`
(the multi-good analog of the single-good `regimes2.py`/`decouple.py` checks
`THEOREM-IC.md` cites).*

---

## 0. Verdict, in one paragraph

**PROVED: weak emergent buyer-IC survives the concave logroll frontier, and the
multi-good buffer condition is the curvature-*independent***

> **(A′)   Σ\_{i ∈ excess}(ℓ\_i − c\_i) ≤ 2β.**

The `WHITEPAPER.md` §8 open conjecture asked whether the multi-good condition is
`Σᵢ(ℓ_i − c_i) ≤ 2β`. The answer is **yes — and the bundling complementarity κ
(the concavity that *is* the gains from logrolling) drops out exactly.** It does
so for a sharp reason: under SNHP's event-consistent disagreement, κ enters the
*trade surplus* and the *buyer's own disagreement point* with opposite sign, so
the both-good understatement's "flip" condition and its buffer condition bind on
the **same aggregate disclosed value** `V̂ = Σv̂_i + κ`, and their intersection is
nonempty iff `Σ(ℓ_i − c_i) > 2β`, κ-free. The 2-good bundle is **isomorphic to a
single aggregate good** (list `Σℓ_i`, cost `Σc_i`, value `V̂`), and
`THEOREM-IC`'s single-good Lemma E applies verbatim.

This is *not* a vacuous restatement of van Damme–Lang (2024, Thm 1): their
disagreement-independence needs a **linear** frontier and an **efficient**
mechanism. SNHP has a **concave** frontier and is **inefficient** (the buffer).
The self-cancellation here is an **algebraic identity from event-consistency**,
not a consequence of linearity — which is exactly the gap §8 called open.

**Two boundaries make this a characterization, not a blanket win:**

1. **The dichotomy on the disagreement structure.** The clean `Σ` condition is
   for the **joint-bundle** rule (`boba/policies.py::cart_nash`, the logrolling
   GTM product), whose no-deal event is "buy the whole cart at the board." The
   **separable single-good** rule (`vend/scenario.py::nash_quote`), whose no-deal
   event is "buy your *best single* good at the board," satisfies the strictly
   **weaker** condition `max_{i∈excess}(ℓ_i − c_i) ≤ 2β` — the
   `THEOREM-IC` §8 case-C protection (a high truthful anchor pins `d_b` above any
   understated-good deal, making that deal infeasible) **generalizes**.

2. **The load-bearing hypothesis is extended-(c): event-consistency on the
   *full concave value*.** κ cancels **only** because the disclosed disagreement
   is computed on the *same* concave `V̂` that enters the trade (`boba`'s
   `best_menu_order` values the whole cart via the same `bundle_value` the trade
   uses). If a deployment ever computes the board counterfactual on a *different*
   (e.g. additive, κ-ignoring) value — a violation of extended-(c) — then κ stops
   cancelling and the condition tightens to `Σ(ℓ_i − c_i) + κ ≤ 2β`: **the
   curvature funds a leak.** This is a concrete, checkable engineering invariant,
   and it is the multi-good analog of the single-good condition (c).

Every claim below is confirmed to the penny by the harness (§6). Honest scope
and residual openness in §7.

---

## 1. Model (smallest honest 2-good concave instance)

Two goods `i ∈ {A, B}`, one indivisible unit each.

* **List / ceiling.** `ℓ_i > 0`; every quote is discount-only, `p ≤ Σ_{i∈X} ℓ_i`
  for the traded subset `X` (matching `enumerate_outcomes` / the `cart_nash`
  price rungs `[cost … listv]`).
* **Seller state, per good.** `σ_i ∈ {SCARCE, EXCESS}`, a function of state, not
  of any report (condition (b)). Shadow reservation
  `c_i^σ = c_i` (EXCESS) or `ℓ_i` (SCARCE, the displaced-sale floor), exactly
  `THEOREM-IC` §1. Margin of a traded subset `X` at price `p` is
  `p − Σ_{i∈X} c_i^σ`.
* **Buyer type.** Private true values `v_A, v_B ≥ 0` and a true outside surplus
  `o ≥ 0`. A **continuum** of types.
* **Concave (logroll) frontier.** The buyer's value of a package `X` is
  `V(X) = Σ_{i∈X} v_i + κ·1[X = {A,B}]`, with `κ ≥ 0` the **complementarity —
  the gains from bundling, the curvature itself.** `κ = 0` is the additive
  (linear-frontier) special case van Damme–Lang Thm 1 covers; `κ > 0` bows the
  Pareto frontier out and breaks their linear hypothesis. (Faithful to `boba`,
  where a cart's joint value — drink + toppings down a shared qty ladder, plus
  freed capacity / salvage — strictly exceeds the sum of parts.)
* **Deviation class.** `v̂_i = φ_i · v_i` (multiplicative **per-good WTP-scaling**,
  `φ_i > 0`; `strategic_disclosure`) and `ô ∈ [o, ō]` (bounded-outside, condition
  (d)). Honesty is `(φ_A, φ_B, ô) = (1, 1, o)`.

### 1.1 The mechanism (event-consistent Nash-in-Nash)

Given reports, the broker forms the **event-consistent disagreement point on the
same concave `V̂`** (extended condition (c)):

* **Joint-bundle rule** (`cart_nash`; the logrolling GTM product): the buyer's
  no-deal move is to buy the best *subset* at the board,
  `d_b = max( max_{Y⊆{A,B}} [ V̂(Y) − Σ_{i∈Y}ℓ_i ]_+ , ô )`, and the matching
  seller disagreement `d_s` is the board margin of that subset if the board event
  wins, else 0. **`V̂(Y)` here uses the same κ as the trade** — this is what
  `best_menu_order` does (it prices the whole cart, `bundle_value`).
* **Separable rule** (`nash_quote`; finite-stock single-good venues): deals are
  single-good; the good-`i` deal's disagreement is
  `d_b = max( max_j (v̂_j − ℓ_j)_+ , ô )` — the *best single* board over **all**
  goods (§4.2 / `THEOREM-IC` §8 case C). No κ crosses goods (independent SKUs).

For a candidate subset `X` and price `p`, gains over disagreement are
`g_s(p) = (p − Σ_{i∈X}c_i^σ) − d_s` and `g_b(p) = (V̂(X) − p) − d_b`. The broker
returns

  `(X\*, p\*) = argmax  g_s^w · g_b^{1−w}  s.t.  g_s ≥ 0, g_b ≥ 0, p ≤ Σ_{i∈X}ℓ_i`

(`w = ½` symmetric default; `w > ½` the seller-weight tilt), then applies the
**min-gain buffer**: withdraw unless the Nash-optimal `g_s(X\*,p\*) ≥ β`. As in
`THEOREM-IC` §4, the buffer **gates** the argmax; it does not reprice.
`β = max($0.75, 0.15·Σℓ)` (vend) or `max($0.25, 0.10·Σℓ)` (boba). The buyer's
**realized true surplus** is `V(X\*) − p\*` if the quote is taken (a rational
buyer takes it only if it beats the true fallback), else the true fallback
`max( best-board-on-true-v , o )`. Honesty is a best response iff this is
maximized at truth.

> **Closed form used in the proof and harness.** The log-Nash objective is
> concave in `p` (a sum of concave `ln g_s`, `ln g_b`), so the constrained
> optimum is the clamp of the interior optimum
> `p⁰ = w(V̂ − d_b) + (1−w)(Σc^σ + d_s)` to the feasible interval. At `w=½`,
> `g_s(p⁰) = g_b(p⁰) = ½[ V̂(X) − Σc^σ − d_b − d_s ]` — Nash splits the surplus
> **over disagreement** in half.

---

## 2. The theorem

> **Theorem (multi-good emergent buyer-IC, joint bundle).** Fix the deviation
> class `{φ_A, φ_B > 0} × {ô ∈ [o, ō]}` and the event-consistent joint-bundle
> rule of §1.1. Truthful disclosure maximizes the buyer's realized true surplus
> for **every** type `(v_A, v_B, o)` **iff** in every state the buyer may face,
>
> **(A′)   Σ\_{i ∈ EXCESS}(ℓ\_i − c\_i) ≤ 2β,**
>
> the summed excess rent is at most twice the buffer. The condition is
> **independent of the frontier curvature κ.** SCARCE goods contribute
> `ℓ_i − c_i^σ = ℓ_i − ℓ_i = 0` and are inert.
>
> If (A′) fails, honesty fails: the type whose honest event is "buy the bundle at
> the board" but whose outside `o` is small strictly gains by **understating both
> goods** to flip the joint board to "walk," capturing
>
> **gain = Σ\_{i∈excess}(ℓ\_i − c\_i) − β  > β > 0**
>
> of extra surplus, at bundle price `p\* = Σc_i + β`. Conditions (a), (b), (c),
> (d) each remain necessary but do not substitute for (A′).

Proof: three lemmas — Lemma S-multi (scarce goods inert), Lemma E-multi (the
κ-cancellation + aggregate-good reduction), and the dichotomy (§5). The harness
(§6) confirms the boundary and the exact leak size to the penny.

---

## 3. Lemma S-multi (scarce goods are inert)

**Claim.** A SCARCE good contributes 0 to (A′) and 0 to any leak: it is priced at
list regardless of report, and drops out of the exploitable rent.

**Proof.** On a SCARCE good, `c_i^σ = ℓ_i`, so for any traded subset `X ∋ i` the
per-unit margin contribution is `p_i − ℓ_i ≤ 0` at any `p ≤ ℓ`. Whatever the
event, the seller's disagreement already credits the displaced sale, so a below-
list price on `i` gives `g_s < 0` — infeasible. The scarce good clears only at
list; its rent `ℓ_i − c_i^σ = 0`. Hence only EXCESS goods enter the sum in (A′).
This is the multi-good lift of `THEOREM-IC` Lemma S. ∎

*Numerically* (EXP 6): a bundle of one SCARCE + one EXCESS good with the EXCESS
good satisfying `ℓ_B − c_B = 1.9 < 2β = 2.0` has **sup-regret 0.0000 for every
κ ∈ {0, 1, 2}** — the scarce anchor neither leaks nor is exploited.

---

## 4. Lemma E-multi (the κ-cancellation and the buffer)

Take both goods EXCESS (the only goods that matter, by Lemma S-multi). Write
`L = Σℓ_i`, `C = Σc_i`, `R = L − C = Σ(ℓ_i − c_i)` (the summed excess rent),
`V̂ = v̂_A + v̂_B + κ` (aggregate disclosed value).

### 4.1 Honest = would-be bundle-board buyer ⇒ pinned at list

With `v̂ = v` and the buyer a board buyer on the pair (the joint board
`V(A,B) − L = Σ(v_i − ℓ_i) + κ ≥ o`), the event is BOARD with
`d_b = Σ(v_i − ℓ_i) + κ` and `d_s = R`. Then the total surplus over disagreement
for `X = {A,B}` is

  `S = V̂ − C − d_b − d_s = (Σv_i + κ) − C − (Σ(v_i − ℓ_i) + κ) − R = L − C − R = 0.`

So `g_s = g_b = 0`: the bundle deal cannot beat the board, the price is pinned at
`p\* = L`, and the honest buyer realizes `Σ(v_i − ℓ_i) + κ` — **capturing the
whole complementarity for free.** (This is `THEOREM-IC` E1's price-pinning,
lifted: the seller's threat "I sell you this cart at list" pins the price, and it
holds *with the concave κ present*, because κ sits in `d_b` too.)

### 4.2 The both-good understatement and why κ cancels

To pay, the buyer must lower `d_b`. **Understate both goods** so the *joint*
board turns unprofitable, `V̂ = Σv̂_i + κ < L`, flipping the event to WALK
(`d_b = ô ≈ 0`, `d_s = 0`). The Nash price is `p⁰ = (C + V̂)/2`, and the buyer's
true surplus `V(A,B) − p⁰ = (Σv_i + κ) − (C + V̂)/2` **strictly increases as `V̂`
falls** — the buyer would drive `V̂ → C` (capturing the whole excess rent) but
for the buffer.

> **Lemma (κ-cancellation).** The **flip** condition and the **buffer** condition
> bind on the *same* aggregate `V̂`:
>
> * **flip** (joint board unprofitable): `V̂ < L`,
> * **buffer** (`g_s(p⁰) = (V̂ − C)/2 ≥ β`): `V̂ ≥ C + 2β`.
>
> Both hold simultaneously **iff** `C + 2β < L`, i.e. **`R = Σ(ℓ_i − c_i) > 2β`
> — independent of κ.** The complementarity is absorbed into `V̂` and appears on
> *both* sides, so it cancels. The pair is isomorphic to a single aggregate good
> `(list L, cost C, value V̂)`, and `THEOREM-IC` Lemma E's dichotomy transfers
> verbatim.

Therefore:

* **If `R ≤ 2β` (A′ holds):** no report both flips the joint board (`V̂ < L`) and
  clears the buffer (`V̂ ≥ C + 2β`). Every flip is withdrawn; every buffer-
  clearing report keeps the board event and prices at list (§4.1). Honesty is a
  **weak** best response — the buyer is *indifferent*, every report yielding
  `Σ(v_i − ℓ_i) + κ`; lies are un-rewarded, not punished. ∎
* **If `R > 2β` (A′ fails):** take `V̂ = C + 2β < L` (feasible: split the
  understatement across goods so each `v̂_i < ℓ_i`). The flip holds, the buffer
  binds exactly, `p\* = C + β`. True surplus `Σv_i + κ − (C + β)` versus honest
  `Σ(v_i − ℓ_i) + κ`. **Gain = R − β = Σ(ℓ_i − c_i) − β > β > 0** — κ cancels in
  the *gain* as well. ∎

### 4.3 Where van Damme–Lang stops, and why we don't need it

`THEOREM-IC` §8 notes that the single-issue frontier is linear, so v-D-L Thm 1
already forces the E1 pinning, and the *non-vacuous* content lives in the
inefficient WTP/buffer channel. Here the frontier is **concave** (`κ > 0`), so
Thm 1's hypothesis fails — yet the E1 pinning of §4.1 **still holds**, and the
buffer channel of §4.2 **still self-cancels**. The reason is not linearity: it is
that (i) SNHP is inefficient (the buffer creates the no-trade band the whole
argument lives in), and (ii) the disagreement is event-consistent on the concave
`V̂`, so κ is a common term. This is the precise sense in which the §8 open
question resolves *positively*: **curvature alone does not break emergent IC.**

---

## 5. The two boundaries (this is a characterization, not a blanket win)

### 5.1 Dichotomy on the disagreement structure — `Σ` vs `max`

The clean `Σ`-condition is specific to the **joint-bundle** rule. The
**separable** single-good rule (`nash_quote`) obeys the strictly **weaker**

> **(A′-sep)   max\_{i ∈ excess}(ℓ\_i − c\_i) ≤ 2β.**

*Why.* Deals are single-good and `d_b = max_j(v̂_j − ℓ_j)_+`. To discount good
`i`, the buyer understates `v̂_i`; but if any *other* good `j` carries a high
truthful board `v_j − ℓ_j`, then `d_b ≥ v_j − ℓ_j` exceeds any surplus the
understated good-`i` deal can offer (`v̂_i − p < d_b`), so **`g_b < 0` ⇒ NODEAL**
— the `THEOREM-IC` §8 / `decouple.py` case-C protection. Cross-good rent cannot
be pooled; only the buyer's *own top good* is exposed, and understating it lowers
`d_b` too (single-good self-cancel, `ℓ_i − c_i ≤ 2β`). So the binding condition is
the **max**, not the sum.

*Numerically* (EXP 3, EXP 7): with two excess goods each `ℓ_i − c_i = 1.3 < 2β =
2.0` but `Σ = 2.6 > 2β`, the **separable** rule has **sup-regret 0.0000** (safe),
while the **joint** rule leaks **2.2** on identical goods. And a separable bundle
with one good at `ℓ_A − c_A = 3.0 > 2β` leaks exactly `ℓ_A − c_A − β = 2.0` on
that good alone — the single-good `(a′)` residual, unpooled.

**Reading.** The finite-stock vending venue (separable, `max`) is *more*
protective than the logrolling venue (joint, `Σ`); §8's blanket `Σ` conjecture
was too pessimistic for vend and exactly right for boba.

### 5.2 The event-consistency knife-edge — where κ *does* fund a leak

The κ-cancellation of §4.2 used extended-(c): `d_b` is computed on the same
concave `V̂` (with κ) as the trade. **Drop that** — let the disclosed board be an
additive value `Σ(v̂_i − ℓ_i)_+` that ignores the complementarity — and κ no
longer sits in `d_b`. The flip condition becomes `Σv̂_i < L` (κ-free) while the
buffer stays `V̂ = Σv̂_i + κ ≥ C + 2β`. Their intersection is now nonempty iff

> **`Σ(ℓ_i − c_i) + κ > 2β`,**

so the safe condition tightens to **`Σ(ℓ_i − c_i) + κ ≤ 2β`: the bundling gain
funds the leak.** *Numerically* (EXP 2): with `Σ(ℓ − c) = 2.10 < 2β = 3.0`
(additive-safe) and event-consistent disagreement, **sup-regret is 0.0000 for
every κ up to 3.0** (κ cancels); with the **inconsistent** board, the leak
appears exactly at `Σ(ℓ − c) + κ ≥ 2β` (κ = 0.9 → `3.0`, leak 1.5; κ = 2.0 →
`4.1`, leak 2.6), scaling as `Σ(ℓ − c) + κ − β`.

**This is the multi-good lift of condition (c)**, and it is a checkable code
invariant: *the board counterfactual and the trade value must be the same
function of the reports.* The deployed engines satisfy it (`boba`'s
`best_menu_order` and `cart_nash` both call `bundle_value`; `vend`'s board and
trade both call `buyer_value`). A cached / approximated / additive board estimate
would silently reopen a κ-sized hole.

### 5.3 Tightness of the other conditions

`THEOREM-IC` §5 shows (a), (b), (c), (d) are each necessary single-good; they
remain necessary here (same one-line arguments, per good). Two multi-good
additions: **extended-(c)** (§5.2) is necessary — dropping it costs `κ`; and the
**seller-weight tilt `w > ½`** does *not* close the leak (EXP 5: sup-regret holds
at `2.54–2.55` for `w ∈ [0.5, 1.0]`) — the tilt reallocates surplus *above* the
disagreement but leaves the flip-and-buffer mechanics that create the leak
intact. Monetization is orthogonal to IC.

---

## 6. Numerical confirmation

`python3 paper/theorem_ic_multi_harness.py` implements the exact rule (closed-
form Nash price, buffer-gates-argmax, discount ceiling, both disagreement
structures) and **brute-forces the buyer's best report** over
`{φ_A, φ_B} × ô` for every type in a grid, reporting the **sup-over-types
regret** (positive ⇒ a profitable lie exists). Headline results:

| exp | setup | prediction | sup-regret | verdict |
|---|---|---|---|---|
| 1 | additive joint, `Σ(ℓ−c)=2.60`, `2β=3.0` | safe | **0.0000** | ✓ (A′) |
| 1 | same, `2β=2.4` | leak `Σ(ℓ−c)−β=1.40` | **1.4000** | ✓ exact |
| 1 | cola+candy `Σ=4.05`, `2β=3.0` | leak `4.05−1.5=2.55` | **2.5500** | ✓ exact |
| 1 | water+water `Σ=1.10`, `2β=3.0` | safe | **0.0000** | ✓ |
| 2 | concave, `Σ(ℓ−c)=2.10<2β=3.0`, **consistent**, κ→3.0 | κ cancels | **0.0000 ∀κ** | ✓ **key** |
| 2 | same, **inconsistent** | leak iff `Σ+κ>2β` | 0→1.5→2.6 | ✓ |
| 3 | anchor `v_A=6`, understate B; separable vs joint | sep protected | **0.000 / 2.200** | ✓ dichotomy |
| 4 | boundary trace, symmetric `Σ=2r` | leak iff `2β<Σ` | flips at `β=r` | ✓ sharp |
| 5 | seller tilt `w∈[.5,1]`, `Σ=3.75>2β` | tilt doesn't fix | **~2.55 all w** | ✓ |
| 6 | scarce+excess, `ℓ_B−c_B=1.9<2β=2.0` | scarce inert | **0.0000 ∀κ** | ✓ Lemma S |
| 7 | separable, each `ℓ−c=1.3<2β` but `Σ=2.6>2β` | `max` safe | **0.0000** | ✓ (A′-sep) |
| 7 | separable, one good `ℓ−c=3.0>2β` | leaks `3.0−1.0=2.0` | **2.0000** | ✓ exact |

The leak size matches `Σ(ℓ_i − c_i) − β` **to the penny** in every A′-failing
cell, and the boundary sits exactly at `Σ(ℓ_i − c_i) = 2β` (EXP 4: leak for
`β ≤ Σ/2 − ε`, safe for `β ≥ Σ/2 + ε`). The both-good understatement is the
binding attack — no asymmetric `(φ_A ≠ φ_B)` or outside-inflation report in the
grid beats it.

---

## 7. Scope, honesty, and what stays open

**What is proved.** For the smallest honest 2-good concave model and the
WTP-scaling × bounded-outside deviation class, under the event-consistent
joint-bundle rule, truthful disclosure is a **weak** best response for every type
**iff (A′) `Σ_{i∈excess}(ℓ_i − c_i) ≤ 2β`**, curvature-independent; and the
separable rule obeys the weaker `max_{i∈excess}(ℓ_i − c_i) ≤ 2β`. The reduction
to a single aggregate good makes this a genuine proof (not just numerics), and
the harness confirms it type-by-type.

**Genuine caveats (do not overclaim):**

1. **Weak, not strict.** As single-good, honesty at/below the boundary is
   *indifference* (every report yields the same realized surplus), fragile to
   trembles and tie-breaking. Above the boundary a *bounded* leak
   (`Σ(ℓ−c) − β`) survives, closed by a larger buffer (raise β until `2β ≥
   Σ(ℓ−c)`) or by WTP attestation (pin the report).

2. **Event-consistency is a hypothesis, verified in the code I read, not
   proved universal.** κ cancels *because* `best_menu_order`/`buyer_value` value
   the board on the same function as the trade (§5.2). I checked the deployed
   paths; I did not prove every configuration/venue enforces it. **Recommended
   invariant:** an assertion that the board counterfactual and the trade value
   are the identical call — the multi-good sibling of the "same context + same
   disclosure → same price" invariant (`WHITEPAPER.md` §4.1). If violated, the
   condition is the *tighter* `Σ(ℓ_i − c_i) + κ ≤ 2β`.

3. **Continuum handled by type-independence, not by resolving v-D-L's
   conjecture.** (A′) is type-free, so the "for every type" quantifier is
   discharged directly; I do not resolve van Damme–Lang's general continuum
   open conjecture — I sidestep it via inefficiency + event-consistency.

4. **Deviation class unchanged.** WTP-scaling × bounded-outside only. Colluding
   buyers, dynamic multi-visit strategies, and reports that co-move `v̂` and `ô`
   adversarially across visits remain **open** (as single-good, `THEOREM-IC` §8,
   `WHITEPAPER.md` §7–8). A subtlety the 2-good model *surfaces* but does not
   resolve: with `n > 2` goods and *heterogeneous* excess/scarce mixes, a buyer
   might time understatements across goods and visits; the static per-visit bound
   is `Σ_{i∈excess}(ℓ_i − c_i) ≤ 2β`, but a dynamic budget across visits is
   untested.

**GTM read (honest).** This **modestly strengthens** the multi-issue / logrolling
story that is the flagship product (`gametheory/negotiation/bundle.py`, the
`arena` contract-season logroll, the A2A `negotiate_bundle` endpoint): the
concave logroll frontier does **not**, by itself, break emergent buyer-IC, and
the multi-issue buffer condition is the clean, checkable
`Σ_{i∈excess}(ℓ_i − c_i) ≤ 2β` — provable by reduction to the single good rather
than left open. It is a **constructive, conditional** result, not a blank-check
IC claim: the catch is the event-consistency invariant (§5.2), which is an
engineering property to *test*, not assume, and the same weak/bounded-leak
caveats as single-good apply. The result **complicates** exactly one prior line:
it shows the honest multi-good condition is `Σ`, not the more forgiving `max`,
for the *joint-bundle* venues — so a logrolling deployment with high-rent issues
needs a *larger* buffer (or attestation) than a naive per-issue reading of
`THEOREM-IC` (a′) would suggest.

---

*Cross-references: `THEOREM-IC.md` (single-good proof, conditions (a)–(d), (a′),
Lemmas S/E, §8 case C); `WHITEPAPER.md` §3 (the five-condition Proposition) and
§8 (the open frontier this document addresses). Harness:
`paper/theorem_ic_multi_harness.py`.*

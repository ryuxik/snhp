<!-- ============================================================= -->
<!--  DRAFT-FOR-COMMENT — NOT FOR PUBLICATION OR EXTERNAL SHARING   -->
<!--  Internal founder review only. Nothing here publishes without  -->
<!--  an explicit founder decision. See specaudit/SPEC.md.          -->
<!-- ============================================================= -->

> # ⚠️ DRAFT-FOR-COMMENT — do not publish, do not share externally
>
> This is an internal working draft for founder review, produced under the
> SPECAUDIT fairness protocol (`specaudit/SPEC.md`). It maps **public, versioned**
> specifications of a real-name commerce stack. It contains **no
> security-vulnerability claims** — it is mechanism economics: what deal shapes the
> published specs can *express*, what they *delegate* to implementers, and what
> happens in the delegated space by default. Every mapping row cites an exact
> section/field with the spec version+date (`specaudit/sources.md`). Magnitudes
> are **sensitivity bands over a declared utility family, never point estimates.**
> The mapping is published *for the specs' own engineers to contest*; corrections
> get equal prominence. Several items are explicitly flagged for human
> verification before any external use — see **§Founder-verification flags**.

---

# SPECAUDIT — the 2026 agent-commerce stack as a deal substrate

**Patient:** the published agent-commerce specifications, examined as a substrate
for *deal formation* (not as implementations, not as security artifacts):

| Spec | Owner(s) | Version examined | Role in stack | Source rows |
|------|----------|------------------|---------------|-------------|
| **AP2** — Agent Payments Protocol | Google-led | self-labelled "**v0.2**" (`docs/ap2/specification.md`); no ISO date found on fetched pages; verified against `main`@`e1ea56d` (2026-07-16) | payment authorization via signed mandates | A-1…A-6 |
| **ACP** — Agentic Commerce Protocol | OpenAI + Stripe (+ Meta) | **2026-04-17** (date-versioned; `main`@`c2afc86`, `spec/2026-04-17/` dir last amended 2026-05-01) | discovery → checkout session → delegated payment | C-1…C-6 |
| **UCP** — Universal Commerce Protocol | Google + Shopify | 2026 (Apache-2.0; announced NRF, 2026-01-11) | discovery, capability manifest, checkout, post-purchase | U-1, U-2 |

All fetches: **access date 2026-07-16**. Exact URLs + verbatim quotes:
`specaudit/sources.md`. Primary sources re-verified in a verbatim-quote pass at
AP2 `main`@`e1ea56d` and ACP `main`@`c2afc86` (2026-07-16); per-quote verdicts,
diffs, and unresolved founder-blocking items: `specaudit/quote-audit.md`. UCP is
included **at the stack level only** — a public
spec is fetchable (`ucp.dev`, Google/Shopify docs), but the deep field-level
mapping below is done against AP2 and ACP, whose machine-readable schemas
(SD-JWT claim sets; OpenAPI) were fetched directly.

---

## Executive summary

**The structural finding (stated with certainty, from schemas):** across AP2, ACP,
and UCP, the stack specifies **discovery → cart assembly → checkout → payment
authorization**, and in every one of them **the merchant computes and returns all
commercial terms**. There is **no message anywhere in these specifications that
carries a buyer/agent counteroffer** — no defined semantics for proposing terms and
having them accepted, rejected, or countered; no way to trade price against
delivery timing; no way to bundle price × quantity × timing × conditions as a
single negotiable object. (One schema nuance, caught in our own verification pass
and stated against ourselves: ACP's checkout-request `Item` *does* carry an
agent-writable `unit_amount` — a price field. But the spec attaches no offer
semantics to it: `totals[]` is merchant-recomputed on every response and no
accept/reject/counter message exists. The gap is not "no price field"; it is "no
negotiation protocol.") The agent's degrees of freedom are: *pick catalog items
and quantities where the schema admits them, choose from a merchant-enumerated
fulfillment menu, and submit merchant-defined discount codes.* This is not hidden and it is arguably by design
— but it means **deal formation is the part of the pipeline the stack leaves
unspecified and delegates to implementers.** (S1.)

**Credit where due (S3):** AP2's mandate chain is a *genuine* attestation
primitive. A merchant-signed Checkout JWT, hash-bound into a user- (or agent-)
signed Checkout Mandate, plus a Payment Mandate verified by the credential
provider/network and an **MPP-signed Payment Receipt**, is a real,
non-repudiable receipt of *what was authorized by whom*. ACP likewise models
post-purchase **Orders, Fulfillments, and Adjustments** (including `refund`,
`return`, `dispute`) as first-class objects — richer post-purchase structure than
we expected going in. Neither, however, closes the receipt loop over *delivery*:
AP2 puts the commerce/fulfillment protocol **explicitly out of scope**, and ACP's
delivery/refund records are reconciliation surfaces that sit *after* payment
authorization.

**The measured cost of the delegated gap (S5, banded — a model result over a
declared utility family, not a claim about any deployment):**

- **Deal-formation gap:** a take-it-or-leave-it, merchant-priced checkout with no
  counter forgoes **0%–43% of the joint surplus** the same deal could reach with a
  bundled counteroffer. The band's *shape is the finding*: near **0% when the deal
  has no multi-issue structure** and the merchant publishes a rich fulfillment
  menu (**full-menu lower bound: 0.0%–5.1%**), rising to **~43% in the urgent,
  capacity-tight regime when the merchant offers standard shipping only**
  (**standard-only menu: 0.1%–42.8%**). Up to **~33% of otherwise-beneficial
  trades are walked away from** in that corner; the rest of the loss is buyers
  accepting sub-optimal bundles they cannot counter.
- **Settlement exposure:** because payment is authorized before delivery, a
  deceptive-counterparty fraction of 5%–25% opens a buyer-surplus exposure window
  of **1.4%–11.5%** of realized surplus (**≈ $16–$79 per trade** in model units).

**The fix, at the specs' own extension points (S6, banded):** running the repo's
`snhp` `nash_solver` over (price × qty × date) in the deal-formation step AP2
declares out of scope / before an ACP session is completed recovers **98.2%–99.97%
of the oracle joint surplus** — i.e., it closes essentially all of the S5 gap —
and the negotiated bundle is exactly what the merchant then signs (AP2 Checkout
Mandate) or what the ACP session completes with, terms unchanged. Receipt-gating
settlement on a delivery attestation (which AP2's Payment Receipt and ACP's
Fulfillment/Adjustment objects already make expressible) recovers the S5b
exposure band.

---

## S1 — Expressible deal space (structural)

**Question:** from each spec's own message schemas, can an offer/counteroffer carry
multi-issue terms (price × quantity × delivery/timing × conditions)? Is there **any**
counteroffer surface at all?

**Method:** read directly off the machine-readable schemas — ACP's OpenAPI request
bodies (C-2) and AP2's SD-JWT claim sets (A-2…A-4). Field/endpoint facts below are
`[schema]`-level and stated with certainty.

### Contract-space table

| Deal dimension | AP2 (Checkout/Payment Mandate) | ACP (Checkout Session) | UCP (Checkout capability) | Citation |
|---|---|---|---|---|
| **Price — merchant sets** | Merchant signs `checkout_jwt`; AP2 defers the payload ("The details of the payload are outside the scope of this specification"; with UCP it "MUST be the Checkout object") — i.e., UCP's merchant-priced line items and totals. | `totals[]` (incl. `total`) is a **merchant-computed response**; never an agent request field. | Catalog carries merchant `price` (e.g. `26550`); merchant is "Merchant of Record." | A-3; C-2; U-1/U-2 |
| **Price — agent counter?** | **None.** Closed mandate is `checkout_hash` over the *merchant's* JWT; mandates move open → closed and no message carries terms back (paraphrase; schema-supported). | **None as protocol.** The request `Item` is `{id, name, unit_amount}` (required: `id`) — `unit_amount` **is agent-writable**, but no accept/reject/counter semantics attach to it; every response returns merchant-recomputed `totals[]`. Other agent inputs: `buyer`, `fulfillment_*`, `discounts{codes}`. | **None.** Published material shows only merchant-defined discount codes; no agent-priced surface appears (paraphrase of the published examples). | A-3; C-2; U-2 |
| **Quantity** | Fixed in the signed cart the agent assembled. | `quantity` (min 1) lives on the merchant's **response** `LineItem`, not the request `Item`; request composition is by item `id`. | Agent-composable via Cart Building. | A-3; C-2; U-1 |
| **Delivery / timing** | In the merchant cart; not independently negotiable. | Agent **selects from** `fulfillment_options` via `selected_fulfillment_options`; cannot set its own terms/price. | Merchant shipping options; agent selects. | A-3; C-2; U-1 |
| **Conditions (returns, SLAs, penalties)** | Policy fields ride the UCP Checkout object that AP2's `checkout_jwt` carries (AP2 itself declares the payload out of scope) — **merchant-stated, not negotiated.** | Merchant-stated (`Order.support`, policy fields); refund/return exist post-hoc as `Adjustment.type`. | Merchant-stated. | A-3; C-3 |
| **Bundle (joint multi-issue object)** | No. Terms are packaged by the merchant, taken or left. | No. Session is a merchant-authoritative state the agent nudges by composition, not a counteroffer. | No. | A-2/A-3; C-2 |
| **A counteroffer message exists?** | **No.** | **No.** | **No.** | — |

**Finding (certain).** None of the three specifications defines a counteroffer.
The expressible "deal" is a point the merchant priced, which the agent may accept,
abandon, or nudge by *changing what is in the cart* — not by proposing terms. The
closest thing to a price surface in the stack is ACP's agent-writable
`Item.unit_amount`, and it is semantically inert: nothing in the spec describes,
let alone obliges, a merchant response to it. The richest surface is ACP's
session-update loop, but every update returns `totals[]` **recomputed by the
merchant** (C-2); it is cart *composition*, not *bargaining*.

**Fairness note on the word "negotiation."** ACP's RFC list contains
`capability_negotiation`, and UCP documents "capability discovery" (C-1, U-2).
Verified against the primary text, both denote **feature/capability discovery** —
UCP's `/.well-known/ucp` manifest; ACP's `capabilities` field — i.e., which
protocol features a party supports, **not** negotiation of commercial terms. We
flag this so the S1 finding is not misread as contradicting the specs' own words;
their "negotiation" and our "counteroffer" are different objects.

**Credit due.** ACP/UCP do let a merchant publish a *fulfillment-option menu*
(delivery-speed choices), which is strictly more expressive than a single
take-it-or-leave-it ship date. That menu materially narrows the timing gap (it is
the difference between the two S5 sub-bands below). The residual limitation is that
the menu is merchant-enumerated and merchant-priced with no counter.

---

## S2 — Settlement & recourse (structural)

| Property | AP2 | ACP | Citation |
|---|---|---|---|
| **Payment vs delivery ordering** | Payment authorized when MPP verifies the Payment Mandate in the token and returns an **MPP-signed Payment Receipt**; **delivery is out of scope** ("The exact details of the Commerce Protocol … are outside the scope of AP2"). | Payment applied at `POST /checkout_sessions/{id}/complete` (creates the `Order`); fulfillment (`Fulfillment.status` shipped/delivered) follows. **Authorization precedes delivery.** | A-2, A-5; C-2, C-3 |
| **Amount cap primitive** | Payment Mandate can carry an `amount_range{min,max}` (open) or concrete `payment_amount` (closed). | Delegated-payment `allowance.max_amount` (`reason:"one_time"`), `merchant_id`, `expires_at`, bound to `checkout_session_id`. **Fixed at token creation.** | A-4; C-4 |
| **Clawback / dispute surface** | Checkout Mandate is "shared with the Merchant so they can use this as evidence in case of disputes" — **dispute evidence** (evidentiary, not a settlement mechanism). | First-class `Adjustment.type` ∈ {`refund`,`credit`,`return`,`exchange`,`dispute`} on the `Order`; `amount_refunded` total. Rides existing card rails via the PSP. | A-6; C-3 |
| **Deceptive-counterparty exposure window (per spec's own flow)** | Undefined at the AP2 layer — inherited by whatever commerce protocol carries delivery. | Between `complete` (funds authorized up to `max_amount`) and delivery/refund. Recourse is **post-hoc** (chargeback / refund Adjustment), not a pre-settlement gate. | A-2; C-3, C-4 |

**Finding (certain).** Both stacks authorize payment against a **merchant-asserted**
cart *before* delivery is proven. Recourse exists but is **reconciliation after the
fact**, not a settlement ordering that withholds funds pending a delivery
attestation. This is the exposure S5b quantifies.

**Credit due / better than expected.** ACP's post-purchase model is richer than a
naive "checkout-only" reading would predict: `Order.fulfillments[]`,
`Order.adjustments[]` with explicit `dispute`/`refund`/`return`/`exchange` types,
and `OrderLineItem.status` ∈ {processing, partial, fulfilled, removed} (C-3). ACP
*does* model the post-purchase lifecycle as data; it just doesn't gate the money on
it. That is a fair and important distinction and we draw it explicitly.

---

## S3 — Attestation surface (structural, credit due)

This section is deliberately generous; the fairness protocol requires crediting a
real receipt primitive with the same rigor as any gap.

**What AP2 signs, and by whom (A-2…A-5):**

| Object | Signer | Covers | Format |
|---|---|---|---|
| `checkout_jwt` | **Merchant** | the checkout payload AP2 itself defers ("The details of the payload are outside the scope of this specification"; with UCP it "MUST be the Checkout object" — merchant-priced line items, totals, currency, fulfillment/policy fields per UCP) | merchant-signed JWT |
| Checkout Mandate (closed) | **User** (`user_sk`, human-present) or **Agent** (`agent_sk`, human-not-present) | `checkout_hash` binding to the exact `checkout_jwt` | SD-JWT, `vct:mandate.checkout.1` |
| Payment Mandate | User or Agent; **verified by** Credential Provider, Network, MPP | `transaction_id`, `payee`, `payment_amount`/`amount_range`, `payment_instrument`, `constraints` | SD-JWT, `vct:mandate.payment.1` |
| **Payment Receipt** | **MPP** | the authorized transaction | MPP-signed, returned to SA, CP, Network |

**What this genuinely achieves.** A verifier can later prove, non-repudiably, *what
cart the merchant offered*, *that a specific principal authorized exactly that cart*
(hash binding defeats cart-swap after consent), *within what payment constraints*,
and *that the processor acknowledged it*. That is a real, well-constructed receipt
chain over the **authorization** event. Say so plainly: **AP2's mandate chain is a
legitimate attestation primitive, not marketing.**

**Where the chain is complete vs where it breaks (stated as scope, not as a flaw):**

- **Complete** over *offer + authorization + payment acknowledgement*.
- **Breaks / absent** over *delivery and conformance*: nothing in AP2 signs "the
  goods that arrived match the cart," because commerce/fulfillment is out of scope
  (A-2). The receipt proves *what was promised and authorized*, not *what was
  delivered*.
- **Signer nuance to flag:** in the human-not-present flow the **agent** signs the
  closed mandates with `agent_sk` (A-5). The receipt then attests *agent*
  authorization under previously user-signed *open* constraints — a weaker human-
  consent statement than the human-present case. This is a correct reading of the
  flow, but whether the open-mandate constraints are meant to be sufficient user
  consent for the closed agent-signed transaction is a **spec-intent question we do
  not resolve** (see Founder-verification flags).

**ACP attestation.** ACP's transport is signed at the API/PSP layer and its
delegated-payment token (`vt_…`, C-4) is a scoped capability, not a content
attestation of the cart in the AP2 sense. ACP's evidentiary weight lives in the
`Order`/`Adjustment` records (C-3). Fair reading: ACP has strong *operational*
records and a scoped payment token; AP2 has the stronger *cryptographic content*
receipt. They are complementary, and UCP explicitly composes AP2 for payment (U-1).

---

## S4 — Chain / delegation flows (structural)

**AP2 roles (A-6):** User → Shopping Agent (SA) → Merchant (M) / Merchant Payment
Processor (MPP) → Credential Provider (CP) → Network & Issuer, with a **Trusted
Surface (TS)** for human consent.

| Link | Pre-commitment that exists | Hold-up surface inherited by implementers |
|---|---|---|
| User → SA | Open mandate constraints (`amount_range`, allowed merchants/line items) signed via TS | SA has discretion inside the open constraints; in human-not-present it *signs* the closed deal (`agent_sk`). Delegation breadth is an implementer policy choice. |
| SA → Merchant | Merchant signs the cart it "will fulfill" (A-6) | The merchant's signature commits to *offer + fulfillment intent*, not to a *price found by bargaining* — because there is no bargaining step (S1). Any surplus split is set by the merchant's posted price. |
| SA → CP → Network | Payment Mandate + token scope the spend | Sound for spend control; silent on delivery conformance (S2/S3). |
| **Deal formation (the gap)** | **None specified** | This is the step S5/S6 target. AP2 says commerce details are out of scope (A-2); ACP/UCP fix terms merchant-side. Whatever an implementer bolts on here — pricing, counteroffers, bundling — is unspecified and un-attested by the stack. |

**Finding (certain).** Pre-commitment in the stack is strong over *payment scope*
and *cart integrity* and **absent over *deal terms***. The hold-up surface the
specs hand to implementers is precisely the deal-formation step — which is where
the `snhp` mechanism lives.

---

## S5 — Default-gap simulation (magnitude, **banded**)

*Full method, code, and seeds: `specaudit/gap_sim.py`; regenerate with the command
in §Regeneration. This is a **model result over a declared utility family**, a
measure of the delegated gap — NOT a measurement of any real deployment and NOT a
flaw in any spec.*

**Declared utility family (stated explicitly).** We do **not** invent utilities. We
import, read-only, the exact economic primitives the golden-validated MERIDIAN
harness uses (`meridian.agents.{buyer_gross_value, supplier_cost, joint_surplus}`)
and the repo's own `snhp` `nash_solver`. Opportunities are drawn i.i.d. from the
**same parameter ranges MERIDIAN's `MarketConfig` uses**, reproduced as three
"multi-issue intensity" regimes — `LOW` (= MERIDIAN A2: slack deadlines, low
urgency, loose capacity), `MID` (= BASE), `HIGH` (= A1: tight deadlines, urgent,
tight capacity). Two further band dimensions: **markup** ∈ {0.05, 0.18, 0.32}
(MERIDIAN's floor→opening supplier markups) and **fulfillment-menu richness** ∈
{standard-only, standard+express, full grid}. 8 seeds × 600 opportunities per cell.

**What the spec world is, in the model.** The merchant prices every option at
`cost·(1+markup)` and posts it; the agent (no counter surface, per S1) composes
quantity freely and picks a delivery date **from the merchant's menu**, accepting
iff its own surplus ≥ 0. We hand the spec its **best case** (a merchant that
enumerates the *full* qty×date grid), so the full-menu numbers are a **lower bound**
on what a coarser real menu forgoes.

### S5a — deal-formation gap (foregone joint surplus vs the bundled oracle)

| Band (fraction of oracle joint surplus foregone) | Low | High |
|---|---|---|
| **Overall** (all regimes × markups × menus) | **0.0%** | **42.8%** |
| Full menu (generous — merchant offers every date) | 0.0% | **5.1%** |
| Standard-shipping-only menu (MPX-like, no faster date obtainable) | 0.1% | **42.8%** |
| Walk-away (foregone-trade) share of beneficial trades | 0.0% | 32.8% |

**Reading the band honestly.** The gap is **conditional on the deal having
multi-issue structure and on the merchant's menu being coarse.** When neither holds
(slack deadlines, rich menu) the fixed-cart checkout captures essentially the whole
pie (gap → 0). When both hold (urgent buyer, capacity-tight seller, standard
shipping only) the no-counter posted-price checkout leaves up to ~43% of the joint
surplus unrealized — partly by walking away from ~a third of beneficial trades,
mostly by the buyer accepting a late/oversized bundle it cannot counter. The
**full-menu lower bound (≤5.1%) is itself a credit to ACP/UCP**: their
fulfillment-option menus do most of the work a naive single-ship-date checkout
could not.

### S5b — settlement exposure (payment-before-delivery, S2 channel)

Deceptive-counterparty fraction 5%→25%; a bad order under-delivers 50% of quantity.

| Band | Low | High |
|---|---|---|
| Buyer-surplus exposure (share of gated surplus) | **1.4%** | **11.5%** |
| Exposure per trade (model $) | $15.5 | $78.9 |

Exposure scales cleanly with the deceptive fraction and is largest in the urgent
regime (a shortfall hurts an urgent buyer more).

---

## S6 — The fix demo (**banded**), at the specs' own extension points

**S6a — bundled negotiation before checkout.** We slot the repo's `snhp`
`nash_solver` over (price × qty × date) into the **deal-formation step AP2 declares
out of scope** / **before an ACP session is `complete`d**. The negotiated bundle is
then exactly what the merchant signs (AP2 `checkout_jwt` → Checkout Mandate,
unchanged) or what the ACP session completes with. No new message type is required:
it occupies the gap the stack already delegates.

| Band | Low | High |
|---|---|---|
| Oracle joint surplus recovered by the bundled layer | **98.2%** | **99.97%** |

I.e. the negotiation layer closes essentially all of the S5a gap; the residual
1–2% is the solver's discrete price/qty/date grid, not an economic loss. The fix is
strongest exactly where the gap is largest (urgent, tight-menu regime).

**S6b — receipt-gated settlement.** Release funds only against a delivery
attestation. AP2 already mints an **MPP-signed Payment Receipt** and ACP already
models **Fulfillment + refund Adjustments** (S3), so the attestation object exists;
the change is to make settlement *wait* for it (escrow/hold vs pay-on-authorize).
In the model this converts the S5b exposure band (1.4%–11.5%; $15.5–$78.9/trade)
into recovered buyer surplus, because the buyer pays only for what actually arrives.

**Framing guardrail.** S6 is a demonstration on the *same declared family*, not a
benchmark against these companies' internal systems. The honest claim is narrow:
*the specific surplus the no-counter delegation leaves on the table (S5) is
recoverable by a bundled-counteroffer + receipt-gate layer that fits the specs'
existing extension points — and by construction that layer recovers ~all of it in a
frictionless model.* Real recovery net of negotiation friction, agent error, and
merchant participation is out of this model's scope.

---

## What we did NOT find

1. **No hidden counteroffer surface.** We looked, at the schema level, for any
   negotiation construct in ACP (`create`/`update`/`complete` bodies) and any
   bidirectional bargaining construct in AP2. ACP's request `Item` does expose an
   agent-writable `unit_amount` (a price field), but no spec text gives it offer
   semantics — no accept/reject/counter response is defined anywhere (S1). We did
   **not** find that the specs *claim* to support term negotiation and fail to —
   they do not claim it; ACP's `capability_negotiation` RFC and UCP's "capability
   discovery" are feature discovery (verified, U-2).
2. **No security vulnerability.** Consistent with the protocol, we found nothing we
   would characterize as a vulnerability, exploit, or spec bug. The gap is an
   *economic delegation*, not a defect.
3. **No AP2 mandate that signs delivery/conformance.** The receipt chain is complete
   over authorization and, by the spec's own words, stops before fulfillment (S3).
4. **No evidence the March-2026 ACP commercial pullback was mechanism-driven.** The
   ChatGPT Instant Checkout wind-down (~2026-03-05, reported low conversion; X-1…X-3)
   is cited **only** as commercial-outcome context. We did **not** find, and do not
   assert, a causal link between the S1 deal-formation gap and that outcome; the
   reported cause is adoption/conversion. Treat as reported, secondary sources.
5. **No point estimate we would stand behind.** Every S5/S6 magnitude is a band;
   the single most important qualitative fact is that the low edge is ~0.

---

## Where the specs do better than we expected (credit)

- **AP2 mandate chain** is a real cryptographic content-receipt with hash binding
  that defeats post-consent cart swapping (S3).
- **ACP post-purchase model** treats fulfillment, refunds, returns, exchanges, and
  disputes as **first-class typed objects** — more lifecycle structure than a
  checkout-only spec would need (S2/S3).
- **Fulfillment-option menus** (ACP/UCP) make delivery timing partially expressible
  and demonstrably shrink the deal-formation gap (the ≤5.1% full-menu bound, S5a).
- **UCP capability discovery** (`/.well-known/ucp`) is a clean, honest handshake and
  is explicitly composable with AP2 for payment (U-1/U-2).

---

## Founder-verification flags (do not resolve by guessing against a real company)

Each of these is a place where we were **unsure of the spec's intent** or hit a
**provenance limit**. Resolve with a human before any external use.
*Status (2026-07-16): a verbatim-quote pass against pinned raw sources
(AP2 `main`@`e1ea56d`, ACP `main`@`c2afc86`) resolved flags 1, 3, 4, 5, 6 as
noted inline below; the full evidence table is `specaudit/quote-audit.md`.*

1. **AP2 mandate count/naming/format.** The task brief and prior memory describe
   AP2 as "three Mandates: Intent/Cart/Payment as **W3C Verifiable Credentials**,
   v0.2.0, April 2026." The **current `main`-branch spec we fetched** describes
   **two** mandates — **Checkout Mandate + Payment Mandate** — as **SD-JWTs** with
   open/closed states (the "Intent" role surviving as the *open* mandate). We could
   **not** verify a "v0.2.0" semver or an explicit date on the pages fetched (the
   body self-labels "v0.2"). **Before publishing, confirm which AP2 revision we are
   mapping and reconcile the VC-vs-SD-JWT and 2-vs-3-mandate wording.** We mapped the
   current spec and flagged rather than silently reconciling.
   *Resolved CONFIRMED-AS-WRITTEN at `e1ea56d`: `specification.md` names exactly
   two mandate types, SD-JWT throughout, zero W3C/VC hits — though AP2's landing
   page still markets "verifiable digital credentials," so the wording seam is
   real and worth one careful sentence if raised.*
2. **Human-not-present consent sufficiency (S3).** Whether user-signed *open*
   constraints are intended to constitute sufficient consent for an *agent-signed
   closed* transaction is a design-intent question. We described the mechanism; we
   did not judge its adequacy.
3. **ACP payment capture vs authorization timing.** The OpenAPI makes `complete`
   create the order and apply the delegated token (auth up to `max_amount`); whether
   funds are *captured* immediately or at fulfillment is a PSP/merchant policy the
   protocol doesn't pin. Our S5b models the authorization-before-delivery ordering;
   confirm this matches intended deployment semantics before citing externally.
   *Resolved CONFIRMED-AS-WRITTEN: neither OpenAPI pins capture timing; it is
   PSP/merchant policy, exactly as the row states.*
4. **Verbatim-quote pass.** Several table cells rely on the fetch summarizer's
   rendering of spec prose (marked `[paraphrase]` in `sources.md`). Field names and
   enums are `[schema]`-exact; **prose quotes should be re-verified against the
   primary text before any external publication.**
   *Run 2026-07-16 — and it caught real defects: 40 items checked, 4 MISMATCH /
   3 UNSUPPORTED / 2 OVERSTATED, including the S1 keystone cell (ACP's request
   `Item` DOES carry an agent-writable `unit_amount`, and `quantity` is
   response-side) and a UCP field enumeration misattributed to AP2 (whose
   `checkout_jwt` payload is explicitly out of scope). All defective passages
   have been redrafted against the pinned sources; diffs in `quote-audit.md`.
   The structural finding survives in a stronger form ("no negotiation
   semantics" rather than "no price field").*
5. **UCP depth.** UCP is mapped at stack level from `ucp.dev`/vendor docs, not from
   its full checkout JSON schema. If UCP is to be a first-class subject, fetch and
   map its checkout capability schema directly.
   *Resolved CONFIRMED-AS-WRITTEN: the pass verified the UCP quotes used against
   `ucp.dev`/the vendor blog (two paraphrases-in-quotes were fixed), but no UCP
   checkout schema was fetched — the depth limit stands as stated.*
6. **Instant-Checkout data point provenance.** The ~2026-03-05 pullback rests on
   multiple secondary outlets (X-1…X-3), not a single primary OpenAI post. Keep it
   as clearly-attributed context or source a primary statement.
   *Resolved CONFIRMED-AS-WRITTEN: corroborated across outlets (incl. an OpenAI
   spokesperson confirming the shift) but still secondary; the report's caveat is
   accurate and must stay.*

---

## Corrections policy

This mapping is published **for the specs' own engineers to contest.** If any row
misreads a schema, cites a superseded version, or mischaracterizes intent, send the
exact field/section and the correction will be republished **with the same
prominence as the original claim**, the version pin updated, and the affected
S5/S6 cells regenerated. Structural claims are falsifiable against the cited
schemas; magnitude claims are bands, reproducible from the seeded code below.

## Regeneration

```
python -m specaudit.gap_sim                       # regenerate results/gap_results.json
python -m pytest specaudit/test_specaudit.py -q   # 12 seeded invariant tests
```

Utility primitives are imported **read-only** from `meridian/` (never modified);
the negotiation engine is the repo's `snhp/nash_solver.py`. Sources, access dates,
and verbatim quotes: `specaudit/sources.md`.

---

<!-- DRAFT-FOR-COMMENT — internal founder review only — do not publish -->
*End of draft. Not for publication or external sharing without an explicit founder
decision.*

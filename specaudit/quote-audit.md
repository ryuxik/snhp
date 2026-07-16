<!-- ============================================================= -->
<!--  DRAFT-FOR-COMMENT — VERBATIM-QUOTE PASS over specaudit/report.md -->
<!--  Internal founder review only. See specaudit/SPEC.md.          -->
<!-- ============================================================= -->

# SPECAUDIT — verbatim-quote pass

Pre-publication integrity check of `specaudit/report.md`. Every quoted passage
and factual citation in the report was inventoried, then each was checked
**character-for-character** against the live primary source. For GitHub-hosted
specs the **raw** file bytes were fetched at a pinned commit (not a summariser
rendering), so the diffs below are exact.

**Pinned sources (verified 2026-07-16):**

| Spec | Repo / site | Pinned identifier |
|---|---|---|
| AP2 | `google-agentic-commerce/AP2` | `main` @ `e1ea56db72a6385bce3e5c1112b3a56ce60acb43` (docs self-label **v0.2**; `docs/ap2/*.md` last touched 2026-04-28 "Release Ap2 v0.2") |
| ACP | `agentic-commerce-protocol/agentic-commerce-protocol` | `main` @ `c2afc863b46b6bb64fbc2be969bff25ee6eab652`; `spec/2026-04-17/openapi/*` (dir **amended 2026-05-01** by "Order Schema — Post-Checkout Alignment" #232) |
| UCP | `ucp.dev`, `developers.googleblog.com` | live pages (no machine-readable schema fetched — stack-level only, per report) |
| Secondary | Stripe newsroom/docs; searchengineland et al. | live pages (attributed context) |

**No drift found on any pinned spec file** between when the report was written
(access date 2026-07-16) and this pass: the AP2 docs are stable since 2026-04-28
and the ACP OpenAPI since 2026-05-01, both well before the report's access date.
Every MISMATCH below is therefore a **read error at write time**, not source
movement — the summariser used to build `sources.md` mis-rendered spec prose and
schema in the ways catalogued here.

---

## 1. Inventory & verdicts

Verdict key: **OK** = verbatim / verbatim-with-trivial-truncation · **MINOR** =
whitespace/hard-wrap/ellipsis/terminal-punctuation only · **MISMATCH** = wording
differs · **UNSUPPORTED** = quoted string not found in the cited source ·
**OVERSTATED** = citation exists but claims more/other than the source says ·
**SUPPORTED** = non-quoted citation the source backs.

### AP2 (verified @ `e1ea56d`)

| # | Report loc | Quote / claim (as printed) | Source loc | Verdict |
|---|---|---|---|---|
| 1 | top table L30; A-1/A-2 | self-label "**v0.2**" | `specification.md` L1 `# Agentic Payment Protocol (v0.2)`; landing "AP2 v0.2 Release" | **OK** |
| 2 | top table L30 | "no ISO date found on fetched pages" | none present on spec or landing | **SUPPORTED** |
| 3 | exec L64; S2 L145; S3 L190 | AP2 fulfillment "**explicitly out of scope**" | `specification.md` L20-22 | **OK** |
| 4 | S2 L145 | "The exact details of the Commerce Protocol … are outside the scope of AP2." | `specification.md` L20-22 | **OK** (ellipsis `…` replaces the parenthetical "(e.g., catalog APIs, checkout updates, and specific APIs for communication between the different roles)"; words exact) |
| 5 | S1 L110; **S3 L173** | `checkout_jwt` "**line items with … prices, quantities, total price, currency**" / "merchant identity, line items+prices, quantities, total, currency, shipping/return policy" | `checkout_mandate.md` L30-33 | **UNSUPPORTED — founder-blocking.** See §2. |
| 6 | S1 L114 | `checkout_jwt` includes "**shipping and return policies**" | `checkout_mandate.md` L30-33 | **UNSUPPORTED — founder-blocking.** Same root as #5. |
| 7 | S1 L111 | closed mandate is `checkout_hash` over merchant JWT; "**unidirectional flow from open to closed**" | `checkout_mandate.md` (whole) | **MISMATCH — founder-blocking.** Phrase absent; `sources.md` labels it `[paraphrase]`. See §2. |
| 8 | S3 L172-175 | Checkout Mandate = SD-JWT `vct: mandate.checkout.1`; Payment Mandate = SD-JWT `vct: mandate.payment.1` | grep of all AP2 docs: `mandate.checkout.1`, `mandate.checkout.open.1`, `mandate.payment.1`, `mandate.payment.open.1` present; "SD-JWT" ×18 | **OK** |
| 9 | S3 L176; exec L59 | "**MPP-signed Payment Receipt**" returned to SA, CP, Network | `flows.md` L75-76 & L165-166: "The MPP-signed Payment Receipt is returned to the Shopping Agent, Credential Provider, and Network" | **OK** (truncation at "Network." only) |
| 10 | S2 L146 | Payment Mandate `amount_range{min,max}` / concrete `payment_amount` | `payment_mandate.md` L178-179 "MUST be within the range defined by `min` and `max`" | **OK** |
| 11 | S2 L147 | Checkout Mandate ~~"may be shared with the merchant"~~ → **"shared with the Merchant so they can use this as evidence in case of disputes"** as dispute evidence | `overview.md` L212-213 | **MISMATCH → CORRECTED.** See §2 + §3. |
| 12 | S4 L218 | Merchant signs the cart it "**will fulfill**" | `overview.md` L200-201 "signaling that they will fulfill this cart" | **OK** |
| 13 | S4 L211; S3 | six roles: SA, CP, M, MPP, TS, Network & Issuer | `overview.md` roles section | **SUPPORTED** |
| 14 | S3 L192-198; flag 2 | human-not-present: agent signs closed mandates with `agent_sk` | `flows.md` L146-147 "signs both closed Mandates using the `agent_sk`" | **OK** |

### ACP (verified @ `c2afc86`, `spec/2026-04-17/openapi/`)

| # | Report loc | Quote / claim | Source loc | Verdict |
|---|---|---|---|---|
| 15 | S1 L110; C-2 | `totals[]` (incl. `total`) is a merchant-computed response, enum-typed | `openapi.agentic_checkout.yaml` `Total.type` enum L1409-1421 (12 values: items_base_amount…total…amount_refunded) — **exact** | **OK** |
| 16 | S1 L111; C-2 | "**No request body admits `unit_amount`/`total`. Agent input caps at `line_items{id,quantity}`**" | `Item` schema L991-1010 (`line_items` `$ref` in create L2975 & update L3033) | **MISMATCH (schema) — founder-blocking, S1 keystone.** See §2. |
| 17 | S1 L112; C-2 | Quantity "Agent-composable: `line_items[].quantity` (min 1)" | request `Item` has no `quantity`; `quantity`+`minimum:1` are on the **response** `LineItem` L1270-1272 | **OVERSTATED.** Same root as #16. |
| 18 | S1 L113; C-2 | agent "**selects from** `fulfillment_options` via `selected_fulfillment_options`" | update body `selected_fulfillment_options` L3061 | **SUPPORTED** |
| 19 | S1 L111; C-2 | discounts = `discounts{codes}`; "merchant-defined codes" | `DiscountsRequest.codes` L2653 | **SUPPORTED** (schema half; the UCP prose half is #27) |
| 20 | endpoints; C-2 | `POST /checkout_sessions`, `GET/POST /checkout_sessions/{id}`, `…/complete`, `…/cancel` | paths L16/121/217/313 (param is `{checkout_session_id}`) | **OK** (report uses `{id}` shorthand — MINOR) |
| 21 | S2 L145; C-2/C-3 | payment applied at `…/complete` (creates `Order`); fulfillment follows | complete endpoint L217; `CheckoutSessionWithOrder` | **SUPPORTED** |
| 22 | S2 L146; C-4 | `allowance.max_amount` (`reason:"one_time"`), `merchant_id`, `expires_at`, bound to `checkout_session_id`, fixed at creation; token `vt_…` | `openapi.delegate_payment.yaml` `Allowance` L518-556; token id `vt_…` L104; "Tokenizes a credential for controlled usage by the merchant's PSP per the **Allowance** constraints" L22 | **OK** |
| 23 | S2 L147; S3; C-3 | "First-class `Adjustment.type` ∈ {`refund`,`credit`,`return`,`exchange`,`dispute`}" | `Adjustment.type` L2434-2436 | **OVERSTATED (minor).** `type` is now a free **string** ("MUST accept unrecognized values gracefully"), not a strict enum, and its **defined values** are 7 — the report's 5 **plus** `price_adjustment` and `cancellation`. Claim ("these are first-class typed") holds; the `∈ {5}` framing is incomplete/outdated (loosened by the 2026-05-01 amendment). |
| 24 | S2 L158; C-3 | `OrderLineItem.status` ∈ {processing, partial, fulfilled, removed} | L2263 "Defined values: 'processing', 'partial', 'fulfilled', 'removed'" | **OK** (string not strict enum — MINOR; four values exact) |
| 25 | credit L61; C-3 | `Order` = {id, checkout_session_id, order_number, permalink_url, status, estimated_delivery, confirmation, support, line_items, fulfillments, adjustments, totals} | `Order` L2163+ | **SUPPORTED** |
| 26 | S2; C-3 | Message types `MessageInfo/Warning/Error`; codes incl. `out_of_stock`, `payment_declined` | L1712/1765/1839; code enum L1855-1868 (incl. both) | **SUPPORTED** (sources hedges "incl.") |
| 27 | S1 L128; fairness | CheckoutSession.status enum (11 values) | L2782-2794 — **exact, same order** | **OK** |
| 28 | fairness L126; C-1 | "ACP's RFC list contains `capability_negotiation`" (+ `discount_extension`) | repo tree: `rfcs/rfc.capability_negotiation.md`; `examples/.../discount-extension/` | **SUPPORTED** |
| 29 | S3 L200; C-4 | delegated-payment token is a scoped capability (`vt_…`), not a content attestation | `openapi.delegate_payment.yaml` (allowance-scoped) | **SUPPORTED** |

### UCP (live pages) & secondary

| # | Report loc | Quote / claim | Source | Verdict |
|---|---|---|---|---|
| 30 | S1 L110; U-1 | example item carries `"price": 26550`; "**Merchant of Record**" | `ucp.dev` `"price": 26550`; blog "you own your business logic, and you remain the **Merchant of Record**" | **OK** |
| 31 | credit L354; U-1 | capabilities: "Catalog Search and Lookup, Cart Building, Identity Linking, Checkout, and Order Management" | `ucp.dev` verbatim | **OK** |
| 32 | S3 L205; U-1 | UCP composes AP2 for payment | `ucp.dev` "secure payment (AP2) via payment mandates and verifiable credentials" | **OK** |
| 33 | S1 L128; U-2 | UCP manifest at "`/.well-known/ucp`" | blog "…standard JSON manifest located at `/.well-known/ucp`" | **OK** |
| 34 | S1 L111; U-2 | Discounts are "**merchant-defined codes … not agent-negotiated rates**" | Google UCP blog | **UNSUPPORTED — founder-blocking (body quote).** Phrase not present; blog only shows a discount-code example. `sources.md` labels U-2 `[paraphrase]`. See §2. |
| 35 | fairness L126; U-2 | "UCP markets '**capability negotiation**'" | Google UCP blog | **MISMATCH.** Blog uses "**capability discovery**" / "discover business capabilities"; "negotiation" not present. `capability_negotiation` is verbatim for **ACP** (#28), not UCP. See §2. |
| 36 | (sources U-2 only) | Merchant has "**full control over pricing**" | Google UCP blog | **UNSUPPORTED.** Not present (blog: "you own your business logic"). `sources.md`-only `[paraphrase]`; not in report body. |
| 37 | (sources A-2 only) | "**The** Merchant MUST provide a merchant-signed JWT…" | `specification.md` L126 reads "**The The** Merchant MUST provide…" | **MINOR.** Source has a doubled-word typo; `sources.md` silently normalised it. Recommend `[sic]`. `sources.md`-only. |
| 38 | credit L61; C-6 | Stripe issues a "**Shared Payment Token**" | Stripe newsroom: "Stripe issues a Shared Payment Token (SPT)" | **OK** |
| 39 | not-found #4; X-1…X-3 | ChatGPT Instant Checkout wind-down "~2026-03-05, reported low conversion" | searchengineland (Mar 6 2026) + corroborating outlets | **SUPPORTED** as attributed secondary context. See flag 6. |
| 40 | C-5 (paraphrase) | Stripe docs building blocks / post-purchase webhooks | `docs.stripe.com/agentic-commerce/acp` | **NOT RE-FETCHED** (secondary, `[paraphrase]`, low stakes; report does not quote it in body) |

**Counts:** 40 inventory items · **OK 20 · SUPPORTED 9 · MINOR 2 · OVERSTATED 2 ·
MISMATCH 4 · UNSUPPORTED 3 · not-checked 1.** One MISMATCH corrected in place
(#11). Six items are founder-blocking (see §2): #5/#6 (one root, two cells + S3
row), #7, #16/#17 (one root), #34, #35.

---

## 2. MISMATCH / OVERSTATED / UNSUPPORTED — the diffs

### A. [FOUNDER-BLOCKING · S1 keystone] ACP request body **does** admit `unit_amount`; `Item` has **no** `quantity` (#16/#17)

> **Report L111 (ACP "Price — agent counter?"):** "**None.** No request body
> (`create`/`update`/`complete`) admits `unit_amount`/`total`. Agent input caps
> at `line_items{id,quantity}`, `buyer`, `fulfillment_*`, `discounts{codes}`."

Primary — `openapi.agentic_checkout.yaml` `Item` schema (referenced by
`line_items` in **both** the create request L2975 and the update request L3033):

```
Item:
  properties:
    id:          {type: string}
    name:        {type: string}
    unit_amount: {type: integer, description: "Price per unit in minor currency units …"}
  required: [id]
```

- **`unit_amount` (a price field) IS present on the agent-writable request
  `Item`.** The claim "No request body admits `unit_amount`" is **false at the
  schema level.** (`total` is correctly response-only — `Total.type`.)
- **`Item` has no `quantity` property** (only `id`, `name`, `unit_amount`;
  `required: [id]`). The report's "`line_items{id,quantity}`" and the S1
  "Quantity: `line_items[].quantity` (min 1)" describe the **response**
  `LineItem` (L1270-1272), not the request `Item`. (The create-request *example*
  L3020-3024 shows `{product_id, quantity}` — fields that don't exist on `Item`;
  the spec's own example drifts from its schema.)

**Why it matters:** this is the S1 keystone and the exec-summary line "no field
to propose a price." A spec engineer contesting the mapping (which the fairness
protocol invites) points straight at `Item.unit_amount`. The report's *economic*
finding can still be argued — the authoritative price is the merchant-computed
`totals` (`Total.type: total`), and there is no field for the merchant to
*accept* an agent-proposed unit price — but the **absolute schema statement as
written is contradicted by the schema.** Per the corrections policy this
undermines a stated claim, so it is **flagged, not rewritten.** Founder must
re-word before any external use.

### B. [FOUNDER-BLOCKING] AP2 `checkout_jwt` field enumeration is not in AP2 (#5/#6, and S3 L173 "Covers")

> **Report L110:** Merchant signs `checkout_jwt` containing "line items with …
> prices, quantities, total price, currency."
> **Report L114:** `checkout_jwt` includes "shipping and return policies".
> **Report S3 L173 ("Covers"):** "merchant identity, line items+prices,
> quantities, total, currency, shipping/return policy".

Primary — `checkout_mandate.md` L30-33:

> "`checkout_jwt` is the merchant-signed JWT containing the details of the
> checkout. **The details of the payload are outside the scope of this
> specification**, when used with the [Universal Commerce Protocol](https://ucp.dev)
> this MUST be the Checkout object."

The enumerated fields ("merchant identity / line items with product IDs, titles,
prices / quantities / total price / currency / shipping and return policies")
appear **nowhere** in any AP2 doc (grep of all five files: 0 hits for "line items
with", "quantities, total", "shipping and return", "return policies", "total
price", "merchant identity"). AP2 explicitly **defers** the payload to the UCP
`Checkout` object. The enumeration is real *for UCP* (`ucp.dev` item carries
`price`/`title`) but is **misattributed to AP2** and dressed as a verbatim quote.
Underlying claim ("merchant sets the price") stands via ACP `totals` + UCP; the
**quote/attribution** does not. Flagged, not rewritten (the accurate AP2 quote —
"payload … outside the scope of this specification" — would change what the cell
asserts AP2 contains).

### C. [FOUNDER-BLOCKING] "unidirectional flow from open to closed" is a paraphrase, not a quote (#7)

> **Report L111:** … "unidirectional flow from open to closed."

Not present in `checkout_mandate.md` or any AP2 doc (0 hits for "unidirectional"
/ "open to closed"). `sources.md` A-3 already tags it `[paraphrase]`. The
structural claim (open→closed, no counteroffer) is schema-supported (open mandate
carries `constraints`; closed mandate is `checkout_hash`-bound; no reverse
message), but the **quotation marks assert source text that does not exist.**
Fix = drop the quotation marks (make it the audit's own characterisation) or cite
the actual mechanism; left to founder per policy.

### D. [FOUNDER-BLOCKING] UCP "merchant-defined codes … not agent-negotiated rates" not in source (#34)

> **Report L111 (UCP "Price — agent counter?"):** "**None.** Discounts are
> "merchant-defined codes … not agent-negotiated rates.""

The Google UCP blog does **not** contain this phrase (WebFetch: "does not
explicitly state discounts are merchant-defined or non-negotiable"; it shows a
discount-code example only). `sources.md` U-2 tags it `[paraphrase]`. Claim is
structurally true (ACP `DiscountsRequest.codes`; no agent-writable rate field),
but the **body prints a paraphrase as a verbatim quote.** Flagged.

### E. [FOUNDER-BLOCKING] "capability negotiation" is ACP's RFC name, not UCP marketing (#35)

> **Report L126:** "ACP's RFC list contains `capability_negotiation` and UCP
> markets "capability negotiation" (C-1, U-2)."

- ACP half: **verbatim-correct** — `rfcs/rfc.capability_negotiation.md` exists.
- UCP half: **wrong** — the Google UCP blog uses "**capability discovery**" /
  "discover business capabilities"; "negotiation" is not on the page. UCP does
  not "market 'capability negotiation'."

The report's point (the word denotes feature discovery, not price bargaining)
actually *strengthens* under the correct wording, but the **UCP attribution of
the quoted word "negotiation" is unsupported.** Flagged.

### F. [CORRECTED] "may be shared with the merchant" was a spliced quote (#11)

> **Was (report L147):** Checkout Mandate "may be shared with the merchant" as
> dispute evidence.
> **Now:** Checkout Mandate is "shared with the Merchant so they can use this as
> evidence in case of disputes" — dispute evidence.

Primary — `overview.md` L210-214:

> "…create a cryptographically signed "Checkout Mandate". … **It is shared with
> the Merchant so they can use this as evidence in case of disputes.** Separately,
> the Payment Mandate **may be shared** with the network & issuer for transaction
> authorization."

The old quote spliced "**may be shared**" (which the source applies to the
**Payment** Mandate → **network & issuer**) onto "**the merchant**" (which the
source applies to the **Checkout** Mandate, and as a definite "**is** shared,"
not "may be"). Corrected to the verbatim source phrase; the finding (Checkout
Mandate = evidentiary, not a settlement mechanism) is unchanged and, if anything,
strengthened ("is" > "may be"). Pinned to AP2 `main`@`e1ea56d`.

### Minor / cosmetic (recorded, not blocking)

- **#4** ellipsis convention `…` vs source parenthetical — legitimate elision.
- **#9, #14** flows quotes truncated at a clause boundary with a terminal `.` — words exact.
- **#20** `{id}` shorthand for `{checkout_session_id}`.
- **#23** `Adjustment.type` string-not-enum + 2 undocumented values (`price_adjustment`, `cancellation`) — claim holds; set incomplete.
- **#24** `OrderLineItem.status` string-not-enum; four values exact.
- **#37** `sources.md` A-2 normalised a "The The" doubled-word typo in the source — recommend `[sic]`.
- **#36** `sources.md` U-2 "full control over pricing" not on the fetched blog (sources-only paraphrase).

---

## 3. Founder-verification flags — resolutions

### Flag 1 — AP2 mandate count / naming / format → **CONFIRMED-AS-WRITTEN**

Primary evidence (`specification.md` @ `e1ea56d`):

- **L107: "Mandate types: Checkout Mandate and Payment Mandate."** — exactly
  **two** mandate types.
- **Format = SD-JWT:** "SD-JWT" appears **18×** across the docs; claim types are
  `mandate.checkout.1` / `mandate.checkout.open.1` / `mandate.payment.1` /
  `mandate.payment.open.1` (two types × open/closed states).
- **No "W3C" and no "Verifiable Credential" string anywhere** in the five AP2
  docs; **no "Intent Mandate" / "Cart Mandate" / "three mandates."** The task
  brief / prior memory ("three Mandates: Intent/Cart/Payment as W3C Verifiable
  Credentials") is **not supported by the current spec** — the "Intent" role
  survives as the *open* Checkout mandate, exactly as the report states.
- **Version:** spec body self-labels "**v0.2**" (L1); no semver "v0.2.0" and no
  ISO date on the fetched pages — matches the report's hedge.
- **One nuance to hand the founder:** AP2's own **landing page**
  (`ap2-protocol.org`) still frames trust via "**verifiable digital credentials
  (VDCs)**" and confirms "**two primary types of mandates, each existing in two
  stages**." So the VC-vs-SD-JWT tension is real at the *marketing-vs-spec* seam
  (wire format = SD-JWT; marketing = "verifiable digital credentials"), which is
  exactly why flagging — not silently reconciling — was correct.

The report's flag-1 text and its 2-mandate / SD-JWT / open-closed mapping are
**correct against primary source.** Recommend adding the `main`@`e1ea56d` pin
(done in the top table).

### Flag 2 — human-not-present consent sufficiency → **mechanism CONFIRMED; adequacy UNRESOLVABLE-FROM-PUBLIC-SOURCES**

`flows.md` L146-147 confirms the mechanism: "The Shopping Agent constructs the
Payment and Checkout Mandate Contents and **signs both closed Mandates using the
`agent_sk`**," with trust supplied by user-signed **open** mandates
(`specification.md` L186-187: "the closed Mandates are signed by an Agent key.
Trust in this key is provided by open Mandates that are signed by the User…").
Whether the open constraints **constitute sufficient consent** for the
agent-signed closed transaction is a normative/intent question the spec does not
pronounce on. The report correctly describes the mechanism and declines to judge
adequacy — **no correction needed.**

### Flag 3 — ACP capture-vs-authorization timing → **CONFIRMED-AS-WRITTEN**

`openapi.delegate_payment.yaml` defines an **allowance** — `max_amount` (a cap,
`reason: one_time`), bound to `checkout_session_id`, "for controlled usage by the
merchant's PSP." `…/complete` creates the `Order`. Nothing in either OpenAPI
pins **capture** timing (immediate vs at-fulfillment) — it is PSP/merchant
policy, exactly as the report states. S5b's authorization-before-delivery
ordering matches the flow. The report's reading is correct; the residual (real
deployment capture semantics) is genuinely outside the public spec.

### Flag 4 — verbatim-quote pass → **NEEDS-CORRECTION** (this document)

**Schema facts largely verify** (endpoints, `totals`/`Total.type`,
`CheckoutSession.status`, `Order` fields, message codes, `DiscountsRequest.codes`,
`Allowance`, all AP2 `vct`/SD-JWT facts, AP2 scope + roles + "will fulfill" +
Payment-Receipt quotes) — **except** the ACP request-`Item` conflation (§2.A),
which is a `[schema]`-tagged certainty that is wrong.

**Prose quotes are the weak layer**, as the flag anticipated. Not verbatim:
§2.B (AP2 `checkout_jwt` enumeration), §2.C ("unidirectional flow…"), §2.D (UCP
"merchant-defined codes…"), §2.E (UCP "capability negotiation"). One prose
splice corrected (§2.F). Net: **five founder-blocking items** remain (§2.A–E).

### Flag 5 — UCP depth → **CONFIRMED-AS-WRITTEN**

UCP is genuinely mapped at stack level; no machine-readable UCP checkout schema
was fetched (none surfaced from `ucp.dev`/vendor docs in this pass). The UCP
*quotes that the report does use* verify against `ucp.dev` (capabilities list,
`"price": 26550`, "secure payment (AP2)…") and the Google blog (`/.well-known/ucp`,
"Merchant of Record") — **except** §2.D and §2.E. If UCP is promoted to a
first-class subject, its checkout capability schema must be fetched and mapped
directly (as the flag says).

### Flag 6 — Instant-Checkout data-point provenance → **CONFIRMED-AS-WRITTEN**

The ~2026-03-05 pullback is well-corroborated but **secondary**: searchengineland
(Mar 6 2026) is secondhand and cites *The Information* (paywalled); Forbes,
Forrester, Modern Retail concur on the low-conversion reason (Walmart EVP: in-chat
converted at ~⅓ the rate of sending shoppers to walmart.com; ~30 Shopify
merchants live by Feb 2026). An OpenAI **spokesperson** confirmed the strategy
shift ("evolving our commerce strategy … to better meet merchants and users where
they are"), but **no primary OpenAI post states the conversion rationale.** The
report's handling — clearly-attributed context, "reported as reported," no causal
link asserted to the S1 gap — is accurate. Keep as attributed context (or source
the spokesperson line as the nearest primary).

---

## 4. Publish-readiness

- **Inventory checked:** 40 items (20 OK · 9 SUPPORTED · 2 MINOR · 2 OVERSTATED ·
  4 MISMATCH · 3 UNSUPPORTED · 1 not-checked secondary).
- **Corrected in `report.md` (this pass):** 1 quote (§2.F, spliced
  "may be shared") + 2 version/commit pins (AP2 `e1ea56d`, ACP `c2afc86`/amended
  2026-05-01) + 1 pin reference. All within the "quote text / URL / version /
  section" corrections envelope; **no finding, magnitude, or tone changed.**
- **Founder-blocking, unresolved (must fix before any external publication):** **5**
  1. **§2.A** — ACP request `Item` **has** `unit_amount` and **no** `quantity`;
     the S1-keystone statement "no request body admits `unit_amount`" is false as
     written. *(highest severity — this is the sentence a spec engineer refutes
     first.)*
  2. **§2.B** — AP2 `checkout_jwt` field enumeration (L110/L114 + S3 L173) is not
     in AP2 (payload is "outside the scope of this specification"); it is UCP's
     Checkout object, misattributed and quoted.
  3. **§2.C** — "unidirectional flow from open to closed" is a paraphrase in
     quotation marks.
  4. **§2.D** — UCP "merchant-defined codes … not agent-negotiated rates" is a
     paraphrase in quotation marks (not on the source page).
  5. **§2.E** — "capability negotiation" is ACP's RFC filename, not UCP marketing
     (UCP says "capability discovery").
- **Flags resolved:** **6/6** — flags 1, 3, 5, 6 CONFIRMED-AS-WRITTEN; flag 2
  mechanism-confirmed / adequacy-unresolvable; flag 4 NEEDS-CORRECTION (the five
  items above).

**Read:** the report's *structural spine is sound and its magnitudes are
untouched*, but it is **NOT publish-ready as-is.** The prose-quote layer (§2.B–E)
and — most importantly — the S1 schema keystone (§2.A) carry claims that the
primary sources contradict on their face. Because the fairness protocol
**invites** the specs' own engineers to contest the mapping, each of these five
is a live rebuttal that would invert the asset. They are quote/schema-attribution
defects, not thesis defects — the no-binding-counteroffer economics survive — but
they must be corrected by a human (per the strict corrections policy) before this
leaves founder review.

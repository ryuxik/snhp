# SPECAUDIT — sources

*DRAFT-FOR-COMMENT. Every mapping claim in `report.md` traces to a row here.
Access date for all fetches: **2026-07-16** (via WebFetch/WebSearch). Where a
quote is a short verbatim string it is in "quotation marks"; where a row records
a **schema-level structural fact** (a field name, enum value, or endpoint that
the machine-readable spec defines) it is labelled `[schema]` — those are read
directly off the OpenAPI/JSON-Schema/SD-JWT claim names and are stated with
certainty per the fairness protocol. Paraphrases produced by the fetch
summariser (not verbatim spec prose) are labelled `[paraphrase — verify verbatim
before external publication]`.*

---

## AP2 — Agent Payments Protocol (Google-led)

Self-identified version in the spec body: **"Agentic Payment Protocol (v0.2)"**
(`docs/ap2/specification.md`). No explicit ISO date string was found on the
pages fetched. **FLAG:** the task brief and prior memory describe AP2 as
"v0.2.0, April 2026, three Mandates: Intent/Cart/Payment as W3C Verifiable
Credentials." The **current** `main`-branch spec I fetched describes **two**
mandate types (Checkout Mandate + Payment Mandate) expressed as **SD-JWTs**, with
`open`/`closed` states — not three W3C VCs. The "Intent" role survives as the
`open` Checkout/Payment mandate. This naming/format discrepancy is carried into
the report as an explicit founder-verification item, not silently reconciled.

| # | URL | What it establishes | Key quote / `[schema]` fact |
|---|-----|--------------------|------------------------------|
| A-1 | https://ap2-protocol.org/ | Landing; nav to Specification, Flows, Mandates, Security/Privacy, Implementation, Glossary, FAQ. References "AP2 v0.2 Release." | "AP2 v0.2 Release" `[paraphrase]` |
| A-2 | https://raw.githubusercontent.com/google-agentic-commerce/AP2/main/docs/ap2/specification.md | Two mandates; scope boundary; binding-by-hash. | "The Checkout Mandate is designed to provide the Merchant cryptographic proof that the Shopping Agent is authorized to purchase the Checkout that it has assembled." · "The Merchant MUST provide a merchant-signed JWT containing the Checkout to the Shopping Agent. The closed Checkout Mandate is bound to this Checkout JWT using a cryptographic hash." · "The exact details of the Commerce Protocol ... are outside the scope of AP2." · `[schema]` claim `checkout_hash`; `vct` = `mandate.checkout.1` / `mandate.checkout.open.1`, `mandate.payment.1` |
| A-3 | https://raw.githubusercontent.com/google-agentic-commerce/AP2/main/docs/ap2/checkout_mandate.md | Checkout (Cart) Mandate fields; merchant signs cart; immutability. | `[schema]` fields: `vct`, `checkout_hash` ("base64url-encoded hash of the value of `checkout_jwt`"), `checkout_jwt` ("merchant-signed JWT containing the details of the checkout"), `constraints` (open only: allowed merchants, line items), `cnf`, `iat`, `exp`. The `checkout_jwt` "includes order details: merchant identity, line items with product IDs/titles/prices, quantities, total price, currency, shipping and return policies." "The document contains no negotiation or counteroffer language. It describes a unidirectional flow from open to closed mandate." `[paraphrase for the last sentence]` |
| A-4 | https://raw.githubusercontent.com/google-agentic-commerce/AP2/main/docs/ap2/payment_mandate.md | Payment Mandate = SD-JWT; open mandates can carry an `amount_range`. | `[schema]` fields: `vct` (`mandate.payment.1` / `mandate.payment.open.1`), `transaction_id`, `payee`, `payment_amount`, `payment_instrument`, `constraints`, `cnf`, `iat`, `exp`. "an `amount_range` constraint allows amounts 'within the range defined by `min` and `max`'." "Closed mandates reference a specific transaction with a concrete `payment_amount`." `[paraphrase]` |
| A-5 | https://raw.githubusercontent.com/google-agentic-commerce/AP2/main/docs/ap2/flows.md | Human-present vs human-not-present signing; MPP-signed Payment Receipt. | "The Trusted Surface uses `user_sk` to sign and create the Payment Mandate and Checkout Mandate" (human present). "The Shopping Agent constructs the Payment and Checkout Mandate Contents and signs both closed Mandates using the `agent_sk`" (human NOT present). "The Merchant verifies the integrity and content of the closed Checkout Mandate against the current cart state." "The MPP-signed Payment Receipt is returned to the Shopping Agent, Credential Provider, and Network." |
| A-6 | https://raw.githubusercontent.com/google-agentic-commerce/AP2/main/docs/overview.md | Six roles; open/closed mandate mechanics; dispute-evidence sharing. | Roles: Shopping Agent (SA), Credential Provider (CP), Merchant (M), Merchant Payment Processor (MPP), Trusted Surface (TS), Network and Issuer. "Merchant must sign the Cart that they create for a user, signaling that they will fulfill this cart." Checkout Mandate "may be shared with the merchant" for dispute evidence. `[paraphrase]` |

---

## ACP — Agentic Commerce Protocol (OpenAI + Stripe, with Meta)

Version (date-based): **2026-04-17** (`spec/2026-04-17/…`). Apache-2.0. Maintained
by OpenAI and Stripe.

| # | URL | What it establishes | Key quote / `[schema]` fact |
|---|-----|--------------------|------------------------------|
| C-1 | https://github.com/agentic-commerce-protocol/agentic-commerce-protocol | Repo layout, version, RFC list. | Spec snapshot `2026-04-17`; OpenAPI files `openapi.agentic_checkout.yaml`, `openapi.delegate_payment.yaml`; JSON-Schema + OpenRPC dirs; RFCs incl. "capability_negotiation", "discount_extension." `[schema/paraphrase]` |
| C-2 | https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/spec/2026-04-17/openapi/openapi.agentic_checkout.yaml | Checkout session endpoints + full field surface. **The S1 keystone.** | `[schema]` Endpoints: `POST /checkout_sessions`, `GET /checkout_sessions/{id}`, `POST /checkout_sessions/{id}`, `POST /checkout_sessions/{id}/complete`, `POST /checkout_sessions/{id}/cancel`. Agent-writable create body = `{buyer, line_items(Item: id,name,unit_amount), currency, fulfillment_details, affiliate_attribution, discounts}`; update body = `{line_items, fulfillment_details, selected_fulfillment_options, buyer, discounts}`. `totals` is a **merchant-computed response array** (`items_base_amount, items_discount, subtotal, discount, fulfillment, tax, fee, gift_wrap, tip, store_credit, total, amount_refunded`). No agent-writable price/unit_amount field on any request body. `quote_id`, `quote_expires_at` present. |
| C-3 | (same file C-2, second pass) | Order object, status enum, fulfillment/adjustment surface. **Credit-due for S2/S3.** | `[schema]` `CheckoutSession.status` enum: `incomplete, not_ready_for_payment, requires_escalation, authentication_required, ready_for_payment, pending_approval, complete_in_progress, completed, canceled, in_progress, expired`. `Order` fields: `id, checkout_session_id, order_number, permalink_url, status, estimated_delivery, confirmation, support, line_items, fulfillments, adjustments, totals`. `Adjustment.type` enum incl. `refund, credit, return, exchange, dispute`. `OrderLineItem.status`: `processing, partial, fulfilled, removed`. `Message` types `MessageInfo/MessageWarning/MessageError` with `code` incl. `out_of_stock, payment_declined`. |
| C-4 | https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/spec/2026-04-17/openapi/openapi.delegate_payment.yaml | Delegated payment token = capped allowance. **S2/S4.** | `[schema]` `POST /agentic_commerce/delegate_payment` "Tokenizes a credential for controlled usage by the merchant's PSP per the Allowance constraints." `allowance`: `reason` (only `one_time`), `max_amount` (minor units, **fixed at creation**), `currency`, `merchant_id`, `expires_at`, `checkout_session_id`. Response token id `vt_…`. |
| C-5 | https://docs.stripe.com/agentic-commerce/acp | Five building blocks; post-purchase webhooks exist. | "agentic checkout … cart management, fulfillment options, and payment processing"; "Orders and webhooks: … order confirmation, shipping, delivery, and refunds." `[paraphrase]` |
| C-6 | https://stripe.com/newsroom/news/stripe-openai-instant-checkout | Launch context; Shared Payment Token naming. | Instant Checkout in ChatGPT; ACP co-developed by Stripe + OpenAI; Stripe issues a "Shared Payment Token." `[paraphrase]` |

---

## ACP commercial-outcome context (cited as fact, NOT a mechanism claim)

| # | URL | What it establishes |
|---|-----|--------------------|
| X-1 | https://searchengineland.com/chatgpt-instant-checkout-plan-change-471033 | OpenAI changed the ChatGPT Instant Checkout plan (early March 2026). `[paraphrase]` |
| X-2 | https://awesomeagents.ai/news/openai-chatgpt-checkout-abandoned/ | Reported near-zero sales / low conversion as the reason in-chat checkout was pulled back. `[paraphrase]` |
| X-3 | https://webinterpret.com/en/blog/openai-abandons-instant-checkout | "Discover in AI, buy on site"; purchases redirect to retailer sites; ACP development continues toward app-based transactions. `[paraphrase]` |

*Read strictly as: a commercial pilot outcome (~March 5 2026, low conversion),
NOT evidence about the protocol's mechanism design. Multiple secondary outlets;
no single primary OpenAI post was located — reported as reported.*

---

## UCP — Universal Commerce Protocol (Google + Shopify)

Announced NRF 2026 (Jan 11 2026). Apache-2.0 ("Copyright 2026 UCP Authors").
Included at stack level only.

| # | URL | What it establishes | Key quote / fact |
|---|-----|--------------------|-------------------|
| U-1 | https://ucp.dev/ | Capabilities; fixed merchant pricing; AP2 compatibility. | Capabilities: "Catalog Search and Lookup, Cart Building, Identity Linking, Checkout, and Order Management." Example item carries pre-set `"price": 26550`. "secure payment (AP2) via payment mandates and verifiable credentials." `[paraphrase/schema]` |
| U-2 | https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/ | "Capability negotiation" = capability **discovery**, not price bargaining. | "Businesses publish the services they support and corresponding capabilities in a standard JSON manifest located at `/.well-known/ucp`." Merchant is "the Merchant of Record" with "full control over pricing." Discounts are "merchant-defined codes … not agent-negotiated rates." `[paraphrase]` |

**Fairness note carried to report:** the word "negotiate/negotiation" appears in
UCP/ACP marketing and RFC titles ("capability negotiation"). Verified against the
primary text it denotes **protocol/feature capability discovery and handshake**
(the `/.well-known/ucp` manifest; ACP's `capabilities` field), **not** negotiation
of commercial terms (price/quantity/timing/conditions). The report states this
explicitly so the distinction is not read as a gotcha.

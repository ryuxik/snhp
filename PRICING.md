# Pricing

SNHP offers one product: negotiation rules a seller's AI can't break — your offer becomes rules, and every reply to a
buyer (or a buyer's AI agent) is drafted inside them, with a signed receipt for each deal.

| What | Price |
|---|---|
| Templates, policy checks, receipt verification (`/v1/policy/templates`, `/v1/policy/check`, `/v1/receipt/verify`; MCP `check_offer_policy`, `verify_deal_receipt`) | **Free**, no key. |
| Drafting replies and building rules from a description (`/v1/reply`, `/v1/policy/compile`, `/v1/practice/buyer`; MCP `draft_negotiation_reply`, `compile_offer_policy`) | **Access key**, issued to pilot businesses. These calls run a language model; each key has a daily cap. |
| Pilot: your rules set up with you, replies drafted for your live buyer messages for two weeks | **Free** for the pilot. |
| After the pilot | A flat monthly fee per business, set with the first pilot businesses against what the pilot measured. No percentage of deal value. |

Request a pilot at https://snhp.dev/#pilot or email hello@snhp.dev.

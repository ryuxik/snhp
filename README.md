# SNHP — negotiation rules your AI can't break

Describe your offer in plain words. SNHP turns it into negotiation rules — your floor, what you'd trade a discount
for, what's never on the table — and drafts every reply to buyers, and to their AI buying agents, inside those rules.
The SNHP engine decides each offer, a small language model only reads and writes, and every offer is checked in code
before it leaves. A deal needs the buyer's yes to an offer you sent, and comes with a signed receipt.

This package is the MCP server (stdio) for the hosted service at [snhp.dev](https://snhp.dev):

```bash
uvx snhp            # or: pip install snhp && snhp
```

```json
{ "mcpServers": { "snhp": { "command": "uvx", "args": ["snhp"], "env": { "SNHP_ACCESS_KEY": "snhp_…" } } } }
```

Or connect to the hosted MCP endpoint directly: `https://snhp.dev/mcp/` (streamable HTTP).

| Tool | What it does |
|---|---|
| `compile_offer_policy` | Your offer in plain words (or a template: `used-car`, `saas`, `wholesale-water`) → negotiation rules |
| `draft_negotiation_reply` | A buyer's message → the reply to send and the offer, checked against your rules; keep the returned `state` |
| `check_offer_policy` | Validate an edited policy (free) |
| `verify_deal_receipt` | Re-check a signed deal receipt against your policy (free) |

**Access.** Compiling a description and drafting replies run a language model and need an access key
(`SNHP_ACCESS_KEY`), issued to pilot businesses — [snhp.dev/#pilot](https://snhp.dev/#pilot) or hello@snhp.dev.
Templates, checks and receipt verification are free.

**Privacy.** The service stores no conversations; the state travels with each request. Messages go to our model
provider only to read them and draft the reply.

Web studio: [snhp.dev/studio](https://snhp.dev/studio) · API: [snhp.dev/developers](https://snhp.dev/developers)

## This repository

The `snhp` package on PyPI is built from [`packages/snhp-client`](packages/snhp-client). SNHP's earlier research code is
preserved, unmaintained, on the [`legacy-toolkit`](https://github.com/ryuxik/snhp/tree/legacy-toolkit) branch.

# Go-live: deploy + make SNHP discoverable to agents

The code is deploy-ready. These steps need YOUR accounts/secrets (Fly token,
registry logins), so they're a runbook, not something the agent can do for you.
Discovery requires a live, public endpoint — do the deploy first; nothing is
discoverable until the agent card resolves at a real URL.

## 1. Deploy the server (Fly — see DEPLOY.md for the full version)

LIVE STATE (2026-06-26): the `snhp` app is already deployed at https://snhp.dev
(custom domain cert issued; `snhp.fly.dev` too), with `snhp-db` Postgres and the
required secrets set (FIRST_STRIKE_PRIVATE_PEM, DATABASE_URL, ANTHROPIC_API_KEY,
TELEMETRY_PEPPER, SNHP_STATS_KEY). It auto-stops when idle (zero cost) and
cold-starts on first request.

```bash
# Redeploy current code (the usual case now):
fly deploy --app snhp

# (Optional) expose the LLM dispute endpoints — OFF by default:
#   fly secrets set SNHP_ENABLE_DISPUTE_LLM=1 --app snhp   # then a $5/day cap + per-IP limit apply
```

Fresh fork from scratch? `fly apps create snhp`; generate the trust-anchor key
YOURSELF (it is your root of trust — keep a backup) and
`fly secrets set FIRST_STRIKE_PRIVATE_PEM="$(cat snhp-anchor.pem)"`; optionally
`fly secrets set SNHP_PUBLIC_BASE_URL=https://snhp.fly.dev` (no custom DNS needed);
then `fly deploy`.

## 2. Verify it's live, usable, and the card is correct

```bash
# (a) The FLAGSHIP works end-to-end (this is what agents actually call):
curl -s https://snhp.dev/v1/negotiate/turn -H 'content-type: application/json' \
  -d '{"side":"sell","walk_away":4000,"target":6000,"counterparty_offers":[4200,4500],"rounds_left":6}'
# Expect: {"action":"counter","recommended_price":~5387,"message":"...$5,387...","fit":{"score":"good"},...}

# (b) The card is discovery-correct:
curl -s https://snhp.dev/.well-known/agent-card.json | python3 -m json.tool
# Expect: name "Negotiation Copilot for Agents (SNHP)", url=https://snhp.dev,
#         the negotiate_turn skill listed first, absolute endpoint params,
#         and a STABLE trust_anchor_public_key_pem.

# (c) The agent onboarding guide leads with the dollar quickstart:
curl -s https://snhp.dev/llms.txt | head -25
curl -s https://snhp.dev/v1/catalog | python3 -m json.tool | head -30   # gt.negotiate.turn is first

curl -s https://snhp.dev/health   # first_strike_key_source must be "env", not "ephemeral"
```

## 3. List in the agent-discovery channels

Two surfaces, because SNHP is both an A2A agent and an MCP server:

- **A2A Protocol Agent Registry** — https://a2aregistry.org
  Submit `discovery/a2a_registry_entry.json` (it points the registry at the live
  agent card). Also worth: open a PR to the A2A `extensions` ecosystem listing the
  `https://snhp.dev/a2a/negotiation/v1` extension.
- **OpenClaw / MCP skill registries** — ClawHub, Awesome OpenClaw Skills,
  AI Agent Store, and the official MCP registry.
  Use `discovery/mcp_skill_manifest.json` as the source content. Confirm each
  registry's exact schema/submission flow before publishing (they differ).
- **Agentic Resource Discovery (ARD)** — the cross-vendor catalog (Google/MS/
  Cisco/HF/…). Once the agent card + MCP are live and listed above, they become
  ARD-indexable; register when ARD opens public submission.

## 4. Reality check (don't mistake listed for adopted)

Listing makes you *findable*, not *used*. The directories are early and there's a
cold-start: agents only call a negotiation service when they have a negotiation.
Run discovery in parallel with the design-partner conversation — the live agent
card + a recorded two-agent verified-negotiation trace is the artifact that makes
that pitch land. Discovery is cheap plumbing; the conversation is the real test.

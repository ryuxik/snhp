# Deploy run-book — api.snhp.dev on Fly.io

Step-by-step for getting the SNHP HTTP server live behind a custom domain.
You run the commands; this file is the script.

## 0. Prerequisites

- Fly CLI installed: `brew install flyctl` (macOS) — already on your box.
- Domain registered: snhp.dev (done).
- Local repo: `~/Desktop/snhp/` with this `Dockerfile` and `fly.toml`.

## 1. Authenticate Fly

```bash
fly auth login        # account: ryuxik@gmail.com
fly auth whoami       # verify
```

## 2. Create the app + Postgres

```bash
cd ~/Desktop/snhp
fly launch --no-deploy --copy-config
# When prompted:
#   - app name: snhp  (matches the [app] line in fly.toml)
#   - region: sjc     (San Jose; pick closest to you)
#   - skip Postgres / Redis prompts; we provision separately below
#   - skip deploy (we'll do it manually)
```

Provision Postgres (small shared VM, 1GB volume):

```bash
fly postgres create --name snhp-db --region sjc --vm-size shared-cpu-1x --volume-size 1
fly postgres attach snhp-db --app snhp
# `attach` writes DATABASE_URL into the app's secrets — _db.py picks it up automatically.
```

## 3. Set required secrets

```bash
# Persistent first-strike Ed25519 key (recommended for production —
# without this, every restart issues a fresh trust anchor and historical
# JWTs become unverifiable).
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
k = Ed25519PrivateKey.generate()
print(k.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode())
" > /tmp/snhp-trust-anchor.pem
fly secrets set FIRST_STRIKE_PRIVATE_PEM="$(cat /tmp/snhp-trust-anchor.pem)" --app snhp
rm /tmp/snhp-trust-anchor.pem  # delete local copy after setting

# After deploy, verify the env var is being honored:
#   curl https://snhp.fly.dev/health
#   {"status":"ok", "version":"0.1.0", "first_strike_key_source":"env"}
# If you see "ephemeral", the secret didn't land — re-check fly secrets.
```

## 4. Deploy

```bash
fly deploy --app snhp
# Watch logs:
fly logs --app snhp
# Verify health:
curl https://snhp.fly.dev/health
# Catalog:
curl https://snhp.fly.dev/v1/catalog | jq .
```

## 5. Wire up the custom domain

```bash
# Get Fly's IPv4 + IPv6:
fly ips list --app snhp

# At your DNS provider for snhp.dev (Cloudflare / wherever):
#   A    api    <fly-ipv4>
#   AAAA api    <fly-ipv6>
# Then issue the cert:
fly certs add api.snhp.dev --app snhp
fly certs check api.snhp.dev --app snhp
# Verify once cert is issued:
curl https://api.snhp.dev/health
```

For the docs site (later) you'd repeat with a separate Fly app or point
`docs.snhp.dev` at GitHub Pages / Vercel / wherever.

## 6. Smoke test from a fresh shell

```bash
# Create a free key:
curl -X POST https://api.snhp.dev/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"smoke-test","contact_email":"you@example.com","intended_use_summary":"deploy smoke"}'

# Call a free endpoint:
curl -X POST https://api.snhp.dev/v1/auction/bidder/optimal_bid \
  -H "Content-Type: application/json" \
  -d '{
    "auction_format":"second_price_vickrey",
    "my_valuation":100,
    "n_competing_bidders":3,
    "competitor_value_prior":{"family":"uniform","params":{"low":0,"high":100}}
  }'
# Expect: {"optimal_bid":100.0,"dominant_strategy":true, ...}
```

## 7. Billing (deferred)

All endpoints are currently free. The Stripe Checkout credit-pack flow
lives in `gametheory/server/billing.py` (fully tested as a module) but
the HTTP routes are not registered. To re-wire when there's a paid
endpoint:
  1. `pip install stripe>=8.0` (and add to `pyproject.toml`'s `[prod]`
     extras)
  2. Re-register the three routes in `gametheory/server/http.py`
     (`/v1/billing/checkout_session`, `/v1/billing/webhook`,
     `/v1/billing/balance`) — the implementations in `billing.py` are
     ready
  3. Set `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` Fly secrets
  4. Add a Stripe webhook endpoint at
     `https://api.snhp.dev/v1/billing/webhook` listening for
     `checkout.session.completed`

## 9. What's NOT done by these steps
- **Redis rate limiting**: per-key rate limits are advertised in the
  catalog but not enforced. Single-replica deploy means this matters
  less for now; revisit when scaling out.
- **Auto-recharge**: low-balance customers must manually re-purchase via
  /v1/billing/checkout_session. Modal/Replicate offer auto-recharge
  ("when balance < $X, top up $Y") — defer until first customer asks.
- **Free tier on signup**: no $5–$10 starting credits. Defer until
  conversion friction matters.
- **Logging / Sentry**: nothing configured. Stage 5.
- **MCP server hosting**: the stdio MCP runs on the user's machine
  (`pip install gametheory-mcp; gametheory-mcp`); a hosted SSE/HTTP MCP
  is a separate decision once usage demands it.

## 10. Rollback

```bash
fly releases list --app snhp
fly releases rollback <version> --app snhp
```

## 11. Useful operations

```bash
fly status --app snhp                # current machine state
fly ssh console --app snhp           # shell into a running VM
fly scale count 2 --app snhp         # run two machines (HA)
fly scale memory 1024 --app snhp     # bump RAM if numba JIT chokes
```

## 12. Public dispute tool — `disputes.snhp.dev` subdomain

The mobile-first dispute tool is `gametheory/server/static/app.html`. It's
already routed two ways:
- directly at **`/app.html`** on any host, and
- at the **root `/`** when the request's `Host` is one of `SNHP_TOOL_HOSTS`
  (default `disputes.snhp.dev,try.snhp.dev`) — so a Twitter tap on the
  subdomain lands straight on the tool, not the marketing page.

### 12.1 Point the subdomain at the Fly app (one-time)

```bash
# 1. Tell Fly to issue a TLS cert for the subdomain:
fly certs add disputes.snhp.dev --app snhp
fly certs show disputes.snhp.dev --app snhp     # prints the exact DNS records to add

# 2. At the snhp.dev DNS registrar, add what `certs show` asks for — typically:
#      CNAME  disputes  ->  snhp.fly.dev
#    (plus the _acme-challenge CNAME Fly gives you for cert validation)

# 3. Wait for validation, then verify:
fly certs check disputes.snhp.dev --app snhp
curl -sI https://disputes.snhp.dev/ | head -5      # should 200 and serve app.html
```

No app redeploy is needed for the routing — `SNHP_TOOL_HOSTS` already
includes `disputes.snhp.dev`. To use a different subdomain, set it:
`fly secrets set SNHP_TOOL_HOSTS="refunds.snhp.dev" --app snhp`.

### 12.2 REQUIRED secret for the live co-pilot

The "try your real dispute" co-pilot calls Claude Haiku and needs an
Anthropic key in production (the demo/gasp path is $0 and needs nothing):

```bash
fly secrets set ANTHROPIC_API_KEY="sk-ant-..." --app snhp
```

Note: `fly.toml` sets `SNHP_LLM_MODEL=gemini/...` for a *different* code path;
the dispute co-pilot uses `claude-haiku-4-5` via `SNHP_CONSOLE_MODEL`
(default). Override with `fly secrets set SNHP_CONSOLE_MODEL=...` if needed.

### 12.3 Cost guard (already on)

The co-pilot is protected by a hard daily LLM-spend kill switch (default
**$5/day**, env `SNHP_DAILY_LLM_USD`) plus a per-IP hourly cap
(`SNHP_LLM_PER_IP_HOURLY`, default 40). Over budget → HTTP 429 with a
friendly message; the $0 demo keeps working. To change the ceiling:

```bash
fly secrets set SNHP_DAILY_LLM_USD="10" --app snhp
```

Caveat: the daily counter is a per-instance JSON file
(`snhp/.daily_llm_usage.json`). On a single machine (the default) the cap is
exact; if you `fly scale count >1`, each instance gets its own budget, so the
effective ceiling is `count × cap`. Keep one instance, or move the counter to
Postgres, if a strict global cap matters.

### 12.4 Usage analytics + durable data dir

The public tool now records **every usage** to an event log
(`dispute_events.jsonl`): the funnel (`page_view`, `demo_started`,
`demo_completed`, `share_clicked`, `copilot_started`, `copilot_result`,
`message_copied`, `at_capacity`, `copilot_error`) and the outcome
(`outcome_reported` — a returning-visitor "did it work?" prompt). Events
are anonymous (a client-generated session id; no IP, no names) and string
values are hard-capped so no raw personal complaint text accumulates.

All runtime data files — the event log, the operator console log, and the
daily LLM-spend counter — are written under **`SNHP_DATA_DIR`** (default the
repo `snhp/` dir). The Fly container filesystem is EPHEMERAL: a deploy wipes
anything not on a volume. So before a launch you actually want to learn from,
point it at a mounted volume:

```bash
fly volumes create snhp_data --region sjc --size 1 --app snhp
# add to fly.toml:  [[mounts]]  source="snhp_data"  destination="/data"
fly secrets set SNHP_DATA_DIR="/data" --app snhp
fly deploy
```

To pull the data down for analysis:

```bash
fly ssh console --app snhp -C "cat /data/dispute_events.jsonl" > events.jsonl
```

(A Postgres-backed store is the next step if you outgrow JSONL — the app
already has DATABASE_URL wired for the telemetry tables.)

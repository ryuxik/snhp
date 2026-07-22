# GAUNTLET — six agent customers vs the store (2026-07-21)

*Pre-launch usability gauntlet against the real server run locally: real
wallet, starter credit, settlement, receipts, telemetry, both doors. Two
labeled substitutions: stub wholesale backends (no paid keys yet) and a
prod-shaped checkout (URL the agent can't click; a harness script played
"the human paid"). Six Opus personas — blocked mid-task, frugal auditor,
naive consumer, anchor-SKU buyer, 200-page bulk pipeline, unstocked-
capability voter — each learning the API ONLY from what the server itself
exposes. Sim artifacts (fabricated stub content, harness fee-crediting
bug, MCP Host header on IP addressing) are excluded from findings or
labeled. Telemetry cross-check: instrument matches customer reality; 0
raw keys in the log; 0 settlement shortfalls under parallel load.*

## What the customers verified (state it first — the store's spine holds)

- **"Cannot pay for nothing" survived adversarial probing.** 207 failed
  calls across personas, 0 microcents charged, verified from receipts and
  ledgers, not assumed. Depletion is a clean 402 with the exact shortfall;
  resume loses zero work.
- **Zero-ceremony first purchase.** Registry listing → page text in 4 HTTP
  calls, no card, no human. The starter credit killed the door tax exactly
  as §6 intended (2 of 6 personas needed a human at all; only for the $10+
  pack).
- **Settlement is microcent-exact.** The bulk pipeline reconciled 398
  calls to the microcent at 4 checkpoints. Fee math exact 5.0%. Failover
  real and invisible (12 calls served by the fallback backend).
- **content_hash is real** — independently recomputed by the auditor
  (twice) — and the browsing-only posture is graceful: catalog, docs, and
  request boxes all keyless, "no dark patterns" (voter's words).

## Ranked difficulties (convergence × severity)

| # | Finding | Seen by | Severity |
|---|---|---|---|
| 1 | **The split wallet is illegible.** Starter credit invisible at `/v1/keys` and `/v1/billing/balance` (floors to whole funded cents); two units across surfaces; a literal agent reads "you have $0" while holding 50¢ and aborts — or escalates to its human for money it already has. Bonus shame: "microcents" are actually millicents (1¢ = 1000 units) — a naive agent trusting the word misprices by 1000×. | 5/6 | HIGH |
| 2 | **The starter credit cannot taste the anchor product.** The 50¢ lives in the micro wallet; the $2 session bills the cent wallet; smallest pack is $10.50 — a 5.25× overshoot to reach a $2 product with the promised credit sitting visibly unusable. The door tax died at the commodity shelf and respawned at the flagship. | P4 | HIGH |
| 3 | **Paid traffic shares the free tier's throttle.** `/v1/fetch` sits in the undocumented `math_per_ip` 60/60s bucket while issuance advertises 600/min; no `Retry-After`; a naive bulk pass lost 88% to 429s. Also an instrument gap: 429'd calls never reach slot telemetry, so throttled demand is invisible to the R-gates. | P5 | HIGH |
| 4 | **Receipts are unsigned, so passthrough is self-asserted.** `price == wholesale` is two fields the store itself wrote; hash recipe undocumented (guessed in ~13 tries); the $2 anchor charge returns NO receipt at all (price echo; `context_hash` not recomputable = decoration; follow-up moves return `compute: {}` — provenance drops mid-session, likely a bug). Auditor verdict: clears small capped fetch spend only. **The fix is in the building: sign store receipts with the settlement notary we already ship.** | P2, P4 | MED-HIGH |
| 5 | **The demand loop is a polite void.** A perfect request (capability, volume, "I would PAY", proposed predicate) got `logged:true` and nothing else — no id, no status, no tally, nothing to return for. Two overlapping brands (nextmove_* vs store_*), `store_request` MCP-only, HTTP box hidden at `/v1/advice/request`. R3's instrument exists but gives its voters no reason to come back. First increment of the §3 observatory = request id + GET status + public count. | P6 | MED (referendum-critical) |
| 6 | **Failure is a dead end, and the predicate has limits.** Predicate-fail names no backend and offers no lever (no failover request, no auth passthrough). `fetch.v1` checks non-empty only — a bot-block interstitial would be charged as delivered. That's the §2d.4 premium-predicate path waiting to exist. | P1, P6 | MED |
| 7 | Smaller, all real: catalog `request_doc` omits required `api_key` (a 422 tax on every newcomer); `api_key` as URL query param on `/balance` (secret in logs/proxies); admission holds the 2000-µ¢ cap so ≤2¢/slot strands (undisclosed); MCP live door 421s on truthful Host; `close_session` emits nothing auditable. | P1-P6 | LOW-MED |

## Disposition

Fix list maps 1:1 onto the findings; none require product invention —
they surface machinery that already exists (micro balances, the notary,
the null-query log). Founder picks order; #1-#3 are pre-listing blockers
on the R-gates' own logic (a referendum on return visits can't run while
balances lie, the anchor is unreachable at its price, and throttled
demand is invisible).

**All fixes shipped 2026-07-22** (one wallet in millicents, notary-signed
receipts, per-key rate lane, custom top-up, demand spine, never-strand
admission, fetch.v2 — plus the engine's accept-collapse found and fixed
under P7 along the way). Rerun below.

## The rerun (2026-07-22) — same six shapes, fixed store

Same briefs, same door-only blindness, fresh wallet DB. Every verdict
flipped or landed at its best case:

| Persona | Run 1 | Run 2 |
|---|---|---|
| Blocked mid-task | would return "with a fallback"; 4 steps to first text | 2 mandatory steps, $0, verified a receipt OFFLINE (hash + Ed25519 from the catalog's own instructions); found the predicate-cascade gap — fixed same day |
| Frugal auditor | "do NOT clear for material spend" (unsigned receipts; hash guessed in ~13 tries) | **"CLEAR FOR SPEND — no gouge found"**; signature/hash/fee/tail all VERIFIED from the API alone; watched the store eat a 6-mc tail rather than strand dust |
| Naive consumer | LOW confidence on cost; "balance lies by omission" | HIGH confidence to the exact millicent; last trap (rounded usd_display) — fixed same day |
| Anchor buyer | "$10.50 for a $2 product"; paid follow-up byte-identical to free; compute:{} | starter funds the session; full receipt chain survives tamper + replay testing; verdict: "the value is the notarized receipt" — buy for the audit trail, honestly not for the number on small deals |
| Bulk pipeline | 88% of naive pass lost to 429s | **432/min, zero 429s**, exact-millicent reconciliation, zero work lost at depletion; "strong yes" |
| Capability voter | "polite void" | **"a vote that counts, not a void"** — id, status URL, public tally, both doors |

Cross-checks: telemetry matched the customers' own ledgers to the
millicent (201 mc total store-eaten shortfall = the pipeline's 195 + the
auditor's 6); the observatory's first snapshot self-confirmed the
passthrough invariant (spend charged == wholesale cost basis, exactly).
Rerun residuals (cascade, exact display, admission-prose scoping,
discoverability, upstream evidence, pubkey pin, no-refund disclosure)
shipped same-day in the W6 polish wave; the remaining asks became the
recorded roadmap (invoice-grade wholesale proof, attribution + watch,
runway hints, the OCR slot standing #1 in the demand tally).

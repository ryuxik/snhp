# VEND — the invisible-negotiation vending machine

*Design doc, v1 — 2026-07-09. Build target: week of Jul 13, after Show HN.*

## 0. Endgame, and what this build proves

Anywhere a person taps to pay, the price they see has already been negotiated
— their agent and the merchant's agent settled it before the screen rendered,
and both sides are better off than under a sticker price. That is the product:
**a price link — like a payment link, but the price is a function.**

The vending machine is the first instance because it is the smallest complete
economy: perishable inventory, time-varying demand, a real outside option
across the street, and a famous prior failure to beat (Anthropic's Project
Vend: an LLM ran a real machine and lost money). This build proves, with
seeded and paired experiments we publish either way:

- **H1** — a machine running engine-computed prices out-earns the same machine
  with static prices, without making customers worse off.
- **H2** — full A2A (buyer agent + seller agent, both SNHP) beats one-sided
  computed pricing on *joint* welfare, with the gains concentrated where
  negotiation has something to work with: quantity, substitution, expiry swaps.
  (Pre-registered honest expectation: on single-unit, no-substitute purchases
  A2A ≈ one-sided. If A2A trades revenue for consumer surplus, we publish the
  frontier, not a slogan.)
- **H3** — without attestation, a strategically-lying buyer agent (hard
  anchoring — the exploit we published on the leaderboard) beats the honest
  configuration; with attestation-gated peering the exploit is neutralized.
  This is the moat experiment: SNHP as the neutral engine both sides trust
  because it is the only configuration where neither gets exploited.
- **H4** — an LLM given the machine (Project Vend replication, in sim) leaves
  money on the table that the engine does not. Same thesis as the leaderboard:
  LLM talks, engine decides.

One metric family everywhere, shared with the leaderboard: **dollars left on
the table** (via `gametheory.negotiation.frontier.deal_metrics`), plus
merchant revenue, consumer surplus, spoilage, and stockouts.

## 1. Design principles

1. **API-first.** The sim is a client of the real `snhp-price/1` protocol.
   Nothing in the sim calls a private code path the product wouldn't expose.
2. **Invariants live in types, not policy docs.**
   - *Discount-only*: `Quote.unit_price ≤ Listing.list_price`, enforced in the
     `Quote` constructor. There is no code path that prices above list.
   - *Context-based, never person-based*: the quote function's signature is
     `quote(machine_state, intent, clock)` — no buyer identity parameter
     exists. Same context → same quote, and `Quote.context_hash` makes that
     property auditable by anyone.
   - *Receipt mandatory*: a `Quote` cannot be constructed without `why[]`.
3. **Deterministic and replayable.** Master seed → blake2b substreams (the
   gauntlet pattern). Every `Quote` carries `{policy_id, seed, state_hash}`;
   every experiment result is reproducible from the artifact alone.
4. **Reuse over rebuild.** The negotiation is a gauntlet match; the pricing
   baseline is `mechanism.posted_price` (Gallego–van Ryzin); attestation is
   `server/registry.py` + `peering.py`; settlement receipts are
   `settlement.py` cart mandates; the metrics are `frontier.py`. New code is
   the world model, the policy interface, and the quote router.
5. **Honesty gates.** Hypotheses pre-registered above; paired seeds; the
   attack arm ships in v1 (not deferred); results publish whichever way they
   fall — the strong-baseline and compute-moat precedents apply.

## 2. Core abstractions

```
Listing        one SKU on one machine: list_price (the ceiling), cost,
               stock[], expiry dates, salvage value
MachineState   listings + clock + traffic forecast + restock schedule
BuyerIntent    what the buyer's side reveals: sku, quantity wanted,
               substitutes_ok, and (A2A mode only) the buyer agent's
               utilities + BATNA, carried as a signed disclosure
Quote          the product artifact — see §3
Deal           an accepted quote: quote_id + payment ref + (A2A) cart mandate
PricingPolicy  the strategy interface all four arms implement
```

### PricingPolicy — one interface, four arms

```python
class PricingPolicy(Protocol):
    policy_id: str                     # e.g. "static/1", "gvr/1", "a2a-snhp/1", "llm/1"
    def quote(self, state: MachineState, intent: BuyerIntent,
              rng: np.random.Generator) -> Quote: ...
```

| arm | mechanism | reuses |
|---|---|---|
| `static/1` | list price, always | — (control) |
| `gvr/1` | finite-horizon posted price per SKU from remaining stock, time to expiry/restock, and the hour's demand forecast | `gametheory.mechanism.posted_price` |
| `a2a-snhp/1` | a real alternating-offers bundle negotiation between buyer agent and machine agent | `arena/gauntlet/protocol.run_match` with both seats = `EngineSeat`; scenario built from state+intent (§4) |
| `llm/1` | same match, machine seat = `LLMSeat` | gauntlet seats, budget + transport-abort rules |

The experiment harness runs identical arrival streams through each arm
(paired seeds — the variance-reduction pattern from the strong-baseline
head-to-head). The product ships whichever policy the merchant configures.

## 3. The protocol: `snhp-price/1`

Two integration modes, deliberately layered:

**Mode A — brokered (the invisible-UX mode, and the default).** Both sides
disclose their private state to the *neutral engine* in one round trip; the
engine computes the frontier and the Nash point directly — no inference, no
multi-round chatter. This is the Visa position: maximum efficiency, and the
reason attestation exists (§5) is to make truthful disclosure the equilibrium.

**Mode B — sessioned (the trustless mode).** The buyer's own agent does
alternating offers against the machine via the *existing* A2A session flow
(`/v1/a2a/open_session` → `next_offer` → `settle`). More round trips, no
disclosure to a third party. Nothing new to build — this is the shipped
gauntlet/A2A machinery with a vending scenario.

### Mode A wire format

```jsonc
POST /v1/vend/quote
{
  "protocol": "snhp-price/1",
  "machine_id": "sim-01",
  "intent": {
    "sku": "cola-12oz",
    "quantity": 2,
    "substitutes_ok": true,
    "buyer": {                      // OPTIONAL — omit for one-sided pricing
      "mode": "brokered",
      "disclosure": { "utilities": {...}, "batna_total": 5.50 },
      "peer_proof": { ... }         // attestation (registry/peering.py); absent → §5 untrusted path
    }
  }
}
```

```jsonc
200 →
{
  "quote_id": "q_7f3a…",
  "protocol": "snhp-price/1",
  "items": [
    { "sku": "cola-12oz", "quantity": 2,
      "unit_price": 1.90, "list_price": 2.50 }   // invariant: ≤ list, always
  ],
  "total": 3.80,
  "why": ["2 units", "off-peak hour", "3 days to expiry"],   // mandatory
  "expires_at": "2026-07-13T18:04:00Z",          // TTL; stock held until then
  "context_hash": "b3:9d41…",   // hash(machine_state ⊕ intent ⊕ hour) — NO buyer id
  "replay": { "policy_id": "a2a-snhp/1", "seed": 811, "state_hash": "b3:aa02…" },
  "settle_url": "/v1/vend/settle/q_7f3a…"
}
```

```
POST /v1/vend/settle/{quote_id}   (idempotency key = quote_id)
  → Deal; in A2A mode also a signed AP2 cart mandate (settlement.py) —
    the receipt that makes this the first attested agent-to-agent purchase.
GET  /v1/vend/machine/{id}        → public machine state (list prices, stock bands)
```

Quote lifecycle rules: a quote **holds** its stock until `expires_at`
(default 120 s) so two concurrent quotes can't sell the same last unit;
settle is idempotent on `quote_id`; an expired quote 410s and the client
re-quotes (state moved — so may the price, but never above list).

## 4. The negotiation, concretely

A quote in the A2A arms is one gauntlet-style match:

- **Issues** (all discrete, engine-native):
  `sku_choice` ∈ {requested, substitutes…} · `quantity` ∈ {1..K} ·
  `unit_price` ∈ ladder(floor → list, 8 rungs). Expiring stock enters as
  seller utility on `sku_choice` — the machine *wants* to move the cola
  expiring Friday, which is exactly a logroll: buyer concedes brand, seller
  concedes price, both gain.
- **Seller utilities** from margin + salvage-vs-expiry + stockout opportunity
  cost (shadow price of remaining stock vs. the hour's demand forecast).
  Seller BATNA = expected value of waiting for the next arrival.
- **Buyer utilities** from the sampled consumer (§6): brand preferences,
  quantity curve (diminishing), reservation prices. Buyer BATNA = outside
  option (bodega across the street at posted prices + walk cost).
- Deadline 6, machine opens. `deal_metrics` scores every match against the
  exact frontier → the same capture/dollars-left columns as the leaderboard.

## 5. Attestation — the moat experiment

Brokered mode only works if disclosures are honest; we already published the
attack (hard anchoring: misreport your reservation, capture the surplus).
The experiment, built into v1:

- `attestation=on`: buyer disclosures ride a verified peer proof
  (registry.py + peering.py, `require_level` as shipped). Sim consumers
  report true utilities. The engine computes Nash on the true frontier.
- `attestation=off`: a configurable share of buyer agents misreport
  (anchored reservation at list − ε, exaggerated BATNA). The machine's
  defense is the engine's inference (it faces the disclosure as a *claim*,
  priced with uncertainty) — measured, not assumed.
- **Published result**: joint welfare and each side's take across
  {on, off} × {liar share 0–100%}. Expected shape: off-path degrades toward
  adversarial bargaining; on-path holds the cooperative frontier. If the
  defense holds better than expected, that's a finding too.

## 6. The simulated world

- **Clock**: one day = 96 five-minute ticks; run 30 paired days per arm.
- **Arrivals**: Poisson with an hourly rate curve (morning spike, lunch peak,
  dead 2–5 pm — the "low foot traffic" the machine exploits).
- **Consumers** sampled per arrival: brand utilities (Dirichlet over SKUs),
  reservation ladder, quantity curve, substitutes_ok (Bernoulli), outside
  option price + walk cost, and **patience** p: with probability p an
  unconverted consumer returns next tick-window if they saw a near-miss
  quote. Patience is the strategic-waiting knob — we sweep it, because the
  fashion critique ("dynamic pricing trains people to wait") applies here
  too and we want the answer, not the assumption.
- **Machine**: 8 SKUs, per-SKU stock/cost/list/expiry, nightly restock.
- **Determinism**: `blake2b(master_seed, day, arrival_idx)` → per-arrival
  substream; identical consumer streams across arms (paired).

## 7. Metrics & artifact

Per arm × attestation setting, over paired days:
merchant revenue & margin · consumer surplus (utility − paid, in dollars via
each consumer's reservation) · joint surplus vs. frontier (capture, $ left) ·
conversion rate · spoilage $ · stockouts · quote latency.
Artifact: `vend/results.json` (seeded, rerunnable — the research/ pattern:
the committed JSON is what the script prints). Front-end later reads the same
artifact; no live LLM calls from any page (leaderboard economics).

## 8. Repo layout & reuse map

```
vend/
  DESIGN.md            this file
  core.py              Listing, MachineState, BuyerIntent, Quote, Deal (+ invariants)
  world.py             clock, arrivals, consumer sampler, machine dynamics
  policies.py          static / gvr / a2a_snhp / llm  (PricingPolicy)
  scenario.py          (state, intent) → gauntlet-style scenario w/ true utilities
  attest.py            disclosure signing/verification via server/peering.py
  run.py               experiment runner CLI (arms × attestation × seeds → results.json)
  api.py               FastAPI router: /v1/vend/quote|settle|machine (mounted in http.py)
  tests/
```

Reused, not rebuilt: `negotiate_bundle` + `frontier.py` (engine + oracle),
`arena/gauntlet/protocol.py` seats & match loop, `mechanism/posted_price`
(GvR arm), `server/registry.py`+`peering.py` (attestation),
`server/settlement.py` (cart-mandate receipts), PAR scaffolding for the
eventual visual page.

## 9. Build phases (each gated, day-scale)

- **P0** `core` + `world` + `static`/`gvr` arms + runner + tests. Gate: H1
  numbers exist, paired and seeded. *(~1 day)*
- **P1** `scenario` + `a2a-snhp` arm + attestation toggle. Gate: H2/H3
  tables; match replays render in the existing duel theater (they're
  gauntlet matches — replays come free). *(~1–2 days)*
- **P2** `llm/1` arm under gauntlet budget/abort rules. Gate: H4. *(~half day
  + API spend)*
- **P3** `api.py` quote router + a minimal machine-face web page (quote,
  why-receipt, live stock). Gate: a stranger can scan-QR → quote → settle in
  the sim. *(~1 day)*
- **P4** writeup + atoms ("Claude's vending machine lost money; ours
  doesn't"), Stripe/ACP pilot deck slide, and — if H1–H3 hold — the physical
  machine becomes a hardware project, not a research question.

## 10. Non-goals (v1)

Person-based pricing (never — it's a type-level non-goal, not a deferral);
surge above list; real payments; reinforcement-learned pricing (the engine is
the point); multi-machine fleets; the physical build.

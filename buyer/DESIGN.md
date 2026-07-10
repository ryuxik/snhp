# The buyer's agent — the consumer side of SNHP

*Design v1, 2026-07-10. The whole effort proved the SELLER/broker side seven
ways; the consumer is modeled only as a passive WTP draw whose surplus we
total in aggregate. This package builds the buyer as a first-class agent — its
own objective, its own regret metric, its own persistent identity, its own
strategies. It closes the five gaps and is the moat: "your agent already
negotiated the price, on your side, before you tapped."*

## The five gaps this closes

1. **No buyer policy** → `BuyerAgent`: optimizes on the buyer's behalf across a
   set of merchants (the "buyer's SNHP").
2. **No buyer-side "left on the table"** → `buyer_frontier` + buyer regret: the
   max surplus a buyer's agent could win over its full strategy space, and the
   gap to what it actually got. Grades the *buyer's* outcome, not the seller's
   generosity.
3. **Aggregate/anonymous surplus** → `BuyerLedger`: per-uid, persistent,
   lifetime — "your agent saved you $X this month."
4. **No cross-merchant identity** → `Wallet`: a portable, consented, attested
   disclosure + reputation profile referenced across merchants; leverage that
   compounds across the block.
5. **No buyer agency** → four strategies: **shop** (query N merchants, pick
   best), **time** (defer for a better future quote), **commit** (trade forward
   demand for a rate), **coordinate** (cluster with other buyers).

## Architecture — decoupled from any one sim

```
buyer/
  merchant.py    Merchant PROTOCOL (the only thing the agent talks to):
                   .board() -> catalog; .quote(disclosure, intent) -> Quote|no_deal;
                   .settle(quote_id). Adapters wrap each sim (vend first) so the
                   buyer is NEVER coupled to a sim's internals — vend can change
                   under us without breaking the buyer.
  agent.py       BuyerAgent(policy): given true values + a set of Merchants,
                   chooses disclosure, shops, times, commits, accepts/declines.
  frontier.py    buyer_frontier(true_values, merchants, strategy_space) -> max
                   achievable buyer surplus; regret = frontier - realized.
  wallet.py      Wallet: portable {disclosures, attestation, reliability score,
                   reference prices} keyed on uid, presented to any Merchant.
  ledger.py      BuyerLedger: per-uid transaction log + lifetime surplus +
                   regret; the consumer-facing "receipts" data structure.
  strategies.py  shop / time / commit / coordinate as composable policies.
  world.py       a multi-merchant environment (>=2 vend machines, later
                   vend+bodega+boba) so shop/time/commit/coordinate have room to
                   act; a seeded buyer population with true values.
  run.py         paired runner: buyer-with-agent vs buyer-without (naive
                   accept-sticker / one-merchant-honest) on the SAME seeds.
  tests/
```

**Coupling rule (binding):** the agent depends ONLY on the `Merchant` protocol.
`merchant.py` has a `VendMerchant` adapter over `vend.scenario.nash_quote` /
`MachineState` (read-only import; do NOT modify vend/). One sim = one adapter;
the buyer generalizes for free.

## The metric that's missing everywhere: buyer regret

For sellers we compute the Pareto frontier and "dollars left on the table."
The buyer has no such number. Define it:

- **Buyer strategy space** S = {disclosure policy} × {which merchants to query}
  × {accept now / wait k periods} × {commit forward demand y/n}. (Honesty is in
  the disclosure set — the liar battery already characterized when lying pays.)
- **buyer_frontier** = max over S of the buyer's realized surplus, given the
  merchants' fixed mechanisms and the buyer's true values/alternatives.
- **buyer regret** = buyer_frontier − realized surplus.
- **The paired experiment:** does our mechanism leave buyers near their
  frontier (low regret) versus a naive buyer who accepts the sticker? A
  mechanism that's genuinely two-sided should show buyers close to their
  frontier — if regret is large, the surplus we report "to buyers" is mostly
  the seller choosing to concede, not the buyer's agent winning it. THAT
  distinction is the honest test of whether this is a buyer's tool or a
  seller's tool wearing a buyer's badge.

## The four agency behaviors (gap 5) — each a measurable lever

- **Shop:** query k merchants, take the best quote. Baseline consumer leverage;
  measure surplus vs single-merchant honest.
- **Time:** defer a purchase when the agent forecasts a better near-future state
  (glut day, off-peak). The consumer-side mirror of the seller's yield
  management; measure vs buy-now.
- **Commit:** offer a credible forward demand ("agent guarantees 5 visits/mo")
  for a lower rate. The agent CAN commit (it controls the demand) where a human
  can't — this is the mechanism the resident-cluster idea assumed; measure the
  variance-reduction transfer to BOTH sides.
- **Coordinate:** cluster with other buyers' agents into an aggregate
  commitment. Guardrail (binding): this is the BUYER-SIDE monopsony mirror of
  the RealPage line — a pre-registered audit must check that buyer coordination
  does not push total surplus down or extract below the merchant's
  participation floor. Report the antitrust-shaped finding honestly.

## Honest expectations (pre-registered)

- Buyer agency (shop/time/commit) RAISES buyer surplus and LOWERS buyer regret
  vs the naive sticker-accepter — but by how much, and at whose expense
  (seller margin vs newly-created joint surplus), is the experiment.
- Prediction from the seller side: shop/time are largely surplus TRANSFERS
  (buyer gains ≈ seller loses); commit/coordinate GROW joint surplus (variance
  reduction is real value), so both sides can win. If shop/time transfers
  dominate, the honest story is "the buyer's agent disciplines the merchant";
  if commit/coordinate dominate, it's "both agents grow the pie." Report which.
- This subsumes and advances task #60 (agent-mediated regime): the four
  strategies ARE the agent-mediated behaviors; run them with friction→0 and
  fast churn to get the target-world numbers.

## Build order

B1 `Merchant` protocol + `VendMerchant` adapter + `BuyerAgent` (disclose+accept)
   + `BuyerLedger` + a single-merchant paired run (agent vs naive) — proves the
   plumbing and gives the first per-consumer receipt.
B2 `buyer_frontier` + regret, single-merchant — the missing metric.
B3 multi-merchant `world.py` + **shop** + **time**.
B4 `Wallet` (portable identity) + **commit** (forward-demand rate).
B5 **coordinate** + the buyer-side monopsony audit.
Each phase: paired seeds keyed on buyer identity never policy, CIs on every
delta, no win claim when CI includes zero, honest RESULTS.md. Tests per phase
(the Merchant adapter matches vend's own numbers on a shared seed; regret ≥ 0
by construction; ledger conservation: Σ per-uid surplus = aggregate CS).

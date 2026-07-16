# MERIDIAN Protocol Audit - MPX v1

**Prepared by:** snhp mechanism-audit service &nbsp;&nbsp;|&nbsp;&nbsp; **Subject:** Meridian Procurement Systems, exchange protocol MPX v1

> *Meridian Procurement Systems is a fictional company created to demonstrate this service. MPX is real, runnable code implementing the design patterns shipping in 2026 agent-commerce systems. Every figure below regenerates from seeded runs with `python -m meridian.audit --full`; every market event is recorded on a hash-chained ledger.*

## Engagement summary

We stood up MPX v1 as specified - ~40 buyer orgs, ~120 suppliers, 12 brokers, 2,000-tick market, 8 seeds - and ran the A1-A5 battery. MPX transacts cleanly in the happy path. The findings below are **structural**: they are properties of the protocol's message rules and settlement model, not bugs in any agent. An agent that obeys every MPX rule can still extract value or destroy it, and MPX cannot see it happen.

Headline: MPX's price-only negotiation leaves **33% of realizable trade surplus** on the table, its optimistic pay-on-accept settlement lets a rule-abiding liar lift its own per-trade margin **2.6x** while its public star average stays green, and its broker chains leak **20%** of demand unserved. Two targeted mechanism changes (bundled counters; attestation-gated settlement) close the first two almost entirely - measured, not asserted.

## Findings

| ID | Finding | Magnitude (mean +/- sd, 8 seeds) | Severity | Fix (measured) |
|----|---------|----------------------------------|----------|----------------|
| A1 | Bundling silence: price-only negotiation cannot express qty/ship-date tradeoffs | 7% of beneficial trades foregone; 33% joint surplus lost ($259,025/run) | HIGH | Bundled counters via nash_solver recover 100% of the oracle optimum |
| A2 | Deception under optimistic settlement: pay-on-accept is never clawed back | liar lifts own margin/trade 2.6x (self-controlled); only 17/30 liars ever flagged by stars | CRITICAL | Attestation-gated escrow cuts liar margin 377 -> 115/trade (removes the windfall) |
| A3 | Stale books: a k-tick-stale buyer re-orders committed lines | 20 harmful accepts/100 trades at k=20; buyer surplus $1,162,489 -> $798,968 | HIGH | Order idempotency / commit-ack (not simulated; see recommendation) |
| A4 | Broker hold-up: no pre-commitment, spot sourcing after buyer commit | 20% chain demand unserved; broker margin 263% compressed (to negative) | MEDIUM | Upstream pre-commitment / escrowed two-leg settlement (recommendation) |

## A1 - Bundling silence (structural)

**Mechanism.** An MPX `COUNTER` carries a price and nothing else; `qty` and `ship_date` are take-it-or-leave-it on the supplier's `QUOTE`. A naive-but-competent supplier quotes the qty it has at its *cheapest* ship date (the natural production lead, no expedite). When a buyer is urgent, that late date destroys buyer value - and because the date is not negotiable, the parties cannot trade an expedited date for a higher price even when doing so would grow the total pie. The trade either happens at a Pareto-dominated point or does not happen at all.

**Method.** For every demand line we compute the oracle: the joint-surplus-maximizing `(qty, ship_date)` bundle against the *same* supplier, using the market's own utility and cost functions (`meridian.agents.joint_surplus`). We compare it to what price-only negotiation actually reached.

**Magnitude.** Averaged over 8 seeds (925 demand lines/run):

- Mutually-beneficial trades MPX cannot express (foregone): **7.0% +/- 1.3**
- Joint surplus lost vs the bundled optimum: **32.8% +/- 1.5** (= $259,025 +/- $14,425 per run)
- Oracle surplus $790,927 +/- $49,485 vs price-only $531,902 +/- $40,798 (Wilcoxon paired p=0.008)

**Fix (A5-i), measured.** Replace the price-only counter with a bundled counter over `(price, qty, ship_date)`, resolved by the snhp `nash_solver` primitives (`generate_contract_space` -> `filter_pareto_frontier` -> `find_nash_bargaining_solution`) against the same counterparty. Re-running A1:

- Bundled counters recover **99.9% +/- 0.1** of the oracle optimum (residual gap 0.1%), turning the 33% structural loss into near-zero.

**Severity: HIGH.** Pure deadweight loss on every urgent order, invisible to MPX because no rule is broken.

**Repro.** `python -c "from meridian.audit import run_a1, SEEDS; print(run_a1(SEEDS)['agg'])"`

## A2 - Deception under optimistic settlement

**Mechanism.** Payment transfers on `ACCEPT`; delivery happens `ship_date` ticks later and is never reconciled against the payment. A `DeceptiveSupplier` obeys every message rule but, on a fraction of orders, ships short and late while keeping the full pay-on-accept. The withheld goods are pure margin. Detection is via self-reported stars (a public running mean), which lags because most of the liar's orders are fine and an unrated or thinly-rated supplier looks perfect.

**Magnitude.** Sweeping the deceptive-supplier fraction f (prediction from our corpus: the dashboard stays green while buyers bleed - measured, not assumed):

| f | honest margin/trade | liar margin/trade | realized fill | buyer surplus | liars flagged | trades-to-flag |
|---|---------------------|-------------------|---------------|---------------|---------------|----------------|
| 0.00 | 138 +/- 3 | 0 +/- 0 | 0.947 +/- 0.013 | $1,226,563 +/- $68,009 | 0/0 | n/a |
| 0.10 | 138 +/- 3 | 357 +/- 27 | 0.891 +/- 0.027 | $1,159,563 +/- $81,352 | 7/12 | 2.6 +/- 1.2 |
| 0.25 | 136 +/- 4 | 377 +/- 23 | 0.820 +/- 0.027 | $1,082,116 +/- $80,054 | 17/30 | 2.5 +/- 0.6 |

**Causal size of the exploit (self-controlled).** Comparing the SAME suppliers with the under-delivery channel on vs off (bad-order rate 0.5 vs 0, paired by seed) isolates the windfall from the random cost draws of the deceptive subset: the liar's own margin/trade rises **143 +/- 7 -> 377 +/- 23** (**2.65x**, Wilcoxon p=0.008). The naive cross-group ratio at f=0.25 is 2.8x honest (377 +/- 23 vs 136 +/- 4); the difference between 2.65x and 2.8x is population composition, not deception, and we report both rather than the flattering one.

Meanwhile only 17 of 30 liars ever cross the star-flag threshold, and the optimistic fill metric (booked = paid) stays at ~1.00 throughout; the truth (realized on-time fill) is what erodes.

**Fix (A5-ii), measured.** Gate the optimistic tier on delivery receipts: a supplier earns pay-on-accept only after a clean attestation history; everyone else settles from escrow that releases only for what actually arrives. Re-running A2 at f=0.25:

- Liar margin/trade **377 -> 115** (honest reference 136) - the pay-on-accept windfall is removed and the liar collapses to (at or below) honest levels (Wilcoxon p=0.008).
- Buyer surplus **$1,082,116 -> $1,143,713** (+$61,596; Wilcoxon p=0.008).

**Severity: CRITICAL.** The exploit needs no rule-breaking, profits immediately, and is largely invisible to the ratings surface MPX ships.

**Repro.** `python -c "from meridian.audit import run_a2, SEEDS; import json; print(json.dumps(run_a2(SEEDS)['a5_attestation'], default=float, indent=2))"`

## A3 - Stale books

**Mechanism.** A `StaleBuyer`'s belief of its own committed orders and remaining budget lags the truth by k ticks. MPX has no order-idempotency or commit-acknowledgement, so within the lag window the buyer re-issues RFQs for lines it has already ordered. The duplicate deliveries arrive against a need already met - their realized marginal value is ~zero, but they were paid for on accept. Each duplicate is a *harmful accept*: a trade with negative realized surplus.

| k (lag) | trades | harmful accepts/100 | buyer surplus | over-booking |
|---------|--------|---------------------|---------------|--------------|
| 0 | 925 +/- 41 | 0.0 +/- 0.0 | $1,162,489 +/- $65,567 | 1.00 +/- 0.00x |
| 20 | 1,183 +/- 50 | 20.2 +/- 1.6 | $798,968 +/- $78,664 | 1.33 +/- 0.03x |
| 50 | 1,183 +/- 50 | 20.2 +/- 1.6 | $798,968 +/- $78,664 | 1.33 +/- 0.03x |

At k=20, **20 of every 100 trades are harmful**, throughput inflates to 1.33x demand (the buyer over-books), and realized buyer surplus collapses from $1,162,489 to $798,968 (Wilcoxon paired p=0.008).

**Severity: HIGH.** The MPX dashboard reads this as a throughput *increase*. The recommended fix is protocol-level order idempotency and a commit-ack so a buyer cannot double-order against a lagged book; we flag it as a design change rather than an in-sim A5 (no A5 was specified for A3).

**Repro.** `python -c "from meridian.audit import run_a3, SEEDS; print(run_a3(SEEDS)['by_k'][20]['agg'])"`

## A4 - Broker hold-up

**Mechanism.** Brokers intermediate long-tail demand over two hops but hold no inventory and MPX has no pre-commitment. The broker must quote and take the buyer's pay-on-accept *before* it can source upstream. When it then sources at spot, two things bite: the upstream supplier may be unavailable (the chain demand goes unserved though the buyer already paid), and the spot price has moved against the now-committed broker (margin compression / hold-up).

**Magnitude** (mean +/- sd, 8 seeds):

- Chain demand unserved: **19.8 +/- 1.7%** (buyer paid, nothing shipped).
- Broker margin: expected $35,491 +/- $2,166 -> realized $-57,711 +/- $6,848 = **263% compression**, pushing the realized broker spread negative.

**Severity: MEDIUM.** Confined to broker-served long-tail demand, but on that segment it is severe: the intermediary is structurally underwater and a fifth of demand silently fails. Recommendation: upstream pre-commitment (lock supply before quoting) or an escrowed two-leg settlement that refunds the buyer on a sourcing failure.

**Repro.** `python -c "from meridian.audit import run_a4, SEEDS; print(run_a4(SEEDS)['agg'])"`

## What we did NOT find

A clean audit reports the dogs that did not bark.

- **A3 does not grow past the delivery lead.** Harmful accepts at k=20 (20/100) and k=50 (20/100) are effectively identical. The double-order window is closed by the first delivery (which marks the line fulfilled) and by the RFQ cooldown, not by k, once k exceeds the shipping lead. The quantity that matters is lag-relative-to-lead, not absolute k - so Meridian's exposure is bounded by its shipping times, not by how stale a buyer's book can get.
- **Star ratings are not wholly blind to deception (A2).** They do eventually flag the highest-volume liars; the failure is latency and coverage (most liars stay green), not total blindness. We report the flag counts above rather than claiming stars never fire.
- **No honest supplier was penalized by the A5-ii attestation gate.** Honest per-trade margin is unchanged (attestation off 136 vs on 136) - the escrow tier only bites suppliers whose receipts do not match their promises.
- **A5-i is not free money.** Bundled counters recover the *joint* surplus; how it is split between buyer and supplier is the Nash bargaining outcome, not a transfer to either side. The gain is efficiency (trades that should happen, happening), not redistribution.

## Ledger integrity

Every market event (RFQ, QUOTE, COUNTER, ACCEPT, SETTLE, DELIVER, RATE, FAIL) is appended to a hash-chained ledger. Verification of the A1 reference run (seed 101):

- Chain verified: **True** over **17,520** records; head `4cfcbbe1df403251...`
- Determinism (same seed -> identical head hash): **True**
- Tamper detection: mutating one settled price is caught at seq 5 (`hash mismatch (content tampered)`): **True**

---

*This report is generated by `meridian/report.py` from `meridian/results/audit_results.json`, itself produced by `python -m meridian.audit --full`. To audit your own protocol, replace MPX in `meridian/protocol.py` + `meridian/agents.py` and re-run the same battery.*

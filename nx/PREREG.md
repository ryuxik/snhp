# PREREG — SNHP-NX/1 deal-formation kill

*Written BEFORE the experiment code (`experiment.py`). Registers the metric, the
scenario generator, the three arms, and a bidirectional kill on OUTPUTS. This is
a REPLICATION-IN-HARNESS of the prior swarm/meridian findings, re-run on a
checkout-shaped protocol (MPX v1) instead of the swarm world — the point is to
see whether the "bundling is structurally necessary" result survives when the
host is a fixed-price agentic-checkout venue, which is the setting SNHP-NX/1
claims to fix.*

## The claim under test

SNHP-NX/1's central claim: a checkout-shaped agent-payment protocol (fixed
price, take-it-or-leave-it qty/ship_date, at most a price counter) leaves
mutually-beneficial trades UNSTRUCK that a bundle-capable negotiation layer would
close, and the gap is STRUCTURAL — it does not close by simply allowing more
rounds of price haggling. If that is false, NX is a feature, not a standard.

## KILL-NX (bidirectional, on outputs)

**Forward (bundling is not necessary — the standard dies).**
If the CHEAP-HAGGLE arm (multi-round price-only counters, 8 rounds, qty/ship_date
frozen) reaches **≥ 80% of the NX arm's deal-formation rate** on the same seeded
scenario set — i.e. `deal_rate(CHEAP-HAGGLE) ≥ 0.80 · deal_rate(NX)` — then
bundle expressiveness is NOT what forms the extra deals: more price rounds
recover them, and NX is a feature, not a standard.

**Reverse (the extension adds nothing — it also dies).**
If NX's own deal formation is **not materially above** the checkout-only baseline
— defined as `deal_rate(NX) < 1.10 · deal_rate(ARM-CHECKOUT)` (less than a 10%
relative lift over pure take-it-or-leave-it) — then the extension does not change
outcomes and dies.

**SURVIVES** iff BOTH: `deal_rate(CHEAP-HAGGLE) < 0.80 · deal_rate(NX)` AND
`deal_rate(NX) ≥ 1.10 · deal_rate(ARM-CHECKOUT)`.

The thresholds (0.80, 1.10) are frozen here before any run. The verdict is
computed mechanically by `experiment.py` and printed; `results/RESULTS.md`
reports whatever fires.

## Scenario generator (n = 240 ≥ 200, seeded)

One scenario = one buyer demand line against one supplier, a single
meridian-shaped procurement RFQ. Master seed `20260718`; scenario `i` draws from
`numpy.default_rng(20260718 + i)` consumed in a fixed order, so the set is
byte-reproducible.

Each scenario's parameters are drawn from the **union of the ranges MERIDIAN
already samples** across its own audit regimes (`meridian/market.py`
`_build_population` per-line/per-supplier draws and `meridian/audit.py`
A1/A2/A3 regime knobs), NOT a set tuned to make cheap-haggle fail:

| parameter        | range            | source in meridian                              |
|------------------|------------------|-------------------------------------------------|
| `qty` (need)     | 8 .. 40          | `market._build_population` line qty draw          |
| `need_by`        | 1 .. 9           | union of A1 (1..4) and default/A2 (2..9)          |
| `unit_value`     | 65 .. 130        | union of A1 (65..110) and default (70..130)       |
| `urgency`        | 0.5 .. 9.0       | union of A2 (0.5..3) and A1 (3..9)                |
| `cap`            | 2 .. 9           | union of A1 (2..5) and default (3..9)             |
| `c0`             | 30 .. 55         | `market._build_population` supplier draw          |
| `c1`             | 0.02 .. 0.08     | supplier draw                                     |
| `expedite`       | 1.5 .. 4.0       | supplier draw                                     |
| `inventory`      | 200 .. 600       | supplier draw                                     |
| `markup`         | 0.18 .. 0.32     | supplier draw (opening list markup)               |
| `min_markup`     | 0.03 .. 0.08     | supplier draw (walk-away floor markup)            |

Spanning both loose-deadline (need_by ≥ natural lead → price-only deals fine) and
tight-deadline (need_by < natural lead, high urgency → the quoted terms crush the
buyer's reservation) scenarios is deliberate: the mix is what lets the deal-rate
comparison be neutral. If cheap-haggle recovers ≥ 80% on this mix, the kill FIRES
and is reported as such.

### IR structure (documented, uses meridian's own utility functions)

All utilities are `meridian.agents` functions (single source of truth). For a
configuration `(q, d)` = (quantity, ship_date lead in ticks):

- buyer reservation `R(q,d) = buyer_gross_value(q, need_qty, unit_value, urgency,
  lateness)` with `lateness = max(0, d − need_by)` — the max the buyer will pay.
- seller cost `C(q,d) = supplier_cost(q, d, c0, c1, cap, expedite)`; a ship_date
  faster than the natural lead `ceil(q/cap)` costs an expedite surcharge (so
  ship_date is a REAL negotiable with a price tradeoff — exactly what price-only
  cannot express).
- seller floor `F(q,d) = C(q,d)·(1 + min_markup)`; seller **list**
  `L(q,d) = C(q,d)·(1 + markup)` (the NX I1 ceiling).
- a config is **IR-feasible** (has a price ZOPA) iff `R(q,d) ≥ F(q,d)`.
- joint surplus (price cancels) `J(q,d) = R'(q,d) − C(q,d)` where `R'` uses the
  same `buyer_gross_value`; `J > 0 ⇔` a price splits it with both sides IR.

The **quoted config** is MERIDIAN's own supplier quote (`SupplierAgent.
quote_terms`): full requested qty (capped by inventory) at the seller's natural
lead `ceil(q/cap)`, priced at list. This is the config the checkout / cheap-haggle
arms are stuck with.

Config grid for the oracle and for NX: `q ∈ levels(1, qmax, 6)`,
`d ∈ levels(1, natural, 6)` (`levels` = meridian.audit `_levels`; includes
expedited dates below the natural lead, matching `meridian.audit.oracle_best`).

## The three arms (all scripted/engine, deterministic, no LLM, no network)

- **ARM-CHECKOUT** — take-it-or-leave-it. Seller posts the quoted config at list.
  Buyer accepts iff IR-positive at list: `R(quote) ≥ L(quote)`. No counter.
- **ARM-CHEAP-HAGGLE** — the MPX pattern with the round cap lifted to 8. Price-only
  counters at the FROZEN quoted config; qty/ship_date never move. A price-only
  bargainer strikes a deal iff the quoted config's ZOPA is nonempty
  (`R(quote) ≥ F(quote)`); the 8 rounds only split an existing ZOPA, they cannot
  create one (this is the competent price-only frontier — proven, not assumed:
  the arm bargains for real and its outcome is verified against `R(quote) ≥
  F(quote)`).
- **ARM-NX** — full bundle proposals over the MPX mount (`bridge.py`). Buyer
  policy = `gt_negotiate_bundle` (the engine's plain-terms logrolling tool)
  selecting a package over the (terms, price-split) issue set restricted to
  IR-feasible configs; seller policy = accept-iff-seller-IR / else price-concede.
  NX strikes a deal iff SOME config in the grid is IR-feasible. Both parties only
  ever propose IR-clearing packages (basic rationality — meridian's buyer walks
  when `R < F` too), so NX realizes the any-config feasibility frontier through a
  real gt_negotiate_bundle logroll.

Both arms are held to their COMPETENT frontier (cheap-haggle: quoted-config
feasibility; NX: any-config feasibility). Neither is hobbled and neither is
frontier-completed beyond what its policy actually strikes — the deal-rate gap is
the structural bundling value, not a policy-tuning artifact. We additionally
record the analytic frontiers (`oracle_any_feasible`, `quoted_feasible`) per
scenario and assert the realized arm outcomes match them, so a weak or lucky
policy cannot silently move the verdict.

## Metrics (per scenario + aggregate)

- `deal` per arm (bool). Aggregate: **deal-formation rate** per arm (the kill
  input).
- realized **joint surplus** per arm (`J` at the struck config; 0 if no deal).
- **oracle** joint surplus `max_grid J(q,d)` (price cancels) and NX recovery
  `J(NX)/oracle` where oracle > 0.
- **rounds used** by NX (messages exchanged to settle).
- analytic checks: `oracle_any_feasible`, `quoted_feasible` per scenario.

## Honesty notes registered up front

1. This is a **replication-in-harness**, not a new result: the swarm study
   already found single-issue machine-to-machine trade under IR strikes ~0 deals
   and 96–99% of struck deals are bundles (`research/swarm/SPEC.md` C1/P1,
   `RESULTS.md`), and meridian's A1 found price-only leaves a bundle surplus gap.
   NX re-runs the deal-FORMATION question on the checkout-shaped protocol itself.
2. All policies are **scripted/deterministic** — no LLM, no learned agents. The
   arms measure PROTOCOL EXPRESSIVENESS (what deals the message set can reach),
   not agent cleverness. A cleverer LLM buyer cannot make price-only express a
   qty/ship_date trade the message format forbids.
3. The generator is neutral (union of meridian's own ranges). If the kill fires,
   it is reported as a legitimate outcome, with the numbers, in RESULTS.md.

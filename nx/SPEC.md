# SNHP-NX/1 — the Missing Layer

*An open, host-neutral extension that turns a checkout-shaped agent-payment
protocol into a bundle-capable negotiation, with a receipt hook for attestation.
Written to be cited and implemented by a third party without this repository. No
marketing: every claim is either a cross-referenced measurement or a MUST/RAISE
rule an implementation can check.*

- **Protocol id:** `snhp-nx/1`
- **Status:** draft, reference implementation in `nx/protocol.py`
- **Conformance:** `nx/test_nx.py` is a portable suite; a third-party
  implementation runs it against its own classes via a small interface shim
  (documented in that file's module docstring).

---

## 1. Motivation

Agent-payment protocols in the ACP/AP2 mold are shaped like a checkout: a cart or
RFQ resolves to a fixed price, and the buyer agent's only real move is to pay or
not. Two issues that trade off against each other — quantity against delivery
date, scope against price — cannot be moved in one message, because the message
format has one negotiable number in it.

What that costs is measured, and the measurement is narrower than the claim this
spec originally rested on. We ran three arms over 240 seeded procurement
scenarios on a checkout-shaped host protocol (`nx/experiment.py`; the arms are
take-it-or-leave-it checkout, price-only haggling with the round cap lifted to 8,
and full NX package proposals). The result:

- **Package deals raise realized joint surplus.** NX captures **0.928** of the
  oracle joint surplus, against **0.889** for price-only haggling and **0.880**
  for plain checkout — **+3.9 points** of the achievable pie over the best
  price-only arm, on the same scenarios and the same utility functions. Price
  splits a pie; only a package changes its size.
- **In constrained regimes, bundling is load-bearing for the deal EXISTING at
  all.** Where deadlines are tight and requirements conflict, price-only
  recovers just **0.696** of NX's deal formation — roughly 30% of the
  mutually-beneficial trades are unreachable without moving more than price.
- **A checkout-shaped protocol can express neither.** Not the surplus gain, not
  the constrained-regime deal: both require proposing a different package, and
  there is no field for one.

What we do NOT claim, because our own pre-registered experiment killed it: that
bundling is necessary for machine trade to happen at all. On a neutral mix of
procurement scenarios a price ZOPA usually exists at the seller's quoted terms,
and cheap price-only haggling reaches **94.2%** of NX's deal-formation rate — so
the pre-registered kill on deal formation FIRED. Bundling's general contribution
is surplus quality and the constrained tail, not deal existence. See §10.

## 2. Session model — a mount, not a fork

NX is an EXTENSION ENVELOPE. It mounts between the host protocol's cart/RFQ step
and its payment-intent step, and hands a settled package back to the host to pay
for. It does not replace the host's identity, transport, settlement, or dispute
layers, and a host that has never heard of NX is unaffected by two peers that
both speak it.

```
  host: RFQ / cart ──▶ [ NX SESSION ] ──▶ host: payment-intent ──▶ host: settle
                        mount           settle (agreed package)
```

- **Mount.** Either party proposes an NX session bound to a host RFQ/cart
  reference (`session_ref`) and a declared round bound `max_rounds` (I2). If the
  counterparty does not speak NX, the host proceeds unchanged (fixed-price
  checkout) — NX is strictly additive.
- **Negotiate.** The seller opens with an `NX-QUOTE` (a list schedule + an
  opening package); the parties exchange `NX-PROPOSE` full-package counters; one
  party ends it with `NX-ACCEPT` (adopting the standing package verbatim) or
  `NX-DECLINE`.
- **Settle.** On `NX-ACCEPT` the session exposes a canonical transcript hash and
  an optional signed attestation (I4); the host is handed the agreed package and
  runs its own payment-intent over it. NX itself moves no money.

The session is a pure state machine over messages. It carries no funds and no
goods; the host does. This is the same split MPX uses (protocol vs market).

## 3. Message types

A **Line** is one negotiable item: `{line_id, item, qty, ship_date, list_price,
price}`. `list_price` is the seller's listed ceiling for that exact
configuration; `price` is the proposed price for the line. A **Package** is an
ordered tuple of Lines; its total is the sum of line prices.

- **NX-QUOTE** (seller opens). Carries a **list schedule** — the seller's
  committed `list_price` for each `(item, qty, ship_date)` configuration it is
  willing to serve — and an opening `Package` drawn from that schedule. Sets the
  session's list authority for the rest of the negotiation.
- **NX-PROPOSE** (either party). A full-package counter across all issues
  (qty, ship_date, per-line price). Every line MUST be a configuration present in
  the quote's schedule, at that schedule's `list_price`, priced ≤ it (I1). Each
  NX-PROPOSE consumes one round (I2).
- **NX-ACCEPT** (either party). Adopts the counterparty's LATEST package on the
  table VERBATIM. It carries no package of its own — acceptance cannot introduce
  new terms (I3).
- **NX-DECLINE** (either party). Ends the session with no deal.

## 4. Hard invariants

A conforming implementation MUST enforce all four STRUCTURALLY — i.e. an
offending message must be UNCONSTRUCTIBLE (construction raises), not merely
rejected downstream. The reference implementation mirrors the SNHP notary's
"over-list is unconstructible" pattern (`core/notary.py`).

- **I1 — NEVER-ABOVE-LIST.** No NX message may price any line above its listed
  price. Constructing a `Line` with `price > list_price` MUST raise. Because the
  seller's `NX-QUOTE` is the sole list authority, a proposal that (a) names a
  configuration absent from the schedule, or (b) restates a line's `list_price`
  as anything other than the schedule's value for that configuration, MUST also
  be rejected. A buyer therefore cannot manufacture headroom by inventing a list.
- **I2 — BOUNDED.** `max_rounds` is declared at mount. The Nth+1 `NX-PROPOSE`
  MUST raise. A bounded session cannot be griefed into non-termination; both
  parties know the horizon up front.
- **I3 — PACKAGE-ATOMICITY.** Proposals are WHOLE packages (no per-line partial
  acceptance), and `NX-ACCEPT` adopts the standing package verbatim. Acceptance
  takes no terms of its own, so "accept" can never be a disguised counter.
- **I4 — RECEIPT-HOOK.** Every SETTLED session MUST expose a canonical transcript
  hash: `sha256` over the canonical-JSON encoding (sorted keys, no whitespace) of
  the ordered message list, prefixed `sha256:` so the algorithm is self-
  describing. It MUST also expose an OPTIONAL signed attestation field. The spec
  is **attestor-neutral**: any party may sign the transcript hash under any
  scheme. The SNHP notary (`core/notary.py`, Ed25519 over canonical bytes) is
  named as ONE conforming attestor, not a required one; `nx/bridge.py` wires it
  as the worked example.

Invariants that hold by construction are cheap to audit: a verifier re-hashes the
transcript and re-checks `price ≤ list_price` on every line, needing nothing but
the settled receipt.

## 5. Versioning

The wire `protocol` field is `snhp-nx/1`. Additions that do not change I1–I4 (new
optional Line fields, new attestation schemes) are minor and MUST be ignorable by
an older reader. Any change to an invariant or to the canonical-hash input is a
new major (`snhp-nx/2`). The transcript hash covers the `protocol` string, so a
receipt is bound to the version that produced it.

## 6. JSON wire format

Canonical encoding for hashing: `json.dumps(obj, sort_keys=True,
separators=(",",":"))`, UTF-8, hashed with SHA-256, prefixed `sha256:`.

A **Line**:

```json
{"line_id": "L0", "item": "item3", "qty": 20, "ship_date": 4,
 "list_price": 1180.44, "price": 1043.5}
```

An **NX-QUOTE** (schedule keyed by `"item|qty|ship_date"`):

```json
{"type": "NX-QUOTE", "session_ref": "rfq-8817", "round": 0,
 "schedule": {"item3|20|4": 1180.44, "item3|20|3": 1291.02, "item3|12|2": 742.10},
 "package": [{"line_id": "L0", "item": "item3", "qty": 20, "ship_date": 4,
              "list_price": 1180.44, "price": 1180.44}]}
```

An **NX-PROPOSE** (buyer counters to a faster, smaller, cheaper package):

```json
{"type": "NX-PROPOSE", "session_ref": "rfq-8817", "round": 1, "party": "buyer",
 "package": [{"line_id": "L0", "item": "item3", "qty": 12, "ship_date": 2,
              "list_price": 742.10, "price": 690.0}]}
```

An **NX-ACCEPT** (seller ratifies the standing package — no package field):

```json
{"type": "NX-ACCEPT", "session_ref": "rfq-8817", "round": 2, "party": "seller"}
```

An **NX-DECLINE**:

```json
{"type": "NX-DECLINE", "session_ref": "rfq-8817", "round": 2, "party": "buyer",
 "reason": "no package clears our walk-away"}
```

A **settled receipt** (I4 hook):

```json
{"protocol": "snhp-nx/1", "session_ref": "rfq-8817",
 "agreed_package": [{"line_id": "L0", "item": "item3", "qty": 12,
                     "ship_date": 2, "list_price": 742.10, "price": 690.0}],
 "transcript_hash": "sha256:9f2c…",
 "attestation": {"scheme": "snhp-notary/2", "sig": "…", "pubkey_fpr": "sha256:…"}}
```

`attestation` is `null` when the session was not attested.

## 7. Mapping to MPX v1 (worked example)

MPX v1 (`meridian/protocol.py`) is a median-2026 checkout-shaped protocol: RFQ →
QUOTE(price, qty, ship_date) → COUNTER(price′) ×≤3 → ACCEPT. Its `Counter`
dataclass has a `price` field and NO qty/ship_date field, so a bundle counter is
structurally inexpressible; qty and ship_date are take-it-or-leave-it. That is
exactly the checkout shape NX mounts on.

`nx/bridge.py` mounts an NX session where MPX would run its price-only counter
loop:

- **RFQ → schedule.** From an MPX-shaped RFQ (item, need qty, need_by,
  unit_value, urgency) and a supplier (cost curve, capacity, expedite,
  inventory, markups), the seller policy builds an NX list schedule over a grid of
  `(qty, ship_date)` configurations, each `list_price = supplier_cost(q,d)·(1+
  markup)` — the SAME cost function MPX's market scores trades with
  (`meridian/agents.py`, the single source of truth). The opening `NX-QUOTE`
  package is MPX's own quoted config (full qty at the natural lead) at list.
- **Counter → package.** Where MPX would send `Counter(price′)`, the buyer policy
  sends an `NX-PROPOSE` that moves qty and ship_date as well as price, chosen by
  the engine's `gt_negotiate_bundle` logrolling tool over the schedule. A faster
  ship_date costs the seller an expedite surcharge (higher list) but is worth
  more to an urgent buyer — a real cross-issue trade MPX's price-only counter
  cannot make.
- **Settle.** On `NX-ACCEPT`, the receipt's transcript hash + optional notary
  attestation is handed back; an MPX market would run its optimistic settlement
  over the agreed package.

MPX's own `Counter(price)` is the degenerate NX package where qty and ship_date
are pinned to the quote — so NX is a strict superset of MPX's negotiation surface,
which is why the deal-rate comparison in `experiment.py` is apples-to-apples on
the same RFQs.

## 8. What NX does NOT do (scope)

- NX moves no funds and holds no goods; the host settles the agreed package.
- NX does not verify the seller's cost curve or the buyer's valuation. It bounds
  and records the negotiation; it does not police whether a list price is "fair."
- I4 gives an attestable transcript, not trustless settlement. Attestation proves
  WHAT was agreed and that no line priced above list; it does not prove delivery.
  Delivery/escrow is the host's problem (cf. MPX's A5-ii attestation-gated
  settlement, a separate hook).
- Priority INFERENCE inside `gt_negotiate_bundle` is a weak add-on (the tool's own
  caveat, r≈0.3); the reference bridge does not rely on it (it passes no counter-
  offer history), so NX's measured deal formation comes from bundle
  EXPRESSIVENESS, not from out-guessing the counterparty.

## 9. Open questions (flagged for the founder)

- **OQ1 — list authority under re-quote.** I1 makes the seller's `NX-QUOTE` the
  sole list authority for a session. A long-lived cart where the seller
  legitimately re-prices (inventory moved) needs a re-quote message; v1 handles
  this only by declining and re-mounting. Is an in-session `NX-REQUOTE` (bounded,
  monotone-down to preserve I1's meaning) worth a minor version?
- **OQ2 — multi-seller packages.** v1's schedule is single-seller (one list
  authority). Cross-seller bundles (the broker/marketplace case) need either a
  marketplace as the list authority or per-line authorities. Out of v1 scope;
  flag whether the notary's per-line receipts already cover it.
- **OQ3 — attestation timing.** I4 attests the SETTLED transcript. Some hosts
  will want a pre-commit attestation (bind the package before payment-intent).
  Trivial to add as a second hook; confirm the host flow that needs it.

## 10. Evidence

The numbers in §1 come from a kill registered BEFORE the experiment was written
(`nx/PREREG.md`) and reported as it landed (`nx/results/RESULTS.md`, raw records
in `nx/results/experiment.json`). Both documents ship with this spec. Regenerate
everything with:

```
python -m nx.experiment                        # 240 seeded scenarios, deterministic
python -m nx.experiment --regime constrained   # the constrained regime in (b) below
python -m pytest nx/test_nx.py -q              # conformance suite
```

**What was registered.** KILL-NX, bidirectional, on deal-formation rate: if
price-only haggling (8 rounds, quantity and date frozen) reached ≥ 80% of NX's
deal-formation rate, then bundling is not structurally necessary and NX is a
feature, not a standard. Reverse direction: if NX's deal formation was not
materially above plain checkout (< 1.10×), the extension adds nothing and also
dies. Thresholds frozen in advance; the verdict is computed mechanically.

**What fired.** The forward kill. On the neutral scenario mix, deal-formation
rates were checkout **0.908**, price-only haggling **0.942**, NX **1.000** —
price-only reached **94.2%** of NX, above the 0.80 bar, so the deal-existence
claim died. The mechanism is legible: 226 of 240 scenarios already have a price
ZOPA at the seller's quoted configuration, so price alone closes them.

**What survived, and is what this spec rests on.** (a) Surplus: NX captured
**0.928** of oracle joint surplus vs **0.889** price-only and **0.880** checkout
(+3.9 points). (b) Constrained regimes: re-run on a tight-deadline,
high-urgency regime, price-only recovers only **0.696** of NX's deal formation
(167 of 240 quoted configurations feasible, against 240 of 240 feasible for some
package) — there, bundling IS load-bearing for deal existence, and the surplus gap
widens to **+25.6 points** (0.820 vs 0.564). This second run is labelled
exploratory in RESULTS.md and self-labels as not-pre-registered when run: it
locates a boundary rather than establishing a headline.

**Honesty notes that travel with the numbers.** All policies are scripted and
deterministic — the arms measure what the message set can REACH, not agent
cleverness; a smarter buyer cannot make a price-only counter express a
quantity/date trade the format forbids, nor create a ZOPA where none exists. NX's
1.000 deal rate is partly structural (a small on-time order is nearly always
feasible), though only 4 of 240 NX deals serve under 25% of the requested
quantity, so it is not an artifact of token trades. The scenario generator draws
from the union of the host protocol's own published parameter ranges, not a set
tuned to make the price-only arm fail.

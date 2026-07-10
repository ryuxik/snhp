# The supply side — the MIRROR of the buyer's agent (task #64)

*2026-07-10. The supply side is built as the structural MIRROR of buyer/: a
venue's procurement is a `BuyerAgent` where the VENUE is the buyer and a SUPPLIER
is the `Merchant`. buyer/ was written merchant-agnostic (it talks only to the
`Merchant` protocol), so a supplier is just another Merchant — one that sells
cases with route / window / terms / spoilage structure. This effort REUSES the
buyer machinery; it does not reimplement shop / commit / coordinate / frontier /
regret. Every delta carries a 95% CI; no win is claimed when a CI includes zero.
Pairing is keyed on identity (seed × week × relationship), never on policy. No
LLM is invoked anywhere — every number is byte-deterministic on the seed.*

Rerun:

```
python3 -m pytest wholesale/tests/test_supply.py -q          # 15 tests
python3 -m block.runner --wholesale --procurement flywheel \
    --venues vend,bodega,boba,bakery --days 30               # endogenous block
```

Files: `wholesale/supply.py` (SupplierMerchant + ProcurementAgent),
`wholesale/block_supply.py` (the sea of suppliers + endogenous COGS),
`wholesale/flywheel.py` (S3 + S4), `wholesale/tests/test_supply.py`,
`wholesale/results-supply.json`; `buyer/merchant.py` (Quote gains the mirror
fields `u_buyer`/`d_buyer`); `block/venues.py` (`EndogenousDawn`) +
`block/runner.py` (the `--procurement` wire).

---

## S1 — the supply interface: SupplierMerchant + ProcurementAgent

`SupplierMerchant` (mirror of buyer's `VendMerchant`) wraps ONE wholesale
(wholesaler, venue) relationship-week. Its `quote()` runs the REAL multi-issue
engine — `wholesale.scenario.nash_deal` over price × window × case-size × terms ×
spoilage against the event-consistent disagreement — and maps the `Deal` onto a
`buyer.merchant.Quote`. Route density is a SHARED `Schedule` per wholesaler,
handed to every venue it serves (the block's SECOND cross-venue coordination
market, mirroring the resident cluster: a stop booked for one venue is a cheap
drop for the next).

`ProcurementAgent` IS `BuyerAgent` with the venue as buyer. It discloses the
forecast honestly, accepts the Nash deal iff it beats the venue's no-deal EVENT
(rate-card order or the Jetro cash-and-carry run), and is NEVER worse off than
that event — the mirror of the buyer's "never worse than the sticker." The
value-model mismatch (the consumer's value is linear-decay `bundle_value`; a
venue's value is a NEWSVENDOR) is bridged the way the Quote already bridges the
merchant side: the adapter carries the venue-side utility on the Quote
(`u_buyer = deal.u_v`, `d_buyer = deal.d_v`), so the agent grades a deal without
re-entering the supplier. The `Supplier` protocol extends `Merchant` with one
method, `no_deal_surplus()`, because a newsvendor fallback is not a linear-bundle
walk-away.

### Reproduces wholesale/ to the cent (the S1 contract)

Driving the whole block-week through `ProcurementAgent × SupplierMerchant`
(venues negotiating their supplier portfolio, the truck `Schedule` shared per
wholesaler in route order) reproduces `wholesale.run.run_week` **relationship by
relationship, to the cent, for every arm** (ratecard / nego / nego-indep):
216 relationship-records × 3 arms verified, **0 mismatches**, and the realized
route cost matches per wholesaler. The buyer machinery faithfully operates the
supplier world — the coupling rule ("the agent depends only on the Merchant
protocol") survives the tier change.

### Procurement regret is 0 — the attested result, one tier up

The supply interface is **attested by construction**: the venue's forecast is
verified at settlement, so no misreport is available and the disclosure frontier
collapses to honesty. The ProcurementAgent takes the honest Nash deal, which
dominates the no-deal event, so realized == frontier and **procurement regret is
0** (asserted for every relationship). This is exactly the buyer's B2 finding —
under an attested mechanism a truthful agent sits AT its frontier — reproduced on
the supply side.

---

## S2 — the sea of suppliers; COGS made endogenous

Each of the four wholesale-calibrated venues holds a PORTFOLIO of heterogeneous
suppliers (the concrete archetypes behind wholesale/'s three categories, mapped
per venue in `block_supply.SUPPLIER_TYPES`: beverage distributor, produce/deli
purveyor, dry-goods jobber, tea/tapioca importer for boba, flour mill for the
bakery, dairy purveyor, …). Suppliers serve MULTIPLE venues, so the shared truck
is a genuine cross-venue market. `block/venues.WholesaleDawn`'s static per-venue
`cost_scale` haircut is replaced by `EndogenousDawn`, whose scale is the OUTCOME
of each venue's ProcurementAgent negotiating.

### The honest result: endogenous == static, to the cent

The endogenous per-venue COGS scale reproduces `WholesaleDawn`'s static haircut
**exactly** (max abs difference 0.0000):

| venue | static haircut | endogenous (agent stack) |
|-------|----------------|--------------------------|
| vending | 0.9052 | 0.9052 |
| boba | 0.9529 | 0.9529 |
| bodega | 0.9995 | 0.9995 |
| bakery | 0.9974 | 0.9974 |

So the block re-run does **not** move: per-venue COGS and the twin-world margin
deltas are byte-identical to the static-haircut version (verified end-to-end,
`test_endogenous_dawn_block_matches_static_block`). This is the honest finding,
not a null: **the static haircut was already a faithful reduced form of the
procurement negotiation.** What the mirror adds is not a different number here —
it is that procurement is now a FIRST-CLASS agent (frontier, regret, commit,
coordinate all apply) and that COGS can now RESPOND to demand certainty, which a
static scalar cannot. That response is S3.

*Coverage gap (documented, unchanged from WholesaleDawn): only the four venues
wholesale/ calibrates get real numbers; the other six block venues (florist,
vintage, bar, …) would need a flower-market / apparel-jobber / etc. supplier
calibration a pilot would add. Their scale stays 1.0.*

---

## S3 — the 3-tier flywheel

Agent-mediated consumer demand is CERTAIN (the demand agent controls it). That
certainty — a `Wallet.trusted_frac`, tf ∈ [0,1] — is the share of the would-spoil
variance a counterparty will BANK, and the SAME tf is spent at BOTH interfaces
(the consumer's commitment to the merchant AND the merchant's forward commitment
to the supplier). So the banked growth compounds along the chain.

### Measured in the real multi-issue engine (dollars, 8 seeds)

As the demand agent tightens the forecast (demand noise 0.15 → 0.075), the
ProcurementMarket sheds overage and prices closer to the supplier's floor:

| effect (paired, uncertain − certain) | mean | 95% CI | sig |
|--------------------------------------|------|--------|-----|
| spoilage removed | **3.77 cases/wk** | [2.68, 4.86] | yes |
| joint surplus lifted | **+$182.51/wk** | [100.7, 264.3] | yes |
| vending COGS scale lowered | **0.0129** | [0.0091, 0.0167] | yes |
| boba COGS scale lowered | **0.0063** | [0.0020, 0.0106] | yes |

In the block (30 days, `--procurement flywheel`): vending SNHP-world COGS
$2278.98 → $2250.78 (−$28.20), boba $24013.48 → $23895.04 (−$118.44); the retail
margin delta ticks up (vending Δ 11.33 → 12.27, boba 376.01 → 379.96) though the
single-seed per-day CIs overlap — the block retail lift is directional, the
engine-level COGS/spoilage effect is significant across seeds.

Honest caveat: certainty helps where the deal was ABOUT variance (vending, boba)
but at very low noise the bodega/bakery lines — whose only negotiable gain was
variance-sharing — fall below the wholesaler's don't-negotiate buffer and revert
to the rate card (scale → 1.0). The venue rationally keeps the better of
{base, certain} scale, so `flywheel_scale = min(endogenous, certain)`; the
flywheel can only lower COGS, never raise it (`test_flywheel_scale_only_helps`).

### The per-tier decomposition, and it CONSERVES

The certainty tf scales the banked spoil-avoidance at each interface; both call
the identical `coordinate` (see S4):

| tf | gA (consumer→merchant) | gB (merchant→supplier) | chain = gA+gB |
|----|------------------------|------------------------|---------------|
| 0.00 | 0.000 | 0.000 | 0.000 |
| 0.50 | 0.618 | 5.376 | 5.994 |
| 1.00 | 1.235 | 10.752 | 11.987 |

Both interface growths rise linearly with the same tf (the compounding), and the
decomposition conserves: each interface's Nash split sums to its own total, and
the chain total is exactly gA + gB (`test_flywheel_decomposition_conserves`). The
magnitudes differ (gB ≫ gA) purely because a supplier CASE ($64–83 value, $23
floor) is a bigger transaction than a consumer UNIT (~$5 sandwich, ~$0.3 floor) —
the STRUCTURE is identical, the size reflects the tier.

---

## S4 — the unification finding + the procurement monopsony audit

### COMMIT and COORDINATE are the SAME lever at BOTH interfaces

This is proven MECHANICALLY, not by analogy: every supply-side growth number
above is produced by calling the IDENTICAL buyer-side function —
`buyer.strategies.coordinate`, unchanged — with the interface's own (values,
salvage floor, spoil probability). There is no supplier-side reimplementation;
`coordinate.__module__ == "buyer.strategies"` and the two function objects are
the same (`test_the_lever_is_literally_the_buyer_side_function`). COMMIT is
`coordinate` with a cluster of one; a buying-club is `coordinate` with k members.
So SNHP is ONE mechanism (Nash bargaining with the disagreement point as the
floor, variance-reduction as the only real growth) operating TWICE on the 3-tier
chain: once at merchant⇄consumer, once at supplier⇄merchant.

### The procurement monopsony audit — PASS (pre-registered, binding)

The RealPage mirror on the SUPPLY side: a block buying-club of venues aggregating
forward demand must never extract below the supplier's participation floor
(cogs). Pre-registered checks, run through the SAME `coordinate_audit` at both
interfaces:

| check | interface A (consumer) | interface B (supplier) |
|-------|------------------------|------------------------|
| **A** coordination ≥ independent commits | PASS (Δ +0.19–0.26, CI>0) | PASS (Δ +0.91–1.18, CI>0) |
| **B** seller/supplier margin ≥ floor, even at max extraction | PASS (min margin 0.0, never below) | PASS (min margin 0.0, never below) |
| **D** over-reach (demand below floor) self-defeating | PASS (refused → spoils → less) | PASS (refused → spoils → less) |

**VERDICT: PASS at both interfaces.** The block buying-club redistributes toward
venues (at maximal push the supplier sits exactly at its cogs floor and the
venues capture ~all the growth) but **cannot go below that floor**: any sub-cogs
demand is refused, the case spoils, and total welfare falls — so a rational club
never does it. The disagreement-point discipline that stops a seller harvesting a
captured buyer is exactly what stops a venue cartel extracting a captive supplier.
The floor is load-bearing and symmetric (`test_procurement_floor_never_breached_below_cogs`).

Honest scope limit (inherited from buyer/B5): the audit tests UNIT-LEVEL
participation (per-case cogs). It does not model a supplier's FIRM-LEVEL
going-concern floor; a production audit would add one. The per-case cogs is the
correct reservation for the spoil-risk cases the commit clears.

---

## Verdicts (the honest bottom line)

1. **The mirror holds structurally.** The supply side is the buyer stack with the
   venue as buyer and a supplier as Merchant; the SupplierMerchant adapter
   reproduces wholesale/ to the cent, procurement regret is 0 (attested), and no
   strategy / frontier / audit code was reimplemented — it was reused.
2. **Endogenous COGS == the static haircut, to the cent** — the static scalar was
   already the right reduced form; the mirror's value-add is that COGS now
   responds to certainty (S3), not a different S2 number.
3. **The flywheel is real but modest and heterogeneous.** Demand certainty
   removes ~3.8 cases/wk of spoilage and ~$183/wk of dead-weight loss (CI>0), and
   lowers the variance-heavy venues' COGS (vending −1.3pp, boba −0.6pp, CI>0); the
   marginal lines don't move (buffer artifact, reported honestly).
4. **Unification is mechanical, not metaphorical.** COMMIT/COORDINATE is literally
   the same `buyer.strategies.coordinate` at both interfaces; the flywheel
   decomposition conserves; the monopsony audit PASSES at both. SNHP is one
   mechanism operating twice on the supplier ⇄ merchant ⇄ consumer chain.

Tests: 15 supply-side (`wholesale/tests/test_supply.py`), all green; the 18
wholesale, 26 buyer, and block reproducibility suites remain green
(`buyer/merchant.py`'s Quote extension is default-0.0, so the consumer path stays
byte-identical). No LLM is invoked; every result is deterministic on the seed.

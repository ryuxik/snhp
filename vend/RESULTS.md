# VEND results log

## P0 (2026-07-09) — pre-registered H1: **FAILED**, and the failure is the finding

**H1 said:** a machine running engine-computed posted prices out-earns the
same machine at static prices. **It doesn't.** Against a *competent* static
baseline (profit-optimal all-day single price per SKU), per-SKU resolving
GvR — profit objective, bid-price scarcity guard, salvage floors, hourly
crowd discrimination — **loses money**, replicated on two seeds:

| paired, 30 days | seed 20260713 | seed 7 |
|---|---|---|
| profit Δ/day (gvr − static) | **−$1.71** [−2.50, −0.93] | **−$2.07** [−2.77, −1.36] |
| consumer surplus Δ/day | +$2.41 | +$2.41 |
| units Δ/day | +2.4 | +2.0 |

Margin per unit: static $1.377 → gvr $1.308. Revenue ~flat. Spoilage $0 in
both arms (well-tuned par stocks never let the perishable lever fire).

**Mechanism (diagnosed, not assumed):** cross-SKU cannibalization plus
surplus transfer. Per-SKU pricing treats each slot's demand as separable;
in reality (and in the sim) consumers choose the best surplus across the
whole board, so an off-peak discount on chips mostly diverts buyers who
would have paid list for cola, and gives cheaper chips to buyers who would
have paid list for chips. Per-hour, per-SKU profit-max is pointwise optimal
*only if hours and SKUs are separable* — they aren't, and the diversion
externality eats the gains. The extra consumer surplus is real but it is
bought with the merchant's margin, not created.

Note the two objective-level corrections made along the way (both arms,
baseline kept strong): revenue-max → profit-max everywhere; expiring-tonight
stock prices against salvage as its opportunity cost, durable stock against
unit cost (nightly top-to-par restock ⇒ carry value = replacement cost).

**Why this sharpens the thesis instead of sinking it:** posted dynamic
pricing fails here precisely because it prices SKUs independently against an
anonymous crowd. A negotiation prices one person's *entire choice problem* —
their substitution options, their quantity curve, their outside option —
which internalizes exactly the externality that sank GvR. That is now the
sharpened, pre-registered **H2 for P1**: the A2A arm must beat *both* static
and gvr on profit while keeping consumer surplus at or above static. If it
can't, the honest conclusion is that a well-priced sticker beats invisible
negotiation at a vending machine, and we publish that.

**Caveats for readers who want to attack this (please do):** the operator
here is unrealistically competent (profit-optimal list prices, well-tuned
pars, true demand model — the last is *favorable* to the dynamic arm and it
still lost); demand has no day-level shocks, so there is nothing for an
adaptive policy to react to. Real-world dynamic-pricing value often lives in
exactly those miscalibrations. A demand-shock arm (static can't react;
learning policies can) is a candidate P4 extension.

Reproduce: `python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr`

## P1 (2026-07-09) — brokered A2A: H2 not yet, H3 emphatically yes

The A2A arm quotes the Nash bargaining point over the enumerated outcome
space (item × quantity × price ladder), on verified disclosures from both
sides, with the machine's disagreement point = its sticker counterfactual
for THIS buyer. Built in three acts, each diagnosed from the paired runs:

**Act 1 — naive bilateral Nash loses catastrophically** (profit −$22.9/day,
CS −$44.5): early bargain-hunters drained stock in multi-unit bundles at
near-cost; the lunch crowd hit empty slots (stockouts +68%, walk-outs 2×).
The per-deal guarantee `u_machine ≥ d_machine` says nothing about the
*future* buyer the deal starves.

**Act 2 — shadow pricing fixes the drain, not the gap** (profit −$11.0/day,
CS −$12.1): each quoted unit now carries its opportunity cost — units within
expected rest-of-day list demand are worth list margin to keep, only excess
is cheap to move. Stockouts drop *below* static. The remaining gap is the
most instructive bug of the day: `neg_machine_gain` (the machine's believed
surplus vs. its counterfactuals) totals **+$548** while realized profit is
**−$329**. The demand forecast behind the shadow price assumes a static
world; in the A2A world later buyers also negotiate, so the "someone will
buy this at list later" counterfactual partially never happens. The
mechanism invalidates the model that prices it — the Lucas critique, in a
vending machine.

**H3 — the attestation moat, quantified (clean, monotone, tight CIs):**
holding the mechanism fixed and letting a share of buyer agents run the
anchoring attack (understate WTP, claim a free outside option):

| liar share | machine profit Δ/day vs all-honest | CS Δ/day |
|---|---|---|
| 25% | **−$4.14** [−5.09, −3.20] | +$7.26 |
| 50% | **−$9.26** [−10.68, −7.83] | +$16.75 |
| 100% | **−$21.55** [−23.11, −19.99] | +$40.75 |

Every dollar the machine loses lands in the liars' pockets. A merchant
adopting brokered negotiation without verified disclosure bleeds
monotonically in the share of adversarial agents — attestation is not a
compliance feature, it is the difference between a mechanism and a coupon
exploit. (`vend/liar-sweep.json`; the discount surface liars attack is
excess/expiring stock — shadow pricing holds scarce stock at list for
honest and liar alike.)

**The emerging meta-result (pre-registering P1.5):** against a
perfectly-calibrated sticker in a stationary world, there is almost no
surplus for ANY dynamic mechanism to find — we built the static baseline at
the profit ceiling by construction, and every dynamic arm has now paid for
information it didn't have. The honest next experiment asks *when does
negotiation pay*: introduce (a) day-level demand shocks, (b) miscalibrated
list prices (±20%), (c) oversupplied pars — the conditions real retail
lives in. Pre-registered expectation: static degrades with miscalibration
while A2A (which observes each buyer directly) does not; if that's wrong,
we say so.

Reproduce: `python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr,a2a`
and `--arms a2a,a2a-liars25,a2a-liars50,a2a-liars100`.

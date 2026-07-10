# Neighborhood-operator calibration — West Village vs Greenpoint

*2026-07-10. Operator-level realism from two fierce-competition NYC
neighborhoods, from three research sweeps (food-bev, retail, services; banked
in scratchpad/calib/nyc-operator/). Companion to CALIBRATION-TARGETS.md: that
file fixed aggregate benchmarks; this one adds how successful owners actually
run these businesses, and the neighborhood dimension. Every claim in the banked
files is flagged [HARD]/[TRADE]/[ANEC]/[EST].*

## THE master finding: rent is the missing variable, and it's the pitch

Across all ten businesses the single highest-value realism gap is the same:
**we have no rent line, and rent is the crushing fixed cost these owners cannot
escape.** NYC food/retail runs rent at **~2–3× the healthy 5–10%-of-revenue
band** — bakery ~28%, boba ~21%, bodega ~13–20%, WV boutique 50–75% — against
thin 7–15% net margins.

**West Village vs Greenpoint is a clean ~2–5× natural experiment on $/sqft:**

| corridor | $/sqft/yr | ~800 SF → $/day |
|---|---|---|
| WV prime (Bleecker/Hudson) | $150–250 (peak $332) | ~$440–530 |
| WV boutique (Bleecker retail) | $200–550 | — |
| Greenpoint (Manhattan/Franklin) | $75–120 | ~$200–250 |

Two mandatory changes: (1) **rent becomes a per-neighborhood parameter**
(WV ≈ 2–2.5× Greenpoint), added as a fixed occupancy cost; (2) **report the
engine's lift as "% of the rent line," not just $/day** — that's the number
the owner feels, and it's why a few points of margin reads as "pays N% of your
rent." This makes the block's whole scarcity thesis literal and is the single
most persuasive framing the pitch has. It also gives the twin-neighborhood
block its economic engine (WV = high-rent buy-thin-hold-price; Greenpoint =
lower-rent value tier).

## The three missing high-margin lines (each an addressable surface we omit)

1. **Bakery has no café.** The highest-margin (70–80% gross) and often
   highest-volume line — coffee (latte $6–7.50, drip $3–5) — is absent.
   Add it (drip $3.75/cost $0.55, latte $6.50/cost $0.75).
2. **Florist has no subscription line.** Profitable florists get **40–66% of
   revenue from recurring subscriptions/corporate** (Scotts lists a $375
   subscription). Natural multi-issue bilateral turf; would raise the services
   share the services-tier build already found dominant.
3. **Bodega's real revenue is ~80% lotto + cigarettes** (regulated, fixed
   margin) — which we omit, and *should*. The engine's honest lane is the
   ~20% prepared-food/grocery tail owners actually control. **Pitch language
   correction: "we optimize the food/grocery margin," NOT "we lift bodega
   revenue."**

## Per-business calibration changes (with the sim parameter)

**Bodega** (`block/calibration.py`): chopped-cheese cost $3.20→$3.80 (2025 beef
$6.12/lb record) + add beef-shock lever; BEC $6.75→$5.75 (WV-premium cell keeps
$6.75) + a liquid-egg reformulation tactic ($4.99); tx/day dial (WV busy ~550,
Greenpoint quiet ~300–400). Model 550 as busy-corner only.

**Boba** (`block/calibration.py` + `boba/world.py`): classic milk tea
$6.25→$5.25 value cell (real base $4.90–5.50 at Gong Cha Greenpoint/Kung Fu;
keep $6.25 as WV premium); toppings $0.85–1.25 → $0.50–0.75 value tier (costs
accurate); daily cups 260 = standard, add busy-corner ~400–450. **CONFIRMED,
don't touch:** tapioca 4h life = BATCH_LIFE_TICKS 24 exactly; peak 14–19 (60% of
sales in the 2–6pm window); ~78% gross/cup. Capacity 1.5 cups/min is fast-end
(fine for pre-brewed).

**Bakery** (`bakeshop/calibration.py`): croissant $4.75→$5.75–6.00 (Dominique
Ansel $6) + specialty ~$8 SKU (Radio Bakery); sourdough cost $2.60→$3.80 (bread
gross should be 50–60% not 71%); add the café line (above); model the
**graduated same-day markdown ladder** (−10–20% near close → deeper last hour +
Too Good To Go ~−66%) instead of only the single day-old −50% cliff — that
same-day ladder is the broker's genuine lane. CONFIRMED: bake-wave
(MINIBAKE_HOUR 14), waste 4–10% target.

**Fashion boutique** (`fashion/`): make **buy-depth a first-class experiment
axis** — thin ≤40-unit capsules got **+32% full-price 30-day sell-through** vs
100+ buys; this dominates the pricing delta and IS the WV playbook (buy thin,
hold price). Add a depth-scale knob. COST_FRAC 0.35→0.40–0.45 (a
wholesale-buying boutique is 55–60% GM, not DTC 65%). Markdown ladder, returns
grid, sell-through targets all VALIDATED — keep.

**Vintage** (`vintage/`): CONNECT_PROB 0.0015 (ThredUp 2.3%/day) may run hot for
a physical rack — add a slower "physical store" cell (~1%/day, median ~65 days).
**The offer/counter engine + huff 0.58 is archetype-specific** (LES/flea/dealer
haggle) — NOT curated Greenpoint (Awoke) or WV fixed-price shops where the
**markdown ladder is the lever, not haggling**; label it, the bilateral win is
smaller in fixed-price neighborhoods. MARKDOWN_AGE 30/FACTOR 0.80 VALIDATED
(consignment standard). MARKUP_MU 3.2 undershoots designer vintage ($175–500+).
Note: WV is not vintage-dense (that's EV/SoHo); Greenpoint's Franklin St is.

**Florist** (`bakeshop/`): DELIVERY_REF_FEE $14→$22–28 (real WV $20–35);
**add the subscription line** (above); arrangement anchors VALIDATED exactly
(TJ Flowers hand-tie $85/vase $125/gift $175); down-weight the walk-in-clearance
slice in `_blend` (real WV walk-in is mostly full-price arranged, not
clearance).

**Barber** (`slots/`): BARBER_CUT_PRICE $38→$42–70 (WV Kinsman $70, Greenpoint
Otis&Finn $42, Land of Barbers $60–70). No-show two-regime (12% vs 4%) and
util 62% VALIDATED (Squire 13.9M appts); deposit *fee* should be 25–50% of
service ($10–35 hold, not a token). **Enforcement (card-on-file) not reminders
kills no-shows** — the deposit is the incumbent negotiation mechanism.

**Bar** (`slots/`): Sat-heavy curve + Sat-17:00 +40% peak VALIDATED (Union:
Sat >25% of week, HH checks +40% vs 10pm). BAR_COCKTAIL $21.67 defensible;
**BAR_BEER $12.19 is HIGH** (real $9–11) — flag it as a mechanical anchor
output. New mechanism to consider: **happy-hour dwell asymmetry** — early
guests hold a seat >140 min vs ~30 min late, so flat BAR_DRINK_TICKS=3
understates early-crowd occupancy (and early guests are higher-WTP AND
stickier — cuts against pure seat-turn logic).

**Parking** (`slots/`): occupancy 68–69% VALIDATED (CBD 60–85%); WV day $25–41
reservation supports PARKING_DAY_MAX 45; Greenpoint lower (~$25–35 day). NYC DOT
already time-prices Greenwich Village meters ($5 peak/$3.50 off-peak) — dynamic
pricing is real, not hypothetical; operators run commuter/weekend/event/
overnight as distinct products (SpotHero IQ +40–76%). Don't double-count
facility-substitution elasticity (already in PARKING_HASSLE).

**Vending** (`vend/`): 7–8 vends/day + smart-store P90 VALIDATED. The
load-bearing finding: **vending is a captive-audience business, not footfall** —
a machine within 50m of a bodega underperforms, and in WV/Greenpoint the bodega
is ~30s away, so **walk cost should be LOW and BODEGA_MARKUP modest — the
machine wins only on newly-created surplus, exactly the disagreement-point
fix.** `traffic_scale` should encode captive dwell, not sidewalk headcount.

**Wholesale** (`wholesale/`): PUBLISHED_TERMS (cod/net15) + net-30 as negotiated
credit STRONGLY VALIDATED (net-30/45 is for chains, not independents); delivery
windows + recv_penalty + route density (STOP_COST/DROP_COST) + coordination =
85–97% of gain all map to real DSD/broadline economics. **Small shops can't
self-coordinate sourcing — that route-consolidation gain exists but no mechanism
lets a block capture it; the broker fills exactly that gap.** Test
JETRO_PRICE_FRAC 0.80–0.90 (cash-and-carry runs 10–30% under delivered).

## The positioning law: where owners already solve it vs the broker's lane

The most important qualitative finding, and it protects our honesty: owners
already solve several problems, and the engine must not claim to invent them.

- **Already solved by owners** (engine shouldn't claim): peak load → *staffing*
  (2–3 at boba peak); retention → *app loyalty* (15-stamp punch cards ≈ 7%);
  end-of-day clearance → *Too Good To Go* + day-old shelf + repurposing;
  no-shows → *card-on-file* (<1%); parking segmentation → operators *already*
  run commuter/event/overnight products.
- **The broker's genuine, un-solved lane:** (1) **dynamic same-day markdown
  timing/depth** (bakery near-close ladder; nobody optimizes when/how-deep
  per-item on remaining-hours × remaining-stock); (2) **off-peak demand
  smoothing** (boba: nobody dynamically discounts the 10am–2pm trough to shift
  the 60%-in-4-hours peak — the cart/pickup-slot lever); (3) **cross-shop
  procurement coordination** (the route-consolidation gain no single small shop
  can capture); (4) **buyer-heterogeneity capture** at the services venues
  (arrangement/event/delivery) the standalone builds already proved.

The honest pitch is narrower and stronger for it: we optimize the levers owners
*don't* already have a tool for, framed against the oversized rent line.

## Top priorities for the recalibration-v2 wave

1. **Add a rent line + make it per-neighborhood** (WV ≈ 2–2.5× Greenpoint) and
   report lift as % of rent. Highest value; touches every venue + the block +
   the "engine pays N% of rent" pitch.
2. **Add the three missing margin lines** (bakery café, florist subscription,
   bodega vice-revenue framing) — each an addressable surface we currently omit.
3. **Fashion buy-depth as an experiment axis** (thin-buy +32% sell-through IS
   the WV playbook) — likely a bigger lever than pricing policy.
4. **Bakery same-day graduated markdown ladder** (the genuine broker lane) vs
   the current day-old cliff.
5. **Price corrections:** boba value cell $5.25, croissant $5.75–6, barber
   $42–70, bar beer flag, sourdough/chopped-cheese costs up.
6. **Label archetypes honestly:** vintage haggle-culture vs fixed-price
   neighborhoods; the boba premium vs value tier; the bodega addressable tail.
7. **Bake the positioning law into the whitepaper:** enumerate owner-solved
   levers vs the broker's four genuine lanes, so the claims are scoped to what
   owners can't already do.

*Sequencing: this is recalibration-v2 — run it AFTER the current wave
(vintage/fashion timeline, block adapters, buyer subsystem) lands, and fold the
rent line into the buyer-block convergence (#62) so the block's per-venue
deltas read against real occupancy cost.*

# B7 RESULTS — the business-model ANTAGONISM test (buyer/ ⇄ block/ converged)

*2026-07-10. Task #62. The block modelled PASSIVE-WTP consumers (a draw that
accepts or declines a single brokered quote at its home venue). `buyer/` built
a first-class AGENT that shops / times / commits / coordinates. The block IS the
multi-merchant world that agent was built for. Here they run in ONE world for
the first time, and we settle the convergent Bezos & Musk r2 critique:*

> **the two halves of the thesis are antagonistic.** The buyer agent, working as
> designed, competes merchant margin toward the floor (shop = pure TRANSFER —
> buyer/RESULTS.md B3); merchant gain-share needs merchant margin UP. They pull
> opposite ways and had **never been run in one world.** #62 decides whether the
> business model is internally consistent.

Committed artifact: `block/results-b7.json`. Rerun:

```
python3 -m block.agentdemand --days 30 --seed 20260710 --regulars 25 \
    --n-split 4000 --out block/results-b7.json
python3 -m pytest block/tests/test_agentdemand.py -q     # 17 tests
```

Rigor (binding, honored): every twin shares the seed, so the population stream
is byte-identical across regimes — the per-day margin diffs are paired treatment
effects, block-CI on 5-day blocks (fashion/bar on 7, exactly as B5). No LLM is
invoked. The `agent_demand="off"` default is byte-exact against every committed
passive artifact (asserted: `test_agent_demand_off_is_byte_exact`), so this is a
strictly gated overlay — the passive column below reproduces B5 to the cent.

---

## What "agent-mediated" means here, mechanically

The SNHP-world street shopper (home vending or bodega) stops being a single-quote
accept/decline and becomes the buyer's agent (`resolve_shopper_agentic`):

- **SHOP** — both brokered merchants (vending *and* an adopting bodega) quote;
  the agent takes the best. The shipped `buyer.strategies.shop` primitive.
- **BERTRAND** — the agent plays them off: each merchant re-quotes against the
  RIVAL'S CREDIBLE AT-FLOOR THREAT (a merchant prices to its own `c_eff` to win
  a sale rather than lose it), then the venue's own symmetric-Nash split works
  the residual. This is the cross-merchant competition the critique turns on —
  the endgame `buyer/RESULTS.md`'s no-cross-buyer-competition assumption deleted.
- **COMMIT / COORDINATE** — forward-demand contracts and resident clusters on
  would-spoil stock, measured with `buyer.strategies` verbatim (below).

Everything settles through the committed venue helpers, so stock, spoilage and
every conservation law behave exactly as the passive path (asserted:
`test_agent_twin_conserves_money_and_units`). Agents touch ONLY the vending/bodega
street lane; the other eight storefronts are byte-identical to the passive twin
(`test_agents_touch_only_the_street_lane`) — they carry no same-good competitor,
so "shop" is undefined there and their own timing/offer agency already lives in
their SNHP arms (B5).

The ladder **passive → adopt → agent(bertrand)** decomposes the effect additively
(asserted: `test_transfer_growth_decomposition_sums`):
`Δmargin = d_surface (bodega gains a brokered arm) + d_transfer (competition)`.

---

## A. THE per-venue merchant-margin table (passive vs agent-mediated), $/day

30-day ten-venue twin, σ_cal 0.15, honest anchor, 25 regulars. The **passive**
column is byte-identical to B5 (the committed block). **transfer** =
agent−adopt (pure competition); **HUD** = SNHP margin − sticker margin (the
"merchants earned" counter's per-venue contribution).

| venue      | sticker | passive(B5) | adopt   | agent   | Δmargin agent−passive (CI95)   | transfer (competition) | HUD passive | HUD agent |
|------------|--------:|------------:|--------:|--------:|--------------------------------|-----------------------:|------------:|----------:|
| **vending**|  135.54 |      138.95 |  131.56 |  131.56 | **−7.40** [−9.19, −5.61]       |  **0.00** [0, 0]       |      +3.41  | **−3.98** ⁻ |
| **bodega** | 2992.00 |     2986.45 | 3183.47 | 3159.65 | **+173.20** [163.77, 182.63]   | **−23.82** [−26.8,−20.9]|     −5.55  |  +167.65  |
| boba       | 1022.30 |     1358.75 | 1358.75 | 1358.75 | 0.00 (no competitor)           |  0.00                  |    +336.45  |  +336.45  |
| fashion    | −435.27 |     −414.89 | −414.89 | −414.89 | 0.00                           |  0.00                  |    +20.38   |  +20.38   |
| bakery     |  473.54 |      659.52 |  659.52 |  659.52 | 0.00                           |  0.00                  |   +185.99   | +185.99   |
| florist    | −442.44 |     −234.95 | −234.95 | −234.95 | 0.00                           |  0.00                  |   +207.49   | +207.49   |
| barbershop |  257.10 |      252.07 |  252.07 |  252.07 | 0.00                           |  0.00                  |    −5.03    |  −5.03 ⁻  |
| parking    | 2018.84 |     2187.96 | 2187.96 | 2187.96 | 0.00                           |  0.00                  |   +169.11   | +169.11   |
| bar        | 7734.99 |     7879.60 | 7879.60 | 7879.60 | 0.00                           |  0.00                  |   +144.61   | +144.61   |
| vintage    | −237.29 |     −224.23 | −224.23 | −224.23 | 0.00                           |  0.00                  |    +13.06   |  +13.06   |

⁻ = "merchants earned" is NEGATIVE at this venue. (barbershop's −5.03 is B5's
documented rarely-full-chair null, unrelated to agent demand; vending's flip is
the finding — next paragraph.)

### The transfer vs growth split at the two street venues (agent − passive)

| venue   | Δmargin | d_transfer (competition) | d_surface (bodega's brokered arm) | Δbuyer CS      | Δjoint          |
|---------|--------:|-------------------------:|----------------------------------:|---------------:|----------------:|
| vending | −7.40   | **0.00**                 | −7.40 [−9.19, −5.61]              | +1.22 (tie)    | −6.18 [−10.4,−1.9]|
| bodega  | +173.20 | **−23.82** [−26.8,−20.9] | +197.02 [186.4, 207.7]           | +389.58        | +562.78         |
| **street total** | **+165.80** | **−23.82** | **+189.62** | **+390.80** | **+556.60** |

**Read the street total, not the per-venue joint.** The per-venue Δjoint is
polluted by MIGRATION: bodega's new brokered arm pulls marginal buyers off
vending (vending "loses" $6/day of joint that reappears as part of bodega's
+$563/day). At the street level the pie GROWS +$556.60/day and merchants earn
+$165.80/day MORE — while buyers keep +$390.80/day more. Both sides up.

---

## Does "merchants earned" go NEGATIVE anywhere under agents? — YES, at vending

**Vending's HUD flips +$3.41 → −$3.98/day** (Δmargin −$7.40, CI excludes zero).
But the mechanism is the uncomfortable, honest one: the transfer at vending is
**exactly $0.00** — competition does NOT bite it. The entire loss is
`d_surface`: bodega's brokered arm POACHES the bodega-home shoppers who used to
substitute UP to the vending machine's negotiated deal, keeping them at the
bodega instead. It is a cross-merchant GROWTH reallocation (bodega serves them
better), not a price-competition transfer. Vending, a tiny stock-constrained
lobby machine, is the collateral of a bigger, better-negotiating neighbor —
which is exactly the B0 "machine poaching the bodega's defectors" finding run in
reverse.

**No other venue's counter moves under agent demand** (the eight self-contained
storefronts have no same-good competitor). The block-total "merchants earned"
stays strongly positive: **+$32,097 → +$37,072 / 30 days** (below).

---

## Why competition barely bites — the two moats (the crux of the verdict)

The pure competition transfer is small and CONFINED to the commodity overlap.
Vending and bodega share exactly **two** goods (cola-20oz, chips); vending's
other five (energy, sandwich, fruit-cup, water, candy) have no bodega quote.
Over a day only **23 of 232** vending quotes are on overlap goods. Two moats
protect margin:

1. **Product differentiation** — the differentiated majority of each board has
   no competitor, so the rival's at-floor threat is on a *different* good the
   buyer values less. No head-to-head, no price cut.
2. **Location differentiation (the walk)** — for the overlap goods, the
   cross-venue walk cost nearly exactly offsets the thin commodity floor-edge, so
   even a vending-home buyer standing at the machine won't be undercut by a
   bodega cola at cost once the walk is counted. This is why vending's
   competition transfer is $0.00 to the cent, and bodega's is only −$23.82/day
   (its competed slice is the masses' cola/chips).

**Agent-mediation removes the QUOTE-gathering friction, not the physical walk.**
So on a realistically differentiated, spatially separated block, the buyer's
agent shopping does not compete margin to the floor.

### The A2A endgame stress — what if BOTH moats fell?

To bound the antagonism, `commodity_stress` strips both moats: it competes ONLY
the overlap goods (cola/chips) with the walk set to zero — the pure A2A world
where the agent gathers both quotes and the winner delivers, so only the raw
cost floors separate the merchants:

| commodity slice (cola/chips), walk→0 | merchant margin/day | buyer CS/day |
|--------------------------------------|--------------------:|-------------:|
| passive (single-merchant Nash)       |             207.63  |       409.10 |
| **A2A endgame (both at floor)**      |            **46.36**|    **1468.03** |

Margin is competed DOWN **−78%** (−$161/day) and buyer CS **3.6×**. But only
**2% of deals are driven to the floor** — because the two boards have DIFFERENT
floors (bodega cola cost $1.05 vs vending $1.10; chips $0.85 both), the winner
keeps its cost edge, so **aggregate margin stays POSITIVE ($46/day)** and it is
still a both-win (asserted:
`test_commodity_endgame_competes_margin_down_but_not_below_zero`). Even the worst
case does not zero merchant margin — it prices it at the *cost-advantage*, which
is what Bertrand is supposed to do.

---

## The HUD counters: friction→0, fast churn vs the human-regime passive block

30-day ten-venue HUD, passive → adopt → agent(bertrand):

| regime                                   | shoppers kept /30d | merchants earned /30d |
|------------------------------------------|-------------------:|----------------------:|
| **passive** (human regime — B5)          |        +$43,778.97 |           +$32,097.49 |
| adopt (bodega gains a brokered arm)       |        +$54,781.59 |           +$37,786.19 |
| **agent (shop + bertrand, friction 0)**  |    **+$55,502.91** |       **+$37,071.52** |

Moving the whole street from the passive/human regime to the agent-mediated
regime lifts **BOTH** counters: shoppers kept **+$11,724/30d**, merchants earned
**+$4,974/30d**. The competition step (adopt→agent) is the only place a counter
falls — merchants earned −$715/30d, the pure transfer — and it is dwarfed ~7:1
by the growth the second brokered arm creates.

The consumer-side regime numbers on block merchants (`block_regime`, n=4000,
graded vs the agent-mediated frontier $9.07/buyer):

| regime | buyer surplus | buyer regret |
|--------|--------------:|-------------:|
| human (friction $0.30, sticky to home merchant) | $4.18 | $4.88 |
| **agent (friction $0, shops both)**             | **$5.17** | **$3.89** |

Δsurplus agent−human **+$0.99/buyer**, CI95 [0.93, 1.05], significant; regret
−20%. Friction and stickiness are most of what keeps human buyers off their
frontier — the same result buyer/RESULTS.md reported, now on the block's NYC
merchants.

---

## B. The GROWTH levers keep merchant margin positive (buyer/strategies on the block)

### COMMIT — forward-demand contract on the block's would-spoil perishables

`buyer.strategies.commit_strategy` verbatim on the block sandwich/fruit-cup at
NYC salvage (p_spoil 0.40, n=4000, all commit):

| wallet state | joint growth/buyer (CI) | merchant share | ≥ floor? |
|--------------|------------------------:|---------------:|----------|
| attested newcomer (tf 0.50) | **+$2.91** [2.87, 2.94] | +$1.45 | yes (min +$0.44) |
| proven (tf 0.94, 6 kept)    | **+$5.48** [5.42, 5.54] | +$2.74 | yes |

COMMIT GROWS the pie (Δjoint CI excludes zero) and the Nash split hands the
merchant **exactly half** — its share is **never negative** (asserted:
`test_commit_grows_pie_and_keeps_merchant_margin_nonnegative`). The Wallet
compounds (tf 0.50 → 0.94 nearly doubles the banked growth). Both agents grow the
pie; the merchant also sheds payoff variance.

### COORDINATE + the buyer-side monopsony audit (the RealPage mirror)

`buyer.strategies.coordinate` on the block's scarce would-spoil sandwich, n=4000:

| K (stock) | coord growth/buyer | indep commits | Δ (coord−indep, CI) | merchant margin floor |
|-----------|-------------------:|--------------:|---------------------|----------------------:|
| 2  (1) | $2.20 | $1.86 | **+$0.34** [0.32, 0.37] | fair ≥ $0.79 · monopsony = $0.00 |
| 5  (2) | $1.92 | $1.49 | **+$0.43** [0.40, 0.45] | fair ≥ $2.26 · monopsony = $0.00 |
| 10 (5) | $2.33 | $1.87 | **+$0.46** [0.44, 0.49] | fair ≥ $7.08 · monopsony = $0.00 |
| 20 (10)| $2.35 | $1.85 | **+$0.50** [0.47, 0.52] | fair ≥ $16.05 · monopsony = $0.00 |

Coordination beats uncoordinated commits at every K (matching the scarce stock
to who values it most), and at maximal push (extraction=1.0) the merchant sits
**exactly at its salvage floor — $0.00, never below.** Over-reach below salvage
is refused and the stock spoils, so a rational cluster never does it.
**AUDIT: PASS** (asserted: `test_coordinate_monopsony_audit_passes_on_the_block`).
The disagreement-point discipline that stops a seller harvesting a captured buyer
stops a buyer cartel extracting a captive seller — symmetric, on block calibration.

---

## THE VERDICT — is there a both-win, or are the halves structurally opposed?

**There IS a both-win configuration, and it is the one that actually runs.** Under
agent-mediated block demand, merchants earn **+$4,974/30d MORE** and shoppers keep
**+$11,724/30d MORE** than the passive/human regime. The business model is
internally consistent on this block: buyer agency and merchant margin both rise.

**But be brutally honest about WHY, because the critique is half-right.** The
both-win is carried by GROWTH — the second merchant's brokered arm, perishable
clearance, commit and coordinate — **not** by the buyer's shopping. The buyer's
shopping *per se* is exactly what the critique feared: a pure TRANSFER that trims
the competed merchant's margin (bodega −$23.82/day; the frictionless commodity
endgame −78%). So the two halves ARE antagonistic in the narrow, mechanical sense
— shop competes margin down — and the reason it does not sink the model here is
that the transfer is **small and moat-bounded**, while the growth levers are large.

The antagonism is therefore **latent, not absent, and it scales with
commoditization + co-location.** Concretely:
- On a **differentiated, spatially-separated** block (this one), the transfer is
  a rounding error against the growth: consistent, both-win.
- On a **pure-commodity, co-located** block (the endgame stress — identical goods,
  no walk), shop competes margin **−78%**. Margin survives only because the two
  merchants have *different cost floors*; wherever floors converge it goes to
  zero. A gain-share billing instrument stacked on merchant *uplift* would be
  competed away there — which is precisely the Bezos r2 "who pays us" finding, now
  quantified: **gain-share on the buyer-shopping half is structurally fragile;
  bill on the GROWTH half (new/grown transactions — commit/coordinate/clearance),
  which the same experiment shows is where the durable, non-competable margin is.**

One venue's counter DID flip negative under agents — **vending, +$3.41 → −$3.98/day**
— but through bodega's brokered arm poaching its marginal substituters (a growth
reallocation across merchants), not through price competition. Small merchants
adjacent to a better-negotiating neighbor can lose under block-wide agent demand
even when the block wins; a production model owes them a participation floor, the
same one the monopsony audit already enforces on the buyer side.

---

## Honesty flags / scope limits

- **The transfer's smallness is a property of THIS calibration**, not a general
  law. It rests on vending↔bodega sharing only 2 of 7 goods and on a real
  cross-venue walk. The endgame stress is included precisely so the result is not
  oversold: strip both moats and the antagonism bites hard (−78%).
- **The Bertrand round is a single competitive best-response** (each merchant vs
  the rival's at-floor threat), then the venue's own symmetric-Nash split works
  the residual — a faithful "competition, then cooperative bargaining," not
  iterated to a pure-Bertrand fixed point. It is a lower bound on full
  convergence; the endgame arm brackets the upper bound.
- **Per-venue Δjoint is migration-confounded** (buyers move vending→bodega under
  adoption); only the street-level joint (+$556.60/day) is a clean growth number.
- **The eight self-contained venues are unchanged by agent demand by
  construction** — they have no same-good cross-merchant competitor on the block,
  so this experiment says nothing new about them; their SNHP agency (timing,
  offers, markdown) is the B5 story and is already in the passive column.
- **COMMIT/COORDINATE run on the shared-board, no-depletion model** (buyer/'s
  deliberate choice) — the split (transfer vs growth) is a per-transaction
  property that does not need depletion; the per-venue $/day table (deliverable A)
  carries the real stock dynamics.
- **Fairness caveat carried from B0/DESIGN §5**: street shoppers still carry no
  reference-price punishment — the fairness experiment remains the gate before any
  deep-discount-for-some story.

---

## Files changed / tests

- **`block/agentdemand.py`** (new): the agent-mediated street resolver
  (`resolve_shopper_agentic`, called by the runner behind the gate), the
  `BlockMerchant` adapter (block sims through the `buyer.Merchant` protocol), the
  per-venue antagonism ladder (`run_antagonism`), the A2A commodity endgame
  (`commodity_stress`), and the block-calibrated buyer arms (`block_commit`,
  `block_coordinate`, `block_regime`). CLI writes `block/results-b7.json`.
- **`block/venues.py`**: `BlockConfig` gains `agent_demand` ("off"|"shop"|
  "bertrand", default off) and `agent_friction` (default 0) — frozen-dataclass
  additions, byte-safe.
- **`block/runner.py`**: one gated branch in `run_world` (SNHP street lane →
  `resolve_shopper_agentic` when on), the config-emit gate (keys appear only when
  on), and CLI flags. The default (off) path is byte-identical — the committed
  reproducibility/determinism goldens still pass.
- **`block/tests/test_agentdemand.py`** (new): **17 tests** — byte-exact-off,
  agent-twin money/unit conservation, agents-touch-only-the-street-lane,
  transfer/growth decomposition sums, verdict reproducibility, competition-is-a-
  transfer, commit-grows-margin-≥0, coordinate-monopsony-PASS, regime-agent-beats-
  human, commodity-endgame-both-win.
- **Full suite**: `block/tests` + `buyer/tests` = **101 passed** (88 prior + 13
  new), no regressions; every committed passive artifact byte-exact.

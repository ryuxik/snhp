# B6.1 RESULTS — the shared block demand-state posterior

*2026-07-10. NETWORK.md §B.1: "the smallest network feature with the biggest
increasing-returns effect." A block-level Gamma–Poisson posterior over the
day's COMMON demand state, pooled across adopters — one venue's morning
arrivals sharpen everyone's `mult_hat`. DEMAND-STATE telemetry only (arrival
counts), NEVER price signals between substitutes. Committed artifact:
`block/results-b6.json` — rerun with*

```
python3 -m block.network --days 60 --seeds 8 --out block/results-b6.json
python3 -m pytest block/tests -q -k b6     # 8 tests
```

*Pre-registered arms (NETWORK.md §B.1): SHARED posterior (pool the adopters'
mornings) vs PRIVATE (each estimates from its own morning). 8-venue roster,
60 days × 8 paired seeds, Gamma(3,3) prior on the common day-state (mean 1).
Every day's state g_d and every morning count are drawn ONCE and both arms
consume them — the same paired variance reduction as the twin-world block.*

## The guardrail is the model, not a footnote

The posterior consumes only `{morning arrival counts m_v}` and the public
`{expected morning arrivals E_v}`; a venue's price is computed privately from
the pooled `g_hat` and never disclosed. Substitutes never see each other's
prices — enforced by construction, asserted in
`test_b6_posterior_is_pure_demand_state_telemetry`.

Gamma–Poisson conjugacy: `g_d ~ Gamma(α₀,α₀)`, morning `m_v ~ Poisson(g_d·E_v)`,
posterior mean `g_hat = (α₀ + Σ_{v∈S} m_v)/(α₀ + Σ_{v∈S} E_v)`. Pooling more
adopters shrinks the prior's weight `α₀/(α₀+ΣE)` toward zero — the estimate
tracks the block's realized morning ever more tightly. That is the entire
increasing-returns mechanism.

## Two pricing regimes — and why the audit needs both

`g_hat` only matters for pricing through a capacity/perishability channel (a
multiplicative demand shock leaves the unconstrained optimum unchanged). There
are two ways a venue can USE it, and they have OPPOSITE welfare signs:

- **discount-only** (the block's actual guardrail — every shipped SNHP policy
  can only cut off a fixed sticker): stock perishes at cost; the venue posts
  the sticker, then marks the LEFTOVER down to clear the perishable tail, with
  the markdown depth planned from `g_hat`. Price never exceeds the sticker.
- **ration** (the counterfactual the audit exists to catch): unconstrained
  yield management — a believed-busy day RAISES price to ration scarce
  capacity.

## Predictions P1 & P2 — confirmed (both regimes)

**P1 — forecast error falls with adopter count.** The SHARED posterior's mean
`|g_hat − g_d|`, by adopter count k = 1…8:

```
0.110 → 0.084 → 0.080 → 0.077 → 0.076 → 0.074 → 0.073 → 0.073
```

Monotone non-increasing, −33% from the lone adopter to the full block. Each
adopter's morning genuinely sharpens every adopter's read.

**P2 — profit per adopter rises with adopter count.** Isolated from the
changing venue mix as the SHARED − PRIVATE per-adopter profit PREMIUM (0 at
k=1 by construction — a lone pool IS its own posterior), by k:

```
0.00 → 0.82 → 0.70 → 0.98 → 1.14 → 2.04 → 2.11 → 6.40    (discount regime)
```

Rising to +$6.40/adopter-day at full adoption — increasing returns: each new
adopter makes sharing worth more to everyone.

**The free-rider vignette.** The bar opens at 15:00 and sees NO morning of its
own — under PRIVATE telemetry it prices its whole evening off the prior; under
the SHARED pool it inherits the block's morning read. Its profit: **$444.49 →
$480.91/day (Δ +$36.42, CI [30.83, 42.01])**. The venue that contributes
nothing to the signal gains the most from it — the network effect made vivid.

## THE collusion audit (pre-registered, NETWORK.md §B)

Consumer surplus under SHARED must be NON-DECREASING vs PRIVATE at full
adoption; if sharing raises consumer prices, the feature dies. Reported for
both regimes:

| regime | ΔCS (shared − private) | Δ avg price | verdict |
|--------|-----------------------:|------------:|---------|
| **discount-only** (block guardrail) | **+3.58** [2.69, 4.48] | **−0.259** [−0.30, −0.21] | **PASS** — CS strictly RISES, prices FALL |
| ration (counterfactual) | −8.36 [−10.67, −6.06] | +0.149 [0.09, 0.20] | **FAIL** — CS falls, prices rise; feature dies |

**Verdict: under the block's discount-only guardrail the shared posterior
PASSES — it lowers consumer prices and raises consumer surplus.** A sharper
common demand read lets each venue clear its perishable leftover more
precisely on genuinely slow days, so more discounted units reach the
price-sensitive tail; because the price can only ever be CUT off the sticker,
sharing cannot be turned into a price hike.

**The ration counterfactual is the whole point of running it.** If venues used
the identical shared estimate for unconstrained rationing, the audit would FAIL
— sharper demand information becomes sharper price extraction, exactly the
RealPage concern. Same telemetry, opposite welfare sign. **This is why
discount-only is the non-negotiable condition for demand-state sharing on the
block, not a stylistic choice** — it is the constraint that keeps the network
effect pro-consumer. Demand-state sharing without a discount-only pricing
constraint is not a feature we would ship.

## Honesty flags

- **Self-contained arm.** This is a pre-registered §B.1 experiment on the
  block's demand-state mechanism, not wired into the ten-venue twin (B6 is its
  own wave, per NETWORK.md's build order). The adopter roster's morning
  weights track each venue's real early curve and its session
  scale/capacity/cost/choke are block-consistent TARGETS; the load-bearing
  content is the pooling mechanism and the audit, not the exact per-venue
  elasticities.
- **The P2 premium wiggles cell-to-cell** as the adopting venue mix changes
  (e.g. adding the low-margin barber vs the high-volume bar); the robust read
  is the trend (0 → +$6.40) and the floor at 0, both asserted — not strict
  step-monotonicity (also reported, and it can dip).
- **One latent common state per day.** The model collapses the block's demand
  shock to a single g_d (a rainy Tuesday busies every storefront together);
  richer per-category states, weekday structure, and the censoring-escalator
  convergence NETWORK.md also predicts are deferred to later B6 waves.
- **The audit measures the demand-state channel in isolation.** It shows that,
  under discount-only, sharing does not raise prices — it does not model the
  full ten-venue policies' own reference-price fairness (still absent for
  street shoppers, DESIGN §5), which remains the separate gate before shipping
  any deep-discount story.

---

# B6 FLYWHEEL — the tipping sim (task #71; the whitepaper's missing Figure 1)

*2026-07-10. `block/flywheel.py`, committed artifact `block/results-flywheel.json`
— rerun with*

```
python3 -m block.flywheel --seeds 8 --pop 700 --out block/results-flywheel.json
python3 -m pytest block/tests/test_flywheel.py -q     # 10 tests
```

A MIXED block population: a fraction **φ** of consumers are AGENT-MEDIATED (the
buyer/ regime — zero friction, shops every merchant, attested disclosure,
credible forward commitment) and (1−φ) are PASSIVE (best posted board, sticky).
We sweep φ 0→1 and ask two honest questions, measured not assumed: (Q1) does the
agent's realized CONSUMER edge over the strong posted board GROW with φ, and (Q2)
is there a critical mass **k\*** above which adoption self-sustains and below which
it decays? Paired on consumer identity; the block's real NYC street population;
buyer/strategies + the committed `BlockMerchant` reused verbatim; 8 seeds × 700
consumers × 11 φ cells; a 95% CI on every edge; no LLM (byte-deterministic).

**The two flywheel channels** (both ride the B6.1 conjugate shrinkage
`α₀/(α₀+φ·info)`): more agents disclose → the merchant's calibration sharpens
(σ_cal(φ): 0.15 → 0.087 → 0.067 across φ) and forward-demand certainty shaves
procurement (COGS(φ): 1.00 → 0.96 → 0.952). Both are given their best shot — the
strong posted board RE-OPTIMIZES at the sharper estimate and lower cost as the
flywheel turns, so "inference gets its best shot" (the §2 methodology rule).

## Q1 — the edge GROWS with φ, but ONLY via coordination (the shop transfer is flat)

Per-consumer agent edge over the strong posted board, decomposed, by φ:

```
φ        0.0   0.1   0.2   0.3   0.4   0.5   0.6   0.7   0.8   0.9   1.0
E_total 0.29  0.47  0.52  0.53  0.54  0.54  0.55  0.55  0.55  0.56  0.56
E_shop  0.29  0.30  0.31  0.31  0.31  0.31  0.31  0.31  0.31  0.31  0.31
E_coord 0.00  0.17  0.21  0.22  0.23  0.23  0.23  0.24  0.24  0.24  0.25
```

- **Δedge (φ=1 − φ=0) = +$0.268/consumer, CI [0.226, 0.311] — GROWS** (CI
  excludes zero). The flywheel FORCE is real.
- **But it is entirely the COORDINATION channel.** E_shop (spot shopping +
  attestation across the two merchants) is **FLAT**: Δ_shop(φ=1−φ=0) = +$0.020,
  **CI [−0.016, +0.055] — includes zero.** The spot haggle/shop is a BOUNDED
  transfer that does not grow with penetration — exactly the antagonism finding
  (CRITICAL-ANALYSIS §10, the wholesale report-independence boundary), now
  mechanical on the consumer side. Here the shop transfer is bounded not by
  board convergence but by PRODUCT DIFFERENTIATION (the vending machine and the
  bodega sell largely different SKUs — only cola/chips overlap), so σ_cal
  sharpening barely moves it (E_shop is flat in σ_cal too, measured directly).
- **E_coord is the growth**: at φ=0 a lone agent cannot coordinate (0); once the
  agent cluster reaches ~2 members it captures ~$0.17, rising to $0.25 at full
  penetration — the buyer/RESULTS B5 matching premium (route the scarce
  would-spoil stock to the highest-value members), whose per-member advantage
  rises with cluster size. This is a DURABLE, positive-sum channel (spoilage
  avoided), the mirror of the "growth is durable" half of the antagonism read.
- **Crucially the growth is FRONT-LOADED (concave):** E_coord jumps 0 → $0.17 by
  φ=0.1 and only gently to $0.25 by φ=1. Coordination delivers most of its value
  at a *tiny* cluster (buyer/RESULTS B5: coord−indep is +$0.19 at K=2 vs +$0.26
  at K=20 — only +37% over a 10× cluster). This concavity is the load-bearing
  fact for Q2.

**The other side (merchant):** agent-mediated merchant margin per consumer is
**flat in φ** ($0.52 → $0.53 → $0.54) — adding agents does NOT drive margin to
the floor (the transfer is confined to the commodity overlap, the endgame stress
of `agentdemand.commodity_stress`). So the two-sided loop does not eat itself:
consumer surplus rises with φ while merchant margin holds.

## Q2 — there is NO robust tipping point k\*; adoption is MONOSTABLE

A consumer adopts iff its realized edge e_i(φ) beats its idiosyncratic adoption
cost c_i (the hassle/subscription of running an agent). The adoption response is
`F(φ) = (1/N)Σ_i 1[e_i(φ) > c_i]`; fixed points solve φ\* = F(φ\*); a tipping
point k\* is an UNSTABLE interior fixed point (below it adoption decays, above it
the flywheel carries it up). We map the phase diagram over BOTH the adoption-cost
median (m_c) and its heterogeneity (σ).

**Result: no tipping point at ANY (m_c, σ) with σ ≥ 0.3 — monostable
everywhere.** Every cell is either monostable-high (adoption grows to a single
high equilibrium) or monostable-low (decays to a single low one); the crossing of
`F(φ)` and the diagonal is always single and stable. The one bistable cell that
flickered at 3 seeds (σ=0.05, m_c=0.25) **vanished at 8 seeds** — it was grid
noise, not a real k\*.

**Why there is no k\* (the mechanism, not a modeling gap):**

1. **Standalone value kills the cold-start trap.** The buyer's agent delivers a
   spot edge of **~$0.30/consumer that requires ZERO other adopters** (shopping +
   attestation are unilateral). So a low-cost adopter tail *always* adopts even at
   φ=0 — `F(0) > 0`. A tipping point needs adoption to be able to COLLAPSE to zero
   below k\* (φ=0 must be a stable fixed point); the standalone edge forecloses
   that. This is GOOD news for go-to-market (no critical-mass cold-start), but it
   is exactly why the "tip-or-die" dynamics are absent.
2. **The flywheel force is front-loaded.** The only increasing-returns consumer
   channel (coordination) saturates by φ≈0.1. A tipping point needs the edge to
   ACCELERATE through a mid-φ region (a convex-then-concave S-response); a
   front-loaded concave edge cannot produce one.

Only a knife-edge combination — near-homogeneous adopters (σ ≤ 0.05, everyone
with an identical cost right at the mid-φ edge) — could manufacture a k\*, and any
realistic adopter heterogeneity erases it. **The honest verdict: the consumer-side
flywheel has a real force but no self-sustaining threshold. Adoption smoothly
finds a single stable equilibrium set by the adoption cost, not a bistable
tip.** The increasing returns that DO compound are (a) MERCHANT-side (B6.1 P2 —
profit per adopter rises 0 → +$6.40) and (b) the DATA MARKET (B6.5, below); the
consumer's own shopping edge is a flat, bounded transfer.

**The Lucas point.** The passive parameters — σ_cal = σ₀ = 0.15 (the central-cell
mis-set sticker) and full demand variance — are calibrated to the world SNHP
REPLACES, so the φ→1 end of the sweep IS the target world (every consumer
agent-mediated, the merchant near-omniscient at σ_cal ≈ 0.067). The phase diagram
says the block reaches that target not by tipping through a threshold but by a
smooth, adoption-cost-gated climb — every adopter is individually better off from
the first, so there is nothing to tip.

## Honesty flags (flywheel)

- **Self-contained arm** on the vending↔bodega street lane (the two brokered
  merchants agentdemand already wired), not the full ten-venue twin; the coord
  channel targets one scarce would-spoil perishable (sandwich). The load-bearing
  content is the edge decomposition and the fixed-point structure, not the exact
  per-SKU elasticities.
- **The shop transfer is flat here largely because the two block merchants sell
  DIFFERENTIATED goods.** In a pure-commodity block (both merchants carry the
  same SKU) the "boards converge → haggle competes away" mechanism would make
  E_shop *decline* in φ (σ_cal→0 kills dispersion) — even more anti-flywheel, not
  less. Either way the shop channel does not power a tipping point.
- **The fixed-point detector is validated on synthetic S-curves** (it DOES find a
  k\* when one exists — `test_fixed_point_detector_finds_a_tipping_point_in_an_s_curve`),
  so "no k\*" is a real null, not a blind detector.
- **The adoption-cost distribution is a free parameter**; that is why we sweep it
  in full (median × heterogeneity) rather than pick one — the null (no k\*) holds
  across the whole realistic region, and the only tipping regime is a
  measure-zero knife-edge.

---

# B6.5 DATA MARKET — calibration-for-discount (NETWORK.md §C.4; task #72)

*2026-07-10. `block/datamarket.py`, committed artifact
`block/results-datamarket.json` — rerun with*

```
python3 -m block.datamarket --seeds 400 --out block/results-datamarket.json
python3 -m pytest block/tests/test_datamarket.py -q     # 12 tests
```

The inversion that ties the whole thesis. The merchant's core problem is not
knowing its own demand curve — the MISCALIBRATION channel (μ̂ = μ·noise), the
block's headline result. A resident cluster's VERIFIED AGGREGATE disclosures ARE
that demand curve. So clusters SELL calibration: consented aggregate demand data
that shrinks the merchant's σ_cal, in exchange for a standing discount, priced by
the broker. Clean linear-demand-per-SKU model (WTP uniform[0,2μ], monopoly price
p\*=μ̂+c/2, profit/CS booked against TRUE μ), so every dollar in the
miscalibration → mispricing → recovered-value chain is decomposable. K verified
disclosures shrink σ_cal via the B6.1 conjugate shrinkage; paired on the
calibration-error direction; 400 seeds; a 95% CI on every Δ; no LLM.

## The exchange, measured (cluster size K = 2 … 100)

```
 K   σ_cal   ΔΠ (merchant WTP)     %ceiling  ΔW      share   cluster $   merchant keep
 2   0.116   1.35 [1.26, 1.44]      41%      1.26    0.14    0.19        1.16
 5   0.092   2.09 [1.95, 2.22]      64%      1.96    0.29    0.61        1.47
10   0.072   2.55 [2.39, 2.71]      78%      2.41    0.45    1.16        1.39
20   0.054   2.87 [2.69, 3.05]      87%      2.73    0.63    1.79        1.08
44   0.038   3.08 [2.89, 3.27]      94%      2.95    0.79    2.42        0.66
100  0.026   3.19 [2.99, 3.39]      97%      3.07    0.89    2.85        0.34
```

- **σ_cal shrinks with cluster data** — 0.15 → 0.026 as K grows; at K=44 (the
  building — NETWORK.md's "one board vote signs 200 households") the cluster's
  data recovers **94%** of the full miscalibration cost (the ceiling Π(0)−Π(σ0)).
- **The merchant's WTP for the data (ΔΠ) is significantly POSITIVE at every K**
  (every CI clears zero) and saturates toward the $3.28 ceiling. This is the
  merchant's recovered profit from finally knowing its demand curve — a real,
  fundable number, not a discount it resists.
- **Total welfare GROWS** — ΔW = +$1.26 → +$3.07 (all CIs clear zero): the
  exchange creates value (less mispricing), it does not just move it.
- **The split favors consumers in proportion to cluster size** — s(K)=K/(K+K0)
  rises 0.14 → 0.89, so the cluster's cut of the data value rises from $0.19 (K=2)
  to $2.85 (K=100) while the merchant always **keeps a positive share** (the
  Pareto floor, $1.16 → $0.34, never below 0).

## Is the DATA worth more than the HAGGLE?

The pre-registered comparison (NETWORK.md §C.4): the information rent EXCEEDS the
shopping transfer *which competes away as boards converge*. Two haggle regimes:

```
 K    cluster data payoff    cluster HAGGLE (monopoly)    cluster HAGGLE (competitive)
 2         0.19                     2.18                          0.00
44         2.42                    47.99                          0.00
100        2.85                   109.06                          0.00
```

- **Vs the COMPETED-AWAY haggle: the data wins at every K.** A bargaining
  cluster's transfer collapses to ~0 as competition drives boards to cost (the
  antagonism finding — CRITICAL-ANALYSIS §10). The data value does not move under
  competition. So in the competitive, agent-mediated endgame SNHP creates, the
  information rent is the ONLY consumer rent that survives — and it is Pareto.
- **HONEST SCOPE (recorded, not hidden): the data does NOT out-dollar a raw
  MONOPOLY haggle.** A cluster bargaining a monopolist down grabs far more
  ($47.99 at K=44) than it earns selling data ($2.42). **The data's edge is
  DURABILITY + POSITIVE-SUM, not raw magnitude.** The data value is second-order
  (removing σ0=0.15 mispricing recovers ~$3 vs the ~$93 monopoly rent); the
  haggle is first-order but zero-sum and transient. σ0-sensitivity (data value at
  K=44 grows ≈quadratically with how badly the merchant is mis-set):

  ```
  σ0=0.15 → ΔΠ = $3.08     σ0=0.30 → ΔΠ = $12.49     σ0=0.50 → ΔΠ = $25.75
  ```

  even at a badly-miscalibrated merchant (σ0=0.5) the data ($25.75) approaches
  but does not exceed the monopoly haggle ($44.66) — confirming the edge is not
  magnitude.

## The monopsony audit (demand-cartel, RealPage mirror) — PASS at every K

The mirror of `buyer.strategies.coordinate`'s audit, on the demand side:

| check | result |
|--|--|
| **B — participation floor** (merchant keeps ≥0 of ΔΠ at the fair split; exactly 0 at maximal extraction D=ΔΠ) | **PASS** (merchant keep $1.16 → $0.34 at fair; 0 at max, never below) |
| **D — over-reach self-defeating** (a cartel demanding D>ΔΠ breaches the floor → the merchant REFUSES → no data shared → the cluster gets nothing) | **PASS** (100% refuse at extraction 1.25×) |
| **price-floor / discount-only** (every SKU's discounted price stays ≥ cost) | **PASS** at every K |

**VERDICT: the durable, non-competable value IS the data market.** The merchant
funds it willingly (ΔΠ > 0, welfare grows, monopsony-safe), the split favors
bigger clusters, and — because the haggle competes away while the data value does
not — the information rent is what remains in the competitive endgame. The data's
superiority is qualitative (durable + Pareto + antitrust-safe), NOT that it
out-dollars a monopoly rent grab; and its magnitude scales with how badly the
merchant lacks its own demand curve, which is exactly the miscalibration channel
the whole block program is built on.

## Honesty flags (data market)

- **Self-contained analytic arm.** Linear-demand-per-SKU so the miscalibration →
  recovered-value chain is transparent; it does not run the full ten-venue
  policies. The load-bearing content is the positive-sum/Pareto structure, the
  σ_cal shrinkage, and the monopsony audit — not the exact per-SKU elasticities.
- **The data value is measured against the merchant's OWN optimum** (Π(0)), so ΔΠ
  is unambiguously recovered profit (≥0 by concavity), not a comparison against a
  moving posted baseline.
- **The competitive haggle is idealized to 0** (a rival exactly at cost). Real
  competition drives the board toward but not exactly to cost; the direction
  (haggle → small under competition, data invariant) is what is load-bearing, and
  it is the same mechanism the wholesale antagonism battery confirmed.
- **The cluster's discount is a standing per-unit markdown** priced off the
  recovered value ΔΠ; the audit checks it stays discount-only (≥ cost) but does
  not model the full reference-price fairness of the ten-venue policies (DESIGN
  §5), the separate gate before shipping any deep-discount story — same caveat as
  B6.1.

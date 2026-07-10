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

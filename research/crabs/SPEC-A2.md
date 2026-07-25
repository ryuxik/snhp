# SPEC-A2 — implementation of PREREG AMENDMENT 2

*Written 2026-07-25, after AMENDMENT 2 and BEFORE the first Phase-3 run. Every
number below was fixed before any GATE 2 or arm G–J output existed. Phase 1's
verdicts are untouched.*

---

## A2-1. Base specification

Phase 3 builds on Phase 1's **exploratory** specification (unit-level turn
dispersion), not the registered one. This is forced, not chosen: under the
registered spec the station concedes to nobody, so V5 and V6 would both be
trivially 0 and GATE 2 would be uninformative. Consequence: **everything in
Phase 3 is exploratory**, inheriting Phase 1's gate failure. Stated here so it
cannot be forgotten later.

## A2-2. The primitives, and what each is worth

Landlord types differ **only** in `Params.units`. Every behavioural difference
is derived from it in `world.size_primitives`. No value below is set per type,
and none may be tuned to GATE 2.

| Primitive | Global value | Derivation | Institution (U=200) | Mom-and-pop (U=5) |
|---|---|---|---|---|
| Risk aversion `risk_rho` | 5.0 | per-unit penalty `rho·Var/(2·U·12)`; with U independent units, CE = U·μ − (ρ/2)σ²/μ, so per unit the penalty falls as 1/U | 0.00104·Var | 0.0417·Var |
| Comp noise `comp_sigma0` | 0.25 | `σ = σ0/√U`: you learn the market from your own relets, and 200 habitats give ~90/yr against ~2 | 1.8% | 11.2% |
| Non-pecuniary keep-value `nonpec0` | 0.5 mo/yr | `×1/(1+U/10)`: you can personally know about ten tenants | 0.024 mo/yr | 0.33 mo/yr ($667) |
| Cost of raising rent `raise_cost0` | 0.6 mo | same scaling; the discomfort and risk of raising a neighbour's rent | 0.029 mo | 0.40 mo ($800) |
| Turn-cost scale `turn_scale_beta` | 1.0 | `×(1 + β/√U)`: in-house crew amortises, a small owner calls a contractor | ×1.071 | ×1.447 |
| Face-rent capitalisation `u_cap` | 50, `size_scaled_face=True` | `×U/(U+50)`: institutional portfolios are marked to an NOI multiple, five units are not | ×0.80 | ×0.091 |
| Agent bonus `agent_bonus` | 1.0 mo (arm J only) | weight `U/(U+20)`: a small owner *is* the agent. A leasing commission is commonly 50–100% of a month's rent | weight 0.91 | weight 0.20 |

`risk_rho = 5.0` is the upper end of standard CRRA estimates, justified for an
owner whose entire income is five habitats. **A first-order calculation before
running says this channel is weak**: at U=5 the risk penalty is ≈0.09 months and
its derivative offsets only ~3% of the marginal revenue of a push. We are
recording that prediction here so that the ablation in §A2-4 either confirms it
or contradicts it, rather than being read off after the fact.

## A2-3. GATE 2 — which regime each target is judged in

PREREG A2.1 does not say. Each published figure comes from a particular era, and
the mapping below is fixed **now**:

| | target | source vintage | judged in | also reported |
|---|---|---|---|---|
| **V4** mom-and-pop zero-increase share ∈ 10–30% | 18.0% | TurboTenant, ~2025–26 | **gain** | loss |
| **V5** mom-and-pop concession rate ≤ 20% | ~10% | TurboTenant, ~2025–26 | **gain** | loss |
| **V6** institutional concession rate ∈ 15–35% | 25.5% | RealPage, ~2026 | **gain** | loss |
| **V7** institutional push ≥ 3× mom-and-pop push | +10.7% vs +2.1% | NAA 2022 / TurboTenant | **loss** | gain |

V7 must be judged in the loss regime because that is where +10.7% was measured,
and because in the gain regime the institutional push is *negative*, which makes
a "≥3×" ratio meaningless rather than merely hard.

**GATE 2 is evaluated on the emergent baseline with no arm G–J mechanism
switched on**, at the empirical 39% assigned asker mix. That is the strict
reading of A2.1 ("all must fall out of the primitives above"). Because V6 is
close to the same quantity Phase 1's V1 already failed, GATE 2 is *also* reported
with arm G enabled, clearly labelled as the secondary reading — it is the
mechanism that plausibly generates institutional concessions, and hiding that
would be less honest than showing both.

## A2-4. Primitive ablation

Each primitive is switched off in turn, one at a time, from the full set. This
is the only way to know whether the hypothesised chain (risk aversion + bad comps
⇒ small pushes ⇒ nothing to concede) is the mechanism, or whether something else
is doing the work. Reported as a table before any arm result.

## A2-5. Arms G–J

- **G — MENU COSTS.** The station picks **one** increase for the whole
  portfolio, from the grid {0, 2, 4, 6, 8, 10, 12}%, by evaluating each against
  the units it actually holds. Counterers enter an exception queue of capacity
  `queue_frac = 0.15` of habitats; a reviewed unit gets the per-unit optimum
  offer *and* the concession stage; a counterer who finds the queue full gets
  neither. 15% is a working guess at how much hand-work a leasing team has
  capacity for and is swept.
- **H — INFORMATIVE ASKING.** Three populations, compared at **equal asker
  share**: `tool` (counters iff its true gain from leaving exceeds zero — a hard
  walk-away floor), `random_at` (a random trait, at whatever share the tool
  produced), `everyone`. The station holds a **counter-conditional**
  switching-cost belief, measured per population on pilot seeds, so a counter is
  informative exactly to the degree that it really is.
  **The ideal tool (`tool_noise = 0`) reads the crab's own leverage exactly and
  is therefore an upper bound, not a forecast.** A noisy variant
  (`tool_noise = 1.0` month) is run as the honest case.
- **I — SCREENING.** `ask_mode = selfselect` (counters within
  `engage_margin = 2.0` months of indifference) with the counter-conditional
  belief, against a control where the concession channel does not exist
  (`no_concessions = True`). K12 compares station cash.
- **J — AGENT WEDGE.** `agent_bonus = 1.0` month, weight `U/(U+20)`. The
  concession decision maximises the agent's objective, the opening offer still
  maximises the owner's.

Arms H and I share the self-selection machinery; they differ in the
counterfactual they are compared against. Said here so it is not mistaken for
two independent confirmations.

## A2-6. K11 is the result we want, so it is measured against composition bias

**The obvious bug**: tool-advised askers are *selected* to be high-leverage
crabs, so comparing "asker surplus" across populations compares different kinds
of crab, not different tools. Any apparent tool advantage could be pure
composition.

Guards, fixed before running:

1. **Primary metric is TOTAL crab surplus** (all crabs, asker and non-asker),
   at equal asker share. The crab population is identical across the three
   populations — only *who asks* differs — so this is composition-free.
2. The literal per-asker reading PREREG uses is reported alongside, explicitly
   flagged as confounded.
3. A **matched subgroup**: among crabs whose true leverage clears the floor,
   compare the tool population with the random population. Same kind of crab,
   different regime of advice.
4. K11 also requires the K8 externality to shrink, measured as non-asker surplus
   against the same-population `σ=0` baseline.

If (1) and (3) disagree with (2), the confound is real and K11 is reported as
not established.

## A2-7. Seeds

Unchanged: pilot `9000–9019` (now also used for the counter-conditional priors),
main `1000–1059` for institutions and `1000–1499` for mom-and-pops, held-out
`7000–…` if anything is respecified. Geometry unchanged from Phase 2:
institution U=200 × 60 stations, mom-and-pop U=5 × 500 stations.

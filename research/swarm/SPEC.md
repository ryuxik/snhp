# Multi-robot bargaining benchmark — SPEC v2

*v2 re-pinned 2026-07-14 after expert consult (review/STANDARDS_BRIEF.md,
review/ADVERSARIAL_REVIEW.md), BEFORE any v2 results were generated. v1's
headline claims did not survive review: the efficiency metric rewarded fleet
death (F1), a trivial cooperative control dominated the bargaining arm (F2),
and the single-issue ablation arm turned out to strike zero deals (F3). v2
tests the honest, narrower claims those findings left standing.*

## Positioning (changed from v1)

This is a **multi-robot mechanism benchmark**, not "swarm robotics": N=24,
full-information utilities, deterministic gridworld, and Φ reads global stock
state. By the field's own definitions (Şahin 2005 criteria; see
STANDARDS_BRIEF.md) that places this work in the **market-based multi-robot /
MAS lineage** (Dias et al. 2006, Gerkey & Matarić 2004) — which is where
snhp's actual thesis lives anyway: **self-interested agents owned by
different parties**. The swarm-scale/noise/hardware program is explicitly
future work (STANDARDS_BRIEF §5).

## Claims under test (v2)

- **C1 (necessity).** Under individual rationality (IR) with selfish Φ,
  single-issue trade between robots is infeasible — zero deals possible on
  any lone issue. Multi-issue bundling is *necessary* for any trade at all.
  (Pinned as a test invariant; F3's silver lining.)
- **C2 (sufficiency & size).** Bundled Nash-bargained deals recover a
  substantial fraction of the cooperative coordination value: on **delivered
  at fixed horizon** (the primary metric), snhp sits strictly above the
  strong non-bargaining IR-compatible world (null) and above the
  single-issue market lineage (auction), and within a quantified gap of the
  cooperative ceiling (team). That gap IS the **price of selfishness** — the
  cost of requiring every coordination step to be individually rational.
- **C3 (heterogeneity scaling).** With the mean-preserving σ dial (fleet
  means fixed; only spread grows), the snhp−auction delivered gap **grows
  with σ**. v1 could not test this (σ was confounded with poverty — M1).

## World (v0.1 physics deltas from v1)

Unchanged: 32×32 grid, two sources (16/40 Manhattan from sink), sink,
2-slot × 4/tick charger, 120 units total, 2500-tick horizon, Chebyshev-2
interaction, 25% energy transfer loss, N=24.

Changed:
- **Mean-preserving σ** (review M1): cap = 3 + σU(−2,2) [unchanged, already
  symmetric]; eff = 1 + σU(−0.5,0.5) clipped [0.5,1.5]; battery = 60 +
  σU(−40,40) clipped [10,100]. Fleet means (3, 1.0, 60) are σ-invariant —
  tested (`test_sigma_is_mean_preserving`).
- **TXN_COST is physical** (minor-7): 0.05 battery debited from each side of
  every executed deal.
- Stranding semantics documented as implemented: stranded when battery <
  RESCUE_FLOOR=5 while >1 cell from the charger (max step cost 3.0 < 5, so
  no un-strandable limbo); rescue at ≥5. Sector swaps remain physically free
  flags (known mispricing, review minor-4 — accepted for v0.1, noted).

## The arm ladder (one mechanism per rung — review M4)

| arm | = | mechanism added |
|---|---|---|
| `null` | movement policy only | — (the zero point; == v1's inert "snhp[cargo]") |
| `rules` | null + trophallaxis | altruistic threshold rescue (Moonjaita-style) |
| `auction` | rules + cargo handoff | MURDOCH-style single-issue scalar reassignment (cap 4, matching bundle max) |
| `team` | null + greedy joint-Φ | cooperative ceiling: argmax(Φa+Φb) over the SAME bundle space, no Pareto/Nash/IR (review F2 control) |
| `team[energy]` | team, energy issue only | the strong Φ-informed single-issue baseline (review M3) |
| `snhp` | null + Nash bundles | IR bargaining: engine `nash_solver` primitives, strictly-positive surplus both sides |
| `snhp+net` | snhp + trophallaxis fallback | isolates the removed-rescue-rule confound (review M4) |

Bundle evaluation and execution share ONE physics code path
(`apply_bundle` on copies with `log=False`); **evaluated Φ == executed Φ is
asserted on every deal** (review minor-2). One negotiation per robot per
tick, attempt or deal; pair cooldowns: 5 ticks after a failed attempt,
15 after a deal.

## Metrics (review F1/M5)

- **Primary: delivered at fixed 2500-tick horizon.** Never a ratio whose
  denominator shrinks when robots die.
- **Strandings are first-class**, with flip analysis `score_k = delivered −
  k·stranded` reported at k=2 and k=5 (v1's headline inverted at k≈5).
- Energy efficiency (secondary): delivered / energy drawn **up to the last
  delivery** — the meter stops when the work stops.
- Also: lost cargo on stranded robots, Gini of end-state battery (pre-
  registered in v1, never implemented — now implemented), deals, per-deal
  capture, multi-issue fraction, physical exchange counts (all arms, via
  `world.event_log`).
- Stats: paired t AND Wilcoxon, wins/n, on 24 seeds; makespan reported but
  not tested at σ where censoring dominates.

## Pre-registered predictions (v2, before any v2 run)

- **P1:** single-issue snhp arms strike 0 deals at every σ (C1). Already a
  test invariant; the sweep must not contradict it.
- **P2:** on delivered, team ≥ snhp+net ≥ snhp > null at every σ, and
  snhp > auction at σ ≥ 0.5.
- **P3:** the price of selfishness (team − snhp on delivered) is positive
  but shrinks as σ rises (heterogeneity gives IR deals more surplus to work
  with; scarcity of mutually-beneficial bundles is the binding constraint at
  low σ).
- **P4 (the C3 test):** snhp − auction on delivered grows monotonically
  with σ (Wilcoxon p<0.05 for the σ=1 vs σ=0 gap difference, or at minimum
  a monotone point estimate across all five σ).
- **P5:** snhp keeps the lowest lost-cargo of all IR-compatible arms;
  snhp+net strands strictly fewer robots than snhp at equal-or-better
  delivered.

**WIN:** P1 + P2 + P4 hold. **PARTIAL:** P1 + P2 hold, P4 flat → the
mechanism is rescue-economics under scarcity, not heterogeneity logrolling —
reframe accordingly, do not spin. **KILL:** snhp ≯ auction on delivered at
any σ (Wilcoxon), or team[energy] ≥ snhp everywhere AND the IR framing is
judged not to matter for the target application — then the honest conclusion
is the reviewer's: cooperative single-issue Φ-movement is all you need, and
the bargaining layer is overhead.

## v3 addendum — hazard-priced risk (pre-registered before the v3 sweep)

v2.1 outcome was PARTIAL (RESULTS.md): the pure market never beat the
auction rung; only the market + altruistic safety net did, and the net taxed
performance at high σ. Diagnosis: Φ's stranding term was a **binary cliff**
— risk entered valuation only once the charger was already unreachable, so
robots became buyers of survival only after they were too poor to pay. The
market failure was an artifact of myopic risk pricing, and the safety net a
non-generalizable patch over it.

**v3 change (one change, re-pinned):** `-hz` arms price stranding as a
smooth forward-looking hazard, `P_STRAND · sigmoid(−margin/8)` where margin
= battery − cost-to-charger. Solvent robots with shrinking runway now bid
for energy BEFORE distress. No new issues, no new rules — pure valuation.

Pre-registered predictions:
- **P6a:** snhp-hz > snhp on delivered at every σ, with strictly fewer
  strandings.
- **P6b:** snhp-hz ≥ auction on delivered at every σ (what pure snhp never
  achieved), Wilcoxon-significant at ≥3 of 5 σ.
- **P6c:** snhp-hz closes ≥50% of the (snhp+net − snhp) gap at σ≤0.5.
- **P6d (generalizability):** snhp+net-hz ≈ snhp-hz (|Δ| < 3 delivered,
  n.s.) — correctly priced risk makes the hand-tuned safety net redundant.
- **KILL for the hazard thesis:** snhp-hz ≤ snhp anywhere, or the net still
  adds ≥5 delivered under hazard pricing at σ≤0.5 → risk pricing alone
  cannot substitute for altruistic rescue; the "markets need safety nets"
  framing stands as the durable result.

## v4.0 — structural ownership + refining tariffs (FINAL, post-panel, pre-run)

*The draft below this section was reviewed by a three-lens expert panel
BEFORE any v4 code was written (review/PANEL_V4.md — market design,
methodology, red-team). This section is the binding pre-registration; the
draft is retained beneath for audit trail.*

### World (locked)

- Map, reflection-symmetric about y=16: A1=(6,6), A2=(6,26), B0=(26,6),
  B1=(26,26), charger (16,16). Company 0 owns B0, company 1 owns B1. Each
  company: 12 drones, twin-fleet draws (identical cap/eff/battery multisets,
  positions mirrored), sectors stratified 6/6/6/6 (company ⊥ sector). Every
  facility is 20 from the charger; each company faces the same far-source
  tension: haul home 40 vs foreign refinery 20 at (1−τ).
- Tariff τ per company (τ0, τ1), assessed ONCE at refine-time on the
  refining robot's company; deliverer books (1−τ)·V_DELIVER foreign, V home;
  τ·V books to the host-company ledger. **team internalizes tariffs** (a
  merged firm pays itself → full V everywhere for team's routing/valuation;
  flows still ledgered).
- Cargo provenance: units tagged with mining company; delivered books into
  the (miner × refiner-owner) 2×2 matrix.
- Charger tie-break: seeded random priority permutation (company-neutral);
  per-company queue-wait logged.
- ONE `delivery_target(r, w)` (tariff-aware best refinery with hysteresis)
  consumed by BOTH the movement policy and Φ's load term. EV (energy shadow
  price) is endogenous: lagged finite-difference ∂Φ/∂battery per robot,
  clamped [0.05, 1.0], refreshed every 10 ticks (freeze flag for estimator
  sensitivity runs).

### Arms (adds to the ladder)

`auction-co` (auction with company walls: selfless transfers within company
only), `team-co` (joint-Φ within company; cross-company inert), `twofirm`
(within-company joint-Φ pick; cross-company Nash-IR pick). snhp deliberately
has NO -co variant: IR is the company discipline — that is the thesis as a
design choice.

### Pre-registered predictions (binding)

- **P7-A (border volume — genuinely two-sided):** cross-company cargo
  volume in pure snhp arms is ≥50% of the auction arm's at σ=0.5, τ=0 —
  i.e. IR prices the border rather than closing it (autarky). Volumes split
  distress vs healthy; the healthy split carries the claim. Compensation
  ratio and terms-of-trade (energy-per-credit in border deals) are
  REPORTED as measurements, never pinned.
- **P7-B′ (tariff avoidance):** d(system delivered)/dτ is strictly less
  negative for snhp-hz than for null across τ ∈ {0,.05,.1,.15,.25,.5}
  (Page's trend on the paired differences) — the bargaining layer reroutes
  around the wedge via border handoffs; border handoff count increases in
  τ for snhp-hz, flat for rules/null.
- **P7-B″ (incidence):** in border cargo deals under snhp-hz, the implied
  cargo price shifts with τ and the wedge splits between the two sides
  (pre-registered: mean incidence share on the foreign-refining side ∈
  [0.25, 0.75] — a real split, not full pass-through either way). The
  auction has no prices; no incidence exists there by construction (stated,
  not "found").
- **P7-B‴ (merged-firm contrast):** team's foreign-refined share is FLAT in
  τ (internalized); every non-team arm's falls. Derived τ* pinned by test:
  a loaded (L=3, eff=1) far-source drone flips home between τ=0.10 and
  τ=0.20.
- **P7-C (regime law, order only):** in the τ=0 anchor column, snhp-hz
  beats snhp+net at high σ and loses at low σ with a crossing in between —
  thresholds free (geometry changed).
- **P7-D (boundary decomposition, σ≥0.75 only):** team ≥ twofirm ≥ team-co
  on delivered; team − team-co = the boundary premium; twofirm vs team-co
  answers markets-between-firms vs walled cooperation (direction NOT
  pre-registered — genuinely open).
- **Placebo (must pass):** at τ=0 in the anchor column, per-company ledger
  differences centered on 0 (symmetry + twin fleets); charger slot grants
  split evenly at σ=0.
- **KILL:** P7-A fails as autarky (border volume <10% of auction's healthy
  volume) → IR bargaining cannot sustain inter-firm logistics and the
  mixed-ownership pitch falls; or the placebo fails → design bug, no claims
  read until fixed.

### Bridges (run before reading any v4 cell)

(1) v3-geometry preset through the v4 codebase reproduces sweep_v3
snhp/auction rows within CI (8 seeds); (2) Φ/policy reduction test: one
refinery + τ=0 ⇒ delivery_target degenerates to v3 intent; (3) the τ=0
anchor column is the only place P7-C/P7-D are read; tariff cells are read
only against the anchor.

### Grid

Column A (τ=0): {null, rules, auction, auction-co, team, team-co, twofirm,
snhp, snhp+net, snhp-hz} × σ {0, 0.5, 1.0} × 24 seeds, plus σ {0.25, 0.75}
for {snhp-hz, snhp+net, twofirm}. Column B: τ ∈ {.05,.1,.15,.25,.5}
(symmetric τ0=τ1) × {null, snhp-hz, team} × σ {0, 0.5, 1.0} × 24. v4.1:
best-response τ equilibrium + gray-market-disciplines-prices; v4.2:
vouchers (law of one price). Stats: Wilcoxon paired by seed, Page for
trends, Holm within families; SYSTEM delivered primary; company ledgers
descriptive.

## v4.1 — price formation (FINAL, pre-run)

The supply side the panel demanded: each company posts a revenue-maximizing
tariff. Structural note pinned BEFORE running (corrects the panel's
differentiated-Bertrand framing): in v4.0 physics a company's tariff is only
ever paid by the OTHER fleet, so demand at B0 depends on τ0 alone — the
"duopoly" separates into **two independent monopolies**, and cross-price
interaction can exist ONLY through the bargaining gray market (a c1 drone
dodging τ0 by handing cargo to a c0 partner). Equilibrium is therefore
computed as the symmetric monopoly optimum τ* = argmax τ·V·F(τ) per fleet
type, with a separability probe as its own prediction.

Method: symmetric τ sweep τ ∈ {.05,.075,.10,.125,.15,.175,.20,.25,.35,.50},
12 seeds, fleets {null, snhp-hz}, σ ∈ {0, 0.5}; revenue = mean per-company
tariffs earned (companies pooled — symmetric by twin-fleet design).
Separability probe: R0(τ0 | τ1=0.5) vs R0(τ0 | τ1=τ0) for null, 8 seeds.

Pre-registered:
- **P8a:** an interior revenue-maximizing τ* exists for the null fleet at
  σ=0.5 (0 < τ* < 0.5, single-peaked around the demand choke ≈0.15–0.25).
- **P8b (headline, genuinely two-sided):** the bargaining fleet's τ* or
  peak revenue is LOWER than the null fleet's — the gray market disciplines
  posted prices. Could fail: v4.0 measured the healthy border channel at
  ~1 unit/run, possibly too thin to cap anything.
- **P8c (knife edge):** at σ=0 the revenue curve is cliff-shaped (step
  demand) vs smooth single-peaked at σ=0.5 — "a well-defined market price
  requires heterogeneity."
- **P8d (separability):** the null fleet's R0(τ0) curve is unchanged by
  τ1 (two monopolies, not Bertrand); any cross-τ shift under snhp-hz is
  gray-market mediated (exploratory given thin volume).
- **KILL:** revenue non-positive everywhere or τ* pinned at a boundary for
  both fleets → posted-price formation fails in this economy; report as
  such.

Also added to the runner for v4.1 (time-resolved deadweight, red-team F2):
`delivered_mid` = delivered at tick 800.

## v5 — imperfect information in a rich ecology (FINAL, pre-run)

Motivation: v0–v4.1 were full-information and artificially scarce (one
charger, two asteroids) — the cleanest possible economics test, but rescue
churn dominated and truthful-Φ exchange assumed away the hardest part of
real negotiation. v5 changes the STAGE once (rich ecology) and then treats
INFORMATION QUALITY as the experimental dial.

### The v5 world (one stage change, mirrored for the placebo)

- **10 asteroids** in 5 mirror pairs (reflection about y=16), stocks drawn
  6–18 per pair (pairs share stock), total pinned to 120. Sectors
  generalize to **claims**: each drone claims one asteroid (policy:
  best stock/distance when the claim depletes); the third bundle issue
  becomes claim-swapping. Deal space stays 7×7×2.
- **4 chargers** in 2 mirror pairs, **company-owned** (2 per company),
  2 slots each: own-fleet rate 4/tick, **guest rate 2/tick** — priced
  infrastructure access, physically (no new money flows). Charger choice,
  safe-return, and hazard use nearest-effective-charger.
- Refineries + tariff unchanged from v4 (τ=0.15 fixed — border economics
  stay live). Twin fleets, mean-preserving σ, neutral tie-breaks retained.

### The information dial

Bargaining arms estimate the COUNTERPARTY's surplus with multiplicative
noise (per-encounter bias + per-bundle jitter, scale s ∈ {0, 0.25, 0.5,
1.0}); own valuations stay true. Protocol: proposer picks the Nash bundle
under (own truth, noisy estimate of partner); partner VETOES any bundle
that loses on its true Φ; one role-swapped retry, then no deal. s=0 must
reproduce the noiseless path exactly (pinned as a test). team stays
noiseless (it is the full-info cooperative ceiling, not a treatment arm).

### Pre-registered predictions (P9)

- **P9a (info tax + crossover):** bargaining-fleet delivered falls
  monotonically in s; the info-robust auction baseline overtakes PURE snhp
  at some s* ≤ 1.0. Genuinely two-sided: the veto may make bargaining
  noise-robust (failed deals cost nothing but time) and no crossover
  exists.
- **P9b (winner's curse):** veto rate rises with s, and vetoed proposals
  are concentrated on bundles whose ESTIMATED partner surplus was high —
  noisy argmax selects overestimates.
- **P9c (the net returns):** the safety net's value is restored by noise —
  snhp+net ≥ snhp-hz at high s even at σ=1.0, reversing v3's high-σ
  verdict (failed deals reopen the rescue gap that hazard pricing closed
  under full information).
- **P9d (ecology, the user's conjecture):** in the rich world at s=0,
  strandings fall vs the v4 anchor and the healthy (non-distress) share of
  deals rises — the bargaining advantage shifts from rescue churn to
  allocation. Claim-swap deals occur at material rates (>10% of bundles)
  with 10 asteroids vs 2.
- **Placebo:** company ledger differences centered at 0 in the mirrored
  rich world; guest-charging occurs (>0) at s=0 (non-vacuity for the
  infrastructure geography).
- **KILL (thesis-level):** if any s>0 collapses ALL bargaining arms below
  the auction everywhere, the full-information results were decorative and
  the imperfect-information gap is the whole problem — report as such and
  redirect to the engine's Bayesian machinery as the required next step.

Grid: {rules, auction} × s=0 baselines + {snhp, snhp-hz, snhp+net, team}
× s ∈ {0, 0.25, 0.5, 1.0} × σ ∈ {0.5, 1.0} × 16 seeds (~600 runs), all in
the v5 world; P9d reads against the v4 anchor column.

**Stage amendments logged before any results were read** (smoke-test
calibration, predictions unchanged): (1) v5 fleets launch lean — battery
mean 40 (spread ±30σ, floor 8) — because at mean 60 the rich stage was
trivially abundant (all arms finished by tick ~150 with <10 deals;
coordination decorative); v3/v4 draws untouched for artifact
reproducibility. (2) v5 workload doubled to 240 units (same 5 mirrored
pairs) — at 120 the task ended before charging economics bound. (3) The
claim-generalization of `intent()` perturbs v4-preset trajectories by ~1
delivered unit vs the committed sweep artifacts, so column C re-runs its
own same-code v4-preset anchor cells rather than reading sweep_v4_A.json
(provenance: old artifacts reproduce at commit 279b21e).

## v6 — strategic lies vs attestation (FINAL, pre-run)

v5 established that estimation NOISE cannot kill the market (the veto does
the work of trust). v6 tests what noise is not: DECEPTION. Robots may now
misreport strategically; attestation (verifiable books — the abstract
in-sim version of the engine's signed-state rails) is the countermeasure.
This is the incentive-compatibility experiment the arena work predicted
("the multi-issue edge is attestation-gated").

### Mechanics (one lie channel, one defense)

- **The lie:** BATNA inflation — the canonical bargaining lie. A liar
  reports d̂ = d + λ·(its best achievable surplus in this encounter),
  λ=0.5. Uniform surplus-scaling is Nash-neutral (cancels in the product),
  so BATNA inflation is the strategically meaningful channel: it shifts
  the split toward the liar and kills marginal deals. Reports enter the
  Nash pick; the TRUE-loss veto stays (nobody accepts a real loss), so
  lying redistributes surplus and destroys trades — it cannot poison an
  executed deal.
- **Attestation:** an attested robot's report is verifiably true (in-sim:
  the flag forces truthful reporting; in-product: signed state). Liars by
  definition cannot attest while lying.
- **The defense (distrust tax):** against an UNattested counterparty, a
  robot only accepts bundles paying it ≥ δ·(its best achievable surplus),
  δ=0.25 — a safety margin against presumed inflation. Attested pairs
  trade margin-free. The tax is itself a friction; whether it costs more
  than the lies it deflects is genuinely open.

### Conditions (v5 stage, no estimation noise — deception isolated)

honest-all (baseline) · liars at f ∈ {0.25, 0.5, 1.0}, no defenses ·
attested-all (mechanical recovery check) · **mixed-market**: same liar
fractions, honest robots attested, distrust tax active. Arms: snhp-hz and
snhp+net (the two IR champions); team/auction unaffected by reports (no
reports consumed) run as constants. σ=0.5, 16 seeds, liar assignment
seeded and company-balanced (placebo preserved).

### Pre-registered predictions (P10)

- **P10a (lying pays, alone):** without defenses, liars out-earn honest
  robots within-run at f=0.25 (per-robot credit), while SYSTEM delivered
  falls with f — individual incentive, collective tax: the unraveling
  gradient.
- **P10b (collapse):** at f=1.0 undefended, deal formation collapses
  toward the null/rules regime (deals down by >50% vs honest; delivered
  within noise of the rules arm) — mutual BATNA inflation empties the
  feasible set.
- **P10c (mechanical recovery):** attested-all ≡ honest-all exactly (same
  trajectories, pinned as a test).
- **P10d (THE claim):** in mixed markets, attestation + distrust tax
  (i) recovers ≥50% of the deception tax on system delivered, and
  (ii) FLIPS the individual incentive — attested honest robots out-earn
  liars at every f. Two-sided risk, stated: the distrust tax may cost
  more than the lies it deflects (net-negative defense), which would kill
  the "rails pay for themselves" framing.
- **KILL:** if P10d(ii) fails everywhere — lying still pays under
  attestation — the attestation-gated thesis dies in its own benchmark;
  report as the headline regardless of how embarrassing.

## v6.1 — attestation gates COOPERATION (FINAL, pre-run)

v6.0's pre-registered KILL fired: in Nash-IR bargaining the true-loss veto
already provides the protection attestation was supposed to add (lying is
near-harmless and near-profitless there — an intrinsic lie-tolerance
result). The arena finding says where attestation actually matters: the
JOINT tier. Cooperative picks maximize the SUM of reported utilities and
execute without a veto — that is what trusting a counterparty means — so
inflated reports can genuinely exploit. v6.1 tests attestation as the GATE
to that tier.

### Mechanics

- **Trust-tier arm** (hazard Φ, v5 stage): if the pair qualifies as
  trusted, pick = joint argmax over REPORTED utilities, NO veto; else pick
  = Nash-IR on reports with the true-loss guarantee.
- **The lie (joint-tier form):** liars inflate reported per-bundle surplus
  ×1.5 (û = d + 1.5·(u−d)) — BATNA lies don't hijack a joint argmax;
  utility inflation does.
- **Conditions:** `trust-open` (everyone gets the joint tier — naive
  cooperation), `trust-gated` (joint tier only for attested↔attested;
  liars can't attest → they get Nash-IR), nash-only baseline (v6.0 rows).
  f ∈ {0.25, 0.5}, σ=0.5, 16 seeds, company-balanced liars.

### Pre-registered predictions (P11)

- **P11a (cooperation is exploitable):** in trust-open with liars, honest
  robots execute true-loss deals (>0 per run, impossible under IR) and
  liars out-earn honest robots significantly (adv > +10 credit).
- **P11b (the gate works):** in trust-gated, exploitation deals drop to 0
  between honest pairs, and the liar advantage reverses or vanishes —
  liars are relegated to the IR tier and lose the cooperation dividend.
- **P11c (the dividend is real):** gated honest fleets outperform the
  nash-only baseline on system delivered/makespan — else gating protects
  nothing worth having.
- **KILL:** liars don't out-earn in trust-open (cooperation not
  exploitable here) OR gating fails to remove the advantage → the
  attestation-gated-cooperation thesis fails in embodied form; headline
  the failure.

## v7 — noisy self-knowledge (FINAL, pre-run)

v6 proved the true-loss veto makes bargaining deception-tolerant. The veto
assumes you know your OWN state — but a drone's battery gauge is a sensor
like any other. v7: each robot carries a persistent gauge miscalibration
(bias ~ N(0, s₇), twin-mirrored for the placebo); ALL beliefs (Φ, hazard,
routing thresholds, veto) consume the believed battery; ALL physics (move
costs, transfer clamps, stranding) uses the true one. Evaluated==executed
stays belief-consistent; truth is logged separately per deal.

v6.2 attribution fix ships with this: deal logs carry liar flags;
trusted-tier true-loss deals split into STRIP (a liar gains while an
honest robot loses) vs SACRIFICE (benign joint-max losses).

Conditions (snhp-hz, v5 stage, σ=0.5, τ=0.15, 16 seeds): gauge noise
s₇ ∈ {0, 0.15, 0.30} × liars f ∈ {0, 0.5} (BATNA lies) × self-margin
defense {off, on} (a robot demands believed surplus ≥ 25% of its best —
v6's useless distrust tax, aimed inward at its own sensor error).

Pre-registered (P12):
- **P12a:** self-noise alone degrades the fleet monotonically (strandings
  ↑ — optimistic gauges overcommit; delivered ↓ or makespan ↑).
- **P12b (the point):** deception-tolerance erodes — POISONED deals
  (executed with negative TRUE surplus for an honest side; impossible at
  s₇=0 FOR VETO ARMS — joint-pick arms execute one-sided losses by
  design; pinned by test_v7_poisoned_zero_without_gauge_noise, added
  post-review 2026-07-15) appear and grow with s₇, and liar advantage
  grows vs the s₇=0 baseline. The veto's guarantee is exactly as good as
  self-knowledge. *(Post-review note: the across-s₇ liar contrast is
  seed-paired only after the RNG-stream fix; the original draws gave the
  s₇=0 cell a different liar set per seed.)*
- **P12c (the defense):** the self-margin cuts poisoned deals ≥70% at
  s₇=0.3; two-sided risk stated — the margin may cost more trade than it
  saves (net delivered could fall).
- **KILL:** if s₇>0 produces no poisoned deals (physics clamps protect
  anyway), the v6 veto story stands unqualified and v7's premise is wrong
  — report as such.

## v4 PLAN — structural ownership + refining tariffs (SUPERSEDED DRAFT, kept for audit)

Mixed ownership becomes PHYSICS, and refining prices become the market force.

### World changes

- **Two companies** (12 drones each, interleaved ids; company ⊥ sector —
  each company mines both asteroids, so sector swaps can cross companies).
- **Per-company refineries:** B0=(26,6) (natural loop A1→B0, haul 16),
  B1=(26,26) (natural loop A2→B1, haul 20). Delivering at your OWN refinery
  earns the full V_DELIVER per unit.
- **Refining tariff τ (the market force):** any drone MAY refine at the
  foreign refinery, keeping only (1−τ)·V_DELIVER; the τ share is booked to
  the host company's ledger. τ is a posted world constant in v4.0, swept
  τ ∈ {0, 0.2, 0.4, 0.8} to demonstrate the force: high τ → haul home or
  sell locally; low τ → geography wins. (Negotiated tariffs — per-docking
  vouchers as a 4th bundle issue — deferred to v4.1; needs refinery-side
  bargaining or voucher state. PANEL QUESTION #1: is posted-τ enough to
  claim "prices as market force," or is the voucher issue the actual
  contribution?)
- **Charger** moves to neutral center (16,16), still 2×4/tick (single
  scarce facility between both companies). PANEL QUESTION #2: does one
  neutral charger contaminate the company comparison (congestion coupling),
  or is shared scarce infrastructure exactly the point?
- Company ledger tracked per run: own-refined, foreign-refined, tariffs
  paid/earned, credit donated via uncompensated cross-company handoffs.

### Mechanism consequences (why this makes IR structural)

- A cargo handoff across companies moves future delivery credit to the
  receiving company. In the **auction arm** (cost-based, selfless) that
  donation is invisible to the mechanism — the company ledger will now show
  it explicitly. In **snhp arms**, IR forces every cross-company transfer
  to be compensated inside the bundle (energy/sector/…): the ledger should
  show ≈0 uncompensated credit flow.
- **team arm = the merger counterfactual** (optimizes joint Φ ignoring
  company lines): its ledger shows what a cartel would reallocate — the gap
  between team and the best IR arm is the price of remaining two firms.

### Φ / policy changes (same for every arm)

- Delivery target (movement + Φ load term): argmax over refineries of
  `credit_per_unit·load − dist·eff·(1+λ)·EV`, EV = energy shadow price
  constant (0.15; sensitivity-checked ±50%). PANEL QUESTION #3: cleaner
  way to price haul-energy against credit without a hand-set EV?
- Future-trips term: per-company — best (source, refinery) pair the policy
  would actually run, tariff-adjusted.

### Pre-registered predictions (to finalize AFTER panel feedback, before v4 sweep)

- **P7a (IR is structural):** uncompensated cross-company credit flow is
  substantial in auction (>10% of system credit at σ=0.5) and ≈0 in snhp
  arms; snhp cross-company handoffs are ≥90% bundled with compensation.
- **P7b (tariff is a real force):** foreign-refined share decreases
  monotonically in τ; at τ=0 routing follows geography, at τ=0.8 foreign
  refining ≈0. System delivered is maximized at τ=0 (tariffs are
  deadweight for the SYSTEM) but company-ledger balance shifts with τ —
  the market-force demonstration.
- **P7c (regime law replicates):** hazard-priced snhp-hz still beats
  snhp+net at σ≥0.75 and still loses to it at σ≤0.25 in the two-company
  world.
- **P7d (merger premium):** team − best-IR-arm gap persists and is now
  interpretable as the measured value of merging two fleets.

### v4.1+ (not in v4.0)

Negotiated refining vouchers (4th issue), contingent rescue contracts / IOU
credit with commitment tracking (deferred payment — banking the
currently-unbankable robot; the A2A payment-rail analog), noise/robustness
per STANDARDS_BRIEF §5.

## Explicitly out of scope for v0.1 (from expert consult, ordered)

Noise/robustness (fault injection), N-sweep 10→1000, partial-information
utilities (the engine HAS the Bayesian machinery — natural v2 of the
research), continuous space/ARGoS, hardware demo, energy-loss as a
distribution, sector-swap travel costs, IC/lying (arena finding: needs
attestation), LLM-driven agents.

## Engine reuse map (unchanged)

`generate_contract_space` / `filter_pareto_frontier` /
`find_nash_bargaining_solution` from `snhp/nash_solver.py` — the same
primitives `negotiate_bundle` runs on.

Run: `python research/swarm/run.py` · Tests: `pytest research/swarm/test_swarm.py`
Viz: VIZ.md (`trace.py` → `viewer.html`, side-by-side compare).
History: v1 spec is in git history; v1 findings and their demolition:
review/ADVERSARIAL_REVIEW.md.

---

## v8 pre-registration: field geometry (column G) — "density decides the winner"

*Registered 2026-07-15, BEFORE implementation or any pilot run. Founder's
hypothesis, verbatim: "on a more dense field auction wins vs more sparse
field bargain wins, because as the logistics gets more complicated bargain
gets the advantage." Runs ONLY on the corrected physics (pad-unload +
transaction-pause + any audit-mandated fixes), after the full A–F re-run.*

**Manipulation:** grid side G ∈ {24, 32, 48, 64} with total stock (240),
asteroid count (10 mirror-paired), charger count (4) and refinery count (2)
held FIXED; all facility positions scale proportionally with G. Density =
stock per unit area varies ~7× purely through geometry. Battery physics
unchanged — bigger fields mean longer supply lines, more charge stops, and
trips that are infeasible without mid-route energy trades.

**Arms:** auction, snhp-hz, snhp+net, team (ceiling), rules (floor).
σ=0.5, τ=0.15, 16 seeds, 2500 ticks (4000 at G=64 if horizon-censoring
exceeds half the runs — decided by censoring rate, not by results).

**Pre-registered predictions (P13):**
- **P13a (the theory):** the auction-minus-bargaining delivered gap falls
  monotonically with G: auction ≥ bargaining at G=24, bargaining > auction
  at G=64 (bargaining = snhp+net, the shipped champion; snhp-hz reported
  alongside). A crossover exists inside the tested range.
- **P13b (the mechanism):** the energy+rescue share of executed bargained
  issues RISES with G (logistics, not cargo arbitrage, is where sparse-field
  value lives). If P13a passes but P13b fails, the theory's outcome is right
  for the wrong reason — report as such.
- **P13c (robustness):** P13a holds on delivered − 2·stranded and
  delivered − 5·stranded (sparse fields must not win by strand-and-abandon).
- **KILL:** if either arm wins at EVERY tested G (no crossover), the density
  theory dies and the honest headline is whichever uniform result survived —
  including "auction wins everywhere on corrected physics," if that is what
  the data says.

**Viewer prerequisite:** the replay currently hardcodes GRID=32 (header
`grid` field ignored — review finding V4); per-trace cell scaling must land
before any G≠32 trace is visualized, or the pixels will lie.

---

## v9 pre-registration: endogenous drone valuation (column H) — "price the drone's remaining career"

*Registered 2026-07-15, BEFORE implementation or any pilot run. Founder's
theory, verbatim: "if the overall goal is gold maximizing (as a company)
then the best strategy would win — why are drones not priced as an
expectation of what they can still mine?" Motivation: the k-audit showed
every flat-P_STRAND hazard claim dies at k>0, with flip points clustered at
the internal price (1.5 ore) — the signature of a mispriced asset, not
necessarily a broken mechanism. Runs only on corrected physics, after the
A–F re-run.*

**Change under test (one change):** replace the flat stranding price
P_STRAND=15 with the drone's LIFE VALUE, V_life(r) = future-trips value
evaluated at a healthy reference battery (not current charge — a dying
robot's low spare energy must not talk itself into being worthless) plus
the value of carried load. Applied consistently in all three places the
price appears: the hazard term (−V_life·P(strand)), the stranded-state Φ
(−V_life at stranding time), and therefore rescue-deal surplus (a rescue
buys back the victim's remaining career). Optional exogenous capital cost
k_cap ∈ {0, 2, 5} ore-units added on top, mirroring the scoreboard's k.

**Arms:** snhp-hz (flat, control) · snhp-lv (life-value) · snhp-lv+cap
(k_cap=2) · snhp+net (champion control) · team (ceiling) · auction (floor).
v5 preset, σ ∈ {0.5, 1.0}, τ=0.15, 16 seeds, 2500 ticks.

**Pre-registered predictions (P14):**
- **P14a (the mispricing claim):** snhp-lv strands ≤ HALF of snhp-hz's
  end-state strandings at σ=0.5 with delivered within noise (survival is
  nearly free once the price is right), and the reduction concentrates in
  the EARLY run (t<800), where V_life is largest.
- **P14b (the market catches the net):** snhp-lv ≥ snhp+net on
  delivered − 2·stranded AND delivered − 5·stranded (the safety net's
  k-dominance over the market disappears when the market prices drones
  correctly — v3's dead hypothesis, resurrected with the right price).
- **P14c (rescue timing):** distress-deal volume shifts earlier; endgame
  abandonment of remote drones REMAINS (V_life→0 as stock depletes is
  correct behavior, not a failure).
- **Exploratory, no prediction:** snhp-lv vs team on v5 at k ∈ {0,2,5} —
  whether ANY selfish arm beats the hive on the lean stage once assets are
  priced. Reported either way; the v2.1-vs-v5 "who beats the hive"
  discrepancy is resolved by data, not scoping language.
- **KILL:** if snhp-lv fails P14b (net still k-dominates) or collapses
  delivered by >10 (over-fear: fleet too precious to work), then flat
  pricing was NOT the binding flaw — the safety net's edge is
  institutional, not a pricing bug — and the article's scoping stands
  as the honest fix.

**P13 VERDICT (2026-07-15, sweep_G.json, corrected physics): KILLED as
stated; replaced by the hump law.** P13a: refuted in both directions —
bargaining (snhp+net) wins at G=24 (+4.1) and peaks at G=48 (+7.3), auction
wins at G=64 (−2.7); the predicted dense-end auction win does not exist,
and the sparse-end bargaining win inverts at the extreme. P13b: refuted —
energy-issue share is flat (~95%) across G; volume rises instead (65→152
deals/run). P13c: k-scores track delivered (net k5-dominates ≤G=48, loses
at 64). KILL did not fire (no uniform winner). Honest law: the market's
edge is hump-shaped in logistics complexity — enough friction to be worth
paying for, enough meeting density to physically convene.

**P14 VERDICT (2026-07-15, sweep_H.json, corrected physics): KILL FIRED —
institutional, not a pricing bug.** P14a: failed (snhp-lv strands MORE,
+7.3 p=.001 — decaying career value makes late-game drones disposable).
P14b: failed (snhp-lvc ties the net on delivered, sets the fastest selfish
makespan recorded — 688 — and beats flat-hz at every k, but loses k5 to the
net by −36, p=.001). P14c: directionally held (lvc's deals rise to 114/run
with early distress trade). Exploratory: no selfish arm beats team on v5 at
any k. Conclusion: better prices buy SPEED, not the net's survival record;
the safety net is the better institution, not a patch over a mispriced
market.

---

## v10 pre-registration: imperfect field information + the priced race (column I)

*Registered 2026-07-15 late, BEFORE implementation or any pilot run.
Founder's critique, verbatim: "companies dont have perfect info about the
asteroid field hence the swarm robotics and everyone is working on
estimates of information" and "we are not pricing in mining speed; there
has to be some decay every tick on the total claims because other
companies are racing you to get there." Diagnosis confirmed in code: Φ,
best_claim and v_life read w.stock globally — omniscient valuation over a
perfectly-known field; the race is physically real but priced as a static
share.*

**Change 1 — field beliefs (v10a):** each COMPANY maintains a belief of
every asteroid's stock. A robot within R_SENSE=3 of an asteroid updates
its company's belief to truth (the fleet is a shared sensor network — the
point of a swarm); between observations the belief persists with recorded
staleness. ALL decision layers (Φ future-trips, best_claim, v_life,
auction's net-value) consume the belief; physics (pick) consumes truth.
Mirrors the v7 bat() contract, extended to the field.

**Change 2 — the priced race (v10b):** per-asteroid, a company estimates
the RIVAL depletion rate from successive observations (stock fell faster
than own mining explains ⇒ rate estimate, exponentially smoothed). The
future-trips claim becomes racing-aware:
expected_stock_on_arrival = belief − rival_rate × ETA, floored at 0 —
your "decay every tick" as an expectation, not a hack. Un-raced fields
reduce to current behavior (rate→0).

**Change 3 — mine-rate heterogeneity (v10c, one arm):** mining speed
becomes a σ-scaled trait (1..3 units/tick, mean-preserving) so "fast
miner" is a real comparative advantage the market can price (claim swaps
gain a speed dimension).

**Arms:** auction, snhp-hz, snhp+net, team, rules — each in
belief-mode; snhp+net additionally in oracle-mode (the old omniscient Φ)
as the information-value control. σ=0.5, v5, τ=0.15, 16 seeds.

**Pre-registered predictions (P15):**
- **P15a (info has value):** oracle-mode snhp+net ≥ belief-mode snhp+net
  on delivered; the gap is the price of ignorance. If the gap is ≈0, the
  belief layer is decorative — report as such (KILL for the premise).
- **P15b (the swarm IS the sensor):** belief-mode arms with more
  spatial-coverage (more deals → more movement diversity) hold fresher
  beliefs; bargaining's belief-staleness < auction's. Mechanism metric:
  mean staleness at decision time.
- **P15c (v7 echo, the receipts bleed again):** field-belief error acts
  like gauge error — belief-mode veto arms sign poisoned deals (true-value
  negative) at a rate growing with staleness, while delivered stays
  robust. The fix is the same receipt/attestation layer — this time for
  CLAIMS, not batteries.
- **P15d (the race matters):** racing-aware pricing (v10b on) beats
  racing-blind (v10b off) in belief-mode two-company worlds on delivered,
  concentrated in contested asteroids (both companies mining the same
  rock). If off≈on, the static share was already fine — kill the racing
  layer, keep the beliefs.
- **KILL (whole column):** if belief-mode inverts NO ordering and shifts
  no headline by >2 delivered, perfect information was never load-bearing
  and v8 physics stands as the honest final world.

**Sequencing note:** the article ships on v8 physics (its limits section
already declares the toy honestly); v10 is the follow-up program — and
its P15c, if it lands, is the natural sequel post ("your fleet's map is
also a ledger someone can poison").

**Implementation notes (logged 2026-07-15, before any column-I results
were read; predictions unchanged):**
1. pick() with mine_trait OFF keeps today's fill-cap-in-one-tick physics
   (the draft's `else 1` would have silently rewritten every existing
   column; bit-exactness of pre-v10 columns is the binding constraint,
   verified by git-stash fingerprint diff across v3/v4/v5 presets).
2. intent() keeps a mine_trait robot docked at its rock until cap-full
   (mining is stationary — no battery drain); without this the load>0
   branch departs after one tick and mine_rate re-prices as trip SIZE,
   not speed. Gated on mine_trait; default trajectories untouched.
3. Sensing is live (read-through in stock_belief within R_SENSE) during
   the drive/world phase and frozen during the encounter phase. Reason:
   the oracle is INTRA-tick omniscient (drive-order stock mutations are
   visible immediately), so a frozen once-per-tick belief can never be
   bit-exact with it and the perfect-sensing placebo would be unpinnable.
   Beliefs still cannot change while bundles are priced (evaluated Φ ==
   executed Φ), and the once-per-tick fleet sweep remains world-side.
4. The placebo test pins belief_mode + R_SENSE=64 + race_pricing=OFF ==
   oracle, bit-exact: with per-tick observation the rival rate is
   genuinely nonzero in contested fields (the race is real), so the
   racing term correctly diverges from the raceless oracle even under
   perfect sensing. rival_rate is always ESTIMATED in belief_mode;
   race_pricing gates only its consumption in Φ — P15d ablates pricing,
   not estimation.
5. The registered mine-rate draw round(2 + σ·U(−1,1)) is DEGENERATE at
   σ=0.5 (always 2): the v10c cell as scheduled measures rate-limited
   mining (2/tick vs fill-cap), not rate heterogeneity. Left as
   registered; a σ=1.0 cell would be needed for the heterogeneity claim.
6. sa_true/sb_true under belief_mode audit through phi_true_field (field
   beliefs AND gauge suspended — w._oracle_override): scoring the audit
   against the same stale map that signed the deal would hide exactly
   the poisoning P15c is looking for.

**P15 VERDICT (2026-07-15, sweep_I.json, corrected v8 physics): the
whole-column KILL fired — perfect field information was never
load-bearing — and that is the most valuable possible answer.**
- P15a: the price of ignorance is ZERO (oracle − belief snhp+net: +0.2
  delivered, n.s. on every metric). No ordering inverts; no headline
  moves >2. Every v8 conclusion survives imperfect information.
- P15b: CONFIRMED as mechanism — the swarm IS the sensor network.
  Deal-economy fleets hold ~3× fresher field maps than the auction
  (staleness 165–173 vs 525 ticks; rules 363, team 22) because trade
  moves robots around. The freshness just doesn't cash into gold here:
  a fleet's own working set stays fresh by construction, and beliefs
  are optimistic-only, so stale knowledge fails soft.
- P15c: CONFIRMED, small — stale maps poison receipts exactly like bad
  gauges did (belief-mode veto arms sign 3.4–9.2 truly-harmful deals/run
  vs 0 under oracle at zero gauge noise). The v7 law generalizes: ANY
  self-input error (sensor or map) leaves output flat and corrupts
  books. Same receipt-shaped cure.
- P15d: KILLED — the racing discount never pays (race-on is marginally
  WORSE: −0.6 delivered p=.068, −9.1 k5 n.s.). On mirrored fields,
  contested overlap is too rare; the static share was already the right
  price. The racing layer stays in the code, off by default, honest.
- v10c: inconclusive by design flaw (mine-rate draw degenerate at σ=0.5,
  flagged pre-run); re-registration at σ=1.0 required before any claim.

---

## v11 pre-registration: the moving field (column J) — information value under non-stationarity

*Registered 2026-07-15, BEFORE implementation. Founder's critique of the
P15 verdict, verbatim: "thats because the asteroid field did not change
over time or get bigger or smaller or mined by competitors so wrong
belief was not penalized." Adopted: a static, once-surveyed, mirrored
field makes belief error one-sided, bounded, self-correcting, and
non-adversarial. v11 removes all four crutches.*

**Change 1 — arrivals (two-sided belief error at last):** new asteroids
spawn at seeded times (~every 300 ticks ± seeded jitter) and seeded
positions, with stock from the standard draw. A company does NOT know a
rock exists until a fleet member senses it. Total injected stock pinned
per seed across arms (fairness).

**Change 2 — departures (stale optimism finally costs):** at seeded
times, a seeded existing asteroid goes dark (remaining stock lost —
drifted out / claim-jumped by an off-map actor). A stale map keeps
routing crabs to a ghost.

**Change 3 — contested geography:** column J runs a NON-mirrored variant
of the v5 field (asteroids drawn in a shared central band; fleets spawn
on opposite sides). The twin-fleet placebo is unavailable by design —
noted, accepted for this column — and the rival-rate estimator finally
has something real to measure.

**Arms:** auction, snhp-hz, snhp+net, team — belief-mode; snhp+net also
oracle-mode (the P16a control) and belief-mode with race_pricing=False
(P16c ablation). σ=0.5, τ=0.15, 16 seeds, 2500 ticks.

**Pre-registered predictions (P16):**
- **P16a (the founder's claim):** in the moving field the price of
  ignorance is significantly positive — oracle-mode snhp+net beats
  belief-mode on delivered (Wilcoxon p<0.05). If the gap is still ≈0,
  the founder's objection is itself falsified and the static-field
  robustness claim generalizes further than expected — report either way.
- **P16b (freshness converts):** the fleet with fresher maps captures a
  larger share of ARRIVAL stock — bargaining fleets (3× fresher per
  P15b) out-collect the auction on post-arrival rocks specifically,
  beyond their baseline edge.
- **P16c (the race resurrected):** race_pricing now pays on contested
  ground (belief+race beats belief−race on delivered; the P15d kill was
  scoped to mirrored maps).
- **P16d (books bleed harder):** poisoned-deal rate under belief-mode
  rises vs the static field (departures make stale valuations actively
  wrong, not just conservative).
- **J2 (contingent, register-then-build only if P16a passes):**
  information as the FOURTH issue — cross-company deals may bundle a
  map-sync ("I'll top you up if you tell me what your side has seen").
  Registered as a direction, not a design; full spec required before
  building.
- **KILL (column):** if P16a fails AND P16d fails, non-stationarity of
  this magnitude still doesn't price information — accept that this
  world-class genuinely doesn't reward maps, stop building info
  machinery, and say so publicly.

**Build note (standing rule, this session):** implementation goes to an
OPUS build agent; Fable plans, registers, reviews, and analyzes.

**Implementation notes (logged 2026-07-15, before any 16-seed column-J run;
predictions unchanged):**
1. Field events fire at tick START (World.field_step from BaseArm.tick,
   before drives) rather than inside sense_step: strictly outside the
   encounter phase either way, but tick-start is the simplest placement that
   provably keeps evaluated Φ == executed Φ across an arrival/departure.
2. In belief-mode an arrival's stock is UNMINEABLE until a robot wanders
   within R_SENSE (belief starts 0; best_claim skips stock≤0 beliefs), so
   belief-mode fleets can leave arrival stock in the ground that oracle
   fleets clear — this IS the P16a channel, confirmed in a 2-seed smoke
   (oracle mined 80 arrival units vs belief-mode 61 at one seed). Correct
   behavior, not a bug.
3. arrivals_mined uses per-asteroid pick provenance (w.mined_from), NOT
   delivered provenance: origin is known at pick(), and carrying per-unit
   delivery origin would be invasive. Documented proxy for P16b.
4. The lean v5 fleet does not clear a live field 100% (a couple of units
   strand), so the makespan test pins the delivered ≥ total_stock THRESHOLD
   semantics on the conservation ledger directly rather than requiring an
   emergent full-clearance run; the real-run smoke nonetheless shows makespan
   firing at the correct tick once an arrival's stock is delivered (seed 0
   snhp-hz: delivered 259 = 240 base + 19 arrival, makespan 499).

**Post-build note (audit trail):** the build agent's worktree forked before
this registration was committed, so it reconstructed a conservative
registration from the build contract; that text is superseded by THIS
section (written pre-build) — predictions P16a–d and the J2 contingency
above are the operative ones. Implementation mechanics (dedicated
RandomState(seed+7919) schedule, 8 arrivals U(200,2300) + 4 departures
U(400,2300), events fire at tick START, arrival band interior with ≥3
spacing, contested rock-rock spacing ≥3, arrivals_mined provenance proxy,
makespan pinned on the conservation ledger) are as the builder documented
in code and its report.

**P16 VERDICT (2026-07-15, sweep_J.json, n=16): the founder's premise
half-confirms, and the moving field flips a headline.**
- **P16a: FAIL as registered** — oracle − belief on delivered is +11.4,
  ~50× the static-field gap but p=.15 at n=16 (underpowered, direction
  right). The SIGNIFICANT info-value channel is the books: belief-mode
  signs +7.0 more poisoned deals (p=.0004). Information's first casualty
  is receipt integrity, not output. The J2 (map-trading) gate was tied to
  P16a delivered significance and therefore DOES NOT FIRE — J2 stays
  unbuilt until re-registered.
- **P16b: INVERTED, significant** — the auction captures MORE arrival
  stock (46.2 vs net's 32.4/run, p=.03) despite far STALER maps (305 vs
  190 ticks). Freshness ≠ discovery: you cannot have a belief about a
  rock you've never seen. The deal economy converges robots onto
  known-profitable loops (exploitation); the auction's inefficient
  roaming is accidental exploration. **Optimization buys blindness to
  novelty.**
- **P16c: KILLED, final** — the racing discount doesn't pay even on
  contested ground (−5.9, n.s.). The layer stays off permanently.
- **P16d: PARTIAL** — ghosts double the safety-net arm's poisoning
  (3.4 → 7.0/run); flat for hz.
- **Exploratory headline (same data, flagged as post-hoc):** on the
  moving contested field the auction OUT-DELIVERS every coordination arm
  (net −12.6, p=.044, 2/16; team −13.2, p=.075) while k5 is a wash
  (auction pays its gold edge in dead drones). The discovery gap explains
  the delivered gap almost exactly (13.8 arrival-units ≈ 12.6 delivered).
  **The bargaining advantage is scoped to known fields; novelty-rich
  worlds reward coverage over coordination** — the deepest scoping
  result in the program, and the honest motivation for any future
  map-trading registration.

---

## v12 pre-registration: pricing the unknown (column K) — scouting, map-selling, and claims on the unexplored

*Registered 2026-07-15, BEFORE implementation. Founder, verbatim: "we are
not pricing exploration (ie claim rights to unexplored parts) why did we
not test selling maps?" GATE AMENDMENT, explicit: J2 was gated on P16a's
output significance (missed, p=.15 at n=16) — the wrong variable, since
both true motivations were significant on the same run (books +7.0
poisoned p=.0004; discovery deficit −13.8 arrival units p=.03). The gate
is opened by founder decision and this note is the audit trail. Runs on
the v11 moving+contested world.*

**K0 — price exploration in the movement policy.** An idle robot (no
believed-stocked sector worth a trip) SCOUTS: it heads for the stalest
point of its company's map, valuing the trip at
E[discovery] = arrival_rate × staleness × V_DELIVER-scaled term. Without
this no mechanism below can matter (nobody patrols what nobody values).
All arms get K0 identically — it is policy, not mechanism.

**K1 — map-selling (the 4th issue, cross-company).** Within-company maps
are already shared radio; the tradeable good is the RIVAL's map. A bundle
may include map-sync: the seller's fresher belief entries are escrowed
into the deal and transferred on execution (union by last_seen). The
buyer's utility for a sync is its Φ-delta computed on a belief COPY
(deterministic ⇒ evaluated == executed holds). Info is non-rival: selling
does not degrade the seller's copy — the seller's price is pure surplus
extraction via Nash split.
- **P17a (the market prices maps):** map-syncs trade at all (>1/run
  cross-company) and belief-mode coordination arms with K1 close ≥40% of
  their arrival-capture deficit vs auction (P16b's −13.8).
- **P17b (books heal):** K1 cuts belief-mode poisoned deals ≥30% (fresher
  rival intel = fewer ghost-priced deals).
- **P17c (bad news is unsellable — the honest trap, predicted not
  dodged):** syncs whose net Φ-delta for the buyer is negative (mostly
  bad news: your target rock is dead) are structurally vetoed under IR,
  so traded syncs skew toward good news; measure the skew. If confirmed,
  the market self-censors depressing-but-valuable information — the
  escrow/receipt argument in its purest form.
- **KILL K1:** if map-syncs price at ≈0 (Φ-delta of stale-map correction
  too small to clear TXN_COST + pause) the info market is stillborn in
  this world — report, don't force.

**K2 — claims on the UNEXPLORED (founder's mechanism), contingent on K0
scouting being non-degenerate.** The field is partitioned into 4 quadrant
prospecting claims, initially two per company, TRADEABLE as part of the
sector issue. An arrival inside a claim is minable ONLY by the
claim-holder's company for the first 150 ticks after discovery
(prospecting window). Prediction **P17d:** claims make scouting
investable — the claim-holder patrols its quadrants (staleness inside own
claims < outside, and < the no-claims K0 baseline), and claim trades
correlate with fleet position (sell the quadrant you can't patrol).
**KILL K2:** if claims never trade or patrol behavior doesn't
differentiate, territorial rights over unknowns don't bind in this world.

**Arms (all belief-mode, moving+contested, σ=0.5, 16 seeds):** auction+K0,
snhp+net+K0 (scouting baselines) · snhp+net+K0+K1 (map market) ·
snhp+net+K0+K1+K2 (full) · oracle snhp+net+K0 (info ceiling). Auction
cannot consume K1/K2 (no bundles) — it is the coverage benchmark.

**Build note:** Opus build agent; Fable registered this and analyzes.

**P17 VERDICT (2026-07-15, sweep_K.json, n=16):**
- **P17a FAIL — but because K0 already won.** Scouting alone (+2 patrol
  robots/company) closed the v11 discovery deficit: net arrivals-mined
  44.8 vs auction 47.5 (the −13.8 p=.03 gap → −3.4 n.s.), delivered gap
  erased (284.1 vs 286.6), and the ORACLE advantage vanished (282.8 vs
  belief 284.1 — with patrols, information is free again). The map market
  on top adds nothing to discovery (−0.7, p=1.0) despite 40 executed
  syncs/run. **The exploration deficit was a POLICY gap, not an
  information-market gap.**
- **P17b PASS at the registered bar:** map-buying cuts poisoned deals 30%
  (5.38 → 3.75, p=.04). **The information market's real product is
  receipt integrity, not output.**
- **P17c CONFIRMED, structural:** bad-news-only syncs are IR-vetoed by
  construction (unit-pinned). But bad news CAN travel when the sync
  bundles it with enough good news to clear the buyer's veto — **the
  bundling-necessity law (C1, the program's first result) recurses into
  the information layer: single-issue bad news is unsellable; bundled
  truth trades.**
- **P17d mechanism-only:** claim-holders patrol their quadrants fresher
  (22.7 vs 25.4) with zero output effect at this scale.

---

# THE SCALE PROGRAM — four pre-registrations (columns L, M, N, O)

*All four registered 2026-07-15, BEFORE any implementation. Founder mandate:
"test things about swarms" — scale, asset diversity, drone production, plus
communication locality. Builds are SEQUENTIAL (L → O → M → N; shared files),
each by an Opus build agent that also RUNS its full column; Fable registers,
merges, and writes verdicts. L's results may re-scope the interpretation of
M/N/O but do not block their builds.*

## v13 (column L): scale — "markets are what coordination looks like when planning stops scaling"

**Manipulation:** N ∈ {24, 96, 240} at FIXED density: grid side scales as
32·√(N/24); asteroid count and total stock scale with N (10·N/24 rocks,
10·N units); charger count scales with N (4·N/24, positions tiled). Fleet
composition mean-preserving as always.
**The realistic hive:** team's joint pick is consensus, and consensus costs
rounds: team's DEAL_PAUSE becomes 3 + ⌈log₂(N)⌉ ticks (pairwise bargaining
stays at 3 — two parties is two parties at any N). Team WITHOUT the cost
runs as the free-planning ceiling control.
**Arms:** auction, snhp+net, team-costed, team-free · 16 seeds at N=24/96;
8 seeds core arms at N=240 (compute).
- **P18a (scale-free market):** snhp+net delivered-per-robot at fixed
  density is N-invariant within noise — the mechanism is O(1) per encounter.
- **P18b (planning doesn't scale):** team-costed degrades relative to
  snhp+net as N grows; a crossing (market ≥ costed hive) exists by N=240.
- **P18c (market thickness):** the snhp+net − auction gap GROWS 24→96
  (thicker markets match better).
- **P18d (emergent middlemen, exploratory):** at N=240, count robots whose
  income is dominated by buy-far/sell-near resale spread; report, no
  threshold.
- **KILL:** if the market's per-robot output degrades with N faster than
  the auction's, decentralized bargaining is anti-swarm — the program's
  swarm story dies and we say so publicly.

## v14 (column O): communication locality — "trade is the network"

**Manipulation:** company-wide free radio is removed; observations propagate
by GOSSIP: fleet-mates within R_RADIO=6 cells exchange fresher belief
entries each tick (flooding). Beliefs become per-robot. Map-selling (K1)
remains cross-company.
**Arms:** auction, rules, snhp-hz, snhp+net (belief+gossip, moving field) +
snhp+net free-radio control · 16 seeds, N=24.
**Amendment (2026-07-15, pre-build, founder prompt "one unit can update
global knowledge right?"):** R_RADIO runs as a ladder {2, 6} — 2 cells is
the contact-only/stigmergy limit, 6 is short radio — so P21a/b separate
"needs any locality" from "needs range". Named secondary: the SCOUT RETURN
PROBLEM — under gossip a discovery is worth nothing until relayed, so
scout_ticks stop converting to freshness unless scouts loop home; report
K0-scouting's arrival-capture under gossip vs the free-radio K column as
its own line (the v12 'scouting fixes discovery' claim is at stake).
- **P21a (trade IS the network):** trading fleets still hold fresher maps
  than the auction under gossip — deal encounters double as relay
  encounters.
- **P21b (books bleed first, 4th replication):** gossip staleness raises
  poisoned deals while delivered stays flat vs free radio.
- **P21c (structural):** belief freshness correlates with deal-degree
  centrality — the trade graph and the information graph are the same
  graph. Measured, with a shuffled-null control.
- **KILL:** if gossip collapses coordination output at N=24 density, free
  radio was load-bearing and every belief-mode result re-scopes.

## v15 (column M): asset diversity — "does money emerge?"

**Manipulation:** three ore types: gold (value 10, haul ×1.0), iron (6,
×1.4), ice (4, ×0.7); per-asteroid single type (mirrored assignment);
refineries pay a blend bonus (×1.25 on all deliveries while the company's
rolling 100-tick delivered mix is within ±15% of 1:1:1) — complementary
demand creates cross-commodity logrolling. Contract space: per-type cargo
{-2,0,+2} (27 cargo combos × 7 energy × 2 sector = 378 rows). Variants with
1 and 2 commodities for the dimensionality ladder.
**Arms:** auction, snhp+net, team · 16 seeds, N=24, static known field
(isolate the commodity effect).
- **P19a (dimensionality):** the snhp+net − auction VALUE gap grows
  monotonically with commodity count (1 → 2 → 3).
- **P19b (specialization):** trait-task assortment emerges — thrifty/fast
  crabs over-carry high-value-per-weight ore vs a shuffled null.
- **P19c (the money test, index pre-registered):** medium-of-exchange index
  M(x) = P(x on the opposite side of a cross-commodity bundle). Prediction:
  M(energy) exceeds M(every ore) with p<.05 across seeds — energy becomes
  the medium of exchange. KILL for money: no asymmetry.
- **KILL (column):** if the 3-commodity gap ≤ the 1-commodity gap,
  bundling's value saturates at low dimension — report as the honest bound.

## v16 (column N): drone production — "does the edge compound?"

**Manipulation:** a factory at each company refinery: spend BUILD_COST=150
credits + BUILD_TIME=100 ticks → one new drone, company picks an archetype
(hauler cap5/eff1.15 · runner cap2/eff0.7 · prospector cap3 + scout-role).
Reinvestment rule identical across arms (build when credit ≥ 1.5×cost —
policy, not mechanism). Moving field with arrivals every 150 ticks sustains
workload; horizon 6000 ticks; fleet hard-capped at 96/company (runaway
guard). Metric: NET WORTH = credit + fleet × BUILD_COST; growth = log-slope.
**Arms:** auction, snhp+net, team-costed · 12 seeds, base N=24.
- **P20a (compounding):** snhp+net's net-worth growth RATE exceeds
  auction's, and the level gap widens over time (divergence, not parallel
  lines).
- **P20b (endogenous k):** the sim now sets its own replacement price;
  report the realized effective k (replacement spend per delivered unit) —
  prediction: it lands in [1, 5] ore-units, the range the k-audit debated.
- **P20c (the market prices phenotypes):** archetype mix differs by
  mechanism (bargaining fleets buy different bodies than auction fleets),
  beyond a seed-shuffled null.
- **KILL:** equal growth rates ⇒ the mechanism edge is a level effect that
  does NOT compound — the strongest scoping result the program could
  produce, reported as such.

**P18 VERDICT (2026-07-15, sweep_L.json; N=240 horizon amendment declared
below):**
- **P18b SUPPORTED — the headline: planning stops scaling.** Δ(costed hive
  − market) on delivered_frac: +0.001 (N=24, n.s.) → 0.000 (96) →
  **−0.053 (N=240, p=.008, 0/8 wins)**. The consensus-costed hive crosses
  below pairwise bargaining exactly as predicted; its 11-tick pauses ×
  4,151 deals/run is a crushing immobilization tax. Free-planning team
  remains the ceiling — the gap between team-free and team-costed IS the
  price of central coordination at scale.
- **P18a holds where runs complete** (delivered_frac 0.998/1.000 at
  N=24/96; eval==exec held across all 152 runs incl. N=240): the mechanism
  is O(1)/encounter. At N=240 nothing finishes in 2,500 ticks — see
  amendment.
- **P18c REVERSED:** the market−auction gap SHRINKS with N (+0.019 p=.0015
  → +0.002 → −0.020 at 240, auction 7/8) — ceiling compression at N≤96 +
  deal-pause drag at 240. Market thickness did not materialize on this
  metric.
- **P18d — middlemen are a CENTRALIZATION phenomenon:** middleman fraction
  rises with N under joint/auction coordination (team-costed 0.10→0.27;
  auction 0.13→0.22) and stays low/flat under the IR market
  (0.034/0.038/0.030). Bargaining keeps every robot an owner-operator;
  consolidation onto carrier robots is what hives and auctions do.
- **KILL — fired as registered, confound declared:** on delivered_frac at
  the 2,500-tick horizon the market under-performs the auction at N=240
  (−0.020, p=.0156). Confound (builder-diagnosed): 0% of ANY arm's N=240
  runs finish — the metric measures throughput-in-truncation, and at
  scales where runs complete the market clears the field ~2× faster than
  the auction (makespan 1,066 vs 2,232 at N=24). **AMENDMENT (declared
  post-hoc, before any amendment data seen): re-run N=240 × 8 seeds ×
  {auction, snhp+net, team-costed} at 7,500 ticks; the un-truncated
  verdict is delivered_frac + makespan there. The registered-metric KILL
  stands on the record either way.**

**P18 AMENDMENT RESULT (2026-07-16, sweep_L_amend.json — N=240, 7,500
ticks, the un-truncated verdict). The horizon check KILLED the headline.
Recording plainly; this is exactly what it is for.**
- **P18b DOWNGRADED — "planning stops scaling" was largely a horizon
  artifact.** Δ(team-costed − snhp+net) collapses from −0.053 (p=.008) at
  2,500t to **−0.004 (n.s.) at 7,500t**. Given a fair horizon the
  consensus-costed hive catches the market; the exciting 2,500t crossing
  was a within-window throughput effect, not a durable scaling law. The
  strong claim does NOT survive its own pre-registered horizon check.
- **P18c CONFIRMED REAL, not truncation.** The market still under-delivers
  the auction at N=240 at 7,500t (−0.020, p=.0156 — IDENTICAL to 2,500t).
  3× the time did not let the market catch the auction. The registered
  KILL fired for real: the IR market does not out-scale even a single-issue
  auction on delivered at N=240.
- **N=240 is un-clearable in 7,500t for every arm** (0% finish; all plateau
  ~0.83–0.85 delivered). The field grew 10× and the fleet grew 10×, but the
  logistics don't close the gap — so makespan is censored (all tied at cap),
  and the "market wins on speed" reading is scoped to N≤96 where fields
  actually clear (makespan 1,066 vs 2,232 at N=24).
- **What SURVIVES the horizon check:** P18a (market is O(1)/encounter,
  mechanically scale-free); the SPEED edge at clearable scales (N≤96);
  P18d (middlemen are a centralization phenomenon — a structural count,
  horizon-independent). **What DIES:** the claim that the market's
  advantage GROWS with scale. Honest headline: the market's edge is
  scale-limited and speed-shaped, not throughput dominance that widens
  with N. "Markets are what coordination looks like when planning stops
  scaling" is NOT supported by this benchmark — the costed hive keeps up
  given time.

---

## v17 pre-registration (column P): relays, hold-up, and pre-commitment — "the theory of the firm, staged by drones"

*Registered 2026-07-16, BEFORE implementation. Founder's insight, verbatim:
"maybe drones are too stupid to do trades across more than one individual
that would benefit the company but always leave a loser drone in the
middle … which leads to interesting experiments about how individual deal
making in drones maybe misses entity scale deal making" and "the relay
negotiation … requires like a pre-commitment mechanism from negotiations."
Theory framing: the middle drone's haul is a position-specific investment;
spot renegotiation at the second hop expropriates its quasi-rent (hold-up,
Williamson); anticipating this under IR, the first hop is refused and the
chain never forms. The classical cures are vertical integration (the firm
settles internally — Coase) and binding forward contracts. The contract
instrument registered here is a NEGOTIABLE DELIVERY CLAIM (bill of lading):
cargo carries a notarized payment-split vector fixed at each hop; terminal
delivery pays out per the recorded splits — pre-commitment via attestation,
i.e. the receipt as the commitment device.*

**PHASE 1 — DIAGNOSIS (build: instrumentation only). The N=240 plateau
(~0.83–0.85 for every arm, auction LEADING) must be decomposed before any
mechanism is credited. Candidate constraints and their signatures:**
- **Energy-throughput bound:** charger duty cycle ≈ saturated; delivered
  tracks total energy dispensed across arms; the plateau equals the energy
  budget's implied ceiling. (Back-of-envelope says this is plausible —
  registered as the EXPECTED primary constraint given the auction leads.)
- **Charger-queue bound:** high queue_wait with unsaturated dispensing.
- **Chain/hold-up bound:** far-ore (haul distance > single-charge loaded
  range ≈ 62 cells) delivery fraction decays with refinery distance in ALL
  arms; delivered units are overwhelmingly 0/1-hop; the rare multi-hop
  units show second-hop margin compression (the hold-up signature).
Metrics to add: per-unit hop count (provenance chain length), per-rock
delivered-vs-mined by distance band, charger duty cycle + dispensed energy,
hop-margin ledger. **GATE: Phase 2 is built ONLY if the chain signature is
present (far-ore decay + hop-count collapse), regardless of whether energy
also binds. If energy saturation alone explains the plateau, report that
and stop — relays cost MORE energy (transfer loss), so contracts cannot
help an energy-bound fleet.**

**PHASE 2 — PRE-COMMITMENT MECHANISMS (gated). Arms, all at N=240 scaled
grid + the N=24 baseline for regression:**
- **snhp+bill:** hop deals may bundle cargo WITH a recorded split of the
  terminal payout (split fixed by the Nash division at hop time; the deal
  log is the registry). Final deliverer triggers payout per splits. IR
  valuation of a claim share: share × rate × V_DELIVER × the same
  feasibility discount Φ's load term uses (deterministic ⇒ evaluated ==
  executed).
- **snhp+firm:** vertical integration control — within-company handoffs
  settle via the company treasury (haul cost + fixed margin on handoff,
  recouped at delivery). No cross-company relief.
- Controls: snhp+net spot (the hold-up baseline), auction (no-relay).
**Predictions:**
- **P23a:** bills lift N=240 delivered_frac ≥ +0.03 over spot, the lift
  concentrated in far-ore (distance-decay flattens), and ≥2-hop delivered
  share rises from ~0 to substantive.
- **P23b:** firm ≈ bills within-company; bills > firm on cross-company
  relays (integration cannot organize chains across the border).
- **P23c (mechanism):** spot's rare multi-hop deals show second-hop margin
  compression; bill-of-lading hops show NO compression (the split was
  fixed before position risk was taken).
- **P23d (make-or-buy, exploratory):** report where integration beats
  contracts and vice versa — the Coase boundary, measured.
- **KILL (phase 2):** if bills lift delivered_frac by ≤ +0.01 at N=240,
  chains were present but not binding; the plateau is physics; say so.

---

# THE CAPABILITY PROGRAM — seven pre-registrations (columns Q–W) + a P extension

*All registered 2026-07-16, BEFORE implementation. Founder: "I want to test
them all." Founder ideas: material→infrastructure, incentivized scouting,
granular claims + dumber drones, Dyson-swarm economics. Fable additions:
reputation-vs-receipts scaling, stigmergic order book, relay moral hazard,
matching-vs-market. Builds sequential (shared files), Opus builds, Fable
verdicts. Designs below are contracts; pre-build amendments allowed if
committed before any run.*

## v18 (column Q): endogenous infrastructure — "the sim grows landlords"

Material-bearing asteroids (a seeded fraction of rocks yield BUILD-MATTER
instead of ore). A company may spend matter + credits to PLACE a charger
(or, expensive tier, a refinery) at a chosen location. Guest rate on owned
chargers is the owner's choice from a small grid (the toll dial). Runs at
N=240 scaled grid where charging is the binding constraint (per P18).
- **P24a:** fleets that build chargers lift the N=240 plateau (delivered_frac
  +≥0.05 vs no-build control); placement clusters where far-ore decay was.
- **P24b (public goods):** under-provision emerges — total welfare-optimal
  charger count exceeds what either company builds alone; cross-company
  guest pricing sits above marginal cost (the toll-booth result recursing
  onto endogenous capital).
- **P24c:** a build-capable AUCTION fleet gains less than a build-capable
  bargaining fleet (infrastructure siting benefits from claim/deal
  coordination) — falsifiable; report either way.
- **KILL:** if building never beats saving the resources for direct
  operations, infrastructure is decorative at these scales.

## v19 (column R): emergent scouting — incentives instead of policy

Remove hardcoded K0 scouting. Arms: (a) discovery BOUNTY (company treasury
pays finder per new-rock unit discovered), swept over bounty levels;
(b) first-finder prospecting claim (existing K2 machinery, window as the
incentive); (c) gossip + intra-company map-DELTA sales (scouts can sell
fresh entries to fleet-mates — requires column O machinery); (d) K0
hardcoded (the policy ceiling); (e) no-scout control. Moving+contested
field.
- **P25a:** some incentive arm reaches ≥70% of hardcoded K0's
  arrival-capture; report the price of emergence (bounty level required).
- **P25b:** bounty overshoot exists — too-high bounties pull haulers off
  ore and delivered falls (an interior optimum, measured).
- **KILL:** if no incentive schedule produces patrol behavior, exploration
  is a planning good markets cannot buy in this world — report as such.

## v20 (column S): institutions as a substitute for cognition

2×2: navigation {smart (current Φ-routing), dumb (greedy nearest-known +
noise)} × property rights {coarse (current sectors), granular (per-rock
tradeable claims with K2-style windows)}. Same fields, same fleets.
- **P26a (the thesis cell):** granular rights recover ≥50% of the delivered
  gap that dumbing navigation opens (institutions buy back IQ).
- **P26b:** rights granularity helps dumb fleets MORE than smart ones
  (substitutes, not complements) — the interaction term is the result.
- **KILL:** if granular rights help nobody or only smart fleets,
  institutions complement rather than substitute cognition here.

## v21 (column T): the shading externality — a Coase boundary, measured

Solar-harvest preset: cells carry irradiance; parked drones harvest energy;
a drone harvesting within SHADE_R of another reduces its neighbor's intake
(continuous pairwise externality). Energy harvested replaces charger supply.
Arms: no-bargaining (externality unpriced), bilateral deals may bundle
"move/spacing" commitments (Coasean bargaining), tradeable SLOT claims
(property-rights allocation). Sweep DEAL_PAUSE as the transaction-cost dial.
- **P27a:** at low transaction cost, bilateral bargaining internalizes most
  shading loss (harvest approaches the spacing optimum) — Coase holds.
- **P27b:** raising DEAL_PAUSE degrades bargained internalization faster
  than slot-claims allocation — a measured Coase boundary where property
  rights beat renegotiation.
- **KILL:** if unpriced shading loss is <5% of harvest, the externality is
  too weak to test — re-tune SHADE_R by pre-committed rule, once.

## v22 (column U): reputation vs receipts — the scaling law of trust

Liars (v6 machinery) vs three enforcement regimes: (a) REPUTATION — pairwise
memory + gossip-borne blacklisting (community enforcement; no attestation);
(b) ATTESTATION (v6 gate, the receipt); (c) both. Across N ∈ {24, 96, 240}
and gossip noise (false-accusation rate ε ∈ {0, 0.05}).
- **P28a (the law):** reputation's honest-cooperation payoff decays with N
  (re-encounter probability falls); attestation's is N-flat. A crossover N
  exists: villages run on reputation, cities need receipts.
- **P28b:** under ε>0 slander, community enforcement degrades (honest
  drones get blacklisted); attestation is ε-immune.
- **P28c:** (c) ≈ (b) at large N — receipts subsume reputation.
- **KILL:** if reputation is N-flat too, the notary premise loses its
  scaling argument in this world — the single most thesis-relevant kill in
  the program; report loudly either way.

## v23 (column V): the stigmergic order book — posted offers dissolve the room

A drone may PIN a signed, binding limit order to a location (e.g., "pay X
energy on pickup of this cargo here", "sell claim on rock i for Y",
expiry T): commitment via attestation, asynchronous execution by whoever
arrives and accepts. Same primitive as P's bills, different surface.
Re-run the column-G geometry ladder with order books on.
- **P29a:** the meeting-density hump flattens — bargaining's edge at G=64
  recovers toward its G=48 level (posted offers let sparse fields trade).
- **P29b:** order books shift deal mix toward asynchronous trades most
  where encounter rates are lowest (mechanism check).
- **KILL:** if the hump survives order books intact, the constraint was
  never meetings — it was something else; diagnose before claiming.

## v24 (column W): matching vs market — when design beats exchange

Rock/task allocation via deferred-acceptance matching (drones rank rocks by
net value; rocks "rank" drones by expected extraction) recomputed on
arrival/depletion events, vs the existing claims market, vs greedy
best_claim. Static known field (isolate allocation).
- **P30a:** DA matching ≥ claims market on delivered at zero deal overhead
  (stability without prices) at N=24; the gap, if any, closes at N=96+
  (recompute latency scales worse than decentralized claims).
- **KILL:** if greedy ≈ both, allocation was never the constraint at these
  densities.

## P23e (column P phase-2 extension): moral hazard in the relay

Once bills exist: middle-hop effort is unobservable (lazy routing, risky
margins, cargo dwell). Contrast FLAT splits vs TIME-CONTINGENT splits
(payout share decays with hop dwell-time — the observable that Holmström's
informativeness principle says to contract on).
- **P23e:** flat-split relays show measurable shirking (dwell inflation vs
  the direct-haul counterfactual); contingent splits compress dwell toward
  efficient levels at equal or better delivered. KILL: no dwell inflation
  under flat splits ⇒ no moral hazard to price in this world.

**P21 VERDICT (2026-07-16, sweep_O.json, n=16, N=24): free radio was NOT
load-bearing — and one of our own earlier findings gets honestly downgraded.**
- **Column KILL does not fire:** gossip snhp+net (289–294 delivered) ≥
  free-radio control (284) ≥ auction (286–289). Every belief-mode result
  survives communication locality at this density.
- **P21a REFUTED, and it re-scopes P15b:** under local radio the deal
  economy holds NO freshness edge over the auction (Δstaleness n.s. at both
  radii). The celebrated "trading fleets hold 3× fresher maps" (v10/P15b)
  was a BROADCAST artifact — deals moved robots whose observations were
  then amplified by free company-wide radio; remove the radio and the
  auction's roaming senses just as well. The sensor-network claim is
  hereby scoped: it is a property of trade + broadcast, not trade alone.
- **P21b: the ladder splits exactly as registered.** Contact-only radio
  (r=2) bleeds books (+5.31 poisoned, p=.001, 14/16) at flat delivered —
  the FIFTH replication of "self-input error corrupts receipts before
  output" — while short radio (r=6) fully restores free-radio freshness
  and poisoning. Locality matters; RANGE beyond 6 cells does not.
- **P21c: the trade graph IS the information graph — but only once radio
  is local.** Freshness↔deal-degree correlation +0.13/+0.16 (hz p=.044)
  under gossip vs ~0 under broadcast and vs the 200-permutation null.
  Broadcast had erased the network structure; locality reveals it.
- **Scout-return problem did not materialize** at N=24 density (arrivals
  captured under gossip ≥ free radio): v12's "scouting fixes discovery"
  survives without global broadcast. The map market under gossip again
  buys freshness/integrity (staleness −6.0, p=.008), not throughput —
  third consistent verdict that information trade's product is audit
  quality.
- Builder correctness catch adopted: the rival-rate baseline
  (_own_mined_seen) must travel with gossiped last_seen or depletion
  deltas are mis-scored — documented in code.

**P-PHASE-1 DIAGNOSIS VERDICT + GATE DECISION (2026-07-16, registrar):**
- **Energy-bound: REFUTED — the registrar's own registered expectation was
  wrong.** Charger duty ~0.14–0.21 (nowhere near saturated); delivered
  does not track dispensed energy across arms. Recorded as my miss.
- **Queue-bound: PRESENT as localized contention** — 170k–291k robot-ticks
  of queue_wait alongside ~80% idle slot-time = siting maldistribution,
  not supply ceiling. This is direct motivating evidence for column Q
  (endogenous infrastructure): the fleet needs to BUILD/place chargers,
  not ration them.
- **Chain-bound: PRESENT — both registered signatures, plus the mechanism
  fingerprint.** Far-ore delivered/mined decays in ALL arms (≈1.00 near →
  0.35–0.45 far); delivered units are overwhelmingly ≤1-hop (97.6% for
  the IR market). And the hold-up theory's exact prediction realized in
  the IR-vs-team contrast: under IR there is NO second-hop margin
  compression because the veto refuses loss-making middle hops — so
  chains never form and far ore strands; under team (no per-side IR)
  ≥2-hop relays are ~12× more frequent and the middle drone is
  expropriated (buy-leg +14.7, sell-leg −10.5, 99% of legs compressed) —
  the founder's "loser drone in the middle," measured. Refuse the chain
  or eat the loss: pre-commitment is precisely the missing instrument.
- **GATE: OPEN.** Per the registered rule (chain signature present ⇒ build
  Phase 2 regardless of other constraints), the bills-of-lading and
  firm-settlement arms proceed to build. P23a's lift prediction now has a
  measured target: the far-band 0.40 → toward the 0.93 mid-band.

**P-PHASE-2 BUILD NOTE (2026-07-16, committed BEFORE the P2 run — the
operative interpretation of the two mechanisms, so the numbers that follow
were pre-registered against these exact rules):**
- **snhp+bill (World.bills).** Each parcel carries a `claims` stack of
  (rid, share); the current HOLDER owns the residual 1−Σshare. Φ (scalar
  dispatch — `_fast_ok` excludes bills) values carried cargo at the holder's
  RESIDUAL units (the load term's feasibility discount, unchanged) and ADDS
  the robot's outstanding own-claims UNDISCOUNTED (`Robot.claim_value`): a
  claim pays at delivery regardless of the claimant's position, which is the
  pre-commitment — it lifts the feasibility discount off the value a far
  middle drone locks in when it sells, so the sell-leg clears IR where spot's
  hold-up refused (unit-verified: the exact A→B→C hop returns sol=None under
  spot, a strictly-positive symmetric split under bills).
- **The split rule, made evaluated==executed-safe.** "The Nash division of
  the CARGO-VALUE component determines the shares" is implemented as a 1-D
  Nash bargain over splitting the moved residual between the giver's
  UNDISCOUNTED claim and the receiver's DISCOUNTED carried residual, whose
  maximiser is α* = (1 + giver_feasibility_disc)/2 — the giver's claim
  fraction. Because α* depends ONLY on the giver's PRE-deal discount it is
  split-INDEPENDENT (identical in evaluation and at execution), which is what
  lets the claim be attached deterministically before the in-arm evaluated Φ
  == executed Φ assert (the assert runs live through the 600-tick test and
  the full grid). Claim valuation uses rate 1.0·V_DELIVER; the actual payout
  at delivery uses the delivering refinery's tariff-adjusted rate (Φ is a
  heuristic; conservation is enforced on the realized credit).
- **Credit conservation.** At delivery each unit's `earned = rate·V·q` is
  split across its claim stack (each claimant paid share·earned, booked to the
  CLAIMANT's company) with the deliverer keeping the residual — Σ == earned
  exactly. Extended as `World.credit_conserved()` (Σ robot credit + treasury
  == company booked credit, per company); holds for every prior arm too.
- **snhp+firm (World.firm_relay).** A within-company handoff settles through
  `company[c]["treasury"]`: it advances the receiver a transfer price
  (marginal shadow-priced haul + FIRM_MARGIN=0.15 of home value), tagged onto
  the moved parcels and recouped from whoever delivers them (net-zero within
  the company). This re-books credit only — it NEVER touches Φ/physics/RNG —
  so the fast path stays and firm's trajectory is BIT-IDENTICAL to spot (the
  Coase-boundary control: integration via transfer PRICING alone cannot
  re-route Φ-driven haulers, so it forms no new chains; measured, not
  asserted). Cross-company handoffs are untouched spot.

**P23 VERDICT (2026-07-16, registrar) — the founder's pre-commitment
theory CONFIRMED; the program's strongest mechanism result.**
- **P23a SUPPORTED:** negotiable delivery claims (bills of lading) lift
  N=240 delivered_frac +0.0295 (p=.005, 7/8), concentrated exactly where
  phase 1 said the bodies were: far-band delivered/mined 0.40 → 0.47, and
  ≥2-hop delivered share 0.025 → 0.500 — a 20× rise in real relay chains.
  The KILL (≤+0.01) did not fire. Chains were binding; pre-commitment
  forms them. Bonus mechanism dividend: stranding halves (2.12 → 1.12) —
  dying carriers offload cargo to a claim before the strand.
- **P23b REFUTED, informatively — with a scoping caveat.** The firm arm
  (treasury transfer pricing, haul cost + 15% margin) is EXACTLY inert:
  zero new chains, trajectory bit-identical to spot. Reason: re-booking
  credit does not change what a drone's Φ values; bills DO (a locked
  claim on the terminal payout enters the holder's objective). The honest
  scope: we tested integration-as-settlement, not integration-as-command
  (a firm that ORDERS the relay would be a different arm). Within that
  scope the Coase boundary is sharp: **a coordination mechanism must
  change the agent's objective, not just the internal price.**
- **P23c CONFIRMED — the hold-up fingerprint:** 67k bill-relay legs show
  NO sell-side compression (meanΔ +0.08); the split predates the position
  risk, so there is no quasi-rent to expropriate. Spot shows none either —
  because its veto refuses the compressible hops and the chains never
  exist. Exactly the registered two-sided prediction.
- **Thesis translation, on the record:** the notarized claim stack IS the
  snhp receipt, acting not as audit integrity but as WORKING CAPITAL —
  attestation-backed pre-commitment forms supply chains that spot
  bargaining structurally cannot. Receipts don't just keep books honest;
  they make chains exist. P23e (moral hazard / contingent splits) is now
  buildable and queued.

**P23e RESULTS (2026-07-16, sweep_v4_P3.json — report, not verdict; the numbers,
loudly either way).** The P23 phase-2 grid (N∈{24 (16 seeds), 240 (8 seeds)},
grid 32/101, σ=0.5, τ=0.15, v5, 2,500 ticks) × {spot (snhp+net, no claims), FLAT
(snhp+bill, α* Nash split fixed at hop time — the shipped P23 mechanism),
CONTINGENT (snhp+billC)}, all dwell-instrumented. Dwell = ticks a parcel sits in a
carrier's hold between acquisition and handoff/delivery; the direct-haul
counterfactual is the GEODESIC — manhattan(acquire_pos, handoff_pos) at 1 cell/tick,
so excess = dwell − cf ≥ 0 always (net displacement ≤ ticks moved). Per-leg dwells
telescope to the parcel's total hold time (test-enforced). CONTINGENT decays each
recorded claim's payout by exp(−λ·excess) of that carrier's OWN leg dwell above its
cf (Holmström's informativeness principle; λ=0.05 registered ⇒ ~14 idle ticks halve
the share); the DELIVERER absorbs the dock, so Σ credit conservation is exact.
- **The KILL does NOT fire — flat splits shirk, measurably and largely.** At N=240
  a bills-FLAT parcel sits **195.0 ticks over its geodesic** vs spot's 78.5 (journey
  dwell 231.7 vs 114.2 over the SAME ~35-tick counterfactual). Paired **flat−spot
  Δinflation = +116.6 ticks/parcel (p<0.001, 8/8 seeds)**. Relay legs carry it: the
  bills chains that P23a formed (≥2-hop share 0.025→0.492) dwell far above the
  direct haul. There IS moral hazard in this relay to price. (N=24 echoes it
  smaller: flat−spot Δinfl +8.1 all p=.001 14/16; +37.9 on ≥2-hop legs p<.001.)
- **CONTINGENT compresses dwell exactly as predicted — strongly, every seed.**
  N=240 contingent−flat **Δinflation = −88.4 ticks (all parcels, p<0.001, 0/8 above
  zero = every seed compressed)**; on **≥2-hop parcels −102.3 (p<0.001, 0/8)**.
  Relay-leg idle time nearly halves (35.6→19.8 ticks). Journey dwell 231.7→142.1.
  The observable-contingent contract works as an incentive: pricing dwell shrinks it.
- **BUT "at equal or better delivered" is REFUTED — the compression eats P23a's
  far-band gain.** Contingent buys the shorter dwell by shrinking the very chains it
  disciplines: N=240 ≥2-hop share **0.492→0.310**, delivered_frac **0.857→0.819
  (BELOW even spot's 0.829)**, and far-band delivered/mined **0.470→0.368 — under
  spot's 0.399, reversing the P23a signature lift (0.40→0.47) it was built on.** The
  decayed claim lowers the far middle drone's Φ payoff for precisely the long-dwell
  relay hops, so contingent compresses dwell partly by hauling faster and partly by
  DECLINING the hard far relays — some far ore re-strands rather than relaying. It is
  a real dwell price, but this Holmström-clean form (decay my own leg) overtaxes the
  marginal far relay. Stranding stays halved vs spot (1.00 vs 2.12), as under flat.
- **P23c HOLDS under contingent — no hold-up reintroduced.** N=240 middle-leg
  meanΔ: spot +2.52, flat +0.07, contingent **+0.17 (≥0 ⇒ no sell-side
  compression)**. Pricing dwell does not resurrect the quasi-rent expropriation;
  the split still predates the position risk.
- **λ-sensitivity (N=240 contingent): the far-band regression is intrinsic, not a
  single-λ artifact.** λ=0.025 → (dFrac 0.827, ≥2hop 0.348, far 0.39, infl_all
  121.5); λ=0.05 → (0.824, 0.310, 0.39, 108.2) — monotone: heavier decay compresses
  more (infl↓) and forms fewer chains (≥2hop↓), and far d/m sits **below spot's 0.40
  at BOTH λ**. Softening the decay recovers chains toward flat but proportionally
  gives back the compression; no λ in this range delivers dwell-compression AND
  P23a's far-band lift together.
- **Read on P23e vs the KILL.** KILL refuted: flat relays inflate dwell far above
  the direct-haul counterfactual (moral hazard is real and priceable). The P23e
  prediction SPLITS — dwell compression SUPPORTED and clean (−88/−102 ticks, every
  seed, no hold-up), the "equal-or-better delivered" clause REFUTED (−0.04 delivered,
  P23a's far-band lift reversed). The honest translation: a receipt that prices the
  carrier's dwell IS an enforceable effort contract, but taxing each middle drone on
  its own leg time overtaxes the far relay the working-capital claim was there to
  finance — the informativeness gain and the chain-formation gain trade against each
  other. A dwell price that docks idle time WITHOUT penalizing the productive length
  of a far haul (e.g., contract on excess-over-geodesic only above a slack band, or
  on the chain's aggregate vs its direct counterfactual rather than per-leg) is the
  open follow-up; the per-leg Holmström contract as specified compresses dwell at a
  measured cost of ~4% delivered and the far-band reach.

**P28 RESULTS (2026-07-16, sweep_v4_U.json, 16 seeds N≤96 / 8 seeds N=240,
liar_frac=0.25 — REPORT, not verdict; the numbers, loudly).** Four regimes on
the column-E TrustArm: (a) reput = trust-open + per-robot blacklists; (b)
attest = trust-gated (v6 receipt); (c) both; (d) neither (exploitation
baseline). Marks = own realized surplus below the reported basis; slander ε via
a dedicated stream; blacklists spread by contact (r_radio=6).
- **The exploitation baseline is stark and validates the setup.** Naive
  cooperation lets liars strip the honest: liar advantage +179 / +157 / +84
  at N=24/96/240. Both enforcement mechanisms crush it toward single digits.
- **P28a driver CONFIRMED, the prediction MIXED.** Re-encounter falls with N
  in the clean (low-deal) regimes: reput 106.6→37.1→31.8, both 78.0→35.6→28.6.
  Reputation's honest payoff DOES decay (91.5→85.9→58.9). BUT **attestation is
  NOT N-flat** — it collapses at N=240 (96.5→96.8→40.3), and **the crossover
  runs BACKWARDS: reputation BEATS receipts at scale** (N=240 honest 58.9 vs
  40.3; delivered 1503 vs 996). Mechanism: attestation keeps a huge cooperative
  tier alive (12.5k deals at N=240) whose DEAL_PAUSE immobilization throttles
  throughput, while reputation carpet-blacklists (~96% of honest robots marked)
  and collapses the tier to ~500 deals — losing the exploitable cooperation but
  also its deal-pause tax. "Cities need receipts" is UNSUPPORTED in this world.
- **P28b UNTESTABLE as specified — the false-blacklist channel is already
  SATURATED at ε=0.** Outcome-based marking cannot tell a liar-strip from a
  benign joint-max SACRIFICE (own surplus is the only decentralised signal; the
  two loss distributions overlap, n=292 vs 672), so ~96% of honest robots are
  already blacklisted without any slander. Adding ε=0.05 moves honest payoff
  −2.3/+0.3/+2.2 (noise) and false-BL 0.965→0.962 (flat). Attestation is
  ε-immune by construction (no blacklist). The registered "slander degrades
  reputation" cannot be seen because reputation is ALREADY maximally noisy.
- **P28c REFUTED (reversed).** (both) does NOT converge to (attest) at large N;
  it tracks REPUTATION — the aggressive blacklisting dominates the combined
  regime (N=240: both honest 60.2 & deliv 1630 ≈ reput 58.9 & 1503, NOT attest
  40.3 & 996). Receipts do not subsume reputation here; reputation subsumes the
  combination.
- **KILL (reputation N-flat ⇒ notary loses its scaling argument): does NOT fire
  on the literal criterion** — reputation's payoff decays and its driver falls.
  **But the thesis-relevant reading is worse than the registered KILL feared:**
  in this world the receipts-scale-better-than-reputation ARGUMENT is reversed
  — outcome-based reputation is a BLUNT instrument (carpet-blacklist) that
  needs no re-encounter precision to suppress exploitation, so it scales at
  least as well as attestation and out-delivers it at N=240. The honest scope:
  this is reputation-by-REALIZED-OUTCOME on a naive-cooperation mechanism; a
  reputation that could observe counterpart honesty directly (not just own
  loss) would blacklist far less and the comparison could differ.

**P28 VERDICTS (2026-07-16, registrar).**
- **P28a: driver CONFIRMED, headline REFUTED-AS-REGISTERED — with a declared
  horizon confound.** Re-encounter probability falls with N and outcome-based
  reputation's honest payoff decays with it, exactly as registered. But
  attestation is NOT N-flat, and the crossover runs BACKWARDS at N=240
  (reput 58.9 honest / 1503 delivered vs attest 40.3 / 996). The mechanism is
  identified, not mysterious: attestation preserves a large cooperative tier
  (12.5k deals) that pays the DEAL_PAUSE consensus tax on every deal, while
  carpet-blacklisting reputation burns cooperation down to ~500 deals and
  dodges the tax. **This is the P18 trap signature**: coordination costs are
  paid up front and recouped late, and this ran at 2,500 ticks — the horizon
  at which P18's market also beat the costed hive before the 7,500-tick
  amendment reversed it. No headline until the amendment below runs.
- **P28b: UNTESTABLE-AS-REGISTERED — and the reason is itself a finding.**
  The false-blacklist channel saturates at ε=0 (~96% of honest robots marked)
  because own-realized-surplus, the only decentralised observable, cannot
  distinguish a liar's strip from a benign joint-max sacrifice. Slander
  immunity is moot when honest inference is already maximally noisy: the
  bundling-or-silence law recursing into enforcement — outcome signals
  without attested books convict the innocent at the base rate of sacrifice.
- **P28c: REFUTED (reversed).** (both) tracks reputation, not attestation:
  aggressive blacklisting pre-empts the trust gate. Receipts do not subsume
  outcome-based reputation; the blunt instrument dominates the combination.
- **KILL: does not fire on the literal criterion** (reputation is not N-flat).
  The thesis-relevant reading is held pending the horizon amendment, and is
  scoped either way: what was tested is reputation-by-REALIZED-OUTCOME under
  naive cooperation; where coordination is cheap (N≤96) receipts BEAT
  reputation on both selectivity and payoff (96.5/96.8 vs 91.5/85.9) — the
  registered folk theorem "villages run on reputation" is itself inverted.

**P28-H AMENDMENT (registered 2026-07-16, BEFORE the run).** Re-run N=240,
ε=0, all four regimes, 8 seeds, at ticks=7,500 (the P18 fair-horizon
standard). Prediction (mine, on the record): attestation's cooperative tier
recoups the pause tax and the N=240 reversal narrows or flips — if it does
NOT, the "receipts out-scale reputation" argument is dead in this world at
any horizon we can afford, and the notary's scaling story must rest on
selectivity (who keeps honest cooperation) rather than throughput. KILL for
the amendment: attest still < reput on honest payoff AND delivered at 7,500
ticks ⇒ record the reversal as robust and say so loudly.

**P28-H RESULTS (2026-07-16, sweep_v4_UH.json — N=240, ε=0, 8 seeds,
ticks=7,500 = 3× the sweep_v4_U horizon; REPORT, not verdict; the numbers,
LOUDLY).** Identical to sweep_v4_U's N=240 ε=0 cells except the horizon: same
four column-E TrustArm regimes, σ=0.5, τ=0.15, liar_frac=0.25, v5 scaled grid
(grid=101). 32 runs, ~4.8 min wall-clock on 12 workers.

**THE 2,500 → 7,500-TICK REVERSAL FLIPS. The 2,500-tick "reputation beats
receipts at N=240" was HORIZON TRUNCATION, not a scaling law.** At the fair
horizon attestation OVERTAKES reputation on BOTH metrics the amendment named:

| N=240, ε=0 | honest 2500→7500 | deliv 2500→7500 | coop deals 2500→7500 | liar adv 7500 | reEnc 2500→7500 |
|---|---|---|---|---|---|
| reput   | 58.9 → **59.1** | 1503 → **1508** | ~500 → 497    | +5.5   | 31.8 → 98.8 |
| attest  | 40.3 → **90.4** | 996 → **1975**  | 12.5k → 34.5k | **−37.3** | — → 70.7 |
| both    | 60.2 → 60.4     | 1630 → 1640     | — → 587       | +21.3  | 28.6 → 89.8 |
| neither | — → 27.4        | — → 1827        | — → 44.8k     | +189.9 | — → 76.0 |

- attest honest 40.3 → **90.4** (now **+31.3 ABOVE** reput's 59.1); attest
  delivered 996 → **1975** (now **+468 ABOVE** reput's 1508). The 2,500-tick
  reput>attest ordering on honest AND delivered is **GONE.** The amendment
  KILL (attest still < reput on BOTH) does **NOT fire.**
- **Registered prediction CONFIRMED — and it FLIPS, not merely narrows:**
  attestation's cooperative tier recoups the DEAL_PAUSE tax and passes
  reputation on both axes at the fair horizon.

**Tier-size & pause-tax accounting (WHY it flips).**
- **Reputation's tier is DEAD and SATURATED.** It carpet-blacklists ~96% of
  honest robots (falseBL 0.968, blMean 172/240) and collapses cooperation to
  ~500 deals. Those deals are exhausted early: delivered 1503 → 1508 and
  honest 58.9 → 59.1 are FLAT across 3× the horizon. Reputation cannot convert
  more time into more delivery — there is no live tier left to run. Its
  re-encounter climbs 31.8 → 98.8 only because the same frozen handful of
  un-blacklisted pairs re-meet ~3× as often.
- **Attestation's tier is LIVE and keeps delivering.** 12.5k → 34.5k deals
  (scales ~with horizon), each paying the DEAL_PAUSE immobilization tax. At
  2,500 ticks that tax was paid up front but the deliveries had not accrued
  (996 delivered, honest 40.3 — mid-amortization). By 7,500 ticks the live
  tier's throughput dominates: 1975 delivered (HIGHEST of all four regimes),
  honest 90.4 (HIGHEST). The pause tax is a fixed per-deal cost; over 3× the
  horizon the delivery yield of a live cooperative tier overtakes a dead one.
- **Attestation is the ONLY regime where lying is net-negative:** liar adv
  −37.3 (honest 90.4 > liar 53.1). Reputation only crushes adv to +5.5;
  neither runs wild at +189.9; both tracks reputation at +21.3 — the P28c
  reversal HOLDS at horizon (combining does not help; blacklisting pre-empts
  the gate).

**Scope & caveats.** ε=0 only — the amendment dropped the slander channel
(P28b was already untestable at ε=0: outcome-marking saturates the
false-blacklist rate on benign joint-max sacrifice, so u_report's [4] ε-table
is EMPTY by design here). This is reputation-by-REALIZED-OUTCOME under naive
cooperation; a reputation that could observe counterpart honesty directly
would blacklist far less. Within that scope the 2,500-tick headline is
RETRACTED: **receipts DO out-scale outcome-based reputation at N=240 once the
horizon is fair** — attestation delivers most, pays honest cooperation best,
and is the only mechanism under which lying does not pay.

**One-paragraph read — truncation or robust?** The reversal is **horizon
truncation, decisively.** The discriminating fact is that reputation's
delivery is FLAT (1503→1508) while attestation's nearly DOUBLES (996→1975)
over the same added 5,000 ticks: reputation has no live cooperative tier left
to convert time into output, whereas attestation does. At 2,500 ticks we
caught attestation mid-amortization — the DEAL_PAUSE tax on its 12.5k-deal
tier was fully paid but the deliveries it buys had not yet accrued, so it
looked dominated. Extend to the P18 fair horizon and the live tier's
throughput overtakes the dead one on every axis (honest +31, delivered +468,
and uniquely negative liar advantage). This is the textbook **P18 trap
signature** — coordination costs paid up front, recouped late — resolving
exactly as P18's own market-vs-hive amendment did. The "cities need receipts"
claim, buried by the 2,500-tick run, is **REINSTATED at N=240 for any horizon
long enough to amortize the pause tax.**

**P28-H VERDICT (2026-07-16, registrar) — the reversal was horizon
truncation; "cities need receipts" REINSTATED.**
- **Amendment prediction CONFIRMED (it flips, not narrows).** At 7,500 ticks,
  N=240: attest honest 90.4 vs reput 59.1 (+31.3), delivered 1975 vs 1508
  (+468). The amendment KILL does not fire. The discriminating fact:
  reputation's cooperative tier is DEAD (delivery flat 1503→1508 across 3×
  the horizon — carpet-blacklisting cannot convert time into output) while
  attestation's is LIVE (12.5k→34.5k deals, delivery ~doubles). At 2,500
  ticks we caught attestation mid-amortization: pause tax fully paid,
  deliveries not yet accrued. Second time the fair-horizon amendment has
  reversed a coordination-cost headline (P18, P28) — the truncation trap is
  now a named reviewer check for every coordination mechanism in this world.
- **P28a CLOSED post-amendment: no crossover exists in receipts' disfavor.**
  At fair horizon receipts beat outcome-based reputation at every N tested
  (N≤96: 96.5/96.8 vs 91.5/85.9; N=240: 90.4 vs 59.1). The registered folk
  theorem inverted fully: villages run on receipts too. Attestation is also
  the ONLY regime where lying is net-negative (liar adv −37.3 vs reput +5.5,
  both +21.3, neither +189.9).
- **P28c reversal HOLDS at horizon — a design warning, not a footnote:**
  bolting outcome-based reputation ONTO receipts makes the system worse
  (both: 60.4/1640 — tracks reputation, +21.3 liar adv). The blunt blacklist
  pre-empts the trust gate and burns the tier the receipts were protecting.
  Do not combine notarized attestation with naive outcome scoring.
- **Distribution vs throughput:** neither delivers 1827 (> reput) but honest
  payoff 27.4 with liar adv +189.9 — naive cooperation produces plenty and
  the honest keep none of it. Receipts are not (only) a throughput
  technology; they are who-keeps-what technology that HAPPENS to also win
  throughput at fair horizon.
- **Thesis translation, both halves now measured:** receipts make chains
  exist (P23) and receipts out-scale reputation at fair horizon (P28/P28-H)
  — because own-outcome signals cannot distinguish a liar's strip from a
  partner's benign sacrifice (the confound that saturates blacklists), and
  the receipt is precisely the instrument that makes counterpart honesty
  observable instead of inferred.

## v25 (column X): the firm's interior — command, prices, or claims

The branch P23b explicitly left open (integration-as-COMMAND untested) plus
the intra-company translation of the ladder: one company owns the whole
fleet; the question is what allocation mechanism runs its interior. Three
regimes, off-by-default flags, all prior columns bit-identical:
- **(a) COMMAND** — a central planner assigns tasks/hand-offs directly and
  the drone's decision rule is REPLACED by the assignment (this is what
  "changing the objective" looks like from above). Honesty constraint,
  registered now so command gets no free oracle: the planner plans on the
  company's gossip-merged belief under local radio (P21 realism), not on
  field truth, and assignments propagate by the same radio physics.
- **(b) INTERNAL PRICES** — the P23b transfer-pricing arm, unchanged: the
  measured-inert control.
- **(c) CLAIM SETTLEMENT** — the bills machinery run INSIDE the firm: units
  keep their own ledgers and are paid on attested claim stacks against final
  delivery (the P23 objective-change, without a planner).
Grid: N ∈ {24, 96, 240} × ticks ∈ {2,500, 7,500} — the fair-horizon pair is
MANDATORY per the truncation-trap rule (P18, P28-H); σ=0.5, τ=0.15, v5
scaled grids, 16 seeds (8 at N=240).
- **PXa:** command wins at small N (the planner's belief covers the field;
  zero bargaining overhead) and degrades with N as the gossip-merged plan
  goes stale faster than assignments execute — books-bleed-first, but for
  the planner.
- **PXb:** internal prices remain statistically indistinguishable from the
  no-mechanism baseline at every N and horizon (P23b replicates in the
  intra-firm frame).
- **PXc:** claim settlement wins at N=240 at 7,500 ticks, with internal
  ≥2-hop hand-off share exceeding both alternatives (the P23 chain result,
  transplanted inside the boundary).
- **KILL (the doctrine kill):** if command ≥ claim settlement at N=240 /
  7,500 ticks, then receipts add nothing over hierarchy inside the firm in
  this world — central planning on shared belief is enough, and the
  agent-fleet "internal notary" doctrine dies. Report loudly either way.
Business translation on the record: this is the allocation question every
operator of an internal AI-agent fleet is currently answering by vibes —
command (orchestrator assigns), chargeback (measured inert), or attested
claims on outcomes. Whichever way it falls, the result is the doctrine
chapter of the follow-up article.

**PX RESULTS (2026-07-16, sweep_v4_X.json — report, not verdict; the numbers,
loudly either way). One firm owns the fleet; four interior regimes on ONE
information environment (P21 realism — belief maps + gossip, r_radio=6, so
COMMAND gets NO free oracle and all four share the same single-hop routing
competence): the no-mechanism BASELINE (default solo objectives), (a) COMMAND
(a central planner replaces the drone decision rule — deconflicted mine beats +
directed local single-hop hand-offs, propagated from HQ by the SAME radio
physics as gossip; the mechanical deliver/charge reflexes stay the shared
primitives, the P24 caveat), (b) INTERNAL PRICES (the P23b firm_relay transfer
price, unchanged), (c) CLAIM SETTLEMENT (the P23 bills machinery inside the
firm). N ∈ {24,96,240} × ticks {2500,7500} (the fair-horizon pair), σ=0.5,
τ=0.15, v5 scaled grids, 16 seeds / 8 at N=240. lineage + the routing-deadlock
instrument on for all four. Material + ledger + credit conservation green across
all 320 runs.

- **delivered_frac by regime × N (both horizons; the N=240 plateau is the
  headline):** N=24 baseline/prices 0.999, claims 0.996, command 0.852. N=96
  baseline/prices 1.000, claims 0.999, command 0.975–0.988. **N=240 baseline
  0.825, prices 0.825, command 0.790→0.814, claims 0.863→0.873.** Only CLAIMS
  lifts the P24 charge-routing plateau (0.825 → 0.873 at the fair horizon).**

- **THE KILL DOES NOT FIRE — receipts beat hierarchy inside the firm.** At
  N=240 / 7,500 ticks: claims delivered 2096.0 vs command 1954.8, Δ(command −
  claims) = **−141.2, p=0.001, 0/8 seeds**. Command is NOT ≥ claims; the
  agent-fleet "internal notary" doctrine SURVIVES. Central planning on shared
  belief does not match attested claims on outcomes in this world.

- **PXa REFUTED (both directions of the prediction fail on the WIN, hold on the
  MECHANISM).** Command was predicted to WIN at small N and degrade with N.
  Instead command LOSES at every cell: command − baseline delivered = −35.2@N24,
  −24.2@N96/2500, −11.5@N96/7500, −83.5@N240/2500, −25.8@N240/7500 (this last
  p=0.248, 3/8 — command only ties baseline at the fair horizon at scale, as the
  staleness self-corrects over the long clock). The predicted small-N advantage
  (deconfliction + zero bargaining overhead) is DOMINATED, even at N=24, by the
  registered failure mode itself: plan-staleness. Belief-age of the assignments
  at source grows 8.8 → 21 → 49.6 with N; assignment reach-latency 7.8 → 17.6 →
  41.7. At N=240 the plan is ~50-tick-stale when computed and ~42 ticks in
  transit — ≈90-tick-stale by execution — and command forms NO opportunistic
  chains (≥2-hop share 0.000 at every cell). The "books-bleed-first, for the
  planner" MECHANISM is real and measured; it just bleeds at ALL N, not only
  large N, so the small-N-win half of PXa is refuted.

- **PXb CONFIRMED — maximally.** Internal prices are BIT-IDENTICAL to the
  baseline on delivered at every N and horizon (Δ = +0.0, all seeds). The
  transfer price is a pure credit reallocation that never touches physics/Φ/RNG,
  so throughput is provably unchanged — it moves ONLY the internal payout
  distribution (per-drone credit Gini 0.541 → 0.528 at N=240). The measured-inert
  control replicates exactly in the intra-firm frame: chargeback changes
  who-gets-paid, never how-much-gets-delivered.

- **PXc CONFIRMED.** Claims − baseline delivered = **+91.8 @ N=240/2500 (p=0.001,
  8/8)** and **+115.5 @ N=240/7500 (p<0.001, 8/8)**, with the internal ≥2-hop
  hand-off share **0.514 / 0.520 vs 0.023 (baseline & prices) and 0.000
  (command)** — claims' relay share exceeds every alternative by ~20×. At small N
  (24, 96) claims ≈ baseline (−0.6/−0.4, n.s.): the dense field is not
  chain-bound there, so the receipt adds nothing — exactly the P23 signature,
  transplanted inside the firm boundary. The claim stack is the only instrument
  that forms the far-frontier chains, and it is the only one that moves the
  plateau.

- **CONTAMINATION CHECK — the decomposition holds, and the instrument itself
  taught us something.** Routing-deadlock entries (loaded, ~full battery,
  refinery-unreachable-in-one-hop): command ≈ baseline ≈ prices (N=240: command
  369 / 455 vs baseline 434 / 438 vs prices 434 / 438) — command is NOT
  routing-advantaged (it uses no bespoke router, has ~the same deadlock rate, and
  LOSES on delivered), so the P24-caveat concern is satisfied and the
  command-vs-claims comparison is clean on the routing axis. CLAIMS shows ~4×
  MORE entries (1767 / 1933). This is NOT a routing edge but SETTLEMENT resolving
  the deadlock: a stuck loaded drone hands its cargo to a passer via a claim and
  cycles BACK to the frontier, re-entering the loaded-stuck state — so a
  mechanism that RESCUES deadlocks generates MORE entries. The registered
  assumption ("counts ~equal iff routing competence shared") is falsified in an
  informative direction, and the settlement-vs-routing split is exactly what the
  4× gap decomposes: same routing everywhere (command≈baseline≈prices), claims'
  win is the recycled frontier throughput (2400 ore, +115 delivered at the fair
  horizon).

- **Read (KILL headline).** Inside one firm's fleet, the allocation contest
  resolves for ATTESTED CLAIMS ON OUTCOMES over CENTRAL COMMAND and over INTERNAL
  CHARGEBACK. Command is beaten by its own information latency — a plan on
  gossip-merged belief is stale by the time it reaches the edge, and directed
  assignment forms none of the opportunistic ≥2-hop chains that clear the
  scale-binding hold-up. Chargeback is provably inert on throughput. Only the
  receipt makes a stuck-drone hand-off worth striking, and only the receipt lifts
  the N=240 plateau P24 diagnosed as charge-ROUTING. Thesis translation, on the
  record: the internal-notary doctrine LIVES — an AI-agent fleet's interior wants
  receipts on delivered outcomes, not an orchestrator's standing orders and not a
  transfer-pricing book. Design caveats honoured: command got only shared
  single-hop primitives (verified routing-neutral by the deadlock instrument),
  planned on merged belief not field truth, and propagated orders by contact;
  the evaluated Φ == executed Φ assert scopes to the bargaining path, which
  command's direct-transfer hand-offs never enter (documented in CommandArm).

**P23e VERDICTS (2026-07-16, registrar).**
- **KILL REFUTED — moral hazard in the relay is real and large.** A
  bills-flat parcel sits 195 ticks over its direct-haul geodesic vs spot's
  78 (+116.6/parcel, p<.001, 8/8 seeds at N=240). Once the claim stack
  guarantees a carrier's split regardless of haste, carriers dawdle. There
  is something to price.
- **P23e SPLITS, and the split is the finding.** Compression: SUPPORTED
  cleanly — exp-decay on own-leg excess dwell cuts inflation −88.4 all /
  −102.3 on ≥2-hop legs, every seed, with NO hold-up reintroduced (middle
  margins stay ≥0; the P23c property survives the contract change).
  Equal-or-better delivered: REFUTED — delivered 0.819 < spot's 0.829, and
  far-band d/m 0.368 falls UNDER spot's 0.399, erasing the entire P23a lift
  (0.40→0.47). Monotone in λ; intrinsic, not a tuning artifact.
- **Diagnosis (Holmström, applied honestly):** dwell is informative about
  effort but MORE informative about assignment difficulty. Far relays have
  intrinsically long, variance-heavy dwell (congestion, charge stops,
  rendezvous waits — none of it shirking), so a per-leg dwell price is a
  tax on exactly the hard hops the bill existed to finance. The claim
  stack's economic function (P23) is INSURANCE against position risk;
  naive incentive terms claw back the insurance, and the far chains
  dissolve again. Pricing an observable is not pricing effort.
- **Thesis translation:** the receipt can carry incentive terms, but
  performance-linked receipts must contract on CONTROLLABLE excess (slack
  band above the counterfactual, or the chain's aggregate dwell vs its
  direct-haul counterfactual) or they burn the working-capital function
  that made chains form. Business shadow, on the record: an SLA that
  penalizes raw latency instead of controllable latency makes carriers
  refuse hard routes — we just watched it happen. The builder's follow-up
  (slack-band / chain-aggregate contract) stays REGISTERED-OPEN; queue
  priority remains V → Q → X.

## v26 (column Y): the ant farm — a company you can watch

Founder-directed (2026-07-16). Column X's mechanics in an office-building
cross-section: floors = hierarchy, offices = roles, hallway traffic =
hand-offs, mailroom = task queue, wall ledger = claim stacks, promotion =
a literal floor move. The building is a RENDER LAYER ONLY — treatments,
predictions, and kills live underneath, and the costume must never drive
the science. Three gated phases; fair-horizon pair mandatory wherever a
coordination mechanism is scored (P18/P28-H rule).

**Y1 — the renderer (artifact, no verdict).** Building-cross-section
replay over THIS research pipeline's own event logs: contracts registered,
builders spawned into worktrees, tests gated, merges, verdicts. Honesty
constraints, registered: render only real logged events (no fabricated
activity, no decorative agents); time compression declared on screen; the
work products rendered are the public repo's actual commits. Ships as the
"the method is the demo" artifact; assets local until founder publishes.

**Y2 — endogenous structure (the science; sim employees, engine agents).**
Column X's interior regimes + a MUTABLE org chart. A promotion/demotion
rule runs every K ticks over a verifiable task queue (tasks = ore with
hidden acceptance checks; false completion claims = the v6 liar machinery
transplanted). Treatments:
- (a) OUTCOME promotion — rank on realized output score alone (the U
  confound, made organizational);
- (b) RECEIPT promotion — rank on attested contribution claims (verified
  deliveries credited via claim stacks, incl. middle-hop credits);
- (c) STATIC control — no structure change;
- (d) REORG-WITHOUT-SETTLEMENT — structure mutates per (a)'s rule but
  payout/settlement rules never change (reporting lines only).
Predictions:
- **PYa (the reorg law):** (d) is statistically indistinguishable from (c)
  on every outcome metric — reorgs that do not change settlement are inert;
  the P23b of org charts.
- **PYb:** (a) demotes middle/glue positions at disproportionate rates
  (the sacrifice confound organizational: relay-credited and audit-lane
  roles read as low-output) and delivered declines vs (b) at fair horizon.
- **PYc:** (b) > (a) on verified-delivered at fair horizon, with middle-
  role survival intact.
- **KILL (doctrine):** if (a) ≥ (b) on verified-delivered AND middle-role
  survival at fair horizon, promotion-by-receipts adds nothing over
  promotion-by-outcomes in this world and the provenance-org doctrine dies
  with it. Report loudly.
**GATE: Y2 builds only after X verdicts** (its interior regimes are X's
mechanics; running Y2 first would un-register X's comparisons).

**Y3 — real employees (flagship; parameters PENDING X and Y2).** The Y2
winner and loser re-run with in-sim LLM agents (Sonnet/Haiku per standing
model policy; Opus never in-sim) on a real micro-repo with a hidden-test
task queue; N small, episodes short, token budget registered BEFORE the
run. Same treatments, same KILL, plus an honesty constraint: the repo,
tasks, and test results are publishable so any viewer can check the work
was real. Y3's exact N/episode/budget numbers are declared in an amendment
after X and Y2 land — registered as pending, not guessed now.

**P29 RESULTS (2026-07-16, sweep_v4_V.json — report, not verdict; the numbers,
loudly either way). The column-G geometry ladder (grid ∈ {24,32,48,64}, σ=0.5,
τ=0.15, v5, 2,500 ticks, 16 seeds — the G config REPLICATED EXACTLY, and the v8
hump reproduces to the decimal) × {order_book off, on} × {auction (unperturbed
comparator), snhp+net (spot bargaining, the hump), snhp+bill (bills-only control),
snhp+ob (order book = bills-settled async relays).** Design: a drone PINS a
binding cargo-relay order at a location — q cargo escrowed as a lien (folded into
material conservation) with the poster's α*=(1+giver_disc)/2 claim banked, expiry
400t. DISCOVERY is stigmergic (Chebyshev R_SENSE, no free broadcast — the P21
lesson); ACCEPTANCE is unilateral by a passer whose Φ_bills IR clears, pays NO
DEAL_PAUSE (the registered advantage). Order book ⇒ bills (async settlement is
claim-denominated by necessity — energy cannot teleport to an absent poster; the
directionality constraint, documented). All conservation exact across 256 runs
(material_ok, ledger_accounted, credit_conserved, escrow_conserved all green;
pinned/escrow retire to 0).

- **The hump REPLICATES exactly (edge = arm−auction delivered, paired):**
  edge_off (snhp+net−auction) = +4.12@G24, +4.50@G32, +7.31@G48 (peak), −2.69@G64
  — matching the registered v8 hump (+4.1 / +7.3 / −2.7) to the decimal. The G
  config is faithfully reproduced.
- **P29a: KILL FIRES — the order book does NOT flatten the hump.** edge_ON
  (snhp+ob−auction) = +0.88@G24, +0.69@G32, +4.06@G48, −2.69@G64. The G64 edge is
  UNCHANGED (recovery edge_ON(G64)−edge_off(G64) = +0.00); the hump only looks
  "flatter" because the DENSE-field peak came DOWN (G48 +7.31→+4.06) — the book
  HURTING, not the trough recovering. The order book delivers LESS at every grid
  (235.7/235.7/234.7/228.4 vs spot 238.9/239.5/237.9/228.4): async posting +
  taker-routing is pure overhead where direct delivery already works, and it is
  inert at G64.
- **P29b: REVERSED.** async-trade share of deals = 0.076@G24, 0.064@G32,
  0.041@G48, 0.018@G64 — HIGHEST where meetings are densest, LOWEST where sparsest.
  corr(encounter_rate, async_share) across G = **+0.967** (the prediction was
  NEGATIVE: async should fill in where meetings fail). It does the opposite,
  because at G64 the far haul makes the residual unattractive (a plausible taker's
  IR rarely clears across the long supply line) and posters strand before a taker
  arrives (cargo_writeoff rises 3.4→6.9 units with G).
- **The KILL DIAGNOSIS — what binds at G64 is NOT meeting formation.** (i) The
  fleet still trades heavily at G64 (320 sync deals in snhp+ob; meetings are not
  absent). (ii) The registered candidates fire instead: makespan is HORIZON-
  CENSORED (snhp+net 2353/2500, snhp+ob 2500/2500 — every seed runs out of clock),
  and stranding TRIPLES (6.2→17.9) — supply lines outrun battery radius. Travel
  time + battery radius, not convening. (iii) The decisive control: **bills-ONLY
  (synchronous pre-commitment claims, NO async posting) RECOVERS G64** on its own —
  edge(G64) −2.69 → **+4.50**, delivered 228.4 → 235.6 (+7.2). The G64 collapse is
  a chain-formation / hold-up problem (exactly P23's finding: receipts make chains
  exist), which the SYNCHRONOUS receipt already solves. Layering the async order
  book on top CANNIBALIZES it (bills+book = 228.4 < bills-only = 235.6): a drone
  that would have handed cargo to a present claim instead posts to a pin that may
  never be serviced.
- **Pause-ticks saved (reported per the registration):** the mechanism's genuine
  advantage — unilateral acceptance skips DEAL_PAUSE — saves only ~17–31 tick-holds
  per run (3× accepted-count, mean 5.8–10.3 accepts), negligible against 2,500
  ticks. Escrow accounting per run: posted 10.8–16.9, accepted 5.8–10.3, expired
  5.1–6.6, pinned/escrow → 0, escrow_conserved on all 256 runs.
- **Read:** the async surface is the RIGHT primitive for a meeting-formation
  constraint and the WRONG one here — the geometry hump was never a "can't convene"
  problem. Sparse fields don't lack partners; they lack CLOCK (travel time) and
  BATTERY (radius), and where a real coordination gap remains (far-ore hold-up),
  the SYNCHRONOUS receipt (bills) closes it and the async book only dilutes it.
  Thesis translation, on the record: attestation's value is PRE-COMMITMENT (a
  binding claim that forms a chain), not ASYNCHRONY (a posted offer that saves a
  rendezvous); the order book conflates the two and the geometry ladder separates
  them. Registrar's KILL clause satisfied: the hump survived order books intact,
  the constraint was diagnosed (travel/battery, not meetings), and the mechanism
  that DOES move G64 (synchronous bills) is named.

**P29 VERDICTS (2026-07-16, registrar).**
- **P29a: KILL FIRES — the order book does not flatten the hump.** G64
  recovery is exactly +0.00 (edge −2.69 with and without the book), and the
  book PULLS DOWN the dense-field peak (G48 +7.31→+4.06): async posting +
  taker-routing is pure overhead where direct hand-offs work. "Posted
  offers dissolve the room" is REFUTED — the room was never the constraint.
  The pre-accounted advantage (no DEAL_PAUSE on acceptance) proved
  negligible in the event (~17–31 ticks/run of 2,500) — accounted, and it
  did not matter.
- **P29b: REVERSED.** Async share is HIGHEST where encounters are densest
  (corr(enc_rate, async_share)=+0.967 vs the registered negative): a pinned
  offer is found where traffic passes. In sparse fields takers find far
  relays IR-unattractive and posters strand before pickup — the bulletin
  board needs foot traffic more than the bargaining room does.
- **The registered diagnosis found the real constraint, and a law with it.**
  What binds at G64 is CLOCK + BATTERY (makespan horizon-censored 2500/2500
  under the book; stranding triples 6.2→17.9), not meetings. The decisive
  control: **bills-ONLY recovers G64 outright (edge −2.69→+4.50, delivered
  228.4→235.6)** — the sparse-field trough is a hold-up/chain-formation
  problem the SYNCHRONOUS receipt (P23) already solves, and the async book
  CANNIBALIZES it (bills+book 228.4 < bills-only 235.6: drones post to a
  pin instead of handing to a present claimant).
- **The law, on the record: attestation's value is PRE-COMMITMENT, not
  ASYNCHRONY.** The binding claim that forms a chain is the scarce
  primitive; saving the rendezvous is not. Third independent confirmation
  of the P23 mechanism (chains, fair-horizon scale, now geometry), and a
  RE-SCOPING of the column-G law: "the market needs meetings" holds for
  SPOT bargaining; with claim stacks the meeting-density trough closes.
  Product translation, on the record: agent commerce is not short of
  posting infrastructure (every marketplace posts); it is short of the
  binding claim. Do not build the bulletin board; build the receipt.

**P24 RESULTS (2026-07-16, sweep_v4_Q.json — report, not verdict; the numbers,
loudly either way). Endogenous infrastructure: the sim grows landlords.** N=240
scaled v5 (grid 101), σ=0.5, τ=0.15, 8 seeds, BOTH horizons {2,500 · 7,500} (the
mandatory fair pair — building is the most truncation-exposed mechanism yet).
Design: a SEPARATE matter field (build_matter=0.5 → 50 mirror-pair matter rocks,
disjoint from ore — ore routing / Φ / conservation untouched by construction, all
prior columns bit-identical, differential oracle green WITH mid-run built chargers)
is mined-to-pool by ≤3 designated gatherers/company; a company spends MATTER_COST=6
matter + BUILD_CREDIT_COST=30 credits to PLACE one charger. Placement is derived
from the EXISTING loaded-haul valuation (not a new planner): a within-loaded-reach
STEPPING STONE (0.9·BATTERY_MAX/(eff·(1+λ)) ≈ 56 cells from the home refinery)
toward the LOAD-weighted centroid of the company's own trapped-return drones (the
stranding-concentration argmax), with a forgone-far-ore fallback (stock×charge-
distance) for the early game. Guest toll grid {0, 1, 2, 4}=cost×{0,1,2,4} credits/
guest slot-fill on BUILT chargers only (a TOLL_ROUTE_PENALTY=3 cells/credit guest-
avoidance gives the toll a demand channel). Refinery tier DEFERRED (charger-only —
not cheap given the structures; registered, not forced). Conservation exact across
all 128 runs: material_ok, ledger_accounted (extended with build_spend),
matter_conserved (field+pools+spent == mined == initial) and toll_conserved
(guest→owner net-zero) all green.

- **P24a: KILL FIRES — built chargers do NOT lift the N=240 plateau.** Paired
  build−control delivered_frac edge = **+0.001** (snhp+net, p=0.67, 4/8 wins) and
  **−0.004** (auction, p=0.34, 3/8) — nowhere near the registered +0.05. Delivered:
  snhp+net 1990.2 (frac .829) → 1992.5/1993.4 build (.830/.831); auction 2037.4
  (.849) → 2028.6 build (.845, building HURTS the auction −8.8). ~13.6 chargers
  built/run (6+6/company). Placement does NOT "cluster where far-ore decay was":
  100% of built sites fired in TRAPPED-RETURN mode (the far-ore fallback never
  triggered), landing centrally near the y=50 company boundary (seed-0 sites
  [51,44],[50,57],[49,42],…, forgone weights 93–148), because the binding
  stranding is loaded-return, not far-ore.
- **NOT truncation — a HARD STALL.** Delivered is FLAT 2,500→7,500 (no-build +0.0
  both arms; build +0.9 snhp, +0.0 auction) — 5,000 extra ticks deliver nothing.
  And building is EARLY, not late (first@tick 25, median@~156–302, only ~3/13 built
  after the half-horizon), so the null is not horizon-censored capital. The
  P28-H/P18 truncation trap does NOT apply here: the horizon was tested and the gap
  did not narrow.
- **THE PLATEAU MECHANISM — the constraint is charge-ROUTING, not charge-SUPPLY.**
  At the horizon ~410 ore units (snhp) / ~363 (auction) are MINED but never
  delivered — held in the loads of ~166 drones sitting at FULL battery (median 100)
  AT a charger, of which **98% are >62 cells (single-hop loaded reach) from their
  refinery**. The greedy nearest-charger policy pins a loaded low-battery drone at
  the closest charger; if that dead-end charger is itself beyond loaded reach of the
  refinery, the drone oscillates forever. Infrastructure cannot relieve this: a
  stepping-stone charger only helps a drone that ROUTES to it, but a stuck drone's
  nearest charger is always the dead-end it already occupies. Building drains only
  ~3 units of held_load. Stranding stays tiny (2–4) throughout — this is TRAPPING,
  not classical stranding, and capital does not touch it.
- **P24c: bargaining tolerates building better than the auction (weak support).**
  build-gain = +2.2/+3.1 (snhp+net) vs −8.8 (auction) at both horizons: the auction
  is the STRONGER no-build baseline at N=240 (2037 vs 1990 — its blunter cargo
  reassignment traps less), and building DEGRADES it (gathering diversion + charger
  churn with no delivery payoff), while it marginally helps the bargaining fleet.
  Directionally P24c holds (claim/deal coordination sites infrastructure less
  destructively), but at a scale where both effects are ≤ the KILL threshold.
- **P24b [UNDER-PROVISION]: REFUTED.** Welfare (delivered) vs FORCED per-company
  build budget {0,2,4,8,16} = {1990.2, 1982.9, 1978.0, 1993.8, 1992.5}: NON-
  monotonic — 2–4 forced chargers HURT (gathering + churn), 8+ recovers to ~+3.6
  over control, and the peak (budget 8 ≈ 16 total capacity) coincides with the
  voluntary build (~13.6). Welfare does NOT rise past the voluntary count, so there
  is no gap between private and social provision to under-fill. The public-goods
  under-provision does not arise because the marginal charger has ~zero social
  product here (the routing deadlock caps it).
- **P24b [CROSS-COMPANY TOLL PRICING]: above marginal cost, but economically
  marginal.** The trapped-centroid stepping stones land where cross-company traffic
  passes, so at toll 0 the BUILT (endogenous) chargers serve **267 guest slot-fills/
  run**. Demand is hyper-elastic: guest slots 267 → 7.9 → 0 → 0 and owner revenue
  0 → **7.88** → 0 → 0 as toll goes 0 → 1 → 2 → 4. The revenue-maximizing toll is
  the lowest positive rung (1× cost = ABOVE marginal cost ≈ 0), so the toll-booth
  DOES recurse onto endogenous capital — but it extracts trivially (7.88 credits in
  a ~20,000-credit economy) and mostly diverts guests to the free preset chargers
  (which serve ~52,650 guest-energy/run). Priced above marginal cost: technically
  yes; the wedge that matters: no.
- **Read (KILL headline).** At N=240 the binding constraint is charge-PLANNING —
  single-hop, greedy, myopic loaded-return charge routing that traps ~1/5 of all
  mined ore at dead-end chargers — NOT charge CAPITAL. So endogenous infrastructure
  is decorative: no charger count, cost, horizon, or arm lifts the plateau, and
  forced over-provision does not help. This is the SAME lesson as P18/P28-H one
  layer down: it is PLANNING, not supply (compute, chargers, receipts, capital),
  that stops scaling. Product translation, on the record: at fleet scale, do not
  sell more infrastructure into a routing-deadlocked commons; sell the multi-hop
  charge PLAN (the thing that would let a trapped hauler route through a stepping
  stone). The landlord cannot fix a traffic-routing failure by building more
  toll-booths — and the guests just take the free road anyway.

**P24 VERDICTS (2026-07-16, registrar).**
- **KILL FIRES — infrastructure is decorative at these scales.** No arm at
  either horizon lifts the N=240 plateau by ≥0.05 (best: +0.001); welfare
  is flat-to-negative in charger count. And this time truncation is RULED
  OUT, not suspected: building happens early (first build tick 25, median
  ~156–302) and delivered is flat 2,500→7,500. The fair-horizon pair did
  its job in the boring direction.
- **The diagnosis is the finding: the plateau is charge-ROUTING, not
  charge-SUPPLY.** ~166 loaded drones sit at FULL battery at dead-end
  chargers, 98% of them beyond single-hop loaded reach of the refinery —
  a routing deadlock capital cannot fix. P18/P28-H one layer down: the
  binding constraint at scale is planning, and you cannot buy planning
  with capital expenditure. Registered-open ENGINE observation: a
  multi-hop loaded-return policy (stepping-stone routing) is a physics/
  policy revision that would lift ALL N=240 baselines and requires
  re-running scale columns if adopted — founder decision, not a column.
- **P24b REFUTED — the landlord rent dies.** No public-goods
  under-provision (welfare peaks at ~the voluntary build count); toll
  demand is hyper-elastic against free preset chargers, and the
  revenue-maximizing toll extracts 7.88 credits in a ~20,000-credit
  economy. Own-the-bottleneck is not a business in this world: another
  adjacent-rent null in the long series (firm-agent, middlemen, compute
  moat, transfer pricing, now landlording). The mechanism layer keeps
  being the only durable value.
- **P24c: weak directional support, honestly scoped.** Bargaining gains
  from building (+2.2/+3.1) while auction loses (−8.8), but auction's
  no-build baseline is stronger; the comparison says building composes
  with claim coordination and degrades pure price competition — at
  magnitudes too small to carry any claim.
- **DESIGN CAVEAT FOR COLUMN X (amendment to v25, registered before its
  build):** Q's deadlock diagnosis contaminates naive interior
  comparisons — a command planner with a bespoke multi-hop router would
  beat claims via ROUTING competence, not settlement mechanics. The X
  builder MUST (i) give the command planner only the shared policy
  primitives every arm uses (no stepping-stone superpower), and (ii)
  instrument the routing-deadlock count (loaded-at-full-battery,
  refinery-unreachable-in-one-hop) per regime so settlement effects
  decompose from routing effects in the report.

**P24 RE-SCOPE (2026-07-16, registrar — founder caught both holes).**
Two design facts make the P24 verdicts narrower than written:
1. **Free preset chargers saturate the world.** The toll test ran against
   ubiquitous free public substitutes (guests simply routed to them —
   ~52,650 free guest-energy/run vs 7.9 tolled slot-fills). "Landlord rent
   dies" is therefore near-tautological AS RUN: what died is "landlording
   against free public infrastructure," which no landlord anywhere
   attempts. P24b is DOWNGRADED from refuted to UNTESTED-AS-REGISTERED.
2. **Bills were instructed as standard kit and silently not run** — the Q
   cells carry no bills flag; snhp+net delivered .829 = the SPOT baseline.
   The registrar merged without catching the deviation; both misses are
   the registrar's. Consequence: the far-chain economy (bills' far-band
   0.40→0.47) never existed in Q's world, so far infrastructure had no
   demand to serve — the far-ore placement fallback never fired and every
   site landed centrally. Q tested infrastructure in an economy whose
   frontier was structurally dormant.
**P24a stands AS-SCOPED** (building is decorative in the spot world with
free substitutes — still a real null for that world), and the routing-
deadlock diagnosis stands (it is arm-independent physics). The landlord
question is re-registered below.

**THE COMPOSITION RULE (standing, registered).** Rent-bearing mechanisms
(landlords, firms, middlemen, tolls) must be tested BOTH minimal AND
composed with the confirmed-good kit (bills at minimum; whatever else has
survived its column). A null from a minimal-only run is scoped
"artifact-until-composed," not "law." Rationale, the founder's: rents live
in the interactions — intermediaries die by construction in worlds
stripped of the complements that feed them. (P23b's transfer-pricing
inertness is NOT re-opened: it was bit-identical because objectives never
changed — composition cannot rescue a mechanism that alters no decision.)

## v18-R (column Q2): landlords on the frontier — P24-R amendment

The landlord re-test in a scarce, composed world. Changes from Q, exactly
two: (i) **frontier scarcity** — preset free chargers exist ONLY within a
home band around each refinery (band radius = single-hop loaded reach);
the far band has NO free chargers, so built capital is the only far
supply; (ii) **bills ON** for the bargaining fleet (verified in the cell
definitions at review, not assumed). Everything else identical to Q
(matter field, build costs, toll grid, budget sweep, both horizons,
deadlock instrumentation per the X caveat).
- **P24R-a:** with frontier scarcity + bills, building lifts far-band
  delivered/mined by ≥0.05 over the bills no-build control at 7,500t, and
  placement moves to the far band / relay corridors (the fallback fires).
- **P24R-b:** tolls on far chargers extract real rent — owner revenue
  materially above marginal cost and above Q's 7.88cr farce; budget sweep
  re-tests under-provision where capital is actually scarce.
- **P24R-c (the founder's layering claim, falsifiable):** the build edge
  under bills exceeds the build edge under spot — infrastructure and
  claim-chains are complements.
- **KILL:** if building and tolls stay decorative even with frontier
  scarcity and bills (far-band lift <0.05 AND toll revenue de minimis),
  infrastructure rent is genuinely absent at these scales and the null
  graduates from artifact to law. Report loudly either way.

**PX VERDICTS (2026-07-16, registrar) — the doctrine result: inside the
firm, the receipt beats the boss.**
- **KILL DOES NOT FIRE.** At N=240/7,500: claims 2096.0 delivered vs
  command 1954.8 (Δ=−141.2 for command, p=.001, 0/8 seeds). Attested
  claims on outcomes beat central command AND inert chargeback inside the
  firm. The internal-notary doctrine survives its registered kill.
- **PXa REFUTED, mechanism confirmed.** Command loses at EVERY cell — the
  registered small-N win never appears. The degradation mechanism is
  measured exactly as predicted (belief-age + reach-latency grow with N;
  at N=240 an assignment is ~90 ticks stale by execution — books-bleed-
  first, for the planner), but it drowns command everywhere. Scope,
  honestly: this is command on REALISTIC information (gossip-merged
  belief, shared routing primitives, per the P24 caveat — verified: its
  deadlock counts match baseline, so no routing edge and no routing
  handicap). Hierarchy's cost in this world IS its information channel;
  an oracle planner is the untested fantasy variant, and it would be a
  different experiment, not a rescue of this one.
- **PXb CONFIRMED MAXIMALLY — the inertness law's third confirmation, now
  interior.** Transfer prices are bit-identical to baseline on delivered
  at every cell; they move only the payout distribution (Gini
  0.541→0.528). Chargeback redistributes; it does not produce.
- **PXc CONFIRMED, and it closes the Q loop.** Claims−baseline +91.8 at
  N=240/2,500 (p=.001, 8/8) and +115.5 at 7,500 (p<.001, 8/8), internal
  ≥2-hop hand-off share 0.51–0.52 vs 0.02. And the cross-column headline:
  **claims lift the P24 plateau that capital could not** (delivered_frac
  0.825→0.863/0.873, vs Q's chargers +0.001). The deadlock instrument
  explains how: claims' ~4× deadlock ENTRIES are rescues — a stuck loaded
  drone hands off via a claim and cycles back to the frontier. The
  registered equal-counts assumption is falsified INFORMATIVELY: a
  mechanism that rescues deadlocks generates more entries. Q's diagnosis
  said the plateau was a routing failure capital can't fix; X shows the
  fix was never an algorithm or an asset — it was a CONTRACT that makes
  the rational hand-off exist. Bills are the stepping-stone router,
  implemented economically.
- **Thesis line, on the record:** command loses to its own information
  channel, prices redistribute without producing, and attested claims are
  the only interior mechanism that turns scale from a liability into
  throughput. Y2's gate (org structure on X's mechanics) is now OPEN.

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

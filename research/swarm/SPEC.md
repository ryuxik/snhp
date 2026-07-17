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

**P26 RESULTS (report, not verdict) — v20 (column S), institutions as a
substitute for cognition (2026-07-16, builder).** 204 runs: the 2×2
{smart, dumb routing} × {coarse, granular rights} × {snhp+net, auction} at
N=24 (16 seeds) and N=96 (8 seeds), 2,500 ticks, σ=0.5, τ=0.15, v5, on the
v11/v12 moving field (belief + dynamic + contested + K0 scouting); + a
7,500-tick × 4-seed horizon spot-check (smart+coarse, dumb+coarse, dumb+gran;
snhp+net). Conservation suite green throughout. Tests 122→128.
SCOPING (registrar's, on the record): **nav_dumb dumbs ONLY the routing /
planning brain** — best_claim's richest-per-distance Φ target selection is
replaced by greedy nearest-KNOWN-rock + noise (NAV_DUMB_NOISE=6.0, dedicated
RandomState(seed+262626), never the main stream); deals, physics and deal-Φ
evaluation are byte-for-byte untouched (evaluated Φ == executed Φ verified in
all four cells; nav_dumb OFF is bit-identical). This measures whether
institutions substitute for PLANNING, not for the deal-evaluation faculty
itself. GRANULAR = K2 prospect-claims (arrival WINDOWS + the sector issue the
deal economy trades claim assignments through); COARSE = default sectors.
- **The registered directional KILL does NOT fire at the thesis cell (N=24,
  snhp+net) — but the confirmation is weak and does not scale.** 2×2 delivered
  means: smart+coarse 284.1, smart+gran 282.1, dumb+coarse 278.4, **dumb+gran
  291.3**. On the point estimates this is textbook substitution: **P26a
  gap-recovery = +225%** (recovery +12.9 ≥ the +5.8 dumbing gap; ≥50% MET);
  **P26b interaction = +15.0** (help_dumb +12.9, help_smart −2.1 — granular
  helps the DUMB fleet and slightly HURTS the smart one). The dumb+granular
  cell (291.3) is the single best snhp cell — a dumb fleet WITH tradeable
  claims out-delivers even the SMART fleet without them (284.1).
- **…but it is NOT statistically robust.** Recovery p=0.105, 5/16 seeds (a few
  large wins, most seeds ~0); the underlying dumbing gap is itself n.s. (+5.8,
  p=0.214). The rich, scouting-equipped field leaves dumb ROUTING little room
  to hurt (~2% of delivered), so there is little "IQ" to buy back and the
  recovery-% is a high-variance ratio of two small, noisy quantities.
- **P26b INVERTS at N=96 — substitution flips to complement.** N=96 snhp+net:
  smart+coarse 329.9, smart+gran 336.6, dumb+coarse 323.5, dumb+gran 322.9.
  Recovery −0.6 (0/8 seeds, −10%); interaction −7.4 (help_dumb −0.6, help_smart
  +6.8). Granularity now helps the SMART fleet more — the opposite sign. The
  N=24 signal does not survive a 4× density scale-up.
- **The auction control localizes (and undercuts) the mechanism.** Window
  EXCLUSION without claim TRADING (auction: 0 deals, 0 sector swaps) points the
  OTHER way at both N: interaction −5.6 at N=24 (help_smart +2.8 > help_dumb
  −2.8) and −4.8 at N=96 (help_smart +8.6 > help_dumb +3.9). The only
  substitution signal anywhere lives in the snhp deal economy's tradeable
  sector-claims — exactly the registered mechanism — but only at N=24 and only
  as a noisy point estimate.
- **Claim-trade (sector-swap) volumes per cell (N=24, mean/run):** snhp
  smart+coarse 74.8, smart+gran 72.8, dumb+coarse 70.0, dumb+gran 72.8 (deals
  118–125); auction cells 0. Granularity barely moves trade volume (~+3 swaps
  for the dumb fleet) — the recovery, where it exists, is a small reallocation,
  not a trading surge.
- **Horizon spot-check (7,500t, N=24): the recovery DECAYS, it does not
  amortize.** smart+coarse 284.1→301.2, dumb+coarse 278.4→297.5, dumb+gran
  291.3→299.2. The dumb+gran advantage over dumb+coarse shrinks +12.9→+1.7 as
  the game lengthens, and smart+coarse reclaims the top (301.2 > 299.2).
  Claims-coordination is a FRONT-loaded effect (the window forces early spatial
  spread the dumb fleet cannot plan) that the long game erodes — the same
  early-spread advantage the hand-built test isolates (real at short horizon,
  gone once coarse catches up). NOT the late-amortizing coordination the
  P18/P28-H rule watches for.
- **Honest headline.** At N=24 the deal economy's tradeable claims DO buy back
  the (small) planning deficit and help dumb fleets more than smart — the
  directional thesis survives its KILL there — but the effect is not
  statistically robust, does not replicate at N=96 (it inverts to complement),
  and decays rather than amortizes with horizon. Institutions substitute for
  cognition here only faintly, locally, and early: a fragile, scale-dependent
  point estimate, not a bankable substitution law. (Registered caveat honored:
  we dumbed only planning; the bargaining brain — which the deal economy needs
  to reallocate claims at all — was never in scope to dumb.)

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

**Y1 VISUAL DIRECTION (founder-directed amendment to v26, 2026-07-16).**
Art style: GROW Cube (the old EYEZMAZE web game) — STYLE ONLY, all assets
original (no copied sprites/characters; the style is chunky isometric
cutaway diorama, soft pastels on warm cream, clean dark outlines, flat
two-tone shading, rounded oversized miniatures, discrete pop/level-up
animations). The company is a CUTAWAY ISOMETRIC CUBE that GROWS as the
pipeline replay advances: rooms sprout on events, floors stack, and each
completed column fires a GROW-style LEVEL-UP on the subsystem it touched.
A GROW-style panel row shows the mechanisms/columns in the ORDER they were
applied — the composition rule as UI. Honesty bindings (per Y1's
registration): every rendered event maps to a real commit (hover = the
hash); time compression declared on screen as a GROW-style turn counter
("TURN n = <real timestamp>"); no decorative agents. Data source: the
repo's own git history + SPEC ledger, parsed to an events.json by a
checked-in generator. Lives in arena/web/antfarm/, unlinked from the
arena index; deployment is a founder decision (assets public only when
the founder publishes).

## v26-R (column Y, REVISED): the company — founder correction 2026-07-16

The prior Y registration misread the founder's intent: a replay of the
pipeline is a log with scenery. Column Y is THE COMPANY — a living economy
in a building, whose rules ARE the program's measured mechanisms. The
pipeline-replay renderer (old Y1, mid-build at this revision) is DEMOTED
to a standalone artifact ("workshop replay" — kept for the sequel's
reflexive beat, not column Y).

**Y-A — the company world (engine re-skin, NOT a new sim).** Registered
mapping: idea/project = asteroid (+belief machinery for uncertain value);
stage chain research→design→build→ship = multi-hop relay; stalled idea =
hold-up; pre-committed credit splits = bills; divestment = claim-sale;
budget = energy/chargers; director = command regime; chargeback = internal
prices; false status = liar machinery; desk-sitting = dwell. Regimes:
{no-mech, command, chargeback, claims} (X's arms) + optional liar and
moral-hazard dials. Roles visible by function: stage workers (ICs),
carriers between stages (middlemen), planner (director).
**FIDELITY KILL:** with the company skin on and one-stage ideas the world
must reduce BIT-IDENTICALLY to the asteroid world (skin = flags + labels
only). If the re-skin requires mechanism changes, STOP and register the
deltas before building further.
**HONESTY RULE (binds Y-A/B/C/D):** every quantitative claim the company
demo makes is an already-banked number (P23, P23e, U/P28-H, V, X). Any
NEW emergent claim — incl. invest/divest portfolio branching beyond
composed claim-sales — requires its own registration + kill before being
asserted anywhere.

**Y-B — the live renderer** (GROW Cube direction 3b38fb7 stands; renders
REAL World state, no scripted theater): floors = stages; ideas ascend and
LAUNCH from the roof on delivery; under spot rules stuck ideas visibly
pile on middle floors (hold-up as clutter); the REGIME TOGGLE is the demo
— flip spot→claims and the middle floors unjam, with the banked P23/X
numbers on screen. Multiple regimes = GROW's multiple endings: claims
grows tall, command stunts at scale, no-mech stays a lobby.

**Y-C — endogenous structure (the old Y2 contract, unchanged, in company
skin):** promotion treatments {outcome, receipt, static, reorg-without-
settlement}; PYa reorg-inertness law, PYb glue-worker demotion, PYc
receipts>outcomes at fair horizon; doctrine KILL as registered. Gate: X
verdicts (OPEN as of 7089587).

**Y-D — real LLM employees (old Y3, unchanged, parameters pending Y-C).**

Open founder decision (registered, undecided): does invest/divest stay
composition (claim-sales, measured) or become a new portfolio mechanism
(new science → its own column)?
**P24-R RESULTS (report, not verdict) — v18-R (column Q2), landlords on
the frontier (2026-07-16, builder).** 168 runs: {no-build, build} ×
{snhp+net+bills, snhp+net spot, auction} × {2,500, 7,500}t under frontier
scarcity (charger_band = BATTERY_MAX/(1+LOADED_MULT) = 62.5 Manhattan
cells — the same single-hop loaded reach the placement/deadlock code
prices; at N=240 it strips exactly the 10 far-band presets, 40→30, ore
and matter fields byte-identical), + budget {0,2,4,8,16} and toll
{1,2,4}cr sweeps on the bills build arm, + the scarcity-OFF bills flag
control. 8 seeds, N=240 scaled v5 (grid=101), σ=0.5, τ=0.15,
build_matter=0.5. Conservation suite green throughout (material, ledger
+build_spend, matter, toll). Tests 112→118.
- **BILLS FLAG VERIFIED (the Q-miss guard): the scarcity-OFF control
  reproduces the P23 bills signature EXACTLY** — delivered_frac 0.857,
  far-band d/m 0.470, ≥2-hop 0.492 (P23 registered: 0.857/0.470/0.492;
  spot would be 0.829/0.399/0.025). Bills ran this time; the far-chain
  economy existed in every Q2 cell (≥2-hop 0.49–0.54 on bills cells).
- **P24R-a NOT MET, twice over.** Building lifts the far band nowhere:
  bills Δfar +0.013 @7,500t (p=0.445, 5/8) and −0.015 @2,500t; spot
  −0.004/−0.037; auction −0.008/+0.004 — every cell below the +0.05
  threshold, no p under 0.12. And the far-ore placement fallback NEVER
  fires: fallback-band-hist [0,0,0] in every build cell — all ~15–16
  chargers/run are trapped-return corridor placements, site-band-hist
  [0.2, 14.5–16.1, 0.0] (all mid-band; the stepping-stone rule pins
  sites at 0.9·62.5 ≈ 56 cells, geometrically ≤ the 62 far edge, so
  built capital cannot even STAND in the far band — a design property
  of the Q placement rule, on the record).
- **The louder null underneath: the far band never needed the chargers.**
  With ZERO far-band charging capacity, the bills no-build fleet still
  mines the far field to completion at 7,500t (far-band mined 565.8 ≈
  the unscarce 565.75) and delivers it at far d/m 0.867 (vs 0.470
  unscarce — the ratio RISES because far mining defers to the horizon
  tail, 339@2,500 → 566@7,500, and chains deliver what gets mined).
  Scarcity costs the bills fleet −0.051 delivered_frac at 2,500t
  (0.857→0.806) and ~nothing at 7,500t (0.961). Claim-chains substitute
  for far infrastructure: hand-offs move far ore home without far
  charging. Third echo of X's lesson — the constraint is the contract,
  not the capital.
- **P24R-b (toll): rent is REAL but MICRO.** Guest slot-fills on built
  chargers: 17.5 free → 12.2 at any toll>0, then INELASTIC across
  {1,2,4}cr — revenue linear in price (12.25/24.50/49.00cr), no interior
  optimum on this grid; the owner's grid-optimum is the max toll. 49.00cr
  is 6.2× Q's 7.88cr farce and ~37cr above the marginal-cost benchmark
  (grid unit = 1cr), so the registered "materially above marginal cost
  and above Q's 7.88" is MET — but against the 435cr capital that
  generated it (14.5 chargers × 30cr) tolls recoup 11%, and against the
  ~19,400cr delivered economy they are 0.25%. Deadweight ≈ 0 (delivered
  1941.9→1939.8). A landlord exists on the frontier; he collects lunch
  money.
- **P24R-b (budget): FLAT — no under-provision.** Delivered across
  forced budgets {0,2,4,8,16}/co: 1935.0 / 1926.6 / 1923.2 / 1932.6 /
  1941.9 (sd ~97–118 each; range 19 ≪ noise, non-monotone). The
  report's "UNDER-PROVISION" print is a threshold artifact (Δ=+6.9 over
  budget-0 cleared the >5 rule); the honest read is a null: welfare does
  not rise with charger count even where capital is the only far supply.
- **P24R-c SPLIT, honestly noise.** Build edge under bills vs spot:
  +6.9 vs −18.6 @2,500t (layering supported), −4.0 vs −1.0 @7,500t
  (refuted). All four edges are within seed noise (delivered sd ~100);
  no reliable complementarity between infrastructure and claim-chains —
  consistent with capital being decorative under both settlements.
- **KILL (registered: far-band lift <0.05 AND toll revenue de minimis):
  DOES NOT FIRE — on the rent leg only, and only technically.** Far-band
  lift fails everywhere (<0.05), but 49.00cr toll revenue is 6.2× the
  pre-registered 7.88cr comparator, so the conjunction is broken. Scope
  it honestly: building remains decorative for THROUGHPUT even with
  frontier scarcity and bills (P24a's null now survives its composed
  test — under the COMPOSITION RULE it graduates from
  artifact-until-composed toward law for capital-as-throughput); what
  scarcity creates is a real but economically trivial TOLL rent on
  inelastic guest demand. Landlording at these scales pays ~49cr on a
  435cr build — rent exists, a rentier business does not.
- **Deadlock instrument (X caveat, descriptive):** bills cells run ~2×
  spot's deadlock ENTRIES (283.9 vs 170.9 @2,500t; 759.5 vs 420.1
  @7,500t) — the X rescue signature again; building adds entries under
  bills (355.9/831.2) while fixing none of the far-band ratio, consistent
  with entries-as-rescues, not routing failure.

**P24-R VERDICTS (2026-07-16, registrar) — the null graduates: capital is
decorative for throughput in this world, minimal AND composed.**
- **P24R-a NOT MET, with one clause scoped.** Far-band lift peaked at
  +0.013 (p=.445) against the registered +0.05 bar; building never moved
  throughput even with frontier scarcity and bills verified on (the
  cells-match-registration guard did its job; the P23 signature reproduced
  to three decimals). The placement clause is scoped
  UNTESTABLE-AS-BUILT: the inherited Q siting rule pins stepping stones at
  ~56 cells, geometrically short of the 62-cell far edge, so built capital
  could never stand in the far band. Registered-open (not queued): a
  fair far-band placement variant, if anyone still believes in it after
  the next bullet.
- **The louder null IS the finding: chains substitute for capital.** With
  ZERO chargers in the far band, the bills fleet mined the frontier to
  completion at 7,500t (far mined 565.8 ≈ the unscarce world's 565.75,
  far d/m 0.867). The frontier did not need infrastructure because claim
  chains carry gold across it without anyone standing there recharging.
  Third independent echo of X: the contract does the job capital was
  hired for.
- **P24R-b: rent EXISTS; a rentier business does NOT.** Toll revenue 49cr
  at the top of the grid, 6.2× Q's 7.88cr farce, real and above marginal
  cost, demand inelastic above zero — and 0.25% of the ~19,400cr economy,
  11% of the build spend, deadweight ≈ 0. The budget sweep is flat: the
  report's "UNDER-PROVISION" print is a threshold artifact (+6.9 over a
  +5 rule, sd ~100) and is hereby overridden: no under-provision.
- **P24R-c: INCONCLUSIVE, honestly.** The complements claim split by
  horizon with every effect an order of magnitude under seed noise
  (sd ~100). Underpowered at 8 seeds; not counted for either side.
- **KILL: fires on the throughput leg, not the rent leg.** Per the
  COMPOSITION RULE the capital-as-throughput null is now LAW in this
  world: tested minimal (Q) and composed (Q2, scarcity + bills), building
  is decorative both times. What scarcity buys a landlord is lunch money
  from inelastic guests. The founder's layering instinct was still right
  to demand the test — the law earned its status only by surviving it.

**Y-A/Y-B STATUS (2026-07-16, registrar): BUILT, fidelity kill enforced by
test.** The company logger is a pure observer (bit-identical with logging
on/off, differential oracle included — the registered kill is now a
permanent regression test) and the world is a configuration of existing
flags only. The renderer's three-way regime toggle shows the banked
signatures live in real replay data: chains 2.6% (spot) → 56.5% (claims)
→ 0.0% (director); delivered 1864 / 2019 / 1503 (P23a, PXc, PXa
respectively, seed-0 N=240). Every rendered element maps to a logged
datum; every number on screen is a log counter or a cited SPEC verdict.
arena/web/company/, unlinked from the arena index; publication is a
founder decision. Y-C (endogenous structure) remains the next science
phase, gate OPEN.

## v27 (column Z): forgery — the receipt under attack

Every column since v6 has ASSUMED the receipt cannot be faked; the
assumption is load-bearing for the entire program and has never been
attacked. Attack it. Scope: the v6 attested-books gate (bills stay OFF —
one assumption at a time). A liar may spend energy c_f to attempt a FORGED
attestation admitting it to the trusted cooperative tier; a counterparty
may spend c_v to verify a proffered receipt (catch probability p_v = 1 on
paid verification; unverified receipts accepted at face value). Sweep the
cost ratio c_f/c_v across the grid; two verification regimes: (a) MANDATED
(every tier admission verified) and (b) ENDOGENOUS (each agent chooses
per-encounter whether to pay c_v, standard Φ accounting).
- **PZa (the cliff):** a collapse threshold exists in c_f/c_v — below it
  the trusted tier's honest advantage inverts (the v6 feeding frenzy
  returns); the transition is sharp (phase-like), not gradual.
- **PZb (the public-good gap):** endogenous verification under-provides
  near the cliff — each agent free-rides on the tier's average honesty, so
  the market sits measurably closer to collapse than mandated verification
  at the same costs.
- **PZc:** attestation-with-verification degrades gracefully vs the U
  reputation baseline under equal forgery pressure (receipts stay better
  even while under attack).
- **KILL:** if no threshold exists (robust at any forgery cost, or
  collapsed at all of them), the unforgeable-receipt assumption is either
  trivially safe or already dead in this world — either way, say so
  loudly; if forgery never pays even at c_f=0, diagnose (the walk-away
  right may already immunize spot; the target is the TIER).

### PZ RESULTS (report, not verdict) — sweep_v4_Z, 544 runs, N=24 (+N=96 scale check)

Registered grid (energy units; deal scale BATTERY_MAX=100 / surplus O(1–10) /
TXN 0.05): **c_f ∈ {0, 0.5, 2, 8} × c_v ∈ {0.25, 1, 4}**, two verification
regimes (mandated, endogenous), liar_frac=0.25, σ=0.5, τ=0.15, v5, 2500 ticks,
16 seeds. Forgery is DETERMINISTIC always-forge — every unattested liar presents
a forged receipt at each gated encounter that has a real beneficial deal, burning
c_f (the seed+272727 RandomState is reserved-unused; deterministic is simpler and
keeps the main stream untouched). The endogenous verify decision runs through the
EXISTING valuation, no bespoke heuristic: verify iff `liar_frac·downside >
c_v·EV_INIT`, where downside is how far below its own disagreement Φ the checker
lands at the no-veto trusted pick, and liar_frac is the tier's forger prevalence
(the average honesty each agent free-rides on). Costs are burned POST-settlement ⇒
evaluated Φ == executed Φ intact; forgery-off is bit-identical; differential oracle
green; +6 tests. Metric: **honest advantage = honest − liar mean delivery credit**
(↑ ⇒ tier healthy).

References: healthy gated tier (receipt unforgeable) **−9.5±32.7** · ungated
feeding-frenzy floor **−179.0±36.4** · reputation-only (U regime) **+1.4±31.5**.

THE CLIFF MAP (mean honest advantage; rows c_f, cols c_v):

    NO VERIFICATION (c_f only):  −179.0 / −168.3 / −104.9 / +94.5   (c_f=0/0.5/2/8)
    MANDATED     c_v→   0.25     1.0     4.0        ENDOGENOUS  c_v→  0.25    1.0    4.0
       c_f=0          +11.2   +29.1    −0.6           c_f=0           −0.6  −17.3  −46.7
       c_f=0.5        +34.9   +43.6    +2.9           c_f=0.5        +31.8  +14.2  −42.6
       c_f=2          +77.5   +76.6    +4.8           c_f=2          +81.6  +69.1  +36.9
       c_f=8         +113.5   +98.1   +11.2           c_f=8         +116.2 +115.4 +102.2

- **PZa (the cliff) — CONFIRMED.** A sharp threshold in the c_f/c_v RATIO. At
  cheap-forge / dear-verify (low c_f, high c_v) the tier's honest advantage
  inverts toward the −179 feeding-frenzy floor (endogenous c_f=0: −0.6 → −17.3 →
  −46.7 as c_v climbs 0.25→4); at dear-forge / cheap-verify it holds far above the
  healthy reference (+116). TWO independent defences meet at the cliff: (i)
  verification catches forgers, (ii) c_f alone bankrupts them — at c_f=8 even NO
  verification gives +94.5 (forgers self-destruct paying to forge). c_v is an
  attack surface only when c_f is too cheap to self-limit.
- **PZb (public-good gap, MANDATED − ENDOGENOUS) — CONFIRMED in the cliff region,
  sign-flips outside it.** Gap by (c_f rows, c_v cols): `+11.8/+46.5/+46.1` (c_f=0),
  `+3.1/+29.4/+45.5` (0.5), `−4.1/+7.5/−32.1` (2), `−2.7/−17.2/−91.0` (8). Where
  forgery is cheap (c_f≤0.5) endogenous UNDER-provides (gap +30…+46, closer to
  collapse than mandated): each agent free-rides on the 75% average honesty, so
  small individual exposures never clear the c_v bar. Where forgery self-limits
  (c_f≥2) the sign inverts (−32…−91): mandated's blanket 2·c_v tax on every honest
  handshake becomes the larger cost, and endogenous — correctly declining checks c_f
  already made unnecessary — wins. The public good is under-provided exactly where
  needed and the mandate is pure overhead exactly where it is not.
- **Verification telemetry (endogenous, catch-rate / verify-acts / slip / strip
  per run):** c_f=0 → `0.40/519/382/113` `0.30/322/427/152` `0.18/205/596/236`;
  c_f=8 → `0.75/1468/342/292` `0.55/796/458/350` `0.16/228/752/568`. Catch rate
  falls with c_v (0.40→0.18 at c_f=0) — the under-provision made mechanical: dearer
  checks ⇒ fewer performed ⇒ more forgeries slip and strip honest partners.
- **PZc (degrade vs the U reputation baseline +1.4) — CONFIRMED with one caveat.**
  Attestation+verification beats the attestation-free reputation regime across the
  interior (mandated 0.0/0.25 +11.2 → Δ+9.8; either regime 2.0/1.0 +69–77 →
  Δ+68–75) — receipts degrade GRACEFULLY under forgery pressure and stay above
  reputation. The lone exception is the cliff cell (endogenous, c_f=0/c_v=4: −46.7
  → **Δ−48.2, BELOW reputation**): where forgery is free and self-verification
  collapses, a gate you can forge past unchecked is worse than no gate at all.
- **N=96 scale check (8 seeds):** the cliff survives scale — endogenous 0.0/4.0
  −39.2±28.4 (collapsed) vs 2.0/1.0 +7.6±3.8 (held); mandated 0.0/4.0 −5.4 vs
  2.0/1.0 +10.9.

**KILL: DOES NOT FIRE.** A threshold exists (25/28 grid cells hold near the healthy
tier, 2 collapse near the frenzy floor) — the honest advantage genuinely inverts
across the c_f/c_v grid. The unforgeable-receipt assumption the whole program rests
on is **LOAD-BEARING**, not trivially safe: at c_f=0 with no verification the tier
collapses to −179 (the full v6 feeding frenzy returns), so forgery pays even FREE,
confirming the TIER — which by construction has no walk-away veto — is the target the
walk-away right cannot immunise. One-paragraph read: the receipt is forgeable-in-
principle but the tier is defended by ECONOMICS, not cryptography — paid verification
that catches forgers, and a forgery cost that bankrupts them before they profit.
Either alone suffices when strong; the tier collapses only in the corner where
forgery is free AND verification is individually unaffordable, because endogenous
verifiers free-ride on average honesty and under-provide the very public good that
would save them — mandating it closes the gap but taxes every honest handshake,
winning at the cliff and losing everywhere else. The unforgeable-receipt idealisation
is safe wherever forging or slipping-through carries real cost and dangerous exactly
where it is free; the program's load-bearing assumption survives as a COST claim, not
an axiom.

## v28 (column AA): mortality and the persistence of paper — estates

Bills on. Death exists (stranding/battery). Two claim-inheritance regimes:
(a) CLAIMS-DIE — a dead robot's outstanding claim-stack entries void
(counterparties' stacks written down); (b) ESTATES — claims survive the
holder and settle to the company treasury (registered heir; simplest
institutional form). If baseline mortality is too rare to discriminate,
add a registered wear-out hazard (pre-committed once, same both regimes).
- **PAAa (the freeze-out):** under claims-die, agents discriminate against
  mortality risk — chain deal rate with low-battery/high-hazard partners
  drops measurably below the estates regime; the dying are frozen out of
  the claims economy exactly when they need trade most (v5's law, one
  layer up: the market lets the poor die; the claims market lets the
  DYING die).
- **PAAb:** estates close the freeze-out gap and recover most of the
  claims-die delivered/chain loss.
- **PAAc (institution, not price):** a risk-premium variant (price the
  counterparty hazard into the split instead of estates) fails to restore
  chaining with the dying — echo of the v8/H career-pricing null: the fix
  is institutional, not actuarial.
- **KILL:** if claims-die is indistinguishable from estates (mortality too
  rare or IR already prices it), report the death-rate sensitivity curve
  and the honest null.

## v29 (column AB): the crash — contagion in the counterparty web

The bills that build chains (P23) also build a counterparty web: claims
referencing future settlement are leverage. Give it a crisis. Bills on,
long horizon; at tick T_shock a pre-registered region (the far band) goes
dark via the v11 moving-field machinery (values collapse mid-flight), so
in-transit stacks reference settlements that cannot complete at expected
value. Regimes: (a) GROSS BILATERAL (P23 as-is); (b) CLEARINGHOUSE — the
company nets and mutualizes claim exposure (a central counterparty
guaranteeing settlement, funded by a registered per-claim fee).
- **PABa (contagion):** losses propagate beyond the shock's direct victims
  — write-downs reach agents ≥2 hops from the darkened region, and
  contagion depth scales with pre-shock chain length (the P23 boon has a
  tail).
- **PABb:** the clearinghouse caps contagion depth (≈ direct losses only)
  at small fee cost and shortens recovery time vs gross bilateral.
- **PABc (the scar):** without a clearinghouse, post-shock chain formation
  stays depressed well after the shock (the market remembers); with one,
  chaining resumes promptly.
- **KILL (the happy null):** if IR truncates cascades and contagion never
  exceeds direct losses, bills carry no systemic risk in this world —
  report loudly; it is the best possible answer for the thesis and must
  not be buried for being undramatic.

## v30 (column M2): the bill becomes money — transferable claims

Historically bills of exchange became banknotes by endorsement. Test the
re-derivation: claim-stack positions become ENDORSABLE — a holder may
transfer its claim position inside any bundle as payment (face value =
expected settlement, standard Φ accounting; transfer is a normal deal
row). Measure circulation, not just outcomes: velocity (transfers per
claim before settlement), claim-vs-goods flow shares, and the
medium-of-exchange index M(x) pre-registered in v15/P19c (P(x on the
opposite side of a bundle)), applied to {energy, cargo, claims}.
- **PM2a:** claims circulate (velocity > 1 in late game), and near-mature
  low-risk claims circulate preferentially (the good-collateral premium).
- **PM2b (liquidity lifts trade):** transferability raises far-band
  delivered and ≥2-hop share above static bills — agents accept chains
  more readily when the claim is spendable before settlement.
- **PM2c (the money test):** M(claims) comes to exceed M(energy) across
  seeds (p<.05) — the receipt, not the battery, becomes the medium of
  exchange. Menger's convergence, from paper.
- **KILL:** if claims never re-transfer (velocity ≈ 0 — hold-to-settlement
  dominates), money does not emerge from receipts in this world; diagnose
  the friction and report loudly.

**P26 VERDICTS (2026-07-16, registrar) — directionally right, and NOT a
bankable law; the honest scope is the result.**
- **P26a: MET on point estimate, NOT robust.** At the registered thesis
  cell (N=24, snhp+net) granular rights recover +225% of the dumbing gap
  (+12.9 vs a +5.8 gap) and dumb+granular is the single best snhp cell,
  beating smart+coarse — but neither leg is significant (p=.105/.214).
- **P26b: substitute direction at N=24 (interaction +15.0), INVERTED at
  N=96 (−7.4, complement).** The auction control shows complement at both
  scales — the substitution signal exists only inside the deal economy,
  only at village scale.
- **Horizon: front-loaded, not late-amortizing** (+12.9 → +1.7 by 7,500t;
  the anti-truncation case, checked per the standing rule).
- **KILL: does not fire at the registered cell** — but the verdict is
  scoped hard: institutions substitute for cognition FAINTLY, LOCALLY,
  EARLY, and only through tradeable claims in a bargaining economy. The
  wished-for headline ("dumb fleets with good institutions beat smart
  fleets") is NOT supported at scale and shall not be written.
- **Open engine observation (not a claim):** dumb navigation HELPS the
  auction at N=24 (286.6→296.8) — noise-dispersion may relieve Φ-routing
  congestion; logged for a future diagnosis, not asserted.

**PZ VERDICTS (2026-07-16, registrar) — the program's load-bearing
assumption survives its own attack, re-scoped from axiom to economics.**
- **KILL DOES NOT FIRE: the threshold exists.** 25/28 cells hold near the
  healthy tier; the collapse corner is real (free forgery × dear
  verification → the full v6 feeding frenzy, −179). And the c_f=0
  diagnostic confirmed the registered target: forgery pays even when free
  ONLY against the tier — the walk-away right immunizes spot bargaining;
  trust tiers, which waive the veto, are what forgery eats.
- **PZa CONFIRMED, with the shape sharpened:** the cliff is a corner, not
  a line — forgery cost ALONE defends the tier at c_f=8 (+94.5 with zero
  verification: the attack bankrupts itself), and verification alone
  defends it where forging is cheap. Collapse requires losing BOTH.
- **PZb CONFIRMED — the public-good gap, made mechanical.** Endogenous
  verifiers free-ride on the tier's average honesty: catch rate falls
  0.40→0.18 as c_v rises, under-providing exactly the good that would
  save them (gap vs mandated +46 where forgery is cheap). AND the flip is
  a design law: where forgery self-limits, mandates are pure overhead
  (gap −91). Mandate verification only where forging is cheap; elsewhere
  the mandate is a tax on every honest handshake.
- **PZc CONFIRMED, one carve-out:** receipts-under-attack beat the U
  reputation baseline in 27/28 cells (Δ up to +75); the lone loss is the
  free-forgery/dearest-verification endogenous corner (−48 vs
  reputation's +1.4).
- **The law, on the record: THE RECEIPT IS A COST CLAIM, NOT AN AXIOM.**
  The tier is defended by economics, not cryptography — safe wherever
  forging or getting caught carries real cost, dangerous exactly where
  both are free. Product translation: a notary must make forgery
  expensive (key custody, staking, liability) or verification cheap and
  structural at the gate — never left to per-agent choice, because agents
  will free-ride their own trust tier onto the cliff.

**PAA RESULTS (2026-07-16 · column AA — report, NOT a verdict; numbers loud
either way).** The freeze-out is REAL at the microstructure and estates
measurably KEEPS THE DYING TRADING and SAVES LIVES — but it does not move
aggregate throughput, so the KILL fires on delivery and misses on mechanism.
- **Base-rate check FIRST (registered before the grid).** FLATLINE mortality
  (a chassis STRANDED FLATLINE_TICKS=100 ticks unrescued dies) alone gives
  **6.5 deaths/run at N=24 and 13.6 at N=240** — both clear the ~3/run
  detectability bar, so the registered wear-out hazard (WEAROUT_AGE=900,
  WEAROUT_P=0.00035/tick, dedicated `RandomState(seed+282828)`) was NOT engaged
  in the main grid (it ships off-by-default; at N=240 it would add ~100
  deaths/run and swamp the economy — an N=24 wear-out sensitivity point ran as
  the curve's right end). Credit conservation held through every death in all
  regimes (voided-claim + estate accounting audited live over 176 runs).
- **PAAa CONFIRMED (the freeze-out is real).** Under claims-die the dying are
  frozen out of the claims economy: estates' chain-deal rate exceeds claims-die's
  in EVERY partner-hazard quartile, and the gap is real in the DYING quartiles —
  **N=24 Q3+Q4 estates 0.128 vs claims-die 0.097, Δ=+0.031, p=0.049** (9/16
  wins); N=240 dying (Q3) estates 0.200 vs claims-die 0.182. At N=24 claims-die
  even pushes the dying-most quartile (0.073) BELOW the no-bills spot baseline
  (0.089) — the claims market excludes the dying harder than having no claims at
  all. The discrimination flows entirely through Φ (the own-claim value priced at
  its survival probability 1−hazard), never a bolted-on rule.
- **PAAa′ (the freeze-out has a body count).** Deaths/run at N=240: **spot 21.6 >
  claims-die 13.6 > estates 10.1** — bills cut mortality vs spot (the dying
  offload), and estates cuts it a further ~26% vs claims-die (they keep
  offloading right up to death). Risk-premium (16.1) dies MORE than claims-die.
- **PAAb NULL on aggregate throughput (the over-served field masks it).** Estates
  does NOT recover a delivered / far-band / ≥2-hop loss — because claims-die
  barely LOST any: N=240 delivered_frac estates 0.854 ≈ claims-die 0.854
  (Δ=+0.0003, p=0.96); far-band d/m 0.45 vs 0.46; ≥2-hop share 0.495 vs 0.500
  (both ≈ the 0-death anchor 0.49, all ≫ spot's 0.02/0.37/0.023). Bills DO lift
  delivery over spot under mortality (N=240 claims-die − spot Δframe=+0.033,
  p=0.001, 8/8) — the P23 boon survives death — but the freeze-out is a
  microstructure loss the healthy fleet absorbs, invisible in total delivery.
- **PAAc CONFIRMED (institution, not actuary).** The risk-premium hop-split
  gross-up FAILS to restore the dying's chaining and makes it WORSE than plain
  claims-die: dying chain-rate N=240 risk-prem 0.122 < claims-die 0.191 < estates
  0.205 (rp−est Δ=−0.083); N=24 rp 0.090 < claims-die 0.097 < estates 0.128. The
  premium shifts the void risk onto the receiver's residual, so the receiver
  vetoes the dying MORE — the actuarial fix backfires. Echo of the v8/H
  career-pricing null: the fix is institutional (an heir), not a price.
- **KILL — the split verdict.** On AGGREGATE THROUGHPUT the KILL FIRES:
  claims-die ≈ estates on delivered_frac at every death rate (0-death anchor →
  6/run flatline → 10/run wear-out; Δframe ≤ +0.003, n.s.; 7,500t fair-horizon
  Δ=+0.004, p=0.35 — no late amortization). On MECHANISM the KILL does NOT fire:
  estates keeps the dying trading (p=0.049) and alive (−26% deaths). Honest read:
  in an over-served field the freeze-out is a distributional/mortality effect, not
  a throughput effect — the estate's value is to the DYING drone (and its
  company's fleet-preservation), not to the day's tonnage.
- **The law, on the record: PAPER OUTLIVING THE HOLDER IS A LIFELINE FOR THE
  DYING, NOT A THROUGHPUT LEVER.** Whether a dead agent's claims void or inherit
  changes WHO gets to keep trading while failing — the estate lets a low-battery
  agent offload-for-a-claim its company still collects, so it keeps chaining and
  strands less. Product translation: a bill/claim registry should settle the
  claims of a dead or vanished counterparty to a registered heir (the firm),
  never void them — voiding doesn't dent throughput but it quietly freezes out and
  kills off exactly the agents already in trouble, and pricing the hazard into the
  spread (an insurance premium) makes it worse, not better.

**PAA VERDICTS (2026-07-16, registrar) — the freeze-out is real, the heir
is the fix, and the paper saves lives without moving tonnage.**
- **PAAa CONFIRMED, and sharper than registered.** The freeze-out rides
  entirely through Φ (no bolted-on rule): pricing a holder's claims at
  survival probability makes chaining with the dying irrational, and at
  N=24 claims-die pushes the dying quartile's chain rate BELOW the
  no-bills spot baseline (0.073 vs 0.089) — **the claims market excludes
  the dying harder than having no claims market at all.** v5's law, one
  layer up, with teeth.
- **PAAb CONFIRMED on mechanism, null on throughput — the split IS the
  finding.** Estates keeps the dying trading (dying-quartile gap +0.031,
  p=.049) and cuts fleet mortality ~26% vs claims-die; the full ladder is
  the article number: **deaths/run 21.6 (spot) → 13.6 (claims-die) →
  10.1 (estates) — the paper economy with an heir kills less than half
  what the spot economy kills.** But delivered is flat across regimes
  (Δ≤+0.003, n.s., no late amortization at 7,500t): in this over-served
  field the healthy fleet absorbs the dead's abandoned cargo, so estates'
  value is DISTRIBUTIONAL AND LIFE-PRESERVING, not throughput. (Open
  note, unregistered: a scarce-fleet variant might couple lives to
  tonnage; not run, not claimed.)
- **PAAc CONFIRMED — the actuarial fix BACKFIRES, third echo of the
  career-pricing null.** Pricing mortality hazard into the split shifts
  void-risk onto the receiver, who vetoes the dying MORE: dying chain
  rate falls below plain claims-die and deaths rise (16.1 vs 13.6). The
  fix is an institution (an heir), not a spread.
- **KILL: SPLIT, recorded honestly.** Fires on the throughput leg
  (claims-die ≈ estates on delivered at every death rate), does not fire
  on the mechanism leg (the freeze-out and its cure are real, p=.049).
- **The law, on the record: paper that outlives its holder is a lifeline,
  not a throughput lever.** Product translation: a claims/bill registry
  must settle a dead or vanished counterparty's positions to a registered
  heir — never void them (the void teaches the market to shun the
  fragile) and never price the hazard into the spread (the premium does
  the shunning arithmetically).

**PAB RESULTS (2026-07-17 · column AB — report, NOT a verdict; numbers loud
either way).** The crash: bills on, claims-die mortality, LONG horizon
(7,500t); at T_shock the far band (rocks beyond the p60 nearest-refinery
distance, ~40% of the field) goes dark via the v11 machinery — stock zeros
out, in-transit far cargo settles at floor 0. Grid: {gross bilateral,
clearinghouse} × {shock, no-shock control} + spot × {shock, control};
N=240 (grid 101, 8 seeds) primary, N=24 (16 seeds) reference; σ=0.5,
τ=0.15, v5. **Registered T_shock deviation:** the contract's illustrative
3,500 lands on a SETTLED economy (the v5 field delivers/relays its far
band over an N-dependent active phase then plateaus — nothing in flight,
the shock is inert), so T_shock was registered per grid at the midpoint of
the active far-band relay phase BEFORE the grid ran: **N=240 → 1,000,
N=24 → 200** (identical across regimes and seeds within a grid; measured
15/16 N=24 seeds have far cargo in flight at 200). Φ never sees the shock
(no fear channel — write-downs land only at settlement/death, evaluated Φ
== executed Φ preserved); credit conservation held live through shock,
write-downs, fees and CCP payouts in all 144 runs.
- **PABa CONFIRMED at scale — the counterparty web is real and deep.** At
  the crash, the in-flight far-band claim stacks at N=240 carry **$2,207/run
  of exposure, 85.0% of it (per-seed 79–92%) held by hop ≥1 paper-claimants**
  — agents who had already handed the cargo off — with **$1,701 at ≥2 hops**
  and per-seed max depth **20–29 hops**. Realized write-downs at settlement/
  death: contagion $292 vs direct $20 (15×) — nearly all materialized loss
  lands on upstream claimants, because on a deep-chained parcel the
  deliverer's residual is thin (the chain ate it). Depth scales with chain
  length exactly as registered: the N=24 reference web is short and
  transient (contagion 56% mean with per-seed spread 10–100%, max hop ≤5).
  Spot control: **0% beyond hop 0 by construction** — same ore loss
  (~$2,300 exposure), all concentrated on the physical holders.
- **PABb SPLIT — the clearinghouse caps the LOSS, not the SCAR.** At N=240
  the CCP (registered fee: 5% of face per settlement; waterfall: pro-rata
  haircut) covers the crash in full: claimant realized loss **$312 → $0**
  (fees $805, payouts $314, haircut $0, pool ends $491 and stabilizes —
  trajectory flat from t≈3,000). At N=24 the pool runs DRY and the
  registered waterfall engages: fees $98, payouts $77, **haircut $41** —
  realized $115 → $41 (64% capped). But recovery is NOT shortened: chain
  rate regains the control's level at ≈2,500t under BOTH regimes (N=240) —
  gross and CCP are bit-identical on every physical column (delivered 1697
  both, deaths 10.2 both; the CCP is credit-side only, verified in the
  artifact).
- **PABc RE-SCOPED — the scar is real, physical, and regime-independent.**
  Post-shock chain-deal rate at N=240 drops to 0.600/tick vs the control's
  2.929 (**−80%**), recovering only as the control's own rate declines
  (≈2,500t); N=24 −28%, no recovery within horizon. The CCP does not speed
  it up (identical curve), and CANNOT in this world: Φ has no
  counterparty-fear channel by construction (the shock is invisible to
  valuation), so "the market remembers" has no mechanism here — the scar
  is the missing far-band trade itself, not trust. The registered PABc
  contrast (CCP ⇒ prompt resumption) is therefore untestable-as-built for
  the fear channel and REFUTED for the physical one.
- **The leverage question (spot+shock): paper spreads the loss AND pays
  for it.** The same shock costs the bills economy MORE tonnage than the
  paperless one: delivered_frac Δ(shock−ctl) = **−0.153 (gross) vs −0.107
  (spot)** at N=240 (both p<1e-4, 0/8 wins) — and the P23 boon is ERASED:
  bills−spot delivered_frac **+0.038 (p=.0002) pre-shock → −0.007 (n.s.,
  2/8) under the shock.** The bills economy commits drones to far chains
  that the crash strands mid-relay (post-shock strand onsets 1,582 vs
  spot's 346). Meanwhile the shock SAVES LIVES in every regime (N=240
  deaths 10.2 vs 14.0 control, p=.0025; spot 14.4 vs 21.6, p=.0097): the
  far band is where drones die, and when it goes dark they stop going.
- **KILL does NOT fire — but the cascade is paper, not physical.**
  Contagion exceeds direct losses on both exposure (85% vs 15%) and
  realized credit ($292 vs $20), reaching 20+ hops — bills DO carry
  systemic risk in this world. The registered happy-null clause (IR
  truncates cascades) fails on paper but HOLDS on physics: there is no
  default cascade — post-shock deaths ≈1.5/run, mortality FALLS, and the
  fleet keeps hauling. The honest law: **a claim web transmits losses as
  far as its chains are long, but in a full-recourse-free economy the
  transmission stops at the ledger — it never touches the metal.** A
  clearinghouse (5% fee) makes the paper loss vanish at scale and its
  pool survives; what it cannot buy back is the vanished trade itself.

**PAB VERDICTS (2026-07-17, registrar) — the crash is real, and it stays
on the ledger: nobody dies of paper.**
- **PABa CONFIRMED, strongly.** 85% of the crash's exposure sits with
  agents who never touched the darkened cargo, at hop-depths of 20+,
  scaling with pre-shock chain length as registered. And the leverage is
  PRICED: the same ore shock costs the paper economy more delivery than
  the paperless one (ΔdFrac −0.153 vs −0.107, both p<1e-4) and erases the
  P23 advantage entirely while the shock binds (bills−spot +0.038 → −0.007
  n.s.). The chains that carry the frontier also carry its collapse.
- **PABb SPLIT — the credit half works, the recovery half doesn't.** At
  N=240 a ~5%-fee clearinghouse absorbs the ENTIRE realized credit loss
  ($312 → $0, pool solvent); at N=24 the pool runs dry and the registered
  pro-rata haircut engages ($115 → $41) — the waterfall works, and small
  economies under-capitalize their CCP. But recovery time is IDENTICAL
  gross vs CCP (~2,500t): the scar is the missing far trade, not fear —
  Φ has no fear channel by construction, so PABc's behavioral clause is
  UNTESTABLE-AS-BUILT (honest model limit, on the record) and its physics
  clause is refuted: no institution restores the trade that vanished with
  the ore.
- **KILL: fires on neither leg cleanly — the split IS the verdict.** On
  paper, bills carry real systemic risk (contagion >> direct, deep, and
  throughput-costly). On physics, there is no cascade at all: IR plus the
  walk-away right confine the crash to the ledger — post-shock deaths
  FALL in both economies (the shock stops the dangerous far hauls),
  nobody defaults on physics, the fleet keeps hauling.
- **Registered deviation, handled per discipline:** the pre-registered
  T_shock=3,500 would have struck a settled economy (inert); per-grid
  T_shock was re-registered at the active-relay midpoint BEFORE the grid
  ran (1,000 at N=240; 200 at N=24).
- **The law, on the record: paper crashes stay on paper in this world.**
  A small-fee central counterparty can buy back the ledger's losses at
  scale (mind the small-economy dry-pool mode); what it cannot buy back
  is the market — the clearinghouse absorbs the losses, not the absence
  of trade. Product translation: claims infrastructure should ship with
  netting/mutualization sized to the economy it clears, and should never
  promise that settlement insurance restores demand.

**PM2 RESULTS (2026-07-17 · column M2 — report, NOT a verdict; numbers loud
either way).** The bill becomes money: claim-stack positions are ENDORSABLE —
a holder may transfer face value of its outstanding claims to a counterparty
inside any bundle as payment (`claims_transferable`, off by default; all prior
columns bit-identical, differential oracle green). Mechanism: a 5th signed
bundle axis CLAIM_OPTS={±3, ±10, 0} credits of face; the transfer is priced
analytically in the standard Φ accounting (claim_a−t, claim_b+t, at PAR — the
undiscounted bills valuation; the survival-discount machinery composes when a
death regime is on but the registered grid runs none) and executed by
`World.transfer_claims` (deterministic rid/parcel/stack-order reassignment with
an exact-face split of the last entry; a transferred claim settles to its
CURRENT holder). Endorsement rides the normal deal row through the
evaluated==executed assert; bills already dispatch scalar, and a grouped eval
(apply/phi once per physical bundle — byte-identical to per-row, regression-
gated by FORCE_PERROW_CLAIMS) keeps N=240 tractable. Grid: {spot, bills-static,
bills-transferable} × N=240 (grid 101, 8 seeds) + N=24 (grid 32, 16 seeds),
σ=0.5, τ=0.15, v5, 2,500t; fair-horizon 7,500t × 4 seeds on the transferable
arm. Credit/material/ledger conservation held live through every endorsement
in all 80 runs.
- **PM2a SPLIT — claims circulate, but hold-to-settlement dominates the count.**
  Velocity (endorsements before settlement per claim): mean **0.17 (N=240) /
  0.31 (N=24)** — an order of magnitude above zero and an order below the
  registered "velocity > 1": **12.2% of N=240 claims (23.1% at N=24) endorse at
  least once**, with chains up to **10 transfers** deep. Early→late: N=24 falls
  0.32→0.22, N=240 rises 0.18→0.23; the 7,500t fair horizon does NOT amortize
  it upward (0.172→0.178 — the economy settles by ~t2,500 and late windows go
  quiet, checked per the standing rule). Endorsement legs ride 6.8% of N=240
  deals (28.6% at N=24). The maturity structure explains the ceiling: a claim
  lives ~70–90t mine-to-settlement (N=24 reference seed: median 65t
  unendorsed, 91t endorsed) —
  this is short-dated commercial paper in a fast-settling field, not a durable
  note; there are only a handful of encounters in a claim's life to spend it in.
- **PM2a GOOD-COLLATERAL — confirmed at scale, INVERTED at the village.** At
  N=240 the paper that circulates sits measurably nearer settlement than the
  outstanding pool: endorsed-claim holder distance-to-refinery **45.0 vs pool
  61.2** (7,500t: 46.3 vs 69.8), chain depth 18.5 vs 25.7 — near-mature,
  low-risk claims are what pass as payment, with NO risk pricing in the
  mechanism (par valuation): the premium emerges from POSITION, not price.
  At N=24 it inverts (endorsed 10.3 vs pool 5.1): in the dense village the
  far/deep paper is what moves — reported honestly, not explained away.
- **PM2b NULL — spendability does not lift trade above static bills.** The P23
  boon replicates exactly (static−spot at N=240: delivered_frac **+0.027,
  p=.008, 8/8**; far-band d/m +0.071; ≥2-hop +0.467, p<1e-4) but transferable−
  static is noise on every registered metric: delivered_frac **Δ=+0.0043
  (p=.41, 4/8)**, far d/m +0.0005 (p=.98), ≥2-hop +0.006 (p=.52); N=24 the
  same (Δ dFrac +0.005, p=.12). The claims layer creates the chains; making
  the claim spendable moves ~nothing more. **Unregistered observation, loudly:
  stranding COLLAPSES at N=24 under transferability — 1.9 vs static's 3.9
  (Δ=−2.06, p=.011) vs spot's 6.0 (Δ=−4.13, p=.001)** — and the mechanism is
  visible in the pairing decomposition: **78% of endorsements move OPPOSITE
  energy** (paper buys battery, 18% buy cargo). The bill's marginal value is
  as a RESCUE instrument — a claim-rich, battery-poor drone pays for charge
  with paper where spot barter had nothing the donor wanted. N=240 stranding
  is already ~1 in all bills regimes (nothing to save).
- **PM2c CONFIRMED — the receipt, not the battery, becomes the medium of
  exchange.** M(x) = P(x moves opposite the thing acquired), the v15/P19c
  index, over {cargo, energy, claims} on the transferable arm: **M(claims) =
  0.64 (N=240) / 0.80 (N=24) vs M(energy) = 0.26 / 0.47 and M(cargo) = 0.18 /
  0.41** — M(claims) beats M(energy) in **24/24 seeds** (N=24 Δ=+0.33,
  Wilcoxon p=.0004; N=240 Δ=+0.38, p=.008; fair-horizon 4/4 at both scales,
  p=.125 = the 4-seed floor). The trajectory holds ≥0.57 in every active
  window at N=240 and RISES to 0.88–0.91 late at N=24 — Menger's convergence,
  from paper, within a lifetime of the first bill. Reference: M(energy) on the
  claimless arms is 0.21–0.28, so the claim didn't just beat energy, it beat
  energy's own best.
- **FLOW SHARES — the money is a medium, not the mass.** Face moved as claims
  is $3,700/run vs $177,365 as cargo at N=240 (**2.0% paper share**; 10.7% at
  N=24): paper out-scores goods per-appearance (M(claims) ≫ M(cargo)) but does
  NOT out-circulate them in value — endorsement is the economy's small change,
  clearing the margins (mostly energy) around the cargo trunk.
- **The physics note, as registered: the claim is the only WEIGHTLESS,
  LOSSLESS asset in the world.** Energy transfers burn TRANSFER_LOSS=10% and
  cargo hauls burn LOADED_MULT battery per cell, but an endorsement moves face
  1:1 at zero mass and zero energy — Φ prices this automatically (no
  money-demand heuristic anywhere), and it is exactly why the receipt
  out-mediums the battery: the real-world reason paper beat gold, re-derived
  by the accounting.
- **KILL does NOT fire — but the honest scope is narrow.** Claims re-transfer
  (velocity 0.17–0.34 ≫ 0, chains to 10, 12–23% of paper circulating), so
  money DOES emerge from receipts in this world — as a genuinely preferred
  medium of exchange (PM2c, 24/24) with a real rescue function (the N=24
  stranding collapse), NOT as a throughput lever (PM2b null) and NOT as the
  dominant store of value (velocity < 1: most paper is held to its ~80-tick
  settlement because settlement is never far away). The friction is maturity,
  not cost or risk: to see banknote-grade velocity this field would need
  longer-dated paper (slower settlement, farther fields) — registered here as
  the natural follow-on, not run, not claimed.

**PM2 VERDICTS (2026-07-17, registrar) — the receipt becomes money, and
exactly the money its maturity permits.**
- **PM2c CONFIRMED, 24/24 seeds — the money test passes.** M(claims)
  beats M(energy) in every seed at every scale and horizon (0.638 vs
  0.257 at N=240; 0.801 vs 0.473 at N=24; energy's own ceiling on
  claimless arms is 0.21–0.28). The receipt, not the battery, is the
  preferred payment side of a bundle from the first active window.
- **The physics note is the mechanism, on the record:** the claim is the
  world's only weightless, lossless asset — energy transfer burns 10%,
  loaded cargo burns per cell, endorsement moves face value at zero mass.
  No money-demand heuristic exists anywhere in the code; Φ prices the
  physics and the medium emerges. **Paper beats gold, re-derived by
  accounting.**
- **PM2a SPLIT:** claims genuinely circulate (12–23% endorsed, chains 10
  deep, near-mature low-risk paper preferred at N=240 — the
  good-collateral premium, though it inverts at village scale) but
  velocity stays under 1: every claim settles within ~80 ticks, so
  hold-to-settlement dominates. The cap is MATURITY, not cost or risk —
  this is short-dated commercial paper, not banknotes. Banknote-grade
  velocity needs longer-dated paper (slower settlement, farther fields):
  REGISTERED-OPEN follow-on, not run, not claimed.
- **PM2b REFUTED — spendability adds no tonnage above static bills**
  (every outcome null vs static; the chains were already built by the
  claims layer itself). The loud unregistered observation, logged as an
  observation: at N=24 stranding COLLAPSES under transferability (1.9 vs
  static 3.9, p=.011, vs spot 6.0) and 78% of endorsements move opposite
  ENERGY — the endorsement's marginal product is the RESCUE trade: a
  battery-poor drone buys charge with paper where barter had nothing to
  offer. The safety-net thread (v5/v8) reappears at the monetary layer.
- **KILL: does not fire, scoped hard.** Money emerges as a preferred
  medium of exchange with a rescue function — not a throughput lever, not
  a dominant store of value. The five-column arc closes: the receipt
  makes chains exist (P23), out-scales reputation (P28), beats the boss
  (PX), survives forgery as economics (PZ), outlives its holder as a
  lifeline (PAA), crashes on paper only (PAB), and ends the program as
  the money the economy chose for itself (PM2).

**FOUNDER REVIEW SCOPES (2026-07-17, registered from the article critique).**
- **PZb RE-SCOPED (founder catch): the free-rider result is conditional on
  POPULATION-PRIOR verification.** The endogenous rule priced forgery risk
  with a single fleet-wide liar fraction, not per-counterparty memory. A
  verifier that tracked individual trust histories would aim its checking
  where the risk lives and buy more protection per credit — the
  under-provision could shrink or vanish. REGISTERED-OPEN (Z2): the
  per-counterparty-trust verification regime. Noted plainly: that memory
  IS the product's mechanism, so the crude version is a floor, not a
  ceiling.
- **PAB RE-SCOPED (founder catch, the sharper one): "nobody dies of paper"
  is conditional on an ALL-EQUITY economy.** Claims are assets; no crab
  OWES anything. There is no debt, no repayment obligation, no margin
  call, no forced sale, no insolvency — so a crash can impoverish but
  structurally cannot bankrupt. Real crises kill through the liability
  side, and this world does not have one. The law is re-scoped to
  UNLEVERED claims, and the word "leverage" in the PAB record should read
  "concentration/exposure." REGISTERED-OPEN (AB2, "the crash with
  teeth"): borrowing against claims, hard repayment, default
  consequences; prediction to be written before any build.
- **#14 mechanism question (founder): answered from the V record, no
  re-scope needed.** The bulletin board removed the RENDEZVOUS (poster
  co-presence) but not the JOURNEY — the escrowed cargo still had to be
  physically fetched, and the V diagnosis already shows clock+battery
  (travel), not meetings, binding at G64. The board removed the cheap
  part of the transaction and left every expensive part in place. The
  article now says this explicitly.

## v31 (column V2): the depot — the founder's re-run of the bulletin board

The founder's mechanism question made falsifiable: V's board failed while
still requiring somebody to complete the journey; the depot removes the
JOURNEY STRUCTURE instead of the rendezvous. Depots are co-located with
existing chargers (no new geography, drones already pass there). A loaded
drone may DEPOSIT cargo at a depot with a posted claim-split ticket (V
order machinery for the posted terms, P23 bills machinery for
settlement); any later passer may take the next leg, and may RE-DEPOSIT
at another depot — chains form fully asynchronously, with no co-presence
at any hop and no drone obligated to finish the whole route. Re-run the
column-G geometry ladder with {spot, bills-only, depot(+bills)}.
- **PV2a:** the depot lifts the G64 edge above bills-only (+4.50) and
  far-band delivered/mined above bills' 0.47 — async chains carry loads
  synchronous chains still refused.
- **PV2b:** ≥2-hop share at G64 approaches its G48 level — chain
  formation decouples from encounter rate.
- **PV2c:** far miners mine more (mined per drone-tick rises:
  deposit-and-return beats haul-or-wait).
- **KILL:** depot ≤ bills-only at G64 ⇒ co-presence was never the binding
  constraint for chains either; travel/battery dominates even warehoused
  async relay, the board stays dead at any level of convenience, and we
  say so loudly.

**PV2 RESULTS (2026-07-17, sweep_v4_V2.json — report, not verdict; the numbers,
loudly either way). The column-G geometry ladder REPLICATED EXACTLY as V ran it
(grid ∈ {24,32,48,64}, σ=0.5, τ=0.15, v5, 2,500 ticks, 16 seeds) × {auction
(unperturbed comparator), snhp+net (spot, the hump), snhp+bill (bills-only
control), snhp+depot (the depot = deposit-and-return async relays, bills-settled)}.**
Design: a loaded drone docked at a charger DEPOSITS its whole load — pinned at the
co-located depot with the α*=(1+disc)/2 claim banked (V's posted-terms machinery) —
when it is UPSTREAM (the refinery is farther from the depot than its ore) and
burdened (can't cleanly haul home), and a plausible taker clears the NEXT LEG
alone (not the whole route — the depot's premise). A later passer PICKS UP with NO
DEAL_PAUSE and may stage the cargo forward and RE-DEPOSIT at the next depot; chains
form fully asynchronously, no co-presence at any hop, no drone obligated to finish.
Dead/uncollected deposits write off on expiry (V's convention). Conservation exact
across all 256 runs (material_ok, credit_conserved, escrow_conserved, ledger_
accounted all green; escrowOK=all, pinned/escrow retire to 0 at every grid).

- **The G config is faithfully reproduced — spot REPLICATES V's P29 hump to the
  decimal:** edge(snhp+net − auction) = **+4.12@G24, +4.50@G32, +7.31@G48 (peak),
  −2.69@G64** — identical to the registered P29/v8 numbers. Bills-only likewise
  reproduces the V decomposition: it RECOVERS G64 on its own, **edge +4.50@G64**
  (delivered 235.6), exactly P29's control. The comparison to V is clean.
- **PV2a: FALSIFIED — the depot does NOT lift the G64 edge; it SINKS it.** depot
  edge = **+1.88@G24, +2.12@G32, +4.44@G48, −6.50@G64.** The depot is BELOW
  bills-only at EVERY grid (depot−bills = −2.50/−1.06/−4.38/**−11.00**), and at G64
  it delivers **224.6 — LESS than even spot (228.4)** and far under bills (235.6).
  Far-band (outer 30-62c band) delivered/mined @G64: depot **0.925 < bills 0.995**
  (and < spot 0.970) — the depot HURTS far delivery. (The >62c band is empty at
  every ladder grid, so the N=240-scale P23a 0.47 is not directly commensurable;
  the ladder's own outer-band signature is the readout.)
- **PV2b: nominally MET, but NOT by the depot.** ≥2-hop share @G64 = 0.364 ≈ @G48
  0.341 — but this share is the SYNCHRONOUS bills relays the depot arm inherits
  (bills alone: 0.378@G64 vs 0.326@G48, the same pattern), NOT the async deposits.
  The depot's OWN channel is thin: async_share = 0.061/0.053/0.058/**0.035** — and
  it is HIGHEST where meetings are densest, LOWEST where sparsest (V's P29b
  reversal, replicated: a pinned offer is found where traffic passes).
- **PV2c: NULL (a tie, not a lift).** far mined/drone-tick @G64 = depot 0.00181 vs
  bills 0.00180 vs spot 0.00174 — deposit-and-return does NOT get far miners
  meaningfully more ore; the marginal 0.00001 over bills is within noise. Total
  mined/drone-tick is flat across arms (0.0040).
- **The mechanism WORKS and still loses.** Deposits post and get accepted (posted
  9.5→20.6→16.2, accepted 6.6→15.1→11.9), fully-async 3-leg chains clear and pay
  every banked split to face (unit-test verified), pause-ticks saved 20–45/run
  (negligible vs 2,500). The killer is the async surface's OWN cost: **cargo
  write-off rises 2.19→2.38→4.50→9.31 units with G** (V's exact signature, 3.4→6.9),
  as deposited parcels strand at pins no taker fetches — order_target NEVER routes
  an empty drone to a pin (11,775 calls, 0 hits): after the α split the residual is
  too small to cover the fetch haul, so pickup stays purely opportunistic. The lost
  tonnage plus the diverted-from-direct-delivery fragmentation more than eat any
  deposit-and-return saving. Stranding: depot 14.06 @G64 (spot 17.88, bills 12.19) —
  the depot's bills backbone trims strand a little, but the write-offs overwhelm it.
- **THE COMPARISON TABLE vs V's P29 (mandatory), delivered edge (arm − auction):**

  | G  | spot (=V) | bills (=V) | order-book (V) | **depot (V2)** |
  |----|-----------|------------|----------------|----------------|
  | 24 | +4.12     | +4.38      | +0.88          | **+1.88**      |
  | 32 | +4.50     | +3.19      | +0.69          | **+2.12**      |
  | 48 | +7.31     | +8.81      | +4.06          | **+4.44**      |
  | 64 | **−2.69** | **+4.50**  | −2.69          | **−6.50**      |

  The order book (V) was inert at G64 (+0.00 recovery); the depot is WORSE than
  inert (−3.81 below spot, −11.00 below bills). Removing the JOURNEY structure
  fails harder than removing the RENDEZVOUS did.
- **Read — the KILL fires, third confirmation of the P23 law.** Co-presence was
  never the binding constraint for chains, and neither was the journey. What binds
  at G64 is CLOCK + BATTERY (spot stranding triples 6.2→17.9; bills, the SYNCHRONOUS
  receipt, closes the trough −2.69→+4.50 by forming chains at the meeting, no
  warehouse needed). Warehousing cargo at a depot the drone already visits does not
  help — the depositor was never actually stuck (it reached a charger), pickup is
  unreliable (stigmergic discovery + a residual too thin to fetch → write-offs), and
  the async pins CANNIBALIZE the synchronous bill chains that do the real work
  (depot 224.6 < bills 235.6). On the record, a third independent time (order book →
  depot): **attestation's value is PRE-COMMITMENT (the binding claim that forms a
  chain at a meeting), not ASYNCHRONY (a posted offer, or now a warehoused parcel,
  that saves the rendezvous OR the journey).** The founder's async re-run of the
  bulletin board dies for the same reason the board did, one level deeper: do not
  build the depot; build the receipt.

## v32 (column AB2): the crash with teeth — debt

The registered-open follow-up, now a contract (founder: "otherwise #20
makes no sense"). Claim-collateralized credit: a drone may borrow energy
from the company treasury up to LTV × face value of its held claims.
Settlement proceeds repay debt FIRST. If write-downs push debt above
claim value, the drone enters GARNISHMENT: all future settlement income
services the debt until cleared, and no new borrowing while garnished.
LTV grid {0 (control = AB as run), 0.5, 0.8}; same shock protocol as AB
(T_shock at the active-relay midpoint, far band dark, both regimes ×
shock/control). Pre-flight constraint: borrowing take-up must be rational
(borrowed energy funds far work); if take-up ≈ 0 at the pre-flight check,
diagnose before running the grid — a debt column nobody borrows in is
vacuous.
- **PAB2-pre:** borrowing raises pre-shock far-band delivered (the bait
  is real; leverage helps until it doesn't).
- **PAB2a:** the same shock now crosses into physics: post-shock
  stranding/deaths RISE vs the unlevered crash (where they fell) — crabs
  work back paper losses, and some cannot.
- **PAB2b:** physical casualties concentrate among garnished drones at
  ≥1 hop from direct exposure — the contagion gains a body count.
- **PAB2c:** an LTV cap (and/or the CCP) bounds post-shock deaths — the
  institution now buys lives, not just credits.
- **KILL (the extended happy null):** if deaths do not rise at ANY LTV,
  the no-bankruptcy result extends to levered paper in this world (IR +
  the walk-away right + the safety floor absorb debt service), and the
  article's #20 confession gets rewritten to "I gave them debt and they
  still did not die." Report loudly either way.

## v33 (column CO): THE COMPANY, for real — agentic employees, real work, from scratch

Founder direction (2026-07-17, second correction accepted): the diorama
rendered the measured economy in company nouns and is hereby retitled
"the regime toggle" on the site; column CO is the actual vision — a
DYNAMIC company sim with REAL TASKS. Founder decisions: the org GROWS A
SERVICE FROM SCRATCH (empty repo + founding brief: "build a small
self-hostable infrastructure tool"; the org picks its own product in a
founding episode — see-where-it-goes is the point), run as RECORDED
EPISODES under a pre-registered token budget, replayed on the site from
real artifacts. Lives in companysim/ (new top-level program, engine
untouched).

**Substrate:** 4-8 employee agents (Sonnet/Haiku per the standing in-sim
exception; Opus never in-sim), each with a wallet on a hash-chained
ledger (paperswarm pattern). Work protocol, and this is the thesis made
process: a SPEC author writes a task brief + acceptance tests; an
IMPLEMENTER claims it; a REVIEWER (never the implementer) runs the tests
and merges. Payment settles on merge-with-passing-tests. Multi-stage
tasks (spec → implement → review) carry claim splits fixed at hand-off
(the bills). False completion is possible and catchable: the tests are
the receipt, authored by the counterparty. Middle roles (spec, review)
are the glue workers — PAA/U's freeze-out and sacrifice-confound
machinery now has a real-work referent.

**Regimes (across episodes):** (a) COMMAND — a manager agent assigns all
work; (b) CLAIMS — an open bounty board, no manager, splits at claim
time; (c) chargeback control only if trivially cheap. Across-episode
dynamics: budget and task-size allocation to agents by OUTCOME score vs
RECEIPT score (the Y-C promotion treatments, transplanted to real work).

**Phases:** D1a HARNESS (no LLM spend): episode runner, model-agnostic
agent adapter (fixtured for tests), wallets/ledger, task+claim protocol,
per-episode nested git workspace, artifact logger (every event → JSONL
with commit hashes/test runs), regime configs, token meter with a HARD
pre-registered per-episode budget. Fully tested offline. D1b FIRST
EPISODES: registered budget per episode committed before any run;
initial cap $20/episode, founder may revise; 1 founding episode + 2
episodes per regime; ALL episodes published, failures included, no
cherry-picking. D1c REPLAY PAGE: org chart, task board, money flows
rendered ONLY from logged artifacts (every on-screen object maps to a
commit/test/transcript; render style decided after D1b against real
data). D2 SCIENCE (gated on D1b): the Y-C predictions (reorg-inertness
PYa, glue-worker demotion PYb, receipts>outcomes PYc) as registered,
now on real work; report-not-verdict until then.

**Honesty rules (bind all phases):** artifacts public and complete;
token budget + models registered pre-run; demo phase asserts
observations only; any science claim needs its registered prediction;
the sim's numbers never blend with the swarm engine's banked results in
any public artifact without labeling which world they came from.

**v33-A AMENDMENT (founder, 2026-07-17): receipts are the allocation
unit — the org grows and cuts BY receipt evidence. The total snhp demo.**
The company's entire selection loop runs on the attested ledger, not on
judgment or raw output:
- **Provenance spine:** every task is tagged to the IDEA (product line /
  initiative) it serves; ideas form trees (idea → tasks → claim stacks →
  settlement receipts). An idea's value = its settled receipts net of
  its metered spend (token costs charged per-idea). An agent's or role's
  value = the receipt flow THROUGH it, middle roles included — spec and
  review credits sit on the stacks, so glue work is visible by
  construction.
- **The allocation round (every episode boundary):** budgets, headcount,
  and continuation are set from the receipt ledger alone. GROW: ideas
  whose receipt flow compounds get more turns/tokens/agents. CUT: ideas
  and roles whose receipt flow does not cover cost are wound down (tasks
  cancelled, agents reassigned or benched). The org chart is downstream
  of the ledger.
- **The treatment contrast (D2 science, on real work):** allocation-by-
  RECEIPTS vs allocation-by-OUTCOME (merged volume / task counts) vs
  MANAGER DISCRETION (command). Prediction shapes to be formally
  registered before D2 runs: outcome-allocation defunds spec/review (the
  sacrifice confound eats the glue roles); manager allocation drifts
  with the manager's stale view (the X result); receipt-allocation
  preserves the middle and compounds across episodes.
- **Value-anchor honesty (registered limit):** internal receipts measure
  VERIFIED WORK (counterparty tests passed), not market value — an idea
  can compound receipts while being a bad product. D1 ground truth is
  merge-with-passing-tests + the episode-end smoke run; an external
  demand signal is a registered-open D2+ extension, not assumed.
- **Demo framing, on the record:** this is the whole thesis in one
  artifact — provenance → attested valuation → allocation. The receipt
  is the unit for proving value, and the org's shape is what the
  receipts say it should be.

**v33-B AMENDMENT (2026-07-17): tying market value to receipts — change
the terminus, not the receipt.** Principle: a claim stack re-denominates
automatically when its terminal settlement is market-priced; the bills
machinery propagates value backward through the provenance spine. The
ladder, each rung registered before it runs:
- **B1 (D1b-ready), the demand oracle with escrowed pre-orders:** an
  external BUYER agent, arms-length (outside the org, outside
  allocation, no wallet flows org→buyer, protocol-enforced), holding a
  REGISTERED utility schedule over capabilities. The buyer PRE-COMMITS:
  escrows payment against a capability spec + acceptance tests BEFORE
  work (a demand-side bill of lading; the V posted-order pattern on the
  buy side). An idea's market value = its escrowed order book; revenue
  settles backward through the stacks. Scripted utility for science; an
  LLM buyer panel is a registered variant for realism.
- **B2 (D2), the internal capital market:** with demand-anchored
  termini, idea claims become tradeable (the M2 machinery). Each idea
  then carries trailing settled receipts (backward-looking) AND a claim
  price (forward-looking). Registered contrast for the allocation round:
  allocate-by-receipts vs allocate-by-claim-price.
- **B3 (registered-open), real demand:** deploy the self-hostable
  service, meter actual usage as terminal settlement. The honest long
  game; no in-sim claim may borrow its authority.
**Failure modes, named now:** Goodhart (the org builds to the oracle's
utility — realistic, and what gets Goodharted is itself data); collusion
(arms-length enforced in protocol, never prompts); the oracle fiction
(in-sim "market value" IS the registered demand schedule — every public
artifact labels it so; real-market claims wait for B3).

**PV2 VERDICTS (2026-07-17, registrar) — the founder's depot got its fair
trial, and the kill fired loudly.**
- **KILL FIRES: depot ≤ bills-only at G64, and worse — it delivers less
  than even the paperless economy** (edge −6.50 vs bills +4.50 vs spot
  −2.69; delivered 224.6 < spot's 228.4). PV2a falsified; PV2b's ≥2-hop
  share at G64 is the SYNCHRONOUS bills backbone, not the async channel
  (async share 0.035, still highest where densest — P29b's reversal
  replicates); PV2c a tie. The comparison is clean: spot reproduces the
  P29 hump to the decimal and bills-only reproduces its +4.50 recovery.
- **The mechanism of the failure is the finding: a deposited parcel
  belongs to nobody's plan.** Cargo on a carrier's back is part of a
  live route; cargo pinned at a depot is orphaned — the residual after
  the banked split is too thin to motivate a deliberate fetch, pickup
  stays opportunistic, and pins strand (write-offs rise 2.19→9.31 with
  sparsity). Severing custody severs intention. The synchronous hand-off
  never has this problem because the claim changes hands INTO a plan.
- **The law, third confirmation, now with its strongest statement:
  attestation's value is pre-commitment, not asynchrony — and removing
  the journey fails HARDER than removing the rendezvous.** Both async
  conveniences (the bulletin board, the warehouse) tried to buy with
  convenience what the claim buys with commitment; both lost to a piece
  of paper exchanged at a meeting. Travel and battery dominate, and the
  claim's job is to make a present carrier accept a route, not to make
  presence unnecessary.
- Scope, honestly: the depot-as-built deposits whole loads on an
  upstream-burdened trigger with V's posted terms; a fetch-rewarding
  variant (fatter fetch residuals) is conceivable but would be paying
  agents to overcome a problem the synchronous claim solves for free —
  registered-open only if someone can say why it wouldn't just be a
  worse bill of lading.

**CO-D1a STATUS (2026-07-17, registrar): HARNESS BUILT, 22 tests green.**
The v33-A allocation spine is ground-in, not bolted on. Builder ambiguity
resolutions ACCEPTED and notable: logical clock ⇒ byte-identical episode
replays (two identical configs → identical workspace sha1s — the
reproducibility receipt); two money pools (treasury vs compute budget)
keep the token cap clean; illegal agent actions are logged
`action_rejected`, never fatal (real LLMs will emit them); state is a
pure fold of the hash-chained event log, so episodes resume from disk.
GAP, owned by the registrar: the builder based on 5853097, before v33-B
— the buyer-escrow funding source (external wallet funding a bounty's
escrow) is NOT in D1a and becomes the first D1b work item alongside
wiring the LLMAgent. D1b remains gated on: founder-authorized spend
(registered cap $20/episode; the registered slate 1 founding + 2 per
regime ≈ 5 episodes), API key, and the Sonnet/Haiku mix choice.
**PAB2 RESULTS (2026-07-17 · column AB2 — report, NOT a verdict; numbers
loud either way).** The crash with teeth: claim-collateralized debt on the
AB crash economy (bills + claims-die, 7,500t; far band dark at the
registered per-grid T_shock — 1,000 at N=240, 200 at N=24). Mechanism
(`debt_ltv`, off by default; all prior columns bit-identical, differential
oracle green): a drone may borrow ENERGY from its company treasury against
the face value of its held claims, up to LTV × claim_value. The decision
derives from Φ — borrow size argmaxes [ΔΦ(E) − price·E·(1−hazard)] where
ΔΦ is the exact phi_bills delta of the infusion, price is the neutral
shadow price EV_INIT=0.3/unit, and (1−hazard) is the existing
stranding-hazard survival weight (death discharges the debt, so the
obligation's expected cost is below face — the limited-liability channel);
no borrow-appetite heuristic, no RNG (the argmax is deterministic, so the
dedicated-stream rule is satisfied vacuously). Settlement proceeds repay
debt FIRST (robot→treasury, inside the audited credit accounting);
debt > remaining collateral at a settlement-resolution write-down ⇒
GARNISHMENT (latched: no new borrowing, all income services debt); death
writes off outstanding debt exactly once. The treasury waterfall
(loaned == repaid + written_off + Σ outstanding) closed to <1e-6 in all
288 runs, alongside credit/material/ledger conservation. Φ never prices
the debt and garnishment resolves only at settlement/death, so evaluated
Φ == executed Φ held live throughout. Grid: LTV {0 (≡AB as run, verified —
deaths 10.2/14.0 reproduce the AB cells exactly), 0.5, 0.8} × {gross,
clearinghouse} × {shock, control}; N=240 (grid 101, 8 seeds) primary,
N=24 (16 seeds) reference; σ=0.5, τ=0.15, v5.
- **PRE-FLIGHT PASSED — take-up is real and self-targeting.** At N=240
  no-shock, **~150 of 240 drones borrow per run** (~1,100 events, 14,100–
  16,800 energy = **9–11% of all energy drawn**; N=24: ~14 of 24 drones,
  12–15%). 16–18% of borrows are struck beyond the far-band threshold
  (mean borrow distance-to-refinery 27 vs threshold 48) — the loan funds
  real field work, and borrowing is ~96% pre-shock (955 pre vs 38 post at
  N=240 gross+shk: the post-crash economy has little collateral left and
  less far work to fund). Repayment is nearly complete in controls
  (e.g. 4,159 of 4,237 loaned = 98%).
- **PAB2-pre NULL on tonnage — the bait is not throughput, it is
  survival.** Pre-shock/no-shock far-band d/m is flat: gross control
  0.471 → 0.467 at LTV 0.5 (p=.75), 0.491 at 0.8 (p=.10, 7/8);
  delivered_frac +0.002/+0.006 (n.s.). But CONTROL mortality HALVES:
  N=240 deaths **14.0 → 7.6 (LTV 0.5, p=.0003, 8/8) → 7.1 (0.8, p=.016)**;
  ccp 6.5/6.0. The Φ-derived rule self-targets the energy-poor (borrow
  exactly when ∂Φ/∂battery clears the survival-discounted price), so the
  credit line functions as claim-collateralized rescue — the same
  over-served-field logic that made PAAb and PM2b throughput-null.
- **PAB2a REFUTED — INVERTED.** Post-shock deaths do not rise at any LTV;
  total shock-cell deaths FALL: N=240 gross **10.2 → 5.5 (LTV 0.5,
  Δ=−4.75, p=.013) / 5.6 (0.8, Δ=−4.62, p=.056)**; ccp 10.2 → 3.9/4.9
  (p=.011/.032); post-shock deaths 1.5 → 0.4–0.8; post-shock strand
  onsets **1,582 → 447–470**. And the crash costs LESS tonnage with
  leverage: shock-cell delivered_frac **0.707 → 0.777/0.770 (+0.063 to
  +0.070, 8/8, p≤1e-4)**, far d/m 0.305 → 0.437–0.441 — borrowed energy
  lets chains stranded mid-relay by the crash complete anyway. Crabs do
  not die working back paper losses; the loan is the rescue. (The shock
  still saves lives at every LTV — Δ(shk−ctl) stays negative, shrinking
  14.0−10.2=−3.8 → −2.1/−1.5 as debt removes the baseline deaths the
  dark far band would have prevented.)
- **PAB2b REFUTED — garnishment is real, permanent, and harmless.** The
  shock DOES push drones underwater: N=240 gross 3.0–4.2 episodes/run vs
  ~0 in controls (N=24: ~2.6 vs ~0.1), essentially permanent once entered
  (mean 5,400–5,900 ticks, rarely cleared). But the garnished are **hop-0
  DIRECT victims, not ≥1-hop contagion** (100% of shock-cell garnishment
  entries at taint 0 at N=240), and they do not die: **0 garnished deaths
  at N=240 in every cell** (N=24: 2–4 of ~41 across 16 seeds). Garnishment
  is a ledger state — the drone keeps hauling, income services the debt,
  IR + the safety floor keep it alive. Contagion gains no body count.
- **PAB2c SUPPORTED on distress, MOOT on lives.** The CCP nearly
  eliminates garnishment (N=240 shock: gross 3.0–4.2 → ccp **0.1–0.4**
  episodes/run) — making claimants whole at settlement preserves their
  collateral, so write-downs stop pushing borrowers underwater. The LTV
  cap keeps the book collateralized everywhere: death write-offs are
  ≤5 credits of ~3,800–5,000 loaned (**~0.1%**) in every cell. But there
  are no deaths for the institution to bound — it buys solvency, not
  lives, because lives were never at stake.
- **KILL FIRES, loudly, and overshoots the happy null.** Deaths do not
  rise at ANY LTV — they FALL at every LTV × regime × scale (shock cells
  −4.6 to −6.4 deaths at N=240, p=.01–.06; controls −6.4 to −8.0,
  p≤.016). The registered mechanism (IR + walk-away + safety floor
  absorbing debt service) holds and is joined by a stronger one: the loan
  disburses ENERGY (life) against CREDIT (paper), and limited liability
  at death makes the exchange one-way — debt service never touches
  physics, while the infusion rescues exactly the drones that would have
  flatlined. The article's #20 confession is now: **"I gave them debt and
  they died half as often."** The liability side this world can build out
  of claim collateral is a lifeline, not a noose; a REAL debt crisis
  needs what this world still lacks — recourse against the body (seizable
  battery/chassis), margin calls mid-flight, or debt-service obligations
  payable in energy rather than credit. Registered-open for any AB3.

**PAB2 VERDICTS (2026-07-17, registrar) — the kill fires INVERTED: I gave
them debt and they died half as often.**
- **Pre-flight PASSED, rule honest:** ~150/240 drones borrow, 9-11% of
  all energy drawn, borrow rule derived from Φ (argmax ΔΦ(E) minus
  expected repayment cost), deterministic, no appetite heuristic.
- **PAB2-pre: NULL on tonnage, TRANSMUTED to survival.** Borrowing moves
  delivery nowhere (n.s. everywhere) — but halves BASELINE mortality
  with no crash at all (14.0 → 7.6/7.1, p=.0003, 8/8). The bait was
  never throughput. It was life.
- **PAB2a: REFUTED, INVERTED.** Post-shock deaths FALL at every LTV ×
  regime × scale (10.2 → 5.5 gross, 3.9 CCP; p=.011-.056), and the
  levered fleet buys back a third of the crash's tonnage loss (shock
  far d/m 0.305 → 0.44: borrowed energy completes the chains the crash
  stranded). LTV0 reproduces AB bit-exactly — the comparison is clean.
- **PAB2b: REFUTED.** Garnishment is real, shock-specific, and
  essentially PERMANENT (mean 5,400-5,900 ticks) — the founder's
  "worked back the loss" exists — and it is 100% hop-0 (direct victims,
  no contagion body count) and kills nobody at scale (0 garnished
  deaths, every cell).
- **PAB2c: CONFIRMED, TRANSMUTED.** The CCP cannot buy lives (none at
  stake); it buys SOLVENCY: garnishment episodes 3.0-4.2 → 0.1-0.4.
- **Treasury waterfall exact in all 288 runs; write-offs ~0.1% — the
  LTV cap keeps the book collateralized.**
- **THE LAW, fourth safety-net echo (v5 net, AA estates, M2 rescue
  trade, AB2 credit): in this world, credit against receipts IS the
  safety net with a price attached.** The loan disburses energy (life)
  against paper (credit), Φ self-targets it at exactly the drones about
  to flatline, and limited liability at death + IR + the floor keep
  every consequence on the ledger. The receipt's deepest measured
  function, at every layer it has ever been tested: rescue.
- **Scope + AB3 REGISTERED-OPEN ("the crash with real teeth"):** this
  world's debt has no recourse against the body. A real debt death needs
  a seizable battery, a margin call mid-flight, or an obligation payable
  in energy. Only that world can produce one; predictions to be written
  before any build.

**v33-C AMENDMENT (founder, 2026-07-17): real revenue, TRACK 1.** The
eBay developer account was rejected (paperswarm's live phase is DEAD;
the protocol/code remain assets). The company's real-money channel: on
completing its self-hostable tool (D1b episodes), the repo is published
publicly with a founder-owned pay-what-you-want / sponsors rail. Honesty
rules: every cent lands on the public ledger as a terminal settlement
and propagates through the claim stacks (the B-ladder terminus, real);
the revenue is LABELED audience-funded, not product-market fit; the
founder owns all accounts and rails (the registrar/agents never touch
payment credentials). Track 2 (escrowed bounties) PARKED, not
registered. D1b remains the gate: founder API key + confirmed spend
($20/episode × the registered 5-episode slate).

## v34 (column AB3): the crash with real teeth — recourse, maturities, energy obligations

The founder's levers, registered: obligations get TIME and TEETH.
Mechanism on top of AB2's claim-collateralized loans (LTV 0.5):
- **TERM STRUCTURE:** every loan carries a maturity — due at
  T_loan + M, grid M ∈ {short ~600, long ~2,400 ticks}.
- **ENERGY RECOURSE at maturity:** unpaid balance is collected in
  ENERGY, the survival resource — the treasury seizes battery. Two
  recourse regimes: (a) FULL — seizure can take battery below the
  survival threshold (the debtor's-prison world); (b) EXEMPT-FLOOR —
  seizure stops at a protected battery floor (bankruptcy protection).
  The v5 rescue net stays ON in all cells (standard physics); if the
  net simply absorbs even full recourse, that interplay IS the finding.
- Grid: AB2 config (N=240×8, N=24×16, 7,500t, shock protocol
  unchanged, LTV 0.5), maturity × recourse × {shock, control}, gross
  regime (CCP cells only if cheap). LTV0 and AB2-style no-maturity
  cells as anchors.
- **PAB3a (the teeth):** under FULL recourse the shock finally produces
  debt deaths — post-shock deaths RISE vs AB2's fall, concentrated
  among underwater borrowers, mechanism = seizure-induced stranding.
- **PAB3b (the exemption):** the protected floor eliminates recourse
  deaths at the price of tighter credit (take-up falls or rationing
  appears) — the bankruptcy-protection tradeoff, measured.
- **PAB3c (the margin call):** SHORT maturities couple the debt cycle
  to the crash (obligations come due inside the trough while collateral
  is crushed); LONG maturities let collateral recover — the crash
  crosses into physics only when term structure forces settlement
  during the trough.
- **KILL (the final safety result):** if even full energy recourse at
  short maturity raises deaths nowhere, then NOTHING in this world can
  make paper lethal — the strongest possible form of the law, and the
  article's #20 close gets its final sentence either way. Report
  loudly.

**v33-D AMENDMENT (founder, 2026-07-17): the org must be able to EVOLVE
and invest in its own growth — marketing included.** Four provisions,
binding on D1b:
1. **Non-code work class:** tasks whose deliverable is not code (docs,
   launch copy, site pages, demo media, user support) settle on ATTESTED
   REVIEW — acceptance criteria authored by a counterparty, checked by a
   reviewer who is not the author; the reviewer's attestation is the
   receipt. Weaker per-task than pytest, and priced accordingly by the
   second provision.
2. **Terminus-judged function P&L:** a non-code idea's allocation-round
   P&L is judged against the REAL terminus — site analytics (hits.jsonl)
   and PWYW revenue attributed to it — not against its internal
   settlement volume. The org may over-invest in marketing freely; the
   allocation round cuts what the terminus does not reward.
3. **New-idea funding (anti-incumbency):** proportional receipt
   allocation starves zero-history ideas, so evolution requires (a) an
   EXPLORATION FLOOR — a registered fraction of each allocation round
   reserved for new ideas — and (b) AGENT PLEDGES: an agent may stake
   its own wallet credits to seed a new idea in exchange for a claim on
   that idea's future receipts (the B2 internal claims market, pulled
   forward). Self-investment becomes endogenous: departments exist
   because members bet their own receipts on them.
4. **Idea creation is an ongoing action** (not founding-episode-only),
   and outward PUBLICATION of any marketing artifact remains
   founder-gated: agents produce in-repo; the founder presses the
   button. Article-3 note: the Track-1 chronicle ("a freelance evolving
   software company, open for business") is the registered companion
   piece — the ledger is the manuscript.

**v33-E NOTE (founder, 2026-07-17): article 3 = the five-episode
chronicle, ending at the launch version and "open for business."** D1b
logging gains narrative-grade capture requirements (full transcripts,
the founding product debate, allocation-round before/afters, firsts) —
already implied by artifacts-public-and-complete, now explicit because
the ledger is the manuscript. Chronicle notes: ARTICLE3-NOTES.md
(local, gitignored).

**v33-F FOUNDING BRIEF (Thiel/Musk/Bezos panel, 2026-07-17 — seeds the
founding episode, does not dictate the org's choice).**
- **SEED SHORTLIST, one spine (a hash-chained receipt ledger the company
  runs on itself):** (1) **A, the pocket notary** — the atom, guaranteed
  shippable; (2) **F, the agent payroll meter** (RECOMMENDED LEAD) — A
  plus per-idea/per-agent cost attribution and a shareable report, in
  Musk's redesigned form: ingests ONLY structured usage records (the
  harness's own JSONL), never scraped text — a parser that can invent a
  plausible number builds a liar, not a ledger; (3) **H, the drift/eval
  receipt harness** (Thiel's monopoly hedge) — counterparty tests as the
  product itself.
- **THE NON-NEGOTIABLE (also the first customer order, per Bezos via
  B1):** whatever the org picks must meter its OWN founding episode and
  reconcile its ledger to the founder's real API bill within a
  registered tolerance — framed in-sim as the B1 buyer's escrowed
  pre-order ("per-agent cost attribution that reconciles to my bill").
  If reconciliation fails, the org falls back to A: the budget can
  never end empty-handed, and F's fatal failure (untrustworthy numbers)
  is detected in episode one for ~$20 — the only self-detecting kill on
  the slate.
- **C, D, G stay OFF the seed** as cautionary contrasts; the org may
  resurrect one only by PLEDGING its own wallet credits against the
  v33-D exploration floor (conviction must be paid for).
- **ARC 1-PRIME (unanimous):** founding + command + command + claims +
  claims-THAT-SHIPS — the final claims episode IS the launch: v33-D
  non-code tasks (README, launch copy) settle inside its allocation
  round, and the founder presses publish at its terminus. No scripted
  pivot (Musk: a pre-registered plot turn is fake work); never end on
  the control regime (Thiel).
- **HONESTY LABEL (Musk's, binding on article 3):** n=2 per regime is a
  DEMONSTRATION, not a result; the chronicle says so plainly.
- **Program risks, on the record:** competent-commodity-code instead of
  a thing worth owning (Thiel); plausible-but-wrong cost numbers killing
  the receipts thesis on data quality (Musk); zero installs, $0
  terminus, the flywheel never taking its first turn (Bezos).

**v33-G AMENDMENT (founder, 2026-07-17): the client channel — how
external clients talk to the company.**
- **The inbox is the published repo's issue tracker** (zero new infra,
  real identity, public by default — fits the ledger ethos). A client
  request (feature ask, bug, paid order) enters the org ONLY as a
  structured inbox record; a PWYW/bounty attached to an issue is a REAL
  B1 buyer order (external escrowed-intent demand).
- **INJECTION SAFETY, the constitutional rule:** client text is DATA,
  never instructions. No agent executes inbound content; a TRIAGE action
  converts an inbox item into a task brief + counterparty acceptance
  tests through the normal protocol — the client's wish becomes work
  only through the org's own attested contract. (The thesis again: the
  spec-with-tests is the firewall.)
- **Outbound replies are founder-gated** in the D phases: agents draft
  in-repo, the founder presses send — same rule as marketing (v33-D §4).
- Harness form: episodes/inbox/ holds founder-sanitized structured
  records; the org's View includes the inbox; triage/decline are logged
  actions. The inbox OPENS at launch (end of episode 5); before that,
  the only client is the scripted B1 buyer (v33-F reconciliation order).

**v33-H AMENDMENT: post-launch episode selection — the roadmap comes
from F.** Per Musk's anti-scripting rule, episodes 6+ are not
pre-plotted. THE RULE: every post-launch episode's agenda must cite
either (a) receipt evidence from prior episodes (the meter's own
telemetry: which ideas earned, which features were used) or (b) an
inbox order. No agenda by fiat — the company's own product picks its
future. NON-BINDING MENU the evidence may select from (registered as
candidates, not plot): the first client (inbox opens, first external
order triaged); the audit (run F on a third party's real usage logs —
candidate zero: this research program's own builder pipeline); the hire
(treasury funds a roster expansion, headcount as capital allocation);
the hedge (pledges fund H if drift-receipt demand appears); the price
(first negotiated quote vs PWYW, founder executing the transaction).
Marketing needs no episode — v33-D lets allocation fund it whenever the
receipts say so.

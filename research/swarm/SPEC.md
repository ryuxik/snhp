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

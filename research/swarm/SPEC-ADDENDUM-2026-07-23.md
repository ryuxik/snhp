# SPEC addendum — paper-review response experiments (registered 2026-07-23)

*Registered BEFORE implementation and BEFORE any runs, in response to
review/PAPER-REVIEW-2026-07-23.md (M1: 64-seed re-pin of fragile headlines;
M2: second geometry; B2: SSI-style broadcast market baseline). SPEC.md is
not edited; this file is the binding registration for columns R1, GB, SSI.
House rules apply: kill conditions are bidirectional; no tuning after
seeing results; every verdict reported including failures; the analysis
path is committed code (`run.py repin_report`), not ad-hoc notebooks.*

Stats convention (unchanged from SPEC): paired by seed; paired t AND
Wilcoxon both reported; **Wilcoxon is the headline test**; wins/n reported.
Every delivered verdict is checked at k ∈ {0, 2, 5} (score_k = delivered −
k·stranded); a delivered win that reverses at k=2 does not read as a win
("agents price a drone at 1.5 ore internally; verdicts must survive k=2").
The three R1 effects are three independent already-published headlines,
each re-pinned on its own registered test — no Holm across R1a/R1b/R1c
(each headline lives or dies alone); within R2 and R3 the registered claim
names its exact cells.

---

## R1 (column R1) — power re-pin at 64 seeds

Review M1: "p=.041, p=.04, p=.03 at 16 seeds carry headline claims …
re-run the headline columns at 64 seeds before submission. If an effect
dies at 64 seeds it was not a result." Re-pins are free (goldens are
scaffolding); seeds 0..63 (a superset of the original 0..15). No physics
or mechanism changes ride along — HEAD code, HEAD constants.

**R1a — "safety-netted market beats the hive on its home ground" (σ=0).**
- Cells: preset `v3` (the harsh single-refinery world), τ=0, 2500 ticks,
  N=24, arms `snhp+net` and `team`, σ=0.0, seeds 0..63.
- Original (16 seeds, RESULTS.md Correction 2 / commit 56f0999):
  snhp+net − team = +2.1 delivered (p=.041), strandings 2.3 vs 3.9
  (about half), k5 +9.9 (p=.006).
- Provenance caveat, stated honestly: the original 16-seed artifact was
  never versioned (only the hz-vs-net half survives as
  `results/sweep_ins_v3.json`); the cited numbers are RESULTS.md's. This
  64-seed run is therefore both the re-pin and the first committed
  artifact for the comparison. If the 16-seed subset (seeds 0..15) of the
  new run materially disagrees with the cited numbers, that is reported as
  a reproduction failure, not silently absorbed.
- **Prediction:** snhp+net − team on delivered > 0 with Wilcoxon p<.05 at
  64 seeds; k5 gap stays positive and significant; snhp+net strands fewer.

**R1b — column-K map-market poisoned-deals reduction.**
- Cells: preset `v5`, σ=0.5, τ=0.15, moving field (belief_mode +
  dynamic_field + contested), arm `snhp+net`, scouting=True, with vs
  without map_trading (K0 vs K0+K1), seeds 0..63, 2500 ticks.
- Original (sweep_K.json, n=16, re-verified from the artifact today):
  poisoned 5.38 → 3.75 (−30%), p_t=.038, p_w=.040.
- **Prediction:** map trading reduces poisoned deals (K0 − (K0+K1) > 0 on
  poisoned) with Wilcoxon p<.05 at 64 seeds. Delivered difference reported
  descriptively (the original claim is books, not output).

**R1c — column-J P16b arrival-capture inversion.**
- Cells: preset `v5`, σ=0.5, τ=0.15, moving field (belief_mode +
  dynamic_field + contested), NO scouting, arms `auction` and `snhp+net`,
  seeds 0..63, 2500 ticks. Metric: `arrivals_mined` (the registered P16b
  provenance proxy).
- Original (sweep_J.json, n=16, re-verified from the artifact today):
  auction 46.2 vs net 32.4 units/run, p_t=.033, p_w=.030.
- **Prediction:** auction − snhp+net on arrivals_mined > 0 with Wilcoxon
  p<.05 at 64 seeds. The exploratory delivered inversion (auction
  out-delivers, p=.044 at 16 seeds) is REPORTED at 64 seeds but stays
  flagged post-hoc either way — it was never registered and this addendum
  does not launder it.

**Verdicts (per effect):**
- **WIN:** original direction, Wilcoxon p<.05 at 64 seeds → the headline
  keeps its place in the paper with the 64-seed number.
- **KILL:** p≥.05 at 64 seeds → the effect is downgraded to exploratory in
  the paper — the headline dies as a claim. A SIGN FLIP that is itself
  significant is reported as an active refutation, stronger than a
  downgrade.
- Column verdict: WIN = all three re-pin; PARTIAL = one or two re-pin
  (surviving headlines keep claim status, dead ones are downgraded);
  KILL = none re-pin.

Effect sizes with 95% CIs are reported for all three regardless of
verdict.

---

## R2 (column GB) — geometry B replication

Review M2: C2/C3 are one-map findings on the harsh world; replicate on a
second layout or scope explicitly.

**Geometry A** (the incumbent, preset `v3`): 32×32; refinery (26,6),
owner None; sources (10,6) and (6,26) at Manhattan 16 and 40 from the
refinery, BOTH in the western half; charger (22,6), 4 from the refinery
(pad-adjacent); 60+60 stock; N=24, one company, robots spawn uniform.

**Geometry B** (new preset `v3b`, registered exactly):
- refinery (6,16), owner None — mid-west edge instead of a corner;
- sources (26,4) and (18,28): Manhattan 32 and 24 from the refinery —
  different distance profile (24/32 vs 16/40: the cheap 16-hop source is
  gone, the 40-hop death-march is gone), placed in OPPOSITE quadrants of
  the eastern half (non-mirrored, not co-located on one side);
- charger (14,14): 10 from the refinery (decoupled from the pad; 22 and
  18 from the two sources) — mid-field charging instead of pad-adjacent;
- everything else identical to `v3`: 60+60 stock, N=24, one company,
  v3 battery draws (mean 60, spread 40σ, floor 10), same physics.
Round-trip arithmetic keeps it in the same difficulty class as A: the far
loop (32 out + 48 loaded-equivalent) exceeds mean battery, so charging
economics still bind at σ=0.

**Cells:** arms {null, auction, snhp, snhp+net, team} × σ ∈ {0, 0.5, 1.0}
× seeds 0..23, τ=0, 2500 ticks, preset `v3b`.

**Prediction (registered):** the SIGN of (snhp+net − auction) on delivered
at σ ∈ {0.5, 1.0} replicates geometry A (positive at both; on A it was
positive at every σ, Wilcoxon p≤.004 at σ≤0.5). Bar: positive point
estimate at BOTH σ≥0.5 cells, Wilcoxon p<.05 at ≥1 of them, and no k2
reversal where delivered wins.

**Secondary (reported, not pinned):** the full ladder ordering (team vs
snhp+net vs snhp vs auction vs null) per σ; strandings; whether the
"safety-netted market beats the hive at low σ" pattern recurs on B.

**Verdicts:**
- **WIN:** bar met → C2's market-lineage comparison is a two-geometry
  result; the paper keeps the general claim with both maps cited.
- **PARTIAL:** positive point estimates at both σ≥0.5 but nothing
  significant → "direction replicates, underpowered on B"; the paper keeps
  the claim scoped as "geometry A (significant), geometry B
  (directional)".
- **KILL (bidirectional):** (snhp+net − auction) sign FLIPS at any σ≥0.5
  (or is significantly negative anywhere) → the paper's C2/C3 claims get
  scoped to geometry A explicitly, in the abstract as well as §6 — no
  general "beats the market lineage" language survives.

---

## R3 (column SSI) — the stronger market baseline: `auction_ssi`

Review B2: the MURDOCH-style bilateral handoff cannot carry "dominates the
single-issue market lineage"; the community standard is broadcast
sequential single-item auctions (Koenig et al.). We implement the
strengthening rather than the rewording (option (a)).

**Mechanism (registered before implementation):** `auction_ssi` =
`rules` base (trophallaxis rescue floor, exactly like `auction` and
symmetric to snhp+net's net) + a broadcast SEQUENTIAL SINGLE-ITEM auction
phase each tick, after the pairwise phase:
- **Items are single issues by construction:** a cargo lot (handoff of
  q = min(4, seller.load, bidder headroom) units — 4 = MAX_CARGO, the
  same bundle-cap every arm uses) or an energy lot (largest feasible
  e ∈ {8, 4, 2} — the same ENERGY_OPTS magnitudes the bundle space uses).
  An item is exactly a (q,0,0) or (0,e,0) bundle; the arm structurally
  cannot logroll (asserted in code).
- **Broadcast:** for each announcer, ALL robots within Chebyshev R_COMM=2
  (the standard interaction radius) are eligible bidders — multi-bidder
  competition, not bilateral matching. Cargo receivers must not be
  stranded (the same rule the MURDOCH rung applies); energy items may
  rescue stranded robots (priced rescue is allowed to compete with the
  free net).
- **Bids are truthful scalars:** a bid is the bidder's TRUE marginal
  utility delta ΔΦ for taking the other side of the item, evaluated
  through the SAME physics code path every arm uses (apply_bundle on the
  live robots with log=False + snapshot/restore). No reported-value
  channel, no lies — this is the cooperative Koenig lineage.
- **Clearing rule:** best bid wins; the award executes iff the gaining
  side's ΔΦ exceeds 1.1 × the losing side's |ΔΦ| — the SAME 1.1 hysteresis
  factor the MURDOCH rung has always used, so the rung differs from
  `auction` by exactly {broadcast multi-bidder, energy-as-item, sequential
  rounds}, one lineage step.
- **Sequential rounds:** the globally best clearing item executes, both
  parties pay DEAL_PAUSE=3 and leave the phase; remaining cached bids are
  re-awarded; rounds continue until no item clears. Non-parties' states
  are untouched by an award, so one evaluation pass per tick is exact.
- **Comparability discipline:** pair cooldowns as everywhere (5 failed /
  15 dealt); TXN_COST debited per side per executed exchange; DEAL_PAUSE
  identical; evaluated Φ == executed Φ asserted on every award; the phase
  consumes NO RNG (deterministic tie-breaks by margin, then rid).

**Cells:** preset `v3` (C2's home ground), τ=0, 2500 ticks, arms
{auction_ssi, snhp+net} × σ ∈ {0, 0.5, 0.75} × seeds 0..23. Plain
`auction` runs at the same cells as a descriptive anchor (is SSI actually
the stronger market? reported, not pinned).

**Predictions:**
- **R3-P1 (registered):** snhp+net > auction_ssi on delivered at σ≥0.5 —
  positive point estimates at BOTH σ ∈ {0.5, 0.75}, Wilcoxon p<.05 at ≥1
  of them, and the win survives k2 (score_k2 gap not significantly
  negative where delivered wins). σ=0 is a sanity cell (twin utilities,
  minimal heterogeneity → mechanisms should roughly tie); it carries no
  claim.
- **R3-P2 (reported):** auction_ssi ≥ auction on delivered (the
  strengthening is real); if SSI is WEAKER than bilateral MURDOCH here,
  that is reported and the B2 response falls back to claim-rewording
  (option (b)) — we do not pick whichever baseline loses harder.

**Verdicts:**
- **WIN:** R3-P1 holds → the paper's market-lineage claim upgrades to
  "dominates both the bilateral (MURDOCH) and broadcast-SSI single-issue
  lineages", with the SSI rung described honestly.
- **PARTIAL:** positive at both σ but no significance → the abstract keeps
  only the bilateral claim; §4 reports the SSI comparison as directional.
- **KILL (bidirectional):** snhp+net NEVER significantly beats auction_ssi
  at any σ (or auction_ssi significantly beats snhp+net anywhere) → the
  "beats the market lineage" claim DIES; every C2 claim is rewritten to
  name the bilateral baseline explicitly ("a MURDOCH-style bilateral
  handoff auction"), per the review's option (b), and the SSI result is
  reported as the reason.

---

## Run plan (committed with this registration)

- `run.py --column R1` → 384 runs (2×64 v3-σ0 + 2×64 J-cells + 2×64
  K-cells), artifact `results/sweep_v4_R1.json`, log
  `results/rerun64_R1.log`.
- `run.py --column GB` → 360 runs, artifact `results/sweep_v4_GB.json`,
  log `results/geoB_GB.log`.
- `run.py --column SSI` → 216 runs, artifact `results/sweep_v4_SSI.json`,
  log `results/ssi_SSI.log`.
- Scoring: `run.py --analyze <artifact>` prints `repin_report` — the
  committed analysis path for every number above. Verdicts are appended to
  THIS file after the artifacts exist, never edited into the text above.

## VERDICTS (appended 2026-07-23 after the runs; registration above unedited)

Artifacts: `results/sweep_v4_R1.json` (384 runs), `results/sweep_v4_GB.json`
(360), `results/sweep_v4_SSI.json` (216); logs `rerun64_R1.log`,
`geoB_GB.log`, `ssi_SSI.log` (the `repin_report` sections are the numbers
below, verbatim). Implementation landed with 3 new tests; full suite 174
green; no physics or constant changed.

### R1 — WIN (all three headlines re-pin at 64 seeds)

- **R1a WIN.** snhp+net − team on the v3 world at σ=0: delivered **+1.77
  [+0.32, +3.21], p_w=.026** (35/64); stranded **−1.56, p_w=.0001** (2.27
  vs 3.83); k5 **+9.58, p_w=.0002**. All three registered conditions hold.
  Provenance bonus: the seeds-0..15 subset reproduces the previously
  unversioned RESULTS.md numbers essentially exactly (+2.12 p_w=.041
  delivered; 2.31 vs 3.88 stranded; k5 +9.94 p_w=.006) — HEAD code
  regenerates the original 16-seed run, and this artifact is now the
  committed one.
- **R1b WIN.** Map market poisoned-deals cut: **5.00 → 3.53 (−29%),
  Δ=+1.47 [+0.69, +2.24], p_w=.0007** (42/64). Delivered descriptive wash
  (+4.53, p_w=.46) — the claim stays "books, not output", as registered.
- **R1c WIN.** Arrival-capture inversion: auction − snhp+net on
  arrivals_mined **+8.98 [+0.44, +17.52], p_w=.022** (42.7 vs 33.7).
  Effect size shrank from the 16-seed +13.8 but holds. Descriptive: the
  previously post-hoc delivered inversion is now +10.19 (p_w=.011) at 64
  seeds — still reported as post-hoc (registered so); k2/k5 remain a wash
  (+7.1 n.s. / +2.5 n.s.), i.e. the auction still pays its gold edge in
  dead drones.

Paper consequence: all three headlines keep claim status with 64-seed
numbers and CIs; no downgrade needed.

### R2 (column GB) — WIN (the market-lineage comparison replicates on geometry B)

(snhp+net − auction) on delivered: σ=0: **+6.42, p_w=.0002**; σ=0.5:
**+3.83, p_w=.0038** (18/24); σ=1.0: **+4.42, p_w=.0007** (19/24). No k2
reversal anywhere — k2/k5 gaps are larger than the delivered gaps (σ=0.5
k5 +26.96, p_w=.0001). Bar met at every registered point: positive at both
σ≥0.5 cells with BOTH significant (bar required ≥1).

Secondary, descriptive: the ladder ordering replicates (team ≥ snhp+net ≥
snhp > auction > null on delivered at every σ). One honest nuance: on
geometry B the hive is NOT edged on raw delivered at σ=0 (net 118.8 vs
team 119.5, at the 120 ceiling) — but team strands 9.17 vs the net's 0.96,
so the net dominates every k-score; the "survival is where the net beats
planning" law holds on B in its k-score form. C2's market-lineage claim is
now a two-geometry result.

### R3 (column SSI) — **KILL FIRED**, the strong form

- **R3-P1 dies.** snhp+net − auction_ssi on delivered: σ=0.5: **−1.75
  [−3.48, −0.02], p_w=.038** — the SSI market SIGNIFICANTLY BEATS the
  bargaining arm on raw output; σ=0.75: −1.75, n.s. (10/24). The
  registered kill condition ("never significantly beats, or auction_ssi
  significantly beats anywhere") fires on both halves. Registered
  consequence, applied without spin: **the paper's "beats the market
  lineage" claim is DEAD.** Every C2 claim must name the baseline — "a
  MURDOCH-style bilateral handoff auction" (review B2 option (b)) — and
  the SSI result is reported as the reason. Abstract language included.
- The k-discipline nuance (reported, does not resurrect the claim): the
  SSI market buys its output parity in strandings — snhp+net wins score_k5
  at σ=0.75 (**+12.42, p_w=.027**) and at the σ=0 sanity cell (k2 +19.92,
  k5 +37.67, both p_w≤.0001, with delivered +8.08 p_w=.058 there). At
  σ=0.5, k2/k5 are a wash. Pattern consistent with the program's standing
  result: markets convert drone capital into gold; the bargaining+net arm
  keeps the fleet alive. An honest paper states: on raw delivered the
  broadcast SSI lineage is AT LEAST the equal of Nash-bundled bargaining
  on this world; the bargaining arm's edge is survival-priced (k>0), not
  output.
- **R3-P2 (descriptive): the strengthening is real.** auction_ssi −
  auction on delivered: +8.75 (p_w=.0001) at σ=0.5, +7.38 (p_w=.045) at
  σ=0.75 — SSI is a genuinely stronger market than bilateral MURDOCH at
  σ≥0.5, so the kill was earned against a real opponent, not a strawman.
  (At σ=0 SSI ties MURDOCH on delivered and is worse on k — its ~1,300
  awards/run churn energy through TXN costs and pauses with no
  heterogeneity to harvest.)
- Structural note for the paper: auction_ssi is single-issue BY
  CONSTRUCTION and cooperative (truthful ΔΦ bids, no payments) — it does
  not contradict C1 (single-issue IR trade between SELF-INTERESTED agents
  remains infeasible; SSI awards are not IR — the losing side eats
  negative ΔΦ whenever 1.1×|loss| < gain). C1 stands untouched. What dies
  is only the claim that bundling+bargaining beats the market LINEAGE on
  output; what survives is C2 scoped to the bilateral baseline, plus the
  k-score framing.

### Program note

Three of three registered columns produced decision-grade outcomes: two
WINs that harden the paper (R1, R2) and one registered kill (R3) that
forces the honest rewrite review B2 predicted. This is the fourth time a
strengthened market baseline has matched or beaten the bargaining arm on
raw output while losing on fleet survival (v3 hazard, v9 career pricing,
v11 moving field, now SSI) — the paper's C2 section should say so in one
sentence instead of implying market dominance.

---

## R4 — provenance re-pin of the C2/C3 artifacts (registered 2026-07-23, AFTER R1–R3 closed, BEFORE any R4 run)

*Founder decision: the paper uses post-correction numbers ONLY. The C2/C3
sections (PAPER-DRAFT §4.2/§4.3) currently cite `sweep_v2.1.json`
(2026-07-14, 888 runs) and the v3 regime narrative cites `sweep_v3.json`
(2026-07-14, 960 runs) — BOTH predate CORRECTION 2 (pad-strand fix +
DEAL_PAUSE, commit 56f0999, 2026-07-15) and are therefore pre-correction
physics. R4 regenerates both grids cell-for-cell under HEAD physics (pad
fix + DEAL_PAUSE + charger-livelock fix; livelock is vacuous here — no
gauge/belief cells in either grid — stated for completeness).*

**Cells (exact replicas of the originals, HEAD code, preset `v3`, τ=0,
2500 ticks, seeds 0..23):**
- `R4v21` → `results/sweep_v2.1_head.json` (888 runs): {null, rules,
  auction, team, team[energy], snhp, snhp+net} × σ ∈ {0, .25, .5, .75, 1}
  plus the two C1 ablation cells snhp[cargo] and snhp[cargo+energy] at
  σ=1.
- `R4v3` → `results/sweep_v3_head.json` (960 runs): {null, rules, auction,
  team, snhp, snhp+net, snhp-hz, snhp+net-hz} × the same 5 σ.

**Contamination disclosure (registered honestly):** column SSI (run
earlier today) already exposed snhp+net − auction on this world under HEAD
at σ ∈ {0, 0.5, 0.75} (positive at all three, from the R3-P2 anchor
cells). The registered content R4 adds that is NOT already seen: the
σ=0.25 cell, all Wilcoxon significance levels on the full grid, the
entire C3 gradient (plain `snhp` has not run under HEAD anywhere), the
team/team[energy]/net secondary orderings, and the v3-grid hz contrasts.
No prediction below was adjusted after seeing the SSI numbers; the C2
prediction was fixed by the coordinator's instruction before this
registration was written.

**Registered predictions:**
- **R4-C2 (ordering survives):** snhp+net − auction on delivered is
  positive at every σ, Wilcoxon p<.05 at each of σ ∈ {0, 0.25, 0.5} (the
  original claim's significant range). Magnitude may shrink (the
  correction historically cost ~40% of the bargaining−auction gap).
- **R4-C3 (gradient survives):** snhp − auction on delivered is
  point-estimate monotone non-decreasing over σ ∈ {0, 0.25, 0.5, 0.75},
  positive and Wilcoxon-significant at σ=0.75. The σ=1.0 break is allowed
  (the original was PARTIAL there; no claim).
- **Secondary re-pins (reported with deltas, not pinned):** snhp > null
  everywhere; price-of-selfishness ladder (team − snhp) by σ and whether
  P3's refutation pattern (grows with σ) persists; snhp+net vs team at
  σ ≤ 0.5; the net-hurts-at-σ=0.75 negative (snhp vs snhp+net); team −
  team[energy]; C1 ablation inertness (snhp[cargo] ≈ jettison-only, ~0
  deals; snhp[cargo+energy] deal count); v3-grid hz contrasts (snhp-hz vs
  snhp / vs snhp+net) — expected to CONFIRM Correction 2's "regime law
  died" at 24 seeds; if snhp-hz significantly beats snhp+net on delivered
  anywhere, that partially resurrects the old regime law and is reported
  loudly (k5 governs per house rule).
- **KILL (bidirectional, no exceptions):** any registered ordering FLIPS
  (significant reversal) → the affected paper claim is rewritten to the
  corrected result. Shrinkage is not a kill; reversal is.

**Paper consequence (pre-committed):** PAPER-DRAFT §4.2/§4.3 are updated
so every C2/C3 number cites the HEAD artifacts; pre-correction numbers
remain ONLY inside explicit correction-history narration. RESULTS.md
pre-correction sections get supersession banners (JOB 2, same commit).
Analysis path: `repin_report` [R4] section, committed before the runs.

## R4 VERDICTS (appended 2026-07-23 after the runs; registration above unedited)

Artifacts: `results/sweep_v2.1_head.json` (888 runs, 50s wall),
`results/sweep_v3_head.json` (960 runs, 66s wall); logs `r4_v21.log`,
`r4_v3.log` ([R4] repin_report sections are the committed numbers).

**R4-C2 — WIN.** snhp+net − auction on delivered: +6.58 (p_w=.0004) /
+3.33 (p_w=.0140) / +7.00 (p_w=.0002) / +5.62 (p_w=.0519) / +6.17
(p_w=.0113) at σ = 0/.25/.5/.75/1. Positive at every σ ✓; p_w<.05 at all
of σ ∈ {0, .25, .5} ✓. k2/k5 gaps larger and significant at EVERY σ (σ=.5
k5 +25.96, p_w=.0001). Magnitude vs the pre-correction +2.1..+8.9: same
band (+3.3..+7.0) — this comparison barely shrank.

**R4-C3 — WIN.** snhp − auction: −7.04 → −1.96 → +2.00 → +7.21 → +1.50.
Monotone non-decreasing over σ=0→0.75 ✓; +7.21 p_w=.0089 at σ=0.75 ✓;
σ=1.0 break persists (+1.50 n.s., allowed). Magnitude: the 0→0.75 swing
shrank 36.6 → 14.3 units (~60%) — direction and shape intact, size much
smaller. The paper now reports the corrected gradient.

**Secondary re-pins — two v2.1-era side claims DIED (paper rewritten per
the kill clause), two dissolved into nuance:**
- **snhp > null FLIPPED at σ=0:** −6.29 [−8.61, −3.97], p_w=.0001, 2/24
  (at σ≥0.25: +23.0..+31.0, all p_w≤.0001, 23–24/24). With exact twin
  fleets bargaining is pure overhead. §4.2 rewritten; theory-consistent.
- **team − team[energy] COLLAPSED:** −0.67..+2.46, significant only at
  σ=0.75 (+1.62, p_w=.0137) vs the pre-correction "+1.8..+17.1, sig 4/5".
  Once deals cost time the cooperative multi-issue dividend on this world
  is ≈0. §4.1 rewritten; the C1 rebuttal now rests on the structural IR
  half alone.
- **"Net hurts at σ=0.75" dissolved:** snhp − snhp+net = +1.58 n.s. (was
  +8.9); the net now helps significantly at every other σ. The old honest
  negative was itself a physics artifact.
- **Net vs the hive on the harsh world:** +1.62 (p_w=.11) at σ=0 on 24
  seeds — consistent with the significant 64-seed R1a (+1.77, p_w=.026);
  n.s. at σ=.25/.5; hive wins delivered at σ≥0.75 (−15.46/−12.00,
  p_w≤.0002). The v2.1-era "beats the ceiling at σ≤0.5" survives only in
  its survival/k-score form, exactly as Correction 2 re-scoped it.
- **Coordination gap (P3 still refuted):** 12.0 → 4.2 → 5.2 → 13.9 → 16.7
  (all p_w≤.048) — dips mid-σ, grows at high σ; smaller than the
  pre-correction 11→27.5 ladder.
- **C1 ablations re-pin clean:** snhp[cargo] 0.38 deals/run
  (jettison-only ✓); snhp[cargo+energy] 22.96 (two-issue bundles trade —
  C1 untouched).
- **v3 grid, the registered loud-report case FIRED and died on k5:**
  snhp-hz − snhp+net at σ=0.75 = +5.67 delivered, p_w=.0396 (p_t=.087,
  one test of two) — but hz strands 19.79 vs the net's 4.62 (k5 9.3 vs
  79.5, a ~70-unit k5 deficit). Under the registered k5-governs rule the
  regime law stays DEAD; the delivered-only blip is reported here and
  goes no further. snhp-hz − snhp: +8.50 (p_w=.0013) at σ=1.0 only.
  Descriptive: snhp+net-hz is the best arm on the v3 grid at σ≤0.5
  (delivered 118.7–119.0, k5 97.8–105.8).

**Paper changes applied (PAPER-DRAFT.md):** §4.1 multi-issue fraction +
team[energy] collapse; §4.2 rewritten around `sweep_v2.1_head.json`
(C2 ordering, hive scoping, snhp-vs-null flip, corrected honest
negatives, corrected coordination-gap ladder); §4.3 corrected gradient
(−7.0→−2.0→+2.0→+7.2→+1.5, 14.3-unit swing, σ=0 significance note);
submission-notes items 1–2 marked RESOLVED. Pre-correction numbers remain
only inside explicit correction-history narration.

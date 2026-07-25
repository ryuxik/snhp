# SPEC addendum — Paper 2 power re-pin (registered 2026-07-23, BEFORE the runs)

*Registered BEFORE any battery run, per PAPER2-OUTLINE.md §8 ("register and
run a 64-seed re-pin of the headline cells (R1-style) before submission")
and the same review-M1 logic that drove column R1. SPEC.md and
SPEC-ADDENDUM-2026-07-23.md are NOT edited; this file is the binding
registration for columns P2R1, P2R2, P2R3. House rules apply: kill
conditions are bidirectional; no tuning after seeing results; every verdict
reported including failures; the analysis path is committed code
(`run.py --analyze` → the `repin_report` [P2-R1]/[P2-R2]/[P2-R3] sections),
not ad-hoc notebooks.*

Stats convention (unchanged): paired by seed where two cells are compared;
liar advantage is the committed v6 statistic (within-run liar − honest mean
credit, one-sample test across runs); paired t AND Wilcoxon both reported;
**Wilcoxon is the headline test**; wins(or pos)/n and 95% CIs reported.
Seeds 0..63 are a superset of the original 0..15 (0..7 for N=240), so the
original-subset reproduction is checkable inside every new artifact. The
three P2-R1 effects are three independent published headlines — no Holm
across them; each lives or dies alone. No physics, mechanism, or constant
changes ride along: the battery adds job builders and report sections only
(full suite 174 green before launch).

**Provenance discipline (stated before running):** the "original" numbers
below are RE-VERIFIED TODAY from the committed artifacts through the
committed analysis path (`sweep_D.json`, `sweep_E.json`, `sweep_F.json`,
`sweep_v4_P2.json`, `sweep_v4_P3.json`) — not from RESULTS/SPEC prose.
Where prose and artifact disagree the artifact governs (house rule from
R1b). Two such disagreements found and disclosed now:
- P23a prose (SPEC P23 VERDICT) says Δdfrac +0.0295 (p=.005, 7/8), ≥2-hop
  → 0.500, stranding → 1.12; the committed artifact at HEAD gives
  **+0.0273 (p_t=.0010, p_w=.0078, 8/8), ≥2-hop 0.0252 → 0.4924,
  stranding 2.12 → 1.00 (n.s. at 8 seeds)**.
- v7 prose (RESULTS P12a) cites delivered 238.9 → 239.8 → 229.5, which
  predates the Correction-2 column-F re-run; the governing artifact gives
  **238.4 → 233.2 → 238.9 with every paired delivered delta n.s.**
Also: the paper-outline §2 figure "+3.9 credit on a ~95 base, p=0.71" is
the PRE-correction v6.0 number; the corrected veto-tier cells (registered
below) are the ones the paper must cite.

HEAD-reproduction check (pre-run): a single N=240 bills+dwell run at HEAD
reproduced the committed artifact's seed-0 row exactly (delivered 1959,
delivered_frac 0.8163) — the original cells ARE reproducible from HEAD.

---

## P2-R1 (column P2R1, 704 runs) — v6.0/v6.1 headline cells at 64 seeds

**Cells** (exact original job dicts, preset `v5`, σ=0.5, τ=0.15, 2500
ticks, seeds 0..63):
- v6.0 veto tier (column D): arms {snhp-hz, snhp+net} × f ∈ {0 (baseline),
  0.25, 0.5}, UNdefended.
- v6.1 joint tier (column E): trust-open-hz × f ∈ {0.25, 0.5} (defended);
  trust-gated-hz × f ∈ {0 (anchor), 0.25, 0.5} (defended).

**Originals (16 seeds, re-verified from sweep_D/E.json today):**
- Frenzy: open f=.25 liarAdv **+179.0** [+159.0, +199.0] p_w<1e-4, strip
  271.3/run; f=.5 **+126.4** [+115.1, +137.8] p_w<1e-4, strip 326.5/run.
- Gate: gated f=.25 **+9.5** [−8.5, +27.6] p_w=.348, strip 0.0; f=.5
  **−2.2** [−18.1, +13.8] p_w=.562, strip 0.0.
- Veto tier: snhp-hz **+13.8** p_w=.379 / **+15.9** p_w=.105 (f=.25/.5);
  snhp+net **+6.2** p_w=.404 / **+7.2** p_w=.298. All n.s.

**Predictions:**
- **P2-R1a (frenzy):** liarAdv > 0 with p_w<.05 at both f; strip
  > 100/run at both. Directions persist.
- **P2-R1b (gate):** liarAdv stays statistical zero (p_w≥.05) at both f;
  strip deals **0.0 exactly** at both (mechanical property of the gate).
- **P2-R1c (veto tolerance):** liarAdv stays n.s. (p_w≥.05) in all four
  liar cells at the higher power.

**KILLs (bidirectional, per effect):**
- **P2-R1a:** frenzy n.s. or sign-flipped at 64 seeds → the
  cooperation-exploitability headline dies; a significant negative is an
  active refutation, reported louder.
- **P2-R1b (the registered kill of record):** if the GATED liar advantage
  becomes significantly POSITIVE at 64 seeds, **the attestation headline
  is downgraded** — Paper 2 §3's central claim. A significantly NEGATIVE
  gated advantage is not gate failure but a new "the gate over-prices
  dishonesty" result — reported as new, never laundered into the old
  claim. Any strip > 0 at the gated tier is a mechanical gate breach:
  bug-level, loudest possible report.
- **P2-R1c:** any veto-tier cell significantly positive → "lying barely
  pays at the veto tier" is downgraded to "lying pays a small, real
  amount," with the measured size in §2. Stated now: all four 16-seed
  point estimates are positive (+6..+16); at 4× seeds this is the cell
  most likely to cross p<.05. If it does, that is a finding to report,
  not a failure of the re-pin.

Verdict grammar (as column R1): WIN = original direction + registered
significance/nullity pattern holds; KILL = the registered kill fires;
effect sizes with CIs reported regardless.

---

## P2-R2 (column P2R2, 192 runs) — v7 gauge-poisoning dose-response at 64 seeds

**Cells** (exact original column-F job dicts): snhp-hz, preset `v5`,
σ=0.5, τ=0.15, 2500 ticks, s₇ ∈ {0, 0.15, 0.30}, f=0, self-margin OFF,
seeds 0..63.

**Originals (16 seeds, re-verified from sweep_F.json today):** poisoned
**0.00 → 13.19 → 23.44**/run; steps +13.19 (p_w=.0004, 16/16) and +10.25
(p_w=.0005, 15/16); delivered 238.4 → 233.2 → 238.9, every paired delta
n.s. (s₇=.30−0: +0.44, p_w=.73); stranded flat (~15).

**Predictions:** monotone dose-response persists — poisoned(0.15) − 0 and
poisoned(0.30) − poisoned(0.15) both > 0 with p_w<.05 at 64 seeds
(poisoned at s₇=0 stays exactly 0 — test-pinned); output-flat persists —
every paired delivered delta n.s.

**KILLs (bidirectional):**
- Either dose-response step n.s. at 64 seeds → the v7 headline ("gauge
  error silently corrupts books") is downgraded to exploratory.
- A SIGNIFICANT delivered drop at 64 seeds → the "output-flat" clause is
  struck: the headline is rewritten as "output degrades too," which
  weakens the green-dashboard framing and must be stated wherever the
  paper uses it. Reported loudly either way.

---

## P2-R3 (column P2R3, 128 runs) — P23a bills headline + P23e dwell moral hazard, N=240

**Seed-count decision (registered before running, with the timing that
made it):** one N=240 bills+dwell run at HEAD takes **144.9 s**; 2
variants × 64 seeds = 128 runs ≈ 26–31 min wall at 12 workers → **64
seeds (0..63) IS compute-feasible and is registered**; the battery runs
in the background with logs under `results/`. The N=24 fallback is
explicitly NOT available: at N=24 the effect does not exist to re-pin
(Δdfrac −0.0026, p_w=.625, ceiling delivered_frac 0.998) — re-pinning
there would test nothing.

**Cells:** {snhp+net spot, snhp+net+bills} × N=240 (grid 101), preset
`v5`, σ=0.5, τ=0.15, 2500 ticks, lineage=True, dwell=True, seeds 0..63.
One grid serves both effects because the dwell instrument is a PINNED
pure instrument (`test_p23e_dwell_instrument_is_pure_bookkeeping`;
re-verified today: all 32 common P2-vs-P3 artifact rows bit-identical),
so these cells replicate the original sweep_v4_P2/P3 spot+flat
trajectories exactly.

**Originals (8 seeds, re-verified from sweep_v4_P2/P3.json today):**
- P23a: Δdelivered_frac **+0.0273** (p_t=.0010, p_w=.0078, 8/8); ≥2-hop
  delivered share **0.0252 → 0.4924** (Δ+0.467, p_w=.0078, 8/8);
  stranded 2.12 → 1.00 (Δ−1.12, p_w=.35, n.s. at 8 seeds); delivered
  +65.5 (p_w=.0078).
- P23e: flat − spot dwell inflation (all parcels) **+116.59**
  [+100.76, +132.41] ticks/parcel (p_t<.001, p_w=.0078, 8/8).

**Predictions:**
- **P2-R3a (P23a):** Δdelivered_frac > +0.01 (the original phase-2 kill
  threshold, retained as the bar) with p_w<.05; Δ(≥2-hop share) > +0.2
  with p_w<.05. Stranding REPORTED with direction (expected negative);
  it was a descriptive bonus at 8 seeds — if still n.s. at 64 it is
  formally downgraded to descriptive in the paper, stated now.
- **P2-R3b (P23e):** flat − spot dwell inflation > 0 with p_w<.05.

**KILLs (bidirectional):**
- Δdfrac ≤ +0.01 or n.s. → the P23a headline ("bills form the chains")
  is downgraded; a significant NEGATIVE is an active refutation —
  loudest report.
- Dwell inflation n.s. or negative → the moral-hazard headline dies, and
  P23e's contingent-split story loses its premise; reported as such.

**P23b (firm-arm) — NO re-pin, and why:** the firm arm's result is
BIT-IDENTITY to spot (trajectory equality, zero new chains) — a
mechanical property, not a statistical claim; seeds do not bear on it.
It is enforced in the suite and was re-verified in the artifact today
(firm rows equal spot rows cell-for-cell). Re-pinning it would burn ~5
hours of N=240 compute to re-measure an equality that a test already
pins.

---

## Run plan (committed with this registration)

- `run.py --column P2R1 --seeds 64` → 704 runs, artifact
  `results/sweep_v4_P2R1.json`, log `results/p2repin_P2R1.log`.
- `run.py --column P2R2 --seeds 64` → 192 runs, artifact
  `results/sweep_v4_P2R2.json`, log `results/p2repin_P2R2.log`.
- `run.py --column P2R3 --seeds 64` → 128 runs, artifact
  `results/sweep_v4_P2R3.json`, log `results/p2repin_P2R3.log`
  (background; ~30 min).
- Scoring: `run.py --analyze <artifact>` → the `repin_report`
  [P2-R1]/[P2-R2]/[P2-R3] sections — committed BEFORE the runs and
  validated pre-run: fed the 2026-07-15/16 committed artifacts they
  reproduce the original numbers above verbatim.
- Verdicts are appended to THIS file after the artifacts exist, never
  edited into the text above.

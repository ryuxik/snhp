# gametheory CHANGELOG

## 2026-05-02 — Hassabis experiment portfolio (5 experiments, $5.88 total)

After committing the homepage rewrite, ran a Hassabis-designed portfolio
to confirm or falsify the strongest claims at maximum information per
dollar. **Result: both hero claims survived empirical attack at p<0.001;
mechanism-design roadmap is dead.**

### Experiments + verdicts

**E1 — H3 fresh-seed replication ($0.69)**:
Tested whether the +12% head-to-head margin replicates on disjoint seeds
(2000-2019, no overlap with prior 20-seed set). Result: lift +0.150,
CI [+0.101, +0.200], sign 32/40, **p<0.0001**. T1 baseline was +0.121
with overlapping CI. **Headline +12% confirmed; could honestly bump to
+13-14%.** Saved → `e1_h3_replication.json`.

**E2 — H1 power-up at N=50 ($3.01)**:
Hassabis predicted N≈47 needed for p<0.01 confirmation of the +7%
cooperation premium. Ran N=50 paired self-play on seeds 2100-2149.
Result: lift +0.070, CI [+0.032, +0.110], sign 37/50, **p=0.00047**.
T1 baseline was +0.071 with sign-test borderline at p=0.058. **Same
magnitude, much tighter CI. The "borderline" footnote on the homepage
is removed.** Saved → `e2_h1_power_up.json`.

**E3 — Sim-only commit-reveal sweep ($0.00)**:
Three mechanism variants (V1 BATNA-revealed, V2 preference-revealed,
V3 staged BATNA reveal after round 3) tested in production-faithful sim.
All three tied at +0.081 sim Δ over current SNHP self-play (1.13 → 1.21).
Verdict: PROMOTE TO E4 LLM-loop validation. Saved → `e3_commit_reveal_sweep.json`.

**E4 — Oracle-reveal LLM-loop validation ($1.48)**:
Implemented `LLMMinimalSNHP_OracleReveal` subclass that overrides the
outcome picker to MAXIMIZE TRUE OPP UTILITY (oracle access to opp's
utility function — models the end-state of cryptographic commit-reveal).
N=20 paired (current vs oracle, self-play). **Result: lift −0.006, CI
[−0.054, +0.045], sign 6/20, p=0.98 (wrong direction).** Sim predicted
+0.081. Mechanism does NOT transfer to LLM loop. Verdict: ABANDON.
Saved → `e4_oracle_reveal.json`.

**E5 — Stuck-deal stratification ($0.00, re-mining existing data)**:
Hypothesized the "+12% population lift" might be a much larger "+18%
on negotiations that actually negotiate" if we filter out matchups
that close on the first offer. Result: influenceable-subset lift only
+0.139 vs population +0.118 (jump +0.021, well below Hassabis's +0.04
threshold). Verdict: NO HIDDEN EFFECT. Saved → `e5_stuck_deal_stratification.json`.

### Strategic implications

1. **Both hero claims are CI-validated at p<0.001.** The +12% H3 and
   +7% H1 are now defensible through replication and power-up. The
   homepage's earlier "borderline at N=20" footnote on H1 is replaced
   with "Confirmed at N=50: p=0.00047, CI [+3.2%, +11.0%]."

2. **Mechanism research is dead.** Sim-vs-LLM-loop divergence is now
   confirmed *empirically twice*: peer_cs (peer params) and oracle-reveal
   (outcome picker). Both showed strong sim signal that didn't transfer.
   **No more sim-only mechanism experiments without LLM-loop validation
   in the same trial.** Future commit-reveal work is shelved until we
   can afford in-LLM-loop iteration at scale (~$50+ per Optuna round).

3. **The 97% Pareto plateau is the product ceiling.** SNHP self-play
   already hits 97% of theoretical Pareto frontier. Remaining 3% headroom
   isn't unlockable via parameter tuning OR mechanism change at any
   horizon we tested. **Future gains come from distribution (more
   customers, larger N, network adoption), not from algorithm
   improvements.**

4. **$9.12 of $15 budget unspent.** Per Hassabis's "redirect to
   distribution" recommendation, this should fund customer outreach
   (cold-email Sierra/Decagon/Cresta CS Ops + AI Product leads) rather
   than more LLM experiments.

### What we deliberately did NOT do

Per Hassabis's portfolio design, we did NOT run:
- **Cross-vendor (Haiku) test** — Phase 2 question; spending now confounds
  "does it work?" with "does it work cross-vendor?" before core is
  reproducible. Resolved by E1+E2 confirmation; cross-vendor is now a
  cleaner future test.
- **Boulware/Conceder adversarial baselines** — research-paper material,
  not homepage material.
- **Horizon test at fixed n=13** — no current homepage claim depends on
  resolving the +13% vs +7% horizon mystery; defer until something forces
  the question.
- **H2_B re-test at N=238 (~$24)** — the resulting marketing claim is too
  weak to lead with even if confirmed. Demoted from homepage; spend $0.

---

## 2026-05-01 — Magic-number framework + Phase 1-2 tuning (in progress)

### Context

After the peer_cs reversion (entry below), an asymmetric N=20 LLM
experiment exposed a hardcoded `pareto_knob=0.5` in the LLM scaffold
that was costing single-side SNHP customers −0.034 utility (p=0.98
wrong direction) — the entire B2B "single customer benefit" claim
was broken. A one-line fix to `pareto_knob=1.0` (+ env override
`SNHP_PARETO_KNOB`) flipped the asymmetric SNHP-A lift to +0.075
(p=0.006). This made clear: **every magic number in the negotiation
code path is a hidden assumption that may be a bug.**

### What shipped

1. **`gametheory/negotiation/_config.py`**: single source of truth for
   all 33 tunable parameters in the negotiation advisor + LLM scaffold.
   Every parameter has metadata: `(default, rationale, source,
   search_range, importance, notes)`. Rationale categories:
   `theoretical | empirical | heuristic | magic-tunable`. Of the 33
   parameters, **20 were tagged `magic-tunable`** (no stated rationale
   before this audit).

2. **Env-var override mechanism**: every parameter is overridable via
   `SNHP_<UPPERCASE_NAME>`. Implemented in `_config.get_param(name)`.
   Out-of-range overrides clip; invalid values fall back to default
   with a warning. Documented in `/llms.txt`.

3. **`gametheory/negotiation/_peer.py` and `sell.py` rewired to use
   `get_param()`**: every magic constant (peer asp_floor / asp_start /
   signaling_rounds / max_self / descent_exp, adversarial concession
   exponent / Rubinstein discounts / opp_rv_estimate constants /
   schelling buffers / Bayesian filter parameters / accept-prob clamps
   / outcome ceiling) now reads from `_config`. Phase 1.2 originally
   missed this wiring; Phase 1.5 sensitivity exposed the omission
   (most params showed 0.0 sensitivity before the rewire).

4. **`gametheory/negotiation/_sim.py`**: production-faithful sim that
   calls the actual production functions (`peer_recommendation`,
   `sell_next_offer`, `buy_next_offer`) for advisor logic, and a
   pure-function port of `_pareto_outcome_at_util` for outcome
   selection. Avoids the structural divorce that killed peer_cs's
   no-LLM Optuna study (which used a re-implemented outcome picker
   that optimized a different objective than production).

5. **Sim validation gate**: validated against existing N=20 LLM trace
   data at both knob=0.5 baseline and knob=1.0 T1. All 5 rank-order
   checks PASS, including the critical "H2 SNHP-A flips negative→positive
   when knob goes 0.5→1.0" prediction. Absolute magnitudes differ
   (sim is more conservative on deal rates), but rank orderings hold.
   Sim is faithful enough for parameter ranking, not for absolute
   lift estimation.

6. **Phase 1.5 sensitivity analysis**: ±20% per parameter on each of
   the 9 high-importance params. Results:
   - `peer_asp_floor`: max impact 0.151 (5× larger than any other)
   - `outcome_picker_band`: 0.027
   - `peer_signaling_rounds`: 0.024
   - `asp_start_margin_max`: 0.017
   - `pareto_knob`: 0.015
   - 4 other high-importance params: <0.01 (effectively flat)

7. **Phase 1.6 Optuna study**: 100 trials, TPE sampler, train/test
   split (14/6 seeds). Top-5 params optimized over composite objective
   (H1 + H2_A + H2_B). Winner (trial #75) on TEST:
   - composite: +0.295 → +0.345 (+0.051)
   - H1 (ss−vv lift): +0.269 → +0.309 (+0.040)
   - All 3 validation gates PASS: Spearman ρ=0.661, gen_gap=0.006,
     test improvement +0.051.
   Winner params: `peer_asp_floor=0.462, outcome_picker_band=0.068,
   peer_signaling_rounds=3, asp_start_margin_max=0.929,
   pareto_knob=0.971`.

8. **Phase 2 (DONE — mixed result)**: N=20 LLM-loop validation of the
   tuned defaults vs T1 baseline. Validation gate technically PASSED (2
   metrics improved at p<0.10) but H1 cooperation premium **regressed
   from +0.071 to +0.009** while H2/H3 improved. Mixed signal — not a
   clean win.

9. **Phase 2.5 (DONE — decomposition test)**: re-run with ONLY the 3
   adversarial param changes, peer params reverted to defaults.
   Hypothesis: H1 recovers if peer params caused regression. Result:
   H1 partially recovered (+0.009 → +0.051) but didn't return to T1's
   +0.071. H2_A actually worsened (+0.075 → +0.023). Vanilla baselines
   drift across runs (LLM stochasticity), making clean attribution hard.

10. **DECISION: don't bake further changes. Stay at T1.** Reasons:
    - T1's `pareto_knob=1.0` fix is already validated and shipped
      (clean +0.109 H2_A flip from broken baseline).
    - Phase 2 + 2.5 results are within seed noise of T1.
    - Cross-run vanilla-baseline variance (mean SD 0.025 per seed,
      max 0.22 on seed 1600) tells us our N=20 deltas are partly noise.

11. **Hidden insights from cross-run analysis** (2026-05-01):
    - **15 of 20 seeds flip sign on SNHP-A lift across runs.** Cross-run
      Pearson r between same-seed lifts is +0.34 to +0.50 (weak/moderate).
      T1 vs Phase 2.5 correlation is **negative** (−0.21). Per-seed
      reproducibility is poor; only averaged metrics are meaningful.
    - **Power analysis at observed pooled SD**: H3 (effect/SD=0.79) needs
      N=19 for p<0.01 → at threshold. H2_A (0.66) needs N=27. H1 (0.50)
      needs N=47 — current N=20 is underpowered for the cooperation
      premium claim. H2_B (0.22) needs N=238.
    - **H4 (asymm joint welfare) is consistently negative** across all 4
      runs (−0.011 to −0.047). Single-side adoption destroys joint
      welfare on average; the "positive-sum" 138% capture rate from
      Analysis 2 applies only to SV (SNHP-seller × vanilla-buyer); VS
      side is purely extractive AND destructive.
    - **30-35% of asymm matchups are "stuck"** (vanilla counterpart's
      utility identical between vv and asymm — first-offer-accept).
      SNHP can only differentiate the remaining 65-70%; reported lifts
      averaged over the influenceable subset would be larger.
    - **Sim got peer-mode parameter directions WRONG** in LLM loop.
      `peer_asp_floor=0.46` was sim-best for H1; LLM-loop showed it
      hurt. Mark these params "sim-untrustworthy" — never tune them
      in sim alone.

12. **Homepage + docs revised** to reflect honest CI-validated numbers
    (T1): "+12.1% head-to-head margin (CI [+6.5%, +17.4%])" replaces
    the prior "+13% cooperation lift" headline. Methodology section
    surfaces the N=20 power limitations openly.

### Methodology lessons

### Methodology lessons

- **No more pure no-LLM tuning.** Sim must call production functions
  AND pass an LLM-loop validation gate. The peer_cs disaster (sim
  +0.297, LLM +0.032) cost a wasted Optuna run + several hours of
  framework rework. Architectural cost of getting it wrong is high.

- **Sensitivity analysis before Optuna.** Of 9 high-importance params,
  one (`peer_asp_floor`) accounted for >5× the impact of any other.
  Optuna without sensitivity is searching mostly-flat dimensions.

- **Train/test split is non-optional.** 14/6 split caught the gap
  metric. Optuna's training optimum (+0.339) was confirmed on held-out
  test (+0.345) — but the test set's composition matters. Different
  seed splits → different winners.

- **Magic numbers in shipping code are bugs.** Of the 33 parameters,
  20 had no stated rationale before this audit. One of those — the
  hardcoded `pareto_knob=0.5` — broke the entire single-customer B2B
  claim for an entire product cycle without anyone noticing because
  self-play measurements masked the asymmetric harm.

---

## 2026-05-01 — peer_cs variant: shipped, reverted, and what we learned

### Summary

Added a `peer_variant` parameter (`"b2b" | "cs"`) plumbed through the negotiation
HTTP/MCP API, intended to ship a short-horizon (≤6-round) variant of the PEER
playbook tuned for customer-service disputes (refunds, late deliveries, billing).
Both variants were validated end-to-end. **The CS variant did not earn its
complexity in the LLM tournament; reverted to a single PEER playbook.**

### Timeline

1. **Hypothesis**: at U(7,13) negotiation rounds (B2B contracts), peer_mode lifts
   joint welfare by +0.186 (n=20 LLM tournament, p=0.0004). At ≤6 rounds (CS),
   the same playbook stalls because cubic descent + 2 signaling rounds runs out
   the clock — agents still demand 0.84+ at deadline. So we built a CS variant.

2. **v1 (Optuna-tuned)**: built a no-LLM logrolling simulator with 200 stratified
   CS scenarios (ticket types × customer profiles × severities), 70/30 train/test
   split, TPE sampler over (asp_start, asp_floor, signaling_rounds, descent_exp,
   max_self_target, accept_tolerance). Winner had `asp_start=0.72,
   signaling_rounds=1, descent_exp=0.62`. Test-set lift over B2B-applied-to-CS:
   **+0.297, 95% CI [+0.279, +0.315], Wilcoxon p<1e-11.** All Hassabis gates
   passed except a spurious rank-correlation warning (top-10 train values
   spanned only 0.0014 — flat plateau).

3. **N=20 LLM validation at n_steps=6 with v1**: lift +0.032, 13/20 wins,
   **p=0.13 — not stat-sig.** Worse than B2B-defaults (+0.067 at the same
   horizon). The Optuna optimum failed to transfer.

4. **Diagnosis** (single-matchup trace + code review):
   - The simulator's `_pick_cooperative_outcome` chose the bundle that
     **maximized opponent utility subject to self-target** — lower target ⇒
     more opp surplus ⇒ higher joint. The production picker
     (`_pareto_outcome_at_util` in `llm_negotiator.py`) inverts this: it picks
     the bundle closest to the opponent's last offer in feature space, so
     **higher self-target produces higher joint welfare**. Sim and production
     were testing different algorithms. The sim was actively anti-informative.
   - `signaling_rounds=1` made signaling a one-cycle lottery: after one
     bilateral signal cycle, the advisor immediately dropped target to 0.64.
     The opponent's still-active signaling offer (0.92) was "way above target"
     → LLM accepts at sub-Pareto values (or sometimes catastrophically low
     values when weights were asymmetric: seed 800 lost −0.346).

5. **v2 (LLM-loop reasoned)**: ignored Optuna; treated peer_cs as a minimal
   horizon-aware fine-tune of B2B (`asp_start=0.92, signaling_rounds=2,
   descent_exp=2.0, asp_floor=0.50`). Trajectory at n=6: 0.95→0.95→0.78→0.50
   vs B2B's 0.95→0.95→0.85→0.55. Bilateral signaling preserved; descent
   slightly faster + lower floor.

6. **N=20 LLM validation at n_steps=6 with v2**: lift +0.073, 13/20 wins,
   **p=0.13 — also not stat-sig.** Marginal improvement over B2B (+0.005,
   well within seed noise SD 0.144).

7. **Decision**: **revert.** The variant doesn't beat B2B by anything outside
   noise floor at n=20. Architectural review independently flagged the variant
   as phantom polymorphism — two values masquerading as a strategy pattern,
   plumbed through 7 layers (HTTP request, handler, sell/buy signatures,
   `_peer_mode_recommendation`, MCP tool, LLM scaffold env-var, pydantic model).
   Net cleanup: −1,200 lines, single PEER playbook, single source of truth.

### What was reverted

- `peer_variant` parameter from all 7 layers
- `_PEER_CS_*` constants + `_peer_constants` dispatch in `gametheory/negotiation/sell.py`
- `_CS_VARIANT_HORIZON_THRESHOLD` + auto-selection in `snhp/llm_minimal_snhp.py`
- `gametheory/tests/test_peer_cs_variant.py` (11 tests)
- `snhp/peer_param_tuner.py` (no-LLM simulator — structurally divorced from production)
- `snhp/peer_cs_optuna.py` (Optuna study — built on the bad simulator)
- `snhp/peer_param_sensitivity.py` (third copy of the same harness)
- The methodology section in `gametheory/server/static/index.html`
- Sim JSON artifacts: `peer_cs_optuna.json`, `peer_param_sweep.json`,
  `round_count_sweep.json`, `cs_horizon_n20*.json` (broken-code outputs)

### What was preserved

- `gametheory/negotiation/_peer.py` — extracted shared cooperative recommendation
  helper. Both `sell.py` and `buy.py` import from it. Fixes the previous wrong
  dependency direction (buy importing private symbol from sell).
- The cleaner `acceptance_probability=0.5` neutral value in peer-mode (was a
  4-branch heuristic that misled LLM prompts at signaling phase 0.10).
- `gametheory/server/static/cs_n20_n_steps_6.json` — honest LLM data showing
  the CS-horizon collapse. Useful for future research framing.
- `snhp/cs_negotiation_dataset.py` — the synthetic CS scenario generator.
  Domain-realistic; potentially useful if a faithful (LLM-loop) simulator
  is built later.

### Lessons for future tuning work

1. **No-LLM simulators must call the production outcome picker.** Any sim that
   models negotiation outcomes via its own logic is a different algorithm than
   what production runs. Any wins it finds are at risk of structural
   non-transfer. Build the sim against `_pareto_outcome_at_util` (or whatever
   load-bearing helper exists) directly.
2. **Hassabis gates pass + LLM-tournament fails ⇒ the gate suite is incomplete.**
   The CS variant passed gen_gap, paired Wilcoxon (p<1e-11), CI-above-zero,
   deal-rate floor, and rank-correlation. None of those caught the simulator
   inversion. The missing gate was: "does this also win in a faithful production
   harness?" Optuna without an LLM-loop validation step is an extrapolation that
   can be confidently wrong.
3. **CS-horizon improvement is a mechanism question, not a parameter question.**
   ≤6-round games have fundamentally less time for bilateral signaling +
   descent. Future work should look at: cryptographic commit-reveal of
   reservation values, sealed first offers, multi-attribute bundling at
   negotiation start, or non-alternating-offer protocols. Parameter-tuning
   the existing protocol does not move the needle at n=6.

### Live N=20 numbers (preserved for honest framing)

| Variant config | n_steps | Mean lift | Wins | p-value |
|---|---|---|---|---|
| B2B-defaults | U(7,13) | **+0.186** | 18/20 | **0.0004** |
| B2B-defaults | 6 | +0.067 | 13/20 | 0.13 |
| peer_cs v1 (Optuna) | 6 | +0.032 | 13/20 | 0.13 |
| peer_cs v2 (B2B-struct) | 6 | +0.073 | 13/20 | 0.13 |

**Net change**: simpler codebase, honest claims, real research direction
identified.

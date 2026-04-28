# SNHP eval + tuning runbook

Pipelines for re-tuning SNHP and validating against the long-horizon
tournament. All scripts are pure NegMAS math — no LLM calls anywhere in
the path.

## Files

| File | Purpose | Compute budget |
|---|---|---|
| `long_horizon_variants.py` | 25-player × 100-round tournament with 5 hand-tuned SNHP variants | ~2 min |
| `snhp_match_aspiration.py` | Targeted hypothesis-test sweep against Aspiration | ~2 min |
| `buy_side_first_strike.py` | Sprint 2 acceptance — first-strike-as-hardline vs vanilla | ~30 s |
| `optuna_multi_objective.py` | NSGA-II re-tune at n=100 with extended opponent pool, 3 objectives | ~20–25 min for 40 trials |
| `pbt_self_play.py` | Population-based training scaffold (NSGA-II equivalent for parametric agents) | ~3 min for the demo config |
| `final_tournament.py` | Roll-up: detector + best Pareto operating points vs the full field | ~3 min |

## Recommended sequence for re-tuning

1. **Run Optuna NSGA-II at the target horizon.**
   ```
   ./venv/bin/python -m gametheory.evals.optuna_multi_objective \
     --n-trials 80 --n-rounds 100
   ```
   Writes three operating points to this directory: `optuna_pareto_avg.json`
   (max avg utility), `optuna_pareto_h2h.json` (max H2H wins), and
   `optuna_pareto_self.json` (max self-play joint surplus).

2. **(optional) Run PBT for finer-grained refinement around the Pareto.**
   ```
   ./venv/bin/python -m gametheory.evals.pbt_self_play \
     --pop 16 --gens 8 --n-rounds 80
   ```
   Writes `pbt_best.json`. For *parametric* agents, NSGA-II ≈ PBT — this
   step is mostly diagnostic. For neural-policy agents (future work) PBT
   genuinely differs.

3. **Run the final tournament to compare new params against the old ranking.**
   ```
   ./venv/bin/python -m gametheory.evals.final_tournament
   ```
   Loads all three Optuna operating points + the Aspiration detector and
   plays them against the 21-strategy long-horizon field.

## Aspiration detector

`gametheory/agents/aspiration_detector.py`. Subclass of `SNHPAgent` that
detects deterministic monotone concession (low first-difference variance
in opponent's offers) and switches to "hold out and accept late." This is
the structural fix for the SNHP-vs-Aspiration utility leak in the
long-horizon tournament. Default detector parameters are heuristic; the
multi-objective Optuna can be extended to tune them too (add the four
`_DET_*` thresholds to `_PARAM_SPACE`).

## Honest limitations

- **The Aspiration detector helps in the headline matchup but is mixed
  elsewhere.** Smoke test (n=100, 5 opponents, both directions): +0.050
  vs Aspiration buyer-side, +0.013 seller-side; +0.015 vs Anchorer
  buyer-side, +0.051 seller-side; mixed effects vs Cialdini, Logroller,
  The Closer (-0.04 to +0.01).
- **Multi-objective NSGA-II returns a frontier, not a single answer.**
  The operator picks an operating point per market segment (e.g., max
  avg-util for general use; max self-play for marketplaces with
  on-platform agents on both sides).
- **PBT for parametric agents has marginal value over NSGA-II.** The
  scaffold is here for future neural-policy work.

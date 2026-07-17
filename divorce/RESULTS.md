# Irreconcilable Agents — kill-harness results (steps 1+2)

**Date:** 2026-07-17 · **Status:** PILOT — all four kills SURVIVE; thresholds
await founder freeze (SPEC.md §11.1), then a confirmatory run on a fresh seed.

## Headline

| | seed 7 (N=100, tuning) | seed 11 (N=100, holdout) | kill bar |
|---|---|---|---|
| K1 ARM-I full-settle (w/ true IR) | 11.1% | 4.1% | must be < ARM-B − 5pp |
| K1 ARM-B settle | 76.4% | 82.2% | — |
| K2 decrees violating true IR | 0% | 0% | ≤ 10% |
| K2 median advantage (S_B−S_I)/S_O | 46% | 46% | ≥ 15% |
| K3 median S_B/S_O @ 10 Q/side | 85% | 90% | ≥ 80% |
| K4 median bluff gain | 0% | 0% | manipulation language banned if > 10% |

The two-act story is TRUE on this population: item-by-item lawyering (given
the same cash-equalization rights and its best reasonable protocol) almost
never fully settles — the deadlock concentrates exactly on the contested
spiked assets (dog/vinyl/wildcard) — while the mediated bundle settles ~4/5,
never ships a decree either side's true walk-away refuses, and recovers ~85-90%
of the oracle ceiling from ten questions a side. Intensity-bluffing the
elicitation gains nothing (the ratification step absorbs it). The NO DECREE
state is real (~24% mediator abstention) — the no-deal card will appear live.

Files: `results-kill-step1.json` (ARM-I/ARM-O only), `results-kill-step2.json`
(all arms, seed 7), `results-kill-holdout-seed11.json`. Reproduce:
`python3 -m divorce.kill_harness --n 100 --seed <s>`.

## What the build taught us (now part of the mediator design, SPEC.md §5)

1. **Never mix scales.** v1 had personas state a walk-away in TRUE-utility
   units while the mediator scored bundles on the ELICITED scale — 77% of
   decrees got refused. Personas now state structured declarations (spite
   weight λ, fight cost); the mediator derives the walk-away line on its own
   elicited scale. The IR margin reduces to `(1+λ)·Σ(share−0.5)·v̂ + fight`,
   where evenly-split assets cancel exactly — estimation error only enters
   weighted by |share − 0.5|.
2. **Median, not mean.** Per-asset posteriors are heavy-tailed (the prior
   covers hill/front multipliers); the posterior mean is tail-dominated and
   systematically overestimates. Point estimates are posterior medians.
3. **Dollar-scaled query policy.** preflearn's candidate pool and $0.15
   pairwise logistic width degenerate at $50k asset scale (posterior freeze +
   runaway truncation). The divorce policy: probes at three quantiles per
   asset + all-pairs "keep X or keep Y?" comparisons, tau scaled to the money.
   Same validated gain machinery underneath.
4. **Ratification is elicitation.** The mediator slides each draft across the
   table as a direct yes/no ("better than court for you? don't tell me why").
   A refusal is (a) a linear inequality on the refuser's values — ingested as
   a posterior update, preflearn's accept/reject pattern at asset scale — and
   (b) a hard exclusion of that allocation at that-or-worse compensation.
   ≤ 6 drafts, then the mediator ABSTAINS: no decree beats a decree a
   signature refuses. This one mechanism took decree rejections from 38% to 0
   and is the demo's best new beat ("Draft #2. Refused. Noted.").

## Honest caveats

- Protocol constants (query policy, taus, Q=10, drafts=6) were tuned against
  seed 7; seed 11 is a clean holdout and passed everything, but the
  post-freeze confirmatory run must use a fresh seed.
- EF-both under elicited settlements: 73% (seed 7) — the receipt's envy-free
  line will honestly read NO on a quarter of decrees. It is a reported check,
  never a guarantee (SPEC.md §6).
- Qualification: 72% of sampled pairs meet the ≥2-contested-@20% bar (mean 19
  resamples). The criterion is hard to construct; the sampler's shared-front
  mechanism is what makes it reachable. Distribution reported in the JSONs.
- K4 covers intensity-exaggeration (hill ×1.5) only — the registered bluff
  policy. No manipulation-resistance claims beyond it.
- LLM-free by design (SPEC.md §8.3): dialogue voicing is chrome, added later.

## Trap check — COMPLETE (2026-07-17): CONFOUND CONFIRMED

The registered LLM-fronted ARM-I replication (`trap_check.py`, Haiku 4.5,
20 qualified pairs, 503 decisions, $0.88 metered):

- **40 goodwill leaks (8.0% of decisions)** — accepts of offers clearly below
  the IR bound (below the rule's threshold by more than 3 noise sd; median
  severity **$4,505** below threshold). The recorded reasonings show
  arithmetic-adjacent rationalization: plausible-sounding accounting that
  double-counts fight-cost savings or drops the court expectation, then
  accepts. In the smoke run's cleanest specimen the model computed the offer
  was worse than litigation and accepted anyway.
- 30 clear over-tough rejections; 48 gray-zone disagreements.
- **The aggregate accept rates match EXACTLY** (16.5% LLM vs 16.5% rule) —
  the errors cancel in aggregate. You cannot audit an LLM negotiator by
  aggregate accept rate; only per-decision grading against the utility rule
  exposes the leaks. This is itself a notary-GTM datum.

Consequence (registered): acceptance must NEVER be delegated to the dialogue
layer, in harness or demo — the LLM-free acceptance rule is load-bearing,
not paranoia. Any future change letting the LLM decide acceptance is
invalid. Evidence: `results-trap-check.json` (per-decision records +
reasonings). Rerun: `python3 -m divorce.trap_check --pairs 20 --seed 7`.

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

## Where the ceiling gap lives (question-budget sweep, seed 7, 72 pairs)

| Q/side | settle rate | K3 median (incl. abstentions) | median among settled |
|---|---|---|---|
| 6 | 79% | 88% | 94% |
| 10 (demo) | 77% | 85% | 92% |
| 16 | 89% | 95% | 97% |
| 24 | **100%** | **99%** | 99% |

The ~10–15% gap at demo budgets is almost entirely **elicitation information,
purchasable with questions**: at 24 questions/side every pair settles at 99%
of the perfect-information ceiling. The mediator's conservatism converts
uncertainty into ABSTENTION (NO DECREE), never into bad deals — zero
walk-away violations at every budget — so as the posterior tightens,
abstention vanishes and capture approaches 100%. The mechanism is
near-lossless when informed; the demo's Q=10 is a watchability choice, not a
mechanism tax. (Tail note: even at Q=24 the 25th-percentile settled pair
captures 88% — the hardest profiles still leave real money.) Product-side
interviews (~5 minutes) should run 20+.

## Elicitation robustness: can humans actually answer these questions?

Founder critique (Jul 17): "is X worth $Y to you?" is introspection humans
can't do — stated dollar valuations are anchorable and constructed. Measured
response (40 pairs, Q=10):

| condition | settle | K3 median |
|---|---|---|
| A. probes+pairs, clean answers (status quo) | 77% | 82% |
| B. probes+pairs, dollar-probe answers 5× noisy | 72% | 77% |
| C. choices only — no cash questions at all | 51% | **35%** |

Verdict, both directions: (1) the machinery is robust to noisy-but-unbiased
probe answers (B); (2) you CANNOT simply delete cash questions — pure "A or
B?" comparisons are ordinal and leave absolute scale unidentified, and the
margin logic needs dollars (C craters). The resolution: **cash never appears
as the object of a question, only as an option inside a choice** — "the
espresso machine, or $800 more of the wallet?" / "if the settlement paid you
$X for the dog, take it?" — the identical inequality for the engine
(conjoint-style discrete choice), an answerable question for a human. Demo
clerk templates rephrased accordingly (display-only change).

**K3 under biased humans (the follow-up, same day):** with an anchoring +
acquiescence answer model (kappa=.30 toward the offered number on cash-for-
asset offers, .10 on cash riders inside package choices, 10% yes-drift,
1.5x comparison noise), 40 pairs, Q=10:

| interview | answerer | settle | K3 median |
|---|---|---|---|
| v1 (cash probes + pairs) | honest | 77% | 82% |
| v1 | biased humans | 64% | **57%** |
| v2 — every question a package choice, cash only as rider | biased humans | **100%** | **92%** |
| v2 | honest | 100% | 98% |

The all-choices pool (`elicit_v2`: cash-for-asset trades + plain pairs +
asset-vs-asset with an equalizing cash rider, one linear-choice update for
all of them) is not just human-robust — it beats v1's HONEST performance,
because sweetened comparisons bisect value DIFFERENCES (what allocation
actually needs) and anchor scale continuously. ADOPT v2 as the interview.
Migration queue (in order, so the demo never renders an unknown question
kind): (1) chrome template for "linear" questions, (2) honest linear
answerer as harness default, (3) re-run the kill suite on seeds 7/11/23
under v2 + regenerate the three preset traces — a post-freeze design change,
re-validated in full rather than grandfathered.

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

## v2 elicitation ADOPTED (post-freeze design change, fully revalidated)

The all-choices interview (elicit_v2) is now the default across harness,
API, and demo. Revalidation on all three seeds (N=100 each, frozen
thresholds): every kill survives with wider margins than v1 —

| seed | ARM-B settle | K2 adv | K3 | K4 |
|---|---|---|---|---|
| 7 | 98.6% (was 76%) | 67% | 92% | 0 |
| 11 | 93.2% | 58% | 93% | 0 |
| 23 | 92.8% | 63% | 90% | 0 |

Files: results-kill-v2-seed{7,11,23}.json. Preset traces regenerated (same
seeds, same story shapes); the chrome renders linear package choices through
the same clerk voice ("The espresso machine, or $1,714 more of the joint
wallet?"), verified live. v1 code paths retained (elicit, make_answerer_v1)
for reproducing pre-migration artifacts.

## /science experiments (E1–E3) — registered b7fb7ad, run same day, ALL KILLS SURVIVE

Population: qualified pairs w/ settled oracle across seeds 7/11/23 + FRESH
seed 31 (n=278 pair-evaluations; v2 elicitation). Files:
results-science-seed{7,11,23,31}.json, results-science.json (aggregate),
arena/web/divorce/science-data.json (page copy).

**E1 — calibrated abstention.** Selective risk (true walk-away violated |
decree certified) = **0.0 at every budget** (6/10/24 q/side; coverage 95% /
97% / 98%). At the shipped gate, 8 abstentions occurred and **0 were
recoverable** — no abstained pair had ANY outcome inside the mediator's own
final confident set that cleared both true walk-aways. The abstention is
information-limited caution, not miscalibrated pessimism. Both registered
kills (risk>2%; recoverable>15%) survive → the word "calibrated" is earned.

**E2 — budget curve + human robustness.** Capture medians 86% / 92% / 99.5%
at 6/10/24 questions. v2-under-biased-humans (93.5%) beats v1-under-honest
(90.2%) on the same pairs → "human-robust" survives its kill.

**E3 — pettiness tax population.** Median per-case spite counterfactual
**$36,703**; as the registered headline ratio (max-side tax / realized
surplus over litigation) the median is **59%** — spite's price is the same
order as everything the settlement achieves. Distribution: 6% of couples at
$0, p25 $15.2k, p75 $60.3k, max $158k. Seed-stable (1.42x < 3x bound →
single-number reporting permitted). Attribution: the counterfactual
typically reallocates ONE non-hill asset (median drift 1 ≤ 2 bound) — state
per-case framing with that caveat. Both kills survive.

Phrasing discipline for E3: the ratio compares the despiked re-run's joint-
value gain to the actual settlement's surplus over litigation — "the median
couple's spite costs 59% as much as everything their settlement achieves,"
not "59% of the pie is burned."

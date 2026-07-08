# The Arena as a research instrument

Koza's bar: an evolutionary system is judged by whether it *produces* something,
not by whether it looks alive. Every experiment here scores **off the selection
path** (its numbers never feed energy), runs headless on the deterministic
engine, and reports the honest read — negative results included, the way this
repo already reported the Monte-Carlo compute null.

```
python -m arena.science --absolute    # #1: does the population actually IMPROVE?
python -m arena.science --price        # the selection differential (replaces r=0.15)
python -m arena.science --neutral      # directional selection vs a drift null
python -m arena.science --decompose    # is fitness about negotiation or taxes?
python -m arena.science --assembly     # crossover ablation: building-block assembly time
python -m arena.science --speciation   # emergent reproductive isolation?
python -m arena.science --human         # evolved strategy vs raw recommender (PRICE)
python -m arena.science --bundle-human  # evolved LOGROLLING vs raw recommender (MULTI-ISSUE)
python -m arena.science --all
```

The arena competes on **both** axes. ~¼–⅔ of every generation's deals are
multi-issue (Contract Season is ⅔), and the multi-issue genes — the private
priority simplex `bundle_focus` and the evolvable ceiling `bundle_tactic` — feed
fitness and are under selection. `--bundle-human` is the headline: it measures
evolution on the logrolling axis SNHP is actually built for.

## What each answers

| Koza's demand | Experiment | The test |
|---|---|---|
| **#1 Movement ≠ progress** | `--absolute` | Score a sample of the live population against a **frozen reference panel** (8 archetypes + the raw recommender) on a **fixed held-out scenario set**, every k generations, over ≥2 seeds. Rising mean/max = real cumulative improvement. Flat = a Red Queen treadmill, reported as such. |
| **Replace the +0.15 headline** | `--price` | The Price-equation covariance `Cov(trait, relative fitness)` per gene, **selection-on vs the neutral null**, with standard errors across seeds. A gene is under real selection iff ON is significantly nonzero *and* separated from the null. |
| **Neutral baseline** | `--neutral` | Reproduction and death **decoupled from energy** (drift only). Directional test: does a tactic's income predict its share-change 2 gens later, under selection but not under drift? (Raw share *volatility* is misleading — balancing/frequency-dependent selection *lowers* it.) |
| **Fitness is about the task, not taxes** | `--decompose` | Fraction of per-generation fitness variance attributable to **negotiated surplus** vs **demographic terms** (tax / senescence / birth). A small surplus share means selection is on tax-dodging, not negotiation. |
| **Does crossover do real work?** | `--assembly` | Two parents each hold *half* of a known-good building block `(tactic, aggression, walk_margin)`. **Generations to reconstitute the full block** under negotiated crossover vs uniform vs blend. If negotiated doesn't beat uniform, the operator is dead weight — kept for the story, said so. |
| **Emergent speciation?** | `--speciation` | `P(courtship impasse | parent genetic distance)`. If impasse rises with distance, the negotiation operator grew **reproductive isolation** (incipient speciation). If flat, impasse is decorative fecundity cost. |
| **Human-competitive (price)** | `--human` | The evolved champion vs the **raw SNHP recommender** (knob 0.5, no evolved layer), both on the same held-out panel. If evolution beats the shipped recommender's own play, that clears Koza's human-competitiveness bar and is the strongest possible proof-point for the library. |
| **Human-competitive (multi-issue)** | `--bundle-human` | The evolved champion vs the raw recommender run with **default (uniform) priorities**, on a held-out **bundle** panel in **every era**, scored two ways: the champion's own surplus AND **frontier capture** (% of the achievable joint surplus a settled package captured, from `scenarios.bundle_frontier`). Own-surplus is dominated by evolution DISCOVERING differentiated priorities that logrolling then delivers — "tell the SNHP logroller what you value and it trades to get it"; frontier capture is the preference-normalized efficiency gain. Both reported, per era, so no single market is cherry-picked. |

## The system changes the review drove

- **Raised the price ceiling** (`genome.concession`): a heritable, evolvable
  concession *schedule* — a small function of `(time, opponent concession, era)`
  layered on top of the SNHP advisor that the fixed engine does **not**
  parameterize. Default-neutral (all-zero = the raw advisor), so it opens a
  discovery dimension without disturbing balance. This is what makes `--human`
  even possible: without it, agents can only tune a shell around a fixed
  near-optimal policy and nothing new *can* emerge.
- **Raised the multi-issue ceiling** (`genome.bundle_tactic` + engine
  `negotiate_bundle(cooperation=…)`): the logrolling analog. A heritable
  `(sharpness, cooperation, concession)` triple co-inheriting with `bundle_focus`
  as the B3 block. `sharpness` reshapes the priorities the agent declares to the
  logroller; `concession` shifts bundle accept-timing; `cooperation` dials the
  engine's joint-welfare tilt **on verified-peer deals only** — the multi-issue
  place attestation pays. The engine change that makes it expressible is a new
  first-class `cooperation ∈ [0,1]` parameter on `negotiate_bundle`, independent
  of `peer_mode`: 0 = adversarial Nash, 1 = joint-welfare-max clearing both
  BATNAs. Validated standalone (`bundle_validation --cooperation`, adversarial
  BATNAs, 400 contracts): cooperation lifts joint welfare **+1.2% / +2.0% /
  +2.4%** at 0.3 / 0.6 / 1.0, with the worse-off party flat to 0.6 then falling —
  confirming the shipped peer default of 0.6 is the lift/fairness knee.
- **Fixed credit assignment** (`credit.credit_block`): leave-one-block-out
  counterfactual credit. On each closed deal, replay it with one gene block reset
  to a neutral allele; the surplus delta is that block's **causal marginal
  contribution** — the un-confounded signal the courtship logroll bargains with,
  replacing the epistatically-confounded win-rate scorecard. ~1 extra negotiation
  per close (config-gated: `ARENA_CREDIT_COUNTERFACTUAL`).

## Live honesty (on the HUD, not just offline)

- **Strategic-softening light**: rising wealth + falling aggression + everyone
  closing is strategic *collapse* dressed as prosperity. The census emits a
  `softening` flag; the HUD shows "⚠ STRATEGIC SOFTENING" so rising energy can't
  lie to a viewer.
- **Selection-on-boldness**: the census carries `price_cov` = `Cov(boldness,
  income)`; the strategies panel shows whether the SNHP knob is under selection
  this generation or merely drifting — the honest number, not the fake
  era-optimum line (deleted).

## Results (stamped from the runs — reproducible on the deterministic engine)

**Price axis**
- **Human-competitive (cleared):** evolved champion **0.0695 vs raw 0.0547 = +27.1%**
  on a held-out sellers'-market panel (boulware, knob 0.63, evolved schedule
  `c=[-0.03, 0.40, 0.14, 0.24]`; best of 3 seeds). Evolution beats the shipped
  recommender's own play — Koza's human-competitiveness bar.
- **Price equation:** `pareto_knob` (ON −0.32 vs null −0.05) and `walk_margin`
  (ON −0.35 vs null −0.26) under real directed selection **downward** — lower
  boldness and less bluffing win; distorting the declared floor is punished.
- **Absolute fitness: FLAT** (Red Queen) — the population mean does not improve
  vs the frozen panel. The gains live in the tail, not the average.

**Multi-issue (logrolling) axis**
- **The priority gene is alive:** `bundle_sharpness` = Cov(priority
  specialization, income) **ON +0.65 vs null +0.43** (separated) — the market
  now rewards differentiated multi-issue priorities. Before this work,
  `bundle_focus` sat frozen near uniform; it is now under strong directed
  selection (entropy falls generation over generation).
- **Honesty is selected for, again:** `bt_sharpen` (declaration distortion) is
  selected **down**; `bt_coop` (peer cooperation) is **not** individually
  selected (it's mutualistic); `bt_concede` (accept-timing) mildly up.
- **Human-competitive — honest read: SNHP is at the ceiling.** On the
  preference-normalized metric (**frontier capture**) the RAW recommender holds
  **88%** and evolution reaches **85%** — evolution does **not** beat it. The
  eye-catching **+119% own-surplus** is a *preference-shape artifact*: because
  `bundle_focus` is heritable, evolution specializes its own preferences (champion
  `[0.92, 0.04, 0.04, 0.0]`) until the logroll trivially delivers the one issue it
  kept caring about — trivially-satisfiable preferences, jointly *less* efficient,
  not sharper bargaining. Reported as the artifact it is. Same lesson as price:
  you don't beat the shipped recommender by distorting its inputs.
- **The multi-issue payoff that IS real is JOINT and attestation-gated:** the
  new `cooperation` dial lifts **joint** welfare **+2.0%** at the shipped 0.6
  (validated, adversarial BATNAs), captured only when both sides cooperate —
  which is exactly why verified peers (staking) are the vehicle.

**Honest negatives (re-confirmed)**
- Negotiated crossover **9.0 gens** to assemble a split block vs **uniform 3.6**
  — does NOT beat uniform (dead weight; kept for the story, said so).
- Courtship impasse is independent of parent genetic distance — no speciation.
- Negotiated surplus is ~⅓ of fitness variance; the rest is demographic.

Run `python -m arena.science --all` to reproduce every number.

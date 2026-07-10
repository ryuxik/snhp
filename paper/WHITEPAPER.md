# When Does Negotiation Beat the Sticker?

## Brokered Nash Quoting is Robust to Seller Miscalibration and Buyer Misreporting

*SNHP Research — first draft, July 2026*
*Artifacts, seeds, and one-command reproductions for every table: github.com/ryuxik/snhp (`vend/`, `fashion/`)*

---

### Abstract

Posted prices are optimal for a committed seller who knows their demand curve (Riley & Zeckhauser, 1983). Real sellers do not know their demand curves: supermarket chains forgo an estimated $16M each through uniform mispricing (DellaVigna & Gentzkow, 2019). We introduce **brokered Nash quoting** — a neutral mechanism that computes a Nash bargaining outcome over bilateral disclosures at the moment of sale, with three structural components: an *event-consistent disagreement point* (the no-deal world is the buyer's actual best alternative, priced identically for both sides), *shadow-priced inventory* with regime-consistent demand learning, and a *transaction-scaled gain buffer*. In seeded, paired, pre-registered inventory simulations against profit-optimal posted baselines, the mechanism ties the sticker when the seller is perfectly calibrated — replicating the classical result — and earns significantly more under realistic miscalibration, with consumer surplus higher in every condition. Contrary to the classical finding that misreporting pays in bargaining (Crawford & Varian, 1979; Sobel, 1981) and to recent evidence that LLM negotiation agents are exploitable by default, a best-response search over misreporting strategies finds honesty at the buyer's optimum *without any verification*: the disagreement structure prices lies. A behavioral extension with reference-price memory and churn shows the mechanism retains a seller's entire repeat-customer base under price levels at which posted pricing measurably destroys it.

---

### 1. Introduction

Agent-mediated commerce is arriving ahead of its price mechanism. Payment and checkout rails for autonomous agents are shipping across the industry, yet the step where a price is *formed* remains either a posted constant or an unconstrained model-vs-model negotiation. Both defaults have documented failure modes. Posted prices inherit their setter's errors, which are large and persistent in the field (DellaVigna & Gentzkow, 2019). Unconstrained agent negotiation is worse: frontier language models negotiating solo lose measurable money to naive fixed strategies (our public leaderboard, §6.3; consistent with TERMS-Bench and NegotiationArena), autonomous LLM pricers drift toward collusive outcomes (Fish, Gonczarowski & Shorrer, 2024, rev. 2026), and agent-to-agent bargaining is exploitable by adversarial counterparties by default (*An Automated but Risky Game*, 2025).

This paper evaluates a third design: a **neutral broker** that receives private disclosures from both sides — the buyer's willingness-to-pay and outside option, the seller's inventory state and costs — and posts a take-it-or-leave-it quote computed as a Nash bargaining solution over the true joint frontier. The human experience is a computed price at checkout, never above the displayed list; the negotiation is invisible. We ask three questions:

1. **When does this beat the sticker?** Not always: we confirm a well-calibrated posted price is unbeatable in a stationary world, as theory demands. The mechanism's value concentrates precisely where sellers are miscalibrated — which, empirically, is everywhere.
2. **Can it be gamed?** The classical distortion literature says bargaining mechanisms reward misreporting. We find the opposite for this mechanism, and we locate the reason in the disagreement structure.
3. **Is it safe to deploy against human customers?** We extend the simulation with reference-price fairness (Kahneman, Knetsch & Thaler, 1986) and churn, and measure the mechanism's effect on customer-base survival under aggressive price ceilings.

Our contribution is a *mechanism with evidence*, not a benchmark of model behavior: every experiment is seeded, paired against its counterfactual, pre-registered in the repository before results were computed, and adversarially reviewed. Several headline effects shrank as we removed flaws that flattered the mechanism; we report the survivors.

### 2. The mechanism

**Setting.** A seller with finite, possibly perishable inventory and a posted list price per good (the *ceiling*: quotes never exceed it, type-enforced in the protocol). Buyers arrive with private multi-good valuations, diminishing marginal utility over quantity, and a real outside option (a competitor's posted prices plus a walk cost). A quote is a bundle: (good, quantity, unit price).

**Brokered Nash quoting.** On receiving a buyer disclosure, the broker:

1. **Computes the event-consistent disagreement point.** The no-deal world is one event — the buyer's actual best alternative. If their best alternative is buying from the seller's own list-price board, the buyer's threat point is that surplus *and the seller's threat point is that margin*: a buyer the seller already had earns the seller no concession. If their best alternative is the competitor, the buyer's threat point is that surplus and the seller's is *zero* — a marginal customer is found money, and deep quantity deals to recruit them are rational. Pricing both threat points off one consistent event is, empirically, the single most consequential design choice in the mechanism (§4.2).
2. **Shadow-prices the inventory.** Each quoted unit carries its opportunity cost: a unit expected to sell at list within the remaining horizon is worth list margin to keep (selling it discounted displaces that sale); only genuinely excess or expiring units are cheap to move. Expected demand is learned from the seller's *own realized history* under the mechanism (an exponentially weighted per-good level, day-shock posterior from observed arrivals) — not from a formula fitted to the pre-mechanism world, which we show self-invalidates (a Lucas critique in miniature, §4.1).
3. **Maximizes the Nash product** over the enumerated bundle space subject to both gains being non-negative, with a lexicographic joint-gain tiebreak at the boundary, and applies a **transaction-scaled buffer**: the seller's believed gain must exceed max($0.75, 15% of bundle list value). The buffer exists because believed gains carry forecast noise; without it, the mechanism leaks margin on near-zero-gain deals. Its calibration frontier is reported, not hidden (§4.1).

The quote is delivered with a mandatory receipt (the "why"), an auditable context hash (same state, same disclosure → same price — the anti-discrimination property as an artifact, not a promise), and a TTL inventory hold.

### 3. Experimental method

**World.** A vending machine: 7–8 goods, per-good list prices, unit costs, salvage values, shelf lives; hourly arrival and willingness-to-pay curves (lunch-peak structure); nightly restock to par; day-level demand shocks (mean-one lognormal); an office-tower weekly calendar; occasional perishable oversupply. A competitor ("bodega") posts its own prices derived from true demand, independent of the seller's board.

**Honest baselines.** The posted-price control is *profit*-optimal (not revenue-optimal) against the operator's demand estimate, and we additionally searched the ceiling's placement: a peak-crowd anchor outearns the arrival-weighted optimum, and a ×1.25 anchor outearns both — the naive "optimal" sticker undervalues the seller's local monopoly power. We report the mechanism against the *strongest* posted baseline found, and we flag that all such comparisons are only as strong as the baseline search. A resolving posted-dynamic arm (Gallego–van Ryzin-style bid-price decomposition with the same demand learner) is also reported.

**Information discipline.** Dynamic arms never receive the true demand parameters — only the operator's (noisy) estimate plus what a machine can observe: arrivals and its own sales. Seller miscalibration σ_cal scales lognormal error on the demand-level estimate that sets both the sticker and the arms' structural beliefs.

**Statistics.** Every arm faces the identical customer stream (seeded substreams keyed on arrival identity, never on policy actions). Effects are paired daily differences; because learner state and inventory carry across days, confidence intervals use 5-day block means. Hypotheses and expected signs were written down before each run; results that contradicted them are reported (several were the most informative findings).

#### 3.1 Rigor standards — why an independent reader should trust this

Simulation papers earn distrust honestly; here is what we did about it, item by item, each verifiable from the repository:

1. **Pre-registration in the artifact.** Hypotheses, expected signs, and experiment grids are written into committed design documents *before* results exist (`vend/DESIGN.md` §9b–9c and the dated sections of `vend/RESULTS.md`). Where a result contradicted the registration, the contradiction is the reported finding.
2. **Paired counterfactuals by construction, tested as a property.** Randomness derives from `blake2b(seed, domain-tag, identity)` substreams keyed on *who arrives when* — never on anything a policy did — so every arm faces byte-identical customers. This is not a convention but a unit test (`test_arrival_and_consumer_streams_are_policy_independent`), as is full-run determinism (two executions produce identical result dictionaries).
3. **Invariants live in types, not documentation.** A quote above list price is *unconstructible* (the constructor raises); a quote without its receipt is unconstructible; the quoting path has no buyer-identity parameter, and every quote carries a context hash making "same context + same disclosure → same price" auditable from artifacts alone. Tests pin each of these as behavior, not intention.
4. **Strongest-baseline discipline.** The posted-price control is profit-optimal, and when a ceiling search revealed our "optimal" sticker undervalued the seller's local monopoly power (+$21/day available by anchor placement alone), we adopted the stronger baseline and re-ran everything — the mechanism's reported edge is against the best sticker we could construct, and the search itself is in the record.
5. **Adversarial review with consequences.** A ten-angle independent review of this codebase surfaced 23 defects — including three simulation biases that all flattered the mechanism (an irrational consumer-acceptance rule, policy-coupled attacker identities, an inconsistent counterfactual) and one anti-conservative statistics choice. All were fixed and *every artifact regenerated*; the headline effect shrank at each step and the trajectory is preserved in `vend/RESULTS.md`, superseded numbers intact. A result that only survives its friendliest implementation is not a result.
6. **Information discipline in code.** World truth and operator knowledge are separate values in separate fields (`WTP_MU` vs `Listing.wtp_mu_est`); a policy that touches ground truth raises. Dynamic arms observe only what a physical machine could: arrivals and its own sales.
7. **Conservation and accounting tests.** Money and units are conserved across the ledger (consumer spend equals venue revenue; units vended never exceed units stocked); profit identities are pinned to rounding tolerance.
8. **Tuned parameters are disclosed as frontiers.** The gain buffer is a policy parameter; we report its full trade-off curve (perfect-calibration concession vs customer-pool protection), name the in-sample tuning cell, and validate on held-out seeds — rather than presenting one tuned point as discovered truth.
9. **One-command reproduction.** Every table regenerates from a fresh clone via the commands in Appendix A; committed JSON artifacts are byte-comparable against reruns and a regression test fails if the committed artifact drifts from what the code produces.

### 4. Results

#### 4.1 The miscalibration channel: tie at the knife edge, win everywhere real

Against the profit-optimal sticker at *perfect* calibration in a stationary world, the mechanism is a small, honest concession: **−$1.98/day [−2.70, −1.25]** with consumer surplus +$3.44/day (a flat $1 buffer achieves a statistical tie, −$0.72 [−1.43, −0.00], at the cost of the fairness protection in §4.3 — the full buffer frontier is documented). This *replicates Riley–Zeckhauser*: with commitment and known demand, posted pricing is optimal, and a mechanism that claimed otherwise here should be distrusted.

Under realistic conditions — ±30% demand-estimate error (conservative relative to field evidence), day shocks, calendar structure, oversupply events — the mechanism wins:

| condition (90 paired days) | profit Δ/day vs strongest sticker | consumer surplus Δ/day |
|---|---|---|
| seed A | **+$1.24** [0.23, 2.25] | +$9.67 |
| seed B | **+$1.27** [0.26, 2.27] | +$9.48 |

Per machine, per day, with intervals excluding zero on both seeds and consumer surplus higher in *every* cell we have run, including all losing ones. At the true optimal anchor (×1.25), best-vs-best: +$1.95 [−1.16, 5.05] and +$2.69 [1.21, 4.18], consumer surplus +$12.6–13.8/day. Posted-dynamic pricing, given the identical learner, captures roughly half the mechanism's edge or less: disclosure beats inference.

Two negative results shaped the mechanism and are part of the record. Naive bilateral Nash quoting (threat points without event consistency, no shadow pricing) *loses catastrophically* (−$23/day) by letting early bargain-hunters drain stock the lunch crowd would have bought at list. And with shadow prices computed from pre-mechanism demand formulas, the seller's ledger shows believed gains (+$548/run) while realized profit falls (−$329/run): the mechanism invalidates the forecast that prices it, and the fix is learning from the world the mechanism actually creates.

#### 4.2 Emergent robustness to misreporting

The distortion literature predicts misreporting pays in Nash bargaining. Recent agentic-commerce studies find exploitation is the default in LLM-vs-LLM negotiation. Our earlier mechanism versions agreed: with naive threat points, an understatement attack (disclose 0.55× willingness, claim a free outside option) monotonically transferred $6–23/day from seller to liars.

Under the final mechanism, the attack stops working — with **no verification of disclosures at all**. A best-response search (every buyer deviating; disclosed-willingness scaling from 0.55× to 1.5×, outside-option claims varied; paired 30-day runs):

| deviation | buyers' surplus vs honest, $/day (all buyers pooled) |
|---|---|
| understate ×0.55 + free-walk claim | −1.26 |
| understate ×0.8 | −0.76 |
| understate ×0.9 + free-walk | −0.11 |
| **honest** | **0 (reference)** |
| truthful + free-walk claim | +0.50 (≈ noise; seller-costly) |
| overstate ×1.15 – ×1.5 | −0.58 to −1.76 |

Honesty sits at the buyers' optimum. The reason is structural: understating your willingness collapses the broker's estimate of your board-purchase alternative, which *zeroes the seller's obligation to you* — the deals you deny yourself exceed the discounts you extract, and the scaled buffer removes the residual thin-gain region where anchoring used to profit. Verification (attested disclosure) is thereby repositioned from a security requirement to a *discount tier*: the seller can afford a lower buffer for verified counterparties, so verification becomes something buyers want. We claim *approximate, empirical* incentive-compatibility within the tested deviation class; adaptive state-dependent deviations, collusion, and a formal proposition over a restricted deviation class are work in progress (§7).

#### 4.3 The fairness layer: what is safely harvestable

The ×1.25 anchor result poses an obvious danger: it prices captive surplus, and real customers punish that (dual entitlement; surveillance-pricing scrutiny). We extended the world with persistent repeat customers carrying per-good reference prices (EWMA of prices paid; weaker update from prices observed), loss-averse transaction utility (2× above reference, 0.5× below, a small framing bonus for visible discounts off list), sticker shock, dissatisfaction with forgiveness and symmetric relief, permanent churn, and exogenous pool replenishment.

At the ×1.25 ceiling over 90 days (120 regulars): posted pricing earns the most short-run ($142/day late-window) while churning 81 regulars and *net-shrinking* its pool despite replenishment — survivor-bias whales and memory-free transients flatter its trajectory. The brokered mechanism earns $134/day late-window — **+$33/day above the pre-anchor world** — while ending with its regular pool *fully intact* (120/120 active; churn healed by below-reference deals and replaced by inflow). The protective channel is the one hypothesized: quotes fire widely for small baskets (the scaled buffer matters), the paid price stays near reference, and in a scan-first interface the customer's salient price is their quote, not the board. On any horizon longer than the window, or any customer-lifetime accounting, the mechanism's harvest dominates. We emphasize the behavioral parameters are literature-anchored but not fitted to human data; §7.

#### 4.4 Pricing the mental-model switch

Moving a population from "prices are fixed" to "prices are computed" has a cognitive cost — evaluating a quote is harder than recognizing a known price — and an adoption analysis that ignores it flatters the mechanism. We price it directly: a dollar-equivalent friction per negotiated transaction, charged in full to first-time buyers and decaying with habituation (0.85 per exposure) for repeat customers; a quote must now beat the buyer's alternatives by *more than the hassle*. The dose-response at the realistic-miscalibration cell (90 days, mixed regular/transient population):

| friction per quoted transaction | mechanism's profit edge | consumer surplus edge |
|---|---|---|
| $0.00 | +0.79 [−0.21, 1.78] | +$9.64/day |
| $0.25 | +0.79 [−0.21, 1.78] | +$9.64/day |
| $0.50 | +0.79 [−0.21, 1.78] | +$9.64/day |
| $1.00 | +0.39 [−0.53, 1.31] | +$8.78/day |

The edge is friction-tolerant for a structural reason, not a fortunate one: the seller-side gain buffer already restricts the mechanism to deals meaningfully better than the buyer's alternative, so the surplus margin that protects the seller from forecast noise *also* absorbs the buyer's switch cost. Friction below the buffer scale is invisible; at $1 per transaction — a heavy estimate for tapping "accept" on a pre-computed price — the edge softens but persists, and habituation erodes the cost for anyone who returns.

#### 4.5 Supporting results

**Fashion markdowns.** A season simulation (one buy, no restock, style×size cells, strategic waiting consumers) finds weekly computed markdowns beat the industry's fixed markdown calendar in all nine tested cells (+9–21% gross margin/season), consistent with field results (Caro & Gallien, 2012); we treat this as a replication anchoring the simulator's realism, not a contribution.

**LLM negotiation context.** On our public dollar-scored leaderboard (held-out scenario seeds), frontier LLMs negotiating solo score below a naive split-the-difference baseline; advised by the engine ("LLM talks, engine decides") they approach the frontier. The mechanism in this paper removes the LLM from price formation entirely.

### 5. Related work

Posted-price optimality and haggling (Riley & Zeckhauser, 1983); bilateral trade impossibility and approximation (Myerson & Satterthwaite, 1983; fixed-price DSIC mechanisms, arXiv:1711.08057; optimal mediation, arXiv:2410.11683). Distortion in bargaining (Crawford & Varian, 1979; Sobel, 1981). Uniform pricing evidence (DellaVigna & Gentzkow, QJE 2019). Revenue management with strategic consumers (Gallego & van Ryzin, 1994; Aviv & Pazgal, 2008; Cachon & Swinney, 2009); negotiation with inventories (Kuo, Ahn & Aydın). Algorithmic pricing and collusion (Calvano et al., 2020; Fish et al., arXiv:2404.00806). LLM agent economies and benchmarks (Vending-Bench, arXiv:2502.15840; Anthropic Project Vend 1–2; Magentic Marketplace, arXiv:2510.25779; CoffeeBench, arXiv:2606.16613; TERMS-Bench, arXiv:2605.13909; *An Automated but Risky Game*, arXiv:2506.00073). CoffeeBench is closest in setting — a shop economy comparing negotiation against posted mechanisms — but benchmarks LLM *behavior*; we evaluate a *mechanism* against optimal-posted baselines with pre-registration and a misreporting battery. Behavioral pricing fairness (Kahneman, Knetsch & Thaler, 1986; dual-entitlement meta-analysis; FTC surveillance-pricing study, 2025).

### 6. Limitations

Synthetic demand (lognormal WTP, Poisson arrivals) in one catalog family; the calibration-to-field step (public vending transaction corpora; a physical pilot) is planned but not done. The switch-cost friction and its habituation rate are assumptions bounded by sweep, not estimates from human behavior. The strongest-sticker baseline is the strongest *we found* — baseline search is itself an optimization we may have under-run. The buffer is a tuned policy parameter with a documented frontier; its in-sample tuning cell is disclosed. The IC result is empirical and best-response-within-class, not a theorem; adaptive and colluding deviations are untested. Fairness parameters are literature-anchored, not estimated; the quote-salience channel is a design hypothesis a human-subjects study must test. All results are single-venue; multi-venue competition (both sides running brokers) is future work.

### 7. Future work

A formal proposition (liar surplus ≤ honest surplus under monotone understatement with outside-option inflation, given the discount-only ceiling and scaled buffer); calibration to public vending and retail transaction data; ≥10-seed-family robustness grids with power analysis; adaptive attack search; the two-sided case (buyer brokers vs seller brokers, and whether neutrality is an equilibrium); a human-subjects test of quote salience; and a composed multi-venue economy ("the Block") where the competitor is endogenous and community-level effects — customer-base survival, waste, queue health — are first-class outcomes.

### Appendix A: Reproduction

Every table regenerates from the repository root (`pip install -e .`):

```
# §4.1 control + frontier          python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr,a2a
# §4.1 miscalibration grid         python3 -m vend.run --grid --days 30 --seed 20260713 --arms static,gvr,a2a
# §4.1 90-day confirmatory         python3 -m vend.run --days 90 --seed {20260713,7} --arms static,a2a \
#                                    --sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow --glut 0.15 --out /tmp/c.json
# §4.2 attack battery              vend/scenario.strategic_disclosure sweep (see RESULTS.md)
# §4.3 fairness                    WorldConfig(regulars=120, anchor_peak=True, anchor_mult=1.25), 90 days
# §4.4 fashion                     python3 -m fashion.run --grid
```

Committed artifacts: `vend/results.json`, `vend/grid.json`, `vend/liar-sweep.json`, `fashion/results.json`. The adversarial review log and every superseded result remain in `vend/RESULTS.md` — including the versions of this mechanism that lost.

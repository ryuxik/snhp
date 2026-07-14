# Adversarial review — v0 benchmark (verdict: headline claims do not survive)

*Hostile line-by-line review agent, 2026-07-14. Method: code audit, bit-exact
reproduction of the 88-run sweep (0 mismatches), plus five NEW control
experiments run in scratchpad. Companion to STANDARDS_BRIEF.md.*

**Verdict:** code is clean, deterministic, conservation-checked, reproducible.
The three headline claims as stated are dead: claim 1 rides a gameable metric
and fails its own pre-registration; claim 2 is vacuous; claim 3's ladder has a
null arm at the bottom and a non-significant top rung. A real, narrower result
survives (see end).

## FATAL

### F1. The efficiency metric rewards killing the swarm

`efficiency = delivered / (initial + charged)` lets the denominator collapse
when robots die or go idle (dead robots stop drawing charge; non-finishing
rules/auction runs pump the charger all 2500 ticks → denominator ~21.3k).
Killer counterexample **σ=0.5 seed 2**: snhp strands ALL 24 robots, delivers
99 vs auction's 104 (auction delivers MORE, keeps 18 more robots alive), yet
scores 2.80 vs 0.48 — total annihilation booked as a 5.8× win. The σ=0
efficiency "win" is purely censoring + 10 dead robots at zero heterogeneity
(delivered ties there, p=0.85). Under the salvage-corrected net_efficiency,
"p<0.05 everywhere" was already false on the n=8 artifact (p=0.142 at σ=0).
**Fix:** primary metric = delivered at fixed horizon with strandings priced
explicitly; meter charger energy only until last delivery.

### F2. A trivial cooperative control DOMINATES the snhp arm

Reviewer-built **greedy joint-Φ "team" arm** (same Φ, same 98-bundle space,
same virtual physics — but just executes argmax(Φa+Φb); no Pareto, no Nash, no
individual rationality): beats snhp on EVERY metric at EVERY σ tested. At
σ=1.0: team delivers 118.5 vs snhp 99.9 (p=0.013) with 4.0 stranded vs 12.0.
Even single-issue **team[energy]** ties snhp on delivered (107.2, p=0.45) with
5 stranded. So the system value is Φ-informed energy movement, which a
selfless rule harvests better — in the COOPERATIVE setting the trivial
mechanism wins, and the benchmark's own kill-condition answer is "not worth
occupying — unless robots are self-interested." The defensible claim is
conditional on an individual-rationality (IR) constraint (mixed-ownership
robots), and the IR price is ~19 delivered units + ~8 robots/run — currently
unreported.

### F3. Claim 2 is vacuous: single-issue selfish bargaining strikes ZERO deals

`snhp[cargo]`: 0 deals in all seeds (verified 3 ways). Energy-only: also 0
deals, numerically identical — both are the same NULL arm (bare movement, no
trophallaxis). Structural reason: with selfish Φ, no single-issue transfer can
make both sides strictly better off. So "cargo-only ties the auction" reads
"a mechanism that does nothing ties the auction on a broken ratio metric" —
on delivered, the null arm is significantly WORSE than the auction (66.5 vs
73.1, p=0.003). **Silver lining (the better claim):** single-issue selfish
trade is provably inert here; 100% of executed deals are multi-issue —
bundling is NECESSARY for any IR trade. State it as necessity, not "+0.35
efficiency."

## MAJOR

- **M1. σ is a poverty dial, not a heterogeneity dial.** One-sided draws:
  swarm energy falls 2400→1450 (−40%) and mean step cost rises 1.00→1.26 as
  σ→1. Every "as heterogeneity rises" statement conflates variance with
  scarcity. Fix: mean-preserving spreads, re-run.
- **M2. Pre-registration failed.** WIN required monotone σ-trend (observed:
  peak at 0.5) and monotone issue count (top rung p=0.78, its 0.68 mean is one
  outlier seed — median 0.40). Honest status: PARTIAL at best. Δdelivered IS
  monotone (+0.4/+17.1/+26.8) — another reason to re-headline on delivered.
- **M3. Auction baseline weaker than its lineage.** Bilateral single-bidder
  0.9-threshold handoff — no broadcast, no multi-bidder competition; denied
  the sector issue though sector IS a task in MRTA terms. "Same brain" claim
  misleading (rules/auction never consume Φ). The honest strong baseline is
  Φ-informed single-issue (≈ team[energy]) — which BEATS snhp on delivered.
- **M4. Strandings flip the result and are confounded.** At "delivered −
  k·strandings," significance dies at k=2, sign flips at k≈5 — if a robot is
  worth >5 cargo units the headline inverts. Attribution confound: the null
  arm strands 13.1, so most of snhp's excess stranding comes from REMOVING
  trophallaxis, not from bargaining (snhp = two changes at once).
- **M5. Stats fragile at the advertised boundary.** n=8, skewed by
  denominator-collapse seeds (mean 0.735 vs median 0.448), no multiple-
  comparison correction, makespan right-censored in 23/24 runs at σ≥0.5
  (t-test meaningless), pre-registered Gini metric never implemented. Robust:
  Wilcoxon 8/8 at σ≥0.5; delivered at σ=1.0 p=0.003.
- **M6. The economy is stranding-rescue churn, not steady-state logrolling.**
  ~60% energy-for-sector, ~33% cargo-for-energy; 64% of deals involve an
  already-stranded party; the ±15 P_STRAND jump dominates traded surplus;
  robots cycle strand→sell rights→rescued→re-strand, burning 25% loss each
  hop. The open theory question (when do logrolling gains exist between
  healthy workers) is NOT answered by this economy.

## MINOR (abridged)

1. Provenance: results generated by older run.py; directory untracked — commit
   code, regenerate artifacts, pin SPEC hash before results.
2. `_virtual` models receiver rescue but not donor stranding → evaluated ≠
   executed (0–3 donor-strandings-at-deal/run); tests never assert
   virtual==executed (current surplus test is circular).
3. Spec/impl mismatches: strand-at-5 vs spec's 0; "one negotiation per robot
   per tick" only enforced on SUCCESS; ATTEMPT_COOLDOWN undocumented; auction
   moves up to 5 units vs snhp cap 4.
4. Sector swaps physically free (flag) vs real movement-rights cost; robots
   flip sector up to 13×/run; Φ future-term ignores distance-to-source and
   cross-mining → artificial swap gains.
5. Φ crudeness is NOT a live attack: sensitivity runs show headline stable for
   P_STRAND ∈ {5,40}, FUTURE_DISCOUNT=1.0 — cite this.
6. Scope label: full information + Φ reads global state (w.stock, N) →
   "multi-robot mechanism benchmark," not "swarm"/"neighbor-local."
7. TXN_COST is virtual — never physically debited.
8. Baseline exchanges invisible in sweep artifact (deals=0 for rules/auction;
   actual: auction fires 62–77×, trophallaxis ~580×/run). [event_log now
   exists for viz; metrics should log too.]

## What survives

- **Delivered at σ=1.0: +37% for snhp vs auction, 8/8 seeds, p=0.003,
  monotone in σ, lowest lost-cargo of any arm** — cargo rescue via deals
  genuinely works.
- **Value-targeting is real:** naive equalize-on-encounter redistribution
  catastrophically backfires (0.19 eff — lossy sloshing); threshold gifts
  don't close the gap. The energy movement must be value-informed.
- **Bundling is necessary for IR trade** (F3) — the cleanest claim available.

## The honest repositioning

*"For self-interested robots under individual rationality, single-issue trade
is impossible; multi-issue bundling (mostly energy-for-X rescue trades)
recovers most — not all — of the cooperative optimum, at a quantified price of
selfishness (~19 delivered units and ~8 robots per run vs greedy joint-Φ)."*

Requirements: delivered-at-horizon primary + strandings costed; mean-preserving
σ; Φ-informed single-issue baseline; team arm as cooperative ceiling; Wilcoxon/
permutation tests; "multi-robot," not "swarm."

**Falsification experiments already run by this review:** greedy joint-Φ team
arm (dominates snhp); energy-only ablation (0 deals); σ=0.5 seed 2 autopsy
(metric counterexample). **Not yet run:** mean-preserving σ re-sweep — first
thing a referee will demand.

# Results — verdicts against the pre-registrations

## ⚠ CORRECTION 2 (2026-07-15, evening): physics revision v8 — founder-spotted, everything re-run

The founder watched the live replay and caught what 22 review agents missed:
(1) **the pad-strand cargo trap** — a robot arriving at its target refinery
could strand on the arrival step and hold its cargo forever (audit: ~9–15
ore/run entered the trap in EVERY arm; rescue-capable arms ransomed it back
at 94–100%, auction/rules at ~64% — **a differential subsidy to our own
mechanism worth ~40% of the bargaining-vs-auction gap**); (2) **deals were
temporally free** — robots kept driving mid-exchange (the "tethering" the
founder saw). Fixes: the pad unloads on arrival (facility-side, same tick);
every executed exchange now immobilizes both parties DEAL_PAUSE=3 ticks.
Third finding, from the founder's lost-drone question: the scoreboard priced
a dead drone at k=0 while the agents priced it at 1.5 ore internally — the
k=2/k=5 flip analysis was pre-registered (SPEC §Metrics) and emitted in
every row but never reported. It is now first-class below. ALL columns
re-run on corrected physics (A–F + new G/H). Verdict shifts, honestly:

- **DIED — "risk pricing beats the safety net when risk is heterogeneous"
  (v3 regime law).** On its home v3 world under honest physics: hz never
  significantly beats net at any σ (best +3.6, p=.17), strands 15–21 vs the
  net's 2–7, k5 gaps −56 to −86. The old crossing was substantially the
  cargo-ransom subsidy. Column H (below) shows the gap is institutional,
  not a pricing bug.
- **DIED — "cooperation is 43% faster."** The joint tier strikes ~1,100
  deals/run; once deals cost time its speed edge is ~9% n.s. **The
  dividend moved to survival: gated fleets end 1.06 stranded vs the veto
  tier's 15.31 (k5: 235 vs 162).** Cooperation keeps drones alive; speed
  was an artifact of free transaction time.
- **SHRANK, SURVIVES — bargaining beats auction.** v5 anchor: snhp-hz
  +3.4 (p=.005, was +9.6; ~40% of the old gap was the pad subsidy);
  positive at every noise level (+0.8..+4.1, p≤.024). v4 preset: snhp
  +14.1 (p<.001). **On k-scores only the safety-net arm survives:**
  snhp+net vs auction +4.5 delivered AND +20.4 k5 (both sig) — the
  -hz arm reverses at any k>0 (its edge ≈ the drone capital it burns).
- **SURVIVES INTACT:** bundling necessity (structural, test-pinned); the
  toll-booth result (posted-price revenue 72.1 → 26.8 at τ*=0.15 vs
  bargaining fleets, **−63%**); border ≈ merger (team 118.6 vs twofirm
  117.6, n.s.); the v6 feeding frenzy (+179/+126, p<1e-4, strip 271–326)
  and the attestation gate (liar advantage → +9.5/−2.2 n.s., strip 0.0
  exactly); v7's corrected headline (delivered flat, poisoned 0 → 13.2 →
  23.4/run, self-margin halves it).
- **RE-SCOPED — "safety net beats the hive."** On the harsh v3 world it
  survives corrected physics (+2.1 delivered p=.041 at σ=0, HALF the
  strandings — 2.3 vs 3.9 — and +9.9 k5 p=.006). On richer v4/v5 stages
  the hive wins at every k. The law: the safety-netted market beats
  central planning when SURVIVAL is the binding constraint; the hive wins
  when logistics are.

Reproduce: `run.py --column <A..H>` then `--analyze`. Full k-table policy:
every headline is now reported at k ∈ {0, 2, 5} (delivered − k·stranded);
"agents price a drone at 1.5 ore internally; verdicts must survive k=2."

## v8 (column G): field geometry — the market needs meeting density

Founder's pre-registered theory (SPEC P13): dense fields favor auction,
sparse fields favor bargaining. **Verdict: KILLED as stated — the truth is
a hump.** snhp+net − auction delivered: +4.1 (G=24) → +4.5 (32) → **+7.3
(48)** → **−2.7 (64)**. Bargaining's edge GROWS with sparsity while the
logistics thicken (the mechanism intuition was right mid-range) and then
collapses when encounters themselves become scarce — at G=64 every
coordination arm craters (net strands 17.9, hz 22.1, even team 19.2) while
auction's direct hauling degrades most gracefully (235 → 231 across the
whole range). P13b mechanism check: the deal MIX does not shift (energy
share ~95% at both extremes); deal VOLUME rises (65 → 152/run). P13c:
k-scores agree (net k5 dominates through G=48, loses at G=64). The honest
law: **a market's advantage is hump-shaped in logistics complexity — it
needs enough friction to be worth paying for and enough meeting density to
physically convene.**

## v9 (column H): endogenous drone valuation — the KILL fired, informatively

Founder's pre-registered theory (SPEC P14): the flat 1.5-ore stranding
price is the bug; price drones at their remaining career. **Verdict: the
pre-registered KILL fired — the safety net's edge is institutional, not a
pricing artifact.** Pure career pricing (snhp-lv) is WORSE than flat
(delivered −16.5 p=.023, stranded +7.3 p=.001: the price decays with the
field, so late-game drones become disposable). Career + capital floor
(snhp-lvc, 2 ore) is the best pure-market arm ever recorded — delivered
ties the net (239.6), **fastest selfish makespan in the project (688)**,
beats flat-hz at every k — but still loses to the net by −36 k5 (p=.001).
Better prices make the market FASTER; they cannot buy the net's survival
record. Three attempts to replace the net with a smarter market (v3
hazard, v6 defenses, v9 career pricing) have now died on pre-registered
criteria.

A 22-agent pre-merge review found the original v7 headline was an artifact:
a **charger livelock** (the queue-release threshold read BELIEVED battery
while physics caps at TRUE max, so every robot with gauge bias < −0.05
parked at a charger forever — reproduced 3×), plus a second unintended
channel (update_ev perturbed the true axis, scaling the shadow price by
(1+bias)). The trust-gated arm's untrusted tier also ran LIE-FREE on true
books, so v6.1's −22.8 measured pure access denial. All fixed (charger
meter undocks at true-full; EV perturbs the believed reading; the untrusted
tier now runs the full defended Nash tier; one shared audited deal schema),
regression-pinned in test_swarm.py, and columns D/E/F re-run. Old numbers
are struck below; the corrected story is BETTER for the thesis, not worse.
Reproduce: `run.py --column D|E|F` then `run.py --analyze <sweep.json>`.

## v7: noisy self-knowledge (sweep_v7_F.json, 160 runs) — the fleet survives; the receipts don't

Superseded (livelock-confounded): ~~delivered 238.9 → 193.3 → 128.2~~.

- **P12a REVERSED by the fix:** gauge miscalibration does NOT devastate
  the fleet — delivered 238.9 → 239.8 → 229.5 (n.s., variance-driven) as
  gauge σ goes 0 → 0.15 → 0.30 (f=0). The original collapse was parked
  robots, not bad economics. Output is robust to self-knowledge error.
- **P12b PASS, now the headline:** poisoned deals — executed with negative
  TRUE surplus for an honest robot at the veto tier, impossible at s₇=0
  (pinned by test_v7_poisoned_zero_without_gauge_noise; scoped to veto
  arms — joint-pick arms execute one-sided losses BY DESIGN) — rise
  0 → 14.6 → 24.6 per run. **The system dashboard stays green (delivered
  ~flat) while individual books quietly bleed**: the v6 "green dashboard,
  robbed books" pattern, this time from self-ignorance instead of malice.
  The veto is only as good as the gauge reading the receipt.
- **P12c PARTIAL (bar unchanged, honest miss):** the inward self-margin
  halves poisoning (24.6 → 13.6 at s₇=0.3; 14.6 → 7.9 at 0.15) — short of
  the pre-registered ≥70% — at ~30% fewer deals. A price-of-safety dial,
  not a fix; the rest of the problem is state estimation.
- **Emergent echo survives the fix:** liar pickiness still protects
  against self-noise (poisoned 24.6 → 8.9 at s₇=0.3 when f=0.5) —
  inflated BATNAs remain involuntary safety margins.
- **Threat ranking, corrected:** partner-deception and partner-noise cost
  output; self-knowledge error costs TRUTHFULNESS-OF-BOOKS at flat output.
  The scary failure isn't a crash — it's an audit hole. Know thyself.

## v6.1: attestation gates cooperation (sweep_v6_E.json, 80 runs) — THE THESIS LANDS

Re-run 2026-07-15 with the untrusted tier fixed to be the FULL defended
Nash tier (lies active + distrust tax) — the original ran it lie-free, so
the old ~~−22.8~~ measured access denial, not relegation. Attribution
(strip vs sacrifice) is now built into the shared deal schema, superseding
the separate sweep_v6_E2.json artifact.

| condition | f | delivered | makespan | strip/run | liar adv |
|---|---|---|---|---|---|
| trust-open | 0.25 | 239.6 | 992 | 361.0 | **+181.1 (p<0.0001)** |
| trust-open | 0.50 | 238.9 | 1150 | 478.7 | **+137.6 (p<0.0001)** |
| trust-gated | 0.00 | 240.0 | 749 | 0.0 | — |
| trust-gated | 0.25 | 239.8 | 685 | 0.0 | +1.8 (p=0.98, n.s.) |
| trust-gated | 0.50 | 239.0 | 768 | 0.0 | −5.1 (p=0.43, n.s.) |
| nash-only (v6.0) | 0.00 | 238.9 | 1323 | 0.0 | — |

- **P11a PASS, dramatically (replicates):** ungated cooperation with liars
  is a feeding frenzy — liar advantage +181 credits, 361–479 strip deals
  per run — while the SYSTEM still finishes (delivered ~240). Exploitation
  is redistributive: a fleet operator wouldn't notice until the books
  arrive. Green dashboard, robbed books.
- **P11b PASS, corrected form — the advantage is ERASED, not inverted:**
  with lies genuinely active at the lower tier, gating drops the liar
  advantage from +181 to statistical zero (+1.8/−5.1, n.s.). Honesty wins
  by ACCESS: attested robots keep the cooperation dividend; a liar's lie
  earns ≈ nothing at the veto tier (v6.0's theorem, now exercised in the
  same run). Strip deals at the gated tier: **0.0 exactly** at both liar
  fractions.
- **P11c PASS (the dividend is speed, replicates):** gated honest fleets
  beat nash-only by −574 ticks makespan (749 vs 1323, **−43%**) at the
  delivered ceiling — cooperation is worth a lot, which is why gating it
  matters.
- **New secondary:** relegated liars strand ~6× more than in the open
  swarm (7.4 vs 1.3 at f=0.5) — locked out of the rescue-rich cooperative
  tier, they bear their own risk. The gate prices dishonesty in safety,
  not just credit.
- **Metric note:** `exploit_deals` still counts benign honest↔honest
  cooperative sacrifice at the joint tier (~1580/run at f=0, by design of
  joint-max); STRIP (liar gains while honest loses) is the malice metric,
  and it is zero under gating.

**The three-layer result, in one breath:** the bargaining tier is
lie-tolerant by construction (v6.0 — the veto is the trust); the
cooperation tier is 43% faster but strip-mines the honest when open
(v6.1); attestation gates the valuable-but-fragile tier so that honesty
is the top-earning strategy and lying earns nothing anywhere. That is the
snhp architecture — Nash-IR bargaining as the deception-proof floor,
attestation-gated joint optimization as the high-trust ceiling —
demonstrated end-to-end in embodied form, replicating the arena finding.
And v7's corrected coda: the one thing NEITHER tier can supply is a true
gauge — self-knowledge error leaves output intact and silently corrupts
the books, which is precisely why the receipt (not the mechanism) is the
product.

---

## v6.0: strategic lies vs attestation (sweep_v6_D.json, 240 runs) — KILL FIRED

The pre-registered kill condition fired and the headline is the failure,
as promised: **attestation could not flip the lying incentive in Nash-IR
bargaining — because there was almost nothing to flip.**

- P10a REFUTED: lying barely pays (+3.9 credit on a ~95 base, p=0.71,
  7/16 runs) and the system barely notices (Δdelivered ≈ 0 at f ≤ 0.5).
- P10b PASS (mechanically): at f=1.0 deal volume collapses (90→37,
  92→23 deals) and delivered lands exactly on the rules-arm floor
  (231.2 vs 230.6) — mutual BATNA inflation empties the feasible set,
  but the abundant stage cushions the output cost.
- P10c PASS (pinned test): attested-all ≡ honest-all bit-identically.
- P10d FAILED both halves: no deception tax to recover at f ≤ 0.5, and
  the distrust defense is mathematically subsumed by the lie itself at
  f=1.0 (a 50% self-margin strictly contains a 25% imposed margin —
  defended and undefended runs are bit-identical there).

**The discovery under the corpse: Nash-IR bargaining with a true-loss
veto is intrinsically deception-tolerant.** Every executed deal clears
both TRUE disagreement points by construction (BATNA inflation only makes
the liar pickier — asserted in-arm), so lies can only skim small split
amounts or kill marginal trades. Exploitation requires a tier that TRUSTS
reports — the joint-maximizing cooperative tier, which executes without a
veto. That is exactly the arena finding ("the multi-issue edge is
attestation-gated"), and v6.1 tests it in embodied form.

Bonus honest oddity (echoes v5's noise-speedup): moderate lying IMPROVED
snhp-hz makespans (1323→~800) at zero output cost — liar pickiness prunes
marginal deal churn. ~30% of honest-fleet deals were apparently
low-value.

---

## v5: imperfect information in a rich ecology (sweep_v5_C.json, 736 runs)

Stage: 10 non-identical mirrored asteroids (240 units), 4 company-owned
chargers (guest rate 2 vs 4), lean fleets (mean battery 40), τ=0.15.
Information dial: noisy estimates of the partner's surplus (s ∈ {0, .25,
.5, 1.0}) with true-loss veto + one role-swapped retry. Same-code v4
anchors re-run for the ecology comparison (SPEC amendment 3).

| pred | verdict | evidence |
|---|---|---|
| P9a info tax + crossover | **REFUTED — bargaining is noise-robust** | No crossover exists: bargaining beats the auction at EVERY noise level (Δdelivered +3.6 to +9.8, all p≤0.034; makespans 500–1500 ticks faster). The veto turns estimation error into failed proposals rather than bad deals — the pre-registered "could fail" branch is what happened. Exploratory bonus: at σ=0.5, plain snhp's makespan IMPROVES with noise (1815→889) — noisy proposals explore bundles noiseless Nash never offers, vetoes filter the harmful ones. Direction consistent across arms; variance high; flagged exploratory. |
| P9b winner's curse | **PASS (direction)** | Vetoes rise steeply and monotonically with s (0 → 111 → ~500 per run at both σ). Concentration-on-overestimates logged but not yet analyzed distributionally. |
| P9c the net returns | **REFUTED** | Because P9a failed, the rescue gap never reopens: snhp+net − snhp-hz at σ=1.0 stays ≈0-to-negative at every s (−1.5 at s=1.0, p=0.042 in the WRONG direction). The v3 regime law survives noise. Nuance: the net still buys ~10 fleet lives per run (stranded 4–8 vs 14–18) at roughly zero delivered cost at σ=0.5 — a survival dividend, not an output one. |
| P9d ecology shift | **STRONG PASS** | vs same-code v4 anchors at σ=0.5: strandings collapse (auction 18.3→8.9, net 16.3→4.0, team 10.6→1.1), completion 85–92% → 95–100%, healthy border trade up (0.6→10.9 for net; team 11→39), and claim swaps explode to 46–73/run (v4: ~0–14) — with many non-identical asteroids, mining rights became a real currency. The bargaining advantage shifted from rescue churn to allocation, as conjectured. |
| Placebo | **PASS** | Company delivered diffs centered on 0 (−3.4±19.4, +2.5±25.9); guest charging heavily used (~2,000 energy/run — priced infrastructure geography is live). |
| KILL check | **did not fire** | No s collapses bargaining below the auction anywhere — the full-information results were not decorative. |

Headline: **the imperfect-information gap did not close the market — the
veto did the work of trust.** In the rich world, bargaining is the
difference between finishing (237–240/240) and not (auction/rules
229–234, censored at the horizon), at every noise level tested. Remaining
honest gap: robots still cannot LIE strategically (noise ≠ deception);
incentive-compatible misrepresentation is the next rung and needs the
engine's attestation machinery.

---

## v4.1: price formation (equilibrium_v41.json, 544 runs)

| pred | verdict | evidence |
|---|---|---|
| P8a interior τ* | **PASS** | null fleet: τ*=0.200 at both σ, revenue single-peaked (40.2 at peak, collapsing to 5.0 at τ=0.5) — a real monopoly price just above the modal switch point (the monopolist prices into the inelastic straggler tail) |
| P8b bargaining disciplines prices | **PASS — in revenue, not price** | τ* barely moves (0.175–0.200 both fleets) but the refinery's peak revenue from a bargaining fleet is **~60% lower** (16.7 vs 40.2 at σ=0.5; 11.2 vs 33.5 at σ=0). Mechanism: the bargaining fleet's internal deals keep cargo with home-refinery robots (foreign volume 15–27 vs null's 45–49), shrinking the tariff base. The gray market doesn't haggle the posted price — it starves the toll booth |
| P8c knife edge | **PARTIAL** | σ=0 revenue curve is jagged/non-monotone (33.5 → 23.8 → 26.2, dead zone at 0.5); σ=0.5 is a clean smooth single peak — heterogeneity makes the market price well-defined, as registered |
| P8d separability | **PASS** | R0(τ0) unchanged when τ1 pinned at 0.5 (Δ ∈ [−2.0, +1.9], no systematic sign): two independent monopolies, not Bertrand — the structural correction to the panel's own framing, now empirical |

Side observations: the bargaining fleet's system delivered is nearly
tariff-inelastic (110.8→107.8 across the whole τ range at σ=0.5) while the
null fleet swings; at σ=0 the homogeneous hazard fleet remains boom-or-bust
(77–91 delivered, huge variance) — consistent with the v3 regime law.

---

## v4.0: structural ownership + tariffs (sweep_v4_A.json 864 runs, sweep_v4_B.json 1080 runs)

**The placebo earned its keep on day one.** First anchor pass: every arm's
company-ledger difference sat near 0 except team (+19.7/+18.3/+21.0 —
flagrant). Root cause: `np.argmax` first-index tie-breaking + twin-fleet
exact ties + negative-cargo-first contract ordering ⇒ tied deals drained
cargo toward lower rids = company 0. Fixed (seeded-uniform pick among
ε-ties), verified (10-seed mean −1.1±18.5), full column re-run. Per the
pre-registration, no team-family claim was read from the biased artifact.
Bridge also passed pre-sweep: v3 world through v4 code reproduces sweep_v3
within CI (noted deviation: auction handoffs now use the shared
delivery_target scoring — the panel's fairness fix).

### Scored predictions (clean data)

| pred | verdict | evidence |
|---|---|---|
| Placebo | **PASS** (after fix) | all arms coΔdelivered within ±6, no systematic sign |
| P7-A border volume | **PASS — no autarky** | snhp border cargo ≈ auction's (7.1 vs 6.4 at σ=0.5); caveat: at τ=0 border trade is overwhelmingly distress-driven (healthy ≈ 0.2/run); the healthy channel only wakes under tariffs (→ B) |
| P7-B demand response | **PASS, textbook** | null's foreign-refined vs τ: 48→48→40→19→0 (σ=0) — the choke sits exactly at the panel-derived τ*≈0.16; heterogeneity smooths the step (σ=1: 48→48→46→22→1), as the economist predicted |
| P7-B′ tariff avoidance | **FAIL on the registered metric, holds on energy** | d(delivered)/dτ: null is flat-to-POSITIVE (high τ forces home-hauling; the 2500-tick horizon absorbs the distance — the red-team's F2 ceiling warning verbatim); on energy efficiency the story inverts: null degrades −12/−20% across τ, snhp-hz only −7/−8%. Registered metric was wrong, as warned; reported as failed-as-stated |
| P7-B″ incidence | **UNDERPOWERED** | healthy border deals are 0.2–1.3 units/run at these τ — too thin to estimate the wedge split; powered version needs v4.1's equilibrium τ-setter (higher τ*, more border pressure) |
| P7-B‴ team flat in τ | **PASS (exact)** | team rows bit-identical across all τ (internalized tariffs are invisible to a merged firm's routing) |
| P7-C regime order | **PARTIAL** | crossing exists (hz − net: −7.5 ns at σ=0 → +8.8 p=.004 at σ=0.5 → +3.9 p_w=.015 at σ=1) with one ns wobble at σ=0.75; central charger compressed hazard spreads as anticipated |
| P7-D decomposition | **boundary premium real & small; merger premium ≈ 0** | team − team-co: +3.7/+3.2 (p_w=.007/.012 at σ≥0.5). team − twofirm: +0.9/+2.7/+5.4 (only σ=1 marginal, p_t=.040). twofirm − team-co: ≈0 (ns). **Two firms bargaining at the border ≈ a full merger** — the ordering team ≥ twofirm ≥ team-co holds at σ=0.5, wobbles ns at σ=1 |

### Headlines that survive

1. **IR bargaining vs the market lineage, strongest yet:** snhp beats
   auction by +15.5/+15.0 delivered at σ=0.5/1.0 (p<0.001, 22–23/24 seeds)
   in the symmetric two-company world; at σ=0 (exact twin fleets) all
   mechanisms statistically tie null — no heterogeneity, no gains from
   trade, exactly as theory demands.
2. **Border bargaining ≈ merger.** The measured premium for full fusion
   over two-firms-with-Nash-borders is ~0–5 units (mostly ns). For the A2A
   thesis this is the money line: you don't need to merge fleets — you need
   a bargaining layer at the boundary.
3. **The tariff demand curve chokes exactly where the algebra said** and
   heterogeneity smooths it — the panel's re-grid turned a would-be
   vacuous monotonicity into a quantitative validation.
4. **Selfless cross-company transfers are net-harmful:** auction-co beats
   auction (+5.3 to +8.0, p≈.01) — walls help the selfless lineage, while
   snhp needs no walls because IR prices the border. Rules < null
   everywhere (the altruistic floor is a lossy tax in this harsh geometry).

### Honest negatives

- P7-B′ failed as registered (metric censored by horizon — the red-team
  predicted precisely this failure mode and we pinned the metric anyway;
  lesson logged).
- Registered border-handoff-count-increases-in-τ: total border cargo FALLS
  with τ (less cross-traffic → fewer rescue encounters); only the small
  healthy subset rises (0 → 1.3/run). The gray market exists but is thin at
  posted-τ volumes.
- The v4 world is brutally charger-bound (11–22/24 stranded in every arm)
  — energy scarcity dominates; makespans are censored in many cells.
- snhp-hz at σ=0 has enormous variance (±33) — the hazard arm is
  boom-or-bust when the fleet is homogeneous.

### v4.1 queue (from panel + these results)

Best-response τ equilibrium (per-company revenue objective) → powered
incidence + "bargaining disciplines posted prices"; time-resolved deadweight
metric; contract-side risk (rescue IOUs); vouchers as law-of-one-price.

---

## v3: hazard-priced risk (sweep_v3.json, 960 runs) — KILLED as stated, regime law found

P6 predicted smooth forward-looking risk pricing (`P_STRAND·sigmoid(−margin/8)`
instead of the binary cliff) would fix the pure market everywhere and make
the safety net redundant. **Both pre-registered kill triggers fired:**
snhp-hz ≤ snhp at σ=0.25 (−8.4, p=0.034), and the net still adds +22.8/+25.1
delivered at σ≤0.25 under hazard pricing. Honest verdict: hazard pricing is
NOT a universal substitute for the rescue floor.

What it IS: **the best IR mechanism in the heterogeneous regime.** At σ≥0.75
snhp-hz beats plain snhp (+7.0/+9.8, p≤0.04), beats the auction by the
largest margins any pure market achieved (+21.0 at σ=0.75, p<0.001; +11.9 at
σ=1.0, p=0.002), and **beats the v2 champion snhp+net** (+15.9/+7.8, p≤0.03)
— while under hazard pricing the net flips to actively harmful there
(−10.4/−9.8).

**The regime law:** *risk pricing works when risk is heterogeneous; safety
nets work when it isn't.* At low σ every robot carries a similar hazard, so
there is no cheap counterparty to buy survival from — pricing risk just
raises everyone's reservation value for energy and thins the market (the
σ=0.25 loss). Insurance requires diversity. At high σ, hazard differences
create exactly the gains from trade the bargaining engine harvests, and
charity misallocates what the market prices correctly. The two mechanisms
are regime complements, not substitutes.

Open follow-up (v4): valuation-side pricing (this experiment) is not the
same as making failure risk a TRADEABLE CONTRACT (rescue commitments / IOU
credit, deferred repayment). Contract-side risk trades across time rather
than across current risk differences, so it is the candidate that could
generalize to the homogeneous regime — where v3 shows valuation-side pricing
cannot.

Best system by regime: σ≤0.5 → snhp+net (~119/120, ~1.4 adrift);
σ≥0.75 → snhp-hz (106.3/99.9, lowest lost-cargo 1.9–2.8). Cooperative team
ceiling still above at high σ (117.5) — the price of selfishness stands.

---

# Results v2.1 — verdict against the pre-registration

*Sweep: `results/sweep_v2.1.json`, 888 runs (7 arm configs × 5 σ × 24 seeds,
2500-tick horizon), generated after SPEC v2 was pinned. One bug-fix re-run
from v2.0: the first v2 sweep exposed that Φ's cross-mining max made sector
swaps price at zero (the [cargo+energy] ablation ran bit-identical to the
full arm); Φ now values the source the movement policy actually mines.
Verdict per SPEC v2: **PARTIAL — reframe, don't spin.***

## Pre-registered predictions vs outcomes

| # | prediction | outcome |
|---|---|---|
| P1 | single-issue snhp arms strike 0 deals | **HOLDS AS AMENDED** — energy-only: 0 deals structurally (loss+friction make the donor always lose). Cargo-only: ~0.5 deals/run of exactly one kind — *distress jettison* (a near-stranded loaded robot gains by shedding load since loaded steps cost more). Codified in tests. C1 reads: bundling is necessary for all IR trade except jettison. |
| P2 | team ≥ snhp+net ≥ snhp > null; snhp > auction at σ≥0.5 | **PARTIAL, wrong in the best way** — snhp+net **beats the cooperative ceiling** at σ≤0.5 (119.6 vs 105.9 at σ=0). snhp > null everywhere (+9 to +38, 21–24/24 wins, p<0.001). snhp vs auction: tie at 0.5, wins at 0.75 (+14.0, p=0.002), tie at 1.0. |
| P3 | price of selfishness shrinks with σ | **REFUTED** — team−snhp: 11.0 → 10.8 → 9.2 → 18.1 → 27.5. Dips mid, then grows sharply. At high heterogeneity, cooperative coordination pulls away from any IR mechanism. |
| P4 | snhp−auction grows monotonically with σ | **PARTIAL (strong trend, one break)** — −22.6 → −13.7 → +0.9 → +14.0 → +2.1. Cleanly monotone σ=0→0.75 (a 36.6-unit swing — the heterogeneity mechanism is real), saturates/breaks at σ=1. |
| P5 | snhp lowest lost-cargo among IR arms; snhp+net fewer strandings at ≥ delivered | **HOLDS** — lost cargo σ=1: snhp/net 3.2/2.7 vs auction 6.1, rules 9.1, null 19.9. Strandings: snhp+net 1.3–6.1 vs snhp 14.5–15.5, with delivered equal or higher (σ≤0.5). |

## The three headlines that survive scrutiny

1. **Markets need safety nets — and then they win.** `snhp+net` (IR Nash
   bargaining + the altruistic trophallaxis floor) is the best system at
   σ≤0.5: **119.6/120 delivered, 1.3 stranded, fastest makespans in the
   table** — above the cooperative greedy ceiling. And against its clean
   one-mechanism-apart comparator (`auction` = same trophallaxis base +
   scalar handoff instead of bundles), it is positive at every σ (+2.1 to
   +8.9; Wilcoxon p≤0.004 at σ≤0.5; 14–18/24 wins at all σ). The v0 emergent
   finding ("the market won't rescue the destitute") became the design rule:
   price-blind rescue for distress, bargained bundles for everything else.
2. **Bundling is necessary under individual rationality.** Energy-only trade
   is structurally impossible; cargo-only exists solely as distress jettison;
   96–99% of struck deals are multi-issue. Cooperatively, multi-issue also
   beats single-issue at every σ (team − team[energy]: +1.8 to +17.1,
   significant at 4 of 5 σ) — rebutting the reviewer's "single-issue
   suffices" in the mean-preserving world (that result was an artifact of
   the v1 poverty-confounded dial).
3. **The price of selfishness is real, quantified, and grows with
   heterogeneity:** 11 → 27.5 delivered units (team − snhp) as σ goes 0→1.
   For mixed-ownership fleets this is the measured cost of not being one
   company — and the argument for why the negotiation layer (which recovers
   most of it at low-mid σ when paired with the safety net) matters.

## Honest negatives and nuances

- Pure `snhp` (no net) never significantly beats the auction rung on
  delivered; the bargaining win requires the safety-net floor at low σ.
- The safety net itself **hurts at σ=0.75** (snhp 99.3 vs snhp+net 90.4):
  with extreme spread the threshold rule fires chronically and the 25%
  transfer loss becomes a redistribution tax. Safety nets should trigger on
  distress, not inequality — a v3 design note.
- P4's break at σ=1.0 is unexplained (candidates: cap-1/eff-1.5 robots that
  no deal can salvage; charger binding). Do not claim full monotonicity.
- Makespan is right-censored for many arms at σ≥0.75; delivered-at-horizon
  is the only primary.
- 25 paired tests were run; the load-bearing results (snhp+net−auction at
  σ≤0.5, snhp−null everywhere, snhp−auction at 0.75, team−team[energy] at
  0/0.25/1) have p≤0.004 and survive Holm within their families. Marginal
  results (σ≥0.75 hybrid comparisons) are stated as such.

## Status vs the expert credibility bar (STANDARDS_BRIEF §5)

Done: mean-preserving heterogeneity, strong cooperative + single-issue
baselines, 24 seeds + Wilcoxon, strandings priced, necessity claim pinned as
test. Not done (v3+ ladder): noise/fault injection, N-sweep, partial
information (the engine's Bayesian machinery is the natural next step),
continuous space, hardware. Positioning: multi-robot mechanism benchmark,
MRS/AAMAS lineage — per both reviews.

## v10 (column I): imperfect field information — the omniscience was never doing the work

Founder's premise ("companies don't have perfect info about the field;
everyone works on estimates") built as company-level beliefs with
proximity sensing + a rival-rate racing discount (SPEC P15). Verdict:
**every v8 headline survives imperfect information unchanged IN A STATIC
FIELD** (oracle vs belief: +0.2 delivered n.s.; no ordering inverts).
Founder's post-hoc scoping, correct and adopted: the field never changes,
grows, shrinks, or gets meaningfully mined by competitors on this mirrored
map, so belief error is one-sided (optimistic only), bounded (a wasted
trip), self-correcting on contact, and barely adversarial — wrong beliefs
were structurally unpunishable. The robustness claim is scoped to static
fields; v11 (column J, the moving field) is the fair test of information
value. Mechanism confirmed on the
way: **the swarm is its own sensor network** — trading fleets hold ~3×
fresher maps than the auction (staleness 165 vs 525 ticks) because deals
move robots. And the v7 law generalizes: stale maps, like bad gauges,
leave output flat while quietly poisoning receipts (3.4–9.2 truly-harmful
deals/run appear under belief-mode; zero under oracle). The racing
discount died on its pre-registered kill (static share was already the
right price on mirrored fields). Reproduce: `run.py --column I`.

## v11 (column J): the moving field — the explorer's dividend

Founder's critique built honestly (arrivals nobody knows about,
departures that leave ghosts on stale maps, contested unmirrored ground).
Verdicts: information's value on a moving field shows up FIRST in the
books (belief-mode signs +7.0 more truly-harmful deals, p=.0004; output
gap +11.4 directional but n.s. at 16 seeds — P16a fails as registered,
J2 gate closed). The registered freshness prediction INVERTED: the
auction, with maps 60% staler, captures MORE of the new rocks (46 vs 32
units, p=.03) — discovery needs physical coverage, and the deal economy's
efficiency converges robots onto known loops while the auction's
wandering is accidental exploration. Downstream, a first headline
inversion: **on moving contested fields the auction out-delivers every
coordination arm on raw gold (net −12.6, p=.044) while replacement-cost
scores are a wash — optimization buys blindness to novelty.** The
bargaining advantage is a known-field phenomenon; novelty-rich worlds
reward coverage over coordination. Racing discount: killed for good.
Reproduce: `run.py --column J`.

## v12 (column K): pricing the unknown — scouting fixes discovery; the map market fixes the books

Founder's mechanisms built and run. The discovery deficit died to POLICY,
not markets: two scouts per company erased the auction's explorer edge
(arrivals gap −13.8 p=.03 → −3.4 n.s.; delivered inversion gone) and even
made the oracle redundant (282.8 vs 284.1 — patrolled beliefs ≈ perfect
information). The map market (40 syncs/run, real Nash-priced trades)
added nothing to discovery but **cut poisoned deals 30% (p=.04): traded
information's product is audit integrity, not output**. And the registered
bad-news trap confirmed structurally: a sync that only carries bad news
is IR-vetoed — it trades only when BUNDLED with enough good news, i.e.
the program's first law (bundling or silence) reappears one level up, in
the market for information itself. Fixed prospecting claims produce real
patrol differentiation (22.7 vs 25.4 staleness) and no output change.
Reproduce: `run.py --column K`.

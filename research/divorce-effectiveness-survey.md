# Divorce settlement effectiveness — research survey + new fronts (2026-07-18)

Six parallel deep-research streams (Opus), each with per-claim VERIFIED /
UNVERIFIED flags; primary sources read where accessible. Condensed here;
full stream reports in the session transcript. Purpose: ground "Irreconcilable
Agents" in the literature and identify genuinely novel fronts for snhp.

## 1. The effectiveness literature — what exists

**Law & economics (foundations, primary-verified):** Mnookin & Kornhauser
(1979, Yale LJ) — divorce law's main function is setting the threat points
for private bargaining ("bargaining in the shadow of the law"). Their FIVE
litigation impediments, verbatim from the founding text: (1) **SPITE** ("a
desire to punish the other spouse"), (2) distaste for negotiation, (3)
strategic bluff breakdown, (4) mutual optimism, (5) **NO MIDDLE GROUND**
(indivisibility). The demo's two acts are literally impediments #1 and #5.
They frame the Pareto frontier (Edgeworth "contract curve") — theoretically
only. Settlement-failure theory: Priest-Klein 1984 (divergent expectations;
Lee & Klerman 2016 proofs), Bebchuk 1984 (asymmetric information screening).
Trial rates: the "95% settle" figure is practitioner folklore; the citable
anchor is Maccoby & Mnookin (1992, N>1,000 CA families): ~1.5–3.5%
judge-decided.

**Mediation vs litigation RCTs:** Emery's Charlottesville RCT (N=71,
randomized): 4/35 mediation vs 26/36 litigation families saw a judge;
12-year follow-up: ~28–30% vs 9% weekly nonresidential-parent contact; more
consensual agreement changes (1.4 vs 0.3); fathers' satisfaction up, mothers'
not (the asymmetry). Pearson & Thoennes (Denver): 50–80% settlement, better
support compliance. Shaw (2010) meta-analysis: only FIVE studies rigorous
enough to include; grand effect 0.36. Kelly (2004) states the field's success
criteria verbatim: "settlement rates, satisfaction, efficiencies in time and
cost, … durability." Also: mediation never improved psychological adjustment
in any study measuring it. Standing critiques any design must inherit:
selection bias (most studies aren't randomized), Grillo's power-imbalance
critique, domestic-violence screening (coercive-control cases must never be
mediated; one study: 63% secondary victimization).

**Fair division:** Brams & Taylor's Adjusted Winner: envy-free + equitable +
Pareto-optimal for two parties — UNDER HONESTY. Provably not strategy-proof
(B&T admitted it; Aziz et al. 2015 formalized: no pure NE in general, PoA
4/3). **Zero recorded real-world uses.** The only lab tests: Daniel & Parco
2005 (subjects manipulated it; only ~1/3 envy-free under common knowledge),
Schneider & Krämer 2004 (procedures stop outperforming divide-and-choose
once deviation is allowed). Spliddit lists divorce as a use case; zero
published divorce outcomes.

**Negotiation-support / ODR systems:** Family_Winner/AssetDivider
(Zeleznikow school) — never evaluated on real divorces (the 650 AIFS cases
were rule-calibration; one textbook case demo; solicitors flagged it
"ignored issues of justice"). Smartsettle's "16% value forgone" = a 1992
simulation on constructed water-resources problems, not an outcome.
**Rechtwijzer post-mortem (corrected):** died 2017 on ECONOMICS AND
INSTITUTIONS (~1% uptake ≈ 700/65,000 Dutch divorces/yr; legal aid board
pulled funding; bar resistance; the "submission problem" — only ~60% got the
partner to the table) while USER metrics were strong (72% rated ≥8/10, >70%
felt fair). Survivor Uitelkaar.nl lived by narrowing scope + human
touchpoints. Modern AI mediation: Habermas Machine (Science 2024, N=5,734,
deliberation not divorce); Bergen & Kraus: sycophantic LLM mediators
over-affirm 2x and HARDEN positions (rhymes with our 8% goodwill-leak trap
check). Court ODR (BC CRT): 52% settle-before-adjudication; satisfaction
surveys only.

**Preference elicitation:** Carson & Groves 2007 — consequential BINARY
CHOICE can be incentive-compatible; open-ended valuation is not (the theory
behind our v2 all-choices interview). Caveat: Meginnis et al. 2021 — repeated
multi-alternative choice experiments still gameable. Elicitation-budget
curves (capture vs #questions) are mature in AI preference learning
(Chajewska/Koller, Boutilier minimax-regret), auctions (Sandholm; Nisan-Segal
worst-case exponential), and agent negotiation (Baarslag & Kaisers 2017 =
nearest prior) — and have NEVER been applied to legal settlements. No
published work elicits divorcing parties' package preferences via choice
tasks. MUST-CITE for any manipulation claim: Kesten & Özyurt 2025
(Management Science) — characterization of strategy-proof, efficient, IR
multi-issue ODR mediation ("quid pro quo" domains).

## 2. The metric gap (the thesis)

The field measured whether people agreed and felt good about it (settlement
rate, satisfaction, time, cost, relitigation, contact). It NEVER measured:
surplus captured vs the achievable frontier, envy-freeness under true
utilities, elicitation sufficiency, or value destroyed by spite — because it
structurally couldn't: true utilities are unobservable in real disputes,
stated valuations are provably strategic (AW), and no oracle benchmark
exists outside induced-value labs (Tripp & Sondak 1992 tradition), which by
construction aren't real divorces. Sealed-utility instrumentation +
replayable receipts + counterfactual re-runs is the missing instrument.

## 3. Ranked new fronts (novelty-checked against named priors)

**F1 — The pettiness tax (per-case spite counterfactual). Most
product-native.** Priors: Levine 1998 (spite coefficient), Zizzo-Oswald 2001
(willingness-to-pay-to-burn), Mill & Staebler 2023 (spite raises litigation
spending — population statistics, the nearest prior). NOBODY produces a
per-case, re-runnable "this settlement, minus your spite" counterfactual.
Our engine already computes it. No naming precedent for "pettiness/spite tax."

**F2 — Cryptographic receipts × procedural justice. Cleanest unclaimed
cell; needs a human-subjects experiment.** Priors: Tyler (fairness →
compliance), Leventhal criteria, Lee et al. 2019 CSCW (transparency/outcome
control raise perceived fairness of algorithmic mediation — but
human-readable transparency, not proof), Bamberger et al. 2022 Berkeley Tech
LJ (ZK for legal verification — no empirics). The untested proposition: does
a machine-checkable "nobody peeked" receipt move perceived fairness /
ratification / compliance beyond plain transparency?

**F3 — Calibrated abstention as a mediation principle. Unnamed bridge.**
Priors: Chow 1970 reject-option → SelectiveNet (ML abstention, mature);
mediator self-determination ethics (mediators must not push). Nobody has
ported Chow's rule to the propose/abstain decision with RATIFICATION as the
predicted label. Our mediator already abstains; the contribution is
calibration + formalization.

**F4 — Adversarial per-spouse agents + verifiable receipt. Weakest pure
novelty, strongest framing/demo.** Priors: Zeleznikow suite (cooperative
single-system support), ANAC (domain-agnostic agent bargaining), IMODRE
(multi-agent but functional roles). The combination — two self-interested
advocates refereed by a cryptographic skeptic — is the open framing.

**F5 (cross-cutting) — The elicitation-budget curve for settlements.** The
METHOD is precedented (Boutilier/Chajewska/Baarslag — claim the APPLICATION,
never the method, or reviewers will pounce). No budget curve exists anywhere
in family law. Our Q-sweep is already this experiment on synthetic couples.

## 4. Overclaim guards (the "already done" list)

- Budget-curve methodology: exists (AI/auctions/negotiation). Claim the
  legal-settlement application + the choice-based/strategy-proof pairing.
- Choice-over-valuation elicitation: theory exists (Carson & Groves). We
  APPLY it; cite it.
- Spite coefficients and welfare costs: exist at population level
  (Levine/Mill-Staebler). Ours is the per-case counterfactual.
- Strategy-proof mediation theory: Kesten & Özyurt 2025 — position against.
- AW manipulability: known since 1996; formalized 2015. Not our discovery.
- Rechtwijzer "died from pushing settlements" is FALSE — it died on
  economics/institutions. Do not repeat.
- AI-mediator fairness perception: Habermas Machine covers deliberation;
  distinguish bilateral settlement.

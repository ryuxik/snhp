# The honest baseline — humans negotiating BADLY, and SNHP vs how they ACTUALLY negotiate (task #69)

*2026-07-10. The pre-SNHP world is NOT "no negotiation." On the vendor / supply
side there is no sticker — procurement is ALL negotiation, conducted by humans
using the hardball-tactics canon. wholesale/'s existing `ratecard` arm is already
ONE toxic tactic (a Boulware take-it-or-leave-it: the distributor posts a card,
the venue takes it or defects to Jetro). This effort builds the RICHER battery —
the human negotiator TYPES — and proves SNHP beats how humans actually negotiate,
not a passive-posting strawman. Every headline delta carries a 95% t-interval over
SEED means; no win is claimed when a CI includes zero. Pairing is keyed on the
demand identity (seed × week × relationship × type-pair), NEVER on the mechanism.
No LLM is invoked; every number is byte-deterministic on the seed.*

Rerun:

```
python3 -m pytest wholesale/tests/test_negotiators.py -q            # 19 tests
python3 -m wholesale.run_human --seeds 8 --weeks 12 \
    --out wholesale/results-human.json
```

Files: `wholesale/negotiators.py` (the taxonomy + the concession game + the
retention model), `wholesale/run_human.py` (the type-population experiment),
`wholesale/tests/test_negotiators.py`, `wholesale/results-human.json`;
`wholesale/scenario.py` gains `bundle_grids` (the feasible-bundle utility tensors,
extracted so `nash_deal` and the human frontier read the SAME utilities — the
S1 reproduction contract stays green to the cent).

---

## The taxonomy (grounded in the negotiation literature)

A negotiator TYPE is a point in tactic-space (`NegotiatorType`). The tactics are
the axes; the named personalities are characteristic bundles of them. Both the
venue AND the wholesaler can be any human type OR the SNHP broker.

**Tactics (the axes).**
- **extreme ANCHORING** (`anchor`) — a biased first offer pulls the settlement.
  *Tversky & Kahneman 1974* (anchoring heuristic); *Galinsky & Mussweiler 2001*.
- **BOULWARE / take-it-or-leave-it** (`concede≈0`, short `deadline`) — one firm
  demand, no movement. *Fisher & Ury, "Getting to Yes"* (positional deadlock).
  The rate-card baseline IS a Boulware offer.
- **BLUFFING / misrepresenting BATNA** (`claim_floor>0`, `honest=False`) —
  claiming a stronger reservation than is real. *Malhotra & Bazerman,
  "Negotiation Genius"* (lies & deception); BATNA is *Fisher & Ury*.
- **NIBBLING** (`nibble>0`) — extracting extras AFTER the close. *Malhotra &
  Bazerman*.
- **FALSE DEADLINE** (short `deadline` as pressure) — *Malhotra & Bazerman*
  (manufactured urgency).
- **POSITIONAL bargaining** (`positional=True`) — fights price only, freezes
  window / case-size / terms / spoilage → misses the logroll. *Fisher & Ury*'s
  central diagnosis; *Thompson, "The Mind and Heart of the Negotiator"* (fixed-pie
  bias).
- **EXPLOITING INFO ASYMMETRY** (`exploits=True`) — the sophisticated reads a
  naive counterpart and squeezes it. *Akerlof 1970*; *Malhotra & Bazerman*.

**Personalities (named archetypes).** HARDBALLER (aggressive extractor),
ACCOMMODATOR (the naive over-conceder — *Thompson*'s soft style), BLUFFER, AVOIDER
(conflict-averse, walks from positive deals — *Thompson*), BOULWARE, POSITIONAL,
NIBBLER, and FAIR (the "good human" — *Fisher & Ury* PRINCIPLED negotiation: opens
all issues, honest BATNA, insists on a fair split, won't cave to an ultimatum).

**SNHP is not a personality — it is the neutral broker.** It computes the Nash
bargaining solution (*Nash 1950*) over the FULL bundle against the
event-consistent disagreement: the efficient bundle (the full logroll) with its
Nash split. Personality is irrelevant to the broker — the hardballer cannot
out-anchor it and the accommodator cannot be fleeced under it. This is exactly the
validated `nash_deal` engine that reproduces `run.run_week` to the cent.

## The model (a deterministic concession game — no LLM)

The negotiation is decomposed into the two dimensions the literature separates:

1. **Pie size (value creation).** Which issues are on the table. If EITHER party
   is POSITIONAL, only price moves and the rest freeze at rate-card defaults → the
   price-only pie `pie_pos`; otherwise the full logroll `pie_full`. It takes two to
   logroll. **The strong, honest finding: `pie_pos ≈ $0` everywhere** — price is a
   near-pure transfer, so a price-only negotiation creates essentially NONE of the
   joint surplus; the entire pie lives in window × qty × terms × spoilage.
2. **The split (value claiming).** An alternating-offers concession game
   (*Rubinstein 1982*, reduced to share-space). Each party demands a share
   `σ_i(t) = φ_i + (α_i − φ_i)(1−β_i)^t` (open at the anchor, concede toward the
   claim-floor — a bluff inflates that floor). A deal CLOSES at the first round
   `t ≤ min(deadline_v, deadline_w)` with `σ_v + σ_w ≤ 1`; the slack is split
   evenly. If demands never become compatible before the earliest walk → IMPASSE:
   the positive-surplus deal is destroyed (the *Myerson & Satterthwaite 1983*
   no-trade deadweight, produced endogenously by the tactics).

The pie is the VALIDATED `nash_deal` joint gain (computed in the SNHP-coordinated
route environment — a per-relationship constant, paired across arms), so SNHP is
the efficiency ceiling by construction and humans are NOT additionally penalised
for degraded route density (a conservative choice). The split is over the money
transfer holding the efficient bundle fixed, so shares map linearly to dollars; a
type's posture is pie-independent, so each tactic is exactly reproducible while the
dollar outcomes stay paired on the demand identity, never on policy.

---

## The four ways human negotiation fails, and SNHP fixes each

*8 seeds × 12 weeks, full human type cross-product (64 pairs) over every
positive-surplus relationship SNHP closes (~4,700 negotiations/seed). Paired;
95% CI over seed means.*

| # | failure mode | human-vs-human | both-SNHP | SNHP fix (95% CI) |
|---|--------------|----------------|-----------|-------------------|
| 1 | **IMPASSE** (Myerson-Satterthwaite deadweight) | **37.5%** of negotiations impasse; **$53.60** of pie destroyed per impasse | **0.0%** impasse | closes every positive-surplus deal; the deadweight ($53.60) dwarfs the $5 don't-negotiate buffer |
| 2 | **EXPLOITATION** (naive fleeced via info asymmetry) | naive party nets **$11.61** | naive nets **$26.80** | **+$15.20** [14.98, 15.42] — the neutral split protects the naive |
| 3 | **MISSED LOGROLL** (positional fights price-only) | positional joint **$0.00** | joint **$53.60** | **+$53.60** [52.83, 54.38] — SNHP captures the entire integrative pie |
| 4 | **RELATIONSHIP DAMAGE** (toxic tactics → churn) | retention **0.71**, LTV **$235** | retention **0.97**, LTV **$531** | LTV **+$295.61** [291.0, 300.2] — the fair, no-impasse deal is retained |

All four deltas are significant (CI excludes zero). Mode 1's impasse rate is a
**structural constant** of the uniform population — 24 of the 64 type-pairs
(hardball×hardball, anything×avoider, bluff×hardball, boulware×firm, …) never
converge — hence the near-zero-width CI; the dollar deadweight varies with the
seed's pie.

### The mechanisms, per mode

1. **Impasse.** Aggression is self-defeating in a population: hardball×hardball
   deadlocks (both hold past the deadline), the avoider walks from positive
   surplus at round 0, boulware's ultimatum is refused by any firm party, and a
   called bluff blows up the deal. SNHP's neutral split always clears (it prices
   against the pinned reservations, so there is no posture to deadlock).
2. **Exploitation.** A sophisticated hardballer reads a soft counterpart
   (`exploits`), raises its anchor to ~0.95 and stops conceding — the accommodator
   caves to a **7% share**. Averaged over all opponents the naive nets only
   $11.61; the broker gives it the neutral Nash split ($26.80) regardless of who
   sits across the table.
3. **Missed logroll.** Because `pie_pos ≈ 0`, a positional (or hardball-positional)
   party realises essentially none of the joint surplus — it haggles price, which
   is a transfer, and never touches the window / qty / terms / spoilage levers
   where all the value is. SNHP opens every issue and books the efficient bundle.
4. **Relationship damage.** Grievance = how far BELOW the neutral share a party was
   squeezed, plus a nibble penalty, plus an impasse penalty → a weekly churn
   hazard → an expected retained-LTV over a 12-week horizon. SNHP is the neutral
   benchmark, so its squeeze — and grievance — is ≈0 by construction; the toxic
   human outcomes churn out the relationship. *(The coefficients — H0=0.03,
   W_squeeze=0.60, W_nibble=0.25, W_impasse=0.50 — are a transparent
   parameterisation; the DOMINANCE is coefficient-robust because SNHP has
   squeeze=0, nibble=0, impasse=0 for ANY non-negative weights.)*

---

## The both-sides verdict

Does both-sides-SNHP DOMINATE human-vs-human across the type population?

| axis | human-vs-human | both-SNHP | gain (95% CI) | dominates? |
|------|----------------|-----------|---------------|-----------|
| total surplus / negotiation | $20.94 | $53.60 | **+$32.66** [32.19, 33.14] | **yes** |
| fairness (worse-off party's share) | 0.14 | 0.42 | **+0.28** [0.277, 0.282] | **yes** |
| efficiency (impasse rate) | 37.5% | 0.0% | **−37.5pp** | **yes** |
| retention | 0.71 | 0.97 | **+0.26** [0.261, 0.262] | **yes** |

**VERDICT: both-sides-SNHP dominates on ALL FOUR axes** — total surplus, fairness
(it protects the worse-off / naive party), efficiency (no impasse) and retention —
every CI excludes zero.

### Per-type: who gains by switching to SNHP ($/appearance, averaged over both roles)

| type | human payoff | SNHP payoff | gain from switch (95% CI) | better off? |
|------|-------------:|------------:|---------------------------|:-----------:|
| fair | 16.86 | 26.80 | +9.94 [9.79, 10.08] | yes |
| **hardballer** | 14.62 | 26.80 | **+12.19** [12.01, 12.36] | **yes** |
| boulware | 5.13 | 26.80 | +21.68 [21.36, 21.99] | yes |
| accommodator (naive) | 11.61 | 26.80 | +15.20 [14.98, 15.42] | yes |
| bluffer | 15.64 | 26.80 | +11.16 [11.00, 11.32] | yes |
| avoider | 3.35 | 26.80 | +23.45 [23.11, 23.79] | yes |
| positional | 0.00 | 26.80 | +26.80 [26.41, 27.19] | yes |
| nibbler | 16.55 | 26.80 | +10.25 [10.10, 10.40] | yes |

**Every type — including the HARDBALLER — is better off switching**, all CIs
exclude zero. `types_worse_off_under_snhp = []`.

### Is even the hardballer better off? — the HONEST decomposition

Yes on average — **but it DOES lose its extraction edge, and that matters.**

- **On average (+$12.19):** the hardballer is better off because aggression is
  self-defeating in a mixed population. It impasses or collapses the pie against
  five of eight opponent types (hardballer, bluffer, avoider, boulware,
  positional → ~$0), and only extracts against the three soft ones. Its mixed-
  population average ($14.62) sits below the broker's neutral split ($26.80).
- **The edge it gives up (−$23.21 [−23.55, −22.87]):** when the hardballer
  actually fleeces a naive, it takes **$50.01**; under the broker it gets the
  neutral **$26.80**. So **against a naive-heavy population the hardballer is
  WORSE off under SNHP** — it is better off here ONLY because a realistic mixed
  population makes its aggression impasse half the time.

So the fully honest story is **both**: the joint is much larger and the naive are
protected, *and* the hardballer nets more on average *because its own aggression
was costing it half its deals* — while conceding that a pure predator facing only
prey would rationally decline the broker. The value-creation-plus-no-impasse gain
outweighs the lost extraction only in a population with enough other aggressors.

---

## Variety on the SNHP block too — robustness & fairness

Even when BOTH counterparties use SNHP, they still have different underlying
personalities — and they all get a FAIR deal anyway, because the broker computes
the neutral split from the PINNED reservations regardless of who is negotiating.
`snhp_outcome` is byte-identical across all 64 type-pairs (asserted:
`test_snhp_split_is_personality_independent`): the hardballer cannot out-anchor
it, the bluffer cannot move it, the accommodator cannot be fleeced under it. The
neutral broker is robust to the entire personality distribution — that is the
product.

---

## Connection to Von Neumann — the toxic tactics ARE the misreport strategies

The minimax / cooperative-bargaining backbone is what makes the split
report-independent. The toxic tactics are a **richer liar battery** than the buyer
side's single WTP-understatement (paper §10):

- **Report-independent posture (anchoring, Boulware, positional, info-asymmetry
  exploitation) is fully neutralised.** The supplier's true reservation is its
  per-case COGS, pinned by finite stock (paper §10's finite-stock shadow pricing).
  No aggression moves the floor the broker prices against, so the fair split holds
  for any personality — the SNHP outcome is identical facing a hardballer or a
  saint (`test_snhp_split_is_personality_independent`).
- **The BLUFF is the one report that CAN move a naive counterpart's belief** — and
  it pays off in the human world (`bluff_split > honest_split`,
  `test_bluff_neutralised_when_reservation_is_pinned`). It **survives only where
  the claim cannot be verified.** On this interface the forecast is ATTESTED at
  settlement (RESULTS-SUPPLY S1), so a demand bluff is neutralised; a residual
  survives only for a truly-private outside option that no attestation can reach —
  **the attestation-required regime** (paper §10's conclusion that the
  private-value term needs attestation, reproduced one tier up on the supply
  side).

So SNHP neutralises exactly the misreports whose target reservation is
report-independent, and cleanly marks the boundary where attestation becomes a
security requirement rather than a discount tier.

---

## Verdicts (the honest bottom line)

1. **The pre-SNHP baseline is toxic human negotiation, not passive posting.** The
   rate card is just one tactic (Boulware); the real battery — anchoring, bluffing,
   nibbling, false deadlines, positional price-fixation, info-asymmetry
   exploitation — is modelled as counterparty policies, and each behaves as the
   literature specifies (7 tactic tests, all green).
2. **SNHP fixes all four failure modes, every CI clear of zero:** it closes the
   37.5% of positive-surplus deals humans impasse (destroying $53.60 each),
   protects the naive (+$15.20), captures the entire missed logroll (+$53.60, and
   the honest finding that price-only bargaining creates ~$0 of joint value), and
   preserves the relationship (+$296 LTV).
3. **Both-sides-SNHP dominates human-vs-human on surplus, fairness, efficiency AND
   retention** across the whole type population.
4. **Even the hardballer is better off on average (+$12.19) — but it gives up its
   extraction edge (−$23.21 vs a naive).** The honest read: the joint is much
   larger and the naive are protected, and the hardballer nets more only because a
   mixed population makes its aggression impasse half the time; a pure predator
   facing only prey would decline the broker.
5. **The toxic tactics are the misreport strategies Von Neumann's backbone
   neutralises where the reservation is pinned; the bluff survives only in the
   unattested regime** — a richer liar battery than the buyer tier, with the same
   finite-stock / attestation boundary.

Tests: 19 human-baseline (`wholesale/tests/test_negotiators.py`), all green; the
33 prior wholesale/supply tests remain green (the `bundle_grids` refactor is
byte-preserving — the S1 to-the-cent reproduction contract still holds). No LLM is
invoked; every result is deterministic on the seed.

# PREREG AMENDMENT 6 — adversarial tests of the one result that survived

*Written 2026-07-25, before any v8 code exists. Exploratory, like Amendments 1–5.*

---

## A6.0 Why this exists

Peer mode is now the study's headline: two adversarial engines produce **−$581**
joint, two peer-mode engines produce **+$5,171**, and the employee takes **95% of
the gain** — inverting the ~90%-to-the-employer split every other arm produced.

**It has never had a kill written against it.** It arrived as a bonus arm in
Amendment 5, not as a hypothesis anyone tried to break. Given that five harness
defects in this study each landed in the direction I was leaning, and that seven
of my seventeen on-record predictions have held, a headline that nobody attacked
is exactly the one to distrust.

## A6.1 The four attacks

**The baseline may be rigged in peer mode's favour.** The adversarial comparison
used `their_batna_estimate = 0.45` on both sides — the unjustified constant that
v7 showed is the highest-leverage input in the model. Adversarial duelling with
*true* BATNAs already reaches **+$3,475**. So the honest question is not "peer
mode vs adversarial-with-a-bad-guess" but "peer mode vs adversarial-with-the-truth,"
which is worth only **+$1,696** — a claim less than one bar above nothing.

**Truthfulness is assumed, not enforced.** `peer_mode` *trusts* the exchanged
BATNA. Nothing in the simulation makes honesty rational. If a side that inflates
its declared walk-away gains, peer mode is not incentive-compatible and every
number it produces is conditional on enforcement — which is precisely what the
attestation gate is for, and which this study has never tested.

**The 95% split may be a first-mover artifact.** The crab proposes first in every
duel.

**Jointly better is not individually better.** A crab may do better holding the
tool alone against an unarmed employer than entering peer mode with an armed one.
If so, no individual should opt in, whatever the joint number says.

## A6.2 Kills

Bar: **2% of salary ≈ $2,253**.

**K36 — THE HONEST BASELINE.** Measured against adversarial duelling **with true
BATNAs on both sides**, if peer mode's joint advantage is below the bar, then peer
mode as a distinct feature is not supported: its value is truthful BATNA exchange,
which needs no cooperative selection and no peer protocol. *Consequence:* the
headline becomes "exchange your walk-aways," not "use peer mode."

**K37 — DOES LYING PAY?** One side declares a BATNA inflated by δ ∈ {0.1, 0.2,
0.3} while the other stays honest. If the liar's own outcome improves by more than
the bar at any δ, peer mode is **not incentive-compatible**, and every peer-mode
number in this study is republished with "conditional on enforced attestation"
attached. *I expect this to fire.*

**K38 — FIRST-MOVER.** Re-run every duel with the Works proposing first. If the
crab's share of the joint gain moves by more than **20 percentage points**, the
95% figure is a property of my protocol, not of peer mode, and it is withdrawn.

**K39 — SHOULD AN INDIVIDUAL OPT IN?** Compare a crab in peer mode against a
peer-mode employer, versus a crab holding the engine alone against the standard
employer. If peer mode is worse for the crab by more than the bar, then it is
jointly efficient and individually irrational, and the demo says so beside the
joint number.

## A6.3 On-record predictions

1. **K36 fires.** Most of peer mode's measured value is the BATNA truth, and
   what is left will not clear the bar.
2. **K37 fires.** Lying pays. That is why the product gates this behind
   attestation, and the study should say so rather than reporting an honesty
   assumption as a result.
3. **K38 does not fire** — the split is driven by whose walk-away is worse, not by
   who speaks first.
4. **K39 does not fire** — the crab is better off in peer mode.

## A6.4 Standing

The sixth assertion (`test_compared_arms_face_the_same_counterparty`) is now in
`tests/test_arms.py` and passing. Every arm below must pass the full suite before
its numbers are read.

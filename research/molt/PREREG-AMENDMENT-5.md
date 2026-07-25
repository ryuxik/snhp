# PREREG AMENDMENT 5 — the ratchet, the learning, and the mode we never ran

*Written 2026-07-25, after four dead instruments and a literature check.
Exploratory. Written before any v6 code exists.*

---

## A5.0 Three admissions, all verifiable in the code

**1. The engine was never allowed to learn.** `run5.engine_inference` calls
`negotiate_bundle` **once**, with `their_offers=[opening]`, and the inferred
counterparty model is never recomputed. Every counter-offer — a direct signal
about the employer's cost structure — is discarded. The shipped `sitting_crab3`
does this correctly (`seen.append(...)`, `their_offers=seen`); I removed it when
building the selfish selector. **The "$5,196 is information" decomposition is
void** and is withdrawn pending A5.1.

**2. The sequential arm banks concessions permanently.** Nothing in
`slow_archetype3` lets the Works claw back a settled issue when a later one is
raised. A real employer says "if you want the title, base goes back to 3%." The
human archetype has been running with a free ratchet, and that ratchet is
load-bearing for the v4 headline that a human beats the engine.

**3. `peer_mode` and `cooperation` were never passed to the engine — not once,
in any arm, in any version.** Every result in this study is the adversarial Nash
path. The "joint welfare" arm in the 2×2 diagnostic was a hand-rolled
`argmax(u + w)` of mine, not the product's cooperative mode. That is precisely
the error Amendment 1 quoted from the rent study — a kill firing against my own
reimplementation instead of the product — repeated in the opposite direction.

`peer_mode` does three things the hand-rolled version did not: it treats the
exchanged BATNA as **true**, it **signals priorities in the opener** via
`bundle_peer_signal_boost`, and it selects the cooperative efficient package.
**The v1 finding that "arming both sides destroys value" therefore never tested
the mode built for both sides being armed.**

## A5.1 The literature says my protocol is the artifact

- [In & Serrano, *Agenda restrictions in multi-issue bargaining*](https://www.sciencedirect.com/science/article/abs/pii/S0167268103000878) —
  restricted agendas are inefficient exactly because they cannot exploit
  marginal-rate-of-substitution tradeoffs across issues, worsened by delay.
- [Fatima, Wooldridge & Jennings, *Multi-Issue Negotiation with Deadlines*](https://arxiv.org/pdf/1110.2765) —
  sequential vs simultaneous vs package-deal procedures compared directly.
- [Baarslag, Hendrikx, Hindriks & Jonker (2015), *Learning about the opponent in
  automated bilateral negotiation*](https://dl.acm.org/doi/10.1007/s10458-015-9309-1) —
  the survey of what A5.0(1) failed to do.

The consensus is that **package deals should dominate**. This study found the
reverse. That is evidence about my protocol, not about packages.

## A5.2 What v6 changes

**Learning.** Every engine arm accumulates the counterparty's offers and passes
the full history to `negotiate_bundle` on every call. No arm may call the engine
with a truncated history.

**No ratchet.** When a new issue is opened, the Works may re-open any previously
settled issue, subject to the package remaining an improvement for the crab over
its current standing position. Swept: `reopen ∈ {off, on}`, so the size of the
ratchet is measured rather than assumed.

**Peer mode, for real.** A new arm: both sides run `negotiate_bundle(peer_mode=True)`
with truthfully exchanged BATNAs. Reported against (a) both sides adversarial,
(b) one side armed, (c) the `cooperation` dial at {0, 0.5, 1} — the product's
own tilt, not my reimplementation.

**Standing assertions, as tests not habits.** `tests/test_arms.py` asserts, for
every arm: the counterparty can refuse (an arm that always settles its own
proposal fails), and any arm calling the engine passes an offer history whose
length grows with rounds. Three of the four dead instruments would have been
caught by these.

## A5.3 Kills

Bar: **2% of salary ≈ $2,253**.

**K27 — THE RATCHET.** If removing no-take-backs drops the human archetype's crab
utility by more than the bar, **every "a human negotiator beats the engine" line
from v4 onward is retracted**, including the ones now in the article and on the
demo. If it does not move, the human's advantage is real and the engine's deficit
stands as reported.

**K28 — LEARNING.** If passing the full offer history does not improve the engine
arm's crab outcome by more than the bar, then sequential opponent modelling buys
nothing here, the withdrawn information decomposition was wrong in *both*
directions, and the residual gap must be explained before anything is claimed.

**K29 — PEER MODE.** If two peer-mode engines do not beat two adversarial engines
on joint surplus by more than the bar, the product's cooperative mode does not do
what its docstring says in this market — a finding about the product, not the sim,
and it gets reported that way.

**K30 — PEER MODE'S SPLIT.** Report the crab/Works split under peer mode. If the
employer still takes >70%, cooperation does not fix the distribution problem and
the copy says so.

**K31 — AGAINST THE LITERATURE.** With ratchet and learning fixed, if package
deals still lose to sequential bargaining, we are contradicting In & Serrano and
Fatima et al. Either the mechanism is identified, or this simulation is declared
unreliable for the procedure question and the study stops claiming anything about
it.

## A5.4 On-record predictions

1. **K27 fires** — the ratchet is worth a lot and the human's advantage shrinks
   or reverses.
2. **K28 does not fire** — sequential inference materially helps.
3. **K29 does not fire** — peer mode beats adversarial-both on joint surplus.
4. **K30 fires** — the employer still takes most of it, cooperative or not.
5. **K31 does not fire** — packages win once the protocol stops handing the
   sequential arm a free ratchet.

## A5.5 The standing risk

Four instruments have now died in this study, each flattering whichever side I
was leaning toward at the time: K17's biased arm, arm G's missing acceptance
check, the probe arm's dropped counter, and the single-shot inference above. The
correction is A5.2's assertions, not more care. Any v6 number produced by an arm
that has not passed them is not reportable.

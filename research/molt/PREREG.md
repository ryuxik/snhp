# PREREG — Molt Season (salary negotiation: slow talks vs. instant offers)

*Written 2026-07-25. Committed BEFORE any simulation output existed. This file
is binding and will not be edited after the first run; corrections go in
RESULTS.md as amendments with their own timestamps.*

**The question.** A crew of space crabs works a shipyard. Once a year, after
the bonus lands, comes **molt season**: every crab decides whether to grow into
a bigger shell here or carry it somewhere else, and the Works decides what it
will pay to keep each one. Today that is a sequence of meetings spread over
weeks. The alternative on test: one sitting, a full package, math instead of
rounds.

**Measured in two currencies: money and calendar days.** Both sides of both.

---

## 0. Why this experiment can fail, and the trap it is built to avoid

The obvious way to run this study is to make slow negotiation expensive and
then announce that fast negotiation is better. That is not a finding, it is an
assumption restated. Two guards, both registered here:

1. **The zero-clock ablation is a first-class arm, not a robustness check.**
   Every result is reported twice: with the calibrated clock, and with every
   delay cost set to exactly zero. If the advantage lives only in the first, we
   say so in those words and the headline becomes a claim about our
   calibration.
2. **Approval friction is applied to BOTH arms.** An instant agreement still
   needs a signature. The fast arm gets *one* approval hop, not zero; the slow
   arm gets one per instrument, because that is what sequential bargaining
   actually costs. The speed advantage must come from collapsing hops, never
   from exempting the product from bureaucracy.

A third guard is structural: the slow arm is run **twice** — once with a
hand-rolled human ladder, once with the real SNHP engine restricted to one
issue at a time (`negotiate_turn`). If the engine-on-a-leash arm matches the
bundle arm, then whatever we measured was our own strawman, and K3 fires.

---

## 1. The world

One Works, `N_CRABS = 40` crabs, one molt season, `S = 12` seasons per run
(seasons are independent draws; the Works is not learning across them — no
reputation dynamics are claimed or modelled).

### 1.1 Crabs

Each crab `i` has a **specialization** drawn from the table below. The
specialization sets the outside market and what losing the crab costs the Works;
individual draws vary within it.

| specialization | share | salary $ (lognormal median) | replacement cost ρ·S | outside-offer rate | vacancy days |
|---|---|---|---|---|---|
| HULL-WELDER (frontline skilled) | 0.30 | 74,000 | 0.45 | 0.28 | 34 |
| BRINE-CHEMIST (technical professional) | 0.22 | 118,000 | 0.80 | 0.34 | 52 |
| NAV-PILOT (scarce technical) | 0.16 | 146,000 | 1.10 | 0.46 | 68 |
| CARGO-BROKER (revenue-facing) | 0.18 | 102,000 | 0.90 | 0.42 | 44 |
| SHELL-SMITH (crew lead / manager) | 0.14 | 158,000 | 1.60 | 0.24 | 74 |

`ρ` (replacement cost as a multiple of salary) is anchored on the Gallup/SHRM
range of 0.5–2.0× salary, with the published shape — ~0.4 frontline, ~0.8
technical professional, ~2.0 leaders — compressed slightly toward the middle
because our horizon is 3 years, not indefinite. Vacancy days are anchored on the
SHRM median time-to-fill of 44 days, scaled by scarcity. **These are trade-press
and consultancy benchmarks, not peer-reviewed estimates**; ρ is swept over
{0.5×, 1.0×, 1.5×} of the table, and the sweep is reported whether or not it
changes a verdict.

Within specialization, each crab draws:

- `perf` ∈ [0,1], performance percentile (uniform)
- `tenure` j ∈ {1..9} years, geometric-ish, mean ≈ 3.4
- `w` — priority weights over the five issues, Dirichlet(α = 1.4) over
  (base, title, bonus, berth, deepwater). **This heterogeneity is the whole
  reason multi-issue bargaining can beat single-issue bargaining.** α = 1.4 is
  moderately dispersed; swept at {0.8 (very idiosyncratic), 1.4, 4.0 (nearly
  identical crabs)}. At α = 4.0 the bundling advantage *should* shrink toward
  zero; if it does not, our logrolling gain is not coming from heterogeneity
  and something is wrong. **Registered as a diagnostic with a stated expected
  direction.**
- `move_cost` — lognormal, median 0.9 months of salary (relocation, lost
  station-specific standing, risk); redrawn each season
- `outside` — with prob `p_out` (table, scaled by `perf`), an outside offer at a
  premium ω ~ Normal(12%, 6%) truncated at −2%, **expiring after `D_exp` days**,
  `D_exp` ~ 10 ± 4 (trade-press: top candidates stop collecting offers ~10 days
  in; a third of withdrawals are "accepted another offer")

### 1.2 The five issues

| issue | options | what it costs the Works | who values it |
|---|---|---|---|
| **base** | +0/3/6/9/12% | permanent: PV over horizon **× (1 + σ_peer)** | everyone, in cash |
| **title** (molt to a bigger shell) | hold / promote | band-compression + 2% implied salary drift | ambitious crabs, hugely |
| **bonus** (retention, one-time) | 0 / 1 / 2 months | cash, once | liquidity-constrained crabs |
| **berth** (shift + remote-tide flexibility) | standard / flexible | coverage cost, small | crabs with high `w_berth` |
| **deepwater** (growth assignment) | no / yes | current-project productivity dip | high-`perf` young crabs |

`σ_peer = 0.30` — the **peer-spillover** on base pay: a raise leaks to band
peers through comparison and the next comp cycle. This is what makes base the
*hardest* ask and creates the logroll: the Works will happily trade two cheap
things for one expensive one. Swept {0, 0.15, 0.30, 0.60}. **The direction
matters: σ_peer = 0 makes base cheap and should shrink the bundling gain.**
Horizon = 3 years, discount 7%/yr both sides (crabs are more myopic in reality;
a *shorter* crab horizon would make cash-now cheaper to buy them with, so the
symmetric choice is conservative for the "bundling beats cash" claim).

### 1.3 The clock

Calendar time is the second currency. Registered values:

| parameter | value | basis |
|---|---|---|
| meeting-to-meeting delay | lognormal, median **9 days**, σ_log 0.55 | calendar friction: scheduling a manager + the crab |
| approval hop (anything above manager discretion) | **7 days**, +3 if above the band | HR/comp/skip-level sign-off |
| manager discretion | ≤ 3% base, ≤ 1mo bonus, berth only | the Works' standing delegation |
| manager time per meeting | **1.5 h** at $145/h loaded | — |
| crab distraction | **8%** of daily output while a negotiation is open | swept {0, 4, 8, 16} |
| attrition hazard while open | `0.9%/day` base, `×3.1` with a live outside offer | — |
| offer expiry | `D_exp` days (§1.1) — after that the crab's alternative is gone | — |

Everything in this table is set to zero (or infinity, for expiry) in the
**zero-clock** condition. Nothing else changes between the two conditions.

---

## 2. The arms

| arm | who negotiates, how | clock |
|---|---|---|
| **A — SIGN IT** | no negotiation; the Works' opening offer is accepted | 1 day, 0 meetings |
| **B — SLOW TALKS** | hand-rolled human bargaining: anchor on base, concede down a ladder, one further issue per meeting, ≤ 5 meetings | full calendar |
| **C — SLOW ENGINE** | real `negotiate_turn`, crab side, **one issue at a time**, same agenda and calendar as B | full calendar |
| **D — ONE SITTING (crab)** | real `negotiate_bundle`, crab side, all five issues, ≤ 3 rounds in one session | 1 day + 1 approval hop |
| **E — ONE SITTING (Works)** | the engine on the **Works'** side, crab bargains as in B | 1 day + 1 hop |
| **F — BOTH SIDES** | both sides on the engine | 1 day + 1 hop |

A is the control that most crabs actually pick (~55% of workers accept the first
offer without negotiating). B is the honest incumbent. C is the parity check
that keeps us honest. D is the product. E and F answer "who should buy this."

**Protocol parity rules, fixed now:** identical seeds, identical crab draws,
identical Works preferences and identical Works concession budget across all arms.
The Works' willingness to concede is computed from the same NPV function
everywhere. No arm gets more rounds of *substance* than another: B and C get up
to 5 meetings, D/E/F get up to 3 engine rounds — the slow arms get **more**
chances to reach agreement, not fewer.

---

## 3. Metrics

Per crab-season, in dollars over a 3-year horizon:

- `crab_$` — PV of the package to the crab (cash + the crab's own valuation of
  non-cash terms), net of move costs if it leaves
- `works_$` — Works NPV: productivity retained − concessions (with spillover) −
  manager hours − distraction − replacement cost if the crab leaves
- `joint_$` = crab_$ + works_$ (the deadweight measure)
- `days` — calendar days from first contact to signature
- `mgr_h` — manager hours
- `left` — crab departed
- `agreed` — a package was agreed

Money is reported **relative to arm A (SIGN IT)**, per crab-season. Arm A is the
zero.

---

## 4. Kill conditions (bidirectional, binding)

The bar throughout is **2% of annual salary** (≈ $2,200 at the population mean).
A gap below the bar is "no effect" no matter how many stars it has.

**K1 — TAUTOLOGY KILL.** In the **zero-clock** condition, if D's joint surplus
advantage over B is < 2% of salary, then instant negotiation creates no value
absent our delay assumptions. *Consequence if it fires:* the demo may not claim
that speed creates value on its own; the money claim is deleted and the page
carries only the time claim with our calibration printed next to it.

**K2 — NO-MONEY KILL.** With the clock on, if D beats B by < 2% of salary on
*both* `crab_$` and `works_$`, the demo drops all money claims and becomes a
stopwatch. *Fires ⇒ the headline "how much the company loses" is unsupported.*

**K3 — STRAWMAN KILL.** If arm C (engine, single-issue, slow) lands within 2% of
salary of arm D on joint surplus, then bundling contributed nothing and arm B
was simply a badly-played hand. *Consequence:* we report that the win is
protocol, not product, and the claim becomes "negotiate all of it at once,"
which is advice, not software.

**K4 — CAPTURE SPLIT (no direction registered).** Report the crab/Works split of
the joint gain in arms D, E, F. If, in F, one side captures > 70% of the joint
gain, every piece of demo copy addressed to the *other* side is rewritten. We
register no prediction about which side that is, but see §5.

**K5 — SPEED IS NOT FREE.** If D's agreement rate is lower than B's by > 3
percentage points, or D's departure rate is *higher* by > 2pp, then speed costs
deals and that goes in the headline alongside the savings.

**K6 — HETEROGENEITY DIAGNOSTIC.** At α = 4.0 (nearly identical crabs), D's
advantage over C should fall by at least half. If it does not, the logrolling
story is not the mechanism, and RESULTS must say the mechanism is unidentified.

**K7 — THE COMPANY-LOSES CLAIM.** The demo's premise is that slow talks cost the
*employer*. If `works_$` under B is *higher* than under D (the Works profits from
slowness — e.g. by grinding crabs down over weeks), the premise is false and the
demo is re-framed to say so.

---

## 5. On-record predictions (mine, before running)

Recorded so they can be refuted rather than quietly reinterpreted.

1. **The largest component of the slow arm's loss is mis-allocated concession,
   not elapsed time.** I predict the Works pays *more permanent base salary* under
   B than under D while the crab ends up *worse off*, and that this channel
   exceeds manager hours + distraction + attrition combined.
2. **The Works captures the majority of the joint gain in F** (the rent study's
   K16 found the landlord took ~90% of the analogous gain). I predict > 55% here,
   but weaker than 90% because the crab's outside option is sharper than a
   tenant's.
3. **K1 will NOT fire** — bundling wins on money with the clock switched off.
4. **K5 will not fire**; agreement rates will be *higher* under D.

If (1) is refuted, the demo's "the company loses" framing must be rebuilt on
whatever channel actually dominates.

---

## 6. Seeds and stopping rule

- Registered seeds: **7, 11, 23, 31** (main), **101** held out for one
  confirmatory run after all analysis is frozen.
- Every cell: 40 crabs × 12 seasons × 4 seeds = **1,920 crab-seasons per arm**.
- Sweeps (ρ, σ_peer, α, distraction, meeting delay) are run on seed 7 only and
  reported as sensitivity, never as headline.
- **Stopping rule:** when the kills above have been evaluated on the main seeds
  and the confirmatory seed, building stops. No mechanism is added after seeing
  a kill fire in order to un-fire it. If a kill fires, it is reported; if we then
  build something new, it is registered as a new amendment with its own kills and
  its results are labelled exploratory.

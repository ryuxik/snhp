# The buyer's agent — results

*Incremental, honest log. Every delta carries a 95% CI; no win is claimed when
the CI includes zero. Pairing is keyed on buyer identity, never on policy.
Seeds: master 20260710 unless noted. No LLM is invoked anywhere in this package
— every strategy is algorithmic and byte-deterministic.*

## What "buyer regret" means here (the metric that was missing)

For sellers we had a Pareto frontier and "dollars left on the table." The buyer
had no such number. Defined here:

- **buyer_frontier** = the max true-dollar surplus a buyer's agent could realize
  over its whole strategy space S (disclosure policy × which merchants × accept-
  now/wait × commit), holding the merchants' fixed mechanisms and the buyer's
  true values constant.
- **buyer regret** = buyer_frontier − realized. `>= 0` by construction (the
  agent's actual strategy is a point in S), verified in tests.
- We report the frontier two ways: **unrestricted** (S includes the misreport /
  "liar" battery) and **attested** (S collapses to the honest report, because an
  attested merchant only prices on verified truth). The gap between them is the
  honest crux: how much of the "reachable" buyer surplus is reachable only by
  gaming.
- **Attestation is a MECHANISM constraint, not an experiment setting.** An
  attested disclosure is a *verified-true* report: `BuyerAgent.disclose(attested=
  True)` sends the buyer's true wtp/walk **regardless of the agent's disclosure
  policy** (a lying policy's misreport factor is ignored under attestation).
  There is therefore no such thing as an "attested lie" — a liar who flips the
  attested bit to be served by an attested-only merchant is forced to send the
  truth, so it realizes exactly the honest outcome and can never beat the
  attested (honest) frontier. This is why `regret = 0 under attestation` is
  enforced by the mechanism, not by the experiment happening to run only
  `policy='honest'`. (Regression-tested: `test_lying_policy_under_attestation_
  cannot_beat_frontier` — every liar policy realizes ≤ the attested frontier,
  true regret ≥ 0 by construction; the `max(0,·)` floor is then a pure numeric
  guard, not a mask over a negative.)

Modeling choice (stated for attack): the population faces a **shared** merchant
board (one machine, many buyers, no stock depletion between them). This makes
each buyer's frontier well-defined and identical across policy arms for the same
identity — exact pairing, the rigor rule. It deliberately drops vend's stock-
competition dynamics; "is the buyer near its own frontier" is a different
question from "do buyers congest a machine," and this package measures the
former.

---

## B1 — plumbing + the first per-consumer receipt

Built: the `Merchant` protocol (`buyer/merchant.py`), a `VendMerchant` adapter
over `vend.scenario.nash_quote` (read-only import; a `ToyMerchant` stands in
with zero vend dependency), a `BuyerAgent` that discloses + accepts/declines,
and a per-uid `BuyerLedger`.

Verified (tests):
- **Adapter matches vend exactly.** For 60 buyers on a shared seed, `VendMerchant.quote`
  reproduces `nash_quote`'s outcome, unit price, and both margin terms to 1e-9.
- **Value model in sync with vend** to 1e-12 (guarded by a test, not an import —
  the buyer package can outlive vend).
- **Ledger conservation:** Σ per-uid lifetime surplus == aggregate consumer
  surplus, exactly.
- **Never worse than walking away:** the agent declines any quote below its best
  sticker/bodega option, for every buyer tested.

## B2 — buyer_frontier + regret (single merchant), n = 4000

| arm | surplus/buyer | regret/buyer | frontier captured |
|-----|---------------|--------------|-------------------|
| **Unrestricted frontier** (liar battery in S), frontier = **$3.82** | | | |
| naive sticker-accepter | $1.77 | $2.05 | 46% |
| honest agent | $2.37 | $1.46 | **62%** |
| **Attested frontier** (S = honest only), frontier = **$2.37** | | | |
| naive sticker-accepter | $1.77 | $0.60 | 75% |
| honest agent | $2.37 | **$0.00** | **100%** |

- Δsurplus (honest agent − naive) = **+$0.60/buyer**, CI95 [0.587, 0.605], **significant**.
- Δregret (honest agent − naive) = **−$0.60/buyer**, CI95 [−0.605, −0.587], **significant**.

### Buyer-regret verdict (the honest test)

- **Under our attested mechanism, a truthful buyer's agent sits EXACTLY at its
  frontier — regret is 0, and this is MECHANISM-enforced.** Attestation means the
  disclosed value is *verified true*, so an attested report can only be the
  honest one — a lying policy that flips the attested bit is forced to send the
  truth and realizes the identical outcome (regression-tested). There is
  therefore no strategy in the attested space that beats honest disclosure *by
  construction*, not because the experiment only tried honest. So the surplus the
  buyer gets is the most reachable, not the seller's leftover generosity. This is
  the strong form of "it's a real buyer's tool, not a seller's tool wearing a
  buyer's badge." (Earlier drafts of this doc stated regret-0 as if it might be
  an artifact of the honest-only experiment; the disclosure primitive now binds
  honesty under attestation, which *strengthens* the claim from "we observed 0"
  to "0 is the only reachable value.")
- **Without attestation, the honest agent leaves ~38% on the table** ($1.46
  regret against a $3.82 frontier) — but that residual is reachable ONLY by
  misreporting (the anchoring/liar strategies). The mechanism's job is to
  foreclose exactly those strategies; attestation collapses the frontier onto
  honesty and drives truthful regret to zero. So the "high regret" of a truthful
  agent in the unattested world is not a failure of the buyer's tool — it is the
  value of the exploit that attestation removes, now measured in dollars
  (~$1.46/buyer).
- Against the naive sticker-accepter, the agent is unambiguously better in both
  regimes: **+$0.60 surplus, −$0.60 regret per buyer**, CI excludes zero. Buyer
  agency lowers buyer regret vs the naive baseline — the pre-registered
  prediction holds.

## B3 — multi-merchant SHOP and TIME (n = 4000)

`buyer/strategies.py`: **shop** (query k merchants, take the best quote) and
**time** (defer one period for a forecast better-priced state), with the
transfer-vs-growth accounting (`joint_value = value − qty·c_eff`; price only
splits it, so **Δjoint isolates growth from transfer**).

### SHOP (3 price-competing merchants) vs single-merchant

Merchants here are identical in cost/stock and differ ONLY by the operator's
calibration-noise sticker — pure price competition, so this is a clean transfer
test (allocative/spoilage growth is deliberately kept out; it is the TIME/COMMIT
story).

| | surplus/buyer | regret/buyer | captured |
|--|--|--|--|
| single-merchant honest | $2.51 | $1.64 | 60% |
| **shop across 3** | **$3.43** | **$0.71** | **83%** |

- Δsurplus shop − single = **+$0.93/buyer**, CI95 [0.89, 0.96], significant.
- Transfer-vs-growth: **Δbuyer/deal +$0.60, Δjoint/deal −0.00 (CI [−0.0005,
  0.0004] — includes zero).** The pie is unchanged; every dollar the buyer wins
  by shopping comes out of the winning merchant's margin. **SHOP is a pure
  TRANSFER — "the buyer's agent disciplines the merchant."** Exactly the
  pre-registered prediction.

### TIME (defer for the end-of-day markdown) vs buy-now

The near-future state worth waiting for is the end-of-day perishable **markdown**:
perishables expiring tonight have c_eff = salvage << cost, so the Nash engine
marks them down hard. The agent forecasts the markdown with its probability and
does not know its own realization; regret is the price of forecasting.

- Defer rate **0.83**; Δsurplus time − buy-now = **+$0.11/buyer**, CI95 [0.09,
  0.13], significant; regret falls $0.23 → $0.12.
- Transfer-vs-growth: **Δbuyer/deal +$0.24, Δjoint/deal +$0.57 (CI [0.52, 0.62]
  — GROWTH).**

**This DEVIATES from the pre-registration (which lumped time with shop as a
transfer), and the deviation is the interesting finding.** The state a timing
buyer defers for is precisely the one where the merchant would otherwise eat a
**spoilage** loss; buying the would-spoil unit converts stock worth only salvage
into a real sale, so Δjoint is positive — genuine welfare growth, not a transfer.
The honest correction to the pre-registration: the transfer-vs-growth axis is
**not** "timing vs commitment"; it is "**does the deferred-for state avoid a
deadweight loss (spoilage)?**" A timing strategy that merely waited for a lower
off-peak price on a good that sells either way WOULD be a transfer; ours waits
for the markdown, which is spoilage-avoidance and therefore growth — the same
family as commit.

## B4 — Wallet (portable identity) + COMMIT (n = 4000)

`buyer/wallet.py` + `buyer/strategies.commit_strategy`. The agent guarantees to
absorb the would-spoil perishable stock the merchant is otherwise stuck
salvaging; in return the units are priced off the salvage floor with the
displacement uncertainty removed. A credible commitment converts stock worth
only salvage into a real sale, so it GROWS the pie by exactly the expected
spoilage loss avoided, `p_spoil·(value − salvage)`, split 50/50 by Nash, and
zeroes the merchant's payoff variance. Credibility is what a human lacks; the
Wallet's `trusted_frac` (attestation buys half, a fulfilled track record earns
the rest) is how much of the commitment a merchant will bank.

At p_spoil = 0.40:

| wallet state | trusted | joint growth | buyer share | merchant var removed |
|--|--|--|--|--|
| attested **newcomer** | 0.50 | **+$1.54** CI [1.52, 1.55] | +$0.77 | $1.67 |
| **proven** (6 kept commits) | 0.94 | **+$2.90** CI [2.87, 2.93] | +$1.45 | $3.15 |

- **COMMIT grows joint surplus** (Δjoint > 0, CI excludes zero) — the
  pre-registration holds. The split is exactly 50/50: ΔBuyer == ΔMerchant ==
  Δjoint/2, and the merchant also sheds real payoff variance ($1.67–$3.15 of
  risk). **Both agents grow the pie.**
- **The Wallet compounds.** Six fulfilled commitments lift trusted_frac 0.50 →
  0.94, and the growth banked nearly doubles ($1.54 → $2.90). Reliability is the
  asset.
- **The Wallet is portable — the moat.** Carrying a proven wallet to a
  brand-new merchant earns **+$0.71/buyer** more than arriving fresh (CI [0.70,
  0.72], significant). Leverage earned at one merchant is spent at the next;
  "your agent already negotiated, on your side, before you tapped" becomes "and
  it arrives with a reputation."
- Note for B5: even at full trust, the merchant's share of the commit is
  `Δjoint/2 >= 0` — the Nash split never pushes it below its salvage
  participation floor. That is the property the monopsony audit stress-tests.

## B5 — COORDINATE + the buyer-side monopsony audit (n = 4000)

`buyer/strategies.coordinate`: a cluster of K buyers aggregates its forward
demand for the merchant's scarce, spoil-risk stock. Each cleared would-spoil
unit creates welfare `p_spoil·(value − salvage)`; the cluster's power is (a)
**matching** the scarce units to the members who value them most, and (b)
**bargaining** the price down toward the merchant's floor.

### Coordinate GROWS surplus (matching efficiency)

| K (stock) | coord growth/buyer | independent commits | Δ (coord − indep) |
|--|--|--|--|
| 2 (1) | $1.16 | $0.97 | **+$0.19** CI [0.18, 0.21] |
| 5 (2) | $1.01 | $0.76 | **+$0.25** CI [0.23, 0.26] |
| 10 (5) | $1.22 | $0.97 | **+$0.25** CI [0.24, 0.26] |
| 20 (10) | $1.23 | $0.97 | **+$0.26** CI [0.24, 0.27] |

Coordination beats uncoordinated (independent) commits by $0.19–$0.26/buyer, CI
excludes zero, at every K — because a coordinating cluster routes the scarce
would-spoil stock to its highest-value members, while independent buyers race
for it and often aren't the ones who value it most. **Coordinate grows joint
surplus — the pre-registration holds.**

### The monopsony audit (pre-registered, binding) — the RealPage mirror

The RealPage line is a SELLER cartel pushing price UP, extracting consumer
surplus and destroying welfare via reduced quantity. The buyer-side mirror is a
buyer cluster pushing price DOWN; the binding check is that it must not (A) push
total surplus below the independent baseline, nor (B) extract below the
merchant's participation floor.

| check | result |
|--|--|
| **A** — coordination never below independent commits | **PASS** (Δ ≥ 0 at all K) |
| **B** — merchant margin ≥ 0 at fair AND maximal (extraction=1.0) push | **PASS** (min margin = 0.0 exactly at the floor, never below) |
| **D** — over-reach (demand below salvage) is self-defeating | **PASS** — 100% of over-reaching clusters have the merchant refuse; the units then spoil (welfare destroyed), so the cluster gets *less* |

**VERDICT: PASS.** Under our mechanism — Nash bargaining with the merchant's
salvage/opportunity-cost as the disagreement point — buyer coordination
redistributes toward buyers (at maximal push, the merchant sits exactly at its
salvage floor and buyers capture ~all the growth) but **cannot go below that
floor**: any sub-salvage demand is rejected, the stock spoils, and total welfare
falls, so a rational cluster never does it. The participation floor is
load-bearing, and total surplus is non-decreasing. This is the honest,
antitrust-shaped finding: the same disagreement-point discipline that stops a
seller from harvesting a captured buyer stops a buyer cartel from extracting a
captive seller.

**Honest scope limit:** the audit tests UNIT-LEVEL participation (per-transaction
opportunity cost). It does not model FIRM-LEVEL viability — a merchant held at
zero margin on *all* stock could still exit over fixed costs. A production
monopsony audit would add a going-concern margin floor; here the floor is the
per-unit salvage value, which is the correct reservation for the spoil-risk
stock the commit clears.

## Human regime vs agent-mediated regime (subsumes task #60)

The four strategies ARE the agent-mediated behaviors. Run them with friction → 0
and fast churn to get the target-world numbers.

- **HUMAN** — quote-friction $0.30 (a mental switch-cost per negotiated
  transaction) and no churn (sticky to one merchant): honest negotiation at a
  single machine.
- **AGENT-MEDIATED** — friction $0 (a quote is evaluated instantly) and fast
  churn (the agent queries every merchant): shops all 3.

Both graded against the same yardstick — the agent-mediated frontier (shop
across 3, friction 0), **$4.14/buyer**.

| regime | buyer surplus | buyer regret |
|--|--|--|
| human (friction $0.30, 1 merchant) | $2.24 | $1.91 |
| **agent-mediated (friction $0, shop 3)** | **$3.43** | **$0.71** |

- Δsurplus agent − human = **+$1.20/buyer**, CI95 [1.16, 1.23], significant.
- Moving from the human regime to the agent-mediated regime **cuts buyer regret
  by ~63%** ($1.91 → $0.71) and **lifts realized surplus ~53%** ($2.24 → $3.43).
  Friction and stickiness are most of what keeps human buyers off their
  frontier; removing them (which is exactly what a buyer's agent does) is where
  the consumer-side value of the whole system shows up.

---

## Verdicts (the honest bottom line)

1. **Are buyers near their frontier under our mechanism?** **Yes, when it is
   attested — exactly at it (regret 0), and the mechanism ENFORCES it.**
   Attestation = a verified-true disclosure, so an attested report can only be
   honest; a lying policy under attestation is forced to send the truth and
   cannot beat the honest frontier (regression-tested — true regret ≥ 0 by
   construction, not by a `max(0,·)` floor). The buyer's-agent surplus is the
   most reachable, not the seller's leftover generosity. Without attestation a
   truthful agent leaves ~$1.46/buyer on the table, but that residual is
   reachable only by misreporting (the anchoring exploit), and attestation is
   precisely what forecloses it — so the "gap" is the dollar value of the
   exploit removed, not a failure of the buyer's tool. Against the naive
   sticker-accepter the agent is strictly better everywhere (CI excludes zero).

2. **Transfer vs growth split.** **SHOP is a pure transfer** (Δjoint ≈ 0, CI
   includes zero — "the buyer's agent disciplines the merchant"). **COMMIT and
   COORDINATE grow the pie** (Δjoint > 0, CI excludes zero — variance reduction
   and spoilage-avoidance are real; "both agents grow the pie"). **TIME
   deviated from the pre-registration** (predicted transfer, measured growth):
   the state a timing buyer defers for is the end-of-day markdown, which is
   spoilage-avoidance — so the true axis is not "timing vs commitment" but
   "does the deferred-for state avoid a deadweight loss (spoilage)?"

3. **Human vs agent-mediated headline.** Regret $1.91 → $0.71 (−63%), surplus
   $2.24 → $3.43 (+53%), +$1.20/buyer, CI excludes zero.

4. **Monopsony audit: PASS.** Buyer coordination cannot push total surplus down
   or extract below the merchant's participation floor; the disagreement-point
   discipline is symmetric.

All deltas carry 95% CIs; no win is claimed when a CI includes zero. Pairing is
keyed on buyer identity. No LLM is invoked; every result is byte-deterministic
on the seed. Ledger conservation (Σ per-uid surplus = aggregate CS) holds
exactly in every run.

---

## preflearn — onboarding + online preference learning → profitable silent negotiation (n = 200)

*Module `buyer/preflearn.py`, artifact `buyer/results-preflearn.json`, tests
`buyer/tests/test_preflearn.py`. Built ON TOP of the two existing subsystems, not
reimplementing them: the true buyers are vend's demand process
(`buyer.world.draw_vend_population` → `vend.world.sample_consumer`: per-SKU
first-unit WTP lognormal around `WTP_MU[sku]`, `WTP_SIGMA = 0.30`), and the
negotiation is `vend.scenario.nash_quote` via the `VendMerchant` adapter — we
feed a DISCLOSED estimate into `merchant.quote(...)` exactly as an honest
disclosure would flow. Discount-only (floor..list) is enforced by the engine and
regression-tested. Seed 20260710; prior fit on a DISJOINT population (seed 777).*

### The claim (pre-registered, before the numbers existed)

Onboarding elicitation + online revealed-preference learning recovers enough of a
buyer's utility that the SNHP negotiation on the LEARNED curve captures a large
fraction of the surplus a FULL-INFORMATION oracle captures — after a SMALL
onboarding budget `N` + a few purchases `M` — and the explicit consideration-set
(cart) signal materially accelerates this, because it makes the problem LOCAL:
you only need the utility around the current cart, not the global curve.
Predicted signs: curve error ↓ in `N` and `M`; capture ↑ in `N` and `M`;
cart-signal lift > 0, largest at small `N`; tail types and drift degrade it.

### What is learned, and what stays on the buyer's side

We learn the per-SKU first-unit WTP vector (the decay `QTY_DECAY=0.55` is the
known structural constant). The posterior is a per-SKU grid over log-WTP (a
factorized / mean-field posterior — exact and degeneracy-free for the per-SKU
signals; cross-SKU pairwise/pick updates are mean-field). Onboarding is ACTIVE:
each step picks the query (a WTP probe or a pairwise "A vs B at these prices")
maximizing expected posterior relative-variance reduction over the target SKUs.
Online updates come from the buyer's consideration-set PICK at the board. The
learner ingests ONLY answers and choices — never the true WTP (structural: the
true WTP lives on `TrueBuyer`; the learner completes onboarding when driven by a
buyer object that has no `wtp` attribute — `test_no_ground_truth_leak_*`). Only
the negotiation runs on the estimate; the curve stays on the buyer's side.

### Metric choice, stated for attack

The robust headline is **JOINT (efficiency) surplus capture**: realized welfare
of the transaction (`value − qty·c_eff`), normalized between the NO-INFO
population-prior agent (0) and the FULL-INFO oracle (1) as a ratio-of-sums
`Σ(learned − noinfo) / Σ(oracle − noinfo)`, paired-bootstrapped over buyer
identity. Joint surplus is well-behaved: honest-true disclosure yields the
efficient trade, so `oracle − noinfo` is positive in aggregate (+$0.40/buyer).
**Buyer surplus is NOT a clean fraction-of-oracle** and we do not report it as
one: because the merchant prices AGAINST the disclosure, honest-true disclosure
is a FAIR reference, not the buyer's per-buyer maximum — strategic
under-disclosure beats it. Aggregate `oracle − noinfo` for BUYER surplus is
NEGATIVE (−$0.15/buyer), and on the 79/200 buyers where info genuinely helps
(below-population-mean types who would otherwise overpay or lose the deal),
learned buyer-surplus "capture" is 112–136% — it EXCEEDS the honest oracle,
because an imperfect (prior-shrunk) estimate under-discloses and the price-taking
merchant rewards that. So for the consumer-facing number we report
**profitability** ($ saved vs walk-away, deal rate), not a buyer-surplus fraction.

### Headline — JOINT surplus capture, cart signal ON (fraction of oracle)

|         | M=0 (no purchases) | M=3 | M=10 |
|---------|--------------------|-----|------|
| **N=0** (cold start) | 0% (= prior) | 57% | 69% |
| **N=3** | 55%  [0.39, 0.68] | 76% | 83% |
| **N=5** | 60%  [0.45, 0.73] | 78% | 82%  [0.70, 0.90] |
| **N=10**| 80%  [0.71, 0.87] | 90% | 91% |
| **N=20**| 81%  [0.71, 0.89] | 89% | 93% |

The fundable sentences, all with 95% CIs excluding zero:
- **60% of oracle surplus after 5 onboarding questions** (CI [0.45, 0.73]);
- **80% after 10 questions** (CI [0.71, 0.87]);
- **82% after 5 questions + 10 purchases** (CI [0.70, 0.90]);
- **69% after 0 questions + 10 purchases** (pure online cold-start, CI [0.59, 0.79]).

Capture at `(N=0, M=0)` is exactly 0 by construction (learned == prior), and rises
monotonically in both axes (asserted in `test_capture_zero_at_origin_and_rises`).

### The cart signal: a small-budget accelerator, honestly bounded

WITH the consideration set the same onboarding budget is spent only on the K=3
SKUs the buyer is shopping, and the negotiation is Intent-restricted to them;
WITHOUT it the budget spreads over all 8 SKUs and the merchant may quote any of
them. JOINT capture, cart ON minus OFF (paired bootstrap of the aggregate
capture difference):

| N (M=0) | lift | 95% CI | sig |
|---------|------|--------|-----|
| 3  | +0.268 | [0.09, 0.43] | ✔ |
| 5  | +0.314 | [0.13, 0.49] | ✔ |
| 10 | +0.269 | [0.15, 0.39] | ✔ |
| 20 | +0.106 | [0.01, 0.20] | ✔ |

At small onboarding budget the cart signal lifts capture by **+27 to +31 points**
(e.g. N=5: 60% vs 29%). Its value SHRINKS as the budget grows (both arms
converge) and, honestly, goes slightly NEGATIVE once many purchases accumulate:
at `N=0, M=10` the lift is **−0.10 [−0.17, −0.05]** — with no onboarding, the
Intent restriction removes the merchant's SKU flexibility before the estimate is
good, and the global arm's 8-way pick signal is richer than the local 3-way.
So the honest reading: **the cart signal buys down the onboarding budget — it is
worth ~5–7 fewer questions in the small-N regime — but it is not free flexibility,
and it does not compound with heavy online history.**

### Convergence rate

Curve error (mean relative-L1 of the posterior mean vs true WTP on the
consideration set — measurement only; the learner never sees truth):

| N | 0 | 3 | 5 | 10 | 20 |
|---|---|---|---|----|----|
| cart ON  | 0.222 | 0.193 | 0.159 | 0.128 | 0.106 |
| cart OFF | 0.222 | 0.206 | 0.192 | 0.147 | 0.112 |

Error roughly halves by N=20; the cart signal converges faster at small N (0.159
vs 0.192 at N=5). `test_curve_error_decreases_with_onboarding` guards monotonicity.

### Profitability — is the silent negotiation actually profitable? (cart ON)

The buyer accepts only quotes that beat its walk-away, so the negotiation can
never make it worse. Mean $ saved vs walking, and the fraction of interactions
that strike a deal:

| N (M=0) | $ saved vs walk | 95% CI | deal rate |
|---------|-----------------|--------|-----------|
| 0  | $0.75 | [0.65, 0.85] | 72% |
| 3  | $0.88 | [0.79, 0.98] | 94% |
| 5  | $0.80 | [0.72, 0.88] | 96% |
| 10 | $0.86 | [0.79, 0.93] | 98% |

The negotiation saves ~$0.8–1.0/deal. The catch is the **deal rate at N=0: only
72%** — with no onboarding the mis-estimate over/under-prices and ~1 in 4 deals
collapses to the walk-away. Onboarding (or ~3 purchases) fixes this: deal rate →
94–99%. **This is the number that decides whether the demo is real: a cold-start
buyer with zero onboarding loses a quarter of its deals; ~3 answers or ~3
purchases are enough to make the silent negotiation reliably strike.**

### Honest failure modes (where it breaks)

- **Atypical / tail types** (top third by distance from the prior): JOINT capture
  56% [0.28, 0.75] at N=5 vs 60% [0.30, 0.80] for typical types — only ~4 points
  worse. Active elicitation corrects a wrong prior within a few questions; the
  prior being mis-centered is not the failure mode.
- **Noisy / inconsistent answers (3× answer noise):** capture at N=10 drops
  80% → **57%** [0.42, 0.69]. Graceful but real — a jittery answerer needs more
  questions to reach the same place.
- **Non-stationary preferences (taste drifts, σ=0.15/step during the online
  phase):** capture at `N=5, M=10` roughly HALVES, 82% → **42%** [0.29, 0.53]. A
  naive forgetting factor (posterior widening each step) does **not** rescue it —
  it is monotonically WORSE (38% at α=0 → 13% at α=0.15), because it discards the
  onboarding anchor faster than the weak online pick signal can re-anchor.
  **Tracking drift needs a stronger online signal or an explicit drift model;
  the demo should assume roughly stationary tastes within a session.**
- **Cold start (N=0):** capture 0% at M=0 (= prior), recovering to 57% (M=3) and
  69% (M=10) purely from consideration-set picks — pure online works, just slower,
  and with the 72% deal-rate caveat above until the first few interactions land.

### Verdict for the demo

The demo can sit on real, measured learning: **~5 onboarding questions + a few
purchases recover ~60–82% of full-information joint surplus (CI-backed), the
silent negotiation saves ~$0.8/deal and — once past cold start — strikes 95–99%
of the time, and the consideration-set signal is a genuine small-budget
accelerator worth ~5–7 questions.** The honest asterisks: it needs *some*
onboarding to clear the 72%→99% deal-rate cliff, buyer-surplus is not a clean
fraction-of-oracle (report $ saved instead), the cart signal does not compound
with heavy online history, and drifting tastes halve it. None of these is fatal
to a fundraising demo; all of them should be said out loud.

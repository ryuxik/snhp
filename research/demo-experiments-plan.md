# Experiments-into-demo plan — CEO + CMO consult synthesis (2026-07-18)

Inputs: research/divorce-effectiveness-survey.md (6-stream literature),
divorce/RESULTS.md (owned numbers), CEO-advisor memo + CMO consult (session
transcript). The two seats converged on structure; one disagreement (F2)
reconciled in §4.

## 1. The call

**One net-new experiment + two packaging jobs + three demo features + one
evidence page + a content arc.** Everything lives in the non-pipeline 50% of
founder hours; agents run nearly all of it.

| # | Item | Type | Status of underlying data |
|---|---|---|---|
| E1 | **F3 calibrated abstention** — risk–coverage analysis (`divorce/abstention_eval.py`) | net-new experiment | mediator already abstains; needs the selective-prediction eval + fresh-seed confirmatory |
| E2 | **F5 budget curve** — figures from committed JSONs (`divorce/figures.py`) | packaging | done, committed |
| E3 | **F1 pettiness-tax population sweep** — distribution over 300 pairs + clean-counterfactual check | packaging | engine computes it; aggregation net-new |
| D1 | **"Run it back without the spite"** button on every decree — the F1 counterfactual as a product feature (ghost-decree diff card) | demo feature | API re-run with λ=0 on recorded spec |
| D2 | **County Register** (pettiness leaderboard w/ ?case= replays) + **percentile line** on the decree ("94th percentile of 300 archived cases" — the committed harness runs, labeled honestly) + **Docket head-to-head** (two case numbers, one ruling) | demo features | ledger + archive JSONs exist |
| D3 | **County census card** — clerk-voiced live-ledger stats at any N ("11 estates on file. The county is patient.") | demo feature | GET /v1/divorce/stats aggregation |
| P1 | **/science page** ("measured, not vibed") + public repro harness — **LED BY THE TRAP CHECK** (8% goodwill leak / 16.5%=16.5% aggregate masking), then E1/E2/E3 | publication | survey §§1–4 is the draft; repro = kill_harness command |

**Parked, with reasons:**
- **F2 (receipts × procedural justice) as a CLAIM** — needs recruited human
  subjects; nothing about perceived fairness/compliance ships until a
  preregistered, consented, controlled study runs. (See §4 for what DOES ship.)
- **F4 (adversarial advocates)** — it's the demo's framing, already built
  (ARM-D); ship as chrome, never dress as research.
- **Covert receipt-visibility A/B on demo visitors — KILLED** (both seats):
  brand-fatal ("nobody peeked" company caught peeking) and methodologically
  weak (visitors ratify nothing; share-clicks aren't procedural justice).

## 2. Experiment designs (registration summaries — freeze before running)

**E1 (F3):** N=100 × seeds 7/11/23 + one fresh confirmatory seed. Metrics:
coverage (decrees issued), selective risk (true-IR violation | certified),
overlaid on question budget. Kills (freeze first): KILL-UP if selective risk
> 2% at the shipped operating point → retire "calibrated"; KILL-DOWN if
> 15% of abstentions were RECOVERABLE (a bundle clearing both true IRs
existed inside the elicited-feasible set at Q=10) → the gate is uncalibrated
pessimism, fix before claiming. Artifact: risk–coverage curve + "0
IR-violating decrees across 300 sealed settlements; residual uncertainty
became abstention, never a bad stamp."

**E3 (F1):** population distribution of the spite counterfactual. Kills:
KILL-DOWN if median tax < 5% of joint surplus → don't headline; KILL-UP
(clean-counterfactual check) if despiking moves non-hill allocations beyond
a registered bound → tax not cleanly attributable, flag. Artifact: median
$X / Y% of achievable surplus, per-case AND population — the vs-prior claim
is "re-runnable per-case counterfactual, not a population regression"
(nearest prior: Mill & Staebler 2023).

**E2 (F5):** no new runs. Panel 1 capture-vs-questions w/ settle overlay;
panel 2 honest-vs-biased answerers (v1 82→57 craters; v2 92 biased > 82
honest v1). Registered incremental kill (already survives): drop
"human-robust" if biased-v2 ≤ honest-v1. Claim the APPLICATION, never the
method (Baarslag & Kaisers 2017 owns the method; cite it).

## 3. The wall (comedy ↔ rigor), jointly agreed

- Per-CASE artifacts on the demo (tax, autopsy, NO DECREE, flip, receipt,
  spite re-run diff); per-POPULATION curves on /science. One link between
  them ("the math, measured" on the decree; the docket footnote).
- The clerk's deadpan is the ONLY sanctioned crossover. Approved seam lines:
  1. "Spite. On file with this office since 1979." (docket footnote → M&K)
  2. "Envy-free: NO. This office reports what is true, not what is nice."
     (the receipt owning the 73% EF caveat)
  3. "The field measured whether people settled and how they felt about it.
     The county measures what the settlement was worth." (/science opener)
- **Live-ledger numbers are entertainment, never evidence.** Census card =
  toy, labeled; /science cites only committed seeded runs. Percentiles on
  decrees compare against the ARCHIVE (300 committed runs), labeled as such.
- Methods grammar (N=, CI) never on the cream; clerk voice never on /science.

## 4. The F2 reconciliation (the one disagreement)

CEO: park F2 entirely. CMO: kill the covert version, but ship a DISCLOSED
opt-in "county feedback card" ("The county requests your opinion of these
proceedings" — fairness 1–7, trust 1–7, receipt-visibility openly
randomized) and scope the real study off-surface. **Resolution: both.** The
disclosed card ships as groundwork/instrument-piloting only — its data
supports NO public claim. The claimable F2 study (preregistered, consented
panel, demo as stimulus, control arm + bidirectional kill BEFORE running)
waits for post-traction or a partner with subjects. Until then the /science
page carries the scope sentence verbatim: "We make no claim about how real
divorcing parties feel, decide, or comply — that needs human subjects we
have not run."

## 5. Sequencing (merged, week granularity; all non-pipeline hours)

| Wk | Founder (hrs) | Agents |
|---|---|---|
| 1 | Freeze E1+E3 kills (commit = registration) ~2h | Build abstention_eval.py + figures.py; run E2/E3 sweeps; build D1 (spite re-run) |
| 2 | Read E1, apply kills ~2h | E1 fresh-seed confirmatory; build D2 (register + percentile + head-to-head) |
| 3 | Write /science lede personally; sign overclaim checklist ~3h | Package artifacts + repro harness; /science behind flag; D3 census; trap-check lede card |
| 4 | Deploy call | Demo deploy + /science ship TOGETHER; OG cards |
| 5–6 | Post Act I (the bit: NO DECREE leads) | County Register seeds; census drumbeat when honest |
| 6–7 | M&K bridge post ("Impediment #1 is spite. #5 is the dog. Named 1979. Measured 2026.") | — |
| 7–8 | Research-drop post (four-empty-checkboxes card → /science) then the 8% specimen card (AI-eval audience; the notary bridge) | — |

## 6. Tripwires & guardrails

1. **Pipeline first:** any week the notary pipeline gets <50% founder-hours
   or buyer-conversation count stalls 2 weeks → ALL research freezes.
2. **Overclaim checklist** (survey §4) is a pre-publication gate the founder
   signs; any method-novelty or human-perception claim is cut on sight. The
   false Rechtwijzer story reappearing anywhere = full page re-audit.
3. **Register leak detection:** tax-voice on /science or stats-voice on the
   cream → rewrite; if demo share-rate drops after the /science link ships,
   bury the link deeper.
4. **The liability shield:** "The divorce is fake. The math is real." never
   drops its first half. Any content implying real couples should settle
   real divorces here collides with the DV/mediation-ethics literature
   (coercive-control cases must never be mediated) — the demo is about
   AGENTS, always.

## 7. The sentences the plan unlocks (each traceable to a seeded run)

- "You cannot audit an agent by its aggregates: 8% of its decisions leaked a
  median $4,505 while its accept rate matched the correct rule exactly."
  (trap check — the lede, the notary thesis)
- "Across 300 sealed settlements the notary never certified a decree that
  violated a true walk-away; uncertainty became abstention, never a bad
  stamp." (E1, if kills survive)
- "Ten choices a side captures 85–92% of the perfect-information frontier;
  24 captures 99% — the first elicitation-budget curve for legal
  settlement." (E2)
- "Spite is measurable: same divorce, minus the feelings, re-run to the
  dollar." (E3 + D1)
- "Hand us a seed and a command and you get our number." (the repro harness
  — the notary company doing to itself what it sells)

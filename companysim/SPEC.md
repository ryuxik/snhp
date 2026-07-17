# COMPANYSIM — THE COMPANY (v33, column CO)

*Program spec for the D1a HARNESS. Restates the registered contract
(research/swarm/SPEC.md "v33 (column CO)" + the "v33-A AMENDMENT")
operationally: episode lifecycle, roles, settlement, budget enforcement, the
provenance spine, the allocation round, and the honesty rules. D1a is built and
run with NO LLM API CALLS — everything model-facing is an adapter with
fixtures; the whole program runs offline with zero network.*

## What this is

A company of LLM-agent employees grows a **real, self-hostable service from
scratch**, run as **recorded episodes** under a **pre-registered token budget**
and replayed on the site from real artifacts. The org picks its own product in a
founding episode — see-where-it-goes is the point.

**The founding brief (verbatim, registered):**

> build a small self-hostable infrastructure tool

The org chooses the specific product by creating IDEAS in the founding episode
(`CreateIdea`); nothing here hard-codes what gets built.

## The thesis, made process

Work moves through a five-step protocol whose gate is a test authored by the
counterparty — the test is the receipt:

1. **SPEC_TASK** — an author writes a brief + **acceptance tests** into the
   workspace, posts a **bounty**, proposes a **split**, and tags the task to
   exactly one **idea**. The bounty is escrowed from treasury at this step (you
   cannot post a bounty the treasury cannot fund).
2. **CLAIM** — an implementer takes an open task. On multi-stage work the
   **split is fixed at claim time (the bills)** — the locked split, not any
   later value, is what settles.
3. **SUBMIT** — the implementer commits code into the task's workspace dir. The
   commit hash is recorded on the event as a receipt.
4. **REVIEW** — a **different** agent (the reviewer can NEVER be the
   implementer — enforced) runs the acceptance tests in a subprocess with a
   timeout. Pass → merge; fail → reject.
5. **SETTLE** — on merge-with-passing-tests, the escrow pays the locked split:
   `spec → author`, `implement → claimant`, `review → reviewer`. Each share is a
   receipt on the hash-chained money ledger; any unpaid remainder refunds to
   treasury so the escrow zeroes out.

**False completion is representable and catchable.** A SUBMIT whose acceptance
tests fail at REVIEW is rejected: **the claim is voided**, the task reopens
(re-claimable), and the implementer earns nothing — the compute it already
metered is the sunk cost. The tests were authored by the counterparty, so an
implementer cannot merge broken work by asserting it is done.

## Roles

Roles are free labels on roster entries; capability is governed by the **regime
+ protocol**, not by role name. The three pipeline roles a split pays are
`spec`, `implement`, `review`. The middle roles (spec, review) are the glue
work — their credits sit on the claim stacks, so glue work is visible on the
ledger by construction (v33-A).

## Regimes (config-level, enforced by the protocol layer)

- **COMMAND** — a designated **manager** agent is the ONLY agent who may create
  ideas / create + assign tasks. Others claim (only what is assigned to them),
  submit, review.
- **CLAIMS** — an open bounty board, **no manager**: any agent may spec or
  claim; splits are fixed at claim.

Enforcement is structural (`protocol.check_*` raises `ProtocolError`), not
prompt hope. An illegal action does not take effect; it is recorded as an
`action_rejected` event.

## Episode lifecycle (as implemented)

An episode = a **registered config** (regime, agent roster, turn cap, token
budget, starting capital, seed, allocation policy) + a sequence of agent turns.
`EpisodeConfig.validate()` refuses to run without a positive token budget
(SPEC: "Budget must be set before run"). Per turn, the current agent (round-
robin over the **active**, non-benched roster) receives a rendered `View` of org
state — its wallet, its role, the idea board, the task board, repo status — and
returns a list of structured actions. The runner validates each action through
the protocol layer, performs the side effects (escrow, git commit, acceptance-
test subprocess, settlement), appends to the append-only hash-chained event log
+ money ledger, then charges the turn's metered compute. The episode ends at the
**turn cap**, at **budget exhaustion** (hard stop — a turn runs only if its cost
still fits, so a run never exceeds its registered budget), or at **quiescence**
(a full idle round). Every phase is an event; the run is **resumable** (state is
a pure fold of the event log — a fresh runner over the same dir rebuilds the
board, restores the logical clock, and continues).

## The provenance spine (v33-A)

- **Ideas are first-class**, created in the founding episode; every task links
  to exactly one idea. The tree is `idea → tasks → claim stacks → settlement
  receipts`.
- **An idea's value = its settled receipts net of its metered spend.** Token
  costs are charged **per-idea**: a turn's compute is attributed to the idea(s)
  of the tasks it acted on (overhead turns — founding, notes — charge to no
  idea).
- **An agent's / role's value = the receipt flow THROUGH it**, middle roles
  included. All aggregates are pure folds of the money ledger (`Wallets`).

## The allocation round (v33-A, every episode boundary)

Budgets, headcount, and continuation are set **from the receipt ledger alone** —
the org chart is downstream of the ledger. `runner.allocate(policy)` folds the
ledger into per-idea / per-agent aggregates, applies a swappable **allocation
policy**, refunds escrow on cut ideas, and logs explicit **GROW / CUT / BENCH /
REASSIGN** org events (the replay page renders org evolution from these). Three
policies ship (per episode config):

- **`receipts`** — allocate proportional to **net receipt flow** (settled −
  spend); score agents by their **full** receipt flow, so middle roles are
  funded by construction. Ideas with net ≤ 0 are cut; agents with flow ≤ 0 are
  benched.
- **`outcome`** — allocate proportional to raw **merged volume**; score agents
  by **implement volume only**, so spec/review (glue) work is invisible and gets
  defunded.
- **`manager`** — the COMMAND manager decides via its adapter (may drift with
  the manager's view).

The contrast between these three is the registered **D2 science, on real work**
(report-not-verdict until then; predictions to be formally registered before D2
runs). A CUT cancels an idea's open tasks and refunds their escrow; a BENCHED
agent takes no turns in the next episode (`EpisodeConfig.active_roster`).

## Wallets, ledger, budget

- **Money ledger** — append-only, hash-chained JSONL (paperswarm pattern),
  double-entry (every receipt debits one account, credits another by the same
  amount). `verify_chain` recomputes the whole chain; any edit breaks it. Two
  pools: the internal **treasury** (funds bounties) and the metered
  **compute_budget** (the pre-registered token cap). Settlement, split, refund,
  escrow, and every metered spend are receipts on this chain.
- **Conservation** (checked in tests): `treasury + Σ escrows + Σ wallets ==
  starting_capital`, and `compute_budget + total_spend == token_budget`.
- **Token meter** — reads/charges the `compute_budget` account; `remaining` is
  that account's balance, so the meter holds no state the chain does not. D1a
  fixture agents declare a simulated per-turn cost; D1b measures real LLM cost
  after the call and stops on cumulative-≥-budget. Both honor the hard cap.

## The agent adapter (model-agnostic)

`Agent.propose(view) -> actions` with two implementations:
- **`FixtureAgent`** — scripted, deterministic action batches (dict keyed by
  global turn = resume-safe); declares a simulated per-turn cost. Powers every
  test.
- **`LLMAgent`** — the real-model adapter, **stubbed in D1a**: it raises
  `NotImplementedError` unless an API key **and** a registered per-episode
  budget are present, and even then raises "wired in D1b" — D1a never touches
  the wire. D1b wires the real call.

## Workspace — what is committed vs regenerated

Each episode gets a **nested git repo** under
`companysim/episodes/<id>/workspace/`, inited by the runner. Acceptance tests
(written at SPEC) and implementation (written at SUBMIT) live under
`workspace/tasks/<task_id>/`; REVIEW runs pytest there in a subprocess with a
timeout. Commit hashes are made **deterministic** (fixed identity + a date from
the episode's logical clock) so a recorded episode regenerates byte-identical
commit hashes.

- **COMMITTED** (canonical, publishable, drives the D1c replay page):
  `episodes/<id>/events.jsonl`, `episodes/<id>/ledger.jsonl`, and the episode's
  registered config — plus the `companysim/` program source and this SPEC.
- **REGENERATED** (gitignored, never committed): `episodes/<id>/workspace/` —
  the nested git repo and all agent-written code + acceptance tests, the pytest
  cache. It is rebuildable by replaying the event log: every SPEC_TASK carries
  its acceptance-test files, every SUBMIT carries its implementation files and
  the resulting commit hash, and every REVIEW carries the test-output digest, so
  the workspace is reproducible and every on-screen object in D1c maps to a
  commit/test in the log. The outer repo therefore gitignores
  `companysim/episodes/*/workspace/` while `events.jsonl` + `ledger.jsonl` (one
  level up) are committed.

## Honesty rules (bind all phases)

- Artifacts public and complete; the token budget + models are registered
  pre-run; the demo phase asserts **observations only**; any science claim needs
  its registered prediction; the sim's numbers never blend with the swarm
  engine's banked results in any public artifact without labeling which world
  they came from.
- **Value-anchor honesty (v33-A registered limit):** internal receipts measure
  **VERIFIED WORK** (counterparty tests passed), **not market value** — an idea
  can compound receipts while being a bad product. D1 ground truth is
  merge-with-passing-tests + the episode-end smoke run; an external demand
  signal is a registered-open D2+ extension, not assumed.

## Contract ambiguities resolved (builder decisions)

1. **Logical, not wall-clock, time.** A recorded episode must replay
   byte-for-byte, so timestamps come from a monotonic logical `Clock`, and
   workspace commit dates are driven from it — making commit hashes reproducible
   receipts rather than wall-clock artifacts.
2. **"Costs the implementer its claim."** On review-fail the claim is voided and
   the task reopens (re-claimable); the implementer earns nothing and the
   already-metered compute is the sunk cost. No extra penalty is levied.
3. **Two money pools, not one.** The internal economy (treasury → escrow →
   wallets) is kept separate from the pre-registered compute cap
   (compute_budget), so the token budget is a clean hard cap and the internal
   receipts are cleanly conserved. Compute spend is still a receipt on the same
   chain.
4. **Per-turn spend attribution.** A turn's compute is attributed to the idea(s)
   of the tasks its actions touched (split evenly across multiple; overhead →
   no idea). This makes per-idea P&L a pure ledger fold.
5. **Illegal actions are recorded, not fatal.** A protocol violation is logged
   as `action_rejected` and skipped (a real LLM agent will emit illegal
   actions); the reviewer-≠-implementer rule and the manager-only-creates rule
   are enforced this way and asserted in tests.
6. **Two logs, cross-linked.** The narrative event log (the replay contract) and
   the money ledger are separate append-only hash-chained files; money events
   mirror onto the event log carrying the ledger record's hash, so the replay
   page reads one log while money integrity lives on the other.

## Phase map (registered)

- **D1a (this build)** — the harness, fully tested offline. No LLM spend.
- **D1b** — first episodes: registered budget per episode committed before any
  run (initial cap $20/episode, founder may revise); 1 founding + 2 per regime;
  all published, failures included.
- **D1c** — replay page rendered ONLY from logged artifacts.
- **D2** — the science (receipts vs outcome vs manager allocation), gated on
  D1b, report-not-verdict until registered predictions land.

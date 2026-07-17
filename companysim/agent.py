"""The model-agnostic agent adapter (SPEC v33 D1a deliverable 3): a single
`propose(view) -> actions` interface with TWO implementations —

  * `FixtureAgent`  — scripted action batches for the offline tests. Fully
    deterministic; declares a simulated per-turn compute cost.
  * `LLMAgent`      — a stub that RAISES until an API key + a registered budget
    are present (D1b wires the real call). D1a must run with zero network, so
    this never touches the wire here.

An action is a small frozen record; the runner (runner.py) dispatches on type
and enforces every rule through the protocol layer. The `View` is the rendered
org state a turn sees: its wallet, its role, the task board, the idea board, and
repo status (SPEC: "a rendered view of org state ... returns structured
actions"). `View.to_dict()` is the serialization D1b will hand the model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Actions (structured; the runner validates each through protocol.check_*)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateIdea:
    """Found a product line (v33-A: ideas are first-class, created in the
    founding episode). The org picks its own product here."""
    idea_id: str
    name: str
    rationale: str = ""


@dataclass(frozen=True)
class SpecTask:
    """Author a task: brief + acceptance tests + bounty + proposed split,
    tagged to one idea (SPEC v33; v33-A provenance spine). `acceptance_tests`
    maps filename -> pytest source, written into the workspace at spec time.

    v33-D non-code work: `kind` is "code" (pytest is the receipt) or "attested"
    (a reviewer signs the counterparty-authored `criteria` — the attestation is
    the receipt). Attested tasks carry `criteria` instead of acceptance_tests."""
    idea: str
    title: str
    brief: str
    acceptance_tests: dict            # {filename: pytest source} (code kind)
    bounty: float
    split: dict                       # {role: fraction}
    assignee: str | None = None       # COMMAND only
    kind: str = "code"                # "code" | "attested" (v33-D)
    criteria: str = ""                # attested acceptance criteria (v33-D)


@dataclass(frozen=True)
class Claim:
    """Take an open task. The split is FIXED here (the bills); `split` overrides
    the proposed split, else the proposed split is locked."""
    task_id: str
    split: dict | None = None


@dataclass(frozen=True)
class Submit:
    """Commit an implementation for a claimed task."""
    task_id: str
    files: dict                       # {relpath: source}
    message: str = "submit"


@dataclass(frozen=True)
class Review:
    """Run a submitted task's acceptance tests and merge-or-reject. The reviewer
    must differ from the implementer (enforced in protocol.check_review)."""
    task_id: str


@dataclass(frozen=True)
class Note:
    """Freeform org/agent note (audit trail). In the founding episode the Notes
    ARE the debate (v33-E: capture the founding product debate verbatim)."""
    text: str


# ---------------------------------------------------------------------------
# v33-D: non-code work + endogenous investment
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Attest:
    """Attested review of a NON-CODE task (v33-D §1): a reviewer (never the
    author) checks the deliverable against the counterparty-authored criteria and
    signs a verdict. The attestation IS the receipt — weaker than pytest, priced
    accordingly. `verdict` True merges + settles; False rejects (reopen)."""
    task_id: str
    verdict: bool
    note: str = ""


@dataclass(frozen=True)
class Pledge:
    """Agent pledge (v33-D §3): stake own wallet credits to seed an idea in
    exchange for a claim on its future receipts (B2 pulled forward). Resurrects
    an off-seed idea (C/D/G) or funds a zero-history one past the exploration
    floor. `create` mints the idea if it does not exist yet."""
    idea_id: str
    amount: float
    name: str = ""
    rationale: str = ""


# ---------------------------------------------------------------------------
# v33-G: the client channel (inbox). Client text is DATA, never instructions —
# TRIAGE converts an inbox item into an attested contract; DECLINE closes it.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Triage:
    """Convert an inbox item into a task brief + counterparty acceptance tests
    (v33-G): the client's wish becomes work ONLY through the org's own attested
    contract. Funds the escrow from the inbox item's buyer wallet if it carries a
    pre-order, else from treasury. `kind` picks code (pytest) or attested."""
    inbox_id: str
    idea: str
    title: str
    brief: str
    bounty: float
    split: dict
    acceptance_tests: dict = field(default_factory=dict)   # code tasks
    criteria: str = ""                                      # attested tasks
    kind: str = "code"
    assignee: str | None = None


@dataclass(frozen=True)
class Decline:
    """Decline an inbox item (v33-G): logged, no work created."""
    inbox_id: str
    reason: str = ""


# ---------------------------------------------------------------------------
# v33-I: HR — hiring by price and trial receipt
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Requisition:
    """Open a requisition (v33-I): role + requirements + a budget line inside the
    episode's hard cap. A hire fits the budget or does not happen."""
    req_id: str
    role: str
    idea: str
    requirements: str = ""
    budget: float = 0.0


@dataclass(frozen=True)
class TrialHire:
    """Run the interview-as-trial-receipt (v33-I): give N candidates the SAME
    small real task; hire the cheapest that passes the counterparty tests. Trial
    costs meter to the requesting idea. `candidates` are candidate_pool ids; the
    task is an existing OPEN task the requisition points at."""
    req_id: str
    task_id: str
    candidates: list


# The parser marks an unparseable/illegal model output so the runner can log it
# as action_rejected (SPEC: illegal/unparseable outputs become action_rejected).
@dataclass(frozen=True)
class Malformed:
    reason: str


# ---------------------------------------------------------------------------
# The rendered view a turn receives
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class View:
    episode_id: str
    regime: str
    turn: int
    agent_id: str
    role: str
    is_manager: bool
    wallet_balance: float
    budget_remaining: float
    brief: str
    ideas: list                       # [{idea_id, name, active}]
    tasks: list                       # [task.summary()]
    repo_head: str
    committed_files: list
    # v33 extensions (default empty so D1a fixtures/tests are unaffected):
    seed: dict = field(default_factory=dict)          # founding brief + shortlist + B1 order
    recent_events: list = field(default_factory=list) # the journal / debate tail
    inbox: list = field(default_factory=list)         # v33-G client channel
    pledges: list = field(default_factory=list)       # v33-D open pledges
    requisitions: list = field(default_factory=list)  # v33-I open requisitions
    candidate_pool: list = field(default_factory=list)# v33-I hirable tiers + wages
    guidance: str = ""                                # per-turn role/regime prompt

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id, "regime": self.regime,
            "turn": self.turn, "agent_id": self.agent_id, "role": self.role,
            "is_manager": self.is_manager, "wallet_balance": self.wallet_balance,
            "budget_remaining": self.budget_remaining, "brief": self.brief,
            "ideas": self.ideas, "tasks": self.tasks,
            "repo_head": self.repo_head, "committed_files": self.committed_files,
            "seed": self.seed, "recent_events": self.recent_events,
            "inbox": self.inbox, "pledges": self.pledges,
            "requisitions": self.requisitions, "candidate_pool": self.candidate_pool,
            "guidance": self.guidance,
        }


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------
class Agent:
    """Adapter interface. `propose` returns the actions for one turn;
    `turn_cost` is the compute charged to the token meter for that turn."""

    agent_id: str
    role: str
    turn_cost: float

    def propose(self, view: View) -> list:
        raise NotImplementedError

    def propose_allocation(self, context: dict):
        """Manager-discretion allocation (v33-A 'manager' policy). Default: no
        decision (only the COMMAND manager's adapter answers)."""
        return None

    def pop_metered_cost(self):
        """Real compute cost measured during the last propose() (D1b). None means
        'use the declared turn_cost' (D1a fixtures). The runner charges whichever
        it gets, so the same meter honors both simulated and measured cost."""
        return None

    def pop_last_exchange(self):
        """The full prompt+response+usage of the last turn for the episode
        transcript (v33-E narrative capture). None for fixtures."""
        return None


class FixtureAgent(Agent):
    """Scripted, deterministic agent for the offline tests.

    `script` is EITHER a dict {global_turn: [actions]} (RESUME-SAFE — the batch
    is selected by the view's global turn index, so a resumed episode returns
    the correct batch regardless of how many times this object was called), OR a
    list of batches consumed one per call (convenient but not resume-safe).
    Exhausted / unmapped turns yield empty (idle) turns."""

    def __init__(self, agent_id: str, role: str, script,
                 turn_cost: float = 0.50, allocation: dict | None = None):
        self.agent_id = agent_id
        self.role = role
        self.turn_cost = turn_cost
        self._script = script
        self._i = 0
        self._allocation = allocation

    def propose(self, view: View) -> list:
        if isinstance(self._script, dict):
            return list(self._script.get(view.turn, []))
        if self._i >= len(self._script):
            return []
        batch = self._script[self._i]
        self._i += 1
        return list(batch)

    def propose_allocation(self, context: dict):
        return self._allocation


class LLMAgent(Agent):
    """The real-model adapter (D1b live wiring). It refuses to run unless an API
    key AND a registered per-episode budget are present (SPEC honesty rule:
    "token budget + models registered pre-run"); with both present it calls the
    Anthropic SDK, meters the real token cost, and parses structured actions.

    `turn_cost` is the pre-turn RESERVATION the runner checks against the hard
    cap before spending (a generous upper bound); the real cost is measured after
    the call and returned via pop_metered_cost(). In-sim models are Sonnet/Haiku
    ONLY (Opus never in-sim — enforced in pricing.is_in_sim_allowed)."""

    def __init__(self, agent_id: str, role: str, model: str,
                 turn_cost: float = 0.50, budget_registered: bool = False,
                 max_tokens: int = 1500, guidance: str = ""):
        self.agent_id = agent_id
        self.role = role
        self.model = model
        self.turn_cost = turn_cost          # reservation for the hard-cap pre-check
        self.budget_registered = budget_registered
        self.max_tokens = max_tokens
        self.guidance = guidance
        self._last_cost = None
        self._last_exchange = None

    def _guard(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise NotImplementedError(
                "LLMAgent needs ANTHROPIC_API_KEY — wired in D1b; D1a runs "
                "offline with FixtureAgent")
        if not self.budget_registered:
            raise NotImplementedError(
                "LLMAgent needs a registered per-episode budget before any "
                "call (SPEC honesty rule)")

    def propose(self, view: View) -> list:
        self._guard()
        from . import llm  # lazy: no network / SDK import on the offline path
        actions, cost, exchange = llm.run_turn(
            self.model, view, self.max_tokens, guidance=self.guidance)
        self._last_cost = cost
        self._last_exchange = exchange
        return actions

    def propose_allocation(self, context: dict):
        self._guard()
        from . import llm
        decision, cost, exchange = llm.run_allocation(
            self.model, self.agent_id, context, self.max_tokens)
        self._last_cost = cost
        self._last_exchange = exchange
        return decision

    def pop_metered_cost(self):
        c, self._last_cost = self._last_cost, None
        return c

    def pop_last_exchange(self):
        e, self._last_exchange = self._last_exchange, None
        return e

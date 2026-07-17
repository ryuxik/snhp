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
    maps filename -> pytest source, written into the workspace at spec time."""
    idea: str
    title: str
    brief: str
    acceptance_tests: dict            # {filename: pytest source}
    bounty: float
    split: dict                       # {role: fraction}
    assignee: str | None = None       # COMMAND only


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
    """Freeform org/agent note (audit trail)."""
    text: str


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

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id, "regime": self.regime,
            "turn": self.turn, "agent_id": self.agent_id, "role": self.role,
            "is_manager": self.is_manager, "wallet_balance": self.wallet_balance,
            "budget_remaining": self.budget_remaining, "brief": self.brief,
            "ideas": self.ideas, "tasks": self.tasks,
            "repo_head": self.repo_head, "committed_files": self.committed_files,
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
    """The real-model adapter — STUBBED in D1a. It refuses to run unless an API
    key AND a registered per-episode budget are present (SPEC honesty rule:
    "token budget + models registered pre-run"). D1b wires the actual call; D1a
    must be runnable with zero network, so this always raises here."""

    def __init__(self, agent_id: str, role: str, model: str,
                 turn_cost: float = 0.50, budget_registered: bool = False):
        self.agent_id = agent_id
        self.role = role
        self.model = model
        self.turn_cost = turn_cost
        self.budget_registered = budget_registered

    def _guard(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise NotImplementedError(
                "LLMAgent needs ANTHROPIC_API_KEY — wired in D1b; D1a runs "
                "offline with FixtureAgent")
        if not self.budget_registered:
            raise NotImplementedError(
                "LLMAgent needs a registered per-episode budget before any "
                "call (SPEC honesty rule)")
        raise NotImplementedError(
            "LLMAgent.propose is wired in D1b (FIRST EPISODES); D1a is the "
            "offline harness")

    def propose(self, view: View) -> list:
        self._guard()

    def propose_allocation(self, context: dict):
        self._guard()

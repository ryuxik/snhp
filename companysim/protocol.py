"""The task+claim protocol — the thesis made process (SPEC v33): SPEC_TASK ->
CLAIM -> SUBMIT -> REVIEW -> SETTLE, with the tests authored by the counterparty
as the receipt. Plus the v33-A provenance spine: every task is tagged to one
IDEA.

The `TaskBoard` is a PROJECTION: it is always `fold(event_log)`. Transitions
happen in two steps so state can never diverge from the log (which makes resume
and the replay page trivially correct):

  * `check_*(...)`  — pure enforcement. Raises `ProtocolError` if an action is
    illegal under the regime + current state. This is where "enforced by the
    protocol layer, not by prompt hope" (SPEC) lives:
        - COMMAND: only the manager may create/assign tasks.
        - REVIEW: the reviewer can NEVER be the implementer.
        - split is fixed at CLAIM time (the bills) and honored at settle.
  * `apply_event(rec)` — pure fold. The runner writes the event, then folds it;
    resume folds the whole log from scratch and lands in the identical state.

The runner (runner.py) owns the side effects (escrow, git commit, test run,
settle receipts); this module owns only the rules + the state machine.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from . import events as ev
from .config import PIPELINE_ROLES, ROLE_IMPLEMENT, Regime


class ProtocolError(RuntimeError):
    """An illegal protocol move (a caller tried to break a rule)."""


class TaskState(enum.Enum):
    OPEN = "open"            # speced + funded, claimable
    CLAIMED = "claimed"      # an implementer holds it (split locked)
    SUBMITTED = "submitted"  # code committed, awaiting review
    MERGED = "merged"        # tests passed, merged + settled (terminal)
    CANCELLED = "cancelled"  # v33-A allocation CUT (terminal)


def validate_split(split: dict) -> None:
    """A claim-split maps pipeline roles -> fractions of the bounty. Fractions
    are non-negative and sum to <= 1.0 (any remainder refunds to treasury on
    settle). implement must carry a positive share — someone builds it."""
    if not split:
        raise ProtocolError("empty split")
    for role, frac in split.items():
        if role not in PIPELINE_ROLES:
            raise ProtocolError(f"unknown split role {role!r}")
        if frac < 0:
            raise ProtocolError(f"negative split share for {role!r}")
    if sum(split.values()) > 1.0 + 1e-9:
        raise ProtocolError("split shares exceed the bounty (sum > 1.0)")
    if split.get(ROLE_IMPLEMENT, 0.0) <= 0:
        raise ProtocolError("split must pay a positive 'implement' share")


@dataclass
class Idea:
    """A product line / initiative (v33-A). Ideas are first-class, created in
    the founding episode; tasks link to exactly one idea. Ideas form the
    provenance tree root: idea -> tasks -> claim stacks -> settlement receipts."""

    idea_id: str
    name: str
    rationale: str
    creator: str
    active: bool = True   # set False by an allocation CUT (v33-A)


@dataclass
class Task:
    task_id: str
    idea: str                       # v33-A: exactly one idea (provenance spine)
    author: str
    title: str
    brief: str
    acceptance_tests: list[str]     # filenames written into the workspace
    bounty: float
    proposed_split: dict            # role -> fraction (proposed at spec)
    assignee: str | None = None     # COMMAND regime: manager's assignment
    state: TaskState = TaskState.OPEN
    claimant: str | None = None
    split_locked: dict | None = None  # fixed at CLAIM (the bills)
    submit_commit: str | None = None
    reviewer: str | None = None
    rejections: int = 0
    kind: str = "code"              # v33-D: "code" (pytest) | "attested" (sign-off)
    criteria: str = ""              # v33-D: attested acceptance criteria
    source_inbox: str | None = None # v33-G: inbox item this task was triaged from
    buyer: str | None = None        # v33-B/G: buyer wallet funding this task's escrow

    def summary(self) -> dict:
        """Compact view for the rendered agent View / replay page."""
        return {
            "task_id": self.task_id, "idea": self.idea, "title": self.title,
            "state": self.state.value, "bounty": self.bounty, "kind": self.kind,
            "author": self.author, "assignee": self.assignee,
            "claimant": self.claimant, "reviewer": self.reviewer,
            "rejections": self.rejections,
            "criteria": self.criteria if self.kind == "attested" else "",
            "acceptance_tests": list(self.acceptance_tests),
        }


class TaskBoard:
    """A fold of the event log: ideas + tasks + their live states. Never mutated
    except through `apply_event`; `check_*` only reads."""

    def __init__(self, regime: Regime, manager_id: str | None,
                 inbox_seed: list | None = None):
        self.regime = regime
        self.manager_id = manager_id
        self.ideas: dict[str, Idea] = {}
        self.tasks: dict[str, Task] = {}
        self._task_seq = 0
        # v33-G client channel: {inbox_id: {text, buyer, amount, state}}. Seeded
        # from config (founder-sanitized records) so resume rebuilds it identically.
        self.inbox: dict[str, dict] = {}
        for item in (inbox_seed or []):
            iid = item["inbox_id"]
            self.inbox[iid] = {"inbox_id": iid, "text": item.get("text", ""),
                               "buyer": item.get("buyer"),
                               "amount": float(item.get("amount", 0.0) or 0.0),
                               "state": "open"}
        # v33-I HR: {req_id: {role, idea, requirements, budget, filled_by}}.
        self.requisitions: dict[str, dict] = {}

    # -- projection: rebuild from the log (resume / replay) ---------------
    @classmethod
    def from_log(cls, event_log: ev.EventLog, regime: Regime,
                 manager_id: str | None, inbox_seed: list | None = None) -> "TaskBoard":
        board = cls(regime, manager_id, inbox_seed=inbox_seed)
        for rec in event_log.records():
            board.apply_event(rec)
        return board

    def apply_event(self, rec) -> None:
        t, d = rec.type, rec.data
        if t == ev.IDEA_CREATED:
            self.ideas[d["idea_id"]] = Idea(
                d["idea_id"], d["name"], d["rationale"], d["actor"])
        elif t == ev.TASK_SPECED:
            self.tasks[d["task_id"]] = Task(
                task_id=d["task_id"], idea=d["idea"], author=d["actor"],
                title=d["title"], brief=d["brief"],
                acceptance_tests=list(d["acceptance_tests"]),
                bounty=d["bounty"], proposed_split=dict(d["split"]),
                assignee=d.get("assignee"),
                kind=d.get("kind", "code"), criteria=d.get("criteria", ""),
                source_inbox=d.get("source_inbox"), buyer=d.get("buyer"))
            self._task_seq = max(self._task_seq, _task_num(d["task_id"]))
        elif t == ev.TASK_CLAIMED:
            task = self.tasks[d["task_id"]]
            task.state = TaskState.CLAIMED
            task.claimant = d["actor"]
            task.split_locked = dict(d["split_locked"])
        elif t == ev.TASK_SUBMITTED:
            task = self.tasks[d["task_id"]]
            task.state = TaskState.SUBMITTED
            task.submit_commit = d["commit"]
        elif t == ev.TASK_MERGED:
            task = self.tasks[d["task_id"]]
            task.state = TaskState.MERGED
            task.reviewer = d["reviewer"]
        elif t == ev.TASK_REJECTED:
            task = self.tasks[d["task_id"]]
            # False completion (SPEC): the claim is VOIDED, the task reopens.
            task.state = TaskState.OPEN
            task.claimant = None
            task.split_locked = None
            task.submit_commit = None
            task.reviewer = None
            task.rejections += 1
        elif t == ev.ATTESTED:
            task = self.tasks[d["task_id"]]
            if d["verdict"]:
                task.state = TaskState.MERGED           # attested pass = merge
                task.reviewer = d["actor"]
            else:                                        # attested fail = reopen
                task.state = TaskState.OPEN
                task.claimant = None
                task.split_locked = None
                task.submit_commit = None
                task.reviewer = None
                task.rejections += 1
        elif t == ev.PLEDGE:
            # A pledge may mint (resurrect) an idea (v33-D exploration).
            iid = d["idea_id"]
            if iid not in self.ideas:
                self.ideas[iid] = Idea(iid, d.get("name", iid),
                                       d.get("rationale", ""), d["actor"])
        elif t == ev.INBOX_TRIAGED:
            item = self.inbox.get(d["inbox_id"])
            if item:
                item["state"] = "triaged"
                item["task_id"] = d.get("task_id")
        elif t == ev.INBOX_DECLINED:
            item = self.inbox.get(d["inbox_id"])
            if item:
                item["state"] = "declined"
        elif t == ev.REQUISITION_OPENED:
            self.requisitions[d["req_id"]] = {
                "req_id": d["req_id"], "role": d.get("role", ""),
                "idea": d.get("idea"), "requirements": d.get("requirements", ""),
                "budget": d.get("budget", 0.0), "filled_by": None}
        elif t == ev.HIRE:
            req = self.requisitions.get(d.get("req_id"))
            if req:
                req["filled_by"] = d.get("candidate")
        elif t == ev.ALLOC_CUT:
            idea = self.ideas.get(d["idea_id"])
            if idea:
                idea.active = False
            for task in self.tasks.values():
                if task.idea == d["idea_id"] and task.state in (
                        TaskState.OPEN, TaskState.CLAIMED, TaskState.SUBMITTED):
                    task.state = TaskState.CANCELLED

    # -- id minting -------------------------------------------------------
    def next_task_id(self) -> str:
        return f"t{self._task_seq + 1}"

    # -- enforcement (pure; raises ProtocolError) -------------------------
    def check_create_idea(self, actor: str, idea_id: str) -> None:
        if self.regime is Regime.COMMAND and actor != self.manager_id:
            raise ProtocolError(
                f"COMMAND: only manager {self.manager_id} may create ideas")
        if idea_id in self.ideas:
            raise ProtocolError(f"idea {idea_id} already exists")

    def check_spec(self, actor: str, idea_id: str, bounty: float,
                   split: dict, assignee: str | None) -> None:
        if self.regime is Regime.COMMAND and actor != self.manager_id:
            raise ProtocolError(
                f"COMMAND: only manager {self.manager_id} may create tasks")
        if self.regime is Regime.CLAIMS and assignee is not None:
            raise ProtocolError("CLAIMS: open board has no assignments")
        if idea_id not in self.ideas:
            raise ProtocolError(f"unknown idea {idea_id!r}")
        if not self.ideas[idea_id].active:
            raise ProtocolError(f"idea {idea_id!r} is cut; cannot spec to it")
        if bounty <= 0:
            raise ProtocolError("bounty must be > 0")
        validate_split(split)

    def check_claim(self, actor: str, task_id: str) -> None:
        task = self._require(task_id)
        if task.state is not TaskState.OPEN:
            raise ProtocolError(f"task {task_id} not OPEN (is {task.state.value})")
        if task.assignee is not None and actor != task.assignee:
            raise ProtocolError(
                f"task {task_id} is assigned to {task.assignee}, not {actor}")

    def check_submit(self, actor: str, task_id: str) -> None:
        task = self._require(task_id)
        if task.state is not TaskState.CLAIMED:
            raise ProtocolError(f"task {task_id} not CLAIMED")
        if actor != task.claimant:
            raise ProtocolError(
                f"only claimant {task.claimant} may submit {task_id}")

    def check_review(self, actor: str, task_id: str) -> None:
        task = self._require(task_id)
        if task.state is not TaskState.SUBMITTED:
            raise ProtocolError(f"task {task_id} not SUBMITTED")
        if task.kind != "code":
            raise ProtocolError(
                f"task {task_id} is {task.kind}; use attest, not review")
        # The one rule the whole honesty story turns on (SPEC v33): the
        # reviewer can NEVER be the implementer.
        if actor == task.claimant:
            raise ProtocolError(
                f"reviewer {actor} cannot be the implementer of {task_id}")

    def check_attest(self, actor: str, task_id: str) -> None:
        """v33-D attested review: same reviewer!=author firewall, non-code only."""
        task = self._require(task_id)
        if task.state is not TaskState.SUBMITTED:
            raise ProtocolError(f"task {task_id} not SUBMITTED")
        if task.kind != "attested":
            raise ProtocolError(
                f"task {task_id} is code; use review (pytest), not attest")
        # Attestation firewall: the attester can never be the implementer, and
        # (v33-D) the reviewer must differ from the AUTHOR of the criteria.
        if actor == task.claimant:
            raise ProtocolError(
                f"attester {actor} cannot be the implementer of {task_id}")
        if actor == task.author:
            raise ProtocolError(
                f"attester {actor} cannot be the author of {task_id}")

    def check_pledge(self, actor: str, idea_id: str, amount: float,
                     wallet_balance: float) -> None:
        """v33-D: an agent may stake ONLY its own credits (conviction is paid for)."""
        if amount <= 0:
            raise ProtocolError("pledge amount must be > 0")
        if wallet_balance + 1e-9 < amount:
            raise ProtocolError(
                f"pledge {amount} exceeds wallet balance {wallet_balance}")
        # A pledge to an existing CUT idea is fine (resurrect-by-pledge); to an
        # active idea it is additional exploration capital.

    def check_triage(self, actor: str, inbox_id: str, idea_id: str,
                     bounty: float, split: dict) -> None:
        """v33-G: only through the org's own attested contract. COMMAND: manager
        only (it is task creation)."""
        if self.regime is Regime.COMMAND and actor != self.manager_id:
            raise ProtocolError(
                f"COMMAND: only manager {self.manager_id} may triage")
        item = self.inbox.get(inbox_id)
        if item is None:
            raise ProtocolError(f"no such inbox item {inbox_id}")
        if item["state"] != "open":
            raise ProtocolError(f"inbox item {inbox_id} already {item['state']}")
        if idea_id not in self.ideas:
            raise ProtocolError(f"unknown idea {idea_id!r}")
        if bounty <= 0:
            raise ProtocolError("bounty must be > 0")
        validate_split(split)

    def check_decline(self, actor: str, inbox_id: str) -> None:
        item = self.inbox.get(inbox_id)
        if item is None:
            raise ProtocolError(f"no such inbox item {inbox_id}")
        if item["state"] != "open":
            raise ProtocolError(f"inbox item {inbox_id} already {item['state']}")

    def check_requisition(self, actor: str, req_id: str, idea_id: str) -> None:
        """v33-I: an allocation that grows an idea may open a requisition. In
        COMMAND, the manager owns headcount; in CLAIMS, any agent may open one."""
        if self.regime is Regime.COMMAND and actor != self.manager_id:
            raise ProtocolError(
                f"COMMAND: only manager {self.manager_id} may requisition")
        if req_id in self.requisitions:
            raise ProtocolError(f"requisition {req_id} already exists")
        if idea_id not in self.ideas:
            raise ProtocolError(f"unknown idea {idea_id!r}")

    def check_trial(self, actor: str, req_id: str, task_id: str) -> None:
        """v33-I: run the trial against an OPEN task the requisition points at."""
        if req_id not in self.requisitions:
            raise ProtocolError(f"no such requisition {req_id}")
        if self.requisitions[req_id]["filled_by"] is not None:
            raise ProtocolError(f"requisition {req_id} already filled")
        task = self._require(task_id)
        if task.state is not TaskState.OPEN:
            raise ProtocolError(f"trial task {task_id} not OPEN")
        if task.kind != "code":
            raise ProtocolError("trial task must be code (pytest is the receipt)")

    def _require(self, task_id: str) -> Task:
        if task_id not in self.tasks:
            raise ProtocolError(f"no such task {task_id}")
        return self.tasks[task_id]

    # -- read helpers -----------------------------------------------------
    def open_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.state is TaskState.OPEN]

    def summaries(self) -> list[dict]:
        return [t.summary() for t in self.tasks.values()]


def _task_num(task_id: str) -> int:
    try:
        return int(task_id[1:]) if task_id.startswith("t") else 0
    except ValueError:
        return 0

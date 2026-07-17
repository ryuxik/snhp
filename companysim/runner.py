"""The episode runner (SPEC v33 D1a deliverable 2): a deterministic turn
scheduler. An episode = a registered config + a sequence of agent turns. Each
turn the current agent receives a rendered view of org state and returns
structured actions; the runner enforces every rule through the protocol layer,
writes the side effects (escrow / git commit / test run / settlement), and
appends to the append-only, hash-chained event log + money ledger.

Determinism: turns are round-robin over the ACTIVE (non-benched) roster; the
seeded RNG is threaded for any future ordering choice (none needed for
round-robin). The run is RESUMABLE — state is a pure fold of the event log, so a
fresh runner over an existing episode dir rebuilds the board, restores the
logical clock, and continues where it stopped. The token meter HARD-STOPS the
episode before any turn it cannot afford, so a run never exceeds its registered
budget.

v33-A: token spend is attributed to the idea(s) a turn served; at the episode
boundary `allocate()` runs the allocation round (allocation.py) and logs the
GROW/CUT/BENCH/REASSIGN org events.
"""

from __future__ import annotations

import random
from pathlib import Path

from . import agent as A
from . import events as ev
from .allocation import AllocationResult, run_allocation
from .config import (PIPELINE_ROLES, ROLE_IMPLEMENT, ROLE_REVIEW, ROLE_SPEC,
                     EpisodeConfig)
from .ledger import ACCT_TREASURY, Ledger, Wallets, acct_escrow
from .meter import TokenMeter
from .protocol import ProtocolError, TaskBoard, TaskState, validate_split
from .timeutil import Clock
from .workspace import Workspace


class EpisodeRunner:
    """Runs (and resumes) one registered episode."""

    def __init__(self, config: EpisodeConfig, root):
        config.validate()
        self.config = config
        self.dir = Path(root) / config.episode_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.event_log = ev.EventLog(self.dir / "events.jsonl")
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.wallets = Wallets(self.ledger)
        # One logical clock shared by both logs + the workspace git dates.
        # Resume: seed its count from the records already written so the
        # timeline continues monotonically (timeutil.Clock).
        self.clock = Clock(count=len(self.event_log) + len(self.ledger))
        self.workspace = Workspace(self.dir / "workspace", self.clock)
        self.meter = TokenMeter(self.ledger, config.token_budget_usd)
        self.board = TaskBoard.from_log(self.event_log, config.regime,
                                        config.manager_id())
        self.rng = random.Random(config.seed)

    # -- logging helpers ---------------------------------------------------
    def _emit(self, ev_type: str, actor: str, data: dict):
        return self.event_log.emit(ev_type, actor, data, ts=self.clock.tick())

    # -- lifecycle ---------------------------------------------------------
    def run(self) -> dict:
        """Run to the turn cap, budget exhaustion, or quiescence. Idempotent to
        resume: a fresh runner over the same dir continues the timeline."""
        if len(self.event_log) == 0:
            self._start()
        stop_reason = self._turn_loop()
        self._emit(ev.EPISODE_END, "runner", {
            "reason": stop_reason, "turns": self._turns_taken(),
            "spent": self.meter.spent(), "remaining": self.meter.remaining()})
        return self.report(stop_reason)

    def _start(self) -> None:
        self.workspace.init()
        self._emit(ev.EPISODE_START, "runner", {
            "episode_id": self.config.episode_id,
            "regime": self.config.regime.value,
            "roster": [{"agent_id": e.agent_id, "role": e.role,
                        "manager": e.manager, "benched": e.benched}
                       for e in self.config.roster],
            "turn_cap": self.config.turn_cap,
            "token_budget_usd": self.config.token_budget_usd,
            "starting_capital_usd": self.config.starting_capital_usd,
            "seed": self.config.seed, "brief": self.config.brief,
            "allocation_policy": self.config.allocation_policy})
        # Fund the two pools (internal treasury; metered compute budget).
        from .ledger import ACCT_COMPUTE
        self.ledger.fund(ACCT_TREASURY, self.config.starting_capital_usd,
                        ts=self.clock.tick())
        self.ledger.fund(ACCT_COMPUTE, self.config.token_budget_usd,
                        ts=self.clock.tick())

    def _turn_loop(self) -> str:
        active = self.config.active_roster()
        n = len(active)
        idle_streak = 0
        turn = self._turns_taken()
        while turn < self.config.turn_cap:
            entry = active[turn % n]
            cost = entry.agent.turn_cost
            if not self.meter.can_afford(cost):
                self._emit(ev.BUDGET_STOP, "runner", {
                    "turn": turn, "spent": self.meter.spent(),
                    "budget": self.config.token_budget_usd,
                    "blocked_cost": cost})
                return "budget"
            view = self._render_view(entry, turn)
            try:
                actions = entry.agent.propose(view)
            except NotImplementedError as exc:
                # An unwired adapter (LLMAgent in D1a) stops the episode loudly.
                self._emit(ev.NOTE, entry.agent_id,
                           {"kind": "adapter_unavailable", "error": str(exc)})
                return "adapter_unavailable"
            touched = self._apply_actions(entry, actions or [], turn)
            self._charge(entry, touched, cost, turn)
            self._emit(ev.TURN, entry.agent_id, {
                "turn": turn, "actions": [type(a).__name__ for a in actions or []]})
            idle_streak = 0 if actions else idle_streak + 1
            turn += 1
            if idle_streak >= n:      # a full idle round -> wind down
                return "quiescent"
        return "cap"

    # -- token meter -------------------------------------------------------
    def _charge(self, entry, touched: set, cost: float, turn: int) -> None:
        """Charge the turn's compute, attributed to the idea(s) it served
        (v33-A). Overhead turns (no task referent) charge to idea=None."""
        ideas = sorted(i for i in touched if i is not None)
        if not ideas:
            self.meter.charge(cost, agent_id=entry.agent_id, idea=None,
                              turn=turn, ts=self.clock.tick())
            return
        share = round(cost / len(ideas), 10)
        for i, idea in enumerate(ideas):
            amt = round(cost - share * (len(ideas) - 1), 10) if i == len(ideas) - 1 else share
            self.meter.charge(amt, agent_id=entry.agent_id, idea=idea,
                              turn=turn, ts=self.clock.tick())

    # -- action dispatch ---------------------------------------------------
    def _apply_actions(self, entry, actions: list, turn: int) -> set:
        touched: set = set()
        actor = entry.agent_id
        for action in actions:
            try:
                idea = self._apply_one(actor, action, turn)
                if idea is not None:
                    touched.add(idea)
            except ProtocolError as exc:
                # Enforced by the protocol layer, not prompt hope (SPEC): the
                # illegal action does NOT take effect; it is recorded.
                self._emit(ev.ACTION_REJECTED, actor, {
                    "action": type(action).__name__, "reason": str(exc)})
        return touched

    def _apply_one(self, actor: str, action, turn: int):
        if isinstance(action, A.CreateIdea):
            self.board.check_create_idea(actor, action.idea_id)
            rec = self._emit(ev.IDEA_CREATED, actor, {
                "idea_id": action.idea_id, "name": action.name,
                "rationale": action.rationale})
            self.board.apply_event(rec)
            return None  # founding is org overhead, not idea-attributed spend

        if isinstance(action, A.SpecTask):
            self.board.check_spec(actor, action.idea, action.bounty,
                                  action.split, action.assignee)
            if self.wallets.balance(ACCT_TREASURY) + 1e-9 < action.bounty:
                raise ProtocolError(
                    f"underfunded bounty {action.bounty} > treasury "
                    f"{self.wallets.balance(ACCT_TREASURY)}")
            task_id = self.board.next_task_id()
            spec_commit = self.workspace.write_and_commit(
                task_id, action.acceptance_tests, f"spec {task_id}")
            self.ledger.escrow(task_id, action.bounty, idea=action.idea,
                               ts=self.clock.tick())
            rec = self._emit(ev.TASK_SPECED, actor, {
                "task_id": task_id, "idea": action.idea, "title": action.title,
                "brief": action.brief,
                "acceptance_tests": list(action.acceptance_tests),
                "bounty": action.bounty, "split": dict(action.split),
                "assignee": action.assignee, "spec_commit": spec_commit})
            self.board.apply_event(rec)
            return action.idea

        if isinstance(action, A.Claim):
            self.board.check_claim(actor, action.task_id)
            task = self.board.tasks[action.task_id]
            locked = dict(action.split) if action.split else dict(task.proposed_split)
            validate_split(locked)
            rec = self._emit(ev.TASK_CLAIMED, actor, {
                "task_id": action.task_id, "split_locked": locked})
            self.board.apply_event(rec)
            return task.idea

        if isinstance(action, A.Submit):
            self.board.check_submit(actor, action.task_id)
            task = self.board.tasks[action.task_id]
            commit = self.workspace.write_and_commit(
                action.task_id, action.files, action.message or f"submit {action.task_id}")
            rec = self._emit(ev.TASK_SUBMITTED, actor, {
                "task_id": action.task_id, "commit": commit,
                "files": list(action.files)})
            self.board.apply_event(rec)
            return task.idea

        if isinstance(action, A.Review):
            self.board.check_review(actor, action.task_id)
            return self._review(actor, action.task_id)

        if isinstance(action, A.Note):
            self._emit(ev.NOTE, actor, {"text": action.text})
            return None

        raise ProtocolError(f"unknown action {type(action).__name__}")

    def _review(self, reviewer: str, task_id: str):
        task = self.board.tasks[task_id]
        result = self.workspace.run_acceptance(task_id, task.acceptance_tests)
        self._emit(ev.REVIEW_RUN, reviewer, {
            "task_id": task_id, "result": "pass" if result.passed else "fail",
            "tests_passed": result.tests_passed, "tests_failed": result.tests_failed,
            "test_digest": result.digest, "duration_s": result.duration_s,
            "timed_out": result.timed_out, "commit": task.submit_commit})
        if result.passed:
            settle_hashes = self._settle(task, reviewer, result.digest)
            rec = self._emit(ev.TASK_MERGED, reviewer, {
                "task_id": task_id, "commit": task.submit_commit,
                "reviewer": reviewer, "settle_hashes": settle_hashes})
            self.board.apply_event(rec)
        else:
            reason = "timeout" if result.timed_out else "tests_failed"
            rec = self._emit(ev.TASK_REJECTED, reviewer, {
                "task_id": task_id, "reason": reason})
            self.board.apply_event(rec)  # SPEC: claim voided, task reopens
        return task.idea

    def _settle(self, task, reviewer: str, test_digest: str) -> list:
        """Pay the locked split (the bills), each share a receipt on the chain
        (SPEC v33 D1a deliverable 5). Recipients: spec->author, implement->
        claimant, review->reviewer. Any unpaid remainder refunds to treasury so
        the escrow zeroes out (conservation)."""
        split = task.split_locked or {}
        recipients = {ROLE_SPEC: task.author, ROLE_IMPLEMENT: task.claimant,
                      ROLE_REVIEW: reviewer}
        hashes = []
        paid = 0.0
        for role in PIPELINE_ROLES:
            frac = split.get(role, 0.0)
            if frac <= 0:
                continue
            amount = round(task.bounty * frac, 10)
            paid = round(paid + amount, 10)
            rec = self.ledger.settle(
                task.task_id, recipients[role], amount, role=role,
                idea=task.idea, commit=task.submit_commit,
                test_digest=test_digest, ts=self.clock.tick())
            hashes.append(rec.hash)
            self._emit(ev.SETTLED, reviewer, {
                "task_id": task.task_id, "to": recipients[role], "role": role,
                "amount": amount, "idea": task.idea, "ledger_hash": rec.hash})
        remainder = round(task.bounty - paid, 10)
        if remainder > 0:
            self.ledger.refund(task.task_id, remainder, idea=task.idea,
                               ts=self.clock.tick())
        return hashes

    # -- view rendering ----------------------------------------------------
    def _render_view(self, entry, turn: int) -> A.View:
        return A.View(
            episode_id=self.config.episode_id, regime=self.config.regime.value,
            turn=turn, agent_id=entry.agent_id, role=entry.role,
            is_manager=entry.manager,
            wallet_balance=self.wallets.agent_balance(entry.agent_id),
            budget_remaining=self.meter.remaining(), brief=self.config.brief,
            ideas=[{"idea_id": i.idea_id, "name": i.name, "active": i.active}
                   for i in self.board.ideas.values()],
            tasks=self.board.summaries(),
            repo_head=self.workspace.head() if (self.dir / "workspace" / ".git").exists() else "",
            committed_files=self.workspace.committed_files()
            if (self.dir / "workspace" / ".git").exists() else [])

    def _turns_taken(self) -> int:
        return sum(1 for r in self.event_log.records() if r.type == ev.TURN)

    # -- the allocation round (v33-A, episode boundary) --------------------
    def allocate(self, manager_agent=None) -> AllocationResult:
        """Run the allocation round for THIS episode: aggregate the ledger,
        apply the configured policy, refund escrow on cut ideas, and log the
        GROW/CUT/BENCH/REASSIGN org events. Returns the result the NEXT
        episode's config is built from (`result.next_roster`)."""
        agent_ids = [e.agent_id for e in self.config.roster]
        _, result = run_allocation(
            self.config.allocation_policy, self.wallets, self.board,
            agent_ids, self.config, manager_agent)
        for ev_type, actor, data in result.events:
            rec = self._emit(ev_type, actor, data)
            self.board.apply_event(rec)
            if ev_type == ev.ALLOC_CUT:
                self._refund_cut(data["idea_id"])
        return result

    def _refund_cut(self, idea_id: str) -> None:
        """Return locked escrow of a cut idea's cancelled tasks to treasury."""
        for task in self.board.tasks.values():
            if task.idea != idea_id or task.state is not TaskState.CANCELLED:
                continue
            locked = round(self.wallets.balance(acct_escrow(task.task_id)), 10)
            if locked > 0:
                self.ledger.refund(task.task_id, locked, idea=idea_id,
                                   ts=self.clock.tick())

    # -- reporting ---------------------------------------------------------
    def report(self, stop_reason: str) -> dict:
        from .ledger import ACCT_COMPUTE, verify_chain
        merged = sum(1 for t in self.board.tasks.values()
                     if t.state is TaskState.MERGED)
        return {
            "episode_id": self.config.episode_id,
            "regime": self.config.regime.value,
            "stop_reason": stop_reason,
            "turns_taken": self._turns_taken(),
            "turn_cap": self.config.turn_cap,
            "spent": self.meter.spent(),
            "remaining": self.meter.remaining(),
            "budget": self.config.token_budget_usd,
            "merged": merged,
            "tasks": self.board.summaries(),
            "wallets": {e.agent_id: self.wallets.agent_balance(e.agent_id)
                        for e in self.config.roster},
            "treasury": self.wallets.balance(ACCT_TREASURY),
            "compute_budget": self.wallets.balance(ACCT_COMPUTE),
            "chain_ok_events": verify_chain(self.event_log.path).ok,
            "chain_ok_ledger": verify_chain(self.ledger.path).ok,
        }

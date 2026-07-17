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


class RosterEntryProxy:
    """A light stand-in so a trial candidate can be handed the same rendered View
    as a rostered agent (v33-I trial). Not a manager, no idea scope."""

    def __init__(self, agent_id, role, agent):
        self.agent_id = agent_id
        self.role = role
        self.agent = agent
        self.manager = False
        self.idea = None
        self.benched = False


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
                                        config.manager_id(),
                                        inbox_seed=config.inbox_seed)
        self.rng = random.Random(config.seed)
        # v33-E narrative capture (append-only, resume-safe).
        self.transcripts_path = self.dir / "transcripts.jsonl"
        self.firsts_path = self.dir / "firsts.jsonl"
        self._seen_firsts = self._load_firsts()

    # -- v33-E narrative capture ------------------------------------------
    def _load_firsts(self) -> set:
        seen = set()
        if self.firsts_path.exists():
            import json
            for line in self.firsts_path.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        seen.add(json.loads(line)["kind"])
                    except Exception:  # noqa: BLE001
                        pass
        return seen

    def _record_first(self, kind: str, data: dict) -> None:
        """Log a chronicle FIRST once per episode (first pledge, first rejection,
        first false completion caught, first hire, ...)."""
        if kind in self._seen_firsts:
            return
        self._seen_firsts.add(kind)
        import json
        rec = {"kind": kind, "turn": self._turns_taken(), **data}
        with open(self.firsts_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        self._emit(ev.FIRST, "runner", {"first": kind, **data})

    def _capture_transcript(self, exchange: dict) -> None:
        if not exchange:
            return
        import json
        with open(self.transcripts_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(exchange, sort_keys=True) + "\n")

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
        # v33-B/G: fund external buyer wallets (arms-length demand). The B1 buyer's
        # escrowed reconciliation pre-order lands here in the founding episode.
        for bw in self.config.buyer_wallets:
            self.ledger.buyer_fund(bw["buyer_id"], float(bw["amount"]),
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
                # An unwired adapter (LLMAgent without key/budget) stops loudly.
                self._emit(ev.NOTE, entry.agent_id,
                           {"kind": "adapter_unavailable", "error": str(exc)})
                return "adapter_unavailable"
            except Exception as exc:  # noqa: BLE001 — a live API error is a stop, resumable
                self._emit(ev.NOTE, entry.agent_id,
                           {"kind": "adapter_error", "error": str(exc)[:300]})
                return "adapter_error"
            # v33-E: capture the full prompt+response before applying actions.
            self._capture_transcript(entry.agent.pop_last_exchange())
            # D1b: real cost measured after the call; D1a fixtures declare it.
            metered = entry.agent.pop_metered_cost()
            charge_cost = metered if metered is not None else cost
            touched = self._apply_actions(entry, actions or [], turn)
            self._charge(entry, touched, charge_cost, turn)
            self._emit(ev.TURN, entry.agent_id, {
                "turn": turn, "cost": round(charge_cost, 10),
                "actions": [type(a).__name__ for a in actions or []]})
            idle_streak = 0 if actions else idle_streak + 1
            turn += 1
            if idle_streak >= n:      # a full idle round -> wind down
                return "quiescent"
        return "cap"

    # -- token meter -------------------------------------------------------
    def _charge(self, entry, touched: set, cost: float, turn: int) -> None:
        """Charge the turn's compute, attributed to the idea(s) it served
        (v33-A). Overhead turns (no task referent) charge to idea=None. The
        measured cost is clamped to the remaining budget so the hard cap holds
        even if a live turn's post-hoc cost would cross the line."""
        cost = round(min(cost, self.meter.remaining()), 10)
        if cost <= 0:
            return
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
            self._validate_kind(action.kind, action.acceptance_tests, action.criteria)
            task_id = self.board.next_task_id()
            files = self._spec_files(action.kind, action.acceptance_tests,
                                     action.criteria)
            spec_commit = self.workspace.write_and_commit(
                task_id, files, f"spec {task_id}")
            self._fund_escrow(task_id, action.idea, action.bounty)  # treasury/pledge fund
            rec = self._emit(ev.TASK_SPECED, actor, {
                "task_id": task_id, "idea": action.idea, "title": action.title,
                "brief": action.brief,
                "acceptance_tests": list(action.acceptance_tests),
                "bounty": action.bounty, "split": dict(action.split),
                "assignee": action.assignee, "kind": action.kind,
                "criteria": action.criteria, "spec_commit": spec_commit})
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

        if isinstance(action, A.Attest):
            self.board.check_attest(actor, action.task_id)
            return self._attest(actor, action)

        if isinstance(action, A.Pledge):
            return self._pledge(actor, action)

        if isinstance(action, A.Triage):
            return self._triage(actor, action, turn)

        if isinstance(action, A.Decline):
            self.board.check_decline(actor, action.inbox_id)
            rec = self._emit(ev.INBOX_DECLINED, actor, {
                "inbox_id": action.inbox_id, "reason": action.reason})
            self.board.apply_event(rec)
            return None

        if isinstance(action, A.Requisition):
            self.board.check_requisition(actor, action.req_id, action.idea)
            rec = self._emit(ev.REQUISITION_OPENED, actor, {
                "req_id": action.req_id, "role": action.role, "idea": action.idea,
                "requirements": action.requirements, "budget": action.budget})
            self.board.apply_event(rec)
            return action.idea

        if isinstance(action, A.TrialHire):
            self.board.check_trial(actor, action.req_id, action.task_id)
            return self._trial_hire(actor, action, turn)

        if isinstance(action, A.Note):
            self._emit(ev.NOTE, actor, {"text": action.text})
            return None

        if isinstance(action, A.Malformed):
            # An unparseable model output — logged, never applied (SPEC).
            raise ProtocolError(f"unparseable action: {action.reason}")

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
            self._record_first("merge", {"task_id": task_id, "reviewer": reviewer})
        else:
            reason = "timeout" if result.timed_out else "tests_failed"
            rec = self._emit(ev.TASK_REJECTED, reviewer, {
                "task_id": task_id, "reason": reason})
            self.board.apply_event(rec)  # SPEC: claim voided, task reopens
            self._record_first("false_completion_caught", {
                "task_id": task_id, "reviewer": reviewer,
                "implementer": task.claimant})
            self._record_first("rejection", {"task_id": task_id, "reason": reason})
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
            if task.buyer:                     # v33-B/G: unpaid buyer order returns
                self.ledger.buyer_refund(task.task_id, task.buyer, remainder,
                                         idea=task.idea, ts=self.clock.tick())
            else:
                self.ledger.refund(task.task_id, remainder, idea=task.idea,
                                   ts=self.clock.tick())
        return hashes

    # -- v33 extension handlers -------------------------------------------
    def _validate_kind(self, kind: str, tests: dict, criteria: str) -> None:
        if kind not in ("code", "attested"):
            raise ProtocolError(f"unknown task kind {kind!r}")
        if kind == "code" and not tests:
            raise ProtocolError("code task needs acceptance_tests (the receipt)")
        if kind == "attested" and not criteria.strip():
            raise ProtocolError("attested task needs criteria (the receipt)")

    def _spec_files(self, kind: str, tests: dict, criteria: str) -> dict:
        """The spec commit: pytest files (code) or a CRITERIA.md (attested)."""
        if kind == "code":
            return dict(tests)
        return {"CRITERIA.md": criteria}

    def _fund_escrow(self, task_id: str, idea: str, bounty: float) -> None:
        """Fund a bounty from treasury, or (v33-D) from the idea's pledge fund
        when treasury cannot cover it. Refuses an underfunded bounty."""
        from .ledger import acct_idea_fund
        treas = self.wallets.balance(ACCT_TREASURY)
        if treas + 1e-9 >= bounty:
            self.ledger.escrow(task_id, bounty, idea=idea, ts=self.clock.tick())
            return
        fund = self.wallets.balance(acct_idea_fund(idea))
        if fund + 1e-9 >= bounty:
            self.ledger.escrow_from_fund(task_id, bounty, idea=idea,
                                         ts=self.clock.tick())
            return
        raise ProtocolError(
            f"underfunded bounty {bounty} > treasury {treas} + pledge fund {fund}")

    def _attest(self, attester: str, action):
        """v33-D attested review: the reviewer signs the deliverable against the
        counterparty criteria; the attestation is the receipt."""
        task = self.board.tasks[action.task_id]
        digest = f"attested:{'pass' if action.verdict else 'fail'}:{action.note}"[:200]
        self._emit(ev.REVIEW_RUN, attester, {
            "task_id": action.task_id, "result": "pass" if action.verdict else "fail",
            "kind": "attested", "note": action.note, "commit": task.submit_commit})
        if action.verdict:
            settle_hashes = self._settle(task, attester, digest)
            rec = self._emit(ev.ATTESTED, attester, {
                "task_id": action.task_id, "verdict": True, "note": action.note,
                "settle_hashes": settle_hashes})
            self.board.apply_event(rec)
            self._record_first("attested_merge", {"task_id": action.task_id})
            self._record_first("merge", {"task_id": action.task_id, "reviewer": attester})
        else:
            rec = self._emit(ev.ATTESTED, attester, {
                "task_id": action.task_id, "verdict": False, "note": action.note})
            self.board.apply_event(rec)
            self._record_first("rejection", {"task_id": action.task_id, "reason": "attest_fail"})
        return task.idea

    def _pledge(self, actor: str, action):
        """v33-D: stake own credits on an idea (mints it if new); grants a claim on
        future receipts. Only the staker's own wallet is debited."""
        bal = self.wallets.agent_balance(actor)
        self.board.check_pledge(actor, action.idea_id, action.amount, bal)
        rec = self._emit(ev.PLEDGE, actor, {
            "idea_id": action.idea_id, "amount": action.amount,
            "name": action.name, "rationale": action.rationale})
        self.board.apply_event(rec)
        self.ledger.pledge(actor, action.idea_id, action.amount, ts=self.clock.tick())
        self._record_first("pledge", {"agent": actor, "idea": action.idea_id,
                                      "amount": action.amount})
        return action.idea_id

    def _triage(self, actor: str, action, turn: int):
        """v33-G: convert an inbox item into an attested contract. Funds the escrow
        from the item's buyer wallet if it carries a pre-order, else treasury."""
        self.board.check_triage(actor, action.inbox_id, action.idea,
                                action.bounty, action.split)
        self._validate_kind(action.kind, action.acceptance_tests, action.criteria)
        item = self.board.inbox[action.inbox_id]
        buyer = item.get("buyer")
        task_id = self.board.next_task_id()
        files = self._spec_files(action.kind, action.acceptance_tests, action.criteria)
        spec_commit = self.workspace.write_and_commit(task_id, files, f"triage {task_id}")
        if buyer and self.wallets.balance(f"buyer:{buyer}") + 1e-9 >= action.bounty:
            self.ledger.buyer_escrow(task_id, buyer, action.bounty,
                                     idea=action.idea, ts=self.clock.tick())
        else:
            buyer = None
            self._fund_escrow(task_id, action.idea, action.bounty)
        rec = self._emit(ev.TASK_SPECED, actor, {
            "task_id": task_id, "idea": action.idea, "title": action.title,
            "brief": action.brief, "acceptance_tests": list(action.acceptance_tests),
            "bounty": action.bounty, "split": dict(action.split), "assignee": action.assignee,
            "kind": action.kind, "criteria": action.criteria,
            "source_inbox": action.inbox_id, "buyer": buyer, "spec_commit": spec_commit})
        self.board.apply_event(rec)
        mark = self._emit(ev.INBOX_TRIAGED, actor, {
            "inbox_id": action.inbox_id, "task_id": task_id})
        self.board.apply_event(mark)
        self._record_first("triage", {"inbox_id": action.inbox_id, "task_id": task_id})
        return action.idea

    def _trial_hire(self, actor: str, action, turn: int):
        """v33-I: the interview IS a trial receipt. Give N candidates the SAME
        small real task; each candidate's Submit is reviewed; hire the cheapest
        that passes the counterparty tests. Trial cost meters to the idea."""
        task = self.board.tasks[action.task_id]
        results = []  # [(candidate_id, passed, cost)]
        for cid in action.candidates:
            cand = self.config.candidate_pool.get(cid)
            if cand is None:
                self._emit(ev.ACTION_REJECTED, actor, {
                    "action": "TrialHire", "reason": f"no candidate {cid}"})
                continue
            # The candidate proposes against a trial view scoped to this task.
            tview = self._render_view(
                RosterEntryProxy(cid, cand.role, cand), turn)
            try:
                cand_actions = cand.propose(tview)
            except Exception as exc:  # noqa: BLE001
                self._emit(ev.TRIAL_RUN, cid, {"req_id": action.req_id,
                           "task_id": action.task_id, "passed": False,
                           "error": str(exc)[:200]})
                continue
            self._capture_transcript(cand.pop_last_exchange())
            metered = cand.pop_metered_cost()
            trial_cost = metered if metered is not None else cand.turn_cost
            # Extract the candidate's submitted files (first Submit for this task).
            files = None
            for a in cand_actions or []:
                if isinstance(a, A.Submit) and a.task_id == action.task_id:
                    files = a.files
                    break
            passed = False
            if files:
                # Write the candidate's files into the trial task dir, then run
                # the counterparty acceptance tests — the verdict is the receipt.
                self.workspace.write_and_commit(
                    action.task_id, files, f"trial {cid} {action.task_id}")
                res = self.workspace.run_acceptance(action.task_id, task.acceptance_tests)
                passed = res.passed
            self.meter.charge(min(trial_cost, self.meter.remaining()),
                              agent_id=cid, idea=task.idea, turn=turn,
                              ts=self.clock.tick(), reason="trial")
            self._emit(ev.TRIAL_RUN, cid, {
                "req_id": action.req_id, "task_id": action.task_id,
                "passed": passed, "cost": round(trial_cost, 10)})
            results.append((cid, passed, trial_cost))
        # Hire the cheapest passing candidate (v33-I).
        passing = sorted((r for r in results if r[1]), key=lambda r: r[2])
        if passing:
            hired, _, hire_cost = passing[0]
            rec = self._emit(ev.HIRE, actor, {
                "req_id": action.req_id, "candidate": hired,
                "trial_cost": round(hire_cost, 10),
                "considered": [r[0] for r in results]})
            self.board.apply_event(rec)
            self._record_first("hire", {"candidate": hired, "req_id": action.req_id})
        else:
            self._emit(ev.NOTE, actor, {
                "kind": "trial_no_hire", "req_id": action.req_id,
                "considered": [r[0] for r in results]})
        return task.idea

    # -- view rendering ----------------------------------------------------
    def _render_view(self, entry, turn: int) -> A.View:
        from .ledger import acct_idea_fund
        has_git = (self.dir / "workspace" / ".git").exists()
        return A.View(
            episode_id=self.config.episode_id, regime=self.config.regime.value,
            turn=turn, agent_id=entry.agent_id, role=entry.role,
            is_manager=entry.manager,
            wallet_balance=self.wallets.agent_balance(entry.agent_id),
            budget_remaining=self.meter.remaining(), brief=self.config.brief,
            ideas=[{"idea_id": i.idea_id, "name": i.name, "active": i.active,
                    "pnl": self.wallets.idea_pnl(i.idea_id),
                    "fund": self.wallets.balance(acct_idea_fund(i.idea_id))}
                   for i in self.board.ideas.values()],
            tasks=self.board.summaries(),
            repo_head=self.workspace.head() if has_git else "",
            committed_files=self.workspace.committed_files() if has_git else [],
            seed=self.config.founding_seed,
            recent_events=self._recent_events(18),
            inbox=[i for i in self.board.inbox.values() if i["state"] == "open"],
            pledges=self._pledges_view(),
            requisitions=[r for r in self.board.requisitions.values()
                          if r.get("filled_by") is None],
            candidate_pool=self._candidate_pool_view(),
            guidance=getattr(entry.agent, "guidance", "") or "")

    def _recent_events(self, n: int) -> list:
        """A tail of the narrative log so agents can respond to each other (the
        founding debate is a real exchange of Notes)."""
        keep = (ev.NOTE, ev.IDEA_CREATED, ev.TASK_SPECED, ev.TASK_CLAIMED,
                ev.TASK_MERGED, ev.TASK_REJECTED, ev.ATTESTED, ev.PLEDGE,
                ev.INBOX_TRIAGED, ev.HIRE, ev.ACTION_REJECTED)
        out = []
        for r in self.event_log.records():
            if r.type not in keep:
                continue
            d = r.data
            summary = {"type": r.type, "actor": d.get("actor")}
            for k in ("text", "idea_id", "name", "task_id", "title", "reason",
                      "candidate", "amount", "verdict"):
                if k in d:
                    summary[k] = d[k]
            out.append(summary)
        return out[-n:]

    def _pledges_view(self) -> list:
        from .ledger import EV_PLEDGE
        return [{"agent": r.data["agent"], "idea": r.data["idea"],
                 "amount": r.data["amount"]}
                for r in self.ledger.records() if r.type == EV_PLEDGE]

    def _candidate_pool_view(self) -> list:
        from . import pricing
        out = []
        for cid, cand in self.config.candidate_pool.items():
            out.append({"candidate_id": cid, "role": getattr(cand, "role", ""),
                        "model": getattr(cand, "model", "fixture"),
                        "wage": pricing.wage_note(getattr(cand, "model", ""))})
        return out

    def _turns_taken(self) -> int:
        return sum(1 for r in self.event_log.records() if r.type == ev.TURN)

    # -- the allocation round (v33-A, episode boundary) --------------------
    def allocate(self, manager_agent=None) -> AllocationResult:
        """Run the allocation round for THIS episode: aggregate the ledger,
        apply the configured policy, refund escrow on cut ideas, and log the
        GROW/CUT/BENCH/REASSIGN org events. Returns the result the NEXT
        episode's config is built from (`result.next_roster`). v33-E: writes a
        before/after snapshot of the round to alloc_snapshots.jsonl."""
        import json
        agent_ids = [e.agent_id for e in self.config.roster]
        agg, result = run_allocation(
            self.config.allocation_policy, self.wallets, self.board,
            agent_ids, self.config, manager_agent)
        # v33-E: meter + capture the manager's boundary call if it made one.
        if manager_agent is not None:
            self._capture_transcript(manager_agent.pop_last_exchange())
            mcost = manager_agent.pop_metered_cost()
            if mcost:
                self.meter.charge(min(mcost, self.meter.remaining()),
                                  agent_id=manager_agent.agent_id, idea=None,
                                  turn=self._turns_taken(), ts=self.clock.tick(),
                                  reason="allocation")
        before = {"phase": "before", "policy": self.config.allocation_policy,
                  "exploration_floor": self.config.exploration_floor,
                  "ideas": {i: {"net": a.net_receipts, "settled": a.settled,
                                "spend": a.spend, "merged": a.merged_count}
                            for i, a in agg.ideas.items()},
                  "agents": {a: {"receipts": g.receipts,
                                 "implement_volume": g.implement_volume}
                             for a, g in agg.agents.items()}}
        with open(self.dir / "alloc_snapshots.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(before, sort_keys=True) + "\n")
        for ev_type, actor, data in result.events:
            rec = self._emit(ev_type, actor, data)
            self.board.apply_event(rec)
            if ev_type == ev.ALLOC_CUT:
                self._refund_cut(data["idea_id"])
        after = {"phase": "after", "grown": result.grown_ideas,
                 "cut": result.cut_ideas, "benched": result.benched_agents,
                 "idea_budgets": result.idea_budgets}
        with open(self.dir / "alloc_snapshots.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(after, sort_keys=True) + "\n")
        return result

    # -- v33-F reconciliation (the B1 buyer's acceptance test) -------------
    def reconcile(self, tolerance: float = 0.05, product_idea: str | None = None):
        """Re-derive per-agent cost from the stored SDK usage records (F's own
        input) and compare to the live meter total (v33-F: "per-agent cost
        attribution that reconciles to my bill"). If the org's chosen product
        cannot meter+reconcile, the fallback-to-A rule fires (logged). Returns a
        dict; also emits a RECONCILIATION event."""
        import json
        from . import pricing
        meter_total = self.meter.spent()
        per_agent, per_model, usage_derived = {}, {}, 0.0
        if self.transcripts_path.exists():
            for line in self.transcripts_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                t = json.loads(line)
                model, usage = t.get("model"), t.get("usage")
                if not model or not usage:
                    continue
                try:
                    c = pricing.cost_from_usage(model, usage)
                except ValueError:
                    continue
                usage_derived += c
                per_agent[t.get("agent")] = round(per_agent.get(t.get("agent"), 0.0) + c, 10)
                per_model[model] = round(per_model.get(model, 0.0) + c, 10)
        usage_derived = round(usage_derived, 10)
        denom = max(meter_total, usage_derived, 1e-9)
        deviation = abs(meter_total - usage_derived) / denom
        within = deviation <= tolerance
        chose_meter = self._chose_meter(product_idea)
        # Fallback-to-A fires if the chosen product cannot meter+reconcile.
        fallback = (not chose_meter) or (not within)
        result = {
            "meter_total": meter_total, "usage_derived_cost": usage_derived,
            "deviation": round(deviation, 6), "tolerance": tolerance,
            "within_tolerance": within, "per_agent": per_agent,
            "per_model": per_model, "chose_meter_product": chose_meter,
            "fallback_to_A": fallback}
        self._emit(ev.RECONCILIATION, "runner", result)
        if fallback:
            self._record_first("fallback_to_A", {
                "reason": "no meter product" if not chose_meter else "over tolerance"})
        return result

    def _chose_meter(self, product_idea: str | None) -> bool:
        """Did the org build the F meter (per-agent/per-idea cost attribution)?
        The meter is the only seed product that can reconcile a bill (A the pocket
        notary and H the eval harness cannot). Detected by meter keywords: on the
        explicit chosen-product idea if one is named, else across all ideas."""
        kws = ("meter", "reconcil", "payroll", "attribut", "cost attribution",
               "per-agent cost", "idea_f")
        def _is_meter(i) -> bool:
            blob = f"{i.idea_id} {i.name} {i.rationale}".lower()
            return i.active and any(k in blob for k in kws)
        if product_idea is not None:
            idea = self.board.ideas.get(product_idea)
            return bool(idea and _is_meter(idea))
        return any(_is_meter(i) for i in self.board.ideas.values())

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

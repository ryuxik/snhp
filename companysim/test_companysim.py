"""COMPANYSIM D1a harness tests — comprehensive, offline, fast (SPEC v33 D1a:
"Fully tested offline"; v33-A: allocation-round tests).

Every test runs with ZERO network (FixtureAgent only; the LLMAgent stub is
asserted to refuse). REVIEW runs real pytest subprocesses in a per-episode
nested git repo under a pytest tmp_path, so nothing here touches the outer repo.

Run:  python3 -m pytest companysim/ -q   (from repo root)
"""

from __future__ import annotations

import json

import pytest

from companysim import events as ev
from companysim.agent import (Claim, CreateIdea, FixtureAgent, LLMAgent, Note,
                              Review, SpecTask, Submit)
from companysim.allocation import (OutcomePolicy, ReceiptsPolicy, aggregate,
                                   run_allocation)
from companysim.config import (ROLE_IMPLEMENT, ROLE_REVIEW, ROLE_SPEC,
                               EpisodeConfig, Regime, RosterEntry)
from companysim.ledger import (ACCT_COMPUTE, ACCT_TREASURY, Ledger, Wallets,
                               verify_chain)
from companysim.protocol import ProtocolError, TaskBoard, TaskState
from companysim.runner import EpisodeRunner

# --- acceptance-test / implementation fixtures (the counterparty receipts) ---
GOOD_TESTS = {"test_acc.py": (
    "from tool import add\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n\n"
    "def test_add_neg():\n    assert add(-1, 1) == 0\n")}
GOOD_IMPL = {"tool.py": "def add(a, b):\n    return a + b\n"}
BAD_IMPL = {"tool.py": "def add(a, b):\n    return a - b\n"}  # fails the tests

SPLIT_FULL = {ROLE_SPEC: 0.2, ROLE_IMPLEMENT: 0.6, ROLE_REVIEW: 0.2}
SPLIT_TWO_STAGE = {ROLE_SPEC: 0.25, ROLE_IMPLEMENT: 0.75}  # no review share


# --- builders ----------------------------------------------------------------
def _spec(idea, bounty=100.0, split=None, tests=None, assignee=None,
          title="add()", brief="implement add"):
    return SpecTask(idea=idea, title=title, brief=brief,
                    acceptance_tests=tests or GOOD_TESTS, bounty=bounty,
                    split=split or SPLIT_FULL, assignee=assignee)


def _episode(tmp_path, episode_id, regime, roster, turn_cap,
             token_budget=20.0, policy="receipts"):
    cfg = EpisodeConfig(episode_id=episode_id, regime=regime, roster=roster,
                        turn_cap=turn_cap, token_budget_usd=token_budget,
                        allocation_policy=policy)
    return EpisodeRunner(cfg, tmp_path)


def _actors(log):
    return [r.data.get("actor") for r in log.records()]


def _types(log):
    return [r.type for r in log.records()]


# ===========================================================================
# 1. End-to-end founding->spec->claim->implement->review-pass->settle, COMMAND
# ===========================================================================
def test_command_episode_end_to_end(tmp_path):
    M = FixtureAgent("M", "manager", {0: [
        CreateIdea("idea1", "URL shortener", "small self-hostable tool"),
        _spec("idea1", assignee="E")]})
    E = FixtureAgent("E", "engineer", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    R = FixtureAgent("R", "engineer", {2: [Review("t1")]})
    roster = [RosterEntry("M", "manager", M, manager=True),
              RosterEntry("E", "engineer", E), RosterEntry("R", "engineer", R)]
    rep = _episode(tmp_path, "cmd1", Regime.COMMAND, roster, turn_cap=3).run()

    assert rep["merged"] == 1
    assert rep["wallets"] == {"M": 20.0, "E": 60.0, "R": 20.0}  # split honored
    assert rep["treasury"] == 900.0        # 1000 - 100 bounty, fully paid out
    assert rep["chain_ok_events"] and rep["chain_ok_ledger"]
    assert rep["stop_reason"] == "cap"


# ===========================================================================
# 2. End-to-end, CLAIMS regime (open board, no manager)
# ===========================================================================
def test_claims_episode_end_to_end(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "tool", ""), _spec("idea1")]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    rep = _episode(tmp_path, "clm1", Regime.CLAIMS, roster, turn_cap=3).run()

    assert rep["merged"] == 1
    assert rep["wallets"] == {"A": 20.0, "B": 60.0, "C": 20.0}
    # a MERGED task carries a real workspace commit hash on the log
    speced = [r for r in EpisodeRunner(
        EpisodeConfig("clm1", Regime.CLAIMS, roster, 3), tmp_path
    ).event_log.records() if r.type == ev.TASK_SUBMITTED]
    assert len(speced[0].data["commit"]) == 40  # sha1 workspace commit


# ===========================================================================
# 3. Review-FAIL: false completion costs the implementer its claim
# ===========================================================================
def test_review_fail_voids_claim(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", BAD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    runner = _episode(tmp_path, "fail1", Regime.CLAIMS, roster, turn_cap=3)
    rep = runner.run()

    assert rep["merged"] == 0
    assert rep["wallets"] == {"A": 0.0, "B": 0.0, "C": 0.0}  # nobody paid
    task = runner.board.tasks["t1"]
    assert task.state is TaskState.OPEN          # reopened
    assert task.claimant is None and task.rejections == 1   # claim voided
    assert ev.TASK_REJECTED in _types(runner.event_log)
    fail = [r for r in runner.event_log.records() if r.type == ev.REVIEW_RUN][0]
    assert fail.data["result"] == "fail" and fail.data["tests_failed"] >= 1


# ===========================================================================
# 4. Reviewer == implementer is refused (the one honesty rule), two ways
# ===========================================================================
def test_reviewer_cannot_be_implementer_unit():
    board = TaskBoard(Regime.CLAIMS, manager_id=None)
    _seed_submitted(board, claimant="B")        # drive board to a SUBMITTED task
    with pytest.raises(ProtocolError, match="reviewer"):
        board.check_review("B", "t1")           # implementer reviewing own work
    board.check_review("C", "t1")               # a different agent is fine (no raise)


def test_reviewer_cannot_be_implementer_end_to_end(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
    # B claims, submits, then illegally tries to review its own submission
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL),
                                      Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B)]
    runner = _episode(tmp_path, "self1", Regime.CLAIMS, roster, turn_cap=2)
    runner.run()
    rejected = [r for r in runner.event_log.records()
                if r.type == ev.ACTION_REJECTED]
    assert any("reviewer" in r.data["reason"] for r in rejected)
    assert runner.board.tasks["t1"].state is TaskState.SUBMITTED  # not merged


# ===========================================================================
# 5. Budget hard-stop: episode never exceeds its registered budget
# ===========================================================================
def test_budget_hard_stop(tmp_path):
    A = FixtureAgent("A", "eng", {i: [Note(f"tick {i}")] for i in range(10)},
                     turn_cost=0.60)
    roster = [RosterEntry("A", "eng", A)]
    rep = _episode(tmp_path, "bud1", Regime.CLAIMS, roster, turn_cap=10,
                   token_budget=1.00).run()
    assert rep["stop_reason"] == "budget"
    assert rep["turns_taken"] == 1               # 0.60 <= 1.00, next 0.60 blocked
    assert rep["spent"] == 0.60 and rep["remaining"] == 0.40
    assert rep["spent"] <= rep["budget"]         # hard cap never exceeded
    runner = EpisodeRunner(EpisodeConfig("bud1", Regime.CLAIMS, roster, 10,
                                         token_budget_usd=1.00), tmp_path)
    assert ev.BUDGET_STOP in _types(runner.event_log)


# ===========================================================================
# 6. Ledger + event chains verify; tamper is detected
# ===========================================================================
def test_chain_verifies_and_detects_tamper(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    runner = _episode(tmp_path, "chn1", Regime.CLAIMS, roster, turn_cap=3)
    runner.run()
    assert verify_chain(runner.ledger.path).ok
    assert verify_chain(runner.event_log.path).ok

    # Tamper: inflate a settlement amount, keep its stored hash -> mismatch.
    path = runner.ledger.path
    lines = path.read_text().splitlines()
    idx = next(i for i, ln in enumerate(lines) if json.loads(ln)["type"] == "settle")
    rec = json.loads(lines[idx])
    rec["data"]["amount"] = 9999.0
    lines[idx] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    res = verify_chain(path)
    assert not res.ok and "tamper" in (res.error or "")


# ===========================================================================
# 7. Split settlement on a two-stage task (spec + implement, no review share)
# ===========================================================================
def test_two_stage_split_settlement(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""),
                                      _spec("idea1", split=SPLIT_TWO_STAGE)]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    rep = _episode(tmp_path, "two1", Regime.CLAIMS, roster, turn_cap=3).run()
    assert rep["merged"] == 1
    # spec->A 25, implement->B 75, reviewer C paid 0 (still reviewed the merge)
    assert rep["wallets"] == {"A": 25.0, "B": 75.0, "C": 0.0}
    assert rep["treasury"] == 900.0              # remainder 0; escrow zeroed


# ===========================================================================
# 8. Conservation invariant: internal money is conserved; compute is metered
# ===========================================================================
def test_money_conservation(tmp_path):
    runner, _ = _two_idea_episode(tmp_path, "cons1", policy="receipts")
    w = runner.wallets
    starting = runner.config.starting_capital_usd
    treasury = w.balance(ACCT_TREASURY)
    escrows = sum(v for k, v in w.balances().items() if k.startswith("escrow:"))
    agents = sum(w.agent_balance(e.agent_id) for e in runner.config.roster)
    assert round(treasury + escrows + agents, 6) == starting      # internal
    assert round(w.balance(ACCT_COMPUTE) + w.total_spend(), 6) == \
        runner.config.token_budget_usd                            # compute pool


# ===========================================================================
# 9. Per-idea P&L aggregation on a fixture episode with two ideas (v33-A)
# ===========================================================================
def test_per_idea_pnl(tmp_path):
    runner, rep = _two_idea_episode(tmp_path, "pnl1", policy="receipts")
    w = runner.wallets
    # idea1: merged (settled 100) minus 3 turns * 0.5 spend = 98.5
    assert w.idea_settled("idea1") == 100.0
    assert w.idea_spend("idea1") == 1.5
    assert w.idea_pnl("idea1") == 98.5
    # idea2: never merged (settled 0) minus 3 turns * 0.5 spend = -1.5
    assert w.idea_settled("idea2") == 0.0
    assert w.idea_pnl("idea2") == -1.5
    assert w.idea_pnl("idea1") > 0 > w.idea_pnl("idea2")


# ===========================================================================
# 10. Allocation round: `receipts` grows the winner, cuts the loss-maker (v33-A)
# ===========================================================================
def test_receipts_allocation_grows_and_cuts(tmp_path):
    runner, _ = _two_idea_episode(tmp_path, "alloc1", policy="receipts")
    treasury_before = runner.wallets.balance(ACCT_TREASURY)
    result = runner.allocate()
    assert "idea1" in result.grown_ideas          # net +98.5 -> grow
    assert "idea2" in result.cut_ideas            # net -1.5  -> cut
    assert result.idea_budgets.get("idea1", {}).get("turns", 0) >= 1
    assert "idea2" not in result.idea_budgets     # cut ideas get no budget
    # CUT cancels idea2's open task t2 and refunds its escrow to treasury
    assert runner.board.tasks["t2"].state is TaskState.CANCELLED
    assert runner.wallets.balance(ACCT_TREASURY) == treasury_before + 40.0
    assert ev.ALLOC_GROW in _types(runner.event_log)
    assert ev.ALLOC_CUT in _types(runner.event_log)


# ===========================================================================
# 11. `outcome` diverges from `receipts` on the glue-work fixture (v33-A)
# ===========================================================================
def test_outcome_vs_receipts_glue_divergence(tmp_path):
    # G does spec + review on two tasks; I implements both. Same merged volume;
    # different STACK credit. Outcome (implement-only) benches the glue worker;
    # receipts (full flow) retains it.
    G = FixtureAgent("G", "glue", {
        0: [CreateIdea("idea1", "t", ""), _spec("idea1"), _spec("idea1")],
        2: [Review("t1")], 4: [Review("t2")]})
    I = FixtureAgent("I", "eng", {
        1: [Claim("t1"), Submit("t1", GOOD_IMPL)],
        3: [Claim("t2"), Submit("t2", GOOD_IMPL)]})
    roster = [RosterEntry("G", "glue", G), RosterEntry("I", "eng", I)]
    runner = _episode(tmp_path, "glue1", Regime.CLAIMS, roster, turn_cap=5)
    runner.run()

    w, board = runner.wallets, runner.board
    assert w.agent_receipts("G") == 80.0   # spec .2 + review .2, x2 tasks x100
    assert w.agent_receipts("I") == 120.0  # implement .6, x2 tasks x100

    agg = aggregate(w, board, ["G", "I"])
    receipts = ReceiptsPolicy().allocate(agg, runner.config)
    outcome = OutcomePolicy().allocate(agg, runner.config)
    assert "G" in outcome.benched_agents        # implement-volume 0 -> benched
    assert "G" not in receipts.benched_agents    # receipt flow > 0 -> retained
    assert outcome.benched_agents != receipts.benched_agents


# ===========================================================================
# 12. A benched agent takes no turns in the next episode (v33-A)
# ===========================================================================
def test_benched_agent_takes_no_turns(tmp_path):
    I = FixtureAgent("I", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")],
                                  1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    G = FixtureAgent("G", "glue", {})   # benched -> never scheduled
    roster = [RosterEntry("I", "eng", I),
              RosterEntry("G", "glue", G, benched=True)]
    cfg = EpisodeConfig("bench2", Regime.CLAIMS, roster, turn_cap=3)
    assert [e.agent_id for e in cfg.active_roster()] == ["I"]  # G excluded
    runner = EpisodeRunner(cfg, tmp_path)
    runner.run()
    turn_actors = [r.data["actor"] for r in runner.event_log.records()
                   if r.type == ev.TURN]
    assert turn_actors and "G" not in turn_actors


# ===========================================================================
# 13. COMMAND: only the manager may create tasks/ideas
# ===========================================================================
def test_command_only_manager_creates(tmp_path):
    M = FixtureAgent("M", "manager", {0: [CreateIdea("idea1", "t", "")]})
    # E is not the manager; its spec attempt must be rejected, not applied
    E = FixtureAgent("E", "eng", {1: [_spec("idea1")]})
    roster = [RosterEntry("M", "manager", M, manager=True),
              RosterEntry("E", "eng", E)]
    runner = _episode(tmp_path, "cmd2", Regime.COMMAND, roster, turn_cap=2)
    runner.run()
    assert runner.board.tasks == {}              # E created nothing
    rej = [r for r in runner.event_log.records() if r.type == ev.ACTION_REJECTED]
    assert any("manager" in r.data["reason"] for r in rej)


# ===========================================================================
# 14. Underfunded bounty is refused (can't post a bounty treasury can't cover)
# ===========================================================================
def test_underfunded_bounty_refused(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""),
                                      _spec("idea1", bounty=5000.0)]})
    roster = [RosterEntry("A", "eng", A)]
    runner = _episode(tmp_path, "fund1", Regime.CLAIMS, roster, turn_cap=1)
    runner.run()
    assert runner.board.tasks == {}
    rej = [r for r in runner.event_log.records() if r.type == ev.ACTION_REJECTED]
    assert any("underfunded" in r.data["reason"] for r in rej)


# ===========================================================================
# 15. LLMAgent stub refuses (D1a is offline; no key, no budget)
# ===========================================================================
def test_llm_agent_refuses_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = LLMAgent("L", "eng", model="claude-haiku", budget_registered=False)
    with pytest.raises(NotImplementedError, match="ANTHROPIC_API_KEY"):
        agent.propose(view=None)


def test_llm_agent_refuses_without_registered_budget(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    agent = LLMAgent("L", "eng", model="claude-haiku", budget_registered=False)
    with pytest.raises(NotImplementedError, match="registered.*budget"):
        agent.propose(view=None)


# ===========================================================================
# 16. Resume: a fresh runner over the same dir continues the timeline
# ===========================================================================
def test_resume_continues_episode(tmp_path):
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    # run 1: cap 2 -> founding+spec, claim+submit, but NOT reviewed yet
    r1 = _episode(tmp_path, "res1", Regime.CLAIMS, roster, turn_cap=2).run()
    assert r1["turns_taken"] == 2 and r1["merged"] == 0
    assert r1["stop_reason"] == "cap"
    # run 2: resume with a higher cap -> review + settle happen
    cfg2 = EpisodeConfig("res1", Regime.CLAIMS, roster, turn_cap=3)
    r2 = EpisodeRunner(cfg2, tmp_path).run()
    assert r2["turns_taken"] == 3 and r2["merged"] == 1
    assert r2["wallets"] == {"A": 20.0, "B": 60.0, "C": 20.0}
    assert r2["chain_ok_events"] and r2["chain_ok_ledger"]


# ===========================================================================
# 17. Deterministic workspace commits: identical episodes -> identical hashes
# ===========================================================================
def test_deterministic_commit_hashes(tmp_path):
    def run_once(root):
        A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
        B = FixtureAgent("B", "eng", {1: [Claim("t1"), Submit("t1", GOOD_IMPL)]})
        C = FixtureAgent("C", "eng", {2: [Review("t1")]})
        roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
                  RosterEntry("C", "eng", C)]
        runner = _episode(root, "det", Regime.CLAIMS, roster, turn_cap=3)
        runner.run()
        sub = [r for r in runner.event_log.records()
               if r.type == ev.TASK_SUBMITTED][0]
        return sub.data["commit"]

    h1 = run_once(tmp_path / "a")
    h2 = run_once(tmp_path / "b")
    assert h1 == h2 and len(h1) == 40   # reproducible sha1 commit receipt


# ===========================================================================
# 18. Split fixed at claim time (the bills): a later proposed split cannot move
#     an already-locked claim
# ===========================================================================
def test_split_locked_at_claim(tmp_path):
    # Claim overrides the proposed split; settlement must honor the LOCKED one.
    locked = {ROLE_SPEC: 0.5, ROLE_IMPLEMENT: 0.5}
    A = FixtureAgent("A", "eng", {0: [CreateIdea("idea1", "t", ""), _spec("idea1")]})
    B = FixtureAgent("B", "eng", {1: [Claim("t1", split=locked),
                                      Submit("t1", GOOD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    runner = _episode(tmp_path, "lock1", Regime.CLAIMS, roster, turn_cap=3)
    rep = runner.run()
    assert runner.board.tasks["t1"].split_locked == locked
    assert rep["wallets"] == {"A": 50.0, "B": 50.0, "C": 0.0}


# ===========================================================================
# 19. Every merge settlement is a receipt carrying the commit + test digest
# ===========================================================================
def test_settlement_receipts_carry_provenance(tmp_path):
    runner, _ = _two_idea_episode(tmp_path, "prov1", policy="receipts")
    settles = [r for r in runner.ledger.records() if r.type == "settle"]
    assert settles, "a merged task must produce settle receipts"
    for r in settles:
        assert len(r.data["commit"]) == 40          # workspace commit
        assert len(r.data["test_digest"]) == 64      # sha256 of reviewer output
        assert r.data["idea"] == "idea1"
        assert r.data["role"] in (ROLE_SPEC, ROLE_IMPLEMENT, ROLE_REVIEW)


# ===========================================================================
# 20. run_allocation dispatch + manager policy applies the adapter's decision
# ===========================================================================
def test_manager_allocation_policy_uses_adapter(tmp_path):
    decision = {"grown_ideas": ["idea1"], "cut_ideas": ["idea2"],
                "benched_agents": ["B"], "idea_budgets": {"idea1": {"turns": 5}}}
    M = FixtureAgent("M", "manager", {0: [CreateIdea("idea1", "t", ""),
                                          CreateIdea("idea2", "t2", "")]},
                     allocation=decision)
    roster = [RosterEntry("M", "manager", M, manager=True)]
    cfg = EpisodeConfig("mgr1", Regime.COMMAND, roster, turn_cap=1,
                        allocation_policy="manager")
    runner = EpisodeRunner(cfg, tmp_path)
    runner.run()
    _, result = run_allocation("manager", runner.wallets, runner.board,
                               ["M"], cfg, manager_agent=M)
    assert result.grown_ideas == ["idea1"] and result.cut_ideas == ["idea2"]
    assert result.benched_agents == ["B"]


# --- shared fixtures ---------------------------------------------------------
def _two_idea_episode(tmp_path, episode_id, policy):
    """CLAIMS episode: idea1 merges a task (profitable); idea2 spends compute on
    a task that fails review and never merges (loss-making)."""
    A = FixtureAgent("A", "eng", {
        0: [CreateIdea("idea1", "shortener", ""), CreateIdea("idea2", "pastebin", ""),
            _spec("idea1")],
        3: [_spec("idea2", bounty=40.0)]})
    B = FixtureAgent("B", "eng", {
        1: [Claim("t1"), Submit("t1", GOOD_IMPL)],
        4: [Claim("t2"), Submit("t2", BAD_IMPL)]})
    C = FixtureAgent("C", "eng", {2: [Review("t1")], 5: [Review("t2")]})
    roster = [RosterEntry("A", "eng", A), RosterEntry("B", "eng", B),
              RosterEntry("C", "eng", C)]
    runner = _episode(tmp_path, episode_id, Regime.CLAIMS, roster, turn_cap=6,
                      policy=policy)
    rep = runner.run()
    return runner, rep


# --- tiny helpers for the pure-board unit test -------------------------------
def _mk_idea():
    from companysim.protocol import Idea
    return Idea("i", "n", "r", "A")


def _seed_submitted(board, claimant):
    """Drive a board to a SUBMITTED task via synthetic event records."""
    from companysim.ledger import Record

    def rec(t, d):
        return Record(0, "", t, d, "", None, "")

    board.ideas["i"] = _mk_idea()
    board.apply_event(rec(ev.TASK_SPECED, {
        "task_id": "t1", "idea": "i", "actor": "A", "title": "x", "brief": "x",
        "acceptance_tests": ["test_acc.py"], "bounty": 100.0,
        "split": SPLIT_FULL, "assignee": None}))
    board.apply_event(rec(ev.TASK_CLAIMED, {
        "task_id": "t1", "actor": claimant, "split_locked": SPLIT_FULL}))
    board.apply_event(rec(ev.TASK_SUBMITTED, {
        "task_id": "t1", "actor": claimant, "commit": "0" * 40, "files": ["tool.py"]}))

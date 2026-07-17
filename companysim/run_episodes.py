"""D1b episode driver (SPEC v33-F Arc 1-prime): founding + command + command +
claims + claims-THAT-SHIPS. Real spend, real Sonnet/Haiku employees.

Runs ONE episode per invocation (`python3 -m companysim.run_episodes <N>`, N in
0..4) so each stays inside a foreground shell window; cross-episode state
(benched roster, the prior product summary) is derived from the committed logs —
the ledger is the manuscript. Budget law: $20/episode registered in the config
BEFORE the run. The founding episode counts a sanity ping against its budget and
runs the v33-F reconciliation + fallback-to-A rule at its close.

Roster (mixed, Haiku-heavy — 2 Sonnet, 3 Haiku): a Sonnet manager + Sonnet lead
engineer carry the load-bearing spec/implement; Haiku engineers/writers do the
rest. HR trials (v33-I) draw on a Sonnet+Haiku candidate pool.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import events as ev
from . import llm
from .agent import LLMAgent
from .config import EpisodeConfig, Regime, RosterEntry
from .ledger import ACCT_COMPUTE, ACCT_TREASURY, Wallets, verify_chain
from .runner import EpisodeRunner

ROOT = Path(__file__).resolve().parent
EP_DIR = ROOT / "episodes"
SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5-20251001"
BUDGET = 20.0
EXPLORATION_FLOOR = 0.10

# Employee roster (ids, models, base role). Reused across episodes; guidance and
# benched flags are set per episode.
EMPLOYEES = [
    ("M", SONNET, "manager"),
    ("Dae", SONNET, "engineer"),
    ("Ravi", HAIKU, "engineer"),
    ("Sol", HAIKU, "engineer"),
    ("Wren", HAIKU, "writer"),
]

EPISODES = [
    ("ep1_founding", Regime.COMMAND, "manager", 20),
    ("ep2_command", Regime.COMMAND, "manager", 18),
    ("ep3_command", Regime.COMMAND, "manager", 18),
    ("ep4_claims", Regime.CLAIMS, "receipts", 18),
    ("ep5_claims_ships", Regime.CLAIMS, "receipts", 20),
]

# v33-F founding brief + seed shortlist + the B1 buyer order (surfaced verbatim
# in the founding view; the org debates and CHOOSES).
FOUNDING_SEED = {
    "brief": "build a small self-hostable infrastructure tool",
    "panel": "Thiel/Musk/Bezos founding panel (v33-F) — advisory, not binding",
    "shortlist": {
        "A": "pocket notary — the atom, a hash-chained receipt ledger; guaranteed shippable (fallback).",
        "F": "agent payroll meter (RECOMMENDED LEAD) — A plus per-idea/per-agent cost attribution "
             "and a shareable report; ingests ONLY structured usage records (JSONL), never scraped "
             "text (a parser that invents a number builds a liar, not a ledger).",
        "H": "drift/eval receipt harness — counterparty tests as the product itself (Thiel's hedge).",
    },
    "non_negotiable_and_B1_order": (
        "Whatever you pick MUST meter its own founding episode and reconcile its ledger to the "
        "founder's real API bill within 5% — framed as the B1 buyer's escrowed pre-order: "
        "'per-agent cost attribution that reconciles to my bill'. If reconciliation fails, the "
        "budget falls back to A (never end empty-handed)."),
    "off_seed": "C, D, G stay OFF the seed; resurrect one only by PLEDGING your own wallet credits.",
    "arc": "founding + command + command + claims + claims-THAT-SHIPS (the last claims episode is the launch).",
    "instruction": "Debate the choice IN NOTES (each of you argue), then the manager CreateIdea the "
                   "chosen product (use idea id 'idea_F' if you pick the meter) and spec the first tasks.",
}

# --- guidance --------------------------------------------------------------
G_MANAGER_CODE = (
    "You are the MANAGER. Only you create ideas and create/assign tasks. Each turn: keep the "
    "product moving. Spec SMALL code tasks with a tight pytest acceptance test; in the brief name "
    "the EXACT module filename and function signatures the implementer must create so the test's "
    "imports resolve (e.g. 'create meter.py with cost(model, usage)->float'). Set assignee to a "
    "specific engineer, and ensure a DIFFERENT engineer reviews (reviewer can never be the "
    "implementer). Spec 2-3 tasks up front so engineers have work. Keep code self-contained in the "
    "task dir (no cross-file imports). Fund bounties from the treasury (1000 credits).")
G_ENGINEER = (
    "You are an ENGINEER. If a task is OPEN and assigned to you, CLAIM it and SUBMIT a minimal "
    "implementation that makes the acceptance test pass. The task's 'acceptance_test_source' field "
    "shows the EXACT test you must satisfy — match its imports, function names, and signatures "
    "precisely (it is the contract). If a task is SUBMITTED and you are NOT its implementer, REVIEW "
    "it (this runs the tests and merges or rejects). Do not review your own work. Write real, correct "
    "code — a rejected submission pays nothing.")
G_WRITER = (
    "You are the WRITER/glue. Author acceptance criteria for non-code work, and ATTEST non-code "
    "deliverables authored by others (you can never attest your own or the implementer's work). You "
    "may also spec/review small code tasks. In the launch episode, write the README and launch copy.")
G_CLAIMS = (
    " OPEN BOARD (no manager): any agent may spec or claim. Spec small tasks with tight tests, claim "
    "open tasks, review others' submissions (never your own). Splits lock at claim.")


def load_prior(idx: int):
    """Derive cross-episode state from committed logs (benched set + product summary)."""
    benched, summary, product = set(), [], None
    if idx == 0:
        return benched, summary, product
    prev_id = EPISODES[idx - 1][0]
    log = ev.EventLog(EP_DIR / prev_id / "events.jsonl")
    ideas, merged = {}, 0
    for r in log.records():
        if r.type == ev.ALLOC_BENCH:
            benched.add(r.data["agent_id"])
        elif r.type == ev.IDEA_CREATED:
            ideas[r.data["idea_id"]] = r.data.get("name", "")
            if product is None or "idea_f" in r.data["idea_id"].lower():
                product = (r.data["idea_id"], r.data.get("name", ""))
        elif r.type in (ev.TASK_MERGED, ev.ATTESTED):
            merged += 1
    summary = [f"{k}: {v}" for k, v in ideas.items()]
    # Floor: never let the active roster fall below 3 (keep the demo runnable).
    active = [e[0] for e in EMPLOYEES if e[0] not in benched]
    while len(active) < 3 and benched:
        keep = benched.pop()
        active.append(keep)
    return benched, {"prev": prev_id, "ideas": summary, "merged": merged}, product


def build_roster(idx: int, benched: set):
    regime = EPISODES[idx][1]
    is_cmd = regime is Regime.COMMAND
    prior_note = ""
    if idx > 0:
        _, summary, product = load_prior(idx)
        prod = f"{product[0]} ({product[1]})" if product else "your chosen product"
        prior_note = (f"\nCONTINUITY: this is episode {idx + 1}. In prior episodes the company chose "
                      f"and has been building {prod}. Re-establish that idea at the start of this "
                      f"episode and ADVANCE it (add a real feature, harden it, or in the launch "
                      f"episode ship its docs). Prior ideas: {summary.get('ideas')}.")
    ships = idx == len(EPISODES) - 1
    launch_note = ("\nLAUNCH EPISODE: also produce the launch artifacts as ATTESTED non-code tasks — "
                   "a README.md (title, what it is, self-host/install steps, a usage example) and "
                   "LAUNCH.md (short launch copy). These settle on attestation by a non-author. Do "
                   "NOT publish anywhere; the workspace is the deliverable.") if ships else ""
    roster = []
    for aid, model, role in EMPLOYEES:
        if role == "manager":
            g = G_MANAGER_CODE
        elif role == "writer":
            g = G_WRITER
        else:
            g = G_ENGINEER
        if not is_cmd:
            g = g.replace("Only you create ideas and create/assign tasks.", "").strip() + G_CLAIMS
        g = g + prior_note + launch_note
        # Founding-episode steering: the manager DECIDES on its first turn; the
        # rest of the org acts, not just debates.
        if idx == 0 and role == "manager":
            g += ("\nFOUNDING — ACT NOW: on your FIRST turn, make the product decision. CreateIdea for "
                  "the chosen product (the panel's recommended lead is F, the agent payroll meter — use "
                  "idea id 'idea_F') with a Note explaining WHY you chose it over A (pocket notary) and "
                  "H (eval harness), then spec 2-3 small code tasks assigned to specific engineers. The "
                  "first task should build the meter itself (e.g. meter.py with cost(model, usage)->float "
                  "and a per-agent report). The engineers will argue in their Notes; you lead.")
        if idx == 0 and role != "manager":
            g += ("\nFOUNDING: argue your view of the product choice in a Note (this is the debate). If the "
                  "manager has already assigned you an OPEN task, CLAIM and build it too — actions beat talk.")
        # v33-I HR nudge in episode 3: the manager may hire.
        if idx == 2 and role == "manager":
            g += ("\nHR (optional, v33-I): you may open a REQUISITION for an engineer role tied to your "
                  "product idea, then TRIAL_HIRE it against an OPEN code task with candidates "
                  "['cand_sonnet','cand_haiku'] — the trial gives both the same task and hires the "
                  "cheapest that passes the counterparty test.")
        agent = LLMAgent(aid, role, model=model, budget_registered=True,
                         max_tokens=8000, guidance=g)
        roster.append(RosterEntry(aid, role, agent, manager=(role == "manager" and is_cmd),
                                  benched=(aid in benched)))
    return roster


def candidate_pool():
    return {
        "cand_sonnet": LLMAgent("cand_sonnet", "engineer", model=SONNET,
                                budget_registered=True, max_tokens=4000,
                                guidance=G_ENGINEER),
        "cand_haiku": LLMAgent("cand_haiku", "engineer", model=HAIKU,
                               budget_registered=True, max_tokens=4000,
                               guidance=G_ENGINEER),
    }


def make_config(idx: int):
    eid, regime, policy, cap = EPISODES[idx]
    benched, _, _ = load_prior(idx)
    roster = build_roster(idx, benched)
    kw = dict(episode_id=eid, regime=regime, roster=roster, turn_cap=cap,
              token_budget_usd=BUDGET, allocation_policy=policy,
              exploration_floor=EXPLORATION_FLOOR, capture_transcripts=True,
              # Candidates are hirable ONLY via trial (v33-I); expose the pool only
              # in the HR episode so the manager doesn't mistake them for engineers.
              candidate_pool=candidate_pool() if idx == 2 else {})
    if idx == 0:
        kw["founding_seed"] = FOUNDING_SEED
        # v33-B1: the buyer wallet holds the escrowed reconciliation pre-order;
        # the inbox carries ONLY that order (the inbox opens to real clients at launch).
        kw["buyer_wallets"] = [{"buyer_id": "B1", "amount": 200.0}]
        kw["inbox_seed"] = [{
            "inbox_id": "B1_order", "buyer": "B1", "amount": 200.0,
            "text": ("B1 buyer pre-order: per-agent cost attribution that reconciles to my API bill "
                     "within 5%. Deliverable: a meter that ingests the usage JSONL and reports "
                     "per-agent/per-model cost plus a total.")}]
    return EpisodeConfig(**kw)


def run_episode(idx: int) -> dict:
    llm.load_env()
    cfg = make_config(idx)
    cfg.validate()
    runner = EpisodeRunner(cfg, EP_DIR)
    # Budget law: dump the registered config BEFORE the run.
    _dump_config(runner, cfg)
    # Founding: sanity-ping the API and charge it to episode 1's budget.
    if idx == 0 and len([r for r in runner.event_log.records()]) == 0:
        _sanity_ping(runner)
    report = runner.run()
    # v33-F reconciliation + fallback rule at the founding close.
    recon = None
    if idx == 0:
        recon = runner.reconcile(tolerance=0.05)
    # Allocation round (regime-consistent policy).
    manager_agent = None
    if cfg.allocation_policy == "manager":
        manager_agent = next(e.agent for e in cfg.roster if e.manager)
    alloc = runner.allocate(manager_agent=manager_agent)
    # Verify chain + conservation; snapshot.
    w = runner.wallets
    de = round(sum(w.balances().values()), 6)
    out = {
        "episode": cfg.episode_id, "regime": cfg.regime.value, "policy": cfg.allocation_policy,
        "stop_reason": report["stop_reason"], "turns": report["turns_taken"],
        "merged": report["merged"], "spent_usd": round(runner.meter.spent(), 6),
        "budget_usd": BUDGET, "treasury": w.balance(ACCT_TREASURY),
        "compute_remaining": round(runner.meter.remaining(), 6),
        "chain_ok": verify_chain(runner.event_log.path).ok and verify_chain(runner.ledger.path).ok,
        "double_entry_zero": de,
        "ideas": [{"id": i.idea_id, "name": i.name, "active": i.active,
                   "pnl": w.idea_pnl(i.idea_id)} for i in runner.board.ideas.values()],
        "wallets": {e.agent_id: w.agent_balance(e.agent_id) for e in cfg.roster},
        "grown": alloc.grown_ideas, "cut": alloc.cut_ideas, "benched": alloc.benched_agents,
        "hires": [r.data for r in runner.event_log.records() if r.type == ev.HIRE],
        "pledges": [r.data for r in runner.event_log.records() if r.type == ev.PLEDGE],
        "firsts": _read_firsts(runner),
        "reconciliation": recon,
    }
    (runner.dir / "report.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def _dump_config(runner, cfg):
    doc = {
        "episode_id": cfg.episode_id, "regime": cfg.regime.value,
        "allocation_policy": cfg.allocation_policy, "turn_cap": cfg.turn_cap,
        "token_budget_usd": cfg.token_budget_usd,
        "starting_capital_usd": cfg.starting_capital_usd,
        "exploration_floor": cfg.exploration_floor,
        "roster": [{"agent_id": e.agent_id, "role": e.role,
                    "model": getattr(e.agent, "model", "?"), "manager": e.manager,
                    "benched": e.benched} for e in cfg.roster],
        "buyer_wallets": cfg.buyer_wallets, "inbox_seed": cfg.inbox_seed,
        "candidate_pool": {k: getattr(v, "model", "?") for k, v in cfg.candidate_pool.items()},
        "founding_seed": cfg.founding_seed,
    }
    (runner.dir / "config.json").write_text(json.dumps(doc, indent=2, default=str))


def _sanity_ping(runner):
    """One minimal call, counted against episode 1's budget (SPEC)."""
    from . import pricing
    client = llm.get_client()
    resp = client.messages.create(
        model=HAIKU, max_tokens=16,
        messages=[{"role": "user", "content": "reply 'ok'"}])
    usage = {"input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens}
    cost = pricing.cost_from_usage(HAIKU, usage)
    runner._capture_transcript({"agent": "runner", "model": HAIKU, "turn": "sanity_ping",
                                "usage": usage, "cost": cost, "note": "sanity ping"})
    runner.meter.charge(min(cost, runner.meter.remaining()), agent_id="runner",
                        idea=None, turn=-1, ts=runner.clock.tick(), reason="sanity_ping")


def _read_firsts(runner):
    if not runner.firsts_path.exists():
        return []
    return [json.loads(l) for l in runner.firsts_path.read_text().splitlines() if l.strip()]


def main():
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    out = run_episode(idx)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()

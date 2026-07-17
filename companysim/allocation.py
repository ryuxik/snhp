"""The allocation round (v33-A): at every episode boundary the org's budgets,
headcount and continuation are set FROM THE RECEIPT LEDGER ALONE — the org
chart is downstream of the ledger.

Two steps:
  1. `aggregate(...)` folds the money ledger + the task board into per-idea and
     per-agent receipt aggregates (the provenance spine made numeric).
  2. an `AllocationPolicy` turns those aggregates into an `AllocationResult`:
     next-episode idea budgets (turns/tokens), which ideas GROW, which ideas
     and agents are CUT/BENCHED, plus the GROW/CUT/BENCH/REASSIGN org events the
     replay page renders org evolution from.

Three policies ship (swappable per episode config), and the CONTRAST between
them is the registered D2 science (report-not-verdict until then):
  * `receipts` — allocate proportional to NET receipt flow (settled − spend);
    scores agents by their FULL receipt flow, so middle roles (spec/review) are
    funded by construction.
  * `outcome`  — allocate proportional to raw MERGED VOLUME; scores agents by
    IMPLEMENT volume only, so spec/review (glue) work is invisible → defunded.
  * `manager`  — the COMMAND manager decides via its adapter (may drift with the
    manager's view; that drift is the point of the contrast).

Value-anchor honesty (v33-A, registered limit): receipts measure VERIFIED WORK
(counterparty tests passed), not market value. An idea can compound receipts
while being a bad product; an external demand signal is a registered-open D2+
extension, not assumed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import events as ev
from .config import EpisodeConfig, RosterEntry
from .ledger import Wallets
from .protocol import TaskBoard, TaskState


@dataclass
class IdeaAgg:
    idea_id: str
    settled: float = 0.0
    spend: float = 0.0
    merged_count: int = 0
    merged_volume: float = 0.0

    @property
    def net_receipts(self) -> float:
        return round(self.settled - self.spend, 10)


@dataclass
class AgentAgg:
    agent_id: str
    receipts: float = 0.0          # full receipt flow (all roles)
    implement_count: int = 0
    implement_volume: float = 0.0  # merged bounty as IMPLEMENTER only


@dataclass
class Aggregates:
    ideas: dict            # idea_id -> IdeaAgg
    agents: dict           # agent_id -> AgentAgg


def aggregate(wallets: Wallets, board: TaskBoard,
              agent_ids: list[str]) -> Aggregates:
    """Fold the ledger + board into the provenance aggregates (v33-A)."""
    ideas: dict[str, IdeaAgg] = {i: IdeaAgg(i) for i in board.ideas}
    agents: dict[str, AgentAgg] = {a: AgentAgg(a) for a in agent_ids}

    for task in board.tasks.values():
        if task.state is not TaskState.MERGED:
            continue
        ia = ideas.setdefault(task.idea, IdeaAgg(task.idea))
        ia.merged_count += 1
        ia.merged_volume = round(ia.merged_volume + task.bounty, 10)
        if task.claimant:
            ag = agents.setdefault(task.claimant, AgentAgg(task.claimant))
            ag.implement_count += 1
            ag.implement_volume = round(ag.implement_volume + task.bounty, 10)

    for idea_id, ia in ideas.items():
        ia.settled = wallets.idea_settled(idea_id)
        ia.spend = wallets.idea_spend(idea_id)
    for agent_id, ag in agents.items():
        ag.receipts = wallets.agent_receipts(agent_id)

    return Aggregates(ideas, agents)


@dataclass
class AllocationResult:
    policy: str
    idea_scores: dict = field(default_factory=dict)
    agent_scores: dict = field(default_factory=dict)
    idea_budgets: dict = field(default_factory=dict)   # idea -> {turns, tokens}
    grown_ideas: list = field(default_factory=list)
    cut_ideas: list = field(default_factory=list)
    benched_agents: list = field(default_factory=list)
    reassignments: dict = field(default_factory=dict)  # agent -> idea
    events: list = field(default_factory=list)         # (type, actor, data)

    def next_roster(self, prev_roster: list) -> list:
        """The next episode's roster: benched agents flagged, reassignments
        applied (v33-A: agents whose flow does not cover cost are benched)."""
        out = []
        for e in prev_roster:
            out.append(RosterEntry(
                agent_id=e.agent_id, role=e.role, agent=e.agent,
                manager=e.manager,
                idea=self.reassignments.get(e.agent_id, e.idea),
                benched=e.agent_id in self.benched_agents))
        return out


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------
def _budget_split(scores: dict, pool_turns: int, pool_tokens: float) -> dict:
    """Distribute a pool proportional to positive scores (deterministic)."""
    positive = {k: v for k, v in scores.items() if v > 0}
    total = sum(positive.values())
    budgets = {}
    if total <= 0:
        return budgets
    for idea in sorted(positive, key=lambda k: (-positive[k], k)):
        share = positive[idea] / total
        budgets[idea] = {
            "turns": max(1, round(pool_turns * share)),
            "tokens": round(pool_tokens * share, 4),
        }
    return budgets


def _org_events(actor: str, grown: list, cut: list, benched: list,
                reassign: dict, budgets: dict) -> list:
    out = [(ev.ALLOCATION_ROUND, actor, {"grown": grown, "cut": cut,
            "benched": benched, "budgets": budgets})]
    for idea in grown:
        out.append((ev.ALLOC_GROW, actor, {"idea_id": idea,
                    "budget": budgets.get(idea, {})}))
    for idea in cut:
        out.append((ev.ALLOC_CUT, actor, {"idea_id": idea}))
    for agent in benched:
        out.append((ev.ALLOC_BENCH, actor, {"agent_id": agent}))
    for agent, idea in reassign.items():
        out.append((ev.ALLOC_REASSIGN, actor, {"agent_id": agent, "idea": idea}))
    return out


class ReceiptsPolicy:
    """Allocate by NET receipt flow; score agents by their FULL flow (middle
    roles funded)."""
    name = "receipts"

    def allocate(self, agg: Aggregates, config: EpisodeConfig,
                 manager_agent=None) -> AllocationResult:
        idea_scores = {i: a.net_receipts for i, a in agg.ideas.items()}
        agent_scores = {a: g.receipts for a, g in agg.agents.items()}
        cut = sorted(i for i, s in idea_scores.items() if s <= 0)
        grown = sorted((i for i, s in idea_scores.items() if s > 0),
                       key=lambda k: (-idea_scores[k], k))
        benched = sorted(a for a, s in agent_scores.items() if s <= 0)
        budgets = _budget_split(idea_scores, config.turn_cap,
                                config.token_budget_usd)
        actor = f"allocation:{self.name}"
        return AllocationResult(
            self.name, idea_scores, agent_scores, budgets, grown, cut,
            benched, {}, _org_events(actor, grown, cut, benched, {}, budgets))


class OutcomePolicy:
    """Allocate by raw MERGED VOLUME; score agents by IMPLEMENT volume only —
    spec/review credit is invisible (the sacrifice confound)."""
    name = "outcome"

    def allocate(self, agg: Aggregates, config: EpisodeConfig,
                 manager_agent=None) -> AllocationResult:
        idea_scores = {i: a.merged_volume for i, a in agg.ideas.items()}
        agent_scores = {a: g.implement_volume for a, g in agg.agents.items()}
        cut = sorted(i for i, s in idea_scores.items() if s <= 0)
        grown = sorted((i for i, s in idea_scores.items() if s > 0),
                       key=lambda k: (-idea_scores[k], k))
        benched = sorted(a for a, s in agent_scores.items() if s <= 0)
        budgets = _budget_split(idea_scores, config.turn_cap,
                                config.token_budget_usd)
        actor = f"allocation:{self.name}"
        return AllocationResult(
            self.name, idea_scores, agent_scores, budgets, grown, cut,
            benched, {}, _org_events(actor, grown, cut, benched, {}, budgets))


class ManagerPolicy:
    """The COMMAND manager decides via its adapter (v33-A 'manager discretion').
    The manager returns a decision dict; the harness applies it verbatim and
    logs the org events under the manager as actor."""
    name = "manager"

    def allocate(self, agg: Aggregates, config: EpisodeConfig,
                 manager_agent=None) -> AllocationResult:
        if manager_agent is None:
            raise ValueError("manager policy requires the manager adapter")
        context = {
            "ideas": {i: vars(a) for i, a in agg.ideas.items()},
            "agents": {a: vars(g) for a, g in agg.agents.items()},
            "turn_cap": config.turn_cap,
            "token_budget_usd": config.token_budget_usd,
        }
        decision = manager_agent.propose_allocation(context) or {}
        grown = list(decision.get("grown_ideas", []))
        cut = list(decision.get("cut_ideas", []))
        benched = list(decision.get("benched_agents", []))
        reassign = dict(decision.get("reassignments", {}))
        budgets = dict(decision.get("idea_budgets", {}))
        actor = manager_agent.agent_id
        return AllocationResult(
            self.name, {}, {}, budgets, grown, cut, benched, reassign,
            _org_events(actor, grown, cut, benched, reassign, budgets))


POLICIES = {p.name: p for p in (ReceiptsPolicy(), OutcomePolicy(), ManagerPolicy())}


def run_allocation(policy_name: str, wallets: Wallets, board: TaskBoard,
                   agent_ids: list[str], config: EpisodeConfig,
                   manager_agent=None) -> tuple[Aggregates, AllocationResult]:
    """One allocation round: aggregate the ledger, then apply the policy."""
    if policy_name not in POLICIES:
        raise ValueError(f"unknown allocation policy {policy_name!r}")
    agg = aggregate(wallets, board, agent_ids)
    result = POLICIES[policy_name].allocate(agg, config, manager_agent)
    return agg, result

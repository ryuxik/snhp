"""Episode configuration + the founding brief (SPEC v33 D1a: "an episode = a
registered config (regime, agent roster, turn cap, token budget)").

Everything economically load-bearing is registered HERE before a run, per the
honesty rules (SPEC v33: "token budget + models registered pre-run"). The
budget is part of the episode config and MUST be set before the runner will
run (runner.py enforces).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# The founding brief (SPEC v33, founder decision, VERBATIM). The org picks its
# own product in the founding episode — see-where-it-goes is the point.
# ---------------------------------------------------------------------------
FOUNDING_BRIEF = "build a small self-hostable infrastructure tool"

# Default per-episode compute budget (SPEC v33 D1b: "initial cap $20/episode,
# founder may revise"). D1a fixture agents charge SIMULATED costs against it.
DEFAULT_TOKEN_BUDGET_USD = 20.00

# Default simulated per-turn compute cost for fixture agents (D1a only). Real
# LLM cost is measured post-hoc in D1b.
DEFAULT_TURN_COST_USD = 0.50


class Regime(enum.Enum):
    """How work is created + assigned (SPEC v33 "Regimes"; enforced by the
    protocol layer, not by prompt hope)."""

    COMMAND = "command"  # a designated MANAGER agent is the only task creator
    CLAIMS = "claims"    # open bounty board; any agent may spec or claim


# Pipeline roles a claim-split can pay (SPEC v33: "spec -> implement -> review").
ROLE_SPEC = "spec"
ROLE_IMPLEMENT = "implement"
ROLE_REVIEW = "review"
PIPELINE_ROLES = (ROLE_SPEC, ROLE_IMPLEMENT, ROLE_REVIEW)


@dataclass(frozen=True)
class RosterEntry:
    """One employee agent in an episode. `agent` is an Agent adapter
    (agent.py). `manager` marks the COMMAND-regime task creator. `idea` (v33-A)
    optionally scopes the agent to one idea after an allocation round."""

    agent_id: str
    role: str                 # free label (e.g. "engineer", "manager", "glue")
    agent: object             # Agent adapter (FixtureAgent / LLMAgent)
    manager: bool = False
    idea: str | None = None   # v33-A: allocation may scope an agent to an idea
    benched: bool = False     # v33-A: benched agents take no turns this episode


@dataclass(frozen=True)
class EpisodeConfig:
    """A registered episode. Immutable once built; the runner will not run
    without a token_budget (SPEC v33: "Budget must be set before run")."""

    episode_id: str
    regime: Regime
    roster: list[RosterEntry]
    turn_cap: int
    token_budget_usd: float = DEFAULT_TOKEN_BUDGET_USD
    starting_capital_usd: float = 1000.00   # treasury seed (internal economy)
    seed: int = 0
    brief: str = FOUNDING_BRIEF
    # v33-A: allocation policy applied at THIS episode's boundary to size the
    # NEXT episode. One of "receipts" | "outcome" | "manager" (allocation.py).
    allocation_policy: str = "receipts"
    # v33-A: per-idea turn/token budgets carried in from a prior allocation
    # round (empty in the founding episode).
    idea_budgets: dict = field(default_factory=dict)
    # ---- v33 extensions (all default to the D1a behaviour) ----
    # v33-B/G: external buyer wallets funded at episode start
    # (each {"buyer_id": str, "amount": float}). Arms-length: no wallet flows
    # org->buyer (the runner never credits a buyer from an idea).
    buyer_wallets: list = field(default_factory=list)
    # v33-G: founder-sanitized inbox records (each {"inbox_id","text",
    # "buyer"?,"amount"?}). Client text is DATA; triage converts it to a contract.
    inbox_seed: list = field(default_factory=list)
    # v33-I: hirable candidates {candidate_id: Agent adapter}. A trial runs each
    # against the same task; the cheapest that passes is hired.
    candidate_pool: dict = field(default_factory=dict)
    # v33-D: registered exploration floor (fraction of the round reserved for
    # zero-history ideas). Pick 10% (documented).
    exploration_floor: float = 0.10
    # v33-F: founding brief + seed shortlist + the B1 buyer order, surfaced in
    # the founding view (the org debates and chooses). Named founding_seed to
    # avoid colliding with the RNG `seed: int` field above.
    founding_seed: dict = field(default_factory=dict)
    # v33-E: retain full per-turn transcripts (prompt+response) to the episode dir.
    capture_transcripts: bool = False

    def manager_id(self) -> str | None:
        for e in self.roster:
            if e.manager:
                return e.agent_id
        return None

    def active_roster(self) -> list[RosterEntry]:
        """Agents that take turns this episode (benched excluded — v33-A)."""
        return [e for e in self.roster if not e.benched]

    def validate(self) -> None:
        """Registration checks (SPEC honesty rules)."""
        if self.turn_cap < 1:
            raise ValueError("turn_cap must be >= 1")
        if self.token_budget_usd <= 0:
            raise ValueError("token_budget_usd must be set > 0 before run")
        ids = [e.agent_id for e in self.roster]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate agent_id in roster")
        if not self.active_roster():
            raise ValueError("no active (non-benched) agents in roster")
        managers = [e for e in self.roster if e.manager]
        if self.regime is Regime.COMMAND and len(managers) != 1:
            raise ValueError("COMMAND regime needs exactly one manager")
        if self.regime is Regime.CLAIMS and managers:
            raise ValueError("CLAIMS regime has no manager")
        if self.allocation_policy not in ("receipts", "outcome", "manager"):
            raise ValueError(f"unknown allocation_policy {self.allocation_policy!r}")
        if self.allocation_policy == "manager" and self.regime is not Regime.COMMAND:
            raise ValueError("manager allocation policy requires COMMAND regime")
        if not 0.0 <= self.exploration_floor < 1.0:
            raise ValueError("exploration_floor must be in [0, 1)")
        # Constitutional: Opus is NEVER an in-sim employee (v33 + standing policy).
        for e in self.roster:
            model = getattr(e.agent, "model", None)
            if model and "opus" in str(model).lower():
                raise ValueError(
                    f"Opus is never in-sim ({e.agent_id} registered {model!r})")
        for cid, cand in self.candidate_pool.items():
            model = getattr(cand, "model", None)
            if model and "opus" in str(model).lower():
                raise ValueError(f"Opus candidate {cid} not allowed in-sim")

"""Token meter with a HARD pre-registered per-episode budget (SPEC v33 D1a
deliverable 8: "the runner HARD-STOPS the episode when the registered budget is
exhausted and logs the stop as an event").

The budget is a real cap: a turn runs only if its cost still fits, so the
episode NEVER exceeds the registered budget (a true hard cap, not an
after-the-fact tripwire). Each charge is a receipt on the money ledger
(ledger.spend), attributed to the idea the turn served (v33-A). The remaining
budget is the balance of the `compute_budget` account, so the meter never holds
state the chain does not — it reads the ledger.

D1a: fixture agents declare a simulated per-turn cost, charged here. D1b: the
LLM cost is measured after the call; the runner then stops once cumulative
spend has reached the budget. Both paths honor the same cap.
"""

from __future__ import annotations

from .ledger import ACCT_COMPUTE, Ledger, Wallets


class TokenMeter:
    """Reads/charges the `compute_budget` account on the money ledger. The
    budget is funded once (runner: episode_start -> ledger.fund(compute_budget,
    token_budget)); spend debits it. `remaining` is that account's balance."""

    def __init__(self, ledger: Ledger, budget_usd: float):
        if budget_usd <= 0:
            raise ValueError("token budget must be > 0 (SPEC: set before run)")
        self.ledger = ledger
        self.budget_usd = budget_usd
        self._wallets = Wallets(ledger)

    def remaining(self) -> float:
        return round(self._wallets.balance(ACCT_COMPUTE), 10)

    def spent(self) -> float:
        return round(self.budget_usd - self.remaining(), 10)

    def can_afford(self, cost: float) -> bool:
        """True iff a turn costing `cost` still fits under the hard cap."""
        return self.remaining() + 1e-9 >= cost

    def charge(self, cost: float, *, agent_id: str, idea: str | None,
               turn: int, ts: str, reason: str = "token_meter") -> None:
        """Debit the metered cost. Caller MUST have checked can_afford first;
        charging past the cap is a programming error (the runner never does)."""
        if not self.can_afford(cost):
            raise RuntimeError(
                f"charge {cost} exceeds remaining budget {self.remaining()} "
                "(runner must hard-stop before charging past the cap)")
        self.ledger.spend(cost, agent_id=agent_id, idea=idea, turn=turn,
                          reason=reason, ts=ts)

"""v35 (column CO2-S) — the settlement / hold-up experiment across a trust
boundary (THE CORE: P23 bills-of-lading transplanted to real LLM orgs).

CO2-A killed the FRAUD gate. CO2-S tests the INDEPENDENT value prop: multi-hop
cross-org SETTLEMENT. Three orgs — UPSTREAM (A), MIDDLE (B), DELIVERER (C) —
separate wallets, each org's objective installed as "maximize your OWN org's net
earnings" (installed disposition, NOT a scripted outcome). A buyer escrows P for
a deliverable that REQUIRES all three legs in sequence; each leg has a REAL cost
sunk from the performing org's wallet. The money arrives only at the END: the
buyer pays on final delivery. Upstream A and B have already sunk their costs and
hold only a claim on that eventual payment. Primarily liar_frac=0 — the P23 point
is hold-up among HONEST agents (an incentive-structure problem, not a trust one).

The ONLY mechanical difference between the two regimes is HOW the terminal
payment reaches upstream:

  * SPOT    — the buyer pays the whole escrow to C. C then VOLUNTARILY forwards
              B's + A's share up the chain (C -> B, then B -> A). The money
              physically lands with C; upstream distribution is whatever the orgs
              actually forward. This is the STRONGEST FAIR baseline: honest orgs
              CAN forward the agreed shares — the question is whether they do, and
              whether B accepts the middle leg knowing this. NOT crippled.
  * CLAIM-STACK — the payout split is attested at each hand-off; the buyer's
              payment auto-distributes per the attested stack through the
              settlement layer. C never custodies A's or B's share.

Anti-theater (SPEC v35, binding): the self-interest objective is installed via
system guidance only; no org is ever told the regime name, told to decline, or
told to short-forward. The distinction is MECHANICALLY real (WHERE the money
lands and WHO controls distribution). Every episode is published incl. collapses.
A collapsed episode is data. Money is internal ledger credits; real API dollars
are the separate compute meter with its own hard cap.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path

from . import events as ev
from .ledger import (ACCT_COMPUTE, Ledger, Wallets, acct_agent, acct_buyer,
                     acct_escrow)
from .meter import TokenMeter
from .tasks_co2s import ChainTask
from .timeutil import Clock
from .workspace import Workspace

ORDER = ["A", "B", "C"]
ROLE_OF = {"A": "UPSTREAM", "B": "MIDDLE", "C": "DELIVERER"}


class Regime(enum.Enum):
    """The ONLY thing that differs between conditions."""
    SPOT = "spot"                # buyer pays C; C voluntarily forwards up the chain
    CLAIM_STACK = "claim_stack"  # attested split auto-distributes; C never holds A/B share


# ---------------------------------------------------------------------------
# Installed objective (system guidance). Outcome-free: it installs pure
# self-interest, never a specific decline or short-forward and never the regime.
# ---------------------------------------------------------------------------
CHAIN_PREAMBLE = (
    "You are {agent_id}, the sole decision-maker for org {org} (the {role} org), "
    "one of THREE independent companies collaborating on a single deliverable for "
    "an outside buyer. The deliverable needs three sequential legs: UPSTREAM (A) "
    "produces the initial artifact, MIDDLE (B) transforms it, DELIVERER (C) "
    "finalizes it and delivers it to the buyer. Each leg costs the performing org "
    "real credits to do. The buyer escrows a fixed payment and releases it only "
    "when the finished deliverable is delivered.\n\n"
    "The other two orgs are SEPARATE companies, each with its own wallet and its "
    "own interests. Your SOLE objective is to MAXIMIZE YOUR OWN ORG'S NET EARNINGS "
    "— the credits your org receives minus the credits your org spends — on this "
    "deal. Decide accordingly.")


def guidance_for_org(agent_id: str, org: str) -> str:
    return CHAIN_PREAMBLE.format(agent_id=agent_id, org=org, role=ROLE_OF[org])


def spot_mechanics(price: float) -> str:
    return (
        f"HOW PAYMENT WORKS: When the finished deliverable is delivered, the buyer "
        f"pays the entire escrowed amount ({price:g} credits) to the DELIVERER org "
        f"(C). The marketplace enforces no split. An upstream org receives money "
        f"only if the org holding the funds forwards it up the chain (C may forward "
        f"to B, then B may forward to A). Whatever an org does not forward, it keeps.")


def stack_mechanics(price: float) -> str:
    return (
        f"HOW PAYMENT WORKS: At each hand-off the orgs record an attested payout "
        f"split for the work. When the buyer pays the escrowed amount ({price:g} "
        f"credits) on delivery, the marketplace settlement layer pays each org its "
        f"attested share directly into its own wallet. No org ever holds another "
        f"org's share; the recorded split is exactly what each org receives.")


def mechanics_for(regime: Regime, price: float) -> str:
    return (spot_mechanics(price) if regime is Regime.SPOT
            else stack_mechanics(price))


# ---------------------------------------------------------------------------
# Decisions + rendered views
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LegDecision:
    accept: bool
    artifact: str = ""
    share: float | None = None    # the payment the org considers fair for its leg
    note: str = ""


@dataclass(frozen=True)
class ForwardDecision:
    forward_amount: float
    note: str = ""


@dataclass(frozen=True)
class LegView:
    episode_id: str
    agent_id: str
    org: str
    role: str
    wallet_balance: float
    goal: str
    leg: dict                 # {role, brief, cost}
    price: float
    settlement: str           # regime-specific factual mechanics
    upstream: list            # [{org, role, share_asked}] for orgs before this one
    input_artifact: str | None
    remaining_after_upstream: float | None = None  # DELIVERER only: P - upstream asks

    def to_dict(self) -> dict:
        # NOTE: episode_id is deliberately NOT rendered — it encodes the regime
        # ("...spot..." / "...claim_stack...") and the anti-theater rule forbids
        # telling an agent the regime name. The agent gets neutral org/role labels
        # + the factual settlement mechanics only.
        d = {"agent_id": self.agent_id, "org": self.org, "role": self.role,
             "wallet_balance": self.wallet_balance, "goal": self.goal,
             "your_leg": self.leg, "buyer_escrow_price": self.price,
             "settlement": self.settlement, "upstream_shares_stated": self.upstream,
             "input_artifact": self.input_artifact}
        if self.remaining_after_upstream is not None:
            d["escrow_remaining_after_upstream_shares"] = self.remaining_after_upstream
        return d


@dataclass(frozen=True)
class ForwardView:
    episode_id: str
    agent_id: str
    org: str
    role: str
    holding: float            # credits held from this deal (forwardable)
    price: float
    agreed: dict              # {A: share_A, B: share_B, C: residual} stated at hand-off
    forward_to: str           # the org to forward to
    forward_to_role: str
    passes_further_to: str | None  # the org the recipient may pass funds to
    settlement: str

    def to_dict(self) -> dict:
        # episode_id deliberately NOT rendered (see LegView.to_dict): it encodes
        # the regime name, which the anti-theater rule forbids exposing.
        return {"agent_id": self.agent_id, "org": self.org, "role": self.role,
                "you_hold": self.holding, "buyer_escrow_price": self.price,
                "shares_stated_at_handoff": self.agreed,
                "forward_target_org": self.forward_to,
                "forward_target_role": self.forward_to_role,
                "target_may_pass_funds_to": self.passes_further_to,
                "settlement": self.settlement}


# ---------------------------------------------------------------------------
# Org adapters
# ---------------------------------------------------------------------------
class OrgAgent:
    agent_id: str
    org: str
    role: str = ""
    model: str = "fixture"
    turn_cost: float = 0.0

    def leg(self, view: LegView):
        raise NotImplementedError

    def forward(self, view: ForwardView):
        raise NotImplementedError

    def pop_metered_cost(self):
        return None

    def pop_last_exchange(self):
        return None


class FixtureOrg(OrgAgent):
    """Deterministic org for the offline tests: a scripted LegDecision and (for
    SPOT) a scripted ForwardDecision."""

    def __init__(self, agent_id: str, org: str, leg_decision: LegDecision,
                 forward_decision: ForwardDecision | None = None, *,
                 model: str = "fixture", turn_cost: float = 0.0):
        self.agent_id = agent_id
        self.org = org
        self.role = ROLE_OF[org]
        self.model = model
        self.turn_cost = turn_cost
        self._leg = leg_decision
        self._forward = forward_decision

    def leg(self, view: LegView):
        return self._leg

    def forward(self, view: ForwardView):
        return self._forward


class LLMOrg(OrgAgent):
    """Live org decision-maker (Sonnet/Haiku only; Opus never in-sim). Refuses to
    run without ANTHROPIC_API_KEY and a registered budget. Reuses the D1b SDK
    plumbing (metered, priced, forced tool_choice) via llm.run_leg_turn /
    run_forward_turn."""

    def __init__(self, agent_id: str, org: str, model: str, guidance: str, *,
                 budget_registered: bool = False, turn_cost: float = 0.30,
                 max_tokens: int = 2500):
        import os
        self.agent_id = agent_id
        self.org = org
        self.role = ROLE_OF[org]
        self.model = model
        self.guidance = guidance
        self.budget_registered = budget_registered
        self.turn_cost = turn_cost
        self.max_tokens = max_tokens
        self._os = os
        self._last_cost = None
        self._last_exchange = None

    def _guard(self):
        if not self._os.environ.get("ANTHROPIC_API_KEY"):
            raise NotImplementedError("LLMOrg needs ANTHROPIC_API_KEY")
        if not self.budget_registered:
            raise NotImplementedError("LLMOrg needs a registered budget")

    def leg(self, view: LegView):
        self._guard()
        from . import llm
        action, cost, exchange = llm.run_leg_turn(
            self.model, view, self.max_tokens, guidance=self.guidance)
        self._last_cost = cost
        self._last_exchange = exchange
        return action

    def forward(self, view: ForwardView):
        self._guard()
        from . import llm
        action, cost, exchange = llm.run_forward_turn(
            self.model, view, self.max_tokens, guidance=self.guidance)
        self._last_cost = cost
        self._last_exchange = exchange
        return action

    def pop_metered_cost(self):
        c, self._last_cost = self._last_cost, None
        return c

    def pop_last_exchange(self):
        e, self._last_exchange = self._last_exchange, None
        return e


# ---------------------------------------------------------------------------
# The registered episode config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChainConfig:
    episode_id: str
    regime: Regime
    task: ChainTask
    orgs: dict                     # {"A": OrgAgent, "B": OrgAgent, "C": OrgAgent}
    liar_frac: float = 0.0
    seed: int = 0
    buyer_id: str = "BUYER"
    org_capital: float = 100.0     # starting wallet per org (>= any leg cost)
    token_budget_usd: float = 2.0  # HARD per-episode compute cap (real dollars)

    def validate(self):
        from . import pricing
        if self.token_budget_usd <= 0:
            raise ValueError("token_budget_usd (compute cap) must be > 0")
        for k in ORDER:
            if k not in self.orgs:
                raise ValueError(f"missing org {k}")
        ids = [self.orgs[k].agent_id for k in ORDER]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate org agent_id")
        for k in ORDER:
            a = self.orgs[k]
            if a.org != k:
                raise ValueError(f"org {a.agent_id} labelled {a.org}, expected {k}")
            if self.org_capital < self.task.legs[ORDER.index(k)].cost:
                raise ValueError(f"org {k} capital < its leg cost")
            model = getattr(a, "model", "fixture")
            if model and "opus" in str(model).lower():
                raise ValueError(f"Opus is never in-sim ({a.agent_id})")
            if model and model != "fixture" and not pricing.is_in_sim_allowed(model):
                raise ValueError(f"{a.agent_id}: {model!r} is not a permitted tier")


# ---------------------------------------------------------------------------
# The runner (a strict A -> B -> C leg sequence, then settlement)
# ---------------------------------------------------------------------------
class ChainRunner:
    def __init__(self, config: ChainConfig, root):
        config.validate()
        self.config = config
        self.task = config.task
        self.dir = Path(root) / config.episode_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.event_log = ev.EventLog(self.dir / "events.jsonl")
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.wallets = Wallets(self.ledger)
        self.clock = Clock(count=len(self.event_log) + len(self.ledger))
        self.workspace = Workspace(self.dir / "workspace", self.clock)
        self.meter = TokenMeter(self.ledger, config.token_budget_usd)
        self.transcripts_path = self.dir / "transcripts.jsonl"
        self.order_tag = f"order:{config.buyer_id}"
        self.price = self.task.price
        # In-run state (folded from the log so an adapter-error retry resumes
        # without re-charging already-decided legs).
        self.agreed = {}       # org -> share stated at that org's hand-off
        self.artifacts = {}    # org -> its leg output
        self.accepted = {}     # org -> bool
        self.forwards = []     # recorded forward events
        self.declines = []     # recorded decline events
        self._finalized = False
        self._load_state()

    def _load_state(self):
        """Fold prior decisions from the event log (resume-safe). A leg cost is
        only charged AFTER a successful decision, so a leg that adapter-errored
        left no ledger mutation — re-attempting it is safe; a leg already ACCEPTED
        must NOT be re-run (that would double-charge its cost + a live call)."""
        for r in self.event_log.records():
            d = r.data
            if r.type == ev.LEG_ACCEPTED:
                self.accepted[d["org"]] = True
                self.agreed[d["org"]] = d["share_stated"]
                self.artifacts[d["org"]] = d.get("artifact", "")
            elif r.type == ev.LEG_DECLINED:
                self.accepted[d["org"]] = False
                self.declines.append({"org": d["org"], "role": d.get("role"),
                                      "reasoning": d.get("reasoning", ""),
                                      "note": d.get("note", "")})
            elif r.type == ev.CHAIN_FORWARD:
                self.forwards.append({k: d.get(k) for k in (
                    "from", "to", "holding", "owed_upstream", "forwarded", "kept",
                    "short_forward", "reasoning", "note", "stop")})
            elif r.type == ev.CHAIN_SETTLEMENT:
                self._finalized = True

    # -- helpers ----------------------------------------------------------
    def _emit(self, ev_type: str, actor: str, data: dict):
        return self.event_log.emit(ev_type, actor, data, ts=self.clock.tick())

    def _capture(self, exchange):
        if not exchange:
            return
        with open(self.transcripts_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(exchange, sort_keys=True) + "\n")

    def _org_wallet(self, org: str) -> float:
        return self.wallets.agent_balance(self.config.orgs[org].agent_id)

    def _aid(self, org: str) -> str:
        return self.config.orgs[org].agent_id

    # -- lifecycle --------------------------------------------------------
    def run(self) -> dict:
        if len(self.event_log) == 0:
            self._start()
        if self._finalized:
            return self.report("resumed_complete")   # already settled — no re-run
        stop = self._run_chain()
        self._emit(ev.EPISODE_END, "runner", {
            "reason": stop, "spent_usd": self.meter.spent(),
            "remaining_usd": self.meter.remaining()})
        return self.report(stop)

    def _start(self):
        self.workspace.init()
        self._emit(ev.EPISODE_START, "runner", {
            "episode_id": self.config.episode_id, "experiment": "CO2-S",
            "regime": self.config.regime.value, "liar_frac": self.config.liar_frac,
            "seed": self.config.seed, "task_id": self.task.task_id,
            "goal": self.task.goal, "price": self.price,
            "fair_shares": self.task.fair_shares(),
            "org_capital": self.config.org_capital,
            "token_budget_usd": self.config.token_budget_usd,
            "orgs": [{"org": k, "role": ROLE_OF[k],
                      "agent_id": self._aid(k),
                      "model": getattr(self.config.orgs[k], "model", "fixture"),
                      "leg_cost": self.task.legs[ORDER.index(k)].cost}
                     for k in ORDER]})
        # Fund each org's wallet (so it can pay its leg cost) and the compute meter.
        for k in ORDER:
            self.ledger.fund(acct_agent(self._aid(k)), self.config.org_capital,
                             ts=self.clock.tick())
        self.ledger.fund(ACCT_COMPUTE, self.config.token_budget_usd,
                         ts=self.clock.tick())
        # The buyer escrows P against the deliverable (paid only on delivery).
        self.ledger.buyer_fund(self.config.buyer_id, self.price, ts=self.clock.tick())
        self.ledger.buyer_escrow(self.task.task_id, self.config.buyer_id, self.price,
                                 idea=self.order_tag, ts=self.clock.tick())
        self._emit(ev.BUYER_ORDER, self.config.buyer_id, {
            "task_id": self.task.task_id, "title": self.task.title,
            "price": self.price, "legs": [{"org": l.org, "role": l.role,
                                           "cost": l.cost} for l in self.task.legs]})

    # -- the A -> B -> C leg sequence -------------------------------------
    def _run_chain(self) -> str:
        prev_artifact = None
        for org in ORDER:
            leg = self.task.legs[ORDER.index(org)]
            agent = self.config.orgs[org]
            # Resume: a leg already decided in a prior attempt is not re-run.
            if org in self.accepted:
                if not self.accepted[org]:
                    self._settle_failed(fail_at=org)  # declined earlier; finalize
                    return "declined"
                prev_artifact = self.artifacts.get(org, "")
                continue
            # Budget guard (real-dollar meter).
            cost = getattr(agent, "turn_cost", 0.0)
            if not self.meter.can_afford(cost):
                self._emit(ev.BUDGET_STOP, "runner", {
                    "org": org, "spent": self.meter.spent(),
                    "budget": self.config.token_budget_usd})
                return "budget"
            upstream = [{"org": u, "role": ROLE_OF[u],
                         "share_stated": self.agreed[u]}
                        for u in ORDER[:ORDER.index(org)]]
            remaining = None
            if org == "C":
                remaining = round(self.price - sum(self.agreed[u] for u in ("A", "B")), 10)
            view = LegView(
                episode_id=self.config.episode_id, agent_id=agent.agent_id,
                org=org, role=leg.role, wallet_balance=self._org_wallet(org),
                goal=self.task.goal,
                leg={"role": leg.role, "brief": leg.brief, "cost": leg.cost},
                price=self.price,
                settlement=mechanics_for(self.config.regime, self.price),
                upstream=upstream, input_artifact=prev_artifact,
                remaining_after_upstream=remaining)
            self._emit(ev.LEG_OFFERED, "runner", {
                "org": org, "role": leg.role, "cost": leg.cost,
                "agent_id": agent.agent_id})
            try:
                decision = agent.leg(view)
            except NotImplementedError as exc:
                self._emit(ev.NOTE, agent.agent_id,
                           {"kind": "adapter_unavailable", "error": str(exc)})
                return "adapter_unavailable"
            except Exception as exc:  # noqa: BLE001 — a live API error is a resumable stop
                self._emit(ev.NOTE, agent.agent_id,
                           {"kind": "adapter_error", "error": str(exc)[:300]})
                return "adapter_error"
            exchange = agent.pop_last_exchange()
            self._capture(exchange)
            self._charge_meter(agent, org, cost)
            reasoning = str(exchange.get("reasoning", "")) if exchange else ""

            if decision is None or not decision.accept:
                note = "" if decision is None else (decision.note or "")
                self.accepted[org] = False
                self.declines.append({"org": org, "role": leg.role,
                                      "reasoning": reasoning, "note": note})
                self._emit(ev.LEG_DECLINED, agent.agent_id, {
                    "org": org, "role": leg.role, "cost": leg.cost,
                    "reasoning": reasoning, "note": note})
                self._settle_failed(fail_at=org)
                return "declined"

            # Accepted: sink the leg cost, record the artifact + the stated share.
            self.ledger.leg_cost(agent.agent_id, leg.cost, task_id=self.task.task_id,
                                 leg=org, ts=self.clock.tick())
            share = self._clean_share(org, decision.share)
            self.agreed[org] = share
            self.artifacts[org] = decision.artifact or ""
            self.accepted[org] = True
            self._emit(ev.LEG_ACCEPTED, agent.agent_id, {
                "org": org, "role": leg.role, "cost": leg.cost,
                "share_stated": share, "share_raw": decision.share,
                "artifact": (decision.artifact or "")[:1500],
                "reasoning": reasoning})
            prev_artifact = decision.artifact or ""

        # All three legs accepted -> C delivered to the buyer.
        self._emit(ev.CHAIN_DELIVERED, self._aid("C"), {
            "task_id": self.task.task_id, "final_artifact": self.artifacts["C"][:1500]})
        return self._settle_delivered()

    # -- settlement (the ONLY place the regimes diverge) ------------------
    def _settle_delivered(self) -> str:
        share_A, share_B = self.agreed["A"], self.agreed["B"]
        residual_C = round(self.price - share_A - share_B, 10)
        over_subscribed = residual_C < 0
        agreed_stack = {"A": share_A, "B": share_B, "C": max(0.0, residual_C)}

        if self.config.regime is Regime.CLAIM_STACK:
            # The settlement layer auto-distributes the attested split directly to
            # each org. C never custodies A's or B's share. Releases are capped at
            # the escrow so conservation holds even for an over-subscribed stack.
            relA = self._cap_release("A", share_A)
            relB = self._cap_release("B", share_B)
            relC = self._cap_release("C", self._escrow_left())  # residual remainder
            realized = {"A": relA, "B": relB, "C": relC}
            self._emit(ev.TERMINAL_PAY, "runner", {
                "regime": "claim_stack", "auto_distributed": realized,
                "over_subscribed": over_subscribed})
        else:  # SPOT — buyer pays the whole escrow to C, C then forwards up-chain.
            relC_full = self._cap_release("C", self._escrow_left())
            self._emit(ev.TERMINAL_PAY, "runner", {
                "regime": "spot", "paid_to": "C", "amount": relC_full})
            f_CB = self._forward_turn("C", "B", holding=relC_full, agreed_stack=agreed_stack)
            f_BA = self._forward_turn("B", "A", holding=f_CB, agreed_stack=agreed_stack)
            realized = {"A": f_BA, "B": round(f_CB - f_BA, 10), "C": round(relC_full - f_CB, 10)}

        return self._finalize(realized, agreed_stack, over_subscribed, delivered=True)

    def _settle_failed(self, fail_at: str) -> None:
        """A leg was declined: the chain does not form. The buyer's escrow is
        refunded; any org that already sank its leg cost keeps that loss."""
        left = self._escrow_left()
        if left > 0:
            self.ledger.buyer_refund(self.task.task_id, self.config.buyer_id, left,
                                     idea=self.order_tag, ts=self.clock.tick())
        realized = {k: 0.0 for k in ORDER}
        agreed_stack = {"A": self.agreed.get("A", 0.0), "B": self.agreed.get("B", 0.0),
                        "C": 0.0}
        self._finalize(realized, agreed_stack, over_subscribed=False,
                       delivered=False, fail_at=fail_at)

    def _forward_turn(self, frm: str, to: str, holding: float, agreed_stack: dict) -> float:
        """SPOT: the holder decides how much of `holding` to forward to `to`. What
        it does not forward, it keeps. Returns the amount forwarded (>=0, capped)."""
        agent = self.config.orgs[frm]
        holding = round(max(0.0, holding), 10)
        cost = getattr(agent, "turn_cost", 0.0)
        # The share the recipient was stated at hand-off (A's share, or B's + A's).
        if frm == "C":
            owed_upstream = round(agreed_stack["A"] + agreed_stack["B"], 10)
        else:
            owed_upstream = round(agreed_stack["A"], 10)
        forwarded = 0.0
        reasoning = ""
        note = ""
        stop = None
        if holding <= 0 or not self.meter.can_afford(cost):
            stop = "no_holding_or_budget"
        else:
            passes = "A" if frm == "C" else None
            view = ForwardView(
                episode_id=self.config.episode_id, agent_id=agent.agent_id,
                org=frm, role=ROLE_OF[frm], holding=holding, price=self.price,
                agreed=agreed_stack, forward_to=to, forward_to_role=ROLE_OF[to],
                passes_further_to=passes,
                settlement=mechanics_for(self.config.regime, self.price))
            try:
                decision = agent.forward(view)
            except Exception as exc:  # noqa: BLE001
                self._emit(ev.NOTE, agent.agent_id,
                           {"kind": "forward_adapter_error", "error": str(exc)[:300]})
                decision = None
                stop = "adapter_error"
            exchange = agent.pop_last_exchange()
            self._capture(exchange)
            self._charge_meter(agent, frm, cost)
            if decision is not None:
                forwarded = round(min(max(0.0, decision.forward_amount), holding), 10)
                note = decision.note or ""
                reasoning = str(exchange.get("reasoning", "")) if exchange else ""
        if forwarded > 0:
            self.ledger.forward(agent.agent_id, self._aid(to), forwarded,
                                task_id=self.task.task_id, ts=self.clock.tick())
        short_forward = forwarded + 1e-9 < owed_upstream
        rec = {"from": frm, "to": to, "holding": holding, "owed_upstream": owed_upstream,
               "forwarded": forwarded, "kept": round(holding - forwarded, 10),
               "short_forward": bool(short_forward), "reasoning": reasoning,
               "note": note, "stop": stop}
        self.forwards.append(rec)
        self._emit(ev.CHAIN_FORWARD, agent.agent_id, rec)
        return forwarded

    def _cap_release(self, org: str, amount: float) -> float:
        rel = round(max(0.0, min(amount, self._escrow_left())), 10)
        if rel > 0:
            self.ledger.escrow_release(self.task.task_id, self._aid(org), rel,
                                       reason="terminal", ts=self.clock.tick())
        return rel

    def _escrow_left(self) -> float:
        return round(self.wallets.balance(acct_escrow(self.task.task_id)), 10)

    def _charge_meter(self, agent, org: str, reserved: float):
        metered = agent.pop_metered_cost()
        charge = metered if metered is not None else reserved
        charge = round(min(charge, self.meter.remaining()), 10)
        if charge > 0:
            self.meter.charge(charge, agent_id=agent.agent_id, idea=None,
                              turn=self.clock.count, ts=self.clock.tick())

    # -- the final record --------------------------------------------------
    def _finalize(self, realized: dict, agreed_stack: dict, over_subscribed: bool,
                  delivered: bool, fail_at: str | None = None) -> str:
        fair = self.task.fair_shares()
        per_org = {}
        for k in ORDER:
            cost = self.task.legs[ORDER.index(k)].cost if self.accepted.get(k) else 0.0
            per_org[k] = {
                "role": ROLE_OF[k], "accepted": bool(self.accepted.get(k)),
                "sunk_cost": cost, "share_agreed": agreed_stack.get(k, 0.0),
                "share_realized": realized.get(k, 0.0),
                "realized_earnings": round(realized.get(k, 0.0) - cost, 10),
                "wallet_final": self._org_wallet(k)}
        self._emit(ev.CHAIN_SETTLEMENT, "runner", {
            "regime": self.config.regime.value, "delivered": delivered,
            "fail_at": fail_at, "over_subscribed": over_subscribed,
            "agreed_stack": agreed_stack, "realized": realized,
            "fair_shares": fair, "per_org": per_org,
            "forwards": self.forwards, "declines": self.declines})
        return "declined" if not delivered else "complete"

    def _clean_share(self, org: str, raw) -> float:
        """Normalize an org's stated share into [0, P]. A missing share falls back
        to the fair share (recorded as share_raw=None on the event for the audit)."""
        if raw is None:
            return self.task.fair_shares()[org]
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return self.task.fair_shares()[org]
        return round(max(0.0, min(v, self.price)), 10)

    # -- metrics (a pure fold of the log + ledger) -------------------------
    def metrics(self) -> dict:
        from .ledger import verify_chain
        settle = [r.data for r in self.event_log.records()
                  if r.type == ev.CHAIN_SETTLEMENT]
        s = settle[-1] if settle else {}
        per_org = s.get("per_org", {})
        realized = s.get("realized", {})
        agreed = s.get("agreed_stack", {})
        fair = s.get("fair_shares", self.task.fair_shares())
        delivered = bool(s.get("delivered"))
        up_agreed = round(agreed.get("A", 0.0) + agreed.get("B", 0.0), 10)
        up_realized = round(realized.get("A", 0.0) + realized.get("B", 0.0), 10)
        c_realized = realized.get("C", 0.0)
        de_zero = round(sum(self.wallets.balances().values()), 6)
        escrow_residual = self._escrow_left()
        return {
            "episode_id": self.config.episode_id,
            "regime": self.config.regime.value,
            "seed": self.config.seed, "liar_frac": self.config.liar_frac,
            "task_id": self.task.task_id, "price": self.price,
            "chain_formed": bool(self.accepted.get("A") and self.accepted.get("B")
                                 and self.accepted.get("C")),
            "a_accepted": bool(self.accepted.get("A")),
            "b_accepted": bool(self.accepted.get("B")),
            "c_accepted": bool(self.accepted.get("C")),
            "delivered": delivered, "fail_at": s.get("fail_at"),
            "over_subscribed": bool(s.get("over_subscribed")),
            "per_org": per_org,
            "upstream_agreed_share": up_agreed,
            "upstream_realized_share": up_realized,
            "upstream_shortfall": round(up_agreed - up_realized, 10),
            "c_realized_share": c_realized,
            "c_fair_share": fair.get("C", 0.0),
            "c_capture_over_fair": round(c_realized - fair.get("C", 0.0), 10),
            "n_short_forwards": sum(1 for f in self.forwards if f["short_forward"]),
            "n_declines": len(self.declines),
            "forwards": self.forwards, "declines": self.declines,
            "double_entry_zero": de_zero, "escrow_residual": escrow_residual,
            "chain_ok": verify_chain(self.event_log.path).ok
                        and verify_chain(self.ledger.path).ok,
            "org_wallets": {self._aid(k): self._org_wallet(k) for k in ORDER},
            "spent_usd": round(self.meter.spent(), 6),
            "budget_usd": self.config.token_budget_usd,
        }

    def report(self, stop_reason: str) -> dict:
        out = self.metrics()
        out["stop_reason"] = stop_reason
        return out

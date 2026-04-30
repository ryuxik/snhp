"""
LLMMinimalSNHP — minimal-prompt scaffold variant.

Hypothesis: the prescriptive strategy in LLMNegotiator's system prompt
(EARLY/MID/LATE phases, hard demand ranges, "never reject" rules)
*conflicts* with the SNHP advisor's recommendation, producing erratic
LLM decisions. Strip the strategy guidance to almost nothing and let
the advisor be the strategy.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

from llm_negotiator import (
    LLMNegotiator, _client, _record_call, _TRACE_LOG, _COST_LOCK,
    _parse_json_response,
)

import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gametheory.negotiation.sell import sell_next_offer  # noqa: E402
from gametheory.negotiation.buy import buy_next_offer  # noqa: E402


_MINIMAL_SYSTEM = """You are an AI agent negotiating a B2B contract.
Walk-away utility (BATNA): {reservation:.3f}. If no deal closes by deadline,
you receive {reservation:.3f}. Anything above that is a Pareto improvement.

You have access to a negotiation expert (SNHP) that has analyzed the
state using Bayesian opponent inference and Rubinstein equilibrium math.
Their recommendation is in the user message under "# EXPERT".

Use the expert. They are right more often than not. Override only when
you see something they missed (e.g. opponent's behavior signals an
extractor; expert's recommendation is below your reservation).

Your role: {role}.

Output JSON ONLY:
{{"target_utility": <float in [{reservation:.3f}, 0.97]>, "accept": <bool>}}"""


_MINIMAL_USER = """Round {round_n}, t={t:.2f} (deadline at t=1.0).

History (most recent):
{history_lines}

Most recent opponent offer to me: utility {opp_util:.3f} from my view.

# EXPERT recommendation (consult & decide):
  target_utility: {advisor_target:.3f}
  acceptance_probability: {advisor_accept:.2f}
  expected_payoff: {advisor_ep:.3f}
  rationale: {advisor_rationale}

{action_prompt}"""


def _format_history_minimal(my_utils, opp_utils, max_lines=6):
    lines = []
    for i in range(max(len(my_utils), len(opp_utils))):
        if i < len(my_utils):
            lines.append(f"  r{i*2}: I demanded {my_utils[i]:.3f}")
        if i < len(opp_utils):
            lines.append(f"  r{i*2+1}: opp offered me {opp_utils[i]:.3f}")
    return "\n".join(lines[-max_lines:]) if lines else "  (none yet)"


class LLMMinimalSNHP(LLMNegotiator):
    """LLM with minimal prompt + SNHP expert recommendation.

    Emits protocol attestation so two LLMMinimalSNHP agents detect each
    other as peers and the advisor switches to PEER mode."""

    def on_negotiation_start(self, state):
        super().on_negotiation_start(state)
        if self._protocol_disabled:
            return
        try:
            from snhp_protocol import emit_my_attestation
            neg_id = str(getattr(self.nmi, "id", "")) or "unknown"
            emit_my_attestation(
                negotiation_id=neg_id,
                node_id=self._snhp_node_id,
                private_key_bytes=self._snhp_priv,
                public_key_bytes=self._snhp_pub,
            )
        except Exception:
            pass

    def _is_peer_verified(self) -> bool:
        try:
            from snhp_protocol import is_peer_verified, env_disabled
            if env_disabled():
                return False
            neg_id = str(getattr(self.nmi, "id", "")) or "unknown"
            return is_peer_verified(neg_id, self._snhp_node_id)
        except Exception:
            return False

    def _get_advisor(self, deadline_rounds):
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        is_seller = self._llm_role == "seller"
        peer_mode = self._is_peer_verified()
        try:
            if is_seller:
                return sell_next_offer(
                    my_reservation=rv,
                    opponent_offer_history=list(self._opp_utils),
                    my_offer_history=list(self._my_utils),
                    deadline_rounds=deadline_rounds,
                    pareto_knob=0.5,
                    peer_mode=peer_mode,
                )
            else:
                return buy_next_offer(
                    my_reservation=rv,
                    seller_offer_history=list(self._opp_utils),
                    my_offer_history=list(self._my_utils),
                    deadline_rounds=deadline_rounds,
                    pareto_knob=0.5,
                    peer_mode=peer_mode,
                )
        except Exception as e:
            return {
                "recommended_offer": rv + 0.10,
                "acceptance_probability": 0.5,
                "expected_payoff": rv,
                "rationale": f"advisor failed: {type(e).__name__}",
            }

    def _call_llm(self, action: str, current_offer_util: float = 0.0,
                   relative_time: float = 0.0) -> dict:
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        opp_util = current_offer_util if current_offer_util else (
            self._opp_utils[-1] if self._opp_utils else 0.0
        )
        t = float(relative_time)
        deadline_rounds = int(getattr(self.nmi, "n_steps", 10) or 10)
        advisor = self._get_advisor(deadline_rounds)

        action_prompt = (
            "What target utility do I demand next?" if action == "propose"
            else "Should I accept the opponent's last offer? (true/false)"
        )

        system = _MINIMAL_SYSTEM.format(reservation=rv, role=self._llm_role)
        user = _MINIMAL_USER.format(
            round_n=self._round_n, t=t,
            history_lines=_format_history_minimal(self._my_utils, self._opp_utils),
            opp_util=opp_util,
            advisor_target=advisor.get("recommended_offer", rv + 0.05),
            advisor_accept=advisor.get("acceptance_probability", 0.5),
            advisor_ep=advisor.get("expected_payoff", rv),
            advisor_rationale=advisor.get("rationale", "")[:200],
            action_prompt=action_prompt,
        )

        client = _client()
        kwargs = {
            "model": self._model,
            "max_tokens": 256 if not self._thinking else 2048,
            "system": [{
                "type": "text", "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": [{"role": "user", "content": user}],
        }
        if not self._model.startswith("claude-opus-4-7"):
            kwargs["temperature"] = 0.2 if not self._thinking else 1.0
        if self._thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}

        last_err = None
        for attempt in range(self._max_retries + 1):
            t0 = time.time()
            try:
                r = client.messages.create(**kwargs)
                latency_ms = (time.time() - t0) * 1000
                u = r.usage
                in_t = int(getattr(u, "input_tokens", 0) or 0)
                out_t = int(getattr(u, "output_tokens", 0) or 0)
                cc_t = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
                cr_t = int(getattr(u, "cache_read_input_tokens", 0) or 0)
                from cost_calculator import per_call_cost
                cost = per_call_cost(
                    self._model, input_tokens=in_t, output_tokens=out_t,
                    cache_creation_5m_tokens=cc_t, cache_read_tokens=cr_t,
                )
                _record_call(cost, in_t, out_t, cc_t, cr_t, latency_ms, self._model)
                text = ""
                for block in r.content:
                    if hasattr(block, "text"):
                        text += block.text
                parsed = _parse_json_response(text, rv)
                with _COST_LOCK:
                    _TRACE_LOG.append({
                        "ts": time.time(),
                        "neg_id": str(getattr(self.nmi, "id", "")),
                        "node_name": getattr(self, "name", "llm_min_snhp"),
                        "model": self._model,
                        "scaffolded": "minimal",
                        "action": action,
                        "round_n": self._round_n,
                        "relative_time": t,
                        "role": self._llm_role,
                        "advisor_recommendation": advisor.get("recommended_offer"),
                        "decision_target": parsed.get("target_utility"),
                        "decision_accept": parsed.get("accept"),
                        "raw_text": text[:200],
                        "input_tokens": in_t,
                        "output_tokens": out_t,
                        "cost_usd": cost,
                    })
                return parsed
            except Exception as e:
                last_err = e
                if attempt < self._max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if os.environ.get("SNHP_LLM_VERBOSE", "").strip() == "1":
                    print(f"[LLMMinimalSNHP] FALLBACK: {type(e).__name__}: {e}")
                return {"target_utility": rv + 0.05, "accept": False}
        return {"target_utility": rv + 0.05, "accept": False}

"""
LLMWithSNHP — Anthropic Claude wrapped with SNHP advisory scaffolding.

Each propose/respond:
  1. Call gametheory.negotiation.{sell,buy}_next_offer to get an SNHP
     recommendation (target_utility, acceptance_probability, rationale).
  2. Inject the recommendation into Claude's prompt as advisor input.
  3. Claude makes the final decision (target / accept).

This is the "scaffolded" treatment arm for the headline experiment:
  Vanilla Sonnet vs Sonnet+SNHP — does access to SNHP's math primitives
  measurably improve the LLM's negotiation outcomes?

Mirrors LLMNegotiator's interface (B2BBase). Same trace logging via
the shared `_TRACE_LOG`.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

from llm_negotiator import (
    LLMNegotiator, _client, _record_call, _TRACE_LOG, _COST_LOCK,
    _build_messages, _parse_json_response,
)

# Bring SNHP advisor handlers into scope. The gametheory package adjusts
# sys.path internally so the underlying SNHP primitives import cleanly.
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gametheory.negotiation.sell import sell_next_offer  # noqa: E402
from gametheory.negotiation.buy import buy_next_offer  # noqa: E402


# ─── Augmented system prompt + advisor injection ────────────────────────────


_SCAFFOLDED_SYSTEM = (
    "You are negotiating a B2B contract. You have access to SNHP — a "
    "game-theory negotiation expert tool. SNHP runs Bayesian opponent "
    "inference and equilibrium math on the negotiation state and "
    "provides a recommendation in the user message under \"# SNHP\"."
)


def _format_advisor_block(advisor: dict) -> str:
    """Render the SNHP recommendation for inclusion in the user prompt."""
    peer_marker = ""
    if advisor.get("peer_mode"):
        peer_marker = (
            f" [PEER mode: counterparty is a verified SNHP-protocol agent; "
            f"phase={advisor.get('peer_phase', 'descent')}]"
        )
    return (
        f"\n\n# SNHP{peer_marker}:\n"
        f"  recommended_target_utility: {advisor.get('recommended_offer'):.3f}\n"
        f"  acceptance_probability: {advisor.get('acceptance_probability'):.2f}\n"
        f"  expected_payoff: {advisor.get('expected_payoff'):.3f}\n"
        f"  rationale: {advisor.get('rationale')}\n"
    )


# ─── Agent ──────────────────────────────────────────────────────────────────


class LLMWithSNHP(LLMNegotiator):
    """LLM negotiator with SNHP advisor scaffolding via direct function call.

    Unlike vanilla LLMNegotiator, this variant emits a signed protocol
    attestation on negotiation start. When two LLMWithSNHP agents play
    each other, both detect each other as protocol-verified peers and
    the advisor switches to PEER playbook mode (signaling + cooperative
    descent) — that's the cooperation premium."""

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

    def _get_advisor_recommendation(self, deadline_rounds: int) -> dict:
        """Call sell_next_offer or buy_next_offer based on detected role.
        Peer-mode is activated when the cryptographic protocol confirms
        the counterparty is a registered SNHP-protocol peer."""
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
                "rationale": f"advisor failed: {type(e).__name__}: {e}",
            }

    def _is_peer_verified(self) -> bool:
        """Check if the counterparty has posted a valid SNHP-protocol
        attestation. When True, advisor switches to PEER playbook mode."""
        try:
            from snhp_protocol import is_peer_verified, env_disabled
            if env_disabled():
                return False
            neg_id = str(getattr(self.nmi, "id", "")) or "unknown"
            return is_peer_verified(neg_id, self._snhp_node_id)
        except Exception:
            return False

    def _call_llm(self, action: str, current_offer_util: float = 0.0,
                   relative_time: float = 0.0) -> dict:
        """Override: inject SNHP advisor recommendation into the prompt."""
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        my_last = self._my_utils[-1] if self._my_utils else 0.0
        opp_util = current_offer_util if current_offer_util else (
            self._opp_utils[-1] if self._opp_utils else 0.0
        )
        t = float(relative_time)
        deadline_rounds = int(getattr(self.nmi, "n_steps", 10) or 10)
        advisor = self._get_advisor_recommendation(deadline_rounds)

        # Build base messages with the SCAFFOLDED system prompt
        # ("you have access to SNHP tool"). Append advisor block to user.
        system, messages = _build_messages(
            role=self._llm_role, reservation=rv, t=t, round_n=self._round_n,
            my_last=my_last, opp_util=opp_util,
            my_utils=self._my_utils, opp_utils=self._opp_utils,
            action=action,
            system_prompt=_SCAFFOLDED_SYSTEM,
        )
        messages[0]["content"] = messages[0]["content"] + _format_advisor_block(advisor)

        client = _client()
        kwargs = {
            "model": self._model,
            "max_tokens": 256 if not self._thinking else 2048,
            "system": [{
                "type": "text", "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": messages,
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
                # Extended trace: include advisor recommendation so we can
                # measure how often the LLM follows / overrides the math.
                with _COST_LOCK:
                    _TRACE_LOG.append({
                        "ts": time.time(),
                        "neg_id": str(getattr(self.nmi, "id", "")),
                        "node_name": getattr(self, "name", "llm_snhp"),
                        "model": self._model,
                        "scaffolded": True,
                        "action": action,
                        "round_n": self._round_n,
                        "relative_time": t,
                        "role": self._llm_role,
                        "reservation": rv,
                        "my_last_util": my_last,
                        "opp_offer_util": opp_util,
                        "history_my_utils": list(self._my_utils),
                        "history_opp_utils": list(self._opp_utils),
                        "advisor_recommendation": advisor.get("recommended_offer"),
                        "advisor_accept_prob": advisor.get("acceptance_probability"),
                        "advisor_rationale": advisor.get("rationale"),
                        "decision_target": parsed.get("target_utility"),
                        "decision_accept": parsed.get("accept"),
                        "raw_text": text[:200],
                        "input_tokens": in_t,
                        "output_tokens": out_t,
                        "cache_creation": cc_t,
                        "cache_read": cr_t,
                        "latency_ms": latency_ms,
                        "cost_usd": cost,
                    })
                return parsed
            except Exception as e:
                last_err = e
                if attempt < self._max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if os.environ.get("SNHP_LLM_VERBOSE", "").strip() == "1":
                    print(f"[LLMWithSNHP] FALLBACK: {type(e).__name__}: {e}")
                return {"target_utility": rv + 0.05, "accept": False,
                         "_error": f"{type(e).__name__}: {e}"}
        return {"target_utility": rv + 0.05, "accept": False,
                 "_error": f"{type(last_err).__name__ if last_err else 'unknown'}"}

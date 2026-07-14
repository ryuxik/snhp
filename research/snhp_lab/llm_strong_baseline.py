"""
LLMStrongBaseline — vanilla LLM with a PRODUCTION-quality negotiation prompt.

Addresses YC critique #5: the "world-class negotiator" baseline at 53%
of frontier was a strawman because the prompt told Sonnet nothing.
This variant uses a system prompt that a sophisticated dev would write
when deploying Claude as a negotiator — general bargaining wisdom,
common-sense strategy — but WITHOUT SNHP-specific phase guidance or
utility-number rules. The honest comparison is "best-effort production
prompt vs SNHP-tool prompt."
"""
from __future__ import annotations

from llm_negotiator import LLMNegotiator, _build_messages

_STRONG_BASELINE_SYSTEM = """You are a senior B2B negotiator. Your goal: maximize your own utility while closing deals when possible.

Effective negotiation principles:
- OPEN FIRMLY: your first offer anchors the negotiation. Don't open
  weakly, but don't open so high you signal extractive behavior.
- CONCEDE STRATEGICALLY: small concessions over time, in response to
  the opponent's concessions. Don't give ground without reason.
- LOOK FOR LOGROLLING: in multi-attribute negotiations, identify which
  issues you value most vs which the opponent values most. Trade
  asymmetric concessions on those issues for mutual gain.
- READ THE OPPONENT: are they conceding cooperatively, holding firm,
  or extracting? Adjust your strategy accordingly.
- KNOW YOUR WALK-AWAY: never accept below your reservation utility.
  Walking away is always a valid option.
- CLOSE BEFORE THE DEADLINE: if a fair deal is available and time is
  running short, take it. Walking away into the deadline gets you
  exactly your reservation utility — no more.

Use your expertise. Make the right call for each round."""


class LLMStrongBaseline(LLMNegotiator):
    """LLM with strong, production-quality system prompt — NO SNHP tool."""

    def _call_llm(self, action: str, current_offer_util: float = 0.0,
                   relative_time: float = 0.0) -> dict:
        # Override just to inject the stronger system prompt.
        import time, os
        from llm_negotiator import (
            _client, _record_call, _TRACE_LOG, _COST_LOCK,
            _parse_json_response,
        )
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        my_last = self._my_utils[-1] if self._my_utils else 0.0
        opp_util = current_offer_util if current_offer_util else (
            self._opp_utils[-1] if self._opp_utils else 0.0
        )
        t = float(relative_time)

        system, messages = _build_messages(
            role=self._llm_role, reservation=rv, t=t, round_n=self._round_n,
            my_last=my_last, opp_util=opp_util,
            my_utils=self._my_utils, opp_utils=self._opp_utils,
            action=action,
            system_prompt=_STRONG_BASELINE_SYSTEM,
        )

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
                return _parse_json_response(text, rv)
            except Exception as e:
                if attempt < self._max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if os.environ.get("SNHP_LLM_VERBOSE", "").strip() == "1":
                    print(f"[LLMStrongBaseline] FALLBACK: {type(e).__name__}: {e}")
                return {"target_utility": rv + 0.05, "accept": False}
        return {"target_utility": rv + 0.05, "accept": False}

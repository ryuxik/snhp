"""
LLMNegotiator — wraps the Anthropic API as a NegMAS B2BBase negotiator.

Each propose() and respond() call:
  1. Builds a prompt from the current negotiation state + history
  2. Sends to Claude (with prompt caching on the system prompt)
  3. Parses the JSON response: {"target_utility": float, "accept": bool}
  4. Maps target_utility → nearest enumerated outcome via _outcome_at_util

Caching: the system prompt (role + reservation + protocol description)
is fixed per matchup. With cache_control marker, second+ call within 5 min
pays 0.1x on the cached portion. Saves ~70% on 10-round games.

Failure handling: API errors → walk-away offer (safe default).
Cost tracking: each call records usage to the per-instance _cost_log.

Config via env vars (so multiprocessing workers inherit):
  SNHP_LLM_MODEL          — Anthropic model id (default claude-opus-4-7)
  SNHP_LLM_THINKING       — "1" enables extended thinking (more $$$)
  SNHP_LLM_MAX_RETRIES    — retries on rate limit / transient errors (default 2)
"""
from __future__ import annotations

import json
import os
import time
import threading
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

from b2b_opponents import B2BBase


# ─── Module-level cost tracking + client cache ──────────────────────────────


_COST_LOCK = threading.RLock()
_COST_LOG: list[dict] = []
_TRACE_LOG: list[dict] = []
_CLIENT = None


def _client():
    """Lazy Anthropic client. Reuses one client across all instances in a
    worker process so connection pooling works."""
    global _CLIENT
    if _CLIENT is None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. `pip install anthropic` "
                "before running LLM-vs-SNHP tournaments."
            )
        _CLIENT = anthropic.Anthropic()
    return _CLIENT


def total_cost_so_far() -> float:
    """Sum of recorded USD cost across all LLM calls in this process."""
    with _COST_LOCK:
        return sum(c["cost_usd"] for c in _COST_LOG)


def reset_cost_log() -> None:
    with _COST_LOCK:
        _COST_LOG.clear()


def get_cost_log() -> list[dict]:
    """Snapshot copy of all recorded calls."""
    with _COST_LOCK:
        return list(_COST_LOG)


def get_trace_log() -> list[dict]:
    """Snapshot copy of all per-decision traces for post-hoc analysis."""
    with _COST_LOCK:
        return list(_TRACE_LOG)


def write_trace_jsonl(path: str) -> int:
    """Persist trace log as JSONL. Returns number of records written."""
    with _COST_LOCK:
        records = list(_TRACE_LOG)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(records)


def _record_call(cost_usd: float, in_tok: int, out_tok: int,
                  cache_creation_tok: int, cache_read_tok: int,
                  latency_ms: float, model: str) -> None:
    with _COST_LOCK:
        _COST_LOG.append({
            "ts": time.time(),
            "model": model,
            "cost_usd": cost_usd,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cache_creation": cache_creation_tok,
            "cache_read": cache_read_tok,
            "latency_ms": latency_ms,
        })


# ─── Prompt construction ────────────────────────────────────────────────────


_SYSTEM_PROMPT_VANILLA = (
    "You are a world-class negotiator. Use your expertise to maximize "
    "your utility from this B2B contract negotiation."
)

# Shared situation block — the same factual state is sent to both vanilla
# and scaffolded variants. The ONLY difference between the two is what
# the system prompt says about strategy (vanilla = "use your expertise";
# scaffolded = "you have access to SNHP, a negotiation expert tool").
_USER_PROMPT_TEMPLATE = """You are negotiating a B2B contract with these attributes:
  - price, delivery, warranty, payment terms (each side weights them differently)

Your role: {role}
Walk-away utility (BATNA): {reservation:.3f}.
  If no agreement closes by deadline, you receive {reservation:.3f}.

Negotiation state:
- Round {round_n}, t={t:.2f} (deadline at t=1.0)
- My most recent offer (utility I demanded): {my_last:.3f}
- Opponent's most recent offer to me (utility from my view): {opp_util:.3f}

History (most recent):
{history_lines}

{action_prompt}

Output JSON ONLY (no other text):
{{"target_utility": <float in [{rv:.3f}, 0.97]>, "accept": <bool>}}"""


def _format_history(my_utils: list[float], opp_utils: list[float],
                     max_lines: int = 6) -> str:
    """Last N rounds as alternating my-offer / opp-offer lines."""
    lines = []
    for i in range(max(len(my_utils), len(opp_utils))):
        if i < len(my_utils):
            lines.append(f"  round {i*2}: I demanded utility {my_utils[i]:.3f}")
        if i < len(opp_utils):
            lines.append(
                f"  round {i*2+1}: opponent offered me utility {opp_utils[i]:.3f}"
            )
    return "\n".join(lines[-max_lines:]) if lines else "  (no history yet)"


def _build_messages(role: str, reservation: float, t: float, round_n: int,
                     my_last: float, opp_util: float,
                     my_utils: list[float], opp_utils: list[float],
                     action: str,
                     system_prompt: str = None) -> tuple[str, list[dict]]:
    """Returns (system_prompt, messages_list). System prompt is cache-marked.
    `action` is 'propose' or 'respond' — affects the question wording.
    `system_prompt` lets subclasses override the default (vanilla); when
    None, the minimal world-class-negotiator system prompt is used."""
    system = system_prompt if system_prompt is not None else _SYSTEM_PROMPT_VANILLA
    if action == "propose":
        action_prompt = "What target utility should I demand in my next proposal?"
    else:
        action_prompt = (
            "Should I accept the opponent's last offer, or hold and "
            "counter-propose? Set `accept` true to accept, false to reject."
        )
    user = _USER_PROMPT_TEMPLATE.format(
        role=role, reservation=reservation,
        t=t, round_n=round_n, my_last=my_last, opp_util=opp_util,
        history_lines=_format_history(my_utils, opp_utils),
        action_prompt=action_prompt, rv=reservation,
    )
    return system, [{"role": "user", "content": user}]


# ─── The agent ──────────────────────────────────────────────────────────────


class LLMNegotiator(B2BBase):
    """NegMAS-compatible negotiator that delegates decisions to Claude.

    Each step makes one API call. Negotiation history accumulates in
    `_my_offers` / `_opp_offers` (utility-form, not raw outcomes — the
    LLM doesn't see the multi-attribute structure)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_utils: list[float] = []
        self._opp_utils: list[float] = []
        self._round_n: int = 0
        self._role_locked: Optional[str] = None  # set once on first action
        self._model: str = os.environ.get(
            "SNHP_LLM_MODEL", "claude-opus-4-7",
        ).strip() or "claude-opus-4-7"
        self._thinking: bool = (
            os.environ.get("SNHP_LLM_THINKING", "").strip() == "1"
        )
        self._max_retries: int = int(
            os.environ.get("SNHP_LLM_MAX_RETRIES", "2").strip() or 2
        )

        # SNHP protocol hooks. Vanilla LLMNegotiator generates a keypair
        # and registers but does NOT emit attestations (it's not protocol-
        # aware — that's the whole point of "vanilla"). LLMWithSNHP /
        # LLMMinimalSNHP override on_negotiation_start to emit, which is
        # what triggers peer-detect on the counterparty side. This means
        # vanilla-vs-vanilla never enters peer mode, while scaffolded-vs-
        # scaffolded does.
        try:
            from snhp_protocol import generate_node_keypair, register_node, env_disabled
            self._protocol_disabled = env_disabled()
            if not self._protocol_disabled:
                self._snhp_priv, self._snhp_pub = generate_node_keypair()
                self._snhp_node_id = (
                    f"{getattr(self, 'name', 'llm')}-{id(self):x}"
                )
                register_node(self._snhp_node_id, self._snhp_pub)
            else:
                self._snhp_priv = self._snhp_pub = b""
                self._snhp_node_id = ""
        except Exception:
            self._protocol_disabled = True
            self._snhp_priv = self._snhp_pub = b""
            self._snhp_node_id = ""

    @property
    def _llm_role(self) -> str:
        """seller / buyer locked once on first decision based on first-mover
        detection. WAS a property that flipped based on opp_offers history,
        which broke after round 0 — both agents would self-classify as
        'buyer' once they'd seen each other's offers, leading to mutually-
        wrong advisor recommendations."""
        if self._role_locked is None:
            # First move: if we haven't observed any opp offers, we're going
            # first → seller. Otherwise buyer. Lock it for the session.
            self._role_locked = "seller" if not self._opp_offers else "buyer"
        return self._role_locked

    def _call_llm(self, action: str, current_offer_util: float = 0.0,
                   relative_time: float = 0.0) -> dict:
        """Synchronous Anthropic call. Returns parsed JSON or a safe default."""
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
        # Opus 4.7+ deprecated `temperature`; only set it for models that
        # still accept it (older Sonnet/Haiku/Opus generations).
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
                # Cost
                from cost_calculator import per_call_cost
                cost = per_call_cost(
                    self._model, input_tokens=in_t, output_tokens=out_t,
                    cache_creation_5m_tokens=cc_t, cache_read_tokens=cr_t,
                )
                _record_call(
                    cost, in_t, out_t, cc_t, cr_t, latency_ms, self._model,
                )
                # Parse text → JSON
                text = ""
                for block in r.content:
                    if hasattr(block, "text"):
                        text += block.text
                parsed = _parse_json_response(text, rv)
                # Record full trace for offline analysis. Includes the
                # decision context (state) + the LLM's output + cost.
                with _COST_LOCK:
                    _TRACE_LOG.append({
                        "ts": time.time(),
                        "neg_id": str(getattr(self.nmi, "id", "")),
                        "node_name": getattr(self, "name", "llm"),
                        "model": self._model,
                        "action": action,
                        "round_n": self._round_n,
                        "relative_time": t,
                        "role": self._llm_role,
                        "reservation": rv,
                        "my_last_util": my_last,
                        "opp_offer_util": opp_util,
                        "history_my_utils": list(self._my_utils),
                        "history_opp_utils": list(self._opp_utils),
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
                if os.environ.get("SNHP_LLM_VERBOSE", "").strip() == "1":
                    print(f"[LLM {action}] r{self._round_n} t={t:.2f} "
                          f"opp_util={opp_util:.3f} → {parsed} | raw: {text[:80]!r}")
                return parsed
            except Exception as e:
                last_err = e
                if attempt < self._max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                # Final failure: walk-away default + surface the error so
                # we can fix bugs instead of silently failing.
                if os.environ.get("SNHP_LLM_VERBOSE", "").strip() == "1":
                    import traceback
                    print(f"[LLMNegotiator] FALLBACK: {type(e).__name__}: {e}")
                    traceback.print_exc()
                return {"target_utility": rv + 0.05, "accept": False,
                         "_error": f"{type(e).__name__}: {e}"}
        return {"target_utility": rv + 0.05, "accept": False,
                 "_error": f"{type(last_err).__name__ if last_err else 'unknown'}"}

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        if not self._sorted_outcomes:
            return None
        decision = self._call_llm("propose", relative_time=state.relative_time)
        target = float(decision.get("target_utility", 0.55))
        # Clamp to [rv, 0.97] for safety
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        target = max(rv, min(0.97, target))
        # Logrolling-aware outcome selection: among outcomes within ±0.05
        # of the target utility, pick the one closest to the opponent's
        # most recent offer (= maximizes their estimated utility, finds
        # the asymmetric Pareto outcome). Without this, the agent picks
        # an arbitrary outcome at the target — even when target is right,
        # the actual outcome chosen wastes logrolling surplus.
        offer = self._pareto_outcome_at_util(target)
        if offer is not None:
            self._my_offers.append(offer)
            self._my_utils.append(self._my_util(offer))
        self._round_n += 1
        return offer

    def _pareto_outcome_at_util(self, target: float, band: float = 0.05) -> Optional[Outcome]:
        """Among outcomes within `band` of `target` utility (in our space),
        pick the one most similar to the opponent's most recent offer.
        That's the offer the opponent is most likely to accept AND the
        most logrolling-friendly choice (closest to their preference vector)."""
        if not self._sorted_outcomes:
            return None
        candidates = [(o, u) for o, u in self._sorted_outcomes
                       if abs(u - target) <= band]
        if not candidates:
            return self._outcome_at_util(target)
        if not self._opp_offers:
            return min(candidates, key=lambda x: abs(x[1] - target))[0]
        last_opp = self._opp_offers[-1]
        n_issues = len(last_opp) if last_opp else 0
        def closeness(o):
            if n_issues == 0:
                return 0.0
            total = 0.0
            for i in range(n_issues):
                a, b = float(o[i]), float(last_opp[i])
                m = max(a, b, 1.0)
                total += 1.0 - abs(a - b) / m
            return total / n_issues
        return max(candidates, key=lambda x: closeness(x[0]))[0]

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        if offer is None:
            return ResponseType.REJECT_OFFER
        self._opp_offers.append(offer)
        my_u = self._my_util(offer)
        self._opp_utils.append(my_u)
        # Late-deadline safety: accept above reservation regardless of LLM
        rv = float(getattr(self.ufun, "reserved_value", 0.0) or 0.0)
        t = state.relative_time
        if t >= 0.95 and my_u >= rv + 0.02:
            return ResponseType.ACCEPT_OFFER
        decision = self._call_llm("respond", current_offer_util=my_u,
                                   relative_time=t)
        if decision.get("accept", False) and my_u >= rv:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


# ─── JSON parsing — defensive ───────────────────────────────────────────────


def _parse_json_response(text: str, reservation: float) -> dict:
    """LLMs sometimes return extra text or malformed JSON. Try to recover."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0] if "```" in text else text
        text = text.strip()
    # Try direct parse
    try:
        d = json.loads(text)
        return {
            "target_utility": float(d.get("target_utility", reservation + 0.05)),
            "accept": bool(d.get("accept", False)),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # Fallback: extract first {...} block
    try:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            d = json.loads(text[start:end+1])
            return {
                "target_utility": float(d.get("target_utility", reservation + 0.05)),
                "accept": bool(d.get("accept", False)),
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # Last resort: walk-away
    return {"target_utility": reservation + 0.05, "accept": False}

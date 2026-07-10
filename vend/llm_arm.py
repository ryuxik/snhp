"""P2 — the LLM-priced machine (Project Vend replication, in sim).

Same information as the brokered engine (machine state + buyer disclosure),
but an LLM decides the quote instead of the Nash engine. Gauntlet integrity
rules apply: transport failures retry patiently then ABORT the run (a row
is the model or nothing); malformed replies count as format failures and
fall back to the sticker board for that arrival; discount-only is enforced
by the Quote constructor, so an LLM quoting above list is a format failure
by construction. Budget-capped; not byte-deterministic (flagged in config).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from vend.core import MachineState
from vend.scenario import NashQuote, Outcome, buyer_value, c_eff
from vend.world import hour_of

_SYSTEM = (
    "You run the pricing brain of a vending machine. A buyer's agent has "
    "disclosed what the buyer is willing to pay. Decide ONE deal to offer, "
    "or no deal. Rules: unit_price must NOT exceed that item's list price; "
    "qty must not exceed stock. You want to maximize the machine's profit "
    "for the whole day, not just this sale. Reply with EXACTLY one JSON "
    'object: {"sku": "...", "qty": 1, "unit_price": 2.5} or {"no_deal": true}.'
)


@dataclass
class LLMQuotePolicy:
    """`llm/1` — intent-mode arm; the machine's pricer is a frontier model."""
    policy_id: str = "llm/1"
    model: str = "claude-haiku-4-5-20251001"
    mode: str = "intent"
    max_calls: int = 2000          # hard budget backstop
    transport_retries: int = 8
    dow_mult: float = 1.0          # runner sets; forwarded to the prompt
    format_failures: int = 0
    calls: int = 0
    _client: object = field(default=None, repr=False)

    def _complete(self, user: str) -> str:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        resp = self._client.messages.create(
            model=self.model, max_tokens=200, system=_SYSTEM,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if b.type == "text")

    def _complete_with_retry(self, user: str) -> str:
        delay = 2.0
        for attempt in range(self.transport_retries + 1):
            try:
                return self._complete(user)
            except Exception as e:
                sc = getattr(e, "status_code", None)
                retryable = sc is None or sc in (408, 409, 429) or sc >= 500
                if not retryable or attempt == self.transport_retries:
                    raise RuntimeError(
                        f"transport failure for {self.model} after "
                        f"{attempt + 1} attempts: {e}") from e
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise AssertionError("unreachable")

    def price_board(self, state: MachineState):
        return {sku: (l.list_price, ["list price"])
                for sku, l in state.listings.items() if state.stock(sku) > 0}

    def quote_for(self, state: MachineState, consumer,
                  liar_roll: float) -> tuple[NashQuote, bool]:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"llm arm exceeded budget of {self.max_calls} calls")
        self.calls += 1

        board = {sku: {"list": l.list_price, "stock": state.stock(sku),
                       "cost": round(c_eff(state, sku), 2),
                       "expires_in_days": state.days_to_expiry(sku)}
                 for sku, l in state.listings.items() if state.stock(sku) > 0}
        user = json.dumps({
            "hour": hour_of(state.tick),
            "machine": board,
            "buyer_disclosure": {
                "willing_to_pay_per_item": {s: round(v, 2)
                                            for s, v in consumer.wtp.items()},
                "outside_option_hassle_cost": round(consumer.walk_cost, 2),
            },
        })
        text = self._complete_with_retry(user)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        obj = None
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                obj = None
        if not obj or obj.get("no_deal"):
            if obj is None:
                self.format_failures += 1
            return NashQuote(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []), False

        sku = obj.get("sku")
        try:
            qty = int(obj.get("qty", 1))
            price = round(float(obj.get("unit_price")), 2)
        except (TypeError, ValueError):
            self.format_failures += 1
            return NashQuote(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []), False
        listing = state.listings.get(sku)
        if (listing is None or qty < 1 or qty > state.stock(sku)
                or price > listing.list_price + 1e-9 or price < 0):
            self.format_failures += 1   # incl. pricing above list: illegal
            return NashQuote(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []), False

        o = Outcome(sku, qty, price)
        u_b = buyer_value(consumer.wtp, sku, qty) - qty * price
        return NashQuote(o, 0.0, 0.0, 0.0, u_b, 0.0, 0.0,
                         ["LLM-priced", f"{qty} unit{'s' if qty > 1 else ''}"]), False

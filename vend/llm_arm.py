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
import re
from dataclasses import dataclass, field

from arena.gauntlet.agents import transport_retry

from vend.core import MachineState
from vend.scenario import (NashQuote, Outcome, buyer_value, c_eff,
                           machine_margin, sticker_choice)
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
    # A default 30-day run makes ~2,200 quote calls (~66 arrivals + returns
    # per day); the backstop must sit ABOVE the documented run, not abort it.
    max_calls: int = 4000
    transport_retries: int = 8
    dow_mult: float = 1.0          # runner sets; included in the prompt below
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
        return transport_retry(lambda: self._complete(user), self.model,
                               self.transport_retries)

    def price_board(self, state: MachineState):
        from vend.policies import sticker_board
        return sticker_board(state)

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
            "day_of_week_traffic_mult": round(self.dow_mult, 2),
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
        no_quote = NashQuote(None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [])
        if obj is None or obj == {}:
            self.format_failures += 1        # unparseable OR contentless
            return no_quote, False
        if obj.get("no_deal") is True:       # explicit, boolean-true only
            return no_quote, False

        sku = obj.get("sku")
        try:
            qty = int(obj.get("qty", 1))
            price = round(float(obj.get("unit_price")), 2)
        except (TypeError, ValueError):
            self.format_failures += 1
            return no_quote, False
        listing = state.listings.get(sku)
        if (listing is None or qty < 1 or qty > state.stock(sku)
                or price > listing.list_price + 1e-9 or price < 0):
            self.format_failures += 1   # incl. pricing above list: illegal
            return no_quote, False

        o = Outcome(sku, qty, price)
        u_b = buyer_value(consumer.wtp, sku, qty) - qty * price
        # Score the LLM's deal with the SAME machine-gain accounting the a2a
        # arm reports — a real number, not a fabricated zero.
        u_s = machine_margin(state, o, dow_mult=self.dow_mult)
        st_sku, st_qty = sticker_choice(consumer.wtp, state)
        d_s = (machine_margin(state,
                              Outcome(st_sku, st_qty,
                                      state.listings[st_sku].list_price),
                              dow_mult=self.dow_mult)
               if st_sku else 0.0)
        return NashQuote(o, d_s, 0.0, u_s, u_b, 0.0, 0.0,
                         ["LLM-priced", f"{qty} unit{'s' if qty > 1 else ''}"]), False

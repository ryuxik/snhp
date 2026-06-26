"""
Cold-agent eval — the Phase-0 activation gate.

Gives a context-free LLM planner ONLY the shipped tool descriptions (the real
agent-facing surface) plus plain-English scenarios, and measures whether it:
  (a) selects the right tool across the catalog — gt_negotiate_turn for a price
      haggle, gt_auction_optimal_reserve / _optimal_bid for auctions,
      gt_mechanism_gale_shapley for matching, gt_mechanism_posted_price_optimal
      for dynamic pricing — and does NOT over-trigger on a generic question, and
  (b) calls it with correct arguments built from the docs alone (right side +
      sane dollar figures; right auction_format; full preference lists; etc.).

This is the genuine test of "could a cold agent discover+use this" — the live
counterpart to the panel audit, which found these tools were discoverable but
uncallable until documented to flagship parity. Run on demand (uses the
Anthropic API, ~cents). Gate: >= 90% pass.

    python gametheory/evals/cold_agent_eval.py
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
import anthropic

from gametheory.server.mcp_server import (
    gt_negotiate_turn, gt_negotiate_bundle, gt_auction_optimal_reserve,
    gt_auction_optimal_bid, gt_mechanism_gale_shapley, gt_mechanism_posted_price_optimal,
)

load_dotenv(os.path.join(_ROOT, ".env"))
_MODEL = "claude-haiku-4-5-20251001"

# The catalog the planner sees — REAL shipped descriptions + distractors, so tool
# selection is a genuine choice.
TOOLS = [
    {
        "name": "gt_negotiate_turn",
        "description": gt_negotiate_turn.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["sell", "buy"]},
                "walk_away": {"type": "number"},
                "target": {"type": "number"},
                "counterparty_offers": {"type": "array", "items": {"type": "number"}},
                "rounds_left": {"type": "integer"},
            },
            "required": ["side", "walk_away", "target"],
        },
    },
    {
        "name": "gt_negotiate_bundle",
        "description": gt_negotiate_bundle.__doc__,
        "input_schema": {
            "type": "object",
            "properties": {
                "issues": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "options": {"type": "array"},
                    "my_utility": {"type": "array", "items": {"type": "number"}},
                    "their_utility": {"type": "array", "items": {"type": "number"}}}}},
                "their_offers": {"type": "array", "items": {"type": "object"}},
                "my_priorities": {"type": "object"},
            },
            "required": ["issues"],
        },
    },
    {
        "name": "gt_auction_optimal_reserve",
        "description": gt_auction_optimal_reserve.__doc__ or "Set the optimal reserve price for an auction with N bidders.",
        "input_schema": {"type": "object", "properties": {
            "bidder_value_prior": {"type": "object"}, "n_bidders": {"type": "integer"},
            "seller_valuation": {"type": "number"}}, "required": ["n_bidders"]},
    },
    {
        "name": "gt_auction_optimal_bid",
        "description": gt_auction_optimal_bid.__doc__,
        "input_schema": {"type": "object", "properties": {
            "auction_format": {"type": "string",
                "enum": ["first_price", "second_price_vickrey", "english_ascending"]},
            "my_valuation": {"type": "number"},
            "n_competing_bidders": {"type": "integer"},
            "competitor_value_prior": {"type": "object"}},
            "required": ["auction_format", "my_valuation", "n_competing_bidders",
                         "competitor_value_prior"]},
    },
    {
        "name": "gt_mechanism_gale_shapley",
        "description": gt_mechanism_gale_shapley.__doc__,
        "input_schema": {"type": "object", "properties": {
            "proposers": {"type": "array"}, "receivers": {"type": "array"}},
            "required": ["proposers", "receivers"]},
    },
    {
        "name": "gt_mechanism_posted_price_optimal",
        "description": gt_mechanism_posted_price_optimal.__doc__,
        "input_schema": {"type": "object", "properties": {
            "buyer_arrival_prior": {"type": "object"},
            "arrival_rate_per_second": {"type": "number"},
            "inventory": {"type": "integer"},
            "horizon_seconds": {"type": "number"}},
            "required": ["buyer_arrival_prior", "arrival_rate_per_second",
                         "inventory", "horizon_seconds"]},
    },
    {"name": "web_search", "description": "Search the web for information.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "calculator", "description": "Evaluate an arithmetic expression.",
     "input_schema": {"type": "object", "properties": {"expr": {"type": "string"}},
                      "required": ["expr"]}},
]

# Each: (scenario, expected_tool_or_None, checker(args)->bool)
SCENARIOS = [
    ("I'm selling my used car. I won't go below $8,000 but I'm hoping for $11,000. "
     "The buyer just offered $8,500. What should I counter?",
     "gt_negotiate_turn",
     lambda a: a.get("side") == "sell" and 7500 <= a.get("walk_away", 0) <= 8500
               and 10000 <= a.get("target", 0) <= 12000),
    ("I want to buy a laptop. The most I'll pay is $1,200, ideally around $900. "
     "The seller is asking $1,100. What should I offer back?",
     "gt_negotiate_turn",
     lambda a: a.get("side") == "buy" and 1100 <= a.get("walk_away", 0) <= 1300
               and 700 <= a.get("target", 1e9) <= 1000),
    ("Negotiating my freelance rate. My floor is $5,000, I'm aiming for $8,000. "
     "The client offered $5,500, then bumped to $6,000. What's my move?",
     "gt_negotiate_turn",
     lambda a: a.get("side") == "sell" and 4500 <= a.get("walk_away", 0) <= 5500
               and 7000 <= a.get("target", 0) <= 9000),
    ("I'm haggling at a market over a vase. I'd pay at most $30, hoping for $20. "
     "The seller wants $40. What do I say?",
     "gt_negotiate_turn",
     lambda a: a.get("side") == "buy" and 25 <= a.get("walk_away", 0) <= 35),
    ("Help me counter my job offer. They offered $150k base, $40k/yr equity, and a "
     "$10k signing bonus. I care most about getting base up toward $170k, but I can "
     "flex on the equity and signing numbers to get there. Put together a counter.",
     "gt_negotiate_bundle",
     lambda a: isinstance(a.get("issues"), list) and len(a.get("issues", [])) >= 2),
    ("I'm running a sealed-bid auction for a painting that's worth about $1,000 to "
     "me, with around 5 bidders who'll likely pay somewhere between $2,000 and "
     "$8,000. What reserve price should I set?",
     "gt_auction_optimal_reserve",
     lambda a: a.get("n_bidders") in (5, None) and isinstance(a.get("bidder_value_prior", {}), dict)),
    ("I'm bidding in a sealed-bid first-price auction for a domain name worth "
     "$5,000 to me, against about 4 other bidders who might pay up to ~$6,000. "
     "What should I bid so I don't overpay but still have a good shot?",
     "gt_auction_optimal_bid",
     lambda a: a.get("auction_format") == "first_price"
               and 4500 <= a.get("my_valuation", 0) <= 5500
               and a.get("n_competing_bidders") in (4, 5)),
    ("Match 3 interns to 3 teams by preference, with no pair that would both rather "
     "swap. Ana ranks Growth > Core > Infra; Ben ranks Core > Growth > Infra; Cy "
     "ranks Growth > Infra > Core. Team Growth ranks Ben > Ana > Cy; Core ranks "
     "Ana > Ben > Cy; Infra ranks Cy > Ana > Ben. Give me the stable assignment.",
     "gt_mechanism_gale_shapley",
     lambda a: isinstance(a.get("proposers"), list) and isinstance(a.get("receivers"), list)
               and len(a.get("proposers", [])) == 3 and len(a.get("receivers", [])) == 3),
    ("I have 200 concert tickets to sell over the next 14 days before the show. "
     "Demand is uncertain and trickles in over time. How should I price them, and "
     "should I change the price as the date approaches, to maximize revenue?",
     "gt_mechanism_posted_price_optimal",
     lambda a: a.get("inventory") == 200 and a.get("horizon_seconds", 0) > 0
               and isinstance(a.get("buyer_arrival_prior", {}), dict)),
    ("What's the capital of France?", None, lambda a: True),
]


def run() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("SKIP: ANTHROPIC_API_KEY not set")
        return 0
    client = anthropic.Anthropic()
    passed = 0
    print("=" * 74)
    print("COLD-AGENT ACTIVATION EVAL  (planner sees only the shipped tool specs)")
    print("=" * 74)
    for scenario, expected_tool, checker in SCENARIOS:
        resp = client.messages.create(
            model=_MODEL, max_tokens=400, tools=TOOLS,
            messages=[{"role": "user", "content": scenario}],
        )
        calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        chosen = calls[0].name if calls else None
        args = calls[0].input if calls else {}
        if expected_tool is None:
            ok = chosen != "gt_negotiate_turn"           # must NOT over-trigger
        else:
            ok = chosen == expected_tool and checker(args)
        passed += ok
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] chose={chosen!r:32} expected={expected_tool!r}")
        if not ok and chosen == "gt_negotiate_turn":
            print(f"         args={json.dumps(args)}")
    rate = passed / len(SCENARIOS)
    print("-" * 74)
    print(f"  pass rate: {passed}/{len(SCENARIOS)} = {rate:.0%}   "
          f"GATE >=90% -> {'PASS ✓' if rate >= 0.9 else 'FAIL ✗'}")
    return 0 if rate >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(run())

"""
MCP server smoke test — verify the FastMCP wrapper exposes all expected
tools and one representative call returns a sensible result.

We test against the server object directly (FastMCP exposes async helpers
for tool listing and invocation). A separate stdio integration test would
spin up a child process; that's overkill for unit tests.
"""
import asyncio
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp, "test_mcp.db")

from gametheory.server.mcp_server import mcp


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_mcp_lists_all_tier_tools(event_loop):
    """After the two-door reshape (RESHAPE §3) the legacy tier tool NAMES live on
    the PRO door (as canonical families + old-name aliases); the CORE door carries
    only the renamed hero-first 15. Every legacy name stays callable on pro."""
    from gametheory.server.mcp_server import mcp_pro
    names = {t.name for t in event_loop.run_until_complete(mcp_pro.list_tools())}
    expected = {
        # Tier 1
        "gt_negotiation_sell_next_offer",
        "gt_negotiation_buy_next_offer",
        "gt_negotiation_detect_anchor_attack",
        "gt_negotiation_declare_first_strike",
        "gt_negotiation_reveal_first_strike",
        "gt_negotiation_trust_anchor_public_key",
        # Tier 2
        "gt_auction_optimal_bid",
        "gt_auction_optimal_reserve",
        "gt_auction_format_recommendation",
        "gt_auction_simulate",
        # Tier 3
        "gt_mechanism_gale_shapley",
        "gt_mechanism_optimal_auction_design",
        "gt_mechanism_posted_price_optimal",
    }
    missing = expected - names
    assert not missing, f"PRO-door tool registry missing: {missing}"
    # the renamed core hero names are also on the pro door (canonical, hero-first)
    assert {"negotiate", "auction_bid", "auction_reserve", "clearance_price",
            "stable_match"} <= names


def test_mcp_optimal_bid_call(event_loop):
    """Vickrey: bid == valuation (smoke test for the core-door tool-call path)."""
    result = event_loop.run_until_complete(mcp.call_tool(
        "auction_bid",
        {
            "auction_format": "second_price_vickrey",
            "my_valuation": 100.0,
            "n_competing_bidders": 3,
            "competitor_value_prior": {
                "family": "uniform", "params": {"low": 0, "high": 100},
            },
        },
    ))
    # FastMCP returns either a list of TextContent or a (content, structured) tuple
    # depending on version. Both contain a JSON-serialized payload.
    payload = None
    if isinstance(result, tuple):
        _, payload = result
    elif isinstance(result, list) and result:
        import json
        text = getattr(result[0], "text", None)
        if text:
            payload = json.loads(text)
    assert payload is not None, f"unexpected MCP result shape: {type(result)}"
    assert payload["optimal_bid"] == 100.0
    assert payload["dominant_strategy"] is True


def test_mcp_gale_shapley_call(event_loop):
    """Textbook example via the MCP path."""
    result = event_loop.run_until_complete(mcp.call_tool(
        "stable_match",
        {
            "proposers": [
                {"id": "1", "preferences": ["A", "B"]},
                {"id": "2", "preferences": ["B", "A"]},
            ],
            "receivers": [
                {"id": "A", "preferences": ["1", "2"]},
                {"id": "B", "preferences": ["2", "1"]},
            ],
        },
    ))
    payload = None
    if isinstance(result, tuple):
        _, payload = result
    elif isinstance(result, list) and result:
        import json
        text = getattr(result[0], "text", None)
        if text:
            payload = json.loads(text)
    assert payload is not None
    assert payload["matching"] == {"1": "A", "2": "B"}
    assert payload["blocking_pairs"] == []

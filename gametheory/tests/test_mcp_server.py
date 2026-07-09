"""SNHP Advisor MCP server tests — direct tool calls + one full-protocol pass."""
from __future__ import annotations

import json

import pytest

from gametheory.negotiation.mcp_server import (
    advise_bundle, advise_price, mcp, score_deal,
)

ISSUES = [
    {"name": "price", "options": ["1200", "1350", "1500"],
     "my_utility": [0, 50, 100], "their_utility": [100, 50, 0]},
    {"name": "delivery", "options": ["2d", "1w", "3w"],
     "my_utility": [0, 40, 100], "their_utility": [100, 60, 0]},
    {"name": "warranty", "options": ["none", "1y", "3y"],
     "my_utility": [100, 60, 0], "their_utility": [0, 50, 100]},
]


def test_advise_price_counter_and_errors():
    out = advise_price(side="sell", walk_away=80.0, target=120.0,
                       counterparty_offers=[70.0], rounds_left=6, item="a couch")
    assert out["action"] in ("counter", "accept", "walk", "negotiate_directly")
    if out["action"] == "counter":
        assert out["recommended_price"] >= 80.0
        assert "message" in out
    bad = advise_price(side="sell", walk_away=120.0, target=100.0)  # target<=floor
    assert "error" in bad


def test_advise_bundle_logrolls():
    out = advise_bundle(issues=ISSUES,
                        my_priorities={"price": 5, "delivery": 1, "warranty": 1},
                        their_offers=[{"price": "1200", "delivery": "2d", "warranty": "3y"}])
    assert out["action"] in ("counter", "accept", "walk")
    if out["action"] == "counter":
        pkg = out["recommended_offer"]
        assert set(pkg) == {"price", "delivery", "warranty"}
        assert all(pkg[i["name"]] in i["options"] for i in ISSUES)
    assert "inferred_their_priorities" in out
    bad = advise_bundle(issues=[{"name": "x", "options": ["a"], "my_utility": [1]}])
    assert "error" in bad


def test_score_deal_oracle():
    # complementary priorities: I care price, they care warranty → the logroll
    # package (my best price, their best warranty) should capture the frontier
    my_w = {"price": 5, "delivery": 1, "warranty": 1}
    their_w = {"price": 1, "delivery": 1, "warranty": 5}
    logroll_pkg = {"price": "1500", "delivery": "1w", "warranty": "3y"}
    s = score_deal(issues=ISSUES, my_weights=my_w, their_weights=their_w,
                   package=logroll_pkg)
    assert s["frontier_capture"] >= 0.95
    assert s["dollars_left_on_table"] <= 500.0
    # the naive middle split captures less
    mid_pkg = {"price": "1350", "delivery": "1w", "warranty": "1y"}
    m = score_deal(issues=ISSUES, my_weights=my_w, their_weights=their_w,
                   package=mid_pkg)
    assert m["joint_welfare"] == pytest.approx(m["naive_split"], abs=1e-6)
    assert m["frontier_capture"] < s["frontier_capture"]
    # bad package → error, not crash
    bad = score_deal(issues=ISSUES, my_weights=my_w, their_weights=their_w,
                     package={"price": "9999"})
    assert "error" in bad


def test_score_deal_matches_leaderboard_pipeline():
    """PARITY PIN: score_deal must reproduce the gauntlet leaderboard's numbers
    on an arena-shaped scenario — the docstring promises 'the SNHP leaderboard
    metric', and this is what enforces it."""
    import numpy as np
    from arena.gauntlet.protocol import _issues_for, _true_utility, gen_gauntlet_scenarios
    from arena.scenarios import bundle_frontier
    from gametheory.negotiation.frontier import deal_metrics

    sc, w_s, w_b = gen_gauntlet_scenarios(1, seed=4242)[0]
    names = [n for n, _ in sc.issues]
    s_issues, b_issues = _issues_for(sc, "seller"), _issues_for(sc, "buyer")
    # an arbitrary settled package: first option everywhere
    package = {iss["name"]: iss["options"][0] for iss in s_issues}
    # leaderboard pipeline numbers
    w_s_map = {n: float(w) for n, w in zip(names, w_s)}
    w_b_map = {n: float(w) for n, w in zip(names, w_b)}
    joint = (_true_utility(s_issues, w_s_map, package)
             + _true_utility(b_issues, w_b_map, package))
    best, naive = bundle_frontier(sc, w_s, w_b)
    met = deal_metrics(joint, best, naive)
    # score_deal, from the seller's frame
    s = score_deal(issues=s_issues, my_weights=w_s_map, their_weights=w_b_map,
                   package=package)
    assert s["joint_welfare"] == pytest.approx(joint, abs=1e-3)
    assert s["frontier_best"] == pytest.approx(best, abs=1e-3)
    assert s["naive_split"] == pytest.approx(naive, abs=1e-3)
    assert s["frontier_capture"] == pytest.approx(met["capture"], abs=1e-3)
    assert s["dollars_left_on_table"] == pytest.approx(met["dollars_left"], abs=1.0)


@pytest.mark.anyio
async def test_mcp_protocol_roundtrip():
    """Full MCP handshake over in-memory streams: list tools, call one."""
    from mcp.shared.memory import create_connected_server_and_client_session
    async with create_connected_server_and_client_session(
            mcp._mcp_server) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"advise_price", "advise_bundle", "score_deal"} <= names
        res = await session.call_tool("advise_price", {
            "side": "buy", "walk_away": 500.0, "target": 380.0,
            "counterparty_offers": [520.0], "rounds_left": 5})
        assert not res.isError
        payload = json.loads(res.content[0].text)
        assert payload["action"] in ("counter", "accept", "walk",
                                     "negotiate_directly")


@pytest.fixture
def anyio_backend():
    return "asyncio"

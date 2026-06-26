"""
Tests for the plain-terms negotiation tool (the agent-facing entry point).

The point of this layer is usability: a cold agent works in dollars and gets back
dollars. These tests pin that contract — real-unit I/O, a full multi-round dollar
negotiation that converges inside the ZOPA, correct accept/walk/opening decisions,
the fit-check, and crucially NO utility-space leakage in the output.

Run: python -m pytest gametheory/tests/test_plain_terms.py -v
"""
import pytest

from gametheory.negotiation.plain_terms import (
    negotiate_turn, NegotiationInputError,
)

SELLER = dict(side="sell", walk_away=4000.0, target=6000.0)
BUYER = dict(side="buy", walk_away=6000.0, target=4000.0)


def test_recommendation_is_real_dollars_in_range_not_utility():
    r = negotiate_turn(**SELLER, counterparty_offers=[4500.0], rounds_left=6)
    # a [0,1] utility leak would show up as a tiny number; this must be real money
    assert 4000.0 <= r["recommended_price"] <= 6000.0
    assert r["recommended_price"] > 1.0
    assert "$" in r["message"]
    assert r["action"] in ("counter", "accept", "walk")


def test_seller_concedes_as_buyer_climbs():
    prices = [negotiate_turn(**SELLER, counterparty_offers=o, rounds_left=6)["recommended_price"]
              for o in ([4200.0], [4200.0, 4500.0], [4200.0, 4500.0, 4800.0])]
    assert prices[0] >= prices[1] >= prices[2]   # monotone concession
    assert all(4000.0 < p < 6000.0 for p in prices)


def test_full_seller_negotiation_converges_inside_zopa():
    walk, target, buyer_max = 4000.0, 6000.0, 5200.0
    buyer_offers, my_offers, deal = [], [], None
    for rnd in range(8):
        r = negotiate_turn(side="sell", walk_away=walk, target=target,
                           counterparty_offers=buyer_offers, my_previous_offers=my_offers,
                           rounds_left=8 - rnd)
        assert walk <= r["recommended_price"] <= target
        if r["action"] == "accept":
            deal = r["recommended_price"]
            break
        my_offers.append(r["recommended_price"])
        last = buyer_offers[-1] if buyer_offers else 4200.0
        buyer_offers.append(round(min(buyer_max, last + 0.6 * (r["recommended_price"] - last)), 2))
    assert deal is not None, "negotiation should converge to a deal"
    assert walk < deal <= buyer_max + 1.0   # deal sits in the zone of agreement


def test_buyer_counters_below_seller_ask_and_settlement_not_inverted():
    r = negotiate_turn(**BUYER, counterparty_offers=[5800.0], rounds_left=6)
    assert 4000.0 <= r["recommended_price"] <= 6000.0
    assert r["recommended_price"] < 5800.0   # buyer counters BELOW the seller's ask
    # expected settlement must sit between the two live positions (never near max)
    assert r["recommended_price"] <= r["expected_settlement"] <= 5800.0


def test_accept_when_counterparty_meets_our_target():
    r = negotiate_turn(**SELLER, counterparty_offers=[5900.0], rounds_left=6)
    assert r["action"] == "accept"
    assert r["recommended_price"] == 5900.0
    assert "5,900" in r["message"]


def test_walk_when_below_floor_near_deadline():
    r = negotiate_turn(**SELLER, counterparty_offers=[3500.0], rounds_left=2)
    assert r["action"] == "walk"
    # No deal => no settlement figure (don't report a misleading number on a walk).
    assert r["expected_settlement"] is None


def test_opening_move_when_no_offers():
    r = negotiate_turn(**SELLER, rounds_left=6)
    assert r["action"] == "counter"
    assert r["expected_settlement"] is None       # no counterparty position yet


def test_one_shot_returns_negotiate_directly():
    r = negotiate_turn(**SELLER, rounds_left=1)
    assert r["action"] == "negotiate_directly"
    assert r["fit"]["score"] == "poor"


def test_fit_marginal_when_no_room():
    r = negotiate_turn(side="sell", walk_away=5000.0, target=5010.0, rounds_left=6)
    assert r["fit"]["score"] == "marginal"


def test_input_validation():
    with pytest.raises(NegotiationInputError):
        negotiate_turn(side="sell", walk_away=6000.0, target=4000.0, rounds_left=6)  # seller inverted
    with pytest.raises(NegotiationInputError):
        negotiate_turn(side="buy", walk_away=4000.0, target=6000.0, rounds_left=6)   # buyer inverted
    with pytest.raises(NegotiationInputError):
        negotiate_turn(side="trade", walk_away=1.0, target=2.0, rounds_left=6)       # bad side
    with pytest.raises(NegotiationInputError):
        negotiate_turn(side="sell", walk_away=-1.0, target=2.0, rounds_left=6)       # non-positive


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))

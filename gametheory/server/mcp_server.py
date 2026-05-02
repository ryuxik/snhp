"""
MCP server binding for the game-theory toolkit.

Exposes the same handlers as the FastAPI binding (see http.py) over MCP, so
LLM agents that prefer MCP discovery can call the toolkit through their
tool-use loop. Tools are namespaced by tier:
  - gt_negotiation_*   (Tier 1)
  - gt_auction_*       (Tier 2)
  - gt_mechanism_*     (Tier 3)

Run as a stdio MCP server:
  ../venv/bin/python -m gametheory.server.mcp_server

For an HTTP-streamable MCP transport (production), use FastMCP's
streamable_http_app() — wired below behind a flag.
"""
from __future__ import annotations

import sys
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from gametheory.negotiation.sell import sell_next_offer
from gametheory.negotiation.buy import buy_next_offer, detect_anchor_attack
from gametheory.auctions.bidder import optimal_bid
from gametheory.auctions.seller import (
    optimal_reserve, format_recommendation, simulate as auction_simulate,
)
from gametheory.crypto.first_strike import (
    declare_first_strike, reveal_first_strike, trust_anchor_public_key_pem,
)
from gametheory.mechanism.gale_shapley import gale_shapley
from gametheory.mechanism.optimal_auction import optimal_auction_design
from gametheory.mechanism.posted_price import posted_price_optimal


mcp = FastMCP(
    "gametheory",
    instructions=(
        "Equilibrium-aware primitives for AI agents. Tier 1 (negotiation), "
        "Tier 2 (auctions), Tier 3 (mechanism design). Math endpoints are "
        "free. Empirical anchor: SNHP rank #1/21 in NegMAS round-robin. "
        "Honest limitation: declare_first_strike provides cryptographic "
        "commitment but only delivers equilibrium benefit when sellers are "
        "aware of and respect the binding nature."
    ),
)


# ─── Tier 1: Negotiation ─────────────────────────────────────────────────────


@mcp.tool()
def gt_negotiation_sell_next_offer(
    my_reservation: float,
    opponent_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
    pareto_knob: float = 0.5,
    peer_mode: bool = False,
    buyer_wtp_prior: Optional[dict] = None,
) -> dict:
    """
    Sell-side next-offer recommendation.

    Set `peer_mode=True` when the counterparty is a verified SNHP-protocol
    peer (cryptographic attestation). Activates the cooperative architecture:
    max-self signaling rounds 0-1, then cubic descent toward the PEER floor
    (0.55). Adds bilateral cooperation premium ~+7% (CI [+2.8%, +11.8%],
    n=20 LLM tournament, p=0.058 borderline — N=50 confirmation pending).

    Without peer_mode (single-side adoption): SNHP customer beats vanilla
    counterparty by +12.1% head-to-head margin (CI [+6.5%, +17.4%], p<0.0001).

    `pareto_knob ∈ [0, 1]` (only used when peer_mode=False) interpolates
    between deal-rate-max (0) and H2H-margin-max (1). Returns the
    recommended offer (in our utility space), acceptance probability,
    expected payoff, and the inferred posterior over the buyer's WTP.
    """
    return sell_next_offer(
        my_reservation=my_reservation,
        opponent_offer_history=opponent_offer_history,
        my_offer_history=my_offer_history,
        deadline_rounds=deadline_rounds,
        pareto_knob=pareto_knob,
        buyer_wtp_prior=buyer_wtp_prior,
        peer_mode=peer_mode,
    )


@mcp.tool()
def gt_negotiation_buy_next_offer(
    my_reservation: float,
    seller_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
    pareto_knob: float = 0.5,
    defenses: Optional[list[str]] = None,
    market_prior: Optional[dict] = None,
    peer_mode: bool = False,
) -> dict:
    """
    Buy-side next-offer recommendation with a defense bundle.

    Set `peer_mode=True` when the counterparty is a verified SNHP-protocol
    peer to activate cooperative architecture (PEER playbook + signaling).

    If `anchor_attack_detection` is in defenses, supply `market_prior`
    {mu, sigma}. Returns recommended offer + warnings + defense actions.
    """
    return buy_next_offer(
        my_reservation=my_reservation,
        seller_offer_history=seller_offer_history,
        my_offer_history=my_offer_history,
        deadline_rounds=deadline_rounds,
        pareto_knob=pareto_knob,
        defenses=defenses,
        market_prior=market_prior,
        peer_mode=peer_mode,
    )


@mcp.tool()
def gt_negotiation_detect_anchor_attack(
    opponent_offer_history: list[float],
    market_prior: dict,
) -> dict:
    """
    Z-score the opponent's opening offer against a market prior {mu, sigma}.
    Recommends ignore / counter_with_market / walk_away.
    """
    return detect_anchor_attack(
        opponent_offer_history=opponent_offer_history,
        market_prior=market_prior,
    )


@mcp.tool()
def gt_negotiation_declare_first_strike(
    buyer_id: str,
    seller_id: str,
    reservation_hash: str,
    deadline_iso: str,
    binding_ttl_seconds: int,
) -> dict:
    """
    Cryptographically commit to a buyer reservation. Returns an EdDSA-signed
    JWT attestation the buyer shows the seller. Use SHA-256 over
    (reservation || nonce || salt || buyer_id || seller_id), base64url-encoded
    without padding, as `reservation_hash`.
    """
    return declare_first_strike(
        buyer_id=buyer_id, seller_id=seller_id,
        reservation_hash=reservation_hash,
        deadline_iso=deadline_iso,
        binding_ttl_seconds=binding_ttl_seconds,
    )


@mcp.tool()
def gt_negotiation_reveal_first_strike(
    commitment_id: str, reservation: float, nonce: str, salt: str,
) -> dict:
    """Reveal a previous first-strike to obtain the binding offer."""
    return reveal_first_strike(
        commitment_id=commitment_id,
        reservation=reservation, nonce=nonce, salt=salt,
    )


@mcp.tool()
def gt_negotiation_trust_anchor_public_key() -> dict:
    """ASCII PEM of the server's first-strike attestation public key."""
    return {"public_key_pem": trust_anchor_public_key_pem()}


# ─── Tier 2: Auctions ────────────────────────────────────────────────────────


@mcp.tool()
def gt_auction_optimal_bid(
    auction_format: Literal["first_price", "second_price_vickrey", "english_ascending"],
    my_valuation: float,
    n_competing_bidders: int,
    competitor_value_prior: dict,
    reserve_price: Optional[float] = None,
    risk_aversion: float = 1.0,
) -> dict:
    """
    Optimal bid for {first_price | second_price_vickrey | english_ascending}.
    Vickrey is truthful. First-price uses the BNE for symmetric IPV.
    """
    return optimal_bid(
        auction_format=auction_format,
        my_valuation=my_valuation,
        n_competing_bidders=n_competing_bidders,
        competitor_value_prior=competitor_value_prior,
        reserve_price=reserve_price,
        risk_aversion=risk_aversion,
    )


@mcp.tool()
def gt_auction_optimal_reserve(
    bidder_value_prior: dict, n_bidders: int, seller_valuation: float,
) -> dict:
    """Myerson optimal reserve from virtual-value-equal-seller-valuation."""
    return optimal_reserve(
        bidder_value_prior=bidder_value_prior,
        n_bidders=n_bidders,
        seller_valuation=seller_valuation,
    )


@mcp.tool()
def gt_auction_format_recommendation(
    bidder_value_prior: dict, n_bidders: int, seller_valuation: float,
    weights: Optional[dict] = None,
) -> dict:
    """Recommend format from {first_price, vickrey, english} given weights."""
    return format_recommendation(
        bidder_value_prior=bidder_value_prior, n_bidders=n_bidders,
        seller_valuation=seller_valuation, weights=weights,
    )


@mcp.tool()
def gt_auction_simulate(
    auction_format: Literal["first_price", "second_price_vickrey", "english_ascending"],
    bidder_priors: list[dict], reserve_price: float,
    n_simulations: int = 10_000, seed: Optional[int] = None,
) -> dict:
    """Monte Carlo auction revenue + efficiency."""
    return auction_simulate(
        auction_format=auction_format, bidder_priors=bidder_priors,
        reserve_price=reserve_price, n_simulations=n_simulations, seed=seed,
    )


# ─── Tier 3: Mechanism Design ───────────────────────────────────────────────


@mcp.tool()
def gt_mechanism_gale_shapley(
    proposers: list[dict], receivers: list[dict],
) -> dict:
    """
    Stable matching via deferred acceptance. Proposers/receivers each have
    {id, preferences} (and optional capacity for receivers). Returns a
    proposer-optimal stable matching plus a blocking-pair sanity check.
    """
    return gale_shapley(proposers=proposers, receivers=receivers)


@mcp.tool()
def gt_mechanism_optimal_auction_design(
    bidder_priors: list[dict],
    seller_valuation: float,
    objective: Literal["revenue", "welfare"] = "revenue",
    n_simulations: int = 5_000,
    seed: int = 42,
) -> dict:
    """
    Myerson revenue-optimal mechanism for asymmetric IPV. Per-bidder
    reserves; collapses to second-price-with-reserve under symmetric IPV.
    """
    return optimal_auction_design(
        bidder_priors=bidder_priors, seller_valuation=seller_valuation,
        objective=objective, n_simulations=n_simulations, seed=seed,
    )


@mcp.tool()
def gt_mechanism_posted_price_optimal(
    buyer_arrival_prior: dict,
    arrival_rate_per_second: float,
    inventory: int,
    horizon_seconds: float,
    n_simulations: int = 2_000,
    seed: int = 42,
) -> dict:
    """
    Gallego-van Ryzin posted-price (static p* + dynamic backward-DP schedule).
    """
    return posted_price_optimal(
        buyer_arrival_prior=buyer_arrival_prior,
        arrival_rate_per_second=arrival_rate_per_second,
        inventory=inventory, horizon_seconds=horizon_seconds,
        n_simulations=n_simulations, seed=seed,
    )


def main() -> None:
    """Entry point for the `gametheory-mcp` console script (stdio MCP)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

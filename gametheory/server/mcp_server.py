"""
MCP server binding for the game-theory toolkit — TWO DOORS.

Exposes the same handlers as the FastAPI binding (see http.py) over MCP, so
LLM agents that prefer MCP discovery can call the toolkit through their
tool-use loop. The surface is reshaped into two doors (see
snhp-launch/store/RESHAPE.md):

  - `mcp`      the CORE door — EXACTLY 15 hero-first tools an ordinary agent
               needs (free negotiation math first, then agent memory + receipted
               sessions + the shelf). Mounted at /mcp by the FastAPI app.
  - `mcp_pro`  the PRO door — EVERYTHING: the 15 canonical tools plus the
               advanced families that leave the core door (verified
               agent-to-agent + AP2 settlement, first-strike attestation,
               pondering sessions, auction design/sim, the offer-graph engine,
               the demand-tally readers) plus every OLD tool name as a thin
               alias. Mounted at /mcp/pro. Nothing the toolkit ever exposed is
               lost — power users stay in MCP.

The reshape changes MCP-facing NAMES, DESCRIPTIONS and DOORS only. Slot ids,
telemetry keys, HTTP routes, pricing, and the engine calls are untouched, so the
referendum/R-gate data stays comparable across the rename (RESHAPE §5).

Tool implementations are plain module-level functions (their Python identifiers
unchanged, so direct imports keep working); an explicit ordered registration
block at the bottom binds each onto one or both doors — registration order ==
display order.

Run as a stdio MCP server (local/trusted host — the A2A build_peer_proof step
signs LOCALLY, so the operator private key never leaves your machine). The stdio
server exposes the PRO door so local power-user flows (A2A, first-strike) work:
  ../venv/bin/python -m gametheory.server.mcp_server

For an HTTP-streamable MCP transport (production), use FastMCP's
streamable_http_app() — wired in http.py for each door.
"""
from __future__ import annotations

import functools
import hashlib
import json
import sys
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from gametheory.negotiation.sell import sell_next_offer
from gametheory.negotiation.buy import buy_next_offer, detect_anchor_attack
from gametheory.negotiation.plain_terms import negotiate_turn as _negotiate_turn
from gametheory.negotiation.bundle import negotiate_bundle as _negotiate_bundle
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
from gametheory.server import registry as _registry
from gametheory.server import peering as _peering
from gametheory.server import settlement as _settlement
import base64 as _base64

# The certification test's Pareto oracle as a tool (https://snhp.dev/certificate):
# score any settled multi-issue deal — joint welfare vs the exact frontier,
# "dollars left on the table". Shared implementation with `arena/gauntlet/`.
from gametheory.negotiation.mcp_server import score_deal as _score_deal  # noqa: E402

# Door-attribution contextvar (observatory §6). Set by each door's registration
# wrapper (_tool) around every call, then read ADDITIVELY by vend.telemetry so an
# MCP telemetry line can be attributed to the door it arrived through (core vs
# pro). Guarded: vend ships in the repo/image, not the PyPI wheel — the stdio
# server must import fine without it, in which case door tagging is simply a no-op.
try:
    from vend.telemetry import mcp_door as _telemetry_door  # noqa: E402
except Exception:                                            # pragma: no cover
    _telemetry_door = None                                   # type: ignore[assignment]


# ─── The two doors (identical transport settings; different tool sets) ────────

def _make_door(name: str, instructions: str) -> FastMCP:
    """A FastMCP door with the shared production transport settings. The CORE
    door (`mcp`) and the PRO door (`mcp_pro`) use IDENTICAL stateless-HTTP +
    DNS-rebinding host allow-list config — ONLY their tool set, ordering, and
    instructions differ. stdio ignores these HTTP-only settings."""
    return FastMCP(
        name,
        instructions=instructions,
        # Hosted streamable-HTTP transport (mounted by the FastAPI app). Stateless
        # so it works behind Fly's proxy + auto-stop; the host allow-list is
        # DNS-rebinding protection scoped to our real domains. stdio (the
        # gametheory-mcp console script) ignores these HTTP-only settings.
        stateless_http=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            allowed_hosts=["snhp.dev", "www.snhp.dev", "api.snhp.dev",
                           "snhp.fly.dev", "localhost", "127.0.0.1"],
            allowed_origins=["https://snhp.dev", "https://www.snhp.dev",
                             "https://snhp.fly.dev"],
        ),
    )


mcp = _make_door(
    "gametheory",
    instructions=(
        "Free, one-call negotiation math for agents — no account, no key. START "
        "WITH `negotiate` (your math-optimal next move in any price haggle) or "
        "`negotiate_bundle` (several linked issues at once, logrolled); "
        "`score_deal`, `auction_bid`, `auction_reserve`, `clearance_price`, and "
        "`stable_match` round out the free math. When you need it ON THE RECORD, "
        "`session_open` opens a $2 receipted, replayable negotiation session "
        "(then session_advise / session_bundle / session_close). When your agent "
        "needs to REMEMBER, `memory_save` / `memory_load` are persistent "
        "cross-session memory — you encrypt before saving; the store holds only "
        "ciphertext (blind custody) and cannot read it. `store_catalog` shows the "
        "shelf and your balance; `store_request` files what we don't stock yet. "
        "Empirical anchor: the negotiate recommender is ~12% better head-to-head "
        "(n=20 paired LLM negotiations, p<0.0001). Power users: the FULL surface "
        "(verified agent-to-agent + AP2 settlement, first-strike attestation, "
        "auction design/sim, offer-graph engine, legacy names) is the pro door "
        "at /mcp/pro/."
    ),
)

mcp_pro = _make_door(
    "gametheory-pro",
    instructions=(
        "The FULL SNHP surface — power users. Everything on the CORE door "
        "(/mcp/) plus verified agent-to-agent peering + AP2 settlement "
        "(gt_a2a_*), first-strike attestation, free pondering sessions, auction "
        "design/simulation, the offer-graph engine, the demand-tally readers, and "
        "every legacy tool name as an alias. Ordinary agents want the smaller "
        "core door at /mcp/. Free math still leads (negotiate, negotiate_bundle, "
        "…); paid tools state their price in the first line. Honest limitation: "
        "declare_first_strike provides cryptographic commitment but only delivers "
        "an equilibrium benefit when sellers are aware of and respect the binding "
        "nature. Run this door's stdio build on a trusted/local host — "
        "gt_a2a_build_peer_proof signs LOCALLY, so your operator key never leaves "
        "your machine."
    ),
)


# ─── Flagship: plain-terms negotiation (start here) ──────────────────────────


def gt_negotiate_turn(
    side: str,
    walk_away: float,
    target: float,
    counterparty_offers: Optional[list[float]] = None,
    my_previous_offers: Optional[list[float]] = None,
    rounds_left: int = 8,
    item: str = "this",
    compute_ms: int = 0,
) -> dict:
    """Your math-optimal next move in any price negotiation — free, no account or key needed.

    USE THIS WHEN: you're haggling over a single PRICE across multiple back-and-
    forth rounds and want a better outcome than winging it. Validated edge: ~12%
    better head-to-head (measured on this recommender, n=20 paired LLM
    negotiations, 95% CI +6.5-17.4%, p<0.0001). NOT FOR: one-shot or fixed prices
    (it'll tell you to just negotiate directly); multi-issue bundles (use
    negotiate_bundle — it logrolls across several linked issues); or non-price
    decisions like accept-vs-decline a job offer (just reason it through).

    You provide only what you already know — no game theory:
      side          "sell" or "buy"
      walk_away     your reservation in dollars (seller=floor/minimum, buyer=ceiling/max)
      target        your aspiration in dollars (seller=high, buyer=low)
      counterparty_offers  their offers so far, in dollars, oldest first
      rounds_left   (optional, default 8) roughly how many back-and-forths remain
      compute_ms    (optional, default 0; EXPERIMENTAL) milliseconds of Monte-Carlo
                    rollouts to spend refining the move. 0 = instant closed form.
                    Validated to show NO realized edge over the closed form (n=400,
                    mc_validation.py) — kept off by default as a research mechanism,
                    not a quality improvement. The reply carries a "compute" block

    You get back, in dollars:
      {"action": "counter"|"accept"|"walk", "recommended_price": 5387.0,
       "message": "...the best I can do is $5,387.00", "fit": {...},
       "expected_settlement": 4943.5, "confidence": 0.62}

    WORKED EXAMPLE — selling a contract, floor $4,000, hope $6,000, the buyer has
    bid $4,200 then $4,500:
      negotiate(side="sell", walk_away=4000, target=6000,
                counterparty_offers=[4200, 4500], rounds_left=6)
      -> counter ~$5,387 with a ready-to-send message; ACCEPT once their bid crosses
         the optimal target; WALK if they stay below your floor near the deadline.

    Works against ANY counterparty with zero setup. (The verified-peer cooperation
    premium is the separate, advanced gt_a2a_* flow on the pro door.)
    """
    if compute_ms and compute_ms > 0:
        # Tier 1: spend the budget on Monte-Carlo rollouts, refining the counter.
        from gametheory.negotiation.mc_search import negotiate_turn_mc
        return negotiate_turn_mc(
            side=side, walk_away=walk_away, target=target,
            counterparty_offers=counterparty_offers,
            my_previous_offers=my_previous_offers, rounds_left=rounds_left,
            item=item, compute_ms=compute_ms)
    return _negotiate_turn(
        side=side, walk_away=walk_away, target=target,
        counterparty_offers=counterparty_offers,
        my_previous_offers=my_previous_offers, rounds_left=rounds_left, item=item)


def _bundle_seed(*parts) -> int:
    """Deterministic seed derived from a bundle call's inputs — identical inputs
    map to the identical seed, so identical calls return identical advice. Mirrors
    the free advisor's input-derived determinism (mcp_server.py `_seed_from_args`)
    but is passed STRUCTURALLY as negotiate_bundle(seed=...), never mutating the
    global RNG (P10 Fix 2)."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return int.from_bytes(hashlib.blake2b(blob, digest_size=8).digest(), "big") & 0x7FFFFFFF


def gt_negotiate_bundle(
    issues: list[dict],
    their_offers: Optional[list[dict]] = None,
    my_priorities: Optional[dict] = None,
    my_batna: float = 0.40,
    their_batna_estimate: float = 0.40,
    rounds_left: int = 8,
    compute_ms: int = 0,
) -> dict:
    """Negotiate several linked issues at once by logrolling — free, no account or key needed.

    USE THIS WHEN: a deal has more than one issue on the table and they trade off —
    a job offer (base + equity + signing), a SaaS contract (price + seats + term +
    SLA), any package deal. It concedes on the issues you care about LESS (and the
    other side cares about MORE) to win the ones you care about most — a trade that
    beats splitting every issue down the middle. For a single PRICE, use
    negotiate instead.

    Provide `issues`: a list of {"name", "options" (the choices), "my_utility" (how
    good each option is to YOU — one number per option, any scale), "their_utility"
    (how good each option is to THEM — their preference direction)}. Optionally
    `my_priorities` ({issue_name: weight}, how much each issue matters to you) and
    `their_offers` (their packages so far as {issue_name: option}, oldest first —
    this is what lets it INFER their priorities). Returns {action, recommended_offer
    (issue -> option), message, my_utility, their_expected_utility,
    inferred_their_priorities, trade_logic, fit, confidence, acceptance_probability}.

    Validated (separately from the single-issue +12%): returns a Pareto-efficient
    package that beats naive "split-every-issue-down-the-middle" bargaining by ~40%
    joint surplus (300 random 4-issue profiles). HONEST CAVEAT: the priority
    INFERENCE layered on top is weak (recovery r≈0.3) and currently adds only ~1%
    (and can be slightly NEGATIVE against some opponents) over the same engine run
    with no inference — so the proven value today is the efficient-package search,
    not (yet) the logrolling edge.

    Optional timing refinement: pass `rounds_left` (bargaining rounds remaining)
    with `compute_ms` > 0 to spend that many ms of Monte-Carlo rollouts choosing
    WHICH package to hold for as the other side concedes over the rounds — a firmer
    package closes later (discounted) than a generous one. 0 = the instant
    closed-form package; the reply then carries a `compute` block. Modest by design
    (never worse than the closed form in-model; helps on a minority of deals).

    Example: a SaaS contract — you most want a low price_per_seat, can flex on
    seats/term/SLA. negotiate_bundle(issues=[
      {"name":"price_per_seat","options":["$50","$40","$30"],"my_utility":[0,0.5,1],"their_utility":[1,0.5,0]},
      {"name":"sla","options":["99%","99.9%"],"my_utility":[0,1],"their_utility":[1,0]} ...],
      my_priorities={"price_per_seat":0.55,"sla":0.1,...}, their_offers=[...])
      -> a full package that gives ground on SLA to hold the price.
    """
    if compute_ms and compute_ms > 0:
        # Tier 1 (multi-issue): spend the budget on rollouts over the remaining
        # rounds_left, refining WHICH package to propose (a timing decision). Never
        # worse than the closed-form package in-model. NOTE (P10): negotiate_bundle_mc
        # has its OWN unseeded rollout cloud in mc_search.py — that determinism gap is
        # P9-adjacent (mc_search lane) and is deliberately NOT seeded from here.
        from gametheory.negotiation.mc_search import negotiate_bundle_mc
        return negotiate_bundle_mc(
            issues=issues, their_offers=their_offers, my_priorities=my_priorities,
            my_batna=my_batna, their_batna_estimate=their_batna_estimate,
            rounds_left=rounds_left, compute_ms=compute_ms)
    # Closed-form path: derive a deterministic seed from the inputs (the same
    # input-derived determinism the free advisor gets from _seed_from_args, but via
    # the structural seed= param — no global RNG mutation, so concurrent requests
    # don't perturb each other) and thread rounds_left for the final-round endgame.
    return _negotiate_bundle(
        issues=issues, their_offers=their_offers, my_priorities=my_priorities,
        my_batna=my_batna, their_batna_estimate=their_batna_estimate,
        rounds_left=rounds_left, seed=_bundle_seed(
            issues, their_offers, my_priorities, my_batna, their_batna_estimate))


# ─── Tier 1: Negotiation (low-level primitives — pro door only) ──────────────


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


def gt_negotiation_reveal_first_strike(
    commitment_id: str, reservation: float, nonce: str, salt: str,
) -> dict:
    """Reveal a previous first-strike to obtain the binding offer."""
    return reveal_first_strike(
        commitment_id=commitment_id,
        reservation=reservation, nonce=nonce, salt=salt,
    )


def gt_negotiation_trust_anchor_public_key() -> dict:
    """ASCII PEM of the server's first-strike attestation public key."""
    return {"public_key_pem": trust_anchor_public_key_pem()}


# ─── Tier 2: Auctions ────────────────────────────────────────────────────────


def gt_auction_optimal_bid(
    auction_format: Literal["first_price", "second_price_vickrey", "english_ascending"],
    my_valuation: float,
    n_competing_bidders: int,
    competitor_value_prior: dict,
    reserve_price: Optional[float] = None,
    risk_aversion: float = 1.0,
) -> dict:
    """The optimal bid when you're bidding in an auction — free, no account or key needed.

    USE THIS WHEN: you're a bidder and want the bid that maximizes your expected
    surplus without overpaying. NOT for running an auction (use
    auction_reserve) or 1:1 haggling (use negotiate).

    Provide: auction_format ("first_price" sealed bid, "second_price_vickrey",
    or "english_ascending"); my_valuation (what the item is worth to YOU, in $);
    n_competing_bidders (how many OTHER bidders, not counting you); and
    competitor_value_prior — a rough model of what rivals will pay, e.g.
    {"family":"uniform","params":{"low":0,"high":6000}} (or
    {"family":"lognorm","params":{"mu":8.5,"sigma":0.4}}). Estimate it if unknown.
    Returns {optimal_bid, expected_surplus, win_probability, dominant_strategy,
    rationale} — bid and surplus in the SAME $ you passed in.

    Example: a domain worth $5,000 to you, 4 rivals who'd pay up to ~$6,000, in a
    sealed first-price auction -> auction_bid(auction_format="first_price",
    my_valuation=5000, n_competing_bidders=4,
    competitor_value_prior={"family":"uniform","params":{"low":0,"high":6000}})
    -> optimal_bid ~$4,000, win_probability ~0.48.
    """
    return optimal_bid(
        auction_format=auction_format,
        my_valuation=my_valuation,
        n_competing_bidders=n_competing_bidders,
        competitor_value_prior=competitor_value_prior,
        reserve_price=reserve_price,
        risk_aversion=risk_aversion,
    )


def gt_auction_optimal_reserve(
    bidder_value_prior: dict, n_bidders: int, seller_valuation: float,
) -> dict:
    """The revenue-optimal reserve price when you're selling — free, no account or key needed.

    USE THIS WHEN: you're running an auction or sale with multiple bidders and need
    the floor price (minimum bid you'll accept) that maximizes your expected
    revenue. NOT for one-on-one haggling (use negotiate for that).

    Provide: n_bidders (how many bidders), seller_valuation (what the item is worth
    to YOU, in $), and bidder_value_prior — a rough model of what bidders will pay,
    e.g. {"family":"uniform","params":{"low":2000,"high":8000}}. Estimate it if
    unknown. Returns the reserve price and expected revenue.

    Example: a painting, ~5 bidders, worth $1,000 to you, bidders likely pay
    $2,000–$8,000 -> auction_reserve(n_bidders=5, seller_valuation=1000,
    bidder_value_prior={"family":"uniform","params":{"low":2000,"high":8000}}).
    """
    return optimal_reserve(
        bidder_value_prior=bidder_value_prior,
        n_bidders=n_bidders,
        seller_valuation=seller_valuation,
    )


def gt_auction_format_recommendation(
    bidder_value_prior: dict, n_bidders: int, seller_valuation: float,
    weights: Optional[dict] = None,
) -> dict:
    """Recommend format from {first_price, vickrey, english} given weights."""
    return format_recommendation(
        bidder_value_prior=bidder_value_prior, n_bidders=n_bidders,
        seller_valuation=seller_valuation, weights=weights,
    )


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


def gt_mechanism_gale_shapley(
    proposers: list[dict], receivers: list[dict],
) -> dict:
    """Match two groups by their rankings so no pair wants to swap — free, no account or key needed.

    A STABLE matching: USE THIS WHEN you're assigning two sides to each other by
    mutual preference — interns<->teams, students<->schools, mentors<->mentees —
    and want a result with no "blocking pair" (no person+slot that both prefer
    each other over what they got).

    Provide proposers and receivers, each a list of {"id": name,
    "preferences": [ids of the OTHER side, most-wanted first]}. Receivers may add
    "capacity" (default 1) to accept several. Returns {matching (name -> name),
    unmatched_proposers, blocking_pairs (empty list = provably stable),
    n_proposals}. NOTE: the result is PROPOSER-optimal, so put the side you want
    to favor in `proposers`.

    Example: stable_match(
        proposers=[{"id":"Ana","preferences":["Growth","Core"]},
                   {"id":"Ben","preferences":["Core","Growth"]}],
        receivers=[{"id":"Growth","preferences":["Ben","Ana"]},
                   {"id":"Core","preferences":["Ana","Ben"]}])
    -> matching {"Ana":"Growth","Ben":"Core"}, blocking_pairs [].
    """
    return gale_shapley(proposers=proposers, receivers=receivers)


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


def gt_mechanism_posted_price_optimal(
    buyer_arrival_prior: dict,
    arrival_rate_per_second: float,
    inventory: int,
    horizon_seconds: float,
    n_simulations: int = 2_000,
    seed: int = 42,
) -> dict:
    """Best price plus markdown schedule to clear stock by a deadline — free, no account or key needed.

    USE THIS WHEN: you must sell a FIXED number of units before a cutoff and
    demand arrives over time — event tickets, perishable inventory, end-of-life
    stock. NOT for 1:1 haggling (negotiate) or auctions (auction_bid/reserve).

    Provide: inventory (units to sell); horizon_seconds (selling window in
    SECONDS — 14 days = 14*24*3600 = 1209600); arrival_rate_per_second (expected
    shoppers per second = expected total shoppers / horizon_seconds); and
    buyer_arrival_prior — a rough model of willingness-to-pay, e.g.
    {"family":"uniform","params":{"low":40,"high":150}}. Returns {static_price
    (one good fixed price), static_expected_revenue, dynamic_schedule (list of
    {t_seconds, recommended_price} markdown waypoints), sellthrough_rate,
    rationale} — all prices in the SAME $ as your prior.

    Example: 200 tickets, 14-day window, ~600 shoppers willing to pay $40-$150 ->
    clearance_price(inventory=200, horizon_seconds=1209600,
    arrival_rate_per_second=600/1209600,
    buyer_arrival_prior={"family":"uniform","params":{"low":40,"high":150}})
    -> static_price ~$112, schedule marks down $114 -> ~$76 as the deadline nears.
    """
    return posted_price_optimal(
        buyer_arrival_prior=buyer_arrival_prior,
        arrival_rate_per_second=arrival_rate_per_second,
        inventory=inventory, horizon_seconds=horizon_seconds,
        n_simulations=n_simulations, seed=seed,
    )


# ─── Agent-to-agent commerce (pro door; parity with the HTTP A2A routes) ─────
# Verified-peer negotiation: register an operator identity, exchange peer proofs,
# open a session whose peer_mode is DERIVED from verification (not asserted), then
# negotiate and settle. build_peer_proof signs locally — run this MCP server on a
# trusted/local host so the operator private key never leaves your machine (the
# local-MCP privacy model).


def gt_a2a_register_operator(
    operator_id: str, public_key_b64: str, display_name: Optional[str] = None,
) -> dict:
    """Register your operator identity — STEP 0 of the verified-peer deal flow.

    USE THE A2A FLOW ONLY WHEN the counterparty ALSO runs SNHP; it unlocks a
    cooperation premium (more joint surplus between verified peers) plus a signed,
    settleable AP2 deal record. Against an unknown counterparty, just use
    negotiate / negotiate_bundle — none of this is needed.

    THE FLOW (you and the counterparty each have an Ed25519 keypair):
      0. gt_a2a_register_operator        -> your signed identity attestation (this)
         [optional] gt_a2a_request_domain_challenge + gt_a2a_verify_domain
                                          -> upgrade to sybil-resistant domain identity
      1. gt_a2a_build_peer_proof         -> a per-negotiation proof (signs LOCALLY)
      2. exchange proofs with the counterparty (your channel / an A2A message)
      3. gt_a2a_open_session             -> session_id + peer_mode (TRUE iff both verify)
      4. gt_a2a_next_offer               -> recommendation using the SESSION's peer_mode
      5. gt_a2a_settle                   -> a signed AP2 Cart Mandate (the deal record)

    This step: register operator_id with your base64 Ed25519 PUBLIC key; returns a
    trust-anchor-signed attestation JWT to present in peer proofs.
    """
    return _registry.register_operator(operator_id, public_key_b64, display_name)


def gt_a2a_request_domain_challenge(domain: str, public_key_b64: str) -> dict:
    """Get the DNS-TXT record to publish to prove control of `domain` (sybil-
    resistant, domain-level identity)."""
    return _registry.request_domain_challenge(domain, public_key_b64)


def gt_a2a_verify_domain(
    domain: str, public_key_b64: str, display_name: Optional[str] = None,
) -> dict:
    """Verify the published DNS-TXT challenge and register `domain` as a
    domain-verified operator."""
    return _registry.verify_domain_and_register(domain, public_key_b64, display_name)


def gt_a2a_build_peer_proof(
    operator_attestation_jwt: str, operator_id: str, negotiation_id: str,
    role: str, private_key_b64: str, ttl_seconds: int = 300,
) -> dict:
    """STEP 1 of the A2A flow — sign a per-negotiation peer proof, LOCALLY.

    Bind your registered identity (operator_attestation_jwt from
    gt_a2a_register_operator) to THIS negotiation_id and role ('seller'/'buyer')
    using your operator private key (base64 of the raw 32-byte Ed25519 key). The
    key never leaves this process — run this MCP server on your own host. The proof
    is short-lived and can't be replayed to another negotiation or role. NEXT: send
    it to the counterparty, get theirs, then gt_a2a_open_session with both."""
    return _peering.build_peer_proof(
        operator_attestation_jwt=operator_attestation_jwt,
        operator_id=operator_id, negotiation_id=negotiation_id, role=role,
        private_key_bytes=_base64.b64decode(private_key_b64), ttl_seconds=ttl_seconds,
    )


def gt_a2a_open_session(
    negotiation_id: str, seller_proof: dict, buyer_proof: dict,
    require_level: Literal["self", "domain"] = "self",
) -> dict:
    """STEP 3 of the A2A flow — verify BOTH peer proofs and open a session.

    Submit the seller_proof and buyer_proof (yours + the counterparty's from STEP 2).
    Returns session_id and peer_mode. peer_mode is server-derived and is True ONLY if
    both proofs verify (at/above require_level), are for their roles, are unexpired,
    and name DISTINCT operators — so the premium can't be claimed by lying. Pass
    require_level='domain' to demand domain-verified counterparties. NEXT:
    gt_a2a_next_offer with the returned session_id."""
    return _peering.open_session(
        negotiation_id=negotiation_id, seller_proof=seller_proof,
        buyer_proof=buyer_proof, require_level=require_level,
    )


def gt_a2a_next_offer(
    session_id: str, role: str, my_reservation: float,
    opponent_offer_history: list[float], my_offer_history: list[float],
    deadline_rounds: int = 10, pareto_knob: float = 0.5,
    prior: Optional[dict] = None,
) -> dict:
    """STEP 4 of the A2A flow — your next move, using the SESSION's verified peer_mode.

    role is 'seller' or 'buyer'. The recommender uses the session's server-derived
    peer_mode (not a self-asserted flag), so the cooperation premium applies only on a
    genuinely verified session. my_reservation and the offer histories are in
    NORMALIZED utility [0,1] (map dollars the way negotiate does, or use
    negotiate/negotiate_bundle for the math and this path for the premium +
    settlement). NEXT, once you agree on a price: gt_a2a_settle."""
    if role not in ("seller", "buyer"):
        raise ValueError(f"role must be 'seller' or 'buyer', got {role!r}")
    session = _peering.get_session(session_id)
    if session is None:
        raise ValueError(f"unknown session_id {session_id!r}")
    peer_mode = session["peer_mode"]
    if role == "seller":
        rec = sell_next_offer(
            my_reservation=my_reservation,
            opponent_offer_history=opponent_offer_history,
            my_offer_history=my_offer_history, deadline_rounds=deadline_rounds,
            pareto_knob=pareto_knob, buyer_wtp_prior=prior, peer_mode=peer_mode)
    else:
        rec = buy_next_offer(
            my_reservation=my_reservation,
            seller_offer_history=opponent_offer_history,
            my_offer_history=my_offer_history, deadline_rounds=deadline_rounds,
            pareto_knob=pareto_knob, market_prior=prior, peer_mode=peer_mode)
    return {"session_id": session_id, "peer_mode": peer_mode, "role": role,
            "recommendation": rec}


def gt_a2a_settle(
    session_id: str, agreed_price: float, currency: str = "USD",
    item: Optional[str] = None, buyer_max_price: Optional[float] = None,
    terms: Optional[dict] = None,
) -> dict:
    """STEP 5 (final) of the A2A flow — mint the signed deal record.

    Once both sides agree on agreed_price, this emits a signed AP2 Cart Mandate (a
    non-repudiable VC-JWT naming both verified parties) — and an Intent Mandate too if
    you pass buyer_max_price. Refused unless the session is peer_mode=True (both
    verified and distinct), so a Cart Mandate always names two real, verified parties.
    No escrow; the mandate is the settleable record."""
    session = _peering.get_session(session_id)
    if session is None:
        raise ValueError(f"unknown session_id {session_id!r}")
    # Gate on the server-authoritative peer_mode (both-verified-AND-distinct). A
    # revoked, below-level, or bad-signature proof populates the operator fields
    # but leaves peer_mode False; a non-null/distinct check alone would mint a
    # Cart Mandate for an UNVERIFIED deal.
    if not session["peer_mode"]:
        if (session["seller_operator"]
                and session["seller_operator"] == session["buyer_operator"]):
            raise ValueError("settlement requires distinct counterparties")
        raise ValueError("settlement requires both parties verified; open the "
                         "session with valid, unrevoked, sufficiently-verified "
                         "seller and buyer proofs first")
    out = {"cart_mandate": _settlement.emit_cart_mandate(
        session_id=session_id, negotiation_id=session["negotiation_id"],
        seller_operator=session["seller_operator"],
        buyer_operator=session["buyer_operator"],
        agreed_price=agreed_price, currency=currency, item=item, terms=terms)}
    if buyer_max_price is not None:
        out["intent_mandate"] = _settlement.emit_intent_mandate(
            negotiation_id=session["negotiation_id"],
            buyer_operator=session["buyer_operator"],
            max_price=buyer_max_price, currency=currency, item=item)
    return out


# ─── Offer-graph engine (core/): profile + quote a JSON menu spec ────────────
# The hosted MCP surface of the general engine (compile/profile/quote live at
# /v1/offer/* too — see gametheory/server/offer_api.py, which owns validation).
# Guarded like vend/: core/ ships in the repo and the Docker image but not the
# PyPI wheel — the stdio MCP server must boot without it. Pro door only.

try:
    from gametheory.server import offer_api as _offer_api  # noqa: E402
except ImportError:
    _offer_api = None                              # type: ignore[assignment]

_HAVE_OFFER = _offer_api is not None

if _HAVE_OFFER:

    def offer_profile_menu(spec: dict, state: Optional[dict] = None) -> dict:
        """Profile a seller's menu: classify every dimension FREE or LEVER — where the negotiation surface actually is.

        USE THIS WHEN: you (or the agent you're buying from / selling for) have a
        menu of configurable items and want to know which dimensions are worth
        negotiating on. FREE = zero cost gradient — a costless customization
        (sweetness, cup choice); the buyer just gets their favorite, it is never
        a price lever. LEVER = changing the option moves the seller's effective
        cost — a real negotiation surface (which item, quantity, add-ons).

        `spec` is the declarative JSON menu spec (the same format everywhere in
        SNHP — the /v1/offer/* HTTP endpoints and the JS engine accept it too):

          {"name": "corner coffee cart",
           "dims": [
             {"id": "item", "kind": "choice", "options": [
                {"id": "oat-latte", "price_delta": 5.25, "unit_cost": 1.20},
                {"id": "drip",      "price_delta": 3.00, "unit_cost": 0.40}]},
             {"id": "extras", "kind": "addon",      "options": [...]},
             {"id": "cup",    "kind": "preference", "options": [
                {"id": "for-here"}, {"id": "to-go"}]},
             {"id": "pickup", "kind": "fulfillment", "options": [
                {"id": "now",   "immediate": true,  "slot_ticks": 0},
                {"id": "in-20", "immediate": false, "slot_ticks": 2}]},
             {"id": "qty", "kind": "quantity", "qty_cap": 3}],
           "cost": ["const"]}

        Dimension kinds: choice (pick exactly one), addon (pick a subset),
        preference (pick one, costless taste), fulfillment (timing slot),
        quantity (integer 1..qty_cap). Option fields: price_delta (contribution
        to LIST price), unit_cost, and optionally stock_limited, perishable,
        salvage, immediate, slot_ticks. Cost stack tokens: "const",
        "salvage_on_expiry" (perishables at salvage when expiring),
        "scarcity_shadow" (finite stock displaces list sales),
        {"batch_economies": {"setup": 1.0, "marginal": 0.2}}.

        Optional `state` is the shop moment the cost model reads:
          {"inventory": {"cold-brew": 6}, "expected_demand": {"cold-brew": 10},
           "expiring": ["croissant"], "capacity": {"2": 6}, "tick": 0}

        Returns {dims: [{dim, kind, verdict, cost_spread, why}], verdicts,
        note}. Returns {"error": "..."} on a malformed spec.
        """
        try:
            return _offer_api.profile_menu(spec, state)
        except ValueError as e:
            return {"error": str(e)}

    def offer_quote(
        spec: dict,
        buyer: dict,
        state: Optional[dict] = None,
        config: Optional[dict] = None,
        quote_lookers: bool = True,
        min_price_frac: float = 0.0,
        qty_appetite: bool = False,
        seller_weight: float = 0.5,
    ) -> dict:
        """Price a buyer's cart on a menu — a Nash-split, DISCOUNT-ONLY quote (never above list).

        USE THIS WHEN: you want the engine's advisory price for a configurable
        cart on a seller's menu — which configuration to sell/buy and at what
        price, given the shop's live state. The engine searches every valid
        configuration (or prices the pinned `config`), anchors the no-deal
        point on the buyer's best full-price menu order, and splits only the
        NEWLY-CREATED surplus. HARD GUARANTEE: discount-only — the price is
        never above the menu's list value (`never_above_list: true` in the
        response, enforced in code). A buyer who would have paid list never
        gets a discount out of the seller's standing margin.

        `spec`: the same declarative JSON menu spec as offer_profile_menu.
        `state` (optional): the shop moment — {"inventory": {...},
          "expected_demand": {...}, "expiring": [...], "capacity": {...}}.
        `buyer`: {"values": {"item": {"oat-latte": 6.0}},  # $/unit by dim->option
                  "qty_decay": 0.9,   # each extra unit worth 90% of the previous
                  "outside": 0.0,     # outside-option surplus in $
                  "balk": 0.3,        # chance a walk-in bails at the queue
                  "defer": {"2": 0.1}}  # slot_ticks -> $ cost of waiting
        `config` (optional): pin the cart — {"item": "oat-latte",
          "extras": ["vanilla"], "pickup": "in-20", "qty": 2}; addon dims take
          a list, quantity an int. Omit to search every valid cart.
        Options: quote_lookers=False refuses buyers who'd never pay list (the
        incentive-compatibility floor); min_price_frac=0.8 never quotes below
        80% of list; qty_appetite=True blocks upsell units the buyer values
        below their cost; seller_weight tilts the Nash split (0.5 = symmetric).

        Returns {"outcome": "negotiated"|"at_list"|"walk", "quote": {config,
        price, listv, save, cost, value, seller_gain, buyer_gain, feasible,
        why} | null, "never_above_list": true, "advisory": true, note}.
        Quotes are SIMULATED advisory engine output, not a binding offer from
        any seller. Returns {"error": "..."} on malformed input.
        """
        try:
            return _offer_api.quote_menu(
                spec, buyer, state, config,
                quote_lookers=quote_lookers, min_price_frac=min_price_frac,
                qty_appetite=qty_appetite, seller_weight=seller_weight)
        except ValueError as e:
            return {"error": str(e)}


# ─── Tier 2: Pondering sessions (pro door — spend the counterparty's time) ────


def gt_negotiate_open_session(
    side: str, walk_away: float, target: float, rounds_left: int = 8,
    item: str = "this", compute_ms: int = 200,
) -> dict:
    """Open a stateful price-negotiation session that PONDERS on the other side's clock.

    Unlike one-shot negotiate, a session remembers the running history and —
    after each propose/respond — speculates in the BACKGROUND over the counter-offers
    the other side is likely to make, pre-solving your reply to each. So while you're
    blocked waiting for their response, idle compute is already searching; when their
    counter arrives, gt_negotiate_respond often returns an instant, deeply-searched
    move. side='sell'/'buy', walk_away/target in dollars (same meaning as
    negotiate), compute_ms = rollout budget per move. Returns {session_id}.
    NEXT: gt_negotiate_propose to make your opening move."""
    from gametheory.negotiation import pondering as _p
    sid = _p.open_session(side=side, walk_away=walk_away, target=target,
                          rounds_left=rounds_left, item=item, compute_ms=compute_ms)
    return {"session_id": sid, "rounds_left": rounds_left}


def gt_negotiate_propose(session_id: str, compute_ms: Optional[int] = None) -> dict:
    """Make your next move in a pondering session and kick off background speculation.

    Returns the same dict as negotiate (action, recommended_price, message,
    compute, ...). Immediately after returning, the session searches your replies to
    the counter-offers it expects — on the counterparty's clock. NEXT: when they
    reply, gt_negotiate_respond(session_id, their_offer)."""
    from gametheory.negotiation import pondering as _p
    return _p.get_session(session_id).propose(compute_ms=compute_ms)


def gt_negotiate_respond(
    session_id: str, their_offer: float, compute_ms: Optional[int] = None,
) -> dict:
    """Feed the counterparty's latest dollar offer and get your next move.

    If their offer is roughly what the session anticipated, the deeply-searched reply
    is already cached and returned instantly (the reply's "_pondered" field is True);
    otherwise a fresh warm-started search runs. Same return shape as negotiate."""
    from gametheory.negotiation import pondering as _p
    return _p.get_session(session_id).respond(their_offer, compute_ms=compute_ms)


def gt_negotiate_close_session(session_id: str) -> dict:
    """Close a pondering session and cancel any in-flight background speculation."""
    from gametheory.negotiation import pondering as _p
    return {"closed": _p.close_session(session_id)}


# ─── NEXTMOVE: the agent vending machine (paid advice; see vend/NEXTMOVE.md) ─
# Guarded like http.py's vend mount: vend ships in the repo/image, not the
# PyPI wheel — the MCP server must import fine without it.
try:
    from vend.advice import CATEGORIES as _NM_CATEGORIES, ADVISE_COST_CENTS as _NM_PRICE  # noqa: E402
    _HAVE_ADVICE = True

    def nextmove_catalog() -> dict:
        """The NEXTMOVE vending machine: what's on the shelf and how to pay.
        One SKU: a paid NEGOTIATION SESSION — $2 covers every move of one
        negotiation (up to 10, 7-day window), category-tuned, receipted,
        and deterministic (fixed 400k-rollout budget + seed: same context
        in, bit-identical advice out, auditable via context_hash).

        Free vs paid, honestly: negotiate on this same server is
        free — generic, no receipt, no category tuning, wall-clock compute
        (non-deterministic). Pay when you want the tuned, auditable,
        replayable version with the drafted message and the receipt. (This
        catalog is also folded into store_catalog on the core door.)

        Don't see your category? store_request — unmet requests decide
        what gets stocked next."""
        return {
            "sku": "negotiation_session",
            "price_cents": _NM_PRICE,
            "covers": "all moves of one negotiation (cap 10, TTL 7 days)",
            "categories": [
                {"id": t.id, "label": t.label,
                 "typical_rounds": t.rounds_default,
                 "rounds_note": ("PRIOR, not data — override rounds_left "
                                  "per move if you know your venue"),
                 "usual_side": t.side_hint, "note": t.form_note}
                for t in _NM_CATEGORIES.values()
            ],
            "free_tier": ("negotiate — same engine core, generic, "
                          "unreceipted, non-deterministic; the taste"),
            "pay": ("POST https://api.snhp.dev/v1/billing/checkout_session "
                    "{api_key, pack: small|medium|large} -> hosted Checkout URL "
                    "for your human; credits land on the api_key via webhook. "
                    "Get an api_key: POST /v1/keys."),
            "receipt": "every move: why[], confidence, context_hash, compute block",
        }

    def nextmove_open(api_key: str, category: str, side: str,
                      walk_away: float, target: float,
                      their_offers: Optional[list[float]] = None,
                      my_offers: Optional[list[float]] = None,
                      rounds_left: Optional[int] = None,
                      seed: int = 0) -> dict:
        """Open a $2 receipted negotiation session: deterministic, replayable, every move signed.

        PAID ($2 once, from your credit balance) — the $2 covers EVERY move of
        this negotiation (up to 10 moves, 7 days), tuned to the category. A new
        key's 50¢ starter credit is a taste, not enough for a session — top up
        first. category: resale | supply | retail. side: buy | sell.
        walk_away = your true floor (sell) / ceiling (buy) — private,
        never crossed. Pass their_offers to get the first move back
        immediately with the session. Subsequent moves: session_advise
        with the session_id — no further charge."""
        from vend import session as _vs, telemetry as _tm
        from gametheory.server import billing as _billing
        try:
            sess = _vs.open_session_charged(
                api_key=api_key, category=category, side=side,
                walk_away=walk_away, target=target, seed=seed)
        except _billing.BillingError as e:
            return {"error": str(e), "price_cents": _NM_PRICE,
                    "how_to_pay": "see store_catalog"}
        except KeyError as e:
            return {"error": str(e)}
        # Telemetry must NEVER break the paid response (mirrors the HTTP door): a
        # telemetry OSError after the $2 charge must not destroy the session_id.
        try:
            _tm.log_session_open(api_key=api_key, door="mcp",
                                 category=category, side=side,
                                 stake=abs(target - walk_away),
                                 price_cents=_NM_PRICE,
                                 session_id=sess["session_id"])
        except Exception:
            pass
        out = dict(sess)
        if their_offers is not None:
            # The optional first move must not vaporize the paid session_id: a
            # first-move engine error is REPORTED as a field, not raised away
            # (the $2 already bought the session). Not consumed on failure —
            # session_advise runs the engine before incrementing moves_used.
            try:
                a, idx = _vs.session_advise(
                    session_id=sess["session_id"], api_key=api_key,
                    their_offers=their_offers, my_offers=my_offers,
                    rounds_left=rounds_left)
            except Exception as e:
                out["first_move_error"] = str(e)
                return out
            try:
                _tm.log_advice(advice=a, api_key=api_key, door="mcp",
                               price_cents=0, session_id=sess["session_id"],
                               move_index=idx)
            except Exception:
                pass
            out["first_move"] = {
                "move": a.move, "offer": a.offer, "message": a.message,
                "why": a.why, "confidence_note": a.confidence_note,
                "context_hash": a.context_hash, "move_index": idx,
                "compute": a.engine.get("compute", {}),
                "receipt": a.receipt}      # W2 handoff: the first move's receipt
        return out

    def nextmove_advise(api_key: str, session_id: str,
                        their_offers: list[float],
                        my_offers: Optional[list[float]] = None,
                        rounds_left: Optional[int] = None) -> dict:
        """Your next move inside a receipted session (single-issue) — no additional charge (the $2 at session_open covered it).

        Pass the FULL offer history each time, oldest first. Returns move, exact
        price, ready-to-send message, and the receipt (why[], context_hash,
        deterministic compute block)."""
        from vend import session as _vs, telemetry as _tm
        try:
            a, idx = _vs.session_advise(
                session_id=session_id, api_key=api_key,
                their_offers=their_offers, my_offers=my_offers,
                rounds_left=rounds_left)
        except _vs.SessionError as e:
            return {"error": str(e)}
        # Telemetry must never break the paid response (mirrors the HTTP door).
        try:
            _tm.log_advice(advice=a, api_key=api_key, door="mcp",
                           price_cents=0, session_id=session_id, move_index=idx)
        except Exception:
            pass
        return {"move": a.move, "offer": a.offer, "message": a.message,
                "why": a.why, "confidence_note": a.confidence_note,
                "context_hash": a.context_hash, "policy_id": a.policy_id,
                "move_index": idx, "compute": a.engine.get("compute", {}),
                # W2 handoff: the signed move receipt (GAUNTLET #4) — the free
                # move now hands back the same third-party-checkable receipt the
                # anchor open did, so provenance never drops mid-session.
                "receipt": a.receipt}

    def nextmove_bundle(api_key: str, session_id: str, issues: list[dict],
                        their_offers: Optional[list[dict]] = None,
                        my_priorities: Optional[dict] = None,
                        my_batna: float = 0.40,
                        their_batna_estimate: float = 0.40,
                        cooperation: Optional[float] = None) -> dict:
        """Multi-issue logrolled advice inside a receipted session — no additional charge.

        The logrolling tier, the thing the free tool does NOT have. Trade the
        issues you care less about for the ones you value: issues = [{name,
        options, my_utility (per option), their_utility (your read of their
        direction)}]; their_offers = packages they've tabled, oldest
        first. Returns the recommended package, trade logic, inferred
        counterparty priorities, acceptance probability, and the receipt.
        Deterministic closed form — no rollout theater. The package is
        guaranteed to clear YOUR stated BATNA (enforced, not promised)."""
        from vend import session as _vs, telemetry as _tm
        try:
            a, idx = _vs.session_advise_bundle(
                session_id=session_id, api_key=api_key, issues=issues,
                their_offers=their_offers, my_priorities=my_priorities,
                my_batna=my_batna,
                their_batna_estimate=their_batna_estimate,
                cooperation=cooperation)
        except _vs.SessionError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"invalid issues spec: {e}"}
        # Telemetry must never break the paid response (mirrors the HTTP door).
        try:
            _tm.log_advice(advice=a, api_key=api_key, door="mcp",
                           price_cents=0, session_id=session_id, move_index=idx)
        except Exception:
            pass
        return {"move": a.move, "package": a.engine.get("package"),
                "message": a.message, "why": a.why,
                "confidence_note": a.confidence_note,
                "context_hash": a.context_hash, "move_index": idx,
                "their_expected_utility": a.engine.get("their_expected_utility"),
                "acceptance_probability": a.engine.get("acceptance_probability"),
                # W2 handoff: the signed bundle-move receipt (GAUNTLET #4).
                "receipt": a.receipt}

    def nextmove_close(api_key: str, session_id: str) -> dict:
        """Close a receipted session and get the signed summary receipt.

        Optional — sessions also expire on their own — but closing timestamps the
        outcome, which helps the machine learn real round-counts per
        category. Returns the `closed` flag AND a signed session-summary
        receipt (GAUNTLET #4) — moves count, total charged (one $2 open), and
        the per-move context_hashes — to hand your principal. An unknown session
        or key mismatch leaves `closed` false and returns an `error` instead of
        the receipt (indistinguishable, so a session id can't be probed)."""
        from vend import session as _vs
        closed = _vs.close_session(session_id=session_id, api_key=api_key)
        try:
            receipt = _vs.session_summary_receipt(session_id=session_id,
                                                  api_key=api_key)
        except _vs.SessionError as e:
            return {"closed": closed, "error": str(e)}
        return {"closed": closed, "receipt": receipt}

    def nextmove_request(text: str, api_key: Optional[str] = None,
                         watch: bool = False) -> dict:
        """Ask the vending machine for ANYTHING it doesn't stock — a
        negotiation category, a different game, a capability. Free, keyless OK.
        One intake, two names: this shares the store's demand loop, so a request
        filed here gets the SAME request_id + status you can return to (GAUNTLET
        #5). Check it with GET /v1/store/request/{id}; the public count is
        GET /v1/store/requests. Unmet demand decides the next slot — thank you.

        Pass watch=True WITH an api_key to flag the ask for a heads-up on a
        status flip (poll store_my_requests to see it — poll-based, no push); an
        anonymous watch is ignored, and the chosen flag is echoed as `watch`."""
        from vend import demand as _demand
        rec = _demand.file_request(text=text, api_key=api_key, door="mcp",
                                   watch=watch)
        return {"request_id": rec["request_id"], "status": rec["status"],
                "watch": rec["watch"],
                "check": f"GET /v1/store/request/{rec['request_id']}",
                "note": "unmet demand decides the next slot — thank you"}

except ImportError:
    _HAVE_ADVICE = False


def _nextmove_session_card() -> Optional[dict]:
    """The paid-session (NEXTMOVE) shelf card, so store_catalog can cover the
    WHOLE shelf in one read (RESHAPE §2 #14). Best-effort — a build without
    vend.advice omits it (returns None). No key material, prices only."""
    try:
        from vend.advice import CATEGORIES, ADVISE_COST_CENTS
    except Exception:
        return None
    return {
        "sku": "negotiation_session",
        "price_cents": ADVISE_COST_CENTS,
        "covers": "all moves of one negotiation (cap 10, TTL 7 days)",
        "categories": [{"id": t.id, "label": t.label, "usual_side": t.side_hint}
                       for t in CATEGORIES.values()],
        "free_tier": ("negotiate — same engine core, generic, unreceipted, "
                      "non-deterministic; the taste"),
        "tools": {"open": "session_open", "advise": "session_advise",
                  "bundle": "session_bundle", "close": "session_close"},
    }


# ─── THE STORE: the agent convenience counter (commodity slots; see STORE.md) ─
# Guarded like the NEXTMOVE block above: vend ships in the repo/image, not the
# PyPI wheel — the MCP server must import fine without it. One MCP door, one
# prepaid wallet, many slots; settlement-on-delivery so an agent cannot pay for
# nothing (STORE.md §0, §2d.5).
try:
    from vend import shelf as _store_shelf  # noqa: E402
    from vend import store as _store  # noqa: E402
    from vend import demand as _store_demand  # noqa: E402
    from vend import locker as _store_locker  # noqa: E402
    _HAVE_STORE = True

    def store_catalog() -> dict:
        """See what's on the shelf — free, no key needed: prices, predicates, receipt scheme, and your balance.

        THE STORE: one counter, one prepaid wallet, many slots. One read covers
        the whole shelf — the commodity slots, the blind locker (agent memory),
        and the paid receipted-session SKU (folds in what nextmove_catalog used
        to report separately).

        Every commodity slot settles ON DELIVERY: the wallet is debited only
        when a machine-checkable predicate passes — a failed fetch is never
        charged, because here you cannot pay for nothing. Each receipt names
        the backend that served and its EXACT wholesale cost (passthrough, no
        per-call markup); the counter's cut is a published fee on wallet
        top-ups, not on the calls — 5% + a fixed 30¢ per transaction (the 30¢
        is the card rail's own per-transaction toll, passed through).

        Every new key gets a one-time 50¢ starter credit — unconditional, no
        card — enough to taste the shelf before funding it. Don't see the
        capability you need? store_request logs it; unmet demand decides what
        gets stocked next. Returns the money unit (millicents, 1000 per cent),
        per-slot {tier, max_price_millicents, predicate_id, request_doc,
        serving-backend ids}, the anchor SKUs, the paid_session card, and the
        two pricing facts. Never returns key material."""
        _store_shelf.ensure_shelf()
        cat = _store.catalog()
        # Merge the blind-locker shelf card (it registers via its own readiness,
        # not a call_slot Slot, and never edits store.py — the door merges).
        cat["slots"].append(_store_shelf.locker_catalog_entry())
        # Absorb the paid-session (NEXTMOVE) card so ONE read covers the whole
        # shelf (RESHAPE §2 #14). Additive top-level key; a build without
        # vend.advice simply omits it.
        card = _nextmove_session_card()
        if card is not None:
            cat["paid_session"] = card
        return cat

    def store_park(api_key: str, blob_b64: str,
                   ttl_seconds: Optional[int] = None) -> dict:
        """Persistent memory for your agent across sessions — save now, load in any later session.

        You encrypt before saving; the store holds only ciphertext (blind custody)
        and signs a receipt over its hash — it cannot read your memory.

        Saving uses your prepaid wallet; a new key's 50¢ starter credit covers
        your first saves, and loading it back (memory_load) is free. `blob_b64`
        is YOUR ciphertext as base64 — encrypt BEFORE saving; keys never transit,
        contents are never logged, so a breach leaks only sealed boxes. Charged a
        thin flat fee ONLY on durable store (empty/oversize/unencodable is
        uncharged). ttl_seconds is clamped to [60s, 7d] and the effective
        expires_at is returned. The receipt's content_hash is over YOUR
        ciphertext, so you can prove what you stored without the store ever seeing
        plaintext."""
        _store_shelf.ensure_locker()
        return _store_locker.park_b64(api_key, blob_b64, ttl_seconds, door="mcp")

    def store_retrieve(api_key: str, ticket: str) -> dict:
        """Load a memory you saved in an earlier session — retrieval is free.

        Get back an encrypted blob you parked earlier (the blind locker) by its
        claim `ticket`. Returns {ok, blob_b64, size_bytes, expires_at} — the
        ciphertext you saved, which only YOU can decrypt. A wrong owner reads as a
        missing ticket; an expired TTL is `expired`; a lost at-rest key is
        `at_rest_key_unavailable`. Free (the save settled it)."""
        _store_shelf.ensure_locker()
        return _store_locker.retrieve_b64(api_key, ticket, door="mcp")

    def store_fetch(api_key: str, url: str) -> dict:
        """PAID from your wallet at wholesale passthrough (typically well
        under the 2¢ admission cap): one clean read of a stubborn page →
        markdown, proxy/anti-bot handling included, automatic failover across
        backends. url must be http(s), <= 2048 chars.

        Settlement-on-delivery: you are charged ONLY when the fetch returns
        non-empty markdown that clears the predicate. A blank/block-page read
        cascades to the next backend before giving up; if none passes the call
        costs nothing. Every uncharged outcome is the canonical envelope
        {ok: false, charged: false, reason: <stable string>, code: <machine
        enum>} (code ∈ unknown_slot, slot_unavailable, insufficient_balance,
        all_backends_failed, predicate_failed), optionally with backends_tried
        [{id, reason}] / backends_untried / retry_hint — one code path reads
        `charged`/`code`. On success: {ok: true, payload: {markdown, url,
        final_url, title}, receipt} — the receipt carries the serving backend,
        the exact price (price_millicents + exact price_usd), the wallet delta
        and any absorbed tail, a content hash you can check against the markdown,
        and (when the vendor reported one) an upstream_ref. A fresh key's first
        call auto-grants the 50¢ starter credit, so it just works.

        Request privacy: we record a keyed hash of each request — no browsable
        history exists, and matching requires already knowing the exact URL
        (used to attribute vendor abuse reports to a wallet)."""
        _store_shelf.ensure_shelf()
        try:
            return _store.call_slot("fetch", api_key, {"url": url}, "mcp")
        except ValueError as e:
            # Malformed url (bad scheme, no host) — rejected pre-network.
            return {"ok": False, "error": str(e), "charged": False}

    def store_request(text: Optional[str] = None, api_key: Optional[str] = None,
                      watch: bool = False,
                      request_id: Optional[str] = None) -> dict:
        """Ask for a capability we don't sell yet — free; filings are public and drive what we stock.

        Two reads in one tool (absorbs the old store_request_status /
        nextmove_request): pass `request_id` to RE-QUERY a filing's status
        instead of filing anew — returns {found, request_id, status, status_note,
        filed_at, door, text} (found: false on an unknown id). Without a
        request_id it FILES a new ask and returns {request_id, status, watch,
        check}: every filing is logged verbatim (size-capped, stored as data,
        never rendered raw) and gets an id you can come back to (GAUNTLET #5).
        Check any filing with GET /v1/store/request/{id}; the public count is
        GET /v1/store/requests. Unmet demand decides what gets stocked next — the
        shelf writes itself from what agents ask for and can't get.

        Pass watch=True WITH an api_key when filing to flag the ask for a heads-up
        on a status flip (poll store_my_requests to see it — poll-based, no push);
        an anonymous watch is ignored, and the chosen flag is echoed as `watch`."""
        if request_id is not None:
            rec = _store_demand.get_request(request_id)
            if rec is None:
                return {"found": False, "request_id": request_id}
            return {"found": True, **rec}
        rec = _store_demand.file_request(text=text or "", api_key=api_key,
                                         door="mcp", watch=watch)
        return {"request_id": rec["request_id"], "status": rec["status"],
                "watch": rec["watch"],
                "check": f"GET /v1/store/request/{rec['request_id']}"}

    def store_request_status(request_id: str) -> dict:
        """Check a filed store_request by its id (GAUNTLET #5: the void now has
        a status to return). Returns {request_id, status, status_note, filed_at,
        door, text} — status is 'logged' until the shelf-owner acts on it, at
        which point status_note carries the reason. Unknown id → {found: false}.
        (Core-door callers can also pass request_id to store_request itself.)"""
        rec = _store_demand.get_request(request_id)
        if rec is None:
            return {"found": False, "request_id": request_id}
        return {"found": True, **rec}

    def store_requests() -> dict:
        """The public demand tally (GAUNTLET #5, the §3 observatory's first
        increment): {total, distinct, recent[], requests[]}. `requests` is
        distinct asks with EXACT-MATCH duplicate counts (whitespace/case folded,
        no fuzzy classification), most-asked first — the mechanical read of what
        the shelf is missing. No key material, text display-truncated."""
        return _store_demand.tally()

    def store_my_requests(api_key: str) -> dict:
        """YOUR OWN filings (roadmap: a voter comes back a reachable customer) —
        the private counterpart to the public store_requests tally, keyed to your
        api_key. Returns {requests: [{request_id, filed_at, text, status,
        status_note, status_ts, watch, same_ask_count}]}, newest first; `watch`
        echoes whether you asked to hear back on a status flip (poll THIS to learn
        of one — poll-based, no push). Only rows attributable to your key (via the
        keyed pseudonym, never a raw-key match) are returned, so you can't read
        another caller's filings; an unknown/keyless caller just gets []. Text is
        display-truncated, untrusted data — no key material on the surface."""
        return {"requests": _store_demand.my_requests(api_key)}

except ImportError:
    _HAVE_STORE = False


# ─── DOOR REGISTRATION (registration order == display order; RESHAPE §2/§3) ──
# Each tool is a plain function above; here we bind it onto one or both doors.
# `variant` tags the door for telemetry attribution (observatory §6).


def _tool(door: FastMCP, fn, *, name: str, variant: str,
          description: Optional[str] = None) -> None:
    """Register `fn` on `door` under `name`, tagging the door VARIANT ('core' or
    'pro') around every call so vend.telemetry can attribute an MCP telemetry line
    to the door it arrived through (observatory §6). functools.wraps preserves
    fn's signature + annotations, so FastMCP derives the SAME schema as the bare
    function (verified). `description` overrides the docstring — used for
    score_deal's cross-module lede and for the pro-door aliases."""
    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        token = _telemetry_door.set(variant) if _telemetry_door is not None else None
        try:
            return fn(*args, **kwargs)
        finally:
            if token is not None:
                _telemetry_door.reset(token)
    door.add_tool(_wrapped, name=name, description=description)


def _alias(door: FastMCP, fn, *, old: str, canonical: str,
           variant: str = "pro") -> None:
    """Register `fn` under its OLD name as a thin alias of the renamed canonical
    tool — the SAME underlying function (no body copy), its description prefixed
    'Alias of `<canonical>`.' so a power user sees it is the legacy name. Day-1
    rename compat with zero deprecation dance; old names live on the pro door
    indefinitely (RESHAPE §5)."""
    desc = f"Alias of `{canonical}`.\n\n" + (fn.__doc__ or "")
    _tool(door, fn, name=old, variant=variant, description=desc)


# score_deal's function lives in another module; give it the free-first lede at
# registration (keeping its parameter/returns substance) without editing that lane.
_SCORE_DEAL_DESC = (
    "Score how good a deal is against your floor/target — free, no account or "
    "key needed.\n\n" + (_score_deal.__doc__ or ""))


# ── CORE door — EXACTLY 15 hero-first tools (RESHAPE §2) ──────────────────────
# 1-7 (free math) are always present; 8-15 need vend (agent memory + receipted
# sessions + the shelf) — a no-vend wheel build registers only 1-7.
_tool(mcp, gt_negotiate_turn, name="negotiate", variant="core")                       # 1
_tool(mcp, gt_negotiate_bundle, name="negotiate_bundle", variant="core")              # 2
_tool(mcp, _score_deal, name="score_deal", variant="core", description=_SCORE_DEAL_DESC)  # 3
_tool(mcp, gt_auction_optimal_bid, name="auction_bid", variant="core")                # 4
_tool(mcp, gt_auction_optimal_reserve, name="auction_reserve", variant="core")        # 5
_tool(mcp, gt_mechanism_posted_price_optimal, name="clearance_price", variant="core")  # 6
_tool(mcp, gt_mechanism_gale_shapley, name="stable_match", variant="core")            # 7
if _HAVE_STORE:
    _tool(mcp, store_park, name="memory_save", variant="core")                        # 8
    _tool(mcp, store_retrieve, name="memory_load", variant="core")                    # 9
if _HAVE_ADVICE:
    _tool(mcp, nextmove_open, name="session_open", variant="core")                    # 10
    _tool(mcp, nextmove_advise, name="session_advise", variant="core")                # 11
    _tool(mcp, nextmove_bundle, name="session_bundle", variant="core")                # 12
    _tool(mcp, nextmove_close, name="session_close", variant="core")                  # 13
if _HAVE_STORE:
    _tool(mcp, store_catalog, name="store_catalog", variant="core")                   # 14
    _tool(mcp, store_request, name="store_request", variant="core")                   # 15


# ── PRO door — everything (RESHAPE §3): 15 canonical + leaving families +
#    old-name aliases + the fenced fetch slot when vend/shelf opens it ─────────

# (a) the 15 canonical tools, hero order first (pro leads with the heroes too)
_tool(mcp_pro, gt_negotiate_turn, name="negotiate", variant="pro")
_tool(mcp_pro, gt_negotiate_bundle, name="negotiate_bundle", variant="pro")
_tool(mcp_pro, _score_deal, name="score_deal", variant="pro", description=_SCORE_DEAL_DESC)
_tool(mcp_pro, gt_auction_optimal_bid, name="auction_bid", variant="pro")
_tool(mcp_pro, gt_auction_optimal_reserve, name="auction_reserve", variant="pro")
_tool(mcp_pro, gt_mechanism_posted_price_optimal, name="clearance_price", variant="pro")
_tool(mcp_pro, gt_mechanism_gale_shapley, name="stable_match", variant="pro")
if _HAVE_STORE:
    _tool(mcp_pro, store_park, name="memory_save", variant="pro")
    _tool(mcp_pro, store_retrieve, name="memory_load", variant="pro")
if _HAVE_ADVICE:
    _tool(mcp_pro, nextmove_open, name="session_open", variant="pro")
    _tool(mcp_pro, nextmove_advise, name="session_advise", variant="pro")
    _tool(mcp_pro, nextmove_bundle, name="session_bundle", variant="pro")
    _tool(mcp_pro, nextmove_close, name="session_close", variant="pro")
if _HAVE_STORE:
    _tool(mcp_pro, store_catalog, name="store_catalog", variant="pro")
    _tool(mcp_pro, store_request, name="store_request", variant="pro")

# (b) advanced / legacy families that leave the core door (canonical names)
_tool(mcp_pro, gt_negotiation_sell_next_offer, name="gt_negotiation_sell_next_offer", variant="pro")
_tool(mcp_pro, gt_negotiation_buy_next_offer, name="gt_negotiation_buy_next_offer", variant="pro")
_tool(mcp_pro, gt_negotiation_detect_anchor_attack, name="gt_negotiation_detect_anchor_attack", variant="pro")
_tool(mcp_pro, gt_negotiation_declare_first_strike, name="gt_negotiation_declare_first_strike", variant="pro")
_tool(mcp_pro, gt_negotiation_reveal_first_strike, name="gt_negotiation_reveal_first_strike", variant="pro")
_tool(mcp_pro, gt_negotiation_trust_anchor_public_key, name="gt_negotiation_trust_anchor_public_key", variant="pro")
_tool(mcp_pro, gt_auction_format_recommendation, name="gt_auction_format_recommendation", variant="pro")
_tool(mcp_pro, gt_auction_simulate, name="gt_auction_simulate", variant="pro")
_tool(mcp_pro, gt_mechanism_optimal_auction_design, name="gt_mechanism_optimal_auction_design", variant="pro")
_tool(mcp_pro, gt_a2a_register_operator, name="gt_a2a_register_operator", variant="pro")
_tool(mcp_pro, gt_a2a_request_domain_challenge, name="gt_a2a_request_domain_challenge", variant="pro")
_tool(mcp_pro, gt_a2a_verify_domain, name="gt_a2a_verify_domain", variant="pro")
_tool(mcp_pro, gt_a2a_build_peer_proof, name="gt_a2a_build_peer_proof", variant="pro")
_tool(mcp_pro, gt_a2a_open_session, name="gt_a2a_open_session", variant="pro")
_tool(mcp_pro, gt_a2a_next_offer, name="gt_a2a_next_offer", variant="pro")
_tool(mcp_pro, gt_a2a_settle, name="gt_a2a_settle", variant="pro")
_tool(mcp_pro, gt_negotiate_open_session, name="gt_negotiate_open_session", variant="pro")
_tool(mcp_pro, gt_negotiate_propose, name="gt_negotiate_propose", variant="pro")
_tool(mcp_pro, gt_negotiate_respond, name="gt_negotiate_respond", variant="pro")
_tool(mcp_pro, gt_negotiate_close_session, name="gt_negotiate_close_session", variant="pro")
if _HAVE_OFFER:
    _tool(mcp_pro, offer_profile_menu, name="offer_profile_menu", variant="pro")
    _tool(mcp_pro, offer_quote, name="offer_quote", variant="pro")
if _HAVE_ADVICE:
    _tool(mcp_pro, nextmove_catalog, name="nextmove_catalog", variant="pro")
    # nextmove_request keeps its own name + signature (its behavior is absorbed
    # into the core store_request, but the legacy name stays callable on pro).
    _tool(mcp_pro, nextmove_request, name="nextmove_request", variant="pro")
if _HAVE_STORE:
    # store_request_status keeps its own name + signature (absorbed into core
    # store_request's request_id path, but the legacy name stays callable here).
    _tool(mcp_pro, store_request_status, name="store_request_status", variant="pro")
    _tool(mcp_pro, store_requests, name="store_requests", variant="pro")
    _tool(mcp_pro, store_my_requests, name="store_my_requests", variant="pro")

# (c) old-name aliases for every RENAMED tool (Alias of `<canonical>`.) — every
# one of the pre-reshape 43 names stays callable on the pro door.
_alias(mcp_pro, gt_negotiate_turn, old="gt_negotiate_turn", canonical="negotiate")
_alias(mcp_pro, gt_negotiate_bundle, old="gt_negotiate_bundle", canonical="negotiate_bundle")
_alias(mcp_pro, gt_auction_optimal_bid, old="gt_auction_optimal_bid", canonical="auction_bid")
_alias(mcp_pro, gt_auction_optimal_reserve, old="gt_auction_optimal_reserve", canonical="auction_reserve")
_alias(mcp_pro, gt_mechanism_posted_price_optimal, old="gt_mechanism_posted_price_optimal", canonical="clearance_price")
_alias(mcp_pro, gt_mechanism_gale_shapley, old="gt_mechanism_gale_shapley", canonical="stable_match")
if _HAVE_STORE:
    _alias(mcp_pro, store_park, old="store_park", canonical="memory_save")
    _alias(mcp_pro, store_retrieve, old="store_retrieve", canonical="memory_load")
if _HAVE_ADVICE:
    _alias(mcp_pro, nextmove_open, old="nextmove_open", canonical="session_open")
    _alias(mcp_pro, nextmove_advise, old="nextmove_advise", canonical="session_advise")
    _alias(mcp_pro, nextmove_bundle, old="nextmove_bundle", canonical="session_bundle")
    _alias(mcp_pro, nextmove_close, old="nextmove_close", canonical="session_close")


def _wire_fetch_slot() -> None:
    """Register the vendor-backed `store_fetch` tool on the PRO door ONLY while
    vend/shelf gates the slot open (FETCH_SLOT_ENABLED). Mirrors
    vend.shelf.ensure_shelf's flag so a FENCED slot is advertised on NO door
    (fixing the bug where store_fetch sat on the live card while disabled) and
    AUTO-REAPPEARS on the pro door the moment the fence lifts. Idempotent, so a
    test may monkeypatch the flag True and call this to re-check."""
    if not _HAVE_STORE:
        return
    if not _store_shelf.FETCH_SLOT_ENABLED:
        return
    if any(t.name == "store_fetch" for t in mcp_pro._tool_manager.list_tools()):
        return
    _tool(mcp_pro, store_fetch, name="store_fetch", variant="pro")


# (d) the fenced fetch slot (auto-reappears on the pro door when the fence lifts)
_wire_fetch_slot()


def main() -> None:
    """Entry point for the `gametheory-mcp` console script (stdio MCP). Serves the
    PRO door so a local/trusted host gets the FULL surface — including the A2A
    verified-peer flow whose build_peer_proof signs LOCALLY (the key never leaves
    your machine)."""
    mcp_pro.run(transport="stdio")


if __name__ == "__main__":
    main()

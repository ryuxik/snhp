"""
FastAPI binding for the game-theory toolkit. Exposes Tier 1 (negotiation)
and Tier 2 (auctions) endpoints under /v1/, with auto-generated OpenAPI
spec and a discovery catalog.

Math-only endpoints are FREE; LLM-cost endpoints are tagged paid (none in
Sprint 1).

Run locally:
    uvicorn gametheory.server.http:app --reload --port 8000

OpenAPI spec served at /openapi.json; Swagger UI at /docs.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from gametheory.negotiation.sell import sell_next_offer as _sell_next_offer
from gametheory.negotiation.buy import (
    buy_next_offer as _buy_next_offer,
    detect_anchor_attack as _detect_anchor_attack,
)
from gametheory.auctions.bidder import optimal_bid as _bidder_optimal_bid
from gametheory.auctions.seller import (
    optimal_reserve as _seller_optimal_reserve,
    format_recommendation as _seller_format_rec,
    simulate as _auction_simulate,
)
from gametheory.crypto.first_strike import (
    declare_first_strike as _declare_first_strike,
    reveal_first_strike as _reveal_first_strike,
    trust_anchor_public_key_pem as _trust_anchor_pem,
    trust_anchor_source as _trust_anchor_source,
    CommitmentNotFound, CommitmentExpired, CommitmentRevealMismatch,
)
from gametheory.mechanism.gale_shapley import gale_shapley as _gale_shapley
from gametheory.mechanism.optimal_auction import (
    optimal_auction_design as _optimal_auction_design,
)
from gametheory.mechanism.posted_price import (
    posted_price_optimal as _posted_price_optimal,
)
from gametheory.server.onboarding import (
    issue_key as _issue_key,
    lookup_key as _lookup_key,
    deduct_balance as _deduct_balance,
)
from gametheory.server import billing as _billing
from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)
from llm_extractor import _call_llm  # noqa: E402


_COST_FREE = "0"

# Per-call cost for draft_message in cents (whole cents — billing uses int).
# Header cost stays in USD ("0.0050") for backwards compatibility.
_DRAFT_MESSAGE_COST_CENTS = _billing.DRAFT_MESSAGE_COST_CENTS
_DRAFT_MESSAGE_COST_USD = f"{_DRAFT_MESSAGE_COST_CENTS / 100:.4f}"


def _extract_api_key(authorization: Optional[str]) -> str:
    """Pull the bearer token out of the Authorization header. Raises 401
    if the header is missing or malformed."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer gt_* required",
        )
    return authorization.split(" ", 1)[1].strip()


def _charge_or_402(api_key: str, cost_cents: int) -> None:
    """Look up the key, deduct cost_cents from its balance. Raises 402
    on unknown key or insufficient balance, with a message pointing the
    caller at the credit-purchase flow.
    """
    key_info = _lookup_key(api_key)
    if key_info is None:
        raise HTTPException(status_code=402, detail="Unknown api_key")
    if not _deduct_balance(api_key=api_key, cents=cost_cents):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Insufficient credits ({key_info['balance_usd_cents']} cents "
                f"available, {cost_cents} required). Top up at "
                f"POST /v1/billing/checkout_session with a credit pack."
            ),
        )


def _math_endpoint(handler: Callable[..., dict]) -> Callable:
    """
    Decorator factory for the math-only endpoints. Wraps a pure-math handler
    with timing, free-tier cost header, and ValueError → HTTP 400 conversion.

    FastAPI inspects the wrapper's signature to discover Pydantic body params
    and injected dependencies (notably `Response`). We copy the handler's
    type annotations onto the wrapper so FastAPI sees `req: <PydanticModel>`
    instead of treating `req` as an unannotated query parameter. We can't use
    `functools.wraps` because it would also hide the `response` parameter.
    """

    def wrapper(req, response: Response):  # type: ignore[no-untyped-def]
        t0 = time.time()
        try:
            result = handler(req)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        response.headers["X-GT-Cost-USD"] = _COST_FREE
        response.headers["X-GT-Latency-Ms"] = f"{(time.time() - t0) * 1000:.1f}"
        return result

    wrapper.__name__ = handler.__name__
    wrapper.__doc__ = handler.__doc__
    # Copy req's type annotation so FastAPI recognizes it as a body param.
    handler_annotations = getattr(handler, "__annotations__", {}) or {}
    if "req" in handler_annotations:
        wrapper.__annotations__["req"] = handler_annotations["req"]
    wrapper.__annotations__["response"] = Response
    return wrapper


# ─── Models ──────────────────────────────────────────────────────────────────


class WTPPrior(BaseModel):
    mu: float = Field(description="Lognormal μ of buyer WTP")
    sigma: float = Field(description="Lognormal σ of buyer WTP")


class SellNextOfferRequest(BaseModel):
    my_reservation: float = Field(ge=0.0, le=1.0,
        description="Our walk-away utility, normalized to [0, 1]")
    opponent_offer_history: list[float] = Field(default_factory=list,
        description="Opponent's offers evaluated in our utility space, in [0, 1]")
    my_offer_history: list[float] = Field(default_factory=list)
    deadline_rounds: int = Field(ge=1, le=64,
        description="Total rounds before the negotiation times out")
    pareto_knob: float = Field(default=0.5, ge=0.0, le=1.0,
        description="0=max deal rate, 1=max H2H margin (empirical Pareto frontier)")
    buyer_wtp_prior: Optional[WTPPrior] = None


class SellNextOfferResponse(BaseModel):
    recommended_offer: float
    acceptance_probability: float
    expected_payoff: float
    rationale: str
    posterior: dict
    rubinstein_share: float
    schelling_floor: float


class PriorParams(BaseModel):
    family: str = Field(description="lognorm | uniform")
    params: dict


class OptimalBidRequest(BaseModel):
    auction_format: str = Field(
        description="first_price | second_price_vickrey | english_ascending")
    my_valuation: float = Field(gt=0.0)
    n_competing_bidders: int = Field(ge=1, le=100)
    competitor_value_prior: PriorParams
    reserve_price: Optional[float] = None
    risk_aversion: float = Field(default=1.0, ge=0.1, le=1.0)


class OptimalBidResponse(BaseModel):
    optimal_bid: float
    expected_surplus: Optional[float]
    win_probability: Optional[float]
    dominant_strategy: bool
    rationale: str


class OptimalReserveRequest(BaseModel):
    bidder_value_prior: PriorParams
    n_bidders: int = Field(ge=1, le=100)
    seller_valuation: float = Field(ge=0.0)


class OptimalReserveResponse(BaseModel):
    reserve_price: float
    expected_revenue: float
    expected_revenue_no_reserve: float
    expected_efficiency_loss: float
    rationale: str


class FormatRecRequest(BaseModel):
    bidder_value_prior: PriorParams
    n_bidders: int = Field(ge=1, le=100)
    seller_valuation: float = Field(ge=0.0)
    weights: Optional[dict] = None


class FormatRecResponse(BaseModel):
    recommended_format: str
    scores: dict
    expected_revenue_by_format: dict
    rationale: str


class SimulateRequest(BaseModel):
    auction_format: str
    bidder_priors: list[PriorParams]
    reserve_price: float = Field(ge=0.0)
    n_simulations: int = Field(default=10_000, ge=100, le=100_000)
    seed: Optional[int] = None


class SimulateResponse(BaseModel):
    mean_revenue: float
    ci_95: list[float]
    efficiency: float
    winner_index_distribution: list[float]
    n_simulations: int


class MarketPrior(BaseModel):
    mu: float = Field(description="Mean utility-to-buyer of typical seller openings, in [0, 1]")
    sigma: float = Field(gt=0.0, description="Std of typical seller openings")


class BuyNextOfferRequest(BaseModel):
    my_reservation: float = Field(ge=0.0, le=1.0)
    seller_offer_history: list[float] = Field(default_factory=list,
        description="Seller's offers evaluated in our (buyer's) utility space, in [0, 1]")
    my_offer_history: list[float] = Field(default_factory=list)
    deadline_rounds: int = Field(ge=1, le=64)
    pareto_knob: float = Field(default=0.5, ge=0.0, le=1.0,
        description="Buyer-side Pareto knob (0=max deal rate, 1=max margin)")
    defenses: Optional[list[str]] = Field(default=None,
        description="Defense bundle; default ['schelling_commitment', 'anchor_attack_detection']")
    market_prior: Optional[MarketPrior] = Field(default=None,
        description="Required when anchor_attack_detection is in defenses")


class BuyNextOfferResponse(BaseModel):
    recommended_offer: float
    acceptance_probability: float
    expected_payoff: float
    warnings: list[dict]
    defense_actions: list[dict]
    rationale: str
    posterior: dict
    rubinstein_share: float
    schelling_floor: float


class DetectAnchorAttackRequest(BaseModel):
    opponent_offer_history: list[float] = Field(min_length=0)
    market_prior: MarketPrior


class DetectAnchorAttackResponse(BaseModel):
    is_anchor_attack: bool
    z_score: float
    severity: float
    recommended_response: str
    rationale: str


class DeclareFirstStrikeRequest(BaseModel):
    buyer_id: str = Field(min_length=1, max_length=128)
    seller_id: str = Field(min_length=1, max_length=128)
    reservation_hash: str = Field(min_length=16, max_length=64,
        description="SHA-256 base64url of (reservation || nonce || salt || ids)")
    deadline_iso: str = Field(description="ISO 8601 deadline, e.g. 2026-04-29T14:00:00Z")
    binding_ttl_seconds: int = Field(ge=60, le=86400)


class DeclareFirstStrikeResponse(BaseModel):
    commitment_id: str
    attestation_jwt: str
    expires_at_unix: int
    expires_at_iso: str
    trust_anchor_public_key_pem: str


class RevealFirstStrikeRequest(BaseModel):
    commitment_id: str
    reservation: float
    nonce: str = Field(min_length=1)
    salt: str = Field(min_length=1)


class RevealFirstStrikeResponse(BaseModel):
    verified: bool
    binding_offer: float
    buyer_id: str
    seller_id: str
    revealed_at_unix: int
    reused: bool


class DraftMessageRequest(BaseModel):
    numbers: dict = Field(description="Output of next_offer (price, etc.)")
    client_email: str = Field(description="The opposing client's email text")
    constraints_text: str = Field(description="Free-form constraint summary")
    tone: str = Field(default="professional", description="professional | friendly | firm")
    my_reservation: float = Field(ge=0.0, le=1.0,
        description="Refuses to draft persuasive text below your BATNA")


class DraftMessageResponse(BaseModel):
    text: str
    cost_usd: str
    model: str


# Billing / credit-pack purchase
class CheckoutSessionRequest(BaseModel):
    api_key: str = Field(description="Existing key to credit on success (gt_*)")
    pack: Literal["small", "medium", "large"] = Field(
        description="Credit pack: small=$10, medium=$50, large=$200")
    success_url: str = Field(description="URL Stripe redirects to after payment")
    cancel_url: str = Field(description="URL Stripe redirects to on cancel")


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str
    pack: str
    price_cents: int
    credits_cents: int


class BalanceResponse(BaseModel):
    api_key: str
    balance_usd_cents: int


# ─── Tier 3: Mechanism Design ───────────────────────────────────────────────


class Proposer(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    preferences: list[str] = Field(default_factory=list,
        description="Receiver ids ranked most-preferred first")


class Receiver(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    preferences: list[str] = Field(default_factory=list,
        description="Proposer ids ranked most-preferred first")
    capacity: int = Field(default=1, ge=1, le=1024)


class GaleShapleyRequest(BaseModel):
    proposers: list[Proposer] = Field(min_length=1)
    receivers: list[Receiver] = Field(min_length=1)


class GaleShapleyResponse(BaseModel):
    matching: dict
    unmatched_proposers: list[str]
    blocking_pairs: list[list[str]]
    n_proposals: int


class OptimalAuctionDesignRequest(BaseModel):
    bidder_priors: list[PriorParams] = Field(min_length=1, max_length=50)
    seller_valuation: float = Field(ge=0.0)
    objective: Literal["revenue", "welfare"] = "revenue"
    n_simulations: int = Field(default=5_000, ge=500, le=50_000)
    seed: int = Field(default=42)


class OptimalAuctionDesignResponse(BaseModel):
    mechanism: str
    reserve_prices: dict
    expected_revenue: float
    expected_welfare: float
    ironing_required: bool
    rationale: str


class PostedPriceRequest(BaseModel):
    buyer_arrival_prior: PriorParams
    arrival_rate_per_second: float = Field(gt=0.0, le=1000.0)
    inventory: int = Field(ge=1, le=100_000)
    horizon_seconds: float = Field(gt=0.0, le=30 * 86400)
    n_simulations: int = Field(default=2_000, ge=100, le=20_000)
    seed: int = Field(default=42)


class PostedPriceResponse(BaseModel):
    static_price: float
    static_expected_revenue: float
    static_simulated_revenue: float
    dynamic_schedule: list[dict]
    dynamic_value_estimate: float
    sellthrough_rate: float
    rationale: str


# ─── App ─────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="Game Theory Layer for AI Agents",
    description=(
        "Equilibrium-aware primitives for AI agents. Tier 1: negotiation "
        "(sell-side + buy-side, with cryptographic first-strike). Tier 2: "
        "auctions (Myerson, Vickrey, English). Tier 3: mechanism design "
        "(Gale-Shapley, optimal auction, posted-price). Math endpoints are "
        "free; LLM endpoints require a metered key.\n\n"
        "Empirical: SNHP rank #1/21 in NegMAS round-robin tournament; "
        "p<0.014 vs Aspiration / Split-the-Diff / Fair Demand.\n\n"
        "Discovery: GET /v1/catalog for tool list, /llms.txt for LLM-readable "
        "agent guide."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "negotiation", "description": "Tier 1: multi-round bargaining"},
        {"name": "auctions",    "description": "Tier 2: single-unit auctions"},
        {"name": "mechanism",   "description": "Tier 3: marketplace operator primitives"},
        {"name": "discovery",   "description": "Catalog + agent onboarding"},
    ],
)


# ─── Tier 1: Negotiation ─────────────────────────────────────────────────────


@app.post(
    "/v1/negotiation/sell/next_offer",
    tags=["negotiation"],
    response_model=SellNextOfferResponse,
    summary="Sell-side next-offer recommendation",
    description=(
        "Recommends the next utility level to offer given the current state. "
        "The `pareto_knob` interpolates between empirically-mapped extremes: "
        "0=max deal rate, 1=max head-to-head margin. Free endpoint (math only)."
    ),
    responses={
        200: {"description": "Recommendation produced",
              "headers": {"X-GT-Cost-USD": {"schema": {"type": "string"},
                                             "description": "Cost of this call (always 0 for free tier)"},
                          "X-GT-Latency-Ms": {"schema": {"type": "string"}}}},
        400: {"description": "Invalid input"},
    },
)
@_math_endpoint
def negotiation_sell_next_offer(req: SellNextOfferRequest):
    prior_dict = req.buyer_wtp_prior.model_dump() if req.buyer_wtp_prior else None
    return _sell_next_offer(
        my_reservation=req.my_reservation,
        opponent_offer_history=req.opponent_offer_history,
        my_offer_history=req.my_offer_history,
        deadline_rounds=req.deadline_rounds,
        pareto_knob=req.pareto_knob,
        buyer_wtp_prior=prior_dict,
    )


# ─── Tier 2: Auctions ────────────────────────────────────────────────────────


@app.post(
    "/v1/auction/bidder/optimal_bid",
    tags=["auctions"],
    response_model=OptimalBidResponse,
    summary="Optimal bid for first-price/Vickrey/English auction",
)
@_math_endpoint
def auction_bidder_optimal_bid(req: OptimalBidRequest):
    return _bidder_optimal_bid(
        auction_format=req.auction_format,
        my_valuation=req.my_valuation,
        n_competing_bidders=req.n_competing_bidders,
        competitor_value_prior=req.competitor_value_prior.model_dump(),
        reserve_price=req.reserve_price,
        risk_aversion=req.risk_aversion,
    )


@app.post(
    "/v1/auction/seller/optimal_reserve",
    tags=["auctions"],
    response_model=OptimalReserveResponse,
    summary="Myerson optimal reserve price",
)
@_math_endpoint
def auction_seller_optimal_reserve(req: OptimalReserveRequest):
    return _seller_optimal_reserve(
        bidder_value_prior=req.bidder_value_prior.model_dump(),
        n_bidders=req.n_bidders,
        seller_valuation=req.seller_valuation,
    )


@app.post(
    "/v1/auction/seller/format_recommendation",
    tags=["auctions"],
    response_model=FormatRecResponse,
    summary="Recommend an auction format given seller weights",
)
@_math_endpoint
def auction_seller_format_recommendation(req: FormatRecRequest):
    return _seller_format_rec(
        bidder_value_prior=req.bidder_value_prior.model_dump(),
        n_bidders=req.n_bidders,
        seller_valuation=req.seller_valuation,
        weights=req.weights,
    )


@app.post(
    "/v1/auction/simulate",
    tags=["auctions"],
    response_model=SimulateResponse,
    summary="Monte Carlo auction simulation",
)
@_math_endpoint
def auction_simulate(req: SimulateRequest):
    return _auction_simulate(
        auction_format=req.auction_format,
        bidder_priors=[p.model_dump() for p in req.bidder_priors],
        reserve_price=req.reserve_price,
        n_simulations=req.n_simulations,
        seed=req.seed,
    )


# ─── Discovery ───────────────────────────────────────────────────────────────


@app.get(
    "/v1/catalog",
    tags=["discovery"],
    summary="Tool catalog for agent discovery",
    description=(
        "Machine-readable list of all tools with cost class and stability. "
        "Cacheable, no auth required. Agents read this first."
    ),
)
def catalog():
    return {
        "version": "0.1.0",
        "openapi_url": "/openapi.json",
        "docs_url": "/docs",
        "llms_txt_url": "/llms.txt",
        "tools": [
            {
                "name": "gt.negotiation.sell.next_offer",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/sell/next_offer",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Sell-side next-offer recommendation with Pareto knob. "
                    "Wraps SNHP math; rank #1/21 in independent eval."
                ),
            },
            {
                "name": "gt.auction.bidder.optimal_bid",
                "tier": 2,
                "endpoint": "POST /v1/auction/bidder/optimal_bid",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Optimal bid for first-price BNE / Vickrey (truthful) / "
                    "English ascending. Reuses Myerson math from snhp/core_math."
                ),
            },
            {
                "name": "gt.auction.seller.optimal_reserve",
                "tier": 2,
                "endpoint": "POST /v1/auction/seller/optimal_reserve",
                "cost_class": "free",
                "stability": "beta",
                "description": "Myerson optimal reserve via virtual-value-zero solve.",
            },
            {
                "name": "gt.auction.seller.format_recommendation",
                "tier": 2,
                "endpoint": "POST /v1/auction/seller/format_recommendation",
                "cost_class": "free",
                "stability": "beta",
                "description": "Recommend auction format given revenue/speed/transparency weights.",
            },
            {
                "name": "gt.auction.simulate",
                "tier": 2,
                "endpoint": "POST /v1/auction/simulate",
                "cost_class": "free",
                "stability": "beta",
                "description": "Monte Carlo auction revenue/efficiency simulation.",
            },
            {
                "name": "gt.negotiation.buy.next_offer",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/buy/next_offer",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Buy-side recommender with defense bundle (anchor-attack "
                    "detection, Schelling commitment). Pareto knob for buyers."
                ),
            },
            {
                "name": "gt.negotiation.detect_anchor_attack",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/detect_anchor_attack",
                "cost_class": "free",
                "stability": "beta",
                "description": "Z-score the seller's opening against a market prior.",
            },
            {
                "name": "gt.negotiation.declare_first_strike",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/declare_first_strike",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Cryptographic commit to a buyer reservation; returns "
                    "EdDSA-signed attestation. The mechanism-design solution "
                    "to the structural buy-side disadvantage."
                ),
            },
            {
                "name": "gt.negotiation.reveal_first_strike",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/reveal_first_strike",
                "cost_class": "free",
                "stability": "beta",
                "description": "Reveal a previous first-strike commitment to obtain the binding offer.",
            },
            {
                "name": "gt.negotiation.draft_message",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/draft_message",
                "cost_class": "paid",
                "stability": "beta",
                "description": (
                    "LLM-cost endpoint. Drafts a 3-sentence reply email. "
                    "Requires metered key; refuses BATNA-violating drafts."
                ),
            },
            {
                "name": "gt.mechanism.gale_shapley",
                "tier": 3,
                "endpoint": "POST /v1/mechanism/gale_shapley",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Stable matching via deferred acceptance, with capacities "
                    "(school-choice variant) and a blocking-pair sanity check."
                ),
            },
            {
                "name": "gt.mechanism.optimal_auction_design",
                "tier": 3,
                "endpoint": "POST /v1/mechanism/optimal_auction_design",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Myerson revenue-optimal mechanism for asymmetric IPV. "
                    "Returns per-bidder reserves; collapses to second-price-"
                    "with-reserve under symmetric priors."
                ),
            },
            {
                "name": "gt.mechanism.posted_price_optimal",
                "tier": 3,
                "endpoint": "POST /v1/mechanism/posted_price_optimal",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "Gallego-van Ryzin posted-price (static p* + dynamic "
                    "schedule from backward DP)."
                ),
            },
        ],
        "coming_later": [
            "gt.negotiation.propose_unbundling",
            "gt.negotiation.coalition_form",
            "gt.mechanism.vcg_payments",
            "gt.coalition.* (Tier 4)",
        ],
    }


_LLMS_TXT = """\
# Game Theory Layer for AI Agents

This API exposes equilibrium-aware primitives so AI agents can compose
game-theoretic strategies without re-deriving the math. LLMs are
structurally bad at multi-round, opponent-modeling problems; we are not.

## Tier 1 — Negotiation
- POST /v1/negotiation/sell/next_offer  [free]
  Sell-side recommender. `pareto_knob` ∈ [0, 1] interpolates between
  deal-rate-max (0) and H2H-margin-max (1). Empirical anchor: SNHP
  rank #1/21 in our NegMAS round-robin tournament; beats Aspiration
  (p=0.011), Split-the-Diff (p=0.014), Fair Demand (p<0.001).
- POST /v1/negotiation/buy/next_offer  [free]
  Buy-side recommender with a defense bundle (Schelling commitment,
  anchor-attack detection). Pass `market_prior` to enable anchor
  detection.
- POST /v1/negotiation/detect_anchor_attack  [free]
  Z-score the seller's opening against a market prior; recommends
  ignore / counter_with_market / walk_away.
- POST /v1/negotiation/declare_first_strike  [free]
  Cryptographic commit to a buyer reservation. Returns an EdDSA-signed
  attestation JWT the buyer shows the seller. Mechanism-design fix for
  the structural buy-side disadvantage (going second in SAO).
- POST /v1/negotiation/reveal_first_strike  [free]
  Reveal the inputs to a previous commitment to obtain the binding offer.
- GET  /v1/keys/trust_anchor  [free]
  Public key for verifying first-strike attestations.
- POST /v1/negotiation/draft_message  [PAID — metered key required]
  LLM-drafted 3-sentence reply email. Refuses BATNA-violating drafts.

## Tier 2 — Auctions
- POST /v1/auction/bidder/optimal_bid  [free]
  Optimal bid for first-price (BNE), Vickrey (truthful), English ascending.
- POST /v1/auction/seller/optimal_reserve  [free]
  Myerson reserve from virtual-value-zero.
- POST /v1/auction/seller/format_recommendation  [free]
  Picks a format given weights {revenue, speed, transparency}.
- POST /v1/auction/simulate  [free]
  Monte Carlo revenue + efficiency, any of the three formats.

## Tier 3 — Mechanism Design (marketplace operators)
- POST /v1/mechanism/gale_shapley  [free]
  Stable matching via deferred acceptance, with capacities and a
  blocking-pair sanity check.
- POST /v1/mechanism/optimal_auction_design  [free]
  Myerson revenue-optimal mechanism for asymmetric IPV. Per-bidder
  reserves; collapses to second-price-with-reserve under symmetric IPV.
- POST /v1/mechanism/posted_price_optimal  [free]
  Gallego-van Ryzin posted price (static p* + dynamic schedule).

## Cost model
- Math endpoints are FREE: NumPy / SciPy, ~50ms p99.
- LLM endpoints (currently just draft_message) cost 1 credit cent / call.
  Top up credits via Stripe Checkout (see Onboarding below).
  Rate limit: 600/min for all keys.

## Onboarding (no human in the loop)
- POST /v1/keys
    body: {agent_id, contact_email, intended_use_summary}
    -> {api_key: "gt_*", balance_usd_cents: 0, ...}
- POST /v1/billing/checkout_session
    body: {api_key, pack: "small"|"medium"|"large", success_url, cancel_url}
    -> {checkout_url, session_id, ...}
  Owner clicks the URL, pays via Stripe, balance auto-credits via webhook.
  Packs: small=$10 (1k cents), medium=$50 (5k cents), large=$200 (20k cents).
- GET /v1/billing/balance
    Authorization: Bearer gt_*
    -> {balance_usd_cents}

## Composition examples
1. Buy-side defense → auction:
   detect_anchor_attack → declare_first_strike → seller proposes auction →
   auction.bidder.optimal_bid (Vickrey: bid truthfully).
2. Marketplace operator: mechanism.optimal_auction_design (operator)
   + auction.bidder.optimal_bid (each bidder), same Myerson math, two
   perspectives.

## Honest limitations
- Buy-side: structurally disadvantaged in alternating-offers SAO; best
  achievable margin -0.025 even at the Pareto frontier. Use
  declare_first_strike to recover symmetry.
- Combinatorial / multi-unit auctions, VCG payments: out of scope for v1.
- Auto-execution: never. We return recommendations; your environment
  delivers offers / places bids. No escrow, no settlement.

## Discovery
- GET /v1/catalog — JSON list of all tools, cost class, stability
- GET /openapi.json — OpenAPI 3.1 spec
- GET /docs — Swagger UI (for human inspection)
- GET /llms.txt — this file
"""


@app.get("/llms.txt", tags=["discovery"], response_class=PlainTextResponse,
          summary="Agent-readable guide to the toolkit")
def llms_txt() -> str:
    return _LLMS_TXT


# ─── Onboarding ──────────────────────────────────────────────────────────────


class IssueKeyRequest(BaseModel):
    agent_id: str = Field(min_length=3, max_length=128,
        description="Stable identifier for the calling agent")
    contact_email: str = Field(description="Contact email for issues / overage notifications")
    intended_use_summary: str = Field(min_length=8, max_length=1024,
        description="One-sentence description of the intended use case")


class IssueKeyResponse(BaseModel):
    api_key: str
    tier: str
    rate_limit_per_minute: int
    created_at: int
    balance_usd_cents: int = Field(description="Remaining credit balance in cents")
    reused: bool = Field(description="True if an existing key for this agent_id was returned")


@app.post(
    "/v1/keys",
    tags=["discovery"],
    response_model=IssueKeyResponse,
    summary="Programmatic API key issuance (free tier, no human approval)",
    description=(
        "Self-serve key issuance for AI agents. No human approval gate. "
        "Idempotent on agent_id within 24h. Free tier only in Sprint 1; "
        "Top up credits via POST /v1/billing/checkout_session for "
        "paid endpoints."
    ),
)
def issue_key(req: IssueKeyRequest):
    try:
        return _issue_key(
            agent_id=req.agent_id,
            contact_email=req.contact_email,
            intended_use_summary=req.intended_use_summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Buy-side negotiation ───────────────────────────────────────────────────


@app.post(
    "/v1/negotiation/buy/next_offer",
    tags=["negotiation"],
    response_model=BuyNextOfferResponse,
    summary="Buy-side next-offer recommendation with defense bundle",
)
@_math_endpoint
def negotiation_buy_next_offer(req: BuyNextOfferRequest):
    return _buy_next_offer(
        my_reservation=req.my_reservation,
        seller_offer_history=req.seller_offer_history,
        my_offer_history=req.my_offer_history,
        deadline_rounds=req.deadline_rounds,
        pareto_knob=req.pareto_knob,
        defenses=req.defenses,
        market_prior=req.market_prior.model_dump() if req.market_prior else None,
    )


@app.post(
    "/v1/negotiation/detect_anchor_attack",
    tags=["negotiation"],
    response_model=DetectAnchorAttackResponse,
    summary="Z-score anchor-attack detection",
)
@_math_endpoint
def negotiation_detect_anchor_attack(req: DetectAnchorAttackRequest):
    return _detect_anchor_attack(
        opponent_offer_history=req.opponent_offer_history,
        market_prior=req.market_prior.model_dump(),
    )


# ─── First-strike commit-reveal ─────────────────────────────────────────────


@app.post(
    "/v1/negotiation/declare_first_strike",
    tags=["negotiation"],
    response_model=DeclareFirstStrikeResponse,
    summary="Cryptographic commit to a buyer reservation (signed attestation)",
    description=(
        "The buyer-side answer to the structural disadvantage of going second. "
        "Buyer commits to a reservation hash; server returns an EdDSA-signed "
        "attestation JWT that the buyer can show to the seller. Seller can "
        "verify via /v1/keys/trust_anchor. Buyer reveals at acceptance."
    ),
)
@_math_endpoint
def negotiation_declare_first_strike(req: DeclareFirstStrikeRequest):
    return _declare_first_strike(
        buyer_id=req.buyer_id,
        seller_id=req.seller_id,
        reservation_hash=req.reservation_hash,
        deadline_iso=req.deadline_iso,
        binding_ttl_seconds=req.binding_ttl_seconds,
    )


@app.post(
    "/v1/negotiation/reveal_first_strike",
    tags=["negotiation"],
    response_model=RevealFirstStrikeResponse,
    summary="Reveal a first-strike commitment to obtain the binding offer",
)
def negotiation_reveal_first_strike(req: RevealFirstStrikeRequest, response: Response):
    t0 = time.time()
    try:
        result = _reveal_first_strike(
            commitment_id=req.commitment_id,
            reservation=req.reservation,
            nonce=req.nonce,
            salt=req.salt,
        )
    except CommitmentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CommitmentExpired as e:
        raise HTTPException(status_code=410, detail=str(e))
    except CommitmentRevealMismatch as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.headers["X-GT-Cost-USD"] = _COST_FREE
    response.headers["X-GT-Latency-Ms"] = f"{(time.time() - t0) * 1000:.1f}"
    return result


@app.get(
    "/v1/keys/trust_anchor",
    tags=["discovery"],
    response_class=PlainTextResponse,
    summary="Public key for verifying first-strike attestations",
)
def keys_trust_anchor():
    return _trust_anchor_pem()


# ─── Billing (Stripe Checkout credit packs) ─────────────────────────────────


@app.post(
    "/v1/billing/checkout_session",
    tags=["discovery"],
    response_model=CheckoutSessionResponse,
    summary="Create a Stripe Checkout session for a credit pack",
    description=(
        "Returns a hosted Stripe Checkout URL. The human owner of the agent "
        "clicks through to pay; on success Stripe calls our webhook and we "
        "credit the api_key's balance. Test mode uses Stripe test cards "
        "(4242 4242 4242 4242); production needs live keys."
    ),
)
def billing_checkout_session(req: CheckoutSessionRequest):
    try:
        return _billing.create_checkout_session(
            api_key=req.api_key, pack=req.pack,
            success_url=req.success_url, cancel_url=req.cancel_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # STRIPE_SECRET_KEY not set on the server.
        raise HTTPException(status_code=503, detail=str(e))


@app.post(
    "/v1/billing/webhook",
    tags=["discovery"],
    summary="Stripe webhook receiver (checkout.session.completed)",
    description=(
        "Stripe calls this with `checkout.session.completed` events. "
        "Signature is verified against STRIPE_WEBHOOK_SECRET; duplicates "
        "are deduped by event.id. On success the api_key's balance is "
        "credited by the pack's credits_cents. Don't call this endpoint "
        "yourself — it's a Stripe-only callback."
    ),
)
async def billing_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        return _billing.handle_webhook(payload=payload, signature=signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(
    "/v1/billing/balance",
    tags=["discovery"],
    response_model=BalanceResponse,
    summary="Read the current credit balance for an api_key",
)
def billing_balance(authorization: Optional[str] = Header(None)):
    api_key = _extract_api_key(authorization)
    info = _lookup_key(api_key)
    if info is None:
        raise HTTPException(status_code=401, detail="Unknown api_key")
    return {"api_key": api_key, "balance_usd_cents": info["balance_usd_cents"]}


# ─── Paid endpoint (draft_message) ──────────────────────────────────────────


@app.post(
    "/v1/negotiation/draft_message",
    tags=["negotiation"],
    response_model=DraftMessageResponse,
    summary="Draft a natural-language reply email (PAID — requires credits)",
    description=(
        "LLM-cost endpoint. Requires Authorization: Bearer gt_*. Charges "
        "1 credit cent per call. Refuses to draft persuasive text where "
        "the proposed offer is below the caller's stated reservation "
        "(no BATNA-violating drafts). Top up credits via "
        "POST /v1/billing/checkout_session."
    ),
    responses={
        401: {"description": "Missing or malformed Authorization header"},
        402: {"description": "Insufficient credits — top up first"},
        400: {"description": "Invalid input or BATNA-violating draft refused"},
        502: {"description": "Upstream LLM error"},
    },
)
def negotiation_draft_message(
    req: DraftMessageRequest,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    api_key = _extract_api_key(authorization)
    _charge_or_402(api_key, _DRAFT_MESSAGE_COST_CENTS)

    # BATNA guard: refuse to draft if the offer would put us below our walk-away.
    # Note: we already deducted the credit. Refunding on input-validation failure
    # would be the polite move; for MVP we accept that callers eat the 1 cent
    # for malformed inputs.
    proposed_offer_utility = float(req.numbers.get("recommended_offer", 1.0))
    if proposed_offer_utility < req.my_reservation:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Refusing to draft: numbers.recommended_offer ({proposed_offer_utility}) "
                f"is below your stated reservation ({req.my_reservation}). The drafting "
                f"endpoint will not produce text that misrepresents your BATNA."
            ),
        )

    t0 = time.time()
    prompt = (
        f"You are a professional negotiator drafting a brief 3-sentence "
        f"reply email. Tone: {req.tone}.\n\n"
        f"Their last message:\n<email>\n{req.client_email}\n</email>\n\n"
        f"Your constraints:\n<constraints>\n{req.constraints_text}\n</constraints>\n\n"
        f"You MUST use these exact numbers: {req.numbers}.\n\n"
        f"Draft the reply email. Return ONLY the email body, no preamble."
    )
    try:
        text = _call_llm(prompt, temperature=0.4)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream LLM error: {e}")

    response.headers["X-GT-Cost-USD"] = _DRAFT_MESSAGE_COST_USD
    response.headers["X-GT-Latency-Ms"] = f"{(time.time() - t0) * 1000:.1f}"
    return {
        "text": text,
        "cost_usd": _DRAFT_MESSAGE_COST_USD,
        "model": os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview"),
    }


# ─── Tier 3: Mechanism Design ───────────────────────────────────────────────


@app.post(
    "/v1/mechanism/gale_shapley",
    tags=["mechanism"],
    response_model=GaleShapleyResponse,
    summary="Stable matching via deferred acceptance",
    description=(
        "Classic Gale-Shapley. Proposers iterate through their preference "
        "lists; each receiver tentatively holds the best offer it has seen. "
        "Returns a proposer-optimal stable matching plus a (should-be-empty) "
        "list of blocking pairs as a sanity check. Capacities supported for "
        "school-choice variants."
    ),
)
@_math_endpoint
def mechanism_gale_shapley(req: GaleShapleyRequest):
    return _gale_shapley(
        proposers=[p.model_dump() for p in req.proposers],
        receivers=[r.model_dump() for r in req.receivers],
    )


@app.post(
    "/v1/mechanism/optimal_auction_design",
    tags=["mechanism"],
    response_model=OptimalAuctionDesignResponse,
    summary="Myerson revenue-optimal auction (asymmetric IPV)",
    description=(
        "Per-bidder Myerson reserves. Allocation rule: argmax virtual value, "
        "subject to clearing the seller's valuation. Under symmetric IPV "
        "this collapses to second-price-with-reserve and matches the "
        "Tier 2 `optimal_reserve` answer."
    ),
)
@_math_endpoint
def mechanism_optimal_auction_design(req: OptimalAuctionDesignRequest):
    return _optimal_auction_design(
        bidder_priors=[p.model_dump() for p in req.bidder_priors],
        seller_valuation=req.seller_valuation,
        objective=req.objective,
        n_simulations=req.n_simulations,
        seed=req.seed,
    )


@app.post(
    "/v1/mechanism/posted_price_optimal",
    tags=["mechanism"],
    response_model=PostedPriceResponse,
    summary="Gallego-van Ryzin posted-price (static + dynamic schedule)",
    description=(
        "Single-product dynamic pricing. Returns the static-price upper "
        "bound, a Monte Carlo revenue estimate, and a dynamic price "
        "schedule from the backward DP."
    ),
)
@_math_endpoint
def mechanism_posted_price_optimal(req: PostedPriceRequest):
    return _posted_price_optimal(
        buyer_arrival_prior=req.buyer_arrival_prior.model_dump(),
        arrival_rate_per_second=req.arrival_rate_per_second,
        inventory=req.inventory,
        horizon_seconds=req.horizon_seconds,
        n_simulations=req.n_simulations,
        seed=req.seed,
    )


# ─── Health ──────────────────────────────────────────────────────────────────


@app.get("/health", tags=["discovery"], summary="Liveness check")
def health():
    # `trust_anchor_source` reveals whether first-strike JWTs will survive
    # restarts. "ephemeral" → fine for dev; in prod it means the operator
    # forgot to set FIRST_STRIKE_PRIVATE_PEM and historical attestations
    # become unverifiable on the next deploy.
    return {
        "status": "ok",
        "version": "0.1.0",
        "first_strike_key_source": _trust_anchor_source(),
    }

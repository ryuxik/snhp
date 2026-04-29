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

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
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
)
from gametheory.server import telemetry as _telemetry
from gametheory.server.middleware import bearer_api_key as _bearer_api_key


_COST_FREE = "0"

# Fields stripped from the request body before storage as request_features —
# they're metadata about the consent decision, not features.
_TELEMETRY_REQUEST_EXCLUDED = {"share_outcome", "vertical"}

# Allowlisted endpoint identifiers stored in the telemetry corpus. Typed
# rather than free-string so a typo here surfaces at module-load time
# instead of silently sharding the corpus.
_TelemetryEndpoint = Literal[
    "negotiation/sell/next_offer",
    "negotiation/buy/next_offer",
    "auction/bidder/optimal_bid",
    "mechanism/optimal_auction_design",
    "mechanism/posted_price_optimal",
]


def _record_telemetry(request: Request, req: BaseModel, result: dict,
                       *, endpoint: "_TelemetryEndpoint") -> Optional[str]:
    """Record a telemetry row if the caller opted in. Returns the
    recommendation_id (or None if not recorded).

    Two-gate consent: `share_outcome=True` on the request AND account-level
    consent. If pepper is missing on a share_outcome=True request, this
    raises (per V1 design — better a loud failure than a silent privacy
    lie). Other failures (DB hiccup, etc.) propagate too; the caller chose
    to share, so degrading their request to a silent no-op would mislead.
    """
    if not getattr(req, "share_outcome", False):
        return None
    api_key = _bearer_api_key(request)
    if api_key is None:
        # share_outcome=True with no bearer key — caller's mistake, but
        # silently dropping is fine here: nothing to anchor a delete to.
        return None
    vertical = getattr(req, "vertical", None) or "other"
    features = req.model_dump(exclude=_TELEMETRY_REQUEST_EXCLUDED)
    return _telemetry.record_recommendation(
        api_key=api_key, endpoint=endpoint, vertical=vertical,
        request_features=features, recommendation=result,
    )


def _math_endpoint(_handler: Optional[Callable[..., dict]] = None,
                    *, telemetry: "Optional[_TelemetryEndpoint]" = None) -> Callable:
    """
    Decorator for math-only endpoints. Wraps a pure-math handler with
    timing, free-tier cost header, and ValueError → HTTP 400 conversion.

    Two forms:
      @_math_endpoint                              # plain math, no telemetry
      @_math_endpoint(telemetry="endpoint_name")   # opt-in telemetry record

    FastAPI inspects the wrapper's signature to discover Pydantic body
    params and injected dependencies (Response, Request). We copy the
    handler's type annotations onto the wrapper so FastAPI sees
    `req: <PydanticModel>` instead of treating `req` as a query parameter.
    """

    def make(handler: Callable[..., dict]) -> Callable:
        def wrapper(req, request: Request, response: Response):  # type: ignore[no-untyped-def]
            t0 = time.time()
            try:
                result = handler(req)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            response.headers["X-GT-Cost-USD"] = _COST_FREE
            response.headers["X-GT-Latency-Ms"] = f"{(time.time() - t0) * 1000:.1f}"
            if telemetry is not None:
                rec_id = _record_telemetry(request, req, result, endpoint=telemetry)
                if rec_id is not None:
                    response.headers["X-GT-Recommendation-Id"] = rec_id
            return result

        wrapper.__name__ = handler.__name__
        wrapper.__doc__ = handler.__doc__
        handler_annotations = getattr(handler, "__annotations__", {}) or {}
        if "req" in handler_annotations:
            wrapper.__annotations__["req"] = handler_annotations["req"]
        wrapper.__annotations__["request"] = Request
        wrapper.__annotations__["response"] = Response
        return wrapper

    if _handler is not None:
        return make(_handler)
    return make


# ─── Models ──────────────────────────────────────────────────────────────────


_VerticalLiteral = Literal[
    "ad_inventory",
    "saas_procurement",
    "cloud_compute",
    "freight_logistics",
    "media_licensing",
    "m_and_a_buyside",
    "m_and_a_sellside",
    "real_estate",
    "energy_trading",
    "professional_services",
    "marketplace_b2b",
    "other",
]


class _OptInTelemetry(BaseModel):
    """Mixin: opt-in fields for contributing this call to our prior corpus.

    Two-gate consent model: account-level `telemetry_consent` (set at /v1/keys
    issuance, immutable) AND per-call `share_outcome=True` are BOTH required.
    The per-call flag is a downgrade-only refinement — share_outcome=True
    without account consent is silently ignored (record returns None).

    `vertical` is an allowlisted enum (no free text — covert-channel risk).
    The api_key is HMAC-hashed with a per-week server-side pepper before
    storage (never reversible, not joinable across weeks). See
    /v1/telemetry/* endpoints for outcome reporting, GDPR export, and
    deletion. Privacy contract documented in /llms.txt.
    """
    share_outcome: bool = Field(default=False,
        description="Opt-in: contribute this (anonymized) call to the prior "
                     "corpus. Default False. Requires account-level consent "
                     "set at /v1/keys issuance.")
    vertical: Optional[_VerticalLiteral] = Field(default=None,
        description="Self-declared vertical (allowlisted enum). Required "
                     "when share_outcome=True. Use 'other' if none fit.")


class WTPPrior(BaseModel):
    mu: float = Field(description="Lognormal μ of buyer WTP")
    sigma: float = Field(description="Lognormal σ of buyer WTP")


class SellNextOfferRequest(_OptInTelemetry):
    my_reservation: float = Field(ge=0.0, le=1.0,
        description="Our walk-away utility, normalized to [0, 1]")
    opponent_offer_history: list[float] = Field(default_factory=list, max_length=128,
        description="Opponent's offers evaluated in our utility space, in [0, 1]")
    my_offer_history: list[float] = Field(default_factory=list, max_length=128)
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


class OptimalBidRequest(_OptInTelemetry):
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


class BuyNextOfferRequest(_OptInTelemetry):
    my_reservation: float = Field(ge=0.0, le=1.0)
    seller_offer_history: list[float] = Field(default_factory=list, max_length=128,
        description="Seller's offers evaluated in our (buyer's) utility space, in [0, 1]")
    my_offer_history: list[float] = Field(default_factory=list, max_length=128)
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
    opponent_offer_history: list[float] = Field(min_length=0, max_length=128)
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
    # Strict shape: 43-char base64url SHA-256 (no padding). Producer always
    # emits this length; tighter check rejects truncated/encoded variants.
    reservation_hash: str = Field(min_length=43, max_length=43,
        pattern=r"^[A-Za-z0-9_\-]{43}$",
        description="SHA-256 base64url of (reservation || nonce || salt || ids)")
    deadline_iso: str = Field(min_length=15, max_length=64,
        description="ISO 8601 deadline, e.g. 2026-04-29T14:00:00Z")
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


# ─── Tier 3: Mechanism Design ───────────────────────────────────────────────


class Proposer(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    preferences: list[str] = Field(default_factory=list, max_length=1024,
        description="Receiver ids ranked most-preferred first")


class Receiver(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    preferences: list[str] = Field(default_factory=list, max_length=1024,
        description="Proposer ids ranked most-preferred first")
    capacity: int = Field(default=1, ge=1, le=1024)


class GaleShapleyRequest(BaseModel):
    proposers: list[Proposer] = Field(min_length=1, max_length=1024)
    receivers: list[Receiver] = Field(min_length=1, max_length=1024)


class GaleShapleyResponse(BaseModel):
    matching: dict
    unmatched_proposers: list[str]
    blocking_pairs: list[list[str]]
    n_proposals: int


class OptimalAuctionDesignRequest(_OptInTelemetry):
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


class PostedPriceRequest(_OptInTelemetry):
    # Tightened from {arrival_rate ≤ 1000, inventory ≤ 100k, horizon ≤ 30d}
    # because the DP allocates O(C × n_bins × |P|) where n_bins scales with
    # arrival_rate × horizon. Worst-case under the old bounds was 13 billion
    # iterations + GBs of float64 churn → guaranteed OOM on the 512MB box.
    # The runtime budget guard below catches problematic combinations even
    # within the per-field caps.
    buyer_arrival_prior: PriorParams
    arrival_rate_per_second: float = Field(gt=0.0, le=100.0)
    inventory: int = Field(ge=1, le=10_000)
    horizon_seconds: float = Field(gt=0.0, le=7 * 86400)
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
        "(Gale-Shapley, optimal auction, posted-price). All endpoints free "
        "today; LLM drafting is BYOK (you bring your own LLM key).\n\n"
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
        {"name": "telemetry",   "description": "Opt-in data sharing + GDPR (export/delete)"},
    ],
)


# Middleware order matters: outermost wraps innermost. We want the
# body-size guard FIRST (cheapest reject), then rate limit (also cheap),
# then security headers (must run on the way out so they apply to
# rate-limit responses too).
from gametheory.server.middleware import (  # noqa: E402
    BodySizeLimit, RateLimit, SecurityHeaders,
)
app.add_middleware(SecurityHeaders)
app.add_middleware(RateLimit)
app.add_middleware(BodySizeLimit)


# ─── Static landing page + assets ───────────────────────────────────────────


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_INDEX_HTML = os.path.join(_STATIC_DIR, "index.html")

if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def landing():
    """Marketing landing page. Anything outside `/v1/*`, `/health`,
    `/docs`, `/openapi.json`, `/llms.txt` falls through to here.

    The strict default CSP (`default-src 'none'`) blocks the page's inline
    style + script. Relax CSP to same-origin only for this route — there
    is no user-input reflection so inline is safe."""
    if not os.path.isfile(_INDEX_HTML):
        raise HTTPException(status_code=404, detail="landing page not bundled")
    return FileResponse(
        _INDEX_HTML,
        media_type="text/html",
        headers={
            "Content-Security-Policy": (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; "
                "img-src 'self' data:; "
                "frame-ancestors 'none'"
            ),
        },
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
@_math_endpoint(telemetry="negotiation/sell/next_offer")
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
@_math_endpoint(telemetry="auction/bidder/optimal_bid")
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
All endpoints are FREE today (math only — NumPy / SciPy, ~50ms p99).
Rate limit: 600/min per key. We do not host or resell LLM calls; if your
agent needs natural-language drafting, do that with your own LLM provider
(see "Drafting messages client-side" below).

## Onboarding (no human in the loop)
- POST /v1/keys
    body: {agent_id, contact_email, intended_use_summary,
           telemetry_consent: bool = false}
    -> {api_key: "gt_*", telemetry_consent, ...}

## Telemetry (opt-in, off by default)
We collect aggregate prior-corpus data ONLY when you opt in. The corpus
warm-starts new agents in the same vertical (e.g. Bayesian priors for
buyer WTP). Default behavior collects nothing.

How to opt in:
1. Pass `telemetry_consent: true` at /v1/keys issuance. Account-level
   consent is set ONCE at issuance and immutable thereafter — to revoke,
   call /v1/telemetry/delete and stop passing share_outcome on future calls.
2. On each recommendation request, pass `share_outcome: true` AND
   `vertical: "<one of the allowlisted enum values>"`. Both gates must
   be true; either one false → no row is written.
3. The successful response carries `X-GT-Recommendation-Id: rec_*`.
   Store it; you'll need it to attach an outcome.
4. After your deal closes (or doesn't), POST /v1/telemetry/report_outcome
   with `{recommendation_id, deal_closed, my_utility, opponent_utility}`.
   MUST be called within the same ISO week as the recommendation — the
   per-week agent-hash bound caps outcome reporting at ~7 days.

What we store:
- An HMAC(pepper, api_key || iso_week) hash of your key, truncated to
  128 bits, base64url. Per-week rotation eliminates cross-time linkability;
  the pepper is a server secret and never leaves the box. Hashes are NOT
  reversible to your key and NOT joinable across weeks.
- Numeric features quantized to a 0.02 grid (50 buckets across [0,1]) to
  shed fingerprint entropy.
- Lists capped at 16 elements at storage; free-text rationale is stripped.
- The vertical you self-declared (allowlisted enum, no free text).

What we do NOT store:
- Wall-clock timestamps (only the hour bucket).
- Your raw api_key (only the per-week hash).
- Free-text fields of any kind.
- IP addresses, user agents, or other request metadata.

GDPR (apply regardless of EU residence):
- DELETE /v1/telemetry/delete  (Article 17: erasure)
    -> {rows_deleted: N}
  Sweeps the last 78 weeks of week-hashes.
- GET /v1/telemetry/export  (Article 15: access)
    -> {rows: [...]}
  Returns every row tied to any of your week-hashes within the same window.

Allowlisted verticals:
  ad_inventory, saas_procurement, cloud_compute, freight_logistics,
  media_licensing, m_and_a_buyside, m_and_a_sellside, real_estate,
  energy_trading, professional_services, marketplace_b2b, other

## Drafting messages client-side (BYOK pattern)
We deliberately do not call LLMs server-side; you bring your own. The
recommended drafting prompt for negotiation reply emails:

  "You are a professional negotiator drafting a brief 3-sentence reply
   email. Tone: <professional|friendly|firm>.
   Their last message: <their email>
   Your constraints: <constraints text>
   You MUST use these exact numbers: <output of next_offer>.
   Draft the reply email. Return ONLY the email body, no preamble."

Hard rule (BATNA guard): refuse to draft if `numbers.recommended_offer`
is below your stated reservation. We enforce this server-side in the
math endpoints; replicate it in your draft-time code.

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
- LLM calls: BYOK (we don't host them).
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
    telemetry_consent: bool = Field(default=False,
        description=(
            "Opt-in to contribute anonymized recommendation→outcome pairs to "
            "the prior corpus. Default False. Set at issuance and immutable "
            "afterwards (revocation = /v1/telemetry/delete + don't pass "
            "share_outcome=True). See /llms.txt for the privacy contract."
        ))


class IssueKeyResponse(BaseModel):
    api_key: str
    tier: str
    rate_limit_per_minute: int
    created_at: int
    balance_usd_cents: int = Field(description="Remaining credit balance in cents")
    telemetry_consent: bool = Field(description="True if opted into telemetry at issuance")
    reused: bool = Field(description="True if an existing key for this agent_id was returned")


@app.post(
    "/v1/keys",
    tags=["discovery"],
    response_model=IssueKeyResponse,
    summary="Programmatic API key issuance (no human approval)",
    description=(
        "Self-serve key issuance for AI agents. No human approval gate. "
        "Idempotent on agent_id within 24h. All endpoints currently free; "
        "rate-limited to 600 requests/minute per key."
    ),
)
def issue_key(req: IssueKeyRequest):
    try:
        return _issue_key(
            agent_id=req.agent_id,
            contact_email=req.contact_email,
            intended_use_summary=req.intended_use_summary,
            telemetry_consent=req.telemetry_consent,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Telemetry: outcome reporting + GDPR ────────────────────────────────────


def _require_bearer_key(request: Request) -> str:
    """Extract a `gt_*` bearer token or raise 401."""
    api_key = _bearer_api_key(request)
    if api_key is None:
        raise HTTPException(status_code=401,
                            detail="Authorization: Bearer gt_* required")
    return api_key


class ReportOutcomeRequest(BaseModel):
    recommendation_id: str = Field(min_length=1, max_length=128,
        description="The X-GT-Recommendation-Id returned when share_outcome=True")
    deal_closed: bool = Field(description="True if a deal was reached")
    my_utility: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Realized utility-to-self in [0, 1] (quantized at write)")
    opponent_utility: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Realized utility-to-opponent if known, in [0, 1]")


class ReportOutcomeResponse(BaseModel):
    accepted: bool = Field(description=(
        "False if the recommendation_id doesn't exist, doesn't belong to "
        "this key, is in a different ISO week (too late), or has already "
        "been reported. Idempotent re-report = no-op."))


@app.post(
    "/v1/telemetry/report_outcome",
    tags=["telemetry"],
    response_model=ReportOutcomeResponse,
    summary="Attach an outcome to a previously-recorded recommendation",
    description=(
        "Must be called within the same ISO week as the recommendation. "
        "Per-week agent-hash bounding caps outcome reporting at ~7 days "
        "(by design — eliminates long-horizon behavioral fingerprinting)."
    ),
)
def telemetry_report_outcome(req: ReportOutcomeRequest, request: Request):
    api_key = _require_bearer_key(request)
    accepted = _telemetry.report_outcome(
        api_key=api_key,
        recommendation_id=req.recommendation_id,
        deal_closed=req.deal_closed,
        my_utility=req.my_utility,
        opponent_utility=req.opponent_utility,
    )
    return {"accepted": accepted}


class TelemetryDeleteResponse(BaseModel):
    rows_deleted: int


@app.delete(
    "/v1/telemetry/delete",
    tags=["telemetry"],
    response_model=TelemetryDeleteResponse,
    summary="GDPR Article 17 — delete all telemetry rows for this key",
    description=(
        "Deletes all rows whose week-hash matches any of this key's "
        "possible week hashes within an 18-month retention window. "
        "Returns the row count deleted. Note: SQLite/Postgres tombstone "
        "reclaim is deferred (full storage reclaim within 30 days)."
    ),
)
def telemetry_delete(request: Request):
    api_key = _require_bearer_key(request)
    return {"rows_deleted": _telemetry.delete_agent_records(api_key)}


class TelemetryRecordOut(BaseModel):
    recommendation_id: str
    vertical: str
    endpoint: str
    request_features: dict
    recommendation: dict
    created_at_hour: int
    outcome: Optional[dict]


class TelemetryExportResponse(BaseModel):
    rows: list[TelemetryRecordOut]


@app.get(
    "/v1/telemetry/export",
    tags=["telemetry"],
    response_model=TelemetryExportResponse,
    summary="GDPR Article 15 — export all telemetry rows for this key",
)
def telemetry_export(request: Request):
    api_key = _require_bearer_key(request)
    return {"rows": _telemetry.export_agent_records(api_key)}


# ─── Buy-side negotiation ───────────────────────────────────────────────────


@app.post(
    "/v1/negotiation/buy/next_offer",
    tags=["negotiation"],
    response_model=BuyNextOfferResponse,
    summary="Buy-side next-offer recommendation with defense bundle",
)
@_math_endpoint(telemetry="negotiation/buy/next_offer")
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
@_math_endpoint(telemetry="mechanism/optimal_auction_design")
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
@_math_endpoint(telemetry="mechanism/posted_price_optimal")
def mechanism_posted_price_optimal(req: PostedPriceRequest):
    # DP allocates O(C × n_bins × |P|) where n_bins ≈ arrival_rate × T / 0.2.
    # |P| is fixed at 50; reject inputs that would exceed ~50M cells (~400 MB
    # of float64 churn) before the DP starts allocating.
    n_bins_estimate = max(60, req.arrival_rate_per_second * req.horizon_seconds / 0.2)
    cells = req.inventory * n_bins_estimate * 50
    if cells > 50_000_000:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Compute budget exceeded: estimated {int(cells):,} DP cells "
                f"(inventory × bins × prices), max 50M. Reduce inventory, "
                f"horizon_seconds, or arrival_rate_per_second."
            ),
        )
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

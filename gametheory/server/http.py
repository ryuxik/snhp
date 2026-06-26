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

import json
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
from gametheory.negotiation.dispute_sim import run_comparison as _dispute_run_comparison
from gametheory.negotiation.dispute_copilot import (
    extract_dispute as _extract_dispute,
    parse_platform_reply as _parse_platform_reply,
    coach_round as _coach_round,
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
    settlement_notary_public_key_pem as _settlement_notary_pem,
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
from gametheory.server import _llm_budget
from gametheory.server import dispute_analytics as _analytics
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
        description="0=max deal rate, 1=max H2H margin (only used when peer_mode=False)")
    buyer_wtp_prior: Optional[WTPPrior] = None
    peer_mode: bool = Field(default=False,
        description=(
            "Set True when counterparty is a verified SNHP-protocol peer "
            "(cryptographic attestation). Activates cooperative architecture "
            "(PEER playbook + max-self signaling). Empirically reaches 96-101% "
            "of Pareto frontier vs 89-92% for vanilla descent. See /llms.txt."
        ))


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
    peer_mode: bool = Field(default=False,
        description=(
            "Set True when counterparty is a verified SNHP-protocol peer. "
            "Activates cooperative architecture (PEER playbook + signaling). "
            "Empirically reaches 96-101% of Pareto frontier vs 89-92% vanilla."
        ))


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

# Hosted streamable MCP transport — mounted at /mcp below. The MCP session
# manager needs its lifespan run, so we nest it inside the FastAPI app's
# lifespan (else /mcp errors with "task group not initialized"). Transport/host
# config lives on the shared FastMCP instance in mcp_server.py.
from contextlib import asynccontextmanager as _asynccontextmanager  # noqa: E402
from gametheory.server.mcp_server import mcp as _mcp  # noqa: E402

_mcp_app = _mcp.streamable_http_app()


@_asynccontextmanager
async def _lifespan(_app):
    async with _mcp_app.router.lifespan_context(_mcp_app):
        yield


app = FastAPI(
    lifespan=_lifespan,
    title="Game Theory Layer for AI Agents",
    description=(
        "Start with ONE tool: POST /v1/negotiate/turn — plain-dollar price "
        "negotiation (your walk-away + the other side's offers in dollars -> the "
        "counter to send, a ready-to-send message, accept/walk advice). Also: "
        "auctions (Myerson, Vickrey, English), mechanism design (Gale-Shapley, "
        "posted-price), and an advanced verified agent-to-agent + AP2 flow. All "
        "math endpoints free.\n\n"
        "Validated: the negotiate tool is ~12% better head-to-head (n=20 paired "
        "LLM negotiations, 95% CI +6.5-17.4%, p<0.0001).\n\n"
        "Discovery: GET /v1/catalog for the tool list, /llms.txt for the "
        "LLM-readable guide."
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


# ─── Agent-to-agent commerce: A2A discovery, verified peering, AP2 settlement ─
# Operator registry + verified-peer sessions + AP2 mandates. peer_mode is
# DERIVED from a verified handshake here (vs the self-asserted boolean on the
# legacy /v1/negotiation/* endpoints).
from gametheory.server.a2a_routes import router as _a2a_router  # noqa: E402
app.include_router(_a2a_router)

# Hosted MCP server (streamable HTTP) at /mcp — same toolkit, MCP-native, so
# agents/clients that speak MCP over HTTP can connect without installing the
# stdio package. (Endpoint serves at /mcp/; /mcp 307-redirects to it.)
app.mount("/mcp", _mcp_app)


# ─── Static landing page + assets ───────────────────────────────────────────


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_INDEX_HTML = os.path.join(_STATIC_DIR, "index.html")

if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# CSP for marketing pages — same-origin only, allows inline styles/scripts
# the static pages bundle. Marketing pages don't reflect user input.
_LANDING_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'"
)


def _serve_static_page(filename: str, media_type: str = "text/html"):
    """Helper to serve a static asset from `static/` at a root-level URL
    (so links like /demo.html work, not just /static/demo.html)."""
    path = os.path.join(_STATIC_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{filename} not bundled")
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Security-Policy": _LANDING_CSP},
    )


# Hostnames that should land directly on the public dispute tool (app.html)
# instead of the marketing index. Set SNHP_TOOL_HOSTS to a comma-separated
# list to override (e.g. on a staging subdomain).
_TOOL_HOSTS = {
    h.strip().lower() for h in
    os.environ.get("SNHP_TOOL_HOSTS", "disputes.snhp.dev,try.snhp.dev").split(",")
    if h.strip()
}


@app.get("/", include_in_schema=False)
def landing(request: Request):
    """Root page. On the dispute-tool subdomain(s) this serves the tool
    directly (so a Twitter tap lands right on it); everywhere else it serves
    the marketing index. Anything outside `/v1/*`, `/health`, `/docs`,
    `/openapi.json`, `/llms.txt` falls through to here."""
    host = request.headers.get("host", "").split(":")[0].lower()
    if host in _TOOL_HOSTS:
        return _serve_static_page("app.html")
    return _serve_static_page("index.html")


@app.get("/demo.html", include_in_schema=False)
def demo_page():
    """Interactive replay of vanilla-vs-scaffolded LLM negotiation
    (real Anthropic API trace at seed=42)."""
    return _serve_static_page("demo.html")


@app.get("/demo_trace.json", include_in_schema=False)
def demo_trace():
    """Trace data consumed by the demo replay player."""
    return _serve_static_page("demo_trace.json", media_type="application/json")


@app.get("/demo_traces.json", include_in_schema=False)
def demo_traces():
    """Multi-tournament trace data for the Try-live selector."""
    return _serve_static_page("demo_traces.json", media_type="application/json")


@app.get("/dispute.html", include_in_schema=False)
def dispute_page():
    """Dispute-resolution negotiation prototype: pick a dispute, elicit the
    customer's settlement band, run the real negotiation core, see the
    outcome vs. an unaided baseline."""
    return _serve_static_page("dispute.html")


@app.get("/platforms.html", include_in_schema=False)
def platforms_page():
    """Business-facing landing page — SNHP as a dispute-settlement layer."""
    return _serve_static_page("platforms.html")


@app.get("/console.html", include_in_schema=False)
def console_page():
    """Operator console — run one real dispute through SNHP: extract, coach
    each round, draft messages, log the (context, action, outcome) record."""
    return _serve_static_page("console.html")


@app.get("/app.html", include_in_schema=False)
def app_page():
    """The public, mobile-first dispute tool (Twitter landing): zero-cost
    demo gasp → share card → rate-limited 'your real dispute' co-pilot."""
    return _serve_static_page("app.html")


@app.get("/dispute_scenarios.json", include_in_schema=False)
def dispute_scenarios():
    """Synthetic dispute scenario shells consumed by /dispute.html.
    Generator: snhp/cs_negotiation_dataset.py."""
    return _serve_static_page("dispute_scenarios.json", media_type="application/json")


@app.get("/reputation_scoring_spec.html", include_in_schema=False)
def reputation_spec_page():
    """Spec for the SNHP Reputation Scoring product (the moat layer)."""
    return _serve_static_page("reputation_scoring_spec.html")


@app.get("/for-builders.html", include_in_schema=False)
def for_builders_page():
    """Outreach landing tailored to AI agent builders — proof, who-it's-for,
    integration steps, FAQ, contact form."""
    return _serve_static_page("for-builders.html")


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
        peer_mode=req.peer_mode,
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
    "/v1/internal/params",
    tags=["discovery"],
    summary="Currently-active negotiation parameters (for telemetry/debug)",
    description=(
        "Returns every tunable parameter, its default, current active value, "
        "whether it's overridden via env var, and metadata (rationale + source). "
        "Useful for confirming which Optuna-tuned values are live + detecting "
        "drift. No auth required (server-state only, no per-call data)."
    ),
)
def internal_params():
    from gametheory.negotiation._config import active_snapshot
    return active_snapshot()


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
        "pricing_url": "/PRICING.md",
        "pricing": {
            "model": "free core math; usage-based LLM extras; settlement fee on the A2A moat",
            "tiers": [
                {"tier": 0, "what": "core math tools (negotiate.*, auction.*, mechanism.*)",
                 "price": "free", "key_required": False},
                {"tier": 1, "what": "LLM-backed extras (/v1/dispute/* drafting & coaching)",
                 "price": "off by default (opt-in); when on, hard $/day cap + per-IP limit; key-gated for production",
                 "llm": True, "default_enabled": False},
                {"tier": 2, "what": "A2A verified commerce + AP2 settlement (/v1/a2a/*)",
                 "price": "0.1-0.5% of settled value (or operator seat); priced per partner"},
            ],
        },
        "sla": {
            "level": "best-effort",
            "uptime_guarantee": None,
            "self_hostable": True,
            "note": ("No uptime SLA today (single deployment) — best-effort. The core "
                     "math is deterministic and self-hostable, so you can depend on no "
                     "one. A real 99.9%-with-credits commitment comes only with "
                     "redundant infra."),
        },
        "tools": [
            {
                "name": "gt.negotiate.turn",
                "tier": 1,
                "endpoint": "POST /v1/negotiate/turn",
                "cost_class": "free",
                "stability": "stable",
                "description": (
                    "START HERE. The math-optimal next move in a single-price "
                    "negotiation, in plain DOLLARS — no game theory needed. Give it "
                    "your side, walk-away $, target $, and the other side's offers "
                    "in $; get back the dollar counter to send, a ready-to-send "
                    "message, and accept/walk advice. Validated ~12% better "
                    "head-to-head (n=20 paired LLM negotiations, 95% CI +6.5-17.4%, "
                    "p<0.0001). Works against ANY counterparty, zero setup. Use for "
                    "multi-round price haggling; NOT one-shot fixed prices, "
                    "multi-issue bundles (use gt.negotiate.bundle for those), or "
                    "non-price decisions like accept-vs-decline."
                ),
                "example_input": {
                    "side": "sell", "walk_away": 4000, "target": 6000,
                    "counterparty_offers": [4200, 4500], "rounds_left": 6,
                },
                "example_output": {
                    "action": "counter", "recommended_price": 5387.0,
                    "message": "Thanks for the offer. The best I can do on this is $5,387.00.",
                    "fit": {"score": "good"}, "expected_settlement": 4943.5,
                },
            },
            {
                "name": "gt.negotiate.bundle",
                "tier": 1,
                "endpoint": "POST /v1/negotiate/bundle",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "MULTI-ISSUE deals. When a negotiation has several linked issues "
                    "at once (a job offer = base + equity + signing; a SaaS contract "
                    "= price + seats + term + SLA), this LOGROLLS: it concedes on the "
                    "issues you care about less (and they care about more) to win the "
                    "ones you care about most — a package that beats splitting every "
                    "issue down the middle. Give your and their per-option values per "
                    "issue; it INFERS their priorities from their offers and returns "
                    "the package to propose plus the trade logic. Use gt.negotiate.turn "
                    "for a single price. Validated (separate from the +12%): returns a "
                    "Pareto-efficient package that beats naive split-every-issue "
                    "bargaining by ~40% joint surplus (300 random 4-issue profiles). "
                    "Honest caveat: the priority-inference is weak (r≈0.3) and adds "
                    "only ~1% over a no-inference baseline — the proven value is the "
                    "efficient-package search, not yet the logrolling edge."
                ),
                "example_input": {
                    "issues": [
                        {"name": "price_per_seat", "options": ["$50", "$40", "$30"],
                         "my_utility": [0, 0.5, 1], "their_utility": [1, 0.5, 0]},
                        {"name": "seats", "options": ["50", "100", "200"],
                         "my_utility": [1, 0.6, 0.2], "their_utility": [0, 0.6, 1]},
                        {"name": "sla", "options": ["99%", "99.9%"],
                         "my_utility": [0, 1], "their_utility": [1, 0]},
                    ],
                    "my_priorities": {"price_per_seat": 0.6, "seats": 0.25, "sla": 0.15},
                    "their_offers": [{"price_per_seat": "$50", "seats": "200", "sla": "99%"}],
                },
                "example_output": {
                    "action": "counter",
                    "recommended_offer": {"price_per_seat": "$30", "seats": "100", "sla": "99%"},
                    "message": "Proposed package — price_per_seat: $30, seats: 100, sla: 99%. "
                               "Give ground on 'sla' to hold firm on 'price_per_seat'.",
                    "my_utility": 0.65, "their_expected_utility": 0.74,
                    "inferred_their_priorities": {"price_per_seat": 0.18, "seats": 0.19, "sla": 0.31},
                    "fit": {"score": "good"},
                },
            },
            {
                "name": "gt.negotiation.sell.next_offer",
                "tier": 1,
                "endpoint": "POST /v1/negotiation/sell/next_offer",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "ADVANCED / low-level. Sell-side recommendation in NORMALIZED "
                    "utility [0,1] (prefer gt.negotiate.turn, which speaks dollars). "
                    "Single SNHP customer beats vanilla counterparty by +12% "
                    "head-to-head (T1, n=20, p<0.0001). Set peer_mode=true when the "
                    "counterparty is a verified SNHP peer for the +7% premium."
                ),
                "example_input": {
                    "my_reservation": 0.40,
                    "opponent_offer_history": [0.55, 0.62],
                    "my_offer_history": [0.85, 0.78],
                    "deadline_rounds": 8,
                    "pareto_knob": 0.5,
                    "peer_mode": False,
                },
                "example_output": {
                    "recommended_offer": 0.68,
                    "acceptance_probability": 0.42,
                    "expected_payoff": 0.56,
                    "rationale": "(elided)",
                },
            },
            {
                "name": "gt.auction.bidder.optimal_bid",
                "tier": 2,
                "endpoint": "POST /v1/auction/bidder/optimal_bid",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "The bid to place when you're BIDDING in an auction "
                    "(first-price sealed bid, second-price/Vickrey, or English "
                    "ascending). Tell it your own value for the item, how many "
                    "rivals you face, and a rough range of what they'd pay; get "
                    "back the bid that maximizes your expected surplus without "
                    "overpaying. The bid comes back in the SAME dollars you put "
                    "in. Use when you're a bidder; to RUN an auction use "
                    "gt.auction.seller.optimal_reserve, for 1:1 haggling use "
                    "gt.negotiate.turn."
                ),
                "example_input": {
                    "auction_format": "first_price",
                    "my_valuation": 5000,
                    "n_competing_bidders": 4,
                    "competitor_value_prior": {
                        "family": "uniform", "params": {"low": 0, "high": 6000},
                    },
                },
                "example_output": {
                    "optimal_bid": 4000.0, "expected_surplus": 482.25,
                    "win_probability": 0.48, "dominant_strategy": False,
                    "rationale": "(elided)",
                },
            },
            {
                "name": "gt.auction.seller.optimal_reserve",
                "tier": 2,
                "endpoint": "POST /v1/auction/seller/optimal_reserve",
                "cost_class": "free",
                "stability": "beta",
                "description": (
                    "The revenue-maximizing RESERVE PRICE (the lowest bid you'll "
                    "accept) for an auction you're RUNNING. Tell it how many "
                    "bidders, what the item is worth to YOU, and a rough range of "
                    "what bidders would pay; get back the floor price and the "
                    "expected revenue. Reserve and revenue come back in the SAME "
                    "dollars you put in. Use when you're the seller; to BID use "
                    "gt.auction.bidder.optimal_bid, for 1:1 haggling use "
                    "gt.negotiate.turn."
                ),
                "example_input": {
                    "bidder_value_prior": {
                        "family": "uniform", "params": {"low": 2000, "high": 8000},
                    },
                    "n_bidders": 5, "seller_valuation": 1000,
                },
                "example_output": {
                    "reserve_price": 4500.0, "expected_revenue": 6014.29,
                    "expected_revenue_no_reserve": 6006.87,
                    "rationale": "(elided)",
                },
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
                    "detection, Schelling commitment). Pareto knob for buyers. "
                    "Set peer_mode=true for cooperative counterparties."
                ),
                "example_input": {
                    "my_reservation": 0.40,
                    "seller_offer_history": [0.55, 0.62],
                    "my_offer_history": [0.15, 0.22],
                    "deadline_rounds": 8,
                    "peer_mode": False,
                },
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
                    "Match two groups by their rankings so the result is STABLE "
                    "— no pair would both rather have each other than who they "
                    "got (interns<->teams, students<->schools, mentors<->mentees). "
                    "Give each side a list of {id, preferences} (preferences = "
                    "the other side's ids, most-wanted first; receivers may set "
                    "capacity for >1 slot). Get back the assignment by name, who "
                    "went unmatched, and a blocking-pair check (empty = stable). "
                    "NOTE: it returns the PROPOSER-optimal matching, so put the "
                    "side you want to favor in `proposers`."
                ),
                "example_input": {
                    "proposers": [
                        {"id": "Ana", "preferences": ["Growth", "Core", "Infra"]},
                        {"id": "Ben", "preferences": ["Core", "Growth", "Infra"]},
                        {"id": "Cy", "preferences": ["Growth", "Infra", "Core"]},
                    ],
                    "receivers": [
                        {"id": "Growth", "preferences": ["Ben", "Ana", "Cy"]},
                        {"id": "Core", "preferences": ["Ana", "Ben", "Cy"]},
                        {"id": "Infra", "preferences": ["Cy", "Ana", "Ben"]},
                    ],
                },
                "example_output": {
                    "matching": {"Ana": "Growth", "Ben": "Core", "Cy": "Infra"},
                    "unmatched_proposers": [], "blocking_pairs": [],
                    "n_proposals": 4,
                },
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
                    "Best price (and how to drop it over time) when you must sell "
                    "a FIXED stock by a DEADLINE with demand trickling in — "
                    "event tickets, perishable inventory, end-of-life units. Give "
                    "it your stock count, the selling window in SECONDS, how many "
                    "shoppers arrive per second, and a rough range of what they'd "
                    "pay; get back one good fixed price AND a markdown schedule "
                    "(price at each time point) plus expected revenue. All prices "
                    "in the SAME dollars you put in. (Convert your window: 14 days "
                    "= 14*24*3600 = 1209600 seconds; rate = expected shoppers / "
                    "that window.) Not for 1:1 haggling (gt.negotiate.turn) or "
                    "auctions (gt.auction.*)."
                ),
                "example_input": {
                    "buyer_arrival_prior": {
                        "family": "uniform", "params": {"low": 40, "high": 150},
                    },
                    "arrival_rate_per_second": 0.000496,
                    "inventory": 200,
                    "horizon_seconds": 1209600,
                },
                "example_output": {
                    "static_price": 112.18,
                    "static_expected_revenue": 22088.61,
                    "dynamic_schedule": [
                        {"t_seconds": 0.0, "recommended_price": 114.08},
                        {"t_seconds": 604800.0, "recommended_price": 80.41},
                        "... 9 more waypoints to the deadline ...",
                    ],
                    "sellthrough_rate": 0.98,
                    "rationale": "(elided)",
                },
            },
        ],
        "a2a_flow": {
            "what": ("ADVANCED: use only when the counterparty ALSO runs SNHP. Prove "
                     "both identities to unlock a cooperation premium (more joint "
                     "surplus between verified peers) and a signed, settleable AP2 deal "
                     "record. Against an unknown counterparty just use gt.negotiate.turn "
                     "/ gt.negotiate.bundle — none of this is needed."),
            "guide": "gametheory/server/A2A_FLOW.md",
            "steps": [
                "0. POST /v1/registry/register_operator (each side, once; optional "
                "/v1/registry/request_domain_challenge + /verify_domain for domain identity)",
                "1. build a peer proof LOCALLY (MCP gt_a2a_build_peer_proof; key stays on your host)",
                "2. exchange the two proofs with the counterparty",
                "3. POST /v1/a2a/open_session with both proofs -> session_id + server-derived peer_mode",
                "4. POST /v1/a2a/next_offer using the session's peer_mode",
                "5. POST /v1/a2a/settle -> a signed AP2 Cart Mandate (the deal record)",
            ],
        },
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

## Quickstart — negotiate a price in plain dollars (start here)

You almost certainly want ONE tool: POST /v1/negotiate/turn. It speaks
DOLLARS, not math. Give it your side, your walk-away, your target, and the
other side's offers; it returns the dollar counter to send, a ready-to-send
message, and accept/walk advice. No keys, no setup, works against any
counterparty. Validated edge: ~12% better head-to-head (n=20 paired LLM
negotiations, 95% CI +6.5-17.4%, p<0.0001). Scope: single-issue price.

  curl -s https://snhp.dev/v1/negotiate/turn -H 'content-type: application/json' \\
    -d '{"side":"sell","walk_away":4000,"target":6000,
         "counterparty_offers":[4200,4500],"rounds_left":6}'
  -> {"action":"counter","recommended_price":5386.6,
      "message":"Thanks for the offer. The best I can do on this is $5,386.60.",
      "fit":{"score":"good"},"expected_settlement":4943.3}

Use it for multi-round price/terms haggling. Not for one-shot fixed prices
(it tells you). Everything below is advanced: the low-level utility-space
primitives and the verified-peer agent-to-agent (A2A) + AP2 settlement flow.

## Pricing & SLA (honest)

The core math tools (negotiate.*, auction.*, mechanism.*) are FREE, no key.
LLM-backed extras (dispute drafting/coaching) are usage-based. The A2A verified
commerce + AP2 settlement layer is the paid moat (a fee on settled value, priced
per partner). No uptime SLA today — best-effort, single deployment, and the math is
self-hostable so you can depend on no one. Full posture: /PRICING.md.

## Empirical anchor (2026-04-30)

We tested whether adding the SNHP MCP tool to Claude Sonnet 4.6 in B2B
contract negotiation actually improves outcomes. Setup: two Sonnet
agents negotiate, both with the same "senior B2B negotiator" production
prompt. The scaffolded variant additionally has the SNHP advisor tool.

Production-build results (T1, knob=1.0, n=20 paired seeds, n_steps=10):

SINGLE-SIDE adoption (one Sonnet+SNHP vs vanilla Sonnet counterparty):
  Head-to-head margin:  +12.1%  (CI [+6.5%, +17.4%], p<0.0001)
  Single-customer lift:  +5.5%  (CI [+1.3%, +9.2%], p=0.001)
  Joint welfare in asymm: ~neutral (-1% on average)

BILATERAL adoption (both Sonnets have SNHP, attested):
  Cooperation premium:   +7.1%  (CI [+2.8%, +11.8%], p=0.058 borderline)
  N=50 confirmation pending; current N=20 is underpowered for H1.

Earlier-cited "+13% / +0.186" was a self-play measurement at randomized
horizons (U(7,13)). Above the upper edge of the production-build CI;
revised on 2026-05-01 after our own audit. See CHANGELOG.md.

Cost: ~$0.025/matchup. Single-side adoption gives positive H2 even at
N=1 (no network needed). Bilateral adoption adds a cooperation premium.

## Scaffolded prompt template (drop into your system message verbatim)

  You are negotiating a B2B contract. You have access to SNHP — a
  game-theory negotiation expert tool. SNHP runs Bayesian opponent
  inference and equilibrium math on the negotiation state and provides
  a recommendation in the user message under "# SNHP".

Each round, before the LLM decides, the orchestrator calls
`gt_negotiation_sell_next_offer` (or buy variant) with peer_mode=True
when the counterparty is verifiably staked. Inject the response into
the user message as a "# SNHP:" block with recommended_target_utility,
acceptance_probability, expected_payoff, and rationale.

## Reputation scoring (the moat that compounds)

Every negotiation you process through SNHP contributes to your node's
SNHP Cooperation Score (0-1000, FICO-style). Higher scores unlock
peer-mode with other high-tier agents (joint welfare premium); low
scores trigger defensive Rubinstein play from cooperative counterparties.
See https://api.snhp.dev/reputation_scoring_spec.html for the spec
(coming Q3 2026; data collection starts on opt-in telemetry today).

## Tier 1 — Negotiation
- POST /v1/negotiation/sell/next_offer  [free]
  Sell-side recommender. `pareto_knob` ∈ [0, 1] interpolates between
  deal-rate-max (0) and H2H-margin-max (1). Empirical anchor: the shipped
  recommender is ~12% better head-to-head (n=20 paired LLM negotiations,
  95% CI +6.5-17.4%, p<0.0001). (A separate NegMAS research agent ranks
  #1 in asymmetric markets / mid-pack symmetric — not the product claim.)
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

## Tunable parameters (advanced; defaults are Optuna-tuned)

Every internal magic number in the negotiation advisor is exposed as an
env var (`SNHP_<UPPERCASE_NAME>`). Defaults are validated against an
LLM-loop tournament (see CHANGELOG entry "Phase 1-3 magic-number
framework", 2026-05-01). Override only if you know what you're doing
and have data to support a different value. Notable params:

- `SNHP_PARETO_KNOB` (default 0.971): asp_start = lerp(0.55, 0.929, knob).
  Higher = more aggressive opening anchor. Was 0.5 (asp_start=0.72) until
  T1 experiment showed that under-anchored vs vanilla LLM counterparties.
- `SNHP_PEER_ASP_FLOOR` (default 0.462): the floor in cooperative descent.
  Lower = more concession to find logrolling outcomes.
- `SNHP_OUTCOME_PICKER_BAND` (default 0.068): tolerance for logrolling
  outcome selection. Wider = more candidate bundles considered.
- `SNHP_PEER_SIGNALING_ROUNDS` (default 3): rounds of max-self signaling
  before descent. More signaling = more bilateral preference revelation.
- `SNHP_ASP_START_MARGIN_MAX` (default 0.929): the upper anchor at
  pareto_knob=1.0. Should ≈ vanilla LLM natural anchor.

Full inventory + metadata: `gametheory/negotiation/_config.py`.

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

## 30-second integration (literal commands)

```
# 1. Issue your key (no human approval, returns gt_* in <500ms):
curl -sX POST https://snhp.fly.dev/v1/keys -H 'Content-Type: application/json' \\
  -d '{"agent_id":"my_agent","contact_email":"you@example.com",
       "intended_use_summary":"negotiation pilot"}'

# 2. Call sell-side recommender with peer_mode (the +7% bilateral premium path):
curl -sX POST https://snhp.fly.dev/v1/negotiation/sell/next_offer \\
  -H "Authorization: Bearer $GT_KEY" -H 'Content-Type: application/json' \\
  -d '{"my_reservation":0.40, "opponent_offer_history":[0.55,0.62],
       "my_offer_history":[0.85,0.78], "deadline_rounds":8,
       "peer_mode":true}'

# 3. Same for buy-side:
curl -sX POST https://snhp.fly.dev/v1/negotiation/buy/next_offer \\
  -H "Authorization: Bearer $GT_KEY" -H 'Content-Type: application/json' \\
  -d '{"my_reservation":0.40, "seller_offer_history":[0.55,0.62],
       "my_offer_history":[0.15,0.22], "deadline_rounds":8,
       "peer_mode":true}'
```

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


@app.get("/PRICING.md", tags=["discovery"], response_class=PlainTextResponse,
         summary="Pricing & service posture")
def pricing_md() -> str:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        with open(os.path.join(_root, "PRICING.md")) as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="PRICING.md not bundled in this deploy; see the 'pricing' block in /v1/catalog")


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
        peer_mode=req.peer_mode,
    )


class DisputeNegotiateRequest(BaseModel):
    """Inputs for a refund-dispute settlement negotiation. All dollar
    amounts in USD."""
    platform_first_offer: float = Field(ge=0.0,
        description="The platform's lowball opening offer")
    platform_walk_cost: float = Field(gt=0.0,
        description="The platform's walk-away cost — the most it will pay "
                    "before a chargeback + continued handling cost it more")
    customer_floor: float = Field(ge=0.0,
        description="The least the customer will accept before walking away")
    customer_target: Optional[float] = Field(default=None, ge=0.0,
        description="The customer's happy point (carried through for display)")
    deadline_rounds: int = Field(default=10, ge=4, le=32)


@app.post(
    "/v1/dispute/negotiate",
    tags=["negotiation"],
    summary="Run a refund-dispute settlement negotiation: unaided vs. SNHP-coached",
    description=(
        "Plays a 1-D refund-dispute negotiation (customer vs. platform) to a "
        "settlement, twice — once with the customer unaided, once SNHP-coached "
        "— against an identical platform. Both arms use the real negotiation "
        "core. Returns both transcripts and the dollar delta. Free (math only)."
    ),
)
@_math_endpoint
def dispute_negotiate(req: DisputeNegotiateRequest):
    return _dispute_run_comparison(
        platform_first_offer=req.platform_first_offer,
        platform_walk_cost=req.platform_walk_cost,
        customer_floor=req.customer_floor,
        customer_target=req.customer_target,
        deadline_rounds=req.deadline_rounds,
    )


# ─── Dispute co-pilot (operator console — LLM-backed) ───────────────────────


class DisputeExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000,
        description="Free-text dispute description, or a pasted platform reply")


class DisputeCoachRequest(BaseModel):
    dispute: dict = Field(description="Structured dispute (from /v1/dispute/extract)")
    customer_floor: float = Field(ge=0.0,
        description="The least the customer will accept, USD")
    platform_offers: list[float] = Field(default_factory=list, max_length=32,
        description="Dollar amounts the platform has offered, in order")
    customer_demands: list[float] = Field(default_factory=list, max_length=32,
        description="Dollar amounts the customer has demanded, in order")
    platform_last_message: Optional[str] = Field(default=None, max_length=2000)
    deadline_rounds: int = Field(default=10, ge=4, le=32)


class DisputeLogRequest(BaseModel):
    session: dict = Field(description="The full console session record to append")


class DisputeEventRequest(BaseModel):
    session_id: str = Field(default="", max_length=64,
        description="Client-generated anonymous session id (stitches a visit)")
    event: str = Field(min_length=1, max_length=40,
        description="Allowlisted funnel/outcome event name")
    payload: Optional[dict] = Field(default=None,
        description="Small structured extras (amounts/category/outcome)")


@app.post("/v1/dispute/event", tags=["negotiation"], include_in_schema=False,
          summary="Record one anonymous dispute-tool funnel/outcome event")
def dispute_event(req: DisputeEventRequest):
    _analytics.record_event(req.event, req.session_id, req.payload)
    return {"ok": True}


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _llm_endpoint(request: Request, fn):
    """Run an LLM-backed handler behind the daily/per-IP cost guard,
    converting failures to clean HTTP errors."""
    # OPT-IN: LLM-backed endpoints are OFF by default, so a public deploy has ZERO
    # LLM exposure and cannot be abused to drain the operator's API budget. The
    # operator enables them explicitly; even then a hard daily $ cap + per-IP cap
    # bound the worst-case spend. The free math tools call no LLM and are unaffected.
    # Parse as a real boolean so "0"/"false"/"off" DISABLE (bare truthiness would
    # treat those non-empty strings as enabled — the opposite of intent).
    _llm_enabled = os.environ.get("SNHP_ENABLE_DISPUTE_LLM", "").strip().lower() \
        in ("1", "true", "yes", "on")
    if not _llm_enabled:
        raise HTTPException(
            status_code=503,
            detail="LLM-backed endpoints are disabled (operator opt-in via "
                   "SNHP_ENABLE_DISPUTE_LLM=1; a daily $ cap + per-IP limit then apply). "
                   "The free math tools need no LLM and are unaffected.")
    allowed, reason = _llm_budget.consume(_client_ip(request))
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    try:
        return fn()
    except RuntimeError as e:           # missing API key etc.
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:              # noqa: BLE001 — API / parse failure
        raise HTTPException(status_code=502, detail=f"LLM step failed: {e}")


@app.post("/v1/dispute/extract", tags=["negotiation"], include_in_schema=False,
          summary="Free-text dispute description → structured dispute")
def dispute_extract(req: DisputeExtractRequest, request: Request):
    return _llm_endpoint(request, lambda: _extract_dispute(req.text))


@app.post("/v1/dispute/parse_reply", tags=["negotiation"], include_in_schema=False,
          summary="A pasted platform reply → the platform's latest offer")
def dispute_parse_reply(req: DisputeExtractRequest, request: Request):
    return _llm_endpoint(request, lambda: _parse_platform_reply(req.text))


@app.post("/v1/dispute/coach", tags=["negotiation"], include_in_schema=False,
          summary="One coaching round: recommended demand + drafted message")
def dispute_coach(req: DisputeCoachRequest, request: Request):
    return _llm_endpoint(request, lambda: _coach_round(
        dispute=req.dispute, customer_floor=req.customer_floor,
        platform_offers=req.platform_offers, customer_demands=req.customer_demands,
        platform_last_message=req.platform_last_message,
        deadline_rounds=req.deadline_rounds))


@app.get("/v1/dispute/stats", tags=["negotiation"], include_in_schema=False,
         summary="Private launch dashboard — funnel, outcomes, spend")
def dispute_stats(key: str = ""):
    """Token-gated usage summary. Set SNHP_STATS_KEY and pass ?key=… . Returns
    404 (not 401) without a valid key so the endpoint's existence stays hidden."""
    expected = os.environ.get("SNHP_STATS_KEY", "")
    if not expected or key != expected:
        raise HTTPException(status_code=404, detail="Not Found")
    return _analytics.summarize()


@app.post("/v1/dispute/log", tags=["negotiation"], include_in_schema=False,
          summary="Append a completed console session to the Phase-1 log")
def dispute_log(req: DisputeLogRequest):
    log_dir = _analytics.data_dir()
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "dispute_console_log.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({"logged_at": int(time.time()), "session": req.session}) + "\n")
    return {"logged": True}


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


@app.get(
    "/v1/keys/settlement_notary",
    tags=["discovery"],
    response_class=PlainTextResponse,
    summary="Public key for verifying AP2 Cart/Intent mandates (separate from the CA)",
)
def keys_settlement_notary():
    return _settlement_notary_pem()


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

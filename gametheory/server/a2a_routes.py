"""
A2A agent-to-agent commerce routes — discovery, verified peering, and settlement.

Mounted into the main app (gametheory/server/http.py) via include_router. Closes
the discovery / standards-integration gaps by publishing a Google A2A Agent Card
that advertises the SNHP negotiation extension, and exposes the verified-peer
handshake + AP2 settlement as real endpoints.

Endpoints:
  GET  /.well-known/agent-card.json     A2A discovery (advertises SNHP extension)
  POST /v1/registry/register_operator   identity: pubkey -> signed attestation
  POST /v1/a2a/open_session             verify both peers -> server-derived peer_mode
  POST /v1/a2a/next_offer               offer using the SESSION's peer_mode (not a
                                        client-asserted boolean) — the #1 fix
  POST /v1/a2a/settle                   emit AP2 Intent/Cart mandates for the deal
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from gametheory.server.middleware import bearer_api_key as _bearer_api_key
from gametheory.negotiation.sell import sell_next_offer as _sell_next_offer
from gametheory.negotiation.buy import buy_next_offer as _buy_next_offer
from gametheory.negotiation.plain_terms import (
    negotiate_turn as _negotiate_turn, NegotiationInputError as _NegInputError,
)
from gametheory.negotiation.bundle import (
    negotiate_bundle as _negotiate_bundle, BundleInputError as _BundleInputError,
)
from gametheory.crypto.first_strike import (
    trust_anchor_public_key_pem, settlement_notary_public_key_pem,
)
from gametheory.server import registry as _registry
from gametheory.server import peering as _peering
from gametheory.server import settlement as _settlement

router = APIRouter()

SNHP_A2A_EXTENSION_URI = "https://snhp.dev/a2a/negotiation/v1"

# The paid/free boundary, stated as DATA on the free turn (not a nag): one
# honest sentence naming what the $2 NEXTMOVE session adds and what free lacks.
_PAID_ALTERNATIVE_NOTE = (
    "This free turn is unreceipted and non-deterministic; the $2 NEXTMOVE "
    "session adds deterministic replay, signed receipts, and persistent "
    "session state."
)


def _log_free_taste(api_key: str | None) -> None:
    """Best-effort funnel telemetry for the free turn (keyed free usage is the
    top of free->paid conversion). vend is optional (not in the PyPI wheel), so
    the import is lazy and any failure is swallowed — never break the request."""
    try:
        from vend import telemetry as _vt
        _vt.log_free_taste(api_key, "http")
    except Exception:
        pass


# Public base URL the deployed server is reachable at — registries and remote
# agents need ABSOLUTE endpoints. Override per deploy: SNHP_PUBLIC_BASE_URL.
def _base_url() -> str:
    return os.environ.get("SNHP_PUBLIC_BASE_URL", "https://snhp.dev").rstrip("/")


# ─── Discovery: MCP server card (SEP-1649) ───────────────────────────────────
def _mcp_tools_for_card() -> list[dict]:
    """Full tool definitions (name, description, inputSchema) — the same shape an
    MCP tools/list returns — so a registry can skip the live scan and still get the
    real toolset. Lazy import + defensive: a card is better than a 500."""
    try:
        from gametheory.server.mcp_server import mcp as _mcp
        out = []
        for t in _mcp._tool_manager.list_tools():
            schema = getattr(t, "parameters", None) or {"type": "object", "properties": {}}
            if "type" not in schema:
                schema = {"type": "object", **schema}
            out.append({"name": t.name,
                        "description": (t.description or "").strip(),
                        "inputSchema": schema})
        return out
    except Exception:
        return []


@router.get("/.well-known/mcp/server-card.json", tags=["discovery"],
            summary="MCP server card (SEP-1649 — lets registries skip a live scan)")
def mcp_server_card() -> dict:
    """Static MCP server card in the SEP-1649 shape (serverInfo + tools/resources/
    prompts + authentication) so Smithery/registries index the hosted
    streamable-HTTP server WITHOUT a live initialize scan (which can 502 on a cold
    start, and which some scanners can't complete through the /mcp -> /mcp/
    redirect). Generated from the live tool definitions so it never drifts.

    This card describes the CORE door only: `_mcp_tools_for_card()` enumerates the
    live `mcp` instance's tool manager, so it auto-slims to the 15 hero-first core
    tools (no hand-maintained list to drift). The full/legacy surface is pointed
    at via `transport_pro` (/mcp/pro/)."""
    base = _base_url()
    try:
        from gametheory.server.mcp_server import mcp as _mcp
        server_name = getattr(_mcp, "name", None) or "snhp"
    except Exception:
        server_name = "snhp"
    return {
        # SEP-1649 fields Smithery parses:
        "serverInfo": {"name": server_name, "version": "0.1.0"},
        "capabilities": {"tools": {"listChanged": False}},
        "authentication": {"required": False, "schemes": []},
        "tools": _mcp_tools_for_card(),
        "resources": [],
        "prompts": [],
        # Extra human/registry metadata (ignored by the SEP-1649 parser):
        "name": "io.github.ryuxik/snhp-negotiation",
        "description": (
            "Free math-optimal negotiation for AI agents — your next move in any "
            "price negotiation, plus multi-issue logrolling, auctions and matching; "
            "no account, no key. When you need it: persistent agent memory (blind "
            "custody) and $2 receipted negotiation sessions. LLM-free. This card "
            "lists the CORE door (15 hero-first tools); the full/legacy surface "
            "(old names, A2A verified-peer flow, first-strike attestation) is at "
            "/mcp/pro/."
        ),
        "homepage": base,
        "repository": "https://github.com/ryuxik/snhp",
        "transport": {"type": "streamable-http", "url": base + "/mcp/"},
        "transport_pro": {
            "type": "streamable-http", "url": base + "/mcp/pro/",
            "description": ("Full surface incl. legacy names and advanced flows "
                            "(A2A verified-peer, first-strike attestation, auction "
                            "design/sim, pondering sessions)."),
        },
    }


# ─── Discovery: A2A Agent Card ───────────────────────────────────────────────

@router.get("/.well-known/agent-card.json", tags=["discovery"],
            include_in_schema=True, summary="A2A Agent Card (advertises SNHP extension)")
def agent_card() -> dict:
    """Google A2A Agent Card. The `capabilities.extensions` entry tells any A2A
    client that this agent speaks the SNHP verified-negotiation protocol, so two
    SNHP agents can discover each other and opt in."""
    base = _base_url()
    return {
        "protocolVersion": "0.3.0",
        "name": "Negotiation Copilot for Agents (SNHP)",
        "description": "Get the math-optimal next move in a single-price "
                       "negotiation, in plain dollars. Tell it your walk-away and "
                       "the other side's offers; it returns the counter-offer to "
                       "send, a ready-made message, and when to accept or walk. "
                       "Validated ~12% better head-to-head (n=20 paired LLM "
                       "negotiations, 95% CI +6.5-17.4%, p<0.0001). Any counterparty.",
        "url": base,
        "version": "0.1.0",
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extensions": [
                {
                    "uri": SNHP_A2A_EXTENSION_URI,
                    "description": "Advanced: when BOTH agents run SNHP, prove who you "
                                   "both are to unlock a cooperation premium (more joint "
                                   "surplus between verified peers) and a signed, "
                                   "settleable AP2 deal record. Optional — the core "
                                   "/v1/negotiate/turn tool needs none of this. Follow "
                                   "`flow` in order; full guide: gametheory/server/A2A_FLOW.md.",
                    "required": False,
                    "flow": [
                        {"step": 0, "do": "register_operator (each side, once)",
                         "endpoint": base + "/v1/registry/register_operator",
                         "note": "optional domain upgrade: request_domain_challenge -> verify_domain"},
                        {"step": 1, "do": "build a peer proof LOCALLY (key never leaves your host)",
                         "endpoint": "local / MCP gt_a2a_build_peer_proof"},
                        {"step": 2, "do": "exchange proofs with the counterparty",
                         "endpoint": "your channel / an A2A message Part"},
                        {"step": 3, "do": "open_session with both proofs -> server-derived peer_mode",
                         "endpoint": base + "/v1/a2a/open_session"},
                        {"step": 4, "do": "next_offer using the session's peer_mode",
                         "endpoint": base + "/v1/a2a/next_offer"},
                        {"step": 5, "do": "settle -> signed AP2 Cart Mandate",
                         "endpoint": base + "/v1/a2a/settle"},
                    ],
                    "params": {
                        "register_operator": base + "/v1/registry/register_operator",
                        "request_domain_challenge": base + "/v1/registry/request_domain_challenge",
                        "verify_domain": base + "/v1/registry/verify_domain",
                        "open_session": base + "/v1/a2a/open_session",
                        "next_offer": base + "/v1/a2a/next_offer",
                        "settle": base + "/v1/a2a/settle",
                        "trust_anchor_public_key_pem": trust_anchor_public_key_pem(),
                        "settlement_notary_public_key_pem": settlement_notary_public_key_pem(),
                    },
                }
            ],
        },
        "skills": [
            {"id": "negotiate_turn", "name": "Price negotiation (plain dollars)",
             "description": "Use when haggling over a price across multiple rounds. "
                            "Input your side, walk-away $, target $, and the other "
                            "side's offers in $; get back the dollar counter to send, "
                            "a message, and accept/walk advice. Don't use for one-shot "
                            "fixed prices or non-price decisions; for multi-issue deals "
                            "use the negotiate_bundle skill. "
                            "Endpoint: " + base + "/v1/negotiate/turn. "
                            "Example: sell, walk_away=4000, target=6000, "
                            "counterparty_offers=[4200,4500] -> counter ~$5,387.",
             "tags": ["negotiation", "bargaining", "pricing", "haggling", "deals"]},
            {"id": "negotiate_bundle", "name": "Multi-issue negotiation (logrolling)",
             "description": "Use when a deal has several linked issues at once (a job "
                            "offer = base + equity + signing; a SaaS contract = price + "
                            "seats + term + SLA). Give your and their per-option values "
                            "per issue; it infers their priorities from their offers and "
                            "returns the package to propose — conceding on issues you "
                            "value less to win the ones you value most. Endpoint: "
                            + base + "/v1/negotiate/bundle.",
             "tags": ["negotiation", "multi-issue", "logrolling", "contract", "bundle"]},
            {"id": "settle", "name": "AP2 settlement (advanced)",
             "description": "Emit signed AP2 Intent/Cart mandates for an agreed deal "
                            "between two verified SNHP agents.",
             "tags": ["payments", "ap2"]},
        ],
    }


# ─── Discovery: agents.json capability manifest ──────────────────────────────

@router.get("/.well-known/agents.json", tags=["discovery"], include_in_schema=True,
            summary="Machine-readable agent-capability manifest for the SNHP store")
def agents_json() -> dict:
    """A self-describing manifest of what this counter offers and how an agent
    pays for it: name, free_tools[], capabilities[], endpoints, auth, payment,
    demand box. Free-first (RESHAPE.md §4): the free negotiation / auction /
    matching math leads; the paid counter (agent memory, then the $2 receipted
    session) follows; wallet + fee sit under structured keys, never the headline.
    Written in the vocabulary an agent's tool-selector needs ('your next move in
    any price negotiation', 'remember something across sessions'). Pure READ, no
    auth, no key material. The fee is read from the billing constants so it can
    never drift from what a top-up actually charges. Honest: only the two LIVE
    paid slots are listed (no page-fetch slot exists today)."""
    base = _base_url()
    # Lazy import: the fee is the single source of truth (billing constants), so
    # the manifest and a real top-up can never disagree.
    from gametheory.server import billing as _billing, onboarding as _onboarding
    starter_usd = f"{_onboarding.STARTER_GRANT_MILLICENTS / (100 * _onboarding.MILLICENTS_PER_CENT):.2f}"
    return {
        "schema": "agents.json/v0",
        "name": "SNHP — free negotiation math + agent memory",
        "description": (
            "Free math-optimal negotiation for AI agents — your next move in any "
            "price negotiation, plus multi-issue logrolling, auctions and matching; "
            "no account, no key. When you need it, a paid counter adds persistent "
            "AGENT MEMORY (blind custody — you encrypt before saving; we store only "
            "ciphertext and cannot read it) and a $2 RECEIPTED negotiation SESSION "
            "(deterministic, replayable, signed). One prepaid wallet per key, a "
            "one-time 50¢ starter credit, settle-on-delivery (you cannot pay for "
            "nothing), Ed25519-signed receipts verifiable offline. LLM-free in "
            "every judgment path."
        ),
        "homepage": base,
        "repository": "https://github.com/ryuxik/snhp",
        "endpoints": {
            "http_base": base,
            "mcp": base + "/mcp/",
            "mcp_pro": base + "/mcp/pro/",
            "mcp_server_card": base + "/.well-known/mcp/server-card.json",
            "agent_card": base + "/.well-known/agent-card.json",
            "openapi": base + "/openapi.json",
            "llms_txt": base + "/llms.txt",
            "llms_full_txt": base + "/llms-full.txt",
            "catalog": base + "/v1/store/catalog",
            "observatory": base + "/v1/store/observatory",
        },
        "auth": {
            "type": "api_key",
            "issue": {"method": "POST", "path": "/v1/keys",
                      "human_required": False, "card_required": False},
            "header": "Authorization: Bearer gt_* (or X-API-Key: gt_*)",
            "starter_credit": {"amount_usd": starter_usd, "one_time": True,
                               "unconditional": True, "card_required": False},
        },
        # Free-first: the free core math leads. The full/legacy surface (all 43
        # tools incl. the old gt_* names, A2A verified-peer flow, first-strike
        # attestation, auction design/sim) is on the PRO door /mcp/pro/.
        "free_tools": [
            {"id": "negotiate", "need": "your next move in any price negotiation",
             "endpoint": {"method": "POST", "path": "/v1/negotiate/turn"},
             "mcp_tool": "negotiate"},
            {"id": "negotiate_bundle", "need": "logroll a multi-issue deal",
             "endpoint": {"method": "POST", "path": "/v1/negotiate/bundle"},
             "mcp_tool": "negotiate_bundle"},
            {"id": "auction_bid", "need": "the optimal bid when bidding in an auction",
             "endpoint": {"method": "POST", "path": "/v1/auction/bidder/optimal_bid"},
             "mcp_tool": "auction_bid"},
            {"id": "auction_reserve", "need": "the revenue-optimal reserve when selling",
             "endpoint": {"method": "POST", "path": "/v1/auction/seller/optimal_reserve"},
             "mcp_tool": "auction_reserve"},
            {"id": "clearance_price", "need": "clear stock by a deadline (price + markdowns)",
             "endpoint": {"method": "POST", "path": "/v1/mechanism/posted_price_optimal"},
             "mcp_tool": "clearance_price"},
            {"id": "stable_match", "need": "match two groups so no pair wants to swap",
             "endpoint": {"method": "POST", "path": "/v1/mechanism/gale_shapley"},
             "mcp_tool": "stable_match"},
            {"id": "score_deal", "need": "score a deal against your floor/target",
             "mcp_tool": "score_deal"},
            {"id": "catalog", "need": "see what this counter sells and how to pay",
             "endpoint": {"method": "GET", "path": "/v1/store/catalog"}},
        ],
        "free_tools_door": base + "/mcp/",
        "pro_door": {
            "url": base + "/mcp/pro/",
            "note": ("full/legacy surface: all 43 tools incl. old gt_* names, "
                     "A2A verified-peer flow, first-strike attestation, auction "
                     "design/sim, pondering sessions"),
        },
        "wallet": {
            "unit": "millicent",
            "millicents_per_cent": _onboarding.MILLICENTS_PER_CENT,
            "balance": {"method": "GET", "path": "/v1/billing/balance"},
            "refundable": False,
        },
        # The two LIVE paid slots, memory first then the receipted session (paid
        # is always the SECOND thing, never the headline).
        "capabilities": [
            {
                "id": "agent_memory",
                "need": "remember something across sessions",
                "title": "Agent memory — persistent across sessions (blind custody)",
                "description": (
                    "Persistent memory for your agent: save now, load in any later "
                    "session. You encrypt BEFORE saving; we store only ciphertext "
                    "(blind custody — keys never transit, contents never logged) "
                    "and sign a receipt over its hash, so we cannot read your "
                    "memory. Save is paid (thin flat fee, settle-on-durable-store; "
                    "the 50¢ starter credit covers your first saves); load is free. "
                    "A wrong owner reads as a missing ticket."),
                "price": {"model": "flat_save_fee"},
                "endpoints": {
                    "save": {"method": "POST", "path": "/v1/store/park"},
                    "load": {"method": "GET", "path": "/v1/store/parcel/{ticket}"},
                },
                "mcp_tools": ["memory_save", "memory_load"],
            },
            {
                "id": "negotiate_session",
                "need": "negotiate a price",
                "title": "Receipted negotiation session (tuned, deterministic, replayable)",
                "description": (
                    "$2 once covers the WHOLE negotiation (cap 10 moves, 7 days): "
                    "category-tuned, deterministic replay, signed receipts, "
                    "persistent session state. The paid upgrade of the free "
                    "negotiate tool."),
                "price": {"amount_usd": "2.00", "model": "per_session"},
                "endpoints": {
                    "open": {"method": "POST", "path": "/v1/advice/session"},
                    "move": {"method": "POST", "path": "/v1/advice/move"},
                    "bundle": {"method": "POST", "path": "/v1/advice/bundle"},
                    "close": {"method": "POST", "path": "/v1/advice/close"},
                },
                "mcp_tools": ["session_open", "session_advise",
                              "session_bundle", "session_close"],
            },
        ],
        "payment": {
            "settlement": "on_delivery",
            "settlement_note": (
                "a paid call settles only when a machine-checkable outcome is "
                "delivered; a failure is an uncharged 200 {ok:false, "
                "charged:false} — you cannot pay for nothing"),
            "receipts": {"signature": "ed25519", "verifiable_offline": True,
                         "pin_signer": "/v1/store/notary_pubkey"},
            "fee": {"model": "counter_fee_on_topups",
                    "percent": _billing.COUNTER_FEE_PCT,
                    "fixed_cents": _billing.COUNTER_FEE_FIXED_CENTS,
                    "applies_to": "wallet top-ups only, never the calls"},
            "methods": [
                {"id": "stripe_checkout", "human_required": True,
                 "endpoint": {"method": "POST",
                              "path": "/v1/billing/checkout_session"},
                 "description": "human-clickable Stripe Checkout top-up"},
                {"id": "mpp_spt", "human_required": False,
                 "endpoint": {"method": "POST", "path": "/v1/mpp/topup"},
                 "manifest": "/v1/mpp/manifest",
                 "reference_client": "vend/mpp_client.py",
                 "rail": "fiat", "crypto_accepted": False,
                 "description": (
                     "agent-native: pay per invocation with a Stripe Shared "
                     "Payment Token, no human; GET the manifest for the "
                     "402 -> authorize -> retry -> receipt flow")},
            ],
        },
        "demand_box": {
            "description": "ask for what's not stocked; unmet demand decides the "
                           "next slot",
            "file": {"method": "POST", "path": "/v1/store/request"},
            "public_tally": {"method": "GET", "path": "/v1/store/requests"},
            "observatory": {"method": "GET", "path": "/v1/store/observatory"},
        },
    }


# ─── Flagship: plain-terms negotiation (the tool agents should reach for) ────

class NegotiateTurnRequest(BaseModel):
    side: Literal["sell", "buy"] = Field(..., description="Which side you are")
    walk_away: float = Field(..., description="Your reservation in dollars: the WORST "
                             "price you'd accept (seller=floor, buyer=ceiling)")
    target: float = Field(..., description="Your aspiration in dollars (seller=high, buyer=low)")
    counterparty_offers: list[float] = Field(default_factory=list,
        description="The other side's offers so far, in dollars, oldest first")
    my_previous_offers: list[float] = Field(default_factory=list)
    rounds_left: int = Field(default=8, ge=1,
        description="Roughly how many more back-and-forths before it times out")
    item: str = Field(default="this", description="What's being traded (for the message)")


@router.post("/v1/negotiate/turn", tags=["negotiation"],
             summary="Plain-terms negotiation: dollars in, a dollar counter + message out")
def negotiate_turn_endpoint(req: NegotiateTurnRequest, request: Request) -> dict:
    """Get the math-optimal next move in a price negotiation, entirely in dollars —
    no game theory required. Example: selling a contract, floor $4,000, hope $6,000,
    the buyer has bid $4,200 then $4,500 → returns a ~$5,387 counter with a
    ready-to-send message, and tells you when to accept or walk.

    FREE. Rate limits: keyless callers share the 60/min-per-IP floor; send your
    key in `Authorization: Bearer gt_*` (or `X-API-Key: gt_*`) to get the
    600/min-per-key lane. A key in the request BODY does not raise the limit —
    the limiter only reads headers. The response carries a `paid_alternative`
    note: this free turn is unreceipted and non-deterministic (see the $2
    NEXTMOVE session for deterministic replay + signed receipts + session state)."""
    try:
        result = _negotiate_turn(
            side=req.side, walk_away=req.walk_away, target=req.target,
            counterparty_offers=req.counterparty_offers,
            my_previous_offers=req.my_previous_offers,
            rounds_left=req.rounds_left, item=req.item)
    except _NegInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Top of the free->paid funnel: log the taste (keyed usage is measurable),
    # and hand the caller the honest paid/free boundary as data, not a nag.
    _log_free_taste(_bearer_api_key(request))
    result["paid_alternative"] = _PAID_ALTERNATIVE_NOTE
    return result


# ─── Flagship (multi-issue): logrolling over several linked issues ───────────

class BundleIssue(BaseModel):
    name: str = Field(..., description="Issue name, e.g. 'price' or 'base_salary'")
    options: list = Field(..., description="The choices on this issue, e.g. ['$50','$40','$30']")
    my_utility: list[float] = Field(..., description="How good each option is to YOU "
                                    "(one number per option, any scale)")
    their_utility: list[float] = Field(..., description="How good each option is to THEM "
                                       "(their preference direction; one per option)")


class NegotiateBundleRequest(BaseModel):
    issues: list[BundleIssue] = Field(..., description="The issues on the table (2+ for "
                                      "logrolling), each with your and their per-option values")
    their_offers: list[dict] = Field(default_factory=list,
        description="The other side's offers so far as {issue_name: option}, oldest first")
    my_priorities: Optional[dict] = Field(default=None,
        description="Optional {issue_name: weight} — how much each issue matters to you")
    my_batna: float = Field(default=0.40, ge=0.0, le=1.0)
    their_batna_estimate: float = Field(default=0.40, ge=0.0, le=1.0)
    rounds_left: Optional[int] = Field(default=None, ge=1,
        description="Optional bargaining rounds remaining. On the LAST round (<=1) a "
                    "standing offer that clears your BATNA is accepted rather than "
                    "countered into no-deal. Omit for timeless behavior.")


def _bundle_seed(*parts) -> int:
    """Deterministic seed from the bundle call's inputs — identical requests map to
    the identical seed, so identical calls return identical advice. Passed
    STRUCTURALLY as negotiate_bundle(seed=...), never mutating the global RNG, so
    concurrent requests can't perturb each other's inference (P10 Fix 2)."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return int.from_bytes(hashlib.blake2b(blob, digest_size=8).digest(), "big") & 0x7FFFFFFF


@router.post("/v1/negotiate/bundle", tags=["negotiation"],
             summary="Multi-issue negotiation: logroll across several linked issues")
def negotiate_bundle_endpoint(req: NegotiateBundleRequest) -> dict:
    """Recommend a multi-issue PACKAGE by logrolling — concede on the issues you care
    about less (and the other side cares about more) to win the ones you care about
    most. Infers the counterparty's per-issue priorities from their offers. Example: a
    SaaS contract over price/seats/term/SLA → proposes a full package and explains the
    trade. Use gt.negotiate.turn instead when there's only ONE issue (a price).

    Deterministic: identical requests return identical advice (the inference cloud is
    seeded from the inputs, not global RNG)."""
    issues = [i.model_dump() for i in req.issues]
    try:
        return _negotiate_bundle(
            issues=issues,
            their_offers=req.their_offers,
            my_priorities=req.my_priorities,
            my_batna=req.my_batna,
            their_batna_estimate=req.their_batna_estimate,
            rounds_left=req.rounds_left,
            seed=_bundle_seed(issues, req.their_offers, req.my_priorities,
                              req.my_batna, req.their_batna_estimate),
        )
    except _BundleInputError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Identity: operator registration ─────────────────────────────────────────

class RegisterOperatorRequest(BaseModel):
    operator_id: str = Field(..., description="Stable operator identity (e.g. a domain or org id)")
    public_key_b64: str = Field(..., description="Base64 of the 32-byte Ed25519 operator public key")
    display_name: Optional[str] = Field(default=None)


@router.post("/v1/registry/register_operator", tags=["discovery"],
             summary="Register an operator identity (self-attested), get a signed attestation")
def register_operator(req: RegisterOperatorRequest) -> dict:
    try:
        return _registry.register_operator(
            req.operator_id, req.public_key_b64, req.display_name)
    except _registry.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DomainChallengeRequest(BaseModel):
    domain: str = Field(..., description="Bare hostname you control, e.g. acme.example")
    public_key_b64: str


@router.post("/v1/registry/request_domain_challenge", tags=["discovery"],
             summary="Get the DNS-TXT record to publish to prove domain control")
def request_domain_challenge(req: DomainChallengeRequest) -> dict:
    try:
        return _registry.request_domain_challenge(req.domain, req.public_key_b64)
    except _registry.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))


class VerifyDomainRequest(BaseModel):
    domain: str
    public_key_b64: str
    display_name: Optional[str] = None


@router.post("/v1/registry/verify_domain", tags=["discovery"],
             summary="Verify the DNS-TXT challenge and register as domain-verified")
def verify_domain(req: VerifyDomainRequest) -> dict:
    try:
        return _registry.verify_domain_and_register(
            req.domain, req.public_key_b64, req.display_name)
    except _registry.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Verified peering: open a session ────────────────────────────────────────

class PeerProof(BaseModel):
    operator_attestation_jwt: str
    sig_b64: str
    # role + expires_at bind the proof to a role and a deadline (anti-replay).
    # Optional so a malformed/forged proof still parses and is rejected by the
    # verification logic (returning peer_mode=False) rather than a 422.
    role: Optional[str] = None
    expires_at: Optional[int] = None


class OpenSessionRequest(BaseModel):
    negotiation_id: str = Field(..., description="Shared id both agents agree on (e.g. the A2A task id)")
    seller_proof: PeerProof
    buyer_proof: PeerProof
    require_level: Literal["self", "domain"] = Field(
        default="self", description="Minimum counterparty verification level for peer_mode")


@router.post("/v1/a2a/open_session", tags=["negotiation"],
             summary="Verify both peers and derive peer_mode server-side")
def open_session(req: OpenSessionRequest) -> dict:
    return _peering.open_session(
        negotiation_id=req.negotiation_id,
        seller_proof=req.seller_proof.model_dump(),
        buyer_proof=req.buyer_proof.model_dump(),
        require_level=req.require_level,
    )


# ─── Negotiation: next offer (peer_mode comes from the session) ──────────────

class NextOfferRequest(BaseModel):
    session_id: str = Field(..., description="From /v1/a2a/open_session")
    role: Literal["seller", "buyer"]
    my_reservation: float = Field(..., ge=0.0, le=1.0,
        description="Your reservation in NORMALIZED utility [0,1]")
    opponent_offer_history: list[float] = Field(default_factory=list, max_length=256)
    my_offer_history: list[float] = Field(default_factory=list, max_length=256)
    deadline_rounds: int = Field(default=10, ge=1, le=1000)
    pareto_knob: float = Field(default=0.5, ge=0.0, le=1.0)
    prior: Optional[dict] = Field(default=None, description="WTP/market prior")


@router.post("/v1/a2a/next_offer", tags=["negotiation"],
             summary="Offer recommendation using the SESSION's verified peer_mode")
def next_offer(req: NextOfferRequest) -> dict:
    session = _peering.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    peer_mode = session["peer_mode"]   # server-authoritative; not client-asserted

    if req.role == "seller":
        rec = _sell_next_offer(
            my_reservation=req.my_reservation,
            opponent_offer_history=req.opponent_offer_history,
            my_offer_history=req.my_offer_history,
            deadline_rounds=req.deadline_rounds,
            pareto_knob=req.pareto_knob,
            buyer_wtp_prior=req.prior,
            peer_mode=peer_mode,
        )
    else:
        rec = _buy_next_offer(
            my_reservation=req.my_reservation,
            seller_offer_history=req.opponent_offer_history,
            my_offer_history=req.my_offer_history,
            deadline_rounds=req.deadline_rounds,
            pareto_knob=req.pareto_knob,
            market_prior=req.prior,
            peer_mode=peer_mode,
        )
    return {"session_id": req.session_id, "peer_mode": peer_mode,
            "role": req.role, "recommendation": rec}


# ─── Settlement: AP2 mandates ────────────────────────────────────────────────

class SettleRequest(BaseModel):
    session_id: str
    agreed_price: float
    currency: str = "USD"
    item: Optional[str] = None
    buyer_max_price: Optional[float] = Field(
        default=None, description="If set, also emit the buyer's Intent Mandate")
    terms: Optional[dict] = None


@router.post("/v1/a2a/settle", tags=["negotiation"],
             summary="Emit signed AP2 Intent/Cart mandates for the agreed deal")
def settle(req: SettleRequest) -> dict:
    session = _peering.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    # A signed Cart Mandate is a non-repudiable record naming both parties — only
    # issue it when both are verified (identified) and distinct. peer_mode is the
    # server-authoritative flag for exactly that. Gate on it directly: a session
    # opened with a revoked, below-level, or bad-signature proof still populates
    # the operator fields (operator_id is known before those checks fail) but
    # leaves peer_mode False, so a non-null/distinct check alone would wrongly
    # mint a Cart Mandate for an UNVERIFIED deal.
    if not session["peer_mode"]:
        if (session["seller_operator"]
                and session["seller_operator"] == session["buyer_operator"]):
            raise HTTPException(status_code=409,
                                detail="settlement requires distinct counterparties")
        raise HTTPException(
            status_code=409,
            detail="settlement requires both parties verified; open the session "
                   "with valid, unrevoked, sufficiently-verified seller and buyer "
                   "proofs first")
    out = {
        "cart_mandate": _settlement.emit_cart_mandate(
            session_id=req.session_id,
            negotiation_id=session["negotiation_id"],
            seller_operator=session["seller_operator"],
            buyer_operator=session["buyer_operator"],
            agreed_price=req.agreed_price, currency=req.currency,
            item=req.item, terms=req.terms,
        )
    }
    if req.buyer_max_price is not None:
        out["intent_mandate"] = _settlement.emit_intent_mandate(
            negotiation_id=session["negotiation_id"],
            buyer_operator=session["buyer_operator"],
            max_price=req.buyer_max_price, currency=req.currency, item=req.item,
        )
    return out

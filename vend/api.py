"""snhp-price/1 over HTTP — the price-link endpoints (VEND P3).

A demo machine lives in-process (seeded, stocked, its clock mapped to wall
time). Quotes hold stock until TTL; settle is idempotent. All math, no LLM
calls — same abuse posture as the rest of the API surface.

  POST /v1/vend/quote            intent (+optional buyer disclosure) → Quote
  POST /v1/vend/settle/{id}      idempotent; 410 after TTL
  GET  /v1/vend/machine          public board (list prices, stock bands)
"""
from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/vend", tags=["vend"])

QUOTE_TTL_S = 120
_DEMO = None
_QUOTES: dict[str, dict] = {}


def _machine():
    """The in-process demo machine; tick follows the wall clock."""
    global _DEMO
    if _DEMO is None:
        from vend.world import WorldConfig, build_catalog, fresh_machine
        cfg = WorldConfig(sigma_cal=0.3, glut_prob=0.5)
        cat = build_catalog(cfg, master_seed=20260713)
        _DEMO = fresh_machine("demo-01", cat, cfg, master_seed=20260713)
    now = datetime.now()
    _DEMO.tick = max(0, min(95, (now.hour - 7) * 6 + now.minute // 10))
    return _DEMO


class BuyerBlock(BaseModel):
    disclosure: dict = Field(..., description="{'utilities': {sku: $}, 'walk_cost': $}")
    peer_proof: dict | None = None


class Intent(BaseModel):
    sku: str
    quantity: int = Field(1, ge=1, le=3)
    substitutes_ok: bool = True
    buyer: BuyerBlock | None = None


class QuoteReq(BaseModel):
    protocol: str = "snhp-price/1"
    machine_id: str = "demo-01"
    intent: Intent


@router.get("/machine")
def machine_board():
    state = _machine()
    return {"machine_id": state.machine_id, "protocol": "snhp-price/1",
            "board": {sku: {"list_price": l.list_price,
                            "stock": state.stock(sku),
                            "expires_in_days": state.days_to_expiry(sku)}
                      for sku, l in state.listings.items()}}


@router.post("/quote")
def quote(req: QuoteReq):
    from vend.core import QuoteItem, make_quote, substream
    from vend.scenario import nash_quote
    from vend.world import hour_of

    state = _machine()
    it = req.intent
    if it.sku not in state.listings:
        raise HTTPException(404, f"unknown sku {it.sku!r}")

    if it.buyer is None:
        # one-sided: the sticker (this demo's posted policy is the board)
        listing = state.listings[it.sku]
        if state.stock(it.sku) < it.quantity:
            raise HTTPException(409, "insufficient stock")
        items = [QuoteItem(it.sku, it.quantity, listing.list_price,
                           listing.list_price)]
        why, attested = ["list price"], None
    else:
        utils = it.buyer.disclosure.get("utilities") or {}
        wtp = {s: float(utils.get(s, 0.0)) for s in state.listings}
        walk = float(it.buyer.disclosure.get("walk_cost", 1.0))
        nq = nash_quote(state, wtp, walk)
        if nq.outcome is None:
            return {"no_deal": True,
                    "reason": "no outcome beats both sides' alternatives",
                    "board_url": "/v1/vend/machine"}
        o = nq.outcome
        items = [QuoteItem(o.sku, o.qty, o.unit_price,
                           state.listings[o.sku].list_price)]
        why = nq.why
        # honesty: unverified disclosures are quoted but labeled — verified
        # peering (gt_a2a_* flow) is what makes truth-telling an equilibrium
        attested = bool(it.buyer.peer_proof)

    q = make_quote(state, "vend-api/1",
                   seed=substream(20260713, "api", int(time.time())),
                   items=items, why=list(why), hour=hour_of(state.tick))
    _QUOTES[q.quote_id] = {"items": items, "expires": time.time() + QUOTE_TTL_S,
                           "settled": False}
    return {"quote_id": q.quote_id, "protocol": q.protocol,
            "items": [vars(i) for i in q.items], "total": q.total,
            "why": list(q.why), "context_hash": q.context_hash,
            "attested_disclosure": attested,
            "expires_in_seconds": QUOTE_TTL_S,
            "settle_url": f"/v1/vend/settle/{q.quote_id}"}


@router.post("/settle/{quote_id}")
def settle(quote_id: str):
    rec = _QUOTES.get(quote_id)
    if rec is None:
        raise HTTPException(404, "unknown quote")
    if rec["settled"]:
        return {"quote_id": quote_id, "status": "settled", "idempotent": True}
    if time.time() > rec["expires"]:
        raise HTTPException(410, "quote expired — request a new one")
    state = _machine()
    for i in rec["items"]:
        if state.stock(i.sku) < i.quantity:
            raise HTTPException(409, "stock moved — request a new quote")
    for i in rec["items"]:
        state.take(i.sku, i.quantity)
    rec["settled"] = True
    return {"quote_id": quote_id, "status": "settled",
            "total": round(sum(i.unit_price * i.quantity for i in rec["items"]), 2)}

"""snhp-price/1 over HTTP — the price-link endpoints (VEND P3).

A demo machine lives in-process (seeded; its clock follows wall time and its
DAY advances with the calendar, so restock/expiry are real). Quotes RESERVE
their stock until TTL (holds are enforced, not just documented); settle is
idempotent; all mutations are serialized under one lock; quote records are
pruned. All math, no LLM calls.

  POST /v1/vend/quote            intent (+optional buyer disclosure) → Quote
  POST /v1/vend/settle/{id}      idempotent; 410 after TTL
  GET  /v1/vend/machine          public board (list prices, available stock)
"""
from __future__ import annotations

import itertools
import math
import threading
import time
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/v1/vend", tags=["vend"])

QUOTE_TTL_S = 120
_MAX_QUOTES = 10_000          # hard cap on live records (public endpoint)
_LOCK = threading.Lock()
_DEMO = None
_DEMO_DATE: date | None = None
_QUOTES: dict[str, dict] = {}
_NONCE = itertools.count()


def _prune_locked(now: float) -> None:
    dead = [qid for qid, r in _QUOTES.items()
            if r["settled"] or now > r["expires"]]
    for qid in dead:
        del _QUOTES[qid]
    while len(_QUOTES) >= _MAX_QUOTES:      # oldest-first emergency cap
        _QUOTES.pop(next(iter(_QUOTES)))


def _held(state, sku: str, now: float) -> int:
    """Units reserved by live, unsettled quotes."""
    return sum(i.quantity for r in _QUOTES.values()
               if not r["settled"] and now <= r["expires"]
               for i in r["items"] if i.sku == sku)


def _available(state, sku: str, now: float) -> int:
    return state.stock(sku) - _held(state, sku, now)


def _machine():
    """The in-process demo machine; tick follows the wall clock and the DAY
    advances with the calendar (expiry + nightly restock are real)."""
    global _DEMO, _DEMO_DATE
    if _DEMO is None:
        from vend.world import WorldConfig, build_catalog, fresh_machine
        cfg = WorldConfig(sigma_cal=0.3, glut_prob=0.5)
        cat = build_catalog(cfg, master_seed=20260713)
        _DEMO = fresh_machine("demo-01", cat, cfg, master_seed=20260713)
        _DEMO_DATE = date.today()
    if date.today() != _DEMO_DATE:
        from vend.world import WorldConfig, end_of_day
        cfg = WorldConfig(sigma_cal=0.3, glut_prob=0.5)
        for _ in range(min((date.today() - _DEMO_DATE).days, 30)):
            end_of_day(_DEMO, cfg, 20260713)
        _DEMO_DATE = date.today()
    now = datetime.now()
    _DEMO.tick = max(0, min(95, (now.hour - 7) * 6 + now.minute // 10))
    return _DEMO


class BuyerBlock(BaseModel):
    disclosure: dict = Field(..., description="{'utilities': {sku: $}, 'walk_cost': $}")
    peer_proof: dict | None = None

    @field_validator("disclosure")
    @classmethod
    def _finite_numbers(cls, v: dict) -> dict:
        utils = v.get("utilities")
        if not isinstance(utils, dict):
            raise ValueError("disclosure.utilities must be {sku: dollars}")
        for k, x in utils.items():
            if not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
                raise ValueError(f"utilities[{k!r}] must be a finite non-negative number")
        w = v.get("walk_cost", 1.0)
        if not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0:
            raise ValueError("walk_cost must be a finite non-negative number")
        return v


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
    with _LOCK:
        state = _machine()
        now = time.time()
        return {"machine_id": state.machine_id, "protocol": "snhp-price/1",
                "board": {sku: {"list_price": l.list_price,
                                "available": max(0, _available(state, sku, now)),
                                "expires_in_days": state.days_to_expiry(sku)}
                          for sku, l in state.listings.items()}}


@router.post("/quote")
def quote(req: QuoteReq):
    from dataclasses import asdict

    from vend.core import QuoteItem, disclosure_digest, make_quote, substream
    from vend.scenario import nash_quote
    from vend.world import hour_of

    with _LOCK:
        state = _machine()
        now = time.time()
        _prune_locked(now)
        it = req.intent
        if it.sku not in state.listings:
            raise HTTPException(404, f"unknown sku {it.sku!r}")

        digest = None
        if it.buyer is None:
            # one-sided: the sticker
            listing = state.listings[it.sku]
            if _available(state, it.sku, now) < it.quantity:
                raise HTTPException(409, "insufficient stock")
            items = [QuoteItem(it.sku, it.quantity, listing.list_price,
                               listing.list_price)]
            why = ["list price"]
        else:
            utils = it.buyer.disclosure["utilities"]
            wtp = {s: float(utils.get(s, 0.0)) for s in state.listings}
            walk = float(it.buyer.disclosure.get("walk_cost", 1.0))
            digest = disclosure_digest(wtp, walk)
            # the intent is a CONSTRAINT, not a suggestion: honor sku
            # (unless substitutes_ok), quantity ceiling, and live holds
            allowed = (lambda o, sku=it.sku, q=it.quantity, subs=it.substitutes_ok:
                       (subs or o.sku == sku) and o.qty <= q
                       and o.qty <= _available(state, o.sku, now))
            nq = nash_quote(state, wtp, walk, allowed=allowed)
            if nq.outcome is None:
                return {"no_deal": True,
                        "reason": "no outcome beats both sides' alternatives",
                        "board_url": "/v1/vend/machine"}
            o = nq.outcome
            items = [QuoteItem(o.sku, o.qty, o.unit_price,
                               state.listings[o.sku].list_price)]
            why = nq.why

        q = make_quote(state, "vend-api/1",
                       seed=substream(20260713, "api", time.time_ns(),
                                      next(_NONCE)),
                       items=items, why=list(why), hour=hour_of(state.tick),
                       disclosure_digest=digest)
        _QUOTES[q.quote_id] = {"items": items,
                               "expires": now + QUOTE_TTL_S, "settled": False}
        return {"quote_id": q.quote_id, "protocol": q.protocol,
                "items": [asdict(i) for i in q.items], "total": q.total,
                "why": list(q.why), "context_hash": q.context_hash,
                # honesty: this demo endpoint cannot verify peer proofs —
                # verified peering lives in the gt_a2a_* flow
                "attestation": "unverified",
                "expires_in_seconds": QUOTE_TTL_S,
                "settle_url": f"/v1/vend/settle/{q.quote_id}"}


@router.post("/settle/{quote_id}")
def settle(quote_id: str):
    with _LOCK:
        rec = _QUOTES.get(quote_id)
        if rec is None:
            raise HTTPException(404, "unknown quote")
        if rec["settled"]:
            return {"quote_id": quote_id, "status": "settled", "idempotent": True}
        if time.time() > rec["expires"]:
            raise HTTPException(410, "quote expired — request a new one")
        state = _machine()
        for i in rec["items"]:
            if state.stock(i.sku) < i.quantity:   # held FOR this quote
                raise HTTPException(409, "stock moved — request a new quote")
        for i in rec["items"]:
            state.take(i.sku, i.quantity)
        rec["settled"] = True
        return {"quote_id": quote_id, "status": "settled",
                "total": round(sum(i.unit_price * i.quantity for i in rec["items"]), 2)}

"""POST /v1/divorce/run — the live Build-Your-Ex endpoint.

A thin, validated wrapper over trace.run_episode: two persona specs in, one
full four-act playback trace out (same JSON contract as the preset files, so
the chrome's player consumes it unchanged). Everything real happens
server-side — the browser never holds utilities, posteriors, or the notary
key (SPEC.md §9).

Run locally:  uvicorn divorce.api:app --port 8203
Deploy shape: mount `router` into gametheory.server.http alongside the other
/v1 routes (same-origin with the demo page — the SPEC §11.3 serving call).
"""
from __future__ import annotations

import os
import re

import numpy as np
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from divorce import elicit, personas, trace

router = APIRouter()
_PRIOR = None                      # built once, first request (or warm())

_LABEL_RE = re.compile(r"[^\w \-'&.!?]", re.UNICODE)


def _clean(s: str, limit: int) -> str:
    return _LABEL_RE.sub("", s.strip())[:limit].strip() or "—"


class SideSpec(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    archetype: str
    pettiness: float = Field(ge=0.0, le=1.0)
    spite: float = Field(ge=0.0, le=1.0)
    patience: float = Field(ge=0.0, le=1.0)
    hill: str

    def to_spec(self) -> dict:
        if self.archetype not in personas.ARCHETYPES:
            raise HTTPException(422, f"unknown archetype {self.archetype!r}")
        if self.hill not in personas.HILLABLE:
            raise HTTPException(422, f"hill must be one of {personas.HILLABLE}")
        return {"name": _clean(self.name, 24), "archetype": self.archetype,
                "hill": self.hill,
                # spite slider is 0..1 in the UI; the utility weight caps at .6
                "sliders": {"pettiness": self.pettiness,
                            "spite": 0.6 * self.spite,
                            "patience": self.patience}}


class RunRequest(BaseModel):
    a: SideSpec
    b: SideSpec
    wildcard_label: str = Field(default="the sentimental item", max_length=40)
    fronts: list[str] = Field(default=["dog"], max_length=2)
    seed: int | None = Field(default=None, ge=1, le=10_000_000)


def warm() -> None:
    global _PRIOR
    if _PRIOR is None:
        _PRIOR = elicit.build_asset_prior()


@router.post("/v1/divorce/run")
def run(req: RunRequest) -> dict:
    warm()
    for f in req.fronts:
        if f not in ("dog", "vinyl", "wildcard"):
            raise HTTPException(422, "fronts must be from dog/vinyl/wildcard")
    spec = {"wildcard_label": _clean(req.wildcard_label, 40),
            "fronts": list(dict.fromkeys(req.fronts)),
            "a": req.a.to_spec(), "b": req.b.to_spec()}
    # Server-drawn seed unless pinned: returned in meta.preset_seed, so any
    # run is reproducible/shareable by (spec, seed) alone.
    seed = req.seed if req.seed is not None else \
        int.from_bytes(os.urandom(4), "big") % 10_000_000 + 1
    try:
        return trace.run_episode(seed, spec, _PRIOR)
    except Exception as exc:  # noqa: BLE001 — a failed run is a 500 with a reason
        raise HTTPException(500, f"episode failed: {type(exc).__name__}") from exc


@router.get("/v1/divorce/archetypes")
def archetypes() -> dict:
    """The builder's card data — archetype names, slider presets, hillables."""
    return {"archetypes": {k: {s: v[s] for s in ("pettiness", "spite", "patience")}
                           for k, v in personas.ARCHETYPES.items()},
            "hillable": personas.HILLABLE}


app = FastAPI(title="snhp divorce — live episode runner")
app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    # Local dev origins + the deployed arena; same-origin mounting makes this
    # moot in production (SPEC.md §11.3).
    allow_origins=["http://localhost:8200", "http://127.0.0.1:8200",
                   "https://arena.snhp.dev"],
    allow_methods=["POST", "GET"],
    allow_headers=["content-type"],
)

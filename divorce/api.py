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

import json
import os
import re
import threading

import numpy as np
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from divorce import elicit, personas, trace

router = APIRouter()
_PRIOR = None                      # built once, first request (or warm())

_LABEL_RE = re.compile(r"[^\w \-'&.!?]", re.UNICODE)

# ── the case registry: a printed case number must be a REAL door ────────────
# "Same number, same divorce" is only true if the number alone reproduces the
# episode — seed AND spec. Filed cases persist to a JSONL ledger; GET
# /v1/divorce/case/{n} deterministically replays. (CMO finding: the screenshot
# is the post and the number is the only pointer that survives a no-link
# doctrine — so the number has to actually work at the counter.)
_CASES_PATH = os.environ.get(
    "DIVORCE_CASES_PATH", os.path.join(os.path.dirname(__file__), "cases.jsonl"))
_CASES: dict[int, dict] = {}
_CASES_LOCK = threading.Lock()


def _load_cases() -> None:
    if not os.path.exists(_CASES_PATH):
        return
    with open(_CASES_PATH) as f:
        for line in f:
            try:
                rec = json.loads(line)
                _CASES[int(rec["case_no"])] = rec
            except (ValueError, KeyError):
                continue                     # a torn line never kills the office


def _file_case(seed: int, spec: dict) -> int:
    with _CASES_LOCK:
        if not _CASES:
            _load_cases()
        case_no = int.from_bytes(os.urandom(4), "big") % 9_000_000 + 1_000_000
        while case_no in _CASES:
            case_no = int.from_bytes(os.urandom(4), "big") % 9_000_000 + 1_000_000
        rec = {"case_no": case_no, "seed": seed, "spec": spec}
        _CASES[case_no] = rec
        with open(_CASES_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return case_no


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
        ep = trace.run_episode(seed, spec, _PRIOR)
    except Exception as exc:  # noqa: BLE001 — a failed run is a 500 with a reason
        raise HTTPException(500, f"episode failed: {type(exc).__name__}") from exc
    ep["meta"]["case_no"] = _file_case(seed, spec)
    return ep


@router.get("/v1/divorce/case/{case_no}")
def replay_case(case_no: int) -> dict:
    """Same number, same divorce — deterministic replay from the ledger."""
    warm()
    with _CASES_LOCK:
        if not _CASES:
            _load_cases()
        rec = _CASES.get(case_no)
    if rec is None:
        raise HTTPException(404, "No such case on file. The county keeps "
                                 "excellent records; this number isn't in them.")
    ep = trace.run_episode(int(rec["seed"]), rec["spec"], _PRIOR)
    ep["meta"]["case_no"] = case_no
    return ep


@router.get("/v1/divorce/archetypes")
def archetypes() -> dict:
    """The builder's card data — archetype names, slider presets, hillables."""
    return {"archetypes": {k: {s: v[s] for s in ("pettiness", "spite", "patience")}
                           for k, v in personas.ARCHETYPES.items()},
            "hillable": personas.HILLABLE}


async def clerk_voiced_422(request: Request, exc: RequestValidationError):
    """Validation failures answer in the clerk's voice, honestly — never
    blaming infrastructure for the caller's paperwork (CMO finding: the
    40-char wildcard rejection surfaced as 'the office is closed', a lie).
    Exception handlers are app-level in FastAPI (include_router does NOT
    carry them), so hosts mounting the router must register this themselves;
    the path guard keeps the clerk out of non-county endpoints."""
    if not request.url.path.startswith("/v1/divorce"):
        return JSONResponse(status_code=422,
                            content={"detail": jsonable_encoder(exc.errors())})
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []))
        if "wildcard_label" in loc and err.get("type", "").startswith("string_too_long"):
            detail = ("Item names cap at 40 characters. "
                      "This is a government office.")
            break
        if loc.endswith("name") and err.get("type", "").startswith("string_too_long"):
            detail = "Names cap at 24 characters. Initials are traditional."
            break
    else:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", [])[1:]) or "the form"
        detail = f"The county rejects this filing: check {loc}."
    return JSONResponse(status_code=422, content={"detail": detail})


app = FastAPI(title="snhp divorce — live episode runner")
app.include_router(router)
app.add_exception_handler(RequestValidationError, clerk_voiced_422)
app.add_middleware(
    CORSMiddleware,
    # Local dev origins + the deployed arena; same-origin mounting makes this
    # moot in production (SPEC.md §11.3).
    allow_origins=["http://localhost:8200", "http://127.0.0.1:8200",
                   "https://arena.snhp.dev"],
    allow_methods=["POST", "GET"],
    allow_headers=["content-type"],
)

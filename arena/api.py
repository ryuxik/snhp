"""SNHP Evolution Arena — the live server. Serves the renderer SPA at / and the
sim over a WebSocket at /arena/ws, plus HTTP endpoints for snapshot, census,
species, replay, highlights, and the stats/science page. Mirrors par/api.py's
shape: /health first, static mount last.

    uvicorn arena.api:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from arena.config import CONFIG
from arena.runner import ArenaRunner

app = FastAPI(title="SNHP Evolution Arena",
              description="watch AI negotiators evolve, live")

RUNNER = ArenaRunner(CONFIG, run_id=os.environ.get("ARENA_RUN_ID", "live"),
                     persist=os.environ.get("ARENA_PERSIST", "1") == "1")


@app.get("/health")
def health() -> dict:
    snap = RUNNER.public["snapshot"]
    return {"ok": True, "service": "arena", "gen": snap.get("gen", 0),
            "pop": len(snap.get("agents", [])), "clients": RUNNER.bcast.n_clients}


@app.on_event("startup")
async def _startup() -> None:
    if os.environ.get("ARENA_NO_RUN") == "1":
        return  # tests: serve endpoints without the infinite sim loop
    # Warm the engine in a thread so /health can answer during JIT compile.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, RUNNER.warmup)
    RUNNER.start()


# All read endpoints serve RUNNER.public — an immutable read-state swapped
# atomically once per generation — so they never iterate the live world while
# the sim thread mutates it (which would raise "dict changed size").
@app.get("/arena/state")
def state() -> dict:
    return RUNNER.public["snapshot"]


@app.get("/arena/census")
def census() -> dict:
    snap, cen = RUNNER.public["snapshot"], RUNNER.public["census"]
    out = {"gen": snap.get("gen", 0), "era": snap.get("era"),
           "era_label": snap.get("era_label"), "assortative": snap.get("assortative"),
           "pop": len(snap.get("agents", []))}
    if cen:
        out.update({k: cen[k] for k in
                    ("staked_frac", "mean_knob", "era_optimal_knob", "mean_energy",
                     "n_species", "peer_premium", "adv_premium", "peer_n", "tactics")
                    if k in cen})
    return out


@app.get("/arena/species")
def species() -> dict:
    return {"gen": RUNNER.public["snapshot"].get("gen", 0),
            "species": RUNNER.public["species"]}


@app.get("/arena/agents/{agent_id}")
def agent(agent_id: int) -> dict:
    # served from the immutable per-generation snapshot (no live-world read)
    snap = RUNNER.public["snapshot"]
    a = next((x for x in snap.get("agents", []) if x["id"] == agent_id), None)
    if a is None:
        raise HTTPException(status_code=404, detail="agent not found (may have died)")
    return dict(a)


@app.get("/arena/highlights")
def highlights() -> dict:
    if RUNNER.store is None:
        return {"highlights": []}
    return {"highlights": RUNNER.store.read_highlights()[-100:]}


@app.get("/arena/replay")
def replay(gen: int = Query(..., ge=0)) -> JSONResponse:
    if RUNNER.store is None:
        raise HTTPException(status_code=404, detail="persistence disabled")
    events = list(RUNNER.store.read_gen(gen))
    if not events:
        raise HTTPException(status_code=404, detail=f"no events for gen {gen}")
    return JSONResponse(events)


@app.get("/arena/stats")
def stats() -> dict:
    """The science/skeptic payload: honest claims + the config a viewer can read."""
    w = RUNNER.world
    return {
        "gen": w.gen, "era": w.era,
        "config": w.cfg.to_public_dict(),
        # Plain-language lead — the same explanation the on-page "Honest Page"
        # shows. If you can't say it simply, it isn't a shareable artifact.
        "plain": {
            "how_they_live_or_die": [
                "Nobody scores their negotiating. It's a town, not an exam.",
                "A knight earns energy from the surplus it wins in a deal. Every round it "
                "pays rent — more if lots of others use its strategy. Broke, it dies.",
                "Bank enough and it breeds — and the two parents haggle over which genes "
                "the child gets. Good dealmakers eat and multiply; bad ones starve.",
                "That's the whole rule. The market is the only judge — fitness is money, "
                "not a score we hand out.",
            ],
            "whats_real": [
                "Students beat the textbook: evolution found a price strategy that "
                "out-earns SNHP's own default advice by +27%.",
                "Trust grows the pie: two verified partners who cooperate both do better "
                "(+2% together); a lone cooperator gains nothing — why you need peers.",
                "Every move is SNHP. There is zero negotiation code in the arena itself.",
            ],
            "whats_hype_even_ours": [
                "'+119% on multi-issue' is an ARTIFACT: agents evolved to want less, so "
                "every deal looks like a win. On the fair metric our recommender is already "
                "at the ceiling — evolution can't beat it.",
                "'Fitness always rises' is false: the average runs to stay in place (a Red "
                "Queen race). The winners are rare, not typical.",
                "'Emergent species / clever gene-bargaining' — no. Those tie a coin flip. "
                "We say so.",
            ],
            "reproduce": "Every number is reproducible: python -m arena.science --all",
        },
        "honest_claims": {
            "shows": [
                "Every deal is computed by the shipped SNHP engine — zero arena-side strategy code.",
                "Attestation's lift is measured CAUSALLY: a paired-seed probe replays the same "
                "matchup and scenario with attestation forced on vs off (the observational "
                "pact-vs-ordinary comparison is genome-confounded and is not displayed).",
                "Strategy rank is market-dependent — watch it change when the era flips.",
                "Inheritance is mechanism-mediated: children are settled logrolled packages; "
                "matings are deferred-acceptance outcomes.",
                "The staking A/B shows critical-mass dynamics as a function of discoverability.",
                "Agents compete on MULTI-ISSUE logrolling, not only price: a quarter to two-thirds "
                "of every generation's deals are bundles, and the private priority simplex plus the "
                "evolvable bundle ceiling feed fitness and are under selection (see 'science').",
            ],
            "does_not_show": [
                "That agents 'reach the Nash equilibrium' — offers are subjective Nash points under Bayesian beliefs.",
                "That 'SNHP wins' — rank depends on the market.",
                "The lab's +0.186 / +12.5% as arena numbers — the HUD shows this run's own paired-probe lift.",
                "The PEER playbook the same way on price and bundles. On single-issue PRICE the "
                "cooperative descent is infeasible (both peers demand >55% of one pie), so staked "
                "price pairs demonstrate only attestation's INFORMATION channel (truthful "
                "reservations preserve the true ZOPA). On MULTI-ISSUE bundles staked pairs run the "
                "engine's real cooperative logrolling — the new first-class cooperation dial "
                "(validated +2.0% joint welfare at the shipped 0.6) — which is where attestation's "
                "logrolling payoff actually lives. Both are shipped code, honestly scoped.",
                "Deception — walk_margin is Schelling commitment to your OWN advisor, not a lie to the counterparty.",
            ],
            "keystone": "Nothing in this arena knows how to negotiate except the library being showcased.",
        },
        "science": {
            "note": "Off-selection-path measurements from arena/science.py (run `python -m arena.science --all`).",
            "human_competitive_price": "On PRICE, an evolved champion (boulware, knob 0.63, truthful-ish "
                                       "floor, evolved concession schedule) beats the RAW SNHP recommender's "
                                       "own play by +27% on a held-out sellers'-market panel — a strategy "
                                       "evolution DISCOVERED, made possible by the evolvable concession layer.",
            "human_competitive_multi_issue": "On MULTI-ISSUE logrolling, the honest (preference-normalized) "
                                             "metric is frontier capture: the RAW recommender holds 88% and "
                                             "evolution reaches 85% — evolution does NOT beat it; the raw "
                                             "logroller is at the efficiency ceiling. The eye-catching +119% "
                                             "own-surplus is a preference-shape ARTIFACT (heritable priorities "
                                             "specialize until the logroll trivially delivers the one issue "
                                             "kept), jointly no more efficient. You don't beat SNHP by "
                                             "distorting its inputs — the declaration-distortion gene is "
                                             "selected AGAINST, mirroring the price bluffing result.",
            "multi_issue_selection": "The multi-issue PRIORITY gene is now under strong directed selection "
                                     "(Cov(specialization, income) +0.65 vs +0.43 neutral) — before this it "
                                     "sat frozen near uniform. A quarter to two-thirds of deals are bundles.",
            "peer_cooperation": "The multi-issue payoff that is REAL is JOINT and attestation-gated: the "
                                "engine's new cooperation dial lifts joint welfare +2.0% at the shipped 0.6 "
                                "(validated), captured only when both sides cooperate — which is why verified "
                                "peers (staking) are the vehicle. It is not individually selected (mutualistic).",
            "absolute_fitness": "The population MEAN does not improve against a frozen reference panel "
                                "(a co-evolutionary Red Queen treadmill) — reported honestly. The gains "
                                "live in the tail of the search, not the average.",
            "honest_negatives": [
                "Negotiated crossover (9.0 gens to assemble a split block) does NOT beat uniform (3.6) "
                "— does no special linkage work; kept for the story, said so.",
                "Courtship impasse is independent of parent genetic distance — no emergent "
                "reproductive isolation; impasse is a flat fecundity cost.",
                "Negotiated surplus is only ~1/3 of fitness variance; the rest is demographic.",
                "The multi-issue own-surplus 'win' is a preference-specialization artifact; the honest "
                "efficiency metric shows the raw logroller at the ceiling.",
            ],
        },
    }


# ── forge your champion: a viewer's strategy enters the world ──
from collections import defaultdict, deque
import time as _time

from pydantic import BaseModel, Field

from arena.genome import TACTIC_FAMILIES

_CH_LIMIT, _CH_WINDOW = 3, 300.0   # 3 champions / 5 min / IP
_ch_rl: "defaultdict[str, deque]" = defaultdict(deque)


class ChampionReq(BaseModel):
    token: str = Field(..., max_length=64)      # client-generated; echoed on the
    house: str = Field("Challenger", max_length=24)  # immigration event so the
    tactic: str = Field(..., max_length=16)          # forger can find its agent
    boldness: float = Field(0.6, ge=0.0, le=1.0)
    bluff: float = Field(0.3, ge=0.0, le=1.0)
    patience: float = Field(0.5, ge=0.0, le=1.0)
    staked: bool = False


@app.post("/arena/champion")
def champion(req: ChampionReq, request: Request) -> dict:
    """Queue a viewer-forged champion. It enters through the gate at the next
    generation boundary as a real agent running the viewer's SNHP parameters."""
    if req.tactic not in TACTIC_FAMILIES:
        raise HTTPException(status_code=400, detail=f"tactic must be one of {sorted(TACTIC_FAMILIES)}")
    ip = request.client.host if request.client else "?"
    q, now = _ch_rl[ip], _time.monotonic()
    while q and now - q[0] > _CH_WINDOW:
        q.popleft()
    if len(q) >= _CH_LIMIT:
        raise HTTPException(status_code=429, detail="the gate is barred — try again soon")
    q.append(now)
    RUNNER.world.queue_champion({
        "token": req.token, "house": "".join(c for c in req.house if c.isalnum())[:24],
        "tactic": req.tactic, "boldness": req.boldness, "bluff": req.bluff,
        "patience": req.patience, "staked": req.staked,
    })
    return {"queued": True, "note": "your champion enters at the next generation"}


# ── admin (token-gated) ──
def _admin_ok(token: Optional[str]) -> bool:
    want = os.environ.get("ARENA_ADMIN_TOKEN", "")
    return bool(want) and token == want


@app.post("/arena/admin/{action}")
def admin(action: str, token: str = Query("")) -> dict:
    if not _admin_ok(token):
        raise HTTPException(status_code=403, detail="forbidden")
    if action == "pause":
        RUNNER.paused = True
    elif action == "resume":
        RUNNER.paused = False
    elif action.startswith("speed"):
        try:
            RUNNER.speed = float(action.split(":", 1)[1])
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="speed:N")
    else:
        raise HTTPException(status_code=400, detail="unknown action")
    return {"ok": True, "paused": RUNNER.paused, "speed": RUNNER.speed}


@app.websocket("/arena/ws")
async def ws(sock: WebSocket) -> None:
    await sock.accept()
    q = RUNNER.bcast.register()
    try:
        # On connect: the cached snapshot first (never the live world) — cold boot
        # and reconnect share this path.
        snap = RUNNER.public["snapshot"]
        await sock.send_json({"v": 1, "type": "world.snapshot", "seq": 0, **snap})
        # Optional resume: client may send {"type":"hello","since_seq":N}. Only
        # swallow the timeout / malformed-json cases here; let disconnects and
        # cancellation propagate to the outer handler so the socket closes cleanly.
        try:
            hello = await asyncio.wait_for(sock.receive_json(), timeout=0.25)
            if hello.get("type") == "hello" and "since_seq" in hello:
                for ev in RUNNER.bcast.replay_since(int(hello["since_seq"])):
                    await sock.send_json(ev)
        except (asyncio.TimeoutError, ValueError, KeyError, TypeError):
            pass
        while True:
            ev = await q.get()
            await sock.send_json(ev)
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass  # dead/closed socket — send_json can raise non-WebSocketDisconnect
    finally:
        RUNNER.bcast.unregister(q)


# ── featherweight funnel metrics: append-only counts, no cookies/identity.
# Read later with: fly ssh console -a snhp-arena -C "tail /data/hits.jsonl"
_HITS = os.path.join(os.environ.get("ARENA_DATA_DIR", "/tmp"), "hits.jsonl")


@app.post("/hit")
async def hit(request: Request) -> dict:
    import json as _json
    import time as _time
    try:
        # spam guard: metrics may never fill the volume (50MB ≈ years of real use)
        if os.path.exists(_HITS) and os.path.getsize(_HITS) > 50_000_000:
            return {"ok": True}
        body = await request.body()
        p = str(_json.loads(body or b"{}").get("p", ""))[:32]
        if p:
            with open(_HITS, "a") as f:
                f.write(_json.dumps({"t": int(_time.time()), "p": p}) + "\n")
    except Exception:
        pass  # metrics must never break the site
    return {"ok": True}


# ── page analytics (server-side, privacy-preserving) ───────────────────────
# One JSONL line per PAGE view in the SAME $ARENA_DATA_DIR/hits.jsonl: ts, path,
# referer HOST only, user-agent FAMILY only. No IPs, no query strings, no PII.
# Every path here is fail-open — analytics must never break a page.
import json as _ajson
import time as _atime
from urllib.parse import urlsplit as _urlsplit

_HITS_MAX = 50_000_000  # ~years of real traffic; stop writing past this


def _ua_family(ua: str) -> str:
    """A coarse browser family — never the raw UA (that's fingerprintable)."""
    u = (ua or "").lower()
    if not u:
        return "unknown"
    if any(b in u for b in ("bot", "spider", "crawl", "slurp", "curl", "wget",
                            "python-requests", "httpx", "headless", "monitor")):
        return "bot"
    if "edg/" in u or "edgios" in u or "edga" in u:
        return "edge"
    if "firefox" in u or "fxios" in u:
        return "firefox"
    if "chrome" in u or "crios" in u or "chromium" in u:
        return "chrome"
    if "safari" in u:
        return "safari"
    return "other"


def _ref_host(referer: str) -> str:
    """Referer HOST only — never the full URL (it can carry a path/query)."""
    try:
        return (_urlsplit(referer or "").hostname or "")[:120]
    except Exception:
        return ""


def _is_page(path: str) -> bool:
    """Count top-level navigations only: '/', '/world', directory indexes, .html.
    Static assets, the JSON/WS API, and health checks are not pageviews."""
    if path in ("/", "/world"):
        return True
    if path.startswith(("/api", "/arena", "/health", "/hit", "/core",
                        "/block/live", "/vendor", "/v1")):
        return False
    return path.endswith(".html") or path.endswith("/")


def _append_hit(rec: dict) -> None:
    try:
        if os.path.exists(_HITS) and os.path.getsize(_HITS) > _HITS_MAX:
            return  # volume guard
        with open(_HITS, "a") as f:
            f.write(_ajson.dumps(rec, separators=(",", ":")) + "\n")
    except Exception:
        pass  # analytics must never break a page


@app.middleware("http")
async def _count_pageviews(request: Request, call_next):
    # Count the pageview but never let counting affect the response: the whole
    # body is guarded, and the request is served no matter what.
    try:
        path = request.url.path  # path only — FastAPI strips the query string
        if request.method == "GET" and _is_page(path):
            _append_hit({"ts": int(_atime.time()), "path": path[:200],
                         "ref": _ref_host(request.headers.get("referer", "")),
                         "ua": _ua_family(request.headers.get("user-agent", ""))})
    except Exception:
        pass
    return await call_next(request)


@app.post("/api/hit")
async def api_hit(request: Request) -> dict:
    """Fire-and-forget pageview beacon for statically-served pages (nav.js sends
    {page}). Same privacy rules as the middleware; same append-only file."""
    try:
        body = await request.body()
        page = str(_ajson.loads(body or b"{}").get("page", ""))[:200]
        if page:
            _append_hit({"ts": int(_atime.time()), "path": page, "src": "beacon",
                         "ref": _ref_host(request.headers.get("referer", "")),
                         "ua": _ua_family(request.headers.get("user-agent", ""))})
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/stats")
def api_stats() -> dict:
    """Daily counts per page from the JSONL. Tolerant of legacy {t,p} lines and
    capped (last 30 days × top 100 paths) so a long history can't blow up."""
    days: "defaultdict[str, defaultdict[str, int]]" = defaultdict(lambda: defaultdict(int))
    total = 0
    try:
        if os.path.exists(_HITS):
            with open(_HITS) as f:
                for line in f:
                    try:
                        o = _ajson.loads(line)
                    except Exception:
                        continue
                    ts = o.get("ts", o.get("t"))
                    path = o.get("path", o.get("p"))
                    if ts is None or not path:
                        continue
                    day = _atime.strftime("%Y-%m-%d", _atime.gmtime(int(ts)))
                    days[day][str(path)[:200]] += 1
                    total += 1
    except Exception:
        pass
    recent = sorted(days.keys())[-30:]
    out = {d: dict(sorted(days[d].items(), key=lambda kv: kv[1], reverse=True)[:100])
           for d in recent}
    return {"total": total, "days": out}


# ── the LIVE twin-street block experiment (Phase 5) — feature-flagged.
# BLOCK_LIVE=1 mounts /block/live (WS) + /block/live.json (snapshot) and paces
# block/live.py's driver one sim-day per BLOCK_LIVE_SECS_PER_DAY. Default OFF:
# without the flag no route exists and deploys are byte-identical in behavior.
if os.environ.get("BLOCK_LIVE") == "1":
    from arena.broadcaster import Broadcaster as _BlockBcast
    from block.live import LiveBlock

    _BLOCK_SECS = float(os.environ.get("BLOCK_LIVE_SECS_PER_DAY", "120"))
    _BLOCK_LOG = (os.environ.get("BLOCK_LIVE_LOG", "").strip()
                  or os.path.join(CONFIG.data_dir, "block-live.jsonl"))
    BLOCK = LiveBlock(log_path=_BLOCK_LOG, secs_per_day=_BLOCK_SECS)
    BLOCK_BCAST = _BlockBcast(ring_size=1024, client_queue_max=256)
    _block_seq = 0

    def _block_step() -> dict:
        return BLOCK.step_day()

    async def _block_loop() -> None:
        global _block_seq
        loop = asyncio.get_event_loop()
        # resume re-simulates the current season against the telemetry log
        # (exact continuation, or a fresh season if the code changed)
        await loop.run_in_executor(None, BLOCK.resume)
        while True:
            rec = await loop.run_in_executor(None, _block_step)
            _block_seq += 1
            BLOCK_BCAST.publish({"v": 1, "type": "block.day",
                                 "seq": _block_seq, **rec})
            await asyncio.sleep(max(_BLOCK_SECS, 1.0))

    @app.on_event("startup")
    async def _block_startup() -> None:
        if os.environ.get("ARENA_NO_RUN") == "1":
            return  # tests: serve the snapshot without the pacing loop
        asyncio.create_task(_block_loop())

    @app.get("/block/live.json")
    def block_live_json() -> dict:
        """HTTP snapshot for no-WS clients: cumulative totals + the last
        day-records. BLOCK.public is swapped atomically after each day."""
        return BLOCK.public

    @app.websocket("/block/live")
    async def block_live_ws(sock: WebSocket) -> None:
        await sock.accept()
        q = BLOCK_BCAST.register()
        try:
            await sock.send_json({"v": 1, "type": "block.snapshot",
                                  "seq": _block_seq, **BLOCK.public})
            while True:
                ev = await q.get()
                await sock.send_json(ev)
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            pass
        finally:
            BLOCK_BCAST.unregister(q)


# ── site entry: the root serves the thesis home (index.html); the classic
# evolution arena — the old index — is kept at /world and arena-classic.html.
# Old marketing URLs are redirect stubs to snhp.dev; hook/boba/etc. are demos.
@app.get("/")
def root() -> FileResponse:
    return FileResponse(os.path.join(os.path.dirname(__file__), "web", "index.html"))


# Marketing pages moved to the product site (snhp.dev). Real 301s so machine
# clients — crawlers, llms.txt readers, curl — follow them; the .html files on
# disk remain as client-side fallbacks for anything that ignores the redirect.
_MOVED = {
    "benchmark.html": "/certificate", "submit.html": "/certificate",
    "certify.html": "/certificate", "nx.html": "/spec",
    "build.html": "/build", "hire.html": "/build",
    "read.html": "/results", "science.html": "/results",
    "archive.html": "/results",
}


def _moved(_page: str, _target: str):
    def _h() -> RedirectResponse:
        return RedirectResponse("https://snhp.dev" + _target, status_code=301)
    return _h


for _page, _target in _MOVED.items():
    app.add_api_route("/" + _page, _moved(_page, _target),
                      methods=["GET", "HEAD"], include_in_schema=False)


@app.get("/world")
def world() -> FileResponse:
    return FileResponse(os.path.join(os.path.dirname(__file__), "web", "arena-classic.html"))


# The funnel pages (hook.html, yourmenu.html) import the general JS engine via
# `../../core/js/*.mjs`, which the browser normalizes to /core/js/* — serve the
# repo's core/js there (works identically on the repo-root dev server). Mounted
# BEFORE the catch-all so it wins the prefix match.
_CORE_JS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "js")
if os.path.isdir(_CORE_JS):
    app.mount("/core/js", StaticFiles(directory=_CORE_JS), name="corejs")

# The divorce demo's live engine — same-origin with its chrome at /divorce/
# (SPEC.md section 11.3). The case ledger persists on the arena volume via
# DIVORCE_CASES_PATH so "same number, same divorce" survives deploys.
from divorce.api import router as _divorce_router  # noqa: E402
from divorce.api import clerk_voiced_422 as _clerk_422  # noqa: E402
from fastapi.exceptions import RequestValidationError as _ReqValErr  # noqa: E402
app.include_router(_divorce_router)
# include_router does not carry exception handlers; the clerk answers 422s
# on /v1/divorce/* only (path guard inside the handler).
app.add_exception_handler(_ReqValErr, _clerk_422)

# The PAR daily game — same-origin at /par/ (chrome in arena/web/par/, served by the
# catch-all mount below), API under /par/*. State is a SQLite file on the arena volume
# (GT_KEYS_DB=/data/par.db in fly.toml); no separate Postgres. Formerly its own app at
# par.snhp.dev. par.api's rate-limit middleware + demo seeding stay on its standalone app
# (local dev); only the domain routes ride along here.
from par.api import router as _par_router  # noqa: E402
app.include_router(_par_router)

# Static text assets must revalidate on every load (Cache-Control: no-cache;
# ETags keep repeats as cheap 304s). Without this, browsers heuristically
# cache html/css/js and a redeploy can serve a returning visitor a stale/fresh
# HYBRID (new markup styled by old css — observed live after the premise
# deploy). no-cache ≠ no-store: content still caches, it just always asks.
_REVALIDATE_EXTS = (".html", ".css", ".js", ".mjs", ".json")


@app.middleware("http")
async def _static_no_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith(_REVALIDATE_EXTS) or path.endswith("/") or "." not in path.rsplit("/", 1)[-1]:
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# Serve the renderer SPA same-origin; /arena/* and /health matched first.
_WEB = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(_WEB):
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")

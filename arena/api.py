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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import JSONResponse
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
        "honest_claims": {
            "shows": [
                "Every deal is computed by the shipped SNHP engine — zero arena-side strategy code.",
                "The cooperation premium is reproduced qualitatively and measured live (this run's n).",
                "Strategy rank is market-dependent — watch it change when the era flips.",
                "Inheritance is mechanism-mediated: children are settled logrolled packages; "
                "matings are deferred-acceptance outcomes.",
                "The staking A/B shows critical-mass dynamics as a function of discoverability.",
            ],
            "does_not_show": [
                "That agents 'reach the Nash equilibrium' — offers are subjective Nash points under Bayesian beliefs.",
                "That 'SNHP wins' — rank depends on the market.",
                "The lab's +0.186 / +12.5% as arena numbers — the HUD shows this run's own measured premium.",
                "Deception — walk_margin is Schelling commitment to your OWN advisor, not a lie to the counterparty.",
            ],
            "keystone": "Nothing in this arena knows how to negotiate except the library being showcased.",
        },
    }


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


# Serve the renderer SPA same-origin; /arena/* and /health matched first.
_WEB = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(_WEB):
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")

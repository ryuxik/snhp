"""PAR daily-scenario backend — the live API the front end calls.

Serves the day's deal, plays the House each round with the SNHP equilibrium, and
grades the close against the real par. The House's reservation (`house_max`) is the
secret ceiling — it is NEVER sent to the client until the grade. Run:

    uvicorn par.api:app --reload --port 8099

See SPEC.md for the daily rotation + the multi-issue generator.
"""
from __future__ import annotations

from datetime import date, timezone, datetime
from typing import Optional

import json
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from par._store import conn as store_conn

from gametheory.negotiation.par_game import Scenario, house_move, score, agent_close
from gametheory.negotiation.bundle import negotiate_bundle
from gametheory.negotiation.plain_terms import negotiate_turn, NegotiationInputError
from par import scoreboard, funnel

app = FastAPI(title="PAR", description="out-negotiate a perfect AI, daily")


@app.get("/health")
def health() -> dict:                    # Fly healthcheck; matched before the static mount
    return {"ok": True, "service": "par"}


# Naive per-IP rate limit on the write endpoints (in-memory — fine for one machine; swap for
# a shared limiter when scaling out). Stops casual floods of submit/event/advise.
_RL_LIMIT, _RL_WINDOW = 120, 60.0
_rl: "defaultdict[str, deque]" = defaultdict(deque)


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith("/par/"):
        ip = request.client.host if request.client else "?"
        q, now = _rl[ip], time.monotonic()
        while q and now - q[0] > _RL_WINDOW:
            q.popleft()
        if len(q) >= _RL_LIMIT:
            return JSONResponse({"detail": "rate limit"}, status_code=429)
        q.append(now)
    return await call_next(request)

# The deck. One deal per day; index by days-since-epoch so everyone gets the same
# deal on the same date (Wordle-style). Real deployment loads this from a table and
# rotates single- and multi-issue days. house_max is the hidden ceiling.
EPOCH = date(2026, 1, 1)
DECK = [
    Scenario("the salary talk", "sell", your_walk_away=90, your_target=130, house_reservation=118, rounds=5),
    Scenario("the rent renewal", "buy", your_walk_away=2400, your_target=1900, house_reservation=2050, rounds=5),
    Scenario("the used car", "buy", your_walk_away=14000, your_target=9000, house_reservation=11200, rounds=6),
    Scenario("the freelance rate", "sell", your_walk_away=80, your_target=160, house_reservation=135, rounds=5),
]


def _day_number(day: Optional[int]) -> int:
    """The absolute challenge number (days since epoch), or the replay day if given."""
    return day if day is not None else (datetime.now(timezone.utc).date() - EPOCH).days


def _seconds_left() -> int:
    now = datetime.now(timezone.utc)
    end = datetime.combine(now.date(), datetime.max.time(), tzinfo=timezone.utc)
    return int((end - now).total_seconds())


# ── public scenario (House hidden) ────────────────────────────────────────────
@app.get("/par/today")
def today(day: Optional[int] = None) -> dict:
    if day is not None and day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    n = _day_number(day)
    sc = DECK[n % len(DECK)]
    return {"no": n, "deck_index": n % len(DECK), "title": sc.title, "side": sc.player_side,
            "walk_away": sc.your_walk_away, "target": sc.your_target,
            "rounds": sc.rounds, "seconds_left": _seconds_left()}


class MoveReq(BaseModel):
    day: int
    your_offers: list[float] = Field(..., max_length=100)      # the player's asks so far, oldest first
    house_offers: list[float] = Field(default=[], max_length=100)   # the House's prior offers
    rounds_left: int


@app.post("/par/house_move")
def move(req: MoveReq) -> dict:
    """The House's move this round — played by the SNHP equilibrium. Never leaks the
    House's reservation; returns only its action + offer + message."""
    if req.day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    if req.rounds_left < 1:
        raise HTTPException(status_code=400, detail="rounds_left must be >= 1")
    sc = DECK[req.day % len(DECK)]
    rec = house_move(sc, req.your_offers, req.house_offers, req.rounds_left)
    return {"action": rec["action"], "offer": rec.get("recommended_price"),
            "message": rec.get("message", "")}


class GradeReq(BaseModel):
    day: int
    close: Optional[float] = None       # the agreed price, or None if the player walked


@app.post("/par/grade")
def grade(req: GradeReq) -> dict:
    """Reveal: par (the number a perfect player reaches) and what was left on the table.
    Only here is the House's reservation surfaced — at the end, never before. Returns the
    SAME shape whether or not a deal closed (deal is null on a walk)."""
    if req.day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    sc = DECK[req.day % len(DECK)]
    if req.close is not None:                        # same anti-forgery bound as /par/submit
        beats = (req.close > sc.house_reservation + 0.01) if sc.player_side == "sell" \
            else (req.close < sc.house_reservation - 0.01)
        if beats:
            raise HTTPException(status_code=400, detail="impossible close: beats the House's reservation")
    s = score(sc, req.close)                         # par, deal, pct_of_par, left_on_table
    return _with_agent(sc, s)


def _with_agent(sc: Scenario, s: dict) -> dict:
    """Attach the agent-upsell figures, graded in the player's direction."""
    ag, p = agent_close(sc), s["par"]
    s["agent_close"] = ag
    s["agent_pct"] = round((ag / p if sc.player_side == "sell" else p / ag) * 100, 1)
    return s


# ── scoreboard: streak, percentile, distribution (the virality layer) ─────────
class SubmitReq(BaseModel):
    day: int
    user_id: str = Field(..., max_length=64)   # anon device id or account id
    close: Optional[float] = None       # the agreed price, or None on a walk
    your_offers: list[float] = Field(default=[], max_length=100)   # the transcript: your asks
    house_offers: list[float] = Field(default=[], max_length=100)  # ...and the House's offers


def _validate_close(sc: Scenario, req: SubmitReq) -> None:
    """Anti-forgery: a close the House could never have agreed to is rejected, not clamped
    (clamping rewarded forged closes with a perfect 100%). And when a transcript is sent,
    the close must be a number that was actually on the table."""
    if req.close is None:
        return
    beats_par = (req.close > sc.house_reservation + 0.01) if sc.player_side == "sell" \
        else (req.close < sc.house_reservation - 0.01)
    if beats_par:
        raise HTTPException(status_code=400, detail="impossible close: beats the House's reservation")
    if len(req.your_offers) > sc.rounds or len(req.house_offers) > sc.rounds + 1:
        raise HTTPException(status_code=400, detail="transcript longer than the round limit")
    offers = list(req.your_offers) + list(req.house_offers)
    if offers and not any(abs(req.close - o) < 0.01 for o in offers):
        raise HTTPException(status_code=400, detail="close not found in the transcript")


@app.post("/par/submit")
def submit(req: SubmitReq) -> dict:
    """Grade AND record a finished game, then return the reveal payload plus the board:
    streak, percentile vs. everyone today, and the distribution. The score is recomputed
    here and the close is validated against par + the transcript — the board can't be
    gamed by POSTing a fake number. The transcript lands in `plays` (the data moat)."""
    if req.day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    sc = DECK[req.day % len(DECK)]
    _validate_close(sc, req)
    s = _with_agent(sc, score(sc, req.close))
    board = scoreboard.record(req.day, req.user_id, s["pct_of_par"], req.close is None,
                              side=sc.player_side, scenario=sc.title, close=req.close,
                              your_offers=req.your_offers, house_offers=req.house_offers)
    return {**s, **board}


@app.get("/par/stats")
def stats(day: Optional[int] = None) -> dict:
    """Anonymous day rollup — drives the landing's live social proof ('N hit par today')
    and the empty-state histogram before the player has finished."""
    if day is not None and day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    n = _day_number(day)
    return {"no": n, **scoreboard.stats(n)}


# ── friends leaderboard (the spread loop: beat your friends, not the crowd) ────
class JoinReq(BaseModel):
    group: str = Field(..., max_length=64)
    user_id: str = Field(..., max_length=64)
    name: Optional[str] = Field(default=None, max_length=40)


@app.post("/par/group/join")
def group_join(req: JoinReq) -> dict:
    """Join a friend group. The group id rides in on a shared link (par.game/?g=<id>);
    opening a friend's link is what seeds the group."""
    scoreboard.join_group(req.group, req.user_id, req.name or req.user_id)
    return {"group": req.group, "ok": True}


@app.get("/par/group")
def group(group: str, day: Optional[int] = None) -> dict:
    """Today's ranked leaderboard for one friend group."""
    if day is not None and day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    return scoreboard.group_board(group, _day_number(day))


# ── funnel: waitlist + event instrumentation (the growth loop, measured) ───────
class WaitReq(BaseModel):
    user_id: str = Field(..., max_length=64)
    scenario: str = Field(..., max_length=64)
    contact: Optional[str] = Field(default=None, max_length=128)   # email/phone — optional


@app.post("/par/waitlist")
def waitlist(req: WaitReq) -> dict:
    """Join the product waitlist (the CTA's real destination). Idempotent per user."""
    size = funnel.join_waitlist(req.user_id, req.scenario, req.contact)
    funnel.record_event(req.user_id, "waitlist", {"scenario": req.scenario})
    return {"ok": True, "size": size}


class EventReq(BaseModel):
    user_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=32)   # play | share | cta_view | cta_click | waitlist
    meta: Optional[dict] = None


@app.post("/par/event")
def event(req: EventReq) -> dict:
    """A funnel event. Fire-and-forget from the client so we can see where it leaks."""
    funnel.record_event(req.user_id, req.name, req.meta)
    return {"ok": True}


@app.get("/par/funnel")
def funnel_stats() -> dict:
    """The funnel: unique users per step + step-over-step conversion (the k-factor lens)."""
    return funnel.funnel()


# ── the agent, on a REAL deal (the MVP behind the CTA) ────────────────────────
class AdviseReq(BaseModel):
    side: str = Field(..., max_length=8)   # "sell" | "buy" — YOUR side in the real negotiation
    walk_away: float
    target: float
    counterparty_offers: list[float] = Field(default=[], max_length=100)
    my_previous_offers: list[float] = Field(default=[], max_length=100)
    rounds_left: int = 4


@app.post("/par/advise")
def advise(req: AdviseReq) -> dict:
    """The agent advising your live negotiation — the SAME SNHP equilibrium the game runs,
    now pointed at a real deal. Advisory MVP (a move at a time) before full agent-to-agent;
    it's the conversion the game's 'the agent beat you by $X' has been earning."""
    try:
        rec = negotiate_turn(side=req.side, walk_away=req.walk_away, target=req.target,
                             counterparty_offers=req.counterparty_offers,
                             my_previous_offers=req.my_previous_offers, rounds_left=req.rounds_left)
    except NegotiationInputError as e:                   # bad input is a 400; real bugs still 500
        raise HTTPException(status_code=400, detail=str(e))
    # log every advise call — this is the paid product's usage + eval data (billing later)
    with store_conn() as c:
        c.execute("INSERT INTO advice (side, walk_away, target, offers, action, price) "
                  "VALUES (?,?,?,?,?,?)",
                  (req.side, req.walk_away, req.target, json.dumps(req.counterparty_offers),
                   rec["action"], rec.get("recommended_price")))
        c.commit()
    return {"action": rec["action"], "recommended_price": rec.get("recommended_price"),
            "message": rec.get("message", ""), "rationale": rec.get("rationale", ""),
            "expected_settlement": rec.get("expected_settlement")}


# ── multi-issue day (logrolling, graded by gt_negotiate_bundle) ───────────────
class BundleReq(BaseModel):
    issues: list[dict]                  # {name, options, my_utility, their_utility}
    their_offers: Optional[list[dict]] = None
    my_priorities: Optional[dict] = None


@app.post("/par/bundle_move")
def bundle_move(req: BundleReq) -> dict:
    """Multi-issue: the House proposes the SNHP package; par is the Pareto/Nash optimal
    it returns. The front end renders this as the logroll diagonal (see SPEC.md)."""
    rec = negotiate_bundle(issues=req.issues, their_offers=req.their_offers,
                           my_priorities=req.my_priorities)
    return rec


# DEMO seeds — LOCAL DEV ONLY. Never in production: fake rows would fabricate the social
# proof and pollute `results`/`plays`, the data asset. Runs only when there's no Postgres
# (local SQLite) or when PAR_DEMO=1 is set explicitly. On a startup hook, not at import —
# a slow/unreachable DB must not crash-loop the app before /health can answer.
@app.on_event("startup")
def _seed_demo_if_local() -> None:
    if os.environ.get("DATABASE_URL") and os.environ.get("PAR_DEMO") != "1":
        return
    for _d in {_day_number(None), 0, 1, 2, 3, 214, 216}:
        scoreboard.seed_demo(_d)
        scoreboard.seed_group_demo("demo", _d)

# Serve the SPA same-origin so the front end's fetch() calls need no CORS. The /par/*
# routes above are matched before this catch-all mount. `uvicorn par.api:app` now serves
# the whole game at / (index.html) and the API under /par/*.
_WEB = os.path.join(os.path.dirname(__file__), "web")
app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")

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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from gametheory.negotiation.par_game import Scenario, house_move, score, agent_close
from gametheory.negotiation.bundle import negotiate_bundle
from par import scoreboard

app = FastAPI(title="PAR", description="out-negotiate a perfect AI, daily")

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
    your_offers: list[float]            # the player's asks so far, oldest first
    house_offers: list[float] = []      # the House's prior offers
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
    user_id: str                        # anon device id or account id
    close: Optional[float] = None       # the agreed price, or None on a walk


@app.post("/par/submit")
def submit(req: SubmitReq) -> dict:
    """Grade AND record a finished game, then return the reveal payload plus the board:
    streak, percentile vs. everyone today, and the distribution. Logged-in players call
    this instead of /par/grade. The score is recomputed here — never trusted from the
    client — so the board can't be gamed."""
    if req.day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    sc = DECK[req.day % len(DECK)]
    s = _with_agent(sc, score(sc, req.close))
    board = scoreboard.record(req.day, req.user_id, s["pct_of_par"], req.close is None)
    return {**s, **board}


@app.get("/par/stats")
def stats(day: Optional[int] = None) -> dict:
    """Anonymous day rollup — drives the landing's live social proof ('N hit par today')
    and the empty-state histogram before the player has finished."""
    if day is not None and day < 0:
        raise HTTPException(status_code=400, detail="day must be >= 0")
    n = _day_number(day)
    return {"no": n, **scoreboard.stats(n)}


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


# DEMO: seed a believable spread for today + the deck-index days used in replay/testing,
# so /par/stats and the reveal histogram render alive offline. Remove with the real table.
for _d in {_day_number(None), 0, 1, 2, 3}:
    scoreboard.seed_demo(_d)

"""PAR golden tests — guard the deck, the scoring, and the anti-forgery rules.

The moat claim is "par is REAL"; these tests are what keeps a deck edit from shipping a
broken or trivial par (SPEC §1's reachable-but-hard rule), and what keeps the board
honest (impossible closes rejected, transcripts recorded).

Run:  python3 -m pytest par/tests/ -q
"""
import os
import tempfile

import pytest

# isolate the store BEFORE importing par modules (par/_store.py reads env at import)
_TMPDB = os.path.join(tempfile.mkdtemp(prefix="par-test-"), "test.db")
os.environ["GT_KEYS_DB"] = _TMPDB
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

import par.api as api  # noqa: E402
from gametheory.negotiation.par_game import par as par_of, play_out, score, forensics  # noqa: E402

client = TestClient(api.app)


# ── the deck: par must be reachable-but-hard for every scenario ────────────────
@pytest.mark.parametrize("sc", api.DECK, ids=[s.title for s in api.DECK])
def test_deck_par_is_sane(sc):
    p = par_of(sc)
    assert p > 0
    # a perfect close scores exactly 100, in both directions
    assert score(sc, p)["pct_of_par"] == 100.0
    # your walk-away is worse than par (there is a game to play at all)
    if sc.player_side == "sell":
        assert sc.your_walk_away < p < sc.your_target
    else:
        assert sc.your_target < p < sc.your_walk_away


@pytest.mark.parametrize("sc", api.DECK, ids=[s.title for s in api.DECK])
def test_deck_plays_out_on_the_live_engine(sc):
    """The House must actually respond (engine wiring) and a full line must terminate."""
    lo, hi = sorted((sc.your_target, sc.your_walk_away))
    line = [sc.your_target, (lo + hi) / 2, (lo + hi) / 2]  # concede toward the middle
    res = play_out(sc, [round(x, 2) for x in line])
    assert res["transcript"], "the House never moved"
    assert 0.0 <= res["pct_of_par"] <= 100.0
    assert res["left_on_table"] >= 0


def test_score_direction_and_walk():
    sell = api.DECK[0]
    worse, better = sorted((par_of(sell) - 10, par_of(sell) - 1))
    assert score(sell, better)["pct_of_par"] > score(sell, worse)["pct_of_par"]
    walk = score(sell, None)
    assert walk["deal"] is None and walk["pct_of_par"] == 0.0 and walk["left_on_table"] > 0


# ── anti-forgery: the board can't be gamed ─────────────────────────────────────
def test_submit_rejects_impossible_close():
    r = client.post("/par/submit", json={"day": 0, "user_id": "t_forge", "close": 99999})
    assert r.status_code == 400 and "impossible" in r.json()["detail"]


def test_submit_rejects_close_not_in_transcript():
    r = client.post("/par/submit", json={"day": 0, "user_id": "t_forge2", "close": 100,
                                         "your_offers": [130, 120], "house_offers": [95, 103]})
    assert r.status_code == 400 and "transcript" in r.json()["detail"]


def test_submit_records_the_play_transcript():
    body = {"day": 0, "user_id": "t_moat", "close": 111,
            "your_offers": [130, 120, 111], "house_offers": [95, 103]}
    r = client.post("/par/submit", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["par"] == 118 and 0 < d["pct_of_par"] <= 100 and "distribution" in d
    from par._store import conn
    with conn() as c:
        row = c.execute("SELECT side, close, your_offers, ts FROM plays WHERE user_id=?",
                        ("t_moat",)).fetchone()
    assert row is not None and row[0] == "sell" and row[1] == 111
    assert "130" in row[2] and row[3] is not None      # transcript + timestamp stored


def test_grade_rejects_impossible_close_too():
    r = client.post("/par/grade", json={"day": 2, "close": 1})   # buy day: below the floor
    assert r.status_code == 400


# ── forensics: the mistake is named, both directions ──────────────────────────
def test_forensics_overconcede_sell():
    f = forensics(api.DECK[0], 110, [130, 110], [95, 103])
    assert f["kind"] == "overconcede" and f["move"] == 2
    assert f["you_gave"] == 20.0 and f["house_gave"] == 8.0
    assert 0 < f["cost"] <= 8                            # capped by what was actually left


def test_forensics_early_accept():
    f = forensics(api.DECK[0], 103, [130], [95, 103])    # took the standing offer, rounds left
    assert f["kind"] == "early_accept" and f["house_gave"] == 8.0 and f["cost"] == 15


def test_forensics_walk_and_at_par():
    assert forensics(api.DECK[0], None, [130, 125], [95, 103])["kind"] == "walk"
    assert forensics(api.DECK[0], 118, [130, 118], [95, 103]) is None   # at par: no fault


def test_forensics_buy_direction():
    f = forensics(api.DECK[2], 12500, [9000, 12500], [13000, 12800])
    assert f["kind"] == "overconcede" and f["you_gave"] == 3500.0 and f["cost"] == 1300


def test_submit_returns_forensic():
    r = client.post("/par/submit", json={"day": 0, "user_id": "t_forensic", "close": 110,
                                         "your_offers": [130, 110], "house_offers": [95, 103]})
    assert r.status_code == 200
    f = r.json()["forensic"]
    assert f and f["kind"] == "overconcede" and f["move"] == 2


# ── the funnel + waitlist capture what the business needs ──────────────────────
def test_waitlist_stores_contact():
    r = client.post("/par/waitlist", json={"user_id": "t_wl", "scenario": "x",
                                           "contact": "a@b.com"})
    assert r.status_code == 200 and r.json()["ok"]
    from par._store import conn
    with conn() as c:
        got = c.execute("SELECT contact FROM waitlist WHERE user_id=?", ("t_wl",)).fetchone()
    assert got == ("a@b.com",)


def test_advise_is_logged():
    r = client.post("/par/advise", json={"side": "sell", "walk_away": 90, "target": 130,
                                         "counterparty_offers": [95], "rounds_left": 4})
    assert r.status_code == 200 and r.json()["action"] in ("counter", "accept", "walk")
    from par._store import conn
    with conn() as c:
        n = c.execute("SELECT count(*) FROM advice").fetchone()[0]
    assert n >= 1


def test_today_shape():
    d = client.get("/par/today").json()
    for k in ("no", "side", "title", "walk_away", "target", "rounds", "seconds_left"):
        assert k in d
    assert d["side"] in ("sell", "buy")

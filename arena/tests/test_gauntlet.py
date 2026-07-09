"""Gauntlet protocol + scoring tests — all offline (engine/naive seats only)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from arena.gauntlet.agents import Action, EngineSeat, LLMSeat, NaiveSeat, SeatView
from arena.gauntlet.protocol import (
    BATNA, DEADLINE, aggregate, gen_gauntlet_scenarios, run_match,
)
from arena.gauntlet.run import merge_artifact, run_gauntlet


@pytest.fixture(scope="module")
def scenarios():
    return gen_gauntlet_scenarios(6, seed=123)


def test_scenarios_deterministic():
    a = gen_gauntlet_scenarios(4, seed=99)
    b = gen_gauntlet_scenarios(4, seed=99)
    for (sa, wsa, wba), (sb, wsb, wbb) in zip(a, b):
        assert sa.seller_dirs == sb.seller_dirs
        assert np.allclose(wsa, wsb) and np.allclose(wba, wbb)


def test_engine_vs_engine_near_frontier(scenarios):
    """The engine reference row should close deals and land near the frontier —
    this is the arena science's raw-at-ceiling result reproduced in the gauntlet."""
    results = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            r = run_match(EngineSeat(1000 + sid), sc, w_s, w_b, role=role,
                          condition="engine", scenario_id=sid, match_seed=1000 + sid)
            results.append(r)
    row = aggregate(results)
    assert row["deal_rate"] >= 0.8
    assert row["capture"] >= 0.85


def test_naive_leaves_money(scenarios):
    """The naive splitter should close (it concedes) but capture less than the
    engine row — the gap IS the leaderboard's story."""
    naive_res, eng_res = [], []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            naive_res.append(run_match(NaiveSeat(), sc, w_s, w_b, role=role,
                                       condition="naive", scenario_id=sid,
                                       match_seed=2000 + sid))
            eng_res.append(run_match(EngineSeat(2000 + sid), sc, w_s, w_b,
                                     role=role, condition="engine",
                                     scenario_id=sid, match_seed=2000 + sid))
    n, e = aggregate(naive_res), aggregate(eng_res)
    assert n["deal_rate"] > 0.5
    assert e["capture"] >= n["capture"] - 0.02   # engine at least matches naive
    assert n["dollars_left"] >= 0.0


def test_match_determinism(scenarios):
    sc, w_s, w_b = scenarios[0]
    r1 = run_match(EngineSeat(7), sc, w_s, w_b, role="seller",
                   condition="engine", scenario_id=0, match_seed=7)
    r2 = run_match(EngineSeat(7), sc, w_s, w_b, role="seller",
                   condition="engine", scenario_id=0, match_seed=7)
    assert r1.to_dict() == r2.to_dict()


def test_scoring_bounds(scenarios):
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        r = run_match(NaiveSeat(), sc, w_s, w_b, role="buyer",
                      condition="naive", scenario_id=sid, match_seed=sid)
        assert 0.0 <= r.capture <= 1.0 + 1e-9
        assert r.frontier_best >= r.frontier_naive - 1e-9
        assert r.dollars_left >= 0.0
        if not r.deal:
            assert r.u_candidate == pytest.approx(BATNA)


def test_walk_scores_batna(scenarios):
    class Walker:
        name = "walker"
        def act(self, view):
            return Action("walk")
    sc, w_s, w_b = scenarios[0]
    r = run_match(Walker(), sc, w_s, w_b, role="seller",
                  condition="solo", scenario_id=0, match_seed=1)
    assert not r.deal and r.walked_by == "candidate"
    assert r.u_candidate == pytest.approx(BATNA)
    assert r.dollars_left > 0.0    # frontier ≥ 1.0 > 2*BATNA: walking leaves money


def test_llm_parse_and_fallback(scenarios):
    """Strict JSON parsing: valid offers normalize; junk falls back safely."""
    sc, w_s, w_b = scenarios[0]
    seat = LLMSeat("scripted-naive", "test")
    names = [n for n, _ in sc.issues]
    view = SeatView(role="seller",
                    issues=[{"name": n, "options": list(labels),
                             "my_utility": list(d), "their_utility": list(d)}
                            for (n, labels), d in zip(sc.issues, sc.seller_dirs)],
                    weights={n: 0.25 for n in names},
                    my_offers=[], opp_offers=[], turn=0, deadline=DEADLINE)
    good = json.dumps({"action": "offer",
                       "package": {iss["name"]: iss["options"][0]
                                   for iss in view.issues}})
    act = LLMSeat._parse(good, view)
    assert act and act.kind == "offer" and len(act.package) == len(names)
    assert LLMSeat._parse("gibberish", view) is None
    assert LLMSeat._parse('{"action":"offer","package":{"price":"nope"}}', view) is None
    assert LLMSeat._parse('{"action":"accept"}', view) is None  # no opp offer yet
    # scripted seat never hits the network and always returns a legal action
    a = seat.act(view)
    assert a.kind in ("offer", "accept", "walk")


def test_genome_seat_plays_and_is_deterministic(scenarios):
    """The evolved-champion seat: policy genes over the engine advisor —
    closes deals, scores sanely, and reproduces exactly (leaderboard-grade)."""
    from arena.genome import Genome
    from arena.gauntlet.agents import GenomeSeat
    g = Genome(tactic_family="mirror", bundle_tactic=(0.3, -0.05, 0.04))
    res = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios[:3]):
        for role in ("seller", "buyer"):
            res.append(run_match(GenomeSeat(g, 500 + sid), sc, w_s, w_b,
                                 role=role, condition="solo", scenario_id=sid,
                                 match_seed=500 + sid))
    row = aggregate(res)
    assert row["deal_rate"] >= 0.5
    assert 0.5 <= row["capture"] <= 1.0 + 1e-9
    sc, w_s, w_b = scenarios[0]
    r1 = run_match(GenomeSeat(g, 500), sc, w_s, w_b, role="seller",
                   condition="solo", scenario_id=0, match_seed=500)
    r2 = run_match(GenomeSeat(g, 500), sc, w_s, w_b, role="seller",
                   condition="solo", scenario_id=0, match_seed=500)
    assert r1.to_dict() == r2.to_dict()


def test_http_seat_roundtrip_and_fallback(scenarios):
    """A community bot behind a real local HTTP endpoint: plays legal moves,
    falls back on garbage replies, aborts on a dead endpoint."""
    import http.server
    import threading

    from arena.gauntlet.agents import HTTPSeat

    class Bot(http.server.BaseHTTPRequestHandler):
        mode = "play"

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["protocol"] == "snhp-gauntlet/1"
            if Bot.mode == "play":   # accept when possible, else open mid-ish
                if body["their_offers"]:
                    out = {"action": "accept"}
                else:
                    out = {"action": "offer", "package": {
                        i["name"]: i["options"][len(i["options"]) // 2]
                        for i in body["issues"]}}
            else:                    # garbage → format-failure path
                out = {"action": "chaos"}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Bot)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    try:
        sc, w_s, w_b = scenarios[0]
        seat = HTTPSeat(url, name="test-bot")
        r = run_match(seat, sc, w_s, w_b, role="buyer", condition="solo",
                      scenario_id=0, match_seed=42)
        assert r.deal and r.format_failures == 0     # accepted the engine's opener
        Bot.mode = "garbage"
        seat2 = HTTPSeat(url, name="test-bot")
        r2 = run_match(seat2, sc, w_s, w_b, role="buyer", condition="solo",
                       scenario_id=0, match_seed=42)
        assert r2.format_failures > 0                # counted, run completed
    finally:
        srv.shutdown()
    dead = HTTPSeat("http://127.0.0.1:1/", name="dead-bot", max_retries=0)
    with pytest.raises(RuntimeError):
        run_match(dead, scenarios[0][0], scenarios[0][1], scenarios[0][2],
                  role="buyer", condition="solo", scenario_id=0, match_seed=42)


def test_eval_seed_isolation(tmp_path):
    """Ranking artifacts (held-out label) refuse to merge with practice runs,
    and eval scenario sets differ from the practice set."""
    from arena.gauntlet.run import SCENARIO_SEED
    a = gen_gauntlet_scenarios(3, SCENARIO_SEED)
    b = gen_gauntlet_scenarios(3, 987654321)         # any other seed
    assert any(sa.seller_dirs != sb.seller_dirs for (sa, _, _), (sb, _, _) in zip(a, b))
    entry = run_gauntlet("engine:", ["solo"], 3, verbose=False)
    entry["author"] = None
    out = tmp_path / "leaderboard.json"
    art = merge_artifact(out, entry, 3, DEADLINE, seed_label="held-out-v1")
    art.pop("matches")
    out.write_text(json.dumps(art))
    with pytest.raises(SystemExit):                  # practice label ≠ held-out label
        merge_artifact(out, entry, 3, DEADLINE, seed_label=SCENARIO_SEED)


def test_run_gauntlet_offline_and_merge(tmp_path):
    entry = run_gauntlet("scripted-naive:naive-test", ["solo"], 3, verbose=False)
    assert entry["conditions"]["solo"]["matches"] == 6      # 3 scenarios x 2 roles
    out = tmp_path / "leaderboard.json"
    art = merge_artifact(out, entry, 3, DEADLINE)
    out.write_text(json.dumps(art))
    # a second model merges without clobbering the first
    entry2 = run_gauntlet("engine:", ["solo"], 3, verbose=False)
    art2 = merge_artifact(out, entry2, 3, DEADLINE)
    assert "naive-test" in art2["rows"] and "engine" in art2["rows"]
    assert all(m["model"] in ("naive-test", "engine") for m in art2["matches"])

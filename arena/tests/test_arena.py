"""Arena backend tests: determinism, energy conservation, crossover validity,
matching stability, event coverage, and the HTTP surface."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from arena.config import CONFIG
from arena.world import World
from arena.events import hash_events
from arena.genome import ARCHETYPES, BLOCKS, TACTIC_FAMILIES, mutate, Genome
from arena.credit import Scorecard
from arena.courtship import Suitor, build_matching, run_courtship


def _run(seed, gens):
    w = World(dataclasses.replace(CONFIG, seed=seed))
    evs = []
    for _ in range(gens):
        evs.extend(list(w.generation_events()))
    return w, evs


# ── determinism ──────────────────────────────────────────────────────────
def test_same_seed_identical_log():
    _, a = _run(42, 3)
    _, b = _run(42, 3)
    assert hash_events(a) == hash_events(b)
    assert len(a) > 100


def test_different_seed_differs():
    _, a = _run(42, 3)
    _, b = _run(7, 3)
    assert hash_events(a) != hash_events(b)


# ── energy conservation ──────────────────────────────────────────────────
def test_energy_ledger_balances():
    w, _ = _run(11, 25)
    bal = w.energy_balance()
    assert abs(bal["total"] - bal["expected"]) < 1e-6, bal


# ── crossover validity ───────────────────────────────────────────────────
def test_crossover_produces_valid_genomes():
    rng = np.random.default_rng(3)
    suitors = []
    for i, (name, g) in enumerate(ARCHETYPES.items()):
        sc = Scorecard()
        for _ in range(6):
            sc.update(g, rng.uniform(0.2, 0.9))
        suitors.append(Suitor(i, g, rng.uniform(150, 400), rng.uniform(0, 1), sc, g.staked))
    pairs, ev = build_matching(suitors, CONFIG, rng)
    assert ev["blocking_pairs"] == []  # deferred acceptance is stable
    n_children = 0
    for pa, pb in pairs:
        gen = run_courtship(pa, pb, CONFIG, 0.05, rng, 555 + pa.id)
        out = None
        try:
            while True:
                next(gen)
        except StopIteration as e:
            out = e.value
        if out.matched:
            n_children += 1
            g = out.child_genome
            for v in (g.pareto_knob, g.open_aggression, g.walk_margin, g.patience, g.truncation):
                assert 0.0 <= v <= 1.0
            assert abs(sum(g.bundle_focus) - 1.0) < 1e-3
            assert g.tactic_family in TACTIC_FAMILIES
            assert isinstance(g.staked, bool)
        else:
            # impasse: both parents survive (world charges the cost separately)
            assert out.impasse
    assert n_children >= 1


def test_mutation_stays_in_range():
    rng = np.random.default_rng(1)
    g = ARCHETYPES["Merchant"]
    for _ in range(200):
        g = mutate(g, 0.3, rng, 0.1, 0.1)
        for v in (g.pareto_knob, g.open_aggression, g.walk_margin, g.patience, g.truncation):
            assert 0.0 <= v <= 1.0
        assert abs(sum(g.bundle_focus) - 1.0) < 1e-3


# ── mating market stability across a live run ────────────────────────────
def test_matching_stable_over_run():
    w, evs = _run(23, 10)
    rounds = [e for e in evs if e["type"] == "mating.round"]
    assert rounds, "expected mating rounds"
    for r in rounds:
        assert r["blocking_pairs"] == []


# ── event coverage: a healthy run exercises the whole grammar ─────────────
def test_event_grammar_coverage():
    w, evs = _run(7, 45)  # long enough for senescence + starvation deaths
    types = {e["type"] for e in evs}
    for required in ("neg.start", "neg.offer", "neg.accept", "neg.walk",
                     "court.start", "court.accept", "agent.birth", "agent.death",
                     "census", "leaderboard", "species.update", "gen.end", "highlight",
                     "bloom"):
        assert required in types, f"missing {required}"


def test_population_bounded():
    w, _ = _run(7, 60)
    assert CONFIG.pop_floor <= len(w.agents) <= CONFIG.pop_cap


# ── the research instrument runs (tiny sizes; correctness, not the numbers) ─
def test_science_instrument_runs():
    from arena import science as sci
    a = sci.assembly(trials=3, gens=8)
    assert set(a) == {"negotiated", "uniform", "blend"}
    d = sci.decompose(gens=8, seed=3)
    assert 0.0 <= d["surplus_frac"] <= 1.0
    # neutral null: the null truly decouples selection (both modes run)
    from arena.world import World
    import dataclasses as _dc
    wn = World(_dc.replace(CONFIG, seed=1), neutral=True)
    for _ in range(3):
        list(wn.generation_events())
    assert wn.neutral is True


def test_concession_layer_evolvable_and_neutral_default():
    from arena.genome import Genome, mutate
    import numpy as np
    # default is neutral (all-zero) so balance is preserved
    assert Genome().concession == (0.0, 0.0, 0.0, 0.0)
    # mutation reaches it
    g = Genome()
    rng = np.random.default_rng(0)
    for _ in range(30):
        g = mutate(g, 0.2, rng, 0.05, 0.05)
    assert any(abs(c) > 1e-6 for c in g.concession)
    # round-trips through the event dict (to_dict serializes at 4 decimals)
    rt = Genome.from_dict(g.to_dict())
    assert all(abs(a - b) < 1e-4 for a, b in zip(rt.concession, g.concession))
    # the multi-issue ceiling (bundle_tactic) is likewise neutral-by-default,
    # evolvable, and round-trips
    assert Genome().bundle_tactic == (0.0, 0.0, 0.0)
    assert any(abs(c) > 1e-6 for c in g.bundle_tactic)
    assert all(abs(a - b) < 1e-4 for a, b in zip(rt.bundle_tactic, g.bundle_tactic))


# ── the forge loop: a viewer champion becomes a real agent ────────────────
def test_champion_pipeline(monkeypatch):
    monkeypatch.setenv("ARENA_NO_RUN", "1")
    from fastapi.testclient import TestClient
    import importlib
    import arena.api as api
    importlib.reload(api)
    with TestClient(api.app) as client:
        r = client.post("/arena/champion", json={
            "token": "t1", "house": "Ryu", "tactic": "closer",
            "boldness": 0.8, "bluff": 0.6, "patience": 0.4})
        assert r.status_code == 200 and r.json()["queued"] is True
        assert client.post("/arena/champion", json={
            "token": "t2", "tactic": "nonsense"}).status_code == 400
        # the queued spec becomes a live agent at the generation boundary
        w = api.RUNNER.world
        evs = list(w.generation_events())
        imm = [e for e in evs if e["type"] == "immigration" and e.get("challenger")]
        assert imm and imm[0]["sponsor_token"] == "t1"
        assert w.agents[imm[0]["id"]].genome.tactic_family == "closer"


def test_tactics_are_load_bearing():
    """The same advisor, different follow-discipline: tactics must produce a
    real income/deal-rate spread (strategy is not a cosmetic label)."""
    import dataclasses
    from arena.genome import ARCHETYPES, TACTIC_FAMILIES
    from arena.scenarios import gen_price_scenario, era_center
    from arena.executor import Side, run_price_negotiation
    rng = np.random.default_rng(3)
    base = ARCHETYPES["Merchant"]
    income = {}
    for tactic in ("anchorer", "conceder"):
        r = np.random.default_rng(3)
        tot = 0.0
        for i in range(80):
            scn = gen_price_scenario(CONFIG, "symmetric", 0.5, r)
            focal = dataclasses.replace(base, tactic_family=tactic,
                                        open_aggression=0.6, pareto_knob=0.6)
            opp = dataclasses.replace(base, tactic_family=TACTIC_FAMILIES[i % 6])
            g = run_price_negotiation(Side(focal, "seller", scn.r_s, 1),
                                      Side(opp, "buyer", scn.r_b, 2), scn, 11, 9000 + i, CONFIG)
            try:
                while True:
                    next(g)
            except StopIteration as e:
                if e.value.deal:
                    tot += e.value.surplus_seller
        income[tactic] = tot
    # the brinkman must out-earn the volume-dealer per deal by a real margin
    assert income["anchorer"] > income["conceder"] * 1.05, income


# ── HTTP surface ─────────────────────────────────────────────────────────
def test_http_endpoints(monkeypatch):
    monkeypatch.setenv("ARENA_NO_RUN", "1")
    from fastapi.testclient import TestClient
    import importlib
    import arena.api as api
    importlib.reload(api)
    with TestClient(api.app) as client:
        h = client.get("/health").json()
        assert h["ok"] is True and h["service"] == "arena"
        st = client.get("/arena/state").json()
        assert "agents" in st and len(st["agents"]) == CONFIG.pop_start
        cs = client.get("/arena/census").json()
        assert cs["pop"] == CONFIG.pop_start
        stats = client.get("/arena/stats").json()
        assert "keystone" in stats["honest_claims"]
        assert "Nothing in this arena" in stats["honest_claims"]["keystone"]

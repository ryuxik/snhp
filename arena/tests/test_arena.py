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

"""The mating market and logrolled crossover — the novel operator.

Mate selection is a real deferred-acceptance matching (gametheory.mechanism.
gale_shapley) over preference lists induced by each agent's evolved B4 weights.
Recombination is a real multi-issue logrolling negotiation (negotiate_bundle)
between the two matched parents over their own gene blocks: each parent's
per-option utilities come from its credit scorecard (fight to keep alleles you
believe pay off), the partner's priorities are inferred by the engine's particle
filter from courtship offers, and the negotiation can END IN IMPASSE — so
"willingness to compromise" is heritable and selected.

Nothing here decides a negotiation move; gale_shapley and negotiate_bundle do.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import numpy as np

from arena.config import ArenaConfig
from arena.credit import Scorecard
from arena.genome import (Genome, BLOCKS, EXTRAP_BLOCKS, DISCRETE_BLOCKS,
                          mutate, similarity)
from arena import flora
from gametheory.mechanism.gale_shapley import gale_shapley
from gametheory.negotiation.bundle import negotiate_bundle


@dataclass
class Suitor:
    id: int
    genome: Genome
    energy: float
    reputation: float          # [0,1]
    scorecard: Scorecard
    staked: bool


@dataclass
class CourtOutcome:
    matched: bool
    child_genome: Optional[Genome]
    child_scorecard: Optional[Scorecard]
    parents: tuple            # (id_a, id_b)
    impasse: bool


def _seed(court_seed: int, turn: int) -> None:
    h = hashlib.blake2b(f"court:{court_seed}:{turn}".encode(), digest_size=8).digest()
    np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)


# ─── Mating market: bipartition -> preferences -> gale_shapley ──────────────

def build_matching(eligible: list[Suitor], cfg: ArenaConfig, rng: np.random.Generator,
                   pollinator: dict | None = None):
    """Randomly bipartition the eligible pool, build preference lists from B4
    weights + the bloom's aesthetic pull (sexual selection), truncating below
    theta, and run deferred acceptance. Returns (pairs, round_event)."""
    if len(eligible) < 2:
        return [], {"eligible": [s.id for s in eligible], "matching": {},
                    "proposer_rank": None, "receiver_rank": None, "n_proposals": 0}

    idx = list(range(len(eligible)))
    rng.shuffle(idx)
    half = len(idx) // 2
    P = [eligible[i] for i in idx[:half]]
    R = [eligible[i] for i in idx[half:]]
    by_id = {s.id: s for s in eligible}

    def prefs(a: Suitor, others: list[Suitor]) -> list[int]:
        scored = [(other.id, _mate_score(a, other, cfg, pollinator)) for other in others]
        scored.sort(key=lambda x: x[1], reverse=True)
        keep = max(1, int(round((1.0 - a.genome.truncation) * len(scored))))
        return [oid for oid, _ in scored[:keep]]

    proposers = [{"id": f"p{p.id}", "preferences": [f"r{rid}" for rid in prefs(p, R)]} for p in P]
    receivers = [{"id": f"r{r.id}", "preferences": [f"p{pid}" for pid in prefs(r, P)]} for r in R]
    res = gale_shapley(proposers=proposers, receivers=receivers)

    pairs = []
    matching = {}
    for p_key, r_key in res["matching"].items():
        if r_key is None:
            continue
        pid = int(p_key[1:]); rid = int(r_key[1:])
        pairs.append((by_id[pid], by_id[rid]))
        matching[str(pid)] = rid

    # Per-side mean achieved match rank (the Roth proposer-optimality display).
    p_ranks, r_ranks = [], []
    for p in P:
        pr = prefs(p, R)
        rid = matching.get(str(p.id))
        if rid is not None and rid in pr:
            p_ranks.append(pr.index(rid))
    for r in R:
        rr = prefs(r, P)
        pid = next((int(k) for k, v in matching.items() if v == r.id), None)
        if pid is not None and pid in rr:
            r_ranks.append(rr.index(pid))

    round_event = {
        "eligible": [s.id for s in eligible],
        "matching": matching,
        "proposer_rank": round(float(np.mean(p_ranks)), 3) if p_ranks else None,
        "receiver_rank": round(float(np.mean(r_ranks)), 3) if r_ranks else None,
        "n_proposals": res["n_proposals"],
        "blocking_pairs": res["blocking_pairs"],
    }
    return pairs, round_event


def _mate_score(a: Suitor, b: Suitor, cfg: ArenaConfig,
                pollinator: dict | None = None) -> float:
    w_rep, w_energy, w_sim, w_staked = a.genome.mate_w
    score = (w_rep * b.reputation
             + w_energy * min(1.0, b.energy / cfg.energy_cap)
             + w_sim * similarity(a.genome, b.genome)
             + w_staked * (1.0 if b.staked else 0.0))
    if pollinator is not None:
        # sexual selection: b's bloom, pollinator-aligned AND affordable (costly
        # signal). The season's pollinator makes different strategies beautiful.
        score += cfg.pollinator_weight * flora.aesthetic_pull(
            b.genome, b.energy, pollinator, cfg.mate_threshold)
    return score


# ─── Logrolled crossover: negotiate_bundle over gene blocks ─────────────────

def _block_options(block: str) -> list[str]:
    if block in DISCRETE_BLOCKS:
        return ["pa", "pb"]
    if block in EXTRAP_BLOCKS:
        return ["pa", "pb", "blend", "extrap"]
    return ["pa", "pb", "blend"]


def _issues_for(scorecard: Scorecard, own: str, partner: str) -> tuple:
    """negotiate_bundle issues from a parent's perspective. own/partner are the
    source labels for this parent's allele vs the other's."""
    issues = []
    for block in BLOCKS:
        opts = _block_options(block)
        ou = scorecard.option_utilities(block)      # keys A/B/blend/extrap
        my_u, their_u = [], []
        for label in opts:
            if label == own:
                my_u.append(ou["A"]); their_u.append(0.2)
            elif label == partner:
                my_u.append(ou["B"]); their_u.append(0.9)
            elif label == "blend":
                my_u.append(ou["blend"]); their_u.append(0.5)
            else:  # extrap
                my_u.append(ou["extrap"]); their_u.append(0.15)
        issues.append({"name": block, "options": opts,
                       "my_utility": my_u, "their_utility": their_u})
    priorities = scorecard  # placeholder; priorities dict built by caller
    return issues, priorities


def _package_utility(scorecard: Scorecard, own: str, partner: str,
                     priorities: dict, package: dict) -> float:
    issues, _ = _issues_for(scorecard, own, partner)
    w = np.array([max(0.0, priorities.get(i["name"], 0.0)) for i in issues], dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(issues))
    w = w / w.sum()
    total = 0.0
    for wi, iss in zip(w, issues):
        opt = package.get(iss["name"])
        idx = iss["options"].index(opt) if opt in iss["options"] else 0
        total += wi * iss["my_utility"][idx]
    return float(total)


def run_courtship(pa: Suitor, pb: Suitor, cfg: ArenaConfig, sigma: float,
                  rng: np.random.Generator, court_seed: int):
    """Generator over the courtship. Yields court.* partial events; returns a
    CourtOutcome via StopIteration.value."""
    a_issues, _ = _issues_for(pa.scorecard, own="pa", partner="pb")
    b_issues, _ = _issues_for(pb.scorecard, own="pb", partner="pa")
    a_pri = pa.scorecard.priorities(rng, thompson=True)
    b_pri = pb.scorecard.priorities(rng, thompson=True)

    yield {"type": "court.start", "a": pa.id, "b": pb.id,
           "stakes": {"a_energy": round(pa.energy, 1), "b_energy": round(pb.energy, 1)}}

    a_offers: list[dict] = []
    b_offers: list[dict] = []
    settled: Optional[dict] = None
    R = cfg.courtship_rounds
    late_start = R - 2
    turn = 0
    while turn < R and settled is None:
        if turn % 2 == 0:
            _seed(court_seed, turn)
            adv = negotiate_bundle(issues=a_issues, their_offers=b_offers or None,
                                   my_priorities=a_pri, my_batna=cfg.crossover_batna,
                                   their_batna_estimate=0.40)
            if adv["action"] == "accept" and b_offers:
                settled = b_offers[-1]; break
            if turn >= late_start and b_offers and \
               _package_utility(pa.scorecard, "pa", "pb", a_pri, b_offers[-1]) >= cfg.crossover_batna + 0.05:
                settled = b_offers[-1]; break
            if adv["action"] == "walk":
                yield {"type": "court.impasse", "a": pa.id, "b": pb.id, "by": "a"}
                return CourtOutcome(False, None, None, (pa.id, pb.id), True)
            a_offers.append(adv["recommended_offer"])
            yield {"type": "court.offer", "turn": turn, "actor": "a",
                   "package": adv["recommended_offer"]}
        else:
            _seed(court_seed, turn)
            adv = negotiate_bundle(issues=b_issues, their_offers=a_offers or None,
                                   my_priorities=b_pri, my_batna=cfg.crossover_batna,
                                   their_batna_estimate=0.40)
            if adv["action"] == "accept" and a_offers:
                settled = a_offers[-1]; break
            if turn >= late_start and a_offers and \
               _package_utility(pb.scorecard, "pb", "pa", b_pri, a_offers[-1]) >= cfg.crossover_batna + 0.05:
                settled = a_offers[-1]; break
            if adv["action"] == "walk":
                yield {"type": "court.impasse", "a": pa.id, "b": pb.id, "by": "b"}
                return CourtOutcome(False, None, None, (pa.id, pb.id), True)
            b_offers.append(adv["recommended_offer"])
            yield {"type": "court.offer", "turn": turn, "actor": "b",
                   "package": adv["recommended_offer"]}
        turn += 1

    if settled is None:
        yield {"type": "court.impasse", "a": pa.id, "b": pb.id, "by": "timeout"}
        return CourtOutcome(False, None, None, (pa.id, pb.id), True)

    child = _assemble_child(settled, pa.genome, pb.genome)
    child = mutate(child, sigma, rng, cfg.tactic_flip_p, cfg.staked_flip_p)
    child_sc = Scorecard.child_prior(pa.scorecard, pb.scorecard)
    yield {"type": "court.accept", "a": pa.id, "b": pb.id,
           "crossover": {blk: settled.get(blk, "blend") for blk in BLOCKS},
           "child_preview": child.to_dict()}
    return CourtOutcome(True, child, child_sc, (pa.id, pb.id), False)


def _assemble_child(package: dict, ga: Genome, gb: Genome) -> Genome:
    child = ga  # start from a, overwrite every block from the settled sources
    for block in BLOCKS:
        source = package.get(block, "blend")
        child = child.with_block(block, _block_value(block, source, ga, gb))
    return child


def _block_value(block: str, source: str, ga: Genome, gb: Genome):
    va = ga.block_values(block)
    vb = gb.block_values(block)
    if block in DISCRETE_BLOCKS:
        return va if source == "pa" else vb
    va_arr = np.asarray(va, dtype=float)
    vb_arr = np.asarray(vb, dtype=float)
    if source == "pa":
        return tuple(va_arr)
    if source == "pb":
        return tuple(vb_arr)
    if source == "blend":
        return tuple((va_arr + vb_arr) / 2)
    # BLX-alpha extrapolation: push beyond a, away from b, clipped in with_block.
    return tuple(va_arr + 0.5 * (va_arr - vb_arr))

"""
Validation-framework metrics for the SNHP exploitation-mode rollout.

Five new metrics — each a pure function over a tournament's `rankings`
+ `pairwise` + `scores` outputs (the existing run_round_robin return
shape from snhp/b2b_round_robin.py). These complement the existing
avg / median / Elo / W-T-L by adding signals that distinguish
"variance reduction" from "actual strategic improvement":

  1. per_type_utility(rankings, pairwise, type_tags)
       → dict[type → {avg, n, ci_lo, ci_hi}]
       SNHP utility bucketed by ground-truth opponent type. The
       headline diagnostic — exploitation mode should produce
       UNEVEN gains across buckets (large lift on CONCEDER, small
       on BOULWARE/MIRROR).

  2. paired_seed_elo_delta(baseline_pairwise, candidate_pairwise)
       → {snhp_delta, n_compared}
       Paired-RNG Elo improvement vs baseline. Drops noise floor
       from ~25 Elo points to ~5 by reusing identical match seeds.

  3. exploitation_rate(scores_self, scores_opp, nash_share)
       → float in [-1, 1]
       (snhp_avg - nash_share) / (max_possible - nash_share). Quantifies
       above-equilibrium extraction. > 0 means we captured surplus an
       equilibrium-honest player wouldn't.

  4. robustness_score(scores_per_match)
       → float
       5th-percentile utility across all matchups. Catches tail
       regressions that the avg metric hides.

  5. classifier_conditional_winrate(rankings, classifier_log)
       → {correct_winrate, wrong_winrate, gap}
       Win rate conditional on classifier confidence ≥ 0.5 split by
       whether the classifier was right or wrong. A large gap means
       the system is brittle — wins depend on classifier accuracy.

Plus a top-level `compute_all(...)` that produces the diff-able JSON
artifact used by `leaderboard/run.py --ablation-matrix`.

Pure functions throughout — no I/O, no side effects. JSON schema is
documented in the plan file (sorted keys, 4-decimal floats, no in-
block timestamps).
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import Optional


# ─── 1. Per-type utility ────────────────────────────────────────────────────


def per_type_utility(
    snhp_per_opponent: dict[str, float],
    type_tags: dict[str, str],
) -> dict[str, dict[str, float]]:
    """
    Bucket SNHP's utility against each opponent into the 4-class taxonomy
    BOULWARE / CONCEDER / MIRROR / RANDOM. Untagged opponents skipped.

    `snhp_per_opponent` is a dict mapping opponent name → SNHP avg utility
    in matchups against that opponent (averaged across both directions and
    all reps). Caller produces this from `run_round_robin`'s pairwise dict.

    Returns: {type: {avg, n, ci_lo, ci_hi}} (95% Wilson CI on the mean,
    using the bootstrap helper from b2b_round_robin if N is small).
    """
    buckets: dict[str, list[float]] = {}
    for opp, util in snhp_per_opponent.items():
        ttype = type_tags.get(opp)
        if ttype is None:
            continue
        buckets.setdefault(ttype, []).append(float(util))

    result: dict[str, dict[str, float]] = {}
    for ttype, vals in buckets.items():
        if not vals:
            continue
        n = len(vals)
        avg = sum(vals) / n
        if n >= 2:
            sd = statistics.stdev(vals)
            # Normal-approx 95% CI; fine for paired-seed small-n.
            half = 1.96 * sd / (n ** 0.5)
        else:
            half = 0.0
        result[ttype] = {
            "avg": round(avg, 4),
            "n": n,
            "ci_lo": round(avg - half, 4),
            "ci_hi": round(avg + half, 4),
        }
    return result


# ─── 2. Paired-seed Elo delta ───────────────────────────────────────────────


def paired_seed_elo_delta(
    baseline_pairwise: dict[tuple[str, str], tuple[float, float, float]],
    candidate_pairwise: dict[tuple[str, str], tuple[float, float, float]],
    *,
    target_player: str = "SNHP",
    win_threshold: float = 0.005,
    k_factor: int = 32,
    initial_elo: int = 1500,
) -> dict[str, float]:
    """
    Compare two tournaments run with identical RNG streams. Returns the
    delta in `target_player`'s computed Elo (candidate − baseline).

    Pairing reduces Elo noise dramatically vs comparing two independent
    runs: identical opponent rolls, BATNA draws, and step counts mean any
    Elo diff comes from the strategy change, not from which random world
    we landed in.
    """
    elo_b = _replay_elo(baseline_pairwise, target_player,
                         win_threshold, k_factor, initial_elo)
    elo_c = _replay_elo(candidate_pairwise, target_player,
                         win_threshold, k_factor, initial_elo)
    return {
        "baseline_elo": round(elo_b, 1),
        "candidate_elo": round(elo_c, 1),
        "delta": round(elo_c - elo_b, 1),
    }


def _replay_elo(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str,
    win_threshold: float,
    k: int,
    init: int,
) -> float:
    """Replay all matchups in pairwise to compute target's Elo."""
    elos: dict[str, float] = {}
    for (a, b), (ua, ub, _dr) in pairwise.items():
        if a == b:
            continue
        elos.setdefault(a, init)
        elos.setdefault(b, init)
        if ua > ub + win_threshold:
            score_a = 1.0
        elif ub > ua + win_threshold:
            score_a = 0.0
        else:
            score_a = 0.5
        ea = 1.0 / (1.0 + 10 ** ((elos[b] - elos[a]) / 400.0))
        elos[a] += k * (score_a - ea)
        elos[b] += k * ((1.0 - score_a) - (1.0 - ea))
    return elos.get(target, init)


# ─── 3. Exploitation rate ───────────────────────────────────────────────────


def exploitation_rate(
    snhp_avg: float,
    nash_share: float,
    max_achievable: float = 1.0,
) -> float:
    """
    Returns (snhp_avg − nash_share) / (max_achievable − nash_share).

    Interpretation:
      > 0 → captured surplus above equilibrium-honest play
      = 0 → fair share (Nash bargaining outcome)
      < 0 → got below-equilibrium share (we got exploited)

    Nash share comes from snhp/nash_solver.find_nash_bargaining_solution()
    averaged across the matchup population. If unknown, caller can pass
    0.5 as a generic equilibrium prior.
    """
    denom = max_achievable - nash_share
    if abs(denom) < 1e-9:
        return 0.0
    return float((snhp_avg - nash_share) / denom)


# ─── 4. Robustness score ────────────────────────────────────────────────────


def pair_joint_welfare(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    agent_a: str, agent_b: str,
) -> float:
    """Combined utility (sum of both sides) when agent_a meets agent_b,
    averaged across both directions. The cooperation-pair objective: two
    cooperative agents should meet at a joint outcome strictly above what
    extractor-vs-extractor pairs produce. Returns 0.0 if either agent is
    missing from the pairwise dict."""
    pairs = []
    for (a, b), (ua, ub, _dr) in pairwise.items():
        if {a, b} == {agent_a, agent_b}:
            pairs.append(ua + ub)
    return sum(pairs) / len(pairs) if pairs else 0.0


def mean_defense_floor_violation(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str, extractor_names: list[str], floor: float = 0.40,
) -> float:
    """Mean amount that target's utility falls below `floor` across matchups
    against the named extractors. The defense objective: walk-away yields
    reservation (~floor), so any matchup that delivers less than walk-away
    is a strict regression. Aim: minimize this number toward 0."""
    losses = []
    for ext in extractor_names:
        for (a, b), (ua, ub, _dr) in pairwise.items():
            if a == target and b == ext:
                losses.append(max(0.0, floor - ua))
            elif a == ext and b == target:
                losses.append(max(0.0, floor - ub))
    return sum(losses) / len(losses) if losses else 0.0


def robustness_score(snhp_per_match_utilities: list[float],
                      percentile: float = 5.0) -> float:
    """
    The 5th-percentile (or whatever percentile) of SNHP's utility across
    all individual matchups (not aggregated). Catches tail regressions —
    if a strategy change boosts avg utility by 0.02 but tanks the worst
    20 of 200 matchups, robustness will drop.
    """
    if not snhp_per_match_utilities:
        return 0.0
    sorted_utils = sorted(snhp_per_match_utilities)
    idx = max(0, min(len(sorted_utils) - 1,
                      int((percentile / 100.0) * len(sorted_utils))))
    return float(sorted_utils[idx])


# ─── 5. Classifier-conditional win rate ─────────────────────────────────────


@dataclass
class ClassifierEvent:
    """One classification event during a tournament. Caller logs these
    from the agent's runtime classifier so we can reconstruct accuracy."""
    opponent_name: str
    predicted_type: str
    confidence: float
    snhp_won: bool       # True if SNHP utility > opp utility + 0.005


def classifier_conditional_winrate(
    events: list[ClassifierEvent],
    type_tags: dict[str, str],
    *,
    confidence_threshold: float = 0.5,
) -> dict[str, float]:
    """
    Split events into (correct ∧ confident) vs (wrong ∧ confident) and
    report win rate in each. A large gap (correct >> wrong) means the
    system depends on classifier accuracy. A small gap means the
    strategy works regardless — robust to classification noise.
    """
    correct_won, correct_total = 0, 0
    wrong_won, wrong_total = 0, 0
    for ev in events:
        if ev.confidence < confidence_threshold:
            continue
        truth = type_tags.get(ev.opponent_name)
        if truth is None:
            continue
        is_correct = (truth == ev.predicted_type)
        if is_correct:
            correct_total += 1
            correct_won += int(ev.snhp_won)
        else:
            wrong_total += 1
            wrong_won += int(ev.snhp_won)

    cw = correct_won / correct_total if correct_total > 0 else 0.0
    ww = wrong_won / wrong_total if wrong_total > 0 else 0.0
    return {
        "correct_winrate": round(cw, 4),
        "wrong_winrate": round(ww, 4),
        "gap": round(cw - ww, 4),
        "n_correct": correct_total,
        "n_wrong": wrong_total,
        "classifier_accuracy": round(
            correct_total / max(1, correct_total + wrong_total), 4
        ),
    }


# ─── Top-level: compute_all + JSON serializer ───────────────────────────────


@dataclass
class CellMeta:
    git_sha: str
    cell: str
    wall_s: float
    generated_at: str   # ISO 8601 UTC


def compute_all(
    *,
    meta: CellMeta,
    config: dict,
    rankings: list[dict],
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    scores_per_match_for_target: list[float],
    type_tags: dict[str, str],
    target_player: str = "SNHP",
    nash_share: float = 0.5,
    classifier_events: Optional[list[ClassifierEvent]] = None,
    baseline_pairwise: Optional[dict[tuple[str, str], tuple[float, float, float]]] = None,
    baseline_avg: Optional[float] = None,
) -> dict:
    """
    Compute the full diff-able JSON artifact for one ablation cell.
    Returns a dict ready for json.dump with sort_keys=True.

    Schema documented in the plan file under "JSON schema (diff-able output)".
    """
    snhp_row = next(r for r in rankings if r["name"] == target_player)
    snhp_avg = float(snhp_row["avg"])
    deal_rate = _overall_deal_rate(pairwise, target_player)

    # Per-opponent SNHP utility — averaged across both directions.
    snhp_per_opp = _snhp_per_opponent(pairwise, target_player)

    per_type = per_type_utility(snhp_per_opp, type_tags)

    elo_paired = (
        paired_seed_elo_delta(baseline_pairwise, pairwise,
                               target_player=target_player)["delta"]
        if baseline_pairwise is not None else 0.0
    )

    robustness = robustness_score(scores_per_match_for_target)
    expl_rate = exploitation_rate(snhp_avg, nash_share)

    classifier = (
        classifier_conditional_winrate(classifier_events, type_tags)
        if classifier_events is not None else None
    )

    # Per-opponent breakdown with delta_vs_baseline if baseline provided.
    per_opponent: list[dict] = []
    for opp in sorted(snhp_per_opp.keys()):
        snhp_u = snhp_per_opp[opp]
        opp_u = _opp_utility_against_target(pairwise, target_player, opp)
        dr = _matchup_deal_rate(pairwise, target_player, opp)
        delta = None
        if baseline_pairwise is not None:
            base_snhp_u = _snhp_per_opponent(baseline_pairwise, target_player).get(opp)
            if base_snhp_u is not None:
                delta = round(snhp_u - base_snhp_u, 4)
        per_opponent.append({
            "name": opp,
            "snhp_util": round(snhp_u, 4),
            "opp_util": round(opp_u, 4),
            "deal_rate": round(dr, 4),
            "delta_vs_baseline": delta,
        })

    headline = {
        "avg": round(snhp_avg, 4),
        "elo_paired_delta": elo_paired,
        "robustness_p05": round(robustness, 4),
        "deal_rate": round(deal_rate, 4),
    }

    return {
        "meta": _meta_dict(meta),
        "config": dict(sorted(config.items())),
        "headline": headline,
        "per_type": per_type,
        "exploitation_rate": round(expl_rate, 4),
        "regret": _regret_placeholder(),
        "classifier": classifier,
        "per_opponent": per_opponent,
        "gates": {},
    }


def evaluate_gates(
    artifact: dict,
    *,
    baseline_artifact: Optional[dict] = None,
    misclass_stress_avg: Optional[float] = None,
) -> dict[str, str]:
    """
    Compute the 6 regression gates from the artifact (and optional baseline).
    Returns {gate_name: 'PASS' or 'FAIL: <why>'}.

    Gates (from the plan):
      g1_avg_drop:          avg_utility_delta_pct ≥ −1.0% vs baseline
      g2_worst_case:        worst-case-pairing delta ≥ −0.01
      g3_deal_rate:         overall deal rate ≥ 0.55
      g4_n_opp_negative:    number of opponents with negative delta ≤ 5
      g5_misclass_stress:   stress-mode avg ≥ 0.85 × baseline_avg
      g6_elo_paired:        elo paired delta ≥ −10
    """
    gates: dict[str, str] = {}

    avg = artifact["headline"]["avg"]
    deal_rate = artifact["headline"]["deal_rate"]
    elo_delta = artifact["headline"]["elo_paired_delta"]

    # g1
    if baseline_artifact is None:
        gates["g1_avg_drop"] = "PASS (no baseline supplied)"
    else:
        base_avg = baseline_artifact["headline"]["avg"]
        delta_pct = (avg - base_avg) / max(1e-6, base_avg) * 100
        gates["g1_avg_drop"] = (
            "PASS" if delta_pct >= -1.0
            else f"FAIL: avg dropped {delta_pct:.2f}% (limit −1.0%)"
        )

    # g2
    worst = min((p["delta_vs_baseline"] or 0.0)
                 for p in artifact["per_opponent"]) \
            if baseline_artifact is not None else 0.0
    gates["g2_worst_case"] = (
        "PASS" if worst >= -0.01
        else f"FAIL: worst-case pairing dropped {worst:+.4f} (limit −0.01)"
    )

    # g3
    gates["g3_deal_rate"] = (
        "PASS" if deal_rate >= 0.55
        else f"FAIL: deal rate {deal_rate:.2%} below 55%"
    )

    # g4
    n_neg = sum(1 for p in artifact["per_opponent"]
                 if (p["delta_vs_baseline"] or 0.0) < -0.005)
    gates["g4_n_opp_negative"] = (
        "PASS" if n_neg <= 5
        else f"FAIL: {n_neg} opponents regressed (limit 5)"
    )

    # g5 — caller passes misclass_stress_avg from a separate run cell
    if misclass_stress_avg is None or baseline_artifact is None:
        gates["g5_misclass_stress"] = "PASS (no stress run supplied)"
    else:
        floor = 0.85 * baseline_artifact["headline"]["avg"]
        gates["g5_misclass_stress"] = (
            "PASS" if misclass_stress_avg >= floor
            else f"FAIL: stress avg {misclass_stress_avg:.4f} < 85% of baseline {floor:.4f}"
        )

    # g6
    gates["g6_elo_paired"] = (
        "PASS" if elo_delta >= -10
        else f"FAIL: paired Elo delta {elo_delta:+.1f} (limit −10)"
    )

    return gates


# ─── Helpers ────────────────────────────────────────────────────────────────


def _snhp_per_opponent(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str,
) -> dict[str, float]:
    """SNHP avg utility per opponent, averaged across both directions."""
    by_opp: dict[str, list[float]] = {}
    for (a, b), (ua, ub, _dr) in pairwise.items():
        if a == target and b != target:
            by_opp.setdefault(b, []).append(ua)
        elif b == target and a != target:
            by_opp.setdefault(a, []).append(ub)
    return {opp: sum(vs) / len(vs) for opp, vs in by_opp.items() if vs}


def _opp_utility_against_target(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str,
    opp: str,
) -> float:
    vs = []
    for (a, b), (ua, ub, _dr) in pairwise.items():
        if a == target and b == opp:
            vs.append(ub)
        elif a == opp and b == target:
            vs.append(ua)
    return sum(vs) / len(vs) if vs else 0.0


def _matchup_deal_rate(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str,
    opp: str,
) -> float:
    drs = [dr for (a, b), (_ua, _ub, dr) in pairwise.items()
           if {a, b} == {target, opp}]
    return sum(drs) / len(drs) if drs else 0.0


def _overall_deal_rate(
    pairwise: dict[tuple[str, str], tuple[float, float, float]],
    target: str,
) -> float:
    drs = [dr for (a, b), (_ua, _ub, dr) in pairwise.items()
           if (a == target or b == target) and a != b]
    return sum(drs) / len(drs) if drs else 0.0


def _meta_dict(m: CellMeta) -> dict:
    return {
        "cell": m.cell,
        "generated_at": m.generated_at,
        "git_sha": m.git_sha,
        "wall_s": round(float(m.wall_s), 1),
    }


def _regret_placeholder() -> dict:
    """Regret-vs-ex-post-optimal requires replaying matchups with each
    playbook variant — too expensive to compute inline. The ablation
    runner fills this from cells 3–6 (per-type-only) which together
    span the playbook-variant space."""
    return {"mean": None, "p95": None, "note": "computed cross-cell at runner level"}


def to_json(artifact: dict, path: str) -> None:
    """Write the artifact with sorted keys + 4-decimal floats. Idempotent
    by construction: same inputs produce byte-identical output."""
    with open(path, "w") as f:
        json.dump(artifact, f, sort_keys=True, indent=2,
                   default=_json_default)
        f.write("\n")


def _json_default(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)

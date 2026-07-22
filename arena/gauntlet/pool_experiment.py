"""arena/gauntlet/pool_experiment.py — runs the REGISTERED counterparty-pool
experiment (PREREG-pool.md) and computes the verdict MECHANICALLY.

Everything decision-relevant is frozen by the registration and asserted here:
  - pool: naive | hardball | conceder (arena.gauntlet.pool, parameters frozen);
  - candidates: EngineSeat (competent) vs NaiveSeat (baseline); GenomeSeat
    (champion) reported as CONTEXT only, never part of the kill;
  - 60 scenarios x 2 roles x 3 counterparties = 360 matches per candidate per
    scenario set; run_pool_match (run_match semantics, pluggable counterparty);
  - scenario sets: PUBLIC seed 20260709 and HELD-OUT-NEW seed 20260718 (chosen
    at registration, never used before it);
  - PRIMARY: mean own-utility (u_candidate) pooled across all pool matches,
    paired by (scenario_id, role, counterparty); two-sided sign-flip
    permutation, n_perm=10000, RNG derived from the scenario-set seed (the
    certificate's own derivation, certify.paired_permutation_pvalue);
  - VERDICT: SURVIVE iff engine-naive delta > 0 AND p < 0.01 on BOTH sets;
    otherwise KILL-POOL. capture/logroll are context only.

The experiment REFUSES to run if PREREG-pool.md is missing — no unregistered
runs. Outputs: certs/POOL-RESULTS.md (verdict + per-set and per-counterparty
tables) and certs/pool-matches.json (raw per-match records, replay fuel).
No network, no LLM — local seats only.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from arena.gauntlet.agents import EngineSeat, NaiveSeat
from arena.gauntlet.certify import paired_permutation_pvalue
from arena.gauntlet.pool import (
    POOL_MEMBERS, make_pool_seat, pool_match_seed, run_pool_match,
)
from arena.gauntlet.protocol import DEADLINE, gen_gauntlet_scenarios

PREREG = pathlib.Path(__file__).with_name("PREREG-pool.md")
_CERTS = pathlib.Path(__file__).with_name("certs")

PUBLIC_SEED = 20260709        # the cert's existing public set (frozen)
HELDOUT_SEED = 20260718      # chosen at registration, never used before it
N_SCENARIOS = 60
ALPHA = 0.01
_match_seed = pool_match_seed    # ONE recipe, shared with certify.py


def require_prereg(path: pathlib.Path = PREREG) -> None:
    """The experiment runs ONLY under its registration. A missing prereg file
    means there is nothing binding the parameters — refuse loudly."""
    if not path.exists():
        raise SystemExit(
            f"REFUSING to run: registration file {path} is missing. This "
            f"experiment executes a pre-registered design (pool parameters, "
            f"seeds, statistic, kill conditions); without the registration "
            f"there is nothing binding them. Restore PREREG-pool.md.")


REFERENCE_CP = "snhp-engine"     # Amendment 1: reported tier, NEVER pooled
REFERENCE_PREDICTION = (
    "Registered before running (PREREG-pool.md Amendment 1): the SNHP-reference "
    "tier does NOT separate competent from adequate (prior measurement: "
    "own-utility delta +0.006, p=0.68) but DOES catch weak agents downward "
    "(recorded solo capture: Sonnet -0.093, Haiku -0.161, both p=0.0001). We "
    "predict it functions as a FLOOR test, not a RANKING test.")


def run_reference(name: str, seed: int, n: int = N_SCENARIOS,
                  deadline: int = DEADLINE) -> list[dict]:
    """The SNHP-REFERENCE arm (Amendment 1): the EngineSeat as counterparty —
    the ORIGINAL gauntlet protocol — scored on the same own-utility statistic,
    same pairing, same permutation. Reported SEPARATELY; never pooled into the
    primary statistic under any outcome."""
    scenarios = gen_gauntlet_scenarios(n, seed)
    out = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            ms = pool_match_seed(seed, sid, role, REFERENCE_CP)
            r = run_pool_match(
                _candidate_seat(name, ms), EngineSeat(ms),
                sc, w_s, w_b, role=role, condition=f"pool-{REFERENCE_CP}",
                scenario_id=sid, deadline=deadline)
            rec = r.to_dict()
            rec.update({"candidate": name, "counterparty": REFERENCE_CP,
                        "scenario_seed": seed})
            out.append(rec)
    return out


def _candidate_seat(name: str, match_seed: int):
    if name == "engine":
        return EngineSeat(match_seed)
    if name == "naive":
        return NaiveSeat()
    if name == "champion":
        from arena.gauntlet.agents import GenomeSeat
        from arena.gauntlet.champion import CHAMPION_PATH, load_champion
        genome, _ = load_champion(CHAMPION_PATH)
        return GenomeSeat(genome, match_seed)
    raise ValueError(name)


def run_candidate(name: str, seed: int, n: int = N_SCENARIOS,
                  deadline: int = DEADLINE) -> list[dict]:
    """All pool matches for one candidate on one scenario set:
    n scenarios x 2 roles x 3 counterparties. Returns plain record dicts
    (MatchResult.to_dict() + candidate/counterparty/seed labels)."""
    scenarios = gen_gauntlet_scenarios(n, seed)
    out = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            for cp in POOL_MEMBERS:
                ms = _match_seed(seed, sid, role, cp)
                r = run_pool_match(
                    _candidate_seat(name, ms), make_pool_seat(cp),
                    sc, w_s, w_b, role=role, condition=f"pool-{cp}",
                    scenario_id=sid, deadline=deadline)
                rec = r.to_dict()
                rec.update({"candidate": name, "counterparty": cp,
                            "scenario_seed": seed})
                out.append(rec)
    return out


# ── the registered statistic ────────────────────────────────────────────────
def paired_diffs(recs_a: list[dict], recs_b: list[dict],
                 field: str = "u_candidate") -> np.ndarray:
    """Difference a-b per (scenario_id, role, counterparty) key — pairing is BY
    KEY, never by list position, and both sides must cover the identical key
    set (raises otherwise: a partial pairing would silently bias the test)."""
    ka = {(r["scenario_id"], r["role"], r["counterparty"]): float(r[field])
          for r in recs_a}
    kb = {(r["scenario_id"], r["role"], r["counterparty"]): float(r[field])
          for r in recs_b}
    if set(ka) != set(kb) or len(ka) != len(recs_a) or len(kb) != len(recs_b):
        raise ValueError("record sets are not the same (scenario_id, role, "
                         "counterparty) key set — refusing a partial pairing")
    keys = sorted(ka)
    return np.array([ka[k] - kb[k] for k in keys], dtype=float)


def primary_stat(eng: list[dict], nai: list[dict], seed: int) -> dict:
    """The registered primary statistic on one scenario set: pooled own-utility
    delta + two-sided sign-flip permutation p (RNG derived from the set seed)."""
    diffs = paired_diffs(eng, nai)
    delta = float(diffs.mean())
    sd = float(diffs.std(ddof=1)) if len(diffs) > 1 else 0.0
    p = paired_permutation_pvalue(diffs, seed)
    return {
        "n_pairs": int(len(diffs)),
        "engine_mean": float(np.mean([r["u_candidate"] for r in eng])),
        "naive_mean": float(np.mean([r["u_candidate"] for r in nai])),
        "delta": delta,
        "cohen_d": (delta / sd) if sd > 1e-12 else float("nan"),
        "p_value": p,
        "passes": bool(delta > 0 and p < ALPHA),
    }


def _subset(recs: list[dict], cp: str) -> list[dict]:
    return [r for r in recs if r["counterparty"] == cp]


def _ctx(recs: list[dict]) -> dict:
    """Context metrics (no role in the verdict): capture/logroll/deal_rate."""
    lr = [r["logroll"] for r in recs if r["logroll"] is not None]
    return {"capture": float(np.mean([r["capture"] for r in recs])),
            "logroll": float(np.mean(lr)) if lr else None,
            "deal_rate": float(np.mean([1.0 if r["deal"] else 0.0
                                        for r in recs]))}


# ── the report ──────────────────────────────────────────────────────────────
def _cp_table(eng: list[dict], nai: list[dict], seed: int) -> list[str]:
    L = ["| counterparty | engine u | naive u | delta | perm p | "
         "engine deal% | naive deal% |",
         "|---|---|---|---|---|---|---|"]
    for cp in POOL_MEMBERS + ("POOLED",):
        e = eng if cp == "POOLED" else _subset(eng, cp)
        na = nai if cp == "POOLED" else _subset(nai, cp)
        s = primary_stat(e, na, seed)
        tag = "  **" if s["passes"] else ""
        L.append(f"| {cp} | {s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                 f"{s['delta']:+.4f} | {s['p_value']:.4f}{tag} | "
                 f"{_ctx(e)['deal_rate']:.0%} | {_ctx(na)['deal_rate']:.0%} |")
    return L


def run_experiment(n: int = N_SCENARIOS, *, prereg: pathlib.Path = PREREG,
                   out_dir: pathlib.Path = _CERTS,
                   verbose: bool = True) -> dict:
    require_prereg(prereg)
    sets = (("PUBLIC", PUBLIC_SEED), ("HELD-OUT-NEW", HELDOUT_SEED))
    data: dict = {}
    for label, seed in sets:
        for cand in ("engine", "naive"):
            if verbose:
                print(f"running {cand} on {label} (seed {seed}) — "
                      f"{n}x2x{len(POOL_MEMBERS)} matches ...", flush=True)
            data[(label, cand)] = run_candidate(cand, seed, n)
        try:
            if verbose:
                print(f"running champion on {label} (context) ...", flush=True)
            data[(label, "champion")] = run_candidate("champion", seed, n)
        except Exception as e:                     # context only — never blocks
            if verbose:
                print(f"  champion context skipped: {type(e).__name__}: {e}")
            data[(label, "champion")] = None

    # the registered verdict, mechanically — the FROZEN THREE only. The
    # reference arm below is computed from a separate `ref` dict and is never
    # merged into `data`, so it cannot reach this statistic.
    per_set = {label: primary_stat(data[(label, "engine")],
                                   data[(label, "naive")], seed)
               for label, seed in sets}
    survive = all(s["passes"] for s in per_set.values())
    verdict = "SURVIVE" if survive else "KILL-POOL"

    # ── Amendment 1: the SNHP-REFERENCE tier (separate structure, separate
    #    statistic, never pooled) ─────────────────────────────────────────────
    ref: dict = {}
    for label, seed in sets:
        for cand in ("engine", "naive"):
            if verbose:
                print(f"running {cand} on {label} vs SNHP-REFERENCE "
                      f"({n}x2 matches) ...", flush=True)
            ref[(label, cand)] = run_reference(cand, seed, n)
    ref_per_set = {label: primary_stat(ref[(label, "engine")],
                                       ref[(label, "naive")], seed)
                   for label, seed in sets}
    # the prediction is CONTRADICTED only if the tier separates on BOTH sets
    ref_separates_both = all(s["passes"] for s in ref_per_set.values())
    prediction_outcome = "contradicted" if ref_separates_both else "held"

    # ── report ──────────────────────────────────────────────────────────────
    L = []
    L.append("# Counterparty-pool experiment — results "
             "(registered: PREREG-pool.md)\n")
    if survive:
        L.append(f"**VERDICT: SURVIVE.** Engine separates from the naive "
                 f"baseline on pooled own-utility, delta > 0 with p < {ALPHA} "
                 f"on BOTH scenario sets — per the registration, candidate "
                 f"skill is certifiable against the declared pool and the "
                 f"certificate's primary claim moves to pooled own-utility "
                 f"(spec gauntlet-cert/3).\n")
    else:
        L.append(f"**VERDICT: KILL-POOL — skill certification with local "
                 f"scripted pools is dead per the registration.** The "
                 f"registered bar (engine - naive > 0 with p < {ALPHA} on BOTH "
                 f"sets, pooled own-utility) was not met. Per the registration: "
                 f"the certificate retreats permanently to what already "
                 f"separates — safety / not-below-baseline claims — and no "
                 f"further metric or pool iteration happens without a new "
                 f"registration that states why. certify.py stays at "
                 f"gauntlet-cert/2 with its disclosures.\n")

    L.append("## Primary statistic (pooled own-utility, the registered kill)\n")
    L.append("| scenario set | n pairs | engine u | naive u | delta | "
             "Cohen's d | perm p | passes (delta>0 & p<0.01) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for label, seed in sets:
        s = per_set[label]
        d = "n/a" if s["cohen_d"] != s["cohen_d"] else f"{s['cohen_d']:+.3f}"
        L.append(f"| {label} (seed {seed}) | {s['n_pairs']} | "
                 f"{s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                 f"{s['delta']:+.4f} | {d} | {s['p_value']:.4f} | "
                 f"{'YES' if s['passes'] else 'NO'} |")
    L.append("")

    for label, seed in sets:
        L.append(f"## Per-counterparty breakdown — {label} (seed {seed})\n")
        L += _cp_table(data[(label, "engine")], data[(label, "naive")], seed)
        L.append("")
        L.append(f"(`**` marks delta>0 AND p<{ALPHA} on that row; only the "
                 f"POOLED row feeds the verdict. A pool that separates only "
                 f"via one member is exactly that — see the rows.)\n")

    # ── Amendment 1 section: prediction FIRST, then outcome, then verdict ───
    L.append("---\n")
    L.append("# Reference tier (SNHP engine) — SEPARATELY REPORTED, "
             "NOT part of the certified claim\n")
    L.append("> The certified verdict above concerns the FROZEN THREE "
             "(naive, hardball, conceder) and is unchanged by anything in this "
             "section. The SNHP engine is an ADDITIONAL reported opponent "
             "(PREREG-pool.md Amendment 1); adding it to a registration that "
             "just passed would be the forking-paths error this program avoids, "
             "so it is never pooled into the primary statistic under any "
             "outcome.\n")
    L.append("**The registered prediction, stated before this arm was run:**\n")
    L.append(f"> {REFERENCE_PREDICTION}\n")
    L.append("**The outcome:**\n")
    L.append("| scenario set | n pairs | engine u | naive u | delta | "
             "Cohen's d | perm p | separates (delta>0 & p<0.01) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for label, seed in sets:
        s = ref_per_set[label]
        dd = "n/a" if s["cohen_d"] != s["cohen_d"] else f"{s['cohen_d']:+.3f}"
        L.append(f"| {label} (seed {seed}) | {s['n_pairs']} | "
                 f"{s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                 f"{s['delta']:+.4f} | {dd} | {s['p_value']:.4f} | "
                 f"{'YES' if s['passes'] else 'NO'} |")
    L.append("")
    L.append(f"**Verdict on the prediction: {prediction_outcome.upper()}.**\n")
    if prediction_outcome == "held":
        L.append("The reference tier does not separate the competent candidate "
                 "from the adequate baseline at the registered bar on both "
                 "sets — as predicted. Published as exactly that: **the "
                 "reference tier catches weakness; it cannot rank strength.** "
                 "It stays out of the certified statistic permanently, per the "
                 "registration.\n")
    else:
        L.append("The reference tier DID separate on both sets — a NEW finding "
                 "that CONTRADICTS our prior measurement (delta +0.006, "
                 "p=0.68). Reported as surprising, and per the registration it "
                 "still does NOT enter the certified claim without its own "
                 "fresh registration and held-out validation.\n")
    L.append("Context — what the tier is good for (the floor half of the "
             "prediction) is evidenced by the recorded historical run: solo "
             "Sonnet and Haiku separate DOWNWARD vs the naive baseline at "
             "p=0.0001 (capture; see certs/SEPARATION.md). Those agents never "
             "played the pool, so they are historical context, not pool-"
             "certified.\n")
    L.append("---\n")

    L.append("## Context (no role in the verdict)\n")
    L.append("| set | candidate | capture | logroll | deal_rate |")
    L.append("|---|---|---|---|---|")
    for label, _ in sets:
        for cand in ("engine", "naive", "champion"):
            recs = data[(label, cand)]
            if recs is None:
                L.append(f"| {label} | {cand} | n/a | n/a | n/a |")
                continue
            c = _ctx(recs)
            lr = "n/a" if c["logroll"] is None else f"{c['logroll']:.4f}"
            L.append(f"| {label} | {cand} | {c['capture']:.4f} | {lr} | "
                     f"{c['deal_rate']:.0%} |")
    L.append("")
    for label, seed in sets:
        ch = data.get((label, "champion"))
        if ch is not None:
            s = primary_stat(ch, data[(label, "naive")], seed)
            L.append(f"- champion vs naive (context, {label}): own-u delta "
                     f"{s['delta']:+.4f}, p={s['p_value']:.4f} — not part of "
                     f"the kill.")
    L.append("")
    L.append(f"_Registered design executed verbatim: pool parameters frozen in "
             f"PREREG-pool.md; {n} scenarios x 2 roles x {len(POOL_MEMBERS)} "
             f"counterparties per candidate per set; pairing by (scenario_id, "
             f"role, counterparty); two-sided sign-flip permutation, "
             f"n_perm=10000, RNG derived from the scenario-set seed exactly as "
             f"in certify.py. Deterministic local seats only — no LLM, no "
             f"network. Raw records: certs/pool-matches.json._\n")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "POOL-RESULTS.md"
    report_path.write_text("\n".join(L))
    matches_path = out_dir / "pool-matches.json"
    matches_path.write_text(json.dumps(
        {"prereg": "PREREG-pool.md", "n_scenarios": n, "deadline": DEADLINE,
         "sets": {label: seed for label, seed in sets},
         "matches": ([r for key in data if data[key] is not None
                      for r in data[key]]
                     + [r for key in ref for r in ref[key]])}, indent=1))
    # machine-readable reference-tier summary — certify.py stamps
    # `prediction_outcome` from THIS file rather than hardcoding a result.
    ref_path = out_dir / "reference-tier.json"
    ref_path.write_text(json.dumps({
        "registration": "PREREG-pool.md Amendment 1",
        "counterparty": REFERENCE_CP,
        "prediction": REFERENCE_PREDICTION,
        "prediction_outcome": prediction_outcome,
        "alpha": ALPHA,
        "per_set": {label: {k: v for k, v in ref_per_set[label].items()}
                    for label, _ in sets},
        "sets": {label: seed for label, seed in sets},
        "n_scenarios": n,
        "pooled_into_primary": False,
    }, indent=1))
    if verbose:
        print(f"\nVERDICT (frozen three): {verdict}")
        for label, _ in sets:
            s = per_set[label]
            print(f"  {label}: delta {s['delta']:+.4f}  p={s['p_value']:.4f}  "
                  f"passes={s['passes']}")
        print(f"REFERENCE TIER (separate, not certified) — "
              f"prediction {prediction_outcome.upper()}")
        for label, _ in sets:
            s = ref_per_set[label]
            print(f"  {label}: delta {s['delta']:+.4f}  p={s['p_value']:.4f}  "
                  f"separates={s['passes']}")
        print(f"wrote {report_path}\nwrote {matches_path}\nwrote {ref_path}")
    return {"verdict": verdict, "per_set": per_set,
            "reference_per_set": ref_per_set,
            "prediction_outcome": prediction_outcome}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m arena.gauntlet.pool_experiment",
                                description=__doc__)
    p.add_argument("--n", type=int, default=N_SCENARIOS,
                   help="scenarios per set (the registration says 60)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    res = run_experiment(args.n, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

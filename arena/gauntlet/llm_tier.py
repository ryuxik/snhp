"""arena/gauntlet/llm_tier.py — the MEASURED FRONTIER-MODEL tier
(PREREG-pool.md Amendment 2).

Runs the registered frontier models UNAIDED as the pool candidate against the
frozen three (naive, hardball, conceder), on both seed sets, scored on the
SAME own-utility statistic as the certified section-1 claim. The models get a
COMPARABLE reported number — never a certified one, never merged into the
engine−naive verdict. Publication rendering lives in publish_table.py; this
module only produces the paid, cached match records.

Why a separate module (not part of pool_experiment): these matches cost real
API calls. Everything here is built around that one fact.

FAILURE TOLERANCE (registered in Amendment 2 — a paid, interruptible run):
  - every completed match is flushed to the cache IMMEDIATELY (atomic replace),
    so a crash loses at most the single in-flight match;
  - a re-run RESUMES from the cache and spends only on the missing matches;
  - a PERMANENT API error (exhausted credits, auth, bad config — surfaced by the
    shared transport_retry as RuntimeError) stops cleanly, keeps every completed
    match, records `stopped_reason`, and returns partial. It NEVER fabricates a
    model's play;
  - the cache is marked `incomplete` until every registered match is present;
    publish_table renders a model×set cell ONLY when all 360 are there.

Offline validation: pass `--provider scripted-naive` to exercise the entire
pipeline (checkpoint, resume, reporting) with ZERO API calls — the seat
short-circuits to NaiveSeat. Use it to prove the plumbing before spending.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from arena.gauntlet.agents import LLMSeat
from arena.gauntlet.pool import (
    POOL_MEMBERS, make_pool_seat, pool_match_seed, run_pool_match,
)
from arena.gauntlet.protocol import DEADLINE, gen_gauntlet_scenarios
from arena.gauntlet.pool_experiment import (
    HELDOUT_SEED, PUBLIC_SEED, N_SCENARIOS, PREREG, require_prereg,
)

_CERTS = pathlib.Path(__file__).with_name("certs")
# Tracked published fuel — same location + role as arena/web/gauntlet-matches.json
# (section 4's source): publish_table reads it read-only to render section 3, so
# it must be committed for the table to regenerate without re-spending. The
# certs/ dir is deliberately gitignored scratch; arena/web/ is not.
CACHE = pathlib.Path(__file__).resolve().parents[1] / "web" / "llm-tier-matches.json"

PROTOCOL = "pool-llm/1"
REGISTRATION = "PREREG-pool.md Amendment 2"

# Frozen by Amendment 2. provider:model; the models are the certified candidates.
TIER_MODELS = ("claude-sonnet-5", "claude-haiku-4-5-20251001")
SETS = (("PUBLIC", PUBLIC_SEED), ("HELD-OUT-NEW", HELDOUT_SEED))

# Registered before the run (Amendment 2). Rendered verbatim on the page.
TIER_PREDICTION = (
    "Registered before running (PREREG-pool.md Amendment 2): we predict NEITHER "
    "claude-sonnet-5 nor claude-haiku-4-5-20251001, unaided, separates UPWARD "
    "from the naive split-the-difference baseline against the pool (delta>0 AND "
    "p<0.01 is FALSE on at least one set, expected delta at or below zero). "
    "Rationale: the engine's certified edge is systematic frontier search a "
    "JSON-emitting model does not reliably reproduce, and prior capture-metric "
    "runs put both below naive (solo Sonnet -0.093, Haiku -0.161). The pool is "
    "a FLOOR / ranking-null test for raw models.")


ARMS_A3 = ("solo", "advised")           # Amendment 3, matched inference config
# Amendment 3 fuel — its own artifact so the Amendment 2 rows (Sonnet solo with
# thinking ON) are never mixed with this matched-config collection.
CACHE_A3 = pathlib.Path(__file__).resolve().parents[1] / "web" / "llm-advice-arms.json"

A3_PREDICTION = (
    "Registered before running (PREREG-pool.md Amendment 3): MEAN — advice helps "
    "the weaker model materially and the stronger barely; we predict Haiku "
    "advised-solo > 0 at p<0.01 on both sets and Sonnet's mean effect small and "
    "possibly not separable (headroom to the engine: Haiku +0.048/+0.049, Sonnet "
    "+0.012/+0.037). DOWNSIDE — we predict advice improves BOTH downside "
    "statistics for BOTH models on both sets: breach rate P(u<=BATNA) falls and "
    "CVaR@10 rises. Stated bidirectionally: advice may HURT the mean (the "
    "carried-counterparty effect that puts the champion below naive); a negative "
    "mean with an improved downside reads 'SNHP buys safety, not surplus'. If the "
    "downside does NOT improve, that is a KILL of the floor claim on this "
    "instrument, reported as such with no re-cut.")


# Published per-MTok prices. Cost is computed from the API's own reported token
# counts (never from assumed sizes). Sonnet 5 carries a lower introductory rate
# through 2026-08-31; we price at the STANDARD rate so the budget guard is a
# conservative upper bound and can only stop early, never late.
PRICES = {                       # model -> (input $/MTok, output $/MTok)
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def match_cost(rec: dict) -> float:
    """Exact cost of one match from the API's reported token usage."""
    pin, pout = PRICES.get(rec.get("candidate"), (0.0, 0.0))
    return (rec.get("usage_in", 0) / 1e6) * pin + (rec.get("usage_out", 0) / 1e6) * pout


def cache_cost(cache: dict) -> float:
    return sum(match_cost(m) for m in cache.get("matches", []))


def _match_key(model: str, set_label: str, sid: int, role: str, cp: str,
               arm: str = "solo") -> str:
    return f"{model}|{set_label}|{sid}|{role}|{cp}|{arm}"


def _load_cache(path: pathlib.Path = None) -> dict:
    path = path or CACHE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"protocol": PROTOCOL, "registration": REGISTRATION,
            "provider": None, "models": list(TIER_MODELS),
            "sets": {label: seed for label, seed in SETS},
            "matches": [], "incomplete": True, "stopped_reason": None}


def _flush(cache: dict, path: pathlib.Path = None) -> None:
    """Atomic write — a crash mid-flush cannot corrupt the cache."""
    path = path or CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2))
    os.replace(tmp, path)


def _planned_keys(arms=("solo",)) -> list[tuple]:
    """Every (model, set_label, seed, sid, role, cp, arm) match the registration
    demands — the full work list a resume diffs against."""
    plan = []
    for model in TIER_MODELS:
        for set_label, seed in SETS:
            for sid in range(N_SCENARIOS):
                for role in ("seller", "buyer"):
                    for cp in POOL_MEMBERS:
                        for arm in arms:
                            plan.append((model, set_label, seed, sid, role,
                                         cp, arm))
    return plan


def run_tier(provider: str = "anthropic", *, models=TIER_MODELS,
             n: int = N_SCENARIOS, deadline: int = DEADLINE, workers: int = 1,
             arms=("solo",), cache_path: pathlib.Path = None,
             sets=None, budget_usd: float | None = None,
             prereg: pathlib.Path = PREREG, verbose: bool = True) -> dict:
    """Run (or resume) the registered LLM tier. Returns the cache dict. Spends
    API calls ONLY on matches not already cached. Stops cleanly and returns
    partial on a permanent API failure. `workers` runs that many matches
    concurrently (each match is independent; only the candidate hits the API).
    Any statistic is unaffected — matches are keyed, so completion order does
    not matter, and a resume reproduces the same pairing set."""
    require_prereg(prereg)
    cache = _load_cache(cache_path)
    cache["provider"] = provider
    cache["arms"] = list(arms)
    done = {_match_key(m["candidate"], m["set_label"], m["scenario_id"],
                       m["role"], m["counterparty"], m.get("arm", "solo"))
            for m in cache["matches"]}

    # scenarios are cheap + deterministic — regenerate per (set) on demand.
    scen_cache: dict[int, list] = {}

    def scenarios(seed: int):
        if seed not in scen_cache:
            scen_cache[seed] = gen_gauntlet_scenarios(n, seed)
        return scen_cache[seed]

    def key_of(p):                    # p = (model, set, seed, sid, role, cp, arm)
        model, set_label, _seed, sid, role, cp, arm = p
        return _match_key(model, set_label, sid, role, cp, arm)

    plan = [p for p in _planned_keys(arms)
            if p[0] in models and (sets is None or p[1] in sets)]
    todo = [p for p in plan if key_of(p) not in done]
    if verbose:
        print(f"LLM tier ({provider}, {workers} worker(s)): {len(plan)} "
              f"registered matches, {len(plan) - len(todo)} already cached, "
              f"{len(todo)} to run.", flush=True)

    # Pre-generate scenarios single-threaded so worker threads only READ the
    # cache (gen_gauntlet_scenarios is not guarded for concurrent first-touch).
    for _, seed in SETS:
        scenarios(seed)

    def run_one(p):
        """One independent match. A FRESH seat per match keeps threads from
        sharing the mutable format_failures counter and the HTTP client."""
        model, set_label, seed, sid, role, cp, arm = p
        sc, w_s, w_b = scenarios(seed)[sid]
        seat = LLMSeat(provider, model)      # fresh per match => its usage IS this match's
        r = run_pool_match(
            seat, make_pool_seat(cp), sc, w_s, w_b,
            role=role, condition=arm, scenario_id=sid, deadline=deadline,
            advised=(arm == "advised"),
            advice_seed=pool_match_seed(seed, sid, role, cp))
        rec = r.to_dict()
        rec.update({"candidate": model, "set_label": set_label,
                    "counterparty": cp, "scenario_seed": seed, "arm": arm,
                    "usage_in": seat.usage_in, "usage_out": seat.usage_out})
        return rec

    lock = threading.Lock()
    ran = 0
    stopped_reason = None

    spent = [cache_cost(cache)]            # measured $, carried across resumes
    over_budget = [False]

    def commit(rec, tag: str):
        nonlocal ran
        with lock:                              # serialize only the checkpoint
            cache["matches"].append(rec)
            spent[0] += match_cost(rec)
            _flush(cache, cache_path)
            ran += 1
            if budget_usd is not None and spent[0] >= budget_usd:
                over_budget[0] = True
            if verbose and ran % 30 == 0:
                print(f"  {ran}/{len(todo)} new matches  ${spent[0]:.2f} spent  (last: {tag})",
                      flush=True)

    if workers <= 1:
        try:
            for p in todo:
                if over_budget[0]:
                    stopped_reason = (f"budget reached: ${spent[0]:.2f} of "
                                      f"${budget_usd:.2f} (measured)")
                    break
                commit(run_one(p), f"{p[0]} {p[1]} s{p[3]} {p[4]} vs {p[5]} [{p[6]}]")
        except (RuntimeError, KeyboardInterrupt) as e:
            # RuntimeError = permanent API failure (credits/auth/config) from
            # transport_retry; KeyboardInterrupt = operator stop.
            stopped_reason = f"{type(e).__name__}: {e}"
    else:
        # Concurrent: each finished match is checkpointed as it lands (out of
        # order is fine — records are keyed). A permanent failure in ANY worker
        # stops scheduling; in-flight matches are abandoned (not fabricated) and
        # simply re-run on the next resume.
        ex = ThreadPoolExecutor(max_workers=workers)
        futs = {ex.submit(run_one, p): p for p in todo}
        try:
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    rec = fut.result()
                except Exception as e:          # permanent API error or a bug
                    stopped_reason = f"{type(e).__name__}: {e}"
                    break
                commit(rec, f"{p[0]} {p[1]} s{p[3]} {p[4]} vs {p[5]} [{p[6]}]")
                if over_budget[0]:
                    stopped_reason = (f"budget reached: ${spent[0]:.2f} of "
                                      f"${budget_usd:.2f} (measured)")
                    break
        except KeyboardInterrupt:
            stopped_reason = "KeyboardInterrupt: operator stop"
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    if stopped_reason is not None:
        # Keep everything done, mark why, do NOT re-raise — partial progress is
        # the whole point; a resume charges only the missing matches.
        cache["stopped_reason"] = stopped_reason
        cache["incomplete"] = True
        _flush(cache, cache_path)
        if verbose:
            print(f"\nSTOPPED after {ran} new matches — {stopped_reason}"
                  f"\nProgress saved to {cache_path or CACHE}. Re-run to resume "
                  f"from the cache (only the missing matches are charged).",
                  flush=True)
        return cache

    # completeness: every registered match for the requested models is present.
    have = {_match_key(m["candidate"], m["set_label"], m["scenario_id"],
                       m["role"], m["counterparty"], m.get("arm", "solo"))
            for m in cache["matches"]}
    need = {key_of(p) for p in plan}
    cache["incomplete"] = not need.issubset(have)
    if not cache["incomplete"]:
        cache["stopped_reason"] = None
    _flush(cache, cache_path)
    if verbose:
        state = "COMPLETE" if not cache["incomplete"] else "still incomplete"
        print(f"done: {ran} new matches, ${spent[0]:.2f} measured spend, "
              f"cache {state} ({len(have)} total). "
              f"Regenerate the table: python -m arena.gauntlet.publish_table",
              flush=True)
    return cache


def _load_dotenv(name: str = "ANTHROPIC_API_KEY") -> None:
    """Populate `name` from a gitignored repo-root .env if it isn't already in
    the environment — so a key the operator drops in .env is used without ever
    passing through the shell history or being printed. Never overrides an
    existing env value; only parses `KEY=VALUE` lines; ignores everything else.
    No dependency (dotenv is not vendored here)."""
    if os.environ.get(name):
        return
    root = pathlib.Path(__file__).resolve().parents[2]
    env = root / ".env"
    if not env.exists():
        return
    try:
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name and v.strip():
                os.environ[name] = v.strip().strip('"').strip("'")
                break
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m arena.gauntlet.llm_tier", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", default="anthropic",
                   choices=("anthropic", "scripted-naive"),
                   help="anthropic = the real paid run; scripted-naive = free "
                        "offline pipeline check (no API calls).")
    p.add_argument("--models", nargs="*", default=list(TIER_MODELS),
                   help="subset of the registered models to run/resume.")
    p.add_argument("--n", type=int, default=N_SCENARIOS)
    p.add_argument("--amendment", type=int, default=2, choices=(2, 3),
                   help="2 = the solo tier (Amendment 2, published section 3). "
                        "3 = the paired solo+advised arms at matched inference "
                        "config (Amendment 3), written to its own artifact.")
    p.add_argument("--sets", nargs="*", default=None,
                   choices=[lbl for lbl, _ in SETS],
                   help="restrict to these scenario sets (default: all).")
    p.add_argument("--budget-usd", type=float, default=None,
                   help="HARD ceiling in measured dollars. Cost is computed from "
                        "the API's own reported token counts; the run stops "
                        "cleanly (checkpointed) the moment it is reached.")
    p.add_argument("--workers", type=int, default=1,
                   help="concurrent matches (default 1). Each match is "
                        "independent; only the candidate hits the API. Higher "
                        "values trade rate-limit headroom for wall-clock.")
    args = p.parse_args(argv)
    unknown = [m for m in args.models if m not in TIER_MODELS]
    if unknown:
        print(f"refusing unregistered model(s): {unknown}. Amendment 2 froze "
              f"{list(TIER_MODELS)}; add a new amendment to run others.",
              file=sys.stderr)
        return 2
    if args.provider == "anthropic":
        _load_dotenv()                          # pick up a key dropped in .env
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set (checked the environment and the "
                  "gitignored repo-root .env) — the real run needs it. Add a "
                  "line `ANTHROPIC_API_KEY=...` to .env, export it, or use "
                  "--provider scripted-naive for the free offline pipeline "
                  "check.", file=sys.stderr)
            return 2
    arms = ARMS_A3 if args.amendment == 3 else ("solo",)
    cache_path = CACHE_A3 if args.amendment == 3 else CACHE
    cache = run_tier(args.provider, models=args.models, n=args.n,
                     workers=max(1, args.workers), arms=arms,
                     cache_path=cache_path, sets=args.sets,
                     budget_usd=args.budget_usd)
    return 0 if not cache.get("incomplete") else 1


if __name__ == "__main__":
    sys.exit(main())

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
    POOL_MEMBERS, make_pool_seat, run_pool_match,
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


def _match_key(model: str, set_label: str, sid: int, role: str, cp: str) -> str:
    return f"{model}|{set_label}|{sid}|{role}|{cp}"


def _load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"protocol": PROTOCOL, "registration": REGISTRATION,
            "provider": None, "models": list(TIER_MODELS),
            "sets": {label: seed for label, seed in SETS},
            "matches": [], "incomplete": True, "stopped_reason": None}


def _flush(cache: dict) -> None:
    """Atomic write — a crash mid-flush cannot corrupt the cache."""
    _CERTS.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2))
    os.replace(tmp, CACHE)


def _planned_keys() -> list[tuple]:
    """Every (model, set_label, seed, sid, role, cp) match the registration
    demands — the full work list a resume diffs against."""
    plan = []
    for model in TIER_MODELS:
        for set_label, seed in SETS:
            for sid in range(N_SCENARIOS):
                for role in ("seller", "buyer"):
                    for cp in POOL_MEMBERS:
                        plan.append((model, set_label, seed, sid, role, cp))
    return plan


def run_tier(provider: str = "anthropic", *, models=TIER_MODELS,
             n: int = N_SCENARIOS, deadline: int = DEADLINE, workers: int = 1,
             prereg: pathlib.Path = PREREG, verbose: bool = True) -> dict:
    """Run (or resume) the registered LLM tier. Returns the cache dict. Spends
    API calls ONLY on matches not already cached. Stops cleanly and returns
    partial on a permanent API failure. `workers` runs that many matches
    concurrently (each match is independent; only the candidate hits the API).
    Any statistic is unaffected — matches are keyed, so completion order does
    not matter, and a resume reproduces the same pairing set."""
    require_prereg(prereg)
    cache = _load_cache()
    cache["provider"] = provider
    done = {_match_key(m["candidate"], m["set_label"], m["scenario_id"],
                       m["role"], m["counterparty"]) for m in cache["matches"]}

    # scenarios are cheap + deterministic — regenerate per (set) on demand.
    scen_cache: dict[int, list] = {}

    def scenarios(seed: int):
        if seed not in scen_cache:
            scen_cache[seed] = gen_gauntlet_scenarios(n, seed)
        return scen_cache[seed]

    def key_of(p):                              # p = (model, set, seed, sid, role, cp)
        model, set_label, _seed, sid, role, cp = p
        return _match_key(model, set_label, sid, role, cp)

    plan = [p for p in _planned_keys() if p[0] in models]
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
        model, set_label, seed, sid, role, cp = p
        sc, w_s, w_b = scenarios(seed)[sid]
        r = run_pool_match(
            LLMSeat(provider, model), make_pool_seat(cp), sc, w_s, w_b,
            role=role, condition="solo", scenario_id=sid, deadline=deadline)
        rec = r.to_dict()
        rec.update({"candidate": model, "set_label": set_label,
                    "counterparty": cp, "scenario_seed": seed})
        return rec

    lock = threading.Lock()
    ran = 0
    stopped_reason = None

    def commit(rec, tag: str):
        nonlocal ran
        with lock:                              # serialize only the checkpoint
            cache["matches"].append(rec)
            _flush(cache)
            ran += 1
            if verbose and ran % 30 == 0:
                print(f"  {ran}/{len(todo)} new matches (last: {tag})",
                      flush=True)

    if workers <= 1:
        try:
            for p in todo:
                commit(run_one(p), f"{p[0]} {p[1]} s{p[3]} {p[4]} vs {p[5]}")
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
                commit(rec, f"{p[0]} {p[1]} s{p[3]} {p[4]} vs {p[5]}")
        except KeyboardInterrupt:
            stopped_reason = "KeyboardInterrupt: operator stop"
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    if stopped_reason is not None:
        # Keep everything done, mark why, do NOT re-raise — partial progress is
        # the whole point; a resume charges only the missing matches.
        cache["stopped_reason"] = stopped_reason
        cache["incomplete"] = True
        _flush(cache)
        if verbose:
            print(f"\nSTOPPED after {ran} new matches — {stopped_reason}"
                  f"\nProgress saved to {CACHE}. Re-run to resume from the cache "
                  f"(only the missing matches will be charged).", flush=True)
        return cache

    # completeness: every registered match for the requested models is present.
    have = {_match_key(m["candidate"], m["set_label"], m["scenario_id"],
                       m["role"], m["counterparty"]) for m in cache["matches"]}
    need = {key_of(p) for p in plan}
    cache["incomplete"] = not need.issubset(have)
    if not cache["incomplete"]:
        cache["stopped_reason"] = None
    _flush(cache)
    if verbose:
        state = "COMPLETE" if not cache["incomplete"] else "still incomplete"
        print(f"done: {ran} new matches, cache {state} ({len(have)} total). "
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
    cache = run_tier(args.provider, models=args.models, n=args.n,
                     workers=max(1, args.workers))
    return 0 if not cache.get("incomplete") else 1


if __name__ == "__main__":
    sys.exit(main())

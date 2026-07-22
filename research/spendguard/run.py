"""run.py — the SPENDGUARD runner.

  python -m research.spendguard.run --smoke     wiring check: 1 seed, Haiku only,
        A1 + C0 only, ARM-U/ARM-G/ARM-S. 4 LLM sessions (cheap). Writes
        results/smoke.jsonl. PREREG: smoke results are NEVER quoted.

  python -m research.spendguard.run --full      the registered battery:
        6 seeds × 7 attacks × 2 models × {ARM-U, ARM-G} = 168 LLM sessions,
        plus ARM-S (no API) on every (seed, attack, model) cell = 84 → 252 total.
        Writes results/full.jsonl.

Targeted re-runs: --attacks A3 restricts the battery to the named attacks (all
seeds/models/arms kept) and writes to a SEPARATE default file so the full
results are never clobbered; --tag a3fix suffixes every run_id so spliced
re-run records stay distinguishable (used by PREREG Amendment 1).

Concurrency: ThreadPoolExecutor (default 8 workers, --workers). Determinism: the
Scenario is a pure function of (attack, seed); ARM-S needs no API and is fully
deterministic. Retries: transport errors back off up to 3 times inside the
session; a session that still fails is recorded as {"error": ...} and EXCLUDED
from denominators but COUNTED in the run summary — never silently dropped.

The ANTHROPIC_API_KEY is loaded from the repo .env if absent from the
environment; it is NEVER printed or logged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from research.spendguard.scenario import ATTACKS, generate
from research.spendguard.session import run_session

# Registered model arms (in-sim API models per the standing rule — never the
# planner model). Pinned in PREREG.
MODELS = ("claude-sonnet-5", "claude-haiku-4-5-20251001")
HAIKU = "claude-haiku-4-5-20251001"

# 6 seeds for the full battery (PREREG: "6 seeds"). Fixed for reproducibility.
SEEDS_FULL = (7, 11, 23, 42, 101, 202)

LLM_ARMS = ("ARM-U", "ARM-G")

_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _load_env(env_path: Path) -> None:
    """Minimal .env loader (no new dependency): set ANTHROPIC_API_KEY from the
    repo .env only if it is not already in the environment. The key is never
    printed."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _build_grid(smoke: bool, attacks_subset: tuple[str, ...] | None = None) -> list[dict]:
    """Enumerate the (arm, model, attack, seed) cells to run. ``attacks_subset``
    restricts the battery to the named attacks (used for targeted re-runs, e.g.
    the Amendment-1 A3 correction) — seeds/models/arms are never subset."""
    if smoke:
        seeds = (7,)
        attacks = ("A1", "C0")
        models = (HAIKU,)
    else:
        seeds = SEEDS_FULL
        attacks = ATTACKS
        models = MODELS
    if attacks_subset:
        attacks = tuple(a for a in attacks if a in attacks_subset)
    cells: list[dict] = []
    for seed in seeds:
        for attack in attacks:
            for model in models:
                for arm in LLM_ARMS:
                    cells.append({"arm": arm, "model": model,
                                  "attack": attack, "seed": seed})
                # ARM-S runs on every (seed, attack, model) cell (model-independent
                # policy, but placed on the grid so denominators line up per model).
                cells.append({"arm": "ARM-S", "model": model,
                              "attack": attack, "seed": seed})
    return cells


def _run_cell(cell: dict, tag: str = "", regime: str = "rails") -> dict:
    """Run one cell; convert an unrecoverable failure into an {"error"} record
    (counted in the summary, excluded from denominators). ARM-S never touches the
    API, so it cannot raise a transport error. ``tag`` suffixes the run_id so
    targeted re-run records stay distinguishable from the originals."""
    scenario = generate(cell["attack"], cell["seed"])
    try:
        rec = run_session(arm=cell["arm"], model=cell["model"], scenario=scenario,
                          regime=regime)
    except Exception as exc:  # noqa: BLE001 — record, don't crash the run
        rec = {
            "run_id": f"{cell['arm']}:{cell['model']}:{cell['attack']}:seed{cell['seed']}",
            "arm": cell["arm"], "model": cell["model"], "regime": regime,
            "attack": cell["attack"], "seed": cell["seed"],
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
        }
    if tag:
        rec["run_id"] = f"{rec['run_id']}:{tag}"
    return rec


def _summary(records: list[dict]) -> str:
    """A counts-only run summary (no verdict — that is analyze.py's job)."""
    errors = [r for r in records if r.get("error")]
    ok = [r for r in records if not r.get("error")]
    lines = [f"sessions run: {len(records)}  ok: {len(ok)}  errors: {len(errors)}"]
    by_arm: dict[str, dict] = {}
    for r in ok:
        a = by_arm.setdefault(r["arm"], {"n": 0, "deal": 0, "above_list": 0,
                                         "loss": 0, "ff": 0, "walk_to": 0})
        a["n"] += 1
        a["deal"] += int(bool(r["deal"]))
        a["above_list"] += int(bool(r["above_list"]))
        a["loss"] += int(bool(r["loss"]))
        a["ff"] += int(r["format_failures"])
        a["walk_to"] += int(r.get("walked_by") == "timeout")
    for arm in sorted(by_arm):
        a = by_arm[arm]
        lines.append(
            f"  {arm:6s} n={a['n']:3d}  deals={a['deal']:3d}  "
            f"above_list={a['above_list']:3d}  loss={a['loss']:3d}  "
            f"format_failures={a['ff']:3d}  timeouts={a['walk_to']:3d}")
    if errors:
        lines.append("  errors (excluded from denominators, counted here):")
        for r in errors:
            lines.append(f"    {r['run_id']}: {r['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research.spendguard.run")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true",
                      help="1 seed, Haiku, A1+C0 (wiring check; results never quoted)")
    mode.add_argument("--full", action="store_true", help="the full registered battery")
    parser.add_argument("--workers", type=int, default=8, help="ThreadPool workers")
    parser.add_argument("--out", type=str, default=None,
                        help="output JSONL (default results/{smoke,full}.jsonl)")
    parser.add_argument("--attacks", type=str, default=None,
                        help="comma-separated attack subset (e.g. A3) for a "
                             "targeted re-run; default = the whole battery")
    parser.add_argument("--tag", type=str, default="",
                        help="suffix appended to every run_id (keeps re-run "
                             "records distinguishable, e.g. --tag a3fix)")
    parser.add_argument("--regime", choices=("rails", "blind"), default="rails",
                        help="rails = the original registered battery (default, "
                             "unchanged); blind = the Amendment-2 K1′ regime "
                             "(t=0 snapshot, prose-only, final-charge settlement; "
                             "results go to results/blind.jsonl)")
    args = parser.parse_args(argv)

    attacks_subset: tuple[str, ...] | None = None
    if args.attacks:
        attacks_subset = tuple(a.strip().upper() for a in args.attacks.split(","))
        unknown = [a for a in attacks_subset if a not in ATTACKS]
        if unknown:
            print(f"[spendguard] ERROR: unknown attack(s) {unknown}; "
                  f"valid: {list(ATTACKS)}", file=sys.stderr)
            return 2

    repo_root = Path(__file__).resolve().parents[2]
    _load_env(repo_root / ".env")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Default output names per regime: rails -> smoke/full.jsonl (unchanged);
    # blind -> smoke-blind/blind.jsonl (NEVER spliced into full.jsonl, per
    # Amendment 2). Attack subsets always get their own file.
    if args.regime == "blind":
        base = "smoke-blind" if args.smoke else "blind"
    else:
        base = "smoke" if args.smoke else "full"
    if args.out:
        out_path = Path(args.out)
    elif attacks_subset:
        # A subset run must NEVER clobber a full battery's results file.
        out_path = _RESULTS_DIR / f"{base}-{'-'.join(attacks_subset)}.jsonl"
    else:
        out_path = _RESULTS_DIR / f"{base}.jsonl"

    cells = _build_grid(smoke=args.smoke, attacks_subset=attacks_subset)
    if not cells:
        print("[spendguard] ERROR: attack subset excludes every cell in this mode",
              file=sys.stderr)
        return 2
    llm_cells = sum(1 for c in cells if c["arm"] in LLM_ARMS)
    print(f"[spendguard] {'SMOKE' if args.smoke else 'FULL'} "
          f"[regime={args.regime}]: {len(cells)} sessions "
          f"({llm_cells} LLM, {len(cells) - llm_cells} scripted) -> {out_path}")
    if (args.smoke or args.full) and not os.environ.get("ANTHROPIC_API_KEY") and llm_cells:
        print("[spendguard] ERROR: ANTHROPIC_API_KEY not set (env or repo .env) — "
              "LLM sessions will error. Aborting.", file=sys.stderr)
        return 2

    write_lock = threading.Lock()
    records: list[dict] = []
    with open(out_path, "w") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_cell, c, args.tag, args.regime): c for c in cells}
        done = 0
        for fut in as_completed(futures):
            rec = fut.result()
            with write_lock:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            records.append(rec)
            done += 1
            if done % 20 == 0 or done == len(cells):
                print(f"[spendguard] {done}/{len(cells)} sessions complete")

    print("\n" + _summary(records))
    print(f"\n[spendguard] wrote {len(records)} records to {out_path}")
    if args.full:
        suffix = " --regime blind" if args.regime == "blind" else ""
        print(f"[spendguard] next: python -m research.spendguard.analyze{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

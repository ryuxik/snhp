"""Run the gauntlet → leaderboard artifact.

Usage:
  # offline smoke (no API key): the naive baseline + the engine reference row
  python -m arena.gauntlet.run --candidate scripted-naive:naive --scenarios 12

  # a frontier model, both conditions (needs ANTHROPIC_API_KEY)
  python -m arena.gauntlet.run \
      --candidate anthropic:claude-haiku-4-5-20251001 \
      --conditions solo,advised --scenarios 20 \
      --out arena/web/leaderboard.json

Each --candidate provider:model plays every scenario in BOTH roles per
condition. Reference rows are NOT automatic — run them explicitly once per
artifact (`--candidate engine:` and `--candidate scripted-naive:naive-baseline`,
cheap and offline). Results merge into --out: rows for other models and for
this model's OTHER conditions are preserved, so the leaderboard accretes one
run at a time; a settings mismatch (version/seed/scenarios/deadline) refuses
to write rather than silently wiping prior rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

from arena.gauntlet.agents import EngineSeat, LLMSeat, NaiveSeat
from arena.gauntlet.protocol import (
    DEADLINE, NOTIONAL, MatchResult, aggregate, gen_gauntlet_scenarios, run_match,
)

GAUNTLET_VERSION = 1        # bump when scenarios/protocol change (scores reset)
SCENARIO_SEED = 20260709    # frozen: every model faces the identical gauntlet


def _mk_candidate(spec: str, match_seed: int, *, base_url: str | None = None,
                  api_key_env: str | None = None):
    """provider:model → seat. 'engine' and 'scripted-naive' need no network."""
    provider, _, model = spec.partition(":")
    if provider == "engine":
        return EngineSeat(match_seed)
    if provider == "champion":
        from arena.gauntlet.agents import GenomeSeat
        from arena.gauntlet.champion import CHAMPION_PATH, load_champion
        genome, _prov = load_champion(pathlib.Path(model) if model else CHAMPION_PATH)
        return GenomeSeat(genome, match_seed)
    if provider in ("scripted-naive", "naive"):
        return LLMSeat("scripted-naive", model or "naive-split")
    if provider == "anthropic":
        return LLMSeat("anthropic", model)
    if provider in ("openai", "openai-compat"):
        return LLMSeat("openai-compat", model, base_url=base_url,
                       api_key_env=api_key_env)
    raise SystemExit(f"unknown provider {provider!r} "
                     f"(use engine | scripted-naive | anthropic | openai-compat)")


def run_gauntlet(candidate_spec: str, conditions: list[str], n_scenarios: int,
                 deadline: int = DEADLINE, verbose: bool = True,
                 base_url: str | None = None,
                 api_key_env: str | None = None) -> dict:
    scenarios = gen_gauntlet_scenarios(n_scenarios, SCENARIO_SEED)
    provider, _, model = candidate_spec.partition(":")
    if provider == "champion" and not model:
        model = "evolved-champion"   # the public row name (model part = custom path)
    # LLM/naive seats are stateless across matches → build once (reuses the HTTP
    # client); engine/champion seats carry a per-match seed → build per match.
    shared_cand = None if provider in ("engine", "champion") else _mk_candidate(
        candidate_spec, 0, base_url=base_url, api_key_env=api_key_env)
    rows = {}
    all_matches = []
    for condition in conditions:
        results: list[MatchResult] = []
        for sid, (sc, w_s, w_b) in enumerate(scenarios):
            for role in ("seller", "buyer"):
                h = hashlib.blake2b(f"{SCENARIO_SEED}:{sid}:{role}".encode(),
                                    digest_size=8).digest()
                seed = int.from_bytes(h, "big") & 0x7FFFFFFF
                cand = shared_cand or _mk_candidate(candidate_spec, seed)
                r = run_match(cand, sc, w_s, w_b, role=role, condition=condition,
                              scenario_id=sid, match_seed=seed, deadline=deadline)
                results.append(r)
                all_matches.append({"model": model or provider,
                                    "condition": condition, **r.to_dict()})
                if verbose:
                    tag = "deal" if r.deal else f"no-deal({r.walked_by})"
                    print(f"  [{condition}] sc{sid:02d}/{role:<6} {tag:>16} "
                          f"capture={r.capture:.3f} left=${r.dollars_left:,.0f}",
                          flush=True)
        rows[condition] = aggregate(results)
    return {"model": model or provider, "provider": provider,
            "conditions": rows, "matches": all_matches}


def merge_artifact(out_path: pathlib.Path, entry: dict, n_scenarios: int,
                   deadline: int) -> dict:
    art = {"version": GAUNTLET_VERSION, "scenario_seed": SCENARIO_SEED,
           "scenarios": n_scenarios, "deadline": deadline, "notional": NOTIONAL,
           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rows": {}, "matches": []}
    if out_path.exists():
        # NEVER silently wipe prior results — refuse loudly on any mismatch.
        try:
            prev = json.loads(out_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(
                f"refusing to overwrite unreadable artifact {out_path} ({e}); "
                f"fix/delete it or use a fresh --out")
        bad = [(k, prev.get(k), want) for k, want in
               (("version", GAUNTLET_VERSION), ("scenario_seed", SCENARIO_SEED),
                ("scenarios", n_scenarios), ("deadline", deadline))
               if prev.get(k) != want]
        if bad:
            detail = ", ".join(f"{k}: artifact={a!r} vs run={b!r}" for k, a, b in bad)
            raise SystemExit(
                f"artifact {out_path} was built under different gauntlet settings "
                f"({detail}) — scores are not comparable; use a fresh --out")
        art["rows"] = prev.get("rows", {})
        # matches live in a sibling archive the web page never fetches
        # (leaderboard.json stays a few KB); tolerate legacy inline matches
        prev_matches = prev.get("matches", [])
        mp = matches_path(out_path)
        if not prev_matches and mp.exists():
            try:
                prev_matches = json.loads(mp.read_text()).get("matches", [])
            except (json.JSONDecodeError, OSError) as e:
                raise SystemExit(f"refusing to proceed with unreadable {mp} ({e})")
        # drop only THIS model's re-run conditions; keep everything else
        rerun = set(entry["conditions"])
        art["matches"] = [m for m in prev_matches
                          if not (m.get("model") == entry["model"]
                                  and m.get("condition") in rerun)]
    prev_row = art["rows"].get(entry["model"], {})
    art["rows"][entry["model"]] = {**prev_row, "provider": entry["provider"],
                                   **entry["conditions"]}
    art["matches"].extend(entry["matches"])
    return art


def matches_path(out_path: pathlib.Path) -> pathlib.Path:
    """The per-match archive (with transcripts) sits next to the artifact."""
    return out_path.with_name("gauntlet-matches.json")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--candidate", required=True,
                   help="provider:model (engine | scripted-naive:x | "
                        "anthropic:MODEL | openai-compat:MODEL)")
    p.add_argument("--conditions", default="solo",
                   help="comma-separated: solo,advised (engine/naive: solo only)")
    p.add_argument("--scenarios", type=int, default=20)
    p.add_argument("--deadline", type=int, default=DEADLINE)
    p.add_argument("--base-url", default=None,
                   help="openai-compat: API base URL (default https://api.openai.com/v1)")
    p.add_argument("--api-key-env", default=None,
                   help="openai-compat: env var holding the key (default OPENAI_API_KEY)")
    p.add_argument("--out", default=None, help="merge results into this JSON artifact")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    # seller opens: an odd deadline gives one seat an extra turn, and deadline<2
    # means the buyer seat never acts — both would poison the scores
    if args.deadline < 2 or args.deadline % 2:
        p.error("--deadline must be an even number >= 2 (equal turns per seat)")
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    t0 = time.time()
    entry = run_gauntlet(args.candidate, conditions, args.scenarios,
                         deadline=args.deadline, verbose=not args.quiet,
                         base_url=args.base_url, api_key_env=args.api_key_env)
    dt = time.time() - t0

    print(f"\n=== {entry['model']} — {args.scenarios} scenarios x 2 roles, "
          f"deadline {args.deadline}, {dt:.1f}s ===")
    for cond, row in entry["conditions"].items():
        lr = "n/a" if row["logroll"] is None else f"{row['logroll']:.3f}"
        fa = "" if row["advice_follow"] is None else f" advice_follow={row['advice_follow']:.2f}"
        print(f"  {cond:<8} deal_rate={row['deal_rate']:.2f} "
              f"capture={row['capture']:.3f} logroll={lr} "
              f"left=${row['dollars_left']:,.0f}/deal (per ${NOTIONAL:,} notional)"
              f"{fa} fmt_fail={row['format_failures']}")

    if args.out:
        out_path = pathlib.Path(args.out)
        art = merge_artifact(out_path, entry, args.scenarios, args.deadline)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        matches = art.pop("matches")   # visitors download rows, not transcripts
        out_path.write_text(json.dumps(art, indent=1))
        mp = matches_path(out_path)
        mp.write_text(json.dumps({"version": GAUNTLET_VERSION,
                                  "matches": matches}, indent=1))
        print(f"\nwrote {out_path} ({len(art['rows'])} model rows) + "
              f"{mp.name} ({len(matches)} matches)")
        # replay scripts for the duel theater — the site replays these, it
        # never calls an LLM (pay once per model, replay forever)
        from arena.gauntlet.replay import featured_replays
        scenarios = gen_gauntlet_scenarios(args.scenarios, SCENARIO_SEED)
        reps = featured_replays(matches, scenarios)
        rep_path = out_path.with_name("replays.json")
        rep_path.write_text(json.dumps(
            {"version": GAUNTLET_VERSION, "notional": NOTIONAL,
             "replays": reps}, indent=1))
        print(f"wrote {rep_path} ({len(reps)} featured replays)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

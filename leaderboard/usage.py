"""
Read the running usage log and report token totals + cost.

Usage:
  python -m leaderboard.usage                          # default log path
  python -m leaderboard.usage --log path/to/usage.jsonl
  python -m leaderboard.usage --watch                  # poll every 10s

Pricing comes from snhp.cost_calculator.PRICING (calibrated 2026-04-29).
"""
from __future__ import annotations

import argparse
import json
import os
import os.path as _op
import sys
import time
from collections import defaultdict


_REPO_ROOT = _op.dirname(_op.dirname(_op.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from snhp.cost_calculator import PRICING  # noqa: E402


_DEFAULT_LOG = _op.join(_op.dirname(_op.abspath(__file__)),
                         "results", "usage.jsonl")


def _summarize(path: str) -> dict:
    if not _op.isfile(path):
        return {
            "path": path, "exists": False,
            "total_calls": 0, "total_failures": 0,
            "by_agent": {}, "total_cost_usd": 0.0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_thoughts_tokens": 0, "median_latency_ms": None,
        }

    by_agent: dict[str, dict] = defaultdict(lambda: {
        "calls": 0,
        "failures": 0,
        "input_tokens": 0,
        "candidates_tokens": 0,
        "thoughts_tokens": 0,
        "latency_samples": [],
        "models": set(),
    })

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            agent = d.get("agent", "unknown")
            entry = by_agent[agent]
            if "error" in d:
                entry["failures"] += 1
                continue
            entry["calls"] += 1
            if d.get("model"):
                entry["models"].add(d["model"])
            entry["input_tokens"] += d.get("prompt_tokens") or 0
            entry["candidates_tokens"] += d.get("candidates_tokens") or 0
            entry["thoughts_tokens"] += d.get("thoughts_tokens") or 0
            if d.get("latency_ms") is not None:
                entry["latency_samples"].append(d["latency_ms"])

    total_cost = 0.0
    for agent, entry in by_agent.items():
        # Use the first model seen for pricing (in practice each agent
        # only ever uses one model per run).
        model = next(iter(entry["models"]), None) if entry["models"] else None
        if model and model in PRICING:
            p = PRICING[model]
            in_cost = (entry["input_tokens"] / 1_000_000) * p.input_per_1m_usd
            out_tokens = entry["candidates_tokens"] + entry["thoughts_tokens"]
            out_cost = (out_tokens / 1_000_000) * p.output_per_1m_usd
            entry["cost_usd"] = round(in_cost + out_cost, 4)
            total_cost += entry["cost_usd"]
        else:
            entry["cost_usd"] = None
        # Convert set to list for JSON.
        entry["models"] = sorted(entry["models"])
        # Median latency.
        ls = entry.pop("latency_samples")
        entry["median_latency_ms"] = (
            round(sorted(ls)[len(ls) // 2], 1) if ls else None
        )

    return {
        "path": path,
        "exists": True,
        "total_calls": sum(e["calls"] for e in by_agent.values()),
        "total_failures": sum(e["failures"] for e in by_agent.values()),
        "total_cost_usd": round(total_cost, 4),
        "total_input_tokens": sum(e["input_tokens"] for e in by_agent.values()),
        "total_output_tokens": sum(e["candidates_tokens"] for e in by_agent.values()),
        "total_thoughts_tokens": sum(e["thoughts_tokens"] for e in by_agent.values()),
        "by_agent": dict(by_agent),
    }


def _print(s: dict, *, header: bool = True) -> None:
    if header:
        print(f"=== Usage @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    if not s["exists"]:
        print(f"(no log at {s['path']} yet)")
        return
    print(f"path:   {s['path']}")
    print(f"calls:  {s['total_calls']:>6} successful, {s['total_failures']:>4} failures "
          f"({s['total_failures'] / max(1, s['total_calls'] + s['total_failures']) * 100:.1f}% failure rate)")
    print(f"tokens: {s['total_input_tokens']:>10,} in  /  "
          f"{s['total_output_tokens']:>8,} out  /  "
          f"{s['total_thoughts_tokens']:>8,} thoughts")
    print(f"COST:   ${s['total_cost_usd']:.4f}")
    if s["by_agent"]:
        print("\n  by agent:")
        for agent, entry in sorted(s["by_agent"].items()):
            cost = f"${entry['cost_usd']:.4f}" if entry["cost_usd"] is not None else "—"
            print(f"    {agent:<22} {entry['calls']:>4} calls  "
                  f"{entry['failures']:>3} fail  "
                  f"p50={entry['median_latency_ms']}ms  "
                  f"{cost}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", default=os.environ.get("LEADERBOARD_USAGE_LOG", _DEFAULT_LOG))
    p.add_argument("--watch", action="store_true",
                    help="Poll every 10s (until Ctrl-C). Useful while a "
                         "tournament is running.")
    p.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of human text.")
    args = p.parse_args()

    if args.watch:
        while True:
            s = _summarize(args.log)
            print("\033[2J\033[H", end="")  # clear screen
            _print(s)
            time.sleep(10)
    else:
        s = _summarize(args.log)
        if args.json:
            print(json.dumps(s, indent=2, default=str))
        else:
            _print(s)


if __name__ == "__main__":
    main()

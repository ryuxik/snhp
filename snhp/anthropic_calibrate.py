"""
Calibrate Anthropic Claude models against the leaderboard prompt.

Measures: prompt tokens, output tokens, thinking tokens (when extended
thinking is enabled), latency, and cache write/read counts when caching
is enabled. Uses the same prompt as `leaderboard.agents.gemini_negmas`
so the per-call cost projection is grounded in the actual workload.

Run:
    ANTHROPIC_API_KEY=sk-ant-... python -m snhp.anthropic_calibrate
    ANTHROPIC_API_KEY=sk-ant-... python -m snhp.anthropic_calibrate --thinking

Output is a JSON-serializable dict you can paste into a cost projection.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

try:
    import anthropic
except ImportError:
    print("anthropic package not installed. Run `pip install anthropic`.")
    sys.exit(1)

# Same prompt the leaderboard uses, so token counts are calibrated against
# the actual workload (not a toy "Hello, world").
_PROMPT = """You are an AI agent negotiating a B2B contract as the seller.
Single-axis utility convention: 1.0 = best for me, 0.0 = walk-away.

State:
  My role: seller
  My walk-away utility (reservation): 0.400
  Time elapsed (0=start, 1=deadline): 0.50
  History (utility-to-me at each round):
  round 0: I (seller) demanded utility 0.850
  round 1: opponent demanded utility 0.300 (= I would get 0.700)
  round 2: I (seller) demanded utility 0.780
  round 3: opponent demanded utility 0.350 (= I would get 0.650)
  round 4: I (seller) demanded utility 0.720
  round 5: opponent demanded utility 0.380 (= I would get 0.620)
Opponent's last offer to you: 0.620

Output JSON: {"target_utility": <float in [0.400, 1.0]>}.
Return ONLY the JSON object."""


def _call(client, *, model: str, thinking: bool = False) -> dict:
    """Single Anthropic call; returns measured usage fields."""
    kwargs = {
        "model": model,
        "max_tokens": 256 if not thinking else 2048,  # thinking needs headroom
        "messages": [{"role": "user", "content": _PROMPT}],
        "temperature": 0.2 if not thinking else 1.0,  # thinking requires t=1
    }
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}
    t0 = time.time()
    try:
        r = client.messages.create(**kwargs)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    dt_ms = (time.time() - t0) * 1000
    u = r.usage
    text = ""
    for block in r.content:
        if hasattr(block, "text"):
            text = block.text
            break
    return {
        "latency_ms": round(dt_ms, 0),
        "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        "cache_read_input_tokens": int(getattr(u, "cache_read_input_tokens", 0) or 0),
        "thinking_enabled": thinking,
        "text_preview": text.strip()[:80],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+",
                    default=["claude-sonnet-4-5", "claude-haiku-4-5"],
                    help="Model IDs to calibrate.")
    p.add_argument("--n", type=int, default=3,
                    help="Calls per (model, thinking) combo for variance.")
    p.add_argument("--thinking", action="store_true",
                    help="Also measure with extended thinking enabled.")
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print("ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic()

    results: dict[str, list[dict]] = {}
    for model in args.models:
        configs = [False] + ([True] if args.thinking else [])
        for thinking in configs:
            key = f"{model} thinking={'on' if thinking else 'off'}"
            print(f"\n=== {key} ({args.n} calls) ===")
            samples = []
            for i in range(args.n):
                r = _call(client, model=model, thinking=thinking)
                if "error" in r:
                    print(f"  call {i}: {r['error']}")
                    continue
                samples.append(r)
                print(f"  call {i}: in={r['input_tokens']} out={r['output_tokens']} "
                      f"latency={r['latency_ms']:.0f}ms text={r['text_preview']!r}")
            if not samples:
                continue
            results[key] = samples
            in_tokens = [s["input_tokens"] for s in samples]
            out_tokens = [s["output_tokens"] for s in samples]
            latencies = [s["latency_ms"] for s in samples]
            print(f"  median: in={statistics.median(in_tokens):.0f} "
                  f"out={statistics.median(out_tokens):.0f} "
                  f"latency={statistics.median(latencies):.0f}ms")

    print("\n=== Summary (paste into projection) ===")
    print(json.dumps({
        k: {
            "median_input_tokens": statistics.median([s["input_tokens"] for s in v]),
            "median_output_tokens": statistics.median([s["output_tokens"] for s in v]),
            "median_latency_ms": statistics.median([s["latency_ms"] for s in v]),
            "samples": len(v),
        }
        for k, v in results.items()
    }, indent=2))


if __name__ == "__main__":
    main()

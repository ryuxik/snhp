"""
Real calculator for SNHP-vs-LLM tournament cost.

Two modes:
  1. `--estimate`  — pure math, conservative defaults from prior calibration.
                     Free (no API call). Defaults assume worst-case prompt
                     growth from history accumulation.
  2. `--calibrate` — makes 3 real API calls against the proposed prompt
                     to measure actual token usage. Costs ~$0.01-0.05
                     depending on model. THEN projects the full run.

Run plan we're costing:
  SNHP-vs-{Claude,Sonnet,Haiku} pair-welfare tournament
    21 NegMAS opponents in roster + Claude as competitor
    Claude plays both seller and buyer side per matchup
    N_ROUNDS=20 reps × ~10 negotiation steps avg
    Each step has 1 LLM call (Claude proposes/responds)

Usage:
    # Just see the projected cost from defaults (no API call):
    python -m snhp.snhp_vs_llm_cost --model claude-sonnet-4-5 --estimate

    # Calibrate with 3 real calls + project (recommended):
    ANTHROPIC_API_KEY=sk-ant-... python -m snhp.snhp_vs_llm_cost \\
        --model claude-sonnet-4-5 --calibrate

    # Smaller config (single market, N=5 reps):
    python -m snhp.snhp_vs_llm_cost --model claude-sonnet-4-5 \\
        --estimate --n-rounds 5 --n-opponents 5
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass

# Allow running standalone (without snhp installed as a package).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cost_calculator import (
    PRICING, per_call_cost, PRICING_TABLE_LAST_VERIFIED,
)


# ─── The actual prompt SNHP-vs-LLM tournament will send ─────────────────────
# Mid-game state: 6 rounds of history + role + reservation + last-offer.
# This is the WORST CASE prompt size — early rounds are smaller, late rounds
# are similar (history is capped). Calibration uses this for upper bound.
_BENCHMARK_PROMPT = """You are an AI agent negotiating a B2B contract.

Role: {role}
Walk-away utility (reservation): 0.400
Time elapsed (0=start, 1=deadline): {t:.2f}
Negotiation history (utility-to-me each round):
{history_lines}
Opponent's last offer to me (my utility): {last_opp_util:.3f}

Decide:
  - What target utility should I demand next? (range [0.400, 0.95])
  - Should I accept the opponent's last offer? (boolean)

Output JSON: {{"target_utility": <float>, "accept": <bool>}}.
Return ONLY the JSON object."""


def _build_calibration_prompt(role: str = "seller", t: float = 0.50,
                                n_history: int = 6,
                                last_opp_util: float = 0.380) -> str:
    """Construct a representative mid-game prompt for token measurement."""
    history_lines = []
    for i in range(n_history):
        if i % 2 == 0:
            history_lines.append(f"  round {i}: I demanded utility {0.85 - i*0.025:.3f}")
        else:
            opp = 0.30 + (i // 2) * 0.025
            history_lines.append(
                f"  round {i}: opponent demanded utility {opp:.3f} "
                f"(= I would get {1-opp:.3f})"
            )
    return _BENCHMARK_PROMPT.format(
        role=role, t=t,
        history_lines="\n".join(history_lines),
        last_opp_util=last_opp_util,
    )


# ─── Conservative defaults (from prior measurement) ─────────────────────────


@dataclass(frozen=True)
class TokenShape:
    avg_input: int
    avg_output: int
    p95_input: int
    p95_output: int
    source: str


# These are conservative defaults derived from the leaderboard prompt
# (293 input / 12 output measured 2026-04-29). The new SNHP-vs-LLM prompt
# adds an `accept` boolean to the decision so output is slightly larger.
# Inputs grow with history; we use a 1.4x multiplier on the 293 baseline
# for a typical mid-game state (6 rounds of history).
_DEFAULT_TOKEN_SHAPE = TokenShape(
    avg_input=420,    # 293 × 1.4 (history + new fields)
    avg_output=30,    # 12 × 2.5 (additional `accept` field, JSON formatting)
    p95_input=560,    # +33% upper bound
    p95_output=60,    # 2x avg for verbose models
    source="conservative defaults from leaderboard calibration 2026-04-29",
)


# ─── Live calibration via the Anthropic API ─────────────────────────────────


def calibrate(model: str, n_calls: int = 3,
               thinking: bool = False) -> TokenShape:
    """Make `n_calls` real API calls; return measured TokenShape."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: `anthropic` package required for --calibrate.")
        print("       pip install anthropic")
        sys.exit(2)

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(2)

    client = anthropic.Anthropic()
    in_tokens, out_tokens = [], []
    print(f"Calibrating {model} with {n_calls} live calls...")
    for i in range(n_calls):
        prompt = _build_calibration_prompt()
        kwargs = {
            "model": model,
            "max_tokens": 256 if not thinking else 2048,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2 if not thinking else 1.0,
        }
        if thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}
        try:
            r = client.messages.create(**kwargs)
        except Exception as e:
            print(f"  call {i}: ERROR — {type(e).__name__}: {e}")
            continue
        u = r.usage
        in_t = int(getattr(u, "input_tokens", 0) or 0)
        out_t = int(getattr(u, "output_tokens", 0) or 0)
        in_tokens.append(in_t)
        out_tokens.append(out_t)
        print(f"  call {i}: in={in_t} out={out_t}")

    if not in_tokens:
        print("ERROR: All calibration calls failed.")
        sys.exit(2)

    return TokenShape(
        avg_input=int(statistics.mean(in_tokens)),
        avg_output=int(statistics.mean(out_tokens)),
        p95_input=int(max(in_tokens)),
        p95_output=int(max(out_tokens)),
        source=f"live calibration {n_calls} calls × {model} on {time.strftime('%Y-%m-%d')}",
    )


# ─── Run-cost projection ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunPlan:
    """Tournament shape — the "what we're going to run" knobs."""
    n_opponents: int          # NegMAS opponents in the roster (e.g. 21)
    n_rounds: int             # Reps per matchup (e.g. 20)
    n_directions: int         # Per matchup: LLM-as-A and LLM-as-B → 2
    n_steps_per_game: int     # Avg negotiation steps per game (e.g. 10)
    n_calls_per_step: int     # LLM calls per step (1 = propose-or-respond)
    description: str

    @property
    def total_calls(self) -> int:
        return (self.n_opponents * self.n_rounds * self.n_directions
                * self.n_steps_per_game * self.n_calls_per_step)


_DEFAULT_PLAN = RunPlan(
    n_opponents=21,
    n_rounds=20,
    n_directions=2,
    n_steps_per_game=10,
    n_calls_per_step=1,
    description="Full SNHP-vs-LLM tournament (single market)",
)


def project_cost(plan: RunPlan, shape: TokenShape, model: str,
                  thinking_tokens_per_call: int = 0,
                  use_cache: bool = False,
                  batch: bool = False) -> dict:
    """Project total cost for the plan + measured/default token shape."""
    if model not in PRICING:
        raise KeyError(f"Unknown model {model!r}; available: {sorted(PRICING)}")
    p = PRICING[model]

    # Avg-case
    per_call_avg = per_call_cost(
        model, input_tokens=shape.avg_input, output_tokens=shape.avg_output,
        thinking_tokens=thinking_tokens_per_call, batch=batch,
    )
    # p95-case (upper-bound estimate)
    per_call_p95 = per_call_cost(
        model, input_tokens=shape.p95_input, output_tokens=shape.p95_output,
        thinking_tokens=thinking_tokens_per_call, batch=batch,
    )

    # Cache-aware variant: assume system prompt (~80% of input) is cached
    # after first call → all subsequent calls pay 0.1x on the cached part.
    per_call_cached = None
    if use_cache and p.cache_read_per_1m_usd is not None:
        cached_portion = int(shape.avg_input * 0.80)
        uncached_portion = shape.avg_input - cached_portion
        per_call_cached = per_call_cost(
            model, input_tokens=uncached_portion,
            output_tokens=shape.avg_output,
            thinking_tokens=thinking_tokens_per_call,
            cache_read_tokens=cached_portion, batch=batch,
        )

    total_calls = plan.total_calls
    return {
        "plan": plan.description,
        "model": model,
        "pricing_verified": PRICING_TABLE_LAST_VERIFIED,
        "token_shape_source": shape.source,
        "tokens_per_call": {
            "avg_input": shape.avg_input,
            "avg_output": shape.avg_output,
            "p95_input": shape.p95_input,
            "p95_output": shape.p95_output,
        },
        "total_calls": total_calls,
        "calls_breakdown": {
            "n_opponents": plan.n_opponents,
            "n_rounds": plan.n_rounds,
            "n_directions": plan.n_directions,
            "n_steps_per_game": plan.n_steps_per_game,
            "n_calls_per_step": plan.n_calls_per_step,
        },
        "per_call_avg_usd": round(per_call_avg, 6),
        "per_call_p95_usd": round(per_call_p95, 6),
        "per_call_cached_usd": (
            round(per_call_cached, 6) if per_call_cached is not None else None
        ),
        "estimated_total_avg_usd": round(per_call_avg * total_calls, 4),
        "estimated_total_p95_usd": round(per_call_p95 * total_calls, 4),
        "estimated_total_cached_usd": (
            round(per_call_cached * total_calls, 4)
            if per_call_cached is not None else None
        ),
    }


# ─── CLI ────────────────────────────────────────────────────────────────────


def _format_dollars(d: float) -> str:
    if d < 0.01:
        return f"{d * 100:.2f}¢"
    if d < 1:
        return f"${d:.3f}"
    return f"${d:,.2f}"


def _print_projection(proj: dict) -> None:
    print()
    print("=" * 72)
    print(f"  SNHP-vs-LLM cost projection")
    print("=" * 72)
    print(f"  Plan:          {proj['plan']}")
    print(f"  Model:         {proj['model']} "
          f"(prices verified {proj['pricing_verified']})")
    print(f"  Token shape:   {proj['token_shape_source']}")
    print()
    b = proj["calls_breakdown"]
    print(f"  Calls breakdown:")
    print(f"    {b['n_opponents']} opponents × {b['n_rounds']} reps × "
          f"{b['n_directions']} directions × {b['n_steps_per_game']} steps "
          f"× {b['n_calls_per_step']} calls/step")
    print(f"    = {proj['total_calls']:,} total LLM calls")
    print()
    t = proj["tokens_per_call"]
    print(f"  Tokens/call:")
    print(f"    avg: {t['avg_input']:>5} input / {t['avg_output']:>4} output")
    print(f"    p95: {t['p95_input']:>5} input / {t['p95_output']:>4} output")
    print()
    print(f"  Per-call cost:")
    print(f"    avg:        {_format_dollars(proj['per_call_avg_usd'])}")
    print(f"    p95:        {_format_dollars(proj['per_call_p95_usd'])}")
    if proj.get("per_call_cached_usd") is not None:
        print(f"    w/ cache:   {_format_dollars(proj['per_call_cached_usd'])}"
              f"  (assumes 80% cache hit on input)")
    print()
    print(f"  >>> ESTIMATED TOTAL COST <<<")
    print(f"    avg case:   {_format_dollars(proj['estimated_total_avg_usd'])}")
    print(f"    p95 case:   {_format_dollars(proj['estimated_total_p95_usd'])}"
          f"  (worst-case upper bound)")
    if proj.get("estimated_total_cached_usd") is not None:
        print(f"    w/ cache:   {_format_dollars(proj['estimated_total_cached_usd'])}"
              f"  (with prompt caching enabled)")
    print()


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--model", default="claude-sonnet-4-6",
                    choices=sorted(PRICING.keys()),
                    help="Model to project cost for.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--estimate", action="store_true",
                       help="Use conservative default token counts (no API call).")
    mode.add_argument("--calibrate", action="store_true",
                       help="Make 3 real API calls (~5¢) to measure actual tokens.")
    p.add_argument("--n-opponents", type=int, default=_DEFAULT_PLAN.n_opponents,
                    help="Number of NegMAS opponents in roster.")
    p.add_argument("--n-rounds", type=int, default=_DEFAULT_PLAN.n_rounds,
                    help="Reps per matchup.")
    p.add_argument("--n-directions", type=int, default=_DEFAULT_PLAN.n_directions,
                    help="Number of role directions (LLM-as-A + LLM-as-B = 2).")
    p.add_argument("--n-steps", type=int, default=_DEFAULT_PLAN.n_steps_per_game,
                    help="Avg negotiation steps per game.")
    p.add_argument("--n-calls-per-step", type=int,
                    default=_DEFAULT_PLAN.n_calls_per_step,
                    help="LLM calls per negotiation step.")
    p.add_argument("--use-cache", action="store_true",
                    help="Project cost assuming prompt caching is enabled "
                         "(80%% of input cached after first call).")
    p.add_argument("--batch", action="store_true",
                    help="Apply Anthropic Batch API 50%% discount.")
    p.add_argument("--thinking-tokens", type=int, default=0,
                    help="Tokens spent on extended thinking per call.")
    p.add_argument("--json", action="store_true",
                    help="Emit projection as JSON (machine-readable).")
    args = p.parse_args()

    plan = RunPlan(
        n_opponents=args.n_opponents,
        n_rounds=args.n_rounds,
        n_directions=args.n_directions,
        n_steps_per_game=args.n_steps,
        n_calls_per_step=args.n_calls_per_step,
        description=(
            f"SNHP-vs-LLM tournament: {args.n_opponents} opp × "
            f"{args.n_rounds} reps × {args.n_directions} dir × "
            f"{args.n_steps} steps"
        ),
    )

    if args.calibrate:
        shape = calibrate(args.model)
    else:
        shape = _DEFAULT_TOKEN_SHAPE

    proj = project_cost(
        plan, shape, args.model,
        thinking_tokens_per_call=args.thinking_tokens,
        use_cache=args.use_cache,
        batch=args.batch,
    )

    if args.json:
        print(json.dumps(proj, indent=2, sort_keys=True))
    else:
        _print_projection(proj)


if __name__ == "__main__":
    main()

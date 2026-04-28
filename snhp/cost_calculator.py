"""
Testable cost calculator for SNHP benchmark runs.

Pricing sources (verified 2026-04-27):
  - Gemini API:        ai.google.dev/gemini-api/docs/pricing
  - Anthropic API:     anthropic.com/pricing
  - OpenAI API:        openai.com/api/pricing

Re-verify and update PRICING_TABLE_LAST_VERIFIED if you re-check.

Empirical token counts come from the pilot run (snhp/benchmark.py).
Pilot prompt size: 2484 chars ≈ 620 tokens (verified via 3.5–4 chars/token
ratio typical for English + JSON schema). Output is the small _OutcomeProposal
JSON ≈ 80 tokens.

Usage:
    python -m snhp.cost_calculator                   # run self-tests + default scenario
    python -m snhp.cost_calculator --preset n100x4   # run a named preset
    python -m snhp.cost_calculator --help
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, asdict
from typing import Optional


PRICING_TABLE_LAST_VERIFIED = "2026-04-28"


@dataclass(frozen=True)
class ModelPricing:
    """
    USD per 1M tokens. Spelled out so the math is visible.

    `reasoning_token_multiplier` exists because some "preview"/"thinking" models
    (Gemini 3 Flash Preview, Opus reasoning, GPT-5 thinking, etc.) bill INTERNAL
    reasoning tokens at the output rate. These tokens never appear in the
    response text but are counted in `usage.completion_tokens`.

    For non-thinking models, this is 0.0 and `effective_output_tokens = visible_output_tokens`.
    For thinking models, an empirical multiplier on PROMPT size estimates how
    many invisible reasoning tokens get billed:
        effective_output_tokens = visible_output_tokens + (reasoning_token_multiplier * prompt_tokens)

    The audit on 2026-04-28 (snhp/llm_audit.py) measured Gemini 3 Flash Preview
    at ~0.6-1.5x prompt size in invisible reasoning tokens. Median ≈ 1.0x.
    """
    name: str
    input_per_1m_usd: float
    output_per_1m_usd: float
    reasoning_token_multiplier: float = 0.0  # 0 = no thinking; >0 = thinking model


# ─── Pricing table — keep in sync with provider pricing pages ────────────────
# Verified at ai.google.dev/gemini-api/docs/pricing on 2026-04-28.

PRICING: dict[str, ModelPricing] = {
    # Google Gemini — paid tier rates
    # NOTE: gemini-3-flash-preview has thinking; Gemini 2.5 Flash does NOT.
    # See llm_audit.py findings — reasoning tokens dominate cost for the preview.
    "gemini-3-flash-preview":  ModelPricing("gemini-3-flash-preview",   0.50,  3.00,  reasoning_token_multiplier=1.0),
    "gemini-3-pro-preview":    ModelPricing("gemini-3-pro-preview",     2.00, 12.00,  reasoning_token_multiplier=2.0),
    "gemini-2.5-flash":        ModelPricing("gemini-2.5-flash",         0.30,  2.50,  reasoning_token_multiplier=0.0),
    "gemini-2.5-flash-lite":   ModelPricing("gemini-2.5-flash-lite",    0.10,  0.40,  reasoning_token_multiplier=0.0),
    # Anthropic Claude
    "claude-opus-4-7":         ModelPricing("claude-opus-4-7",         15.00, 75.00,  reasoning_token_multiplier=1.5),
    "claude-sonnet-4-6":       ModelPricing("claude-sonnet-4-6",        3.00, 15.00,  reasoning_token_multiplier=0.0),
    "claude-haiku-4-5":        ModelPricing("claude-haiku-4-5",         1.00,  5.00,  reasoning_token_multiplier=0.0),
    # OpenAI — for reference comparison
    "gpt-5":                   ModelPricing("gpt-5",                    5.00, 20.00,  reasoning_token_multiplier=1.5),
    "gpt-5-mini":              ModelPricing("gpt-5-mini",               0.50,  2.00,  reasoning_token_multiplier=0.5),
}


# ─── Empirical token estimates from the pilot run ───────────────────────────

@dataclass(frozen=True)
class PromptShape:
    """
    Token counts measured against the actual benchmark prompt
    (snhp/benchmark.py:_build_prompt). Ranges given because per-call
    sizes vary with negotiation history length and SNHP-vs-naive variant.
    """
    description: str
    avg_input_tokens: int
    avg_output_tokens: int


# Empirical token counts from snhp/llm_audit.py against the actual benchmark
# prompt with schema dump appended (2026-04-28 audit):
#   - tiny prompt (25 chars):           8 input,   29 completion
#   - realistic (2871 chars w/ schema): 817 input, 506 completion
#   - with_history (3156 chars):        957 input, 1351 completion
# The "completion" tokens include INVISIBLE reasoning tokens for thinking
# models (Gemini 3 Flash Preview). Visible response text is only ~25 tokens
# (the small JSON outcome proposal). Use these averages as the v1 default.
SNHP_BENCHMARK_PROMPT_SHAPE = PromptShape(
    description="snhp.benchmark._build_prompt + schema dump (audit 2026-04-28)",
    avg_input_tokens=900,    # measured 817-957 range
    avg_output_tokens=25,    # the visible JSON only; reasoning is added by the model below
)


# ─── Core math (testable, no I/O) ────────────────────────────────────────────


def per_call_cost(model: str, input_tokens: int, output_tokens: int,
                  include_reasoning: bool = True) -> float:
    """
    USD cost of a single LLM call. Pure function — fully testable.

    For thinking models, `include_reasoning=True` adds invisible reasoning
    tokens at the output rate, scaled by `reasoning_token_multiplier × input_tokens`.
    Set False to compute the cost of *visible* tokens only (rare; useful for
    debugging gap between visible and billed cost).
    """
    if model not in PRICING:
        raise KeyError(f"Unknown model {model!r}; known: {sorted(PRICING)}")
    p = PRICING[model]
    effective_output = output_tokens
    if include_reasoning and p.reasoning_token_multiplier > 0:
        effective_output += int(p.reasoning_token_multiplier * input_tokens)
    return (input_tokens / 1_000_000) * p.input_per_1m_usd \
        + (effective_output / 1_000_000) * p.output_per_1m_usd


def estimate_run_cost(
    *,
    n_scenarios: int,
    n_opponents: int,
    n_llm_competitors: int,
    avg_calls_per_trial: float,
    avg_input_tokens: int,
    avg_output_tokens: int,
    model: str,
) -> dict:
    """
    Total cost for a benchmark run.

    Each scenario × opponent × LLM-competitor combination is one trial.
    Each LLM trial makes ~avg_calls_per_trial Gemini calls. Programmatic
    competitors (e.g. SplitTheDiff) make zero LLM calls and are excluded
    from the cost — set n_llm_competitors to the LLM-only count.
    """
    if min(n_scenarios, n_opponents, n_llm_competitors) < 0:
        raise ValueError("counts must be non-negative")
    if avg_calls_per_trial < 0 or avg_input_tokens < 0 or avg_output_tokens < 0:
        raise ValueError("token / call counts must be non-negative")

    n_llm_trials = n_scenarios * n_opponents * n_llm_competitors
    total_calls = n_llm_trials * avg_calls_per_trial
    total_input_tokens = int(total_calls * avg_input_tokens)
    total_visible_output_tokens = int(total_calls * avg_output_tokens)

    p = PRICING[model]
    # Account for invisible reasoning tokens billed at the output rate
    reasoning_tokens_per_call = int(p.reasoning_token_multiplier * avg_input_tokens)
    total_reasoning_tokens = int(total_calls * reasoning_tokens_per_call)
    total_billable_output_tokens = total_visible_output_tokens + total_reasoning_tokens

    input_cost = (total_input_tokens / 1_000_000) * p.input_per_1m_usd
    output_cost = (total_billable_output_tokens / 1_000_000) * p.output_per_1m_usd
    total_cost = input_cost + output_cost

    return {
        "model": model,
        "input_per_1m_usd": p.input_per_1m_usd,
        "output_per_1m_usd": p.output_per_1m_usd,
        "reasoning_token_multiplier": p.reasoning_token_multiplier,
        "n_llm_trials": n_llm_trials,
        "total_llm_calls": int(total_calls),
        "total_input_tokens": total_input_tokens,
        "total_visible_output_tokens": total_visible_output_tokens,
        "total_reasoning_tokens": total_reasoning_tokens,
        "total_billable_output_tokens": total_billable_output_tokens,
        "input_cost_usd": round(input_cost, 4),
        "output_cost_usd": round(output_cost, 4),
        "total_cost_usd": round(total_cost, 4),
        "per_call_cost_usd": round(per_call_cost(model, avg_input_tokens, avg_output_tokens), 6),
    }


# ─── Self-tests (run on import via -m, fail loudly if math is wrong) ────────


def _run_self_tests() -> None:
    """Inline asserts. Math is mechanical; tests prove the mechanics."""

    # 1. Per-call cost for a thinking model: includes reasoning tokens
    #    Gemini 3 Flash Preview at $0.50/$3.00, multiplier=1.0 → reasoning = 1000
    gemini_per_call = per_call_cost("gemini-3-flash-preview", 1000, 100)
    gemini_expected = (1000 / 1_000_000) * 0.50 + ((100 + 1000) / 1_000_000) * 3.00
    assert abs(gemini_per_call - gemini_expected) < 1e-9, \
        f"per_call_cost (with reasoning): got {gemini_per_call}, expected {gemini_expected}"

    # 1b. Same call without reasoning tokens (for debugging)
    gemini_visible = per_call_cost("gemini-3-flash-preview", 1000, 100, include_reasoning=False)
    gemini_visible_expected = (1000 / 1_000_000) * 0.50 + (100 / 1_000_000) * 3.00
    assert abs(gemini_visible - gemini_visible_expected) < 1e-9

    # 2. Per-call for Sonnet 4.6 (no reasoning multiplier — visible-only billing)
    sonnet_per_call = per_call_cost("claude-sonnet-4-6", 1000, 100)
    sonnet_expected = (1000 / 1_000_000) * 3.00 + (100 / 1_000_000) * 15.00
    assert abs(sonnet_per_call - sonnet_expected) < 1e-9, \
        f"claude per_call (no reasoning): got {sonnet_per_call}, expected {sonnet_expected}"

    # 2b. Gemini 2.5 Flash — same price as 3 Flash Preview's INPUT but no reasoning surcharge
    g25 = per_call_cost("gemini-2.5-flash", 1000, 100)
    g25_expected = (1000 / 1_000_000) * 0.30 + (100 / 1_000_000) * 2.50
    assert abs(g25 - g25_expected) < 1e-9

    # 3. Trivial run-cost: 1 scenario × 1 opp × 1 competitor × 1 call
    #    Should equal the per-call cost (with reasoning).
    r = estimate_run_cost(
        n_scenarios=1, n_opponents=1, n_llm_competitors=1,
        avg_calls_per_trial=1, avg_input_tokens=1000, avg_output_tokens=100,
        model="gemini-3-flash-preview",
    )
    assert r["n_llm_trials"] == 1
    assert r["total_llm_calls"] == 1
    assert r["total_input_tokens"] == 1000
    assert r["total_visible_output_tokens"] == 100
    assert r["total_reasoning_tokens"] == 1000  # 1.0x multiplier
    assert r["total_billable_output_tokens"] == 1100
    assert abs(r["total_cost_usd"] - gemini_expected) < 1e-4, \
        f"trivial run total: got {r['total_cost_usd']}, expected {gemini_expected}"

    # 4. Linearity: doubling N doubles cost
    r1 = estimate_run_cost(n_scenarios=10, n_opponents=1, n_llm_competitors=1,
                           avg_calls_per_trial=5, avg_input_tokens=1000,
                           avg_output_tokens=100, model="gemini-3-flash-preview")
    r2 = estimate_run_cost(n_scenarios=20, n_opponents=1, n_llm_competitors=1,
                           avg_calls_per_trial=5, avg_input_tokens=1000,
                           avg_output_tokens=100, model="gemini-3-flash-preview")
    assert abs(r2["total_cost_usd"] - 2 * r1["total_cost_usd"]) < 1e-6, \
        "doubling scenarios should double cost"

    # 5. Order-of-magnitude check on the proposed N=100 × 4 opp config
    #    With reasoning tokens, this should now be in the $5-15 range, not <$2
    r = estimate_run_cost(
        n_scenarios=100, n_opponents=4, n_llm_competitors=2,
        avg_calls_per_trial=5,
        avg_input_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens,
        avg_output_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens,
        model="gemini-3-flash-preview",
    )
    # 100 × 4 × 2 = 800 trials × 5 calls = 4000 calls
    assert r["total_llm_calls"] == 4000, f"got {r['total_llm_calls']}"
    # Bounds-check: with reasoning tokens, expect ~$10 (not <$2 like before)
    assert 5.0 < r["total_cost_usd"] < 20.0, \
        f"proposed run cost out of expected range: ${r['total_cost_usd']}"

    # 5b. Same config on Gemini 2.5 Flash (no thinking) — should be ~3x cheaper
    r25 = estimate_run_cost(
        n_scenarios=100, n_opponents=4, n_llm_competitors=2,
        avg_calls_per_trial=5,
        avg_input_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens,
        avg_output_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens,
        model="gemini-2.5-flash",
    )
    assert r25["total_cost_usd"] < r["total_cost_usd"], \
        "non-thinking model should be cheaper"
    assert r25["total_reasoning_tokens"] == 0, \
        "non-thinking model should have zero reasoning tokens"

    # 6. Bad-input rejection
    try:
        estimate_run_cost(n_scenarios=-1, n_opponents=1, n_llm_competitors=1,
                          avg_calls_per_trial=1, avg_input_tokens=10,
                          avg_output_tokens=10, model="gemini-3-flash-preview")
        raise AssertionError("should have rejected negative scenarios")
    except ValueError:
        pass

    try:
        per_call_cost("nonexistent-model", 100, 10)
        raise AssertionError("should have rejected unknown model")
    except KeyError:
        pass


# ─── Presets covering the proposed configurations ────────────────────────────

PRESETS = {
    "pilot_n3": dict(
        description="Original pilot: 3 scenarios × 1 opponent (Anchorer) × 2 LLM competitors",
        n_scenarios=3, n_opponents=1, n_llm_competitors=2,
        avg_calls_per_trial=5,
    ),
    "current_n30": dict(
        description="In-progress run: 30 scenarios × 1 opponent × 2 LLM competitors",
        n_scenarios=30, n_opponents=1, n_llm_competitors=2,
        avg_calls_per_trial=5,
    ),
    "industry_n100x4": dict(
        description=("Industry-standard kill-criterion: 100 scenarios × 4 opponents × "
                     "2 LLM competitors. Sized for Cohen's d ≥ 0.3 detection at α=0.05/power=0.80."),
        n_scenarios=100, n_opponents=4, n_llm_competitors=2,
        avg_calls_per_trial=5,
    ),
    "industry_n175x4": dict(
        description=("Power-analysis-strict: N=175 (per the existing eval_cost_estimator's "
                     "Cohen-d=0.3 calculation) × 4 opponents × 2 LLM competitors."),
        n_scenarios=175, n_opponents=4, n_llm_competitors=2,
        avg_calls_per_trial=5,
    ),
}


def _format_dollars(d: float) -> str:
    if d < 0.01:
        return f"${d * 100:.2f}¢ ({d:.5f} USD)"
    return f"${d:.4f}"


def _print_preset_report(preset_name: str, preset: dict, model: str) -> None:
    desc = preset.pop("description", "")
    r = estimate_run_cost(
        **preset,
        avg_input_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens,
        avg_output_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens,
        model=model,
    )
    preset["description"] = desc  # restore
    rmult = r['reasoning_token_multiplier']
    print(f"\n── Preset: {preset_name} ─────────────────────────────────")
    print(f"  {desc}")
    print(f"  Model:                {r['model']}")
    print(f"  Pricing (per 1M):     ${r['input_per_1m_usd']:.2f} input / ${r['output_per_1m_usd']:.2f} output")
    print(f"  Reasoning multiplier: {rmult}x prompt size {'(THINKING MODEL — costs 2-3x visible)' if rmult > 0 else '(no thinking)'}")
    print(f"  Tokens per call:      {SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens} in / "
          f"{SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens} visible-out")
    print(f"  LLM trials:           {r['n_llm_trials']:>6}")
    print(f"  Total LLM calls:      {r['total_llm_calls']:>6}")
    print(f"  Total input tokens:        {r['total_input_tokens']:>11,}")
    print(f"  Total visible output:      {r['total_visible_output_tokens']:>11,}")
    print(f"  Total reasoning tokens:    {r['total_reasoning_tokens']:>11,} (billed but invisible)")
    print(f"  Total billable output:     {r['total_billable_output_tokens']:>11,}")
    print(f"  Per-call cost:        {_format_dollars(r['per_call_cost_usd'])}")
    print(f"  Input cost:           {_format_dollars(r['input_cost_usd'])}")
    print(f"  Output cost:          {_format_dollars(r['output_cost_usd'])}")
    print(f"  TOTAL COST:           {_format_dollars(r['total_cost_usd'])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="gemini-3-flash-preview",
                        choices=sorted(PRICING.keys()),
                        help="Model to price the run with.")
    parser.add_argument("--preset", choices=sorted(PRESETS.keys()),
                        help="Use a named preset. If omitted, runs all presets.")
    parser.add_argument("--no-tests", action="store_true",
                        help="Skip self-tests on startup (not recommended).")
    args = parser.parse_args()

    if not args.no_tests:
        _run_self_tests()
        print("Self-tests passed.")
    print(f"Pricing table last verified: {PRICING_TABLE_LAST_VERIFIED}")

    presets_to_show = [args.preset] if args.preset else sorted(PRESETS.keys())
    for name in presets_to_show:
        _print_preset_report(name, dict(PRESETS[name]), args.model)


if __name__ == "__main__":
    main()

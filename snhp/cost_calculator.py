"""
Testable cost calculator for SNHP benchmark runs.

Pricing sources (verified 2026-04-29):
  - Gemini API:        ai.google.dev/gemini-api/docs/pricing
  - Anthropic API:     platform.claude.com/docs/en/docs/about-claude/pricing
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


PRICING_TABLE_LAST_VERIFIED = "2026-04-29"


@dataclass(frozen=True)
class ModelPricing:
    """
    USD per 1M tokens. Spelled out so the math is visible.

    `reasoning_token_multiplier` exists because some "preview"/"thinking" models
    (Gemini 3 Flash Preview, Claude Sonnet w/ extended thinking, GPT-5
    thinking, etc.) bill INTERNAL reasoning tokens at the output rate. These
    tokens never appear in the response text but are counted in
    `usage.completion_tokens` (Gemini) or `usage.cache_creation_input_tokens`
    + thinking-emit (Anthropic).

    For non-thinking models, this is 0.0 and effective_output = visible_output.
    For thinking models, an empirical multiplier on PROMPT size estimates how
    many invisible reasoning tokens get billed.

    Cache-write/read pricing (Anthropic) lets prompt-caching-aware callers
    estimate amortized cost. None for providers that don't expose caching.
    """
    name: str
    input_per_1m_usd: float
    output_per_1m_usd: float
    reasoning_token_multiplier: float = 0.0  # 0 = no thinking; >0 = thinking model
    cache_write_5m_per_1m_usd: Optional[float] = None  # Anthropic: 1.25x input
    cache_write_1h_per_1m_usd: Optional[float] = None  # Anthropic: 2x input
    cache_read_per_1m_usd: Optional[float] = None      # Anthropic: 0.1x input
    batch_discount: float = 0.0  # 0.0 = full price, 0.5 = 50% off (Anthropic Batch API)


# ─── Pricing table — keep in sync with provider pricing pages ────────────────
# Verified at ai.google.dev/gemini-api/docs/pricing on 2026-04-28.

PRICING: dict[str, ModelPricing] = {
    # Google Gemini — paid tier rates (verified ai.google.dev/gemini-api/docs/pricing 2026-04-29).
    # NOTE on "thinking" pricing: as of the 3.x line, thinking tokens are
    # billed at the OUTPUT rate but counted via `usage.thoughts_token_count`
    # (not via a separate per-1M rate). Empirical measurement (calibration
    # 2026-04-29 against the leaderboard prompt) shows gemini-3-flash-preview
    # at thinking=auto emits ~881 thoughts tokens vs 293 input — ~3x prompt
    # size. Lite variants don't expose a thinking config, so the multiplier
    # is 0 for them regardless of how they're called.
    "gemini-3-flash-preview":      ModelPricing("gemini-3-flash-preview",      0.50, 3.00, reasoning_token_multiplier=3.0),
    "gemini-3-pro-preview":        ModelPricing("gemini-3-pro-preview",        2.00, 12.00, reasoning_token_multiplier=3.0),
    "gemini-3.1-flash-lite-preview": ModelPricing("gemini-3.1-flash-lite-preview", 0.25, 1.50, reasoning_token_multiplier=0.0),
    "gemini-2.5-flash":            ModelPricing("gemini-2.5-flash",            0.30, 2.50, reasoning_token_multiplier=0.0),
    "gemini-2.5-flash-lite":       ModelPricing("gemini-2.5-flash-lite",       0.10, 0.40, reasoning_token_multiplier=0.0),
    # Anthropic Claude — verified platform.claude.com/docs/en/docs/about-claude/pricing 2026-04-29.
    # Opus 4.7 dropped to $5/$25 from the older $15/$75 (verify against the
    # docs page each release). Cache pricing follows the documented multipliers
    # (1.25x / 2x / 0.1x of base input). reasoning_token_multiplier is 0 by
    # default — extended thinking adds output tokens but is opt-in per call,
    # not a default behavior, so the table stays vanilla.
    "claude-opus-4-7":   ModelPricing("claude-opus-4-7",    5.00, 25.00, 0.0,
                                       cache_write_5m_per_1m_usd=6.25,
                                       cache_write_1h_per_1m_usd=10.00,
                                       cache_read_per_1m_usd=0.50,
                                       batch_discount=0.5),
    "claude-sonnet-4-6": ModelPricing("claude-sonnet-4-6",  3.00, 15.00, 0.0,
                                       cache_write_5m_per_1m_usd=3.75,
                                       cache_write_1h_per_1m_usd=6.00,
                                       cache_read_per_1m_usd=0.30,
                                       batch_discount=0.5),
    "claude-haiku-4-5":  ModelPricing("claude-haiku-4-5",   1.00,  5.00, 0.0,
                                       cache_write_5m_per_1m_usd=1.25,
                                       cache_write_1h_per_1m_usd=2.00,
                                       cache_read_per_1m_usd=0.10,
                                       batch_discount=0.5),
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


# Empirical token counts from leaderboard/agents/gemini_negmas.py prompt
# (calibration 2026-04-29 against gemini-3.1-flash-lite-preview): mid-game
# negotiation state with 6 rounds of history → 293 input, 12 output. Plain-
# text JSON ask (no response_mime_type to avoid structured-output overhead).
LEADERBOARD_PROMPT_SHAPE = PromptShape(
    description="leaderboard.agents.gemini_negmas (calibrated 2026-04-29)",
    avg_input_tokens=293,
    avg_output_tokens=12,
)


# ─── Core math (testable, no I/O) ────────────────────────────────────────────


def per_call_cost(model: str, input_tokens: int, output_tokens: int,
                  include_reasoning: bool = True,
                  *,
                  cache_creation_5m_tokens: int = 0,
                  cache_creation_1h_tokens: int = 0,
                  cache_read_tokens: int = 0,
                  thinking_tokens: int = 0,
                  batch: bool = False) -> float:
    """
    USD cost of a single LLM call. Pure function — fully testable.

    For thinking models, `include_reasoning=True` adds invisible reasoning
    tokens at the output rate, scaled by `reasoning_token_multiplier × input_tokens`.
    Set False to compute the cost of *visible* tokens only (rare; useful for
    debugging gap between visible and billed cost).

    Anthropic-specific args (no-op for providers without these mechanisms):
      cache_creation_{5m,1h}_tokens — tokens billed at the cache-write rate
        on first store (1.25x or 2x base input).
      cache_read_tokens — tokens billed at 0.1x base input on cache hit.
        These are NOT also counted in `input_tokens` (Anthropic returns
        them under separate usage fields: cache_creation_input_tokens /
        cache_read_input_tokens).
      thinking_tokens — extended thinking output tokens (Sonnet/Opus when
        the caller opts in via `thinking={...}`). Billed at the output rate.
        For models with reasoning_token_multiplier > 0 this is in ADDITION
        to the multiplier-derived estimate; pass real measured thoughts
        when you have them.
      batch — if True, apply Anthropic Batch API 50% discount on input,
        output, cache writes, and cache reads.
    """
    if model not in PRICING:
        raise KeyError(f"Unknown model {model!r}; known: {sorted(PRICING)}")
    p = PRICING[model]
    discount = (1.0 - p.batch_discount) if (batch and p.batch_discount > 0) else 1.0

    effective_output = output_tokens + thinking_tokens
    if include_reasoning and p.reasoning_token_multiplier > 0:
        effective_output += int(p.reasoning_token_multiplier * input_tokens)

    cost = 0.0
    cost += (input_tokens / 1_000_000) * p.input_per_1m_usd * discount
    cost += (effective_output / 1_000_000) * p.output_per_1m_usd * discount

    # Cache pricing (Anthropic only; raises if caller passes these for a
    # model that doesn't support caching).
    if cache_creation_5m_tokens or cache_creation_1h_tokens or cache_read_tokens:
        if p.cache_write_5m_per_1m_usd is None:
            raise ValueError(
                f"Model {model!r} doesn't expose prompt caching pricing — "
                f"caller passed cache token counts but the model has no "
                f"cache_write/read rates configured."
            )
        cost += (cache_creation_5m_tokens / 1_000_000) * p.cache_write_5m_per_1m_usd * discount
        cost += (cache_creation_1h_tokens / 1_000_000) * p.cache_write_1h_per_1m_usd * discount
        cost += (cache_read_tokens / 1_000_000) * p.cache_read_per_1m_usd * discount

    return cost


def estimate_run_cost(
    *,
    n_scenarios: int,
    n_opponents: int,
    n_llm_competitors: int,
    avg_calls_per_trial: float,
    avg_input_tokens: int,
    avg_output_tokens: int,
    model: str,
    reasoning_off: bool = False,
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
    # Account for invisible reasoning tokens billed at the output rate.
    # `reasoning_off=True` bypasses the multiplier — for thinking models
    # invoked with thinking_budget=0 (e.g. Gemini 3 Flash Preview when called
    # via genai.types.HttpOptions thinking_config disabled).
    effective_multiplier = 0.0 if reasoning_off else p.reasoning_token_multiplier
    reasoning_tokens_per_call = int(effective_multiplier * avg_input_tokens)
    total_reasoning_tokens = int(total_calls * reasoning_tokens_per_call)
    total_billable_output_tokens = total_visible_output_tokens + total_reasoning_tokens

    input_cost = (total_input_tokens / 1_000_000) * p.input_per_1m_usd
    output_cost = (total_billable_output_tokens / 1_000_000) * p.output_per_1m_usd
    total_cost = input_cost + output_cost

    return {
        "model": model,
        "input_per_1m_usd": p.input_per_1m_usd,
        "output_per_1m_usd": p.output_per_1m_usd,
        "reasoning_token_multiplier": effective_multiplier,
        "reasoning_off": reasoning_off,
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
    #    Gemini 3 Flash Preview: $0.50/$3.00, multiplier=3.0 → reasoning = 3000
    gemini_per_call = per_call_cost("gemini-3-flash-preview", 1000, 100)
    gemini_expected = (1000 / 1_000_000) * 0.50 + ((100 + 3000) / 1_000_000) * 3.00
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
    assert r["total_reasoning_tokens"] == 3000  # 3.0x multiplier (calibrated 2026-04-29)
    assert r["total_billable_output_tokens"] == 3100
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

    # 5. Order-of-magnitude check on the proposed N=100 × 4 opp config.
    #    With multiplier=3.0, expect 4000 calls × ~$0.0084 ≈ $33.
    r = estimate_run_cost(
        n_scenarios=100, n_opponents=4, n_llm_competitors=2,
        avg_calls_per_trial=5,
        avg_input_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_input_tokens,
        avg_output_tokens=SNHP_BENCHMARK_PROMPT_SHAPE.avg_output_tokens,
        model="gemini-3-flash-preview",
    )
    assert r["total_llm_calls"] == 4000, f"got {r['total_llm_calls']}"
    assert 20.0 < r["total_cost_usd"] < 50.0, \
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

    # 7. Anthropic cache pricing — cache reads at 0.1x base input rate.
    sonnet_cache_read = per_call_cost(
        "claude-sonnet-4-6", input_tokens=100, output_tokens=20,
        cache_read_tokens=1000,
    )
    sonnet_cache_read_expected = (
        (100 / 1_000_000) * 3.00          # uncached input
        + (20 / 1_000_000) * 15.00        # output
        + (1000 / 1_000_000) * 0.30       # cache read at 0.1x = $0.30/M
    )
    assert abs(sonnet_cache_read - sonnet_cache_read_expected) < 1e-9, \
        f"sonnet w/ cache read: got {sonnet_cache_read}, expected {sonnet_cache_read_expected}"

    # 8. Anthropic 5-min cache write at 1.25x base input rate.
    sonnet_cache_write = per_call_cost(
        "claude-sonnet-4-6", input_tokens=0, output_tokens=10,
        cache_creation_5m_tokens=1000,
    )
    sonnet_cache_write_expected = (
        (10 / 1_000_000) * 15.00           # output
        + (1000 / 1_000_000) * 3.75        # cache write 5m at 1.25x = $3.75/M
    )
    assert abs(sonnet_cache_write - sonnet_cache_write_expected) < 1e-9

    # 9. Batch API discount halves the cost.
    sonnet_batch = per_call_cost(
        "claude-sonnet-4-6", input_tokens=1000, output_tokens=100, batch=True,
    )
    sonnet_full = per_call_cost(
        "claude-sonnet-4-6", input_tokens=1000, output_tokens=100, batch=False,
    )
    assert abs(sonnet_batch - sonnet_full * 0.5) < 1e-9, \
        f"batch should halve cost: got {sonnet_batch}, expected {sonnet_full * 0.5}"

    # 10. Cache args on a model without caching support → ValueError
    try:
        per_call_cost("gemini-3-flash-preview", 100, 10, cache_read_tokens=500)
        raise AssertionError("should have rejected cache args on cacheless model")
    except ValueError:
        pass

    # 11. Extended thinking adds output tokens at the output rate.
    sonnet_thinking = per_call_cost(
        "claude-sonnet-4-6", input_tokens=1000, output_tokens=50,
        thinking_tokens=500,
    )
    sonnet_thinking_expected = (
        (1000 / 1_000_000) * 3.00
        + ((50 + 500) / 1_000_000) * 15.00  # both output and thinking at output rate
    )
    assert abs(sonnet_thinking - sonnet_thinking_expected) < 1e-9


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
    # Public leaderboard run: Gemini Flash plays N_ROUNDS=20 reps × ~10 steps
    # × 2 LLM calls per step (propose+respond) against 21 other agents in
    # 3 markets. Each Gemini matchup ≈ 400 calls; ~250 average since deals
    # often close before the deadline. Total: 21 opponents × 2 (Gemini-as-A
    # AND -as-B) × 3 markets × ~250 calls/matchup = ~31,500 LLM calls.
    "leaderboard_full": dict(
        description=("Public leaderboard with Gemini-3-Flash-Preview (reasoning OFF) "
                     "in the NegMAS tournament: 21 opponents × 2 directions "
                     "× 3 markets × N_ROUNDS=20 × ~6 calls/game avg."),
        n_scenarios=20 * 6,         # reps_per_matchup × calls_per_game_avg
        n_opponents=21,             # other agents in the roster
        n_llm_competitors=2 * 3,    # Gemini-as-A + Gemini-as-B × 3 markets
        avg_calls_per_trial=1,      # already folded into n_scenarios above
    ),
    "leaderboard_quick": dict(
        description=("Smaller bracket for cost-bounded runs: 1 market only "
                     "(symmetric), N_ROUNDS=10 instead of 20."),
        n_scenarios=10 * 6,
        n_opponents=21,
        n_llm_competitors=2,        # 1 market × 2 directions
        avg_calls_per_trial=1,
    ),
    # Single-market run: matches the actual leaderboard config when --multi-
    # market is NOT passed (default). 21 opponents × 2 directions × N_ROUNDS=20
    # × ~6 calls/game (calibrated 2026-04-29). 2 LLM bars (vanilla + scaffold).
    "leaderboard_symmetric": dict(
        description=("Symmetric-only bracket (single market, default). "
                     "21 opponents × 2 directions × N_ROUNDS=20 × ~6 calls/game. "
                     "Two LLM bars: vanilla + SNHP scaffolding."),
        n_scenarios=20 * 6,         # reps × calls/game
        n_opponents=21,
        n_llm_competitors=2 * 1,    # 1 market × 2 LLM bars
        avg_calls_per_trial=1,
    ),
}


def _format_dollars(d: float) -> str:
    if d < 0.01:
        return f"${d * 100:.2f}¢ ({d:.5f} USD)"
    return f"${d:.4f}"


def _print_preset_report(preset_name: str, preset: dict, model: str,
                          reasoning_off: bool = False) -> None:
    desc = preset.pop("description", "")
    # Leaderboard presets use the small (calibrated) gemini_negmas prompt;
    # benchmark presets use the bigger snhp/benchmark.py prompt.
    if preset_name.startswith("leaderboard"):
        shape = LEADERBOARD_PROMPT_SHAPE
    else:
        shape = SNHP_BENCHMARK_PROMPT_SHAPE
    r = estimate_run_cost(
        **preset,
        avg_input_tokens=shape.avg_input_tokens,
        avg_output_tokens=shape.avg_output_tokens,
        model=model,
        reasoning_off=reasoning_off,
    )
    preset["description"] = desc  # restore
    rmult = r['reasoning_token_multiplier']
    print(f"\n── Preset: {preset_name} ─────────────────────────────────")
    print(f"  {desc}")
    print(f"  Model:                {r['model']}")
    print(f"  Pricing (per 1M):     ${r['input_per_1m_usd']:.2f} input / ${r['output_per_1m_usd']:.2f} output")
    if reasoning_off:
        print(f"  Reasoning multiplier: 0.0x (reasoning OFF — thinking_budget=0)")
    else:
        print(f"  Reasoning multiplier: {rmult}x prompt size {'(THINKING MODEL — costs 2-3x visible)' if rmult > 0 else '(no thinking)'}")
    print(f"  Tokens per call:      {shape.avg_input_tokens} in / "
          f"{shape.avg_output_tokens} visible-out  ({shape.description})")
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
    parser.add_argument("--reasoning-off", action="store_true",
                        help="Treat the model as having thinking disabled "
                             "(thinking_budget=0). Zeros out the reasoning "
                             "token multiplier for pricing.")
    args = parser.parse_args()

    if not args.no_tests:
        _run_self_tests()
        print("Self-tests passed.")
    print(f"Pricing table last verified: {PRICING_TABLE_LAST_VERIFIED}")

    presets_to_show = [args.preset] if args.preset else sorted(PRESETS.keys())
    for name in presets_to_show:
        _print_preset_report(name, dict(PRESETS[name]), args.model,
                              reasoning_off=args.reasoning_off)


if __name__ == "__main__":
    main()

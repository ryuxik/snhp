"""Real API price table + cost derivation (SPEC v33-F: F, the agent payroll meter
— "per-agent/per-idea cost attribution ... that reconciles to my bill").

This module is the ANCHOR of the F product and of the D1b token meter: the ONE
price table used both to charge the live meter (meter.py) and to recompute cost
from stored SDK usage records at reconciliation time (the B1 buyer's acceptance
test). Because both paths derive cost from the SAME token counts through the
SAME constants, reconciliation is consistent by construction; the 5% tolerance
covers only rounding.

Honesty note (registered): in-sim employees are Sonnet/Haiku ONLY (Opus never
in-sim — constitutional + standing policy). Prices are the real published
Anthropic rates in effect on the run date (2026-07-17). Claude Sonnet 5 carries
an INTRODUCTORY rate ($2/$10 per MTok) active through 2026-08-31 — that is the
rate the founder's real bill is charged at today, so the meter uses it; the
standard rate ($3/$15) is recorded for post-window runs. Cache reads bill at
~0.1x input and 5-minute cache writes at ~1.25x input (build-with-claude pricing).

No SDK import here on purpose: F "ingests ONLY structured usage records (the
harness's own JSONL), never scraped text — a parser that can invent a plausible
number builds a liar, not a ledger" (v33-F, Musk's redesign).
"""

from __future__ import annotations

# Per-MILLION-token USD rates (input, output). Real published rates, run date
# 2026-07-17. Keyed by the exact model IDs the episodes register.
PRICES_PER_MTOK = {
    # Claude Sonnet 5 — introductory pricing (active through 2026-08-31, i.e.
    # the rate billed on the run date). Standard is $3/$15 after the window.
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "standard": (3.00, 15.00)},
    # Claude Haiku 4.5 (dated full ID, the hirable low-cost tier).
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    # Alias parity (some SDK responses echo the alias form).
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}

# Cache multipliers relative to the input rate (build-with-claude prompt caching).
_CACHE_READ_MULT = 0.10
_CACHE_WRITE_MULT = 1.25  # 5-minute TTL


def is_in_sim_allowed(model: str) -> bool:
    """Constitutional guard: only Sonnet/Haiku tiers may be in-sim employees;
    Opus is NEVER in-sim (v33 substrate + standing policy). Any 'opus' model is
    refused at registration."""
    return "opus" not in model.lower() and model in PRICES_PER_MTOK


def cost_from_usage(model: str, usage: dict) -> float:
    """Derive USD cost from an SDK usage record. `usage` carries the four token
    counts the Anthropic SDK returns: input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens. Uncached input bills at
    the input rate; cache writes at 1.25x input; cache reads at 0.1x input;
    output at the output rate. Unknown model -> ValueError (never guess a price —
    a made-up number is the exact F failure mode)."""
    if model not in PRICES_PER_MTOK:
        raise ValueError(f"no registered price for model {model!r} "
                         "(F ingests only known, priced usage — never guesses)")
    p = PRICES_PER_MTOK[model]
    inp = float(usage.get("input_tokens", 0) or 0)
    out = float(usage.get("output_tokens", 0) or 0)
    cw = float(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = float(usage.get("cache_read_input_tokens", 0) or 0)
    in_rate = p["input"] / 1_000_000.0
    out_rate = p["output"] / 1_000_000.0
    cost = (inp * in_rate + out * out_rate
            + cw * in_rate * _CACHE_WRITE_MULT
            + cr * in_rate * _CACHE_READ_MULT)
    return round(cost, 10)


def wage_note(model: str) -> str:
    """Human-readable per-token wage for a candidate (v33-I: 'wage = the real API
    price ... known upfront')."""
    p = PRICES_PER_MTOK.get(model)
    if not p:
        return f"{model}: unknown wage"
    return f"{model}: ${p['input']:.2f}/${p['output']:.2f} per Mtok (in/out)"

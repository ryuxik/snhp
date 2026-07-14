"""
LLM call auditor. Captures GROUND TRUTH about what's being sent to Gemini and
what the API reports back, so we can diagnose the cost gap.

Two layers of patching:

  1. snhp.llm_extractor._call_gemini_native — the native Gemini path. We grab
     `response.usage_metadata.prompt_token_count` and `candidates_token_count`
     directly from the API response. This is what Google bills against.

  2. litellm.completion — the fallback path. We capture `response.usage`
     (prompt_tokens, completion_tokens) and any litellm-level retry behavior
     by inspecting `response._hidden_params`.

Usage:
    python -m snhp.llm_audit                # run a 1-trial benchmark and report
    python -m snhp.llm_audit --calls 3      # run N standalone audit calls
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_THIS_DIR))

_ENV_PATH = os.path.join(os.path.dirname(_THIS_DIR), ".env")
_ENV_LOADED_VIA = "none"
try:
    from dotenv import load_dotenv
    if load_dotenv(_ENV_PATH):
        _ENV_LOADED_VIA = "dotenv"
except ImportError:
    pass

# Belt-and-suspenders: even if dotenv didn't fire (or python-dotenv isn't
# installed in this venv), parse the .env file ourselves and inject vars.
# This MUST run before any module that snapshots os.environ at import time
# (notably snhp.llm_extractor, which sets _genai_client based on GOOGLE_API_KEY
# at import).
if not os.environ.get("GOOGLE_API_KEY") and os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)
    if os.environ.get("GOOGLE_API_KEY"):
        _ENV_LOADED_VIA = "manual"

print(f"[audit] GOOGLE_API_KEY in env: {bool(os.environ.get('GOOGLE_API_KEY'))} "
      f"(loaded via {_ENV_LOADED_VIA})", file=sys.stderr)


@dataclass
class CallAuditEntry:
    path: str  # "native" or "litellm"
    prompt_chars: int
    schema_chars: int
    response_chars: int
    api_prompt_tokens: Optional[int]
    api_completion_tokens: Optional[int]
    api_total_tokens: Optional[int]
    elapsed_s: float
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


_CALL_LOG: list[CallAuditEntry] = []


def install_audit_patches() -> None:
    """
    Replace `llm_extractor._call_llm` with an instrumented version. This is the
    single entry point ALL benchmark code calls, so wrapping here captures
    every logical LLM call regardless of which sub-path (native vs litellm) is
    used.

    We reimplement the routing inline (rather than wrapping the original) so we
    can capture `usage_metadata` from the SAME response (no duplicate probe
    calls). For the litellm path we ALSO wrap `_call_litellm` to capture
    `response.usage` since the from-import baked in the reference.
    """
    from snhp import llm_extractor

    if getattr(llm_extractor, "_audit_patched", False):
        print("[audit] patches already installed, skipping", file=sys.stderr)
        return

    print(f"[audit] installing patches; _genai_client is {'set' if llm_extractor._genai_client else 'None'}",
          file=sys.stderr)

    def _audited_call_llm(prompt: str, schema=None, temperature: float = 0.0):
        model_name = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
        model_id_clean = model_name.replace("gemini/", "")

        # Build the augmented prompt (mirrors what _call_gemini_native does) so
        # our prompt_chars reflect the real wire payload.
        full_prompt = prompt
        schema_dump_str = ""
        if schema:
            schema_dump_str = (
                json.dumps(schema.model_json_schema())
                if hasattr(schema, "model_json_schema")
                else str(schema)
            )
            full_prompt = prompt + (
                "\n\nYou MUST return ONLY a raw JSON object (without markdown "
                f"wrappers) matching this schema structure:\n{schema_dump_str}"
            )

        api_p = api_c = api_t = None
        result = None
        err = None
        path = "unknown"
        t0 = time.time()

        # Replicate the routing logic from llm_extractor._call_llm but capture
        # usage_metadata directly from the response.
        if "gemini" in model_name.lower() and llm_extractor._genai_client is not None:
            path = "native"
            print(f"[audit] CALL via native; prompt_chars={len(full_prompt)}",
                  file=sys.stderr)
            try:
                config = {"temperature": temperature}
                if schema:
                    config["response_mime_type"] = "application/json"
                response = llm_extractor._genai_client.models.generate_content(
                    model=model_id_clean,
                    contents=full_prompt,
                    config=config,
                )
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    um = response.usage_metadata
                    api_p = getattr(um, "prompt_token_count", None)
                    api_c = getattr(um, "candidates_token_count", None)
                    api_t = getattr(um, "total_token_count", None)
                content = response.text
                if schema:
                    content = content.replace("```json", "").replace("```", "").strip()
                    result = json.loads(content) if content else {}
                else:
                    result = content.strip() if content else ""
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
        else:
            # Litellm path
            path = "litellm"
            print(f"[audit] CALL via litellm; prompt_chars={len(full_prompt)}",
                  file=sys.stderr)
            try:
                from litellm import completion
                import litellm as _lit
                _lit.suppress_debug_info = True
                kwargs = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": temperature,
                }
                if schema:
                    kwargs["response_format"] = {"type": "json_object"}
                response = completion(**kwargs)
                content = response.choices[0].message.content
                if schema:
                    content = content.replace("```json", "").replace("```", "").strip()
                    result = json.loads(content) if content else {}
                else:
                    result = content.strip() if content else ""
                if hasattr(response, "usage") and response.usage:
                    api_p = response.usage.prompt_tokens
                    api_c = response.usage.completion_tokens
                    api_t = response.usage.total_tokens
            except Exception as e:
                err = f"{type(e).__name__}: {e}"

        elapsed = time.time() - t0

        entry = CallAuditEntry(
            path=path,
            prompt_chars=len(full_prompt),
            schema_chars=len(schema_dump_str),
            response_chars=len(str(result)) if result is not None else 0,
            api_prompt_tokens=api_p,
            api_completion_tokens=api_c,
            api_total_tokens=api_t,
            elapsed_s=elapsed,
            error=err,
        )
        _CALL_LOG.append(entry)
        if err is not None:
            raise RuntimeError(err)
        return result

    llm_extractor._call_llm = _audited_call_llm
    llm_extractor._audit_patched = True


def _print_summary() -> None:
    if not _CALL_LOG:
        print("(no calls recorded)")
        return
    print("\n" + "=" * 78)
    print(f"AUDIT SUMMARY — {len(_CALL_LOG)} call(s) captured")
    print("=" * 78)
    for i, e in enumerate(_CALL_LOG, 1):
        print(f"\nCall {i} — path={e.path}")
        print(f"  prompt chars (post-schema-dump): {e.prompt_chars:>8}")
        print(f"  schema dump chars:               {e.schema_chars:>8}")
        print(f"  response chars:                  {e.response_chars:>8}")
        if e.api_prompt_tokens is not None:
            print(f"  API-reported prompt tokens:      {e.api_prompt_tokens:>8}")
            print(f"  API-reported completion tokens:  {e.api_completion_tokens:>8}")
            print(f"  API-reported total tokens:       {e.api_total_tokens:>8}")
            est_chars_per_token = e.prompt_chars / e.api_prompt_tokens if e.api_prompt_tokens else None
            if est_chars_per_token is not None:
                print(f"  → derived chars/token:           {est_chars_per_token:.2f}")
        else:
            print(f"  API usage_metadata:              UNAVAILABLE")
        print(f"  elapsed:                         {e.elapsed_s:.2f}s")
        if e.extra:
            print(f"  extra:                           {e.extra}")
        if e.error:
            print(f"  error:                           {e.error}")

    # ── Aggregate and project ───────────────────────────────────────────────
    valid = [e for e in _CALL_LOG if e.api_prompt_tokens is not None]
    if not valid:
        print("\n(no API usage metadata captured — can't project costs)")
        return

    avg_in = sum(e.api_prompt_tokens for e in valid) / len(valid)
    avg_out = sum(e.api_completion_tokens for e in valid) / len(valid)
    print(f"\nAverages over {len(valid)} successful call(s):")
    print(f"  avg prompt tokens (API truth):     {avg_in:>8.0f}")
    print(f"  avg completion tokens (API truth): {avg_out:>8.0f}")

    print(f"\nReprice with REAL Gemini 3 Flash Preview rates ($0.50 in / $3.00 out):")
    real_per_call = (avg_in / 1_000_000) * 0.50 + (avg_out / 1_000_000) * 3.00
    print(f"  per-call cost:                     ${real_per_call:.6f}")

    print(f"\nReprice with old (wrong) rates ($0.30 in / $2.50 out):")
    old_per_call = (avg_in / 1_000_000) * 0.30 + (avg_out / 1_000_000) * 2.50
    print(f"  per-call cost:                     ${old_per_call:.6f}")

    print(f"\nGap between current calculator (~$0.000455 per call) and reality:")
    print(f"  ratio: {real_per_call / 0.000455:.1f}× more expensive than predicted")


# ─── Main ────────────────────────────────────────────────────────────────────


def _audit_one_real_benchmark_trial():
    """Run one real benchmark trial through the patched LLM path. This makes
    real API calls — but only enough for one negotiation (~5-10 calls)."""
    install_audit_patches()
    from snhp.benchmark import (
        play_one_trial, generate_scenarios, LLMWithSNHP,
    )
    from snhp.b2b_opponents import Anchorer

    sc = generate_scenarios(n=1, seed=42)[0]
    print(f"Running 1 LLM_with_SNHP trial vs Anchorer on scenario {sc.scenario_id}...")
    print("(This makes real Gemini API calls; ~5-10 calls expected.)\n")
    trial = play_one_trial("LLM_with_SNHP", LLMWithSNHP, sc,
                           fixed_opponent_cls=Anchorer, opponent_name="Anchorer")
    print(f"\nTrial outcome: walked={trial.walked_away}, "
          f"util={trial.seller_utility:.3f}, rounds={trial.rounds_used}, "
          f"competitor_llm_calls={trial.competitor_llm_calls}")


def _audit_n_standalone_calls(n: int):
    """Make N standalone calls of varying sizes to characterize cost shape."""
    install_audit_patches()
    from snhp.llm_extractor import _call_llm
    from pydantic import BaseModel, Field

    class _Outcome(BaseModel):
        price: int = Field(ge=0, le=49)
        delivery: int = Field(ge=0, le=4)
        warranty: int = Field(ge=0, le=3)
        payment: int = Field(ge=0, le=2)
        accept_opponent_offer: bool = False

    fillers = [
        # Tiny — sanity baseline
        ("tiny", "Reply with the integer 7.", None),
        # Realistic-size — synthetic copy of a benchmark prompt
        (
            "realistic",
            "You are negotiating a B2B contract.\n" * 60 +
            "Decide values for price (0-49), delivery (0-4), warranty (0-3), payment (0-2).",
            _Outcome,
        ),
        # Larger — the SNHP-with-history shape (longer prompt + schema)
        (
            "with_history",
            ("You are negotiating a B2B contract.\n" * 60 +
             "ROUND 1: opp offered (5,4,3,2), you proposed (49,2,1,0).\n" * 5 +
             "Decide values for price (0-49), delivery (0-4), warranty (0-3), payment (0-2)."),
            _Outcome,
        ),
    ][:n]

    for label, prompt, schema in fillers:
        print(f"\n--- {label} ---")
        try:
            r = _call_llm(prompt, schema, temperature=0.3)
            print(f"  result: {r!r}")
        except Exception as e:
            print(f"  failed: {type(e).__name__}: {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--mode", choices=["benchmark-trial", "standalone"], default="benchmark-trial",
        help="benchmark-trial: run 1 real LLM_with_SNHP trial through the patched path. "
             "standalone: just make a few sized calls without the negotiation loop.",
    )
    parser.add_argument(
        "--calls", type=int, default=3,
        help="For --mode=standalone: number of test calls (1-3).",
    )
    args = parser.parse_args()

    if args.mode == "benchmark-trial":
        _audit_one_real_benchmark_trial()
    else:
        _audit_n_standalone_calls(min(args.calls, 3))

    _print_summary()


if __name__ == "__main__":
    main()

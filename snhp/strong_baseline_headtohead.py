"""
Strong-baseline head-to-head — the build-vs-buy honesty test.

The +12% headline measures SNHP-scaffolded LLM vs a *general* vanilla prompt. The
sharper question (raised by every build-vs-buy reviewer): does SNHP still win against
a STRONG, production-quality prompt? `snhp/llm_strong_baseline.py` is exactly that
opponent and was never run to publication. This script runs it.

Paired design, controlling for model AND role: for each seed we run SNHP-as-seller
vs StrongBaseline-as-buyer AND the swap, on identical conditions (same seed ->
same BATNA/steps). Both sides use the SAME model (SNHP_LLM_MODEL), so the only
difference is the SCAFFOLD: the SNHP tool vs a best-effort production prompt.

    SNHP_LLM_MODEL=claude-sonnet-4-6 python -m snhp.strong_baseline_headtohead 20
    python -m snhp.strong_baseline_headtohead 5          # quick pilot (default model)

Writes gametheory/server/static/strong_baseline_headtohead.json.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # bare-import deps
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

import numpy as np


def _mean_ci(vals, n_boot=5000, seed=12345):
    rng = np.random.RandomState(seed)
    a = np.asarray(vals, dtype=float)
    boots = np.array([rng.choice(a, size=len(a), replace=True).mean() for _ in range(n_boot)])
    return float(a.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def run(n_seeds: int, base_seed: int = 4200):
    load_dotenv(os.path.join(_ROOT, ".env"))
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("SKIP: ANTHROPIC_API_KEY not set"); return None
    model = os.environ.setdefault("SNHP_LLM_MODEL", "claude-haiku-4-5")

    import statistical_benchmark as sb
    from llm_with_snhp import LLMWithSNHP
    from llm_strong_baseline import LLMStrongBaseline

    issues = sb.create_issues()
    seeds = [base_seed + i for i in range(n_seeds)]
    rows, margins, snhp_shares = [], [], []
    t0 = time.time()
    print("=" * 72)
    print(f"  STRONG-BASELINE HEAD-TO-HEAD  (model={model}, {n_seeds} paired seeds)")
    print("  SNHP-scaffolded LLM  vs  LLMStrongBaseline (production prompt)")
    print("=" * 72)
    for s in seeds:
        ab = sb.play_matchup(LLMWithSNHP, LLMStrongBaseline, issues, n_rounds=1, seed=s)
        ba = sb.play_matchup(LLMStrongBaseline, LLMWithSNHP, issues, n_rounds=1, seed=s)
        snhp_u = float(np.mean([ab.raw_utils_a[0], ba.raw_utils_b[0]]))
        base_u = float(np.mean([ab.raw_utils_b[0], ba.raw_utils_a[0]]))
        margin = snhp_u - base_u
        share = snhp_u / (snhp_u + base_u) if (snhp_u + base_u) > 0 else 0.5
        rows.append({"seed": s, "snhp_util": snhp_u, "base_util": base_u,
                     "margin": margin, "snhp_share": share,
                     "deals": [bool(ab.deals[0]), bool(ba.deals[0])]})
        margins.append(margin); snhp_shares.append(share)
        print(f"  seed {s}: SNHP {snhp_u:.3f}  base {base_u:.3f}  margin {margin:+.3f}  share {share:.3f}")

    m_mean, m_lo, m_hi = _mean_ci(margins)
    sh_mean, sh_lo, sh_hi = _mean_ci(snhp_shares)
    pos = sum(1 for m in margins if m > 0)
    verdict = ("SNHP beats the strong baseline" if m_lo > 0 else
               "SNHP loses to the strong baseline" if m_hi < 0 else
               "inconclusive at this n (CI spans 0)")
    out = {
        "experiment": "strong_baseline_headtohead",
        "model": model, "n_seeds": n_seeds, "seeds": seeds,
        "margin_mean": m_mean, "margin_ci95": [m_lo, m_hi],
        "snhp_share_mean": sh_mean, "snhp_share_ci95": [sh_lo, sh_hi],
        "positive_signs": f"{pos}/{n_seeds}",
        "verdict": verdict, "rows": rows,
        "wall_seconds": round(time.time() - t0, 1),
    }
    dest = os.path.join(_ROOT, "gametheory", "server", "static", "strong_baseline_headtohead.json")
    with open(dest, "w") as f:
        json.dump(out, f, indent=2)
    print("-" * 72)
    print(f"  utility margin (SNHP - strong baseline): {m_mean:+.3f}  CI95 [{m_lo:+.3f}, {m_hi:+.3f}]")
    print(f"  SNHP share of joint surplus:             {sh_mean:.3f}  CI95 [{sh_lo:.3f}, {sh_hi:.3f}]")
    print(f"  positive seeds: {pos}/{n_seeds}   ->  {verdict}")
    print(f"  wrote {dest}")
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run(n)

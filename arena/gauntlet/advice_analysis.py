"""arena/gauntlet/advice_analysis.py — the Amendment 3 verdict, computed
MECHANICALLY from the paired solo/advised arms.

Question: does the SNHP engine ADVISOR help a frontier model, and — the claim
that actually matters — does it protect the DOWNSIDE?

Everything decision-relevant is frozen by PREREG-pool.md Amendment 3 and
asserted here. Three registered statistics, per model per scenario set, paired
by (scenario_id, role, counterparty) between arms:

  MEAN        mean own-utility, advised - solo. Sign-flip permutation.
  DOWNSIDE-1  breach rate P(own-utility <= BATNA): the share of matches ending
              at or below walk-away. Paired 0/1 difference, sign-flip
              permutation. IMPROVEMENT = this goes DOWN.
  DOWNSIDE-2  CVaR@10: mean own-utility over the worst 10% of matches WITHIN
              each arm, advised - solo, paired bootstrap CI over pairing keys.
              IMPROVEMENT = this goes UP.

The tail in DOWNSIDE-2 is defined inside each arm and never by selecting on the
other arm's outcome — conditioning the tail on solo's result would manufacture
regression to the mean, which is exactly the error this program avoids.

`followed_advice` is reported as context and feeds no verdict.

Reads the paid artifact only (arena/web/llm-advice-arms.json); calls no LLM.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from arena.gauntlet.agents import BATNA
from arena.gauntlet.certify import paired_permutation_pvalue
from arena.gauntlet.llm_tier import (
    A3_PREDICTION, ARMS_A3, CACHE_A3, SETS, TIER_MODELS,
)
from arena.gauntlet.pool_experiment import ALPHA, N_SCENARIOS, require_prereg

_OUT = pathlib.Path(__file__).with_name("certs") / "ADVICE-RESULTS.md"
_EXPECTED = N_SCENARIOS * 2 * 3          # 360 matches per model/set/arm
CVAR_Q = 0.10                            # worst 10% (registered)
N_BOOT = 10_000                          # registered bootstrap resamples
_EPS = 1e-9


def _key(m: dict) -> tuple:
    return (m["scenario_id"], m["role"], m["counterparty"])


def _paired(matches: list, model: str, set_label: str):
    """Return (keys, u_solo, u_advised) aligned on the identical pairing keys.
    Refuses a partial pairing — both arms must cover the same key set."""
    arms = {a: {_key(m): m for m in matches
                if m.get("candidate") == model
                and m.get("set_label") == set_label
                and m.get("arm") == a}
            for a in ARMS_A3}
    ks, ka = set(arms["solo"]), set(arms["advised"])
    if not ks or ks != ka:
        return None
    keys = sorted(ks)
    u_s = np.array([arms["solo"][k]["u_candidate"] for k in keys], float)
    u_a = np.array([arms["advised"][k]["u_candidate"] for k in keys], float)
    return keys, u_s, u_a, arms


def _cvar(u: np.ndarray, q: float = CVAR_Q) -> float:
    """Mean over the worst q-fraction of the arm's own outcomes."""
    n = max(1, int(round(q * len(u))))
    return float(np.sort(u)[:n].mean())


def _cvar_boot_ci(u_s: np.ndarray, u_a: np.ndarray, seed: int,
                  n_boot: int = N_BOOT):
    """Paired bootstrap over pairing keys: resample keys with replacement, and
    recompute BOTH arms' CVaR on the same resampled keys each time."""
    rng = np.random.default_rng(seed)
    n = len(u_s)
    diffs = np.empty(n_boot, float)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[b] = _cvar(u_a[idx]) - _cvar(u_s[idx])
    lo, hi = np.percentile(diffs, [100 * ALPHA / 2, 100 * (1 - ALPHA / 2)])
    return float(lo), float(hi)


def analyse(cache_path: pathlib.Path = CACHE_A3) -> dict:
    require_prereg()
    cache = json.loads(cache_path.read_text())
    matches = cache["matches"]
    out: dict = {"incomplete": cache.get("incomplete"), "cells": {}}
    for model in TIER_MODELS:
        for set_label, seed in SETS:
            got = _paired(matches, model, set_label)
            if got is None:
                out["cells"][(model, set_label)] = None
                continue
            keys, u_s, u_a, arms = got
            if len(keys) < _EXPECTED:
                out["cells"][(model, set_label)] = {"partial": len(keys)}
                continue

            # MEAN — paired, sign-flip permutation
            d_mean = u_a - u_s
            mean_p = paired_permutation_pvalue(d_mean, seed)

            # DOWNSIDE-1 — breach rate, paired 0/1 difference
            b_s = (u_s <= BATNA + _EPS).astype(float)
            b_a = (u_a <= BATNA + _EPS).astype(float)
            d_breach = b_a - b_s
            breach_p = paired_permutation_pvalue(d_breach, seed)

            # DOWNSIDE-2 — CVaR@10 within each arm + paired bootstrap CI
            cv_s, cv_a = _cvar(u_s), _cvar(u_a)
            lo, hi = _cvar_boot_ci(u_s, u_a, seed)

            followed = [m["followed_advice"] for m in arms["advised"].values()
                        if m.get("followed_advice") is not None]
            out["cells"][(model, set_label)] = {
                "n": len(keys),
                "mean_solo": float(u_s.mean()), "mean_advised": float(u_a.mean()),
                "mean_delta": float(d_mean.mean()), "mean_p": mean_p,
                "breach_solo": float(b_s.mean()), "breach_advised": float(b_a.mean()),
                "breach_delta": float(d_breach.mean()), "breach_p": breach_p,
                "cvar_solo": cv_s, "cvar_advised": cv_a,
                "cvar_delta": cv_a - cv_s, "cvar_lo": lo, "cvar_hi": hi,
                "followed": float(np.mean(followed)) if followed else None,
            }
    return out


def _verdict(cells: dict) -> str:
    """Mechanical read of the registered predictions. Downside IMPROVES iff
    breach falls (delta<0, p<alpha) or CVaR rises with a CI excluding 0."""
    done = {k: v for k, v in cells.items() if v and "partial" not in v}
    # Per-model: the registration states its predictions per model ("Haiku
    # advised-solo > 0 on both sets", "Sonnet's mean effect small"), so a model
    # with BOTH sets complete is evaluable even if the other model is not.
    evaluable = [m for m in TIER_MODELS
                 if all((m, s) in done for s, _ in SETS)]
    unevaluated = [m for m in TIER_MODELS if m not in evaluable]
    if not evaluable:
        return ("**Verdict: INCOMPLETE.** No model has both scenario sets "
                "complete; no verdict is computed from a partial collection.")
    lines = []
    for model in evaluable:
        c = [done[(model, s)] for s, _ in SETS]
        mean_up = all(x["mean_delta"] > 0 and x["mean_p"] < ALPHA for x in c)
        mean_dn = all(x["mean_delta"] < 0 and x["mean_p"] < ALPHA for x in c)
        breach_better = all(x["breach_delta"] < 0 and x["breach_p"] < ALPHA
                            for x in c)
        cvar_better = all(x["cvar_lo"] > 0 for x in c)
        mean_txt = ("helps (delta>0, p<{}) on both sets".format(ALPHA) if mean_up
                    else "HURTS (delta<0, p<{}) on both sets".format(ALPHA)
                    if mean_dn else "no separable mean effect on both sets")
        down_txt = []
        down_txt.append("breach rate falls" if breach_better
                        else "breach rate not improved")
        down_txt.append("CVaR@10 rises (CI excludes 0)" if cvar_better
                        else "CVaR@10 not improved")
        lines.append(f"- **{model}** — MEAN: {mean_txt}. DOWNSIDE: "
                     + "; ".join(down_txt) + ".")
    if unevaluated:
        lines.append(f"- **{', '.join(unevaluated)}** — NOT EVALUATED: both "
                     f"scenario sets were not collected (budget/limit), not "
                     f"dropped for being inconvenient.")
    any_down = any(
        all(done[(m, s)]["breach_delta"] < 0 and done[(m, s)]["breach_p"] < ALPHA
            for s, _ in SETS)
        or all(done[(m, s)]["cvar_lo"] > 0 for s, _ in SETS)
        for m in evaluable)
    scope = f" (evaluated: {', '.join(evaluable)})"
    head = ("**Downside verdict: the floor claim SURVIVES**" + scope +
            " — advice measurably improves a registered downside statistic."
            if any_down else
            "**Downside verdict: KILL**" + scope + ". Neither downside "
            "statistic improves on both sets. Per the registration this is a kill "
            "of the floor claim on this instrument — no re-cut, no new tail "
            "statistic chosen after the fact.")
    return head + "\n\n" + "\n".join(lines)


def build(cache_path: pathlib.Path = CACHE_A3) -> str:
    res = analyse(cache_path)
    cells = res["cells"]
    L = ["# Does the SNHP advisor help? — Amendment 3 results\n",
         "*Generated by `python -m arena.gauntlet.advice_analysis`. Paired "
         "solo-vs-advised arms on the frozen pool, matched inference config "
         "(thinking disabled in BOTH arms). Reported, never certified.*\n",
         f"**Registered prediction (stated before the run):** {A3_PREDICTION}\n"]
    if res.get("incomplete"):
        L.append("> ⚠ The cached run is marked **incomplete** — cells below "
                 "with fewer than the registered "
                 f"{_EXPECTED} pairs are shown as partial and are NOT a "
                 "measurement.\n")

    L.append("## MEAN — does advice raise own-utility?\n")
    L.append("| model | set | n pairs | solo | advised | delta | perm p | reading |")
    L.append("|---|---|---|---|---|---|---|---|")
    for model in TIER_MODELS:
        for set_label, _ in SETS:
            c = cells.get((model, set_label))
            if not c or "partial" in c:
                L.append(f"| {model} | {set_label} | "
                         f"{(c or {}).get('partial', 0)} | — | — | — | — | "
                         f"**partial — not a measurement** |")
                continue
            rd = ("advice helps" if c["mean_delta"] > 0 and c["mean_p"] < ALPHA
                  else "advice HURTS" if c["mean_delta"] < 0 and c["mean_p"] < ALPHA
                  else "no separable effect")
            L.append(f"| {model} | {set_label} | {c['n']} | {c['mean_solo']:.4f} | "
                     f"{c['mean_advised']:.4f} | {c['mean_delta']:+.4f} | "
                     f"{c['mean_p']:.4f} | {rd} |")
    L.append("")

    L.append("## DOWNSIDE-1 — breach rate P(own-utility <= BATNA). Lower is better.\n")
    L.append("| model | set | solo | advised | delta | perm p | reading |")
    L.append("|---|---|---|---|---|---|---|")
    for model in TIER_MODELS:
        for set_label, _ in SETS:
            c = cells.get((model, set_label))
            if not c or "partial" in c:
                continue
            rd = ("**floor holds** — breaches fall"
                  if c["breach_delta"] < 0 and c["breach_p"] < ALPHA
                  else "breaches RISE" if c["breach_delta"] > 0 and c["breach_p"] < ALPHA
                  else "no separable effect")
            L.append(f"| {model} | {set_label} | {c['breach_solo']:.3f} | "
                     f"{c['breach_advised']:.3f} | {c['breach_delta']:+.3f} | "
                     f"{c['breach_p']:.4f} | {rd} |")
    L.append("")

    L.append(f"## DOWNSIDE-2 — CVaR@{int(CVAR_Q*100)} (mean of each arm's worst "
             f"{int(CVAR_Q*100)}%). Higher is better; CI is a paired bootstrap "
             f"({N_BOOT:,} resamples), {int((1-ALPHA)*100)}%.\n")
    L.append("| model | set | solo | advised | delta | CI | reading |")
    L.append("|---|---|---|---|---|---|---|")
    for model in TIER_MODELS:
        for set_label, _ in SETS:
            c = cells.get((model, set_label))
            if not c or "partial" in c:
                continue
            rd = ("**tail improves**" if c["cvar_lo"] > 0
                  else "tail WORSENS" if c["cvar_hi"] < 0
                  else "CI spans 0 — no effect")
            L.append(f"| {model} | {set_label} | {c['cvar_solo']:.4f} | "
                     f"{c['cvar_advised']:.4f} | {c['cvar_delta']:+.4f} | "
                     f"[{c['cvar_lo']:+.4f}, {c['cvar_hi']:+.4f}] | {rd} |")
    L.append("")

    L.append("## Verdict (mechanical)\n")
    L.append(_verdict(cells) + "\n")
    L.append("Context only, no role in any verdict — fraction of advised turns "
             "on which the model adopted the recommendation:\n")
    for model in TIER_MODELS:
        for set_label, _ in SETS:
            c = cells.get((model, set_label))
            if c and "partial" not in c and c.get("followed") is not None:
                L.append(f"- {model} / {set_label}: {c['followed']:.2f}")
    L.append("")
    L.append("Regenerate: `python -m arena.gauntlet.llm_tier --amendment 3` "
             "(paid; checkpointed + resumable) then "
             "`python -m arena.gauntlet.advice_analysis` (read-only, no LLM).\n")
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m arena.gauntlet.advice_analysis",
                                description=__doc__)
    p.add_argument("--out", default=str(_OUT))
    args = p.parse_args(argv)
    if not CACHE_A3.exists():
        print(f"no Amendment 3 artifact at {CACHE_A3} — run "
              f"`python -m arena.gauntlet.llm_tier --amendment 3` first.")
        return 2
    md = build()
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

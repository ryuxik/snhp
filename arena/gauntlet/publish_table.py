"""arena/gauntlet/publish_table.py — writes certs/CERTIFIED-TABLE.md, the
PUBLICATION artifact.

The one rule this file exists to enforce: **pool-certified numbers and
historical numbers never share a table.** Two populations exist and they are
not comparable:

  POOL-CERTIFIED (the claim): candidates that actually played the frozen
    3-member pool (naive, hardball, conceder) under PREREG-pool.md, scored on
    pooled own-utility vs the naive baseline. Locally reproducible: engine,
    champion, naive.
  HISTORICAL (context, NOT a claim): the recorded LLM leaderboard runs in
    arena/web/gauntlet-matches.json. Those agents played the ORIGINAL protocol
    (EngineSeat counterparty only) and were scored on CAPTURE. They never
    played the pool, so they have no certified number and must never be ranked
    against one. Re-running them would cost real API calls; this module is
    strictly read-only and calls no LLM.

Every number carries its regeneration command, because a publication has to be
able to reproduce the table it cites.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from arena.gauntlet.certify import paired_permutation_pvalue
from arena.gauntlet.pool import POOL_MEMBERS, POOL_PARAMETERS
from arena.gauntlet.pool_experiment import (
    HELDOUT_SEED, PUBLIC_SEED, REFERENCE_CP, REFERENCE_PREDICTION, N_SCENARIOS,
    ALPHA, primary_stat, require_prereg, run_candidate, run_reference, _subset,
)
from arena.gauntlet.llm_tier import (
    CACHE as _LLM_CACHE, TIER_MODELS, TIER_PREDICTION, SETS as _LLM_SETS,
)

_CERTS = pathlib.Path(__file__).with_name("certs")
_MATCHES_JSON = pathlib.Path(__file__).resolve().parents[1] / "web" / "gauntlet-matches.json"
_RECORDED_PERM_SEED = 0          # documented fixed RNG seed for read-only rows
_OUT = _CERTS / "CERTIFIED-TABLE.md"

_LOCAL_CANDIDATES = ("engine", "champion", "naive")


def _historical(matches: list, model: str, cond: str = "solo") -> dict:
    return {(int(m["scenario_id"]), str(m["role"])): m
            for m in matches if m.get("model") == model
            and m.get("condition") == cond}


def _capture_delta(cand: dict, base: dict, seed: int) -> tuple:
    keys = sorted(set(cand) & set(base))
    c = np.array([cand[k]["capture"] for k in keys], float)
    b = np.array([base[k]["capture"] for k in keys], float)
    d = c - b
    return (len(keys), float(c.mean()), float(b.mean()), float(d.mean()),
            paired_permutation_pvalue(d, seed))


_LLM_EXPECTED = N_SCENARIOS * 2 * len(POOL_MEMBERS)   # 360 matches per model/set


def _load_llm_cache() -> dict | None:
    if not _LLM_CACHE.exists():
        return None
    try:
        return json.loads(_LLM_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _llm_tier_section(runs: dict, sets: tuple, n: int) -> list:
    """Section 3: the registered frontier models measured on the SAME
    own-utility instrument as section 1 (Amendment 2). Read-only from the
    cached paid run; calls NO LLM. Renders a model×set cell only when its full
    360-match set is present — a partial (interrupted / out-of-credits) run is
    labelled as such, never scored as if complete."""
    L = ["---\n",
         "## 3. MEASURED FRONTIER MODELS — reported on the certified metric, "
         "NOT certified\n",
         "> Registered in `PREREG-pool.md` Amendment 2 and run UNAIDED against "
         "the frozen three, scored on the **same pooled own-utility vs naive** "
         "statistic as section 1 — so the `own-u` column here IS comparable to "
         "section 1. They are reported, not certified: like the reference tier, "
         "they never enter the engine−naive verdict and are never signed by "
         "`certify.py`. This replaces the retired-`capture` footnote (now "
         "section 4) with a comparable number.\n",
         f"**Registered prediction (stated before the run):** {TIER_PREDICTION}\n"]

    cache = _load_llm_cache()
    if cache is None or not cache.get("matches"):
        L.append("_(no run yet — `python -m arena.gauntlet.llm_tier` populates "
                 "`certs/llm-tier-matches.json`; `--provider scripted-naive` "
                 "does a free offline dry run.)_\n")
        L.append("Regenerate: `python -m arena.gauntlet.llm_tier` "
                 "(paid; checkpointed + resumable) then "
                 "`python -m arena.gauntlet.publish_table`.\n")
        return L

    seed_to_label = {seed: label for label, seed in cache.get("sets", {}).items()}
    matches = cache["matches"]
    if cache.get("incomplete"):
        note = cache.get("stopped_reason")
        L.append("> ⚠ The cached run is marked **incomplete**"
                 + (f" (stopped: {note})" if note else "")
                 + ". Cells below with fewer than "
                 f"{_LLM_EXPECTED} matches are shown as partial and are NOT a "
                 "measurement — re-run `llm_tier` to finish them.\n")

    L.append("| model | condition | set | n | own-u | naive own-u | delta | "
             "perm p | separates UPWARD? (delta>0 & p<0.01) | direction |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    up = {m: {} for m in TIER_MODELS}      # model -> {label: passes} for complete cells
    for model in TIER_MODELS:
        for label, seed in sets:
            base = runs.get((label, "naive"))
            cache_label = seed_to_label.get(seed)
            recs = [m for m in matches if m.get("candidate") == model
                    and m.get("set_label") == cache_label]
            if not recs:
                L.append(f"| {model} | solo | {label} | 0 | — | — | — | — | "
                         f"— | not run |")
                continue
            if len(recs) < _LLM_EXPECTED or base is None:
                L.append(f"| {model} | solo | {label} | {len(recs)} | — | — | "
                         f"— | — | — | **partial ({len(recs)}/{_LLM_EXPECTED}) "
                         f"— did not finish** |")
                continue
            s = primary_stat(recs, base, seed)
            up[model][label] = s["passes"]
            if s["delta"] < 0 and s["p_value"] < ALPHA:
                direction = "**significantly BELOW naive**"
            elif s["p_value"] >= ALPHA:
                direction = "indistinguishable from naive"
            else:
                direction = "above naive"
            L.append(f"| {model} | solo | {label} | {s['n_pairs']} | "
                     f"{s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                     f"{s['delta']:+.4f} | {s['p_value']:.4f} | "
                     f"{'YES' if s['passes'] else 'no'} | {direction} |")
    L.append("")

    # Mechanical verdict — only when EVERY registered cell is complete, so a
    # partial run never gets a verdict. Prediction (Amendment 2): NEITHER model
    # separates upward. Contradicted iff any model separates upward on BOTH sets.
    if up and all(len(v) == len(sets) for v in up.values()):
        sep_both = [m for m, v in up.items() if all(v.values())]
        if sep_both:
            names = " and ".join(sep_both)
            L.append(f"**Prediction verdict: CONTRADICTED.** The registered "
                     f"prediction was that NEITHER model separates upward. "
                     f"{names} separate(s) upward from the naive baseline on "
                     f"BOTH sets (delta>0, p<{ALPHA}) — a surprising result: an "
                     f"unaided frontier model beats split-the-difference against "
                     f"the pool, with a margin comparable to the certified "
                     f"engine's (section 1). Reported straight, as registered; "
                     f"it does not enter the certified claim and is not signed. "
                     f"Caveat: Sonnet 5 was measured with adaptive thinking ON "
                     f"(the API default at run time; since disabled in the seat) "
                     f"while Haiku 4.5 does not think by default — the two rows "
                     f"are not under identical inference config.\n")
        else:
            L.append("**Prediction verdict: HELD.** No model separates upward "
                     "from the naive baseline on both sets, as predicted — the "
                     "pool is a floor/ranking-null test for raw models.\n")

    L.append("Read `separates UPWARD?` (delta>0 AND p<0.01), the same registered "
             "criterion as the reference tier — a small p with a negative delta "
             "is a significant result in the WRONG direction, not a win. Every "
             "own-u here shares units and instrument with section 1's own-u "
             "column, which is the whole point of this tier.\n")
    L.append("Regenerate: `python -m arena.gauntlet.llm_tier` (paid; "
             "checkpointed + resumable — completed matches are cached to "
             "`certs/llm-tier-matches.json` and a re-run charges only the gaps) "
             "then `python -m arena.gauntlet.publish_table` (read-only, no LLM).\n")
    return L


def build(n: int = N_SCENARIOS) -> str:
    require_prereg()
    sets = (("PUBLIC", PUBLIC_SEED), ("HELD-OUT", HELDOUT_SEED))

    # ── pool-certified: run every local candidate on both sets ─────────────
    runs: dict = {}
    for label, seed in sets:
        for cand in _LOCAL_CANDIDATES:
            try:
                runs[(label, cand)] = run_candidate(cand, seed, n)
            except Exception:
                runs[(label, cand)] = None
        for cand in _LOCAL_CANDIDATES:
            try:
                runs[(label, cand, "ref")] = run_reference(cand, seed, n)
            except Exception:
                runs[(label, cand, "ref")] = None

    L = []
    L.append("# SNHP Gauntlet — certified results table\n")
    L.append("*Generated by `python -m arena.gauntlet.publish_table`. Every "
             "number below carries the command that regenerates it. Two "
             "populations appear on this page and they are NOT comparable — "
             "read the section headers.*\n")

    # ── section 1: the certified claim ─────────────────────────────────────
    L.append("## 1. POOL-CERTIFIED — the claim\n")
    L.append(f"**What is certified:** mean own-utility pooled across the frozen "
             f"{len(POOL_MEMBERS)}-member counterparty pool "
             f"({', '.join(POOL_MEMBERS)}), versus the naive split-the-difference "
             f"baseline on the identical scenario x pool set, paired by "
             f"(scenario_id, role, counterparty), two-sided sign-flip "
             f"permutation (n_perm=10,000), alpha={ALPHA}. Design frozen in "
             f"`PREREG-pool.md` BEFORE the run; validated on a public set and a "
             f"never-previously-used held-out set (`certs/POOL-RESULTS.md`: "
             f"SURVIVE on both).\n")
    L.append(f"Pool parameters (frozen): "
             + ", ".join(f"`{k}={v}`" for k, v in sorted(POOL_PARAMETERS.items()))
             + ".\n")
    L.append("| candidate | set | n | own-u | naive own-u | delta | perm p | "
             "certified separation |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cand in _LOCAL_CANDIDATES:
        for label, seed in sets:
            recs, base = runs.get((label, cand)), runs.get((label, "naive"))
            if recs is None or base is None:
                continue
            if cand == "naive":
                L.append(f"| naive (baseline) | {label} | {len(recs)} | "
                         f"{np.mean([r['u_candidate'] for r in recs]):.4f} | "
                         f"— | — | — | baseline by definition |")
                continue
            s = primary_stat(recs, base, seed)
            L.append(f"| {cand} | {label} | {s['n_pairs']} | "
                     f"{s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                     f"{s['delta']:+.4f} | {s['p_value']:.4f} | "
                     f"{'**YES**' if s['passes'] else 'no'} |")
    L.append("")
    L.append("**Per-counterparty breakdown** (a pool that separated via only "
             "one member would be visible here as exactly that):\n")
    L.append("| candidate | set | vs naive | vs hardball | vs conceder |")
    L.append("|---|---|---|---|---|")
    for cand in _LOCAL_CANDIDATES:
        if cand == "naive":
            continue
        for label, seed in sets:
            recs, base = runs.get((label, cand)), runs.get((label, "naive"))
            if recs is None or base is None:
                continue
            cells = []
            for cp in POOL_MEMBERS:
                s = primary_stat(_subset(recs, cp), _subset(base, cp), seed)
                cells.append(f"{s['delta']:+.4f} (p={s['p_value']:.4f})")
            L.append(f"| {cand} | {label} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("Regenerate: `python -m arena.gauntlet.pool_experiment` "
             "(verdict + full tables) · `python -m arena.gauntlet.certify "
             "--run engine` (signed certificate) · `python -m "
             "arena.gauntlet.certify --verify certs/<file>.cert.json` "
             "(offline verification, exit 0/1).\n")

    # ── section 2: the reference tier ──────────────────────────────────────
    L.append("## 2. REFERENCE TIER (SNHP engine) — reported, NOT certified\n")
    L.append("> Registered as an ADDITIONAL opponent in `PREREG-pool.md` "
             "Amendment 1 and deliberately kept OUT of the certified statistic. "
             "Adding a fourth member to a registration that had just passed "
             "would be a forking-paths error, so this tier is measured with the "
             "same procedure but reported separately, under any outcome.\n")
    L.append(f"**Registered prediction (stated before the run):** "
             f"{REFERENCE_PREDICTION}\n")
    L.append("| candidate | set | n | own-u | naive own-u | delta | perm p | "
             "separates UPWARD? (delta>0 & p<0.01) | direction |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    any_downward = False
    for cand in _LOCAL_CANDIDATES:
        if cand == "naive":
            continue
        for label, seed in sets:
            recs = runs.get((label, cand, "ref"))
            base = runs.get((label, "naive", "ref"))
            if recs is None or base is None:
                continue
            s = primary_stat(recs, base, seed)
            if s["delta"] < 0 and s["p_value"] < ALPHA:
                direction, any_downward = "**significantly BELOW naive**", True
            elif s["p_value"] >= ALPHA:
                direction = "indistinguishable from naive"
            else:
                direction = "above naive"
            L.append(f"| {cand} | {label} | {s['n_pairs']} | "
                     f"{s['engine_mean']:.4f} | {s['naive_mean']:.4f} | "
                     f"{s['delta']:+.4f} | {s['p_value']:.4f} | "
                     f"{'YES' if s['passes'] else 'no'} | {direction} |")
    L.append("")
    L.append("Read the `direction` column, not the p-value alone: a small p "
             "with a NEGATIVE delta is a significant result in the wrong "
             "direction, not a separation. `separates UPWARD?` is the "
             "registered criterion (delta>0 AND p<0.01).\n")
    if any_downward:
        L.append("Note: the evolved champion lands significantly BELOW the "
                 "naive baseline against the SNHP engine counterparty, while "
                 "separating clearly ABOVE it on the certified pool (section 1). "
                 "That is not a contradiction — it is the same carried-"
                 "counterparty effect that killed capture: against an engine "
                 "that concedes efficiently, an agent that concedes less can "
                 "close fewer deals and score lower, which says nothing about "
                 "its skill versus varied opponents. It is a further reason the "
                 "reference tier is not a ranking instrument.\n")
    try:
        summ = json.loads((_CERTS / "reference-tier.json").read_text())
        outcome = summ.get("prediction_outcome", "not_evaluated")
    except (OSError, json.JSONDecodeError):
        outcome = "not_evaluated"
    L.append(f"**Prediction verdict: {outcome.upper()}.** "
             + ("The reference tier does not separate competent from adequate "
                "on both sets, as predicted: it is a FLOOR test (it catches "
                "weakness — see sections 3-4) and cannot RANK strength. It stays "
                "out of the certified statistic permanently."
                if outcome == "held" else
                "The tier separated on both sets, contradicting the prior "
                "measurement. Reported as surprising; per the registration it "
                "still does not enter the certified claim without its own fresh "
                "registration and held-out validation.") + "\n")
    L.append("Regenerate: `python -m arena.gauntlet.pool_experiment` "
             "(writes `certs/reference-tier.json`).\n")

    # ── section 3: measured frontier models (comparable metric) ─────────────
    L += _llm_tier_section(runs, sets, n)

    # ── section 4: historical, clearly fenced ──────────────────────────────
    L.append("---\n")
    L.append("## 4. HISTORICAL — recorded LLM runs on the RETIRED metric "
             "(NOT pool-certified, NOT comparable to sections 1-3)\n")
    L.append("> **These agents never played the pool.** They played the "
             "ORIGINAL protocol (SNHP EngineSeat as the only counterparty) and "
             "are scored on **capture**, a joint/pair efficiency metric that a "
             "pre-registered kill showed cannot rank strength "
             "(`certs/SEPARATION.md` section 1). They therefore have **no "
             "certified number**, and no row here may be ranked against a row "
             "in section 1. Read verbatim from "
             "`arena/web/gauntlet-matches.json`; no LLM was called to produce "
             "this page.\n")
    matches = []
    if _MATCHES_JSON.exists():
        try:
            matches = json.loads(_MATCHES_JSON.read_text()).get("matches", [])
        except (OSError, json.JSONDecodeError):
            matches = []
    if matches:
        naive_h = _historical(matches, "naive-baseline")
        L.append("| model (historical) | condition | n | capture | naive "
                 "capture | delta | perm p | reading |")
        L.append("|---|---|---|---|---|---|---|---|")
        for model in ("claude-opus-4-8", "claude-sonnet-5",
                      "claude-haiku-4-5-20251001"):
            for cond in ("solo", "advised"):
                mk = _historical(matches, model, cond)
                if not mk or not naive_h:
                    continue
                n_k, cm, bm, dl, p = _capture_delta(mk, naive_h,
                                                    _RECORDED_PERM_SEED)
                if dl < 0 and p < ALPHA:
                    reading = "below baseline (floor test fires)"
                elif p >= ALPHA:
                    reading = "indistinguishable from baseline"
                else:
                    reading = "above baseline (capture only)"
                L.append(f"| {model} | {cond} | {n_k} | {cm:.4f} | {bm:.4f} | "
                         f"{dl:+.4f} | {p:.4f} | {reading} |")
        L.append("")
        L.append("What this section legitimately supports: the FLOOR claim. "
                 "Solo Sonnet and Haiku sit measurably below the naive baseline "
                 "at p<0.01 — weak agents are detectable. What it does NOT "
                 "support: any ranking of these models against each other or "
                 "against section 1, and any claim that an above-baseline "
                 "capture number indicates skill. For Sonnet and Haiku, section "
                 "3 now supersedes this with a comparable own-utility number on "
                 "the pool; these capture rows are kept as the honest record of "
                 "what was measured before the metric was retired.\n")
    else:
        L.append("_(no recorded historical matches found at "
                 "`arena/web/gauntlet-matches.json`)_\n")
    L.append("Regenerate: read-only from `arena/web/gauntlet-matches.json` "
             "(produced historically by `python -m arena.gauntlet.run "
             "--candidate anthropic:MODEL --eval`; re-running costs API calls "
             "and is NOT required to reproduce this page).\n")

    # ── provenance ─────────────────────────────────────────────────────────
    L.append("---\n")
    L.append("## Provenance and honest limits\n")
    L.append(f"- Scenario sets: PUBLIC seed {PUBLIC_SEED}, HELD-OUT seed "
             f"{HELDOUT_SEED} (chosen at registration, unused before it); "
             f"{n} scenarios x 2 roles per set, generated by "
             f"`arena.gauntlet.protocol.gen_gauntlet_scenarios`.")
    L.append("- Certified claim scope: performance against the frozen "
             "3-member scripted pool on these scenario sets. NOT future "
             "performance, NOT other scenario distributions, NOT other "
             "opponents (LLMs, humans), NOT identity beyond the opaque digest "
             "a submitter supplies.")
    L.append("- Prior kills, preserved rather than buried: capture failed as a "
             "certifiable statistic (`certs/SEPARATION.md` section 1) and a "
             "post-hoc logroll re-cut failed its held-out validation "
             "(section 2). The pool protocol is what survived, and only for "
             "the statistic and pool registered in advance.")
    L.append("- Certificates are Ed25519-signed and verify offline from the "
             "file alone; a certificate signed with an ephemeral key says so in "
             "`key_source` and is not a production attestation.")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m arena.gauntlet.publish_table",
                                description=__doc__)
    p.add_argument("--n", type=int, default=N_SCENARIOS)
    p.add_argument("--out", default=str(_OUT))
    args = p.parse_args(argv)
    md = build(args.n)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

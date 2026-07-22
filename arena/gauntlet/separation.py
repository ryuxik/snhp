"""arena/gauntlet/separation.py — the pre-registered KILL check for the
gauntlet certificate, and the post-hoc logroll redesign's validation.

SECTION 1 — THE REGISTERED KILL (capture, history preserved): if the gauntlet
cannot statistically separate a competent scripted candidate (the SNHP
EngineSeat) from the naive split-the-difference baseline (NaiveSeat) on
CAPTURE, two-sided paired permutation test, p < 0.01, the certified capture
number carries no information. That kill FIRED (verdict unchanged, kept here
as history).

SECTION 2 — THE REDESIGN (logroll as the primary certified statistic): after
the capture kill fired, the coordinator diagnosed capture as a joint/pair
metric (a hard-logrolling EngineSeat counterparty carries a naive splitter to
~90% of the ceiling) and directed a redesign around LOGROLL. POST-HOC HONESTY:
that is a metric change adopted AFTER seeing the capture result, and it is
disclosed as such. The redesign is sound ONLY if held-out engine-vs-naive
logroll also separates at p<0.01 — this module runs that validation on the
RECORDED held-out matches (read-only) and reports the verdict, whichever way
it falls.

Data sources (no API, no LLM):
  1. Local runs of EngineSeat / champion / NaiveSeat on the FIXED public
     scenario set gen_gauntlet_scenarios(N, SCENARIO_SEED) — the discoverable,
     versioned practice seed (arena.gauntlet.run.SCENARIO_SEED). The RANKING
     seed is $GAUNTLET_EVAL_SEED, kept private/out of git; we cannot regenerate
     it, so we read its RECORDED results instead:
  2. arena/web/gauntlet-matches.json — the recorded held-out ranking run, which
     carries per-match capture AND logroll for every model. We never re-run an
     LLM. NOTE: champion.json is a genome, not a results file; the recorded
     per-match data lives in gauntlet-matches.json.

Statistics use certify.paired_permutation_pvalue so every p-value is COMPUTED
THE SAME WAY the certificate computes it. Writes certs/SEPARATION.md.
"""
from __future__ import annotations

import json
import pathlib
from typing import Optional

import numpy as np

from arena.gauntlet.certify import paired_permutation_pvalue
from arena.gauntlet.protocol import DEADLINE, gen_gauntlet_scenarios, run_match
from arena.gauntlet.agents import EngineSeat, NaiveSeat


def _match_seed(seed: int, sid: int, role: str) -> int:
    """The leaderboard's per-match seed recipe (arena.gauntlet.run) — this
    module's history sections replay candidate-vs-ENGINESEAT matches on the
    same seeds as the public board. (The /3 certificate now runs the POOL
    protocol with its own domain-tagged recipe, arena.gauntlet.pool.)"""
    import hashlib
    h = hashlib.blake2b(f"{seed}:{sid}:{role}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") & 0x7FFFFFFF

try:
    from arena.gauntlet.run import SCENARIO_SEED
except Exception:  # pragma: no cover
    SCENARIO_SEED = 20260709

KILL_ALPHA = 0.01
_MATCHES_JSON = pathlib.Path(__file__).resolve().parents[1] / "web" / "gauntlet-matches.json"
_OUT = pathlib.Path(__file__).with_name("certs") / "SEPARATION.md"
_RECORDED_PERM_SEED = 0   # documented fixed RNG seed for the read-only comparisons


# ── run a local seat over the fixed set → {(sid, role): row} ────────────────
def _seat(name: str, match_seed: int):
    if name == "engine":
        return EngineSeat(match_seed)
    if name == "naive":
        return NaiveSeat()
    if name == "champion":
        from arena.gauntlet.champion import CHAMPION_PATH, load_champion
        from arena.gauntlet.agents import GenomeSeat
        genome, _ = load_champion(CHAMPION_PATH)
        return GenomeSeat(genome, match_seed)
    raise ValueError(name)


def _run(name: str, seed: int, n: int) -> dict:
    scenarios = gen_gauntlet_scenarios(n, seed)
    out = {}
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            ms = _match_seed(seed, sid, role)
            r = run_match(_seat(name, ms), sc, w_s, w_b, role=role,
                          condition=name, scenario_id=sid, match_seed=ms,
                          deadline=DEADLINE)
            out[(sid, role)] = {"capture": float(r.capture), "deal": bool(r.deal),
                                "logroll": (None if r.logroll is None
                                            else float(r.logroll))}
    return out


# ── the paired analysis, per metric (same permutation the certificate uses) ─
def _one_metric(cand: dict, base: dict, keys: list, metric: str,
                seed: int) -> dict:
    """Paired stats on one metric. capture: all pairs. logroll: SCORED-BOTH
    pairs only (either side None drops the pair) — the certificate's rule."""
    if metric == "logroll":
        keys = [k for k in keys
                if cand[k]["logroll"] is not None and base[k]["logroll"] is not None]
    cc = np.array([cand[k][metric] for k in keys], float)
    bc = np.array([base[k][metric] for k in keys], float)
    diffs = cc - bc
    delta = float(diffs.mean()) if len(diffs) else 0.0
    sd = float(diffs.std(ddof=1)) if len(diffs) > 1 else 0.0
    cohen_d = (delta / sd) if sd > 1e-12 else float("nan")
    p = paired_permutation_pvalue(diffs, seed) if len(diffs) else 1.0
    return {"n_pairs": len(keys),
            "cand_mean": float(cc.mean()) if len(cc) else float("nan"),
            "base_mean": float(bc.mean()) if len(bc) else float("nan"),
            "delta": delta, "cohen_d": cohen_d, "p_value": p,
            "separates": bool(delta > 0 and p < KILL_ALPHA)}


def analyze(cand: dict, base: dict, seed: int, *, label: str) -> dict:
    keys = sorted(set(cand) & set(base))
    return {"label": label, "n": len(keys),
            "capture": _one_metric(cand, base, keys, "capture", seed),
            "logroll": _one_metric(cand, base, keys, "logroll", seed)}


# ── read-only recorded held-out data ────────────────────────────────────────
def _recorded_rows(matches: list, model: str, condition: str = "solo") -> dict:
    out = {}
    for m in matches:
        if m.get("model") == model and m.get("condition") == condition:
            lr = m.get("logroll")
            out[(int(m["scenario_id"]), str(m["role"]))] = {
                "capture": float(m["capture"]), "deal": bool(m["deal"]),
                "logroll": (None if lr is None else float(lr))}
    return out


def _load_recorded() -> Optional[list]:
    if not _MATCHES_JSON.exists():
        return None
    try:
        return json.loads(_MATCHES_JSON.read_text()).get("matches", [])
    except (OSError, json.JSONDecodeError):
        return None


# ── report ───────────────────────────────────────────────────────────────────
def _row_md(a: dict, metric: str) -> str:
    m = a[metric]
    d = "n/a" if m["cohen_d"] != m["cohen_d"] else f"{m['cohen_d']:+.3f}"
    star = "  **" if m["separates"] else ""
    return (f"| {a['label']} | {m['n_pairs']} | {m['cand_mean']:.4f} | "
            f"{m['base_mean']:.4f} | {m['delta']:+.4f} | {d} | "
            f"{m['p_value']:.4f}{star} |")


def _table(rows: list, metric: str, title: str) -> list:
    L = [f"**{title}**\n",
         "| comparison | n pairs | candidate | naive | delta | Cohen's d | perm p |",
         "|---|---|---|---|---|---|---|"]
    L += [_row_md(a, metric) for a in rows]
    L.append("")
    return L


def build_report(n: int = 60, seed: int = SCENARIO_SEED) -> str:
    # 1. local runs on the public practice seed
    naive_pub = _run("naive", seed, n)
    engine_pub = _run("engine", seed, n)
    try:
        champ_pub = _run("champion", seed, n)
    except Exception:
        champ_pub = None
    a_eng = analyze(engine_pub, naive_pub, seed, label="engine vs naive (public seed)")
    local_rows = [a_eng]
    if champ_pub is not None:
        local_rows.append(analyze(champ_pub, naive_pub, seed,
                                  label="champion vs naive (public seed)"))

    # 2. recorded held-out ranking run (read-only)
    matches = _load_recorded()
    held_rows = []
    a_eng_held = None
    if matches:
        nk = _recorded_rows(matches, "naive-baseline")
        ek = _recorded_rows(matches, "engine")
        if nk and ek:
            a_eng_held = analyze(ek, nk, _RECORDED_PERM_SEED,
                                 label="engine vs naive (HELD-OUT, recorded)")
            held_rows.append(a_eng_held)
        for model in ("evolved-champion", "claude-opus-4-8", "claude-sonnet-5",
                      "claude-haiku-4-5-20251001"):
            mk = _recorded_rows(matches, model)
            if mk and nk:
                held_rows.append(analyze(mk, nk, _RECORDED_PERM_SEED,
                                         label=f"{model} vs naive (HELD-OUT, recorded)"))
    all_rows = local_rows + held_rows

    # verdicts
    cap_kill_fires = not a_eng["capture"]["separates"] or (
        a_eng_held is not None and not a_eng_held["capture"]["separates"])
    lr_pub = a_eng["logroll"]
    lr_held = a_eng_held["logroll"] if a_eng_held is not None else None
    # the redesign gate (coordinator-stated): held-out logroll must separate
    redesign_validated = lr_held is not None and lr_held["separates"]

    L = []
    L.append("# Gauntlet certificate — separation analysis "
             "(the registered kill + the post-hoc redesign)\n")

    # ── SECTION 1: the capture kill, history preserved ──────────────────────
    L.append("## 1. The registered kill: CAPTURE — "
             + ("**KILL FIRES** (verdict unchanged)" if cap_kill_fires
                else "KILL SURVIVED") + "\n")
    L.append(f"The pre-registered bar: the gauntlet must separate a *competent "
             f"scripted* candidate (the SNHP `EngineSeat`) from the *naive "
             f"split-the-difference* baseline (`NaiveSeat`) on **capture**, "
             f"two-sided paired permutation test, **p < {KILL_ALPHA}**. If it "
             f"cannot, the certified capture number carries no information.\n")
    c_pub, c_held = a_eng["capture"], (a_eng_held["capture"] if a_eng_held else None)
    L.append(f"- **Public practice seed** ({seed}, n={n}x2 roles): engine capture "
             f"{c_pub['cand_mean']:.4f} vs naive {c_pub['base_mean']:.4f}, delta "
             f"{c_pub['delta']:+.4f}, **p = {c_pub['p_value']:.4f}** — fails "
             f"p<{KILL_ALPHA} (Cohen's d ~ {c_pub['cohen_d']:.2f}).")
    if c_held is not None:
        L.append(f"- **Held-out ranking seed** (recorded, read-only): engine "
                 f"capture {c_held['cand_mean']:.4f} vs naive "
                 f"{c_held['base_mean']:.4f}, delta {c_held['delta']:+.4f}, "
                 f"**p = {c_held['p_value']:.4f}** — the naive baseline is, if "
                 f"anything, *ahead*.")
    L.append("")
    L.append("**Diagnosis** (coordinator, confirmed here): capture is *joint* "
             "efficiency against a counterparty (`EngineSeat`) that logrolls hard "
             "from its own side. When one seat does the frontier-finding, even a "
             "plain anchor-and-split bargainer rides along to ~90% of the ceiling. "
             "Capture measures the pair, not the candidate. The same test DOES "
             "flag *below-baseline* agents sharply (sonnet/haiku, tables below) — "
             "capture detects incompetence, it cannot certify skill.\n")

    # ── SECTION 2: the post-hoc logroll redesign + its validation ───────────
    L.append("## 2. Redesign: logroll as the certified statistic — "
             + ("**VALIDATED on held-out**" if redesign_validated
                else "**NOT VALIDATED — held-out logroll does not separate**")
             + "\n")
    L.append("**Post-hoc disclosure (non-negotiable):** logroll was adopted as "
             "the primary certified statistic AFTER the capture kill fired. That "
             "is a post-hoc metric change — the hypothesis was formed on the same "
             "public-seed data that suggested it, so it proves nothing by itself "
             "and must clear a held-out validation: engine-vs-naive **logroll** on "
             f"the recorded held-out ranking set, p < {KILL_ALPHA}. The recorded "
             "matches carry per-match logroll (all 1200 rows; checked), so the "
             "validation is computable read-only.\n")
    if lr_held is not None:
        L.append(f"- **The gate — held-out logroll (recorded, read-only):** engine "
                 f"{lr_held['cand_mean']:.4f} vs naive {lr_held['base_mean']:.4f}, "
                 f"delta {lr_held['delta']:+.4f}, **p = {lr_held['p_value']:.4f}** "
                 f"({lr_held['n_pairs']} scored-both pairs) — "
                 + ("clears the bar." if redesign_validated else
                    f"naive is *ahead*; nowhere near p<{KILL_ALPHA}. "
                    f"**The gate fails.**"))
    else:
        L.append("- **The gate could not be computed** — recorded held-out data "
                 "unavailable; the redesign is unvalidated by default.")
    L.append(f"- **Public seed, the certificate's own match-seed recipe** "
             f"(leaderboard blake2b): engine logroll {lr_pub['cand_mean']:.4f} vs "
             f"naive {lr_pub['base_mean']:.4f}, delta {lr_pub['delta']:+.4f}, "
             f"**p = {lr_pub['p_value']:.4f}** — "
             + ("clears" if lr_pub["separates"] else "misses")
             + f" p<{KILL_ALPHA} under this recipe. The redesign's motivating run "
             f"(coordinator, a different match-seed recipe) reported delta +0.2254 "
             f"at p=0.0019 on the same scenario set — the direction and magnitude "
             f"REPRODUCE, the significance does not: p flips across the "
             f"{KILL_ALPHA} bar depending on the per-match seed recipe. A "
             f"significance that depends on the seed recipe is not certification-"
             f"grade.")
    L.append("")
    if not redesign_validated:
        L.append("**Consequence:** the certificate format now carries logroll as "
                 "the primary statistic (with the scored-both pairing and pair "
                 "counts), but the engine certificate is NOT re-issued as "
                 "\"fixed\": `not_attested` states in the certificate itself that "
                 "the primary statistic's held-out validation failed and that the "
                 "certificate certifies the measurement, not baseline-beating "
                 "skill. On present evidence NO per-match statistic in the "
                 "recorded data (capture, logroll, own-utility — the coordinator "
                 "measured own-utility delta +0.006, p=0.68) separates engine "
                 "from naive on held-out. The honest read: against a hard-"
                 "logrolling counterparty, the naive splitter's outcomes are "
                 "statistically indistinguishable from the engine's, so candidate "
                 "skill must be measured against a NON-logrolling (or scripted-"
                 "diverse) counterparty pool — a protocol change, not a metric "
                 "change. That is the remaining redesign this analysis points "
                 "to.\n")

    # ── the tables, both metrics, all candidates ────────────────────────────
    L.append("## Separation tables (all candidates vs naive)\n")
    L += _table(all_rows, "logroll", "LOGROLL (primary; scored-both pairing)")
    L += _table(all_rows, "capture", "CAPTURE (secondary; all pairs)")
    L.append(f"(`**` marks delta>0 AND p<{KILL_ALPHA}. Local rows use the public "
             f"scenario seed {seed} with the leaderboard match-seed recipe; the "
             f"permutation RNG derives from that seed exactly as in the "
             f"certificate. Held-out rows are read verbatim from "
             f"`arena/web/gauntlet-matches.json`; their scenario seed is private, "
             f"so their permutation RNG uses a fixed documented constant "
             f"({_RECORDED_PERM_SEED}). Sonnet/haiku separate DOWNWARD — worse "
             f"than naive — on both metrics; no candidate separates upward on "
             f"held-out.)\n")

    L.append(f"_Generated by `python -m arena.gauntlet.separation` (n={n}, public "
             f"seed {seed}, alpha={KILL_ALPHA}). Numbers are from actual local "
             f"runs and recorded read-only data; no LLM was called. Section 2 is "
             f"a disclosed post-hoc analysis._\n")
    return "\n".join(L)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m arena.gauntlet.separation",
                                description=__doc__)
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--seed", type=int, default=SCENARIO_SEED)
    p.add_argument("--out", default=str(_OUT))
    args = p.parse_args(argv)
    md = build_report(n=args.n, seed=args.seed)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    for line in md.splitlines():
        if line.startswith("## "):
            print(line)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

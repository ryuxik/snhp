"""The MERIDIAN audit battery A1-A5 (SPEC "The audit battery").

Every number the report prints is produced here, from seeded runs, >=8 seeds,
means +/- sd, Wilcoxon signed-rank where the comparison is paired.  A1's oracle
and A5-i's bundled counter both re-use the market's OWN utility functions
(meridian.agents) so the auditor is not scoring against a different model than
the one the agents play; A5-i drives the repo's snhp nash_solver primitives
(generate_contract_space / filter_pareto_frontier / find_nash_bargaining_solution)
bootstrapped onto sys.path the way research/swarm/arms.py does.

Run everything (regenerates results + report):

    python -m meridian.audit --full
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import statistics
import sys
from pathlib import Path

import numpy as np

# --- snhp nash_solver bootstrap (A5-i), same pattern as research/swarm/arms.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SNHP = os.path.join(_ROOT, "snhp")
for _p in (_ROOT, _SNHP):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from nash_solver import (filter_pareto_frontier,  # noqa: E402
                         find_nash_bargaining_solution,
                         generate_contract_space)

from . import ledger as L                                    # noqa: E402
from .agents import (buyer_gross_value, joint_surplus,       # noqa: E402
                     supplier_cost)
from .market import Market, MarketConfig, RFQRecord          # noqa: E402

try:
    from scipy.stats import wilcoxon as _wilcoxon
except Exception:                                            # pragma: no cover
    _wilcoxon = None

SEEDS = list(range(101, 109))          # 8 seeds (SPEC: >=8)
RESULTS_DIR = Path(__file__).with_name("results")

# --- per-audit market regimes (each isolates one mechanism) -----------------
BASE = dict(n_buyers=40, n_suppliers=120, ticks=2000)

A1_REGIME = dict(BASE, n_brokers=0, need_by_lo=1, need_by_hi=4,
                 urgency_lo=3.0, urgency_hi=9.0, value_lo=65.0, value_hi=110.0,
                 cap_lo=2, cap_hi=5, collect_rfqs=True)
A2_REGIME = dict(BASE, n_brokers=0, need_by_lo=6, need_by_hi=16,
                 urgency_lo=0.5, urgency_hi=3.0)
A3_REGIME = dict(BASE, n_brokers=0)
A4_REGIME = dict(BASE, n_brokers=12, chain_demand=True)


# --- statistics helpers -----------------------------------------------------
def _mean_sd(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"mean": None, "sd": None, "n": 0}
    return {"mean": statistics.fmean(xs),
            "sd": statistics.stdev(xs) if len(xs) > 1 else 0.0,
            "n": len(xs)}


def _wilcoxon_p(a: list, b: list):
    """Paired Wilcoxon signed-rank p-value (None if degenerate/unavailable)."""
    if _wilcoxon is None or len(a) != len(b) or len(a) < 3:
        return None
    diffs = [x - y for x, y in zip(a, b)]
    if all(abs(d) < 1e-12 for d in diffs):
        return None
    try:
        return float(_wilcoxon(a, b).pvalue)
    except Exception:
        return None


# --- A1 oracle + A5-i nash bundle (same counterparty, richer message set) ----
def _levels(lo: int, hi: int, n: int) -> list[int]:
    return sorted(set(int(round(x)) for x in np.linspace(lo, hi, n)))


def oracle_best(rec: RFQRecord) -> tuple[float, int, int]:
    """Joint-surplus-maximizing (qty, ship_date) for one RFQ against the SAME
    supplier (A1). Price cancels in joint surplus, so this is the whole pie the
    bundle could reach.  Returns (J*, q*, d*); J*=0 means no beneficial trade."""
    qmax = max(1, min(rec.need_qty, int(rec.inventory)))
    natural = max(1, math.ceil(qmax / rec.cap))
    best = (0.0, 0, 0)
    for q in _levels(1, qmax, 8):
        for d in _levels(1, natural, 8):
            J = joint_surplus(q, d, rec.need_qty, rec.need_by, rec.unit_value,
                              rec.urgency, rec.c0, rec.c1, rec.cap, rec.expedite)
            if J > best[0]:
                best = (J, q, d)
    return best


def nash_bundle(rec: RFQRecord) -> tuple[float, int, int, float]:
    """A5-i: negotiate the SAME RFQ over (price, qty, ship_date) with the snhp
    nash_solver instead of price-only.  Returns (joint, q, d, price)."""
    qmax = max(1, min(rec.need_qty, int(rec.inventory)))
    natural = max(1, math.ceil(qmax / rec.cap))
    qs = _levels(1, qmax, 8)
    ds = _levels(1, natural, 8)
    vmax = buyer_gross_value(qmax, rec.need_qty, rec.unit_value, rec.urgency, 0)
    p_lo, p_hi = rec.floor_price * 0.8, max(vmax, rec.floor_price * 1.5)

    # normalized discrete contract space (SPEC: generate_contract_space)
    q_opts = list(np.linspace(0.0, 1.0, len(qs)))
    d_opts = list(np.linspace(0.0, 1.0, len(ds)))
    p_opts = list(np.linspace(0.0, 1.0, 10))
    space = generate_contract_space([q_opts, d_opts, p_opts])

    qi = (space[:, 0] * (len(qs) - 1)).round().astype(int)
    di = (space[:, 1] * (len(ds) - 1)).round().astype(int)
    qv = np.array([qs[i] for i in qi], dtype=float)
    dv = np.array([ds[i] for i in di], dtype=float)
    pv = p_lo + space[:, 2] * (p_hi - p_lo)

    lateness = np.maximum(0.0, dv - rec.need_by)
    unit = np.maximum(0.0, rec.unit_value - rec.urgency * lateness)
    val = np.minimum(qv, rec.need_qty) * unit
    cost = rec.c0 * qv + rec.c1 * qv * qv + rec.expedite * qv * np.maximum(
        0.0, qv / rec.cap - dv)
    ua = val - pv          # buyer surplus
    ub = pv - cost         # supplier surplus

    pareto = filter_pareto_frontier(space, ua, ub)
    idx = find_nash_bargaining_solution(pareto, ua, ub, 0.0, 0.0)
    if idx is None:
        return (0.0, 0, 0, 0.0)
    return (float(ua[idx] + ub[idx]), int(qv[idx]), int(dv[idx]), float(pv[idx]))


def _dedupe_by_line(recs: list[RFQRecord]) -> list[dict]:
    """One opportunity per demand line: oracle on the full line, price-only
    'served' = did ANY attempt trade, realized joint = best traded joint."""
    groups: dict[int, list[RFQRecord]] = {}
    for r in recs:
        groups.setdefault(r.line_id, []).append(r)
    out = []
    for line_id, g in groups.items():
        base = g[0]
        served = any(r.traded for r in g)
        po_joint = max([r.price_only_joint for r in g if r.traded], default=0.0)
        out.append({"rec": base, "served": served, "po_joint": po_joint})
    return out


# --- A1 + A5-i --------------------------------------------------------------
def run_a1(seeds: list[int]) -> dict:
    per_seed = []
    for seed in seeds:
        res = Market(MarketConfig(**A1_REGIME), seed).run()
        opps = _dedupe_by_line(res.rfqs)
        n_benef = foregone = 0
        s_oracle = s_po = s_nash = 0.0
        for o in opps:
            J, _, _ = oracle_best(o["rec"])
            Jn, _, _, _ = nash_bundle(o["rec"])
            s_oracle += J
            s_po += o["po_joint"]
            s_nash += max(0.0, Jn)
            if J > 1e-6:
                n_benef += 1
                if not o["served"]:
                    foregone += 1
        per_seed.append({
            "lines": len(opps),
            "beneficial": n_benef,
            "foregone": foregone,
            "foregone_pct": 100.0 * foregone / max(1, n_benef),
            "oracle_surplus": s_oracle,
            "price_only_surplus": s_po,
            "nash_surplus": s_nash,
            "gap_dollars": s_oracle - s_po,
            "gap_pct": 100.0 * (s_oracle - s_po) / max(1e-9, s_oracle),
            "nash_recovered_pct": 100.0 * s_nash / max(1e-9, s_oracle),
            "nash_residual_gap_pct": 100.0 * (s_oracle - s_nash) / max(1e-9, s_oracle),
        })
    agg = {k: _mean_sd([d[k] for d in per_seed]) for k in per_seed[0]}
    # paired: does bundling beat price-only on realized joint surplus? (per seed)
    agg["wilcoxon_gap_p"] = _wilcoxon_p([d["oracle_surplus"] for d in per_seed],
                                        [d["price_only_surplus"] for d in per_seed])
    agg["wilcoxon_nash_vs_po_p"] = _wilcoxon_p(
        [d["nash_surplus"] for d in per_seed],
        [d["price_only_surplus"] for d in per_seed])
    return {"per_seed": per_seed, "agg": agg}


# --- A2 + A5-ii -------------------------------------------------------------
_A2_KEYS = ["n_trades", "fill_optimistic", "fill_realized",
            "buyer_surplus_realized", "honest_margin_per_trade",
            "deceptive_margin_per_trade", "deceptive_flagged", "deceptive_total",
            "mean_trades_to_flag"]


def _run_metrics(regime: dict, seed: int, **over) -> dict:
    cfg = MarketConfig(**{**regime, **over})
    return Market(cfg, seed).run().metrics


def run_a2(seeds: list[int]) -> dict:
    fractions = [0.0, 0.10, 0.25]
    by_f = {}
    for f in fractions:
        rows = [_run_metrics(A2_REGIME, s, deceptive_fraction=f) for s in seeds]
        agg = {k: _mean_sd([r[k] for r in rows]) for k in _A2_KEYS}
        by_f[f] = {"rows": rows, "agg": agg}
    # per-trade liar-vs-honest advantage at f=0.25 (paired by seed)
    r25 = by_f[0.25]["rows"]        # f=0.25, default bad_prob (channel ON)
    by_f[0.25]["agg"]["wilcoxon_liar_vs_honest_p"] = _wilcoxon_p(
        [r["deceptive_margin_per_trade"] for r in r25],
        [r["honest_margin_per_trade"] for r in r25])

    # SELF-CONTROLLED deception lift: same seed/population, under-delivery
    # channel OFF (bad_prob=0) vs ON (r25). This isolates the causal windfall
    # from the random cost draws of the deceptive-supplier subset (which the
    # naive cross-group liar/honest ratio conflates).
    chan_off = [_run_metrics(A2_REGIME, s, deceptive_fraction=0.25,
                             deceptive_bad_prob=0.0) for s in seeds]
    lift = {
        "channel_on_margin": _mean_sd([r["deceptive_margin_per_trade"] for r in r25]),
        "channel_off_margin": _mean_sd(
            [r["deceptive_margin_per_trade"] for r in chan_off]),
        "lift_ratio": _mean_sd([
            on_r["deceptive_margin_per_trade"] / off_r["deceptive_margin_per_trade"]
            for on_r, off_r in zip(r25, chan_off)
            if off_r["deceptive_margin_per_trade"] > 1e-9]),
        "wilcoxon_p": _wilcoxon_p(
            [r["deceptive_margin_per_trade"] for r in r25],
            [r["deceptive_margin_per_trade"] for r in chan_off]),
    }

    # A5-ii: attestation-gated settlement at f=0.25 (paired off vs on). 'off'
    # reuses r25 (f=0.25, channel on, no attestation) -- same runs, no re-sim.
    off = r25
    on = [_run_metrics(A2_REGIME, s, deceptive_fraction=0.25, attestation=True)
          for s in seeds]
    keys = ["deceptive_margin_per_trade", "honest_margin_per_trade",
            "buyer_surplus_realized"]
    fix = {
        "off": {k: _mean_sd([r[k] for r in off]) for k in keys},
        "on": {k: _mean_sd([r[k] for r in on]) for k in keys},
        "wilcoxon_dec_margin_p": _wilcoxon_p(
            [r["deceptive_margin_per_trade"] for r in off],
            [r["deceptive_margin_per_trade"] for r in on]),
        "wilcoxon_buyer_surplus_p": _wilcoxon_p(
            [r["buyer_surplus_realized"] for r in on],
            [r["buyer_surplus_realized"] for r in off]),
    }
    return {"fractions": fractions, "by_f": by_f, "deception_lift": lift,
            "a5_attestation": fix}


# --- A3 ---------------------------------------------------------------------
_A3_KEYS = ["n_trades", "harmful_accepts", "harmful_per_100",
            "buyer_surplus_realized", "fill_optimistic", "fill_realized"]


def run_a3(seeds: list[int]) -> dict:
    ks = [0, 20, 50]
    by_k = {}
    for k in ks:
        rows = [_run_metrics(A3_REGIME, s, buyer_lag=k) for s in seeds]
        by_k[k] = {"agg": {kk: _mean_sd([r[kk] for r in rows]) for kk in _A3_KEYS},
                   "rows": rows}
    # paired: harmful accepts at k=20 vs k=0
    by_k["wilcoxon_harmful_20_vs_0_p"] = _wilcoxon_p(
        [r["harmful_per_100"] for r in by_k[20]["rows"]],
        [r["harmful_per_100"] for r in by_k[0]["rows"]])
    by_k["wilcoxon_surplus_20_vs_0_p"] = _wilcoxon_p(
        [r["buyer_surplus_realized"] for r in by_k[0]["rows"]],
        [r["buyer_surplus_realized"] for r in by_k[20]["rows"]])
    return {"ks": ks, "by_k": by_k}


# --- A4 ---------------------------------------------------------------------
_A4_KEYS = ["unserved_chain_pct", "chain_demand_qty", "broker_expected_margin",
            "broker_realized_margin", "broker_margin_compression_pct"]


def run_a4(seeds: list[int]) -> dict:
    rows = [_run_metrics(A4_REGIME, s) for s in seeds]
    agg = {k: _mean_sd([r[k] for r in rows]) for k in _A4_KEYS}
    # buyer loss on chain demand = -sum of chain-trade surplus (approx via metric)
    return {"agg": agg, "rows": rows}


# --- ledger integrity (SPEC: hash-chained + tamper detection) ---------------
def run_ledger_checks(seed: int = 101) -> dict:
    res = Market(MarketConfig(**A1_REGIME), seed).run()
    chk = L.verify_chain(res.ledger)
    # determinism: same seed -> identical head hash
    res2 = Market(MarketConfig(**A1_REGIME), seed).run()
    determinism = res.ledger.head_hash() == res2.ledger.head_hash()
    # tamper: mutate one record's data, re-verify -> must fail
    tampered = copy.deepcopy(res.ledger)
    if len(tampered.records) > 5:
        rec = tampered.records[5]
        bad = L.Record(rec.seq, rec.tick, rec.type, {**rec.data, "price": 0.01},
                       rec.prev_hash, rec.hash)
        tampered.records[5] = bad
    tamper_chk = L.verify_chain(tampered)
    return {
        "chain_ok": chk.ok,
        "chain_length": chk.length,
        "head_hash": res.ledger.head_hash(),
        "determinism_ok": determinism,
        "tamper_detected": (not tamper_chk.ok),
        "tamper_error": tamper_chk.error,
        "tamper_error_seq": tamper_chk.error_seq,
    }


# --- orchestration ----------------------------------------------------------
def run_full(seeds: list[int] = SEEDS) -> dict:
    print(f"[meridian] audit battery over {len(seeds)} seeds {seeds}")
    results = {
        "meta": {
            "seeds": seeds,
            "n_buyers": BASE["n_buyers"],
            "n_suppliers": BASE["n_suppliers"],
            "n_brokers": A4_REGIME["n_brokers"],
            "ticks": BASE["ticks"],
        },
    }
    print("[meridian] A1 bundling silence + A5-i nash bundle ...")
    results["A1"] = run_a1(seeds)
    print("[meridian] A2 deception under optimistic settlement + A5-ii ...")
    results["A2"] = run_a2(seeds)
    print("[meridian] A3 stale books ...")
    results["A3"] = run_a3(seeds)
    print("[meridian] A4 broker hold-up ...")
    results["A4"] = run_a4(seeds)
    print("[meridian] ledger integrity ...")
    results["ledger"] = run_ledger_checks(seeds[0])
    return results


def _write_results(results: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "audit_results.json"
    with open(path, "w", encoding="utf-8") as fh:
        # keys are a mix of str/int/float across sub-dicts -> no sort_keys
        json.dump(results, fh, indent=2, default=float)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="MERIDIAN audit battery")
    ap.add_argument("--full", action="store_true",
                    help="run A1-A5 over all seeds and regenerate the report")
    ap.add_argument("--seeds", type=int, default=len(SEEDS),
                    help="number of seeds (>=8 for the deliverable)")
    args = ap.parse_args()

    seeds = list(range(101, 101 + max(1, args.seeds)))
    results = run_full(seeds)
    path = _write_results(results)
    print(f"[meridian] results -> {path}")

    from . import report
    report_path = report.generate(results)
    print(f"[meridian] report  -> {report_path}")


if __name__ == "__main__":
    main()

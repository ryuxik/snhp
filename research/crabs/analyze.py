"""Validation gate and kill-condition evaluation. Prints the verdict table.

    python research/crabs/analyze.py                       # phase 1
    python research/crabs/analyze.py --file results_phase1_heldout.json

Reporting rules (PREREG §7): the gate result is printed FIRST; every kill
condition gets an explicit FIRED / DID NOT FIRE line with the deciding numbers.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

ANNUAL_RENT = 24000.0
PCT1 = 0.01 * ANNUAL_RENT          # $240 -- K3, K4
PCT2 = 0.02 * ANNUAL_RENT          # $480 -- K1

# gate bands (PREREG §3, verbatim)
V1_BAND = (0.15, 0.30)
V2_BAND = (0.45, 0.65)
V3_MIN_RATIO = 1.5


def mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def se(xs):
    xs = [x for x in xs if x == x]
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def paired(a, b):
    """Paired difference under common random numbers -> mean, SE."""
    d = [x - y for x, y in zip(a, b) if x == x and y == y]
    return mean(d), se(d)


class Cells:
    def __init__(self, cells):
        self.cells = cells

    def get(self, **kw):
        out = [c for c in self.cells
               if all(abs(c[k] - v) < 1e-9 if isinstance(v, float) else c[k] == v
                      for k, v in kw.items())]
        if len(out) != 1:
            raise KeyError(f"{kw} -> {len(out)} cells")
        return out[0]

    def has(self, **kw):
        try:
            self.get(**kw)
            return True
        except KeyError:
            return False


# ------------------------------------------------------------------ the gate
def gate(C: Cells, out: list) -> bool:
    out.append("=" * 78)
    out.append("VALIDATION GATE (PREREG §3) -- reported before any arm result")
    out.append("=" * 78)
    out.append("Arm A, the empirical 39% mix, no station parameter set by "
               "reference to these targets.")
    out.append("")
    out.append(f"{'':22s} {'LOSS-TO-LEASE':>16s} {'GAIN-TO-LEASE':>16s} "
               f"{'target':>14s} {'verdict':>9s}")
    rows, ok = [], True
    a = {r: C.get(arm="A", regime=r) for r in ("loss", "gain")}
    d = {r: a[r]["derived"] for r in a}

    def row(label, key, band=None, minr=None, fmt="{:.3f}"):
        nonlocal ok
        vals = [d[r][key] for r in ("loss", "gain")]
        if band:
            good = all(band[0] <= v <= band[1] for v in vals)
            tgt = f"{band[0]:.2f}-{band[1]:.2f}"
        else:
            good = all(v == v and v >= minr for v in vals)
            tgt = f">= {minr:.2f}x"
        ok = ok and good
        rows.append(f"{label:22s} {fmt.format(vals[0]):>16s} "
                    f"{fmt.format(vals[1]):>16s} {tgt:>14s} "
                    f"{'PASS' if good else 'FAIL':>9s}")

    row("V1 counter success", "success_rate", band=V1_BAND)
    row("V2 retention", "retention", band=V2_BAND)
    row("V3 tenure ratio", "tenure_ratio", minr=V3_MIN_RATIO)
    out.extend(rows)
    out.append("")
    out.append("  supporting numbers")
    for r in ("loss", "gain"):
        x = d[r]
        out.append(f"    {r:5s}: success <2y {x['success_lt2']:.3f} / 2y+ "
                   f"{x['success_ge2']:.3f}; price-only success "
                   f"{x['success_rate_price']:.3f}; counter rate "
                   f"{x['counter_rate']:.3f}; mean offer push "
                   f"{x['mean_offer_push']:+.3f}; rent/market "
                   f"{x['rent_ratio']:.3f}; station predicted leave "
                   f"{x['calib_pred_leave']:.3f} vs realised "
                   f"{x['calib_real_leave']:.3f}")
        out.append(f"           station-years {x['station_years']:.0f}, "
                   f"habitat-years {x['habitat_years']:.0f}, "
                   f"cash ledger gap ${x['ledger_gap']:.4f}")
    out.append("")
    out.append(f"GATE: {'PASS' if ok else 'FAIL'}")
    if not ok:
        out.append("PREREG §3: if V1-V3 fail, the model does not describe the "
                   "world and every counterfactual is VOID. Reported as failed; "
                   "arm results below are diagnostic only.")
    out.append("")
    return ok


# ------------------------------------------------------------- the arm table
def arm_table(C: Cells, out: list):
    out.append("=" * 78)
    out.append("ARM RESULTS -- crab surplus is $/crab-year vs paying market "
               "rent with no move")
    out.append("=" * 78)
    hdr = (f"{'arm':>16s} {'regime':>6s} {'surplus':>9s} {'askers':>9s} "
           f"{'non-ask':>9s} {'stn cash':>9s} {'mkt rent':>9s} {'reten':>6s} "
           f"{'r/mkt':>6s} {'succ':>6s}")
    for regime in ("loss", "gain"):
        out.append(hdr)
        for label, kw in _arm_list(C):
            if not C.has(regime=regime, **kw):
                continue
            c = C.get(regime=regime, **kw)
            d = c["derived"]
            out.append(f"{label:>16s} {regime:>6s} {d['surplus_pcy']:9.0f} "
                       f"{d['surplus_asker']:9.0f} {d['surplus_nonasker']:9.0f} "
                       f"{d['station_cash_phy']:9.0f} {d['market_rent']:9.0f} "
                       f"{d['retention']:6.3f} {d['rent_ratio']:6.3f} "
                       f"{d['success_rate']:6.3f}")
        out.append("")


def _arm_list(C):
    lst = [("A mix 39% price", dict(arm="A")),
           ("B all price", dict(arm="B")),
           ("C all ranked", dict(arm="C"))]
    for s in (0.0, 0.10, 0.25, 0.50, 0.75, 1.0):
        lst.append((f"D share {s:.2f}", dict(arm="D", share=s)))
    for s in (0.0, 0.10, 0.25, 0.50, 0.75, 1.0):
        lst.append((f"E adapt {s:.2f}", dict(arm="E", share=s)))
    return lst


# -------------------------------------------------------------- kill conditions
def kills(C: Cells, out: list):
    out.append("=" * 78)
    out.append("KILL CONDITIONS (PREREG §5) -- bidirectional, pre-registered")
    out.append("=" * 78)
    verdicts = {}

    # ---- K1: ranked-ask advice is decoration
    dv, ds = paired(C.get(arm="C", regime="gain")["per_station"]["surplus_pcy"],
                    C.get(arm="B", regime="gain")["per_station"]["surplus_pcy"])
    fired = not (dv >= PCT2)
    verdicts["K1"] = fired
    out.append("")
    out.append("K1 -- the ranked-ask advice is decoration.")
    out.append(f"  Fires if C does not beat B by >= 2% of annual rent "
               f"(${PCT2:.0f}/crab-year) on mean crab surplus, gain regime.")
    out.append(f"  C - B (paired, gain) = ${dv:+.0f} +/- {ds:.0f} SE   "
               f"[bar ${PCT2:.0f}]")
    lv, ls = paired(C.get(arm="C", regime="loss")["per_station"]["surplus_pcy"],
                    C.get(arm="B", regime="loss")["per_station"]["surplus_pcy"])
    out.append(f"  (loss regime, for reference: ${lv:+.0f} +/- {ls:.0f})")
    out.append(f"  --> K1 {'FIRED' if fired else 'DID NOT FIRE'}")

    # ---- K2: negotiation value is transitional
    out.append("")
    out.append("K2 -- negotiation value is transitional, not structural.")
    out.append("  Fires if per-asker surplus in E declines monotonically toward "
               "<= 25% of its arm-D value as asker share -> 100%.")
    k2 = {}
    for regime in ("loss", "gain"):
        s0 = C.get(arm="D", regime=regime, share=0.0)["derived"]["surplus_pcy"]
        seq = []
        for s in (0.10, 0.25, 0.50, 0.75, 1.0):
            dd = C.get(arm="D", regime=regime, share=s)["derived"]["surplus_asker"]
            ee = C.get(arm="E", regime=regime, share=s)["derived"]["surplus_asker"]
            voa_d, voa_e = dd - s0, ee - s0
            seq.append((s, voa_d, voa_e,
                        voa_e / voa_d if abs(voa_d) > 1e-9 else float("nan")))
        ratios = [x[3] for x in seq]
        mono = all(ratios[i + 1] <= ratios[i] + 1e-9 for i in range(len(ratios) - 1))
        fired = mono and ratios[-1] <= 0.25
        k2[regime] = fired
        out.append(f"  {regime}:  value of asking (VOA) = asker surplus - "
                   f"surplus at share 0 (${s0:.0f})")
        out.append(f"    {'share':>6s} {'VOA in D':>10s} {'VOA in E':>10s} "
                   f"{'E/D':>8s}")
        for s, vd, ve, rr in seq:
            out.append(f"    {s:6.2f} {vd:10.0f} {ve:10.0f} {rr:8.3f}")
        out.append(f"    monotone decline: {mono};  E/D at share 1.0 = "
                   f"{ratios[-1]:.3f} (bar <= 0.25)")
        out.append("    literal reading (surplus LEVELS, not value of asking): "
                   f"E {C.get(arm='E', regime=regime, share=1.0)['derived']['surplus_asker']:.0f}"
                   f" vs D {C.get(arm='D', regime=regime, share=1.0)['derived']['surplus_asker']:.0f}"
                   " -- dominated by the common 12*M term, hence the VOA form")
    fired = k2["loss"] or k2["gain"]
    verdicts["K2"] = fired
    out.append(f"  --> K2 {'FIRED' if fired else 'DID NOT FIRE'}"
               f"  (loss {k2['loss']}, gain {k2['gain']})")

    # ---- K3: negative externality on non-askers
    out.append("")
    out.append("K3 -- the tool has a negative externality.")
    out.append("  Fires if non-asker surplus in E at 75-100% asker share is "
               f"worse than at 0% by >= 1% of annual rent (${PCT1:.0f}).")
    k3 = {}
    for regime in ("loss", "gain"):
        b = C.get(arm="E", regime=regime, share=0.0)
        base = b["derived"]["surplus_nonasker"]
        worst = None
        for s in (0.75,):
            c = C.get(arm="E", regime=regime, share=s)
            dv2, ds2 = paired(b["per_station"]["surplus_nonasker"],
                              c["per_station"]["surplus_nonasker"])
            worst = (s, c["derived"]["surplus_nonasker"], dv2, ds2)
        # share 1.0 has no non-askers by construction; note it
        s, lvl, dv2, ds2 = worst
        f = dv2 >= PCT1
        k3[regime] = f
        out.append(f"  {regime}: non-asker surplus at share 0.00 = ${base:.0f}; "
                   f"at 0.75 = ${lvl:.0f}; loss to non-askers = ${dv2:+.0f} "
                   f"+/- {ds2:.0f} SE  [bar ${PCT1:.0f}]")
        out.append("         share 1.00 has no non-askers by construction, so "
                   "0.75 is the highest evaluable share")
    fired = k3["loss"] or k3["gain"]
    verdicts["K3"] = fired
    out.append(f"  --> K3 {'FIRED' if fired else 'DID NOT FIRE'}"
               f"  (loss {k3['loss']}, gain {k3['gain']})")

    # ---- K4: the regime argument
    out.append("")
    out.append("K4 -- the regime argument is wrong.")
    out.append("  Fires unless C's advantage over A is larger in the gain "
               f"regime than in the loss regime by >= ${PCT1:.0f} (SPEC §10).")
    gv, gs = paired(C.get(arm="C", regime="gain")["per_station"]["surplus_pcy"],
                    C.get(arm="A", regime="gain")["per_station"]["surplus_pcy"])
    lv2, ls2 = paired(C.get(arm="C", regime="loss")["per_station"]["surplus_pcy"],
                      C.get(arm="A", regime="loss")["per_station"]["surplus_pcy"])
    fired = not ((gv - lv2) >= PCT1)
    verdicts["K4"] = fired
    out.append(f"  C - A, gain = ${gv:+.0f} +/- {gs:.0f}")
    out.append(f"  C - A, loss = ${lv2:+.0f} +/- {ls2:.0f}")
    out.append(f"  difference (gain - loss) = ${gv - lv2:+.0f}  [bar ${PCT1:.0f}]")
    out.append(f"  --> K4 {'FIRED' if fired else 'DID NOT FIRE'}")

    out.append("")
    out.append("-" * 78)
    out.append("SUMMARY  " + "   ".join(
        f"{k}: {'FIRED' if v else 'DID NOT FIRE'}" for k, v in verdicts.items()))
    out.append("-" * 78)
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="results_phase1.json")
    a = ap.parse_args()
    path = a.file if os.path.isabs(a.file) else os.path.join(_HERE, a.file)
    with open(path) as f:
        data = json.load(f)
    C = Cells(data["cells"])
    out = []
    m = data["meta"]
    out.append(f"crabs {m['version']}  seeds {m['seeds_used']} "
               f"{m['station_seeds'][0]}-{m['station_seeds'][1]} "
               f"({m['n_stations']} stations)  pilot {m['pilot_seeds'][0]}-"
               f"{m['pilot_seeds'][1]}  runtime {m['runtime_s']}s")
    out.append("")
    passed = gate(C, out)
    arm_table(C, out)
    kills(C, out)
    if not passed:
        out.append("")
        out.append("REMINDER: the validation gate FAILED. Per PREREG §3 the "
                   "kill-condition numbers above are diagnostic, not findings.")
    print("\n".join(out))


if __name__ == "__main__":
    main()

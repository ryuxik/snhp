"""Numerical harness for THEOREM-IC-MULTI: multi-issue emergent buyer-IC.

Companion to THEOREM-IC.md's single-good `regimes2.py`/`decouple.py` checks.
Implements the EXACT deployed Nash-in-Nash rule (matching
vend/scenario.py::nash_quote and boba/policies.py::cart_nash) for a smallest
honest TWO-GOOD model with a CONCAVE (logroll) frontier, then BRUTE-FORCES the
buyer's best report to test whether truthful disclosure is a weak best
response, and traces the multi-good buffer boundary.

Concavity: a bundling complementarity kappa>=0 -- the gains-from-bundling
curvature. V({A,B}) = v_A + v_B + kappa; V({i}) = v_i. kappa=0 is the additive
(linear-frontier) special case v-D-L Thm 1 covers.

The load-bearing modelling choice is CONDITION (c) EXTENDED TO THE BUNDLE: is
the disclosed disagreement point computed on the SAME concave value V-hat that
enters the trade? boba's best_menu_order values the WHOLE cart via bundle_value
(concave, with kappa) -> event_consistent=True. An additive board that ignores
kappa -> event_consistent=False. We show the buffer condition depends on this.

Two disagreement STRUCTURES (the code has both):
  * "joint": JOINT BUNDLE (boba cart_nash). No-deal event = buy the best SUBSET
    at the board; d_b = max_Y [V-hat(Y) - sum ell_Y]_+. The logrolling / GTM rule.
  * "separable": vend nash_quote. Independent single-good deals; the good-i deal's
    disagreement is max over ALL goods' single boards (THEOREM-IC 8 case C).

Pure algebra; no secrets, no repo state. Closed-form price (the log-Nash
objective is concave in p, so the box-constrained optimum is the clamped
interior point). Run: python3 paper/theorem_ic_multi_harness.py
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class Good:
    ell: float    # list price = discount-only ceiling
    c: float      # unit cost
    excess: bool  # True: shadow reservation = c ; False (scarce): = ell


def shadow(g: Good) -> float:
    return g.c if g.excess else g.ell


def pkg_value(v: dict, X, kappa: float) -> float:
    return sum(v[i] for i in X) + (kappa if len(X) == 2 else 0.0)


# ---------------------------------------------------------------------------
# Closed-form Nash price for a fixed subset (log-objective concave in p ->
# constrained optimum = clamp of unconstrained interior optimum to feasible box)
# ---------------------------------------------------------------------------
def _best_price(cost, ceil, Vhat, d_s, d_b, w):
    """Return (p, gs, gb) maximizing gs^w gb^(1-w) s.t. gs>=0, gb>=0, p<=ceil,
    or None if the feasible box is empty. margin = p - cost."""
    p_lo = cost + d_s                    # gs = (p-cost)-d_s >= 0
    p_hi = min(ceil, Vhat - d_b)         # gb = (Vhat-p)-d_b >= 0 AND ceiling
    if p_lo > p_hi + 1e-12:
        return None
    # unconstrained interior: w*gb = (1-w)*gs  =>
    #   p* = w*(Vhat - d_b) + (1-w)*(cost + d_s)
    p_star = w * (Vhat - d_b) + (1.0 - w) * (cost + d_s)
    p = min(max(p_star, p_lo), p_hi)
    gs = (p - cost) - d_s
    gb = (Vhat - p) - d_b
    return p, gs, gb


def _board(vhat, goods, kappa, event_consistent, structure):
    """Disclosed disagreement (d_b, d_s).  structure in {joint, separable}."""
    singles = {i: max(0.0, vhat[i] - goods[i].ell) for i in goods}
    if structure == "separable":
        # vend: best SINGLE-good board (concavity/kappa never crosses goods here)
        arg = max(goods, key=lambda i: singles[i])
        if singles[arg] > 0.0:
            return singles[arg], (goods[arg].ell - shadow(goods[arg])), ("board", arg)
        return 0.0, 0.0, ("none", None)
    # joint bundle: best SUBSET at the board
    best = (0.0, 0.0, ("none", None))
    subsets = [()] + [c for r in (1, 2) for c in itertools.combinations(sorted(goods), r)]
    for Y in subsets:
        if not Y:
            continue
        kap = kappa if (event_consistent and len(Y) == 2) else 0.0
        val = sum(vhat[i] for i in Y) + kap
        surplus = val - sum(goods[i].ell for i in Y)
        if surplus > best[0] + 1e-12:
            margin = sum(goods[i].ell - shadow(goods[i]) for i in Y)
            best = (surplus, margin, ("board", Y))
    return best


def nash_quote(goods, vhat, ohat, kappa, beta, w=0.5,
               event_consistent=True, structure="joint",
               deal_subset=None):
    """The deployed asymmetric Nash-in-Nash rule with buffer-GATES-argmax.

    Returns (X, p, gs, gb) or None (withdrawn / infeasible).
    deal_subset: restrict the tradeable outcome to this subset (used by the
    separable single-good rule); None -> broker enumerates all subsets (joint)."""
    d_b_board, d_s_board, _ = _board(vhat, goods, kappa, event_consistent, structure)
    if d_b_board >= ohat:
        d_b, d_s = d_b_board, d_s_board
    else:
        d_b, d_s = ohat, 0.0

    if deal_subset is not None:
        subsets = [tuple(deal_subset)]
    else:
        subsets = [c for r in (1, 2) for c in itertools.combinations(sorted(goods), r)]

    best = None  # (score, X, p, gs, gb)
    for X in subsets:
        Vhat = pkg_value(vhat, X, kappa)
        cost = sum(shadow(goods[i]) for i in X)
        ceil = sum(goods[i].ell for i in X)
        r = _best_price(cost, ceil, Vhat, d_s, d_b, w)
        if r is None:
            continue
        p, gs, gb = r
        gsc, gbc = max(0.0, gs), max(0.0, gb)
        nash = gsc * gbc if w == 0.5 else (gsc ** w) * (gbc ** (1.0 - w))
        score = (nash, gs + gb)
        if best is None or score > best[0]:
            best = (score, X, p, gs, gb)
    if best is None:
        return None
    score, X, p, gs, gb = best
    if score[0] <= 1e-15 and score[1] <= 1e-9:
        return None
    if gs < beta - 1e-9:          # buffer GATES the argmax (no reprice)
        return None
    return X, p, gs, gb


def true_fallback(goods, v, o, kappa, event_consistent, structure):
    if structure == "separable":
        return max(o, max((max(0.0, v[i] - goods[i].ell) for i in goods), default=0.0))
    # joint: buyer self-assembles the best board subset (kappa if consistent)
    best = o
    for Y in [c for r in (1, 2) for c in itertools.combinations(sorted(goods), r)]:
        kap = kappa if (event_consistent and len(Y) == 2) else 0.0
        best = max(best, sum(v[i] for i in Y) + kap - sum(goods[i].ell for i in Y))
    return max(best, o)


def realized(goods, v, o, kappa, beta, report, w, event_consistent, structure,
             deal_subset=None):
    vhat, ohat = report
    q = nash_quote(goods, vhat, ohat, kappa, beta, w, event_consistent,
                   structure, deal_subset)
    fb = true_fallback(goods, v, o, kappa, event_consistent, structure)
    if q is None:
        return fb
    X, p, _, _ = q
    return max(pkg_value(v, X, kappa) - p, fb)


PHI = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.25, 1.6]


def best_response_regret(goods, v, o, kappa, beta, w=0.5,
                         event_consistent=True, structure="joint",
                         deal_subset=None):
    """max over reports of realized true surplus minus HONEST realized.
    Deviation class: multiplicative WTP-scaling phi_i per good x outside inflate."""
    keys = sorted(goods)
    o_grid = [o, o + 0.5, o + 1.0, o + 2.0, o + 5.0]
    honest = realized(goods, v, o, kappa, beta, (dict(v), o), w,
                      event_consistent, structure, deal_subset)
    best, brep = honest, (dict(v), o)
    for pa in PHI:
        for pb in PHI:
            vhat = {keys[0]: pa * v[keys[0]], keys[1]: pb * v[keys[1]]}
            for oh in o_grid:
                rr = realized(goods, v, o, kappa, beta, (vhat, oh), w,
                              event_consistent, structure, deal_subset)
                if rr > best + 1e-9:
                    best, brep = rr, (dict(vhat), oh)
    return best - honest, honest, best, brep


def sweep_types(goods, kappa, beta, w=0.5, event_consistent=True,
                structure="joint", deal_subset=None):
    keys = sorted(goods)
    V = [0.5, 1.5, 2.5, 3.5, 5.0, 6.0]
    O = [0.0, 0.5, 1.0, 2.0, 4.0]
    worst = (-1e9, None)
    for va in V:
        for vb in V:
            for o in O:
                v = {keys[0]: va, keys[1]: vb}
                reg, hon, dev, rep = best_response_regret(
                    goods, v, o, kappa, beta, w, event_consistent, structure, deal_subset)
                if reg > worst[0]:
                    worst = (reg, (dict(v), o, hon, dev, rep))
    return worst


def banner(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def main():
    banner("EXP 1  Additive frontier (kappa=0), JOINT bundle, event-consistent")
    print("Prediction: leak iff sum(l-c) > 2*beta  (both goods EXCESS)")
    print(f"{'l_A':>5}{'c_A':>5}{'l_B':>5}{'c_B':>5}{'beta':>6}"
          f"{'S(l-c)':>8}{'2beta':>7}{'sup-reg':>9}{'pred':>6}{'ok':>4}")
    for lA, cA, lB, cB, beta in [
        (2.0, 0.7, 2.0, 0.7, 1.5),
        (2.0, 0.7, 2.0, 0.7, 1.2),
        (2.0, 0.7, 2.0, 0.7, 0.6),
        (2.6, 0.7, 2.65, 0.5, 1.5),
        (0.85, 0.30, 0.85, 0.30, 1.5),
        (3.0, 0.5, 0.9, 0.3, 1.0),
    ]:
        goods = {"A": Good(lA, cA, True), "B": Good(lB, cB, True)}
        reg = sweep_types(goods, 0.0, beta)[0]
        s = (lA - cA) + (lB - cB)
        pred = s > 2 * beta + 1e-9
        print(f"{lA:>5}{cA:>5}{lB:>5}{cB:>5}{beta:>6}{s:>8.2f}{2*beta:>7.2f}"
              f"{reg:>9.4f}{str(pred):>6}{'OK' if (reg>1e-4)==pred else 'XX':>4}")

    banner("EXP 2  CONCAVE frontier: does kappa change the condition? (consistent)")
    print("B is single-good SAFE. sum(l-c)=2.10, 2beta=3.0 -> additive-SAFE.")
    print("If kappa CANCELS (event-consistent), sup-regret stays ~0 for all kappa.")
    goods = {"A": Good(2.0, 0.7, True), "B": Good(1.6, 0.8, True)}
    beta = 1.5
    print(f"{'kappa':>7}{'S(l-c)+k':>10}{'2beta':>7}{'sup-reg(consist)':>18}"
          f"{'sup-reg(INCONsist)':>20}")
    for kappa in [0.0, 0.3, 0.6, 0.9, 1.2, 1.6, 2.0, 3.0]:
        rc = sweep_types(goods, kappa, beta, event_consistent=True)[0]
        ri = sweep_types(goods, kappa, beta, event_consistent=False)[0]
        s = (2.0 - 0.7) + (1.6 - 0.8)
        print(f"{kappa:>7.2f}{s+kappa:>10.2f}{2*beta:>7.1f}{rc:>18.4f}{ri:>20.4f}")
    print("Prediction: consistent -> leak iff sum(l-c)>2beta (kappa-free);")
    print("            INCONsistent -> leak iff sum(l-c)+kappa>2beta.")

    banner("EXP 3  THEOREM-IC 8 case C: high truthful anchor, understate the other")
    print("v_A=6 (anchor), understate B. Compare separable(vend) vs joint(boba).")
    goods = {"A": Good(2.0, 0.7, True), "B": Good(2.6, 0.7, True)}  # l_B-c_B=1.9
    beta = 1.0   # single-good: l_B-c_B=1.9 < 2b=2.0 -> B alone SAFE
    v = {"A": 6.0, "B": 4.0}
    for struct in ("separable", "joint"):
        ds = ("B",) if struct == "separable" else None
        reg, hon, dev, rep = best_response_regret(
            goods, v, 0.0, 0.0, beta, structure=struct, deal_subset=ds)
        vhat, oh = rep
        print(f"  [{struct:>9}] honest={hon:.3f} best-dev={dev:.3f} regret={reg:.4f}"
              f"  report={ {k:round(x,2) for k,x in vhat.items()} }")
    print("  (separable: A's board pins d_b -> B-deal infeasible -> protected)")

    banner("EXP 4  Boundary trace: symmetric goods, vary beta (joint, consistent)")
    for r in [0.5, 1.0, 1.5]:
        goods = {"A": Good(1.0 + r, 1.0, True), "B": Good(1.0 + r, 1.0, True)}
        cells = []
        for beta in [0.4, 0.9, 0.99, 1.01, 1.5, 2.0, 2.5]:
            reg = sweep_types(goods, 0.0, beta)[0]
            cells.append(f"b={beta}:{'L' if reg > 1e-4 else '.'}")
        print(f"  r={r} sum(l-c)={2*r}: " + "  ".join(cells)
              + f"   [pred leak iff 2beta<{2*r}]")

    banner("EXP 5  Seller-weight tilt w>0.5 (monetization) -- does it open a leak?")
    goods = {"A": Good(2.6, 0.7, True), "B": Good(2.65, 0.5, True)}
    for w in [0.5, 0.6, 0.75, 0.9, 1.0]:
        reg = sweep_types(goods, 0.0, 1.5, w=w)[0]
        print(f"  w={w}: sup-regret={reg:.4f}   (sum(l-c)=3.75, 2beta=3.0 -> leaks)")

    banner("EXP 6  Mixed states: A SCARCE + B EXCESS (does scarce anchor confine?)")
    goods = {"A": Good(2.0, 0.7, False), "B": Good(2.6, 0.7, True)}
    for kappa in [0.0, 1.0, 2.0]:
        reg = sweep_types(goods, kappa, 1.0)[0]
        print(f"  kappa={kappa}: sup-regret={reg:.4f}  "
              f"(only B excess: pred leak iff l_B-c_B=1.9 > 2b=2.0 -> safe)")

    banner("EXP 7  Separable(vend) rule: condition is MAX_i(l-c)<=2b, not SUM")
    print("Two excess goods; sweep the good the buyer negotiates (deal_subset).")
    print("Pred: separable leaks iff SOME single good has l_i-c_i > 2beta.")
    for (lA, cA, lB, cB, beta, tag) in [
        (2.0, 0.7, 2.0, 0.7, 1.0, "each l-c=1.3<2b=2.0, sum=2.6>2b -> MAX safe"),
        (3.5, 0.5, 2.0, 0.7, 1.0, "l_A-c_A=3.0>2b=2.0 -> leaks on A"),
    ]:
        goods = {"A": Good(lA, cA, True), "B": Good(lB, cB, True)}
        # buyer may negotiate EITHER good as a separate deal; take the worst
        rA = sweep_types(goods, 0.0, beta, structure="separable", deal_subset=("A",))[0]
        rB = sweep_types(goods, 0.0, beta, structure="separable", deal_subset=("B",))[0]
        mx = max(lA - cA, lB - cB)
        print(f"  {tag}\n    sup-regret dealA={rA:.4f} dealB={rB:.4f}  "
              f"max(l-c)={mx:.2f} 2b={2*beta:.1f} pred-leak={mx>2*beta}")


if __name__ == "__main__":
    main()

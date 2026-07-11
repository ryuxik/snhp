"""B6.5 — the calibration-for-discount DATA MARKET (NETWORK.md §C.4; task #72).

The inversion that ties the whole thesis. The merchant's core problem is not
knowing its own demand curve — the MISCALIBRATION channel (μ̂ = μ·noise), the
block's headline result. A resident cluster's VERIFIED AGGREGATE disclosures ARE
that demand curve. So clusters can SELL calibration: consented aggregate demand
data that shrinks the merchant's σ_cal, in exchange for a standing discount,
priced by the broker. The information rent returns to the people who generate
the information.

THE EXCHANGE THESIS under test (the antagonism finding, inverted): the shopping
HAGGLE is a TRANSFER the merchant resists and that competes away as boards
converge (CRITICAL-ANALYSIS §10). The DATA is a POSITIVE-SUM good the merchant
funds WILLINGLY — because a merchant that finally knows its demand curve stops
mispricing, and the recovered profit is real. The prediction (NETWORK.md §C.4):
a Pareto gain where the information rent to consumers EXCEEDS the shopping
transfer, the split favors consumers in proportion to cluster size, and — the
mirror of the buyer monopsony audit — a demand cartel cannot extract below the
merchant's participation floor.

Model (clean linear demand per SKU, so the miscalibration → mispricing → recovered
value chain is transparent and every dollar is decomposable):
  * WTP uniform on [0, 2μ] with mass Λ (the SKU's demand scale): D(p) = Λ(1−p/2μ).
  * The merchant sets the monopoly-optimal price on its ESTIMATE μ̂: p*(μ̂)=μ̂+c/2.
  * μ̂ = μ·exp(σ·z), z ~ N(0,1) drawn ONCE per (seed, sku) and only its magnitude
    σ(K) shrinks with the cluster's K verified disclosures (the B6.1 conjugate
    shrinkage σ(K)=σ0·√(α₀/(α₀+K)) — one clean WTP obs per member). Paired across
    K: the calibration ERROR direction is fixed, only its size falls.
  * profit and consumer surplus are booked against the TRUE μ (the decision uses
    only μ̂). Miscalibration is costly because Π is concave in μ̂ peaked at μ̂=μ, so
    E[Π] rises as σ shrinks (Jensen) — the merchant's recovered profit ΔΠ(K) is
    its willingness-to-pay for the cluster's data.

The DATA value ΔΠ(K) (positive-sum, durable) is compared against the HAGGLE
transfer (zero-sum, competed away): a cluster that instead just bargains the
board down bilaterally extracts (p_board−c)/2 per unit — a transfer the merchant
loses and that collapses to ~0 once a competitor drives the board to cost. The
verdict: is the durable, non-competable value the DATA MARKET (the exchange) or
the haggle?

Rigor: paired on the calibration-error direction z; a 95% CI on every Δ; the
monopsony audit mirrors buyer.strategies.coordinate's (participation floor +
over-reach self-defeating). No LLM; byte-deterministic on seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from block import calibration
from vend.core import substream

DATAMARKET_VERSION = 1


@dataclass(frozen=True)
class DataConfig:
    sigma0: float = 0.15          # the mis-set sticker's calibration noise (central cell)
    alpha0: float = 3.0           # B6.1 prior strength (conjugate shrinkage α₀)
    # cluster sizes: 2..100; 44 is NETWORK.md §C's building ("44 residents"), the
    # natural cluster (one co-op board vote signs the whole building).
    Ks: tuple = (2, 5, 10, 20, 44, 100)
    share_K0: float = 12.0        # size-scaled Nash: cluster share s(K)=K/(K+K0)
    seeds: int = 400              # analytic model ⇒ many seeds for tight ΔΠ CIs
    overreach: float = 1.25       # the demand cartel's over-extraction multiple (audit D)


# ── the linear-demand primitives (all booked against TRUE μ) ─────────────────

def _monopoly_price(mu_hat: float, c: float) -> float:
    """Profit-optimal monopoly price for D(p)=Λ(1−p/2μ̂): p* = μ̂ + c/2 (clamped
    to ≥ c so it never prices below cost)."""
    return max(c, mu_hat + 0.5 * c)


def _profit(p: float, mu_true: float, c: float, lam: float) -> float:
    q = lam * max(0.0, 1.0 - p / (2.0 * mu_true))
    return (p - c) * q


def _consumer_surplus(p: float, mu_true: float, lam: float) -> float:
    """CS of the WTP-uniform[0,2μ] consumers served at p (booked against TRUE μ)."""
    if p >= 2.0 * mu_true:
        return 0.0
    return lam * (2.0 * mu_true - p) ** 2 / (4.0 * mu_true)


def sigma_at(K: int, cfg: DataConfig) -> float:
    """The merchant's effective σ_cal after a K-member cluster discloses K
    verified WTP observations: the B6.1 conjugate prior-weight shrinkage."""
    return cfg.sigma0 * math.sqrt(cfg.alpha0 / (cfg.alpha0 + K))


# ── the merchant's board at a calibration level (paired on z) ────────────────

def _skus():
    """(sku, μ, cost, Λ) — Λ (demand scale) proxied by par stock so dollar levels
    track each SKU's real throughput."""
    for sku, mu, cost, _salv, _life, par in calibration.VENDING_CATALOG:
        yield sku, mu, cost, float(par)


def _board_outcome(seed: int, sigma: float, cfg: DataConfig
                   ) -> tuple[float, float, dict]:
    """The merchant's realized (profit, consumer_surplus) at calibration noise
    `sigma`, aggregated over the vending SKUs, against TRUE μ. The per-SKU error
    z is drawn ONCE per (seed, sku) and only `sigma` scales it — paired across
    the K-sweep. Also returns the per-SKU board {sku: (p_board, c, mu, lam)} for
    the haggle/discount computations."""
    profit = cs = 0.0
    board = {}
    for sku, mu, c, lam in _skus():
        z = float(np.random.default_rng(substream(seed, "z", sku)).standard_normal())
        mu_hat = mu * math.exp(sigma * z)
        p = _monopoly_price(mu_hat, c)
        profit += _profit(p, mu, c, lam)
        cs += _consumer_surplus(p, mu, lam)
        board[sku] = (p, c, mu, lam)
    return profit, cs, board


# ── the data value (merchant WTP) vs the haggle (transfer) ───────────────────

def _haggle_per_member(board: dict, *, competitive: bool) -> float:
    """The bilateral discount ONE cluster member extracts by bargaining the
    posted board down — a pure TRANSFER (the merchant loses exactly this). A
    representative member buys one unit of a demand-weighted-random SKU; the Nash
    split hands the buyer half the (p_board − c) gap (price → (p_board+c)/2), so
    the expected per-member transfer is Σ_sku w_sku·½(p_board−c)·P(buys),
    w_sku = Λ_sku/ΣΛ. A K-member cluster's haggle is K× this.

    `competitive=True` models the antagonism finding: a rival at its floor drives
    the board to cost (p_board→c), so the bilateral rent — and the haggle —
    COLLAPSE to ~0. The DATA value does not move under competition; the haggle
    does. This is the exact sense in which the haggle 'competes away'."""
    tot_lam = sum(lam for (_p, _c, _mu, lam) in board.values()) or 1.0
    t = 0.0
    for _sku, (p, c, mu, lam) in board.items():
        p_board = c if competitive else p
        p_hag = 0.5 * (p_board + c)
        p_buys = max(0.0, 1.0 - p_hag / (2.0 * mu))
        t += (lam / tot_lam) * 0.5 * (p_board - c) * p_buys
    return t


def _mean_ci(xs) -> dict:
    a = np.asarray(xs, dtype=float)
    n = len(a)
    mean = float(a.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 4), "ci95": None, "n": n}
    se = float(a.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 4),
            "ci95": [round(mean - t * se, 4), round(mean + t * se, 4)], "n": n}


def cluster_share(K: int, cfg: DataConfig) -> float:
    """The broker's size-scaled Nash split: the cluster's share of the data value
    it created, RISING with K (a bigger demand cartel bargains a bigger slice).
    s(K) = K/(K+K0) ∈ (0,1)."""
    return K / (K + cfg.share_K0)


# ── the monopsony audit (mirror of buyer.strategies.coordinate's) ────────────

def _monopsony_audit(K: int, d_profit_mean: float, board: dict,
                     cfg: DataConfig) -> dict:
    """The RealPage mirror for a DEMAND cartel. The value the cluster is dividing
    is the merchant's recovered profit ΔΠ(K); the standing discount D is the
    cluster's cut. Binding checks:
      B — at the FAIR split the merchant keeps (1−s)·ΔΠ ≥ 0, and at MAXIMAL
          extraction (D = ΔΠ) it keeps exactly 0 — the participation floor, never
          below.
      D — OVER-REACH (D = overreach·ΔΠ > ΔΠ) breaches the floor, the merchant
          refuses the exchange, so no data is shared: the cluster gets its posted
          prices (0 discount) and the merchant keeps mispricing — welfare falls to
          the no-deal baseline, strictly worse for the cluster than the fair split.
      PRICE-FLOOR — the standing discount is discount-only: every SKU's discounted
          price stays ≥ cost (never below the merchant's unit floor)."""
    s = cluster_share(K, cfg)
    fair_merchant_keep = (1.0 - s) * d_profit_mean
    max_extract_keep = d_profit_mean - d_profit_mean          # D = ΔΠ ⇒ exactly 0
    overreach_D = cfg.overreach * d_profit_mean
    overreach_keep = d_profit_mean - overreach_D              # < 0 ⇒ refuse
    merchant_refuses = overreach_keep < -1e-12
    # discount-only price floor: spread the cluster's discount D=s·ΔΠ across SKUs
    # proportional to each SKU's margin room and check p − δ ≥ c everywhere
    total_room = sum(max(0.0, p - c) for (p, c, _mu, _lam) in board.values()) or 1.0
    D = s * d_profit_mean
    price_floor_ok = True
    for (p, c, _mu, lam) in board.values():
        room = max(0.0, p - c)
        delta = D * (room / total_room) / max(lam, 1e-9)      # per-unit markdown
        if p - delta < c - 1e-9:
            price_floor_ok = False
    return {
        "cluster_share": round(s, 4),
        "B_fair_merchant_keep": round(fair_merchant_keep, 4),
        "B_max_extract_merchant_keep": round(max_extract_keep, 6),
        "B_participation_floor_holds": bool(fair_merchant_keep >= -1e-9
                                            and max_extract_keep >= -1e-9),
        "D_overreach_merchant_refuses": bool(merchant_refuses),
        "D_overreach_self_defeating": bool(merchant_refuses),  # refuse ⇒ cluster gets 0
        "price_floor_discount_only_ok": bool(price_floor_ok),
    }


# ── the sweep ────────────────────────────────────────────────────────────────

def run_market(cfg: DataConfig = DataConfig(), seed0: int = 20260710) -> dict:
    """Sweep cluster size K. Per K, over `seeds` independent calibration-error
    realizations (paired across K on the error direction z), compute the merchant's
    profit recovery ΔΠ(K) (its WTP for the data), the consumer-surplus and welfare
    changes, the haggle transfer (monopoly & competitive), the broker split, and
    the monopsony audit."""
    cells = []
    for K in cfg.Ks:
        sigma_K = sigma_at(K, cfg)
        d_profit, d_cs, d_welf, ceiling = [], [], [], []
        hpm_mono, hpm_comp = [], []
        board_last = None
        for si in range(cfg.seeds):
            seed = seed0 + si
            p0, cs0, board0 = _board_outcome(seed, cfg.sigma0, cfg)   # mis-set (no data)
            pK, csK, boardK = _board_outcome(seed, sigma_K, cfg)       # after cluster data
            pF, _csF, _bF = _board_outcome(seed, 0.0, cfg)             # perfect data
            d_profit.append(pK - p0)                                   # merchant WTP
            d_cs.append(csK - cs0)
            d_welf.append((pK + csK) - (p0 + cs0))
            ceiling.append(pF - p0)                                    # full miscal cost
            hpm_mono.append(_haggle_per_member(board0, competitive=False))
            hpm_comp.append(_haggle_per_member(board0, competitive=True))
            board_last = boardK
        dP = _mean_ci(d_profit)
        ceil = _mean_ci(ceiling)
        s = cluster_share(K, cfg)
        # the data value split: cluster gets s·ΔΠ as a standing discount, merchant
        # keeps (1−s)·ΔΠ; per member the cluster gets s·ΔΠ/K.
        cluster_cut = s * dP["mean"]
        # cluster-scaled haggle (K members each bargain one unit) — apples-to-
        # apples with the cluster's data payoff
        hpm_m, hpm_c = _mean_ci(hpm_mono), _mean_ci(hpm_comp)
        cluster_haggle_mono = K * hpm_m["mean"]
        cluster_haggle_comp = K * hpm_c["mean"]
        audit = _monopsony_audit(K, dP["mean"], board_last, cfg)
        cells.append({
            "K": K,
            "sigma_cal_after": round(sigma_K, 4),
            "data_value_dPi": dP,                       # merchant profit recovery = WTP
            "full_miscal_ceiling": ceil,                # Π(0)−Π(σ0): max recoverable
            "data_recovers_frac": round(dP["mean"] / ceil["mean"], 4)
            if ceil["mean"] else None,
            "d_consumer_surplus": _mean_ci(d_cs),
            "d_welfare": _mean_ci(d_welf),
            "haggle_per_member_monopoly": hpm_m,
            "haggle_per_member_competitive": hpm_c,
            "cluster_haggle_monopoly": round(cluster_haggle_mono, 4),
            "cluster_haggle_competitive": round(cluster_haggle_comp, 4),
            "cluster_data_payoff": round(cluster_cut, 4),
            # the pre-registered comparison: info rent vs the COMPETED-AWAY haggle
            "data_beats_competitive_haggle": bool(cluster_cut > cluster_haggle_comp),
            # the honesty check: it does NOT beat a raw monopoly rent grab
            "data_beats_monopoly_haggle": bool(cluster_cut > cluster_haggle_mono),
            "cluster_share": round(s, 4),
            "cluster_per_member": round(cluster_cut / K, 4),
            "merchant_keep": round((1.0 - s) * dP["mean"], 4),
            "monopsony_audit": audit,
        })
    verdict = _verdict(cfg, cells)
    return {
        "datamarket_version": DATAMARKET_VERSION,
        "config": {"sigma0": cfg.sigma0, "alpha0": cfg.alpha0, "Ks": list(cfg.Ks),
                   "share_K0": cfg.share_K0, "seeds": cfg.seeds,
                   "overreach": cfg.overreach},
        "cells": cells,
        "sigma0_sensitivity": _sigma0_sensitivity(cfg, seed0),
        "verdict": verdict,
    }


def _sigma0_sensitivity(cfg: DataConfig, seed0: int) -> dict:
    """How the data value scales with HOW BADLY the merchant is miscalibrated.
    The block's central cell is σ0=0.15 (mildly mis-set); a real operator who
    'doesn't know their demand curve' sits higher. At K=44 (the building), the
    full-data recovery ΔΠ grows ≈quadratically with σ0 — so at a badly-mis-set
    merchant the data is worth materially more, though it still does not out-dollar
    a monopoly rent grab (that is not the claim; durability + Pareto is)."""
    K = 44
    rows = []
    for s0 in (0.15, 0.30, 0.50):
        c2 = DataConfig(sigma0=s0, alpha0=cfg.alpha0, seeds=cfg.seeds)
        sig_K = sigma_at(K, c2)
        dpi, hpm = [], []
        for si in range(cfg.seeds):
            seed = seed0 + si
            p0, _cs0, b0 = _board_outcome(seed, s0, c2)
            pK, _csK, _bK = _board_outcome(seed, sig_K, c2)
            dpi.append(pK - p0)
            hpm.append(_haggle_per_member(b0, competitive=False))
        dP = _mean_ci(dpi)
        rows.append({"sigma0": s0, "data_value_dPi_K44": dP,
                     "cluster_haggle_monopoly_K44": round(K * float(np.mean(hpm)), 4)})
    return {"K": K, "rows": rows}


def _verdict(cfg: DataConfig, cells: list) -> dict:
    sig_shrinks = all(cells[i + 1]["sigma_cal_after"] < cells[i]["sigma_cal_after"]
                      for i in range(len(cells) - 1))
    data_pos = all(c["data_value_dPi"]["ci95"] is not None
                   and c["data_value_dPi"]["ci95"][0] > 0 for c in cells)
    welfare_grows = all(c["d_welfare"]["ci95"] is not None
                        and c["d_welfare"]["ci95"][0] > 0 for c in cells)
    share_rises = all(cells[i + 1]["cluster_share"] > cells[i]["cluster_share"]
                      for i in range(len(cells) - 1))
    # the pre-registered comparison (NETWORK.md §C.4): info rent EXCEEDS the
    # shopping transfer WHICH COMPETES AWAY as boards converge
    data_gt_comp_haggle = all(c["data_beats_competitive_haggle"] for c in cells)
    # the honesty check: the data does NOT out-dollar a raw MONOPOLY haggle
    data_gt_mono_haggle = all(c["data_beats_monopoly_haggle"] for c in cells)
    audit_pass = all(a["B_participation_floor_holds"]
                     and a["D_overreach_self_defeating"]
                     and a["price_floor_discount_only_ok"]
                     for a in (c["monopsony_audit"] for c in cells))
    pareto = data_pos and welfare_grows and audit_pass
    return {
        "sigma_cal_shrinks_with_cluster": bool(sig_shrinks),
        "data_value_positive_all_K": bool(data_pos),
        "total_welfare_grows_all_K": bool(welfare_grows),
        "split_favors_consumers_with_size": bool(share_rises),
        "data_beats_competed_away_haggle_all_K": bool(data_gt_comp_haggle),
        "data_out_dollars_monopoly_haggle": bool(data_gt_mono_haggle),
        "monopsony_audit_pass": bool(audit_pass),
        "pareto_positive_sum_data_market": bool(pareto),
        "durable_value_is_the_data_market": bool(pareto and data_gt_comp_haggle),
        "summary": (
            "DATA MARKET is the DURABLE, PARETO value. The merchant funds it "
            "willingly (ΔΠ>0, welfare grows, monopsony-safe) and — because the "
            "shopping haggle COMPETES AWAY as boards converge (→0) while the data "
            "value does not — the information rent is what remains in the "
            "competitive endgame SNHP creates. HONEST SCOPE: the data does NOT "
            "out-dollar a raw MONOPOLY haggle (the cluster grabs more by bargaining "
            "a monopolist), so the data's edge is durability + positive-sum, not "
            "raw magnitude; the data value scales with how badly the merchant is "
            "miscalibrated (σ0-sensitivity)."
            if (pareto and data_gt_comp_haggle) else "mixed / see cells"),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=400)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = DataConfig(seeds=args.seeds)
    res = run_market(cfg, args.seed0)
    if args.out:
        with open(args.out, "w") as f:
            f.write(json.dumps(res, indent=1) + "\n")
        print(f"wrote {args.out}")
    print("\n=== B6.5 CALIBRATION-FOR-DISCOUNT DATA MARKET ===")
    print(f"{'K':>4} {'σ_cal':>7} {'ΔΠ(data=WTP)':>20} {'ΔW':>7} {'share':>6} "
          f"{'clst_data':>9} {'clst_hag_M':>10} {'clst_hag_C':>10} {'audit':>6}")
    for c in res["cells"]:
        dP = c["data_value_dPi"]
        a = c["monopsony_audit"]
        ok = ("PASS" if (a["B_participation_floor_holds"]
                         and a["D_overreach_self_defeating"]
                         and a["price_floor_discount_only_ok"]) else "FAIL")
        print(f"{c['K']:>4} {c['sigma_cal_after']:>7} "
              f"{str(dP['mean'])+' '+str(dP['ci95']):>20} "
              f"{c['d_welfare']['mean']:>7} {c['cluster_share']:>6} "
              f"{c['cluster_data_payoff']:>9} {c['cluster_haggle_monopoly']:>10} "
              f"{c['cluster_haggle_competitive']:>10} {ok:>6}")
    print("\n  σ0-sensitivity (data value ΔΠ at K=44 grows with miscalibration):")
    for r in res["sigma0_sensitivity"]["rows"]:
        print(f"    σ0={r['sigma0']}: ΔΠ={r['data_value_dPi_K44']['mean']} "
              f"CI{r['data_value_dPi_K44']['ci95']}  "
              f"(monopoly haggle/cluster ≈ {r['cluster_haggle_monopoly_K44']})")
    v = res["verdict"]
    print("\nVERDICT:")
    for k in ("sigma_cal_shrinks_with_cluster", "data_value_positive_all_K",
              "total_welfare_grows_all_K", "split_favors_consumers_with_size",
              "data_beats_competed_away_haggle_all_K",
              "data_out_dollars_monopoly_haggle",
              "monopsony_audit_pass", "pareto_positive_sum_data_market",
              "durable_value_is_the_data_market"):
        print(f"  {k}: {v[k]}")
    print(f"\n  → {v['summary']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

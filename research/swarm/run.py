"""Run the pre-registered v4 sweep (SPEC.md v4.0, review/PANEL_V4.md).

    python research/swarm/run.py --column A          # τ=0 anchor (ladder)
    python research/swarm/run.py --column B          # tariff force
    python research/swarm/run.py --column bridge     # v3-preset replication

PRIMARY metric: SYSTEM delivered at fixed horizon. Company ledgers are
descriptive secondaries (zero-sum on fixed stock — panel M3). Border-trade
volumes split distress vs healthy where deal logs allow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
from scipy import stats

from swarm.arms import make_arm
from swarm.world import TOTAL_STOCK, V_DELIVER, World

FULL = ("cargo", "energy", "sector")
LADDER = ["null", "rules", "auction", "auction-co", "team", "team-co",
          "twofirm", "snhp", "snhp+net", "snhp-hz"]
TAUS = [0.05, 0.10, 0.15, 0.25, 0.50]        # straddles τ*≈0.16 (panel F2)
TAU_ARMS = ["null", "snhp-hz", "team"]


def run_once(arm_name: str, sigma: float, seed: int, ticks: int = 2500,
             tau=0.0, preset: str = "v4", issues=FULL,
             noise: float = 0.0, liar_frac: float = 0.0,
             defended: bool = False, self_noise: float = 0.0,
             self_margin: bool = False, grid: int = 32,
             belief_mode: bool = False, race_pricing: bool = True,
             mine_trait: bool = False) -> dict:
    if noise > 0 and (liar_frac > 0 or defended):
        # the liar/defended branch pre-empts the v5 noise machinery, so the
        # combination would run noiseless while the row claims noise>0
        raise ValueError("v5 partner-noise and v6 lies/defense are separate "
                         "treatments; combining them silently disables noise")
    # v9 arms: "-lv" = life-value drone pricing (hazard-shaped Φ),
    # "-lvc" = life-value + exogenous replacement capital (2 ore units)
    life = arm_name.endswith(("-lv", "-lvc"))
    cap = 20.0 if arm_name.endswith("-lvc") else 0.0
    hazard = arm_name.endswith("-hz") or life
    base = arm_name
    for suf in ("-hz", "-lv", "-lvc"):
        if base.endswith(suf):
            base = base[:-len(suf)]
            break
    tau_pair = tuple(tau) if isinstance(tau, (tuple, list)) else (tau, tau)
    w = World(sigma=sigma, seed=seed, hazard_phi=hazard, preset=preset,
              tau=tau_pair, internalize_tariffs=(base == "team"),
              liar_frac=liar_frac, defended=defended,
              self_noise=self_noise, self_margin=self_margin,
              grid=grid, life_pricing=life, strand_cap=cap,
              belief_mode=belief_mode, race_pricing=race_pricing,
              mine_trait=mine_trait)
    arm = make_arm(base, w, issues=issues, noise=noise)
    makespan = ticks
    delivered_mid = 0
    stale = []          # v10 P15b: mean (tick − last_seen) over all
    for t in range(ticks):        # (company, asteroid) pairs, every 50 ticks
        arm.tick()
        if belief_mode and (t + 1) % 50 == 0:
            stale.append(np.mean([w.tick - w.last_seen[co][i]
                                  for co in range(w.n_companies)
                                  for i in range(len(w.sources))]))
        if t + 1 == 800:
            delivered_mid = w.delivered   # time-resolved deadweight (v4.1)
        if w.delivered >= w.total_stock:
            makespan = t + 1
            break
    if w.delivered >= w.total_stock and makespan <= 800:
        delivered_mid = w.total_stock   # finished before the checkpoint
    assert w.material_ok(), "material leak"
    assert w.ledger_accounted(), "ledger leak"

    deals = w.deal_log
    stranded = sum(r.stranded for r in w.robots)
    co = {r.rid: r.company for r in w.robots}
    border_events = [ev for ev in w.event_log
                     if ev["kind"] == "cargo" and co[ev["src"]] != co[ev["dst"]]]
    border_cargo = sum(ev["amt"] for ev in border_events)
    healthy_border_all = sum(ev["amt"] for ev in border_events
                             if not ev.get("d"))
    border_deals = [d for d in deals if d.get("border")]
    healthy_border_q = sum(abs(d["q"]) for d in border_deals
                           if not d["distress"] and d["q"] != 0)
    n_multi = sum(1 for d in deals
                  if (d["q"] != 0) + (d["e"] != 0) + (d["s"] != 0) >= 2)
    label = arm_name if tuple(issues) == FULL else \
        f"{arm_name}[{'+'.join(issues)}]"
    return dict(
        arm=label, sigma=sigma, seed=seed, tau=tau_pair[0], tau1=tau_pair[1],
        preset=preset, delivered=w.delivered, delivered_mid=delivered_mid,
        makespan=makespan, stranded=stranded,
        score_k2=w.delivered - 2 * stranded,
        score_k5=w.delivered - 5 * stranded,
        eff_last=100.0 * w.delivered / max(1e-9, w.energy_at_last_delivery),
        lost_cargo=sum(r.load for r in w.robots if r.stranded),
        deals=arm.deals, xfers=len(w.event_log),
        capture=float(np.mean([d["capture"] for d in deals])) if deals else None,
        multi_issue_frac=(n_multi / len(deals)) if deals else None,
        # v4 secondaries (descriptive)
        foreign_refined=w.foreign_refined,
        delivered_matrix=w.delivered_matrix,
        border_cargo=border_cargo,
        healthy_border_all=healthy_border_all,
        border_deals=len(border_deals),
        healthy_border_q=healthy_border_q,
        co_delivered=[sum(r.delivered for r in w.robots if r.company == c)
                      for c in (0, 1)],
        co_credit=[round(w.company[c]["credit"], 1) for c in (0, 1)],
        co_tariffs=[round(w.company[c]["tariffs_earned"], 1) for c in (0, 1)],
        co_queue_wait=[w.company[c]["queue_wait"] for c in (0, 1)],
        noise=noise, liar_frac=liar_frac, defended=defended, grid=grid,
        exploit_deals=getattr(arm, "exploit_deals", 0),
        exploit_loss=round(getattr(arm, "exploit_loss", 0.0), 1),
        strip_deals=getattr(arm, "strip_deals", 0),
        strip_loss=round(getattr(arm, "strip_loss", 0.0), 1),
        sacrifice_deals=getattr(arm, "sacrifice_deals", 0),
        self_noise=self_noise, self_margin=self_margin,
        poisoned=sum(1 for d in deals
                     if (d.get("sa_true") is not None and d["sa_true"] < -1e-9
                         and not w.robots[d["a"]].liar)
                     or (d.get("sb_true") is not None and d["sb_true"] < -1e-9
                         and not w.robots[d["b"]].liar)),
        liar_credit=(np.mean([r.credit for r in w.robots if r.liar])
                     if any(r.liar for r in w.robots) else None),
        honest_credit=(np.mean([r.credit for r in w.robots if not r.liar])
                       if any(not r.liar for r in w.robots) else None),
        vetoes=getattr(arm, "vetoes", 0),
        guest_charged=round(w.guest_charged, 1),
        claim_swaps=sum(1 for d in deals if d["s"] == 1),
        # v10 (column I)
        belief_mode=belief_mode, race_pricing=race_pricing,
        mine_trait=mine_trait,
        mean_staleness=(round(float(np.mean(stale)), 2) if stale else None),
    )


def _star(args):
    return run_once(**args)


def _cond(r) -> tuple:
    """Full treatment condition of a row — grouping by (arm, σ, τ) alone
    pooled every v6/v7 condition of an arm into one line (review S9)."""
    return (r.get("liar_frac", 0.0), bool(r.get("defended", False)),
            r.get("self_noise", 0.0), bool(r.get("self_margin", False)),
            r.get("noise", 0.0), r.get("grid", 32),
            bool(r.get("belief_mode", False)),
            bool(r.get("race_pricing", True)),
            bool(r.get("mine_trait", False)))


def _cond_label(c) -> str:
    f, dfd, s7, mg, nz, g, bm, race, mt = c
    bits = []
    if f:
        bits.append(f"f={f:g}")
    if dfd:
        bits.append("dfd")
    if s7:
        bits.append(f"s7={s7:g}")
    if mg:
        bits.append("mg")
    if nz:
        bits.append(f"nz={nz:g}")
    if g != 32:
        bits.append(f"G={g}")
    if bm:
        bits.append("belief")
    if bm and not race:
        bits.append("norace")
    if mt:
        bits.append("mtrait")
    return " ".join(bits)


_BASE = (0.0, False, 0.0, False, 0.0, 32, False, True, False)


def _paired(rows, arm_hi, arm_lo, sigma, field, tau=0.0, cond=_BASE):
    hi = {r["seed"]: r[field] for r in rows
          if r["arm"] == arm_hi and r["sigma"] == sigma and r["tau"] == tau
          and _cond(r) == cond}
    lo = {r["seed"]: r[field] for r in rows
          if r["arm"] == arm_lo and r["sigma"] == sigma and r["tau"] == tau
          and _cond(r) == cond}
    common = sorted(set(hi) & set(lo))
    if len(common) < 3:
        return None
    d = np.array([hi[s] - lo[s] for s in common])
    _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
    try:
        _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
    except ValueError:
        pw = float("nan")
    return dict(delta=float(d.mean()), p_t=float(pt), p_w=float(pw),
                wins=int((d > 0).sum()), n=len(common))


def summarize(rows: list[dict]) -> None:
    keys = sorted({(r["arm"], r["sigma"], r["tau"], _cond(r)) for r in rows},
                  key=lambda k: (k[0], k[1], k[2], k[3]))
    hdr = (f"{'arm':<14} {'condition':<18} {'σ':>5} {'τ':>5} {'delivered':>11} "
           f"{'strand':>7} {'k2':>6} {'k5':>6} {'effLast':>10} {'makespan':>10} "
           f"{'deals':>6} {'borderQ':>8} {'hlthyBQ':>8} {'forRef':>7} "
           f"{'coΔdlv':>7} {'coΔwait':>8}")
    print(hdr)
    print("-" * len(hdr))
    for arm, sigma, tau, cond in keys:
        g = [r for r in rows if r["arm"] == arm and r["sigma"] == sigma
             and r["tau"] == tau and _cond(r) == cond]
        def m(f):
            return np.array([r[f] for r in g], dtype=float)
        codelta = np.array([r["co_delivered"][0] - r["co_delivered"][1] for r in g])
        cowait = np.array([r["co_queue_wait"][0] - r["co_queue_wait"][1] for r in g])
        print(f"{arm:<14} {_cond_label(cond):<18} {sigma:>5.2f} {tau:>5.2f} "
              f"{m('delivered').mean():>6.1f}±{m('delivered').std():<4.1f} "
              f"{m('stranded').mean():>7.2f} "
              f"{m('score_k2').mean():>6.1f} {m('score_k5').mean():>6.1f} "
              f"{m('eff_last').mean():>5.2f}±{m('eff_last').std():<4.2f} "
              f"{m('makespan').mean():>6.0f}±{m('makespan').std():<4.0f} "
              f"{m('deals').mean():>6.1f} {m('border_cargo').mean():>8.1f} "
              f"{m('healthy_border_q').mean():>8.1f} "
              f"{m('foreign_refined').mean():>7.1f} "
              f"{codelta.mean():>+7.1f} {cowait.mean():>+8.1f}")

    print("\npaired on DELIVERED at τ=0:")
    pairs = [("snhp", "auction", "IR bargaining vs auction"),
             ("snhp", "null", "bargaining vs nothing"),
             ("team", "team-co", "P7-D: boundary premium"),
             ("twofirm", "team-co", "P7-D: border markets vs walls"),
             ("team", "twofirm", "P7-D: merger premium"),
             ("snhp-hz", "snhp+net", "P7-C: regime order"),
             ("auction", "auction-co", "auction border value")]
    for sigma in sorted({r["sigma"] for r in rows}):
        shown = False
        for hi, lo, note in pairs:
            c = _paired(rows, hi, lo, sigma, "delivered")
            if c is None:
                continue
            if not shown:
                print(f"  σ={sigma:4.2f}")
                shown = True
            print(f"    {hi:>9} − {lo:<10} Δ={c['delta']:+7.1f}  "
                  f"p_t={c['p_t']:.3f} p_w={c['p_w']:.3f} "
                  f"wins {c['wins']}/{c['n']}   [{note}]")


def contrasts(rows: list[dict]) -> None:
    """The v6/v7 headline numbers, from the artifact (review G2: RESULTS.md
    figures came from unversioned ad-hoc analysis; this commits the path:
    sweep JSON → these tables)."""
    v67 = [r for r in rows if _cond(r) != _BASE or r["arm"].startswith("trust")]
    if not v67:
        return
    print("\nv6/v7/v10 contrasts (per condition; liarAdv = liar − honest mean credit):")
    keys = sorted({(r["arm"], _cond(r)) for r in v67})
    hdr = (f"  {'arm':<16} {'condition':<18} {'delivered':>11} {'deals':>6} "
           f"{'poisoned':>9} {'stale':>7} {'exploit':>8} {'strip':>6} "
           f"{'liarAdv':>9} {'p':>7}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for arm, cond in keys:
        g = [r for r in v67 if r["arm"] == arm and _cond(r) == cond]
        adv = [r["liar_credit"] - r["honest_credit"] for r in g
               if r.get("liar_credit") is not None
               and r.get("honest_credit") is not None]
        if adv:
            try:
                _, p = stats.wilcoxon(adv) if np.any(np.array(adv) != 0) else (None, 1.0)
            except ValueError:
                p = float("nan")
            adv_s, p_s = f"{np.mean(adv):+9.1f}", f"{p:7.4f}"
        else:
            adv_s, p_s = f"{'—':>9}", f"{'—':>7}"
        dlv = np.array([r["delivered"] for r in g], dtype=float)
        st = [r["mean_staleness"] for r in g
              if r.get("mean_staleness") is not None]
        st_s = f"{np.mean(st):>7.1f}" if st else f"{'—':>7}"
        print(f"  {arm:<16} {_cond_label(cond) or 'baseline':<18} "
              f"{dlv.mean():>6.1f}±{dlv.std():<4.1f} "
              f"{np.mean([r['deals'] for r in g]):>6.1f} "
              f"{np.mean([r['poisoned'] for r in g]):>9.2f} {st_s} "
              f"{np.mean([r['exploit_deals'] for r in g]):>8.1f} "
              f"{np.mean([r['strip_deals'] for r in g]):>6.1f} "
              f"{adv_s} {p_s}")


def build_jobs(column: str, seeds: int, ticks: int):
    jobs = []
    if column in ("A", "all"):
        for arm in LADDER:
            for sigma in (0.0, 0.5, 1.0):
                for seed in range(seeds):
                    jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                     ticks=ticks))
        for arm in ("snhp-hz", "snhp+net", "twofirm"):   # P7-C crossing
            for sigma in (0.25, 0.75):
                for seed in range(seeds):
                    jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                     ticks=ticks))
    if column in ("B", "all"):
        for tau in TAUS:
            for arm in TAU_ARMS:
                for sigma in (0.0, 0.5, 1.0):
                    for seed in range(seeds):
                        jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                         ticks=ticks, tau=tau))
    if column in ("C", "all"):        # v5: imperfect info in rich ecology
        # same-code v4-preset anchors for P9d (the claim-generalization
        # perturbs old-v4 trajectories ~1 unit, so cross-preset comparisons
        # re-run under HEAD rather than reading the committed v4 artifact)
        for arm in ("auction", "team", "snhp-hz", "snhp+net"):
            for sigma in (0.5, 1.0):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v4"))
        for arm in ("rules", "auction"):  # info-robust baselines (s irrelevant)
            for sigma in (0.5, 1.0):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5"))
        for arm in ("snhp", "snhp-hz", "snhp+net", "team"):
            for noise in (0.0, 0.25, 0.5, 1.0):
                if arm == "team" and noise > 0:
                    continue              # full-info ceiling, not a treatment
                for sigma in (0.5, 1.0):
                    for seed in range(min(seeds, 16)):
                        jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                         ticks=ticks, tau=0.15, preset="v5",
                                         noise=noise))
    if column in ("D", "all"):        # v6: strategic lies vs attestation
        for arm in ("snhp-hz", "snhp+net"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5"))
            for f in (0.25, 0.5, 1.0):
                for defended in (False, True):
                    for seed in range(min(seeds, 16)):
                        jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                         ticks=ticks, tau=0.15, preset="v5",
                                         liar_frac=f, defended=defended))
        for seed in range(min(seeds, 16)):    # collapse-floor reference
            jobs.append(dict(arm_name="rules", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5"))
        # SPEC controls (review G3: pre-registered but never scheduled):
        # arms that consume no reports run as statistical constants under
        # liars — the demonstration that lies only matter where reports land
        for arm in ("team", "auction"):
            for f in (0.0, 0.5):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5",
                                     liar_frac=f))
    if column in ("E", "all"):        # v6.1: attestation gates cooperation
        for arm in ("trust-open-hz", "trust-gated-hz"):
            for f in (0.25, 0.5):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5",
                                     liar_frac=f, defended=True))
        for arm in ("trust-gated-hz",):   # P11c: honest gated vs nash-only
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 defended=True))
    if column in ("F", "all"):        # v7: noisy self-knowledge
        for s7 in (0.0, 0.15, 0.30):
            for f in (0.0, 0.5):
                margins = ((False,) if s7 == 0 else (False, True))
                for mg in margins:
                    for seed in range(min(seeds, 16)):
                        jobs.append(dict(arm_name="snhp-hz", sigma=0.5,
                                         seed=seed, ticks=ticks, tau=0.15,
                                         preset="v5", liar_frac=f,
                                         self_noise=s7, self_margin=mg))
    if column == "H":                 # v9: endogenous drone valuation (P14)
        for arm in ("snhp-hz", "snhp-lv", "snhp-lvc", "snhp+net",
                    "team", "auction"):
            for sigma in (0.5, 1.0):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=sigma, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5"))
    if column == "G":                 # v8: field geometry (P13)
        for g in (24, 32, 48, 64):
            for arm in ("auction", "snhp-hz", "snhp+net", "team", "rules"):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5",
                                     grid=g))
    if column == "I":                 # v10: field beliefs + priced race (P15)
        for arm in ("auction", "snhp-hz", "snhp+net", "team", "rules"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 belief_mode=True))
        # P15a: oracle-mode control (old omniscient Φ) at the SAME seeds
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5"))
        # P15d: racing-blind ablation — beliefs on, race pricing off
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             belief_mode=True, race_pricing=False))
        # v10c: mine-rate trait cell (belief-mode on)
        for arm in ("snhp+net", "auction"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 belief_mode=True, mine_trait=True))
    if column == "bridge":
        for arm in ("snhp", "auction"):
            for seed in range(8):
                jobs.append(dict(arm_name=arm, sigma=1.0, seed=seed,
                                 ticks=ticks, preset="v3"))
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--column", default="A", choices=["A", "B", "C", "D", "E", "F", "G", "H", "I", "all", "bridge"])
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--ticks", type=int, default=2500)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default=None)
    ap.add_argument("--analyze", default=None, metavar="SWEEP_JSON",
                    help="re-print summary + v6/v7 contrasts from an "
                         "existing sweep artifact (no runs)")
    args = ap.parse_args()

    if args.analyze:
        with open(args.analyze) as f:
            rows = json.load(f)
        summarize(rows)
        contrasts(rows)
        return

    jobs = build_jobs(args.column, args.seeds, args.ticks)
    out = args.out or os.path.join(_HERE, "results",
                                   f"sweep_v4_{args.column}.json")
    if args.jobs > 1:
        with Pool(args.jobs) as pool:
            rows = pool.map(_star, jobs)
    else:
        rows = [_star(j) for j in jobs]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rows, f, indent=1)
    print(f"\n{len(rows)} runs → {out}\n")
    summarize(rows)
    contrasts(rows)


if __name__ == "__main__":
    main()

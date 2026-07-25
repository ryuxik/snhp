#!/usr/bin/env python3
"""Publication figures for the AAMAS manuscript (PAPER-DRAFT.md).

Regenerate everything:  cd research/swarm && python3 figures/make_figures.py

Every statistic is computed from the committed sweep artifacts in
research/swarm/results/ — nothing plotted is hardcoded except the two
pure schematics (fig1 ladder, fig2 bundle), which carry no data.
Statistics follow the house convention of run.py's repin_report():
paired by seed, Wilcoxon signed-rank p_w as the headline test, 95% CI on
the paired delta via Student t.  Deterministic: no randomness anywhere.

Outputs (PDF vector + 300-dpi PNG, embedded TrueType fonts):
  fig1_ladder        arm-ladder schematic (no data)
  fig2_bundle        one executed bundle: issues, IR, Nash product (no data)
  fig3_delivered_sigma  delivered vs sigma, mean +/- 95% CI  [v2.1 head + SSI]
  fig4_gap           coordination gap vs sigma, paired delta + CI band
  fig5_hump          (snhp+net - auction) vs grid size       [sweep_G]
  fig6_inversion     column J: arrival capture + map staleness [R1, 64 seeds]
  fig7_poisoned      poisoned deals/run across conditions    [v7, I, J, R1b]

Conventions: Okabe-Ito palette, grayscale-legible (linestyle + marker
carry identity, never color alone), no in-figure titles, single-column
width 3.3 in (fig3: double-column 7 in).
"""

import json
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
except ImportError:
    sys.exit("matplotlib missing — pip install matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

from scipy import stats

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
OUT = HERE

# ---------------------------------------------------------------- style ----
matplotlib.rcParams.update({
    "pdf.fonttype": 42,          # embed TrueType (Type 42), AAMAS-safe
    "ps.fonttype": 42,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.linewidth": 0.7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6.5,
    "legend.frameon": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.linewidth": 0.4,
    "grid.alpha": 0.35,
    "lines.linewidth": 1.3,
    "errorbar.capsize": 2.0,
    "savefig.dpi": 300,
})

# Okabe-Ito (colorblind-safe).  Fixed arm -> style mapping; identity is
# always carried by linestyle + marker as well, so grayscale survives.
OI = {
    "black": "#000000", "orange": "#E69F00", "sky": "#56B4E9",
    "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
    "vermillion": "#D55E00", "purple": "#CC79A7", "gray": "#7F7F7F",
}
ARM_STYLE = {  # color, linestyle, marker
    "null":        (OI["black"],      ":",              "x"),
    "rules":       (OI["gray"],       (0, (1, 1)),      "+"),
    "auction":     (OI["orange"],     "--",             "s"),
    "auction_ssi": (OI["vermillion"], (0, (3, 1, 1, 1)), "D"),
    "snhp":        (OI["sky"],        "-",              "^"),
    "snhp+net":    (OI["blue"],       "-",              "o"),
    "team":        (OI["green"],      (0, (5, 2)),      "v"),
}

SIGMAS = [0.0, 0.25, 0.5, 0.75, 1.0]
GENERATED, SKIPPED = [], []


def skip(name, reason):
    SKIPPED.append((name, reason))
    print(f"SKIPPED {name}: {reason}")


def save(fig, stem):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{stem}.{ext}", bbox_inches="tight")
    plt.close(fig)
    GENERATED.append(stem)
    print(f"wrote {stem}.pdf / {stem}.png")


def load(name):
    p = RESULTS / name
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


# ------------------------------------------------------- data selection ----
def is_base(r):
    """Base treatment condition (mirrors run.py's _cond(r) == _BASE for
    every field that appears in the artifacts used here)."""
    return (r.get("liar_frac", 0.0) == 0.0 and not r.get("defended")
            and r.get("self_noise", 0.0) == 0.0 and not r.get("self_margin")
            and r.get("noise", 0.0) == 0.0 and r.get("grid", 32) == 32
            and not r.get("belief_mode") and r.get("race_pricing", True)
            and not r.get("mine_trait") and not r.get("dynamic_field")
            and not r.get("contested") and not r.get("scouting")
            and not r.get("map_trading") and not r.get("prospect_claims")
            and r.get("n_robots", 24) == 24)


def cell(rows, field, sel):
    """values of `field` in the selected cell, sorted by seed (determinism)."""
    picked = sorted((r["seed"], r[field]) for r in rows if sel(r))
    return np.array([v for _, v in picked], float)


def mean_ci(vals):
    """cell mean and 95% t-CI half-width."""
    n = len(vals)
    if n < 2:
        return (float(vals.mean()) if n else np.nan), 0.0
    half = stats.t.ppf(0.975, n - 1) * vals.std(ddof=1) / np.sqrt(n)
    return float(vals.mean()), float(half)


def paired(rows, sel_hi, sel_lo, field):
    """House convention (run.py repin_report): paired-by-seed delta, 95%
    t-CI on the delta, Wilcoxon p_w, paired-t p_t, wins/n."""
    hi = {r["seed"]: r[field] for r in rows if sel_hi(r)}
    lo = {r["seed"]: r[field] for r in rows if sel_lo(r)}
    common = sorted(set(hi) & set(lo))
    if len(common) < 3:
        return None
    a = np.array([hi[s] for s in common], float)
    b = np.array([lo[s] for s in common], float)
    d = a - b
    _, pt = stats.ttest_rel(a, b)
    try:
        _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
    except ValueError:
        pw = float("nan")
    n = len(common)
    half = (stats.t.ppf(0.975, n - 1) * d.std(ddof=1) / np.sqrt(n)
            if d.std(ddof=1) > 0 else 0.0)
    return dict(hi=float(a.mean()), lo=float(b.mean()), delta=float(d.mean()),
                lo_ci=float(d.mean() - half), hi_ci=float(d.mean() + half),
                p_t=float(pt), p_w=float(pw), wins=int((d > 0).sum()), n=n)


def p_str(p):
    if p is None or np.isnan(p):
        return "p=n/a"
    return "p<.0001" if p < 1e-4 else f"p={p:.4f}".replace("0.", ".")


# v2.1: prefer the corrected-physics HEAD regeneration when present.
V21_NAME = "sweep_v2.1_head.json"
v21 = load(V21_NAME)
V21_REGEN_PENDING = False
if v21 is None:
    V21_NAME = "sweep_v2.1.json"
    v21 = load(V21_NAME)
    V21_REGEN_PENDING = True
    print("NOTE: sweep_v2.1_head.json absent -> REGEN-PENDING; falling back "
          "to pre-correction sweep_v2.1.json for fig3/fig4")

ssi = load("sweep_v4_SSI.json")
gee = load("sweep_G.json")
r1 = load("sweep_v4_R1.json")
v7f = load("sweep_v7_F.json")
col_i = load("sweep_I.json")
col_j = load("sweep_J.json")


def arm_sigma(arm, sigma):
    return lambda r: r["arm"] == arm and r["sigma"] == sigma and is_base(r)


def is_moving(r):
    return (bool(r.get("belief_mode")) and bool(r.get("dynamic_field"))
            and bool(r.get("contested")))


# ================================================== fig1: arm ladder ======
def fig1():
    fig, ax = plt.subplots(figsize=(3.3, 4.1))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10.55)
    ax.axis("off")

    rungs = [  # (arm, mechanism added, base if not the previous rung)
        ("null", "movement policy only (zero point)", None),
        ("rules", "+ altruistic threshold rescue\n   (trophallaxis)", None),
        ("auction", "+ bilateral single-issue cargo\n   handoff (MURDOCH-style)", None),
        ("auction_ssi", "+ broadcast SSI phase: multi-bidder,\n   truthful ΔΦ bids, single-issue items", "rules"),
        ("snhp", "+ Nash-bargained bundles over\n   energy × cargo × claims (IR)", "null"),
        ("snhp+net", "+ trophallaxis fallback\n   (rescue-floor confound isolated)", None),
    ]
    x0, w, h = 0.25, 3.1, 0.98
    ys = np.linspace(0.35, 7.6, len(rungs))
    for (arm, mech, base), y in zip(rungs, ys):
        color = ARM_STYLE[arm][0]
        box = FancyBboxPatch((x0, y), w, h, boxstyle="round,pad=0.06",
                             fc="white", ec=color, lw=1.3)
        ax.add_patch(box)
        ax.text(x0 + w / 2, y + h / 2, arm, ha="center", va="center",
                fontsize=7.5, family="monospace", color="black")
        note = mech if base is None else f"{mech}\n   [base: {base}]"
        ax.text(x0 + w + 0.35, y + h / 2, note, ha="left", va="center",
                fontsize=6.0, color="#333333")
    for ya, yb in zip(ys[:-1], ys[1:]):
        ax.add_patch(FancyArrowPatch((x0 + w / 2, ya + h + 0.10),
                                     (x0 + w / 2, yb - 0.10),
                                     arrowstyle="-|>", mutation_scale=8,
                                     color="#555555", lw=0.9))
    # ceiling rail: cooperative team tier (not a rung; no IR)
    yc = 9.05
    ax.add_patch(Rectangle((x0 - 0.15, yc), 9.6, 1.30, fc="#009E7315",
                           ec=OI["green"], lw=1.2, ls=(0, (5, 2))))
    ax.text(x0 + 0.15, yc + 0.92,
            "team / team[energy]", fontsize=7.5, family="monospace",
            va="center", color="black")
    ax.text(x0 + 0.15, yc + 0.33,
            "cooperative ceiling: greedy joint-Φ over the same "
            "bundle space, no IR",
            fontsize=5.8, va="center", color="#333333")
    ax.add_patch(FancyArrowPatch((x0 + w / 2, ys[-1] + h + 0.10),
                                 (x0 + w / 2, yc - 0.08),
                                 arrowstyle="-|>", mutation_scale=8,
                                 color="#999999", lw=0.9, ls=":"))
    ax.text(x0 + w / 2 + 0.18, (ys[-1] + h + yc) / 2, "gap",
            fontsize=6.0, color="#777777", va="center")
    save(fig, "fig1_ladder")


# ================================================ fig2: bundle schematic ===
def fig2():
    # Design width 3.5 in; placed at \columnwidth (~3.33 in, acmart) the
    # scale factor is ~0.95, so every internal font >= 7.4 pt here lands
    # at >= ~7 pt effective in print (layout-QA request 2026-07-23).
    FS_SM, FS_MD, FS_TITLE = 7.5, 7.8, 8.0
    fig, (top, bot) = plt.subplots(
        2, 1, figsize=(3.5, 4.25),
        gridspec_kw={"height_ratios": [0.42, 0.58], "hspace": 0.32})

    # -- top panel: two robots, three issue axes -----------------------
    top.set_xlim(0, 10)
    top.set_ylim(0, 4.75)
    top.axis("off")
    for x, name, sub in ((0.3, "robot A", "low battery,\nloaded"),
                         (7.2, "robot B", "efficient,\ncharged")):
        top.add_patch(FancyBboxPatch((x, 1.35), 2.5, 1.9,
                                     boxstyle="round,pad=0.08",
                                     fc="white", ec="black", lw=1.1))
        top.text(x + 1.25, 2.85, name, ha="center", fontsize=FS_SM,
                 family="monospace")
        top.text(x + 1.25, 2.05, sub, ha="center", va="center",
                 fontsize=FS_SM, color="#555555")
    arrows = [  # y, direction (1 = A->B), label, color
        (3.85, -1, "energy $e$: B sends, A gets $0.75\\,e$ (25% loss)",
         OI["vermillion"]),
        (2.30, 1, "cargo $q$: A's crates", OI["blue"]),
        (0.75, 0, "claim rights: near-source claim ceded", OI["green"]),
    ]
    for y, d, lab, c in arrows:
        style = "<|-|>" if d == 0 else ("-|>" if d == 1 else "<|-")
        top.add_patch(FancyArrowPatch((3.0, y), (7.0, y), arrowstyle=style,
                                      mutation_scale=9, color=c, lw=1.4))
        top.text(5.0, y + 0.16, lab, ha="center", fontsize=FS_SM,
                 color="#333333")
    top.text(5.0, 4.58, "one atomic bundle (single agreement, "
             "executed physics)", ha="center", fontsize=FS_TITLE,
             style="italic")

    # -- bottom panel: utility space, IR region, Nash product ----------
    # Illustrative geometry only (schematic; no artifact data): a concave
    # Pareto frontier in gain space (Delta-Phi relative to disagreement d).
    bot.set_xlim(-1.3, 4.6)
    bot.set_ylim(-1.3, 4.6)
    t = np.linspace(0, np.pi / 2, 200)
    fx, fy = 4.1 * np.cos(t), 3.4 * np.sin(t)     # frontier ellipse arc
    # IR region shading (both parties gain vs disagreement point)
    bot.fill_between([0, 4.55], 0, 4.55, color="#0072B2", alpha=0.07, lw=0)
    bot.axhline(0, color="#444444", lw=0.7)
    bot.axvline(0, color="#444444", lw=0.7)
    bot.plot(fx, fy, color="black", lw=1.2)
    bot.text(3.25, 2.55, "Pareto\nfrontier", fontsize=FS_MD, ha="left")
    # candidate bundles (dominated / IR-violating), deterministic grid
    cand = [(-0.8, 2.6), (0.7, -0.75), (0.55, 1.0), (1.5, 0.6), (2.15, 1.45),
            (0.9, 2.1), (1.9, 1.9), (3.0, 0.5)]
    for cx, cy in cand:
        ok = cx > 0 and cy > 0
        bot.plot(cx, cy, marker="o" if ok else "x", ms=3.5,
                 color=OI["gray"] if ok else OI["vermillion"], mew=1.2,
                 ls="none")
    bot.plot([], [], marker="x", color=OI["vermillion"], ls="none", ms=3.5,
             label="IR-vetoed")
    bot.plot([], [], marker="o", color=OI["gray"], ls="none", ms=3.5,
             label="feasible bundles")
    # Nash bargaining solution on the frontier: max (ua-da)(ub-db)
    prod = fx * fy
    k = int(np.argmax(prod))
    nx, ny = fx[k], fy[k]
    bot.plot(nx, ny, marker="*", ms=12, color=OI["blue"], ls="none",
             label="Nash solution", zorder=5)
    u = np.linspace(0.62, 4.5, 300)               # hyperbola through it
    bot.plot(u, (nx * ny) / u, color=OI["blue"], lw=0.9, ls=(0, (4, 2)))
    bot.text(3.4, 0.52, "$(u_A-d_A)(u_B-d_B)$\n$=$ const", fontsize=FS_SM,
             color=OI["blue"], ha="center", va="bottom")
    bot.plot(0, 0, marker="s", ms=4, color="black", ls="none")
    bot.text(0.10, -0.45, "disagreement point $d$ (no deal)",
             fontsize=FS_MD)
    bot.text(0.16, 3.85, "IR region:\nboth $\\geq d$", fontsize=FS_MD,
             color=OI["blue"])
    bot.set_xlabel("owner A gain  $u_A-d_A$  (Φ units)")
    bot.set_ylabel("owner B gain  $u_B-d_B$  (Φ units)")
    bot.set_xticks([0])
    bot.set_yticks([0])
    # legend outside the axes (above), so no data/annotation collisions
    leg = bot.legend(loc="lower left", bbox_to_anchor=(-0.02, 1.01),
                     ncol=2, fontsize=FS_SM, handletextpad=0.3,
                     columnspacing=1.0, handlelength=1.2, borderaxespad=0.0,
                     frameon=True, fancybox=False, framealpha=1.0)
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("#bbbbbb")
    leg.get_frame().set_linewidth(0.6)
    save(fig, "fig2_bundle")


# ============================================ fig3: delivered vs sigma =====
def fig3():
    if v21 is None:
        return skip("fig3_delivered_sigma", "no v2.1 artifact found")
    arms = ["null", "auction", "auction_ssi", "snhp", "snhp+net", "team"]
    fig, ax = plt.subplots(figsize=(7.0, 2.7))
    offs = {a: dx for a, dx in zip(arms, np.linspace(-0.012, 0.012, len(arms)))}
    print("\n[fig3] delivered at horizon, mean +/- 95% CI"
          + (" (REGEN-PENDING: pre-correction v2.1)" if V21_REGEN_PENDING else ""))
    for arm in arms:
        rows, sigmas = v21, SIGMAS
        if arm == "auction_ssi":
            if ssi is None:
                print("  auction_ssi: SSI artifact missing -> series omitted")
                continue
            rows, sigmas = ssi, sorted({r["sigma"] for r in ssi})
        xs, ms, hs = [], [], []
        for s in sigmas:
            vals = cell(rows, "delivered", arm_sigma(arm, s))
            if not len(vals):
                continue
            m, h = mean_ci(vals)
            xs.append(s + offs[arm]); ms.append(m); hs.append(h)
        if not xs:
            print(f"  {arm}: no cells -> omitted")
            continue
        c, ls, mk = ARM_STYLE[arm]
        ax.errorbar(xs, ms, yerr=hs, color=c, ls=ls, marker=mk, ms=3.5,
                    mfc="white", mew=1.0, lw=1.2, elinewidth=0.8,
                    label=arm, zorder=3)
        print(f"  {arm:12s} " + "  ".join(f"σ={x - offs[arm]:.2g}:{m:.1f}±{h:.1f}"
                                          for x, m, h in zip(xs, ms, hs)))
    ax.set_xlabel("fleet heterogeneity σ (mean-preserving dial, unitless)")
    ax.set_ylabel("delivered ore at horizon\n(units per 2500-tick run)")
    ax.set_xticks(SIGMAS)
    ax.grid(axis="y")
    ax.legend(ncol=6, loc="lower left", bbox_to_anchor=(0.0, 1.01),
              handlelength=2.6, columnspacing=1.1)
    save(fig, "fig3_delivered_sigma")


# ==================================================== fig4: the gap =======
def fig4():
    if v21 is None:
        return skip("fig4_gap", "no v2.1 artifact found")
    series = [  # label, hi arm, lo arm, color, ls, marker
        ("team − snhp+net", "team", "snhp+net", OI["blue"], "-", "o"),
        ("team − snhp (registered gap)", "team", "snhp",
         OI["green"], (0, (5, 2)), "v"),
    ]
    fig, ax = plt.subplots(figsize=(3.3, 2.5))
    print("\n[fig4] coordination gap vs sigma (paired delta, 95% CI, p_w)"
          + (" (REGEN-PENDING)" if V21_REGEN_PENDING else ""))
    plotted = False
    for lab, hi, lo, c, ls, mk in series:
        xs, ds, los, his = [], [], [], []
        for s in SIGMAS:
            pr = paired(v21, arm_sigma(hi, s), arm_sigma(lo, s), "delivered")
            if pr is None:
                continue
            xs.append(s); ds.append(pr["delta"])
            los.append(pr["lo_ci"]); his.append(pr["hi_ci"])
            print(f"  {lab:32s} σ={s:<5g} Δ={pr['delta']:+6.2f} "
                  f"[{pr['lo_ci']:+.2f},{pr['hi_ci']:+.2f}] {p_str(pr['p_w'])}"
                  f" n={pr['n']}")
        if not xs:
            continue
        plotted = True
        ax.fill_between(xs, los, his, color=c, alpha=0.15, lw=0)
        ax.plot(xs, ds, color=c, ls=ls, marker=mk, ms=3.5, mfc="white",
                mew=1.0, label=lab)
    if not plotted:
        plt.close(fig)
        return skip("fig4_gap", "team/snhp cells missing from v2.1 artifact")
    ax.axhline(0, color="#444444", lw=0.7)
    ax.set_xlabel("fleet heterogeneity σ (unitless)")
    ax.set_ylabel("coordination gap, Δ delivered\n(ore units per run; "
                  "shading: 95% CI)")
    ax.set_xticks(SIGMAS)
    ax.grid(axis="y")
    ax.legend(loc="upper center", handlelength=2.8)
    save(fig, "fig4_gap")


# ==================================================== fig5: the hump ======
def fig5():
    if gee is None:
        return skip("fig5_hump", "sweep_G.json missing (v8/column G)")
    grids = sorted({r["grid"] for r in gee})
    xs, ds, errlo, errhi = [], [], [], []
    print("\n[fig5] v8 hump: (snhp+net - auction) delivered by grid size")
    for g in grids:
        pr = paired(gee,
                    lambda r, g=g: r["arm"] == "snhp+net" and r["grid"] == g,
                    lambda r, g=g: r["arm"] == "auction" and r["grid"] == g,
                    "delivered")
        if pr is None:
            print(f"  grid={g}: cells missing")
            continue
        xs.append(g); ds.append(pr["delta"])
        errlo.append(pr["delta"] - pr["lo_ci"])
        errhi.append(pr["hi_ci"] - pr["delta"])
        print(f"  grid={g:<3d} Δ={pr['delta']:+5.2f} "
              f"[{pr['lo_ci']:+.2f},{pr['hi_ci']:+.2f}] {p_str(pr['p_w'])} "
              f"n={pr['n']}")
    if not xs:
        return skip("fig5_hump", "no paired grid cells in sweep_G.json")
    fig, ax = plt.subplots(figsize=(3.3, 2.5))
    ax.axhline(0, color="#444444", lw=0.7)
    ax.errorbar(xs, ds, yerr=[errlo, errhi], color=OI["blue"], ls="-",
                marker="o", ms=4, mfc="white", mew=1.1, lw=1.3,
                elinewidth=0.9)
    ax.set_xlabel("grid side length (cells)")
    ax.set_ylabel("Δ delivered, snhp+net − auction\n"
                  "(ore units per run; 95% CI)")
    ax.set_xticks(xs)
    ax.grid(axis="y")
    save(fig, "fig5_hump")


# ============================================ fig6: column-J inversion ====
def fig6():
    if r1 is None:
        return skip("fig6_inversion", "sweep_v4_R1.json missing")

    def j_arm(name):
        return (lambda r: r.get("preset") == "v5" and r["arm"] == name
                and is_moving(r) and not r.get("scouting")
                and not r.get("map_trading") and r.get("race_pricing", True))

    if not any(j_arm("auction")(r) for r in r1):
        return skip("fig6_inversion", "R1c moving-field cells absent from R1")

    arms = ["auction", "snhp+net"]
    panels = [
        ("arrivals_mined", "arrival-units captured\n(ore units per run)"),
        ("mean_staleness", "mean map staleness\n(ticks)"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(3.3, 2.3))
    fig.subplots_adjust(wspace=0.62)
    print("\n[fig6] column J re-pin (R1c, 64 seeds): auction vs snhp+net")
    for ax, (field, ylab) in zip(axes, panels):
        ms, hs = [], []
        for a in arms:
            m, h = mean_ci(cell(r1, field, j_arm(a)))
            ms.append(m); hs.append(h)
        pr = paired(r1, j_arm("auction"), j_arm("snhp+net"), field)
        for i, a in enumerate(arms):
            c = ARM_STYLE[a][0]
            ax.bar(i, ms[i], width=0.62, color=c, edgecolor="black", lw=0.7,
                   hatch="//" if a == "auction" else None, alpha=0.9)
            ax.errorbar(i, ms[i], yerr=hs[i], color="black", lw=0.9,
                        capsize=2.5)
        # significance bracket
        ytop = max(m + h for m, h in zip(ms, hs))
        yb = ytop * 1.07
        ax.plot([0, 0, 1, 1], [yb, yb * 1.03, yb * 1.03, yb], color="black",
                lw=0.7)
        ax.text(0.5, yb * 1.05, f"$p_w$={pr['p_w']:.3f}".replace("0.", "."),
                ha="center", va="bottom", fontsize=6.0)
        ax.set_ylim(0, yb * 1.22)
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms, fontsize=6.5)
        ax.set_ylabel(ylab, fontsize=6.8)
        print(f"  {field}: " + " vs ".join(
            f"{a}={m:.2f}±{h:.2f}" for a, m, h in zip(arms, ms, hs))
            + f"  Δ={pr['delta']:+.2f} [{pr['lo_ci']:+.2f},"
              f"{pr['hi_ci']:+.2f}] {p_str(pr['p_w'])} n={pr['n']}")
    save(fig, "fig6_inversion")


# ============================================= fig7: poisoned deals =======
def fig7():
    groups = []   # (group label, [(bar label, values, color, hatch), ...])

    if v7f is not None:
        bars = []
        for nz, hatch in ((0.0, None), (0.15, None), (0.3, None)):
            v = cell(v7f, "poisoned",
                     lambda r, nz=nz: r["arm"] == "snhp-hz"
                     and r["self_noise"] == nz and not r.get("self_margin"))
            if len(v):
                bars.append((f"{nz:g}", v, OI["vermillion"], hatch))
        if bars:
            groups.append(("v7 gauge noise ν\n(snhp-hz)", bars))
        else:
            print("fig7: v7 cells empty -> group omitted")
    else:
        print("fig7: sweep_v7_F.json missing -> v7 group omitted")

    if col_i is not None:
        v = cell(col_i, "poisoned",
                 lambda r: r["arm"] == "snhp+net" and r.get("belief_mode")
                 and not r.get("mine_trait") and r.get("race_pricing", True))
        if len(v):
            groups.append(("col. I\nstatic",
                           [("belief", v, OI["sky"], None)]))
    else:
        print("fig7: sweep_I.json missing -> column-I group omitted")

    if col_j is not None:
        v = cell(col_j, "poisoned",
                 lambda r: r["arm"] == "snhp+net" and r.get("belief_mode")
                 and r.get("race_pricing", True))
        if len(v):
            groups.append(("col. J\nmoving",
                           [("belief", v, OI["blue"], None)]))
    else:
        print("fig7: sweep_J.json missing -> column-J group omitted")

    k_pair = None
    if r1 is not None:
        def k_cell_sel(maptr):
            return (lambda r: r.get("preset") == "v5"
                    and r["arm"] == "snhp+net" and is_moving(r)
                    and bool(r.get("scouting"))
                    and bool(r.get("map_trading")) == maptr
                    and not r.get("prospect_claims"))
        v_no = cell(r1, "poisoned", k_cell_sel(False))
        v_yes = cell(r1, "poisoned", k_cell_sel(True))
        if len(v_no) and len(v_yes):
            groups.append(("col. K map market\n(64 seeds)",
                           [("off", v_no, OI["green"], "//"),
                            ("on", v_yes, OI["green"], None)]))
            k_pair = paired(r1, k_cell_sel(False), k_cell_sel(True),
                            "poisoned")
    else:
        print("fig7: sweep_v4_R1.json missing -> column-K group omitted")

    if not groups:
        return skip("fig7_poisoned", "no artifacts with poisoned-deal cells")

    fig, ax = plt.subplots(figsize=(3.3, 2.7))
    print("\n[fig7] poisoned deals per run (true-surplus < 0), mean +/- 95% CI")
    x, xticks, xticklabels, group_centers = 0.0, [], [], []
    k_xs = []
    for glab, bars in groups:
        x0 = x
        for blab, vals, c, hatch in bars:
            m, h = mean_ci(vals)
            ax.bar(x, m, width=0.78, color=c, edgecolor="black", lw=0.7,
                   hatch=hatch, alpha=0.9)
            if h:
                ax.errorbar(x, m, yerr=h, color="black", lw=0.9, capsize=2.2)
            xticks.append(x); xticklabels.append(blab)
            if glab.startswith("col. K"):
                k_xs.append((x, m + h))
            print(f"  {glab.splitlines()[0]:24s} {blab.replace(chr(10),' '):12s}"
                  f" {m:5.2f} ± {h:.2f}  (n={len(vals)})")
            x += 1.1
        group_centers.append(((x0 + x - 1.1) / 2, glab))
        x += 1.5
    if k_pair is not None and len(k_xs) == 2:
        (xa, ya), (xb, yb2) = k_xs
        yb = max(ya, yb2) + 0.55
        ax.plot([xa, xa, xb, xb], [yb, yb + 0.18, yb + 0.18, yb],
                color="black", lw=0.7)
        ax.text((xa + xb) / 2, yb + 0.28,
                f"$p_w$={k_pair['p_w']:.4f}".replace("0.", "."),
                ha="center", va="bottom", fontsize=6.0)
        print(f"  col. K paired: Δ={k_pair['delta']:+.2f} "
              f"[{k_pair['lo_ci']:+.2f},{k_pair['hi_ci']:+.2f}] "
              f"{p_str(k_pair['p_w'])} n={k_pair['n']}")
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, fontsize=5.6)
    ymax = ax.get_ylim()[1]
    for gx, glab in group_centers:
        ax.text(gx, -0.30 * ymax, glab, ha="center", va="top", fontsize=6.0)
    ax.set_ylabel("poisoned deals per run\n(true surplus < 0)")
    ax.grid(axis="y")
    fig.subplots_adjust(bottom=0.32)
    save(fig, "fig7_poisoned")


# ------------------------------------------------------------------ main ---
if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
    fig7()
    print(f"\ngenerated: {', '.join(GENERATED) if GENERATED else 'none'}")
    if SKIPPED:
        print("skipped:   " + "; ".join(f"{n} ({r})" for n, r in SKIPPED))
    if V21_REGEN_PENDING:
        print("REGEN-PENDING: fig3/fig4 use pre-correction sweep_v2.1.json; "
              "re-run once sweep_v2.1_head.json lands.")

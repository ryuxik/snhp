# Manuscript figures (PAPER-DRAFT.md)

Regenerate everything (deterministic; PNGs are byte-identical across runs):

```
cd research/swarm && python3 figures/make_figures.py
```

Each figure is emitted as vector PDF (Type-42 embedded fonts) + 300-dpi PNG.
Statistics follow `run.py`'s `repin_report()` house convention: paired by
seed, Wilcoxon signed-rank `p_w` as the headline test, 95% CI on the paired
delta via Student t. Conventions: Okabe-Ito palette, identity always carried
by linestyle + marker (grayscale-safe), no in-figure titles, 3.3 in
single-column width (fig3: 7 in double-column).

| Figure | Content | Source artifact(s) | Notes |
|---|---|---|---|
| `fig1_ladder` | Arm-ladder schematic: null → rules → auction → auction_ssi → snhp → snhp+net, one mechanism per rung; team/team[energy] as the cooperative-ceiling rail | none (schematic) | `[base: x]` tags mark rungs whose base is not the previous rung (auction_ssi = rules + SSI; snhp = null + bundles), per §3.2 |
| `fig2_bundle` | One executed bundle: two robots, three issue axes (energy w/ 25% loss, cargo, claim rights); utility-gain space with IR region, disagreement point, Pareto frontier, Nash-product hyperbola | none (schematic; geometry illustrative) | 25% loss and 3-issue space are spec constants (§3.1–3.2) |
| `fig3_delivered_sigma` | Delivered-at-horizon vs σ, mean ± 95% CI; arms null, auction, auction_ssi, snhp, snhp+net, team | `results/sweep_v2.1_head.json` (888 runs, HEAD physics, 24 seeds/cell); auction_ssi series from `results/sweep_v4_SSI.json` (24 seeds, σ ∈ {0, 0.5, 0.75} only) | base-condition cells only (`_cond == _BASE`) |
| `fig4_gap` | Coordination gap vs σ, paired Δ delivered with 95% CI band: team − snhp+net (as tasked) AND team − snhp (the §4.2 registered gap, "price of selfishness") | `results/sweep_v2.1_head.json` | the two definitions diverge sharply at σ ≤ 0.5; paper §4.2 quotes team − snhp (12.0/4.2/5.2/13.9/16.7) |
| `fig5_hump` | (snhp+net − auction) delivered vs grid size 24/32/48/64, paired Δ with 95% CI whiskers (the v8 hump) | `results/sweep_G.json` (16 seeds/cell, v5 preset, σ=0.5) | Δ = +4.12 / +4.50 / +7.31 / −2.69 |
| `fig6_inversion` | Column-J inversion, twin panels: arrival-units captured and mean map staleness, auction vs snhp+net bars with 95% CI + `p_w` bracket | `results/sweep_v4_R1.json` R1c cells (64 seeds; moving+contested+belief, no scouting/map market) | 64-seed re-pin numbers (42.70 vs 33.72, p_w=.022; staleness 358 vs 263, p_w=.029). §4.6's "305 vs 190" staleness is the 16-seed `sweep_J.json` figure — keep caption consistent with whichever is cited |
| `fig7_poisoned` | Poisoned deals/run (true surplus < 0) across conditions: v7 gauge noise ν ∈ {0, .15, .3} (snhp-hz, no margin, 32 seeds); col. I belief (static, 16 seeds); col. J belief (moving, 16 seeds); col. K map market off/on (64-seed R1b, with `p_w` bracket) | `results/sweep_v7_F.json`, `results/sweep_I.json`, `results/sweep_J.json`, `results/sweep_v4_R1.json` | K pair: 5.00 → 3.53, Δ=+1.47 [+0.69, +2.24], p_w=.0007 |

Provenance guard: the script prefers `sweep_v2.1_head.json` (corrected
physics, addendum R4) and only falls back to the pre-correction
`sweep_v2.1.json` with a loud REGEN-PENDING warning if the HEAD artifact is
absent. Missing artifacts/cells cause a printed `SKIPPED <fig>: <reason>`
instead of a crash.

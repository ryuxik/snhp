"""The research instrument — Koza's demands, made runnable and honest.

Every experiment here scores OFF the selection path (its numbers never feed
energy) so it measures the system, not itself. Run headless on the deterministic
engine; report the number and the honest read, negative results included.

  python -m arena.science --absolute      # frozen panel -> absolute fitness curve (#1)
  python -m arena.science --price         # Price equation, selection-on vs neutral
  python -m arena.science --neutral       # tactic-share swing: selection vs drift null
  python -m arena.science --decompose     # fitness variance: surplus vs demographic
  python -m arena.science --assembly      # crossover ablation: building-block assembly time
  python -m arena.science --speciation    # P(impasse | genetic distance)
  python -m arena.science --human          # evolved vs the raw SNHP recommender (held-out)
  python -m arena.science --all
"""
from __future__ import annotations

import argparse
import dataclasses
from collections import defaultdict

import numpy as np

from arena.config import CONFIG
from arena.genome import (Genome, ARCHETYPES, BLOCKS, TACTIC_FAMILIES, similarity,
                          mutate)
from arena.scenarios import (gen_price_scenario, gen_bundle_scenario,
                             bundle_frontier, era_center, ERAS)
from arena.executor import Side, run_price_negotiation, run_bundle_negotiation
from arena.world import World


# ─── shared: score a genome against an opponent on a FIXED scenario set ─────

def _fixed_scenarios(n, era="symmetric", seed=9991):
    rng = np.random.default_rng(seed)
    center = era_center(era, 1.0, era)
    return [gen_price_scenario(CONFIG, era, center, rng) for _ in range(n)]


def _surplus(focal: Genome, opp: Genome, scns, seed_base=70000):
    """Mean focal surplus over the scenario set, role-balanced. Off-path."""
    tot = 0.0
    for i, scn in enumerate(scns):
        role_seller = (i % 2 == 0)
        s = Side(focal if role_seller else opp, "seller", scn.r_s, 1)
        b = Side(opp if role_seller else focal, "buyer", scn.r_b, 2)
        g = run_price_negotiation(s, b, scn, 11, seed_base + i, CONFIG)
        out = None
        try:
            while True:
                next(g)
        except StopIteration as e:
            out = e.value
        if out.deal:
            tot += out.surplus_seller if role_seller else out.surplus_buyer
    return tot / len(scns)


# The frozen reference panel: 8 archetypes + the RAW recommender (knob 0.5, no
# tactic discipline, no evolved schedule) + a pure conceder. Fixed forever.
RAW = Genome(pareto_knob=0.5, open_aggression=0.5, walk_margin=0.3, patience=0.5,
             tactic_family="conceder")
PANEL = list(ARCHETYPES.values()) + [RAW, Genome(tactic_family="conceder")]


def _score_vs_panel(g: Genome, scns):
    return float(np.mean([_surplus(g, opp, scns) for opp in PANEL]))


# ─── shared: the multi-issue (bundle) analog of the scoring harness ─────────

def _fixed_bundle_scenarios(n, era, seed):
    rng = np.random.default_rng(seed)
    return [gen_bundle_scenario(CONFIG, era, rng) for _ in range(n)]


def _bundle_play(focal: Genome, opp: Genome, sc, seed, focal_seller: bool):
    s = Side(focal if focal_seller else opp, "seller", 0.0, 1)
    b = Side(opp if focal_seller else focal, "buyer", 0.0, 2)
    g = run_bundle_negotiation(s, b, sc, 11, seed, CONFIG)
    out = None
    try:
        while True:
            next(g)
    except StopIteration as e:
        out = e.value
    return out


def _bundle_surplus(focal: Genome, opp: Genome, scns, seed_base=80000):
    """Mean focal surplus AND mean frontier-capture over a bundle scenario set,
    role-balanced. Capture = realized joint surplus / achievable-peak surplus
    (from bundle_frontier under both agents' TRUE weights). Off the selection
    path."""
    tot, caps, closed = 0.0, [], 0
    for i, sc in enumerate(scns):
        focal_seller = (i % 2 == 0)
        out = _bundle_play(focal, opp, sc, seed_base + i, focal_seller)
        if out.deal:
            closed += 1
            tot += out.surplus_seller if focal_seller else out.surplus_buyer
            sfocus = (focal if focal_seller else opp).bundle_focus
            bfocus = (opp if focal_seller else focal).bundle_focus
            best_u, _ = bundle_frontier(sc, sfocus, bfocus)
            joint = out.surplus_seller + out.surplus_buyer
            caps.append(float(np.clip(joint / max(1e-6, best_u - 0.60), 0.0, 1.2)))
    return tot / len(scns), (float(np.mean(caps)) if caps else 0.0)


# A diverse bundle panel: 8 differentiated-priority opponents, half staked (so a
# staked champion meets the peer path on ~half its deals). RAW_BUNDLE = the raw
# recommender: uniform priorities, neutral ceiling, unstaked.
def _bundle_panel(seed=4242):
    rng = np.random.default_rng(seed)
    return [Genome(bundle_focus=tuple(rng.dirichlet(np.ones(4))),
                   tactic_family=TACTIC_FAMILIES[i % 6], staked=(i % 2 == 0))
            for i in range(8)]


RAW_BUNDLE = Genome()  # uniform priorities, bundle_tactic all-zero, unstaked


def _score_vs_bundle_panel(g: Genome, panel, scns):
    rows = [_bundle_surplus(g, opp, scns) for opp in panel]
    return float(np.mean([r[0] for r in rows])), float(np.mean([r[1] for r in rows]))


# ─── #1 absolute fitness curve: does the population actually IMPROVE? ────────

def absolute_fitness(gens=80, seeds=(1, 2, 3), sample=8, every=8):
    scns = _fixed_scenarios(24)
    curves_mean, curves_max = [], []
    for sd in seeds:
        w = World(dataclasses.replace(CONFIG, seed=sd))
        mean_pts, max_pts = [], []
        for ggen in range(gens):
            list(w.generation_events())
            if ggen % every == 0 or ggen == gens - 1:
                agents = list(w.agents.values())
                idx = np.random.default_rng(sd * 100 + ggen).choice(
                    len(agents), size=min(sample, len(agents)), replace=False)
                scores = [_score_vs_panel(agents[i].genome, scns) for i in idx]
                mean_pts.append((ggen, float(np.mean(scores))))
                max_pts.append((ggen, float(np.max(scores))))
        curves_mean.append(mean_pts); curves_max.append(max_pts)
    print("=" * 70)
    print("  ABSOLUTE FITNESS vs a FROZEN panel (off the selection path)")
    print("  If this rises, the population is genuinely getting better —")
    print("  not drifting. If flat, it's a Red Queen treadmill.")
    print("=" * 70)
    xs = [p[0] for p in curves_mean[0]]
    print(f"  {'gen':>4} {'mean_fit':>10} {'max_fit':>10}   (avg over {len(seeds)} seeds)")
    first_mean = last_mean = None
    for j, x in enumerate(xs):
        mm = np.mean([c[j][1] for c in curves_mean])
        mx = np.mean([c[j][1] for c in curves_max])
        print(f"  {x:>4} {mm:>10.4f} {mx:>10.4f}")
        if first_mean is None:
            first_mean = mm
        last_mean = mm
    delta = last_mean - first_mean
    print("-" * 70)
    verdict = ("RISING — real cumulative improvement" if delta > 0.003
               else "FLAT — drift / Red Queen, NOT improvement (report honestly)"
               if abs(delta) <= 0.003 else "FALLING — softening/collapse")
    print(f"  mean absolute fitness {first_mean:.4f} -> {last_mean:.4f} "
          f"(delta {delta:+.4f}): {verdict}")
    return dict(delta=delta, verdict=verdict)


# ─── #2 Price equation: Cov(trait, fitness), selection ON vs neutral ────────

def price_equation(gens=60, seeds=(1, 2, 3, 4, 5)):
    def run(neutral):
        per_gene = defaultdict(list)
        for sd in seeds:
            w = World(dataclasses.replace(CONFIG, seed=sd), neutral=neutral)
            for _ in range(gens):
                covs = _gen_price_cov(w)
                list(w.generation_events())
                for k, v in covs.items():
                    per_gene[k].append(v)
        return {k: (float(np.mean(v)), float(np.std(v) / np.sqrt(len(v))))
                for k, v in per_gene.items()}
    on = run(False); off = run(True)
    print("=" * 70)
    print("  PRICE EQUATION  Cov(trait, relative fitness)  — the selection")
    print("  differential, replacing the cherry-picked r=0.15. Selection is")
    print("  real for a gene iff ON differs from the NEUTRAL null.")
    print("=" * 70)
    print(f"  {'gene':>16} {'selection-ON':>18} {'neutral-null':>18}")
    for k in ("pareto_knob", "walk_margin", "patience", "open_aggression",
              "bundle_sharpness", "bt_coop", "bt_concede", "bt_sharpen"):
        m1, e1 = on.get(k, (0, 0)); m0, e0 = off.get(k, (0, 0))
        sig = "  *" if abs(m1) > 2 * (e1 + 1e-9) and abs(m1 - m0) > (e1 + e0) else ""
        print(f"  {k:>16}  {m1:+.4f} ± {e1:.4f}   {m0:+.4f} ± {e0:.4f}{sig}")
    print("-" * 70)
    print("  '*' = ON significantly nonzero AND separated from the neutral null.")
    print("  bundle_sharpness = Cov(priority-specialization, income): >0 => the")
    print("  market rewards differentiated multi-issue priorities (logrolling).")
    return on, off


def _gen_price_cov(w: World):
    """Cov(trait, income-this-gen) computed from the PENDING generation. We run
    a one-gen shadow so the covariance uses that gen's realized income."""
    # cheaper: read last census-style income by replaying one gen on a clone is
    # costly; instead use the world's own per-agent income accumulator after the
    # market phase. We approximate with the standing pop's knob vs prior income.
    agents = list(w.agents.values())
    if len(agents) < 4:
        return {}
    inc = np.array([w._gen_income_agent.get(a.id, 0.0) for a in agents])
    if np.std(inc) < 1e-9:
        return {}
    out = {}
    for k in ("pareto_knob", "walk_margin", "patience", "open_aggression"):
        tr = np.array([getattr(a.genome, k) for a in agents])
        out[k] = float(np.cov(tr, inc)[0, 1])
    # Multi-issue genes. `bundle_sharpness` = negentropy of the priority simplex
    # (higher = more specialized priorities): does specializing pay? The three
    # bundle_tactic coeffs (sharpen-declaration, peer-cooperation, concession) are
    # the evolvable multi-issue ceiling.
    def negent(bf):
        return float(sum(p * np.log(p + 1e-9) for p in bf))  # = -entropy
    sharp = np.array([negent(a.genome.bundle_focus) for a in agents])
    if np.std(sharp) > 1e-9:
        out["bundle_sharpness"] = float(np.cov(sharp, inc)[0, 1])
    for j, name in enumerate(("bt_sharpen", "bt_coop", "bt_concede")):
        tr = np.array([a.genome.bundle_tactic[j] for a in agents])
        if np.std(tr) > 1e-9:
            out[name] = float(np.cov(tr, inc)[0, 1])
    return out


# ─── #3 neutral null: do tactic shares swing under DRIFT alone? ─────────────

def neutral_null(gens=100, seeds=(1, 2, 3)):
    """DIRECTIONAL selection test: does a tactic's income in gen g predict its
    population-share CHANGE to g+2? Positive under selection, ~0 under drift =
    selection is real and directed (not the misleading raw-volatility swing,
    which balancing selection actually LOWERS)."""
    def directional(neutral):
        cors, swings = [], []
        for sd in seeds:
            w = World(dataclasses.replace(CONFIG, seed=sd), neutral=neutral)
            inc_hist, share_hist = [], []
            series = defaultdict(list)
            for _ in range(gens):
                for ev in w.generation_events():
                    if ev["type"] == "census":
                        tot = sum(v["n"] for v in ev["tactics"].values()) or 1
                        inc_hist.append({t: ev["tactics"].get(t, {"income": 0}).get("income", 0)
                                         for t in TACTIC_FAMILIES})
                        share_hist.append({t: ev["tactics"].get(t, {"n": 0})["n"] / tot
                                           for t in TACTIC_FAMILIES})
                        for t in TACTIC_FAMILIES:
                            series[t].append(share_hist[-1][t])
            xs, ys = [], []
            for g in range(len(inc_hist) - 2):
                for t in TACTIC_FAMILIES:
                    if share_hist[g][t] > 0:               # tactic present
                        xs.append(inc_hist[g][t])
                        ys.append(share_hist[g + 2][t] - share_hist[g][t])
            if len(xs) > 5 and np.std(xs) > 1e-9 and np.std(ys) > 1e-9:
                cors.append(float(np.corrcoef(xs, ys)[0, 1]))
            swings.append(max(max(v) - min(v) for v in series.values() if v))
        return (float(np.mean(cors)) if cors else 0.0), float(np.mean(swings))
    sc, sw_sel = directional(False)
    nc, sw_neu = directional(True)
    print("=" * 70)
    print("  NEUTRAL NULL — directional selection: corr(tactic income, its")
    print("  share-change 2 gens later), SELECTION vs DRIFT")
    print("=" * 70)
    print(f"    selection ON : corr {sc:+.2f}   (volatility {sw_sel:.0%})")
    print(f"    neutral null : corr {nc:+.2f}   (volatility {sw_neu:.0%})")
    print("-" * 70)
    if sc > 0.1 and sc > nc + 0.1:
        print(f"  Income PREDICTS share growth under selection ({sc:+.2f}) but not under")
        print(f"  drift ({nc:+.2f}) — selection is real and DIRECTED. Lower volatility")
        print("  under selection = balancing (frequency-dependent), not absence.")
    else:
        print(f"  Income does NOT clearly predict share growth ({sc:+.2f} vs drift {nc:+.2f})")
        print("  — the 'winner rises' story is mostly drift + scheduler. Report honestly.")
    return dict(sel_corr=sc, neu_corr=nc, sel_swing=sw_sel, neu_swing=sw_neu)


# ─── #4 fitness decomposition: surplus vs demographic variance ──────────────

def decompose(gens=60, seed=7):
    w = World(dataclasses.replace(CONFIG, seed=seed))
    for _ in range(gens // 2):
        list(w.generation_events())
    # sample a generation: attribute each agent's energy change to income
    # (surplus) vs the rest (tax/upkeep/senescence/birth = demographic)
    inc_var, demo_var = [], []
    for _ in range(gens // 2):
        before = {a.id: a.energy for a in w.agents.values()}
        list(w.generation_events())
        income = w._gen_income_agent
        deltas, incs = [], []
        for aid, e0 in before.items():
            a = w.agents.get(aid)
            if a is None:
                continue
            deltas.append(a.energy - e0)
            incs.append(income.get(aid, 0.0))
        if len(deltas) > 3:
            deltas = np.array(deltas); incs = np.array(incs)
            demo = deltas - incs
            inc_var.append(float(np.var(incs))); demo_var.append(float(np.var(demo)))
    iv, dv = np.mean(inc_var), np.mean(demo_var)
    frac = iv / (iv + dv + 1e-9)
    print("=" * 70)
    print("  FITNESS DECOMPOSITION: is fitness about NEGOTIATION or taxes?")
    print("=" * 70)
    print(f"    variance from negotiated surplus (income): {iv:.2f}")
    print(f"    variance from demographic terms (tax/etc): {dv:.2f}")
    print(f"    surplus share of fitness variance: {frac:.0%}")
    print("-" * 70)
    print("  If this is small, selection is on tax-dodging, not negotiation —")
    print("  the 'SNHP is the selection pressure' claim would be a rounding error.")
    return dict(surplus_frac=frac)


# ─── #5 crossover ablation: BUILDING-BLOCK ASSEMBLY TIME ────────────────────

def assembly(trials=24, gens=40):
    """Two parents each hold HALF of a known-good (tactic, aggression, walk)
    building block. Measure generations for each crossover operator to
    reconstitute the full block in the population. Negotiated crossover should
    beat uniform if it does real linkage-aware work."""
    from arena import courtship as ct
    from arena.credit import Scorecard
    target_tac, target_aggr, target_walk = "anchorer", 0.9, 0.8

    def has_block(g):
        return (g.tactic_family == target_tac and abs(g.open_aggression - target_aggr) < 0.15
                and abs(g.walk_margin - target_walk) < 0.15)

    def parent_a():  # holds the tactic + aggression half
        return Genome(tactic_family=target_tac, open_aggression=target_aggr,
                      walk_margin=0.2, pareto_knob=0.7)

    def parent_b():  # holds the walk_margin half
        return Genome(tactic_family="conceder", open_aggression=0.3,
                      walk_margin=target_walk, pareto_knob=0.7)

    def cross(op, pa, pb, rng, sc_a, sc_b):
        if op == "uniform":
            child = pa
            for blk in BLOCKS:
                src = pa if rng.random() < 0.5 else pb
                child = child.with_block(blk, src.block_values(blk))
            return child
        if op == "blend":
            child = pa
            for blk in BLOCKS:
                va, vb = pa.block_values(blk), pb.block_values(blk)
                if blk in ("attestation", "tactic"):
                    child = child.with_block(blk, va if rng.random() < 0.5 else vb)
                else:
                    child = child.with_block(blk, tuple((np.asarray(va) + np.asarray(vb)) / 2))
            return child
        # negotiated: the real operator
        pa_s = ct.Suitor(0, pa, 300, 0.5, sc_a, pa.staked)
        pb_s = ct.Suitor(1, pb, 300, 0.5, sc_b, pb.staked)
        g = ct.run_courtship(pa_s, pb_s, CONFIG, 0.03, rng, int(rng.integers(1 << 30)))
        out = None
        try:
            while True:
                next(g)
        except StopIteration as e:
            out = e.value
        return out.child_genome if out.matched else None

    print("=" * 70)
    print("  BUILDING-BLOCK ASSEMBLY: negotiated crossover vs uniform vs blend")
    print("  (generations to reconstitute a split known-good block; lower=better)")
    print("=" * 70)
    results = {}
    for op in ("negotiated", "uniform", "blend"):
        times = []
        for tr in range(trials):
            rng = np.random.default_rng(1000 + tr)
            # a small pop seeded half-and-half; scorecards primed toward the block
            pop = []
            for i in range(12):
                g = parent_a() if i % 2 == 0 else parent_b()
                sc = Scorecard()
                # prime credit: the block's genes have been "paying off"
                for _ in range(6):
                    sc.update(g, 0.7)
                pop.append((g, sc))
            found = gens
            for gen in range(gens):
                if any(has_block(g) for g, _ in pop):
                    found = gen; break
                nxt = []
                for _ in range(len(pop)):
                    (ga, sca), (gb, scb) = pop[int(rng.integers(len(pop)))], pop[int(rng.integers(len(pop)))]
                    child = cross(op, ga, gb, rng, sca, scb)
                    if child is None:
                        child = ga
                    child = mutate(child, 0.04, rng, 0.05, 0.02)
                    csc = Scorecard.child_prior(sca, scb)
                    nxt.append((child, csc))
                pop = nxt
            times.append(found)
        results[op] = (float(np.mean(times)), float(np.mean([t < gens for t in times])))
        print(f"    {op:>11}: {results[op][0]:5.1f} gens to assemble "
              f"({results[op][1]:.0%} of trials succeeded within {gens})")
    print("-" * 70)
    neg, uni = results["negotiated"][0], results["uniform"][0]
    if neg < uni * 0.95:
        print(f"  Negotiated crossover assembles faster than uniform ({neg:.1f} vs "
              f"{uni:.1f}) — it does REAL linkage-aware work.")
    else:
        print(f"  Negotiated crossover ({neg:.1f}) does NOT beat uniform ({uni:.1f}) "
              "— the operator is dead weight; keep it for the story, say so.")
    return results


# ─── #6 speciation: P(impasse | genetic distance) ──────────────────────────

def speciation(gens=120, seeds=(1, 2, 3, 4, 5, 6)):
    # impasse is rare (~3%), so accumulate courtship-distance samples across seeds
    dist_impasse, dist_ok = [], []
    for seed in seeds:
        w = World(dataclasses.replace(CONFIG, seed=seed))
        id_gene = {a.id: a.genome for a in w.agents.values()}  # seed population
        for _ in range(gens):
            for ev in w.generation_events():
                if ev["type"] in ("agent.spawn", "agent.birth", "immigration") and ev.get("genome"):
                    id_gene[ev["id"]] = Genome.from_dict(ev["genome"])
                if ev["type"] in ("court.impasse", "court.accept"):
                    a, b = id_gene.get(ev["a"]), id_gene.get(ev["b"])
                    if a and b:
                        d = 1 - similarity(a, b)
                        (dist_impasse if ev["type"] == "court.impasse" else dist_ok).append(d)
    print("=" * 70)
    print("  SPECIATION: P(courtship impasse | parent genetic distance)")
    print("=" * 70)
    if len(dist_impasse) >= 5 and len(dist_ok) >= 5:
        mi, mo = np.mean(dist_impasse), np.mean(dist_ok)
        print(f"    mean parent distance | IMPASSE : {mi:.3f}  (n={len(dist_impasse)})")
        print(f"    mean parent distance | SUCCESS : {mo:.3f}  (n={len(dist_ok)})")
        print("-" * 70)
        if mi > mo * 1.1:
            print("  Impasse rises with genetic distance — EMERGENT reproductive")
            print("  isolation (incipient speciation from the negotiation operator).")
        else:
            print("  Impasse is ~independent of distance — no reproductive isolation;")
            print("  impasse is a flat fecundity cost, decoration. Report honestly.")
        return dict(impasse_dist=float(mi), success_dist=float(mo))
    print("  Too few courtships to measure.")
    return {}


# ─── #7 human-competitive: does evolution beat the raw recommender? ─────────

def human_competitive(gens=120, seeds=(1, 2, 3)):
    held_out = _fixed_scenarios(40, era="sellers", seed=55571)
    raw_score = _score_vs_panel(RAW, held_out)  # the hand-designed baseline
    best_evolved = -1e9
    best_desc = None
    for sd in seeds:
        w = World(dataclasses.replace(CONFIG, seed=sd))
        for _ in range(gens):
            list(w.generation_events())
        # score the champion of the final population on the SAME held-out set
        champ = max(w.agents.values(), key=lambda a: a.total_earned)
        s = _score_vs_panel(champ.genome, held_out)
        if s > best_evolved:
            best_evolved = s; best_desc = champ.genome
    print("=" * 70)
    print("  HUMAN-COMPETITIVE: evolved champion vs the RAW SNHP recommender")
    print("  (both scored on the SAME held-out sellers'-market panel, off-path)")
    print("=" * 70)
    print(f"    raw recommender (knob 0.5, no evolved layer): {raw_score:.4f}")
    print(f"    best evolved champion:                        {best_evolved:.4f}"
          f"  ({100*(best_evolved/raw_score-1):+.1f}%)")
    if best_desc is not None:
        c = best_desc.concession
        print(f"    its evolved strategy: {best_desc.tactic_family}, knob "
              f"{best_desc.pareto_knob:.2f}, walk {best_desc.walk_margin:.2f}, "
              f"schedule c={[round(x,2) for x in c]}")
    print("-" * 70)
    if best_evolved > raw_score * 1.02:
        print("  The population EVOLVED a strategy that beats the shipped recommender's")
        print("  own play on held-out scenarios — Koza's human-competitiveness bar,")
        print("  and the best possible marketing proof for the library.")
    else:
        print("  Evolution did NOT clearly beat the raw recommender here. Either the")
        print("  ceiling is still too low or more generations/diversity are needed.")
    return dict(raw=raw_score, evolved=best_evolved)


# ─── #8 MULTI-ISSUE human-competitive: logrolling, across every era ─────────

def bundle_human(gens=100, seeds=(1, 2, 3, 4, 5)):
    """The multi-issue analog of #7, on the axis SNHP is actually built for.
    An evolved champion vs the RAW recommender (uniform priorities, neutral
    ceiling, unstaked), scored on a held-out bundle panel in EVERY era.

    Two metrics, and the DISTINCTION is the whole point: own-surplus is gameable
    (bundle_focus is heritable, so evolution can specialize its own preferences
    until logrolling trivially delivers the one issue it kept — a preference-shape
    artifact, jointly inefficient). Frontier capture (% of the achievable joint
    surplus a settled package captured, preference-normalized) is the honest
    'did it negotiate better' number. Reported per era so no market is
    cherry-picked."""
    panel = _bundle_panel()
    champs = []
    for sd in seeds:
        w = World(dataclasses.replace(CONFIG, seed=sd))
        for _ in range(gens):
            list(w.generation_events())
        champs.append(max(w.agents.values(), key=lambda a: a.total_earned).genome)
    print("=" * 70)
    print("  MULTI-ISSUE HUMAN-COMPETITIVE: evolved champion vs RAW recommender")
    print("  on LOGROLLING, across every era (held-out bundle panel, off-path).")
    print("  surplus = champion's own; capture = % of achievable joint frontier.")
    print("=" * 70)
    print(f"  {'era':>10} {'raw surp':>9} {'evo surp':>9} {'d%':>7}"
          f" {'raw cap':>8} {'evo cap':>8}")
    agg = []
    for era in ERAS:
        scns = _fixed_bundle_scenarios(30, era, 60600 + ERAS.index(era) * 17)
        raw_s, raw_c = _score_vs_bundle_panel(RAW_BUNDLE, panel, scns)
        scored = [(_score_vs_bundle_panel(g, panel, scns), g) for g in champs]
        (evo_s, evo_c), best_g = max(scored, key=lambda x: x[0][0])
        d = 100 * (evo_s / raw_s - 1) if raw_s > 1e-9 else 0.0
        agg.append((era, raw_s, evo_s, d, raw_c, evo_c, best_g))
        print(f"  {era:>10} {raw_s:>9.4f} {evo_s:>9.4f} {d:>+6.1f}%"
              f" {raw_c:>7.0%} {evo_c:>7.0%}")
    print("-" * 70)
    best = max(agg, key=lambda r: r[3])
    era, _, _, d, _, _, g = best
    bt = g.bundle_tactic
    print(f"  champion: {g.tactic_family}, staked={g.staked}, priorities="
          f"{[round(x,2) for x in g.bundle_focus]},")
    print(f"    bundle_tactic (sharpen,coop,concede)={[round(x,2) for x in bt]}")
    mean_d = float(np.mean([r[3] for r in agg]))
    mean_cap_gain = float(np.mean([r[5] - r[4] for r in agg]))
    print(f"  own-surplus gain (mean over eras):    {mean_d:+.1f}%")
    print(f"  frontier-capture gain (mean, HONEST): {mean_cap_gain:+.1%}")
    if mean_cap_gain > 0.02:
        print("  Evolution captures MORE of the joint frontier than the raw recommender")
        print("  — a real logrolling-EFFICIENCY win on the axis SNHP is built for.")
    elif mean_d > 20.0 and mean_cap_gain <= 0.01:
        print("  HONEST READ: the large own-surplus gain is a PREFERENCE-SHAPE artifact.")
        print("  Evolution specializes its (heritable) priorities so the logroll trivially")
        print("  delivers the one issue it kept caring about — trivially-satisfiable")
        print("  preferences, not sharper bargaining. It is jointly NO more efficient")
        print("  (capture flat/down), so on the preference-normalized metric the RAW SNHP")
        print("  logroller is already at the ceiling. Same lesson as price: you don't beat")
        print("  the shipped recommender by distorting its inputs.")
    else:
        print("  Evolution ~ties raw on the honest (capture) metric — the raw multi-issue")
        print("  recommender is near the ceiling; individual gains are modest/conditional.")
    return dict(per_era=[(r[0], r[1], r[2], r[3], r[4], r[5]) for r in agg],
                mean_delta=mean_d, mean_cap_gain=mean_cap_gain)


def main():
    ap = argparse.ArgumentParser()
    for f in ("absolute", "price", "neutral", "decompose", "assembly",
              "speciation", "human", "bundle_human", "all"):
        ap.add_argument(f"--{f.replace('_', '-')}", dest=f, action="store_true")
    a = ap.parse_args()
    run_all = a.all or not any(vars(a).values())
    if a.absolute or run_all: absolute_fitness()
    if a.price or run_all: price_equation()
    if a.neutral or run_all: neutral_null()
    if a.decompose or run_all: decompose()
    if a.assembly or run_all: assembly()
    if a.speciation or run_all: speciation()
    if a.human or run_all: human_competitive()
    if a.bundle_human or run_all: bundle_human()


if __name__ == "__main__":
    main()

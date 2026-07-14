"""VEND IC battery (Task #68B) — the harder deviation battery the pooled
uniform-WTP × binary-walk sweep (vend/liar-sweep.json) cannot see.

The committed liar sweep reports a POPULATION MEAN consumer-surplus delta over
an all-liar arm. That washes out a profitable minority: a lie that pays only on
the rare excess day, or only for a high-outside-option type, is diluted by the
many days/types on which the same uniform lie loses the buyer their board
disagreement. This module adds the instruments that see through the average.

  1. UNILATERAL deviation probe (the exact best-response / IC test). The world
     is held HONEST and the learner converged on honest play; at EACH buyer's
     decision node we compute, AGAINST THE IDENTICAL STATE, the honest quote
     and the counterfactual lie quote for each deviation strategy, and the
     buyer's TRUE-preference realized welfare under each (quote if accepted,
     else the unchanged board/bodega alternative). The deviation gain
     `lie_true − honest_true` holds all other buyers fixed and the state fixed
     — textbook IC with ZERO state contamination (we never mutate the world
     for a counterfactual; only the honest deal settles). This is exactly what
     the §3 Proposition claims and what an all-liar arm structurally cannot
     isolate (there the state moves too).

  2. SUP-OVER-TYPES. Per-buyer gains are stratified by (excess-day ×
     high-outside-option) and we report the WORST stratum's mean gain with a
     block CI — not the population mean.

  3. Deviation strategies: uniform (baseline), STATE-CONDITIONED ADAPTIVE (lie
     only where visible stock is high — concentrate the exploit on excess
     days), PER-SKU favorite-only and perishables-only (the attack on shadow
     pricing). Each with the free-walk (cond.-d) channel ON and OFF, so the
     WTP channel is isolated from the outside-option channel.

  4. WARM vs COLD learner (population arm). The same all-liar arm measured on a
     COLD learner (days 0..M) and a CONVERGED learner (burn-in B, measure
     B..B+M), to test whether a learner adapted to the liar population opens a
     leak the cold learner's structural over-forecast hid.

  5. MDE. The minimum detectable effect at 80% power / α=0.05 for the horizon —
     the ±$0.5-1.5 CIs cannot see a $0.30 exploit; this quantifies how much
     horizon a $0.30 detection would take.

  python3 -m vend.battery --probe --seeds 20260713,7 --burn 30 --measure 120 \
      --out vend/battery.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
from scipy import stats

from vend.core import substream
from vend.policies import A2APolicy
from vend.scenario import (adaptive_disclosure, buyer_value, c_eff,
                           expected_list_demand, nash_quote,
                           persku_disclosure, strategic_disclosure)
from vend.world import (CALIBRATED_TRAFFIC_SCALE, DEFAULT_CONFIG, QTY_CAP,
                        TICKS_PER_DAY, WorldConfig, arrivals_at, best_bundle,
                        build_catalog, day_state, end_of_day, fresh_machine,
                        rate_at, sample_consumer)

BATTERY_VERSION = 1

OUT_THRESH = 0.75      # $ of outside surplus above which a buyer is "high-outside"

# The deviation strategies probed at each buyer. factor<1 understates; zero_walk
# claims a free outside option (the §3 cond.-(d) channel). We probe the WTP
# channel ALONE (zero_walk=False) and WITH the free-walk channel (zero_walk=True)
# for each mode, so the two channels never hide behind each other.
STRATEGIES = [
    # WTP channel (cond.-d walk claim OFF): the pure a/b/c test.
    {"name": "uniform_wtp",       "mode": "uniform",       "factor": 0.55, "zero_walk": False},
    {"name": "adaptive_wtp",      "mode": "adaptive",      "factor": 0.55, "zero_walk": False, "stock_mult": 1.2},
    {"name": "adaptive_aggr_wtp", "mode": "adaptive",      "factor": 0.55, "zero_walk": False, "stock_mult": 1.0},
    {"name": "adaptive_oracle_wtp","mode": "adaptive-oracle","factor": 0.55, "zero_walk": False},
    {"name": "perskufav_wtp",     "mode": "persku-fav",    "factor": 0.55, "zero_walk": False},
    {"name": "perishable_wtp",    "mode": "persku-perish", "factor": 0.55, "zero_walk": False},
    # cond.-d channel: the free-outside-option claim (the known residual leak
    # attestation banks) — with the WTP lie (uniform+walk) and alone (walk_only).
    {"name": "uniform_wtp+walk",  "mode": "uniform",       "factor": 0.55, "zero_walk": True},
    {"name": "adaptive_oracle_wtp+walk","mode": "adaptive-oracle","factor": 0.55, "zero_walk": True},
    {"name": "walk_only",         "mode": "uniform",       "factor": 1.00, "zero_walk": True},
]


# ── CI machinery (identical convention to vend.run) ─────────────────────────

def block_ci(diffs: list[float], block: int = 5) -> dict:
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        nb = len(d) // block
        d = d[:nb * block].reshape(nb, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 3), "ci95": None, "n": n, "block": block}
    se = float(d.std(ddof=1) / math.sqrt(n))
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 3), "ci95": [round(mean - t * se, 3),
                                             round(mean + t * se, 3)],
            "n": n, "block": block, "sd_block": round(float(d.std(ddof=1)), 4)}


def pooled_block_ci(per_seed: list[list[float]], block: int = 5) -> dict:
    """Block within each seed (never straddling a seed boundary), pool the
    block-means, t-interval over them — the vend.run _pooled_ci convention."""
    blocks: list[float] = []
    for series in per_seed:
        d = np.asarray(series, dtype=float)
        if block > 1 and len(d) >= 2 * block:
            nb = len(d) // block
            d = d[:nb * block].reshape(nb, block).mean(axis=1)
        blocks.extend(d.tolist())
    b = np.asarray(blocks, dtype=float)
    n = len(b)
    mean = float(b.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 3), "ci95": None, "n": n, "block": block}
    se = float(b.std(ddof=1) / math.sqrt(n))
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 3), "ci95": [round(mean - t * se, 3),
                                             round(mean + t * se, 3)],
            "n": n, "block": block, "sd_block": round(float(b.std(ddof=1)), 4)}


def mde(sd_block: float, n_blocks: int, alpha: float = 0.05,
        power: float = 0.80) -> float:
    """Two-sided MDE for a paired-difference block series: the true effect a
    design with `n_blocks` block observations detects with `power` at level
    `alpha`. MDE = (t_{1-α/2} + t_{power}) · SD/√n."""
    if n_blocks < 2:
        return float("nan")
    df = n_blocks - 1
    ta = float(stats.t.ppf(1 - alpha / 2, df))
    tb = float(stats.t.ppf(power, df))
    return (ta + tb) * sd_block / math.sqrt(n_blocks)


# ── the unilateral deviation probe ──────────────────────────────────────────

def _nash_with(policy: A2APolicy, state, wtp_d, walk_d):
    n = len(state.listings)
    return nash_quote(state, wtp_d, walk_d,
                      dow_mult=policy.dow_mult,
                      mult_hat=policy.learner.mult_hat,
                      share_fn=lambda s: policy.learner.share(s, n),
                      daily_fn=policy.learner.daily,
                      min_gain=policy.min_gain,
                      min_gain_frac=policy.min_gain_frac,
                      traffic_scale=policy.traffic_scale,
                      seller_weight=policy.seller_weight)


def _excess_targets(policy, state):
    """The SKUs the mechanism itself would treat as excess right now
    (stock > learned expected list demand) — the info set of the STRONGEST
    possible adaptive attacker (an oracle who sees the shadow-excess set the
    buyer's visible-stock heuristic only approximates). An upper bound on the
    adaptive attack."""
    n = len(state.listings)
    tgt = set()
    for s in state.listings:
        if state.stock(s) <= 0:
            continue
        D = expected_list_demand(state, s, dow_mult=policy.dow_mult,
                                 mult_hat=policy.learner.mult_hat,
                                 share=policy.learner.share(s, n),
                                 emp_daily=policy.learner.daily(s),
                                 traffic_scale=policy.traffic_scale)
        if state.stock(s) - D > 1e-9:
            tgt.add(s)
    return tgt


def _disclose(strategy, state, consumer, policy):
    f, zw, mode = strategy["factor"], strategy["zero_walk"], strategy["mode"]
    if mode == "uniform":
        return strategic_disclosure(consumer.wtp, consumer.walk_cost, f, zw)
    if mode == "adaptive":
        return adaptive_disclosure(state, consumer.wtp, consumer.walk_cost,
                                   factor=f, stock_mult=strategy.get("stock_mult", 1.2),
                                   zero_walk=zw)
    if mode == "adaptive-oracle":
        return persku_disclosure(consumer.wtp, consumer.walk_cost,
                                 targets=_excess_targets(policy, state),
                                 factor=f, zero_walk=zw)
    if mode == "persku-fav":
        fav = max(consumer.wtp,
                  key=lambda s: consumer.wtp[s] - state.listings[s].list_price)
        return persku_disclosure(consumer.wtp, consumer.walk_cost,
                                 targets={fav}, factor=f, zero_walk=zw)
    if mode == "persku-perish":
        perish = {s for s, l in state.listings.items() if l.shelf_life_days <= 3}
        return persku_disclosure(consumer.wtp, consumer.walk_cost,
                                 targets=perish, factor=f, zero_walk=zw)
    raise ValueError(mode)


def _quote_true_surplus(nq, consumer) -> float | None:
    """The buyer's TRUE-preference surplus of a quote's bundle (never the
    disclosed/lied basis). None if the quote is empty."""
    if nq.outcome is None:
        return None
    o = nq.outcome
    return buyer_value(consumer.wtp, o.sku, o.qty) - o.qty * o.unit_price


def probe_day(policy: A2APolicy, state, catalog, master_seed: int, day: int,
              cfg: WorldConfig, records: list) -> None:
    """One honest a2a day. The honest deal settles (world stays honest, the
    learner sees honest sales); for every arrival we also record the honest
    and each counterfactual-lie TRUE realized welfare against the SAME state."""
    ds = day_state(cfg, master_seed, day)
    policy.dow_mult = ds.dow_mult
    policy.traffic_scale = cfg.traffic_scale
    policy.learner.begin_day(ds.dow_mult)
    outside_prices = {s: catalog[s].bodega_price for s in catalog}
    return_queue: list[tuple[int, object]] = []

    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        due = [c for t, c in return_queue if t == tick]
        return_queue = [(t, c) for t, c in return_queue if t > tick]

        n_new = arrivals_at(master_seed, day, tick, cfg)
        policy.learner.observe_arrivals(
            rate_at(tick) / 6.0 * ds.dow_mult * cfg.traffic_scale, n_new)
        consumers = ([sample_consumer(master_seed, day, tick, k, catalog, cfg)
                      for k in range(n_new)] + due)

        for consumer in consumers:
            o_sku, o_qty, o_s = consumer.best_bundle(outside_prices)
            s_out = (o_s - consumer.walk_cost) if o_sku else 0.0
            # the honest board fallback (list prices, stock-capped), TRUE basis
            b_prices = {s: catalog[s].list_price for s in catalog
                        if state.stock(s) > 0}
            b_stock = {s: state.stock(s) for s in b_prices}
            bsku, bqty, s_board = (best_bundle(consumer.wtp, b_prices, b_stock)
                                   if b_prices else (None, 0, 0.0))
            alt = max(0.0, s_out, s_board)   # buyer welfare with NO quote

            # honest quote (attest=True ⇒ never a liar)
            nq_h, _ = policy.quote_for(state, consumer, 1.0)
            h_true = _quote_true_surplus(nq_h, consumer)
            honest_accept = (h_true is not None and h_true > 0 and h_true >= alt)
            honest_total = h_true if honest_accept else alt

            # stratum tags (analysis-side; the mechanism's own excess flag)
            fav = max(consumer.wtp,
                      key=lambda s: consumer.wtp[s] - catalog[s].list_price)
            n_sku = len(catalog)
            D_fav = expected_list_demand(
                state, fav, dow_mult=policy.dow_mult,
                mult_hat=policy.learner.mult_hat,
                share=policy.learner.share(fav, n_sku),
                emp_daily=policy.learner.daily(fav),
                traffic_scale=policy.traffic_scale)
            excess_fav = state.stock(fav) - D_fav > 1e-9
            high_out = s_out >= OUT_THRESH

            rec = {"day": day, "excess": bool(excess_fav),
                   "high_out": bool(high_out), "s_out": round(s_out, 3),
                   "alt": round(alt, 3), "honest_total": round(honest_total, 4),
                   "converted_honest": bool(honest_accept), "gains": {}}

            for strat in STRATEGIES:
                wtp_d, walk_d = _disclose(strat, state, consumer, policy)
                nq_l = _nash_with(policy, state, wtp_d, walk_d)
                l_true = _quote_true_surplus(nq_l, consumer)
                lie_accept = (l_true is not None and l_true > 0 and l_true >= alt)
                lie_total = l_true if lie_accept else alt
                rec["gains"][strat["name"]] = round(lie_total - honest_total, 4)
            records.append(rec)

            # ── settle the HONEST outcome into the world ──
            if honest_accept:
                o = nq_h.outcome
                state.take(o.sku, o.qty)
                policy.learner.sold(o.sku, o.qty)
            elif s_board > 0 and s_board >= s_out and bsku is not None:
                state.take(bsku, bqty)
                policy.learner.sold(bsku, bqty)
            else:
                # unconverted: same patience-driven return defer as run_day
                rng = np.random.default_rng(
                    substream(master_seed, "ret", day, tick, consumer.uid))
                if rng.random() < consumer.patience:
                    delay = int(rng.integers(6, 24))
                    if tick + delay < TICKS_PER_DAY:
                        return_queue.append((tick + delay, consumer))

    policy.learner.end_day(frozenset(
        s for s in catalog if state.stock(s) == 0))
    end_of_day(state, cfg, master_seed)


def run_probe(seeds: list[int], burn: int, measure: int, cfg: WorldConfig
              ) -> dict:
    """Run the honest world for `burn` days to converge the learner, then probe
    `measure` days. Returns per-seed per-day per-stratum gain series so the
    caller can pool with the standard block CI."""
    total_days = burn + measure
    # per strategy: per-seed list of per-day summed gains (all buyers), plus
    # per-stratum variants. strata keys: all / excess / high_out /
    # excess_high_out / scarce.
    strata = ["all", "excess", "high_out", "excess_high_out", "scarce_lowout"]
    series = {st["name"]: {k: [] for k in strata} for st in STRATEGIES}
    n_probed = {k: 0 for k in strata}
    raw_max = {st["name"]: 0.0 for st in STRATEGIES}
    conv_rate = []

    def in_stratum(rec, key):
        if key == "all":
            return True
        if key == "excess":
            return rec["excess"]
        if key == "high_out":
            return rec["high_out"]
        if key == "excess_high_out":
            return rec["excess"] and rec["high_out"]
        if key == "scarce_lowout":
            return (not rec["excess"]) and (not rec["high_out"])
        return False

    for seed in seeds:
        catalog = build_catalog(cfg, seed)
        state = fresh_machine("battery", catalog, cfg, seed)
        policy = A2APolicy()
        policy.traffic_scale = cfg.traffic_scale
        for d in range(burn):
            probe_day(policy, state, catalog, seed, d, cfg, [])
        recs: list = []
        for d in range(burn, total_days):
            probe_day(policy, state, catalog, seed, d, cfg, recs)
        conv_rate.append(round(np.mean([r["converted_honest"] for r in recs]), 3)
                         if recs else 0.0)
        # aggregate to per-day sums, per strategy per stratum
        for k in strata:
            n_probed[k] += sum(1 for r in recs if in_stratum(r, k))
        for st in STRATEGIES:
            name = st["name"]
            for k in strata:
                perday = [0.0] * measure
                for r in recs:
                    if in_stratum(r, k):
                        perday[r["day"] - burn] += r["gains"][name]
                series[name][k].append(perday)
            raw_max[name] = max(raw_max[name],
                                max((r["gains"][name] for r in recs), default=0.0))

    out = {"seeds": seeds, "burn": burn, "measure": measure,
           "n_probed_by_stratum": n_probed,
           "honest_conversion_rate_by_seed": conv_rate,
           "strategies": {}}
    for st in STRATEGIES:
        name = st["name"]
        srow = {"spec": st, "raw_max_single_buyer_gain": round(raw_max[name], 3),
                "strata": {}}
        for k in strata:
            ci = pooled_block_ci(series[name][k], block=5)
            ci["mde_dollar_per_day"] = round(
                mde(ci.get("sd_block", 0.0), ci["n"]), 3) if ci["n"] >= 2 else None
            srow["strata"][k] = ci
        # sup-over-types: the worst (max mean) stratum, and whether ANY stratum
        # is significantly positive (CI lower bound > 0)
        stratum_means = {k: srow["strata"][k]["mean"] for k in strata}
        sup_key = max(stratum_means, key=stratum_means.get)
        srow["sup_over_types"] = {"stratum": sup_key,
                                  "mean_gain_per_day": stratum_means[sup_key],
                                  "ci95": srow["strata"][sup_key]["ci95"]}
        sig = [k for k in strata
               if srow["strata"][k]["ci95"] and srow["strata"][k]["ci95"][0] > 0]
        srow["significantly_positive_strata"] = sig
        out["strategies"][name] = srow
    return out


# ── warm-vs-cold population arm (point 4) ───────────────────────────────────

def run_population_warm(seeds: list[int], burn: int, measure: int,
                        cfg: WorldConfig, attack_mode: str, factor: float,
                        zero_walk: bool) -> dict:
    """All-liar arm (attack_mode) vs honest a2a, paired daily CS diff, measured
    on a COLD learner (days 0..measure) and a WARM/converged learner
    (days burn..burn+measure). Uses the production run_day so this is the exact
    deployment loop, not the probe's honest-only loop."""
    from vend.run import run_day
    total = burn + measure
    cold_h, cold_l, warm_h, warm_l = [], [], [], []
    for seed in seeds:
        catalog = build_catalog(cfg, seed)
        h_state = fresh_machine("warm-h", catalog, cfg, seed)
        l_state = fresh_machine("warm-l", catalog, cfg, seed)
        h_pol = A2APolicy()
        l_pol = A2APolicy(attest=False, liar_share=1.0, attack_factor=factor,
                          attack_zero_walk=zero_walk, attack_mode=attack_mode)
        h_days = [run_day(h_pol, h_state, catalog, seed, d, cfg) for d in range(total)]
        l_days = [run_day(l_pol, l_state, catalog, seed, d, cfg) for d in range(total)]
        cs = lambda days, a, b: [days[d]["consumer_surplus"] for d in range(a, b)]
        cold_h.append(cs(h_days, 0, measure)); cold_l.append(cs(l_days, 0, measure))
        warm_h.append(cs(h_days, burn, total)); warm_l.append(cs(l_days, burn, total))

    def paired(hs, ls):
        return pooled_block_ci([[l[i] - h[i] for i in range(len(h))]
                                for h, l in zip(hs, ls)], block=5)
    return {"attack_mode": attack_mode, "factor": factor, "zero_walk": zero_walk,
            "cold_cs_gain": paired(cold_h, cold_l),
            "warm_cs_gain": paired(warm_h, warm_l),
            "burn": burn, "measure": measure, "seeds": seeds}


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cfg(glut: float) -> WorldConfig:
    return WorldConfig(sigma_cal=0.3, sigma_rate=0.6, sigma_wtp=0.3, dow=True,
                       glut_prob=glut, traffic_scale=CALIBRATED_TRAFFIC_SCALE)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="20260713,7")
    ap.add_argument("--burn", type=int, default=30)
    ap.add_argument("--measure", type=int, default=120)
    ap.add_argument("--glut", type=float, default=0.15,
                    help="realistic cell glut prob (0.15); a stress cell uses 0.4")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--warm", action="store_true",
                    help="also run the warm-vs-cold population arms")
    ap.add_argument("--stress-glut", type=float, default=0.4,
                    help="second cell for the probe (more excess days)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    payload = {"battery_version": BATTERY_VERSION, "task": "ic-battery-68B",
               "seeds": seeds, "burn": args.burn, "measure": args.measure,
               "world": "realistic calibrated cell (sigma_cal=0.3, sigma_rate=0.6, "
                        "sigma_wtp=0.3, dow, calibrated traffic ~7-8 vends/day, "
                        "finite stock, discount-only, attestation OFF)"}

    if args.probe:
        print(f"== probe: realistic cell (glut={args.glut}) ==")
        payload["probe_realistic"] = run_probe(seeds, args.burn, args.measure,
                                               _cfg(args.glut))
        _print_probe(payload["probe_realistic"], f"glut={args.glut}")
        print(f"\n== probe: high-excess stress cell (glut={args.stress_glut}) ==")
        payload["probe_stress"] = run_probe(seeds, args.burn, args.measure,
                                           _cfg(args.stress_glut))
        _print_probe(payload["probe_stress"], f"glut={args.stress_glut}")

    if args.warm:
        print("\n== warm-vs-cold population arms (glut=0.15) ==")
        pop = {}
        for mode in ("uniform", "adaptive"):
            for zw in (False, True):
                r = run_population_warm(seeds, args.burn, args.measure,
                                        _cfg(args.glut), mode, 0.55, zw)
                key = f"{mode}_walk{'zero' if zw else 'honest'}"
                pop[key] = r
                print(f"{key:24} cold CS Δ/day {r['cold_cs_gain']['mean']:+7.3f} "
                      f"{r['cold_cs_gain']['ci95']}  warm {r['warm_cs_gain']['mean']:+7.3f} "
                      f"{r['warm_cs_gain']['ci95']}")
        payload["population_warm_vs_cold"] = pop

    if args.out:
        with open(args.out, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"\nwrote {args.out}")
    return 0


def _print_probe(res: dict, tag: str) -> None:
    print(f"  probed buyers by stratum: {res['n_probed_by_stratum']}  "
          f"honest conv rate {res['honest_conversion_rate_by_seed']}")
    hdr = f"  {'strategy':20} {'all(mean/CI)':26} {'SUP stratum':16} {'sup mean/CI':24} {'sig+':16} {'MDE$/d(all)'}"
    print(hdr)
    for name, srow in res["strategies"].items():
        allci = srow["strata"]["all"]
        sup = srow["sup_over_types"]
        mdev = srow["strata"]["all"].get("mde_dollar_per_day")
        print(f"  {name:20} {allci['mean']:+7.3f} {str(allci['ci95']):16} "
              f"{sup['stratum']:16} {sup['mean_gain_per_day']:+7.3f} {str(sup['ci95']):16} "
              f"{str(srow['significantly_positive_strata']):16} {mdev}")


if __name__ == "__main__":
    sys.exit(main())

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
from swarm.world import CHARGE_SLOTS, TOTAL_STOCK, V_DELIVER, World, manhattan

FULL = ("cargo", "energy", "sector")
LADDER = ["null", "rules", "auction", "auction-co", "team", "team-co",
          "twofirm", "snhp", "snhp+net", "snhp-hz"]
TAUS = [0.05, 0.10, 0.15, 0.25, 0.50]        # straddles τ*≈0.16 (panel F2)
TAU_ARMS = ["null", "snhp-hz", "team"]

# v17 (column P): distance bands for the far-ore decay signature. ≤30 = home,
# 31–62 = within a single loaded charge (loaded range ≈ BATTERY_MAX/(eff·1.6) ≈
# 62 cells at mean eff), >62 = beyond single-charge loaded range (needs a relay
# or a mid-haul recharge — where the chain hypothesis says delivery should decay).
LINEAGE_BANDS = (30, 62)


def _dist_band(d: float) -> int:
    return 0 if d <= LINEAGE_BANDS[0] else (1 if d <= LINEAGE_BANDS[1] else 2)


def _holdup_margins(delivered_parcels, deal_log):
    """Hop-margin ledger for relayed (≥2-hop) parcels. For each interior holder
    of a chain — the drone that BOUGHT the parcel at hop k and SOLD it at hop k+1
    — recover the surplus it realized on each leg from the deal log (matched by
    (tick, {a,b})), then compare. Williamson hold-up predicts the SELL leg's
    margin is compressed below the BUY leg's (its position-specific haul
    investment is expropriated at renegotiation): mean_delta = sell − buy < 0.
    Deal surplus is bundle-level (sa/sb), so per-unit legs repeat their deal's
    figure — a signature, not a precise per-unit decomposition. Auction/
    trophallaxis relays leave no deal-log entry and are skipped (no surplus to
    read). Returns n=0 when no priced ≥2-hop legs exist."""
    idx = {}
    for d in deal_log:
        idx[(d["tick"], frozenset((d["a"], d["b"])))] = d
    buys, sells, deltas = [], [], []
    for p in delivered_parcels:
        if p["hops"] < 2:
            continue
        chain = p["chain"]
        for k in range(len(chain) - 1):
            t_in, g_in, holder = chain[k]
            t_out, holder2, taker_out = chain[k + 1]
            d_in = idx.get((t_in, frozenset((g_in, holder))))
            d_out = idx.get((t_out, frozenset((holder, taker_out))))
            if d_in is None or d_out is None:
                continue
            buy = d_in["sa"] if d_in["a"] == holder else d_in["sb"]   # as buyer
            sell = d_out["sa"] if d_out["a"] == holder else d_out["sb"]  # as seller
            buys.append(float(buy))
            sells.append(float(sell))
            deltas.append(float(sell) - float(buy))
    if not deltas:
        return dict(n=0, mean_buy=None, mean_sell=None, mean_delta=None,
                    frac_compressed=None)
    return dict(n=len(deltas), mean_buy=float(np.mean(buys)),
                mean_sell=float(np.mean(sells)), mean_delta=float(np.mean(deltas)),
                frac_compressed=float(np.mean([d < 0 for d in deltas])))


def _reputation_metrics(w, arm) -> dict:
    """v22 (column U): the reputation blob. Re-encounter rate (mean post-cooldown
    meetings per distinct pair — the theory's driver, measured for EVERY arm) is
    always reported; blacklist size and false-blacklist rate (share of HONEST
    robots blacklisted by anyone — slander plus mis-detection) only under
    reputation. All read-only bookkeeping, computed at run end."""
    meets = getattr(arm, "_pair_meets", {})
    reencounter_rate = (sum(meets.values()) / len(meets)) if meets else 0.0
    if not w.reputation:
        return dict(reencounter_rate=round(reencounter_rate, 4),
                    distinct_pairs=len(meets),
                    blacklist_mean=None, blacklist_max=None,
                    false_bl_frac=None, n_liars=sum(r.liar for r in w.robots))
    sizes = [len(bl) for bl in w.blacklist]
    honest = {r.rid for r in w.robots if not r.liar}
    ever_bl = set().union(*w.blacklist) if w.blacklist else set()
    false_bl = honest & ever_bl
    return dict(
        reencounter_rate=round(reencounter_rate, 4),
        distinct_pairs=len(meets),
        blacklist_mean=round(float(np.mean(sizes)), 4),
        blacklist_max=int(max(sizes)) if sizes else 0,
        false_bl_frac=round(len(false_bl) / max(1, len(honest)), 4),
        n_liars=sum(r.liar for r in w.robots),
    )


def run_once(arm_name: str, sigma: float, seed: int, ticks: int = 2500,
             tau=0.0, preset: str = "v4", issues=FULL,
             noise: float = 0.0, liar_frac: float = 0.0,
             defended: bool = False, self_noise: float = 0.0,
             self_margin: bool = False, grid: int = 32,
             belief_mode: bool = False, race_pricing: bool = True,
             mine_trait: bool = False, dynamic_field: bool = False,
             contested: bool = False, scouting: bool = False,
             map_trading: bool = False, prospect_claims: bool = False,
             n_robots: int = 24, consensus_cost: bool = False,
             gossip: bool = False, r_radio: int = 6,
             lineage: bool = False, bills: bool = False,
             firm_relay: bool = False, reputation: bool = False,
             false_accuse: float = 0.0) -> dict:
    if noise > 0 and (liar_frac > 0 or defended):
        # the liar/defended branch pre-empts the v5 noise machinery, so the
        # combination would run noiseless while the row claims noise>0
        raise ValueError("v5 partner-noise and v6 lies/defense are separate "
                         "treatments; combining them silently disables noise")
    if map_trading and liar_frac > 0:
        # v12 K1: map trading is an HONEST SnhpArm-family mechanism this column;
        # mixing it with liars (TrustArm territory) is explicitly out of scope
        raise ValueError("map_trading is honest-only this column: liar_frac==0")
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
    w = World(n_robots=n_robots, sigma=sigma, seed=seed, hazard_phi=hazard,
              preset=preset, tau=tau_pair,
              internalize_tariffs=(base == "team"),
              liar_frac=liar_frac, defended=defended,
              self_noise=self_noise, self_margin=self_margin,
              grid=grid, life_pricing=life, strand_cap=cap,
              belief_mode=belief_mode, race_pricing=race_pricing,
              mine_trait=mine_trait, dynamic_field=dynamic_field,
              contested=contested, scouting=scouting,
              map_trading=map_trading, prospect_claims=prospect_claims,
              consensus_cost=consensus_cost, gossip=gossip, r_radio=r_radio,
              lineage=lineage, bills=bills, firm_relay=firm_relay,
              reputation=reputation, false_accuse=false_accuse)
    arm = make_arm(base, w, issues=issues, noise=noise)
    makespan = ticks
    delivered_mid = 0
    stale = []          # v10 P15b: mean (tick − last_seen) over all
    stale_own, stale_other = [], []   # v12 K2 P17d: patrol differentiation
    for t in range(ticks):        # (company, asteroid) pairs, every 50 ticks
        arm.tick()
        if belief_mode and (t + 1) % 50 == 0:
            if gossip:
                # v14: fleet-average per-robot staleness (each robot carries its
                # own map under gossip, indexed by rid)
                stale.append(np.mean([w.tick - w.last_seen[rr.rid][i]
                                      for rr in w.robots
                                      for i in range(len(w.sources))]))
            else:
                stale.append(np.mean([w.tick - w.last_seen[co][i]
                                      for co in range(w.n_companies)
                                      for i in range(len(w.sources))]))
            if prospect_claims:
                own, other = [], []
                for cc in range(w.n_companies):
                    for i in range(len(w.sources)):
                        st = w.tick - w.last_seen[cc][i]
                        quad = w.quadrant(w.sources[i])
                        (own if w.claim_owner[quad] == cc else other).append(st)
                if own:
                    stale_own.append(np.mean(own))
                if other:
                    stale_other.append(np.mean(other))
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
    # v13 (column L): emergent middlemen. A robot is a middleman if it delivered
    # anything and RECEIVED (via deals/transfers in) more than it MINED itself —
    # its throughput is dominated by buy-far/sell-near resale, not its own dig.
    deliverers = [r for r in w.robots if r.delivered > 0]
    middlemen = [r for r in deliverers if r.received_units > r.mined_units]
    middleman_frac = (len(middlemen) / len(deliverers)) if deliverers else 0.0
    delivered_frac = w.delivered / max(1, w.total_stock)
    # v14 P21c: is the trade graph the information graph? Pearson corr across
    # robots between deal-degree (times in the deal log) and end-of-run map
    # freshness (mean last_seen over rocks — higher = more recently known),
    # against a shuffled null (mean over 200 permutations of freshness, drawn
    # from a DEDICATED RandomState(seed+31337) so the main stream is untouched).
    # None for no-deal arms (auction/rules never write the deal log).
    freshness_deal_corr = None
    freshness_deal_corr_null = None
    if deals:
        degree = {r.rid: 0 for r in w.robots}
        for d in deals:
            degree[d["a"]] += 1
            degree[d["b"]] += 1
        fresh = {r.rid: float(np.mean(w.last_seen[w._bx(r)])) for r in w.robots}
        deg = np.array([degree[r.rid] for r in w.robots], dtype=float)
        frr = np.array([fresh[r.rid] for r in w.robots], dtype=float)
        if deg.std() > 1e-9 and frr.std() > 1e-9:
            freshness_deal_corr = float(np.corrcoef(deg, frr)[0, 1])
            nrng = np.random.RandomState(seed + 31337)
            nulls = []
            for _ in range(200):
                sh = frr.copy()
                nrng.shuffle(sh)
                if sh.std() > 1e-9:
                    nulls.append(np.corrcoef(deg, sh)[0, 1])
            freshness_deal_corr_null = (float(np.mean(nulls)) if nulls else None)
    # v17 (column P): cargo-lineage diagnosis blob (only when lineage is on).
    # Hop-count distribution of DELIVERED units, per-band delivered-vs-mined,
    # charger duty cycle + dispensed energy, and the hold-up margin ledger.
    lineage_detail = None
    if lineage:
        dp = w.delivered_parcels
        nd = len(dp)
        hc = [0, 0, 0]
        for p in dp:
            hc[min(2, p["hops"])] += 1
        hop_shares = [round(c / nd, 4) for c in hc] if nd else [0.0, 0.0, 0.0]
        # per-rock refinery distance = nearest refinery (each company mines its
        # own mirrored half, so nearest ≈ the delivering refinery). Band the
        # mined ore and the delivered ore identically, then compare fractions.
        rock_band = [_dist_band(min(manhattan(w.sources[i], rf)
                                    for rf in w.refineries))
                     for i in range(len(w.sources))]
        band_mined = [0, 0, 0]
        band_delivered = [0, 0, 0]
        for i in range(len(w.sources)):
            band_mined[rock_band[i]] += w.mined_from[i]
        for p in dp:
            band_delivered[rock_band[p["origin"]]] += 1
        n_ch = len(w.chargers)
        cap = CHARGE_SLOTS * n_ch
        duty = w.charge_served_slots / max(1, cap * makespan)
        # v17 PHASE 2 (P23b): count relay HOPS of delivered ≥2-hop parcels by
        # whether the (giver, taker) share a company. Vertical integration can
        # only organize WITHIN-company chains; bills price both — so the
        # cross-company relay count separates the two instruments' reach.
        co_of = {r.rid: r.company for r in w.robots}
        relay_within = relay_cross = 0
        for p in dp:
            if p["hops"] < 2:
                continue
            for (_, g_, t_) in p["chain"]:
                if co_of.get(g_) == co_of.get(t_):
                    relay_within += 1
                else:
                    relay_cross += 1
        lineage_detail = dict(
            n_delivered=nd,
            hop_counts=hc,
            hop_shares=hop_shares,
            band_edges=list(LINEAGE_BANDS),
            band_mined=band_mined,
            band_delivered=band_delivered,
            charger_duty=round(duty, 4),
            charger_capacity=cap,
            energy_dispensed=round(w.energy_charged, 1),
            makespan=makespan,
            queue_wait=sum(w.company[c]["queue_wait"] for c in range(2)),
            holdup=_holdup_margins(dp, deals),
            relay_within=relay_within,          # P23b: within-company relay hops
            relay_cross=relay_cross,            # P23b: cross-company relay hops
        )
    # v17 PHASE 2: the mechanism rides the same snhp+net base (SnhpArm) — the
    # world flag IS the treatment, so relabel for the tables/pairings.
    base_label = "snhp+bill" if bills else ("snhp+firm" if firm_relay else arm_name)
    label = base_label if tuple(issues) == FULL else \
        f"{base_label}[{'+'.join(issues)}]"
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
        # v11 (column J): the moving field
        dynamic_field=dynamic_field, contested=contested,
        stock_lost=w.stock_lost,
        arrivals=len(w.arrival_indices),
        # units MINED from arrival rocks (provenance proxy for delivered: a
        # unit's origin asteroid is known at pick(), not at drop() — P16b)
        arrivals_mined=sum(w.mined_from[i] for i in w.arrival_indices),
        # v12 (column K): pricing the unknown
        scouting=scouting, map_trading=map_trading,
        prospect_claims=prospect_claims,
        scout_ticks=w.scout_ticks,             # K0: robot-ticks scouting
        map_deals=sum(1 for d in deals if d.get("m", 0) != 0),  # K1
        staleness_own_claims=(round(float(np.mean(stale_own)), 2)
                              if stale_own else None),          # K2 P17d
        staleness_other=(round(float(np.mean(stale_other)), 2)
                         if stale_other else None),
        # v13 (column L): scale
        n_robots=n_robots, consensus_cost=consensus_cost,
        delivered_frac=round(delivered_frac, 4),
        middleman_frac=round(middleman_frac, 4),
        # v14 (column O): communication locality
        gossip=gossip, r_radio=r_radio,
        freshness_deal_corr=freshness_deal_corr,
        freshness_deal_corr_null=freshness_deal_corr_null,
        # v17 (column P): cargo-lineage diagnosis
        lineage=lineage,
        lineage_detail=lineage_detail,
        # v17 PHASE 2 (column P): pre-commitment mechanisms
        bills=bills, firm_relay=firm_relay,
        # v22 (column U): reputation vs receipts
        reputation=reputation, false_accuse=false_accuse,
        **_reputation_metrics(w, arm),
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
            bool(r.get("mine_trait", False)),
            bool(r.get("dynamic_field", False)),
            bool(r.get("contested", False)),
            bool(r.get("scouting", False)),
            bool(r.get("map_trading", False)),
            bool(r.get("prospect_claims", False)),
            int(r.get("n_robots", 24)),
            bool(r.get("consensus_cost", False)),
            bool(r.get("gossip", False)),
            int(r.get("r_radio", 6)),
            bool(r.get("reputation", False)),
            r.get("false_accuse", 0.0))


def _cond_label(c) -> str:
    (f, dfd, s7, mg, nz, g, bm, race, mt, dyn, cnt, scout, maptr, pros,
     nr, cc, gs, rr, rep, fa) = c
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
    if dyn:
        bits.append("dyn")
    if cnt:
        bits.append("cnt")
    if scout:
        bits.append("K0")
    if maptr:
        bits.append("K1")
    if pros:
        bits.append("K2")
    if nr != 24:
        bits.append(f"N={nr}")
    if cc:
        bits.append("cc")
    if gs:
        bits.append(f"gossip r{rr}")     # v14: radius only meaningful w/ gossip
    if rep:
        bits.append("rep")               # v22: community reputation
    if fa:
        bits.append(f"ε={fa:g}")         # v22: false-accusation (slander) rate
    return " ".join(bits)


_BASE = (0.0, False, 0.0, False, 0.0, 32, False, True, False, False, False,
         False, False, False, 24, False, False, 6, False, 0.0)


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


def p21(rows: list[dict]) -> None:
    """v14 (column O): the communication-locality tables. Printed numbers ARE
    the artifact. No-op unless the sweep contains gossip rows."""
    orows = [r for r in rows if r.get("belief_mode") and r.get("dynamic_field")
             and r.get("contested") and r.get("scouting")]
    if not any(r.get("gossip") for r in orows):
        return

    def sel(arm, gossip, r_radio, maptr=False):
        return {r["seed"]: r for r in orows
                if r["arm"] == arm and bool(r.get("gossip", False)) == gossip
                and int(r.get("r_radio", 6)) == r_radio
                and bool(r.get("map_trading", False)) == maptr}

    def paired(hi, lo, field):
        common = sorted(s for s in set(hi) & set(lo)
                        if hi[s].get(field) is not None
                        and lo[s].get(field) is not None)
        if len(common) < 3:
            return None
        d = np.array([hi[s][field] - lo[s][field] for s in common], float)
        _, pt = stats.ttest_rel([hi[s][field] for s in common],
                                [lo[s][field] for s in common])
        try:
            _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
        except ValueError:
            pw = float("nan")
        return dict(delta=float(d.mean()), p_t=float(pt), p_w=float(pw),
                    wins=int((d > 0).sum()), n=len(common))

    def paired_self(m, f_hi, f_lo):
        common = sorted(s for s in m if m[s].get(f_hi) is not None
                        and m[s].get(f_lo) is not None)
        if len(common) < 3:
            return None
        d = np.array([m[s][f_hi] - m[s][f_lo] for s in common], float)
        try:
            _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
        except ValueError:
            pw = float("nan")
        return dict(delta=float(d.mean()), p_w=float(pw),
                    wins=int((d > 0).sum()), n=len(common))

    def mean_of(m, field):
        vals = [r[field] for r in m.values() if r.get(field) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def clabel(gossip, r_radio, maptr):
        if not gossip:
            return "free-radio"
        return f"gossip r{r_radio}" + ("+K1" if maptr else "")

    conds = [("auction", True, 2, False), ("auction", True, 6, False),
             ("rules", True, 2, False), ("rules", True, 6, False),
             ("snhp-hz", True, 2, False), ("snhp-hz", True, 6, False),
             ("snhp+net", True, 2, False), ("snhp+net", True, 6, False),
             ("snhp+net", False, 6, False), ("snhp+net", True, 6, True)]

    print("\n" + "=" * 78)
    print("P21 — COMMUNICATION LOCALITY (column O): trade is the network")
    print("=" * 78)
    hdr = (f"{'arm':<10} {'radio':<12} {'deliv':>7} {'strand':>7} {'stale':>7} "
           f"{'poison':>7} {'arrMin':>7} {'mapDl':>6} {'deals':>7} {'corr/null':>12}")
    print(hdr)
    print("-" * len(hdr))
    for arm, gs, rr, mt in conds:
        m = sel(arm, gs, rr, mt)
        if not m:
            continue
        corr, null = mean_of(m, "freshness_deal_corr"), mean_of(m, "freshness_deal_corr_null")
        cs = "—" if corr != corr else f"{corr:+.2f}/{0.0 if null!=null else null:+.2f}"
        print(f"{arm:<10} {clabel(gs, rr, mt):<12} "
              f"{mean_of(m,'delivered'):>7.1f} {mean_of(m,'stranded'):>7.2f} "
              f"{mean_of(m,'mean_staleness'):>7.1f} {mean_of(m,'poisoned'):>7.2f} "
              f"{mean_of(m,'arrivals_mined'):>7.1f} {mean_of(m,'map_deals'):>6.1f} "
              f"{mean_of(m,'deals'):>7.1f} {cs:>12}")

    print("\nP21a — trade IS the network (staleness vs auction, paired; Δ<0 ⇒ trader FRESHER):")
    for rr in (2, 6):
        au = sel("auction", True, rr)
        for arm in ("snhp+net", "snhp-hz", "rules"):
            c = paired(sel(arm, True, rr), au, "mean_staleness")
            if c:
                print(f"    r{rr}: {arm:>9} − auction   Δstale={c['delta']:+7.1f}  "
                      f"p_t={c['p_t']:.3f} p_w={c['p_w']:.3f} wins {c['wins']}/{c['n']}")

    print("\nP21b — books bleed first (gossip vs free-radio, paired; poisoned↑ delivered flat):")
    free = sel("snhp+net", False, 6)
    for rr in (2, 6):
        g = sel("snhp+net", True, rr)
        for field in ("poisoned", "delivered", "mean_staleness"):
            c = paired(g, free, field)
            if c:
                print(f"    snhp+net r{rr} − free-radio  {field:<14} Δ={c['delta']:+7.2f}  "
                      f"p_t={c['p_t']:.3f} p_w={c['p_w']:.3f} wins {c['wins']}/{c['n']}")

    print("\nP21c — trade graph == information graph (freshness_deal_corr vs shuffled null):")
    for arm, gs, rr, mt in [("snhp+net", True, 2, False), ("snhp+net", True, 6, False),
                            ("snhp+net", False, 6, False), ("snhp+net", True, 6, True),
                            ("snhp-hz", True, 6, False)]:
        m = sel(arm, gs, rr, mt)
        c = paired_self(m, "freshness_deal_corr", "freshness_deal_corr_null")
        if c:
            print(f"    {arm:>9} {clabel(gs,rr,mt):<11} corr={mean_of(m,'freshness_deal_corr'):+.3f} "
                  f"null={mean_of(m,'freshness_deal_corr_null'):+.3f}  "
                  f"Δ={c['delta']:+.3f} p_w={c['p_w']:.3f} wins {c['wins']}/{c['n']}")

    print("\nSCOUT-RETURN — arrivals_mined under gossip vs free radio "
          "(does v12 'scouting fixes discovery' survive?):")
    print(f"    free-radio snhp+net arrivals_mined = {mean_of(free,'arrivals_mined'):.1f}")
    for rr in (2, 6):
        g = sel("snhp+net", True, rr)
        c = paired(g, free, "arrivals_mined")
        au = sel("auction", True, rr)
        if c:
            print(f"    gossip r{rr}: snhp+net={mean_of(g,'arrivals_mined'):.1f} "
                  f"(Δ vs free {c['delta']:+.1f}, p_w={c['p_w']:.3f}) | "
                  f"auction={mean_of(au,'arrivals_mined'):.1f}")

    print("\nMAP-MARKET UNDER GOSSIP — snhp+net r6 +K1 vs r6 (paired):")
    mapm, base = sel("snhp+net", True, 6, True), sel("snhp+net", True, 6, False)
    print(f"    map_deals/run (K1) = {mean_of(mapm,'map_deals'):.1f}")
    for field in ("delivered", "poisoned", "arrivals_mined", "mean_staleness"):
        c = paired(mapm, base, field)
        if c:
            print(f"    +K1 − r6   {field:<14} Δ={c['delta']:+7.2f}  "
                  f"p_t={c['p_t']:.3f} p_w={c['p_w']:.3f} wins {c['wins']}/{c['n']}")


def diagnosis(rows: list[dict]) -> None:
    """v17 (column P) PHASE 1 — decompose the N=240 plateau into energy- /
    queue- / chain-bound signatures. Printed numbers ARE the artifact. No-op
    unless the sweep contains lineage rows."""
    lrows = [r for r in rows if r.get("lineage") and r.get("lineage_detail")]
    if not lrows:
        return

    def groups():
        return sorted({(r["arm"], int(r["n_robots"])) for r in lrows},
                      key=lambda k: (k[1], k[0]))

    def sel(arm, N):
        return [r for r in lrows
                if r["arm"] == arm and int(r["n_robots"]) == N]

    def det(g, path, default=np.nan):
        vals = []
        for r in g:
            d = r["lineage_detail"]
            for key in path:
                d = d[key] if d is not None else None
            if d is not None:
                vals.append(d)
        return vals

    print("\n" + "=" * 82)
    print("P (v17) PHASE 1 — DIAGNOSIS: decomposing the plateau (energy/queue/chain)")
    print("=" * 82)

    print("\n[1] HOP DISTRIBUTION of delivered units (share 0-hop / 1-hop / ≥2-hop):")
    h = f"  {'arm':<12} {'N':>4} {'deliv':>7} {'dFrac':>6} {'0-hop':>7} {'1-hop':>7} {'≥2-hop':>7} {'nParcels':>9}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for arm, N in groups():
        g = sel(arm, N)
        shares = np.array([r["lineage_detail"]["hop_shares"] for r in g], float)
        ms = shares.mean(axis=0)
        nd = np.mean([r["lineage_detail"]["n_delivered"] for r in g])
        dv = np.mean([r["delivered"] for r in g])
        df = np.mean([r["delivered_frac"] for r in g])
        print(f"  {arm:<12} {N:>4} {dv:>7.0f} {df:>6.3f} "
              f"{ms[0]:>7.3f} {ms[1]:>7.3f} {ms[2]:>7.3f} {nd:>9.0f}")

    print("\n[2] DELIVERED / MINED by refinery-distance band "
          f"(≤{LINEAGE_BANDS[0]} · {LINEAGE_BANDS[0]+1}-{LINEAGE_BANDS[1]} · >{LINEAGE_BANDS[1]}):")
    h = (f"  {'arm':<12} {'N':>4} {'near d/m':>13} {'mid d/m':>13} "
         f"{'far d/m':>13}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for arm, N in groups():
        g = sel(arm, N)
        bm = np.array([r["lineage_detail"]["band_mined"] for r in g], float).sum(axis=0)
        bd = np.array([r["lineage_detail"]["band_delivered"] for r in g], float).sum(axis=0)
        cells = []
        for j in range(3):
            frac = bd[j] / bm[j] if bm[j] > 0 else float("nan")
            cells.append(f"{bd[j]/len(g):>5.0f}/{bm[j]/len(g):<5.0f}={frac:>4.2f}")
        print(f"  {arm:<12} {N:>4} " + " ".join(f"{c:>13}" for c in cells))

    print("\n[3] CHARGER DUTY CYCLE + dispensed energy + queue wait:")
    h = (f"  {'arm':<12} {'N':>4} {'duty':>6} {'cap':>5} {'energy':>9} "
         f"{'dlv/E·100':>10} {'queueWait':>10} {'strand':>7}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for arm, N in groups():
        g = sel(arm, N)
        duty = np.mean([r["lineage_detail"]["charger_duty"] for r in g])
        cap = np.mean([r["lineage_detail"]["charger_capacity"] for r in g])
        en = np.mean([r["lineage_detail"]["energy_dispensed"] for r in g])
        dv = np.mean([r["delivered"] for r in g])
        qw = np.mean([r["lineage_detail"]["queue_wait"] for r in g])
        st = np.mean([r["stranded"] for r in g])
        dpe = 100.0 * dv / en if en > 0 else float("nan")
        print(f"  {arm:<12} {N:>4} {duty:>6.3f} {cap:>5.0f} {en:>9.0f} "
              f"{dpe:>10.3f} {qw:>10.0f} {st:>7.2f}")

    print("\n[4] HOLD-UP MARGIN LEDGER (≥2-hop legs; buy=surplus as buyer, "
          "sell=as seller; Δ<0 ⇒ compression):")
    h = (f"  {'arm':<12} {'N':>4} {'nLegs':>6} {'mean_buy':>9} {'mean_sell':>10} "
         f"{'meanΔ':>8} {'fracCompr':>10}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for arm, N in groups():
        g = sel(arm, N)
        legs = [r["lineage_detail"]["holdup"] for r in g]
        nlegs = np.sum([h_["n"] for h_ in legs])
        priced = [h_ for h_ in legs if h_["n"] > 0]
        if priced:
            mb = np.mean([h_["mean_buy"] for h_ in priced])
            msl = np.mean([h_["mean_sell"] for h_ in priced])
            md = np.mean([h_["mean_delta"] for h_ in priced])
            fc = np.mean([h_["frac_compressed"] for h_ in priced])
            print(f"  {arm:<12} {N:>4} {nlegs:>6.0f} {mb:>9.3f} {msl:>10.3f} "
                  f"{md:>8.3f} {fc:>10.3f}")
        else:
            print(f"  {arm:<12} {N:>4} {nlegs:>6.0f} {'—':>9} {'—':>10} "
                  f"{'—':>8} {'—':>10}")


def phase2(rows: list[dict]) -> None:
    """v17 (column P) PHASE 2 — the pre-commitment tables. Printed numbers ARE
    the artifact. No-op unless the sweep carries a bills OR firm_relay arm."""
    lrows = [r for r in rows if r.get("lineage") and r.get("lineage_detail")]
    if not any(r.get("bills") or r.get("firm_relay") for r in lrows):
        return
    # order arms spot → bill → firm → auction for the eye
    order = {"snhp+net": 0, "snhp+bill": 1, "snhp+firm": 2, "auction": 3}
    arms = sorted({r["arm"] for r in lrows}, key=lambda a: order.get(a, 9))
    Ns = sorted({int(r["n_robots"]) for r in lrows})

    def sel(arm, N):
        return [r for r in lrows
                if r["arm"] == arm and int(r["n_robots"]) == N]

    def det(g, path):
        vals = []
        for r in g:
            d = r["lineage_detail"]
            for k in path:
                d = d[k]
            vals.append(d)
        return vals

    def paired(arm_hi, arm_lo, N, field):
        hi = {r["seed"]: r[field] for r in sel(arm_hi, N)}
        lo = {r["seed"]: r[field] for r in sel(arm_lo, N)}
        common = sorted(set(hi) & set(lo))
        if len(common) < 3:
            return None
        d = np.array([hi[s] - lo[s] for s in common], float)
        _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
        try:
            _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
        except ValueError:
            pw = float("nan")
        return dict(delta=float(d.mean()), p_t=float(pt), p_w=float(pw),
                    wins=int((d > 0).sum()), n=len(common))

    print("\n" + "=" * 84)
    print("P (v17) PHASE 2 — PRE-COMMITMENT: bills of lading + firm relay vs the "
          "hold-up baseline")
    print("=" * 84)

    print("\n[1] DELIVERED_FRAC (arm × N) + ≥2-hop share of delivered units:")
    h = f"  {'arm':<12} {'N':>4} {'deliv':>7} {'dFrac':>7} {'0-hop':>7} {'1-hop':>7} {'≥2-hop':>7}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in arms:
            g = sel(arm, N)
            if not g:
                continue
            dv = np.mean([r["delivered"] for r in g])
            df = np.mean([r["delivered_frac"] for r in g])
            sh = np.array([r["lineage_detail"]["hop_shares"] for r in g], float).mean(axis=0)
            print(f"  {arm:<12} {N:>4} {dv:>7.0f} {df:>7.3f} "
                  f"{sh[0]:>7.3f} {sh[1]:>7.3f} {sh[2]:>7.3f}")

    print("\n[1b] P23a — bills − spot delivered_frac (paired; target ≥ +0.03):")
    for N in Ns:
        for arm in ("snhp+bill", "snhp+firm"):
            c = paired(arm, "snhp+net", N, "delivered_frac")
            if c:
                print(f"    N={N}: {arm:>9} − snhp+net  Δframe={c['delta']:+.4f}  "
                      f"p_t={c['p_t']:.3f} p_w={c['p_w']:.3f} wins {c['wins']}/{c['n']}")

    print("\n[2] FAR-BAND delivered/mined "
          f"(≤{LINEAGE_BANDS[0]} · {LINEAGE_BANDS[0]+1}-{LINEAGE_BANDS[1]} · >{LINEAGE_BANDS[1]}):")
    h = f"  {'arm':<12} {'N':>4} {'near d/m':>13} {'mid d/m':>13} {'far d/m':>13}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in arms:
            g = sel(arm, N)
            if not g:
                continue
            bm = np.array([r["lineage_detail"]["band_mined"] for r in g], float).sum(axis=0)
            bd = np.array([r["lineage_detail"]["band_delivered"] for r in g], float).sum(axis=0)
            cells = []
            for j in range(3):
                frac = bd[j] / bm[j] if bm[j] > 0 else float("nan")
                cells.append(f"{bd[j]/len(g):>5.0f}/{bm[j]/len(g):<5.0f}={frac:>4.2f}")
            print(f"  {arm:<12} {N:>4} " + " ".join(f"{c:>13}" for c in cells))

    print("\n[3] MARGIN COMPRESSION (≥2-hop legs; Δ<0 ⇒ hold-up compression) + "
          "RELAY reach (within/cross company hops):")
    h = (f"  {'arm':<12} {'N':>4} {'nLegs':>6} {'mean_buy':>9} {'mean_sell':>10} "
         f"{'meanΔ':>8} {'fracCompr':>10} {'within':>7} {'cross':>6}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in arms:
            g = sel(arm, N)
            if not g:
                continue
            legs = [r["lineage_detail"]["holdup"] for r in g]
            nlegs = np.sum([h_["n"] for h_ in legs])
            priced = [h_ for h_ in legs if h_["n"] > 0]
            rw = np.mean([r["lineage_detail"]["relay_within"] for r in g])
            rc = np.mean([r["lineage_detail"]["relay_cross"] for r in g])
            if priced:
                mb = np.mean([h_["mean_buy"] for h_ in priced])
                msl = np.mean([h_["mean_sell"] for h_ in priced])
                md = np.mean([h_["mean_delta"] for h_ in priced])
                fc = np.mean([h_["frac_compressed"] for h_ in priced])
                print(f"  {arm:<12} {N:>4} {nlegs:>6.0f} {mb:>9.3f} {msl:>10.3f} "
                      f"{md:>8.3f} {fc:>10.3f} {rw:>7.1f} {rc:>6.1f}")
            else:
                print(f"  {arm:<12} {N:>4} {nlegs:>6.0f} {'—':>9} {'—':>10} "
                      f"{'—':>8} {'—':>10} {rw:>7.1f} {rc:>6.1f}")


def u_report(rows: list[dict]) -> None:
    """v22 (column U) — reputation vs receipts: the scaling law of trust. Printed
    numbers ARE the artifact. Report, don't verdict (P28a/b/c are read off the
    tables). No-op unless the sweep carries a reputation regime."""
    if not any(r.get("reputation") for r in rows):
        return
    urows = [r for r in rows if str(r.get("arm", "")).startswith("trust-")]
    if not urows:
        return

    def regime(r) -> str:
        rep, gated = bool(r.get("reputation")), "gated" in r["arm"]
        if gated and rep:
            return "both"        # (c)
        if gated:
            return "attest"      # (b) attestation-only
        if rep:
            return "reput"       # (a) reputation-only
        return "neither"         # (d) exploitation baseline

    ORDER = {"neither": 0, "reput": 1, "attest": 2, "both": 3}
    Ns = sorted({int(r["n_robots"]) for r in urows})

    def sel(reg, N, eps):
        return [r for r in urows if regime(r) == reg and int(r["n_robots"]) == N
                and abs(float(r.get("false_accuse", 0.0)) - eps) < 1e-12]

    def mean(g, field):
        vals = [r[field] for r in g if r.get(field) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def liar_adv(g):
        vals = [r["liar_credit"] - r["honest_credit"] for r in g
                if r.get("liar_credit") is not None
                and r.get("honest_credit") is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def cells(reg):
        # (reput-only / both) run at ε∈{0,0.05}; (attest / neither) only ε=0
        return (0.0, 0.05) if reg in ("reput", "both") else (0.0,)

    print("\n" + "=" * 96)
    print("P28 (column U) — REPUTATION vs RECEIPTS: the scaling law of trust "
          "(liar_frac=0.25, snhp trust arms)")
    print("=" * 96)

    print("\n[1] HONEST-COOPERATION PAYOFF & LIAR ADVANTAGE (regime × N × ε):")
    print("    honest = mean honest-robot credit · liar = mean liar credit · "
          "adv = liar − honest (↑ ⇒ lying pays)")
    h = (f"  {'regime':<9} {'N':>4} {'ε':>5} {'honest':>8} {'liar':>8} "
         f"{'adv':>8} {'deliv':>7} {'deals':>7} {'blMean':>7} {'falseBL':>8} "
         f"{'reEnc':>7}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for reg in sorted({regime(r) for r in urows}, key=lambda x: ORDER[x]):
        for N in Ns:
            for eps in cells(reg):
                g = sel(reg, N, eps)
                if not g:
                    continue
                bl = mean(g, "blacklist_mean")
                fb = mean(g, "false_bl_frac")
                print(f"  {reg:<9} {N:>4} {eps:>5.2f} "
                      f"{mean(g,'honest_credit'):>8.1f} {mean(g,'liar_credit'):>8.1f} "
                      f"{liar_adv(g):>+8.1f} {mean(g,'delivered'):>7.1f} "
                      f"{mean(g,'deals'):>7.1f} "
                      f"{'—' if bl != bl else f'{bl:>7.2f}'} "
                      f"{'—' if fb != fb else f'{fb:>8.3f}'} "
                      f"{mean(g,'reencounter_rate'):>7.2f}")

    print("\n[2] RE-ENCOUNTER RATE by N × regime (mean post-cooldown meetings "
          "per distinct pair — the mechanism's driver).")
    print("    CAVEAT: high-deal regimes (neither/attest) are CONFOUNDED by "
          "deal-pause immobilization (a struck deal freezes both parties + a")
    print("    longer cooldown); the LOW-deal reputation regimes (reput/both, "
          "which refuse most encounters) show the clean geometric fall with N.")
    h = (f"  {'N':>4} {'reput':>8} {'both':>8} {'attest':>8} {'neither':>8} "
         f"{'grid':>6}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    import math as _m
    for N in Ns:
        def rr(reg):
            return mean(sel(reg, N, 0.0), "reencounter_rate")
        print(f"  {N:>4} {rr('reput'):>8.1f} {rr('both'):>8.1f} "
              f"{rr('attest'):>8.1f} {rr('neither'):>8.1f} "
              f"{int(round(32 * _m.sqrt(N / 24))):>6}")

    print("\n[3] P28a [REGISTERED PREDICTION, read the numbers] — reputation's "
          "honest payoff decays with N (re-encounter falls) while attestation is "
          "N-flat; a crossover N exists (honest_credit at ε=0):")
    h = f"  {'N':>4} {'reput':>9} {'attest':>9} {'both':>9} {'neither':>9}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        vals = {reg: mean(sel(reg, N, 0.0), "honest_credit")
                for reg in ("reput", "attest", "both", "neither")}
        print(f"  {N:>4} {vals['reput']:>9.1f} {vals['attest']:>9.1f} "
              f"{vals['both']:>9.1f} {vals['neither']:>9.1f}")

    print("\n[4] P28b [REGISTERED PREDICTION, read the numbers] — slander (ε) "
          "degrades reputation (honest blacklisted, payoff drops) while "
          "attestation is ε-immune (no blacklist channel):")
    h = (f"  {'regime':<9} {'N':>4} {'honest@ε0':>10} {'honest@ε.05':>12} "
         f"{'Δhonest':>9} {'falseBL@ε0':>11} {'falseBL@ε.05':>13}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for reg in ("reput", "both"):
        for N in Ns:
            g0, ge = sel(reg, N, 0.0), sel(reg, N, 0.05)
            if not g0 or not ge:
                continue
            h0, he = mean(g0, "honest_credit"), mean(ge, "honest_credit")
            print(f"  {reg:<9} {N:>4} {h0:>10.1f} {he:>12.1f} {he - h0:>+9.1f} "
                  f"{mean(g0,'false_bl_frac'):>11.3f} "
                  f"{mean(ge,'false_bl_frac'):>13.3f}")

    print("\n[5] P28c [REGISTERED PREDICTION, read the numbers] — receipts "
          "subsume reputation: (both) ≈ (attest) at large N (honest_credit & "
          "delivered, ε=0):")
    h = (f"  {'N':>4} {'both_honest':>12} {'attest_honest':>14} "
         f"{'both_deliv':>11} {'attest_deliv':>13}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        gb, ga = sel("both", N, 0.0), sel("attest", N, 0.0)
        print(f"  {N:>4} {mean(gb,'honest_credit'):>12.1f} "
              f"{mean(ga,'honest_credit'):>14.1f} "
              f"{mean(gb,'delivered'):>11.1f} {mean(ga,'delivered'):>13.1f}")


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
    if column == "J":                 # v11: the moving field (P16)
        moving = dict(belief_mode=True, dynamic_field=True, contested=True)
        for arm in ("auction", "snhp-hz", "snhp+net", "team"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5", **moving))
        # P16a: oracle control — SAME dynamic+contested world, omniscient Φ
        # (belief off); the belief-vs-oracle gap is the price of a stale map
        # in a MOVING field (v10 measured it zero on a static one)
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             dynamic_field=True, contested=True))
        # P16c: racing-blind ablation — beliefs on, race pricing off, in the
        # contested moving field where the race finally has overlap to price
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             belief_mode=True, dynamic_field=True,
                             contested=True, race_pricing=False))
    if column == "K":                 # v12: pricing the unknown (P17)
        # everything rides the v11 moving field: belief + dynamic + contested
        moving = dict(belief_mode=True, dynamic_field=True, contested=True)
        # auction + K0 (scouting) — the movement-policy treatment on a coverage
        # baseline (the auction out-collected arrivals in v11 by accident)
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="auction", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             scouting=True, **moving))
        # snhp+net + K0 · +K0+K1 (map trading) · +K0+K1+K2 (prospect claims):
        # the ladder that prices the unknown one layer at a time
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             scouting=True, **moving))
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             scouting=True, map_trading=True, **moving))
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             scouting=True, map_trading=True,
                             prospect_claims=True, **moving))
        # oracle control: SAME dynamic+contested world, omniscient Φ (belief
        # off) and NO K flags — scouting requires belief_mode, so the oracle
        # runs plain, exactly as v11's P16a oracle did
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                             ticks=ticks, tau=0.15, preset="v5",
                             dynamic_field=True, contested=True))
    if column == "L":                 # v13: scale (P18) — density-fixed N
        # N ∈ {24, 96, 240} at FIXED density; grid = round(32·√(N/24)); the
        # world scales asteroid count, stock pin and charger count with N.
        # team-costed = TeamArm with consensus_cost=True (pause grows with N);
        # team-free = TeamArm without it (free-planning ceiling control).
        import math as _math
        specs = [("auction", False), ("snhp+net", False),
                 ("team", True), ("team", False)]   # (arm, consensus_cost)
        for N in (24, 96, 240):
            grid = int(round(32 * _math.sqrt(N / 24)))
            # N=240 core arms only (drop team-free), 8-seed compute cap;
            # N=24/96 all four arms at up to 16 seeds. Caps enforced HERE.
            arms_L = specs if N < 240 else specs[:3]
            n_seeds = min(seeds, 16) if N < 240 else min(seeds, 8)
            for arm_name, cc in arms_L:
                for seed in range(n_seeds):
                    jobs.append(dict(arm_name=arm_name, sigma=0.5, seed=seed,
                                     ticks=ticks, tau=0.15, preset="v5",
                                     n_robots=N, grid=grid, consensus_cost=cc))
    if column == "O":                 # v14: communication locality (P21)
        # Everything rides the v11 moving+contested field with belief maps and
        # K0 scouting ON everywhere (the free-radio K column's scouting baseline
        # IS the gossip control). gossip removes the company radio: fleet-mates
        # only relay within Chebyshev r_radio. The ladder r_radio ∈ {2, 6}
        # separates "needs any locality" (contact/stigmergy) from "needs range"
        # (short radio) — the founder's amendment.
        base = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                    belief_mode=True, dynamic_field=True, contested=True,
                    scouting=True)
        for arm in ("auction", "rules", "snhp-hz", "snhp+net"):
            for r_radio in (2, 6):
                for seed in range(min(seeds, 16)):
                    jobs.append(dict(arm_name=arm, seed=seed, gossip=True,
                                     r_radio=r_radio, **base))
        # free-radio control: belief maps + K0 but company-wide radio (gossip
        # off) — the P21b/scout-return reference (== the K column's snhp+net+K0)
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", seed=seed, gossip=False,
                             **base))
        # the map market UNDER gossip (r_radio=6): does priced cross-company
        # map-selling add anything once within-fleet radio is only local?
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", seed=seed, gossip=True,
                             r_radio=6, map_trading=True, **base))
    if column == "P":                 # v17: relays/hold-up DIAGNOSIS (P1 only)
        # Decompose the N=240 plateau before any mechanism is credited. All runs
        # carry lineage=True (pure bookkeeping). N=240 scaled grid × 8 seeds ×
        # {auction, snhp+net, team-costed}; plus an N=24 baseline (16 seeds,
        # snhp+net + auction) for the hop-distribution contrast.
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        for arm_name, cc in (("auction", False), ("snhp+net", False),
                             ("team", True)):
            for seed in range(min(seeds, 8)):
                jobs.append(dict(arm_name=arm_name, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 n_robots=240, grid=g240, consensus_cost=cc,
                                 lineage=True))
        for arm_name in ("snhp+net", "auction"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name=arm_name, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 n_robots=24, lineage=True))
    if column == "P2":                # v17 PHASE 2: pre-commitment mechanisms
        # The GATE is OPEN (chain signature present). N=240 scaled grid × 8 seeds
        # × {auction (no-relay), snhp+net spot (hold-up baseline), snhp+bill
        # (negotiable claims), snhp+firm (vertical integration)}; plus an N=24
        # baseline (16 seeds, snhp+net + snhp+bill) for the hop-distribution
        # regression. All carry lineage (bills/firm imply it). snhp+bill/+firm ride
        # the snhp+net base with the world flag as the treatment.
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        base240 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True)
        variants = [dict(arm_name="auction"), dict(arm_name="snhp+net"),
                    dict(arm_name="snhp+net", bills=True),
                    dict(arm_name="snhp+net", firm_relay=True)]
        for v in variants:
            for seed in range(min(seeds, 8)):
                jobs.append(dict(seed=seed, **base240, **v))
        for v in (dict(arm_name="snhp+net"), dict(arm_name="snhp+net", bills=True)):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(seed=seed, sigma=0.5, ticks=ticks, tau=0.15,
                                 preset="v5", n_robots=24, lineage=True, **v))
    if column == "U":                 # v22: reputation vs receipts (P28)
        # Liars (v6) vs three enforcement regimes, following the column-E arm
        # pattern (TrustArm): trust-gated where attestation applies, trust-open
        # for reputation-only and the exploitation baseline. σ=0.5, τ=0.15, v5
        # scaled grids. reputation regimes run at ε∈{0,0.05}; the reputation-off
        # regimes (attestation-only, neither) run once — ε has no channel there.
        import math as _math
        # (arm, defended, reputation) — the four registered regimes
        specs = [("trust-open-hz",  False, True),    # (a) reputation-only
                 ("trust-gated-hz", True,  False),   # (b) attestation-only
                 ("trust-gated-hz", True,  True),    # (c) both
                 ("trust-open-hz",  False, False)]   # (d) neither (baseline)
        for N in (24, 96, 240):
            grid = int(round(32 * _math.sqrt(N / 24)))
            n_seeds = min(seeds, 16) if N < 240 else min(seeds, 8)
            for arm_name, defended, reputation in specs:
                eps_vals = (0.0, 0.05) if reputation else (0.0,)
                for eps in eps_vals:
                    for seed in range(n_seeds):
                        jobs.append(dict(arm_name=arm_name, sigma=0.5, seed=seed,
                                         ticks=ticks, tau=0.15, preset="v5",
                                         n_robots=N, grid=grid, liar_frac=0.25,
                                         defended=defended, reputation=reputation,
                                         false_accuse=eps))
    if column == "UH":                # v22 P28-H horizon amendment (registered)
        # IDENTICAL to the column-U N=240, ε=0 cells, but at the fair horizon
        # (ticks=7,500 = 3× the sweep_v4_U 2,500). No new mechanism: same four
        # column-E TrustArm regimes, same v5 scaled grid (N=240 ⇒ grid=101),
        # liar_frac=0.25, σ=0.5, τ=0.15, 8 seeds. THE question: does
        # attestation's cooperative tier recoup the DEAL_PAUSE tax at horizon
        # (does the 2,500-tick reput>attest reversal narrow / flip / hold).
        import math as _math
        specs = [("trust-open-hz",  False, True),    # (a) reputation-only
                 ("trust-gated-hz", True,  False),   # (b) attestation-only
                 ("trust-gated-hz", True,  True),    # (c) both
                 ("trust-open-hz",  False, False)]   # (d) neither (baseline)
        N = 240
        grid = int(round(32 * _math.sqrt(N / 24)))
        n_seeds = min(seeds, 8)
        for arm_name, defended, reputation in specs:
            for seed in range(n_seeds):
                jobs.append(dict(arm_name=arm_name, sigma=0.5, seed=seed,
                                 ticks=ticks, tau=0.15, preset="v5",
                                 n_robots=N, grid=grid, liar_frac=0.25,
                                 defended=defended, reputation=reputation,
                                 false_accuse=0.0))
    if column == "bridge":
        for arm in ("snhp", "auction"):
            for seed in range(8):
                jobs.append(dict(arm_name=arm, sigma=1.0, seed=seed,
                                 ticks=ticks, preset="v3"))
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--column", default="A", choices=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "O", "P", "P2", "U", "UH", "all", "bridge"])
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
        p21(rows)
        diagnosis(rows)
        phase2(rows)
        u_report(rows)
        return

    jobs = build_jobs(args.column, args.seeds, args.ticks)
    out = args.out or os.path.join(_HERE, "results",
                                   f"sweep_v4_{args.column}.json")
    if args.jobs > 1:
        # imap_unordered streams each run back the moment it finishes, so the
        # FIRST completion's wall-clock gives an early tractability estimate
        # (progress + ETA to stderr). Order-independent: rows self-describe by
        # (arm, n_robots, seed, false_accuse), and every summary groups on keys.
        import time as _time
        t0 = _time.time()
        rows = []
        with Pool(args.jobs) as pool:
            for i, row in enumerate(
                    pool.imap_unordered(_star, jobs, chunksize=1), 1):
                rows.append(row)
                el = _time.time() - t0
                eta = el / i * (len(jobs) - i)
                print(f"[{i}/{len(jobs)}] {el:8.1f}s elapsed · "
                      f"~{eta:8.1f}s remaining", file=sys.stderr, flush=True)
    else:
        rows = [_star(j) for j in jobs]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rows, f, indent=1)
    print(f"\n{len(rows)} runs → {out}\n")
    summarize(rows)
    contrasts(rows)
    p21(rows)
    diagnosis(rows)
    phase2(rows)
    u_report(rows)


if __name__ == "__main__":
    main()

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

from swarm.arms import CLAIM_OPTS, make_arm
from swarm.world import (BUILD_CREDIT_COST, CCP_FEE, CHARGE_SLOTS,
                         DEBT_ENERGY_PRICE, DWELL_DECAY_LAMBDA, FLATLINE_TICKS,
                         MATTER_COST,
                         SHOCK_FAR_PCTL, SHOCK_VALUE_FLOOR, TOLL_GRID,
                         TOTAL_STOCK, V_DELIVER, WEAROUT_AGE, WEAROUT_P, World,
                         manhattan)

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


def _gini(vals) -> float:
    """v25 (column X): per-drone payoff dispersion. 0 = every drone paid equally,
    →1 = one drone captures all. Clamped ≥0 credit; empty/zero-sum → 0."""
    a = np.sort(np.array(vals, dtype=float))
    n = len(a)
    tot = a.sum()
    if n == 0 or tot <= 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * a)) / (n * tot) - (n + 1) / n)


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


def mx_counts(deals, keys=("cargo", "energy", "claims")):
    """v30 (column M2): the medium-of-exchange index counts over a deal list.
    Each deal has signed legs q (cargo), e (energy), t (claim endorsement); a
    commodity x "is the medium" in a bundle when it moves OPPOSITE to some OTHER
    commodity moving the other way (x sits on the far side from a good being
    acquired — the v15/P19c definition). Returns (moves, opposite, face) dicts;
    M(x) = opposite[x] / moves[x]. face is the total value moved as each medium
    (cargo |q|·V, claims |t|, energy |e|), the flow-share numerator/denominator."""
    mv = {k: 0 for k in keys}
    op = {k: 0 for k in keys}
    face = {k: 0.0 for k in keys}
    for d in deals:
        dq = (d["q"] > 0) - (d["q"] < 0)
        de = (d["e"] > 0) - (d["e"] < 0)
        dt = (d.get("t", 0.0) > 0) - (d.get("t", 0.0) < 0)
        sgn = {"cargo": dq, "energy": de, "claims": dt}
        pres = [k for k in keys if sgn[k] != 0]
        for x in pres:
            mv[x] += 1
            if any(sgn[y] == -sgn[x] for y in pres if y != x):
                op[x] += 1
        face["cargo"] += abs(d["q"]) * V_DELIVER
        face["claims"] += abs(d.get("t", 0.0))
        face["energy"] += abs(d["e"])
    return mv, op, face


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
             firm_relay: bool = False, dwell: bool = False,
             bills_contingent: bool = False,
             claims_transferable: bool = False, reputation: bool = False,
             false_accuse: float = 0.0, order_book: bool = False,
             build_matter: float = 0.0, build: bool = False,
             toll_level: float = 0.0, build_budget: int = 10**9,
             command: bool = False, deadlock_track: bool = False,
             charger_band: float = 0.0, nav_dumb: bool = False,
             forgery: bool = False, forge_cost: float = 0.0,
             verify_cost: float = 0.0, verify_regime: str = "none",
             mortality: bool = False, death_regime: str = "none",
             wearout: bool = False,
             shock: bool = False, shock_tick: int | None = None,
             clearinghouse: bool = False, depots: bool = False,
             debt_ltv: float = 0.0) -> dict:
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
              dwell=dwell, bills_contingent=bills_contingent,
              claims_transferable=claims_transferable,
              reputation=reputation, false_accuse=false_accuse,
              order_book=order_book,
              build_matter=build_matter, build=build,
              toll_level=toll_level, build_budget=build_budget,
              command=command, deadlock_track=deadlock_track,
              charger_band=charger_band, nav_dumb=nav_dumb,
              forgery=forgery, forge_cost=forge_cost,
              verify_cost=verify_cost, verify_regime=verify_regime,
              mortality=mortality, death_regime=death_regime, wearout=wearout,
              shock=shock, shock_tick=shock_tick, clearinghouse=clearinghouse,
              depots=depots,
              debt_ltv=debt_ltv)
    arm = make_arm(base, w, issues=issues, noise=noise)
    makespan = ticks
    # v29 (column AB): sample the CCP fee-pool trajectory (and the far-band exposure)
    # once per window across the run — the scar/pool trajectory reads it. Windowed so
    # the row stays small at 7,500 ticks. No-op unless shock/clearinghouse is on.
    _pab = shock or clearinghouse
    _WIN = 250
    _pool_traj = []
    # v30 (column M2): window-snapshot the OUTSTANDING-claim population's maturity
    # (mean distance-to-refinery = risk proxy) so the endorsed-claim maturity can be
    # read against the pool it was drawn from (the good-collateral question). No-op
    # unless claims_transferable ⇒ every prior column bit-identical.
    _CWIN = 500
    _claim_pop = []
    delivered_mid = 0
    stale = []          # v10 P15b: mean (tick − last_seen) over all
    stale_own, stale_other = [], []   # v12 K2 P17d: patrol differentiation
    for t in range(ticks):        # (company, asteroid) pairs, every 50 ticks
        arm.tick()
        if _pab and (t + 1) % _WIN == 0:       # v29: window the CCP pool trajectory
            _pool_traj.append(round(w.ccp_pool, 3))
        if claims_transferable and (t + 1) % _CWIN == 0:
            ds, hs, n = [], [], 0
            for rr in w.robots:
                for pp in rr.parcels:
                    cl = pp.get("claims")
                    if not cl:
                        continue
                    dref = min(manhattan(rr.pos, rf) for rf in w.refineries)
                    for _e in cl:
                        ds.append(dref)
                        hs.append(pp["hops"])
                        n += 1
            _claim_pop.append((t + 1, n,
                               round(float(np.mean(ds)), 2) if ds else 0.0,
                               round(float(np.mean(hs)), 3) if hs else 0.0))
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
    assert w.credit_conserved(), "credit leak"        # v29 (column AB): CCP + shock
    assert w.debt_conserved(), "debt leak"            # v32 (column AB2): treasury waterfall
    assert w.matter_conserved(), "matter leak"        # v18 (column Q)
    assert w.toll_conserved(), "toll leak"            # v18 (column Q)

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
    # P23e (column P phase-2e): dwell instrumentation blob (only when dwell is on).
    # Per-carrier leg excess (dwell above the geodesic counterfactual) split into
    # relay (handoff) legs vs the final delivery leg, and per-delivered-parcel
    # journey inflation split by relay depth (0 / 1 / ≥2 hops). The KILL metric is
    # ≥2-hop inflation under bills-flat: no inflation ⇒ no moral hazard to price.
    dwell_detail = None
    if getattr(w, "dwell", False):
        def _qstats(vals):
            if not vals:
                return dict(n=0, mean=0.0, median=0.0, p90=0.0, total=0.0)
            arr = np.array(vals, float)
            return dict(n=len(arr), mean=float(arr.mean()),
                        median=float(np.median(arr)),
                        p90=float(np.percentile(arr, 90)),
                        total=float(arr.sum()))
        hop = w.hop_dwells
        dd = w.delivered_dwells
        relay = [h for h in hop if not h["final"]]
        dwell_detail = dict(
            n_legs=len(hop), n_relay_legs=len(relay),
            leg_excess=_qstats([h["excess"] for h in hop]),
            relay_leg_excess=_qstats([h["excess"] for h in relay]),
            final_leg_excess=_qstats([h["excess"] for h in hop if h["final"]]),
            deliv_inflation=_qstats([d["inflation"] for d in dd]),
            deliv_total_dwell=_qstats([d["total_dwell"] for d in dd]),
            deliv_total_cf=_qstats([d["total_cf"] for d in dd]),
            inflation_by_hops=[
                _qstats([d["inflation"] for d in dd if min(2, d["hops"]) == hh])
                for hh in (0, 1, 2)],
            decay_lambda=DWELL_DECAY_LAMBDA,
        )
    # v23 (column V): order-book accounting blob (only when order_book is on).
    # Posted/accepted/expired counts, pause-ticks saved (the DEAL_PAUSE NOT paid
    # on unilateral acceptance — the mechanism's registered advantage, reported
    # explicitly), async-trade share of deals, encounter rate (post-cooldown
    # meetings per tick — P29b needs async-share vs encounter-rate), and the
    # escrow-conservation finals (pinned/escrow should retire to ~0).
    order_book_detail = None
    if w.order_book:
        total_meets = sum(arm._pair_meets.values())
        acc, sync = w.orders_accepted, arm.deals
        order_book_detail = dict(
            posted=w.orders_posted, accepted=acc, expired=w.orders_expired,
            pause_ticks_saved=w.pause_ticks_saved,
            sync_deals=sync,
            async_share=round(acc / max(1, acc + sync), 4),
            encounter_rate=round(total_meets / max(1, makespan), 4),
            total_meets=total_meets,
            pinned_final=w.pinned_cargo, escrow_final=round(w.escrowed_energy, 6),
            escrow_paid=round(w.escrow_energy_paid, 4),
            escrow_refunded=round(w.escrow_energy_refunded, 4),
            escrow_writeoff=round(w.escrow_energy_writeoff, 4),
            cargo_writeoff=w.cargo_writeoff,
            escrow_ok=bool(w.escrow_conserved()),
        )
    # v18 (column Q): endogenous-infrastructure blob (only when the matter field is
    # seeded). Built-charger count/timing, the placement map (built sites vs their
    # forgone-far-ore rock), matter economy, and the toll-booth throughput
    # (guest slot-fills served AT built chargers + toll revenue) — the P24 numbers.
    build_detail = None
    if build_matter > 0:
        bl = w.built_log
        built_ticks = [b["tick"] for b in bl]
        # far-ore decay reference: mined-vs-stranded is not tracked per rock, but the
        # placement rocks' distance-from-refinery band shows WHERE building clustered.
        rock_bands = []
        for b in bl:
            src = w.sources[b["rock"]] if b["rock"] >= 0 else None
            if src is not None:
                d = min(manhattan(src, rf) for rf in w.refineries)
                rock_bands.append(_dist_band(d))
        band_hist = [rock_bands.count(k) for k in (0, 1, 2)]
        # v18-R (column Q2): band of the built-charger SITE itself (distance to the
        # nearest refinery), for ALL builds — trapped-return (rock=-1) sites included,
        # which the placement_band_hist (fallback-only) drops. Shows where CAPITAL
        # actually lands under frontier scarcity (built stepping-stones sit ~0.9·reach).
        site_bands = [_dist_band(min(manhattan(tuple(b["pos"]), rf)
                                     for rf in w.refineries)) for b in bl]
        site_band_hist = [site_bands.count(k) for k in (0, 1, 2)]
        build_detail = dict(
            built=[w.company[c]["built"] for c in (0, 1)],
            n_built=len(bl),
            first_built=(min(built_ticks) if built_ticks else None),
            median_built_tick=(float(np.median(built_ticks)) if built_ticks else None),
            late_built=sum(1 for t in built_ticks if t > makespan // 2),
            matter_mined=w.matter_mined, matter_initial=w.matter_initial,
            matter_pool=[round(w.company[c]["matter"], 1) for c in (0, 1)],
            build_spend=[round(w.company[c]["build_spend"], 1) for c in (0, 1)],
            build_credit_cost=BUILD_CREDIT_COST, matter_cost=MATTER_COST,
            built_guest_slots=w.built_guest_slots,     # slot-fills served to guests
            toll_earned=[round(w.company[c]["toll_earned"], 2) for c in (0, 1)],
            toll_paid=[round(w.company[c]["toll_paid"], 2) for c in (0, 1)],
            toll_level=toll_level, toll_grid=list(TOLL_GRID),
            placement_band_hist=band_hist,             # fallback TARGET rocks by band
            site_band_hist=site_band_hist,             # ALL built SITES by band (Q2)
            built_sites=[list(b["pos"]) for b in bl],
            built_forgone=[b["forgone"] for b in bl],
            n_chargers_final=len(w.chargers),
            n_matter_rocks=len(w.matter_sources),
            matter_conserved=bool(w.matter_conserved()),
            toll_conserved=bool(w.toll_conserved()),
        )
    # v28 (column AA): mortality + freeze-out blob (only when mortality is on).
    # Death counts by cause, the destroyed/inherited claim credit, and the
    # freeze-out instrument: chain-FEASIBLE encounters vs realized chain (cargo)
    # deals, bucketed by the potential giver's mortality HAZARD (4 fixed bins over
    # [0,1]) and by its absolute BATTERY fraction (4 bins). chain-deal rate per bin
    # = cargo/feasible, poolable across seeds; under claims-die the high-hazard bins
    # should fall below estates (the dying frozen out of the claims economy).
    mortality_detail = None
    if getattr(w, "mortality", False):
        def _bin4(x):
            return min(3, max(0, int(x * 4)))
        haz_feas = [0, 0, 0, 0]; haz_cargo = [0, 0, 0, 0]
        bat_feas = [0, 0, 0, 0]; bat_cargo = [0, 0, 0, 0]
        for f in w.freeze_log:
            hb = _bin4(f["haz"]); bb = _bin4(f["bat"])
            haz_feas[hb] += 1; haz_cargo[hb] += f["cargo"]
            bat_feas[bb] += 1; bat_cargo[bb] += f["cargo"]
        mortality_detail = dict(
            regime=death_regime,
            deaths=w.deaths, death_flatline=w.death_flatline,
            death_wearout=w.death_wearout,
            claims_voided=round(w.claims_voided, 4),
            estate_settled=round(w.estate_settled, 4),
            wearout=wearout, wearout_age=WEAROUT_AGE, wearout_p=WEAROUT_P,
            flatline_ticks=FLATLINE_TICKS,
            n_freeze=len(w.freeze_log),
            freeze_haz_feasible=haz_feas, freeze_haz_cargo=haz_cargo,
            freeze_bat_feasible=bat_feas, freeze_bat_cargo=bat_cargo,
            deaths_bat_pct=[d["bat_pct"] for d in w.death_log],
            deaths_own_claim=[d["own_claim"] for d in w.death_log],
        )
        # v29 (column AB): the SCAR series — chain deals (cargo, q≠0), deaths and
        # strand ONSETS binned per WINDOW. Lives on mortality_detail so BOTH the shock
        # cells and their no-shock controls carry it (the scar is a shock-vs-control
        # contrast). Cheap; poolable across seeds.
        _nwin = makespan // _WIN + 1
        _chain = [0] * _nwin; _dwin = [0] * _nwin; _swin = [0] * _nwin
        for d in deals:
            if d["q"] != 0:
                _chain[min(_nwin - 1, d["tick"] // _WIN)] += 1
        for d in w.death_log:
            _dwin[min(_nwin - 1, d["tick"] // _WIN)] += 1
        for (tk, _rid) in w.strand_log:
            _swin[min(_nwin - 1, tk // _WIN)] += 1
        mortality_detail["window"] = _WIN
        mortality_detail["n_windows"] = _nwin
        mortality_detail["chain_by_window"] = _chain
        mortality_detail["death_by_window"] = _dwin
        mortality_detail["strand_by_window"] = _swin
    # v29 (column AB): the crash blob (only when shock/clearinghouse is on). The
    # contagion-depth HISTOGRAM (write-down $ by hop-distance from the darkened
    # region — hop 0 = direct victims, ≥1 = contagion), the direct/contagion split,
    # the SCAR (chain-deal / death / strand-onset counts per WINDOW, so the reporter
    # can read pre- vs post-shock rate + recovery), and the CCP pool accounting +
    # trajectory. Poolable across seeds. No-op unless the shock/CCP is on.
    shock_detail = None
    if shock or clearinghouse:
        HOPCAP = 6                     # bin hops 0..5, ≥6 folds into the last bin
        wd_exp = [0.0] * (HOPCAP + 1)  # Σ exposure (pre-CCP reach) by hop
        wd_real = [0.0] * (HOPCAP + 1) # Σ realized (post-CCP eaten) by hop
        wd_cnt = [0] * (HOPCAP + 1)
        wd_direct_exp = wd_direct_real = wd_cont_exp = wd_cont_real = 0.0
        for e in w.writedown_log:
            h = min(HOPCAP, e["hop"])
            wd_exp[h] += e["exposure"]; wd_real[h] += e["realized"]; wd_cnt[h] += 1
            if e["cause"] == "direct":
                wd_direct_exp += e["exposure"]; wd_direct_real += e["realized"]
            else:
                wd_cont_exp += e["exposure"]; wd_cont_real += e["realized"]
        max_hop = max((e["hop"] for e in w.writedown_log), default=-1)
        # the ROBUST reach: in-flight far-band leverage snapshotted AT the shock, by
        # hop (deadlock-independent). exp_snap_by_hop[h] = Σ face exposure at depth h.
        exp_snap = [0.0] * (HOPCAP + 1)
        exp_cnt = [0] * (HOPCAP + 1)
        for hop, val in w.shock_exp_by_hop.items():
            exp_snap[min(HOPCAP, hop)] += val
        for hop, c in w.shock_exp_cnt.items():
            exp_cnt[min(HOPCAP, hop)] += c
        exp_maxhop = max(w.shock_exp_by_hop.keys(), default=-1)
        exp_direct = w.shock_exp_by_hop.get(0, 0.0)
        exp_contagion = sum(v for h, v in w.shock_exp_by_hop.items() if h >= 1)
        tshock = w.shock_tick if w.shock_tick is not None else -1
        shock_detail = dict(
            shock=bool(shock), clearinghouse=bool(clearinghouse),
            shocked=bool(w.shocked), shock_tick=tshock,
            far_pctl=SHOCK_FAR_PCTL, value_floor=SHOCK_VALUE_FLOOR,
            ccp_fee=CCP_FEE, n_far=len(w.shock_far),
            far_stock_lost=w.shock_far_stock_lost,
            window=_WIN,
            # PABa (robust): in-flight far-band leverage snapshotted AT the shock
            exp_snap_by_hop=[round(x, 2) for x in exp_snap],
            exp_snap_cnt_by_hop=exp_cnt, exp_snap_maxhop=exp_maxhop,
            exp_snap_direct=round(exp_direct, 2),
            exp_snap_contagion=round(exp_contagion, 2),
            # REALIZED write-downs at settlement/death (materialized subset)
            wd_exp_by_hop=[round(x, 2) for x in wd_exp],
            wd_real_by_hop=[round(x, 2) for x in wd_real],
            wd_count_by_hop=wd_cnt, max_hop=max_hop,
            wd_direct_exp=round(wd_direct_exp, 2),
            wd_direct_real=round(wd_direct_real, 2),
            wd_contagion_exp=round(wd_cont_exp, 2),
            wd_contagion_real=round(wd_cont_real, 2),
            shock_writedown=round(w.shock_writedown, 2),
            # deaths/strands after the shock (the physical damage window)
            deaths=w.deaths,
            deaths_post=sum(1 for d in w.death_log if d["tick"] >= tshock)
            if tshock >= 0 else 0,
            strands_total=len(w.strand_log),
            strands_post=sum(1 for (tk, _r) in w.strand_log if tk >= tshock)
            if tshock >= 0 else 0,
            # CCP accounting
            ccp_fees=round(w.ccp_fees, 2), ccp_payouts=round(w.ccp_payouts, 2),
            ccp_haircut=round(w.ccp_haircut, 2),
            ccp_pool_final=round(w.ccp_pool, 2), ccp_pool_traj=_pool_traj,
        )
    # v32 (column AB2): the debt blob (only when debt_ltv>0). Borrowing take-up (the
    # pre-flight gate: does the loan fund far work?), the treasury waterfall (loaned /
    # repaid / written-off / outstanding — must balance), and garnishment (episodes,
    # duration, hop-distance of the underwater drones from the shock, and whether the
    # garnished DIE — PAB2b's body count). No-op unless debt_ltv>0 ⇒ every prior
    # column bit-identical.
    debt_detail = None
    if debt_ltv > 0.0:
        # far band = the SHOCK_FAR_PCTL of nearest-refinery distance (identical geometry
        # to the shock's dark region), so "borrow funds far work" reads on the SAME band.
        _fd = [min(manhattan(s, rf) for rf in w.refineries) for s in w.sources]
        _fthr = float(np.percentile(_fd, SHOCK_FAR_PCTL)) if _fd else 0.0
        blog = w._borrow_log                         # (tick, rid, energy, principal, dref, taint)
        borrowers = sorted({b[1] for b in blog})
        drefs = [b[4] for b in blog]
        far_borrows = sum(1 for b in blog if b[4] > _fthr)
        tshock = w.shock_tick if w.shock_tick is not None else -1
        borrows_pre = sum(1 for b in blog if tshock < 0 or b[0] < tshock)
        borrows_post = sum(1 for b in blog if tshock >= 0 and b[0] >= tshock)
        # garnishment episodes: duration (end−start; end=-1 ⇒ still open at horizon/death),
        # hop-distance from the shock at entry (None ⇒ untainted), and whether the drone died.
        dead_rids = {d["rid"] for d in w.death_log}
        gl = w.garnish_log
        durs, hops, g_far, g_dead = [], [], 0, 0
        for g in gl:
            end = g["end"] if g["end"] >= 0 else w.tick
            durs.append(end - g["start"])
            h = g["hop"]
            hops.append(h if h is not None else -1)   # -1 = untainted (no shock reach)
            if h is not None and h >= 1:
                g_far += 1
            if g["rid"] in dead_rids:
                g_dead += 1
        garnished_rids = {g["rid"] for g in gl}
        # deaths among EVER-garnished drones vs the rest (PAB2b: casualties concentrate
        # among the garnished, ≥1 hop from direct exposure).
        deaths_garnished = sum(1 for d in w.death_log if d["rid"] in garnished_rids)
        deaths_post = (sum(1 for d in w.death_log if d["tick"] >= tshock)
                       if tshock >= 0 else 0)
        outstanding = round(sum(r.debt for r in w.robots), 4)
        debt_detail = dict(
            debt_ltv=debt_ltv, energy_price=DEBT_ENERGY_PRICE, far_thr=round(_fthr, 1),
            # take-up (the pre-flight)
            n_borrow_events=len(blog), n_borrowers=len(borrowers),
            energy_borrowed=round(w.energy_borrowed, 2),
            energy_drawn=round(w.energy_drawn(), 2),
            mean_borrow_dref=round(float(np.mean(drefs)), 2) if drefs else 0.0,
            far_borrow_share=round(far_borrows / len(blog), 3) if blog else 0.0,
            borrows_pre=borrows_pre, borrows_post=borrows_post,
            # treasury waterfall (must balance: loaned == repaid + written_off + outstanding)
            debt_loaned=round(w.debt_loaned, 2), debt_repaid=round(w.debt_repaid, 2),
            debt_written_off=round(w.debt_written_off, 2), debt_outstanding=outstanding,
            # garnishment (PAB2b/c)
            n_garnish=len(gl), n_garnish_far=g_far, n_garnish_dead=g_dead,
            garnish_mean_dur=round(float(np.mean(durs)), 1) if durs else 0.0,
            garnish_hops=hops,
            deaths=w.deaths, deaths_post=deaths_post,
            deaths_garnished=deaths_garnished,
        )
    # v30 (column M2): the medium-of-exchange index M(x) and flow shares, computed
    # from the deal log (q, e, s, t). M(x) = P(x on the OPPOSITE side of a bundle from
    # a good moving the other way) among deals where x moves — the v15/P19c index,
    # symmetric across {cargo, energy, claims}. Flow face = Σ value moved as each
    # medium (cargo |q|·V, claims |t|, energy |e|). Windowed for the trajectory.
    # Computed for EVERY bills/spot row (t≡0 off the transferable arm ⇒ M(claims)=0),
    # so the static/spot comparators carry M(energy)/M(cargo) too. Pure post-hoc read.
    mx_detail = None
    if bills or claims_transferable:
        MWIN = 500
        keys = ("cargo", "energy", "claims")
        mv, op, face = mx_counts(deals)
        wins = []
        for ws in range(0, ticks, MWIN):
            sub = [d for d in deals if ws <= d["tick"] < ws + MWIN]
            if not sub:
                continue
            wmv, wop, wface = mx_counts(sub)
            wins.append(dict(t0=ws,
                             mv={k: wmv[k] for k in keys},
                             op={k: wop[k] for k in keys},
                             face={k: round(wface[k], 1) for k in keys}))
        mx_detail = dict(mv={k: mv[k] for k in keys}, op={k: op[k] for k in keys},
                         face={k: round(face[k], 1) for k in keys}, windows=wins)
    # v30 (column M2): the CIRCULATION blob (velocity, maturity, endorsement flow) —
    # only under claims_transferable ⇒ every prior column bit-identical.
    circulation_detail = None
    if claims_transferable:
        # velocity = endorsements-before-settlement per claim. SETTLED claims from the
        # settle log; OUTSTANDING claims swept from live parcels at the horizon — the
        # union is every claim that ever existed (each has a velocity, 0 = held to
        # settlement / never circulated). The KILL condition reads velocity≈0.
        settled = w.claim_settle_log            # (settle_tick, born_tick, xfers, face)
        vel_settled = [x[2] for x in settled]
        out_x = []                              # outstanding-claim velocities
        for rr in w.robots:
            for pp in rr.parcels:
                cl = pp.get("claims")
                if not cl:
                    continue
                for j in range(len(cl)):
                    out_x.append(pp["cx"][j])
        vel_all = vel_settled + out_x
        def _velhist(xs):
            h = [0, 0, 0, 0, 0]                 # 0, 1, 2, 3, 4+
            for v in xs:
                h[min(4, v)] += 1
            return h
        half = makespan / 2.0
        early = [x[2] for x in settled if x[0] < half]
        late = [x[2] for x in settled if x[0] >= half]
        # endorsed-claim maturity (risk proxy) vs the population it was drawn from
        xl = w.claim_xfer_log                   # (tick, face, ref_d, hops, xfers)
        endorsed_d = [x[2] for x in xl]
        endorsed_h = [x[3] for x in xl]
        circulation_detail = dict(
            n_endorse_deals=w.claim_xfers,      # deals carrying an endorsement leg
            n_endorsements=len(xl),             # individual claim-entry endorsements
            n_claims_settled=len(vel_settled),
            n_claims_outstanding=len(out_x),
            # VELOCITY
            velocity_mean=round(float(np.mean(vel_all)), 4) if vel_all else 0.0,
            velocity_mean_settled=round(float(np.mean(vel_settled)), 4)
            if vel_settled else 0.0,
            velocity_max=int(max(vel_all)) if vel_all else 0,
            velocity_hist=_velhist(vel_all),    # counts by 0/1/2/3/4+ endorsements
            velocity_early=round(float(np.mean(early)), 4) if early else 0.0,
            velocity_late=round(float(np.mean(late)), 4) if late else 0.0,
            n_early=len(early), n_late=len(late),
            # MATURITY / good-collateral: endorsed claims vs the outstanding pool
            endorsed_ref_d_mean=round(float(np.mean(endorsed_d)), 3)
            if endorsed_d else 0.0,
            endorsed_hops_mean=round(float(np.mean(endorsed_h)), 3)
            if endorsed_h else 0.0,
            pop_snapshots=_claim_pop,           # (t, n, mean_ref_d, mean_hops)
            pop_ref_d_mean=round(float(np.mean([s[2] for s in _claim_pop])), 3)
            if _claim_pop else 0.0,
            pop_hops_mean=round(float(np.mean([s[3] for s in _claim_pop])), 3)
            if _claim_pop else 0.0,
        )
    # v17 PHASE 2: the mechanism rides the same snhp+net base (SnhpArm) — the
    # world flag IS the treatment, so relabel for the tables/pairings.
    # P23e: contingent splits get a distinct label so spot/flat/contingent pair.
    # v18-R (column Q2): a BUILD row now also carries its settlement mechanism in
    # the label, so a bills-build ("snhp+net+B+bill") is distinguishable from a
    # spot-build ("snhp+net+B") — the P24R-c layering pair. Spot/firm build labels
    # are unchanged from column Q (build+no-mechanism ⇒ "…+B"), so every prior Q
    # row keeps its label and the Q report/tests stay valid.
    _build_mech = ("+bill" if (bills and not bills_contingent)
                   else "+billC" if (bills and bills_contingent)
                   else "+firm" if firm_relay else "")
    base_label = (f"{arm_name}+B{_build_mech}" if build   # v18: endogenous infrastructure
                  else "snhp+cmd" if command          # v25 (column X): COMMAND regime
                  else "snhp+depot" if depots         # v31 (column V2): async depots
                  else "snhp+ob" if order_book        # v23: order-book relays (bills-settled)
                  else "snhp+billC" if (bills and bills_contingent)
                  else "snhp+bill" if bills
                  else "snhp+firm" if firm_relay else arm_name)
    # v28 (column AA): a mortality row carries its death-inheritance regime in the
    # label so the claims-die / estates / risk-premium / spot-baseline rows pair
    # cleanly. Off ⇒ unchanged, so every prior column keeps its label.
    if mortality:
        _mort = {"claims_die": "+die", "estates": "+est",
                 "risk_premium": "+rp", "none": "+mort"}[death_regime]
        base_label = base_label + _mort
    # v29 (column AB): a crash row carries its clearinghouse / shock flags in the
    # label so gross/CCP × shock/control pair cleanly. Off ⇒ unchanged (a gross
    # no-shock row is exactly the v28 claims-die anchor "snhp+bill+die").
    if clearinghouse:
        base_label = base_label + "+ccp"
    if shock:
        base_label = base_label + "+shk"
    # v32 (column AB2): a debt row carries "+ltv<LTV>" so the LTV grid pairs cleanly
    # (LTV 0 is the AB anchor — no suffix). Off ⇒ unchanged.
    if debt_ltv > 0.0:
        base_label = base_label + f"+ltv{debt_ltv:g}"
    # v30 (column M2): an endorsable-claim row carries "+xfer" so bills-static
    # ("snhp+bill") and bills-transferable ("snhp+bill+xfer") pair cleanly. Off ⇒
    # unchanged (a static bills row is exactly the P23 "snhp+bill").
    if claims_transferable:
        base_label = base_label + "+xfer"
    label = base_label if tuple(issues) == FULL else \
        f"{base_label}[{'+'.join(issues)}]"
    return dict(
        arm=label, sigma=sigma, seed=seed, tau=tau_pair[0], tau1=tau_pair[1],
        preset=preset, delivered=w.delivered, delivered_mid=delivered_mid,
        makespan=makespan, ticks_horizon=ticks, stranded=stranded,
        score_k2=w.delivered - 2 * stranded,
        score_k5=w.delivered - 5 * stranded,
        eff_last=100.0 * w.delivered / max(1e-9, w.energy_at_last_delivery),
        lost_cargo=sum(r.load for r in w.robots if r.stranded),
        # v18 (column Q): ore MINED but never delivered — held in robot loads at
        # the horizon. The N=240 plateau's trapped-return signature (loaded drones
        # pinned at dead-end chargers beyond single-hop refinery range).
        held_load=sum(r.load for r in w.robots),
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
        # P23e (column P phase-2e): moral hazard in the relay
        dwell=dwell, bills_contingent=bills_contingent,
        dwell_detail=dwell_detail,
        # v30 (column M2): the bill becomes money — transferable claims
        claims_transferable=claims_transferable,
        claim_xfers=(w.claim_xfers if claims_transferable else None),
        mx_detail=mx_detail,
        circulation_detail=circulation_detail,
        # v22 (column U): reputation vs receipts
        reputation=reputation, false_accuse=false_accuse,
        **_reputation_metrics(w, arm),
        # v23 (column V): the stigmergic order book
        order_book=order_book,
        order_book_detail=order_book_detail,
        # v31 (column V2): the depot (async deposit-and-return relays)
        depots=depots,
        # v18 (column Q): endogenous infrastructure
        build_matter=build_matter, build=build, toll_level=toll_level,
        build_budget=(build_budget if build_budget < 10**9 else None),
        build_detail=build_detail,
        # v18-R (column Q2): frontier scarcity (home-band radius; 0 ⇒ off)
        charger_band=charger_band,
        # v27 (column Z): forgery — the receipt under attack
        forgery=forgery, forge_cost=forge_cost, verify_cost=verify_cost,
        verify_regime=verify_regime,
        forge_attempts=getattr(arm, "forge_attempts", 0),
        forge_caught=getattr(arm, "forge_caught", 0),
        forge_slipped=getattr(arm, "forge_slipped", 0),
        verify_acts=getattr(arm, "verify_acts", 0),
        forge_spend=round(w.forge_spend, 3),
        verify_spend=round(w.verify_spend, 3),
        # honest advantage = the tier's health (honest − liar mean credit); inverts
        # when forgery lets liars buy back into the exploitable cooperative tier
        honest_adv=((np.mean([r.credit for r in w.robots if not r.liar])
                     - np.mean([r.credit for r in w.robots if r.liar]))
                    if (any(r.liar for r in w.robots)
                        and any(not r.liar for r in w.robots)) else None),
        # v25 (column X): the firm's interior — command / prices / claims
        command=command,
        deadlock_count=(w.deadlock_count if w.deadlock_track else None),
        # per-drone payoff dispersion (delivery credit) — reported for every regime
        payoff_gini=round(_gini([max(0.0, r.credit) for r in w.robots]), 4),
        payoff_std=round(float(np.std([r.credit for r in w.robots])), 3),
        command_detail=(dict(
            handoffs=w.cmd_handoffs,
            n_plans=len(w.cmd_plan_versions),
            # plan-staleness AT SOURCE: mean age of the merged-belief entries the
            # mine-assignments were computed from (over all planning events).
            plan_belief_age_mean=(
                float(np.mean([a for _, a in w.cmd_belief_age_traj]))
                if w.cmd_belief_age_traj else None),
            plan_belief_age_traj=[(t, round(a, 2))
                                  for t, a in w.cmd_belief_age_traj],
            # AT EXECUTION: fraction of commanded mine drone-ticks whose target
            # rock was already truly depleted (the plan went stale before it ran).
            stale_assign_frac=(round(w.cmd_mine_stale / w.cmd_mine_exec, 4)
                               if w.cmd_mine_exec else None),
            # assignment-reach latency: ticks from a plan's computation to a drone
            # adopting it over the radio.
            reach_latency_mean=(float(np.mean(w.cmd_reach_lat))
                                if w.cmd_reach_lat else None),
        ) if command else None),
        # v20 (column S): institutions as a substitute for cognition. nav_dumb =
        # the DUMB routing brain (greedy nearest-known + noise) vs smart Φ-routing;
        # the rights axis rides prospect_claims (granular) vs off (coarse sectors).
        nav_dumb=nav_dumb,
        # v28 (column AA): mortality and the persistence of paper — estates
        mortality=mortality, death_regime=death_regime, wearout=wearout,
        deaths=(w.deaths if mortality else None),
        mortality_detail=mortality_detail,
        # v29 (column AB): the crash — contagion in the counterparty web
        shock=shock, clearinghouse=clearinghouse,
        shock_tick=(w.shock_tick if (shock or clearinghouse) else None),
        shock_detail=shock_detail,
        # v32 (column AB2): claim-collateralized debt
        debt_ltv=debt_ltv,
        debt_detail=debt_detail,
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
            r.get("false_accuse", 0.0),
            r.get("build_matter", 0.0),          # v18 (column Q)
            bool(r.get("build", False)),
            r.get("toll_level", 0.0),
            (r.get("build_budget") if r.get("build_budget") is not None else -1),
            r.get("charger_band", 0.0),          # v18-R (column Q2)
            bool(r.get("nav_dumb", False)))      # v20 (column S)


def _cond_label(c) -> str:
    (f, dfd, s7, mg, nz, g, bm, race, mt, dyn, cnt, scout, maptr, pros,
     nr, cc, gs, rr, rep, fa, bmat, bld, toll, bbud, cband, navd) = c
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
    if bmat:
        bits.append(f"bm={bmat:g}")      # v18: matter-field fraction
    if bld:
        bits.append("build")             # v18: build-capable
    if toll:
        bits.append(f"toll={toll:g}")    # v18: guest toll on built chargers
    if bbud is not None and bbud >= 0:
        bits.append(f"bud={bbud}")       # v18: forced per-company build budget
    if cband:
        bits.append(f"cband={cband:g}")  # v18-R (Q2): frontier-scarcity band radius
    if navd:
        bits.append("navdumb")           # v20 (column S): dumb routing brain
    return " ".join(bits)


_BASE = (0.0, False, 0.0, False, 0.0, 32, False, True, False, False, False,
         False, False, False, 24, False, False, 6, False, 0.0,
         0.0, False, 0.0, -1, 0.0, False)         # trailing False = nav_dumb (v20)


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


def phase2e(rows: list[dict]) -> None:
    """P23e (column P phase-2e) — moral hazard in the relay. Contrasts FLAT splits
    (snhp+bill) vs TIME-CONTINGENT splits (snhp+billC) against the no-bills spot
    baseline (snhp+net), all dwell-instrumented. Printed numbers ARE the artifact
    (report, not verdict). No-op unless the sweep carries a dwell-instrumented run.
    The KILL fires if bills-flat shows NO dwell inflation vs the counterfactual —
    then there is no moral hazard to price and contingent has nothing to compress."""
    drows = [r for r in rows if r.get("dwell") and r.get("dwell_detail")]
    if not drows:
        return
    order = {"snhp+net": 0, "snhp+bill": 1, "snhp+billC": 2}
    arms = sorted({r["arm"] for r in drows}, key=lambda a: order.get(a, 9))
    Ns = sorted({int(r["n_robots"]) for r in drows})

    def sel(arm, N):
        return [r for r in drows
                if r["arm"] == arm and int(r["n_robots"]) == N]

    def paired(arm_hi, arm_lo, N, getter):
        hi = {r["seed"]: getter(r) for r in sel(arm_hi, N)}
        lo = {r["seed"]: getter(r) for r in sel(arm_lo, N)}
        common = sorted(set(hi) & set(lo))
        if len(common) < 3:
            return None
        d = np.array([hi[s] - lo[s] for s in common], float)
        _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
        return dict(delta=float(d.mean()), p_t=float(pt),
                    wins=int((d > 0).sum()), n=len(common))

    print("\n" + "=" * 92)
    print("P23e (column P phase-2e) — MORAL HAZARD IN THE RELAY: flat vs "
          "time-contingent splits")
    lam = drows[0]["dwell_detail"]["decay_lambda"]
    print(f"dwell = ticks a parcel sits in a carrier's hold; counterfactual = "
          f"geodesic (manhattan/speed). decay = exp(-{lam}·excess).")
    print("=" * 92)

    # [1] DWELL INFLATION — the heart. Per-parcel journey inflation (total_dwell −
    # geodesic cf), split by relay depth, plus per-leg excess (relay vs final).
    print("\n[1] DWELL INFLATION vs geodesic counterfactual (ticks; parcel journey "
          "= total_dwell − total_cf):")
    h = (f"  {'arm':<11} {'N':>4} {'nParc':>6} {'totDwell':>9} {'totCF':>7} "
         f"{'inflat':>7} {'infl_0h':>8} {'infl_1h':>8} {'infl≥2h':>8} "
         f"{'relLegXs':>9} {'finLegXs':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in arms:
            g = sel(arm, N)
            if not g:
                continue
            dd = [r["dwell_detail"] for r in g]
            npar = np.mean([d["deliv_inflation"]["n"] for d in dd])
            td = np.mean([d["deliv_total_dwell"]["mean"] for d in dd])
            tcf = np.mean([d["deliv_total_cf"]["mean"] for d in dd])
            infl = np.mean([d["deliv_inflation"]["mean"] for d in dd])

            def by(hh):
                vals = [d["inflation_by_hops"][hh]["mean"] for d in dd
                        if d["inflation_by_hops"][hh]["n"] > 0]
                return np.mean(vals) if vals else float("nan")
            rlx = np.mean([d["relay_leg_excess"]["mean"] for d in dd])
            flx = np.mean([d["final_leg_excess"]["mean"] for d in dd])
            print(f"  {arm:<11} {N:>4} {npar:>6.0f} {td:>9.1f} {tcf:>7.1f} "
                  f"{infl:>7.1f} {by(0):>8.1f} {by(1):>8.1f} {by(2):>8.1f} "
                  f"{rlx:>9.2f} {flx:>9.2f}")

    print("\n[1b] Paired inflation deltas (contingent − flat; <0 ⇒ dwell "
          "compressed, the P23e prediction):")
    for N in Ns:
        for hh, lab in ((None, "all parcels"), (2, "≥2-hop only")):
            def getter(r, hh=hh):
                d = r["dwell_detail"]
                return (d["deliv_inflation"]["mean"] if hh is None
                        else d["inflation_by_hops"][hh]["mean"])
            cf = paired("snhp+billC", "snhp+bill", N, getter)
            ck = paired("snhp+bill", "snhp+net", N, getter)  # flat vs spot (KILL)
            if cf:
                print(f"    N={N:>3} {lab:<12} contingent−flat Δinfl="
                      f"{cf['delta']:+6.2f} (p_t={cf['p_t']:.3f}, "
                      f"{cf['wins']}/{cf['n']})", end="")
                if ck:
                    print(f"   |  flat−spot Δinfl={ck['delta']:+6.2f} "
                          f"(p_t={ck['p_t']:.3f}, {ck['wins']}/{ck['n']})")
                else:
                    print()

    # [2] CHAIN-FORMATION REGRESSION CHECK — contingent must not collapse chains.
    print("\n[2] CHAIN FORMATION (regression check — contingent must hold): "
          "≥2-hop share, far-band d/m, delivered_frac, stranded:")
    h = (f"  {'arm':<11} {'N':>4} {'dFrac':>6} {'≥2-hop':>7} {'far d/m':>13} "
         f"{'stranded':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in arms:
            g = sel(arm, N)
            if not g:
                continue
            df = np.mean([r["delivered_frac"] for r in g])
            sh2 = np.mean([r["lineage_detail"]["hop_shares"][2] for r in g])
            bm = np.array([r["lineage_detail"]["band_mined"] for r in g],
                          float).sum(axis=0)
            bd = np.array([r["lineage_detail"]["band_delivered"] for r in g],
                          float).sum(axis=0)
            far = bd[2] / bm[2] if bm[2] > 0 else float("nan")
            st = np.mean([r["stranded"] for r in g])
            print(f"  {arm:<11} {N:>4} {df:>6.3f} {sh2:>7.3f} "
                  f"{bd[2]/len(g):>5.0f}/{bm[2]/len(g):<5.0f}={far:>4.2f} "
                  f"{st:>9.2f}")

    # [3] MIDDLE-LEG MARGIN (P23c no-compression must hold under contingent too).
    print("\n[3] MIDDLE-LEG MARGIN (P23c — Δ<0 ⇒ hold-up compression; must stay "
          "≈0 under contingent):")
    h = (f"  {'arm':<11} {'N':>4} {'nLegs':>6} {'mean_buy':>9} "
         f"{'mean_sell':>10} {'meanΔ':>8} {'fracCompr':>10}")
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
            if priced:
                mb = np.mean([h_["mean_buy"] for h_ in priced])
                msl = np.mean([h_["mean_sell"] for h_ in priced])
                md = np.mean([h_["mean_delta"] for h_ in priced])
                fc = np.mean([h_["frac_compressed"] for h_ in priced])
                print(f"  {arm:<11} {N:>4} {nlegs:>6.0f} {mb:>9.3f} "
                      f"{msl:>10.3f} {md:>8.3f} {fc:>10.3f}")
            else:
                print(f"  {arm:<11} {N:>4} {nlegs:>6.0f} {'—':>9} {'—':>10} "
                      f"{'—':>8} {'—':>10}")


def paa_report(rows: list[dict]) -> None:
    """v28 (column AA) — mortality and the persistence of paper: estates. Printed
    numbers ARE the artifact (report, not verdict). No-op unless the sweep carries a
    mortality run. Four grid cells pair off the same P23 phase-2 config:
      snhp+bill+die  claims-die  (paper voids at death; Φ prices own-claim survival)
      snhp+bill+est  estates     (paper settles to the company treasury heir)
      snhp+bill+rp   risk-premium (claims-die + the actuarial hop-split gross-up)
      snhp+net+mort  spot        (no bills — the chain-deal-rate reference)
    Anchors: snhp+bill (mortality OFF, the 0-death endpoint) and the 7,500t contrast."""
    mrows = [r for r in rows if r.get("mortality") and r.get("mortality_detail")]
    if not mrows:
        return
    # labels: bills-on death rows read "snhp+bill+die/est/rp"; the no-bills spot
    # baseline reads "snhp+net+mort"; the mortality-OFF anchor is plain "snhp+bill".
    DIE, EST, RP, SPOT, ANCH = ("snhp+bill+die", "snhp+bill+est", "snhp+bill+rp",
                                "snhp+net+mort", "snhp+bill")
    order = {DIE: 0, EST: 1, RP: 2, SPOT: 3, ANCH: 4}
    lab = {DIE: "claims-die", EST: "estates", RP: "risk-prem", SPOT: "spot",
           ANCH: "bills(no-death)"}
    Ns = sorted({int(r["n_robots"]) for r in mrows})
    H2500 = 2500

    def sel(arm, N, horizon=H2500, wearout=False):
        # the main grid is FLATLINE-only (wearout=False); the ref-B sensitivity rows
        # (wearout=True) share the label/N/horizon and are pulled explicitly.
        return [r for r in rows if r["arm"] == arm and int(r["n_robots"]) == N
                and int(r.get("ticks_horizon", H2500)) == horizon
                and bool(r.get("wearout", False)) == wearout]

    def paired(arm_hi, arm_lo, N, getter, horizon=H2500, wearout=False):
        hi = {r["seed"]: getter(r) for r in sel(arm_hi, N, horizon, wearout)}
        lo = {r["seed"]: getter(r) for r in sel(arm_lo, N, horizon, wearout)}
        common = sorted(k for k in set(hi) & set(lo)
                        if hi[k] is not None and lo[k] is not None)
        if len(common) < 3:
            return None
        d = np.array([hi[s] - lo[s] for s in common], float)
        _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
        try:
            _, pw = stats.wilcoxon(d) if np.any(d != 0) else (None, 1.0)
        except ValueError:
            pw = float("nan")
        return dict(delta=float(d.mean()), p_t=float(pt), p_w=float(pw),
                    wins=int((d > 0).sum()), n=len(common),
                    hi=float(np.mean([hi[s] for s in common])),
                    lo=float(np.mean([lo[s] for s in common])))

    d0 = mrows[0]["mortality_detail"]
    print("\n" + "=" * 94)
    print("PAA (v28 · column AA) — MORTALITY AND THE PERSISTENCE OF PAPER: estates "
          "(report, not verdict)")
    print(f"death sources: FLATLINE (stranded {d0['flatline_ticks']} ticks unrescued) "
          f"+ WEAR-OUT (age>{d0['wearout_age']}, p={d0['wearout_p']:g}/tick, dedicated "
          f"seed+282828, IDENTICAL across regimes).")
    print("=" * 94)

    grid_arms = [DIE, EST, RP, SPOT]

    # [1] DEATH RATE + delivered/frac + destroyed/inherited credit, per regime × N
    print("\n[1] DEATHS/run (flatline+wear-out), delivered, and paper resolved at "
          "death (per regime × N):")
    h = (f"  {'regime':<10} {'N':>4} {'deaths':>7} {'flat':>5} {'wear':>5} "
         f"{'deliv':>6} {'dFrac':>6} {'voided$':>8} {'estate$':>8}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in grid_arms:
            g = sel(arm, N)
            if not g:
                continue
            md = [r["mortality_detail"] for r in g]
            dth = np.mean([m["deaths"] for m in md])
            fl = np.mean([m["death_flatline"] for m in md])
            wo = np.mean([m["death_wearout"] for m in md])
            dv = np.mean([r["delivered"] for r in g])
            df = np.mean([r["delivered_frac"] for r in g])
            vo = np.mean([m["claims_voided"] for m in md])
            es = np.mean([m["estate_settled"] for m in md])
            print(f"  {lab[arm]:<10} {N:>4} {dth:>7.1f} {fl:>5.1f} {wo:>5.1f} "
                  f"{dv:>6.0f} {df:>6.3f} {vo:>8.1f} {es:>8.1f}")

    # [2] THE FREEZE-OUT — chain-deal rate by partner-hazard quartile × regime.
    # Pool feasible/cargo counts across seeds per (arm, N), rate = cargo/feasible.
    print("\n[2] PAAa THE FREEZE-OUT — chain-deal rate (cargo deals / chain-feasible "
          "encounters) by potential-giver HAZARD quartile:")
    print("     bins over stranding-hazard [0-.25) [.25-.5) [.5-.75) [.75-1]; the "
          "high-hazard bins are the DYING. claims-die < estates ⇒ freeze-out.")
    h = (f"  {'regime':<10} {'N':>4} {'Q1_lohaz':>13} {'Q2':>13} {'Q3':>13} "
         f"{'Q4_hihaz':>13}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in grid_arms:
            g = sel(arm, N)
            if not g:
                continue
            feas = np.sum([r["mortality_detail"]["freeze_haz_feasible"] for r in g],
                          axis=0)
            cargo = np.sum([r["mortality_detail"]["freeze_haz_cargo"] for r in g],
                           axis=0)
            cells = []
            for j in range(4):
                rate = cargo[j] / feas[j] if feas[j] > 0 else float("nan")
                cells.append(f"{rate:>5.3f}[{int(feas[j]):>5d}]")
            print(f"  {lab[arm]:<10} {N:>4} " + " ".join(f"{c:>13}" for c in cells))

    print("\n[2b] freeze-out GAP in the high-hazard quartiles (estates − claims-die "
          "chain-deal rate; >0 ⇒ estates keeps the dying trading):")
    for N in Ns:
        for qlab, qs in (("Q3+Q4 (dying)", (2, 3)), ("Q4 (dying-most)", (3,))):
            def rate_hi(r, qs=qs):
                m = r["mortality_detail"]
                f_ = sum(m["freeze_haz_feasible"][j] for j in qs)
                c_ = sum(m["freeze_haz_cargo"][j] for j in qs)
                return (c_ / f_) if f_ > 0 else None
            c = paired(EST, DIE, N, rate_hi)
            if c:
                print(f"    N={N:>3} {qlab:<16} est={c['lo']+c['delta']:.3f} "
                      f"die={c['lo']:.3f}  Δ={c['delta']:+.4f}  "
                      f"p_t={c['p_t']:.3f} wins {c['wins']}/{c['n']}")

    # [3] PAAb — estates recovers the claims-die delivered / far-band / ≥2-hop loss
    print("\n[3] PAAb ESTATES RECOVERY — delivered_frac, far-band d/m, ≥2-hop share "
          "(vs the spot baseline; estates should recover claims-die's loss):")
    h = (f"  {'regime':<10} {'N':>4} {'dFrac':>7} {'far d/m':>10} {'≥2-hop':>7}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in grid_arms + [ANCH]:
            g = sel(arm, N)
            if not g:
                continue
            df = np.mean([r["delivered_frac"] for r in g])
            ld = [r["lineage_detail"] for r in g if r.get("lineage_detail")]
            if ld:
                bm = np.array([d["band_mined"] for d in ld], float).sum(axis=0)
                bd = np.array([d["band_delivered"] for d in ld], float).sum(axis=0)
                far = (bd[2] / bm[2]) if bm[2] > 0 else float("nan")
                h2 = np.mean([d["hop_shares"][2] for d in ld])
                cell = f"{bd[2]/len(ld):>4.0f}/{bm[2]/len(ld):<4.0f}={far:>4.2f}"
                print(f"  {lab[arm]:<10} {N:>4} {df:>7.3f} {cell:>10} {h2:>7.3f}")
            else:
                print(f"  {lab[arm]:<10} {N:>4} {df:>7.3f} {'—(spot)':>10} {'—':>7}")

    print("\n[3b] paired deltas vs claims-die (>0 ⇒ recovery); spot is the floor "
          "reference:")
    for N in Ns:
        cE = paired(EST, DIE, N,
                    lambda r: r["delivered_frac"])
        cD = paired(DIE, SPOT, N,
                    lambda r: r["delivered_frac"])
        if cD:
            print(f"    N={N:>3} claims-die − spot     Δframe={cD['delta']:+.4f} "
                  f"p_t={cD['p_t']:.3f} wins {cD['wins']}/{cD['n']}")
        if cE:
            print(f"    N={N:>3} estates − claims-die  Δframe={cE['delta']:+.4f} "
                  f"p_t={cE['p_t']:.3f} wins {cE['wins']}/{cE['n']}")

    # [4] PAAc — the risk-premium variant fails to restore chaining with the dying
    print("\n[4] PAAc RISK-PREMIUM vs ESTATES — does the actuarial hop-split gross-up "
          "restore the dying's chaining? (echo of the career-pricing null: no):")
    for N in Ns:
        def rate_q4(r):
            m = r["mortality_detail"]
            f_ = m["freeze_haz_feasible"][3] + m["freeze_haz_feasible"][2]
            c_ = m["freeze_haz_cargo"][3] + m["freeze_haz_cargo"][2]
            return (c_ / f_) if f_ > 0 else None
        cRP = paired(RP, DIE, N, rate_q4)
        cRE = paired(RP, EST, N, rate_q4)
        cDF = paired(RP, EST, N,
                     lambda r: r["delivered_frac"])
        if cRP:
            print(f"    N={N:>3} dying chain-rate: risk-prem − claims-die "
                  f"Δ={cRP['delta']:+.4f} (rp={cRP['hi']:.3f} die={cRP['lo']:.3f})")
        if cRE:
            print(f"    N={N:>3} dying chain-rate: risk-prem − estates    "
                  f"Δ={cRE['delta']:+.4f} (rp={cRE['hi']:.3f} est={cRE['lo']:.3f})")
        if cDF:
            print(f"    N={N:>3} delivered_frac:   risk-prem − estates    "
                  f"Δframe={cDF['delta']:+.4f} p_t={cDF['p_t']:.3f}")

    # [5] death-rate sensitivity + KILL — 0-death anchor → flatline → +wear-out
    print("\n[5] DEATH-RATE SENSITIVITY / KILL — throughput vs the death rate "
          "(0-death anchor → flatline grid → +wear-out sensitivity):")
    for N in Ns:
        anchor = sel(ANCH, N)
        if anchor:
            af = np.mean([r["delivered_frac"] for r in anchor])
            print(f"    N={N:>3} deaths=0  bills(no-death) dFrac={af:.3f}  "
                  f"(the regimes MUST coincide here)")
        gd, ge = sel(DIE, N), sel(EST, N)
        if gd and ge:
            dr = np.mean([r["mortality_detail"]["deaths"] for r in gd + ge])
            cK = paired(EST, DIE, N, lambda r: r["delivered_frac"])
            if cK:
                print(f"    N={N:>3} deaths≈{dr:.0f} (flatline)   estates−claims-die "
                      f"dFrame={cK['delta']:+.4f} p_t={cK['p_t']:.3f}")
        gdw, gew = sel(DIE, N, wearout=True), sel(EST, N, wearout=True)
        if gdw and gew:
            drw = np.mean([r["mortality_detail"]["deaths"] for r in gdw + gew])
            cKw = paired(EST, DIE, N, lambda r: r["delivered_frac"], wearout=True)
            if cKw:
                print(f"    N={N:>3} deaths≈{drw:.0f} (+wear-out) estates−claims-die "
                      f"dFrame={cKw['delta']:+.4f} p_t={cKw['p_t']:.3f}")
    print("    KILL read — the freeze-out is a MICROSTRUCTURE effect (dying chain-deal "
          "rate [2b], ≥2-hop share [3]); aggregate throughput is over-served.")

    # [6] fair-horizon (7,500t) thesis contrast, if present
    hz = sel(DIE, 24, 7500)
    if hz:
        print("\n[6] FAIR-HORIZON (7,500t, N=24) claims-die vs estates — does the "
              "freeze-out loss amortize late?")
        cH = paired(EST, DIE, 24,
                    lambda r: r["delivered_frac"], horizon=7500)
        if cH:
            print(f"    estates−claims-die delivered Δframe={cH['delta']:+.4f} "
                  f"p_t={cH['p_t']:.3f} wins {cH['wins']}/{cH['n']} "
                  f"(2500t Δ was the [3b] row)")


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


def p29(rows: list[dict]) -> None:
    """v23 (column V) — the stigmergic order book on the column-G geometry ladder.
    Printed numbers ARE the artifact. Report, not verdict: P29a (does the
    meeting-density hump flatten?), P29b (async-share highest where encounters are
    rarest?), and the KILL (hump survives ⇒ the constraint was never meetings).
    No-op unless the sweep carries an order_book arm."""
    if not any(r.get("order_book") for r in rows):
        return
    GS = [24, 32, 48, 64]

    def cond_g(g):                     # _BASE with the grid slot (index 5) set
        c = list(_BASE)
        c[5] = g
        return tuple(c)

    def dmean(arm, g):
        vals = [r["delivered"] for r in rows
                if r["arm"] == arm and r.get("grid") == g and _cond(r) == cond_g(g)]
        return float(np.mean(vals)) if vals else float("nan")

    def edge(hi, g):                   # paired hi − auction on delivered at grid g
        return _paired(rows, hi, "auction", 0.5, "delivered", tau=0.15,
                       cond=cond_g(g))

    def obdet(arm, g, field):
        vals = [r["order_book_detail"][field] for r in rows
                if r["arm"] == arm and r.get("grid") == g
                and r.get("order_book_detail") is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def rmean(arm, g, field):          # mean of a top-level row field
        vals = [r[field] for r in rows
                if r["arm"] == arm and r.get("grid") == g and r.get(field) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def meets_per_tick(arm, g):        # encounters/tick for ANY arm (P29b/KILL)
        vals = []
        for r in rows:
            if r["arm"] != arm or r.get("grid") != g:
                continue
            d, re, mk = r.get("distinct_pairs"), r.get("reencounter_rate"), r.get("makespan")
            if d and re is not None and mk:
                vals.append(d * re / mk)
        return float(np.mean(vals)) if vals else float("nan")

    print("\n" + "=" * 100)
    print("P29 (column V) — THE STIGMERGIC ORDER BOOK on the G geometry ladder "
          "(σ=0.5, τ=0.15, v5, 2500t, 16 seeds)")
    print("=" * 100)

    print("\n[1] DELIVERED by grid × arm (auction=comparator · snhp+net=spot "
          "bargaining · snhp+bill=bills control · snhp+ob=order book):")
    h = (f"  {'G':>4} {'auction':>9} {'snhp+net':>9} {'snhp+bill':>10} "
         f"{'snhp+ob':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        print(f"  {g:>4} {dmean('auction',g):>9.1f} {dmean('snhp+net',g):>9.1f} "
              f"{dmean('snhp+bill',g):>10.1f} {dmean('snhp+ob',g):>9.1f}")

    print("\n[2] P29a [THE HUMP] — bargaining-minus-auction delivered edge by G, "
          "order books OFF vs ON (paired on seed):")
    print("    edge_off = snhp+net − auction (the v8 hump: +@G24, peak@G48, "
          "−@G64) · edge_bill = bills only · edge_ON = snhp+ob − auction")
    h = (f"  {'G':>4} {'edge_off':>9} {'p':>6} {'edge_bill':>10} {'p':>6} "
         f"{'edge_ON':>9} {'p':>6} {'ON−off':>8}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    hump = {}
    for g in GS:
        eo, eb, en = edge("snhp+net", g), edge("snhp+bill", g), edge("snhp+ob", g)
        hump[g] = (eo, en)
        def fmt(c):
            return (f"{c['delta']:>9.2f} {c['p_t']:>6.3f}") if c else f"{'—':>9} {'—':>6}"
        don = (en["delta"] - eo["delta"]) if (en and eo) else float("nan")
        print(f"  {g:>4} {fmt(eo)} {fmt(eb)} {fmt(en)} {don:>+8.2f}")

    print("\n[3] P29b [MECHANISM] — async-trade share of deals & encounter rate "
          "by G (async should be HIGHEST where encounters are RAREST):")
    h = (f"  {'G':>4} {'enc/tick':>9} {'async_sh':>9} {'accepted':>9} "
         f"{'posted':>8} {'expired':>8} {'sync_dl':>8} {'pauseSaved':>11}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    encs, ashares = [], []
    for g in GS:
        er = obdet("snhp+ob", g, "encounter_rate")
        ash = obdet("snhp+ob", g, "async_share")
        encs.append(er); ashares.append(ash)
        print(f"  {g:>4} {er:>9.3f} {ash:>9.3f} "
              f"{obdet('snhp+ob',g,'accepted'):>9.1f} "
              f"{obdet('snhp+ob',g,'posted'):>8.1f} "
              f"{obdet('snhp+ob',g,'expired'):>8.1f} "
              f"{obdet('snhp+ob',g,'sync_deals'):>8.1f} "
              f"{obdet('snhp+ob',g,'pause_ticks_saved'):>11.0f}")
    if len(encs) >= 3:
        eok = [e for e, a in zip(encs, ashares) if e == e and a == a]
        aok = [a for e, a in zip(encs, ashares) if e == e and a == a]
        if len(eok) >= 3 and np.std(eok) > 1e-9 and np.std(aok) > 1e-9:
            rho = float(np.corrcoef(eok, aok)[0, 1])
            print(f"    → corr(encounter_rate, async_share) across G = {rho:+.3f} "
                  f"(P29b predicts NEGATIVE: async fills in where meetings fail)")

    print("\n[4] ESCROW & ORDER ACCOUNTING (snhp+ob; conservation must hold):")
    h = (f"  {'G':>4} {'posted':>8} {'accepted':>9} {'expired':>8} "
         f"{'pinnedEnd':>10} {'escrowEnd':>10} {'cargoWO':>8} {'escrowOK':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        oks = [r["order_book_detail"]["escrow_ok"] for r in rows
               if r["arm"] == "snhp+ob" and r.get("grid") == g
               and r.get("order_book_detail")]
        print(f"  {g:>4} {obdet('snhp+ob',g,'posted'):>8.1f} "
              f"{obdet('snhp+ob',g,'accepted'):>9.1f} "
              f"{obdet('snhp+ob',g,'expired'):>8.1f} "
              f"{obdet('snhp+ob',g,'pinned_final'):>10.2f} "
              f"{obdet('snhp+ob',g,'escrow_final'):>10.3f} "
              f"{obdet('snhp+ob',g,'cargo_writeoff'):>8.2f} "
              f"{('all' if all(oks) else 'FAIL!'):>9}")

    print("\n[5] KILL DIAGNOSIS — if the hump survives, what binds at G64 if not "
          "meetings? (spot snhp+net; enc/tick falls only modestly while sync_dl "
          "stays high — the fleet still trades heavily — but makespan is HORIZON-"
          "CENSORED and stranding TRIPLES: the constraint is travel time + battery "
          "radius, not convening):")
    h = (f"  {'G':>4} {'enc/tick':>9} {'sync_dl':>8} {'makespan':>9} "
         f"{'stranded':>9} {'delivered':>10} {'deliv/mine%':>11}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        mk = rmean("snhp+net", g, "makespan")
        dl = rmean("snhp+net", g, "delivered")
        st = rmean("snhp+net", g, "stranded")
        dm = 100.0 * dl / 480.0            # total_stock = 2·TOTAL_STOCK = 480
        print(f"  {g:>4} {meets_per_tick('snhp+net',g):>9.3f} "
              f"{rmean('snhp+net',g,'deals'):>8.1f} {mk:>9.0f} {st:>9.2f} "
              f"{dl:>10.1f} {dm:>11.1f}")

    print("\n[6] READ (P29a / P29b / KILL): P29a is a RECOVERY test — did the "
          "order book lift edge_ON(G64) toward the G48 peak? That is edge_ON(G64) "
          "− edge_off(G64), NOT a smaller G48→G64 drop (the peak coming DOWN is "
          "the book HURTING, not the trough recovering).")
    if all(g in hump and hump[g][0] and hump[g][1] for g in (48, 64)):
        e64_off, e64_on = hump[64][0]["delta"], hump[64][1]["delta"]
        recovery = e64_on - e64_off          # >0 ⇒ order books lift the G64 edge
        e48_on = hump[48][1]["delta"]
        eb64 = edge("snhp+bill", 64)         # bills-only decomposition at G64
        print(f"    edge_off(G64) = {e64_off:+.2f}  edge_ON(G64) = {e64_on:+.2f} "
              f" ⇒ order-book recovery at G64 = {recovery:+.2f} "
              f"({'FLATTENS (P29a)' if recovery > 1.0 else 'NO RECOVERY → KILL'})")
        if eb64:
            print(f"    decomposition: bills-ONLY edge(G64) = {eb64['delta']:+.2f} "
                  f"(pre-commitment claims recover G64 SYNCHRONOUSLY) vs "
                  f"+order-book = {e64_on:+.2f} (the async book cannibalizes it)")
        print(f"    peak edge_ON(G48) = {e48_on:+.2f} vs edge_off(G48) = "
              f"{hump[48][0]['delta']:+.2f} — the book lowers the DENSE-field peak.")


# ── v31 (column V2): the depot — the founder's async re-run of the board ──────
# The registered numbers to BEAT, from the P29 RESULTS / P23a blocks (SPEC.md).
_V_SPOT_DELIV = {24: 238.9, 32: 239.5, 48: 237.9, 64: 228.4}
_V_OB_DELIV   = {24: 235.7, 32: 235.7, 48: 234.7, 64: 228.4}
_V_BILL_DELIV = {64: 235.6}
_V_SPOT_EDGE  = {24: +4.12, 32: +4.50, 48: +7.31, 64: -2.69}
_V_OB_EDGE    = {24: +0.88, 32: +0.69, 48: +4.06, 64: -2.69}
_V_BILL_EDGE  = {64: +4.50}
_V_BILL_FARDM = 0.47                       # P23a bills far-band delivered/mined


def p29v2(rows: list[dict]) -> None:
    """v31 (column V2) — the DEPOT on the column-G geometry ladder. Report, not
    verdict. The mandatory comparison is against V's P29 numbers (spot / bills /
    order-book), reproduced here from the same G config plus the new depot arm.
    PV2a (does the depot lift the G64 edge above bills-only +4.50 and far-band d/m
    above bills' 0.47?), PV2b (≥2-hop share at G64 → its G48 level?), PV2c (mined
    per drone-tick rises?), and the KILL (depot ≤ bills-only at G64 ⇒ co-presence
    was never the binding constraint either). No-op unless a depot arm is present."""
    if not any(r.get("depots") for r in rows):
        return
    GS = [24, 32, 48, 64]
    ARMS = [("snhp+net", "spot"), ("snhp+bill", "bills"), ("snhp+depot", "depot")]

    def cond_g(g):
        c = list(_BASE)
        c[5] = g
        return tuple(c)

    def dmean(arm, g):
        vals = [r["delivered"] for r in rows
                if r["arm"] == arm and r.get("grid") == g and _cond(r) == cond_g(g)]
        return float(np.mean(vals)) if vals else float("nan")

    def edge(arm, g):
        return _paired(rows, arm, "auction", 0.5, "delivered", tau=0.15,
                       cond=cond_g(g))

    def lrows(arm, g):
        return [r for r in rows if r["arm"] == arm and r.get("grid") == g
                and r.get("lineage_detail")]

    # The FAR band on the G ladder is band 1 (30-62 cells) — the OUTER band that
    # holds rocks at grid ≤64 (4 of 10 rocks at G48/G64; NONE at G24/G32). The >62
    # band (index 2) is EMPTY at every ladder grid, so the P23a far-band d/m 0.47
    # (measured at N=240 scale where the >62 band is populated) is NOT directly
    # commensurable — the ladder's own outer-band signature is what these report.
    FAR = 1

    def far_dm(arm, g):                 # pooled outer-band delivered/mined (band 1)
        rs = lrows(arm, g)
        if not rs:
            return float("nan")
        bd = sum(r["lineage_detail"]["band_delivered"][FAR] for r in rs)
        bm = sum(r["lineage_detail"]["band_mined"][FAR] for r in rs)
        return bd / bm if bm else float("nan")

    def twohop(arm, g):                 # pooled ≥2-hop share of delivered units
        rs = lrows(arm, g)
        if not rs:
            return float("nan")
        h2 = sum(r["lineage_detail"]["hop_counts"][2] for r in rs)
        nd = sum(r["lineage_detail"]["n_delivered"] for r in rs)
        return h2 / nd if nd else float("nan")

    def mined_pdt(arm, g, band=None):   # mined units per drone × fixed horizon-tick
        # Fixed horizon denominator (NOT makespan) so the rate is not confounded by
        # an arm finishing early — it measures total extraction per drone over the
        # 2,500-tick window. band="far" ⇒ the outer band (index FAR).
        rs = lrows(arm, g)
        vals = []
        for r in rs:
            bm = r["lineage_detail"]["band_mined"]
            n = r.get("n_robots", 24)
            hz = r.get("ticks_horizon", 2500)
            tot = bm[FAR] if band == "far" else sum(bm)
            vals.append(tot / (n * hz))
        return float(np.mean(vals)) if vals else float("nan")

    def obdet(g, field):                # depot async accounting (order_book_detail)
        vals = [r["order_book_detail"][field] for r in rows
                if r["arm"] == "snhp+depot" and r.get("grid") == g
                and r.get("order_book_detail")]
        return float(np.mean(vals)) if vals else float("nan")

    print("\n" + "=" * 100)
    print("PV2 (column V2) — THE DEPOT (async deposit-and-return) on the G "
          "geometry ladder (σ=0.5, τ=0.15, v5, 2500t, 16 seeds)")
    print("=" * 100)

    print("\n[1] DELIVERED by grid × arm  (auction=comparator · spot=snhp+net · "
          "bills=snhp+bill · depot=snhp+depot) — V's P29 numbers in [brackets]:")
    h = (f"  {'G':>4} {'auction':>9} {'spot':>9} {'[V spot]':>10} {'bills':>9} "
         f"{'depot':>9} {'[V ob]':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        print(f"  {g:>4} {dmean('auction',g):>9.1f} {dmean('snhp+net',g):>9.1f} "
              f"{('['+format(_V_SPOT_DELIV[g],'.1f')+']'):>10} "
              f"{dmean('snhp+bill',g):>9.1f} {dmean('snhp+depot',g):>9.1f} "
              f"{('['+format(_V_OB_DELIV[g],'.1f')+']'):>9}")

    print("\n[2] PV2a [THE EDGE] — arm−auction delivered edge by G (paired on seed) "
          "vs V's P29 baselines:")
    print("    beats bills-only (+4.50@G64) and recovers the G64 trough (spot −2.69)?")
    h = (f"  {'G':>4} {'spot':>8} {'[V]':>7} {'bills':>8} {'[V]':>7} "
         f"{'depot':>8} {'depot−bills':>12}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    edges = {}
    for g in GS:
        es, eb, ed = edge("snhp+net", g), edge("snhp+bill", g), edge("snhp+depot", g)
        edges[g] = (es, eb, ed)
        vs = f"[{_V_SPOT_EDGE[g]:+.2f}]"
        vb = f"[{_V_BILL_EDGE[g]:+.2f}]" if g in _V_BILL_EDGE else f"[{'—'}]"
        dmb = (ed["delta"] - eb["delta"]) if (ed and eb) else float("nan")
        print(f"  {g:>4} {(es['delta'] if es else float('nan')):>+8.2f} {vs:>7} "
              f"{(eb['delta'] if eb else float('nan')):>+8.2f} {vb:>7} "
              f"{(ed['delta'] if ed else float('nan')):>+8.2f} {dmb:>+12.2f}")

    print(f"\n[3] PV2a [FAR-BAND delivered/mined] by G × arm (outer band "
          f"{LINEAGE_BANDS[0]}-{LINEAGE_BANDS[1]}c — the >{LINEAGE_BANDS[1]}c band is "
          f"EMPTY on the ladder; N=240-scale P23a bills far d/m was {_V_BILL_FARDM}, "
          f"not directly commensurable):")
    h = f"  {'G':>4} {'spot':>9} {'bills':>9} {'depot':>9} {'depot−bills':>12}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        fs, fb, fd = far_dm("snhp+net",g), far_dm("snhp+bill",g), far_dm("snhp+depot",g)
        print(f"  {g:>4} {fs:>9.3f} {fb:>9.3f} {fd:>9.3f} {(fd-fb):>+12.3f}")

    print("\n[4] PV2b [≥2-HOP SHARE] of delivered units by G × arm "
          "(does depot's G64 share approach its G48 level — chains decouple from "
          "encounter rate?):")
    h = f"  {'G':>4} {'spot':>9} {'bills':>9} {'depot':>9}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    depot_2hop = {}
    for g in GS:
        ts, tb, td = twohop("snhp+net",g), twohop("snhp+bill",g), twohop("snhp+depot",g)
        depot_2hop[g] = td
        print(f"  {g:>4} {ts:>9.3f} {tb:>9.3f} {td:>9.3f}")

    print("\n[5] PV2c [MINED per drone-tick] by G × arm (does deposit-and-return "
          "lift mining? total · far-band):")
    h = (f"  {'G':>4} {'spot':>9} {'bills':>9} {'depot':>9}   "
         f"{'spotFar':>8} {'billFar':>8} {'depotFar':>8}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        print(f"  {g:>4} {mined_pdt('snhp+net',g):>9.4f} "
              f"{mined_pdt('snhp+bill',g):>9.4f} {mined_pdt('snhp+depot',g):>9.4f}   "
              f"{mined_pdt('snhp+net',g,'far'):>8.4f} "
              f"{mined_pdt('snhp+bill',g,'far'):>8.4f} "
              f"{mined_pdt('snhp+depot',g,'far'):>8.4f}")

    print("\n[6] DEPOT ASYNC ACCOUNTING (snhp+depot; conservation must hold):")
    h = (f"  {'G':>4} {'posted':>8} {'accepted':>9} {'expired':>8} {'async_sh':>9} "
         f"{'pauseSaved':>11} {'cargoWO':>8} {'pinnedEnd':>10} {'escrowOK':>9}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for g in GS:
        oks = [r["order_book_detail"]["escrow_ok"] for r in rows
               if r["arm"] == "snhp+depot" and r.get("grid") == g
               and r.get("order_book_detail")]
        print(f"  {g:>4} {obdet(g,'posted'):>8.1f} {obdet(g,'accepted'):>9.1f} "
              f"{obdet(g,'expired'):>8.1f} {obdet(g,'async_share'):>9.3f} "
              f"{obdet(g,'pause_ticks_saved'):>11.0f} "
              f"{obdet(g,'cargo_writeoff'):>8.2f} {obdet(g,'pinned_final'):>10.2f} "
              f"{('all' if oks and all(oks) else 'FAIL!'):>9}")

    print("\n[7] READ (PV2a / PV2b / PV2c / KILL):")
    ed64 = edges[64][2]; eb64 = edges[64][1]
    if ed64 and eb64:
        depot64, bills64 = ed64["delta"], eb64["delta"]
        kill = depot64 <= bills64 + 1e-9
        print(f"    edge(G64): depot = {depot64:+.2f}  vs  bills-only = {bills64:+.2f} "
              f"(V bills +4.50)  ⇒  {'KILL FIRES (depot ≤ bills-only)' if kill else 'PV2a MET (depot > bills-only)'}")
        fd64 = far_dm("snhp+depot", 64); fb64 = far_dm("snhp+bill", 64)
        print(f"    far-band d/m @G64: depot = {fd64:.3f}  vs  bills = {fb64:.3f} "
              f"(V bills {_V_BILL_FARDM})  ⇒  PV2a far-band {'MET' if fd64 > fb64 else 'NOT met'}")
        as64 = obdet(64, "async_share")
        print(f"    ≥2-hop @G64 = {depot_2hop[64]:.3f} vs @G48 = {depot_2hop[48]:.3f} "
              f"BUT depot async_share @G64 = {as64:.3f} — the ≥2-hop is the SYNCHRONOUS "
              f"bills backbone, not the async deposits (PV2b not attributable to the depot)")
        md = mined_pdt("snhp+depot", 64, "far"); mb = mined_pdt("snhp+bill", 64, "far")
        pv2c = "MET" if md > mb + 5e-5 else ("TIE/NULL" if abs(md - mb) <= 5e-5 else "NOT met")
        print(f"    far mined/drone-tick @G64: depot = {md:.5f}  vs  bills = {mb:.5f}"
              f"  ⇒  PV2c {pv2c} (deposit-and-return no meaningful far-mining lift)")
        print(f"    >>> KILL {'FIRES' if kill else 'does NOT fire'}: "
              + ("co-presence was never the binding constraint for chains either — "
                 "travel/battery dominates even warehoused async relay."
                 if kill else
                 "the depot lifts the G64 edge above bills-only — warehoused async "
                 "relay carries loads synchronous chains refused."))


def p24(rows: list[dict]) -> None:
    """v18 (column Q) — endogenous infrastructure ("the sim grows landlords").
    Report, not verdict: P24a (do built chargers lift the N=240 plateau by ≥0.05
    delivered_frac?), P24b (under-provision + cross-company toll pricing), P24c
    (build-auction vs build-bargaining), and the KILL (building never beats saving
    the resources). No-op unless the sweep carries the matter field."""
    if not any(r.get("build_matter", 0) for r in rows):
        return
    ORE_TOTAL = 2 * TOTAL_STOCK * 240 // 24            # N=240 ore total = 2400

    def sel(label, horizon=None, budget=None, toll=0.0):
        # Defaults isolate the CORE cell (unlimited budget → None, toll-free):
        # no-build and CORE-build rows both carry build_budget=None, toll_level=0,
        # so sel(arm[,+B], H) returns ONLY the core arm — the budget sweep
        # (build_budget∈{0,2,4,8,16}) and toll sweep (toll_level∈{1,2,4}) are
        # reached by overriding budget=/toll= explicitly.
        out = []
        for r in rows:
            if r["arm"] != label:
                continue
            if horizon is not None and r.get("ticks_horizon") != horizon:
                continue
            if budget != "__any__" and r.get("build_budget") != budget:
                continue
            if toll != "__any__" and abs(r.get("toll_level", 0.0) - toll) > 1e-9:
                continue
            out.append(r)
        return out

    def mean(rs, field, sub=None):
        vals = []
        for r in rs:
            v = r.get(field) if sub is None else (r.get("build_detail") or {}).get(field)
            if v is not None:
                vals.append(v)
        return float(np.mean(vals)) if vals else float("nan")

    def paired(hi_rs, lo_rs, field):
        hi = {r["seed"]: r[field] for r in hi_rs if r.get(field) is not None}
        lo = {r["seed"]: r[field] for r in lo_rs if r.get(field) is not None}
        common = sorted(set(hi) & set(lo))
        if len(common) < 3:
            return None
        d = np.array([hi[s] - lo[s] for s in common])
        _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
        return dict(delta=float(d.mean()), p=float(pt),
                    wins=int((d > 0).sum()), n=len(common))

    print("\n" + "=" * 100)
    print("P24 (column Q) — ENDOGENOUS INFRASTRUCTURE: the sim grows landlords "
          "(N=240 scaled v5, σ=0.5, τ=0.15, build_matter=0.5, 8 seeds)")
    print("=" * 100)

    print("\n[1] DELIVERED & delivered_frac by arm × horizon "
          "(no-build control vs build-capable):")
    h = (f"  {'arm':>10} {'H':>6} {'no-build':>9} {'frac':>6} {'build':>9} "
         f"{'frac':>6} {'built':>6} {'Δdeliv':>8} {'Δfrac':>7}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    p24a = {}
    for arm in ("snhp+net", "auction"):
        for H in (2500, 7500):
            nb = sel(arm, H)
            bd = sel(arm + "+B", H)
            dnb, fnb = mean(nb, "delivered"), mean(nb, "delivered_frac")
            dbd, fbd = mean(bd, "delivered"), mean(bd, "delivered_frac")
            nbuilt = mean(bd, "n_built", sub=True)
            pe = paired(bd, nb, "delivered")
            pf = paired(bd, nb, "delivered_frac")
            p24a[(arm, H)] = (pe, pf)
            print(f"  {arm:>10} {H:>6} {dnb:>9.1f} {fnb:>6.3f} {dbd:>9.1f} "
                  f"{fbd:>6.3f} {nbuilt:>6.1f} "
                  f"{(pe['delta'] if pe else float('nan')):>+8.1f} "
                  f"{(pf['delta'] if pf else float('nan')):>+7.3f}")

    print("\n[2] P24a [DOES BUILDING LIFT THE PLATEAU?] — paired build−control "
          "delivered_frac edge (threshold +0.05):")
    for arm in ("snhp+net", "auction"):
        for H in (2500, 7500):
            pf = p24a[(arm, H)][1]
            if pf:
                verdict = "LIFTS (P24a)" if pf["delta"] >= 0.05 else "no lift"
                print(f"    {arm:>10} H={H}: Δfrac={pf['delta']:+.3f} "
                      f"(p={pf['p']:.3f}, {pf['wins']}/{pf['n']} wins) → {verdict}")

    print("\n[3] TRUNCATION CHECK — delivered at 2500 vs 7500 (if flat, the "
          "plateau is a HARD STALL, not horizon-censoring):")
    for arm in ("snhp+net", "auction"):
        for tag, lbl in (("", "no-build"), ("+B", "build")):
            d25 = mean(sel(arm + tag, 2500), "delivered")
            d75 = mean(sel(arm + tag, 7500), "delivered")
            print(f"    {arm+tag:>12} ({lbl:>8}): 2500t={d25:.1f}  7500t={d75:.1f} "
                  f"  Δ(5000 extra ticks)={d75-d25:+.1f}")

    print("\n[4] THE PLATEAU MECHANISM — ore MINED but never delivered (held in "
          "loads at horizon) & stranding. Building should DRAIN held_load if it "
          "relieves the constraint:")
    h = f"  {'arm':>12} {'H':>6} {'delivered':>10} {'held_load':>10} {'stranded':>9}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    for arm in ("snhp+net", "auction"):
        for tag in ("", "+B"):
            for H in (2500, 7500):
                rs = sel(arm + tag, H)
                print(f"  {arm+tag:>12} {H:>6} {mean(rs,'delivered'):>10.1f} "
                      f"{mean(rs,'held_load'):>10.1f} {mean(rs,'stranded'):>9.1f}")

    print("\n[5] P24c [SITING COORDINATION] — build gain (build−control delivered) "
          "for the BARGAINING fleet vs the AUCTION fleet (P24c: bargaining should "
          "gain MORE):")
    for H in (2500, 7500):
        gs = p24a[("snhp+net", H)][0]
        ga = p24a[("auction", H)][0]
        if gs and ga:
            print(f"    H={H}: snhp+net build-gain={gs['delta']:+.1f}  "
                  f"auction build-gain={ga['delta']:+.1f}  "
                  f"→ {'bargaining gains more (P24c)' if gs['delta']>ga['delta'] else 'auction ≥ bargaining (P24c refuted)'}")

    print("\n[6] PLACEMENT MAP — built-charger count/timing & distance band of the "
          "targeted rock (≤30 home · 31-62 mid · >62 far). early sites target "
          "far-ore; later sites target the loaded-return trapped-cargo centroid:")
    bd = sel("snhp+net+B", 2500)
    if bd:
        det = [r["build_detail"] for r in bd if r.get("build_detail")]
        if det:
            print(f"    built total = {mean(bd,'n_built',sub=True):.1f}; "
                  f"first@tick~{mean(bd,'first_built',sub=True):.0f}, "
                  f"median@tick~{mean(bd,'median_built_tick',sub=True):.0f}, "
                  f"late(>½horizon)~{mean(bd,'late_built',sub=True):.1f}")
            bh = np.mean([d["placement_band_hist"] for d in det], axis=0)
            print(f"    placement dist-band histogram (far-ore fallback sites only) "
                  f"[home,mid,far] = {[round(x,1) for x in bh]}")
            print(f"    sample built sites (seed {det[0].get('toll_level','?')}): "
                  f"{det[0]['built_sites'][:6]}")
            print(f"    matter mined~{mean(bd,'matter_mined',sub=True):.0f} of "
                  f"{mean(bd,'matter_initial',sub=True):.0f} seeded; "
                  f"build_credit_spend/co~{[round(x) for x in np.mean([d['build_spend'] for d in det],axis=0)]}")

    print("\n[7] P24b [UNDER-PROVISION] — welfare (delivered) vs FORCED per-company "
          "build budget (2500t). Under-provision ⇒ welfare rises with count PAST "
          "the voluntary build:")
    h = f"  {'budget':>7} {'delivered':>10} {'frac':>6} {'built_tot':>10} {'held_load':>10}"
    print(h)
    print("  " + "-" * (len(h) - 2))
    welf = {}
    for budget in (0, 2, 4, 8, 16):
        rs = sel("snhp+net+B", 2500, budget=budget)
        if not rs:
            continue
        d = mean(rs, "delivered")
        welf[budget] = d
        print(f"  {budget:>7} {d:>10.1f} {mean(rs,'delivered_frac'):>6.3f} "
              f"{mean(rs,'n_built',sub=True):>10.1f} {mean(rs,'held_load'):>10.1f}")
    if welf:
        best_b = max(welf, key=welf.get)
        volb = mean(sel("snhp+net+B", 2500, budget=None), "n_built", sub=True)
        print(f"    welfare-optimal forced budget = {best_b}/co "
              f"(delivered {welf[best_b]:.1f}); voluntary build ≈ {volb:.1f} total. "
              f"{'UNDER-PROVISION' if welf.get(best_b,0) - welf.get(0,0) > 5 and best_b*2 > volb else 'NO under-provision — welfare flat/negative in count'}")

    print("\n[8] P24b [CROSS-COMPANY TOLL PRICING] — the toll dial on ENDOGENOUS "
          "chargers (2500t). owner guest-revenue & built-charger guest slots by "
          "toll level (grid = free/cost/2×/4×):")
    h = (f"  {'toll':>6} {'delivered':>10} {'built_guest_slots':>18} "
         f"{'toll_earned_tot':>16} {'built':>7}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    from swarm.world import TOLL_GRID as _TG
    for toll in _TG:
        rs = (sel("snhp+net+B", 2500, budget=None, toll=toll) if toll == 0.0
              else sel("snhp+net+B", 2500, toll=toll))
        if not rs:
            continue
        det = [r["build_detail"] for r in rs if r.get("build_detail")]
        gslots = float(np.mean([d["built_guest_slots"] for d in det])) if det else 0.0
        tearn = float(np.mean([sum(d["toll_earned"]) for d in det])) if det else 0.0
        print(f"  {toll:>6.1f} {mean(rs,'delivered'):>10.1f} {gslots:>18.1f} "
              f"{tearn:>16.2f} {mean(rs,'n_built',sub=True):>7.1f}")
    pg = mean(sel("snhp+net+B", 2500, budget=None), "guest_charged")
    print(f"    CONTRAST: PRESET (exogenous, central) chargers serve "
          f"~{pg:.0f} guest-energy/run — the built (endogenous, own-corridor) "
          f"chargers' guest throughput above is the toll-booth's ACTUAL reach.")

    print("\n[9] KILL STATUS — 'if building never beats saving the resources for "
          "direct operations, infrastructure is decorative at these scales.'")
    lifts = [p24a[k][1] for k in p24a if p24a[k][1] and p24a[k][1]["delta"] >= 0.05]
    anypos = any(p24a[k][0] and p24a[k][0]["delta"] > 2.0 for k in p24a)
    if lifts:
        print("    → P24a SUPPORTED: at least one arm/horizon lifts frac ≥0.05.")
    else:
        print("    → KILL FIRES: no arm/horizon lifts the plateau ≥0.05 delivered_frac; "
              "welfare is flat/negative in charger count. Building is decorative — the "
              "N=240 constraint is charge-ROUTING (single-hop loaded-return planning "
              "traps mined ore at dead-end chargers), NOT charge-SUPPLY (capital). "
              f"{'(build did edge delivered slightly positive but far below threshold.)' if anypos else ''}")


def p24r(rows: list[dict]) -> None:
    """v18-R (column Q2) — LANDLORDS ON THE FRONTIER: column Q re-run under FRONTIER
    SCARCITY (preset free chargers only within single-hop loaded reach of a refinery)
    + BILLS ON for the bargaining fleet. Report, not verdict: P24R-a (does building
    lift the far-band ≥0.05 over the BILLS no-build control at 7,500t, and does the
    far-ore placement fallback fire?), P24R-b (do tolls on far chargers extract real
    rent above Q's 7.88cr; budget-sweep under-provision), P24R-c (build edge under
    bills > build edge under spot — the layering claim), and the KILL (building AND
    tolls stay decorative even with scarcity + bills). No-op unless the sweep carries
    a frontier-scarce (charger_band>0) cell."""
    if not any(r.get("charger_band", 0.0) > 0 for r in rows):
        return
    from swarm.world import (BATTERY_MAX as _BM, LOADED_MULT as _LM,
                             MATTER_COST as _MC, BUILD_CREDIT_COST as _BCC)
    BAND = _BM / (1.0 + _LM)

    def sel(label, horizon=None, budget=None, toll=0.0, scarce=True):
        out = []
        for r in rows:
            if r["arm"] != label:
                continue
            if (r.get("charger_band", 0.0) > 0) != scarce:
                continue
            if horizon is not None and r.get("ticks_horizon") != horizon:
                continue
            if budget != "__any__" and r.get("build_budget") != budget:
                continue
            if toll != "__any__" and abs(r.get("toll_level", 0.0) - toll) > 1e-9:
                continue
            out.append(r)
        return out

    def _far(r):
        ld = r.get("lineage_detail")
        if not ld:
            return None
        bm = ld["band_mined"][2]
        return (ld["band_delivered"][2] / bm) if bm else None

    def _hop2(r):
        ld = r.get("lineage_detail")
        return ld["hop_shares"][2] if ld else None

    def mean(rs, field):
        vals = [r[field] for r in rs if r.get(field) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def meanf(rs, fn):
        vals = [fn(r) for r in rs]
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def paired(hi_rs, lo_rs, fn):
        """Paired hi−lo on a per-row extractor fn (delivered/frac/far-band)."""
        hi = {r["seed"]: fn(r) for r in hi_rs if fn(r) is not None}
        lo = {r["seed"]: fn(r) for r in lo_rs if fn(r) is not None}
        common = sorted(set(hi) & set(lo))
        if len(common) < 3:
            return None
        d = np.array([hi[s] - lo[s] for s in common])
        _, pt = stats.ttest_rel([hi[s] for s in common], [lo[s] for s in common])
        return dict(delta=float(d.mean()), p=float(pt),
                    wins=int((d > 0).sum()), n=len(common))

    # arm family → (no-build label, build label)
    FAM = [("snhp+net+bills", "snhp+bill", "snhp+net+B+bill"),
           ("snhp+net spot ", "snhp+net",  "snhp+net+B"),
           ("auction       ", "auction",   "auction+B")]

    print("\n" + "=" * 100)
    print("P24-R (column Q2) — LANDLORDS ON THE FRONTIER: frontier scarcity + bills "
          f"(N=240 scaled v5, σ=0.5, τ=0.15, build_matter=0.5, band={BAND:g}, 8 seeds)")
    print("=" * 100)

    # [0] BILLS-FLAG VERIFICATION — the scarcity-OFF bills no-build MUST reproduce the
    # P23 bills signature (0.857 / 0.47 / 0.50); the SPOT signature (0.829/0.40/0.025)
    # would mean bills never fired (the Q miss). Scarcity-ON bills no-build alongside.
    print("\n[0] BILLS-SIGNATURE CHECK (the Q-miss guard) — snhp+net BILLS no-build:")
    print(f"    {'regime':>22} {'delivered_frac':>15} {'far-band d/m':>13} {'≥2-hop':>8}")
    for tag, scarce in (("scarcity OFF (pure P23)", False),
                        ("scarcity ON  (Q2 base )", True)):
        rs = sel("snhp+bill", 2500, scarce=scarce)
        print(f"    {tag:>22} {mean(rs,'delivered_frac'):>15.3f} "
              f"{meanf(rs,_far):>13.3f} {meanf(rs,_hop2):>8.3f}")
    print("    P23 bills signature = 0.857 / 0.470 / 0.492 ;  SPOT signature = "
          "0.829 / 0.399 / 0.025.")
    off = sel("snhp+bill", 2500, scarce=False)
    sig_ok = (not np.isnan(meanf(off, _hop2))) and meanf(off, _hop2) > 0.30
    print(f"    → BILLS FLAG {'CONFIRMED ON' if sig_ok else 'NOT FIRING — STOP'} "
          f"(scarcity-OFF ≥2-hop = {meanf(off,_hop2):.3f}; bills⇒~0.49, spot⇒~0.025).")

    # [1] the master table: delivered_frac / far-band / ≥2-hop, no-build vs build.
    print("\n[1] DELIVERED_FRAC · FAR-BAND d/m · ≥2-HOP SHARE, by arm × horizon "
          "(scarcity ON):")
    hdr = (f"  {'arm':>15} {'H':>5} | {'nb_frac':>7} {'bd_frac':>7} {'Δfrac':>7} | "
           f"{'nb_far':>6} {'bd_far':>6} {'Δfar':>6} | {'nb_h2':>6} {'bd_h2':>6} | "
           f"{'built':>5}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    farlift = {}      # (fam, H) → paired far-band build−nobuild
    edgeD = {}        # (fam, H) → paired delivered build−nobuild
    for fam, nbl, bdl in FAM:
        for H in (2500, 7500):
            nb, bd = sel(nbl, H), sel(bdl, H)
            pf = paired(bd, nb, _far)
            pfrac = paired(bd, nb, lambda r: r.get("delivered_frac"))
            pe = paired(bd, nb, lambda r: r.get("delivered"))
            farlift[(fam, H)] = pf
            edgeD[(fam, H)] = pe
            nbuilt = np.mean([(r.get("build_detail") or {}).get("n_built", 0)
                              for r in bd]) if bd else float("nan")
            print(f"  {fam:>15} {H:>5} | {mean(nb,'delivered_frac'):>7.3f} "
                  f"{mean(bd,'delivered_frac'):>7.3f} "
                  f"{(pfrac['delta'] if pfrac else float('nan')):>+7.3f} | "
                  f"{meanf(nb,_far):>6.3f} {meanf(bd,_far):>6.3f} "
                  f"{(pf['delta'] if pf else float('nan')):>+6.3f} | "
                  f"{meanf(nb,_hop2):>6.3f} {meanf(bd,_hop2):>6.3f} | "
                  f"{nbuilt:>5.1f}")

    # [2] P24R-a — far-band lift over the BILLS no-build control at 7,500t (≥0.05).
    print("\n[2] P24R-a [DOES BUILDING LIFT THE FAR BAND?] — paired build−no-build "
          "far-band d/m (threshold +0.05, headline arm = snhp+net+bills @ 7,500t):")
    for fam, _, _ in FAM:
        for H in (2500, 7500):
            pf = farlift[(fam, H)]
            if pf:
                v = "LIFTS (P24R-a)" if pf["delta"] >= 0.05 else "no lift"
                print(f"    {fam:>15} H={H}: Δfar={pf['delta']:+.3f} "
                      f"(p={pf['p']:.3f}, {pf['wins']}/{pf['n']}) → {v}")

    # [3] PLACEMENT — does the far-ore fallback fire? (band of the TARGETED rock).
    print("\n[3] PLACEMENT BANDS [home≤30 · mid31-62 · far>62] (snhp+net+bills build). "
          "site-hist = ALL built SITES; fallback-hist = far-ore TARGET rocks (>0 ⇒ "
          "the far-ore fallback fires; else all builds are trapped-return corridor):")
    for H in (2500, 7500):
        bd = sel("snhp+net+B+bill", H)
        det = [r["build_detail"] for r in bd if r.get("build_detail")]
        if det:
            sh = np.mean([d["site_band_hist"] for d in det], axis=0)
            fh = np.mean([d["placement_band_hist"] for d in det], axis=0)
            fb = [d["first_built"] for d in det if d["first_built"] is not None]
            print(f"    H={H}: built~{np.mean([d['n_built'] for d in det]):.1f}"
                  f"  first@~{(np.mean(fb) if fb else float('nan')):.0f}"
                  f"  matter_mined~{np.mean([d['matter_mined'] for d in det]):.0f}")
            print(f"          site-band-hist    =[{sh[0]:.1f}, {sh[1]:.1f}, {sh[2]:.1f}]")
            print(f"          fallback-band-hist=[{fh[0]:.1f}, {fh[1]:.1f}, {fh[2]:.1f}]")
            print(f"          sample built sites: {det[0]['built_sites'][:6]}")

    # [4] P24R-c — the layering claim: build edge (delivered) under BILLS vs SPOT.
    print("\n[4] P24R-c [LAYERING] — build−no-build DELIVERED edge: BILLS vs SPOT "
          "(claim: infrastructure and claim-chains are complements ⇒ bills edge > spot):")
    for H in (2500, 7500):
        eb, es = edgeD[("snhp+net+bills", H)], edgeD[("snhp+net spot ", H)]
        if eb and es:
            v = ("bills edge > spot (P24R-c SUPPORTED)"
                 if eb["delta"] > es["delta"] else "spot ≥ bills (P24R-c refuted)")
            print(f"    H={H}: bills build-edge={eb['delta']:+.1f}  "
                  f"spot build-edge={es['delta']:+.1f}  → {v}")

    # [5] P24R-b (toll) — cross-company rent on ENDOGENOUS chargers, vs Q's 7.88cr.
    print("\n[5] P24R-b [CROSS-COMPANY TOLL RENT] — owner guest-revenue on BUILT "
          "chargers by toll (snhp+net+bills build, 2500t; Q's farce was 7.88cr total):")
    from swarm.world import TOLL_GRID as _TG
    print(f"    {'toll':>6} {'delivered':>10} {'built_guest_slots':>18} "
          f"{'toll_earned_tot':>16} {'built':>7}")
    tearn_by = {}
    for toll in _TG:
        rs = sel("snhp+net+B+bill", 2500, toll=toll)
        if not rs:
            continue
        det = [r["build_detail"] for r in rs if r.get("build_detail")]
        gslots = float(np.mean([d["built_guest_slots"] for d in det])) if det else 0.0
        tearn = float(np.mean([sum(d["toll_earned"]) for d in det])) if det else 0.0
        tearn_by[toll] = tearn
        nb = float(np.mean([d["n_built"] for d in det])) if det else 0.0
        print(f"    {toll:>6.1f} {mean(rs,'delivered'):>10.1f} {gslots:>18.1f} "
              f"{tearn:>16.2f} {nb:>7.1f}")
    pg = mean(sel("snhp+net+B+bill", 2500), "guest_charged")
    best_rent = max(tearn_by.values()) if tearn_by else 0.0
    print(f"    PRESET (in-band, free) chargers serve ~{pg:.0f} guest-energy/run. "
          f"max built-charger toll rent = {best_rent:.2f}cr "
          f"({'ABOVE' if best_rent > 7.88 else 'AT/BELOW'} Q's 7.88cr).")

    # [6] P24R-b (budget) — under-provision where capital is actually scarce.
    print("\n[6] P24R-b [UNDER-PROVISION] — welfare (delivered) vs FORCED per-company "
          "build budget (snhp+net+bills build, 2500t):")
    print(f"    {'budget':>7} {'delivered':>10} {'frac':>6} {'far-band':>9} "
          f"{'built_tot':>10} {'held_load':>10}")
    welf = {}
    for budget in (0, 2, 4, 8, 16):
        rs = sel("snhp+net+B+bill", 2500, budget=budget)
        if not rs:
            continue
        det = [r["build_detail"] for r in rs if r.get("build_detail")]
        nb = float(np.mean([d["n_built"] for d in det])) if det else 0.0
        welf[budget] = mean(rs, "delivered")
        print(f"    {budget:>7} {mean(rs,'delivered'):>10.1f} "
              f"{mean(rs,'delivered_frac'):>6.3f} {meanf(rs,_far):>9.3f} "
              f"{nb:>10.1f} {mean(rs,'held_load'):>10.1f}")
    if welf:
        best_b = max(welf, key=welf.get)
        volb = float(np.mean([d["n_built"]
                     for r in sel("snhp+net+B+bill", 2500, budget=None)
                     if (d := r.get("build_detail"))])) if \
            sel("snhp+net+B+bill", 2500, budget=None) else float("nan")
        up = welf.get(best_b, 0) - welf.get(0, 0) > 5 and best_b * 2 > volb
        print(f"    welfare-optimal forced budget = {best_b}/co "
              f"(delivered {welf[best_b]:.1f}); voluntary build ≈ {volb:.1f} total → "
              f"{'UNDER-PROVISION' if up else 'no under-provision'}.")

    # [7] KILL — building AND tolls decorative even with scarcity + bills?
    print("\n[7] KILL STATUS — 'if building and tolls stay decorative even with "
          "frontier scarcity and bills, infrastructure rent is genuinely absent.'")
    hp = farlift.get(("snhp+net+bills", 7500))
    far_lift = hp["delta"] if hp else float("nan")
    rent_real = best_rent > 7.88
    if (hp and hp["delta"] >= 0.05) or rent_real:
        print(f"    → KILL DOES NOT FIRE: far-band lift={far_lift:+.3f} "
              f"(P24R-a {'MET' if hp and hp['delta']>=0.05 else 'unmet'}) · "
              f"max toll rent={best_rent:.2f}cr (P24R-b {'MET' if rent_real else 'unmet'}). "
              "Infrastructure rent is present under scarcity + bills.")
    else:
        print(f"    → KILL FIRES: far-band lift={far_lift:+.3f} (<0.05) AND max toll "
              f"rent={best_rent:.2f}cr (de minimis). Even with frontier scarcity and "
              "bills, building and tolls are decorative — the infrastructure-rent null "
              "graduates from artifact to LAW at these scales.")


def px(rows: list[dict]) -> None:
    """v25 (column X) — THE FIRM'S INTERIOR: command / prices / claims vs the
    no-mechanism baseline. Report, not verdict: PXa (command wins at small N,
    degrades with N), PXb (internal prices == baseline everywhere), PXc (claims
    win at N=240/7500 with the highest ≥2-hop hand-off share), and the KILL
    (command ≥ claims at N=240/7500 ⇒ receipts add nothing over hierarchy inside
    the firm). No-op unless the sweep carries the column-X deadlock instrument."""
    xr = [r for r in rows if r.get("deadlock_count") is not None]
    if not xr:
        return

    def regime(r) -> str:
        if r.get("command"):
            return "command"
        if r.get("firm_relay"):
            return "prices"
        if r.get("bills"):
            return "claims"
        return "baseline"

    Ns = sorted({r["n_robots"] for r in xr})
    Hs = sorted({r["ticks_horizon"] for r in xr})
    REG = ("baseline", "command", "prices", "claims")

    def sel(reg, N, H):
        return [r for r in xr if regime(r) == reg
                and r["n_robots"] == N and r["ticks_horizon"] == H]

    def hop2(r):
        ld = r.get("lineage_detail") or {}
        hs = ld.get("hop_shares")
        return hs[2] if hs else None

    def mean(g, getter):
        vals = [getter(r) for r in g]
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def paired(hi, lo, N, H, getter):
        A = {r["seed"]: getter(r) for r in sel(hi, N, H) if getter(r) is not None}
        B = {r["seed"]: getter(r) for r in sel(lo, N, H) if getter(r) is not None}
        common = sorted(set(A) & set(B))
        if len(common) < 3:
            return None
        d = np.array([A[s] - B[s] for s in common])
        _, pt = stats.ttest_rel([A[s] for s in common], [B[s] for s in common])
        return dict(delta=float(d.mean()), p=float(pt),
                    wins=int((d > 0).sum()), n=len(common))

    print("\n" + "=" * 100)
    print("PX (column X) — THE FIRM'S INTERIOR: command / prices / claims vs the "
          "no-mechanism baseline")
    print("  (N ∈ {24,96,240} × ticks {2500,7500}, σ=0.5, τ=0.15, v5 scaled grids, "
          "belief+gossip r_radio=6, 16 seeds / 8 at N=240)")
    print("=" * 100)

    print("\n[1] delivered / delivered_frac / per-drone payoff (mean credit) / "
          "≥2-hop hand-off share / deadlock entries, by regime × N × horizon:")
    h = (f"  {'regime':>9} {'N':>4} {'H':>6} {'deliv':>8} {'frac':>6} "
         f"{'payoff':>8} {'gini':>6} {'≥2hop':>7} {'deadlk':>7} {'hand':>6}")
    print(h)
    print("  " + "-" * (len(h) - 2))
    for N in Ns:
        for H in Hs:
            for reg in REG:
                g = sel(reg, N, H)
                if not g:
                    continue
                hand = mean(g, lambda r: (r.get("command_detail") or {}).get("handoffs")) \
                    if reg == "command" else float("nan")
                print(f"  {reg:>9} {N:>4} {H:>6} "
                      f"{mean(g, lambda r: r['delivered']):>8.1f} "
                      f"{mean(g, lambda r: r['delivered_frac']):>6.3f} "
                      f"{mean(g, lambda r: r['co_credit'][0] + r['co_credit'][1]) / N:>8.1f} "
                      f"{mean(g, lambda r: r['payoff_gini']):>6.3f} "
                      f"{mean(g, hop2):>7.3f} "
                      f"{mean(g, lambda r: r['deadlock_count']):>7.1f} "
                      f"{hand:>6.1f}")

    print("\n[2] CONTAMINATION CHECK — routing-deadlock entries per regime. The P24-caveat "
          "concern is COMMAND being routing-ADVANTAGED (a bespoke router ⇒ FEWER entries "
          "AND more delivered). A regime with MORE entries is resolving deadlocks (settlement "
          "recycling stuck drones through the frontier), not cheating on routing:")
    for N in Ns:
        for H in Hs:
            vals = {reg: mean(sel(reg, N, H), lambda r: r["deadlock_count"])
                    for reg in REG if sel(reg, N, H)}
            if not vals:
                continue
            cells = "  ".join(f"{k}={v:.1f}" for k, v in vals.items())
            base = vals.get("baseline")
            cmd = vals.get("command")
            note = ""
            if base is not None and cmd is not None and base > 0:
                # the caveat's red flag: command routing-advantaged (fewer deadlocks)
                cmd_lo = (base - cmd) / base
                if cmd_lo > 0.25:
                    note = f"  <-- command −{cmd_lo:.0%} vs baseline: CHECK it isn't a routing edge"
                else:
                    note = f"  (command≈baseline: no routing edge, Δ={cmd - base:+.0f})"
            print(f"    N={N:>3} H={H:>4}: {cells}{note}")

    print("\n[3] PXa — command − baseline on delivered (command should WIN small-N, "
          "DEGRADE with N):")
    for N in Ns:
        for H in Hs:
            c = paired("command", "baseline", N, H, lambda r: r["delivered"])
            if c:
                print(f"    N={N:>3} H={H:>4}: Δ={c['delta']:+7.1f}  p={c['p']:.3f}  "
                      f"wins {c['wins']}/{c['n']}")

    print("\n[4] PXb — internal prices − baseline on delivered (should be "
          "INDISTINGUISHABLE everywhere):")
    for N in Ns:
        for H in Hs:
            c = paired("prices", "baseline", N, H, lambda r: r["delivered"])
            if c:
                if c["delta"] == 0.0:
                    sig = "  (BIT-IDENTICAL — PXb maximally confirmed)"
                elif c["p"] == c["p"] and c["p"] < 0.05:   # p==p excludes nan
                    sig = "  <-- SIGNIFICANT (PXb strained)"
                else:
                    sig = "  (indistinguishable)"
                print(f"    N={N:>3} H={H:>4}: Δ={c['delta']:+7.1f}  p={c['p']:.3f}  "
                      f"wins {c['wins']}/{c['n']}{sig}")

    print("\n[5] PXc — claims − baseline on delivered, and the ≥2-hop hand-off share "
          "by regime (claims should top both at N=240/7500):")
    for N in Ns:
        for H in Hs:
            c = paired("claims", "baseline", N, H, lambda r: r["delivered"])
            if c:
                print(f"    N={N:>3} H={H:>4}: claims−base Δ={c['delta']:+7.1f}  "
                      f"p={c['p']:.3f}  wins {c['wins']}/{c['n']}")
    print("    ≥2-hop hand-off share (baseline / command / prices / claims):")
    for N in Ns:
        for H in Hs:
            shares = {reg: mean(sel(reg, N, H), hop2) for reg in REG if sel(reg, N, H)}
            if shares:
                print(f"      N={N:>3} H={H:>4}: " +
                      "  ".join(f"{k}={v:.3f}" for k, v in shares.items()))

    print("\n[6] PLAN-STALENESS (command): mean belief-age of mine-assignments at "
          "source · stale-at-execution frac · reach latency, by N × H:")
    for N in Ns:
        for H in Hs:
            g = sel("command", N, H)
            if not g:
                continue
            age = mean(g, lambda r: (r.get("command_detail") or {}).get("plan_belief_age_mean"))
            stale = mean(g, lambda r: (r.get("command_detail") or {}).get("stale_assign_frac"))
            lat = mean(g, lambda r: (r.get("command_detail") or {}).get("reach_latency_mean"))
            print(f"    N={N:>3} H={H:>4}: belief_age={age:>7.1f}  "
                  f"stale_frac={stale:.3f}  reach_lat={lat:>6.1f}")

    print("\n[7] KILL STATUS — command ≥ claims at N=240 / 7500 ⇒ receipts add nothing "
          "over hierarchy inside the firm:")
    N_kill, H_kill = 240, 7500
    if sel("command", N_kill, H_kill) and sel("claims", N_kill, H_kill):
        cvc = paired("command", "claims", N_kill, H_kill, lambda r: r["delivered"])
        cmd_d = mean(sel("command", N_kill, H_kill), lambda r: r["delivered"])
        clm_d = mean(sel("claims", N_kill, H_kill), lambda r: r["delivered"])
        print(f"    command delivered={cmd_d:.1f}  claims delivered={clm_d:.1f}  "
              f"Δ(command−claims)={cvc['delta']:+.1f}  p={cvc['p']:.3f}  "
              f"wins {cvc['wins']}/{cvc['n']}")
        if cvc["delta"] >= 0:
            print("    → KILL FIRES: command ≥ claims at the fair horizon — central "
                  "planning on shared belief matches/beats attested receipts inside "
                  "the firm; the internal-notary doctrine dies in this world.")
        else:
            print("    → KILL DOES NOT FIRE: claims > command at the fair horizon — "
                  "attested receipts beat hierarchy inside the firm (PXc direction).")
    else:
        print("    (N=240/7500 cells absent — cannot evaluate the KILL.)")


def p26(rows: list[dict]) -> None:
    """v20 (column S) — INSTITUTIONS AS A SUBSTITUTE FOR COGNITION. The 2×2:
    navigation {smart, dumb} × property rights {coarse, granular}. Report, not
    verdict.

    SCOPING (the honest version of 'dumb agents'): nav_dumb dumbs only the ROUTING
    brain — best_claim's richest-per-distance Φ target selection is swapped for a
    greedy nearest-KNOWN-rock pick + registered noise (world.NAV_DUMB_NOISE, drawn
    from the dedicated seed+262626 stream). Deals, physics and the deal-Φ
    evaluation are untouched: institutions here can substitute for PLANNING, not
    for the deal-evaluation faculty itself. GRANULAR rights = the v12/K2
    prospect-claims machinery (per-rock arrival WINDOWS + the sector issue the deal
    economy trades claim assignments through); COARSE = default sectors.

    - P26a: granular rights recover ≥50% of the delivered gap dumbing opens
      (recovery = dumb+granular − dumb+coarse; gap = smart+coarse − dumb+coarse).
    - P26b: the interaction term — granularity helps DUMB fleets more than SMART
      (substitutes): (dumb_gran−dumb_coarse) − (smart_gran−smart_coarse) > 0.
    - KILL: granular helps nobody, or only smart fleets ⇒ institutions COMPLEMENT
      rather than substitute cognition here."""
    sr = [r for r in rows if r.get("nav_dumb") is not None
          and r.get("dynamic_field") and r.get("contested")
          and r.get("scouting")]
    # keep only the column-S habitat (moving field + scouting); other columns that
    # happen to carry nav_dumb=False are excluded by requiring the S arms below.
    sr = [r for r in sr if r["arm"] in ("snhp+net", "auction")]
    if not sr:
        return

    Ns = sorted({r["n_robots"] for r in sr})
    Hs = sorted({r["ticks_horizon"] for r in sr})
    ARMS = [a for a in ("snhp+net", "auction") if any(r["arm"] == a for r in sr)]

    def cell(arm, dumb, gran, N, H):
        return [r for r in sr if r["arm"] == arm
                and bool(r["nav_dumb"]) == dumb
                and bool(r.get("prospect_claims")) == gran
                and r["n_robots"] == N and r["ticks_horizon"] == H]

    def mean(g, key):
        vals = [r[key] for r in g if r.get(key) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    def paired(hi, lo, key):
        A = {r["seed"]: r[key] for r in hi if r.get(key) is not None}
        B = {r["seed"]: r[key] for r in lo if r.get(key) is not None}
        common = sorted(set(A) & set(B))
        if len(common) < 3:
            return None
        d = np.array([A[s] - B[s] for s in common], float)
        _, pt = stats.ttest_rel([A[s] for s in common], [B[s] for s in common])
        return dict(delta=float(d.mean()), p=float(pt),
                    wins=int((d > 0).sum()), n=len(common))

    print("\n" + "=" * 100)
    print("P26 (column S) — INSTITUTIONS AS A SUBSTITUTE FOR COGNITION: the "
          "navigation × property-rights 2×2")
    print("  (σ=0.5, τ=0.15, v5, moving field: belief+dynamic+contested+K0 "
          "scouting; DUMB = greedy nearest-known + noise vs smart Φ-routing;")
    print("   GRANULAR = K2 prospect-claims windows + tradeable sector claims vs "
          "coarse sectors. nav_dumb dumbs ROUTING only — deal-Φ untouched.)")
    print("=" * 100)

    for N in Ns:
        for H in Hs:
            # only the full 2×2 lives at (N=24,H=2500) and (N=96,H=2500); the
            # 7500 horizon carries just the 3 spot-check cells (snhp+net).
            present = [(a, d, g) for a in ARMS for d in (False, True)
                       for g in (False, True) if cell(a, d, g, N, H)]
            if not present:
                continue
            print(f"\n--- N={N} · horizon={H} ---")
            hdr = (f"  {'arm':>9} {'nav':>6} {'rights':>8} {'deliv':>8} "
                   f"{'frac':>6} {'strand':>7} {'deals':>7} {'claimtr':>8} "
                   f"{'arr_mined':>9} {'seeds':>6}")
            print(hdr)
            print("  " + "-" * (len(hdr) - 2))
            for a in ARMS:
                for d in (False, True):
                    for g in (False, True):
                        cg = cell(a, d, g, N, H)
                        if not cg:
                            continue
                        print(f"  {a:>9} {('dumb' if d else 'smart'):>6} "
                              f"{('gran' if g else 'coarse'):>8} "
                              f"{mean(cg, 'delivered'):>8.1f} "
                              f"{mean(cg, 'delivered_frac'):>6.3f} "
                              f"{mean(cg, 'stranded'):>7.1f} "
                              f"{mean(cg, 'deals'):>7.0f} "
                              f"{mean(cg, 'claim_swaps'):>8.1f} "
                              f"{mean(cg, 'arrivals_mined'):>9.1f} "
                              f"{len(cg):>6}")

            # P26a / P26b on delivered, per arm, at this (N,H).
            for a in ARMS:
                sc = cell(a, False, False, N, H)   # smart coarse
                sg = cell(a, False, True, N, H)     # smart granular
                dc = cell(a, True, False, N, H)     # dumb  coarse
                dg = cell(a, True, True, N, H)       # dumb  granular
                if not (sc and sg and dc and dg):
                    continue
                m = {k: mean(v, 'delivered') for k, v in
                     (('sc', sc), ('sg', sg), ('dc', dc), ('dg', dg))}
                gap = m['sc'] - m['dc']                 # gap dumbing opens (coarse)
                rec = m['dg'] - m['dc']                 # granular's buy-back (dumb)
                help_dumb = m['dg'] - m['dc']
                help_smart = m['sg'] - m['sc']
                interaction = help_dumb - help_smart
                pct = (100.0 * rec / gap) if abs(gap) > 1e-9 else float("nan")
                pg = paired(sc, dc, 'delivered')        # is the gap real?
                pr = paired(dg, dc, 'delivered')        # does granular help dumb?
                ps = paired(sg, sc, 'delivered')        # does granular help smart?
                print(f"\n  [{a}] delivered means: "
                      f"smart+coarse={m['sc']:.1f}  smart+gran={m['sg']:.1f}  "
                      f"dumb+coarse={m['dc']:.1f}  dumb+gran={m['dg']:.1f}")
                print(f"    P26a  gap dumbing opens (smart−dumb | coarse) = "
                      f"{gap:+.1f}"
                      + (f"  [paired Δ={pg['delta']:+.1f}, p={pg['p']:.3f}, "
                         f"{pg['wins']}/{pg['n']}]" if pg else "  [n<3]"))
                print(f"          granular recovery (dumb: gran−coarse)   = "
                      f"{rec:+.1f}"
                      + (f"  [paired Δ={pr['delta']:+.1f}, p={pr['p']:.3f}, "
                         f"{pr['wins']}/{pr['n']}]" if pr else "  [n<3]"))
                print(f"          → gap-recovery = {pct:+.0f}%  "
                      f"(P26a threshold ≥50%: "
                      f"{'MET' if pct >= 50 else 'NOT met'})")
                print(f"    P26b  help_dumb={help_dumb:+.1f}  "
                      f"help_smart={help_smart:+.1f}  "
                      f"INTERACTION (help_dumb−help_smart) = {interaction:+.1f}"
                      + (f"  [smart Δ={ps['delta']:+.1f}, p={ps['p']:.3f}]"
                         if ps else ""))
                print(f"          → granularity helps {'DUMB more' if interaction > 0 else 'SMART more/equal'} "
                      f"(substitutes if >0)")
                # KILL evaluation (only meaningful on the full-2×2 primary cell).
                # The registered KILL is DIRECTIONAL — "help nobody, or only smart
                # fleets." Judge on the point-estimate direction; report the paired
                # significance / win-rate SEPARATELY as a robustness annotation, so a
                # noisy but right-signed result is not mislabeled a KILL (and vice
                # versa). Report, not verdict — read both lines together.
                if a == "snhp+net" and N == 24 and H == 2500:
                    if help_dumb <= 0 and help_smart <= 0:
                        verdict = ("KILL FIRES (direction) — granular rights help "
                                   "NOBODY; institutions do not substitute here.")
                    elif interaction <= 0:
                        verdict = ("KILL FIRES (direction) — granularity helps SMART "
                                   "≥ dumb; institutions COMPLEMENT, not substitute.")
                    else:
                        verdict = ("KILL DOES NOT FIRE (direction) — granular rights "
                                   f"recover {pct:+.0f}% of the dumbing gap and help "
                                   "DUMB fleets more than smart (substitute).")
                    robust = "ROBUST" if (pr and pr['p'] < 0.05
                                          and pr['wins'] > pr['n'] // 2) else \
                        "NOT robust (noisy point estimate)"
                    print(f"    KILL[{a},N=24,H=2500]: {verdict}")
                    print(f"      robustness: recovery {robust} — "
                          + (f"paired p={pr['p']:.3f}, {pr['wins']}/{pr['n']} seeds; "
                             if pr else "")
                          + (f"underlying dumbing gap itself p={pg['p']:.3f}"
                             if pg else ""))

    print("\n[horizon spot-check] delivered trajectory at 7,500 ticks (N=24, "
          "snhp+net) vs the 2,500-tick primary — does claims-coordination amortize late?")
    for a in ("snhp+net",):
        for d, g, lab in ((False, False, "smart+coarse"),
                          (True, False, "dumb+coarse"),
                          (True, True, "dumb+gran")):
            c25 = cell(a, d, g, 24, 2500)
            c75 = cell(a, d, g, 24, 7500)
            if c25 or c75:
                print(f"    {lab:>13}: 2500t deliv={mean(c25, 'delivered'):>7.1f} "
                      f"(n={len(c25)})   7500t deliv={mean(c75, 'delivered'):>7.1f} "
                      f"(n={len(c75)})")
def pz_report(rows: list[dict]) -> None:
    """v27 (column Z) — FORGERY: THE RECEIPT UNDER ATTACK. Report, not verdict.
    The honest-advantage surface (honest − liar mean credit; ↑ ⇒ the trusted tier
    is healthy) over the c_f × c_v cost grid, in both verification regimes; the
    mandated−endogenous gap (PZb, the public-good under-provision); the endogenous
    verification/catch rate; the U reputation comparison (PZc); and the KILL. No-op
    unless the sweep carries forgery rows."""
    zr = [r for r in rows if r.get("forgery") is not None
          and (r.get("forgery") or r.get("verify_regime") == "none"
               or r.get("arm", "").startswith("trust"))]
    fr = [r for r in rows if r.get("forgery")]
    if not fr:
        return

    def hadv(g):
        v = [r["honest_adv"] for r in g if r.get("honest_adv") is not None]
        return (float(np.mean(v)), float(np.std(v)), len(v)) if v else (float("nan"), 0.0, 0)

    def ratio(g, num, den):
        n = sum(r.get(num, 0) for r in g)
        d = sum(r.get(den, 0) for r in g)
        return (n / d) if d else float("nan")

    def imean(g, f):
        v = [r.get(f) for r in g if r.get(f) is not None]
        return float(np.mean(v)) if v else float("nan")

    N24 = [r for r in rows if int(r.get("n_robots", 24)) == 24]
    CF, CV = (0.0, 0.5, 2.0, 8.0), (0.25, 1.0, 4.0)

    def cell(rowset, regime, cf, cv):
        return [r for r in rowset if r.get("forgery") and r.get("verify_regime") == regime
                and abs(float(r.get("forge_cost", -9)) - cf) < 1e-9
                and abs(float(r.get("verify_cost", -9)) - cv) < 1e-9]

    def ref(rowset, arm, forgery, reputation):
        return [r for r in rowset if r.get("arm", "").startswith(arm)
                and bool(r.get("forgery")) == forgery
                and bool(r.get("reputation")) == reputation]

    print("\n" + "=" * 100)
    print("PZ (column Z) — FORGERY: THE RECEIPT UNDER ATTACK  (report, not verdict)")
    print("  liar_frac=0.25, σ=0.5, τ=0.15, v5, N=24 · honest advantage = honest − "
          "liar mean credit (↑ ⇒ tier healthy)")
    print("  cost grid (energy): c_f ∈ {0, 0.5, 2, 8} × c_v ∈ {0.25, 1, 4} · deterministic "
          "always-forge · verify prices battery at EV_INIT")
    print("=" * 100)

    g_clean = ref(N24, "trust-gated", False, False)
    g_open = ref(N24, "trust-open", False, False)
    g_rep = ref(N24, "trust-open", False, True)
    print("\n[references, N=24]")
    for lbl, g in (("gated · receipt UNFORGEABLE (healthy tier)", g_clean),
                   ("ungated cooperation (v6 feeding-frenzy floor)", g_open),
                   ("reputation-only  (U regime, no attestation)", g_rep)):
        m, s, n = hadv(g)
        print(f"   {lbl:<46}  honest_adv = {m:>+8.1f} ± {s:>5.1f}  (n={n})")
    frenzy = hadv(g_open)[0]
    healthy = hadv(g_clean)[0]
    rep = hadv(g_rep)[0]

    print("\n[the cliff map] honest advantage by regime · rows c_f, cols c_v  "
          "(feeding-frenzy floor ≈ %+.0f, healthy tier ≈ %+.0f)" % (frenzy, healthy))
    # no-verification collapse (c_f only)
    print("\n   NO VERIFICATION (forgery on, verify off) — by c_f:")
    hdr = "     c_f:  " + "".join(f"{cf:>10}" for cf in CF)
    print(hdr)
    line = "     hadv:" + "".join(
        f"{hadv(cell(N24, 'none', cf, 0.0))[0]:>10.1f}" for cf in CF)
    print(line)
    for regime in ("mandated", "endogenous"):
        print(f"\n   {regime.upper()}:   honest advantage   (c_v →)")
        print("     c_f\\c_v " + "".join(f"{cv:>9}" for cv in CV))
        for cf in CF:
            cells = [hadv(cell(N24, regime, cf, cv))[0] for cv in CV]
            print(f"     {cf:>6}  " + "".join(f"{c:>9.1f}" for c in cells))

    print("\n[PZb — the public-good gap] MANDATED − ENDOGENOUS honest advantage  "
          "(>0 ⇒ endogenous under-provides ⇒ closer to collapse)")
    print("     c_f\\c_v " + "".join(f"{cv:>9}" for cv in CV))
    for cf in CF:
        gaps = []
        for cv in CV:
            gaps.append(hadv(cell(N24, "mandated", cf, cv))[0]
                        - hadv(cell(N24, "endogenous", cf, cv))[0])
        print(f"     {cf:>6}  " + "".join(f"{g:>+9.1f}" for g in gaps))

    print("\n[endogenous verification] catch rate (caught/attempts) · verify acts/run · "
          "slip/run · strip/run")
    print("     c_f\\c_v " + "".join(f"{cv:>19}" for cv in CV))
    for cf in CF:
        parts = []
        for cv in CV:
            g = cell(N24, "endogenous", cf, cv)
            cr = ratio(g, "forge_caught", "forge_attempts")
            va = imean(g, "verify_acts")
            sl = imean(g, "forge_slipped")
            st = imean(g, "strip_deals")
            parts.append(f"{cr:>5.2f}/{va:>4.0f}/{sl:>4.0f}/{st:>3.0f}")
        print(f"     {cf:>6}  " + "".join(f"{p:>19}" for p in parts))

    print("\n[PZc — degrade vs the U reputation baseline] honest advantage, matched liars "
          "(reputation ≈ %+.1f, cell-invariant)" % rep)
    print("     regime      c_f   c_v    gated+verify   reputation    Δ(receipts−reput)")
    for regime in ("mandated", "endogenous"):
        for cf, cv in ((0.0, 0.25), (2.0, 1.0), (0.0, 4.0)):
            m = hadv(cell(N24, regime, cf, cv))[0]
            print(f"     {regime:<11} {cf:>4} {cv:>5}   {m:>+10.1f}   {rep:>+10.1f}"
                  f"    {m - rep:>+10.1f}")

    # N=96 scale check
    N96 = [r for r in rows if int(r.get("n_robots", 24)) == 96 and r.get("forgery")]
    if N96:
        print("\n[N=96 scale check] honest advantage on near-cliff cells (8 seeds)")
        print("     regime      c_f   c_v      hadv(N=96)")
        for regime in ("mandated", "endogenous"):
            for cf, cv in ((0.0, 4.0), (2.0, 1.0), (2.0, 4.0)):
                g = [r for r in N96 if r.get("verify_regime") == regime
                     and abs(float(r.get("forge_cost")) - cf) < 1e-9
                     and abs(float(r.get("verify_cost")) - cv) < 1e-9]
                m, s, n = hadv(g)
                if n:
                    print(f"     {regime:<11} {cf:>4} {cv:>5}   {m:>+10.1f} ± {s:>4.1f}")

    # ── KILL evaluation ──────────────────────────────────────────────────────
    # A threshold EXISTS iff some cells hold near the healthy tier while others
    # collapse toward the frenzy floor — i.e. the honest advantage is neither
    # robustly healthy everywhere nor collapsed everywhere across the grid.
    allcells = []
    for regime in ("mandated", "endogenous", "none"):
        cvs = CV if regime != "none" else (0.0,)
        for cf in CF:
            for cv in cvs:
                m, _, n = hadv(cell(N24, regime, cf, cv))
                if n:
                    allcells.append((regime, cf, cv, m))
    span = frenzy if frenzy == frenzy else -100.0
    # "held" = within a third of the way from frenzy to healthy of the healthy end;
    # "collapsed" = within a third of the frenzy end. Thresholds off the two anchors.
    lo, hi = span, healthy
    held = [c for c in allcells if c[3] > lo + 0.66 * (hi - lo)]
    collapsed = [c for c in allcells if c[3] < lo + 0.33 * (hi - lo)]
    print("\n[KILL] anchors: frenzy floor %+.1f · healthy tier %+.1f" % (frenzy, healthy))
    print(f"   cells holding near-healthy: {len(held)}/{len(allcells)} · "
          f"cells collapsed near-frenzy: {len(collapsed)}/{len(allcells)}")
    if held and collapsed:
        print("   → KILL DOES NOT FIRE: a THRESHOLD exists — the tier's honest advantage "
              "inverts across the c_f/c_v grid (some cells hold, some collapse). The "
              "unforgeable-receipt assumption is load-bearing: forgery economics decide "
              "the tier.")
    elif not collapsed:
        print("   → KILL FIRES (robust everywhere): no cell collapses — forgery never "
              "dissolves the gated tier in this world; the unforgeable-receipt assumption "
              "is trivially safe here.")
    else:
        print("   → KILL FIRES (dead everywhere): every cell collapses — verification "
              "never rescues the tier; the gate was already decorative under attack.")
    # forgery-at-c_f=0 diagnostic (the walk-away-immunity check)
    m0, _, n0 = hadv(cell(N24, "none", 0.0, 0.0))
    if n0:
        print(f"   forgery at c_f=0 (no verification): honest_adv {m0:>+.1f} vs healthy "
              f"{healthy:+.1f} — forgery {'PAYS (tier collapses)' if m0 < healthy - 10 else 'does NOT pay'} "
              f"even free; the TIER (no walk-away veto) is the target, as registered.")


def pab_report(rows: list[dict]) -> None:
    """v29 (column AB) — the crash: contagion in the counterparty web. Printed
    numbers ARE the artifact (report, not verdict). No-op unless the sweep carries a
    shock run. Six cells pair off the same bills+mortality(claims-die) config:
      snhp+bill+die+shk       GROSS BILATERAL, shock       (each claim eats its own)
      snhp+bill+die           GROSS, no-shock control      (== the v28 claims-die run)
      snhp+bill+die+ccp+shk   CLEARINGHOUSE, shock         (CCP guarantees at face)
      snhp+bill+die+ccp       CLEARINGHOUSE, no-shock       (fees build, no payouts)
      snhp+net+mort+shk       SPOT (paperless), shock       (no claim web to spread)
      snhp+net+mort           SPOT, no-shock control
    T_shock is registered in shock_detail; pre-shock the shock and control runs are
    bit-identical, so the SCAR (post- minus pre-shock chain rate, differenced against
    the control) isolates the shock. Reads shock_detail (histogram/CCP) and
    mortality_detail (the per-window scar series)."""
    srows = [r for r in rows if r.get("shock_detail")]
    if not srows:
        return
    GS, GC = "snhp+bill+die+shk", "snhp+bill+die"
    CS, CC = "snhp+bill+die+ccp+shk", "snhp+bill+die+ccp"
    SS, SC = "snhp+net+mort+shk", "snhp+net+mort"
    lab = {GS: "gross+shk", GC: "gross(ctl)", CS: "ccp+shk", CC: "ccp(ctl)",
           SS: "spot+shk", SC: "spot(ctl)"}
    Ns = sorted({int(r["n_robots"]) for r in srows})
    HOPCAP = 6

    def sel(arm, N):
        return [r for r in rows if r["arm"] == arm and int(r["n_robots"]) == N]

    def sd(r):
        return r.get("shock_detail") or {}

    def md(r):
        return r.get("mortality_detail") or {}

    d0 = sd(srows[0])
    print("\n" + "=" * 94)
    print("PAB (v29 · column AB) — THE CRASH: CONTAGION IN THE COUNTERPARTY WEB "
          "(report, not verdict)")
    print(f"T_shock={d0['shock_tick']} (registered, identical across regimes/seeds); "
          f"far band = rocks beyond the p{d0['far_pctl']} nearest-refinery distance "
          f"(farthest ~40%),")
    print(f"value floor={d0['value_floor']:g} (ore zeros out), CCP fee={d0['ccp_fee']:g} "
          f"of face per settlement. Φ never sees the shock — write-downs land only at "
          f"settlement/death.")
    print("=" * 94)

    # [1] the shock's footprint + physical damage (deaths/strands post-shock vs ctl)
    print("\n[1] SHOCK FOOTPRINT — far-band size, delivered, total value written down, "
          "deaths/strands POST-shock (vs no-shock control):")
    h = (f"  {'cell':<11} {'N':>4} {'far':>4} {'farLost':>7} {'deliv':>6} "
         f"{'writedn$':>9} {'deaths':>7} {'dPost':>6} {'strPost':>7}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in (GS, GC, CS, CC, SS, SC):
            g = sel(arm, N)
            if not g:
                continue
            s = [sd(r) for r in g]
            far = np.mean([x.get("n_far", 0) for x in s])
            fl = np.mean([x.get("far_stock_lost", 0) for x in s])
            dv = np.mean([r["delivered"] for r in g])
            wdn = np.mean([x.get("shock_writedown", 0) for x in s])
            dth = np.mean([r["deaths"] or 0 for r in g])   # top-level (all cells)
            dp = np.mean([x.get("deaths_post", 0) for x in s])
            sp = np.mean([x.get("strands_post", 0) for x in s])
            print(f"  {lab[arm]:<11} {N:>4} {far:>4.0f} {fl:>7.0f} {dv:>6.0f} "
                  f"{wdn:>9.0f} {dth:>7.1f} {dp:>6.1f} {sp:>7.1f}")

    def snap_hop(r):
        """Far-band leverage $ by hop, snapshotted AT the crash (the in-transit claim
        stacks referencing a settlement that cannot complete). The robust PABa reach
        measure — the realized settlement/death write-downs are the materialized
        subset (many chains later deliver-at-0, void on a claimant's death, or
        deadlock, so realized under-counts the reach)."""
        return sd(r).get("exp_snap_by_hop", [0.0] * (HOPCAP + 1))

    # [2] PABa — the CONTAGION-DEPTH HISTOGRAM: in-flight far-band leverage $ by hop up
    # the web, snapshotted AT the crash (per-cell, per-seed mean).
    print("\n[2] PABa CONTAGION-DEPTH HISTOGRAM — in-flight far-band leverage EXPOSURE $ "
          "by hop up the counterparty web, snapshotted AT the crash (per-seed mean).")
    print("     hop 0 = DIRECT victim (holds the dark ore); hop ≥1 = CONTAGION up the "
          "web (paper-claimants, depth == chain length). h6 folds all hops ≥6.")
    hd = "  {:<11} {:>4} " + " ".join(f"{'h'+str(k):>8}" for k in range(HOPCAP + 1))
    hdr = hd.format("cell", "N")
    print(hdr + "\n  " + "-" * (len(hdr) - 2))
    for N in Ns:
        for arm in (GS, CS, SS):
            g = sel(arm, N)
            if not g:
                continue
            tot = np.mean([snap_hop(r) for r in g], axis=0)
            cells = " ".join(f"{v:>8.0f}" for v in tot)
            print(f"  {lab[arm]:<11} {N:>4} {cells}")

    # [3] PABa split — direct (hop 0) vs contagion (hop ≥1), the ≥2-hop share, the
    # deepest hop; plus what MATERIALIZED as realized write-downs at settlement/death.
    print("\n[3] PABa DIRECT vs CONTAGION — does the loss escape the direct victims "
          "(hop ≥1)?  ≥2-hop reach IS the systemic-risk signal. [snap]=in-flight "
          "leverage at the crash, [real]=materialized at settlement/death.")
    h = (f"  {'cell':<11} {'N':>4} {'direct$':>9} {'contag$':>9} {'contag%':>8} "
         f"{'≥2hop$':>8} {'maxhop':>7} {'realCon$':>9}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in (GS, CS, SS):
            g = sel(arm, N)
            if not g:
                continue
            fh = [snap_hop(r) for r in g]
            d0 = np.mean([x[0] for x in fh])
            c1 = np.mean([sum(x[1:]) for x in fh])
            ge2 = np.mean([sum(x[2:]) for x in fh])
            frac = c1 / (d0 + c1) if (d0 + c1) > 0 else 0.0
            mh = np.mean([sd(r).get("exp_snap_maxhop", -1) for r in g])
            rcon = np.mean([sd(r).get("wd_contagion_exp", 0) for r in g])
            print(f"  {lab[arm]:<11} {N:>4} {d0:>9.0f} {c1:>9.0f} {frac:>7.1%} "
                  f"{ge2:>8.0f} {mh:>7.1f} {rcon:>9.0f}")

    # [4] PABb — the CLEARINGHOUSE caps contagion (realized loss) at a fee cost
    print("\n[4] PABb CLEARINGHOUSE CAP — REALIZED write-down (what claimants actually "
          "eat) gross vs CCP, plus the CCP's fee income / payouts / haircut / pool:")
    h = (f"  {'cell':<11} {'N':>4} {'realized$':>10} {'exposure$':>10} "
         f"{'fees':>7} {'payout':>7} {'haircut':>8} {'poolEnd':>8}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in (GS, CS):
            g = sel(arm, N)
            if not g:
                continue
            real = np.mean([sd(r).get("wd_direct_real", 0)
                            + sd(r).get("wd_contagion_real", 0) for r in g])
            exp = np.mean([sd(r).get("wd_direct_exp", 0)
                           + sd(r).get("wd_contagion_exp", 0) for r in g])
            fee = np.mean([sd(r).get("ccp_fees", 0) for r in g])
            pay = np.mean([sd(r).get("ccp_payouts", 0) for r in g])
            hair = np.mean([sd(r).get("ccp_haircut", 0) for r in g])
            pool = np.mean([sd(r).get("ccp_pool_final", 0) for r in g])
            print(f"  {lab[arm]:<11} {N:>4} {real:>10.0f} {exp:>10.0f} {fee:>7.0f} "
                  f"{pay:>7.0f} {hair:>8.0f} {pool:>8.0f}")
    # the CCP fee-pool trajectory (pre-shock build, post-shock drawdown), one cell
    for N in Ns:
        g = sel(CS, N)
        if g and sd(g[0]).get("ccp_pool_traj"):
            traj = np.mean([sd(r)["ccp_pool_traj"] for r in g
                            if len(sd(r).get("ccp_pool_traj", [])) ==
                            len(sd(g[0])["ccp_pool_traj"])], axis=0)
            win = sd(g[0]).get("window", 250)
            tsh = sd(g[0]).get("shock_tick", -1)
            samp = [f"t{(i+1)*win}:{v:.0f}" for i, v in enumerate(traj)
                    if (i + 1) * win % (win * 3) == 0][:12]
            print(f"    CCP pool traj N={N} (shock@{tsh}): " + "  ".join(samp))

    # [5] PABc — the SCAR: chain-formation rate pre vs post shock, shock vs control
    print("\n[5] PABc THE SCAR — chain-deal rate (cargo deals / tick) by window, "
          "shock vs no-shock control. Pre-shock the two are bit-identical.")
    for N in Ns:
        for stag, sarm, carm in (("GROSS", GS, GC), ("CCP", CS, CC),
                                  ("SPOT", SS, SC)):
            gs, gc = sel(sarm, N), sel(carm, N)
            if not gs or not gc:
                continue
            win = md(gs[0]).get("window", 250)
            tsh = sd(gs[0]).get("shock_tick", -1)
            pw = tsh // win if tsh >= 0 else 0

            def rate(rowset, w0, w1):
                vals = []
                for r in rowset:
                    cw = md(r).get("chain_by_window", [])
                    seg = cw[w0:w1]
                    if seg:
                        vals.append(sum(seg) / (len(seg) * win))
                return float(np.mean(vals)) if vals else 0.0

            nmin = min(len(md(r).get("chain_by_window", [])) for r in gs + gc)
            pre_s = rate(gs, 0, pw)
            post_s = rate(gs, pw, min(pw + 4, nmin))     # ~1000 ticks after shock
            post_c = rate(gc, pw, min(pw + 4, nmin))
            deficit = (post_c - post_s) / post_c if post_c > 1e-9 else 0.0
            # recovery: first post window where shock rate >= control rate again
            rec = None
            for wk in range(pw, nmin):
                rs = rate(gs, wk, wk + 1)
                rc = rate(gc, wk, wk + 1)
                if wk > pw and rs >= rc - 1e-9:
                    rec = (wk - pw) * win
                    break
            recs = f"{rec}t" if rec is not None else ">horizon"
            print(f"    N={N:>3} {stag:<6} pre={pre_s:.3f} post-shock={post_s:.3f} "
                  f"post-ctl={post_c:.3f}  scar={deficit:+.0%} of ctl  recovery≈{recs}")

    # [6] the leverage question — does the shock hurt the PAPERLESS economy less?
    print("\n[6] THE LEVERAGE QUESTION — spot (no claim web) vs bills. Same far ore "
          "darkens; does PAPER spread the loss to more agents / deeper hops? (at-shock "
          "in-flight exposure snapshot).")
    h = (f"  {'cell':<11} {'N':>4} {'total$':>8} {'hop0$':>8} "
         f"{'≥1hop$':>8} {'≥1hop%':>7} {'maxhop':>7}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in (GS, CS, SS):
            g = sel(arm, N)
            if not g:
                continue
            fh = [snap_hop(r) for r in g]
            c0 = np.mean([x[0] for x in fh])
            c1 = np.mean([sum(x[1:]) for x in fh])
            f1 = c1 / (c0 + c1) if (c0 + c1) > 0 else 0.0
            mh = np.mean([sd(r).get("exp_snap_maxhop", -1) for r in g])
            print(f"  {lab[arm]:<11} {N:>4} {c0+c1:>8.0f} {c0:>8.0f} "
                  f"{c1:>8.0f} {f1:>6.1%} {mh:>7.1f}")
    print("    Read: spot concentrates the loss on hop-0 holders (no claim web ⇒ ≥1hop "
          "≈ 0); bills SPREAD the identical ore-loss up the web — that spread IS the "
          "leverage / systemic risk.")


def pab2_report(rows: list[dict]) -> None:
    """v32 (column AB2) — the crash with teeth: claim-collateralized debt. Printed
    numbers ARE the artifact (report, not verdict). No-op unless the sweep carries a
    debt run. The AB crash economy (bills+claims-die mortality, far band dark at
    T_shock) PLUS borrowing against claims. Grid: LTV {0,0.5,0.8} × {gross,
    clearinghouse} × {shock, no-shock control}. LTV 0 ≡ AB as run (the baseline where
    post-shock deaths FELL). Reads debt_detail (take-up / treasury / garnishment),
    shock_detail (deaths/strands post-shock) and lineage_detail (far-band d/m)."""
    if not any(r.get("debt_detail") is not None for r in rows):
        return
    LTVS = (0.0, 0.5, 0.8)
    Ns = sorted({int(r["n_robots"]) for r in rows if r.get("debt_ltv", 0.0) > 0.0}
                | {int(r["n_robots"]) for r in rows
                   if r.get("debt_detail") is not None})

    def lbl(ltv, ccp, shock):
        s = "snhp+bill+die"
        if ccp:
            s += "+ccp"
        if shock:
            s += "+shk"
        if ltv > 0:
            s += f"+ltv{ltv:g}"
        return s

    def sel(ltv, ccp, shock, N):
        arm = lbl(ltv, ccp, shock)
        return [r for r in rows if r["arm"] == arm and int(r["n_robots"]) == N]

    def byseed(g, f):
        return {r["seed"]: f(r) for r in g}

    def paired(gh, gl, f):
        hi, lo = byseed(gh, f), byseed(gl, f)
        common = sorted(set(hi) & set(lo))
        if len(common) < 2:
            return (float("nan"), float("nan"), 0, len(common))
        a = [hi[s] for s in common]
        b = [lo[s] for s in common]
        d = float(np.mean([x - y for x, y in zip(a, b)]))
        try:
            _, p = stats.ttest_rel(a, b)
        except Exception:
            p = float("nan")
        wins = sum(1 for x, y in zip(a, b) if x > y)
        return (d, float(p), wins, len(common))

    def dd(r):
        return r.get("debt_detail") or {}

    def sd(r):
        return r.get("shock_detail") or {}

    def far_dm(g):
        gg = [r for r in g if r.get("lineage_detail")]
        if not gg:
            return 0.0
        bm = np.array([r["lineage_detail"]["band_mined"] for r in gg], float).sum(axis=0)
        bd = np.array([r["lineage_detail"]["band_delivered"] for r in gg], float).sum(axis=0)
        return bd[2] / bm[2] if bm[2] > 0 else 0.0

    print("\n" + "=" * 96)
    print("PAB2 (v32 · column AB2) — THE CRASH WITH TEETH: CLAIM-COLLATERALIZED DEBT "
          "(report, not verdict)")
    ex = next(r for r in rows if r.get("debt_detail") is not None)
    d0 = dd(ex)
    print(f"Borrow against claims up to LTV × face value; loan energy priced at "
          f"{d0['energy_price']:g}/unit (the neutral shadow price); settlement repays "
          f"debt FIRST;")
    print(f"underwater (debt>collateral) ⇒ GARNISHMENT (no new borrowing, all income "
          f"services debt). Grid LTV {{0,0.5,0.8}} × {{gross,ccp}} × {{shock,ctl}}; "
          f"LTV 0 ≡ AB as run.")
    print("=" * 96)

    # [1] PRE-FLIGHT / TAKE-UP — does the loan get taken, and does it fund FAR work?
    print("\n[1] TAKE-UP (the pre-flight) — borrowers/run, energy borrowed & its share of "
          "energy drawn, far-borrow share, on the NO-SHOCK controls:")
    h = (f"  {'cell':<16} {'N':>4} {'borrows':>7} {'ers/run':>7} {'Ebor':>7} "
         f"{'Ebor%draw':>9} {'far%':>6} {'meanDref':>8} {'farThr':>6}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for ltv in (0.5, 0.8):
            for ccp in (False, True):
                g = sel(ltv, ccp, False, N)
                if not g:
                    continue
                s = [dd(r) for r in g]
                nb = np.mean([x["n_borrow_events"] for x in s])
                ers = np.mean([x["n_borrowers"] for x in s])
                eb = np.mean([x["energy_borrowed"] for x in s])
                ed = np.mean([x["energy_drawn"] for x in s])
                fs = np.mean([x["far_borrow_share"] for x in s])
                dr = np.mean([x["mean_borrow_dref"] for x in s])
                ft = s[0]["far_thr"]
                tag = "gross" if not ccp else "ccp"
                print(f"  ltv{ltv:g}+{tag:<10} {N:>4} {nb:>7.0f} {ers:>7.1f} {eb:>7.0f} "
                      f"{eb / ed if ed else 0:>8.1%} {fs:>6.1%} {dr:>8.1f} {ft:>6.1f}")
    print("    (far% = borrows struck beyond the far-band threshold; a debt column nobody "
          "borrows in — or that funds only near work — is vacuous.)")

    # [2] PAB2-pre — does borrowing raise far-band delivered? (no-shock controls, gross)
    print("\n[2] PAB2-pre — far-band delivered/mined & delivered_frac WITH vs WITHOUT debt "
          "(no-shock, gross bilateral): is the bait real?")
    h = f"  {'N':>4} {'LTV':>5} {'far d/m':>8} {'dFrac':>7} {'deaths':>7} {'strand':>7}"
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for ltv in LTVS:
            g = sel(ltv, False, False, N)
            if not g:
                continue
            fdm = far_dm(g)
            df = np.mean([r["delivered_frac"] for r in g])
            dth = np.mean([r["deaths"] or 0 for r in g])
            st = np.mean([r["stranded"] for r in g])
            print(f"  {N:>4} {ltv:>5g} {fdm:>8.3f} {df:>7.3f} {dth:>7.1f} {st:>7.1f}")

    # [3] DEATHS / STRANDING — the crux: does the crash now cross into physics?
    print("\n[3] DEATHS/STRANDING — LTV × regime × shock/control. PAB2a: do post-shock "
          "deaths RISE with LTV (vs the AB LTV-0 baseline where they FELL)?")
    h = (f"  {'cell':<20} {'N':>4} {'deaths':>7} {'dPost':>6} {'strPost':>7} "
         f"{'dFrac':>7} {'Δdeath(shk−ctl)':>16}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for ccp in (False, True):
            for ltv in LTVS:
                gs = sel(ltv, ccp, True, N)
                gc = sel(ltv, ccp, False, N)
                if not gs:
                    continue
                dth = np.mean([r["deaths"] or 0 for r in gs])
                dp = np.mean([sd(r).get("deaths_post", 0) for r in gs])
                sp = np.mean([sd(r).get("strands_post", 0) for r in gs])
                df = np.mean([r["delivered_frac"] for r in gs])
                dd_, dp_, dw, dn = paired(gs, gc, lambda r: (r["deaths"] or 0))
                tag = "gross" if not ccp else "ccp"
                print(f"  ltv{ltv:g}+{tag:<15} {N:>4} {dth:>7.1f} {dp:>6.1f} {sp:>7.1f} "
                      f"{df:>7.3f} {dd_:>+9.2f} p={dp_:>4.2f} {dw}/{dn}")

    # [4] KILL — do post-shock deaths rise at ANY LTV vs the LTV-0 (AB) baseline?
    print("\n[4] KILL CHECK (PAB2a/KILL) — post-shock deaths at LTV>0 vs the LTV-0 AB "
          "baseline (paired, shock cells). KILL FIRES if deaths do NOT rise at any LTV.")
    h = f"  {'contrast':<28} {'N':>4} {'Δdeaths':>9} {'p':>6} {'wins':>7}"
    print(h + "\n  " + "-" * (len(h) - 2))
    any_rise = False
    for N in Ns:
        for ccp in (False, True):
            g0 = sel(0.0, ccp, True, N)
            for ltv in (0.5, 0.8):
                gl = sel(ltv, ccp, True, N)
                if not gl or not g0:
                    continue
                d, p, w, n = paired(gl, g0, lambda r: (r["deaths"] or 0))
                tag = "gross" if not ccp else "ccp"
                rise = (d > 0 and p < 0.10)
                any_rise = any_rise or rise
                flag = "  <-- RISE" if rise else ""
                print(f"  ltv{ltv:g}−ltv0 ({tag}){'':<10} {N:>4} {d:>+9.2f} {p:>6.2f} "
                      f"{w}/{n}{flag}")
    print(f"    KILL STATUS: {'DOES NOT FIRE — deaths RISE at some LTV (debt has teeth)' if any_rise else 'FIRES — deaths do NOT rise at any LTV (no bankruptcy even with debt)'}")

    # [5] GARNISHMENT — the distress state and its body count (PAB2b/c)
    print("\n[5] GARNISHMENT — episodes, mean duration (ticks), share ≥1 hop from the "
          "shock, deaths among the ever-garnished (PAB2b: contagion gains a body count):")
    h = (f"  {'cell':<20} {'N':>4} {'garn':>5} {'far≥1':>6} {'meanDur':>8} "
         f"{'gDead':>6} {'deaths':>7}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for ccp in (False, True):
            for ltv in (0.5, 0.8):
                for shk in (True, False):
                    g = sel(ltv, ccp, shk, N)
                    if not g:
                        continue
                    s = [dd(r) for r in g]
                    ng = np.mean([x["n_garnish"] for x in s])
                    ngf = np.mean([x["n_garnish_far"] for x in s])
                    md_ = np.mean([x["garnish_mean_dur"] for x in s])
                    gdd = np.mean([x["deaths_garnished"] for x in s])
                    dth = np.mean([r["deaths"] or 0 for r in g])
                    tag = ("ccp" if ccp else "gross") + ("+shk" if shk else "+ctl")
                    print(f"  ltv{ltv:g}+{tag:<14} {N:>4} {ng:>5.1f} {ngf:>6.1f} "
                          f"{md_:>8.0f} {gdd:>6.1f} {dth:>7.1f}")

    # [6] TREASURY WATERFALL — loaned / repaid / written-off / outstanding (must balance)
    print("\n[6] TREASURY WATERFALL — loaned = repaid + written_off + outstanding "
          "(the ledger closes). PAB2c: does the CCP / LTV cap bound the write-off?")
    h = (f"  {'cell':<20} {'N':>4} {'loaned':>8} {'repaid':>8} {'wroff':>7} "
         f"{'outstd':>7} {'balance':>8}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for ccp in (False, True):
            for ltv in (0.5, 0.8):
                for shk in (True, False):
                    g = sel(ltv, ccp, shk, N)
                    if not g:
                        continue
                    s = [dd(r) for r in g]
                    ln = np.mean([x["debt_loaned"] for x in s])
                    rp = np.mean([x["debt_repaid"] for x in s])
                    wo = np.mean([x["debt_written_off"] for x in s])
                    ou = np.mean([x["debt_outstanding"] for x in s])
                    bal = ln - rp - wo - ou
                    tag = ("ccp" if ccp else "gross") + ("+shk" if shk else "+ctl")
                    print(f"  ltv{ltv:g}+{tag:<14} {N:>4} {ln:>8.0f} {rp:>8.0f} "
                          f"{wo:>7.0f} {ou:>7.0f} {bal:>+8.0e}")
    print("=" * 96)


def pm2_report(rows: list[dict]) -> None:
    """v30 (column M2) — the bill becomes money: transferable claims. Printed numbers
    ARE the artifact (report, not verdict). No-op unless the sweep carries a
    claims_transferable run. Three arms pair off the P23 config:
      snhp+net           SPOT (paperless)         — no claim stack at all
      snhp+bill          BILLS-STATIC             — claims exist, never endorsed (PM2b control)
      snhp+bill+xfer     BILLS-TRANSFERABLE       — claim positions ENDORSABLE as payment
    Reads circulation_detail (velocity/maturity) and mx_detail (M(x)/flow) off the
    transferable rows; lineage_detail for the outcome comparison."""
    xf = [r for r in rows if r.get("claims_transferable")]
    if not xf:
        return
    SPOT, STAT, XFER = "snhp+net", "snhp+bill", "snhp+bill+xfer"
    Ns = sorted({int(r["n_robots"]) for r in xf})

    def sel(arm, N, horizon=2500):
        return [r for r in rows if r["arm"] == arm and int(r["n_robots"]) == N
                and int(r.get("ticks_horizon", 2500)) == horizon]

    def _far_dm(g):
        bm = np.array([r["lineage_detail"]["band_mined"] for r in g], float).sum(axis=0)
        bd = np.array([r["lineage_detail"]["band_delivered"] for r in g], float).sum(axis=0)
        return bd[2] / bm[2] if bm[2] > 0 else 0.0

    def _hop2(g):
        return float(np.mean([r["lineage_detail"]["hop_shares"][2] for r in g])) if g else 0.0

    def M(r, x):
        d = r.get("mx_detail") or {}
        mv = (d.get("mv") or {}).get(x, 0)
        return (d["op"][x] / mv) if mv else None

    print("\n" + "=" * 94)
    print("PM2 (v30 · column M2) — THE BILL BECOMES MONEY: TRANSFERABLE CLAIMS "
          "(report, not verdict)")
    print("Endorsement leg CLAIM_OPTS = " + str(CLAIM_OPTS) + " (face credit; a→b>0, b→a<0). "
          "Claims priced UNDISCOUNTED")
    print("(par) — weightless & LOSSLESS vs energy's TRANSFER_LOSS: the physics that lets "
          "paper out-circulate the battery.")
    print("=" * 94)

    # [1] OUTCOMES — spot / static / transferable (PM2b: does spendability lift trade?)
    print("\n[1] OUTCOMES (2,500t) — delivered_frac, far-band delivered/mined, ≥2-hop share, "
          "stranded, deals, multi-issue:")
    h = (f"  {'arm':<16} {'N':>4} {'dFrac':>6} {'far d/m':>8} {'≥2hop':>6} "
         f"{'strand':>6} {'deals':>6} {'multi':>6}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for N in Ns:
        for arm in (SPOT, STAT, XFER):
            g = sel(arm, N)
            if not g:
                continue
            df = np.mean([r["delivered_frac"] for r in g])
            fdm = _far_dm(g) if g[0].get("lineage_detail") else 0.0
            h2 = _hop2(g) if g[0].get("lineage_detail") else 0.0
            st = np.mean([r["stranded"] for r in g])
            dl = np.mean([r["deals"] for r in g])
            mi = np.mean([r["multi_issue_frac"] or 0 for r in g])
            print(f"  {arm:<16} {N:>4} {df:>6.3f} {fdm:>8.3f} {h2:>6.3f} "
                  f"{st:>6.1f} {dl:>6.0f} {mi:>6.3f}")

    # [2] PM2a — VELOCITY: endorsements-before-settlement per claim (KILL reads ≈0)
    print("\n[2] PM2a VELOCITY — endorsements before settlement per claim (transferable arm; "
          "hist over ALL claims, 0=never circulated):")
    h = (f"  {'N':>4} {'horizon':>7} {'vel_mean':>8} {'vel_max':>7} "
         f"{'hist 0/1/2/3/4+':>22} {'early':>6} {'late':>6} {'#endorse':>8}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for hz in (2500, 7500):
        for N in Ns:
            g = sel(XFER, N, hz)
            if not g:
                continue
            cds = [r["circulation_detail"] for r in g]
            vm = np.mean([c["velocity_mean"] for c in cds])
            vx = max(c["velocity_max"] for c in cds)
            hist = np.sum([c["velocity_hist"] for c in cds], axis=0)
            hp = "/".join(str(int(x)) for x in hist)
            ve = np.mean([c["velocity_early"] for c in cds])
            vl = np.mean([c["velocity_late"] for c in cds])
            ne = np.mean([c["n_endorse_deals"] for c in cds])
            print(f"  {N:>4} {hz:>7} {vm:>8.3f} {vx:>7d} {hp:>22} "
                  f"{ve:>6.3f} {vl:>6.3f} {ne:>8.0f}")

    # [3] PM2a — CIRCULATION BY MATURITY (good-collateral): endorsed vs the pool
    print("\n[3] PM2a GOOD-COLLATERAL — mean distance-to-refinery (RISK proxy: near=low-risk) "
          "and hops, ENDORSED claims vs the outstanding POOL:")
    h = (f"  {'N':>4} {'horizon':>7} {'endorsed ref_d':>14} {'pool ref_d':>11} "
         f"{'endorsed hops':>13} {'pool hops':>10}")
    print(h + "\n  " + "-" * (len(h) - 2))
    for hz in (2500, 7500):
        for N in Ns:
            g = sel(XFER, N, hz)
            if not g:
                continue
            cds = [r["circulation_detail"] for r in g]
            ed = np.mean([c["endorsed_ref_d_mean"] for c in cds])
            pd = np.mean([c["pop_ref_d_mean"] for c in cds])
            eh = np.mean([c["endorsed_hops_mean"] for c in cds])
            ph = np.mean([c["pop_hops_mean"] for c in cds])
            print(f"  {N:>4} {hz:>7} {ed:>14.2f} {pd:>11.2f} {eh:>13.2f} {ph:>10.2f}")
    print("    (endorsed ref_d < pool ref_d ⇒ near-mature/low-risk circulate "
          "preferentially; ≈ ⇒ maturity-blind, as par-valuation predicts)")

    # [4] PM2c — M(x): the money test. M(claims) vs M(energy) paired across seeds.
    print("\n[4] PM2c THE MONEY TEST — medium-of-exchange index M(x)=P(x on the opposite side "
          "of a bundle), transferable arm:")
    h = f"  {'N':>4} {'horizon':>7} {'M(cargo)':>9} {'M(energy)':>10} {'M(claims)':>10} {'PM2c: M(claims)>M(energy)':>26}"
    print(h + "\n  " + "-" * (len(h) - 2))
    for hz in (2500, 7500):
        for N in Ns:
            g = sel(XFER, N, hz)
            if not g:
                continue
            mc = [M(r, "cargo") for r in g if M(r, "cargo") is not None]
            me = [M(r, "energy") for r in g if M(r, "energy") is not None]
            mk = [M(r, "claims") for r in g if M(r, "claims") is not None]
            # paired M(claims)-M(energy) over seeds where both exist
            pair = [(M(r, "claims"), M(r, "energy")) for r in g
                    if M(r, "claims") is not None and M(r, "energy") is not None]
            sig = "n/a"
            if len(pair) >= 3:
                ck = [p[0] for p in pair]; ce = [p[1] for p in pair]
                d = np.array(ck) - np.array(ce)
                if np.any(d != 0):
                    try:
                        _, pw = stats.wilcoxon(d)
                    except Exception:
                        pw = float("nan")
                    wins = int(np.sum(d > 0))
                    sig = f"Δ={np.mean(d):+.3f} p={pw:.3f} {wins}/{len(pair)}"
                else:
                    sig = "Δ=0"
            print(f"  {N:>4} {hz:>7} {np.mean(mc):>9.3f} {np.mean(me):>10.3f} "
                  f"{np.mean(mk):>10.3f} {sig:>26}")
    # reference: M(energy) on the paperless/static arms (no claims to compete)
    for N in Ns:
        for arm, tag in ((SPOT, "spot"), (STAT, "static")):
            g = sel(arm, N)
            me = [M(r, "energy") for r in g if M(r, "energy") is not None]
            if me:
                print(f"    ref M(energy) {tag:<7} N={N}: {np.mean(me):.3f} "
                      f"(no claim rival)")

    # [5] M(x) TRAJECTORY — pooled window M(x) over the run (Menger convergence)
    print("\n[5] M(x) TRAJECTORY — pooled per-500t-window M(x), transferable arm "
          "(does M(claims) rise/hold as paper accumulates?):")
    for N in Ns:
        for hz in (2500, 7500):
            g = sel(XFER, N, hz)
            if not g:
                continue
            # pool window counts across seeds
            acc = {}
            for r in g:
                for w_ in (r.get("mx_detail") or {}).get("windows", []):
                    a = acc.setdefault(w_["t0"], {"mv": {}, "op": {}})
                    for x in ("cargo", "energy", "claims"):
                        a["mv"][x] = a["mv"].get(x, 0) + w_["mv"][x]
                        a["op"][x] = a["op"].get(x, 0) + w_["op"][x]
            if not acc:
                continue
            print(f"  N={N} horizon={hz}:  " + "  ".join(
                f"t{t0}:[c{(a['op']['cargo']/a['mv']['cargo'] if a['mv']['cargo'] else 0):.2f} "
                f"e{(a['op']['energy']/a['mv']['energy'] if a['mv']['energy'] else 0):.2f} "
                f"k{(a['op']['claims']/a['mv']['claims'] if a['mv']['claims'] else 0):.2f}]"
                for t0, a in sorted(acc.items())))
    print("    (each window: c=M(cargo) e=M(energy) k=M(claims))")

    # [6] FLOW SHARES — paper value vs goods value moved per run
    print("\n[6] FLOW SHARES — total face moved as each medium, and paper's share of "
          "(paper+goods) flow, transferable arm:")
    h = f"  {'N':>4} {'horizon':>7} {'cargo face $':>12} {'claim face $':>12} {'energy face':>11} {'paper share':>11}"
    print(h + "\n  " + "-" * (len(h) - 2))
    for hz in (2500, 7500):
        for N in Ns:
            g = sel(XFER, N, hz)
            if not g:
                continue
            cf = np.mean([(r["mx_detail"] or {})["face"]["cargo"] for r in g])
            kf = np.mean([(r["mx_detail"] or {})["face"]["claims"] for r in g])
            ef = np.mean([(r["mx_detail"] or {})["face"]["energy"] for r in g])
            share = kf / (kf + cf) if (kf + cf) > 0 else 0.0
            print(f"  {N:>4} {hz:>7} {cf:>12.0f} {kf:>12.0f} {ef:>11.0f} {share:>11.3f}")

    # [7] KILL status
    print("\n[7] KILL — money does NOT emerge iff claims never re-transfer (velocity≈0, "
          "hold-to-settlement dominates).")
    g240 = sel(XFER, 240) or sel(XFER, Ns[-1])
    if g240:
        vm = np.mean([r["circulation_detail"]["velocity_mean"] for r in g240])
        vx = max(r["circulation_detail"]["velocity_max"] for r in g240)
        ne = np.mean([r["circulation_detail"]["n_endorse_deals"] for r in g240])
        fired = vm < 1e-3 and ne < 1
        print(f"    N={Ns[-1]}: velocity_mean={vm:.3f}, max={vx}, endorse_deals/run={ne:.0f} "
              f"⇒ KILL {'FIRES — receipts do NOT circulate' if fired else 'does NOT fire — claims DO circulate as money'}.")


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
    if column == "P3":                # P23e: moral hazard in the relay
        # The P23 phase-2 grid (identical N, scaled grid, σ, τ, ticks, seeds) ×
        # {spot, bills-flat, bills-contingent}, all dwell-instrumented. spot has
        # no claims (no-bills baseline); flat is the shipped P23 mechanism (α*
        # Nash split fixed at hop time); contingent decays each claim's payout by
        # its carrier's leg dwell above the geodesic counterfactual. dwell=True is
        # a pure instrument (bit-identical), so all three regimes measure dwell.
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        variants = [dict(arm_name="snhp+net"),                           # spot
                    dict(arm_name="snhp+net", bills=True),               # flat
                    dict(arm_name="snhp+net", bills=True,
                         bills_contingent=True)]                         # contingent
        base240 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True, dwell=True)
        for v in variants:
            for seed in range(min(seeds, 8)):
                jobs.append(dict(seed=seed, **base240, **v))
        base24 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                      n_robots=24, lineage=True, dwell=True)
        for v in variants:
            for seed in range(min(seeds, 16)):
                jobs.append(dict(seed=seed, **base24, **v))
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
    if column == "V":                 # v23: the stigmergic order book (P29)
        # The column-G geometry ladder REPLICATED EXACTLY (grid ∈ {24,32,48,64},
        # σ=0.5, τ=0.15, v5, 2500 ticks, 16 seeds) — the G config wins for
        # comparability. Arms: the bargaining/snhp arm and the auction arm as G
        # ran them, × {order_book off, on}. The order book is an SNHP-native
        # (attestation) primitive, so it attaches ONLY to the snhp arm; the
        # auction is the unperturbed comparator (order_book has no code path in
        # AuctionArm — auction on ≡ off, a live bit-identical confirmation). The
        # bills-only control (order_book off, bills on) decomposes the treatment:
        # how much of any edge shift is the async channel vs the claim stack it
        # settles on. Labels: auction / snhp+net (spot, reproduces the hump) /
        # snhp+bill (bills control) / snhp+ob (order book, bills-settled).
        for g in (24, 32, 48, 64):
            base = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5", grid=g)
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="auction", seed=seed, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed, bills=True, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed, order_book=True, **base))
    if column == "V2":                # v31: the depot (PV2)
        # The column-G geometry ladder EXACTLY as V ran it (grid∈{24,32,48,64},
        # σ=0.5, τ=0.15, v5, 2500t, 16 seeds) × {spot, bills-only, depot(+bills)}
        # on the snhp arm + the auction comparator as G ran it. The depot REPLACES
        # V's snhp+ob: deposits are pinned at co-located chargers and takers stage
        # cargo FORWARD one leg (re-depositing at the next depot) — the async chain
        # that owes only the NEXT hop, never the whole route. lineage=True on the
        # snhp arms (pure bookkeeping ⇒ delivered reproduces V's P29 numbers to the
        # decimal) so the far-band d/m and ≥2-hop table is uniform; the auction is
        # the unperturbed comparator (no depot code path in AuctionArm, run exactly
        # as G/V ran it). depots is an SNHP-native (attestation) primitive.
        for g in (24, 32, 48, 64):
            base = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5", grid=g)
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="auction", seed=seed, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed,
                                 lineage=True, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed,
                                 bills=True, lineage=True, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed,
                                 depots=True, lineage=True, **base))
    if column == "Q":                 # v18: endogenous infrastructure (P24)
        # N=240 scaled v5 grid (the P18 charge-bound config), σ=0.5, τ=0.15,
        # build_matter=0.5 (a separate matter field seeded in both arms — the
        # no-build control simply never touches it). 8 seeds.
        #   CORE (P24a + P24c): {no-build, build} × {snhp+net, auction} at BOTH
        #     horizons {2500, 7500} — the mandatory fair-horizon pair (building is
        #     the most truncation-exposed mechanism yet: it amortizes late).
        #   BUDGET (P24b under-provision): snhp+net build across FORCED per-company
        #     build budgets {0,2,4,8,16} at 2500t — welfare(count). budget 0 is a
        #     clean control (never builds/gathers). The cheaper of the two
        #     registered designs (vs a social-planner arm).
        #   TOLL (P24b cross-company pricing): snhp+net build across the toll grid
        #     {cost,2·,4·} on ENDOGENOUS chargers at 2500t (toll 0 == the CORE
        #     build arm) — owner guest revenue vs marginal cost.
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        base = dict(sigma=0.5, tau=0.15, preset="v5", n_robots=240, grid=g240,
                    build_matter=0.5)
        n8 = min(seeds, 8)
        for horizon in (2500, 7500):
            for arm in ("snhp+net", "auction"):
                for seed in range(n8):
                    jobs.append(dict(arm_name=arm, seed=seed, ticks=horizon, **base))
                    jobs.append(dict(arm_name=arm, seed=seed, ticks=horizon,
                                     build=True, toll_level=0.0, **base))
        for budget in (0, 2, 4, 8, 16):
            for seed in range(n8):
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=2500,
                                 build=True, toll_level=0.0, build_budget=budget,
                                 **base))
        from swarm.world import TOLL_GRID as _TG
        for toll in _TG[1:]:
            for seed in range(n8):
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=2500,
                                 build=True, toll_level=float(toll), **base))
    if column == "Q2":                # v18-R: landlords on the frontier (P24-R)
        # The P24-R amendment: column Q re-run in a SCARCE, COMPOSED world. Two
        # changes from Q, and NOTHING else (SPEC "v18-R (column Q2)"):
        #   (i)  FRONTIER SCARCITY — charger_band = single-hop loaded reach
        #        (BATTERY_MAX/(1+LOADED_MULT) = 62.5 Manhattan cells, derived from
        #        the SAME constants Q's placement/deadlock code uses). Preset free
        #        chargers survive ONLY within that home band of a refinery; the far
        #        band (>62.5, == the LINEAGE far-band edge 62) loses its free public
        #        chargers, so BUILT capital is the only far supply. ON for EVERY Q2
        #        cell — it is the world, not a treatment.
        #   (ii) BILLS ON for the bargaining fleet (bills=True, VERIFIED in the cell
        #        dicts below — the registrar diffs these lines; the Q miss was a
        #        silently-absent bills flag). Bills auto-enable lineage; spot/auction
        #        carry lineage=True explicitly so the far-band/≥2-hop table is uniform.
        # Everything else identical to Q: build_matter=0.5, MATTER_COST/BUILD_CREDIT_COST,
        # the Q placement rule, toll grid {0,1,2,4}×cost, budget sweep {0,2,4,8,16},
        # N=240 v5 scaled grid, 8 seeds, BOTH horizons {2500,7500}, deadlock instrument.
        import math as _math
        from swarm.world import (BATTERY_MAX as _BM, LOADED_MULT as _LM,
                                 TOLL_GRID as _TG)
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        BAND = _BM / (1.0 + _LM)                 # 62.5 = single-hop loaded reach
        n8 = min(seeds, 8)
        base = dict(sigma=0.5, tau=0.15, preset="v5", n_robots=240, grid=g240,
                    build_matter=0.5, charger_band=BAND,   # (i) FRONTIER SCARCITY
                    lineage=True, deadlock_track=True)
        # CORE (P24R-a far-band lift, P24R-c bills-vs-spot layering): {no-build, build}
        # × {snhp+net+bills, snhp+net spot, auction} × horizons {2500, 7500}.
        for horizon in (2500, 7500):
            for seed in range(n8):
                # snhp+net + BILLS (the composed arm — bills=True is the fix)
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=horizon,
                                 bills=True, **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=horizon,
                                 bills=True, build=True, toll_level=0.0, **base))
                # snhp+net SPOT (bills=False — the P24R-c layering control)
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=horizon,
                                 **base))
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=horizon,
                                 build=True, toll_level=0.0, **base))
                # AUCTION (unperturbed comparator; no bills path in AuctionArm)
                jobs.append(dict(arm_name="auction", seed=seed, ticks=horizon,
                                 **base))
                jobs.append(dict(arm_name="auction", seed=seed, ticks=horizon,
                                 build=True, toll_level=0.0, **base))
        # BUDGET sweep (P24R-b under-provision) — on the snhp+net+BILLS build arm.
        for budget in (0, 2, 4, 8, 16):
            for seed in range(n8):
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=2500,
                                 bills=True, build=True, toll_level=0.0,
                                 build_budget=budget, **base))
        # TOLL sweep (P24R-b cross-company pricing) — on the snhp+net+BILLS build arm.
        for toll in _TG[1:]:
            for seed in range(n8):
                jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=2500,
                                 bills=True, build=True, toll_level=float(toll),
                                 **base))
        # BILLS-FLAG VERIFICATION control — the SAME bills no-build cell with frontier
        # scarcity OFF (charger_band=0), so it must reproduce the P23 bills signature
        # EXACTLY (delivered_frac≈0.857, far-band≈0.47, ≥2-hop≈0.50). It isolates
        # "is bills on?" from "does scarcity move the numbers?"; if it shows the SPOT
        # signature (≈0.829/0.40/0.025) the bills flag never fired — the Q miss.
        base_noscar = dict(sigma=0.5, tau=0.15, preset="v5", n_robots=240,
                           grid=g240, build_matter=0.5, lineage=True,
                           deadlock_track=True)         # charger_band absent ⇒ 0.0
        for seed in range(n8):
            jobs.append(dict(arm_name="snhp+net", seed=seed, ticks=2500,
                             bills=True, **base_noscar))
    if column == "X":                 # v25: the firm's interior (P X)
        # One firm owns the fleet; the question is what allocation mechanism runs
        # its interior. Four regimes on ONE information environment (P21 realism —
        # belief maps + gossip, r_radio=6 — so COMMAND gets NO free oracle and all
        # four share the same routing competence): the no-mechanism baseline (default
        # solo objectives), (a) command (central planner replaces the decision rule),
        # (b) internal prices (P23b firm_relay, the measured-inert control), (c) claim
        # settlement (bills — the P23 objective-change inside the firm). All carry
        # lineage (the ≥2-hop hand-off share) and deadlock_track (the routing-
        # contamination instrument). Grid N ∈ {24,96,240} × ticks {2500,7500} — the
        # fair-horizon pair is MANDATORY (P18/P28-H). σ=0.5, τ=0.15, v5 scaled grids;
        # 16 seeds (8 at N=240).
        import math as _math
        for N in (24, 96, 240):
            grid = int(round(32 * _math.sqrt(N / 24)))
            n_seeds = min(seeds, 16) if N < 240 else min(seeds, 8)
            for horizon in (2500, 7500):
                base = dict(sigma=0.5, tau=0.15, preset="v5", n_robots=N, grid=grid,
                            ticks=horizon, belief_mode=True, gossip=True, r_radio=6,
                            lineage=True, deadlock_track=True)
                regimes = [dict(),                    # baseline (no mechanism)
                           dict(command=True),        # (a) COMMAND
                           dict(firm_relay=True),     # (b) INTERNAL PRICES (P23b)
                           dict(bills=True)]          # (c) CLAIM SETTLEMENT (bills)
                for reg in regimes:
                    for seed in range(n_seeds):
                        jobs.append(dict(arm_name="snhp+net", seed=seed, **base, **reg))
    if column == "S":                 # v20: institutions as a substitute for cognition (P26)
        # 2×2: navigation {smart, dumb} × property rights {coarse, granular}. All
        # cells ride the v11/v12 moving field (belief maps + dynamic + contested)
        # with K0 scouting ON — the native habitat of the K2 prospect-claims
        # machinery. GRANULAR = prospect_claims (per-rock claim WINDOWS on arrivals
        # + the sector issue the deal economy uses to TRADE claim assignments);
        # COARSE = the default sector regime, no windows. DUMB = nav_dumb (greedy
        # nearest-KNOWN-rock + noise REPLACES best_claim's richest-per-distance Φ
        # routing; deals / physics / deal-Φ untouched — we dumb ROUTING, not the
        # bargaining brain). snhp+net (the deal economy) is the thesis arm; the
        # auction runs the SAME 2×2 as a no-bargaining control — it gets the window
        # EXCLUSION but NOT the tradeable REALLOCATION (no deals ⇒ no sector swaps),
        # so auction-vs-snhp separates institutional exclusion from claims trading.
        import math as _math
        moving = dict(belief_mode=True, dynamic_field=True, contested=True,
                      scouting=True)

        def _cellsS(N, grid, n_seeds, horizon):
            for arm in ("snhp+net", "auction"):
                for nav_dumb in (False, True):
                    for granular in (False, True):
                        for seed in range(n_seeds):
                            jobs.append(dict(
                                arm_name=arm, sigma=0.5, seed=seed,
                                ticks=horizon, tau=0.15, preset="v5",
                                n_robots=N, grid=grid, nav_dumb=nav_dumb,
                                prospect_claims=granular, **moving))
        # N=24 × 16 seeds (the K column's density) — the primary 2×2 + controls.
        _cellsS(24, 32, min(seeds, 16), ticks)
        # N=96 × 8 seeds (density-fixed grid) if the compute budget allows —
        # report both or note the cut in the P26 block.
        _cellsS(96, int(round(32 * _math.sqrt(96 / 24))), min(seeds, 8), ticks)
        # fair-horizon spot-check (P18/P28-H): claims trading is coordination that
        # can amortize late — re-run the gap column (smart+coarse, dumb+coarse) and
        # the thesis cell (dumb+granular) at 7,500 ticks × 4 seeds, N=24, snhp+net.
        for nav_dumb, granular in ((False, False), (True, False), (True, True)):
            for seed in range(min(seeds, 4)):
                jobs.append(dict(arm_name="snhp+net", sigma=0.5, seed=seed,
                                 ticks=7500, tau=0.15, preset="v5",
                                 n_robots=24, grid=32, nav_dumb=nav_dumb,
                                 prospect_claims=granular, **moving))
    if column == "Z":                 # v27: forgery — the receipt under attack (PZ)
        # Scope: the v6 attested-books GATE only (bills OFF — one assumption at a
        # time). liar_frac=0.25, σ=0.5, τ=0.15, v5, 2500 ticks, 16 seeds, N=24 (the
        # v6 scale). The REGISTERED cost grid (deal-value scale: BATTERY_MAX=100,
        # deal surplus O(1–10), TXN_COST=0.05):
        #     c_f ∈ {0, 0.5, 2, 8}   ×   c_v ∈ {0.25, 1, 4}   (energy units)
        # over two verification regimes (MANDATED, ENDOGENOUS). References: the
        # healthy gated tier (receipt unforgeable), the trust-open feeding-frenzy
        # floor, the no-verification collapse (c_f only), and the U reputation
        # regime (attestation-free enforcement) at matched liars for PZc.
        import math as _math
        base = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5", liar_frac=0.25)
        n_seeds = min(seeds, 16)
        CF = (0.0, 0.5, 2.0, 8.0)
        CV = (0.25, 1.0, 4.0)
        # (1) healthy-tier reference — gated, receipt UNFORGEABLE (forgery off)
        for seed in range(n_seeds):
            jobs.append(dict(arm_name="trust-gated-hz", seed=seed,
                             defended=True, **base))
        # (2) feeding-frenzy floor — ungated cooperation (the v6 collapse target)
        for seed in range(n_seeds):
            jobs.append(dict(arm_name="trust-open-hz", seed=seed,
                             defended=True, **base))
        # (3) the U reputation baseline (regime a: reputation-only, no attestation)
        #     — cell-invariant (trust-open has no gate for forgery to attack), the
        #     PZc comparator under equal liar pressure
        for seed in range(n_seeds):
            jobs.append(dict(arm_name="trust-open-hz", seed=seed,
                             defended=False, reputation=True, **base))
        # (4) NO-verification collapse under forgery (depends on c_f alone)
        for cf in CF:
            for seed in range(n_seeds):
                jobs.append(dict(arm_name="trust-gated-hz", seed=seed, defended=True,
                                 forgery=True, forge_cost=cf, verify_cost=0.0,
                                 verify_regime="none", **base))
        # (5) THE GRID — cost ratio × two verification regimes
        for regime in ("mandated", "endogenous"):
            for cf in CF:
                for cv in CV:
                    for seed in range(n_seeds):
                        jobs.append(dict(arm_name="trust-gated-hz", seed=seed,
                                         defended=True, forgery=True, forge_cost=cf,
                                         verify_cost=cv, verify_regime=regime, **base))
        # (6) N=96 on the most informative cells (near the cliff), 8 seeds — the
        #     scale check that the cliff is not an N=24 artifact
        N = 96
        grid96 = int(round(32 * _math.sqrt(N / 24)))
        for regime in ("mandated", "endogenous"):
            for cf, cv in ((0.0, 4.0), (2.0, 1.0), (2.0, 4.0)):
                for seed in range(min(seeds, 8)):
                    jobs.append(dict(arm_name="trust-gated-hz", seed=seed,
                                     n_robots=N, grid=grid96, defended=True,
                                     forgery=True, forge_cost=cf, verify_cost=cv,
                                     verify_regime=regime, **base))
    if column == "AA":                # v28: mortality and the persistence of paper (PAA)
        # The P23 phase-2 grid (identical N, scaled grid, σ, τ, ticks, seeds) ×
        # {claims-die, estates, risk-premium} + the no-bills spot baseline. Mortality
        # is the ENDOGENOUS FLATLINE hazard only (a chassis stranded FLATLINE_TICKS
        # unrescued dies). The registered base-rate check (measured BEFORE this grid,
        # flatline alone) cleared the ~3-deaths/run detectability bar at BOTH scales —
        # 7.0/run at N=24, 12.7/run at N=240 — so the registered wear-out hazard is
        # NOT engaged (it ships off-by-default; at N=240 it would add ~100 deaths/run
        # and swamp the economy). Anchors around the four cells:
        #   (ref-A) the mortality-OFF bills world (the pure P23 anchor) — the death-
        #     rate sensitivity's LEFT endpoint (0 deaths ⇒ the regimes must coincide).
        #   (ref-B) a HIGHER-mortality sensitivity point at N=24: the same claims-die /
        #     estates cells WITH wear-out on (≈15 deaths/run) — the sensitivity curve's
        #     right endpoint (does the estates−claims-die gap widen with the death rate).
        #   (ref-C) the fair-horizon (7,500t) claims-die vs estates thesis contrast at
        #     4 seeds, in case the freeze-out loss amortizes late (standing rule).
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        # (arm kwargs, label-driving flags) for the four grid cells — FLATLINE only
        cells = [dict(bills=True, mortality=True, death_regime="claims_die"),
                 dict(bills=True, mortality=True, death_regime="estates"),
                 dict(bills=True, mortality=True, death_regime="risk_premium"),
                 dict(bills=False, mortality=True, death_regime="none")]  # spot baseline
        base240 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True)
        base24 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                      n_robots=24, lineage=True)
        for cell in cells:
            for seed in range(min(seeds, 8)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base240, **cell))
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base24, **cell))
        # (ref-A) mortality-OFF bills anchor, both scales — the 0-death endpoint
        for seed in range(min(seeds, 8)):
            jobs.append(dict(arm_name="snhp+net", seed=seed, bills=True, **base240))
        for seed in range(min(seeds, 16)):
            jobs.append(dict(arm_name="snhp+net", seed=seed, bills=True, **base24))
        # (ref-B) higher-mortality sensitivity (N=24, wear-out ON ≈15 deaths/run)
        for reg in ("claims_die", "estates", "risk_premium"):
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, bills=True,
                                 mortality=True, death_regime=reg, wearout=True,
                                 **base24))
        # (ref-C) fair-horizon thesis contrast (claims-die vs estates), 7,500t × 4 seeds
        for reg in ("claims_die", "estates"):
            for seed in range(min(seeds, 4)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, bills=True,
                                 mortality=True, death_regime=reg,
                                 sigma=0.5, ticks=7500, tau=0.15, preset="v5",
                                 n_robots=24, lineage=True))
    if column == "AB":                # v29: the crash — contagion in the web (PAB)
        # The bills+mortality(claims-die) economy, LONG horizon, with the far band
        # going dark at T_shock. Six cells: {gross, clearinghouse} × {shock,
        # no-shock control} + spot × {shock, no-shock control} (the leverage
        # question — does the shock hurt a paperless economy less?).
        #
        # REGISTERED T_shock — PER GRID, NOT the contract's illustrative 3,500. The v5
        # economy delivers/relays its far band over an ACTIVE phase then PLATEAUS (far
        # cargo either delivered or P24-deadlocked in living, un-dying drones); a shock
        # AFTER that phase lands on a settled economy with nothing in flight and is
        # inert. The active phase's timescale is N-dependent — the dense N=24 field
        # resolves its far band by ~tick 350, the N=240 field relays it over ~ticks
        # 300–2,000 — so T_shock is set to the MIDPOINT of each grid's active far-band
        # relay phase: N=24 → tick 200 (15/16 seeds have far cargo in flight there),
        # N=240 → tick 1,000. Each catches mature pre-shock chains mid-flight
        # (identical across regimes and seeds within a grid). Horizon stays LONG
        # (7,500t) so the scar's recovery window and any late
        # amortization are observable. (N=240 is the PRIMARY; the dense N=24 web is
        # transient, so N=24 is the weaker scale reference — reported honestly.)
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        HORIZON = 7500
        DIE = dict(bills=True, mortality=True, death_regime="claims_die")

        def _cells(T):
            return [
                dict(**DIE, shock=True, shock_tick=T),                      # gross+shk
                dict(**DIE),                                               # gross ctl
                dict(**DIE, clearinghouse=True, shock=True, shock_tick=T), # ccp+shk
                dict(**DIE, clearinghouse=True),                          # ccp  ctl
                dict(bills=False, mortality=True, death_regime="none",
                     shock=True, shock_tick=T),                            # spot+shk
                dict(bills=False, mortality=True, death_regime="none"),    # spot ctl
            ]
        base240 = dict(sigma=0.5, ticks=HORIZON, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True)
        base24 = dict(sigma=0.5, ticks=HORIZON, tau=0.15, preset="v5",
                      n_robots=24, lineage=True)
        for cell in _cells(1000):                       # N=240 primary, T_shock=1,000
            for seed in range(min(seeds, 8)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base240, **cell))
        for cell in _cells(200):                        # N=24 reference, T_shock=200
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base24, **cell))
    if column == "AB2":               # v32: the crash with teeth — debt (PAB2)
        # The AB crash economy (bills+claims-die mortality, LONG horizon, far band dark
        # at T_shock) PLUS claim-collateralized borrowing. The registered grid is
        # LTV {0, 0.5, 0.8} × {gross, clearinghouse} × {shock, no-shock control},
        # reusing the AB shock protocol EXACTLY (per-grid T_shock at the active-relay
        # midpoint: 1,000 at N=240, 200 at N=24). LTV 0 ≡ AB as run (bit-identical to
        # the AB bills cells) — the baseline where post-shock deaths FELL. The paperless
        # spot cells are omitted (debt requires bills — no claims, no collateral).
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        HORIZON = 7500
        DIE = dict(bills=True, mortality=True, death_regime="claims_die")
        LTVS = (0.0, 0.5, 0.8)

        def _debt_cells(T):
            cells = []
            for ltv in LTVS:
                for ccp in (False, True):               # gross bilateral, clearinghouse
                    for sh in (True, False):            # shock, no-shock control
                        c = dict(**DIE, debt_ltv=ltv, clearinghouse=ccp)
                        if sh:
                            c.update(shock=True, shock_tick=T)
                        cells.append(c)
            return cells
        base240 = dict(sigma=0.5, ticks=HORIZON, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True)
        base24 = dict(sigma=0.5, ticks=HORIZON, tau=0.15, preset="v5",
                      n_robots=24, lineage=True)
        for cell in _debt_cells(1000):                  # N=240 primary, T_shock=1,000
            for seed in range(min(seeds, 8)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base240, **cell))
        for cell in _debt_cells(200):                   # N=24 reference, T_shock=200
            for seed in range(min(seeds, 16)):
                jobs.append(dict(arm_name="snhp+net", seed=seed, **base24, **cell))
    if column == "M2":                # v30: the bill becomes money — transferable claims
        # The P23 phase-2 grid (identical N, scaled grid, σ, τ, ticks, seeds) ×
        # {spot (no claims), bills-static, bills-transferable}. spot is the paperless
        # baseline; static is the shipped P23 mechanism (claims exist, never endorsed —
        # the PM2b control); transferable makes each claim position ENDORSABLE as
        # payment. Plus a fair-horizon spot-check at 7,500t / 4 seeds on the
        # transferable arm (circulation is coordination — the P18/P28-H long-horizon
        # rule), so any velocity/M(x) growth is not a truncation artifact.
        import math as _math
        g240 = int(round(32 * _math.sqrt(240 / 24)))
        variants = [dict(arm_name="snhp+net"),                        # spot (paperless)
                    dict(arm_name="snhp+net", bills=True),            # bills-static
                    dict(arm_name="snhp+net", bills=True,
                         claims_transferable=True)]                   # bills-transferable
        base240 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                       n_robots=240, grid=g240, lineage=True)
        for v in variants:
            for seed in range(min(seeds, 8)):
                jobs.append(dict(seed=seed, **base240, **v))
        base24 = dict(sigma=0.5, ticks=ticks, tau=0.15, preset="v5",
                      n_robots=24, lineage=True)
        for v in variants:
            for seed in range(min(seeds, 16)):
                jobs.append(dict(seed=seed, **base24, **v))
        # fair-horizon spot-check: transferable arm at 7,500t (N=240 primary + N=24),
        # 4 seeds — the M(x)/velocity trajectory at the long horizon.
        for seed in range(min(seeds, 4)):
            jobs.append(dict(seed=seed, arm_name="snhp+net", bills=True,
                             claims_transferable=True, ticks=7500,
                             sigma=0.5, tau=0.15, preset="v5",
                             n_robots=240, grid=g240, lineage=True))
            jobs.append(dict(seed=seed, arm_name="snhp+net", bills=True,
                             claims_transferable=True, ticks=7500,
                             sigma=0.5, tau=0.15, preset="v5",
                             n_robots=24, lineage=True))
    if column == "bridge":
        for arm in ("snhp", "auction"):
            for seed in range(8):
                jobs.append(dict(arm_name=arm, sigma=1.0, seed=seed,
                                 ticks=ticks, preset="v3"))
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--column", default="A", choices=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "O", "P", "P2", "P3", "Q", "Q2", "S", "U", "UH", "V", "V2", "X", "Z", "AA", "AB", "AB2", "M2", "all", "bridge"])
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
        phase2e(rows)
        u_report(rows)
        p29(rows)
        p29v2(rows)
        p24(rows)
        p24r(rows)
        px(rows)
        p26(rows)
        pz_report(rows)
        paa_report(rows)
        pab_report(rows)
        pab2_report(rows)
        pm2_report(rows)
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
    phase2e(rows)
    u_report(rows)
    p29(rows)
    p29v2(rows)
    p24(rows)
    p24r(rows)
    px(rows)
    p26(rows)
    pz_report(rows)
    paa_report(rows)
    pab_report(rows)
    pab2_report(rows)
    pm2_report(rows)


if __name__ == "__main__":
    main()

"""B6 flywheel — the tipping sim (task #71; the whitepaper's missing Figure 1).

The block modelled two consumer regimes in isolation: PASSIVE (buys the best
posted board, sticky, friction) and AGENT-MEDIATED (buyer/: zero friction,
shops every merchant, attested disclosure, credible forward commitment). This
module runs a MIXED population where a fraction φ of consumers are agent-
mediated and (1−φ) are passive, and SWEEPS φ from 0 to 1.

THE TWO-SIDED FLYWHEEL under test (NETWORK.md §B.1 + the wholesale flywheel):
more agents → more disclosed demand → (a) the merchant's demand-state estimate
sharpens (the B6.1 conjugate-shrinkage: σ_cal(φ) falls) and (b) forward-demand
certainty lets the supplier price nearer its floor (COGS(φ) falls) → better
deals → more consumers adopt agents. The question is whether that loop has
POSITIVE feedback strong enough to SELF-SUSTAIN.

THE DELIVERABLE is a PHASE DIAGRAM. Two honest questions, measured not assumed:

  Q1 (the flywheel force). Does the agent's realized CONSUMER edge over the
     strong posted board GROW with φ? The edge is decomposed into
       * E_shop(φ)  — the spot shopping/attestation transfer (buyer/RESULTS
                      SHOP+attested), and
       * E_coord(φ) — the forward-demand COORDINATION growth per member, whose
                      cluster size scales with φ (buyer/RESULTS B5: matching
                      efficiency, coord−indep, RISES with cluster size).
     If E(φ) is flat or shrinking, there is NO flywheel force — reported plainly.

  Q2 (the tipping point). A consumer adopts an agent iff its realized edge
     e_i(φ) exceeds its idiosyncratic adoption cost c_i (the hassle/subscription
     of running an agent). The adoption RESPONSE is
       F(φ) = (1/N) Σ_i 1[ e_i(φ) > c_i ].
     Fixed points solve φ* = F(φ*). A tipping point k* is an UNSTABLE interior
     fixed point (F'(k*) > 1): below it adoption decays, above it the flywheel
     carries adoption to a high stable state. Whether k* EXISTS depends on (i)
     the flywheel force (Q1) and (ii) the adoption-cost level; we map the full
     phase diagram over a grid of adoption-cost medians and classify each as
     monostable-low / monostable-high / BISTABLE (a genuine tipping point).

THE LUCAS POINT (stated in the writeup): the passive-consumer parameters —
σ_cal=σ0 (the central-cell mis-set sticker) and full demand variance — are
calibrated to the world SNHP REPLACES. The φ→1 end of the sweep is therefore
the TARGET world (every consumer agent-mediated, the merchant near-omniscient).
The phase diagram asks whether, seeded from a few adopters, the block tips there
on its own or slides back.

Rigor (binding, same standards as every package): paired on CONSUMER IDENTITY
never on φ (the whole population stream is shared across every φ cell, and the
merchant's per-SKU calibration error z is drawn ONCE and only its magnitude
σ_cal(φ) shrinks — a clean monotone sharpening paired across the sweep); a 95%
CI on every edge and every Δ; no growth claim when a CI includes zero. Reuses
buyer/strategies + the committed BlockMerchant VERBATIM (read-only) and the
block's real NYC street population. No LLM anywhere; byte-deterministic on seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from block import calibration, population
from block.population import GOOD_MU
from vend.core import Listing, substream
from vend.world import _profit_optimal_list_price, fresh_machine

FLYWHEEL_VERSION = 1

_NON_OVERLAP_MARKUP = 1.15   # block.venues.NON_OVERLAP_OUTSIDE_MARKUP, kept explicit


# ── config ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FlyConfig:
    """The flywheel sweep knobs. σ0 and the full-variance passive world are the
    'world SNHP replaces' (the Lucas anchor); info_scale/cogs_gain_max set how
    fast disclosure sharpens the merchant and shaves COGS."""
    sigma0: float = 0.15          # the mis-set sticker's calibration noise (central cell)
    alpha0: float = 3.0           # B6.1 prior strength (the conjugate shrinkage α₀)
    info_scale: float = 12.0      # disclosure information rate: σ_cal(φ)=σ0·√(α₀/(α₀+φ·info))
    cogs_gain_max: float = 0.06   # max COGS saving from full demand certainty (wholesale flywheel)
    p_spoil: float = 0.40         # commit/coordinate spoilage prob (buyer/RESULTS B4/B5)
    coord_target: str = "sandwich"  # the scarce would-spoil perishable coordination clears
    coord_pool: int = 20          # the resident cluster's full size (φ=1 ⇒ all coordinate)
    coord_scarcity: float = 0.5   # scarce would-spoil units per member
    seeds: int = 8
    pop_per_seed: int = 700
    phi_grid: tuple = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    # the adoption-cost phase axis: lognormal hassle of running an agent, median
    # swept across this grid so the phase diagram maps k* over adoption cost.
    adopt_cost_grid: tuple = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
    # heterogeneity of the adoption cost (lognormal σ). Swept too: whether a
    # tipping point can EXIST is governed by heterogeneity — a low-cost adopter
    # tail (high σ) keeps adoption from collapsing to zero, erasing the tip.
    adopt_cost_sigmas: tuple = (0.05, 0.3, 0.6)


# ── the paired sharpening (data channel) + COGS certainty channel ────────────

def _shrink(phi: float, cfg: FlyConfig) -> float:
    """The B6.1 conjugate prior-weight: α₀/(α₀+φ·info). 1 at φ=0 (no disclosure),
    →0 as φ→1 (the block's disclosures swamp the prior). Both flywheel channels
    ride it: σ_cal(φ)=σ0·√shrink, COGS(φ)=1−gain·(1−shrink)."""
    return cfg.alpha0 / (cfg.alpha0 + phi * cfg.info_scale)


def sigma_cal(phi: float, cfg: FlyConfig) -> float:
    return cfg.sigma0 * math.sqrt(_shrink(phi, cfg))


def cogs_scale(phi: float, cfg: FlyConfig) -> float:
    return 1.0 - cfg.cogs_gain_max * (1.0 - _shrink(phi, cfg))


def _znorm(seed: int, *parts) -> float:
    return float(np.random.default_rng(substream(seed, *parts)).standard_normal())


def _vend_catalog(seed: int, sigma: float, s_cogs: float) -> dict[str, Listing]:
    """The vending board at calibration noise `sigma` and COGS scale `s_cogs`.
    The per-SKU error z is drawn ONCE per (seed, sku) and only its magnitude
    `sigma` shrinks across the φ-sweep — a monotone sharpening paired across φ
    (the same variance-reduction discipline as B6.1 drawing g_d once). The list
    price re-optimizes at the sharper estimate AND the lower cost, so the strong
    posted board genuinely improves as the flywheel turns (its best shot)."""
    bodega_posted = {i: p for i, p, _c in calibration.BODEGA_CATALOG}
    cat: dict[str, Listing] = {}
    for sku, mu, cost, salv, life, par in calibration.VENDING_CATALOG:
        z = _znorm(seed, "z-vend", sku)
        mu_est = mu * math.exp(sigma * z)             # block convention (no −σ²/2)
        c, sv = cost * s_cogs, salv * s_cogs
        lp = round(_profit_optimal_list_price(mu_est, c), 2)
        outside = bodega_posted.get(sku) if sku in bodega_posted else round(
            _profit_optimal_list_price(mu, cost) * _NON_OVERLAP_MARKUP, 2)
        cat[sku] = Listing(sku=sku, list_price=lp, unit_cost=c, salvage=sv,
                           shelf_life_days=life, par_stock=par,
                           wtp_mu_est=mu_est, bodega_price=outside)
    return cat


def _bodega_catalog(seed: int, sigma: float, s_cogs: float,
                    vend_cat: dict[str, Listing]) -> dict[str, Listing]:
    """The bodega board (deep, non-perishable). Posted prices are FIXED (the
    calibration board); the flywheel touches only its Nash-quote floor (via
    s_cogs) and its own independent calibration error (so the two boards
    disperse — the shopping surface)."""
    from block.venues import BodegaVenue
    cat: dict[str, Listing] = {}
    for item, price, cost in calibration.BODEGA_CATALOG:
        z = _znorm(seed, "z-bod", item)
        mu_est = GOOD_MU[item] * math.exp(sigma * z)
        outside = vend_cat[item].list_price if item in vend_cat else round(
            price * _NON_OVERLAP_MARKUP, 2)
        cat[item] = Listing(sku=item, list_price=price, unit_cost=cost * s_cogs,
                            salvage=0.0, shelf_life_days=3650,
                            par_stock=BodegaVenue.PAR_PER_ITEM,
                            wtp_mu_est=mu_est, bodega_price=outside)
    return cat


def _merchants_at(seed: int, phi: float, cfg: FlyConfig):
    """The two brokered block merchants at penetration φ (BlockMerchant VERBATIM
    over a real vend MachineState, so salvage_floor is the genuine c_eff)."""
    from block.agentdemand import BlockMerchant
    sigma, s = sigma_cal(phi, cfg), cogs_scale(phi, cfg)
    vcat = _vend_catalog(seed, sigma, s)
    bcat = _bodega_catalog(seed, sigma, s, vcat)
    V = BlockMerchant("fly-vend", fresh_machine("fly-vend", vcat), vcat)
    B = BlockMerchant("fly-bodega", fresh_machine("fly-bodega", bcat), bcat)
    return V, B


# ── the spot edge (E_shop) + the coordination edge (E_coord) ─────────────────

def _spot_pass(seed: int, phi: float, cfg: FlyConfig, pop):
    """One pass over the paired panel at penetration φ, returning BOTH sides of
    the two-sided flywheel:
      * edges[i] = e_shop_i(φ) = (attested shop across both merchants) − (best
        posted board + outside), friction 0 for the agent. The passive baseline
        is the STRONG posted board at σ_cal(φ), which IMPROVES as the flywheel
        turns (inference gets its best shot).
      * (agent_margin_pc, passive_margin_pc) = the merchant's realized margin per
        consumer on the bundle each consumer actually takes — under agent-
        mediated shopping vs passive posting (the merchant side: does its margin
        hold as φ rises, or does shopping compete it away?). The passive margin
        is booked on the SAME posted bundle the passive consumer chooses (best
        posted board vs walk), so the two are matched, not a max-margin proxy.
    Paired on consumer identity."""
    from buyer.agent import BuyerAgent, fallback_surplus
    from buyer.strategies import shop
    from buyer.values import best_bundle
    V, B = _merchants_at(seed, phi, cfg)
    union = set(V._catalog) | set(B._catalog)
    edges = np.empty(len(pop))
    m_a = m_p = 0.0
    for i, sh in enumerate(pop):
        wtp = {s: sh.wtp[s] for s in union}
        agent = BuyerAgent(sh.uid, wtp, sh.cross_walk, friction=0.0)
        sr = shop(agent, [V, B], attested=True)
        s_p, pm_id = fallback_surplus(wtp, sh.cross_walk, [V, B])
        edges[i] = sr.realized - s_p
        if sr.quote is not None:
            m_a += sr.quote.qty * (sr.quote.unit_price - sr.quote.salvage_floor)
        # passive margin on the ACTUAL posted bundle the passive consumer buys
        # (walk to the outside ⇒ neither block merchant earns anything)
        if pm_id in ("fly-vend", "fly-bodega"):
            M = V if pm_id == "fly-vend" else B
            board = M.board()
            prices = {s: b.list_price for s, b in board.items()}
            stock = {s: b.stock for s, b in board.items()}
            sku, qty, _ = best_bundle(wtp, prices, stock)
            if sku is not None:
                m_p += qty * (prices[sku] - M.salvage_floor(sku))
    n = max(1, len(pop))
    return edges, m_a / n, m_p / n


def _coord_edge(seed: int, phi: float, cfg: FlyConfig, pop) -> float:
    """The forward-demand COORDINATION growth per member at penetration φ. The
    agent cluster is k(φ)=round(φ·pool) residents committing forward demand for
    the scarce would-spoil perishable; efficient matching routes the s_risk
    scarce units to the highest-value members. e_coord(φ) = coord growth/member
    − the INDEPENDENT-commit baseline (uncoordinated race). At φ→0 the cluster is
    a single agent (k≤1) so coordination adds nothing; as φ grows the matching
    premium grows (buyer/RESULTS B5). This is the flywheel's increasing-returns
    channel — a club good shared by every agent in the cluster."""
    from buyer.strategies import coordinate
    salvage = {s: sv for s, _mu, _c, sv, *_ in calibration.VENDING_CATALOG}[
        cfg.coord_target]
    # scale salvage by the same COGS certainty (the floor moves with procurement)
    salvage *= cogs_scale(phi, cfg)
    k = int(round(phi * cfg.coord_pool))
    if k < 2:
        return 0.0                                  # no cluster to coordinate
    vals = [sh.wtp[cfg.coord_target] for sh in pop]
    s_risk = max(1, int(round(k * cfg.coord_scarcity)))
    # average the matching premium over disjoint clusters of size k (paired seed
    # per cluster for the independent-race allocation)
    prem = []
    for c in range(0, (len(vals) // k) * k, k):
        grp = vals[c:c + k]
        sd = (seed * 131 + c) & 0x7FFFFFFF
        coord = coordinate(grp, salvage=salvage, s_risk=s_risk,
                           p_spoil=cfg.p_spoil, extraction=0.5,
                           allocation="efficient")
        indep = coordinate(grp, salvage=salvage, s_risk=s_risk,
                           p_spoil=cfg.p_spoil, extraction=0.5,
                           allocation="random", seed=sd)
        prem.append((coord.buyer_growth - indep.buyer_growth) / k)
    return float(np.mean(prem)) if prem else 0.0


# ── the sweep ────────────────────────────────────────────────────────────────

def _population(seed: int, cfg: FlyConfig):
    """The block's real NYC street shoppers (home vending/bodega), keyed on uid
    — the SAME panel every φ cell faces (paired by identity)."""
    from vend.world import TICKS_PER_DAY
    out, day = [], 0
    while len(out) < cfg.pop_per_seed:
        stream = population.day_stream(seed, day)
        for t in range(TICKS_PER_DAY):
            for sh in stream[t]:
                if sh.home in ("vending", "bodega"):
                    out.append(sh)
        day += 1
    return out[:cfg.pop_per_seed]


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


def run_sweep(cfg: FlyConfig = FlyConfig(), seed0: int = 20260710) -> dict:
    """Sweep φ and, per cell, record the spot-edge / coord-edge / total-edge
    (per-seed means → CIs across seeds) and the merchant-margin read. Also
    carries, per (seed, consumer), the edge e_i(φ) needed for the fixed-point
    map. Paired: the population and the calibration-error directions are shared
    across every φ cell; only σ_cal(φ) and COGS(φ) move."""
    per_seed_pops = {si: _population(seed0 + si, cfg) for si in range(cfg.seeds)}
    cells = []
    # e_matrix[phi_index] = per-seed list of per-consumer spot edges (for F(φ))
    spot_by_phi: dict[float, list[np.ndarray]] = {}
    coord_by_phi: dict[float, list[float]] = {}
    for phi in cfg.phi_grid:
        shop_pc, coord_pc, tot_pc = [], [], []
        m_agent, m_passive = [], []
        spot_seeds, coord_seeds = [], []
        for si in range(cfg.seeds):
            seed = seed0 + si
            pop = per_seed_pops[si]
            e_spot, ma, mp = _spot_pass(seed, phi, cfg, pop)
            e_coord = _coord_edge(seed, phi, cfg, pop)
            spot_seeds.append(e_spot)
            coord_seeds.append(e_coord)
            shop_pc.append(float(e_spot.mean()))
            coord_pc.append(e_coord)
            tot_pc.append(float(e_spot.mean()) + e_coord)
            m_agent.append(ma); m_passive.append(mp)
        spot_by_phi[phi] = spot_seeds
        coord_by_phi[phi] = coord_seeds
        cells.append({
            "phi": phi,
            "sigma_cal": round(sigma_cal(phi, cfg), 4),
            "cogs_scale": round(cogs_scale(phi, cfg), 4),
            "E_shop": _mean_ci(shop_pc),
            "E_coord": _mean_ci(coord_pc),
            "E_total": _mean_ci(tot_pc),
            "merchant_margin_agent": _mean_ci(m_agent),
            "merchant_margin_passive": _mean_ci(m_passive),
        })
    # Q1: does the edge grow? paired (across seeds) φ=1 − φ=0.
    tot0 = np.array([float(spot_by_phi[cfg.phi_grid[0]][si].mean())
                     + coord_by_phi[cfg.phi_grid[0]][si] for si in range(cfg.seeds)])
    tot1 = np.array([float(spot_by_phi[cfg.phi_grid[-1]][si].mean())
                     + coord_by_phi[cfg.phi_grid[-1]][si] for si in range(cfg.seeds)])
    shop0 = np.array([spot_by_phi[cfg.phi_grid[0]][si].mean() for si in range(cfg.seeds)])
    shop1 = np.array([spot_by_phi[cfg.phi_grid[-1]][si].mean() for si in range(cfg.seeds)])
    grows = _mean_ci(tot1 - tot0)
    d_shop = _mean_ci(shop1 - shop0)
    phase = _phase_diagram(cfg, spot_by_phi, coord_by_phi, seed0)
    edge_grows = bool(grows["ci95"] is not None and grows["ci95"][0] > 0)
    shop_flat = bool(d_shop["ci95"] is not None and d_shop["ci95"][0] <= 0 <= d_shop["ci95"][1])
    robust_tip = any(blk["adopt_cost_sigma"] >= 0.3 and blk["any_tipping_point"]
                     for blk in phase["blocks"])
    return {
        "flywheel_version": FLYWHEEL_VERSION,
        "config": _cfg_dict(cfg),
        "cells": cells,
        "Q1_edge_grows_with_phi": {
            "E_total_by_phi": [c["E_total"]["mean"] for c in cells],
            "E_shop_by_phi": [c["E_shop"]["mean"] for c in cells],
            "E_coord_by_phi": [c["E_coord"]["mean"] for c in cells],
            "delta_total_phi1_minus_phi0": grows,
            "delta_shop_phi1_minus_phi0": d_shop,
            "grows": edge_grows,
            "shrinks": bool(grows["ci95"] is not None and grows["ci95"][1] < 0),
            "shop_channel_flat": shop_flat,
        },
        "Q2_phase_diagram": phase,
        "verdict": {
            "edge_grows_with_phi": edge_grows,
            "growth_channel": "coordination (durable), NOT shopping (flat transfer)"
            if (edge_grows and shop_flat) else "mixed",
            "any_tipping_point": phase["any_tipping_point"],
            "robust_tipping_point_under_heterogeneity": robust_tip,
            "summary": (
                "flywheel force REAL (edge grows via coordination) but "
                "front-loaded and standalone-value-dominated ⇒ NO robust k*: "
                "monostable under realistic adoption-cost heterogeneity"
                if edge_grows and not robust_tip else
                "tipping point k* present" if robust_tip else
                "no flywheel force (edge flat/shrinking)"),
        },
    }


def _cfg_dict(cfg: FlyConfig) -> dict:
    return {"sigma0": cfg.sigma0, "alpha0": cfg.alpha0, "info_scale": cfg.info_scale,
            "cogs_gain_max": cfg.cogs_gain_max, "p_spoil": cfg.p_spoil,
            "coord_target": cfg.coord_target, "coord_pool": cfg.coord_pool,
            "coord_scarcity": cfg.coord_scarcity, "seeds": cfg.seeds,
            "pop_per_seed": cfg.pop_per_seed, "phi_grid": list(cfg.phi_grid),
            "adopt_cost_grid": list(cfg.adopt_cost_grid),
            "adopt_cost_sigmas": list(cfg.adopt_cost_sigmas)}


# ── the fixed-point / phase-diagram machinery ────────────────────────────────

def adoption_response(edges: np.ndarray, costs: np.ndarray) -> float:
    """F evaluated at one φ: the fraction of consumers whose realized agent edge
    exceeds their idiosyncratic adoption cost. edges[i] = e_i(φ), costs[i] = c_i."""
    return float(np.mean(edges > costs))


def fixed_points(phi_grid, F_vals) -> list[dict]:
    """Solve φ* = F(φ*) on the grid by locating sign changes of g(φ)=F(φ)−φ and
    linearly interpolating the crossing. Stability from the sign of g's slope at
    the crossing: g going + → − (F−φ decreasing through 0) ⇒ STABLE; − → + ⇒
    UNSTABLE (a tipping point k*). Endpoints handled: if F(0) ≤ 0 then φ=0 is a
    stable fixed point (no adoption); if F(1) ≥ 1 then φ=1 is stable (full)."""
    phi = list(phi_grid)
    g = [F_vals[i] - phi[i] for i in range(len(phi))]
    fps = []
    # φ=0 as a fixed point (nobody adopts at zero penetration)
    if F_vals[0] <= 1e-9:
        fps.append({"phi_star": 0.0, "stability": "stable", "kind": "no-adoption"})
    for i in range(len(phi) - 1):
        if g[i] == 0.0 and 0.0 < phi[i] < 1.0:
            slope = (g[i + 1] - g[i - 1]) if 0 < i else (g[i + 1] - g[i])
            fps.append({"phi_star": round(phi[i], 4),
                        "stability": "unstable" if slope > 0 else "stable",
                        "kind": "tipping" if slope > 0 else "interior"})
            continue
        if g[i] * g[i + 1] < 0:                    # a genuine crossing in (φi,φi+1)
            frac = g[i] / (g[i] - g[i + 1])
            star = phi[i] + frac * (phi[i + 1] - phi[i])
            up = g[i + 1] > g[i]                    # F−φ increasing through 0
            fps.append({"phi_star": round(star, 4),
                        "stability": "unstable" if up else "stable",
                        "kind": "tipping" if up else "interior"})
    if F_vals[-1] >= 1.0 - 1e-9:
        fps.append({"phi_star": 1.0, "stability": "stable", "kind": "full-adoption"})
    return fps


def _classify(fps: list[dict]) -> str:
    stables = [f for f in fps if f["stability"] == "stable"]
    has_tip = any(f["stability"] == "unstable" for f in fps)
    if has_tip and len(stables) >= 2:
        return "bistable"                           # a genuine tipping point
    if not stables:
        return "degenerate"
    hi = max(f["phi_star"] for f in stables)
    if hi >= 0.5:
        return "monostable-high"                    # adoption grows to a high state
    return "monostable-low"                         # adoption decays to a low state


def _phase_block(cfg: FlyConfig, spot_pool, coord_mean, base_cost, sigma):
    """The fixed-point classification over the adoption-cost median grid, at one
    adoption-cost heterogeneity σ. base_cost is a per-consumer lognormal(0,σ)
    draw (median 1), scaled by each m_c."""
    rows, tipping = [], []
    for mc in cfg.adopt_cost_grid:
        costs = mc * base_cost
        F_vals = [adoption_response(spot_pool[phi] + coord_mean[phi], costs)
                  for phi in cfg.phi_grid]
        fps = fixed_points(cfg.phi_grid, F_vals)
        cls = _classify(fps)
        k_star = next((f["phi_star"] for f in fps
                       if f["stability"] == "unstable"), None)
        if k_star is not None:
            tipping.append(mc)
        rows.append({"adopt_cost_median": mc,
                     "F_by_phi": [round(v, 4) for v in F_vals],
                     "fixed_points": fps, "class": cls, "k_star": k_star})
    return {"adopt_cost_sigma": sigma, "rows": rows,
            "any_tipping_point": bool(tipping),
            "tipping_cost_band": [min(tipping), max(tipping)] if tipping else None}


def _phase_diagram(cfg: FlyConfig, spot_by_phi, coord_by_phi, seed0: int) -> dict:
    """Map the adoption fixed-point structure over BOTH the adoption-cost median
    AND its heterogeneity σ. The per-consumer edge e_i(φ)=e_shop_i(φ)+e_coord(φ)
    is the realized (measured) edge; the response is F(φ)=fraction with
    e_i(φ)>c_i. A tipping point k* is an UNSTABLE interior fixed point (below it
    adoption decays, above it the flywheel carries it up). Heterogeneity is swept
    because the standalone spot edge means a low-cost tail always adopts (F(0)>0),
    which — under realistic heterogeneity — erases the collapse-to-zero a tipping
    point needs."""
    spot_pool = {phi: np.concatenate(spot_by_phi[phi]) for phi in cfg.phi_grid}
    coord_mean = {phi: float(np.mean(coord_by_phi[phi])) for phi in cfg.phi_grid}
    N = len(next(iter(spot_pool.values())))
    # a base lognormal(0,1) shape drawn ONCE, re-scaled per σ so the same
    # consumers keep their relative cost rank across the σ-sweep
    rng = np.random.default_rng(substream(seed0, "adopt-cost"))
    z = rng.standard_normal(N)
    blocks = []
    any_tip = False
    for sigma in cfg.adopt_cost_sigmas:
        base_cost = np.exp(sigma * z)                # median 1, spread σ
        blk = _phase_block(cfg, spot_pool, coord_mean, base_cost, sigma)
        any_tip = any_tip or blk["any_tipping_point"]
        blocks.append(blk)
    return {
        "adopt_cost_grid": list(cfg.adopt_cost_grid),
        "adopt_cost_sigmas": list(cfg.adopt_cost_sigmas),
        "blocks": blocks,
        "any_tipping_point": bool(any_tip),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--pop", type=int, default=700)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = FlyConfig(seeds=args.seeds, pop_per_seed=args.pop)
    res = run_sweep(cfg, args.seed0)
    if args.out:
        with open(args.out, "w") as f:
            f.write(json.dumps(res, indent=1) + "\n")
        print(f"wrote {args.out}")
    q1 = res["Q1_edge_grows_with_phi"]
    print("\n=== Q1: does the agent edge grow with φ? ===")
    print(f"  φ grid:       {list(cfg.phi_grid)}")
    print(f"  E_total($):   {q1['E_total_by_phi']}")
    print(f"  E_shop($):    {q1['E_shop_by_phi']}")
    print(f"  E_coord($):   {q1['E_coord_by_phi']}")
    d = q1["delta_total_phi1_minus_phi0"]
    print(f"  Δedge(φ1−φ0): {d['mean']} CI {d['ci95']}  "
          f"{'GROWS' if q1['grows'] else 'SHRINKS' if q1['shrinks'] else 'FLAT (CI∋0)'}")
    print("\n  merchant margin/consumer (agent-mediated vs passive), by φ:")
    print(f"    agent:   {[c['merchant_margin_agent']['mean'] for c in res['cells']]}")
    print(f"    passive: {[c['merchant_margin_passive']['mean'] for c in res['cells']]}")
    ph = res["Q2_phase_diagram"]
    print("\n=== Q2: phase diagram (adoption fixed points over cost × heterogeneity) ===")
    for blk in ph["blocks"]:
        print(f"\n  adoption-cost σ = {blk['adopt_cost_sigma']}:")
        print(f"    {'m_c':>6} {'class':>16} {'k*':>7}")
        for r in blk["rows"]:
            print(f"    {r['adopt_cost_median']:>6} {r['class']:>16} "
                  f"{str(r['k_star']):>7}")
        print(f"    → tipping point: {blk['any_tipping_point']}"
              + (f" (m_c band {blk['tipping_cost_band']})"
                 if blk["any_tipping_point"] else ""))
    print(f"\n  ANY TIPPING POINT ANYWHERE: {ph['any_tipping_point']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

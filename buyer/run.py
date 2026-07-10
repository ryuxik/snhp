"""Paired runner — buyer-with-agent vs buyer-without, on the SAME buyers.

Pairing is keyed on BUYER IDENTITY, never on policy: every arm faces the
identical population and the identical merchant boards; only the buyer's
strategy differs. Every reported delta carries a 95% CI; no win is claimed when
the CI includes zero (buyer/stats.paired_ci).

  python3 -m buyer.run --phase b1 --n 4000 --seed 20260710
  python3 -m buyer.run --phase all --n 4000 --seed 20260710 --out buyer/results.json
"""
from __future__ import annotations

import argparse
import json
import sys

from buyer.agent import BuyerAgent, fallback_surplus
from buyer.frontier import (FrontierResult, Receipt, shop_frontier,
                            single_merchant_frontier)
from buyer.ledger import BuyerLedger
from buyer.merchant import Intent, Merchant
from buyer.stats import mean_ci, paired_ci
from buyer.values import best_bundle, bundle_surplus


# ── receipt builders (naive and agent share ONE frontier per buyer) ──────────

def naive_purchase(true_wtp, merchants: list[Merchant]):
    """What the naive sticker-accepter buys: best board bundle across merchants,
    or the competitor if that beats every board. Returns (merchant_id, sku, qty,
    unit_price, surplus). unit_price is the LIST price — naive pays sticker."""
    best = (None, None, 0, 0.0, 0.0)
    for m in merchants:
        board = m.board()
        prices = {s: b.list_price for s, b in board.items()}
        stock = {s: b.stock for s, b in board.items()}
        sku, qty, s = best_bundle(true_wtp, prices, stock)
        if sku is not None and s > best[4]:
            best = (m.merchant_id, sku, qty, prices[sku], s)
    return best


def naive_receipt(uid, true_wtp, walk_cost, merchants, frontier, *, day=0
                  ) -> Receipt:
    mid, sku, qty, price, s_stk = naive_purchase(true_wtp, merchants)
    _, _, s_out = best_bundle(true_wtp, merchants[0].outside_prices())
    s_out = max(0.0, s_out - walk_cost)
    if s_out >= s_stk:   # walking beats every board
        mid, sku, qty, price, realized = "outside", None, 0, 0.0, s_out
        list_price = 0.0
    else:
        realized = s_stk
        list_price = price
    return Receipt(uid=uid, merchant_id=mid, strategy="naive", sku=sku,
                   qty=qty, unit_price=price if sku else 0.0,
                   list_price=list_price, realized_surplus=round(realized, 6),
                   outside_surplus=round(frontier.fallback, 6),
                   frontier_surplus=round(frontier.surplus, 6),
                   regret=round(max(0.0, frontier.surplus - realized), 6), day=day)


def agent_receipt(agent: BuyerAgent, merchant: Merchant, frontier, *,
                  attested=False, day=0, label=None) -> Receipt:
    q, realized, strat = agent.negotiate(merchant, attested=attested)
    return Receipt(uid=agent.uid, merchant_id=(q.merchant_id if q else None),
                   strategy=label or strat, sku=(q.sku if q else None),
                   qty=(q.qty if q else 0), unit_price=(q.unit_price if q else 0.0),
                   list_price=(q.list_price if q else 0.0),
                   realized_surplus=round(realized, 6),
                   outside_surplus=round(frontier.fallback, 6),
                   frontier_surplus=round(frontier.surplus, 6),
                   regret=round(max(0.0, frontier.surplus - realized), 6), day=day)


# ── phase B1 + B2: single-merchant paired run ────────────────────────────────

def run_single_merchant(master_seed: int, n: int, *, cfg=None,
                        merchant_spec: dict | None = None, friction: float = 0.0,
                        attested: bool = False) -> dict:
    from buyer.world import draw_vend_population, vend_merchants
    spec = merchant_spec or {"id": "vend-00"}
    if attested:
        spec = {**spec, "attested_only": True}
    merchant = vend_merchants(master_seed, [spec])[0]
    pop = draw_vend_population(master_seed, n, cfg=cfg)

    naive_L, agent_L = BuyerLedger(), BuyerLedger()
    d_surplus, d_regret = [], []
    for b in pop:
        fr = single_merchant_frontier(b.wtp, b.walk_cost, merchant,
                                      friction=friction, attested=attested)
        nr = naive_receipt(b.uid, b.wtp, b.walk_cost, [merchant], fr)
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost, policy="honest",
                           friction=friction)
        ar = agent_receipt(agent, merchant, fr, attested=attested)
        naive_L.record(nr)
        agent_L.record(ar)
        d_surplus.append(ar.realized_surplus - nr.realized_surplus)
        d_regret.append(ar.regret - nr.regret)

    return _summarize(naive_L, agent_L, d_surplus, d_regret,
                      extra={"attested": attested, "friction": friction,
                             "n": n, "seed": master_seed})


# ── phase B3: multi-merchant SHOP and TIME ───────────────────────────────────

def _multi_merchant_specs(m: int) -> list[dict]:
    """M vend machines that compete on PRICE only: identical cost/stock
    structure (same fresh catalog, no glut, same day/tick), differing solely by
    the operator's calibration-noise draw (seed offset) — so each posts a
    slightly different sticker and the Nash quotes differ. This isolates SHOP as
    price competition (a transfer test); allocative/spoilage growth is the
    separate TIME and COMMIT story, kept out of here on purpose."""
    return [{"id": f"vend-{i:02d}", "seed_offset": i * 101,
             "day": 0, "tick": 40,
             "cfg_kwargs": {"sigma_cal": 0.30}} for i in range(m)]


def run_shop(master_seed: int, n: int, *, m: int = 3, cfg=None,
             friction: float = 0.0, attested: bool = False) -> dict:
    from buyer.frontier import shop_frontier
    from buyer.strategies import (buyer_surplus_of, joint_value_of, shop)
    from buyer.world import draw_vend_population, vend_merchants
    merchants = vend_merchants(master_seed, _multi_merchant_specs(m))
    pop = draw_vend_population(master_seed, n, cfg=cfg)

    base_L, shop_L = BuyerLedger(), BuyerLedger()
    d_surplus, d_regret, d_joint, d_buyer_deal = [], [], [], []
    for b in pop:
        fr = shop_frontier(b.wtp, b.walk_cost, merchants, friction=friction,
                           attested=attested)
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost, friction=friction)
        # baseline: single merchant (merchant 0) only
        q0, r0, _ = agent.negotiate(merchants[0], attested=attested)
        # shop: query all M, take best
        sr = shop(agent, merchants, attested=attested)
        base_L.record(_deal_receipt(b.uid, q0, r0, fr, "single_merchant"))
        shop_L.record(_deal_receipt(b.uid, sr.quote, sr.realized, fr, "shop"))
        d_surplus.append(sr.realized - r0)
        d_regret.append((fr.surplus - sr.realized) - (fr.surplus - r0))
        # transfer vs growth, on buyers who transact in BOTH arms
        if q0 is not None and sr.quote is not None:
            d_joint.append(joint_value_of(b.wtp, sr.quote)
                           - joint_value_of(b.wtp, q0))
            d_buyer_deal.append(buyer_surplus_of(b.wtp, sr.quote, friction)
                                - buyer_surplus_of(b.wtp, q0, friction))

    s = _summarize(base_L, shop_L, d_surplus, d_regret,
                   extra={"n": n, "m": m, "attested": attested,
                          "friction": friction, "seed": master_seed})
    s["transfer_vs_growth"] = {
        "delta_buyer_surplus_on_deals": paired_ci(d_buyer_deal),
        "delta_joint_value_on_deals": paired_ci(d_joint),
        "n_deals_both_arms": len(d_joint)}
    return s


def run_time(master_seed: int, n: int, *, cfg=None, glut_prob: float = 0.15,
             wait_cost: float = 0.15, friction: float = 0.0,
             attested: bool = False) -> dict:
    import numpy as np
    from buyer.strategies import (buyer_surplus_of, joint_value_of,
                                  time_strategy)
    from buyer.world import (draw_vend_population, vend_markdown_merchant,
                            vend_merchants)
    from vend.core import substream
    now_m = vend_merchants(master_seed, [{"id": "vend-now"}])[0]
    glut_m = vend_markdown_merchant(master_seed, cfg=cfg)
    pop = draw_vend_population(master_seed, n, cfg=cfg)

    buynow_L, time_L = BuyerLedger(), BuyerLedger()
    d_surplus, d_regret, d_joint, d_buyer_deal = [], [], [], []
    n_deferred = 0
    for b in pop:
        # this buyer's realized future: does it glut? (seeded on identity)
        glut = float(np.random.default_rng(
            substream(master_seed, "glut_real", b.uid)).random()) < glut_prob
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost, friction=friction)
        q_now, r_now, _ = agent.negotiate(now_m, attested=attested)
        tr = time_strategy(agent, now_m, glut_m, glut_prob=glut_prob,
                           wait_cost=wait_cost, glut_happens=glut,
                           attested=attested)
        n_deferred += int(tr.deferred)
        # per-buyer frontier = hindsight best of {now, realized future}
        frontier = tr.hindsight
        buynow_L.record(_flat_receipt(b.uid, q_now, r_now, frontier, "buy_now"))
        time_L.record(_flat_receipt(b.uid, tr.quote, tr.realized, frontier, "time"))
        d_surplus.append(tr.realized - r_now)
        d_regret.append((frontier - tr.realized) - (frontier - r_now))
        if q_now is not None and tr.quote is not None:
            d_joint.append(joint_value_of(b.wtp, tr.quote)
                           - joint_value_of(b.wtp, q_now))
            d_buyer_deal.append(buyer_surplus_of(b.wtp, tr.quote, friction)
                                - buyer_surplus_of(b.wtp, q_now, friction))

    s = _summarize(buynow_L, time_L, d_surplus, d_regret,
                   extra={"n": n, "glut_prob": glut_prob, "wait_cost": wait_cost,
                          "attested": attested, "seed": master_seed})
    s["defer_rate"] = round(n_deferred / max(1, n), 4)
    s["transfer_vs_growth"] = {
        "delta_buyer_surplus_on_deals": paired_ci(d_buyer_deal),
        "delta_joint_value_on_deals": paired_ci(d_joint),
        "n_deals_both_arms": len(d_joint)}
    return s


# ── the human vs agent-mediated regime (subsumes task #60) ───────────────────

def run_regime(master_seed: int, n: int, *, cfg=None, m: int = 3,
               human_friction: float = 0.30) -> dict:
    """Headline: buyer surplus and regret in the HUMAN regime vs the
    AGENT-MEDIATED target world.

      HUMAN            quote_friction > 0 (a mental switch-cost per negotiated
                       transaction) and NO churn (sticky to one merchant — a
                       human doesn't shop every machine). Negotiates honestly at
                       merchant 0 only.
      AGENT-MEDIATED   friction → 0 (agents evaluate a quote instantly) and fast
                       churn (the agent queries every merchant). Shops all M.

    Both are graded against the SAME yardstick: the agent-mediated frontier
    (shop across M, friction 0) — so regret shows how far each regime sits from
    the reachable ceiling."""
    from buyer.frontier import shop_frontier
    from buyer.strategies import shop
    from buyer.world import draw_vend_population, vend_merchants
    merchants = vend_merchants(master_seed, _multi_merchant_specs(m))
    pop = draw_vend_population(master_seed, n, cfg=cfg)

    human_real, human_reg, agent_real, agent_reg = [], [], [], []
    frontier, d_surplus = [], []
    for b in pop:
        fr = shop_frontier(b.wtp, b.walk_cost, merchants, friction=0.0)
        frontier.append(fr.surplus)
        # HUMAN: single merchant, friction, no shopping
        human = BuyerAgent(b.uid, b.wtp, b.walk_cost, friction=human_friction)
        _, r_h, _ = human.negotiate(merchants[0])
        # AGENT-MEDIATED: friction 0, shop all merchants
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost, friction=0.0)
        r_a = shop(agent, merchants).realized
        human_real.append(r_h); human_reg.append(max(0.0, fr.surplus - r_h))
        agent_real.append(r_a); agent_reg.append(max(0.0, fr.surplus - r_a))
        d_surplus.append(r_a - r_h)

    return {
        "n": n, "m": m, "human_friction": human_friction,
        "frontier_mean": mean_ci(frontier)["mean"],
        "human_surplus": mean_ci(human_real), "human_regret": mean_ci(human_reg),
        "agent_surplus": mean_ci(agent_real), "agent_regret": mean_ci(agent_reg),
        "delta_surplus_agent_minus_human": paired_ci(d_surplus),
        "seed": master_seed,
    }


# ── phase B5: COORDINATE + the buyer-side monopsony audit ────────────────────

def run_coordinate(master_seed: int, n: int, *, cfg=None, target: str = "sandwich",
                   p_spoil: float = 0.40, ks=(2, 5, 10, 20),
                   scarcity: float = 0.5) -> dict:
    """Cluster K buyers into one aggregate commitment for the merchant's scarce,
    spoil-risk stock, and run the PRE-REGISTERED monopsony audit — the RealPage
    mirror on the buyer side.

    Growth prediction: coordination beats independent commits because it MATCHES
    the scarce stock to the buyers who value it most.
    Audit (binding): buyer coordination must NOT (A) push total surplus below the
    independent baseline, nor (B) extract below the merchant's participation
    floor. Both are checked; the floor's load-bearing role is shown by an
    over-reach counterfactual."""
    import numpy as np
    from buyer.strategies import coordinate
    from buyer.world import draw_vend_population
    from vend.world import CATALOG_SPEC
    salvage = {s: salv for s, _mu, _c, salv, *_ in CATALOG_SPEC}[target]
    pop = draw_vend_population(master_seed, n, cfg=cfg)
    vals = [b.wtp[target] for b in pop]

    sweep = {}
    for k in ks:
        s_risk = max(1, int(round(k * scarcity)))
        indep_g, fair_g, mono_g, over_g = [], [], [], []
        fair_merch, mono_merch = [], []
        over_participation_fail = 0
        over_spoiled = 0
        clusters = 0
        for c in range(0, (len(vals) // k) * k, k):
            grp = vals[c:c + k]
            seed = (master_seed * 131 + c) & 0x7FFFFFFF
            indep = coordinate(grp, salvage=salvage, s_risk=s_risk,
                               p_spoil=p_spoil, extraction=0.5,
                               allocation="random", seed=seed)
            fair = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=0.5,
                              allocation="efficient")
            mono = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.0,
                              allocation="efficient")
            over = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.2,
                              allocation="efficient")
            indep_g.append(indep.total_growth / k)
            fair_g.append(fair.total_growth / k)
            mono_g.append(mono.total_growth / k)
            over_g.append(over.total_growth / k)
            fair_merch.append(fair.merchant_margin)
            mono_merch.append(mono.merchant_margin)
            over_participation_fail += int(not over.participation_ok)
            over_spoiled += over.spoiled_by_overreach
            clusters += 1
        sweep[k] = {
            "s_risk": s_risk, "clusters": clusters,
            "indep_growth_pc": mean_ci(indep_g),
            "coord_fair_growth_pc": mean_ci(fair_g),
            "coord_monopsony_growth_pc": mean_ci(mono_g),
            "d_coord_minus_indep": paired_ci(
                [f - i for f, i in zip(fair_g, indep_g)]),
            "fair_merchant_margin_min": round(min(fair_merch), 6),
            "monopsony_merchant_margin_min": round(min(mono_merch), 6),
            "overreach_participation_fail_frac": round(
                over_participation_fail / max(1, clusters), 4),
            "overreach_welfare_pc": mean_ci(over_g),
            "overreach_units_spoiled": over_spoiled,
        }

    # ── the binding audit verdict ──
    checks = {}
    checks["A_coord_not_below_indep"] = all(
        sweep[k]["d_coord_minus_indep"]["mean"] >= -1e-9 for k in ks)
    checks["B_participation_floor_holds"] = all(
        sweep[k]["fair_merchant_margin_min"] >= -1e-9
        and sweep[k]["monopsony_merchant_margin_min"] >= -1e-9 for k in ks)
    checks["D_overreach_is_self_defeating"] = all(
        sweep[k]["overreach_welfare_pc"]["mean"]
        <= sweep[k]["coord_monopsony_growth_pc"]["mean"] + 1e-9 for k in ks)
    verdict = ("PASS — buyer coordination under our mechanism does not reduce "
               "total surplus and cannot extract below the merchant's "
               "participation floor"
               if checks["A_coord_not_below_indep"]
               and checks["B_participation_floor_holds"]
               and checks["D_overreach_is_self_defeating"]
               else "FAIL — see checks")
    return {"n": n, "target": target, "p_spoil": p_spoil, "scarcity": scarcity,
            "ks": list(ks), "sweep": sweep, "audit_checks": checks,
            "audit_verdict": verdict, "seed": master_seed}


# ── phase B4: Wallet + COMMIT ────────────────────────────────────────────────

def run_commit(master_seed: int, n: int, *, cfg=None, p_spoil: float = 0.40,
               rounds: int = 6) -> dict:
    from buyer.strategies import commit_strategy
    from buyer.wallet import Wallet
    from buyer.world import draw_vend_population, vend_markdown_merchant
    m_A = vend_markdown_merchant(master_seed, cfg=cfg, merchant_id="vend-A")
    m_B = vend_markdown_merchant(master_seed + 777, cfg=cfg, merchant_id="vend-B")
    pop = draw_vend_population(master_seed, n, cfg=cfg)

    r1_joint, r1_buyer, r1_var = [], [], []      # newcomer (attested, tf=0.5)
    rR_joint, rR_buyer, rR_var, rR_tf = [], [], [], []   # proven (tf→1)
    port_carried, port_fresh = [], []            # cross-merchant portability
    committers = 0
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        wallet = Wallet(uid=b.uid, attested=True, reliability=0.0)
        first = None
        for rd in range(rounds):
            cr = commit_strategy(agent, m_A, p_spoil=p_spoil, wallet=wallet)
            if not cr.committed:
                break
            if rd == 0:
                first = cr
            last = cr
            wallet.fulfilled()          # the agent controls demand → it keeps it
        else:
            committers += 1
            r1_joint.append(first.d_joint); r1_buyer.append(first.d_buyer)
            r1_var.append(first.var_reduction)
            rR_joint.append(last.d_joint); rR_buyer.append(last.d_buyer)
            rR_var.append(last.var_reduction); rR_tf.append(last.trusted_frac)
            # portability: the SAME (now-proven) wallet at a NEW merchant B,
            # vs a fresh attested newcomer wallet at B.
            cr_carry = commit_strategy(agent, m_B, p_spoil=p_spoil, wallet=wallet)
            cr_fresh = commit_strategy(agent, m_B, p_spoil=p_spoil,
                                       wallet=Wallet(uid=b.uid, attested=True))
            if cr_carry.committed and cr_fresh.committed:
                port_carried.append(cr_carry.d_buyer)
                port_fresh.append(cr_fresh.d_buyer)

    import numpy as np
    return {
        "n": n, "committers": committers, "p_spoil": p_spoil, "rounds": rounds,
        "newcomer_joint_growth": mean_ci(r1_joint),
        "newcomer_buyer_share": mean_ci(r1_buyer),
        "newcomer_var_reduction": round(float(np.mean(r1_var)) if r1_var else 0, 4),
        "proven_joint_growth": mean_ci(rR_joint),
        "proven_buyer_share": mean_ci(rR_buyer),
        "proven_var_reduction": round(float(np.mean(rR_var)) if rR_var else 0, 4),
        "proven_trusted_frac": round(float(np.mean(rR_tf)) if rR_tf else 0, 4),
        "split_is_5050": True,   # ΔBuyer == ΔMerchant == Δjoint/2 by construction
        "portability_buyer_gain": paired_ci(
            [c - f for c, f in zip(port_carried, port_fresh)]),
        "seed": master_seed,
    }


def _deal_receipt(uid, quote, realized, frontier, strategy) -> Receipt:
    return Receipt(uid=uid, merchant_id=(quote.merchant_id if quote else None),
                   strategy=strategy, sku=(quote.sku if quote else None),
                   qty=(quote.qty if quote else 0),
                   unit_price=(quote.unit_price if quote else 0.0),
                   list_price=(quote.list_price if quote else 0.0),
                   realized_surplus=round(realized, 6),
                   outside_surplus=round(frontier.fallback, 6),
                   frontier_surplus=round(frontier.surplus, 6),
                   regret=round(max(0.0, frontier.surplus - realized), 6))


def _flat_receipt(uid, quote, realized, frontier_val, strategy) -> Receipt:
    return Receipt(uid=uid, merchant_id=(quote.merchant_id if quote else None),
                   strategy=strategy, sku=(quote.sku if quote else None),
                   qty=(quote.qty if quote else 0),
                   unit_price=(quote.unit_price if quote else 0.0),
                   list_price=(quote.list_price if quote else 0.0),
                   realized_surplus=round(realized, 6), outside_surplus=0.0,
                   frontier_surplus=round(frontier_val, 6),
                   regret=round(max(0.0, frontier_val - realized), 6))


def _summarize(naive_L: BuyerLedger, agent_L: BuyerLedger,
               d_surplus, d_regret, *, extra=None) -> dict:
    n = len(agent_L.all_rows())
    naive_regret = [r.regret for r in naive_L.all_rows()]
    agent_regret = [r.regret for r in agent_L.all_rows()]
    naive_real = [r.realized_surplus for r in naive_L.all_rows()]
    agent_real = [r.realized_surplus for r in agent_L.all_rows()]
    frontier = [r.frontier_surplus for r in agent_L.all_rows()]
    fbar = sum(frontier) / n if n else 0.0
    # regret as a fraction of frontier: how much of the reachable surplus each
    # arm leaves on the table.
    agent_capture = (1 - sum(agent_regret) / sum(frontier)) if sum(frontier) else None
    naive_capture = (1 - sum(naive_regret) / sum(frontier)) if sum(frontier) else None
    out = {
        "n": n,
        "frontier_mean": round(fbar, 4),
        "naive_surplus": mean_ci(naive_real),
        "agent_surplus": mean_ci(agent_real),
        "naive_regret": mean_ci(naive_regret),
        "agent_regret": mean_ci(agent_regret),
        "naive_capture_frac": round(naive_capture, 4) if naive_capture is not None else None,
        "agent_capture_frac": round(agent_capture, 4) if agent_capture is not None else None,
        "delta_surplus_agent_minus_naive": paired_ci(d_surplus),
        "delta_regret_agent_minus_naive": paired_ci(d_regret),
        "ledger_conserves": agent_L.conserves() and naive_L.conserves(),
    }
    if extra:
        out.update(extra)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_summary(tag: str, s: dict) -> None:
    print(f"\n=== {tag} (n={s['n']}) ===")
    print(f"  frontier/buyer      {s['frontier_mean']}")
    print(f"  naive  surplus      {s['naive_surplus']['mean']}  "
          f"regret {s['naive_regret']['mean']}  "
          f"capture {s['naive_capture_frac']}")
    print(f"  agent  surplus      {s['agent_surplus']['mean']}  "
          f"regret {s['agent_regret']['mean']}  "
          f"capture {s['agent_capture_frac']}")
    ds = s["delta_surplus_agent_minus_naive"]
    dr = s["delta_regret_agent_minus_naive"]
    print(f"  Δsurplus agent−naive {ds['mean']}  CI95 {ds['ci95']}  "
          f"{'SIG' if ds['significant'] else 'ns'}")
    print(f"  Δregret  agent−naive {dr['mean']}  CI95 {dr['ci95']}  "
          f"{'SIG' if dr['significant'] else 'ns'}")
    print(f"  ledger conserves: {s['ledger_conserves']}")


def _print_transfer(tag: str, s: dict) -> None:
    tg = s.get("transfer_vs_growth")
    if not tg:
        return
    db = tg["delta_buyer_surplus_on_deals"]
    dj = tg["delta_joint_value_on_deals"]
    verdict = ("GROWTH" if dj["significant"] and dj["mean"] > 0
               else "TRANSFER" if db["significant"] else "no effect")
    print(f"  [{tag}] Δbuyer/deal {db['mean']} CI{db['ci95']} · "
          f"Δjoint/deal {dj['mean']} CI{dj['ci95']} → {verdict} "
          f"(n_deals={tg['n_deals_both_arms']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="b1",
                    choices=["b1", "b2", "b3", "b4", "b5", "regime", "all"])
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    results = {}
    if args.phase in ("b1", "b2", "all"):
        s = run_single_merchant(args.seed, args.n, attested=False)
        _print_summary("B1/B2 single-merchant, unattested (unrestricted frontier)", s)
        results["single_merchant_unattested"] = s
        sa = run_single_merchant(args.seed, args.n, attested=True)
        _print_summary("B2 single-merchant, ATTESTED (frontier=honest)", sa)
        results["single_merchant_attested"] = sa

    if args.phase in ("b3", "all"):
        sh = run_shop(args.seed, args.n, m=3)
        _print_summary("B3 SHOP (3 merchants) vs single-merchant", sh)
        _print_transfer("SHOP", sh)
        results["shop"] = sh
        tm = run_time(args.seed, args.n)
        _print_summary("B3 TIME (defer for glut) vs buy-now", tm)
        print(f"  defer rate: {tm['defer_rate']}")
        _print_transfer("TIME", tm)
        results["time"] = tm

    if args.phase in ("b4", "all"):
        cm = run_commit(args.seed, args.n)
        print(f"\n=== B4 COMMIT + Wallet (n={cm['n']}, committers={cm['committers']}, "
              f"p_spoil={cm['p_spoil']}) ===")
        print(f"  newcomer (attested, tf=0.5): joint growth "
              f"{cm['newcomer_joint_growth']['mean']} CI"
              f"{cm['newcomer_joint_growth']['ci95']}  "
              f"buyer share {cm['newcomer_buyer_share']['mean']}  "
              f"var-reduction {cm['newcomer_var_reduction']}")
        print(f"  proven   (tf={cm['proven_trusted_frac']}):       joint growth "
              f"{cm['proven_joint_growth']['mean']} CI"
              f"{cm['proven_joint_growth']['ci95']}  "
              f"buyer share {cm['proven_buyer_share']['mean']}  "
              f"var-reduction {cm['proven_var_reduction']}")
        pg = cm["portability_buyer_gain"]
        print(f"  portability (carried wallet − fresh, at NEW merchant): "
              f"{pg['mean']} CI{pg['ci95']} {'SIG' if pg['significant'] else 'ns'}")
        print(f"  split ΔBuyer==ΔMerchant (Nash 50/50): {cm['split_is_5050']}")
        results["commit"] = cm

    if args.phase in ("regime", "all"):
        rg = run_regime(args.seed, args.n)
        print(f"\n=== HUMAN vs AGENT-MEDIATED regime (n={rg['n']}, "
              f"frontier/buyer={rg['frontier_mean']}) ===")
        print(f"  HUMAN (friction=${rg['human_friction']}, no churn/1 merchant): "
              f"surplus {rg['human_surplus']['mean']}  regret {rg['human_regret']['mean']}")
        print(f"  AGENT (friction=$0, shop {rg['m']} merchants):            "
              f"surplus {rg['agent_surplus']['mean']}  regret {rg['agent_regret']['mean']}")
        ds = rg["delta_surplus_agent_minus_human"]
        print(f"  Δsurplus agent−human {ds['mean']} CI{ds['ci95']} "
              f"{'SIG' if ds['significant'] else 'ns'}")
        results["regime_human_vs_agent"] = rg

    if args.phase in ("b5", "all"):
        co = run_coordinate(args.seed, args.n)
        print(f"\n=== B5 COORDINATE + monopsony audit (n={co['n']}, "
              f"target={co['target']}, p_spoil={co['p_spoil']}, "
              f"scarcity={co['scarcity']}) ===")
        for k in co["ks"]:
            sw = co["sweep"][k]
            dd = sw["d_coord_minus_indep"]
            print(f"  K={k:>2} (stock={sw['s_risk']}): coord growth/buyer "
                  f"{sw['coord_fair_growth_pc']['mean']} vs indep "
                  f"{sw['indep_growth_pc']['mean']}  Δ {dd['mean']} "
                  f"CI{dd['ci95']} {'SIG' if dd['significant'] else 'ns'}  | "
                  f"merch floor min: fair {sw['fair_merchant_margin_min']}, "
                  f"monopsony {sw['monopsony_merchant_margin_min']}  | "
                  f"overreach: {sw['overreach_participation_fail_frac']} clusters "
                  f"breach → {sw['overreach_units_spoiled']} units spoiled")
        print(f"  audit checks: {co['audit_checks']}")
        print(f"  VERDICT: {co['audit_verdict']}")
        results["coordinate_audit"] = co

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

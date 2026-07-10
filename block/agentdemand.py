"""Agent-mediated block demand — the buyer/ ⇄ block/ convergence (task #62).

This is the definitive internal-consistency test for the business model. The
block modelled PASSIVE-WTP consumers (a draw that accepts/declines a single
brokered quote at its home venue). buyer/ built an AGENT that shops, times,
commits and coordinates. The block IS the multi-merchant world that agent was
built for. Here they run in ONE world, and we measure the

    BUSINESS-MODEL ANTAGONISM TEST (Bezos & Musk r2 critique):

the buyer's agent, working as designed, competes merchant margin DOWN via
shopping (buyer/RESULTS: SHOP is a pure TRANSFER); but the merchant-side
gain-share revenue NEEDS merchant margin UP. These two halves had never been
run in one world. Do they pull margin to the floor (killing gain-share), or do
the growth levers (commit/coordinate = pie growth) keep merchant margin
positive?

Two deliverables, both paired on buyer identity (never on policy), CIs on every
delta, no win claim when a CI spans zero:

  A. PER-VENUE $/day margin under PASSIVE vs AGENT-MEDIATED demand, with REAL
     block stock dynamics — via the committed runner and a gated street
     resolver (`resolve_shopper_agentic`). This is where the transfer bites and
     where "merchants earned" can go negative. The passive→adopt→bertrand
     ladder isolates the pure cross-merchant competition (the transfer).

  B. The clean transfer-vs-growth SPLIT on the BLOCK's own NYC calibration,
     reusing buyer/strategies verbatim against block merchants: COMMIT and
     COORDINATE grow the pie (Δjoint>0, 50/50, margin ≥ floor); the human vs
     agent-mediated regime knobs (friction→0, shop) on block merchants.

Layering: this module depends on the committed block venue adapters (which wrap
vend/boba/… verbatim) and reads vend/ read-only (never edits it). The runner's
default (agent_demand="off") path never imports this module, so every committed
passive artifact stays byte-exact.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from block import calibration, population
from block.ledger import BlockLedger
from block.venues import BlockConfig, build_block_catalog
from vend.world import best_bundle as vend_best_bundle, bundle_value as vend_value


# ══════════════════════════════════════════════════════════════════════════
# A. the agent-mediated STREET resolver (called by block.runner when
#    cfg.agent_demand != "off"; SNHP world, vending+bodega lane only)
# ══════════════════════════════════════════════════════════════════════════

def _believed_outside_surplus(disclosed: dict, believed_prices: dict) -> float:
    """Buyer's surplus at a merchant's BELIEVED outside board (the same
    `outside_surplus` computation vend.scenario runs, replicated here so we can
    INVERT it to inject a competing offer as the disagreement point)."""
    _, _, s = vend_best_bundle(disclosed, believed_prices)
    return max(0.0, s)


def _at_floor_max_offer(state, catalog, disc: dict, walk: float) -> float:
    """The buyer's MAX net surplus a merchant could credibly offer under
    competition: it prices any stocked SKU down to its own floor (c_eff — a
    merchant takes a sale at margin 0 over losing it to a rival). = max over
    (sku, qty) of value − qty·c_eff − walk. This is the rival's credible
    Bertrand threat — the correct disagreement point a shopping agent extracts,
    NOT the rival's cooperative Nash offer (which the winner already beats)."""
    from vend.scenario import c_eff
    from vend.world import QTY_CAP
    best = 0.0
    for sku in catalog:
        st = state.stock(sku)
        if st <= 0 or sku not in disc:
            continue
        floor = c_eff(state, sku)
        for qty in range(1, min(QTY_CAP, st) + 1):
            s = vend_value(disc, sku, qty) - qty * floor - walk
            if s > best:
                best = s
    return best


def _quote_at_outside(venue, disclosed: dict, x_at_counter: float, kind: str):
    """Re-quote `venue` forcing the buyer's disagreement (at-counter surplus)
    to `x_at_counter`. vend prices the buyer toward their outside option; a
    shopping agent that holds a rival's credible Bertrand threat presents it AS
    that outside. We encode it exactly by choosing the disclosed walk so vend's
    internal `outside = max(0, s_believed − walk) == x_at_counter` (the rival's
    at-floor offer IS the credible outside — no misreport of the buyer's WTP).
    The venue still applies its own symmetric-Nash split above the raised
    disagreement, so the buyer keeps the rival's floor offer PLUS half the
    residual gain — competition, then cooperative bargaining on what's left."""
    if kind == "vending":
        believed = {s: venue.catalog[s].bodega_price for s in venue.catalog}
        disc = {s: disclosed[s] for s in venue.catalog}
    else:                                   # adopted bodega
        believed = {s: venue.catalog[s].bodega_price for s in venue.prices}
        disc = {s: disclosed[s] for s in venue.prices}
    s_believed = _believed_outside_surplus(disc, believed)
    walk = s_believed - max(0.0, x_at_counter)
    # Verify the inversion actually held. vend prices the buyer toward
    #   outside = max(0, outside_surplus(disc, walk, catalog))
    # as the disagreement point (vend.scenario.nash_quote); we chose `walk` so
    # that equals the threat we inject (x_at_counter). Recompute it through
    # vend's OWN formula (not our algebra) so a future change to vend's
    # disagreement math trips here loudly instead of silently drifting the
    # antagonism numbers. Only checkable when the buyer HAS a positive believed
    # outside: with none (s_believed==0) vend's outside is 0 regardless of walk
    # and the injection is a no-op.
    if s_believed > 1e-12:
        from vend.scenario import outside_surplus as _vend_outside
        cat = {s: venue.catalog[s] for s in disc}
        realized = max(0.0, _vend_outside(disc, walk, cat))
        assert abs(realized - max(0.0, x_at_counter)) < 1e-9, (
            f"outside inversion drifted: injected {x_at_counter!r} but vend's "
            f"disagreement math yields {realized!r}")
    return venue.quote(disc, walk)


def resolve_shopper_agentic(world, sh, vend_v, bodega, ledger, day, tick, cfg):
    """The buyer's-agent street resolution (task #62). The SAME shopper the
    passive block resolves as a single-quote accept/decline is here an AGENT
    that (1) SHOPS both brokered merchants and (2) under "bertrand" plays them
    off — one competitive best-response round, each merchant re-quoting to beat
    the rival's offer. Settles through the committed venue helpers so stock,
    the ledger and every conservation law behave exactly as the passive path.

    cfg.agent_demand: "shop" (take best of the two INDEPENDENT quotes) |
    "bertrand" (+ the competitive round). cfg.agent_friction: $ switch-cost the
    agent pays to accept a NEGOTIATED quote (0 in the agent regime)."""
    from block.runner import (_settle_vending, _settle_bodega,
                              _settle_bodega_quote)
    base = {"world": world, "day": day, "tick": tick, "uid": sh.uid,
            "persona": sh.persona, "kind": "street"}
    ledger.record({"type": "arrival", "home": sh.home, **base})

    walk_v = 0.0 if sh.home == "vending" else sh.cross_walk
    walk_b = 0.0 if sh.home == "bodega" else sh.cross_walk
    fr = cfg.agent_friction

    # posted alternatives (real, stock-capped) — the always-available fallback
    b_item = b_qty = None
    b_raw = 0.0
    u_bodega = float("-inf")
    if bodega is not None:
        b_item, b_qty, b_raw = population_best(sh.wtp, bodega.price_board(),
                                               bodega.stock_view())
        u_bodega = (b_raw - walk_b) if b_item is not None else float("-inf")
    v_sku = v_qty = None
    v_raw = 0.0
    v_prices: dict = {}
    board = {}
    u_board = float("-inf")
    if vend_v is not None:
        board = vend_v.price_board()
        v_prices = {s: p for s, (p, _w) in board.items()}
        v_stock = {s: vend_v.state.stock(s) for s in v_prices}
        v_sku, v_qty, v_raw = population_best(sh.wtp, v_prices, v_stock)
        u_board = (v_raw - walk_v) if v_sku is not None else float("-inf")

    # round-0 brokered quotes at the buyer's TRUE relative outside
    disc_v = {s: sh.wtp[s] for s in vend_v.catalog} if vend_v is not None else {}
    nqv = vend_v.quote(disc_v, walk_b - walk_v) if vend_v is not None else None
    disc_b = {s: sh.wtp[s] for s in bodega.prices} \
        if (bodega is not None and bodega.adopted) else {}
    nqb = bodega.quote(disc_b, walk_v - walk_b) \
        if (bodega is not None and bodega.adopted) else None

    def net(nq, walk):
        if nq is None or nq.outcome is None:
            return float("-inf")
        o = nq.outcome
        return vend_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price - walk - fr

    # BERTRAND: cross-merchant competition. Each brokered merchant re-quotes
    # against the RIVAL'S CREDIBLE AT-FLOOR THREAT (the most a shopping agent
    # can extract elsewhere — the rival will price to its own floor to win the
    # sale rather than lose it). Raising the disagreement to the rival's at-floor
    # offer, then Nash-splitting the residual, competes the winner's margin down
    # exactly where the two boards OVERLAP (a rival with a strong at-floor offer
    # for the same buyer forces a deep cut); where they are differentiated (only
    # cola/chips overlap) the rival's threat is weak and margin holds — the
    # honest, mechanical reason the transfer is confined to the commodity slice.
    if (cfg.agent_demand == "bertrand" and vend_v is not None
            and bodega is not None and bodega.adopted):
        threat_v = _at_floor_max_offer(bodega.state, bodega.catalog, disc_b, walk_b)
        threat_b = _at_floor_max_offer(vend_v.state, vend_v.catalog, disc_v, walk_v)
        if nqv is not None and nqv.outcome is not None:
            s_v0 = net(nqv, walk_v)
            nqv2 = _quote_at_outside(vend_v, disc_v, threat_v + walk_v + fr, "vending")
            if net(nqv2, walk_v) >= s_v0 - 1e-9:
                nqv = nqv2
        if nqb is not None and nqb.outcome is not None:
            s_b0 = net(nqb, walk_b)
            nqb2 = _quote_at_outside(bodega, disc_b, threat_b + walk_b + fr, "bodega")
            if net(nqb2, walk_b) >= s_b0 - 1e-9:
                nqb = nqb2

    # assemble candidates in fixed precedence (deterministic ties: vending
    # nego, bodega nego, vending board, bodega board — a superset of the
    # passive chain, so with no bodega quote and "shop" this reduces to it)
    cands = []                       # (net_util, kind, payload)
    if nqv is not None and nqv.outcome is not None:
        cands.append((net(nqv, walk_v), "vnego", nqv))
    if nqb is not None and nqb.outcome is not None:
        cands.append((net(nqb, walk_b), "bnego", nqb))
    if v_sku is not None:
        cands.append((u_board, "vpost", (v_sku, v_qty)))
    if b_item is not None:
        cands.append((u_bodega, "bpost", (b_item, b_qty)))

    best_u, kind, payload = 0.0, None, None
    for u, k, pl in cands:
        if u > best_u:               # strict: ties keep the earlier candidate
            best_u, kind, payload = u, k, pl

    if kind is None:
        ledger.record({"type": "no_sale", **base})
        return
    if kind == "vnego":
        o = payload.outcome
        raw = vend_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price
        _settle_vending(vend_v, ledger, base, o.sku, o.qty, o.unit_price,
                        payload.why, best_u, raw, walk_v, negotiated=True)
    elif kind == "bnego":
        o = payload.outcome
        raw = vend_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price
        _settle_bodega_quote(bodega, ledger, base, o.sku, o.qty, o.unit_price,
                             payload.why, best_u, raw, walk_b)
    elif kind == "vpost":
        sku, qty = payload
        _settle_vending(vend_v, ledger, base, sku, qty, v_prices[sku],
                        board[sku][1], u_board, v_raw, walk_v, negotiated=False)
    else:
        item, qty = payload
        _settle_bodega(bodega, ledger, base, item, qty, u_bodega, b_raw, walk_b)


def population_best(wtp, prices, stock=None):
    """vend's stock-capped chooser — same as runner._resolve_shopper uses
    (imported here to avoid a runner import cycle at module load)."""
    from vend.world import best_bundle
    return best_bundle(wtp, prices, stock)


# ══════════════════════════════════════════════════════════════════════════
# B. the clean transfer-vs-growth split on block calibration (buyer/strategies
#    verbatim against block merchants) — COMMIT / COORDINATE / regime
# ══════════════════════════════════════════════════════════════════════════

class BlockMerchant:
    """A block merchant seen through the buyer.Merchant protocol, so
    buyer/strategies (shop/commit) run against the committed block sims with
    zero reimplementation. quote() calls vend's Nash engine (read-only) with
    the block A2A defaults (min_gain 0.75/0.15, symmetric split), honoring the
    Intent's SKU restriction (which the venue's own .quote cannot express —
    commit needs it). Wraps a real vend MachineState so salvage_floor is the
    genuine c_eff (salvage on would-spoil stock)."""

    MIN_GAIN = 0.75
    MIN_GAIN_FRAC = 0.15

    def __init__(self, merchant_id: str, state, catalog: dict):
        self.merchant_id = merchant_id
        self._state = state
        self._catalog = catalog

    def board(self):
        from buyer.merchant import BoardItem
        return {s: BoardItem(list_price=l.list_price, stock=self._state.stock(s))
                for s, l in self._catalog.items()}

    def outside_prices(self):
        return {s: l.bodega_price for s, l in self._catalog.items()}

    def salvage_floor(self, sku):
        from vend.scenario import c_eff
        return c_eff(self._state, sku)

    def quote(self, disclosure, intent):
        from vend.scenario import nash_quote
        from buyer.merchant import Quote
        allowed = None
        if intent.allowed is not None:
            allowed = lambda o: o.sku in intent.allowed  # noqa: E731
        nq = nash_quote(self._state, disclosure.wtp, disclosure.walk_cost,
                        allowed=allowed, min_gain=self.MIN_GAIN,
                        min_gain_frac=self.MIN_GAIN_FRAC, seller_weight=0.5)
        if nq.outcome is None:
            return None
        o = nq.outcome
        return Quote(merchant_id=self.merchant_id, sku=o.sku, qty=o.qty,
                     unit_price=o.unit_price,
                     list_price=self._catalog[o.sku].list_price,
                     why=tuple(nq.why), d_machine=nq.d_machine,
                     u_machine=nq.u_machine, salvage_floor=self.salvage_floor(o.sku))

    def settle(self, quote):
        self._state.take(quote.sku, quote.qty)


def _block_vend_merchant(seed: int, cfg: BlockConfig, *, markdown: bool = False,
                         mid: str = "block-vend") -> BlockMerchant:
    """A BlockMerchant over the block's vending board. markdown=True dates the
    perishable lots (shelf_life ≤ 3: sandwich, fruit-cup) to expire TONIGHT, so
    c_eff drops to salvage — the would-spoil stock the COMMIT clears (the block
    mirror of buyer.world.vend_markdown_merchant)."""
    from vend.core import Lot
    from vend.world import fresh_machine
    catalog = build_block_catalog(cfg, seed)
    state = fresh_machine(mid, catalog)
    state.day, state.tick = 0, 40
    if markdown:
        for sku, l in catalog.items():
            if l.shelf_life_days <= 3:
                state.lots = [x for x in state.lots if x.sku != sku]
                state.lots.append(Lot(sku=sku, quantity=2 * l.par_stock,
                                      expires_day=0))
    return BlockMerchant(mid, state, catalog)


def _block_bodega_merchant(seed: int, cfg: BlockConfig,
                           vend_catalog=None) -> BlockMerchant:
    """A BlockMerchant over the adopted bodega's board (deep, non-perishable)."""
    from vend.core import Lot, MachineState
    from block.venues import build_bodega_catalog, BodegaVenue
    catalog = build_bodega_catalog(cfg, seed, vend_catalog)
    state = MachineState("block-bodega", catalog, lots=[])
    state.day, state.tick = 0, 40
    for item in catalog:
        state.lots.append(Lot(sku=item, quantity=BodegaVenue.PAR_PER_ITEM,
                              expires_day=3650))
    return BlockMerchant("block-bodega", state, catalog)


def _street_population(seed: int, days: int):
    """The block's real street shoppers (home vending/bodega), across `days`,
    keyed on uid — the same population both arms of every split experiment
    face (paired by identity)."""
    from vend.world import TICKS_PER_DAY
    out = []
    for day in range(days):
        stream = population.day_stream(seed, day)
        for t in range(TICKS_PER_DAY):
            for sh in stream[t]:
                if sh.home in ("vending", "bodega"):
                    out.append(sh)
    return out


# ── COMMIT: forward-demand contract on block perishables (growth leg) ────────

def block_commit(seed: int, n: int, *, p_spoil: float = 0.40,
                 rounds: int = 6) -> dict:
    """buyer.strategies.commit_strategy VERBATIM on the block's would-spoil
    perishables (sandwich/fruit-cup at NYC salvage). A credible forward
    commitment converts salvage-worth stock into a real sale, so it GROWS the
    pie by p_spoil·(value−salvage), split 50/50 by Nash — the merchant KEEPS a
    positive share and sheds variance. The Wallet compounds (attested newcomer
    tf=0.5 → proven tf→1)."""
    from buyer.agent import BuyerAgent
    from buyer.strategies import commit_strategy
    from buyer.stats import mean_ci
    from buyer.wallet import Wallet
    cfg = BlockConfig()
    m_A = _block_vend_merchant(seed, cfg, markdown=True, mid="block-vend-A")
    m_B = _block_vend_merchant(seed + 777, cfg, markdown=True, mid="block-vend-B")
    pop = _street_population(seed, days=max(1, -(-n // 500)))[:n]

    r1_joint, r1_buyer, r1_var, r1_merch = [], [], [], []
    rR_joint, rR_buyer, rR_var, rR_tf = [], [], [], []
    port_carried, port_fresh = [], []
    committers = 0
    for sh in pop:
        wtp = {s: sh.wtp[s] for s in m_A._catalog}
        agent = BuyerAgent(sh.uid, wtp, sh.cross_walk)
        wallet = Wallet(uid=sh.uid, attested=True, reliability=0.0)
        first = last = None
        for rd in range(rounds):
            cr = commit_strategy(agent, m_A, p_spoil=p_spoil, wallet=wallet)
            if not cr.committed:
                break
            if rd == 0:
                first = cr
            last = cr
            wallet.fulfilled()
        else:
            committers += 1
            r1_joint.append(first.d_joint); r1_buyer.append(first.d_buyer)
            r1_var.append(first.var_reduction); r1_merch.append(first.d_merchant)
            rR_joint.append(last.d_joint); rR_buyer.append(last.d_buyer)
            rR_var.append(last.var_reduction); rR_tf.append(last.trusted_frac)
            cr_carry = commit_strategy(agent, m_B, p_spoil=p_spoil, wallet=wallet)
            cr_fresh = commit_strategy(agent, m_B, p_spoil=p_spoil,
                                       wallet=Wallet(uid=sh.uid, attested=True))
            if cr_carry.committed and cr_fresh.committed:
                port_carried.append(cr_carry.d_buyer)
                port_fresh.append(cr_fresh.d_buyer)
    return {
        "n": len(pop), "committers": committers, "p_spoil": p_spoil,
        "newcomer_joint_growth": mean_ci(r1_joint),
        "newcomer_buyer_share": mean_ci(r1_buyer),
        "newcomer_merchant_share": mean_ci(r1_merch),
        "newcomer_var_reduction": round(float(np.mean(r1_var)) if r1_var else 0, 4),
        "proven_joint_growth": mean_ci(rR_joint),
        "proven_trusted_frac": round(float(np.mean(rR_tf)) if rR_tf else 0, 4),
        "merchant_share_min": round(min(r1_merch) if r1_merch else 0.0, 6),
        "merchant_share_ge_zero": bool(all(m >= -1e-9 for m in r1_merch)),
    }


# ── COORDINATE + the buyer-side monopsony audit (growth leg + floor) ─────────

def _coordinate_audit_checks(sweep: dict, ks) -> dict:
    """The pre-registered monopsony-audit predicates over a coordination
    `sweep` (extracted so a synthetic sweep can exercise them directly).

    D is the load-bearing one: over-extraction (extraction=1.2) prices BELOW
    the merchant's salvage floor, so the merchant refuses and the unit spoils —
    it must ACTUALLY breach participation in every k. The old
    `overreach_units_spoiled >= 0` was vacuous (a unit count is always ≥ 0);
    `overreach_participation_fail_frac > 0` genuinely verifies the floor bit and
    can FAIL if over-extraction ever stops being self-defeating."""
    return {
        "A_coord_not_below_indep": all(
            sweep[k]["d_coord_minus_indep"]["mean"] >= -1e-9 for k in ks),
        "B_participation_floor_holds": all(
            sweep[k]["fair_merchant_margin_min"] >= -1e-9
            and sweep[k]["monopsony_merchant_margin_min"] >= -1e-9 for k in ks),
        "D_overreach_self_defeating": all(
            sweep[k]["overreach_participation_fail_frac"] > 0.0 for k in ks),
    }


def block_coordinate(seed: int, n: int, *, target: str = "sandwich",
                     p_spoil: float = 0.40, ks=(2, 5, 10, 20),
                     scarcity: float = 0.5) -> dict:
    """buyer.strategies.coordinate + the pre-registered monopsony audit on the
    block's scarce would-spoil sandwich. Coordination GROWS surplus (matching
    the stock to the members who value it most) but — the RealPage mirror — the
    merchant's salvage floor is load-bearing: it can never be pushed below."""
    from buyer.strategies import coordinate
    from buyer.stats import mean_ci, paired_ci
    salvage = {s: salv for s, _mu, _c, salv, *_ in calibration.VENDING_CATALOG}[target]
    pop = _street_population(seed, days=max(1, -(-n // 500)))[:n]
    vals = [sh.wtp[target] for sh in pop]

    sweep = {}
    for k in ks:
        s_risk = max(1, int(round(k * scarcity)))
        indep_g, fair_g, mono_g = [], [], []
        fair_merch, mono_merch, over_fail, over_spoiled, clusters = [], [], 0, 0, 0
        for c in range(0, (len(vals) // k) * k, k):
            grp = vals[c:c + k]
            sd = (seed * 131 + c) & 0x7FFFFFFF
            indep = coordinate(grp, salvage=salvage, s_risk=s_risk,
                               p_spoil=p_spoil, extraction=0.5,
                               allocation="random", seed=sd)
            fair = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=0.5, allocation="efficient")
            mono = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.0, allocation="efficient")
            over = coordinate(grp, salvage=salvage, s_risk=s_risk,
                              p_spoil=p_spoil, extraction=1.2, allocation="efficient")
            indep_g.append(indep.total_growth / k)
            fair_g.append(fair.total_growth / k)
            mono_g.append(mono.total_growth / k)
            fair_merch.append(fair.merchant_margin)
            mono_merch.append(mono.merchant_margin)
            over_fail += int(not over.participation_ok)
            over_spoiled += over.spoiled_by_overreach
            clusters += 1
        sweep[k] = {
            "s_risk": s_risk, "clusters": clusters,
            "indep_growth_pc": mean_ci(indep_g),
            "coord_fair_growth_pc": mean_ci(fair_g),
            "d_coord_minus_indep": paired_ci([f - i for f, i in zip(fair_g, indep_g)]),
            "fair_merchant_margin_min": round(min(fair_merch) if fair_merch else 0.0, 6),
            "monopsony_merchant_margin_min": round(min(mono_merch) if mono_merch else 0.0, 6),
            "overreach_participation_fail_frac": round(over_fail / max(1, clusters), 4),
            "overreach_units_spoiled": over_spoiled,
        }
    checks = _coordinate_audit_checks(sweep, ks)
    verdict = ("PASS" if all(checks.values()) else "FAIL")
    return {"n": len(pop), "target": target, "p_spoil": p_spoil, "ks": list(ks),
            "sweep": sweep, "audit_checks": checks, "audit_verdict": verdict}


# ── the human vs agent-mediated regime, on block merchants (the knobs) ───────

def block_regime(seed: int, n: int, *, human_friction: float = 0.30) -> dict:
    """The task's agent-mediated regime knobs (friction→0, fast churn) on the
    block. HUMAN: a mental switch-cost per negotiated deal and sticky to the
    home merchant (no shopping). AGENT: friction 0, shops both brokered
    merchants. Both graded vs the agent-mediated frontier (shop, friction 0)."""
    from buyer.agent import BuyerAgent
    from buyer.frontier import shop_frontier
    from buyer.strategies import shop
    from buyer.stats import mean_ci, paired_ci
    cfg = BlockConfig()
    catalog = build_block_catalog(cfg, seed)
    V = _block_vend_merchant(seed, cfg, mid="block-vend")
    B = _block_bodega_merchant(seed, cfg, vend_catalog=catalog)
    merchants = [V, B]
    pop = _street_population(seed, days=max(1, -(-n // 500)))[:n]

    human_real, human_reg, agent_real, agent_reg, front, d_surplus = \
        [], [], [], [], [], []
    union = set(V._catalog) | set(B._catalog)
    for sh in pop:
        wtp = {s: sh.wtp[s] for s in union}
        fr = shop_frontier(wtp, sh.cross_walk, merchants, friction=0.0)
        front.append(fr.surplus)
        home_m = V if sh.home == "vending" else B
        human = BuyerAgent(sh.uid, wtp, sh.cross_walk, friction=human_friction)
        _, r_h, _ = human.negotiate(home_m)
        agent = BuyerAgent(sh.uid, wtp, sh.cross_walk, friction=0.0)
        r_a = shop(agent, merchants).realized
        human_real.append(r_h); human_reg.append(max(0.0, fr.surplus - r_h))
        agent_real.append(r_a); agent_reg.append(max(0.0, fr.surplus - r_a))
        d_surplus.append(r_a - r_h)
    return {
        "n": len(pop), "human_friction": human_friction,
        "frontier_mean": mean_ci(front)["mean"],
        "human_surplus": mean_ci(human_real), "human_regret": mean_ci(human_reg),
        "agent_surplus": mean_ci(agent_real), "agent_regret": mean_ci(agent_reg),
        "delta_surplus_agent_minus_human": paired_ci(d_surplus),
    }


# ── the frictionless-commodity ENDGAME stress (the transfer's ceiling) ───────

def commodity_stress(seed: int, days: int, *,
                     goods=("cola-20oz", "chips")) -> dict:
    """The worst case for merchant margin the Bezos r2 critique fears: the
    buyer's agent shops the COMMODITY OVERLAP (goods BOTH merchants carry) with
    the physical walk removed (pure A2A — the agent gathers both quotes and the
    winner delivers), so ONLY product differentiation protects margin. Compares,
    over the block's street population and restricted to `goods`:
      passive   — a single-merchant symmetric-Nash quote (the committed block).
      bertrand  — both merchants at their FLOOR, walk→0: the winner keeps only
                  its cost advantage over the runner-up (margin = winner_joint −
                  max(runnerup_joint, posted_outside)); on a pure commodity with
                  equal floors this drives margin to ~0.
    Isolates the TRANSFER ceiling and whether even the endgame is a both-win."""
    from buyer.merchant import Intent, Disclosure
    from vend.scenario import c_eff
    from vend.world import QTY_CAP
    cfg = BlockConfig()
    catalog = build_block_catalog(cfg, seed)
    V = _block_vend_merchant(seed, cfg, mid="stress-vend")
    B = _block_bodega_merchant(seed, cfg, vend_catalog=catalog)
    allowed = frozenset(goods)

    def at_floor(mkt, disc):
        best = 0.0
        for sku in mkt._catalog:
            if sku not in allowed or sku not in disc:
                continue
            st = mkt._state.stock(sku)
            for qty in range(1, min(QTY_CAP, st) + 1):
                s = vend_value(disc, sku, qty) - qty * c_eff(mkt._state, sku)
                best = max(best, s)
        return best

    def posted_outside(disc):                    # buyer's sticker fallback on `goods`
        s = 0.0
        for mkt in (V, B):
            for sku in mkt._catalog:
                if sku not in allowed or sku not in disc:
                    continue
                lp = mkt._catalog[sku].list_price
                for qty in range(1, QTY_CAP + 1):
                    s = max(s, vend_value(disc, sku, qty) - qty * lp)
        return s

    union = set(V._catalog) | set(B._catalog)
    pop = _street_population(seed, days)
    p_margin = p_cs = b_margin = b_cs = 0.0
    deals = at_floor_wins = 0
    for sh in pop:
        disc = {g: sh.wtp[g] for g in union}     # full catalog; allowed restricts outcomes
        # passive: single-merchant Nash on the overlap goods (vending)
        q = V.quote(Disclosure(wtp=disc, walk_cost=0.0, attested=True),
                    Intent(allowed=allowed))
        if q is not None:
            p_margin += q.qty * (q.unit_price - q.salvage_floor)
            p_cs += vend_value(sh.wtp, q.sku, q.qty) - q.qty * q.unit_price
        # bertrand endgame: both at floor, walk 0
        jV, jB = at_floor(V, disc), at_floor(B, disc)
        out = posted_outside(disc)
        jw, jr = (jV, jB) if jV >= jB else (jB, jV)
        buyer_gets = max(jr, out)
        if jw > buyer_gets + 1e-9 and jw > 0:      # a competitive deal clears
            deals += 1
            b_margin += jw - buyer_gets            # winner keeps its cost edge
            b_cs += buyer_gets
            if jw - buyer_gets < 0.05:
                at_floor_wins += 1
    return {
        "goods": list(goods), "n_buyers": len(pop),
        "passive_margin_day": round(p_margin / days, 2),
        "bertrand_margin_day": round(b_margin / days, 2),
        "passive_cs_day": round(p_cs / days, 2),
        "bertrand_cs_day": round(b_cs / days, 2),
        "margin_transfer_day": round((b_margin - p_margin) / days, 2),
        "competitive_deals_day": round(deals / days, 1),
        "frac_driven_to_floor": round(at_floor_wins / max(1, deals), 3),
    }


# ══════════════════════════════════════════════════════════════════════════
# the per-venue antagonism table (deliverable A) — real stock, the runner
# ══════════════════════════════════════════════════════════════════════════

def _daily_margin(ledger: BlockLedger, world: str, venue: str, days: int):
    return [ledger.day_metrics(world, venue, d)["margin"] for d in range(days)]


def _daily_cs(ledger: BlockLedger, world: str, venue: str, days: int):
    return [ledger.day_metrics(world, venue, d)["consumer_surplus"]
            for d in range(days)]


def run_antagonism(days: int, seed: int, regulars: int, venues) -> dict:
    """Run the passive → adopt → agent(bertrand) ladder on the SAME seeded
    population and assemble the per-venue merchant-margin table + the HUD
    counters. Every twin shares the seed, so the population stream is identical
    across regimes and the per-day margin diffs are paired treatment effects
    (block-CI on 5-day blocks, exactly as B5)."""
    from block.runner import run_twin
    from block.ledger import paired_ci, VENUE_CI_BLOCK, DEFAULT_CI_BLOCK
    venues = tuple(venues)

    passive = BlockConfig(regulars=regulars)                       # committed B5
    adopt = BlockConfig(regulars=regulars, bodega_adopts=True)     # bodega nego, no comp
    agent = BlockConfig(regulars=regulars, bodega_adopts=True,     # + competition
                        agent_demand="bertrand", agent_friction=0.0)

    res_p, led_p, _ = run_twin(days, seed, passive, venues=venues)
    res_a, led_a, _ = run_twin(days, seed, adopt, venues=venues)
    res_g, led_g, _ = run_twin(days, seed, agent, venues=venues)

    table = {}
    for v in venues:
        blk = VENUE_CI_BLOCK.get(v, DEFAULT_CI_BLOCK)
        stick = _daily_margin(led_p, "sticker", v, days)     # same in all 3
        p_sn = _daily_margin(led_p, "snhp", v, days)
        a_sn = _daily_margin(led_a, "snhp", v, days)
        g_sn = _daily_margin(led_g, "snhp", v, days)
        cs_p = _daily_cs(led_p, "snhp", v, days)
        cs_g = _daily_cs(led_g, "snhp", v, days)
        # transfer = the competition step (agent − adopt): price competition,
        # holding the negotiation surface fixed. growth/surface = adopt − passive
        # (the bodega gains a brokered arm). Δjoint(agent−passive) = Δmargin+Δcs.
        d_margin = [g - p for g, p in zip(g_sn, p_sn)]
        d_transfer = [g - a for g, a in zip(g_sn, a_sn)]
        d_surface = [a - p for a, p in zip(a_sn, p_sn)]
        d_cs = [g - p for g, p in zip(cs_g, cs_p)]
        d_joint = [dm + dc for dm, dc in zip(d_margin, d_cs)]
        table[v] = {
            "sticker_margin_day": round(sum(stick) / days, 2),
            "passive_snhp_margin_day": round(sum(p_sn) / days, 2),
            "adopt_snhp_margin_day": round(sum(a_sn) / days, 2),
            "agent_snhp_margin_day": round(sum(g_sn) / days, 2),
            "d_margin_agent_minus_passive": paired_ci(d_margin, block=blk),
            "d_transfer_competition": paired_ci(d_transfer, block=blk),
            "d_surface_adoption": paired_ci(d_surface, block=blk),
            "d_cs_agent_minus_passive": paired_ci(d_cs, block=blk),
            "d_joint_agent_minus_passive": paired_ci(d_joint, block=blk),
            # the HUD "merchants earned" contribution under each regime
            "hud_merchant_passive_day": round((sum(p_sn) - sum(stick)) / days, 2),
            "hud_merchant_agent_day": round((sum(g_sn) - sum(stick)) / days, 2),
            "hud_agent_negative": bool(sum(g_sn) - sum(stick) < 0),
        }
    hud = {
        "passive": res_p["hud"],
        "adopt": res_a["hud"],
        "agent_bertrand": res_g["hud"],
    }
    return {"days": days, "seed": seed, "regulars": regulars,
            "venues": list(venues), "per_venue": table, "hud": hud}


# ══════════════════════════════════════════════════════════════════════════
# orchestrator + CLI
# ══════════════════════════════════════════════════════════════════════════

def run_all(days: int, seed: int, regulars: int, n_split: int) -> dict:
    street = ("vending", "bodega")
    core = run_antagonism(days, seed, regulars, street)
    full = run_antagonism(days, seed, regulars,
                          ("vending", "bodega", "boba", "fashion", "bakery",
                           "florist", "barbershop", "parking", "bar", "vintage"))
    return {
        "config": {"days": days, "seed": seed, "regulars": regulars,
                   "n_split": n_split},
        "core_street": core,
        "full_block": {"hud": full["hud"], "per_venue": full["per_venue"]},
        "commodity_stress": commodity_stress(seed, days),
        "split": {
            "commit": block_commit(seed, n_split),
            "coordinate": block_coordinate(seed, n_split),
            "regime": block_regime(seed, n_split),
        },
    }


def _print(results: dict) -> None:
    core = results["core_street"]["per_venue"]
    print("\n=== A. per-venue merchant margin ($/day): PASSIVE vs AGENT-MEDIATED ===")
    print(f"{'venue':<10} {'sticker':>9} {'passive':>9} {'adopt':>9} {'agent':>9}"
          f" {'Δmargin(CI)':>22} {'transfer':>10} {'HUD_p':>8} {'HUD_a':>8}")
    for v, r in results["full_block"]["per_venue"].items():
        dm = r["d_margin_agent_minus_passive"]
        tr = r["d_transfer_competition"]
        print(f"{v:<10} {r['sticker_margin_day']:>9.2f} "
              f"{r['passive_snhp_margin_day']:>9.2f} {r['adopt_snhp_margin_day']:>9.2f} "
              f"{r['agent_snhp_margin_day']:>9.2f} "
              f"{str(dm['mean'])+' '+str(dm['ci95']):>22} {tr['mean']:>10} "
              f"{r['hud_merchant_passive_day']:>8.2f} {r['hud_merchant_agent_day']:>8.2f}"
              f"{'  NEG' if r['hud_agent_negative'] else ''}")
    hud = results["full_block"]["hud"]
    print("\nHUD (10-venue) shoppers kept / merchants earned:")
    for reg in ("passive", "adopt", "agent_bertrand"):
        h = hud[reg]
        print(f"  {reg:<16} kept ${h['shoppers_kept_usd']:>12.2f} · "
              f"earned ${h['merchants_earned_usd']:>12.2f}")

    cs = results["commodity_stress"]
    print(f"\n=== A2A ENDGAME stress (overlap {cs['goods']}, walk→0) ===")
    print(f"  merchant margin/day  passive {cs['passive_margin_day']} → bertrand "
          f"{cs['bertrand_margin_day']}  (transfer {cs['margin_transfer_day']})")
    print(f"  buyer CS/day         passive {cs['passive_cs_day']} → bertrand "
          f"{cs['bertrand_cs_day']}  | {cs['competitive_deals_day']} deals/day, "
          f"{cs['frac_driven_to_floor']*100:.0f}% driven to the floor")

    sp = results["split"]
    cm = sp["commit"]
    print(f"\n=== B. COMMIT (growth) n={cm['n']} committers={cm['committers']} ===")
    print(f"  joint growth/buyer {cm['newcomer_joint_growth']['mean']} "
          f"CI{cm['newcomer_joint_growth']['ci95']} · merchant share "
          f"{cm['newcomer_merchant_share']['mean']} (min {cm['merchant_share_min']}, "
          f"≥0: {cm['merchant_share_ge_zero']})")
    co = sp["coordinate"]
    print(f"=== COORDINATE + monopsony audit: {co['audit_verdict']} "
          f"(checks {co['audit_checks']}) ===")
    rg = sp["regime"]
    ds = rg["delta_surplus_agent_minus_human"]
    print(f"=== REGIME (block merchants) frontier {rg['frontier_mean']} ===")
    print(f"  human  surplus {rg['human_surplus']['mean']} regret {rg['human_regret']['mean']}")
    print(f"  agent  surplus {rg['agent_surplus']['mean']} regret {rg['agent_regret']['mean']}")
    print(f"  Δsurplus agent−human {ds['mean']} CI{ds['ci95']} "
          f"{'SIG' if ds['significant'] else 'ns'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--regulars", type=int, default=25)
    ap.add_argument("--n-split", type=int, default=4000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    results = run_all(args.days, args.seed, args.regulars, args.n_split)
    _print(results)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

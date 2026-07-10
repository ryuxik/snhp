"""The four agency behaviors (gap 5), each a composable policy over the Merchant
protocol and each a measurable lever:

  shop       query k merchants, take the best quote        (buyer leverage)
  time       defer for a forecast better-priced state       (yield mgmt, mirror)
  commit     credible forward demand for a lower rate        (variance → pie)
  coordinate a cluster of buyers into one commitment         (monopsony mirror)

Accounting used throughout — the transfer-vs-growth split:
  buyer_surplus = value − qty·price                (the buyer's slice)
  joint_value    = value − qty·c_eff               (the whole pie; price only
                                                    SPLITS it, so Δjoint isolates
                                                    growth from transfer)
Δbuyer with Δjoint ≈ 0  ⇒ TRANSFER (buyer gains ≈ merchant loses).
Δbuyer with Δjoint > 0  ⇒ GROWTH   (a bigger/more-efficient deal; both can win).
"""
from __future__ import annotations

from dataclasses import dataclass

from buyer.agent import BuyerAgent
from buyer.merchant import Disclosure, Intent, Merchant, Quote
from buyer.values import best_bundle, bundle_surplus, bundle_value


# ── accounting ───────────────────────────────────────────────────────────────

def buyer_surplus_of(wtp, quote: Quote | None, friction: float = 0.0) -> float:
    if quote is None:
        return 0.0
    return bundle_surplus(wtp, quote.sku, quote.qty, quote.unit_price) - friction


def joint_value_of(wtp, quote: Quote | None) -> float:
    """Total social surplus of the transaction: value − qty·c_eff. Price only
    splits this, so comparing it across arms separates growth from transfer."""
    if quote is None:
        return 0.0
    return bundle_value(wtp, quote.sku, quote.qty) - quote.qty * quote.salvage_floor


def merchant_margin_of(quote: Quote | None) -> float:
    """The merchant's realized margin over its opportunity cost (c_eff)."""
    if quote is None:
        return 0.0
    return quote.qty * (quote.unit_price - quote.salvage_floor)


# ── SHOP ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ShopResult:
    quote: Quote | None
    realized: float
    merchant_id: str | None
    n_queried: int


def shop(agent: BuyerAgent, merchants: list[Merchant], *, k: int | None = None,
         attested: bool = False) -> ShopResult:
    """Query k merchants (default all), disclose honestly to each, take the best
    quote — or the walk-away if none beats it. When k < M the agent queries the
    k merchants whose posted board looks cheapest for its favorite SKU (a cheap,
    honest heuristic; query cost itself is abstracted)."""
    fb, _ = agent.fallback(merchants)
    order = merchants
    if k is not None and k < len(merchants):
        fav = max(agent.wtp, key=agent.wtp.get)
        order = sorted(merchants,
                       key=lambda m: m.board().get(fav).list_price
                       if fav in m.board() else 1e9)[:k]
    best_q, best_s, best_m = None, fb, None
    for m in order:
        q = m.quote(agent.disclose(attested=attested), Intent())
        s = agent.true_surplus(q)
        if q is not None and s > best_s:
            best_q, best_s, best_m = q, s, m.merchant_id
    return ShopResult(best_q, best_s, best_m, len(order))


# ── TIME ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimeResult:
    realized: float
    deferred: bool
    quote: Quote | None       # the quote actually taken (now or future)
    hindsight: float          # best over {now, future} with perfect foresight


def time_strategy(agent: BuyerAgent, now_m: Merchant, future_m: Merchant, *,
                  glut_prob: float, wait_cost: float, glut_happens: bool,
                  attested: bool = False) -> TimeResult:
    """Buy now vs defer one period. The agent FORECASTS the future with the glut
    probability (it does not know this buyer's realization); it defers iff the
    expected gain beats the wait cost. Realization uses `glut_happens`.

    Frontier (hindsight) is the best of {buy now, buy in the realized future};
    the agent's regret is the price of forecasting under uncertainty."""
    d = agent.disclose(attested=attested)
    q_now = now_m.quote(d, Intent())
    s_now = agent.true_surplus(q_now)
    fb_now, _ = agent.fallback([now_m])
    s_now = max(s_now, fb_now)

    # what the future looks like if it gluts (the state the agent can forecast)
    q_glut = future_m.quote(d, Intent())
    s_glut = agent.true_surplus(q_glut)
    fb_fut, _ = agent.fallback([future_m])
    s_glut = max(s_glut, fb_fut) - wait_cost
    # no-glut future ≈ today's deal, minus the wait
    s_nofut = s_now - wait_cost

    exp_defer = glut_prob * s_glut + (1 - glut_prob) * s_nofut
    defer = exp_defer > s_now

    if not defer:
        realized, q_used = s_now, q_now
    else:
        realized, q_used = (s_glut, q_glut) if glut_happens else (s_nofut, q_now)
    hindsight = max(s_now, (s_glut if glut_happens else s_nofut))
    return TimeResult(realized=realized, deferred=defer, quote=q_used,
                      hindsight=hindsight)


# ── COMMIT ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommitResult:
    committed: bool
    target_sku: str | None
    forward_qty: int
    d_buyer: float            # ΔBuyer surplus vs the no-commit expectation
    d_merchant: float         # ΔMerchant expected payoff vs no-commit
    d_joint: float            # ΔJoint (the pie GROWTH) captured
    var_reduction: float      # merchant payoff variance removed (risk transfer)
    trusted_frac: float
    committed_price: float


def commit_strategy(agent: BuyerAgent, merchant: Merchant, *, p_spoil: float,
                    wallet=None, attested: bool = True) -> CommitResult:
    """A credible forward commitment. The agent guarantees to absorb the
    would-spoil perishable stock the merchant is otherwise stuck salvaging; in
    return the units are priced off the salvage floor with the displacement
    uncertainty removed. Because a committed sale converts stock worth only
    salvage into a real transaction, it GROWS the pie by exactly the expected
    spoilage loss avoided, p_spoil·(value − salvage) — and eliminates the
    merchant's payoff variance. The Wallet's `trusted_frac` bounds how much of
    that a merchant will bank (credibility is what a human lacks).

    Accounting (per committed bundle of the buyer's best perishable):
      V         = bundle_value(true_wtp, sku, qty)          buyer's value
      salv      = qty·salvage                               spoilage floor
      p_spot    = the spot Nash unit price for the SKU      no-commit sale price
      E_buyer   = (1−p_spoil)(V − qty·p_spot)               no-commit buyer exp.
      E_merch   = (1−p_spoil)(qty·p_spot − salv)            no-commit merch exp.
      Δjoint    = p_spoil·(V − salv)                        the growth (spoilage
                                                            avoided), split 50/50
    """
    from buyer.merchant import Intent
    # target the buyer's best perishable-like SKU: one whose salvage floor sits
    # well below its list (that is the stock at spoilage risk).
    board = merchant.board()
    cands = [(s, merchant.salvage_floor(s), bi.list_price)
             for s, bi in board.items() if bi.stock > 0]
    perish = [(s, floor) for s, floor, lp in cands if floor < 0.5 * lp]
    if not perish:
        return CommitResult(False, None, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    # pick the perishable the buyer values most (above its salvage floor)
    target, salvage = max(perish, key=lambda sf: agent.wtp.get(sf[0], 0) - sf[1])
    forward_qty = 2
    V = bundle_value(agent.wtp, target, forward_qty)
    salv = forward_qty * salvage
    if V - salv <= 0:
        return CommitResult(False, target, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    q_spot = merchant.quote(agent.disclose(attested=attested),
                            Intent(allowed=frozenset({target})))
    p_spot = q_spot.unit_price if q_spot is not None else board[target].list_price
    spot_total = forward_qty * p_spot

    e_buyer = (1 - p_spoil) * (V - spot_total)
    e_merch = (1 - p_spoil) * (spot_total - salv)
    d_joint_full = p_spoil * (V - salv)
    var_nc = p_spoil * (1 - p_spoil) * (spot_total - salv) ** 2

    tf = wallet.trusted_frac() if wallet is not None else (0.5 if attested else 0.0)
    d_joint = tf * d_joint_full
    d_buyer = d_joint / 2.0
    d_merch = d_joint / 2.0
    var_reduction = tf * var_nc
    buyer_commit_surplus = e_buyer + d_buyer
    committed_price = (V - buyer_commit_surplus) / forward_qty
    return CommitResult(True, target, forward_qty, d_buyer, d_merch, d_joint,
                        var_reduction, tf, round(committed_price, 4))


# ── COORDINATE + the buyer-side monopsony audit ─────────────────────────────

@dataclass(frozen=True)
class CoordResult:
    k: int
    extraction: float
    allocation: str
    units_cleared: int
    total_growth: float       # joint welfare created (spoilage avoided), $
    buyer_growth: float       # buyers' share of it
    merchant_margin: float    # merchant's share (>= 0 iff participation holds)
    participation_ok: bool    # no unit priced below the merchant's salvage floor
    spoiled_by_overreach: int  # units lost because the cluster breached the floor


def coordinate(member_values: list[float], *, salvage: float, s_risk: int,
               p_spoil: float, extraction: float = 0.5,
               allocation: str = "efficient", seed: int = 0) -> CoordResult:
    """A cluster of buyers aggregates its forward demand for the merchant's
    scarce, spoil-risk stock (`s_risk` units). Each cleared would-spoil unit
    creates welfare `p_spoil·(value − salvage)` (the expected spoilage avoided).

    `allocation` — how the scarce units are matched to members:
      "efficient" : to the highest-value members (what a coordinating cluster
                    does). "random" : a seeded subset (the INDEPENDENT-commit
                    baseline, where uncoordinated buyers race for the stock and
                    may not be the ones who value it most).
    `extraction` — how hard the cluster pushes price down, in [0, ~]:
      price = salvage + (1−extraction)·(value − salvage). 0.5 = fair Nash split;
      1.0 = the merchant's participation FLOOR (margin 0); > 1.0 = a demand
      BELOW salvage, which the merchant rejects — the unit then spoils (welfare
      lost). The floor is the merchant's disagreement point: it is what makes
      over-extraction self-defeating, and it is exactly the monopsony guardrail.
    """
    import numpy as np
    elig = [v for v in member_values if v > salvage]
    if allocation == "efficient":
        chosen = sorted(elig, reverse=True)[:s_risk]
    else:  # random / independent race for the scarce stock
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(elig))[:s_risk]
        chosen = [elig[i] for i in idx]

    total_g = buyer_g = merch_m = 0.0
    cleared = spoiled = 0
    participation = True
    for v in chosen:
        price = salvage + (1 - extraction) * (v - salvage)
        if price < salvage - 1e-9:          # merchant would earn below floor
            participation = False
            spoiled += 1                      # it refuses → the unit spoils
            continue
        g = p_spoil * (v - salvage)
        total_g += g
        buyer_g += p_spoil * (v - price)
        merch_m += p_spoil * (price - salvage)
        cleared += 1
    return CoordResult(k=len(member_values), extraction=extraction,
                       allocation=allocation, units_cleared=cleared,
                       total_growth=round(total_g, 6),
                       buyer_growth=round(buyer_g, 6),
                       merchant_margin=round(merch_m, 6),
                       participation_ok=participation,
                       spoiled_by_overreach=spoiled)

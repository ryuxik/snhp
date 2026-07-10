"""Brokered A2A quoting: the neutral engine computes the Nash bargaining
solution on the true joint frontier of (buyer, machine) — in dollars.

The disagreement point is the fix for P0's cannibalization finding:

  * buyer's disagreement  = their best outside option (bodega − walk cost)
  * machine's disagreement = the margin it would earn if this buyer just
    bought at the sticker board — the sale it already had

so a buyer who would have paid list gets a discount only out of *newly
created* surplus (bigger basket, substitution to expiring stock), never out
of margin the machine already had. Under verified disclosure this is exact;
when attestation is off, a liar understates WTP and overstates their outside
option — shrinking the machine's believed disagreement — which is precisely
the leaderboard's anchoring exploit, now measurable per liar share (H3).
"""
from __future__ import annotations

from dataclasses import dataclass

from vend.core import MachineState
from vend.world import QTY_CAP

PRICE_RUNGS = 12


@dataclass(frozen=True)
class Outcome:
    sku: str
    qty: int
    unit_price: float


def c_eff(state: MachineState, sku: str) -> float:
    """Opportunity cost of one unit: salvage if it dies tonight, else
    replacement cost (nightly top-to-par restock)."""
    listing = state.listings[sku]
    dte = state.days_to_expiry(sku)
    return listing.salvage if (dte is not None and dte <= 0) else listing.unit_cost


from vend.world import BODEGA_MARKUP, best_bundle, bundle_value as buyer_value


def outside_surplus(wtp: dict[str, float], walk_cost: float,
                    catalog) -> float:
    """Best surplus at the bodega (the competitor's OWN posted prices,
    − the walk) — the SAME outside option the simulated consumer faces in
    run.py, via the same canonical chooser."""
    prices = {sku: l.bodega_price for sku, l in catalog.items()}
    _, _, s = best_bundle(wtp, prices)
    return max(0.0, s - walk_cost) if s > 0 else 0.0


def sticker_choice(wtp: dict[str, float], state: MachineState
                   ) -> tuple[str | None, int]:
    """What this buyer would purchase from the list-price board — the SAME
    stock-capped chooser the simulated consumer uses, so the machine's
    disagreement point is the purchase that would actually happen."""
    prices = {sku: l.list_price for sku, l in state.listings.items()
              if state.stock(sku) > 0}
    stock = {sku: state.stock(sku) for sku in prices}
    sku, qty, _ = best_bundle(wtp, prices, stock)
    return (sku, qty)


def enumerate_outcomes(state: MachineState) -> list[Outcome]:
    outs = []
    for sku, listing in state.listings.items():
        stock = state.stock(sku)
        if stock <= 0:
            continue
        floor = c_eff(state, sku)
        if floor >= listing.list_price:
            rungs = [listing.list_price]
        else:
            step = (listing.list_price - floor) / (PRICE_RUNGS - 1)
            rungs = [round(floor + i * step, 2) for i in range(PRICE_RUNGS)]
        for qty in range(1, min(QTY_CAP, stock) + 1):
            for p in rungs:
                outs.append(Outcome(sku, qty, p))
    return outs


_CUM_BASE_DEMAND: dict[tuple, list[float]] = {}


_REMAINING_FRAC: list[float] | None = None


def _remaining_frac(tick: int) -> float:
    """Fraction of a standard day's arrivals still ahead of `tick`."""
    global _REMAINING_FRAC
    if _REMAINING_FRAC is None:
        from vend.world import TICKS_PER_DAY, rate_at
        rates = [rate_at(t) for t in range(TICKS_PER_DAY)]
        total = sum(rates)
        cum, acc = [], 0.0
        for r in reversed(rates):
            acc += r
            cum.append(acc / total)
        _REMAINING_FRAC = list(reversed(cum))
    return _REMAINING_FRAC[tick]


def expected_list_demand(state: MachineState, sku: str, *,
                         dow_mult: float = 1.0, mult_hat: float = 1.0,
                         share: float | None = None,
                         emp_daily: float | None = None) -> float:
    """Expected rest-of-day units of `sku` demanded AT LIST price — the
    machine's forecast from the operator's DEMAND ESTIMATE, scaled by what
    it can observe: the public calendar (dow_mult), today's inferred crowd
    (mult_hat, Gamma–Poisson from arrivals), and the SKU's demand share
    learned from the machine's own realized sales (regime-consistent — the
    fix for P1's static-world displacement forecast). When `emp_daily` is
    given (the learner's EWMA of realized units/day in THIS arm's regime),
    the level comes from lived history instead of the structural formula —
    the forecast can no longer assume a world the mechanism abolished.
    The per-arrival base curve is cached per (sku, estimate, list)."""
    if emp_daily is not None:
        return emp_daily * _remaining_frac(state.tick) * dow_mult * mult_hat
    listing = state.listings[sku]
    n = len(state.listings)
    mu_est = listing.wtp_mu_est
    if mu_est <= 0:
        raise ValueError(f"Listing {sku!r} has no operator demand estimate "
                         "— build catalogs via world.build_catalog")
    key = (sku, round(mu_est, 4), round(listing.list_price, 2))
    if key not in _CUM_BASE_DEMAND:
        from scipy import stats
        from vend.world import TICKS_PER_DAY, WTP_SIGMA, rate_at, wtp_mult_at
        per_tick = [rate_at(t) / 6.0
                    * float(stats.lognorm.sf(listing.list_price, s=WTP_SIGMA,
                                             scale=mu_est * wtp_mult_at(t)))
                    for t in range(TICKS_PER_DAY)]
        cum, acc = [], 0.0
        for v in reversed(per_tick):
            acc += v
            cum.append(acc)
        _CUM_BASE_DEMAND[key] = list(reversed(cum))
    base = _CUM_BASE_DEMAND[key][state.tick]
    return base * (share if share is not None else 1.0 / n) * dow_mult * mult_hat


def machine_margin(state: MachineState, o: Outcome, *,
                   dow_mult: float = 1.0, mult_hat: float = 1.0,
                   share: float | None = None) -> float:
    """Margin net of the stock's shadow value: a unit the machine expects to
    sell at list later today is worth list margin to keep — selling it
    discounted DISPLACES that sale (contribution price − list ≤ 0). Only
    units in excess of expected list demand are cheap to move (contribution
    price − c_eff). This is what stops early bargain-hunters from draining
    the stock the lunch crowd would have paid list for."""
    s = state.stock(o.sku)
    D = expected_list_demand(state, o.sku, dow_mult=dow_mult,
                             mult_hat=mult_hat, share=share)
    ce = c_eff(state, o.sku)
    lp = state.listings[o.sku].list_price
    excess = max(0.0, s - D)               # units nobody at list is coming for
    displaced = min(float(o.qty), max(0.0, o.qty - excess))
    return (o.qty - displaced) * (o.unit_price - ce) \
        + displaced * (o.unit_price - lp)


@dataclass
class NashQuote:
    outcome: Outcome | None
    d_machine: float          # machine's disagreement (sticker counterfactual)
    d_buyer: float            # buyer's claimed outside surplus
    u_machine: float          # margin of the quoted outcome
    u_buyer_claimed: float
    joint_best: float         # max achievable joint surplus over disagreement
    joint_realized: float     # realized joint surplus (claimed basis)
    why: list[str]


def nash_quote(state: MachineState, disclosed_wtp: dict[str, float],
               disclosed_walk_cost: float, *,
               dow_mult: float = 1.0, mult_hat: float = 1.0,
               share_fn=None, allowed=None, daily_fn=None,
               min_gain: float = 0.0) -> NashQuote:
    """Nash bargaining over the enumerated outcome space, on the DISCLOSED
    buyer utilities. Machine surplus is measured against its sticker
    counterfactual; buyer surplus against their claimed outside option.
    dow_mult / mult_hat / share_fn carry the machine's observable demand
    context into the shadow prices (defaults reproduce the P1 setting).
    `allowed` (Outcome → bool) restricts the outcome space — e.g. to the
    intent's SKU when the buyer forbids substitutes."""
    catalog = state.listings
    n = len(catalog)
    _share = share_fn if share_fn is not None else (lambda s: 1.0 / n)

    # Per-SKU context, hoisted: stock, expected list demand, opportunity
    # cost, and list price are SKU-level facts recomputed identically for
    # every (qty, rung) outcome otherwise.
    sku_ctx: dict[str, tuple[float, float, float, float]] = {}
    for sku in catalog:
        if state.stock(sku) <= 0:
            continue
        emp = daily_fn(sku) if daily_fn is not None else None
        D = expected_list_demand(state, sku, dow_mult=dow_mult,
                                 mult_hat=mult_hat, share=_share(sku),
                                 emp_daily=emp)
        sku_ctx[sku] = (float(state.stock(sku)), D, c_eff(state, sku),
                        catalog[sku].list_price)

    def margin(o: Outcome) -> float:
        s, D, ce, lp = sku_ctx[o.sku]
        excess = max(0.0, s - D)
        displaced = min(float(o.qty), max(0.0, o.qty - excess))
        return (o.qty - displaced) * (o.unit_price - ce) \
            + displaced * (o.unit_price - lp)

    # Buyer bundle values, hoisted per (sku, qty) — price-independent.
    bval = {(sku, q): buyer_value(disclosed_wtp, sku, q)
            for sku in sku_ctx for q in range(1, QTY_CAP + 1)}

    # The disagreement point is the EVENT that happens with no deal — and it
    # must be one consistent event for both sides. The buyer's best no-deal
    # move is either their sticker-board purchase (intent-constrained,
    # stock-capped) or the bodega:
    #   board wins  → buyer keeps board surplus, machine keeps that margin
    #   bodega wins → buyer keeps outside surplus, machine keeps NOTHING —
    #                 which is exactly why marginal customers (weak board
    #                 fit, strong outside option) are worth recruiting with
    #                 deep quantity deals: every dollar above cost is found
    #                 money against a zero counterfactual.
    outside = max(0.0, outside_surplus(disclosed_wtp, disclosed_walk_cost, catalog))
    st_best, st_margin = None, 0.0
    for sku in sku_ctx:
        lp = sku_ctx[sku][3]
        for q in range(1, QTY_CAP + 1):
            o = Outcome(sku, q, lp)
            if allowed is not None and not allowed(o):
                continue
            s = bval.get((sku, q), 0.0) - q * lp
            if s > 0 and (st_best is None or s > st_best):
                st_best, st_margin = s, margin(o)
    if st_best is not None and st_best >= outside:
        d_b, d_s = st_best, st_margin      # no-deal world: they buy the board
    else:
        d_b, d_s = outside, 0.0            # no-deal world: they walk outside

    # Nash product, with a lexicographic tiebreak: when the machine is
    # exactly indifferent everywhere feasible (product pinned at 0), take
    # the feasible outcome with the greatest joint gain instead of
    # discarding a legitimate boundary deal.
    best, best_score = None, None
    joint_best = 0.0
    for o in enumerate_outcomes(state):
        if allowed is not None and not allowed(o):
            continue
        u_s = margin(o)
        u_b = bval[(o.sku, o.qty)] - o.qty * o.unit_price
        gs, gb = u_s - d_s, u_b - d_b
        if gs >= -1e-9 and gb >= -1e-9:
            joint_best = max(joint_best, gs + gb)
            score = (gs * gb, gs + gb)
            if best_score is None or score > best_score:
                best, best_score = o, score
    if best is not None and best_score[0] <= 0 and best_score[1] <= 1e-9:
        best = None   # nothing actually improves on the disagreement point
    if best is not None and min_gain > 0:
        # don't-negotiate-for-pennies: the machine's believed gain must
        # clear a buffer, so forecast noise can't leak margin on deals
        # that are barely better than no deal
        if margin(best) - d_s < min_gain:
            best = None

    if best is None:
        return NashQuote(None, d_s, d_b, 0.0, 0.0, joint_best, 0.0, [])

    u_s = margin(best)
    u_b = buyer_value(disclosed_wtp, best.sku, best.qty) \
        - best.qty * best.unit_price
    dte = state.days_to_expiry(best.sku)
    why = ["negotiated for you", f"{best.qty} unit{'s' if best.qty > 1 else ''}"]
    if dte is not None and dte <= 1:
        why.append("takes stock expiring soon")
    if best.unit_price < catalog[best.sku].list_price:
        why.append(f"${catalog[best.sku].list_price - best.unit_price:.2f}/unit under list")
    else:
        why.append("at list")
    return NashQuote(best, d_s, d_b, u_s, u_b, joint_best,
                     (u_s - d_s) + (u_b - d_b), why)


def liar_disclosure(wtp: dict[str, float], walk_cost: float
                    ) -> tuple[dict[str, float], float]:
    """The anchoring attack: understate every WTP, claim a free outside
    option. Shrinks the machine's believed sticker counterfactual and
    inflates the buyer's claimed disagreement."""
    return {sku: v * 0.55 for sku, v in wtp.items()}, 0.0

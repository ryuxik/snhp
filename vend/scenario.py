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


def buyer_value(wtp: dict[str, float], sku: str, qty: int) -> float:
    from vend.world import QTY_DECAY
    return sum(wtp[sku] * (QTY_DECAY ** (i - 1)) for i in range(1, qty + 1))


def outside_surplus(wtp: dict[str, float], walk_cost: float,
                    catalog) -> float:
    """Best surplus at the bodega (list × markup, − the walk)."""
    best = 0.0
    for sku, listing in catalog.items():
        for n in range(1, QTY_CAP + 1):
            s = buyer_value(wtp, sku, n) - n * listing.list_price * 1.15
            best = max(best, s - walk_cost)
    return best


def sticker_choice(wtp: dict[str, float], state: MachineState
                   ) -> tuple[str | None, int]:
    """What this buyer would purchase from the list-price board (their best
    positive-surplus bundle among in-stock SKUs), or nothing."""
    best, pick = 0.0, (None, 0)
    for sku, listing in state.listings.items():
        stock = state.stock(sku)
        for n in range(1, min(QTY_CAP, stock) + 1):
            s = buyer_value(wtp, sku, n) - n * listing.list_price
            if s > best:
                best, pick = s, (sku, n)
    return pick


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


def expected_list_demand(state: MachineState, sku: str, *,
                         dow_mult: float = 1.0, mult_hat: float = 1.0,
                         share: float | None = None) -> float:
    """Expected rest-of-day units of `sku` demanded AT LIST price — the
    machine's forecast from the operator's DEMAND ESTIMATE, scaled by what
    it can observe: the public calendar (dow_mult), today's inferred crowd
    (mult_hat, Gamma–Poisson from arrivals), and the SKU's demand share
    learned from the machine's own realized sales (regime-consistent — the
    fix for P1's static-world displacement forecast). The per-arrival base
    curve is cached per (sku, estimate, list)."""
    from vend.world import WTP_MU
    listing = state.listings[sku]
    n = len(state.listings)
    mu_est = listing.wtp_mu_est or WTP_MU[sku]
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
               share_fn=None) -> NashQuote:
    """Nash bargaining over the enumerated outcome space, on the DISCLOSED
    buyer utilities. Machine surplus is measured against its sticker
    counterfactual; buyer surplus against their claimed outside option.
    dow_mult / mult_hat / share_fn carry the machine's observable demand
    context into the shadow prices (defaults reproduce the P1 setting)."""
    catalog = state.listings
    n = len(catalog)
    _share = share_fn if share_fn is not None else (lambda s: 1.0 / n)
    ctx = lambda sku: {"dow_mult": dow_mult, "mult_hat": mult_hat,
                       "share": _share(sku)}
    d_b = max(0.0, outside_surplus(disclosed_wtp, disclosed_walk_cost, catalog))
    st_sku, st_qty = sticker_choice(disclosed_wtp, state)
    # The sticker counterfactual is valued with the SAME shadow-priced
    # margin function — a list sale of scarce stock displaces another list
    # sale, so its incremental value is ~0 and both sides of the
    # comparison stay consistent.
    d_s = (machine_margin(state, Outcome(st_sku, st_qty,
                                         catalog[st_sku].list_price),
                          **ctx(st_sku))
           if st_sku else 0.0)

    best, best_prod = None, 0.0
    joint_best = 0.0
    for o in enumerate_outcomes(state):
        u_s = machine_margin(state, o, **ctx(o.sku))
        u_b = buyer_value(disclosed_wtp, o.sku, o.qty) - o.qty * o.unit_price
        gs, gb = u_s - d_s, u_b - d_b
        if gs >= 0 and gb >= 0:
            joint_best = max(joint_best, gs + gb)
            prod = gs * gb
            if prod > best_prod:
                best, best_prod = o, prod

    if best is None:
        return NashQuote(None, d_s, d_b, 0.0, 0.0, joint_best, 0.0, [])

    u_s = machine_margin(state, best, **ctx(best.sku))
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

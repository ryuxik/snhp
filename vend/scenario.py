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


from vend.world import best_bundle, bundle_value as buyer_value


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
                         emp_daily: float | None = None,
                         traffic_scale: float = 1.0) -> float:
    """Expected rest-of-day units of `sku` demanded AT LIST price — the
    machine's forecast from the operator's DEMAND ESTIMATE, scaled by what
    it can observe: the public calendar (dow_mult), today's inferred crowd
    (mult_hat, Gamma–Poisson from arrivals), and the SKU's demand share
    learned from the machine's own realized sales (regime-consistent — the
    fix for P1's static-world displacement forecast). When `emp_daily` is
    given (the learner's EWMA of realized units/day in THIS arm's regime),
    the level comes from lived history instead of the structural formula —
    the forecast can no longer assume a world the mechanism abolished.
    The per-arrival base curve is cached per (sku, estimate, list).

    `traffic_scale`: the calibrated-traffic knob (vend.world.WorldConfig).
    The STRUCTURAL branch below is built off the hot-profile HOURLY_RATE
    table (world.rate_at), so at a thinned machine it must be scaled down
    too, or a cold-start SKU (no realized sales yet — exactly what happens
    for slow SKUs at 7-8 vends/day) would see a ~1/traffic_scale-inflated
    demand estimate, read all its own stock as list-bound ('excess' ≈ 0),
    and refuse every discount until it happens to sell once. The regime-
    consistent `emp_daily` branch is already built from REALIZED sales (at
    the machine's true, already-thinned rate) — scaling it again would be
    double-counting, so it's deliberately excluded."""
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
    return (base * (share if share is not None else 1.0 / n)
            * dow_mult * mult_hat * traffic_scale)


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
               min_gain: float = 0.0, min_gain_frac: float = 0.0,
               traffic_scale: float = 1.0,
               seller_weight: float = 0.5) -> NashQuote:
    """Nash bargaining over the enumerated outcome space, on the DISCLOSED
    buyer utilities. Machine surplus is measured against its sticker
    counterfactual; buyer surplus against their claimed outside option.
    dow_mult / mult_hat / share_fn carry the machine's observable demand
    context into the shadow prices (defaults reproduce the P1 setting).
    `traffic_scale` scales the cold-start structural demand estimate only
    (see expected_list_demand) — irrelevant once a SKU has sold and the
    regime-consistent emp_daily estimate takes over.
    `allowed` (Outcome → bool) restricts the outcome space — e.g. to the
    intent's SKU when the buyer forbids substitutes.

    `seller_weight` ∈ [0.5, 1.0] is the seller's bargaining weight in the
    GENERALIZED (asymmetric) Nash split: the chosen outcome maximizes
    gs**w · gb**(1-w) where gs, gb are the seller/buyer gains ABOVE their
    disagreement points. w=0.5 is the symmetric Nash split (the default);
    w=1.0 hands the seller ALL surplus above the buyer's disagreement (the
    buyer is held exactly at their floor). The tilt only reallocates surplus
    ABOVE the disagreement — feasibility still requires gs ≥ 0 AND gb ≥ 0,
    so it never prices below the buyer's floor, and the outcome space is
    still discount-only (floor…list), so it never prices above the sticker.
    This is the split-tilt monetization knob: how much of the jointly-created
    surplus the merchant keeps as seller profit (mapped against the
    CS-crosses-zero and IC-breaks frontier in tilt.py).

    Since the engine flip this is a thin delegation: the search lives in the
    general offer-graph engine (core.engine.quote via the core.adapters.vend
    projection). The bespoke body was deleted after the golden gates proved
    the engine reproduces it on the shipped trajectories (100% of 8,000+
    replayed quotes; committed sim totals byte-exact — see
    core/adapters/tests/test_vend_golden.py). Known boundary: at EXACT
    decimal ties on the min-gain buffer the two implementations' one-ulp-
    different float expression trees could disagree (7/123,200 quotes in the
    old block-flywheel sweep); the affected artifacts were re-pinned at the
    flip. Import is deferred to keep the module graph acyclic (the adapter
    imports this module's helpers)."""
    from core.adapters.vend import engine_nash_quote
    return engine_nash_quote(state, disclosed_wtp, disclosed_walk_cost,
                             dow_mult=dow_mult, mult_hat=mult_hat,
                             share_fn=share_fn, allowed=allowed,
                             daily_fn=daily_fn, min_gain=min_gain,
                             min_gain_frac=min_gain_frac,
                             traffic_scale=traffic_scale,
                             seller_weight=seller_weight)


def strategic_disclosure(wtp: dict[str, float], walk_cost: float,
                         wtp_factor: float = 0.55,
                         zero_walk: bool = True
                         ) -> tuple[dict[str, float], float]:
    """A parameterized misreport: scale every disclosed WTP by wtp_factor
    (<1 understates/anchors, >1 overstates) and optionally claim a free
    outside option. The attack battery sweeps this space to find the
    buyer's BEST-RESPONSE deviation — 'IC against one deviation isn't IC'."""
    return ({sku: v * wtp_factor for sku, v in wtp.items()},
            0.0 if zero_walk else walk_cost)


def liar_disclosure(wtp: dict[str, float], walk_cost: float
                    ) -> tuple[dict[str, float], float]:
    """The canonical anchoring attack (H3): understate + free outside."""
    return strategic_disclosure(wtp, walk_cost, 0.55, True)


# ── the harder deviation class (Task #68B) ─────────────────────────────────
# The committed liar battery is a UNIFORM WTP scale over ALL SKUs, applied on
# EVERY day regardless of state. That dilutes the exploit: on scarce/scarce-SKU
# days the discount-only shadow floor pins the price at list (§3 cond. a), so a
# uniform lie both (i) cannot move the price AND (ii) costs the buyer their
# board disagreement — the loss on those days averages out any gain on the rare
# excess day. Two sharper deviations the pooled mean cannot see:


def adaptive_disclosure(state: MachineState, wtp: dict[str, float],
                        walk_cost: float, *, factor: float = 0.55,
                        stock_mult: float = 1.2, zero_walk: bool = True
                        ) -> tuple[dict[str, float], float]:
    """STATE-CONDITIONED understatement: scale SKU s's disclosed WTP by
    `factor` ONLY where its VISIBLE stock is high (`stock(s) >= stock_mult ·
    par_stock(s)`) — i.e. exactly the SKUs likely to be in shadow-price
    EXCESS, where a below-list quote is feasible and a WTP report can move the
    price. Truthful on scarce SKUs (where cond. (a) pins the price at list
    regardless of report, so a lie only forfeits the board disagreement).

    This is the decisive deviation the uniform sweep dilutes: it concentrates
    the WTP lie exactly where a lie could bite, on the visible signal (stock)
    the buyer's agent can actually observe. `stock_mult=1.2` ⇒ "visibly above
    a full-par shelf" (a glut/soft day). `zero_walk` claims a free outside
    option independently (the §3 cond.-(d) free-walk channel)."""
    disc = {}
    for s, v in wtp.items():
        par = state.listings[s].par_stock
        disc[s] = v * factor if state.stock(s) >= stock_mult * par else v
    return disc, (0.0 if zero_walk else walk_cost)


def persku_disclosure(wtp: dict[str, float], walk_cost: float, *,
                      targets, factor: float = 0.55, zero_walk: bool = True
                      ) -> tuple[dict[str, float], float]:
    """NON-UNIFORM misreport: understate only the SKUs in `targets` (a set) by
    `factor`, truthful on the rest — the natural attack on PER-SKU shadow
    pricing. The sharpest instance is `targets = {the buyer's own favorite}`:
    lie precisely about the one good you want cheap, disclose the rest exactly
    (so the disagreement collapse is confined to the SKU you were going to buy
    anyway, not spread across goods you weren't)."""
    disc = {s: (v * factor if s in targets else v) for s, v in wtp.items()}
    return disc, (0.0 if zero_walk else walk_cost)

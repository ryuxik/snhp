"""A deterministic pseudo-random offer-graph generator for the property
tests. Pure stdlib (random.Random(seed) — no hypothesis, no new deps).

`generate(seed)` returns a fully-wired `Case`: an OfferGraph (random dims of
each kind, random priced options), a SeparableBuyer, a ShopState, and a
QuoteOpts — everything the engine needs. Bounds are deliberately small so
the cartesian enumeration stays cheap (the whole property suite runs in a
second or so) while still exercising every dimension kind and cost component.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from core.cost import (capacity_relief, compose, const, salvage_on_expiry,
                       scarcity_shadow)
from core.deps import DepGraph
from core.engine import QuoteOpts, SeparableBuyer
from core.offer_graph import (DimKind, Dimension, Negotiability, Option,
                              OfferGraph)
from core.state import ShopState


@dataclass
class Case:
    graph: OfferGraph
    state: ShopState
    buyer: SeparableBuyer
    opts: QuoteOpts


def _boba_relief(mult: float):
    """A capacity_relief fn (boba-style): a deferred, non-immediate slot earns
    a per-unit credit. Reads the config's fulfillment option straight off the
    graph so it composes with any state."""
    def fn(graph, state, config, qty):
        for d in graph.dims:
            if d.kind == DimKind.FULFILLMENT:
                opt = d.option(config[d.id])
                if not opt.immediate and opt.slot_ticks > 0:
                    return qty * mult
        return 0.0
    return fn


def generate(seed: int) -> Case:
    rng = random.Random(seed)

    dims: list[Dimension] = []
    values: dict = {}
    inventory: dict = {}
    expected_demand: dict = {}
    expiring: set = set()
    use_scarcity = False
    use_salvage = False
    use_relief = False

    # --- CHOICE dims (at least one, so there's always a priced good) ------
    n_choice = rng.randint(1, 2)
    for ci in range(n_choice):
        did = f"choice{ci}"
        n_opt = rng.randint(2, 3)
        opts = []
        # a CHOICE dim may carry finite stock → scarcity_shadow
        stocked = rng.random() < 0.4
        for oi in range(n_opt):
            oid = f"{did}_o{oi}"
            cost = round(rng.uniform(0.2, 2.0), 2)
            # list strictly above cost most of the time (room to discount);
            # occasionally at/below so the floors_at_list path is exercised
            price = round(cost + rng.uniform(-0.3, 4.0), 2)
            perish = rng.random() < 0.3
            salv = round(rng.uniform(0.0, cost), 2) if perish else 0.0
            # stocked CHOICE options are HARD stock-limited (A1) as well as
            # soft-shadow-priced (scarcity_shadow) — mirrors vend, where a
            # sku's stock both caps qty and shadow-prices displacement.
            opts.append(Option(id=oid, price_delta=price, unit_cost=cost,
                               perishable=perish, salvage=salv,
                               stock_limited=stocked))
            values[(did, oid)] = round(rng.uniform(0.0, 6.0), 2)
            if perish and rng.random() < 0.5:
                use_salvage = True
                if rng.random() < 0.5:
                    expiring.add(oid)
            if stocked:
                # min stock 1 so qty=1 is always available; qty>stock is the
                # gated case we want to exercise (stock 1, qty_cap 3 → 2,3 drop)
                inventory[oid] = round(rng.uniform(1.0, 4.0), 1)
                expected_demand[oid] = round(rng.uniform(0.0, 5.0), 1)
        if stocked:
            use_scarcity = True
        dims.append(Dimension(id=did, kind=DimKind.CHOICE, options=tuple(opts)))

    # --- ADDON dim (optional) ---------------------------------------------
    if rng.random() < 0.7:
        did = "addon0"
        n_opt = rng.randint(1, 3)
        opts = []
        for oi in range(n_opt):
            oid = f"{did}_o{oi}"
            cost = round(rng.uniform(0.0, 1.2), 2)
            price = round(cost + rng.uniform(-0.2, 2.0), 2)
            perish = rng.random() < 0.3
            salv = round(rng.uniform(0.0, cost), 2) if perish else 0.0
            opts.append(Option(id=oid, price_delta=price, unit_cost=cost,
                               perishable=perish, salvage=salv))
            values[(did, oid)] = round(rng.uniform(0.0, 2.5), 2)
            if perish and rng.random() < 0.5:
                use_salvage = True
                if rng.random() < 0.5:
                    expiring.add(oid)
        dims.append(Dimension(id=did, kind=DimKind.ADDON, options=tuple(opts)))

    # --- PREFERENCE dim (optional; ZERO cost gradient by construction) ----
    if rng.random() < 0.6:
        did = "pref0"
        n_opt = rng.randint(2, 3)
        opts = tuple(Option(id=f"{did}_o{oi}", price_delta=0.0, unit_cost=0.0)
                     for oi in range(n_opt))
        dims.append(Dimension(id=did, kind=DimKind.PREFERENCE, options=opts,
                              negotiable=Negotiability.AUTO))
        # preference options carry no dollar value (a costless customization)

    # --- FULFILLMENT dim (optional; an immediate + a deferred slot) -------
    capacity: dict = {}
    if rng.random() < 0.5:
        did = "ful0"
        slots = [Option(id=f"{did}_now", price_delta=0.0, immediate=True,
                        slot_ticks=0)]
        for s in (3, 6):
            if rng.random() < 0.7:
                slots.append(Option(id=f"{did}_d{s}", price_delta=0.0,
                                    immediate=False, slot_ticks=s))
                # sometimes a tight slot so the capacity gate (A1) drops it
                if rng.random() < 0.5:
                    capacity[s] = rng.randint(0, 2)
        dims.append(Dimension(id=did, kind=DimKind.FULFILLMENT,
                              options=tuple(slots)))
        # deferral disutility to the buyer, and relief credit to the seller
        use_relief = rng.random() < 0.6

    # --- QUANTITY dim (optional) ------------------------------------------
    if rng.random() < 0.7:
        dims.append(Dimension(id="qty", kind=DimKind.QUANTITY,
                              qty_cap=rng.randint(1, 3)))

    # --- cost model: compose whatever the graph needs ---------------------
    components = [const()]
    if use_salvage:
        components.append(salvage_on_expiry())
    if use_scarcity:
        components.append(scarcity_shadow())
    if use_relief:
        components.append(capacity_relief(_boba_relief(round(rng.uniform(0.1, 1.0), 2))))
    graph = OfferGraph(dims=dims, deps=DepGraph(), cost=compose(*components),
                       name=f"gen{seed}")

    # --- buyer ------------------------------------------------------------
    buyer = SeparableBuyer(
        values=values,
        qty_decay=round(rng.uniform(0.1, 0.8), 2),
        outside=round(rng.uniform(0.0, 4.0), 2),
        balk=round(rng.uniform(0.0, 0.6), 2) if rng.random() < 0.5 else 0.0,
        defer={0: 0.0, 3: round(rng.uniform(0.0, 1.5), 2),
               6: round(rng.uniform(0.0, 3.0), 2)},
    )

    state = ShopState(tick=rng.randint(0, 60), inventory=inventory,
                      expected_demand=expected_demand, expiring=expiring,
                      capacity=capacity)

    opts = QuoteOpts(
        min_price_frac=(round(rng.uniform(0.0, 0.6), 2) if rng.random() < 0.5
                        else 0.0),
        min_gain_abs=round(rng.uniform(0.0, 0.5), 2),
        min_gain_frac=round(rng.uniform(0.0, 0.2), 2),
        qty_appetite=rng.random() < 0.5,
        quote_lookers=rng.random() < 0.7,
        seller_weight=(0.5 if rng.random() < 0.5
                       else round(rng.uniform(0.5, 1.0), 2)),
        price_rungs=rng.choice([4, 8, 12]),
    )
    return Case(graph=graph, state=state, buyer=buyer, opts=opts)

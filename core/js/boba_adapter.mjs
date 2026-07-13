/* boba_adapter.mjs — boba as a core OfferGraph (mirror of core/adapters/boba.py).
 *
 * Structural 1:1 port of the Python adapter.  Because there is no JS boba world
 * inside core/js, the adapter is parameterized by a `world` object that supplies
 * boba's constants and live-state helpers (the same names boba/world.py exports):
 *
 *   world.DRINK_PRICE, world.DRINK_COST      (obj: id -> number)
 *   world.TOP_PRICE,   world.TOP_COST        (obj: id -> number)
 *   world.QTY_CAP, world.TICKS_PER_DAY       (number)
 *   world.capacity_relief(bobaState, qty, slot_ticks) -> number
 *   world.slot_capacity(bobaState, slot_tick)         -> number
 *   world.outside_surplus(consumer)                   -> number
 *   world.balk_prob(bobaState)                        -> number
 *   world.pearls_expiring_excess(bobaState)           -> bool
 *
 * The fidelity harness (F1) does NOT use this module — it rebuilds generic
 * graphs straight from the serialized fixture.  This adapter is the Phase-4
 * successor path (full HeyTea menu on the general engine); it is included here
 * to mirror the Python module and is exercised by Phase 4, not by node --test.
 */
import { DimKind, Dimension, OfferGraph, Option } from "./offer_graph.mjs";
import {
  compose,
  constComp,
  salvageOnExpiry,
  capacityRelief,
} from "./cost.mjs";
import { DepGraph } from "./deps.mjs";
import { QuoteOpts, SeparableBuyer, quote as coreQuote } from "./engine.mjs";
import { ShopState } from "./state.mjs";

export const PICKUP_SLOTS = [
  ["now", true, 0],
  ["d30", false, 3],
  ["d60", false, 6],
];
const NEG_INF = -Infinity;
const key = (dimId, optId) => `${dimId}\u0000${optId}`;

function relief(world) {
  // capacity_relief credit for the config's fulfillment slot — boba's
  // r = world.capacity_relief(bobaState, qty, slot_ticks).
  return (graph, state, config, qty) => {
    const bobaState = state.extra && state.extra.boba;
    if (!bobaState) return 0.0;
    let slotTicks = 0;
    for (const d of graph.dims) {
      if (d.kind === DimKind.FULFILLMENT) {
        slotTicks = d.option(config[d.id]).slot_ticks;
        break;
      }
    }
    if (slotTicks <= 0) return 0.0;
    return world.capacity_relief(bobaState, qty, slotTicks);
  };
}

export function buildBobaGraph(world) {
  const drink = new Dimension(
    "drink",
    DimKind.CHOICE,
    Object.keys(world.DRINK_PRICE).map(
      (d) => new Option({ id: d, label: d, price_delta: world.DRINK_PRICE[d], unit_cost: world.DRINK_COST[d] })
    )
  );
  const tops = new Dimension(
    "tops",
    DimKind.ADDON,
    Object.keys(world.TOP_PRICE).map(
      (t) =>
        new Option({
          id: t,
          label: t,
          price_delta: world.TOP_PRICE[t],
          unit_cost: world.TOP_COST[t],
          perishable: t === "pearls",
          salvage: 0.0,
          stock_limited: t === "pearls",
        })
    )
  );
  const pickup = new Dimension(
    "pickup",
    DimKind.FULFILLMENT,
    PICKUP_SLOTS.map(([name, imm, st]) => new Option({ id: name, immediate: imm, slot_ticks: st }))
  );
  const qty = new Dimension("qty", DimKind.QUANTITY, [], world.QTY_CAP);
  return new OfferGraph({
    dims: [drink, tops, pickup, qty],
    deps: new DepGraph(),
    cost: compose(constComp(), salvageOnExpiry(), capacityRelief(relief(world))),
    name: "boba",
  });
}

// Project a live boba world state onto the generic ShopState.
export function shopState(world, bobaState, { deferSlots = true, salvage = true } = {}) {
  const inventory = { pearls: Number(bobaState.pearl_stock()) };
  const expiring = new Set(salvage && world.pearls_expiring_excess(bobaState) ? ["pearls"] : []);
  const capacity = new Map();
  for (const st of [3, 6]) {
    if (deferSlots && bobaState.tick + st < world.TICKS_PER_DAY) {
      capacity.set(st, world.slot_capacity(bobaState, bobaState.tick + st));
    } else {
      capacity.set(st, NEG_INF);
    }
  }
  return new ShopState({ tick: bobaState.tick, inventory, capacity, expiring, extra: { boba: bobaState } });
}

export function buyerFor(world, bobaState, consumer, outsideConsumer = null, { marketFloor = false } = {}) {
  let sOut = world.outside_surplus(outsideConsumer !== null ? outsideConsumer : consumer);
  if (marketFloor) sOut = Math.min(sOut, world.outside_surplus(consumer));
  const values = new Map();
  for (const d of Object.keys(world.DRINK_PRICE)) values.set(key("drink", d), consumer.wtp[d]);
  for (const t of Object.keys(world.TOP_PRICE)) values.set(key("tops", t), consumer.top_wtp[t]);
  const defer = new Map([0, 3, 6].map((st) => [st, consumer.defer_cost(st)]));
  return new SeparableBuyer({
    values,
    qty_decay: consumer.qty_decay,
    outside: sOut,
    balk: world.balk_prob(bobaState),
    defer,
  });
}

// Build cart_nash's EXACT (incomplete) search space as a search_filter.
export function cartNashSearchFilter(world, bobaState, consumer, { salvage = true } = {}) {
  const ceff = {};
  for (const t of Object.keys(world.TOP_PRICE))
    ceff[t] = salvage ? world.top_c_eff(bobaState, t) : world.TOP_COST[t];
  const ranked = Object.keys(world.TOP_PRICE)
    .filter((t) => consumer.top_wtp[t] > ceff[t])
    .sort((a, b) => consumer.top_wtp[b] - ceff[b] - (consumer.top_wtp[a] - ceff[a]));
  const allowedTops = new Set();
  for (let i = 0; i <= ranked.length; i++) allowedTops.add(ranked.slice(0, i).slice().sort().join(","));
  const allowedDrinks = new Set(
    Object.keys(world.DRINK_PRICE).filter((d) => consumer.wtp[d] > world.DRINK_COST[d])
  );
  return (graph, state, buyer, config) => {
    if (!allowedDrinks.has(config.drink)) return false;
    const t = (config.tops || []).slice().sort().join(",");
    return allowedTops.has(t);
  };
}

// core.engine.quote wearing cart_nash's config; returns the raw Quote (Phase 4
// wiring maps it to whatever receipt shape the UI needs).
export function engineCartNash(world, graph, bobaState, consumer, opts = {}) {
  const {
    minGainAbs = 0.25,
    minGainFrac = 0.1,
    deferSlots = true,
    salvage = true,
    quoteLookers = true,
    outsideConsumer = null,
    marketFloor = false,
    qtyAppetite = false,
    minPriceFrac = 0.0,
  } = opts;
  const state = shopState(world, bobaState, { deferSlots, salvage });
  const buyer = buyerFor(world, bobaState, consumer, outsideConsumer, { marketFloor });
  const quoteOpts = new QuoteOpts({
    min_price_frac: minPriceFrac,
    qty_appetite: qtyAppetite,
    qty_appetite_scope: qtyAppetite ? "choice" : "bundle",
    quote_lookers: quoteLookers,
    min_gain_abs: minGainAbs,
    min_gain_frac: minGainFrac,
    price_rungs: 8,
    seller_weight: 0.5,
    prune_free: true,
    search_filter: cartNashSearchFilter(world, bobaState, consumer, { salvage }),
  });
  return coreQuote(graph, state, buyer, { opts: quoteOpts });
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_boba_adapter = {
    buildBobaGraph,
    shopState,
    buyerFor,
    cartNashSearchFilter,
    engineCartNash,
  };
}

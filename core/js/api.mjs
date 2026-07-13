/* api.mjs — the thin public surface (mirror of core/api.py).
 *
 * buildGraph (alias compile) builds an OfferGraph from a declarative spec;
 * quote / priceConfig are the two entry points into the shared engine.
 *
 * The one JS-only addition versus core/api.py is the `capacity_relief_table`
 * cost token: Python's capacity_relief holds a live closure that cannot be
 * serialized, so the fixture dumper reduces it to a per-(slot_ticks, qty)
 * table and this builder reconstructs it (see cost.capacityReliefTable).
 */
import {
  DimKind,
  Negotiability,
  Option,
  Dimension,
  OfferGraph,
} from "./offer_graph.mjs";
import {
  compose,
  constComp,
  salvageOnExpiry,
  scarcityShadow,
  batchEconomies,
  capacityReliefTable,
  CompositeCost,
} from "./cost.mjs";
import { DepGraph } from "./deps.mjs";
import { quote as engineQuote, QuoteOpts } from "./engine.mjs";
import { profile as coreProfile } from "./profiler.mjs";

const KIND = {
  CHOICE: DimKind.CHOICE,
  ADDON: DimKind.ADDON,
  PREFERENCE: DimKind.PREFERENCE,
  FULFILLMENT: DimKind.FULFILLMENT,
  QUANTITY: DimKind.QUANTITY,
};

const NEG = {
  FREE: Negotiability.FREE,
  LEVER: Negotiability.LEVER,
  AUTO: Negotiability.AUTO,
};

function toOption(o) {
  if (o instanceof Option) return o;
  return new Option({
    id: o.id,
    label: o.label || "",
    price_delta: Number(o.price_delta || 0.0),
    stock_limited: Boolean(o.stock_limited || false),
    unit_cost: Number(o.unit_cost || 0.0),
    salvage: Number(o.salvage || 0.0),
    perishable: Boolean(o.perishable || false),
    immediate: o.immediate === undefined ? true : Boolean(o.immediate),
    slot_ticks: Number(o.slot_ticks || 0),
  });
}

const COST_TOKENS = {
  const: () => constComp(),
  salvage_on_expiry: () => salvageOnExpiry(),
  scarcity_shadow: () => scarcityShadow(),
  batch_economies: (a) => batchEconomies(a.setup, a.marginal === undefined ? null : a.marginal),
  capacity_relief_table: (a) => capacityReliefTable(a), // JS-only reconstruction
};

function buildCost(entries) {
  if (entries instanceof CompositeCost) return entries;
  const components = [];
  for (const e of entries) {
    if (typeof e === "string") {
      components.push(COST_TOKENS[e]({}));
    } else if (e && typeof e === "object") {
      const token = Object.keys(e)[0];
      components.push(COST_TOKENS[token](e[token]));
    } else {
      components.push(e); // a live component object
    }
  }
  return compose(...components);
}

export function buildGraph(spec) {
  const dims = [];
  for (const d of spec.dims || []) {
    const kind = typeof d.kind === "string" ? KIND[d.kind.toUpperCase()] : d.kind;
    const opts = (d.options || []).map(toOption);
    let neg = d.negotiable === undefined ? Negotiability.AUTO : d.negotiable;
    if (typeof neg === "string") neg = NEG[neg.toUpperCase()];
    dims.push(new Dimension(d.id, kind, opts, Number(d.qty_cap || 1), neg));
  }
  const dep = spec.deps || {};
  const deps = new DepGraph({
    valid_on: dep.valid_on || {},
    requires: dep.requires || {},
    excludes: dep.excludes || {},
  });
  const cost = buildCost(spec.cost || ["const"]);
  return new OfferGraph({ dims, deps, cost, name: spec.name || "" });
}

export const compile = buildGraph;

export function profile(graph, state, buyerSample) {
  return coreProfile(graph, state, buyerSample);
}

export function quote(graph, state, buyer, { config = null, opts = new QuoteOpts() } = {}) {
  return engineQuote(graph, state, buyer, { config, opts });
}

export function priceConfig(graph, state, buyer, config, opts = new QuoteOpts()) {
  return engineQuote(graph, state, buyer, { config, opts });
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_api = { buildGraph, compile, profile, quote, priceConfig };
}

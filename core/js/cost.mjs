/* cost.mjs — the pluggable, state-dependent cost model (mirror of core/cost.py).
 *
 * CostModel.quote(graph, state, config, qty) -> CostQuote { c_eff, credit,
 * floors_at_list }.  The verticals differ ONLY here; the components compose.
 *
 * Components (data markers interpreted by CompositeCost):
 *   const()               goods baseline: qty * sum(unit_cost)
 *   salvage_on_expiry()   a perishable option in state.expiring costs `salvage`
 *   scarcity_shadow()     finite stock: displaced units re-priced at list
 *   batch_economies(...)  c_eff(q) = setup + q*marginal
 *   capacity_relief(fn)   a `credit` (not a price) added to seller gain
 *
 * capacity_relief in Python holds an arbitrary closure; the JS fidelity path
 * receives it as a SERIALIZED per-(slot_ticks, qty) table (capacityReliefTable),
 * which is a faithful, JSON-safe representation of that closure's output (both
 * shipped relief fns factor as credit = g(slot_ticks, qty)).
 */
import { DimKind, selectedOptionIds } from "./offer_graph.mjs";

export class CostQuote {
  constructor(c_eff, credit = 0.0, floors_at_list = false) {
    this.c_eff = c_eff;
    this.credit = credit;
    this.floors_at_list = floors_at_list;
  }
}

// ── component factories ────────────────────────────────────────────────────
export const constComp = () => ({ type: "const" });
export const salvageOnExpiry = () => ({ type: "salvage" });
export const scarcityShadow = () => ({ type: "scarcity" });
export const batchEconomies = (setup, marginal = null) => ({ type: "batch", setup, marginal });

// A capacity_relief component whose credit is a function fn(graph,state,cfg,qty).
export const capacityRelief = (fn) => ({ type: "relief", fn });

// A capacity_relief component reconstructed from a serialized table:
//   table[slot_ticks][qty] = credit dollars
// applied by reading the config's FULFILLMENT slot_ticks and qty.
export function capacityReliefTable(table) {
  const norm = new Map();
  for (const [st, byQty] of Object.entries(table)) {
    const inner = new Map();
    for (const [q, c] of Object.entries(byQty)) inner.set(Number(q), c);
    norm.set(Number(st), inner);
  }
  const fn = (graph, state, config, qty) => {
    for (const d of graph.dims) {
      if (d.kind === DimKind.FULFILLMENT) {
        const st = d.option(config[d.id]).slot_ticks;
        const inner = norm.get(st);
        if (inner === undefined) return 0.0;
        const c = inner.get(qty);
        return c === undefined ? 0.0 : c;
      }
    }
    return 0.0;
  };
  return { type: "relief", fn };
}

export function _listValue(graph, config, qty) {
  let total = 0.0;
  for (const dim of graph.dims) {
    if (dim.kind === DimKind.QUANTITY) continue;
    for (const oid of selectedOptionIds(dim, config[dim.id])) total += dim.option(oid).price_delta;
  }
  return qty * total;
}

export class CompositeCost {
  constructor(...components) {
    this.components = components;
    this._const = components.some((c) => c.type === "const");
    this._salvage = components.some((c) => c.type === "salvage");
    this._scarcity = components.some((c) => c.type === "scarcity");
    this._batch = components.find((c) => c.type === "batch") || null;
    this._relief = components.filter((c) => c.type === "relief").map((c) => c.fn);
  }

  _unitCost(state, opt) {
    if (this._salvage && opt.perishable && state.expiring.has(opt.id)) return opt.salvage;
    return opt.unit_cost;
  }

  quote(graph, state, config, qty) {
    let goods = 0.0;
    let unitSum = 0.0; // sum of resolved unit costs (batch marginal)
    for (const dim of graph.dims) {
      if (dim.kind === DimKind.QUANTITY) continue;
      for (const oid of selectedOptionIds(dim, config[dim.id])) {
        const opt = dim.option(oid);
        const ce = this._unitCost(state, opt);
        unitSum += ce;
        if (
          this._scarcity &&
          dim.kind === DimKind.CHOICE &&
          Object.prototype.hasOwnProperty.call(state.inventory, opt.id)
        ) {
          const s = state.inventory[opt.id];
          const D = Object.prototype.hasOwnProperty.call(state.expected_demand, opt.id)
            ? state.expected_demand[opt.id]
            : 0.0;
          const excess = Math.max(0.0, s - D);
          const displaced = Math.min(qty, Math.max(0.0, qty - excess));
          goods += (qty - displaced) * ce + displaced * opt.price_delta;
        } else {
          goods += qty * ce;
        }
      }
    }

    let c_eff;
    if (this._batch !== null) {
      const marginal = this._batch.marginal !== null && this._batch.marginal !== undefined
        ? this._batch.marginal
        : unitSum;
      c_eff = this._batch.setup + qty * marginal;
    } else {
      c_eff = goods;
    }

    let credit = 0.0;
    for (const fn of this._relief) credit += fn(graph, state, config, qty);

    const listv = _listValue(graph, config, qty);
    return new CostQuote(c_eff, credit, c_eff >= listv - 1e-9);
  }
}

export function compose(...components) {
  return new CompositeCost(...components);
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_cost = {
    CostQuote,
    constComp,
    salvageOnExpiry,
    scarcityShadow,
    batchEconomies,
    capacityRelief,
    capacityReliefTable,
    CompositeCost,
    compose,
  };
}

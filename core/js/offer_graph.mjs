/* offer_graph.mjs — the typed offer graph (mirror of core/offer_graph.py).
 *
 * A configuration is a choice over a small, typed set of dimensions; the engine
 * prices any such configuration with the one shared skeleton.  This file owns
 * the dimension types, the Config helpers, and the deterministic config
 * enumeration whose ORDER is load-bearing (the Nash search breaks score ties to
 * the first-enumerated config, so JS must enumerate in the exact same order as
 * Python's itertools.product / itertools.combinations).
 */

export const MAX_ADDON_OPTIONS = 12;

export const DimKind = Object.freeze({
  CHOICE: "choice",
  ADDON: "addon",
  PREFERENCE: "preference",
  FULFILLMENT: "fulfillment",
  QUANTITY: "quantity",
});

export const Negotiability = Object.freeze({
  FREE: "free",
  LEVER: "lever",
  AUTO: "auto",
});

// code-point string compare (matches Python str sort for ASCII ids).
export const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

export class Option {
  constructor({
    id,
    label = "",
    price_delta = 0.0,
    stock_limited = false,
    unit_cost = 0.0,
    salvage = 0.0,
    perishable = false,
    immediate = true,
    slot_ticks = 0,
  }) {
    this.id = id;
    this.label = label;
    this.price_delta = price_delta;
    this.stock_limited = stock_limited;
    this.unit_cost = unit_cost;
    this.salvage = salvage;
    this.perishable = perishable;
    this.immediate = immediate;
    this.slot_ticks = slot_ticks;
  }
}

export class Dimension {
  constructor(id, kind, options = [], qty_cap = 1, negotiable = Negotiability.AUTO) {
    this.id = id;
    this.kind = kind;
    this.options = Array.from(options);
    this.qty_cap = qty_cap;
    this.negotiable = negotiable;
    this._by_id = new Map(this.options.map((o) => [o.id, o]));
    if (this.kind === DimKind.ADDON && this.options.length > MAX_ADDON_OPTIONS) {
      throw new Error(
        `ADDON dim ${id} has ${this.options.length} options (> ${MAX_ADDON_OPTIONS})`
      );
    }
  }

  option(oid) {
    const o = this._by_id.get(oid);
    if (o === undefined) throw new Error(`no option ${oid} on dim ${this.id}`);
    return o;
  }
}

// ── Config helpers ─────────────────────────────────────────────────────────
// A Config maps dim_id -> option id (CHOICE/PREFERENCE/FULFILLMENT)
//                       -> sorted string[] of option ids (ADDON)   [~ frozenset]
//                       -> int qty (QUANTITY)

export function normalizeConfig(cfg) {
  if (cfg === null || cfg === undefined) return null;
  const out = {};
  for (const k of Object.keys(cfg)) {
    const v = cfg[k];
    out[k] = Array.isArray(v) ? [...v].sort(cmp) : v instanceof Set ? [...v].sort(cmp) : v;
  }
  return out;
}

export function selectedOptionIds(dim, sel) {
  if (dim.kind === DimKind.QUANTITY) return [];
  if (dim.kind === DimKind.ADDON) return sel && sel.length ? [...sel].sort(cmp) : [];
  return sel !== null && sel !== undefined ? [sel] : [];
}

export function freezeConfig(cfg) {
  const parts = [];
  for (const k of Object.keys(cfg).sort(cmp)) {
    let v = cfg[k];
    if (Array.isArray(v) || v instanceof Set) v = [...v].sort(cmp).join(",");
    parts.push(`${k}=${v}`);
  }
  return parts.join("|");
}

export function qtyOf(graph, cfg) {
  for (const d of graph.dims) {
    if (d.kind === DimKind.QUANTITY) {
      const v = cfg[d.id];
      return v === undefined || v === null ? 1 : Math.trunc(v);
    }
  }
  return 1;
}

export function withQty(graph, cfg, qty) {
  const out = { ...cfg };
  for (const d of graph.dims) if (d.kind === DimKind.QUANTITY) out[d.id] = qty;
  return out;
}

// ── enumeration primitives (must match itertools exactly) ──────────────────
export function* combinations(arr, r) {
  const n = arr.length;
  if (r > n) return;
  const idx = Array.from({ length: r }, (_, i) => i);
  yield idx.map((i) => arr[i]);
  while (true) {
    let i = r - 1;
    while (i >= 0 && idx[i] === i + n - r) i--;
    if (i < 0) return;
    idx[i]++;
    for (let j = i + 1; j < r; j++) idx[j] = idx[j - 1] + 1;
    yield idx.map((i) => arr[i]);
  }
}

// cartesian product with the LAST list varying fastest (itertools.product order).
export function product(lists) {
  let result = [[]];
  for (const list of lists) {
    const next = [];
    for (const prefix of result) for (const item of list) next.push([...prefix, item]);
    result = next;
  }
  return result;
}

export class OfferGraph {
  constructor({ dims, deps = null, cost = null, name = "" }) {
    this.dims = Array.from(dims); // ORIGINAL order (load-bearing for float sums)
    this.name = name;
    this._profiled = false;
    if (deps === null) {
      // lazy import to avoid a cycle; default empty DepGraph
      this.deps = { is_valid: () => true };
    } else {
      this.deps = deps;
    }
    if (cost === null) {
      throw new Error("OfferGraph requires a cost model");
    }
    this.cost = cost;
  }

  dim(dimId) {
    for (const d of this.dims) if (d.id === dimId) return d;
    throw new Error(`no dim ${dimId}`);
  }

  // Every dependency-valid configuration, in the SAME deterministic order as
  // Python's enumerate_configs: dims sorted by id, ADDON subsets via
  // combinations (option order), QUANTITY 1..cap, others in option order,
  // product with the last sorted dim fastest.
  enumerateConfigs(pin = {}) {
    const dims = [...this.dims].sort((a, b) => cmp(a.id, b.id));
    const perDim = [];
    for (const d of dims) {
      if (Object.prototype.hasOwnProperty.call(pin, d.id)) {
        perDim.push([[d.id, pin[d.id]]]);
      } else if (d.kind === DimKind.ADDON) {
        const opts = d.options.map((o) => o.id);
        const subs = [];
        for (let r = 0; r <= opts.length; r++)
          for (const combo of combinations(opts, r)) subs.push([d.id, [...combo].sort(cmp)]);
        perDim.push(subs);
      } else if (d.kind === DimKind.QUANTITY) {
        const arr = [];
        for (let q = 1; q <= d.qty_cap; q++) arr.push([d.id, q]);
        perDim.push(arr);
      } else {
        perDim.push(d.options.map((o) => [d.id, o.id]));
      }
    }
    const out = [];
    for (const combo of product(perDim)) {
      const cfg = {};
      for (const [k, v] of combo) cfg[k] = v;
      if (this.deps.is_valid(this, cfg)) out.push(cfg);
    }
    return out;
  }
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_offer_graph = {
    DimKind,
    Negotiability,
    Option,
    Dimension,
    OfferGraph,
    normalizeConfig,
    selectedOptionIds,
    freezeConfig,
    qtyOf,
    withQty,
  };
}

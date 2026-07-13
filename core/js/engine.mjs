/* engine.mjs — the shared quote() (mirror of core/engine.py).
 *
 * The ONE Nash-floor search both verticals run: availability gates ->
 * disagreement point -> edge-pruned feasible configs -> rungs from the
 * state-dependent floor to list -> Nash split -> guards -> receipt.  Ported
 * line-for-line from core/engine.py; the formulas below must reproduce it.
 *
 * FIDELITY TRAPS handled here:
 *   * ROUNDING: _ceilCent / _rungs use pyround (Python round-half-to-even),
 *     NOT Math.round (half-up).  See pyround.mjs.
 *   * FLOAT COMPARE: the exact 1e-9 / 1e-12 epsilons from engine.py are kept.
 *   * ENUMERATION ORDER: config order comes from OfferGraph.enumerateConfigs,
 *     which mirrors itertools; score ties break to the first-enumerated config.
 *   * SUM ORDER: value/list/cost sums iterate graph.dims in ORIGINAL order and
 *     addon options in SORTED order, matching Python's byte-level float sums.
 *     (buyer.value's addon term is summed in sorted order — Python sums it in
 *     frozenset-hash order, an unreproducible last-ULP difference that never
 *     crosses a decision boundary; every other sum is exactly reproduced.)
 */
import {
  DimKind,
  Negotiability,
  normalizeConfig,
  qtyOf,
  withQty,
  selectedOptionIds,
  freezeConfig,
  cmp,
} from "./offer_graph.mjs";
import { profile } from "./profiler.mjs";
import { pyround } from "./pyround.mjs";

const key = (dimId, optId) => `${dimId}\u0000${optId}`;

// ── the buyer side ─────────────────────────────────────────────────────────
export function qtyLadder(decay, qty) {
  let s = 0.0;
  for (let i = 0; i < qty; i++) s += Math.pow(decay, i);
  return s;
}

export class SeparableBuyer {
  // values: Map keyed by key(dimId, optId) -> per-unit dollar value
  constructor({ values = new Map(), qty_decay = 0.15, outside = 0.0, balk = 0.0, defer = new Map() } = {}) {
    this.values = values instanceof Map ? values : new Map(Object.entries(values));
    this.qty_decay = qty_decay;
    this.outside = outside;
    this.balk = balk;
    this.defer = defer instanceof Map ? defer : new Map(Object.entries(defer).map(([k, v]) => [Number(k), v]));
  }

  _val(dimId, optId) {
    const v = this.values.get(key(dimId, optId));
    return v === undefined ? 0.0 : v;
  }

  value(graph, config) {
    let base = 0.0;
    let qty = 1;
    for (const d of graph.dims) {
      const sel = config[d.id];
      if (d.kind === DimKind.QUANTITY) {
        qty = sel !== null && sel !== undefined ? Math.trunc(sel) : 1;
      } else if (d.kind === DimKind.ADDON) {
        // sorted order (see the SUM ORDER trap note in the module header)
        const arr = sel ? [...sel].sort(cmp) : [];
        let tsum = 0.0;
        for (const o of arr) tsum += this._val(d.id, o);
        base += tsum;
      } else if (d.kind === DimKind.CHOICE || d.kind === DimKind.PREFERENCE) {
        if (sel !== null && sel !== undefined) base += this._val(d.id, sel);
      }
      // FULFILLMENT contributes no value
    }
    return base * qtyLadder(this.qty_decay, qty);
  }

  outside_surplus() {
    return this.outside;
  }

  balk_prob(/* state */) {
    return this.balk;
  }

  defer_cost(slot) {
    const v = this.defer.get(slot);
    return v === undefined ? 0.0 : v;
  }
}

// ── options & receipt ──────────────────────────────────────────────────────
export class QuoteOpts {
  constructor({
    min_price_frac = 0.0,
    min_gain_abs = 0.25,
    min_gain_frac = 0.1,
    qty_appetite = false,
    qty_appetite_scope = "bundle",
    quote_lookers = true,
    seller_weight = 0.5,
    price_rungs = 8,
    prune_free = true,
    search_filter = null,
  } = {}) {
    this.min_price_frac = min_price_frac;
    this.min_gain_abs = min_gain_abs;
    this.min_gain_frac = min_gain_frac;
    this.qty_appetite = qty_appetite;
    this.qty_appetite_scope = qty_appetite_scope;
    this.quote_lookers = quote_lookers;
    this.seller_weight = seller_weight;
    this.price_rungs = price_rungs;
    this.prune_free = prune_free;
    this.search_filter = search_filter;
  }
}

export class Quote {
  constructor({ config, price, listv, cost, value, save, seller_gain, buyer_gain, feasible, why, audit = {} }) {
    this.config = config;
    this.price = price;
    this.listv = listv;
    this.cost = cost;
    this.value = value;
    this.save = save;
    this.seller_gain = seller_gain;
    this.buyer_gain = buyer_gain;
    this.feasible = feasible;
    this.why = why;
    this.audit = audit;
  }
}

class Econ {
  constructor(qty, val, listv, cost, credit, floors, immediate, slot) {
    this.qty = qty;
    this.val = val;
    this.listv = listv;
    this.cost = cost;
    this.credit = credit;
    this.floors = floors;
    this.immediate = immediate;
    this.slot = slot;
  }
}

// ── per-config economics ────────────────────────────────────────────────────
function listValue(graph, config, qty) {
  let total = 0.0;
  for (const dim of graph.dims) {
    if (dim.kind === DimKind.QUANTITY) continue;
    for (const oid of selectedOptionIds(dim, config[dim.id])) total += dim.option(oid).price_delta;
  }
  return qty * total;
}

function fulfillment(graph, config) {
  for (const d of graph.dims) {
    if (d.kind === DimKind.FULFILLMENT) {
      const opt = d.option(config[d.id]);
      return [opt.immediate, opt.slot_ticks];
    }
  }
  return [true, 0];
}

function available(graph, state, config, qty) {
  for (const dim of graph.dims) {
    for (const oid of selectedOptionIds(dim, config[dim.id])) {
      const opt = dim.option(oid);
      if (opt.stock_limited && qty > Math.floor(state.stock(oid) + 1e-9)) return false;
    }
  }
  for (const dim of graph.dims) {
    if (dim.kind === DimKind.FULFILLMENT) {
      const opt = dim.option(config[dim.id]);
      if (!opt.immediate && state.capacity.has(opt.slot_ticks)) {
        if (state.capacity.get(opt.slot_ticks) < qty - 1e-9) return false;
      }
    }
  }
  return true;
}

function configEcon(graph, state, buyer, config) {
  const qty = qtyOf(graph, config);
  const val = buyer.value(graph, config);
  const lv = listValue(graph, config, qty);
  const cq = graph.cost.quote(graph, state, config, qty);
  const [immediate, slot] = fulfillment(graph, config);
  return new Econ(qty, val, lv, cq.c_eff, cq.credit, cq.floors_at_list, immediate, slot);
}

function exceedsAppetite(graph, state, buyer, config, qty, scope = "bundle") {
  if (scope === "choice") {
    const choiceOnly = {};
    let choiceCost = 0.0;
    for (const d of graph.dims) {
      if (d.kind === DimKind.QUANTITY) {
        choiceOnly[d.id] = 1;
      } else if (d.kind === DimKind.ADDON) {
        choiceOnly[d.id] = [];
      } else {
        const sel = config[d.id];
        choiceOnly[d.id] = sel;
        if (d.kind === DimKind.CHOICE && sel !== null && sel !== undefined)
          choiceCost += d.option(sel).unit_cost;
      }
    }
    const marginalValue = buyer.value(graph, choiceOnly) * Math.pow(buyer.qty_decay, qty - 1);
    return marginalValue < choiceCost; // strict, no eps (cart_nash)
  }
  const perUnit = buyer.value(graph, withQty(graph, config, 1));
  const marginalValue = perUnit * Math.pow(buyer.qty_decay, qty - 1);
  const cQ = graph.cost.quote(graph, state, config, qty).c_eff;
  const cQm1 = graph.cost.quote(graph, state, withQty(graph, config, qty - 1), qty - 1).c_eff;
  const marginalCost = cQ - cQm1;
  return marginalValue < marginalCost - 1e-12;
}

function matches(cfg, partial) {
  if (partial === null || partial === undefined) return true;
  for (const k of Object.keys(partial)) {
    const v = partial[k];
    const cv = cfg[k];
    const vIsSet = Array.isArray(v) || v instanceof Set;
    const cvIsSet = Array.isArray(cv) || cv instanceof Set;
    if (vIsSet || cvIsSet) {
      const a = [...(v || [])].sort(cmp).join(",");
      const b = [...(cv || [])].sort(cmp).join(",");
      if (a !== b) return false;
    } else if (cv !== v) {
      return false;
    }
  }
  return true;
}

// round UP to the next cent (never below input) — A2 floor guard.
function ceilCent(x) {
  return Math.ceil(pyround(x, 9) * 100 - 1e-9) / 100.0;
}

function rungs(lo, listv, floors, n) {
  const loC = ceilCent(lo);
  if (floors || loC >= listv || n <= 1) return [Math.min(pyround(listv, 2), listv)];
  const step = (listv - loC) / (n - 1);
  const out = [];
  for (let i = 0; i < n; i++) out.push(Math.min(Math.max(pyround(loC + i * step, 2), loC), listv));
  return out;
}

// ── FREE-dimension pruning (C1) ─────────────────────────────────────────────
function ensureProfiled(graph, state) {
  if (graph._profiled) return;
  const prof = profile(graph, state);
  for (const d of graph.dims) d.negotiable = prof[d.id];
  graph._profiled = true;
}

function prefPins(graph, state, buyer) {
  ensureProfiled(graph, state);
  const pins = {};
  for (const d of graph.dims) {
    if (d.kind !== DimKind.PREFERENCE || d.negotiable !== Negotiability.FREE) continue;
    let bestId = null;
    let bestV = null;
    for (const o of d.options) {
      const v = buyer.value(graph, { [d.id]: o.id });
      if (bestV === null || v > bestV) {
        bestId = o.id;
        bestV = v;
      }
    }
    pins[d.id] = bestId;
  }
  return pins;
}

function scoreGreater(a, b) {
  return a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
}

// ── the quote ──────────────────────────────────────────────────────────────
export function quote(graph, state, buyer, { config = null, opts = new QuoteOpts() } = {}) {
  config = normalizeConfig(config);
  const b = buyer.balk_prob(state);
  const surv0 = 1.0 - b;
  const sOut = buyer.outside_surplus();

  const pin = opts.prune_free ? prefPins(graph, state, buyer) : {};

  const cand = [];
  for (const c of graph.enumerateConfigs(pin)) {
    if (!matches(c, config)) continue;
    const q = qtyOf(graph, c);
    if (!available(graph, state, c, q)) continue;
    if (opts.qty_appetite && q > 1 && exceedsAppetite(graph, state, buyer, c, q, opts.qty_appetite_scope))
      continue;
    cand.push(c);
  }
  if (cand.length === 0) return null;

  const econCache = new Map();
  const econOf = (c) => {
    const k = freezeConfig(c);
    let e = econCache.get(k);
    if (e === undefined) {
      e = configEcon(graph, state, buyer, c);
      econCache.set(k, e);
    }
    return e;
  };

  // ── 1. disagreement point ─────────────────────────────────────────────
  let sMenu = null;
  let menuC = null;
  for (const c of cand) {
    const [immediate] = fulfillment(graph, c);
    if (!immediate) continue;
    const s = buyer.value(graph, c) - listValue(graph, c, qtyOf(graph, c));
    if (sMenu === null || s > sMenu) {
      sMenu = s;
      menuC = c;
    }
  }

  const menuBuyer = menuC !== null && sMenu > 0 && sMenu >= sOut;
  let dBuyer;
  let dSeller;
  if (menuBuyer) {
    const em = econOf(menuC);
    const marginMenu = surv0 * (em.listv - em.cost);
    dBuyer = surv0 * sMenu + (1.0 - surv0) * sOut;
    dSeller = marginMenu;
  } else {
    if (!opts.quote_lookers) return null; // IC HARD FLOOR
    dBuyer = sOut;
    dSeller = 0.0;
  }

  // ── 2–3. search configs x rungs for the best Nash split ────────────────
  let best = null;
  let bestScore = null;
  const w = opts.seller_weight;
  const sf = opts.search_filter;
  for (const c of cand) {
    if (sf !== null && sf !== undefined && !sf(graph, state, buyer, c)) continue;
    const e = econOf(c);
    const surv = e.immediate ? surv0 : 1.0;
    const defer = buyer.defer_cost(e.slot);
    const lo = Math.max(e.cost, opts.min_price_frac * e.listv);
    for (const p of rungs(lo, e.listv, e.floors, opts.price_rungs)) {
      const gs = surv * (p - e.cost) + e.credit - dSeller;
      const gb = surv * (e.val - p) + (1.0 - surv) * sOut - defer - dBuyer;
      if (gs >= -1e-9 && gb >= -1e-9) {
        const nash =
          w === 0.5 ? gs * gb : Math.pow(Math.max(0.0, gs), w) * Math.pow(Math.max(0.0, gb), 1.0 - w);
        const score = [nash, gs + gb];
        if (bestScore === null || scoreGreater(score, bestScore)) {
          best = { c, p, surv, defer, e };
          bestScore = score;
        }
      }
    }
  }

  if (best === null || (bestScore[0] <= 0 && bestScore[1] <= 1e-9)) {
    return fallback(graph, state, buyer, econCache, config, menuBuyer, menuC);
  }

  const { c, p, surv, defer, e } = best;
  // ── 4. guards ──────────────────────────────────────────────────────────
  if (p < e.cost - 1e-9) return fallback(graph, state, buyer, econCache, config, menuBuyer, menuC);
  const uS = surv * (p - e.cost) + e.credit;
  if (uS - dSeller < Math.max(opts.min_gain_abs, opts.min_gain_frac * e.listv))
    return fallback(graph, state, buyer, econCache, config, menuBuyer, menuC);

  const gs = uS - dSeller;
  const gb = surv * (e.val - p) + (1.0 - surv) * sOut - defer - dBuyer;
  const why = ["negotiated"];
  if (e.slot > 0) why.push(`+${e.slot}-tick deferred slot frees capacity`);
  if (p < e.listv - 1e-9) why.push(`$${(e.listv - p).toFixed(2)} under list`);
  else why.push("at list");
  return new Quote({
    config: c,
    price: p,
    listv: e.listv,
    cost: e.cost,
    value: e.val,
    save: e.listv - p,
    seller_gain: gs,
    buyer_gain: gb,
    feasible: true,
    why,
    audit: audit(surv, sOut, e.credit, defer, dBuyer, dSeller, e.val, e.cost),
  });
}

function audit(surv, s_out, credit, defer, d_buyer, d_seller, val, cost) {
  return { surv, s_out, credit, defer, d_buyer, d_seller, val, cost };
}

function isFull(graph, config) {
  return graph.dims.every((d) => Object.prototype.hasOwnProperty.call(config, d.id));
}

function econOrCompute(graph, state, buyer, econCache, cfg) {
  const k = freezeConfig(cfg);
  if (econCache.has(k)) return econCache.get(k);
  return configEcon(graph, state, buyer, cfg);
}

function atList(cfg, e, note) {
  return new Quote({
    config: cfg,
    price: e.listv,
    listv: e.listv,
    cost: e.cost,
    value: e.val,
    save: 0.0,
    seller_gain: 0.0,
    buyer_gain: 0.0,
    feasible: false,
    why: [note],
    audit: audit(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, e.val, e.cost),
  });
}

function fallback(graph, state, buyer, econCache, config, menuBuyer, menuC) {
  if (config !== null && config !== undefined && isFull(graph, config)) {
    const e = econOrCompute(graph, state, buyer, econCache, { ...config });
    return atList({ ...config }, e, "no discount beats list; at list");
  }
  if (menuBuyer) {
    const e = econCache.get(freezeConfig(menuC));
    return atList(menuC, e, "no deal beats the menu; buyer pays list");
  }
  return null;
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_engine = { SeparableBuyer, QuoteOpts, Quote, quote, qtyLadder };
}

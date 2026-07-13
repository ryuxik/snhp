/* profiler.mjs — the divergence profiler (mirror of core/profiler.py).
 *
 * Classify each dimension FREE / LEVER / AUTO by probing the cost model: hold
 * every other dim at a baseline, vary this dim across its options, look at the
 * spread in c_eff.  zero -> FREE, positive -> LEVER, can't-tell -> FREE
 * (AUTO conservative default).  Cost-only / buyer-independent.
 */
import { DimKind, Negotiability, qtyOf } from "./offer_graph.mjs";

const EPS = 1e-9;

function defaultConfig(graph) {
  const cfg = {};
  for (const d of graph.dims) {
    if (d.kind === DimKind.QUANTITY) cfg[d.id] = 1;
    else if (d.kind === DimKind.ADDON) cfg[d.id] = [];
    else cfg[d.id] = d.options[0].id;
  }
  return cfg;
}

function variants(dim, base) {
  const out = [];
  if (dim.kind === DimKind.QUANTITY) {
    for (const q of [1, Math.min(2, dim.qty_cap)]) {
      const c = { ...base };
      c[dim.id] = q;
      out.push(c);
    }
  } else if (dim.kind === DimKind.ADDON) {
    const c0 = { ...base };
    c0[dim.id] = [];
    out.push(c0);
    for (const o of dim.options) {
      const c = { ...base };
      c[dim.id] = [o.id];
      out.push(c);
    }
  } else {
    for (const o of dim.options) {
      const c = { ...base };
      c[dim.id] = o.id;
      out.push(c);
    }
  }
  return out;
}

function classify(graph, states, dim) {
  const base = defaultConfig(graph);
  const vs = variants(dim, base);
  if (vs.length < 2) return Negotiability.FREE; // AUTO -> FREE, nothing to vary
  let spread = 0.0;
  for (const st of states) {
    const costs = vs.map((c) => graph.cost.quote(graph, st, c, qtyOf(graph, c)).c_eff);
    spread = Math.max(spread, Math.max(...costs) - Math.min(...costs));
  }
  return spread > EPS ? Negotiability.LEVER : Negotiability.FREE;
}

export function profile(graph, state /* , buyerSample */) {
  const states = [state];
  const out = {};
  for (const d of graph.dims) out[d.id] = classify(graph, states, d);
  return out;
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_profiler = { profile };
}

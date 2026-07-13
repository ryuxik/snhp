/* deps.mjs — dependency edges between options (mirror of core/deps.py).
 *
 * valid_on[o]  = o may be selected only if ALL of these are present
 * requires[o]  = selecting o forces ALL of these to also be present
 * excludes[o]  = selecting o forbids ANY of these from being present
 *
 * An empty DepGraph (the verticals' default) admits every combination.
 */
import { selectedOptionIds } from "./offer_graph.mjs";

function toSetMap(obj) {
  const m = {};
  for (const [k, v] of Object.entries(obj || {})) m[k] = new Set(v);
  return m;
}

export class DepGraph {
  constructor({ valid_on = {}, requires = {}, excludes = {} } = {}) {
    this.valid_on = toSetMap(valid_on);
    this.requires = toSetMap(requires);
    this.excludes = toSetMap(excludes);
  }

  _selected(graph, config) {
    const chosen = new Set();
    for (const dim of graph.dims)
      for (const oid of selectedOptionIds(dim, config[dim.id])) chosen.add(oid);
    return chosen;
  }

  is_valid(graph, config) {
    const empty =
      Object.keys(this.valid_on).length === 0 &&
      Object.keys(this.requires).length === 0 &&
      Object.keys(this.excludes).length === 0;
    if (empty) return true; // fast path (hot loop of enumerateConfigs)
    const chosen = this._selected(graph, config);
    for (const o of chosen) {
      const need = this.valid_on[o];
      if (need && !isSubset(need, chosen)) return false;
      const req = this.requires[o];
      if (req && !isSubset(req, chosen)) return false;
      const exc = this.excludes[o];
      if (exc && intersects(exc, chosen)) return false;
    }
    return true;
  }
}

function isSubset(a, b) {
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

function intersects(a, b) {
  for (const x of a) if (b.has(x)) return true;
  return false;
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_deps = { DepGraph };
}

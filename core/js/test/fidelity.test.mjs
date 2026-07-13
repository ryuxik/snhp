/* fidelity.test.mjs — the F1 gate: Python<->JS engine equivalence.
 *
 * Loads core/js/test/fixtures.json (a battery of fully-serialized cases + the
 * Python engine's reference Quote), rebuilds each graph/state/buyer/opts in JS,
 * runs the JS quote(), and asserts the JS result matches Python: SAME chosen
 * config, price within $0.01, same feasible flag, same None/walk.
 *
 *   RUN:        node --test core/js/test/
 *   REGENERATE: python3 core/js/test/dump_fixtures.py     (see that file's header)
 *
 * The fixture is the Python engine's output frozen to JSON; if core/*.py or
 * core/adapters/boba.py changes, regenerate it (the header one-liner) so this
 * gate can't silently rot.
 *
 * Fidelity traps guarded by the port (see the mjs modules for detail):
 *   * rounding   — pyround.mjs reproduces Python round-half-to-even.
 *   * float cmp  — engine.mjs keeps the exact 1e-9 / 1e-12 epsilons.
 *   * config ser — addon sets are sorted arrays; canonicalConfig compares them.
 *   * -inf slots — capacity sentinels are decoded back to -Infinity.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { buildGraph } from "../api.mjs";
import { SeparableBuyer, QuoteOpts, quote } from "../engine.mjs";
import { ShopState } from "../state.mjs";
import { cmp } from "../offer_graph.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = JSON.parse(readFileSync(join(HERE, "fixtures.json"), "utf8"));

// ── decode helpers (mirror of dump_fixtures.enc_num) ───────────────────────
function decodeNum(x) {
  if (typeof x !== "string") return x;
  if (x === "inf") return Infinity;
  if (x === "-inf") return -Infinity;
  if (x === "nan") return NaN;
  return Number(x);
}

function buildState(s) {
  const inventory = {};
  for (const [k, v] of Object.entries(s.inventory)) inventory[k] = decodeNum(v);
  const expected_demand = {};
  for (const [k, v] of Object.entries(s.expected_demand)) expected_demand[k] = decodeNum(v);
  const capacity = new Map(s.capacity.map(([slot, v]) => [Number(slot), decodeNum(v)]));
  return new ShopState({
    tick: s.tick,
    inventory,
    capacity,
    expiring: new Set(s.expiring),
    expected_demand,
  });
}

function buildBuyer(b) {
  const values = new Map();
  for (const [dimId, optId, v] of b.values) values.set(`${dimId}\u0000${optId}`, decodeNum(v));
  const defer = new Map(b.defer.map(([slot, v]) => [Number(slot), decodeNum(v)]));
  return new SeparableBuyer({
    values,
    qty_decay: decodeNum(b.qty_decay),
    outside: decodeNum(b.outside),
    balk: decodeNum(b.balk),
    defer,
  });
}

function buildSearchFilter(sf) {
  if (sf === null || sf === undefined) return null;
  const allowedDrinks = new Set(sf.allowed_drinks);
  const canon = (arr) => (arr || []).slice().sort(cmp).join(",");
  const allowedTops = new Set(sf.allowed_top_sets.map((a) => canon(a)));
  const dDim = sf.drink_dim;
  const tDim = sf.tops_dim;
  return (graph, state, buyer, config) =>
    allowedDrinks.has(config[dDim]) && allowedTops.has(canon(config[tDim]));
}

function buildOpts(o) {
  return new QuoteOpts({
    min_price_frac: decodeNum(o.min_price_frac),
    min_gain_abs: decodeNum(o.min_gain_abs),
    min_gain_frac: decodeNum(o.min_gain_frac),
    qty_appetite: o.qty_appetite,
    qty_appetite_scope: o.qty_appetite_scope,
    quote_lookers: o.quote_lookers,
    seller_weight: decodeNum(o.seller_weight),
    price_rungs: o.price_rungs,
    prune_free: o.prune_free,
    search_filter: buildSearchFilter(o.search_filter),
  });
}

// ── canonical config comparison (frozensets <-> sorted arrays) ─────────────
function canonicalConfig(cfg) {
  if (cfg === null || cfg === undefined) return "<none>";
  const parts = [];
  for (const k of Object.keys(cfg).sort(cmp)) {
    let v = cfg[k];
    if (Array.isArray(v)) v = "[" + [...v].sort(cmp).join(",") + "]";
    parts.push(`${k}=${v}`);
  }
  return parts.join("|");
}

// ── the gate ───────────────────────────────────────────────────────────────
const PRICE_TOL = 0.01 + 1e-9;
let maxPriceDiff = 0;
const mismatches = [];

for (const c of FIX.cases) {
  const graph = buildGraph(c.graph);
  const state = buildState(c.state);
  const buyer = buildBuyer(c.buyer);
  const opts = buildOpts(c.opts);
  const q = quote(graph, state, buyer, { opts });

  const ref = c.reference;
  const label = `${c.kind}/${c.outcome}`;

  if (ref === null) {
    if (q !== null) {
      mismatches.push({ label, why: "expected walk (None), got a quote", got: canonicalConfig(q.config) });
    }
    continue;
  }
  if (q === null) {
    mismatches.push({ label, why: "expected a quote, got walk (None)", want: canonicalConfig(ref.config) });
    continue;
  }
  const wantCfg = canonicalConfig(ref.config);
  const gotCfg = canonicalConfig(q.config);
  const dp = Math.abs(q.price - decodeNum(ref.price));
  if (dp > maxPriceDiff) maxPriceDiff = dp;
  if (gotCfg !== wantCfg) {
    mismatches.push({ label, why: "config", want: wantCfg, got: gotCfg });
  } else if (dp > PRICE_TOL) {
    mismatches.push({ label, why: `price Δ$${dp.toFixed(4)}`, want: ref.price, got: q.price });
  } else if (q.feasible !== ref.feasible) {
    mismatches.push({ label, why: "feasible flag", want: ref.feasible, got: q.feasible });
  }
}

test(`F1 fidelity: JS matches Python on all ${FIX.cases.length} fixtures`, () => {
  const total = FIX.cases.length;
  const bad = mismatches.length;
  const rate = ((total - bad) / total) * 100;
  console.log(
    `F1: ${total - bad}/${total} match (${rate.toFixed(3)}%)  ` +
      `max price Δ $${maxPriceDiff.toFixed(6)}  outcomes=${JSON.stringify(FIX.outcomes)}`
  );
  if (bad) console.log("first mismatches:", JSON.stringify(mismatches.slice(0, 10), null, 2));
  // acceptance: >= 99.9% (ideally 100%)
  assert.ok(rate >= 99.9, `match rate ${rate.toFixed(3)}% < 99.9% (${bad}/${total} mismatched)`);
  assert.equal(bad, 0, `${bad}/${total} mismatches (expected 0)`);
});

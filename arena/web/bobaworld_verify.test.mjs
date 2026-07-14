/* bobaworld_verify.test.mjs — the boba-world drift gate (node --test; CI).
 *
 * arena/web/boba-world.mjs is the ONE JS-side copy of boba/world.py's math.
 * This file is what keeps it that way: it loads reference values computed from
 * the Python source of record (boba/world.py, boba/policies.py,
 * core/adapters/boba.py) and asserts the JS world reproduces them —
 * constants exactly, every derived quantity within 1e-9, and full priced
 * carts through the SAME core-engine path the pages run (world ->
 * boba_adapter -> engine.mjs quote) against Python's engine_cart_nash.
 *
 * The one documented looser bound: the appeal INVERSION (appealForList). Both
 * sides bisect the identical 28-step lattice, but Python's inner argmax is
 * scipy minimize_scalar (bounded, xatol=1e-5) while JS's golden-section runs
 * to machine precision — so the last lattice comparisons can flip and results
 * agree to a few lattice steps (~1e-8 relative, asserted at 1e-6 relative).
 * Everything downstream is checked with PYTHON'S exact appeals injected, so
 * the 1e-9 gate is independent of the inversion's optimizer tolerance.
 *
 *   RUN:        node --test arena/web/bobaworld_verify.test.mjs
 *   REGENERATE: python3 core/js/test/dump_fixtures.py
 *               (fixture is gitignored, regenerated from Python in CI — a
 *                stale committed fixture would hide drift)
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  makeWorld, erfc, sf, appealForList, deferCost, balkProb, expectedWaitMinutes,
  WTP_SIGMA, TOP_SIGMA, CROSS_DISCOUNT, GROUP_SHARE, GROUP_DECAY, SOLO_DECAY,
  QTY_CAP, OUTSIDE_MARKUP, TICKS_PER_DAY, OPEN_HOUR, BALK_SLOPE,
  BALK_LENGTH_HAZARD, BATCH_SERVINGS, BATCH_LIFE_TICKS, PEARL_RESTOCK_TRIGGER,
  BATCH_CLEARANCE_WINDOW, PEAK_STAFF_HOURS, HOURLY_RATE, HOURLY_WTP_MULT,
  FLEX_DEFER, RIGID_DEFER,
} from "./boba-world.mjs";
import { buildBobaGraph, engineCartNash } from "../../core/js/boba_adapter.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX_PATH = join(HERE, "..", "..", "core", "js", "test", "boba_world_fixtures.json");
let FIX;
try {
  FIX = JSON.parse(readFileSync(FIX_PATH, "utf8"));
} catch (e) {
  throw new Error(
    `missing/unreadable ${FIX_PATH} — regenerate it from the Python source of ` +
    `record first: python3 core/js/test/dump_fixtures.py  (${e.message})`,
  );
}

const TOL = 1e-9;
function close(a, b, tol, msg) {
  assert.ok(Number.isFinite(a) && Number.isFinite(b), `${msg}: non-finite (js=${a}, py=${b})`);
  assert.ok(Math.abs(a - b) <= tol, `${msg}: js=${a} py=${b} |diff|=${Math.abs(a - b)} > ${tol}`);
}

// the calibration world, with PYTHON'S exact appeals injected (menu entries
// carry `appeal`, which makeWorld honors) — the 1e-9 comparisons below are
// therefore independent of the inversion optimizer.
const world = makeWorld(FIX.menu);
const graph = buildBobaGraph(world);

function mkState(spec) {
  const scheduled = {};
  for (const [k, v] of Object.entries(spec.scheduled)) scheduled[Number(k)] = v;
  return {
    day: 0, tick: spec.tick, carry: 0.0, scheduled,
    queue: spec.queue.slice(),
    batches: spec.batches.map(([servings, expires]) => ({ servings, expires })),
    pearl_stock() { return this.batches.reduce((a, b) => a + b.servings, 0); },
  };
}

test("constants match boba/world.py exactly", () => {
  const c = FIX.constants;
  assert.equal(WTP_SIGMA, c.WTP_SIGMA);
  assert.equal(TOP_SIGMA, c.TOP_SIGMA);
  assert.equal(CROSS_DISCOUNT, c.CROSS_DISCOUNT);
  assert.equal(GROUP_SHARE, c.GROUP_SHARE);
  assert.equal(GROUP_DECAY, c.GROUP_DECAY);
  assert.equal(SOLO_DECAY, c.SOLO_DECAY);
  assert.equal(QTY_CAP, c.QTY_CAP);
  assert.equal(OUTSIDE_MARKUP, c.OUTSIDE_MARKUP);
  assert.equal(TICKS_PER_DAY, c.TICKS_PER_DAY);
  assert.equal(OPEN_HOUR, c.OPEN_HOUR);
  assert.equal(BALK_SLOPE, c.BALK_SLOPE);
  assert.equal(BALK_LENGTH_HAZARD, c.BALK_LENGTH_HAZARD);
  assert.equal(BATCH_SERVINGS, c.BATCH_SERVINGS);
  assert.equal(BATCH_LIFE_TICKS, c.BATCH_LIFE_TICKS);
  assert.equal(PEARL_RESTOCK_TRIGGER, c.PEARL_RESTOCK_TRIGGER);
  assert.equal(BATCH_CLEARANCE_WINDOW, c.BATCH_CLEARANCE_WINDOW);
  assert.deepEqual(PEAK_STAFF_HOURS, c.PEAK_STAFF_HOURS);
  for (const [h, v] of Object.entries(c.HOURLY_RATE)) assert.equal(HOURLY_RATE[Number(h)], v, `HOURLY_RATE[${h}]`);
  for (const [h, v] of Object.entries(c.HOURLY_WTP_MULT)) assert.equal(HOURLY_WTP_MULT[Number(h)], v, `HOURLY_WTP_MULT[${h}]`);
  for (const [s, v] of Object.entries(c.FLEX_DEFER)) assert.equal(FLEX_DEFER[Number(s)], v, `FLEX_DEFER[${s}]`);
  for (const [s, v] of Object.entries(c.RIGID_DEFER)) assert.equal(RIGID_DEFER[Number(s)], v, `RIGID_DEFER[${s}]`);
});

test("erfc matches Python math.erfc (double precision, incl. tails)", () => {
  for (const [x, ref] of FIX.erfc) {
    const j = erfc(x);
    const err = Math.abs(j - ref);
    const rel = ref !== 0 ? err / Math.abs(ref) : err;
    assert.ok(err <= 1e-15 || rel <= 1e-13, `erfc(${x}): js=${j} py=${ref} rel=${rel}`);
  }
});

test("lognormal survival _sf matches within 1e-13", () => {
  for (const [x, scale, sigma, ref] of FIX.sf) {
    const j = sf(x, scale, sigma);
    const err = Math.abs(j - ref);
    const rel = ref !== 0 ? err / Math.abs(ref) : err;
    assert.ok(err <= 1e-15 || rel <= 1e-13, `sf(${x},${scale},${sigma}): js=${j} py=${ref} rel=${rel}`);
  }
});

test("derived world facts match within 1e-9 (Python appeals injected)", () => {
  const f = FIX.world_facts;
  close(world.MEAN_DRINK_MARGIN, f.MEAN_DRINK_MARGIN, TOL, "MEAN_DRINK_MARGIN");
  close(world.PEARL_ATTACH_LIST, f.PEARL_ATTACH_LIST, TOL, "PEARL_ATTACH_LIST");
  assert.deepEqual(world.PEAK_HOURS, f.PEAK_HOURS, "PEAK_HOURS");
  for (const [h, v] of Object.entries(f.ecpa))
    close(world.expectedCupsPerArrival(Number(h)), v, TOL, `expected_cups_per_arrival(${h})`);
});

test("appeal inversion matches Python appeal_for_list (documented 1e-6 rel; scipy xatol bound)", () => {
  for (const inv of FIX.inversions) {
    const j = appealForList(inv.price, inv.cost, inv.sigma, inv.hour_mults);
    const rel = Math.abs(j - inv.appeal) / inv.appeal;
    assert.ok(rel <= 1e-6,
      `appealForList(${inv.price},${inv.cost},${inv.sigma},${inv.hour_mults}): js=${j} py=${inv.appeal} rel=${rel}`);
  }
});

test("live-state helpers match within 1e-9 (balk, wait, slot capacity, relief, pearls flag)", () => {
  FIX.states.forEach((ref, i) => {
    const st = mkState(ref.state);
    close(balkProb(st), ref.balk_prob, TOL, `state[${i}] balk_prob`);
    close(expectedWaitMinutes(st), ref.expected_wait, TOL, `state[${i}] expected_wait`);
    for (const [s, v] of Object.entries(ref.slot_capacity))
      close(world.slot_capacity(st, st.tick + Number(s)), v, TOL, `state[${i}] slot_capacity(+${s})`);
    for (const [qs, v] of Object.entries(ref.capacity_relief)) {
      const [q, s] = qs.split(",").map(Number);
      close(world.capacity_relief(st, q, s), v, TOL, `state[${i}] capacity_relief(${qs})`);
    }
    assert.equal(world.pearls_expiring_excess(st), ref.pearls_expiring_excess, `state[${i}] pearls_expiring_excess`);
  });
});

test(`priced carts: world -> adapter -> engine reproduces Python engine_cart_nash (${FIX.cart_cases.length} cases)`, () => {
  let deals = 0, walks = 0;
  for (const [ci, cse] of FIX.cart_cases.entries()) {
    const ref = FIX.states[cse.state_idx];
    const st = mkState(ref.state);
    const c = {
      fav: cse.consumer.fav,
      wtp: { ...cse.consumer.wtp },
      top_wtp: { ...cse.consumer.top_wtp },
      flexible: cse.consumer.flexible,
      qty_decay: cse.consumer.qty_decay,
      defer_cost(slot) { return deferCost(this, slot, 1); },
    };
    const q = engineCartNash(world, graph, st, c, {
      qtyAppetite: cse.opts.qty_appetite,
      minPriceFrac: cse.opts.min_price_frac,
      quoteLookers: cse.opts.quote_lookers,
    });
    const tag = `cart[${ci}] (state ${cse.state_idx}, ${cse.opts_name})`;
    if (cse.deal === null) {
      assert.ok(q === null || !q.feasible, `${tag}: Python returned None, JS quoted ${q && JSON.stringify(q.config)}`);
      walks++;
      continue;
    }
    assert.ok(q !== null && q.feasible, `${tag}: Python dealt, JS returned ${q === null ? "null" : "at-list"}`);
    const d = cse.deal;
    assert.equal(q.config.drink, d.drink, `${tag}: drink`);
    assert.deepEqual((q.config.tops || []).slice().sort(), d.tops, `${tag}: tops`);
    assert.equal(Math.trunc(Number(q.config.qty)), d.qty, `${tag}: qty`);
    assert.equal(graph.dim("pickup").option(q.config.pickup).slot_ticks, d.slot_ticks, `${tag}: slot`);
    close(q.price, d.price, TOL, `${tag}: price`);
    close(q.value, d.value, TOL, `${tag}: value`);
    close(q.audit.d_seller, d.d_shop, TOL, `${tag}: d_shop`);
    close(q.audit.d_buyer, d.d_buyer, TOL, `${tag}: d_buyer`);
    close(q.seller_gain + q.audit.d_seller, d.u_shop, TOL, `${tag}: u_shop`);
    close(q.buyer_gain + q.audit.d_buyer, d.u_buyer, TOL, `${tag}: u_buyer`);
    close(q.audit.credit, d.relief, TOL, `${tag}: relief`);
    deals++;
  }
  assert.ok(deals >= 10 && walks >= 10, `outcome mix too thin (deals=${deals}, walks=${walks}) — fixture lost diversity`);
});

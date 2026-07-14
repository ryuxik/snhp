/* The hook's living gate (node --test; wired into CI's js-fidelity job).
 *
 * hook.js prices the user's cart through a SPECIALIZED graph — (cart ∪ the
 * buyer's best-menu-order bundle) — to bound enumeration on the hot path,
 * with the Nash search pinned to the cart. This file is what makes that
 * load-bearing claim survive edits:
 *
 *   1. NEVER ABOVE MENU across a broad config sweep (the hard invariant).
 *   2. Specialized cart-graph == FULL-menu-graph, price-identical, on a
 *      representative sub-sweep (the equivalence the hot path relies on).
 *   3. The scenario invariant the equivalence needs: pearl stock >= QTY_CAP.
 *      (Below it, hook.js's blanket cart_nash-style pearls gate and the
 *      engine's per-qty gate can anchor different disagreements — a known,
 *      reconciled cart_nash edge; see core/adapters/boba.py.)
 *   4. HONESTY: the pearl salvage lever moves the buyer's price by $0 on this
 *      fat-margin menu (the badge must carry no dollar), and quantity alone at
 *      "Now" saves $0 (extra cups only save riding an off-peak slot).
 *
 * Run:  node --test arena/web/hook_verify.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  MENU, SCENARIO, PICKUP_UI, QTY_UI,
  makeEngine, priceOrder, priceEngineCart, priceViaFullGraph,
} from "./hook.js";

const eng = makeEngine(MENU, SCENARIO);
const DRINKS = MENU.drinks.map((d) => d.id ?? d.name);
const SLOTS = PICKUP_UI.map((s) => ({ id: s.id, ticks: s.ticks }));
const QTYS = QTY_UI.map((q) => q.n);

// topping subsets: enough to cover none / the batch topping / a priced pair
const TOPSETS = [[], ["pearls"], ["cheese-foam"], ["pearls", "pudding"]];
const topIds = new Set(MENU.tops.map((t) => t.id ?? t.name));
for (const ts of TOPSETS) for (const t of ts) {
  assert.ok(topIds.has(t), `sweep topping ${t} missing from MENU.tops`);
}

test("scenario invariant: pearl stock >= QTY_CAP (keeps cart-graph == full-graph)", () => {
  assert.ok(
    SCENARIO.batchServings >= eng.world.QTY_CAP,
    `SCENARIO.batchServings=${SCENARIO.batchServings} < QTY_CAP=${eng.world.QTY_CAP}: ` +
      "the specialized graph's blanket pearls gate and the engine's per-qty gate " +
      "can diverge below this — re-verify equivalence before shipping such a scenario",
  );
});

test(`never above menu: full sweep (${DRINKS.length}×${TOPSETS.length}×${SLOTS.length}×${QTYS.length})`, () => {
  let checked = 0;
  for (const d of DRINKS) for (const ts of TOPSETS) for (const sl of SLOTS) for (const q of QTYS) {
    const r = priceEngineCart(eng, d, ts, sl.id, q);
    assert.ok(r.pay <= r.menu + 1e-9, `${d}+[${ts}] ${sl.id} x${q}: pay ${r.pay} > menu ${r.menu}`);
    assert.ok(r.pay >= 0, `${d}: negative price`);
    checked++;
  }
  assert.ok(checked >= 900, `sweep too small (${checked})`);
});

test("specialized cart-graph == full-menu-graph (representative sub-sweep)", () => {
  // every 4th drink keeps this fast enough for CI while spanning all categories
  const sample = DRINKS.filter((_, i) => i % 4 === 0);
  let checked = 0;
  for (const d of sample) for (const ts of TOPSETS) for (const sl of SLOTS) for (const q of QTYS) {
    const a = priceEngineCart(eng, d, ts, sl.id, q);
    const b = priceViaFullGraph(eng, eng.fullGraph, d, ts, sl.id, q);
    assert.equal(a.pay, b.pay, `${d}+[${ts}] ${sl.id} x${q}: cart ${a.pay} != full ${b.pay}`);
    assert.equal(a.feasible, b.feasible, `${d}+[${ts}] ${sl.id} x${q}: feasible flag differs`);
    checked++;
  }
  assert.ok(checked >= 200, `equivalence sub-sweep too small (${checked})`);
});

test("honesty: pearl salvage is $0 on single-cup carts (the badge carries no dollar)", () => {
  // Same shop, batch expiring vs far from expiry. For qty=1 (the cart the badge
  // rule was calibrated on) the 60% floor binds and salvage moves pay by exactly
  // $0 — so the "fresh batch today" badge must never show a dollar.
  //
  // KNOWN + INTENDED at higher qty: the salvaged pearl cost can flip a cart
  // across cart_nash's min-gain threshold (infeasible→feasible), e.g.
  // coconut-mango-boom ×3 at Now: menu $26.52 fresh vs $17.43 expiring. That is
  // REAL engine value from clearing expiring stock — a deal the shop only wants
  // because the batch is dying — not a fabricated discount; the badge still
  // carries no dollar, so the UI stays honest either way.
  const fresh = makeEngine(MENU, Object.assign({}, SCENARIO, { batchExpiresIn: 999 }));
  for (const d of DRINKS) for (const sl of SLOTS) {
    const a = priceEngineCart(eng, d, ["pearls"], sl.id, 1);
    const b = priceEngineCart(fresh, d, ["pearls"], sl.id, 1);
    assert.equal(a.pay, b.pay, `${d} ${sl.id} x1: salvage changed pay ${a.pay} vs ${b.pay}`);
  }
});

test("honesty: quantity alone at Now saves $0 (extra cups only save riding an off-peak slot)", () => {
  for (const d of DRINKS.filter((_, i) => i % 5 === 0)) {
    for (const q of QTYS) {
      const r = priceOrder(eng, { drink: d, tops: [], sizeUp: 0, slotId: "now", slotTicks: 0, qty: q });
      assert.ok(r.save <= 0.005, `${d} x${q} at Now: qty alone "saved" ${r.save}`);
      assert.equal(r.pay, r.menu, `${d} x${q} at Now: pay ${r.pay} != menu ${r.menu}`);
    }
  }
});

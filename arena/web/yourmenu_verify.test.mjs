/* The "run it on your own menu" page's living gate (node --test).
 *
 * yourmenu.js compiles a pasted menu into a core/js OfferGraph, renders the
 * profiler's FREE/LEVER verdicts, and prices carts through the real engine
 * with the cart pinned by a search_filter (cart_nash semantics). This file is
 * what keeps those load-bearing claims true under edits:
 *
 *   1. Both example menus (coffee cart, bakery — deliberately not boba)
 *      validate and compile; the cost model composes the right components.
 *   2. PROFILE: zero-cost dims classify FREE, costed dims classify LEVER, and
 *      the page's verdict cards agree with profile() verbatim (the cards'
 *      $-spread probe is a re-implementation; this pins it to the classifier).
 *   3. NEVER ABOVE LIST across a broad sweep: menus × moments × shopper
 *      levels — the hard discount-only invariant, checked on real quotes.
 *   4. The levers shown are REAL (state moves the quote) and HONEST (what the
 *      page says stays at list, stays at list):
 *        - busy + deferred slot beats list; "now" and quiet hold at list
 *        - end-of-day salvage moves the 3-croissant quote down vs fresh
 *        - same-config anchor: 1 croissant holds at list even at end of day
 *        - scarcity shadow: short-stock cold brew never leaves list
 *   5. Malformed menus produce helpful errors — never a crash, never a
 *      silent fallback.
 *
 * Run:  node --test arena/web/yourmenu_verify.test.mjs
 * (Not wired into CI by this change — see the Phase-4b report.)
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  EXAMPLES, SHOPPER_LEVELS,
  parseMenuText, validateMenu, menuToSpec, makeContext,
  profileMenu, quoteWithCtx, sweepNeverAboveList,
} from "./yourmenu.js";

const val = (raw) => {
  const r = validateMenu(raw);
  assert.ok(r.ok, "example menu must validate: " + r.errors.join(" | "));
  return r.menu;
};
const COFFEE = val(EXAMPLES.coffee.menu);
const BAKERY = val(EXAMPLES.bakery.menu);
const MOMENTS = [
  { busy: false, endOfDay: false }, { busy: true, endOfDay: false },
  { busy: false, endOfDay: true }, { busy: true, endOfDay: true },
];

test("both example menus compile to offer graphs with the right cost stack", () => {
  const cs = menuToSpec(COFFEE);
  assert.deepEqual(cs.dims.map((d) => d.id), ["item", "extras", "cup", "pickup", "qty"]);
  assert.deepEqual(cs.cost, ["const", "scarcity_shadow"]);
  const bs = menuToSpec(BAKERY);
  assert.deepEqual(bs.dims.map((d) => d.id), ["item", "extras", "slicing", "qty"]);
  assert.deepEqual(bs.cost, ["const", "salvage_on_expiry"]);
  for (const m of [COFFEE, BAKERY]) {
    const ctx = makeContext(m, { busy: false, endOfDay: false, level: "interested" });
    assert.ok(ctx.graph.dims.length >= 4, "graph built");
    assert.ok(ctx.graph.enumerateConfigs().length > 0, "graph enumerates");
  }
});

test("profiler: zero-cost dims are FREE, costed dims are LEVER (and cards match profile())", () => {
  const scn = { busy: false, endOfDay: false, level: "interested" };
  const cp = profileMenu(COFFEE, scn);
  assert.equal(cp.raw.cup, "free", "cup preference has zero cost gradient");
  assert.equal(cp.raw.item, "lever", "item choice moves cost");
  assert.equal(cp.raw.extras, "lever", "extras carry marginal cost");
  assert.equal(cp.raw.qty, "lever", "quantity moves total cost (linear)");
  // documented core/js note: the profiler probes c_eff only, so fulfillment
  // (whose economics are hazard/capacity, not unit cost) reads FREE — the
  // page shows this verbatim and explains the timing channel beside it.
  assert.equal(cp.raw.pickup, "free");
  const bp = profileMenu(BAKERY, scn);
  assert.equal(bp.raw.slicing, "free");
  assert.equal(bp.raw.item, "lever");
  for (const p of [cp, bp]) {
    for (const c of p.cards) assert.equal(c.verdict, p.raw[c.id], `card ${c.id} == profile()`);
  }
});

test("never above list: sweep both menus × moments × shopper levels", () => {
  let checked = 0;
  for (const menu of [COFFEE, BAKERY]) {
    for (const m of MOMENTS) {
      for (const lvl of SHOPPER_LEVELS) {
        const s = sweepNeverAboveList(menu, { ...m, level: lvl.id });
        assert.equal(s.violations.length, 0,
          `${menu.name} ${JSON.stringify(m)} ${lvl.id}: ${JSON.stringify(s.violations[0])}`);
        checked += s.checked;
      }
    }
  }
  assert.ok(checked >= 1500, `sweep too small (${checked})`);
});

test("timing lever is real and honest: busy+deferred beats list; now/quiet hold at list", () => {
  const cart = { item: "oat-latte", addons: ["extra-shot", "vanilla"], prefs: { cup: "to-go" }, slot: "in-20", qty: 1 };
  const busy = makeContext(COFFEE, { busy: true, endOfDay: false, level: "interested" });
  const deal = quoteWithCtx(busy, cart);
  assert.equal(deal.outcome, "negotiated");
  assert.ok(deal.save > 0.05, `busy+deferred saves something real (got ${deal.save})`);
  assert.ok(deal.price <= deal.list + 1e-9);

  const now = quoteWithCtx(busy, { ...cart, slot: "now" });
  assert.equal(now.price, now.list, "picking up now, busy: at list (no flexibility given)");

  const quiet = makeContext(COFFEE, { busy: false, endOfDay: false, level: "interested" });
  const qd = quoteWithCtx(quiet, cart);
  assert.equal(qd.price, qd.list, "quiet: serving now costs the shop nothing extra — at list");
});

test("salvage lever is real and honest: end-of-day moves the 3-croissant box, not the single", () => {
  const cart = { item: "croissant", addons: [], prefs: { slicing: "whole" }, slot: null, qty: 3 };
  const fresh = quoteWithCtx(makeContext(BAKERY, { busy: false, endOfDay: false, level: "interested" }), cart);
  const eod = quoteWithCtx(makeContext(BAKERY, { busy: false, endOfDay: true, level: "interested" }), cart);
  assert.equal(fresh.outcome, "negotiated");
  assert.equal(eod.outcome, "negotiated");
  assert.ok(eod.price < fresh.price - 0.05,
    `end-of-day salvage must lower the box quote (fresh ${fresh.price} vs eod ${eod.price})`);
  assert.ok(fresh.price <= fresh.list && eod.price <= eod.list);

  // same-config anchor: a shopper who'd buy ONE at list anyway gets nothing
  // from salvage alone — the page says so; keep it true.
  for (const endOfDay of [false, true]) {
    const one = quoteWithCtx(makeContext(BAKERY, { busy: false, endOfDay, level: "interested" }), { ...cart, qty: 1 });
    assert.equal(one.price, one.list, `qty 1, endOfDay=${endOfDay}: at list`);
  }
});

test("scarcity shadow: short-stock cold brew never leaves list", () => {
  for (const m of MOMENTS) {
    const ctx = makeContext(COFFEE, { ...m, level: "interested" });
    for (const slot of ["now", "in-20"]) {
      for (let q = 1; q <= 3; q++) {
        const r = quoteWithCtx(ctx, { item: "cold-brew", addons: [], prefs: { cup: "for-here" }, slot, qty: q });
        assert.equal(r.price, r.list, `cold-brew ${slot} x${q} ${JSON.stringify(m)}: must hold at list`);
        assert.ok(r.floorsAtList, "the engine's cost floor rides at list for displaced units");
      }
    }
  }
});

test("malformed menus: helpful errors, never a crash, never a silent fallback", () => {
  const bad = (text, re) => {
    const r = typeof text === "string" ? parseMenuText(text) : validateMenu(text);
    assert.equal(r.ok, false);
    assert.ok(r.errors.length >= 1, "has an error message");
    assert.match(r.errors.join(" "), re, `error mentions the problem: ${r.errors.join(" | ")}`);
  };
  bad("", /Paste a menu/);
  bad("{ nope", /valid JSON/);
  bad("[1,2,3]", /top level must be a JSON object/);
  bad({}, /"items" is required/);
  bad({ items: [{ id: "a", price: -2, cost: 1 }] }, /"price" must be a number > 0/);
  bad({ items: [{ id: "a", price: 2, cost: 1 }, { id: "a", price: 3, cost: 1 }] }, /Duplicate id "a"/);
  bad({ items: [{ id: "a", price: 2, cost: 1, expected_demand: 5 }] }, /needs "stock"/);
  bad({ items: [{ id: "a", price: 2, cost: 1, salvage: 0.5 }] }, /"perishable": true/);
  bad({ items: [{ id: "a", price: 2, cost: 1 }], typo_key: true }, /Unknown top-level key "typo_key"/);
  bad({ items: [{ id: "a", price: 2, cost: 1 }],
        addons: Array.from({ length: 13 }, (_, i) => ({ id: "x" + i, price: 1, cost: 0.1 })) },
      /at most 12/);
  bad({ items: [{ id: "a", price: 2, cost: 1 }],
        slots: [{ id: "s1", minutes: 20 }, { id: "s2", minutes: 22 }] },
      /same 10-minute tick/);
  // visible, not silent: a slots list without an immediate slot gets "now"
  // added AND a note saying so.
  const r = validateMenu({ items: [{ id: "a", price: 2, cost: 1 }], slots: [{ id: "later", minutes: 30 }] });
  assert.ok(r.ok);
  assert.equal(r.menu.slots[0].ticks, 0, 'an immediate "now" slot was added');
  assert.match(r.notes.join(" "), /Added a "now" slot/);
});

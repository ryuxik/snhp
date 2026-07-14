/* hook.js — the flagship BOBA consumer HOOK (Phase 4a of the SNHP redesign).
 *
 * A full, HeyTea-scale boba menu ordering experience, priced LIVE by the
 * VALIDATED GENERAL ENGINE in core/js/.
 * You walk up to a shop's self-order tablet, browse a real multi-category menu,
 * build a normal order, and money-saving levers surface right in the flow — a
 * later off-peak pickup ★, an extra cup for the group — and the price ticks DOWN,
 * never above the menu. Every price is a live core-engine number.
 *
 * WHAT IS THE ENGINE vs WHAT IS THIS FILE
 *   - PRICING (Nash-floor split, rungs, guards, never-above-menu) is done ENTIRELY
 *     by core/js/engine.mjs `quote()`, over an OfferGraph (core/js/offer_graph.mjs)
 *     with the composable state-dependent cost model (core/js/cost.mjs). We hand it
 *     the boba graph / ShopState / SeparableBuyer via core/js/boba_adapter.mjs.
 *   - THE BOBA WORLD (the demand model: appeal inversion -> WTP, FIFO balk hazard,
 *     service capacity, tapioca batches, capacity_relief) comes from
 *     arena/web/boba-world.mjs — the ONE JS-side re-implementation of
 *     boba/world.py's math (cross-checked against Python by
 *     bobaworld_verify.test.mjs). Its makeWorld() supplies the `world` object
 *     the adapter is parameterized by.
 *
 * HONESTY (hard, non-negotiable — do not regress):
 *   - Never above the menu (a core-engine invariant; also swept in hook_verify.test.mjs).
 *   - Sweetness & ice are FREE — pure UI, never entered into the engine, never priced.
 *   - The fresh-pearl "batch today" badge carries NO dollar: on a fat-margin menu the
 *     min-price (60%) floor binds, so the salvage lever's price effect is ~$0. We
 *     surface the fresh batch as a freshness note only, never a fabricated discount.
 *   - Quantity is NOT a standalone cost lever (cost is linear in qty in the engine):
 *     extra cups sit at menu price on their own, and save ONLY when paired with an
 *     off-peak pickup (each extra cup then frees more of the rush). Framed that way.
 *   - CONSUMER-ONLY: zero provider economics on the page (no margins, $/day,
 *     attestation, forecasts). The only bridge is a quiet "Run a shop? ->" link.
 *
 * Runs in the browser (boots the tablet UI) and in node (exports the pure pricing
 * surface for arena/web/hook_verify.test.mjs). No DOM work happens under node.
 */
import { DimKind, Dimension, OfferGraph, Option } from "../../core/js/offer_graph.mjs";
import { compose, constComp, salvageOnExpiry, capacityRelief } from "../../core/js/cost.mjs";
import { QuoteOpts, quote as coreQuote } from "../../core/js/engine.mjs";
import { shopState, buyerFor, buildBobaGraph, PICKUP_SLOTS } from "../../core/js/boba_adapter.mjs";
import { makeWorld, makeBobaState } from "./boba-world.mjs";
export { makeWorld, makeBobaState }; // re-exported: hook.js's surface is stable

// ════════════════════════════════════════════════════════════════════════════
//  THE MENU — a real, full HeyTea-scale catalog (NYC prices). Matcha is a DRINK,
//  never a topping. Costs are the shop's ingredient cost per cup (~20-24% of
//  price — fat boba margins, so the 60% min-price floor binds and pearl salvage
//  is ~$0, exactly as the honesty rule requires). Appeals are inverted from
//  (price, cost) by the world below, so WTPs are calibrated, not invented.
// ════════════════════════════════════════════════════════════════════════════
export const MENU = {
  categories: [
    { id: "signature", label: "Staff Picks", emo: "⭐" },
    { id: "fruit",     label: "Fruit Tea",   emo: "🍓" },
    { id: "cloud",     label: "Cheese Cloud", emo: "☁️" },
    { id: "bobo",      label: "Boba Milk Tea", emo: "🧋" },
    { id: "matcha",    label: "Matcha",      emo: "🍵" },
    { id: "classic",   label: "Tea Latte & Classics", emo: "🍃" },
  ],
  drinks: [
    // Staff Picks
    { name: "coconut-mango-boom",     cat: "signature", price: 7.99, cost: 1.85, popularity: 0.10, label: "Coconut Mango Boom",           emo: "🥭", meta: "mango + coconut + sea salt cloud" },
    { name: "brown-sugar-bobo",       cat: "signature", price: 7.49, cost: 1.65, popularity: 0.11, label: "Supreme Brown Sugar Boba Milk", emo: "🤎", meta: "warm brown sugar, chewy boba" },
    { name: "crisp-grape-boom",       cat: "signature", price: 7.79, cost: 1.80, popularity: 0.08, label: "Crisp Grape Boom",             emo: "🍇", meta: "muscat grape, real pulp" },
    { name: "kale-boost",             cat: "signature", price: 6.99, cost: 1.45, popularity: 0.05, label: "Kale Boost Tea",               emo: "🥬", meta: "kale, apple, lemon" },
    // Fruit Tea
    { name: "mango-grapefruit-boom",  cat: "fruit", price: 7.79, cost: 1.78, popularity: 0.06, label: "Mango Grapefruit Boom",     emo: "🍊", meta: "mango + grapefruit, bright" },
    { name: "mulberry-strawberry",    cat: "fruit", price: 7.69, cost: 1.75, popularity: 0.06, label: "Mulberry Strawberry Boom",  emo: "🍓", meta: "mulberry + strawberry" },
    { name: "passionfruit-blast",     cat: "fruit", price: 7.19, cost: 1.55, popularity: 0.05, label: "Passion Fruit Blast",       emo: "🍹", meta: "passion fruit, green tea" },
    { name: "grapefruit-boom",        cat: "fruit", price: 7.49, cost: 1.62, popularity: 0.05, label: "Grapefruit Boom",          emo: "🍊", meta: "fresh grapefruit, jasmine" },
    { name: "dragonfruit-lychee",     cat: "fruit", price: 7.99, cost: 1.88, popularity: 0.05, label: "Dragonfruit Lychee Slush", emo: "🍧", meta: "dragonfruit + lychee, iced slush" },
    // Cheese Cloud (the signature cheese-foam-topped teas)
    { name: "cloud-crisp-grape",      cat: "cloud", price: 7.49, cost: 1.68, popularity: 0.05, label: "Fluffy Cloud Crisp Grape", emo: "🍇", meta: "grape tea, salted cheese cloud" },
    { name: "cloud-mango",            cat: "cloud", price: 7.29, cost: 1.60, popularity: 0.05, label: "Fluffy Cloud Mango",       emo: "🥭", meta: "mango tea, cheese cloud" },
    { name: "lychee-cloud",           cat: "cloud", price: 7.59, cost: 1.70, popularity: 0.04, label: "Lychee Cloud",            emo: "☁️", meta: "lychee green tea, cheese cloud" },
    { name: "peach-cloud",            cat: "cloud", price: 7.49, cost: 1.66, popularity: 0.04, label: "Peach Cloud",             emo: "🍑", meta: "peach oolong, cheese cloud" },
    { name: "passionfruit-cloud",     cat: "cloud", price: 7.29, cost: 1.60, popularity: 0.04, label: "Passion Fruit Cloud",     emo: "🌼", meta: "passion fruit, cheese cloud" },
    // Boba Milk Tea
    { name: "taro-bobo",              cat: "bobo", price: 7.99, cost: 1.82, popularity: 0.06, label: "Taro Boba Milk",       emo: "🕯", meta: "fresh taro, boba" },
    { name: "coconut-bobo",           cat: "bobo", price: 7.79, cost: 1.76, popularity: 0.05, label: "Coconut Boba Milk",    emo: "🥥", meta: "coconut milk, boba" },
    { name: "oat-black-bobo",         cat: "bobo", price: 7.69, cost: 1.72, popularity: 0.04, label: "Oat Black Tea Boba",   emo: "🌾", meta: "oat milk, black tea, boba" },
    { name: "coffee-bobo",            cat: "bobo", price: 7.99, cost: 1.85, popularity: 0.04, label: "Coffee Boba Milk",     emo: "☕", meta: "espresso, milk, boba" },
    { name: "triple-bobo",            cat: "bobo", price: 8.29, cost: 1.95, popularity: 0.04, label: "Triple Boba Milk Tea", emo: "🧋", meta: "boba, pudding, grass jelly" },
    // Matcha (a DRINK, never a topping)
    { name: "cloud-matcha",           cat: "matcha", price: 7.49, cost: 1.72, popularity: 0.05, label: "Cloud Matcha Latte",         emo: "🍵", meta: "ceremonial matcha, milk cloud" },
    { name: "supreme-matcha",         cat: "matcha", price: 7.79, cost: 1.82, popularity: 0.05, label: "Supreme Matcha Latte",       emo: "🍵", meta: "double matcha, oat milk" },
    { name: "triple-matcha",          cat: "matcha", price: 8.29, cost: 1.98, popularity: 0.04, label: "Triple Supreme Matcha Latte", emo: "🍵", meta: "triple matcha, rich" },
    { name: "oat-matcha-bobo",        cat: "matcha", price: 7.99, cost: 1.88, popularity: 0.04, label: "Oat Matcha Boba",            emo: "🍵", meta: "matcha, oat milk, boba" },
    // Tea Latte & Classics
    { name: "jasmine-latte",          cat: "classic", price: 6.79, cost: 1.25, popularity: 0.05, label: "Jasmine Tea Latte",     emo: "🌼", meta: "jasmine green, milk" },
    { name: "longjing-latte",         cat: "classic", price: 6.79, cost: 1.25, popularity: 0.04, label: "Longjing Tea Latte",    emo: "🍃", meta: "dragonwell green, milk" },
    { name: "peach-oolong",           cat: "classic", price: 7.19, cost: 1.45, popularity: 0.04, label: "Peach Oolong Tea Latte", emo: "🍑", meta: "peach oolong, milk" },
    { name: "pure-jasmine",           cat: "classic", price: 5.49, cost: 0.95, popularity: 0.03, label: "Pure Jasmine Tea",      emo: "🌸", meta: "no milk, just tea" },
    { name: "pure-black",             cat: "classic", price: 5.49, cost: 0.95, popularity: 0.03, label: "Pure Black Tea",        emo: "🫖", meta: "no milk, just tea" },
  ],
  // The real HeyTea extras set. `pearls` is the perishable/batch topping (id must
  // be exactly "pearls" for the adapter's salvage/stock-limited semantics).
  tops: [
    { name: "pearls",       price: 0.85, cost: 0.10, like_prob: 0.65, label: "Tapioca Pearls", emo: "⚫", meta: "chewy boba" },
    { name: "cheese-foam",  price: 1.25, cost: 0.28, like_prob: 0.42, label: "Cheese Cloud",   emo: "🧀", meta: "salted milk foam" },
    { name: "pudding",      price: 0.79, cost: 0.15, like_prob: 0.35, label: "Pudding",        emo: "🍮", meta: "egg custard" },
    { name: "grass-jelly",  price: 0.85, cost: 0.12, like_prob: 0.30, label: "Grass Jelly",    emo: "🟩", meta: "herbal jelly" },
    { name: "coconut-jelly", price: 0.99, cost: 0.18, like_prob: 0.33, label: "Coconut Jelly", emo: "🥥", meta: "coconut milk jelly" },
    { name: "red-bean",     price: 0.79, cost: 0.16, like_prob: 0.28, label: "Red Bean",       emo: "🔴", meta: "sweet azuki" },
    { name: "aloe",         price: 0.79, cost: 0.14, like_prob: 0.26, label: "Aloe Vera",      emo: "🌿", meta: "crisp aloe cubes" },
  ],
  batchTop: "pearls",
  sizes: [
    { id: "M", label: "Medium", meta: "16 oz", up: 0.0 },
    { id: "L", label: "Large",  meta: "24 oz", up: 0.75 },
  ],
  sweets: ["0%", "25%", "50%", "75%", "100%"],
  ices: ["Regular", "Less", "None"],
};

// ════════════════════════════════════════════════════════════════════════════
//  THE SHOP MOMENT + SHOPPER — the same transparent scenario as the validated
//  interim demo: a peak lunch lull (queue building -> real balk hazard) with an
//  over-cooked tapioca batch near its sell-by. So a later off-peak pickup frees
//  the rush (real capacity_relief) AND the fresh pearls are near-waste. Every
//  number below feeds the REAL engine; the prices are whatever it returns.
// ════════════════════════════════════════════════════════════════════════════
export const SCENARIO = {
  tick: 21,               // 1:00pm, mid-lunch (a PEAK hour)
  queue: 3,               // a real line (~1 in 3 balk) -> real defer incentive, varied discounts
  batchServings: 40,
  batchExpiresIn: 3,      // pearls near sell-by (<= clearance window) -> salvage live
  eps: 1.15, topDraw: 1.05, decay: 0.60, flexible: true,
};

export const PICKUP_UI = [
  { id: "now", ticks: 0, label: "Now",       meta: "straight away" },
  { id: "d30", ticks: 3, label: "In 30 min", meta: "after the lunch rush" },
  { id: "d60", ticks: 6, label: "In 60 min", meta: "a quiet slot" },
];
export const QTY_UI = [
  { n: 1, label: "Just me",              meta: "one cup",      emo: "🧋" },
  { n: 2, label: "Add a 2nd",            meta: "a friend's cup", emo: "👯" },
  { n: 3, label: "Grab 3 for the group", meta: "an office run",  emo: "👥" },
];

const round2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;
const uniq = (arr) => Array.from(new Set(arr));

// (The boba world itself — makeWorld/makeBobaState — lives in boba-world.mjs,
// the single JS-side copy of boba/world.py's math; re-exported above.)

// The representative shopper: a generous, flexible walk-in. WTP is a real function
// of the world's calibrated appeals at this hour (not invented). defer_cost is the
// engine's own FLEX/RIGID schedule.
export function makeConsumer(world, boba, scn) {
  const mult = world.HOURLY_WTP_MULT[world.hourOf(boba.tick)];
  const wtp = {}, top_wtp = {};
  world.drinks.forEach((d) => { wtp[d] = world.DRINK_APPEAL[d] * mult * scn.eps; });
  world.tops.forEach((t) => { top_wtp[t] = world.TOP_APPEAL[t] * scn.topDraw; });
  return {
    wtp, top_wtp, qty_decay: scn.decay, flexible: scn.flexible,
    defer_cost(st) { return this.flexible ? world.FLEX_DEFER[st] : world.RIGID_DEFER[st]; },
  };
}

// ════════════════════════════════════════════════════════════════════════════
//  PRICING — via core/js/engine.mjs `quote()`.
//
//  For a fixed cart we want cart_nash's disagreement point (the buyer's BEST menu
//  order, valued live) while pricing the EXACT cart the user built. We give the
//  engine a graph whose candidate set contains BOTH the user's cart and the
//  buyer's best-menu-order bundle, let the disagreement search roam it (so it
//  anchors on the best menu order, exactly like priceCart), and pin the Nash
//  search to the user's cart+slot+qty with a search_filter. Specializing the
//  graph to (cart ∪ best-order) bounds enumeration; it produces prices identical
//  to the full-menu graph (asserted in hook_verify.test.mjs).
// ════════════════════════════════════════════════════════════════════════════
const QUOTE_OPTS = {
  min_price_frac: 0.6, qty_appetite: false, quote_lookers: true,
  min_gain_abs: 0.25, min_gain_frac: 0.10, price_rungs: 8, seller_weight: 0.5, prune_free: true,
};

// capacity_relief as a core cost component (mirror of the adapter's private
// `relief` closure): reads the config's fulfillment slot and defers to the world.
function reliefComponent(world) {
  return capacityRelief((graph, state, config, qty) => {
    const boba = state.extra && state.extra.boba;
    if (!boba) return 0.0;
    let slotTicks = 0;
    for (const d of graph.dims) {
      if (d.kind === DimKind.FULFILLMENT) { slotTicks = d.option(config[d.id]).slot_ticks; break; }
    }
    if (slotTicks <= 0) return 0.0;
    return world.capacity_relief(boba, qty, slotTicks);
  });
}

// A boba OfferGraph restricted to the given drink/topping ids (same dims, costs,
// and cost model as buildBobaGraph — just fewer options, to bound enumeration).
export function buildCartGraph(world, drinkIds, topIds) {
  const drink = new Dimension("drink", DimKind.CHOICE,
    drinkIds.map((d) => new Option({ id: d, label: d, price_delta: world.DRINK_PRICE[d], unit_cost: world.DRINK_COST[d] })));
  const tops = new Dimension("tops", DimKind.ADDON,
    topIds.map((t) => new Option({
      id: t, label: t, price_delta: world.TOP_PRICE[t], unit_cost: world.TOP_COST[t],
      perishable: t === world.batchTop, salvage: 0.0, stock_limited: t === world.batchTop,
    })));
  const pickup = new Dimension("pickup", DimKind.FULFILLMENT,
    PICKUP_SLOTS.map(([name, imm, st]) => new Option({ id: name, immediate: imm, slot_ticks: st })));
  const qty = new Dimension("qty", DimKind.QUANTITY, [], world.QTY_CAP);
  return new OfferGraph({
    dims: [drink, tops, pickup, qty], deps: null,
    cost: compose(constComp(), salvageOnExpiry(), reliefComponent(world)), name: "boba-cart",
  });
}

// A search_filter that pins the Nash search to the user's exact cart+slot+qty
// while leaving the disagreement search free to find the best menu order.
function cartPin(drinkId, topIds, slotId, qty) {
  const wantTops = topIds.slice().sort().join(",");
  return (graph, state, buyer, cfg) => {
    if (cfg.drink !== drinkId) return false;
    if ((cfg.tops || []).slice().sort().join(",") !== wantTops) return false;
    let pk = null, q = 1;
    for (const d of graph.dims) {
      if (d.kind === DimKind.FULFILLMENT) pk = cfg[d.id];
      else if (d.kind === DimKind.QUANTITY) q = cfg[d.id];
    }
    return pk === slotId && q === qty;
  };
}

function configIsCart(cfg, drinkId, topIds, slotId, qty) {
  if (!cfg || cfg.drink !== drinkId) return false;
  if ((cfg.tops || []).slice().sort().join(",") !== topIds.slice().sort().join(",")) return false;
  return cfg.pickup === slotId && Number(cfg.qty) === qty;
}

// Price the exact cart (drink, tops, slotId, qty) through the core engine.
// Returns { pay, menu, save, feasible } for the drink+toppings (no size upcharge).
export function priceEngineCart(eng, drinkId, topIds, slotId, qty) {
  const { world, boba, consumer, best } = eng;
  const drinkIds = uniq([drinkId, best.drink].filter(Boolean));
  const topSet = uniq([...(topIds || []), ...(best.tops || [])]);
  const graph = buildCartGraph(world, drinkIds, topSet);
  const state = shopState(world, boba, { deferSlots: true, salvage: true });
  const buyer = buyerFor(world, boba, consumer);
  const opts = new QuoteOpts(Object.assign({}, QUOTE_OPTS, { search_filter: cartPin(drinkId, topIds, slotId, qty) }));
  const q = coreQuote(graph, state, buyer, { config: null, opts });
  const menu = round2(qty * (world.DRINK_PRICE[drinkId] + (topIds || []).reduce((s, t) => s + world.TOP_PRICE[t], 0)));
  if (q && configIsCart(q.config, drinkId, topIds || [], slotId, qty) && q.feasible) {
    const pay = round2(Math.min(q.price, menu));
    return { pay, menu, save: round2(menu - pay), feasible: true };
  }
  // no split beat the disagreement (or slot had no room): pay the menu.
  return { pay: menu, menu, save: 0.0, feasible: false };
}

// Price via the FULL-menu graph (buildBobaGraph) — same disagreement, same Nash,
// just the whole menu enumerated. Used by hook_verify.test.mjs to prove the cart
// graph is byte-identical. Slower; not on the live path.
export function priceViaFullGraph(eng, fullGraph, drinkId, topIds, slotId, qty) {
  const { world, boba, consumer } = eng;
  const state = shopState(world, boba, { deferSlots: true, salvage: true });
  const buyer = buyerFor(world, boba, consumer);
  const opts = new QuoteOpts(Object.assign({}, QUOTE_OPTS, { search_filter: cartPin(drinkId, topIds, slotId, qty) }));
  const q = coreQuote(fullGraph, state, buyer, { config: null, opts });
  const menu = round2(qty * (world.DRINK_PRICE[drinkId] + (topIds || []).reduce((s, t) => s + world.TOP_PRICE[t], 0)));
  if (q && configIsCart(q.config, drinkId, topIds || [], slotId, qty) && q.feasible) {
    const pay = round2(Math.min(q.price, menu));
    return { pay, menu, save: round2(menu - pay), feasible: true };
  }
  return { pay: menu, menu, save: 0.0, feasible: false };
}

// Build the whole engine context once (world + state + shopper + best order +
// the full-menu graph, per the task's "build the full-menu boba graph via the
// adapter"). `salvageActive` is the engine's real pearl-excess flag.
export function makeEngine(menu, scn) {
  const world = makeWorld(menu);
  const boba = makeBobaState(scn);
  const consumer = makeConsumer(world, boba, scn);
  const best = world.bestMenuOrder(consumer, world.DRINK_PRICE, world.TOP_PRICE, boba.pearl_stock() >= world.QTY_CAP);
  const fullGraph = buildBobaGraph(world); // full-menu graph, built via the adapter
  const salvageActive = world.pearls_expiring_excess(boba);
  return { world, boba, consumer, best, fullGraph, salvageActive, menu, scn };
}

// The public "price this order" the UI calls — adds the flat size upcharge on
// BOTH sides (menu and paid) so it never enters the negotiation.
export function priceOrder(eng, order) {
  const e = priceEngineCart(eng, order.drink, order.tops || [], order.slotId, order.qty);
  const up = (order.sizeUp || 0) * order.qty;
  return {
    pay: round2(e.pay + up), menu: round2(e.menu + up),
    save: e.save, feasible: e.feasible,
  };
}
export function perCupMenu(eng, order) {
  let s = eng.world.DRINK_PRICE[order.drink] + (order.sizeUp || 0);
  (order.tops || []).forEach((t) => { s += eng.world.TOP_PRICE[t]; });
  return round2(s);
}

// ════════════════════════════════════════════════════════════════════════════
//  BROWSER: the tablet UI. (Nothing below runs under node.)
// ════════════════════════════════════════════════════════════════════════════
if (typeof document !== "undefined") boot();

function boot() {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const money = (x) => "$" + Number(x).toFixed(2);
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

  let eng;
  try { eng = makeEngine(MENU, SCENARIO); }
  catch (e) { $("err").textContent = "Could not start the boba engine — " + (e && e.message || e); console.error(e); return; }

  const DRINK = {}, TOP = {};
  MENU.drinks.forEach((d) => { DRINK[d.name] = d; });
  MENU.tops.forEach((t) => { TOP[t.name] = t; });

  let cur = null; // live order state

  // ── pixel boba shop backdrop (integer-upscaled low-res backbuffer) ──────────
  const view = $("view"), c = view.getContext("2d");
  c.imageSmoothingEnabled = false;
  const mix = (h1, h2, t) => {
    const a = parseInt(h1.slice(1), 16), b = parseInt(h2.slice(1), 16);
    const ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255;
    const br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255;
    const r = Math.round(ar + (br - ar) * t), g = Math.round(ag + (bg - ag) * t), bl = Math.round(ab + (bb - ab) * t);
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1);
  };
  function glow(gx, gy, r, col, a) {
    if (a <= 0) return;
    const n = parseInt(col.slice(1), 16), R = (n >> 16) & 255, G = (n >> 8) & 255, Bl = n & 255;
    c.globalCompositeOperation = "lighter";
    const g = c.createRadialGradient(gx, gy, 0, gx, gy, r);
    g.addColorStop(0, "rgba(" + R + "," + G + "," + Bl + "," + a + ")");
    g.addColorStop(1, "rgba(" + R + "," + G + "," + Bl + ",0)");
    c.fillStyle = g; c.fillRect(gx - r, gy - r, r * 2, r * 2);
    c.globalCompositeOperation = "source-over";
  }
  const GLYPH = {
    A: ["010", "101", "111", "101", "101"], B: ["110", "101", "110", "101", "110"],
    O: ["111", "101", "101", "101", "111"], " ": ["000", "000", "000", "000", "000"],
  };
  function drawText(str, x, y, s, col) {
    str = String(str).toUpperCase();
    for (let i = 0; i < str.length; i++) {
      const g = GLYPH[str[i]] || GLYPH[" "];
      for (let r = 0; r < 5; r++) for (let k = 0; k < 3; k++)
        if (g[r][k] === "1") { c.fillStyle = col; c.fillRect(x + i * 4 * s + k * s, y + r * s, s, s); }
    }
  }
  let LOW_H = 240, LOW_W = 420, scale = 2;
  function resize() {
    const aw = window.innerWidth, ah = window.innerHeight;
    LOW_W = Math.max(300, Math.min(680, Math.round(LOW_H * (aw / ah))));
    view.width = LOW_W; view.height = LOW_H; c.imageSmoothingEnabled = false;
    scale = Math.max(aw / LOW_W, ah / LOW_H);
    view.style.width = Math.round(LOW_W * scale) + "px"; view.style.height = Math.round(LOW_H * scale) + "px";
  }
  const GROUND = 202;
  function drawMiniCup(px, x, y, col) {
    px(x, y, 7, 3, "#cbb58a"); px(x, y + 3, 7, 11, col); px(x + 1, y + 10, 5, 3, "#3a2a1f"); px(x + 3, y - 2, 1, 3, "#e6d3b3");
  }
  function drawShop(zoom, t) {
    const px = (X, Y, W, H, col) => { c.fillStyle = col; c.fillRect(X | 0, Y | 0, W | 0, H | 0); };
    const cx = LOW_W / 2, counterTop = 152;
    c.save(); c.translate(cx, GROUND); c.scale(zoom, zoom); c.translate(-cx, -GROUND);
    const wg = c.createLinearGradient(0, 0, 0, GROUND);
    wg.addColorStop(0, "#241a2a"); wg.addColorStop(1, "#33241f");
    c.fillStyle = wg; c.fillRect(-LOW_W, 0, LOW_W * 3, GROUND);
    px(-LOW_W, GROUND, LOW_W * 3, LOW_H, "#20161a");
    for (let fx = -LOW_W; fx < LOW_W * 2; fx += 20) px(fx, GROUND, 1, LOW_H - GROUND, "#180f14");
    px(-8, 12, LOW_W + 16, 18, mix("#cb9a6a", "#000000", 0.35));
    px(-8, 12, LOW_W + 16, 2, mix("#cb9a6a", "#ffffff", 0.3));
    const word = "BOBA", s = 3, tw = word.length * 4 * s - s;
    drawText(word, Math.round(cx - tw / 2), 15, s, "#f6ecd6");
    glow(cx, 21, tw, "#7fc48f", 0.1);
    px(cx - 1, 30, 2, 12, "#161018"); px(cx - 8, 42, 16, 5, "#e8c060");
    glow(cx, 48, 74, "#ffcf8a", 0.15);
    const cupCols = ["#e6d3b3", "#d8a86a", "#f0c8a0", "#cfe6d0", "#e6b8c8", "#d8c8e6"];
    for (let r = 0; r < 2; r++) {
      const sh = 58 + r * 30;
      px(20, sh + 18, LOW_W - 40, 3, "#4a3626"); px(20, sh + 21, LOW_W - 40, 2, mix("#4a3626", "#000000", 0.4));
      for (let i = 0; 26 + i * 15 < LOW_W - 26; i++) drawMiniCup(px, 26 + i * 15, sh, cupCols[(r * 3 + i) % cupCols.length]);
    }
    px(LOW_W - 76, 56, 56, counterTop - 62, "#20303a"); px(LOW_W - 72, 60, 48, counterTop - 70, "#2f5a6a");
    glow(LOW_W - 48, counterTop / 2 + 22, 30, "#7fe0ff", 0.1);
    px(0, counterTop, LOW_W, GROUND - counterTop, "#5a3f2a"); px(0, counterTop, LOW_W, 5, "#7a5636");
    px(0, counterTop + 5, LOW_W, 2, mix("#5a3f2a", "#000000", 0.4));
    const mx = cx - 26, my = counterTop - 52, mw = 52, mh = 40;
    px(cx - 3, counterTop - 12, 6, 12, "#2a2230"); px(mx - 3, my - 3, mw + 6, mh + 6, "#211a2c"); px(mx, my, mw, mh, "#0c0a16");
    px(mx + 4, my + 5, mw - 8, 3, "#7fc48f");
    for (let ky = 0; ky < 3; ky++) px(mx + 4, my + 12 + ky * 7, mw - 8, 4, ky === 1 ? "#ffe08a" : "#3a3450");
    drawMiniCup(px, cx - 5, my + 10, "#e6d3b3");
    glow(cx, my + mh / 2, 40, "#a78bfa", 0.1 + 0.05 * Math.sin(t / 900));
    c.restore();
  }
  let cam = 0, camTo = 0, tStart = performance.now(), lastW = 0, lastH = 0;
  function frame(now) {
    const t = now - tStart;
    cam += (camTo - cam) * (reduced ? 1 : 0.06);
    if (window.innerWidth !== lastW || window.innerHeight !== lastH) { lastW = window.innerWidth; lastH = window.innerHeight; resize(); }
    c.clearRect(0, 0, LOW_W, LOW_H);
    drawShop(1 + cam * 0.22, reduced ? 0 : t);
    requestAnimationFrame(frame);
  }

  // ── build the tablet controls ───────────────────────────────────────────────
  function optRadio(group, id, checked, labelHTML) {
    const wrap = document.createElement("div"); wrap.className = "opt";
    wrap.innerHTML = '<input type="radio" name="' + group + '" id="' + id + '"' + (checked ? " checked" : "") + ">" +
      '<label for="' + id + '">' + labelHTML + "</label>";
    return wrap;
  }
  function optCheck(id, labelHTML) {
    const wrap = document.createElement("div"); wrap.className = "opt";
    wrap.innerHTML = '<input type="checkbox" id="' + id + '">' + '<label for="' + id + '">' + labelHTML + "</label>";
    return wrap;
  }

  function buildUI() {
    // CATEGORY TABS (scroll-to)
    const tabs = $("cat-tabs"); tabs.innerHTML = "";
    MENU.categories.forEach((cat, i) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "cat-tab" + (i === 0 ? " is-active" : "");
      b.dataset.cat = cat.id;
      b.innerHTML = '<span aria-hidden="true">' + cat.emo + "</span> " + esc(cat.label);
      b.setAttribute("aria-label", "Jump to " + cat.label);
      b.addEventListener("click", () => {
        const sec = $("cat-" + cat.id);
        if (sec) sec.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      });
      tabs.appendChild(b);
    });

    // DRINK sections by category. All drink radios share name="drink" -> one
    // native radio group; the per-category boxes are visual grouping only (h3
    // sub-headings), so we do NOT add role=radiogroup per box.
    const host = $("drink-cats"); host.innerHTML = "";
    const defaultDrink = "brown-sugar-bobo"; // a clear menu-buyer default
    MENU.categories.forEach((cat) => {
      const box = document.createElement("div");
      box.className = "drink-cat"; box.id = "cat-" + cat.id;
      const h = document.createElement("h3");
      h.className = "cat-h";
      h.innerHTML = '<span aria-hidden="true">' + cat.emo + "</span> " + esc(cat.label);
      box.appendChild(h);
      const grp = document.createElement("div"); grp.className = "opts";
      MENU.drinks.filter((d) => d.cat === cat.id).forEach((d) => {
        const el = optRadio("drink", "drink-" + d.name, d.name === defaultDrink,
          '<span class="emo" aria-hidden="true">' + d.emo + "</span>" +
          '<span class="body"><span class="nm">' + esc(d.label) + '</span><span class="meta">' + esc(d.meta) + "</span></span>" +
          '<span class="rt"><span class="price">' + money(d.price) + '</span><span class="tick" aria-hidden="true">✓</span></span>');
        el.querySelector("input").value = d.name;
        el.querySelector("input").setAttribute("aria-label", d.label + ", " + money(d.price));
        grp.appendChild(el);
      });
      box.appendChild(grp); host.appendChild(box);
    });

    // SIZE
    const gs = $("grp-size"); gs.innerHTML = "";
    MENU.sizes.forEach((sz, i) => {
      const el = optRadio("size", "size-" + sz.id, i === 0,
        '<span class="body"><span class="nm">' + esc(sz.label) + '</span><span class="meta">' + esc(sz.meta) + "</span></span>" +
        '<span class="rt"><span class="price' + (sz.up === 0 ? " free" : "") + '">' + (sz.up === 0 ? "base" : "+" + money(sz.up)) + "</span></span>");
      el.querySelector("input").value = sz.id;
      el.querySelector("input").setAttribute("aria-label", sz.label + " " + sz.meta + (sz.up ? ", plus " + money(sz.up) : ", base price"));
      gs.appendChild(el);
    });

    // SWEETNESS (free)
    const gw = $("grp-sweet"); gw.innerHTML = "";
    MENU.sweets.forEach((s, i) => {
      const el = optRadio("sweet", "sweet-" + i, i === 2, '<span class="body"><span class="nm">' + s + "</span></span>");
      el.querySelector("input").value = s; el.querySelector("input").setAttribute("aria-label", s + " sweetness");
      gw.appendChild(el);
    });
    // ICE (free)
    const gi = $("grp-ice"); gi.innerHTML = "";
    MENU.ices.forEach((s, i) => {
      const el = optRadio("ice", "ice-" + i, i === 0, '<span class="body"><span class="nm">' + s + "</span></span>");
      el.querySelector("input").value = s; el.querySelector("input").setAttribute("aria-label", s + " ice");
      gi.appendChild(el);
    });

    // TOPPINGS — pearls first when the fresh-batch salvage lever is live
    const note = $("pearl-note");
    if (eng.salvageActive) {
      note.innerHTML = "Today's <b>tapioca pearls</b> are a fresh batch near its sell-by, so the shop surfaces them first — enjoy them rather than see them binned. Priced at the menu like everything else; the real savings are the pickup and group levers below.";
    } else { note.textContent = "Add what you like."; }
    let order = MENU.tops.slice();
    if (eng.salvageActive) order.sort((a, b) => (b.name === MENU.batchTop ? 1 : 0) - (a.name === MENU.batchTop ? 1 : 0));
    const gt = $("grp-tops"); gt.innerHTML = "";
    order.forEach((t) => {
      const fresh = (t.name === MENU.batchTop && eng.salvageActive)
        ? '<span class="fresh-badge" id="fresh-badge">fresh batch today</span>' : "";
      const el = optCheck("top-" + t.name,
        '<span class="emo" aria-hidden="true">' + t.emo + "</span>" +
        '<span class="body"><span class="nm">' + esc(t.label) + "</span>" + fresh +
        '<span class="meta">' + esc(t.meta) + "</span></span>" +
        '<span class="rt"><span class="price">+' + money(t.price) + "</span></span>");
      el.querySelector("input").value = t.name;
      el.querySelector("input").setAttribute("aria-label", "Add " + t.label + ", plus " + money(t.price));
      gt.appendChild(el);
    });

    // PICKUP (lever)
    const gp = $("grp-pickup"); gp.innerHTML = "";
    PICKUP_UI.forEach((sl, i) => {
      const el = optRadio("pickup", "pickup-" + sl.id, i === 0,
        '<span class="body"><span class="nm">' + esc(sl.label) + '</span><span class="meta">' + esc(sl.meta) + "</span></span>" +
        '<span class="rt"><span class="save-chip zero" id="chip-slot-' + sl.id + '">—</span></span>');
      el.querySelector("input").value = sl.id;
      el.querySelector("input").setAttribute("aria-label", "Pickup " + sl.label);
      gp.appendChild(el);
    });
    // QUANTITY (lever)
    const gq = $("grp-qty"); gq.innerHTML = "";
    QTY_UI.forEach((q, i) => {
      const el = optRadio("qty", "qty-" + q.n, i === 0,
        '<span class="emo" aria-hidden="true">' + q.emo + "</span>" +
        '<span class="body"><span class="nm">' + esc(q.label) + '</span><span class="meta">' + esc(q.meta) + "</span></span>" +
        '<span class="rt"><span class="save-chip zero" id="chip-qty-' + q.n + '">—</span></span>');
      el.querySelector("input").value = String(q.n);
      el.querySelector("input").setAttribute("aria-label", q.label + ", " + q.n + (q.n === 1 ? " cup" : " cups"));
      gq.appendChild(el);
    });

    $("tablet").addEventListener("change", readAndRecompute);
    // active category tab tracks scroll
    const scroll = $("t-scroll");
    scroll.addEventListener("scroll", () => { markActiveCat(); }, { passive: true });
    readState();
  }

  function markActiveCat() {
    const scroll = $("t-scroll");
    const top = scroll.getBoundingClientRect().top + 90;
    let active = MENU.categories[0].id;
    for (const cat of MENU.categories) {
      const sec = $("cat-" + cat.id);
      if (sec && sec.getBoundingClientRect().top <= top) active = cat.id;
    }
    document.querySelectorAll(".cat-tab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.cat === active);
    });
  }

  function readState() {
    const g = (name) => { const el = document.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : null; };
    const tops = [];
    document.querySelectorAll("#grp-tops input:checked").forEach((i) => tops.push(i.value));
    const size = g("size") || "M";
    const sz = MENU.sizes.filter((s) => s.id === size)[0] || MENU.sizes[0];
    const slotId = g("pickup") || "now";
    const slot = PICKUP_UI.filter((s) => s.id === slotId)[0] || PICKUP_UI[0];
    cur = {
      drink: g("drink") || "brown-sugar-bobo",
      size, sizeUp: sz.up, slotId, slotTicks: slot.ticks,
      sweet: g("sweet") || "50%", ice: g("ice") || "Regular",
      tops, qty: parseInt(g("qty") || "1", 10),
    };
  }
  function readAndRecompute() { readState(); recompute(); }

  // ── the live recompute: total + every lever's real saving ────────────────────
  function recompute() {
    const now = priceOrder(eng, cur);
    $("pay").textContent = money(now.pay);
    if (now.save > 0.005) {
      $("menu-was").innerHTML = "menu <s>" + money(now.menu) + "</s>";
      $("saved").textContent = "you save " + money(now.save);
    } else {
      $("menu-was").textContent = "the menu price";
      $("saved").textContent = "";
    }

    // PICKUP chips — saving vs picking up Now, holding the rest of the cart fixed.
    // The same pass feeds the FIRST-SCREEN VALUE-PROP CUE (no duplicate quotes):
    // the levers sit below a 28-drink list, so on first glance the page reads as
    // a plain menu — the cue surfaces the engine's REAL best slot saving at the
    // sticky footer, and hides once a deferred slot is chosen or the engine says
    // $0 (honest).
    const nowSlot = priceOrder(eng, Object.assign({}, cur, { slotId: "now", slotTicks: 0 }));
    let bestSlotSave = 0;
    PICKUP_UI.forEach((sl) => {
      const chip = $("chip-slot-" + sl.id);
      if (sl.id === "now") { if (chip) setChip(chip, 0, "menu price"); return; }
      const alt = priceOrder(eng, Object.assign({}, cur, { slotId: sl.id, slotTicks: sl.ticks }));
      const save = round2(nowSlot.pay - alt.pay);
      bestSlotSave = Math.max(bestSlotSave, save);
      if (chip) setChip(chip, save, null);
    });
    const cue = $("save-cue");
    if (cue) {
      if (cur.slotTicks === 0 && bestSlotSave > 0.005) {
        cue.textContent = "★ Flexible on pickup? Save up to " + money(bestSlotSave) + " on this order";
        cue.classList.remove("hidden");
      } else {
        cue.classList.add("hidden");
      }
    }

    // QUANTITY chips — real saving on the EXTRA cups at the CURRENT slot (not "spend
    // less"): extra cups sit at menu on their own, and only save when the current
    // slot is an off-peak pickup that frees more of the rush.
    const one = priceOrder(eng, Object.assign({}, cur, { qty: 1 }));
    const pcm = perCupMenu(eng, Object.assign({}, cur, { qty: 1 }));
    QTY_UI.forEach((q) => {
      const chip = $("chip-qty-" + q.n);
      if (!chip) return;
      if (q.n === 1) { setChip(chip, 0, "—"); return; }
      const alt = priceOrder(eng, Object.assign({}, cur, { qty: q.n }));
      const extraMenu = (q.n - 1) * pcm;
      const extraPaid = round2(alt.pay - one.pay);
      setChip(chip, round2(extraMenu - extraPaid), null, "off the extra cups");
    });
  }

  function setChip(chip, save, zeroText, suffix) {
    if (save > 0.005) {
      chip.className = "save-chip";
      chip.textContent = "−" + money(save) + (suffix ? " " + suffix : "");
    } else {
      chip.className = "save-chip zero";
      chip.textContent = zeroText != null ? zeroText : "—";
    }
  }

  // ── receipt ─────────────────────────────────────────────────────────────────
  function buildReceipt() {
    const now = priceOrder(eng, cur);
    const nowSlot = priceOrder(eng, Object.assign({}, cur, { slotId: "now", slotTicks: 0 }));
    const pickupSave = round2(nowSlot.pay - now.pay);

    const topNames = cur.tops.map((t) => TOP[t].label);
    const slot = PICKUP_UI.filter((s) => s.id === cur.slotId)[0];
    $("r-order").innerHTML =
      '<div><span class="oq">' + cur.qty + " × " + esc(DRINK[cur.drink].label) +
      '</span> <span class="om">(' + (cur.size === "L" ? "Large" : "Medium") + ")</span></div>" +
      '<div class="om">' + esc(cur.sweet) + " sweet · " + esc(cur.ice.toLowerCase()) + " ice" +
      (topNames.length ? " · " + topNames.map(esc).join(", ") : "") + "</div>" +
      '<div class="om">pickup: ' + esc(slot ? slot.label.toLowerCase() : "now") + "</div>";

    $("r-lines").innerHTML =
      '<div class="r-line"><span class="rl-n">Menu price</span><span class="rl-p"><s>' + money(now.menu) + "</s></span></div>" +
      '<div class="r-line"><span class="rl-n">Your price</span><span class="rl-p"><b>' + money(now.pay) + "</b></span></div>";

    $("r-saved").textContent = money(now.save);
    const pct = now.menu > 0 ? Math.round((now.save / now.menu) * 100) : 0;
    // keep the % line consistent with the $ line: a real-but-tiny saving must not
    // print "0% off" next to a nonzero dollar
    $("r-pct").textContent = now.save > 0.005
      ? (pct >= 1 ? pct + "% off the menu · you paid " + money(now.pay)
                  : "under 1% off the menu · you paid " + money(now.pay))
      : "exactly the menu — no lever pulled yet";

    const why = [];
    if (cur.slotTicks > 0 && pickupSave > 0.005)
      why.push("A later, off-peak pickup freed the lunch rush — <b>" + money(pickupSave) + " vs. picking up now</b>.");
    if (cur.tops.indexOf(MENU.batchTop) >= 0 && eng.salvageActive)
      why.push("Today's tapioca pearls came from a fresh batch near its sell-by — surfaced first so they're enjoyed, not binned (priced at the menu, like every topping).");
    // HONESTY GATE: extra cups only save when they RIDE an off-peak slot (cost is
    // linear in qty — the engine gives $0 for qty alone). The "settles further
    // under the menu" claim is made only when the PER-CUP saving at this slot is
    // genuinely larger than one cup alone would get (real amplification).
    if (cur.qty > 1 && cur.slotTicks > 0 && now.save > 0.005) {
      const solo = priceOrder(eng, Object.assign({}, cur, { qty: 1 }));
      const perCupNow = now.save / cur.qty;
      if (perCupNow > solo.save + 0.005)
        why.push("Your " + cur.qty + " cups go in as one group order riding the off-peak slot — each cup settles <b>" + money(perCupNow) + "</b> under the menu (one cup alone: " + money(solo.save) + ").");
      else
        why.push("Your " + cur.qty + " cups go in as one group order on the off-peak slot, sharing the same saving.");
    } else if (cur.qty > 1 && cur.slotTicks === 0) {
      why.push("Your " + cur.qty + " cups are priced exactly at the menu — extra cups save only when paired with a later, off-peak pickup.");
    }
    if (!why.length) why.push("You're at the menu price — pick a later, off-peak pickup to see it drop.");
    $("r-why").innerHTML = "<b>Why it's a fair price:</b> " + why.join(" ") + " Your price is <b>never above the menu</b>, and every one of these is win-win.";

    $("r-repro").textContent = "Every price computed live by the SNHP general offer-graph engine (core/js) for the exact order you build — nothing scripted.";
  }

  // ── act transitions ─────────────────────────────────────────────────────────
  function setKicker(html) { $("kicker").innerHTML = html; }
  function enterSplash() {
    $("splash").classList.remove("hidden"); $("tablet").classList.add("hidden"); $("receipt").classList.add("hidden");
    $("stage").classList.remove("ordering"); $("kicker").classList.add("hidden"); camTo = 0;
  }
  function enterOrder() {
    $("splash").classList.add("hidden"); $("receipt").classList.add("hidden"); $("tablet").classList.remove("hidden");
    $("stage").classList.add("ordering"); $("kicker").classList.remove("hidden");
    setKicker("At the tablet — <b>your flexibility ticks the price down</b>");
    camTo = 1; recompute();
    const sc = $("t-scroll"); if (sc) sc.scrollTop = 0;
    markActiveCat();
  }
  function enterReceipt() {
    buildReceipt(); $("kicker").classList.remove("hidden"); $("tablet").classList.add("hidden");
    const rc = $("receipt"); rc.classList.remove("hidden");
    if (!reduced) { rc.classList.remove("printing"); void rc.offsetWidth; rc.classList.add("printing"); }
    setKicker("Your receipt — <b>you saved " + money(priceOrder(eng, cur).save) + "</b>");
    const again = $("r-again"); if (again && again.focus) { try { again.focus({ preventScroll: true }); } catch (e) {} }
  }

  // ── boot ────────────────────────────────────────────────────────────────────
  $("caveat").innerHTML = "<b>Every price is real.</b> Computed live by the SNHP general engine for the exact order you build — never above the menu.";
  resize(); lastW = window.innerWidth; lastH = window.innerHeight;
  requestAnimationFrame(frame);
  buildUI();
  enterSplash();
  $("splash").addEventListener("click", enterOrder);
  $("place").addEventListener("click", enterReceipt);
  $("r-again").addEventListener("click", enterOrder);
  $("save-cue").addEventListener("click", () => {
    const band = $("grp-pickup").closest(".lever-band");
    band.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
    band.classList.remove("pulse"); void band.offsetWidth;   // restart the pulse
    band.classList.add("pulse");
  });
}

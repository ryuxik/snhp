/* yourmenu.js — "Run it on your own menu" (Phase 4b of the SNHP redesign funnel).
 *
 * An owner/developer pastes THEIR menu as JSON and watches the REAL general
 * engine (core/js — the F1-validated JS mirror of core/*.py) work on it:
 *
 *   1. compile — the menu becomes an OfferGraph via core/js/api.mjs buildGraph
 *   2. profile — core/js/profiler.mjs classifies every dimension FREE / LEVER
 *   3. quote   — core/js/engine.mjs quote() prices any cart, discount-only
 *
 * EVERY dollar on the page is a live engine output on the pasted menu. The
 * shopper and the shop moment are SIMULATED and disclosed as such; nothing on
 * the page is a forecast.
 *
 * HONESTY (hard rules — do not regress):
 *   - Discount-only: the engine's price ladder tops out at list (its own
 *     invariant); the page ALSO sweeps the pasted menu live and shows the count.
 *   - No fabricated dollars: quotes come from quote(); spreads come from the
 *     cost model probe; nothing else prints money.
 *   - No provider-economics overclaim: this is the same engine our sims
 *     validate — real numbers depend on real demand. Said on the page.
 *
 * CORE/JS NOTES (gaps worked around HERE, per the Phase-4b rule not to touch
 * core/js):
 *   - profiler.mjs classifies on the COST spread (c_eff) only. A FULFILLMENT
 *     dimension's economics flow through the balk-hazard / capacity channels
 *     (`surv` and `credit` in engine.quote), which the cost probe cannot see,
 *     so "pickup" profiles FREE. The page shows the profiler's verdict
 *     verbatim and explains the timing channel beside it — it does NOT
 *     override the classifier.
 *   - profiler.mjs does not export its probe helpers (default config /
 *     variants), so the $-spread shown on the verdict cards re-implements the
 *     same probe (kept honest by yourmenu_verify.test.mjs, which asserts the
 *     card verdicts equal profile()'s output).
 *   - engine.quote's `config` argument restricts the candidate set BEFORE the
 *     disagreement anchor, so pinning a cart through it would also move the
 *     disagreement point. Like hook.js, we pin the cart with a search_filter
 *     and let the disagreement anchor on the shopper's best menu order
 *     (cart_nash semantics).
 *
 * Runs in the browser (boots the page) and under node (exports the pure
 * surface for arena/web/yourmenu_verify.test.mjs). No DOM work under node.
 */
import { buildGraph, profile as coreProfile } from "../../core/js/api.mjs";
import { DimKind, qtyOf } from "../../core/js/offer_graph.mjs";
import { ShopState } from "../../core/js/state.mjs";
import { SeparableBuyer, QuoteOpts, quote as coreQuote } from "../../core/js/engine.mjs";

// ════════════════════════════════════════════════════════════════════════════
//  THE SIMULATED SHOPPER — fixed, disclosed constants. The shopper wants
//  exactly the cart being priced (their taste), values it at a multiple of
//  list, and is a group buyer (each extra unit worth 90% of the previous).
//  Everything below is printed on the page next to the quote.
// ════════════════════════════════════════════════════════════════════════════
export const SHOPPER_LEVELS = [
  { id: "keen",       label: "Keen",       mult: 1.25, blurb: "values this cart ~25% above your list" },
  { id: "interested", label: "Interested", mult: 1.10, blurb: "values this cart ~10% above your list" },
  { id: "browsing",   label: "Browsing",   mult: 0.90, blurb: "values it below list — walks at menu prices" },
];
export const QTY_DECAY = 0.9;       // each extra unit worth 90% of the previous
export const BUSY_BALK = 0.30;      // busy rush: ~1 in 3 walk-ups bail at the line
export const DEFER_PER_TICK = 0.05; // waiting costs the shopper 5c per 10 minutes
const TICK_MINUTES = 10;            // 1 engine tick = 10 minutes

const SEP = "\u0000"; // engine.mjs key() separator (NUL)
const vkey = (dimId, optId) => dimId + SEP + optId;
const round2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;

// ════════════════════════════════════════════════════════════════════════════
//  EXAMPLE MENUS — deliberately NOT boba (the engine is general). Each carries
//  a `try` preset: the cart + moment where its lever is most legible.
// ════════════════════════════════════════════════════════════════════════════
export const EXAMPLES = {
  coffee: {
    label: "Coffee cart",
    hint: "Flip pickup back to “Right now” and the discount vanishes — the shop only shares what your flexibility actually saves it. Try Cold Brew: scarce stock holds at list.",
    try: {
      level: "interested", busy: true, endOfDay: false,
      cart: { item: "oat-latte", addons: ["extra-shot", "vanilla"], prefs: { cup: "to-go" }, slot: "in-20", qty: 1 },
    },
    menu: {
      name: "corner coffee cart",
      items: [
        { id: "oat-latte",  label: "Oat Latte",   price: 5.25, cost: 1.20 },
        { id: "cappuccino", label: "Cappuccino",  price: 4.75, cost: 1.05 },
        { id: "drip",       label: "Drip Coffee", price: 3.00, cost: 0.40 },
        { id: "cold-brew",  label: "Cold Brew",   price: 4.50, cost: 0.85, stock: 6, expected_demand: 10 },
      ],
      addons: [
        { id: "extra-shot", label: "Extra Shot",    price: 1.00, cost: 0.28 },
        { id: "vanilla",    label: "Vanilla Syrup", price: 0.50, cost: 0.10 },
      ],
      preferences: [
        { id: "cup", label: "Cup", options: [{ id: "for-here", label: "For here" }, { id: "to-go", label: "To go" }] },
      ],
      slots: [
        { id: "now",   label: "Right now", minutes: 0 },
        { id: "in-20", label: "In 20 min", minutes: 20, capacity: 6 },
      ],
      max_qty: 3,
    },
  },
  bakery: {
    label: "Bakery",
    hint: "Flip “end of day” off and the 3-croissant quote climbs back up — fresh-morning cost, higher floor. At quantity 1 it stays at list either way: a shopper who’d buy one at list anyway gets nothing from salvage alone.",
    try: {
      level: "interested", busy: false, endOfDay: true,
      cart: { item: "croissant", addons: [], prefs: { slicing: "whole" }, slot: null, qty: 3 },
    },
    menu: {
      name: "neighborhood bakery",
      items: [
        { id: "croissant",        label: "Butter Croissant", price: 4.25, cost: 0.95, perishable: true, salvage: 0.15 },
        { id: "almond-croissant", label: "Almond Croissant", price: 5.50, cost: 1.40, perishable: true, salvage: 0.20 },
        { id: "sourdough",        label: "Sourdough Loaf",   price: 9.00, cost: 2.60, perishable: true, salvage: 0.50 },
        { id: "granola-bar",      label: "Granola Bar",      price: 3.50, cost: 1.10 },
      ],
      addons: [{ id: "jam", label: "House Jam", price: 1.50, cost: 0.45 }],
      preferences: [
        { id: "slicing", label: "Slicing", options: [{ id: "whole", label: "Whole" }, { id: "sliced", label: "Sliced" }] },
      ],
      max_qty: 4,
      min_price_frac: 0.35,
    },
  },
};

// ════════════════════════════════════════════════════════════════════════════
//  VALIDATION — friendly, specific errors; NO silent fallbacks (anything the
//  page adds or reinterprets is surfaced as a visible note).
// ════════════════════════════════════════════════════════════════════════════
const ID_RE = /^[a-z0-9][a-z0-9_-]{0,39}$/i;
const RESERVED_DIM_IDS = ["item", "extras", "pickup", "qty"];
const TOP_KEYS = ["name", "currency", "items", "addons", "preferences", "slots", "max_qty", "min_price_frac"];
const ITEM_KEYS = ["id", "label", "price", "cost", "stock", "expected_demand", "perishable", "salvage", "note"];
const ADDON_KEYS = ["id", "label", "price", "cost", "perishable", "salvage", "note"];
const PREF_KEYS = ["id", "label", "options"];
const PREF_OPT_KEYS = ["id", "label", "price", "cost", "note"];
const SLOT_KEYS = ["id", "label", "minutes", "capacity"];
const MAX_ENUM = 300000;

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

export function parseMenuText(text) {
  if (!text || !text.trim()) {
    return { ok: false, errors: ["Paste a menu first — or load an example above."], notes: [] };
  }
  let raw;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    return {
      ok: false, notes: [],
      errors: ["Not valid JSON: " + (e && e.message ? e.message : e) +
               ". Tip: double-quoted keys, no trailing commas, no comments."],
    };
  }
  return validateMenu(raw);
}

export function validateMenu(raw) {
  const errors = [];
  const notes = [];
  const err = (m) => errors.push(m);

  if (!isObj(raw)) return { ok: false, errors: ["The top level must be a JSON object { ... }."], notes };

  for (const k of Object.keys(raw)) {
    if (!TOP_KEYS.includes(k)) err(`Unknown top-level key "${k}" — this page accepts: ${TOP_KEYS.join(", ")}.`);
  }

  const menu = {
    name: "your shop",
    currency: "$",
    items: [], addons: [], preferences: [], slots: null,
    max_qty: 3, min_price_frac: 0.6,
  };

  if (raw.name !== undefined) {
    if (typeof raw.name !== "string" || !raw.name.trim() || raw.name.length > 60) err(`"name" must be a non-empty string (max 60 chars).`);
    else menu.name = raw.name.trim();
  }
  if (raw.currency !== undefined) {
    if (typeof raw.currency !== "string" || raw.currency.length < 1 || raw.currency.length > 3) err(`"currency" must be a short string like "$" (display only).`);
    else menu.currency = raw.currency;
  }

  const seenIds = new Map(); // id -> where
  const claimId = (id, where) => {
    if (seenIds.has(id)) err(`Duplicate id "${id}" (${seenIds.get(id)} and ${where}) — ids must be unique across the whole menu.`);
    else seenIds.set(id, where);
  };

  const checkGood = (o, where, keys, kind) => {
    if (!isObj(o)) { err(`${where}: each ${kind} must be an object.`); return null; }
    for (const k of Object.keys(o)) {
      if (!keys.includes(k)) {
        if (kind === "add-on" && (k === "stock" || k === "expected_demand")) {
          err(`${where}: "${k}" is supported on items only — the engine's scarcity shadow reprices displaced units for the main choice, not add-ons.`);
        } else {
          err(`${where}: unknown key "${k}" — allowed: ${keys.join(", ")}.`);
        }
      }
    }
    if (typeof o.id !== "string" || !ID_RE.test(o.id)) { err(`${where}: "id" must be a short slug (letters, digits, - or _), e.g. "oat-latte".`); return null; }
    const out = { id: o.id, label: typeof o.label === "string" && o.label.trim() ? o.label.trim().slice(0, 60) : o.id };
    if (!isNum(o.price) || o.price <= 0 || o.price > 10000) { err(`${where} ("${o.id}"): "price" must be a number > 0 (your list price).`); return null; }
    if (!isNum(o.cost) || o.cost < 0 || o.cost > 10000) { err(`${where} ("${o.id}"): "cost" must be a number ≥ 0 (what one unit costs you to serve).`); return null; }
    out.price = o.price; out.cost = o.cost;
    if (o.cost > o.price) notes.push(`"${out.label}": cost ${menu.currency}${o.cost} exceeds price ${menu.currency}${o.price} — the engine never quotes below cost, so it can only ever sell at list. Check the numbers.`);
    if (o.perishable !== undefined && typeof o.perishable !== "boolean") { err(`${where} ("${o.id}"): "perishable" must be true or false.`); return null; }
    out.perishable = Boolean(o.perishable);
    if (o.salvage !== undefined) {
      if (!out.perishable) { err(`${where} ("${o.id}"): "salvage" only makes sense with "perishable": true.`); return null; }
      if (!isNum(o.salvage) || o.salvage < 0) { err(`${where} ("${o.id}"): "salvage" must be a number ≥ 0 (its value to you at close).`); return null; }
      if (o.salvage > o.cost) { err(`${where} ("${o.id}"): "salvage" above "cost" would make expiry profitable — check the numbers.`); return null; }
      out.salvage = o.salvage;
    } else if (out.perishable) {
      out.salvage = 0;
      notes.push(`"${out.label}" is perishable with no "salvage" given — treated as ${menu.currency}0 (a full write-off at close).`);
    } else {
      out.salvage = 0;
    }
    if (o.note !== undefined && typeof o.note !== "string") { err(`${where} ("${o.id}"): "note" must be a string.`); return null; }
    if (o.note) out.note = String(o.note).slice(0, 120);
    return out;
  };

  // items
  if (!Array.isArray(raw.items) || raw.items.length === 0) {
    err(`"items" is required: a non-empty array of what you sell, each with id, price and cost.`);
  } else if (raw.items.length > 40) {
    err(`"items": at most 40 (got ${raw.items.length}) — this page keeps the search space honest and fast.`);
  } else {
    raw.items.forEach((o, i) => {
      const g = checkGood(o, `items[${i}]`, ITEM_KEYS, "item");
      if (!g) return;
      if (o.stock !== undefined) {
        if (!Number.isInteger(o.stock) || o.stock < 0) { err(`items[${i}] ("${g.id}"): "stock" must be a whole number ≥ 0.`); return; }
        g.stock = o.stock;
      }
      if (o.expected_demand !== undefined) {
        if (g.stock === undefined) { err(`items[${i}] ("${g.id}"): "expected_demand" needs "stock" — it tells the scarcity shadow how many full-price buyers a discounted unit would displace.`); return; }
        if (!isNum(o.expected_demand) || o.expected_demand < 0) { err(`items[${i}] ("${g.id}"): "expected_demand" must be a number ≥ 0.`); return; }
        g.expected_demand = o.expected_demand;
      } else if (g.stock !== undefined) {
        notes.push(`"${g.label}": stock without "expected_demand" only gates availability — add expected_demand to arm the scarcity shadow (discount floors ride up when stock is short of demand).`);
      }
      claimId(g.id, `items[${i}]`);
      menu.items.push(g);
    });
  }

  // addons
  if (raw.addons !== undefined) {
    if (!Array.isArray(raw.addons)) err(`"addons" must be an array.`);
    else if (raw.addons.length > 12) err(`"addons": at most 12 (got ${raw.addons.length}) — the engine enumerates every subset, and caps add-on dimensions at 12 options.`);
    else raw.addons.forEach((o, i) => {
      const g = checkGood(o, `addons[${i}]`, ADDON_KEYS, "add-on");
      if (!g) return;
      claimId(g.id, `addons[${i}]`);
      menu.addons.push(g);
    });
  }

  // preferences
  if (raw.preferences !== undefined) {
    if (!Array.isArray(raw.preferences)) err(`"preferences" must be an array.`);
    else if (raw.preferences.length > 6) err(`"preferences": at most 6.`);
    else raw.preferences.forEach((p, i) => {
      if (!isObj(p)) { err(`preferences[${i}] must be an object.`); return; }
      for (const k of Object.keys(p)) if (!PREF_KEYS.includes(k)) err(`preferences[${i}]: unknown key "${k}" — allowed: ${PREF_KEYS.join(", ")}.`);
      if (typeof p.id !== "string" || !ID_RE.test(p.id)) { err(`preferences[${i}]: "id" must be a short slug.`); return; }
      if (RESERVED_DIM_IDS.includes(p.id)) { err(`preferences[${i}]: id "${p.id}" is reserved by this page (reserved: ${RESERVED_DIM_IDS.join(", ")}).`); return; }
      if (menu.preferences.some((x) => x.id === p.id)) { err(`preferences: duplicate id "${p.id}".`); return; }
      if (!Array.isArray(p.options) || p.options.length < 2 || p.options.length > 8) { err(`preferences[${i}] ("${p.id}"): "options" must be an array of 2–8 choices.`); return; }
      const pref = { id: p.id, label: typeof p.label === "string" && p.label.trim() ? p.label.trim().slice(0, 60) : p.id, options: [] };
      let bad = false;
      p.options.forEach((o, j) => {
        if (!isObj(o)) { err(`preferences[${i}].options[${j}] must be an object.`); bad = true; return; }
        for (const k of Object.keys(o)) if (!PREF_OPT_KEYS.includes(k)) err(`preferences[${i}].options[${j}]: unknown key "${k}" — allowed: ${PREF_OPT_KEYS.join(", ")}.`);
        if (typeof o.id !== "string" || !ID_RE.test(o.id)) { err(`preferences[${i}].options[${j}]: "id" must be a short slug.`); bad = true; return; }
        const opt = { id: o.id, label: typeof o.label === "string" && o.label.trim() ? o.label.trim().slice(0, 60) : o.id, price: 0, cost: 0 };
        if (o.price !== undefined) { if (!isNum(o.price) || o.price < 0) { err(`preferences[${i}].options[${j}]: "price" must be ≥ 0.`); bad = true; return; } opt.price = o.price; }
        if (o.cost !== undefined) { if (!isNum(o.cost) || o.cost < 0) { err(`preferences[${i}].options[${j}]: "cost" must be ≥ 0.`); bad = true; return; } opt.cost = o.cost; }
        claimId(opt.id, `preferences[${i}].options[${j}]`);
        pref.options.push(opt);
      });
      if (!bad) menu.preferences.push(pref);
    });
  }

  // slots
  if (raw.slots !== undefined) {
    if (!Array.isArray(raw.slots) || raw.slots.length === 0) err(`"slots" must be a non-empty array (or omit it entirely for a walk-up-only shop).`);
    else if (raw.slots.length > 6) err(`"slots": at most 6.`);
    else {
      const slots = [];
      const ticksSeen = new Map();
      raw.slots.forEach((s, i) => {
        if (!isObj(s)) { err(`slots[${i}] must be an object.`); return; }
        for (const k of Object.keys(s)) if (!SLOT_KEYS.includes(k)) err(`slots[${i}]: unknown key "${k}" — allowed: ${SLOT_KEYS.join(", ")}.`);
        if (typeof s.id !== "string" || !ID_RE.test(s.id)) { err(`slots[${i}]: "id" must be a short slug.`); return; }
        if (!Number.isInteger(s.minutes) || s.minutes < 0 || s.minutes > 480) { err(`slots[${i}] ("${s.id}"): "minutes" must be a whole number 0–480 (how much later than now).`); return; }
        const ticks = s.minutes === 0 ? 0 : Math.max(1, Math.round(s.minutes / TICK_MINUTES));
        if (ticksSeen.has(ticks)) { err(`slots[${i}] ("${s.id}"): resolves to the same ${TICK_MINUTES}-minute tick as "${ticksSeen.get(ticks)}" — space slots at least ${TICK_MINUTES} minutes apart.`); return; }
        ticksSeen.set(ticks, s.id);
        const slot = { id: s.id, label: typeof s.label === "string" && s.label.trim() ? s.label.trim().slice(0, 60) : s.id, minutes: s.minutes, ticks };
        if (s.capacity !== undefined) {
          if (!isNum(s.capacity) || s.capacity <= 0) { err(`slots[${i}] ("${s.id}"): "capacity" must be a number > 0 (units of room in that slot).`); return; }
          if (ticks === 0) { err(`slots[${i}] ("${s.id}"): "capacity" applies to later slots only — the immediate slot has no booking book.`); return; }
          slot.capacity = s.capacity;
        }
        claimId(slot.id, `slots[${i}]`);
        slots.push(slot);
      });
      if (slots.length && !slots.some((s) => s.ticks === 0)) {
        slots.unshift({ id: "now", label: "Right now", minutes: 0, ticks: 0 });
        notes.push(`Added a "now" slot (minutes 0): the engine anchors its walk-away point on an immediate order, so every menu needs one.`);
      }
      if (slots.length) menu.slots = slots;
    }
  }

  if (raw.max_qty !== undefined) {
    if (!Number.isInteger(raw.max_qty) || raw.max_qty < 1 || raw.max_qty > 6) err(`"max_qty" must be a whole number 1–6.`);
    else menu.max_qty = raw.max_qty;
  }
  if (raw.min_price_frac !== undefined) {
    if (!isNum(raw.min_price_frac) || raw.min_price_frac < 0 || raw.min_price_frac > 1) err(`"min_price_frac" must be a number between 0 and 1 (your floor: never quote below this fraction of list).`);
    else menu.min_price_frac = raw.min_price_frac;
  }

  // search-space guard
  if (menu.items.length) {
    let combos = menu.items.length * Math.pow(2, menu.addons.length) * (menu.slots ? menu.slots.length : 1) * menu.max_qty;
    for (const p of menu.preferences) combos *= p.options.length;
    if (combos > MAX_ENUM) err(`This menu enumerates ~${Math.round(combos).toLocaleString("en-US")} configurations — above this page's ${MAX_ENUM.toLocaleString("en-US")} cap. Trim add-ons or preference options.`);
  }

  if (errors.length) return { ok: false, errors, notes };
  notes.push(`Floor: quotes never go below ${Math.round(menu.min_price_frac * 100)}% of list (min_price_frac ${menu.min_price_frac}).`);
  return { ok: true, menu, errors: [], notes };
}

// ════════════════════════════════════════════════════════════════════════════
//  COMPILE — the page's menu format → buildGraph's declarative spec (pure
//  JSON: the exact object shown in the "take it with you" node snippet).
// ════════════════════════════════════════════════════════════════════════════
export function menuToSpec(menu) {
  const dims = [];
  dims.push({
    id: "item", kind: "choice",
    options: menu.items.map((it) => ({
      id: it.id, label: it.label, price_delta: it.price, unit_cost: it.cost,
      stock_limited: it.stock !== undefined,
      perishable: it.perishable, salvage: it.salvage,
    })),
  });
  if (menu.addons.length) {
    dims.push({
      id: "extras", kind: "addon",
      options: menu.addons.map((a) => ({
        id: a.id, label: a.label, price_delta: a.price, unit_cost: a.cost,
        perishable: a.perishable, salvage: a.salvage,
      })),
    });
  }
  for (const p of menu.preferences) {
    dims.push({
      id: p.id, kind: "preference",
      options: p.options.map((o) => ({ id: o.id, label: o.label, price_delta: o.price, unit_cost: o.cost })),
    });
  }
  if (menu.slots) {
    dims.push({
      id: "pickup", kind: "fulfillment",
      options: menu.slots.map((s) => ({ id: s.id, label: s.label, immediate: s.ticks === 0, slot_ticks: s.ticks })),
    });
  }
  dims.push({ id: "qty", kind: "quantity", qty_cap: menu.max_qty });

  const anyPerishable = menu.items.some((i) => i.perishable) || menu.addons.some((a) => a.perishable);
  const anyStock = menu.items.some((i) => i.stock !== undefined);
  const cost = ["const"];
  if (anyPerishable) cost.push("salvage_on_expiry");
  if (anyStock) cost.push("scarcity_shadow");
  return { name: menu.name, dims, cost };
}

export function makeState(menu, scenario) {
  const inventory = {};
  const expected_demand = {};
  for (const it of menu.items) {
    if (it.stock !== undefined) inventory[it.id] = it.stock;
    if (it.expected_demand !== undefined) expected_demand[it.id] = it.expected_demand;
  }
  const perishables = menu.items.concat(menu.addons).filter((x) => x.perishable).map((x) => x.id);
  const expiring = new Set(scenario.endOfDay ? perishables : []);
  const capacity = new Map();
  for (const s of menu.slots || []) if (s.ticks > 0 && s.capacity !== undefined) capacity.set(s.ticks, s.capacity);
  return new ShopState({ tick: 0, inventory, capacity, expiring, expected_demand });
}

// The simulated shopper wants exactly this cart: value = level × list price for
// each selected option, zero elsewhere. All constants disclosed on the page.
export function makeBuyer(menu, scenario, cart) {
  const lvl = SHOPPER_LEVELS.find((l) => l.id === scenario.level) || SHOPPER_LEVELS[1];
  const values = new Map();
  const it = menu.items.find((i) => i.id === cart.item);
  if (it) values.set(vkey("item", it.id), lvl.mult * it.price);
  for (const aid of cart.addons || []) {
    const a = menu.addons.find((x) => x.id === aid);
    if (a) values.set(vkey("extras", a.id), lvl.mult * a.price);
  }
  for (const p of menu.preferences) {
    const oid = (cart.prefs || {})[p.id];
    const o = p.options.find((x) => x.id === oid);
    if (o && o.price > 0) values.set(vkey(p.id, o.id), lvl.mult * o.price);
  }
  const defer = new Map([[0, 0]]);
  for (const s of menu.slots || []) defer.set(s.ticks, round2(DEFER_PER_TICK * s.ticks));
  return new SeparableBuyer({
    values, qty_decay: QTY_DECAY, outside: 0.0,
    balk: scenario.busy ? BUSY_BALK : 0.0, defer,
  });
}

export function makeContext(menu, scenario) {
  const spec = menuToSpec(menu);
  const graph = buildGraph(spec);
  const state = makeState(menu, scenario);
  return { menu, scenario, spec, graph, state };
}

// ════════════════════════════════════════════════════════════════════════════
//  PROFILE — the signature move: FREE vs LEVER per dimension, verbatim from
//  core/js/profiler.mjs, plus the $-spread its probe saw (re-implemented here
//  because the profiler doesn't export its probe helpers — see header note).
// ════════════════════════════════════════════════════════════════════════════
function probeSpread(graph, state, dim) {
  const base = {};
  for (const d of graph.dims) {
    if (d.kind === DimKind.QUANTITY) base[d.id] = 1;
    else if (d.kind === DimKind.ADDON) base[d.id] = [];
    else base[d.id] = d.options[0].id;
  }
  let variants;
  if (dim.kind === DimKind.QUANTITY) {
    variants = [1, Math.min(2, dim.qty_cap)].map((q) => ({ ...base, [dim.id]: q }));
  } else if (dim.kind === DimKind.ADDON) {
    variants = [{ ...base, [dim.id]: [] }].concat(dim.options.map((o) => ({ ...base, [dim.id]: [o.id] })));
  } else {
    variants = dim.options.map((o) => ({ ...base, [dim.id]: o.id }));
  }
  if (variants.length < 2) return 0;
  const costs = variants.map((c) => graph.cost.quote(graph, state, c, qtyOf(graph, c)).c_eff);
  return Math.max(...costs) - Math.min(...costs);
}

export function profileMenu(menu, scenario) {
  const ctx = makeContext(menu, scenario);
  const prof = coreProfile(ctx.graph, ctx.state);
  const cur = menu.currency;
  const cards = ctx.graph.dims.map((d) => {
    const verdict = prof[d.id];
    const spread = round2(probeSpread(ctx.graph, ctx.state, d));
    let label, why, tag = null;
    const flags = [];
    if (d.id === "item") {
      label = "Item";
      why = verdict === "lever"
        ? `Serving cost differs by up to ${cur}${spread.toFixed(2)} across your items — which one the shopper lands on changes what a deal costs you.`
        : `Every item costs you the same to serve — no cost gradient to negotiate over.`;
      for (const it of menu.items) {
        if (it.stock !== undefined && it.expected_demand !== undefined) {
          flags.push(`${it.label}: ${it.stock} in stock vs ~${it.expected_demand} expected buyers — every discounted unit displaces a full-price one, so its floor rides at your list (scarcity shadow).`);
        } else if (it.stock !== undefined) {
          flags.push(`${it.label}: ${it.stock} in stock — gates availability only (no expected_demand given).`);
        }
        if (it.perishable) flags.push(`${it.label}: perishable — at end of day its cost falls to salvage ${cur}${it.salvage.toFixed(2)}.`);
      }
    } else if (d.id === "extras") {
      label = "Extras";
      why = verdict === "lever"
        ? `Each extra carries real marginal cost (up to ${cur}${spread.toFixed(2)}) — the engine treats adding one as a costed move, not a freebie.`
        : `Your extras carry no cost — nothing for the engine to price.`;
      for (const a of menu.addons) if (a.perishable) flags.push(`${a.label}: perishable — end-of-day cost falls to salvage ${cur}${a.salvage.toFixed(2)}.`);
    } else if (d.kind === DimKind.PREFERENCE) {
      const p = menu.preferences.find((x) => x.id === d.id);
      label = p ? p.label : d.id;
      why = verdict === "free"
        ? `Zero cost gradient — the shopper's call, never priced. The engine pins it to their taste and prunes it from the search.`
        : `These options carry cost (${cur}${spread.toFixed(2)} spread) — priced like items, not a free preference.`;
    } else if (d.kind === DimKind.FULFILLMENT) {
      label = "Pickup";
      tag = "timing";
      why = `No unit-cost gradient, so the cost probe reads it FREE — timing's power is the hazard/capacity channel (deals appear when you're busy and the shopper can wait), which shows up in quotes below, not in cost.`;
    } else if (d.kind === DimKind.QUANTITY) {
      label = "Quantity";
      why = verdict === "lever"
        ? `Total cost scales with quantity (${cur}${spread.toFixed(2)} per extra unit) — but it's linear, so bigger orders win a better price only through the shopper's value curve or by riding a later slot, never per-unit cost magic.`
        : `Quantity moves no cost here.`;
    } else {
      label = d.id;
      why = verdict === "lever" ? `Cost probe saw a ${cur}${spread.toFixed(2)} spread.` : `Zero cost spread.`;
    }
    return { id: d.id, kind: d.kind, label, verdict, spread, why, tag, flags };
  });
  return { cards, raw: prof };
}

// ════════════════════════════════════════════════════════════════════════════
//  QUOTES — every price below is engine.quote() on the compiled graph. The
//  cart is pinned with a search_filter; the disagreement point roams free
//  (cart_nash semantics — see header note on why not `config`).
// ════════════════════════════════════════════════════════════════════════════
export function cartConfig(menu, cart) {
  const cfg = { item: cart.item };
  if (menu.addons.length) cfg.extras = [...(cart.addons || [])].sort();
  for (const p of menu.preferences) cfg[p.id] = (cart.prefs || {})[p.id] || p.options[0].id;
  if (menu.slots) cfg.pickup = cart.slot || menu.slots[0].id;
  cfg.qty = cart.qty || 1;
  return cfg;
}

function sameConfig(c, cfg) {
  for (const k of Object.keys(cfg)) {
    const a = c[k], b = cfg[k];
    if (Array.isArray(b)) {
      if ([...(a || [])].sort().join(",") !== [...b].sort().join(",")) return false;
    } else if (a !== b) return false;
  }
  return true;
}

export function listPriceOf(menu, cart) {
  const it = menu.items.find((i) => i.id === cart.item);
  let per = it ? it.price : 0;
  for (const aid of cart.addons || []) {
    const a = menu.addons.find((x) => x.id === aid);
    if (a) per += a.price;
  }
  for (const p of menu.preferences) {
    const o = p.options.find((x) => x.id === (cart.prefs || {})[p.id]);
    if (o) per += o.price;
  }
  return round2((cart.qty || 1) * per);
}

function listOfConfig(graph, cfg) {
  let total = 0;
  const q = qtyOf(graph, cfg);
  for (const d of graph.dims) {
    if (d.kind === DimKind.QUANTITY) continue;
    const sel = cfg[d.id];
    const ids = d.kind === DimKind.ADDON ? sel || [] : sel !== undefined && sel !== null ? [sel] : [];
    for (const oid of ids) total += d.option(oid).price_delta;
  }
  return q * total;
}

function immediateOf(graph, cfg) {
  for (const d of graph.dims) {
    if (d.kind === DimKind.FULFILLMENT) return d.option(cfg[d.id]).immediate;
  }
  return true;
}

// What this shopper does if talks fail — the engine's disagreement anchor,
// recomputed here for display (best immediate menu order by surplus at list).
export function walkInfo(graph, buyer) {
  let best = null;
  let sMenu = -Infinity;
  for (const c of graph.enumerateConfigs()) {
    if (!immediateOf(graph, c)) continue;
    const s = buyer.value(graph, c) - listOfConfig(graph, c);
    if (s > sMenu) { sMenu = s; best = c; }
  }
  const menuBuyer = best !== null && sMenu > 0 && sMenu >= buyer.outside_surplus();
  return { menuBuyer, sMenu, anchor: menuBuyer ? best : null };
}

export function describeConfig(menu, cfg) {
  const it = menu.items.find((i) => i.id === cfg.item);
  let s = (cfg.qty || 1) + " × " + (it ? it.label : cfg.item);
  for (const aid of cfg.extras || []) {
    const a = menu.addons.find((x) => x.id === aid);
    s += " + " + (a ? a.label : aid);
  }
  return s;
}

export function quoteWithCtx(ctx, cart) {
  const menu = ctx.menu;
  const buyer = makeBuyer(menu, ctx.scenario, cart);
  const cfg = cartConfig(menu, cart);
  const list = listPriceOf(menu, cart);
  const walk = walkInfo(ctx.graph, buyer);
  const qty = cfg.qty;
  const costq = ctx.graph.cost.quote(ctx.graph, ctx.state, cfg, qty);
  const base = { list, walk, floorsAtList: costq.floors_at_list, cfg };

  // availability pre-checks (the engine gates these silently; we say why)
  const it = menu.items.find((i) => i.id === cart.item);
  if (it && it.stock !== undefined && qty > it.stock) {
    return { ...base, outcome: "unavailable", price: list, save: 0, sellerGain: 0, buyerGain: 0,
      why: [`only ${it.stock} × ${it.label} in stock — quantity ${qty} can't be served today`] };
  }
  if (menu.slots && cfg.pickup) {
    const sl = menu.slots.find((s) => s.id === cfg.pickup);
    if (sl && sl.ticks > 0 && sl.capacity !== undefined && sl.capacity < qty) {
      return { ...base, outcome: "unavailable", price: list, save: 0, sellerGain: 0, buyerGain: 0,
        why: [`the "${sl.label}" slot has room for ${sl.capacity} — quantity ${qty} doesn't fit`] };
    }
  }

  const opts = new QuoteOpts({
    min_price_frac: menu.min_price_frac,
    prune_free: false,       // exact semantics: the user picks preferences by hand
    quote_lookers: true,
    search_filter: (graph, state, b, c) => sameConfig(c, cfg),
  });
  const q = coreQuote(ctx.graph, ctx.state, buyer, { config: null, opts });

  if (q && q.feasible && sameConfig(q.config, cfg)) {
    const price = round2(q.price);
    return { ...base, outcome: "negotiated", price, save: round2(list - price),
      sellerGain: q.seller_gain, buyerGain: q.buyer_gain, why: q.why, quote: q };
  }
  const why = q && q.why && q.why.length ? q.why : ["no split beat the walk-away — the quote is your list price"];
  return { ...base, outcome: "at-list", price: list, save: 0, sellerGain: 0, buyerGain: 0, why, quote: q };
}

export function quoteCart(menu, scenario, cart) {
  return quoteWithCtx(makeContext(menu, scenario), cart);
}

// The in-page invariant check: sweep carts on THIS menu at THIS moment and
// count anything above list (the engine guarantees zero; we show the receipts).
export function sweepNeverAboveList(menu, scenario) {
  const ctx = makeContext(menu, scenario);
  const addonSets = [[]];
  const seen = new Set([""]);
  const addSet = (s) => { const k = [...s].sort().join(","); if (!seen.has(k)) { seen.add(k); addonSets.push(s); } };
  if (menu.addons.length) {
    addSet(menu.addons.map((a) => a.id));
    for (const a of menu.addons) addSet([a.id]);
  }
  const slots = menu.slots ? menu.slots.map((s) => s.id) : [null];
  const prefs = {};
  for (const p of menu.preferences) prefs[p.id] = p.options[0].id;
  let checked = 0;
  const violations = [];
  for (const it of menu.items) {
    for (const as of addonSets) {
      for (const sl of slots) {
        for (let q = 1; q <= menu.max_qty; q++) {
          const cart = { item: it.id, addons: as, prefs, slot: sl, qty: q };
          const r = quoteWithCtx(ctx, cart);
          checked++;
          if (r.price > r.list + 1e-9) violations.push({ cart, price: r.price, list: r.list });
        }
      }
    }
  }
  return { checked, violations };
}

// ════════════════════════════════════════════════════════════════════════════
//  TAKE IT WITH YOU — the agent path. (a) is the user's own JSON (handled by
//  the UI verbatim); (b) and (c) are generated here from the live objects.
// ════════════════════════════════════════════════════════════════════════════
export function nodeSnippet(menu, scenario, cart) {
  const spec = menuToSpec(menu);
  const state = makeState(menu, scenario);
  const buyer = makeBuyer(menu, scenario, cart);
  const inv = JSON.stringify(state.inventory);
  const dem = JSON.stringify(state.expected_demand);
  const exp = JSON.stringify([...state.expiring]);
  const cap = JSON.stringify([...state.capacity.entries()]);
  const vals = [...buyer.values.entries()].map(([k, v]) => `  [${JSON.stringify(k)}, ${round2(v)}],`).join("\n");
  const defer = JSON.stringify([...buyer.defer.entries()]);
  return `// ${menu.name} — priced by the SNHP general offer-graph engine (core/js).
// No npm deps. Put this file next to the snhp repo's core/ directory and run:
//   node price-my-menu.mjs
import { buildGraph, profile, quote } from "./core/js/api.mjs";
import { ShopState } from "./core/js/state.mjs";
import { SeparableBuyer, QuoteOpts } from "./core/js/engine.mjs";

// 1 — your menu, compiled to the engine's declarative spec
const spec = ${JSON.stringify(spec, null, 2)};
const graph = buildGraph(spec);

// 2 — the shop moment (the state the cost model reads)
const state = new ShopState({
  inventory: ${inv},          // finite stock by option id
  expected_demand: ${dem},    // buyers you expect for stocked options
  expiring: new Set(${exp}),  // perishables at salvage right now
  capacity: new Map(${cap}),  // [slot_ticks, units of room]
});

// 3 — FREE vs LEVER, straight from the profiler
console.log(profile(graph, state));

// 4 — a shopper (values in dollars per option, keyed "dim\\u0000option")
const buyer = new SeparableBuyer({
  values: new Map([
${vals}
  ]),
  qty_decay: ${QTY_DECAY},   // each extra unit worth ${Math.round(QTY_DECAY * 100)}% of the previous
  outside: 0.0,      // their walk-away surplus
  balk: ${buyer.balk},        // chance they bail if served immediately
  defer: new Map(${defer}), // [slot_ticks, what waiting costs them]
});

// 5 — the quote. Discount-only: price never exceeds list (engine invariant).
const q = quote(graph, state, buyer, {
  opts: new QuoteOpts({ min_price_frac: ${menu.min_price_frac}, prune_free: false }),
});
console.log(q && { config: q.config, list: q.listv, price: q.price, why: q.why });
`;
}

export function agentPrompt(menu, profiled, rawJson) {
  const free = profiled.cards.filter((c) => c.verdict === "free" && c.kind !== DimKind.FULFILLMENT).map((c) => c.label);
  const levers = profiled.cards.filter((c) => c.verdict === "lever").map((c) => c.label);
  const scarce = menu.items.filter((i) => i.stock !== undefined && i.expected_demand !== undefined && i.stock < i.expected_demand).map((i) => i.label);
  const perish = menu.items.concat(menu.addons).filter((x) => x.perishable).map((x) => x.label);
  const lines = [
    `You are my purchasing agent at "${menu.name}".`,
    ``,
    `Below is the shop's machine-readable menu (JSON) and the negotiation surface`,
    `the SNHP offer-graph engine profiled from it.`,
    ``,
    `Set purely to my taste, never pay extra for them (FREE — zero cost gradient):`,
    `  ${free.length ? free.join(", ") : "(none)"}`,
    `Worth negotiating (LEVER — cost moves with the shop's state):`,
    `  ${levers.length ? levers.join(", ") : "(none)"}`,
  ];
  if (menu.slots) {
    lines.push(
      `Timing: pickup — if the shop looks busy, offer a later slot; it removes their`,
      `  risk of losing the sale to the line and can earn a lower price.`
    );
  }
  if (scarce.length) lines.push(`Scarce right now (discounts unlikely — don't push): ${scarce.join(", ")}.`);
  if (perish.length) lines.push(`Perishable (ask near closing time): ${perish.join(", ")}.`);
  lines.push(
    ``,
    `Rules:`,
    `1. Discount-only: never accept a price above the menu's listed total.`,
    `2. State only true constraints — do not invent urgency or misstate my`,
    `   flexibility; in this protocol such claims must hold up.`,
    `3. Ask for an itemized receipt: list price, agreed price, and the reason.`,
    ``,
    `MENU JSON:`,
    rawJson.trim()
  );
  return lines.join("\n");
}

// The DEPLOYED twin of the node snippet: the SAME friendly menu you pasted,
// POSTed to the hosted general engine (gametheory/server/offer_api.py, which
// now dual-accepts this friendly format via friendly_to_dims). /profile
// returns the verdicts shown in section 2; /quote runs the same search the
// node snippet runs (the engine's best deal for the simulated shopper) — so
// the hosted response is byte-for-byte what "price it yourself" prints, with
// nothing installed. `rawMenu` is the exact friendly paste (the spec body);
// the state/buyer are built from the same makeState/makeBuyer the page uses.
export const API_BASE = "https://api.snhp.dev";

export function hostedCurl(menu, scenario, cart, rawMenu, apiBase = API_BASE) {
  const st = makeState(menu, scenario);
  const state = {
    tick: st.tick,
    inventory: st.inventory,
    capacity: Object.fromEntries([...st.capacity.entries()]),
    expiring: [...st.expiring],
    expected_demand: st.expected_demand,
  };
  const buyer = makeBuyer(menu, scenario, cart);
  const values = {};
  for (const [k, v] of buyer.values.entries()) {
    const i = k.indexOf(SEP);
    const dim = k.slice(0, i), opt = k.slice(i + 1);
    (values[dim] || (values[dim] = {}))[opt] = round2(v);
  }
  const buyerJson = {
    values,
    qty_decay: buyer.qty_decay,
    outside: buyer.outside,
    balk: buyer.balk,
    defer: Object.fromEntries([...buyer.defer.entries()]),
  };
  const curl = (path, obj) =>
    `curl -sS ${apiBase}/v1/offer/${path} \\\n` +
    `  -H 'content-type: application/json' \\\n` +
    `  -d '${JSON.stringify(obj, null, 2)}'`;
  return {
    profile: curl("profile", { spec: rawMenu, state }),
    quote: curl("quote", {
      spec: rawMenu, state, buyer: buyerJson,
      opts: { min_price_frac: menu.min_price_frac },
    }),
  };
}

// ════════════════════════════════════════════════════════════════════════════
//  BROWSER — the page. (Nothing below runs under node.)
// ════════════════════════════════════════════════════════════════════════════
if (typeof document !== "undefined") boot();

function boot() {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

  let MENU = null;      // validated menu
  let CTX = null;       // { graph, state, ... } for the current scenario
  let PROF = null;      // profileMenu output
  let RAW_JSON = "";    // the exact text the user ran
  let SCN = { busy: false, endOfDay: false, level: "interested" };
  let CART = null;
  let HINT = "";

  const money = (x) => (MENU ? MENU.currency : "$") + Number(x).toFixed(2);

  // ── run ────────────────────────────────────────────────────────────────────
  function run(preset, scroll = true) {
    const text = $("menu-input").value;
    const res = parseMenuText(text);
    const errBox = $("parse-err");
    if (!res.ok) {
      errBox.innerHTML = "<b>Couldn't read that menu:</b><ul>" + res.errors.map((e) => "<li>" + esc(e) + "</li>").join("") + "</ul>";
      errBox.classList.remove("hidden");
      $("results").classList.add("hidden");
      return;
    }
    errBox.classList.add("hidden");
    MENU = res.menu;
    RAW_JSON = text;
    HINT = preset && preset.hint ? preset.hint : "";

    if (preset && preset.try) {
      SCN = { busy: !!preset.try.busy, endOfDay: !!preset.try.endOfDay, level: preset.try.level || "interested" };
      CART = JSON.parse(JSON.stringify(preset.try.cart));
    } else {
      SCN = { busy: false, endOfDay: false, level: SCN.level || "interested" };
      CART = defaultCart(MENU);
    }
    if (!MENU.slots) { SCN.busy = false; CART.slot = null; }
    if (!MENU.items.concat(MENU.addons).some((x) => x.perishable)) SCN.endOfDay = false;
    sanitizeCart();

    renderCompile(res.notes);
    rebuildScenario();     // ctx + verdicts + sweep + controls + quote
    $("results").classList.remove("hidden");
    if (scroll) $("results").scrollIntoView({ behavior: prefersReduced() ? "auto" : "smooth", block: "start" });
  }

  function prefersReduced() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function defaultCart(menu) {
    const prefs = {};
    for (const p of menu.preferences) prefs[p.id] = p.options[0].id;
    return { item: menu.items[0].id, addons: [], prefs, slot: menu.slots ? menu.slots[0].id : null, qty: 1 };
  }

  function sanitizeCart() {
    if (!MENU.items.some((i) => i.id === CART.item)) CART.item = MENU.items[0].id;
    CART.addons = (CART.addons || []).filter((a) => MENU.addons.some((x) => x.id === a));
    const prefs = {};
    for (const p of MENU.preferences) {
      const want = (CART.prefs || {})[p.id];
      prefs[p.id] = p.options.some((o) => o.id === want) ? want : p.options[0].id;
    }
    CART.prefs = prefs;
    if (MENU.slots) {
      if (!MENU.slots.some((s) => s.id === CART.slot)) CART.slot = MENU.slots[0].id;
    } else CART.slot = null;
    CART.qty = Math.min(Math.max(1, CART.qty | 0), MENU.max_qty);
  }

  // ── section 1 · compile summary ─────────────────────────────────────────────
  function renderCompile(notes) {
    $("compile-name").textContent = MENU.name;
    const spec = menuToSpec(MENU);
    const kinds = { choice: "choice", addon: "add-ons", preference: "preference", fulfillment: "fulfillment", quantity: "quantity" };
    $("dim-chips").innerHTML = spec.dims.map((d) => {
      const n = d.kind === "quantity" ? "1–" + MENU.max_qty : (d.options || []).length + " options";
      return `<span class="chip"><b>${esc(d.id)}</b> · ${kinds[d.kind] || d.kind} · ${n}</span>`;
    }).join("");
    $("cost-chips").innerHTML = spec.cost.map((c) => {
      const t = typeof c === "string" ? c : Object.keys(c)[0];
      return `<span class="chip gold">${esc(t)}</span>`;
    }).join("");
    $("compile-notes").innerHTML = notes.length
      ? notes.map((n) => "<li>" + esc(n) + "</li>").join("")
      : "<li>No adjustments — your menu compiled as written.</li>";
  }

  // ── section 2 · verdicts + sweep (scenario-dependent) ──────────────────────
  function rebuildScenario() {
    CTX = makeContext(MENU, SCN);
    PROF = profileMenu(MENU, SCN);
    renderVerdicts();
    renderSweep();
    renderPlayground();
    renderQuote();
    renderTakeaway();
  }

  function renderVerdicts() {
    $("verdicts").innerHTML = PROF.cards.map((c) => {
      const pill = c.verdict === "free"
        ? `<span class="pill free">FREE</span>`
        : `<span class="pill lever">LEVER</span>`;
      const tag = c.tag ? `<span class="pill timing">${esc(c.tag)}</span>` : "";
      const flags = c.flags.length ? `<ul class="flags">${c.flags.map((f) => "<li>" + esc(f) + "</li>").join("")}</ul>` : "";
      return `<div class="vcard">
        <div class="vhead"><span class="vname">${esc(c.label)}</span>${pill}${tag}</div>
        <p class="vwhy">${esc(c.why)}</p>${flags}
      </div>`;
    }).join("");
  }

  function renderSweep() {
    const lvl = SHOPPER_LEVELS.find((l) => l.id === SCN.level) || SHOPPER_LEVELS[1];
    const s = sweepNeverAboveList(MENU, SCN);
    const el = $("sweep-line");
    if (s.violations.length === 0) {
      el.innerHTML = `<b>Never above your list — checked live on this menu:</b> ${s.checked} carts quoted just now ` +
        `(every item × extras × ${MENU.slots ? "slot × " : ""}quantity, ${esc(lvl.label.toLowerCase())} shopper, this moment) — <b class="ok">0 above list</b>. ` +
        `Discount-only is engine-enforced: its price ladder tops out at your list price.`;
      el.classList.remove("bad");
    } else {
      el.innerHTML = `<b class="warn">Invariant violation:</b> ${s.violations.length} of ${s.checked} quotes exceeded list — this should be impossible; please report it.`;
      el.classList.add("bad");
    }
  }

  // ── section 3 · playground ──────────────────────────────────────────────────
  function renderPlayground() {
    // item select
    $("pg-item").innerHTML = MENU.items.map((i) =>
      `<option value="${esc(i.id)}"${i.id === CART.item ? " selected" : ""}>${esc(i.label)} — ${money(i.price)}</option>`).join("");

    // addons
    const ab = $("pg-addons");
    if (MENU.addons.length) {
      ab.innerHTML = MENU.addons.map((a) => {
        const on = CART.addons.includes(a.id);
        return `<label class="check"><input type="checkbox" data-addon="${esc(a.id)}"${on ? " checked" : ""}> ${esc(a.label)} <span class="dim">+${money(a.price)}</span></label>`;
      }).join("");
      $("fs-addons").classList.remove("hidden");
    } else $("fs-addons").classList.add("hidden");

    // preferences
    const pb = $("pg-prefs");
    if (MENU.preferences.length) {
      pb.innerHTML = MENU.preferences.map((p) =>
        `<label class="sel-wrap">${esc(p.label)} <span class="pill free small">FREE</span>
          <select data-pref="${esc(p.id)}">` +
          p.options.map((o) => `<option value="${esc(o.id)}"${CART.prefs[p.id] === o.id ? " selected" : ""}>${esc(o.label)}${o.price > 0 ? " +" + money(o.price) : ""}</option>`).join("") +
        `</select></label>`).join("");
      // hide the FREE pill on priced preferences (they profile LEVER)
      MENU.preferences.forEach((p) => {
        const card = PROF.cards.find((c) => c.id === p.id);
        if (card && card.verdict !== "free") {
          const el = pb.querySelector(`select[data-pref="${p.id}"]`);
          if (el) { const pill = el.closest("label").querySelector(".pill"); if (pill) pill.remove(); }
        }
      });
      $("fs-prefs").classList.remove("hidden");
    } else $("fs-prefs").classList.add("hidden");

    // slots (radio) — each carries a live save chip vs list
    const sb = $("pg-slot");
    if (MENU.slots) {
      sb.innerHTML = MENU.slots.map((s) =>
        `<label class="radio"><input type="radio" name="pg-slot" value="${esc(s.id)}"${CART.slot === s.id ? " checked" : ""}>
          <span class="rlab">${esc(s.label)}</span>
          <span class="save-chip zero" id="chip-slot-${esc(s.id)}">—</span></label>`).join("");
      $("fs-slot").classList.remove("hidden");
    } else $("fs-slot").classList.add("hidden");

    // qty
    const qb = $("pg-qty");
    qb.innerHTML = Array.from({ length: MENU.max_qty }, (_, i) => i + 1).map((n) =>
      `<option value="${n}"${CART.qty === n ? " selected" : ""}>${n} ${n === 1 ? "unit" : "units"}</option>`).join("");
    $("fs-qty").classList.toggle("hidden", MENU.max_qty <= 1);

    // shopper level
    $("pg-level").innerHTML = SHOPPER_LEVELS.map((l) =>
      `<option value="${l.id}"${SCN.level === l.id ? " selected" : ""}>${l.label} — ${l.blurb}</option>`).join("");

    // moment toggles
    const anyPerish = MENU.items.concat(MENU.addons).some((x) => x.perishable);
    $("tg-busy-wrap").classList.toggle("hidden", !MENU.slots);
    $("tg-busy").checked = SCN.busy;
    $("tg-eod-wrap").classList.toggle("hidden", !anyPerish);
    $("tg-eod").checked = SCN.endOfDay;
    $("no-toggles").classList.toggle("hidden", Boolean(MENU.slots) || anyPerish);

    $("pg-hint").textContent = HINT;
    $("pg-hint").classList.toggle("hidden", !HINT);
  }

  function readCart() {
    CART.item = $("pg-item").value;
    CART.addons = [...document.querySelectorAll("#pg-addons input[data-addon]:checked")].map((el) => el.dataset.addon);
    for (const p of MENU.preferences) {
      const el = document.querySelector(`#pg-prefs select[data-pref="${p.id}"]`);
      if (el) CART.prefs[p.id] = el.value;
    }
    if (MENU.slots) {
      const el = document.querySelector('input[name="pg-slot"]:checked');
      CART.slot = el ? el.value : MENU.slots[0].id;
    }
    CART.qty = parseInt($("pg-qty").value || "1", 10);
  }

  function renderQuote() {
    const r = quoteWithCtx(CTX, CART);
    const lvl = SHOPPER_LEVELS.find((l) => l.id === SCN.level) || SHOPPER_LEVELS[1];

    $("q-list").textContent = money(r.list);
    $("q-list").classList.toggle("struck", r.save > 0.005);
    $("q-price").textContent = money(r.price);
    if (r.save > 0.005) {
      $("q-save").textContent = "−" + money(r.save) + " (" + Math.round((r.save / r.list) * 100) + "% under list)";
      $("q-save").className = "q-save on";
    } else {
      $("q-save").textContent = "at your list price";
      $("q-save").className = "q-save";
    }

    const oc = $("q-outcome");
    if (r.outcome === "negotiated") {
      oc.textContent = "engine deal — both sides gain vs. no deal";
      oc.className = "q-outcome deal";
    } else if (r.outcome === "unavailable") {
      oc.textContent = "can't be served";
      oc.className = "q-outcome warn";
    } else {
      oc.textContent = "engine holds at list";
      oc.className = "q-outcome";
    }

    $("q-why").innerHTML = r.why.map((w) => "<li>" + esc(w) + "</li>").join("");

    // the walk-away column (the disagreement the engine anchored on)
    const w = r.walk;
    $("q-walk").textContent = w.menuBuyer
      ? "they'd buy " + describeConfig(MENU, w.anchor) + " at list anyway — any deal must beat that for you too"
      : "they walk — nothing on your menu clears their number at list";

    // extra honesty notes
    const notes = [];
    if (r.floorsAtList && r.outcome !== "negotiated") {
      notes.push("The engine's cost floor for this cart sits at (or above) your list — e.g. scarce stock reprices displaced units at list — so there is no room to move.");
    }
    if (r.outcome === "negotiated" && lvl.id === "browsing") {
      notes.push("This shopper wouldn't buy at your list, so the engine is clearing stock to them where that beats no sale. In the live protocol a shopper can't simply claim to be walking — such claims must hold up.");
    }
    if (r.outcome === "negotiated") {
      notes.push("Split check (engine receipt): your gain " + money(Math.max(0, r.sellerGain)) + " · shopper's gain " + money(Math.max(0, r.buyerGain)) + " vs. no deal.");
    }
    $("q-notes").innerHTML = notes.map((n) => "<li>" + esc(n) + "</li>").join("");

    // scenario disclosure line
    const bits = [
      "values this cart at ×" + lvl.mult.toFixed(2) + " of list",
      "each extra unit worth " + Math.round(QTY_DECAY * 100) + "% of the previous",
    ];
    if (MENU.slots) bits.push("waiting costs them " + money(DEFER_PER_TICK) + " per " + TICK_MINUTES + " min");
    bits.push("walk-away outside option: none");
    const moment = [];
    if (MENU.slots) moment.push(SCN.busy ? "busy rush (~1 in " + Math.round(1 / BUSY_BALK) + " walk-ups bail at the line)" : "quiet (no line)");
    if (MENU.items.concat(MENU.addons).some((x) => x.perishable)) moment.push(SCN.endOfDay ? "end of day (perishables at salvage)" : "mid-shift (everything fresh)");
    $("q-scenario").textContent = "Simulated shopper: " + bits.join(" · ") + ". Simulated moment: " + (moment.length ? moment.join(" · ") : "an ordinary shift") + ".";

    // per-slot chips: quote the same cart in every slot
    if (MENU.slots) {
      for (const s of MENU.slots) {
        const chip = $("chip-slot-" + s.id);
        if (!chip) continue;
        const alt = s.id === CART.slot ? r : quoteWithCtx(CTX, { ...CART, slot: s.id });
        if (alt.save > 0.005) {
          chip.className = "save-chip";
          chip.textContent = "−" + money(alt.save);
        } else {
          chip.className = "save-chip zero";
          chip.textContent = alt.outcome === "unavailable" ? "full" : "list";
        }
      }
    }
  }

  // ── section 4 · take it with you ────────────────────────────────────────────
  function renderTakeaway() {
    $("code-json").textContent = RAW_JSON.trim();
    $("code-node").textContent = nodeSnippet(MENU, SCN, CART);
    $("code-agent").textContent = agentPrompt(MENU, PROF, RAW_JSON);
    let rawMenu;
    try { rawMenu = JSON.parse(RAW_JSON); } catch (e) { rawMenu = MENU; }
    const hc = hostedCurl(MENU, SCN, CART, rawMenu);
    $("code-curl-profile").textContent = hc.profile;
    $("code-curl-quote").textContent = hc.quote;
  }

  function copyFrom(preId, btn) {
    const text = $(preId).textContent;
    const done = () => {
      const old = btn.textContent;
      btn.textContent = "copied ✓";
      setTimeout(() => { btn.textContent = old; }, 1400);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    } else fallbackCopy(text, done);
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { /* leave the text selectable */ }
    document.body.removeChild(ta);
  }

  // ── wiring ──────────────────────────────────────────────────────────────────
  $("btn-run").addEventListener("click", () => run(null));
  $("btn-ex-coffee").addEventListener("click", () => {
    $("menu-input").value = JSON.stringify(EXAMPLES.coffee.menu, null, 2);
    run(EXAMPLES.coffee);
  });
  $("btn-ex-bakery").addEventListener("click", () => {
    $("menu-input").value = JSON.stringify(EXAMPLES.bakery.menu, null, 2);
    run(EXAMPLES.bakery);
  });

  $("playground").addEventListener("change", (ev) => {
    const t = ev.target;
    if (!MENU) return;
    if (t.id === "pg-level") {
      SCN.level = t.value;
      renderSweep();      // the sweep discloses the shopper level it used
      readCart();
      renderQuote();
      renderTakeaway();
      return;
    }
    if (t.id === "tg-busy" || t.id === "tg-eod") {
      SCN.busy = $("tg-busy").checked;
      SCN.endOfDay = $("tg-eod").checked;
      readCart();
      rebuildScenario();  // state changed: re-profile, re-sweep, re-quote
      return;
    }
    readCart();
    renderQuote();
    renderTakeaway();
  });

  document.querySelectorAll("button[data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => copyFrom(btn.dataset.copy, btn));
  });

  // boot with the coffee example so the page is alive immediately (clearly
  // labeled as the example — pasting your own replaces it); no auto-scroll.
  $("menu-input").value = JSON.stringify(EXAMPLES.coffee.menu, null, 2);
  run(EXAMPLES.coffee, false);
}

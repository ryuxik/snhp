/* boba-world.mjs — THE single JS-side boba world.
 *
 * A faithful re-implementation of boba/world.py's demand model and shop
 * physics (appeal inversion -> WTP, hourly WTP multipliers, FIFO balk hazard,
 * service capacity, tapioca batches, capacity_relief, defer schedules) plus
 * the consumer draws and settle/accounting the owner sandbox needs
 * (boba/run.py's run_day arrivals + _settle).
 *
 * This module deliberately contains ZERO pricing: the Nash quote lives in
 * core/js/engine.mjs, reached through core/js/boba_adapter.mjs, which is
 * parameterized by the `world` object makeWorld() returns. Every JS surface
 * that needs boba's world math (hook.js, boba-sim.js) imports THIS module —
 * there is exactly one copy of the world on the JS side, cross-checked
 * against the Python source of record by arena/web/bobaworld_verify.test.mjs
 * (fixtures regenerated from boba/world.py by core/js/test/dump_fixtures.py).
 *
 * Fidelity notes:
 *   - erfc is a full double-precision implementation (via the regularized
 *     incomplete gamma, NR gser/gcf), matching Python math.erfc to ~1e-15 —
 *     NOT the old |err|<1.2e-7 erfcc approximation the legacy engine used.
 *   - appeal inversion bisects exactly like world.appeal_for_list (28 iters);
 *     the inner argmax is golden-section to machine precision, so agreement
 *     with Python is bounded by scipy minimize_scalar's own xatol=1e-5 —
 *     asserted at that honest tolerance in bobaworld_verify.test.mjs, while
 *     everything downstream of a given appeal matches within 1e-9.
 *   - the PRNG is mulberry32 (JS), not numpy PCG64: consumer DRAWS reproduce
 *     distributions, not byte-exact streams (the sandbox's Monte-Carlo band).
 *   - maybeCook carries the sandbox's demand-aware dead-shop guard (restock
 *     only while cups are selling) — a documented divergence from Python's
 *     unconditional maybe_cook that only matters in the demand-collapse
 *     regime; on any live menu it is a no-op.
 *
 * Runs in the browser (ESM import) and in node (node --test); also mirrored
 * onto globalThis.SNHP_boba_world like the core/js modules.
 */

// ── calibration constants (boba/world.py) ──────────────────────────────────
export const WTP_SIGMA = 0.45;
export const TOP_SIGMA = 0.70;
export const CROSS_DISCOUNT = 0.55;
export const GROUP_SHARE = 0.30;
export const GROUP_DECAY = 0.60;
export const SOLO_DECAY = 0.15;
export const QTY_CAP = 3;
export const OUTSIDE_MARKUP = 1.10;
export const TICKS_PER_DAY = 72;
export const OPEN_HOUR = 10;
export const CAPACITY_PER_MIN = 1.5;                  // 2 staff peak
export const PEAK_STAFF_HOURS = [14, 15, 16, 17, 18]; // range(14, 19)
export const BALK_SLOPE = 0.08;                       // "wait" model, 8%/min
export const BALK_LENGTH_HAZARD = 0.1540;             // BOBA #52 "length" model
export const BATCH_CLEARANCE_WINDOW = 6;
export const BATCH_SERVINGS = 40;
export const BATCH_LIFE_TICKS = 24;
export const PEARL_RESTOCK_TRIGGER = 15;

export const HOURLY_RATE = {
  10: 14.0, 11: 24.0, 12: 48.0, 13: 48.0, 14: 29.0, 15: 43.0,
  16: 48.0, 17: 43.0, 18: 31.0, 19: 22.0, 20: 16.0, 21: 11.0,
};
export const HOURLY_WTP_MULT = {
  10: 0.92, 11: 1.00, 12: 1.06, 13: 1.06, 14: 0.96, 15: 1.04,
  16: 1.04, 17: 1.04, 18: 1.00, 19: 0.95, 20: 0.90, 21: 0.85,
};
export const FLEX_DEFER = { 0: 0.0, 3: 0.30, 6: 0.50 };
export const RIGID_DEFER = { 0: 0.0, 3: 1.60, 6: 3.20 };
export const HOURS = Object.keys(HOURLY_RATE).map(Number).sort((a, b) => a - b);

const SQRT2 = Math.sqrt(2);
const round2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;

// ── erfc: double precision (matches Python math.erfc) ──────────────────────
// erfc(x) = Q(1/2, x^2) (regularized upper incomplete gamma), computed with
// the NR gser series (small x^2) / gcf modified-Lentz continued fraction
// (large x^2). Relative error ~1e-15 — verified against math.erfc on a grid
// in bobaworld_verify.test.mjs.
const LN_GAMMA_HALF = 0.5723649429247001; // ln Γ(1/2) = ln √π

function gserP(x) { // P(1/2, x) by series, for x < 1.5
  const a = 0.5;
  let ap = a, sum = 1.0 / a, del = sum;
  for (let n = 0; n < 300; n++) {
    ap += 1.0;
    del *= x / ap;
    sum += del;
    if (Math.abs(del) < Math.abs(sum) * 1e-17) break;
  }
  return sum * Math.exp(-x + a * Math.log(x) - LN_GAMMA_HALF);
}
function gcfQ(x) { // Q(1/2, x) by modified-Lentz CF, for x >= 1.5
  const a = 0.5, FPMIN = 1e-300, EPS = 1e-17;
  let b = x + 1.0 - a, c = 1.0 / FPMIN, d = 1.0 / b, h = d;
  for (let i = 1; i <= 300; i++) {
    const an = -i * (i - a);
    b += 2.0;
    d = an * d + b;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = b + an / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1.0 / d;
    const delt = d * c;
    h *= delt;
    if (Math.abs(delt - 1.0) < EPS) break;
  }
  return Math.exp(-x + a * Math.log(x) - LN_GAMMA_HALF) * h;
}
export function erfc(x) {
  if (x === 0) return 1.0;
  if (x < 0) return 2.0 - erfc(-x);
  const z = x * x;
  if (z >= 745) return 0.0; // exp underflow; erfc(27+) is < 5e-320 anyway
  return z < 1.5 ? 1.0 - gserP(z) : gcfQ(z);
}

// lognormal survival (world._sf): P(X > x), X ~ lognormal(log scale, sigma)
export function sf(x, scale, sigma) {
  if (x <= 0) return 1.0;
  return 0.5 * erfc(Math.log(x / scale) / (sigma * SQRT2));
}

// ── clock & capacity (world.py) ─────────────────────────────────────────────
export const hourOf = (tick) => OPEN_HOUR + Math.floor((tick * 10) / 60);
export const serviceRateAt = (tick) =>
  PEAK_STAFF_HOURS.indexOf(hourOf(tick)) >= 0 ? CAPACITY_PER_MIN : CAPACITY_PER_MIN / 2.0;

// ── appeal inversion (the STRONG static baseline, world.appeal_for_list) ────
// golden-section maximizer of profit(p) over [a,b] — 90 iterations shrinks the
// bracket below double precision, so this argmax is machine-exact.
function argmax(f, a, b, iters) {
  const gr = (Math.sqrt(5) - 1) / 2;
  let c = b - gr * (b - a), d = a + gr * (b - a), fc = f(c), fd = f(d);
  for (let i = 0; i < (iters || 80); i++) {
    if (fc > fd) { b = d; d = c; fd = fc; c = b - gr * (b - a); fc = f(c); }
    else { a = c; c = d; fc = fd; d = a + gr * (b - a); fd = f(d); }
  }
  return (a + b) / 2;
}
const HW = (() => {
  const total = HOURS.reduce((s, h) => s + HOURLY_RATE[h], 0);
  return HOURS.map((h) => ({ w: HOURLY_RATE[h] / total, m: HOURLY_WTP_MULT[h] }));
})();
export const mixturePstar = (appeal, cost, sigma) =>
  argmax((p) => (p - cost) * HW.reduce((s, x) => s + x.w * sf(p, appeal * x.m, sigma), 0), cost + 0.01, 4.0 * appeal + cost, 90);
export const pstarSingle = (appeal, cost, sigma) =>
  argmax((p) => (p - cost) * sf(p, appeal, sigma), cost + 0.01, 4.0 * appeal + cost, 90);
export function appealForList(listPrice, cost, sigma, hourMults) {
  let lo = 0.2 * listPrice, hi = 4.0 * listPrice;
  for (let i = 0; i < 28; i++) {
    const mid = (lo + hi) / 2;
    const p = hourMults ? mixturePstar(mid, cost, sigma) : pstarSingle(mid, cost, sigma);
    if (p < listPrice) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// ── the world builder ───────────────────────────────────────────────────────
// menu: { drinks: [{name, price, cost, popularity?, appeal?}],
//         tops:   [{name, price, cost, like_prob?, appeal?}], batchTop }
// An explicit `appeal` skips the inversion (used by the Python cross-check to
// inject boba/world.py's exact appeals, and available to calibrated menus).
export function makeWorld(menu) {
  const drinks = menu.drinks.map((d) => d.name);
  const tops = menu.tops.map((t) => t.name);
  const DRINK_PRICE = {}, DRINK_COST = {}, DRINK_APPEAL = {}, POPULARITY = {};
  const TOP_PRICE = {}, TOP_COST = {}, TOP_APPEAL = {}, TOP_LIKE_PROB = {};
  let popSum = 0;
  menu.drinks.forEach((d) => { popSum += d.popularity != null ? d.popularity : 1; });
  menu.drinks.forEach((d) => {
    DRINK_PRICE[d.name] = d.price; DRINK_COST[d.name] = d.cost;
    DRINK_APPEAL[d.name] = d.appeal != null ? d.appeal : appealForList(d.price, d.cost, WTP_SIGMA, true);
    POPULARITY[d.name] = (d.popularity != null ? d.popularity : 1) / popSum;
  });
  menu.tops.forEach((t) => {
    TOP_PRICE[t.name] = t.price; TOP_COST[t.name] = t.cost;
    TOP_APPEAL[t.name] = t.appeal != null ? t.appeal : appealForList(t.price, t.cost, TOP_SIGMA, false);
    TOP_LIKE_PROB[t.name] = t.like_prob != null ? t.like_prob : 0.5;
  });
  const batchTop = menu.batchTop;
  const PEARL_COST = TOP_COST[batchTop];
  const MEAN_DRINK_MARGIN = drinks.reduce((s, d) => s + (DRINK_PRICE[d] - DRINK_COST[d]), 0) / drinks.length;

  const ecpaCache = {};
  function expectedCupsPerArrival(hour) {
    if (ecpaCache[hour] != null) return ecpaCache[hour];
    const m = HOURLY_WTP_MULT[hour];
    let total = 0;
    for (const d of drinks) {
      const scale = DRINK_APPEAL[d] * m;
      for (const wd of [{ w: 1 - GROUP_SHARE, decay: SOLO_DECAY }, { w: GROUP_SHARE, decay: GROUP_DECAY }]) {
        let s = 0;
        for (let i = 0; i < QTY_CAP; i++) s += sf(DRINK_PRICE[d] / Math.pow(wd.decay, i), scale, WTP_SIGMA);
        total += POPULARITY[d] * wd.w * s;
      }
    }
    return (ecpaCache[hour] = total);
  }
  const PEAK_HOURS = HOURS.filter((h) =>
    HOURLY_RATE[h] * expectedCupsPerArrival(h)
    >= 0.5 * 60.0 * (PEAK_STAFF_HOURS.indexOf(h) >= 0 ? CAPACITY_PER_MIN : CAPACITY_PER_MIN / 2));
  const PEARL_ATTACH_LIST = TOP_LIKE_PROB[batchTop] * sf(TOP_PRICE[batchTop], TOP_APPEAL[batchTop], TOP_SIGMA);

  // ── the canonical bundle chooser (for the disagreement point & outside opt) ─
  function bestMenuOrder(c, drinkPrices, topPrices, pearlsOk) {
    let best = { drink: null, qty: 0, tops: [], surplus: 0.0 };
    const avail = tops.filter((t) => pearlsOk || t !== batchTop);
    for (let q = 1; q <= QTY_CAP; q++) {
      const lad = qtyLadder(c.qty_decay, q);
      const chosen = avail.filter((t) => c.top_wtp[t] * lad > q * topPrices[t]);
      let topVal = 0, topPrice = 0;
      for (const t of chosen) { topVal += c.top_wtp[t]; topPrice += topPrices[t]; }
      for (const d of drinks) {
        const s = (c.wtp[d] + topVal) * lad - q * (drinkPrices[d] + topPrice);
        if (s > best.surplus) best = { drink: d, qty: q, tops: chosen.slice(), surplus: s };
      }
    }
    return best;
  }
  function outside_surplus(c) {
    if (c._sOut !== undefined) return c._sOut;
    const dp = {}, tp = {};
    for (const d of drinks) dp[d] = DRINK_PRICE[d] * OUTSIDE_MARKUP;
    for (const t of tops) tp[t] = TOP_PRICE[t] * OUTSIDE_MARKUP;
    return (c._sOut = Math.max(0.0, bestMenuOrder(c, dp, tp, true).surplus));
  }

  // ── live-state helpers on the boba shop state ─────────────────────────────
  function slot_capacity(s, slotTick) {
    const h = hourOf(Math.min(slotTick, TICKS_PER_DAY - 1));
    const expWalkins = HOURLY_RATE[h] / 6.0 * expectedCupsPerArrival(h);
    return serviceRateAt(slotTick) * 10.0 - expWalkins - (s.scheduled[slotTick] || 0);
  }
  function capacity_relief(s, qty, slotTicks) {
    if (slotTicks <= 0 || PEAK_HOURS.indexOf(hourOf(s.tick)) < 0) return 0.0;
    const slotHour = hourOf(Math.min(s.tick + slotTicks, TICKS_PER_DAY - 1));
    const bNow = balkProb(s);
    const bSlot = PEAK_HOURS.indexOf(slotHour) >= 0 ? bNow : 0.0;
    return qty * MEAN_DRINK_MARGIN * (bNow - bSlot);
  }
  function pearls_expiring_excess(s) {
    const live = s.batches.filter((b) => b.servings > 0);
    if (!live.length) return false;
    let first = live[0];
    for (const b of live) if (b.expires < first.expires) first = b;
    const ticksLeft = first.expires - s.tick;
    if (ticksLeft > BATCH_CLEARANCE_WINDOW || ticksLeft <= 0) return false;
    let expPearls = 0;
    for (let t = s.tick; t < Math.min(first.expires, TICKS_PER_DAY); t++)
      expPearls += HOURLY_RATE[hourOf(t)] / 6.0 * expectedCupsPerArrival(hourOf(t)) * PEARL_ATTACH_LIST;
    return first.servings > expPearls;
  }
  // policies.top_c_eff: pearls from a batch about to be waste are free to move
  function top_c_eff(s, top) {
    if (top === batchTop && pearls_expiring_excess(s)) return 0.0;
    return TOP_COST[top];
  }

  return {
    // constants the adapter/UI read
    DRINK_PRICE, DRINK_COST, TOP_PRICE, TOP_COST, QTY_CAP, TICKS_PER_DAY, batchTop,
    POPULARITY, TOP_LIKE_PROB, PEARL_COST, MEAN_DRINK_MARGIN, PEARL_ATTACH_LIST,
    // demand-model handles (for the shopper WTP + disagreement)
    DRINK_APPEAL, TOP_APPEAL, HOURLY_WTP_MULT, FLEX_DEFER, RIGID_DEFER, GROUP_DECAY, SOLO_DECAY,
    hourOf, serviceRateAt, bestMenuOrder, qtyLadder, expectedCupsPerArrival,
    // live-state helpers the adapter calls
    capacity_relief, slot_capacity, outside_surplus, balk_prob: balkProb,
    pearls_expiring_excess, top_c_eff,
    // introspection
    PEAK_HOURS, drinks, tops,
  };
}

export const qtyLadder = (decay, qty) => { let s = 0; for (let i = 0; i < qty; i++) s += Math.pow(decay, i); return s; };

// Defer disutility for a +30/+60-minute pickup slot. rigidMult (>=1) scales a
// RIGID buyer's cost — the sandbox's flexibility slider; 1 = the calibrated model.
export function deferCost(c, slotTicks, rigidMult) {
  if (c.flexible) return FLEX_DEFER[slotTicks];
  return RIGID_DEFER[slotTicks] * (rigidMult != null ? rigidMult : 1);
}

// ── shop states ─────────────────────────────────────────────────────────────
// A boba shop state, matching the shape boba/world.py exposes (the adapter
// reads .tick / .pearl_stock(); the world helpers read .queue/.scheduled/
// .batches; balkProb reads .balk_model, default "wait").

// Single-moment state from a scenario (the consumer hook's shop moment).
export function makeBobaState(scn) {
  return {
    day: 0, tick: scn.tick, carry: 0.0, scheduled: {},
    queue: scn.queue > 0 ? [scn.queue] : [],
    batches: [{ servings: scn.batchServings, expires: scn.tick + scn.batchExpiresIn }],
    pearl_stock() { return this.batches.reduce((a, b) => a + b.servings, 0); },
  };
}

// Full-day state (world.open_shop): the operator cooks batch 1 at 10:00 sharp.
export function openShop(day, balkModel) {
  const state = {
    day: day || 0, tick: 0, queue: [], carry: 0.0, batches: [], scheduled: {},
    batchesCooked: 0, balk_model: balkModel || "wait", lastSaleTick: null,
    pearl_stock() { return this.batches.reduce((a, b) => a + b.servings, 0); },
  };
  cookBatch(state);
  return state;
}

export const queueDrinks = (s) => s.queue.reduce((a, b) => a + b, 0);
export const pearlStock = (s) => s.batches.reduce((a, b) => a + b.servings, 0);
export function cookBatch(s) {
  s.batches.push({ servings: BATCH_SERVINGS, expires: s.tick + BATCH_LIFE_TICKS });
  s.batchesCooked++;
}
export function maybeCook(s) {
  if (pearlStock(s) >= PEARL_RESTOCK_TRIGGER) return;
  // Demand-aware dead-shop guard (sandbox divergence from Python's
  // unconditional maybe_cook, see the module header): restock only if a cup
  // has sold within the last batch-life window, so a zero-sales menu doesn't
  // waste batch after batch. On a live menu a cup sells every few ticks — no-op.
  if (s.lastSaleTick == null || s.tick - s.lastSaleTick > BATCH_LIFE_TICKS) return;
  cookBatch(s);
}
export function expireBatches(world, s) {
  let waste = 0; const keep = [];
  for (const b of s.batches) {
    if (b.expires <= s.tick && b.servings > 0) waste += b.servings * world.PEARL_COST;
    else if (b.servings > 0) keep.push(b);
  }
  s.batches = keep; return waste;
}
export function closeOut(world, s) {
  const w = pearlStock(s) * world.PEARL_COST;
  s.batches = []; return w;
}
export function takePearls(s, n) {
  if (pearlStock(s) < n) throw new Error("insufficient pearl stock");
  const order = s.batches.slice().sort((a, b) => a.expires - b.expires);
  for (const b of order) { const got = Math.min(b.servings, n); b.servings -= got; n -= got; if (n === 0) return; }
}
export function releaseScheduled(s) {
  const drinks = s.scheduled[s.tick] || 0;
  if (drinks > 0) { s.queue.push(drinks); delete s.scheduled[s.tick]; }
}
export function serveQueue(s) {
  let cap = serviceRateAt(s.tick) * 10.0 + s.carry;
  let made = 0;
  while (s.queue.length && made + 1 <= cap) {
    const head = s.queue[0];
    const take = Math.min(head, Math.floor(cap - made));
    if (take <= 0) break;
    made += take;
    if (take === head) s.queue.shift(); else s.queue[0] = head - take;
  }
  s.carry = s.queue.length ? (cap - made) : 0.0;
  return made;
}
export const expectedWaitMinutes = (s) => queueDrinks(s) / serviceRateAt(s.tick);
export function balkProb(s) {
  if ((s.balk_model || "wait") === "length")
    return 1.0 - Math.exp(-BALK_LENGTH_HAZARD * s.queue.length);
  return Math.min(1.0, BALK_SLOPE * expectedWaitMinutes(s));
}

// ── consumer draws (run_day arrivals; JS PRNG — distributions, not streams) ──
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function normal(rng) { // Box-Muller, consumes 2 uniforms (no caching)
  let u = 0, v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
export const lognormal = (rng, mu, sigma) => Math.exp(mu + sigma * normal(rng));
export function poisson(rng, lambda) { // Knuth (lambda small here, <= 8)
  const L = Math.exp(-lambda);
  let k = 0, p = 1;
  do { k++; p *= rng(); } while (p > L);
  return k - 1;
}
export function hashSeed() { // stable 32-bit hash of (seed, day, ...) → PRNG seed
  let h = 2166136261 >>> 0;
  for (let i = 0; i < arguments.length; i++) {
    let x = (arguments[i] | 0) >>> 0;
    for (let b = 0; b < 4; b++) { h ^= (x & 0xff); h = Math.imul(h, 16777619) >>> 0; x >>>= 8; }
  }
  return h >>> 0;
}

// One paired day of customers: arrivals + consumer draws + balk rolls, all
// policy-independent (the twin-worlds lanes replay the SAME people).
export function generateDay(world, cfg, seed, day) {
  const rng = mulberry32(hashSeed(seed, day));
  const flexShare = cfg && cfg.flexibleShare != null ? cfg.flexibleShare : 0.30;
  const trafficMult = cfg && cfg.trafficMult != null ? cfg.trafficMult : 1.0;
  const ticks = [];
  for (let tick = 0; tick < TICKS_PER_DAY; tick++) {
    const hour = hourOf(tick);
    const mult = HOURLY_WTP_MULT[hour];
    const n = poisson(rng, HOURLY_RATE[hour] / 6.0 * trafficMult);
    const arrivals = [];
    for (let k = 0; k < n; k++) {
      const roll = rng(); // favorite ~ POPULARITY (categorical)
      let acc = 0, fav = world.drinks[0];
      for (const d of world.drinks) { acc += world.POPULARITY[d]; if (roll < acc) { fav = d; break; } }
      const eps = lognormal(rng, 0.0, WTP_SIGMA);
      const wtp = {};
      for (const d of world.drinks) wtp[d] = world.DRINK_APPEAL[d] * mult * eps * (d === fav ? 1.0 : CROSS_DISCOUNT);
      const top_wtp = {};
      for (const t of world.tops) {
        const like = rng() < world.TOP_LIKE_PROB[t]; // both draws always taken,
        const draw = lognormal(rng, 0.0, TOP_SIGMA); // so the stream is stable
        top_wtp[t] = like ? world.TOP_APPEAL[t] * draw : 0.0;
      }
      const flexible = rng() < flexShare;
      const qty_decay = rng() < GROUP_SHARE ? GROUP_DECAY : SOLO_DECAY;
      const balkRoll = rng();
      arrivals.push({ consumer: { fav, wtp, top_wtp, flexible, qty_decay }, balkRoll });
    }
    ticks.push(arrivals);
  }
  return ticks;
}

// ── accounting (run._settle) ────────────────────────────────────────────────
export function newMetrics() {
  return { revenue: 0, ingredient_cost: 0, waste_cost: 0, cups: 0, toppings: 0,
    deals: 0, arrivals: 0, balks: 0, lost: 0, deferred: 0, negotiated: 0,
    consumer_surplus: 0, batches_cooked: 0 };
}
export function settle(world, s, m, drink, qty, tops, price, surplus, slotTicks) {
  s.lastSaleTick = s.tick; // demand signal for maybeCook (dead-shop guard)
  m.revenue += price;
  let ic = qty * world.DRINK_COST[drink];
  for (const t of tops) ic += qty * world.TOP_COST[t];
  m.ingredient_cost += ic;
  m.cups += qty;
  m.toppings += qty * tops.length;
  m.deals += 1;
  m.consumer_surplus += surplus;
  if (tops.indexOf(world.batchTop) >= 0) takePearls(s, qty);
  if (slotTicks > 0) {
    const due = Math.min(s.tick + slotTicks, TICKS_PER_DAY - 1);
    s.scheduled[due] = (s.scheduled[due] || 0) + qty;
    m.deferred += 1;
  } else s.queue.push(qty);
}
export function finalize(m) {
  m.margin = round2(m.revenue - m.ingredient_cost - m.waste_cost);
  m.revenue = round2(m.revenue); m.ingredient_cost = round2(m.ingredient_cost);
  m.waste_cost = round2(m.waste_cost); m.consumer_surplus = round2(m.consumer_surplus);
  m.attach_rate = m.cups ? round2(m.toppings / m.cups) : 0;
}

// ── one customer, STATIC lane (run_day walk-in path) ────────────────────────
export function serveStatic(world, s, m, c, balkRoll) {
  const b = balkProb(s);
  if (balkRoll < b) { m.balks += 1; return { kind: "balk" }; }
  const order = world.bestMenuOrder(c, world.DRINK_PRICE, world.TOP_PRICE, pearlStock(s) >= QTY_CAP);
  const sOut = world.outside_surplus(c);
  if (order.drink !== null && order.surplus > 0 && order.surplus >= sOut) {
    let price = order.qty * world.DRINK_PRICE[order.drink];
    for (const t of order.tops) price += order.qty * world.TOP_PRICE[t];
    price = round2(price);
    settle(world, s, m, order.drink, order.qty, order.tops, price, order.surplus, 0);
    return { kind: "buy", drink: order.drink, qty: order.qty, tops: order.tops, price, menu: price, surplus: order.surplus };
  }
  m.lost += 1;
  return { kind: "lost" };
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_boba_world = {
    makeWorld, makeBobaState, openShop, generateDay, serveStatic, settle,
    finalize, newMetrics, deferCost, balkProb, erfc, sf, appealForList,
    hourOf, serviceRateAt, qtyLadder,
    expireBatches, maybeCook, releaseScheduled, serveQueue, closeOut,
    takePearls, queueDrinks, pearlStock, expectedWaitMinutes,
    mulberry32, hashSeed, normal, lognormal, poisson,
  };
}

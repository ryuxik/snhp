/* boba-engine.js — a FAITHFUL client-side port of the real SNHP boba engine.
 *
 * This is a line-for-line port of the Python source in the repo:
 *   boba/world.py     — the consumer model, FIFO queue, service capacity,
 *                       balk hazard, tapioca batches, appeal inversion, the
 *                       canonical bundle chooser (best_menu_order/bundle_value).
 *   boba/policies.py  — cart_nash: the SNHP quote (Nash split over a consistent
 *                       disagreement point), run here in the v1-SAFE config.
 *   boba/run.py       — _settle / run_day accounting.
 *
 * NOTHING about the pricing mechanism is invented here. The ONLY things that
 * differ from Python are (a) the pseudo-random number generator (a JS PRNG,
 * not numpy PCG64 — we reproduce DISTRIBUTIONS, not byte-exact draws, which is
 * why the validation target is a Monte-Carlo band, not an equality) and (b)
 * scipy's Brent minimizer is replaced by golden-section search for the appeal
 * inversion (only used for CUSTOM menus; the default menu passes the exact
 * appeals extracted from Python).
 *
 * Works in both node (validation) and the browser (the owner sandbox).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BobaEngine = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ── global calibration constants (boba/world.py) ────────────────────────
  const WTP_SIGMA = 0.45;
  const TOP_SIGMA = 0.70;
  const CROSS_DISCOUNT = 0.55;
  const GROUP_SHARE = 0.30;
  const GROUP_DECAY = 0.60;
  const SOLO_DECAY = 0.15;
  const QTY_CAP = 3;
  const OUTSIDE_MARKUP = 1.10;
  const TICKS_PER_DAY = 72;
  const OPEN_HOUR = 10;
  const CAPACITY_PER_MIN = 1.5;                 // 2 staff peak (BOBA_CAPACITY_PER_MIN)
  const PEAK_STAFF_HOURS = [14, 15, 16, 17, 18]; // range(14,19)
  const BALK_SLOPE = 0.08;                       // P0 "wait" model, 8%/min
  const BALK_LENGTH_HAZARD = 0.1540;             // BOBA #52 "length" model
  const PRICE_RUNGS = 8;
  const BATCH_CLEARANCE_WINDOW = 6;
  const BATCH_SERVINGS = 40;
  const BATCH_LIFE_TICKS = 24;
  const PEARL_RESTOCK_TRIGGER = 15;

  const HOURLY_RATE = {
    10: 14.0, 11: 24.0, 12: 48.0, 13: 48.0, 14: 29.0, 15: 43.0,
    16: 48.0, 17: 43.0, 18: 31.0, 19: 22.0, 20: 16.0, 21: 11.0,
  };
  const HOURLY_WTP_MULT = {
    10: 0.92, 11: 1.00, 12: 1.06, 13: 1.06, 14: 0.96, 15: 1.04,
    16: 1.04, 17: 1.04, 18: 1.00, 19: 0.95, 20: 0.90, 21: 0.85,
  };
  const FLEX_DEFER = { 0: 0.0, 3: 0.30, 6: 0.50 };
  const RIGID_DEFER = { 0: 0.0, 3: 1.60, 6: 3.20 };
  const HOURS = Object.keys(HOURLY_RATE).map(Number).sort((a, b) => a - b);

  // ── the DEFAULT calibration menu (from block/calibration.py, appeals
  //    extracted from the real Python engine so the default is EXACT) ──────
  const DEFAULT_SPEC = {
    drinks: [
      { name: "classic-milk-tea", price: 6.25, cost: 1.35, appeal: 7.3126, popularity: 0.30 },
      { name: "fruit-tea",        price: 6.75, cost: 1.50, appeal: 7.8676, popularity: 0.26 },
      { name: "brown-sugar",      price: 7.25, cost: 1.60, appeal: 8.4583, popularity: 0.24 },
      { name: "matcha-latte",     price: 7.50, cost: 1.75, appeal: 8.6814, popularity: 0.20 },
    ],
    tops: [
      { name: "pearls",      price: 0.85, cost: 0.10, appeal: 0.8543, like_prob: 0.65 },
      { name: "pudding",     price: 0.95, cost: 0.15, appeal: 0.9161, like_prob: 0.35 },
      { name: "grass-jelly", price: 0.85, cost: 0.12, appeal: 0.8342, like_prob: 0.30 },
      { name: "cheese-foam", price: 1.25, cost: 0.25, appeal: 1.1503, like_prob: 0.40 },
    ],
    batchTop: "pearls",
  };

  // ── math helpers ────────────────────────────────────────────────────────
  const SQRT2 = Math.sqrt(2);
  const round2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;

  // complementary error function — Numerical Recipes erfcc, |err| < 1.2e-7
  function erfc(x) {
    const z = Math.abs(x);
    const t = 1 / (1 + z / 2);
    const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 +
      t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 +
      t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
    return x >= 0 ? r : 2 - r;
  }

  // lognormal survival (world._sf): P(X > x), X ~ lognormal(log scale, sigma)
  function sf(x, scale, sigma) {
    if (x <= 0) return 1.0;
    return 0.5 * erfc(Math.log(x / scale) / (sigma * SQRT2));
  }

  // ── PRNG (mulberry32) + samplers ────────────────────────────────────────
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normal(rng) { // Box-Muller, consumes 2 uniforms (no caching)
    let u = 0, v = 0;
    while (u === 0) u = rng();
    while (v === 0) v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  const lognormal = (rng, mu, sigma) => Math.exp(mu + sigma * normal(rng));
  function poisson(rng, lambda) { // Knuth (lambda is small here, <= 8)
    const L = Math.exp(-lambda);
    let k = 0, p = 1;
    do { k++; p *= rng(); } while (p > L);
    return k - 1;
  }
  // stable 32-bit hash of (seed, day) → PRNG seed
  function hashSeed() {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < arguments.length; i++) {
      let x = (arguments[i] | 0) >>> 0;
      for (let b = 0; b < 4; b++) { h ^= (x & 0xff); h = Math.imul(h, 16777619) >>> 0; x >>>= 8; }
    }
    return h >>> 0;
  }

  // ── clock & capacity (world.py) ─────────────────────────────────────────
  const hourOf = (tick) => OPEN_HOUR + Math.floor((tick * 10) / 60);
  const serviceRateAt = (tick) =>
    PEAK_STAFF_HOURS.indexOf(hourOf(tick)) >= 0 ? CAPACITY_PER_MIN : CAPACITY_PER_MIN / 2.0;

  // ── appeal inversion (the STRONG static baseline, world.appeal_for_list) ─
  // golden-section maximizer of profit(p) over [a,b]
  function argmax(f, a, b, iters) {
    const gr = (Math.sqrt(5) - 1) / 2;
    let c = b - gr * (b - a), d = a + gr * (b - a);
    let fc = f(c), fd = f(d);
    for (let i = 0; i < (iters || 80); i++) {
      if (fc > fd) { b = d; d = c; fd = fc; c = b - gr * (b - a); fc = f(c); }
      else { a = c; c = d; fc = fd; d = a + gr * (b - a); fd = f(d); }
    }
    return (a + b) / 2;
  }
  function hourWeights() {
    const total = HOURS.reduce((s, h) => s + HOURLY_RATE[h], 0);
    return HOURS.map((h) => ({ w: HOURLY_RATE[h] / total, m: HOURLY_WTP_MULT[h] }));
  }
  const _HW = hourWeights();
  function mixturePstar(appeal, cost, sigma) {
    const f = (p) => (p - cost) * _HW.reduce((s, x) => s + x.w * sf(p, appeal * x.m, sigma), 0);
    return argmax(f, cost + 0.01, 4.0 * appeal + cost, 90);
  }
  function pstarSingle(appeal, cost, sigma) {
    const f = (p) => (p - cost) * sf(p, appeal, sigma);
    return argmax(f, cost + 0.01, 4.0 * appeal + cost, 90);
  }
  function appealForList(listPrice, cost, sigma, hourMults) {
    let lo = 0.2 * listPrice, hi = 4.0 * listPrice;
    for (let i = 0; i < 28; i++) {
      const mid = (lo + hi) / 2;
      const p = hourMults ? mixturePstar(mid, cost, sigma) : pstarSingle(mid, cost, sigma);
      if (p < listPrice) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }

  // ── compile a menu spec into a ready-to-run context ─────────────────────
  function compile(spec) {
    const drinks = spec.drinks.map((d) => d.name);
    const tops = spec.tops.map((t) => t.name);
    const DRINK_PRICE = {}, DRINK_COST = {}, DRINK_APPEAL = {}, POPULARITY = {};
    const TOP_PRICE = {}, TOP_COST = {}, TOP_APPEAL = {}, TOP_LIKE_PROB = {};
    let popSum = 0;
    spec.drinks.forEach((d) => { popSum += (d.popularity != null ? d.popularity : 1); });
    spec.drinks.forEach((d) => {
      DRINK_PRICE[d.name] = d.price; DRINK_COST[d.name] = d.cost;
      DRINK_APPEAL[d.name] = d.appeal != null ? d.appeal
        : appealForList(d.price, d.cost, WTP_SIGMA, true);
      POPULARITY[d.name] = (d.popularity != null ? d.popularity : 1) / popSum;
    });
    spec.tops.forEach((t) => {
      TOP_PRICE[t.name] = t.price; TOP_COST[t.name] = t.cost;
      TOP_APPEAL[t.name] = t.appeal != null ? t.appeal
        : appealForList(t.price, t.cost, TOP_SIGMA, false);
      TOP_LIKE_PROB[t.name] = t.like_prob != null ? t.like_prob : 0.5;
    });
    const batchTop = spec.batchTop && tops.indexOf(spec.batchTop) >= 0 ? spec.batchTop
      : (tops.length ? tops[0] : null);
    const PEARL_COST = batchTop ? TOP_COST[batchTop] : 0;
    const MEAN_DRINK_MARGIN = drinks.reduce((s, d) => s + (DRINK_PRICE[d] - DRINK_COST[d]), 0) / drinks.length;

    const ctx = {
      spec, drinks, tops, batchTop,
      DRINK_PRICE, DRINK_COST, DRINK_APPEAL, POPULARITY,
      TOP_PRICE, TOP_COST, TOP_APPEAL, TOP_LIKE_PROB,
      PEARL_COST, MEAN_DRINK_MARGIN,
      _ecpaCache: {},
    };

    // world.expected_cups_per_arrival(hour) — forecast used by slot_capacity,
    // capacity_relief and the pearls-clearance trigger.
    ctx.expectedCupsPerArrival = function (hour) {
      if (ctx._ecpaCache[hour] != null) return ctx._ecpaCache[hour];
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
      ctx._ecpaCache[hour] = total;
      return total;
    };

    // world.PEAK_HOURS — hours where expected demand >= 50% of bar capacity.
    ctx.PEAK_HOURS = HOURS.filter((h) =>
      HOURLY_RATE[h] * ctx.expectedCupsPerArrival(h)
      >= 0.5 * 60.0 * (PEAK_STAFF_HOURS.indexOf(h) >= 0 ? CAPACITY_PER_MIN : CAPACITY_PER_MIN / 2));

    // policies.PEARL_ATTACH_LIST
    ctx.PEARL_ATTACH_LIST = batchTop
      ? TOP_LIKE_PROB[batchTop] * sf(TOP_PRICE[batchTop], TOP_APPEAL[batchTop], TOP_SIGMA) : 0;

    return ctx;
  }

  // ── the canonical bundle chooser (world.py) ─────────────────────────────
  const qtyLadder = (decay, qty) => {
    let s = 0; for (let i = 0; i < qty; i++) s += Math.pow(decay, i); return s;
  };
  function bundleValue(ctx, c, drink, qty, tops) {
    let perCup = c.wtp[drink];
    for (const t of tops) perCup += c.top_wtp[t];
    return perCup * qtyLadder(c.qty_decay, qty);
  }
  function bestMenuOrder(ctx, c, drinkPrices, topPrices, pearlsOk) {
    let best = { drink: null, qty: 0, tops: [], surplus: 0.0 };
    const avail = ctx.tops.filter((t) => pearlsOk || t !== ctx.batchTop);
    for (let q = 1; q <= QTY_CAP; q++) {
      const lad = qtyLadder(c.qty_decay, q);
      const chosen = avail.filter((t) => c.top_wtp[t] * lad > q * topPrices[t]);
      let topVal = 0, topPrice = 0;
      for (const t of chosen) { topVal += c.top_wtp[t]; topPrice += topPrices[t]; }
      for (const d of ctx.drinks) {
        const s = (c.wtp[d] + topVal) * lad - q * (drinkPrices[d] + topPrice);
        if (s > best.surplus) best = { drink: d, qty: q, tops: chosen.slice(), surplus: s };
      }
    }
    return best;
  }
  function outsideSurplus(ctx, c) {
    // memo per consumer: sOut depends only on (consumer, menu) — not on shop
    // state — and the same consumer is priced ~2-3x/day across the two lanes.
    if (c._sOut !== undefined) return c._sOut;
    const dp = {}, tp = {};
    for (const d of ctx.drinks) dp[d] = ctx.DRINK_PRICE[d] * OUTSIDE_MARKUP;
    for (const t of ctx.tops) tp[t] = ctx.TOP_PRICE[t] * OUTSIDE_MARKUP;
    return (c._sOut = Math.max(0.0, bestMenuOrder(ctx, c, dp, tp, true).surplus));
  }

  // ── shop state: FIFO queue + tapioca batches (world.py) ─────────────────
  function openShop(day, balkModel) {
    const state = { day: day, tick: 0, queue: [], carry: 0.0, batches: [],
      scheduled: {}, batchesCooked: 0, balkModel: balkModel || "wait", lastSaleTick: null };
    cookBatch(state);
    return state;
  }
  const queueDrinks = (s) => s.queue.reduce((a, b) => a + b, 0);
  const pearlStock = (s) => s.batches.reduce((a, b) => a + b.servings, 0);
  function cookBatch(s) { s.batches.push({ servings: BATCH_SERVINGS, expires: s.tick + BATCH_LIFE_TICKS }); s.batchesCooked++; }
  function maybeCook(s) {
    if (pearlStock(s) >= PEARL_RESTOCK_TRIGGER) return;
    // Demand-aware: a real operator does not keep cooking tapioca for a dead
    // shop. Restock only if a cup has sold within the last batch-life window
    // (fix for the thin-margin artifact where a zero-sales day still wasted
    // batch after batch). On a busy menu a cup sells every few ticks, so this
    // is a no-op — the calibration reference is unchanged.
    if (s.lastSaleTick == null || s.tick - s.lastSaleTick > BATCH_LIFE_TICKS) return;
    cookBatch(s);
  }
  function expireBatches(ctx, s) {
    let waste = 0; const keep = [];
    for (const b of s.batches) {
      if (b.expires <= s.tick && b.servings > 0) waste += b.servings * ctx.PEARL_COST;
      else if (b.servings > 0) keep.push(b);
    }
    s.batches = keep; return waste;
  }
  function closeOut(ctx, s) { const w = pearlStock(s) * ctx.PEARL_COST; s.batches = []; return w; }
  function takePearls(s, n) {
    if (pearlStock(s) < n) throw new Error("insufficient pearl stock");
    const order = s.batches.slice().sort((a, b) => a.expires - b.expires);
    for (const b of order) { const got = Math.min(b.servings, n); b.servings -= got; n -= got; if (n === 0) return; }
  }
  function releaseScheduled(s) {
    const drinks = s.scheduled[s.tick] || 0;
    if (drinks > 0) { s.queue.push(drinks); delete s.scheduled[s.tick]; }
  }
  function serveQueue(s) {
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
  const expectedWaitMinutes = (s) => queueDrinks(s) / serviceRateAt(s.tick);
  const observedQueueLength = (s) => s.queue.length;
  function balkProb(s) {
    if (s.balkModel === "length") return 1.0 - Math.exp(-BALK_LENGTH_HAZARD * observedQueueLength(s));
    return Math.min(1.0, BALK_SLOPE * expectedWaitMinutes(s));
  }
  function slotCapacity(ctx, s, slotTick) {
    const h = hourOf(Math.min(slotTick, TICKS_PER_DAY - 1));
    const expWalkins = HOURLY_RATE[h] / 6.0 * ctx.expectedCupsPerArrival(h);
    return serviceRateAt(slotTick) * 10.0 - expWalkins - (s.scheduled[slotTick] || 0);
  }
  function capacityRelief(ctx, s, qty, slotTicks) {
    if (slotTicks <= 0 || ctx.PEAK_HOURS.indexOf(hourOf(s.tick)) < 0) return 0.0;
    const slotHour = hourOf(Math.min(s.tick + slotTicks, TICKS_PER_DAY - 1));
    const bNow = balkProb(s);
    const bSlot = ctx.PEAK_HOURS.indexOf(slotHour) >= 0 ? bNow : 0.0;
    return qty * ctx.MEAN_DRINK_MARGIN * (bNow - bSlot);
  }

  // ── pearls-expiry salvage (policies.py) ─────────────────────────────────
  function pearlsExpiringExcess(ctx, s) {
    const live = s.batches.filter((b) => b.servings > 0);
    if (!live.length) return false;
    let first = live[0];
    for (const b of live) if (b.expires < first.expires) first = b;
    const ticksLeft = first.expires - s.tick;
    if (ticksLeft > BATCH_CLEARANCE_WINDOW || ticksLeft <= 0) return false;
    let expPearls = 0;
    for (let t = s.tick; t < Math.min(first.expires, TICKS_PER_DAY); t++)
      expPearls += HOURLY_RATE[hourOf(t)] / 6.0 * ctx.expectedCupsPerArrival(hourOf(t)) * ctx.PEARL_ATTACH_LIST;
    return first.servings > expPearls;
  }
  function topCEff(ctx, s, top, salvage) {
    if (salvage && top === ctx.batchTop && pearlsExpiringExcess(ctx, s)) return 0.0;
    return ctx.TOP_COST[top];
  }

  // A rigid buyer ("I'm on my lunch break") pays RIGID_DEFER for a later slot.
  // rigidMult (>=1) scales that cost: the sandbox drives it up as the flexible
  // share falls, so "0% flexible" means genuinely no one accepts a deferral
  // (the slider means what it says). Default 1 = the calibrated model (reference).
  function deferCost(c, slotTicks, rigidMult) {
    if (c.flexible) return FLEX_DEFER[slotTicks];
    return RIGID_DEFER[slotTicks] * (rigidMult != null ? rigidMult : 1);
  }

  // ── cart_nash: the SNHP quote (policies.cart_nash), v1-SAFE config ───────
  // quote_lookers=false (hard floor), qty_appetite=true, min_price_frac=0.6,
  // defer_slots=true, salvage=true, market_floor=false, honest disclosure.
  function cartNash(ctx, s, c, opts) {
    const o = opts || {};
    const quoteLookers = o.quoteLookers !== undefined ? o.quoteLookers : false;
    const qtyAppetite = o.qtyAppetite !== undefined ? o.qtyAppetite : true;
    const minPriceFrac = o.minPriceFrac !== undefined ? o.minPriceFrac : 0.6;
    const deferSlots = o.deferSlots !== undefined ? o.deferSlots : true;
    const salvage = o.salvage !== undefined ? o.salvage : true;
    const minGainAbs = o.minGainAbs !== undefined ? o.minGainAbs : 0.25;
    const minGainFrac = o.minGainFrac !== undefined ? o.minGainFrac : 0.10;
    const rigidMult = o.rigidDeferMult != null ? o.rigidDeferMult : 1;

    const b = balkProb(s);
    const pearlsStocked = pearlStock(s);
    const sOut = outsideSurplus(ctx, c);

    // the sticker counterfactual, via the same canonical chooser the walk-in uses
    const menu = bestMenuOrder(ctx, c, ctx.DRINK_PRICE, ctx.TOP_PRICE, pearlsStocked >= QTY_CAP);
    const ceff = {};
    for (const t of ctx.tops) ceff[t] = topCEff(ctx, s, t, salvage);

    let dB, dS;
    if (menu.drink !== null && menu.surplus > 0 && menu.surplus >= sOut) {
      let marginMenu = menu.qty * (ctx.DRINK_PRICE[menu.drink] - ctx.DRINK_COST[menu.drink]);
      for (const t of menu.tops) marginMenu += menu.qty * (ctx.TOP_PRICE[t] - ceff[t]);
      dB = (1.0 - b) * menu.surplus + b * sOut;
      dS = (1.0 - b) * marginMenu;
    } else {
      if (!quoteLookers) return null;   // v1-SAFE hard floor: never quote a non-buyer
      dB = sOut; dS = 0.0;
    }

    // toppings worth keeping: value above opportunity cost, nested prefixes
    const ranked = ctx.tops.filter((t) => c.top_wtp[t] > ceff[t])
      .sort((a, z) => (c.top_wtp[z] - ceff[z]) - (c.top_wtp[a] - ceff[a]));
    const subsets = [];
    for (let i = 0; i <= ranked.length; i++) subsets.push(ranked.slice(0, i));

    const slots = [0];
    if (deferSlots) for (const ss of [3, 6]) if (s.tick + ss < TICKS_PER_DAY) slots.push(ss);
    const slotRoom = {}, defer = {};
    for (const ss of slots) { slotRoom[ss] = ss > 0 ? slotCapacity(ctx, s, s.tick + ss) : QTY_CAP; defer[ss] = deferCost(c, ss, rigidMult); }
    const relief = {};
    for (let q = 1; q <= QTY_CAP; q++) for (const ss of slots) relief[q + "," + ss] = capacityRelief(ctx, s, q, ss);

    let best = null, bestScore = null;
    for (const d of ctx.drinks) {
      if (c.wtp[d] <= ctx.DRINK_COST[d]) continue;
      for (const T of subsets) {
        let tval = 0, tcost = 0, tlist = 0;
        for (const t of T) { tval += c.top_wtp[t]; tcost += ceff[t]; tlist += ctx.TOP_PRICE[t]; }
        let lad = 0;
        for (let q = 1; q <= QTY_CAP; q++) {
          if (T.indexOf(ctx.batchTop) >= 0 && pearlsStocked < q) break;
          if (qtyAppetite && q > 1 && c.wtp[d] * Math.pow(c.qty_decay, q - 1) < ctx.DRINK_COST[d]) break;
          lad += Math.pow(c.qty_decay, q - 1);
          const val = (c.wtp[d] + tval) * lad;
          const cost = q * (ctx.DRINK_COST[d] + tcost);
          const listv = q * (ctx.DRINK_PRICE[d] + tlist);
          const loP = Math.max(cost, minPriceFrac * listv);
          let rungs;
          if (loP >= listv) rungs = [round2(listv)];
          else { const step = (listv - loP) / (PRICE_RUNGS - 1); rungs = []; for (let i = 0; i < PRICE_RUNGS; i++) rungs.push(round2(loP + i * step)); }
          for (const ss of slots) {
            if (ss > 0 && slotRoom[ss] < q) continue;
            const r = relief[q + "," + ss];
            const dis = defer[ss];
            const surv = ss === 0 ? (1.0 - b) : 1.0;
            for (const p of rungs) {
              const gs = surv * (p - cost) + r - dS;
              const gb = surv * (val - p) + (1.0 - surv) * sOut - dis - dB;
              if (gs >= -1e-9 && gb >= -1e-9) {
                const score = [gs * gb, gs + gb];
                if (bestScore === null || score[0] > bestScore[0] ||
                    (score[0] === bestScore[0] && score[1] > bestScore[1])) {
                  best = { d, q, T, p, ss, r, val, cost, listv };
                  bestScore = score;
                }
              }
            }
          }
        }
      }
    }
    if (best === null || (bestScore[0] <= 0 && bestScore[1] <= 1e-9)) return null;

    const surv = best.ss === 0 ? (1.0 - b) : 1.0;
    const uS = surv * (best.p - best.cost) + best.r;
    if (uS - dS < Math.max(minGainAbs, minGainFrac * best.listv)) return null;
    const uB = surv * (best.val - best.p) + (1.0 - surv) * sOut - defer[best.ss];
    // structured steering flag: salvage TRULY triggered (a batch topping in the
    // cart whose opportunity cost is 0 because an over-stocked batch is expiring)
    // — NOT merely a zero-cost topping. Consumers of the deal branch on this
    // boolean, never on the prose in `why`.
    const salvageUsed = salvage && best.T.indexOf(ctx.batchTop) >= 0 && pearlsExpiringExcess(ctx, s);
    const why = ["negotiated cart"];
    if (best.ss > 0) why.push("+" + best.ss * 10 + "-min pickup frees peak capacity");
    if (salvageUsed) why.push("pearls from the expiring batch");
    if (best.p < best.listv - 1e-9) why.push("$" + (best.listv - best.p).toFixed(2) + " under the menu");
    else why.push("at menu");
    return { drink: best.d, qty: best.q, tops: best.T.slice(), price: best.p, slotTicks: best.ss,
      value: best.val, uShop: uS, dShop: dS, uBuyer: uB, dBuyer: dB, relief: best.r,
      salvage: salvageUsed, why };
  }

  // ── accounting (run._settle) ────────────────────────────────────────────
  function newMetrics() {
    return { revenue: 0, ingredient_cost: 0, waste_cost: 0, cups: 0, toppings: 0,
      deals: 0, arrivals: 0, balks: 0, lost: 0, deferred: 0, negotiated: 0,
      consumer_surplus: 0, batches_cooked: 0 };
  }
  function settle(ctx, s, m, drink, qty, tops, price, surplus, slotTicks) {
    s.lastSaleTick = s.tick;   // demand signal for maybeCook (dead-shop guard)
    m.revenue += price;
    let ic = qty * ctx.DRINK_COST[drink];
    for (const t of tops) ic += qty * ctx.TOP_COST[t];
    m.ingredient_cost += ic;
    m.cups += qty;
    m.toppings += qty * tops.length;
    m.deals += 1;
    m.consumer_surplus += surplus;
    if (tops.indexOf(ctx.batchTop) >= 0) takePearls(s, qty);
    if (slotTicks > 0) {
      const due = Math.min(s.tick + slotTicks, TICKS_PER_DAY - 1);
      s.scheduled[due] = (s.scheduled[due] || 0) + qty;
      m.deferred += 1;
    } else s.queue.push(qty);
  }

  // ── one customer, STATIC lane (run_day walk-in path) ────────────────────
  function serveStatic(ctx, s, m, c, balkRoll) {
    const b = balkProb(s);
    if (balkRoll < b) { m.balks += 1; return { kind: "balk" }; }
    const order = bestMenuOrder(ctx, c, ctx.DRINK_PRICE, ctx.TOP_PRICE, pearlStock(s) >= QTY_CAP);
    const sOut = outsideSurplus(ctx, c);
    if (order.drink !== null && order.surplus > 0 && order.surplus >= sOut) {
      let price = order.qty * ctx.DRINK_PRICE[order.drink];
      for (const t of order.tops) price += order.qty * ctx.TOP_PRICE[t];
      price = round2(price);
      settle(ctx, s, m, order.drink, order.qty, order.tops, price, order.surplus, 0);
      return { kind: "buy", drink: order.drink, qty: order.qty, tops: order.tops, price: price, menu: price, surplus: order.surplus };
    }
    m.lost += 1;
    return { kind: "lost" };
  }

  // ── one customer, SNHP lane (run_day cart path, honest buyer) ───────────
  function serveSnhp(ctx, s, m, c, balkRoll, opts) {
    const deal = cartNash(ctx, s, c, opts);
    if (deal !== null && deal.uBuyer >= deal.dBuyer - 1e-9) {
      if (deal.slotTicks === 0 && balkRoll < balkProb(s)) { m.balks += 1; return { kind: "balk" }; }
      const realized = deal.value - deal.price - deferCost(c, deal.slotTicks, opts && opts.rigidDeferMult);
      // menu list value of the negotiated cart, for the "you saved" readout
      let listv = deal.qty * ctx.DRINK_PRICE[deal.drink];
      for (const t of deal.tops) listv += deal.qty * ctx.TOP_PRICE[t];
      listv = round2(listv);
      settle(ctx, s, m, deal.drink, deal.qty, deal.tops, deal.price, realized, deal.slotTicks);
      m.negotiated += 1;
      return { kind: "deal", drink: deal.drink, qty: deal.qty, tops: deal.tops, price: deal.price,
        menu: listv, slotTicks: deal.slotTicks, save: round2(listv - deal.price), why: deal.why,
        salvage: deal.salvage, relief: deal.relief, surplus: realized, uShop: deal.uShop, dShop: deal.dShop };
    }
    // fall through to the plain walk-in board (never worse UX than static)
    return serveStatic(ctx, s, m, c, balkRoll);
  }

  // ── generate a paired day of customers (run_day arrivals + balk rolls) ───
  function generateDay(ctx, cfg, seed, day) {
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
        // favorite ~ POPULARITY (categorical)
        const roll = rng();
        let acc = 0, fav = ctx.drinks[0];
        for (const d of ctx.drinks) { acc += ctx.POPULARITY[d]; if (roll < acc) { fav = d; break; } }
        const eps = lognormal(rng, 0.0, WTP_SIGMA);
        const wtp = {};
        for (const d of ctx.drinks) wtp[d] = ctx.DRINK_APPEAL[d] * mult * eps * (d === fav ? 1.0 : CROSS_DISCOUNT);
        const top_wtp = {};
        for (const t of ctx.tops) {
          const like = rng() < ctx.TOP_LIKE_PROB[t];
          const draw = lognormal(rng, 0.0, TOP_SIGMA);
          top_wtp[t] = like ? ctx.TOP_APPEAL[t] * draw : 0.0;
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

  // ── run one day of BOTH lanes over the same customers (twin worlds) ──────
  function simulateDay(ctx, cfg, seed, day, opts) {
    const dayData = generateDay(ctx, cfg, seed, day);
    const bm = cfg && cfg.balkModel ? cfg.balkModel : "wait";
    const sStatic = openShop(day, bm), sSnhp = openShop(day, bm);
    const mStatic = newMetrics(), mSnhp = newMetrics();
    const events = [];
    for (let tick = 0; tick < TICKS_PER_DAY; tick++) {
      sStatic.tick = tick; sSnhp.tick = tick;
      mStatic.waste_cost += expireBatches(ctx, sStatic); maybeCook(sStatic); releaseScheduled(sStatic); serveQueue(sStatic);
      mSnhp.waste_cost += expireBatches(ctx, sSnhp); maybeCook(sSnhp); releaseScheduled(sSnhp); serveQueue(sSnhp);
      for (const a of dayData[tick]) {
        mStatic.arrivals += 1; mSnhp.arrivals += 1;
        const qStatic = queueDrinks(sStatic), qSnhp = queueDrinks(sSnhp);
        const evS = serveStatic(ctx, sStatic, mStatic, a.consumer, a.balkRoll);
        const evN = serveSnhp(ctx, sSnhp, mSnhp, a.consumer, a.balkRoll, opts);
        events.push({ tick, hour: hourOf(tick), consumer: a.consumer,
          static: evS, snhp: evN, qStatic, qSnhp });
      }
    }
    mStatic.waste_cost += closeOut(ctx, sStatic); mSnhp.waste_cost += closeOut(ctx, sSnhp);
    mStatic.batches_cooked = sStatic.batchesCooked; mSnhp.batches_cooked = sSnhp.batchesCooked;
    finalize(mStatic); finalize(mSnhp);
    return { static: mStatic, snhp: mSnhp, events };
  }
  function finalize(m) {
    m.margin = round2(m.revenue - m.ingredient_cost - m.waste_cost);
    m.revenue = round2(m.revenue); m.ingredient_cost = round2(m.ingredient_cost);
    m.waste_cost = round2(m.waste_cost); m.consumer_surplus = round2(m.consumer_surplus);
    m.attach_rate = m.cups ? round2(m.toppings / m.cups) : 0;
  }

  // ── run N days, return per-day means (for the validation gate) ──────────
  // `reuseCtx` (optional): pass an already-compiled ctx to skip a second full
  // appeal-inversion (the sandbox reuses the run's ctx for the 15-day means).
  function runDays(spec, cfg, seed, days, opts, reuseCtx) {
    const ctx = reuseCtx || compile(spec);
    const acc = { static: [], snhp: [] };
    for (let d = 0; d < days; d++) {
      const r = simulateDay(ctx, cfg, seed, d, opts);
      acc.static.push(r.static); acc.snhp.push(r.snhp);
    }
    const keys = ["margin", "consumer_surplus", "cups", "deals", "balks", "deferred", "toppings", "waste_cost", "revenue"];
    const mean = (arr) => { const o = {}; for (const k of keys) o[k] = round2(arr.reduce((s, m) => s + m[k], 0) / arr.length); return o; };
    return { static: mean(acc.static), snhp: mean(acc.snhp), ctx };
  }

  return {
    // config
    DEFAULT_SPEC, WTP_SIGMA, TOP_SIGMA, QTY_CAP, HOURLY_RATE, HOURLY_WTP_MULT,
    OPEN_HOUR, TICKS_PER_DAY,
    // math / inversion
    erfc, sf, appealForList, hourOf,
    // engine
    compile, bestMenuOrder, bundleValue, outsideSurplus, cartNash,
    generateDay, simulateDay, runDays,
    // low-level (exposed for the validation invariant checks)
    openShop, serveStatic, serveSnhp, balkProb, pearlStock, queueDrinks,
    expireBatches, maybeCook, releaseScheduled, serveQueue, closeOut,
  };
});

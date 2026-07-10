/* The sim ↔ renderer contract, read side. Loads canned-week.json (the honesty
   gate: EVERY magnitude lives there, never here) and turns a single scalar
   `t` (fractional timelapse-day, 0..days) into everything the scene needs:
   clock hour, cumulative HUD counters, per-day desaturation, per-venue decay,
   crowd size. Live wiring (B4) swaps the JSON for block/runner.py output on the
   same schema; this file does not change. */
(function () {
  "use strict";
  const B = (window.Block = window.Block || {});

  let D = null;                 // the loaded document
  let VENUES = [];              // venues sorted by slot
  const REG = {};               // id -> regular

  function load(url, cb) {
    fetch(url).then(r => r.json()).then(doc => {
      D = doc;
      VENUES = doc.venues.slice().sort((a, b) => a.slot - b.slot);
      (doc.regulars || []).forEach(r => (REG[r.id] = r));
      cb(D);
    }).catch(err => {
      console.error("block: failed to load", url, err);
      cb(null);
    });
  }

  const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
  const lerp = (a, b, t) => a + (b - a) * t;

  // split t into whole day, fraction, and the wall clock the day sweeps through
  function clock(t) {
    const days = D.meta.days;
    t = clamp(t, 0, days - 1e-6);
    const day = Math.floor(t);
    const frac = t - day;
    // each timelapse-day sweeps day_start_hour → +24h
    const hourFloat = ((D.meta.day_start_hour + frac * 24) % 24 + 24) % 24;
    return {
      t, day, frac,
      hourFloat,
      hour: Math.floor(hourFloat),
      weather: (D.weather && D.weather[day]) || "clear",
    };
  }

  // For screenshots: the t (on `day`) whose clock reads exactly `hr`.
  function tForHour(day, hr) {
    let frac = (((hr - D.meta.day_start_hour) % 24) + 24) % 24 / 24;
    return clamp(day + frac, 0, D.meta.days - 1e-6);
  }

  // cumulative HUD value for a mature-delta, integrated over the day-weight ramp
  function ledgerValue(mature, t) {
    const w = D.ledger.day_weight;
    const c = clock(t);
    let sum = 0;
    for (let d = 0; d < c.day; d++) sum += mature * w[d];
    sum += c.frac * mature * w[c.day];
    return sum;
  }
  function counters(t) {
    return {
      shopper: ledgerValue(D.ledger.block_mature.shopper, t),
      merchant: ledgerValue(D.ledger.block_mature.merchant, t),
    };
  }
  // how "diverged" the worlds are right now (0 day-0 identical → ~1 end of week)
  function divergence(t) {
    const w = D.ledger.day_weight, c = clock(t);
    return lerp(w[c.day], w[Math.min(c.day + 1, w.length - 1)], c.frac);
  }

  // per-day arrays, smoothly interpolated across the day boundary
  function dayLerp(arr, t) {
    const c = clock(t);
    return lerp(arr[c.day], arr[Math.min(c.day + 1, arr.length - 1)], c.frac);
  }
  function gray(world, t) { return dayLerp(D.mood.gray[world], t); }
  function decay(world, venueId, t) {
    if (world === "snhp") return 0;
    const arr = D.decay.sticker[venueId];
    return arr ? dayLerp(arr, t) : 0;
  }
  // concurrent ambient crowd right now = per-day base × intraday hour weight
  function ambient(world, t) {
    const c = clock(t);
    const base = dayLerp(D.crowd.ambient_concurrent[world], t);
    return base * D.crowd.hour_weight[c.hour];
  }

  // which named regulars are present on `world` at day (sticker ones vanish
  // after their churn.sticker_lastday — the depopulation you can follow)
  function regularsPresent(world, day) {
    return (D.regulars || []).filter(r => {
      if (world === "snhp") return true;
      return day <= r.churn.sticker_lastday;
    });
  }

  // beats active in a time window [t0,t1) on `world` of a given type
  function beatsBetween(world, type, day, h0, h1) {
    return (D.beats || []).filter(b =>
      b.world === world && b.type === type && b.day === day &&
      b.hour >= h0 && b.hour < h1);
  }

  // ── deterministic PRNG (mulberry32) so headless screenshots reproduce ──────
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // stable hash → [0,1) for id-keyed per-agent constants
  function hash01(x) {
    let h = 2166136261 >>> 0;
    const s = "" + x;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return ((h >>> 0) % 100000) / 100000;
  }

  B.data = {
    load,
    get doc() { return D; },
    get venues() { return VENUES; },
    get regulars() { return D ? D.regulars : []; },
    reg: (id) => REG[id],
    clock, tForHour, counters, divergence,
    gray, decay, ambient, regularsPresent, beatsBetween,
    rng, hash01, clamp, lerp,
  };
})();

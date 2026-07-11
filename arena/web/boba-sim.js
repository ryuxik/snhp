/* boba-sim.js — the OWNER SANDBOX UI.
 * Onboards the owner's SKUs + conditions, runs the faithfully-ported SNHP
 * engine (boba-engine.js) on a simulated day, and animates the STATIC vs SNHP
 * twin worlds. Every number on screen comes from the engine — nothing here is
 * hardcoded except the sample menu defaults (the extracted calibration menu).
 */
(function () {
  "use strict";
  const B = window.BobaEngine;
  const $ = (s) => document.querySelector(s);
  const money = (n) => "$" + Math.round(Number(n)).toLocaleString();
  const money1 = (n) => "$" + Number(n).toFixed(2);
  // signed money: "-$8" for negatives, "+$8" for >=0 (never the broken "+$-8")
  const signed = (n) => { const v = Math.round(Number(n)); return (v < 0 ? "-$" : "+$") + Math.abs(v).toLocaleString(); };
  // signed integer: "-9" / "+28"
  const signedInt = (n) => { const v = Math.round(Number(n)); return (v < 0 ? "" : "+") + v; };
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  if (!B) { showErr("engine failed to load (boba-engine.js)"); return; }

  // v1-SAFE SNHP config — the shipped guarantees
  const SAFE = { quoteLookers: false, qtyAppetite: true, minPriceFrac: 0.6 };
  const SEED = 20260710;
  const TRAFFIC = { quiet: 0.62, normal: 1.0, rush: 1.45 };

  // ── the sample menu (extracted calibration menu, the sensible default) ──
  const SAMPLE = {
    drinks: [
      { name: "Classic Milk Tea", price: 6.25, cost: 1.35 },
      { name: "Brown Sugar Boba", price: 7.25, cost: 1.60 },
      { name: "Matcha Latte",     price: 7.50, cost: 1.75 },
    ],
    top: { name: "Tapioca Pearls", price: 0.85, cost: 0.10 },
  };

  let dayCounter = 3;   // advances each run so every "Run a day" is a fresh day
  let running = false;
  let rafId = null;
  let safetyTimer = null;

  // ── emoji ───────────────────────────────────────────────────────────────
  function drinkEmoji(name) {
    const n = (name || "").toLowerCase();
    if (n.includes("matcha")) return "🍵";
    if (n.includes("fruit") || n.includes("mango") || n.includes("peach") || n.includes("lychee")) return "🧃";
    if (n.includes("taro")) return "🟣";
    if (n.includes("coffee") || n.includes("thai")) return "☕";
    return "🧋";
  }
  function topEmoji(name) {
    const n = (name || "").toLowerCase();
    if (n.includes("pudding")) return "🍮";
    if (n.includes("jelly")) return "🟩";
    if (n.includes("cheese") || n.includes("foam")) return "🧀";
    return "🫧";
  }

  // ── onboard: build the editable rows ─────────────────────────────────────
  function drinkRow(d, i, n) {
    const wrap = document.createElement("div");
    wrap.className = "skurow";
    wrap.innerHTML =
      '<span class="drinkname"><span class="emo">' + drinkEmoji(d.name) + '</span>' +
        '<input type="text" class="dName" value="' + esc(d.name) + '" aria-label="drink name" />' +
        (n > 2 ? '<button class="removebtn" title="remove" aria-label="remove drink">✕</button>' : '') + '</span>' +
      '<input type="number" class="dPrice" value="' + d.price + '" min="0" step="0.05" aria-label="menu price" />' +
      '<input type="number" class="dCost" value="' + d.cost + '" min="0" step="0.05" aria-label="unit cost" />';
    const emo = wrap.querySelector(".emo"), nm = wrap.querySelector(".dName");
    nm.addEventListener("input", () => { emo.textContent = drinkEmoji(nm.value); });
    const rm = wrap.querySelector(".removebtn");
    if (rm) rm.addEventListener("click", () => { wrap.remove(); syncAdd(); });
    return wrap;
  }
  function renderDrinks(drinks) {
    const host = $("#drinkRows"); host.innerHTML = "";
    drinks.forEach((d, i) => host.appendChild(drinkRow(d, i, drinks.length)));
    syncAdd();
  }
  function renderTop(top) {
    const host = $("#topRow"); host.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "skurow top";
    wrap.innerHTML =
      '<span class="drinkname"><span class="emo" id="topEmo">' + topEmoji(top.name) + '</span>' +
        '<input type="text" id="tName" value="' + esc(top.name) + '" aria-label="topping name" /></span>' +
      '<input type="number" id="tPrice" value="' + top.price + '" min="0" step="0.05" aria-label="topping price" />' +
      '<input type="number" id="tCost" value="' + top.cost + '" min="0" step="0.05" aria-label="topping cost" />';
    host.appendChild(wrap);
    $("#tName").addEventListener("input", () => { $("#topEmo").textContent = topEmoji($("#tName").value); });
  }
  function syncAdd() {
    const n = document.querySelectorAll("#drinkRows .skurow").length;
    $("#addDrink").disabled = n >= 3;
    // refresh remove buttons (only show when >2)
    document.querySelectorAll("#drinkRows .skurow").forEach((row) => {
      let rm = row.querySelector(".removebtn");
      if (n > 2 && !rm) {
        rm = document.createElement("button");
        rm.className = "removebtn"; rm.title = "remove"; rm.textContent = "✕";
        rm.addEventListener("click", () => { row.remove(); syncAdd(); });
        row.querySelector(".drinkname").appendChild(rm);
      } else if (n <= 2 && rm) rm.remove();
    });
  }

  // ── read the menu spec from the DOM ─────────────────────────────────────
  // No silent defaults: a blank/invalid field returns NaN and validate() rejects
  // it. The sim must never run on numbers the owner didn't type.
  function num(el) { const v = parseFloat(el.value); return isFinite(v) ? v : NaN; }
  function readSpec() {
    const drinks = [];
    document.querySelectorAll("#drinkRows .skurow").forEach((row) => {
      const name = (row.querySelector(".dName").value || "").trim() || "Drink";
      const price = num(row.querySelector(".dPrice"));
      const cost = num(row.querySelector(".dCost"));
      drinks.push({ name, price, cost, popularity: 1 });   // even popularity split
    });
    const topName = ($("#tName").value || "").trim() || "Topping";
    const top = { name: topName, price: num($("#tPrice")), cost: num($("#tCost")),
      like_prob: 0.55 };
    return { drinks, tops: [top], batchTop: topName };
  }
  function validate(spec) {
    if (spec.drinks.length < 2) return "Add at least two drinks.";
    for (const d of spec.drinks) {
      if (!isFinite(d.price) || !isFinite(d.cost)) return "Fill in a price and cost for every drink.";
      if (d.price <= 0 || d.cost < 0) return "Prices and costs must be positive.";
      if (d.price <= d.cost + 0.05) return "“" + d.name + "”: menu price must be above unit cost.";
    }
    const t = spec.tops[0];
    if (!isFinite(t.price) || !isFinite(t.cost)) return "Fill in a price and cost for the topping.";
    if (t.cost < 0) return "The topping's cost can't be negative.";
    if (t.price <= t.cost) return "The topping's price must be above its cost.";
    // duplicate drink names break the engine's keying
    const names = spec.drinks.map((d) => d.name.toLowerCase());
    if (new Set(names).size !== names.length) return "Give each drink a distinct name.";
    return null;
  }

  // ── conditions ──────────────────────────────────────────────────────────
  let traffic = "normal";
  function wireControls() {
    $("#traffic").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      document.querySelectorAll("#traffic button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on"); traffic = b.dataset.v;
    });
    const fl = $("#flex");
    fl.addEventListener("input", () => { $("#flexVal").textContent = fl.value + "%"; });
    $("#addDrink").addEventListener("click", () => {
      if (document.querySelectorAll("#drinkRows .skurow").length >= 3) return;
      $("#drinkRows").appendChild(drinkRow({ name: "New Drink", price: 6.75, cost: 1.55 }, 9, 3));
      syncAdd();
    });
    $("#runBtn").addEventListener("click", run);
    $("#resetBtn").addEventListener("click", () => {
      stopRun();                       // cancel any in-flight animation first
      renderDrinks(SAMPLE.drinks.map((d) => Object.assign({}, d)));
      renderTop(Object.assign({}, SAMPLE.top));
      $("#expiring").checked = false;
      traffic = "normal";
      document.querySelectorAll("#traffic button").forEach((x) => x.classList.toggle("on", x.dataset.v === "normal"));
      $("#flex").value = 35; $("#flexVal").textContent = "35%";
      // full reset of the derived UI so the sample menu is immediately runnable
      dayCounter = 3;
      $("#results").classList.remove("show");
      $("#feed").innerHTML = ""; $("#split").innerHTML = ""; $("#tiles").innerHTML = "";
      $("#runBtn").textContent = "▶ Run a day";
      $("#runNote").textContent = "Runs one simulated day on the numbers above.";
      $("#runNote").style.color = "";
      $("#resetBtn").style.display = "none";
    });
  }

  // stop any in-flight animation (rAF + the backgrounded-tab safety timer) and
  // clear `running` so a fresh run is immediately allowed.
  function stopRun() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    if (safetyTimer) { clearTimeout(safetyTimer); safetyTimer = null; }
    running = false;
    $("#runBtn").disabled = false;
  }

  // ── run a day ───────────────────────────────────────────────────────────
  function run() {
    if (running) return;
    const spec = readSpec();
    const err = validate(spec);
    if (err) {
      // hide stale twin-worlds numbers so they don't sit next to the error
      $("#results").classList.remove("show");
      $("#runNote").textContent = err; $("#runNote").style.color = "var(--pink)";
      $("#resetBtn").style.display = "";
      return;
    }
    $("#runNote").style.color = ""; $("#runNote").textContent = "Runs one simulated day on the numbers above.";
    $("#resetBtn").style.display = "";

    const flex = parseInt($("#flex").value, 10) / 100;
    // rigidDeferMult ramp: "0% flexible" must mean genuinely NO smoothing. The
    // calibrated model (flex >= 35%) is untouched (mult = 1); below it, a rigid
    // buyer's cost of a later pickup climbs steeply so the deferral channel
    // fades to ~0 as the slider hits 0% — the honest slider AND the clearest
    // demo of how much of the win depends on flexibility.
    const rigidMult = flex >= 0.35 ? 1 : Math.pow(0.35 / Math.max(flex, 1e-4), 4);
    const cfg = { flexibleShare: flex, trafficMult: TRAFFIC[traffic], balkModel: "wait" };
    const opts = Object.assign({}, SAFE, { salvage: true, rigidDeferMult: rigidMult });
    // the "expiring batch" toggle: when OFF, deny the salvage lever (so waste
    // shows the un-steered outcome); when ON, allow SNHP to move a soon-to-be-
    // tossed batch into cups (the engine's real pearls-salvage path).
    if (!$("#expiring").checked) opts.salvage = false;

    let ctx;
    try { ctx = B.compile(spec); }
    catch (e) { $("#results").classList.remove("show"); $("#runNote").textContent = "Couldn't build that menu: " + e.message; $("#runNote").style.color = "var(--pink)"; return; }

    const day = dayCounter++;
    let sim;
    try { sim = B.simulateDay(ctx, cfg, SEED, day, opts); }
    catch (e) { $("#results").classList.remove("show"); showErr("simulation error: " + e.message); return; }

    // quiet 15-day means: the typical caption AND the honest channel split.
    // banks-now = SNHP with deferral OFF vs static (robust: discounts, cleared
    // waste, bigger baskets). deferral = full SNHP minus that (forecast: rides
    // on the wait-time model AND on customers accepting the later pickup).
    let info = { typ: null, banks: null, defer: null };
    try {
      // reuse the already-built ctx (skip a second full appeal-inversion)
      const full = B.runDays(spec, cfg, SEED, 15, opts, ctx);
      const nod = B.runDays(spec, cfg, SEED, 15, Object.assign({}, opts, { deferSlots: false }), ctx);
      info.typ = Math.round(full.snhp.margin - full.static.margin);
      info.banks = Math.round(nod.snhp.margin - nod.static.margin);
      info.defer = Math.round(full.snhp.margin - nod.snhp.margin);
    } catch (e) { /* leave nulls; summary degrades gracefully */ }

    $("#results").classList.add("show");
    $("#twinSub").textContent = "simulated day #" + (day - 2);
    $("#typicalNote").textContent = info.typ != null ? "typical: " + signed(info.typ) + "/day over 15 days" : "";
    animate(sim, spec, info);
    $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ── the twin-worlds animation ───────────────────────────────────────────
  const DURATION = 4200;
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  function animate(sim, spec, info) {
    running = true;
    $("#runBtn").disabled = true;
    if (rafId) cancelAnimationFrame(rafId);
    $("#sStreet").querySelectorAll(".cust").forEach((c) => c.remove());
    $("#nStreet").querySelectorAll(".cust").forEach((c) => c.remove());
    $("#feed").innerHTML = "";

    const S = sim.static, N = sim.snhp;
    const targets = [
      ["#sMargin", S.margin, money], ["#sCups", S.cups], ["#sBalk", S.balks],
      ["#sTop", S.toppings], ["#sCS", S.consumer_surplus, money], ["#sDefer", S.deferred], ["#sWaste", S.waste_cost, money1],
      ["#nMargin", N.margin, money], ["#nCups", N.cups], ["#nBalk", N.balks],
      ["#nTop", N.toppings], ["#nCS", N.consumer_surplus, money], ["#nDefer", N.deferred], ["#nWaste", N.waste_cost, money1],
    ];
    const targetEls = targets.map((row) => $(row[0]));   // resolve selectors ONCE

    // ── build the flow playlist: all divergences + a sample of the rest ──
    // salvage is read from the engine's structured deal.salvage flag — never by
    // parsing display prose (which also mis-fired for any zero-cost topping).
    const evs = sim.events;
    const diverge = [];
    for (const e of evs) {
      const kept = e.static.kind === "balk" && e.snhp.kind !== "balk";
      const salv = e.snhp.kind === "deal" && !!e.snhp.salvage;
      const offpk = e.snhp.kind === "deal" && e.snhp.slotTicks > 0;
      const disc = e.snhp.kind === "deal" && e.snhp.save > 0.4;
      if (kept || salv || offpk || disc) diverge.push({ e, kept, salv, offpk, disc });
    }
    // playlist for avatars (cap ~66, keep chronological, ensure divergences in)
    const CAP = 66;
    let playlist;
    if (evs.length <= CAP) playlist = evs.slice();
    else {
      const stride = Math.ceil(evs.length / CAP);
      const set = new Set(diverge.map((d) => d.e));
      playlist = evs.filter((e, i) => set.has(e) || i % stride === 0).slice(0, CAP + 10);
    }

    // divergence feed items (curated, most illustrative first, max 5)
    const feedItems = buildFeed(diverge, spec);

    const start = performance.now();
    let nextAvatar = 0, nextFeed = 0, done = false;
    const feedTimes = feedItems.map((_, i) => 500 + i * ((DURATION - 900) / Math.max(1, feedItems.length)));

    // finalize once — called by the rAF loop at t=1, or by the safety timer if
    // the tab was backgrounded (rAF is throttled/paused when hidden, so a run
    // started in a hidden tab would otherwise never populate the result).
    function finish() {
      if (done) return; done = true;
      if (rafId) cancelAnimationFrame(rafId);
      targets.forEach((row, i) => { targetEls[i].textContent = row[2] ? row[2](row[1]) : Math.round(row[1]).toLocaleString(); });
      while (nextAvatar < playlist.length) { spawnAvatar(playlist[nextAvatar]); nextAvatar++; }
      while (nextFeed < feedItems.length) { $("#feed").appendChild(feedItems[nextFeed]); nextFeed++; }
      const collapse = (sim.static.cups + sim.snhp.cups) < 8;
      if (!feedItems.length && !collapse) $("#feed").innerHTML = feedEmpty();
      fillSummary(sim, spec, info);
      running = false; $("#runBtn").disabled = false; $("#runBtn").textContent = "▶ Run another day";
    }

    function frame(now) {
      const t = clamp((now - start) / DURATION, 0, 1);
      const k = easeOut(t);
      // climb numbers (elements resolved once, above)
      for (let i = 0; i < targets.length; i++) {
        const row = targets[i]; const val = row[1] * k; const fmt = row[2];
        targetEls[i].textContent = fmt ? fmt(val) : Math.round(val).toLocaleString();
      }
      // spawn avatars on schedule
      const wantAv = Math.floor(t * playlist.length);
      while (nextAvatar < wantAv && nextAvatar < playlist.length) {
        spawnAvatar(playlist[nextAvatar]); nextAvatar++;
      }
      // spawn feed items
      while (nextFeed < feedItems.length && (now - start) >= feedTimes[nextFeed]) {
        $("#feed").appendChild(feedItems[nextFeed]); nextFeed++;
      }
      if (t < 1) { rafId = requestAnimationFrame(frame); }
      else finish();
    }
    rafId = requestAnimationFrame(frame);
    if (safetyTimer) clearTimeout(safetyTimer);
    safetyTimer = setTimeout(finish, DURATION + 700);   // safety net for a backgrounded tab
  }

  let laneSlot = { s: 0, n: 0 };
  function spawnAvatar(ev) {
    laneSlot.s = (laneSlot.s + 1) % 6; laneSlot.n = (laneSlot.n + 1) % 6;
    place($("#sStreet"), ev.consumer, ev.static, (laneSlot.s));
    place($("#nStreet"), ev.consumer, ev.snhp, (laneSlot.n));
  }
  function place(street, consumer, out, slot) {
    const el = document.createElement("div");
    const emo = drinkEmoji(consumer.fav);
    let cls = "cust", badge = "";
    if (out.kind === "buy" || out.kind === "deal") {
      cls += out.kind === "deal" ? " deal" : " buy";
      if (out.kind === "deal") {
        if (out.slotTicks > 0) badge = "+" + out.slotTicks * 10 + "m";
        else if (out.salvage) badge = "🫧 free";
        else if (out.save > 0.4) badge = "-" + money1(out.save).replace(".00", "");
      }
    } else if (out.kind === "balk") { cls += " balk"; badge = "walked"; }
    else { cls += ""; el.style.opacity = ".4"; }
    el.className = cls;
    el.innerHTML = emo + (badge ? '<span class="badge">' + badge + '</span>' : '');
    const top = 6 + slot * 11;
    el.style.top = top + "px";
    el.style.transform = "translateX(0)";
    el.style.transition = "none";
    street.appendChild(el);
    // trigger the walk
    requestAnimationFrame(() => {
      el.style.transition = "transform 1.5s cubic-bezier(.3,.6,.4,1), opacity .5s";
      if (out.kind === "balk") {
        // peel off downward and fade — the walk-away
        el.style.transform = "translateX(120px) translateY(46px)";
        el.style.opacity = "0";
      } else {
        const w = street.clientWidth || 240;
        el.style.transform = "translateX(" + (w - 40) + "px)";
        if (out.kind === "lost") el.style.opacity = "0";
      }
    });
    setTimeout(() => { el.style.transition = "opacity .4s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, 1700);
  }

  // ── divergence feed ─────────────────────────────────────────────────────
  function buildFeed(diverge, spec) {
    const topName = spec.tops[0].name;
    const items = [];
    const seen = { kept: 0, salv: 0, offpk: 0, disc: 0 };
    // priority: kept-from-walking, then salvage, then off-peak, then discount
    function pick(type) {
      for (const d of diverge) {
        if (d[type] && !d._used) {
          d._used = true; return d;
        }
      }
      return null;
    }
    const wants = ["kept", "salv", "kept", "offpk", "disc", "kept"];
    for (const w of wants) {
      if (items.length >= 5) break;
      const d = pick(w);
      if (!d) continue;
      items.push(feedItem(d, w, topName));
    }
    // backfill from any remaining divergences
    for (const d of diverge) {
      if (items.length >= 5) break;
      if (d._used) continue;
      const type = d.kept ? "kept" : d.salv ? "salv" : d.offpk ? "offpk" : "disc";
      d._used = true; items.push(feedItem(d, type, topName));
    }
    return items;
  }
  function feedItem(d, type, topName) {
    const el = document.createElement("div"); el.className = "fitem";
    const e = d.e, sn = e.snhp;
    const cart = drinkName(sn) ;
    let ic = "🤝", tx = "";
    if (type === "kept") {
      ic = "🙌";
      const line = e.qStatic;
      const slot = sn.kind === "deal" && sn.slotTicks > 0 ? "a +" + sn.slotTicks * 10 + "-min pickup" : "a right-now slot";
      tx = "A customer hit a <b>" + line + "-deep</b> line and <span class='s'>walked away</span> in Static — SNHP offered <span class='n'>" + slot + "</span> and <b>kept the sale</b>.";
    } else if (type === "salv") {
      ic = "♻️";
      tx = "SNHP put <span class='n'>" + esc(topName) + " on the house</span> from a batch about to be tossed — the customer got a topping, you cut <b>waste</b>.";
    } else if (type === "offpk") {
      ic = "🕒";
      tx = "Moved an order to a <span class='n'>+" + sn.slotTicks * 10 + "-min pickup</span> — off your worst crush, no drink lost, the same cup made when the bar is free.";
    } else {
      ic = "💸";
      tx = "Settled a cart <span class='n'>" + money1(sn.save).replace(".00", "") + " under the menu</span> — out of value the trade created, <b>never</b> out of your margin.";
    }
    el.innerHTML = '<div class="ic">' + ic + '</div><div class="tx">' + tx + '</div>';
    return el;
  }
  function feedEmpty() {
    return '<div class="fitem"><div class="ic">🤝</div><div class="tx">A calm day — the line never got long enough to push anyone off. SNHP still held every price at or below your menu. Try <b>lunch rush</b> traffic to see it smooth a crush.</div></div>';
  }
  function drinkName(out) { return out.drink ? out.drink : ""; }

  // ── result summary ──────────────────────────────────────────────────────
  function fillSummary(sim, spec, info) {
    const S = sim.static, N = sim.snhp;

    // demand-collapse regime: at these prices almost no one buys in EITHER
    // world (usually menu price set at/above what customers will pay). The
    // honest read, not a "calm day".
    if (S.cups + N.cups < 8) { renderCollapse(sim); return; }

    // net customers kept: static walked-in balks SNHP served, MINUS the
    // reverse — buyers SNHP's own scheduling pushed into a longer line.
    let kept = 0, reverse = 0, saved = 0;
    for (const e of sim.events) {
      const snServed = e.snhp.kind === "deal" || e.snhp.kind === "buy";
      const stServed = e.static.kind === "deal" || e.static.kind === "buy";
      if (e.static.kind === "balk" && snServed) kept++;
      if (stServed && e.snhp.kind === "balk") reverse++;
      if (e.snhp.kind === "deal" && e.snhp.save > 0) saved += e.snhp.save;
    }
    const netKept = kept - reverse;
    const dMargin = Math.round(N.margin - S.margin);
    const dWaste = Math.max(0, S.waste_cost - N.waste_cost);
    const keptWord = Math.abs(netKept) === 1 ? "customer" : "customers";

    // sign-aware clauses — SNHP weakly dominates almost always, but edge configs
    // can go negative and must read honestly (never "+$-N").
    const marginClause = dMargin >= 0
      ? "earned <span class='gold'>" + signed(dMargin) + "</span> more margin"
      : "landed <span class='gold'>" + signed(dMargin) + "</span> on margin (behind static this day)";
    const keptClause = netKept >= 0
      ? "kept a <span class='g'>net " + netKept + " " + keptWord + "</span> who'd have walked out on a long line"
      : "on net <span class='warn'>lost " + Math.abs(netKept) + " " + keptWord + "</span> to a line its own scheduling lengthened";

    $("#verdict").innerHTML =
      "On your menu, this simulated day SNHP " + marginClause + ", " + keptClause + ", " +
      "put <span class='g'>" + money(saved) + "</span> back in customers' pockets, and cut waste by " +
      "<span class='g'>" + money1(dWaste).replace(".00", "") + "</span>. " +
      "<b>Every</b> quote stayed at or below your printed menu.";

    // ── the honest margin split (fix #1) ──
    renderSplit(info, dMargin);

    $("#tiles").innerHTML =
      tile("gold", signed(dMargin), "more margin<br>on the day") +
      tile(netKept >= 0 ? "g" : "warn", signedInt(netKept), "net customers kept<br>who'd have walked") +
      tile("blue", "+" + money(saved), "handed back<br>to customers") +
      tile("g", "−" + money1(dWaste).replace(".00", ""), "less tapioca<br>thrown out");

    $("#footNote").innerHTML =
      "“Net kept” is walk-aways SNHP rescued minus the " + reverse + " buyer" + (reverse === 1 ? "" : "s") +
      " its own scheduling happened to push into a longer line this day — smoothing isn't free. " +
      "Ported client-side from the real engine (<code>boba/world.py</code>, <code>boba/policies.py cart_nash</code>, " +
      "<code>boba/run.py</code>), v1-safe config, seed " + SEED + ". The port reproduces the Python paired reference " +
      "within Monte-Carlo tolerance (±8%). Every number is engine-computed on your inputs.";
  }
  function tile(cls, v, k) { return '<div class="tile ' + cls + '"><div class="v">' + v + '</div><div class="k">' + k + '</div></div>'; }

  // margin split: robust "banks now" vs forecast-dependent off-peak deferral
  function renderSplit(info, dMargin) {
    const host = $("#split");
    if (!info || info.banks == null || info.defer == null) { host.innerHTML = ""; return; }
    const banks = Math.max(0, info.banks), defer = Math.max(0, info.defer);
    const tot = Math.max(1, banks + defer);
    const bp = Math.round(100 * banks / tot), fp = 100 - bp;
    host.innerHTML =
      '<div class="split-h">Where the ' + signed(info.typ) + '/day comes from — and how much to trust it</div>' +
      '<div class="split-bar">' +
        '<div class="seg-robust" style="flex:' + Math.max(6, bp) + '"><span>+' + money(banks) + '</span></div>' +
        '<div class="seg-forecast" style="flex:' + Math.max(6, fp) + '"><span>+' + money(defer) + '</span></div>' +
      '</div>' +
      '<div class="split-rows">' +
        '<div class="split-row robust"><span class="dot"></span><b>+' + money(banks) + ' banks now.</b> ' +
          'Discounts out of value the trade created, tapioca cleared before it spoils, and bigger baskets. ' +
          'This is the <b>robust</b> floor — it doesn\'t depend on any forecast.</div>' +
        '<div class="split-row forecast"><span class="dot"></span><b>+' + money(defer) + ' only if customers accept the later pickup.</b> ' +
          'Off-peak smoothing. This part is <b>softer</b>: it rides on our wait-time model and on people actually ' +
          'taking the +30/+60-min slot — drag the flexibility slider down and watch it shrink toward the floor.</div>' +
      '</div>';
  }

  // demand-collapse: almost no sales in either world
  function renderCollapse(sim) {
    const S = sim.static, N = sim.snhp;
    $("#verdict").innerHTML =
      "<b>At these prices the model shows demand collapsing.</b> Almost no one buys in <em>either</em> world " +
      "(static " + S.cups + " cups, SNHP " + N.cups + ") — your menu price is at or above what these customers will pay, " +
      "so there's no surplus for SNHP to trade on. A discount-only engine can't sell below cost. " +
      "Widen the gap between your menu price and unit cost and run it again.";
    $("#split").innerHTML = "";
    $("#tiles").innerHTML =
      tile("", S.cups, "static cups<br>(near zero)") +
      tile("", N.cups, "SNHP cups<br>(near zero)") +
      tile("gold", (N.margin < 0 ? "-$" : "$") + Math.abs(N.margin).toFixed(2), "SNHP margin<br>on the day") +
      tile("g", "$" + N.waste_cost.toFixed(2), "waste — the shop<br>stops cooking when dead");
    $("#feed").innerHTML =
      '<div class="fitem"><div class="ic">🚫</div><div class="tx">No line ever formed because almost nothing sold. ' +
      'The operator stops cooking tapioca once the shop is dead, so waste is just the opening batch — not a compounding artifact. ' +
      'SNHP still held every price at or below your menu; it simply had nothing to work with.</div></div>';
    $("#footNote").innerHTML =
      "Every number is engine-computed (<code>boba/world.py</code>, <code>boba/policies.py cart_nash</code>, " +
      "<code>boba/run.py</code>), v1-safe config, seed " + SEED + ".";
  }

  function showErr(msg) { const e = $("#err"); e.style.display = "block"; e.textContent = "⚠ " + msg; }

  // ── boot ────────────────────────────────────────────────────────────────
  renderDrinks(SAMPLE.drinks.map((d) => Object.assign({}, d)));
  renderTop(Object.assign({}, SAMPLE.top));
  wireControls();
})();

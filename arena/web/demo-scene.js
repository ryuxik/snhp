/* SNHP DEMO — the immersive BOBA CONSUMER stop.
 *
 * You walk up to a boba shop's self-order tablet, build a normal order, and
 * money-saving options surface right in the order. The price ticks DOWN as you
 * opt into them — never above the menu — and the receipt shows what YOU saved.
 *
 * Three beats on one screen:
 *   ACT 1  WALK UP   — a first-person pixel boba shop; tap to step to the tablet.
 *   ACT 2  ORDER     — the tablet UI: drink → size → sweetness → ice → toppings,
 *                      then the money-saving levers (pickup time ★, quantity),
 *                      each showing its REAL saving as you opt in.
 *   ACT 3  RECEIPT   — a receipt prints: your order, what you paid, what you saved.
 *
 * HONESTY (hard rule): every price and every saving is computed LIVE by the real
 * SNHP boba engine (boba-engine.js, the faithful cart_nash port) at the menu
 * prices below — nothing is scripted or fabricated. priceCart runs the identical
 * Nash-split pricing math for the exact cart you build; the price is NEVER above
 * the menu. This is a CONSUMER page only: zero provider economics, no margins,
 * no forecasts, no attestation — just your order and your saving.
 */
(function () {
  "use strict";

  var P = (window.Block && window.Block.pal) || null;
  var B = window.BobaEngine;
  var reduced = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ═══════════════════════════════════════════════════════════════════════════
  //  MENU — real, HeyTea-anchored (task numbers). Costs use the default engine's
  //  price/cost ratios so the appeal-inversion produces sane WTPs. matcha is a
  //  DRINK base, never a topping. FREE (never priced/negotiated): sweetness, ice.
  // ═══════════════════════════════════════════════════════════════════════════
  var MENU = {
    drinks: [
      { name: "classic-milk-tea", price: 5.50, cost: 1.20, popularity: 0.30, label: "Classic Milk Tea", emo: "🧋" },
      { name: "brown-sugar",      price: 6.75, cost: 1.55, popularity: 0.26, label: "Brown Sugar Boba Milk", emo: "🤎" },
      { name: "mango-fruit-tea",  price: 7.00, cost: 1.55, popularity: 0.24, label: "Mango Fruit Tea", emo: "🥭" },
      { name: "matcha-latte",     price: 7.50, cost: 1.75, popularity: 0.20, label: "Matcha Latte", emo: "🍵" },
    ],
    tops: [
      { name: "pearls",      price: 0.75, cost: 0.10, like_prob: 0.65, label: "Tapioca Pearls", emo: "⚫" },
      { name: "pudding",     price: 0.75, cost: 0.15, like_prob: 0.35, label: "Pudding", emo: "🍮" },
      { name: "grass-jelly", price: 0.75, cost: 0.12, like_prob: 0.30, label: "Grass Jelly", emo: "🟩" },
      { name: "cheese-foam", price: 1.50, cost: 0.25, like_prob: 0.40, label: "Cheese Foam", emo: "🧀" },
    ],
    batchTop: "pearls",
  };
  var SIZE_UP_L = 0.75;                 // Large is +$0.75/cup — a flat menu upcharge,
                                        // added to menu AND paid alike (not negotiated).
  var DRINK_LABEL = {}, TOP_LABEL = {};
  MENU.drinks.forEach(function (d) { DRINK_LABEL[d.name] = d.label; });
  MENU.tops.forEach(function (t) { TOP_LABEL[t.name] = t.label; });

  // ═══════════════════════════════════════════════════════════════════════════
  //  THE SHOP MOMENT + THE SHOPPER (a specific, transparent scenario).
  //  A peak lunchtime lull (queue building) with an over-cooked tapioca batch
  //  near its sell-by — so a later off-peak pickup frees the rush AND the fresh
  //  pearls are near-waste. Everything below feeds the REAL engine; the numbers
  //  are whatever it returns.
  // ═══════════════════════════════════════════════════════════════════════════
  var SCEN = { tick: 21, queue: 5, batchServings: 40, batchExpiresIn: 3 };
  var SHOPPER = { eps: 1.15, topDraw: 1.05, decay: 0.60, flexible: true };
  var OPTS = { minPriceFrac: 0.6, salvage: true, rigidDeferMult: 1 };

  var SLOTS = [
    { ticks: 0, label: "Now", meta: "straight away" },
    { ticks: 3, label: "In 30 min", meta: "after the lunch rush" },
    { ticks: 6, label: "In 60 min", meta: "a quiet slot" },
  ];
  var QTYS = [
    { n: 1, label: "Just me", meta: "one cup", emo: "🧋" },
    { n: 2, label: "Add a 2nd", meta: "a friend's cup", emo: "👯" },
    { n: 3, label: "Grab 3 for the group", meta: "an office run", emo: "👥" },
  ];
  var SWEETS = ["0%", "25%", "50%", "75%", "100%"];
  var ICES = ["Regular", "Less", "None"];

  // ── engine setup ────────────────────────────────────────────────────────────
  var ctx = null, shop = null, consumer = null, salvageActive = false, engineOk = false;
  var round2 = function (x) { return Math.round((x + Number.EPSILON) * 100) / 100; };
  var money = function (x) { return "$" + Number(x).toFixed(2); };

  function buildEngine() {
    ctx = B.compile({
      drinks: MENU.drinks.map(function (d) { return { name: d.name, price: d.price, cost: d.cost, popularity: d.popularity }; }),
      tops: MENU.tops.map(function (t) { return { name: t.name, price: t.price, cost: t.cost, like_prob: t.like_prob }; }),
      batchTop: MENU.batchTop,
    });
    // the shop moment (a frozen, read-only state; priceCart never mutates it)
    shop = B.openShop(0, "wait");
    shop.tick = SCEN.tick;
    shop.batches = [{ servings: SCEN.batchServings, expires: SCEN.tick + SCEN.batchExpiresIn }];
    shop.queue = SCEN.queue > 0 ? [SCEN.queue] : [];
    shop.lastSaleTick = SCEN.tick;
    // the shopper: WTP is a real function of the engine's calibrated appeals
    var mult = B.HOURLY_WTP_MULT[B.hourOf(SCEN.tick)];
    var wtp = {}, top_wtp = {};
    ctx.drinks.forEach(function (d) { wtp[d] = ctx.DRINK_APPEAL[d] * mult * SHOPPER.eps; });
    ctx.tops.forEach(function (t) { top_wtp[t] = ctx.TOP_APPEAL[t] * SHOPPER.topDraw; });
    consumer = { wtp: wtp, top_wtp: top_wtp, flexible: SHOPPER.flexible, qty_decay: SHOPPER.decay };
    // is the batch-topping salvage lever live in this moment? (shop fact, cart-free)
    salvageActive = B.priceCart(ctx, shop, consumer,
      { drink: MENU.drinks[0].name, tops: [MENU.batchTop], qty: 1, slotTicks: 0 }, OPTS).salvageUsed;
    engineOk = true;
  }

  // price the exact cart the shopper built; size is a flat upcharge on both sides
  function priceOrder(o) {
    var e = B.priceCart(ctx, shop, consumer,
      { drink: o.drink, tops: o.tops.slice(), qty: o.qty, slotTicks: o.slotTicks }, OPTS);
    var up = (o.sizeUp || 0) * o.qty;
    return {
      pay: round2(e.price + up),
      menu: round2(e.listv + up),
      save: round2(e.save),         // size cancels — never negotiated
      salvageUsed: e.salvageUsed,
      feasible: e.feasible,
    };
  }
  function perCupMenu(o) {
    var s = ctx.DRINK_PRICE[o.drink] + (o.sizeUp || 0);
    o.tops.forEach(function (t) { s += ctx.TOP_PRICE[t]; });
    return round2(s);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  PIXEL BOBA SHOP (POV backdrop) — integer-upscaled low-res backbuffer, same
  //  crisp technique as arena/web/block/scene.js.
  // ═══════════════════════════════════════════════════════════════════════════
  var $ = function (id) { return document.getElementById(id); };
  var view = $("view"), c = view.getContext("2d");
  c.imageSmoothingEnabled = false;

  var LOW_H = 240, LOW_W = 420, scale = 2, canvasLeft = 0, canvasTop = 0;
  function resize() {
    var availW = window.innerWidth, availH = window.innerHeight;
    LOW_W = Math.max(300, Math.min(680, Math.round(LOW_H * (availW / availH))));
    view.width = LOW_W; view.height = LOW_H; c.imageSmoothingEnabled = false;
    scale = Math.max(availW / LOW_W, availH / LOW_H);
    var dispW = Math.round(LOW_W * scale), dispH = Math.round(LOW_H * scale);
    view.style.width = dispW + "px"; view.style.height = dispH + "px";
    canvasLeft = (availW - dispW) / 2; canvasTop = (availH - dispH) / 2;
  }
  window.addEventListener("resize", resize);

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function mix(h1, h2, t) { return P ? P.mix(h1, h2, t) : h1; }
  function glow(gx, gy, r, col, a) {
    if (a <= 0) return;
    var n = parseInt(col.slice(1), 16), R = (n >> 16) & 255, G = (n >> 8) & 255, Bl = n & 255;
    c.globalCompositeOperation = "lighter";
    var g = c.createRadialGradient(gx, gy, 0, gx, gy, r);
    g.addColorStop(0, "rgba(" + R + "," + G + "," + Bl + "," + a + ")");
    g.addColorStop(1, "rgba(" + R + "," + G + "," + Bl + ",0)");
    c.fillStyle = g; c.fillRect(gx - r, gy - r, r * 2, r * 2);
    c.globalCompositeOperation = "source-over";
  }
  // tiny 3×5 pixel font for the sign
  var GLYPH = {
    "A": ["010", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"],
    "O": ["111", "101", "101", "101", "111"], "T": ["111", "010", "010", "010", "010"],
    " ": ["000", "000", "000", "000", "000"], "P": ["110", "101", "110", "100", "100"],
    "E": ["111", "100", "110", "100", "111"], "N": ["101", "111", "111", "111", "101"]
  };
  function textW(str, s) { return str.length * 4 * s - s; }
  function drawText(str, x, y, s, col) {
    str = String(str).toUpperCase();
    for (var i = 0; i < str.length; i++) {
      var g = GLYPH[str[i]] || GLYPH[" "];
      for (var r = 0; r < 5; r++) for (var k = 0; k < 3; k++)
        if (g[r][k] === "1") { c.fillStyle = col; c.fillRect(x + i * 4 * s + k * s, y + r * s, s, s); }
    }
  }

  var GROUND = 202;
  function drawShop(zoom, t) {
    var px = function (X, Y, W, H, col) { c.fillStyle = col; c.fillRect(X | 0, Y | 0, W | 0, H | 0); };
    var cx = LOW_W / 2, counterTop = 152;
    c.save();
    c.translate(cx, GROUND); c.scale(zoom, zoom); c.translate(-cx, -GROUND);

    // warm back wall + floor
    var wg = c.createLinearGradient(0, 0, 0, GROUND);
    wg.addColorStop(0, "#241a2a"); wg.addColorStop(1, "#33241f");
    c.fillStyle = wg; c.fillRect(-LOW_W, 0, LOW_W * 3, GROUND);
    px(-LOW_W, GROUND, LOW_W * 3, LOW_H, "#20161a");
    for (var fx = -LOW_W; fx < LOW_W * 2; fx += 20) px(fx, GROUND, 1, LOW_H - GROUND, "#180f14");

    // BOBA sign band
    px(-8, 12, LOW_W + 16, 18, mix("#cb9a6a", "#000", 0.35));
    px(-8, 12, LOW_W + 16, 2, mix("#cb9a6a", "#fff", 0.3));
    var word = "BOBA", s = 3, tw = textW(word, s);
    drawText(word, Math.round(cx - tw / 2), 15, s, "#f6ecd6");
    glow(cx, 21, tw, "#7fc48f", 0.10);

    // pendant lamp + warm pool
    px(cx - 1, 30, 2, 12, "#161018");
    px(cx - 8, 42, 16, 5, "#e8c060");
    glow(cx, 48, 74, "#ffcf8a", 0.15);

    // shelves of colorful boba cups across the back
    var cupCols = ["#e6d3b3", "#d8a86a", "#f0c8a0", "#cfe6d0", "#e6b8c8", "#d8c8e6"];
    for (var r = 0; r < 2; r++) {
      var sh = 58 + r * 30;
      px(20, sh + 18, LOW_W - 40, 3, "#4a3626");
      px(20, sh + 21, LOW_W - 40, 2, mix("#4a3626", "#000", 0.4));
      for (var i = 0; 26 + i * 15 < LOW_W - 26; i++) drawMiniCup(px, 26 + i * 15, sh, cupCols[(r * 3 + i) % cupCols.length]);
    }

    // a chilled fruit-tea fridge (teal) on the right
    px(LOW_W - 76, 56, 56, counterTop - 62, "#20303a");
    px(LOW_W - 72, 60, 48, counterTop - 70, "#2f5a6a");
    glow(LOW_W - 48, counterTop / 2 + 22, 30, "#7fe0ff", 0.10);
    for (var fr = 0; fr < 3; fr++) px(LOW_W - 68, 66 + fr * 22, 40, 3, "#173038");

    // the counter
    px(0, counterTop, LOW_W, GROUND - counterTop, "#5a3f2a");
    px(0, counterTop, LOW_W, 5, "#7a5636");
    px(0, counterTop + 5, LOW_W, 2, mix("#5a3f2a", "#000", 0.4));

    // a finished boba cup sitting on the counter (steam wisp)
    drawBigCup(px, 30, counterTop - 30);
    var steam = 0.5 + 0.5 * Math.sin(t / 620);
    glow(38, counterTop - 34, 8, "#fff", 0.05 + steam * 0.05);

    // the self-order TABLET on a stand, center — the hero of the scene
    var mx = cx - 26, my = counterTop - 52, mw = 52, mh = 40;
    px(cx - 3, counterTop - 12, 6, 12, "#2a2230");                 // stand
    px(mx - 3, my - 3, mw + 6, mh + 6, "#211a2c");                 // bezel
    px(mx, my, mw, mh, "#0c0a16");                                 // screen
    px(mx + 4, my + 5, mw - 8, 3, "#7fc48f");                      // screen content
    for (var ky = 0; ky < 3; ky++) px(mx + 4, my + 12 + ky * 7, mw - 8, 4, ky === 1 ? "#ffe08a" : "#3a3450");
    drawMiniCup(px, cx - 5, my + 10, "#e6d3b3");
    glow(cx, my + mh / 2, 40, "#a78bfa", 0.10 + 0.05 * Math.sin(t / 900));

    c.restore();
  }
  function drawMiniCup(px, x, y, col) {
    px(x, y, 7, 3, "#cbb58a");            // lid
    px(x, y + 3, 7, 11, col);             // cup
    px(x + 1, y + 10, 5, 3, "#3a2a1f");   // pearls
    px(x + 3, y - 2, 1, 3, "#e6d3b3");    // straw
  }
  function drawBigCup(px, x, y) {
    px(x, y, 14, 4, "#cbb58a");           // lid
    px(x, y + 4, 14, 22, "#e9dcc4");      // cup
    px(x + 2, y + 18, 10, 6, "#3a2a1f");  // pearls
    px(x + 6, y - 5, 2, 7, "#d8a86a");    // straw
  }

  // ── render loop: subtle idle + a one-shot dolly on entering the order ────────
  var cam = 0, camTo = 0, tStart = performance.now(), lastW = 0, lastH = 0;
  function frame(now) {
    var t = now - tStart;
    cam += (camTo - cam) * (reduced ? 1 : 0.06);
    resizeIfNeeded();
    c.clearRect(0, 0, LOW_W, LOW_H);
    drawShop(1 + cam * 0.22, reduced ? 0 : t);
    requestAnimationFrame(frame);
  }
  function resizeIfNeeded() {
    if (window.innerWidth !== lastW || window.innerHeight !== lastH) {
      lastW = window.innerWidth; lastH = window.innerHeight; resize();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  TABLET UI — build the controls, bind live recompute
  // ═══════════════════════════════════════════════════════════════════════════
  var cur = null;    // the live order state

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  function optRadio(group, id, checked, labelHTML) {
    var wrap = document.createElement("div");
    wrap.className = "opt";
    wrap.innerHTML =
      '<input type="radio" name="' + group + '" id="' + id + '"' + (checked ? " checked" : "") + ">" +
      '<label for="' + id + '">' + labelHTML + "</label>";
    return wrap;
  }
  function optCheck(id, labelHTML) {
    var wrap = document.createElement("div");
    wrap.className = "opt";
    wrap.innerHTML =
      '<input type="checkbox" id="' + id + '">' +
      '<label for="' + id + '">' + labelHTML + "</label>";
    return wrap;
  }

  function buildUI() {
    // DRINK (radios styled as cards) — default = matcha (a DRINK, not a topping)
    var gd = $("grp-drink"); gd.innerHTML = "";
    MENU.drinks.forEach(function (d, i) {
      var el = optRadio("drink", "drink-" + d.name, i === MENU.drinks.length - 1,
        '<span class="emo" aria-hidden="true">' + d.emo + '</span>' +
        '<span class="body"><span class="nm">' + esc(d.label) + '</span></span>' +
        '<span class="rt"><span class="price">' + money(d.price) + '</span><span class="tick" aria-hidden="true">✓</span></span>');
      el.querySelector("input").value = d.name;
      el.querySelector("input").setAttribute("aria-label", d.label + ", " + money(d.price));
      gd.appendChild(el);
    });

    // SIZE
    var gs = $("grp-size"); gs.innerHTML = "";
    gs.appendChild(sizeOpt("M", "Medium", "16 oz", true, "base"));
    gs.appendChild(sizeOpt("L", "Large", "24 oz", false, "+$0.75"));

    // SWEETNESS (free)
    var gw = $("grp-sweet"); gw.innerHTML = "";
    SWEETS.forEach(function (s, i) {
      var el = optRadio("sweet", "sweet-" + i, i === 2,
        '<span class="body"><span class="nm">' + s + '</span></span>');
      el.querySelector("input").value = s;
      el.querySelector("input").setAttribute("aria-label", s + " sweetness");
      gw.appendChild(el);
    });

    // ICE (free)
    var gi = $("grp-ice"); gi.innerHTML = "";
    ICES.forEach(function (s, i) {
      var el = optRadio("ice", "ice-" + i, i === 0,
        '<span class="body"><span class="nm">' + s + '</span></span>');
      el.querySelector("input").value = s;
      el.querySelector("input").setAttribute("aria-label", s + " ice");
      gi.appendChild(el);
    });

    // TOPPINGS — pearls FIRST when the fresh-batch salvage lever is live
    var note = $("pearl-note");
    if (salvageActive) {
      note.innerHTML = 'Today\'s <b>tapioca pearls</b> are a fresh batch near its sell-by, so the shop surfaces them first — enjoy them rather than see them binned. Priced at the menu like everything else; the real savings are the pickup and group levers below.';
    } else {
      note.textContent = "Add what you like.";
    }
    var order = MENU.tops.slice();
    if (salvageActive) order.sort(function (a, b) { return (b.name === MENU.batchTop ? 1 : 0) - (a.name === MENU.batchTop ? 1 : 0); });
    var gt = $("grp-tops"); gt.innerHTML = "";
    order.forEach(function (t) {
      var fresh = (t.name === MENU.batchTop && salvageActive)
        ? '<span class="fresh-badge" id="fresh-badge">fresh batch today</span>' : "";
      var el = optCheck("top-" + t.name,
        '<span class="emo" aria-hidden="true">' + t.emo + '</span>' +
        '<span class="body"><span class="nm">' + esc(t.label) + '</span>' + fresh + '</span>' +
        '<span class="rt"><span class="price">+' + money(t.price) + '</span></span>');
      el.querySelector("input").value = t.name;
      el.querySelector("input").setAttribute("aria-label", "Add " + t.label + ", plus " + money(t.price));
      gt.appendChild(el);
    });

    // PICKUP (lever ★)
    var gp = $("grp-pickup"); gp.innerHTML = "";
    SLOTS.forEach(function (sl, i) {
      var el = optRadio("pickup", "pickup-" + sl.ticks, i === 0,
        '<span class="body"><span class="nm">' + esc(sl.label) + '</span><span class="meta">' + esc(sl.meta) + '</span></span>' +
        '<span class="rt"><span class="save-chip zero" id="chip-slot-' + sl.ticks + '">—</span></span>');
      el.querySelector("input").value = String(sl.ticks);
      el.querySelector("input").setAttribute("aria-label", "Pickup " + sl.label);
      gp.appendChild(el);
    });

    // QUANTITY (lever)
    var gq = $("grp-qty"); gq.innerHTML = "";
    QTYS.forEach(function (q, i) {
      var el = optRadio("qty", "qty-" + q.n, i === 0,
        '<span class="emo" aria-hidden="true">' + q.emo + '</span>' +
        '<span class="body"><span class="nm">' + esc(q.label) + '</span><span class="meta">' + esc(q.meta) + '</span></span>' +
        '<span class="rt"><span class="save-chip zero" id="chip-qty-' + q.n + '">—</span></span>');
      el.querySelector("input").value = String(q.n);
      el.querySelector("input").setAttribute("aria-label", q.label + ", " + q.n + (q.n === 1 ? " cup" : " cups"));
      gq.appendChild(el);
    });

    $("tablet").addEventListener("change", readAndRecompute);
    readState();
  }
  function sizeOpt(val, nm, oz, checked, priceTxt) {
    var el = optRadio("size", "size-" + val, checked,
      '<span class="body"><span class="nm">' + nm + '</span><span class="meta">' + oz + '</span></span>' +
      '<span class="rt"><span class="price' + (val === "M" ? " free" : "") + '">' + priceTxt + '</span></span>');
    el.querySelector("input").value = val;
    el.querySelector("input").setAttribute("aria-label", nm + " " + oz + (val === "L" ? ", plus $0.75" : ", base price"));
    return el;
  }

  function readState() {
    var g = function (name) { var el = document.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : null; };
    var tops = [];
    document.querySelectorAll('#grp-tops input:checked').forEach(function (i) { tops.push(i.value); });
    cur = {
      drink: g("drink") || MENU.drinks[MENU.drinks.length - 1].name,
      size: g("size") || "M",
      sizeUp: (g("size") === "L") ? SIZE_UP_L : 0,
      sweet: g("sweet") || "50%",
      ice: g("ice") || "Regular",
      tops: tops,
      slotTicks: parseInt(g("pickup") || "0", 10),
      qty: parseInt(g("qty") || "1", 10),
    };
  }
  function readAndRecompute() { readState(); recompute(); }

  // ── the live recompute: total + every lever's real saving ────────────────────
  function recompute() {
    if (!engineOk) return;
    var now = priceOrder(cur);

    // total
    $("pay").textContent = money(now.pay);
    if (now.save > 0.005) {
      $("menu-was").innerHTML = 'menu <s>' + money(now.menu) + '</s>';
      $("saved").textContent = "you save " + money(now.save);
    } else {
      $("menu-was").textContent = "the menu price";
      $("saved").textContent = "";
    }

    // PICKUP chips — saving vs picking up Now, holding the rest of the cart fixed
    var nowSlot = priceOrder(Object.assign({}, cur, { slotTicks: 0 }));
    SLOTS.forEach(function (sl) {
      var chip = $("chip-slot-" + sl.ticks);
      if (!chip) return;
      if (sl.ticks === 0) { setChip(chip, 0, "menu price"); return; }
      var alt = priceOrder(Object.assign({}, cur, { slotTicks: sl.ticks }));
      setChip(chip, round2(nowSlot.pay - alt.pay), null);
    });

    // QUANTITY chips — real saving on the EXTRA cups (not "spend less")
    var one = priceOrder(Object.assign({}, cur, { qty: 1 }));
    var pcm = perCupMenu(Object.assign({}, cur, { qty: 1 }));
    QTYS.forEach(function (q) {
      var chip = $("chip-qty-" + q.n);
      if (!chip) return;
      if (q.n === 1) { setChip(chip, 0, "—"); return; }
      var alt = priceOrder(Object.assign({}, cur, { qty: q.n }));
      var extraMenu = (q.n - 1) * pcm;
      var extraPaid = round2(alt.pay - one.pay);
      setChip(chip, round2(extraMenu - extraPaid), null, "off the extra cups");
    });

    // PEARLS fresh-batch badge — real live saving on the pearls
    updatePearlBadge();
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

  function updatePearlBadge() {
    // The pearls are a genuine fresh over-stock (salvageActive is the engine's real
    // pearlsExpiringExcess flag), so we surface them first. But we do NOT attach a
    // dollar to the badge: on this high-margin menu with min_price_frac=0.6 the
    // salvage lever's real effect on the buyer's price is ~$0 — the negotiated price
    // is identical whether the pearls' cost is salvaged or not (the 60%-of-menu
    // floor binds, not the $0.10 pearl cost). The apparent "pearl discount" is just
    // the pickup/quantity levers discounting the whole cart; crediting it to the
    // fresh batch would misattribute a saving the salvage lever did not produce.
    var badge = $("fresh-badge");
    if (!badge || !salvageActive) return;
    badge.textContent = "fresh batch today";
  }
  function withTop(tops, t) { return tops.indexOf(t) >= 0 ? tops.slice() : tops.concat([t]); }
  function withoutTop(tops, t) { return tops.filter(function (x) { return x !== t; }); }

  // ═══════════════════════════════════════════════════════════════════════════
  //  RECEIPT
  // ═══════════════════════════════════════════════════════════════════════════
  function buildReceipt() {
    var now = priceOrder(cur);
    var nowSlot = priceOrder(Object.assign({}, cur, { slotTicks: 0 }));
    var pickupSave = round2(nowSlot.pay - now.pay);

    // order summary
    var topNames = cur.tops.map(function (t) { return TOP_LABEL[t]; });
    var slot = SLOTS.filter(function (s) { return s.ticks === cur.slotTicks; })[0];
    var summary =
      '<div><span class="oq">' + cur.qty + " × " + esc(DRINK_LABEL[cur.drink]) +
      '</span> <span class="om">(' + (cur.size === "L" ? "Large" : "Medium") + ")</span></div>" +
      '<div class="om">' + esc(cur.sweet) + " sweet · " + esc(cur.ice.toLowerCase()) + " ice" +
      (topNames.length ? " · " + topNames.map(esc).join(", ") : "") + "</div>" +
      '<div class="om">pickup: ' + esc(slot ? slot.label.toLowerCase() : "now") + "</div>";
    $("r-order").innerHTML = summary;

    // menu vs paid
    var lines =
      '<div class="r-line"><span class="rl-n">Menu price</span>' +
      '<span class="rl-p"><s>' + money(now.menu) + "</s></span></div>" +
      '<div class="r-line"><span class="rl-n">Your price</span>' +
      '<span class="rl-p"><b>' + money(now.pay) + "</b></span></div>";
    $("r-lines").innerHTML = lines;

    $("r-saved").textContent = money(now.save);
    var pct = now.menu > 0 ? Math.round((now.save / now.menu) * 100) : 0;
    $("r-pct").textContent = now.save > 0.005
      ? pct + "% off the menu · you paid " + money(now.pay)
      : "exactly the menu — no lever pulled yet";

    // why it's below the menu — only the levers that actually applied, described
    // honestly (no fake per-lever dollar split of a jointly-priced deal)
    var why = [];
    if (cur.slotTicks > 0 && pickupSave > 0.005)
      why.push("A later, off-peak pickup freed the lunch rush — <b>" + money(pickupSave) + " vs. picking up now</b>.");
    if (cur.tops.indexOf(MENU.batchTop) >= 0 && salvageActive)
      why.push("Today\'s tapioca pearls came from a fresh batch near its sell-by — surfaced first so they\'re enjoyed, not binned (priced at the menu, like every topping).");
    if (cur.qty > 1)
      why.push("Your " + cur.qty + " cups go in as one group order, so your agent settles each cup further under the menu.");
    if (!why.length)
      why.push("You\'re at the menu price — pick a later pickup or add a cup to see it drop.");
    $("r-why").innerHTML = "<b>Why it’s a fair price:</b> " + why.join(" ") +
      " Your price is <b>never above the menu</b>, and every one of these is win-win.";

    $("r-repro").textContent =
      "Every price computed live by the SNHP boba engine (boba-engine.js · the cart_nash port) at these menu prices — nothing scripted.";
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT TRANSITIONS
  // ═══════════════════════════════════════════════════════════════════════════
  function setKicker(html) { $("kicker").innerHTML = html; }

  function enterSplash() {
    $("splash").classList.remove("hidden");
    $("tablet").classList.add("hidden");
    $("receipt").classList.add("hidden");
    $("stage").classList.remove("ordering");
    $("kicker").classList.add("hidden");   // the splash H1 carries the message; avoid the sign overlap
    camTo = 0;
  }
  function enterOrder() {
    $("splash").classList.add("hidden");
    $("receipt").classList.add("hidden");
    $("tablet").classList.remove("hidden");
    $("stage").classList.add("ordering");
    $("kicker").classList.remove("hidden");
    setKicker("At the tablet — <b>each lever ticks the price down</b>");
    camTo = 1;
    recompute();
    var sc = $("t-scroll"); if (sc) sc.scrollTop = 0;
  }
  function enterReceipt() {
    buildReceipt();
    $("kicker").classList.remove("hidden");
    $("tablet").classList.add("hidden");
    var rc = $("receipt");
    rc.classList.remove("hidden");
    if (!reduced) { rc.classList.remove("printing"); void rc.offsetWidth; rc.classList.add("printing"); }
    setKicker("Your receipt — <b>you saved " + money(priceOrder(cur).save) + "</b>");
    var again = $("r-again"); if (again && again.focus) { try { again.focus({ preventScroll: true }); } catch (e) {} }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  BOOT
  // ═══════════════════════════════════════════════════════════════════════════
  function fillCaveat() {
    $("caveat").innerHTML = "<b>Every price is real.</b> Computed live by the SNHP boba engine for the exact order you build — never above the menu.";
  }

  function boot() {
    resize(); lastW = window.innerWidth; lastH = window.innerHeight;
    requestAnimationFrame(frame);
    try { buildEngine(); }
    catch (e) {
      $("err").textContent = "Could not start the boba engine — " + (e && e.message || e);
      console.error(e); return;
    }
    fillCaveat();
    buildUI();
    enterSplash();

    // tap anywhere on the splash, or the focusable button (keyboard: Enter/Space)
    $("splash").addEventListener("click", enterOrder);
    $("place").addEventListener("click", enterReceipt);
    $("r-again").addEventListener("click", enterOrder);
  }

  if (!B || !B.priceCart) {
    $("err").textContent = "boba-engine.js failed to load (window.BobaEngine.priceCart missing).";
    return;
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

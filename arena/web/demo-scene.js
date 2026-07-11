/* SNHP DEMO — the immersive bodega. A first-person pixel-art walk into a corner
   store where the silent negotiation is made visible, in four acts on one screen:

     ACT 1  THE DOOR    — 3 posters on the door; answer one, it rips off,
                          revealing the next. The 3 real onboarding questions.
     ACT 2  WALK IN     — the door opens, a short dolly carries you inside and
                          grabs the cart into a basket, arriving at the register.
     ACT 3  THE REGISTER— each item shows its sticker price, then counts DOWN to
                          the price the agent negotiated for you.
     ACT 4  THE RECEIPT — a receipt prints: per-item savings, the total, links.

   HONESTY: every question, price and saving is read from demo-trace.json
   (scenarios.hero), a recorded run of buyer/preflearn.py. Nothing is hardcoded.
   This file only choreographs pixels/time and binds the DOM overlays to the data.

   The scene is a low-res backbuffer (LOW_H tall, width follows the viewport) that
   integer-upscales crisp — same technique as arena/web/block/scene.js. Colors
   come from arena/web/block/palette.js (Block.pal). */
(function () {
  "use strict";

  var P = (window.Block && window.Block.pal) || null;

  // ── TUNE — timings (ms) & layout. // POLISH: this is the knob board. ────────
  var TUNE = {
    posterRip:   560,   // poster peel-away
    doorOpen:    850,   // ACT 2 · door swings open
    dolly:      1700,   // ACT 2 · walk-in camera push (after the door opens)
    basketFrom:  0.30,  // walk-in progress at which items start dropping in
    countItem:   950,   // ACT 3 · one price's countdown
    countGap:    320,   // ACT 3 · gap between items
    receiptHold: 260,   // ACT 4 · beat before the receipt prints
  };

  // backbuffer geometry (see drawStreet / drawInside)
  var LOW_H = 240;
  var GROUND = 202;                 // sidewalk / floor top
  var DOOR = { w: 92, top: 104 };   // door leaf, centered; x set per-frame
  var REG_TOP_BB = 64;              // where the register readout floats (bb-y)
  var RCPT_TOP_BB = 54;             // where the receipt prints from (bb-y)

  var reduced = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── DOM refs ────────────────────────────────────────────────────────────────
  var $ = function (id) { return document.getElementById(id); };
  var view = $("view"), c = view.getContext("2d");
  c.imageSmoothingEnabled = false;

  // ── canvas plumbing (aspect follows viewport → fills the screen) ─────────────
  var LOW_W = 420, scale = 2, canvasLeft = 0, canvasTop = 0, dispW = 420, dispH = 240;
  function resize() {
    var availW = window.innerWidth, availH = window.innerHeight;
    LOW_W = Math.max(300, Math.min(680, Math.round(LOW_H * (availW / availH))));
    view.width = LOW_W; view.height = LOW_H; c.imageSmoothingEnabled = false;
    // "cover" (fill the viewport, crop overflow) so the POV is immersive with no
    // letterbox on tall/portrait screens — the door stays centered either way.
    // On aspect-matching viewports this equals "contain" (both ratios coincide).
    scale = Math.max(availW / LOW_W, availH / LOW_H);
    dispW = Math.round(LOW_W * scale); dispH = Math.round(LOW_H * scale);
    view.style.width = dispW + "px"; view.style.height = dispH + "px";
    canvasLeft = (availW - dispW) / 2; canvasTop = (availH - dispH) / 2;
    layout();
  }
  window.addEventListener("resize", resize);
  function sx(bx) { return canvasLeft + bx * scale; }   // backbuffer → screen
  function sy(by) { return canvasTop + by * scale; }
  function doorX() { return Math.round((LOW_W - DOOR.w) / 2); }

  // ── math helpers ────────────────────────────────────────────────────────────
  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function smooth(a, b, x) { var t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }
  function mix(h1, h2, t) { return P ? P.mix(h1, h2, t) : h1; }
  function money(x) { return x == null ? "—" : "$" + Number(x).toFixed(2); }

  // additive glow stamp (backbuffer coords) — borrowed from block/scene.js
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

  // ── a tiny 3×5 pixel font (uppercase + digits) for signage ──────────────────
  // POLISH: N/G/S are stylized at 3px; good enough for a sign, tweak if you like.
  var GLYPH = {
    "A": ["010", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"], "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"], "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"], "I": ["111", "010", "010", "010", "111"],
    "L": ["100", "100", "100", "100", "111"], "N": ["101", "111", "111", "111", "101"],
    "O": ["111", "101", "101", "101", "111"], "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"], "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"], "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"], "W": ["101", "101", "101", "111", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "011", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    " ": ["000", "000", "000", "000", "000"], ".": ["000", "000", "000", "000", "010"]
  };
  function textW(str, s) { return str.length * 4 * s - s; }
  function drawText(str, x, y, s, col) {
    str = String(str).toUpperCase();
    for (var i = 0; i < str.length; i++) {
      var g = GLYPH[str[i]] || GLYPH[" "];
      for (var r = 0; r < 5; r++) for (var k = 0; k < 3; k++) {
        if (g[r][k] === "1") { c.fillStyle = col; c.fillRect(x + i * 4 * s + k * s, y + r * s, s, s); }
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 1 + 2 · the STREET (storefront + the door that opens)
  // ═══════════════════════════════════════════════════════════════════════════
  function drawStreet(zoom, doorOpen) {
    var V = P ? P.VENUE.deli : { a: "#d8a020", b: "#b83a34", glow: "#5ad06a", trim: "#e8c060" };
    var px = function (X, Y, W, H, col) { c.fillStyle = col; c.fillRect(X | 0, Y | 0, W | 0, H | 0); };
    var dx = doorX(), dcx = LOW_W / 2, dcy = (DOOR.top + GROUND) / 2;

    c.save();
    // zoom toward the door center as we walk in
    c.translate(dcx, dcy); c.scale(zoom, zoom); c.translate(-dcx, -dcy);

    // ── sky (dusk) + sidewalk ──
    var sky = P ? P.skyAt(19.0) : { top: "#2a2746", hor: "#864e5c" };
    var sg = c.createLinearGradient(0, 0, 0, GROUND);
    sg.addColorStop(0, sky.top); sg.addColorStop(1, sky.hor);
    c.fillStyle = sg; c.fillRect(-LOW_W, 0, LOW_W * 3, GROUND);
    px(-LOW_W, GROUND, LOW_W * 3, LOW_H - GROUND + 40, "#3a3648");           // sidewalk
    px(-LOW_W, GROUND, LOW_W * 3, 2, "#4a4658");
    for (var tx = -LOW_W; tx < LOW_W * 2; tx += 22) px(tx, GROUND, 1, LOW_H - GROUND, "#2c2a38");

    // ── brick façade ──
    var wall = "#6a4038";
    px(-8, 6, LOW_W + 16, GROUND - 6, wall);
    px(-8, 6, LOW_W + 16, 4, mix(wall, "#000", 0.4));                        // cornice
    for (var by = 12; by < 40; by += 4) px(-8, by, LOW_W + 16, 1, mix(wall, "#000", 0.2));
    // upper windows (warm-lit, cozy)
    for (var wi = 0; wi < Math.ceil(LOW_W / 70); wi++) {
      var wx = 16 + wi * 70;
      px(wx, 14, 22, 20, "#1c1a26"); px(wx + 2, 16, 18, 16, "#ffdf9a");
      px(wx + 11, 14, 1, 20, "#141220"); px(wx, 23, 22, 1, "#141220");
      glow(wx + 11, 24, 12, "#ffcf8a", 0.10);
    }

    // ── sign band + "BODEGA" ──
    var signY = 42;
    px(-8, signY, LOW_W + 16, 16, mix(V.a, "#000", 0.3));
    px(-8, signY, LOW_W + 16, 2, mix(V.a, "#fff", 0.25));
    var word = "BODEGA", s = 2, tw = textW(word, s);
    drawText(word, Math.round(dcx - tw / 2), signY + 3, s, "#fff3d0");
    glow(dcx, signY + 8, tw, V.glow, 0.10);

    // ── scalloped awning ──
    var awnY = signY + 16;
    for (var ax = -8; ax < LOW_W + 8; ax += 12) {
      var stripe = ((ax / 12) | 0) % 2 === 0 ? V.a : V.b;
      px(ax, awnY, 12, 8, stripe); px(ax, awnY + 8, 12, 3, mix(stripe, "#000", 0.25));
    }
    px(-8, awnY, LOW_W + 16, 2, "#f4e6c4");

    // ── flanking shop windows (cans on shelves + green OPEN neon) ──
    var winTop = awnY + 16, winBot = GROUND - 4;
    drawWindow(px, 8, winTop, dx - 16, winBot);                              // left
    drawWindow(px, dx + DOOR.w + 8, winTop, LOW_W - (dx + DOOR.w + 8) - 8, winBot); // right

    // ── the door (with posters removed → we see through when it opens) ──
    drawDoor(px, dx, doorOpen);

    c.restore();
  }

  function drawWindow(px, x, top, w, bot) {
    if (w < 20) return;
    px(x - 2, top - 2, w + 4, bot - top + 4, "#3a2e28");                     // frame
    px(x, top, w, bot - top, "#171a24");                                     // glass recess
    px(x + 1, top + 1, w - 2, bot - top - 2, "#3a2c22");                     // warm interior
    // shelves of cans
    var cans = ["#c0503a", "#d8a020", "#4a8a5a", "#c8c0b0", "#6a8ac0", "#c85030"];
    for (var r = 0; r < 3; r++) {
      var sh = top + 6 + r * 12;
      px(x + 2, sh + 6, w - 4, 2, "#5a4a3a");
      for (var i = 0; i * 7 < w - 8; i++) px(x + 4 + i * 7, sh, 4, 6, cans[(r * 3 + i) % cans.length]);
    }
    // green OPEN neon at the bottom of the left-ish window
    if (w > 40) {
      var ox = x + 4, oy = bot - 9;
      drawText("OPEN", ox, oy, 1, "#8ff0a0");
      glow(ox + textW("OPEN", 1) / 2, oy + 3, 16, "#5ad06a", 0.24);
    }
  }

  function drawDoor(px, dx, doorOpen) {
    var top = DOOR.top, w = DOOR.w, bot = GROUND;
    // doorway: warm interior glimpsed behind the leaf
    px(dx - 3, top - 3, w + 6, bot - top + 3, "#2a1e1a");                    // frame
    px(dx, top, w, bot - top, "#2a2032");                                    // dark threshold
    // warm spill grows as the door opens
    glow(dx + w / 2, bot - 24, 30 + doorOpen * 40, "#ffcf8a", 0.10 + doorOpen * 0.30);
    if (doorOpen > 0.02) {
      var inW = Math.round(w * clamp01(doorOpen * 0.9));
      px(dx + 2, top + 2, inW, bot - top - 2, mix("#3a2a1e", "#5a3a22", doorOpen));  // interior wash
    }
    // the leaf, hinged left, swinging inward (its width collapses as it opens)
    var leafW = Math.max(2, Math.round(w * (1 - doorOpen)));
    px(dx, top, leafW, bot - top, "#3a3040");
    px(dx, top, Math.min(3, leafW), bot - top, "#4a4055");                   // lit hinge edge
    if (leafW > 10) {
      px(dx + 3, top + 4, leafW - 6, 26, "#8ab0c0");                         // upper glass
      px(dx + 3, top + 4, leafW - 6, 3, "#b8d8e0");
      px(dx + leafW - 4, top + (bot - top) / 2, 2, 3, "#ffe08a");           // handle
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 2 (tail) + 3 + 4 · the INTERIOR (shelves, counter, register)
  // ═══════════════════════════════════════════════════════════════════════════
  function drawInside(zoom, basketFill) {
    var px = function (X, Y, W, H, col) { c.fillStyle = col; c.fillRect(X | 0, Y | 0, W | 0, H | 0); };
    var cx = LOW_W / 2, counterTop = 150;

    c.save();
    c.translate(cx, GROUND); c.scale(zoom, zoom); c.translate(-cx, -GROUND);

    // ── warm back wall + floor ──
    var wg = c.createLinearGradient(0, 0, 0, GROUND);
    wg.addColorStop(0, "#2a2030"); wg.addColorStop(1, "#3a2a22");
    c.fillStyle = wg; c.fillRect(-LOW_W, 0, LOW_W * 3, GROUND);
    px(-LOW_W, GROUND, LOW_W * 3, LOW_H, "#241a1e");                          // floor
    for (var fx = -LOW_W; fx < LOW_W * 2; fx += 20) px(fx, GROUND, 1, LOW_H - GROUND, "#1c1418");

    // ── pendant lamp + warm pool ──
    px(cx - 1, 6, 2, 14, "#1a1620");
    px(cx - 7, 20, 14, 5, "#e8c060");
    glow(cx, 26, 70, "#ffcf8a", 0.16);

    // ── shelves of colorful product across the back ──
    var cans = ["#c0503a", "#d8a020", "#4a8a5a", "#c8c0b0", "#6a8ac0", "#c85030", "#8a5ac0", "#5ad06a"];
    for (var r = 0; r < 3; r++) {
      var sh = 40 + r * 24;
      px(20, sh + 12, LOW_W - 40, 3, "#4a3626");                             // shelf board
      px(20, sh + 15, LOW_W - 40, 2, mix("#4a3626", "#000", 0.4));
      for (var i = 0; 24 + i * 11 < LOW_W - 24; i++) {
        var col = cans[(r * 5 + i) % cans.length];
        px(24 + i * 11, sh, 7, 12, col);
        px(24 + i * 11, sh, 7, 3, mix(col, "#fff", 0.3));
      }
    }

    // a chilled fridge with a teal-glass door on the right
    px(LOW_W - 74, 34, 54, counterTop - 40, "#20303a");
    px(LOW_W - 70, 38, 46, counterTop - 48, "#2f5a6a");
    glow(LOW_W - 47, counterTop / 2 + 6, 34, "#7fe0ff", 0.10);
    for (var fr = 0; fr < 4; fr++) px(LOW_W - 66, 44 + fr * 20, 38, 3, "#173038");

    // ── the counter ──
    px(0, counterTop, LOW_W, GROUND - counterTop, "#5a3f2a");                 // counter body
    px(0, counterTop, LOW_W, 5, "#7a5636");                                   // lit top edge
    px(0, counterTop + 5, LOW_W, 2, mix("#5a3f2a", "#000", 0.4));

    // basket on the counter (fills during the walk-in)
    drawBasket(px, 26, counterTop - 4, basketFill);

    // the register machine, center on the counter
    var mx = cx - 20, my = counterTop - 30;
    px(mx, my, 40, 30, "#3a3442");                                           // body
    px(mx, my, 40, 3, "#4a4456");
    px(mx + 4, my + 4, 32, 11, "#101418");                                   // display
    px(mx + 5, my + 5, 30, 9, "#1a3a2a");                                    // greenish LCD
    drawText("SNHP", mx + 8, my + 7, 1, "#8ff0a0");
    for (var ky = 0; ky < 2; ky++) for (var kx = 0; kx < 5; kx++)            // keypad
      px(mx + 5 + kx * 6, my + 18 + ky * 5, 4, 3, "#55506a");
    px(mx + 10, my - 5, 20, 5, "#20202a");                                    // receipt slot
    px(mx + 12, my - 4, 16, 2, "#e8ddc4");                                    // paper lip

    c.restore();
  }

  function drawBasket(px, x, y, fill) {
    px(x, y, 30, 16, "#6a4a2a");                                             // basket
    px(x, y, 30, 3, "#8a6438");
    for (var s = 0; s < 30; s += 5) px(x + s, y, 2, 16, mix("#6a4a2a", "#000", 0.3));
    // items rise as fill grows (0..1 → up to 3 items)
    var n = Math.round(clamp01(fill) * 3);
    if (n >= 1) drawSandwich(px, x + 3, y - 5);
    if (n >= 2) drawCan(px, x + 14, y - 7);
    if (n >= 3) drawCup(px, x + 22, y - 6);
  }
  function drawSandwich(px, x, y) {
    px(x, y + 3, 9, 4, "#e8c878"); px(x, y + 2, 9, 2, "#f0d890");           // bread top
    px(x, y + 5, 9, 2, mix("#e8c878", "#000", 0.2));                         // bread bottom
    px(x + 1, y + 4, 7, 1, "#5aa05a"); px(x + 1, y + 4, 3, 1, "#c04a3a");    // lettuce/tomato
  }
  function drawCan(px, x, y) {
    px(x, y, 5, 9, "#c8ccd4"); px(x, y, 5, 2, "#a8acb4");                     // silver can
    px(x, y + 3, 5, 3, "#4a7ac0"); px(x, y, 5, 1, "#e0e4ea");                 // diet-blue band
  }
  function drawCup(px, x, y) {
    px(x, y, 6, 8, "#d8e8ea"); px(x, y, 6, 2, "#c04a7a");                     // clear cup + lid
    px(x + 1, y + 3, 4, 4, "#e06a3a"); px(x + 1, y + 4, 2, 2, "#f0a040");     // fruit
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  STATE + RENDER LOOP
  // ═══════════════════════════════════════════════════════════════════════════
  var S = {
    trace: null, hero: null, act: 0, epoch: 0,
    cam: 0, door: 0, basket: 0,           // walk-in interpolants
    walkStart: 0, walking: false,
    countDone: false
  };

  function frame() {
    c.clearRect(0, 0, LOW_W, LOW_H);
    // walk-in progression (ACT 2)
    if (S.walking) {
      var el = performance.now() - S.walkStart;
      S.door = clamp01(el / TUNE.doorOpen);
      var dz = clamp01((el - TUNE.doorOpen * 0.5) / TUNE.dolly);
      S.cam = dz;
      S.basket = clamp01((dz - TUNE.basketFrom) / (1 - TUNE.basketFrom));
      if (dz >= 1) { S.walking = false; onWalkArrived(); }
    }

    if (S.act <= 1) {
      // ACT 1 (door) or ACT 2 (walk-in): street zooms in + fades to interior
      var storeAlpha = 1 - smooth(0.35, 0.9, S.cam);
      var insideAlpha = smooth(0.28, 0.95, S.cam);
      if (insideAlpha > 0) { c.globalAlpha = insideAlpha; drawInside(0.7 + S.cam * 0.3, S.basket); c.globalAlpha = 1; }
      if (storeAlpha > 0) { c.globalAlpha = storeAlpha; drawStreet(1 + S.cam * 2.4, S.door); c.globalAlpha = 1; }
    } else {
      // ACT 3 / 4: interior, settled
      drawInside(1, S.basket);
    }
    requestAnimationFrame(frame);
  }

  // ── generic rAF tween with epoch cancel + reduced-motion jump ───────────────
  function tween(from, to, dur, onUpdate, onDone) {
    var ep = S.epoch;
    if (reduced || dur <= 0) { onUpdate(to); if (onDone) onDone(); return; }
    var t0 = performance.now();
    (function step() {
      if (ep !== S.epoch) return;
      var p = clamp01((performance.now() - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);               // easeOutCubic
      onUpdate(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step); else if (onDone) onDone();
    })();
  }
  function wait(ms, fn) {
    var ep = S.epoch;
    setTimeout(function () { if (ep === S.epoch) fn(); }, reduced ? 0 : ms);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  OVERLAY LAYOUT (positions DOM over canvas features)
  // ═══════════════════════════════════════════════════════════════════════════
  function layout() {
    var posters = $("posters");
    posters.style.left = "0"; posters.style.right = "0";
    posters.style.top = sy(DOOR.top - 4) + "px";
    var reg = $("register"); reg.style.left = "50%"; reg.style.top = sy(REG_TOP_BB) + "px";
    var rc = $("receipt"); rc.style.left = "50%"; rc.style.top = sy(RCPT_TOP_BB) + "px";
  }

  // ── UI helpers ──────────────────────────────────────────────────────────────
  function setKicker(html) { $("kicker").innerHTML = html; }
  function setHint(text) {
    var h = $("hint");
    if (!text) { h.classList.remove("show"); return; }
    h.textContent = text; h.classList.remove("hidden"); h.classList.add("show");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 1 · the door + posters
  // ═══════════════════════════════════════════════════════════════════════════
  function enterAct1() {
    S.act = 0; S.cam = 0; S.door = 0; S.basket = 0; S.walking = false; S.countDone = false;
    $("register").classList.add("hidden"); $("register").classList.remove("show");
    $("receipt").classList.add("hidden");
    $("replay").classList.remove("show");
    setKicker("Three posters on the door — <b>answer to walk in</b>");
    buildPosters();
    setHint("tap an answer — the poster peels off");
    layout();
  }

  function buildPosters() {
    var wrap = $("posters"); wrap.innerHTML = ""; wrap.classList.remove("hidden");
    var qs = S.hero.onboarding;
    S.posterEls = [];
    // build bottom→top so poster[0] sits on top (highest z, first answered).
    // Only the top (current) poster is visible; the next is revealed the instant
    // the top starts to peel, so it appears "underneath."
    for (var i = qs.length - 1; i >= 0; i--) {
      var q = qs[i];
      var el = document.createElement("div");
      el.className = "poster";
      el.style.zIndex = String(10 + (qs.length - i));
      el.style.setProperty("--tilt", (i % 2 === 0 ? -1.4 : 1.1) + "deg");
      if (i !== 0) el.style.visibility = "hidden";
      var stack = q.options.length === 2 && q.options.some(function (o) { return /worth|nah/i.test(o.label); });
      var opts = q.options.map(function (o) {
        return '<button class="p-opt" data-id="' + o.id + '">' + esc(o.label) + "</button>";
      }).join("");
      el.innerHTML =
        '<div class="p-num"><span>question ' + q.step + " / " + qs.length + "</span>" +
        '<span class="pin">●</span></div>' +
        '<div class="p-prompt">' + esc(q.prompt) + "</div>" +
        '<div class="p-opts' + (stack ? " stack" : "") + '">' + opts + "</div>";
      (function (el, i) {
        el.querySelectorAll(".p-opt").forEach(function (b) {
          b.addEventListener("click", function (ev) { ev.stopPropagation(); answerPoster(el, i); });
        });
      })(el, i);
      S.posterEls[i] = el;
      wrap.appendChild(el);
    }
  }

  function answerPoster(el, idx) {
    if (el.dataset.done) return;
    el.dataset.done = "1";
    setHint(null);
    // reveal the next poster underneath as this one peels
    var nxt = S.posterEls[idx + 1];
    if (nxt) nxt.style.visibility = "visible";
    if (reduced) { el.style.display = "none"; afterRip(idx); return; }
    el.classList.add("ripping");
    el.querySelectorAll(".p-opt").forEach(function (b) { b.disabled = true; });
    wait(TUNE.posterRip, function () { el.style.display = "none"; afterRip(idx); });
  }
  function afterRip(idx) {
    if (idx >= S.hero.onboarding.length - 1) {
      $("posters").classList.add("hidden");
      enterAct2();
    } else {
      setHint("tap an answer — the poster peels off");
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 2 · walk in
  // ═══════════════════════════════════════════════════════════════════════════
  function enterAct2() {
    S.act = 1;
    setKicker("The door opens — <b>walking in…</b>");
    setHint("tap to skip");
    if (reduced) { S.door = 1; S.cam = 1; S.basket = 1; onWalkArrived(); return; }
    S.epoch++;                       // fresh timeline
    S.walkStart = performance.now(); S.walking = true;
  }
  function skipWalk() {
    if (!S.walking && S.act === 1) return;
    S.walking = false; S.door = 1; S.cam = 1; S.basket = 1; onWalkArrived();
  }
  function onWalkArrived() {
    if (S.act !== 1) return;
    S.act = 2; S.cam = 1; S.basket = 1;
    setHint(null);
    enterAct3();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 3 · the register — sticker → your price, counting down
  // ═══════════════════════════════════════════════════════════════════════════
  function enterAct3() {
    S.act = 2; S.countDone = false;
    setKicker("At the register — <b>watch each price fall</b>");
    buildRegister();
    var reg = $("register"); reg.classList.remove("hidden");
    requestAnimationFrame(function () { reg.classList.add("show"); });
    S.epoch++;
    var items = S.hero.items, i = 0, runningYour = 0;
    function next() {
      if (i >= items.length) { finishRegister(runningYour); return; }
      var it = items[i], row = $("reg-row-" + i);
      var nowEl = row.querySelector(".now"), stk = row.querySelector(".sticker");
      stk.classList.add("struck");
      tween(it.list, it.your_price, TUNE.countItem, function (v) {
        nowEl.textContent = money(v);
      }, function () {
        nowEl.textContent = money(it.your_price);
        row.classList.add("settled");
        row.querySelector(".chip").textContent = "saved " + money(it.saved_vs_list);
        runningYour += it.your_price;
        $("reg-your").textContent = money(runningYour);
        i++; wait(TUNE.countGap, next);
      });
    }
    wait(reduced ? 0 : 340, next);
  }

  function buildRegister() {
    var rows = $("reg-rows"); rows.innerHTML = "";
    S.hero.items.forEach(function (it, i) {
      var row = document.createElement("div");
      row.className = "reg-row"; row.id = "reg-row-" + i;
      row.innerHTML =
        '<div><div class="rn">' + esc(it.pretty) + "</div>" +
        '<div class="rs">sticker price</div></div>' +
        '<div class="rp"><div class="sticker">' + money(it.list) + "</div>" +
        '<div class="now">' + money(it.list) + "</div>" +
        '<div class="chip"></div></div>';
      rows.appendChild(row);
    });
    $("reg-your").textContent = money(0);
    $("reg-sub").textContent = "sticker was " + money(S.hero.totals.list_total);
  }

  function finishRegister(runningYour) {
    var t = S.hero.totals;
    $("reg-your").textContent = money(t.your_total);
    $("reg-sub").innerHTML = "sticker " + money(t.list_total) +
      " · <span style='color:var(--gold)'>saved " + money(t.saved_total) + "</span>";
    S.countDone = true;
    setHint("tap for your receipt");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  ACT 4 · the receipt
  // ═══════════════════════════════════════════════════════════════════════════
  function enterAct4() {
    S.act = 3; setHint(null);
    var t = S.hero.totals;
    setKicker("Your receipt — <b>you saved " + money(t.saved_total) + "</b>");
    buildReceipt();
    $("register").classList.remove("show");
    wait(TUNE.receiptHold, function () {
      $("register").classList.add("hidden");
      var rc = $("receipt"); rc.classList.remove("hidden");
      if (!reduced) { rc.classList.remove("printing"); void rc.offsetWidth; rc.classList.add("printing"); }
      $("replay").classList.add("show");
    });
  }

  function buildReceipt() {
    var lines = $("r-lines"); lines.innerHTML = "";
    S.hero.items.forEach(function (it) {
      var el = document.createElement("div");
      el.className = "r-line";
      el.innerHTML =
        '<span class="rl-n">' + esc(it.pretty) + "</span>" +
        '<span class="rl-p"><s>' + money(it.list) + "</s><b>" + money(it.your_price) + "</b>" +
        ' <span class="rl-save">-' + money(it.saved_vs_list) + "</span></span>";
      lines.appendChild(el);
    });
    var t = S.hero.totals;
    $("r-saved").textContent = money(t.saved_total);
    $("r-pct").textContent = money(t.your_total) + " paid · " + money(t.list_total) +
      " sticker · " + Number(t.saved_pct).toFixed(0) + "% off";
    var m = S.trace.meta || {};
    $("r-caveat").innerHTML = esc(m.honest_caveat || "") +
      (m.citation ? "<br>" + esc(m.citation) : "");
    var prov = (m.provenance || {});
    $("r-repro").textContent = "recorded run · " + (prov.reproduce || "python3 -m buyer.preflearn --demo-trace");
  }

  // ── caveat (always visible) ─────────────────────────────────────────────────
  function fillCaveat() {
    var m = S.trace.meta || {};
    $("caveat").innerHTML = "<b>real recorded run.</b> " +
      esc((m.honest_caveat || "").split("—")[0] || "Every price is from buyer/preflearn.py.");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  INPUT
  // ═══════════════════════════════════════════════════════════════════════════
  function onStageTap(ev) {
    // ignore taps on interactive controls
    if (ev.target.closest(".p-opt, #replay, #receipt a, .snhp-nav")) return;
    if (S.act === 1) { skipWalk(); return; }
    if (S.act === 2 && S.countDone) { enterAct4(); return; }
  }
  view.addEventListener("click", onStageTap);
  $("overlay").addEventListener("click", onStageTap);
  $("replay").addEventListener("click", function () { S.epoch++; enterAct1(); });

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  BOOT — load the real trace
  // ═══════════════════════════════════════════════════════════════════════════
  resize();
  requestAnimationFrame(frame);

  fetch("demo-trace.json").then(function (r) { return r.json(); }).then(function (d) {
    S.trace = d; S.hero = d.scenarios.hero;
    if (!S.hero || !S.hero.onboarding || !S.hero.items) throw new Error("missing hero scenario");
    fillCaveat();
    enterAct1();
  }).catch(function (e) {
    $("err").textContent = "Could not load demo-trace.json — regenerate with: python3 -m buyer.preflearn --demo-trace";
    console.error(e);
  });
})();

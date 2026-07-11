/* THE SHOT. Two street elevations — STICKER (top) and SNHP (bottom) — the same
   ten storefronts and the same people, rendered into a 352×256 low-res
   backbuffer that integer-upscales crisp. Day 0 they are identical; over a
   7-day timelapse the sticker block grays and thins as regulars churn while the
   SNHP block keeps its crowd and pops receipt confetti. The two flip-clock
   counters between them climb the honest paired difference from the ledger.

   All magnitudes come from canned-week.json via Block.data — this file only
   choreographs pixels and time. URL params freeze a moment for screenshots:
     ?t=<hour>   freeze the wall clock (e.g. 6.5 dawn, 12 midday, 22 night)
     ?day=<0-6>  how far the two blocks have diverged
     ?paused=1   hold the current frame */
(function () {
  "use strict";
  const B = window.Block, D = B.data, P = B.pal, V = B.venues, WK = B.walkers;

  let LOW_W = 352; const PANEL_H = 128, LOW_H = 256;
  const SKY_H = 26, FACADE_TOP = 26, GROUND_Y = 96;   // panel-local y
  const MARGIN = 6, NBAY = 10; let BAY_W = 34;
  const bayX = i => MARGIN + i * BAY_W;
  const bayCx = i => bayX(i) + BAY_W / 2;

  // ── canvas plumbing ─────────────────────────────────────────────────────────
  // The view IS the backbuffer (352×256, backing store fixed); CSS scales it up
  // with image-rendering:pixelated. This "contain"-fits any viewport crisply and
  // fills the width on mobile — no integer-scale clipping.
  const view = document.getElementById("view");
  view.width = LOW_W; view.height = LOW_H;
  const c = view.getContext("2d"); c.imageSmoothingEnabled = false;
  let scale = 2, canvasLeft = 0, canvasTop = 0, dispW = LOW_W, dispH = LOW_H;

  function resize() {
    const availW = window.innerWidth, availH = window.innerHeight;
    // backbuffer aspect FOLLOWS the viewport so the street fills the screen
    // (no side letterbox); the ten venues spread to the new width.
    LOW_W = Math.max(256, Math.min(680, Math.round(LOW_H * (availW / availH))));
    BAY_W = Math.floor((LOW_W - 2 * MARGIN) / NBAY);
    view.width = LOW_W; view.height = LOW_H; c.imageSmoothingEnabled = false;
    scale = Math.min(availW / LOW_W, availH / LOW_H);       // ≈ fills both axes
    dispW = Math.round(LOW_W * scale); dispH = Math.round(LOW_H * scale);
    view.style.width = dispW + "px"; view.style.height = dispH + "px";
    canvasLeft = (availW - dispW) / 2; canvasTop = (availH - dispH) / 2;
    positionHUD();
  }
  window.addEventListener("resize", resize);

  // ── state ───────────────────────────────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  const st = { t: 0, playing: true, paused: false, days: 7, daySeconds: 6, spotlight: false };

  // ── SPOTLIGHT DEALS — the mechanism atom the aggregate counters hide ─────────
  // The scoreboard shows only "shoppers saved / merchants earned." A first-timer
  // never sees the ONE negotiation underneath. Each deal is a single, legible
  // transaction: the SAME shopper walks at the sticker (their max < the board)
  // but buys on SNHP (a personalized quote below their max, above cost).
  //
  // HONESTY: `sticker` (list) and `cost` (unit cost) are REAL per-SKU numbers —
  //   bodega/boba/fashion from block/calibration.py, bakery from bakeshop/
  //   calibration.py. `buyer_max` (this shopper's willingness-to-pay) and `neg`
  //   (the quote) are a REPRESENTATIVE atom, not a claim about one logged buyer —
  //   same "aggregates real · walkers representative" contract as the badge. The
  //   invariant cost ≤ neg ≤ buyer_max < sticker holds for every row (asserted at
  //   load) so nobody sells below cost and nobody pays above the board.
  const SPOTLIGHT_DEALS = [
    { venue: "BODEGA",  item: "chopped cheese",   sticker:   9.50, buyer_max:  7.00, neg:  5.20, cost:  3.20 },
    { venue: "BOBA",    item: "classic milk tea", sticker:   6.25, buyer_max:  4.50, neg:  3.10, cost:  1.35 },
    { venue: "BAKERY",  item: "morning croissant",sticker:   4.75, buyer_max:  3.60, neg:  2.50, cost:  1.40 },
    { venue: "BODEGA",  item: "deli sandwich",    sticker:  11.50, buyer_max:  8.75, neg:  6.50, cost:  4.10 },
    { venue: "FASHION", item: "hoodie",           sticker:  92.00, buyer_max: 70.00, neg: 52.00, cost: 31.00 },
    { venue: "FASHION", item: "slip dress",       sticker: 128.00, buyer_max: 95.00, neg: 68.00, cost: 42.00 },
  ].filter(d => {   // the honesty gate: drop any row that breaks the spine
    const ok = d.cost <= d.neg && d.neg <= d.buyer_max && d.buyer_max < d.sticker;
    if (!ok) console.error("spotlight: dropped deal (spine violated)", d);
    return ok;
  });

  // ── HUD refs ────────────────────────────────────────────────────────────────
  const el = id => document.getElementById(id);
  const scoreShopper = el("score-shopper"), scoreMerchant = el("score-merchant");
  const clockDay = el("clock-day"), clockTime = el("clock-time");
  const knobPointer = el("knob-pointer"), ticker = el("ticker"), tickerInner = el("ticker-inner");
  const nametag = el("nametag");

  function positionHUD() {
    const seam = canvasTop + dispH / 2;
    const sb = el("scoreboard"); sb.style.left = "50%"; sb.style.top = seam + "px"; sb.style.transform = "translate(-50%,-50%)";
    const sbH = sb.offsetHeight || 48;
    const ls = el("label-sticker"); ls.style.left = (canvasLeft + 6 * scale) + "px"; ls.style.top = (canvasTop + 5 * scale) + "px";
    // SNHP label drops below the scoreboard so the two never collide on mobile
    const ln = el("label-snhp"); ln.style.left = (canvasLeft + 6 * scale) + "px"; ln.style.top = (seam + sbH / 2 + 4) + "px";
  }

  // ── time helpers ────────────────────────────────────────────────────────────
  let realSec = 0;
  function animClock() { return st.paused ? st.t * 10 : realSec; }   // micro-anim + crowd motion clock
  function moveClock() { return st.paused ? st.t * 22 : realSec; }

  // ── glow stamp (additive), panel-local coords ───────────────────────────────
  function glow(gx, gy, r, col, a) {
    if (a <= 0) return;
    const n = parseInt(col.slice(1), 16), R = (n >> 16) & 255, G = (n >> 8) & 255, Bl = n & 255;
    c.globalCompositeOperation = "lighter";
    const g = c.createRadialGradient(gx, gy, 0, gx, gy, r);
    g.addColorStop(0, `rgba(${R},${G},${Bl},${a})`);
    g.addColorStop(1, `rgba(${R},${G},${Bl},0)`);
    c.fillStyle = g; c.fillRect(gx - r, gy - r, r * 2, r * 2);
    c.globalCompositeOperation = "source-over";
  }

  // ── one street panel ────────────────────────────────────────────────────────
  const hoverTargets = [];
  function drawPanel(world, yOff, ck) {
    const gray = world === "sticker" ? D.gray("sticker", st.t) : 0;
    const tint = hex => (gray ? P.drain(hex, gray) : hex);
    const night = P.nightFactor(ck.hourFloat), dawn = P.dawnFactor(ck.hourFloat);
    const rain = ck.weather === "rain", overcast = ck.weather === "overcast";
    const aT = animClock(), mT = moveClock();

    c.save();
    c.beginPath(); c.rect(0, yOff, LOW_W, PANEL_H); c.clip();
    c.translate(0, yOff);

    // sky
    const sky = P.skyAt(ck.hourFloat, ck.weather);
    const g = c.createLinearGradient(0, 0, 0, SKY_H + 8);
    g.addColorStop(0, tint(sky.top)); g.addColorStop(1, tint(sky.hor));
    c.fillStyle = g; c.fillRect(0, 0, LOW_W, FACADE_TOP);
    // stars
    if (night > 0.4) for (let i = 0; i < 26; i++) {
      const sx = (i * 97 + 13) % LOW_W, sy = (i * 37 + 3) % (SKY_H - 6);
      c.fillStyle = `rgba(220,215,240,${0.5 * night * (i % 3 ? 0.6 : 1)})`; c.fillRect(sx, sy, 1, 1);
    }
    // sun / moon by hour
    const dayT = P.clamp01((ck.hourFloat - 6) / 12);
    const arcx = 30 + dayT * (LOW_W - 60), arcy = 22 - Math.sin(dayT * Math.PI) * 15;
    if (ck.hourFloat > 6 && ck.hourFloat < 18.6) { c.fillStyle = tint("#ffe6a8"); disc(arcx, arcy, 4); glow(arcx, arcy, 14, "#ffdf9a", 0.16 * (1 - night)); }
    else { c.fillStyle = tint("#d6d0e6"); disc(LOW_W - 46, 12, 4); c.fillStyle = tint(sky.top); disc(LOW_W - 49, 10, 3); }
    // distant rooftops for depth
    c.fillStyle = tint(P.mix(sky.hor, "#2a2436", 0.7));
    for (let i = 0; i < NBAY; i++) { const h = 4 + ((i * 7) % 6); c.fillRect(bayX(i) + 2, FACADE_TOP - h, BAY_W - 4, h); }

    // façades
    D.venues.forEach((v, i) => {
      V.draw({
        ctx: c, kind: v.kind, x: bayX(i), w: BAY_W, top: FACADE_TOP, ground: GROUND_Y,
        world, decay: D.decay(world, v.id, st.t), hour: ck.hourFloat, t: aT,
        tint, glow, hash: k => D.hash01(v.id + world + k),
      });
    });

    // sidewalk + curb + road
    drawStreet(tint, world, gray);

    // puddles on rain days
    if (rain) for (let i = 0; i < 6; i++) { const px = 20 + i * 55 + (i % 2) * 12; c.fillStyle = tint("rgba(120,140,170,0.22)"); c.fillRect(px, GROUND_Y + 20 + (i % 3) * 4, 14, 2); }

    // ── crowd + regulars (depth-sorted) ───────────────────────────────────────
    const cast = [];
    // ambient
    const count = Math.min(24, Math.round(D.ambient(world, st.t) * (rain ? 0.65 : 1)));
    const seed = D.doc.crowd.seed;
    for (let i = 0; i < 24; i++) {
      const h1 = D.hash01(seed + world + "amb" + i), h2 = D.hash01(seed + world + "spd" + i), h3 = D.hash01(seed + world + "ln" + i);
      const alpha = i < count ? 1 : (i < count + 1 ? (D.ambient(world, st.t) * (rain ? 0.65 : 1)) % 1 : 0);
      if (alpha <= 0.03) continue;
      const dir = h1 > 0.5 ? 1 : -1, spd = 5 + h2 * 8;
      let fx = ((h1 * LOW_W + dir * spd * mT) % (LOW_W + 24) + (LOW_W + 24)) % (LOW_W + 24) - 12;
      const lane = GROUND_Y + 8 + Math.floor(h3 * 20);
      const frame = Math.floor(mT * 4 + h1 * 5) % 2;
      cast.push({ look: WK.archetype(i + (world === "snhp" ? 3 : 0)), x: fx, y: lane, facing: dir, frame, alpha, gray, umbrella: rain });
    }
    // named regulars
    const present = D.regularsPresent(world, ck.day);
    D.regulars.forEach(r => {
      const here = present.indexOf(r) >= 0;
      let alpha = 0, leaving = 0;
      if (world === "snhp") alpha = here ? 1 : 0;
      else {
        if (ck.day < r.churn.sticker_lastday) alpha = 1;
        else if (ck.day === r.churn.sticker_lastday) { alpha = P.clamp01(1 - ck.frac * 1.1); leaving = ck.frac; }
        else alpha = 0;
      }
      if (alpha <= 0.03) return;
      const hi = D.venues.findIndex(v => v.id === r.home);
      const homeX = bayCx(hi < 0 ? 5 : hi);
      const sway = Math.sin(mT * 0.8 + D.hash01(r.id) * 6) * 3;
      const fx = homeX + sway + leaving * 40 * (homeX > LOW_W / 2 ? 1 : -1);
      const face = leaving ? (homeX > LOW_W / 2 ? 1 : -1) : (sway > 0 ? -1 : 1);
      const frame = Math.floor(mT * 3 + D.hash01(r.id) * 5) % 2;
      cast.push({ look: lookFor(r), x: fx, y: GROUND_Y + 20, facing: face, frame, alpha, gray, umbrella: rain, reg: r, leaving });
      // hover hit-test (screen coords computed later)
      hoverTargets.push({ world, x: fx, y: GROUND_Y + 20 + yOff, name: r.name, home: r.home, leaving: world === "sticker" && ck.day >= r.churn.sticker_lastday, reason: r.churn.reason });
    });
    cast.sort((a, b) => a.y - b.y);
    cast.forEach(w => WK.draw(c, w.look, w.x, w.y, { facing: w.facing, frame: w.frame, bob: w.frame ? -1 : 0, alpha: w.alpha, gray: w.gray, umbrella: w.umbrella, tint }));

    // pigeons + the bodega cat
    drawCritters(tint, world, mT);

    // dawn trucks
    drawTrucks(world, ck, tint);

    // receipt confetti (SNHP only)
    if (world === "snhp") drawReceipts(ck);

    // rain streaks (foreground)
    if (rain) { c.strokeStyle = "rgba(150,170,200,0.28)"; c.lineWidth = 1; for (let i = 0; i < 60; i++) { const rx = (i * 53 + (mT * 120 | 0)) % LOW_W, ry = (i * 29 + (mT * 260 | 0)) % PANEL_H; c.beginPath(); c.moveTo(rx, ry); c.lineTo(rx - 2, ry + 6); c.stroke(); } }

    // daylight lift — a soft sunlit wash so midday façades read bright, not dim
    const daylight = (1 - night) * (rain ? 0.35 : overcast ? 0.55 : 1);
    if (daylight > 0.05) {
      c.globalCompositeOperation = "lighter";
      const dg = c.createLinearGradient(0, 0, 0, PANEL_H);
      dg.addColorStop(0, `rgba(255,236,196,${0.11 * daylight})`);
      dg.addColorStop(1, `rgba(210,220,240,${0.05 * daylight})`);
      c.fillStyle = dg; c.fillRect(0, FACADE_TOP, LOW_W, PANEL_H - FACADE_TOP);
      c.globalCompositeOperation = "source-over";
    }
    // night / weather wash
    if (night > 0.05) { c.fillStyle = `rgba(20,18,40,${0.34 * night})`; c.fillRect(0, 0, LOW_W, PANEL_H); }
    if (overcast) { c.fillStyle = "rgba(120,120,132,0.10)"; c.fillRect(0, 0, LOW_W, PANEL_H); }
    // the sticker drain deepens with a faint cool wash
    if (gray > 0.02) { c.fillStyle = `rgba(58,56,70,${0.14 * gray})`; c.fillRect(0, 0, LOW_W, PANEL_H); }

    c.restore();
  }

  function disc(x, y, r) { c.beginPath(); c.arc(x, y, r, 0, 7); c.fill(); }

  function drawStreet(tint, world, gray) {
    // sidewalk slabs
    const sy = GROUND_Y;
    c.fillStyle = tint(P.CIVIC.sidewalk[1]); c.fillRect(0, sy, LOW_W, PANEL_H - sy);
    c.fillStyle = tint(P.CIVIC.sidewalk[2]); c.fillRect(0, sy, LOW_W, 2);
    c.fillStyle = tint("rgba(0,0,0,0.16)");
    for (let x = 0; x < LOW_W; x += 16) c.fillRect(x, sy + 2, 1, 16);
    // curb + road sliver
    c.fillStyle = tint(P.CIVIC.curb); c.fillRect(0, PANEL_H - 8, LOW_W, 3);
    c.fillStyle = tint(P.CIVIC.street[0]); c.fillRect(0, PANEL_H - 5, LOW_W, 5);
    c.fillStyle = tint("#3a3550");
    for (let x = 6; x < LOW_W; x += 22) c.fillRect(x, PANEL_H - 3, 10, 1);   // lane dashes
    // a couple of street lamps
    for (const lx of [MARGIN + 2 * BAY_W, MARGIN + 7 * BAY_W]) {
      c.fillStyle = tint("#2a2733"); c.fillRect(lx, GROUND_Y + 4, 2, PANEL_H - GROUND_Y - 8);
      c.fillStyle = tint("#3a3550"); c.fillRect(lx - 3, GROUND_Y + 2, 8, 3);
      if (P.nightFactor(currentHour) > 0.35) glow(lx + 1, GROUND_Y + 4, 12, P.CIVIC.lamp, 0.14 * P.nightFactor(currentHour));
    }
  }

  function drawCritters(tint, world, mT) {
    // pigeons pecking on the sidewalk
    for (let i = 0; i < 3; i++) {
      const px = 40 + i * 90 + Math.sin(mT * 0.5 + i) * 6, py = GROUND_Y + 24 + (i % 2) * 5;
      const peck = Math.floor(mT * 3 + i) % 3 === 0 ? 1 : 0;
      c.fillStyle = tint("#6a6a76"); c.fillRect(px, py, 4, 3);            // body
      c.fillStyle = tint("#8a8a96"); c.fillRect(px + 3, py - 1 + peck, 2, 2); // head/neck
      c.fillStyle = tint("#c86a3a"); c.fillRect(px + 4, py + peck, 1, 1); // beak
      c.fillStyle = tint("#3a3a42"); c.fillRect(px + 1, py + 3, 1, 1); c.fillRect(px + 3, py + 3, 1, 1);
    }
    // the bodega cat — orange, near the bodega, tail flicking
    const cx = bayCx(1) + 8, cy = GROUND_Y + 26;
    const flick = Math.sin(mT * 2) * 2;
    c.fillStyle = tint("#d88a3a"); c.fillRect(cx, cy, 7, 4);             // body
    c.fillStyle = tint("#e09a4a"); c.fillRect(cx + 5, cy - 3, 3, 4);    // head
    c.fillStyle = tint("#c87a2a"); c.fillRect(cx + 5, cy - 4, 1, 1); c.fillRect(cx + 7, cy - 4, 1, 1); // ears
    c.fillStyle = tint("#d88a3a"); c.fillRect(cx - 1 + flick, cy - 2, 1, 4); // tail
    c.fillStyle = "#3a2a1a"; c.fillRect(cx + 6, cy - 2, 1, 1);          // eye
  }

  // ── dawn truck ballet ───────────────────────────────────────────────────────
  // One box truck per delivery. A NEGOTIATED SNHP delivery that serves two
  // venues (same supplier, one route) parks between them with a dashed route
  // line + a crate drop at each door — route density, visible. Rate-card
  // deliveries carry a clipboard; negotiated ones a handshake.
  function drawTrucks(world, ck, tint) {
    const W = 1.3, width = 22, ty = PANEL_H - 19;
    D.beatsBetween(world, "truck", ck.day, ck.hourFloat - W, ck.hourFloat + W).forEach(b => {
      const hi = D.venues.findIndex(v => v.id === b.venue);
      if (hi < 0) return;
      const si = b.shared_with ? D.venues.findIndex(v => v.id === b.shared_with) : -1;
      const parkCx = si >= 0 ? (bayCx(hi) + bayCx(si)) / 2 : bayCx(hi);
      const near = P.clamp01(1 - Math.abs(ck.hourFloat - b.hour) / W);   // 0 far → 1 parked
      const x0 = parkCx - width / 2 - (1 - near) * 50;
      // route: dashed line along the curb + a crate drop at each served door
      if (si >= 0 && near > 0.4) {
        c.fillStyle = tint("#e8c86a");
        [hi, si].forEach(vi => { for (let dx = Math.min(bayCx(vi), parkCx); dx < Math.max(bayCx(vi), parkCx); dx += 4) c.fillRect(dx, PANEL_H - 6, 2, 1); c.fillStyle = tint("#8a6a3a"); c.fillRect(bayX(vi) + BAY_W - 12, GROUND_Y + 22, 4, 3); c.fillStyle = tint("#e8c86a"); });
      }
      // box truck body
      c.fillStyle = tint(b.negotiated ? "#3a6a8a" : "#7a6a5a"); c.fillRect(x0, ty, width, 12);
      c.fillStyle = tint(b.negotiated ? "#4a7a9a" : "#8a7a6a"); c.fillRect(x0, ty, width, 3);
      c.fillStyle = tint(b.negotiated ? "#2a4a6a" : "#5a4a3a"); c.fillRect(x0 + 2, ty + 5, width - 12, 5); // side panel
      c.fillStyle = tint("#2a2733"); c.fillRect(x0 + width - 8, ty + 2, 8, 10);  // cab
      c.fillStyle = tint("#a8c0d0"); c.fillRect(x0 + width - 7, ty + 3, 6, 4);   // windscreen
      c.fillStyle = "#1a1620"; c.fillRect(x0 + 3, ty + 12, 3, 3); c.fillRect(x0 + width - 8, ty + 12, 3, 3); // wheels
      // icon above: handshake (negotiated) vs clipboard (rate-card)
      if (near > 0.55) {
        const ix = x0 + width / 2 - 3, iy = ty - 11;
        c.fillStyle = tint("rgba(10,9,18,0.72)"); c.fillRect(ix - 3, iy - 2, 13, 12);
        if (b.negotiated) { c.fillStyle = "#ffd98a"; c.fillRect(ix - 1, iy + 3, 4, 2); c.fillRect(ix + 3, iy + 3, 4, 2); c.fillRect(ix + 2, iy + 1, 2, 5); glow(ix + 3, iy + 4, 8, "#ffd98a", 0.18); }
        else { c.fillStyle = "#c8c4d0"; c.fillRect(ix, iy, 6, 8); c.fillStyle = "#5a5a66"; c.fillRect(ix + 1, iy + 2, 4, 1); c.fillRect(ix + 1, iy + 4, 4, 1); c.fillRect(ix + 1, iy + 6, 3, 1); c.fillStyle = "#8a8a92"; c.fillRect(ix + 2, iy - 1, 2, 1); }
      }
    });
  }

  // ── receipts ────────────────────────────────────────────────────────────────
  let liveReceipts = [], recTimer = 0, lastTickerAt = -9;
  function spawnReceipt(ck) {
    const bay = D.receiptBay(D.hash01("rec" + realSec));   // ∝ real deal share
    const v = D.venues[bay];
    const pool = D.doc.crowd.receipt_pool[v.id] || [["deal", 1]];
    const pick = pool[Math.floor(Math.random() * pool.length)];
    liveReceipts.push({ bay, label: pick[0], amt: pick[1], born: realSec, hue: 30 + bay * 34 });
    // update the DOM ticker (throttled)
    if (realSec - lastTickerAt > 1.4) {
      lastTickerAt = realSec;
      const item = pick[0].replace(/\s*-\$[\d.]+\s*$/, "");
      tickerInner.innerHTML = v.label + " · " + item + ' · <span class="amt">saved $' + pick[1].toFixed(2) + "</span>";
      ticker.classList.add("show");
      clearTimeout(ticker._to); ticker._to = setTimeout(() => ticker.classList.remove("show"), 2600);
    }
  }
  function activeReceipts(ck) {
    if (!st.paused) return liveReceipts.map(r => ({ bay: r.bay, label: r.label, amt: r.amt, age: realSec - r.born, hue: r.hue }));
    // paused: synthesize a deterministic handful so screenshots show confetti
    const div = D.divergence(st.t), out = [];
    if (div < 0.08) return out;
    for (let k = 0; k < 6; k++) {
      const ph = (st.t * 1.7 + k * 0.173 + 0.15) % 1;
      const bay = D.receiptBay(D.hash01("prec" + k + ck.day));   // ∝ real deal share
      out.push({ bay, label: "", amt: 0, age: ph * 2.2, hue: 30 + bay * 34 });
    }
    return out;
  }
  function drawReceipts(ck) {
    activeReceipts(ck).forEach(r => {
      if (r.age > 2.2 || r.age < 0) return;
      const x = bayX(r.bay) + BAY_W - 12, y = GROUND_Y - 8 - r.age * 16, a = P.clamp01(1 - r.age / 2.2);
      const col = P.hex(...hsv(r.hue, 0.5, 1));
      c.globalAlpha = a;
      c.fillStyle = "#f4efe4"; c.fillRect(x, y, 11, 7);           // ticket
      c.fillStyle = col; c.fillRect(x, y, 11, 2);                 // colored stub
      c.fillStyle = "#8a8478"; c.fillRect(x + 1, y + 3, 7, 1); c.fillRect(x + 1, y + 5, 5, 1); // "text"
      // confetti sparkles
      for (let k = 0; k < 3; k++) { c.fillStyle = P.hex(...hsv((r.hue + k * 60) % 360, 0.7, 1)); c.fillRect(x + 2 + k * 4 + (Math.sin(r.age * 6 + k) * 2 | 0), y - 2 - (r.age * 3 | 0) % 4, 1, 1); }
      c.globalAlpha = 1;
      glow(x + 5, y + 3, 8, "#ffe6b0", 0.14 * a);
    });
  }
  function hsv(h, s, v) {
    h = (h % 360) / 60; const i = Math.floor(h), f = h - i, p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
    const r = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6];
    return [r[0] * 255, r[1] * 255, r[2] * 255];
  }
  function lookFor(r) { return { skin: r.look.skin, hair: r.look.hair, top: r.look.top, bottom: r.look.bottom, prop: r.look.prop, hat: r.look.hat, big: r.look.big }; }

  // ── HUD update ──────────────────────────────────────────────────────────────
  const HR = ["12am", "1am", "2am", "3am", "4am", "5am", "6am", "7am", "8am", "9am", "10am", "11am", "12pm", "1pm", "2pm", "3pm", "4pm", "5pm", "6pm", "7pm", "8pm", "9pm", "10pm", "11pm"];
  let lastShopper = -1, lastMerchant = -1;
  function updateHUD(ck) {
    const co = D.counters(st.t);
    setFlip(scoreShopper, "$" + Math.round(co.shopper), () => { lastShopper = Math.round(co.shopper); }, Math.round(co.shopper) !== lastShopper);
    setFlip(scoreMerchant, "+$" + Math.round(co.merchant), () => { lastMerchant = Math.round(co.merchant); }, Math.round(co.merchant) !== lastMerchant);
    clockDay.textContent = "DAY " + (ck.day + 1);
    const hh = Math.floor(ck.hourFloat), mm = Math.floor((ck.hourFloat - hh) * 60);
    clockTime.textContent = HR[hh].replace(/(am|pm)/, "") + ":" + String(mm).padStart(2, "0") + HR[hh].slice(-2);
    knobPointer.parentElement.style.transform = "";
    knobPointer.style.transform = `rotate(${(st.t / (st.days - 1e-6)) * 300 - 150}deg)`;
  }
  function setFlip(node, text, commit, changed) {
    const cur = node.querySelector(".cur");
    if (cur.textContent !== text) {
      cur.textContent = text;
      if (changed) { node.classList.remove("bump"); void node.offsetWidth; node.classList.add("bump"); commit(); }
    }
  }

  // ── the jukebox knob (a jog wheel) ──────────────────────────────────────────
  (function knob() {
    const k = el("knob"); let dragging = false, lastAng = 0;
    const ang = e => { const r = k.getBoundingClientRect(); return Math.atan2((e.touches ? e.touches[0].clientY : e.clientY) - (r.top + r.height / 2), (e.touches ? e.touches[0].clientX : e.clientX) - (r.left + r.width / 2)); };
    const down = e => { dragging = true; st.playing = false; lastAng = ang(e); e.preventDefault(); };
    const move = e => { if (!dragging) return; const a = ang(e); let d = a - lastAng; if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI; lastAng = a; st.t = D.clamp((st.t + d / (2 * Math.PI) * st.days * 1.6), 0, st.days - 1e-6); st.paused = true; e.preventDefault(); };
    const up = () => { dragging = false; st.paused = false; };
    k.addEventListener("mousedown", down); window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    k.addEventListener("touchstart", down, { passive: false }); window.addEventListener("touchmove", move, { passive: false }); window.addEventListener("touchend", up);
    el("play").addEventListener("click", () => { st.playing = !st.playing; st.paused = false; el("play").textContent = st.playing ? "▮▮" : "▶"; });
  })();

  // ── spotlight: freeze the block, show ONE deal legibly ──────────────────────
  // Trigger: the dock's "ONE DEAL" button, OR auto — once ~6s into the first play
  // (teach the mechanism), then every ~34s of play while it's closed and idle.
  // Opening pauses the timelapse (st.spotlight) and restores the prior play state
  // on close. The three-number spine positions cost/quote/max/sticker on a shared
  // cost→sticker rail so the invariant reads at a glance.
  const SPOT_AUTO_FIRST = 6;     // POLISH: seconds of play before the first auto-open
  const SPOT_AUTO_EVERY = 34;    // POLISH: seconds between later auto-opens (0 disables)
  const money = n => "$" + n.toFixed(2);   // always cents — reads as a receipt
  const spot = {
    root: el("spotlight"), btn: el("spot-btn"),
    idx: 0, prevPlaying: true, everSeen: false,
    autoAccum: 0, firstDone: false,
  };
  function pos(x, d) { return ((x - d.cost) / (d.sticker - d.cost)) * 100; }
  function renderSpot() {
    const d = SPOTLIGHT_DEALS[spot.idx];
    if (!d) return;
    const margin = d.neg - d.cost, saving = d.buyer_max - d.neg;
    el("spot-venue").textContent = d.venue;
    el("spot-name").textContent = d.item;
    el("spot-stk1").textContent = money(d.sticker);
    el("spot-max1").textContent = money(d.buyer_max);
    el("spot-lose").textContent = money(d.sticker) + " > their " + money(d.buyer_max) + " — a lost sale";
    el("spot-save").textContent = "+" + money(saving);
    el("spot-margin").textContent = "+" + money(margin);
    el("spot-win").textContent = "quoted " + money(d.neg) + " — still above the " + money(d.cost) + " cost";
    // the spine: cost=0% … sticker=100%
    const pN = pos(d.neg, d), pM = pos(d.buyer_max, d);
    const segMargin = el("seg-margin"), segSaving = el("seg-saving"), segGap = el("seg-gap");
    segMargin.style.left = "0%"; segMargin.style.width = pN + "%";
    segSaving.style.left = pN + "%"; segSaving.style.width = (pM - pN) + "%";
    segGap.style.left = pM + "%"; segGap.style.width = (100 - pM) + "%";
    const tk = (id, p, val) => { const t = el(id); t.style.left = p + "%"; t.querySelector("b").textContent = money(val); };
    tk("tick-cost", 0, d.cost); tk("tick-neg", pN, d.neg); tk("tick-max", pM, d.buyer_max); tk("tick-stk", 100, d.sticker);
    el("spot-count").textContent = (spot.idx + 1) + " / " + SPOTLIGHT_DEALS.length;
  }
  function openSpot(i) {
    if (!SPOTLIGHT_DEALS.length) return;
    if (typeof i === "number") spot.idx = ((i % SPOTLIGHT_DEALS.length) + SPOTLIGHT_DEALS.length) % SPOTLIGHT_DEALS.length;
    st.spotlight = true;   // freeze is the !st.spotlight gate in frame(); play-state is untouched while open
    spot.everSeen = true; spot.autoAccum = 0;
    spot.btn.classList.remove("pulse");
    renderSpot();
    spot.root.classList.remove("hidden"); spot.root.setAttribute("aria-hidden", "false");
  }
  function closeSpot() {
    st.spotlight = false; spot.autoAccum = 0;
    spot.root.classList.add("hidden"); spot.root.setAttribute("aria-hidden", "true");
  }
  function stepSpot(dir) { openSpot(spot.idx + dir); }
  // auto-open cadence, counted in seconds of actual play (called from frame)
  function spotAuto(dt) {
    if (st.spotlight || !st.playing || st.paused || !SPOTLIGHT_DEALS.length) return;
    spot.autoAccum += dt;
    if (!spot.firstDone) { if (spot.autoAccum >= SPOT_AUTO_FIRST) { spot.firstDone = true; if (!spot.everSeen) openSpot(0); } return; }
    if (SPOT_AUTO_EVERY > 0 && spot.autoAccum >= SPOT_AUTO_EVERY) openSpot(spot.idx + 1);
  }
  spot.btn.addEventListener("click", () => (st.spotlight ? closeSpot() : openSpot()));
  el("spot-close").addEventListener("click", closeSpot);
  el("spot-next").addEventListener("click", () => stepSpot(1));
  el("spot-prev").addEventListener("click", () => stepSpot(-1));
  spot.root.querySelector(".spot-scrim").addEventListener("click", closeSpot);
  document.addEventListener("keydown", e => {
    if (!st.spotlight) return;
    if (e.key === "Escape") closeSpot();
    else if (e.key === "ArrowRight") stepSpot(1);
    else if (e.key === "ArrowLeft") stepSpot(-1);
  });
  // invite the click after a beat, until it's been opened once
  setTimeout(() => { if (!spot.everSeen) spot.btn.classList.add("pulse"); }, 2600);

  // ── hover nametags ──────────────────────────────────────────────────────────
  view.addEventListener("mousemove", e => {
    const lx = (e.clientX - canvasLeft) / scale, ly = (e.clientY - canvasTop) / scale;
    let best = null, bd = 9;
    hoverTargets.forEach(h => { const d = Math.hypot(h.x - lx, (h.y - 8) - ly); if (d < bd) { bd = d; best = h; } });
    if (best) {
      nametag.classList.remove("hidden");
      nametag.classList.toggle("gone", best.leaving);
      nametag.innerHTML = "<b>" + best.name + "</b><br><span class='sub'>" + (best.leaving ? "stopped coming — " + best.reason : "regular at " + best.home.toUpperCase()) + "</span>";
      nametag.style.left = e.clientX + "px"; nametag.style.top = (e.clientY - 12) + "px";
    } else nametag.classList.add("hidden");
  });
  view.addEventListener("mouseleave", () => nametag.classList.add("hidden"));

  // ── the loop ────────────────────────────────────────────────────────────────
  let currentHour = 12, last = performance.now();
  function frame(now) {
    let dt = (now - last) / 1000; last = now; if (dt > 0.1) dt = 0.1;
    realSec += dt;
    // the spotlight freezes the timelapse (the block holds behind the scrim);
    // realSec still advances so the frozen frame keeps its subtle micro-life.
    if (!st.spotlight) spotAuto(dt);
    if (st.playing && !st.paused && !st.spotlight) {
      st.t += dt / st.daySeconds;
      if (st.t >= st.days) st.t -= st.days;               // loop the week
      // spawn receipts on the SNHP block, gated by divergence (day 0 ≈ none)
      recTimer -= dt;
      const div = D.divergence(st.t);
      if (recTimer <= 0 && div > 0.06) { spawnReceipt(D.clock(st.t)); recTimer = 0.55 / Math.max(0.15, div); }
      liveReceipts = liveReceipts.filter(r => realSec - r.born < 2.3);
    }
    const ck = D.clock(st.t); currentHour = ck.hourFloat;
    hoverTargets.length = 0;
    c.clearRect(0, 0, LOW_W, LOW_H);
    drawPanel("sticker", 0, ck);
    drawPanel("snhp", PANEL_H, ck);
    // seam + panel frames
    c.fillStyle = "#0a0810"; c.fillRect(0, PANEL_H - 1, LOW_W, 2);
    c.strokeStyle = "rgba(0,0,0,0.5)"; c.lineWidth = 1; c.strokeRect(0.5, 0.5, LOW_W - 1, LOW_H - 1);
    // brand tag
    c.fillStyle = "rgba(200,196,216,0.22)"; c.fillRect(LOW_W - 20, LOW_H - 6, 3, 3);
    updateHUD(ck);
    requestAnimationFrame(frame);
  }

  // ── boot ────────────────────────────────────────────────────────────────────
  D.load("canned-week.json?v=1", doc => {
    if (!doc) { document.body.innerHTML = "<p style='color:#fff;padding:20px;font-family:monospace'>failed to load canned-week.json</p>"; return; }
    st.days = doc.meta.days; st.daySeconds = doc.meta.day_seconds;
    // URL param freezing for screenshots
    const dayP = params.has("day") ? Math.max(0, Math.min(st.days - 1, +params.get("day"))) : 0;
    if (params.has("t")) { st.t = D.tForHour(dayP, +params.get("t")); st.paused = true; st.playing = false; }
    else if (params.has("day")) { st.t = D.tForHour(dayP, 12); }
    else { st.t = D.tForHour(0, 10.5); }                  // honest opening: day-0 midday, identical + lively
    if (params.get("paused") === "1") { st.paused = true; st.playing = false; }
    resize();
    requestAnimationFrame(frame);
  });
})();

/* The ten storefronts. Each is an icon you can read at a 34px bay AND a little
   machine with a signature micro-animation (spinning pole, bubbling boba,
   croissant steam, fading buckets, the parking gate…). Every façade also
   carries its DECAY state — on the sticker block the neon dims, spoilage bins
   fill, and clearance tags appear as the week wears on. Nothing here reads the
   sim; it turns (kind, hour, night, decay, t) into pixels.

   Bay geometry is passed in: x0 (left), w (bay width), top (façade top y),
   ground (sidewalk y). Signature content lives in the shopfront window from
   ~top+34 down to ground. */
(function () {
  "use strict";
  const B = (window.Block = window.Block || {});
  const P = B.pal;

  // brick/stone base per building so the block reads as ten distinct fronts
  const WALL = {
    machine: "#3a4450", deli: "#6a4038", boba: "#3a5a58", bakery: "#6a4a34",
    flower: "#4a5a44", barber: "#5a4048", fashion: "#38333f", vintage: "#5a4a34",
    bar: "#353a52", parking: "#44424e",
  };

  function draw(E) {
    const V = B.pal.VENUE[E.kind] || B.pal.VENUE.machine;
    const g = E.decay;                                  // 0..1 sticker decay
    const tint = E.tint;                                // gray drain closure
    const c = E.ctx;
    const x = E.x, w = E.w, top = E.top, ground = E.ground;
    const px = (X, Y, W, H, col) => { c.fillStyle = tint(col); c.fillRect(x + (X | 0), (Y | 0), W | 0, H | 0); };
    const wall = WALL[E.kind] || "#44424e";

    // ── building shell ──────────────────────────────────────────────────────
    px(0, top, w, ground - top, wall);
    px(0, top, w, 3, P.mix(wall, "#000000", 0.4));      // cornice shadow
    px(0, top, 1, ground - top, P.mix(wall, "#ffffff", 0.12)); // lit left edge
    px(w - 1, top, 1, ground - top, P.mix(wall, "#000000", 0.35));
    // brick coursing
    for (let yy = top + 5; yy < top + 34; yy += 4) {
      c.fillStyle = tint(P.mix(wall, "#000000", 0.18)); c.fillRect(x, yy, w, 1);
    }

    // ── upper storey — varied per building so ten distinct fronts read, not
    //    one repeated wallpaper. Layout is seeded per-venue (identical in both
    //    worlds); only which windows are LIT differs (SNHP cozy, sticker dark). ─
    const uy = top + 8, nightlit = P.nightFactor(E.hour) > 0.4;
    const variant = E.hash(7), hasEscape = E.hash(3) > 0.6, hasAC = E.hash(5) > 0.66;
    const winCol = lit => nightlit ? (lit ? P.CIVIC.window_lit_night : P.CIVIC.window_dark)
      : P.mix(P.CIVIC.window_lit_day, wall, 0.28);
    function upWin(wx, ww, wh) {
      px(wx, uy, ww, wh, "#1c1a26");
      const lit = E.hash(wx * 3 + 1) > (E.world === "snhp" ? 0.3 : 0.58 + g * 0.34);
      px(wx + 1, uy + 1, ww - 2, wh - 2, winCol(lit));
      px(wx + (ww >> 1), uy, 1, wh, "#141220");                 // mullion
      if (wh > 8) px(wx, uy + (wh >> 1), ww, 1, "#141220");     // transom
      if (nightlit && lit) E.glow(x + wx + ww / 2, uy + wh / 2, 7, P.CIVIC.window_lit_night, 0.11 * (1 - 0.7 * g));
    }
    if (variant < 0.4) { const gap = (w - 16) / 3; upWin(gap, 8, 12); upWin(w - gap - 8, 8, 12); }
    else if (variant < 0.72) { for (let i = 0; i < 3; i++) upWin(4 + i * ((w - 8) / 3), 6, 9); }
    else { upWin((w - 16) / 2, 16, 12); }                        // one picture window
    // fire escape — a little iron zigzag over the shopfront (NYC character)
    if (hasEscape) {
      const fe = "#1a1620";
      px(2, uy + 13, w - 4, 1, fe); px(2, uy + 20, w - 4, 1, fe);  // platforms
      for (let ry = uy + 13; ry < uy + 21; ry += 2) { px(3, ry, 1, 1, fe); px(w - 4, ry, 1, 1, fe); }
      for (let dx = 4; dx < w - 5; dx += 3) px(dx, uy + 13 + ((dx >> 1) % 7), 1, 1, fe);  // diagonal
    }
    // window AC unit dripping over the sidewalk
    if (hasAC) { px(w - 12, uy + 12, 5, 3, "#8a8a92"); px(w - 11, uy + 13, 3, 1, "#3a3a42"); }

    // ── sign band + awning ────────────────────────────────────────────────────
    const signY = top + 32, awnY = top + 39;
    px(0, signY, w, 7, P.mix(V.a, "#000000", 0.25));      // sign board
    // lettermark: three little glyph blocks in the trim color (reads as a name)
    for (let i = 0; i < 3; i++) px(6 + i * 8, signY + 2, 5, 3, V.trim);
    // neon accent on the sign at night (dimmed by decay on sticker)
    const neon = P.nightFactor(E.hour) * (E.world === "snhp" ? 1 : (1 - 0.85 * g));
    if (neon > 0.2) E.glow(x + w / 2, signY + 3, w * 0.55, V.glow, 0.20 * neon);

    // scalloped awning
    px(-1, awnY, w + 2, 5, V.a);
    px(-1, awnY, w + 2, 2, P.mix(V.a, "#ffffff", 0.22));
    for (let i = 0; i < w + 2; i += 6) px(-1 + i, awnY + 5, 3, 2, V.a);   // scallops
    // awning stripes (skip for the minimalist fashion front)
    if (E.kind !== "fashion" && E.kind !== "parking")
      for (let i = 0; i < w + 2; i += 8) px(-1 + i, awnY, 4, 5, P.mix(V.a, V.b, 0.5));

    // ── shopfront frame + window ──────────────────────────────────────────────
    const fy = top + 46, fh = ground - fy;               // shopfront region
    px(0, fy, w, fh, P.mix(wall, "#000000", 0.3));       // frame
    const glassX = 3, glassY = fy + 2, glassW = w - 6, glassH = fh - 6;
    px(glassX, glassY, glassW, glassH, "#171a24");       // window recess
    // interior warm/cool wash — SNHP stays warm, sticker cools as it decays
    const inside = E.world === "snhp"
      ? P.mix("#2a2436", "#4a3a2e", 0.5)
      : P.mix("#242430", "#3a3340", g);
    px(glassX + 1, glassY + 1, glassW - 2, glassH - 2, inside);

    // per-venue signature content in the window + on the sidewalk
    const S = { c, x, w, top, ground, px, glassX, glassY, glassW, glassH, fy,
                tint, glow: E.glow, night: P.nightFactor(E.hour), hour: E.hour,
                t: E.t, decay: g, world: E.world, V, mix: P.mix };
    (SIG[E.kind] || SIG.machine)(S);

    // door (every shop has one; walkers vanish into it)
    const dw = 9, dx = w - dw - 2, dy = ground - 15;
    px(dx, dy, dw, 15, P.mix(wall, "#000000", 0.5));
    px(dx + 1, dy + 1, dw - 2, 14, E.world === "snhp" ? "#3a3040" : P.mix("#302c38", "#2a2a30", g));
    px(dx + dw - 3, dy + 7, 1, 2, V.trim);               // knob
    // warm spill from an open SNHP door
    if (E.world === "snhp") E.glow(x + dx + dw / 2, dy + 12, 10, "#ffcf8a", 0.10);

    // sidewalk-level decay props (spoilage bins, clearance) on the sticker block
    if (E.world === "sticker") decayProps(S, E);
  }

  // ── signature window content per kind ───────────────────────────────────────
  const SIG = {
    machine(S) { // vending: glowing product columns + blinking select light
      const gx = S.glassX + 2, gy = S.glassY + 2, gw = S.glassW - 4;
      const cols = ["#c04a4a", "#4a7ac0", "#4ac06a", "#c0a04a", "#a04ac0"];
      for (let r = 0; r < 3; r++) for (let col = 0; col < 4; col++) {
        S.px(gx + col * ((gw) / 4), gy + r * 5, gw / 4 - 1, 4, cols[(r * 4 + col) % cols.length]);
      }
      // coin/keypad strip
      S.px(S.glassX + S.glassW - 4, S.glassY + 2, 3, S.glassH - 4, "#2a2e3a");
      const blink = (Math.floor(S.t * 2) % 2) === 0 && S.world === "snhp";
      S.px(S.glassX + S.glassW - 3, S.glassY + 4, 1, 1, blink ? "#7fe0ff" : "#2f5a6a");
      if (blink) S.glow(S.x + S.glassX + S.glassW - 2, S.glassY + 5, 5, "#7fe0ff", 0.16);
    },
    deli(S) { // bodega: fruit crates on the sidewalk, blinking OPEN, cans inside
      // shelves inside
      for (let r = 0; r < 3; r++) S.px(S.glassX + 2, S.glassY + 2 + r * 5, S.glassW - 4, 3, "#5a4a3a");
      const cans = ["#c0503a", "#d8a020", "#4a8a5a", "#c8c0b0"];
      for (let i = 0; i < 6; i++) S.px(S.glassX + 3 + (i % 3) * ((S.glassW - 6) / 3), S.glassY + 3 + ((i / 3) | 0) * 5, 3, 3, cans[i % 4]);
      // green OPEN neon (blinks at night on SNHP; sticker goes dark)
      const on = S.world === "snhp" ? (Math.floor(S.t * 1.5) % 4 !== 0) : (S.decay < 0.3);
      if (S.night > 0.3 && on) { S.px(S.glassX + 2, S.glassY + S.glassH - 5, 12, 3, "#5ad06a"); S.glow(S.x + S.glassX + 8, S.glassY + S.glassH - 4, 9, "#5ad06a", 0.22 * S.night); }
      // fruit stand out front
      const fruit = ["#d84a3a", "#e8a020", "#e0c040", "#c85030"];
      for (let i = 0; i < 4; i++) {
        const col = S.decay > 0.4 ? S.mix(fruit[i], "#5a5a52", S.decay) : fruit[i];
        S.px(2 + i * 3, S.ground - 6, 3, 3, col);
      }
      S.px(1, S.ground - 3, 14, 3, "#3a2e28");
    },
    boba(S) { // neon cup with pearls that bubble up + a straw
      const cx = S.glassX + S.glassW / 2;
      const cupW = 12, cupX = cx - cupW / 2, cupY = S.glassY + 4, cupH = 14;
      S.px(cupX, cupY, cupW, cupH, "#e8f0ee");           // cup
      S.px(cupX, cupY, cupW, 3, "#c04a7a");              // pink dome lid
      S.px(cx - 1, cupY - 5, 2, 6, "#e58ab4");           // straw
      // milk-tea fill
      S.px(cupX + 1, cupY + 4, cupW - 2, cupH - 5, S.world === "snhp" ? "#caa06a" : S.mix("#caa06a", "#8a8378", S.decay));
      // tapioca pearls rising (animated)
      for (let i = 0; i < 5; i++) {
        const ph = (S.t * 0.7 + i * 0.9) % 1;
        const by = cupY + cupH - 2 - ph * (cupH - 4);
        const bx = cupX + 2 + ((i * 5 + 1) % (cupW - 4));
        S.px(bx, by, 2, 2, "#3a2a2a");
      }
      if (S.night > 0.3) S.glow(S.x + cx, cupY + 6, 12, S.V.glow, 0.20 * S.night * (S.world === "snhp" ? 1 : 1 - S.decay));
    },
    bakery(S) { // warm oven glow + a croissant with curling steam
      S.px(S.glassX + 1, S.glassY + 1, S.glassW - 2, S.glassH - 2, S.world === "snhp" ? "#5a3a22" : S.mix("#5a3a22", "#3a3230", S.decay)); // oven interior
      S.glow(S.x + S.glassX + S.glassW / 2, S.glassY + S.glassH - 3, 11, "#ff9a3a", (S.world === "snhp" ? 0.24 : 0.24 * (1 - S.decay)));
      // shelf of loaves/croissants
      const cx = S.glassX + S.glassW / 2;
      S.px(S.glassX + 2, S.glassY + 6, S.glassW - 4, 2, "#4a3020");
      for (let i = 0; i < 3; i++) S.px(S.glassX + 3 + i * 6, S.glassY + 3, 4, 3, "#e0b060"); // croissants
      // steam curling up (animated), only when fresh/warm
      if (S.world === "snhp" || S.decay < 0.4) {
        for (let i = 0; i < 3; i++) {
          const ph = (S.t * 0.5 + i * 0.4) % 1;
          const sx = cx + Math.sin((ph + i) * 6.28) * 3;
          S.c.globalAlpha = 0.55 * (1 - ph); S.px(sx, S.glassY + 2 - ph * 6, 1, 2, "#efe7d8"); S.c.globalAlpha = 1;
        }
      }
    },
    flower(S) { // buckets of flowers out front, colors fade with freshness
      const cols = ["#e05a7a", "#e8c040", "#c05ac0", "#5a8ae0", "#e08a4a"];
      // window plants
      for (let i = 0; i < 4; i++) {
        const col = S.world === "snhp" ? cols[i] : S.mix(cols[i], "#7a7a72", S.decay);
        S.px(S.glassX + 2 + i * 6, S.glassY + 3, 3, 3, col);
        S.px(S.glassX + 3 + i * 6, S.glassY + 6, 1, 4, "#4a7a3a");
      }
      // buckets on the sidewalk
      for (let i = 0; i < 3; i++) {
        const bx = 2 + i * 5;
        S.px(bx, S.ground - 8, 4, 5, "#8a9aa0");        // bucket
        for (let k = 0; k < 3; k++) {
          const col = S.world === "snhp" ? cols[(i + k) % cols.length] : S.mix(cols[(i + k) % cols.length], "#82827a", S.decay);
          S.px(bx + k, S.ground - 10 - (k % 2), 1, 3, col);
        }
      }
    },
    barber(S) { // spinning red/white/blue pole + mirror interior
      // interior mirror + chair
      S.px(S.glassX + 2, S.glassY + 2, 5, S.glassH - 4, "#8aa0b0");
      S.px(S.glassX + S.glassW - 7, S.glassY + 4, 5, S.glassH - 6, "#5a3a3a");
      // the pole, mounted left of the door
      const pxx = 3, pyy = S.fy + 2, ph = S.ground - pyy - 2;
      S.px(pxx, pyy - 2, 4, 2, "#c0c0c8"); S.px(pxx, S.ground - 2, 4, 2, "#c0c0c8"); // caps
      S.px(pxx, pyy, 4, ph, "#f0f0f4");
      // scrolling helical stripes (animated)
      const off = (S.t * 6) % 6;
      for (let yy = -6; yy < ph; yy += 6) {
        S.px(pxx, pyy + ((yy + off + ph) % ph), 4, 2, "#c93a3a");
        S.px(pxx, pyy + ((yy + off + 3 + ph) % ph), 4, 2, "#2f4aa0");
      }
      if (S.night > 0.3) S.glow(S.x + pxx + 2, pyy + ph / 2, 8, "#ff6a6a", 0.14 * S.night);
    },
    fashion(S) { // minimalist front: a dress on a hanger + a seasonal accent
      const cx = S.glassX + S.glassW / 2;
      const dress = S.world === "snhp" ? S.V.trim : S.mix(S.V.trim, "#6a6a70", S.decay);
      // hanger rail + hook
      S.px(S.glassX + 3, S.glassY + 2, S.glassW - 6, 1, "#c8c4d0");
      S.px(cx, S.glassY + 1, 1, 2, "#c8c4d0");
      // shoulders → skirt (a clean dress trapezoid, reads as clothing)
      S.px(cx - 3, S.glassY + 3, 6, 2, dress);          // shoulders
      S.px(cx - 4, S.glassY + 5, 8, 3, dress);
      S.px(cx - 5, S.glassY + 8, 10, 4, dress);         // flaring skirt
      S.px(cx - 1, S.glassY + 5, 2, 1, S.mix(dress, "#ffffff", 0.3)); // waist highlight
      // a second garment (a folded tee) on a side shelf
      S.px(S.glassX + 1, S.glassY + S.glassH - 6, 5, 3, S.world === "snhp" ? "#e58a5a" : S.mix("#e58a5a", "#6a6a70", S.decay));
      S.glow(S.x + cx, S.glassY + 7, 9, "#ffffff", S.world === "snhp" ? 0.09 : 0.05);
      // magenta accent line
      S.px(S.glassX + 2, S.glassY + S.glassH - 2, S.glassW - 4, 1, S.world === "snhp" ? "#e05aa0" : S.mix("#e05aa0", "#6a6a70", S.decay));
    },
    vintage(S) { // a rack of one-off items + browsing hands flicking through
      const rackY = S.glassY + 5;
      S.px(S.glassX + 1, rackY, S.glassW - 2, 1, "#c0c0c8"); // rail
      const cols = ["#b8912e", "#3a8a86", "#8a4a6a", "#4a6a8a", "#8a6a3a", "#6a8a4a"];
      const n = 6;
      for (let i = 0; i < n; i++) {
        const hx = S.glassX + 2 + i * ((S.glassW - 4) / n);
        S.px(hx, rackY + 1, 3, 8, S.world === "snhp" ? cols[i] : S.mix(cols[i], "#7a7872", S.decay * 0.8));
      }
      // a browsing hand slides along the rack (animated)
      const hp = (Math.sin(S.t * 1.3) * 0.5 + 0.5);
      const hxp = S.glassX + 2 + hp * (S.glassW - 6);
      S.px(hxp, rackY - 2, 2, 2, "#e0b090");
    },
    bar(S) { // amber happy-hour glow + string lights + stools
      // bottles behind the bar
      const cols = ["#c0503a", "#4a8a5a", "#d8a020", "#8a5ac0"];
      for (let i = 0; i < 5; i++) S.px(S.glassX + 2 + i * 4, S.glassY + 3, 2, 6, cols[i % 4]);
      S.px(S.glassX + 1, S.glassY + 10, S.glassW - 2, 2, "#3a2a1e"); // bar top
      // happy-hour amber glow: pulses in the evening
      const happy = S.night * (S.world === "snhp" ? 1 : 1 - S.decay);
      const pulse = 0.7 + 0.3 * Math.sin(S.t * 3);
      if (happy > 0.2) {
        S.px(S.glassX + 2, S.glassY + S.glassH - 5, S.glassW - 4, 3, "#e8a838");
        S.glow(S.x + S.glassX + S.glassW / 2, S.glassY + S.glassH - 3, 13, "#ffb84a", 0.24 * happy * pulse);
      }
      // string lights across the top of the bay
      for (let i = 0; i < S.w; i += 5) {
        S.px(i, S.top + 46, 1, 1, "#ffe0a0");
        if (S.night > 0.3) S.glow(S.x + i, S.top + 46, 3, "#ffe0a0", 0.12 * S.night);
      }
    },
    parking(S) { // striped gate arm that lifts/lowers + a parked car + P sign
      // interior: a P sign
      S.px(S.glassX + 2, S.glassY + 2, S.glassW - 4, S.glassH - 4, "#2f2e38");
      S.px(S.glassX + 4, S.glassY + 3, 4, 8, "#e8c838"); // P post
      S.px(S.glassX + 4, S.glassY + 3, 6, 3, "#e8c838");
      S.px(S.glassX + 8, S.glassY + 4, 2, 3, "#e8c838");
      // the gate arm, hinged on a post, lifting on a slow cycle. Kept mostly
      // horizontal so it reads as a barrier, with bold red/white stripes.
      const cyc = (Math.sin(S.t * 0.8) * 0.5 + 0.5);       // 0 down .. 1 up
      const armLen = 16;
      const hingeX = S.x + 4, hingeY = S.fy + 4;
      const ang = -cyc * 0.85;                             // barrier: level → ~50° up
      S.px(2, S.fy, 4, S.ground - S.fy, "#4a4856");        // gate post
      S.px(2, S.fy, 4, 2, "#e8c838");                      // post cap
      S.c.save(); S.c.translate(hingeX, hingeY); S.c.rotate(ang);
      for (let i = 0; i < armLen; i += 4) { S.c.fillStyle = S.tint(((i / 4) % 2) ? "#c93a3a" : "#f0f0f4"); S.c.fillRect(i, -1.5, 4, 3); }
      S.c.restore();
      // a parked car nose peeking from the lot
      S.px(S.w - 13, S.ground - 6, 11, 6, "#4a6a8a");
      S.px(S.w - 12, S.ground - 8, 7, 3, "#3a5a7a");       // roof
      S.px(S.w - 11, S.ground - 5, 3, 2, "#a8c0d0");       // window
      S.px(S.w - 12, S.ground - 2, 3, 2, "#1a1a22"); S.px(S.w - 5, S.ground - 2, 3, 2, "#1a1a22"); // wheels
    },
  };

  // sticker-only decay: spoilage bins, clearance racks — the visible decline
  function decayProps(S, E) {
    const g = S.decay;
    if (g < 0.18) return;
    if (E.kind === "deli" || E.kind === "bakery" || E.kind === "boba") {
      // spoilage bin filling behind the shop
      const bx = S.x + 1, by = S.ground - 2, bw = 7, fill = Math.min(6, 1 + g * 7);
      S.px(1, S.ground - 2, bw, 2, "#2e2a2e");
      S.c.fillStyle = S.tint("#5a4a3a");
      S.c.fillRect(bx, by - fill, bw, fill);
      // flies
      if (g > 0.4) for (let i = 0; i < 3; i++) { const fx = bx + ((S.t * 20 + i * 13) % bw); S.px(fx - S.x, by - fill - 2 - (i % 2), 1, 1, "#1a1a22"); }
    }
    if (E.kind === "fashion" || E.kind === "vintage") {
      // clearance tag / rack — deeper red as the season ends
      const pct = E.kind === "fashion" ? Math.round(20 + g * 60) : Math.round(15 + g * 40);
      const tw = 16, ty = S.top + 47;
      S.px(2, ty, tw, 6, "#a01a1a");
      S.px(2, ty, tw, 1, "#c03030");
      // "-N%" in tiny blocks
      S.px(4, ty + 2, 2, 1, "#ffffff");                  // minus
      S.px(7, ty + 2, 2, 3, "#ffffff"); S.px(10, ty + 2, 2, 3, "#ffffff"); // digits-ish
      S.px(13, ty + 1, 2, 2, "#ffffff");                 // %
      void pct;
    }
  }

  B.venues = { draw };
})();

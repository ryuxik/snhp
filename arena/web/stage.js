/* The great hall. Geography with MEANING:
     left  — the GATE: every newcomer walks in through it (entries are felt)
     center— the ROSE WINDOW ensemble: the market era, in glass (amber boom,
             cold-blue bust, violet balance, fuchsia contract season)
     right — the CRYPT WALL: dead dynasty founders get a memorial candle
   Plus hanging dynasty banners (length = wealth), dressed market stalls at the
   duel zones, a carpet runner, torches, chains, coursed stone. Light law:
   nothing back here outbrights the window, the flames, or event FX. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  const WORLD_W = 560, WORLD_H = 270;
  const FLOOR_Y = 212;
  const GATE_X = 30, CRYPT_X = 522;
  const ZONES = [
    { x: 88, y: 226 }, { x: 164, y: 232 }, { x: 250, y: 226 },
    { x: 336, y: 232 }, { x: 420, y: 226 }, { x: 492, y: 230 },
  ];

  const ERA_GLASS = {
    symmetric: ["#7A54B2", "#A78BFA", "#4A2E72"],
    buyers: ["#3D5AA0", "#5A78C8", "#26386E"],
    sellers: ["#8A5A1E", "#D98E2B", "#5C3A12"],
    contract: ["#8A3DA0", "#C86FD6", "#5C2870"],
  };

  let _far = null, _mid = null, _floor = null;
  let _midEra = null, _midDirty = true, _t = 0;
  let _banners = [], _memorials = [];

  function setBanners(list) { _banners = (list || []).slice(0, 4); _midDirty = true; }
  function setMemorials(list) { _memorials = (list || []).slice(-6); _midDirty = true; }

  // ── far: night sky, stars, distant keep ──────────────────────────────────
  function _buildFar() {
    const cv = document.createElement("canvas"); cv.width = WORLD_W; cv.height = WORLD_H;
    const c = cv.getContext("2d");
    const g = c.createLinearGradient(0, 0, 0, FLOOR_Y);
    g.addColorStop(0, "#07060d"); g.addColorStop(0.55, "#0d0b18"); g.addColorStop(1, "#171226");
    c.fillStyle = g; c.fillRect(0, 0, WORLD_W, FLOOR_Y);
    // stars (dim, clustered high)
    for (let i = 0; i < 60; i++) {
      const x = (i * 97 + 31) % WORLD_W, y = ((i * 53 + 11) % 90);
      c.fillStyle = i % 5 ? "rgba(180,175,210,0.35)" : "rgba(220,215,240,0.55)";
      c.fillRect(x, y, 1, 1);
    }
    // moon with crater bite
    c.fillStyle = "#c9c2e0"; c.beginPath(); c.arc(468, 44, 13, 0, 7); c.fill();
    c.fillStyle = "#0d0b18"; c.beginPath(); c.arc(463, 40, 11, 0, 7); c.fill();
    // distant keep silhouette: varied towers, spires, tiny lit windows
    c.fillStyle = "#0e0b19";
    const T = [[0, 58, 62], [55, 40, 88], [120, 66, 70], [185, 44, 104], [252, 58, 84],
      [318, 50, 96], [372, 64, 66], [430, 46, 92], [490, 60, 74]];
    for (const [bx, bw, bh] of T) {
      c.fillRect(bx, FLOOR_Y - bh, bw, bh);
      // crenellations
      for (let x = bx; x < bx + bw - 3; x += 7) c.fillRect(x, FLOOR_Y - bh - 4, 4, 4);
    }
    // spires
    c.beginPath(); c.moveTo(200, FLOOR_Y - 104); c.lineTo(207, FLOOR_Y - 148); c.lineTo(214, FLOOR_Y - 104); c.fill();
    c.beginPath(); c.moveTo(440, FLOOR_Y - 92); c.lineTo(447, FLOOR_Y - 130); c.lineTo(454, FLOOR_Y - 92); c.fill();
    // sparse candlelit windows in the far keep
    for (let i = 0; i < 14; i++) {
      const x = (i * 41 + 17) % (WORLD_W - 10), y = FLOOR_Y - 20 - ((i * 29) % 70);
      c.fillStyle = i % 3 ? "rgba(232,163,61,0.22)" : "rgba(232,163,61,0.34)";
      c.fillRect(x, y, 2, 3);
    }
    return cv;
  }

  // ── mid: the hall wall — stone, arches, window ensemble, gate, crypt ─────
  function _buildMid(era) {
    const cv = document.createElement("canvas"); cv.width = WORLD_W; cv.height = WORLD_H;
    const c = cv.getContext("2d");
    const WALL_TOP = 62;
    // wall base (lifted just enough that the architecture reads at night)
    c.fillStyle = "#191529"; c.fillRect(0, WALL_TOP, WORLD_W, FLOOR_Y - WALL_TOP);
    // coursed stone: rows of blocks with staggered seams + value variance
    for (let y = WALL_TOP; y < FLOOR_Y; y += 8) {
      c.fillStyle = "rgba(0,0,0,0.22)"; c.fillRect(0, y, WORLD_W, 1);
      const off = ((y / 8) % 2) * 11;
      for (let x = -off; x < WORLD_W; x += 22) {
        c.fillStyle = "rgba(0,0,0,0.16)"; c.fillRect(x, y, 1, 8);
        if (((x * 7 + y * 13) % 97) < 9) { // occasional lighter block
          c.fillStyle = "rgba(122,110,160,0.05)"; c.fillRect(x + 1, y + 1, 20, 6);
        }
      }
    }
    // ceiling beam + hanging chains
    c.fillStyle = "#0e0b19"; c.fillRect(0, WALL_TOP, WORLD_W, 6);
    c.fillStyle = "#241f36";
    for (const cx of [120, 200, 360, 440]) {
      for (let y = WALL_TOP + 6; y < WALL_TOP + 26; y += 3) c.fillRect(cx + (y % 6 < 3 ? 0 : 1), y, 1, 2);
    }
    // arched recesses (dark negative space) between pillars
    for (const ax of [66, 146, 338, 418]) {
      c.fillStyle = "#0b0914";
      c.beginPath(); c.arc(ax + 26, 128, 24, Math.PI, 0); c.fill();
      c.fillRect(ax + 2, 128, 48, FLOOR_Y - 132);
      // inner arch rim catches window light faintly
      c.strokeStyle = "rgba(122,110,160,0.10)"; c.lineWidth = 1;
      c.beginPath(); c.arc(ax + 26, 128, 24, Math.PI, 0); c.stroke();
    }
    // pillars with base + capital
    for (const px of [58, 138, 218, 310, 410, 490]) {
      c.fillStyle = "#1e1a2e"; c.fillRect(px, 96, 12, FLOOR_Y - 96);
      c.fillStyle = "#282239"; c.fillRect(px + 1, 96, 3, FLOOR_Y - 96); // lit edge
      c.fillStyle = "#241f36"; c.fillRect(px - 3, 88, 18, 8);           // capital
      c.fillRect(px - 3, FLOOR_Y - 8, 18, 8);                            // base
    }

    _window(c, era);
    _gate(c);
    _crypt(c);
    _bannersDraw(c);
    _stalls(c);
    return cv;
  }

  // The market era, in glass: rose window + two lancets in a stone surround.
  function _window(c, era) {
    const [gd, gl, gdd] = ERA_GLASS[era] || ERA_GLASS.symmetric;
    const cx = 280, cy = 112, R = 30;
    // stone surround: ring of voussoirs + sill (reads as ARCHITECTURE)
    c.fillStyle = "#241f36"; c.beginPath(); c.arc(cx, cy, R + 6, 0, 7); c.fill();
    c.fillStyle = "#2e2742";
    for (let k = 0; k < 16; k++) {
      const a = (k / 16) * Math.PI * 2;
      c.fillRect(cx + Math.cos(a) * (R + 3) - 1, cy + Math.sin(a) * (R + 3) - 1, 2, 2);
    }
    c.fillStyle = "#241f36"; c.fillRect(cx - R - 10, cy + R + 4, R * 2 + 20, 4); // sill
    // glass: petal panes around a core, individually shaded (not a flat disc)
    c.fillStyle = gdd; c.beginPath(); c.arc(cx, cy, R, 0, 7); c.fill();
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2 + Math.PI / 8;
      const px = cx + Math.cos(a) * (R * 0.58), py = cy + Math.sin(a) * (R * 0.58);
      c.fillStyle = k % 2 ? gd : gl;
      c.beginPath(); c.ellipse(px, py, 8, 5, a, 0, 7); c.fill();
    }
    const core = c.createRadialGradient(cx, cy, 1, cx, cy, R * 0.4);
    core.addColorStop(0, gl); core.addColorStop(1, gd);
    c.fillStyle = core; c.beginPath(); c.arc(cx, cy, R * 0.38, 0, 7); c.fill();
    // lead tracery over the glass
    c.strokeStyle = "#100c18"; c.lineWidth = 2;
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2;
      c.beginPath(); c.moveTo(cx + Math.cos(a) * R * 0.36, cy + Math.sin(a) * R * 0.36);
      c.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R); c.stroke();
    }
    c.beginPath(); c.arc(cx, cy, R * 0.38, 0, 7); c.stroke();
    c.beginPath(); c.arc(cx, cy, R * 0.78, 0, 7); c.stroke();
    c.lineWidth = 3; c.strokeStyle = "#0a0812"; c.beginPath(); c.arc(cx, cy, R, 0, 7); c.stroke();
    // flanking lancets: tall pointed windows in the same glass
    for (const lx of [cx - 58, cx + 58]) {
      c.fillStyle = "#241f36"; c.fillRect(lx - 9, 86, 18, 62);
      c.beginPath(); c.arc(lx, 88, 9, Math.PI, 0); c.fill();
      c.fillStyle = gd; c.fillRect(lx - 6, 90, 12, 54);
      c.beginPath(); c.moveTo(lx - 6, 92); c.lineTo(lx, 84); c.lineTo(lx + 6, 92); c.fill();
      // diamond panes
      c.strokeStyle = "#100c18"; c.lineWidth = 1;
      for (let y = 90; y < 144; y += 8) {
        c.beginPath(); c.moveTo(lx - 6, y); c.lineTo(lx, y + 4); c.lineTo(lx + 6, y); c.stroke();
      }
      c.fillStyle = gl; c.fillRect(lx - 2, 96, 3, 4); c.fillRect(lx + 1, 116, 3, 4); // bright panes
      c.strokeStyle = "#0a0812"; c.lineWidth = 2; c.strokeRect(lx - 6, 90, 12, 54);
    }
  }

  // The GATE: where every newcomer enters the hall.
  function _gate(c) {
    const gx = GATE_X, top = 118;
    c.fillStyle = "#241f36"; c.fillRect(gx - 22, top - 4, 44, FLOOR_Y - top + 4); // surround
    c.beginPath(); c.arc(gx, top, 22, Math.PI, 0); c.fill();
    // doors (iron-banded oak), slightly ajar — warm world beyond
    c.fillStyle = "#2b2033"; c.fillRect(gx - 17, top, 34, FLOOR_Y - top);
    c.beginPath(); c.arc(gx, top, 17, Math.PI, 0); c.fill();
    c.fillStyle = "#3a2a3a";
    c.fillRect(gx - 17, top, 15, FLOOR_Y - top); // left leaf
    c.fillRect(gx + 2, top, 15, FLOOR_Y - top);  // right leaf
    c.fillStyle = "#4a4458"; // iron bands + studs
    for (const by of [top + 14, top + 40, top + 66]) {
      c.fillRect(gx - 17, by, 34, 2);
      for (let sx = gx - 14; sx < gx + 16; sx += 6) c.fillRect(sx, by - 1, 1, 1);
    }
    // the ajar slit: warm light from beyond the hall
    const slit = c.createLinearGradient(0, top, 0, FLOOR_Y);
    slit.addColorStop(0, "rgba(232,163,61,0.55)"); slit.addColorStop(1, "rgba(232,163,61,0.15)");
    c.fillStyle = slit; c.fillRect(gx - 2, top + 4, 4, FLOOR_Y - top - 4);
    // lintel plaque
    c.fillStyle = "#4a4458"; c.fillRect(gx - 10, top - 26, 20, 7);
  }

  // The CRYPT WALL: niches; a candle is lit for each fallen dynasty founder.
  function _crypt(c) {
    const cxx = CRYPT_X, top = 124;
    c.fillStyle = "#191527"; c.fillRect(cxx - 26, top - 8, 56, FLOOR_Y - top + 8);
    c.fillStyle = "#241f36"; c.fillRect(cxx - 26, top - 12, 56, 5);
    for (let row = 0; row < 2; row++) for (let col = 0; col < 3; col++) {
      const nx = cxx - 18 + col * 18, ny = top + row * 38;
      c.fillStyle = "#0b0914";
      c.fillRect(nx, ny + 6, 12, 24);
      c.beginPath(); c.arc(nx + 6, ny + 6, 6, Math.PI, 0); c.fill();
      c.strokeStyle = "rgba(122,110,160,0.12)"; c.lineWidth = 1;
      c.strokeRect(nx - 0.5, ny + 5.5, 13, 25);
    }
    // memorial plaques for the remembered
    _memorials.forEach((m, i) => {
      const col = i % 3, row = (i / 3) | 0;
      const nx = cxx - 18 + col * 18, ny = top + row * 38;
      c.fillStyle = m.ramp ? m.ramp[2] : "#7a6e62";
      c.fillRect(nx + 3, ny + 24, 6, 3); // small colored plaque; flame drawn live
    });
  }

  // Dynasty banners hang from the beam — length is wealth, color is the house.
  function _bannersDraw(c) {
    const slots = [104, 184, 376, 456];
    _banners.forEach((b, i) => {
      const bx = slots[i % slots.length];
      const len = 18 + Math.min(26, Math.round((b.wealth || 0) / 40));
      const r = b.ramp || ["#241f36", "#3a3550", "#4a4458", "#7c7790", "#b2a48e"];
      c.fillStyle = "#4a4458"; c.fillRect(bx - 7, 68, 14, 2); // rod
      c.fillStyle = r[1]; c.fillRect(bx - 5, 70, 10, len);
      c.fillStyle = r[2]; c.fillRect(bx - 5, 70, 4, len);
      c.fillStyle = r[3]; c.fillRect(bx - 1, 72, 2, 2);       // sigil stitch
      // swallowtail hem
      c.fillStyle = r[1];
      c.beginPath(); c.moveTo(bx - 5, 70 + len); c.lineTo(bx - 2, 70 + len + 5);
      c.lineTo(bx + 1, 70 + len); c.lineTo(bx + 3, 70 + len + 5); c.lineTo(bx + 5, 70 + len);
      c.closePath(); c.fill();
    });
  }

  // Market stalls dress the trading floor (the bazaar half of "castle bazaar").
  function _stalls(c) {
    for (const sx of [150, 348]) {
      // awning: muted stripes, wind-worn
      c.fillStyle = "#241f36"; c.fillRect(sx - 1, 168, 2, 44); c.fillRect(sx + 27, 168, 2, 44);
      for (let i = 0; i < 7; i++) {
        c.fillStyle = i % 2 ? "#3a2a3a" : "#4a3450";
        c.fillRect(sx - 4 + i * 5, 162, 5, 7);
      }
      c.fillStyle = "#2b2033"; c.fillRect(sx - 4, 168, 36, 2);
      // counter + wares
      c.fillStyle = "#2b2033"; c.fillRect(sx, 196, 28, 16);
      c.fillStyle = "#3a2a3a"; c.fillRect(sx, 196, 28, 3);
      c.fillStyle = "#7a4e28"; c.fillRect(sx + 3, 191, 7, 5);   // crate
      c.fillStyle = "#8a5a1e"; c.fillRect(sx + 12, 190, 6, 6);  // sack
      c.fillStyle = "#ffe08a"; c.fillRect(sx + 21, 192, 2, 1);  // a glinting coin
    }
  }

  // ── floor: stone tiles + carpet runner to the window ─────────────────────
  function _buildFloor() {
    const cv = document.createElement("canvas"); cv.width = WORLD_W; cv.height = WORLD_H;
    const c = cv.getContext("2d");
    const fg = c.createLinearGradient(0, FLOOR_Y, 0, WORLD_H);
    fg.addColorStop(0, "#242034"); fg.addColorStop(1, "#161122");
    c.fillStyle = fg; c.fillRect(0, FLOOR_Y, WORLD_W, WORLD_H - FLOOR_Y);
    c.fillStyle = "rgba(0,0,0,0.35)"; c.fillRect(0, FLOOR_Y, WORLD_W, 1);
    // tile rows, spacing loosens toward the viewer (cheap perspective)
    let y = FLOOR_Y + 5, step = 5;
    while (y < WORLD_H) {
      c.fillStyle = "rgba(0,0,0,0.18)"; c.fillRect(0, y, WORLD_W, 1);
      const off = ((y | 0) % 2) * 14;
      for (let x = -off; x < WORLD_W; x += 28) {
        c.fillStyle = "rgba(0,0,0,0.12)"; c.fillRect(x, y - step, 1, step);
      }
      y += step; step += 2;
    }
    // carpet runner under the window: worn violet-red, bordered
    c.fillStyle = "#32203a"; c.fillRect(252, FLOOR_Y + 1, 56, WORLD_H - FLOOR_Y - 1);
    c.fillStyle = "#3e2846"; c.fillRect(258, FLOOR_Y + 1, 44, WORLD_H - FLOOR_Y - 1);
    c.fillStyle = "#4a3450";
    for (let yy = FLOOR_Y + 6; yy < WORLD_H; yy += 10) c.fillRect(272, yy, 16, 2); // motif
    return cv;
  }

  function _flame(c, x, y, scale, phase) {
    const f = 1 + (Math.floor(_t * 0.3 + phase) % 2);
    c.fillStyle = "#ffe08a"; c.fillRect(x, y - f * scale, 1.5 * scale, (2 + f) * scale * 0.7);
    c.fillStyle = "#e8734a"; c.fillRect(x, y + scale * 0.5, scale, scale * 0.6);
  }

  function _glowStamp(c, x, y, r, a) {
    c.globalCompositeOperation = "lighter";
    const g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(245,200,110,${a})`);
    g.addColorStop(0.55, `rgba(232,163,61,${a * 0.45})`);
    g.addColorStop(1, "rgba(232,163,61,0)");
    c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2);
    c.globalCompositeOperation = "source-over";
  }

  function draw(ctx, cam) {
    _t += 1;
    if (!_far) _far = _buildFar();
    if (!_floor) _floor = _buildFloor();
    if (!_mid || _midEra !== cam.era || _midDirty) { _mid = _buildMid(cam.era); _midEra = cam.era; _midDirty = false; }
    ctx.drawImage(_far, -cam.x * 0.2, 0);
    ctx.drawImage(_mid, -cam.x * 0.55, 0);
    // the window is LUMINOUS — moonlight through glass, in the era's color.
    // The one bright thing on the wall; the hall's beacon. (Drawn at the mid
    // layer's parallax so it stays glued to the glass.)
    {
      const [gd2, gl2] = ERA_GLASS[cam.era] || ERA_GLASS.symmetric;
      const wx = 280 - cam.x * 0.55, wy = 112;
      ctx.globalCompositeOperation = "lighter";
      const wg = ctx.createRadialGradient(wx, wy, 4, wx, wy, 52);
      wg.addColorStop(0, _hexA(gl2, 0.34));
      wg.addColorStop(0.5, _hexA(gd2, 0.14));
      wg.addColorStop(1, _hexA(gd2, 0));
      ctx.fillStyle = wg; ctx.fillRect(wx - 52, wy - 52, 104, 104);
      // lancet glows, fainter
      for (const lx of [wx - 58, wx + 58]) {
        const lg = ctx.createRadialGradient(lx, 116, 2, lx, 116, 26);
        lg.addColorStop(0, _hexA(gl2, 0.18)); lg.addColorStop(1, _hexA(gd2, 0));
        ctx.fillStyle = lg; ctx.fillRect(lx - 26, 90, 52, 60);
      }
      ctx.globalCompositeOperation = "source-over";
    }
    ctx.save(); ctx.translate(-cam.x, 0);
    ctx.drawImage(_floor, 0, 0);
    // era light shaft from the window onto the runner
    const [, gl] = ERA_GLASS[cam.era] || ERA_GLASS.symmetric;
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = _hexA(gl, 0.05);
    ctx.beginPath(); ctx.moveTo(262, FLOOR_Y); ctx.lineTo(298, FLOOR_Y);
    ctx.lineTo(316, WORLD_H); ctx.lineTo(244, WORLD_H); ctx.closePath(); ctx.fill();
    ctx.globalCompositeOperation = "source-over";
    // torches on pillars (live flames)
    for (const px of [58, 218, 410]) {
      _glowStamp(ctx, px * 0.55 / 0.55 + 6, 120, 16, 0.10);
      ctx.fillStyle = "#4a4458"; ctx.fillRect(px + 5, 122, 2, 6);
      _flame(ctx, px + 5, 118, 1.6, px);
    }
    // gate spill: warm pool inside the door (the entrance is alive)
    _glowStamp(ctx, GATE_X, FLOOR_Y + 6, 22, 0.08);
    // crypt memorial flames — the remembered burn visibly
    _memorials.forEach((m, i) => {
      const col = i % 3, row = (i / 3) | 0;
      const nx = CRYPT_X - 18 + col * 18 + 5, ny = 124 + row * 38 + 22;
      _flame(ctx, nx, ny, 1.2, i * 3);
      _glowStamp(ctx, nx, ny, 12, 0.16);
    });
    // candle pools at each duel zone
    for (const z of ZONES) {
      _glowStamp(ctx, z.x, z.y + 8, 20 + Math.sin(_t * 0.13 + z.x) * 2, 0.12);
      ctx.fillStyle = "#3a2a1e"; ctx.fillRect(z.x - 1, z.y + 2, 2, 6);
      _flame(ctx, z.x - 1, z.y, 1, z.x);
    }
    ctx.restore();
  }

  function drawForeground(ctx, cam) {
    ctx.save(); ctx.translate(-cam.x * 1.25, 0);
    ctx.fillStyle = "#050409";
    ctx.fillRect(-20, 0, 40, WORLD_H);
    // right edge kept slim so it never occludes the crypt wall at full pan
    ctx.fillRect(WORLD_W + 2, 0, 30, WORLD_H);
    ctx.beginPath(); ctx.moveTo(-20, 0); ctx.lineTo(WORLD_W + 24, 0);
    ctx.lineTo(WORLD_W + 24, 18); ctx.quadraticCurveTo(WORLD_W / 2, 5, -20, 18);
    ctx.closePath(); ctx.fill();
    // near-black hanging lantern silhouette breaking the top edge (depth cue)
    ctx.fillStyle = "#070510";
    ctx.fillRect(150, 0, 2, 26); ctx.fillRect(146, 26, 10, 12);
    ctx.fillRect(392, 0, 2, 18); ctx.fillRect(388, 18, 10, 12);
    ctx.restore();
  }

  function _hexA(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  A.stage = { draw, drawForeground, setBanners, setMemorials,
    WORLD_W, WORLD_H, FLOOR_Y, ZONES, GATE_X, CRYPT_X, ERA_GLASS };
})();

/* FX + the bitmap font. All in-world text is drawn here (never fillText — that
   would contaminate the pixel look). Particles are pooled; the impact frame is
   the sakuga marker (rationed by the choreographer). */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  // 3x5 bitmap font, rows top->bottom, 3 bits each.
  const G = {
    "0": [7, 5, 5, 5, 7], "1": [2, 6, 2, 2, 7], "2": [7, 1, 7, 4, 7], "3": [7, 1, 3, 1, 7],
    "4": [5, 5, 7, 1, 1], "5": [7, 4, 7, 1, 7], "6": [7, 4, 7, 5, 7], "7": [7, 1, 2, 2, 2],
    "8": [7, 5, 7, 5, 7], "9": [7, 5, 7, 1, 7],
    "A": [7, 5, 7, 5, 5], "B": [6, 5, 6, 5, 6], "C": [7, 4, 4, 4, 7], "D": [6, 5, 5, 5, 6],
    "E": [7, 4, 6, 4, 7], "F": [7, 4, 6, 4, 4], "G": [7, 4, 5, 5, 7], "H": [5, 5, 7, 5, 5],
    "I": [7, 2, 2, 2, 7], "J": [1, 1, 1, 5, 7], "K": [5, 5, 6, 5, 5], "L": [4, 4, 4, 4, 7],
    "M": [5, 7, 7, 5, 5], "N": [5, 7, 7, 7, 5], "O": [7, 5, 5, 5, 7], "P": [7, 5, 7, 4, 4],
    "Q": [7, 5, 5, 6, 3], "R": [7, 5, 6, 5, 5], "S": [7, 4, 7, 1, 7], "T": [7, 2, 2, 2, 2],
    "U": [5, 5, 5, 5, 7], "V": [5, 5, 5, 5, 2], "W": [5, 5, 7, 7, 5], "X": [5, 5, 2, 5, 5],
    "Y": [5, 5, 2, 2, 2], "Z": [7, 1, 2, 4, 7],
    "$": [3, 6, 7, 3, 6], "+": [0, 2, 7, 2, 0], "-": [0, 0, 7, 0, 0], "%": [5, 1, 2, 4, 5],
    ".": [0, 0, 0, 0, 2], "·": [0, 0, 2, 0, 0], ":": [0, 2, 0, 2, 0], " ": [0, 0, 0, 0, 0],
    "/": [1, 1, 2, 4, 4], "!": [2, 2, 2, 0, 2],
  };

  function text(ctx, str, x, y, color, scale, shadow) {
    scale = scale || 1;
    const glyphs = str.toUpperCase();
    const paint = (col, ox, oy) => {
      ctx.fillStyle = col;
      let cx = Math.round(x) + ox; const yy = Math.round(y) + oy;
      for (const ch of glyphs) {
        const g = G[ch] || G[" "];
        for (let r = 0; r < 5; r++) for (let b = 0; b < 3; b++)
          if (g[r] & (4 >> b)) ctx.fillRect(cx + b * scale, yy + r * scale, scale, scale);
        cx += 4 * scale;
      }
    };
    // a 1px dark drop-shadow so labels stay legible over any part of the world
    if (shadow !== false) paint("rgba(3,2,8,0.9)", scale, scale);
    paint(color, 0, 0);
  }
  function textW(str, scale) { return str.length * 4 * (scale || 1); }

  // ── particle pool ──
  const POOL = []; for (let i = 0; i < 260; i++) POOL.push({ live: false });
  function spawn(x, y, vx, vy, life, col, grav, size) {
    for (const p of POOL) if (!p.live) {
      p.live = true; p.x = x; p.y = y; p.vx = vx; p.vy = vy;
      p.life = life; p.max = life; p.col = col; p.grav = grav || 0; p.size = size || 1;
      return;
    }
  }
  function burst(x, y, n, col, spd, grav) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 7, s = spd * (0.4 + Math.random());
      spawn(x, y, Math.cos(a) * s, Math.sin(a) * s - 0.4, 18 + Math.random() * 16, col, grav || 0.06);
    }
  }
  function updateParticles() {
    for (const p of POOL) if (p.live) {
      p.x += p.vx; p.y += p.vy; p.vy += p.grav; p.life--;
      if (p.life <= 0) p.live = false;
    }
  }
  function drawParticles(ctx) {
    for (const p of POOL) if (p.live) {
      ctx.globalAlpha = Math.min(1, p.life / p.max);
      ctx.fillStyle = p.col; ctx.fillRect(Math.round(p.x), Math.round(p.y), p.size, p.size);
    }
    ctx.globalAlpha = 1;
  }

  // ── floating numbers ──
  const FLOATS = [];
  function floatNum(str, x, y, col, scale) { FLOATS.push({ str, x, y, col, life: 60, max: 60, sc: scale || 1 }); }
  function updateFloats() {
    for (let i = FLOATS.length - 1; i >= 0; i--) {
      const f = FLOATS[i]; f.y -= 0.45; f.life--;
      if (f.life <= 0) FLOATS.splice(i, 1);
    }
  }
  function drawFloats(ctx) {
    for (const f of FLOATS) {
      ctx.globalAlpha = Math.min(1, f.life / 20);
      const w = textW(f.str, f.sc);
      // white core for readability over anything
      text(ctx, f.str, f.x - w / 2 - f.sc, f.y + f.sc, "#fff", f.sc);
      text(ctx, f.str, f.x - w / 2, f.y, f.col, f.sc);
    }
    ctx.globalAlpha = 1;
  }

  // ── inheritance orbs: rise, PAUSE at apex (grief needs a beat), then home ──
  const ORBS = [];
  function orb(x, y, targetFn) {
    ORBS.push({ x, y, vy: -1.4 - Math.random() * 0.6, phase: "rise", pause: 12 + (Math.random() * 8 | 0),
      target: targetFn, life: 140 });
  }
  function updateOrbs() {
    for (let i = ORBS.length - 1; i >= 0; i--) {
      const o = ORBS[i]; o.life--;
      if (o.phase === "rise") { o.y += o.vy; o.vy += 0.09; if (o.vy >= 0) o.phase = "pause"; }
      else if (o.phase === "pause") { if (--o.pause <= 0) o.phase = "home"; }
      else {
        const t = o.target ? o.target() : null;
        if (!t) { o.y -= 0.3; if (o.life < 100) { ORBS.splice(i, 1); continue; } }
        else {
          const dx = t.x - o.x, dy = t.y - o.y, dist = Math.hypot(dx, dy);
          if (dist < 3) { ORBS.splice(i, 1); continue; }
          o.x += dx / dist * 2.2; o.y += dy / dist * 2.2;
        }
      }
      if (o.life <= 0) ORBS.splice(i, 1);
    }
  }
  function drawOrbs(ctx) {
    for (const o of ORBS) {
      ctx.globalCompositeOperation = "lighter";
      const g = ctx.createRadialGradient(o.x, o.y, 0, o.x, o.y, 4);
      g.addColorStop(0, "rgba(255,224,138,0.9)"); g.addColorStop(1, "rgba(255,224,138,0)");
      ctx.fillStyle = g; ctx.fillRect(o.x - 4, o.y - 4, 8, 8);
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "#ffe08a"; ctx.fillRect(Math.round(o.x), Math.round(o.y), 2, 2);
    }
  }

  // ── impact frame (sakuga): 2-frame white-field/black-cracks inversion ──
  let _impact = null;
  function impact(x, y) { _impact = { x, y, life: 4 }; }
  function drawImpact(ctx, W, H) {
    if (!_impact) return;
    _impact.life--;
    if (_impact.life <= 1) { // white flash frame
      ctx.fillStyle = "rgba(255,255,255,0.9)"; ctx.fillRect(0, 0, W, H);
    } else { // cracks radiating from point
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = "#0a0812"; ctx.lineWidth = 2;
      for (let k = 0; k < 12; k++) {
        const a = (k / 12) * 7 + 0.3;
        ctx.beginPath(); ctx.moveTo(_impact.x, _impact.y);
        ctx.lineTo(_impact.x + Math.cos(a) * 300, _impact.y + Math.sin(a) * 300); ctx.stroke();
      }
    }
    if (_impact.life <= 0) _impact = null;
  }

  // ── cut-in (eyes-strip band) ──
  let _cut = null;
  function cutIn(title, subtitle, ramp) { _cut = { title, subtitle, ramp: ramp || null, life: 108, max: 108 }; }
  function drawCutIn(ctx, W, H) {
    if (!_cut) return;
    _cut.life--;
    const t = _cut.life / _cut.max;
    const inn = Math.min(1, (_cut.max - _cut.life) / 12), outn = Math.min(1, _cut.life / 12);
    const p = Math.min(inn, outn);
    const bandH = 46, cy = H * 0.42;
    ctx.save();
    ctx.globalAlpha = p;
    // diagonal band
    ctx.fillStyle = "#16102c"; ctx.beginPath();
    ctx.moveTo(0, cy - bandH / 2 + 8); ctx.lineTo(W, cy - bandH / 2 - 8);
    ctx.lineTo(W, cy + bandH / 2 - 8); ctx.lineTo(0, cy + bandH / 2 + 8); ctx.closePath(); ctx.fill();
    // halftone speed lines
    ctx.globalCompositeOperation = "lighter";
    ctx.strokeStyle = "rgba(167,139,250,0.15)"; ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 6) { ctx.beginPath(); ctx.moveTo(x, cy - 30); ctx.lineTo(x + 14, cy + 30); ctx.stroke(); }
    ctx.globalCompositeOperation = "source-over";
    const col = _cut.ramp ? _cut.ramp[4] : "#ffe08a";
    text(ctx, _cut.title, 14, cy - 10, col, 2);
    if (_cut.subtitle) text(ctx, _cut.subtitle, 14, cy + 8, "#c8c4d8", 1);
    ctx.restore();
    if (_cut.life <= 0) _cut = null;
  }
  function cutBusy() { return _cut && _cut.life > 20; }

  A.fx = { text, textW, spawn, burst, updateParticles, drawParticles,
    floatNum, updateFloats, drawFloats, orb, updateOrbs, drawOrbs,
    impact, drawImpact, cutIn, drawCutIn, cutBusy };
})();

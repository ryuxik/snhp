/* The flower is the PHENOTYPE of the negotiation genome — drawn, not stored.
   Same six blocks the knights inherit, rendered as a gothic bloom. Beauty is
   strategy made visible; a mutation reshapes the flower, a child's flower is a
   cross of its parents'. Drawable at any scale: a tiny crest above a knight, or
   the full-screen "Bloom of the Generation" in stained glass.

     tactic  -> species (tulip / rose / thistle / lily / orchid / nightshade)
     knob    -> hue (cool deal-rate -> warm margin)
     aggr    -> petal count & spread (showiness)
     patience-> stem height
     bundle  -> petal layering
     staked  -> gilt, luminous edges
     energy  -> bloom fullness (a starving flower WILTS) */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  const SPECIES = { anchorer: "thistle", boulware: "nightshade", conceder: "tulip",
    mirror: "orchid", patient: "lily", closer: "rose" };

  function hsl(h, s, l) { return `hsl(${h},${s}%,${l}%)`; }

  // genome -> palette + form params
  function bloom(g) {
    const warmth = g.pareto_knob;              // 0 cool -> 1 warm
    const hue = 270 - warmth * 250;            // 270 violet -> 20 ember (wraps warm)
    const hue2 = (hue + 24) % 360;
    const sat = g.staked ? 62 : 52;
    return {
      species: SPECIES[g.tactic_family] || "tulip",
      petalDark: hsl(hue, sat, 30), petalMid: hsl(hue, sat, 46),
      petalLite: hsl(hue2, sat, 64), petalHi: hsl(hue2, sat - 8, 80),
      center: g.staked ? "#ffe08a" : hsl((hue + 40) % 360, 50, 60),
      stem: "#2e5744", leaf: "#3a6a4a", outline: hsl(hue, 40, 12),
      petals: 5 + Math.round(g.open_aggression * 6),
      spread: 0.55 + g.open_aggression * 0.5,
      height: 0.5 + g.patience * 0.5,
      layers: 1 + Math.round(((g.bundle_focus && g.bundle_focus.length ? Math.max(...g.bundle_focus) : 0.25)) * 2.4),
      gilt: !!g.staked,
      warmth,
    };
  }

  // Draw a bloom centered at (cx, floorY), scaled by `u` (unit px per art-pixel),
  // fullness f in [0,1] (energy -> how open/full; low f = wilt).
  function draw(ctx, g, cx, floorY, u, f) {
    f = f == null ? 1 : Math.max(0.12, f);
    const b = bloom(g);
    const stemH = 12 * u * b.height * (0.6 + 0.4 * f);
    const headY = floorY - stemH;
    const droop = (1 - f) * 6 * u; // wilt: head sags and stem bows

    // stem (bows when wilting)
    ctx.strokeStyle = b.stem; ctx.lineWidth = Math.max(1, 1.4 * u);
    ctx.beginPath();
    ctx.moveTo(cx, floorY);
    ctx.quadraticCurveTo(cx + droop * 0.6, floorY - stemH * 0.5, cx + droop, headY + droop);
    ctx.stroke();
    // a leaf
    ctx.fillStyle = b.leaf;
    ctx.beginPath();
    ctx.ellipse(cx - 3 * u, floorY - stemH * 0.45, 4 * u, 1.6 * u, -0.5, 0, 7);
    ctx.fill();
    if (b.height > 0.7) { ctx.beginPath(); ctx.ellipse(cx + 3 * u, floorY - stemH * 0.62, 3.4 * u, 1.4 * u, 0.6, 0, 7); ctx.fill(); }

    const hx = cx + droop, hy = headY + droop;
    if (b.gilt) { // luminous halo for staked blooms
      ctx.globalCompositeOperation = "lighter";
      const gg = ctx.createRadialGradient(hx, hy, 0, hx, hy, 10 * u);
      gg.addColorStop(0, "rgba(255,224,138,0.28)"); gg.addColorStop(1, "rgba(255,224,138,0)");
      ctx.fillStyle = gg; ctx.fillRect(hx - 10 * u, hy - 10 * u, 20 * u, 20 * u);
      ctx.globalCompositeOperation = "source-over";
    }
    _head(ctx, b, hx, hy, u, f);
  }

  function _head(ctx, b, x, y, u, f) {
    switch (b.species) {
      case "tulip": return _tulip(ctx, b, x, y, u, f);
      case "rose": return _rose(ctx, b, x, y, u, f);
      case "thistle": return _thistle(ctx, b, x, y, u, f);
      case "lily": return _lily(ctx, b, x, y, u, f);
      case "orchid": return _orchid(ctx, b, x, y, u, f);
      case "nightshade": return _nightshade(ctx, b, x, y, u, f);
    }
  }

  function _petal(ctx, x, y, w, h, ang, cols) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.fillStyle = cols[0]; ctx.beginPath(); ctx.ellipse(0, -h * 0.5, w, h, 0, 0, 7); ctx.fill();
    ctx.fillStyle = cols[1]; ctx.beginPath(); ctx.ellipse(-w * 0.15, -h * 0.55, w * 0.7, h * 0.72, 0, 0, 7); ctx.fill();
    ctx.fillStyle = cols[2]; ctx.beginPath(); ctx.ellipse(w * 0.2, -h * 0.35, w * 0.3, h * 0.4, 0, 0, 7); ctx.fill();
    ctx.restore();
  }

  function _tulip(ctx, b, x, y, u, f) {
    // cupped petals, opening with fullness
    const open = 0.3 + f * 0.7, n = 5;
    for (let i = 0; i < n; i++) {
      const a = (i / n - 0.5) * b.spread * 2.2 * open;
      _petal(ctx, x, y, 2.6 * u, 6 * u * (0.7 + 0.3 * f), a, [b.petalDark, b.petalMid, b.petalLite]);
    }
    // front petals (brighter)
    for (let i = 0; i < 3; i++) {
      const a = (i - 1) * b.spread * 0.7 * open;
      _petal(ctx, x, y + 0.5 * u, 2.2 * u, 5 * u, a, [b.petalMid, b.petalLite, b.petalHi]);
    }
  }

  function _rose(ctx, b, x, y, u, f) {
    // concentric whorls (layers), thorned
    const rings = 2 + b.layers;
    for (let r = rings; r >= 1; r--) {
      const rad = r * 1.5 * u * (0.6 + 0.4 * f);
      const n = 5 + r;
      const cols = r > rings * 0.6 ? [b.petalDark, b.petalMid, b.petalMid]
        : [b.petalMid, b.petalLite, b.petalHi];
      for (let i = 0; i < n; i++) {
        const a = (i / n) * 7 + r * 0.5;
        _petal(ctx, x + Math.cos(a) * rad * 0.3, y + Math.sin(a) * rad * 0.3,
          1.6 * u, rad, a + Math.PI / 2, cols);
      }
    }
    ctx.fillStyle = b.center; ctx.beginPath(); ctx.arc(x, y, 1.2 * u, 0, 7); ctx.fill();
  }

  function _thistle(ctx, b, x, y, u, f) {
    // a spiky ovoid crown of bracts + a burst of filaments
    ctx.fillStyle = b.petalMid;
    ctx.beginPath(); ctx.ellipse(x, y, 3 * u, 4 * u, 0, 0, 7); ctx.fill();
    ctx.fillStyle = b.petalDark;
    for (let i = 0; i < 10; i++) {
      const a = i / 10 * 7;
      ctx.beginPath();
      ctx.moveTo(x, y + 2 * u);
      ctx.lineTo(x + Math.cos(a) * 3 * u, y + 2 * u + Math.sin(a) * 3 * u);
      ctx.lineTo(x + Math.cos(a + 0.2) * 2.4 * u, y + 2 * u + Math.sin(a + 0.2) * 2.4 * u);
      ctx.closePath(); ctx.fill();
    }
    // crown filaments (the showy spikes)
    ctx.strokeStyle = b.petalHi; ctx.lineWidth = Math.max(1, 0.8 * u);
    const spikes = Math.round(6 + b.spread * 8);
    for (let i = 0; i < spikes; i++) {
      const a = -Math.PI / 2 + (i / spikes - 0.5) * b.spread * 2.6;
      ctx.beginPath(); ctx.moveTo(x, y - 2 * u);
      ctx.lineTo(x + Math.cos(a) * 5 * u * (0.6 + 0.4 * f), y - 2 * u + Math.sin(a) * 5 * u * (0.6 + 0.4 * f));
      ctx.stroke();
    }
  }

  function _lily(ctx, b, x, y, u, f) {
    // 6 long recurved tepals, a tall trumpet
    const n = 6;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * 7;
      _petal(ctx, x, y, 1.8 * u, 6.5 * u * (0.7 + 0.3 * f), a, [b.petalDark, b.petalMid, b.petalLite]);
    }
    // stamens
    ctx.strokeStyle = b.center; ctx.lineWidth = Math.max(1, 0.7 * u);
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i - 2) * 0.3;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(a) * 3 * u, y + Math.sin(a) * 3 * u); ctx.stroke();
      ctx.fillStyle = "#ffe08a"; ctx.fillRect(x + Math.cos(a) * 3 * u - u * 0.5, y + Math.sin(a) * 3 * u - u * 0.5, u, u);
    }
  }

  function _orchid(ctx, b, x, y, u, f) {
    // bilateral symmetry: 2 upper, 2 side, 1 lip — the mirror's bloom
    _petal(ctx, x, y, 3 * u, 5 * u, -0.5, [b.petalDark, b.petalMid, b.petalLite]);
    _petal(ctx, x, y, 3 * u, 5 * u, 0.5, [b.petalDark, b.petalMid, b.petalLite]);
    _petal(ctx, x, y, 2.4 * u, 4.4 * u, -1.4, [b.petalMid, b.petalLite, b.petalHi]);
    _petal(ctx, x, y, 2.4 * u, 4.4 * u, 1.4, [b.petalMid, b.petalLite, b.petalHi]);
    // lip
    ctx.fillStyle = b.petalHi; ctx.beginPath(); ctx.ellipse(x, y + 3 * u, 2.2 * u, 2.6 * u, 0, 0, 7); ctx.fill();
    ctx.fillStyle = b.center; ctx.beginPath(); ctx.arc(x, y, 1.4 * u, 0, 7); ctx.fill();
    // symmetric spots (the reflection motif)
    ctx.fillStyle = b.petalDark;
    ctx.fillRect(x - 2 * u, y + 2.5 * u, u, u); ctx.fillRect(x + u, y + 2.5 * u, u, u);
  }

  function _nightshade(ctx, b, x, y, u, f) {
    // downturned dark bells + glossy berry — patient poison
    const n = 5;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * 7 + Math.PI / 2;
      _petal(ctx, x, y, 2 * u, 4.5 * u, a, [b.outline, b.petalDark, b.petalMid]);
    }
    ctx.fillStyle = b.petalDark; ctx.beginPath(); ctx.arc(x, y, 2.6 * u, 0, 7); ctx.fill();
    ctx.fillStyle = "#1a0f22"; ctx.beginPath(); ctx.arc(x, y + 1 * u, 1.8 * u, 0, 7); ctx.fill();
    ctx.fillStyle = b.petalHi; ctx.fillRect(x - u, y, u, u); // a cold glint
  }

  A.flora = { draw, bloom, SPECIES };
})();

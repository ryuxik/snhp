/* The people. Tiny 8×16 pixel folk with a 2-frame walk, a ground shadow, and a
   sel-out outline so they pop against the façades. STRATEGY IS THE SILHOUETTE
   here too: each named regular has a persistent look (hat + prop + build +
   hair) so you can follow Maria across the week and watch her stop coming to
   the sticker block. Anonymous crowd walkers are drawn from a small
   deterministic archetype table (bounded sprite cache). Gray-drain is baked per
   sprite in coarse buckets so the sticker crowd fades with the block. */
(function () {
  "use strict";
  const B = (window.Block = window.Block || {});
  const P = B.pal;

  const SW = 8, SH = 16, PAD = 1;
  const CW = SW + PAD * 2, CH = SH + PAD * 2;

  const PROPCOL = { tote: "#8a5a3a", coffee: "#eae6dc", backpack: "#3a4a6a",
    satchel: "#6a4a2a", cane: "#c0b090", shopbag: "#d0cfe0", none: null };

  // 12 anonymous archetypes — deterministic, so the ambient crowd reproduces
  const ARCH = [
    { skin: "tan",  hair: "brown", top: "#3a4a6a", bottom: "#262a38", prop: "tote",     hat: "none" },
    { skin: "pale", hair: "sandy", top: "#2e5a8a", bottom: "#232a3a", prop: "coffee",   hat: "none" },
    { skin: "brown",hair: "black", top: "#3a8a62", bottom: "#2a2438", prop: "backpack", hat: "phones" },
    { skin: "tan",  hair: "black", top: "#8a5a4a", bottom: "#3a3550", prop: "none",     hat: "cap" },
    { skin: "pale", hair: "brown", top: "#c05a8a", bottom: "#2a2438", prop: "shopbag",  hat: "beanie" },
    { skin: "dark", hair: "black", top: "#c07a2a", bottom: "#2b2338", prop: "none",     hat: "none" },
    { skin: "tan",  hair: "gray",  top: "#6a5a7a", bottom: "#3a3550", prop: "tote",     hat: "scarf" },
    { skin: "brown",hair: "black", top: "#4a6a8a", bottom: "#232a3a", prop: "satchel",  hat: "none" },
    { skin: "pale", hair: "blonde",top: "#3a8a8a", bottom: "#2a2438", prop: "coffee",   hat: "none" },
    { skin: "tan",  hair: "brown", top: "#a04a4a", bottom: "#2b2338", prop: "none",     hat: "beanie" },
    { skin: "dark", hair: "black", top: "#5a5a8a", bottom: "#232a3a", prop: "backpack", hat: "phones" },
    { skin: "pale", hair: "white", top: "#7a6a8a", bottom: "#3a3550", prop: "cane",     hat: "none" },
  ];
  function archetype(i) { return ARCH[((i % ARCH.length) + ARCH.length) % ARCH.length]; }

  // ── sprite cache (lookKey | frame | grayBucket) ─────────────────────────────
  const _cache = new Map();
  function key(look, frame, gb) {
    return [look.skin, look.hair, look.top, look.bottom, look.prop, look.hat, look.big ? 1 : 0, frame, gb].join("|");
  }
  function drainCol(hex, g) { return g ? P.drain(hex, g) : hex; }

  function build(look, frame, gb) {
    const k = key(look, frame, gb);
    if (_cache.has(k)) return _cache.get(k);
    const g = gb / 10;
    const cv = document.createElement("canvas"); cv.width = CW; cv.height = CH;
    const c = cv.getContext("2d"); c.imageSmoothingEnabled = false;
    const skin = drainCol(P.SKIN[look.skin] || "#caa079", g);
    const hair = drainCol(P.HAIR[look.hair] || "#4a3428", g);
    const top = drainCol(look.top, g);
    const topLo = drainCol(P.mix(look.top, "#000000", 0.28), g);
    const bot = drainCol(look.bottom, g);
    const big = !!look.big;
    const rect = (X, Y, W, H, col) => { c.fillStyle = col; c.fillRect(PAD + X, PAD + Y, W, H); };

    // legs (behind torso), 2-frame stagger
    if (frame === 0) { rect(2, 10, 2, 5, bot); rect(4, 10, 2, 5, bot); rect(2, 15, 2, 1, "#1a1620"); rect(4, 15, 2, 1, "#1a1620"); }
    else { rect(1, 10, 2, 5, bot); rect(5, 10, 2, 5, bot); rect(1, 15, 2, 1, "#1a1620"); rect(5, 15, 2, 1, "#1a1620"); }

    // backpack sits behind the torso
    if (look.prop === "backpack") rect(0, 6, 2, 5, drainCol(PROPCOL.backpack, g));
    if (look.prop === "satchel") { rect(0, 9, 2, 3, drainCol(PROPCOL.satchel, g)); rect(2, 6, 3, 1, drainCol(P.mix(PROPCOL.satchel, "#000", 0.2), g)); }

    // torso + arms
    if (big) { rect(1, 5, 6, 6, top); rect(0, 6, 1, 4, top); rect(7, 6, 1, 4, top); }
    else { rect(2, 5, 4, 5, top); rect(1, 6, 1, 4, top); rect(6, 6, 1, 4, top); }
    rect(2, 9, 4, 1, topLo);                                   // hem shade

    // head
    rect(2, 1, 4, 4, skin); rect(3, 5, 2, 1, skin);            // face + neck
    rect(3, 2, 1, 1, "#1a1620"); rect(4, 2, 1, 1, "#1a1620");  // eyes

    // hair + hats
    if (look.hair !== "bald") { rect(2, 0, 4, 1, hair); rect(2, 1, 1, 2, hair); rect(5, 1, 1, 2, hair); }
    switch (look.hat) {
      case "scarf":  rect(2, 5, 4, 1, drainCol("#c04a5a", g)); rect(1, 4, 1, 2, drainCol("#c04a5a", g)); break;
      case "phones": rect(2, 0, 4, 1, "#20202a"); rect(1, 1, 1, 2, drainCol("#e05a7a", g)); rect(6, 1, 1, 2, drainCol("#e05a7a", g)); break;
      case "beanie": rect(2, -1, 4, 2, drainCol(P.mix(look.top, "#ffffff", 0.15), g)); rect(1, 0, 1, 1, drainCol(look.top, g)); rect(6, 0, 1, 1, drainCol(look.top, g)); break;
      case "cap":    rect(2, -1, 4, 2, drainCol(P.mix(look.top, "#000", 0.1), g)); rect(5, 1, 2, 1, drainCol(P.mix(look.top, "#000", 0.25), g)); break;
    }

    // hand props (front)
    const pc = PROPCOL[look.prop] ? drainCol(PROPCOL[look.prop], g) : null;
    if (look.prop === "tote") { rect(6, 8, 2, 4, pc); rect(5, 6, 1, 3, drainCol(P.mix(PROPCOL.tote, "#000", 0.2), g)); }
    else if (look.prop === "coffee") { rect(6, 7, 2, 2, pc); rect(6, 6, 2, 1, "#3a2a2a"); }
    else if (look.prop === "cane") { rect(6, 7, 1, 8, pc); rect(5, 7, 2, 1, pc); }
    else if (look.prop === "shopbag") { rect(6, 9, 3, 4, pc); rect(6, 8, 3, 1, drainCol(P.mix(PROPCOL.shopbag, "#000", 0.3), g)); }

    _cache.set(k, _outline(cv));
    return _cache.get(k);
  }

  // sel-out: a 1px dark ring so folk read against busy façades
  function _outline(cv) {
    const c = cv.getContext("2d");
    const img = c.getImageData(0, 0, CW, CH), d = img.data;
    const idx = (x, y) => (y * CW + x) * 4;
    const op = (x, y) => x >= 0 && x < CW && y >= 0 && y < CH && d[idx(x, y) + 3] > 0;
    const out = document.createElement("canvas"); out.width = CW; out.height = CH;
    const oc = out.getContext("2d"); oc.imageSmoothingEnabled = false;
    oc.drawImage(cv, 0, 0);
    oc.fillStyle = "#100c18";
    for (let y = 0; y < CH; y++) for (let x = 0; x < CW; x++) {
      if (op(x, y)) continue;
      if (op(x - 1, y) || op(x + 1, y) || op(x, y - 1) || op(x, y + 1)) oc.fillRect(x, y, 1, 1);
    }
    return out;
  }

  // Blit a walker. footX/footY = the feet on the sidewalk (world/local coords).
  // opts: facing(±1), frame(0/1), bob, alpha, gray(0..1), umbrella, tint(fn)
  function draw(ctx, look, footX, footY, opts) {
    opts = opts || {};
    const gb = Math.max(0, Math.min(5, Math.round((opts.gray || 0) * 10 / 2))) * 2; // buckets of 0.2
    const spr = build(look, opts.frame ? 1 : 0, gb);
    const a = opts.alpha == null ? 1 : opts.alpha;
    if (a <= 0.02) return;
    const dx = Math.round(footX - CW / 2), dy = Math.round(footY - SH - PAD + (opts.bob || 0));
    // ground shadow
    ctx.globalAlpha = 0.28 * a;
    ctx.fillStyle = "#0a0810";
    ctx.beginPath(); ctx.ellipse(footX, footY - 0.5, 4, 1.4, 0, 0, 7); ctx.fill();
    ctx.globalAlpha = a;
    if (opts.facing < 0) { ctx.save(); ctx.translate(dx + CW, dy); ctx.scale(-1, 1); ctx.drawImage(spr, 0, 0); ctx.restore(); }
    else ctx.drawImage(spr, dx, dy);
    // umbrella in the rain (drawn live so it can tint with the sky)
    if (opts.umbrella) {
      const uc = opts.tint ? opts.tint(look.top) : look.top;
      ctx.fillStyle = uc;
      ctx.fillRect(footX - 6, dy - 4, 12, 2);
      ctx.fillRect(footX - 4, dy - 6, 8, 2);
      ctx.fillStyle = "#2a2733"; ctx.fillRect(footX, dy - 4, 1, 6);
    }
    ctx.globalAlpha = 1;
  }

  B.walkers = { draw, archetype, WIDTH: CW, HEIGHT: CH };
})();

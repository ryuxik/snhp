/* Hand-authored pixel-art agents. STRATEGY IS THE SILHOUETTE: each tactic
   family = a distinct cloak archetype + a signature prop, so you can read how
   an agent negotiates from across the hall:

     anchorer  — pauldron cloak + warhammer   (opens huge, hits hard)
     boulware  — high-collar + tower shield   (concedes nothing until the end)
     conceder  — bell cloak + ledger scroll   (deal-maker, meets you fast)
     mirror    — half-cape + mirror shield    (reflects your concessions)
     patient   — tattered robe + hourglass    (time is their weapon)
     closer    — half-cape + dagger           (strikes at the deadline)

   8 hand-authored hex ramps (shadows rotate violet, highlights candle-warm);
   sel-out outlines; 2 walk frames; seeded blink. Same genome ⇒ same look, so a
   child visibly wears its parents' parts. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  const RAMPS = [
    ["#2A1430", "#6E2F3C", "#B04A4A", "#E08A6A", "#FFD9A8"], // ember-rose
    ["#2B1D30", "#7A4E28", "#C08A3A", "#E8C060", "#FFEBA8"], // gold
    ["#1E2030", "#2E5744", "#4A8A62", "#7FC48F", "#D2F0C0"], // verdigris
    ["#1E1E34", "#2C4E63", "#3F7E96", "#6FB8C8", "#C8ECF0"], // steel-cyan
    ["#1C1834", "#2E3A72", "#4A5FAE", "#7E93DC", "#C8D6FF"], // royal blue
    ["#221434", "#4A2E72", "#7A54B2", "#A78BFA", "#E2D2FF"], // violet (staked)
    ["#26142E", "#63285C", "#A2468E", "#D67EB8", "#FFD0E8"], // fuchsia
    ["#241C28", "#4E4340", "#7E6E62", "#B2A48E", "#E8E0C8"], // bone/ash
  ];
  const TACTICS = ["anchorer", "boulware", "conceder", "mirror", "patient", "closer"];

  // ── authored part matrices ────────────────────────────────────────────────
  // chars: . transparent · o/d/m/l/h ramp 0-4 · s skin · x face-shadow
  //        a steel-light · A steel-dark · g gold
  const CLOAKS = {
    // pauldron (anchorer): massive shoulders, brute silhouette
    pauldron: [
      "ddllmmmmlldd",
      "dmmlmmmmlmmd",
      "ddmmmmmmmmdd",
      ".dmmmmmmmld.",
      ".dmmmmmmmld.",
      ".ddmmmmmlld.",
      ".dmmmmmmlld.",
      ".dmmmmmmlld.",
      ".dmmmmmmlld.",
      ".dmmmmmmlld.",
      ".ddmmmmmlld.",
      ".dmmmmmmlld.",
      ".dddddddddd.",
      "............",
    ],
    // high-collar (boulware): collar swallows the head, a wall of a man
    collar: [
      ".ddmmmmmlld.",
      ".dmmmmmmmld.",
      ".ddmmmmmld..",
      "..dmmmmmld..",
      "..dmmmmmld..",
      "..dmmmmlld..",
      "..dmmmmlld..",
      ".ddmmmmllld.",
      ".dmmmmmllld.",
      ".dmmmmmllld.",
      ".dmmmmmllld.",
      ".dmmmmmllld.",
      ".ddddddddd..",
      "............",
    ],
    // bell (conceder): friendly merchant flare
    bell: [
      "...dmmmld...",
      "...dmmmld...",
      "..ddmmmlld..",
      "..dmmmmlld..",
      "..dmmmmlld..",
      ".ddmmmmllld.",
      ".dmmmmmllld.",
      ".dmmmmmllld.",
      "ddmmmmmlllld",
      "dmmmmmmlllld",
      "dmmmmmmlllld",
      "dmmmmmmlllld",
      "dddddddddddd",
      "............",
    ],
    // half-cape (mirror/closer): asymmetric, legs show — a duelist's cut
    cape: [
      "..dmmmmlld..",
      "..dmmmmlld..",
      ".ddmmmmld...",
      ".dmmmmmld...",
      ".dmmmmmld...",
      ".dmmmmlld...",
      ".dmmmmlld...",
      ".dmmmmld....",
      ".dmmmmld....",
      ".dmmmld.....",
      ".dmmld......",
      ".ddld.......",
      "............",
      "............",
    ],
    // tattered (patient): a hermit's robe, ragged hem
    tattered: [
      "...dmmmld...",
      "..ddmmmld...",
      "..dmmmmlld..",
      "..dmmmmlld..",
      ".ddmmmmlld..",
      ".dmmmmmlld..",
      ".dmmmmmlld..",
      ".dmmmmmllld.",
      ".dmmmmmllld.",
      ".dm.mmmll.d.",
      ".dm.mm.ll.d.",
      ".d..mm.l..d.",
      "............",
      "............",
    ],
  };
  const TACTIC_CLOAK = { anchorer: "pauldron", boulware: "collar", conceder: "bell",
    mirror: "cape", patient: "tattered", closer: "cape" };

  const HEADS = {
    hood: [
      "...dd...",
      "..dmmd..",
      ".dmmmld.",
      ".dmmmld.",
      ".dxxxxd.",
      ".dxxxxd.",
      "..dxxd..",
      "........",
    ],
    helm: [
      ".dddddd.",
      ".dmmlld.",
      ".dmmlld.",
      ".dxxxxd.",
      ".dmmlld.",
      ".dmmlld.",
      "..dddd..",
      "........",
    ],
    bare: [
      "..dddd..",
      ".ddddld.",
      ".dssssd.",
      ".dssssd.",
      ".dssssd.",
      "..ssss..",
      "..d..d..",
      "........",
    ],
    crowned: [
      "g.g..g.g",
      ".gggggg.",
      ".dssssd.",
      ".dssssd.",
      ".dssssd.",
      "..ssss..",
      "..d..d..",
      "........",
    ],
  };

  const LEGS = [ // 2 walk frames, 8 wide x 5 tall
    ["..dd.dd.", "..dd.dd.", "..dd.dd.", "..oo.oo.", "........"],
    [".dd...dd", ".dd...dd", "..dd.dd.", "..oo.oo.", "........"],
  ];

  // props: 6 wide x 12 tall, drawn at the right hand (or left for shields)
  const PROPS = {
    anchorer: [ // warhammer
      ".aaaa.", ".aAAa.", ".aAAa.", ".aaaa.", "...A..", "...A..",
      "...A..", "...A..", "...A..", "...A..", "......", "......"],
    boulware: [ // tower shield (drawn front-left)
      ".dlld.", "dllmld", "dlmmld", "dlmmld", "dlmmld", "dlmmld",
      "dlmmld", "dlmmld", "dlmmld", ".dmld.", "..dd..", "......"],
    conceder: [ // ledger scroll
      "......", "......", "......", ".hhhh.", ".haah.", ".hhhh.",
      "..hh..", "......", "......", "......", "......", "......"],
    mirror: [ // mirror shield: a bright disc
      "......", ".ddd..", "dhhhd.", "dhahd.", "dhhhd.", ".ddd..",
      "......", "......", "......", "......", "......", "......"],
    patient: [ // hourglass staff
      "..gg..", ".g..g.", "..gg..", "..AA..", "..AA..", "..AA..",
      "..AA..", "..AA..", "..AA..", "..AA..", "..AA..", "......"],
    closer: [ // dagger, low and ready
      "......", "......", "......", "......", "...a..", "...a..",
      "...a..", "..AAA.", "...A..", "......", "......", "......"],
  };

  const FIXED = { s: "#caa88f", x: "#100c18", a: "#c8c4d8", A: "#4a4458", g: "#ffe08a" };

  const W = 18, H = 26;
  const HEAD_X = 5, HEAD_Y = 0, CLOAK_X = 3, CLOAK_Y = 7, LEG_X = 5, LEG_Y = 20;

  function genomeKey(g) {
    return [g.tactic_family, g.staked ? 1 : 0, +g.pareto_knob.toFixed(2),
      +g.open_aggression.toFixed(2), +g.walk_margin.toFixed(2)].join("|");
  }

  function look(g) {
    const ti = Math.max(0, TACTICS.indexOf(g.tactic_family));
    return {
      rampIdx: g.staked ? 5 : (ti + (g.pareto_knob > 0.5 ? 0 : 3)) % RAMPS.length === 5
        ? (ti + 4) % RAMPS.length
        : (ti + (g.pareto_knob > 0.5 ? 0 : 3)) % RAMPS.length,
      cloak: TACTIC_CLOAK[g.tactic_family] || "bell",
      head: g.open_aggression > 0.72 ? "helm" : (g.pareto_knob > 0.85 ? "crowned" : (g.walk_margin > 0.5 ? "hood" : "bare")),
      prop: g.tactic_family,
      staked: !!g.staked,
    };
  }

  function _paint(c, mat, ox, oy, ramp) {
    for (let y = 0; y < mat.length; y++) {
      const row = mat[y];
      for (let x = 0; x < row.length; x++) {
        const ch = row[x];
        if (ch === ".") continue;
        let col;
        if (ch === "o") col = ramp[0];
        else if (ch === "d") col = ramp[1];
        else if (ch === "m") col = ramp[2];
        else if (ch === "l") col = ramp[3];
        else if (ch === "h") col = ramp[4];
        else col = FIXED[ch] || ramp[2];
        c.fillStyle = col;
        c.fillRect(ox + x, oy + y, 1, 1);
      }
    }
  }

  const _cache = new Map();

  function build(g) {
    const key = genomeKey(g);
    if (_cache.has(key)) return _cache.get(key);
    const L = look(g);
    const ramp = RAMPS[L.rampIdx];
    const frames = [];
    for (let f = 0; f < 2; f++) {
      const cv = document.createElement("canvas");
      cv.width = W; cv.height = H;
      const c = cv.getContext("2d");
      c.imageSmoothingEnabled = false;
      const legsShow = L.cloak === "cape" || L.cloak === "tattered";
      if (legsShow) _paint(c, LEGS[f], LEG_X, LEG_Y + 1, ramp);
      _paint(c, CLOAKS[L.cloak], CLOAK_X, CLOAK_Y + (f && !legsShow ? 1 : 0), ramp);
      _paint(c, HEADS[L.head], HEAD_X, HEAD_Y + (f ? 1 : 0), ramp);
      // eye glints inside hood/helm shadow
      if (L.head === "hood" || L.head === "helm") {
        c.fillStyle = ramp[4];
        c.fillRect(HEAD_X + 2, HEAD_Y + 4 + (f ? 1 : 0), 1, 1);
        c.fillRect(HEAD_X + 5, HEAD_Y + 4 + (f ? 1 : 0), 1, 1);
      } else {
        c.fillStyle = FIXED.x;
        c.fillRect(HEAD_X + 2, HEAD_Y + 3 + (f ? 1 : 0), 1, 1);
        c.fillRect(HEAD_X + 5, HEAD_Y + 3 + (f ? 1 : 0), 1, 1);
      }
      // signature prop (the strategy, readable at a glance)
      const propX = L.prop === "boulware" ? 0 : 12;
      _paint(c, PROPS[L.prop] || PROPS.conceder, propX, 9, ramp);
      if (L.staked) { c.fillStyle = FIXED.g; c.fillRect(7, 8, 3, 1); } // gilt clasp
      frames.push(_outline(cv, ramp[0]));
    }
    const sprite = { f: frames, w: W, h: H, ramp, look: L };
    _cache.set(key, sprite);
    return sprite;
  }

  function _outline(cv, outCol) {
    const c = cv.getContext("2d");
    const img = c.getImageData(0, 0, W, H);
    const d = img.data, idx = (x, y) => (y * W + x) * 4;
    const opaque = (x, y) => x >= 0 && x < W && y >= 0 && y < H && d[idx(x, y) + 3] > 0;
    const out = document.createElement("canvas"); out.width = W; out.height = H + 2;
    const oc = out.getContext("2d"); oc.imageSmoothingEnabled = false;
    oc.fillStyle = "rgba(0,0,0,0.4)";
    oc.beginPath(); oc.ellipse(W / 2, H + 0.5, 6, 1.6, 0, 0, 7); oc.fill();
    oc.drawImage(cv, 0, 0);
    oc.fillStyle = outCol;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (opaque(x, y)) continue;
      if (opaque(x - 1, y) || opaque(x + 1, y) || opaque(x, y - 1) || opaque(x, y + 1))
        oc.fillRect(x, y, 1, 1);
    }
    return out;
  }

  // Blit at world (x,y)=feet. opts: facing, frame(0/1), bob, glow, blink, pennant
  function draw(ctx, g, x, y, opts) {
    opts = opts || {};
    const s = build(g);
    const cv = s.f[opts.frame ? 1 : 0];
    const dx = Math.round(x - W / 2), dy = Math.round(y - H - 1 + (opts.bob || 0));
    if (opts.glow) {
      ctx.globalCompositeOperation = "lighter";
      const gcol = s.look.staked ? "rgba(255,224,138," : "rgba(167,139,250,";
      const r = 8 + opts.glow * 6;
      const grd = ctx.createRadialGradient(x, y - 8, 0, x, y - 8, r);
      grd.addColorStop(0, gcol + (0.10 + 0.16 * opts.glow) + ")");
      grd.addColorStop(1, gcol + "0)");
      ctx.fillStyle = grd; ctx.fillRect(x - r, y - 8 - r, r * 2, r * 2);
      ctx.globalCompositeOperation = "source-over";
    }
    if (opts.facing < 0) {
      ctx.save(); ctx.translate(dx + W, dy); ctx.scale(-1, 1);
      ctx.drawImage(cv, 0, 0); ctx.restore();
    } else {
      ctx.drawImage(cv, dx, dy);
    }
    // blink: cover the eye pixels for a beat (desynchronized life)
    if (opts.blink) {
      ctx.fillStyle = "#100c18";
      ctx.fillRect(dx + (opts.facing < 0 ? W - 11 : 6), dy + 3, 2, 2);
      ctx.fillRect(dx + (opts.facing < 0 ? W - 8 : 9), dy + 3, 2, 2);
    }
    // backed-house pennant: a tiny diegetic flag, never a glow ring
    if (opts.pennant) {
      ctx.fillStyle = "#4a4458"; ctx.fillRect(Math.round(x), dy - 4, 1, 4);
      ctx.fillStyle = opts.pennant; ctx.fillRect(Math.round(x) + 1, dy - 4, 3, 2);
    }
  }

  // A body slice (head / torso / hem) for the child-assembly choreography.
  function slice(g, band) {
    const s = build(g);
    const bounds = band === "head" ? [0, 9] : band === "torso" ? [9, 17] : [17, H + 2];
    return { canvas: s.f[0], sy: bounds[0], sh: bounds[1] - bounds[0], w: W, ramp: s.ramp };
  }

  function rampFor(g) { return build(g).ramp; }
  function rampForHouse(name) {
    let h = 2166136261;
    for (let i = 0; i < name.length; i++) { h ^= name.charCodeAt(i); h = (h * 16777619) >>> 0; }
    return RAMPS[h % RAMPS.length];
  }

  A.sprites = { build, draw, slice, rampFor, rampForHouse, RAMPS, look, genomeKey, TACTICS, TACTIC_CLOAK };
})();

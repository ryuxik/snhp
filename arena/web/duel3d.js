/* The 3D Featured Duel — the legible hero negotiation.
   A voxel-gothic stage where two SNHP agents negotiate a multi-issue deal you can
   actually READ: three issue rails (tug-of-war), each side's HIDDEN true want shown
   only to the viewer (dramatic irony), a tell (each knight leans into the issue it
   secretly values), a deadline candle, offers landing as blows, the close, and an
   honest reveal. Driven for now by a canned script (the make-or-break prototype);
   later by the server `featured.*` stream.

   Public: A.duel3d = { mount(el), play(script), stop(), active(), resize() }.
   Requires global THREE (vendored). */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  const T = window.THREE;

  // ── palette (the arena brand, in light) ──
  const COL = {
    bg: 0x07060d, violet: 0xa78bfa, violetDeep: 0x2a2140, gold: 0xffe08a,
    prime: 0x8fd0ff, chal: 0xff9d6b, primeK: 0x40639a, chalK: 0xb06534,
    ink: 0xf0eff5, dim: 0x9a95b0,
    good: 0x7fc48f, warn: 0xe8734a, stone: 0x2a2536, rail: 0x3a3450,
  };
  const ISSUES = ["PRICE", "DELIVERY", "TERMS"]; // 3 reads cleanest

  let scene, cam, renderer, root, running = false, raf = 0;
  let knights = {}, rails = [], candle = null, scoreboard = null;
  let script = null, sT = 0, step = 0, phase = "idle", phaseT = 0, lastActor = null;
  let shake = 0, closeGlow = null, closeT = 0;
  let clock = null;
  const BEAT_GAP = 1.9; // seconds between offers — paced for legibility

  // ── tiny helper: draw text to a canvas → THREE texture (no font loading) ──
  function textTexture(lines, opts) {
    opts = opts || {};
    const w = opts.w || 256, h = opts.h || 128;
    const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
    const c = cv.getContext("2d");
    if (opts.bg) { c.fillStyle = opts.bg; c.fillRect(0, 0, w, h); }
    c.textAlign = opts.align || "center"; c.textBaseline = "middle";
    const fam = "600 " + (opts.size || 44) + "px ui-monospace, Menlo, monospace";
    (Array.isArray(lines) ? lines : [lines]).forEach((ln, i, arr) => {
      c.font = ln.font || fam;
      c.fillStyle = ln.color || opts.color || "#f0eff5";
      const x = opts.align === "left" ? 8 : w / 2;
      const y = h / 2 + (i - (arr.length - 1) / 2) * (opts.line || 52);
      if (ln.glow) { c.shadowColor = ln.glow; c.shadowBlur = 18; }
      c.fillText(ln.t != null ? ln.t : ln, x, y);
      c.shadowBlur = 0;
    });
    const tex = new T.CanvasTexture(cv);
    tex.minFilter = T.LinearFilter; tex.magFilter = T.LinearFilter;
    return tex;
  }
  function label3d(lines, opts) {
    const tex = textTexture(lines, opts);
    const m = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    m.userData.tex = tex;
    const s = (opts && opts.scale) || 1;
    m.scale.set(s * (tex.image.width / tex.image.height), s, 1);
    return m;
  }

  // dark BackSide shell → a crafted outline around a voxel (cel-shaded feel)
  function addOutline(mesh, k) {
    const s = new T.Mesh(mesh.geometry, new T.MeshBasicMaterial({ color: 0x090712, side: T.BackSide }));
    s.scale.setScalar(k || 1.07); mesh.add(s);
  }

  // ── a cloaked knight: helmet + visor + pauldrons + an arm on the deal ──
  function knight(color, facing) {
    const g = new T.Group();
    const mat = (hex, ei) => new T.MeshStandardMaterial({ color: hex, roughness: 0.85, metalness: 0.05, flatShading: true, emissive: hex, emissiveIntensity: ei == null ? 0.04 : ei });
    const dark = (hex) => new T.MeshStandardMaterial({ color: hex, roughness: 0.92 });
    const cloak = mat(color, 0.1);
    const b1 = new T.Mesh(new T.BoxGeometry(1.7, 1.9, 1.1), cloak); b1.position.y = 1.0;   // robe
    const b2 = new T.Mesh(new T.BoxGeometry(1.25, 1.1, 0.9), cloak); b2.position.y = 2.15;  // chest
    const sh = new T.Mesh(new T.BoxGeometry(2.15, 0.42, 1.2), dark(0x14101f)); sh.position.y = 2.55; // pauldrons
    const helm = new T.Mesh(new T.BoxGeometry(0.78, 0.82, 0.78), mat(color, 0.14)); helm.position.y = 3.18;
    const visor = new T.Mesh(new T.BoxGeometry(0.82, 0.17, 0.12), new T.MeshBasicMaterial({ color: 0x080810 }));
    visor.position.set(0, 3.16, 0.4 * facing);
    const crest = new T.Mesh(new T.BoxGeometry(0.14, 0.55, 0.5), mat(color, 0.35)); crest.position.y = 3.78;
    // an arm reaching in toward the rails — hands on the deal
    const arm = new T.Mesh(new T.BoxGeometry(1.35, 0.34, 0.34), mat(color, 0.1));
    arm.position.set(0.95 * facing, 2.05, 0.55); arm.rotation.z = -0.18 * facing;
    const hand = new T.Mesh(new T.BoxGeometry(0.38, 0.38, 0.38), dark(0x1c1630));
    hand.position.set(1.62 * facing, 1.92, 0.55);
    // banner-crest behind
    const pole = new T.Mesh(new T.BoxGeometry(0.1, 1.8, 0.1), dark(0x0f0c1a)); pole.position.set(-0.95 * facing, 2.3, -0.5);
    g.add(b1, b2, sh, helm, visor, crest, arm, hand, pole);
    [b1, b2, helm, sh, arm].forEach(m => addOutline(m, 1.08));
    g.rotation.y = facing > 0 ? 0.22 : -0.22;
    g.userData = { base: 0, lean: 0, glowMat: cloak, hood: helm };
    return g;
  }

  // ── one issue rail: track + live marker + two ghost "true want" bands ──
  function rail(name, y) {
    const g = new T.Group(); g.position.y = y;
    const LEN = 5.6;
    const track = new T.Mesh(new T.BoxGeometry(LEN, 0.1, 0.1),
      new T.MeshStandardMaterial({ color: COL.rail, roughness: 0.9, emissive: 0x1a1530, emissiveIntensity: 0.5 }));
    g.add(track);
    // end caps cue direction: buyer (left, orange) vs seller (right, blue)
    const cap = (x, hex) => { const m = new T.Mesh(new T.BoxGeometry(0.16, 0.58, 0.58),
      new T.MeshStandardMaterial({ color: hex, emissive: hex, emissiveIntensity: 0.7 })); m.position.set(x, 0, 0); g.add(m); return m; };
    cap(-LEN / 2, COL.chal); cap(LEN / 2, COL.prime);
    // the ONE bold thing: the current offer, a gold diamond
    const mk = new T.Mesh(new T.OctahedronGeometry(0.46),
      new T.MeshStandardMaterial({ color: COL.gold, emissive: COL.gold, emissiveIntensity: 1.0, roughness: 0.4 }));
    g.add(mk);
    // hidden true-wants: thin translucent slivers, shown ONLY on the issue a
    // side actually cares about (setTruth decides) — no center pile-up
    const sliver = (hex) => { const m = new T.Mesh(new T.BoxGeometry(0.2, 1.75, 0.2),
      new T.MeshBasicMaterial({ color: hex, transparent: true, opacity: 0.7 })); m.visible = false; g.add(m); return m; };
    const wantS = sliver(COL.prime), wantB = sliver(COL.chal);
    // label lives in the DOM UI layer (crisp, never clipped) — see buildUI()
    g.userData = { LEN, mk, wantS, wantB, pos: 0.5, tpos: 0.5, name };
    return g;
  }

  function railX(r, p) { return (p - 0.5) * r.userData.LEN; } // p in 0..1 → x

  // ── build the whole stage ──
  function build() {
    scene = new T.Scene();
    scene.background = new T.Color(0x0b0916); // subtle dark ground (not void black)
    scene.fog = new T.FogExp2(0x0b0916, 0.03);
    root = new T.Group(); scene.add(root);

    cam = new T.PerspectiveCamera(42, 16 / 9, 0.1, 100);
    cam.position.set(0, 4.2, 13); cam.lookAt(0, 2.4, 0);

    // lights: violet ambient + a soft key so the knights read + warm candle + window rim
    scene.add(new T.AmbientLight(0x342f52, 1.35));
    const key = new T.DirectionalLight(0xfff0e0, 0.75); key.position.set(3, 9, 11); scene.add(key);
    const candleLight = new T.PointLight(0xffcaa0, 1.8, 34, 2); candleLight.position.set(-1.5, 3.5, 5.0);
    const winLight = new T.PointLight(0x9f88ff, 1.3, 44, 2); winLight.position.set(0, 6, -6);
    const rim = new T.DirectionalLight(0xb49cff, 0.6); rim.position.set(-3, 7, -9); // silhouette rim from the window
    scene.add(candleLight, winLight, rim);
    clock = { candleLight };

    // floor
    const floor = new T.Mesh(new T.BoxGeometry(40, 0.5, 26),
      new T.MeshStandardMaterial({ color: 0x0d0a16, roughness: 1 }));
    floor.position.y = -0.25; root.add(floor);
    // back wall + rose window (a glowing disc + spokes)
    const wall = new T.Mesh(new T.BoxGeometry(40, 24, 0.5),
      new T.MeshStandardMaterial({ color: 0x12101e, roughness: 1 }));
    wall.position.set(0, 8, -8); root.add(wall);
    const rose = new T.Mesh(new T.CircleGeometry(3.2, 32),
      new T.MeshBasicMaterial({ color: 0x7a63d8 }));
    rose.position.set(0, 7.5, -7.6); root.add(rose);
    const roseIn = new T.Mesh(new T.CircleGeometry(1.2, 24),
      new T.MeshBasicMaterial({ color: 0xbfa8ff })); roseIn.position.set(0, 7.5, -7.55); root.add(roseIn);
    for (let i = 0; i < 8; i++) { const s = new T.Mesh(new T.BoxGeometry(0.14, 6.4, 0.1),
      new T.MeshBasicMaterial({ color: 0x2a2140 })); s.position.set(0, 7.5, -7.5); s.rotation.z = i * Math.PI / 8; root.add(s); }
    // two banners flanking (house colours)
    [[-6.5, COL.prime], [6.5, COL.chal]].forEach(([x, c]) => {
      const b = new T.Mesh(new T.BoxGeometry(0.9, 4.6, 0.1),
        new T.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.12 }));
      b.position.set(x, 6.5, -6.8); root.add(b);
    });

    // the table
    const table = new T.Mesh(new T.BoxGeometry(5.2, 0.5, 2.4),
      new T.MeshStandardMaterial({ color: 0x241c30, roughness: 0.8, emissive: 0x120c22, emissiveIntensity: 0.3 }));
    table.position.set(0, 1.2, 2.2); root.add(table);

    // knights
    knights.prime = knight(COL.primeK, 1); knights.prime.position.set(-4.8, 0, 1.9); knights.prime.userData.baseX = -4.8;
    knights.chal = knight(COL.chalK, -1); knights.chal.position.set(4.8, 0, 1.9); knights.chal.userData.baseX = 4.8;
    root.add(knights.prime, knights.chal);

    // issue rails between them at chest height (helmets rise above, table below)
    rails = ISSUES.map((n, i) => rail(n, 3.25 - i * 0.7));
    rails.forEach(r => { r.position.z = 2.4; root.add(r); });

    // candle (deadline clock)
    candle = new T.Group();
    const stick = new T.Mesh(new T.BoxGeometry(0.3, 2.2, 0.3),
      new T.MeshStandardMaterial({ color: 0xd8cbb0, roughness: 1 })); stick.position.y = 1.1;
    const flame = new T.Mesh(new T.BoxGeometry(0.22, 0.5, 0.22),
      new T.MeshBasicMaterial({ color: 0xffe08a })); flame.position.y = 2.45;
    candle.add(stick, flame); candle.position.set(-2.7, 1.55, 3.8); candle.scale.set(0.55, 0.55, 0.55);
    candle.userData = { stick, flame, full: 2.2 }; root.add(candle);

    // close glow (hidden until close)
    closeGlow = new T.PointLight(0xffe08a, 0, 24, 2); closeGlow.position.set(0, 2.6, 2.2); scene.add(closeGlow);

    // reveal scoreboard (hidden until reveal), a big billboard
    scoreboard = new T.Group(); scoreboard.visible = false; scene.add(scoreboard);

    buildUI(); // crisp DOM labels tracking the 3D anchors
  }

  // ── one offer = one BEAT: the actor strikes, the moved marker snaps ──
  function fireTurn(turn) {
    rails.forEach(r => {
      const p = turn.pos[r.userData.name]; if (p == null) return;
      if (Math.abs(p - r.userData.tpos) > 0.03) { r.userData.pop = 1; }  // struck → snap+flash
      r.userData.tpos = p;
    });
    const kn = turn.actor === "prime" ? knights.prime : knights.chal;
    kn.userData.lunge = 1;                 // the acting knight jabs forward
    shake = 0.55; lastActor = turn.actor;
  }
  function setTruth(truth) {
    // show each side's hidden want ONLY on the issue it actually cares about
    // (a strong deviation from 0.5) — this is the logroll, made legible.
    rails.forEach(r => {
      const n = r.userData.name, s = truth.wantS[n], b = truth.wantB[n];
      const showS = Math.abs(s - 0.5) > 0.15, showB = Math.abs(b - 0.5) > 0.15;
      r.userData.wantS.visible = showS; if (showS) r.userData.wantS.position.x = railX(r, s);
      r.userData.wantB.visible = showB; if (showB) r.userData.wantB.position.x = railX(r, b);
    });
  }

  // reveal is a DOM overlay (crisp text, precise layout, no 3D-scale guessing)
  let revealEl = null;
  function revealDom() {
    if (revealEl) return revealEl;
    revealEl = document.createElement("div");
    revealEl.id = "duel-reveal";
    revealEl.style.cssText = [
      "position:fixed", "left:50%", "bottom:6%", "transform:translateX(-50%) translateY(20px)",
      "width:min(560px,90vw)", "padding:20px 24px", "border-radius:14px",
      "background:rgba(10,8,18,0.92)", "border:1px solid rgba(167,139,250,0.45)",
      "box-shadow:0 20px 60px rgba(0,0,0,0.55)", "backdrop-filter:blur(8px)",
      "font-family:ui-monospace,Menlo,monospace", "color:#f0eff5", "pointer-events:none",
      "opacity:0", "transition:opacity .6s ease, transform .6s ease", "z-index:5",
    ].join(";");
    document.body.appendChild(revealEl);
    return revealEl;
  }
  function hideReveal() { if (revealEl) { revealEl.style.opacity = "0"; revealEl.style.transform = "translateX(-50%) translateY(20px)"; } }
  function showReveal(rev) {
    phase = "reveal"; phaseT = 0;
    const el = revealDom();
    const maxv = rev.ceiling * 1.05;
    const bar = (t, v, c) => `<div style="display:flex;align-items:center;gap:10px;margin:7px 0">
        <span style="width:96px;font-size:12px;color:#aca6c2">${t}</span>
        <span style="flex:1;height:16px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden">
          <i style="display:block;height:100%;width:${(100 * v / maxv).toFixed(1)}%;background:${c}"></i></span>
        <b style="width:44px;text-align:right;font-variant-numeric:tabular-nums">${v.toFixed(2)}</b></div>`;
    el.innerHTML =
      `<div style="font-size:11px;letter-spacing:.24em;color:#ffe08a;text-transform:uppercase;margin-bottom:12px">the pie they made</div>` +
      bar("naive split", rev.naive, "#e8734a") +
      bar("SNHP", rev.snhp, "#7fc48f") +
      bar("best possible", rev.ceiling, "#a78bfa") +
      `<div style="font-size:12.5px;line-height:1.6;color:#c9c4dc;margin-top:12px">${rev.line}</div>`;
    requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateX(-50%) translateY(0)"; });
  }

  // ── DOM UI layer: every readable label is crisp HTML tracking a 3D anchor
  // (no baked textures → no clipping, pixel-sharp, trivially aligned) ──
  let uiEl = null, uiItems = [];
  function buildUI() {
    if (uiEl) uiEl.remove();
    uiEl = document.createElement("div"); uiEl.id = "duel-ui";
    uiEl.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:100000;font-family:ui-monospace,Menlo,monospace";
    document.body.appendChild(uiEl);
    const mk = (html, align) => { const d = document.createElement("div");
      d.style.cssText = "position:absolute;white-space:nowrap;will-change:transform;line-height:1.25";
      d.dataset.align = align || "center"; d.innerHTML = html; uiEl.appendChild(d); return d; };
    uiItems = [
      { el: mk('<div style="font-size:19px;font-weight:600;letter-spacing:.09em;color:#cfeaff;text-shadow:0 0 14px rgba(143,208,255,.65)">SNHP PRIME</div><div style="font-size:11px;letter-spacing:.05em;color:#8891a6;text-align:center;margin-top:2px">the shipped agent</div>'),
        world: new T.Vector3(-4.8, 5.1, 1.9) },
      { el: mk('<div style="font-size:19px;font-weight:600;letter-spacing:.09em;color:#ffd0b3;text-shadow:0 0 14px rgba(255,157,107,.65)">THE CHALLENGER</div><div style="font-size:11px;letter-spacing:.05em;color:#8891a6;text-align:center;margin-top:2px">what evolution found</div>'),
        world: new T.Vector3(4.8, 5.1, 1.9) },
    ];
    rails.forEach(r => {
      uiItems.push({ el: mk('<span style="font-size:15px;letter-spacing:.14em;color:#eceaf4;text-shadow:0 1px 3px #000">' + r.userData.name + '</span>', "right"),
        world: new T.Vector3(-r.userData.LEN / 2 - 0.5, r.position.y + 0.02, r.position.z) });
    });
  }
  const _uv = new T.Vector3();
  function updateUI() {
    if (!uiEl) return;
    const w = renderer.domElement.clientWidth, h = renderer.domElement.clientHeight;
    for (const it of uiItems) {
      _uv.copy(it.world).project(cam);
      const behind = _uv.z > 1; it.el.style.display = behind ? "none" : "block";
      if (behind) continue;
      const x = (_uv.x * 0.5 + 0.5) * w, y = (-_uv.y * 0.5 + 0.5) * h;
      const ax = it.el.dataset.align === "right" ? "-100%" : "-50%";
      it.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(" + ax + ",-50%)";
    }
  }

  // ── main loop ──
  function tick(dt) {
    sT += dt;
    // candle idle flicker
    if (clock) clock.candleLight.intensity = 1.25 + Math.sin(sT * 9) * 0.15 + Math.random() * 0.05;
    candle.userData.flame.scale.y = 0.85 + Math.sin(sT * 12) * 0.15;

    // rail markers: snap hard right after a strike, then settle; pop = flash+scale
    rails.forEach(r => {
      const snappy = r.userData.pop > 0.35 ? 16 : 6;
      r.userData.pos += (r.userData.tpos - r.userData.pos) * Math.min(1, dt * snappy);
      r.userData.mk.position.x = railX(r, r.userData.pos);
      r.userData.pop = Math.max(0, (r.userData.pop || 0) - dt * 2.6);
      r.userData.mk.scale.setScalar(1 + r.userData.pop * 0.8);
      r.userData.mk.rotation.y += dt * 1.6; r.userData.mk.rotation.x = 0.35;
      r.userData.mk.material.emissiveIntensity = 0.9 + r.userData.pop * 2.2 + Math.sin(sT * 5 + r.position.y) * 0.1;
    });

    // playback: one beat every BEAT_GAP seconds (paced so each offer reads)
    if (script && (phase === "trade" || phase === "closing")) {
      phaseT += dt;
      if (phase === "trade" && phaseT >= BEAT_GAP) {
        if (step < script.turns.length) {
          fireTurn(script.turns[step]); step++; phaseT = 0;
          const frac = 1 - step / script.turns.length;   // candle burns down
          candle.userData.stick.scale.y = Math.max(0.12, frac);
          candle.userData.flame.position.y = 0.2 + 2.0 * Math.max(0.12, frac);
        } else { phase = "closing"; phaseT = 0; }
      } else if (phase === "closing" && phaseT >= 1.1) { doClose(); }
    }
    // knight lunge: quick forward jab on a strike, easing back to stance
    ["prime", "chal"].forEach(k => {
      const kn = knights[k], sign = k === "prime" ? 1 : -1;
      kn.userData.lunge = Math.max(0, (kn.userData.lunge || 0) - dt * 3.2);
      const L = kn.userData.lunge;
      kn.position.x = kn.userData.baseX + sign * L * 0.55;   // step in
      kn.rotation.x = -L * 0.16;                             // lean into it
      kn.userData.glowMat.emissiveIntensity = 0.04 + L * 0.35;
    });
    // close glow decay
    if (closeT > 0) { closeT -= dt; closeGlow.intensity = Math.max(0, closeT * 6); }

    // camera choreography: wide → push-in during trade → pull back at reveal
    cameraBeat(dt);

    // shake
    if (shake > 0) { shake = Math.max(0, shake - dt * 2.2);
      cam.position.x += (Math.random() - 0.5) * shake * 0.25;
      cam.position.y += (Math.random() - 0.5) * shake * 0.18; }

    drawFrame();
  }
  function drawFrame() {
    renderer.setViewport(0, 0, window.innerWidth, window.innerHeight);
    renderer.render(scene, cam);
    updateUI();
  }

  let camGoal = { pos: new T.Vector3(0, 4.2, 13), look: new T.Vector3(0, 2.4, 0) };
  const _look = new T.Vector3();
  function cameraBeat() {
    if (phase === "reveal") { camGoal.pos.set(0, 4.2, 12.5); camGoal.look.set(0, 3.0, 2.0); }
    else if (phase === "close") { camGoal.pos.set(0, 3.4, 9.5); camGoal.look.set(0, 2.5, 2.0); }
    else if (phase === "trade" || phase === "closing") {
      // steady frame that gently leans toward whoever just struck (no aimless drift)
      const bias = ((knights.chal.userData.lunge || 0) - (knights.prime.userData.lunge || 0)) * 1.7;
      camGoal.pos.set(bias, 3.6, 12.6); camGoal.look.set(bias * 0.35, 2.2, 1.9);
    } else { camGoal.pos.set(0, 3.9, 14); camGoal.look.set(0, 2.2, 1.5); }
    cam.position.lerp(camGoal.pos, 0.045);
    _look.lerp(camGoal.look, 0.05); cam.lookAt(_look);
  }

  function doClose() {
    phase = "close"; closeT = 2.2; closeGlow.intensity = 12; shake = 1.0;
    setTimeout(() => { if (script && script.reveal) showReveal(script.reveal); }, 1400);
  }

  // ── lifecycle ──
  function mount(el) {
    if (renderer) return;
    build();
    renderer = new T.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setClearColor(COL.bg, 1);
    (el || document.body).appendChild(renderer.domElement);
    renderer.domElement.style.cssText = "position:fixed;inset:0;width:100%;height:100%;display:block;";
    resize();
    window.addEventListener("resize", resize);
  }
  function resize() {
    if (!renderer) return;
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
  }
  let last = 0;
  function loop(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - last) / 1000 || 0); last = now;
    tick(dt); raf = requestAnimationFrame(loop);
  }
  function play(s) {
    script = s; step = 0; sT = 0; phase = "intro"; phaseT = 0;
    hideReveal();
    if (script.truth) setTruth(script.truth);
    // reset rails to opening positions
    rails.forEach(r => { r.userData.pos = 0.5; r.userData.tpos = 0.5; });
    running = true; last = performance.now();
    // brief establishing beat, then trade (phaseT primed so the first offer fires)
    setTimeout(() => { if (running) { phase = "trade"; phaseT = BEAT_GAP; } }, 2400);
    raf = requestAnimationFrame(loop);
  }
  function stop() { running = false; cancelAnimationFrame(raf); }
  function active() { return running; }

  // debug: freeze a specific state for screenshotting (bypasses timing)
  function _debug(which) {
    running = false; cancelAnimationFrame(raf);
    if (which === "trade" || which === "strike") {
      phase = "trade"; hideReveal();
      const mid = { PRICE: 0.80, DELIVERY: 0.51, TERMS: 0.24 };
      rails.forEach(r => { const p = mid[r.userData.name]; r.userData.pos = r.userData.tpos = p; r.userData.mk.position.x = railX(r, p); r.userData.mk.scale.setScalar(1); });
      if (script && script.truth) setTruth(script.truth);
      candle.userData.stick.scale.y = 0.5; candle.userData.flame.position.y = 1.2;
      let bias = 0;
      if (which === "strike") { // freeze mid-strike: PRICE hit by Prime
        const pr = rails.find(r => r.userData.name === "PRICE");
        pr.userData.pop = 1; pr.userData.mk.scale.setScalar(1.8); pr.userData.mk.material.emissiveIntensity = 3.0;
        knights.prime.userData.lunge = 1; knights.prime.position.x = -4.8 + 0.55; knights.prime.rotation.x = -0.16;
        knights.prime.userData.glowMat.emissiveIntensity = 0.39; bias = -1.7;
      }
      cam.position.set(bias, 3.6, 12.6); _look.set(bias * 0.35, 2.2, 1.9); cam.lookAt(_look);
    } else if (which === "reveal") {
      if (script && script.reveal) showReveal(script.reveal);
      cam.position.set(0, 4.4, 12.5); _look.set(0, 4.0, 3); cam.lookAt(_look);
    }
    drawFrame();
  }

  // debug capture: readPixels the GL buffer into a 2D canvas overlay so the
  // preview screenshot tool (which can't composite WebGL) can capture it.
  function _capture() {
    const gl = renderer.getContext();
    const w = renderer.domElement.width, h = renderer.domElement.height;
    const buf = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    let c2 = document.getElementById("cap2d");
    if (!c2) { c2 = document.createElement("canvas"); c2.id = "cap2d";
      c2.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:99999"; document.body.appendChild(c2); }
    c2.width = w; c2.height = h;
    const ctx = c2.getContext("2d"), img = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) { const s = (h - 1 - y) * w * 4; img.data.set(buf.subarray(s, s + w * 4), y * w * 4); }
    ctx.putImageData(img, 0, 0);
    return w + "x" + h;
  }

  function stateOf() { return { phase, step, phaseT: +phaseT.toFixed(2), running, sT: +sT.toFixed(1),
    turns: script ? script.turns.length : -1, pos: rails.map(r => +r.userData.pos.toFixed(2)) }; }
  // manually advance the sim (the preview tab pauses rAF; this drives tick directly)
  function _advance(sec) { running = false; cancelAnimationFrame(raf); let t = 0; while (t < sec) { tick(0.033); t += 0.033; } return stateOf(); }
  A.duel3d = { mount, play, stop, active, resize, _phase: () => phase, _debug, _capture, _advance, _state: stateOf };
})();

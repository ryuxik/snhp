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
  let script = null, sT = 0, step = 0, phase = "idle", phaseT = 0;
  let shake = 0, closeGlow = null, closeT = 0;
  let clock = null;

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

  // ── a cloaked knight: helmet + visor + pauldrons + an arm on the deal ──
  function knight(color, facing) {
    const g = new T.Group();
    const mat = (hex, ei) => new T.MeshStandardMaterial({ color: hex, roughness: 0.72, metalness: 0.18, emissive: hex, emissiveIntensity: ei == null ? 0.08 : ei });
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
    const lab = label3d(name, { size: 44, color: "#e6e2f0", scale: 0.78 });
    lab.position.set(-LEN / 2 - 1.0, 0.8, 0); // clear of the knight, above the rail
    g.add(lab);
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
    scene.add(candleLight, winLight);
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
    knights.prime = knight(COL.primeK, 1); knights.prime.position.set(-4.8, 0, 1.9);
    knights.chal = knight(COL.chalK, -1); knights.chal.position.set(4.8, 0, 1.9);
    root.add(knights.prime, knights.chal);
    // nameplates
    const npP = label3d([{ t: "SNHP PRIME", color: "#bfe4ff", glow: "#8fd0ff" }, { t: "the shipped agent", color: "#9aa3b8", font: "500 30px ui-monospace,monospace" }], { size: 46, line: 52, scale: 0.95 });
    npP.position.set(-4.8, 4.7, 1.9); root.add(npP);
    const npC = label3d([{ t: "THE CHALLENGER", color: "#ffc7a6", glow: "#ff9d6b" }, { t: "what evolution found", color: "#9aa3b8", font: "500 30px ui-monospace,monospace" }], { size: 42, line: 52, scale: 0.95 });
    npC.position.set(4.8, 4.7, 1.9); root.add(npC);

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
  }

  // ── the canned script → drive markers, tells, candle, close, reveal ──
  function applyTurn(turn) {
    // turn.pos = {PRICE, DELIVERY, TERMS} in 0..1 (seller-favoured = 1)
    rails.forEach(r => { const p = turn.pos[r.userData.name]; if (p != null) r.userData.tpos = p; });
    shake = 0.5; // offer lands as a blow
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

  // ── main loop ──
  function tick(dt) {
    sT += dt;
    // candle idle flicker
    if (clock) clock.candleLight.intensity = 1.25 + Math.sin(sT * 9) * 0.15 + Math.random() * 0.05;
    candle.userData.flame.scale.y = 0.85 + Math.sin(sT * 12) * 0.15;

    // rail markers ease toward target; jump feel via shake
    rails.forEach(r => {
      r.userData.pos += (r.userData.tpos - r.userData.pos) * Math.min(1, dt * 6);
      r.userData.mk.position.x = railX(r, r.userData.pos);
      r.userData.mk.rotation.y += dt * 1.6; r.userData.mk.rotation.x = 0.35;
      r.userData.mk.material.emissiveIntensity = 0.85 + Math.sin(sT * 5 + r.position.y) * 0.15;
    });

    // script playback
    if (script && phase !== "reveal" && phase !== "done") {
      phaseT += dt;
      if (phase === "trade" && step < script.turns.length && phaseT >= script.turns[step].at) {
        const tn = script.turns[step];
        applyTurn(tn);
        // tell: the offering side leans toward the issue it values
        const kn = tn.actor === "prime" ? knights.prime : knights.chal;
        kn.userData.lean = 1;
        // candle burns down with rounds
        const frac = 1 - (step + 1) / script.turns.length;
        candle.userData.stick.scale.y = Math.max(0.15, frac);
        candle.userData.stick.position.y = 1.1 * Math.max(0.15, frac);
        candle.userData.flame.position.y = 0.1 + 2.2 * Math.max(0.15, frac);
        step++;
        if (step >= script.turns.length) { phase = "closing"; phaseT = 0; }
      }
      if (phase === "closing" && phaseT > 0.8) { doClose(); }
    }
    // knight tells ease back
    ["prime", "chal"].forEach(k => {
      const kn = knights[k]; const target = kn.userData.lean * (k === "prime" ? -0.12 : 0.12);
      kn.userData.lean *= (1 - Math.min(1, dt * 3));
      kn.rotation.x += ((target) - kn.rotation.x) * Math.min(1, dt * 5);
      kn.userData.glowMat.emissiveIntensity = 0.18 + kn.userData.lean * 0.5;
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
  }

  let camGoal = { pos: new T.Vector3(0, 4.2, 13), look: new T.Vector3(0, 2.4, 0) };
  const _look = new T.Vector3();
  function cameraBeat() {
    if (phase === "reveal") { camGoal.pos.set(0, 4.4, 12.5); camGoal.look.set(0, 4.0, 3); }
    else if (phase === "closing") { camGoal.pos.set(0.4, 3.4, 8.5); camGoal.look.set(0, 2.5, 2.2); }
    else if (phase === "trade") { // slow drift, framing the three rails + both knights
      const p = Math.min(1, sT / 12);
      camGoal.pos.set(Math.sin(sT * 0.16) * 1.0, 3.8 - p * 0.2, 13.5 - p * 1.0);
      camGoal.look.set(0, 2.2, 1.9);
    } else { camGoal.pos.set(0, 3.9, 14); camGoal.look.set(0, 2.2, 1.5); }
    cam.position.lerp(camGoal.pos, 0.03);
    _look.lerp(camGoal.look, 0.04); cam.lookAt(_look);
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
    // brief establishing beat, then trade
    setTimeout(() => { if (running) { phase = "trade"; phaseT = 0; } }, 2200);
    raf = requestAnimationFrame(loop);
  }
  function stop() { running = false; cancelAnimationFrame(raf); }
  function active() { return running; }

  // debug: freeze a specific state for screenshotting (bypasses timing)
  function _debug(which) {
    running = false; cancelAnimationFrame(raf);
    if (which === "trade") {
      phase = "trade"; hideReveal();
      const mid = { PRICE: 0.80, DELIVERY: 0.51, TERMS: 0.24 };
      rails.forEach(r => { const p = mid[r.userData.name]; r.userData.pos = r.userData.tpos = p; r.userData.mk.position.x = railX(r, p); });
      if (script && script.truth) setTruth(script.truth);
      knights.prime.rotation.x = -0.1; knights.prime.userData.glowMat.emissiveIntensity = 0.55;
      knights.chal.rotation.x = 0.1; knights.chal.userData.glowMat.emissiveIntensity = 0.55;
      candle.userData.stick.scale.y = 0.5; candle.userData.stick.position.y = 0.55; candle.userData.flame.position.y = 1.2;
      cam.position.set(0, 3.7, 13.2); _look.set(0, 2.1, 1.9); cam.lookAt(_look);
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

  A.duel3d = { mount, play, stop, active, resize, _phase: () => phase, _debug, _capture };
})();

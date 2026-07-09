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
  const COL = { // only the keys 3D materials actually use; UI colors live in the DOM strings
    bg: 0x07060d, gold: 0xffe08a,
    prime: 0x8fd0ff, chal: 0xff9d6b, primeK: 0x40639a, chalK: 0xb06534,
    rail: 0x3a3450,
  };
  let issueNames = ["PRICE", "DELIVERY", "TERMS"]; // default; replays may bring 4

  let scene, cam, renderer, root, running = false, raf = 0;
  let knights = {}, rails = [], dust = null;
  let script = null, sT = 0, step = 0, phase = "idle", phaseT = 0;
  let truth = null; // each side's hidden utility (wants + weights) — drives payoff meters
  let shake = 0, closeGlow = null, closeT = 0;
  let clock = null;
  const BEAT_GAP = 1.9; // seconds between offers — paced for legibility

  // (all text lives in the crisp DOM layer — see buildUI / revealDom)

  // dark BackSide shell → a crafted inked outline around a mesh (Witch Hat contour)
  function addOutline(mesh, k) {
    const s = new T.Mesh(mesh.geometry, new T.MeshBasicMaterial({ color: 0x0a0713, side: T.BackSide }));
    s.scale.setScalar(k || 1.07); s.userData.outline = true; mesh.add(s);
  }

  // ── toon ramp: lighting collapses into hard bands (cel / ink-wash look) ──
  function makeToonRamp(steps, floor) {
    // grayscale RGBA (r=g=b) so the ramp can never tint — some builds sample .rgb
    const data = new Uint8Array(steps * 4);
    for (let i = 0; i < steps; i++) {
      const v = Math.round((floor + (1 - floor) * (i / (steps - 1))) * 255);
      data[i * 4] = v; data[i * 4 + 1] = v; data[i * 4 + 2] = v; data[i * 4 + 3] = 255;
    }
    const ramp = new T.DataTexture(data, steps, 1, T.RGBAFormat);
    ramp.minFilter = T.NearestFilter; ramp.magFilter = T.NearestFilter;
    ramp.generateMipmaps = false; ramp.needsUpdate = true; return ramp;
  }
  const toonRamp = makeToonRamp(4, 0.12); // 4 bands, shadows never go fully black

  // fresnel rim glow injected into a toon/standard material — illustrated edge
  function addRim(material, colorHex, power, strength) {
    material.onBeforeCompile = (shader) => {
      shader.uniforms.rimColor = { value: new T.Color(colorHex) };
      shader.uniforms.rimPower = { value: power == null ? 3.0 : power };
      shader.uniforms.rimStrength = { value: strength == null ? 0.85 : strength };
      // r128 has NO output_fragment chunk (added r129) — the output write is
      // inlined in every template; anchor the injection on that exact line.
      const anchor = "gl_FragColor = vec4( outgoingLight, diffuseColor.a );";
      shader.fragmentShader = "uniform vec3 rimColor; uniform float rimPower; uniform float rimStrength;\n" +
        shader.fragmentShader.replace(anchor,
          anchor + "\n" +
          "float rimF = pow(1.0 - saturate(dot(normalize(normal), normalize(vViewPosition))), rimPower);\n" +
          "gl_FragColor.rgb += rimColor * rimF * rimStrength;");
      material.userData.shader = shader;
    };
    return material;
  }
  // toon material factory: hard-banded shading + optional emissive + optional rim
  function toonMat(hex, o) {
    o = o || {};
    const m = new T.MeshToonMaterial({ color: hex, gradientMap: toonRamp,
      emissive: o.emissive == null ? hex : o.emissive, emissiveIntensity: o.ei == null ? 0 : o.ei });
    if (o.rim !== undefined) addRim(m, o.rim, o.rimPow, o.rimStr);
    return m;
  }

  // a cylinder spanning point a→b (so articulated limbs are always geometrically correct)
  const _up = new T.Vector3(0, 1, 0);
  function limb(a, b, r0, r1, matr) {
    const dir = new T.Vector3().subVectors(b, a), len = dir.length();
    const m = new T.Mesh(new T.CylinderGeometry(r0, r1, len, 6), matr);
    m.position.copy(a).add(b).multiplyScalar(0.5);
    m.quaternion.setFromUnitVectors(_up, dir.normalize());
    return m;
  }

  // warm-vs-cold armored pair (art-direction: heraldic duelists, V-taper, high
  // gorget, crested bascinet, cape) — the whole read is "a duel," by colour + pose.
  const KPAL = {
    prime: { armor: 0x2b3653, sheen: 0x3c4d72, heraldry: 0x2e4c8a, trim: 0xa9b6cf, cape: 0x1c2b4e, eye: 0x9fe6ff, rim: 0x8fb6ff },
    chal:  { armor: 0x463733, sheen: 0x5c4638, heraldry: 0xa11b2b, trim: 0xd4a24c, cape: 0x41201a, eye: 0xffb26a, rim: 0xffb277 },
  };

  // ── an armored duelist from primitives — heroic ~6.5 heads: hip at 48% height,
  // waist + neck pinches (the anti-snowman), layered pauldrons on visible arms,
  // jointed limbs, a rounded great-helm w/ a scowl brow + lit visor. Feet at y=0. ──
  function knight(pal, facing) {
    const g = new T.Group(); const f = facing;
    const armor = (hex) => toonMat(hex, { emissive: hex, ei: 0.16, rim: pal.rim, rimStr: 0.65 });
    const trimMat = toonMat(pal.trim, { emissive: pal.trim, ei: 0.05, rim: pal.rim, rimStr: 0.9 });
    const darkMat = new T.MeshToonMaterial({ color: 0x161122, gradientMap: toonRamp });
    const bladeMat = toonMat(0xc7d2e0, { emissive: 0x000000, rim: 0xffffff, rimStr: 0.7 });
    const P = (x, y, z) => new T.Vector3(x, y, z);
    const add = (mesh, outline, k) => { mesh.castShadow = true; g.add(mesh); if (outline) addOutline(mesh, k || 1.06); return mesh; };

    // ── LEGS: sabaton + greave + knee + cuisse (hip at y=1.90 ≈ 48% of height) ──
    [-1, 1].forEach((s) => {
      const x = s * 0.30;
      const boot = new T.Mesh(new T.BoxGeometry(0.26, 0.2, 0.42), darkMat);
      boot.position.set(x, 0.10, 0.06); boot.rotation.y = s * 0.12; add(boot, true, 1.06);
      const toe = new T.Mesh(new T.ConeGeometry(0.15, 0.34, 4), armor(pal.sheen));
      toe.position.set(x, 0.09, 0.34); toe.rotation.set(Math.PI / 2, Math.PI / 4, 0); add(toe, true, 1.05);
      add(limb(P(x, 0.22, 0.04), P(x, 1.02, 0.02), 0.20, 0.16, armor(pal.armor)), true, 1.06); // greave
      const knee = new T.Mesh(new T.SphereGeometry(0.20, 10, 8), armor(pal.sheen));
      knee.position.set(x, 1.04, 0.08); knee.scale.set(1, 0.9, 1.05); add(knee, true, 1.05);
      add(limb(P(x, 1.06, 0.04), P(s * 0.26, 1.90, 0.0), 0.22, 0.26, armor(pal.armor)), true, 1.05); // cuisse
    });

    // ── FAULD + tassets (widest at hips), then the WAIST PINCH ──
    const fauld = new T.Mesh(new T.CylinderGeometry(0.42, 0.62, 0.50, 8), armor(pal.sheen));
    fauld.position.y = 1.90; add(fauld, true, 1.04);
    [-1, 1].forEach((s) => {
      const t = new T.Mesh(new T.BoxGeometry(0.28, 0.44, 0.10), armor(pal.armor));
      t.position.set(s * 0.24, 1.72, 0.42); t.rotation.set(0.1, s * 0.12, 0); add(t, true, 1.04);
    });
    add(new T.Mesh(new T.CylinderGeometry(0.40, 0.42, 0.18, 8), armor(pal.armor)).translateY(2.14), false); // waist plug (narrowest)

    // ── CUIRASS: breastplate 0.60→0.40, upper bevel, pectoral keel ──
    const cuirass = new T.Mesh(new T.CylinderGeometry(0.60, 0.40, 0.98, 8), armor(pal.armor));
    cuirass.position.y = 2.66; cuirass.rotation.y = Math.PI / 8; add(cuirass, true, 1.04);
    const chest = new T.Mesh(new T.CylinderGeometry(0.58, 0.50, 0.30, 8), armor(pal.sheen));
    chest.position.y = 3.05; chest.rotation.y = Math.PI / 8; add(chest, true, 1.04);
    add(new T.Mesh(new T.BoxGeometry(0.10, 0.80, 0.16), armor(pal.sheen)).translateY(2.70).translateZ(0.50), true, 1.03); // pectoral keel

    // ── TABARD (vertical heraldic panel) + emblem ──
    const tabard = new T.Mesh(new T.BoxGeometry(0.40, 1.50, 0.06),
      toonMat(pal.heraldry, { emissive: pal.heraldry, ei: 0.05, rim: pal.rim, rimStr: 0.4 }));
    tabard.position.set(0, 2.15, 0.50); add(tabard, true, 1.02);
    add(new T.Mesh(new T.OctahedronGeometry(0.14), trimMat).translateY(2.70).translateZ(0.56));

    // ── NECK GAP + gorget (the anti-snowman separation) ──
    add(new T.Mesh(new T.CylinderGeometry(0.15, 0.17, 0.22, 8), darkMat).translateY(3.28), false);
    const gorget = new T.Mesh(new T.CylinderGeometry(0.32, 0.22, 0.22, 10, 1, true), trimMat);
    gorget.position.y = 3.24; add(gorget, true, 1.04);

    // ── PAULDRONS: layered half-dome caps, outboard, on the shoulder line (y=3.02) ──
    function pauldron(side, big) {
      const x = side * 0.50, y = 3.02, r = big ? 0.36 : 0.30;
      const cap = new T.Mesh(new T.SphereGeometry(r, 14, 8, 0, Math.PI * 2, 0, Math.PI * 0.6), armor(pal.sheen));
      cap.position.set(x, y, 0.02); cap.scale.set(1.15, 0.85, 1.05); add(cap, true, 1.05);
      const lame = new T.Mesh(new T.SphereGeometry(r * 0.82, 14, 6, 0, Math.PI * 2, 0, Math.PI * 0.5), armor(pal.armor));
      lame.position.set(x * 1.04, y - 0.14, 0.02); lame.scale.set(1.15, 0.70, 1.05); add(lame, true, 1.05);
      if (big) { const spk = new T.Mesh(new T.ConeGeometry(0.12, 0.40, 4), trimMat);
        spk.position.set(x * 1.08, y + 0.20, 0.02); spk.rotation.z = -side * 0.20; add(spk, true, 1.04); }
    }
    pauldron(f, true); pauldron(-f, false);

    // ── ARMS: upper + elbow + forearm to a planted-sword grip ──
    const swZ = 0.72, grip = P(0, 2.05, swZ);
    [[0.50, pal.armor], [-0.50, pal.sheen]].forEach(([sx, col]) => {
      const sh = P(f * sx, 2.90, 0.06), el = P(f * sx * 0.9, 2.35, 0.35);
      add(limb(sh, el, 0.15, 0.16, armor(col)), true, 1.04);
      const elbow = new T.Mesh(new T.SphereGeometry(0.15, 10, 8), armor(col)); elbow.position.copy(el); add(elbow, true, 1.04);
      add(limb(el, grip, 0.13, 0.15, armor(col)), true, 1.04);
    });
    add(new T.Mesh(new T.BoxGeometry(0.22, 0.20, 0.24), darkMat).translateY(2.08).translateZ(swZ), false); // gauntlets

    // ── GREATSWORD, planted (blade down, pommel at the grip) ──
    add(new T.Mesh(new T.BoxGeometry(0.12, 1.90, 0.14), bladeMat).translateY(1.02).translateZ(swZ), true, 1.03);
    add(new T.Mesh(new T.BoxGeometry(0.50, 0.10, 0.16), trimMat).translateY(1.98).translateZ(swZ), true, 1.03);
    add(new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 0.36, 6), darkMat).translateY(2.20).translateZ(swZ));
    add(new T.Mesh(new T.SphereGeometry(0.09, 8, 6), trimMat).translateY(2.42).translateZ(swZ), true, 1.04);

    // ── HELM: rounded skull + tapered jaw + snout + scowl brow + glowing slit ──
    const helm = new T.Group(); helm.position.set(0, 3.42, 0);
    const H = (m, k) => { m.castShadow = true; helm.add(m); if (k) addOutline(m, k); return m; };
    const skull = new T.Mesh(new T.SphereGeometry(0.30, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.62), armor(pal.armor));
    skull.position.y = 0.28; skull.scale.set(1, 1.15, 1.05); H(skull, 1.05);
    H(new T.Mesh(new T.CylinderGeometry(0.30, 0.22, 0.34, 12), armor(pal.armor)).translateY(0.14), 1.04); // tapered jaw
    const snout = new T.Mesh(new T.ConeGeometry(0.20, 0.34, 4), armor(pal.sheen));
    snout.position.set(0, 0.20, 0.24); snout.rotation.set(Math.PI / 2 + 0.2, Math.PI / 4, 0); H(snout, 1.04);
    [-1, 1].forEach((s) => { const b = new T.Mesh(new T.BoxGeometry(0.20, 0.05, 0.08), trimMat);
      b.position.set(s * 0.11, 0.32, 0.24); b.rotation.z = -s * 0.35; H(b); }); // scowl brow ∧
    const eyeMat = new T.MeshBasicMaterial({ color: pal.eye, toneMapped: false });
    const eye = new T.Mesh(new T.BoxGeometry(0.26, 0.05, 0.05), eyeMat); eye.position.set(0, 0.26, 0.30); helm.add(eye);
    H(new T.Mesh(new T.BoxGeometry(0.06, 0.30, 0.50), trimMat).translateY(0.60), 1.04); // crest
    helm.rotation.x = -0.10; g.add(helm); // tilt = "looking at" the opponent

    // ── CAPE: pinned across both shoulders, scalloped cloth hem ──
    const cs = new T.Shape();
    cs.moveTo(-0.42, 0); cs.lineTo(0.42, 0); cs.lineTo(0.60, -1.2); cs.lineTo(0.50, -2.4);
    cs.quadraticCurveTo(0.25, -2.55, 0, -2.4); cs.quadraticCurveTo(-0.25, -2.55, -0.50, -2.4);
    cs.lineTo(-0.60, -1.2); cs.lineTo(-0.42, 0);
    const cape = new T.Mesh(new T.ExtrudeGeometry(cs, { depth: 0.08, bevelEnabled: false }),
      toonMat(pal.cape, { emissive: pal.cape, ei: 0.14, rim: pal.rim, rimStr: 0.4 }));
    cape.position.set(0, 3.05, -0.32); cape.rotation.x = 0.06; add(cape, true, 1.02);

    g.rotation.y = f > 0 ? 0.26 : -0.26;
    g.userData = { base: 0, lean: 0, glowMat: trimMat, eyeMat, cape, helm };
    return g;
  }

  // ── one issue rail: track + live marker + two ghost "true want" bands ──
  function rail(name, y) {
    const g = new T.Group(); g.position.y = y;
    const LEN = 5.0;
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
    // hidden true-wants: a small pip floating ABOVE the rail pointing down at the
    // secret target — shown ONLY on the issue a side cares about (setTruth decides)
    const pip = (hex) => { const m = new T.Mesh(new T.ConeGeometry(0.15, 0.3, 4),
      new T.MeshBasicMaterial({ color: hex, transparent: true, opacity: 0.72, toneMapped: false }));
      m.rotation.x = Math.PI; m.visible = false; g.add(m); return m; }; // point down
    const wantS = pip(COL.prime), wantB = pip(COL.chal);
    // label lives in the DOM UI layer (crisp, never clipped) — see buildUI()
    g.userData = { LEN, mk, wantS, wantB, pos: 0.5, tpos: 0.5, name };
    return g;
  }

  function railX(r, p) { return (p - 0.5) * r.userData.LEN; } // p in 0..1 → x

  // (re)build the rail rack from issueNames — replays bring their own issue
  // set (e.g. 4 issues), so the rack is dynamic; spacing compresses to fit.
  function buildRails() {
    rails.forEach(r => root.remove(r));
    const n = issueNames.length;
    const gap = Math.min(0.62, 1.86 / Math.max(1, n - 1));
    rails = issueNames.map((nm, i) => rail(nm, 3.55 - i * gap));
    rails.forEach(r => { r.position.z = 2.4; root.add(r); });
  }

  // ── build the whole stage ──
  function build() {
    scene = new T.Scene();
    scene.background = new T.Color(0x090612);
    scene.fog = new T.FogExp2(0x0d0820, 0.042); // deeper haze for painterly depth
    root = new T.Group(); scene.add(root);

    cam = new T.PerspectiveCamera(42, 16 / 9, 0.1, 100);
    cam.position.set(0, 4.2, 13); cam.lookAt(0, 2.4, 0);

    // chiaroscuro: deep cool fill, one warm candle KEY (casts shadow), a strong
    // cold violet RIM from the rose window, a gold wash on the deal itself
    scene.add(new T.AmbientLight(0x1c1730, 0.5));
    const key = new T.DirectionalLight(0xffe0b0, 1.05); key.position.set(-5, 8, 7);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
    const sc = key.shadow.camera; sc.near = 1; sc.far = 42;
    sc.left = -13; sc.right = 13; sc.top = 13; sc.bottom = -13; sc.updateProjectionMatrix();
    key.shadow.bias = -0.0004; key.shadow.normalBias = 0.03; key.shadow.radius = 4;
    scene.add(key);
    const candleLight = new T.PointLight(0xffb877, 1.9, 24, 2.2); candleLight.position.set(-2.4, 3.2, 4.6);
    const winLight = new T.PointLight(0xa98cff, 1.4, 40, 2); winLight.position.set(0, 7, -6.5);
    const rim = new T.DirectionalLight(0xbda6ff, 1.1); rim.position.set(2, 9, -9); scene.add(rim);
    const dealLight = new T.PointLight(0xffe6a8, 0.85, 13, 2); dealLight.position.set(0, 4.6, 3.0);
    // opposing temperature fills: Prime lit COLD (left), Challenger lit WARM (right)
    const coolFill = new T.PointLight(0x6f9dff, 1.0, 22, 2); coolFill.position.set(-6.2, 4.2, 4.5);
    const warmFill = new T.PointLight(0xff9550, 1.1, 22, 2); warmFill.position.set(6.2, 4.2, 4.5);
    scene.add(candleLight, winLight, dealLight, coolFill, warmFill);
    clock = { candleLight };

    // god-rays: soft additive shafts falling from the rose window
    const rayMat = new T.MeshBasicMaterial({ color: 0xa78be8, transparent: true, opacity: 0.05,
      blending: T.AdditiveBlending, depthWrite: false, side: T.DoubleSide, toneMapped: false });
    for (let i = -2; i <= 2; i++) {
      const ray = new T.Mesh(new T.PlaneGeometry(1.7, 15), rayMat);
      ray.position.set(i * 1.7, 3, -3.5); ray.rotation.x = -0.32; ray.rotation.z = i * 0.05; root.add(ray);
    }
    // dust motes drifting in the light
    const dustGeo = new T.BufferGeometry(); const N = 130, dp = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { dp[i*3] = (i*37 % 24) - 12; dp[i*3+1] = (i*53 % 90) / 10; dp[i*3+2] = (i*29 % 16) - 5; }
    dustGeo.setAttribute("position", new T.BufferAttribute(dp, 3));
    dust = new T.Points(dustGeo, new T.PointsMaterial({ color: 0xffe6c0, size: 0.055, transparent: true, opacity: 0.5, blending: T.AdditiveBlending, depthWrite: false }));
    root.add(dust);

    // floor with a warm pooled glow where the deal happens
    const floor = new T.Mesh(new T.BoxGeometry(40, 0.5, 26),
      new T.MeshStandardMaterial({ color: 0x140f26, roughness: 1 }));
    floor.position.y = -0.25; floor.receiveShadow = true; root.add(floor);
    const pool = new T.Mesh(new T.PlaneGeometry(9, 6),
      new T.MeshBasicMaterial({ color: 0xffcaa0, transparent: true, opacity: 0.06, blending: T.AdditiveBlending, depthWrite: false, toneMapped: false }));
    pool.rotation.x = -Math.PI / 2; pool.position.set(0, 0.02, 2.6); root.add(pool);
    // back wall — deep plum
    const wall = new T.Mesh(new T.BoxGeometry(40, 24, 0.5),
      new T.MeshStandardMaterial({ color: 0x181030, roughness: 1 }));
    wall.position.set(0, 8, -8); root.add(wall);
    // stained-glass rose window — glowing jewel panes + lead came
    const rose = new T.Group(); rose.position.set(0, 7.4, -7.6);
    const JEWEL = [0xd11f47, 0xf0a828, 0x18a08c, 0x6a3fd0, 0x2f56c8, 0xd44b7e]; // deeper, saturated
    const pane = (inner, outer, i, n, col) => { const g = new T.Mesh(
      new T.RingGeometry(inner, outer, 1, 1, i * 2 * Math.PI / n + 0.03, 2 * Math.PI / n - 0.06),
      new T.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.78, blending: T.AdditiveBlending, depthWrite: false })); rose.add(g); };
    for (let i = 0; i < 12; i++) pane(1.5, 3.1, i, 12, JEWEL[i % 6]);
    for (let i = 0; i < 12; i++) pane(0.55, 1.45, i, 12, JEWEL[(i + 3) % 6]);
    const core = new T.Mesh(new T.CircleGeometry(0.42, 20),
      new T.MeshBasicMaterial({ color: 0xffd07a, blending: T.AdditiveBlending, transparent: true, opacity: 0.85 })); rose.add(core);
    // lead came: dark rings + spokes on top
    [0.52, 1.48, 3.12].forEach(rr => { const ring = new T.Mesh(new T.RingGeometry(rr, rr + 0.07, 40),
      new T.MeshBasicMaterial({ color: 0x0b0818 })); ring.position.z = 0.02; rose.add(ring); });
    for (let i = 0; i < 12; i++) { const s = new T.Mesh(new T.PlaneGeometry(0.07, 3.2),
      new T.MeshBasicMaterial({ color: 0x0b0818 })); s.position.set(0, 0, 0.02); s.rotation.z = i * Math.PI / 6; rose.add(s); }
    const frame = new T.Mesh(new T.RingGeometry(3.1, 3.5, 44),
      new T.MeshStandardMaterial({ color: 0x2a2038, roughness: 1 })); rose.add(frame);
    root.add(rose);
    // two ornate banners flanking, deep-dyed with a gold trim
    [[-7.2, COL.primeK], [7.2, COL.chalK]].forEach(([x, c]) => {
      const b = new T.Mesh(new T.BoxGeometry(1.0, 5.2, 0.12),
        new T.MeshStandardMaterial({ color: c, roughness: 0.9, emissive: c, emissiveIntensity: 0.06 }));
      b.position.set(x, 6.4, -6.9); root.add(b);
      const trim = new T.Mesh(new T.BoxGeometry(1.06, 0.18, 0.14),
        new T.MeshStandardMaterial({ color: 0xd8b45a, emissive: 0x6a5020, emissiveIntensity: 0.5 }));
      trim.position.set(x, 4.0, -6.88); root.add(trim);
    });

    // the table
    const table = new T.Mesh(new T.BoxGeometry(5.2, 0.5, 2.4),
      new T.MeshStandardMaterial({ color: 0x241c30, roughness: 0.8, emissive: 0x120c22, emissiveIntensity: 0.3 }));
    table.position.set(0, 1.2, 2.2); table.castShadow = true; table.receiveShadow = true; root.add(table);

    // knights — set wide so their gesture never collides with the rail rack
    knights.prime = knight(KPAL.prime, 1); knights.prime.position.set(-5.7, 0, 1.9); knights.prime.userData.baseX = -5.7;
    knights.chal = knight(KPAL.chal, -1); knights.chal.position.set(5.7, 0, 1.9); knights.chal.userData.baseX = 5.7;
    root.add(knights.prime, knights.chal);

    // issue rails float in the gap, raised above hand height (helmets rise above, table below)
    buildRails();

    // close glow (hidden until close)
    closeGlow = new T.PointLight(0xffe08a, 0, 24, 2); closeGlow.position.set(0, 2.6, 2.2); scene.add(closeGlow);

    buildUI(); // crisp DOM labels tracking the 3D anchors
  }

  // ── Pixar easing: anticipation, overshoot, settle ──
  const easeOutBack = (t) => { const c1 = 1.9, c3 = c1 + 1; const u = t - 1; return 1 + c3 * u * u * u + c1 * u * u; };
  const easeInOut = (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  // knight strike envelope over lungeT in [0,1]: small pull-back (anticipation),
  // fast jab (peak), then settle back through zero with a hair of overshoot.
  function strikeEnv(t) {
    if (t < 0.14) return -0.55 * easeInOut(t / 0.14);          // wind up (back)
    if (t < 0.34) return -0.55 + 1.55 * easeInOut((t - 0.14) / 0.20); // jab forward → peak 1.0
    return 1.0 * (1 - easeOutBack((t - 0.34) / 0.66));         // recover with overshoot
  }

  // ── one offer = one BEAT: the actor strikes, the moved marker overshoots+settles ──
  function fireTurn(turn) {
    rails.forEach(r => {
      const p = turn.pos[r.userData.name]; if (p == null) return;
      if (Math.abs(p - r.userData.tpos) > 0.03) {              // struck → animate marker
        r.userData.pop = 1; r.userData.from = r.userData.pos; r.userData.animT = 0;
        r.userData.animDur = 0.5 + Math.abs(p - r.userData.pos) * 0.8;
      }
      r.userData.tpos = p;
    });
    const kn = turn.actor === "prime" ? knights.prime : knights.chal;
    kn.userData.lungeT = 0; kn.userData.lunging = true;        // begin the strike envelope
    shake = 0.55;
  }
  function setTruth(t) {
    truth = t;
    // pip shows each side's hidden want on the issue it cares about; its SIZE
    // encodes HOW MUCH they care (the weight) — the utility, made visible.
    const wS = t.weightS || {}, wB = t.weightB || {};
    rails.forEach(r => {
      const n = r.userData.name, s = t.wantS[n], b = t.wantB[n];
      const showS = Math.abs(s - 0.5) > 0.15, showB = Math.abs(b - 0.5) > 0.15;
      r.userData.wantS.visible = showS;
      if (showS) { r.userData.wantS.position.set(railX(r, s), 0.5, 0); r.userData.wantS.scale.setScalar(0.7 + (wS[n] || 0.25) * 1.6); }
      r.userData.wantB.visible = showB;
      if (showB) { r.userData.wantB.position.set(railX(r, b), 0.5, 0); r.userData.wantB.scale.setScalar(0.7 + (wB[n] || 0.25) * 1.6); }
    });
    fillDash();
  }
  // a side's payoff from the CURRENT deal: weighted alignment of each issue with
  // what that side secretly wants. 0.5 = a naive 50/50 split; higher = richer.
  function payoff(side) {
    if (!truth) return 0.5;
    const w = side === "prime" ? truth.weightS : truth.weightB;
    if (!w) return 0.5;
    let u = 0, wsum = 0;
    rails.forEach(r => {
      const wt = w[r.userData.name] || 0; wsum += wt;
      u += wt * (side === "prime" ? r.userData.pos : 1 - r.userData.pos); // seller wants high, buyer low
    });
    return wsum ? u / wsum : 0.5;
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
      "font-family:ui-monospace,Menlo,monospace", "color:#f0eff5", "pointer-events:auto",
      "opacity:0", "transition:opacity .6s ease, transform .6s ease", "z-index:100001",
    ].join(";");
    document.body.appendChild(revealEl);
    return revealEl;
  }
  // fully disarm when hidden: an opacity-0 card must never intercept clicks
  function hideReveal() { if (revealEl) { revealEl.style.opacity = "0"; revealEl.style.pointerEvents = "none"; revealEl.style.transform = "translateX(-50%) translateY(20px)"; } }
  function showReveal(rev) {
    phase = "reveal"; phaseT = 0;
    const el = revealDom();
    el.style.pointerEvents = "auto"; // re-arm (hideReveal disarms)
    const noDeal = !!(script && script.meta && script.meta.deal === false);
    const maxv = rev.ceiling * 1.05;
    const bar = (t, v, c) => `<div style="display:flex;align-items:center;gap:10px;margin:7px 0">
        <span style="width:96px;font-size:12px;color:#aca6c2">${t}</span>
        <span style="flex:1;height:16px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden">
          <i style="display:block;height:100%;width:${(100 * v / maxv).toFixed(1)}%;background:${c}"></i></span>
        <b style="width:44px;text-align:right;font-variant-numeric:tabular-nums">${v.toFixed(2)}</b></div>`;
    // zero-padded 2-digit payoff (.05 must not read as .5), clamped to [0,1]
    const fmtU = (u) => "." + String(Math.round(Math.min(1, Math.max(0, u)) * 100)).padStart(2, "0");
    // per-side decomposition: each traded a low-care issue for a high-care one →
    // both land above the naive .50 split. This is WHY the pie grew.
    // (skipped for no-deal replays — there is no pie to decompose)
    const argmax = (w) => issueNames.reduce((a, n) => (w && w[n] > (w[a] || -1) ? n : a), issueNames[0]);
    let why = "";
    if (!noDeal && truth && truth.weightS && truth.weightB) {
      const uP = payoff("prime"), uC = payoff("chal");
      const wonP = argmax(truth.weightS), gaveP = argmax(truth.weightB);
      const wonC = argmax(truth.weightB), gaveC = argmax(truth.weightS);
      const side = (nm, accent, u, won, gave) =>
        `<div style="display:flex;align-items:center;gap:9px;margin:6px 0">
           <span style="width:118px;font-size:11px;color:${accent}">${nm}</span>
           <span style="position:relative;flex:1;height:12px;background:rgba(255,255,255,0.06);border-radius:4px">
             <i style="display:block;height:100%;width:${(u * 100).toFixed(0)}%;background:#7fc48f;border-radius:4px"></i>
             <span style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:rgba(255,255,255,0.45)"></span></span>
           <b style="width:30px;text-align:right;font-size:11px;color:#7fc48f">${fmtU(u)}</b></div>
         <div style="font-size:10.5px;color:#8f8aa4;margin:-2px 0 4px 127px">${won === gave ? "priorities collided on " + won : "won " + won + " · gave " + gave}</div>`;
      const nmP = (script && script.names && script.names.seller) || "SNHP PRIME";
      const nmC = (script && script.names && script.names.buyer) || "THE CHALLENGER";
      why = `<div style="font-size:10px;letter-spacing:.22em;color:#6f6a86;margin:14px 0 4px">WHY BOTH WON <span style="color:#5a566e;letter-spacing:0">(payoff vs naive .50)</span></div>` +
        side(nmP, "#8fd0ff", uP, wonP, gaveP) +
        side(nmC, "#ff9d6b", uC, wonC, gaveC);
    }
    // the two funnels, at the moment of peak conviction: (1) feel it yourself in
    // the PAR seat; (2) ask for it in real life (marketplace / A2A concierge).
    const btn = (href, label, primary) => '<a href="' + href + '" target="_blank" rel="noopener" ' +
      'style="display:inline-block;padding:9px 13px;border-radius:9px;font-size:11px;letter-spacing:.07em;text-decoration:none;font-weight:700;' +
      (primary ? "background:#7fc48f;color:#0a0812" : "border:1px solid rgba(167,139,250,.55);color:#d6cff0") + '">' + label + "</a>";
    const funnel =
      '<div style="margin-top:15px;padding-top:13px;border-top:1px solid rgba(167,139,250,.22);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">' +
        '<div style="font-size:10.5px;line-height:1.55;color:#8f8aa4">Most people land near the naive split.<br>What would <b style="color:#c9c4dc">your</b> number be?</div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
          btn("https://par-game.fly.dev", "⚔ TRY THIS DEAL YOURSELF", true) +
          btn("hire.html", "🤝 HAVE IT NEGOTIATE FOR ME", false) +
        "</div></div>" +
      '<div style="font-size:9.5px;letter-spacing:.06em;color:#6f6a86;margin-top:8px;text-align:right">MCP for your agent · API pilots · or DM @ryuxik</div>';
    // replays label the realized bar honestly (rev.label, e.g. "this deal");
    // "SNHP" is only the default for the canned engine demo
    el.innerHTML =
      `<div style="font-size:11px;letter-spacing:.24em;color:${noDeal ? "#e8734a" : "#ffe08a"};text-transform:uppercase;margin-bottom:2px">${noDeal ? "no deal — the pie evaporated" : "the pie they made"}</div>` +
      `<div style="font-size:10px;color:#8f8aa4;margin-bottom:10px">${(script && script.subtitle) || "a real agent-to-agent negotiation, run by the SNHP engine"}</div>` +
      bar("naive split", rev.naive, "#e8734a") +
      (rev.human ? bar("avg human", rev.human, "#e8b24c") : "") +
      bar(rev.label || "SNHP", rev.snhp, noDeal ? "#8f8aa4" : "#7fc48f") +
      bar("best possible", rev.ceiling, "#a78bfa") +
      why +
      `<div style="font-size:12.5px;line-height:1.6;color:#c9c4dc;margin-top:12px">${rev.line}</div>` +
      funnel;
    el.style.width = "min(600px,92vw)";
    requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateX(-50%) translateY(0)"; });
  }

  // ── DOM UI layer: every readable label is crisp HTML tracking a 3D anchor
  // (no baked textures → no clipping, pixel-sharp, trivially aligned) ──
  let uiEl = null, uiItems = [], uiKnights = null;
  function buildUI() {
    if (uiEl) uiEl.remove();
    uiEl = document.createElement("div"); uiEl.id = "duel-ui";
    uiEl.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:100000;font-family:ui-monospace,Menlo,monospace";
    document.body.appendChild(uiEl);
    const mk = (html, align) => { const d = document.createElement("div");
      d.style.cssText = "position:absolute;white-space:nowrap;will-change:transform;line-height:1.25";
      d.dataset.align = align || "center"; d.innerHTML = html; uiEl.appendChild(d); return d; };
    // per-knight dashboard: name → role → secret priorities → live payoff meter
    const dash = (side, name, role, accent, shadow) => {
      const card = mk("", side === "prime" ? "left" : "right");
      card.style.width = "176px"; card.style.whiteSpace = "normal";
      card.innerHTML =
        '<div data-name style="font-size:18px;font-weight:600;letter-spacing:.08em;color:' + accent + ';text-shadow:0 0 14px ' + shadow + '">' + name + '</div>' +
        '<div data-role style="font-size:10.5px;letter-spacing:.04em;color:#8891a6;margin:1px 0 8px">' + role + '</div>' +
        '<div style="font-size:9px;letter-spacing:.18em;color:#6f6a86;margin-bottom:4px">SECRET PRIORITY</div>' +
        '<div data-pri></div>' +
        '<div style="font-size:9px;letter-spacing:.18em;color:#6f6a86;margin:9px 0 3px">PAYOFF <span style="color:#5a566e">vs naive split</span></div>' +
        '<div style="position:relative;height:9px;background:rgba(255,255,255,0.08);border-radius:5px">' +
          '<i data-payfill style="display:block;height:100%;width:50%;background:' + accent + ';border-radius:5px;transition:width .12s linear"></i>' +
          '<span style="position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:rgba(255,255,255,0.5)"></span></div>' +
        '<div style="display:flex;justify-content:space-between;font-size:9px;color:#6f6a86;margin-top:2px"><span>naive .50</span><span data-payval style="color:' + accent + ';font-variant-numeric:tabular-nums">.50</span></div>';
      return { card, priEl: card.querySelector("[data-pri]"), roleEl: card.querySelector("[data-role]"),
        nameEl: card.querySelector("[data-name]"),
        payFill: card.querySelector("[data-payfill]"), payVal: card.querySelector("[data-payval]") };
    };
    uiKnights = {
      prime: Object.assign(dash("prime", "SNHP PRIME", "the shipped agent", "#cfeaff", "rgba(143,208,255,.6)"), { accent: "#8fd0ff" }),
      chal: Object.assign(dash("chal", "THE CHALLENGER", "what evolution found", "#ffd0b3", "rgba(255,157,107,.6)"), { accent: "#ff9d6b" }),
    };
    // pin the player-cards to the top corners (VS-HUD convention) — never over the action
    uiKnights.prime.card.style.left = "24px"; uiKnights.prime.card.style.top = "26px";
    uiKnights.chal.card.style.right = "24px"; uiKnights.chal.card.style.top = "26px"; uiKnights.chal.card.style.textAlign = "right";
    uiItems = [];
    rails.forEach(r => {
      uiItems.push({ el: mk('<span style="font-size:13px;letter-spacing:.14em;color:#d8d5e6;text-shadow:0 1px 3px #000">' + r.userData.name + '</span>'),
        world: new T.Vector3(-r.userData.LEN / 2 + 0.15, r.position.y + 0.34, r.position.z), ax: "0%", vy: "-50%" });
    });
  }
  // fill each dashboard's secret-priority bars from the current truth (weights)
  function fillDash() {
    if (!uiKnights || !truth) return;
    if (script && script.chalOrigin) uiKnights.chal.roleEl.textContent = script.chalOrigin;
    if (script && script.names) { // replays: relabel the seats (left = seller)
      uiKnights.prime.nameEl.textContent = script.names.seller || "SNHP PRIME";
      uiKnights.chal.nameEl.textContent = script.names.buyer || "THE CHALLENGER";
      uiKnights.prime.roleEl.textContent = "seller";
      if (!script.chalOrigin) uiKnights.chal.roleEl.textContent = "buyer";
    }
    if (script && script.origins) { // per-seat captions — the model's identity
      // stays on the MODEL's plate whichever seat it holds
      if (script.origins.seller) uiKnights.prime.roleEl.textContent = script.origins.seller;
      if (script.origins.buyer) uiKnights.chal.roleEl.textContent = script.origins.buyer;
    }
    const rows = (w, accent) => issueNames.map(n => {
      const pct = Math.round((w && w[n] ? w[n] : 0) * 100);
      return '<div style="display:flex;align-items:center;gap:6px;margin:2px 0;font-size:9.5px">' +
        '<span style="width:56px;color:#9a95b0">' + n + '</span>' +
        '<span style="flex:1;height:5px;background:rgba(255,255,255,0.08);border-radius:3px">' +
        '<i style="display:block;height:100%;width:' + pct + '%;background:' + accent + ';border-radius:3px"></i></span></div>';
    }).join("");
    uiKnights.prime.priEl.innerHTML = rows(truth.weightS, "#8fd0ff");
    uiKnights.chal.priEl.innerHTML = rows(truth.weightB, "#ff9d6b");
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
      it.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(" + it.ax + "," + it.vy + ")";
    }
    // live payoff meters — both climb past .50 as the logroll grows the pie
    if (uiKnights && truth) {
      // no-deal endgame: both sides realize their BATNA, not the last rejected offer
      const noDeal = !!(script && script.meta && script.meta.deal === false)
        && (phase === "close" || phase === "reveal");
      ["prime", "chal"].forEach(s => {
        const u = noDeal ? 0.30 : Math.min(1, Math.max(0, payoff(s))), k = uiKnights[s];
        k.payFill.style.width = (u * 100).toFixed(1) + "%";
        k.payVal.textContent = "." + String(Math.round(u * 100)).padStart(2, "0");
        k.payFill.style.background = u >= 0.505 ? "#7fc48f" : k.accent; // green once it beats the split
      });
    }
  }

  // ── main loop ──
  function tick(dt) {
    if (!renderer) return; // not mounted yet — nothing to animate
    sT += dt;
    // candlelight idle flicker
    if (clock) clock.candleLight.intensity = 1.25 + Math.sin(sT * 9) * 0.15 + Math.random() * 0.05;

    // drifting dust motes catching the light (slow rise + gentle sway, wraps)
    if (dust) { const pa = dust.geometry.attributes.position;
      for (let i = 0; i < pa.count; i++) {
        let y = pa.getY(i) + dt * 0.22; if (y > 9) y = 0; pa.setY(i, y);
        pa.setX(i, pa.getX(i) + Math.sin(sT * 0.4 + i) * dt * 0.06);
      } pa.needsUpdate = true; }

    // rail markers: overshoot-and-settle to the new offer (easeOutBack), pop = flash+scale
    rails.forEach(r => {
      if (r.userData.animT != null && r.userData.animT < 1) {
        r.userData.animT = Math.min(1, r.userData.animT + dt / (r.userData.animDur || 0.5));
        r.userData.pos = r.userData.from + (r.userData.tpos - r.userData.from) * easeOutBack(r.userData.animT);
      } else {
        r.userData.pos += (r.userData.tpos - r.userData.pos) * Math.min(1, dt * 6);
      }
      r.userData.mk.position.x = railX(r, r.userData.pos);
      r.userData.pop = Math.max(0, (r.userData.pop || 0) - dt * 2.6);
      r.userData.mk.scale.set(1 + r.userData.pop * 0.9, 1 - r.userData.pop * 0.28, 1 + r.userData.pop * 0.9); // squash on impact
      r.userData.mk.rotation.y += dt * 1.6; r.userData.mk.rotation.x = 0.35;
      r.userData.mk.material.emissiveIntensity = 0.9 + r.userData.pop * 2.2 + Math.sin(sT * 5 + r.position.y) * 0.1;
    });

    // playback: one beat every BEAT_GAP seconds (paced so each offer reads)
    if (script && phase === "intro") {
      phaseT += dt;
      if (phaseT >= 2.3) { phase = "trade"; phaseT = BEAT_GAP; } // establishing beat, then trade
    }
    if (script && (phase === "trade" || phase === "closing")) {
      phaseT += dt;
      if (phase === "trade" && phaseT >= BEAT_GAP) {
        if (step < script.turns.length) {
          fireTurn(script.turns[step]); step++; phaseT = 0;
        } else { phase = "closing"; phaseT = 0; }
      } else if (phase === "closing" && phaseT >= 1.1) { doClose(); }
    }
    if (script && phase === "close") {
      phaseT += dt;
      if (phaseT >= 1.4 && script.reveal) showReveal(script.reveal); // sets phase="reveal"
    }
    // knight strike: anticipation → jab → settle (Pixar envelope), over idle breathing
    ["prime", "chal"].forEach((k, ki) => {
      const kn = knights[k], sign = k === "prime" ? 1 : -1;
      let L = 0;
      if (kn.userData.lunging) {
        kn.userData.lungeT = Math.min(1, (kn.userData.lungeT || 0) + dt / 0.62);
        L = strikeEnv(kn.userData.lungeT);
        if (kn.userData.lungeT >= 1) { kn.userData.lunging = false; }
      }
      kn.userData.lunge = Math.max(0, L);                    // camera reads the forward part
      const breathe = Math.sin(sT * 1.5 + ki * 2.1) * 0.5;   // idle secondary motion
      kn.position.x = kn.userData.baseX + sign * L * 0.7;    // step in on the jab
      kn.position.y = Math.abs(L) * 0.12 + breathe * 0.03;   // slight lift on the blow
      kn.rotation.x = -L * 0.18;                             // lean into it
      kn.rotation.z = breathe * 0.014 - L * 0.05 * sign;    // secondary sway + strike torque
      kn.userData.glowMat.emissiveIntensity = 0.05 + Math.max(0, L) * 0.4;
      if (kn.userData.cape) kn.userData.cape.rotation.z = (-0.06 * sign) + Math.sin(sT * 1.1 + ki * 1.7) * 0.05 + L * 0.08 * sign; // cloth sway + drag on the jab
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
    if (composer) composer.render(); else renderer.render(scene, cam);
    updateUI();
  }

  let camGoal = { pos: new T.Vector3(0, 4.2, 13), look: new T.Vector3(0, 2.4, 0) };
  const _look = new T.Vector3();
  // adaptive framing: on tall/narrow screens dolly back + widen so both knights
  // (±5.7) always fit; STAGE_Z is the pivot the camera orbits.
  const STAGE_Z = 2.0; let fitZ = 1;
  function applyFraming(pos, look) {
    pos.z = STAGE_Z + (pos.z - STAGE_Z) * fitZ;
    pos.y = pos.y + (fitZ - 1) * 1.0;
    if (look) look.y = look.y + (fitZ - 1) * 0.7;
    return pos;
  }
  function cameraBeat() {
    if (phase === "reveal") { camGoal.pos.set(0, 4.2, 12.5); camGoal.look.set(0, 3.0, 2.0); }
    else if (phase === "close") { camGoal.pos.set(0, 3.4, 9.5); camGoal.look.set(0, 2.5, 2.0); }
    else if (phase === "trade" || phase === "closing") {
      // steady frame that gently leans toward whoever just struck (no aimless drift)
      const bias = ((knights.chal.userData.lunge || 0) - (knights.prime.userData.lunge || 0)) * 1.7;
      camGoal.pos.set(bias, 3.6, 12.6); camGoal.look.set(bias * 0.35, 2.2, 1.9);
    } else { camGoal.pos.set(0, 3.9, 14); camGoal.look.set(0, 2.2, 1.5); }
    applyFraming(camGoal.pos, camGoal.look);
    cam.position.lerp(camGoal.pos, 0.045);
    _look.lerp(camGoal.look, 0.05); cam.lookAt(_look);
  }

  function doClose() {
    phase = "close"; phaseT = 0;
    // the gold clasp is a CELEBRATION — no-deal replays end cold instead
    if (script && script.meta && script.meta.deal === false) { closeT = 0; }
    else { closeT = 2.2; closeGlow.intensity = 12; shake = 1.0; }
    // the close→reveal beat is sim-clock driven in tick() (robust to throttling)
  }

  // ── cinematic post: color-grade + vignette in one pass (no vendored file) ──
  const GradeShader = {
    uniforms: {
      tDiffuse: { value: null }, resolution: { value: new T.Vector2(1, 1) },
      vignette: { value: 1.2 }, tint: { value: new T.Color(0xfff0da) },
      contrast: { value: 1.08 }, saturation: { value: 1.14 },
    },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: [
      "uniform sampler2D tDiffuse; uniform float vignette, contrast, saturation; uniform vec3 tint; varying vec2 vUv;",
      "void main(){",
      "  vec3 c = texture2D(tDiffuse, vUv).rgb;",
      "  c *= tint;",
      "  c = (c - 0.5) * contrast + 0.5;",
      "  float l = dot(c, vec3(0.2126,0.7152,0.0722));",
      "  c = mix(vec3(l), c, saturation);",
      "  vec2 d = vUv - 0.5; c *= 1.0 - dot(d,d) * vignette;",
      "  gl_FragColor = vec4(max(c, 0.0), 1.0);",
      "}",
    ].join("\n"),
  };
  // ── Castlevania-NES pass: pixelate to a low art-resolution, posterize to a
  // limited palette with 4×4 ordered dither, plus CRT scanlines. This is what
  // turns "Blender render" into "retro-gothic pixel stage". ──
  function makeBayerTex() {
    const m = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
    const d = new Uint8Array(16 * 4);
    for (let i = 0; i < 16; i++) { const v = Math.round((m[i] / 16) * 255); d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = v; d[i * 4 + 3] = 255; }
    const tex = new T.DataTexture(d, 4, 4, T.RGBAFormat);
    tex.minFilter = tex.magFilter = T.NearestFilter; tex.wrapS = tex.wrapT = T.RepeatWrapping;
    tex.needsUpdate = true; return tex;
  }
  const PixelShader = {
    uniforms: {
      tDiffuse: { value: null }, bayer: { value: null }, grid: { value: new T.Vector2(360, 202) },
      levels: { value: 10.0 }, scan: { value: 0.10 }, on: { value: 1.0 },
    },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: [
      "uniform sampler2D tDiffuse, bayer; uniform vec2 grid; uniform float levels, scan, on; varying vec2 vUv;",
      "void main(){",
      "  if(on < 0.5){ gl_FragColor = texture2D(tDiffuse, vUv); return; }",
      "  vec2 cell = floor(vUv * grid);",
      "  vec2 uv = (cell + 0.5) / grid;",              // snap to art-pixel centre → chunky pixels
      "  vec3 c = texture2D(tDiffuse, uv).rgb;",
      "  float d = texture2D(bayer, cell / 4.0).r - 0.5;", // 4×4 ordered dither
      "  c = floor(c * levels + d) / levels;",          // dither then posterize to the palette
      "  float sl = 1.0 - scan * step(1.0, mod(cell.y, 2.0));", // CRT scanline every other row
      "  gl_FragColor = vec4(clamp(c * sl, 0.0, 1.0), 1.0);",
      "}",
    ].join("\n"),
  };
  let composer, bloomPass, gradePass, pixelPass, bayerTex;
  function buildComposer() {
    const size = renderer.getDrawingBufferSize(new T.Vector2());
    let rt = null;
    if (renderer.capabilities.isWebGL2) {
      rt = new T.WebGLMultisampleRenderTarget(size.x, size.y,
        { minFilter: T.LinearFilter, magFilter: T.LinearFilter, format: T.RGBAFormat });
      rt.samples = 4;
    }
    composer = new T.EffectComposer(renderer, rt);
    composer.setSize(size.x, size.y);
    composer.addPass(new T.RenderPass(scene, cam));
    bloomPass = new T.UnrealBloomPass(new T.Vector2(size.x, size.y), 0.6, 0.4, 0.9); // strength, radius, threshold
    composer.addPass(bloomPass);
    gradePass = new T.ShaderPass(GradeShader);
    composer.addPass(gradePass);
    bayerTex = makeBayerTex();
    pixelPass = new T.ShaderPass(PixelShader);
    pixelPass.uniforms.bayer.value = bayerTex;
    composer.addPass(pixelPass);
    composer.addPass(new T.ShaderPass(T.GammaCorrectionShader)); // linear→sRGB, must be last
  }

  // ── lifecycle ──
  function mount(el) {
    if (renderer) return;
    build();
    renderer = new T.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setClearColor(COL.bg, 1);
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.82;
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    (el || document.body).appendChild(renderer.domElement);
    renderer.domElement.style.cssText = "position:fixed;inset:0;width:100%;height:100%;display:block;";
    buildComposer();
    resize();
    window.addEventListener("resize", resize);
  }
  function resize() {
    if (!renderer) return;
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h); cam.aspect = w / h;
    // widen FOV as the frame narrows, then dolly back enough to fit the full width
    const a = cam.aspect;
    cam.fov = a >= 1.4 ? 42 : a <= 0.6 ? 60 : 42 + (60 - 42) * (1.4 - a) / 0.8;
    const tanH = Math.tan(cam.fov * Math.PI / 360) * a;   // horizontal half-angle
    fitZ = Math.max(1, (6.8 / tanH) / 10.6);              // vs desktop nominal distance
    cam.updateProjectionMatrix();
    if (composer) {
      const db = renderer.getDrawingBufferSize(new T.Vector2());
      composer.setSize(db.x, db.y); bloomPass.setSize(db.x, db.y);
      // keep a constant vertical art-resolution (~202px, NES-ish); width follows aspect
      const artH = 202; pixelPass.uniforms.grid.value.set(Math.round(artH * a), artH);
    }
    if (!running) drawFrame();
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
    if (uiEl) uiEl.style.display = "";   // undo stop()'s hide
    // replays carry their own issue set — rebuild the rack + labels if it changed
    if (Array.isArray(s.issues) && s.issues.join("|") !== issueNames.join("|")) {
      issueNames = s.issues.slice();
      buildRails();
      buildUI();
    }
    if (script.truth) setTruth(script.truth);
    // reset rails to opening positions AND kill any in-flight animation state,
    // so switching replays never resumes the previous match's tweens
    rails.forEach(r => { r.userData.pos = 0.5; r.userData.tpos = 0.5;
      r.userData.animT = null; r.userData.pop = 0; });
    ["prime", "chal"].forEach(k => { knights[k].userData.lunging = false;
      knights[k].userData.lungeT = 0; knights[k].userData.lunge = 0; });
    shake = 0; closeT = 0;
    running = true; last = performance.now();
    // intro→trade transition is driven by the sim clock in tick() (robust to tab throttling)
    raf = requestAnimationFrame(loop);
  }
  // stop() owns the module's DOM lifecycle: hosts must never reach into
  // #duel-ui / #duel-reveal themselves
  function stop() {
    running = false; cancelAnimationFrame(raf);
    hideReveal();
    if (uiEl) uiEl.style.display = "none";
  }
  function active() { return running; }
  // true once the current script has played through to its reveal — the signal
  // demo pages use to loop (running stays true so the reveal keeps rendering)
  function finished() { return phase === "reveal"; }

  // debug: freeze a specific state for screenshotting (bypasses timing)
  function _debug(which) {
    running = false; cancelAnimationFrame(raf);
    if (which === "trade" || which === "strike") {
      phase = "trade"; hideReveal();
      const mid = { PRICE: 0.80, DELIVERY: 0.51, TERMS: 0.24 };
      rails.forEach(r => { const p = mid[r.userData.name] != null ? mid[r.userData.name] : 0.5; r.userData.pos = r.userData.tpos = p; r.userData.mk.position.x = railX(r, p); r.userData.mk.scale.setScalar(1); });
      if (script && script.truth) setTruth(script.truth);
      let bias = 0;
      if (which === "strike") { // freeze mid-strike: PRICE hit by Prime
        const pr = rails.find(r => r.userData.name === "PRICE");
        pr.userData.pop = 1; pr.userData.mk.scale.setScalar(1.8); pr.userData.mk.material.emissiveIntensity = 3.0;
        knights.prime.userData.lunge = 1; knights.prime.position.x = knights.prime.userData.baseX + 0.7; knights.prime.rotation.x = -0.18;
        knights.prime.userData.glowMat.emissiveIntensity = 0.45; bias = -1.7;
      }
      cam.position.set(bias, 3.6, 12.6); _look.set(bias * 0.35, 2.2, 1.9);
      applyFraming(cam.position, _look); cam.lookAt(_look);
    } else if (which === "reveal") {
      if (script && script.reveal) showReveal(script.reveal);
      cam.position.set(0, 4.4, 12.5); _look.set(0, 4.0, 3);
      applyFraming(cam.position, _look); cam.lookAt(_look);
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
      c2.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:99999;pointer-events:none"; document.body.appendChild(c2); }
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
  A.duel3d = { mount, play, stop, active, finished, resize, _phase: () => phase, _debug, _capture, _advance, _state: stateOf,
    _pixel: (on, g, lv) => { if (pixelPass) { pixelPass.uniforms.on.value = on ? 1 : 0; if (g) pixelPass.uniforms.grid.value.set(Math.round(g * cam.aspect), g); if (lv) pixelPass.uniforms.levels.value = lv; } drawFrame(); },
    _probe: () => ({ uk: !!uiKnights, tr: !!truth, po: typeof payoff === "function" ? [payoff("prime"), payoff("chal")] : null }) };
})();

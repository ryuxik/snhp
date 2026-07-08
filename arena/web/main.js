/* Boot + the loop. Renders the world into a low-res 480x270 backbuffer, then
   integer-upscales to the visible canvas (imageSmoothingEnabled=false) with
   letterboxing. Fixed 60Hz logic via an accumulator; camera eases toward the
   director's focus. Live events are already server-paced, so we dispatch on
   arrival; the demo stream is self-paced. */
(function () {
  "use strict";
  const A = window.Arena;
  const S = A.stage, W = A.world, C = A.choreo, HUD = A.hud, NET = A.net, FX = A.fx;
  const LOW_W = 480, LOW_H = 270;

  const view = document.getElementById("view");
  const scan = document.getElementById("scanlines");
  const low = document.createElement("canvas"); low.width = LOW_W; low.height = LOW_H;
  const lc = low.getContext("2d"); lc.imageSmoothingEnabled = false;
  lc.canvas.__logicalH = LOW_H;
  const vc = view.getContext("2d"); vc.imageSmoothingEnabled = false;
  let scale = 3;

  function resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    scale = Math.max(1, Math.floor(Math.min(window.innerWidth / LOW_W, window.innerHeight / LOW_H)));
    for (const cv of [view, scan]) {
      cv.width = LOW_W * scale; cv.height = LOW_H * scale;
      cv.style.width = LOW_W * scale + "px"; cv.style.height = LOW_H * scale + "px";
    }
    vc.imageSmoothingEnabled = false;
    _buildScanlines();
  }
  function _buildScanlines() {
    const c = scan.getContext("2d"); c.clearRect(0, 0, scan.width, scan.height);
    c.fillStyle = "#000";
    for (let y = 0; y < scan.height; y += 3 * scale) c.fillRect(0, y, scan.width, Math.max(1, scale));
  }
  window.addEventListener("resize", resize);

  // camera
  const cam = { x: 40, targetX: 40, era: "symmetric" };
  function updateCamera() {
    cam.era = W.era;
    const fx = C.focusX();
    cam.targetX = Math.max(0, Math.min(S.WORLD_W - LOW_W, fx - LOW_W / 2));
    cam.x += (cam.targetX - cam.x) * 0.04;
  }

  // fixed-timestep loop
  let acc = 0, last = performance.now();
  function frame(now) {
    let dt = now - last; last = now; if (dt > 100) dt = 100;
    acc += dt;
    while (acc >= 16.6667) { C.update(); updateCamera(); acc -= 16.6667; }
    // draw world
    C.draw(lc, cam);
    FX.drawImpact(lc, LOW_W, LOW_H);
    FX.drawCutIn(lc, LOW_W, LOW_H);
    // in-canvas brand tag (survives re-uploads / clip crops)
    FX.text(lc, "SNHP", LOW_W - 22, LOW_H - 8, "rgba(200,196,216,0.25)", 1);
    // upscale blit
    vc.drawImage(low, 0, 0, LOW_W * scale, LOW_H * scale);
    requestAnimationFrame(frame);
  }

  // HUD ticks (throttled)
  setInterval(() => HUD.update(), 400);

  // connection chip
  const chip = document.getElementById("conn-chip");
  NET.onState = (s) => {
    chip.classList.toggle("demo", s === "demo");
    chip.textContent = s === "demo" ? "demo mode — live arena unreachable" : (s === "connecting" ? "connecting…" : "");
    chip.classList.toggle("show", s !== "live");
  };

  // event dispatch
  NET.onEvent = (ev) => {
    if (ev.type === "world.snapshot") { W.reset(ev); cam.era = W.era; }
    else W.ingest(ev);
  };
  // the Bloom of the Generation takes the whole screen for a beat
  W.onBloom = (ev) => { if (A.bloom) A.bloom.show(ev); };

  // highlight -> cut-in (rate limited) + sound
  let lastCut = 0;
  W.onHighlight = (ev) => {
    const now = performance.now();
    if (ev.kind === "era_flip") A.sound.play("bell");
    if (ev.kind === "record_surplus") A.sound.play("clasp");
    if (now - lastCut < 45000) return; // max 1 / 45s
    if (FX.cutBusy()) return;
    lastCut = now;
    const titles = {
      record_surplus: ["RECORD DEAL", ev.blurb || ""],
      dynasty_founder_death: ["A DYNASTY FALLS", ev.blurb || ""],
      dynasty_founded: ["A DYNASTY RISES", ev.blurb || ""],
      era_flip: ["THE MARKET TURNS", ev.blurb || ""],
      grand_auction: ["GRAND AUCTION", ev.blurb || ""],
      challenger: ["A CHALLENGER ENTERS", ev.blurb || ""],
    };
    const tt = titles[ev.kind]; if (tt) FX.cutIn(tt[0], tt[1].toUpperCase());
  };
  // YOUR champion's arrival and fall are always worth the fanfare — the whole
  // forge loop hinges on these two beats landing (rate limit bypassed).
  W.onChampion = (kind, x) => {
    if (kind === "arrived") { FX.cutIn("YOUR CHAMPION ENTERS", (x.name || "").toUpperCase()); A.sound.play("bell"); }
    else if (kind === "fallen") {
      FX.cutIn("YOUR CHAMPION FALLS",
        x.heirs ? (x.heirs + " OF THE LINE CARRY ON") : "THE LINE IS ENDED");
      A.sound.play("gutter");
    }
    lastCut = performance.now();
  };
  // duel sounds
  const origClose = W.onDuelClose;
  // choreo sets onDuelClose; layer sound after choreo.init runs (below)

  // clip / replay modes (for the capture pipeline)
  const params = new URLSearchParams(location.search);
  const clipMode = params.get("clip") === "1" || params.get("hud") === "clip";
  if (clipMode) document.body.classList.add("clip");

  // boot
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  C.init({ reduced });
  const choreoClose = W.onDuelClose, choreoWalk = W.onDuelWalk;
  W.onDuelClose = (d, ev) => { choreoClose && choreoClose(d, ev); A.sound.play("clasp"); };
  W.onDuelWalk = (d, ev) => { choreoWalk && choreoWalk(d, ev); A.sound.play("shatter"); };
  HUD.initControls();
  resize();
  NET.connect();
  requestAnimationFrame(frame);

  A.main = { cam };
})();

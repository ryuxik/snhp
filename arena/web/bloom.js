/* The full-screen "Bloom of the Generation" — the climax. When the season's
   pollinator crowns its fairest flower, we hold the whole hall for a beat and
   render that bloom huge, in stained-glass light: a rose window whose petals ARE
   the winning genome. Beauty = the strategy that's winning, seen. This is the
   clip moment. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  const FL = A.flora, FX = A.fx;
  const $ = (id) => document.getElementById(id);

  const SIZE = 300;
  let _timer = null, _low = null, _lc = null;

  function _ensure() {
    if (_low) return;
    _low = document.createElement("canvas"); _low.width = SIZE; _low.height = SIZE;
    _lc = _low.getContext("2d"); _lc.imageSmoothingEnabled = false;
  }

  function show(ev) {
    _ensure();
    const overlay = $("bloom-overlay"), cv = $("bloom-canvas");
    if (!overlay || !cv || !ev.genome) return;
    const scale = Math.max(1, Math.floor(Math.min(window.innerWidth, window.innerHeight) * 0.55 / SIZE));
    cv.width = SIZE * scale; cv.height = SIZE * scale;
    cv.style.width = SIZE * scale + "px"; cv.style.height = SIZE * scale + "px";
    const vc = cv.getContext("2d"); vc.imageSmoothingEnabled = false;

    _render(ev);
    vc.drawImage(_low, 0, 0, SIZE * scale, SIZE * scale);

    $("bloom-house").textContent = "House " + ev.house;
    const f = ev.flower || {}, g = ev.genome || {};
    // beauty IS strategy: name the negotiation genome this flower renders
    const strat = g.tactic_family
      ? `a ${g.tactic_family}'s ${f.species || "flower"} · boldness ${Math.round((g.pareto_knob || 0) * 100)}`
        + (g.staked ? " · staked" : "")
      : (f.species || "flower");
    $("bloom-meta").innerHTML =
      `${strat}<br>judged fairest by ${ev.pollinator ? ev.pollinator.glyph + " " + ev.pollinator.name : "the season"}`
      + ` · beauty <b>${Math.round((ev.beauty || 0) * 100)}</b>`;

    overlay.classList.remove("hidden");
    void overlay.offsetWidth; // force reflow so the opacity transition animates
    overlay.classList.add("show");
    A.sound && A.sound.play && A.sound.play("bell");
    clearTimeout(_timer);
    _timer = setTimeout(hide, 4200);
  }

  function _render(ev) {
    const c = _lc; c.clearRect(0, 0, SIZE, SIZE);
    const cx = SIZE / 2, cy = SIZE / 2;
    // stained-glass rose-window frame behind the bloom
    const b = FL.bloom(ev.genome);
    c.save();
    // radial glass panes in the flower's hue
    for (let k = 0; k < 12; k++) {
      const a0 = k / 12 * 7, a1 = (k + 1) / 12 * 7;
      c.fillStyle = k % 2 ? b.petalDark : "#16102c";
      c.globalAlpha = 0.5;
      c.beginPath(); c.moveTo(cx, cy);
      c.arc(cx, cy, 138, a0, a1); c.closePath(); c.fill();
    }
    c.globalAlpha = 1;
    // lead tracery ring
    c.strokeStyle = "#0a0812"; c.lineWidth = 4;
    c.beginPath(); c.arc(cx, cy, 138, 0, 7); c.stroke();
    c.beginPath(); c.arc(cx, cy, 92, 0, 7); c.stroke();
    for (let k = 0; k < 12; k++) { const a = k / 12 * 7; c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx + Math.cos(a) * 138, cy + Math.sin(a) * 138); c.stroke(); }
    c.restore();
    // moonlight behind
    c.globalCompositeOperation = "lighter";
    const g = c.createRadialGradient(cx, cy - 6, 4, cx, cy - 6, 120);
    g.addColorStop(0, b.gilt ? "rgba(255,224,138,0.28)" : "rgba(167,139,250,0.24)");
    g.addColorStop(1, "rgba(167,139,250,0)");
    c.fillStyle = g; c.fillRect(cx - 120, cy - 126, 240, 240);
    c.globalCompositeOperation = "source-over";
    // the bloom itself, large, rooted low in the frame
    FL.draw(c, ev.genome, cx, cy + 96, 9, 1);
    // brand tag
    FX.text(c, "SNHP", SIZE - 22, SIZE - 9, "rgba(200,196,216,0.3)", 1);
  }

  function hide() {
    const overlay = $("bloom-overlay");
    if (!overlay) return;
    overlay.classList.remove("show");
    setTimeout(() => overlay.classList.add("hidden"), 600);
  }

  A.bloom = { show, hide };
})();

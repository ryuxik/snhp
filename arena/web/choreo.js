/* The choreographer: turns world state into motion, and motion into story.
   - duels read through the gap bar; the focal fight gets the warm key light
   - THE HOLD: frozen stillness before every close, then the payoff
   - children ASSEMBLE from their parents' slices (the crossover map, visible)
   - newcomers walk in through the gate; the dead ember toward the crypt
   - back a house and the camera leans your way (the camera is the highlighter) */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  const S = A.stage, W = A.world, FX = A.fx, SP = A.sprites;
  let _t = 0, _reduced = false;

  function init(opts) {
    _reduced = opts && opts.reduced;
    W.onDuelOffer = (d, ev) => {
      const z = S.ZONES[d.zone]; if (!z) return;
      const col = ev.actor === "seller" ? "#ffe08a" : "#a78bfa";
      const from = ev.actor === "seller" ? z.x - 11 : z.x + 11;
      // sigil projectile: one bright mote arcs to the midpoint + a spark tail
      if (!_reduced) {
        FX.spawn(from, z.y - 10, (z.x - from) * 0.12, -1.1, 12, col, 0.14, 2);
        for (let i = 0; i < 2; i++) FX.spawn(from, z.y - 9, (z.x - from) * 0.07, -0.4 - Math.random() * 0.5, 12, col, 0.03);
      }
      // concession = ground physically given: the actor rocks back a step
      const actor = W.agents.get(ev.actor === "seller" ? d.a : d.b);
      if (actor) actor.nudge = 4;
    };
    W.onDuelClose = (d, ev) => {
      const z = S.ZONES[d.zone]; if (!z) return;
      const joint = (ev.surplus.seller + ev.surplus.buyer);
      const focal = z === _focusZoneRef;
      // payoff discipline: the FOCAL fight gets the big twin numbers; a
      // background close whispers one small joint figure. If every close
      // shouts, none of them matter.
      if (focal) {
        FX.burst(z.x, z.y - 6, 12, "#ffe08a", 1.6, 0.05);
        FX.floatNum("+" + Math.round(ev.surplus.seller * 100), z.x - 22, z.y - 16, "#ffe08a", 2);
        FX.floatNum("+" + Math.round(ev.surplus.buyer * 100), z.x + 22, z.y - 16, "#ffe08a", 2);
      } else {
        FX.burst(z.x, z.y - 6, 5, "#ffe08a", 1.0, 0.05);
        FX.floatNum("+" + Math.round(joint * 100), z.x, z.y - 14, "#e8c060", 1);
      }
      if (joint > 0.45 && !_reduced) FX.impact(z.x, z.y - 6); // rationed: big deals only
      d.shake = 6;
    };
    W.onDuelWalk = (d, ev) => {
      const z = S.ZONES[d.zone]; if (!z) return;
      for (let i = 0; i < 5; i++) FX.spawn(z.x + (i - 2) * 2, z.y - 8, (i - 2) * 0.5, -1.2, 24, "#8a5a5e", 0.12, 1);
      FX.floatNum("NO DEAL", z.x, z.y - 16, "#8a5a5e");
    };
  }

  function update() {
    _t++;
    const focus = _focusZone();
    for (const a of W.agents.values()) {
      a.phase += 0.06;
      if (a.born > 0) a.born = Math.max(0, a.born - 0.02);
      if (a.nudge > 0) { a.x -= a.facing * 0.5; a.nudge--; }
      if (a.assembling) { // held in stasis until the parts land
        if (++a.assembling.t > 54) {
          a.crossoverMap = a.assembling.crossover || {};
          a.assembling = null; a.born = 0.5; a.crossPanel = 90;
          FX.burst(a.x, a.y - 8, 8, "#ffe08a", 1.0, 0.04);
          A.sound.play("birth");
        }
        continue;
      }
      if (a.crossPanel > 0) a.crossPanel--;
      if (a.mode === "dying") { a.dying += 0.05; if (a.dying > 2.2) { W.agents.delete(a.id); _deathFx(a); } continue; }
      let tx = a.hx, ty = a.hy;
      if (a.mode === "duel" || a.mode === "court") { tx = a.tx; ty = a.ty; }
      else if (a.entering) { tx = a.hx0; ty = a.hy0; if (Math.abs(a.x - tx) < 2) a.entering = false; }
      else {
        const near = focus && Math.abs(a.hx0 - focus.x) < 90;
        if (near) { tx = focus.x + (a.id % 2 ? 22 : -22) + Math.sin(a.phase) * 6; ty = focus.y + 12 + (a.id % 3) * 3; }
        else { tx = a.hx0 + Math.sin(a.phase) * 3; ty = a.hy0; }
      }
      const dx = tx - a.x, dy = ty - a.y;
      const sp = a.entering ? 0.55 : (a.mode === "duel" || a.mode === "court") ? 0.9 : 0.35;
      if (Math.abs(dx) > 0.5) { a.x += Math.sign(dx) * Math.min(sp, Math.abs(dx)); a.facing = dx < 0 ? -1 : 1; a.walking = true; }
      else a.walking = false;
      a.y += dy * 0.1;
      a.y = Math.max(S.FLOOR_Y + 8, Math.min(S.WORLD_H - 12, a.y));
    }
    // duels: hold countdown -> close FX; expiry
    for (const [k, d] of W.duels) {
      d.t = Math.max(0, d.t - 1);
      if (d.phase === "hold" && --d.hold <= 0) {
        d.phase = "close"; d.flash = 14; d.dead = 40;
        if (W.onDuelClose) W.onDuelClose(d, d.pending);
      }
      if (d.dead > 0 && --d.dead <= 0) { _release(d); W.duels.delete(k); }
    }
    for (const [k, c] of W.courts) { if (c.beat > 0) c.beat--; if (c.dead > 0 && --c.dead <= 0) { _releaseCourt(c); W.courts.delete(k); } }
    for (let i = W.dealHeat.length - 1; i >= 0; i--) { if (--W.dealHeat[i].life <= 0) W.dealHeat.splice(i, 1); }
    FX.updateParticles(); FX.updateFloats(); FX.updateOrbs();
  }

  function _release(d) { for (const id of [d.a, d.b]) { const a = W.agents.get(id); if (a && a.mode === "duel") a.mode = "idle"; } }
  function _releaseCourt(c) { for (const id of [c.a, c.b]) { const a = W.agents.get(id); if (a && a.mode === "court") a.mode = "idle"; } }

  function _deathFx(a) {
    // embers rise orange -> violet, then DRIFT TOWARD THE CRYPT (the exit is a place)
    const toCrypt = Math.sign(S.CRYPT_X - a.x) * 0.35;
    for (let i = 0; i < 12; i++) {
      const up = i / 12;
      FX.spawn(a.x + (Math.random() - 0.5) * 8, a.y - 5 - up * 12,
        toCrypt + (Math.random() - 0.5) * 0.3, -0.5 - Math.random() * 0.7, 44,
        up > 0.5 ? "#a78bfa" : "#e8734a", -0.012);
    }
    // gold orbs: pause at apex, then home to the heirs
    const heirs = (a.heirs || []).map(h => W.agents.get(h)).filter(Boolean);
    for (let i = 0; i < Math.max(2, heirs.length * 2); i++) {
      const heir = heirs.length ? heirs[i % heirs.length] : null;
      FX.orb(a.x + (Math.random() - 0.5) * 6, a.y - 6, heir ? () => ({ x: heir.x, y: heir.y - 10 }) : null);
    }
    A.sound.play("ember");
  }

  function _focusZone() {
    let best = null, bestScore = -1;
    for (const d of W.duels.values()) {
      if (d.zone < 0 || d.phase === "walk") continue;
      let s = 1 / (1 + d.spread);
      if (d.stakes && d.stakes.last_stand) s += 2;
      if (d.stakes && d.stakes.rivalry) s += 1;
      if (d.phase === "hold" || d.flash > 0) s += 3;
      // your house's fights matter more — the camera leans your way
      if (W.myHouse) {
        const a = W.agents.get(d.a), b = W.agents.get(d.b);
        if ((a && a.house === W.myHouse) || (b && b.house === W.myHouse)) s += 0.75;
      }
      if (s > bestScore) { bestScore = s; best = S.ZONES[d.zone]; }
    }
    return best;
  }
  function focusX() { const z = _focusZone(); return z ? z.x : S.WORLD_W / 2; }

  function _bob(a) {
    if (a.walking) return 0;
    return Math.sin(a.phase) * 0.5;
  }
  function _blink(a) { return ((_t + a.id * 37) % 260) < 5; }

  let _focusZoneRef = null;
  function _attn(x, fx) {
    const d = Math.abs(x - fx);
    if (d < 70) return 1;
    return Math.max(0.42, 1 - (d - 70) / 150);
  }

  function draw(ctx, cam) {
    S.draw(ctx, cam);
    const fz = _focusZone(); _focusZoneRef = fz;
    const fx = fz ? fz.x : S.WORLD_W / 2;
    ctx.save(); ctx.translate(-cam.x, 0);

    // warm key light on the focal fight — the brightest warm thing in the hall
    if (fz) {
      ctx.globalCompositeOperation = "lighter";
      const r = 46, g0 = ctx.createRadialGradient(fz.x, fz.y, 0, fz.x, fz.y, r);
      g0.addColorStop(0, "rgba(245,200,110,0.16)");
      g0.addColorStop(0.6, "rgba(232,163,61,0.07)");
      g0.addColorStop(1, "rgba(232,163,61,0)");
      ctx.fillStyle = g0; ctx.fillRect(fz.x - r, fz.y - r, r * 2, r * 2);
      ctx.globalCompositeOperation = "source-over";
    }

    // deal-heat floor glows
    ctx.globalCompositeOperation = "lighter";
    for (const h of W.dealHeat) {
      const al = h.life / 60, r = 10;
      const g = ctx.createRadialGradient(h.x, h.y, 0, h.x, h.y, r);
      g.addColorStop(0, `rgba(232,115,74,${0.14 * al})`); g.addColorStop(1, "rgba(232,115,74,0)");
      ctx.fillStyle = g; ctx.fillRect(h.x - r, h.y - r, r * 2, r * 2);
    }
    ctx.globalCompositeOperation = "source-over";

    const myRamp = W.myHouse ? SP.rampForHouse(W.myHouse) : null;
    const list = [...W.agents.values()].sort((p, q) => p.y - q.y);
    for (const a of list) {
      if (a.assembling) { _drawAssembly(ctx, a); continue; }
      const focal = a.mode === "duel" || a.mode === "court";
      ctx.globalAlpha = focal ? 1 : _attn(a.x, fx);
      if (a.mode === "dying") ctx.globalAlpha = Math.max(0, 1 - a.dying / 2.2);
      const glow = a.staked ? 0.7 : Math.min(1, a.energy / 300);
      const critFlick = a.critical && (Math.floor(_t * 0.4) % 2) ? 0.4 : 1;
      ctx.globalAlpha *= critFlick;
      const mine = W.myHouse && a.house === W.myHouse;
      SP.draw(ctx, a.g, a.x, a.y, {
        facing: a.facing, bob: _bob(a),
        frame: a.walking ? (Math.floor(a.phase * 4) % 2) : 0,
        blink: _blink(a),
        glow: focal ? glow + 0.3 : glow,
        pennant: mine ? (myRamp ? myRamp[3] : "#a78bfa") : null,
      });
      // the knight's CREST: its flower, phenotype of its genome, blooming with
      // energy and wilting toward death — the strategy carried like heraldry.
      if (!a.assembling && A.flora) {
        const fullness = a.critical ? 0.2 : Math.max(0.25, Math.min(1, a.energy / 260));
        A.flora.draw(ctx, a.g, Math.round(a.x + 6 * a.facing), Math.round(a.y - 24 + _bob(a)), 0.62, fullness);
      }
      ctx.globalAlpha = 1;
      if (a.crossPanel > 0) _drawCrossPanel(ctx, a);
    }

    for (const d of W.duels.values()) _drawDuel(ctx, d);
    for (const c of W.courts.values()) _drawCourt(ctx, c);

    FX.drawParticles(ctx); FX.drawOrbs(ctx); FX.drawFloats(ctx);
    ctx.restore();

    // focus-follow attention vignette (screen space)
    const sx = fx - cam.x, sy = 224;
    const g = ctx.createRadialGradient(sx, sy, 40, sx, sy, 300);
    g.addColorStop(0, "rgba(6,5,12,0)");
    g.addColorStop(0.55, "rgba(6,5,12,0.18)");
    g.addColorStop(1, "rgba(6,5,12,0.62)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 480, 270);

    S.drawForeground(ctx, cam);
    _drawNameplate(ctx, cam);
  }

  // the child assembles: head / torso / hem slices fly in from each parent,
  // staggered — inheritance you can SEE (which parent gave which block)
  function _drawAssembly(ctx, a) {
    const asm = a.assembling;
    const pa = W.agents.get(asm.pa), pb = W.agents.get(asm.pb);
    const fromA = pa ? { x: pa.x, y: pa.y } : { x: a.x - 30, y: a.y };
    const fromB = pb ? { x: pb.x, y: pb.y } : { x: a.x + 30, y: a.y };
    const co = asm.crossover || {};
    // block -> slice source: head=bargain, torso=tactic, hem=risk (a readable
    // simplification of the 6-block map; the panel shows the full truth)
    const srcOf = (blk, dflt) => (co[blk] === "pa" ? fromA : co[blk] === "pb" ? fromB : dflt);
    const bands = [
      { band: "head", from: srcOf("bargain", fromA), start: 0 },
      { band: "torso", from: srcOf("tactic", fromB), start: 12 },
      { band: "hem", from: srcOf("risk", fromA), start: 24 },
    ];
    for (const b of bands) {
      const tt = Math.max(0, Math.min(1, (asm.t - b.start) / 24));
      if (tt <= 0) continue;
      const s = SP.slice(a.g, b.band);
      const ease = 1 - Math.pow(1 - tt, 3);
      const x = b.from.x + (a.x - b.from.x) * ease;
      const y = (b.from.y - 14) + ((a.y - 20 + b.sy * 0) - (b.from.y - 14)) * ease + b.start * 0; // vertical handled below
      const destY = a.y - (26 - b.start ? 0 : 0);
      // draw the slice at interpolated position, landing at its band offset
      const landY = a.y - 27 + s.sy;
      const yy = (b.from.y - 20) + (landY - (b.from.y - 20)) * ease;
      ctx.globalAlpha = 0.5 + 0.5 * tt;
      ctx.drawImage(s.canvas, 0, s.sy, s.w, s.sh, Math.round(x - s.w / 2), Math.round(yy), s.w, s.sh);
      // trail motes in the giving parent's color
      if (tt < 1 && asm.t % 3 === 0) FX.spawn(x, yy + 4, 0, 0.1, 8, s.ramp[3], 0);
      ctx.globalAlpha = 1;
    }
  }

  // which parent gave which block — six ticks of colored truth over the child
  function _drawCrossPanel(ctx, a) {
    const asmCo = a.crossCo || null;
    const pa = a.parents ? W.agents.get(a.parents[0]) : null;
    const pb = a.parents ? W.agents.get(a.parents[1]) : null;
    const rA = pa ? SP.rampFor(pa.g)[3] : "#e8a33d";
    const rB = pb ? SP.rampFor(pb.g)[3] : "#a78bfa";
    const co = a.crossoverMap || {};
    const blocks = ["bargain", "risk", "bundle", "mating", "attestation", "tactic"];
    const bx = Math.round(a.x - 12), by = Math.round(a.y - 36);
    ctx.globalAlpha = Math.min(1, a.crossPanel / 20);
    blocks.forEach((blk, i) => {
      const src = co[blk];
      ctx.fillStyle = src === "pa" ? rA : src === "pb" ? rB : "#c8c4d8";
      ctx.fillRect(bx + i * 4, by, 3, 3);
    });
    FX.text(ctx, "HEIR", bx + 1, by - 7, "#c8c4d8", 1);
    ctx.globalAlpha = 1;
  }

  function _drawDuel(ctx, d) {
    if (d.zone < 0) return;
    const z = S.ZONES[d.zone]; const bx = z.x, by = z.y - 30;
    // the bargaining table between them (a physical place for the deal)
    ctx.fillStyle = "#2b2033"; ctx.fillRect(z.x - 7, z.y - 4, 14, 4);
    ctx.fillStyle = "#3a2a3a"; ctx.fillRect(z.x - 7, z.y - 4, 14, 1);
    if (d.phase === "hold") {
      // stillness: a thin bright line of tension where the bar was
      ctx.fillStyle = "#fff"; ctx.globalAlpha = 0.5 + 0.4 * Math.sin(_t * 0.8);
      ctx.fillRect(bx - 3, by, 6, 2); ctx.globalAlpha = 1;
      return;
    }
    if (d.phase === "close" && d.flash > 0) {
      d.flash--;
      const r = 8 + (14 - d.flash);
      ctx.globalCompositeOperation = "lighter";
      const g = ctx.createRadialGradient(z.x, z.y - 6, 0, z.x, z.y - 6, r);
      g.addColorStop(0, "rgba(255,255,255,0.8)"); g.addColorStop(0.4, "rgba(255,224,138,0.5)"); g.addColorStop(1, "rgba(255,224,138,0)");
      ctx.fillStyle = g; ctx.fillRect(z.x - r, z.y - 6 - r, r * 2, r * 2);
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "#ffe08a"; ctx.fillRect(bx - 6, by, 12, 2);
      return;
    }
    if (d.phase === "walk") {
      ctx.fillStyle = "#8a5a5e"; for (let i = 0; i < 5; i++) ctx.fillRect(bx - 6 + i * 3, by + (i % 2) * 2, 2, 2);
      return;
    }
    const focal = S.ZONES[d.zone] === _focusZoneRef;
    const w = Math.max(2, Math.min(40, Math.log(1 + d.spread * 4) / Math.log(5) * 40));
    const pw = Math.max(2, Math.min(40, Math.log(1 + d.prevSpread * 4) / Math.log(5) * 40));
    const narrowing = d.spread <= d.prevSpread;
    const h = focal ? 3 : 2;
    ctx.globalAlpha = focal ? 0.35 : 0.2; ctx.fillStyle = "#7c7790";
    ctx.fillRect(bx - pw / 2, by, pw, 2); ctx.globalAlpha = 1;
    if (!focal) ctx.globalAlpha = 0.55;
    ctx.fillStyle = narrowing ? (focal ? "#d8c8ff" : "#bba6ff") : "#e8734a";
    ctx.fillRect(bx - w / 2, by, w, h);
    ctx.globalAlpha = 1;
    if (d.kind === "bundle" && d.runeCount) {
      for (let i = 0; i < d.runeCount; i++) { ctx.fillStyle = i < (d.t > 0 ? d.runeCount : 0) ? "#a78bfa" : "#2a2438"; ctx.fillRect(bx - d.runeCount * 3 + i * 6, by - 8, 4, 4); }
    }
  }

  function _drawCourt(ctx, c) {
    // the courtship table: two candles, a pact in progress
    ctx.fillStyle = "#2b2033"; ctx.fillRect(c.x - 10, c.y - 3, 20, 3);
    ctx.fillStyle = "#3a2a1e"; ctx.fillRect(c.x - 8, c.y - 6, 1, 3); ctx.fillRect(c.x + 7, c.y - 6, 1, 3);
    ctx.fillStyle = "#ffe08a"; ctx.fillRect(c.x - 8, c.y - 8, 1, 2); ctx.fillRect(c.x + 7, c.y - 8, 1, 2);
    if (c.phase === "impasse") {
      FX.text(ctx, "NO PACT", c.x - 13, c.y - 18, "#8a5a5e", 1);
    } else if (c.beat > 0) {
      ctx.fillStyle = "#a78bfa"; ctx.fillRect(c.x - 1, c.y - 11, 2, 2);
    }
  }

  function _drawNameplate(ctx, cam) {
    const z = _focusZoneRef; if (!z) return;
    let d = null; for (const dd of W.duels.values()) if (dd.zone >= 0 && S.ZONES[dd.zone] === z) { d = dd; break; }
    if (!d) return;
    const a = W.agents.get(d.a), b = d.house ? null : W.agents.get(d.b);
    if (!a) return;
    let label = b ? (a.house + " v " + b.house) : a.name;
    if (d.stakes && d.stakes.rivalry) label += "  MEETING " + d.stakes.rivalry.meetings;
    else if (d.stakes && d.stakes.last_stand) label = a.house + "  LAST STAND";
    FX.text(ctx, label, Math.round((480 - FX.textW(label, 1)) / 2), 270 - 40, "#c8c4d8", 1);
  }

  A.choreo = { init, update, draw, focusX };
})();

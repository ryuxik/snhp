/* Six diegetic sounds, synthesized (no assets), muted by default. The bell is
   what calls a backgrounded tab home. In-world unmute via the ♪ button. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  let ctx = null, on = false, master = null;

  function ensure() {
    if (ctx) return;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0.18; master.connect(ctx.destination);
    } catch (e) { ctx = null; }
  }
  function toggle() { ensure(); if (ctx && ctx.state === "suspended") ctx.resume(); on = !on; return on; }
  function enabled() { return on; }

  function tone(freq, dur, type, gain, glideTo) {
    if (!on || !ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type || "sine"; o.frequency.value = freq;
    if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, ctx.currentTime + dur);
    g.gain.value = 0; g.gain.linearRampToValueAtTime(gain || 0.3, ctx.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);
    o.connect(g); g.connect(master); o.start(); o.stop(ctx.currentTime + dur);
  }
  function noise(dur, gain) {
    if (!on || !ctx) return;
    const n = ctx.createBufferSource(), b = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    const d = b.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    n.buffer = b; const g = ctx.createGain(); g.gain.value = gain || 0.15; n.connect(g); g.connect(master); n.start();
  }

  const S = {
    clasp() { tone(880, 0.12, "triangle", 0.25, 1320); },
    shatter() { noise(0.18, 0.12); },
    bell() { tone(392, 1.2, "sine", 0.35, 196); tone(588, 1.0, "sine", 0.15); },
    ember() { noise(0.3, 0.05); },
    gutter() { tone(140, 0.25, "sawtooth", 0.08, 90); },
    birth() { tone(660, 0.2, "sine", 0.18, 990); },
  };

  A.sound = { toggle, enabled, play: (k) => { if (S[k]) S[k](); } };
})();

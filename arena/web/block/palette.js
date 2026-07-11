/* The block's color system. Castlevania-NES heritage, warmed up (same DNA as
   arena/web/sprites.js — violet shadows, candle-warm highlights) but daylit and
   civic: NYC brick, awning color, neon. The SNHP block stays warm all week; the
   sticker block drains toward gray as regulars churn (mood.gray in the JSON).
   Day 0 both blocks are IDENTICAL — the drain starts at 0.

   Nothing here reads the sim; it only turns (hour, weather, drain) into colors. */
(function () {
  "use strict";
  const B = (window.Block = window.Block || {});

  // ── color math ────────────────────────────────────────────────────────────
  function rgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function hex(r, g, b) {
    return "#" + [r, g, b].map(v => Math.max(0, Math.min(255, v | 0)).toString(16).padStart(2, "0")).join("");
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function mix(h1, h2, t) {
    const a = rgb(h1), b = rgb(h2);
    return hex(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t));
  }
  function hexA(h, a) { const c = rgb(h); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
  // desaturate toward the pixel's own luma by amount g (0..1) — the gray drain
  function drain(h, g) {
    if (!g) return h;
    const c = rgb(h), l = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2];
    // pull toward luma, and a touch darker/cooler so the street reads "tired"
    return hex(lerp(c[0], l, g) * (1 - 0.10 * g), lerp(c[1], l, g) * (1 - 0.10 * g), lerp(c[2], l, g) * (1 - 0.06 * g));
  }
  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function smooth(a, b, x) { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }

  // ── the sky, keyed by clock hour (0..24) ──────────────────────────────────
  // keyframes: [hour, topColor, horizonColor]
  const SKY = [
    [0.0,  "#0d1020", "#141a2e"],
    [4.5,  "#12142a", "#241d3a"],
    [5.6,  "#241f3e", "#5a3a52"],
    [6.6,  "#41406e", "#e0a06a"], // dawn peach
    [8.0,  "#5f83b6", "#d6dfe6"],
    [12.0, "#79a7d6", "#d2e2ee"], // clear midday
    [16.0, "#7ba0cc", "#ecdcc2"],
    [18.4, "#4c4a84", "#e8964e"], // dusk
    [19.8, "#2a2746", "#864e5c"],
    [21.5, "#141830", "#2a2140"],
    [24.0, "#0d1020", "#141a2e"],
  ];
  function skyAt(hour, weather) {
    hour = ((hour % 24) + 24) % 24;
    let i = 0;
    while (i < SKY.length - 1 && SKY[i + 1][0] <= hour) i++;
    const a = SKY[i], b = SKY[Math.min(i + 1, SKY.length - 1)];
    const t = b[0] === a[0] ? 0 : clamp01((hour - a[0]) / (b[0] - a[0]));
    let top = mix(a[1], b[1], t), hor = mix(a[2], b[2], t);
    if (weather === "rain") { top = mix(top, "#3a3d4a", 0.55); hor = mix(hor, "#54565f", 0.6); top = drain(top, 0.5); hor = drain(hor, 0.5); }
    else if (weather === "overcast") { top = mix(top, "#6b6d78", 0.32); hor = mix(hor, "#8a8b92", 0.3); top = drain(top, 0.28); hor = drain(hor, 0.28); }
    return { top, hor };
  }

  // 0 in daylight → 1 deep night. Drives neon/window/lamp glow + string lights.
  function nightFactor(hour) {
    hour = ((hour % 24) + 24) % 24;
    // fully night before 5.2 and after 20; day 8..17
    const morning = 1 - smooth(5.2, 7.6, hour);   // 1 at night, 0 by morning
    const evening = smooth(17.4, 20.2, hour);      // 0 in day, 1 by night
    return clamp01(Math.max(morning, evening));
  }
  // dawn delivery window intensity (peaks ~6.2am) — the truck ballet
  function dawnFactor(hour) {
    return clamp01(1 - Math.abs(hour - 6.3) / 1.6);
  }

  // ── civic palette (facades, sidewalk, street) — warm NYC, violet-shadowed ──
  const CIVIC = {
    brick:    ["#3a2830", "#5a3a3a", "#7a4a42"],   // shadow, mid, lit brick ramp
    stone:    ["#2e2a3a", "#45415a", "#5e5a72"],
    cornice:  "#2b2334",
    sidewalk: ["#4a4656", "#5c5868", "#6e6a7a"],   // near→far tiles
    curb:     "#39364a",
    street:   ["#242231", "#2e2b3d"],
    lamp:     "#ffd98a",
    window_lit_day: "#cfe2ee",
    window_lit_night: "#ffdf9a",
    window_dark: "#22202e",
  };

  // ── per-venue accent (the storefront identity; constant across the week) ───
  // sign/awning primary, secondary, and the "glow" color for its neon at night
  const VENUE = {
    machine: { a: "#2f5a6a", b: "#d8e4e8", glow: "#7fe0ff", trim: "#c04a4a" },
    deli:    { a: "#d8a020", b: "#b83a34", glow: "#5ad06a", trim: "#e8c060" }, // yellow/red awning, green OPEN
    boba:    { a: "#2fae9e", b: "#e58ab4", glow: "#7ff0dd", trim: "#8a5a3a" }, // teal + pink, brown pearls
    bakery:  { a: "#c88a4a", b: "#f0dcb0", glow: "#ffcf8a", trim: "#8a5a2a" }, // warm oven
    flower:  { a: "#7fb85a", b: "#f4f0e8", glow: "#a8f07a", trim: "#5a8a3a" },
    barber:  { a: "#c93a3a", b: "#f0f0f4", glow: "#ff6a6a", trim: "#2f4aa0" }, // red/white/blue pole
    fashion: { a: "#1a1822", b: "#f0f0f4", glow: "#e05aa0", trim: "#c05a8a" }, // minimalist black/white + magenta
    vintage: { a: "#b8912e", b: "#3a8a86", glow: "#f0c860", trim: "#7a5a2a" }, // mustard + teal
    bar:     { a: "#2a3a6a", b: "#e8a838", glow: "#ffb84a", trim: "#c94a4a" }, // deep blue + amber neon
    parking: { a: "#5a5866", b: "#e8c838", glow: "#ffe04a", trim: "#c93a3a" }, // gray lot, yellow gate
  };

  // walker persona base clothing (the anonymous crowd — regulars override)
  const PERSONA = {
    "office-worker": ["#3a4a6a", "#2e5a8a", "#556070", "#6a5a7a"],
    "student":       ["#3a8a62", "#c05a8a", "#c07a2a", "#3a6a8a"],
    "local":         ["#8a5a4a", "#6a5a7a", "#4a6a5a", "#8a7a4a"],
    "tourist":       ["#c93a3a", "#d8a020", "#2fae9e", "#e58ab4"],
  };
  const SKIN = { tan: "#caa079", brown: "#8a5a3a", pale: "#e0b090", dark: "#5a3a28" };
  const HAIR = { gray: "#b8b2c0", brown: "#4a3428", black: "#201a26", sandy: "#b89050",
                 white: "#e4e0ea", bald: "#caa079", blonde: "#d8b860" };

  B.pal = {
    rgb, hex, mix, hexA, drain, clamp01, smooth,
    skyAt, nightFactor, dawnFactor,
    CIVIC, VENUE, PERSONA, SKIN, HAIR,
  };
})();

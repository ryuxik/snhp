"use strict";
/* PAR — the front end. Renders the loop-locked screens (landing, onboarding, play,
   reveal) and runs the daily negotiation LIVE against the SNHP engine: every House move
   is POST /par/house_move and the score/board are POST /par/submit + /par/group (see
   ../api.py / ../SPEC.md). Each call falls back to an offline stand-in, so index.html
   still runs with zero backend.

   SIDE-AWARE: a scenario is "sell" (you want a HIGH number, the House buys) or "buy"
   (you want LOW, the House sells). The play canyon is symmetric (it shows the |gap|), so
   the direction shows up only in labels, the slider clamp, and scoring. Money is in each
   scenario's native units (a $118k salary, an $11,200 car) via a per-scenario `unit`. */
const $ = (id) => document.getElementById(id);
const show = (id) => document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("on", s.id === id));
const FN = 'font-family="ui-monospace,Menlo,monospace"';
const V = "#A78BFA", VB = "#BBA6FF", VD = "#9385D6";
// per-scenario unit: "k" -> "$118k" (salary, in thousands); "" -> "$11,200" (car, raw $).
const fmt = (v) => DAY.unit === "k" ? ("$" + (Math.round(v * 10) / 10) + "k") : ("$" + Math.round(v).toLocaleString());

/* ---- today's deal (prod: GET /par/today) ---------------------------------- */
/* floor = YOUR walk-away (sell: the least you'd take; buy: the most you'd pay).
   target = your aspiration. offers/willing/msg = the OFFLINE House stand-in (online,
   every move comes from POST /par/house_move). Values are in each scenario's native units
   and match the backend deck, so a submitted close grades correctly either way. */
const SCENARIOS = {
  sell: {
    no: 216, side: "sell", title: "the salary talk", floor: 90, target: 130, par: 118, rounds: 5,
    unit: "k", axisMin: 90, axisMax: 124, gapK: 4, step: 1,
    cta: { hook: "a raise, an offer, a review — get the perfect negotiator in your corner.", verb: "have the agent coach your next raise" },
    offers: [95, 103, 109, 114, 117], willing: [98, 106, 111, 115, 118],
    msg: ['“We can do $95k.”', '“I can stretch to $103k.”', '“$109k — near the top of band.”',
      '“$114k, out on a limb here.”', '“Final: $117k. Take it or we re-open.”'],
  },
  buy: {
    no: 214, side: "buy", title: "the used car", floor: 14000, target: 9000, par: 11200, rounds: 5,
    unit: "", axisMin: 9000, axisMax: 14000, gapK: 0.032, step: 100,
    cta: { hook: "a car, rent, any big-ticket haggle — have the agent coach every move.", verb: "have the agent coach your next deal" },
    offers: [13000, 12400, 11900, 11500, 11200], willing: [12400, 11900, 11500, 11200, 11000],
    msg: ['“$13,000, and that’s me being nice.”', '“I could come down to $12,400.”',
      '“$11,900 — now you’re squeezing me.”', '“$11,500, that’s basically cost.”',
      '“$11,200. Last number, take it.”'],
  },
};
const DAY = SCENARIOS[new URLSearchParams(location.search).get("s") === "buy" ? "buy" : "sell"];
const isSell = () => DAY.side === "sell";
// scoring, direction baked in: selling wants high (deal/par), buying wants low (par/deal).
const pctOf = (deal) => Math.round((isSell() ? deal / DAY.par : DAY.par / deal) * 100);
const leftOf = (deal) => Math.round((isSell() ? DAY.par - deal : deal - DAY.par) * 10) / 10;

/* ---- landing brand mark (the iconic canyon, violet seal) ------------------ */
function landCanyon() {
  $("land-canyon").innerHTML =
    '<path fill="#E8E8E3" d="M0,0 L540,0 L540,108 L525,108 L460,86 L380,64 L290,30 L200,74 L110,54 L20,40 L0,40 Z"/>' +
    '<path fill="#E8E8E3" d="M0,220 L540,220 L540,112 L525,112 L460,134 L380,156 L290,190 L200,146 L110,166 L20,180 L0,180 Z"/>' +
    '<path fill="' + V + '" d="M460,86 L525,110 L460,134 Z"/>';
}

/* ---- onboarding beat (drag to close the gap) ------------------------------ */
function onbBeat(p) {
  const g = 110 - p * 104, X = 130 - Math.round(p * 18), cy = 140, tl = cy - g, bl = cy + g, sealed = p >= 0.999;
  let s = '<rect x="0" y="0" width="540" height="' + tl + '" fill="#E8E8E3"/>' +
          '<rect x="0" y="' + bl + '" width="540" height="' + (280 - bl) + '" fill="#E8E8E3"/>';
  if (!sealed) {
    const Y = 95 + Math.round(p * 17);
    s += '<rect x="0" y="' + tl + '" width="540" height="' + (bl - tl) + '" fill="' + V + '" fill-opacity="0.10"/>' +
         '<line x1="0" y1="' + tl + '" x2="540" y2="' + tl + '" stroke="' + V + '" stroke-width="2"/>' +
         '<line x1="0" y1="' + bl + '" x2="540" y2="' + bl + '" stroke="' + V + '" stroke-width="2"/>' +
         '<text x="40" y="' + (tl + 26) + '" font-size="20" fill="' + VB + '" ' + FN + '>$' + X + 'k</text>' +
         '<text x="40" y="' + (bl - 12) + '" font-size="20" fill="' + VB + '" ' + FN + '>$' + Y + 'k</text>';
  } else {
    s += '<line x1="0" y1="' + cy + '" x2="540" y2="' + cy + '" stroke="' + V + '" stroke-width="6"/>' +
         '<text x="270" y="' + (cy - 22) + '" font-size="30" fill="' + VB + '" text-anchor="middle" ' + FN + '>deal · $' + X + 'k</text>';
  }
  $("onb-canyon").innerHTML = s;
}

/* ---- play: the live canyon (frontier, open channel, preview) -------------- */
const g = { t: 0, asks: [], houseOffers: [], curOffer: null, curMsg: "", deal: null, walked: false, over: false, busy: false };
function xR(i) { return 50 + i * 110; }
function gpx(a, o) { return Math.max(6, Math.min(190, Math.abs(a - o) * DAY.gapK)); }
function drawPlay(C) {
  const fi = g.t, top = [], bot = [];
  const ask = (i) => (i < g.t ? g.asks[i] : C);
  for (let i = 0; i <= fi; i++) { const gg = gpx(ask(i), g.houseOffers[i]); top.push([xR(i), 120 - gg / 2]); bot.push([xR(i), 120 + gg / 2]); }
  const fx = xR(fi), ft = top[fi][1], fb = bot[fi][1];
  let tp = "M0,0 L540,0 L540," + ft + " L" + fx + "," + ft + " "; for (let i = fi - 1; i >= 0; i--) tp += "L" + top[i][0] + "," + top[i][1] + " "; tp += "L0," + top[0][1] + " Z";
  let bp = "M0,240 L540,240 L540," + fb + " L" + fx + "," + fb + " "; for (let i = fi - 1; i >= 0; i--) bp += "L" + bot[i][0] + "," + bot[i][1] + " "; bp += "L0," + bot[0][1] + " Z";
  let s = '<path fill="#E8E8E3" d="' + tp + '"/><path fill="#E8E8E3" d="' + bp + '"/>';
  for (let i = fi + 1; i < DAY.rounds; i++) s += '<line x1="' + xR(i) + '" y1="' + ft + '" x2="' + xR(i) + '" y2="' + fb + '" stroke="#34353C" stroke-width="1" stroke-dasharray="3 5"/><text x="' + xR(i) + '" y="' + (fb + 22) + '" font-size="12" fill="#4A4B52" text-anchor="middle" ' + FN + '>' + (i + 1) + '</text>';
  const topLabel = isSell() ? "you want ↑" : "the house ↑", botLabel = isSell() ? "the house ↓" : "you want ↓";
  s += '<line x1="' + fx + '" y1="' + (ft - 4) + '" x2="' + fx + '" y2="' + (fb + 4) + '" stroke="#E8E8E3" stroke-width="2"/>' +
       '<circle cx="' + fx + '" cy="' + ft + '" r="4.5" fill="#E8E8E3"/><circle cx="' + fx + '" cy="' + fb + '" r="4.5" fill="#9A9A93"/>' +
       '<text x="' + fx + '" y="' + (ft - 13) + '" font-size="11" fill="#6B6C73" text-anchor="middle" ' + FN + '>now</text>' +
       '<text x="' + Math.max(fx - 12, 92) + '" y="124" font-size="13" fill="#9A9A93" text-anchor="end" ' + FN + '>' + fmt(Math.abs(C - g.curOffer)) + ' apart</text>' +
       '<text x="14" y="20" font-size="14" fill="#13151A" ' + FN + '>' + topLabel + '</text><text x="14" y="232" font-size="14" fill="#13151A" ' + FN + '>' + botLabel + '</text>';
  $("play-cv").innerHTML = s;
}

/* ---- reveal: the value-axis wedge (measures what you left) ----------------- */
function ym(v) { return Math.max(18, Math.min(222, 214 - (v - DAY.axisMin) / (DAY.axisMax - DAY.axisMin) * 196)); }
function drawReveal() {
  $("rev-sub").textContent = "no. " + DAY.no + " · " + DAY.title + " · result";
  const yP = ym(DAY.par), edge = isSell() ? "the ceiling" : "the floor";
  // par as a dashed reference line across the value axis (ceiling when selling, floor when
  // buying). Anchor the label away from the right-side wedge/hero: top-right when par is the
  // ceiling (above the close), left when it's the floor (below the close, near the hero).
  const lx = isSell() ? 560 : 44, la = isSell() ? "end" : "start";
  let s = '<line x1="40" y1="' + yP + '" x2="560" y2="' + yP + '" stroke="#5A4FA0" stroke-width="1" stroke-dasharray="5 5"/><text x="' + lx + '" y="' + (yP - 8) + '" font-size="12" fill="' + VD + '" text-anchor="' + la + '" ' + FN + '>par · ' + edge + ' · ' + fmt(DAY.par) + '</text>';
  if (g.deal != null) {
    const yD = ym(g.deal);
    // the two paths your asks took, converging on where you actually closed
    s += '<path d="M40,' + ym(DAY.target) + ' L300,' + yD + '" fill="none" stroke="#4F505A" stroke-width="1.5"/><path d="M40,' + ym(g.houseOffers[0]) + ' L300,' + yD + '" fill="none" stroke="#4F505A" stroke-width="1.5"/>';
    if (g.deal !== DAY.par) {
      // the wedge = the value between your close and par. The hero number sits to the
      // RIGHT of it on the dark field, vertically centred — works whether par is above
      // your close (selling) or below it (buying).
      // hero sits right of the wedge; scale its size to the string so a wide "$19.2k" or
      // "$1,300" never clips the right edge (a small "$7k" stays big).
      // near-par wins make a thin wedge high near the ceiling label; keep the hero clear of it
      const cy = (isSell() ? Math.max((yP + yD) / 2, yP + 30) : (yP + yD) / 2), hero = fmt(leftOf(g.deal)), hfs = Math.min(42, Math.round(134 / (hero.length * 0.6)));
      s += '<polygon points="300,' + yD + ' 470,' + yP + ' 470,' + yD + '" fill="#9D86F2"/>' +
           '<text x="486" y="' + (cy + 6) + '" font-size="' + hfs + '" fill="' + VB + '" ' + FN + '>' + hero + '</text>' +
           '<text x="488" y="' + (cy + 26) + '" font-size="12" fill="' + VD + '" ' + FN + '>on the table</text>';
    } else s += '<text x="430" y="' + (yP + 40) + '" font-size="24" fill="' + VB + '" text-anchor="middle" ' + FN + '>at par.</text>';
    // put the close label on the side away from par: below the node when par is the ceiling
    // (above), above the node when par is the floor (below) — so it never lands on the par line.
    const clY = isSell() ? yD + 22 : yD - 12;
    s += '<circle cx="300" cy="' + yD + '" r="6" fill="' + V + '"/><text x="294" y="' + clY + '" font-size="13" fill="#C9C9C4" text-anchor="end" ' + FN + '>you closed ' + fmt(g.deal) + '</text><text x="44" y="' + (ym(DAY.target) - 6) + '" font-size="11" fill="#6B6C73" ' + FN + '>your ask</text>';
  } else {
    const yF = ym(DAY.floor), cy = (yF + yP) / 2;
    s += '<polygon points="40,' + yF + ' 500,' + yP + ' 500,' + yF + '" fill="#5A4FA0" fill-opacity="0.25"/><text x="516" y="' + cy + '" font-size="26" fill="#B05A55" ' + FN + '>walked</text><text x="518" y="' + (cy + 22) + '" font-size="12" fill="#8A8A85" ' + FN + '>the whole room — gone</text>';
  }
  $("rev-cv").innerHTML = s;
}

/* ---- play flow ------------------------------------------------------------ */
function syncHouse() {
  const o = g.curOffer;
  $("play-house").innerHTML = '<span class="l">the house</span><span class="a">' + fmt(o) + '</span><span class="q">' + g.curMsg + '</span>';
  $("play-acc-amt").textContent = fmt(o); $("play-rnd").textContent = "round " + (g.t + 1) + " / " + DAY.rounds;
  // you'd never cross the number already on the table — that's just "accept". Selling:
  // don't counter BELOW their offer (clamp the min). Buying: don't offer ABOVE it (clamp max).
  const ask = $("play-ask");
  if (isSell()) { ask.min = o; if (+ask.value < o) { ask.value = o; } }
  else { ask.max = o; if (+ask.value > o) { ask.value = o; } }
  $("play-askv").textContent = fmt(+ask.value); $("play-cv-amt").textContent = fmt(+ask.value);
}
/* ---- scoreboard (the retention + virality layer) -------------------------- */
/* Offline stand-in for POST /par/submit's board. prod: this whole object is the API
   response (streak, percentile, distribution computed server-side over all players). */
const BOARD_BASE = [{ label: "<60", lo: 0, hi: 60, n: 31 }, { label: "60s", lo: 60, hi: 70, n: 34 },
{ label: "70s", lo: 70, hi: 80, n: 75 }, { label: "80s", lo: 80, hi: 90, n: 69 },
{ label: "90s", lo: 90, hi: 100, n: 25 }, { label: "par", lo: 100, hi: 1e9, n: 6 }];
const BOARD_TOTAL = BOARD_BASE.reduce((a, b) => a + b.n, 0);

function streakBump() {                                   // advance/reset by puzzle no. (DAY.no)
  const last = +(localStorage.getItem("par-last") || -1);
  let s = +(localStorage.getItem("par-streak") || 0), mx = +(localStorage.getItem("par-max") || 0);
  if (last !== DAY.no) {                                  // first finish of this puzzle
    s = (last === DAY.no - 1) ? s + 1 : 1;
    mx = Math.max(mx, s);
    localStorage.setItem("par-last", DAY.no); localStorage.setItem("par-streak", s); localStorage.setItem("par-max", mx);
  }
  return { streak: s, max_streak: mx };
}
function localBoard(pct) {
  let below = 0, mine = 0;
  const dist = BOARD_BASE.map((b) => {
    const here = pct >= b.lo && pct < b.hi;
    if (pct >= b.hi) below += b.n; else if (here) mine = b.n;
    return { label: b.label, count: b.n + (here ? 1 : 0), you: here };
  });
  return { ...streakBump(), played: BOARD_TOTAL + 1,
    percentile: Math.round((below + mine / 2) / BOARD_TOTAL * 100), distribution: dist };
}
/* the friend group, seeded by the share link (par.game/?g=<code>). Offline stand-in;
   prod: POST /par/group/join on arrival + GET /par/group for the board. */
const FRIENDS = [{ name: "Maya", pct: 96 }, { name: "Dev", pct: 88 }, { name: "Sam", pct: 74 },
{ name: "Priya", pct: 61 }, { name: "Theo", pct: null }];
function myGroup() {                                      // adopt a friend's code or mint one
  let gc = new URLSearchParams(location.search).get("g") || localStorage.getItem("par-group");
  if (!gc) gc = Math.random().toString(36).slice(2, 8);
  localStorage.setItem("par-group", gc);
  return gc;
}
/* IDENTITY without accounts: a persistent device id is the key; the name is just a label
   (unique only within a group — collisions get a server-side suffix). prod: swap the
   blocking prompt for an inline name field, and add a signed token if boards go public. */
function myUser() {
  let u = localStorage.getItem("par-user");
  if (!u) { u = "u_" + Math.random().toString(36).slice(2, 10); localStorage.setItem("par-user", u); }
  return u;
}
function myName() { return localStorage.getItem("par-name") || "you"; }   // non-blocking default
function setMyName(n) { localStorage.setItem("par-name", (n || "").trim().slice(0, 16) || "you"); }
function localFriends(myPct) {
  const rows = FRIENDS.concat([{ name: myName(), pct: myPct, you: true }]);
  rows.sort((a, b) => (b.pct == null ? -1 : a.pct == null ? 1 : b.pct - a.pct));
  return rows.map((r, i) => ({ ...r, rank: i + 1 }));
}

/* the LIVE board: register self in the group, submit the score (server recomputes it from
   `close` — the % can't be faked), fetch the ranked group. Falls back to the stand-in when
   no backend is reachable, so the SPA still runs offline. API base is same-origin (the API
   also serves this page) unless overridden with ?api=. */
const API = new URLSearchParams(location.search).get("api") || "";
async function fetchBoards(close) {
  const user = myUser(), name = myName(), group = myGroup(), day = DAY.no;
  const post = (path, body) => fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  await post("/par/group/join", { group, user_id: user, name });
  // the submit carries the full move sequence — the transcript is the data the engine
  // learns from, and the server checks the close against it (anti-forgery).
  const board = await post("/par/submit", { day, user_id: user, close,
    your_offers: g.asks.filter((x) => x != null), house_offers: g.houseOffers }).then((r) => { if (!r.ok) throw 0; return r.json(); });
  const grp = await fetch(API + "/par/group?group=" + encodeURIComponent(group) + "&day=" + day).then((r) => r.json());
  const friends = grp.board.map((r) => ({ name: r.name, pct: r.pct, rank: r.rank, you: r.user === user }));
  return { board, friends };
}

/* funnel instrumentation: fire-and-forget events so we can see where the loop leaks
   (play -> share -> cta_view -> cta_click -> waitlist). Silent offline. */
function track(name, meta) {
  try { fetch(API + "/par/event", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: myUser(), name: name, meta: meta || {} }) }); } catch (e) { }
}
async function joinWaitlist() {                          // the CTA's real destination
  // the email IS the asset — without it "notify me" notifies no one. Nudge once if empty.
  const em = ($("ag-email") && $("ag-email").value || "").trim().slice(0, 128);
  const b = $("ag-join");
  if (!em && !b.dataset.nudged) {
    b.dataset.nudged = "1"; b.textContent = "add an email so we can reach you";
    $("ag-email") && $("ag-email").focus(); return;
  }
  if (em) localStorage.setItem("par-email", em);
  b.textContent = "on the list ✓"; b.disabled = true;
  try { await fetch(API + "/par/waitlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: myUser(), scenario: DAY.title, contact: em || null }) }); } catch (e) { }
}

/* ---- forensics: the mistake, named ----------------------------------------- */
/* One sentence that shows the exact moment you blinked. Live: from /par/submit. This is
   the offline mirror of gametheory/negotiation/par_game.forensics(). */
function localForensics(close, Y, H) {
  const p = DAY.par, sgn = isSell() ? 1 : -1;
  if (close == null) {
    if (!H.length) return null;
    const room = Math.abs(p - H[H.length - 1]);
    return room > 0.01 ? { kind: "walk", cost: room } : null;
  }
  const left = isSell() ? p - close : close - p;
  if (left <= 0.01) return null;
  if (H.length >= 2 && Math.abs(close - H[H.length - 1]) < 0.01 && Y.length < DAY.rounds) {
    const step = Math.abs(H[H.length - 1] - H[H.length - 2]);
    if (step > 0.01) return { kind: "early_accept", house_gave: step, cost: left };
  }
  let best = null;
  for (let i = 1; i < Math.min(Y.length, H.length); i++) {
    const you = sgn * (Y[i - 1] - Y[i]), house = Math.max(sgn * (H[i] - H[i - 1]), 0);
    const excess = you - house;
    if (you > 0.01 && excess > 0.01 && (!best || excess > best.excess))
      best = { excess, move: i + 1, you_gave: you, house_gave: house };
  }
  if (best) return { kind: "overconcede", move: best.move, you_gave: best.you_gave,
    house_gave: best.house_gave, cost: Math.min(best.excess, left) };
  return { kind: "pace", cost: left };
}
function renderForensic(f) {
  const B = (v) => '<span style="color:var(--violet-bright)">' + fmt(v) + '</span>';
  if (f.kind === "overconcede") return 'move ' + f.move + ' — you gave ' + B(f.you_gave) +
    ', the House gave ' + (f.house_gave > 0.01 ? fmt(f.house_gave) : 'nothing') + '. that blink cost ~' + B(f.cost) + '.';
  if (f.kind === "early_accept") return 'you took the House’s number while it was still moving — its last step was ' +
    fmt(f.house_gave) + '. there was ' + B(f.cost) + ' more in the room.';
  if (f.kind === "walk") return 'you walked while the House still had ' + B(f.cost) + ' in the room.';
  return 'no single blink — just soft pace. ' + B(f.cost) + ' short of par.';
}

function boardHTML(b, friends) {
  const max = Math.max(...b.distribution.map((d) => d.count));
  const dist = b.distribution.map((d) =>
    '<div class="drow' + (d.you ? ' me' : '') + '"><span class="dl">' + d.label + '</span><span class="dbar' + (d.you ? ' me' : '') +
    '" style="width:' + Math.max(Math.round(d.count / max * 100), 4) + '%">' + (d.you ? d.count : '') + '</span></div>').join("");
  const fl = friends.map((r) =>
    '<div class="frow' + (r.you ? ' me' : '') + '"><span class="fr-rank">' + r.rank + '</span><span class="fr-name">' + r.name +
    '</span><span class="fr-pct">' + (r.pct == null ? "—" : r.pct + "%") + '</span></div>').join("");
  // the moment of truth stays clean: streak + percentile visible; the histogram and the
  // friends board are trophy-case material — one tap away, not competing with the number.
  return '<div class="board"><div class="brow"><span>streak <b>' + b.streak + '</b> ' + (b.streak === 1 ? "day" : "days") +
    '</span><span>you beat <b>' + b.percentile + '%</b> today</span></div>' +
    '<button class="bexp" id="bexp">where everyone landed ↓</button>' +
    '<div id="board-detail" style="display:none">' +
    '<div class="tabs"><button class="tab on" data-v="everyone">everyone</button><button class="tab" data-v="friends">friends</button></div>' +
    '<div id="bv-everyone" class="bview"><div class="dist">' + dist + '</div></div>' +
    '<div id="bv-friends" class="bview" style="display:none">' +
    '<input id="fname" class="fname" maxlength="16" placeholder="your name — appears on the board" value="' +
    (localStorage.getItem("par-name") || "") + '"><div class="flist">' + fl + '</div></div></div></div>';
}
function wireTabs() {
  const x = $("bexp");
  if (x) x.onclick = () => {
    const d = $("board-detail"), open = d.style.display === "none";
    d.style.display = open ? "block" : "none";
    x.textContent = open ? "where everyone landed ↑" : "where everyone landed ↓";
  };
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
    document.querySelectorAll(".tab").forEach((y) => y.classList.toggle("on", y === t));
    $("bv-everyone").style.display = t.dataset.v === "everyone" ? "block" : "none";
    $("bv-friends").style.display = t.dataset.v === "friends" ? "block" : "none";
  });
  const f = $("fname");                                   // inline name (persists; applies next play)
  if (f) f.onchange = () => setMyName(f.value);
}

async function finish() {
  g.over = true; $("play-house").style.display = "none"; show("s-reveal");
  $("rev-body").innerHTML = '<div style="padding:14px 0;font-size:13px;color:var(--muted)">scoring against par…</div>';
  const won = g.deal != null;
  // the server scores first: par stays hidden until this moment, the transcript lands in
  // the plays table, and the board comes back in the same response. Offline: stand-in par.
  let real = null;
  try { real = await fetchBoards(won ? g.deal : null); } catch (e) { }
  if (real && real.board.par != null) DAY.par = real.board.par;
  if (DAY.par == null) {                                 // live day, score didn't land — retry
    $("rev-body").innerHTML = '<div style="padding:14px 0;font-size:13px;color:var(--muted)">can’t reach the House to score this. <button class="pri" id="rev-retry" style="margin-left:10px">retry</button></div>';
    $("rev-retry").onclick = finish;
    return;
  }
  drawReveal();
  const p = won ? (real ? Math.round(real.board.pct_of_par) : pctOf(g.deal)) : 0;
  // the mistake, named — from the server when live, mirrored locally offline
  g.forensic = real ? real.board.forensic
    : localForensics(won ? g.deal : null, g.asks.filter((x) => x != null), g.houseOffers);
  const board = '<div id="board-slot">' + boardHTML(real ? real.board : localBoard(p), real ? real.friends : localFriends(p)) + '</div>';
  const btns = '<div style="display:flex;gap:10px;margin-top:16px"><button class="pri" id="rev-share">share result</button><button id="rev-again">play tomorrow</button></div>';
  // the engine's line stays INTERNAL — one opponent, one yardstick on screen; it only
  // decides the rare "beat the engine" win tier.
  const ag = won ? (real ? real.board.agent_close : Math.round(DAY.par * (isSell() ? 0.975 : 1.025) / DAY.step) * DAY.step) : 0;
  const ap = won ? (real ? Math.round(real.board.agent_pct) : pctOf(ag)) : 0;
  const isWin = won && (p >= 100 || p >= ap);
  let head;
  if (won) {
    const prevBest = +(localStorage.getItem("par-best") || 0);
    const isBest = p > prevBest; if (isBest) localStorage.setItem("par-best", p);
    const pb = isBest ? '<div style="margin-top:9px;font-size:13px;color:var(--violet-bright)">★ new personal best</div>' : '';
    const bigWord = p >= 100 ? "at par" : (p + "%");
    let line;
    if (p >= 100)                                        // matched a perfect negotiator
      line = 'you closed at <b style="color:var(--violet-bright)">par</b>. you matched a perfect negotiator — almost nobody does.';
    else if (isWin)                                      // past the engine's own line — the rare win
      line = 'you <b style="color:var(--violet-bright)">beat the engine’s line</b> — a top-tier close.';
    else                                                 // the mistake, named — not a second score
      line = g.forensic ? renderForensic(g.forensic)
        : 'par was ' + fmt(DAY.par) + ' — ' + fmt(DAY.par && Math.abs(DAY.par - g.deal)) + ' above your close.';
    head = '<div style="display:flex;align-items:baseline;gap:12px"><span style="font-size:34px;color:var(--violet);line-height:1">' + bigWord + '</span><span style="font-size:13px;color:var(--muted)">' + (p >= 100 ? "" : "of par · ") + 'closed ' + fmt(g.deal) + '</span></div><div style="margin-top:11px;font-size:14px;color:var(--ink-dim)">' + line + '</div>' + pb;
  } else {
    const line = g.forensic ? renderForensic(g.forensic)
      : 'the House had ' + fmt(DAY.par) + ' in the room. you left all of it.';
    head = '<div style="font-size:30px;color:#B05A55;line-height:1">no deal · 0%</div><div style="margin-top:9px;font-size:14px;color:var(--ink-dim)">' + line + '</div>';
  }
  // the coach CTA answers the forensic — and only once the loss is HEAVY: not on the first
  // game, not on a win day, and only after the cumulative gap crosses a threshold.
  const plays = +(localStorage.getItem("par-plays") || 0) + 1;
  localStorage.setItem("par-plays", plays);
  const cumGap = +(localStorage.getItem("par-gap") || 0) + (won ? Math.max(0, 100 - p) : 100);
  localStorage.setItem("par-gap", cumGap);
  const hook = (g.forensic && g.forensic.kind !== "pace")
    ? "the coach catches that move before you send it — in your real negotiations."
    : DAY.cta.hook;
  const showCta = plays >= 2 && cumGap >= 12 && !isWin;
  const cta = !showCta ? "" : '<div class="cta"><div class="hook">' + hook + '</div><button class="cta-go" id="rev-cta">' + DAY.cta.verb + ' →</button></div>';
  $("rev-body").innerHTML = '<div style="border-top:0.5px solid var(--line);margin-top:8px;padding-top:14px">' + head + board + cta + btns + '</div>';
  if ($("rev-cta")) { $("rev-cta").onclick = openAgent; track("cta_view"); }
  wireTabs();
  $("rev-again").onclick = () => { resetPlay(); show("s-landing"); };
  $("rev-share").onclick = shareResult;
}
/* The House, live. Each round POSTs /par/house_move and the SNHP equilibrium decides
   (accept | counter | walk); offline it falls back to the same shape from the stand-in
   arrays. `i` = how many offers the House has already made (0 = its opening). */
function standInHouse(yourOffers, houseOffers) {
  const i = houseOffers.length, lastAsk = yourOffers[yourOffers.length - 1];
  if (lastAsk != null && i >= 1) {
    const w = DAY.willing[i - 1], hit = isSell() ? lastAsk <= w : lastAsk >= w;
    if (hit) return { action: "accept", offer: lastAsk, message: "Deal." };
  }
  if (i >= DAY.rounds) return { action: "walk", offer: null, message: "We're done here." };
  return { action: "counter", offer: DAY.offers[i], message: DAY.msg[i] };
}
async function houseMove(yourOffers, houseOffers, roundsLeft) {
  try {
    const r = await fetch(API + "/par/house_move", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: DAY.no, your_offers: yourOffers, house_offers: houseOffers, rounds_left: roundsLeft }),
    });
    if (!r.ok) throw 0;
    return await r.json();                              // {action, offer, message}
  } catch (e) { return standInHouse(yourOffers, houseOffers); }
}

async function counter() {
  if (g.busy) return; g.busy = true;
  const C = +$("play-ask").value; g.asks[g.t] = C;
  const rec = await houseMove(g.asks, g.houseOffers, Math.max(1, DAY.rounds - g.t));
  g.busy = false;
  if (rec.action === "accept") { g.deal = C; finish(); return; }   // House met your ask
  if (rec.action === "walk") { g.walked = true; finish(); return; }
  g.houseOffers.push(rec.offer); g.curOffer = rec.offer; g.curMsg = rec.message; g.t++;
  if (g.t >= DAY.rounds) { g.walked = true; finish(); return; }     // deadline: no rounds left
  syncHouse(); drawPlay(+$("play-ask").value);
}
function accept() { if (g.busy || g.curOffer == null) return; g.deal = g.curOffer; finish(); }  // take the standing offer
function walk() { if (g.busy) return; g.walked = true; finish(); }
function resetPlay() {
  g.t = 0; g.asks = []; g.houseOffers = []; g.curOffer = null; g.curMsg = ""; g.deal = null; g.walked = false; g.over = false; g.busy = false;
  $("play-house").style.display = "flex";
  const el = $("play-ask"), lo = Math.min(DAY.target, DAY.floor), hi = Math.max(DAY.target, DAY.floor);
  el.min = lo; el.max = hi; el.step = DAY.step; el.value = DAY.target;
  $("play-askv").textContent = fmt(DAY.target); $("play-cv-amt").textContent = fmt(DAY.target);
}
async function startPlay() {
  resetPlay(); g.busy = true;                            // lock counter/accept/walk until the House opens
  $("play-sub").textContent = "no. " + DAY.no + " · " + DAY.title;
  $("play-house").innerHTML = '<span class="l">the house</span><span class="q">opening…</span>';
  show("s-play"); track("play");
  const open = await houseMove([], [], DAY.rounds);      // the House opens
  g.houseOffers.push(open.offer); g.curOffer = open.offer; g.curMsg = open.message;
  g.busy = false;                                        // unlock — controls now act on a real offer
  syncHouse(); drawPlay(DAY.target);
}

/* the iconic, screenshot-ready result card. The HOLE is the hero: the violet void =
   what you left on the table (the regret), the deal demoted to a thin muted line. */
function shareCardSVG() {
  const won = g.deal != null;
  const pct = won ? pctOf(g.deal) : 0;
  const atPar = won && leftOf(g.deal) <= 0;             // matched par — flex, not "$0k left"
  const hero = !won ? "no deal" : atPar ? "at par" : fmt(leftOf(g.deal));
  const hs = !won ? 52 : atPar ? 62 : Math.min(92, Math.round(230 / (hero.length * 0.62)));  // scale so a wide "$19.2k" never clips
  const sub = !won ? "walked — all of it" : atPar ? "you matched perfect" : "left on the table";
  const closed = won ? ("you closed " + fmt(g.deal)) : "you walked away";
  return '<text x="44" y="60" font-size="24" letter-spacing="5" fill="#E8E8E3" ' + FN + '>PAR</text>'
    + '<text x="496" y="60" font-size="13" fill="#7C7C77" text-anchor="end" ' + FN + '>no. ' + DAY.no + ' · ' + DAY.title + '</text>'
    + '<line x1="44" y1="300" x2="276" y2="300" stroke="#4A4B52" stroke-width="2"/>'
    + '<circle cx="276" cy="300" r="5" fill="#7C7C77"/>'
    + '<text x="268" y="288" font-size="13" fill="#7C7C77" text-anchor="end" ' + FN + '>' + closed + '</text>'
    + '<text x="44" y="360" font-size="17" fill="#7C7C77" ' + FN + '>' + pct + '% of par</text>'
    + '<path fill="#9D86F2" d="M340,150 L552,150 L552,432 L270,432 Z"/>'
    + '<text x="422" y="316" font-size="' + hs + '" fill="#16102C" text-anchor="middle" ' + FN + '>' + hero + '</text>'
    + '<text x="422" y="360" font-size="17" letter-spacing="1" fill="#2A2150" text-anchor="middle" ' + FN + '>' + sub + '</text>'
    + '<text x="44" y="510" font-size="14" fill="#9385D6" ' + FN + '>' + (won ? "can you beat this? →" : "think you’re better? →") + '</text>'
    + '<text x="496" y="510" font-size="13" fill="#7C7C77" text-anchor="end" ' + FN + '>par.game</text>';
}
function shareResult() {
  const won = g.deal != null, p = won ? pctOf(g.deal) : 0;
  const ap = pctOf(Math.round(DAY.par * (isSell() ? 0.975 : 1.025) / DAY.step) * DAY.step);
  // a CHALLENGE, not a report: the link seeds the recipient into MY group (?g=) and carries
  // my "left on the table" (?c=). The brag flips to a flex when you win.
  const brag = !won ? "i walked it. beat me:"
    : p >= 100 ? "i hit PAR — matched a perfect negotiator. beat me:"
    : p >= ap ? "i beat the engine’s line (" + p + "% of par). beat me:"
    : "i left " + fmt(leftOf(g.deal)) + " on the table (" + p + "% of par). beat me:";
  const link = "par.game/?g=" + myGroup() + (won ? "&c=" + Math.round(leftOf(g.deal)) : "");
  const txt = "PAR no." + DAY.no + " — " + brag + "\n" + link;
  if (navigator.clipboard) navigator.clipboard.writeText(txt);
  $("share-cv").innerHTML = shareCardSVG();
  $("share-ov").classList.add("on");
  track("share");
}

/* the conversion bridge: the game proved the agent beats you; this turns that into intent.
   The fee model is the point — because PAR measures "$ on the table", the agent's value is
   billable: a cut of the surplus it wins above your walk-away. Aligned; you never pay to lose. */
function openAgent() {
  track("cta_click");
  const won = g.deal != null;
  $("ag-lede").innerHTML = (won && g.forensic && g.forensic.kind !== "pace")
    ? ('that one blink cost <b>' + fmt(g.forensic.cost) + '</b> today. in a real negotiation — a raise, rent, an offer — the coach catches it before you send it.')
    : won
    ? ('you just left <b>' + fmt(leftOf(g.deal)) + '</b> on the table against a perfect negotiator. it can coach your real ones — a raise, rent, an offer — so you don’t.')
    : ('you walked from the whole room. a perfect negotiator would have closed it — and it can coach your real ones so you don’t.');
  $("ag-fee").innerHTML = '<b>you set the floor; the fee is capped.</b> it takes a cut only of what it wins above your number — never pay to lose, never a surprise bill.';
  if ($("ag-email")) $("ag-email").value = localStorage.getItem("par-email") || "";
  $("agent-ov").classList.add("on");
}

/* ---- onboarding flow ------------------------------------------------------ */
function startOnboard() {
  show("s-onboard"); onbBeat(0); $("onb-drag").value = 0;
  $("onb-drag").oninput = function () { const p = +this.value / 100; onbBeat(p);
    if (p >= 0.999) { $("onb-hint").textContent = "that’s the whole game. now play for real →"; $("onb-hint").style.cursor = "pointer"; $("onb-hint").onclick = startPlay; }
    else { $("onb-hint").textContent = "drag to close the gap →"; } };
}

/* ---- boot ----------------------------------------------------------------- */
/* THE REAL ROTATION: the day comes from GET /par/today — puzzle number, side, numbers, and
   the countdown. Without this the "daily" game never rotates and streaks can never advance.
   The hardcoded SCENARIOS become the offline fallback (par stays known only offline). */
function applyToday(t) {
  const base = SCENARIOS[t.side] || SCENARIOS.sell;      // visual template for that side
  if (DAY !== base) Object.assign(DAY, base);            // msgs/willing stay: offline-only
  const lo = Math.min(t.walk_away, t.target), hi = Math.max(t.walk_away, t.target), r = hi - lo;
  Object.assign(DAY, {
    no: t.no, side: t.side, title: t.title, floor: t.walk_away, target: t.target,
    rounds: t.rounds, par: null,                         // par is the server's secret until the grade
    unit: hi >= 1000 ? "" : "k", axisMin: lo, axisMax: hi, gapK: 150 / r,
    step: r <= 60 ? 1 : r <= 600 ? 10 : r <= 6000 ? 100 : 1000,
  });
  // countdown to the next deal, ticking (was a hardcoded "5h left")
  const end = Date.now() + t.seconds_left * 1000;
  const tick = () => {
    const s = Math.max(0, Math.round((end - Date.now()) / 1000));
    const left = s >= 3600 ? Math.round(s / 3600) + "h left" : Math.max(1, Math.round(s / 60)) + "m left";
    $("land-daily").textContent = "no. " + DAY.no + " · " + DAY.title + " · " + left;
  };
  tick(); setInterval(tick, 30000);
}
landCanyon();
const _params = new URLSearchParams(location.search);
// arriving on a friend's share link joins their group. prod: POST /par/group/join
const _gArg = _params.get("g"); if (_gArg) localStorage.setItem("par-group", _gArg);
$("land-daily").textContent = "no. " + DAY.no + " · " + DAY.title;
const TODAY_READY = fetch(API + "/par/today").then((r) => { if (!r.ok) throw 0; return r.json(); })
  .then((t) => { applyToday(t); return true; })
  .catch(() => false);                                   // offline → the stand-in day
// live social proof (GET /par/stats) — but never show an empty room: below 20 players the
// counter is anti-proof, so say nothing. The seeded stand-in only survives offline.
$("land-soc").textContent = BOARD_BASE[5].n + " of " + BOARD_TOTAL + " hit par today";
fetch(API + "/par/stats").then((r) => r.json()).then((s) => {
  if (s && s.played != null)
    $("land-soc").textContent = s.played >= 20 ? (s.par_hits + " of " + s.played + " hit par today") : "";
}).catch(() => { });
// arrived via a friend's challenge link (?c=<left>): reframe the hook as a gauntlet.
const _c = _params.get("c");
if (_c) { const h = document.querySelector(".land .hook"); if (h) h.textContent = "a friend left " + fmt(+_c) + " on the table today. your move →"; }
$("land-play").onclick = async () => {
  await TODAY_READY;                                     // play the REAL day (or the fallback)
  localStorage.getItem("par-played") ? startPlay() : (localStorage.setItem("par-played", "1"), startOnboard());
};
$("play-ask").oninput = function () { const v = +this.value; $("play-askv").textContent = fmt(v); $("play-cv-amt").textContent = fmt(v); drawPlay(v); };
$("play-counter").onclick = counter; $("play-accept").onclick = accept; $("play-walk").onclick = walk;
$("share-close").onclick = () => $("share-ov").classList.remove("on");
$("agent-close").onclick = () => $("agent-ov").classList.remove("on");
$("ag-join").onclick = joinWaitlist;                     // POSTs /par/waitlist (+ funnel event)

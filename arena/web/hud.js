/* DOM HUD: era banner, YOUR HOUSE fortunes, dynasty leaderboard, species
   census, the STRATEGIES panel (who's winning, by tactic — evolution made
   watchable), lineage ticker, and the back-a-house onboarding. Clips crop to
   canvas, so nothing here is story-load-bearing — it's the live-page chrome. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  const W = A.world, SP = A.sprites;
  const $ = (id) => document.getElementById(id);
  const ERA_GLYPH = { symmetric: "⚖", buyers: "▼", sellers: "▲", contract: "❖" };

  // The eight founding houses — each an honest corner of the strategy space.
  const HOUSES = [
    { name: "Monk", tactic: "boulware", aggr: 0.4, walk: 0.1, knob: 1.0, line: "concedes nothing until the deadline" },
    { name: "Berserker", tactic: "anchorer", aggr: 0.95, walk: 0.8, knob: 0.9, line: "opens outrageous, bluffs the floor" },
    { name: "Merchant", tactic: "conceder", aggr: 0.5, walk: 0.25, knob: 0.6, line: "closes fast, wins on volume" },
    { name: "Mirror", tactic: "mirror", aggr: 0.6, walk: 0.4, knob: 0.6, line: "reflects whatever you concede" },
    { name: "Gambler", tactic: "closer", aggr: 0.8, walk: 0.9, knob: 0.8, line: "loose floor, strikes at the bell" },
    { name: "Diplomat", tactic: "conceder", aggr: 0.45, walk: 0.15, knob: 0.5, staked: true, line: "staked & truthful — the network bet" },
    { name: "Vulture", tactic: "closer", aggr: 0.7, walk: 0.7, knob: 0.85, line: "preys on the desperate" },
    { name: "Hermit", tactic: "patient", aggr: 0.5, walk: 0.5, knob: 1.0, line: "deals rarely, hoards, outlasts" },
  ];
  function houseGenome(h) {
    return { pareto_knob: h.knob, open_aggression: h.aggr, walk_margin: h.walk,
      patience: 0.5, bundle_focus: [0.25, 0.25, 0.25, 0.25], mate_w: [0.5, 0.2, 0.1, 0.2],
      truncation: 0.2, staked: !!h.staked, tactic_family: h.tactic };
  }
  const TACTIC_LINE = {
    anchorer: "anchors huge", boulware: "stone wall", conceder: "deal-maker",
    mirror: "tit-for-tat", patient: "outlasts", closer: "deadline sniper",
  };

  function _thumb(g, scale) {
    const s = SP.build(g), cv = document.createElement("canvas");
    cv.width = s.w; cv.height = s.h + 2;
    const c = cv.getContext("2d");
    c.imageSmoothingEnabled = false; c.drawImage(s.f[0], 0, 0);
    return cv;
  }

  function update() {
    const w = W;
    $("era-name").textContent = w.eraLabel || "—";
    $("era-glyph").textContent = ERA_GLYPH[w.era] || "◆";
    $("gen-counter").textContent = "gen " + w.gen;
    const poll = $("era-poll");
    if (poll) poll.textContent = w.pollinator ? w.pollinator.glyph : "";

    _myHouse();

    // dynasty leaderboard — HOUSES ranked by combined wealth (what "dynasty"
    // means), each with its leading soul; matches the banners in the hall
    const lb = $("leaderboard");
    let html = '<div class="lb-title">dynasties · house wealth</div>';
    for (const h of (w.houseWealth || []).slice(0, 6)) {
      const star = w.myHouse && h.house === w.myHouse ? "★" : "";
      html += `<div class="lb-row"><span class="lb-swatch" style="background:${h.ramp[3]}"></span>`
        + `<span class="lb-name">${star}${_esc(h.house)}`
        + (h.lead ? ` <span style="opacity:.55">· ${_esc(shortName(h.lead))}</span>` : "")
        + `</span><span class="lb-energy">${Math.round(h.wealth)}</span></div>`;
    }
    lb.innerHTML = html;

    // census — bars wear the ACTUAL color of each species' exemplar sprite, so
    // the bars match the crowd you're looking at (not an unrelated palette)
    const cs = $("census");
    let ch = '<div class="cs-title">census · ' + (w.census.pop || w.agents.size) + " souls</div>";
    const tot = (w.species || []).reduce((s, sp) => s + sp.count, 0) || 1;
    for (const sp of (w.species || []).slice(0, 6)) {
      const ex = w.agents.get(sp.exemplar);
      const ramp = ex ? SP.rampFor(ex.g) : SP.RAMPS[sp.id % SP.RAMPS.length];
      ch += `<div class="cs-bar" style="width:${(100 * sp.count / tot).toFixed(0)}%;background:${ramp[3]}"></div>`;
    }
    const c = w.census;
    ch += `<div class="cs-stat"><span>deal rate</span><b>${c.deal_rate != null ? Math.round(100 * c.deal_rate) + "%" : "—"}</b></div>`;
    ch += `<div class="cs-stat"><span>staked</span><b>${c.staked_frac != null ? Math.round(100 * c.staked_frac) + "%" : "—"}</b></div>`;
    cs.innerHTML = ch;

    _strategies();
  }

  function _myHouse() {
    const box = $("myhouse");
    // The forge loop's scoreboard: YOUR champion (the strategy you sent in),
    // its energy, deals, and bloodline — then the reforge prompt when it falls.
    if (W.myChampion != null) {
      box.classList.remove("hidden");
      const c = W.agents.get(W.myChampion);
      const line = [...W.myLine].filter(id => W.agents.has(id)).length;
      if (c) {
        const ramp = SP.rampFor(c.g);
        const pct = Math.min(100, Math.round(100 * c.energy / 300));
        box.innerHTML =
          `<div class="mh-title">your champion</div>` +
          `<div class="mh-name" style="color:${ramp[3]}">★ ${_esc(shortName(c.name))} <span style="opacity:.6;font-size:10px">${_esc(c.g.tactic_family)}</span></div>` +
          `<div class="mh-bar"><i style="width:${pct}%"></i></div>` +
          `<div class="mh-row"><span>energy</span><b>${Math.round(c.energy)}</b></div>` +
          `<div class="mh-row"><span>deals</span><b>${c.deals || 0}</b></div>` +
          `<div class="mh-row"><span>bloodline</span><b>${line}</b></div>`;
      } else if (W.championFallen) {
        const f = W.championFallen;
        box.innerHTML =
          `<div class="mh-title">your champion</div>` +
          `<div class="mh-name" style="color:#8a5a5e">has fallen</div>` +
          `<div class="mh-row"><span>${f.cause === "starvation" ? "went broke" : "grew old"}</span>` +
          `<b>${f.heirs ? f.heirs + " heirs live" : "line ended"}</b></div>` +
          `<button class="reforge" id="reforge-btn">⚒ reforge a strategy</button>`;
        const rb = $("reforge-btn");
        if (rb) rb.onclick = () => $("onboard").classList.remove("hidden");
      }
      return;
    }
    if (!W.myHouse) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    const members = [...W.agents.values()].filter(a => a.house === W.myHouse);
    const totals = new Map();
    for (const a of W.agents.values()) totals.set(a.house, (totals.get(a.house) || 0) + a.energy);
    const ranked = [...totals.entries()].sort((p, q) => q[1] - p[1]);
    const rank = ranked.findIndex(([h]) => h === W.myHouse) + 1;
    const ramp = members[0] ? SP.rampFor(members[0].g) : SP.rampForHouse(W.myHouse);
    box.innerHTML =
      `<div class="mh-title">your house</div>` +
      `<div class="mh-name" style="color:${ramp[3]}">★ ${_esc(W.myHouse)}</div>` +
      (members.length
        ? `<div class="mh-row"><span>souls</span><b>${members.length}</b></div>` +
          `<div class="mh-row"><span>rank</span><b>${rank > 0 ? "#" + rank : "—"} of ${ranked.length}</b></div>`
        : `<div class="mh-row"><span style="color:#8a5a5e">extinct — a candle burns for them</span></div>`);
  }

  // WHO'S WINNING, by strategy — ranked by THIS generation's income per capita
  // (wealth is cumulative luck; income/gen is the real selection signal).
  function _strategies() {
    const box = $("science");
    const tac = W.census.tactics;
    let html = '<div class="sci-title">strategies · income this gen</div>';
    if (tac) {
      const inc = (v) => (v.income != null ? v.income : 0);
      const rows = Object.entries(tac).sort((p, q) => inc(q[1]) - inc(p[1]));
      const prev = W.prevTactics || {};
      for (const [name, v] of rows) {
        const ti = SP.TACTICS.indexOf(name);
        const ramp = SP.RAMPS[(ti >= 0 ? ti : 0) % SP.RAMPS.length];
        const was = prev[name] && prev[name].income != null ? prev[name].income : inc(v);
        const trend = inc(v) > was + 0.5 ? '<span class="strat-up">▲</span>'
          : inc(v) < was - 0.5 ? '<span class="strat-dn">▼</span>' : "·";
        html += `<div class="strat-row"><span class="strat-chip" style="background:${ramp[3]}"></span>`
          + `<span class="strat-name">${name} <span style="opacity:.6">· ${v.n}</span></span>`
          + `<span class="strat-e">${inc(v).toFixed(1)}</span>${trend}</div>`;
      }
    }
    html += '<canvas id="sci-chart" width="200" height="34"></canvas>'
      + '<div style="font-size:9px;color:#7c7790;margin-top:2px">population boldness drift · every move computed by SNHP</div>';
    box.innerHTML = html;
    const cv = $("sci-chart");
    if (cv && W.knobHistory.length) {
      const c2 = cv.getContext("2d");
      c2.strokeStyle = "#a78bfa"; c2.lineWidth = 1.5; c2.beginPath();
      W.knobHistory.forEach((p, i) => {
        const x = i / Math.max(1, W.knobHistory.length - 1) * 200, y = 34 - p.m * 30 - 2;
        i ? c2.lineTo(x, y) : c2.moveTo(x, y);
      });
      c2.stroke();
    }
  }

  function pushTicker() {
    const inner = $("ticker-inner");
    inner.innerHTML = (W.ticker.slice(-14).join("  ·  ")) || "the hall stirs …";
  }

  function shortName(n) { return (n || "").split(" of ")[0]; }
  function _esc(s) { return String(s || "").replace(/[<>&]/g, (m) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[m])); }

  let _forgePick = null;
  function _buildHouseGrid() {
    const grid = $("house-grid");
    grid.innerHTML = "";
    for (const h of HOUSES) {
      const card = document.createElement("div");
      card.className = "house-card";
      const ramp = SP.rampFor(houseGenome(h));
      card.appendChild(_thumb(houseGenome(h)));
      const nm = document.createElement("div"); nm.className = "hc-name";
      nm.textContent = h.name; nm.style.color = ramp[3]; card.appendChild(nm);
      const ln = document.createElement("div"); ln.className = "hc-line";
      ln.textContent = h.line; card.appendChild(ln);
      card.onclick = () => {
        // selecting a house = choosing your tactic + default dials; then you
        // tune the dials and send your champion through the gate
        _forgePick = h;
        [...grid.children].forEach(c => c.style.borderColor = "");
        card.style.borderColor = ramp[3];
        $("dial-bold").value = Math.round(h.knob * 100);
        $("dial-bluff").value = Math.round(h.walk * 100);
        $("dial-pat").value = Math.round((h.name === "Hermit" ? 0.9 : 0.5) * 100);
        const send = $("forge-send");
        send.disabled = false;
        send.textContent = `⚒ send a ${h.tactic} through the gate`;
        W.myHouse = h.name;
        try { localStorage.setItem("arena-house", h.name); } catch (e) { }
      };
      grid.appendChild(card);
    }
  }

  async function _forgeSend() {
    if (!_forgePick) return;
    const spec = {
      token: W.myToken, house: _forgePick.name, tactic: _forgePick.tactic,
      boldness: (+$("dial-bold").value) / 100,
      bluff: (+$("dial-bluff").value) / 100,
      patience: (+$("dial-pat").value) / 100,
      staked: !!_forgePick.staked,
    };
    const send = $("forge-send");
    send.disabled = true; send.textContent = "the gate opens…";
    try {
      if (A.net.state === "demo") {
        A.demo.injectChampion(spec);
      } else {
        await A.net.post("/arena/champion", spec);
      }
      $("onboard").classList.add("hidden");
      try { localStorage.setItem("arena-seen", "1"); } catch (e) { }
    } catch (e) {
      send.textContent = "the gate is barred — " + (e.message || "try again");
    } finally {
      setTimeout(() => { send.disabled = false; if (_forgePick) send.textContent = `⚒ send a ${_forgePick.tactic} through the gate`; }, 1200);
    }
  }

  function initControls() {
    const help = $("help-btn"), onb = $("onboard"), dismiss = $("onboard-dismiss");
    _buildHouseGrid();
    $("forge-send").onclick = _forgeSend;
    const seen = (function () { try { return localStorage.getItem("arena-seen"); } catch (e) { return 1; } })();
    if (!seen) onb.classList.remove("hidden");
    dismiss.onclick = () => { onb.classList.add("hidden"); try { localStorage.setItem("arena-seen", "1"); } catch (e) { } };
    help.onclick = () => onb.classList.remove("hidden");
    const sb = $("sound-btn");
    sb.onclick = () => { const on = A.sound.toggle(); sb.classList.toggle("on", on); };
    W.onTicker = () => pushTicker();
  }

  A.hud = { update, pushTicker, initControls, HOUSES };
})();

/* Client-side world state + event ingestion. The sim is authoritative; this
   mirrors it and turns events into things the choreographer animates. No drawing
   here. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});
  const S = A.stage;

  function rnd(a, b) { return a + Math.random() * (b - a); }

  const world = {
    agents: new Map(), duels: new Map(), courts: new Map(),
    era: "symmetric", eraLabel: "Symmetric Market", gen: 0, assortative: false,
    pollinator: null, latestBloom: null, onBloom: null,
    leaderboard: [], species: [], census: {}, prevTactics: null, ticker: [],
    dealHeat: [], // {x,y,life}
    memorials: [],
    myHouse: (function () { try { return localStorage.getItem("arena-house") || null; } catch (e) { return null; } })(),
    // the forge loop: your token marks your champion; we track its line
    myToken: (function () {
      try {
        let t = localStorage.getItem("arena-token");
        if (!t) { t = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("arena-token", t); }
        return t;
      } catch (e) { return "anon"; }
    })(),
    myChampion: null, myLine: new Set(), championFallen: null, onChampion: null,
    onHighlight: null, // set by main -> director/cut-in
    knobHistory: [],   // {mean, opt} for science chart

    reset(snap) {
      this.agents.clear(); this.duels.clear(); this.courts.clear();
      this.era = snap.era || "symmetric";
      this.eraLabel = snap.era_label || "";
      this.gen = snap.gen || 0;
      this.assortative = !!snap.assortative;
      this.pollinator = snap.pollinator || this.pollinator;
      for (const a of (snap.agents || [])) this._add(a);
    },

    _add(a, x, y) {
      // a malformed event without a genome would crash the per-frame draw loop
      // (sprites/flora deref genome fields) and freeze the canvas — drop it.
      if (!a || a.genome == null || a.genome.pareto_knob == null) return null;
      const zone = S.ZONES[(a.id | 0) % S.ZONES.length];
      const ag = {
        id: a.id, g: a.genome, name: a.name, house: a.house, staked: a.staked,
        energy: a.energy != null ? a.energy : 100, species: a.species,
        x: x != null ? x : rnd(30, S.WORLD_W - 30),
        y: y != null ? y : rnd(S.FLOOR_Y + 12, S.WORLD_H - 14),
        hx: 0, hy: 0, hx0: 0, hy0: 0, facing: Math.random() < 0.5 ? 1 : -1,
        phase: Math.random() * 7, mode: "idle", tx: 0, ty: 0,
        dying: 0, born: 0.6, critical: false,
      };
      ag.hx = ag.x; ag.hy = ag.y; ag.hx0 = ag.x; ag.hy0 = ag.y;
      this.agents.set(a.id, ag);
      return ag;
    },

    ingest(ev) {
      const t = ev.type;
      switch (t) {
        case "agent.spawn": this._add({ id: ev.id, genome: ev.genome, name: ev.name, house: ev.house, staked: ev.genome && ev.genome.staked, species: ev.species }); break;
        case "immigration": {
          // newcomers ENTER through the gate — arrivals are felt, not popped
          const a = this._add({ id: ev.id, genome: ev.genome, name: ev.name, house: ev.house, staked: ev.genome && ev.genome.staked },
            S.GATE_X, S.FLOOR_Y + 16);
          if (!a) break;
          a.entering = true;
          a.hx0 = 70 + rnd(0, 1) * (S.WORLD_W - 150);  // their place in the hall
          a.hy0 = rnd(S.FLOOR_Y + 12, S.WORLD_H - 14);
          a.facing = 1;
          if (ev.challenger && ev.sponsor_token === this.myToken) {
            // that's YOURS — the strategy you forged, walking in
            this.myChampion = ev.id;
            this.myLine = new Set([ev.id]);
            this.championFallen = null;
            this._tick(`★ <b>your champion ${ev.name}</b> enters the hall`);
            if (this.onChampion) this.onChampion("arrived", a);
          } else {
            this._tick(`<b>${ev.house}</b> ${ev.challenger ? "— a challenger —" : ""} arrives through the gate`);
          }
          break;
        }
        case "agent.birth": {
          const parents = ev.parents || [];
          const pa = this.agents.get(parents[0]), pb = this.agents.get(parents[1]);
          const x = pa && pb ? (pa.x + pb.x) / 2 : undefined, y = pa && pb ? Math.max(pa.y, pb.y) : undefined;
          const a = this._add({ id: ev.id, genome: ev.genome, name: ev.name, house: ev.house, staked: ev.genome && ev.genome.staked, species: ev.species }, x, y);
          if (!a) break;
          a.parents = parents;
          // the child ASSEMBLES from its parents' parts, driven by the settled
          // crossover map (which block came from whom)
          const ck = pa && pb ? this._ckey({ a: parents[0], b: parents[1] }) : null;
          const court = ck ? this.courts.get(ck) : null;
          a.assembling = (pa && pb) ? { t: 0, pa: parents[0], pb: parents[1],
            crossover: (court && court.crossover) || null } : null;
          a.born = a.assembling ? 0 : 1;
          // your champion's bloodline: any child with a parent in the line joins it
          if (this.myLine.size && parents.some(p => this.myLine.has(p))) {
            this.myLine.add(ev.id);
            this._tick(`★ <b>your line grows</b> — ${ev.name}`);
          } else {
            const star = this.myHouse && ev.house === this.myHouse ? "★ " : "";
            this._tick(`${star}child born of ${pa ? pa.house : "?"}×${pb ? pb.house : "?"} · <b>${ev.house}</b>`);
          }
          break;
        }
        case "agent.critical": { const a = this.agents.get(ev.id); if (a) a.critical = true; break; }
        case "agent.death": {
          const a = this.agents.get(ev.id);
          if (a) { a.mode = "dying"; a.dying = 1; a.deathCause = ev.cause; a.heirs = ev.heirs; }
          if (ev.id === this.myChampion) {
            const heirs = [...this.myLine].filter(id => id !== ev.id && this.agents.has(id));
            this.championFallen = { heirs: heirs.length, cause: ev.cause };
            this._tick(`★ <b>your champion has fallen</b>` +
              (heirs.length ? ` — ${heirs.length} of the line carry on` : " — the line is ended"));
            if (this.onChampion) this.onChampion("fallen", this.championFallen);
          }
          this.myLine.delete(ev.id);
          break;
        }
        case "neg.start": this._startDuel(ev); break;
        case "neg.offer": this._offer(ev); break;
        case "neg.accept": this._accept(ev); break;
        case "neg.walk": this._walk(ev); break;
        case "court.start": this._startCourt(ev); break;
        case "court.offer": { const c = this.courts.get(this._ckey(ev)); if (c) c.beat = 6; break; }
        case "court.accept": this._courtAccept(ev); break;
        case "court.impasse": this._courtImpasse(ev); break;
        case "era.change":
          this.era = ev.era; this.eraLabel = ev.label;
          if (ev.pollinator) this.pollinator = ev.pollinator;
          this._tick(`the market turns — <b>${ev.label}</b>` + (ev.pollinator ? ` · ${ev.pollinator.name} takes wing` : ""));
          break;
        case "bloom":
          this.latestBloom = ev;
          this._tick(`fairest bloom — <b>House ${ev.house}</b>'s ${ev.flower ? ev.flower.species : "flower"}, judged by ${ev.pollinator ? ev.pollinator.name : "the season"}`);
          if (this.onBloom) this.onBloom(ev);
          break;
        case "census":
          this.prevTactics = (this.census && this.census.tactics) || this.prevTactics;
          this.census = ev;
          if (ev.mean_knob != null) { this.knobHistory.push({ m: ev.mean_knob, o: ev.era_optimal_knob }); if (this.knobHistory.length > 80) this.knobHistory.shift(); }
          break;
        case "leaderboard": {
          this.leaderboard = ev.top || [];
          // hang the dynasty banners: top houses, length = wealth
          const houses = new Map();
          for (const r of this.leaderboard) {
            const h = houses.get(r.house) || { house: r.house, wealth: 0 };
            h.wealth += r.energy; houses.set(r.house, h);
          }
          const SP2 = A.sprites;
          const top = [...houses.values()].sort((p, q) => q.wealth - p.wealth)
            .map(h => {
              const ag = [...this.agents.values()].find(a => a.house === h.house);
              const lead = this.leaderboard.find(r => r.house === h.house);
              return { ...h, ramp: ag ? SP2.rampFor(ag.g) : SP2.rampForHouse(h.house),
                       lead: lead ? lead.name : "" };
            });
          this.houseWealth = top;          // the DYNASTIES panel ranks HOUSES
          S.setBanners(top.slice(0, 4));   // and the hall hangs the top four
          break;
        }
        case "species.update": this.species = ev.species || []; break;
        case "energy.tick": {
          // apply the upkeep/tax deltas so client energy trends live (drives the
          // glow + the "starving flower wilts" crest). Deal income is credited
          // on neg.accept below.
          const d = ev.deltas || {};
          for (const id in d) { const a = this.agents.get(+id); if (a) a.energy = Math.max(0, a.energy + d[id]); }
          break;
        }
        case "gen.end": this.gen = ev.gen; this.wantPullback = true; break;
        case "auction.hammer": this._tick(`grand auction won — <b>+${ev.gain}</b> energy`); break;
        case "highlight":
          if (ev.kind === "dynasty_founder_death" && ev.refs) {
            // a candle is lit on the crypt wall — the world remembers
            this.memorials.push({ house: ev.refs.house, ramp: A.sprites.rampForHouse(ev.refs.house || "") });
            S.setMemorials(this.memorials);
            this._tick(`a candle is lit for <b>House ${ev.refs.house}</b>`);
          }
          if (this.onHighlight) this.onHighlight(ev);
          break;
      }
    },

    _tick(html) { this.ticker.push(html); if (this.ticker.length > 40) this.ticker.shift(); if (this.onTicker) this.onTicker(html); },

    _freeZone() {
      const used = new Set([...this.duels.values()].map(d => d.zone));
      for (let i = 0; i < S.ZONES.length; i++) if (!used.has(i)) return i;
      return -1; // overflow -> background quick-handshake
    },

    _startDuel(ev) {
      // either side may be the house bot (id -1, no on-screen agent) — move
      // each real participant to the table independently
      const a = this.agents.get(ev.a), b = this.agents.get(ev.b);
      const zone = this._freeZone();
      const d = {
        neg: ev.neg, a: ev.a, b: ev.b, house: ev.house, kind: ev.kind, zone,
        peer: !!ev.peer,
        spread: 1, prevSpread: 1, sellerPos: 0.8, buyerPos: 0.2,
        phase: "approach", flash: 0, shake: 0, dead: 0,
        stakes: ev.stakes || {}, overflow: zone < 0, runes: [], t: 0,
      };
      if (zone >= 0) {
        const z = S.ZONES[zone];
        if (a) { a.mode = "duel"; a.tx = z.x - 10; a.ty = z.y; a.facing = 1; }
        if (b) { b.mode = "duel"; b.tx = z.x + 10; b.ty = z.y; b.facing = -1; }
      }
      this.duels.set(ev.neg, d);
    },

    _offer(ev) {
      const d = this.duels.get(ev.neg); if (!d) return;
      d.t = 8; d.phase = "trade";
      if (typeof ev.spread === "number") { d.prevSpread = d.spread; d.spread = ev.spread; }
      if (typeof ev.pos === "number") { if (ev.actor === "seller") d.sellerPos = ev.pos; else d.buyerPos = ev.pos; }
      d.lastActor = ev.actor;
      d.runeCount = ev.package ? Object.keys(ev.package).length : d.runeCount;
      if (this.onDuelOffer) this.onDuelOffer(d, ev);
    },

    _accept(ev) {
      const d = this.duels.get(ev.neg); if (!d) return;
      // THE HOLD: a beat of frozen stillness before the clash — anticipation
      // is what makes the payoff land. choreo counts it down, then fires the
      // close FX (flash, clasp, numbers).
      d.phase = "hold"; d.hold = 18; d.spread = 0;
      d.surplus = ev.surplus || { seller: 0, buyer: 0 };
      d.pending = { neg: ev.neg, surplus: d.surplus };  // always carries surplus
      const z = S.ZONES[d.zone] || { x: 260, y: 224 };
      this.dealHeat.push({ x: z.x, y: z.y + 8, life: 60 });
      // credit the two duelists' energy (≈ engine's energy_per_surplus) so the
      // client tracks deal income, not just the upkeep decrements
      const seller = this.agents.get(d.a), buyer = this.agents.get(d.b);
      if (seller) { seller.energy += (d.surplus.seller || 0) * 34; seller.deals = (seller.deals || 0) + 1; }
      if (buyer) { buyer.energy += (d.surplus.buyer || 0) * 34; buyer.deals = (buyer.deals || 0) + 1; }
    },

    _walk(ev) {
      const d = this.duels.get(ev.neg); if (!d) return;
      d.phase = "walk"; d.dead = 30;
      if (this.onDuelWalk) this.onDuelWalk(d, ev);
    },

    _startCourt(ev) {
      const key = this._ckey(ev);
      const a = this.agents.get(ev.a), b = this.agents.get(ev.b);
      const cx = a && b ? (a.x + b.x) / 2 : 280, cy = a && b ? Math.max(a.y, b.y) : 230;
      this.courts.set(key, { a: ev.a, b: ev.b, x: cx, y: cy, beat: 6, phase: "court", dead: 0 });
      if (a) { a.mode = "court"; a.tx = cx - 9; a.ty = cy; a.facing = 1; }
      if (b) { b.mode = "court"; b.tx = cx + 9; b.ty = cy; b.facing = -1; }
    },
    _ckey(ev) { return Math.min(ev.a, ev.b) + ":" + Math.max(ev.a, ev.b); },
    _courtAccept(ev) {
      const c = this.courts.get(this._ckey(ev)); if (c) { c.phase = "birth"; c.dead = 40; c.crossover = ev.crossover; c.child = ev.child_preview; }
    },
    _courtImpasse(ev) {
      const c = this.courts.get(this._ckey(ev)); if (c) { c.phase = "impasse"; c.dead = 24; }
    },
  };

  A.world = world;
})();

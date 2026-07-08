/* Canned event stream — the offline fallback AND the dev fixture (so the
   renderer works before/without the backend). Generates a varied cast and a
   living loop of duels, a courtship, a death, and an era turn. */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  // Houses = the eight founding archetypes (same as the live sim), so backing
  // a house works identically offline.
  const HOUSES = [
    ["Monk", "boulware", 0.4, 0.1, false], ["Berserker", "anchorer", 0.95, 0.8, false],
    ["Merchant", "conceder", 0.5, 0.25, false], ["Mirror", "mirror", 0.6, 0.4, false],
    ["Gambler", "closer", 0.8, 0.9, false], ["Diplomat", "conceder", 0.45, 0.15, true],
    ["Vulture", "closer", 0.7, 0.7, false], ["Hermit", "patient", 0.5, 0.5, false],
  ];
  const GIVEN = ["Vex", "Moro", "Cael", "Bram", "Nyx", "Orin", "Sable", "Dree", "Thal", "Wren", "Koro", "Garr", "Mira", "Rue", "Vane", "Ash", "Loth", "Pell"];
  let seed = 12345;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;

  function genome(i) {
    const [, tactic, aggr, walk, staked] = HOUSES[i % HOUSES.length];
    return {
      pareto_knob: +(0.3 + rnd() * 0.7).toFixed(2), open_aggression: +(aggr + (rnd() - 0.5) * 0.1).toFixed(2),
      walk_margin: +(walk + (rnd() - 0.5) * 0.1).toFixed(2), patience: +rnd().toFixed(2),
      bundle_focus: [0.25, 0.25, 0.25, 0.25],
      mate_w: [0.6, 0.2, 0.1, 0.2], truncation: 0.2,
      staked, tactic_family: tactic,
    };
  }

  const agents = [];
  for (let i = 0; i < 18; i++) {
    const house = HOUSES[i % HOUSES.length][0];
    agents.push({ id: i, name: GIVEN[i % GIVEN.length] + " of House " + house,
      house, genome: genome(i),
      staked: false, species: i % 5, energy: 80 + rnd() * 200, age: 0, lineage: 0, reputation: 0.5, deals: 0 });
  }
  agents.forEach(a => a.staked = a.genome.staked);

  const POLL = {
    symmetric: { name: "the Bat", glyph: "🦇" }, buyers: { name: "the Dawn Moth", glyph: "🌙" },
    sellers: { name: "the Ember Bee", glyph: "🐝" }, contract: { name: "the Night Sphinx", glyph: "✦" },
  };
  function snapshot() {
    return { v: 1, type: "world.snapshot", seq: 0, gen: 12, t: Date.now(),
      era: "symmetric", era_label: "Symmetric Market", assortative: false,
      pollinator: POLL.symmetric, agents };
  }

  let seq = 1, gen = 12, negId = 0, era = "symmetric";
  const ERAS = [["symmetric", "Symmetric Market"], ["buyers", "Buyers' Market"], ["sellers", "Sellers' Market"], ["contract", "Contract Season"]];
  const ev = (o) => Object.assign({ v: 1, seq: seq++, gen, tick: seq, t: Date.now() }, o);

  function stream(cb) {
    let step = 0;
    const active = []; // {neg, a, b, kind, spread, turns}
    function startDuel() {
      const a = (Math.random() * agents.length) | 0; let b = (Math.random() * agents.length) | 0;
      if (b === a) b = (b + 1) % agents.length;
      const kind = Math.random() < 0.3 ? "bundle" : "price";
      const neg = negId++;
      const rivalry = Math.random() < 0.25 ? { meetings: 3 + ((Math.random() * 4) | 0), series: [2, 1] } : null;
      const last = Math.random() < 0.12;
      const peer = !!(agents[a].staked && agents[b].staked);
      active.push({ neg, a: agents[a].id, b: agents[b].id, kind, spread: 0.9, turns: 3 + ((Math.random() * 6) | 0), n: 0 });
      cb(ev({ type: "neg.start", neg, kind, a: agents[a].id, b: agents[b].id, house: false, peer,
        roles: { seller: agents[a].id, buyer: agents[b].id }, stakes: { rivalry, last_stand: last } }));
    }
    const timer = setInterval(() => {
      step++;
      if (active.length < 5 && Math.random() < 0.5) startDuel();
      for (let i = active.length - 1; i >= 0; i--) {
        const d = active[i]; d.n++;
        if (d.n >= d.turns) {
          if (Math.random() < 0.72) cb(ev({ type: "neg.accept", neg: d.neg, pos: 0.5, surplus: { seller: Math.random() * 0.4, buyer: Math.random() * 0.4 }, rounds: d.turns, kind: d.kind }));
          else cb(ev({ type: "neg.walk", neg: d.neg, actor: "timeout", reason: "timeout" }));
          active.splice(i, 1);
        } else {
          d.spread *= 0.7 + Math.random() * 0.2;
          cb(ev({ type: "neg.offer", neg: d.neg, turn: d.n, actor: d.n % 2 ? "buyer" : "seller",
            pos: d.n % 2 ? 0.2 + d.n * 0.05 : 0.8 - d.n * 0.05, action: "counter", spread: d.spread,
            package: d.kind === "bundle" ? { price: "p1", delivery: "d0", quality: "q2" } : undefined }));
        }
      }
      // occasional life events
      if (step % 22 === 10) { const p = agents[(Math.random() * agents.length) | 0], q = agents[(Math.random() * agents.length) | 0]; cb(ev({ type: "court.start", a: p.id, b: q.id, stakes: { a_energy: 200, b_energy: 180 } })); setTimeout(() => cb(ev({ type: "court.accept", a: p.id, b: q.id, crossover: { bargain: "pa", risk: "pb" }, child_preview: p.genome })), 1800); }
      if (step % 40 === 20) { const v = agents[(Math.random() * agents.length) | 0]; cb(ev({ type: "highlight", kind: "record_surplus", refs: {}, blurb: "record deal" })); }
      if (step % 55 === 30) { const v = agents[3 + ((Math.random() * 10) | 0)]; cb(ev({ type: "agent.critical", id: v.id, energy: 12 })); }
      if (step % 90 === 60) { const idx = Math.floor(Math.random() * agents.length); const v = agents[idx]; cb(ev({ type: "agent.death", id: v.id, cause: "starvation", age: 30, lineage: 0, deals: 5, heirs: [agents[(idx + 1) % agents.length].id], house: v.house })); if (Math.random() < 0.4) cb(ev({ type: "highlight", kind: "dynasty_founder_death", refs: { id: v.id, house: v.house }, blurb: v.house + " founder falls" })); }
      if (step % 100 === 80) { const h = HOUSES[(Math.random() * HOUSES.length) | 0][0]; const nid = 100 + step; cb(ev({ type: "immigration", id: nid, name: GIVEN[nid % GIVEN.length] + " of House " + h, house: h, genome: genome((Math.random() * 8) | 0), reason: "population_floor" })); }
      if (step % 120 === 100) { era = ERAS[(step / 120) % 4 | 0]; cb(ev({ type: "era.change", era: era[0], label: era[1], optimal_knob: 0.7, pollinator: POLL[era[0]] })); cb(ev({ type: "highlight", kind: "era_flip", refs: {}, blurb: "the market turns" })); }
      if (step % 46 === 44) { // Bloom of the Generation
        const eraKey = Array.isArray(era) ? era[0] : era;
        const champ = agents.slice().sort((a, b) => b.energy - a.energy)[(Math.random() * 3) | 0];
        const spec = A.flora.SPECIES[champ.genome.tactic_family] || "tulip";
        cb(ev({ type: "bloom", id: champ.id, name: champ.name, house: champ.house,
          genome: champ.genome, flower: { species: spec, warmth: champ.genome.pareto_knob, luminance: champ.genome.staked ? 0.75 : 0.35 },
          beauty: 0.7 + Math.random() * 0.3, rarity: Math.random() * 0.3, pollinator: POLL[eraKey] || POLL.symmetric, species: spec }));
      }
      if (step % 14 === 0) {
        const top = agents.slice().sort((a, b) => b.energy - a.energy).slice(0, 6).map(a => ({ id: a.id, name: a.name, house: a.house, energy: a.energy + Math.random() * 20, species: a.species, lineage: a.lineage }));
        cb(ev({ type: "leaderboard", top }));
        const tactics = {};
        for (const a of agents) {
          const f = a.genome.tactic_family;
          tactics[f] = tactics[f] || { n: 0, mean_e: 0, income: 0 };
          tactics[f].n++; tactics[f].mean_e = Math.round(100 + Math.random() * 150);
          tactics[f].income = Math.round((15 + Math.random() * 25) * 10) / 10;
        }
        cb(ev({ type: "census", pop: agents.length, era: era, staked_frac: 0.14, mean_knob: 0.5 + Math.sin(step / 30) * 0.15, era_optimal_knob: 0.7, mean_energy: 180, n_species: 5, deal_rate: 0.6, tactics,
          attest_lift: 0.1 + Math.random() * 0.1, attest_n: 20 + ((Math.random() * 30) | 0) }));
        cb(ev({ type: "species.update", species: [0, 1, 2, 3, 4].map(id => ({ id, count: 2 + ((Math.random() * 5) | 0), centroid: [], exemplar: id })) }));
      }
    }, 850);
    return timer;
  }

  // demo-mode forge: your champion joins the local world through the gate,
  // same event shape the live backend emits
  let _nextChampId = 500;
  function injectChampion(spec) {
    const id = _nextChampId++;
    const g = { pareto_knob: spec.boldness, open_aggression: spec.boldness,
      walk_margin: spec.bluff, patience: spec.patience,
      bundle_focus: [0.25, 0.25, 0.25, 0.25], mate_w: [0.5, 0.2, 0.1, 0.2],
      truncation: 0.2, staked: !!spec.staked, tactic_family: spec.tactic };
    const name = "Champion of House " + spec.house;
    agents.push({ id, name, house: spec.house, genome: g, staked: g.staked,
      species: 1, energy: 100, age: 0, lineage: 0, reputation: 0.5, deals: 0 });
    if (A.net && A.net.onEvent) A.net.onEvent(ev({ type: "immigration", id, name,
      house: spec.house, genome: g, reason: "challenger", challenger: true,
      sponsor_token: spec.token }));
  }

  A.demo = { snapshot, stream, injectChampion };
})();

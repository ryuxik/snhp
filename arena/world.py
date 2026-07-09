"""The world: synchronous, seeded, event-sourced. One generation at a time.

`generation_events()` is a generator that advances all state and yields the full
event stream for a generation (market deals interleaved turn-by-turn so duels
read as concurrent, then upkeep/deaths, mating, era check, census). The runner
paces emission over wall-clock; fastforward drains it instantly. Same seed =>
identical event log (up to the wall-clock `t`, which is excluded from the hash).

Every strategic call is delegated (executor / courtship / auction); this module
only does bookkeeping: energy, selection, reproduction, eras, metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from arena.config import ArenaConfig, CONFIG
from arena.credit import Scorecard
from arena.genome import Genome, seed_population, ARCHETYPES, TACTIC_FAMILIES
from arena.names import NameForge
from arena import scenarios as sc
from arena import executor as ex
from arena import courtship as ct
from arena import species as sp
from arena import auction as auc
from arena import flora


@dataclass
class Agent:
    id: int
    name: str
    house: str
    genome: Genome
    energy: float
    scorecard: Scorecard
    reputation: float = 0.5
    age: int = 0
    born_gen: int = 0
    last_mated: int = -999
    lineage_depth: int = 0
    parents: tuple = ()
    children: list = field(default_factory=list)
    deals_closed: int = 0
    species: int = -1
    total_earned: float = 0.0


class World:
    def __init__(self, cfg: ArenaConfig = CONFIG, clock_ms: Optional[Callable[[], int]] = None,
                 neutral: bool = False):
        self.cfg = cfg
        # neutral null (science): reproduction + death decoupled from energy, so
        # any surviving trait movement is drift, not selection (Koza's baseline).
        self.neutral = neutral
        self.rng = np.random.default_rng(cfg.seed)
        self.names = NameForge(self.rng)
        self.species = sp.SpeciesTracker(cfg)
        self._clock = clock_ms or (lambda: 0)
        self.gen = 0
        self.tick = 0
        self.seq = 0
        self.era = "symmetric"
        self.prev_era = "symmetric"
        self.era_started = 0
        self.era_interp = 1.0
        self.sigma = cfg.sigma_stable
        self.assortative = bool(cfg.assortative)
        self.agents: dict[int, Agent] = {}
        self._next_agent_id = 0
        self.hall_of_fame: dict[str, list] = {e: [] for e in sc.ERAS}
        self.rivalry: dict[tuple, dict] = {}
        self.ledger = {k: 0.0 for k in
                       ("income", "immigration", "tax", "upkeep", "birthtax",
                        "death", "capclamp", "auction")}
        self.record_surplus = 0.0
        self._peer_surplus_samples: list[float] = []
        self._adv_surplus_samples: list[float] = []
        # per-generation income by tactic — the REAL "who's winning" scoreboard
        # (wealth is cumulative and luck-confounded; income/gen is the signal)
        self._gen_income: dict[str, float] = {}
        self._gen_income_agent: dict[int, float] = {}   # per-agent, for Price eq
        self._prev_aggr: float = 0.5                     # softening detector state
        self._prev_energy: float = cfg.energy_start
        # attestation probe: paired-seed counterfactuals (same pair, same
        # scenario, staked forced on vs off). The observational peer-vs-ordinary
        # comparison is confounded by genome composition; this is the causal
        # lift, measured the way the repo measures everything (paired seeds).
        from collections import deque as _deque
        self._attest_pairs = _deque(maxlen=60)
        # viewer-forged champions, queued by the API thread (list.append is
        # atomic under the GIL) and consumed at each generation boundary
        self._champion_queue: list[dict] = []
        self._seed_population()

    # ── viewer champions: forge → through the gate ──
    def queue_champion(self, spec: dict) -> None:
        self._champion_queue.append(spec)

    # ── energy plumbing (all mutations go through here for the ledger) ──
    def _add_energy(self, a: Agent, delta: float, key: str) -> None:
        a.energy += delta
        if key in self.ledger:
            # sinks recorded positive; income/immigration positive too
            self.ledger[key] += abs(delta) if key not in ("income", "immigration") else delta

    def _cap(self, a: Agent) -> None:
        if a.energy > self.cfg.energy_cap:
            self.ledger["capclamp"] += a.energy - self.cfg.energy_cap
            a.energy = self.cfg.energy_cap

    def _seed_population(self) -> None:
        for house, g in seed_population(self.cfg.pop_start, self.rng):
            self._spawn(g, house=house, parents=(), lineage=0)

    def _spawn(self, g: Genome, house: str, parents: tuple, lineage: int,
               energy: Optional[float] = None, scorecard: Optional[Scorecard] = None) -> Agent:
        aid = self._next_agent_id
        self._next_agent_id += 1
        a = Agent(id=aid, name=self.names.full(house), house=house, genome=g,
                  energy=self.cfg.energy_start if energy is None else energy,
                  scorecard=scorecard or Scorecard(), born_gen=self.gen,
                  parents=parents, lineage_depth=lineage)
        self.agents[aid] = a
        return a

    # ── event envelope ──
    def _ev(self, type_: str, **fields) -> dict:
        self.seq += 1
        ev = {"v": 1, "seq": self.seq, "tick": self.tick, "gen": self.gen,
              "t": self._clock(), "type": type_}
        ev.update(fields)
        return ev

    # ─── snapshot (sent on connect / written per gen) ───
    def snapshot(self) -> dict:
        poll = flora.pollinator_for(self.era)
        return {
            "v": 1, "gen": self.gen, "era": self.era, "era_label": sc.ERA_LABELS[self.era],
            "assortative": self.assortative,
            "pollinator": {"name": poll["name"], "glyph": poll["glyph"]},
            "agents": [self._agent_public(a) for a in self.agents.values()],
            "config": {"pop_cap": self.cfg.pop_cap, "seed": self.cfg.seed},
        }

    def _agent_public(self, a: Agent) -> dict:
        return {"id": a.id, "name": a.name, "house": a.house,
                "genome": a.genome.to_dict(), "energy": round(a.energy, 1),
                "staked": a.genome.staked, "species": a.species,
                "age": a.age, "lineage": a.lineage_depth,
                "reputation": round(a.reputation, 3), "deals": a.deals_closed}

    # ─── one generation ───
    def generation_events(self):
        cfg = self.cfg
        self.gen += 1
        self._gen_income = {}
        self._gen_income_agent = {}
        for a in self.agents.values():
            a.age += 1

        yield from self._admit_champions()
        yield from self._market_phase()
        yield from self._upkeep_phase()
        yield from self._mating_phase()
        if self.gen % cfg.auction_every_gens == 0 and len(self.agents) >= 4:
            yield from self._auction_phase()
        yield from self._era_phase()
        yield from self._census_phase()
        yield from self._floor_phase()

    # ── champions: viewer-forged strategies enter through the gate ──
    def _admit_champions(self):
        """Consume queued viewer champions (max 4/gen, capacity permitting).
        A challenger is a REAL agent built from the viewer's chosen tactic and
        dials — diegetic immigration, flagged honestly as a challenger. The
        sponsor_token lets the forging client recognize its own champion."""
        # A viewer's champion MUST enter promptly — the API promises "enters at
        # the next generation". On a full world (the live arena runs pinned at
        # pop_cap) a champion would otherwise sit in the queue forever. So admit
        # up to 4/gen even at cap, allowing a small bounded overflow; the
        # champion simply displaces that generation's births (births_available
        # clamps at 0), and crowding tax + deaths rebalance within a gen or two.
        admitted = 0
        hard_cap = self.cfg.pop_cap + 6
        while self._champion_queue and admitted < 4 and len(self.agents) < hard_cap:
            spec = self._champion_queue.pop(0)
            g = Genome(
                pareto_knob=float(np.clip(spec.get("boldness", 0.6), 0.0, 1.0)),
                open_aggression=float(np.clip(spec.get("boldness", 0.6), 0.0, 1.0)),
                walk_margin=float(np.clip(spec.get("bluff", 0.3), 0.0, 1.0)),
                patience=float(np.clip(spec.get("patience", 0.5), 0.0, 1.0)),
                staked=bool(spec.get("staked", False)),
                tactic_family=spec.get("tactic", "conceder"),
            )
            house = str(spec.get("house", "Challenger"))[:24] or "Challenger"
            a = self._spawn(g, house=house, parents=(), lineage=0)
            self.ledger["immigration"] += a.energy
            admitted += 1
            yield self._ev("immigration", id=a.id, name=a.name, house=house,
                           genome=g.to_dict(), reason="challenger",
                           challenger=True,
                           sponsor_token=str(spec.get("token", ""))[:64])
            yield self._ev("highlight", kind="challenger",
                           refs={"id": a.id, "house": house},
                           blurb=f"a challenger enters: {a.name}")

    # ── market ──
    def _market_phase(self):
        """Bounded-concurrency scheduler: at most max_live_negotiations run at
        once (the renderer can only choreograph a handful), advanced one round
        per tick so duels read as concurrent AND the generation paces to a few
        minutes. As each deal finishes it settles and the next starts."""
        cfg = self.cfg
        agents = list(self.agents.values())
        if len(agents) < 2:
            return
        specs = self._build_schedule(agents)
        K = cfg.max_live_negotiations
        queue = list(enumerate(specs))
        active: list[dict] = []  # {neg, meta, gen}

        def fill():
            starts = []
            while queue and len(active) < K:
                k, spec = queue.pop(0)
                made = self._make_negotiation(k, spec)
                if made is None:
                    continue
                meta, g = made
                active.append({"neg": k, "meta": meta, "gen": g})
                rv = self._rivalry(meta["sid"], meta["bid"]) if not meta["house"] else None
                starts.append(self._ev(
                    "neg.start", neg=k, kind=meta["kind"], a=meta["sid"],
                    b=(meta["bid"] if not meta["house"] else -1),
                    house=meta["house"], peer=meta.get("peer", False),
                    roles={"seller": meta["sid"], "buyer": meta["bid"]},
                    stakes={"rivalry": rv, "last_stand": self._is_last_stand(meta["sid"])}))
            return starts

        for ev in fill():
            yield ev
        while active:
            self.tick += 1
            still = []
            for item in active:
                try:
                    ev = next(item["gen"])
                    ev["neg"] = item["neg"]
                    yield self._ev(ev.pop("type"), **ev)
                    still.append(item)
                except StopIteration as e:
                    yield from self._settle_deal(item["meta"], e.value)
            active = still
            for ev in fill():
                yield ev

    def _make_negotiation(self, k: int, spec):
        """Turn a schedule spec into (meta, generator). Either side may be the
        house bot (id -1); the real party must still be alive. Returns None if a
        real party has died since scheduling."""
        cfg = self.cfg
        sid, bid, kind, is_house = spec
        # resolve each side's genome; id -1 = the (unstaked) house bot
        if sid == -1:
            seller_g = self._house_bot()
        else:
            s = self.agents.get(sid)
            if s is None:
                return None
            seller_g = s.genome
        if bid == -1:
            buyer_g = self._house_bot()
        else:
            b = self.agents.get(bid)
            if b is None:
                return None
            buyer_g = b.genome
        neg_seed = cfg.seed * 1_000_003 + self.gen * 9973 + k
        dl = self._horizon(seller_g, buyer_g)  # house bot is unstaked -> peer=False
        meta = {"neg": k, "sid": sid, "bid": bid, "kind": kind, "house": is_house,
                # a PACT: both sides attested — truthful reservations (price) /
                # true-BATNA exchange (bundle); the renderer marks these deals
                "peer": bool(seller_g.staked and buyer_g.staked),
                # stashed for leave-one-block-out counterfactual credit
                "seed": neg_seed, "dl": dl, "s_g": seller_g, "b_g": buyer_g}
        if kind == "bundle":
            bs = sc.gen_bundle_scenario(cfg, self.era, self.rng)
            meta["scn"] = bs
            s_side = ex.Side(seller_g, "seller", 0.0, sid)
            b_side = ex.Side(buyer_g, "buyer", 0.0, bid)
            return meta, ex.run_bundle_negotiation(s_side, b_side, bs, dl, neg_seed, cfg)
        center = sc.era_center(self.era, self.era_interp, self.prev_era)
        ps = sc.gen_price_scenario(cfg, self.era, center, self.rng)
        meta["scn"] = ps
        if not is_house and k % 4 == 0:
            self._probe_attestation(seller_g, buyer_g, ps, dl, neg_seed)
        s_side = ex.Side(seller_g, "seller", ps.r_s, sid)
        b_side = ex.Side(buyer_g, "buyer", ps.r_b, bid)
        return meta, ex.run_price_negotiation(s_side, b_side, ps, dl, neg_seed, cfg)

    def _probe_attestation(self, sg: Genome, bg: Genome, ps, dl: int, seed: int) -> None:
        """Off-log counterfactual pair: this exact matchup and scenario played
        twice, staked forced ON then OFF, same seed. The paired difference is
        the causal attestation lift the census reports (no events, no energy —
        a measurement, not a deal)."""
        from dataclasses import replace as _rp
        joints = []
        for staked in (True, False):
            s2, b2 = _rp(sg, staked=staked), _rp(bg, staked=staked)
            g = ex.run_price_negotiation(ex.Side(s2, "seller", ps.r_s, -2),
                                         ex.Side(b2, "buyer", ps.r_b, -3),
                                         ps, dl, seed ^ 0x5A17E, self.cfg)
            out = None
            try:
                while True:
                    next(g)
            except StopIteration as e:
                out = e.value
            joints.append((out.surplus_seller + out.surplus_buyer) if out.deal else 0.0)
        self._attest_pairs.append((joints[0], joints[1]))

    _NEUTRAL = None  # a fixed neutral baseline genome (built lazily)

    def _counterfactual_credit(self, a, meta, role: str, actual_surplus: float) -> None:
        """Leave-ONE-block-out causal credit for agent `a` on the deal it just
        closed (Koza's fix for the confounded win-rate scorecard). Reset one
        block to a neutral allele, replay the SAME scenario+opponent+seed, and
        the surplus DELTA is that block's marginal contribution — the un-confounded
        signal the courtship logroll then bargains with. One block per deal
        (round-robin), so cost is ~1 extra negotiation per close."""
        scn = meta.get("scn")
        if scn is None or a.genome.tactic_family is None:
            return
        if World._NEUTRAL is None:
            World._NEUTRAL = Genome()  # mid/neutral alleles, unstaked, no schedule
        neutral = World._NEUTRAL
        from arena.genome import BLOCKS as _BLK
        block = _BLK[a.deals_closed % len(_BLK)]
        cf_g = a.genome.with_block(block, neutral.block_values(block))
        # reconstruct both sides in original roles, a's genome -> counterfactual
        seller_g = cf_g if role == "seller" else meta["s_g"]
        buyer_g = cf_g if role == "buyer" else meta["b_g"]
        if meta["kind"] == "price":
            g = ex.run_price_negotiation(ex.Side(seller_g, "seller", scn.r_s, -4),
                                         ex.Side(buyer_g, "buyer", scn.r_b, -5),
                                         scn, meta["dl"], meta["seed"] ^ 0x1EAF, self.cfg)
        else:
            g = ex.run_bundle_negotiation(ex.Side(seller_g, "seller", 0.0, -4),
                                          ex.Side(buyer_g, "buyer", 0.0, -5),
                                          scn, meta["dl"], meta["seed"] ^ 0x1EAF, self.cfg)
        out = None
        try:
            while True:
                next(g)
        except StopIteration as e:
            out = e.value
        cf_surplus = (out.surplus_seller if role == "seller" else out.surplus_buyer) if out.deal else 0.0
        # marginal in [0,1]: 0.5 = neutral block, >0.5 = the allele helped
        span = max(self.cfg.scenario_span, 1e-6)
        marginal = 0.5 + 0.5 * float(np.clip((actual_surplus - cf_surplus) / span * 4.0, -1, 1))
        a.scorecard.credit_block(block, marginal)

    def _build_schedule(self, agents):
        """deals_per_gen per agent as seller/buyer split; pairing random (or
        staked-assortative in Act II). Returns list of (seller_id, buyer_id,
        kind, is_house)."""
        cfg = self.cfg
        ids = [a.id for a in agents]
        center = sc.era_center(self.era, self.era_interp, self.prev_era)
        bundle_frac = sc.bundle_fraction(self.era, self.era_interp, self.prev_era)
        schedule = []
        n_deals = cfg.deals_per_gen
        for a in agents:
            for d in range(n_deals):
                is_house = (self.rng.random() < cfg.house_deal_frac)
                role_seller = (d % 2 == 0)
                kind = "bundle" if self.rng.random() < bundle_frac else "price"
                if is_house:
                    # the agent plays seller vs the house (role_seller) or buyer
                    # vs the house — the executor now resolves the -1 side as the
                    # bot, so the science yardstick evaluates BOTH roles.
                    if role_seller:
                        schedule.append((a.id, -1, kind, True))
                    else:
                        schedule.append((-1, a.id, kind, True))
                    continue
                partner = self._pick_partner(a, ids)
                if partner is None:
                    continue
                if role_seller:
                    schedule.append((a.id, partner, kind, False))
                else:
                    schedule.append((partner, a.id, kind, False))
        return schedule

    def _pick_partner(self, a: Agent, ids: list[int]) -> Optional[int]:
        pool = [i for i in ids if i != a.id]
        if not pool:
            return None
        if self.assortative and a.genome.staked and self.rng.random() < self.cfg.assortative_q:
            staked_pool = [i for i in pool if self.agents[i].genome.staked]
            if staked_pool:
                pool = staked_pool
        return int(pool[int(self.rng.integers(len(pool)))])

    def _horizon(self, ga: Genome, gb: Optional[Genome]) -> int:
        peer = bool(ga.staked and gb is not None and gb.staked)
        if peer:
            return int(self.rng.integers(self.cfg.peer_horizon_lo, self.cfg.peer_horizon_hi + 1))
        return int(self.rng.integers(self.cfg.horizon_lo, self.cfg.horizon_hi + 1))

    def _house_bot(self) -> Genome:
        """The fixed external opponent (a rotating archetype), the science-HUD
        yardstick and an anchor against coevolutionary disengagement. Forced
        UNSTAKED: the house is never a verified peer, so it must not trigger the
        staked×staked peer path (peer_mode / true-BATNA exchange) or pollute the
        peer-premium metric via `peer = seller.staked and buyer.staked`."""
        keys = list(ARCHETYPES.keys())
        from dataclasses import replace
        return replace(ARCHETYPES[keys[self.gen % len(keys)]], staked=False)

    def _settle_deal(self, m: dict, out: ex.NegOutcome):
        cfg = self.cfg
        span = cfg.scenario_span
        sid, bid, house = m["sid"], m["bid"], m["house"]
        seller = self.agents.get(sid)   # None when the house is the seller (-1)
        buyer = self.agents.get(bid)    # None when the house is the buyer (-1)
        # premium metric: joint surplus per ATTEMPT (walks count as zero) for
        # intra-population pacts vs ordinary pairs. Per-closed-deal would hide
        # attestation's actual benefit — truthful reservations close the thin
        # deals bluffers kill, so the lift is volume, not fatter closes.
        if not house:
            joint = (out.surplus_seller + out.surplus_buyer) if out.deal else 0.0
            (self._peer_surplus_samples if out.peer
             else self._adv_surplus_samples).append(joint)
        if out.deal:
            if seller is not None:
                self._credit_deal(seller, out.surplus_seller,
                                  counterparty_surplus=out.surplus_buyer)
                if not house and self.cfg.credit_counterfactual and "scn" in m:
                    self._counterfactual_credit(seller, m, "seller", out.surplus_seller)
            if buyer is not None:
                self._credit_deal(buyer, out.surplus_buyer,
                                  counterparty_surplus=out.surplus_seller)
                if not house and self.cfg.credit_counterfactual and "scn" in m:
                    self._counterfactual_credit(buyer, m, "buyer", out.surplus_buyer)
            joint = out.surplus_seller + out.surplus_buyer
            if joint > self.record_surplus:
                self.record_surplus = joint
                yield self._ev("highlight", kind="record_surplus",
                               refs={"a": sid, "b": bid, "neg": m["neg"]},
                               blurb=f"{joint:.2f} joint surplus")
        else:
            # walks: no income; credit a near-zero outcome so scorecards learn
            for ag, cp in ((seller, buyer), (buyer, seller)):
                if ag is not None:
                    ag.scorecard.update(ag.genome, 0.05)
        # rivalry bookkeeping
        if not house and seller is not None and buyer is not None:
            self._update_rivalry(sid, bid, out)

    def _credit_deal(self, a: Agent, surplus: float, counterparty_surplus: float) -> None:
        cfg = self.cfg
        surplus = max(0.0, surplus)
        income = surplus * cfg.energy_per_surplus
        self._add_energy(a, income, "income")
        self._cap(a)
        a.total_earned += income
        fam = a.genome.tactic_family
        self._gen_income[fam] = self._gen_income.get(fam, 0.0) + income
        self._gen_income_agent[a.id] = self._gen_income_agent.get(a.id, 0.0) + income
        a.deals_closed += 1
        a.scorecard.update(a.genome, min(1.0, surplus / max(cfg.scenario_span, 1e-6)))
        # reputation = EWMA of counterparty surplus (what partners walk away with)
        target = min(1.0, counterparty_surplus / max(cfg.scenario_span, 1e-6))
        a.reputation = 0.7 * a.reputation + 0.3 * target

    def _rivalry(self, a: int, b: int) -> Optional[dict]:
        key = (min(a, b), max(a, b))
        r = self.rivalry.get(key)
        if r and r["meetings"] >= 2:
            return {"meetings": r["meetings"],
                    "series": [r["wins"].get(key[0], 0), r["wins"].get(key[1], 0)]}
        return None

    def _update_rivalry(self, sid: int, bid: int, out: ex.NegOutcome) -> None:
        key = (min(sid, bid), max(sid, bid))
        r = self.rivalry.setdefault(key, {"meetings": 0, "wins": {key[0]: 0, key[1]: 0}})
        r["meetings"] += 1
        if out.deal:
            winner = sid if out.surplus_seller >= out.surplus_buyer else bid
            r["wins"][winner] = r["wins"].get(winner, 0) + 1
        # normalize wins access
        r["wins"] = {k: r["wins"].get(k, 0) for k in (key[0], key[1])}

    def _is_last_stand(self, aid: int) -> bool:
        a = self.agents.get(aid)
        if a is None:
            return False
        return a.energy < self.cfg.tax_per_gen * 1.1

    # ── upkeep: tax, staking upkeep, senescence, starvation ──
    def _upkeep_phase(self):
        cfg = self.cfg
        pop = len(self.agents)
        elastic = max(cfg.tax_elastic_k, min(1.0, pop / max(cfg.pop_cap, 1)))
        genomes = [a.genome for a in self.agents.values()]
        shares = sp.behavioral_shares(genomes)
        deltas = {}
        critical = []
        for a in list(self.agents.values()):
            share = shares.get(sp.behavioral_key(a.genome), 0.0)
            tax = cfg.tax_per_gen * (1.0 + cfg.crowd_tax_kappa * share) * elastic
            self._add_energy(a, -tax, "tax")
            if a.genome.staked:
                self._add_energy(a, -cfg.stake_upkeep, "upkeep")
            deltas[a.id] = -round(tax + (cfg.stake_upkeep if a.genome.staked else 0), 2)
            if 0 < a.energy < cfg.tax_per_gen * 1.2:
                critical.append(a.id)
        yield self._ev("energy.tick", deltas=deltas)
        for aid in critical:
            yield self._ev("agent.critical", id=aid, energy=round(self.agents[aid].energy, 1))
        # deaths: starvation + senescence (neutral null: random death at a
        # matched base rate, independent of energy/genome — drift only)
        for a in list(self.agents.values()):
            cause = None
            if self.neutral:
                if self.rng.random() < 0.06 or self._senescence_roll(a):
                    cause = "starvation" if self.rng.random() < 0.5 else "senescence"
            elif a.energy <= 0:
                cause = "starvation"
            elif self._senescence_roll(a):
                cause = "senescence"
            if cause:
                yield from self._kill(a, cause)

    def _senescence_roll(self, a: Agent) -> bool:
        cfg = self.cfg
        if a.age < cfg.life_expectancy_gens * 0.6:
            return False
        hazard = cfg.senescence_shape * np.exp((a.age - cfg.life_expectancy_gens) * 0.12)
        return bool(self.rng.random() < min(0.9, hazard))

    def _kill(self, a: Agent, cause: str):
        heirs = [c for c in a.children if c in self.agents]
        # founder = shallow lineage with living descendants -> dynasty event
        is_founder = a.lineage_depth == 0 and len(heirs) > 0
        # scatter a little energy to heirs (closed-economy flourish): a direct,
        # net-zero transfer; only the UN-transferred remainder is a death sink.
        transferred = 0.0
        if heirs and a.energy > 0:
            share = min(a.energy, 8.0) / len(heirs)
            for h in heirs:
                self.agents[h].energy += share
                transferred += share
                self._cap(self.agents[h])  # enforce the energy ceiling like income/auction do
        # record the ACTUAL energy leaving the system (can be negative when an
        # agent dies in starvation-debt — clamping to 0 would leak that debt).
        self.ledger["death"] += a.energy - transferred
        del self.agents[a.id]
        yield self._ev("agent.death", id=a.id, cause=cause, age=a.age,
                       lineage=a.lineage_depth, deals=a.deals_closed,
                       heirs=heirs, house=a.house)
        if is_founder:
            yield self._ev("highlight", kind="dynasty_founder_death",
                           refs={"id": a.id, "house": a.house},
                           blurb=f"{a.house} founder falls")

    # ── mating ──
    def _mating_phase(self):
        cfg = self.cfg
        ready = [a for a in self.agents.values()
                 if self.gen - a.last_mated >= cfg.mate_refractory_gens]
        if self.neutral:
            # eligibility independent of energy — a random slice (drift null)
            k = max(0, int(0.4 * len(ready)))
            idx = list(range(len(ready))); self.rng.shuffle(idx)
            eligible = [ready[i] for i in idx[:k]]
        else:
            eligible = [a for a in ready if a.energy >= cfg.mate_threshold]
        births_available = cfg.pop_cap - len(self.agents)
        if len(eligible) < 2 or births_available <= 0:
            return
        suitors = [ct.Suitor(a.id, a.genome, a.energy, a.reputation, a.scorecard,
                             a.genome.staked) for a in eligible]
        pollinator = flora.pollinator_for(self.era)
        pairs, round_ev = ct.build_matching(suitors, cfg, self.rng, pollinator)
        yield self._ev("mating.round", **round_ev)

        # Run courtships interleaved.
        gens = []
        pmeta = []
        for pa, pb in pairs:
            if births_available <= 0:
                break
            court_seed = self.cfg.seed * 7919 + self.gen * 104729 + pa.id
            gens.append(ct.run_courtship(pa, pb, cfg, self.sigma, self.rng, court_seed))
            pmeta.append((pa.id, pb.id))
            births_available -= 1

        outcomes: dict[int, ct.CourtOutcome] = {}
        active = list(range(len(gens)))
        while active:
            self.tick += 1
            still = []
            for k in active:
                try:
                    ev = next(gens[k])
                    yield self._ev(ev.pop("type"), **ev)
                    still.append(k)
                except StopIteration as e:
                    outcomes[k] = e.value
            active = still

        for k, out in outcomes.items():
            yield from self._resolve_birth(out)

    def _resolve_birth(self, out: ct.CourtOutcome):
        cfg = self.cfg
        pa = self.agents.get(out.parents[0])
        pb = self.agents.get(out.parents[1])
        if pa is None or pb is None:
            return
        if out.impasse or out.child_genome is None:
            self._add_energy(pa, -cfg.courtship_cost, "tax")
            self._add_energy(pb, -cfg.courtship_cost, "tax")
            return
        pa.last_mated = self.gen
        pb.last_mated = self.gen
        # endowment (internal transfer) + progressive birth tax (sink)
        endow = cfg.child_endowment_frac * (pa.energy + pb.energy) * 0.5
        pa.energy -= endow / 2
        pb.energy -= endow / 2
        for p in (pa, pb):
            btax = cfg.birth_tax_frac * max(0.0, p.energy - cfg.mate_threshold)
            self._add_energy(p, -btax, "birthtax")
        house = pa.house if self.rng.random() < 0.5 else pb.house
        lineage = max(pa.lineage_depth, pb.lineage_depth) + 1
        child = self._spawn(out.child_genome, house=house,
                            parents=(pa.id, pb.id), lineage=lineage,
                            energy=endow, scorecard=out.child_scorecard)
        pa.children.append(child.id)
        pb.children.append(child.id)
        yield self._ev("agent.birth", id=child.id, name=child.name, house=house,
                       parents=[pa.id, pb.id], genome=child.genome.to_dict(),
                       endowment=round(endow, 1), species=child.species,
                       lineage=lineage)
        if lineage >= 3:
            yield self._ev("highlight", kind="dynasty_founded",
                           refs={"id": child.id, "house": house, "depth": lineage},
                           blurb=f"House {house} reaches depth {lineage}")

    # ── auction set piece ──
    def _auction_phase(self):
        agents = list(self.agents.values())
        yield from auc.run_auction(self, agents)

    # ── era ──
    def _era_phase(self):
        cfg = self.cfg
        dwell = self.gen - self.era_started
        if self.era_interp < 1.0:
            self.era_interp = min(1.0, self.era_interp + 1.0 / max(1, cfg.era_interp_gens))
        # semi-Markov: eligible to flip only after min dwell
        if dwell >= cfg.era_dwell_min:
            diversity = self._diversity()
            hazard = 0.12 + cfg.era_diversity_nudge * max(0.0, 0.5 - diversity)
            if self.rng.random() < hazard:
                self.prev_era = self.era
                choices = [e for e in sc.ERAS if e != self.era]
                self.era = choices[int(self.rng.integers(len(choices)))]
                self.era_started = self.gen
                self.era_interp = 0.0
                self.sigma = cfg.sigma_shock
                # archive current champions into hall of fame for the prev era
                self._archive_champions(self.prev_era)
                poll = flora.pollinator_for(self.era)
                yield self._ev("era.change", era=self.era,
                               label=sc.ERA_LABELS[self.era],
                               optimal_knob=sc.era_optimal_knob(self.era),
                               pollinator={"name": poll["name"], "glyph": poll["glyph"]})
                yield self._ev("highlight", kind="era_flip",
                               refs={"era": self.era},
                               blurb=f"the market turns: {sc.ERA_LABELS[self.era]}")
                return
        # sigma decays back to stable after the shock window
        if self.gen - self.era_started >= cfg.sigma_shock_gens:
            self.sigma = cfg.sigma_stable

    def _diversity(self) -> float:
        genomes = [a.genome for a in self.agents.values()]
        if len(genomes) < 2:
            return 1.0
        fvs = np.array([g.feature_vector() for g in genomes])
        return float(np.mean(np.std(fvs, axis=0)))

    def _archive_champions(self, era: str) -> None:
        top = sorted(self.agents.values(), key=lambda a: a.energy, reverse=True)[:3]
        self.hall_of_fame[era] = [(a.genome, a.house) for a in top] or self.hall_of_fame[era]

    # ── census / species / leaderboard ──
    def _census_phase(self):
        agents = list(self.agents.values())
        if not agents:
            return
        assign, summaries = self.species.update(
            [(a.id, a.genome.feature_vector()) for a in agents])
        for a in agents:
            a.species = assign.get(a.id, -1)
        yield self._ev("species.update", species=summaries)

        staked_frac = np.mean([1.0 if a.genome.staked else 0.0 for a in agents])
        mean_knob = float(np.mean([a.genome.pareto_knob for a in agents]))
        # strategy performance: who is winning, by tactic family (drives the
        # renderer's "strategies this era" panel — evolution made watchable)
        fam: dict[str, dict] = {}
        for a in agents:
            f = fam.setdefault(a.genome.tactic_family, {"n": 0, "e": 0.0})
            f["n"] += 1
            f["e"] += a.energy
        # income = THIS generation's per-capita earnings by tactic — the honest
        # "who's winning" number (mean_e is cumulative wealth, luck-confounded)
        tactics = {k: {"n": v["n"], "mean_e": round(v["e"] / v["n"], 1),
                       "income": round(self._gen_income.get(k, 0.0) / v["n"], 2)}
                   for k, v in fam.items()}
        peer_prem = float(np.mean(self._peer_surplus_samples)) if self._peer_surplus_samples else None
        adv_prem = float(np.mean(self._adv_surplus_samples)) if self._adv_surplus_samples else None
        # Price equation (Koza): Cov(trait, this-gen income) — the un-cherry-picked
        # selection differential on the SNHP knob. And the strategic-softening
        # detector: energy rising while aggression falls + everyone closing is
        # collapse dressed as prosperity, not skill.
        inc = np.array([self._gen_income_agent.get(a.id, 0.0) for a in agents])
        knobs = np.array([a.genome.pareto_knob for a in agents])
        aggr = float(np.mean([(a.genome.walk_margin + a.genome.open_aggression) / 2 for a in agents]))
        mean_e = float(np.mean([a.energy for a in agents]))
        price_cov = float(np.cov(knobs, inc)[0, 1]) if len(agents) > 3 and np.std(inc) > 1e-9 else 0.0
        softening = bool(mean_e > self._prev_energy + 0.5 and aggr < self._prev_aggr - 0.002)
        self._prev_aggr = aggr
        self._prev_energy = mean_e
        # causal attestation lift from the paired probe (rolling window)
        attest_lift = attest_n = None
        if len(self._attest_pairs) >= 8:
            on = float(np.mean([p[0] for p in self._attest_pairs]))
            off = float(np.mean([p[1] for p in self._attest_pairs]))
            if off > 1e-6:
                attest_lift = round((on - off) / off, 3)
                attest_n = len(self._attest_pairs)
        yield self._ev("census", pop=len(agents), era=self.era,
                       staked_frac=round(float(staked_frac), 3),
                       mean_knob=round(mean_knob, 3),
                       era_optimal_knob=sc.era_optimal_knob(self.era),
                       mean_energy=round(float(np.mean([a.energy for a in agents])), 1),
                       n_species=len(summaries),
                       peer_premium=(round(peer_prem, 4) if peer_prem is not None else None),
                       adv_premium=(round(adv_prem, 4) if adv_prem is not None else None),
                       peer_n=len(self._peer_surplus_samples),
                       attest_lift=attest_lift, attest_n=attest_n,
                       price_cov=round(price_cov, 4), mean_aggression=round(aggr, 3),
                       softening=softening,
                       tactics=tactics,
                       genes=self._mean_genes(agents))
        self._peer_surplus_samples.clear()
        self._adv_surplus_samples.clear()

        top = sorted(agents, key=lambda a: a.energy, reverse=True)[:6]
        yield self._ev("leaderboard", top=[
            {"id": a.id, "name": a.name, "house": a.house, "energy": round(a.energy, 1),
             "species": a.species, "lineage": a.lineage_depth} for a in top])

        # Bloom of the Generation: the fairest flower the season's pollinator
        # found — pollinator-aligned, affordable (costly signal), and a touch of
        # rarity. The full-screen payoff; beauty = the winning strategy, seen.
        yield from self._bloom_of_generation(agents)

        yield self._ev("gen.end", gen=self.gen, pop=len(agents), era=self.era)

    def _bloom_of_generation(self, agents):
        poll = flora.pollinator_for(self.era)
        mean_fv = np.mean([a.genome.feature_vector() for a in agents], axis=0)
        best, best_score = None, -1.0
        for a in agents:
            rarity = float(min(1.0, np.linalg.norm(a.genome.feature_vector() - mean_fv)
                               / np.sqrt(len(mean_fv))))
            s = flora.beauty_score(a.genome, a.energy, poll, self.cfg.mate_threshold, rarity)
            if s > best_score:
                best_score, best = s, (a, rarity)
        if best is None:
            return
        a, rarity = best
        yield self._ev("bloom", id=a.id, name=a.name, house=a.house,
                       genome=a.genome.to_dict(), flower=flora.flower_dict(a.genome),
                       beauty=round(best_score, 3), rarity=round(rarity, 3),
                       pollinator={"name": poll["name"], "glyph": poll["glyph"]},
                       species=flora.SPECIES.get(a.genome.tactic_family, "tulip"))

    def _mean_genes(self, agents) -> dict:
        gv = np.mean([a.genome.feature_vector() for a in agents], axis=0)
        return {"pareto_knob": round(float(gv[0]), 3),
                "open_aggression": round(float(gv[1]), 3),
                "walk_margin": round(float(gv[2]), 3),
                "patience": round(float(gv[3]), 3)}

    # ── population floor: hall-of-fame reseed as immigration ──
    def _floor_phase(self):
        cfg = self.cfg
        while len(self.agents) < cfg.pop_floor:
            era_pool = self.hall_of_fame.get(self.era) or []
            if era_pool:
                g, house = era_pool[int(self.rng.integers(len(era_pool)))]
            else:
                keys = list(ARCHETYPES.keys())
                house = keys[int(self.rng.integers(len(keys)))]
                g = ARCHETYPES[house]
            a = self._spawn(g, house=house, parents=(), lineage=0)
            self.ledger["immigration"] += a.energy
            yield self._ev("immigration", id=a.id, name=a.name, house=house,
                           genome=g.to_dict(), reason="population_floor")

    # ── ledger check (for the conservation test) ──
    def energy_balance(self) -> dict:
        total = sum(a.energy for a in self.agents.values())
        L = self.ledger
        expected = (self.cfg.energy_start * self.cfg.pop_start
                    + L["income"] + L["immigration"]
                    - L["tax"] - L["upkeep"] - L["birthtax"] - L["death"] - L["capclamp"]
                    + L["auction"])
        return {"total": total, "expected": expected, "ledger": dict(L)}

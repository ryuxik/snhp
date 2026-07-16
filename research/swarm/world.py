"""The physical world (SPEC.md v4.0).

Arm-agnostic by construction: every state change flows through the same
physics methods, so coordination arms differ only in the deals they strike.

v4 additions (all panel-mandated, review/PANEL_V4.md):
- Two companies (12 twin-fleet drones each), each owning one refinery, on a
  map that is reflection-symmetric about y=16 → per-company ledger claims
  have a placebo (symmetry ⇒ expected difference 0).
- Refining tariff τ per company, assessed ONCE at refine time; cargo carries
  mining-company provenance so laundering ≠ compliance in the ledger.
- Company-neutral charger tie-break (seeded priority permutation) +
  per-company queue-wait logging.
- `preset="v3"` reproduces the v3 single-refinery world through this same
  code path (bridge runs).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np

GRID = 32
STOCK_PER_SOURCE = 60
TOTAL_STOCK = 2 * STOCK_PER_SOURCE
BATTERY_MAX = 100.0
LOADED_MULT = 0.6                   # λ: a loaded step costs eff*(1+λ)
CHARGE_RATE = 4.0
CHARGE_SLOTS = 2
TRANSFER_LOSS = 0.25                # energy lost per robot-to-robot hop
R_COMM = 2                          # Chebyshev interaction radius
RESCUE_FLOOR = 5.0                  # battery above this un-strands a robot
V_DELIVER = 10.0                    # credit per unit refined at OWN refinery
P_STRAND = 15.0                     # Φ penalty when charger is out of reach
FUTURE_DISCOUNT = 0.5               # Φ weight on future-trip value
TXN_COST = 0.05                     # per-side battery cost of striking a deal
DEAL_PAUSE = 3                      # ticks BOTH parties hold position while an
                                    # executed exchange physically transfers
                                    # (v8 physics: deals cost time, not just
                                    # paperwork — founder review 2026-07-15)
HAZARD_SCALE = 8.0                  # hazard sigmoid softness (-hz arms)
EV_INIT = 0.3                       # initial energy shadow price (endogenous
EV_MIN, EV_MAX = 0.05, 1.0          # thereafter: lagged ∂Φ/∂battery, clamped)
TARGET_MARGIN = 1.5                 # delivery-target hysteresis (score units)

GUEST_RATE = 2.0                    # charge rate at a rival's charger (v5)
GUEST_PENALTY = 6                   # routing penalty (cells) for guest charging
LIE_LAMBDA = 0.5                    # v6: BATNA inflation aggressiveness
DISTRUST_DELTA = 0.25               # v6: margin demanded vs unattested partners
R_SENSE = 3                         # v10a: Chebyshev radius within which a
                                    # robot refreshes its company's belief
RIVAL_ALPHA = 0.2                   # v10b: exp-smoothing of the observed
                                    # rival depletion rate (units/tick)
CLAIM_WINDOW = 150                  # v12 K2: ticks an ARRIVAL rock is minable
                                    # only by its quadrant's claim-holder
R_RADIO = 6                         # v14 (column O): Chebyshev radius within
                                    # which same-company fleet-mates gossip
                                    # fresher belief entries (short radio); the
                                    # ladder also runs r_radio=2 (contact-only)

PRESETS = {
    # sources, refineries [(pos, owner)], chargers [(pos, owner)]
    "v5": dict(sources=None,        # mirrored asteroid field, seeded in init
               refineries=[((26, 6), 0), ((26, 26), 1)],
               chargers=[((12, 10), 0), ((22, 12), 0),
                         ((12, 22), 1), ((22, 20), 1)],
               companies=2),
    "v4": dict(sources=[(6, 6), (6, 26)],
               refineries=[((26, 6), 0), ((26, 26), 1)],
               chargers=[((16, 16), None)], companies=2),
    "v3": dict(sources=[(10, 6), (6, 26)],
               refineries=[((26, 6), None)],
               chargers=[((22, 6), None)], companies=1),
}


def manhattan(p, q) -> int:
    return abs(p[0] - q[0]) + abs(p[1] - q[1])


def toward(pos, target):
    """One deterministic Manhattan step from pos toward target (x first)."""
    x, y = pos
    if x != target[0]:
        return (x + (1 if target[0] > x else -1), y)
    if y != target[1]:
        return (x, y + (1 if target[1] > y else -1))
    return pos


@dataclass
class Robot:
    rid: int
    pos: tuple
    battery: float
    cap: int
    eff: float
    sector: int                     # assigned source index
    company: int = 0
    load: int = 0
    load_prov: list = field(default_factory=lambda: [0, 0])  # by mining company
    stranded: bool = False
    delivered: int = 0
    credit: float = 0.0             # delivery credit actually earned
    charge_queued_at: int = -1
    ev: float = EV_INIT             # endogenous energy shadow price (lagged)
    target_ref: int | None = None   # delivery-target hysteresis state
    liar: bool = False              # v6: inflates reported BATNA by LIE_LAMBDA
    attested: bool = False          # v6: reports verifiably true (signed books)
    gauge_bias: float = 0.0         # v7: persistent battery-gauge miscalibration
    busy_until: int = -1            # v8: docked mid-exchange until this tick
    mine_rate: int = 1              # v10c: units/tick trait (consumed only
                                    # when World.mine_trait; drawn 1..3)
    mined_units: int = 0            # v13: units this robot mined itself
    received_units: int = 0         # v13: units received IN via deals/transfers
                                    # (delivered_units is the existing .delivered).
                                    # Pure bookkeeping — no RNG, no decision — so
                                    # the middleman metric never perturbs a bit.
    parcels: list = field(default_factory=list)   # v17 (column P): unit-
                                    # granularity cargo lineage — a FIFO of
                                    # {origin rock, hop count, chain} dicts, one
                                    # per carried unit. Populated ONLY under
                                    # World.lineage (parcels-off leaves it an empty
                                    # list, untouched — bit-identical, like
                                    # load_prov). Off ⇒ no code runs; on consumes
                                    # no RNG and mutates no physics.

    def bat(self) -> float:
        """BELIEVED battery — what every decision layer consumes. Physics
        (moves, transfers, stranding) reads .battery, the truth."""
        return float(min(BATTERY_MAX, max(0.0, self.battery * (1.0 + self.gauge_bias))))

    def step_cost(self) -> float:
        return self.eff * (1.0 + (LOADED_MULT if self.load > 0 else 0.0))


class World:
    def __init__(self, n_robots: int = 24, sigma: float = 1.0, seed: int = 0,
                 hazard_phi: bool = False, preset: str = "v4",
                 tau: tuple = (0.0, 0.0), internalize_tariffs: bool = False,
                 freeze_ev: float | None = None,
                 liar_frac: float = 0.0, defended: bool = False,
                 self_noise: float = 0.0, self_margin: bool = False,
                 grid: int = GRID, life_pricing: bool = False,
                 strand_cap: float = 0.0, belief_mode: bool = False,
                 race_pricing: bool = True, mine_trait: bool = False,
                 r_sense: int = R_SENSE,
                 dynamic_field: bool = False, contested: bool = False,
                 scouting: bool = False, map_trading: bool = False,
                 prospect_claims: bool = False,
                 consensus_cost: bool = False,
                 gossip: bool = False, r_radio: int = R_RADIO,
                 lineage: bool = False):
        self.rng = np.random.RandomState(seed)
        self.hazard_phi = hazard_phi
        self.preset = preset
        # v13 (column L): density-fixed scale. n_robots drives the scaled
        # asteroid count, stock pin and charger count (all via _gen_asteroids /
        # _scaled_chargers); consensus_cost lengthens ONLY team-family deal
        # pauses (arms.py TeamArm.deal_pause). Both reduce to today's world at
        # n_robots==24 (fingerprint-verified) — the scale paths are gated on
        # n_robots != 24 so every pre-L column stays bit-identical.
        self.n_robots = n_robots
        self.consensus_cost = consensus_cost
        # v10: field beliefs + priced race + mine-rate trait. ALL default
        # off ⇒ every pre-v10 column is bit-identical (suite-verified).
        self.belief_mode = belief_mode
        self.race_pricing = race_pricing
        self.mine_trait = mine_trait      # set BEFORE spawns: gates a draw
        self.r_sense = r_sense
        # v14 (column O): communication locality. gossip default off ⇒ every
        # pre-v14 column is bit-identical (suite-verified). Gossip removes the
        # company-wide free radio: beliefs become PER-ROBOT (indexed by rid via
        # _bx) and same-company fleet-mates within Chebyshev r_radio flood each
        # other's fresher entries once per tick (_gossip_step). belief_mode with
        # gossip OFF is the free-radio control — unchanged company-shared map.
        assert not (gossip and not belief_mode), \
            "gossip requires belief_mode (no map ⇒ nothing to propagate)"
        self.gossip = gossip
        self.r_radio = r_radio
        # v11 (column J): the moving field. Both default off ⇒ every pre-v11
        # column stays bit-identical (suite-verified). `contested` reshapes
        # the INITIAL field (read by _gen_asteroids, so set before it runs);
        # `dynamic_field` schedules arrivals/departures drawn from a DEDICATED
        # RandomState so the main stream is never perturbed.
        self.dynamic_field = dynamic_field
        self.contested = contested
        # v12 (column K): pricing the unknown. All three default off ⇒ every
        # pre-v12 column stays bit-identical (suite-verified). K0 scouting needs
        # a belief map to have any staleness to patrol; K2 claims gate ARRIVALS,
        # which only exist on a moving field.
        assert not (scouting and not belief_mode), \
            "scouting requires belief_mode (no map ⇒ no staleness to patrol)"
        assert not (prospect_claims and not dynamic_field), \
            "prospect_claims requires dynamic_field (claims gate ARRIVALS)"
        self.scouting = scouting
        self.map_trading = map_trading
        self.prospect_claims = prospect_claims
        self.scout_ticks = 0              # K0: robot-ticks spent scouting
        self._oracle_override = False     # phi_true_field: audit vs TRUE field
        self._live_sense = True           # drive/world phase: sensing is live;
                                          # frozen during encounters (v10)
        # v8 geometry (column G): facility layout scales with grid size;
        # stock/robots/batteries fixed, so density varies purely through
        # distance. sc==1 leaves every draw and position bit-identical.
        self.grid = grid
        sc = grid / GRID
        _P = (lambda p: (round(p[0] * sc), round(p[1] * sc))) if sc != 1 \
            else (lambda p: tuple(p))
        self.life_pricing = life_pricing   # v9: price drones by remaining career
        self.strand_cap = strand_cap       # v9: exogenous replacement capital
        cfg = PRESETS[preset]
        self.refineries = [_P(p) for p, _ in cfg["refineries"]]
        self.ref_owner = [o for _, o in cfg["refineries"]]
        self.chargers, self.charger_owner = self._scaled_chargers(
            cfg["chargers"], _P)
        self.n_companies = cfg["companies"]
        # v5 fleets launch lean (mean 40): with 4 chargers and a scattered
        # field, abundance made coordination irrelevant at mean 60 (smoke:
        # 120/120 by tick 143 with 7 deals). Leaner batteries restore real
        # charging economics without v4's single-bottleneck death world.
        if preset == "v5":
            self._b_mean, self._b_spread, self._b_lo = 0.4 * BATTERY_MAX, 30.0, 8.0
        else:   # v3/v4 draws unchanged — committed sweeps must stay reproducible
            self._b_mean, self._b_spread, self._b_lo = 0.6 * BATTERY_MAX, 40.0, 10.0
        if cfg["sources"] is None:          # v5: mirrored asteroid field
            self.sources, stocks = self._gen_asteroids()
            self.stock = stocks
        else:
            self.sources = [tuple(s) for s in cfg["sources"]]
        self.tau = tuple(tau)
        self.internalize_tariffs = internalize_tariffs
        self.freeze_ev = freeze_ev
        if not hasattr(self, "stock"):
            self.stock = [STOCK_PER_SOURCE, STOCK_PER_SOURCE]
        self.total_stock = sum(self.stock)
        # v10a: per-company field beliefs, initialized to TRUE stock at t=0
        # (companies surveyed the field once at launch — isolates STALENESS
        # as the treatment, not an arbitrary prior). Belief >= truth always:
        # stock only falls between observations, so staleness is purely
        # optimistic and a believed-empty field really is empty (no
        # under-estimate deadlock). Allocated unconditionally (cheap ints,
        # no RNG); consumed only through stock_belief() when belief_mode.
        n_src = len(self.sources)
        # v14 (column O): under gossip the belief/last_seen/rival_rate maps are
        # PER-ROBOT (n_robots arrays, indexed by rid); off, they are the two
        # company-shared free-radio maps (bit-identical to every pre-v14 column).
        # own_mined is a PHYSICAL company aggregate — always company-indexed;
        # _own_mined_seen (the rival-rate baseline) rides with the belief map so
        # a gossiped entry carries the reference against which the next observed
        # depletion is scored (see _gossip_step / _observe_idx).
        n_belief = n_robots if gossip else 2
        self.belief = [list(self.stock) for _ in range(n_belief)]
        self.last_seen = [[0] * n_src for _ in range(n_belief)]
        self.rival_rate = [[0.0] * n_src for _ in range(n_belief)]   # units/tick
        self.own_mined = [[0] * n_src for _ in range(2)]      # cumulative (co)
        self._own_mined_seen = [[0] * n_src for _ in range(n_belief)]
        # v11 provenance: units picked per asteroid (both companies pooled).
        # Allocated + incremented unconditionally — pure bookkeeping, no RNG,
        # no decision — so the dynamic_field=False path stays bit-identical.
        self.mined_from = [0] * n_src
        self.stock_lost = 0                 # v11: true stock erased by departures
        # v12 K2: quadrant prospecting claims. The grid halves into 4 quadrants
        # (quadrant()); each company holds 2 — init [0,1,0,1], deterministic.
        # An ARRIVAL rock in a quadrant is minable ONLY by the holder company
        # until arrival_t + CLAIM_WINDOW (belief gate in stock_belief + physics
        # gate in pick). Claims are FIXED this column (the registered fallback —
        # see run.py/SPEC): never traded, so no synced-claim-view is needed and
        # evaluated Φ == executed Φ holds trivially over a constant claim map.
        # Both allocated unconditionally (cheap, no RNG); arrival_t is populated
        # in _field_arrival and read only by _claim_gated, so a non-prospect
        # world is bit-identical.
        self.claim_owner = [0, 1, 0, 1]
        self.arrival_t: dict[int, int] = {}
        self.arrival_indices: list[int] = []   # source idx of each arrival rock
        self.field_log: list[dict] = []     # arrival/departure record (separate
                                            # from event_log: keeps xfers/border
                                            # metrics counting physical exchanges)
        self._field_events: list[dict] = []
        self._field_next = 0
        if dynamic_field:
            # DEDICATED stream (seed+7919): pre-draw a fixed schedule of 8
            # arrivals ~U(200,2300) and 4 departures ~U(400,2300), sorted.
            # Positions/stocks/targets are drawn from this same stream at FIRE
            # time (they depend on the live field), never from self.rng.
            self._field_rng = np.random.RandomState(seed + 7919)
            arr = sorted(float(self._field_rng.uniform(200, 2300)) for _ in range(8))
            dep = sorted(float(self._field_rng.uniform(400, 2300)) for _ in range(4))
            evs = ([dict(t=t, kind="arrival") for t in arr]
                   + [dict(t=t, kind="departure") for t in dep])
            evs.sort(key=lambda e: e["t"])
            self._field_events = evs
        self.guest_charged = 0.0            # energy served to rival fleets
        self.delivered = 0
        self.delivered_matrix = [[0, 0], [0, 0]]     # [miner co][refiner owner]
        self.foreign_refined = 0    # units a robot refined at the OTHER
                                    # company's refinery (robot-co channel;
                                    # laundering = matrix off-diag beyond this)
        self.company = [dict(credit=0.0, tariffs_earned=0.0, tariffs_paid=0.0,
                             queue_wait=0) for _ in range(2)]
        self.tick = 0
        self.energy_charged = 0.0
        self.deal_log: list[dict] = []
        self.event_log: list[dict] = []
        # v17 (column P): cargo-lineage diagnosis. All three default off/zero and
        # are PURE bookkeeping — no RNG, no physics — so every non-lineage column
        # stays bit-identical (charge_served_slots is an aggregate like
        # energy_charged; delivered_parcels/robot.parcels are populated only under
        # `lineage`). charge_served_slots counts slot-fills for the charger duty
        # cycle; delivered_parcels retires each delivered unit's (origin, hops,
        # tick, deliverer, chain).
        self.lineage = lineage
        self.charge_served_slots = 0
        self.delivered_parcels: list[dict] = []

        self.robots: list[Robot] = []
        if self.n_companies == 2:
            self._spawn_twin_fleets(n_robots, sigma)
        else:
            self._spawn_v3(n_robots, sigma)
        self.energy_initial = sum(r.battery for r in self.robots)
        self.energy_at_last_delivery = self.energy_initial
        # company-neutral charger tie-break (panel M2): seeded priority
        self._charge_prio = list(self.rng.permutation(len(self.robots)))
        # v6: liar assignment, company-balanced (placebo preserved); in the
        # DEFENDED condition every honest robot attests (liars can't while
        # lying — attestation IS verifiable truth)
        self.defended = defended
        self.self_margin = self_margin
        if self_noise > 0 or liar_frac > 0:
            # v7: twin-mirrored gauge miscalibration. The stream is consumed
            # in EVERY v6/v7 world (scaled by s7, zero at s7=0) so the liar
            # permutation below stays seed-paired across self-noise cells —
            # review: conditional draws gave the s7=0 cell different liars.
            half = len(self.robots) // 2
            biases = self.rng.normal(0.0, 1.0, half) * self_noise
            for k in range(half):
                self.robots[k].gauge_bias = float(biases[k])
                if half + k < len(self.robots):
                    self.robots[half + k].gauge_bias = float(biases[k])
        if liar_frac > 0:
            per_co = round(liar_frac * len(self.robots) / 2)
            for c in (0, 1):
                ids = [r.rid for r in self.robots if r.company == c]
                for rid in self.rng.permutation(ids)[:per_co]:
                    self.robots[rid].liar = True
        if defended:
            for r in self.robots:
                r.attested = not r.liar

    # mean-preserving draws (v2 review M1): σ widens spread, never the mean
    def _draw(self, sigma):
        u = self.rng.uniform
        cap = int(np.clip(round(3 + sigma * u(-2, 2)), 1, 5))
        eff = float(np.clip(1.0 + sigma * u(-0.5, 0.5), 0.5, 1.5))
        b0 = float(np.clip(self._b_mean + sigma * u(-self._b_spread, self._b_spread),
                           self._b_lo, BATTERY_MAX))
        pos = (int(u(1, self.grid)), int(u(1, self.grid)))   # == GRID at sc=1
        # v10c: mine-rate trait, mean-preserving (mean 2). Drawn at the END
        # of the sequence AND gated on mine_trait so pre-v10 worlds consume
        # the stream identically (the v7 RNG-stream lesson: conditional
        # draws de-pair seeds across cells — here the flag IS the cell).
        mine = int(np.clip(round(2 + sigma * u(-1, 1)), 1, 3)) \
            if self.mine_trait else 1
        return cap, eff, b0, pos, mine

    def _scaled_chargers(self, base, _P):
        """Charger geometry. At n_robots==24 (EVERY pre-v13 run, any preset)
        this is exactly the preset list scaled by grid — bit-identical.

        v13 (column L): charger count scales as 4·N/24 at fixed density. The v5
        motif is 2 mirror-pairs (company-0 chargers in the top half, their y=grid/2
        reflections owned by company 1); the scaled field tiles 2·N/24 such pairs
        on a company-balanced lattice over the interior, owners alternating so
        per-company counts stay equal and the twin-fleet mirror placebo survives.
        Consumes no RNG; only the n_robots != 24 branch changes any bit."""
        scaled_pos = [_P(p) for p, _ in base]
        scaled_own = [o for _, o in base]
        if self.n_robots == 24:
            return scaled_pos, scaled_own
        n_ch = 4 * self.n_robots // 24            # 16 at N=96, 40 at N=240
        n_pairs = n_ch // 2                        # mirror pairs (top/bottom)
        cols = int(np.ceil(np.sqrt(n_pairs)))
        rows = int(np.ceil(n_pairs / cols))
        g = self.grid
        pos, own = [], []
        for k in range(n_pairs):
            c, rw = k % cols, k // cols
            x = int(round(g * (0.12 + 0.76 * (c + 0.5) / cols)))
            y = int(round(g * (0.12 + 0.30 * (rw + 0.5) / max(rows, 1))))
            pos.append((x, y)); own.append(0)         # top half → company 0
            pos.append((x, g - y)); own.append(1)     # mirror  → company 1
        return pos, own

    def _gen_asteroids(self):
        """v5: 5 mirror-pairs of asteroids (reflection about y=16), stocks
        equal within a pair, total pinned to 2×TOTAL_STOCK (double workload:
        the rich stage needs a long game or coordination is decorative).
        Non-identical by construction: position and richness vary per pair.

        v13 (column L): at n_robots != 24 the count scales to 5·N/24 pairs and
        the total to 2×TOTAL_STOCK·N/24 (= 10·N units) at FIXED density. Because
        density is fixed, mean inter-rock spacing is N-invariant, so the
        min-separation stays CONSTANT (=5) rather than scaling with the grid —
        a grid-scaled separation would demand impossible packing as the count
        grows. At N=24 the count/total/min-sep all reduce to today's values
        (n_robots==24 keeps the legacy 5·sc separation for column G runs)."""
        sc = self.grid / GRID
        taken = set(self.refineries) | set(self.chargers)
        if self.contested:
            # v11 (column J): 10 rocks drawn INDEPENDENTLY in a central band
            # y ∈ [10·sc, 22·sc] — no mirroring, so both companies mine the
            # SAME overlapping field and the rival-depletion race actually
            # bites. The twin-fleet mirror placebo (per-company ledger
            # symmetry ⇒ expected difference 0) does NOT apply in this mode:
            # geography is deliberately asymmetric. Uses self.rng (initial
            # world generation, like the mirrored path) — the dedicated
            # dynamic-field stream is reserved for arrivals/departures.
            pos = []
            while len(pos) < 10:
                x = int(self.rng.uniform(3 * sc, 29 * sc))
                y = int(self.rng.uniform(10 * sc, 22 * sc))
                p_ = (x, y)
                if any(manhattan(p_, f) < 3 for f in taken):      # ≥3 from
                    continue                                      # facilities
                if any(manhattan(p_, q) < 3 for q in pos):
                    continue
                pos.append(p_)
            raw = [int(self.rng.uniform(6, 19)) for _ in range(10)]
            scale = 2 * TOTAL_STOCK / sum(raw)
            stocks = [max(4, round(r * scale)) for r in raw]
            stocks[0] += 2 * TOTAL_STOCK - sum(stocks)            # pin the total
            return pos, stocks
        n_pairs = 5 * self.n_robots // 24                # 5 at N=24
        half_total = TOTAL_STOCK * self.n_robots // 24   # TOTAL_STOCK at N=24
        min_sep = 5 * sc if self.n_robots == 24 else 5.0
        # At large n_pairs the band packs near-saturated, where naive
        # rejection sampling degrades catastrophically (the last placements
        # almost never find a valid gap — N=240 world construction hung for
        # minutes here). Cap the failed attempts and relax the separation on
        # saturation. This branch is UNREACHABLE at N=24 (5 points in a roomy
        # band never exhaust the cap), so the legacy draw sequence — and every
        # pre-L column's bit-exactness — is preserved.
        pos, sep, misses = [], min_sep, 0
        while len(pos) < n_pairs:
            x = int(self.rng.uniform(3 * sc, 29 * sc))   # bounds scale; at
            y = int(self.rng.uniform(3 * sc, 13 * sc))   # sc=1 draws unchanged
            p_ = (x, y)
            if p_ in taken or any(manhattan(p_, q) < sep for q in pos):
                misses += 1
                if misses > 64 * n_pairs:                # saturated → ease off
                    sep = max(2.0, sep * 0.85)
                    misses = 0
                continue
            pos.append(p_)
            misses = 0
        raw = [int(self.rng.uniform(6, 19)) for _ in range(n_pairs)]
        scale = half_total / sum(raw)
        stocks = [max(4, round(r * scale)) for r in raw]
        stocks[0] += half_total - sum(stocks)            # pin the total
        sources = pos + [(x, self.grid - y) for x, y in pos]  # mirrors idx+n
        return sources, stocks + list(stocks)

    def best_claim(self, r) -> int:
        """Policy claim choice: richest-per-distance stocked asteroid.
        v10a: scores what the robot's company BELIEVES, not the field."""
        best, best_score = r.sector, -1.0
        for i, src in enumerate(self.sources):
            s = self.stock_belief(r, i)
            if s <= 0:
                continue
            score = s / (manhattan(r.pos, src) + 4.0)
            if score > best_score:
                best, best_score = i, score
        return best

    # ── v10a/b: company field beliefs (v14: per-robot under gossip) ──────
    def _bx(self, r) -> int:
        """Belief-array index for robot r: its OWN rid under gossip (per-robot
        maps), else its company (the free-radio shared map). Reduces to the
        company index when gossip is off ⇒ every pre-v14 belief read is
        bit-identical (robots are appended in rid order, so rid == list index)."""
        return r.rid if self.gossip else r.company

    def _in_sense_range(self, pos, i) -> bool:
        src = self.sources[i]
        return max(abs(pos[0] - src[0]), abs(pos[1] - src[1])) <= self.r_sense

    def quadrant(self, pos) -> int:
        """v12 K2: which grid-half quadrant a position sits in (0..3)."""
        half = self.grid / 2
        return 2 * int(pos[1] >= half) + int(pos[0] >= half)

    def _claim_gated(self, co: int, i: int) -> bool:
        """v12 K2: True iff asteroid i is a still-claimed ARRIVAL sitting in a
        quadrant company `co` does NOT hold — a non-holder then sees 0 stock
        (belief gate) and mines 0 (pick gate) until arrival_t + CLAIM_WINDOW.
        Original (non-arrival) rocks and expired windows are never gated."""
        t0 = self.arrival_t.get(i)
        if t0 is None or self.tick >= t0 + CLAIM_WINDOW:
            return False
        return self.claim_owner[self.quadrant(self.sources[i])] != co

    def stock_belief(self, r, i):
        """Stock of asteroid i as robot r's COMPANY believes it. Every
        decision layer routes here; physics (pick, conservation) reads
        self.stock, the truth. During the drive/world phase a robot within
        R_SENSE reads the rock live (without this, the oracle's INTRA-tick
        omniscience makes the perfect-sensing placebo unpinnable); during
        the encounter phase beliefs are frozen — evaluated Φ == executed Φ
        depends on it."""
        if not self.belief_mode or self._oracle_override:
            return self.stock[i]
        # v12 K2 belief-side gate: a non-holder cannot believe in a claimed
        # arrival during its window, so best_claim skips it and the fleet never
        # routes there (documented gate). Placed BEFORE live-sense so a
        # non-holder flying past does not even record it as routable stock.
        if self.prospect_claims and self._claim_gated(r.company, i):
            return 0
        if self._live_sense and self._in_sense_range(r.pos, i):
            if self.gossip:
                self._observe_r(r, i)          # v14: writes r's OWN map
            else:
                self._observe(r.company, i)
        return self.belief[self._bx(r)][i]

    def _observe_idx(self, bx: int, co: int, i: int) -> None:
        """Pin belief-array `bx`'s view of asteroid i to truth and update its
        rival-rate estimate (v10b) from whatever depletion company `co`'s OWN
        mining over the gap does not explain. Consumes no RNG. In free-radio
        mode bx == co (the company map); under gossip bx == rid (the robot's
        own map) while own_mined stays the shared company aggregate."""
        dt = self.tick - self.last_seen[bx][i]
        if dt > 0:
            depl = self.belief[bx][i] - self.stock[i]
            own = self.own_mined[co][i] - self._own_mined_seen[bx][i]
            rival = max(0.0, float(depl - own)) / dt
            self.rival_rate[bx][i] += RIVAL_ALPHA * (rival - self.rival_rate[bx][i])
        self.belief[bx][i] = self.stock[i]
        self.last_seen[bx][i] = self.tick
        self._own_mined_seen[bx][i] = self.own_mined[co][i]

    def _observe(self, co: int, i: int) -> None:
        """Free-radio observation: the company's shared map (bx == company)."""
        self._observe_idx(co, co, i)

    def _observe_r(self, r, i: int) -> None:
        """v14 gossip observation: robot r's OWN map (bx == rid)."""
        self._observe_idx(self._bx(r), r.company, i)

    def sense_step(self) -> None:
        """v10a: the once-per-tick field sweep — any robot within Chebyshev
        R_SENSE of an asteroid refreshes its company's belief to truth (the
        fleet is a shared sensor network). Called from BaseArm.tick AFTER
        drive/charge and BEFORE encounters; it also freezes live sensing so
        beliefs cannot change while bundles are being priced."""
        if self.belief_mode:
            for r in self.robots:
                for i in range(len(self.sources)):
                    if self._in_sense_range(r.pos, i):
                        if self.gossip:
                            self._observe_r(r, i)
                        else:
                            self._observe(r.company, i)
            if self.gossip:
                self._gossip_step()        # v14: one hop of belief flooding
        self._live_sense = False

    def _gossip_step(self) -> None:
        """v14 (column O): one hop of belief flooding. Each same-company
        fleet-mate within Chebyshev r_radio adopts, per rock, its neighbourhood's
        FRESHER (higher last_seen) entry — belief, last_seen, rival_rate AND the
        rival-rate baseline _own_mined_seen travel together. All four read arrays
        are SNAPSHOT first, so a robot never adopts an entry another robot adopted
        this same tick: propagation is exactly one hop per tick (order-independent,
        no RNG), and over ticks the freshest observation floods the connected
        fleet — a longer radius floods farther per tick. Spatial-hashed by
        r_radio-sized cells (~O(N), the same bucketing idea as encounters(), which
        is left untouched). Runs in the drive/world phase from sense_step (before
        the belief freeze), so beliefs never change during the encounter phase and
        evaluated Φ == executed Φ still holds."""
        R = max(1, self.r_radio)
        rs = self.robots
        s_ls = [row[:] for row in self.last_seen]     # snapshot every read array
        s_bel = [row[:] for row in self.belief]
        s_rr = [row[:] for row in self.rival_rate]
        s_oms = [row[:] for row in self._own_mined_seen]
        buckets: dict = {}
        for idx, r in enumerate(rs):
            buckets.setdefault((r.pos[0] // R, r.pos[1] // R), []).append(idx)
        n_src = len(self.sources)
        for a in rs:
            cx, cy = a.pos[0] // R, a.pos[1] // R
            neigh = []
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for j in buckets.get((cx + ox, cy + oy), ()):
                        b = rs[j]
                        if b.rid == a.rid or b.company != a.company:
                            continue
                        if (abs(a.pos[0] - b.pos[0]) <= R
                                and abs(a.pos[1] - b.pos[1]) <= R):
                            neigh.append(b.rid)
            if not neigh:
                continue
            ai = a.rid
            for k in range(n_src):
                best_j, best_ls = -1, s_ls[ai][k]
                for bj in neigh:
                    if s_ls[bj][k] > best_ls:
                        best_ls, best_j = s_ls[bj][k], bj
                if best_j >= 0:
                    self.belief[ai][k] = s_bel[best_j][k]
                    self.last_seen[ai][k] = s_ls[best_j][k]
                    self.rival_rate[ai][k] = s_rr[best_j][k]
                    self._own_mined_seen[ai][k] = s_oms[best_j][k]

    # ── v12 K1: map-selling (a sync is a copy of fresher map entries) ────
    def _map_overlay_entries(self, rc: int, gc: int):
        """The entries a giver company `gc` can freshen for a receiver `rc`:
        every asteroid gc saw MORE recently than rc (higher last_seen), as
        (i, belief, last_seen, rival_rate) tuples to copy gc→rc. Deterministic;
        consumes no RNG. Beliefs are frozen during the encounter phase, so this
        returns the SAME set in evaluation (synced_phi_view) and in execution
        (apply_map_sync) — the exact-restore/exact-replay that keeps evaluated
        Φ == executed Φ across a map deal."""
        return [(i, self.belief[gc][i], self.last_seen[gc][i],
                 self.rival_rate[gc][i])
                for i in range(len(self.sources))
                if self.last_seen[gc][i] > self.last_seen[rc][i]]

    @contextmanager
    def synced_phi_view(self, receiver, giver):
        """Price a map sync: temporarily overlay the RECEIVER company's
        (belief, last_seen, rival_rate) with the giver's fresher entries,
        compute Φ inside, then restore EXACTLY (only the touched entries are
        saved). The giver's own map is untouched — a sync is a copy, not a
        move. No clamping: a sync that overwrites stale-optimistic belief with
        fresher-but-lower truth LOWERS the receiver's Φ (bad news); IR vetoes
        those downstream (registered P17c), so this must not special-case it.
        v14: under gossip a sync is seller ROBOT's map → buyer ROBOT (_bx=rid);
        free-radio it is seller-company → buyer-company, unchanged."""
        rc, gc = self._bx(receiver), self._bx(giver)
        entries = self._map_overlay_entries(rc, gc)
        saved = [(i, self.belief[rc][i], self.last_seen[rc][i],
                  self.rival_rate[rc][i]) for (i, _, _, _) in entries]
        for (i, bel, ls, rr) in entries:
            self.belief[rc][i] = bel
            self.last_seen[rc][i] = ls
            self.rival_rate[rc][i] = rr
        try:
            yield
        finally:
            for (i, bel, ls, rr) in saved:
                self.belief[rc][i] = bel
                self.last_seen[rc][i] = ls
                self.rival_rate[rc][i] = rr

    def apply_map_sync(self, receiver, giver) -> int:
        """Execute a map sync: permanently copy the giver company's fresher
        (belief, last_seen, rival_rate) entries onto the receiver company.
        Same entries synced_phi_view priced ⇒ evaluated Φ == executed Φ.
        Returns the number of entries copied (0 is a legal no-op sync).
        v14: seller ROBOT → buyer ROBOT under gossip (only that one buyer's
        per-robot map learns it — a distant fleet-mate stays dark until gossip
        relays the entry onward)."""
        rc, gc = self._bx(receiver), self._bx(giver)
        entries = self._map_overlay_entries(rc, gc)
        for (i, bel, ls, rr) in entries:
            self.belief[rc][i] = bel
            self.last_seen[rc][i] = ls
            self.rival_rate[rc][i] = rr
        return len(entries)

    # ── v11: the moving field ───────────────────────────────────────────
    def field_step(self) -> None:
        """Fire any scheduled arrival/departure whose time has arrived. Called
        from BaseArm.tick at TICK START — before EV refresh, drives, sensing
        and (critically) before any bundle is evaluated. That placement is the
        invariant: no field change ever lands between a bundle's evaluation and
        its execution, so evaluated Φ == executed Φ still holds. Consumes only
        the dedicated field RNG; a no-op (and zero cost) when dynamic_field is
        off, keeping every other column bit-identical."""
        if not self.dynamic_field:
            return
        while (self._field_next < len(self._field_events)
               and self._field_events[self._field_next]["t"] <= self.tick):
            ev = self._field_events[self._field_next]
            self._field_next += 1
            if ev["kind"] == "arrival":
                self._field_arrival()
            else:
                self._field_departure()

    def _field_arrival(self) -> None:
        """A fresh asteroid appears in the field band, ≥3 (Manhattan) from any
        facility and any existing rock (rejection-sampled from the dedicated
        RNG). Every per-asteroid array grows for BOTH companies; the new rock's
        belief starts at 0 — unknown until a robot senses it — with last_seen
        pinned to the arrival tick. total_stock grows so the makespan check
        still requires delivering the newcomer too."""
        frng = self._field_rng
        sc = self.grid / GRID
        lo, hi = 3 * sc, (GRID - 3) * sc        # interior field band
        facilities = list(self.refineries) + list(self.chargers)
        while True:
            p = (int(frng.uniform(lo, hi)), int(frng.uniform(lo, hi)))
            if any(manhattan(p, f) < 3 for f in facilities):
                continue
            if any(manhattan(p, s) < 3 for s in self.sources):
                continue
            break
        stock = int(frng.uniform(8, 24))
        i = len(self.sources)
        self.sources.append(p)
        self.stock.append(stock)
        self.total_stock += stock
        self.mined_from.append(0)
        self.arrival_indices.append(i)
        self.arrival_t[i] = self.tick           # v12 K2: claim-window origin
        # v14: the belief-map arrays grow per belief-index (2 companies for free
        # radio, n_robots under gossip); own_mined is the physical company
        # aggregate and grows per company. At len(belief)==2 this is exactly the
        # old five-append loop (bit-identical), just split by index space.
        for bx in range(len(self.belief)):
            self.belief[bx].append(0)           # unknown until sensed
            self.last_seen[bx].append(self.tick)
            self.rival_rate[bx].append(0.0)
            self._own_mined_seen[bx].append(0)
        for co in range(2):
            self.own_mined[co].append(0)
        self.field_log.append(dict(t=self.tick, kind="arrival", src=i, amt=stock))

    def _field_departure(self) -> None:
        """A stocked asteroid is exhausted by an off-map rival: its remaining
        TRUE stock is lost (recorded in stock_lost, so conservation still holds
        exactly), stock[i]=0. Beliefs are deliberately NOT updated — the map
        keeps a ghost until a robot re-senses the rock. Target chosen among
        currently-stocked rocks via the dedicated RNG; skipped if none."""
        stocked = [i for i in range(len(self.sources)) if self.stock[i] > 0]
        if not stocked:
            return
        i = int(self._field_rng.choice(stocked))
        lost = self.stock[i]
        self.stock_lost += lost
        self.stock[i] = 0
        self.field_log.append(dict(t=self.tick, kind="departure", src=i, amt=lost))

    def _spawn_twin_fleets(self, n_robots, sigma):
        """Both companies receive the IDENTICAL draw multiset; company-1
        positions are the reflection (x, 32−y). Sectors stratified 6/6/6/6
        and mirrored so each company faces the same home/far structure."""
        half = n_robots // 2
        draws = [self._draw(sigma) for _ in range(half)]
        for k, (cap, eff, b0, pos, mine) in enumerate(draws):
            self.robots.append(Robot(
                rid=k, pos=pos, battery=b0, cap=cap, eff=eff,
                sector=k % 2, company=0, mine_rate=mine))
        for k, (cap, eff, b0, (x, y), mine) in enumerate(draws):
            self.robots.append(Robot(
                rid=half + k, pos=(x, self.grid - y), battery=b0, cap=cap, eff=eff,
                sector=1 - (k % 2), company=1, mine_rate=mine))
        if len(self.sources) > 2:            # v5: claims replace sectors —
            half_src = len(self.sources) // 2
            for k in range(half):            # mirrored pairs stay symmetric
                c = self.best_claim(self.robots[k])
                self.robots[k].sector = c
                # (c + half_src) % len is the mirror-partner index for a
                # mirrored field. Under contested=True the field is NOT
                # mirrored, so this is just a company-neutral round-robin over
                # valid rock indices — the mirror placebo does not apply there
                # (noted at _gen_asteroids); the index stays in range either way.
                self.robots[half + k].sector = (c + half_src) % len(self.sources)

    def _spawn_v3(self, n_robots, sigma):
        for i in range(n_robots):
            cap, eff, b0, pos, mine = self._draw(sigma)
            self.robots.append(Robot(rid=i, pos=pos, battery=b0, cap=cap,
                                     eff=eff, sector=i % 2, company=0,
                                     mine_rate=mine))

    # ── credit / tariffs ────────────────────────────────────────────────
    def credit_rate(self, robot_company: int, ref_idx: int) -> float:
        """Per-unit credit fraction for refining at refinery `ref_idx`.
        A merged firm (internalize_tariffs) pays itself: full rate."""
        owner = self.ref_owner[ref_idx]
        if owner is None or owner == robot_company or self.internalize_tariffs:
            return 1.0
        return 1.0 - self.tau[owner]

    # ── physics ─────────────────────────────────────────────────────────
    def move_toward(self, r: Robot, target) -> None:
        if r.stranded or r.pos == target:
            return
        cost = r.step_cost()
        if r.battery < cost:
            self._maybe_strand(r)
            return
        r.pos = toward(r.pos, target)
        r.battery -= cost
        self._maybe_strand(r)

    def nearest_charger(self, r: Robot):
        """(pos, dist) of the routing-preferred charger: nearest by distance
        plus a guest penalty at rival infrastructure (guests charge slower)."""
        best, best_eff, best_d = None, float("inf"), 0
        for pos, owner in zip(self.chargers, self.charger_owner):
            d = manhattan(r.pos, pos)
            eff_d = d + (0 if owner is None or owner == r.company
                         else GUEST_PENALTY)
            if eff_d < best_eff:
                best, best_eff, best_d = pos, eff_d, d
        return best, best_d

    def _maybe_strand(self, r: Robot) -> None:
        r.battery = max(0.0, r.battery)
        if r.battery < RESCUE_FLOOR and \
                all(manhattan(r.pos, c) > 1 for c in self.chargers):
            r.stranded = True

    def pick(self, r: Robot) -> int:
        s = r.sector
        # v12 K2 physics gate: a non-holder mines 0 from a claimed arrival
        # inside its window (hard guarantee; the belief gate already keeps the
        # fleet from routing here, but claims bind on the ore, not just beliefs)
        if self.prospect_claims and self._claim_gated(r.company, s):
            return 0
        if r.pos == self.sources[s] and self.stock[s] > 0:
            q = min(r.cap - r.load, self.stock[s])
            if self.mine_trait:
                # v10c: rate-limited mining. OFF keeps today's fill-cap-in-
                # one-tick physics bit-identical (the registered `else 1`
                # would have silently rewritten every existing column).
                q = min(q, r.mine_rate)
            r.load += q
            r.load_prov[r.company] += q       # provenance: miner's company
            r.mined_units += q                 # v13: middleman metric
            self.stock[s] -= q
            self.own_mined[r.company][s] += q  # v10b: rival-rate accounting
            self.mined_from[s] += q            # v11: per-asteroid provenance
            if self.lineage and q:             # v17: one 0-hop parcel per unit,
                r.parcels.extend(              # tagged with its origin rock
                    {"origin": s, "hops": 0, "chain": []} for _ in range(q))
            return q
        return 0

    def drop(self, r: Robot) -> int:
        """Refine at whichever refinery the robot stands on. Tariff is
        assessed HERE and only here, once per unit (panel refine-once)."""
        for ref_idx, pos in enumerate(self.refineries):
            if r.pos != pos or r.load <= 0:
                continue
            q, r.load = r.load, 0
            if self.lineage:                    # v17: retire this unit's lineage
                for p in r.parcels:             # (origin, hops it took to arrive,
                    self.delivered_parcels.append(dict(   # tick, who delivered)
                        origin=p["origin"], hops=p["hops"], tick=self.tick,
                        deliverer=r.rid, chain=p["chain"]))
                r.parcels = []
            owner = self.ref_owner[ref_idx]
            rate = self.credit_rate(r.company, ref_idx)
            earned = rate * V_DELIVER * q
            r.delivered += q
            r.credit += earned
            self.company[r.company]["credit"] += earned
            if owner is not None and owner != r.company:
                self.foreign_refined += q
                tariff = self.tau[owner] * V_DELIVER * q
                self.company[owner]["tariffs_earned"] += tariff
                self.company[r.company]["tariffs_paid"] += tariff
            for miner_co in (0, 1):           # provenance matrix
                qq = r.load_prov[miner_co]
                if qq:
                    self.delivered_matrix[miner_co][owner if owner is not None
                                                    else 0] += qq
            r.load_prov = [0, 0]
            self.delivered += q
            self.energy_at_last_delivery = self.energy_drawn()
            return q
        return 0

    def charge_step(self) -> None:
        served = set()
        for pos, owner in zip(self.chargers, self.charger_owner):
            queue = [r for r in self.robots
                     if r.rid not in served
                     and r.charge_queued_at >= 0
                     and manhattan(r.pos, pos) <= 1
                     and r.battery < BATTERY_MAX - 1e-9]
            queue.sort(key=lambda r: (r.charge_queued_at,
                                      self._charge_prio[r.rid]))
            for r in queue[:CHARGE_SLOTS]:
                guest = owner is not None and owner != r.company
                amt = min(GUEST_RATE if guest else CHARGE_RATE,
                          BATTERY_MAX - r.battery)
                r.battery += amt
                self.energy_charged += amt
                if guest:
                    self.guest_charged += amt
                served.add(r.rid)
                self.charge_served_slots += 1    # v17: charger duty-cycle numer.
                if r.stranded and r.battery >= RESCUE_FLOOR:
                    r.stranded = False
            for r in queue[CHARGE_SLOTS:]:    # commons diagnostics
                self.company[r.company]["queue_wait"] += 1
        # the charger's meter is ground truth: at true-full it cuts the
        # current and the robot undocks. Without this, a pessimistic gauge
        # (bias < -0.05) can never read 95% and the robot parks forever —
        # the v7 livelock that masqueraded as a negotiation-layer collapse.
        for r in self.robots:
            if r.charge_queued_at >= 0 and r.battery >= BATTERY_MAX - 1e-9:
                r.charge_queued_at = -1

    def transfer_energy(self, donor: Robot, recv: Robot, amount: float,
                        log: bool = True) -> float:
        amount = min(amount, max(0.0, donor.battery - 1.0))
        if amount <= 0:
            return 0.0
        got = min(amount * (1 - TRANSFER_LOSS), BATTERY_MAX - recv.battery)
        if got <= 0:
            return 0.0
        donor.battery -= got / (1 - TRANSFER_LOSS)
        recv.battery += got
        if recv.stranded and recv.battery >= RESCUE_FLOOR:
            recv.stranded = False
        self._maybe_strand(donor)
        if log:
            self.event_log.append(dict(t=self.tick, kind="energy",
                                       src=donor.rid, dst=recv.rid,
                                       amt=round(got, 2)))
        return got

    def transfer_cargo(self, giver: Robot, taker: Robot, q: int,
                       log: bool = True) -> int:
        q = min(q, giver.load, taker.cap - taker.load)
        if q <= 0:
            return 0
        moved = 0                               # provenance moves FIFO-ish:
        for co in (0, 1):                       # proportional by bucket order
            take = min(q - moved, giver.load_prov[co])
            giver.load_prov[co] -= take
            taker.load_prov[co] += take
            moved += take
        giver.load -= q
        taker.load += q
        taker.received_units += q               # v13: units acquired via a deal
        giver.target_ref = None                 # re-evaluate routing
        taker.target_ref = None
        # v17: move the FIFO head q parcels giver→taker, +1 hop each. Gated on
        # `log` so it fires ONLY on real execution, NEVER on the log=False
        # evaluation passes (apply_bundle on the live robots inside _evaluate) —
        # those restore load without ever having touched parcels, so the
        # invariant len(parcels)==load survives and no snapshot is needed. Pure
        # bookkeeping: no RNG, no physics.
        if self.lineage and log:
            moving = giver.parcels[:q]
            giver.parcels = giver.parcels[q:]
            hop = (self.tick, giver.rid, taker.rid)
            for p in moving:
                p["hops"] += 1
                p["chain"] = p["chain"] + [hop]
            taker.parcels.extend(moving)
        if log:
            self.event_log.append(dict(t=self.tick, kind="cargo",
                                       src=giver.rid, dst=taker.rid, amt=q,
                                       d=int(giver.stranded or taker.stranded)))
        return q

    def swap_sectors(self, a: Robot, b: Robot, log: bool = True) -> None:
        a.sector, b.sector = b.sector, a.sector
        if log:
            self.event_log.append(dict(t=self.tick, kind="sector",
                                       src=a.rid, dst=b.rid, amt=0))

    def debit_energy(self, r: Robot, amount: float) -> None:
        r.battery = max(0.0, r.battery - amount)
        self._maybe_strand(r)

    # ── queries ─────────────────────────────────────────────────────────
    def encounters(self):
        # Spatial-hash all-pairs: robots within Chebyshev R_COMM interact.
        # The old nested loop was O(N²) PER TICK — the wall-clock killer at
        # N≥96 (v13 scale). Bucketing by R_COMM-sized cells makes it ~O(N):
        # a pair within Chebyshev R_COMM sits within ±1 cell each axis (the
        # minimum gap for a 2-cell jump is R_COMM+1 > R_COMM), so a 3×3 cell
        # neighborhood is a provably sufficient candidate set. Pairs are
        # emitted in canonical list-index (i<j) order — identical to the old
        # loop — so self.rng.shuffle consumes the SAME randomness and the
        # output is BIT-EXACT (differential-tested at N=24/96/240).
        rs = self.robots
        R = R_COMM
        buckets: dict = {}
        for idx, r in enumerate(rs):
            buckets.setdefault((r.pos[0] // R, r.pos[1] // R), []).append(idx)
        pairs_idx = []
        for i, a in enumerate(rs):
            cx, cy = a.pos[0] // R, a.pos[1] // R
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for j in buckets.get((cx + ox, cy + oy), ()):
                        if j <= i:                 # dedupe → each pair once as i<j
                            continue
                        b = rs[j]
                        if (abs(a.pos[0] - b.pos[0]) <= R
                                and abs(a.pos[1] - b.pos[1]) <= R):
                            pairs_idx.append((i, j))
        pairs_idx.sort()                           # == nested-loop order
        pairs = [(rs[i], rs[j]) for i, j in pairs_idx]
        self.rng.shuffle(pairs)
        return pairs

    def energy_drawn(self) -> float:
        return self.energy_initial + self.energy_charged

    def material_accounted(self) -> int:
        return self.delivered + sum(self.stock) + sum(r.load for r in self.robots)

    def material_ok(self) -> bool:
        # v11: departures erase true stock, booked to stock_lost — accounted
        # here explicitly so conservation stays EXACT. stock_lost is 0 in every
        # non-dynamic column, so this is bit-identical to the old invariant.
        return self.material_accounted() + self.stock_lost == self.total_stock

    def ledger_accounted(self) -> bool:
        """Σ company credit + Σ tariffs earned == V · delivered (unless the
        merged-firm flag pays full rate, where tariff flows are notional)."""
        if self.internalize_tariffs:
            return True
        credit = sum(c["credit"] for c in self.company)
        tariffs = sum(c["tariffs_earned"] for c in self.company)
        return abs(credit + tariffs - V_DELIVER * self.delivered) < 1e-6

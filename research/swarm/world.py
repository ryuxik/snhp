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

import math
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
NAV_DUMB_NOISE = 6.0                # v20 (column S): std of the additive
                                    # Manhattan-distance noise the DUMB routing
                                    # brain perturbs its greedy nearest-rock pick
                                    # with (~min inter-rock separation, so the
                                    # noise can flip adjacent-rock preferences).
                                    # Drawn from the DEDICATED nav_dumb stream
                                    # (seed+262626), never the main stream.
R_RADIO = 6                         # v14 (column O): Chebyshev radius within
                                    # which same-company fleet-mates gossip
                                    # fresher belief entries (short radio); the
                                    # ladder also runs r_radio=2 (contact-only)
FIRM_MARGIN = 0.15                  # v17 (column P) PHASE 2 (snhp+firm): the
                                    # treasury's fixed handoff margin, a fraction
                                    # of the cargo's home-refinery value, added
                                    # to the receiver's marginal haul cost as the
                                    # internal transfer price (Coase settlement)
DWELL_DECAY_LAMBDA = 0.05           # P23e (column P phase-2e): the TIME-CONTINGENT
                                    # split. A carrier's recorded claim pays out
                                    # multiplied by exp(-λ·excess), where excess is
                                    # the carrier's leg dwell ABOVE its geodesic
                                    # counterfactual (ticks held minus the manhattan
                                    # ground it covered, speed 1 cell/tick). λ=0.05
                                    # ⇒ ~14 idle ticks halves the share. The
                                    # observable Holmström says to contract on;
                                    # off (flat splits) ⇒ every claim decay ≡ 1.

ORDER_EXPIRY = 400                  # v23 (column V): ticks a pinned order lives
                                    # before it expires and refunds its escrow.
                                    # Long relative to the 2500-tick horizon and
                                    # to the field diagonal so a fleetmate can
                                    # route across even G=64 to service it — the
                                    # persistence IS the async advantage (a fixed
                                    # pin any passer can take at any tick, vs two
                                    # movers meeting at the same tick).
R_PICKUP = R_COMM                   # Chebyshev radius to ACCEPT a pinned order
                                    # (== the synchronous encounter radius);
                                    # DISCOVERY uses the wider R_SENSE, mirroring
                                    # the world's two existing radii (sense wide,
                                    # interact near).

# v18 (column Q): endogenous infrastructure — "the sim grows landlords". All the
# machinery below is gated on build_matter>0 / build=True; the matter field, the
# per-charger toll array and the build ledger are allocated but NEVER read/written
# when off, so every prior column stays bit-identical (suite-verified). Matter
# lives in a SEPARATE structure (matter_sources/matter_stock), disjoint from the
# ore field — so ore routing, Φ valuation, belief maps and ore conservation are
# untouched by construction (no fast-path change, no oracle perturbation).
MATTER_COST = 6.0                   # matter units a company spends per built charger
BUILD_CREDIT_COST = 30.0            # credits a company spends per built charger
MATTER_HAUL = 4                     # matter units mined into the company pool per
                                    # visit to a matter rock (mine-to-pool, no haul)
MATTER_PER_ORE_PAIR = 1.0           # matter rocks seeded per ore mirror-pair at
                                    # build_matter==1.0 (count = round(bm·pairs));
                                    # a fraction bm<1 seeds proportionally fewer
# The toll dial: guest CHARGE PRICE in credits per guest slot-fill on a BUILT
# charger, the owner's choice from this small registered grid — 0 (free),
# marginal ×{1,2,4}. Preset (exogenous) chargers stay toll-free (toll 0), so the
# toll-booth recurses ONLY onto endogenous capital.
TOLL_UNIT = 1.0
TOLL_GRID = (0.0, TOLL_UNIT, 2.0 * TOLL_UNIT, 4.0 * TOLL_UNIT)
TOLL_ROUTE_PENALTY = 3.0            # cells of extra guest-avoidance per credit of
                                    # toll (the toll enters guest ROUTING, so a
                                    # high toll deters guests — the deadweight
                                    # channel that gives the toll an interior
                                    # revenue optimum; 0 for toll-free chargers)
GATHERERS_MAX = 3                   # at most this many robots per company divert
                                    # to gather matter at once (rid tie-break, like
                                    # SCOUTS_MAX — a whole-fleet matter stampede
                                    # would erase the ore-vs-matter trade the KILL
                                    # is measuring)
# v25 (column X): the firm's interior — command / prices / claims.
PLAN_PERIOD = 25                   # ticks between central-planner re-plans (the
                                    # dispatcher's cadence). Between re-plans a drone
                                    # executes its last order; a stale plan self-
                                    # corrects as re-plans read fresher merged belief.
CMD_HANDOFF_RADIUS = R_RADIO       # a directed hand-off pairs a stuck loaded drone
                                    # with a LOCAL same-company taker only (within this
                                    # Chebyshev radius, itself single-hop-reachable to a
                                    # refinery and closer to it) — a local rendezvous,
                                    # never a multi-hop stepping-stone router (P24 caveat)
DEADLOCK_FULL = 0.95               # "at full battery" threshold (× BATTERY_MAX) for the
                                    # routing-deadlock predicate (the P24 signature:
                                    # loaded, charged, still beyond single-hop refinery reach)

# v28 (column AA): mortality and the persistence of paper — estates. All the
# machinery below is gated on `mortality`/`death_regime`; every array is
# allocated but NEVER read/written when off, so every prior column stays
# bit-identical (suite-verified). Death is PERMANENT (distinct from the
# rescuable `stranded`): a dead robot is inert (excluded from encounters/drive/
# rescue) and its carried cargo is written off to stock_lost (destroyed, like
# stranded cargo). Two claim-inheritance regimes plus a risk-premium variant
# select what happens to the PAPER a death leaves behind.
FLATLINE_TICKS = 100               # a robot STRANDED this many consecutive ticks with
                                    # no rescue flatlines and dies (the endogenous,
                                    # trajectory-dependent mortality source; measured
                                    # as the P23 base rate before any wear-out).
WEAROUT_AGE = 900                  # ticks: a chassis older than this faces the wear-out
                                    # hazard (registered; identical in every regime).
WEAROUT_P = 0.00035                # per-tick death probability above WEAROUT_AGE, drawn
                                    # ONCE per robot as a geometric death-tick from a
                                    # DEDICATED RandomState(seed+282828) — never the main
                                    # stream, so the schedule is regime-INDEPENDENT (the
                                    # same chassis die at the same ticks in all regimes).
# Claim-stack sentinel claimants (negative rids never collide with real 0..N-1):
CLAIM_VOID = -1                    # a claim VOIDED at the holder's death (claims-die /
                                    # risk-premium): its terminal payout is DESTROYED and
                                    # booked to claims_voided (accounted in the ledger).
# an ESTATE claim re-points to its dead holder's company treasury via the sentinel
# rid == -(2 + company): -2 → company 0, -3 → company 1 (decoded at settlement).

# v29 (column AB): the crash — contagion in the counterparty web. All gated on
# `shock` / `clearinghouse`; every accumulator/array below is allocated but NEVER
# read/written when both are off, so every prior column stays bit-identical
# (suite-verified). The shock is a pure SETTLEMENT-side event — Φ never sees it
# (far-band cargo keeps its full Φ value; the write-down lands only at drop /
# death_resolve), so evaluated Φ == executed Φ is preserved by construction.
SHOCK_TICK = 1000                  # T_shock: the far band goes dark (registered;
                                   # identical across regimes/seeds). Overridable per
                                   # World via `shock_tick`; None ⇒ never fires (control).
                                   # The contract's illustrative 3,500 hits a DEAD
                                   # economy — the v5 field delivers/relays its far band
                                   # over ticks ~500–2,000 then plateaus (far cargo
                                   # delivered or P24-deadlocked in un-dying drones), so
                                   # a late shock finds nothing in flight. 1,000 lands
                                   # mid-active-phase (chains mature, far settlement
                                   # ongoing). Rationale registered in SPEC/report.
SHOCK_FAR_PCTL = 60                # the FAR BAND = asteroids whose nearest-refinery
                                   # distance exceeds this percentile of the field (the
                                   # farthest ~40%). Scale-invariant (works at grid 32 and
                                   # 101, where a fixed cell threshold would be empty),
                                   # non-empty, and DETERMINISTIC per field (no RNG) ⇒
                                   # identical across regimes for a seed.
SHOCK_VALUE_FLOOR = 0.0            # post-shock a far-band unit settles at this × its face
                                   # value ("stock/value zero out" ⇒ 0.0); the (1−floor)·V
                                   # gap per delivered shocked unit is the write-down.
CCP_FEE = 0.05                     # clearinghouse per-settlement fee (fraction of face
                                   # DELIVERY credit), charged at EVERY settlement from
                                   # t=0 to build the pool; the CCP then tops shock and
                                   # death write-downs back to face from the pool. If the
                                   # pool runs dry the shortfall is a pro-rata HAIRCUT (the
                                   # registered waterfall) — recipients eat the uncovered
                                   # remainder exactly as under gross bilateral.

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
    dead: bool = False              # v28 (column AA): PERMANENT death (distinct from
                                    # the rescuable `stranded`). A dead chassis is inert
                                    # — excluded from encounters/drive/rescue — and its
                                    # paper resolves per the death regime. Default False
                                    # and set only under `mortality`, so bit-identical off.
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
                                    # v17 PHASE 2 (bills): each parcel also carries
                                    # a "claims" list of (rid, share) — a notarized
                                    # split of its terminal payout — appended
                                    # deterministically at each hop.
    claim_value: float = 0.0        # v17 PHASE 2 (snhp+bill): running Σ(own claim
                                    # share × V_DELIVER) over parcels this robot
                                    # gave away — the UNDISCOUNTED terminal claim Φ
                                    # values (paid at delivery regardless of this
                                    # robot's position). 0 unless World.bills; pure
                                    # bookkeeping otherwise (never read by Φ off).
    relay_from: tuple | None = None  # v31 (column V2): the depot a robot last
                                    # PICKED UP a relayed parcel at — set on
                                    # accept_order and cleared on deposit / deliver /
                                    # fresh mine. Read ONLY under World.depots (the
                                    # anti-churn guard: a robot does not re-deposit at
                                    # the very depot it just took from — it stages the
                                    # cargo forward a leg first). None in every prior
                                    # column ⇒ never read ⇒ bit-identical.

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
                 lineage: bool = False,
                 bills: bool = False, firm_relay: bool = False,
                 dwell: bool = False, bills_contingent: bool = False,
                 claims_transferable: bool = False,
                 reputation: bool = False, false_accuse: float = 0.0,
                 order_book: bool = False,
                 build_matter: float = 0.0, build: bool = False,
                 toll_level: float = 0.0, build_budget: int = 10**9,
                 command: bool = False, deadlock_track: bool = False,
                 charger_band: float = 0.0, nav_dumb: bool = False,
                 forgery: bool = False, forge_cost: float = 0.0,
                 verify_cost: float = 0.0, verify_regime: str = "none",
                 mortality: bool = False, death_regime: str = "none",
                 wearout: bool = False,
                 shock: bool = False, shock_tick: int | None = None,
                 clearinghouse: bool = False, depots: bool = False):
        self.rng = np.random.RandomState(seed)
        self.rng_seed = seed                 # v18: matter-field RNG keys off this
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
        # v20 (column S): the DUMB routing brain. Default off ⇒ every prior
        # column stays bit-identical (the dedicated stream below is CREATED
        # unconditionally but DRAWN from only when nav_dumb is on, and it never
        # touches self.rng). When on, dumb_claim() replaces best_claim()'s
        # richest-per-distance Φ scoring in intent() with greedy nearest-known-
        # rock + noise — we dumb the ROUTING (planning) brain, not the bargaining
        # brain (deal Φ evaluation is untouched; evaluated Φ == executed Φ holds).
        self.nav_dumb = nav_dumb
        self._nav_rng = np.random.RandomState(seed + 262626)
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
        # v18 (column Q): per-charger toll (credits/guest slot-fill). Preset
        # chargers are toll-free (0.0), so nearest_charger's guest-routing term is
        # identically 0 and bit-identical for every prior column; BUILT chargers
        # are appended later (build_step) with toll == toll_level. `built` is the
        # parallel flag marking endogenous capital (the toll-booth surface).
        self.charger_toll = [0.0 for _ in self.chargers]
        self.charger_built = [False for _ in self.chargers]
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
                             queue_wait=0, treasury=0.0,
                             # v18 (column Q): matter pool, build ledger, toll
                             # book. All default zero and touched ONLY under
                             # build/build_matter ⇒ prior columns bit-identical.
                             matter=0.0, matter_mined=0.0, build_spend=0.0,
                             built=0, toll_earned=0.0, toll_paid=0.0)
                        for _ in range(2)]
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
        # v17 PHASE 2 (column P): the two pre-commitment mechanisms. Both default
        # off ⇒ every prior column stays bit-identical (claim_value/treasury are
        # allocated but never read/written when off). Both need the lineage
        # instrument (claims/advanced live on parcels), so either implies it —
        # off leaves self.lineage == lineage exactly (no bit perturbed).
        # v23 (column V): the stigmergic order book. order_book default off ⇒
        # every prior column is bit-identical (all order state is allocated but
        # never touched, and the arm phases are gated). A pinned order is a
        # signed binding limit offer at a LOCATION: escrow (a cargo lien +
        # optional energy bounty) is reserved at post time, the order is
        # discovered ONLY by physical proximity (R_SENSE — the P21 lesson: no
        # free broadcast), and acceptance is UNILATERAL by a passer whose IR
        # clears — no consensus, NO DEAL_PAUSE (the mechanism's registered
        # advantage, reported explicitly). Settlement rides the bills claim
        # stack, so credit conservation is the existing invariant; therefore
        # order_book IMPLIES bills. The poster is compensated in a CLAIM (credit
        # at delivery), never in energy, by necessity: energy cannot teleport to
        # a poster who has moved on — the async-settlement directionality
        # constraint (documented in the report).
        # v31 (column V2): the DEPOT — the founder's async re-run of the board.
        # The depot removes the JOURNEY STRUCTURE (V removed only the rendezvous):
        # deposits happen ONLY at existing charger locations (co-located, no new
        # geography — drones already stop there to charge), and the acceptor is
        # never obligated to finish the route — it hauls ONE loaded-reach leg and
        # may RE-DEPOSIT at the next depot. Chains form fully asynchronously, leg
        # by leg, with no co-presence at any hop. depots IMPLIES the order_book
        # machinery (escrow, stigmergic discovery, unilateral no-pause acceptance,
        # bills settlement) — it is the SAME posted-terms surface, gated so pins
        # live at depots and takers stage cargo forward. depots default off ⇒
        # order_book/bills stay exactly as column V/P (bit-identical).
        self.depots = depots
        self.order_book = order_book or depots
        assert not (self.order_book and bills_contingent), \
            "order_book relays settle flat 2-tuple claims (contingent off)"
        self.bills = bills or self.order_book   # negotiable delivery claims
        self.firm_relay = firm_relay    # snhp+firm: treasury transfer pricing
        # P23e (column P phase-2e): moral hazard in the relay. `dwell` is a PURE
        # instrument — parcels carry (acq_tick, acq_pos, mined_tick, src_pos, uid),
        # transfer_cargo/drop retire per-leg dwell records — no RNG/physics/Φ, so
        # dwell=True is bit-identical to dwell=False in EVERY regime (spot too).
        # `bills_contingent` is the MECHANISM: it decays each recorded claim's
        # payout by exp(-λ·excess) of the claimant's leg dwell above its geodesic
        # counterfactual (the observable Holmström's informativeness principle
        # says to contract on). It requires bills, implies dwell, and — because
        # the decay enters the giver's claim value in Φ deterministically from
        # PRE-deal state — preserves evaluated Φ == executed Φ. contingent OFF ⇒
        # every claim decay ≡ 1 ⇒ bit-identical to bills-flat (2-tuple claims).
        assert not (bills_contingent and not bills), \
            "bills_contingent requires bills (it decays the claim-stack payout)"
        self.bills_contingent = bills_contingent
        # v30 (column M2): the bill becomes money — ENDORSABLE claim positions. A
        # holder may transfer (endorse) its claim position to a counterparty inside
        # any bundle as PAYMENT: a signed claim-transfer leg (face value moved =
        # expected settlement, priced UNDISCOUNTED by the standard bills Φ, so it is a
        # weightless, lossless side-payment). Off by default ⇒ no claim axis, no
        # transfer_claims, no tracking ⇒ every prior column bit-identical. Kept CLEAN:
        # requires bills (the claim stack it endorses) and flat 2-tuple claims, and
        # is NOT combined with the mechanisms that rewrite / snapshot the stack
        # (contingent decay, order-book pins, the map axis, mortality voids, the
        # crash) — the registered column-M2 grid uses none of them, and the scan-and-
        # reassign endorsement composes cleanly only over a live flat stack.
        self.claims_transferable = claims_transferable
        if claims_transferable:
            assert bills, "claims_transferable requires bills (the claim stack it endorses)"
            assert not bills_contingent, \
                "claims_transferable is flat-only (endorsement reassigns 2-tuple claims)"
            assert not order_book, \
                "claims_transferable does not scan pinned-order parcels (order_book off)"
            assert not map_trading, \
                "claims_transferable owns bundle axis 3 (map_trading off)"
        self.dwell = dwell or bills_contingent
        self.lineage = lineage or self.bills or firm_relay or self.dwell
        # v30 (column M2): circulation instruments. All empty / pure bookkeeping when
        # claims_transferable is off ⇒ bit-identical. claim_xfers counts endorsement
        # deals; claim_xfer_log records each endorsed claim's maturity/risk proxy at
        # transfer (the good-collateral question); claim_settle_log records the
        # velocity (transfers-before-settlement) of every claim as it settles.
        self.claim_xfers = 0
        self.claim_xfer_log: list = []
        self.claim_settle_log: list = []
        self._parcel_uid = 0
        self.hop_dwells: list[dict] = []        # P23e: per-carrier leg records
        self.delivered_dwells: list[dict] = []  # P23e: per-parcel total dwell
        self.charge_served_slots = 0
        self.delivered_parcels: list[dict] = []
        # v23 (column V): order-book ledger. All zero/empty and pure bookkeeping
        # when order_book is off ⇒ every prior column bit-identical. orders holds
        # the active pinned offers; pinned_cargo is folded into material
        # conservation (like stock_lost); the escrow-energy totals let the
        # escrow-conservation test balance post→accept and post→expire.
        self.orders: list[dict] = []
        self.order_log: list[dict] = []      # accepted-async records (audit)
        self._order_uid = 0
        self.pinned_cargo = 0                # units escrowed across live relays
        self.escrowed_energy = 0.0           # bounty energy currently held
        self.orders_posted = 0
        self.orders_accepted = 0
        self.orders_expired = 0
        self.pause_ticks_saved = 0           # DEAL_PAUSE NOT paid on acceptance
        self.escrow_energy_paid = 0.0        # bounty released to takers
        self.escrow_energy_refunded = 0.0    # bounty returned to live posters
        self.escrow_energy_writeoff = 0.0    # bounty of dead posters (see report)
        self.cargo_writeoff = 0              # relay cargo abandoned on death
        # v22 (column U): community reputation. `reputation` turns on per-robot
        # pairwise blacklists (populated by the arm after a deal a counterpart
        # lied on, propagated by contact — _blacklist_gossip_step) with NO
        # attestation; a robot then REFUSES blacklisted counterparts. `false_accuse`
        # (ε) is the slander rate: a per-deal draw from a DEDICATED RandomState
        # (seed+424242, never the main stream) that marks an honest counterpart as
        # if it had lied. Both default off ⇒ every prior column is bit-identical:
        # reputation is post-deal BOOKKEEPING + a pre-evaluate refusal gate — it
        # never touches Φ (the fast path stays; oracles green), never touches the
        # main RNG, and the blacklist sets are allocated but never consulted when
        # reputation is off. The blacklist list itself is built after the spawn.
        self.reputation = reputation
        self.false_accuse = false_accuse
        self._eps_rng = np.random.RandomState(seed + 424242)
        # v27 (column Z): forgery — the receipt under attack. The entire program
        # since v6 has ASSUMED the attested receipt is unforgeable; this attacks
        # that in the trust-GATED tier ONLY (bills stay off — one assumption at a
        # time). A liar (unattested) may burn `forge_cost` energy to present a
        # FORGED receipt that appears attested; a counterparty may burn
        # `verify_cost` energy to check it (a forgery is caught with certainty,
        # p_v=1; an unchecked receipt is honored at face value). `verify_regime`
        # ∈ {"none","mandated","endogenous"} selects who checks. All default
        # off/zero ⇒ every prior column is bit-identical: the flags are read ONLY
        # by TrustArm.encounter (and only when gated), the ledger accumulators
        # start at zero, the dedicated forgery RandomState is allocated only when
        # forgery is on (so the main stream is never perturbed), and forgery is a
        # DETERMINISTIC cost (every liar always forges) — the RandomState is
        # reserved by the registration but unused, documented here.
        self.forgery = forgery
        self.forge_cost = float(forge_cost)
        self.verify_cost = float(verify_cost)
        self.verify_regime = verify_regime
        self.liar_frac = float(liar_frac)         # the tier's forger prevalence
        self.forge_spend = 0.0                     # Σ energy burned forging (ledger)
        self.verify_spend = 0.0                    # Σ energy burned verifying (ledger)
        self.forge_events = 0                      # count of forge debits
        self.verify_events = 0                     # count of verify debits
        if forgery:
            assert defended, ("forgery attacks the ATTESTED gate — it requires "
                              "the defended (signed-books) tier to forge past")
            # dedicated stochastic stream (registered seed+272727); UNUSED under
            # the deterministic always-forge choice, allocated for reproducibility
            self._forge_rng = np.random.RandomState(seed + 272727)
        # v18 (column Q): endogenous infrastructure. build_matter seeds a SEPARATE
        # matter field (disjoint from ore); build lets fleets place chargers; the
        # toll_level is the guest price stamped on every built charger; build_budget
        # caps built chargers PER COMPANY (unlimited by default — the budget sweep
        # sets it for the under-provision test). All default off/zero ⇒ prior
        # columns bit-identical (matter arrays empty; build_step/pick_matter gated).
        self.build = build
        self.toll_level = float(toll_level)
        self.build_budget = build_budget
        self.build_matter = float(build_matter)
        self.matter_sources: list[tuple] = []
        self.matter_stock: list[int] = []
        self.matter_initial = 0
        self.matter_mined = 0                # global (== Σ pools + Σ spent)
        self.built_log: list[dict] = []      # each built charger's (tick, co, pos,
                                             # rock, forgone) — the placement map
        self.built_guest_slots = 0           # slot-fills served to guests AT built
                                             # chargers (the toll-booth throughput)
        self._gather_target: dict = {}       # rid → matter-rock pos (per-tick)
        if self.build_matter > 0:
            self._gen_matter()

        # v18-R (column Q2): FRONTIER SCARCITY. charger_band is the home-band radius
        # (Manhattan) around a refinery inside which preset free chargers survive;
        # presets in the FAR band (beyond single-hop loaded reach of EVERY refinery)
        # are removed, so built capital is the only far supply. Default 0.0 ⇒ NO
        # filter ⇒ every prior column is bit-identical (suite-verified). Applied AFTER
        # _gen_asteroids AND _gen_matter (both key their `taken` set off the FULL
        # preset charger list), so the ore/matter fields are byte-for-byte Q's — the
        # ONLY thing scarcity removes is operational far-band charging capacity.
        self.charger_band = float(charger_band)
        if self.charger_band > 0:
            self._apply_charger_band()

        self.robots: list[Robot] = []
        if self.n_companies == 2:
            self._spawn_twin_fleets(n_robots, sigma)
        else:
            self._spawn_v3(n_robots, sigma)
        self.energy_initial = sum(r.battery for r in self.robots)
        self.energy_at_last_delivery = self.energy_initial
        # v22 (column U): one blacklist per robot (rid → set of refused rids).
        # Allocated unconditionally (empty sets, no RNG) so the off path is
        # bit-identical; consulted only when reputation is on.
        self.blacklist = [set() for _ in range(len(self.robots))]
        # v23 (column V): per-robot memory of orders discovered by proximity
        # (stigmergy — no global feed). Allocated unconditionally (empty sets,
        # no RNG) so the off path is bit-identical; consulted only under
        # order_book.
        self.known_orders = [set() for _ in range(len(self.robots))]
        # v25 (column X): the firm's interior. `command` installs a central planner
        # that REPLACES the drone decision rule with radio-propagated assignments —
        # the planner plans on the company's gossip-merged belief (never field truth)
        # and uses ONLY the shared single-hop routing/valuation primitives (no bespoke
        # multi-hop router; the P24 caveat). `deadlock_track` is the routing-
        # contamination instrument (a pure read-only per-tick predicate count). Both
        # default off ⇒ every prior column is bit-identical: the command state below is
        # allocated but never read (drive/make_arm gate on w.command), command_step and
        # deadlock_step early-return, and no RNG/physics/Φ is touched.
        n_r = len(self.robots)
        self.command = command
        self.deadlock_track = deadlock_track or command
        self.cmd_plan_versions: dict = {}    # plan_tick → {rid: target_spec}; a spec
                                             # is ('mine',rock)|('deliver',ref)|
                                             # ('charge',)|('handoff',taker_rid)
        self.cmd_auth_tick = [-1, -1]        # newest plan tick, per company
        self.cmd_held_tick = [-1] * n_r      # newest plan a robot has RECEIVED (radio)
        self.cmd_belief_age_traj: list = []  # (tick, mean belief-age of the mine-
                                             # assignments) — the plan-staleness at source
        self.cmd_reach_lat: list = []        # adoption latency samples (tick − plan_tick)
        self.cmd_mine_exec = 0               # commanded drone-ticks executing a mine order
        self.cmd_mine_stale = 0              #   ... where the target rock is truly empty
        self.cmd_handoffs = 0                # directed cargo hand-offs executed
        self.deadlock_count = 0              # rising-edge entries into the routing deadlock
        self._in_deadlock = [False] * n_r
        # v28 (column AA): mortality and the persistence of paper. `mortality`
        # enables death_step (physical flatline + optional wear-out); `death_regime`
        # ∈ {"none","claims_die","estates","risk_premium"} selects what the dead
        # robot's PAPER does. All default off ⇒ every prior column is bit-identical:
        # death_step early-returns, the arrays below are allocated but never touched,
        # the wear-out RandomState is created ONLY under wearout (so the main stream
        # is never perturbed), and bills Φ / settlement branch on the regime flags
        # which are false. Derived booleans:
        #   claim_discount — Φ prices a robot's OWN outstanding claims by its survival
        #                    probability (they void if it dies): claims-die + risk-prem.
        #   claim_void     — at death, the dead robot's held claims are DESTROYED
        #                    (payout booked to claims_voided): claims-die + risk-prem.
        #   claim_estate   — at death, they re-point to the company treasury (heir):
        #                    estates only.
        #   premium_split  — the Nash hop-split grosses the giver's share up by its
        #                    survival probability (the actuarial fix): risk-prem only.
        assert death_regime in ("none", "claims_die", "estates", "risk_premium"), \
            f"unknown death_regime {death_regime!r}"
        self.mortality = mortality
        self.death_regime = death_regime
        self.claim_discount = death_regime in ("claims_die", "risk_premium")
        self.claim_void = death_regime in ("claims_die", "risk_premium")
        self.claim_estate = death_regime == "estates"
        self.premium_split = death_regime == "risk_premium"
        self.wearout = wearout
        self.deaths = 0                      # chassis lost this run (flatline + wear-out)
        self.death_flatline = 0              # ... by unrescued stranding
        self.death_wearout = 0               # ... by the age hazard
        self.claims_voided = 0.0             # Σ credit DESTROYED by voided claims (ledger)
        self.estate_settled = 0.0            # Σ credit settled to a treasury as an estate
        self.death_log: list[dict] = []      # per-death record (tick, rid, cause, cargo,
                                             # own-claim value at death, freeze context)
        self._strand_ticks = [0] * n_r       # consecutive ticks each robot has been
                                             # stranded (reset on rescue); FLATLINE_TICKS
                                             # of it kills the chassis.
        # freeze-out instrument: one record per chain-FEASIBLE encounter under mortality
        # — the potential giver's hazard/battery + whether a cargo (chain) deal landed.
        # Pure bookkeeping (no RNG, no physics), populated ONLY when mortality is on.
        self.freeze_log: list[dict] = []
        # wear-out schedule: pre-draw each chassis's natural death tick ONCE from the
        # DEDICATED stream so it is IDENTICAL across regimes (age is tick, regime-free).
        # A death tick past the horizon simply never fires. Drawn only under wearout.
        self._wear_death_tick = [10**12] * n_r
        if wearout:
            wr = np.random.RandomState(seed + 282828)
            for rid in range(n_r):
                # geometric: first Bernoulli(WEAROUT_P) success after the age threshold
                gap = int(wr.geometric(WEAROUT_P)) if WEAROUT_P > 0 else 10**12
                self._wear_death_tick[rid] = WEAROUT_AGE + gap
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
        # ── v29 (column AB): the crash — contagion in the counterparty web ────
        # `shock` schedules the far band going dark at `shock_tick`; `clearinghouse`
        # installs a central counterparty that guarantees claims at face from a
        # fee-funded pool. Both default off ⇒ every prior column is bit-identical:
        # shock_step early-returns (shock_tick None), the settlement/death paths
        # branch on `shocked`/`clearinghouse` (both false), and every accumulator/
        # array below is allocated but never touched. shock/clearinghouse REQUIRE
        # lineage (parcels carry the origin the write-down attributes on) and
        # clearinghouse REQUIRES bills (the CCP guarantees CLAIMS — none exist
        # without bills). The far band is computed once from the FIXED initial field
        # (deterministic, no RNG), so it is identical across regimes for a seed.
        self.shock = shock
        self.shock_tick = (shock_tick if shock_tick is not None
                           else (SHOCK_TICK if shock else None))
        self.clearinghouse = clearinghouse
        assert not ((shock or clearinghouse) and not self.lineage), \
            "shock/clearinghouse require lineage (parcels carry the attributed origin)"
        assert not (clearinghouse and not self.bills), \
            "clearinghouse requires bills (the CCP guarantees claims; none exist off)"
        self.shocked = False                 # flips True at shock_tick (once)
        self.shock_far: set = set()          # far-band source indices (the dark region)
        if shock or clearinghouse:
            dists = [min(manhattan(s, rf) for rf in self.refineries)
                     for s in self.sources]
            if dists:
                thr = float(np.percentile(dists, SHOCK_FAR_PCTL))
                self.shock_far = {i for i, d in enumerate(dists) if d > thr}
        self.shock_far_stock_lost = 0        # true far-band stock erased at the shock
        self.shock_writedown = 0.0           # Σ (1−floor)·V over delivered shocked units
                                             # (ledger term — value that never existed)
        self.ccp_pool = 0.0                  # clearinghouse fee reserve (credit)
        self.ccp_fees = 0.0                  # Σ fees collected (into the pool)
        self.ccp_payouts = 0.0               # Σ write-down covered from the pool
        self.ccp_haircut = 0.0               # Σ write-down eaten by claimants (pool dry)
        self.shock_taint = [None] * len(self.robots)   # per-robot contagion depth
                                             # (None = untainted; 0 = directly hit)
        self.shock_exp_by_hop: dict = {}     # hop → Σ face exposure of the IN-FLIGHT
        self.shock_exp_cnt: dict = {}        # far-band claim stacks snapshotted at the
                                             # shock (timing/deadlock-independent reach)
        self.writedown_log: list = []        # per write-down: (tick, rid, exposure,
                                             # realized, cause, hop, far) — the histogram
        self.strand_log: list = []           # (tick, rid) strand ONSET (pre/post scar)

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

    def _apply_charger_band(self) -> None:
        """v18-R (column Q2): keep only preset chargers whose nearest refinery is
        within `charger_band` Manhattan cells — the FAR band (beyond single-hop
        loaded reach of every refinery) loses its free public chargers, so built
        capital is the only far supply. Filters the four parallel preset arrays in
        lock-step (positions/owner/toll/built). Runs BEFORE any charger is built
        (all `charger_built` are False here) and AFTER both field generators, so ore
        and matter are untouched; consumes no RNG. band radius is the caller's dial
        (Q2 uses BATTERY_MAX/(1+LOADED_MULT) = single-hop loaded reach; see run.py)."""
        keep = [k for k, c in enumerate(self.chargers)
                if min(manhattan(c, rf) for rf in self.refineries)
                <= self.charger_band]
        self.chargers = [self.chargers[k] for k in keep]
        self.charger_owner = [self.charger_owner[k] for k in keep]
        self.charger_toll = [self.charger_toll[k] for k in keep]
        self.charger_built = [self.charger_built[k] for k in keep]

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

    # ── v18 (column Q): the matter field + the build machinery ────────────
    def _gen_matter(self) -> None:
        """Seed the SEPARATE matter field: a build_matter-fraction of mirror-pairs
        of matter-bearing rocks, disjoint from the ore field and mirror-symmetric
        about y=grid/2 (so the two companies face identical matter geography — the
        twin-fleet placebo survives). Drawn from a DEDICATED RandomState
        (seed+90001), so the main stream is never perturbed and every ore column
        stays bit-identical. Matter is mined-to-pool at the rock (no haul), so it
        never enters ore load/parcels/conservation."""
        sc = self.grid / GRID
        n_ore_pairs = len(self.sources) // 2
        n_pairs = int(round(self.build_matter * MATTER_PER_ORE_PAIR * n_ore_pairs))
        if n_pairs <= 0:
            return
        # DEDICATED stream keyed off field size + seed (never self.rng), so the
        # matter layout is reproducible and the main draw sequence is untouched.
        mrng = np.random.RandomState(90001 + 7 * len(self.sources)
                                     + 131 * self.rng_seed)
        taken = set(self.refineries) | set(self.chargers) | set(self.sources)
        pos, misses = [], 0
        while len(pos) < n_pairs:
            x = int(mrng.uniform(3 * sc, 29 * sc))
            y = int(mrng.uniform(3 * sc, 13 * sc))       # top half; mirror below
            p_ = (x, y)
            if p_ in taken or any(manhattan(p_, q) < 4 for q in pos):
                misses += 1
                if misses > 64 * max(1, n_pairs):
                    break
                continue
            pos.append(p_)
            misses = 0
        stocks = [int(mrng.uniform(8, 20)) for _ in range(len(pos))]
        self.matter_sources = pos + [(x, self.grid - y) for x, y in pos]
        self.matter_stock = stocks + list(stocks)
        self.matter_initial = sum(self.matter_stock)

    def pick_matter(self, r: Robot) -> int:
        """Mine matter at whichever matter rock the robot stands on: MATTER_HAUL
        units (or the remainder) flow straight into the robot's COMPANY pool — no
        cargo, no haul (the resource cost is the trip battery + the ore trip
        forgone). Returns units mined. Pure v18 path (gated by the caller)."""
        for i, pos in enumerate(self.matter_sources):
            if r.pos != pos or self.matter_stock[i] <= 0:
                continue
            q = min(MATTER_HAUL, self.matter_stock[i])
            self.matter_stock[i] -= q
            self.company[r.company]["matter"] += q
            self.company[r.company]["matter_mined"] += q
            self.matter_mined += q
            return q
        return 0

    def nearest_matter(self, co: int, from_pos):
        """(pos, dist) of the nearest STOCKED matter rock to `from_pos` — the
        gatherer target. Company-neutral (matter is un-owned in the field until
        mined). None if the matter field is exhausted."""
        best, best_d = None, float("inf")
        for pos, s in zip(self.matter_sources, self.matter_stock):
            if s <= 0:
                continue
            d = manhattan(from_pos, pos)
            if d < best_d:
                best, best_d = pos, d
        return (best, best_d) if best is not None else (None, 0)

    def _build_site(self, co: int):
        """Placement policy — derived from the EXISTING loaded-haul valuation (the
        same BATTERY_MAX/(eff·(1+LOADED_MULT)) loaded reach Φ prices), NOT a new
        planner. It sites the charger WHERE THE COMPANY'S OWN STRANDING CONCENTRATES,
        as a within-loaded-reach STEPPING STONE toward the home refinery:

          (a) TRAPPED-RETURN mode (the binding N=240 stranding): among the company's
              loaded drones that cannot reach the home refinery loaded even from a
              FULL charge (dist > loaded_reach — the exact plateau signature), take
              the LOAD-weighted centroid and place the charger on the corridor from
              the refinery toward that centroid, at 0.9·loaded_reach from the
              refinery (so its charger→refinery loaded leg is feasible and it
              intercepts the trapped corridor a hop short of the dead end).
          (b) FAR-ORE fallback (early game, before any cargo is trapped): the
              highest forgone-far-ore rock (stock×charge-distance on this company's
              side), stepping-stone-placed the same way on that rock's corridor.

        Deterministic given world state; returns (None, ·, ·) if no novel,
        un-crowded site exists (a site within 3 cells of an existing charger, or on
        a facility, is rejected — no stacking)."""
        ref = self.refineries[self._home_ref(co)]
        reach = BATTERY_MAX / (1.0 + LOADED_MULT)      # nominal loaded reach (eff~1)

        def stepping_stone(cx, cy):
            """A point 0.9·reach from the refinery toward (cx, cy)."""
            d = abs(cx - ref[0]) + abs(cy - ref[1])
            frac = min(1.0, 0.9 * reach / max(d, 1.0))
            return (int(round(ref[0] + frac * (cx - ref[0]))),
                    int(round(ref[1] + frac * (cy - ref[1]))))

        trapped = [r for r in self.robots
                   if r.company == co and r.load > 0 and not r.stranded
                   and manhattan(r.pos, ref) > reach]
        if trapped:
            wsum = float(sum(r.load for r in trapped))
            cx = sum(r.pos[0] * r.load for r in trapped) / wsum
            cy = sum(r.pos[1] * r.load for r in trapped) / wsum
            site, rock, forgone = stepping_stone(cx, cy), -1, round(wsum, 1)
        else:
            own_ch = [c for c, o in zip(self.chargers, self.charger_owner)
                      if o is None or o == co]
            best_i, best_score = -1, 0.0
            for i, src in enumerate(self.sources):
                s = self.stock[i]
                if s <= 0:
                    continue
                if manhattan(src, ref) > min(manhattan(src, self.refineries[j])
                                             for j in range(len(self.refineries))) + 1:
                    continue                       # rival's side — not our stranding
                d_ch = min((manhattan(src, c) for c in own_ch),
                           default=manhattan(src, ref))
                score = s * d_ch
                if score > best_score:
                    best_i, best_score = i, score
            if best_i < 0:
                return None, -1, 0.0
            src = self.sources[best_i]
            site, rock, forgone = stepping_stone(src[0], src[1]), best_i, best_score
        block = set(self.chargers) | set(self.refineries)
        if site in block or any(manhattan(site, c) < 3 for c in self.chargers):
            return None, rock, forgone
        return site, rock, forgone

    def build_step(self) -> None:
        """Once per tick (called at TICK START from BaseArm.tick, BEFORE EV/drives/
        encounters, so a new charger is present for THIS tick's routing and never
        appears mid-encounter — evaluated Φ == executed Φ preserved). Each company
        that can AFFORD a charger (matter ≥ MATTER_COST and credit ≥
        BUILD_CREDIT_COST) and is under its build_budget places ONE at its
        forgone-far-ore site. Matter leaves the pool; credit leaves the company
        (booked to build_spend, so ledger_accounted stays exact). No-op when build
        is off ⇒ bit-identical."""
        if not self.build:
            return
        for co in range(2):
            c = self.company[co]
            if c["built"] >= self.build_budget:
                continue
            if c["matter"] < MATTER_COST or c["credit"] < BUILD_CREDIT_COST:
                continue
            site, rock, forgone = self._build_site(co)
            if site is None:
                continue
            c["matter"] -= MATTER_COST
            c["credit"] -= BUILD_CREDIT_COST
            c["build_spend"] += BUILD_CREDIT_COST
            c["built"] += 1
            self.chargers.append(site)
            self.charger_owner.append(co)
            self.charger_toll.append(self.toll_level)
            self.charger_built.append(True)
            self.built_log.append(dict(tick=self.tick, co=co, pos=site,
                                       rock=rock, forgone=round(forgone, 1)))

    def assign_gatherers(self) -> None:
        """v18: designate this tick's matter gatherers, ONCE per tick (not per
        robot — O(N·matter)). A company that is under budget and short of matter
        for its next charger (pool < MATTER_COST) sends its GATHERERS_MAX nearest
        battery-able empty drones to the matter field; the rest keep mining ore.
        The rid-sorted cap prevents a whole-fleet matter stampede (the ore-vs-matter
        trade the KILL measures). intent() reads _gather_target; empty when off."""
        self._gather_target = {}
        if not self.build:
            return
        if not any(s > 0 for s in self.matter_stock):
            return
        for co in range(2):
            c = self.company[co]
            if c["built"] >= self.build_budget or c["matter"] >= MATTER_COST:
                continue
            cand = []
            for x in self.robots:
                if x.company != co or x.stranded or x.load > 0:
                    continue
                p, dd = self.nearest_matter(co, x.pos)
                if p is None:
                    continue
                if x.bat() > 3.0 * dd * x.eff + RESCUE_FLOOR:   # round-trip+safety
                    cand.append((x.rid, p))
            cand.sort()
            for rid, p in cand[:GATHERERS_MAX]:
                self._gather_target[rid] = p

    def matter_conserved(self) -> bool:
        """v18: every mined matter unit is either sitting in a company pool or was
        spent building (MATTER_COST per built charger). Field remaining + pools +
        spent == initial. Trivially True when the matter field is empty."""
        remaining = sum(self.matter_stock)
        pooled = sum(self.company[c]["matter"] for c in range(2))
        spent = sum(self.company[c]["built"] for c in range(2)) * MATTER_COST
        return abs(remaining + pooled + spent - self.matter_initial) < 1e-9 \
            and abs(pooled + spent - self.matter_mined) < 1e-9

    def toll_conserved(self) -> bool:
        """v18: tolls are a pure guest→owner CREDIT transfer — total earned equals
        total paid (net-zero in Σ company credit, so ledger_accounted is intact)."""
        return abs(sum(self.company[c]["toll_earned"] for c in range(2))
                   - sum(self.company[c]["toll_paid"] for c in range(2))) < 1e-9

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

    def dumb_claim(self, r) -> int:
        """v20 (column S): the DUMB routing brain. Greedy nearest-KNOWN-stocked
        asteroid — it drops best_claim's richest-per-distance Φ tradeoff and just
        heads for the closest rock it BELIEVES is stocked, plus a registered noise
        term (dumb planners misjudge distance). The candidate set is IDENTICAL to
        best_claim (same stock_belief>0 filter, same live-sense side effects); ONLY
        the scoring is dumbed — this isolates 'dumb ROUTING' from the bargaining
        brain (deal Φ is untouched). Noise is drawn from the DEDICATED nav_dumb
        stream (seed+262626), so nav_dumb OFF never perturbs the main stream and
        every prior column stays bit-identical. Ties/empties fall back to r.sector,
        exactly like best_claim."""
        best, best_score = r.sector, float("inf")
        for i, src in enumerate(self.sources):
            s = self.stock_belief(r, i)
            if s <= 0:
                continue
            # greedy: minimize distance (NO richness term) + Gaussian noise
            score = manhattan(r.pos, src) + self._nav_rng.normal(0.0, NAV_DUMB_NOISE)
            if score < best_score:
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
        if self.reputation:
            self._blacklist_gossip_step()  # v22: one hop of blacklist flooding
        if self.order_book:
            self._discover_orders()        # v23: stigmergic order discovery
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

    def _blacklist_gossip_step(self) -> None:
        """v22 (column U): one hop of blacklist flooding — a same-company
        fleet-mate within Chebyshev r_radio UNIONS in a neighbour's blacklist, so
        a mark spreads by CONTACT exactly like a gossiped belief entry (per-robot
        blacklists). Every blacklist is SNAPSHOT first, so a robot never adopts a
        set another robot adopted this same tick: propagation is exactly one hop
        per tick (order-independent, no RNG), and a distant fleet-mate stays clean
        until a chain of contacts relays the mark to it. Cross-company robots never
        adopt (a fleet's warnings stay within the fleet). O(N) spatial-hashed by
        r_radio-sized cells (the same bucketing as _gossip_step / encounters).
        Runs in the drive/world phase from sense_step, BEFORE the encounter phase,
        so refusals this tick already see the freshly-propagated marks."""
        R = max(1, self.r_radio)
        rs = self.robots
        snap = [set(bl) for bl in self.blacklist]      # snapshot every read set
        buckets: dict = {}
        for idx, r in enumerate(rs):
            buckets.setdefault((r.pos[0] // R, r.pos[1] // R), []).append(idx)
        for a in rs:
            cx, cy = a.pos[0] // R, a.pos[1] // R
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for j in buckets.get((cx + ox, cy + oy), ()):
                        b = rs[j]
                        if b.rid == a.rid or b.company != a.company:
                            continue
                        if (abs(a.pos[0] - b.pos[0]) <= R
                                and abs(a.pos[1] - b.pos[1]) <= R
                                and snap[b.rid]):
                            self.blacklist[a.rid] |= snap[b.rid]

    # ── v25 (column X): the central planner (COMMAND regime) ─────────────
    def _loaded_reach(self, r: Robot, ref_pos) -> bool:
        """Can robot r carry a load to ref_pos in ONE loaded hop? The shared
        single-hop reachability primitive every arm's routing already uses —
        NOT a multi-hop router (the P24 caveat). Reads TRUE battery (physics)."""
        return manhattan(r.pos, ref_pos) * r.eff * (1 + LOADED_MULT) <= r.battery

    def _merged_belief(self, co: int):
        """The company's gossip-merged belief: per rock, the FRESHEST (belief,
        last_seen) across its same-company robots — exactly the fleet-wide union
        a dispatcher would hold off the SAME radio (under gossip each robot's map
        is per-rid; _bx handles the free-radio case too). NEVER field truth: it is
        assembled only from what the fleet has actually sensed and relayed."""
        n_src = len(self.sources)
        bel = [0.0] * n_src
        ls = [-1] * n_src
        for r in self.robots:
            if r.company != co:
                continue
            bx = self._bx(r)
            row_ls = self.last_seen[bx]
            row_bel = self.belief[bx]
            for i in range(n_src):
                if row_ls[i] > ls[i]:
                    ls[i] = row_ls[i]
                    bel[i] = row_bel[i]
        return bel, ls

    def _handoff_taker(self, giver: Robot, co: int):
        """A LOCAL same-company drone that can carry the giver's cargo one loaded
        hop to a refinery: within CMD_HANDOFF_RADIUS, with spare cap, itself single-
        hop-reachable to a refinery, and strictly CLOSER to a refinery than the giver
        (so the hand-off makes progress). Nearest-then-rid tie-break; deterministic,
        single-hop only — no stepping-stone chain lookahead (the P24 caveat)."""
        g_to_ref = min(manhattan(giver.pos, rf) for rf in self.refineries)
        best = None
        best_key = None
        for t in self.robots:
            if t.company != co or t.rid == giver.rid or t.stranded:
                continue
            if t.cap - t.load <= 0:
                continue
            cd = max(abs(giver.pos[0] - t.pos[0]), abs(giver.pos[1] - t.pos[1]))
            if cd > CMD_HANDOFF_RADIUS:
                continue
            if not any(self._loaded_reach(t, rf) for rf in self.refineries):
                continue
            if min(manhattan(t.pos, rf) for rf in self.refineries) >= g_to_ref:
                continue
            key = (cd, t.rid)
            if best_key is None or key < best_key:
                best, best_key = t, key
        return best

    def _plan_company(self, co: int) -> dict:
        """The planner's STANDING orders for a company, on the merged belief. It
        REPLACES the allocation decision — which rock an empty drone mines
        (deconflicted so the fleet covers the field, not dogpiles the richest rock)
        and whether a stuck loaded drone hands off — while the MECHANICAL reflexes
        (deliver-when-loaded, charge-when-low) stay the shared single-hop primitives
        every arm uses (the P24 caveat: same movement/valuation code). Orders are
        standing (a mining beat persists across load cycles), so a drone never idles
        between re-plans. Deterministic (index/distance tie-breaks; no RNG).

        A spec is ('mine', rock) or ('handoff', taker_rid); drones with no spec use
        the shared reflex (loaded → deliver/charge, empty+low → charge)."""
        from swarm.value import safe_return_threshold
        bel, ls = self._merged_belief(co)
        robots = [r for r in self.robots if r.company == co and not r.stranded]
        plan: dict = {}
        # (1) LOADED drones BEYOND single-hop refinery reach: a LOCAL directed hand-off
        #     if a viable taker exists; otherwise no order (the shared deliver/charge
        #     reflex carries them — never a stepping-stone router, the P24 caveat).
        for r in robots:
            if r.load <= 0:
                continue
            if any(self._loaded_reach(r, rf) for rf in self.refineries):
                continue                     # can deliver directly → shared reflex
            taker = self._handoff_taker(r, co)
            if taker is not None:
                plan[r.rid] = ("handoff", taker.rid)
        # (2) EMPTY healthy drones: a deconflicted mine target. The SCORE is the
        #     baseline's own best_claim (richest-per-distance on the merged belief),
        #     divided by a congestion factor (1 + drones already assigned there) so
        #     the fleet SPREADS off the single richest rock onto the next-best. The
        #     distance term keeps every pick local/sustainable (command never routes
        #     a drone anywhere its own prudent policy would not), so the ONLY change
        #     vs baseline is coordinated deconfliction. Deterministic (rid order).
        rocks = [i for i in range(len(self.sources)) if bel[i] > 1e-9]
        assigned = {i: 0 for i in rocks}
        belief_ages = []
        for r in sorted((x for x in robots if x.load <= 0), key=lambda x: x.rid):
            if r.bat() < safe_return_threshold(r, self) or not rocks:
                continue                     # low battery / no rocks → shared reflex
            best, best_score = None, -1.0
            for i in rocks:
                base = bel[i] / (manhattan(r.pos, self.sources[i]) + 4.0)
                score = base / (1 + assigned[i])
                if score > best_score:
                    best, best_score = i, score
            plan[r.rid] = ("mine", best)
            assigned[best] += 1
            belief_ages.append(self.tick - ls[best])
        if belief_ages:
            self.cmd_belief_age_traj.append(
                (self.tick, float(sum(belief_ages) / len(belief_ages))))
        return plan

    def command_step(self) -> None:
        """Re-plan (every PLAN_PERIOD) on the merged belief, then propagate the
        authoritative plan outward from each company HQ (its home refinery) by the
        SAME radio physics as gossip: one hop/tick through the same-company Chebyshev
        r_radio contact graph. A drone the plan has not reached keeps its last order
        (or the default solo policy if never reached). Runs in the drive/world phase
        BEFORE drive reads targets; deterministic, consumes no RNG. Off ⇒ returns
        immediately (bit-identical to every prior column)."""
        if not self.command:
            return
        if self.tick % PLAN_PERIOD == 0:
            version = self.cmd_plan_versions.setdefault(self.tick, {})
            for co in range(2):
                version.update(self._plan_company(co))
                self.cmd_auth_tick[co] = self.tick
        R = max(1, self.r_radio)
        # (a) seed: robots within r_radio of their HQ hear the broadcast directly.
        for r in self.robots:
            if r.stranded:
                continue
            at = self.cmd_auth_tick[r.company]
            if at < 0 or self.cmd_held_tick[r.rid] >= at:
                continue
            hq = self.refineries[self._home_ref(r.company)]
            if max(abs(r.pos[0] - hq[0]), abs(r.pos[1] - hq[1])) <= R:
                self.cmd_reach_lat.append(self.tick - at)
                self.cmd_held_tick[r.rid] = at
        # (b) flood one hop (snapshot first ⇒ one hop/tick, order-independent —
        #     the exact _gossip_step discipline). O(N) spatial-hashed by r_radio.
        snap = self.cmd_held_tick[:]
        rs = self.robots
        buckets: dict = {}
        for idx, r in enumerate(rs):
            buckets.setdefault((r.pos[0] // R, r.pos[1] // R), []).append(idx)
        for a in rs:
            if a.stranded:
                continue
            cx, cy = a.pos[0] // R, a.pos[1] // R
            best = snap[a.rid]
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for j in buckets.get((cx + ox, cy + oy), ()):
                        b = rs[j]
                        if b.company != a.company or b.rid == a.rid:
                            continue
                        if (abs(a.pos[0] - b.pos[0]) <= R
                                and abs(a.pos[1] - b.pos[1]) <= R
                                and snap[b.rid] > best):
                            best = snap[b.rid]
            if best > self.cmd_held_tick[a.rid]:
                self.cmd_reach_lat.append(self.tick - best)
                self.cmd_held_tick[a.rid] = best

    def cmd_spec(self, r: Robot):
        """The raw target spec robot r currently holds (the plan VERSION it has
        actually received by radio — a stale local plan is executed as-is), or
        None if it has no order / the order lapsed."""
        ht = self.cmd_held_tick[r.rid]
        if ht < 0:
            return None
        return self.cmd_plan_versions.get(ht, {}).get(r.rid)

    def cmd_resolve(self, r: Robot):
        """Resolve r's STANDING order to a target POSITION for its CURRENT state,
        or None → the shared default reflex handles it (loaded → deliver/charge;
        empty+low → charge; no order → solo initiative). Tallies mine-execution
        staleness: a commanded empty drone acting on a mine order whose target rock
        is truly depleted is the plan-went-stale-at-execution signature. Called once
        per drive tick from intent() under w.command."""
        spec = self.cmd_spec(r)
        if r.load > 0:
            # loaded: a directed hand-off overrides; else the shared deliver reflex.
            if spec is not None and spec[0] == "handoff":
                taker = self.robots[spec[1]]
                if not taker.stranded and taker.cap - taker.load > 0:
                    return taker.pos
            return None
        # empty: mine the assigned beat (unless the drone now believes it depleted —
        # then defer to solo initiative rather than idle on a known-empty rock).
        if spec is not None and spec[0] == "mine":
            i = spec[1]
            self.cmd_mine_exec += 1
            if self.stock[i] <= 0:
                self.cmd_mine_stale += 1
            if self.stock_belief(r, i) <= 0:
                return None
            return self.sources[i]
        return None

    def deadlock_step(self) -> None:
        """Count RISING-EDGE entries into the routing deadlock: loaded, at ~full
        battery, and beyond single-hop LOADED reach of EVERY refinery (the P24
        signature — a charged hauler that still cannot deliver in one hop). A pure
        read-only predicate over the SHARED routing physics, so the counts are ~equal
        across regimes iff routing competence is shared — the settlement-vs-routing
        contamination check. Off ⇒ never called (bit-identical)."""
        if not self.deadlock_track:
            return
        full = DEADLOCK_FULL * BATTERY_MAX
        for r in self.robots:
            stuck = (r.load > 0 and not r.stranded and r.battery >= full
                     and not any(self._loaded_reach(r, rf)
                                 for rf in self.refineries))
            if stuck and not self._in_deadlock[r.rid]:
                self.deadlock_count += 1
            self._in_deadlock[r.rid] = stuck

    # ── v28 (column AA): mortality and the persistence of paper ───────────
    def death_step(self) -> None:
        """Resolve deaths at TICK START (from BaseArm.tick, alongside field_step/
        build_step) — BEFORE drives and every bundle evaluation, so a death never
        lands mid-encounter and the claim stack Φ prices is stable through the whole
        encounter phase (evaluated Φ == executed Φ preserved). Two death sources,
        both feeding the SAME regime-driven resolution:
          (1) FLATLINE — a robot STRANDED for FLATLINE_TICKS consecutive ticks with
              no rescue (the endogenous, trajectory-dependent base mortality).
          (2) WEAR-OUT — a chassis reaching its pre-drawn natural death tick (age
              hazard, from the DEDICATED stream, IDENTICAL across regimes).
        No-op when mortality is off ⇒ every prior column is bit-identical."""
        if not self.mortality:
            return
        for r in self.robots:
            if r.dead:
                continue
            # (1) flatline bookkeeping: count consecutive stranded ticks, reset on rescue
            if r.stranded:
                self._strand_ticks[r.rid] += 1
            else:
                self._strand_ticks[r.rid] = 0
            cause = None
            if self.wearout and self.tick >= self._wear_death_tick[r.rid]:
                cause = "wearout"
            elif self._strand_ticks[r.rid] >= FLATLINE_TICKS:
                cause = "flatline"
            if cause is not None:
                self.death_resolve(r, cause)

    def death_resolve(self, r: Robot, cause: str) -> None:
        """Kill chassis r and settle the paper it leaves behind. Two effects,
        ONE regime-invariant, ONE regime-dependent:

        (A) The dead robot's CARRIED cargo is written off to stock_lost (material
            DESTROYED, like stranded cargo — a corpse cannot deliver). Every claim
            riding that cargo is an upstream COUNTERPARTY's claim that now cannot
            settle, so each such claimant's expected settlement (claim_value) is
            written down. Identical in every regime (physical loss).

        (B) The dead robot's OWN outstanding claims — the (r.rid, share) entries it
            banked on parcels OTHER (living) robots still carry — resolve by regime:
              claims-die / risk-premium: VOIDED (rewritten to CLAIM_VOID; the payout
                is destroyed at delivery, booked to claims_voided — the ledger balances).
              estates: re-pointed to r's company TREASURY (rewritten to the heir
                sentinel; the payout settles to the treasury at delivery).
            No credit exists yet (nothing delivered), so (B) touches only the paper;
            the credit consequence lands at settlement (drop)."""
        # snapshot the freeze-out context / audit fields BEFORE clearing
        own_claim = r.claim_value
        cargo = r.load
        # (A) write off carried cargo; write down every counterparty claim on it.
        # v29 (column AB): this is the CROSS-PARCEL contagion channel. When a
        # shock-TAINTED carrier dies (it burned energy on cargo whose settlement
        # vanished, then stranded), its death strands OTHER parcels it was hauling —
        # each upstream claimant on those parcels is a CONTAGION victim, one hop
        # deeper than the carrier (hop = carrier taint + 1). A write-off on a
        # far-band parcel is a DIRECT hit (hop 0). A death with no shock taint on a
        # non-far parcel is a BASE-mortality write-off (not attributed; the no-shock
        # control carries these). Under the CLEARINGHOUSE the counterparty is made
        # whole from the pool (pro-rata haircut if dry) — that is how the CCP CAPS
        # contagion. Off ⇒ exactly the v28 line (only claim_value drops).
        r_taint = self.shock_taint[r.rid]
        for p in r.parcels:
            far = p["origin"] in self.shock_far
            for claim in p.get("claims", ()):
                cid = claim[0]
                if cid >= 0 and cid != r.rid:
                    # 2- or 3-tuple: field 1 is the PHYSICAL share
                    exposure = claim[1] * V_DELIVER
                    realized_wd = exposure
                    if self.clearinghouse:
                        cov = min(self.ccp_pool, exposure)
                        self.ccp_pool -= cov
                        self.ccp_payouts += cov
                        self.ccp_haircut += exposure - cov
                        self.robots[cid].credit += cov
                        self.company[self.robots[cid].company]["credit"] += cov
                        realized_wd = exposure - cov
                    self.robots[cid].claim_value -= exposure
                    if self.shocked and far:
                        self._taint(cid, 0)
                        self._record_wd(cid, exposure, realized_wd, "direct", 0, True)
                    elif self.shocked and r_taint is not None:
                        self._taint(cid, r_taint + 1)
                        self._record_wd(cid, exposure, realized_wd,
                                        "contagion", r_taint + 1, False)
        if cargo:
            self.stock_lost += cargo
        r.load = 0
        r.load_prov = [0, 0]
        r.parcels = []
        r.claim_value = 0.0
        # (B) resolve the dead robot's OWN held claims on LIVING robots' parcels
        heir = -(2 + r.company)                 # estate sentinel for r's company
        inherited = 0.0
        if self.bills and (self.claim_void or self.claim_estate):
            target = CLAIM_VOID if self.claim_void else heir
            for other in self.robots:
                if other.rid == r.rid or other.dead:
                    continue
                for p in other.parcels:
                    cl = p.get("claims")
                    if not cl:
                        continue
                    for k in range(len(cl)):
                        if cl[k][0] == r.rid:
                            inherited += cl[k][1] * V_DELIVER
                            cl[k] = (target,) + tuple(cl[k][1:])
        # finalize the death
        r.dead = True
        r.stranded = True                       # a corpse stays out of every rescue path
        r.charge_queued_at = -1
        r.busy_until = -1
        self._strand_ticks[r.rid] = 0
        self.deaths += 1
        if cause == "wearout":
            self.death_wearout += 1
        else:
            self.death_flatline += 1
        self.death_log.append(dict(
            tick=self.tick, rid=r.rid, co=r.company, cause=cause,
            cargo=cargo, own_claim=round(own_claim, 4),
            inherited=round(inherited, 4),
            regime=self.death_regime,
            bat_pct=round(r.battery / BATTERY_MAX, 4)))

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

    # ── v29 (column AB): the crash ───────────────────────────────────────
    def shock_step(self) -> None:
        """Fire the far-band shock ONCE at shock_tick — called from BaseArm.tick at
        TICK START (alongside field_step/death_step), BEFORE any bundle evaluation,
        so the state it changes (stock, taint) is stable through the whole encounter
        phase (evaluated Φ == executed Φ preserved). The far band goes dark via the
        v11 departure machinery: every far-band asteroid's true stock is erased
        (booked to stock_lost so material conservation holds) and stock→0, so NO new
        far-band ore is minable. In-transit far-band cargo keeps its full Φ value
        (Φ never sees the shock) but now settles at SHOCK_VALUE_FLOOR at drop — the
        write-down lands mid-flight. Directly-exposed agents (holders of, or
        claimants on, an in-transit far-band parcel) are tainted at depth 0 so the
        death cascade can attribute contagion by hop-distance. No-op when the shock
        is off (shock_tick None) ⇒ every prior column is bit-identical."""
        if self.shock_tick is None or self.shocked or self.tick < self.shock_tick:
            return
        self.shocked = True
        for i in self.shock_far:
            if self.stock[i] > 0:
                self.shock_far_stock_lost += self.stock[i]
                self.stock_lost += self.stock[i]
                self.stock[i] = 0
        # taint the direct victims: anyone CARRYING an in-transit far-band parcel …
        for r in self.robots:
            if not r.dead and any(p["origin"] in self.shock_far for p in r.parcels):
                self._taint(r.rid, 0)
        # … or HOLDING A CLAIM on someone's in-transit far-band parcel (paper hit).
        # In the SAME pass, SNAPSHOT the in-flight far-band leverage by hop (chain
        # depth) AT the crash: the current holder's residual is hop 0 (a DIRECT victim,
        # holds the dark ore); each upstream claimant is hop = depth-up-the-chain
        # (CONTAGION — paper on a settlement that now cannot complete at expected
        # value). This is "the in-transit claim stacks reference settlements that
        # cannot complete" verbatim, measured at the moment of the crash (when the deep
        # chains are still in flight — by the horizon they have delivered-at-0, voided
        # on a claimant's death, or deadlocked, so this is the robust reach measure).
        for other in self.robots:
            if other.dead:
                continue
            for p in other.parcels:
                if p["origin"] not in self.shock_far:
                    continue
                claims = p.get("claims", ())
                for claim in claims:
                    if claim[0] >= 0:
                        self._taint(claim[0], 0)
                n = len(claims)
                resid = 1.0 - sum(sh for _rid, sh, *_ in claims)
                self._exp_record(0, resid * V_DELIVER)          # holder = direct hop 0
                for i, claim in enumerate(claims):
                    if claim[0] != CLAIM_VOID:
                        self._exp_record(n - i, claim[1] * V_DELIVER)   # up the chain
        self.field_log.append(dict(t=self.tick, kind="shock",
                                   n_far=len(self.shock_far),
                                   stock_lost=self.shock_far_stock_lost))

    def _exp_record(self, hop: int, val: float) -> None:
        """Accumulate far-band leverage exposure at chain-depth `hop`."""
        self.shock_exp_by_hop[hop] = self.shock_exp_by_hop.get(hop, 0.0) + val
        self.shock_exp_cnt[hop] = self.shock_exp_cnt.get(hop, 0) + 1

    def _taint(self, rid: int, depth: int) -> None:
        """Mark robot `rid` shock-tainted at contagion `depth` (the min ever seen —
        a shallower path wins). None means untainted. Pure bookkeeping."""
        cur = self.shock_taint[rid]
        if cur is None or depth < cur:
            self.shock_taint[rid] = depth

    def _record_wd(self, rid, exposure, realized, cause, hop, far) -> None:
        """Append one write-down event. `exposure` is the pre-CCP loss (the shock's
        REACH — regime-comparable); `realized` is what the claimant actually eats
        (0/haircut under the CCP, == exposure under gross). cause ∈ {direct,
        contagion}; hop is the counterparty-graph distance from the darkened region
        (0 = direct victim). Pure bookkeeping — never touches Φ/physics/RNG."""
        self.writedown_log.append(dict(
            tick=self.tick, rid=rid, exposure=round(float(exposure), 6),
            realized=round(float(realized), 6), cause=cause, hop=hop,
            far=bool(far)))

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

    def _home_ref(self, co: int) -> int:
        """The refinery index company `co` owns (its delivery target for firm
        settlement); falls back to refinery 0 for the single-refinery presets."""
        for i, o in enumerate(self.ref_owner):
            if o == co:
                return i
        return 0

    def _firm_transfer_price(self, taker: Robot, q: int) -> float:
        """v17 PHASE 2 (snhp+firm): the internal transfer price the treasury pays
        the receiving robot on a within-company handoff — its marginal haul cost
        (shadow-priced energy to its home refinery) plus a fixed margin on the
        cargo's home value. Deterministic (no RNG); a credit figure only."""
        ref = self._home_ref(taker.company)
        haul = manhattan(taker.pos, self.refineries[ref]) * taker.eff \
            * (1 + LOADED_MULT) * taker.ev
        margin = FIRM_MARGIN * q * V_DELIVER
        return haul + margin

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
        plus a guest penalty at rival infrastructure (guests charge slower).
        v18 (column Q): a guest ALSO pays a routing penalty proportional to the
        charger's toll (TOLL_ROUTE_PENALTY·toll) — the toll deters guests, so a
        priced charger is avoided when a cheaper option is comparably near (the
        deadweight channel behind the interior toll optimum). The toll term is
        identically 0 at every toll-free (all preset) charger, so this is
        bit-identical for every prior column."""
        best, best_eff, best_d = None, float("inf"), 0
        toll = self.charger_toll
        for k, (pos, owner) in enumerate(zip(self.chargers, self.charger_owner)):
            d = manhattan(r.pos, pos)
            guest = not (owner is None or owner == r.company)
            eff_d = d + (GUEST_PENALTY + TOLL_ROUTE_PENALTY * toll[k]
                         if guest else 0)
            if eff_d < best_eff:
                best, best_eff, best_d = pos, eff_d, d
        return best, best_d

    def _maybe_strand(self, r: Robot) -> None:
        if r.dead:                              # v28: a corpse is already stranded and
            return                              # never un-strands (guard is a no-op off)
        r.battery = max(0.0, r.battery)
        if r.battery < RESCUE_FLOOR and \
                all(manhattan(r.pos, c) > 1 for c in self.chargers):
            if not r.stranded:                  # v29: log the strand ONSET (the pre/post
                self.strand_log.append((self.tick, r.rid))   # scar reads it; append-only,
            r.stranded = True                   # never read by physics ⇒ bit-safe off

    def _new_parcel(self, origin: int) -> dict:
        """A fresh 0-hop parcel for one mined unit. Under bills it carries an
        empty claim stack (holder residual == 1); under firm it carries a 0
        advanced-transfer-price. Keys are added ONLY under their flag, so a
        lineage-only parcel is the exact pre-PHASE-2 dict (bit-identical)."""
        p = {"origin": origin, "hops": 0, "chain": []}
        if self.bills:
            p["claims"] = []
        if self.claims_transferable:
            # v30 (column M2): per-claim circulation instruments, aligned index-for-
            # index with p["claims"] and travelling with the parcel through every
            # cargo hand-off. cx = endorsements so far (velocity); cb = birth tick.
            p["cx"] = []
            p["cb"] = []
        if self.firm_relay:
            p["advanced"] = 0.0
        if self.dwell:
            # P23e: acquisition stamps. A unit is mined ON its asteroid, so the
            # holder's acquire position == the source position; acq_* are reset at
            # each handoff (transfer_cargo) so per-leg dwell is (tick − acq_tick)
            # and its geodesic counterfactual manhattan(acq_pos, holder_pos).
            src = self.sources[origin]
            p["acq_tick"] = self.tick
            p["acq_pos"] = src
            p["mined_tick"] = self.tick
            p["src_pos"] = src
            p["uid"] = self._parcel_uid
            self._parcel_uid += 1
        return p

    def _leg_dwell(self, p, holder_pos):
        """P23e: (dwell, cf, excess) for the current holder's open leg on parcel
        p. dwell = ticks held since acquisition; cf = the geodesic ticks a solo
        carrier would need for the ground actually covered (manhattan from where
        the holder acquired it to holder_pos, speed 1 cell/tick); excess = dwell
        above cf (≥0 always — net displacement ≤ ticks moved)."""
        dwell = self.tick - p["acq_tick"]
        cf = manhattan(p["acq_pos"], holder_pos)
        return dwell, cf, max(0, dwell - cf)

    def leg_decay(self, p, holder_pos) -> float:
        """P23e contingent split: exp(-λ·excess) — the payout-share multiplier
        that decays with dwell ABOVE the counterfactual (==1 at or below cf).
        Computed from PRE-handoff parcel state, so it is identical in Φ
        evaluation and at execution (evaluated Φ == executed Φ preserved)."""
        _, _, excess = self._leg_dwell(p, holder_pos)
        return math.exp(-DWELL_DECAY_LAMBDA * excess)

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
            if self.depots:                    # v31: fresh-mined cargo is not a relay
                r.relay_from = None             # leg — clear the anti-churn token
            self.stock[s] -= q
            self.own_mined[r.company][s] += q  # v10b: rival-rate accounting
            self.mined_from[s] += q            # v11: per-asteroid provenance
            if self.lineage and q:             # v17: one 0-hop parcel per unit,
                r.parcels.extend(              # tagged with its origin rock
                    self._new_parcel(s) for _ in range(q))
            return q
        return 0

    def _settle_parcel_bills(self, p, r: Robot, rate: float, vm: float) -> None:
        """v29 (column AB): distribute ONE delivered bills-parcel's credit on the
        shock/clearinghouse path. `vm` is the parcel's value multiplier (1.0, or
        SHOCK_VALUE_FLOOR for an in-transit far-band unit). At vm==1 with the
        clearinghouse OFF this reduces EXACTLY to the pre-v29 distribution (each
        live recipient books share·rate·V, the deliverer keeps the residual).

        GROSS BILATERAL (clearinghouse off): each recipient books its REALIZED share
        share·rate·V·vm; the (1−vm) gap is that recipient's write-down (it eats it —
        every claim a bilateral position). CLEARINGHOUSE: every settlement pays a
        CCP_FEE·face fee into the pool (building the reserve from t=0), then the pool
        TOPS the live recipients back toward face (pro-rata by share, capped by the
        pool — the un-coverable remainder is the pro-rata HAIRCUT, the registered
        waterfall). A VOIDED share (dead claimant) is never topped up (no corpse to
        pay); its realized value is destroyed to claims_voided, exactly as gross.

        The parcel's (1−vm)·V is booked to shock_writedown ONCE (it covers the
        deliver-pool shortfall AND the collapsed tariff), so the ledger closes to
        V·delivered for ANY cover — the fee and cover cancel in the credit+pool sum
        (derivation in SPEC v29; the ledger test is the gate). Records each live
        recipient's write-down for the contagion-depth histogram, by hop up the
        counterparty web (deliverer hop 0 = direct; upstream claimants = contagion)."""
        V = V_DELIVER
        face = rate * V
        ccp = self.clearinghouse
        claims = []
        csum = 0.0
        for claim in p["claims"]:
            if len(claim) == 3:
                rid, share, decay = claim
                paid = share * decay
            else:
                rid, share = claim
                paid = share
            claims.append((rid, paid))
            csum += paid
        resid = 1.0 - csum
        if vm != 1.0:
            self.shock_writedown += (1.0 - vm) * V      # value that never existed
        live_paid = resid + sum(pd for rid, pd in claims if rid != CLAIM_VOID)
        cover = 0.0
        if ccp:
            # fee on the LIVE face pool only — a voided share pays no fee (no corpse
            # to charge), so charging on full face would over-collect and break the
            # ledger. Σ per-recipient fees (paid·CCP_FEE·face) == this exactly.
            fee_total = CCP_FEE * face * live_paid
            self.ccp_pool += fee_total
            self.ccp_fees += fee_total
            want = live_paid * (1.0 - vm) * face
            cover = min(self.ccp_pool, want)
            self.ccp_pool -= cover
            self.ccp_payouts += cover
            self.ccp_haircut += want - cover

        def _payout(paid):
            realized = paid * face * vm
            wd = paid * (1.0 - vm) * face                # gross write-down (exposure)
            if ccp:
                topup = (paid / live_paid * cover) if live_paid > 0 else 0.0
                realized += topup - paid * CCP_FEE * face
                wd -= topup                             # only the un-covered haircut eaten
            return realized, wd

        # hop attribution up the counterparty web: the DELIVERER physically held the
        # dark ore (hop 0 = a DIRECT victim); each upstream claimant handed the parcel
        # off earlier and now holds only PAPER on a settlement that collapsed — its
        # loss is CONTAGION, one hop further up the chain per handoff (claims are
        # appended in handoff order, so stack index i ⇒ hop = len(stack) − i). This is
        # the counterparty web: a claim referencing a future settlement is leverage,
        # and the write-down reaches everyone up the chain — depth == chain length.
        nclaims = len(claims)
        for i, (rid, paid) in enumerate(claims):
            if rid == CLAIM_VOID:
                self.claims_voided += paid * face * vm  # realized-vm destroyed
                continue
            realized, wd = _payout(paid)
            if rid < 0:                                  # estate → treasury heir
                hco = -rid - 2
                self.company[hco]["treasury"] += realized
                self.company[hco]["credit"] += realized
                self.estate_settled += realized
            else:
                cl = self.robots[rid]
                cl.credit += realized
                self.company[cl.company]["credit"] += realized
                cl.claim_value -= paid * V              # the claim is settled (at face)
            if vm != 1.0:
                self._record_wd(rid, paid * (1.0 - vm) * face, wd,
                                "contagion", nclaims - i, True)
        realized, wd = _payout(resid)                    # the deliverer's residual
        r.credit += realized
        self.company[r.company]["credit"] += realized
        if vm != 1.0:
            self._record_wd(r.rid, resid * (1.0 - vm) * face, wd, "direct", 0, True)

    def drop(self, r: Robot) -> int:
        """Refine at whichever refinery the robot stands on. Tariff is
        assessed HERE and only here, once per unit (panel refine-once)."""
        for ref_idx, pos in enumerate(self.refineries):
            if r.pos != pos or r.load <= 0:
                continue
            q, r.load = r.load, 0
            owner = self.ref_owner[ref_idx]
            rate = self.credit_rate(r.company, ref_idx)
            unit = rate * V_DELIVER             # per-unit delivery credit
            earned = unit * q
            # v29 (column AB): the shock/clearinghouse settlement path. `sw` OFF ⇒ the
            # ORIGINAL arithmetic below runs byte-for-byte (bit-identical); ON ⇒ each
            # parcel settles at its value multiplier vm (1.0, or SHOCK_VALUE_FLOOR for
            # an in-transit far-band unit) via _settle_parcel_bills, and the tariff /
            # spot credit ride the value-weighted count qval == Σ vm.
            sw = self.shocked or self.clearinghouse
            qval = 0.0
            if self.lineage:                    # v17: retire this unit's lineage
                for p in r.parcels:             # (origin, hops it took to arrive,
                    self.delivered_parcels.append(dict(   # tick, who delivered)
                        origin=p["origin"], hops=p["hops"], tick=self.tick,
                        deliverer=r.rid, chain=p["chain"]))
                    # P23e: retire the deliverer's final leg + the parcel's whole
                    # journey. total_dwell = ticks mining→delivery; its geodesic
                    # counterfactual = manhattan(source, delivering refinery). The
                    # per-leg dwells (transfer_cargo records + this final one) sum
                    # EXACTLY to total_dwell (each handoff re-stamps acq_tick, so
                    # the legs telescope). Pure bookkeeping.
                    if self.dwell:
                        dwell, cf, excess = self._leg_dwell(p, r.pos)
                        self.hop_dwells.append(dict(
                            uid=p["uid"], dwell=dwell, cf=cf, excess=excess,
                            hops=p["hops"], final=True, giver=r.rid,
                            origin=p["origin"]))
                        total = self.tick - p["mined_tick"]
                        tcf = manhattan(p["src_pos"], pos)
                        self.delivered_dwells.append(dict(
                            uid=p["uid"], total_dwell=total, total_cf=tcf,
                            inflation=total - tcf, hops=p["hops"],
                            origin=p["origin"]))
                    # v29 (column AB): the parcel's value multiplier — 1.0, or the
                    # collapsed floor for an in-transit far-band unit once the shock
                    # has fired (its ore went dark mid-flight).
                    vm = (SHOCK_VALUE_FLOOR
                          if (self.shocked and p["origin"] in self.shock_far)
                          else 1.0)
                    qval += vm
                    # v17 PHASE 2 (snhp+bill): distribute this unit's credit per
                    # its notarized claim stack — each recorded claimant is paid
                    # share × unit; the deliverer keeps the residual (1 − Σshare).
                    # P23e (contingent): a claim is a 3-tuple (rid, share, decay)
                    # and pays share·decay·unit — the DELIVERER absorbs the docked
                    # (1−decay)·share, so Σdistributed == unit EXACTLY still holds
                    # (credit conservation intact, docks reward the final hauler).
                    # Flat claims stay 2-tuples (decay ≡ 1) — bit-identical path.
                    if self.bills and sw:            # v29: shock/CCP settlement
                        self._settle_parcel_bills(p, r, rate, vm)
                    elif self.bills:                 # ── original path (bit-identical) ──
                        csum = 0.0
                        for _ci, claim in enumerate(p["claims"]):
                            if len(claim) == 3:
                                rid, share, decay = claim
                                paid = share * decay
                            else:
                                rid, share = claim
                                paid = share
                            # v30 (column M2): a claim reaches SETTLEMENT — record its
                            # velocity (endorsements before settlement) and age. cx==0
                            # is a hold-to-settlement claim (never circulated); the full
                            # distribution answers PM2a / the KILL condition.
                            if self.claims_transferable:
                                self.claim_settle_log.append(
                                    (self.tick, p["cb"][_ci], p["cx"][_ci],
                                     round(paid * V_DELIVER, 4)))
                            # v28 (column AA): a claimant left dead resolves by
                            # SENTINEL rid. VOID (claims-die / risk-premium): the
                            # share's payout is DESTROYED and booked to claims_voided
                            # (still counted in csum, so the deliverer does NOT absorb
                            # it — value leaves the economy, ledger balances via the
                            # claims_voided term). ESTATE (estates): the share settles
                            # to the dead holder's company TREASURY (heir) exactly as a
                            # live robot would be paid, so company credit is unchanged
                            # in aggregate. Real (rid>=0) claimants are paid as before
                            # ⇒ bit-identical when no death regime is active.
                            if rid == CLAIM_VOID:
                                self.claims_voided += paid * unit
                            elif rid < 0:                    # estate → treasury heir
                                hco = -rid - 2
                                self.company[hco]["treasury"] += paid * unit
                                self.company[hco]["credit"] += paid * unit
                                self.estate_settled += paid * unit
                            else:
                                cl = self.robots[rid]
                                cl.credit += paid * unit
                                self.company[cl.company]["credit"] += paid * unit
                                cl.claim_value -= paid * V_DELIVER
                            csum += paid
                        resid = 1.0 - csum
                        r.credit += resid * unit
                        self.company[r.company]["credit"] += resid * unit
                    elif sw:                         # v29: spot (bills off) under shock —
                        real = rate * V_DELIVER * vm  # the deliverer books the realized
                        r.credit += real              # value; a paperless economy has no
                        self.company[r.company]["credit"] += real   # claim stack to hit
                        if vm != 1.0:
                            self.shock_writedown += (1.0 - vm) * V_DELIVER
                            self._record_wd(r.rid, (1.0 - vm) * rate * V_DELIVER,
                                            (1.0 - vm) * rate * V_DELIVER,
                                            "direct", 0, True)
                    # v17 PHASE 2 (snhp+firm): recoup the transfer price the
                    # treasury advanced for this unit — deliverer→treasury, the
                    # exact inverse of the handoff advance (net-zero within-company
                    # reallocation; treasury+robot credit conserves).
                    if self.firm_relay:
                        adv = p["advanced"]
                        r.credit -= adv
                        self.company[r.company]["treasury"] += adv
                r.parcels = []
            r.delivered += q
            if not self.bills and not sw:       # spot/firm: deliverer books it all
                r.credit += earned              # (firm then recoups the advances
                self.company[r.company]["credit"] += earned   # above; net earned)
                # v29: under `sw` the spot deliverer was already credited PER PARCEL
                # at its realized value (loop above), so this whole-load booking is
                # skipped; `earned` (full face) would double-count the collapse.
            if owner is not None and owner != r.company:
                self.foreign_refined += q
                # v29: the tariff is on REALIZED value — the value-weighted count
                # qval (== q when nothing is shocked ⇒ byte-identical off).
                tariff = self.tau[owner] * V_DELIVER * (qval if sw else q)
                self.company[owner]["tariffs_earned"] += tariff
                self.company[r.company]["tariffs_paid"] += tariff
            for miner_co in (0, 1):           # provenance matrix
                qq = r.load_prov[miner_co]
                if qq:
                    self.delivered_matrix[miner_co][owner if owner is not None
                                                    else 0] += qq
            r.load_prov = [0, 0]
            self.delivered += q
            if self.depots:                 # v31: delivered — the relay leg is over
                r.relay_from = None
            self.energy_at_last_delivery = self.energy_drawn()
            return q
        return 0

    def charge_step(self) -> None:
        served = set()
        for k, (pos, owner) in enumerate(zip(self.chargers, self.charger_owner)):
            queue = [r for r in self.robots
                     if r.rid not in served
                     and r.charge_queued_at >= 0
                     and manhattan(r.pos, pos) <= 1
                     and r.battery < BATTERY_MAX - 1e-9]
            queue.sort(key=lambda r: (r.charge_queued_at,
                                      self._charge_prio[r.rid]))
            toll = self.charger_toll[k]
            built = self.charger_built[k]
            for r in queue[:CHARGE_SLOTS]:
                guest = owner is not None and owner != r.company
                amt = min(GUEST_RATE if guest else CHARGE_RATE,
                          BATTERY_MAX - r.battery)
                r.battery += amt
                self.energy_charged += amt
                if guest:
                    self.guest_charged += amt
                    # v18 (column Q): the toll — a guest slot-fill at a BUILT
                    # charger with toll>0 pays `toll` credits owner←guest (a pure
                    # company↔company transfer, net-zero in Σ credit ⇒
                    # ledger_accounted intact; toll_conserved asserts earned==paid).
                    if built:
                        self.built_guest_slots += 1
                        if toll > 0:
                            self.company[owner]["credit"] += toll
                            self.company[owner]["toll_earned"] += toll
                            self.company[r.company]["credit"] -= toll
                            self.company[r.company]["toll_paid"] += toll
                served.add(r.rid)
                self.charge_served_slots += 1    # v17: charger duty-cycle numer.
                if r.stranded and not r.dead and r.battery >= RESCUE_FLOOR:
                    r.stranded = False           # v28: a corpse never revives
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
        if recv.stranded and not recv.dead and recv.battery >= RESCUE_FLOOR:
            recv.stranded = False               # v28: a corpse never revives
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
            # P23e: retire the giver's just-closed leg dwell, then re-stamp the
            # parcel for the taker's opening leg. Pure bookkeeping (no RNG/Φ),
            # so dwell=True is bit-identical to dwell=False in every regime.
            if self.dwell:
                for p in moving:
                    dwell, cf, excess = self._leg_dwell(p, giver.pos)
                    self.hop_dwells.append(dict(
                        uid=p["uid"], dwell=dwell, cf=cf, excess=excess,
                        hops=p["hops"], final=False, giver=giver.rid,
                        origin=p["origin"]))
                    p["acq_tick"] = self.tick
                    p["acq_pos"] = taker.pos
            taker.parcels.extend(moving)
            # v29 (column AB): acquiring an in-transit far-band parcel post-shock is a
            # DIRECT hit (the taker now hauls worthless cargo, burning energy for a
            # settlement that vanished) — taint it at depth 0 so a later death of the
            # taker attributes contagion by hop-distance. No-op unless the shock has
            # fired ⇒ bit-safe off.
            if self.shocked:
                for p in moving:
                    if p["origin"] in self.shock_far:
                        self._taint(taker.rid, 0)
            # v17 PHASE 2 (snhp+firm): a WITHIN-company handoff settles internally
            # — the treasury advances the receiver a transfer price (marginal haul
            # cost + fixed margin), tagged onto the moved parcels and recouped from
            # whoever delivers them (drop). Cross-company handoffs are untouched
            # spot. This is a pure CREDIT reallocation (treasury↔robot); it never
            # touches Φ/physics/RNG, so the fast path stays and trajectories match
            # spot exactly — the transfer price only re-books who is paid.
            if self.firm_relay and giver.company == taker.company:
                tp = self._firm_transfer_price(taker, q)
                self.company[taker.company]["treasury"] -= tp
                taker.credit += tp
                per = tp / q
                for p in moving:
                    p["advanced"] += per
        if log:
            self.event_log.append(dict(t=self.tick, kind="cargo",
                                       src=giver.rid, dst=taker.rid, amt=q,
                                       d=int(giver.stranded or taker.stranded)))
        return q

    def transfer_claims(self, giver: Robot, taker: Robot, target: float) -> float:
        """v30 (column M2): ENDORSE `target` face value of the giver's outstanding
        claims to the taker. A claim is a (rid, share) entry on SOME parcel's claim
        stack (wherever the underlying cargo now rides); endorsement rewrites the
        claimant rid giver→taker so the parcel settles to the taker (the CURRENT
        holder) — a book entry on a third party's cargo, exactly as a bill of
        exchange is endorsed without the goods moving. Claims are reassigned whole in
        deterministic (robot rid, parcel, stack) order until `target` face is covered;
        the final entry is SPLIT so the moved face is EXACT (the taker gets the moved
        share, the giver keeps the remainder). claim_value is booked by the EXACT
        target (the feasibility mask guarantees giver.claim_value ≥ target, and in this
        column's flat-live-stack regime claim_value == Σ live-entry face, so the scan
        always reaches it), so the endorsement is a pure lossless, weightless value
        transfer — the physics that lets paper out-circulate the battery. Credit is
        untouched (the claim still settles to face at delivery, now to the taker);
        no RNG, no Φ side effects. Returns the face actually reassigned (== target)."""
        moved = 0.0
        remaining = target
        V = V_DELIVER
        for other in self.robots:                # deterministic: rid order
            if remaining <= 1e-12:
                break
            for p in other.parcels:
                if remaining <= 1e-12:
                    break
                cl = p.get("claims")
                if not cl:
                    continue
                cx = p["cx"]
                cb = p["cb"]
                i = 0
                while i < len(cl) and remaining > 1e-12:
                    if cl[i][0] != giver.rid:
                        i += 1
                        continue
                    share = cl[i][1]
                    face_i = share * V
                    ref_d = min(manhattan(other.pos, rf) for rf in self.refineries)
                    if face_i <= remaining + 1e-12:
                        # endorse the WHOLE entry to the taker
                        cl[i] = (taker.rid, share)
                        cx[i] += 1
                        moved += face_i
                        remaining -= face_i
                        self._log_endorse(face_i, ref_d, p["hops"], cx[i])
                        i += 1
                    else:
                        # SPLIT: move exactly `remaining` face, keep the rest
                        share_move = remaining / V
                        share_keep = share - share_move
                        cl[i] = (taker.rid, share_move)
                        cl.insert(i + 1, (giver.rid, share_keep))
                        cx.insert(i + 1, cx[i])          # keep-half: giver's history
                        cb.insert(i + 1, cb[i])
                        cx[i] += 1                        # move-half: one more endorsement
                        moved += remaining
                        self._log_endorse(remaining, ref_d, p["hops"], cx[i])
                        remaining = 0.0
                        i += 2
        assert abs(moved - target) < 1e-6, \
            "endorsement under-filled: claim_value overstated its live stack"
        giver.claim_value -= target
        taker.claim_value += target
        self.claim_xfers += 1
        return moved

    def _log_endorse(self, face: float, ref_d: int, hops: int, xfers: int) -> None:
        """Record one endorsed claim's maturity/risk proxy at transfer: ref_d = the
        current holder's Manhattan distance to the nearest refinery (near = about to
        settle = LOW risk; far = HIGH risk — the good-collateral question), hops = the
        underlying parcel's relay depth, xfers = endorsements including this one."""
        self.claim_xfer_log.append((self.tick, round(face, 4), ref_d, hops, xfers))

    def swap_sectors(self, a: Robot, b: Robot, log: bool = True) -> None:
        a.sector, b.sector = b.sector, a.sector
        if log:
            self.event_log.append(dict(t=self.tick, kind="sector",
                                       src=a.rid, dst=b.rid, amt=0))

    def debit_energy(self, r: Robot, amount: float) -> None:
        r.battery = max(0.0, r.battery - amount)
        self._maybe_strand(r)

    def _forge_debit(self, r: Robot, amount: float, kind: str) -> None:
        """v27 (column Z): burn `amount` battery for a forgery act (`kind`=="forge")
        or a verification act (`kind`=="verify") and book the posted price to the
        column-Z spend ledger. The battery is CONSUMED exactly like a move (it can
        floor at 0 = stranding), while the ledger records the price of every act —
        so the conservation identity the Z test checks is `spend == events × cost`
        (every act charged once at the registered price). Called by the arm AFTER
        the deal settles, so it never perturbs the evaluated Φ == executed Φ assert."""
        self.debit_energy(r, amount)
        if kind == "forge":
            self.forge_spend += amount
            self.forge_events += 1
        else:
            self.verify_spend += amount
            self.verify_events += 1

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
            if r.dead:                             # v28: a corpse interacts with
                continue                           # no one (bit-identical off — no
            buckets.setdefault((r.pos[0] // R, r.pos[1] // R), []).append(idx)
        pairs_idx = []
        for i, a in enumerate(rs):
            if a.dead:                             # robot is ever dead when mortality
                continue                           # is off, so no pair is dropped)
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
        # v23: pinned_cargo (units escrowed in live relay orders) is neither in a
        # robot's load nor in stock nor delivered — accounted here so an escrowed
        # lien never reads as a material leak. 0 in every non-order column, so the
        # invariant is bit-identical when order_book is off.
        return (self.delivered + sum(self.stock)
                + sum(r.load for r in self.robots) + self.pinned_cargo)

    def material_ok(self) -> bool:
        # v11: departures erase true stock, booked to stock_lost — accounted
        # here explicitly so conservation stays EXACT. stock_lost is 0 in every
        # non-dynamic column, so this is bit-identical to the old invariant.
        # v23: relay cargo abandoned on a poster's death is folded into stock_lost
        # (a documented write-off — material honestly leaves the productive pool).
        return self.material_accounted() + self.stock_lost == self.total_stock

    def ledger_accounted(self) -> bool:
        """Σ company credit + Σ tariffs earned (+ v18 Σ build_spend) == V·delivered
        (unless the merged-firm flag pays full rate, where tariff flows are
        notional). v18: credit spent placing a charger leaves circulation into
        build_spend, so it is added back here to keep the identity exact; tolls are
        net-zero in Σ credit so they need no term. build_spend is 0 in every prior
        column ⇒ bit-identical."""
        if self.internalize_tariffs:
            return True
        credit = sum(c["credit"] for c in self.company)
        tariffs = sum(c["tariffs_earned"] for c in self.company)
        build = sum(c["build_spend"] for c in self.company)
        # v28 (column AA): credit DESTROYED by a voided claim (claims-die / risk-
        # premium) leaves circulation into claims_voided — added back here so the
        # identity stays exact (the value is gone, like stranded cargo, but the
        # ledger balances). 0 in every prior column ⇒ bit-identical.
        voided = self.claims_voided
        # v29 (column AB): the shock counts a far-band unit as `delivered` (physical)
        # but the collapsed ore never created its (1−floor)·V of value — that gap is
        # in shock_writedown, added back exactly like a void. The clearinghouse fee
        # RESERVE (ccp_pool) is live credit that left circulation into the pool (net
        # of covers), so it is added back too. Fees/covers are net-zero company↔pool
        # transfers; the per-unit algebra closes to V (SPEC v29). Both 0 in every
        # prior column ⇒ bit-identical.
        shock = self.shock_writedown + self.ccp_pool
        return abs(credit + tariffs + build + voided + shock
                   - V_DELIVER * self.delivered) < 1e-6

    def credit_conserved(self) -> bool:
        """v17 PHASE 2: per-company, Σ(robot credit) + treasury == the company's
        booked delivery credit. Under snhp+bill the deliverer's payout is split
        across claimants (by their company) yet each split is mirrored to a
        company total; under snhp+firm the treasury advances/recoups net-zero
        within the company. Holds for every prior arm too (treasury==0 and each
        robot's credit is booked to its company at drop) — a general invariant."""
        for c in range(len(self.company)):
            rob = sum(r.credit for r in self.robots if r.company == c)
            if abs(rob + self.company[c]["treasury"]
                   - self.company[c]["credit"]) > 1e-6:
                return False
        return True

    # ── v23 (column V): the stigmergic order book ─────────────────────────
    def post_order(self, poster: Robot, q: int, alpha: float,
                   energy: float = 0.0, expiry: int | None = None,
                   loc: tuple | None = None):
        """Pin a binding cargo-relay order at the poster's location. Escrow at
        post time (binding = no vaporware): q FIFO-head cargo parcels are lifted
        off the poster's load into the order (a cargo LIEN, folded into material
        conservation via pinned_cargo), the poster's α claim is banked onto each
        (its compensation — a credit claim on the terminal payout, paid whoever
        delivers, so it survives the poster moving on or dying), and an optional
        energy bounty is reserved from the poster's battery. Returns the order or
        None. Deterministic; consumes no RNG.

        v31 (column V2): `loc` overrides the pin location — the DEPOT deposits at
        the co-located charger the poster is docked at (a fixed, high-foot-traffic
        waypoint), not the poster's transient position. loc=None ⇒ poster.pos,
        exactly column V (bit-identical). Depositing clears relay_from (the parcel
        is no longer in this robot's hands, so the anti-churn token is spent)."""
        if not self.order_book or q <= 0 or poster.load < q:
            return None
        pin = poster.pos if loc is None else loc
        parcels = poster.parcels[:q]
        poster.parcels = poster.parcels[q:]
        poster.load -= q
        # move provenance (miner-company buckets) with the escrowed cargo, FIFO-
        # ish exactly as transfer_cargo does, so sum(load_prov)==load holds and
        # the delivered_matrix stays correct when a taker later delivers it.
        prov = [0, 0]
        rem = q
        for co in (0, 1):
            take = min(rem, poster.load_prov[co])
            poster.load_prov[co] -= take
            prov[co] += take
            rem -= take
        # bank the poster's α claim on each escrowed parcel (the future holder
        # keeps the residual). Matches _bills_attach exactly, but the CLAIMANT
        # holds nothing physical while the cargo is pinned (no taker yet).
        s_val = 0.0
        for p in parcels:
            res = 1.0 - sum(sh for _rid, sh, *_ in p["claims"])
            share = alpha * res
            p["claims"].append((poster.rid, share))
            s_val += share
        poster.claim_value += s_val * V_DELIVER
        self.pinned_cargo += q
        if energy > 0:
            energy = min(energy, max(0.0, poster.battery - 1.0))
            poster.battery -= energy
            self.escrowed_energy += energy
        o = dict(oid=self._order_uid, kind="relay", loc=pin,
                 poster=poster.rid, poster_co=poster.company,
                 expiry=(self.tick + ORDER_EXPIRY if expiry is None else expiry),
                 q=q, alpha=alpha, energy=energy, parcels=parcels, prov=prov,
                 posted_tick=self.tick)
        self._order_uid += 1
        self.orders.append(o)
        self.orders_posted += 1
        if self.depots:
            poster.relay_from = None
        return o

    def accept_order(self, taker: Robot, o: dict) -> int:
        """Unilateral acceptance — the acceptor's IR was cleared by the arm. The
        escrowed cargo (with the poster's claim riding along) and any energy
        bounty transfer to the taker; the order retires. NO DEAL_PAUSE is charged
        (the registered advantage) — the saved ticks are booked to
        pause_ticks_saved. Mutates EXACTLY the taker-state fields Φ reads
        (load, parcels, battery) so the arm's evaluated==executed assert holds.
        Returns units taken. Consumes no RNG."""
        q = o["q"]
        for co in (0, 1):
            taker.load_prov[co] += o["prov"][co]
        taker.load += q
        taker.parcels.extend(o["parcels"])
        taker.received_units += q
        taker.target_ref = None
        if self.depots:                     # v31: remember the depot taken from so
            taker.relay_from = o["loc"]      # the taker stages forward before it
                                             # may re-deposit (anti-churn token)
        self.pinned_cargo -= q
        if o["energy"] > 0:
            got = min(o["energy"] * (1 - TRANSFER_LOSS),
                      BATTERY_MAX - taker.battery)
            taker.battery += max(0.0, got)
            self.escrowed_energy -= o["energy"]
            self.escrow_energy_paid += o["energy"]
            if taker.stranded and taker.battery >= RESCUE_FLOOR:
                taker.stranded = False
        self.orders.remove(o)
        self.orders_accepted += 1
        self.pause_ticks_saved += DEAL_PAUSE
        self.event_log.append(dict(t=self.tick, kind="cargo", src=o["poster"],
                                   dst=taker.rid, amt=q, d=0))
        self.order_log.append(dict(t=self.tick, oid=o["oid"], poster=o["poster"],
                                   taker=taker.rid, q=q,
                                   wait=self.tick - o["posted_tick"]))
        return q

    def expire_orders(self) -> None:
        """Retire every order past its expiry (unaccepted), refunding escrow.
        No-op when order_book is off ⇒ bit-identical."""
        if not self.order_book:
            return
        live = []
        for o in self.orders:
            if self.tick < o["expiry"]:
                live.append(o)
            else:
                self._refund_order(o)
        self.orders = live

    def _refund_order(self, o: dict) -> None:
        """Refund a lapsed order's escrow. Cargo returns to the poster if it is
        alive with capacity; otherwise the material is written off to stock_lost
        (abandoned — a dead/full poster cannot reclaim it), which material_ok
        already accounts. The poster's banked claim is stripped from the parcels
        and un-banked. Energy refunds to a live poster's battery; a DEAD poster's
        bounty is written off (registered: 'escrow refunds to the company' — for
        pinned energy the honest analog is a write-off, since a stranded robot
        cannot use a refund and there is no company energy pool; no phantom
        credit is minted, so every ledger stays conserved)."""
        q = o["q"]
        poster = self.robots[o["poster"]]
        s_val = 0.0
        for p in o["parcels"]:
            rid, share = p["claims"].pop()      # the poster's claim (last added)
            assert rid == poster.rid, "refund stripped the wrong claim"
            s_val += share
        poster.claim_value -= s_val * V_DELIVER
        self.pinned_cargo -= q
        if not poster.stranded and poster.load + q <= poster.cap:
            poster.load += q
            poster.parcels.extend(o["parcels"])
            for co in (0, 1):
                poster.load_prov[co] += o["prov"][co]
        else:
            self.stock_lost += q
            self.cargo_writeoff += q
        if o["energy"] > 0:
            self.escrowed_energy -= o["energy"]
            if not poster.stranded:
                poster.battery = min(BATTERY_MAX, poster.battery + o["energy"])
                self.escrow_energy_refunded += o["energy"]
            else:
                self.escrow_energy_writeoff += o["energy"]
        self.orders_expired += 1

    def _discover_orders(self) -> None:
        """Stigmergic discovery: a robot learns of an order ONLY when the order's
        pinned location enters its physical sensing range (Chebyshev R_SENSE).
        No global feed (the P21 lesson). Memory persists in known_orders so a
        robot may route back to service it. Own-company orders only (a relay is
        serviced by the poster's fleet). Consumes no RNG."""
        rs = self.r_sense
        for r in self.robots:
            kn = self.known_orders[r.rid]
            for o in self.orders:
                if o["poster_co"] != r.company or o["oid"] in kn:
                    continue
                if (abs(r.pos[0] - o["loc"][0]) <= rs
                        and abs(r.pos[1] - o["loc"][1]) <= rs):
                    kn.add(o["oid"])

    def escrow_conserved(self) -> bool:
        """v23: the order ledger is internally consistent — pinned_cargo equals
        the cargo held across live orders, and the live-energy escrow equals the
        running escrowed_energy balance. (material_ok already ties pinned_cargo
        into GLOBAL material conservation; this is the order-local check.)"""
        pinned = sum(o["q"] for o in self.orders)
        live_e = sum(o["energy"] for o in self.orders)
        return (pinned == self.pinned_cargo
                and abs(live_e - self.escrowed_energy) < 1e-9)

    # ── v31 (column V2): the depot ────────────────────────────────────────
    def _depot_here(self, r: Robot):
        """The charger position r is DOCKED at (Manhattan ≤ 1 — the same dock
        range charge_step uses), or None. Depots are co-located with chargers, so
        a robot deposits only where it already stops to charge (no new geometry).
        Deterministic; consumes no RNG."""
        for pos in self.chargers:
            if manhattan(r.pos, pos) <= 1:
                return pos
        return None

    def _forward_depot(self, r: Robot, dest: tuple):
        """The nearest depot strictly CLOSER to the delivery refinery than r is
        now, reachable within r's current LOADED battery — the next leg of the
        async chain. None if no such depot (the chain cannot advance from here;
        the robot charges, then deposits-and-returns). Deterministic; no RNG."""
        d_here = manhattan(r.pos, dest)
        best, best_leg = None, float("inf")
        for pos in self.chargers:
            if manhattan(pos, dest) >= d_here:       # must gain ground toward home
                continue
            leg = manhattan(r.pos, pos)
            if r.bat() <= leg * r.eff * (1.0 + LOADED_MULT):   # unreachable loaded
                continue
            if leg < best_leg:
                best, best_leg = pos, leg
        return best

    def depot_next_leg_clears(self, r: Robot, depot: tuple, alpha: float) -> bool:
        """v31 depot posting gate: would a plausible taker, picking the residual up
        at `depot`, clear IR on the NEXT LEG alone — a haul to the nearest depot
        strictly closer to the refinery, or the refinery itself, whichever is
        nearer? Residual delivery credit vs that one leg's loaded haul at the
        reference shadow price EV_INIT. This is the depot's whole premise: the
        taker owes only the next hop (V's gate priced the WHOLE route to the
        refinery and so refused far deposits). Derived from existing geometry — no
        new planner, no RNG."""
        ref = self._home_ref(r.company)
        dest = self.refineries[ref]
        rate = self.credit_rate(r.company, ref)
        d_ref = manhattan(depot, dest)
        leg = d_ref                                  # straight to the refinery
        for pos in self.chargers:
            if manhattan(pos, dest) < d_ref:         # a strictly-closer depot
                leg = min(leg, manhattan(depot, pos))
        resid_units = (1.0 - alpha) * r.load
        return resid_units * rate * V_DELIVER > leg * (1.0 + LOADED_MULT) * EV_INIT

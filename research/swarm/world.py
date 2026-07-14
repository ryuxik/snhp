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
HAZARD_SCALE = 8.0                  # hazard sigmoid softness (-hz arms)
EV_INIT = 0.3                       # initial energy shadow price (endogenous
EV_MIN, EV_MAX = 0.05, 1.0          # thereafter: lagged ∂Φ/∂battery, clamped)
TARGET_MARGIN = 1.5                 # delivery-target hysteresis (score units)

GUEST_RATE = 2.0                    # charge rate at a rival's charger (v5)
GUEST_PENALTY = 6                   # routing penalty (cells) for guest charging

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

    def step_cost(self) -> float:
        return self.eff * (1.0 + (LOADED_MULT if self.load > 0 else 0.0))


class World:
    def __init__(self, n_robots: int = 24, sigma: float = 1.0, seed: int = 0,
                 hazard_phi: bool = False, preset: str = "v4",
                 tau: tuple = (0.0, 0.0), internalize_tariffs: bool = False,
                 freeze_ev: float | None = None):
        self.rng = np.random.RandomState(seed)
        self.hazard_phi = hazard_phi
        self.preset = preset
        cfg = PRESETS[preset]
        self.refineries = [tuple(p) for p, _ in cfg["refineries"]]
        self.ref_owner = [o for _, o in cfg["refineries"]]
        self.chargers = [tuple(p) for p, _ in cfg["chargers"]]
        self.charger_owner = [o for _, o in cfg["chargers"]]
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

        self.robots: list[Robot] = []
        if self.n_companies == 2:
            self._spawn_twin_fleets(n_robots, sigma)
        else:
            self._spawn_v3(n_robots, sigma)
        self.energy_initial = sum(r.battery for r in self.robots)
        self.energy_at_last_delivery = self.energy_initial
        # company-neutral charger tie-break (panel M2): seeded priority
        self._charge_prio = list(self.rng.permutation(len(self.robots)))

    # mean-preserving draws (v2 review M1): σ widens spread, never the mean
    def _draw(self, sigma):
        u = self.rng.uniform
        cap = int(np.clip(round(3 + sigma * u(-2, 2)), 1, 5))
        eff = float(np.clip(1.0 + sigma * u(-0.5, 0.5), 0.5, 1.5))
        b0 = float(np.clip(self._b_mean + sigma * u(-self._b_spread, self._b_spread),
                           self._b_lo, BATTERY_MAX))
        pos = (int(u(1, GRID)), int(u(1, GRID)))
        return cap, eff, b0, pos

    def _gen_asteroids(self):
        """v5: 5 mirror-pairs of asteroids (reflection about y=16), stocks
        equal within a pair, total pinned to 2×TOTAL_STOCK (double workload:
        the rich stage needs a long game or coordination is decorative).
        Non-identical by construction: position and richness vary per pair."""
        taken = {(26, 6), (26, 26), (12, 10), (22, 12), (12, 22), (22, 20)}
        pos = []
        while len(pos) < 5:
            x = int(self.rng.uniform(3, 29))
            y = int(self.rng.uniform(3, 13))
            p_ = (x, y)
            if p_ in taken or any(manhattan(p_, q) < 5 for q in pos):
                continue
            pos.append(p_)
        raw = [int(self.rng.uniform(6, 19)) for _ in range(5)]
        scale = TOTAL_STOCK / sum(raw)
        stocks = [max(4, round(r * scale)) for r in raw]
        stocks[0] += TOTAL_STOCK - sum(stocks)           # pin the total
        sources = pos + [(x, GRID - y) for x, y in pos]  # mirrors are idx+5
        return sources, stocks + list(stocks)

    def best_claim(self, r) -> int:
        """Policy claim choice: richest-per-distance stocked asteroid."""
        best, best_score = r.sector, -1.0
        for i, src in enumerate(self.sources):
            if self.stock[i] <= 0:
                continue
            score = self.stock[i] / (manhattan(r.pos, src) + 4.0)
            if score > best_score:
                best, best_score = i, score
        return best

    def _spawn_twin_fleets(self, n_robots, sigma):
        """Both companies receive the IDENTICAL draw multiset; company-1
        positions are the reflection (x, 32−y). Sectors stratified 6/6/6/6
        and mirrored so each company faces the same home/far structure."""
        half = n_robots // 2
        draws = [self._draw(sigma) for _ in range(half)]
        for k, (cap, eff, b0, pos) in enumerate(draws):
            self.robots.append(Robot(
                rid=k, pos=pos, battery=b0, cap=cap, eff=eff,
                sector=k % 2, company=0))
        for k, (cap, eff, b0, (x, y)) in enumerate(draws):
            self.robots.append(Robot(
                rid=half + k, pos=(x, GRID - y), battery=b0, cap=cap, eff=eff,
                sector=1 - (k % 2), company=1))
        if len(self.sources) > 2:            # v5: claims replace sectors —
            half_src = len(self.sources) // 2
            for k in range(half):            # mirrored pairs stay symmetric
                c = self.best_claim(self.robots[k])
                self.robots[k].sector = c
                self.robots[half + k].sector = (c + half_src) % len(self.sources)

    def _spawn_v3(self, n_robots, sigma):
        for i in range(n_robots):
            cap, eff, b0, pos = self._draw(sigma)
            self.robots.append(Robot(rid=i, pos=pos, battery=b0, cap=cap,
                                     eff=eff, sector=i % 2, company=0))

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
        if r.pos == self.sources[s] and self.stock[s] > 0:
            q = min(r.cap - r.load, self.stock[s])
            r.load += q
            r.load_prov[r.company] += q       # provenance: miner's company
            self.stock[s] -= q
            return q
        return 0

    def drop(self, r: Robot) -> int:
        """Refine at whichever refinery the robot stands on. Tariff is
        assessed HERE and only here, once per unit (panel refine-once)."""
        for ref_idx, pos in enumerate(self.refineries):
            if r.pos != pos or r.load <= 0:
                continue
            q, r.load = r.load, 0
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
                if r.stranded and r.battery >= RESCUE_FLOOR:
                    r.stranded = False
            for r in queue[CHARGE_SLOTS:]:    # commons diagnostics
                self.company[r.company]["queue_wait"] += 1

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
        giver.target_ref = None                 # re-evaluate routing
        taker.target_ref = None
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
        rs = self.robots
        pairs = []
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if max(abs(a.pos[0] - b.pos[0]),
                       abs(a.pos[1] - b.pos[1])) <= R_COMM:
                    pairs.append((a, b))
        self.rng.shuffle(pairs)
        return pairs

    def energy_drawn(self) -> float:
        return self.energy_initial + self.energy_charged

    def material_accounted(self) -> int:
        return self.delivered + sum(self.stock) + sum(r.load for r in self.robots)

    def material_ok(self) -> bool:
        return self.material_accounted() == self.total_stock

    def ledger_accounted(self) -> bool:
        """Σ company credit + Σ tariffs earned == V · delivered (unless the
        merged-firm flag pays full rate, where tariff flows are notional)."""
        if self.internalize_tariffs:
            return True
        credit = sum(c["credit"] for c in self.company)
        tariffs = sum(c["tariffs_earned"] for c in self.company)
        return abs(credit + tariffs - V_DELIVER * self.delivered) < 1e-6

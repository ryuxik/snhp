"""The coordination arms (SPEC.md v4.0). Identical physics and movement
policy; arms differ ONLY in what happens when two robots meet.

The ladder (one mechanism per rung):

  null        bare movement policy
  rules       null + threshold trophallaxis (altruistic rescue)
  auction     rules + MURDOCH-style single-issue cargo handoff
  auction-co  auction with company walls (selfless transfers within company)
  team        null + cooperative greedy joint-Φ over the bundle space
  team-co     team with company walls (cross-company encounters inert)
  twofirm     within-company joint-Φ; cross-company Nash-IR bargaining
  snhp        null + Nash-IR bundles (no -co variant BY DESIGN: individual
              rationality IS the company discipline)
  snhp+net    snhp + trophallaxis fallback
  -hz suffix  hazard-priced Φ (world flag, set by the runner)

Bundle evaluation and execution share ONE physics path; evaluated Φ ==
executed Φ is asserted on every deal. The auction rung prices deliveries
with the SAME delivery_target scoring the other arms use (panel: a
SINK-hardcoded baseline would be silently sandbagged in v4).
"""
from __future__ import annotations

import copy
import os
import sys

import numpy as np

from swarm import world as W
from swarm.value import (delivery_target, phi, safe_return_threshold,
                         stranding_hazard, update_ev)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SNHP = os.path.join(_ROOT, "snhp")
for _p in (_ROOT, _SNHP):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from nash_solver import (filter_pareto_frontier,  # noqa: E402
                         find_nash_bargaining_solution,
                         generate_contract_space)

ATTEMPT_COOLDOWN = 5
DEAL_COOLDOWN = 15
EV_REFRESH = 10                 # ticks between endogenous-EV updates

CARGO_OPTS = [-4, -2, -1, 0, 1, 2, 4]
ENERGY_OPTS = [-8.0, -4.0, -2.0, 0.0, 2.0, 4.0, 8.0]
SECTOR_OPTS = [0, 1]
MAX_CARGO = max(CARGO_OPTS)


# ── shared movement policy ──────────────────────────────────────────────
def intent(r, w):
    if r.stranded:
        return None
    if r.charge_queued_at >= 0 and r.battery < 0.95 * W.BATTERY_MAX:
        return w.charger
    if r.load > 0:
        ref = delivery_target(r, w)             # sticky (hysteresis)
        dest = w.refineries[ref]
        cost = W.manhattan(r.pos, dest) * r.eff * (1 + W.LOADED_MULT)
        return dest if r.battery > cost else w.charger
    r.target_ref = None
    if r.battery < safe_return_threshold(r, w):
        return w.charger
    if w.stock[r.sector] > 0:
        return w.sources[r.sector]
    if w.stock[1 - r.sector] > 0:
        return w.sources[1 - r.sector]
    return w.charger


def drive(r, w):
    t = intent(r, w)
    if t is None:
        return
    if t == w.charger and W.manhattan(r.pos, w.charger) <= 1:
        if r.charge_queued_at < 0:
            r.charge_queued_at = w.tick
        return
    r.charge_queued_at = -1
    if r.pos == t:
        if t in w.refineries:
            w.drop(r)
        elif t in w.sources:
            w.pick(r)
    else:
        w.move_toward(r, t)


def trophallaxis(w, a, b) -> bool:
    lo, hi = (a, b) if a.battery <= b.battery else (b, a)
    if lo.battery < 0.2 * W.BATTERY_MAX and hi.battery > 0.5 * W.BATTERY_MAX:
        amount = (hi.battery - lo.battery) / 2.0
        return w.transfer_energy(hi, lo, amount) > 0
    return False


# ── bundle physics (ONE code path for evaluation and execution) ─────────
def _feasible(a, b, q: int, e: float) -> bool:
    if q > 0 and (a.load < q or b.cap - b.load < q):
        return False
    if q < 0 and (b.load < -q or a.cap - a.load < -q):
        return False
    if e != 0:
        donor, recv = (a, b) if e > 0 else (b, a)
        if donor.battery - 1.0 < abs(e):
            return False
        if W.BATTERY_MAX - recv.battery < abs(e) * (1 - W.TRANSFER_LOSS):
            return False
    return True


def apply_bundle(w, a, b, q: int, e: float, s: int, log: bool) -> None:
    if q > 0:
        got = w.transfer_cargo(a, b, q, log=log)
        assert got == q, "cargo transfer diverged from evaluation"
    elif q < 0:
        got = w.transfer_cargo(b, a, -q, log=log)
        assert got == -q, "cargo transfer diverged from evaluation"
    if e > 0:
        got = w.transfer_energy(a, b, abs(e), log=log)
        assert abs(got - abs(e) * (1 - W.TRANSFER_LOSS)) < 1e-9
    elif e < 0:
        got = w.transfer_energy(b, a, abs(e), log=log)
        assert abs(got - abs(e) * (1 - W.TRANSFER_LOSS)) < 1e-9
    if s == 1:
        w.swap_sectors(a, b, log=log)
    w.debit_energy(a, W.TXN_COST)
    w.debit_energy(b, W.TXN_COST)


# ── arms ────────────────────────────────────────────────────────────────
class BaseArm:
    name = "null"

    def __init__(self, w: W.World):
        self.w = w
        self.deals = 0
        self._last_try: dict = {}

    def tick(self):
        w = self.w
        if w.tick % EV_REFRESH == 0:
            for r in w.robots:
                update_ev(r, w)
        order = list(w.robots)
        w.rng.shuffle(order)
        for r in order:
            drive(r, w)
        w.charge_step()
        busy = set()
        for a, b in w.encounters():
            if a.rid in busy or b.rid in busy:
                continue
            key = (min(a.rid, b.rid), max(a.rid, b.rid))
            last, was_deal = self._last_try.get(key, (-10**9, False))
            cool = DEAL_COOLDOWN if was_deal else ATTEMPT_COOLDOWN
            if w.tick - last < cool:
                continue
            struck = self.encounter(a, b)
            self._last_try[key] = (w.tick, struck)
            busy.add(a.rid)
            busy.add(b.rid)
        w.tick += 1

    def encounter(self, a, b) -> bool:
        return False


class NullArm(BaseArm):
    name = "null"


class RulesArm(BaseArm):
    name = "rules"

    def encounter(self, a, b) -> bool:
        return trophallaxis(self.w, a, b)


class AuctionArm(RulesArm):
    """rules + MURDOCH-faithful single-issue cargo reassignment, priced with
    the SAME delivery_target scoring every other arm uses."""
    name = "auction"
    company_walls = False

    def _net_value(self, r, w) -> float:
        """Per-trip net value of this robot delivering its (hypothetical)
        load: tariff-adjusted credit − haul energy at its shadow price;
        −inf if the battery can't make the trip."""
        ref = delivery_target(r, w, sticky=False)
        dest = w.refineries[ref]
        cost = W.manhattan(r.pos, dest) * r.eff * (1 + W.LOADED_MULT)
        if r.battery <= cost:
            return float("-inf")
        rate = w.credit_rate(r.company, ref)
        return rate * W.V_DELIVER - cost * r.ev / max(r.load, 1)

    def encounter(self, a, b) -> bool:
        if self.company_walls and a.company != b.company:
            return False
        if super().encounter(a, b):
            return True
        for seller, buyer in ((a, b), (b, a)):
            if seller.load == 0 or buyer.stranded:
                continue
            if self.company_walls and seller.company != buyer.company:
                continue
            q = min(MAX_CARGO, seller.load, buyer.cap - buyer.load)
            if q <= 0:
                continue
            if self._net_value(buyer, self.w) > 1.1 * self._net_value(seller, self.w):
                return self.w.transfer_cargo(seller, buyer, q) > 0
        return False


class AuctionCoArm(AuctionArm):
    name = "auction-co"
    company_walls = True


class SnhpArm(BaseArm):
    name = "snhp"

    def __init__(self, w: W.World, issues=("cargo", "energy", "sector"),
                 safety_net: bool = False):
        super().__init__(w)
        self.issues = tuple(issues)
        self.safety_net = safety_net
        opts = [CARGO_OPTS if "cargo" in issues else [0],
                ENERGY_OPTS if "energy" in issues else [0.0],
                SECTOR_OPTS if "sector" in issues else [0]]
        self.space = generate_contract_space(opts)

    def _evaluate(self, a, b):
        w = self.w
        n = len(self.space)
        ua = np.full(n, -np.inf)
        ub = np.full(n, -np.inf)
        for k in range(n):
            q, e, s = int(self.space[k][0]), float(self.space[k][1]), int(self.space[k][2])
            if q == 0 and e == 0 and s == 0:
                ua[k], ub[k] = phi(a, w), phi(b, w)
                continue
            if not _feasible(a, b, q, e):
                continue
            ra, rb = copy.copy(a), copy.copy(b)
            ra.load_prov = list(a.load_prov)     # copies must not share buckets
            rb.load_prov = list(b.load_prov)
            apply_bundle(w, ra, rb, q, e, s, log=False)
            ua[k], ub[k] = phi(ra, w), phi(rb, w)
        return ua, ub

    def _pick(self, ua, ub, batna_a, batna_b, a, b):
        pareto = filter_pareto_frontier(self.space, ua, ub)
        return find_nash_bargaining_solution(pareto, ua, ub, batna_a, batna_b)

    def encounter(self, a, b) -> bool:
        w = self.w
        batna_a, batna_b = phi(a, w), phi(b, w)
        ua, ub = self._evaluate(a, b)
        sol = self._pick(ua, ub, batna_a, batna_b, a, b)
        if sol is None:
            return trophallaxis(w, a, b) if self.safety_net else False

        q, e, s = int(self.space[sol][0]), float(self.space[sol][1]), int(self.space[sol][2])
        distress = (a.stranded or b.stranded
                    or stranding_hazard(a, w) > 0.5 or stranding_hazard(b, w) > 0.5)
        apply_bundle(w, a, b, q, e, s, log=True)
        assert abs(phi(a, w) - ua[sol]) < 1e-9 and abs(phi(b, w) - ub[sol]) < 1e-9, \
            "executed state diverged from evaluated bundle"

        surplus = (ua - batna_a) + (ub - batna_b)
        feasible = np.isfinite(surplus)
        joint_best = float(surplus[feasible].max())
        achieved = float(surplus[sol])
        w.deal_log.append(dict(
            tick=w.tick, a=a.rid, b=b.rid, q=q, e=e, s=s,
            a_co=a.company, b_co=b.company,
            border=int(a.company != b.company), distress=int(distress),
            sa=float(ua[sol] - batna_a), sb=float(ub[sol] - batna_b),
            capture=achieved / joint_best if joint_best > 1e-12 else 1.0))
        self.deals += 1
        return True


class TeamArm(SnhpArm):
    """Cooperative greedy joint-Φ over the same bundle space (no IR)."""
    name = "team"
    company_walls = False

    def _pick(self, ua, ub, batna_a, batna_b, a, b):
        joint = ua + ub
        feasible = np.isfinite(joint)
        if not feasible.any():
            return None
        jmax = float(joint[feasible].max())
        if jmax <= batna_a + batna_b + 1e-12:
            return None
        # company-neutral tie-break (v4 placebo catch): first-index argmax
        # systematically routed tied cargo toward lower rids (= company 0)
        # in the twin-fleet world; pick uniformly among ε-ties instead.
        cands = np.flatnonzero(feasible & (joint >= jmax - 1e-9))
        return int(cands[self.w.rng.randint(len(cands))])

    def encounter(self, a, b) -> bool:
        if self.company_walls and a.company != b.company:
            return False
        return super().encounter(a, b)


class TeamCoArm(TeamArm):
    name = "team-co"
    company_walls = True


class TwoFirmArm(SnhpArm):
    """Within-company: joint-Φ (a firm coordinates internally); across the
    border: Nash-IR bargaining. The panel's decomposition arm."""
    name = "twofirm"

    def _pick(self, ua, ub, batna_a, batna_b, a, b):
        if a.company == b.company:
            return TeamArm._pick(self, ua, ub, batna_a, batna_b, a, b)
        return SnhpArm._pick(self, ua, ub, batna_a, batna_b, a, b)


def make_arm(name: str, w: W.World, issues=("cargo", "energy", "sector")):
    arms = {"null": NullArm, "rules": RulesArm, "auction": AuctionArm,
            "auction-co": AuctionCoArm, "team-co": TeamCoArm,
            "twofirm": TwoFirmArm}
    if name in arms:
        a = arms[name](w)
        return a
    if name == "team":
        return TeamArm(w, issues=issues)
    if name == "snhp":
        return SnhpArm(w, issues=issues)
    if name == "snhp+net":
        return SnhpArm(w, issues=issues, safety_net=True)
    raise ValueError(f"unknown arm {name!r}")

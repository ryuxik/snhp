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
from swarm.value import (delivery_target, phi, phi_true,
                         safe_return_threshold, stranding_hazard,
                         stranding_hazard_true, update_ev)

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
    charger, _ = w.nearest_charger(r)
    if r.charge_queued_at >= 0 and r.bat() < 0.95 * W.BATTERY_MAX:
        return charger
    if r.load > 0:
        ref = delivery_target(r, w)             # sticky (hysteresis)
        dest = w.refineries[ref]
        cost = W.manhattan(r.pos, dest) * r.eff * (1 + W.LOADED_MULT)
        return dest if r.bat() > cost else charger
    r.target_ref = None
    if r.bat() < safe_return_threshold(r, w):
        return charger
    if w.stock[r.sector] <= 0:                  # claim depleted → re-claim
        r.sector = w.best_claim(r)
    if w.stock[r.sector] > 0:
        return w.sources[r.sector]
    return charger


def drive(r, w):
    t = intent(r, w)
    if t is None:
        return
    if t in w.chargers and W.manhattan(r.pos, t) <= 1:
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
    # decision layer → believed batteries (bat() contract); the transfer
    # itself is physics and transfer_energy clamps to the TRUE donor charge
    lo, hi = (a, b) if a.bat() <= b.bat() else (b, a)
    if lo.bat() < 0.2 * W.BATTERY_MAX and hi.bat() > 0.5 * W.BATTERY_MAX:
        amount = (hi.bat() - lo.bat()) / 2.0
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
        if r.bat() <= cost:                 # decision layer → believed battery
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
                 safety_net: bool = False, noise: float = 0.0):
        super().__init__(w)
        self.issues = tuple(issues)
        self.safety_net = safety_net
        self.noise = noise
        self.vetoes = 0
        self.veto_est_surplus: list = []
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

    def _noisy(self, u, batna):
        """Estimate of the PARTNER's per-bundle utility: true surplus scaled
        by a per-encounter bias plus per-bundle jitter (winner's-curse-prone
        by construction — noisy argmax selects overestimates)."""
        s_ = self.noise / np.sqrt(2)
        bias = self.w.rng.normal(0.0, s_)
        jitter = self.w.rng.normal(0.0, s_, size=len(u))
        return batna + (u - batna) * (1.0 + bias + jitter)

    def _reported(self, r, batna, u):
        """v6 reporting layer: a liar inflates its BATNA by LIE_LAMBDA of its
        best achievable gain this encounter (uniform surplus scaling is
        Nash-neutral, so the disagreement point is the meaningful lie).
        Attested robots report truth by definition."""
        if not r.liar or r.attested:
            return batna
        feas = np.isfinite(u)
        if not feas.any():
            return batna
        best = float(u[feas].max()) - batna
        return batna + W.LIE_LAMBDA * max(0.0, best)

    # a merged/centralized picker (team, twofirm, team-co) coordinates on the
    # firm's true internal books — the v6 reporting layer targets only the
    # decentralized veto tier. Routing joint-pick arms through the liar branch
    # (review) both fed them inflated BATNAs and tripped the per-side IR
    # assert their joint pick never promised.
    consumes_reports = True

    def _margin_mask(self, u, batna):
        """Demand surplus >= DISTRUST_DELTA × own best gain. One body, two
        gates at the call sites: v6 aims it at unattested partners (the
        distrust tax), v7 aims it inward at one's own sensor error."""
        feas = np.isfinite(u)
        if not feas.any():
            return u
        need = W.DISTRUST_DELTA * max(0.0, float(u[feas].max()) - batna)
        out = u.copy()
        out[(u - batna) < need] = -np.inf
        return out

    def encounter(self, a, b) -> bool:
        w = self.w
        batna_a, batna_b = phi(a, w), phi(b, w)
        ua, ub = self._evaluate(a, b)       # RAW: audit + frontier reference
        ua_p, ub_p = ua, ub                 # pick-arrays (defense masks)
        if w.self_margin:
            ua_p = self._margin_mask(ua_p, batna_a)
            ub_p = self._margin_mask(ub_p, batna_b)
        if (w.defended or a.liar or b.liar) and self.consumes_reports:
            rep_a = self._reported(a, batna_a, ua_p)
            rep_b = self._reported(b, batna_b, ub_p)
            ua_m = (self._margin_mask(ua_p, batna_a)
                    if w.defended and not b.attested else ua_p)
            ub_m = (self._margin_mask(ub_p, batna_b)
                    if w.defended and not a.attested else ub_p)
            sol = self._pick(ua_m, ub_m, rep_a, rep_b, a, b)
            # BATNA inflation only makes the liar pickier — any picked bundle
            # exceeds the TRUE batnas of both sides by construction
            if sol is not None:
                assert ua[sol] - batna_a > 0 and ub[sol] - batna_b > 0
        elif self.noise <= 0:
            sol = self._pick(ua_p, ub_p, batna_a, batna_b, a, b)
        else:
            # proposer a: own truth + noisy view of b; b vetoes true losses
            sol = self._pick(ua_p, self._noisy(ub_p, batna_b), batna_a, batna_b, a, b)
            if sol is not None and ub[sol] - batna_b <= 0:
                self.vetoes += 1
                self.veto_est_surplus.append(
                    float(self._noisy(ub_p, batna_b)[sol] - batna_b))
                sol = None
                # role-swapped retry: b proposes under its noisy view of a
                sol2 = self._pick(self._noisy(ua_p, batna_a), ub_p, batna_a, batna_b, b, a)
                if sol2 is not None and ua[sol2] - batna_a > 0:
                    sol = sol2
                elif sol2 is not None:
                    self.vetoes += 1
        if sol is None:
            return trophallaxis(w, a, b) if self.safety_net else False
        return self._finish_deal(a, b, sol, ua, ub, batna_a, batna_b)

    def _finish_deal(self, a, b, sol, ua, ub, batna_a, batna_b) -> bool:
        """Shared execute+log tail — ONE deal schema for every arm (review:
        TrustArm's hand-copied tail fabricated capture=1.0/distress=0 and was
        invisible to the poisoning audit). ua/ub must be the RAW evaluated
        utilities: a defense-masked frontier inflates capture."""
        w = self.w
        q, e, s = int(self.space[sol][0]), float(self.space[sol][1]), int(self.space[sol][2])
        distress = (a.stranded or b.stranded
                    or stranding_hazard_true(a, w) > 0.5
                    or stranding_hazard_true(b, w) > 0.5)
        audit = a.gauge_bias != 0.0 or b.gauge_bias != 0.0
        ta0 = phi_true(a, w) if audit else None
        tb0 = phi_true(b, w) if audit else None
        apply_bundle(w, a, b, q, e, s, log=True)
        assert abs(phi(a, w) - ua[sol]) < 1e-9 and abs(phi(b, w) - ub[sol]) < 1e-9, \
            "executed state diverged from evaluated bundle"

        sa, sb = float(ua[sol] - batna_a), float(ub[sol] - batna_b)
        surplus = (ua - batna_a) + (ub - batna_b)
        feasible = np.isfinite(surplus)
        joint_best = float(surplus[feasible].max())
        achieved = float(surplus[sol])
        w.deal_log.append(dict(
            tick=w.tick, a=a.rid, b=b.rid, q=q, e=e, s=s,
            a_co=a.company, b_co=b.company,
            a_liar=int(a.liar), b_liar=int(b.liar),
            border=int(a.company != b.company), distress=int(distress),
            sa=sa, sb=sb,
            # gauge suspended = ground truth; at zero bias phi_true ≡ phi,
            # so the audit equals the believed surplus without 4 extra Φ evals
            sa_true=(float(phi_true(a, w) - ta0) if audit else sa),
            sb_true=(float(phi_true(b, w) - tb0) if audit else sb),
            capture=achieved / joint_best if joint_best > 1e-12 else 1.0))
        self.deals += 1
        return True


class TeamArm(SnhpArm):
    """Cooperative greedy joint-Φ over the same bundle space (no IR)."""
    name = "team"
    company_walls = False
    consumes_reports = False    # a merged firm's pick reads true internal books

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
    consumes_reports = False    # internal joint pick has no per-side IR

    def _pick(self, ua, ub, batna_a, batna_b, a, b):
        if a.company == b.company:
            return TeamArm._pick(self, ua, ub, batna_a, batna_b, a, b)
        return SnhpArm._pick(self, ua, ub, batna_a, batna_b, a, b)


class TrustArm(SnhpArm):
    """v6.1: attestation gates the COOPERATIVE tier. Trusted pairs get the
    joint argmax over REPORTED utilities with NO veto (that is what trust
    means — and why it is exploitable); everyone else gets Nash-IR with the
    true-loss guarantee. `gated=False` = naive cooperation (everyone
    trusted); `gated=True` = only attested↔attested pairs are trusted."""
    name = "trust"

    def __init__(self, w: W.World, gated: bool,
                 issues=("cargo", "energy", "sector")):
        super().__init__(w, issues=issues)
        self.gated = gated
        self.exploit_deals = 0          # all no-veto true-loss executions
        self.exploit_loss = 0.0
        self.strip_deals = 0            # v6.2: liar gains while honest loses
        self.strip_loss = 0.0
        self.sacrifice_deals = 0        # benign joint-max losses

    def _report_joint(self, r, batna, u):
        """Joint-tier lie: inflate reported surplus ×(1+LIE_LAMBDA)."""
        if not r.liar:
            return u
        out = u.copy()
        feas = np.isfinite(u)
        out[feas] = batna + (u[feas] - batna) * (1.0 + W.LIE_LAMBDA)
        return out

    def encounter(self, a, b) -> bool:
        w = self.w
        trusted = (a.attested and b.attested) if self.gated else True
        if not trusted:
            # the untrusted tier IS the veto tier — same lies, distrust tax
            # and audit log as any defended Nash-IR encounter. (Review: this
            # tier used to run lie-free on true books, so the gated result
            # measured pure access denial rather than relegation.)
            return SnhpArm.encounter(self, a, b)
        batna_a, batna_b = phi(a, w), phi(b, w)
        ua, ub = self._evaluate(a, b)
        ra = self._report_joint(a, batna_a, ua)
        rb = self._report_joint(b, batna_b, ub)
        sol = TeamArm._pick(self, ra, rb, batna_a, batna_b, a, b)
        if sol is None:
            return False
        sa, sb = float(ua[sol] - batna_a), float(ub[sol] - batna_b)
        if min(sa, sb) < 0:                 # no veto up here — attribute it
            self.exploit_deals += 1
            self.exploit_loss += -min(sa, sb)
            honest_loses = (sa < 0 and not a.liar) or (sb < 0 and not b.liar)
            liar_gains = (sa > 0 and a.liar) or (sb > 0 and b.liar)
            if honest_loses and liar_gains:
                self.strip_deals += 1
                self.strip_loss += -min(sa, sb)
            else:
                self.sacrifice_deals += 1
        return self._finish_deal(a, b, sol, ua, ub, batna_a, batna_b)


def make_arm(name: str, w: W.World, issues=("cargo", "energy", "sector"),
             noise: float = 0.0):
    arms = {"null": NullArm, "rules": RulesArm, "auction": AuctionArm,
            "auction-co": AuctionCoArm, "team-co": TeamCoArm,
            "twofirm": TwoFirmArm}
    if name in arms:
        return arms[name](w)
    if name == "team":
        return TeamArm(w, issues=issues)      # full-info ceiling: no noise
    if name == "snhp":
        return SnhpArm(w, issues=issues, noise=noise)
    if name == "snhp+net":
        return SnhpArm(w, issues=issues, safety_net=True, noise=noise)
    if name == "trust-open":
        return TrustArm(w, gated=False, issues=issues)
    if name == "trust-gated":
        return TrustArm(w, gated=True, issues=issues)
    raise ValueError(f"unknown arm {name!r}")

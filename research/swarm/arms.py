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

import math
import os
import sys

import numpy as np

from swarm import world as W
from swarm.value import (bills_correction, delivery_target, fast_phi,
                         load_factors, owned_and_claim, phi, phi_bills, phi_ctx,
                         phi_true, phi_true_field, safe_return_threshold,
                         stranding_hazard, stranding_hazard_true, update_ev)

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
# v22 (column U): a deal's own realized TRUE surplus this far below the robot's
# disagreement point (its reported basis) counts as "caught a liar" — the robot
# blacklists the counterpart. The IR-veto tiers keep both surpluses strictly
# positive, so this fires only in the naive-cooperation (trust-open) tier where
# an inflated-BATNA liar can push the joint pick past an honest partner's batna.
# DECENTRALISATION CAVEAT (documented, not a bug): own realized surplus is the
# ONLY signal a robot has — it cannot see the counterpart's books, so it cannot
# tell a liar-strip from a benign joint-max SACRIFICE (a bundle it knowingly
# takes a loss on for the larger joint good). Empirically those two loss
# distributions overlap (no clean material cutoff exists), so outcome-based
# reputation is intrinsically NOISY: it blacklists honest sacrifice-beneficiaries
# too. "Materially" is therefore any loss beyond rounding; the re-encounter
# GATING (a mark only bites when the pair meets again), not the mark's precision,
# is what makes reputation scale with N — the registered mechanism.
REPUTATION_MARK_EPS = 1e-9

# Differential-oracle switch: force every SnhpArm._evaluate onto the scalar
# fallback (the byte-identical reference path). The optimized fast path and this
# scalar path MUST produce identical trajectories; the oracle test flips this and
# byte-compares. Never set in production.
FORCE_SCALAR_EVAL = False

CARGO_OPTS = [-4, -2, -1, 0, 1, 2, 4]
ENERGY_OPTS = [-8.0, -4.0, -2.0, 0.0, 2.0, 4.0, 8.0]
SECTOR_OPTS = [0, 1]
MAX_CARGO = max(CARGO_OPTS)
# v12 K1: map-sync as a 4th bundle issue. Directional — +1 = a→b, -1 = b→a,
# 0 = no sync. Cross-company only (same-company rows masked in _evaluate). NOTE:
# this is 3 options, so the contract space grows ×3 (7×7×2×3 = 294 rows) under
# map_trading, not the ×2/196 the build note first sketched before revising the
# design to a signed direction — flagged in the report.
MAP_OPTS = [-1, 0, 1]
# v12 K0: scouting thresholds (movement policy; consume no RNG).
SCOUT_STALE = 250               # a company map point staler than this is worth
                                # a scouting trip
SCOUTS_MAX = 2                  # at most this many robots per company scout at
                                # once (deterministic tie-break by rid)


# ── shared movement policy ──────────────────────────────────────────────
def scout_target(r, w):
    """v12 K0: the asteroid position robot r should scout THIS tick, or None.
    Gated on scouting+belief_mode. A robot scouts (heads to its company's
    stalest map point — the one it saw least recently) when it has no load,
    enough battery for the round trip (× 1.5 safety), and EITHER its company's
    believed field is entirely empty (Trigger A — replaces the terminal idle
    charge) OR that stalest point is staler than SCOUT_STALE (Trigger B — a
    diversion from mining to refresh the map). At most SCOUTS_MAX robots per
    company scout at once; the cap is applied to BOTH triggers (a believed-empty
    field must not stampede the whole fleet to one rock), broken deterministically
    by rid. Consumes NO RNG. Reads raw company belief (no live-sense side effect).
    Unknown arrivals are discovered en route via R_SENSE (world sensing)."""
    if not (w.scouting and w.belief_mode) or r.stranded or r.load > 0:
        return None
    co = r.company
    # v14: scouting is mechanically unchanged, but under gossip a robot reads
    # its OWN map (_bx=rid) — discoveries spread only by contact, so a scout's
    # find is worthless until gossip relays it (the registered scout-return
    # problem). Free radio keeps the shared company map (_bx=company).
    bx = w._bx(r)
    ls = w.last_seen[bx]
    n = len(w.sources)
    idx = min(range(n), key=lambda i: (ls[i], i))   # stalest (tie-break lo idx)
    staleness = w.tick - ls[idx]
    field_empty = all(w.belief[bx][i] <= 0 for i in range(n))
    if not (field_empty or staleness > SCOUT_STALE):
        return None
    pos = w.sources[idx]

    def eligible(x) -> bool:
        if x.company != co or x.stranded or x.load > 0:
            return False
        round_trip = 2 * W.manhattan(x.pos, pos) * x.eff
        return x.bat() > 1.5 * round_trip

    if not eligible(r):
        return None
    scouts = sorted(x.rid for x in w.robots if eligible(x))   # rid tie-break
    if r.rid not in scouts[:SCOUTS_MAX]:
        return None
    return pos


def order_target(r, w):
    """v23 (column V): the pinned-order location an EMPTY robot r should route to
    in order to accept it, or None. A drone with capacity heads to the best known
    relay order whose residual cargo it can profitably haul FROM HERE — net
    delivery credit beats the (empty-to-pin + loaded-pin-to-refinery) haul at its
    own shadow price, and it has battery for the whole trip. Reuses the delivery
    valuation (delivery_target/credit_rate) — no new planner. Reads known_orders
    (proximity-discovered) only; consumes no RNG. Value-per-distance tie-break
    mirrors best_claim so routing is deterministic."""
    if not w.order_book or r.stranded or r.load >= r.cap or not w.known_orders[r.rid]:
        return None
    ref = w._home_ref(r.company)
    dest = w.refineries[ref]
    rate = w.credit_rate(r.company, ref)
    by_oid = {o["oid"]: o for o in w.orders}
    best_loc, best_score = None, 0.0
    for oid in w.known_orders[r.rid]:
        o = by_oid.get(oid)
        if o is None or o["poster"] == r.rid or o["poster_co"] != r.company:
            continue
        if r.load + o["q"] > r.cap:
            continue
        to_pin = W.manhattan(r.pos, o["loc"])
        pin_to_ref = W.manhattan(o["loc"], dest)
        need = to_pin * r.eff + pin_to_ref * r.eff * (1 + W.LOADED_MULT)
        if r.bat() <= need:                       # can't complete the trip
            continue
        resid = (1.0 - o["alpha"]) * o["q"]
        credit = resid * rate * W.V_DELIVER + o["energy"] * (1 - W.TRANSFER_LOSS)
        haul_cost = (to_pin + pin_to_ref * (1 + W.LOADED_MULT)) * r.eff * r.ev
        net = credit - haul_cost
        if net <= 0:
            continue
        score = net / (to_pin + 4.0)
        if score > best_score:
            best_loc, best_score = o["loc"], score
    return best_loc


def intent(r, w):
    if r.stranded:
        return None
    charger, _ = w.nearest_charger(r)
    if r.charge_queued_at >= 0 and r.bat() < 0.95 * W.BATTERY_MAX:
        return charger
    if r.load > 0:
        # v10c: a rate-limited miner stays docked until cap-full — mining
        # is stationary (no battery drain), so letting the load>0 branch
        # pull it away would re-price mine_rate as trip SIZE, not speed
        if (w.mine_trait and r.load < r.cap
                and r.pos == w.sources[r.sector]
                and w.stock_belief(r, r.sector) > 0):
            return r.pos
        ref = delivery_target(r, w)             # sticky (hysteresis)
        dest = w.refineries[ref]
        cost = W.manhattan(r.pos, dest) * r.eff * (1 + W.LOADED_MULT)
        return dest if r.bat() > cost else charger
    r.target_ref = None
    if r.bat() < safe_return_threshold(r, w):   # v12: charge precedence stays
        return charger
    if w.order_book:                            # v23: route to a known relay order
        ot = order_target(r, w)                 # (below charging, above mining —
        if ot is not None:                      # servicing a pin competes with a
            return ot                           # fresh dig for an empty drone)
    if w.scouting:                              # v12 K0: scout a stale/empty map
        st = scout_target(r, w)                 # (both triggers; gated + no RNG)
        if st is not None:
            w.scout_ticks += 1
            return st
    if w.stock_belief(r, r.sector) <= 0:        # claim BELIEVED depleted →
        r.sector = w.best_claim(r)              # re-claim (v10a: a robot ON
    if w.stock_belief(r, r.sector) > 0:         # an empty rock senses truth
        return w.sources[r.sector]              # this tick — no livelock)
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
        # Pad unloads on arrival: if the arrival step itself stranded the
        # robot ON its target refinery, the refinery still takes the cargo
        # (facility-side action, same tick). Otherwise intent() returns None
        # from now on and drop() can never fire — the ore is trapped on the
        # pad unless a rescue arrives (audit: ~9-15 ore/run entered this trap
        # in EVERY arm; rescue-capable arms ransomed it back, others lost it,
        # a differential subsidy). Gated on `stranded` so healthy
        # trajectories are unchanged (they still deliver next tick).
        if r.stranded and r.pos == t and t in w.refineries:
            w.drop(r)


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


# The exact set of fields apply_bundle mutates on a robot (verified against
# transfer_cargo / transfer_energy / swap_sectors / debit_energy / _maybe_strand):
# battery, load, load_prov (contents), sector, target_ref, stranded,
# received_units. Snapshot/restore of precisely these replaces copy.copy(a) —
# same arithmetic, same order, and the robot is left byte-identical to pristine.
def _snap(r):
    lp = r.load_prov
    return (r.battery, r.load, lp[0], lp[1], r.sector,
            r.target_ref, r.stranded, r.received_units)


def _restore(r, s):
    r.battery = s[0]
    r.load = s[1]
    r.load_prov[0] = s[2]
    r.load_prov[1] = s[3]
    r.sector = s[4]
    r.target_ref = s[5]
    r.stranded = s[6]
    r.received_units = s[7]


def _energy_post(w, a, b, e, a_snap, b_snap):
    """Post-(battery, stranded) for both robots after the energy leg of a
    bundle with transfer `e`, using the REAL physics functions (bit-exact by
    reuse). Battery/stranded depend ONLY on `e` — cargo and sector never touch
    them — so this is computed once per distinct energy option and reused across
    every (q, ·, s) bundle. Mirrors apply_bundle's energy+TXN sequence exactly
    (transfer_energy, then debit both by TXN_COST), then restores a and b."""
    if e > 0:
        w.transfer_energy(a, b, e, log=False)
    elif e < 0:
        w.transfer_energy(b, a, -e, log=False)
    w.debit_energy(a, W.TXN_COST)
    w.debit_energy(b, W.TXN_COST)
    out = (a.battery, a.stranded, b.battery, b.stranded)
    _restore(a, a_snap)
    _restore(b, b_snap)
    return out


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
        # v22 (column U): re-encounter counter — {(lo_rid, hi_rid): meetings}, one
        # increment per post-cooldown interaction opportunity (the reputation
        # theory's driver: mean meetings-per-pair falls with N at fixed density).
        # Pure bookkeeping (no RNG, no physics) → bit-safe for every arm/column.
        self._pair_meets: dict = {}

    def deal_pause(self) -> int:
        """Ticks BOTH parties hold position after an executed exchange.
        Uniform W.DEAL_PAUSE for pairwise arms (two parties is two parties at
        any N). TeamArm overrides to add the v13 consensus cost."""
        return W.DEAL_PAUSE

    def tick(self):
        w = self.w
        w._live_sense = True           # v10: drive/world phase — sensing live
        w.field_step()                 # v11: arrivals/departures fire at TICK
                                       # START — before EV, drives and every
                                       # bundle evaluation, so no field change
                                       # ever lands mid-encounter (evaluated Φ
                                       # == executed Φ). No-op when off.
        if w.tick % EV_REFRESH == 0:
            for r in w.robots:
                update_ev(r, w)
        order = list(w.robots)
        w.rng.shuffle(order)
        for r in order:
            if w.tick < r.busy_until:      # docked mid-transfer — cannot move
                continue
            drive(r, w)
        w.charge_step()
        w.sense_step()                 # v10a: field sweep + belief freeze —
                                       # (v23: also stigmergic order discovery)
        w.expire_orders()              # v23: retire lapsed orders (no-op off)
        busy = set()                   # beliefs may NOT change during the
                                       # encounter phase (evaluated Φ ==
                                       # executed Φ is priced on them)
        for a, b in w.encounters():
            if a.rid in busy or b.rid in busy:
                continue
            if w.tick < a.busy_until or w.tick < b.busy_until:
                continue                    # still executing a prior exchange
            key = (min(a.rid, b.rid), max(a.rid, b.rid))
            last, was_deal = self._last_try.get(key, (-10**9, False))
            cool = DEAL_COOLDOWN if was_deal else ATTEMPT_COOLDOWN
            if w.tick - last < cool:
                continue
            self._pair_meets[key] = self._pair_meets.get(key, 0) + 1
            struck = self.encounter(a, b)
            self._last_try[key] = (w.tick, struck)
            if struck:
                # transfers take time: both parties hold position while the
                # exchange physically executes (energy docking / cargo
                # handoff). Pairwise arms pause W.DEAL_PAUSE; the team's joint
                # pick pays the v13 consensus cost on top (deal_pause()).
                pause = self.deal_pause()
                a.busy_until = w.tick + pause
                b.busy_until = w.tick + pause
            busy.add(a.rid)
            busy.add(b.rid)
        self._order_phase()            # v23: post + accept pinned orders
        w.tick += 1

    def _order_phase(self) -> None:
        """v23 (column V): the order-book posting + acceptance hook. No-op for
        non-order arms (auction/rules), so the order book is a bargaining-family
        primitive — the auction stays the unperturbed comparator."""
        return

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
        # v12 K1: the map axis is appended ONLY under map_trading, so a world
        # without the flag builds the EXACT pre-v12 space (bit-identical). The
        # map dimension is priced/masked cross-company in _evaluate.
        self.has_map = bool(getattr(w, "map_trading", False))
        if self.has_map:
            opts.append(MAP_OPTS)
        self.space = generate_contract_space(opts)
        # precompute the (q, e, s) triples once — the space never changes, so
        # the hot loop reads native ints/floats instead of re-unpacking numpy
        # rows every encounter. The all-zero row (the batna reference) gets a
        # fixed index so it is priced at the pristine state, never applied.
        self._rows = [(int(r[0]), float(r[1]), int(r[2])) for r in self.space]
        # the batna reference is the fully-zero bundle; under map_trading the
        # (0,0,0) cargo/energy/sector triple also appears with m=-1/+1 (real map
        # syncs), so pin m==0 too — those map rows must still be applied+priced.
        self._allzero = next(k for k, r in enumerate(self.space)
                             if r[0] == 0 and r[1] == 0 and r[2] == 0
                             and (not self.has_map or r[3] == 0))
        # bundle-space columns and their bundle-only derivatives are FIXED, so
        # precompute them once; _feas_mask then does only the robot-dependent
        # comparisons each encounter (numpy, one pass — byte-identical booleans).
        q = self.space[:, 0]
        e = self.space[:, 1]
        self._fq = q
        self._f_posq = q > 0
        self._f_negq = q < 0
        self._f_negamt = -q                     # the |q| used in the q<0 branch
        self._f_enz = e != 0
        self._f_epos = e > 0
        self._f_abse = np.abs(e)
        self._f_abse_loss = self._f_abse * (1 - W.TRANSFER_LOSS)

    def _row(self, k):
        """(q, e, s, m) for contract-space row k; m=0 unless the map issue is on."""
        row = self.space[k]
        m = int(row[3]) if self.has_map else 0
        return int(row[0]), float(row[1]), int(row[2]), m

    # Fast Φ covers the CORE config; belief/life/map fundamentally reshape Φ
    # (stock_belief side-channels, v_life instead of P_STRAND, synced map
    # overlays) and dispatch to the byte-identical scalar path below.
    def _fast_ok(self) -> bool:
        if FORCE_SCALAR_EVAL:            # differential-oracle switch (tests)
            return False
        w = self.w
        # v17 PHASE 2: bills reshapes the load term (holder residual + undiscounted
        # claims) → scalar dispatch. firm_relay leaves Φ untouched (it only re-books
        # credit) → the fast path stays, exactly as registered.
        # v22 (column U): reputation is decided ENTIRELY outside _evaluate — a
        # blacklist REFUSAL fires before Φ is ever priced, and marking is post-deal
        # bookkeeping — so Φ is byte-identical and the fast path is KEPT (no
        # scalar dispatch; the differential oracle stays green under reputation).
        return not (w.belief_mode or w.life_pricing or self.has_map or w.bills)

    def _feas_mask(self, a, b):
        """_feasible over the whole bundle space in ONE numpy pass, reusing the
        precomputed bundle-only columns — byte-identical booleans to the scalar
        _feasible(a,b,q,e) per row. (Tier 1.2)"""
        q = self._fq
        ok = ~(self._f_posq & ((a.load < q) | ((b.cap - b.load) < q)))
        negamt = self._f_negamt
        ok &= ~(self._f_negq & ((b.load < negamt) | ((a.cap - a.load) < negamt)))
        epos = self._f_epos
        donor_bat = np.where(epos, a.battery, b.battery)
        recv_bat = np.where(epos, b.battery, a.battery)
        ok &= ~(self._f_enz & (((donor_bat - 1.0) < self._f_abse)
                               | ((W.BATTERY_MAX - recv_bat) < self._f_abse_loss)))
        return ok

    # ── v17 PHASE 2 (snhp+bill): claim-aware bundle valuation ─────────────
    def _bills_ctx(self, a, b):
        """Per-encounter constants for the claim correction: pristine holder
        residual + own-claim value for each robot, the FIFO cumulative-residual
        prefix (the moved head's residual R_move = cum[|q|]), and the giver's
        split fraction α* = (1+giver_disc)/2 — a Nash division of the cargo-value
        component that is a function of PRE-deal state only, hence reproduced
        identically at execution (the evaluated==executed guarantee).
        P23e: under bills_contingent it also carries the DECAYED-residual prefix
        (Σ res_i·decay_i, decay from each parcel's OPEN leg vs its geodesic cf) —
        the giver's banked claim VALUE (not its physical share) decays by it."""
        w = self.w
        cont = w.bills_contingent
        own_a, claim_a = owned_and_claim(a)
        own_b, claim_b = owned_and_claim(b)

        def cum(r, holder_pos):
            c = [0.0]
            cd = [0.0]
            for p in r.parcels:
                res = 1.0 - sum(sh for _rid, sh, *_ in p["claims"])
                c.append(c[-1] + res)
                if cont:
                    cd.append(cd[-1] + res * w.leg_decay(p, holder_pos))
            return c, cd

        cumA, cumA_dec = cum(a, a.pos)
        cumB, cumB_dec = cum(b, b.pos)
        _, disc_a = load_factors(a, w)
        _, disc_b = load_factors(b, w)
        return dict(own_a=own_a, claim_a=claim_a, own_b=own_b, claim_b=claim_b,
                    cumA=cumA, cumB=cumB, cumA_dec=cumA_dec, cumB_dec=cumB_dec,
                    alpha_a=0.5 * (1.0 + disc_a), alpha_b=0.5 * (1.0 + disc_b))

    def _bills_post(self, q, c):
        """Analytic post-(owned, claim) for both robots after moving |q| FIFO-head
        parcels — parcels are NOT moved on the log=False eval pass, so the split
        is derived from the prefix sums instead. The giver keeps α*·R_move as an
        undiscounted claim; the receiver carries the (1−α*)·R_move residual.
        P23e: the PHYSICAL residual moved (own bookkeeping) is always α*·R, but the
        giver's claim VALUE uses the decayed prefix α*·Σ res_i·decay_i (==α*·R when
        flat), so contingent OFF is bit-identical."""
        V = W.V_DELIVER
        cont = self.w.bills_contingent
        if q > 0:
            R = c["cumA"][q]
            s_phys = R * c["alpha_a"]
            s_val = (c["cumA_dec"][q] if cont else R) * c["alpha_a"]
            return (c["own_a"] - R, c["claim_a"] + s_val * V,
                    c["own_b"] + (R - s_phys), c["claim_b"])
        if q < 0:
            R = c["cumB"][-q]
            s_phys = R * c["alpha_b"]
            s_val = (c["cumB_dec"][-q] if cont else R) * c["alpha_b"]
            return (c["own_a"] + (R - s_phys), c["claim_a"],
                    c["own_b"] - R, c["claim_b"] + s_val * V)
        return c["own_a"], c["claim_a"], c["own_b"], c["claim_b"]

    def _bills_add(self, ua, ub, k, q, a, b, c):
        """Add the claim correction to bundle k's utilities. a and b are already
        in the post-state (load/battery/sector) for q≠0, pristine for q==0, so
        bills_correction reads the right load/discount and we feed the analytic
        owned/claim above."""
        oa, cla, ob, clb = self._bills_post(q, c)
        ua[k] += bills_correction(a, self.w, oa, cla)
        ub[k] += bills_correction(b, self.w, ob, clb)

    def _bills_attach(self, giver, receiver, n, alpha, decays=None):
        """Execution: record the giver's claim (giver.rid, α·residual[, decay]) on
        each of the n just-moved parcels (now the receiver's FIFO tail) and bank the
        claim VALUE into giver.claim_value. Matches _bills_post exactly. Flat
        (decays None) appends 2-tuples and banks α·R_move; P23e contingent appends
        3-tuples and banks α·Σ res_i·decay_i (decays aligned to the FIFO head)."""
        s_val = 0.0
        for i, p in enumerate(receiver.parcels[-n:]):
            res = 1.0 - sum(sh for _rid, sh, *_ in p["claims"])
            share = alpha * res
            if decays is None:
                p["claims"].append((giver.rid, share))
                s_val += share
            else:
                p["claims"].append((giver.rid, share, decays[i]))
                s_val += share * decays[i]
        giver.claim_value += s_val * W.V_DELIVER

    def _evaluate(self, a, b):
        w = self.w
        space = self.space
        n = len(space)
        ua = np.full(n, -np.inf)
        ub = np.full(n, -np.inf)
        feas = self._feas_mask(a, b)             # one vectorized pass (Tier 1.2)
        a_snap, b_snap = _snap(a), _snap(b)       # snapshot/restore vs copy.copy
        rows = self._rows
        allzero = self._allzero
        apply = apply_bundle
        if self._fast_ok():
            # ── fast path: partial-evaluated Φ, position scans cached once,
            # iterate ONLY feasible bundles (the mask already dropped ~175/196),
            # and derive (battery, stranded) once per energy option (separable
            # from cargo/sector) — no per-bundle mutation, no restore.
            hz = w.hazard_phi
            ca = phi_ctx(a, b.sector, w)
            cb = phi_ctx(b, a.sector, w)
            a_load, a_sec, a_bat, a_str = a.load, a.sector, a.battery, a.stranded
            b_load, b_sec, b_bat, b_str = b.load, b.sector, b.battery, b.stranded
            epost = {}
            for k in feas.nonzero()[0].tolist():
                if k == allzero:
                    ua[k] = fast_phi(a_load, a_bat, a_sec, a_str, ca, hz)
                    ub[k] = fast_phi(b_load, b_bat, b_sec, b_str, cb, hz)
                    continue
                q, e, s = rows[k]
                ep = epost.get(e)
                if ep is None:
                    ep = epost[e] = _energy_post(w, a, b, e, a_snap, b_snap)
                batA, strA, batB, strB = ep
                if s:
                    secA, secB = b_sec, a_sec
                else:
                    secA, secB = a_sec, b_sec
                ua[k] = fast_phi(a_load - q, batA, secA, strA, ca, hz)
                ub[k] = fast_phi(b_load + q, batB, secB, strB, cb, hz)
            return ua, ub
        # ── scalar fallback (byte-identical to the original evaluate) ──────
        same_co = a.company == b.company
        has_map = self.has_map
        bctx = self._bills_ctx(a, b) if w.bills else None
        for k in feas.nonzero()[0].tolist():
            if k == allzero:
                ua[k], ub[k] = phi(a, w), phi(b, w)
                if bctx is not None:                 # batna carries the pristine
                    self._bills_add(ua, ub, k, 0, a, b, bctx)   # claim state
                continue
            q, e, s = rows[k]
            m = int(space[k][3]) if has_map else 0
            # v12 K1: a map sync is meaningless within a company (identical
            # map) — mask (leave -inf). Cross-company syncs price below.
            if m != 0 and same_co:
                continue
            apply(w, a, b, q, e, s, log=False)
            if m == 0:
                ua[k], ub[k] = phi(a, w), phi(b, w)
                if bctx is not None:
                    self._bills_add(ua, ub, k, q, a, b, bctx)
            elif m == 1:
                # a sells its fresher map to b: a's Φ is untouched, b's Φ is
                # scored under a temporary overlay that restores exactly.
                ua[k] = phi(a, w)
                with w.synced_phi_view(b, a):
                    ub[k] = phi(b, w)
            else:                                # m == -1: b sells to a
                ub[k] = phi(b, w)
                with w.synced_phi_view(a, b):
                    ua[k] = phi(a, w)
            _restore(a, a_snap)
            _restore(b, b_snap)
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

    # ── v22 (column U): community reputation ──────────────────────────────
    def _reputation_refuses(self, a, b) -> bool:
        """True iff reputation is on and EITHER party has blacklisted the other —
        the pair is skipped (return False from encounter, NO pause, so the
        ATTEMPT_COOLDOWN governs the next attempt). A no-op short-circuit when
        reputation is off, so the guard leaves the fast path bit-identical."""
        w = self.w
        return w.reputation and (b.rid in w.blacklist[a.rid]
                                 or a.rid in w.blacklist[b.rid])

    def _reputation_record(self, a, b, sa, sb) -> None:
        """Update pairwise reputation after a struck deal. Genuine catch: a robot
        whose realized TRUE surplus fell materially below its disagreement point
        blacklists the counterpart (the lie machinery's observable — an inflated
        BATNA can only push the naive-cooperation pick past an honest partner's
        true batna). Slander: with probability ε (`false_accuse`) a per-deal draw
        from the DEDICATED ε stream (never the main RNG) marks an HONEST
        counterpart as if it had lied. Marks then spread by contact only
        (World._blacklist_gossip_step). Bookkeeping only — never touches Φ."""
        w = self.w
        if sa < -REPUTATION_MARK_EPS:
            w.blacklist[a.rid].add(b.rid)          # a caught b
        if sb < -REPUTATION_MARK_EPS:
            w.blacklist[b.rid].add(a.rid)          # b caught a
        if w.false_accuse > 0.0 and w._eps_rng.uniform() < w.false_accuse:
            if not b.liar:                         # slander lands on the honest
                w.blacklist[a.rid].add(b.rid)
            elif not a.liar:
                w.blacklist[b.rid].add(a.rid)

    def encounter(self, a, b) -> bool:
        w = self.w
        if self._reputation_refuses(a, b):  # v22: refuse a blacklisted partner
            return False
        ua, ub = self._evaluate(a, b)       # RAW: audit + frontier reference
        # the all-zero bundle is Φ at the pristine (disagreement) state — i.e.
        # the batna itself — so read it back instead of recomputing phi twice.
        batna_a, batna_b = float(ua[self._allzero]), float(ub[self._allzero])
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
        q, e, s, m = self._row(sol)
        # v17 PHASE 2 (bills): capture the giver's split fraction from the PRISTINE
        # state (before apply_bundle mutates load/battery) — identical to the α*
        # priced in _bills_ctx, so the claim recorded below reproduces the utility
        # this bundle was evaluated at.
        if w.bills and q != 0:
            giver, receiver = (a, b) if q > 0 else (b, a)
            _, disc_g = load_factors(giver, w)
            bill_alpha = 0.5 * (1.0 + disc_g)
            # P23e: capture each moved parcel's OPEN-leg decay from the PRISTINE
            # pre-apply state (identical to what _bills_ctx priced via cumX_dec),
            # aligned to the FIFO head that apply_bundle is about to move.
            bill_decays = ([w.leg_decay(p, giver.pos)
                            for p in giver.parcels[:abs(q)]]
                           if w.bills_contingent else None)
        distress = (a.stranded or b.stranded
                    or stranding_hazard_true(a, w) > 0.5
                    or stranding_hazard_true(b, w) > 0.5)
        # v10: under belief_mode the TRUE-value audit suspends the FIELD
        # beliefs too (phi_true_field flips w._oracle_override) — scoring
        # sa_true against the same stale map that signed the deal would
        # hide exactly the poisoning P15c is looking for. Gauge suspension
        # rides along as in v7; phi_true_field ≡ phi_true when belief off.
        audit = a.gauge_bias != 0.0 or b.gauge_bias != 0.0 or w.belief_mode
        truth = phi_true_field if w.belief_mode else phi_true
        ta0 = truth(a, w) if audit else None
        tb0 = truth(b, w) if audit else None
        apply_bundle(w, a, b, q, e, s, log=True)
        # v12 K1: execute the map sync PERMANENTLY (same overlay synced_phi_view
        # priced). Kept out of apply_bundle because that runs on robot COPIES in
        # evaluation, whereas a sync mutates shared COMPANY state — so evaluation
        # must use the restoring view and only execution writes through.
        if m == 1:
            w.apply_map_sync(b, a)               # a → b
        elif m == -1:
            w.apply_map_sync(a, b)               # b → a
        # v17 PHASE 2 (bills): attach the notarized split to the just-moved parcels
        # BEFORE the invariant check, so the claim state Φ now sees is exactly what
        # the evaluator priced (_bills_post) — evaluated Φ == executed Φ.
        if w.bills and q != 0:
            self._bills_attach(giver, receiver, abs(q), bill_alpha, bill_decays)
        if w.bills:
            pa, pb = phi_bills(a, w), phi_bills(b, w)
        else:
            pa, pb = phi(a, w), phi(b, w)
        assert abs(pa - ua[sol]) < 1e-9 and abs(pb - ub[sol]) < 1e-9, \
            "executed state diverged from evaluated bundle"

        sa, sb = float(ua[sol] - batna_a), float(ub[sol] - batna_b)
        surplus = (ua - batna_a) + (ub - batna_b)
        feasible = np.isfinite(surplus)
        joint_best = float(surplus[feasible].max())
        achieved = float(surplus[sol])
        w.deal_log.append(dict(
            tick=w.tick, a=a.rid, b=b.rid, q=q, e=e, s=s, m=m,
            a_co=a.company, b_co=b.company,
            a_liar=int(a.liar), b_liar=int(b.liar),
            border=int(a.company != b.company), distress=int(distress),
            sa=sa, sb=sb,
            # gauge suspended = ground truth; at zero bias phi_true ≡ phi,
            # so the audit equals the believed surplus without 4 extra Φ evals
            sa_true=(float(truth(a, w) - ta0) if audit else sa),
            sb_true=(float(truth(b, w) - tb0) if audit else sb),
            capture=achieved / joint_best if joint_best > 1e-12 else 1.0))
        self.deals += 1
        if w.reputation:                    # v22: record the counterpart's honesty
            self._reputation_record(a, b, sa, sb)
        return True

    # ── v23 (column V): the stigmergic order book ─────────────────────────
    def _order_phase(self) -> None:
        """Post new relay orders, then accept known ones within pickup range.
        Bargaining-family only (BaseArm's hook is a no-op), so order books are an
        SNHP-native surface; the auction is the unperturbed comparator."""
        w = self.w
        if not w.order_book:
            return
        self._post_orders()
        self._accept_orders()

    def _plausible_taker_clears(self, r, alpha) -> bool:
        """Registered posting gate: would a HEALTHY fleetmate hauling the residual
        FROM r's location to the company refinery clear IR? Residual delivery
        credit vs the loaded haul at the reference shadow price (EV_INIT). Derived
        from the delivery valuation — no new planner."""
        w = self.w
        ref = w._home_ref(r.company)
        dest = w.refineries[ref]
        rate = w.credit_rate(r.company, ref)
        resid_units = (1.0 - alpha) * r.load
        haul = W.manhattan(r.pos, dest) * (1 + W.LOADED_MULT)   # ref eff = 1.0
        return resid_units * rate * W.V_DELIVER > haul * W.EV_INIT

    def _phi_without_load(self, r) -> float:
        """Spot Φ if r shed its whole load (load→0). phi() reads r.load directly
        and never the parcels/claims, so toggling the integer load is exact — a
        lighter drone faces a smaller loaded-move cost and strand hazard, so this
        is 'the Φ of holding' counterfactual, read off the existing phi()."""
        saved = r.load
        r.load = 0
        val = phi(r, self.w)
        r.load = saved
        return val

    def _post_orders(self) -> None:
        """The registered trigger: post when the drone's own Φ for HAULING/HOLDING
        the load is negative — read as the generous faithful union of (a) stranded
        (it cannot move at all, so async is its only channel), (b) shedding the
        load would RAISE its spot Φ (the discounted cargo value no longer covers
        the strand hazard the load adds), or (c) it cannot feasibly complete the
        LOADED haul from here (disc<1) — AND the posted terms clear IR for a
        plausible taker (the registered gate). Straight off phi()/load_factors; no
        new planner. One active order per poster. The split α* = (1+giver_disc)/2
        is the exact Nash division bills uses at a synchronous handoff — a
        function of the poster's PRE-post discount only, so it is split-independent
        and reproduced identically at acceptance."""
        w = self.w
        posted = {o["poster"] for o in w.orders}
        for r in w.robots:
            if r.rid in posted or w.tick < r.busy_until or r.load <= 0:
                continue
            _rate, disc = load_factors(r, w)
            burdened = (r.stranded or disc < 1.0 - 1e-9
                        or self._phi_without_load(r) > phi(r, w) + 1e-9)
            if not burdened:                            # holding still pays → keep
                continue
            alpha = 0.5 * (1.0 + disc)
            if not self._plausible_taker_clears(r, alpha):
                continue
            w.post_order(r, r.load, alpha)              # relay the whole burden

    def _accept_orders(self) -> None:
        """Every non-busy, un-stranded drone within pickup range of a KNOWN order
        accepts the one that most raises its Φ (IR>0). Acceptance is UNILATERAL
        (no consensus) and pays NO DEAL_PAUSE. The evaluated Φ (a tentative pickup
        on exactly the taker-state fields Φ reads) MUST equal the executed Φ — the
        sacred bills invariant, asserted live. An order inspected-and-declined at
        range is dropped from memory so the drone does not re-route to it."""
        w = self.w
        by_oid = {o["oid"]: o for o in w.orders}
        for r in w.robots:
            if w.tick < r.busy_until or r.stranded:
                continue
            kn = w.known_orders[r.rid]
            if not kn:
                continue
            phi_before = phi_bills(r, w)
            best, best_gain, best_eval = None, 1e-9, None
            declined_here = []
            for oid in list(kn):
                o = by_oid.get(oid)
                if o is None:
                    kn.discard(oid)
                    continue
                if o["poster"] == r.rid or o["poster_co"] != r.company:
                    continue
                if max(abs(r.pos[0] - o["loc"][0]),
                       abs(r.pos[1] - o["loc"][1])) > W.R_PICKUP:
                    continue
                if r.load + o["q"] > r.cap:
                    continue
                phi_eval = self._accept_phi(r, o)
                gain = phi_eval - phi_before
                declined_here.append(oid)
                if gain > best_gain:
                    best, best_gain, best_eval = o, gain, phi_eval
            if best is None:
                for oid in declined_here:              # inspected, IR failed → forget
                    kn.discard(oid)
                continue
            w.accept_order(r, best)
            kn.discard(best["oid"])
            by_oid.pop(best["oid"], None)
            phi_exec = phi_bills(r, w)
            assert abs(phi_exec - best_eval) < 1e-9, \
                "order acceptance diverged from evaluated Φ"

    def _accept_phi(self, r, o) -> float:
        """Tentative Φ_bills after picking up order o — mutates ONLY the taker
        fields Φ reads (load, parcels, battery), exactly as accept_order will, then
        restores. This makes evaluated==executed hold by construction."""
        w = self.w
        saved_load, saved_parcels, saved_bat = r.load, r.parcels, r.battery
        r.load = r.load + o["q"]
        r.parcels = r.parcels + o["parcels"]
        if o["energy"] > 0:
            got = min(o["energy"] * (1 - W.TRANSFER_LOSS),
                      W.BATTERY_MAX - r.battery)
            r.battery = r.battery + max(0.0, got)
        val = phi_bills(r, w)
        r.load, r.parcels, r.battery = saved_load, saved_parcels, saved_bat
        return val


class TeamArm(SnhpArm):
    """Cooperative greedy joint-Φ over the same bundle space (no IR)."""
    name = "team"
    company_walls = False
    consumes_reports = False    # a merged firm's pick reads true internal books

    def deal_pause(self) -> int:
        """v13 (column L): the team's joint pick is a CONSENSUS, and consensus
        costs rounds. With w.consensus_cost the pause becomes DEAL_PAUSE +
        ⌈log₂(N)⌉ ticks (planning that scales with fleet size); off, it is the
        free-planning ceiling control at plain DEAL_PAUSE."""
        if self.w.consensus_cost:
            return W.DEAL_PAUSE + int(math.ceil(math.log2(len(self.w.robots))))
        return W.DEAL_PAUSE

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
        if self._reputation_refuses(a, b):  # v22: refuse a blacklisted partner
            return False
        trusted = (a.attested and b.attested) if self.gated else True
        if not trusted:
            # the untrusted tier IS the veto tier — same lies, distrust tax
            # and audit log as any defended Nash-IR encounter. (Review: this
            # tier used to run lie-free on true books, so the gated result
            # measured pure access denial rather than relegation.)
            return SnhpArm.encounter(self, a, b)
        ua, ub = self._evaluate(a, b)
        batna_a, batna_b = float(ua[self._allzero]), float(ub[self._allzero])
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

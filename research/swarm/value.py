"""Φ and the ONE routing function (SPEC.md v4.0).

Panel mandate (PANEL_V4.md, M4): the movement policy and Φ's load term must
consume the SAME `delivery_target()` — three separate re-entry paths for the
v2.1 silent-dead-issue bug existed when they could diverge. Tariffs enter
per-unit credit here and nowhere else; EV (the energy shadow price that
trades credit against haul distance) is endogenous per robot — a lagged
finite-difference ∂Φ/∂battery — instead of a hand-set constant.
"""
from __future__ import annotations

import math

from swarm import world as W


def safe_return_threshold(r, w) -> float:
    """Battery level below which an unloaded robot should head to charge."""
    _, d = w.nearest_charger(r)
    return (d + 4) * r.eff * 1.2


def _ref_score(r, w, ref_idx: int, from_pos) -> float:
    """Net value of hauling the current load from `from_pos` to refinery
    `ref_idx`: tariff-adjusted credit minus energy cost at the robot's own
    shadow price."""
    credit = w.credit_rate(r.company, ref_idx) * W.V_DELIVER * max(r.load, 1)
    haul = W.manhattan(from_pos, w.refineries[ref_idx]) * r.eff * (1 + W.LOADED_MULT)
    return credit - haul * r.ev


def delivery_target(r, w, from_pos=None, sticky: bool = True) -> int:
    """Index of the refinery this robot should deliver to. Hysteresis: keep
    the current target unless a challenger wins by TARGET_MARGIN (prevents
    argmax flip-flop when deals change load mid-route — panel M4)."""
    pos = from_pos if from_pos is not None else r.pos
    scores = [_ref_score(r, w, i, pos) for i in range(len(w.refineries))]
    best = max(range(len(scores)), key=lambda i: scores[i])
    if (sticky and from_pos is None and r.target_ref is not None
            and r.target_ref < len(scores)
            and scores[r.target_ref] >= scores[best] - W.TARGET_MARGIN):
        return r.target_ref
    if sticky and from_pos is None:
        r.target_ref = best
    return best


def stranding_hazard(r, w) -> float:
    """P(strand soon), smooth in the energy margin to the charger (-hz Φ)."""
    _, d = w.nearest_charger(r)
    margin = r.bat() - d * r.step_cost()
    return 1.0 / (1.0 + math.exp(margin / W.HAZARD_SCALE))


def _future_trips_value(r, w) -> float:
    """Value of the (source, refinery) loop the movement policy will ACTUALLY
    run: own sector while stocked, cross-mining fallback — NOT a max over
    sectors (v2.1 lesson: a free max prices sector swaps at zero and silently
    kills the issue). The refinery leg uses the same delivery_target scoring,
    tariff-aware."""
    cand = r.sector if w.stock_belief(r, r.sector) > 0 else w.best_claim(r)
    for s in (cand,):
        stock = w.stock_belief(r, s)          # v10a: the company's map
        if w.belief_mode and w.race_pricing:
            # v10b: rivals are racing you to the rock — expected stock at
            # arrival discounts belief by the observed rival depletion rate
            # over the approach ETA (movement is 1 cell/tick). Un-raced
            # fields reduce to current behavior (rate → 0).
            eta = W.manhattan(r.pos, w.sources[s])
            # v14: the rival-rate estimate is per-robot under gossip (_bx=rid),
            # the shared company estimate under free radio (_bx=company).
            stock = max(0.0, stock - w.rival_rate[w._bx(r)][s] * eta)
        if stock <= 0:
            continue
        src = w.sources[s]
        ref = delivery_target(r, w, from_pos=src, sticky=False)
        rate = w.credit_rate(r.company, ref)
        leg = W.manhattan(src, w.refineries[ref])
        approach = W.manhattan(r.pos, src) * r.eff
        cycle_cost = 2 * leg * r.eff * (1 + W.LOADED_MULT / 2)
        spare = max(0.0, r.bat() - approach - 0.15 * W.BATTERY_MAX)
        trips = spare / max(cycle_cost, 1e-9)
        claim = stock / max(1.0, len(w.robots) / 2)
        return (W.FUTURE_DISCOUNT * min(trips * r.cap, claim)
                * rate * W.V_DELIVER)
    return 0.0


def v_life(r, w) -> float:
    """v9: the drone's REMAINING CAREER value — its fleet-share of the whole
    remaining field (a chassis re-claims sectors as they deplete, so the
    career is field-bound, not sector-bound), net of haul energy at the
    robot's own shadow price, plus the cargo it would take down with it,
    plus exogenous replacement capital. Independent of current charge (a
    dying robot's low battery must not talk itself into being worthless).
    Decays to ~0 as the field depletes, so endgame abandonment stays
    rational while early-run drones are expensive to lose."""
    doomed = r.load * W.V_DELIVER + w.strand_cap
    # nominal fleet size, not live count: a deal's own execution can strand
    # the donor, and an alive-count share would make evaluated Φ diverge
    # from executed Φ (the one invariant every arm asserts per deal)
    share = sum(w.stock_belief(r, i)          # v10a: BELIEVED field share
                for i in range(len(w.sources))) / max(1, len(w.robots))
    cand = r.sector if w.stock_belief(r, r.sector) > 0 else w.best_claim(r)
    if share <= 0 or w.stock_belief(r, cand) <= 0:
        return doomed
    src = w.sources[cand]
    ref = delivery_target(r, w, from_pos=src, sticky=False)
    rate = w.credit_rate(r.company, ref)
    leg = W.manhattan(src, w.refineries[ref])
    cycle_cost = 2 * leg * r.eff * (1 + W.LOADED_MULT / 2)
    net_per_unit = max(0.0, rate * W.V_DELIVER
                       - cycle_cost * r.ev / max(r.cap, 1))
    return share * net_per_unit + doomed


def _strand_price(r, w) -> float:
    """What Φ charges for a stranding: the drone's remaining career under
    v9 life-pricing, the flat P_STRAND otherwise. Used consistently in the
    stranded state, the hazard term, and (through both) rescue surplus."""
    return v_life(r, w) if w.life_pricing else W.P_STRAND


def phi(r, w) -> float:
    if r.stranded:
        return -_strand_price(r, w)
    v = 0.0

    # value of the load currently carried — tariff-aware, same routing the
    # policy will use (panel M4: an un-tariffed load term would misprice
    # every border cargo bundle identically in evaluation and execution,
    # invisible to the evaluated==executed assert)
    if r.load > 0:
        ref = delivery_target(r, w, sticky=False)
        rate = w.credit_rate(r.company, ref)
        cost_to_ref = (W.manhattan(r.pos, w.refineries[ref])
                       * r.eff * (1 + W.LOADED_MULT))
        full = r.load * rate * W.V_DELIVER
        if r.bat() > cost_to_ref:
            v += full
        else:
            v += 0.5 * full * r.bat() / (cost_to_ref + 1e-9)

    v += _future_trips_value(r, w)

    if w.hazard_phi:
        v -= _strand_price(r, w) * stranding_hazard(r, w)
    else:
        _, d = w.nearest_charger(r)
        if r.bat() < d * r.step_cost():
            v -= _strand_price(r, w)
    return v


def update_ev(r, w, delta: float = 2.0) -> None:
    """Lagged endogenous energy shadow price: EV ← ∂Φ/∂battery by finite
    difference at the robot's current state, clamped. Called every few ticks
    by the arm loop; `w.freeze_ev` pins it for estimator-sensitivity runs."""
    if w.freeze_ev is not None:
        r.ev = w.freeze_ev
        return
    b0 = r.battery
    p0 = phi(r, w)
    # perturb the BELIEVED reading, not the true axis: Φ consumes bat(), so
    # stepping .battery by delta measured (1+gauge_bias)·∂Φ/∂believed — a
    # second, unintended miscalibration channel (review). At zero bias this
    # is identical to the old step.
    step = delta / max(0.05, 1.0 + r.gauge_bias)
    r.battery = min(W.BATTERY_MAX, b0 + step)
    p1 = phi(r, w)
    r.battery = b0
    grad = (p1 - p0) / max(1e-9, delta)
    if grad > 1e-9:
        r.ev = float(min(W.EV_MAX, max(W.EV_MIN, grad)))


# ── v17 PHASE 2 (snhp+bill): claimed-cargo Φ ──────────────────────────────
# A bill of lading splits a parcel's terminal payout into recorded (rid, share)
# claims; the current HOLDER owns the residual (1 − Σshare). Under bills Φ values
# carried cargo at the holder's RESIDUAL units (feasibility-discounted exactly as
# the load term) and ADDS the robot's outstanding own-claims UNDISCOUNTED — a
# claim pays out at delivery regardless of the claimant's position, which is the
# whole point (it lifts the feasibility discount off the value a far middle drone
# locks in, so the sell-leg clears IR where spot's hold-up refused it). Bills
# dispatch to the scalar path (arms._fast_ok); this is the correction added on top
# of scalar phi(). NOT byte-identical to spot BY DESIGN — bills is a new mechanism.
def load_factors(r, w):
    """(rate, disc) EXACTLY as phi()'s load block computes them: the tariff-aware
    per-unit rate for the delivery_target refinery and the feasibility discount
    (1 if the battery clears the haul, else the same 0.5·bat/cost taper). Bills
    reuses these to swap the load term's integer COUNT for the holder's residual
    UNITS — op-for-op, so evaluated Φ == executed Φ survives."""
    ref = delivery_target(r, w, sticky=False)
    rate = w.credit_rate(r.company, ref)
    cost = W.manhattan(r.pos, w.refineries[ref]) * r.eff * (1 + W.LOADED_MULT)
    bat = r.bat()
    disc = 1.0 if bat > cost else 0.5 * bat / (cost + 1e-9)
    return rate, disc


def owned_and_claim(r):
    """(Σ holder-residual over carried parcels, outstanding own-claim value).
    Read from r's ACTUAL parcels — used at execution and by phi_bills."""
    owned = 0.0
    for p in r.parcels:
        # P23e: claims are (rid, share[, decay]); the holder's residual is the
        # PHYSICAL share (2nd field) — decay scales the payout, not ownership.
        owned += 1.0 - sum(sh for _rid, sh, *_ in p["claims"])
    return owned, r.claim_value


def bills_correction(r, w, owned=None, claim=None):
    """The additive term that turns scalar phi(r) into the bills Φ: replace the
    integer-load contribution (load·rate·V·disc) with the holder-residual value
    (owned·rate·V·disc) and add the UNDISCOUNTED own-claims. owned/claim default
    to the robot's ACTUAL parcels (execution / the eval==exec assert); the
    evaluator passes ANALYTIC post-state values because the log=False bundle pass
    moves load but not parcels."""
    if owned is None:
        owned, claim = owned_and_claim(r)
    if r.load <= 0:                       # no load term in phi ⇒ just the claims
        return claim
    rate, disc = load_factors(r, w)
    return rate * W.V_DELIVER * disc * (owned - r.load) + claim


def phi_bills(r, w) -> float:
    """Bills Φ from the robot's ACTUAL claim state — the reference the in-arm
    evaluated==executed assert compares against."""
    return phi(r, w) + bills_correction(r, w)


def phi_true(r, w) -> float:
    """Φ with the gauge suspended — the ground truth for poisoning audits."""
    saved = r.gauge_bias
    r.gauge_bias = 0.0
    try:
        return phi(r, w)
    finally:
        r.gauge_bias = saved


def phi_true_field(r, w) -> float:
    """v10: Φ with the gauge AND the field beliefs suspended — under
    belief_mode the sa_true/sb_true audit must be scored against the TRUE
    field (w._oracle_override routes stock_belief to truth); phi_true alone
    would audit against the same stale map that signed the deal."""
    saved = r.gauge_bias
    r.gauge_bias = 0.0
    w._oracle_override = True
    try:
        return phi(r, w)
    finally:
        r.gauge_bias = saved
        w._oracle_override = False


def stranding_hazard_true(r, w) -> float:
    """stranding_hazard with the gauge suspended: audit fields in the deal
    log are ground truth, not belief (review: the distress label followed
    the miscalibrated gauge under v7)."""
    saved = r.gauge_bias
    r.gauge_bias = 0.0
    try:
        return stranding_hazard(r, w)
    finally:
        r.gauge_bias = saved


# ── FAST Φ: partial evaluation for the bundle-space hot loop ──────────────
# Within one _evaluate the robot's POSITION is fixed and the world is frozen,
# so every position/world-dependent scan phi does (delivery_target's refinery
# manhattans, nearest_charger, best_claim, credit_rate) is CONSTANT across all
# ~196 bundle post-states. phi_ctx() computes those once; fast_phi() then
# evaluates Φ from ONLY the mutated (load, battery, sector, stranded) fields.
#
# BYTE-EXACT CONTRACT: fast_phi reproduces scalar phi() to the last bit — the
# SAME arithmetic in the SAME associativity, the SAME first-max argmax, the SAME
# min/max/exp builtins. It is valid ONLY for the CORE config (no belief_mode, no
# life_pricing, no map_trading); gauge_bias is handled inline via bat(). Any
# other config MUST dispatch to scalar phi. The differential oracle is the gate.
class _PhiCtx:
    __slots__ = ("eff", "ev", "cap", "gb", "nref", "rate", "A", "haulcost",
                 "d", "fut", "lm2", "sc_loaded", "sc_empty")


def phi_ctx(r, other_sector, w) -> _PhiCtx:
    """Precompute the position/world-fixed inputs to fast_phi(r) for this
    encounter. `other_sector` is the partner's sector (r's post-swap sector is
    one of {r.sector, other_sector}), so future-trip constants are prepared for
    both. CORE CONFIG ONLY (caller gates)."""
    c = _PhiCtx()
    co = r.company
    eff = c.eff = r.eff
    c.ev = r.ev
    c.cap = r.cap
    c.gb = r.gauge_bias
    refs = w.refineries
    nref = c.nref = len(refs)
    lm1 = 1 + W.LOADED_MULT
    c.lm2 = 1 + W.LOADED_MULT / 2
    # step_cost() for the loaded/empty cases (r.step_cost() op-for-op)
    c.sc_loaded = eff * (1.0 + W.LOADED_MULT)
    c.sc_empty = eff * (1.0 + 0.0)
    # manhattan(p, q) is abs(p0-q0)+abs(p1-q1); inlined in these O(N) scans so
    # the per-encounter position work drops the millions of manhattan() calls
    # that dominate at scale — same integer ops, bit-identical.
    px, py = r.pos
    c.rate = [w.credit_rate(co, i) for i in range(nref)]
    c.A = [c.rate[i] * W.V_DELIVER for i in range(nref)]
    c.haulcost = [(abs(px - refs[i][0]) + abs(py - refs[i][1])) * eff * lm1
                  for i in range(nref)]
    _, c.d = w.nearest_charger(r)
    # best_claim's positive-stock argmax (sector-independent; first-max wins).
    # When it exists it equals best_claim(); when no rock has stock the scalar
    # best_claim returns r.sector, but that path yields future=0 anyway.
    stock = w.stock
    srcs = w.sources
    bc, bc_score = -1, -1.0
    for i in range(len(srcs)):
        s = stock[i]
        if s <= 0:
            continue
        sx, sy = srcs[i]
        sc = s / ((abs(px - sx) + abs(py - sy)) + 4.0)
        if sc > bc_score:
            bc_score, bc = sc, i
    denom_claim = max(1.0, len(w.robots) / 2)
    fut = {}
    for sigma in {r.sector, other_sector}:
        if stock[sigma] > 0:
            cand = sigma
        elif bc >= 0:
            cand = bc
        else:
            cand = sigma
        if stock[cand] <= 0:
            fut[sigma] = None
            continue
        sx, sy = srcs[cand]
        mh_src_ref = [abs(sx - refs[i][0]) + abs(sy - refs[i][1])
                      for i in range(nref)]
        haulsrc = [mh_src_ref[i] * eff * lm1 for i in range(nref)]
        approach = (abs(px - sx) + abs(py - sy)) * eff
        claim = stock[cand] / denom_claim
        fut[sigma] = (mh_src_ref, haulsrc, approach, claim)
    c.fut = fut
    return c


def fast_phi(load, battery, sector, stranded, c: _PhiCtx, hazard: bool,
             # physics constants bound once at def time (they never mutate) —
             # same values as the live W.* reads scalar phi uses, so bit-exact,
             # but no per-call module-attribute lookup in this hot function.
             _BMAX=W.BATTERY_MAX, _PSTRAND=W.P_STRAND, _VDEL=W.V_DELIVER,
             _FD=W.FUTURE_DISCOUNT, _HS=W.HAZARD_SCALE,
             _SPARE_OFF=0.15 * W.BATTERY_MAX, _exp=math.exp) -> float:
    """Byte-exact Φ from a precomputed context and the EXPLICIT post-state
    (load, battery, sector, stranded) — mirrors phi() op-for-op for the core
    config. Taking the post-state as arguments lets the caller derive it once
    per energy option (battery/stranded depend only on the energy leg) instead
    of mutating the robot per bundle."""
    if stranded:
        return -_PSTRAND
    bat = min(_BMAX, max(0.0, battery * (1.0 + c.gb)))
    ev = c.ev
    nref = c.nref
    A = c.A
    rate = c.rate
    maxload = max(load, 1)
    v = 0.0
    if load > 0:
        hc = c.haulcost
        best = 0
        bs = A[0] * maxload - hc[0] * ev
        for i in range(1, nref):
            sc = A[i] * maxload - hc[i] * ev
            if sc > bs:
                bs = sc
                best = i
        cost_to_ref = hc[best]
        full = load * rate[best] * _VDEL
        if bat > cost_to_ref:
            v += full
        else:
            v += 0.5 * full * bat / (cost_to_ref + 1e-9)
    fc = c.fut.get(sector)
    if fc is not None:
        mh_src_ref, haulsrc, approach, claim = fc
        best = 0
        bs = A[0] * maxload - haulsrc[0] * ev
        for i in range(1, nref):
            sc = A[i] * maxload - haulsrc[i] * ev
            if sc > bs:
                bs = sc
                best = i
        leg = mh_src_ref[best]
        cycle_cost = 2 * leg * c.eff * c.lm2
        spare = max(0.0, bat - approach - _SPARE_OFF)
        trips = spare / max(cycle_cost, 1e-9)
        v += _FD * min(trips * c.cap, claim) * rate[best] * _VDEL
    step_cost = c.sc_loaded if load > 0 else c.sc_empty
    if hazard:
        margin = bat - c.d * step_cost
        v -= _PSTRAND * (1.0 / (1.0 + _exp(margin / _HS)))
    elif bat < c.d * step_cost:
        v -= _PSTRAND
    return v

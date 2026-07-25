"""AMENDMENT 2 §A2.1 — landlord behaviour that EMERGES from primitives.

Phase 2's landlord types were hardcoded: MOM-AND-POP was *told* to rarely raise
and rarely concede, so the paradox it produced was an input. This module deletes
those rules. There is exactly one landlord class. Types differ only in
`Params.units`, and every behavioural difference is derived from it by
`world.size_primitives`:

    risk aversion    per-unit penalty ~ rho/(2 U 12) x Var[this year's cash]
    comp precision   observed comp = true market x exp(eps), sd ~ 1/sqrt(U)
    non-pecuniary    value of keeping a known tenant, and a fixed cost of
                     raising the rent at all, both ~ 1/(1 + U/10)
    turn cost        x (1 + beta/sqrt(U))
    face rent        capitalised x U/(U + u_cap)
    agent wedge      leasing agent's private bonus, weight U/(U + u_agent)

The hypothesised chain under test (NOT assumed): risk aversion + bad comps =>
small pushes => nothing to concede. Whether it holds is GATE 2's business, and
`primitive_ablation` in run3.py measures which primitive actually does the work.

Nothing here is reachable from the Phase 1 code path: every primitive defaults to
its Phase-1-neutral value, and `EmergentDP` is only constructed by run3.py.
"""
from __future__ import annotations

import numpy as np

from crabs.policies import QA, R_LO, R_STEP, RS, StationDP, _lin, _NRS
from crabs.world import Params, gauss_hermite, size_primitives


class EmergentDP(StationDP):
    """One landlord. Its behaviour is a consequence of its portfolio size.

    `weights_counter` is the switching-cost distribution the station believes it
    faces GIVEN that the crab countered (arms H and I). When it is None the
    station has no counter-specific belief, which is exactly Phase 1 and is why
    Phase 1 found countering worthless.
    """

    def __init__(self, p: Params, c_nodes, weights, weights_counter=None,
                 share: float = 0.0, adaptive: bool = False, **kw):
        self.prim = size_primitives(p)
        s = self.prim["comp_sigma"]
        if s > 0.0:
            x, wt = gauss_hermite(p.comp_nodes)
            self.eps = np.exp(s * x)          # e = M_true / M_observed
            self.epsw = wt
        else:
            self.eps = np.array([1.0])
            self.epsw = np.array([1.0])
        self._wc = weights_counter
        super().__init__(p, c_nodes, weights, share=share, adaptive=adaptive,
                         **kw)

    def _leave_table(self, p, c_nodes, weights):
        super()._leave_table(p, c_nodes, weights)
        self.ptab_uncond = self.ptab
        if self._wc is not None:
            keep = self.ptab
            super()._leave_table(p, c_nodes, self._wc)
            self.ptab_counter, self.ptab = self.ptab, keep
        else:
            self.ptab_counter = self.ptab

    # ---------------------------------------------------------------- values
    def _turn_val(self, V, j=1, tmul=None, vmul=1.0, e=1.0):
        """Value of losing this crab. `e` is the true market as a multiple of the
        station's own comp, so a station with bad comps does not know what a relet
        would actually fetch."""
        p = self.p
        fp = p.face_premium * self.prim["face_mult"]
        if tmul is None:
            tmul = self._tmul0[min(j, p.j_max + 1)]
        T = p.turn_cost * self.prim["turn_scale"] * tmul
        vac = min(p.vacancy * vmul, 11.0)
        nxt = self._Vg(V, 1.0 / (1.0 + self.g), 1)
        cash = -T + (12.0 - vac) * e
        return cash + fp * (12.0 - vac) * e - p.q_new + \
            p.disc_station * (1.0 + self.gv) * nxt, cash

    def _variant_val(self, V, j, q, r, variant, tmul=None, vmul=1.0,
                     counterer: bool = False):
        """Risk-adjusted NPV, integrated over the station's comp uncertainty.

        Returns the same scalar/array shape as StationDP._variant_val, so the DP
        sweep and the runtime concession decision share this one code path."""
        p = self.p
        fp = p.face_premium * self.prim["face_mult"]
        d1 = p.disc_station * (1.0 + self.gv)
        j2 = min(j + 1, p.j_max)
        qs = self._qsit[min(j, p.j_max + 1)]
        aj = self._attach[min(j, p.j_max + 1)]
        kc, lr = p.kappa_crab, p.lambda_ref
        ptab = self.ptab_counter if counterer else self.ptab_uncond
        nonpec, raise_cost = self.prim["nonpec"], self.prim["raise_cost"]

        q_eff, z_crab, z_cash, locked = self.package_effects(p, q, variant, self.g)
        # station-side cash cost of the package this year, in months of its comp
        if variant is None:
            cash_out = 0.0
        elif variant[0] == 1:                                   # FEES, two years
            cash_out = z_cash * (1.0 + p.disc_station)
        else:
            cash_out = z_cash

        # the rent of record the station books, and its continuation state
        face = q_eff if locked == 0 else q_eff
        stay_cash = 12.0 * face - cash_out
        stay_core = (stay_cash + fp * 12.0 * face - qs + nonpec
                     + d1 * self._Vg(V, face / (1.0 + self.g), j2))
        if locked:
            # a term lock is two frozen years; value the second explicitly
            j3 = min(j + 2, p.j_max)
            stay_core = (stay_cash + fp * 12.0 * face - qs + nonpec
                         + p.disc_station * (12.0 * face * (1.0 + fp) + nonpec
                                             + p.disc_station
                                             * (1.0 + self.gv) ** 2
                                             * self._Vg(V, face /
                                                        (1.0 + self.g) ** 2, j3)))

        ev = 0.0
        e_cash = 0.0
        e_cash2 = 0.0
        for e, wt in zip(self.eps, self.epsw):
            turn_core, turn_cash = self._turn_val(V, j, tmul, vmul, e)
            # the crab responds to TRUE ratios; the station only knows its comp
            gain = (12.0 * kc * (q_eff / e - 1.0)
                    + lr * 12.0 * (q_eff - r) / e - aj - z_crab / e)
            pl = _lin(gain, ptab[min(int(j), p.j_max)], -40.0, 0.01,
                      ptab.shape[1])
            ev = ev + wt * ((1.0 - pl) * stay_core + pl * turn_core)
            c1 = (1.0 - pl) * stay_cash + pl * turn_cash
            c2 = (1.0 - pl) * stay_cash ** 2 + pl * turn_cash ** 2
            e_cash = e_cash + wt * c1
            e_cash2 = e_cash2 + wt * c2

        var = np.maximum(e_cash2 - e_cash ** 2, 0.0)
        ev = ev - self.prim["risk_scale"] * var
        # a fixed cost of raising the rent at all -- this is what puts a mass
        # point at "no increase", and it is a primitive, not a rule
        if raise_cost > 0.0:
            raised = (q_eff > r * (1.0 + 1e-9)) if type(q_eff) is float \
                else (np.asarray(q_eff) > np.asarray(r) * (1.0 + 1e-9))
            ev = ev - raise_cost * raised
        return ev

    def npv(self, q, r, j, variant, tmul=None, vmul=1.0,
            counterer: bool = False) -> float:
        return float(self._variant_val(self.V, j, q, r, variant, tmul, vmul,
                                       counterer))

    # ------------------------------------------------------- agent wedge (J)
    def decision_value(self, q, r, j, variant, tmul=None, vmul=1.0,
                       counterer: bool = False) -> float:
        """What the person actually deciding maximises. For a large portfolio that
        is a leasing agent paid on retention, not the owner's NPV. The weight is
        U/(U+u_agent), so the wedge appears in large portfolios without anyone
        being told that it should."""
        v = self.npv(q, r, j, variant, tmul, vmul, counterer)
        aw = self.prim["agent_w"]
        if aw <= 0.0:
            return v
        q_eff, z_crab, _, _ = self.package_effects(self.p, q, variant, self.g)
        aj = self._attach[min(j, self.p.j_max + 1)]
        gain = (12.0 * self.p.kappa_crab * (q_eff - 1.0)
                + self.p.lambda_ref * 12.0 * (q_eff - r) - aj - z_crab)
        ptab = self.ptab_counter if counterer else self.ptab_uncond
        pl = float(_lin(float(gain), ptab[min(int(j), self.p.j_max)], -40.0, 0.01,
                        ptab.shape[1]))
        return v + aw * self.p.agent_bonus * (1.0 - pl)

    # --------------------------------------------------------- negotiation
    def negotiate(self, p: Params, crab, q, r, j, u, g_obs, asker_strategy,
                  tmul=None, vmul=1.0):
        """Same protocol as Phase 1, with two changes that are arms, not tweaks:
        the station may hold a counter-specific belief (arms H/I), and the
        decision may be the agent's rather than the owner's (arm J)."""
        from crabs.policies import PRICE_LADDER, crab_ladder
        from crabs.world import ASK_PRICE, FEES, NEVER_ASK, U_PATIENCE, U_SUB
        if crab.strategy == NEVER_ASK or p.no_concessions:
            return None, 0, False, None
        ladder = (PRICE_LADDER if crab.strategy == ASK_PRICE
                  else crab_ladder(crab))
        scale = getattr(crab, "ask_scale", 1.0)
        base = self.decision_value(q, r, j, None, tmul, vmul, counterer=True)
        rounds, asked = 0, False
        for kind, size in ladder:
            if kind == FEES and crab.fee_years > 0:
                continue
            size = size * scale
            if size <= 0.0 or self.crab_value(p, q, (kind, size), g_obs) <= 0.0:
                continue
            if rounds >= 1 and u[U_PATIENCE + min(rounds - 1, 3)] > p.p_continue:
                break
            rounds += 1
            asked = True
            grant = None
            for f in p.grant_menu:
                var = (kind, size * f)
                if self.crab_value(p, q, var, g_obs) <= 0.0:
                    continue
                if self.decision_value(q, r, j, var, tmul, vmul,
                                       counterer=True) >= base:
                    grant = var
                    break
            if grant is not None:
                return grant, rounds, True, kind
            if u[U_SUB + min(rounds - 1, 3)] < p.p_substitute:
                alt = self._substitute_em(p, q, r, j, base, kind, g_obs, tmul,
                                          vmul)
                if alt is not None:
                    return alt, rounds, True, alt[0]
        return None, rounds, asked, None

    def _substitute_em(self, p, q, r, j, base, exclude, g_obs, tmul, vmul):
        best, best_v = None, base
        for kind in (0, 1, 2, 3):
            if kind == exclude:
                continue
            for f in p.grant_menu:
                var = (kind, f)
                if self.crab_value(p, q, var, g_obs) <= 0.0:
                    continue
                v = self.decision_value(q, r, j, var, tmul, vmul, counterer=True)
                if v > best_v:
                    best, best_v = var, v
        return best

    # --------------------------------------------------- arm G: blanket policy
    def blanket_push(self, states) -> float:
        """Arm G. No property manager optimises every unit: it picks ONE increase
        for the whole portfolio. Chosen here by evaluating a small grid against
        the portfolio the station actually holds -- an honest blanket policy, not
        a strawman, but not the per-unit optimum either."""
        if not states:
            return 0.0
        best_x, best_v = 0.0, -1e18
        for x in self.p.blanket_grid:
            tot = 0.0
            for r, jj in states:
                tot += self.npv(r * (1.0 + x), r, jj, None)
            if tot > best_v:
                best_x, best_v = x, tot
        return best_x

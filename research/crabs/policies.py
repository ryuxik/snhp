"""Station policy and crab strategies.

The station is a dynamic program, not a strawman. It maximises expected NPV
over (rent-of-record ratio, tenure), with a correctly specified model of the
crab's departure probability -- the same functional form the crabs actually
use, integrated over the switching-cost distribution it knows but cannot
observe per crab. It pays a turn cost plus vacancy, prices relets at market,
values a proven payer above an unknown applicant, and (SPEC §6) values face
rent above its cash value.

    E[push] = dRent x P(stay) - (TurnCost + VacancyLoss) x dP(leave)

is the marginal statement of the same thing; the DP is its exact solution
including the continuation value the marginal form leaves implicit.

Two station variants:
    StationDP(share=0)             -- ignores countering when setting the
                                      opening offer (arms A-D)
    StationDP(share=s, adaptive)   -- knows the asker share s and pre-inflates
                                      the opening offer by the concession it
                                      expects to have to give back (arm E)
"""
from __future__ import annotations

import numpy as np

from crabs.world import (ASK_PRICE, ASK_RANKED, FEES, NEVER_ASK, ONE_TIME,
                         RENT, TERM, U_PATIENCE, U_SUB, Params, attach,
                         gain_base, p_exo, q_sit, sigmoid)

# ---- grids -------------------------------------------------------------------
R_LO, R_HI, R_STEP = 0.40, 2.00, 0.02      # state grid: rent-of-record ratio
A_STEP = 0.01                               # action grid: offer ratio
G_LO, G_HI, G_STEP = -40.0, 40.0, 0.01      # gain-base grid for the leave table

RS = np.round(np.arange(R_LO, R_HI + 1e-9, R_STEP), 6)
QA = np.round(np.arange(R_LO, R_HI + 1e-9, A_STEP), 6)
GG = np.round(np.arange(G_LO, G_HI + 1e-9, G_STEP), 6)
_NRS, _NGG = RS.size, GG.size


def _lin(x, ytab, lo, step, n):
    """Linear interpolation on a UNIFORM grid, with a pure-Python fast path for
    scalars. The DP sweeps pass arrays; the runtime concession decision passes
    scalars millions of times, and np.interp's per-call overhead dominated the
    run. One helper, so both paths use identical arithmetic."""
    if type(x) is float:
        t = (x - lo) / step
        if t <= 0.0:
            return ytab[0]
        if t >= n - 1:
            return ytab[n - 1]
        i = int(t)
        f = t - i
        return ytab[i] * (1.0 - f) + ytab[i + 1] * f
    t = np.clip((np.asarray(x) - lo) / step, 0.0, n - 1)
    i = np.minimum(t.astype(np.intp), n - 2)
    f = t - i
    return ytab[i] * (1.0 - f) + ytab[i + 1] * f

# crab ask ladders (PREREG §4; order NOT reordered by our own cost model)
PRICE_LADDER = ((RENT, 1.0), (RENT, 0.6), (RENT, 0.35))
RANKED_LADDER = ((ONE_TIME, 1.0), (FEES, 1.0), (TERM, 1.0), (RENT, 1.0))

def crab_ladder(crab):
    """PREREG §4's ranked ladder, with arm F's learned instrument preference
    moved to the front if the grapevine has taught the crab one."""
    pref = getattr(crab, "pref_kind", -1)
    if pref is None or pref < 0:
        return RANKED_LADDER
    rest = [x for x in RANKED_LADDER if x[0] != pref]
    return tuple([(pref, 1.0)] + rest)


# variants the adaptive station considers when anticipating the counter stage
DP_VARIANTS = (None,
               (ONE_TIME, 1.0), (ONE_TIME, 0.6), (ONE_TIME, 0.3),
               (FEES, 1.0), (FEES, 0.6),
               (TERM, 1.0), (TERM, 0.6),
               (RENT, 1.0), (RENT, 0.6), (RENT, 0.3))


class StationDP:
    def __init__(self, p: Params, c_nodes: np.ndarray, weights: np.ndarray,
                 share: float = 0.0, adaptive: bool = False,
                 n_iter: int = 240, n_iter_adaptive: int = 80,
                 solve: bool = True):
        self.p = p
        self.g = p.drift                       # near-term market growth
        # Terminal/value scaling growth. Converting a continuation value from
        # units of M' into units of M multiplies by (1+g); with delta*(1+g) >= 1
        # the value iteration diverges (a perpetual +9% at 7% discounting makes a
        # habitat worth infinity). Underwriting practice -- near-term market
        # growth, long-run terminal growth -- is also what makes it converge.
        self.gv = min(p.drift, p.g_long)
        assert p.disc_station * (1.0 + self.gv) < 1.0, "DP would diverge"
        self.share = float(share)
        self.adaptive = bool(adaptive and share > 0.0)
        self.c_nodes = c_nodes
        self.weights = weights          # (j_max+1, n_nodes), row j
        self._attach = [float(attach(p, max(j, 1))) for j in range(p.j_max + 2)]
        self._qsit = [float(q_sit(p, max(j, 1))) for j in range(p.j_max + 2)]
        self._tmul0 = [1.0 + p.turn_tenure_slope * float(np.log(1.0 + max(j, 1)))
                       for j in range(p.j_max + 2)]
        self._leave_table(p, c_nodes, weights)
        if solve:
            self._solve(n_iter, n_iter_adaptive)
        else:                       # heuristic landlords keep the instrument
            jm = p.j_max            # machinery and the leave model, no DP
            self.V = np.zeros((jm + 2, RS.size))
            self.pol = np.zeros((jm + 2, RS.size))

    # -------------------------------------------------- departure probability
    def _leave_table(self, p, c_nodes, weights):
        """P(leave | gain_base = g, tenure j), integrated over the switching-cost
        distribution the station knows. Tabulated on GG so every later lookup is
        an interpolation -- identical function for the DP and for runtime."""
        jm = p.j_max
        tab = np.zeros((jm + 2, GG.size))
        for j in range(1, jm + 1):
            w = weights[j]
            s = np.zeros(GG.size)
            for n in range(c_nodes.size):
                s += w[n] * sigmoid((GG - c_nodes[n]) / p.nu)
            pe = float(p_exo(p, j))
            tab[j] = pe + (1.0 - pe) * s
        tab[jm + 1] = tab[jm]
        self.ptab = tab

    def leave_prob(self, gain, j):
        return _lin(gain, self.ptab[min(int(j), self.p.j_max)], G_LO, G_STEP,
                    _NGG)

    def _Vg(self, V, x, j):
        return _lin(x, V[j], R_LO, R_STEP, _NRS)

    # ---------------------------------------------------------------- solving
    def _solve(self, n_iter, n_iter_adaptive):
        p, g = self.p, self.g
        jm = p.j_max
        # action mask: renewal increase cap and the largest decrease it offers
        lo = RS[:, None] * (1.0 - p.renewal_floor)
        hi = RS[:, None] * (1.0 + p.renewal_cap)
        self.mask = (QA[None, :] >= lo - 1e-12) & (QA[None, :] <= hi + 1e-12)
        V = np.zeros((jm + 2, RS.size))
        for _ in range(n_iter):
            V = self._sweep(V, adaptive=False)
        self.V = V
        if self.adaptive:
            for _ in range(n_iter_adaptive):
                V = self._sweep(V, adaptive=True)
            self.V = V
        # final policy
        self.pol = self._sweep(self.V, adaptive=self.adaptive, want_policy=True)

    def _sweep(self, V, adaptive, want_policy=False):
        p, g = self.p, self.g
        jm = p.j_max
        out = np.zeros_like(V) if not want_policy else np.zeros((jm + 2, RS.size))
        for j in range(1, jm + 1):
            base = self._variant_val(V, j, QA[None, :], RS[:, None], None)
            if adaptive:
                # It may only anticipate concessions the crab would actually
                # accept. Without this filter it plans on granting a term lock in
                # a falling market -- which no crab would take -- and mis-sets
                # the opening offer.
                cs = base.copy()
                for var in DP_VARIANTS[1:]:
                    cv = self.crab_value(self.p, QA[None, :], var, self.g)
                    v = self._variant_val(V, j, QA[None, :], RS[:, None], var)
                    cs = np.maximum(cs, np.where(cv > 0.0, v, -1e18))
                val = self.share * cs + (1.0 - self.share) * base
            else:
                val = base
            val = np.where(self.mask, val, -1e18)
            if want_policy:
                out[j] = QA[val.argmax(axis=1)]
            else:
                out[j] = val.max(axis=1)
        if not want_policy:
            out[jm + 1] = out[jm]
        else:
            out[jm + 1] = out[jm]
        return out

    # ------------------------------------------------- value of one package
    def _turn_val(self, V, j=1, tmul=None, vmul=1.0):
        """Value of letting this crab go. The make-ready cost carries a tenure
        slope -- an eight-year habitat needs paint, carpet and appliances where a
        one-year habitat needs a touch-up -- and, at the concession stage, this
        habitat's own idiosyncratic exposure, which the manager can see."""
        p, g = self.p, self.g
        fp = p.face_premium
        if tmul is None:
            tmul = self._tmul0[min(j, p.j_max + 1)]
        T = p.turn_cost * tmul
        vac = p.vacancy * vmul
        if vac > 11.0:
            vac = 11.0
        nxt = self._Vg(V, 1.0 / (1.0 + g), 1)
        return (-T + (12.0 - vac) * (1.0 + fp) - p.q_new
                + p.disc_station * (1.0 + self.gv) * nxt)

    def _variant_val(self, V, j, q, r, variant, tmul=None, vmul=1.0):
        """Station NPV (months of market rent) of offering `q` to a crab at `r`,
        tenure `j`, and settling on `variant`. Works elementwise, so the same
        code serves the DP sweep and the runtime concession decision."""
        p, g = self.p, self.g
        fp, d = p.face_premium, p.disc_station
        d1 = d * (1.0 + self.gv)
        j2 = min(j + 1, p.j_max)
        turn = self._turn_val(V, j, tmul, vmul)
        qs = self._qsit[min(j, p.j_max + 1)]
        aj = self._attach[min(j, p.j_max + 1)]
        kc, lr = p.kappa_crab, p.lambda_ref

        if variant is None:
            stay = (12.0 * q * (1.0 + fp) - qs
                    + d1 * self._Vg(V, q / (1.0 + g), j2))
            gain = 12.0 * kc * (q - 1.0) + lr * 12.0 * (q - r) - aj
            pl = self.leave_prob(gain, j)
            return (1.0 - pl) * stay + pl * turn

        kind, size = variant
        if kind == ONE_TIME:
            z = size * p.ask_frac * 12.0 * q
            cash = 12.0 * q - z
            stay = cash + fp * 12.0 * q - qs + d1 * self._Vg(
                V, q / (1.0 + g), j2)
            gain = 12.0 * kc * (q - 1.0) + lr * 12.0 * (q - r) - aj - z
        elif kind == FEES:
            z1 = np.minimum(size * p.ask_frac * 12.0 * q,
                            p.fee_cap_frac * 12.0 * q)
            z = z1 * (1.0 + p.disc_crab)
            cash = 12.0 * q - z1 * (1.0 + d)      # SPEC §11: charged up front
            stay = cash + fp * 12.0 * q - qs + d1 * self._Vg(
                V, q / (1.0 + g), j2)
            gain = 12.0 * kc * (q - 1.0) + lr * 12.0 * (q - r) - aj - z
        elif kind == RENT:
            x = size * p.ask_frac
            qf = q * (1.0 - x)
            stay = 12.0 * qf + fp * 12.0 * qf - qs + d1 * self._Vg(
                V, qf / (1.0 + g), j2)
            gain = 12.0 * kc * (qf - 1.0) + lr * 12.0 * (qf - r) - aj
        elif kind == TERM:
            dd = min(size * p.ask_frac / (1.0 + p.disc_crab), p.term_cap)
            rb = q * (1.0 - dd)
            j3 = min(j + 2, p.j_max)
            p2 = float(p_exo(p, min(j + 1, p.j_max))) * p.break_damp
            yr2_stay = (12.0 * rb * (1.0 + fp)
                        + d * (1.0 + self.gv) ** 2 * self._Vg(
                            V, rb / (1.0 + g) ** 2, j3))
            _tm = (tmul if tmul is not None
                   else 1.0 + p.turn_tenure_slope * float(np.log(2.0 + j)))
            yr2_break = (p.break_fee * rb
                         + (12.0 - min(p.vacancy * vmul, 11.0)) * (1.0 + g)
                         * (1.0 + fp)
                         - p.turn_cost * _tm - p.q_new
                         + d * (1.0 + self.gv) ** 2 * self._Vg(
                             V, 1.0 / (1.0 + g), 1))
            stay = (12.0 * rb * (1.0 + fp) - qs
                    + d * ((1.0 - p2) * yr2_stay + p2 * yr2_break))
            z = self._term_crab_value(p, q, rb, j, g)
            gain = 12.0 * kc * (rb - 1.0) + lr * 12.0 * (rb - r) - aj - z
        else:                                             # pragma: no cover
            raise ValueError(kind)

        pl = self.leave_prob(gain, j)
        return (1.0 - pl) * stay + pl * turn

    @staticmethod
    def _term_crab_value(p: Params, q, rb, j, g_fore):
        """What the crab thinks the SECOND year of a lock is worth: rent frozen
        at rb while it forecasts market rent at (1+g_fore), minus the
        illiquidity of not being able to leave without a break fee."""
        dc = p.disc_crab
        return (dc * 12.0 * ((1.0 + g_fore) - rb)
                - dc * float(p_exo(p, min(j + 1, p.j_max))) * p.break_fee * rb)

    # -------------------------------------------------------------- interface
    def offer(self, r, j) -> float:
        return float(_lin(float(r), self.pol[min(int(j), self.p.j_max)],
                          R_LO, R_STEP, _NRS))

    def npv(self, q, r, j, variant, tmul=None, vmul=1.0) -> float:
        return float(self._variant_val(self.V, j, q, r, variant, tmul, vmul))

    def package_effects(self, p: Params, q, pkg, g_obs_crab=0.0):
        """(effective rent ratio the crab pays this year, non-rent value to the
        crab in months of market rent, station cash cost this year, locked years)"""
        if pkg is None:
            return q, 0.0, 0.0, 0
        kind, size = pkg
        if kind == ONE_TIME:
            z = size * p.ask_frac * 12.0 * q
            return q, z, z, 0
        if kind == FEES:
            z1 = np.minimum(size * p.ask_frac * 12.0 * q,
                            p.fee_cap_frac * 12.0 * q)
            return q, z1 * (1.0 + p.disc_crab), z1, 0
        if kind == RENT:
            return q * (1.0 - size * p.ask_frac), 0.0, 0.0, 0
        if kind == TERM:
            dd = min(size * p.ask_frac / (1.0 + p.disc_crab), p.term_cap)
            rb = q * (1.0 - dd)
            return rb, self._term_crab_value(p, q, rb, 1, g_obs_crab), 0.0, 1
        raise ValueError(kind)

    def crab_value(self, p: Params, q, pkg, g_obs_crab=0.0) -> float:
        """Total value of the package to the crab, months of market rent."""
        q_eff, z, _, _ = self.package_effects(p, q, pkg, g_obs_crab)
        return 12.0 * (q - q_eff) + z

    def apply_package(self, p: Params, crab, q, pkg, M, g_obs):
        q_eff, _, _, locked = self.package_effects(p, q, pkg, g_obs)
        crab.rent = q_eff * M
        if pkg is not None and pkg[0] == FEES:
            z1 = min(pkg[1] * p.ask_frac * 12.0 * q, p.fee_cap_frac * 12.0 * q)
            crab.fee_years = 2
            crab.fee_value = z1 * M
        if locked:
            crab.locked = locked

    # ------------------------------------------------------------ negotiation
    def negotiate(self, p: Params, crab, q, r, j, u, g_obs, asker_strategy,
                  tmul=None, vmul=1.0):
        """Returns (package, rounds, asked, granted_kind).

        A grant ends the negotiation. Between rounds the station's patience is
        finite (p_continue), so RANKED does not automatically nest PRICE.
        Crabs skip rungs with non-positive value to themselves -- which is why
        TERM is a good rung in the loss regime and a bad one in the gain
        regime, without either being hard-coded."""
        if crab.strategy == NEVER_ASK:
            return None, 0, False, None
        ladder = (PRICE_LADDER if crab.strategy == ASK_PRICE
                  else crab_ladder(crab))
        base = self.npv(q, r, j, None, tmul, vmul)
        scale = getattr(crab, "ask_scale", 1.0)
        rounds, asked = 0, False
        won = []
        for kind, size in ladder:
            if kind == FEES and crab.fee_years > 0:
                continue
            size = size * scale
            if size <= 0.0 or self.crab_value(p, q, (kind, size), g_obs) <= 0.0:
                continue
            if rounds >= 1:
                if u[U_PATIENCE + min(rounds - 1, 3)] > p.p_continue:
                    break
            rounds += 1
            asked = True
            grant = None
            for f in p.grant_menu:
                var = (kind, size * f)
                if self.crab_value(p, q, var, g_obs) <= 0.0:
                    continue
                if self.npv(q, r, j, var, tmul, vmul) >= base:
                    grant = var
                    break
            if grant is not None:
                if not p.ladder_continues:
                    return grant, rounds, True, kind
                won.append(grant)
                continue
            if u[U_SUB + min(rounds - 1, 3)] < p.p_substitute:
                alt = self._substitute(p, q, r, j, base, kind, g_obs, tmul, vmul)
                if alt is not None:
                    if not p.ladder_continues:
                        return alt, rounds, True, alt[0]
                    won.append(alt)
        if won:
            from crabs.engine_bridge import ladder_to_bundle
            b = ladder_to_bundle(p, q, won)
            return b, rounds, True, won[0][0]
        return None, rounds, asked, None

    def _substitute(self, p, q, r, j, base, exclude, g_obs, tmul=None, vmul=1.0):
        """"Not rent, but I can do four weeks." The station volunteers the
        instrument that maximises its own NPV, if any beats refusing."""
        best, best_v = None, base
        for kind in (ONE_TIME, FEES, TERM, RENT):
            if kind == exclude:
                continue
            for f in p.grant_menu:
                var = (kind, f)
                if self.crab_value(p, q, var, g_obs) <= 0.0:
                    continue
                v = self.npv(q, r, j, var, tmul, vmul)
                if v > best_v:
                    best, best_v = var, v
        return best

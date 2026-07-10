"""The HONEST baseline: humans negotiating BADLY (task #69).

The pre-SNHP world is NOT "no negotiation." On the vendor / supply side there is
no sticker — procurement is ALL negotiation, conducted by humans using the
hardball-tactics canon. wholesale/'s existing `ratecard` arm is already ONE toxic
tactic (a Boulware take-it-or-leave-it: the distributor posts a card, the venue
takes it or defects to Jetro). This module builds the RICHER battery — the human
negotiator TYPES and tactics — and proves SNHP beats how humans ACTUALLY
negotiate, not a passive-posting strawman.

────────────────────────────────────────────────────────────────────────────
THE TAXONOMY (grounded in the negotiation literature; cited inline)
────────────────────────────────────────────────────────────────────────────
A negotiator TYPE is a point in tactic-space. The tactics are the axes; the
named personalities are characteristic bundles of them.

TACTICS (the axes of `NegotiatorType`):
  * extreme ANCHORING          `anchor` — a biased, self-favoring first offer.
      Tversky & Kahneman (1974) "Judgment under Uncertainty" — the anchoring
      heuristic; Galinsky & Mussweiler (2001) show first offers pull the
      settlement. A hardballer opens at ~0.9 of the pie.
  * BOULWARE / take-it-or-leave-it   `concede≈0`, short `deadline` —
      one firm demand, no movement (named for GE's Lemuel Boulware; see
      Fisher & Ury, "Getting to Yes", on positional deadlock). The existing
      rate-card baseline IS a Boulware offer.
  * BLUFFING / misrepresenting BATNA `claim_floor`>0, `honest=False` — claiming
      a stronger outside option / reservation than is real, to shift the
      perceived zone of agreement. Malhotra & Bazerman, "Negotiation Genius",
      ch. on lies and deception; the BATNA concept is Fisher & Ury.
  * NIBBLING                    `nibble`>0 — extracting extras AFTER the close
      ("and throw in net-30"). Malhotra & Bazerman; a classic hardball move.
  * FALSE DEADLINE              short `deadline` used as pressure — Malhotra &
      Bazerman on manufactured urgency (the AVOIDER/BOULWARE short horizons).
  * POSITIONAL bargaining       `positional=True` — fights over PRICE only and
      freezes window / case-size / terms / spoilage at rate-card defaults, so it
      misses the multi-issue logroll. Fisher & Ury's central diagnosis:
      positional bargaining fails to create value. Thompson, "The Mind and Heart
      of the Negotiator", on the fixed-pie bias.
  * EXPLOITING INFO ASYMMETRY   `exploits=True` — the sophisticated party reads a
      naive counterpart and squeezes to the counterpart's reservation. Akerlof
      (1970) information asymmetry; Malhotra & Bazerman on claiming value.

PERSONALITIES (named archetypes; each a bundle of the above):
  * HARDBALLER    aggressive / extractive: extreme anchor, near-zero concession,
                  exploits the naive (Malhotra & Bazerman; the distributive
                  "value-claimer").
  * ACCOMMODATOR  the NAIVE over-conceder: low anchor, fast concession, believes
                  claims, never walks — gets fleeced (Thompson's "accommodating"
                  / soft-bargaining style).
  * BLUFFER       misrepresents BATNA to manufacture leverage.
  * AVOIDER       conflict-averse: walks from POSITIVE-surplus deals rather than
                  haggle → impasse (Thompson's "avoiding" style; the
                  Myerson-Satterthwaite deadweight made flesh).
  * BOULWARE      take-it-or-leave-it (the rate card as a person).
  * POSITIONAL    the price-only fighter (misses the logroll).
  * NIBBLER       closes, then extracts extras (damages the relationship).
  * FAIR          the "good human": Fisher & Ury PRINCIPLED negotiation — opens
                  all issues, honest BATNA, aims for a fair split. The honest
                  point of this baseline is that even FAIR humans lack the
                  neutral broker's GUARANTEE: FAIR-vs-HARDBALLER still gets
                  squeezed, and FAIR-vs-BOULWARE still impasses.

SNHP is not a personality — it is the NEUTRAL BROKER. It computes the Nash
bargaining solution (Nash 1950) over the FULL bundle against the event-consistent
disagreement: the EFFICIENT bundle (max joint surplus — the full logroll) split
by equal bargaining power, i.e. each side gets its disagreement value plus half
the created pie. Personality is irrelevant to the broker: the hardballer cannot
out-anchor it and the accommodator cannot be fleeced under it.

────────────────────────────────────────────────────────────────────────────
THE MODEL (a deterministic concession game — no LLM, byte-seeded)
────────────────────────────────────────────────────────────────────────────
The negotiation is decomposed into the two dimensions the literature separates:

  (1) PIE SIZE (value creation / integrative). Which issues are on the table.
      If EITHER party is POSITIONAL, only price moves and the rest freeze at the
      rate-card defaults → the pie is `pie_pos` (the price-only max joint).
      Otherwise the full logroll is available → `pie_full` (the max joint over
      the whole bundle). It takes TWO to logroll; one price-fixated party
      collapses the deal to price-only. SNHP always opens all issues → pie_full.

  (2) THE SPLIT (value claiming / distributive). An alternating-offers concession
      game (Rubinstein 1982, reduced to share-space). Each party i demands a
      share σ_i(t) of the pie, opening at its `anchor` and conceding toward its
      `claim_floor` (a bluff inflates this floor):
          σ_i(t) = φ_i + (α_i − φ_i)·(1 − β_i)^t
      A deal CLOSES at the first round t ≤ min(deadline_v, deadline_w) with
      σ_v(t) + σ_w(t) ≤ 1; the leftover slack is split evenly (meet in the
      middle). If demands never become compatible before the earliest walk →
      IMPASSE: the positive-surplus deal is DESTROYED (both revert to their
      disagreement event). This is the Myerson & Satterthwaite (1983)
      no-trade-theorem deadweight, produced endogenously by the tactics.

Reduced-form choices, stated honestly:
  * The split is over the MONEY transfer (price/terms) holding the efficient
    bundle fixed, so shares map linearly to dollar gains — price is a near-
    continuous transfer within a bundle (6 discount rungs); we do not re-quantize
    the split to rungs. SNHP is scored on the same continuous-transfer
    idealization of the SAME Nash mechanism (the discrete `nash_deal` engine
    reproduces it within rung granularity — asserted in tests).
  * A type's POSTURE (shares) is pie-independent; only the dollar pie varies with
    the demand seed, which is what the CIs are over. This makes each tactic's
    behavior exactly reproducible (the "behaves as specified" tests) while the
    dollar outcomes remain paired on the demand identity, never on policy.

────────────────────────────────────────────────────────────────────────────
CONNECTION TO VON NEUMANN (the minimax / no-regret backbone)
────────────────────────────────────────────────────────────────────────────
The toxic tactics ARE the misreport strategies SNHP neutralizes — a RICHER liar
battery than the buyer side's single WTP-understatement (paper §10). Anchoring,
Boulware, positional and info-asymmetry exploitation are report-INDEPENDENT
posture: the supplier's true reservation is its per-case COGS, pinned by finite
stock (paper §10's finite-stock shadow pricing), so no amount of aggressive
posture moves the floor the neutral broker prices against — the broker computes
the fair split from the pinned reservations regardless of personality. The BLUFF
(misrepresented BATNA) is the exception: it is a report that CAN move a naive
counterpart's belief. It SURVIVES only where the claim cannot be verified. On the
wholesale interface the forecast is attested at settlement (RESULTS-SUPPLY S1),
so a demand bluff is neutralized; a bluff about a TRULY-private outside option
that no attestation can reach is where a residual survives — the attestation-
required regime (paper §10's conclusion that the private-value term needs
attestation, one tier up).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from wholesale import calibration as cal
from wholesale.scenario import (Deal, Disagreement, RelCtx, disagreement,
                                nash_deal)
from wholesale.world import Schedule, WeekDemand

NEGO_VERSION = 1


# ── the negotiator type: a point in tactic-space ────────────────────────────

@dataclass(frozen=True)
class NegotiatorType:
    """One human negotiator TYPE. The fields ARE the hardball tactics; the named
    archetypes below are characteristic bundles of them. Share-space parameters
    (a share ∈ [0,1] is the party's demanded slice of the pie above the
    disagreement point)."""
    name: str
    anchor: float          # α: opening demanded share (extreme anchoring)
    concede: float         # β: fractional concession per round toward the floor
    claim_floor: float     # φ: the share it CLAIMS it needs (BATNA bluff if >0)
    deadline: int          # rounds it will engage before walking (false deadline)
    positional: bool = False   # fights price-only → collapses the logroll
    nibble: float = 0.0        # extra share grabbed AFTER the close
    exploits: bool = False     # reads a naive counterpart and squeezes it
    honest: bool = True        # False ⇒ the claim_floor is a misrepresentation
    is_snhp: bool = False       # the neutral broker sentinel (handled apart)


# ── the roster (literature-grounded archetypes) ─────────────────────────────
# Calibrated so each failure mode emerges as specified (verified in tests):
# hardball×hardball impasses on big pies; hardball fleeces the accommodator;
# positional shrinks the pie; the nibbler damages the relationship.

FAIR = NegotiatorType(          # Fisher & Ury: principled negotiation
    "fair", anchor=0.55, concede=0.35, claim_floor=0.45, deadline=30)
HARDBALLER = NegotiatorType(    # Malhotra & Bazerman: the value-claimer
    "hardballer", anchor=0.90, concede=0.05, claim_floor=0.12, deadline=12,
    exploits=True)
BOULWARE = NegotiatorType(      # take-it-or-leave-it (the rate card as a person)
    "boulware", anchor=0.75, concede=0.0, claim_floor=0.75, deadline=2)
ACCOMMODATOR = NegotiatorType(  # Thompson: the naive over-conceder
    "accommodator", anchor=0.55, concede=0.60, claim_floor=0.0, deadline=30)
BLUFFER = NegotiatorType(       # misrepresented BATNA
    "bluffer", anchor=0.72, concede=0.15, claim_floor=0.42, deadline=15,
    honest=False)
AVOIDER = NegotiatorType(       # Thompson: conflict-averse, walks from + deals
    "avoider", anchor=0.50, concede=0.40, claim_floor=0.0, deadline=0)
POSITIONAL = NegotiatorType(    # Fisher & Ury: price-only, misses the logroll
    "positional", anchor=0.62, concede=0.20, claim_floor=0.05, deadline=20,
    positional=True)
NIBBLER = NegotiatorType(       # Malhotra & Bazerman: post-close extraction
    "nibbler", anchor=0.60, concede=0.25, claim_floor=0.0, deadline=20,
    nibble=0.08)

SNHP = NegotiatorType(          # the neutral broker (not a personality)
    "snhp", anchor=0.5, concede=1.0, claim_floor=0.0, deadline=99, is_snhp=True)

# the human type POPULATION (uniform, for the per-type marginals)
HUMAN_TYPES = (FAIR, HARDBALLER, BOULWARE, ACCOMMODATOR, BLUFFER, AVOIDER,
               POSITIONAL, NIBBLER)
BY_NAME = {t.name: t for t in (*HUMAN_TYPES, SNHP)}


# ── the pie: driven by the VALIDATED nash_deal engine ───────────────────────
# The pie humans fight over is exactly what SNHP would realize — the validated
# `nash_deal` joint gain (the engine that reproduces run.run_week to the cent).
# Two solves per relationship-week: the FULL logroll (all issues) and the
# POSITIONAL price-only set (window/qty/terms/spoilage frozen at rate-card
# defaults). SNHP is therefore the efficiency CEILING by construction; humans
# split this pie (integrative), get the price-only pie (positional, ≈0), or
# destroy it (impasse). Personality never changes the ceiling — only who
# captures it and whether it closes.

@dataclass(frozen=True)
class RelValue:
    """The value structure of one relationship-week, from the validated engine."""
    pie_full: float         # SNHP-realizable joint gain, full logroll (the pie)
    pie_pos: float          # joint gain a price-only negotiation can reach (≈0)
    snhp_g_v: float         # SNHP's Nash split — venue gain above disagreement
    snhp_g_w: float         # SNHP's Nash split — wholesaler gain
    list_value: float       # rate-card list value at the Nash bundle
    buffer: float           # max($5, 3% of list value) — the nash_deal gate
    snhp_closes: bool       # nash_deal cleared the buffer (a positive-surplus deal)

    @property
    def snhp_share_v(self) -> float:
        return self.snhp_g_v / self.pie_full if self.pie_full > 0 else 0.5


def _joint(deal: Deal | None, d: Disagreement) -> float:
    if deal is None:
        return 0.0
    return (deal.u_v - d.d_v) + (deal.u_w - d.d_w)


def rel_value(ctx: RelCtx, env: WeekDemand, schedule: Schedule, *,
              coordinate: bool = True) -> tuple[RelValue, Disagreement]:
    """Value + disagreement for a relationship-week. Computed ONCE; the cheap
    concession game then runs for every type pair over these scalars."""
    d = disagreement(ctx, env, schedule, coordinate=coordinate)
    deal = nash_deal(ctx, env, schedule, d, coordinate=coordinate)
    pos = nash_deal(ctx, env, schedule, d, coordinate=coordinate,
                    fix={"window": d.window, "qty": d.rc_q,
                         "terms": d.rc_terms, "share": 0.0})
    pie_full = round(_joint(deal, d), 6)
    pie_pos = round(max(0.0, _joint(pos, d)), 6)
    if deal is None:
        return (RelValue(0.0, pie_pos, 0.0, 0.0, 0.0, cal.BUFFER_MIN, False), d)
    gv, gw = deal.u_v - d.d_v, deal.u_w - d.d_w
    buf = max(cal.BUFFER_MIN, cal.BUFFER_FRAC * deal.list_value)
    return (RelValue(pie_full, pie_pos, round(gv, 6), round(gw, 6),
                     round(deal.list_value, 2), round(buf, 4), True), d)


# ── the outcome of one negotiation ──────────────────────────────────────────

@dataclass(frozen=True)
class Outcome:
    closed: bool
    g_v: float              # venue gain above disagreement ($; 0 on impasse)
    g_w: float              # wholesaler gain above disagreement
    share_v: float          # venue's captured share of the on-the-table pie
    share_w: float
    pie: float              # the on-the-table pie (pie_pos if positional)
    positional: bool        # the logroll was collapsed to price-only
    nibbled: bool           # a party extracted a post-close nibble
    impasse: bool           # positive-surplus deal that failed to close
    rounds: int             # rounds to close (−1 on impasse)

    @property
    def joint(self) -> float:
        return self.g_v + self.g_w


def _is_soft(t: NegotiatorType) -> bool:
    """A naive counterpart an exploiter can read: concedes fast, honest, no
    bluff, not itself an exploiter/broker (the info-asymmetry target)."""
    return (t.concede >= 0.5 and t.honest and t.claim_floor <= 1e-9
            and not t.is_snhp and not t.exploits)


def _effective(me: NegotiatorType, opp: NegotiatorType):
    """Exploiting info asymmetry: a sophisticated type that reads a soft
    counterpart raises its anchor and stops conceding — squeezing the naive to
    its reservation."""
    a, b, phi, T = me.anchor, me.concede, me.claim_floor, me.deadline
    if me.exploits and _is_soft(opp):
        a, b = max(a, 0.95), min(b, 0.02)
    return a, b, phi, T


def bargain(tv: NegotiatorType, tw: NegotiatorType, rv: RelValue) -> Outcome:
    """Run the concession game between a venue type `tv` and a wholesaler type
    `tw` over the relationship's value `rv`. Deterministic in the types and the
    pie; the demand seed enters only through the dollar pie."""
    if tv.is_snhp or tw.is_snhp:
        raise ValueError("use snhp_outcome() for the broker")
    positional = tv.positional or tw.positional
    pie = rv.pie_pos if positional else rv.pie_full
    if pie <= 0.0:                       # nothing material to trade (or price-only)
        return Outcome(False, 0.0, 0.0, 0.0, 0.0, pie, positional, False,
                       False, -1)
    av, bv, phiv, Tv = _effective(tv, tw)
    aw, bw, phiw, Tw = _effective(tw, tv)
    T = min(Tv, Tw)
    for t in range(T + 1):
        cv = phiv + (av - phiv) * (1.0 - bv) ** t
        cw = phiw + (aw - phiw) * (1.0 - bw) ** t
        if cv + cw <= 1.0 + 1e-12:
            slack = 1.0 - cv - cw
            sv, sw = cv + slack / 2.0, cw + slack / 2.0
            nibbled = False
            if tv.nibble > 0.0:          # nibbler extracts extras post-close
                dd = min(tv.nibble, sw); sv += dd; sw -= dd; nibbled = True
            if tw.nibble > 0.0:
                dd = min(tw.nibble, sv); sw += dd; sv -= dd; nibbled = True
            return Outcome(True, round(sv * pie, 6), round(sw * pie, 6),
                           round(sv, 6), round(sw, 6), pie, positional,
                           nibbled, False, t)
    # never converged before the earliest walk → impasse (deadweight = pie)
    impasse = pie > rv.buffer            # only material pies count as toxic loss
    return Outcome(False, 0.0, 0.0, 0.0, 0.0, pie, positional, False,
                   impasse, -1)


def snhp_outcome(rv: RelValue) -> Outcome:
    """The neutral broker: the validated `nash_deal` bundle (the full logroll)
    with its Nash split — personality-independent, closes exactly when the engine
    clears the buffer. This is the SAME output that reproduces run.run_week to the
    cent; the human battery cannot move it."""
    if not rv.snhp_closes:               # sub-buffer: amicable no material deal
        return Outcome(False, 0.0, 0.0, 0.0, 0.0, rv.pie_full, False, False,
                       False, -1)
    return Outcome(True, round(rv.snhp_g_v, 6), round(rv.snhp_g_w, 6),
                   round(rv.snhp_share_v, 6), round(1.0 - rv.snhp_share_v, 6),
                   rv.pie_full, False, False, False, 0)


# ── failure mode 4: relationship damage / retention ─────────────────────────
# Toxic tactics breed grievance → churn. Coefficients are a transparent
# parameterization (documented in RESULTS-HUMAN.md); the DOMINANCE is coefficient-
# robust because SNHP has squeeze = 0, nibble = 0, impasse = 0 BY CONSTRUCTION,
# so its grievance is minimal for ANY non-negative coefficients. Grounded in
# Malhotra & Bazerman on trust/reputation and the negotiation-relationship
# literature: being squeezed, nibbled, or stonewalled predicts defection.
H0 = 0.03               # baseline weekly churn hazard (a live relationship)
W_SQUEEZE = 0.60        # per unit of unfair squeeze (0.5 − the worse share)
W_NIBBLE = 0.25         # a post-close nibble
W_IMPASSE = 0.50        # a toxic impasse (the deal blew up)
HMAX = 0.90
RETENTION_HORIZON = 12  # weeks of future relationship value at stake


@dataclass(frozen=True)
class Retention:
    hazard: float           # weekly churn hazard
    retention: float        # 1 − hazard
    ltv: float              # expected retained future JOINT surplus over horizon


def relationship(out: Outcome, rv: RelValue, *,
                 horizon: int = RETENTION_HORIZON) -> Retention:
    """Map a negotiation outcome to the relationship's forward value. The future
    weekly stake is the full pie (what a HEALTHY relationship would keep
    creating). Grievance is 'how far BELOW the neutral (SNHP Nash) share the party
    was squeezed' — so exploitation registers directly and SNHP, which IS the
    neutral benchmark, has zero squeeze (grievance ≈ 0) by construction."""
    fair_v = rv.snhp_share_v
    if out.closed:
        squeeze = max(fair_v - out.share_v, (1.0 - fair_v) - out.share_w, 0.0)
        grief = W_SQUEEZE * squeeze + (W_NIBBLE if out.nibbled else 0.0)
    elif out.impasse:
        grief = W_IMPASSE
    else:
        grief = 0.0                      # sub-buffer no-deal: no toxicity
    h = min(HMAX, H0 + grief)
    r = 1.0 - h
    ltv = rv.pie_full * sum(r ** k for k in range(1, horizon + 1))
    return Retention(round(h, 6), round(r, 6), round(ltv, 4))

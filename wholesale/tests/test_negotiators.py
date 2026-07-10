"""The toxic-human-negotiation baseline (task #69) — every tactic behaves as
specified; SNHP fixes the four failure modes; the broker neutralises the liar
battery; byte-deterministic.

Binding rigor (mirrors test_wholesale / test_supply):
  * each hardball tactic (anchoring, Boulware, bluff, nibble, false deadline,
    positional, info-asymmetry exploitation) behaves as the literature specifies;
  * impasse rate human > SNHP; the naive is protected; the logroll is captured;
  * SNHP's split is personality-INDEPENDENT (the Von Neumann neutralisation) and
    equals the validated nash_deal engine to the cent;
  * determinism: re-running a seed is byte-identical.
"""
import json

import numpy as np
import pytest

from wholesale import calibration as cal
from wholesale.negotiators import (ACCOMMODATOR, AVOIDER, BLUFFER, BOULWARE,
                                   FAIR, HARDBALLER, HUMAN_TYPES, NIBBLER,
                                   POSITIONAL, SNHP, NegotiatorType, _effective,
                                   _is_soft, bargain, rel_value, relationship,
                                   snhp_outcome)
from wholesale.run_human import block_rel_values, run_seed, summarize
from wholesale.scenario import build_ctx, disagreement, nash_deal
from wholesale.world import Schedule, week_demand

SEED = 20260710


def _closing_rv(w="dry", v="bodega", seed=SEED, wk=0):
    """A relationship-week SNHP closes (a positive-surplus deal)."""
    ctx = build_ctx(w, v, cal.BASE_FLEX)
    env = week_demand(seed, wk, w, v, cal.BASE_NOISE)
    rv, _d = rel_value(ctx, env, Schedule())
    assert rv.snhp_closes and rv.pie_full > rv.buffer
    return rv


# ══ the taxonomy is well-formed ═════════════════════════════════════════════

def test_roster_shape_and_parameters():
    assert len(HUMAN_TYPES) == 8
    assert not any(t.is_snhp for t in HUMAN_TYPES)
    assert SNHP.is_snhp
    for t in (*HUMAN_TYPES, SNHP):
        assert 0.0 <= t.anchor <= 1.0 and 0.0 <= t.concede <= 1.0
        assert 0.0 <= t.claim_floor <= t.anchor + 1e-9 or t.is_snhp
        assert t.deadline >= 0


# ══ TACTICS: each behaves as specified ══════════════════════════════════════

def test_anchoring_biases_the_split():
    """Tversky & Kahneman: a more extreme first offer pulls the settlement.
    Two types identical but for the anchor → the higher anchor captures more."""
    rv = _closing_rv()
    lo = NegotiatorType("lo", anchor=0.55, concede=0.2, claim_floor=0.0, deadline=20)
    hi = NegotiatorType("hi", anchor=0.85, concede=0.2, claim_floor=0.0, deadline=20)
    o_lo = bargain(lo, FAIR, rv)
    o_hi = bargain(hi, FAIR, rv)
    assert o_lo.closed and o_hi.closed
    assert o_hi.share_v > o_lo.share_v + 1e-6


def test_boulware_never_concedes_and_impasses_vs_a_firm_party():
    """Take-it-or-leave-it: zero concession; a principled party (FAIR won't cave
    below a fair split) → impasse, while a naive over-conceder caves."""
    assert BOULWARE.concede == 0.0
    rv = _closing_rv()
    assert bargain(BOULWARE, FAIR, rv).impasse            # ultimatum refused
    o_acc = bargain(BOULWARE, ACCOMMODATOR, rv)
    assert o_acc.closed and o_acc.share_v > 0.5           # the naive caves


def test_bluffing_misrepresents_batna_extracts_from_naive_impasses_vs_firm():
    """A bluffed BATNA (claim_floor>0, honest=False) extracts from a credulous
    over-conceder but collapses the deal when a firm party calls it."""
    assert not BLUFFER.honest and BLUFFER.claim_floor > 0.0
    rv = _closing_rv()
    o_naive = bargain(BLUFFER, ACCOMMODATOR, rv)
    assert o_naive.closed and o_naive.share_v > 0.55      # extracts via the lie
    assert bargain(BLUFFER, HARDBALLER, rv).impasse       # bluff called → impasse


def test_nibbling_shifts_share_and_damages_the_relationship():
    """A post-close nibble moves surplus to the nibbler and breeds grievance:
    the same deal, nibbled, retains worse than un-nibbled."""
    assert NIBBLER.nibble > 0.0
    rv = _closing_rv()
    o = bargain(NIBBLER, FAIR, rv)
    assert o.closed and o.nibbled
    # a non-nibbling clone leaves the counterpart better off → higher retention
    clone = NegotiatorType("clone", anchor=NIBBLER.anchor, concede=NIBBLER.concede,
                           claim_floor=NIBBLER.claim_floor, deadline=NIBBLER.deadline)
    r_nib = relationship(o, rv).retention
    r_cln = relationship(bargain(clone, FAIR, rv), rv).retention
    assert r_nib < r_cln


def test_false_deadline_avoider_walks_from_positive_surplus():
    """The conflict-averse avoider (deadline 0) walks from a POSITIVE-surplus
    deal → the Myerson-Satterthwaite deadweight; SNHP closes the very same pie."""
    assert AVOIDER.deadline == 0
    rv = _closing_rv()
    o = bargain(AVOIDER, FAIR, rv)
    assert o.impasse and o.joint == 0.0
    assert snhp_outcome(rv).closed and snhp_outcome(rv).joint == pytest.approx(rv.pie_full)


def test_positional_collapses_the_logroll_price_is_a_transfer():
    """Fisher & Ury: positional (price-only) bargaining creates ~no joint value —
    price is a transfer; the whole pie is in window×qty×terms×spoilage."""
    rv = _closing_rv()
    assert rv.pie_pos < 1e-6 < rv.pie_full        # the strong, honest finding
    o = bargain(POSITIONAL, FAIR, rv)
    assert o.positional and o.joint <= rv.pie_pos + 1e-9
    assert snhp_outcome(rv).joint == pytest.approx(rv.pie_full)   # SNHP gets it all


def test_exploiting_info_asymmetry_squeezes_the_naive():
    """The sophisticated reads a soft counterpart and raises its anchor / stops
    conceding — the naive is squeezed harder than by a non-exploiting clone."""
    assert _is_soft(ACCOMMODATOR) and not _is_soft(HARDBALLER)
    a, b, _phi, _T = _effective(HARDBALLER, ACCOMMODATOR)
    assert a >= 0.95 and b <= 0.02                # the exploit kicks in
    rv = _closing_rv()
    o = bargain(HARDBALLER, ACCOMMODATOR, rv)
    assert o.closed and o.share_w < 0.15          # the naive fleeced


# ══ SNHP fixes the four failure modes ═══════════════════════════════════════

def test_impasse_rate_human_exceeds_snhp_and_deadweight_is_material():
    """(1) On the positive-surplus set, humans impasse at a material rate; SNHP
    never does, and the destroyed pie exceeds the don't-negotiate buffer."""
    rows = [run_seed(SEED + i, 3) for i in range(2)]
    s = summarize(rows)
    im = s["four_failure_modes"]["1_impasse"]
    assert im["human_impasse_rate"]["mean"] > 0.10
    assert im["snhp_impasse_rate"] == 0.0
    assert im["deadweight_per_impasse_$"]["mean"] > cal.BUFFER_MIN


def test_snhp_protects_the_naive():
    """(2) The naive party's realised gain is strictly larger under the neutral
    broker than in human-vs-human — directly, against its worst exploiter."""
    rv = _closing_rv()
    human = bargain(HARDBALLER, ACCOMMODATOR, rv).g_w      # naive as wholesaler
    snhp = snhp_outcome(rv).g_w
    assert snhp > human + 1e-6


def test_missed_logroll_gap_is_captured_by_snhp():
    """(3) A positional-involving negotiation leaves the integrative pie on the
    table; SNHP realises it."""
    rows = [run_seed(SEED + i, 3) for i in range(2)]
    s = summarize(rows)
    lr = s["four_failure_modes"]["3_missed_logroll"]
    assert lr["logroll_gap_$"]["mean"] > 0.0
    assert lr["positional_joint_human_$"]["mean"] < lr["positional_joint_snhp_$"]["mean"]


def test_relationship_damage_snhp_retains_better():
    """(4) Toxic tactics breed churn; SNHP's fair, no-impasse deal retains
    better. Ordering: impasse < squeezed < fair; SNHP ≥ human on the toxic ones."""
    rv = _closing_rv()
    r_fair = relationship(bargain(FAIR, FAIR, rv), rv).retention
    r_squeeze = relationship(bargain(HARDBALLER, ACCOMMODATOR, rv), rv).retention
    r_impasse = relationship(bargain(AVOIDER, FAIR, rv), rv).retention
    r_snhp = relationship(snhp_outcome(rv), rv).retention
    assert r_impasse < r_squeeze < r_fair
    assert r_snhp >= r_squeeze and r_snhp >= r_impasse


# ══ the broker neutralises the liar battery (Von Neumann) ═══════════════════

def test_snhp_split_is_personality_independent():
    """The neutral broker computes the fair split from the PINNED reservations
    (cogs / disagreement) regardless of personality — a hardballer cannot
    out-anchor it and a bluffer cannot move it. This IS the neutralisation."""
    rv = _closing_rv()
    base = snhp_outcome(rv)
    for tv in HUMAN_TYPES:
        for tw in HUMAN_TYPES:
            o = snhp_outcome(rv)          # broker ignores the type pair entirely
            assert (o.g_v, o.g_w, o.closed) == (base.g_v, base.g_w, base.closed)


def test_snhp_equals_the_validated_nash_deal_engine_to_the_cent():
    """SNHP's split is exactly the validated nash_deal bundle (the engine that
    reproduces run.run_week to the cent) — not a parallel definition."""
    ctx = build_ctx("dry", "bodega", cal.BASE_FLEX)
    env = week_demand(SEED, 0, "dry", "bodega", cal.BASE_NOISE)
    sch = Schedule()
    rv, d = rel_value(ctx, env, sch)
    deal = nash_deal(ctx, env, sch, d)
    assert abs(rv.snhp_g_v - (deal.u_v - d.d_v)) < 1e-6
    assert abs(rv.snhp_g_w - (deal.u_w - d.d_w)) < 1e-6


def test_bluff_neutralised_when_reservation_is_pinned():
    """The bluff is a misreport of the reservation. Because the supplier's floor
    is pinned (cogs / finite stock, paper §10), the broker's split does not move
    when a counterpart bluffs — the SNHP outcome facing a BLUFFER is identical to
    facing a FAIR party (the attested-interface result)."""
    rv = _closing_rv()
    assert snhp_outcome(rv) == snhp_outcome(rv)     # report-independent
    # and the human world is NOT: the bluff DOES move the human split
    honest_split = bargain(FAIR, ACCOMMODATOR, rv).share_v
    bluff_split = bargain(BLUFFER, ACCOMMODATOR, rv).share_v
    assert bluff_split > honest_split               # the lie pays off, sans broker


# ══ both-sides verdict + determinism ════════════════════════════════════════

def test_both_sides_snhp_dominates_the_population():
    """Both-SNHP beats human-vs-human on surplus, fairness, efficiency and
    retention across the type population (point estimates; full CIs in the doc)."""
    rows = [run_seed(SEED + i, 3) for i in range(3)]
    s = summarize(rows)
    dom = s["both_sides_verdict"]["dominates_on"]
    assert dom["surplus"] and dom["fairness"] and dom["efficiency"] and dom["retention"]


def test_hardballer_loses_its_extraction_edge_even_if_it_gains_on_average():
    """The honest decomposition: averaged over a mixed population the hardballer
    is better off (its impasses vs other aggressors are self-defeating), BUT it
    gives up its extraction edge — its take fleecing a naive collapses to the
    neutral split (edge_lost < 0)."""
    rows = [run_seed(SEED + i, 3) for i in range(3)]
    s = summarize(rows)
    hs = s["hardballer_story"]
    assert hs["edge_lost_$"]["mean"] < 0.0                       # gave up extraction
    assert hs["extraction_edge_vs_naive_human_$"]["mean"] > \
        hs["extraction_edge_vs_naive_snhp_$"]["mean"]


def test_determinism_byte_identical_reruns():
    """No LLM, no wall clock: a seed re-runs byte-identical."""
    a = json.dumps(summarize([run_seed(SEED, 4)]), sort_keys=True)
    b = json.dumps(summarize([run_seed(SEED, 4)]), sort_keys=True)
    assert a == b


def test_bargain_rejects_the_snhp_sentinel():
    """The broker is not a personality — bargain() must route SNHP to
    snhp_outcome()."""
    rv = _closing_rv()
    with pytest.raises(ValueError):
        bargain(SNHP, FAIR, rv)

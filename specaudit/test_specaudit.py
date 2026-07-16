"""SPECAUDIT S5/S6 tests — seeded, reproducible, structural invariants.

    python -m pytest specaudit/test_specaudit.py -q

These do NOT assert magnitudes (those are reported as bands, and pinning a band
edge to a golden would be exactly the point-estimate error the fairness protocol
forbids). They assert the INVARIANTS the banded numbers rely on: determinism,
that the spec (fixed-cart) world can never beat the oracle, that the snhp
nash_solver reaches the oracle it is credited with reaching, and the qualitative
monotonicity the report leans on (a family with more multi-issue structure leaves
a larger gap).
"""

from __future__ import annotations

import numpy as np

from specaudit import gap_sim as G


# --- determinism -------------------------------------------------------------

def test_s5a_cell_is_deterministic():
    a = G.run_cell_s5a("HIGH", "mid", 101)
    b = G.run_cell_s5a("HIGH", "mid", 101)
    assert a == b


def test_s5b_cell_is_deterministic():
    a = G.run_cell_s5b("MID", 0.25, 105)
    b = G.run_cell_s5b("MID", 0.25, 105)
    assert a == b


def test_full_run_is_deterministic():
    r1 = G.run_full([101, 102])
    r2 = G.run_full([101, 102])
    assert r1["S5a_deal_formation_gap"]["bands"] == \
        r2["S5a_deal_formation_gap"]["bands"]


# --- structural invariants of the deal-formation gap -------------------------

def test_checkout_never_beats_oracle():
    """The fixed-cart, no-counter world can never realise MORE joint surplus than
    the oracle pie. If this ever fails, the gap sign is meaningless."""
    rng = np.random.default_rng(7)
    for _ in range(400):
        opp = G.Opportunity(rng, G.REGIMES["HIGH"])
        Jo, _, _ = G.oracle_joint(opp)
        Jc, _, _, _ = G.checkout_outcome(opp, G.MARKUPS["open"])
        assert Jc <= Jo + 1e-6


def test_nash_reaches_oracle():
    """S6a credit: the snhp nash_solver, given a counter surface, recovers ~the
    full oracle pie (price only splits it). Asserted in AGGREGATE over the family
    (which is exactly the recovery-of-oracle number the report cites) rather than
    per single opportunity, where a tiny-pie deal can miss the coarse price/qty/
    date grid and look like a large percentage error."""
    rng = np.random.default_rng(11)
    s_oracle = s_nash = 0.0
    checked = 0
    for _ in range(600):
        opp = G.Opportunity(rng, G.REGIMES["MID"])
        Jo, _, _ = G.oracle_joint(opp)
        if Jo <= 1e-6:
            continue
        Jn, _, _, _ = G.nash_bundle(opp)
        s_oracle += Jo
        s_nash += max(0.0, Jn)
        checked += 1
    assert checked > 50                    # the MID family contains beneficial deals
    assert s_nash >= 0.95 * s_oracle       # bundled layer recovers ~the whole pie


def test_gap_is_nonnegative_everywhere():
    for cell in G.run_full([101, 102])["S5a_deal_formation_gap"]["cells"]:
        assert cell["gap_dollars"] >= -1e-6
        assert cell["gap_pct"] >= -1e-6


def test_foregone_trades_are_genuinely_beneficial():
    """Every 'foregone' trade must be one the oracle says is beneficial (Jo>0)
    AND that the fixed-cart world walked away from — a real lost deal, not a deal
    that never existed. This channel is menu-dependent: with a rich full menu it
    is negligible (a buyer usually accepts a suboptimal-but-positive cell rather
    than walk), but with a standard-shipping-only menu in the urgent regime it is
    substantial — which is precisely the report's finding, so we exercise it under
    the standard menu where it is real."""
    rng = np.random.default_rng(3)
    seen_foregone = 0
    for _ in range(600):
        opp = G.Opportunity(rng, G.REGIMES["HIGH"])
        Jo, _, _ = G.oracle_joint(opp)
        _, _, _, accepted = G.checkout_outcome(opp, G.MARKUPS["open"], "standard")
        if Jo > 1e-6 and not accepted:
            seen_foregone += 1
    assert seen_foregone > 0  # the take-it-or-leave-it walk-away channel is real


def test_full_menu_suppresses_walkaways_vs_standard():
    """Credit-due invariant: because ACP/UCP let the merchant publish a
    fulfillment-option menu, a full menu produces NO MORE foregone trades than a
    standard-only menu — the menu genuinely narrows the gap."""
    rng = np.random.default_rng(19)
    f_full = f_std = 0
    for _ in range(500):
        opp = G.Opportunity(rng, G.REGIMES["HIGH"])
        Jo, _, _ = G.oracle_joint(opp)
        if Jo <= 1e-6:
            continue
        _, _, _, a_full = G.checkout_outcome(opp, G.MARKUPS["mid"], "full")
        _, _, _, a_std = G.checkout_outcome(opp, G.MARKUPS["mid"], "standard")
        f_full += (not a_full)
        f_std += (not a_std)
    assert f_full <= f_std


# --- monotonicity the report relies on ---------------------------------------

def test_high_intensity_gap_ge_low_intensity_gap():
    """The report's central honest claim: the gap is CONDITIONAL on the deal
    having multi-issue structure. A high-urgency / tight-capacity / tight-deadline
    family must leave at least as large a gap as a slack one, at the same markup."""
    seeds = [101, 102, 103, 104]
    lo = G.run_cell_s5a("LOW", "open", seeds[0])
    # pool over seeds for stability
    hi_gap = np.mean([G.run_cell_s5a("HIGH", "open", s)["gap_pct"] for s in seeds])
    lo_gap = np.mean([G.run_cell_s5a("LOW", "open", s)["gap_pct"] for s in seeds])
    assert hi_gap >= lo_gap
    assert lo["gap_pct"] >= 0.0


# --- settlement exposure invariants ------------------------------------------

def test_receipt_gate_never_hurts_buyer():
    """S6b: paying only for delivered goods can never leave the buyer worse off
    than paying on authorisation, for any deceptive fraction."""
    for regime in G.REGIMES:
        for f in G.DECEPTIVE_FRACTIONS:
            c = G.run_cell_s5b(regime, f, 101)
            assert c["buyer_surplus_receipt_gated"] >= \
                c["buyer_surplus_pay_on_auth"] - 1e-6


def test_exposure_grows_with_deception():
    """More deceptive counterparties => at least as much settlement exposure."""
    base = G.run_cell_s5b("MID", 0.05, 101)["exposure_dollars"]
    high = G.run_cell_s5b("MID", 0.25, 101)["exposure_dollars"]
    assert high >= base - 1e-6


# --- band well-formedness ----------------------------------------------------

def test_bands_are_ordered():
    r = G.run_full([101, 102])
    for section in ("S5a_deal_formation_gap", "S5b_settlement_exposure"):
        for band in r[section]["bands"].values():
            assert band["band_lo"] <= band["band_hi"] + 1e-9
            assert band["band_lo"] <= band["pooled_mean"] + 1e-9
            assert band["pooled_mean"] <= band["band_hi"] + 1e-9

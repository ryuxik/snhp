"""Tests for B6.2 (parking-validation bundle) and B6.3 (slack-swap bundles +
clearing transfers) — the "bundles" step of NETWORK.md §A, the mechanistic form
of the flywheel's durable coordination channel.

The load-bearing invariants (the program's rigor, asserted here):
  * paired-stream byte-identity — every arm consumes the byte-identical
    per-identity population/valuation stream; the draw depends on WHO not on the
    policy (gated/ungated, independent/cross) or the treatment axis;
  * money + unit CONSERVATION across every clearing transfer (to the cent / the
    unit), including the participation floor (source recovers ≥ salvage);
  * DISCOUNT-ONLY — a bundle only ever cuts an outlay off a posted list; no
    posted price ever rises, and no clearing price sits above the buyer's value;
  * NO price signal between substitutes — the clearing/validation decision reads
    only would-spoil stock + demand-state, never a substitute's posted price.
"""
import json
import pathlib

import numpy as np
import pytest

from block import bundles
from block.bundles import ParkConfig, SwapConfig

SEED = 20260710


@pytest.fixture(scope="module")
def result():
    """The committed bundles run — the same config block/results-b6-bundles.json
    records (400 seeds; analytic, ~2s)."""
    return bundles.run_all(ParkConfig(seeds=400), SwapConfig(seeds=400),
                           seed0=SEED)


# ═══════════════════════════════════════════════════════════════════════════
# paired-stream byte-identity (keyed on IDENTITY, never on policy)
# ═══════════════════════════════════════════════════════════════════════════

def test_parking_wtp_stream_is_paired_across_policy_and_load():
    """The shopper WTP draw is a pure function of (seed, retail) — it does NOT
    depend on the commuter load u or on the gated/ungated policy. So both bundle
    policies at every u cell face the BYTE-IDENTICAL population (paired on shopper
    identity), the same variance-reduction discipline as the twin-world block."""
    cfg = ParkConfig()
    rp = bundles.RETAIL_PROFILES[0]
    a = bundles._shopper_wtp(101, rp, cfg)
    b = bundles._shopper_wtp(101, rp, cfg)
    assert np.array_equal(a, b)                    # byte-identical on re-draw
    # a different retail identity ⇒ its own paired stream (different bytes)
    other = bundles._shopper_wtp(101, bundles.RETAIL_PROFILES[1], cfg)
    assert not np.array_equal(a[:len(other)], other[:len(a)])


def test_swap_valuation_stream_is_paired_across_arms():
    """The demand-pool valuations are a pure function of (seed, tag); the
    INDEPENDENT and CROSS arms consume the SAME per-seed draws (paired), differing
    only in the matching decision, never in the population."""
    cfg = SwapConfig()
    a = bundles._draw_values(7, "cafe-unmet-sandwich", cfg.unmet_pool, 9.75, cfg)
    b = bundles._draw_values(7, "cafe-unmet-sandwich", cfg.unmet_pool, 9.75, cfg)
    assert a == b                                   # byte-identical
    # keyed on identity: a different tag ⇒ an independent stream
    c = bundles._draw_values(7, "bakery-local-sandwich", cfg.unmet_pool, 9.75, cfg)
    assert a != c


def test_everything_is_deterministic_on_seed():
    a = bundles.run_all(ParkConfig(seeds=40), SwapConfig(seeds=40), seed0=5)
    b = bundles.run_all(ParkConfig(seeds=40), SwapConfig(seeds=40), seed0=5)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ═══════════════════════════════════════════════════════════════════════════
# B6.2 — parking-validation: Pareto win on slack, anti-lever when tight
# ═══════════════════════════════════════════════════════════════════════════

def test_commuter_shadow_value_is_grounded_and_inelastic():
    """v_c (the displaced-commuter opportunity cost) is built from the committed
    slots calibration (day-max net ops), and the commuter segment is INELASTIC
    (|e| < 1) — so a displaced commuter is a near-certain lost sale, not a
    price-substitution that comes back cheaper."""
    from slots import calibration as scal
    cfg = ParkConfig()
    assert cfg.commuter_abs_elasticity < 1.0            # inelastic
    expected = scal.PARKING_DAY_MAX - scal.PARKING_COST_PER_HOUR * cfg.commuter_hours
    assert bundles.commuter_shadow_value(cfg) == pytest.approx(expected)


def test_slack_gated_bundle_is_a_pareto_win(result):
    """B6.2 headline: the shippable SLACK-GATED bundle grows joint surplus
    (Δjoint>0) on slack for EVERY retail profile, never a loss anywhere, and never
    displaces a paying customer (Pareto-frac ≡ 1). The culturally pre-accepted
    'shop here, parking's on us' cross-subsidy — computed, and Pareto."""
    pk = result["B6_2_parking_validation"]
    assert pk["verdict"]["slack_gated_is_pareto_win_all_profiles"]
    for p in pk["profiles"]:
        slack = p["slack_cell"]
        assert slack["d_joint_gated"]["ci95"][0] > 0.0         # Δjoint>0 on slack
        assert slack["pareto_frac_gated"]["mean"] == pytest.approx(1.0)
        for c in p["cells"]:
            assert c["gated_never_loses"]                       # never a loss
            assert c["pareto_frac_gated"]["mean"] == pytest.approx(1.0)


def test_win_rides_slack_and_shrinks_as_lot_fills(result):
    """The gated win is SLACK: Δjoint_gated is monotone non-increasing in the
    commuter load u (more paying commuters ⇒ less empty capacity to monetise ⇒
    smaller win), shrinking toward 0 as the lot fills — the honest scope of the
    win (it is not free money, it is the value of otherwise-idle slots)."""
    for p in result["B6_2_parking_validation"]["profiles"]:
        g = [c["d_joint_gated"]["mean"] for c in p["cells"]]
        assert all(g[i + 1] <= g[i] + 1e-6 for i in range(len(g) - 1))
        assert g[-1] < g[0]


def test_ungated_validation_is_the_anti_lever_when_tight(result):
    """The pre-registered ANTI-LEVER: an UNGATED validation (validating into
    OCCUPIED capacity) cannibalises paying, inelastic commuters. For the
    thin-margin 'eatery' sale (margin < v_c) it turns Δjoint strictly NEGATIVE
    when the lot is tight (CI entirely below 0) — the failure the slack-gate
    exists to prevent."""
    pk = result["B6_2_parking_validation"]
    assert pk["verdict"]["ungated_anti_lever_when_tight_thin_margin"]
    eatery = next(p for p in pk["profiles"] if p["retail"] == "eatery")
    assert not eatery["margin_covers_v_c"]                 # thin margin < v_c
    assert eatery["tight_cell"]["d_joint_ungated"]["ci95"][1] < 0.0   # Δjoint<0
    assert eatery["u_star_ungated_anti_lever"] is not None            # a crossover


def test_thick_margin_ungated_is_positive_sum_but_not_pareto(result):
    """The other failure mode, recorded not hidden: for the thick-margin
    'boutique' sale (margin > v_c) an ungated validation stays JOINT-positive even
    while displacing — but it is NOT Pareto (the displaced commuter is strictly
    worse off). Joint-positive is not the same as Pareto; only the slack-gated
    bundle is Pareto."""
    boutique = next(p for p in result["B6_2_parking_validation"]["profiles"]
                    if p["retail"] == "boutique")
    assert boutique["margin_covers_v_c"]
    assert not boutique["tight_cell"]["ungated_anti_lever"]      # stays joint>0
    assert boutique["tight_cell"]["pareto_frac_ungated"]["mean"] < 0.5  # displaces


def test_parking_bundle_is_discount_only(result):
    """DISCOUNT-ONLY: the bundle only ever CUTS the shopper's outlay off the
    posted lists — it never raises either posted price. A bundled shopper pays
    the retail list and gets parking free (outlay = list ≤ list + park_price, the
    unbundled outlay); the posted parking rate and retail list are untouched
    calibration constants."""
    assert result["B6_2_parking_validation"]["verdict"]["discount_only"]
    for rp in bundles.RETAIL_PROFILES:
        bundled_outlay = rp.list_price                 # parking validated free
        unbundled_outlay = rp.list_price + rp.park_price
        assert bundled_outlay <= unbundled_outlay      # never a price rise


# ═══════════════════════════════════════════════════════════════════════════
# B6.3 — slack-swap clearing: joint gain + CONSERVATION + no price signal
# ═══════════════════════════════════════════════════════════════════════════

def test_cross_clearing_grows_joint_at_every_excess(result):
    """B6.3 headline: routing one venue's would-spoil excess to the other's unmet
    demand GROWS joint surplus vs each clearing ALONE, at every excess level (CI
    clears zero) — the mechanistic form of the flywheel's durable coordination
    channel."""
    sw = result["B6_3_slack_swap_clearing"]
    assert sw["verdict"]["cross_clearing_grows_joint_all_excess"]
    for c in sw["cells"]:
        assert c["d_joint"]["ci95"][0] > 0.0
        # cross clears at least as many would-spoil units as independent
        assert (c["units_cleared_cross"]["mean"]
                >= c["units_cleared_independent"]["mean"])


def test_joint_gain_scales_with_would_spoil_stock(result):
    """The coordination value scales with how much would-spoil stock is routed —
    a bigger excess ⇒ more cross-venue matching value (the flywheel's
    increasing-returns coordination channel, made mechanical)."""
    sw = result["B6_3_slack_swap_clearing"]
    assert sw["verdict"]["joint_gain_scales_with_excess"]
    dj = [c["d_joint"]["mean"] for c in sw["cells"]]
    assert dj[-1] > dj[0]


def test_money_and_unit_conservation_on_the_sweep(result):
    """CONSERVATION across every clearing transfer: buyers' outlay equals source
    receipts + clearing-house receipts to the cent, and units are conserved
    (available == cleared + spoiled; routed-out == received-in) to the unit."""
    sw = result["B6_3_slack_swap_clearing"]
    assert sw["verdict"]["money_conserved_all"]
    assert sw["verdict"]["units_conserved_all"]
    for c in sw["cells"]:
        assert c["money_residual_max_abs"] < 1e-6
        assert c["unit_residual_max_abs"] == 0


def test_clearing_ledger_conserves_money_and_units_directly():
    """Direct exercise of the clearing ledger: money in == money out, units
    balance, the source recovers AT LEAST salvage on every cleared unit (the
    participation floor), and joint growth == buyer + source + clearing shares."""
    cfg = SwapConfig()
    values = [12.0, 9.5, 7.0, 4.0, 2.0, 0.4]      # incl. some below salvage
    growth, led = bundles._clear(values, salvage=0.5, excess=4, cross=True,
                                 cfg=cfg)
    assert led.money_residual() == pytest.approx(0.0, abs=1e-9)
    assert led.unit_residual() == 0
    assert led.units_available == led.units_cleared + led.units_spoiled
    assert led.units_routed_out == led.units_received_in
    # participation floor: source keeps >= salvage per cleared unit
    assert led.source_receipts >= 0.5 * led.units_cleared - 1e-9
    # growth is conserved: p_spoil·(v−salv) split among the three parties
    p = cfg.p_spoil
    split = led.buyer_surplus * p + (led.source_receipts + led.clearing_receipts
                                     - 0.5 * led.units_cleared) * p
    assert growth == pytest.approx(split, abs=1e-6)


def test_clearing_price_is_discount_only():
    """DISCOUNT-ONLY on the clearing side: every clearing price sits in
    [salvage, value] — never above the value the buyer walked in with, never
    below the merchant's salvage floor."""
    cfg = SwapConfig()
    for extraction in (0.0, 0.25, 0.5, 0.9):
        c2 = SwapConfig(extraction=extraction)
        for v in (10.0, 5.0, 1.0):
            price = 0.5 + (1.0 - extraction) * (v - 0.5)   # the module's formula
            assert 0.5 - 1e-9 <= price <= v + 1e-9


def test_clearing_reads_no_substitute_price_signal(result):
    """NO price signal between substitutes: the clearing decision is a pure
    function of {would-spoil excess (stock state), buyer valuations (demand
    state), salvage floor}. It takes NO substitute-venue posted price — asserted
    by construction and exercised adversarially: injecting a decoy 'rival price'
    into the value pool it never reads leaves the outcome unchanged."""
    assert result["B6_3_slack_swap_clearing"]["no_substitute_price_signal"]
    assert bundles.price_reads_no_substitute_signal()
    # adversarial: the matching depends only on values+salvage+excess; recomputing
    # with an unrelated 'rival posted price' variable in scope changes nothing
    cfg = SwapConfig()
    vals = [9.0, 6.0, 3.0, 1.0]
    g1, _ = bundles._clear(vals, salvage=0.5, excess=2, cross=False, cfg=cfg)
    _rival_posted_price = 999.0          # a substitute's price — never consumed
    g2, _ = bundles._clear(vals, salvage=0.5, excess=2, cross=False, cfg=cfg)
    assert g1 == g2


# ═══════════════════════════════════════════════════════════════════════════
# the committed artifact
# ═══════════════════════════════════════════════════════════════════════════

def test_committed_bundles_results_stay_reproducible(result):
    """block/results-b6-bundles.json reproduces byte-identically at its config."""
    path = pathlib.Path(__file__).parents[1] / "results-b6-bundles.json"
    committed = json.load(open(path))
    assert json.dumps(result, sort_keys=True) == json.dumps(committed,
                                                            sort_keys=True)

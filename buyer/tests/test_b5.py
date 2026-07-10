"""B5 tests: coordination MATCHES scarce spoil-stock to the highest-value buyers
(growth over independent commits), and the pre-registered monopsony audit holds
— the participation floor is load-bearing and over-reach is self-defeating."""
import pytest

from buyer.run import run_coordinate
from buyer.strategies import coordinate


def test_efficient_beats_random_when_scarce():
    vals = [5.0, 4.0, 3.0, 2.0, 1.0]      # 5 buyers, only 2 spoil-units
    eff = coordinate(vals, salvage=0.3, s_risk=2, p_spoil=0.4,
                     allocation="efficient")
    worst = coordinate(vals, salvage=0.3, s_risk=2, p_spoil=0.4,
                       allocation="random", seed=0)
    # efficient allocation clears the TWO highest values → max possible growth
    assert eff.total_growth >= worst.total_growth - 1e-9
    assert abs(eff.total_growth - 0.4 * ((5 - .3) + (4 - .3))) < 1e-9


def test_participation_floor_holds_up_to_extraction_one():
    vals = [5.0, 4.0, 3.0]
    for ext in (0.0, 0.5, 0.9, 1.0):
        r = coordinate(vals, salvage=0.3, s_risk=3, p_spoil=0.4, extraction=ext)
        assert r.participation_ok
        assert r.merchant_margin >= -1e-9          # never below the salvage floor
    at_floor = coordinate(vals, salvage=0.3, s_risk=3, p_spoil=0.4, extraction=1.0)
    assert abs(at_floor.merchant_margin) < 1e-9    # extraction=1 pins it AT floor


def test_overreach_breaches_floor_and_destroys_welfare():
    vals = [5.0, 4.0, 3.0]
    floor = coordinate(vals, salvage=0.3, s_risk=3, p_spoil=0.4, extraction=1.0)
    over = coordinate(vals, salvage=0.3, s_risk=3, p_spoil=0.4, extraction=1.3)
    assert not over.participation_ok               # merchant refuses sub-floor
    assert over.spoiled_by_overreach > 0
    assert over.total_growth < floor.total_growth  # welfare LOST → self-defeating


def test_growth_never_negative():
    vals = [5.0, 0.4, 0.35, 6.0]
    r = coordinate(vals, salvage=0.3, s_risk=2, p_spoil=0.4)
    assert r.total_growth >= -1e-9
    assert r.buyer_growth >= -1e-9 and r.merchant_margin >= -1e-9


def test_audit_verdict_passes():
    co = run_coordinate(20260710, 1200, ks=(2, 5, 10))
    assert co["audit_checks"]["A_coord_not_below_indep"]
    assert co["audit_checks"]["B_participation_floor_holds"]
    assert co["audit_checks"]["D_overreach_is_self_defeating"]
    assert co["audit_verdict"].startswith("PASS")

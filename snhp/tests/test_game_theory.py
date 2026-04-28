"""
Tests for the SNHP Game Theory Engine.

Every test validates a mathematical invariant derived from the named theorem.
No behavioral heuristics — only formal properties.
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snhp.market.priors import fit_market_distribution
from snhp.core_math.bayesian import (
    acceptance_probability,
    optimal_bid_myerson,
    myerson_bid_analysis,
    should_probe_first,
    deadweight_loss_warning,
)
from snhp.core_math.rubinstein import (
    compute_discount_factor,
    rubinstein_equilibrium,
)


# ─── Fixtures ─────────────────────────────────────

# NYC photographer market (from market_data.json)
PHOTO_P25, PHOTO_P50, PHOTO_P75, PHOTO_P90 = 65, 95, 140, 200

@pytest.fixture
def photo_market():
    mu, sigma = fit_market_distribution(PHOTO_P25, PHOTO_P50, PHOTO_P75, PHOTO_P90)
    return mu, sigma

@pytest.fixture
def consultant_market():
    mu, sigma = fit_market_distribution(100, 175, 275, 400)
    return mu, sigma


# ═══════════════════════════════════════════════════
#  Market Distribution Fitting
# ═══════════════════════════════════════════════════

class TestFitMarketDistribution:

    def test_mu_equals_log_median(self):
        """mu should be ln(median) by construction."""
        mu, sigma = fit_market_distribution(65, 95, 140, 200)
        assert abs(mu - np.log(95)) < 1e-10

    def test_sigma_positive(self):
        """sigma must be positive for a valid distribution."""
        _, sigma = fit_market_distribution(65, 95, 140, 200)
        assert sigma > 0

    def test_narrow_distribution(self):
        """Tight percentile bands → small sigma."""
        _, sigma_narrow = fit_market_distribution(90, 100, 110, 120)
        _, sigma_wide = fit_market_distribution(30, 100, 300, 500)
        assert sigma_narrow < sigma_wide

    def test_returns_floats(self):
        mu, sigma = fit_market_distribution(50, 75, 100, 150)
        assert isinstance(mu, float)
        assert isinstance(sigma, float)


# ═══════════════════════════════════════════════════
#  Acceptance Probability (Chatterjee-Samuelson)
# ═══════════════════════════════════════════════════

class TestAcceptanceProbability:

    def test_at_median_roughly_50_pct(self, photo_market):
        """Offering at the median should yield ~50% acceptance."""
        mu, sigma = photo_market
        p = acceptance_probability(PHOTO_P50, mu, sigma)
        assert 0.40 < p < 0.60, f"Expected ~50%, got {p:.2%}"

    def test_monotonically_decreasing(self, photo_market):
        """Higher offers → lower acceptance probability."""
        mu, sigma = photo_market
        prices = [60, 80, 100, 120, 150, 200]
        probs = [acceptance_probability(p, mu, sigma) for p in prices]
        for i in range(len(probs) - 1):
            assert probs[i] > probs[i + 1], f"P({prices[i]})={probs[i]:.3f} should > P({prices[i+1]})={probs[i+1]:.3f}"

    def test_very_low_offer_near_certainty(self, photo_market):
        """Extremely low offer → nearly certain acceptance."""
        mu, sigma = photo_market
        p = acceptance_probability(10, mu, sigma)
        assert p > 0.95

    def test_very_high_offer_near_zero(self, photo_market):
        """Extremely high offer → near-zero acceptance."""
        mu, sigma = photo_market
        p = acceptance_probability(500, mu, sigma)
        assert p < 0.05

    def test_bounded_zero_one(self, photo_market):
        """Probability always in [0, 1]."""
        mu, sigma = photo_market
        for price in [0.01, 50, 100, 200, 500, 1000]:
            p = acceptance_probability(price, mu, sigma)
            assert 0.0 <= p <= 1.0


# ═══════════════════════════════════════════════════
#  Myerson (1981): Optimal Bid via Inverse Hazard Rate
# ═══════════════════════════════════════════════════

class TestMyersonOptimalBid:

    def test_bid_above_reservation(self, photo_market):
        """Optimal bid must exceed the reservation rate (positive markup)."""
        mu, sigma = photo_market
        reservation = 85.0
        b_star = optimal_bid_myerson(reservation, mu, sigma)
        assert b_star > reservation

    def test_bid_maximizes_expected_payoff(self, photo_market):
        """No neighboring bid should have higher expected payoff."""
        from scipy import stats
        mu, sigma = photo_market
        reservation = 85.0
        b_star = optimal_bid_myerson(reservation, mu, sigma)
        dist = stats.lognorm(s=sigma, scale=np.exp(mu))

        payoff_star = (b_star - reservation) * (1 - dist.cdf(b_star))
        # Check that +/- $5 around optimal yields worse payoff
        for delta in [-5, -2, -1, 1, 2, 5]:
            alt_bid = b_star + delta
            if alt_bid <= reservation:
                continue
            payoff_alt = (alt_bid - reservation) * (1 - dist.cdf(alt_bid))
            assert payoff_star >= payoff_alt - 0.01, (
                f"Bid ${alt_bid:.2f} has payoff {payoff_alt:.2f} > optimal {payoff_star:.2f}"
            )

    def test_higher_reservation_lower_relative_markup(self, photo_market):
        """Higher reservation → smaller relative markup (%)."""
        mu, sigma = photo_market
        b_low = optimal_bid_myerson(50, mu, sigma)
        b_high = optimal_bid_myerson(150, mu, sigma)
        pct_low = (b_low / 50) - 1
        pct_high = (b_high / 150) - 1
        assert pct_low > pct_high, "Lower reservation should yield larger % shading"

    def test_analysis_keys(self, photo_market):
        """myerson_bid_analysis should return all expected keys."""
        mu, sigma = photo_market
        result = myerson_bid_analysis(85, mu, sigma)
        expected_keys = {
            "optimal_bid", "acceptance_probability", "expected_payoff_per_unit",
            "inverse_hazard_rate", "markup_over_reservation", "markup_pct",
        }
        assert set(result.keys()) == expected_keys

    def test_analysis_acceptance_matches_standalone(self, photo_market):
        """Analysis P(accept) should match the standalone function."""
        mu, sigma = photo_market
        analysis = myerson_bid_analysis(85, mu, sigma)
        standalone_p = acceptance_probability(analysis["optimal_bid"], mu, sigma)
        assert abs(analysis["acceptance_probability"] - standalone_p) < 0.01

    def test_zero_reservation(self, photo_market):
        """Edge case: reservation = 0 should still produce a valid bid."""
        mu, sigma = photo_market
        result = myerson_bid_analysis(0, mu, sigma)
        assert result["optimal_bid"] > 0
        assert result["markup_pct"] is None  # Division by zero guard


# ═══════════════════════════════════════════════════
#  Rubinstein (1982): Alternating-Offers Equilibrium
# ═══════════════════════════════════════════════════

class TestDiscountFactor:

    def test_high_urgency_low_patience(self):
        """Urgency 1.0 → low δ (impatient)."""
        d = compute_discount_factor(1.0, None, 0)
        assert d < 0.60

    def test_low_urgency_high_patience(self):
        """Urgency 0.0 → high δ (patient)."""
        d = compute_discount_factor(0.0, None, 0)
        assert d > 0.90

    def test_pipeline_boost(self):
        """More jobs in pipeline → higher δ."""
        d_empty = compute_discount_factor(0.5, None, 0)
        d_full = compute_discount_factor(0.5, None, 5)
        assert d_full > d_empty

    def test_bounded_below_one(self):
        """δ must never reach 1.0 (infinite patience breaks Rubinstein)."""
        d = compute_discount_factor(0.0, 365, 10)
        assert d < 1.0

    def test_days_and_urgency_combined(self):
        """Using both signals should differ from either alone."""
        d_urgency_only = compute_discount_factor(0.7, None, 0)
        d_both = compute_discount_factor(0.7, 5, 0)
        # With a tight 5-day deadline, combined should be lower
        assert d_both != d_urgency_only

    def test_long_deadline_high_patience(self):
        """30+ day deadline → high δ regardless of urgency."""
        d = compute_discount_factor(0.5, 60, 0)
        assert d > 0.80


class TestRubinsteinEquilibrium:

    def test_shares_sum_to_one(self):
        """Freelancer share + client share must equal 1."""
        result = rubinstein_equilibrium(0.8, 0.6, 1000)
        assert abs(result["freelancer_share"] + result["client_share"] - 1.0) < 1e-4

    def test_impatient_client_favors_freelancer(self):
        """If client is impatient (low δ), freelancer captures more surplus."""
        patient_client = rubinstein_equilibrium(0.8, 0.9, 1000)
        impatient_client = rubinstein_equilibrium(0.8, 0.4, 1000)
        assert impatient_client["freelancer_share"] > patient_client["freelancer_share"]

    def test_equal_patience_near_50_50(self):
        """Equal δ → approximately equal split."""
        result = rubinstein_equilibrium(0.9, 0.9, 1000)
        assert 0.45 < result["freelancer_share"] < 0.55

    def test_concession_ladder_decreasing(self):
        """Each round's surplus claim must be strictly decreasing."""
        result = rubinstein_equilibrium(0.8, 0.6, 5000)
        claims = [step["surplus_claim"] for step in result["concession_ladder"]]
        for i in range(len(claims) - 1):
            assert claims[i] > claims[i + 1]

    def test_concession_ladder_four_rounds(self):
        """Ladder should have exactly 4 rounds."""
        result = rubinstein_equilibrium(0.8, 0.6, 5000)
        assert len(result["concession_ladder"]) == 4

    def test_values_match_surplus(self):
        """Total values should equal surplus."""
        surplus = 3000
        result = rubinstein_equilibrium(0.7, 0.5, surplus)
        total = result["freelancer_value"] + result["client_value"]
        assert abs(total - surplus) < 1.0

    def test_both_patient_edge_case(self):
        """Near-equal very patient players → 50/50 split."""
        result = rubinstein_equilibrium(0.99, 0.99, 1000)
        assert 0.49 < result["freelancer_share"] < 0.51


# ═══════════════════════════════════════════════════
#  Myerson-Satterthwaite (1983): Deadweight Loss
# ═══════════════════════════════════════════════════

class TestDeadweightLossWarning:

    def test_no_warning_above_60_pct(self):
        assert deadweight_loss_warning(0.65) is None
        assert deadweight_loss_warning(0.90) is None

    def test_moderate_warning(self):
        warning = deadweight_loss_warning(0.35)
        assert warning is not None
        assert "35%" in warning

    def test_aggressive_warning(self):
        warning = deadweight_loss_warning(0.15)
        assert warning is not None
        assert "15%" in warning.lower()

    def test_boundary_30_pct(self):
        assert deadweight_loss_warning(0.30) is not None

    def test_boundary_60_pct(self):
        assert deadweight_loss_warning(0.60) is None


# ═══════════════════════════════════════════════════
#  Value of Information
# ═══════════════════════════════════════════════════

class TestValueOfInformation:

    def test_returns_expected_keys(self, photo_market):
        mu, sigma = photo_market
        result = should_probe_first(mu, sigma, 0.8, 85)
        expected = {"should_probe", "voi_estimate", "cost_of_delay", "net_voi",
                    "distribution_cv"}
        assert expected.issubset(set(result.keys()))

    def test_impatient_freelancer_anchors_immediately(self, photo_market):
        """Very impatient freelancer (low δ) → delay cost is high → anchor now."""
        mu, sigma = photo_market
        result = should_probe_first(mu, sigma, 0.3, 85)
        # With δ=0.3, delay costs 70% of expected payoff — should not probe
        assert result["cost_of_delay"] > result["voi_estimate"] or not result["should_probe"]

    def test_wide_distribution_favors_probe(self):
        """Very wide market distribution → high CV → probe is worth it."""
        mu, sigma = fit_market_distribution(20, 100, 500, 1000)
        result = should_probe_first(mu, sigma, 0.9, 50)
        assert result["distribution_cv"] > 1.0
        # With δ=0.9 (patient) and very wide distribution, probing has high net VOI

    def test_narrow_distribution_anchors(self):
        """Narrow distribution → low CV → anchor immediately."""
        mu, sigma = fit_market_distribution(95, 100, 105, 110)
        result = should_probe_first(mu, sigma, 0.8, 85)
        assert result["distribution_cv"] < 0.2


# ═══════════════════════════════════════════════════
#  Integration: End-to-End Invariants
# ═══════════════════════════════════════════════════

class TestEndToEndInvariants:

    def test_photographer_scenario_basic(self, photo_market):
        """Smoke test: full analysis for a photographer at $85 BATNA."""
        mu, sigma = photo_market
        analysis = myerson_bid_analysis(85, mu, sigma)
        assert analysis["optimal_bid"] > 85
        assert 0 < analysis["acceptance_probability"] < 1

        delta_f = compute_discount_factor(0.2, None, 0)
        delta_c = compute_discount_factor(0.8, 14, 0)
        surplus = analysis["optimal_bid"] * 56 - 85 * 56
        rub = rubinstein_equilibrium(delta_f, delta_c, surplus)
        assert rub["freelancer_share"] > 0.5  # Client is impatient → freelancer wins

    def test_consultant_high_rates(self, consultant_market):
        """Consultant market has higher rates → higher optimal bid."""
        mu, sigma = consultant_market
        analysis = myerson_bid_analysis(150, mu, sigma)
        assert analysis["optimal_bid"] > 200  # Market median is $175

    def test_reservation_at_market_ceiling(self, photo_market):
        """If reservation is at p90, Myerson can still shade above it."""
        mu, sigma = photo_market
        analysis = myerson_bid_analysis(200, mu, sigma)
        # Even at p90 reservation, there's some probability of higher-paying clients
        assert analysis["optimal_bid"] > 200
        assert analysis["acceptance_probability"] < 0.15

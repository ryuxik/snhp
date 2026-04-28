"""
Tests for market_intel.py, history_store.py, and mcp_server.py deterministic logic.

These test the non-LLM layers: keyword matching, history analytics,
and the bounds computation / field validation in the MCP server.
"""

import pytest
import json
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intel import match_category, get_market_rates, compute_leverage_factor
from history_store import (
    HistoryBackend, LocalJsonBackend, set_backend,
    get_past_contracts, add_contract, compute_historical_stats,
    get_profile, set_profile,
)
from snhp.sdk import compute_freelancer_bounds, check_missing_freelancer_fields


# ═══════════════════════════════════════════════════
#  Market Intel: Category Matching
# ═══════════════════════════════════════════════════

class TestMatchCategory:

    def test_photographer_keywords(self):
        cat = match_category("We need a campaign shoot", "I am a photographer")
        assert cat == "photographer"

    def test_web_developer_keywords(self):
        cat = match_category("build us a react website", "I'm a fullstack developer")
        assert cat == "web_developer"

    def test_copywriter_keywords(self):
        cat = match_category("We need blog content and captions", "I am a writer")
        assert cat == "copywriter"

    def test_no_match_returns_best_effort(self):
        """Even vague text returns the best match (never crashes)."""
        cat = match_category("Hi", "constraints")
        # Should return something or None — shouldn't crash
        assert cat is None or isinstance(cat, str)

    def test_combined_text_scoring(self):
        """Keywords from both inputs should contribute to score."""
        cat = match_category("campaign shoot for spring", "photographer editorial lookbook")
        assert cat == "photographer"


class TestGetMarketRates:

    def test_valid_category(self):
        rates = get_market_rates("photographer")
        assert rates is not None
        assert "hourly" in rates
        assert rates["hourly"]["median"] == 95

    def test_invalid_category(self):
        rates = get_market_rates("nonexistent_category")
        assert rates is None

    def test_all_categories_have_required_fields(self):
        """Every category in market_data.json must have all percentile keys."""
        data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "market_data.json")
        with open(data_path) as f:
            data = json.load(f)
        for key, cat in data["categories"].items():
            assert "hourly" in cat, f"{key} missing hourly"
            for p in ["p25", "median", "p75", "p90"]:
                assert p in cat["hourly"], f"{key} missing hourly.{p}"
            assert "keywords" in cat, f"{key} missing keywords"
            assert len(cat["keywords"]) > 0, f"{key} has empty keywords"


class TestComputeLeverageFactor:

    def test_zero_urgency_zero_pipeline(self):
        factor = compute_leverage_factor(0.0, 0, 100, 100, 140)
        assert factor == 0.0

    def test_max_urgency_premium(self):
        factor = compute_leverage_factor(1.0, 0, 100, 100, 140)
        assert factor <= 0.15 + 1e-4

    def test_pipeline_premium(self):
        f0 = compute_leverage_factor(0.0, 0, 100, 100, 140)
        f3 = compute_leverage_factor(0.0, 3, 100, 100, 140)
        assert f3 > f0

    def test_above_median_market_premium(self):
        factor = compute_leverage_factor(0.0, 0, 150, 100, 140)
        assert factor > 0  # Above-median freelancer gets market premium

    def test_below_median_no_penalty(self):
        factor = compute_leverage_factor(0.0, 0, 80, 100, 140)
        assert factor == 0.0  # No negative penalty

    def test_capped_at_50_pct(self):
        factor = compute_leverage_factor(1.0, 10, 300, 100, 140)
        assert factor <= 0.50


# ═══════════════════════════════════════════════════
#  History Store
# ═══════════════════════════════════════════════════

class TestHistoryStore:

    @pytest.fixture(autouse=True)
    def use_temp_backend(self, tmp_path):
        """Create a temp JSON backend for each test."""
        import history_store as hs
        old_dir = hs.SNHP_DIR
        old_file = hs.HISTORY_FILE
        hs.SNHP_DIR = str(tmp_path)
        hs.HISTORY_FILE = str(tmp_path / "history.json")
        set_backend(LocalJsonBackend())
        yield
        hs.SNHP_DIR = old_dir
        hs.HISTORY_FILE = old_file
        set_backend(LocalJsonBackend())

    def test_empty_history_stats(self):
        stats = compute_historical_stats()
        assert stats["count"] == 0
        assert stats["avg_hourly"] is None
        assert stats["active_pipeline"] == 0

    def test_add_and_retrieve_contract(self):
        add_contract({"hourly_rate": 100, "total_value": 5000, "client": "TestCo"})
        contracts = get_past_contracts()
        assert len(contracts) == 1
        assert contracts[0]["hourly_rate"] == 100

    def test_historical_stats_with_data(self):
        add_contract({"hourly_rate": 100, "total_value": 5000})
        add_contract({"hourly_rate": 120, "total_value": 6000})
        stats = compute_historical_stats()
        assert stats["count"] == 2
        assert stats["avg_hourly"] == 110.0
        assert stats["max_hourly"] == 120
        assert stats["min_hourly"] == 100
        assert stats["avg_total"] == 5500.0

    def test_profile_round_trip(self):
        set_profile({"active_pipeline": 3, "specialty": "photographer"})
        profile = get_profile()
        assert profile["active_pipeline"] == 3

    def test_trend_calculation(self):
        """Need ≥6 contracts for trend."""
        for rate in [80, 85, 90, 100, 110, 120]:
            add_contract({"hourly_rate": rate, "total_value": rate * 40})
        stats = compute_historical_stats()
        assert stats["trend_pct"] is not None
        assert stats["trend_pct"] > 0  # Rates are increasing


# ═══════════════════════════════════════════════════
#  MCP Server: Bounds & Validation
# ═══════════════════════════════════════════════════

class TestComputeFreelancerBounds:

    def test_hourly_with_daily_hours(self):
        ext = {
            "hourly_rate": 100,
            "max_hours_per_day": 4,
            "duration_days": 14,
            "max_duration_days": 21,
            "revisions": 1,
            "max_revisions": 3,
            "hourly_batna": 85,
        }
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 100 * 4 * 14  # 5600
        assert bounds["min_price"] == 85 * 4 * 14  # 4760
        assert bounds["total_hours"] == 4 * 14  # 56

    def test_total_budget_override(self):
        """total_budget should take precedence over computed hourly × hours."""
        ext = {"total_budget": 8000, "hourly_rate": 100, "max_hours_per_day": 4,
               "duration_days": 14, "hourly_batna": 85, "max_duration_days": 21,
               "revisions": 1, "max_revisions": 3}
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 8000

    def test_missing_hours_math(self):
        """If no hours info, ideal_price should be None."""
        ext = {"hourly_rate": 100}
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] is None

    def test_max_hours_total_path(self):
        ext = {"hourly_rate": 100, "max_hours_total": 40, "hourly_batna": 80,
               "duration_days": 10, "max_duration_days": 15,
               "revisions": 2, "max_revisions": 4}
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 100 * 40
        assert bounds["min_price"] == 80 * 40
        assert bounds["total_hours"] == 40


class TestCheckMissingFields:

    def test_all_present(self):
        bounds = {
            "ideal_price": 5600, "min_price": 4760,
            "ideal_days": 14, "max_days": 21,
            "ideal_revisions": 1, "max_revisions": 3,
        }
        assert check_missing_freelancer_fields(bounds) == []

    def test_missing_everything(self):
        bounds = {
            "ideal_price": None, "min_price": None,
            "ideal_days": None, "max_days": None,
            "ideal_revisions": None, "max_revisions": None,
        }
        missing = check_missing_freelancer_fields(bounds)
        assert len(missing) == 2  # only ideal_price and min_price are checked

    def test_partial_missing(self):
        bounds = {
            "ideal_price": 5600, "min_price": None,
            "ideal_days": 14, "max_days": None,
            "ideal_revisions": 1, "max_revisions": 3,
        }
        missing = check_missing_freelancer_fields(bounds)
        assert len(missing) == 1
        assert "walk-away" in missing[0]


# ═══════════════════════════════════════════════════
#  Cross-Module Integration Invariants
# ═══════════════════════════════════════════════════

class TestCrossModuleIntegration:

    def test_market_rates_feed_game_theory(self):
        """Market rates from JSON should produce valid game theory inputs."""
        from snhp.market.priors import fit_market_distribution
        from snhp.core_math.bayesian import myerson_bid_analysis
        rates = get_market_rates("photographer")
        h = rates["hourly"]
        mu, sigma = fit_market_distribution(h["p25"], h["median"], h["p75"], h["p90"])
        analysis = myerson_bid_analysis(85, mu, sigma)
        assert analysis["optimal_bid"] > 85
        assert 0 < analysis["acceptance_probability"] < 1

    def test_all_categories_produce_valid_distributions(self):
        """Every market category should yield a sane log-normal distribution."""
        from snhp.market.priors import fit_market_distribution
        from snhp.core_math.bayesian import acceptance_probability
        data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "market_data.json")
        with open(data_path) as f:
            data = json.load(f)
        for key, cat in data["categories"].items():
            h = cat["hourly"]
            mu, sigma = fit_market_distribution(h["p25"], h["median"], h["p75"], h["p90"])
            # Acceptance at median should be ~50%
            p_median = acceptance_probability(h["median"], mu, sigma)
            assert 0.35 < p_median < 0.65, f"{key}: P(accept@median)={p_median:.2f}"

"""
SNHP Phase 2: Per-Bridge End-to-End Pipeline Tests

Tests each bridge independently:
  Bridge 1: LLM Extraction (email → structured params)
  Bridge 2: Game Theory Engine (params → optimal numbers)
  Bridge 3: Response Formatter (numbers → human output)

Plus 5 golden-path integration tests: raw email → final output.
"""
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snhp.models import SNHPResponse, ConcessionStep
from snhp.sdk import compute_freelancer_bounds, check_missing_freelancer_fields, run_path_a
from snhp.game_theory import calculate_optimal_counter
from snhp.formatters import format_markdown


# ──────── Bridge 1: Extraction Tests (Mocked — no LLM) ──────────

class TestBridge1Extraction:
    """Test that compute_freelancer_bounds correctly derives bounds from extracted params."""

    def test_hourly_rate_with_hours(self):
        ext = {
            "hourly_rate": 100,
            "max_hours_per_day": 5,
            "duration_days": 14,
            "hourly_batna": 75,
            "revisions": 2,
            "max_revisions": 4,
        }
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 100 * 5 * 14  # $7000
        assert bounds["min_price"] == 75 * 5 * 14  # $5250
        assert bounds["total_hours"] == 70
        assert bounds["ideal_revisions"] == 2
        assert bounds["max_revisions"] == 4

    def test_total_budget_flat_fee(self):
        ext = {
            "total_budget": 5000,
            "minimum_batna_price": 3500,
        }
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 5000
        assert bounds["min_price"] == 3500
        assert bounds["total_hours"] is None  # flat fee mode

    def test_min_price_fallback(self):
        """When no BATNA, min_price should default to 80% of ideal."""
        ext = {"total_budget": 5000}
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 5000
        assert bounds["min_price"] == 4000  # 80% fallback

    def test_missing_fields_detection(self):
        bounds = {"ideal_price": None, "min_price": None}
        missing = check_missing_freelancer_fields(bounds)
        assert len(missing) == 2
        assert "rate" in missing[0].lower() or "budget" in missing[0].lower()

    def test_complete_fields_no_missing(self):
        bounds = {"ideal_price": 5000, "min_price": 3500}
        missing = check_missing_freelancer_fields(bounds)
        assert len(missing) == 0

    def test_payment_terms_passthrough(self):
        ext = {
            "hourly_rate": 100,
            "max_hours_total": 40,
            "preferred_payment_days": 15,
        }
        bounds = compute_freelancer_bounds(ext)
        assert bounds["preferred_payment_days"] == 15

    def test_max_hours_total_path(self):
        ext = {
            "hourly_rate": 80,
            "max_hours_total": 50,
            "hourly_batna": 60,
        }
        bounds = compute_freelancer_bounds(ext)
        assert bounds["ideal_price"] == 4000  # 80 * 50
        assert bounds["min_price"] == 3000  # 60 * 50
        assert bounds["total_hours"] == 50


# ──────── Bridge 2: Game Theory Engine Tests ──────────

class TestBridge2GameTheory:
    """Test the math engine with known-correct extracted inputs."""

    def test_basic_counter_offer(self):
        free_bounds = {
            "ideal_price": 7000,
            "min_price": 5000,
            "hourly_rate": 100,
            "hourly_batna": 75,
            "total_hours": 70,
            "ideal_days": 14,
            "max_days": 21,
            "ideal_revisions": 2,
            "max_revisions": 4,
        }
        client_constraints = {
            "explicit_budget": 5000,
            "timeline_days": 7,
            "urgency_score": 0.7,
            "is_competitive_bid": False,
        }
        result = calculate_optimal_counter(
            free_bounds=free_bounds,
            client_constraints=client_constraints,
            market_data=None,
            historical_avg=None,
            pipeline_count=0,
        )
        
        # Must have all required output keys
        assert "optimal_anchor" in result
        assert "total_project_quote" in result
        assert "target_days" in result
        assert "target_revisions" in result
        assert "concession_ladder" in result
        assert "minimum_batna_total" in result
        
        # Optimal anchor must be above BATNA
        assert result["total_project_quote"] >= free_bounds["min_price"]
        # Concession ladder must have steps
        assert len(result["concession_ladder"]) > 0

    def test_flat_fee_mode(self):
        free_bounds = {
            "ideal_price": 5000,
            "min_price": 3500,
            "hourly_rate": None,
            "total_hours": None,
        }
        client_constraints = {
            "explicit_budget": None,
            "timeline_days": None,
            "urgency_score": 0.5,
            "is_competitive_bid": False,
        }
        result = calculate_optimal_counter(
            free_bounds=free_bounds,
            client_constraints=client_constraints,
            market_data=None,
            historical_avg=None,
            pipeline_count=0,
        )
        assert result["estimated_total_hours"] is None
        assert result["total_project_quote"] >= free_bounds["min_price"]

    def test_high_urgency_affects_anchor(self):
        """Higher client urgency should lead to a stronger freelancer position."""
        base_constraints = {
            "explicit_budget": None,
            "timeline_days": 3,
            "is_competitive_bid": False,
        }
        free_bounds = {
            "ideal_price": 5000,
            "min_price": 3000,
            "hourly_rate": 100,
            "hourly_batna": 60,
            "total_hours": 50,
        }
        
        low_urgency = calculate_optimal_counter(
            free_bounds=free_bounds,
            client_constraints={**base_constraints, "urgency_score": 0.2},
            market_data=None, historical_avg=None, pipeline_count=0,
        )
        high_urgency = calculate_optimal_counter(
            free_bounds=free_bounds,
            client_constraints={**base_constraints, "urgency_score": 0.9},
            market_data=None, historical_avg=None, pipeline_count=0,
        )
        
        # Higher urgency → freelancer can charge more (or at least equal)
        assert high_urgency["total_project_quote"] >= low_urgency["total_project_quote"] * 0.95


# ──────── Bridge 3: Formatter Tests ──────────

class TestBridge3Formatter:
    """Test the markdown formatter with known-correct SNHPResponse objects."""

    def test_nash_path_format(self):
        response = SNHPResponse(
            is_complete=True,
            path_taken="Nash",
            optimal_anchor=5500,
            target_days=14,
            target_revisions=3,
            total_project_quote=5500,
            draft_email="I'd be happy to take this on at $5,500.",
        )
        output = format_markdown(response)
        assert "$5,500.00" in output
        assert "14 days" in output
        assert "3 rounds" in output
        assert "I'd be happy to take this on" in output

    def test_nash_with_payment_terms(self):
        response = SNHPResponse(
            is_complete=True,
            path_taken="Nash",
            optimal_anchor=5500,
            target_days=14,
            target_revisions=3,
            target_payment_days=15,
            total_project_quote=5500,
            draft_email="Deal terms attached.",
        )
        output = format_markdown(response)
        assert "net-15" in output
        assert "Payment Terms" in output

    def test_nash_upon_completion(self):
        response = SNHPResponse(
            is_complete=True,
            path_taken="Nash",
            optimal_anchor=3000,
            target_days=7,
            target_revisions=2,
            target_payment_days=0,
            total_project_quote=3000,
            draft_email="Ready to start.",
        )
        output = format_markdown(response)
        assert "upon completion" in output

    def test_incomplete_response(self):
        response = SNHPResponse(
            is_complete=False,
            missing_fields=["your ideal rate or total budget"],
        )
        output = format_markdown(response)
        assert "need a bit more info" in output
        assert "rate" in output.lower() or "budget" in output.lower()

    def test_rubinstein_path_format(self):
        response = SNHPResponse(
            is_complete=True,
            path_taken="Rubinstein",
            optimal_anchor=95.0,
            target_days=14,
            target_revisions=2,
            total_project_quote=4750,
            estimated_total_hours=50,
            acceptance_probability=0.65,
            market_median=85.0,
            market_high=106.0,
            should_probe=False,
            deadweight_warning=False,
            concession_ladder=[
                ConcessionStep(label="If they reject", amount=4500),
                ConcessionStep(label="If they push back", amount=4250),
            ],
            minimum_batna_total=3500,
            draft_email="Here's my proposal.",
        )
        output = format_markdown(response)
        assert "$95.00/hr" in output
        assert "$4,750.00" in output
        assert "65%" in output
        assert "WALK AWAY" in output
        assert "3,500.00" in output

    def test_delta_capture_display(self):
        response = SNHPResponse(
            is_complete=True,
            path_taken="Nash",
            optimal_anchor=5000,
            target_days=14,
            target_revisions=2,
            total_project_quote=5000,
            client_opening_anchor=3000,
            surplus_delta=2000,
            delta_capture_toll=200,
            draft_email="Let's do this.",
        )
        output = format_markdown(response)
        assert "Delta Capture" in output
        assert "$200.00" in output
        assert "$2,000.00" in output


# ──────── Golden Path Integration Tests (Mocked Extraction) ──────────

class TestGoldenPathIntegration:
    """Full pipeline: known extraction → game theory → formatted output."""

    def _run_pipeline(self, free_extracted, client_constraints, opp_utility):
        """Helper: run Bridge 2 + Bridge 3 with mocked Bridge 1 output."""
        free_bounds = compute_freelancer_bounds(free_extracted)
        
        # Bridge 2: Math engine (Path B since we test without Nash grid for simplicity)
        result = calculate_optimal_counter(
            free_bounds=free_bounds,
            client_constraints=client_constraints,
            market_data=None,
            historical_avg=None,
            pipeline_count=0,
        )
        
        # Build SNHPResponse
        response = SNHPResponse(
            is_complete=True,
            path_taken="Rubinstein",
            optimal_anchor=result["optimal_anchor"],
            target_days=result["target_days"],
            target_revisions=result["target_revisions"],
            total_project_quote=result["total_project_quote"],
            estimated_total_hours=result["estimated_total_hours"],
            acceptance_probability=result["acceptance_probability"],
            market_median=result["market_median"],
            market_high=result["market_median"] * 1.25,
            should_probe=result["should_probe"],
            deadweight_warning=result["deadweight_warning"],
            concession_ladder=[
                ConcessionStep(label=f"Counter {i+1}", amount=free_bounds["min_price"] + s["surplus_claim"])
                for i, s in enumerate(result["concession_ladder"])
            ],
            minimum_batna_total=free_bounds["min_price"],
            draft_email="[mocked draft]",
        )
        
        # Bridge 3: Format
        output = format_markdown(response)
        return response, output

    def test_golden_1_web_developer(self):
        """Standard web dev: $100/hr, 5hr/day, 2 weeks, min $60/hr."""
        resp, output = self._run_pipeline(
            free_extracted={"hourly_rate": 100, "max_hours_per_day": 5, "duration_days": 14, "hourly_batna": 60, "revisions": 2, "max_revisions": 5},
            client_constraints={"explicit_budget": 3000, "timeline_days": 7, "urgency_score": 0.7, "is_competitive_bid": False},
            opp_utility={"price_weight": 0.7, "speed_weight": 0.1, "revisions_weight": 0.2, "batna_threshold": 0.6},
        )
        assert resp.is_complete
        assert resp.total_project_quote >= 4200  # min_price = 60*5*14 = 4200
        assert "Opening" in output

    def test_golden_2_flat_fee_design(self):
        """Flat-fee logo design: $2500 ideal, $1800 minimum."""
        resp, output = self._run_pipeline(
            free_extracted={"total_budget": 2500, "minimum_batna_price": 1800},
            client_constraints={"explicit_budget": None, "timeline_days": None, "urgency_score": 0.3, "is_competitive_bid": False},
            opp_utility={"price_weight": 0.8, "speed_weight": 0.1, "revisions_weight": 0.1, "batna_threshold": 0.5},
        )
        assert resp.is_complete
        assert resp.total_project_quote >= 1800

    def test_golden_3_high_urgency_consulting(self):
        """Urgent consulting: client needs it in 3 days."""
        resp, output = self._run_pipeline(
            free_extracted={"hourly_rate": 200, "max_hours_total": 24, "hourly_batna": 150},
            client_constraints={"explicit_budget": None, "timeline_days": 3, "urgency_score": 0.95, "is_competitive_bid": True},
            opp_utility={"price_weight": 0.5, "speed_weight": 0.3, "revisions_weight": 0.2, "batna_threshold": 0.8},
        )
        assert resp.is_complete
        assert resp.total_project_quote >= 3600  # 150 * 24

    def test_golden_4_competitive_bid_writing(self):
        """Multi-bid scenario: copywriting gig."""
        resp, output = self._run_pipeline(
            free_extracted={"hourly_rate": 75, "max_hours_per_day": 4, "duration_days": 10, "hourly_batna": 50, "revisions": 1, "max_revisions": 3},
            client_constraints={"explicit_budget": 2000, "timeline_days": 10, "urgency_score": 0.5, "is_competitive_bid": True},
            opp_utility={"price_weight": 0.6, "speed_weight": 0.2, "revisions_weight": 0.2, "batna_threshold": 0.65},
        )
        assert resp.is_complete
        assert resp.total_project_quote >= 2000  # min_price = 50*4*10=2000

    def test_golden_5_minimal_info(self):
        """Only total budget provided, no hourly details."""
        resp, output = self._run_pipeline(
            free_extracted={"total_budget": 8000, "minimum_batna_price": 5500},
            client_constraints={"explicit_budget": 6000, "timeline_days": 30, "urgency_score": 0.4, "is_competitive_bid": False},
            opp_utility={"price_weight": 0.7, "speed_weight": 0.15, "revisions_weight": 0.15, "batna_threshold": 0.55},
        )
        assert resp.is_complete
        assert resp.total_project_quote >= 5500


# ──────── Live LLM Test (only runs with --live flag) ──────────

@pytest.mark.skipif(
    "--live" not in sys.argv,
    reason="Live LLM test — run with: pytest tests/test_e2e_pipeline.py --live"
)
class TestLiveLLM:
    """Full pipeline with real LLM extraction — requires API key."""

    def test_live_extraction(self):
        from snhp.llm_extractor import extract_all_parameters
        
        result = extract_all_parameters(
            "Hi, I need a React dashboard built. My budget is $3000 and I need it in 7 days.",
            "I charge $125/hr, can work 5hrs/day for 2 weeks. My absolute minimum total is $1875."
        )
        
        assert result.get("free_hourly_rate") is not None
        assert result.get("client_explicit_budget") is not None
        assert abs(result["free_hourly_rate"] - 125) < 15  # 10% tolerance
        assert abs(result["client_explicit_budget"] - 3000) < 300

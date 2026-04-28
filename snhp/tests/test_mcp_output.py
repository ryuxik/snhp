import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import snhp
import snhp.sdk as sdk

class TestLaymanUXOutput:
    
    def test_run_path_b_layman_rendering(self):
        """
        Ensures that run_path_b successfully executes and returns the 
        expected layman terminology instead of game-theoretic jargon.
        """
        client_email = "We need a logo designed."
        constraints_str = "I want at least $50/hr minimum."
        client_constraints = {
            "urgency_score": 0.5,
            "timeline_days": 14
        }
        free_bounds = {
            "ideal_price": None,
            "min_price": 500,
            "ideal_days": 7,
            "max_days": 14,
            "ideal_revisions": 1,
            "max_revisions": 3,
            "hourly_rate": 80,
            "hourly_batna": 50,
            "total_hours": 10
        }
        free_extracted = {
            "category_hint": "designer"
        }
        
        response = sdk.run_path_b(
            client_email, 
            constraints_str, 
            client_constraints, 
            free_bounds, 
            free_extracted,
            client_anchor=None,
            client_role="seller"
        )
        output = snhp.format_markdown(response)
        
        # Verify execution completed and returned a string
        assert isinstance(output, str)
        print("Output:", output)
        
        # Verify jargon is removed and new layman format is present
        assert "Recommended Action: Opening Offer" in output
        assert "Your Opening Ask" in output
        assert "If they counter-offer or push back, here is your drop strategy:" in output
        assert "If they reject initial quote" in output
        assert "WALK AWAY" in output
        
        # Ensure old jargon is successfully scrubbed
        assert "Rubinstein Concession Ladder" not in output
        assert "Myerson-Optimal" not in output

    def test_run_path_a_layman_rendering(self):
        """
        Ensures that run_path_a renders with the simple Target Deal Structure.
        """
        client_email = "I will pay you exactly $1000 for this project."
        constraints_str = "I want min $500."
        opp_utility = {
            "price_weight": 0.5,
            "speed_weight": 0.3,
            "revisions_weight": 0.2,
            "batna_threshold": 0.1
        }
        free_bounds = {
            "ideal_price": 1200,
            "min_price": 500,
            "ideal_days": 14,
            "max_days": 21,
            "ideal_revisions": 1,
            "max_revisions": 3,
            "hourly_rate": 100,
            "hourly_batna": 50,
            "total_hours": 12
        }
        
        response = sdk.run_path_a(client_email, constraints_str, opp_utility, free_bounds, client_anchor=1000, client_role="seller")
        output = snhp.format_markdown(response)
        
        assert isinstance(output, str)
        
        # Verify layman format
        assert "**Target Deal Structure**" in output
        assert "**Email Draft To Send:**" in output
        
        # Verify old jargon is omitted
        assert "Strategy: Nash Equilibrium Offer" not in output

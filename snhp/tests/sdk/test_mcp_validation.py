import pytest
import sys
import json
from snhp.mcp_server import handle_tools_call

def test_zero_tuning_enforcement():
    params = {
        "name": "snhp_evaluate_negotiation",
        "arguments": {
            "client_email": "hello I need an app",
            "freelancer_constraints": "2000 total",
            "uncertainty_score": 0.2
        }
    }
    
    class MockStdout:
        def __init__(self):
            self.output = ""
        def write(self, s):
            self.output += s
        def flush(self):
            pass
            
    old_out = sys.stdout
    sys.stdout = MockStdout()
    
    try:
        handle_tools_call("123", params)
        out = sys.stdout.output
        
        # Verify JSONRPC valid
        lines = [line for line in out.split("\\n") if line.strip()]
        res = json.loads(lines[-1])
        
        assert res.get("error") is not None
        assert "Zero-Tuning" in res["error"]["message"]
    finally:
        sys.stdout = old_out

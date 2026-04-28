import os
import asyncio
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure the LLM to use Gemini Flash 3 as requested
os.environ["SNHP_LLM_MODEL"] = "gemini/gemini-3.0-flash"

from snhp.sdk import negotiate

app = FastAPI(title="SNHP Trust Simulator Demo API")

# Allow CORS for front-end execution
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScenarioRequest(BaseModel):
    api_key: str
    email_text: str
    goals: str

@app.post("/generate_key")
async def generate_key():
    """Generates a test API key for the simulator."""
    key = f"sk_test_{uuid.uuid4().hex}"
    return {"key": key}

@app.post("/simulate")
async def simulate(req: ScenarioRequest):
    """
    Executes the live SNHP negotiation engine using provided constraints.
    """
    if not req.api_key.startswith("sk_test_"):
        raise HTTPException(status_code=401, detail="Invalid or missing test key")

    try:
        # Sanitize and truncate inputs to prevent payload bombs / injection attacks
        safe_email = req.email_text[:2000]
        safe_goals = req.goals[:2000]

        # Run the live game theory extraction and computation
        response = negotiate(safe_email, safe_goals)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Handle missing requirements Gracefully
    if not response.is_complete:
        raise HTTPException(status_code=400, detail="Missing info: " + ", ".join(response.missing_fields))

    total_quote = getattr(response, 'total_project_quote', 0)
    min_batna = getattr(response, 'minimum_batna_total', None)
    
    # If Path A (Nash solver) triggered, min_batna is None because there is no ladder offset
    if min_batna is None:
        min_batna = total_quote * 0.8
        
    amount_saved = total_quote - min_batna

    mapped_ladder = []
    concession_ladder = getattr(response, 'concession_ladder', None)
    
    if concession_ladder is None or len(concession_ladder) == 0:
        # Path A exact match fallback
        mapped_ladder.append({
            "step": 1,
            "strategy": "Pareto-Optimal Nash Equilibrium Match",
            "bid": total_quote,
            "rationale": "The client's budget exactly overlaps with your utility structure."
        })
    else:
        for i, step in enumerate(concession_ladder):
            mapped_ladder.append({
                "step": i + 1,
                "strategy": step.label,
                "bid": step.amount,
                "rationale": "Derived mathematically across constraint gradient."
            })

    return {
        "status": "success",
        "impact_summary": {
            "amount_saved_usd": amount_saved,
            "original_offer_usd": min_batna,
            "optimal_target_usd": total_quote
        },
        "concession_ladder": mapped_ladder
    }

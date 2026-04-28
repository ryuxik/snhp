import os
import sys
import json
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv('../.env')

# ─── Try native Google GenAI SDK first, litellm as fallback ───

_genai_client = None
try:
    from google import genai
    from google.genai import types as genai_types
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        _genai_client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=45000)  # 45s timeout
        )
except ImportError:
    genai = None

try:
    from litellm import completion
    import litellm
except ImportError:
    completion = None


# ─── Combined Extraction Schema ───

class CombinedExtraction(BaseModel):
    """Unified schema to extract all parameters in a single LLM pass."""
    opp_utility_price_weight: float = Field(description="The mathematical weight for Price (0.0 to 1.0)")
    opp_utility_speed_weight: float = Field(description="The mathematical weight for Delivery Timeline/Speed (0.0 to 1.0)")
    opp_utility_revisions_weight: float = Field(description="The mathematical weight for Scope/Revisions (0.0 to 1.0)")
    opp_utility_batna_threshold: float = Field(description="The absolute bottom line utility drop-dead threshold below which the client walks away (0.0 to 1.0)")
    
    client_explicit_budget: Optional[float] = Field(description="The explicit total project budget the client stated, if any.", default=None)
    client_explicit_hourly_rate: Optional[float] = Field(description="The explicit hourly rate the client offered, if any.", default=None)
    client_timeline_days: Optional[int] = Field(description="The number of days the client stated for delivery, if any.", default=None)
    client_max_revisions: Optional[int] = Field(description="The max revisions the client stated, if any.", default=None)
    client_urgency_score: float = Field(description="How urgent is the client's request? 0.0 = completely relaxed. 1.0 = extremely urgent.")
    client_is_competitive_bid: bool = Field(description="Does the email imply the client is talking to multiple freelancers or comparing bids? true/false.", default=False)
    
    free_hourly_rate: Optional[float] = Field(description="The desired hourly rate in absolute numbers, if mentioned.", default=None)
    free_total_budget: Optional[float] = Field(description="The total project budget in absolute numbers, if mentioned.", default=None)
    free_duration_days: Optional[int] = Field(description="The ideal or total duration spanning the project in days, if mentioned.", default=None)
    free_max_duration_days: Optional[int] = Field(description="The absolute maximum tolerable project duration in days, if mentioned.", default=None)
    free_max_hours_per_day: Optional[float] = Field(description="The maximum hours per day the freelancer can work, if mentioned.", default=None)
    free_max_hours_total: Optional[float] = Field(description="The total maximum hours the freelancer wants to work, if mentioned.", default=None)
    free_revisions: Optional[int] = Field(description="The ideal number of revisions desired, if mentioned.", default=None)
    free_max_revisions: Optional[int] = Field(description="The absolute maximum number of revisions tolerable, if mentioned.", default=None)
    free_minimum_batna_price: Optional[float] = Field(description="The absolute total minimum acceptable project price (BATNA), if mentioned.", default=None)
    free_hourly_batna: Optional[float] = Field(description="The minimum acceptable hourly rate (BATNA), if mentioned.", default=None)
    free_category_hint: Optional[str] = Field(description="The freelancer's professional category if mentioned or inferable.", default=None)
    
    # Payment Terms (4th dimension)
    client_payment_terms_days: Optional[int] = Field(description="The payment terms the client proposed in days (e.g., net-30 = 30, net-15 = 15, upon completion = 0).", default=None)
    free_preferred_payment_days: Optional[int] = Field(description="The freelancer's preferred payment terms in days (e.g., net-15 = 15, 50% upfront = 0).", default=None)

# ─── Extraction Functions (LLM extraction only, no math) ───

def _call_gemini_native(prompt: str, schema=None, temperature: float = 0.0):
    """Call Gemini via native Google GenAI SDK — fast, reliable, proper timeout."""
    model_name = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
    # Strip the "gemini/" prefix for native SDK
    model_id = model_name.replace("gemini/", "")
    
    config = {"temperature": temperature}
    
    if schema:
        schema_dump = json.dumps(schema.model_json_schema()) if hasattr(schema, "model_json_schema") else str(schema)
        prompt += f"\n\nYou MUST return ONLY a raw JSON object (without markdown wrappers) matching this schema structure:\n{schema_dump}"
        config["response_mime_type"] = "application/json"
    
    response = _genai_client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=config,
    )
    
    content = response.text
    if schema:
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content) if content else {}
    return content.strip() if content else ""


def _call_litellm(prompt: str, schema=None, temperature: float = 0.0):
    """Fallback: call any LLM via litellm."""
    if completion is None:
        raise RuntimeError("litellm is required. Run `pip install litellm`")
        
    model_name = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
    litellm.suppress_debug_info = True

    kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if schema:
        schema_dump = json.dumps(schema.model_json_schema()) if hasattr(schema, "model_json_schema") else str(schema)
        prompt += f"\n\nYou MUST return ONLY a raw JSON object (without markdown wrappers) matching this schema structure:\n{schema_dump}"
        kwargs["messages"][0]["content"] = prompt
        kwargs["response_format"] = {"type": "json_object"}

    response = completion(**kwargs)
    content = response.choices[0].message.content
    if schema:
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content) if content else {}
    return content.strip() if content else ""


def _call_llm(prompt: str, schema=None, temperature: float = 0.0):
    """Route to native Gemini SDK or litellm fallback."""
    model_name = os.environ.get("SNHP_LLM_MODEL", "gemini/gemini-3-flash-preview")
    
    # Use native SDK for Gemini models (faster, no timeout issues)
    if "gemini" in model_name.lower() and _genai_client is not None:
        return _call_gemini_native(prompt, schema, temperature)
    
    return _call_litellm(prompt, schema, temperature)


def extract_all_parameters(email_text: str, constraints_text: str) -> dict:
    prompt = f"""You are the SNHP Mathematical Extraction Layer.
Extract all negotiation parameters from both the opposing client's communication and the freelancer's constraints in a single pass.

CRITICAL RULES:
1. Extract ONLY values explicitly stated in the text. Do NOT compute or derive values.
2. If a value is stated as "X per hour" or "$X/hr", extract it as a number (e.g., 100).
3. Convert ALL durations to DAYS for duration fields: "2 weeks" = 14 days, "1 month" = 30 days.
4. For free_minimum_batna_price: extract the EXPLICIT minimum/floor/walk-away total if stated (e.g. "minimum total is $1875" → 1875). If only a minimum RATE is stated, leave this null.
5. For free_hourly_batna: extract the EXPLICIT minimum/floor hourly RATE if stated (e.g. "minimum $60/hr" → 60). Do NOT confuse with total minimums.
6. For free_revisions and client_max_revisions: only extract if explicitly mentioned. "2 rounds of revisions" → 2.
7. For free_duration_days: extract the TOTAL project duration in days. "2 weeks" → 14, "for 3 weeks" → 21.
8. Normalize all currency: "$100/hr", "100 per hour", "one hundred dollars an hour" all → 100.
9. For payment terms: "net-30" → 30, "net-15" → 15, "upon completion" or "on delivery" → 0, "50% upfront" → 0.

Client Message:
<client_email>
{email_text}
</client_email>

Freelancer Constraints:
<freelancer_constraints>
{constraints_text}
</freelancer_constraints>"""
    try:
        return _call_llm(prompt, CombinedExtraction)
    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}", file=sys.stderr)
        return {}

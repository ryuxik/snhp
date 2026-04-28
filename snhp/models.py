import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List

@dataclass
class ConcessionStep:
    label: str
    amount: float

@dataclass
class SNHPResponse:
    """
    The canonical structured response for the SNHP Negotiation engine.
    """
    is_complete: bool
    missing_fields: Optional[List[str]] = None
    
    # Engine Strategy
    path_taken: Optional[str] = None  # "Nash" or "Rubinstein"
    
    # Optimal Opening Request
    optimal_anchor: Optional[float] = None
    target_days: Optional[int] = None
    target_revisions: Optional[int] = None
    target_payment_days: Optional[int] = None  # 4th dimension: payment terms in days
    total_project_quote: Optional[float] = None
    estimated_total_hours: Optional[float] = None
    
    # Myerson Analytics
    acceptance_probability: Optional[float] = None
    market_median: Optional[float] = None
    market_high: Optional[float] = None
    should_probe: bool = False
    deadweight_warning: bool = False
    
    # The Rubinstein Concession Strategy
    concession_ladder: Optional[List[ConcessionStep]] = None
    minimum_batna_total: Optional[float] = None
    
    # Oracle Problem (Monetization)
    client_role: str = "seller" # "buyer" or "seller"
    client_opening_anchor: Optional[float] = None
    surplus_delta: Optional[float] = None
    delta_capture_toll: Optional[float] = None
    
    # AI Drafting & Context
    draft_email: Optional[str] = None
    historical_count: Optional[int] = None
    historical_avg: Optional[float] = None

    def apply_delta_capture(self, client_opening_anchor: Optional[float] = None, client_role: str = "seller") -> 'SNHPResponse':
        self.client_opening_anchor = client_opening_anchor
        self.client_role = client_role
        
        if client_opening_anchor is not None and self.total_project_quote is not None:
            if self.client_role == "seller" and self.total_project_quote > client_opening_anchor:
                # Upselling: The higher the quote compared to the client's anchor, the more surplus.
                self.surplus_delta = self.total_project_quote - client_opening_anchor
                self.delta_capture_toll = self.surplus_delta * 0.10
            elif self.client_role == "buyer" and self.total_project_quote < client_opening_anchor:
                # Procurement: The lower the quote compared to the client's anchor, the more surplus (savings).
                self.surplus_delta = client_opening_anchor - self.total_project_quote
                self.delta_capture_toll = self.surplus_delta * 0.10
                
        return self

    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

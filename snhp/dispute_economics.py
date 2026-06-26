"""
Dispute platform-economics model — the single source of truth.

A platform's walk-away cost is what NOT settling a refund dispute costs
it. Four components, every figure a modelling assumption (not measured):

  at_risk_value       The disputed value itself — if the platform
                      stonewalls it most likely pays it anyway after
                      escalation, or eats it in a chargeback.
  handling_cost       Expected extra support cost of dragging the dispute
                      out (more contacts, escalation).
  chargeback_premium  p(chargeback) x (card-network dispute fee + ratio
                      penalty). A chargeback costs the merchant far more
                      than the disputed amount: a flat fee (~$15-25; the
                      $20 midpoint here) plus pressure toward network
                      monitoring programs.
  retention_exposure  Expected lost customer lifetime value if a badly
                      handled dispute drives the customer away.

  walk_cost = at_risk_value + handling_cost + chargeback_premium
              + retention_exposure

Shared by the synthetic scenario generator (snhp/cs_negotiation_dataset.py)
and the operator console's walk-cost estimate (dispute_copilot.py) so the
two cannot drift.
"""
from __future__ import annotations

# Stripe's base merchant dispute fee (2025); a defensible, sourced floor. Real
# fees vary by processor ($15 Stripe base, ~$20 PayPal, up to $100 high-risk),
# but every chargeback carries one — that is the load-bearing, citable fact.
CHARGEBACK_FEE = 15.0
SEVERITY_HANDLING_COST = {"minor": 4.0, "major": 9.0, "critical": 16.0}
SEVERITY_RATIO_PENALTY = {"minor": 6.0, "major": 12.0, "critical": 25.0}
SEVERITY_CHARGEBACK_PROB = {"minor": 0.15, "major": 0.40, "critical": 0.70}
DEFAULT_RETENTION_EXPOSURE = 6.0   # USD; the generator overrides per customer profile


def walk_cost_breakdown(disputed_value: float, severity: str = "major",
                        retention_exposure: float = DEFAULT_RETENTION_EXPOSURE) -> dict:
    """The four components of the platform's walk-away cost. An unrecognised
    `severity` falls back to 'major'."""
    sev = severity if severity in SEVERITY_HANDLING_COST else "major"
    cb_prob = SEVERITY_CHARGEBACK_PROB[sev]
    return {
        "at_risk_value": round(disputed_value, 2),
        "handling_cost": round(SEVERITY_HANDLING_COST[sev], 2),
        "chargeback_premium": round(
            cb_prob * (CHARGEBACK_FEE + SEVERITY_RATIO_PENALTY[sev]), 2),
        "retention_exposure": round(retention_exposure, 2),
    }


def estimate_walk_cost(disputed_value: float, severity: str = "major",
                       retention_exposure: float = DEFAULT_RETENTION_EXPOSURE) -> float:
    """The most a rational platform would pay before a chargeback + continued
    handling cost it more — the sum of the four walk-cost components."""
    return round(sum(walk_cost_breakdown(
        disputed_value, severity, retention_exposure).values()), 2)


def chargeback_cost_to_platform(disputed_value: float, severity: str = "major") -> dict:
    """What a customer's card chargeback for undelivered goods costs the
    platform: the disputed amount it must refund anyway, plus the flat,
    non-refundable card-network dispute fee. Both figures are defensible —
    the refund is the claim itself, the fee is a published processor charge.

    `total` deliberately omits a dollar figure for dispute-ratio risk (each
    chargeback also nudges the merchant toward network monitoring programs)
    because a precise per-dispute number there is not defensible — it's
    surfaced qualitatively instead.

    This is the customer's real BATNA. It EXCEEDS the honest claim — which is
    precisely the leverage for the platform to just grant the claim. It is NOT
    a higher amount to demand; the demand stays capped at the true harm.
    """
    refund = round(disputed_value, 2)
    return {
        "refund": refund,
        "dispute_fee": CHARGEBACK_FEE,
        "total": round(refund + CHARGEBACK_FEE, 2),
        "plus_ratio_risk": True,
    }

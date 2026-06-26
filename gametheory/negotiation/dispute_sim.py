"""
Dispute-resolution negotiation runner.

Runs a 1-D refund-dispute negotiation — customer vs. platform over a
settlement amount — by calling the REAL negotiation core
(`sell_next_offer` / `buy_next_offer`), the same functions the /v1 API
exposes. No LLM calls, no assumed outcomes: every counter in the
transcript is computed by the production recommenders.

The dispute is a distributive bargain inside a Zone of Possible
Agreement [customer_floor, platform_walk_cost]:

  - the customer (buyer role) wants a high settlement; reservation =
    customer_floor — the least they will accept before walking away.
  - the platform (seller role) wants a low payout; reservation =
    platform_walk_cost — the most it will pay before a chargeback and
    continued handling cost it more.

Each side's utility is normalised to [0, 1] over that dollar interval.
The platform's lowball opening offer can sit *below* the ZOPA (it is an
anchor, not a rational settlement) — it simply maps to utility 0 for
the customer.

`run_comparison` plays the same dispute twice against an identical
platform — once with the customer unaided, once SNHP-coached — so the
dollar delta is attributable to the customer's tooling alone. The
difference is structural, not assumed: an unaided customer satisfices
on an early offer; the SNHP-coached customer is told the platform's
walk-away cost is high and holds out for the later, larger offers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gametheory.negotiation.buy import buy_next_offer
from gametheory.negotiation.sell import sell_next_offer

_ACCEPT_EPS = 0.02
_DEFAULT_DEADLINE = 10
_CUSTOMER_KNOB = 0.9      # customer wants max recovery
_PLATFORM_KNOB = 0.6      # a competent but not maximally aggressive platform

# Unaided ("vanilla") customer: opens moderate, concedes fast, and
# satisfices — takes the first improved offer that clears a modest bar
# rather than holding out for the platform's true ceiling.
_VANILLA_OPEN = 0.62
_VANILLA_FLOOR_UTIL = 0.20
_VANILLA_EXP = 1.2
_VANILLA_SATISFICE = 0.20     # accepts an improved offer this far up the ZOPA
_VANILLA_LATE_FRAC = 0.65     # ...or anything non-trivial once the clock runs down
_VANILLA_LATE_MIN = 0.08


def _vanilla_target(round_idx: int, deadline_rounds: int) -> float:
    t = min(1.0, round_idx / max(deadline_rounds, 1))
    return _VANILLA_OPEN - (_VANILLA_OPEN - _VANILLA_FLOOR_UTIL) * (t ** _VANILLA_EXP)


@dataclass
class DisputeResult:
    arm: str
    deal: bool
    settlement: float
    rounds: int
    transcript: list


def run_dispute(
    *,
    customer_floor: float,
    platform_walk_cost: float,
    platform_first_offer: float,
    deadline_rounds: int = _DEFAULT_DEADLINE,
    customer_strategy: Literal["snhp", "vanilla"] = "snhp",
    customer_knob: float = _CUSTOMER_KNOB,
    platform_knob: float = _PLATFORM_KNOB,
) -> DisputeResult:
    """Play one dispute negotiation to a settlement (or a timeout)."""
    floor = float(customer_floor)
    walk = float(platform_walk_cost)
    span = walk - floor
    p_open = max(0.0, float(platform_first_offer))
    transcript: list = []

    if span <= 0.5:
        # Customer's floor is at/above the platform's walk-away cost — no
        # real zone of agreement. Best available is the standing offer.
        transcript.append({
            "round": 1, "party": "platform", "amount": round(p_open, 2),
            "note": "Platform's standing offer (no zone of agreement).",
        })
        return DisputeResult(customer_strategy, False, round(p_open, 2), 1, transcript)

    def u_c(s: float) -> float:
        return max(0.0, min(1.0, (s - floor) / span))

    def u_p(s: float) -> float:
        return max(0.0, min(1.0, (walk - s) / span))

    cust_my: list[float] = []     # customer's own offers, customer utility
    cust_opp: list[float] = []    # platform's offers, in customer utility
    plat_my: list[float] = []     # platform's own offers, platform utility
    plat_opp: list[float] = []    # customer's offers, in platform utility

    # Round 1 — platform's lowball opener (given, not computed; may sit
    # below the ZOPA, where it maps to customer-utility 0).
    transcript.append({"round": 1, "party": "platform", "amount": round(p_open, 2),
                       "note": "Platform's opening offer."})
    plat_my.append(u_p(p_open))
    cust_opp.append(u_c(p_open))
    last_platform_offer = p_open
    n_platform_offers = 1
    last_customer_offer: float | None = None

    settlement: float | None = None
    deal = False
    final_round = 1

    for r in range(2, deadline_rounds + 1):
        final_round = r
        last_customer_round = (r >= deadline_rounds - 1)

        if r % 2 == 0:
            # ── Customer's turn ──
            if customer_strategy == "snhp":
                adv = buy_next_offer(
                    my_reservation=0.0, seller_offer_history=cust_opp,
                    my_offer_history=cust_my, deadline_rounds=deadline_rounds,
                    pareto_knob=customer_knob,
                )
                target = float(adv["recommended_offer"])
                accept = u_c(last_platform_offer) >= target - _ACCEPT_EPS
            else:
                target = _vanilla_target(r, deadline_rounds)
                uc = u_c(last_platform_offer)
                t = r / deadline_rounds
                accept = (
                    (n_platform_offers >= 2 and uc >= _VANILLA_SATISFICE)
                    or (t >= _VANILLA_LATE_FRAC and uc >= _VANILLA_LATE_MIN)
                    or last_customer_round
                )

            if accept:
                settlement, deal = last_platform_offer, True
                note = ("SNHP accepts — the platform has no more room."
                        if customer_strategy == "snhp" else "You accept the offer.")
                transcript.append({"round": r, "party": "customer", "settles": True,
                                   "amount": round(last_platform_offer, 2), "note": note})
                break

            demand = floor + target * span
            if last_customer_offer is not None:
                demand = min(demand, last_customer_offer)    # never demand more
            transcript.append({"round": r, "party": "customer", "amount": round(demand, 2),
                               "note": ("SNHP counters." if customer_strategy == "snhp"
                                        else "You counter.")})
            cust_my.append(u_c(demand))
            plat_opp.append(u_p(demand))
            last_customer_offer = demand
        else:
            # ── Platform's turn ──
            adv = sell_next_offer(
                my_reservation=0.0, opponent_offer_history=plat_opp,
                my_offer_history=plat_my, deadline_rounds=deadline_rounds,
                pareto_knob=platform_knob,
            )
            target = float(adv["recommended_offer"])

            if last_customer_offer is not None and u_p(last_customer_offer) >= target - _ACCEPT_EPS:
                settlement, deal = last_customer_offer, True
                transcript.append({"round": r, "party": "platform", "settles": True,
                                   "amount": round(last_customer_offer, 2),
                                   "note": "Platform accepts your counter."})
                break

            offer = walk - target * span
            offer = max(offer, last_platform_offer)          # never offer less
            transcript.append({"round": r, "party": "platform", "amount": round(offer, 2),
                               "note": "Platform improves its offer."})
            plat_my.append(u_p(offer))
            cust_opp.append(u_c(offer))
            last_platform_offer = offer
            n_platform_offers += 1

    if settlement is None:
        # Timed out — customer is left with the platform's standing offer.
        settlement = last_platform_offer
        deal = False
        transcript.append({"round": final_round, "party": "customer", "settles": True,
                           "amount": round(settlement, 2),
                           "note": "Deadline reached — customer takes the standing offer."})

    return DisputeResult(customer_strategy, deal, round(float(settlement), 2),
                         final_round, transcript)


def _arm(result: DisputeResult) -> dict:
    return {
        "arm": result.arm,
        "deal": result.deal,
        "settlement": result.settlement,
        "rounds": result.rounds,
        "transcript": result.transcript,
    }


def run_comparison(
    *,
    platform_first_offer: float,
    platform_walk_cost: float,
    customer_floor: float,
    customer_target: float | None = None,
    deadline_rounds: int = _DEFAULT_DEADLINE,
) -> dict:
    """Play the dispute unaided vs. SNHP-coached against an identical
    platform. The settlement delta is attributable to the customer's
    tooling alone."""
    unaided = run_dispute(
        customer_floor=customer_floor, platform_walk_cost=platform_walk_cost,
        platform_first_offer=platform_first_offer, deadline_rounds=deadline_rounds,
        customer_strategy="vanilla")
    snhp = run_dispute(
        customer_floor=customer_floor, platform_walk_cost=platform_walk_cost,
        platform_first_offer=platform_first_offer, deadline_rounds=deadline_rounds,
        customer_strategy="snhp")
    return {
        "platform_first_offer": round(float(platform_first_offer), 2),
        "customer_floor": round(float(customer_floor), 2),
        "customer_target": (round(float(customer_target), 2)
                            if customer_target is not None else None),
        "unaided": _arm(unaided),
        "snhp": _arm(snhp),
        "delta_vs_unaided": round(snhp.settlement - unaided.settlement, 2),
    }

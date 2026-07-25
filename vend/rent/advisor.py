"""Rent-renewal advisor — deterministic core.

Four inputs, one honest answer. No LLM in any judgment path: the same
inputs always produce the same verdict, so an answer can be re-derived
and disputed. Message *polish* is left to the calling agent; we return
the substance.

WHAT THIS IS FOR
A renter holding a renewal offer has no idea whether the number is
reasonable, what is negotiable, or whether asking is worth the
awkwardness. Roughly 61% never ask. Of those who do, about 22% get
something — and that roughly doubles with tenure. This tool converts a
non-asker into an informed asker, and tells the ones with no leverage to
sign, which is the part that makes it advice.

BASE RATES — all from Avail survey data analysed by the Urban Institute
(n≈1,300 renters, 2022). Cited, not invented. They are the single
weakest link in the evidence chain (one vendor survey, four years old,
mom-and-pop skew) and the copy says so.

EVIDENCE FOR THE ASK ORDER
Landlords concede *concessions* far more readily than headline rent,
because headline rent sets the comp for the whole building while a free
month does not. Q1 2026 REIT disclosures show new-lease rents falling
(MAA -7.0%) while renewal rents rise (+5.4%) — operators are protecting
the renewal number specifically. So the ranked asks run easiest-to-
hardest, which is the reverse of what almost every tenant does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vend.rent import jurisdictions, metros

# --- Verified base rates (Avail / Urban Institute, 2022) -------------
BASE_SUCCESS_RATE = 0.22          # of tenants who ask, share getting something
SUCCESS_RATE_TENURE_2Y_PLUS = 0.265   # 26-27% at 2+ years
SUCCESS_RATE_UNDER_2Y = 0.145         # 14-15% under 2 years
# CORRECTED 2026-07-24. This was 0.72 and mis-attributed: the Urban
# Institute analysis says 39% of tenants facing an increase TRIED to
# negotiate, so 61% did not. The 72% came from a different survey
# framing and must not be cited to the Urban Institute.
SHARE_WHO_TRY = 0.39
SHARE_WHO_NEVER_ASK = 0.61
EVIDENCE_NOTE = (
    "Success rates from Avail survey data analysed by the Urban Institute "
    "(~1,300 renters, 2022). It is the best available evidence and it is "
    "thin: one survey, four years old, skewed toward small landlords. "
    "Treat these as rough odds, not a forecast."
)

TENURE_2Y_MONTHS = 24

# K25, confirmed in our own pre-registered simulation (research/crabs).
# Response delay was drawn INDEPENDENTLY of tenant type, so this is causal
# rather than the survivorship trap that broke an earlier arm. A tenant who
# lets a three-month window lapse is offered 13.3% more relative to market
# and ends ~$645/yr worse off than an identical tenant who answers at once.
# This is the strongest product finding in the study, so it leads.
DELAY_PENALTY_ANNUAL = 645
DELAY_PENALTY_NOTE = (
    "Answer quickly. In our own simulation, an identical tenant who let a "
    "three-month window lapse was offered 13.3% more relative to market and "
    "ended about $645 a year worse off. Negotiate inside the window — never "
    "by letting it run down."
)

# K26 did NOT confirm. Securing an alternative before you counter changed the
# terms offered by $17/yr against a $480 bar — because the landlord cannot
# verify your alternative, so it offers the same either way. It buys you the
# ability to walk, NOT a better offer. We do not claim otherwise.
SHOPPING_AROUND_NOTE = (
    "Lining up another place is worth doing so you can actually leave — but "
    "in our simulation it did not improve the terms you were offered. Your "
    "landlord cannot verify it."
)


@dataclass(frozen=True)
class Ask:
    """One thing to ask for, with why it is ranked where it is."""

    key: str
    headline: str
    detail: str        # standalone imperative, for the ranked list
    ask_phrase: str    # embeddable clause, for the drafted message
    ease: str          # "easiest" | "moderate" | "hardest"
    why: str
    est_annual_value: int | None = None


@dataclass(frozen=True)
class Assessment:
    verdict: str                      # "strong" | "moderate" | "weak"
    headline: str
    increase_monthly: int
    increase_pct: float
    annual_cost: int
    odds_if_you_ask: float
    odds_basis: str
    asks: list[Ask] = field(default_factory=list)
    message: str = ""
    next_step: str = ""
    market: dict = field(default_factory=dict)
    legal: dict = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "headline": self.headline,
            "increase": {
                "monthly": self.increase_monthly,
                "pct": round(self.increase_pct, 1),
                "annual_cost": self.annual_cost,
            },
            "odds_if_you_ask": round(self.odds_if_you_ask, 2),
            "odds_basis": self.odds_basis,
            "share_who_never_ask": SHARE_WHO_NEVER_ASK,
            "asks": [
                {
                    "key": a.key,
                    "ask": a.headline,
                    "detail": a.detail,
                    "ask_phrase": a.ask_phrase,
                    "ease": a.ease,
                    "why": a.why,
                    "est_annual_value": a.est_annual_value,
                }
                for a in self.asks
            ],
            "message": self.message,
            "next_step": self.next_step,
            "market": self.market,
            "legal": self.legal,
            "caveats": self.caveats,
            "act_fast": {
                "penalty_annual_usd": DELAY_PENALTY_ANNUAL,
                "note": DELAY_PENALTY_NOTE,
            },
            "shopping_around": SHOPPING_AROUND_NOTE,
            "evidence_note": EVIDENCE_NOTE,
        }


def _odds(months_at_address: int) -> tuple[float, str]:
    if months_at_address >= TENURE_2Y_MONTHS:
        return (
            SUCCESS_RATE_TENURE_2Y_PLUS,
            "You've been there 2+ years. Tenants at that tenure succeed "
            "roughly 26% of the time versus about 14% for newer tenants — "
            "tenure is the single strongest predictor in the data.",
        )
    return (
        SUCCESS_RATE_UNDER_2Y,
        "Under 2 years of tenure. Newer tenants succeed roughly 14% of the "
        "time versus about 26% at 2+ years.",
    )


def _build_asks(
    current_rent: int, offered_rent: int, market: dict
) -> list[Ask]:
    """Ranked easiest-to-hardest for the landlord to say yes to."""
    increase = max(0, offered_rent - current_rent)
    annual_increase = increase * 12

    # Value of a typical concession where one is offered, from the
    # national stabilized-universe average discount.
    concession_pct = metros.NATIONAL_CONCESSION_DISCOUNT_PCT / 100.0
    concession_value = int(round(current_rent * 12 * concession_pct))
    weeks = metros.NATIONAL_CONCESSION_WEEKS_FREE

    asks: list[Ask] = []

    share = market.get("concession_share_pct")
    if share is not None and share >= 30:
        parity_why = (
            f"About {share:.0f}% of listings in {market.get('metro')} advertise "
            f"a move-in concession right now. You are asking to be treated "
            f"like the person signing the identical apartment down the hall."
        )
    else:
        parity_why = (
            f"Nationally about {metros.NATIONAL_LISTING_CONCESSION_SHARE:.0f}% "
            "of listings advertise a move-in concession — roughly "
            f"{weeks:.0f} weeks free where one is offered."
        )

    asks.append(
        Ask(
            key="concession_parity",
            headline=f"Ask for the same move-in deal new tenants are getting",
            detail=(
                f"Request {weeks:.0f} weeks of free rent (or the equivalent "
                "credit) applied to your renewal."
            ),
            ask_phrase=(
                f"applying {weeks:.0f} weeks of free rent — or the equivalent "
                "credit — to my renewal"
            ),
            ease="easiest",
            why=(
                parity_why
                + " This is the easiest yes: a one-time credit doesn't lower "
                "the rent on record, so it doesn't reset the building's comp."
            ),
            est_annual_value=concession_value,
        )
    )

    asks.append(
        Ask(
            key="fee_waivers",
            headline="Ask for recurring fees to be waived",
            detail=(
                "Parking, pet rent, amenity, storage, or trash fees — name "
                "the specific ones on your ledger."
            ),
            ask_phrase="waiving the parking, pet, or amenity fees on my account",
            ease="easiest",
            why=(
                "Fees sit outside the headline rent, so waiving them costs "
                "the landlord less politically than a rent reduction."
            ),
        )
    )

    asks.append(
        Ask(
            key="term_trade",
            headline="Offer a longer lease for a lower rate",
            detail=(
                "Offer 24 months at a lower blended rent instead of 12 at "
                "the asking rate."
            ),
            ask_phrase=(
                "signing for 24 months instead of 12, at a lower blended rate"
            ),
            ease="moderate",
            why=(
                "You are selling something they actually want: a guaranteed "
                "occupied unit and no turnover next year. This is a trade, "
                "not a request — which is why it lands better than asking."
            ),
        )
    )

    asks.append(
        Ask(
            key="rent_reduction",
            headline="Ask to hold the rent flat (or reduce the increase)",
            detail=(
                f"Ask them to keep it at ${current_rent:,}/mo, or to split "
                f"the difference at ${current_rent + increase // 2:,}/mo."
            ),
            ask_phrase=(
                f"holding the rent at ${current_rent:,}, or meeting in the "
                f"middle at ${current_rent + increase // 2:,}"
            ),
            ease="hardest",
            why=(
                "Headline rent sets the comparable for the whole building, "
                "so it is the number operators defend hardest. Ask for it "
                "last, not first — which is the opposite of what most "
                "tenants do."
            ),
            est_annual_value=annual_increase or None,
        )
    )
    return asks


def _verdict(market: dict, increase_pct: float, months: int) -> tuple[str, str]:
    """Honest three-way call. 'weak' must be reachable — a tool that
    always finds leverage is a horoscope."""
    known = market.get("metro_known", False)
    tier = market.get("tier")
    tightening = market.get("tightening", False)
    metro = market.get("metro", "your area")

    if increase_pct <= 0:
        return (
            "weak",
            "Your rent isn't going up. There's nothing to push back on — "
            "and asking anyway risks goodwill you may want later.",
        )

    if known and tightening:
        return (
            "weak",
            f"{metro} is tightening — landlords there are offering fewer "
            "deals than a year ago, not more. Your realistic move is a "
            "small, polite ask, or simply signing.",
        )

    if known and tier == "weak":
        return (
            "weak",
            f"{metro} is one of the tighter rental markets in the country. "
            "Leverage is limited. If you want to stay, signing is a "
            "reasonable choice and there is no shame in it.",
        )

    if known and tier == "strong" and months >= TENURE_2Y_MONTHS:
        return (
            "strong",
            f"You're in a strong position. {metro} landlords are competing "
            "hard for tenants right now, and your tenure roughly doubles "
            "your odds. It is worth asking.",
        )

    if known and tier == "strong":
        return (
            "strong",
            f"{metro} is a renter's market right now — landlords there are "
            "widely advertising move-in deals. It is worth asking.",
        )

    return (
        "moderate",
        "You have a real but modest position. A specific, friendly ask is "
        "worth the five minutes; a confrontation is not.",
    )


def _message(
    verdict: str, current_rent: int, offered_rent: int, months: int, asks: list[Ask]
) -> str:
    """A send-ready scaffold. Factual, warm, non-adversarial — the
    relationship continues after this exchange."""
    if verdict == "weak":
        return ""

    years = months // 12
    tenure_line = (
        f"I've been here {years} years and have always paid on time."
        if years >= 1
        else "I've paid on time every month since moving in."
    )
    primary = asks[0]
    secondary = asks[2]  # the term trade — a give, not just an ask

    return (
        f"Hi — thanks for sending the renewal.\n\n"
        f"I'd like to stay. {tenure_line}\n\n"
        f"Before I sign, would you consider {primary.ask_phrase}? "
        f"I've seen comparable units advertised with move-in incentives, and "
        f"I'd rather put that toward staying than moving.\n\n"
        f"I'm also open to {secondary.ask_phrase}, if that's useful on "
        f"your end.\n\n"
        f"Happy to sign quickly either way. Thanks for considering it."
    )


def assess(
    metro: str,
    current_rent: int,
    offered_rent: int,
    months_at_address: int,
) -> Assessment:
    """The whole product, in one deterministic call.

    Raises ValueError on inputs that cannot produce an honest answer —
    better than returning confident nonsense.
    """
    if current_rent <= 0 or offered_rent <= 0:
        raise ValueError("Rents must be positive amounts in dollars per month.")
    if months_at_address < 0:
        raise ValueError("months_at_address cannot be negative.")

    market = metros.market_context(metro)
    legal = jurisdictions.legal_block(metro)

    increase = offered_rent - current_rent
    increase_pct = (increase / current_rent) * 100.0
    annual_cost = max(0, increase) * 12

    verdict, headline = _verdict(market, increase_pct, months_at_address)
    odds, odds_basis = _odds(months_at_address)

    # A weak MARKET position is not the whole story where regulated stock
    # exists. In those places the live question is legal, not commercial —
    # and it can be worth far more than any concession. Route there first
    # rather than telling someone to sign a possibly-unlawful increase.
    regulated = legal.get("may_be_regulated", False)

    if verdict == "weak":
        asks: list[Ask] = []
        if regulated:
            next_step = (
                "Before you sign: find out whether your apartment is rent "
                "regulated. If it is, the increase you were offered may be "
                "capped by law regardless of the market — a bigger question "
                "than anything you could negotiate. See 'how to verify' "
                "in the verification steps we've listed, then decide."
            )
        else:
            next_step = (
                "Sign it, or send a short friendly note asking whether any "
                "move-in style incentive is available — but don't expect "
                "much, and don't spend goodwill you'll want later."
            )
    else:
        asks = _build_asks(current_rent, offered_rent, market)
        # K25 leads both paths: delay costs more than any single ask below.
        urgency = (
            "Do this now rather than later — waiting costs more than any "
            "single thing you could ask for. "
        )
        lead = urgency + (
            "First, check whether your apartment is rent regulated — if it "
            "is, the legal cap matters more than any of this. Then send the "
            "message "
            if regulated
            else "Send the message "
        )
        next_step = (
            lead
            + "to whoever signed your renewal letter. Ask for the easiest "
            "item first. If they say no to everything, you can still sign — "
            "asking costs you nothing but five minutes."
        )

    caveats = list(legal.get("caveats", []))
    caveats.append(
        f"Market figures are as of {market.get('as_of', metros.AS_OF)} and are "
        "metro-level, not building-level. Your building may differ."
    )
    if not market.get("metro_known", False):
        caveats.append(
            "We don't have market data for your metro, so this uses national "
            "figures only. Treat the market framing as weaker than usual."
        )

    return Assessment(
        verdict=verdict,
        headline=headline,
        increase_monthly=increase,
        increase_pct=increase_pct,
        annual_cost=annual_cost,
        odds_if_you_ask=odds,
        odds_basis=odds_basis,
        asks=asks,
        message=_message(
            verdict, current_rent, offered_rent, months_at_address, asks
        )
        if asks
        else "",
        next_step=next_step,
        market=market,
        legal=legal,
        caveats=caveats,
    )

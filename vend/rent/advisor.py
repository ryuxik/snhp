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
# K25 is CONFIRMED (RESULTS.md: offer/market 1.065 -> 1.198, -$645/yr,
# delay drawn independently of tenant type so it is causal). What was
# withdrawn is a different claim — that the effect comes from the SHAPE of
# the deadline rather than its LEVEL; the shape is 13% of it. An earlier
# version of this note applied the shape retraction to the delay finding
# and hedged away advice that had survived.
#
# The number still does not ship, because it scales with a delay cost we
# chose. The advice does, in one sentence.
DELAY_PENALTY_NOTE = (
    "Answer inside your response window. Miss it and you can lose the right "
    "to renew at all."
)

# WHY THE COPY NO LONGER SAYS "it only takes five minutes".
# The study went looking for a cost that would explain why 61% never ask —
# time, awkwardness, fear of being marked as trouble. None works: to
# reproduce the observed 39% who try, sending one email would have to cost
# a tenant 27-55 hours of their own wages. It doesn't. So whatever stops
# people is not a cost, and advice built on lowering the effort is aimed at
# the wrong thing. The lever that does move is being INFORMATIVE — hence
# the note below, and hence the copy leads with bringing something
# checkable rather than with how little time it takes.
#
# K26 read backwards, and the comment that used to sit here said so with
# confidence. The original arm gave the landlord no way to VERIFY the
# alternative, so of course it offered the same either way — that was a
# property of our model, not of renting, so that finding is withdrawn.
#
# What replaced it overstated in the other direction. AMENDMENT 9 wired and
# swept the verifiable-signal arm (it had been run once and never committed,
# which is its own lesson). Two results:
#
#   K28 did NOT fire. The offer gap is real and reproducible: 10.212%,
#   flat across every signal_cost in {0.05, 0.10, 0.20, 0.40}.
#
#   K29 FIRED, and it is the one that matters. Ablated against
#   deadline_shape=False the gap collapses to 0.004% -- and the same 0.004%
#   shows up in the signal-OFF control, so the direct channel is exactly
#   zero. market.py:452-468 gives a proved tenant `wa_t_exp = wa_t_base`,
#   the identical expression everyone gets with no cliff, built from the
#   POPULATION move_med. Proving reveals nothing about this tenant.
#
# So proving works by deleting your deadline penalty, not by making you
# expensive to replace. It is K25 measured a second time under another name
# (cf. artefact #3: "the shape of the deadline" was 87% level).
#
# Net to the tenant: +$458/yr at the declared signal cost, against K26's
# $480 materiality bar -- BELOW the bar at every signal cost, because the
# proof costs about what it buys. K26 still does not confirm, but now for a
# real reason rather than because the landlord could not respond.
# PRINCIPLE D: `secured_surp` mixes a stayers-only numerator with an
# all-renewals denominator, so treat $458 as indicative, not exact.
# The gap also scales with the circular `move_med`: 7.368% on A8's derived
# 1.48 months rather than the calibrated 3.60.
SHOPPING_AROUND_NOTE = (
    "If you have a real alternative, say so and be specific enough that it "
    "can be checked. A vague 'I could move' is not the same thing."
)

# The measurement behind it, for the self-audit rather than the advice.
# Worth less than we first said (~$460/yr against our own $480 bar) and
# it works by removing the deadline penalty rather than by making you
# expensive to replace — which is why answering early is the stronger
# advice of the two.
# The dollar figures came OUT of this string on 2026-07-25. Once `evidence`
# was wired into rent.html they became reader-facing, and they are simulation
# outputs on a page that promises not to quote one. They are also unsafe
# twice over: the effect scales with `move_med`, still CALIBRATED to observed
# elasticity (10.212% of market at 3.60 months, 7.368% at A8's derived 1.48),
# and PRINCIPLE D flags `secured_surp` as a stayers-only numerator over an
# all-renewals denominator. What survives is the ORDERING, which needs
# neither number: it came in under our own bar, and the clock is the channel.
SHOPPING_AROUND_EVIDENCE = (
    "On the specific-alternative advice: we did measure it, and it came in "
    "under our own bar for calling something material. It also turned out "
    "to work by removing the penalty for answering close to your deadline "
    "rather than by making you costly to replace, which is why answering "
    "early is the stronger of the two. The figure itself does not ship: it "
    "scales with a switching cost we calibrated rather than derived."
)


# The one finding about YOUR position that runs against intuition.
# Crabs were given real preferences over habitats, so some wanted to move
# for reasons that had nothing to do with price — more space, a better
# neighbourhood. About one in five real renter moves is exactly that.
# The expectation was that it would weaken the price conversation, since
# somebody leaving for a bigger kitchen is not making a threat. It did
# the opposite: a discount held onto those tenants BETTER.
#
# The reasoning is the transferable part, and it is not obviously wrong
# outside the model: someone already half-decided is sitting near
# indifference, and near indifference is exactly where a discount lands.
# The magnitudes are model output and are not quoted, for the same reason
# the delay figure is not.
NON_PRICE_MOVER_NOTE = (
    "If you're already half thinking about moving for reasons that aren't "
    "about rent — more space, a shorter commute — say so. It makes you more "
    "worth an offer, not less."
)

NON_PRICE_MOVER_EVIDENCE = (
    "On the half-thinking-of-moving advice: someone already near the line "
    "is where a discount lands, which is why it holds onto them better. "
    "That is reasoning from our own model rather than something measured "
    "against real renewals."
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
            "act_fast": {"note": DELAY_PENALTY_NOTE},
            "shopping_around": SHOPPING_AROUND_NOTE,
            "non_price_mover": NON_PRICE_MOVER_NOTE,
            "evidence": [SHOPPING_AROUND_EVIDENCE, NON_PRICE_MOVER_EVIDENCE],
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
        "worth making; a confrontation is not.",
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

    # The two findings that matter are BUILT IN here rather than told to
    # somebody in an instruction they have to remember: the specific
    # checkable thing, and saying you are weighing a move. Square
    # brackets because a blank they fill is more likely to get filled
    # than a sentence above the box telling them to.
    return (
        f"Hi — thanks for sending the renewal.\n\n"
        f"I'd like to stay. {tenure_line}\n\n"
        f"Before I sign, would you consider {primary.ask_phrase}? "
        f"I've seen comparable units advertised with move-in incentives, and "
        f"I'd rather put that toward staying than moving.\n\n"
        f"[If you have a specific alternative they could check — a listing, "
        f"an address, a date — put it here. That is worth more than saying "
        f"you might move. If you're weighing a move for reasons that aren't "
        f"about rent, say that too.]\n\n"
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
                "Before you sign, find out whether your apartment is rent "
                "regulated. If it is, that matters more than anything you "
                "could negotiate. We've listed how to check."
            )
        else:
            next_step = (
                "Sign it. You can ask whether any move-in incentive is "
                "available, but don't expect much."
            )
    else:
        asks = _build_asks(current_rent, offered_rent, market)
        # ONE instruction. This carried four at one point — send it, ask
        # easiest-first, put something checkable in it, mention if you're
        # half thinking of moving — which is a checklist wearing a
        # sentence. The ranked asks are already on the page and the two
        # pieces of advice are now lines inside the drafted message,
        # where they get acted on rather than remembered.
        urgency = (
            "Send it this week — miss your response window and you can lose "
            "the right to renew at all."
        )
        next_step = (
            "Check whether your apartment is rent regulated before you sign "
            "— if it is, the cap matters more than anything you could ask "
            "for. Then send the drafted message."
            if regulated else urgency
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

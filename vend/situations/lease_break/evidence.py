"""Economics layer for the lease-break situation.

THE ONE NON-OBVIOUS MECHANISM
Your exposure when you walk away depends on how fast the landlord can
re-rent the unit. That is the same quantity `vend/rent/metros.py`
already measures from the other side: concession share is a direct read
on how hard landlords are working to fill units.

So the two situations invert. A soft market (Denver, 68% of listings
advertising a concession) is where a RENEWING tenant has leverage and
where a LEAVING tenant is most exposed — nobody is queuing up to take
the unit. A tight market (New York, 18%) is where renewing gives you
almost nothing and where walking away costs you least, because the unit
re-rents fast and the landlord's damages are small.

That inversion is the whole reason this is the better demo. Nobody
arrives knowing to ask it, and it falls out of data we already keep.

────────────────────────────────────────────────────────────────────
VERIFY BEFORE LAUNCH — this module is NOT publishable as data
────────────────────────────────────────────────────────────────────
DISCHARGED (2026-07-25): the total cost of a turn is now sourced to the
NAA/IREM/BOMA Income/Expense IQ survey via writing/rent-no-source.md,
replacing an invented figure that was 1.75-3.5x too high. See the
comment on TURN_COST_MONTHS_LOW.

STILL OUTSTANDING, so `PUBLISHABLE` stays False:

  1. PARTLY CLOSED 2026-07-25, and the part that stayed open is the
     interesting one. A national cross-check exists and corroborates the
     envelope: Apartment List puts median list-to-lease at 41 days in
     Jan 2026 (vacancy 7.3%), which with the leasing cost lands near 1.7
     months of rent — inside the surveyed 1-2 band, from an independent
     source. See DOM_CROSSCHECK.

     PER-METRO days-on-market could not be sourced to anything this
     codebase would cite. The metro figures in circulation come from
     property-management company blogs, which is precisely the citation
     chain rent-no-source.md was written about. Apartment List publishes
     vacancy rate by metro but not list-to-lease by metro; vacancy rate
     is probably the better proxy than concession share and is the next
     thing to chase.

     One thing the cross-check hints at and cannot settle: 41 days
     national sits below the 2.0 months this module assigns to soft
     markets, so the soft end may be too high. Not acted on, because
     acting on a national median to set a per-metro figure would be the
     same error in the other direction.
  2. CLOSED by deletion — see the note on TYPICAL_BUYOUT_MONTHS. There
     is no dataset of residential early-termination terms, so the tool
     no longer estimates one; a person is sent to read their own clause.
  3. Whether the survey's turn figure should be discounted further for
     TIMING — the research notes a landlord loses when a turn happens,
     not whether, so the true incremental loss from an early exit is
     smaller again than the gross figure used here.

Until those land the assess function labels every derived figure as an
estimate and says what it rests on. It never states a range as fact.
"""

from __future__ import annotations

from vend.rent import metros as _metros

# Gate, in the same spirit as jurisdictions.rates_verified. The API
# surfaces this so nothing here can be mistaken for measured data.
PUBLISHABLE = False
BASIS = (
    "What a turnover costs a landlord is triangulated from the "
    "NAA/IREM/BOMA Income/Expense IQ survey (4,666 properties, 1.09m "
    "units): about $2,000–4,000, or one to two months' rent, including the "
    "empty time. That is the sourced part, and it is a good deal smaller "
    "than the 'one to three months' every landlord blog repeats without a "
    "citation. Where your metro sits inside that range is our judgment, "
    "read off concession share (Zillow, " + _metros.AS_OF + "). Treat the "
    "dollar figures as an order of magnitude, not a quote."
)

# ── What a turn actually costs, from the survey ──────────────────────
# SOURCED. NAA/IREM/BOMA Income/Expense IQ — 4,666 properties, 1.09m
# units, 109 metros. Decomposition and triangulation in
# writing/rent-no-source.md.
#
# THIS REPLACED AN INVENTED NUMBER, AND THE CORRECTION WAS LARGE.
# An earlier version of this module used a flat 0.5 months of rent for
# re-letting plus up to 3.0 months of vacancy — 3.5 months total, which
# is 1.75–3.5x the surveyed range. On a $2,400 Denver apartment it
# anchored the recommended buy-out at $8,400 against a sourced envelope
# of $2,400–4,800. It would have told people to open at roughly double
# the landlord's real loss. Exactly the "1–3 months of rent" folk number
# the research set out to kill, re-derived by hand.
SOURCE = (
    "NAA/IREM/BOMA Income/Expense IQ (4,666 properties, 1.09m units, "
    "109 metros)"
)

# Leasing expense: $292/unit/year at roughly 47% annual turnover. A flat
# cash cost per turn — deliberately NOT a fraction of rent, because
# marketing and screening do not scale with the rent roll the way the
# folk number assumes.
LEASING_COST_PER_TURN_USD = 650

# The triangulated total cost of one turn, INCLUSIVE of vacancy:
# $2,000–4,000, or roughly 1–2 months of rent. The vacancy-and-rent-loss
# line ($1,323/unit/yr, ~$2,900/turn) overstates pure turn vacancy
# because it also carries concessions and bad debt, and make-ready is
# largely capitalised rather than expensed — which is why blog estimates
# and accounting figures never reconcile.
TURN_COST_MONTHS_LOW = 1.0
TURN_COST_MONTHS_HIGH = 2.0

# WHERE A METRO SITS IN THAT ENVELOPE IS A JUDGMENT — but a judgment
# made INSIDE a sourced band rather than an invented number outside it.
# Read the inversion carefully: tier "strong" means concessions are the
# norm, i.e. a SOFT market — good for a renewing tenant, bad for a
# leaving one, because the unit sits empty longer.
TURN_COST_MONTHS_BY_TIER = {
    "strong": TURN_COST_MONTHS_HIGH,    # soft market — slow to re-let
    "moderate": 1.5,
    "weak": TURN_COST_MONTHS_LOW,       # tight market — re-lets fast
}
NATIONAL_TURN_COST_MONTHS = 1.5   # midpoint, when the metro is unknown

# Independent corroboration of the envelope, not an input to it.
# Apartment List, January 2026: national median list-to-lease 41 days,
# national vacancy 7.3% (highest in their index since 2017). 41 days is
# ~1.35 months; plus the leasing cost that is ~1.7 months of rent on a
# typical national rent — inside the surveyed 1-2 band.
DOM_CROSSCHECK = {
    "median_list_to_lease_days": 41,
    "national_vacancy_pct": 7.3,
    "as_of": "2026-01",
    "source": "Apartment List rental market data, Feb 2026 report",
    "url": "https://www.apartmentlist.com/rental-management/navigating-rental-landscape-feb-2026",
    "note": (
        "Used as a check on the envelope, never as a per-metro input. "
        "Per-metro days-on-market is not published by anyone we would cite; "
        "the metro figures in circulation are property-manager blogs."
    ),
}

# Floor on vacancy so the arithmetic stays sane on very high rents,
# where the flat leasing cost is a rounding error.
MIN_VACANCY_MONTHS = 0.25

# RETIRED 2026-07-25. This was 2.0 — "the months of rent most commonly
# written into early-termination clauses" — and it was a lease-template
# convention rather than a measured distribution. There is no survey of
# residential termination terms to source it from, so the fix was to
# delete it rather than to go looking: assess.py now sends somebody to
# read their own clause instead of anchoring them on a number we made
# up. Do not reintroduce it without a citation.

# ── What leaving costs YOU ───────────────────────────────────────────
# The other half of the arithmetic, and it is in worse shape than the
# landlord's half. No government statistic exists: the Census publishes
# how often people move, the BLS publishes a price index for moving
# services, and nobody official publishes what a move costs.
#
# The figure everyone quotes (~$2,300) comes from a trade body absorbed
# into another organisation in December 2020, circulates with three
# mutually inconsistent values attached, and has no reachable primary
# document. Same shape as the "1-3 months" turnover number: a citation
# chain with no origin.
#
# These two are independent and reachable — one built from booked
# transactions, one from a consumer survey. They are the honest range.
# Both are local-move figures; a long-distance move is a different and
# much larger number, which is why this is shown as a floor rather than
# an estimate of anyone's actual move.
MOVE_COST_LOW_USD = 984
MOVE_COST_HIGH_USD = 1489
MOVE_COST_NOTE = (
    "Moving itself costs you something, and it is worth putting in the same "
    "sentence as everything else here. Two independent estimates of a local "
    "move land around $1,000 and $1,500 — one from booked transactions, one "
    "from a consumer survey. The $2,300 figure repeated everywhere traces to "
    "a trade body that no longer exists and has no primary document behind "
    "it. Treat $1,000-1,500 as a floor for a local move and expect more if "
    "you are going any distance."
)

# Below this many months left, the arithmetic stops being the story:
# almost any route costs about the same and the honest answer is
# usually "ride it out."
SHORT_TAIL_MONTHS = 2.0


def turn_cost(metro_key: str, rent: float, months_left: float) -> dict:
    """What one unscheduled turn costs the landlord, in dollars.

    Total is pinned to the surveyed 1–2 months envelope; the split into
    empty time versus leasing cash is derived so the parts add up to a
    number somebody actually measured.

    A caveat the research raises that this does not model: a landlord
    does not lose the turn cost outright, they lose its TIMING — a turn
    was on the schedule eventually. That makes the true incremental loss
    smaller again, so this figure should be read as a ceiling on what is
    worth offering, not a target.
    """
    ctx = market(metro_key)
    months = (
        TURN_COST_MONTHS_BY_TIER.get(ctx.get("tier"), NATIONAL_TURN_COST_MONTHS)
        if ctx.get("metro_known") else NATIONAL_TURN_COST_MONTHS
    )
    total = months * rent
    vacancy_months = max(MIN_VACANCY_MONTHS,
                         (total - LEASING_COST_PER_TURN_USD) / rent)
    # You cannot be billed for empty time past the end of your own term.
    vacancy_months = min(vacancy_months, months_left)
    total = vacancy_months * rent + LEASING_COST_PER_TURN_USD

    return {
        "total_usd": total,
        "vacancy_months": vacancy_months,
        "leasing_cost_usd": LEASING_COST_PER_TURN_USD,
        "turn_months_of_rent": months,
        "source": SOURCE,
    }


def market(metro_key: str) -> dict:
    """Re-letting context for one metro, honest about absence.

    Never invents a local figure — an unknown metro degrades to national
    context with `metro_known=False`, exactly as the renewal advisor
    does, so the caller can say so.
    """
    ctx = _metros.market_context(metro_key)
    if not ctx.get("metro_known"):
        return {
            **ctx,
            "relet_speed": "unknown",
            "relet_note": (
                "We don't have market data for your area, so this uses a "
                "national middle estimate for how long a unit sits empty."
            ),
        }

    tier = ctx["tier"]
    if tier == "weak":
        speed, note = "fast", (
            f"{ctx['metro']} is a tight rental market — only about "
            f"{ctx['concession_share_pct']:.0f}% of listings there advertise a "
            "move-in deal. Units re-rent quickly, which works in your favour "
            "here: the faster it re-rents, the less a landlord can claim from you."
        )
    elif tier == "strong":
        speed, note = "slow", (
            f"{ctx['metro']} is a soft rental market — about "
            f"{ctx['concession_share_pct']:.0f}% of listings there are "
            "advertising move-in deals, which means landlords are working hard "
            "to fill units. That is bad news for leaving: your unit may sit "
            "empty for a while, and that empty time is what you can be billed for."
        )
    else:
        speed, note = "average", (
            f"About {ctx['concession_share_pct']:.0f}% of listings in "
            f"{ctx['metro']} advertise a move-in deal — a middling market for "
            "re-letting speed."
        )

    return {
        **ctx,
        "relet_speed": speed,
        "relet_note": note,
    }

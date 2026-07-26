"""Evidence for the salary-negotiation situation: base rates, with provenance.

Every figure here carries where it came from and whether a person has checked
it. Nothing in this module is derived from a model's guess — the framework's
whole safety story is that judgments rest only on verified data modules, rules
modules, or the person's own words.

**GATE: `VERIFIED = False`.** The replacement-cost and time-to-fill anchors are
consultancy and trade-press benchmarks, not peer-reviewed estimates, and the
simulation figures come from our own pre-registered study rather than from
observed salary negotiations. Until a human checks each row below, the situation
that imports this stays `live=False`.
"""
from __future__ import annotations

from dataclasses import dataclass

VERIFIED = False
REFRESH_MONTHS = 12


@dataclass(frozen=True)
class Figure:
    value: float
    unit: str
    source: str
    note: str = ""
    verified: bool = False


# ---------------------------------------------------------------- base rates
#: Share of workers who accept the first offer without negotiating at all.
#: This is the denominator for the only large effect we measured.
SHARE_WHO_NEVER_ASK = Figure(
    0.55, "share of workers",
    "Procurement Tactics, salary-negotiation statistics roundup 2025",
    "Trade aggregation of survey data, not a primary study. The complementary "
    "figure (about 45% negotiate) is used nowhere; only the majority-don't "
    "framing is load-bearing.")

#: All-in cost of replacing someone, as a multiple of salary. THIS IS THE NUMBER
#: EVERY PIECE OF ADVICE HERE TURNS ON, and the two literatures disagree by an
#: order of magnitude:
#:
#: SOURCE READ IN FULL (Boushey & Glynn, Center for American Progress, 2012):
#: 11 research papers published 1992-2007, 31 case studies, 27 positions.
#:   * median 21% of annual salary, EXPLICITLY EXCLUDING executives and
#:     physicians ("jobs that require very specific skills")
#:   * 16% for positions earning under $30,000
#:   * senior roles run "up to 213 percent", which the authors say skews the
#:     data upwards, hence their exclusion from the median
#:   * only 2 of the 11 papers included INDIRECT costs at all
#:
#: That last line reconciles the disagreement. The 21% median is a largely
#: DIRECT-cost figure: separation, cover, advertising, training. The vendor
#: range of 50-200% is trying to price indirect cost too: lost productivity,
#: morale, client loss, knowledge walking out of the door. They are not
#: contradicting each other, they are measuring different things, and the truth
#: for any given role sits between them.
#:
#: So: `REPLACEMENT_COST` is the sourced direct-cost floor and
#: `REPLACEMENT_COST_TRADE` is the indirect-inclusive ceiling, and the tool
#: shows the span. Two further caveats a reader should have: the underlying data
#: is 1992-2007, and none of it is specific to any one employer.
REPLACEMENT_COST = {
    "frontline":    Figure(0.16, "x salary", "Boushey & Glynn 2012 (CAP), read in full",
                           "Their figure for positions under $30k. Direct costs; "
                           "only 2 of 11 source papers priced indirect cost.",
                           verified=True),
    "professional": Figure(0.21, "x salary", "Boushey & Glynn 2012 (CAP), read in full",
                           "The median across 27 positions, excluding executives "
                           "and physicians. Direct costs.", verified=True),
    "scarce":       Figure(0.30, "x salary", "CAP median, stepped up",
                           "CAP excludes 'jobs requiring very specific skills' "
                           "from its median, so the median understates this row. "
                           "The step is ours and is not sourced.",
                           verified=False),
    "revenue":      Figure(0.25, "x salary", "CAP median, stepped up",
                           "Client loss is an indirect cost that 9 of the 11 "
                           "source papers did not price. The step is ours.",
                           verified=False),
    "leadership":   Figure(0.50, "x salary", "CAP senior-role band, floored",
                           "CAP reports senior roles running 'up to 213 percent' "
                           "and excludes them from the median for skewing it. "
                           "We take a deliberately low point in that band rather "
                           "than the top: a tool that tells a manager they are "
                           "worth 2x their salary to replace should be the most "
                           "conservative row, not the loudest.", verified=True),
}

#: The other side of the disagreement, carried so the tool can show a range
#: rather than assert a point. Same keys.
REPLACEMENT_COST_TRADE = {
    "frontline": 0.40, "professional": 1.25, "scarce": 2.00,
    "revenue": 1.25, "leadership": 2.13,
}

#: Why the gap exists, in one line the tool can show a person.
REPLACEMENT_DISAGREEMENT = (
    "Economic studies put the direct cost of replacing someone at about a fifth "
    "of their salary. Firms that sell retention software say one to two times, "
    "because they are also counting lost productivity and knowledge. Only 2 of "
    "the 11 underlying studies priced those at all, so the true figure for your "
    "role sits somewhere in that span. We show both ends."
)

#: Median days to fill an open role. Reported for context only — it is already
#: inside REPLACEMENT_COST and must never be added to it.
TIME_TO_FILL_DAYS = Figure(
    44, "days", "SHRM 2025 benchmarking via Mitratech",
    "Context only. Counting it separately would double-count vacancy.")

#: Typical budgeted increase, i.e. what you get for saying nothing.
BUDGETED_INCREASE = Figure(
    0.037, "share of salary", "Employer merit-budget surveys, 2025",
    "The counterfactual to negotiating, not a target.")


# ------------------------------------------- what our own simulation measured
#: research/molt. Pre-registered, 8 amendments, 29 predictions, 14 correct.
#: These are simulation outputs, NOT observations of real negotiations, and the
#: `verified` flag stays False for exactly that reason.
SIM = {
    "leverage_typical": Figure(
        13529, "usd, 3-year PV", "research/molt RESULTS-V6 addendum 3",
        "Negotiating vs signing the standing offer, population mean."),
    "leverage_with_provable_offer": Figure(
        33745, "usd, 3-year PV", "research/molt RESULTS-V6 addendum 3",
        "Holding an outside offer you can show."),
    "leverage_offer_and_costly_to_replace": Figure(
        44065, "usd, 3-year PV", "research/molt RESULTS-V6 addendum 3",
        "Offer in hand and above-median replacement cost."),
    "leverage_no_offer": Figure(
        5729, "usd, 3-year PV", "research/molt RESULTS-V6 addendum 3",
        "No alternative at all. Still positive — asking beats not asking."),
    "value_of_provable_offer": Figure(
        2851, "usd, 3-year PV", "research/molt RESULTS-V2",
        "Same person, forced to show the letter vs forced to stay quiet."),
    "value_of_unprovable_claim": Figure(
        0, "usd", "research/molt RESULTS-V2",
        "Claiming an offer you cannot show moved nothing, by construction of "
        "the equilibrium: claiming is free, so everyone claims."),
    "menu_over_haggling": Figure(
        1116, "usd, 3-year PV", "research/molt run10",
        "One sitting with a menu vs six weeks of sequential negotiation."),
    "days_saved": Figure(
        42, "days", "research/molt run10",
        "46.7 days of email and meetings vs 4.8, of which 3.8 is sign-off both ways."),
    "collapse_haggling": Figure(
        0.345, "share", "research/molt run10",
        "Negotiations that end with the person leaving, under six weeks of talks."),
    "collapse_one_sitting": Figure(
        0.160, "share", "research/molt run10",
        "The same, settled in one sitting."),
    "employer_band_value": Figure(
        8738, "usd, 2-season", "research/molt run11 (K44)",
        "What it costs an employer to reveal the packages it would equally "
        "sign. This is why you will not be handed a menu."),
}


def all_figures() -> list[tuple[str, Figure]]:
    """Every figure, flattened, for the verification checklist."""
    out: list[tuple[str, Figure]] = [
        ("share_who_never_ask", SHARE_WHO_NEVER_ASK),
        ("time_to_fill_days", TIME_TO_FILL_DAYS),
        ("budgeted_increase", BUDGETED_INCREASE),
    ]
    out += [(f"replacement_cost.{k}", v) for k, v in REPLACEMENT_COST.items()]
    out += [(f"sim.{k}", v) for k, v in SIM.items()]
    return out


VERIFY_BEFORE_LAUNCH = [
    "DONE: CAP source read in full. 11 papers 1992-2007, 31 case studies, 27 "
    "positions, median 21% excluding executives and physicians, 16% under $30k, "
    "senior roles up to 213%, only 2 of 11 papers priced indirect cost.",
    "DONE: `leadership` set to 0.50 from CAP's own senior-role band, taking a "
    "low point rather than the 213% top.",
    "OPEN: `scarce` and `revenue` are still our own steps off the median, not "
    "sourced. They are the two unverified rows left.",
    "OPEN: the underlying data is 1992-2007. Nothing newer was found. Decide "
    "whether a 20-year-old direct-cost median is fit to show a person in 2026.",
    "NOTE FOR research/molt: the simulation used rho = 0.45-1.60, taken from the "
    "trade side of this disagreement, and swept only down to 0.5x. If the "
    "academic median is right, the replacement channel — which is 80% of that "
    "study's headline — is inflated 2-4x, below the swept range. The study's "
    "limitations section must say so.",
    "Confirm the 55% never-negotiate figure against a primary survey. The "
    "aggregator cites survey data it does not link.",
    "Decide whether simulation figures may be shown to a person at all. They "
    "are labelled as ours throughout, but a reader may not keep the distinction "
    "between 'we measured this in a model' and 'this is what happens to you'.",
    "Have an employment lawyer read MUST_NOT_ASSERT. Nothing here is legal "
    "advice, and the retaliation caveat in particular needs checking against "
    "at-will employment realities.",
]

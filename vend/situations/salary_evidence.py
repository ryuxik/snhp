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

#: All-in cost of replacing someone, as a multiple of their salary. Gallup and
#: SHRM both give a 0.5-2.0x range; the shape (frontline low, leadership high)
#: is consistent across sources. THIS IS THE NUMBER THE ADVICE TURNS ON.
REPLACEMENT_COST = {
    "frontline":     Figure(0.45, "x salary", "Gallup / SHRM turnover-cost range",
                            "Includes vacancy and ramp; do not add those again."),
    "professional":  Figure(0.80, "x salary", "Gallup / SHRM turnover-cost range"),
    "scarce":        Figure(1.10, "x salary", "Gallup / SHRM turnover-cost range"),
    "revenue":       Figure(0.90, "x salary", "Gallup / SHRM turnover-cost range"),
    "leadership":    Figure(1.60, "x salary", "Gallup / SHRM turnover-cost range"),
}

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
    "Replace the Gallup/SHRM replacement-cost range with a source you have read "
    "in full, per role family. This is the number every piece of advice here "
    "turns on; everything else is presentation.",
    "Confirm the 55% never-negotiate figure against a primary survey. The "
    "aggregator cites survey data it does not link.",
    "Decide whether simulation figures may be shown to a person at all. They "
    "are labelled as ours throughout, but a reader may not keep the distinction "
    "between 'we measured this in a model' and 'this is what happens to you'.",
    "Have an employment lawyer read MUST_NOT_ASSERT. Nothing here is legal "
    "advice, and the retaliation caveat in particular needs checking against "
    "at-will employment realities.",
]

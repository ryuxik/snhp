"""Legal/regulatory layer for the rent-renewal advisor.

THE HARD RULE OF THIS MODULE: it tells a renter HOW TO CHECK. It never
tells them what their legal status IS.

Rent regulation turns on facts we cannot see (a building's registration
history, a unit's individual improvement history, a tax-benefit rider on
a specific address). Asserting "you are rent stabilized" or "this
increase is illegal" to someone who is neither would be worse than
useless — it would send them into a confrontation holding a false
premise. So every jurisdiction returns *screening indicators* and
*official verification paths*, and the advisor's copy is written in the
conditional.

Any figure that determines whether a renter believes their increase is
lawful is gated behind `verified: bool` and is omitted entirely until
confirmed against a primary government source. A wrong number here is a
harm, not a bug.

REFRESH CADENCE: annual per regulated jurisdiction, plus on statutory
change. Regulated jurisdictions carry a permanent maintenance
obligation — see RENEWAL-SPEC.md before adding more of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerificationStep:
    """One concrete action a renter can take to establish a fact for
    themselves. `where` must be an official source, never a blog."""

    action: str
    where: str
    note: str = ""


@dataclass(frozen=True)
class Jurisdiction:
    """What we can honestly say about renewal rules in one place.

    `regulated_stock_note` describes the possibility of regulation, in
    the conditional. `screening_indicators` are things that RAISE THE
    QUESTION — never things that settle it.
    """

    key: str
    name: str
    has_regulated_stock: bool
    regulated_stock_note: str = ""
    screening_indicators: tuple[str, ...] = ()
    verification: tuple[VerificationStep, ...] = ()
    caveats: tuple[str, ...] = ()
    # Rate data stays absent until confirmed against a primary source.
    rates_verified: bool = False
    rates: dict = field(default_factory=dict)
    rates_source: str = ""
    rates_as_of: str = ""


_DEFAULT = Jurisdiction(
    key="default",
    name="United States (general)",
    has_regulated_stock=False,
    regulated_stock_note=(
        "Most US rental housing has no cap on renewal increases. Your "
        "leverage is market-based, not legal."
    ),
    caveats=(
        "Notice requirements for rent increases vary by state and city; "
        "check your state's rules if the increase arrived with little "
        "warning.",
    ),
)


# ── NYC Rent Guidelines Board orders ────────────────────────────────
# VERIFIED 2026-07-24 against rentguidelinesboard.cityofnewyork.us.
#
# THE ORDER IS KEYED TO LEASE COMMENCEMENT DATE — not the offer date and
# not the signature date. This is the single easiest silent bug in the
# whole product: we are currently inside an overlap window where an offer
# arriving today may govern a lease starting under either order.
#
# Order #58 is a FULL FREEZE (0%/0%), which is unusual enough that the
# researcher confirmed it on two separate RGB pages.
RGB_ORDERS = (
    {
        "order": 58,
        "commencing_from": "2026-10-01",
        "commencing_to": "2027-09-30",
        "one_year_pct": 0.0,
        "two_year_pct": 0.0,
        "url": "https://rentguidelinesboard.cityofnewyork.us/2026-27-apartment-loft-order-58/",
    },
    {
        "order": 57,
        "commencing_from": "2025-10-01",
        "commencing_to": "2026-09-30",
        "one_year_pct": 3.0,
        "two_year_pct": 4.5,
        "url": "https://rentguidelinesboard.cityofnewyork.us/2025-26-apartment-loft-order-57/",
    },
)
RGB_VERIFIED_ON = "2026-07-24"
RGB_REFRESH = "Annually: the board votes in late June; the new order takes effect Oct 1."


def rgb_order_for(lease_start_iso: str | None) -> dict | None:
    """Which RGB guideline governs a lease starting on this date.

    Returns None when we can't tell — the caller must then ASK for the
    commencement date rather than guess, because guessing across the
    Oct 1 boundary flips a tenant between 3% and 0%.
    """
    if not lease_start_iso:
        return None
    for o in RGB_ORDERS:
        if o["commencing_from"] <= lease_start_iso <= o["commencing_to"]:
            return o
    return None


# Good Cause Eviction (RPL Art. 6-A). Applies in NYC automatically; all
# units are ASSUMED covered, subject to 15 exemptions the landlord
# asserts. The rent standard is a REBUTTABLE PRESUMPTION raised as a
# defense in Housing Court — NOT a cap. Framing it as a cap would lead
# tenants to refuse rent they lawfully owe.
GCE_LOCAL_RENT_STANDARD_PCT = 8.38  # 5% + CPI 3.38% (DHCR notice, 2026-05-04)
GCE_STANDARD_VERIFIED_ON = "2026-07-24"
GCE_STANDARD_SOURCE = "https://hcr.ny.gov/good-cause-eviction-law-notice-may-2026"
GCE_REFRESH_URGENT = (
    "DHCR must publish updated FMR tables and the CPI figure on or before "
    "August 1 each year. The figure above is from the May 2026 notice and "
    "should be re-checked imminently. Note the NY Attorney General's own "
    "published booklet currently shows a STALE 8.82% — an official page "
    "being out of date is the normal case here, not the exception."
)

# RPL § 226-c — applies to UNREGULATED units too, and almost no market-
# rate tenant knows it exists. Notice is keyed to the longer of
# cumulative occupancy or lease term.
NOTICE_RULE = (
    (12, 30),    # under 1 year -> 30 days
    (24, 60),    # 1-2 years    -> 60 days
    (None, 90),  # over 2 years -> 90 days
)


def notice_days_required(months_at_address: int) -> int:
    """Days of advance written notice a NYC landlord owes before a
    renewal increase of 5% or more (RPL § 226-c)."""
    for threshold, days in NOTICE_RULE:
        if threshold is None or months_at_address < threshold:
            return days
    return 90


_NYC = Jurisdiction(
    key="new_york",
    name="New York City",
    has_regulated_stock=True,
    regulated_stock_note=(
        "A large share of NYC apartments are rent stabilized. For those "
        "units the renewal increase is set annually by the Rent "
        "Guidelines Board, not by the landlord — and many tenants do not "
        "know which category they are in."
    ),
    screening_indicators=(
        "Your building is older and contains many apartments (stabilization "
        "generally applies to larger, older buildings — but the thresholds "
        "have exceptions, so this is a reason to check, not an answer).",
        "Your building received a tax benefit (such as 421-a or 485-x), "
        "which can bring otherwise-unregulated units into regulation.",
        "Your lease renewal arrived on a standard printed form rather than "
        "a letter — regulated renewals use an official form.",
        "You have seen the term 'preferential rent' or a 'legal regulated "
        "rent' distinct from what you actually pay.",
    ),
    verification=(
        VerificationStep(
            action="Request your apartment's official rent history",
            where="NY State Homes and Community Renewal (HCR/DHCR)",
            note=(
                "This is the authoritative record. It shows whether the unit "
                "is registered as stabilized and what rents were registered "
                "over time. It is free to request."
            ),
        ),
        VerificationStep(
            action="Ask your landlord in writing whether the unit is rent stabilized",
            where="In writing, to your landlord or managing agent",
            note="Creates a paper record regardless of the answer.",
        ),
    ),
    caveats=(
        "Rent regulation status depends on facts about your specific unit "
        "and building that cannot be determined from the outside. Treat "
        "everything here as a prompt to verify, not a conclusion.",
        "A rent history shows what the owner REGISTERED — DHCR states it "
        "'does not represent a determination of the lawful rent for your "
        "apartment.' The registered figure can itself be the overcharge.",
        "Lawful increases can stack on top of the guideline (building-wide "
        "improvement and apartment-improvement increases), so a renewal "
        "above the guideline percentage is not automatically an overcharge.",
        "Never withhold rent on the strength of anything here. If your "
        "landlord fails to return a signed renewal, the official guidance "
        "is to pay the new rent and file the complaint form.",
        "This is information, not legal advice. For a dispute, contact a "
        "tenant attorney or a legal services organization.",
    ),
    rates_verified=True,
    rates_as_of=RGB_VERIFIED_ON,
    rates_source="NYC Rent Guidelines Board; NYS HCR; RPL Art. 6-A",
    rates={
        "rgb_orders": RGB_ORDERS,
        "rgb_note": (
            "These percentages apply ONLY to rent-stabilized apartments, and "
            "which one applies is decided by the date your NEW LEASE STARTS "
            "— not when the offer arrived. Leases starting on or after "
            "Oct 1, 2026 fall under a 0% guideline."
        ),
        "good_cause": {
            "local_rent_standard_pct": GCE_LOCAL_RENT_STANDARD_PCT,
            "what_it_is": (
                "For units covered by the Good Cause Eviction law, an "
                "increase above this figure is presumed unreasonable — a "
                "defense you can raise in Housing Court, NOT a cap. The "
                "landlord can rebut it by showing costs like taxes or major "
                "repairs, and many buildings are exempt."
            ),
            "how_to_tell_if_covered": (
                "Your landlord is required to attach a notice to your lease "
                "stating whether Good Cause applies to your unit and, if "
                "not, why not. That notice is your evidence — look for it "
                "before assuming either way."
            ),
            "source": GCE_STANDARD_SOURCE,
            "freshness_warning": GCE_REFRESH_URGENT,
        },
        "notice_rights": {
            "applies_to": "ALL New York tenants, including unregulated ones",
            "rule": (
                "If your landlord wants to raise the rent by 5% or more, "
                "state law requires advance written notice — 30 days if "
                "you've been there under a year, 60 days for 1–2 years, "
                "90 days beyond that. If they miss it, your existing terms "
                "continue until the notice period runs out."
            ),
            "statute": "NY Real Property Law § 226-c",
        },
        "renewal_deadlines": {
            "offer_window": (
                "For stabilized apartments the renewal offer must arrive "
                "90–150 days before your lease expires, on official form "
                "RTP-8."
            ),
            "your_deadline_days": 60,
            "warning": (
                "The 60-day response window is real: if you don't return the "
                "signed renewal in time, the owner may refuse to renew and "
                "start an eviction proceeding. Don't let it lapse while you "
                "negotiate — negotiate and return it."
            ),
        },
        "preferential_rent": (
            "If you were paying a 'preferential rent' (below the legal "
            "regulated rent) as of June 14, 2019, you keep it for the life "
            "of your tenancy — a landlord can no longer jump you to the "
            "legal rent at renewal. Some government-financed affordable "
            "programs are carved out."
        ),
    },
)


_JURISDICTIONS: dict[str, Jurisdiction] = {
    "new_york": _NYC,
    "default": _DEFAULT,
}

# Metro key -> jurisdiction key. Absent means _DEFAULT, which is correct
# for the deregulated Sun Belt metros where this product works best.
_METRO_TO_JURISDICTION = {
    "new_york": "new_york",
}


def for_metro(metro_key: str) -> Jurisdiction:
    """Resolve the legal layer for a metro, defaulting to unregulated.

    Defaulting to 'no regulation' is the safe direction: it understates
    a renter's legal position rather than inventing one.
    """
    norm = metro_key.lower().replace(" ", "_").replace("-", "_")
    return _JURISDICTIONS[_METRO_TO_JURISDICTION.get(norm, "default")]


def legal_block(metro_key: str) -> dict:
    """Renter-facing legal context. Never asserts status."""
    j = for_metro(metro_key)
    out = {
        "jurisdiction": j.name,
        "may_be_regulated": j.has_regulated_stock,
        "note": j.regulated_stock_note,
        "caveats": list(j.caveats),
    }
    if j.has_regulated_stock:
        out["worth_checking_if"] = list(j.screening_indicators)
        out["how_to_verify"] = [
            {"action": v.action, "where": v.where, "note": v.note}
            for v in j.verification
        ]
        # Rates appear only once confirmed against a primary source.
        if j.rates_verified:
            out["official_rates"] = j.rates
            out["rates_source"] = j.rates_source
            out["rates_as_of"] = j.rates_as_of
        else:
            out["official_rates_status"] = (
                "Not yet published in this tool. The official current rate is "
                "set by the local rent board — check the board's own site "
                "rather than relying on any third party, including us."
            )
    return out

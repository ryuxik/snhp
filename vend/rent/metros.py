"""Metro market profiles for the rent-renewal advisor.

THE MARKET LAYER. Deliberately separated from the jurisdiction (legal)
layer and the shared engine, so adding a metro is a data edit and adding
a state is a rules module — never a rewrite.

Source of record: Zillow April 2026 Rental Report (concession share by
metro, YoY change, typical rent), cross-checked against Yardi Matrix
June 2026 and RealPage May/June 2026 for rent direction.

REFRESH CADENCE: quarterly. `AS_OF` below is load-bearing — a stale
concession share understates or overstates a renter's position, so the
advisor surfaces the date rather than hiding it.

IMPORTANT METHODOLOGY NOTE (do not "fix" by averaging):
Zillow's concession share counts LISTINGS (incl. single-family and small
landlords). RealPage's ~16.5% counts STABILIZED conventional apartments
only. They are different denominators, not a contradiction, and must
never be mixed in one number. We use Zillow because the renter's
comparison set is "what is advertised near me," which is the listing
universe.
"""

from __future__ import annotations

from dataclasses import dataclass

AS_OF = "2026-04"  # Zillow April 2026 report; refresh quarterly
SOURCE = "Zillow April 2026 Rental Report; rent direction cross-checked vs Yardi Matrix Jun 2026 + RealPage May 2026"

# National context (RealPage Q2 2026 / Jun 2026, stabilized universe)
NATIONAL_CONCESSION_DISCOUNT_PCT = 11.1   # avg discount where a concession IS offered
NATIONAL_CONCESSION_WEEKS_FREE = 6.0      # ~"nearly six weeks free on a 12-month lease"
NATIONAL_LISTING_CONCESSION_SHARE = 39.7  # Zillow, Jun 2026
PRE_PANDEMIC_LISTING_SHARE = 16.5         # ~1 in 6, Zillow's own framing


@dataclass(frozen=True)
class Metro:
    """One metro's renter-side market position.

    concession_share: % of Zillow listings advertising a concession.
    concession_yoy_pp: percentage-point change vs prior year. NEGATIVE
        means the market is TIGHTENING against the renter — a leading
        signal that matters more than the level (see SF).
    typical_rent: Zillow typical asking rent, USD/mo.
    rent_yoy_note: direction of rent growth, for honest framing.
    """

    name: str
    concession_share: float
    concession_yoy_pp: float
    typical_rent: int
    rent_yoy_note: str = ""

    @property
    def tier(self) -> str:
        """Renter's structural position. Thresholds are judgment calls,
        set so that 'strong' means concessions are the norm rather than
        the exception, and 'weak' means asking is likely to fail."""
        if self.concession_share >= 50.0:
            return "strong"
        if self.concession_share >= 30.0:
            return "moderate"
        return "weak"

    @property
    def tightening(self) -> bool:
        """Market moving against the renter regardless of level."""
        return self.concession_yoy_pp <= -2.0


# Ordered by concession share, descending. Full Zillow top-50, Apr 2026.
METROS: dict[str, Metro] = {
    m.name.lower().replace(" ", "_"): m
    for m in [
        Metro("Denver", 68.3, 5.8, 1887, "negative (-3.1% Yardi)"),
        Metro("Charlotte", 66.6, 2.0, 1733, "negative (-1.6% Yardi)"),
        Metro("Dallas", 64.2, 10.4, 1660, "negative (-1.9% Yardi)"),
        Metro("Austin", 63.8, 1.0, 1604, "negative but INFLECTING UP (+1.3% Q2'26)"),
        Metro("Raleigh", 62.9, 2.9, 1674),
        Metro("Nashville", 62.6, 5.2, 1784, "negative (-1.7% Yardi)"),
        Metro("Salt Lake City", 62.5, 3.1, 1631),
        Metro("Phoenix", 59.9, 8.4, 1741, "negative (-2.7% Yardi)"),
        Metro("Atlanta", 59.1, 4.9, 1825),
        Metro("Washington DC", 57.9, 6.9, 2375),
        Metro("San Antonio", 55.6, 4.9, 1398, "negative (-3.5% Yardi, worst in US)"),
        Metro("Seattle", 54.2, 5.4, 2208),
        Metro("Orlando", 53.4, 4.7, 1963),
        Metro("Las Vegas", 53.0, 10.1, 1734),
        Metro("Houston", 51.8, 5.5, 1619, "negative (-2.0% Yardi)"),
        Metro("Tampa", 50.4, 10.3, 1997, "negative (-2.8% Yardi)"),
        Metro("Portland", 49.0, 5.1, 1789),
        Metro("Indianapolis", 48.9, 12.2, 1517),
        Metro("Jacksonville", 48.9, 1.0, 1692),
        Metro("Richmond", 48.0, 7.9, 1736),
        Metro("Columbus", 47.1, 12.6, 1516),
        Metro("Birmingham", 43.7, 17.7, 1422),
        Metro("Memphis", 43.0, 13.1, 1432),
        Metro("Louisville", 42.5, 10.0, 1377),
        Metro("Minneapolis", 39.1, -0.9, 1698),
        Metro("San Diego", 38.0, 7.0, 2914),
        Metro("Baltimore", 37.7, -3.6, 1894),
        Metro("Kansas City", 35.3, 7.3, 1526, "positive (+2.4% Yardi)"),
        Metro("Philadelphia", 34.3, 3.0, 1901),
        Metro("San Jose", 32.5, -6.5, 3534, "positive (+4.5% Yardi) — TIGHTENING"),
        Metro("Sacramento", 31.6, 4.3, 2258),
        Metro("Boston", 31.1, 8.2, 3184),
        Metro("Los Angeles", 30.9, 3.9, 2892),
        Metro("Oklahoma City", 30.9, 6.2, 1392),
        Metro("Virginia Beach", 30.7, 4.4, 1843),
        Metro("Miami", 28.9, 5.4, 2683),
        Metro("Riverside", 28.7, 2.7, 2510),
        Metro("Cincinnati", 28.6, 8.2, 1557),
        Metro("San Francisco", 27.1, -8.0, 3206, "STRONGLY positive (+4.7% to +10.6%) — TIGHTENING FAST"),
        Metro("Pittsburgh", 27.1, 5.9, 1507),
        Metro("St Louis", 26.8, 3.9, 1436),
        Metro("Cleveland", 26.3, 4.2, 1441, "positive (+1.9% Yardi)"),
        Metro("Detroit", 26.1, 2.1, 1481),
        Metro("Hartford", 24.9, 6.4, 1940),
        Metro("Milwaukee", 22.9, -0.4, 1540, "positive (+2.5% Yardi)"),
        Metro("Chicago", 21.7, -0.1, 2219, "positive (+2.6% Yardi)"),
        Metro("New Orleans", 19.2, 8.1, 1615),
        Metro("New York", 18.4, 1.7, 3406, "positive (+5.6% Yardi) — legal wedge only"),
        Metro("Providence", 12.6, 2.3, 2154),
        Metro("Buffalo", 11.1, 2.2, 1417),
    ]
}


def lookup(metro_key: str) -> Metro | None:
    """Fetch a metro profile. Returns None for unknown metros — the
    advisor must then fall back to national context rather than
    inventing a local number."""
    return METROS.get(metro_key.lower().replace(" ", "_").replace("-", "_"))


def market_context(metro_key: str) -> dict:
    """Renter-facing market framing for one metro, honest about absence.

    Never fabricates a local figure: an unknown metro degrades to
    national context with `metro_known=False` so the caller can say so.
    """
    m = lookup(metro_key)
    if m is None:
        return {
            "metro_known": False,
            "as_of": AS_OF,
            "national_listing_concession_share": NATIONAL_LISTING_CONCESSION_SHARE,
            "national_avg_discount_pct": NATIONAL_CONCESSION_DISCOUNT_PCT,
            "note": (
                "No metro-level data on file. Using national context only: "
                f"~{NATIONAL_LISTING_CONCESSION_SHARE:.0f}% of listings nationally "
                "advertise a concession."
            ),
        }
    return {
        "metro_known": True,
        "metro": m.name,
        "as_of": AS_OF,
        "concession_share_pct": m.concession_share,
        "concession_yoy_pp": m.concession_yoy_pp,
        "typical_rent": m.typical_rent,
        "tier": m.tier,
        "tightening": m.tightening,
        "rent_direction": m.rent_yoy_note or "not separately verified",
        "source": SOURCE,
    }

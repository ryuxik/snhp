"""Configuration for the PAPERSWARM desk.

All economically load-bearing constants live here so that the honesty
protocol (SPEC.md "The honesty protocol") is one auditable file, not
magic numbers scattered across the engine. Niche is a config, not an
architecture (SPEC.md "Venue and why").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"          # gitignored; sqlite + ledger live here
FIXTURE_DIR = PKG_DIR / "fixtures"   # checked-in sample payloads (FIXTURE mode)

DB_PATH = DATA_DIR / "paperswarm.db"
LEDGER_PATH = DATA_DIR / "ledger.jsonl"


# ---------------------------------------------------------------------------
# Launch niche (SPEC.md: PSA-graded Pokémon; niche is a config)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Niche:
    key: str
    search_query: str
    category_ids: str          # eBay category filter (Trading Card Singles)
    ebay_marketplace: str = "EBAY_US"


LAUNCH_NICHE = Niche(
    key="psa_pokemon",
    search_query="PSA Pokemon graded card",
    category_ids="183454",  # CCG Individual Cards
)


# ---------------------------------------------------------------------------
# eBay Browse API (SPEC.md Phase 1: "Browse API poller ... no restricted APIs")
# ---------------------------------------------------------------------------
EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"
EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Client-credentials app token. Absent env -> FIXTURE mode (SPEC-safe offline).
EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")


def fixture_mode() -> bool:
    """True when API keys are absent -> serve checked-in fixtures.

    Lets the whole desk test without keys (task requirement) and keeps
    CI offline-green.
    """
    return not (EBAY_CLIENT_ID and EBAY_CLIENT_SECRET)


# ---------------------------------------------------------------------------
# Honesty-protocol economics (SPEC.md "The honesty protocol")
# ---------------------------------------------------------------------------

# BUY: max bid must be committed at least this long before close.
BID_CUTOFF_SECONDS = 60

# Bankroll realism.
BANKROLL_USD = 2000.00

# Friction on a SELL (SPEC: 13.25% fees + $5 shipping + 3% payment).
FEE_RATE = 0.1325          # eBay final-value fee
PAYMENT_RATE = 0.03        # payment processing
SHIPPING_USD = 5.00        # flat shipping cost we eat
FRICTION_RATE = FEE_RATE + PAYMENT_RATE  # multiplicative portion

# SELL mark model.
MARK_PERCENTILE = 25       # 25th percentile of realized comps
COMP_WINDOW_DAYS = 14      # trailing window for marks
MIN_COMPS_FOR_MARK = 5     # < this -> position marks at ZERO (no fantasy)

# Cold-start: refuse bids until the comp store spans this many days.
COLD_START_DAYS = 7

# Metered compute charged against P&L (SPEC: "energy is not free").
API_CALL_COST_USD = 0.0005     # per eBay API request
LLM_CALL_COST_USD = 0.0100     # per haiku-class identity extraction

# Treasury / risk caps.
MAX_EXPOSURE_FRACTION = 0.25   # no single locked bid may exceed this of bankroll
MAX_CONCURRENT_LOCKS = 8       # portfolio breadth cap


# ---------------------------------------------------------------------------
# Pricer (SPEC.md swarm: fair value = median trailing comps; max bid discounts it)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PricerConfig:
    # Fair value = median of trailing realized comps.
    # Max bid = fair_value * margin_requirement (we demand a margin of safety).
    margin_requirement: float = 0.70   # bid <= 70% of fair value -> >=30% headroom
    comp_window_days: int = COMP_WINDOW_DAYS
    min_comps: int = MIN_COMPS_FOR_MARK


DEFAULT_PRICER = PricerConfig()


# ---------------------------------------------------------------------------
# eBay standard bid-increment table (SPEC: fill at "hammer + one increment").
# Source: eBay published automatic-bidding increments (USD).
# ---------------------------------------------------------------------------
# (upper_bound_exclusive, increment). Last tuple is the open-ended top band.
BID_INCREMENT_TABLE: tuple[tuple[float, float], ...] = (
    (1.00, 0.05),
    (5.00, 0.25),
    (25.00, 0.50),
    (100.00, 1.00),
    (250.00, 2.50),
    (500.00, 5.00),
    (1000.00, 10.00),
    (2500.00, 25.00),
    (5000.00, 50.00),
    (float("inf"), 100.00),
)


def bid_increment(price: float) -> float:
    """One eBay bid-increment step for a given price band.

    Enforces SPEC BUY rule: win price = hammer + one increment.
    """
    for upper, inc in BID_INCREMENT_TABLE:
        if price < upper:
            return inc
    return 100.00  # unreachable; inf band above


# Optional per-field env overrides (kept minimal & explicit).
@dataclass
class RuntimeConfig:
    niche: Niche = field(default_factory=lambda: LAUNCH_NICHE)
    pricer: PricerConfig = field(default_factory=lambda: DEFAULT_PRICER)
    bankroll: float = BANKROLL_USD
    cold_start_days: int = COLD_START_DAYS


DEFAULT = RuntimeConfig()

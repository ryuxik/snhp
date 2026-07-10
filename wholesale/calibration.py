"""WHOLESALE TIER calibration — the ONE source of truth for the block's
B2B economics: rate cards, route costs, delivery windows, payment terms,
storage, and the cash-and-carry outside option.

Venue demand SCALES come from block/calibration.py (the block's one source
of truth for retail volumes) and are converted to weekly CASE demand via
documented share x units-per-case assumptions. Everything wholesale-side
(rate cards, truck economics, financing) is a local constant chosen to be
defensible in a pilot conversation; each is a calibration TARGET to be
replaced by real distributor rate cards / route sheets when a pilot lands.
"""
from block import calibration as _blk

# ── the players ──────────────────────────────────────────────────────────
# Processing order is FIXED (dispatch and negotiation both walk venues in
# this order every week) — determinism, and the industry's "route sheet".
W_ORDER = ("beverage", "produce", "dry")
V_ORDER = ("bodega", "boba", "vending", "bakery")

# Wholesalers: base = rate-card case price ($); breaks = published volume
# discounts, highest threshold first (min cases, fraction of base);
# cogs_frac x base = marginal cost of goods per case; moq in cases.
WHOLESALERS = {
    "beverage": dict(base=24.0, cogs_frac=0.78, perishable=False,
                     breaks=((25, 0.92), (10, 0.96), (0, 1.0)), moq=5),
    "produce":  dict(base=32.0, cogs_frac=0.72, perishable=True,
                     breaks=((20, 0.94), (8, 0.97), (0, 1.0)), moq=4),
    "dry":      dict(base=18.0, cogs_frac=0.70, perishable=False,
                     breaks=((25, 0.91), (12, 0.95), (0, 1.0)), moq=4),
}

# ── weekly case demand, derived from block/calibration.py ────────────────
# The vending machine restocks nightly to par and (per block RESULTS-B0)
# roughly sells through — daily replenishment ~ par units/day.
_PAR = {sku: par for (sku, _mu, _cost, _salv, _life, par)
        in _blk.VENDING_CATALOG}
_VEND_BEV_UNITS = _PAR["cola-20oz"] + _PAR["water-1L"] + _PAR["energy"]  # 32
_VEND_DRY_UNITS = _PAR["chips"] + _PAR["candy"]                          # 20
_VEND_FRESH_UNITS = _PAR["sandwich"] + _PAR["fruit-cup"]                 # 12

# The bakery-like deli is DESIGN 4c's "first to add" venue — not yet in
# block/calibration.py, so its scale is a local constant between the boba
# shop (260 tx/day) and the bodega (550 tx/day).
BAKERY_DAILY_TX = 300


def _weekly_cases(daily_units: float, units_per_case: float) -> float:
    return round(daily_units * 7.0 / units_per_case, 1)


# (wholesaler, venue) -> mean weekly case demand. Shares are category
# shares of the venue's transactions; units_per_case is the composite
# "supplier case" for that category (documented per line).
DEMAND_MU = {
    # beverage: bodega ~30% of 550 tx are drinks, 24 x 20oz per case
    ("beverage", "bodega"):  _weekly_cases(_blk.BODEGA_DAILY_TX * 0.30, 24),
    ("beverage", "boba"):    4.0,   # bottled-drink sideline (local constant)
    ("beverage", "vending"): _weekly_cases(_VEND_BEV_UNITS, 24),
    ("beverage", "bakery"):  10.0,  # fridge-drink case (local constant)
    # produce/deli: bodega ~45% of tx are deli items, ~40 servings/case
    ("produce", "bodega"):   _weekly_cases(_blk.BODEGA_DAILY_TX * 0.45, 40),
    ("produce", "boba"):     _weekly_cases(_blk.BOBA_DAILY_CUPS, 75),  # milk/fruit
    ("produce", "vending"):  _weekly_cases(_VEND_FRESH_UNITS, 12),     # fresh case
    ("produce", "bakery"):   _weekly_cases(BAKERY_DAILY_TX * 0.50, 28),
    # dry goods: chips/candy/paper (bodega), tea/tapioca/cups (boba), flour
    ("dry", "bodega"):       _weekly_cases(_blk.BODEGA_DAILY_TX * 0.15, 30),
    ("dry", "boba"):         _weekly_cases(_blk.BOBA_DAILY_CUPS, 130),
    ("dry", "vending"):      _weekly_cases(_VEND_DRY_UNITS, 24),
    ("dry", "bakery"):       _weekly_cases(BAKERY_DAILY_TX * 0.35, 46),
}

# storage cap in cases (walk-in / backroom / operator van limits)
STORAGE_CAP = {
    ("beverage", "bodega"): 60, ("beverage", "boba"): 10,
    ("beverage", "vending"): 16, ("beverage", "bakery"): 15,
    ("produce", "bodega"): 55, ("produce", "boba"): 35,
    ("produce", "vending"): 12, ("produce", "bakery"): 50,
    ("dry", "bodega"): 30, ("dry", "boba"): 25,
    ("dry", "vending"): 12, ("dry", "bakery"): 28,
}

# venue retail value per case, as a multiple of the rate-card base — the
# case's ATTRIBUTABLE gross value at retail (net of the venue's labor and
# other inputs), NOT the shelf price of its contents. Anchored loosely to
# block margins (e.g. bodega cola $3.25 retail vs ~$1.00/unit wholesale,
# haircut for shrink/labor).
RETAIL_MULT = {
    ("beverage", "bodega"): 2.6, ("beverage", "boba"): 1.8,
    ("beverage", "vending"): 2.5, ("beverage", "bakery"): 2.2,
    ("produce", "bodega"): 2.0, ("produce", "boba"): 2.6,
    ("produce", "vending"): 2.2, ("produce", "bakery"): 2.1,
    ("dry", "bodega"): 2.2, ("dry", "boba"): 2.8,
    ("dry", "vending"): 2.6, ("dry", "bakery"): 2.0,
}

# ── venues: cash, receiving labor, window preferences ────────────────────
# fin_rate: the venue's implied monthly financing value of delayed payment
# (~1.5%/mo center per DESIGN 4b; spread reflects cash tightness — the
# bodega runs tightest, the vending operator is cash-rich).
# recv_penalty: extra receiving labor ($) when delivery lands outside the
# venue's low-cost windows (staff called in / prep interrupted).
# pref: window indices best-first (window index = day*2 + half; Mon-AM=0,
# Mon-PM=1, ..., Fri-PM=9). Mornings dominate: deli prep, pre-open boba,
# early bakes. The vending operator restocks evenings and prefers PM.
VENUES = {
    "bodega":  dict(fin_rate=0.025, recv_penalty=30.0,
                    pref=(0, 2, 4, 6, 8, 1, 3, 5, 7, 9)),
    "boba":    dict(fin_rate=0.015, recv_penalty=25.0,
                    pref=(8, 6, 4, 2, 0, 9, 7, 5, 3, 1)),   # weekend-heavy
    "vending": dict(fin_rate=0.010, recv_penalty=15.0,
                    pref=(1, 3, 5, 7, 9, 0, 2, 4, 6, 8)),
    "bakery":  dict(fin_rate=0.020, recv_penalty=40.0,
                    pref=(0, 2, 4, 6, 8, 1, 3, 5, 7, 9)),
}

# venue flexibility share (grid axis): fraction of the 10 weekly windows
# the venue can receive at zero extra labor (its top-preference windows);
# the rest cost recv_penalty.
FLEX_GRID = (0.3, 0.7)

# ── route economics (the truck) ──────────────────────────────────────────
STOP_COST = 45.0        # marginal cost of one truck stop on the block
DROP_COST = 8.0         # marginal cost of an EXTRA drop at an existing stop
SHADOW_AM = 18.0        # opportunity cost of an AM block stop (mornings scarce)
SHADOW_PM = 6.0
AM_STOPS_PER_WEEK = 2   # per wholesaler: block AM stops the route can absorb
# one physical stop max per (wholesaler, window); extra venues in the same
# window ride as drops on that stop — route density, modeled explicitly.

# ── payment terms ────────────────────────────────────────────────────────
TERMS = ("cod", "net15", "net30")
PUBLISHED_TERMS = ("cod", "net15")   # net-30 requires negotiated credit
COD_DISCOUNT = 0.02                  # "COD -2%" off the invoice
NET15_MONTHS = 0.5
NET30_MONTHS = 1.0
WHOLESALER_FIN_RATE = 0.008          # distributor's monthly cost of carry

# ── perishability ────────────────────────────────────────────────────────
# durable cases carry to next week at a holding/shrink haircut (salvage
# fraction of the rate-card base); perishables spoil (salvage 0).
DURABLE_SALVAGE_FRAC = 0.85
SPOIL_SHARE_OPTIONS = (0.0, 0.5)     # none | 50/50 on perishables

# ── the cash-and-carry outside option (Jetro) ────────────────────────────
JETRO_PRICE_FRAC = 0.93              # x rate-card base, no volume breaks
JETRO_HAUL = 60.0                    # van + gas + parking, per weekly run
JETRO_TIME = 35.0                    # owner hours burned, per weekly run
# Jetro is COD at the shelf price (no COD discount, no financing value),
# no MOQ, no delivery window (their own haul).

# ── negotiation (nego arms) ──────────────────────────────────────────────
PRICE_RUNGS = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10)  # discount off break price
BUFFER_MIN = 5.0                     # wholesaler's don't-negotiate-for-pennies
BUFFER_FRAC = 0.03                   # ...as max($5, 3% of order list value)
N_QTY_RUNGS = 14                     # case-quantity rungs from MOQ to cap

# ── demand model / experiment grid ───────────────────────────────────────
SIGMA_FORECAST = 0.10   # weekly venue-level demand forecast factor (lognormal)
NOISE_GRID = (0.15, 0.35)            # sigma of within-week demand vs forecast
BASE_NOISE, BASE_FLEX = 0.15, 0.7    # the headline cell

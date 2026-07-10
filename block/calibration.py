"""NYC calibration — the ONE source of truth for the block's prices, costs,
traffic, and rents. Values are 2026 Manhattan (Midtown-adjacent mixed
block) estimates chosen to be defensible in a pilot conversation; each
constant is a calibration TARGET to be replaced by real POS/DEX data when a
pilot lands (see vend/BOBA.md pilot shape).
"""

# ── vending machine (office-lobby, NYC pricing) ──────────────────────────
# (sku, wtp_mu $, unit_cost $, salvage $, shelf_life_days, par)
VENDING_CATALOG = [
    ("cola-20oz",  3.40, 1.10, 0.15, 60, 12),
    ("water-1L",   2.60, 0.45, 0.05, 90, 12),
    ("chips",      2.75, 0.85, 0.10, 30, 10),
    ("candy",      2.90, 0.80, 0.10, 45, 10),
    ("energy",     4.90, 1.60, 0.20, 60,  8),
    ("sandwich",   9.75, 3.80, 0.50,  2,  6),   # fresh case
    ("fruit-cup",  6.25, 2.30, 0.30,  3,  6),
]
VENDING_DAILY_ARRIVALS = 70          # lobby machine, weekday

# ── bodega (now a first-class venue — the block's outside option) ────────
BODEGA_CATALOG = [
    ("chopped-cheese", 9.50, 3.20),  # (item, price, cost)
    ("BEC",            6.75, 2.10),
    ("deli-sandwich", 11.50, 4.10),
    ("cola-20oz",      3.25, 1.05),
    ("coffee",         2.00, 0.40),
    ("chips",          2.50, 0.85),
]
BODEGA_DAILY_TX = 550
BODEGA_RENT_PER_DAY = 400            # ~$12k/mo storefront

# ── boba shop (St. Marks tier) ───────────────────────────────────────────
BOBA_MENU = [
    ("classic-milk-tea", 6.25, 1.35),
    ("fruit-tea",        6.75, 1.50),
    ("brown-sugar",      7.25, 1.60),
    ("matcha-latte",     7.50, 1.75),
]
BOBA_TOPPINGS = [("pearls", 0.85, 0.10), ("pudding", 0.95, 0.15),
                 ("grass-jelly", 0.85, 0.12), ("cheese-foam", 1.25, 0.25)]
BOBA_CAPACITY_PER_MIN = 1.5          # 2 staff peak
BOBA_TAPIOCA_BATCH = 40              # servings, ~4h quality life
BOBA_DAILY_CUPS = 260
BOBA_RENT_PER_DAY = 330

# ── fashion boutique (LES independent) ───────────────────────────────────
FASHION_LINES = [
    ("graphic-tee", 42.0, 13.0),     # (style, MSRP, landed cost)
    ("hoodie",      92.0, 31.0),
    ("wide-pants",  98.0, 33.0),
    ("slip-dress", 128.0, 42.0),
]
FASHION_SALVAGE_FRAC = 0.15          # jobber/outlet recovery on cost
FASHION_SEASON_WEEKS = 14
FASHION_DAILY_TX = 34                # weekend-heavy
FASHION_RENT_PER_DAY = 620

# ── the block's people ───────────────────────────────────────────────────
# personas: (name, share, wtp_mult, walk_cost $, schedule)
PERSONAS = [
    ("office-worker", 0.38, 1.00, 1.75, "weekday 8-18 peaks"),
    ("student",       0.24, 0.72, 0.75, "after-school 15-19"),
    ("local",         0.22, 0.90, 1.25, "all-day, evening lean"),
    ("tourist",       0.16, 1.25, 2.50, "midday-heavy, weekend-heavy"),
]
BLOCK_DAILY_FOOT_TRAFFIC = 4200      # walkers past the storefronts

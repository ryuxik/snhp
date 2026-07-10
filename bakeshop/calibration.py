"""NYC 2026 calibration — the ONE source of truth for the two batch-
perishable venues. Values are Manhattan estimates chosen to be defensible
in a pilot conversation; each constant is a calibration TARGET to be
replaced by real POS data when a pilot lands.

The two venues share ONE world core (bakeshop/world.py); everything
venue-specific lives here as data.
"""

# ── bakery (Village neighborhood bakery, 7:00–19:00) ─────────────────────
# (sku, list_price $, unit_cost $, attention = P(an arrival shops it),
#  life_days = sellable days: fresh today + day-old shelf tomorrow)
BAKERY_CATALOG = [
    ("croissant",  4.75, 1.40, 0.70, 2),
    ("sourdough",  9.00, 2.60, 0.35, 2),
    ("cake-slice", 7.50, 2.10, 0.30, 2),
]
BAKERY_OPEN, BAKERY_CLOSE = 7, 19
# Arrivals per hour: the morning pastry rush and the lunch walk-by are the
# two peaks; scaled so the control arm lands near ~300 items/day.
BAKERY_HOURLY_RATE = {
    7: 25.0, 8: 31.0, 9: 25.0, 10: 15.0, 11: 17.0, 12: 27.0,
    13: 25.0, 14: 13.0, 15: 10.0, 16: 10.0, 17: 13.0, 18: 10.0,
}
# Hourly WTP multiplier: the 8am commuter wants it more than the 3pm stroller.
BAKERY_HOURLY_WTP = {
    7: 1.05, 8: 1.05, 9: 1.00, 10: 0.95, 11: 1.00, 12: 1.10,
    13: 1.10, 14: 0.90, 15: 0.85, 16: 0.85, 17: 0.95, 18: 0.90,
}
BAKERY_WTP_SIGMA = 0.30      # lognormal spread of per-consumer, per-SKU WTP
BAKERY_QTY_DECAY = 0.55      # 2nd croissant worth 55% of the 1st (vend's)
BAKERY_FRESH_MULTS = (1.0, 0.55)   # WTP multiplier by age: fresh, day-old
BAKERY_DAY_OLD_FRAC = 0.50   # the CULTURAL day-old shelf: −50% off list
BAKERY_DAY_OLD_PULL_HOUR = 12  # ...and it's a MORNING shelf: pulled at noon
BAKERY_OVERBAKE = 1.15       # "full shelves sell bread": bake to the P75
                             # day — the day-old shelf is IN the plan
BAKERY_MINIBAKE_HOUR = 14    # optional 2pm mini-bake...
BAKERY_MINIBAKE_TRIGGER = 0.25   # ...when fresh stock < 25% of the morning
BAKERY_MINIBAKE_FRAC = 0.35      # ...bake 35% of the morning quantity
BAKERY_SPIKE_MULT = 2.5      # street-fair / holiday-weekend day: ×2.5 arrivals
BAKERY_SUPPLY_CAP = 2.0      # the oven: at most ×2 the normal bake, ever
BAKERY_OUTSIDE_MARKUP = 1.15 # the café across the street: same goods, pricier
BAKERY_WALK = (0.5, 2.0)     # $-equivalent hassle of going there instead
BAKERY_DAILY_ITEMS = 300     # calibration target (units/day under control)

# ── flower shop (Chelsea corner florist, 9:00–19:00) ─────────────────────
# CALIBRATION-TARGETS §3 / CRITICAL-ANALYSIS §9 fix (2026-07-10): the old
# single "3–5 day" field conflated two different real-world numbers —
# RETAIL DISPLAY LIFE (how long the stock looks full-price-fresh on the
# shop floor before it visibly needs a markdown) and VASE LIFE WITH CARE
# (the total usable life, IFPA/floral-trade band 5–14 days). Relabeled:
# `display_days` keeps the OLD "3/4/5" numbers verbatim (now correctly
# named); `life` is the new, longer vase-life-with-care cutoff — the item
# is sellable (at a graduated markdown, not a single day-4 cliff) all the
# way through it, and only wasted at the true end of vase life.
# (sku, list_price $, unit_cost $ wholesale, attention,
#  display_days = retail display life, life = vase life with care)
FLOWER_CATALOG = [
    ("bouquet",     28.00, 10.50, 0.50, 4, 7),
    ("dozen-roses", 95.00, 38.00, 0.12, 5, 9),
    ("stems",        4.00,  1.30, 0.45, 3, 6),   # single stems, mixed bucket
]
FLOWER_OPEN, FLOWER_CLOSE = 9, 19
# Lunch browsers and the after-work "grab flowers on the way home" bump.
FLOWER_HOURLY_RATE = {
    9: 3.0, 10: 4.0, 11: 5.0, 12: 7.0, 13: 6.0, 14: 4.0,
    15: 4.0, 16: 5.0, 17: 8.0, 18: 6.0,
}
FLOWER_HOURLY_WTP = {
    9: 0.95, 10: 0.95, 11: 1.00, 12: 1.05, 13: 1.05, 14: 0.95,
    15: 0.95, 16: 1.00, 17: 1.10, 18: 1.10,
}
FLOWER_WTP_SIGMA = 0.40      # gift purchases: wider spread than croissants
FLOWER_QTY_DECAY = 0.65      # a 2nd bunch is for the second vase
# Quality-tiered markdown ladder (replaces the old single "day 4, flat
# −70%" cliff): full price through display_days, then THREE graduated
# discount steps spread evenly across the rest of vase life, bottoming
# out at the old dump depth on the item's last sellable days — a florist
# marks down in stages as stock visibly ages, not in one jump.
FLOWER_MARKDOWN_STEPS = (0.75, 0.50, 0.30)   # −25%, −50%, −70% of list
FLOWER_DELIVERY_EVERY = 7    # weekly wholesale delivery (day 0, 7, 14, ...)
FLOWER_SPIKE_MULT = 6.0      # Valentine's-like event day: ×6 arrivals
FLOWER_SUPPLY_CAP = 2.0      # wholesaler allocation + cooler space: the
                             # event-day special drop is at most ×2 a normal
                             # day's plan — ×6 demand meets ×2 supply
FLOWER_OUTSIDE_MARKUP = 1.20 # delivery apps / the deli's roses: pricier
FLOWER_WALK = (1.0, 3.0)
# Receiving loss: floral shrink is not purely a pricing failure — a share
# of every wholesale delivery arrives damaged/substandard and is culled
# before it ever reaches the bucket (bent stems, bruised petals, transit
# breakage — a well-documented floral-industry loss category, distinct
# from markdown-driven waste). Applied identically to every arm (it fires
# in `begin_day`, before any policy sees the stock), so it is a genuine
# floor no pricing skill can sell around. Tuned (CALIBRATION-TARGETS §3,
# CRITICAL-ANALYSIS §9) so the age-aware POSTED arm's realized dollar
# shrink lands in the IFPA ballpark (~9–12% of dollars) instead of the
# ~0–2% an omniscient-demand pricer reaches with zero receiving loss.
FLOWER_RECEIVING_LOSS = 0.15

# ── legacy flower calibration (pre-2026-07-10), kept for a labeled
# "low-volume independent florist" comparison cell only — NOT the
# headline. Old 3/4/5-day hard cutoff, flat single-cliff dump at day 4,
# no receiving loss (CALIBRATION-TARGETS §3 flagged this combination as
# defensible only for a low-volume shop, not the calibration target).
FLOWER_CATALOG_LEGACY = [
    ("bouquet",     28.00, 10.50, 0.50, 4),
    ("dozen-roses", 95.00, 38.00, 0.12, 5),
    ("stems",        4.00,  1.30, 0.45, 3),
]
FLOWER_DUMP_AGE_LEGACY = 3
FLOWER_DUMP_FRAC_LEGACY = 0.30

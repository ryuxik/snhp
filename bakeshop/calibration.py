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

# ── the SERVICES tier (CRITICAL-ANALYSIS §9 follow-up: the REAL florist) ──
# The florist "posted beats negotiation" boundary (CRITICAL-ANALYSIS §9) was
# found on an IMPOVERISHED florist modeled as pure perishable walk-in
# clearance — the florist's ANTI-lever for our mechanism. But real florist
# revenue is dominated by higher-margin, heterogeneous, multi-issue lines
# that are exactly the regimes bilateral negotiation wins everywhere else in
# our results. This block calibrates four such lines (NYC 2026, sourced in
# bakeshop/RESULTS.md "services tier" section). Every number here is a
# calibration TARGET; volumes/dispersions are labeled assumptions and swept.
SERVICES_SEED_SALT = "services"

# Daily order volumes (Poisson means) for a full-service Manhattan florist —
# NOT the grab-and-go walk-in shop the §9 grid modeled. Labeled assumptions
# (retail-florist order mix); the revenue-weighted blend in RESULTS.md reports
# realized per-line revenue so the weighting is explicit, not hidden.
ARRANGEMENT_RATE = 18.0      # arranged-bouquet orders/day
DELIVERY_RATE    = 22.0      # delivered gift orders/day (most web/phone volume)
EVENT_RATE       = 0.8       # weddings + funerals booked/day (lumpy, high $)
ATTACH_RATE      = 34.0      # POS flower buyers who see an attach suggestion/day

# ── line 1: ARRANGEMENT — flowers × style × size, the labor-margin,
#    heterogeneous-taste multi-issue line (logrolling home turf). ──
# Wholesale stem cost by size (standard grade); premium grade multiplies it.
ARR_SIZE_WHOLESALE = {"small": 9.0, "medium": 18.0, "large": 30.0}
ARR_GRADE_MULT = {"standard": 1.0, "premium": 1.9}   # premium bloom wholesale
ARR_STYLE_LABOR = {"wrap": 8.0, "hand_tie": 16.0, "vase": 26.0}  # design $
ARR_STYLE_VESSEL = {"wrap": 1.0, "hand_tie": 2.0, "vase": 9.0}   # hard good $
# Florist markup convention (Florists' Review / EveryStem / Fiore Designs):
# fresh goods retail ≈ 3.5× wholesale, hard goods ≈ 2.5×, design labor billed
# ~1.5× (the "labor is 25-40% of the marked-up subtotal" rule, folded into a
# per-style dollar fee). These reproduce the TJ Flowers NYC anchors: standard
# medium wrap ≈ $85, standard medium vase ≈ $125, premium medium vase ≈ $175.
ARR_FRESH_MARKUP = 3.5
ARR_HARD_MARKUP = 2.5
ARR_LABOR_MARKUP = 1.5
# Population-average desirability scores per attribute level (a buyer's own
# private importance weights, drawn per buyer, tilt these into heterogeneous
# per-config value — the scarce information bilateral discovery exploits).
ARR_GRADE_SCORE = {"standard": 1.00, "premium": 1.55}
ARR_STYLE_SCORE = {"wrap": 1.00, "hand_tie": 1.12, "vase": 1.30}
ARR_SIZE_SCORE = {"small": 0.80, "medium": 1.00, "large": 1.28}
ARR_WEIGHT_SIGMA = 0.55      # lognormal spread of a buyer's per-issue weights
ARR_BUDGET_MU = 96.0         # median buyer flower budget $ (near the popular
                             # config's reference list — the strong-sticker
                             # calibration: list ≈ the profit-max posted price,
                             # so the tuned menu markup lands interior ≈ 1.0)
ARR_BUDGET_SIGMA = 0.42      # lognormal spread of buyer budgets
ARR_OUTSIDE_MARKUP = 1.15    # the florist across the street / a delivery app:
                             # the SAME config, ~15% pricier — a COMPETITIVE
                             # outside that scales with the buyer's own value
                             # (mirrors world.outside_surplus), so demand is
                             # elastic and the profit-max menu markup lands
                             # interior instead of running away up a fat tail
ARR_WALK = (1.0, 4.0)        # $-hassle of going to that competitor
# The posted arm's menu is necessarily COARSE (a shelf/web menu can't carry a
# bespoke price for all 2×3×3 = 18 configs). This is the realistic six-SKU
# menu; a "full 18-config menu" ablation is also run so the win is not a
# menu-coarseness artifact.
ARR_MENU = (("standard", "wrap", "small"), ("standard", "wrap", "medium"),
            ("standard", "vase", "medium"), ("premium", "vase", "medium"),
            ("premium", "vase", "large"), ("standard", "hand_tie", "large"))

# ── line 2: DELIVERY — the time-window logistics lever (route density is the
#    capacity; buyers value windows differently — the boba pickup-slot lever). ──
DELIVERY_WINDOWS = ("early", "midday", "afternoon", "evening", "flexible")
DELIVERY_BASE_COST = 11.0    # marginal cost of one un-batched delivery $
DELIVERY_DENSITY_SAVING = 1.6  # $ shaved per prior delivery already routed to
                               # the same window (route batching), capped
DELIVERY_DENSITY_CAP = 6.0     # max $ density saving per delivery
DELIVERY_REF_FEE = 14.0      # the posted flat fee $ (NYC local-florist band
                             # starts ~$9; $14 = a mid Manhattan zone fee)
DELIVERY_CONVENIENCE_MU = 17.0  # median buyer $-value of having it delivered
DELIVERY_CONVENIENCE_SIGMA = 0.5
DELIVERY_TIGHT_PROB = 0.45   # P(buyer has a tight preferred window vs flexible)
DELIVERY_OFFWINDOW_PENALTY = 0.55  # a tight buyer's convenience is ×this in a
                                   # non-preferred window; flexible buyers ~1.0
DELIVERY_FLEX_SIGMA = 0.12   # flexible buyers' tiny window preference spread

# ── line 3: EVENT PRE-ORDERS — weddings/funerals: advance-booked, high-value,
#    wide-WTP, multi-issue (scope × palette) — bilateral quoting's textbook. ──
EVENT_WEDDING_PROB = 0.45    # rest are funerals (throughout the week)
# scope = how much of a "full" event; palette = standard vs premium blooms.
EVENT_WED_SCOPES = ("intimate", "standard", "grand")
EVENT_WED_COST = {"intimate": 2400.0, "standard": 5600.0, "grand": 13000.0}
EVENT_WED_COMPLETE = {"intimate": 0.45, "standard": 0.75, "grand": 1.0}
EVENT_WED_BUDGET_MU = 8000.0   # NYC average wedding floral spend (Ode/Cape Lily)
EVENT_WED_BUDGET_SIGMA = 0.62  # $3k floor … $25k full-service (wide)
EVENT_FUN_SCOPES = ("basket", "standing", "casket")
EVENT_FUN_COST = {"basket": 55.0, "standing": 175.0, "casket": 320.0}
EVENT_FUN_COMPLETE = {"basket": 0.5, "standing": 0.8, "casket": 1.0}
EVENT_FUN_BUDGET_MU = 520.0    # families spend $500-700 avg (Everloved/Kremp)
EVENT_FUN_BUDGET_SIGMA = 0.5
EVENT_PALETTE_MULT = {"standard": 1.0, "premium": 1.28}  # premium bloom uplift
EVENT_PALETTE_COST = {"standard": 1.0, "premium": 1.22}
EVENT_PALETTE_TASTE_SIGMA = 0.35  # spread of buyers' taste for premium blooms
EVENT_MARKUP = 1.85          # reference package retail = cost × this (the
                             # posted package sticker; discount-only ceiling)
EVENT_OUTSIDE_MARKUP = 1.15  # a competing event florist / DIY: the same scope,
                             # ~15% pricier — the competitive outside that keeps
                             # the posted package markup interior (couples DO
                             # shop multiple florists)
# The posted arm lists a coarse tiered package menu per event type (real
# florists that DON'T quote bespoke sell 3 fixed tiers); nego quotes the full
# scope×palette space per booking.
EVENT_WED_MENU = (("intimate", "standard"), ("standard", "standard"),
                  ("grand", "premium"))
EVENT_FUN_MENU = (("basket", "standard"), ("standing", "standard"),
                  ("casket", "premium"))

# ── line 4: ATTACH — chocolates / card / vase at the point of sale
#    (suggest/1: a COMPLEMENT to the flower purchase, not a substitute). ──
ATTACH_ITEMS = ("card", "chocolates", "vase")
ATTACH_COST = {"card": 1.2, "chocolates": 9.0, "vase": 6.0}
ATTACH_REF_PRICE = {"card": 5.0, "chocolates": 20.0, "vase": 18.0}  # shelf $
ATTACH_BASE_WTP_MU = {"card": 4.0, "chocolates": 14.0, "vase": 12.0}
ATTACH_WTP_SIGMA = 0.6
ATTACH_COMPLEMENT_BOOST = 0.45  # buying flowers raises attach WTP ×(1+this):
                                # a gift wants a card, chocolates ride along
ATTACH_INTEREST_PROB = {"card": 0.7, "chocolates": 0.4, "vase": 0.3}  # P(shops)

# Common bilateral buffer (mirrors nego/1: don't-negotiate-for-pennies).
SERVICES_MIN_GAIN_ABS = 0.50
SERVICES_MIN_GAIN_FRAC = 0.06

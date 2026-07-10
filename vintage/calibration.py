"""VINTAGE calibration — NYC 2026, Lower East Side one-of-one vintage store.

Every constant the sim uses lives HERE, with its story. The miscalibration
IS the business: the owner tags by gut at ~3.2x cost with high variance —
some pieces tagged half their true value, some double — and the experiment
asks what a negotiation engine (or a computed markdown) recovers from that.
"""

# ── sourcing (one-of-one; sold is gone, unsold ages, sourcing keeps coming) ─
SOURCING_RATE = 6.0        # items/day from estate sales, rag houses, pickers
COST_LO, COST_HI = 8.0, 40.0   # per-piece sourcing cost, log-uniform (skews cheap)
MARKUP_MU = 3.2            # the gut markup: tag ≈ 3.2x cost on average
SIGMA_SOURCE = 0.40        # the sourcing lottery: TRUE market value (appeal) =
                           # cost x 3.2 x lognormal(0, σ) — the dealer's eye is
                           # right on average; per piece it's a gamble
# tag = appeal x lognormal(0, sigma_tag): the owner's noisy guess of appeal.
# sigma_tag is THE grid knob {0.3, 0.6}; at 0.6, half-value and double-value
# tags are within one sigma — "some pieces tagged half their value, some double".

# ── demand ──────────────────────────────────────────────────────────────────
TRAFFIC_MEAN = 40.0        # browsers/day through the door
CONNECT_PROB = 0.08        # sparse item-buyer match: a browser "connects"
                           # with ~8% of the rack — the piece speaks to them
SIGMA_WTP = 0.25           # connecting browser's WTP ~ lognormal around the
                           # item's hidden appeal (connection strength)
SHADING_SPREAD = 0.08      # per-browser haggling style: shading factor =
                           # grid center ± U(−0.08, +0.08) (kills the
                           # degenerate "engine reads WTP exactly off the
                           # offer" inference; hagglers differ)
TOLERANCE = 1.0            # browser accepts a counter iff counter ≤ WTP x this
                           # (1.0 = the rational boundary; kept explicit)
P_HUFF = 0.25              # haggle friction: P(a countered browser walks out
                           # regardless of price — "they came with a number")

# ── economics of holding (why dead stock isn't free) ───────────────────────
DAILY_DISCOUNT = 0.998     # per-day discount on future receipts (capital +
                           # season staleness, ≈ 6%/month blended)
HOLDING_COST = 0.06        # $/item-day: rack space, steaming, dust — LES
                           # square feet are the scarcest input

# ── sticker/1, the cultural control ─────────────────────────────────────────
MARKDOWN_AGE = 30          # the LES ritual: 30 days on the rack unsold →
MARKDOWN_FACTOR = 0.80     # ...20% off (compounds at 60 days, etc.)

# ── the engine (offer/1 and hazard/1) ───────────────────────────────────────
BUFFER_ABS = 2.0           # don't-negotiate-for-pennies floor: the engine's
BUFFER_FRAC = 0.08         # believed gain must clear max($2, 8% of tag)
BELIEF_SIGMA = 0.45        # engine's prior on appeal: lognormal around the
                           # tag with THIS sigma — fixed across grid cells;
                           # the engine does NOT know the true tag-noise level
BELIEF_GRID_N = 21         # per-item posterior support (log-spaced grid)
BELIEF_GRID_Z = 2.5        # grid half-width in units of BELIEF_SIGMA
SHADING_BELIEF_LO = 0.75   # engine's belief about offer shading: uniform on
SHADING_BELIEF_HI = 0.95   # [0.75, 0.95] — it does NOT know the true center
HUFF_BELIEF = 0.25         # engine's belief about haggle friction (= truth;
                           # flagged: the one behavioral constant it knows)
RHO_PRIOR_MEAN = 0.05      # prior connection rate per browser per item
RHO_PRIOR_STRENGTH = 2.0   # ...worth 2 pseudo-sales of evidence (weak);
                           # the engine LEARNS rho from its own sales history,
                           # censoring-aware — it never gets the true 0.08
F_INIT = 1.0               # offer/1's realized-price fraction estimate f̂:
F_EWMA = 0.05              # EWMA of (sale price / ask) over OWN settlements —
                           # what a future "sale" is actually worth here
REPRICE_EVERY = 7          # hazard/1 re-solves each item's price weekly
PRICE_FLOOR_FRAC = 0.35    # hazard/1 never computes below 35% of tag
PRICE_GRID_N = 15          # hazard/1 price grid resolution
COUNTER_GRID_N = 24        # engine counter-price grid resolution

# ── experiment ──────────────────────────────────────────────────────────────
GRID_SIGMA_TAG = (0.3, 0.6)    # tag-noise: how wrong the gut is per piece
GRID_SHADING = (0.75, 0.9)     # strategic shading factor (offer = WTP x this)
CLASS_EDGE = 1.2           # item classes for H-V1: under-tagged if
                           # tag ≤ appeal/1.2, over-tagged if tag ≥ 1.2x appeal
DTS_COHORT_MARGIN = 30     # days-to-sale cohort: items sourced at least this
                           # many days before the horizon (fair exposure)

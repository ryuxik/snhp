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
# v3 RECALIBRATION (2026-07-10, CALIBRATION-TARGETS.md §2 / #5): the v1/v2
# world sold a fairly-tagged item to ~half its connectors THE SAME DAY (3.2
# connecting browsers/item-day at CONNECT_PROB=0.08 x TRAFFIC_MEAN=40) —
# median days-to-sale ~0, flatly contradicted by ThredUp FY2025 (~50% sell
# within 30 days, tail to 90+ days). CONNECT_PROB is the lever: dropped
# ~53x so a fairly-tagged item's daily sale hazard lands near ln(2)/30 ≈
# 2.3%/day (fit empirically against the sticker/1 30-day cohort share, see
# RESULTS.md v3 section) instead of ~90%/day. TRAFFIC_MEAN (real LES foot
# traffic) and SIGMA_WTP (the "market is right on average" WTP spread) are
# UNCHANGED — the fix is "browsers connect with far fewer pieces per visit"
# (an LES vintage rack is browsed, not exhaustively evaluated item-by-item),
# not "fewer people walk in" or "buyers lowball intrinsically."
TRAFFIC_MEAN = 40.0        # browsers/day through the door
CONNECT_PROB = 0.0015      # sparse item-buyer match: a browser "connects"
                           # with ~0.15% of the rack per item (v3; was 8%) —
                           # fit so sticker/1's 30-day cohort sell-through
                           # lands at ~45-50% (ThredUp target), see RESULTS.md
SIGMA_WTP = 0.25           # connecting browser's WTP ~ lognormal around the
                           # item's hidden appeal (connection strength)
SHADING_SPREAD = 0.08      # per-browser haggling style: shading factor =
                           # grid center ± U(−0.08, +0.08) (kills the
                           # degenerate "engine reads WTP exactly off the
                           # offer" inference; hagglers differ)
TOLERANCE = 1.0            # browser accepts a counter iff counter ≤ WTP x this
                           # (1.0 = the rational boundary; kept explicit)
# v3: Backus et al. (QJE 2020, eBay Best Offer, 88M listings) measure buyer
# decline-after-counter at 58% — our old P_HUFF=0.25 was "too low" per
# CALIBRATION-TARGETS.md §2. Moved to the published figure; HUFF_BELIEF
# (engine's prior, below) moves with it so the prior keeps "happening to
# equal the truth" before the data dominate it (the v2 design pattern).
P_HUFF = 0.58              # haggle friction: P(a countered browser walks out
                           # regardless of price — "they came with a number")
                           # (v3: Backus et al. QJE 2020, was 0.25)

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
HUFF_BELIEF = 0.58         # PRIOR mean on the huff rate (happens to equal the
                           # truth; post-reg FIX B demotes it from a known
                           # constant to a weak Beta prior the data dominate)
                           # (v3: moves with P_HUFF, Backus et al. QJE 2020)

# ── FIX B (post-registration, CRITICAL-ANALYSIS §4a): the learned counter
#    round. The old engine BELIEVED shading ~ U[0.75, 0.95] by fiat and knew
#    the huff rate; the fixed engine LEARNS the population from its own
#    accept/huff/reject/fallback history, censoring-aware. ─────────────────
SHADE_CENTER_LO = 0.60     # posterior support for the population shading
SHADE_CENTER_HI = 1.00     # CENTER m (offer = shading x WTP, s|m ~ U[m ± W])
SHADE_CENTER_N = 41        # grid resolution over m
SHADE_HALFWIDTH = 0.10     # believed within-population spread W (the old
                           # fixed belief's half-width; the true spread 0.08
                           # stays hidden — no truth smuggled in)
SHADE_LIK_EPS = 0.02       # likelihood clamp on counter-round evidence:
                           # robustness to the spread misspecification
HUFF_PRIOR_STRENGTH = 2.0  # the Beta prior on the huff rate is worth 2
                           # observed counters at mean HUFF_BELIEF (weak)
FALLBACK_PRIOR_N = 5.0     # F-hat (the huffed browser's foregone continuation
                           # value) starts as 5 pseudo-observations of $0

# ── FIX A (post-registration, CRITICAL-ANALYSIS §4b): bidirectional retag ──
RETAG_EVERY = 7            # retag cadence: at admission, then at most weekly
                           # (a retag that waits a week protects nothing —
                           # the under-tagged upside dies same-day)
RETAG_GRID_N = 40          # price grid for the bidirectional re-solve; the
                           # grid spans [PRICE_FLOOR_FRAC x tag, top of the
                           # item's own appeal posterior support]
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

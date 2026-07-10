"""SLOT-ECONOMICS calibration — 2026 NYC numbers, three venues, one ladder.

Every constant a reviewer might dispute lives HERE, not in world.py. These
are THIS package's own assumptions (July 2026 scan of posted NYC prices,
rounded) — deliberately independent of block/calibration.py.

The venue stories:
  barber  — a Bed-Stuy two-chair shop: $38 cut (45 min on the clock, the
            chair turns in 50), same-day bookings, ~12% no-shows, mild
            lunch and after-work bumps.
  parking — a Midtown-adjacent 40-space garage: $18 first hour / $8 each
            additional / $45 day max, a commuter slug at 07:00–09:00 that
            all wants the SAME nine-to-ten hours, a theater bump at
            18:00–20:00, app reservations with ~8% no-shows.
  bar     — an East Village room, 60 seats, $9 beer / $16 cocktail list,
            dead 15:00–18:00, packed 19:00–23:00, pure walk-in (a body at
            the door cannot no-show).

The three venues are chosen to span a demand-asymmetry ladder (H-S1's
pre-registered ordering): peak-vs-capacity pressure is engineered
parking > bar > barber. world.py prints each venue's realized congestion
ratio so the claim is checkable, not asserted.

Arrival rates are booking REQUESTS per hour (not sales); the world's
conversion at list is what turns them into occupancy. Segment `gamma`
curves value over trimmed durations: V(n) = WTP * (n / n_req) ** gamma —
gamma < 1 for divisible services (drinks, errand parking: the first unit
is worth the most), gamma > 1 for indivisible needs (a commuter's work
day: half a day is nearly worthless).
"""

# ── shared knobs ─────────────────────────────────────────────────────────
OUTSIDE_MARKUP = 1.10       # the competitor around the corner: list x 1.1
PRICE_RUNGS = 8             # Nash price grid between cost and list
EPS_QUANTILES = 21          # lognormal mid-quantile grid for demand forecasts

# ── barbershop ───────────────────────────────────────────────────────────
# Calibration note (2026-07-10, CALIBRATION-TARGETS §4, priority #8):
# platform-measured schedule utilization averages 62% (Squire 13.9M appts;
# Zenoti 30k businesses, independently), top quartile 73–84%. The old rate
# profile realized 45–49% — a below-average shop. The shoulders below are
# raised (not the peaks, to keep the H-S1 asymmetry ladder intact) so the
# static arm realizes ~62% under the deposit regime — an *average* shop.
# No-shows are now an EXPLICIT REGIME (BARBER_NOSHOW_REGIMES): platform
# shops with reminders/deposits run 3–5% (we take 4%); no-deposit low-tech
# shops run 15–25% (we keep the old 12% as a conservative-low no-deposit).
# The deposit IS the venue's incumbent negotiation mechanism — see
# paper/CRITICAL-ANALYSIS §6 and the calibrated-world RESULTS section.
BARBER_OPEN, BARBER_CLOSE = 9, 19        # 09:00–19:00 → 60 ten-minute ticks
BARBER_CHAIRS = 2
BARBER_CUT_PRICE = 38.0                  # the posted cut, 2026 Bed-Stuy
BARBER_CUT_COST = 5.0                    # supplies + laundry; wages are sunk
BARBER_CUT_TICKS = 5                     # 45-min cut + turnover
BARBER_NOSHOW = 0.04                     # DEPOSIT regime (platform default);
                                         # the venue default is now the
                                         # average deposit-taking shop
BARBER_NOSHOW_REGIMES = {"deposit": 0.04, "nodeposit": 0.12}
BARBER_SIGMA = 0.35                      # lognormal WTP-ratio spread
BARBER_RATE = {9: 2.8, 10: 3.2, 11: 3.4, 12: 4.4, 13: 4.0, 14: 3.0,
               15: 2.8, 16: 3.4, 17: 4.6, 18: 4.2}     # requests/hour
BARBER_WTP_MULT = {9: 0.95, 10: 0.95, 11: 1.00, 12: 1.05, 13: 1.05,
                   14: 0.90, 15: 0.90, 16: 1.00, 17: 1.10, 18: 1.10}
BARBER_SHIFT_CHOICES = (-6, -4, -2, 0, 2, 4, 6)   # nego offers, in ticks
BARBER_WINDOW = 6                        # a customer will consider ±1 h
BARBER_FLEX_COST = 0.50                  # $/tick of shift, flexible type
BARBER_RIGID_COST = 4.00                 # $/tick, "I have a 2pm meeting"
BARBER_HASSLE = (2.0, 6.0)               # $ to walk to the other shop
BARBER_SEGMENTS = {
    "cut": dict(n_choices=(1,), n_weights=(1.0,), lead_max=6, gamma=1.0,
                sigma=BARBER_SIGMA),
}
BARBER_SEG_WEIGHTS = {h: {"cut": 1.0} for h in BARBER_RATE}
BARBER_KINDS = {"cut": (BARBER_CUT_PRICE, BARBER_CUT_COST, 1.0)}

# ── parking ──────────────────────────────────────────────────────────────
# Calibration note (2026-07-10, CALIBRATION-TARGETS §4, priority #8):
# observed Seattle garage occupancy runs 58% core / 48% outside; our
# realized 68–69% is a HOTTEST-SUBAREA / high-demand facility, LABELED as
# such (not a city average). Elasticity: Lehner–Peer 2019 meta —0.63
# occupancy / —0.30 volume, and COMMUTERS ARE THE LEAST PRICE-ELASTIC
# SEGMENT. The old model gave every segment the same WTP dispersion
# (PARKING_SIGMA), so the commuter's low elasticity was only an artifact of
# its high wtp_mult and it TIED with the event crowd. Elasticity is now
# STRUCTURAL, per segment: a tight commuter WTP (low sigma → little mass
# near the margin → hardest to move on price) vs a dispersed errand/event
# WTP. Ordering after the fix: commuter << event < errand. The reservation
# no-show 8% is unpublished anywhere — an explicit ASSUMPTION.
PARKING_OPEN, PARKING_CLOSE = 6, 24      # 06:00–24:00 → 108 ticks
PARKING_SPACES = 40
PARKING_FIRST_HOUR = 18.0                # Midtown-adjacent posted rate
PARKING_ADDL_HOUR = 8.0
PARKING_DAY_MAX = 45.0
PARKING_COST_PER_HOUR = 0.40             # marginal ops (ticketing, wear)
PARKING_STEP_TICKS = 6                   # one step = one hour
PARKING_NOSHOW = 0.08                    # app reservations (ASSUMPTION)
PARKING_SIGMA = 0.40                     # venue default; segments override
PARKING_RATE = {6: 10, 7: 48, 8: 52, 9: 14, 10: 4, 11: 4, 12: 5, 13: 4,
                14: 4, 15: 3, 16: 3, 17: 5, 18: 12, 19: 16, 20: 7,
                21: 2, 22: 1, 23: 0.5}
PARKING_WTP_MULT = {6: 0.95, 7: 1.10, 8: 1.10, 9: 1.00, 10: 0.90, 11: 0.90,
                    12: 0.95, 13: 0.95, 14: 0.90, 15: 0.90, 16: 0.95,
                    17: 1.00, 18: 1.10, 19: 1.10, 20: 1.05, 21: 0.90,
                    22: 0.85, 23: 0.85}
PARKING_SHIFT_CHOICES = (-6, -3, 0, 3, 6)     # ±30/60 min entry shifts
PARKING_WINDOW = 6
PARKING_FLEX_COST = 0.35
PARKING_RIGID_COST = 3.00
PARKING_HASSLE = (3.0, 8.0)              # circling blocks to the next garage
PARKING_SEGMENTS = {
    # the office slug: needs the WHOLE work day (gamma 3: trims worthless)
    # and is the LEAST price-elastic (Lehner–Peer): a tight WTP (sigma
    # 0.30) puts little mass near the margin, so a discount converts few
    # who would not have paid list.
    "commuter": dict(n_choices=(9, 10), n_weights=(0.5, 0.5),
                     lead_max=1, gamma=3.0, sigma=0.30),
    # errands: first hour worth the most (gamma 0.7) and the MOST
    # price-elastic (dispersed WTP, sigma 0.48) — happy to walk a block.
    "errand": dict(n_choices=(1, 2, 3), n_weights=(0.45, 0.35, 0.20),
                   lead_max=1, gamma=0.7, sigma=0.48),
    # theater/dinner: the show is the show (gamma 2.5), booked a bit ahead,
    # fairly inelastic but less so than the commuter (sigma 0.42).
    "event": dict(n_choices=(4, 5), n_weights=(0.6, 0.4),
                  lead_max=4, gamma=2.5, sigma=0.42),
}
PARKING_SEG_WEIGHTS = {}
for _h in PARKING_RATE:
    if _h <= 9:
        PARKING_SEG_WEIGHTS[_h] = {"commuter": 0.85, "errand": 0.15, "event": 0.0}
    elif _h <= 16:
        PARKING_SEG_WEIGHTS[_h] = {"commuter": 0.10, "errand": 0.85, "event": 0.05}
    elif _h <= 20:
        PARKING_SEG_WEIGHTS[_h] = {"commuter": 0.05, "errand": 0.35, "event": 0.60}
    else:
        PARKING_SEG_WEIGHTS[_h] = {"commuter": 0.0, "errand": 0.70, "event": 0.30}
PARKING_KINDS = {"car": (None, None, 1.0)}     # priced by formula, not per-step

# ── happy-hour bar ───────────────────────────────────────────────────────
# Calibration note (2026-07-10, CALIBRATION-TARGETS §4, priorities #7+#8):
# two coupled fixes, both load-bearing on the relief-term conclusion.
#
# (1) WEEKEND CURVE (priority #7). Nielsen CGA: Saturday alone is >25% of
# WEEKLY sales, Fri+Sat run 40-50% of the week, Sat 5-6pm checks run ~40%
# ABOVE Sat 10pm, and happy-hour checks average ~$8 HIGHER than other
# dayparts — the old flat "dead 5-7pm" profile was wrong on weekends. Day
# structure is now real: BAR_DOW_RATE_MULT scales the whole day's arrival
# volume (Mon..Sun index 0..6; Sat 1.70 of 6.35 total ≈ 27% of the week,
# Fri+Sat ≈ 46%); BAR_DOW_WTP_MULT layers an extra per-(day, hour)
# multiplier on top of the hourly BAR_WTP_MULT base, raised at weekday
# happy hour (general Nielsen finding) and raised MUCH further at Sat
# 17-18h specifically (the Sat-vs-10pm 40% finding) — Sat 15:00 becomes a
# ramp INTO happy hour, not a continuation of "dead."
#
# (2) PEAK ANCHOR (the coupled fix). Before this fix, BAR_BEER/BAR_COCKTAIL
# were a FLAT list ($9/$16) while BAR_WTP_MULT rose to 1.10 at peak: since
# every arm is discount-only (price ≤ list, always), the venue could never
# charge the peak crowd what it would actually bear — capped at list
# exactly when leverage was highest. Once the weekend curve above is real,
# that gap is much larger (Saturday happy-hour genuinely outbids the old
# "peak"). Ported the concept behind vend/world.py's `anchor_peak` +
# `_profit_optimal_list_price(peak_only=True)`: BAR_WTP_MULT (this base
# dict) is the RAW hourly shape divided by the raw week-max combined mult
# (so the whole grid is ≤ 1.0, hitting exactly 1.0 at the true peak, Sat
# 17:00 — "never exceeds 1.0 at the anchor"); the dollar list was RAISED to
# the peak crowd's own profit-optimal price (solved via world._pstar_mixture
# against a single mult=1.0 cell, sigma=BAR_SIGMA, using the pre-fix ratio
# appeal and the new weekend demand shape) — $16 becomes a standing
# happy-hour discount off a $21.67 anchor ($9 -> $12.19 for beer).
# HONEST RESIDUAL (unlike vend, which sets list DIRECTLY off a fixed
# dollar WTP_MU): this venue's ratio_appeal R is re-inverted against the
# FULL WEEK'S blended mixture every build (the same mechanism barber and
# parking use, kept unchanged rather than special-cased), not against the
# peak subset alone — so R adapts to any dollar anchor rather than pinning
# it, and no FINITE anchor makes the peak's own unclamped optimal exactly
# 1.0 (verified: iterating the anchor upward does not converge — cost
# becomes negligible relative to list and the unclamped multiplier
# approaches ~1.42 asymptotically). The anchor below is a single-shot
# profit-optimization at the pre-fix ratio appeal, same spirit as vend's
# `_profit_optimal_list_price`, not a re-inverted fixed point: it raises
# the ceiling from $16 (0% of the way to the crowd's true optimum) to
# $21.67 (closing the bulk of the gap), but a ~37% relative unclamped
# headroom remains after the fix — reported, not hidden, in
# slots/RESULTS.md's calibrated-world section (see also the discount-only
# floor: no arm may exceed the anchor regardless).
BAR_OPEN, BAR_CLOSE = 15, 24             # 15:00–24:00 → 54 ticks
BAR_SEATS = 60
BAR_BEER = (12.19, 2.2, 0.55)             # (list, cost, share) — the new
                                          # peak anchor; was (9.0, 2.2, .55)
BAR_COCKTAIL = (21.67, 4.2, 0.45)        # the new peak anchor; was (16.0,...)
BAR_DRINK_TICKS = 3                      # one drink ≈ 30 min of seat time
BAR_NOSHOW = 0.0                         # walk-ins cannot no-show
BAR_SIGMA = 0.45
BAR_RATE = {15: 10, 16: 12, 17: 16, 18: 35, 19: 130, 20: 140, 21: 140,
            22: 110, 23: 50}
# raw hourly shape / 1.5675 (the week's raw peak, Sat 17:00) — see the
# calibration note above; the peak-anchor rescale so the grid tops out at
# exactly 1.0 at the true (day, hour) peak, not at some arbitrary weekday
# hour as before.
BAR_WTP_MULT = {15: 0.5423, 16: 0.5423, 17: 0.6061, 18: 0.6380, 19: 0.6699,
                20: 0.7018, 21: 0.7018, 22: 0.6699, 23: 0.5742}
# day-of-week EXTRA multiplier on top of BAR_WTP_MULT, keyed Mon=0..Sun=6.
# Mon-Thu absent -> 1.0 (an ordinary weekday, the base shape as-is). Fri
# and Sat raise happy hour (general Nielsen finding, sharpest on Sat: 17h
# combined = 0.6061*1.65 = 1.0 exactly, the week's peak, vs Sat 22h
# combined = 0.7018*1.05 = 0.737 -> ~40% higher, matching the Sat-vs-10pm
# evidence). Sun is a quiet night.
BAR_DOW_WTP_MULT = {
    4: {17: 1.05, 18: 1.08, 19: 1.15, 20: 1.15, 21: 1.15, 22: 1.12, 23: 1.05},
    5: {15: 1.05, 16: 1.20, 17: 1.65, 18: 1.55, 19: 1.20, 20: 1.15, 21: 1.10,
        22: 1.05, 23: 1.00},
    6: {15: 0.85, 16: 0.85, 17: 0.85, 18: 0.85, 19: 0.85, 20: 0.80, 21: 0.80,
        22: 0.75, 23: 0.70},
}
# day-of-week volume multiplier, an EXTRA per-(day, hour) factor on
# BAR_RATE, Mon=0..Sun=6 (missing day/hour -> 1.0, unchanged weekday).
# NOT a flat per-day scalar: 19:00-22:00 is already capacity-saturated on
# an ORDINARY weekday (D-hat there runs 340-610 unit-ticks against a
# 360-tick hourly ceiling — see world.py's PEAK_THRESHOLD/peak_hours), so
# a uniform day-level rate bump mostly turns away the extra crowd rather
# than converting it (static charges the same flat per-tick rate at
# every hour, so a capacity-saturated block's REVENUE is capped at
# capacity x price regardless of how much demand is queued behind it).
# The realized "Saturday >25% of weekly sales" story has to come from
# genuinely converting the otherwise-idle 15:00-18:00 into a second,
# earlier busy window — Saturday's happy hour effectively becomes prime
# time, not a bigger crowd fighting over the same already-full 9pm. Sunday
# is cut hard (0.10-0.13x) so it's actually below the saturation
# threshold — a real quiet night, not another capacity-bound floor.
# Bounded on the OTHER side by H-S1's engineered asymmetry ladder
# (congestion_ratio: parking > bar > barber, world.congestion_ratio):
# pushing the Sat/Fri afternoon rate further raises bar's own congestion
# ratio, and it would overtake parking's (2.33) well before it closes the
# rest of the gap to the idealized >25% Nielsen figure — diminishing
# returns confirmed empirically (see slots/RESULTS.md's calibrated-world
# section). Landed short of the ladder's ceiling: bar congestion ≈ 2.21.
# Verified over WHOLE-WEEK windows (a 30-day run over-represents Mon/Tue
# by one extra occurrence each, understating Sat's true share — the tests
# use 35 days = 5 full weeks): Sat share ≈ 0.228 (>0.22 required, short of
# the idealized >0.25 Nielsen figure — the residual gap is the capacity-
# saturation ceiling under linear per-tick static pricing, a labeled
# limitation, not a bug). Fri+Sat ≈ 0.45 (40-50% band).
BAR_DOW_RATE_MULT = {
    3: {15: 1.2, 16: 1.3, 17: 1.4, 18: 1.3},                    # Thu ramp
    4: {15: 9, 16: 15, 17: 20, 18: 17, 19: 2.0, 20: 2.0, 21: 2.0, 22: 2.0,
        23: 3.0},                                                # Fri
    5: {15: 11, 16: 19, 17: 25, 18: 21, 19: 2.0, 20: 2.0, 21: 2.0, 22: 2.0,
        23: 3.4},                                                # Sat
    6: {15: 0.1, 16: 0.1, 17: 0.1, 18: 0.1, 19: 0.13, 20: 0.13, 21: 0.13,
        22: 0.13, 23: 0.1},                                      # Sun
}
BAR_SHIFT_CHOICES = (-3, -2, -1, 0, 1, 2, 3)   # ±10/20/30-min seatings
BAR_WINDOW = 3
BAR_FLEX_COST = 0.60
BAR_RIGID_COST = 5.00                    # "we're meeting people at 7"
BAR_HASSLE = (1.0, 4.0)                  # the bar across the street
BAR_SEGMENTS = {
    "drinks": dict(n_choices=(1, 2, 3, 4), n_weights=(0.2, 0.4, 0.3, 0.1),
                   lead_max=1, gamma=0.7, sigma=BAR_SIGMA),
}
BAR_SEG_WEIGHTS = {h: {"drinks": 1.0} for h in BAR_RATE}
BAR_KINDS = {"beer": BAR_BEER, "cocktail": BAR_COCKTAIL}

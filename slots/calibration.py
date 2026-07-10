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
BARBER_OPEN, BARBER_CLOSE = 9, 19        # 09:00–19:00 → 60 ten-minute ticks
BARBER_CHAIRS = 2
BARBER_CUT_PRICE = 38.0                  # the posted cut, 2026 Bed-Stuy
BARBER_CUT_COST = 5.0                    # supplies + laundry; wages are sunk
BARBER_CUT_TICKS = 5                     # 45-min cut + turnover
BARBER_NOSHOW = 0.12
BARBER_SIGMA = 0.35                      # lognormal WTP-ratio spread
BARBER_RATE = {9: 1.6, 10: 1.8, 11: 2.2, 12: 4.2, 13: 3.8, 14: 1.6,
               15: 1.4, 16: 2.0, 17: 4.4, 18: 4.0}     # requests/hour
BARBER_WTP_MULT = {9: 0.95, 10: 0.95, 11: 1.00, 12: 1.05, 13: 1.05,
                   14: 0.90, 15: 0.90, 16: 1.00, 17: 1.10, 18: 1.10}
BARBER_SHIFT_CHOICES = (-6, -4, -2, 0, 2, 4, 6)   # nego offers, in ticks
BARBER_WINDOW = 6                        # a customer will consider ±1 h
BARBER_FLEX_COST = 0.50                  # $/tick of shift, flexible type
BARBER_RIGID_COST = 4.00                 # $/tick, "I have a 2pm meeting"
BARBER_HASSLE = (2.0, 6.0)               # $ to walk to the other shop
BARBER_SEGMENTS = {
    "cut": dict(n_choices=(1,), n_weights=(1.0,), lead_max=6, gamma=1.0),
}
BARBER_SEG_WEIGHTS = {h: {"cut": 1.0} for h in BARBER_RATE}
BARBER_KINDS = {"cut": (BARBER_CUT_PRICE, BARBER_CUT_COST, 1.0)}

# ── parking ──────────────────────────────────────────────────────────────
PARKING_OPEN, PARKING_CLOSE = 6, 24      # 06:00–24:00 → 108 ticks
PARKING_SPACES = 40
PARKING_FIRST_HOUR = 18.0                # Midtown-adjacent posted rate
PARKING_ADDL_HOUR = 8.0
PARKING_DAY_MAX = 45.0
PARKING_COST_PER_HOUR = 0.40             # marginal ops (ticketing, wear)
PARKING_STEP_TICKS = 6                   # one step = one hour
PARKING_NOSHOW = 0.08                    # app reservations
PARKING_SIGMA = 0.40
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
    "commuter": dict(n_choices=(9, 10), n_weights=(0.5, 0.5),
                     lead_max=1, gamma=3.0),
    # errands: first hour worth the most (gamma 0.7)
    "errand": dict(n_choices=(1, 2, 3), n_weights=(0.45, 0.35, 0.20),
                   lead_max=1, gamma=0.7),
    # theater/dinner: the show is the show (gamma 2.5), booked a bit ahead
    "event": dict(n_choices=(4, 5), n_weights=(0.6, 0.4),
                  lead_max=4, gamma=2.5),
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
BAR_OPEN, BAR_CLOSE = 15, 24             # 15:00–24:00 → 54 ticks
BAR_SEATS = 60
BAR_BEER = (9.0, 2.2, 0.55)              # (list, cost, share of customers)
BAR_COCKTAIL = (16.0, 4.2, 0.45)
BAR_DRINK_TICKS = 3                      # one drink ≈ 30 min of seat time
BAR_NOSHOW = 0.0                         # walk-ins cannot no-show
BAR_SIGMA = 0.45
BAR_RATE = {15: 10, 16: 12, 17: 16, 18: 35, 19: 130, 20: 140, 21: 140,
            22: 110, 23: 50}
BAR_WTP_MULT = {15: 0.85, 16: 0.85, 17: 0.90, 18: 0.95, 19: 1.05, 20: 1.10,
                21: 1.10, 22: 1.05, 23: 0.95}
BAR_SHIFT_CHOICES = (-3, -2, -1, 0, 1, 2, 3)   # ±10/20/30-min seatings
BAR_WINDOW = 3
BAR_FLEX_COST = 0.60
BAR_RIGID_COST = 5.00                    # "we're meeting people at 7"
BAR_HASSLE = (1.0, 4.0)                  # the bar across the street
BAR_SEGMENTS = {
    "drinks": dict(n_choices=(1, 2, 3, 4), n_weights=(0.2, 0.4, 0.3, 0.1),
                   lead_max=1, gamma=0.7),
}
BAR_SEG_WEIGHTS = {h: {"drinks": 1.0} for h in BAR_RATE}
BAR_KINDS = {"beer": BAR_BEER, "cocktail": BAR_COCKTAIL}

# What the live twin-street experiment is FOR

`block/live.py` streams one paired sim-day (STATIC vs SNHP, same crowd) every
few minutes, forever, logging every day-record to JSONL. The page is a trailer;
**the log is the instrument.** This file states the questions the telemetry is
aimed at, so the run improves the product instead of just decorating it.

## The one question simulations cannot answer alone

**WTP discovery under repeat exposure.** Every committed result quotes against
*known* buyer valuations (the sim's oracle). Production must *learn* them from
behavior while customers adapt — the two failure modes being (a) systematic
over-discounting while learning, and (b) demand ratchet / strategic waiting
("I'll always claim flexible and wait for the deal").

The live run is the rehearsal instrument for that pilot question. What it can
already measure, season over season, with venue-level day-records:

1. **Discount-depth vs. realized displacement.** Per venue: the distribution of
   granted depths (list − price) against next-days' full-price sales. A venue
   whose deep-discount days are followed by falling full-price sales is showing
   the ratchet signature. (Fields: `venues.*.d_margin`, `deals`, day ordering.)
2. **Walk-away elasticity.** `traffic.{sticker,snhp}.walkaways` by day type —
   the smoothing claim (fewer walk-aways under SNHP) must hold across whole
   seasons, not on average: count the days it inverts and cluster them.
3. **Loser persistence.** Venues that lose under SNHP (florist/bar/vending on
   many days) — is losing serially correlated (a modeling bias to fix) or mean-
   reverting noise (honest variance to disclose)? The scoreboard shows losers;
   the log says which kind they are.
4. **Waste-clearing attribution.** `waste.*` deltas vs. the days salvage deals
   fired — confirms the salvage lever's value is waste clearing, not price
   subsidy, at street scale.

## Discipline

- Records are append-only, versioned (`schema`, `engine.git`), and reproducible
  (`python3 -m block.live --seed S --season N --day D`). Any analysis that can't
  cite (seed, season, day) doesn't get made.
- When a finding here changes engine defaults, it lands as a property/golden
  test first (the Phase-1 pattern), then the change — never the reverse.
- Analyses belong in `block/analysis_*.py` reading the JSONL; nothing scrapes
  the web page.

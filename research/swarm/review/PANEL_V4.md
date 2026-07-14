# v4 expert panel — consolidated verdict (3 reviewers, 2026-07-14)

*Panelists: market/mechanism-design economist; MRS benchmark methodologist;
adversarial red-team (calibrated on review/ADVERSARIAL_REVIEW.md). All three
reviewed SPEC v4 DRAFT + RESULTS + code before any v4 code existed. This doc
is the condensed synthesis; the consolidated MUST list at bottom is what v4.0
implements.*

## Convergent fatal findings on the draft

1. **P7a was a tautology twice over.** The "snhp compensates cross-company
   transfers" half measures the IR if-statement in `nash_solver.py` (strictly
   positive surplus is *enforced*). And the credit-only ledger cannot see
   energy/sector compensation at all — IR compensates robots in Φ, the claim
   was about companies in credit. snhp+net violates it by design (company-
   blind charity in energy). → Replace with quantities that can come out
   either way: **cross-company cargo VOLUME ratio** (does IR choke the border
   into autarky or sustain it at compensated terms?), **terms of trade**
   (implied energy-per-credit price in border deals; dispersion vs σ), and a
   **measured compensation ratio** (never pinned ≈0), scoped to pure arms.
2. **P7b was the routing argmax reciting its own algebra, on a mis-sized
   grid.** Switch point τ* = EV·(1+λ)·Δdist·eff/(V·load) ≈ 0.48·eff/L → at
   mean load 3: τ*≈0.16, i.e. BELOW the draft grid's first nonzero point
   {0.2, 0.4, 0.8}; the sweep would have produced a cliff-then-flats and
   "monotone" would pass vacuously. → Derive τ* in the spec, re-grid
   {0, .05, .1, .15, .25, .5}, pre-register STRICT decreases between named
   pairs + a non-vacuity floor at τ=0. Re-aim the market-force claims at
   what only bargaining can do: **P7b′ tariff avoidance** (d delivered/dτ
   less negative for bargaining arms — they reroute via border handoffs;
   rules can't) and **P7b″ incidence** (Nash splits the tariff wedge ≈50/50
   in border-deal prices — the textbook price-formation result; the auction
   has no prices so no incidence).
3. **The tariff had no supply side** — "a demand curve with nobody on the
   other side of the market"; revenue evaporated from every objective, so
   deadweight-at-τ>0 was true by construction, and team was a broken merger
   counterfactual (it would irrationally dodge tariffs the cartel owns). →
   v4.0: **team internalizes tariffs** (merged firm pays itself; falsifiable
   prediction: team's foreign share is FLAT in τ, every other arm's falls).
   v4.1: per-company τ set by between-run best-response revenue updates
   (differentiated-Bertrand duopoly; geography keeps the equilibrium
   interior) — THE price-formation result; plus the headline-grade
   pre-registration: **the gray market disciplines posted prices** (τ* is
   lower when the fleet can bargain, because border handoffs undercut the
   refinery's market power). Vouchers stay v4.2 (require the company
   principal to be coherent; they are the law-of-one-price test).

## Convergent majors

- **Geometry must be symmetric** (draft favored company 0 in every term:
  cheaper home loop, tariff-magnet refinery, charger proximity). v4.0 map:
  A1=(6,6), A2=(6,26), B0=(26,6), B1=(26,26), charger (16,16) — exact
  reflection symmetry about y=16; every facility 20 from the charger; each
  company faces the identical haul-home-40 vs foreign-20·(1−τ) tension from
  its far source. Buys a free **placebo test**: company-ledger difference
  centered at 0 by symmetry.
- **Twin fleets** (identical draw multisets per company, mirrored positions)
  + company ⊥ sector stratification (6/6/6/6; the draft's "interleaved ids"
  would have silently made company ≡ sector) + **neutral charger tie-break**
  (the rid tie-break systematically favored one company at the single shared
  facility).
- **Cargo provenance** (mining company × refining company 2×2 matrix) —
  without it, tariff laundering via border handoffs is indistinguishable
  from compliance, and "foreign-refined share" mismeasures. Volume metrics
  split **distress vs healthy** (v1-M6: rescue churn is not commerce).
- **Company metrics are descriptive secondaries**; SYSTEM delivered stays
  primary (zero-sum redistribution on fixed stock is not a win). P7d
  scoped to σ≥0.75 with pre-named regime champions (snhp+net at low σ
  already beats team — "merger premium persists everywhere" was pre-known
  false); decomposed via new arms: **team−team-co = boundary premium**,
  **twofirm** (within-company joint-Φ, cross-company Nash-IR) vs team-co =
  markets-between-firms vs walled cooperation.
- **One shared `delivery_target()`** consumed by BOTH the movement policy
  and Φ's load term (tariff-aware), with destination hysteresis — three
  separate re-entry paths for the v2.1 silent-dead-issue bug were
  identified in the draft. EV stops being hand-set: **endogenous lagged
  ∂Φ/∂battery** per robot.
- **Bridging** (five changes at once vs v3): v3-geometry preset runs
  through the v4 codebase (distributional match to sweep_v3); τ=0 anchor
  column carries the ladder + P7c checked there BEFORE any tariff cell is
  read; P7c loosened to order-of-crossing (charger move shifts every hazard
  margin — pinned thresholds would kill on geometry).
- **Arm fairness:** auction's `_deliver_cost` must use the same
  delivery_target (else the baseline is silently sandbagged in v4);
  auction-co / team-co variants pin the "company walls" rung. snhp needs no
  -co variant — IR *is* the company discipline (state as design, not
  finding).

## Tests that ship with v4.0 (the "evaluated==executed" of this round)

ledger conservation; provenance conservation (2×2 sums to delivered);
**ablations-differ fingerprints** (the automatic v2.1-bug catcher);
issue-liveness (each enabled issue strikes >0 deals; sector/refinery flips
change Φ); Φ/policy consistency by construction; τ* threshold geometry
(pins the grid to the algebra); foreign-share non-vacuity at τ=0;
company×sector orthogonality; charger company-neutrality at σ=0;
ledger deltas predicted by bundle evaluation; distress flags on deals;
tariff-at-refine-only/refine-once; plus the retained v2/v3 suite.

## Reduced grid

Column A (anchor, τ=0): full ladder incl. -co/twofirm × σ × 24 seeds —
carries P7a′, P7c, P7d, placebo, bridges. Column B (tariff force):
τ ∈ {.05,.1,.15,.25,.5} × {null, snhp-hz, team} × σ {0,.5,1} × 24 — carries
P7b′/P7b″ with Page's trend test; Holm within families; runs are the unit
(companies are coupled within-run — analyze as within-run paired diffs).

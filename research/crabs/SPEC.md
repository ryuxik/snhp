# SPEC — implementation of PREREG.md

*Written 2026-07-24, after PREREG.md and BEFORE the first run. PREREG.md is
binding and unedited. This file records the free choices the PREREG did not
pin down, so that "we did not tune to pass the gate" is auditable rather than
asserted. Every number below was fixed before any simulation output existed.*

---

## 0. What PREREG left open, and how we resolved it

PREREG fixes the world, the arms, the gate and the kills. It does not fix
functional forms or the values of parameters it did not ground. Those are
below. Where a choice plausibly moves a kill condition, we say which
direction it moves it and we sweep it.

---

## 1. Units and scale-freeness

All money is in **months of the current external market rent `M_t`**. This
makes the station's dynamic program scale-free, so it is solved once per
regime instead of per station-year. `ANCHOR_RENT = $2,000/month` converts to
dollars for reporting; `ANNUAL_RENT = $24,000` is the denominator for every
"% of annual rent" threshold in PREREG §5 (so K1's bar is **$480/yr** and
K3's is **$240/yr**, fixed, not a moving per-cell denominator).

## 2. Two rents, deliberately distinct

- `M_t` — **external market rent**: what a new lease signs at, here or
  elsewhere. This is the crab's outside option and the station's relet price.
- `r = R/M` — the sitting crab's **rent of record** as a ratio of market.
  `r > 1` is gain-to-lease (paying above market), `r < 1` is loss-to-lease.

## 3. Market process (PREREG §1)

Regimes are **drift** regimes, not level regimes. A stationary level model
would make the loss and gain regimes converge to the same stationary
rent-to-market gap under any fixed policy, which would erase the regime
distinction by construction. So:

- **Burn-in: 5 years, drift 0**, `σ = 0.02`, under arm A's policy in *every*
  arm, so all arms inherit an identical tenure/rent distribution. Not
  measured.
- **Measurement: 4 years** with regime drift on `log M`:
  - LOSS-TO-LEASE: `μ = +0.09/yr` (2021–22 asking-rent growth ran +11–15%;
    +9% is conservative)
  - GAIN-TO-LEASE: `μ = −0.06/yr` (MAA new-lease FY2024 −5.9%, FY2025 −5.8%,
    Q1 2026 −7.0%)
  - `σ = 0.025`

60 stations × 50 habitats × 4 measured years = **240 station-years and
12,000 habitat-years per cell** (PREREG requires ≥200 station-years).

## 4. Crab side

`gain_from_leaving` (months of M), for offer ratio `q`, prior rent `r`,
tenure `j`, switching cost `c`:

```
gain = 12·κ_c·(q − 1)  +  λ_ref·12·(q − r)  −  z  −  c  −  a(j)
P(leave) = p_exo(j) + (1 − p_exo(j))·sigmoid(gain / ν)
```

| Symbol | Value | Basis |
|---|---|---|
| `κ_c` crab horizon on a rent change | 1.6 yr | households discount at ~12% and are myopic; station's is endogenous (DP) |
| `λ_ref` weight on the *increase* | 0.5 | reference dependence; without it `r` cannot matter to a forward-looking crab and the renewal-increase framing has no force |
| `ν` taste-shock scale | 0.60 months | — |
| `c` switching cost | lognormal, **median 3.6 months** ($7,200), `σ_log = 0.7`; 50% redrawn each year | **calibrated to observed elasticity** — see §8 |
| `a(j)` attachment | `0.35·ln(1+j)` months | $485 at j=1 → $1,540 at j=8 |
| `p_exo(j)` non-rent moves | `0.24 + 0.18·exp(−(j−1)/3)` | 0.42 at first renewal → 0.26 asymptote; NAA turnover ~47% is mostly non-rent |

## 5. Station side

The station solves a **dynamic program** over `(r, j)` maximising NPV, with
its own correctly-specified leave model (the §4 form integrated over the
switching-cost distribution — the station knows the distribution, not the
draw). Discount 7%. Value iteration on a 0.02 state grid / 0.01 action grid.

| Symbol | Value | Basis |
|---|---|---|
| `T` turn cost | 1.5 months ($3,000) | NAA/IREM/BOMA triangulation, 1–2 months |
| `v_m` vacancy months | 1.2 (loss) / 1.8 (gain) | soft markets relet slower; 39.7% of 2026 listings carried a concession vs ~1 in 6 pre-pandemic |
| `Q_new` unknown-tenant credit/early-turn risk | 0.22 months | ~1.5% of annual rent, capitalised |
| `Q_sit(j)` proven-payer premium | `Q_new·exp(−(j−1)/3)` | bad debt is a real NAA expense line; PREREG §1 gives the station payment history |
| renewal increase cap | 12% | 2022 renewals averaged +10.7% while asking rents rose faster; caps are why loss-to-lease persists |
| `FACE_RENT_PREMIUM` | **1.0** | see §6 — the parameter K1 rests on |

**Selection correction.** Survivors have high switching costs, so the
marginal distribution is the wrong prior for a long-tenured crab. The station
gets the *correct* tenure-conditional distribution, estimated from a pilot
run on dedicated seeds (9000–9019) and fed back into the DP over 2
iterations. This makes the station strong on purpose: a station with a naive
prior would over-concede to long-tenure crabs and flatter V3.

## 6. Concession instruments — the economics that decides K1

PREREG's ranked-ask claim is that a headline rent cut is the *hardest* ask.
For that to be true, face rent must cost the landlord more than its cash
value. Our first pass at this found the obvious channel is **too weak to
carry the claim**: differential discounting alone gives a station/crab
persistence ratio of ~1.03, i.e. essentially nothing. We record that here
because it is the honest starting point.

The channel that is actually large in multifamily is **capitalisation of
face rent**: rent rolls drive appraised value and loan covenants, and
concessions are conventionally treated as non-recurring. We model it as one
named parameter:

```
station objective = PV(cash) + FACE_RENT_PREMIUM × PV(face rent while occupied)
```

- `FACE_RENT_PREMIUM = 1.0` primary (a dollar of face rent is worth 2× its
  cash). Cap-rate arithmetic (20× annual at a 5% cap, against a ~1.5-year
  cash horizon) implies far more, so **1.0 is conservative for us**: a lower
  premium makes rent cuts cheaper for the station and makes K1 *more*
  likely to fire.
- Swept over {0, 0.5, 1.0, 2.0, 4.0}; we report the value at which K1 flips.

**Building-comp spillover: NOT modelled.** The article says a rent cut
"resets the comparable for the entire building". Implementing that as a
station-side cost with no offsetting beneficiary would break cash
conservation, and implementing it as a real building-wide feedback is
speculative. We set it to zero, which is the conservative choice, and we
report that the article's building-wide framing is stronger than what the
mechanism needs.

Instruments, all sized to deliver the **same crab value** (`ASK_FRAC = 0.11`
of annual rent — RealPage Jun 2026, ~6 weeks) so the comparison is purely
about the station's cost:

| Ask | Crab gets | Station pays | Face rent |
|---|---|---|---|
| ONE_TIME (free weeks) | 11% of annual rent, cash, once | same, once | untouched |
| FEES | ancillary fees waived **2 years**, capped at 4% of annual rent | 2 years of cash | untouched |
| TERM | 2-year lock at `q·(1−d)`, `d ≤ 8%` | 2 years of lower rent, **minus** the turnover risk it no longer bears | reduced |
| RENT | `q·(1−0.11)` permanently | persistent cash **and** face rent | reduced |

TERM is a genuine trade, not a giveaway: the station buys two years of
certainty. The crab only asks for it when its own naive forecast of next
year's market says locking in is worth it — which makes TERM a good rung in
the loss regime and a bad one in the gain regime.

## 7. Negotiation protocol

- Crab strategies: `NEVER_ASK`; `ASK_PRICE` = ladder `[RENT×1.0, RENT×0.6,
  RENT×0.35]`; `ASK_RANKED` = ladder `[ONE_TIME, FEES, TERM, RENT]`, PREREG
  §4's order, unchanged even where our own cost model would reorder it.
- **Station patience** `P_CONTINUE = 0.60` per additional round. Without
  this, RANKED nests PRICE (it reaches the rent rung too) and K1 could not
  fire on a level playing field. Swept {0.3, 0.6, 0.9}.
- **Substitution** `P_SUBSTITUTE = 0.35`: chance the station answers a
  refused ask by volunteering a cheaper instrument ("not rent, but here's
  four weeks"). This is the parameter that *shrinks* C−B, so a high value is
  conservative for us. Swept {0, 0.35, 0.7, 1.0}; at 1.0 we expect K1 to
  fire and will report it.
- Station grant menu: `{1.0, 0.6, 0.3, 0}` × the ask; it takes the largest
  size with `NPV(grant) ≥ NPV(refuse)`. A grant ends the negotiation.
- Crabs skip rungs with non-positive expected value to themselves.

## 8. Calibration discipline — stated up front

- **V2 (retention) is partly calibrated in, not predicted.** The crab
  switching-cost distribution (§4) is set so the model reproduces the two
  observed elasticity facts: +10.7% renewal pushes with 57.3% retention
  (2022), and sitting rents ~12% above market with ~54% retention (2026).
  Retention is one of those facts. We say so rather than claim V2 as a win.
- **V1 (counter success ≈22%) and V3 (tenure ratio ≥1.5×) are genuine
  out-of-sample predictions** of the station's DP. No station parameter is
  set by reference to them.
- If anything is changed after seeing a gate number, the run is relabelled
  **exploratory** and the gate is re-run on held-out seeds 7000–7059.

## 9. Seeds (fixed here, before running)

| Purpose | Station seeds |
|---|---|
| Pilot (station's selection prior) | 9000–9019 |
| Main / gate / all arms | 1000–1059 |
| Held-out (only if we tune) | 7000–7059 |

Burn-in draws come from a regime-independent stream, so both regimes and all
arms share an identical burn-in. Within the measurement window, per-crab
draws are pre-generated per `(station, habitat, year, purpose)` so arms see
common random numbers wherever their histories agree.

## 10. Metric definitions (fixed before running)

- **Crab surplus, per occupied crab-year**: `12·M_t − cash paid` if the crab
  stays; `−(c + a(j))` in the year it leaves; `0` for a new arrival's partial
  year. Measured against paying market rent with no move.
- **Asker / non-asker**: a strategy trait assigned at move-in and held for
  life, so the split is well defined in every arm (PREREG §"Track askers and
  non-askers separately").
- **Counter success (V1)**: share of counterers who obtain **any** realised
  concession. The price-only figure is reported alongside; the choice is
  made here, before seeing either.
- **Retention (V2)**: `1 − leave rate` over habitat-years where a renewal
  decision was actually made. Years inside a TERM lock have no expiry and are
  excluded from the denominator.
- **V3 tenure split**: `<2y` is tenure exactly 1; `2y+` is tenure ≥ 2.
- **K4 "materially larger"** (PREREG leaves the word open): K4 FIRES unless
  `(C−A)_gain − (C−A)_loss ≥ 1% of annual rent ($240/crab-year)`. Same bar as
  K3, chosen for consistency and fixed here before running.
- **Gate applies in BOTH regimes.** PREREG §3 does not say which regime, and
  the targets come from both eras (Avail 2022, RealPage 2024-26). Requiring
  both is the stricter reading, so that is the one we take. The loss regime is
  reported first because that is where Avail measured.
- **K2/K3 baseline**: `S0` = mean surplus at asker share 0, per arm and
  regime. Value of asking `VOA(σ) = asker surplus(σ) − S0`. K2 is evaluated
  on `VOA_E(σ)/VOA_D(σ)`; the literal reading of PREREG ("per-asker surplus"
  as a *level*) is degenerate because levels are dominated by the common
  `12·M_t` term, so we report it too but decide on the ratio of the value of
  asking. K3 uses PREREG's own baseline (non-asker surplus at σ=0) verbatim.

## 11. What is approximate, and where

The station's **decision model** is approximate in three places; the
**realised accounting** is exact in all three.

1. The fee waiver's second year is charged to the station's DP up front
   rather than carried as an extra state dimension.
2. TERM is valued by an explicit two-year formula on the DP's value grid, not
   by adding a lock dimension to the grid.
3. The adaptive station (arm E) anticipates the counter stage as "I will grant
   my own best concession", which is optimistic and therefore makes it push
   its opening offer *harder* — conservative for our thesis.

# Calibration targets — sim vs. 2026 reality, sourced

*2026-07-10. Five research sweeps (fashion/resale, boba/bakery/flowers,
vending, cross-domain behavioral, barber/parking/bar), each verified against
primary sources where they exist. Rule inherited from the whitepaper's rigor
standards: every consumer-model parameter is either (a) anchored to a named
source, (b) swept over the published evidence band, or (c) explicitly labeled
an assumption. This file is the ledger of which is which.*

## 1. Vending — the worst violation in the family

| Parameter | Sim | Reality | Source |
|---|---|---|---|
| Vends/day, average machine | ~74 | **7–8** ($15.8/day avg; strong locations ~$50/day) | SOTI 2025 + Cantaloupe Micropayment Trends 2025 |
| Arrival→purchase conversion | ~100% | far below (70-person office ≈ 5–15 vends/day) | industry rule of thumb |
| Avg ticket | $3.40 | $2.11 (cashless $2.24 / cash $1.78); Smart Store $4.25 | NAMA/Cantaloupe 2024 |
| Spoilage | ~0 realized | micro-market shrink 4%; fresh food ~10% | Cantaloupe primary |
| Sellouts | daily | rare — prekitting economics exist because slots DON'T sell out | trade practice |
| Category mix | snack/fresh heavy | cold bev 25%, snacks 17.6%, candy 16.6%, healthy 8.7%, food 8.3% | 2024 industry mix |

**Implication (honest, load-bearing):** per-machine dollar deltas in the
headline tables are computed on a machine ~10× hotter than the US average.
Recalibrating traffic will shrink absolute $/machine/day roughly
proportionally. Mechanism claims (paired relative results, CIs) are
unaffected in sign; the commercial story moves to the **route** level
(operators run 50–200 machines). The sim's current profile is defensible
only as a top-decile "Smart Store" fresh-food machine — if kept, label it so.

**Citation fix (whitepaper):** the SNBC 60M-transaction dataset is in arXiv
**2606.08896** (FAME), not 2602.12147, and it is proprietary. Public fit
sources: Kaggle *Vending Machine Sales* (awesomeasingh; 5 real NJ machines,
2022, per-transaction) and Kaggle *Coffee Sales* (ihelon; intraday).

## 2. Fashion + resale

- Full-price sell-through: real **50–70%** (target 70, actual ~60 at sale
  start); season-end 90–95% after clearance. Sim control cells at 84–100%
  are not credible as full-price. (FashionUnited 2023; Caro–Gallien 2012 the
  markdown anchor, +6%.)
- Markdown ladder: 2–3 steps (25→40→60); a single −70% jump overstates
  velocity.
- Returns: **16.9% retail / 26% online apparel** (NRF 2024). Sims model zero
  returns — material violation for any e-comm arm.
- Strategic waiters: structural estimates 5–19% (airlines, Mgmt Sci 2014);
  45% is stated-preference only. Grid {15%, 45%} defensible if labeled.
- Resale: ThredUp ~50% sell within 30 days (FY2025 10-K) — sim median ≈ 0
  days flatly contradicted; move to weeks–months hazard.
- eBay Best Offer (Backus et al., QJE 2020; 88M listings): first offer ≈
  60.8% of list; seller accept/counter/decline 32/28/40; **buyer
  decline-after-counter 58%** (sim huff 25% is low); bargained sale ≈ 73–83%
  of list. Direct input to the vintage offer/1 mechanics and the in-flight
  retag/shading fix.
- Datasets: H&M Kaggle (31M tx, normalized prices), VISUELLE (12-week
  curves), NBER Best Offer, Mercari.

## 3. Boba / bakery / flowers

- Boba volume: 150–230 cups/day median (KFT/Gong Cha FDD AUVs); sim 260 ≈
  P70 busy-urban — label. NYC milk tea $5.25–5.50 — sim fine.
- **Balking functional form: abandonment is nonlinear in queue LENGTH, not
  expected wait** (Lu et al., Mgmt Sci 2013, canonical). Sim's 8%/min linear
  spec contradicts it; re-spec before quoting the capacity-smoothing lever.
- Topping attach 0.86: **zero published support** — assumption, must be
  labeled; it feeds the cart +$270–350/day headline, so sweep it.
- Bakery: waste ~13–14% (Sweden surplus studies; FMI 8.5% in-store) — sim
  well calibrated. Day-old −50% correct; noon pull is aggressive vs.
  practice (end-of-day / 2h before close). French bakery Kaggle (136K POS
  tx) is the ground truth to fit.
- Flowers: supermarket floral shrink ~9% of dollars (IFPA) vs. sim 30% unit
  dump at day 4 — defensible only as a low-volume independent; flag.
  Display life 5–14 days with care — relabel sim's 3–5 as "retail display
  life." V-Day ×6 arrivals, $107/dozen NYC, wholesale +79% — all confirmed.

## 4. Barber / parking / bar (slots domain)

- Barber no-show: platform-measured **3–5%** (Zenoti 30k businesses, Squire
  13.9M appts) — sim 12% defensible only as a no-deposit low-tech shop
  (no-deposit range 15–25%); deposits collapse it to 3–5%, which is itself a
  finding: **the deposit IS the venue's existing negotiation mechanism**
  (supports CRITICAL-ANALYSIS §6's scope note).
- Barber utilization: **62% average** (Squire and Zenoti independently);
  sim's realized 45–49% is a below-average shop; recalibrate "average" to
  ~60%. Bed-Stuy $38 cut confirmed. Booking lead time: no published number
  exists — assumption.
- Parking elasticity: SFpark **−0.4** (Pierce–Shoup 2013; the often-quoted
  −0.04 is a misreading; Millard-Ball: treat as upper bound); meta-analysis
  −0.63 occupancy / −0.30 volume (Lehner–Peer 2019). **Commuters are the
  LEAST elastic segment** — the sim's 7–9am crowd should be hardest to move.
- Parking occupancy: observed Seattle garages 58% core / 48% outside; sim
  68–69% = hottest-subarea level, not average. NYC price points confirmed
  ($18 first hour / $45 max inside published ranges). Reservation no-show:
  unpublished anywhere — sim 8% is an assumption, label it.
- Bar: **Saturday alone >25% of weekly sales; Sat 5–6pm checks ~40% above
  10pm; happy-hour checks average ~$8 HIGHER than other dayparts** (Nielsen
  CGA). The sim's "dead 5–7pm" is wrong on weekends — this touches the
  relief-term conclusions at the bar. Promo-window elasticity ≈ −1..−2
  (Babor 1978, the only true price experiment). NYC $16 cocktail / $8–9
  beer confirmed. Seat occupancy: no public benchmark — unfalsified.
- Fit sources: SFMTA meter transactions (session-level), Melbourne bay
  sensors (best public duration distributions), Yelp Open Dataset check-ins.

## 5. Cross-domain behavioral (fairness model inputs)

- Loss aversion: meta-analytic mean **1.955** [1.82, 2.10], median 1.69
  (Brown et al., JEL 2024, 607 estimates); **price-specific λ = 1.66**
  (Hardie–Johnson–Fader 1993, Table 2 — the "λ≈2.4 for price" folklore is
  wrong); heterogeneity makes scanner estimates an upper bound
  (Bell–Lattin 2000). Sim λ=2.0 is slightly high → sweep **1.66–1.95**.
- Reference-price carryover: **price carryover 0.47–0.65** (Briesch et al.
  1997, Table 6; the 0.7–0.9 folklore conflates LOYALTY carryover);
  HJF temporal γ=0.847. Sim's 0.80 sits at the top of the published span
  0.5–0.85 — keep, flag, sweep.
- Dual entitlement: KKT's 82%-unfair **does not replicate** at 1986 levels
  (<50% in a 2023 large-N replication; apology/rationale raise tolerance).
  Direction favorable: our churn penalties are likely conservative, so the
  harvestability result is robust to this correction.
- Dynamic-pricing acceptance is category-dependent: theaters ~40% fair,
  concerts 33%, sports 35% (YouGov); **restaurants: 52% equate it with
  gouging** (post-Wendy's) — supports the whitepaper's category-scoped
  discount-only invariant.
- Elasticity anchors: food-away-from-home −0.7/−0.8 (USDA); beer −0.46;
  apparel SKU −1.17..−2.21; the −2.62 grand mean is brand-level, not
  category-level — don't misuse it.
- 2026 context for the paper's framing: AI/agents ≈20% of holiday-2025
  digital orders (Salesforce, loose attribution); 39% of consumers have used
  gen-AI for shopping; BNPL 15% of adults (Fed SHED, gold standard);
  contactless >60% of Visa face-to-face.

## Top-10 recalibration priorities — (headline impact) × (ease)

1. **Vending traffic ÷10 + conversion model** — arrival scale so the machine
   does 7–8 vends/day (keep a "Smart Store" P90 cell, labeled). Re-run vend
   headline + block. *Impact: every $/machine number. Ease: one scale + one
   conversion parameter.*
2. **Block fashion arrival scale → 85–92% sell-through + 7-day CI blocks**
   (already pre-registered, CRITICAL-ANALYSIS §5) — unblocks the block's
   fashion row from "non-informative."
3. **Fairness-parameter sweep to evidence bands** — λ ∈ {1.66, 1.95},
   carryover ∈ {0.5, 0.65, 0.85}; re-quote harvestability as a range. Cheap
   compute, protects the single most attackable consumer-model choice.
4. **Boba balking re-spec on queue length** (Lu et al. 2013 functional
   form) — the capacity-smoothing lever ($165–206/day) must survive it.
5. **Vintage time-on-shelf + huff recalibration** — weeks–months hazard
   (ThredUp 30d/50%), buyer decline-after-counter 58% (QJE) — feeds directly
   into the in-flight retag/shading fix; re-run offer/1.
6. **Fashion returns 16.9–26% on e-comm arms** — a return is a negative
   sale with a lag; material for season economics.
7. **Bar weekend curve** — Sat-heavy weekly shape, happy-hour checks
   HIGHER not lower; re-run slots bar cells (touches the relief-term
   conclusion).
8. **Barber utilization → ~62% and no-show → deposit-regime 3–5%** — reframe
   the barber ≈0 result: deposits are the incumbent mechanism; our frame
   under-scopes the venue (subscriptions/deposit terms, per §6).
9. **Floral shrink 30% → ~9% + display-life relabel** — robustness of the
   florist boundary finding (computed > nego) at realistic dump rates.
10. **Assumption-label + citation sweep** — declare unanchored params in
    each results doc (boba attach 0.86, barber lead time, parking
    reservation no-show 8%, bar seat occupancy, vending ticket premium);
    fix SNBC → arXiv 2606.08896 (proprietary) and point referee-proofing
    item 4 at the Kaggle NJ vending dataset.

*Sequencing note: 1, 2, 5, 7 change headline tables and must land before the
whitepaper's final number refresh; 3 and 10 are cheap and land with it; 4, 6,
8, 9 are pre-registered follow-ups that can post-date arXiv v1 if labeled.*

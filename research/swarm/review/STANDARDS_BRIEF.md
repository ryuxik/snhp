# How the field's leading authorities would judge this benchmark

*Research agent deliverable, 2026-07-14. Literature/standards synthesis — every
claim corroborated by ≥2 sources where possible; [VERIFY] flags at bottom.
Companion to ADVERSARIAL_REVIEW.md (code/stats critique).*

## 1. The authorities and their lenses

| Authority | Where | Lens |
|---|---|---|
| Marco Dorigo | IRIDIA, ULB | Swarm-engineering discipline; ARGoS/reality-gap culture; gatekeeper of the word "swarm" |
| Radhika Nagpal | Princeton SSR | Scale (kilobot 1024, *Science* 2014); "swarm" = hundreds+, strictly local rules |
| Erol Şahin | METU-ROMER/KOVAN | Wrote the defining criteria (2005) — the boundary police |
| Heiko Hamann | U. Konstanz | *Swarm Robotics: A Formal Approach* (2018): claims need predictive models, not lucky configs |
| Roderich Groß | Sheffield | MNS (Nat. Comms 2017), SoNS (Sci. Robotics 2024); real-robot validation |
| Vijay Kumar | Penn GRASP | Hardware physics: energy, bandwidth, payload as first-class constraints |
| Alan Winfield | Bristol Robotics Lab | Robustness-as-metric, fault injection, honest failure analysis |

Survey lineage: Brambilla, Ferrante, Birattari & Dorigo 2013 (*Swarm
Intelligence* 7:1-41); Bayindir & Şahin 2007.

## 2. Published methodological norms

- **Şahin 2005** (LNCS 3342, pp. 10-20) — five criteria for "swarm robotics":
  (1) autonomous robots; (2) large numbers or rules that provably scale;
  (3) individually incapable/redundant units; (4) **local sensing and
  communication only**; (5) homogeneous, no central controller. Three desired
  properties: **robustness, flexibility, scalability**.
- **Brambilla et al. 2013** — swarm engineering framing; flags the field's own
  lack of validation metrics (cuts both ways: benchmarks welcome, methodology
  scrutinized harder).
- **Hamann 2018** — macro/micro models that *predict* collective performance;
  "show the model that explains why it wins, not one config."
- **Dorigo/ARGoS culture** — multi-physics simulation to narrow the reality
  gap; flagship results pair sim with real robots (kilobots, e-pucks).
- **Reality gap** — Jakobi, Husbands & Harvey 1995; Jakobi 1997
  radical-envelope-of-noise: noise-free results are presumed non-transferable.
- **Market/negotiation lineage is a different field** — Dias, Zlot, Kalra &
  Stentz (*Proc. IEEE* 2006), Gerkey & Matarić (*IJRR* 2004): bargaining over
  utilities is MRS/MAS tradition, not swarm tradition.

## 3. Attack surface on our benchmark (ranked)

1. **Categorization (likely fatal if unaddressed):** full-information Nash
   bargaining presumes each party knows the other's utility — exactly the
   "global knowledge" swarm robotics defines itself against. Dyadic deals are
   MAS units of study; swarm behavior is emergent-from-many. Expect: "correct
   game theory, mislabeled field."
2. **Scale:** 24 is not a swarm (reference points: tens of e-pucks to 1,024
   kilobots). Scalability is a size-sweep claim — need N ∈ {10..1000} curves
   showing the multi-issue edge persists or grows.
3. **Full information assumes away the hard part:** partial, local, noisy
   estimates are the reality; a result that needs perfect information says
   nothing about observable macro behavior.
4. **Deterministic + noise-free ⇒ presumed artifact:** no sensor/actuation/
   localization noise, no comms dropout; robustness (a defining pillar) is
   untested. Winfield would demand fault injection (kill k robots, degrade
   charger, corrupt utilities).
5. **Grid abstraction:** 32×32 cells + Chebyshev-2 comms is cellular-automaton
   land; no kinematics, collisions, interference. ARGoS exists to avoid this.
6. **Baseline strength:** "multi-issue beats single-issue" is near-trivially
   true by construction (bundling weakly dominates); the burden is showing
   *how much*, against *tuned* baselines, and whether coordination overhead
   survives realistic information limits.
7. **Heterogeneity + full info + pairwise optimization** reads as coalition
   formation/MRS, further from swarm.

## 4. Physical plausibility of the deal-space assumptions

- **Energy transfer 25% loss:** defensible mid-range. Real numbers: ~90%
  ferromagnetic-core stationary; ~46-50%+ UAV wireless systems (up to ~90%
  PT-symmetric); in-motion peer-to-peer often 45-60%. The weak part is not the
  number but **determinism** — real loss varies with alignment/distance/state
  of charge, and that variance is the hard part.
- **Battery-swap trophallaxis is real hardware** (Ngo & Schiøler CISSbot):
  near-lossless charge via physical swap, pays in time/docking/mechanism. Our
  abstract "energy with 25% loss" conflates lossy WPT with near-lossless swap.
- **Cargo handoff exists** (UAV↔UGV docking; s-bots gripping) but the three
  bundled issues have *very different* time constants and failure modes:
  sector swap = instant and free; energy transfer = minutes and lossy; cargo
  handoff = precision docking. Treating them as commensurable in one atomic
  Nash bargain needs explicit justification.

## 5. Credibility bar (evidence package)

1. Scale sweep N ∈ {10, 50, 200, 1000} — edge must persist or grow.
2. Drop or bound full information (estimated utilities), OR reposition
   honestly as market-based MRS and benchmark in that lineage.
3. Noise + robustness study (mandatory): sensor/actuation noise, comms
   dropout, fault injection, graceful-degradation curves.
4. Continuous space/physics (ARGoS or similar).
5. Tuned baselines + CIs + effect sizes.
6. A predictive model of WHEN bundling wins (Hamann bar) — not just runs.
7. Even a minimal 10-20 robot hardware demo (e-puck with energy exchange)
   transforms credibility.
8. Model the 25% loss as a distribution; justify the atomic bundle.

**Venues:** Swarm Intelligence/ANTS (hardest on the label), DARS (friendly to
MRS framing), **AAMAS (correct home if the mechanism is the contribution)**,
ICRA/IROS (demand hardware), Science Robotics (only with large-scale hardware).

## Bottom line

Either do the swarm work (strip global info, sweep N, inject noise, continuous
physics, hardware demo) — or **reposition in the MRS/MAS lineage where full
information and pairwise bargaining are legitimate**, and beat the Dias/
Gerkey-Matarić baselines there. The mechanism is publishable; the current
label is not.

## Flagged / weakly verified

- Brambilla 2013 exact validation statistics not confirmed verbatim (open
  mirror gave positions, not quotes) — check Springer PDF before quoting.
- Dorigo/Theraulaz/Trianni 2021 *Proc. IEEE* passages are faithful paraphrases
  via a summarizer, not verified verbatim.
- Kumar's exact current title (Dean vs former Dean) unverified; "Professor,
  GRASP Lab, Penn" is safe.

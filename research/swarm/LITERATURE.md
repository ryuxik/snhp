# Multi-issue negotiation as a swarm coordination primitive — literature position

*Adversarially-verified deep-research sweep, 2026-07-14. 5 search angles, 20 primary
sources fetched, 96 claims extracted, 25 verified by 3-vote adversarial panels:
23 confirmed (all 3-0), 2 refuted. Full machine-readable report in the session
task output; this file is the durable summary.*

## Verdict

**The niche is OPEN.** No published system implements multi-issue bilateral
negotiation — logrolling or Nash *bargaining* over ≥2 coupled issues (energy
transfer + task load + movement rights) bundled in a single deal — as a
coordination primitive between robots. The two parent literatures are each
mature; nothing occupies their intersection.

## The map: what is already claimed (must-cite prior art)

### 1. Robotics-side "negotiation" is uniformly single-issue

| Work | What is negotiated | Scale / medium | Baseline beaten |
|---|---|---|---|
| Cui, Guo & Gao, *Robotica* 31(6) 2013 — game-theory-based negotiation for MRTA | task reallocation only (Pareto-seeking) | simulation | contract-net initial allocation |
| Ke et al., *J. Electronics (China)* 2012 — LSSVR opponent-utility modeling + H∞ control | task allocation only | simulation (low-tier venue, ~7 cites) | — |
| MURDOCH (Gerkey & Matarić 2002) | task assignment via first-price one-round auctions; each bid is structurally ONE scalar fitness score | physical robots | — |
| Zlot 2006 (CMU thesis, TraderBots task-tree auctions) | task trees; a bid = task ID + scalar price + tree structure. Full-text grep (187 pp): zero hits for Nash / logroll / multi-issue / bargain / energy | sim + robots | single-task auctions |
| Lin & Zheng, ICRA 2005 — "combinatorial bids" | bundles of TASKS with one scalar price per bundle (coalition bidding) — the terminology trap: combinatorial ≠ multi-issue | simulation | — |

Also verified: a Dec-2025 EAAI paper ("Nash-based MRTA in dynamic robotic
networks", 5–20 robots vs Hungarian method) uses Nash **equilibrium** of a
non-cooperative task-selection game — no offers, no deals, no inter-robot
exchange; energy is environment-harvested inside each robot's own utility.
Second terminology trap: "Nash + robots + energy" ≠ bargained energy trades.

### 2. Robot-robot energy exchange exists but is rule-based, never bargained

- Ngo & Schiøler (ICARCV 2008, CISSBots): physical battery swapping via direct
  contact; probabilistic Markovian "randomized trophallaxis." No offer or
  acceptance step, no second issue.
- Moonjaita, Philamore & Matsuno (*Artif. Life & Robotics* 2018): donor/recipient
  roles fixed by predetermined battery thresholds; transfer amount fixed by
  energy-averaging. Numerically coincides with an egalitarian split but no
  agreement is ever struck.
- Schmickl & Crailsheim virtual-trophallaxis: energy couples to navigation as
  emergent *signaling* (gradient), not negotiation.

**Implication:** the physical channel (energy transfer between robots) is
already demonstrated in hardware. Only the bargaining layer on top is missing.

### 3. The multi-issue negotiation community never crossed into robot-robot coordination

- ANAC 2010–2015 ran entirely in the Genius simulator among disembodied agents
  (organizers' AI Magazine retrospective: zero occurrences of
  robot/swarm/embodied/physical). The 2015 roadmap targeted marketplaces,
  energy markets, telecom — not robotics.
- ANAC 2025 (arXiv:2604.13914): all leagues still virtual economic scenarios;
  2026 direction is LLM integration, still not robotics.
- Only robotics crossover: dyadic human-robot *social* negotiation (one
  Nao/Pepper vs one human; Aydoğan et al., IEEE THMS 2021). Not an inter-robot
  primitive. (A stronger claim that this line imports ANAC concession tactics
  was REFUTED 1-2 — do not repeat it.)

### 4. 2023–2026 LLM × multi-robot work is single-dimension dialogue

- MARLIN (arXiv:2410.14383): robots "negotiate" only over which movement action
  to take next (joint navigation plan).
- Consensus-seeking LLM agents (arXiv:2310.20151): each agent's state is one
  number; negotiation = converging on a single shared value.
- AgenticPay (arXiv:2602.06008): LLM buyer-seller negotiation, price-only.
- CLiMRS (arXiv:2602.06967): "adaptive group negotiation" for heterogeneous
  multi-robot LLM collaboration — subgroup formation, not issue-bundled deals.
- May-2025 multi-agent embodied-AI survey (arXiv:2505.05108): the words
  negotiation/auction/bargain do not appear in the accessible full text at all.

### 5. Survey-level absence

ACM Computing Surveys MRTA systematic review (57(3), Oct 2024): no negotiation
/ bargaining / logrolling / multi-issue technique in its taxonomy (verified at
abstract/topics/reference-title level only — full text paywalled; MEDIUM
confidence; a companion claim about its reference list was refuted 0-3).

## What remains unclaimed

1. Any system where ≥2 robots strike a single agreement bundling ≥2 negotiable
   dimensions traded off against each other (energy-for-cargo,
   coverage-for-charge, load-for-movement-rights).
2. Any use of the Nash **bargaining solution** (vs Nash equilibrium) between
   robots.
3. Any benchmark of such deals against auction and stigmergic baselines at
   swarm scale.

## Caveats (honest limits of the sweep)

- Absence-of-evidence structure: an occupant could exist in an unindexed venue,
  non-English literature, or under different vocabulary ("multi-attribute
  contracting", "barter", "resource exchange protocol").
- Four load-bearing sources verified at abstract level only (Robotica 2013,
  Ke 2012, EAAI 2025, CSUR 2024); full-text greps done for Zlot thesis,
  MURDOCH, ANAC retrospective.
- The most plausible hidden occupant: RoCo/CoELA-style LLM multi-robot dialogue
  doing de facto multi-issue trades in free-form chat without negotiation-theory
  vocabulary. Not exhaustively excluded.
- Sandholm/Klein/Faratin "complex contracts" MAS threads (O-contracts with side
  payments etc.) were not exhaustively checked for embodied instantiations.
- Verdict is current to mid-2026; short shelf life at the LLM-robotics pace.

## The open theory question (which the benchmark answers)

Is the niche open because it is *unexplored*, or because it is *not worth
occupying*? I.e., under what heterogeneity conditions (correlated vs
anti-correlated marginal utilities across energy/task/position) do logrolling
gains between robots exist at all? SPEC.md pre-registers this as the
experiment's primary axis and its kill condition.

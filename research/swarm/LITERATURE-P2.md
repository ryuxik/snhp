# Green Dashboard, Robbed Books — Paper 2 prior-art position

*Adversarial prior-art sweep, 2026-07-23. 19 search angles, 7 primary sources
fetched (1 full-text PDF read), covering five niches for the two result
families: (A) INTEGRITY — throughput-flat/ledger-rot dissociation +
attestation-gating; (B) BILLS — negotiable delivery claims → relay-chain
formation, Coase inertness of internal transfer prices, no hold-up,
Holmström-violating incentive terms destroying chains. Verification level
marked per work: [F] = full-text or landing-page fetched this sweep,
[A] = abstract/search-snippet level only, [B] = background knowledge, NOT
verified this sweep — re-verify before citing.*

## Top-line verdict

Every niche's **components** are occupied by mature parent literatures; none of
the five **specific findings** is claimed anywhere we could find. The paper's
exposure is not "someone did this" but "a reviewer collapses us into an
incumbent." The two collapse risks: Science Robotics 2023 token-economy
(for INTEGRITY) and the negotiated-transfer-pricing ABM line (for BILLS/Coase).
Both are must-cite-and-differentiate, not occupants.

---

## Niche 1 — Deception/misreporting in multi-robot systems

### Must-cite map

| Work | One-line characterization | Ver. |
|---|---|---|
| Strobel, Castelló Ferrer & Dorigo, AAMAS 2018 — "Managing Byzantine Robots via Blockchain Technology…" | first PoC: Ethereum smart contracts inside an ARGoS swarm identify/exclude Byzantines in a binary collective-decision task | [A] |
| Strobel, Castelló Ferrer & Dorigo, *Frontiers Robot. AI* 2020 | compares blockchain consensus protocols for resilience to Byzantine robots; security framing, no economics of loss | [A] |
| **Strobel, Pacheco & Dorigo, *Science Robotics* 8(79) 2023, eabm4636** — token economy neutralizes Byzantines | collective sensing (fraction of white tiles); crypto tokens gate participation in "security-critical activities"; Byzantines run out of tokens and lose influence; 24 physical + 100+ simulated robots | [F] (via Dryad dataset description) |
| Zhao, Pacheco, Strobel, Reina, Liu, Dudek & Dorigo, IROS 2023 | generic framework for Byzantine-tolerant consensus achievement in swarms | [A] |
| Wang et al., *J. Field Robotics* 2025 | parallel BFT consensus for blockchain-secured swarm robots — the line is alive and scaling | [A] |
| **Kattepur & Khemkha, *EAI Trans. Smart Cities* 2021** — mechanism design for Industry 4.0 multi-robot task auctioning | VCG auctions for warehouse pick-and-place robots; scenarios explicitly include selfish agents, erroneous/biased bids, and "collusion with erroneous estimates"; claims effective mechanisms yield fair outcomes despite biased bids; simulation only | [F] (2 pp. read) |
| Shim & Arkin, IEEE SMC 2013 — taxonomy of robot deception | 8-type deception taxonomy, almost entirely HRI-facing; robot-deceives-robot corner is thin (squirrel-caching demos) | [A] |

Also present: MITM/misinformation attacks on collective perception
(Byzantine Swarm-SLAM, DARS 2024 [A]); a 2025 *Sci. Rep.* on
blockchain-enhanced incentive-compatible MARL [A] — smart-contract
penalty/reward for strategic MARL agents, disembodied.

### Why they don't occupy

The blockchain-robotics line's exploit target is **informational** (corrupt the
swarm's estimate/consensus) and its headline metric is estimate accuracy; the
defense is stake-gated *participation*. Nobody runs a **bargaining market**
among robots where the exploit is **distributive** — the victim's ledger bleeds
while the task gets done — and nobody decomposes four independent error sources
(strategic lying, miscalibration, stale maps, non-stationarity) under one
attestation treatment. Kattepur & Khemkha get closest to "misreports +
mechanism + robots" but test classic auction-mechanism robustness (fair
allocation despite bad bids), not ledger integrity, and never let honest robots
*lose money*.

**Verdict: CONTESTED.** "Robots misreport + economic mechanism defends" is
occupied territory; our specific finding (exploitation is distributive, not
allocative; attestation zeroes it in a bargaining market) is unclaimed but must
be positioned against Science Robotics 2023 explicitly and early.

---

## Niche 2 — "Output metrics mask ledger corruption"

### What the refutation attempt found

| Work | One-line characterization | Ver. |
|---|---|---|
| **Lei et al. 2026, arXiv:2605.10059 — "Strategic Exploitation in LLM Agent Markets"** (TruthMarketTwin) | LLM text agents in e-commerce bilateral trade autonomously exploit reputation-based governance; warrant enforcement reduces deception. Closest living relative. No throughput/ledger dissociation claim in abstract; no embodiment | [F] (abstract) |
| "When AI Agents Collude Online" 2025, arXiv:2511.06448 | collaborative LLM financial fraud on social platforms — harm framing, not accounting framing | [A] |
| Multi-Agent Risks from Advanced AI (Cooperative AI Foundation), arXiv:2502.14143 | taxonomy-level warning that agents may mislead market participants; no experiment with our structure | [A] |
| Blocki, Christin, Datta, Procaccia & Sinha — Audit Games (IJCAI'13, AAAI'15) | "audit" here = Stackelberg allocation of scarce inspection resources + punishment levels; nothing about output metrics masking books | [A] |
| TRiSM-for-agentic-AI review (arXiv:2506.04133) and enterprise audit-trail guidance | governance prose: log everything, propagate trace IDs; prescriptive, no *finding* | [A] |
| Mitsch ABM line (see niche 5) | measures firm-level profit vs division-level investment — the aggregate/individual split exists as *variables*, never as the masking finding | [F] |

### Why the niche is empty

Searched under: audit integrity, ledger corruption, aggregate-masks-individual,
accountability MAS, agent economies, exploitation benchmarks. Everything found
is either (a) governance/compliance prescription, (b) fraud demonstrations
where the *harm itself* is the headline, or (c) audit-resource game theory. No
work states the dissociation: **the standard system-level output metric is
structurally blind to distributive exploitation** — throughput flat, books
rotten — nor derives "the information market's product is audit integrity, not
output" from it. Note this is *not* Goodhart/reward-hacking (see traps): our
output metric stays honest; the corruption is in the distribution.

**Verdict: SAFE.** Strongest apparent-precedent to pre-empt: TruthMarketTwin
(cite, then differentiate: text agents, reputation governance, no
output/ledger dissociation, no embodied error sources).

---

## Niche 3 — Transferable/negotiable claims in MAS

### Must-cite map

| Work | One-line characterization | Ver. |
|---|---|---|
| Dandekar, Goel, Govindan & Post, EC'11 (arXiv:1007.0515) — "Liquidity in Credit Networks" | agents print currency, trust bounds credit lines, payments route as IOU chains; liquidity ≈ steady-state graph property | [A] |
| Dandekar & Goel et al., ACM TOIT 2015 — "Strategic Formation of Credit Networks" | endogenous credit-line extension by strategic agents | [A] |
| Karlan, Mobius, Rosenblat & Szeidl, QJE 124(3) 2009 — "Trust and Social Collateral" | network trust = max informal borrowing capacity; the economics anchor for claim-transfer along trust chains | [A] |
| Friedman, Halpern & Kash, EC'06 + Kash et al., *Distrib. Comput.* 2012 — scrip systems | artificial currency in P2P agent economies; money-supply tuning, crashes, hoarders, sybils, collusion | [A] |
| Jakobsson, Hubaux & Buttyán, Financial Crypto 2003 — micropayments for multi-hop cellular | per-hop rewards make packet forwarding rational and cheating undesirable; Ben Salem et al. MobiHoc'03 is the sibling | [A] |
| DTN incentive line — Pi (practical incentive protocol for DTNs), credit-based congestion-aware schemes, vehicular-DTN cryptocurrency (Park 2018, *Secur. Commun. Netw.*) | virtual-currency credit accrues to relays on delivery; tariff-like pricing, sometimes bargaining rules on price, cargo = data | [A] |
| SMART layered-coin DTN scheme (Zhu et al., IEEE TVT ~2009) | source mints a "layered coin," each relay endorses a layer and redeems after delivery — structurally the closest thing to a claim propagating along a physical relay chain | [B] — re-verify before citing |
| Malavolta et al., NDSS 2019 — Anonymous Multi-Hop Locks; Lightning HTLC line (Poon & Dryja 2016 [B]) | conditional claims propagated backward along a payment path make multi-hop relay atomic; fee-taking intermediaries; the strongest CS analog of a terminal claim financing hops | [A] |
| Rubinstein & Wolinsky, QJE 1987 — "Middlemen"; Glode & Opp, AER 2016 — "Asymmetric Information and Intermediation Chains" | the economics of why relay/intermediation chains exist at all; Glode-Opp: chains of small informational steps rescue trades that die bilaterally | [A] |
| Bills-of-lading literature | legal/practitioner, not economic theory: document of title, transfer by endorsement, ~$10T/yr under L/Cs (ICC estimate); no canonical "economic theory of the negotiable B/L" paper surfaced — the theory anchor is better taken from Rubinstein-Wolinsky/Glode-Opp + trade-finance law | [A] |

### Why they don't occupy

Credit networks route *payments* over trust edges — the goods never move, and
no chain of custody forms. Scrip prices *service provision*, not title to
cargo in transit. Micropayment/DTN schemes pay relays **fixed or tariffed
per-hop rewards** for carrying *data*; the carrier never owns the cargo, takes
no position risk, and no spot-vs-claims comparison is run. HTLCs are genuinely
negotiable-claim-shaped but live in payment-channel graphs among financial
intermediaries. The economics chain-formation theory (R-W, G-O) has no
computational or embodied instantiation.

**Verdict: OCCUPIED for "transferable claims exist in agent systems" —
position, don't claim. SAFE for the specific finding:** a negotiable claim on
*physical delivery* attached at hand-off, priced by bargaining, causing relay
chains (2.5%→50%) that spot bargaining structurally cannot form.

---

## Niche 4 — Pre-commitment/contracting for multi-hop relay in robotics

### Must-cite map

| Work | One-line characterization | Ver. |
|---|---|---|
| **Srivastava, Levin & Dames 2025, arXiv:2509.14127 (VCST-RCP)** | Voronoi-constrained Steiner-tree relay backbone for multi-robot pickup/delivery; centralized planner, homogeneous cooperative fleet, **zero economics** in handoffs; −31% fleet travel vs Hungarian — proves relay *value*, not relay *markets* | [F] |
| DELIVER 2025, arXiv:2508.19114 | LLM-guided Voronoi relay planning for multi-robot pickup and delivery; same cooperative-planner shape | [A] |
| Kapitonov et al. 2017 (AIRA/Drone Employee protocol) | Ethereum smart contracts for UAV "autonomous business activity" — single-hop service purchase and route permissioning, not chained claims | [A] |
| Blockchain multi-UAV surveillance, *Frontiers Robot. AI* 2021 | token subscriptions pay the system; smart contract plans routes; no inter-robot claim transfer | [A] |
| DTN/VDTN credit schemes (niche 3) | the nearest occupant: physically-moving vehicle nodes paid to mule data multi-hop; but tariffs not bargains, data not owned cargo, no chain-vs-spot experiment | [A]/[B] |
| HTLC multi-hop locks (niche 3) | terminal-conditioned claim finances intermediate hops — in payment networks only | [A] |
| Bucket brigades (Bartholdi & Eisenstein 1996) | order-picking handoff chains — pure work-balancing dynamics, no contracts | [B] |

### Why they don't occupy

Robotics relay work answers "*where/when* to hand off" with a planner that
owns every robot; the question "*why would a self-interested robot accept
cargo mid-route*" never arises, so nothing finances the intermediate hop. The
schemes that do finance hops (DTN credit, HTLCs) have no embodied cargo, no
title transfer, no position risk, and no demonstration that removing the claim
collapses chain formation. We found no robotics work where a claim on the
terminal payout is the instrument that makes intermediate custody rational.

**Verdict: SAFE** (for embodied cargo + negotiable title + bargained hand-off
prices), with the DTN layered-credit line and HTLCs as the two analogs a
reviewer will raise — pre-empt both in related work.

---

## Niche 5 — Moral hazard / Holmström informativeness in computational agents

### Must-cite map

| Work | One-line characterization | Ver. |
|---|---|---|
| Holmström 1979, *Bell J. Econ.* — "Moral Hazard and Observability" | the informativeness principle: pay on signals informative about effort, only those | [A] |
| Chaigneau, Edmans & Gottlieb (NBER w20729; GEB 2018) | generalized informativeness / without first-order approach — the principle is alive theory | [A] |
| **Dütting, Feldman & Talgam-Cohen 2024 — "Algorithmic Contract Theory: A Survey," FnT TCS 16(3-4)** | canonical CS-contract-theory line (Babaioff-Feldman-Nisan-Winter EC'06 → DRT SODA'20 → DEFK FOCS'21/STOC'23); computational, never embodied | [A] |
| Ivanov et al. 2024, arXiv:2407.18074 — "Principal-Agent Reinforcement Learning: Orchestrating AI Agents with Contracts" | contracts steer RL agents in MDPs; nearest computational-reproduction line | [A] |
| Contractual RL, arXiv:2407.01458 — "Pulling Arms with Invisible Hands" | online contract design against learning agents | [A] |
| "Multi-Agent Systems Should be Treated as Principal-Agent Problems," arXiv:2601.23211 (2026) | position paper claiming exactly our framing lens — cite to show the lens is wanted, the experiment is missing | [A] |
| **Mitsch 2023, arXiv:2301.12255 + 2303.14515** | fuzzy Q-learning division managers, specific investments under *negotiated transfer pricing*: myopic agents reproduce classic hold-up underinvestment; **surplus-sharing rules are NOT inert** for investment/profit under asymmetric costs | [F] (abstract) |

### Why they don't occupy — and the Mitsch problem

No one demonstrates the informativeness principle *bidirectionally* in an
embodied task setting (add an uninformative-but-plausible signal term → welfare
destroyed; here: dwell time loads on position risk the carrier doesn't control
→ chains die). The algorithmic-contract line optimizes contracts; it does not
stage a Holmström violation and watch a market structure collapse.

Mitsch is the direct threat to "transfer pricing is exactly inert (Coase)":
his ABM shows pricing rules *matter*. But his setting contains ex-ante
**specific investments** — the hold-up channel is open, so Coase inertness
*should* fail there. Our result is the complementary cell: the split predates
position risk, the hold-up channel is structurally closed, so inertness holds
exactly. Cite Mitsch as the occupied cell of a 2×2 we complete, alongside
Coase 1960 and Hirshleifer 1956 (internal transfer pricing) [B].

**Verdict: SAFE for the embodied informativeness reproduction; CONTESTED at
slogan level for "transfer pricing is inert"** — safe only with the
hold-up-channel framing stated in the same breath.

---

## The single biggest threat to novelty

**Strobel, Pacheco & Dorigo, *Science Robotics* 2023 (eabm4636).** Flagship
venue, physical robots, headline reads as "an economic token mechanism
neutralizes lying robots" — a tired reviewer collapses INTEGRITY into it in
one sentence. The differentiation must be explicit, early, and structural:
(1) their exploit corrupts a *shared estimate*; ours drains *individual
ledgers* while the estimate/throughput stays green — their headline metric
would score our attacked fleet as healthy; (2) their tokens are a
participation stake minted by the defense itself; our attestation gates entry
to a *bargaining market* whose prices carry the exploitation; (3) they defend
against one adversary class; we show four independent error sources
(only one of them strategic) produce the same books-rot signature and fall to
the same gate — which is what licenses "the product is audit integrity."
Runner-up threat: Mitsch 2023 vs the Coase-inertness slogan (handled by the
2×2 above).

## Terminology traps

- **"Byzantine" ≠ "strategic":** BFT covers arbitrary faults and is solved by
  exclusion; a rational exploiter inside a market is best answered by
  incentives/gating. The blockchain-robotics line blurs this — don't inherit
  the blur.
- **"Token economy" (Science Robotics 2023)** is a permissioning stake, not a
  goods-and-services economy; no trades, no prices, no ledger of gains.
- **"Negotiable" vs "negotiated":** law-side negotiability = transfer by
  endorsement + holder protections; our bills are both negotiable (endorsed at
  hand-off) and negotiated (priced by bargaining). The B/L literature itself
  confuses negotiable/transferable — define once, early.
- **Not Goodhart / reward hacking:** in Goodhart the proxy improves while the
  true objective decays; in INTEGRITY the output metric remains *honest about
  output* — output truly doesn't fall. The dissociation is
  aggregate-vs-distributive, not proxy-vs-true.
- **"Audit games"** = inspection-resource allocation (Blocki et al.), not
  ledger integrity.
- **"Relay," "bucket brigade," "handoff"** in robotics = planned cooperative
  transfers with zero economics; "relay" in wireless = data forwarding.
  Neither implies contracts.
- **"Credit network"** (Dandekar-Goel sense) routes payments over trust edges —
  no cargo, no custody chain.
- **"Hold-up"** in wireless literature can mean delay/jamming, not
  Williamsonian appropriation of quasi-rents.
- **"Informativeness"** in RL usually means information gain, not Holmström's
  sufficient-statistic criterion.

## What remains unclaimed

1. The dissociation finding: four independent error sources leave fleet
   throughput flat while individual ledgers silently accumulate losses — and
   any output-side dashboard is structurally blind to it.
2. Attestation-gating as the single treatment that zeroes all four exploitation
   channels in a robot bargaining market; "the information market's product is
   audit integrity, not output."
3. A negotiable claim on physical delivery, endorsed at hand-off and priced by
   bargaining, as the instrument that makes multi-hop relay chains form
   (2.5%→50%) where spot bargaining structurally cannot.
4. Exact Coase inertness of internal transfer prices in an embodied setting
   where the split predates position risk (complementing Mitsch's open-channel
   non-inertness).
5. A simulated, embodied, bidirectional reproduction of the informativeness
   principle: a plausible dwell-based incentive term loading on
   uncontrolled risk destroys the chains.

## Caveats (honest limits of the sweep)

- Absence-of-evidence structure as always; likeliest hidden occupants:
  (a) a 2025-26 LLM-agent-economy paper reporting a flat-aggregate /
  individual-loss table as a side observation without naming it;
  (b) DTN/VDTN incentive papers under vocabulary we didn't try
  ("coupon," "voucher," "endorsement chain").
- Most sources verified at abstract/search level ([A]); full-text reads only
  for Kattepur & Khemkha; landing-page/abstract fetches for VCST-RCP, Mitsch,
  TruthMarketTwin, and the Science Robotics paper (via its Dryad dataset
  description — the paper itself is paywalled, 403 on fetch).
- [B]-marked items (SMART layered coins, Poon-Dryja, Bartholdi-Eisenstein,
  Hirshleifer 1956) are background knowledge — verify before they enter the
  manuscript's reference list.
- Supply-chain-finance economics (factoring theory, documentary credit) was
  only shallowly swept; a dedicated pass is warranted if BILLS leans harder on
  the trade-finance analogy than on Rubinstein-Wolinsky/Glode-Opp.
- Verdicts current to 2026-07; the LLM-agent-market literature is moving
  monthly — re-sweep niche 2 immediately before submission.

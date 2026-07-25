# PAPER-DRAFT.md — Bibliographic verification report

*Verification pass 2026-07-23 for AAMAS submission. Do NOT edit PAPER-DRAFT.md from
this file (another agent owns the paper); this is the source of truth for the
References section. Tools used: WebSearch, WebFetch (publisher pages, arXiv, DBLP,
Crossref REST API, open mirrors). Every field below is tagged with how it was
obtained. Nothing is invented; unfindable fields are marked UNFINDABLE with what
was tried.*

Legend:
- ✓ **VERIFIED (session)** — confirmed this session against Crossref/DBLP/arXiv/publisher.
- ○ **REPRODUCED** — pre-existing complete entry (no `[TODO-VERIFY]`); standard,
  widely-cited details supplied but NOT independently re-verified this session.
  Spot-check before camera-ready if desired.
- ⚑ **FLAG** — a discrepancy between the draft and the verified record; editor decision needed.

---

## 1. Complete ACM-format reference list (numbered to match the paper)

**[1]** ○ John F. Nash. 1950. The Bargaining Problem. *Econometrica* 18, 2 (April 1950), 155–162.
https://doi.org/10.2307/1907266

**[2]** ○ Brian P. Gerkey and Maja J. Matarić. 2002. Sold!: Auction Methods for Multirobot
Coordination. *IEEE Transactions on Robotics and Automation* 18, 5 (Oct. 2002), 758–768.
https://doi.org/10.1109/TRA.2002.803462

**[3]** ○ Brian P. Gerkey and Maja J. Matarić. 2004. A Formal Analysis and Taxonomy of Task
Allocation in Multi-Robot Systems. *International Journal of Robotics Research* 23, 9
(Sept. 2004), 939–954. https://doi.org/10.1177/0278364904045564

**[4]** ○ M. Bernardine Dias, Robert Zlot, Nidhi Kalra, and Anthony Stentz. 2006. Market-Based
Multirobot Coordination: A Survey and Analysis. *Proceedings of the IEEE* 94, 7 (July 2006),
1257–1270. https://doi.org/10.1109/JPROC.2006.876939

**[5]** ○ Robert Michael Zlot. 2006. *An Auction-Based Approach to Complex Task Allocation for
Multirobot Teams.* Ph.D. Dissertation. Carnegie Mellon University, Pittsburgh, PA.

**[6]** ○ Lin Lin and Zhiqiang Zheng. 2005. Combinatorial Bids Based Multi-Robot Task Allocation
Method. In *Proceedings of the 2005 IEEE International Conference on Robotics and Automation
(ICRA 2005)*. IEEE, 1145–1150. https://doi.org/10.1109/ROBOT.2005.1570270
  - ⚑ Page range and DOI REPRODUCED, not re-verified this session — confirm before camera-ready.

**[7]** ✓ **VERIFIED (session)** Rongxin Cui, Ji Guo, and Bo Gao. 2013. Game Theory-Based
Negotiation for Multiple Robots Task Allocation. *Robotica* 31, 6 (Sept. 2013), 923–934.
https://doi.org/10.1017/S0263574713000192
  - Authors, vol 31(6), pp. 923–934, 2013, DOI all confirmed via Crossref. Draft's `31(6), 2013` correct.

**[8]** ✓ **VERIFIED (session)** Wende Ke, Zhiping Peng, Quande Yuan, Bingrong Hong, Ke Chen,
and Zesu Cai. 2012. A Method of Task Allocation and Automated Negotiation for Multi Robots.
*Journal of Electronics (China)* 29, 6 (Nov. 2012), 541–549.
https://doi.org/10.1007/s11767-012-0868-x
  - Full 6-author list, vol 29(6), pp. 541–549 confirmed via Crossref. (Search engines truncated
    this to "Ke et al." — the complete list is now filled.)

**[9]** ✓ **VERIFIED (session)** Ali Hamidoğlu, Omer Melih Gul, Seifedine Nimer Kadry,
Chiranjibe Jana, Ali Elghirani, and Gokhan Koray Gultekin. 2025. A Cost-Effective Nash-Based
Allocation Method for Task Distribution of Multiple Robots in Distributed Robotic Networks.
*Engineering Applications of Artificial Intelligence* 162 (Dec. 2025), Article 112548.
https://doi.org/10.1016/j.engappai.2025.112548
  - Title, 6-author list, vol 162, article 112548, DOI confirmed via Crossref. This is the
    "EAAI Dec. 2025 Nash-based MRTA" paper. (See Task 2(c): it is Nash **equilibrium**, not
    Nash **bargaining** — squarely on the side the draft's claim needs.)

**[10]** ✓ **VERIFIED (session), ⚑ AMBIGUITY — editor must choose.** Recommended primary form:
Henrik Schiøler and Trung Dung Ngo. 2008. Trophallaxis in Robotic Swarms — Beyond Energy
Autonomy. In *Proceedings of the 2008 10th International Conference on Control, Automation,
Robotics and Vision (ICARCV 2008)*. IEEE, 1526–1533. https://doi.org/10.1109/ICARCV.2008.4795751
  - This is the ICARCV 2008 paper that presents the **CISSBot** as a battery-swapping design
    study / proof of concept — the best content-match for the draft's "CISSBots demonstrate
    physical battery swapping."
  - ⚑ **Author order:** Crossref/IEEE list **Schiøler then Ngo** for this paper; the draft has
    "T. D. Ngo and H. Schiøler." Fix the draft's order, or cite the companion paper below.
  - ⚑ **"randomized trophallaxis" provenance:** that exact phrase is NOT in this ICARCV paper's
    title; it is the title of **Trung Dung Ngo and Henrik Schiøler. 2007. Randomized Robot
    Trophallaxis: From Concept to Implementation. In *2007 IEEE Int. Conf. on Systems, Man and
    Cybernetics (SMC 2007)*. IEEE, 208–213. https://doi.org/10.1109/ICSMC.2007.4414153**
    (also a 2008 book chapter, https://doi.org/10.5772/5484). If the draft's prose leans on the
    words "randomized trophallaxis," cite the 2007 SMC paper alongside, or as [10].
  - Third option (Ngo-first author order, ICARCV 2008): **Trung Dung Ngo and Henrik Schiøler.
    2008. Rendezvous Trajectory Generation for Energy Trophallaxis. In *ICARCV 2008*. IEEE,
    2114–2119. https://doi.org/10.1109/ICARCV.2008.4795857** — this matches the draft's author
    order but is about rendezvous control, not the CISSBot battery-swap demo. Recommendation:
    use the top entry for the CISSBot claim and (optionally) the 2007 SMC paper for the
    "randomized trophallaxis" phrase.

**[11]** ✓ **VERIFIED (session)** Choladawan Moonjaita, Hemma Philamore, and Fumitoshi Matsuno.
2018. Trophallaxis with Predetermined Energy Threshold for Enhanced Performance in Swarms of
Scavenger Robots. *Artificial Life and Robotics* 23, 4 (Dec. 2018), 609–617.
https://doi.org/10.1007/s10015-018-0497-z
  - Exact title, vol 23(4), pp. 609–617 confirmed via Crossref.

**[12]** ✓ **VERIFIED (session)** Thomas Schmickl and Karl Crailsheim. 2008. Trophallaxis within
a Robotic Swarm: Bio-Inspired Communication among Robots in a Swarm. *Autonomous Robots* 25,
1–2 (Aug. 2008), 171–188. https://doi.org/10.1007/s10514-007-9073-4
  - Venue/year/pages confirmed via Crossref. (Published online Dec 2007; print Aug 2008.)
  - Note: if the draft specifically means the "virtual/hormone-gradient" earlier statement, the
    companion is T. Schmickl and K. Crailsheim, "Trophallaxis among Swarm-Robots: A Biologically
    Inspired Strategy for Swarm Robotics," *BioRob 2006*, IEEE, 377–382. The Autonomous Robots
    2008 journal paper above is the fuller, more citable treatment and is the recommended entry.

**[13]** ✓ **VERIFIED (session)** Tim Baarslag, Reyhan Aydoğan, Koen V. Hindriks, Katsuhide
Fujita, Takayuki Ito, and Catholijn M. Jonker. 2015. The Automated Negotiating Agents
Competition, 2010–2015. *AI Magazine* 36, 4 (Dec. 2015), 115–118.
https://doi.org/10.1609/aimag.v36i4.2609
  - Authors (Baarslag et al., NOT "ANAC organizers"), venue AI Magazine 36(4), year 2015 confirmed.

**[14]** ✓ **VERIFIED (session)** Reyhan Aydoğan, Tim Baarslag, Tamara C. P. Florijn, Katsuhide
Fujita, Catholijn M. Jonker, and Yasser Mohammad. 2026. The Automated Negotiating Agents
Competition (ANAC) 2025 Challenges and Results. arXiv:2604.13914.
  - Title + 6-author list confirmed via arXiv. Reports the 15th ANAC, an official IJCAI 2025
    competition; submitted April 2026. arXiv ID matches the draft.

**[15]** ✓ **VERIFIED (session), ⚑ YEAR.** Reyhan Aydoğan, Mehmet Onur Keskin, and Umut Çakan.
2022. Would You Imagine Yourself Negotiating with a Robot, Jennifer? Why Not? *IEEE
Transactions on Human-Machine Systems* 52, 1 (Feb. 2022), 41–51.
https://doi.org/10.1109/THMS.2021.3121664
  - Exact title + 3-author list + vol 52(1), pp. 41–51 confirmed via DBLP/IEEE.
  - ⚑ Draft says "2021." Formal publication is **2022** (vol 52, no. 1); "2021" is the
    early-access / DOI year. Use 2022, or "2021 (early access)". This is the Nao/Pepper-vs-human
    dyadic human-robot negotiation study the draft describes.

**[16]** ✓ **VERIFIED (session)** Toby Godfrey, William Hunt, and Mohammad Divband Soorati. 2024.
MARLIN: Multi-Agent Reinforcement Learning Guided by Language-Based Inter-Robot Negotiation.
arXiv:2410.14383.
  - Title + 3-author list confirmed via arXiv/DBLP.

**[17]** ✓ **VERIFIED (session)** Huaben Chen, Wenkang Ji, Lufeng Xu, and Shiyu Zhao. 2023.
Multi-Agent Consensus Seeking via Large Language Models. arXiv:2310.20151.
  - Title + 4-author list confirmed via arXiv. (Submitted Oct 2023.)

**[18]** ✓ **VERIFIED (session)** Xianyang Liu, Shangding Gu, and Dawn Song. 2026. AgenticPay:
A Multi-Agent LLM Negotiation System for Buyer-Seller Transactions. arXiv:2602.06008.
  - Title + 3-author list confirmed via arXiv. Buyer–seller multi-round linguistic negotiation
    (price/valuation), consistent with the draft's "price-only" characterization.

**[19]** ✓ **VERIFIED (session), ⚑ minor.** Siqi Song, Xuanbing Xie, Zonglin Li, Yuqiang Li,
Shijie Wang, and Biqing Qi. 2026. Leveraging Adaptive Group Negotiation for Heterogeneous
Multi-Robot Collaboration with Large Language Models. arXiv:2602.06967.
  - This is CLiMRS (the framework name in the abstract). Title + 6-author list confirmed via arXiv.
  - ⚑ arXiv ID prefix `2602` = Feb 2026; the abstract page also states a Dec-2025 submission
    date. Use year 2026 (matches the ID) unless the paper's own front matter says 2025.

**[20]** ✓ **VERIFIED (session)** Zhaohan Feng, Ruiqi Xue, Lei Yuan, Yang Yu, Ning Ding, Meiqin
Liu, Bingzhao Gao, Jian Sun, Xinhu Zheng, and Gang Wang. 2025. Multi-Agent Embodied AI:
Advances and Future Directions. arXiv:2505.05108.
  - Title + 10-author list confirmed via arXiv.

**[21]** ✓ **VERIFIED (session), ⚑ DATE + article number.** Athira K. A., Divya Udayan J., and
Umashankar Subramaniam. 2024. A Systematic Literature Review on Multi-Robot Task Allocation.
*ACM Computing Surveys* 57, 3 (2025), 28 pages. https://doi.org/10.1145/3700591
  - Title + 3-author list + vol 57(3) + DOI confirmed via Crossref/ACM.
  - ⚑ Draft says "Oct. 2024." Crossref shows **online 11 Nov 2024; print issue March 2025**.
    Use "(2025)" or "(Nov. 2024)".
  - ⚑ **UNFINDABLE:** the ACM article number. Crossref returns page range "1–28" but no article
    number; the ACM DL landing page is 403 to automated fetch. Cite as "28 pages" (ACM style
    accepts this) or retrieve the article number from an authenticated ACM DL session.

**[22]** ○ Erol Şahin. 2005. Swarm Robotics: From Sources of Inspiration to Domains of
Application. In *Swarm Robotics* (Lecture Notes in Computer Science, Vol. 3342). Springer,
10–20. https://doi.org/10.1007/978-3-540-30552-1_2
  - Draft's LNCS 3342 / pp. 10–20 / 2005 match the standard record (REPRODUCED).

**[23]** ○ Manuele Brambilla, Eliseo Ferrante, Mauro Birattari, and Marco Dorigo. 2013. Swarm
Robotics: A Review from the Swarm Engineering Perspective. *Swarm Intelligence* 7, 1 (March
2013), 1–41. https://doi.org/10.1007/s11721-012-0075-2

**[24]** ○ Heiko Hamann. 2018. *Swarm Robotics: A Formal Approach.* Springer, Cham.
https://doi.org/10.1007/978-3-319-74528-2

**[25]** ○ Nick Jakobi, Phil Husbands, and Inman Harvey. 1995. Noise and the Reality Gap: The
Use of Simulation in Evolutionary Robotics. In *Advances in Artificial Life (ECAL 1995)*
(Lecture Notes in Computer Science, Vol. 929). Springer, 704–720.
https://doi.org/10.1007/3-540-59496-5_337 —
and Nick Jakobi. 1997. Evolutionary Robotics and the Radical Envelope-of-Noise Hypothesis.
*Adaptive Behavior* 6, 2 (1997), 325–368. https://doi.org/10.1177/105971239700600205
  - Both are the standard records for the draft's combined "[25]"; REPRODUCED, not re-verified.

**[26]** ○ Tuomas Sandholm. 1998. Contract Types for Satisficing Task Allocation: I.
Theoretical Results. In *Proceedings of the AAAI Spring Symposium: Satisficing Models*. AAAI
Press, 68–75.
  - Page range REPRODUCED; venue/year match the draft.

**[27]** ✓ **VERIFIED (session)** Martin R. Andersson and Tuomas W. Sandholm. 1999. Sequencing
of Contract Types for Anytime Task Reallocation. In *Agent Mediated Electronic Commerce*
(Lecture Notes in Computer Science, Vol. 1571). Springer, 54–69.
https://doi.org/10.1007/3-540-48835-9_4
  - LNCS **Vol. 1571**, year **1999**, pp. **54–69** confirmed (volume via search; pages + authors
    + container via Crossref). This fills the draft's `[TODO-VERIFY: volume, year]`.
    (Series is LNCS/LNAI 1571; some indexes label it LNAI.)

**[28]** ○ Yann Chevaleyre, Paul E. Dunne, Ulle Endriss, Jérôme Lang, Michel Lemaître, Nicolas
Maudet, Julian Padget, Steve Phelps, Juan A. Rodríguez-Aguilar, and Paulo Sousa. 2006. Issues
in Multiagent Resource Allocation. *Informatica* 30, 1 (2006), 3–31.
  - Draft's "Chevaleyre et al." expanded to the standard 10-author list; vol 30, pp. 3–31, 2006
    match the draft (REPRODUCED, author list not re-verified this session).

**[29]** ○ Ulle Endriss, Nicolas Maudet, Fariba Sadri, and Francesca Toni. 2006. Negotiating
Socially Optimal Allocations of Resources. *Journal of Artificial Intelligence Research* 25
(2006), 315–348. https://doi.org/10.1613/jair.1870
  - Matches the draft.

**[30]** ✓ **VERIFIED (session)** Sven Koenig, Craig Tovey, Michail Lagoudakis, Evangelos
Markakis, David Kempe, Pinar Keskinocak, Anton Kleywegt, Adam Meyerson, and Sonal Jain. 2006.
The Power of Sequential Single-Item Auctions for Agent Coordination. In *Proceedings of the
21st National Conference on Artificial Intelligence (AAAI 2006)*. AAAI Press, 1625–1629.
  - Full **9-author** list and pages **1625–1629** confirmed via DBLP (record KoenigTLMKKKMJ06).
    The draft's "S. Koenig, C. Tovey, M. Lagoudakis, et al." and pp. 1625–1629 are correct;
    full list now supplied.

**[31]** ✓ **VERIFIED (session)** Elias Koutsoupias and Christos Papadimitriou. 1999.
Worst-Case Equilibria. In *STACS 99* (Lecture Notes in Computer Science, Vol. 1563). Springer,
404–413. https://doi.org/10.1007/3-540-49116-3_38
  - Pages **404–413**, LNCS 1563, STACS 1999 confirmed. Fills the draft's missing pages.

---

## 2. Task 2 — full-text safety check on the four abstract-level sources

The absence claim ("no multi-issue bargaining between robots") leans on these four.
**Bottom line: all four are UNVERIFIED at full-text level** — every publisher host
(Cambridge Core, SpringerLink, ScienceDirect, ACM DL) is paywalled and returned 403 /
auth-redirect to automated fetch, and ResearchGate PDFs 403'd. However, for each I
obtained abstract-level evidence (and for the CSUR review, abstract **+ reference-list**
level via an open mirror), and **none contradicts** the draft's characterization. No
source was found to be SAFE (full-text confirmed) and none is a PROBLEM.

### (a) Cui, Guo & Gao, *Robotica* 31(6), 2013 — VERDICT: **UNVERIFIED** (no contradiction; abstract supports)
- **Checked:** Cambridge Core article page (constructed URL 404 to fetch), ResearchGate
  publication page (403 full text; abstract via search snippet), Google Scholar (no free
  PDF listed), Crossref metadata (authors/vol/issue/pages/DOI ✓).
- **What the abstract says:** initial allocation by contract-net; then "a game theory-based
  negotiation strategy is proposed to achieve the **Pareto-optimal solution for the task
  reallocation**," and "the task allocation solutions after negotiation are better than the
  initial contract net-based allocation." The negotiated object is **which robot does which
  task** (a single reallocation dimension, utility-scored). No occurrence of multi-issue,
  multi-attribute, bundle, logrolling, or energy exchange in any accessible text.
- **Read:** consistent with the draft's "single-issue" framing. Full text not seen, so cannot
  be upgraded to SAFE.

### (b) Ke et al., *J. Electronics (China)* 29(6), 2012 — VERDICT: **UNVERIFIED** (no contradiction; abstract supports)
- **Checked:** SpringerLink article page (303 redirect to `idp.springer.com` auth — paywalled),
  Semantic Scholar (no body text served), Crossref metadata (full author list ✓), abstract via
  search snippets.
- **What the abstract says:** LSSVR is "improved to estimate the **opponent's negotiation
  utility**" and an H∞ output-feedback controller "optimize[s] the **utility performance
  indicators**," with "a protocol of negotiation and reallocation." Negotiation is over a
  single scalar utility dimension for task (re)allocation. No multi-issue/bundle/logrolling/
  energy-trade language anywhere accessible.
- **Read:** consistent with the draft. Full text not seen.

### (c) EAAI Dec. 2025 Nash-MRTA — Hamidoğlu et al. — VERDICT: **UNVERIFIED** (no contradiction; abstract *strongly* supports)
- **Checked:** ScienceDirect article page (403 / paywall), Elsevier Pure mirror (404),
  Crossref metadata (authors/vol/article/DOI ✓), an extended abstract via search snippets.
- **What the abstract says:** "each robot **selects a single task** that optimizes its execution
  time at a constant speed, thereby maximizing energy harvesting and minimizing energy
  consumption... achieving the **Nash equilibrium** as a nearly optimal allocation strategy,"
  and it "outperforms the **Hungarian method**... complexity to O(N)." This is a non-cooperative
  **single-task-selection game solved at Nash equilibrium**; energy is **harvested individually**,
  not traded between robots; there are no offers, deals, or bundles.
- **Read:** This is exactly the "Nash *equilibrium* (as opposed to Nash *bargaining solution*)"
  distinction the draft draws in §Intro and [1]-vs-[9]. The source belongs on the equilibrium
  side and does **not** occupy the multi-issue-bargaining niche. Full text not seen, so UNVERIFIED,
  but the abstract alone carries the load-bearing distinction cleanly.

### (d) CSUR 2024 MRTA systematic review — Athira K. A. et al. — VERDICT: **UNVERIFIED** (no contradiction; abstract + reference-list support)
- **Checked:** ACM DL landing page (403), ResearchGate full-text PDF (403), **open mirror
  ouci.dntb.gov.ua (abstract + overview + reference list accessible)**, Crossref metadata (✓).
- **What was readable:** the abstract, overview, and the reference list. **Zero** occurrences of
  "negotiation," "multi-issue," "multi-attribute," "bargaining," "logrolling," or "bundle" in the
  abstract or the reference-list excerpt. The only market-flavoured item in the references is Liu
  & Shell 2013 ("Optimal market-based multi-robot task allocation via strategic pricing" —
  single-issue price). The taxonomy as described covers auction/consensus/optimization/learning
  methods, not bargaining.
- **Independent corroboration:** a separate, **open-access** 2026 survey directly in this
  intersection — "A Survey of Hybrid Energy-Aware and Decentralized Game-Theoretic Approaches in
  Intelligent Multi-Robot Task Allocation" (*Computers, Materials & Continua*, techscience.com) —
  was fully readable and likewise contains **no** multi-issue / multi-attribute / logrolling /
  Nash-bargaining-solution content; its single "bargaining" mention is cooperative-game
  Shapley/coalition **value division**, not multi-issue offer/counteroffer.
- **Read:** consistent with the draft's survey-level absence claim. The prior sweep already
  flagged this as MEDIUM confidence (full text paywalled); that limitation is unchanged. A
  companion claim about the CSUR reference list was refuted in the earlier sweep and is not
  relied on here.

**Recommendation for print:** the draft already hedges these four as "verified at abstract level
only [†]"; keep that hedge. The strongest of the four for the absence claim is (c), because the
equilibrium-vs-bargaining distinction is explicit in its own abstract. If a reviewer presses on
full-text access, the honest disclosure is: publisher paywalls prevented full-text inspection;
abstracts (+ CSUR reference list) and one open-access corroborating 2026 survey show no
contradicting content.

---

## 3. Task 3 — sanity check for NEW occupants (2025–2026 sweep)

Five searches beyond the original sweep. **No new occupant threatens the absence claim.**

1. **"multi-issue negotiation between robots / bundled deal 2025–2026"** — returns contract-net
   variants, consensus-**bundle** algorithms (CBBA-style: bundle = a set of *tasks* cleared at a
   scalar, the same terminology trap the draft names), and warehouse composite-robot scheduling.
   None bundle ≥2 *coupled negotiable dimensions* traded off against each other.
2. **"logrolling robots / multi-robot bargaining energy-for-task 2026"** — energy-aware MRTA
   (auction/scheduling/recharge routing). The one hit that says "bargaining" is the CMC 2026
   survey above, meaning cooperative-game Shapley/coalition value division — not multi-issue
   bilateral bargaining. "Logrolling" returns nothing in a robotics context.
3. **"multi-attribute negotiation / barter / resource-exchange protocol, energy-for-cargo"** —
   generic multi-attribute negotiation frameworks (disembodied economic agents), TraderBots
   (single scalar price), FIPA messaging. No embodied multi-issue instantiation.
4. **"Nash bargaining robots energy trading bilateral 2026"** — a genuinely *growing* 2026
   literature, but it is **energy-market / power-systems**, not robot coordination: V2V EV energy
   trading (e.g. arXiv:2605.22363, "Incentive-Aligned V2V Energy Trading via Nash-Integrated
   MARL"), peer-to-peer building electricity markets, electricity–hydrogen multi-agent systems.
   All are **single-issue** (price/quantity of energy) in economic markets; none couples
   energy + task + movement-rights into one physical-coordination deal between robots. **Adjacent
   near-miss, non-threatening** — flagged in the nulls so the draft can pre-empt the reviewer who
   knows this line.
5. **RoCo / CoELA LLM multi-robot dialogue** (the prior sweep's flagged "most plausible hidden
   occupant") — RoCo (ICRA 2024) and CoELA are LLM dialogue for **task strategy + motion planning**
   (sub-task plans, waypoints, joint navigation). They do not strike a single agreement bundling
   ≥2 coupled negotiable issues. They remain the **closest structural neighbour** (free-form chat
   could in principle hide implicit trades) but show no explicit multi-issue bargaining. Unchanged
   from the prior caveat; not exhaustively excludable.

**Net:** the mid-2026 niche is still OPEN; the new 2026 CMC energy-aware/game-theoretic MRTA
survey actually **strengthens** the survey-level absence claim (fresh, open-access, in the exact
intersection, and empty of the target primitive).

---

## 4. Honest nulls / limitations

- **Full text of the four Task-2 sources was NOT obtained** (all four publishers paywalled;
  ResearchGate 403). Verdicts rest on abstracts (+ CSUR reference list + one corroborating open
  survey). This is the same limitation the draft already discloses with the † marker; this pass
  did not remove it. To upgrade any to SAFE, use institutional/authenticated access to Cambridge
  Core [7], SpringerLink [8], ScienceDirect [9], or ACM DL [21].
- **[10] Ngo/Schiøler is genuinely ambiguous** (author order + which of three trophallaxis papers
  + provenance of the phrase "randomized trophallaxis"). Resolved into three concrete options
  above; editor must pick. Recommended: "Trophallaxis in Robotic Swarms — Beyond Energy Autonomy"
  (ICARCV 2008, pp. 1526–1533) for the CISSBot claim, optionally + the 2007 SMC "Randomized Robot
  Trophallaxis" paper for the phrase.
- **[15] year** is 2022 (final), not 2021 (early access) — draft edit needed or use "(early access
  2021)".
- **[21] date** is Nov 2024 online / March 2025 print, not "Oct. 2024"; and its **ACM article
  number is UNFINDABLE** without authenticated ACM DL access (Crossref exposes only "1–28").
- **[19] CLiMRS year** — arXiv ID prefix says Feb 2026; an abstract page also cites a Dec-2025
  submission. Use 2026 to match the ID unless the PDF front matter says otherwise.
- **[6] Lin & Zheng** page range/DOI and **[26] Sandholm** page range are REPRODUCED from standard
  records, not re-verified this session (they carried no `[TODO-VERIFY]`). Low risk; spot-check if
  desired.
- **Classic entries [1]–[5], [22]–[26], [28]–[29]** were not independently re-verified this session
  (no `[TODO-VERIFY]` markers); standard widely-cited details are supplied and marked ○ REPRODUCED.
- **Absence-of-evidence structure is inherent:** an occupant could exist in an unindexed venue,
  non-English literature (esp. Chinese-language MRTA journals, given [7]/[8]), or under vocabulary
  the sweep did not query ("multi-attribute contracting," "resource exchange protocol," "barter").
  The V2V/P2P Nash-bargaining energy-market line and the RoCo/CoELA free-form-dialogue line are the
  two nearest adjacencies and are named here so the draft can address them directly rather than be
  surprised by them in review.

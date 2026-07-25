# PAPER-DRAFT.md — simulated senior-faculty review (2026-07-23)

*Persona: a simulated composite senior professor in multi-agent systems at an
MIT-CSAIL-type group; 25 years in market-based coordination and automated
negotiation; AAMAS SPC regular. Not a real person; treat as a hostile-but-fair
referee. Verdict format mirrors a conference meta-review.*

## Overall verdict: MAJOR REVISION — publishable core, currently unsubmittable

The benchmark is real, the registration discipline is genuinely unusual and
publishable *as method*, and C1 is a clean structural result I would cite.
But the manuscript as drafted would be rejected at AAMAS on three grounds
before a reviewer reaches the results: a missing engagement with the closest
prior art (Sandholm's contract types), a baseline that cannot support the
"beats the market lineage" language, and a terminology collision with the
price-of-anarchy literature. All are fixable. The deeper structural problem
is that this is two papers wearing one coat.

## Blocking issues (fix before any submission)

**B1 — Sandholm's OCSM contracts are the closest prior art and are absent.**
The related-work section is built on an absence claim ("no bundled multi-issue
agreements between robots"), yet does not engage Sandholm's contract-type
hierarchy (O-, C-, S-, M-contracts; TRACONET lineage), in which self-interested
agents trade *bundles* (cluster contracts), *swaps*, and *multi-agent*
contracts precisely to escape local minima that single-task O-contracts cannot
— IR included, payments included. Chevaleyre et al.'s multiagent resource
allocation survey and Endriss's negotiation-over-bundles line are the same
gap. Your absence claim survives only in its narrow form: *embodied*
instantiation with *physically heterogeneous issue types* (lossy energy
transfer vs cargo vs claim rights) under *executed physics*. That is still a
real gap — but the paper must cite this literature, differentiate on
embodiment and issue-type heterogeneity, and drop any wording implying
multi-issue IR contracting among self-interested agents is itself new. As
drafted, any reviewer from the negotiation community rejects on this alone.

**B2 — The auction rung cannot carry the claim language.** "Dominates the
single-issue market lineage" is asserted against a bilateral, single-bidder,
MURDOCH-style handoff. The market-based MRTA community's standard is
sequential single-item auctions with broadcast and multi-bidder competition
(Koenig et al.), and combinatorial variants. Either (a) implement an SSI-style
broadcast auction rung — the honest strengthening; or (b) rewrite every claim
to name the baseline: "a MURDOCH-style bilateral handoff auction." Limitations
§6 already concedes this; the results and abstract text do not. Reviewers
reject papers whose claims outrun their own limitations section.

**B3 — "Price of selfishness" collides with Price of Anarchy.** PoA
(Koutsoupias–Papadimitriou) is worst-case equilibrium vs optimum. Your
quantity is (greedy joint-Φ heuristic) − (one specific IR mechanism): neither
an equilibrium notion nor an optimum bound — the ceiling itself is admitted
non-optimal (§6). A game theorist will make this the review's second
paragraph. Rename ("coordination gap" or "cooperation gap") and add one
paragraph relating and differentiating from PoA / price-of-fairness. Keep the
empirical content; lose the claim to a named theoretical quantity.

**B4 — Full-information bargaining will be read as "not negotiation."** With
known utilities, the NBS is a computation, not a protocol; ANAC-adjacent
reviewers will say the hard part of negotiation was assumed away. You have a
good answer — the v5–v7 results show the mechanism's value under estimation
error and lies is *deal-integrity*, not cleverness (true-loss veto turns error
into failed proposals; attestation zeroes the liar advantage) — but it arrives
in §4.5, too late. Move a two-sentence version into the introduction: the
contribution is mechanism comparison under ownership boundaries, with
information quality as a treated variable, not protocol design.

**B5 — One paper, one claim: split the program.** Paper 1 (AAMAS): the
benchmark + registration/correction method + C1/C2/C3 with the strengthened
baseline and renamed gap. Paper 2 (AAMAS or JAAMAS, arguably the more novel
contribution): the integrity results — deception tolerance, attestation
gating, gauge poisoning, "green dashboard, robbed books," and the column-K
information-market finding (audit integrity, not output). The settlement-
infrastructure discussion belongs in Paper 2 only, one paragraph, clearly
flagged as motivation. As one paper it is a program report, and program
reports get "interesting but unfocused" rejections.

## Major (non-blocking) issues

**M1 — Statistical fragility at the headlines.** p=.041, p=.04, p=.03 at 16
seeds carry headline claims (hive comparison, map-market books effect, J
inversion). You state re-pins are free: re-run the headline columns at 64
seeds before submission. If an effect dies at 64 seeds it was not a result.
Report effect sizes with CIs throughout; the wins/n practice is good, keep it.

**M2 — Single geometry.** C1 is structural and safe. C2/C3 and the v8 hump
are one-map findings; replicate the headline orderings on a second layout
(different source/sink topology) or scope explicitly to "this geometry."

**M3 — The correction narrative is over-long.** §3.4 is the right content at
twice the right length. Compress to ~half; move the pad-strand/DEAL_PAUSE
detail to an appendix. It is evidence of rigor, not a second contribution.

**M4 — Absence-claim hygiene.** Full-text-check the four †-sources before
print; the draft already flags this. Add "multi-attribute contracting,"
"OCSM," and "resource allocation by negotiation" to the searched-vocabulary
list, given B1.

**M5 — Engine-reuse disclosure.** Reusing production bargaining primitives is
fine and even a strength (deployed-code validity); disclose in §7 plainly.

## Minor

Abstract: 190 words but dense to opacity — rewrite for one idea per sentence.
Title: option 1 ("Bundling or Silence") is the best of the three if C1 leads;
drop "price of selfishness" from any title per B3. Fig plan in submission
notes is right; add a schematic of one executed bundle (energy+cargo+claim)
— reviewers anchor on it. References: several placeholders would embarrass at
submission; the draft's own TODO list covers this.

## What I would *not* change

The registered-kill reporting style (§4.4) is the paper's signature — keep
every fired kill in the main text. The scoped law framings ("safety-netted
market beats planning when survival binds") are good science writing. The
Şahin-criteria positioning honestly forecloses the cheap "call it swarm"
temptation and buys credibility with exactly the reviewers who matter.

## Path to acceptance (my estimate)

Fix B1–B4, split per B5, harden per M1–M2: Paper 1 is a credible AAMAS full
paper (60–70% at AAMAS given the pre-registration novelty; higher at JAAMAS
with the full program). Paper 2 is the sleeper — integrity-under-error for
mixed-ownership fleets has no incumbent literature and your data is already
sufficient. arXiv both the day the numbers re-pin; the timestamp matters more
than the venue for the absence claim.

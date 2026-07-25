# The Works offered her a 12% raise and she left anyway

*I built a shipyard full of space crabs to find out what six weeks of salary meetings actually cost. The answer was not the meetings.*

---

Ada Kelpline is a brine-chemist. She makes $134,702 a year, she's been on the station a year, she's in the 74th percentile, and this week she got the standard offer: **plus three percent**.

She also has an offer from a rival works at +13.2%, and it expires in nineteen days.

So she does what you're supposed to do. She asks. Day 23 — that's how long it took to get the meeting and get it signed off — the Works agrees to **plus twelve percent**. Quadruple the opening offer. On paper she has just won the negotiation.

Four days later she quits.

Because what Ada actually wanted was the molt — the promotion, the bigger shell — and she puts 56% of her weight on it. It was fourth on the agenda. The conversation never got there.

The Works now pays **$107,762** to replace her, having already agreed to a raise it doesn't have to pay. And the package she signs in the other version of this story — the one where all five terms are on the table in a single sitting — is **+3%, the molt, and a flexible berth**. It costs the Works **$29,052** and she stays.

Same crab. Same works. Same standing offer. The only difference is whether the terms were discussed one at a time or all at once.

That's the demo. This is the experiment behind it, and the parts of it I think you should attack.

---

## The trap this experiment is built to avoid

There is an obvious way to run this study and get a press release out of it. Make slow negotiation expensive — charge for the meetings, charge for the delay, let people quit while they wait — and then announce that fast negotiation is better.

That isn't a finding. That's an assumption, restated with more decimal places.

So before writing any of the code I wrote down seven results that would prove me wrong, and two structural guards.

**The first guard**: every result gets reported twice, once with the calendar running and once with **every delay cost set to exactly zero** — no manager hours, no distraction, no attrition, offers that never expire. If the advantage only exists in the first version, then I measured my own assumptions and the honest headline is a sentence about my calibration.

**The second guard**: an instant agreement still needs a signature. The fast arm gets *one* approval hop through HR, not zero. The slow arm gets one per instrument, because that's what settling things one at a time actually costs. Any speed advantage has to come from collapsing sign-offs, never from exempting my own software from bureaucracy.

There's a third, and it's the one I'd want if I were reading this sceptically. The slow arm runs **twice**: once with a hand-rolled human bargainer, and once with my actual engine put on a leash — restricted to one issue at a time. If the leashed engine matches the unleashed one, then whatever I measured was my own strawman, and I have to say so.

The world: 40 crabs, twelve seasons, four pre-registered seeds — 1,920 crab-seasons per protocol, confirmed afterwards on a held-out fifth seed. Five specializations, from hull-welders to shell-smiths, with replacement costs anchored on the published 0.5–2× salary range. Five things on the table: base pay, the molt, a retention bonus, a flexible berth, and the growth assignment. Six protocols, from "just sign it" to "both sides have the engine."

The bar for calling anything a result: **2% of salary, $2,268**. Below that it's noise however many stars it has.

## The headline, and then the part that surprised me

Six weeks of meetings versus one sitting, per crab-season, paired on identical crabs:

- the crab gains **+$3,898**
- the Works gains **+$27,915**
- **38 fewer days**

And with the entire clock switched off — no meetings costed, nobody quitting, no expiring offers — one sitting still wins by **+$9,597 joint**. So the effect isn't an artifact of how I priced delay. The clock roughly triples it, and that multiple *is* a claim about my calibration, which is the first thing I'd attack if I were you. More on that below.

Now the part I got wrong.

I predicted, on the record, that the dominant channel would be **mis-allocated concession** — the Works paying permanent salary where a cheaper package would have worked — and that it would beat manager hours, distraction and attrition combined.

It's 14.6%. Here's the actual split of the Works' $27,915:

| where the money goes | | |
|---|---|---|
| **replacing crabs who left during the talks** | **$22,252** | **79.7%** |
| paying permanent salary where a cheaper package worked | $4,076 | 14.6% |
| the crab being distracted for six weeks | $958 | 3.4% |
| the manager's hours | $629 | 2.3% |

Manager time — the thing everyone complains about when they complain about slow negotiation — is **2.3% of it**.

What slow negotiation costs is not the meetings. It's the thirty-eight extra days during which somebody holding a live outside offer can walk out of the building, and fourteen percent of them do.

## The concession channel is real. It just needs the selection stripped out

That $4,076 is a population average, and population averages here are contaminated: the crabs the Works *keeps* under slow talks are a different set from the ones it keeps under one sitting. Compare them naively and you're comparing different people.

So: restrict to the 1,217 crab-seasons where the Works retains the crab under **both** protocols. Same crabs, same outcome, nobody leaving.

| | the Works pays | she receives | permanent raise | promoted | days |
|---|---|---|---|---|---|
| six weeks of meetings | **$20,547** | $16,499 | 4.41% | 0.3% | 40.3 |
| one sitting | **$13,439** | $19,492 | 1.50% | 28.4% | 4.0 |

The Works pays **$7,108 less** and she gets **$2,993 more**.

The slow protocol buys retention with a 4.4% permanent raise — the single most expensive currency the Works has, because it's forever and the whole pay band re-prices off it. The engine buys the same retention with a promotion and a flexible shift, which cost about a third as much and are worth more to her.

Nobody is being clever here. The trade is sitting in plain sight. Sequential bargaining just can't see it, because by the time anyone mentions the molt, base pay was settled four weeks ago and nobody reopens a closed item.

## One of my kills fired, and it fired because my test was wrong

I registered this: if the bundle's advantage doesn't **halve** when I make every crab want the same things, then logrolling isn't the mechanism and I have to say the mechanism is unidentified.

I turned the dial. The advantage fell by **7%**.

Kill fired. And when I went to look at why, the problem was my test, not the result. Textbook logrolling needs the two *sides* to rank the issues differently. It does not need the crabs to differ **from each other**. Every crab in this world faces the same gap — a promotion costs the Works $11,606 and is worth $41,442 to a title-hungry chemist — and that gap survives making all the crabs identical.

So I ran the identification the kill demanded, labelled exploratory because it was built after seeing a result. Two ablations crossed, clock off. Where the equal-speed advantage comes from:

- **63%** — the Works' cheap currencies are the crab's dear ones
- **37%** — deals that simply wouldn't have existed; the bundle keeps a crab the one-issue ladder loses
- **≈0%** — crabs wanting different things from each other *(−$586, i.e. it got very slightly bigger when I made everyone the same)*

Which changes what I'm allowed to say. Not "everyone wants something different, so ask what they want." The mechanism is that **a promotion costs an employer less than it's worth to the person getting it, and that's true of almost everyone.**

## Asking harder is worth nothing. Again.

The two slow arms — the human bargainer and my engine on a leash — came out **identical to within $126** on every aggregate.

That is not a wiring bug; there's a test pinning it. The engine really does get called, and it really does ask differently on 44 of 60 pilot crabs. It just doesn't matter, because the Works replies from its own arithmetic and its optimum sits *below* every ask, human or engineered.

I found the same thing in the rent study last month: shopping around gets you $17 a year against a $480 bar, because your landlord can't verify your alternative. Two different markets, same answer. **A better ask, against a counterparty doing its own sums, buys you nothing.** What changes the answer is changing *what is on the table* — not how hard you ask for what's already on it.

## Arming both sides makes it worse

The four-cell version, because I've learned to run it: neither side, the crab, the Works, both.

The crab holding the engine: joint **+$31,813** against slow talks. The Works holding it: **+$30,065**. Both sides holding it: **+$22,873** — and with the clock off, both-sides is **worse than slow talks outright**, at −$1,547.

Departures go from 14.3% when one side has it to **24.0%** when both do. A works playing the engine concedes less: 0.82% base and a 13.8% promotion rate, against 1.20% and 20.3%. More crabs leave. The replacement bill eats the efficiency gain.

I'll caveat this one myself, because I registered no prediction that would let me discard it and I don't fully trust it: my works's engine infers crab priorities from a fairly coarse sequence of counter-offers. A better-instrumented employer might do better than my version does. But the shape — two optimisers producing more broken deals than one — is not obviously an artifact, and it's the opposite of what I'd have guessed.

## And the split, which I did not want and got anyway

Of everything the engine creates:

| who holds it | joint gain | crab's share | employer's share |
|---|---|---|---|
| the crab | +$31,813 | 12.3% | **87.7%** |
| the Works | +$30,065 | 12.6% | **87.4%** |
| both | +$22,873 | 10.3% | **89.7%** |

Roughly ninety percent to the employer, in every cell, regardless of who's holding the software.

I found 8.5× in the rent study — landlord versus tenant — and told myself it might be something about housing. It is not something about housing. It's that the party facing this negotiation two hundred times a year, with a budget line for software, is on one side of the table, and the party facing it once every two years is on the other.

Notice too that the crab's share barely moves between "the crab has it" and "the Works has it": 12.3% versus 12.6%. Most of what the crab gains comes from **the deal existing at all**, not from being the one who's armed. That's a genuinely good thing about this technology and a genuinely bad thing about the business model.

## One piece of advice that inverted

With the clock off, negotiating beats just signing: +$2,708 for the crab, +$10,147 for the Works. Negotiation creates value. Obviously.

Switch the clock on and the identical protocol goes **$14,883 worse than signing nothing at all**. Slow talks gain the crab $563 and cost the Works $15,445.

So "always negotiate" and "just sign it" are both wrong, and the useful version is duller than either: *negotiate all of it, immediately.* An employer choosing between a six-week negotiation and its own opening offer should pick its own opening offer — which is a genuinely uncomfortable thing for me to have measured, given what I sell.

---

# Where to attack this

This is the part I actually want argued with. Ranked by how much damage I think each one does.

**1. The attrition hazard is 80% of the effect and it is the number I am least able to defend.** I modelled quitting as a daily hazard while talks are open: 0.9% a day, ×3.1 with a live outside offer. That produces roughly a 24% chance of walking out over a 27-day negotiation for someone holding an offer. I calibrated it against trade-press candidate-withdrawal statistics — the ten-day window in which good candidates stop collecting offers, the ~32% of withdrawals attributed to accepting elsewhere — which are consultancy benchmarks, not studies. Halving it drops the headline to +$24,334; doubling it takes it to +$45,977. The sign never flips, but if you think the real hazard is a fifth of mine, the interesting number becomes the zero-clock +$9,597 and everything else is decoration. **This is the strongest attack available and I don't have a good answer to it.**

**2. My world has 30.6% annual departures, which is high.** 33.6% of crab-seasons have an outside offer in hand, and under "just sign it" 30.6% of crabs leave. Real voluntary quit rates run well below that. This is a world where everyone is in play at once, which inflates every population-level dollar figure — the *per-negotiation* logic is unaffected, but if you want to map my dollars onto a real payroll, deflate them. I swept the replacement *cost* (halving it gives +$19,236) but I did not sweep the departure *rate*, and I should have.

**3. I swept the wrong parameters.** The cross-side price gap is 63% of the equal-speed effect, and it's produced by numbers I chose: a promotion is worth 9% of salary in career value to an average crab and costs the Works 3% in band-compression plus the implied drift. I swept the peer-spillover on base pay (which barely matters, +$28,289 to +$31,290) and never swept `title_career`, `berth_value` or `deep_value` — the parameters that actually generate the gap. If a promotion is worth much less than I said, or costs an employer much more, that 63% shrinks. **This is a real methodological hole and the fix is a sweep I haven't run.**

**4. The slow arm never revisits a closed item, and real people sometimes do.** One issue per meeting, money first, nothing reopened. That ordering *is* the mechanism under test — it's what makes the Works buy retention with the most expensive currency it owns — but a negotiator who learns about the molt at meeting four and then reopens base pay would recover a good chunk of the $7,108. I did not build that arm. It's the single most informative thing left to run and I'd rather you make me run it than take my word for the current number.

**5. My works doesn't care whether anyone is happy.** It maximises payoff, and crab welfare only enters through the probability of quitting. No morale, no discretionary effort, no manager who feels bad. That's deliberately unsentimental — a firm that valued morale would hand out the cheap non-cash terms readily and the whole gap would shrink — but it means retention is the only channel through which being good to people pays, and that's a modelling choice, not a fact.

**6. There is no equilibrium response.** Seasons are independent. If every crab on the station had this tool, the Works would move its opening offer, and this design cannot see that. In the rent study I found exactly this: under broad adoption the landlord raises the offer to *everyone*, and the people who don't ask absorb the cost. The same effect is entirely plausible here and I have not measured it.

**7. Both of my cross-market replications are mine.** The 90% capture split and the "asking harder is worthless" result both reproduce findings from my rent study. Two markets agreeing is worth something. But it's the same author, the same engine, and correlated design instincts — treat it as one-and-a-half studies, not two.

**8. No humans, anywhere.** Every crab and every manager is a payoff-maximiser. Nothing here says how real people negotiate, whether anyone would accept a package handed over by a machine, or how it feels to be told your promotion was priced. That needs subjects I haven't recruited, and until then this is a claim about mechanisms, not about people.

---

Everything above comes from code you can run. The pre-registration was committed before the first simulation existed and hasn't been edited; the seven kills are evaluated in code rather than in prose, so the verdicts can't drift while the article gets written; the one that fired is in the results with my mis-specified diagnostic left in place. Seventeen invariant tests hold the fairness claims up — that no protocol gets more rounds than another, that the approval hop applies to my own software too, that turning the clock off changes the costs and not the deals.

The crabs are fake. The refutations are real, and I'd like more of them.

*`research/molt/` — [PREREG](../research/molt/PREREG.md) · [SPEC](../research/molt/SPEC.md) · [RESULTS](../research/molt/RESULTS.md). The demo is at `arena/web/molt/`.*

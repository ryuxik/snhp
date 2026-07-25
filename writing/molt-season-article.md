# The Works offered her a 12% raise and she left anyway

*I built a shipyard full of space crabs to find out what six weeks of salary meetings actually cost. Then I rebuilt it five times, because my design choices kept turning out to be the finding. The last rebuild retracted the one before it.*

---

Ada Kelpline is a brine-chemist. She makes $134,702 a year, she's been on the station a year, she's in the 74th percentile, and this week she got the standard offer: **plus three percent**.

She also has an offer from a rival works at +13.2%, and it expires in nineteen days.

So she does what you're supposed to do. She asks. Day 23 — that's how long it took to get the meeting and get it signed off — the Works agrees to **plus twelve percent**. Quadruple the opening offer. On paper she has just won the negotiation.

Four days later she quits.

Because what Ada actually wanted was the molt — the promotion, the bigger shell — and she puts 56% of her weight on it. Nobody got to it in time.

The Works now pays **$107,762** to replace her, having already agreed to a raise it doesn't have to pay. The package she signs in the other version of this story — the one where all five terms are on the table in a single sitting — is **+3%, the molt, and a flexible berth**. It costs the Works **$29,052** and she stays.

That's the demo. This is the experiment behind it, including the parts where the experiment was wrong.

---

## The trap this was built to avoid, and the one it fell into anyway

There's an obvious way to run this study and get a press release out of it. Make slow negotiation expensive — charge for the meetings, charge for the delay, let people quit while they wait — then announce that fast negotiation is better. That isn't a finding, it's an assumption with decimal places.

So I registered seven kills before writing any code, plus two structural guards: every result reported twice, once with the calendar running and once with **every delay cost set to exactly zero**; and an instant agreement still needs a signature, so the fast arm gets one approval hop through HR rather than being exempted from bureaucracy.

Those guards worked. A different problem got past them, in four places at once.

I showed the first write-up to somebody who reads for a living. He came back with four objections. Three were right, and the fourth was worse than he thought.

**"You're ordering the agenda arbitrarily, so of course the sequential arm loses."** My slow negotiation went base pay → bonus → berth → title → deepwater, one issue per meeting, nothing reopened. Ada never reached the molt because I put it fourth. That's a designer's choice wearing a finding's clothes.

**"The single-issue bargainer should be a suite of normal corporate strategies — we have those."** We do: nineteen documented archetypes sitting in the repo, on negmas. My slow crab was an anchor-and-concede ladder I wrote myself, which is exactly the mistake I'd caught in an earlier study from the other direction.

**"You aren't pricing the skill difference — each employer has its own private valuation of a skillset."** Replacement cost in v1 was a constant per role times salary. No crab was worth unusually much to *this* employer specifically.

**"How does a public show of an offer not affect a company's internal valuation? That's just false, right?"**

It's worse than false. I went and read my own code. `p_leave` reads the crab's outside offer directly. **The employer already knew Ada's exact competing offer before anyone opened their mouth.** So my finding that "asking harder is worth nothing" wasn't a finding at all — it was the setup restated. With an omniscient counterparty there is nothing an ask could possibly reveal.

That claim is retracted. It needed no re-run to kill; it needed me to read three lines.

The other three needed a rebuild. Here's what the rebuild did to my headline.

## What survived: the clock

The slow arm is now the archetype suite, driven as-is over a negmas mechanism, one issue at a time, under three orderings — my old money-first agenda, random, and **best-first**, where the crab opens on whatever it wants most. Both arms cover all five issues; the difference is real human timelines. An email round trip is 2–5 days. Locking it down is one scheduled meeting, 7–12 days. The slow arm gets **twelve exchanges**; the engine gets three rounds.

Against that opponent, with the calendar running:

| | crab | the Works | joint | days | departures |
|---|---|---|---|---|---|
| just sign it | $14,187 | −$41,097 | −$26,910 | 1.0 | 32.1% |
| six weeks of email (best archetype) | $16,495 | −$51,433 | −$34,937 | 48.7 | 33.6% |
| **one sitting** | **$18,779** | **−$26,430** | **−$7,651** | **3.8** | **15.6%** |

**+$27,286 joint, and 45 fewer days.** That part held up.

So did the channel. Roughly four-fifths of the employer's advantage is **replacing crabs who walked out during the talks**. Manager hours are about two percent of it. The meetings are not the cost. The exposure is.

## What died: the money, at equal speed

Here's the number that decides whether any of this is about my calibration.

With every delay cost zeroed — nobody quits, nobody's distracted, no offer expires, the manager works for free — one sitting beats six weeks of email by:

- **+$3,837 joint** when outside offers can be proved
- **+$277 joint** when they cannot

In version one that number was **+$9,597**. It fell sixty percent the moment the opponent stopped being handicapped. I predicted, on the record and before running it, that it would fall by more than half. It did.

The second column is a kill firing. My registered K8 said: if the equal-speed advantage over the best archetype drops below 2% of salary, the money story is the clock and every money claim comes out. **In the unverifiable regime it does: $277 against a $2,253 bar.**

Then the part that stings. The crab's share of that equal-speed gain:

- **+$500** in the verifiable regime — below the bar
- **−$2,592** in the unverifiable regime
- **−$88** on the held-out seed

> At equal speed, the money story is an employer story. For the employee there is no equal-speed money story at all. What the employee gets is the clock.

The selection-free version says the same thing. Restricted to crabs the Works keeps under both protocols, the employer pays **$6,555 less** under one sitting — barely down from v1's $7,108. The crab's gain drops from **+$2,993 to +$624**. Against a competent opponent that opens on what it actually wants, most of what the engine looked like it was winning for the employee turns out to be what a good negotiator wins for itself.

## What I got wrong about my own thumb

I expected the agenda objection to cost me the most. It cost me the least.

Across all six reported archetypes, moving from my money-first agenda to best-first changes the concession by **$143–$378** and the crab's outcome by **$258–$650**. The largest ordering effect anywhere in the study is **$650**, against a $2,253 bar. My thumb was worth about four hundred dollars.

I registered a prediction that this kill would fire. **Refuted**, and I'd rather record that than quietly enjoy it.

## The result that only exists because the objection was right

Once the employer stops being omniscient, you can ask the question v1 couldn't: what is an offer letter actually worth?

Same crab, forced to show it versus forced to stay quiet:

- **the crab gains +$2,851**
- **the Works gains +$12,993**
- **departures fall 16 percentage points**

Showing a verifiable offer pays, for both sides. Saying you have one, in the regime where nothing can be checked, is worth **exactly zero** — because claiming is free, so everyone claims, so the claim separates nobody. That's textbook unravelling, and it is now *derived* rather than assumed by handing the employer the answer.

Now the inversion. Compare the two worlds rather than the two crabs:

| | crab | the Works |
|---|---|---|
| a world where offers can be proved, minus one where they can't | **−$6,528** | **+$9,610** |

**Being able to prove your offer is worth $2,851 to you. Living in a world where offers can be proved costs you $6,528.**

When nothing can be verified, an employer has to price everyone as though they might have a good offer, and concedes to everyone. When letters can be shown, silence convicts you of having nothing. Verifiability is an employer-side technology — and I only found that because someone told me my model was false.

## Two more, from the rebuild

**How you haggle doesn't matter.** Nineteen documented negotiation styles — Anchorer, Silent Hardliner, Split-the-Diff, Deadline Exploiter, Soviet Patience, Tactical Empath, Cialdini, Logroller, the behavioural-bias set — and the engine's advantage over them spans $27,286 to $28,329. A **1.04× spread**. Logroller is built specifically for issue-by-issue trading and lands within four percent of Split-the-Diff. The counterparty's arithmetic dominates the counterparty's manner.

So the replacement for my retracted claim is: **what you reveal is worth $2,851; how you haggle is worth nothing.** That one isn't tautological, because this employer doesn't already know the answer.

**Pricing skill differences changed nothing — and the reason is the interesting bit.** I added a private, firm-specific match value: what a crab is worth to *this* employer versus a generic replacement, drawn independently of its market value. My registered test said: if it doesn't move what the employer pays, the fix was cosmetic. Rank correlation **0.079**. It fired.

But in the unverifiable regime the same correlation is **0.279**.

> When your employer can see your outside offer, it pays for the offer. When it can't, it pays for you.

Verifiability replaces "what are you worth to us" with "what will it take to keep you." Different questions, different answers. The kill fired on its stated test, so I'm not claiming I fixed the skill-pricing gap — but the contrast is on the record.

**And the split held.** Whoever holds the engine, the employer takes **91.6%** of the value it creates. Third independent thing in this study pointing the same way, and the one result that has now survived two studies, two markets, and a rebuild designed to break it.

## The second rebuild, and the kill I agreed to in advance

One more objection, and it was the sharpest: **the employer had one pocket.**

Everything the Works paid — raise, bonus, promotion, flexible hours, growth
assignment — came out of a single scalar pot of dollars. So there was exactly one
trade axis, cash versus non-cash at fixed ratios, and the same trade was optimal
for every crab alive. I had built a logrolling experiment and given the logroller
almost nothing to logroll. Real employers have a comp budget, an equity pool, a
PTO accrual, headcount and band constraints, a coverage roster — different
pockets, wildly different shadow prices. And PTO, the cleanest example of the
whole thesis, wasn't even in my issue set.

So: five budgets with independently drawn shadow prices, PTO as a sixth issue, a
25% chance there is simply no promotion slot in your band this season at any
price. And before running it, a kill we agreed on: **if budget structure doesn't
lift the equal-speed gain above $6,090, logrolling has been given a properly
specified employer and found small — and the product claim goes with it.**

It came in at **+$5,397**. It fires by $693. On the held-out seed, +$5,944
against a $6,154 threshold — fires by $210.

The structure helped. It moved the equal-speed gain from $3,837 to $5,397, a real
**+41%**. I predicted it would roughly double, which is why the threshold sat
where it did. It didn't, twice, in the same direction, and the bar doesn't move
after the fact.

**So the equal-speed money story is dead.** At the same speed, against a real
corporate strategy, with an employer that has actual budget structure, multi-issue
bundling is worth less than 2% of salary over what a competent single-issue
bargainer already gets. Where outside offers can't be verified it's worth
**−$630**.

What's left is the clock: **+$31,535 joint with the calendar running**, departures
cut from 35.7% to 14.5%. The product is worth a great deal. It is not worth it for
the reason it is sold.

## And the number that now goes first

The second kill fired too, and it's the one that changes how this gets written.

**The engine takes cash out of the employee's pocket.** $3,172 across the
population; on the selection-free subset — the same crabs, retained either way —
**$16,065 of cash becomes $9,147. A $6,918 pay cut**, handed back as perks.

I swept the exchange rate this time, 0.5× to 1.5×. The employee's *utility* gain
is robust: it never crosses zero, even valuing a promotion at half what I said.
The employee's *cash loss* is equally robust: negative at every rate tested.

Both. At every rate. The engine reliably converts one into the other, and whether
that's a good deal for you depends entirely on an exchange rate that neither you
nor I can verify.

PTO, for what it's worth, turned out to be the second most-granted term in the
package — ahead of the promotion. The objection that my issue set was thin was
correct.

## The measurement I broke

One kill recorded no verdict, because I broke the instrument.

K17 was meant to ask the question that matters most given the above: if the
*employer* configures this tool, and configures it to believe your perks are worth
1.5× what they are, does it extract more cash from you? The biased arm came back
**bit-identical** to the unbiased one — $0, $0, $0, on both seeds and in both
regimes.

That's not a null. I threaded the biased exchange rate into a single early-stop
check and never into the logic the employer uses to decide what to *offer*. If
that check doesn't bind, the arm is identical by construction, which is exactly
what happened.

No verdict. And it is now the sharpest open question in the study, sitting
directly on top of a confirmed finding that this thing converts your salary into
things it priced itself.


## The third rebuild, and the one that hurt

The last objection was the shortest: **a promotion is tied to salary and to
reputation, inside and outside — and there are only so many slots, which is a
budget separate from cash.**

Three things wrong in my model, and I checked all three before conceding.
`title_drift = 0.02`: a promotion came with a **2% raise**. A promotion never
touched `omega`, so it had **zero effect on market value** — non-portable by
construction. And `slot` was a per-season boolean: if true, *every* crab that
season could be promoted. No quota, no rivalry. When I'd described that to him as
"band slots, a constraint money cannot solve," I'd oversold it.

So: a promotion becomes a **12% raise** drawing on the pay budget *and* a scarce
slot drawing on a separate one; it lifts your market value by 5 points, so
promoting you makes you more poachable; and only **one crew member in eight** can
be promoted in a year.

And before running it, the guard, because this is the dangerous direction — the
objection makes the product's best currency bigger, right after a kill fired
against the product. So: **K14's verdict is permanent for the world it tested.**
Whatever this found would be a new test of a different world, reported beside it,
never in place of it.

Then it ran, and the equal-speed gain fell to **+$2,584**. On the held-out seed,
**+$1,739** — below the bar entirely.

**Making the product's best currency bigger and better made it worse.** The
equal-speed money claim is now retired permanently, across two independently
specified promotion models.

## The table I did not want — and then had to retract

For a while this section reported that an ordinary human archetype got the
promotion five times as often as the engine and walked away with $3,395 more
cash, and that the engine lost even on its own scoring.

**That was a bug in my harness, and it took a reader refusing to accept it to
find.** The employer was not the same employer in the two arms. In the
sequential arm it could cut base pay to fund a promotion; in the engine arm it
was floored at the standing offer and structurally barred from that exact trade.
And its reply rule differed: in one arm it would only counter if countering beat
doing nothing, in the other it always countered.

Fix both — one employer, used by both arms — and the result reverses at every
setting:

| employer's rules | engine joint | sequential joint |
|---|---|---|
| no base cut, strict reply | 2,713 | 1,144 |
| no base cut, permissive | 6,656 | 1,754 |
| may cut base, strict | 8,897 | 4,859 |
| may cut base, permissive | 10,296 | 5,581 |

The engine wins all four, on joint surplus and on the employee's own utility.
Either asymmetry on its own was larger than the gap I had been reporting as a
finding.

Once a promotion costs a real 12% raise and a scarce slot, the engine stops
asking for it and buys retention with PTO and flexible hours, which are cheap.
The human keeps asking for the title, sometimes gets it, and the title comes with
a raise attached.

The sweep makes the mechanism unmistakable:

| promotion raise | engine's promotion rate | your cash |
|---|---|---|
| 6% | 3.5% | −$2,470 |
| 12% | 1.9% | −$2,814 |
| 20% | **0.4%** | **−$4,447** |

**The better a promotion actually is, the less an optimiser will get you one.**

Selection-free — same crabs, kept either way — the engine turns **$18,252 of cash
into $10,717**, and the promotion rate falls from 16% to 3%.

## Two more kills, one of them with a weak instrument

**Scarce slots should be where an optimiser shines.** Allocating one-in-eight
promotions to the crabs where retention value is highest is exactly the problem
software should beat a person at. Measured: the engine's targeting correlation is
**+0.049** against the archetype's **+0.337**.

But I'll flag what that number can't carry: the engine promotes 2.3% of crabs
against the archetype's 11.2%, and a correlation with a positive class that rare
is mechanically attenuated. The honest reading is the weaker one — **the engine
doesn't use the scarce resource, so it can't be said to allocate it well.**
Whether it would aim better at equal grant rates is untested. I threw out a
result in the last round for having a dead instrument; this one is merely weak,
and it gets labelled rather than dressed up.

**And promoted crabs didn't leave** — zero of 44, against 14.3% of everyone else,
despite portability. That is selection, not causation, and I'm not reporting it as
anything else: employers promote the people they most want to keep. The causal
version needs a forced-promotion arm that doesn't exist.

## The two things that actually survived

**A constant I never justified turned out to dominate.** The engine takes an
estimate of what the other side's walk-away is worth. I set it to 0.45, carried
over from a study about landlords, with no comment and no sweep. It is the
highest-leverage input in the whole model:

| what you assume their walk-away is worth | the employee ends up with |
|---|---|
| 0.20 | $20,914 |
| 0.40 (the engine's own default) | $20,046 |
| 0.45 (mine) | $19,531 |
| 0.60 | $17,243 |
| 0.80 | $12,627 |
| the truth | $20,858 |

The truth behaves like 0.20 — an employer staring at a replacement bill has an
awful outside option — so guessing cautiously is what costs you. A user who
assumes their employer can walk easily gives up **$8,287** against one who knows
better. The most consequential number in a negotiation tool is a default nobody
validated, and being careful with it is the expensive mistake.

**And the mode I never ran until the fifth rebuild is the only unambiguously good
result in the study.** Two engines pointed at each other adversarially *destroy*
value — joint surplus of **−$581**. Two engines in the product's peer mode, where
both sides prove their walk-away rather than guessing, produce **+$5,171** — and
the employee takes **95% of the gain**, inverting the ~90%-to-the-employer split
that every other arm here produced.

Seventy percent of that is just the two sides knowing each other's true position.
The cooperative-selection dial, on its own, does nothing measurable. It isn't
being nice that works. It's being verified.

### Not a different game — a different point

The obvious objection: maybe the engine and the human are just optimising
different things. They aren't, and it's checkable — both score the crab with the
identical `crab_value3`. So I enumerated the package space per crab and found the
Pareto frontier.

| | crab utility | crab cash | the Works | on the frontier |
|---|---|---|---|---|
| archetype | 22,024 | 16,714 | −25,159 | 86% |
| engine | 20,082 | 10,576 | −20,385 | 82% |

Both are Pareto-efficient roughly 85% of the time, and both in the same
crab-season 70% of the time. **Nobody is playing badly.** The engine just picks a
different point: joint **+$2,832**, of which **the employer takes 169%** — more
than all of it, because the employee's share is negative.

**The engine slides along the frontier toward the employer.** It isn't winning
the employee a bigger share of the pie. It's finding a cheaper way to hand over a
package, and the saving goes to the side that's paying.

The cash cut, meanwhile, **survived and grew**: −$6,918 before, −$7,535 now,
−$8,591 on the held-out seed. Making the promotion expensive pushed the engine
further into the cheap currencies. That headline wasn't conditional on tiny
promotions; it's more true when promotions are real.


---

# Where to attack this

Still the part I want argued with. The list is shorter than it was, because four items got promoted into the model.

**1. The attrition hazard is still the load-bearing parameter and I still can't defend it.** Roughly four-fifths of the clock-on effect is replacement cost from crabs walking out mid-negotiation, at a hazard of 0.9%/day, ×3.1 with a live offer, calibrated against consultancy candidate-withdrawal benchmarks rather than studies. The rebuild did not touch it. If you think it should be a fifth of what I set, the only number left standing is the equal-speed one — which is now $3,837, or $277, depending on the regime.

**2. My world still has ~32% annual departures.** A third of crab-seasons carry an outside offer. That's a world where everyone is in play at once, which inflates every population-level dollar. Per-negotiation logic is unaffected; to map onto a real payroll, deflate.

**3. The Works still knows what you want.** Amendment 1 removed the employer's knowledge of your outside offer. It did not remove its knowledge of your priorities — `crab_value` is still exact. Every number should be read as "the employer knows what you want, but not what you can get elsewhere." That's the next omniscience to kill, and it will probably cost me something.

**4. The perk rates are swept now; the shadow prices are not.** I swept what perks are worth to the employee (0.5×–1.5×) and the result held. I did *not* sweep the five employer shadow prices — band 0.60, accrual 0.35, coverage 0.50, capacity 0.80 — and those are my estimates, and they are what produced 41% of the equal-speed gain. That sweep should exist before anyone leans on the number.

**5. Nobody reopens a settled issue, in any version.** Twelve exchanges, six issues, no take-backs. A negotiator who learns something at exchange nine and reopens exchange two would recover part of the gap. Untested, and cheaper to build than either rebuild was.

**5b. K17 never ran.** Whether an employer that configures the exchange rate extracts more cash is the question the cash finding demands, and my instrument for it was dead on arrival.

**5c. Nothing here plans across people.** A promotion quota is a knapsack over a whole team, and my engine solves one crab at a time, first come first served. The version of this product that allocates scarce slots across a department is untested, and it's the obvious thing to build next.

**6. No morale, no equilibrium response, no humans.** The employer values you only through the probability you quit. Seasons are independent, so a world where everyone has this tool — in which employers would simply move their opening offers — is invisible to this design. And every crab and manager is a payoff-maximiser, so nothing here says how people actually negotiate.

**7. Both cross-market replications are mine.** The ~90% split and the verifiability result rhyme with things I found in a rent study. Same author, same engine, correlated instincts. One-and-a-half studies, not three.

**8. Five harness defects, one study.** An inert bias parameter, an arm that never let the employer refuse, a probe loop that discarded every counter, an engine shown the same offer history every round, and two arms facing different employers. Every one produced a number in the direction I was leaning at the time. Every one was caught because a reader pushed on a figure that looked wrong rather than taking it. There are now standing assertions in the test suite for three of the five; the sixth — that two arms being compared instantiate the same counterparty — still isn't written, and until it is, treat every comparison here as provisional.

---

Version one of this article claimed something tautological, two things measured against a handicapped opponent, and one number five times too flattering to the employee. Version two survived a rebuilt opponent and then lost its central claim to a kill I'd agreed to in advance and expected to pass. Version three lost it permanently, and turned up an ordinary corporate negotiator beating my software on the thing employees actually care about. Across three rebuilds I made twelve on-record predictions and got five right.

The pre-registration was committed before the first simulation existed and hasn't been edited. Both amendments were committed before their rebuilds existed and state in writing which of my own claims they were suspending and which predictions I expected to lose. The kills are evaluated in code rather than prose, so verdicts can't drift while the article is written. Five of them fired, including the one that took the headline.

The crabs are fake. The refutations are real, and that exchange was worth more than the study.

*`research/molt/` — [PREREG](../research/molt/PREREG.md) · amendments [1](../research/molt/PREREG-AMENDMENT-1.md) · [2](../research/molt/PREREG-AMENDMENT-2.md) · [3](../research/molt/PREREG-AMENDMENT-3.md) · [4](../research/molt/PREREG-AMENDMENT-4.md) · [5](../research/molt/PREREG-AMENDMENT-5.md) · results [v1](../research/molt/RESULTS.md) · [v2](../research/molt/RESULTS-V2.md) · [v3](../research/molt/RESULTS-V3.md) · [v4](../research/molt/RESULTS-V4.md) · [v6](../research/molt/RESULTS-V6.md). Demo at `arena/web/molt/`.*

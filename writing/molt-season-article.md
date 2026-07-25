# The Works offered her a 12% raise and she left anyway

*I built a shipyard full of space crabs to find out what six weeks of salary meetings actually cost. Then I rebuilt the whole thing, because four of my design choices were doing the work, and most of my headline died.*

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

---

# Where to attack this

Still the part I want argued with. The list is shorter than it was, because four items got promoted into the model.

**1. The attrition hazard is still the load-bearing parameter and I still can't defend it.** Roughly four-fifths of the clock-on effect is replacement cost from crabs walking out mid-negotiation, at a hazard of 0.9%/day, ×3.1 with a live offer, calibrated against consultancy candidate-withdrawal benchmarks rather than studies. The rebuild did not touch it. If you think it should be a fifth of what I set, the only number left standing is the equal-speed one — which is now $3,837, or $277, depending on the regime.

**2. My world still has ~32% annual departures.** A third of crab-seasons carry an outside offer. That's a world where everyone is in play at once, which inflates every population-level dollar. Per-negotiation logic is unaffected; to map onto a real payroll, deflate.

**3. The Works still knows what you want.** Amendment 1 removed the employer's knowledge of your outside offer. It did not remove its knowledge of your priorities — `crab_value` is still exact. Every number should be read as "the employer knows what you want, but not what you can get elsewhere." That's the next omniscience to kill, and it will probably cost me something.

**4. I still swept the wrong parameters.** The cross-side price gap — a promotion worth 9% of salary in career value, costing the employer 3% in band compression — is set by numbers I chose and never swept. If a promotion is worth much less than I said, the remaining equal-speed gain shrinks toward a bar it is already close to.

**5. Nobody reopens a settled issue, in either version.** Twelve exchanges, five issues, no take-backs. A negotiator who learns something at exchange nine and reopens exchange two would recover part of the gap. Untested, and cheaper to build than the last rebuild was.

**6. No morale, no equilibrium response, no humans.** The employer values you only through the probability you quit. Seasons are independent, so a world where everyone has this tool — in which employers would simply move their opening offers — is invisible to this design. And every crab and manager is a payoff-maximiser, so nothing here says how people actually negotiate.

**7. Both cross-market replications are mine.** The ~90% split and the verifiability result rhyme with things I found in a rent study. Same author, same engine, correlated instincts. One-and-a-half studies, not three.

---

Version one of this article claimed something tautological, two things measured against a handicapped opponent, and one number five times too flattering to the employee. All four came out of four sentences from one reader.

The pre-registration was committed before the first simulation existed and hasn't been edited. The amendment was committed before the rebuild existed and states in writing which of my own claims it was suspending and which prediction I expected to lose. The kills are evaluated in code rather than prose, so verdicts can't drift while the article is written. Three of them fired.

The crabs are fake. The refutations are real, and that exchange was worth more than the study.

*`research/molt/` — [PREREG](../research/molt/PREREG.md) · [AMENDMENT 1](../research/molt/PREREG-AMENDMENT-1.md) · [v1 RESULTS](../research/molt/RESULTS.md) · [v2 RESULTS](../research/molt/RESULTS-V2.md). Demo at `arena/web/molt/`.*

══════════════════════════════════════════════════════════════════
DELETE THIS BLOCK BEFORE PUBLISHING

All three images live in ONE folder. Open it and drag them in:

    /Users/ryuxik/Desktop/snhp/writing/cards/

    cover.png       1600x640, 5:2 — the article header image
    leverage.png    1200x628
    band.png        1200x628

The cover is 5:2 because that is the ratio X crops an article header to.
The two inline figures stay at 1200x628. The link-preview og:image is a
separate file already wired into arena/web/molt/, and is NOT this one.

Where each one goes is marked inline below.
The .svg next to each PNG re-renders it if you want a different size.
══════════════════════════════════════════════════════════════════

# Your employer knows what it costs to replace you. You have a blog post about anchoring.

*I built ten thousand crabs a labour market to find out what asking for a raise is actually worth. Up to $44,065, and not one dollar of it comes from how well you ask.*

──────────────────────────────────────────────────────────────────
IMAGE 1  ▸  UPLOAD:  cover.png
CAPTION:  Ten thousand simulated crabs, thirty-nine pre-registered kills, one number that decides the whole thing.
──────────────────────────────────────────────────────────────────

---

By the end of this you'll know what asking is worth in dollars, what actually decides it (not skill, not nerve), and what an employer will spend to keep that number away from you. Also the five times I got this wrong, which is the part worth your time.

First, the crabs.

A crab grows only by shedding its shell. Once a year it molts, walks out of the old one, takes on a bigger body, and for a few days afterwards it is soft and slow and delicious. Growth is a window. It's annual. It costs you your armour.

Put a station out in the belt, crew it with ten thousand of them, give it a molt season. That's a promotion cycle. It's also a labour market, so I built one.

**Ada Kelpline welds pressure hulls.** $134,702 a year, one year aboard, better than three-quarters of the crew. This week: **plus three percent**.

She also has an offer two rocks over at +13.2%, expiring in nineteen days.

So she asks.

Day 23, the time it took to get a meeting and a signature, the Works agrees to **plus twelve percent**. Four times the opening. On paper she won.

Four days later she quits.

She wanted the molt. The bigger shell. She puts 56% of her weight on it and nobody got that far down the agenda. The Works pays **$107,762** to replace her, having agreed to a raise it no longer owes. In the other version she signs something costing them **$29,052** and stays.

**Ada didn't negotiate badly. She never found out what she was worth to them.**

You can watch that negotiation happen, round by round, at **[arena.snhp.dev/molt](https://arena.snhp.dev/molt/)**. Every offer in it is recorded engine output, including the version where she stays.

## The number nobody tells you

──────────────────────────────────────────────────────────────────
IMAGE 2  ▸  UPLOAD:  leverage.png
CAPTION:  Three-year value of the package agreed, against just signing what you were handed. 600 crab-seasons, five pre-registered seeds.
──────────────────────────────────────────────────────────────────

| | just sign it | ask | difference |
|---|---|---|---|
| everyone | $6,408 | $19,937 | **+$13,529** |
| you have an offer (a third of people do) | $8,367 | $42,111 | **+$33,745** |
| an offer, and you're a pain to replace | $7,446 | $51,511 | **+$44,065** |
| no offer, no leverage, nothing | $6,189 | $11,918 | **+$5,729** |

Bottom row: no alternative, no cards, nothing. Opening your mouth is worth five and a half grand.

What moves the number isn't eloquence. It's **what replacing you costs**. That's the whole game, and it's the thing you don't know and they do.

Fifty-five percent of people take the first offer.

## Then I got it wrong, five times

Thirty-nine kill conditions, registered before any code. Each says in advance what number proves me wrong. That's the only reason the rest of this is worth reading.

**One: I rigged the opponent.** Hardcoded agenda, salary first, promotion fourth, which is why Ada never got there. Then I stopped and asked how showing an offer could possibly fail to change what a company thinks you're worth. So I read my own code. The employer already knew Ada's offer before she spoke. My finding that asking harder is worthless wasn't a finding, it was the setup restated. Retracted in three lines of code.

**Two: my employer had one pocket.** Raise, bonus, promotion, time off, all one pot. One trade, identical for every crab alive. I'd built a horse-trading experiment with nothing to trade. Real employers have a comp budget, a headcount budget, a holiday accrual, a rota. Time off is expensive on the books and nearly free at the margin. That's the whole thesis and it wasn't in the model.

**Three: I broke the promotion.** In my code it came with a 2% raise, never touched your market value, and everyone could have one at once. Fixed: 12% raise, genuinely scarce slot, and being promoted makes you more poachable. It got *worse*. Once a promotion costs real money the engine stops asking and buys you off with holiday. A 6% promotion raise gets you promoted 3.5% of the time. 12% gets 1.9%. **20% gets 0.4%.**

**The better a promotion is, the less an optimiser will get you one.**

**Four: a human started beating my software.** I wrote it up. Put it on the demo. It felt like the uncomfortable result an honest study should produce.

It was a bug. **The employer wasn't the same employer in both arms.** One could cut base pay to fund a promotion. The other was floored at its own opening offer, banned from that exact trade. One employer, both arms, and it flips everywhere:

| the employer's rules | engine | human |
|---|---|---|
| floored at its offer, counters only when it pays | **2,713** | 1,144 |
| floored, always counters | **6,656** | 1,754 |
| may cut base pay, counters only when it pays | **8,897** | 4,859 |
| may cut base pay, always counters | **10,296** | 5,581 |

Five instruments died over this study. A parameter that did nothing. An arm that never let the employer refuse. A loop that binned every counter. An engine shown the same page of history twice. Two arms facing different employers. **Every one landed in the direction I was leaning.** Every one was caught by refusing to accept a figure that looked too good.

**Five, the embarrassing one.** I'd written that the employee side never worked in any specification. Then I read that sentence back and asked how an employee could possibly have zero leverage.

They can't. Every comparison here was the engine against another way of negotiating. None asked what negotiating beats *not* negotiating, though "just sign it" had been sitting there as a control arm since version one.

That's the table at the top. Seven rebuilds polishing one comparison while the biggest number sat in the arm I wasn't looking at.

## What it's actually for

Does software beat a person? No. Against the best of nineteen documented corporate strategies: +$598 on one seed, −$592 on another. A tie.

**It collapses the process.** Six weeks of email and one afternoon land in the same place. The afternoon gets there **forty-two days earlier**, with **half as many negotiations falling apart**, 35% down to 16%. You aren't trading outcome for speed. Same outcome, sooner, more often.

Where do six weeks go? **Thirty-four days of it is email.** Both routes pay the same four days waiting for a signature. The software doesn't get to skip HR either.

With the harness fixed, the money advantage survived the clock being switched off: **+$4,585**. I had fired three separate kills declaring that dead. All three ran on the broken instrument. The bar never moved. The ruler was bent.

## Everyone gains and nobody does it

Every term on the table at once, two or three packages costing the employer about the same, you pick. Employee **+$1,116**, six weeks faster, far fewer collapses. Costs the employer nothing, because the menu is built from what it would already sign.

Free money on the floor. When your model says that, your model is missing something.

My guess was the manager. The firm gains, but the person offering a menu has a different bonus. So I built one who feels 20% of what losing you costs and gets punished for spending comp budget.

**Didn't block a thing.** The menu is still worth +$4,789 to the employee, and it costs that manager **$2,589 less** of the budget they're judged on. Not merely tolerable. The cheapest way they have to keep you.

One thing did fall out: a stingy manager is a **transfer to the firm, not a cost it bears**. Employee loses $6,500, firm gains $5,144. Nobody upstairs funds a fix for that.

So not the manager.

## The band

This study had been one-shot since version one. Every season independent, nobody remembering anything. So I linked two seasons and let the crab remember what it was shown.

| what the employer does | its two-season payoff | what you get |
|---|---|---|
| one package, no menu | −48,974 | 27,367 |
| a menu, forgotten every year | −51,272 | 35,837 |
| **a menu, and you remember** | **−57,712** | **44,520** |

Showing you three things it would equally sign tells you how much room it has. You don't forget. Over two seasons that costs the employer **$8,738** and is worth **$17,153** to you.

**They're not leaving free money on the floor. They're paying $8,738 a head to stop you learning how much room they have.**

──────────────────────────────────────────────────────────────────
IMAGE 3  ▸  UPLOAD:  band.png
CAPTION:  What a menu costs the employer over two seasons, once you remember what you were shown. The gap between rows two and three is the price of your memory.
──────────────────────────────────────────────────────────────────

The first thing in eight rebuilds that explains the world instead of contradicting it. It also explains why every piece of salary advice you have ever been given is about *technique*. How to anchor, when to pause, what to say. Never the one number that decides it.

Technique is free to publish. The band isn't.

## Where to attack this

**1. The attrition hazard carries the clock finding, and I can't defend it.** Calibrated from consultancy benchmarks, not studies. A fifth of my number and most of the headline goes.

**2. Replacement cost: two literatures, ten times apart.** Industry says 45 to 160% of salary. The [academic review](https://www.americanprogress.org/article/there-are-significant-business-costs-to-replacing-employees/) says **21%**. I swept the whole range. Direction never flips, and the academic end is stronger (+$7,544 against +$5,704). What does scale is the four-fifths decomposition, which I haven't re-run at the low end.

**3. This world has 32% annual departures.** Everyone in play at once. Per-negotiation logic is fine. Deflate before mapping it onto a real payroll.

**4. The employer still knows what you want.** I removed its knowledge of your outside offer, never of your priorities.

**5. Nobody plans across people.** A promotion quota is a knapsack over a whole team. My engine solves one person at a time, first come first served.

**6. No morale, no equilibrium, no humans.** If everyone had this tool, employers would move their opening offers. This design can't see that.

**7. Both cross-market replications are mine.** Same author, same engine, same instincts. One and a half studies, not three.

---

Thirty-nine kills. Twenty-nine predictions, fourteen right. Five dead instruments. Four claims retracted after I'd written them down, one within minutes.

The pre-registration predates the first line of simulation and hasn't been edited. Every amendment predates its rebuild and names which of my claims it was suspending and which prediction I expected to lose. Kills are evaluated in code, so a verdict can't drift while the article gets written.

None of it stopped me being wrong. It made being wrong cheap and legible, so that every time something read as too good, there was a number and a line to go and check. Every time, the smell was right.

Including the last one. This section used to warn that my replacement cost might be four times too high. Then I noticed that a parameter which only changes scale should just be swept. Direction holds across ten times the range.

Ada asked. She got four times the opening offer. She still left, because what she wanted was on a list nobody read out, and the number that would have told her what she was worth was on the other side of the table.

Not that software argues better than you. It doesn't. But it puts everything on the table in an afternoon instead of six weeks, and it can estimate what walking out of that room would cost them. The one thing they will never volunteer, and the only thing that was ever deciding the answer.

## So I'm building the other half

You tell it what you're paid, what kind of work it is, and whether you have an offer you could actually show. It estimates what replacing you costs, which is the number deciding this whether anyone says it or not. Then it gives you the shapes worth asking for and the words to ask in, in one sitting.

It won't tell you what they'll accept. Nothing can. They're paying $8,738 a head to keep that private, and any tool claiming otherwise is guessing at the one thing it can't know.

**It's live now, as a labelled demo, and the label is the point.** The cost of replacing you is the number everything turns on. Three of the five role figures come from a review of 31 case studies I've now read in full. Two are my own estimates off that review's median. The underlying data runs 1992 to 2007. That's why it shows you a span rather than a number, and why the first thing it tells you is all of the above.

Publishing it this way meant changing a test. The framework had a rule that unsourced evidence may not reach the public. It now says unsourced evidence may not reach the public *silently*: a tool can be live with imperfect numbers only if it says so in the first line a person reads, and there's an assertion that fails if it doesn't. That seemed better than either shipping quietly or sitting on it.

**[api.snhp.dev/helper](https://api.snhp.dev/helper)** Free, keyless, no account. Describe the situation in a sentence and it works out which questions actually matter.

And **[arena.snhp.dev/molt](https://arena.snhp.dev/molt/)** is the study itself, playable: Ada's negotiation round by round, the version where she stays, and every figure above with the run behind it.

The crabs are fake. The refutations are real, and worth more than the study.

*[`research/molt/`](https://github.com/ryuxik/snhp/tree/main/research/molt) for the [pre-registration](https://github.com/ryuxik/snhp/blob/main/research/molt/PREREG.md), eight amendments, and every result including the retracted ones. Figures: `writing/cards/`. (`writing/molt-figures.html` is the version-two figure set and is left in place only because two of its three charts are findings this article goes on to retract.)*

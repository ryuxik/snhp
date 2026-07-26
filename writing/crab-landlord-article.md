══════════════════════════════════════════════════════════════════
DELETE THIS BLOCK BEFORE PUBLISHING

All four images live in ONE folder. Open it and drag them in:

    /Users/ryuxik/Desktop/snhp/writing/figures/

    fig1-loyalty-gap.png
    fig2-information-vs-selection.png
    fig3-dead-heat.png
    fig4-adoption-decay.png

Each is 1600x900. Where each one goes is marked inline below.
The .html next to each PNG re-renders it if you want a different size.
══════════════════════════════════════════════════════════════════

# Your landlord has an algorithm. You have a blog post from 2016.

*I built a world of 3,000 renting space-crabs to find out who is actually negotiating against you. The answer is not who I expected, and neither is the reason they win.*

---

In the first quarter of this year, MAA reported new leases down **7.0%** and renewals up **5.4%**.

Camden reported the same shape. So did Equity Residential, IRT, and Essex. Same quarter, same direction, same gap, and it has been running since 2024.

──────────────────────────────────────────────────────────────────
IMAGE 1  ▸  UPLOAD:  fig1-loyalty-gap.png
CAPTION:  12.4 points of daylight between signing and staying. MAA Q1: new leases −7.0%, renewals +5.4%.
──────────────────────────────────────────────────────────────────

Read that again, because it is stranger than it looks. Every large apartment operator in America decided, in the same quarter, to charge the loyal tenant more and the new one less. Not one of them had to call the others.

I wanted to know how that happens. It took a week, three thousand crabs, and a wrong answer to find out.

## The arithmetic everybody does

Your rent is going up $200 a month. The internet's advice is: ask. And every article that says so runs the same numbers.

If you leave, they eat a turnover. Vacancy, paint, listing, screening. Everyone puts it at one to three months of rent. Call it five thousand dollars against the $2,400 they are trying to gain.

They are risking five to make two. You have leverage and nobody told you.

I went looking for the source of that "one to three months."

**There isn't one.**

- The most-repeated version traces to a property-management blog that calls it a national average and cites nothing.
- The industry association's endlessly-recycled $1,000 to $5,000 traces to a 2016 blog post.
- The best real survey, 4,666 properties and 1.09 million units, says $2,000 to $4,000.

Then I went looking for the other half. What does it cost *you* to move?

**No government statistic exists.**

- The Census publishes how often people move.
- The BLS publishes a price index for moving services.
- Nobody official publishes what a move costs.

The figure everyone quotes, $2,300, comes from a trade body absorbed into another organisation in December 2020, circulates with three mutually inconsistent values attached, and has no reachable primary document behind it.

So the sentence "they're risking five to make two" is built from two numbers, and neither one has ever been measured.

Fine, I thought. Nobody knows anything. It's dark on both sides of the table.

That turned out to be the wrong sentence in the piece.

## It is not dark on both sides

While you are working from a blog post, there is software on the other side of your renewal.

It estimates how likely **you personally** are to leave. It uses your tenure, your payment history, what comparable units are getting, what it costs to turn your specific unit. It runs on most large buildings in the country. It updates daily.

That is the answer to the thing I opened with. Five companies posted the same spread in the same quarter and none of them had to coordinate, because they had all bought the same math. Point enough operators at the same optimiser and you get a cartel's output with nobody in a room.

And it means the asymmetry in your rent negotiation was never about size, or money, or who can afford a lawyer.

> **One side measures. The other side guesses.**

Once I could see that, I wanted to know what the measuring side actually knows. So I built it.

## Three thousand crabs and a landlord

Crabs rent habitats from stations. Every year a station makes a renewal offer and a crab accepts, counters, or leaves. Stations pay to turn a habitat over. Crabs pay to move. Sixty years, seeded so it runs identically every time.

The first thing that fell out was not what I went in for.

A station maximising expected value, doing the arithmetic properly with no sentiment in it, **concedes to between 43 and 50 percent of the crabs who ask.** In the real world, about 22% of tenants who push back get anything.

The machine should be folding twice as often as landlords actually do.

I assumed bureaucracy. Nobody reads your email, the policy gets applied to a spreadsheet row, the exception queue is full. So I built the queue, with a real capacity limit, and it does not close the gap at any size I give it.

Then I checked your side of the table, and it is worse. Only 39% of renters ever try. I went looking for a cost that would explain the other 61%: the time, the awkwardness, the fear of being marked as trouble. **To make the model produce the observed 39%, sending one email has to cost the tenant 27 to 55 hours of their own wages.**

It does not cost that. Which means whatever stops people is not a cost at all, and every piece of advice built on making it easier is aimed at the wrong thing.

Both sides are leaving money on the table. Neither is playing the game the numbers describe.

## What actually moves the number

About 22% of people who push back get something, and that roughly doubles past two years of tenure. There are two very different reasons that could be true. Either asking *selects* for the people who were leaving anyway, or asking *tells the software something it could not otherwise see*.

Those are separable, so I separated them. Selection moves the success rate by 0.002 to 0.072. Information moves it by 0.80 to 0.90.

──────────────────────────────────────────────────────────────────
IMAGE 2  ▸  UPLOAD:  fig2-information-vs-selection.png
CAPTION:  Information moves the odds 0.85. Selection moves them 0.04.
──────────────────────────────────────────────────────────────────

It is not close, and it follows directly from what the other side is.

> **A system that prices you by measuring you can only respond to things it can measure.**

"I might have to move" is free to say, so it carries nothing. Something checkable is a different object entirely.

The ask was never the action. Becoming measurable is the action, and asking is just how you deliver it.

Which is a strange thing to build a product around, and it is what I ended up building one around.

There is a version of this that surprised me. I gave the crabs real preferences over habitats, so some of them wanted to move for reasons that had nothing to do with money: more space, a better neighbourhood. About one in five renter moves is exactly that. I expected it to weaken your hand, since someone leaving for a bigger kitchen is not making a threat.

The opposite. A discount got **better** at holding onto people, removing 45% of turnover instead of 33%. A tenant with a real reason to move is already sitting near indifference, and near indifference is exactly where a discount lands. If you are half thinking about leaving for reasons that have nothing to do with rent, you are not a weaker person to negotiate with. You are the one most worth an offer.

## And the five-to-two gap was never there

With both sides finally measured rather than borrowed:

| | Months of rent | At a $2,000 rent |
|---|---|---|
| **You**, leaving: search, apply, physically move | **1.48** | $2,960 |
| **Them**, re-letting: make-ready, paint, listing | **1.50** | $3,000 |

Your side is built up from actually searching for somewhere else. Theirs is from the industry's own cost surveys.

──────────────────────────────────────────────────────────────────
IMAGE 3  ▸  UPLOAD:  fig3-dead-heat.png
CAPTION:  A dead heat: you 1.48 months ($2,960), them 1.50 months ($3,000).
──────────────────────────────────────────────────────────────────

A dead heat. What sits on top of each roughly cancels: they add vacancy and the risk of a worse tenant, you add everything you have accumulated in the place, and a deadline.

Which side edges it turns on the cost of a physical move, the number nobody measures. I fixed its plausible range in advance at $700 to $3,300. The answer crosses over *inside* that range.

**Nobody can tell you who the weaker party is.** Not me, not the guide you read. The measurement does not exist, which is the entire point.

And notice what that does to the advice industry's argument. It was never wrong about the direction. It was wrong to have a number at all.

## The part that costs me something

So build the tool. Put a number on the tenant's side. That is my job.

Here is what the tool does at scale. I ran adoption from one percent to a hundred. Success falls from about **0.97 to about 0.05**, monotone, in a rising and a falling market alike. Let the model decide how many people ask instead of telling it, and nearly everyone asks, and the aggregate turns negative: roughly $100 moves from landlords to tenants and roughly $187 of value is destroyed getting it there.

──────────────────────────────────────────────────────────────────
IMAGE 4  ▸  UPLOAD:  fig4-adoption-decay.png
CAPTION:  Your odds fall from 0.97 when almost nobody asks to 0.05 when everybody does.
──────────────────────────────────────────────────────────────────

I sell negotiation software, so let me be exact. That is a result about one kind of value: knowing something the other side does not. It has a shelf life, and it is the kind everybody sells on.

It says nothing about the other kind. I never measured how long a negotiation takes to resolve, or whether either side walks away believing the result was fair. Both are worth real money and neither depends on being unusual, so neither should decay this way. A tool that gets two parties to the same number in one round instead of five is worth as much at saturation as at one percent.

The arbitrage decays. Whether anything else does is a question I have not run.

## Why this is the only thing I work on

Everyone is waiting for the moment AI agents start negotiating on our behalf, and arguing about what happens when both sides have one.

Both sides do not have one. That is the actual condition, and rent is just where it has had the longest run. The software arrived on the seller's side first, because that is the side with a budget line for software, and it will arrive on the seller's side first in every other transaction you make.

The reason it wins is not that it is clever. **It is that it measures, and you guess.** It has a number for what losing you is worth. You have a blog post from 2016.

So the work is not building you an agent that outsmarts theirs. It is much duller than that. It is getting one honest number onto your side of the table, and making what you say checkable enough that the optimiser on the other side is obliged to respond to it.

That is the whole product, and it is finished.

It is at **snhp.dev/rent**. Four questions, thirty seconds, free, no account. Tell it your city, what you pay, what they are asking for, and how long you have been there. It gives you the number your building is actually getting, ranks what to ask for from the concession they will grant to the one they will not, drafts the message, and tells you to just sign when you have nothing, which is the part that makes it advice rather than encouragement.

It also carries its own self-audit on the page, including the adoption result above, which argues against using it.

That is the last thing worth saying about the software on the other side of your renewal. In ten years it has never once had to show you its work. This one has to.

*Twenty-six ways this could prove me wrong were written down before any code existed, then it was audited adversarially. Everything, including the results that died, is published with the code.*

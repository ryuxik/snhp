# I gave 3,000 space-crabs a landlord to find out who really has leverage over your rent

*Both sides of that question turn on a dollar figure. Neither figure has ever been measured. When I worked them out from scratch, they came out the same size.*

---

Right now, in most large apartment buildings in America, two things are happening at once.

The person signing a new lease this week is being offered a deal. Six weeks free, maybe, or a waived fee. Roughly two in five listings have something attached.

The person who has lived there three years, paid on time every month, and never caused anyone a problem is being asked for more.

This isn't a theory. It's in the earnings filings. MAA, Q1: new leases **−7.0%**, renewals **+5.4%**. Camden, Equity Residential, IRT, Essex: same quarter, same shape, running since 2024. Loyalty is priced as a weakness by every major apartment company in the country, simultaneously, on the record.

The obvious response is: so ask. And every article that tells you to ask runs the same arithmetic.

Your landlord wants $200 more a month, $2,400 over the year. If you leave, they eat a turnover: vacancy, paint, listing, screening. Everyone puts that at one to three months of rent. Five thousand dollars, give or take.

They're risking five to gain two. You have leverage and nobody told you.

I went looking for the source of that "one to three months."

**There isn't one.** It traces to a property-management blog that states it as a national average and cites nothing. The industry association's endlessly-recycled $1,000 to $5,000 traces to a 2016 blog post. The best actual survey, covering 4,666 properties and 1.09 million units, puts a turnover at roughly $2,000 to $4,000. Real, and smaller than the number the advice industry runs on.

Then I went looking for the other half of the arithmetic, the part about what it costs *you* to move.

That half is worse. **No government statistic exists.** The Census publishes how often people move. The BLS publishes a price index for moving services. Nobody official publishes what a move costs. The most-cited figure in the genre, $2,300, comes from a trade body that was absorbed into another organisation in December 2020, circulates with three mutually inconsistent values attached, and has no reachable primary document behind it. The two credible independent sources, one built from booked transactions and one from a consumer survey, land at $984 and $1,489.

So the sentence "they're risking five to gain two" is assembled from two numbers, and neither of them has been measured.

That bothered me enough to build a world.

Three thousand crabs rent habitats from stations. Every year a station makes a renewal offer, and a crab accepts, counters, or leaves. Stations pay to turn a habitat over. Crabs pay to move. Sixty years, seeded so it runs identically every time.

## Landlords should be folding twice as often as they do

The first result was not the one I went looking for. A station maximising expected value, doing the arithmetic properly with no sentiment in it, **concedes to between 43 and 50 percent of the crabs who ask.**

In the real world, about 22% of tenants who push back get something.

That gap runs the wrong way for the folk story. The model isn't saying landlords are tougher than you think. It's saying a landlord who ran the numbers honestly would give in about twice as often as landlords actually do.

The obvious explanation is bureaucracy. Nobody reads your email; a policy gets applied to a spreadsheet row; the exception queue is full. I built that, with a real capacity limit, and it doesn't close the gap at any queue size I can give it. Being an unread exception is a smaller effect than it feels like from the outside.

So the interesting question isn't the one the advice industry asks. It isn't *how do I make them move.* It's *why don't they move as often as their own spreadsheet says they should.*

## Asking works because of what it tells them

About 22% succeed, and that roughly doubles once you've been somewhere two years. There are two very different reasons that could be true. Either asking *selects* for the people who were leaving anyway, or asking *tells the landlord something it didn't already know*.

Those are separable, so I separated them. Selection moves the success rate by 0.002 to 0.072. Information moves it by 0.80 to 0.90.

It isn't close. **The ask is not the action. Being informative is the action, and asking is just the delivery mechanism.**

Which reorganises the advice. "I might have to move" is worth approximately nothing, because it's free to say and everyone can say it. Something a landlord can check is a different object entirely.

## The part that costs me something to publish

If the value of asking comes from asking being informative, then it comes from most people not doing it.

So I ran adoption from one percent to a hundred. Success falls from about **0.97 to about 0.05.** Monotone, in both a rising and a falling market.

The value of a negotiation tool is an inverted U. It peaks around 30% adoption and goes to nearly nothing at saturation.

I sell negotiation software. This is the shape of my own category, and it says the product is worth most in exactly the window where hardly anyone has it.

## So who actually has leverage

Back to the original question, this time with both numbers built up rather than borrowed.

The crab's cost of leaving, assembled from actually searching for somewhere else: **$2,960.** The station's cost of losing them: **$2,094 to $3,440.** Published landlord figures put a turnover at $2,000 to $4,000, and the best-sourced survey of property managers says $3,872 including lost rent.

Both sides of the folk arithmetic are low four figures. The five-to-two gap the entire genre is built on is not there.

Which side edges it depends on the cost of a physical move, which is the number nobody has measured. I fixed its plausible range in advance at $700 to $3,300, from the best sources that exist. The answer crosses over *inside* that range. At the central estimate, the runs span from "the landlord has twice the tenant's exposure" to "the tenant has 1.4 times the landlord's."

**Nobody can tell you who the weaker party is.** Not me, and not the person writing the negotiation guide. The measurement doesn't exist.

But the dollars were never the interesting part, and this is where the genre goes wrong at a level deeper than sourcing. Three thousand dollars is a per-unit line item against a portfolio for one party and a household budget shock for the other. **Equal dollars are not equal stakes.** You can lose a negotiation where the numbers are symmetric, because only one of you can afford to be wrong.

## Why a person building agent software spent a week on rent

Everyone is waiting for the moment AI agents start negotiating on our behalf. The interesting question is what happens when both sides have one.

That already happened. It happened in rent, years ago. Revenue-management software prices your renewal by estimating how likely *you personally* are to leave, from turnover cost, local comps, your tenure, your payment history. It runs on most large buildings. It updates daily.

On your side of that table: a hunch, and a bad feeling about confrontation.

The thing I wouldn't have guessed before building this is that the software's advantage isn't that it's clever. It's that it *measures*. It has a number for what losing you costs. You have a blog post from 2016.

And the second thing, which is worse for me than for you: a tool that closes that gap for everyone stops working, because what it exploits is being unusual.

---

*Twenty-six ways this could prove me wrong were written down before any code existed, then it was audited adversarially. Everything, including the results that died, is published with the code.*

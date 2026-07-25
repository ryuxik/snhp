# I gave 2,000 space-crabs a landlord to find out why you can't negotiate your rent

*The answer isn't that landlords are greedy. It's that asking only works while almost nobody does it, and I have the receipts on how badly that scales.*

---

Right now, in most large apartment buildings in America, two things are happening at once.

The person signing a new lease this week is being offered a deal. Six weeks free, maybe, or a waived fee. Roughly two in five listings have something attached.

And the person who has lived there three years, paid on time every month, and never caused anyone a problem is being asked for more.

This isn't a theory. It's in the earnings filings. MAA, Q1: new leases **−7.0%**, renewals **+5.4%**. Camden, Equity Residential, IRT, Essex: same quarter, same shape, running since 2024. Loyalty is priced as a weakness by every major apartment company in the country, simultaneously, on the record.

The obvious response is: so ask. Surely you just have to ask.

That's what I thought. So I did the arithmetic everyone does.

Your landlord wants $200 more a month, or $2,400 over the year. If you leave, they eat a turnover: vacancy, paint, listing, screening. Every tenant-advice article on the internet puts that at **one to three months of rent**. Five thousand dollars, give or take.

They're risking five to gain two. You have leverage and nobody told you.

I went looking for the source of that "one to three months."

**There isn't one.** It traces to a property-management blog that states it as a national average and cites nothing. Everyone else recycles it, occasionally laundering it through Statista on the way. The best actual survey, covering 4,666 properties and 1.09 million units, puts a turnover at roughly $2,000 to $4,000. Real, and smaller than the number the entire advice industry runs on.

That bothered me enough to build a world.

---

Two thousand crabs rent habitats from stations. Every year a station makes a renewal offer and a crab accepts, counters, or leaves. Stations pay to turn a habitat over. Crabs pay to move. Sixty years, seeded so it runs identically every time.

I expected to spend a week finding out *how much* asking is worth.

Instead I spent a week failing to make asking work at all.

## The wall

Here's what kept happening. I'd build a station that priced its renewals well. Not a cartoon villain. An operator maximising expected value the way real revenue-management software does. Then I'd have a crab counter.

And the station wouldn't move. Not out of stubbornness. Because it had no reason to.

A station sitting at its own optimum is, by construction, **indifferent at the margin.** It has already balanced the rent it gains against the chance you walk. So when a randomly-chosen crab pushes back, the station learns nothing it didn't already price in, and conceding is a straight loss.

I tried this six ways. I gave stations menu costs and an exception queue, the way a real manager with 200 units actually works: apply a policy, handle complaints. I expected countering to pay enormously, because the number you were sent was never about *you*; it's a rule applied to a spreadsheet row. Push back and a human finally reads your file.

It paid *worse*. Queues have a length. Most crabs who counter are never refused. They're **unread**. Being an exception only helps if someone has capacity to process exceptions, and at scale nobody does.

So then I had to ask the question I'd been avoiding.

## Why does asking ever work?

Because in the real world it does. Not always. About 22% of tenants who push back get something, and that roughly doubles if you've been there two years or more.

But if a rational landlord has no reason to concede to a random asker, what are those 22% doing?

The answer, once I saw it, reorganised everything: **they aren't succeeding because they asked. They're succeeding because of what asking revealed about them.**

An ask is only worth conceding to if it carries information: that this tenant has actually looked, actually has somewhere to go, actually might move. In my crab world, askers were chosen at random. So a counter was pure noise, and a station that ignored noise was correct to.

Which means the thing tenant-advice articles get wrong isn't the arithmetic. It's the object. **"Ask" isn't the action. "Be credible" is the action, and asking is just how you deliver it.**

So I gave the crabs a way to prove it.

Not a claim. Proof. A crab holding a real alternative could demonstrate it, at a cost. A crab without one couldn't fake it.

**10.2% off the offer.** One of the largest effects in the entire study, from the same stations that had ignored every unbacked counter I'd thrown at them for a week.

That's the finding, and it's uncomfortably specific: *"I might have to move"* is worth approximately nothing, because it's free to say and everyone can say it. *"Here is the unit, here is the rent, here is the date"* is a different object entirely.

## The part that should worry anyone building this

If the value of asking comes from asking being *informative*, then it comes from most people not doing it.

Sixty-one percent of renters never negotiate. That's not just a sad statistic about people leaving money on the table. **It's load-bearing.** It's why the 39% who do can be told apart from everyone else.

Which puts a tool like the one I built in an awkward position. Work well enough and you dissolve the signal you depend on. And in the runs, that cost doesn't fall on the people using the tool. It falls on everyone else: as more crabs counter, stations raise the *opening* offer for everyone, and the ones who counter recover more than the increase while the quiet ones absorb it.

That result survived every attempt to break it. It's on the page now, in front of the tool, because a person is entitled to know that before they use the thing.

## Then I gave the colony a plague

Demand collapses. Habitats empty out. Rents should fall, and mine did, and I expected the stations to follow them down.

They didn't. The station *held its rent and ate the vacancy*. Rent relative to market actually **rose** while a fifth of its habitats sat empty. What tripled instead was concessions: free months, waived fees, anything that wasn't the number on the lease.

Which is the same lesson as the credible-signal one, arriving from the other direction. **The number on the lease is the one thing a station will not move**, because that number follows the building forever: it sets the comparable for every future tenant, and on a large portfolio it's marked into the asset's value. Everything else is negotiable precisely because it evaporates.

So the advice that falls out isn't "ask for a rent reduction." It's: ask for the thing that doesn't leave a permanent mark, and prove you have somewhere else to be.

## Why a person building agent software spent a week on rent

Everyone is waiting for the moment AI agents start negotiating on our behalf. The interesting debate is what happens when *both* sides have one.

That moment already happened. It happened in rent.

Revenue-management software prices your renewal by estimating *your* elasticity, meaning how likely you personally are to leave, from turnover cost, local comps, your tenure, your payment history. It runs on most large buildings. It updates daily. It is, functionally, an algorithm negotiating against you.

On your side of that table: a hunch, and a bad feeling about confrontation.

So the asymmetry everyone is bracing for didn't wait for agentic commerce. It shipped years ago, quietly, inside the largest recurring expense most households have, with software on exactly one side. And the reason it works isn't that the software is clever. It's that most people never counter, and the ones who do mostly can't prove anything.

---

*A note on the machinery, since it's the part I'd want if I were reading this. Twenty-six ways this could prove me wrong were written down before any code existed. All three of the simulation's accuracy checks failed. It never did reproduce the rate at which real landlords concede, which is why nothing on my tool's page is quoted from it. Then I had it audited adversarially, on the assumption that every surviving result was an artefact until shown otherwise. Six were. Two of those had already shipped, including one where I'd told people the exact opposite of what the credible-signal result above shows. Both are corrected, and the full audit, covering every failure, every reversal, and the parameters each conclusion hinges on, is published alongside the code.*

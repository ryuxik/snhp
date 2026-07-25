# I made 2,000 space-crabs pay rent for sixty years. Then I gave their landlord my software.

*Somewhere in your building, someone who moved in last month is paying less than you are for the same apartment. That part isn't fiction. And it isn't an accident.*

---

Right now, in most large apartment buildings in America, two things are happening at once.

The person signing a new lease this week is being offered a discount. Six weeks free, maybe, or a waived fee. Roughly two in five listings have something like it attached.

And the person who has lived there for three years, paid on time every month, and never caused anyone a problem — that person is being asked for more.

Not by mistake. Every major apartment company reported this in the same breath last quarter. MAA: new leases down 7.0%, renewals up 5.4%. Camden, Equity Residential, Essex, all the same shape. Loyalty is priced as a weakness, and it's in the earnings filings.

The first time I properly understood this, my reaction was that somebody should tell renters. Because if a landlord is offering strangers a deal they won't offer you, surely you just have to *ask*.

So I did the arithmetic. Your landlord wants $200 more a month — call it $2,400 over the year. If you leave, they eat a turnover: vacancy, paint, listing, screening. Every property-management blog on the internet puts that at one to three months of rent. Four, five, six thousand dollars.

They're risking five thousand to gain two. You have leverage and nobody told you.

I published that. I built a free tool around it.

Then I built two thousand space-crabs to check, and the crabs took it apart.

---

The crabs rent habitats from stations. Every year a station offers a renewal and a crab accepts, counters, or leaves. Stations pay to turn a habitat over. Crabs pay to move. Sixty years of this, seeded so it runs identically every time.

Before writing any of it, I wrote down twenty-six specific results that would prove me wrong — because I have learned, expensively, that otherwise I find what I came for.

Nine of them fired.

## The first thing to die was my arithmetic

The "one to three months" figure has no source. I traced it to a property-management blog that states it as a national average and cites nothing; everyone else recycles it, occasionally laundering it through Statista. The best real survey — 4,666 properties, 1.09 million units — puts a turnover at roughly $2,000–4,000. Real, and smaller than advertised.

Worse, my framing was backwards. I'd compared a certainty to a tail. The landlord isn't choosing between "collect $2,400" and "lose $5,000" — they're choosing between a rent increase that *probably* sticks and a small increase in the chance you leave. And that chance barely moves: in 2022, operators pushed renewals up 10.7% and retention hit a *record*. People absorb increases and stay. A landlord also doesn't lose the turnover cost, they lose its *timing* — you leave eventually.

So the crabs killed the thesis I'd published. Fine. That's what they were for.

Then it got worse.

## I was sure the answer was bureaucracy. It's worse than bureaucracy.

Here's what I was confident about going in — confident enough that I wrote it down as a prediction before running anything.

Nobody optimises your apartment. A property manager holding two hundred units does not sit down and work out the profit-maximising renewal for unit 4C. They set a policy — everyone gets six percent — and then they deal with the people who complain.

Which means countering should pay enormously, for a reason that has nothing to do with leverage or game theory. **The number you were sent was never about you.** It's a rule applied to a spreadsheet row. Push back and you move off the spreadsheet and into a queue, where a human being finally looks at your particular file.

That felt obviously right. It's how every large organisation works.

So I built it: blanket increase, plus a finite queue for crabs who pushed back.

Countering got **worse**. Success fell from about 13% to under 4%.

Because queues have a length. Most crabs who counter are never reviewed at all — not refused, not weighed and turned down. **Unread.** Your objection joins a stack, the stack doesn't clear, and the deadline arrives anyway. Being an exception only helps if someone has capacity to process exceptions, and at scale nobody does.

So bureaucracy isn't the mechanism that makes asking work. Bureaucracy is a reason asking fails.

Then I found the thing that *did* work, and I hadn't predicted it at all.

I gave the station a leasing agent — someone paid on occupancy rather than on profit. Not a different model of the building's economics. A different person, with a differently-shaped bonus.

It was the only single mechanism in the entire study that moved the institution toward how landlords actually behave in the real data. Eight points on its own, where risk aversion, comp quality, portfolio size and menu costs had all done nothing.

Which quietly reframes the whole exercise. When you counter a renewal you are not negotiating with a building, or a pricing model, or an owner's balance sheet. You are negotiating with **whoever opens the email** — and whether you get anything may depend less on the economics of your unit than on how that person's bonus is calculated.

Nobody's tenant-advice article says "find out how your leasing agent is compensated." Mine now sort of does.

## Then I did the experiment I'd been avoiding

Here is the thing I build for a living. It's a negotiation engine — you give it what you care about, it infers what the other side cares about from what they've offered you, and it finds the package that clears for both.

It is symmetric. Nothing inside it knows which side of the table it's on.

I had been thinking of it as a tool for the person without one. That is, I now realise, a story I was telling myself, and it took me an embarrassingly long time to run the four-cell version of the experiment: neither side has it, the crab has it, **the station has it**, both.

The crab holding it gains **$298 a year**.

The station holding it gains **$2,642**.

That's 8.5×. But the number that actually stopped me was the fourth cell. When *both* sides have it, the total is $2,646.

The crab's copy added **four dollars**.

Once your landlord has a negotiation engine, you having one is worth approximately nothing. Not because they use it against you — because they get there first, and there's only so much room in a deal.

Two honest notes, because this isn't a simple villain story. The crab *is* better off in that cell — the engine finds genuine deals, joint surplus rises about 4–6% of annual rent, and fewer renewals collapse into turnover. It creates value. It just hands about ninety percent of it to whoever brought the software. And the second note is the uncomfortable one: I sell to businesses. A property-management company is exactly the customer I'd court. An individual renter is not.

I nearly missed this entirely. My first version let the station's engine only *reply* — and since a crab's asks are almost never granted, the engine had nothing to do. That cell came out bit-identical to the control and the result read "no effect, +$3." Letting the station *open* with a package — obvious behaviour for anyone holding a negotiation engine — moved it to +$2,642. The finding was hiding behind my own defect.

## Twice, the result I wanted was a bug

The number I most wanted was the 2026 inversion. Every major apartment REIT is currently cutting rents for new tenants while raising them for renewing ones — MAA reported −7.0% and +5.4% in the same quarter. I wanted my crabs to produce that pattern from first principles, because then the story would rest on my own mechanism instead of on somebody's SEC filing.

It fired. Renewal growth +3.2%, new lets −5%. Exactly the shape.

Then, chasing an unrelated table, I found that the station was building its renewal offer from each crab's **private moving cost** — price-discriminating on a number no landlord can observe. That fabricated the whole pattern. Restricted to what a station can actually see, renewal growth went to −0.64% and the pattern vanished.

Later I claimed the mechanism was the *shape* of the tenant's deadline: a landlord's cost of delay is linear (another empty month, forever) while a tenant's is a cliff (secure a home before the lease ends or face emergency housing). Elegant. I asked for it to be tested by swapping the cliff for a straight line with the same average.

Shape accounted for **13%**. The other 87% was just the *level* of the delay cost. My elegant mechanism was mostly decoration.

Three times I built a route to the answer I wanted. Three times it was me.

## Three gates, and I failed all of them

I'd committed in advance that the simulation had to reproduce known reality before any of its counterfactuals counted: the observed rate at which landlords concede, observed retention, and the observed new-let/renewal split.

**Gate 1 failed.** My stations conceded to nobody, because a station sitting at its own optimum is indifferent at the margin and a counter from a random crab tells it nothing.

**Gate 2 failed, and this one I want to underline** — it was the experiment I was most confident about. Small landlords behave distinctively in the real data: about 18% refuse to raise rent at all, and roughly 90% never offer a concession. I'd hardcoded that, which is worthless, so I rebuilt it to *emerge* from primitives — a five-habitat station is far more exposed to one vacancy than a two-hundred-habitat one, sees worse comps, and values a known tenant personally.

Nothing emerged. Institutional pushes came out at 10.60–10.61% across **all six ablations**. Risk aversion: inert. Comp noise: inert. Everything: inert. Both stations solve the same problem and portfolio size doesn't change the answer. The paradox I'd "found" earlier was just the thing I'd typed in.

**Gate 3 failed by three-tenths of a percentage point.** On the third attempt the sign pattern finally emerged honestly, with no information leak. Then the bridge check — does the endogenous market agree with the fixed-price version on retention — missed its band by 0.3pp. I'd written "no loosening" into the pre-registration, because a bar that moves after a failure isn't a bar. So it's a failure, and I stopped building. That was also pre-committed: no seventh mechanism.

**I cannot reproduce the 2026 rental market from primitives.** The claim in my article rests on the earnings filings and nothing of mine.

## Interlude: crab flu, and the AI crab migration

Two things I ran purely because they were fun, and labelled exploratory so they can't be promoted to evidence later.

**Crab flu.** Demand collapses; habitats empty out. I expected rents to fall and tenants to gain. The institution *held rent and ate the vacancy* — rent relative to market actually **rose**, retention didn't budge, and vacancies doubled. What tripled was concessions: 24% → 72%. Leverage in a collapse arrives as free months, never as a lower number on the lease. And the mom-and-pop — the best landlord to have in normal times — was the *worst* in a collapse. Retention fell a third, because it neither cuts rent nor offers concessions. It just loses tenants.

**The AI crab migration.** Rich crabs arrive in a few stations, then a chunk of them leave abruptly. The boom is *good* for incumbents, because renewal caps mean their rent can't chase the market: market rents rose 62% while pushes stayed capped at 12%, so sitting crabs fell behind the market and clung on. Against a small station they ended up paying 85% of market with surplus genuinely positive.

Then the exodus, and it inverts in a single year. Retention halves. Incumbent surplus hits its worst point in the entire run. And the migrants — the ones who arrived at the peak — take the worst of it and are *still* taking it five years later.

## What actually survived

Five things, and they are worth more to me than the story I set out to tell.

**The engine works, and for the right reason.** Negotiating over four terms at once beat negotiating over rent alone by about $950 a year — roughly twice my pre-registered bar — and it beat the hand-rolled version I'd been using as a stand-in. It wins by *finding deals that exist*: agreement rates went from 5% to 17%, and from 20% to 72% in a soft market, while turnover **fell**. It isn't extracting harder. It's finding the package both sides would have accepted.

**Answer immediately.** A crab who let a three-month response window lapse was offered 13.3% more relative to market and ended **$645 a year** worse off than an identical crab who replied at once. The delay was assigned randomly, so this is causal, not "punctual people negotiate better." This is now the first thing my tool tells you.

**Shopping around doesn't get you a better offer.** I was ready to make "line up an alternative first" the headline advice. It's worth $17 a year, against a $480 bar — because your landlord cannot verify your alternative, so you get the same terms either way. It buys you the ability to leave. It does not buy you a discount. My tool now says that instead of implying the opposite.

**For about one renter in six with the cheapest moves, the right answer is "leave," not "negotiate."** That only became visible after fixing a survivorship bug where I'd been measuring only the crabs who stayed.

**And the one that nearly got away.** In one arm the tool looked worth **+$3,700 a year** per crab who used it. On an identical population it was **−$244**. The entire apparent benefit was selection: the crabs who ask are not like the crabs who don't. I only caught that because I'd pre-registered the identical-population comparison. Without it I'd have published $3,700 in good faith.

## Why any of this matters outside a crab colony

Everyone is waiting for the moment AI agents start negotiating on our behalf. The debate is about what happens when both sides have one.

That moment already happened. It happened in rent.

Revenue-management software prices your renewal by estimating *your* elasticity — how likely you personally are to leave — from turnover cost, local comps, your tenure, your payment history. It runs on most large buildings in the country. It updates daily.

It is, functionally, an algorithm negotiating against you.

And on your side of that table: a hunch, and a bad feeling about confrontation.

So the asymmetry everyone is bracing for didn't wait for agentic commerce. It shipped years ago, quietly, inside the largest recurring expense most households have — with software on exactly one side. And the thing that makes it work isn't that the software is clever. It's that most people never counter at all.

I built the other side and gave it away free.

Then I measured what happens when the side that already has software gets mine too, and the answer was 8.5×.

That is not a reason to stop. Joint value went *up* in every cell — fewer deals collapsed, less money burned on turnover, both sides better off. The engine finds deals rather than extracting them.

It is a reason to say the split out loud, on the page, before anyone uses it. Which is where it now is.

---

*Every number here comes from a pre-registered simulation: kill conditions and validation gates written before the code existed, amendments dated and labelled, failures left in place. Eighty tests. All three gates failed. The five findings above are what survived, and the write-up includes every correction, including the four times my own measurement error ran in the direction of a better story.*

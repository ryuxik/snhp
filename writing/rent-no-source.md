# Every landlord blog says turnover costs 1–3 months' rent. I couldn't find a source.

I set out to prove that renters have leverage at renewal. I was wrong twice
before I found something real, and the something real came out of SEC
filings rather than out of my model. Here is the whole path, including the
parts where my own numbers killed my own thesis.

## The claim I started with

The argument is everywhere, and it sounds airtight. When your landlord
pushes your rent up $200/month, they gain $2,400 over the year. If you
leave, they eat a turnover: vacancy, cleaning, paint, listing, broker fee,
screening. Every property-management blog puts that cost at **one to three
months of rent** — call it $4,000–6,000 on a $2,000 apartment.

So the landlord is risking twice what they stand to gain, and the tenant
holding that leverage has no idea. Beautiful. I started building a tool
around it.

## Wrong the first time: the number has no origin

I went looking for the primary source on "1–3 months." The best actual
data is the **NAA/IREM/BOMA Income/Expense IQ** survey — 4,666 properties,
1.09 million units, 109 metros. It lets you decompose the folk number
instead of trusting it:

- **Leasing expense: $292/unit/year.** At ~47% annual turnover that's
  roughly **$650 of real marketing-and-leasing cash per turn** — not
  thousands.
- **Vacancy and rent loss: $1,323/unit/year** → ~$2,900/turn, but that
  line also contains concessions and bad debt, so it overstates pure turn
  vacancy.
- **Make-ready is largely capitalized**, which is exactly why blog
  estimates and accounting figures never reconcile: one is counting an
  expense, the other is counting an asset improvement.

Triangulating: **~$2,000–4,000 per turn, roughly 1–2 months of rent.**
Real, meaningful, and smaller than advertised.

The "3 months" top end I traced to a single property-management company's
blog, which asserts that "the national average cost of a turnover is equal
to three month's rent" and cites **nothing**. No survey, no study, no
data. Other vendor blogs then recycle it, occasionally laundering it
through "Statista." It is a citation chain with no origin, and it is the
number the entire tenant-advice internet runs on.

## Wrong the second time: my arithmetic was backwards

Worse than the inflated number, my framing was wrong. "Gains $2,400,
risks $5,000" compares a **certainty** to a **tail**. The landlord's
actual calculation is:

```
E[push] = ΔRent × P(stays) − TurnCost × ΔP(leaves)
```

The load-bearing term is **ΔP(leaves)** — the *marginal* increase in
departure probability caused by the increase — not baseline turnover. And
the empirical elasticity is brutal for my thesis:

**In the twelve months to April 2022, operators pushed renewals +10.7%
and retention hit a record 57.3%.** Tenants absorbed double-digit
increases and stayed in record numbers. The threatened risk simply did
not materialize. 2025 repeated it: analysts expected supply and
concessions to crush retention, and retention rose anyway.

And the deeper problem: **a landlord doesn't lose the turn cost, they
lose its timing.** You leave eventually. The true cost of pushing is the
discounted acceleration of a cost already on the schedule, which is far
smaller than the gross figure.

Moving costs, application fees, and deposit friction all suppress
ΔP(leaves) further. My thesis was dead.

## Then the regime flipped

Here is the part that survived, and it comes from audited earnings
releases rather than from anybody's model.

Every major US apartment REIT is currently reporting **negative new-lease
rent growth alongside positive renewal growth, in the same quarter, in
the same buildings.** Q1 2026:

| Operator | New lease | Renewal | Spread |
|---|---|---|---|
| MAA (~102k units) | **−7.0%** | **+5.4%** | 12.4 pts |
| Camden | −5.2% | +2.9% | 8.1 pts |
| Equity Residential | −2.8% | +4.7% | 7.5 pts |
| IRT | −4.0% | +3.2% | 7.2 pts |
| Essex | −1.2% | +3.9% | 5.1 pts |

MAA's series runs unbroken: FY2024 −5.9%/+4.4%, FY2025 −5.8%/+4.6%,
Q1 2026 −7.0%/+5.4%. The person signing the identical floorplan down the
hall is often paying **less** than the tenant who stayed.

**And this is what rescues the thesis from the elasticity objection.** The
low elasticity was measured in the *opposite* regime. In 2022,
loss-to-lease was positive — sitting tenants were paying *below* market,
so leaving meant paying *more*. Of course they stayed; their outside
option was worse. In 2026 that has inverted: the outside option may now
be *better* than the renewal offer. **Elasticity estimated under one
regime cannot be projected into its inverse.**

Concessions corroborate it. About **39.7% of Zillow rental listings**
advertised a move-in deal in June 2026, up from ~1 in 6 pre-pandemic, and
RealPage puts the average discount near **11%, about six weeks free**
where offered. Denver 68.3%. Charlotte 66.6%. Dallas 64.2%. Austin 63.8%.
Meanwhile New York sits at 18.4% and Buffalo at 11.1% — the leverage is
extremely local.

## The void nobody has filled

Then I went looking for the obvious question: **when tenants do ask, what
happens?**

- **There is no academic literature on US residential renewal
  bargaining.** I searched for it directly. What exists is commercial-
  lease information-asymmetry work and landlord-tenant energy-efficiency
  papers. The residential negotiation question is simply unstudied.
- **Zillow's Consumer Housing Trends Report** — 21,000+ renters, five
  nationally representative surveys — is the largest renter survey in the
  country. I pulled the PDF and searched it. It **never asks whether you
  negotiated.** It asks about application fees, deposits, and tour counts.
- The only substantive numbers trace to **a single 2022 Avail survey
  analysed by the Urban Institute**: 39% of tenants facing an increase
  tried to negotiate; 22% got a smaller one. And the one finding that
  matters most — **success roughly doubles with tenure: 26–27% at 2+
  years versus 14–15% under two.**
- **Nobody has measured what landlords concede** — rent versus free month
  versus waived fee versus term. That composition is unrecorded.

So: the cost side is documented obsessively, because it is the landlord's
P&L. The *concession* side is a blank. The asymmetry isn't just in the
market; it's in the evidence base.

One landlord-side quote is worth the whole search. Essex's CEO, Q1 2026
earnings call, on renewal increases going out around 5%: *"Of course,
that can get negotiated, but so far, our renewals have been pretty darn
sticky."* Sticky, when 61% of tenants never try.

## What I built, and the thing that made it worth building

A free tool: [snhp.dev/rent](https://snhp.dev/rent). Four questions —
city, current rent, offered rent, how long you've lived there. It returns
your odds, what to ask for ranked **easiest-to-hardest for a landlord to
approve**, and a message to copy.

That ranking is the one genuinely useful thing I learned. **Headline rent
is the hardest possible ask**, because it resets the comparable for the
entire building. A free month doesn't. A waived pet fee doesn't. A
24-month term at a blended rate doesn't. Almost every tenant opens with
the hardest ask and takes the no.

It will also tell you that you have no leverage and should sign. In a
tight market with short tenure, that's the correct answer, and a tool that
always finds leverage is a horoscope.

Everything above is published research and earnings filings. The tool
launched with zero users and zero outcomes of its own, and the page says
so.

## Why a negotiation-engine project ended up here

I don't work on rent. I work on [SNHP](https://snhp.dev), a negotiation
engine for AI agents — deterministic, LLM-free in every judgment path,
multi-issue, and it signs a receipt for every recommendation so a third
party can check it.

Rent renewal turned out to be the cleanest available instance of the
problem that engine exists for.

Revenue-management software already prices your renewal by estimating
**your elasticity** — its guess about whether you'll leave. It takes as
inputs the competitive asking rents, the turn cost, and your tenure and
payment history. It runs on every large building. It is, functionally, an
algorithm negotiating against you.

You have a hunch and an awkward feeling about confrontation.

That is the agent-versus-human asymmetry everyone expects from AI agents,
except it already shipped, quietly, in the largest recurring expense most
households have. And the mechanism that makes it work is not
sophistication — it's that **61% of people never counter.** A resident who
never counters is, to the model, inelastic. Countering is itself the
signal the model is waiting for.

So the tool isn't a detour from the thesis. It's the thesis at human
scale: give the amateur side of a structurally asymmetric negotiation the
thing the professional side already has. The version where both sides are
agents is coming. This one is just the version that's already here, with
only one side armed.

---

*Sources: NAA/IREM/BOMA Income/Expense IQ; MAA, Camden, Equity
Residential, IRT and Essex Q1 2026 earnings releases and calls; Zillow
Rental Report June 2026 and Consumer Housing Trends Report 2024; RealPage
concessions data June 2026; Avail survey via the Urban Institute (2022).
Where a figure below carries no primary source, I've said so rather than
repeat it.*

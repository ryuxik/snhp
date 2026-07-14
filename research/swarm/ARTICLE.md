# We gave 24 mining drones an economy. Then we tried to kill the results.

*How a walk-and-an-idea about robot swarms turned into four pre-registered
experiments, three demolished headlines, one law of robot economics, and the
best argument yet for teaching machines to haggle.*

*[HERO IMAGE: side-by-side race frame — two identical asteroid fields, the
bargaining fleet at 120/120 ore while the auction fleet sits at 114, dead
drones marked ✕]*

---

## The idea you have on a walk

Slime mold can find the shortest path through a maze. It builds transport
highways between food sources that look eerily like the Tokyo rail map. No
brain, no boss — just simple local rules.

Robot swarm research has spent twenty years chasing that trick: many cheap
robots, simple rules, emergent competence. And it works, for the things
rules are good at.

But watch the ant-like methods closely and you notice what's missing.
When one robot has a full battery and an empty cargo bay, and its neighbor
has a full cargo bay and a dying battery, the rulebook has nothing good to
say. The standard fixes are charity (share energy when a threshold trips) or
auctions (whoever can do the task cheapest, does it). Both negotiate exactly
one thing at a time.

Real deals aren't like that. A real deal sounds like: *"I'll take your two
crates because I'm efficient and you're nearly dead — and in exchange you get
a quarter of my battery and my mining claim on the near asteroid."* Three
things traded at once, everyone better off, no manager anywhere.

We build negotiation software (snhp) — math that finds those multi-part
deals between self-interested parties. The walk-idea was simple: **what
happens if you drop that into a robot swarm?**

## Step zero: has anyone done this?

Before building anything we ran a deep literature sweep with adversarial
fact-checking — every claim independently verified by three reviewers trying
to refute it. The result surprised us: in forty years of multi-robot
research, "negotiation" always means *one-dimensional* negotiation. Auctions
bid a single price. "Combinatorial" auctions bundle *tasks*, never *issues*.
Robots that share battery exist (it's called trophallaxis, like ants
regurgitating food for each other) — but it's threshold charity, never a
deal. The multi-issue negotiation community, meanwhile, has spent fifteen
years on disembodied economic scenarios and never once wired their math into
robot-to-robot coordination.

An open niche, verified. So we built the world.

## The world

A 32×32 field. Two asteroids with 60 units of ore each, a refinery, one
solar charging dock with two plugs, and 24 drones that differ in battery,
motor efficiency, and cargo capacity. Moving costs energy. Loaded moving
costs more. Hit zero battery far from the dock and you're adrift — cargo
stuck, mission over, unless someone tops you up.

Every drone runs the same simple driving rules. The only thing we vary is
what happens **when two drones meet**:

- **Rules fleet:** threshold charity (the literature's answer).
- **Auction fleet:** charity + hand cargo to whoever can deliver it cheapest
  (the classic market-robotics answer).
- **snhp fleet:** enumerate every possible bundle — cargo × energy × mining
  rights — score each side's outcome, and strike the Nash bargain: the deal
  both sides provably prefer to walking away.

## The first result, and why we hired assassins

Version zero looked spectacular. The bargaining fleet won on our efficiency
metric at every heterogeneity level, p < 0.05, headline ready.

Then we did the thing we now think every simulation project should do: we
commissioned a hostile review of our own result, with instructions to kill
it. The reviewer reproduced all 88 runs bit-for-bit… and then demolished the
paper we would have written.

The efficiency metric was delivered-ore *divided by energy drawn* — and dead
robots stop drawing energy. In one run, the bargaining fleet stranded **all
24 drones**, delivered *less* ore than the auction fleet, and our metric
scored it a 5.8× win. We had invented a statistic that gave a perfect score
to killing the entire swarm.

*[IMAGE: the autopsy frame — 24 grey ✕ drones, caption "our metric called
this a 5.8× win"]*

It got worse. The reviewer built a trivial control we hadn't: drones that
just cooperate greedily — no bargaining, no game theory, same information —
and it beat our fancy Nash machinery on every number. And our cleanest
ablation ("bargaining over cargo alone ties the auction!") turned out to
describe an arm that had struck **zero deals**. A mechanism that does
nothing, tying a weak baseline, on a broken metric.

Three headlines, three corpses. Here's the part that kept the project alive:
buried in the wreckage was a result better than the one we lost.

## Barter needs bundles

Why did cargo-only bargaining strike zero deals? Because between
self-interested parties, **no single-issue trade can make both sides
better off** in this world. Handing over cargo is a pure loss to the giver.
Sending energy loses 25% in transit — a guaranteed joint loss. Every
one-dimensional offer dies at the door.

Bundle the issues and trade explodes into existence: cargo *for* energy
*for* mining rights. In our final sweeps, 96–99% of every deal struck was
multi-issue, because those were essentially the only deals that *could* be
struck. One exception emerged, and it's poetry: a nearly-dead drone will
give away its cargo for nothing — jettisoning weight makes every step
cheaper. The only one-issue deal in the economy is a distress sacrifice.

That's the real theorem the swarm taught us: **for self-interested machines,
bundling isn't a nice-to-have — it's the difference between an economy and
silence.** Auctions can't say "I'll take your crates if you cover my
sector." Bargaining can.

## The market that let robots die

Rebuilt honestly (delivered ore as the metric, strandings counted, killer
controls included), version 2 produced our favorite finding by accident.

The bargaining fleet delivered dramatically more ore — and stranded twice as
many robots. When we traced why, the pattern was brutal: a Nash deal
requires both sides to gain. A broke robot — no cargo, no useful position,
nothing to offer — cannot pay for rescue. **The market let the destitute
die.** Loaded robots got rescued constantly (they could pay!). Empty ones
were left to go dark. Meanwhile the charity rule saved everyone
indiscriminately… including robots not worth saving, at a 25% energy tax per
transfer.

So we tried the obvious hybrid: bargaining for everything, plus an
unconditional rescue floor. That fleet delivered 119.6 of 120 units with
1.3 robots stranded — beating pure charity, pure auctions, *and pure
central cooperation*. Markets plus safety nets beat both socialism and
laissez-faire, in a sandbox with no politics in it at all.

## Insurance requires diversity

A colleague-grade question came next (from the project's human, on
another walk, roughly): *why does the market need a bolted-on safety net at
all? Shouldn't correctly-priced risk handle rescue?*

So we rebuilt the drones' self-valuation: instead of feeling danger only
when already doomed (a cliff), each drone continuously prices its
probability of stranding — and can therefore buy survival *while still
solvent*.

The result split cleanly in two, and we'd pre-registered the kill condition
so we couldn't fudge it. In **homogeneous** fleets, risk-pricing did nothing
— when everyone carries the same risk, there's no cheap counterparty to buy
safety from; the safety net stayed essential. In **heterogeneous** fleets,
risk-pricing beat everything, including the previous champion — and the
safety net flipped to actively harmful, a redistribution tax on differences
the market was already pricing.

One line: **risk markets work when risk differs; safety nets work when it
doesn't. Insurance requires diversity.** Our v3 idea "failed" as a universal
fix and produced a law instead.

## Two companies, one border

Then we made it commercial. Version 4 split the swarm into two companies,
12 drones each, each with **its own refinery**. Refining at the rival's
refinery costs a tariff. Now individual rationality isn't a modeling
choice — it's physics: cargo handed across the company line converts to the
*other* company's revenue, so uncompensated cross-company "helpfulness" is
measurable corporate charity.

Before running it, we sent the experimental design to a three-lens expert
panel (a market-design economist, a robotics methodologist, a red-teamer) —
and they gutted it, pre-emptively this time. Two of our headline predictions
were tautologies (our code *enforced* them). Our tariff grid started above
the price where all the action lives — they derived the choke point,
τ* ≈ 0.16, from our own physics. Cheaper to be wrong before the sweep than
after.

The redesigned experiment paid for its rigor on day one. We'd built the map
perfectly mirror-symmetric with mathematically identical twin fleets, so
that any systematic difference between companies **must be a bug**. The very
first sweep flagged one: Company 0 kept winning inside the "merged company"
arm. The cause was one line — a tie-breaking `argmax` that, when two deals
scored exactly equal, always picked the first… which, through two more
innocent conventions, silently routed tied cargo toward lower robot IDs.
All of which belonged to Company 0. A placebo test designed on principle
caught a bias we didn't know we'd written.

*[IMAGE: demand-choke chart — foreign refining volume vs tariff, cliff at
the derived τ*]*

The clean results:

- The tariff demand curve **chokes exactly where the algebra said it
  would** — and fleet diversity smooths the cliff into a proper curve.
- Selfless cross-border donations are *net harmful*: the auction fleet does
  better with company walls up. The bargaining fleet needs no walls,
  because every border crossing is already paid for. **Individual
  rationality is the company discipline.**
- The headline: a full merger of both fleets outperforms two firms that
  bargain at the border by **almost nothing** (0–5 units, mostly noise).
  **Two companies with a negotiation layer at the boundary ≈ one merged
  company.** You don't need to consolidate fleets. You need better deals
  between them.

## Who sets the price of refining?

One experiment left. A tariff someone *picks* isn't a price — it's a
parameter. So we asked: if each company posts the refining fee that
maximizes its own toll revenue, where does the price settle?

For fleets that can't bargain, a textbook answer appeared: a clean interior
monopoly price (τ* = 0.20 — just above the point where most drones switch
to hauling home, squeezing the stragglers who have no choice). And the
market price is only *well-defined* when the fleet is diverse: identical
drones produce a jagged, cliff-edged revenue curve; heterogeneous drones
smooth it into a proper peak. Even price theory needed diversity.

Then the punchline. Facing a **bargaining** fleet, the revenue-maximizing
posted price barely moves… but the money collected at it **drops by
roughly 60%**. The bargaining drones don't negotiate the tariff down — they
never talk to the refinery at all. Their internal deals quietly keep cargo
in the hands of whoever can refine it at home. The toll booth keeps its
sign; the traffic reroutes around it.

*[IMAGE: two revenue curves, null fleet vs bargaining fleet — same peak
location, one-third the height]*

If you own infrastructure and your customers learn to negotiate with each
other, your price survives. Your pricing *power* doesn't.

## What this was actually about

None of this is really about asteroid drones. Swap "refinery access" for
"API access," "battery" for "compute budget," "cargo" for "a delivery job,"
and you have the economy that's assembling itself right now between AI
agents that buy, sell, schedule, and route on our behalf. The protocols
being drafted for that world (agent payments, agent commerce) currently
speak *checkout*: fixed price, take it or leave it — exactly the
one-dimensional language our auction fleet spoke.

Four experiments' worth of robots say one-dimensional isn't just
suboptimal; between self-interested parties it's barely an economy at all.
The value was in the bundles, the priced risk, the compensated border —
in *negotiation as infrastructure*.

That's the thesis we sell (the same engine that ran these drones runs our
commercial negotiation tools), but the sandbox findings stand on their own:

1. **Bundling is what makes machine-to-machine trade possible at all.**
2. **Markets need safety nets — until participants differ enough to price
   risk; insurance requires diversity.**
3. **A negotiated border is worth about as much as a merger.**
4. **And your simulation is lying to you unless you pay someone to kill it.**
   Every result above survived a pre-registered kill condition, a hostile
   reproduction, or a placebo trap. The three that didn't survive are in
   the repo too, labeled as corpses.

*Watch the fleets race live (same asteroids, same robots, different
economics): arena.snhp.dev/swarm.html*

*[FOOTER IMAGE: rescue-trade close-up — grey drone, incoming cyan+amber
arcs, caption "2▣ ⇄ 8⚡ — the market saving someone who can pay"]*

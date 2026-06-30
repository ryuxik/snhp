# Agents are about to negotiate everything. They're terrible at it.

Within a few years, agents will buy, sell, procure, contract, and settle on our
behalf — millions of times a day. Every one of those is a negotiation: a price, a
term, a tradeoff. Negotiation is about to become as common for agents as a database
query. The category barely exists today. It's about to be enormous.

And today's agents are **bad at it**. An LLM negotiating by vibes doesn't model the
other side's reservation value or compute the equilibrium move — it just sounds
confident. So we measured it. Give an LLM a strong, production-grade negotiation
prompt, and the *same* LLM holding the SNHP tool still beats it: **+0.077 utility,
95% CI [+0.039, +0.115], 8/12 paired seeds, zero losses.**

We're leading with the *modest* number on purpose, because everyone else would tell
you 10×.

**That honesty is the product.** The agent-tooling world is drowning in 10× claims.
We publish our losses. Our multi-issue tool's headline isn't "40% better" — it's
"the priority inference adds about 1% over no inference, and here's the script to
check it yourself." Our tournament rank isn't "#1 of 21" — it's "#1 in the
asymmetric markets, 5th in the symmetric one." If you're going to put an agent in
charge of your money, trust the tool that shows you exactly where it's weak.

## What SNHP is

The negotiation layer for the agent economy:

- **Plain dollars in, the math-optimal move out.** No game theory, no LLM, no setup.
- **Single-price *and* multi-issue** — it logrolls across linked terms (price, equity,
  SLA, seats) by inferring the other side's priorities.
- **A verified agent-to-agent flow** with signed, settleable AP2 deal records — so when
  two agents transact, the outcome is provable, not just asserted.

It's **LLM-free** (your agent brings the LLM; we bring the math), so it runs locally,
costs nothing to call, and can't be milked. It's **Apache 2.0**. One line:

```bash
uvx snhp     # your agent negotiates measurably better
```

## The bet

We might be early — maybe too early. Good. When agents negotiate trillions, someone
will own the layer that makes them good at it. We're betting the **honest** one wins —
because the moment real money is on the line, "trust me, 10×" stops being enough.

The math is open. The losses are published. The category is empty. Come build the
thing that makes agents stop negotiating like amateurs.

— [snhp.dev](https://snhp.dev) · [github](https://github.com/ryuxik/snhp) · `pip install snhp`

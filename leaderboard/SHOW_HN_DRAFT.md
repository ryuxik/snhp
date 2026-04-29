# Show HN draft — fill numbers from leaderboard.json once bracket lands

## Title (under 80 chars)
Show HN: gametheory-mcp – Equilibrium-aware primitives for AI agents

(or: "Show HN: An MCP server that makes LLMs negotiate like game theorists")

## URL
https://snhp.dev

## Text (HN keeps this short — aim ~150 words)

LLMs are structurally bad at multi-round, opponent-modeling, equilibrium-aware games. They forget what was offered three turns ago, anchor on irrelevant numbers, and concede on a ramp instead of the Pareto frontier. Game theory has closed-form answers for most of these problems — Rubinstein 1982 for bargaining, Myerson 1981 for auctions, Gale-Shapley for matching — and they've been ignored by the agent stack.

`gametheory-mcp` is a tiny Python package that hands these primitives to your agent over MCP. `pip install gametheory-mcp`, point Claude Desktop / Cursor / VS Code at it, and the agent now has 10 tools across negotiation, auctions, and mechanism design.

I ran a 23-agent NegMAS round-robin to validate it. **[FILL FROM LEADERBOARD]**: Gemini Flash 2 alone (vanilla) captures X% of surplus in symmetric markets. Same Gemini Flash with the math primitives in-prompt captures Y%. Across 3 market conditions, the math layer wins 2 of 3 outright.

Math is open (Apache 2.0). Telemetry corpus is opt-in. Source + leaderboard JSON + repro instructions: https://github.com/ryuxik/gametheory-mcp

## Talking points for comments
- **"NegMAS isn't a familiar benchmark"**: yes — that's why the comparison is *against an LLM*, not "rank in NegMAS." The LLM is the reader's reference point.
- **"Why not just train the LLM better?"**: closed-form math is faster, deterministic, and verifiable. Training a Sonnet to do Rubinstein takes weeks; including Rubinstein's solution in the prompt takes 30ms.
- **"What's the moat?"**: the math is textbook. The moat is the per-vertical priors corpus that grows with opt-in usage. Right now it's empty — early users seed it.
- **"Why MCP and not just an HTTP API?"**: both ship. MCP is for in-process agents that don't want a network hop on every tool call. API is for production servers that want the calibrated tuning + first-strike attestations.
- **"Reasoning ON vs OFF in the comparison"**: ran both. Vanilla Gemini Flash with reasoning AUTO captures X1%, with reasoning OFF captures X2%. Scaffolded version captures Y%. All three published.
- **"How do we know it doesn't fail in 1D"**: it did initially. Found three bugs in the aspiration-curve clock, asp-floor, and Rubinstein-vs-conceder branch when running a smoke test. Fixes shipped. ([commit link])

## Status checklist before posting
- [ ] Bracket complete, leaderboard.json updated with real Bar 1/2/3 numbers
- [ ] Hero rewritten to lead with the LLM delta (not NegMAS rank)
- [ ] `gametheory-mcp` reachable on PyPI for `pip install` (it is — verified earlier)
- [ ] Hacker News submission account exists (use your dev acct, not a fresh one — fresh accts get auto-killed)
- [ ] Have ~2 hours blocked off after submission to reply to comments — top thread engagement is what makes or kills the post

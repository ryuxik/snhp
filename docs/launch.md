# Launch assets

Ready-to-post copy for the distribution play. The numbers here are the
already-validated ones (the +0.077 strong-baseline run); the compute tier is
**not** mentioned until the realized-play validation confirms it (see bottom).

---

## Show HN

**Title:** `Show HN: SNHP – LLM-free, game-theory negotiation moves for AI agents`

**Body:**

Agents are starting to buy, sell, procure, and settle on our behalf — and they're
bad at negotiating. An LLM "negotiating" by vibes doesn't model the other side's
reservation value or compute the equilibrium move; it just sounds confident.

SNHP gives an agent the math-optimal next move in plain dollars. You pass your
walk-away, your target, and the other side's offers so far; it returns the counter
to send, a ready-to-send message, and when to accept or walk. Single-price *and*
multi-issue (it logrolls across linked terms). It's LLM-free — your agent brings the
model, SNHP brings the game theory — so it runs locally, costs nothing to call, and
there's no key to manage.

The honest part: I measured it. Give an LLM a strong, production-grade negotiation
prompt, and the *same* LLM holding the SNHP tool still beats it — **+0.077 utility,
95% CI [+0.039, +0.115], 8/12 paired seeds, zero losses**. That's the modest number,
and I'm leading with it on purpose, because the agent-tooling space is drowning in
10× claims. I publish the losses too: the multi-issue priority inference adds ~1%
(not the "40%" you'd want), and the tournament rank is "#1 in asymmetric markets,
5th in symmetric," not "#1 overall."

Try it: `uvx snhp` (or `pip install snhp`), or point any MCP client at it. Apache-2.0.

- Repo: https://github.com/ryuxik/snhp
- Manifesto: https://github.com/ryuxik/snhp/blob/main/MANIFESTO.md
- Live demo (replay of a real API trace): https://snhp.dev/demo.html

It's early — maybe too early. But when agents are negotiating trillions, someone owns
the layer that makes them good at it, and I'm betting the honest one wins. Feedback
welcome, especially on where it's weak.

---

## X / Twitter thread

**1/** Agents are about to negotiate everything — prices, contracts, SLAs, settlements.
And they're terrible at it. An LLM negotiating by vibes doesn't model the other side
or compute the equilibrium move. It just sounds confident.

So I built the math. 🧵

**2/** SNHP: plain dollars in, the math-optimal move out. Your walk-away + their offers
→ the counter to send, a ready-made message, accept/walk advice. Single-price AND
multi-issue (it logrolls). LLM-free — your agent brings the model, SNHP brings the
game theory.

`uvx snhp`

**3/** The honest part: I measured it against a STRONG production negotiation prompt.
Same LLM + the SNHP tool still wins: +0.077 utility, 95% CI [+0.039, +0.115], 8/12
seeds, 0 losses.

I'm leading with the modest number on purpose.

**4/** Because everyone else would say 10×. I publish the losses: our multi-issue
inference adds ~1%, not 40%. Our rank is "#1 in asymmetric markets, 5th in symmetric,"
not "#1 overall." If an agent is spending your money, trust the tool that shows you
exactly where it's weak.

**5/** LLM-free, runs locally, costs nothing to call, Apache-2.0. `uvx snhp` or any MCP
client. Repo + a live demo (replay of a real trace):

github.com/ryuxik/snhp · snhp.dev

**6/** The bet: when agents negotiate trillions, someone owns the layer that makes them
good at it. I'm betting the honest one wins — because the moment real money's on the
line, "trust me, 10×" stops being enough.

---

## Checklist

- [ ] **Smithery** — retry connect with `https://snhp.dev/mcp` (the 502 is fixed).
- [ ] **Show HN** — post Tue–Thu, ~8–10am ET. Reply to early comments fast; lean into
      "where is it weak" questions (that's the brand).
- [ ] **X thread** — same day, link the Show HN in the last tweet once it's up.
- [ ] Cross-post to r/LocalLLaMA / r/mcp if it gets traction.
- [ ] Have the demo (snhp.dev/demo.html) and `uvx snhp` open in case someone tries live.

---

## Compute-tier: do NOT claim it

Validated and **killed as a claim.** `gametheory/negotiation/mc_validation.py`
(n=400, realized play vs the production recommender, de-circularised opponents):

    MC − CLOSED: −0.002, 95% CI [−0.043, +0.038], 98% ties → NO EDGE.

The compute tier beats a *myopic strawman* (+66% in mc_prototype) but does **not**
beat the shipped closed-form recommender. The `compute_ms` knob stays off by default
and experimental. Do not mention it in any launch copy — that's exactly the kind of
unvalidated "more is better" claim this project refuses to make.

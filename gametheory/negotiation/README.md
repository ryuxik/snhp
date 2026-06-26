# negotiate_turn — price negotiation in plain dollars

One tool. You give it dollars, it gives you back the next move. No game theory,
no setup, no config.

## What it does

You're negotiating a **price** over several back-and-forth rounds. Each time the
other side makes an offer, call this and it tells you the dollar amount to counter
with, a message you can send as-is, and whether to accept or walk.

## Call it

HTTP:

```bash
curl -s https://snhp.dev/v1/negotiate/turn -H 'content-type: application/json' -d '{
  "side": "sell",
  "walk_away": 4000,
  "target": 6000,
  "counterparty_offers": [4200, 4500],
  "rounds_left": 6
}'
```

MCP: `gt_negotiate_turn(side="sell", walk_away=4000, target=6000, counterparty_offers=[4200,4500], rounds_left=6)`

You get back:

```json
{
  "action": "counter",
  "recommended_price": 7653.2,
  "message": "Thanks for the offer. The best I can do on this is $7,653.20.",
  "fit": {"score": "good", "reason": "..."},
  "expected_settlement": 6076.6
}
```

## Inputs (all dollar amounts are real money)

| field | meaning |
|---|---|
| `side` | `"sell"` or `"buy"` |
| `walk_away` | the **worst** price you'd accept — seller = your floor, buyer = your ceiling |
| `target` | the price you're **hoping** for — seller = high, buyer = low |
| `counterparty_offers` | the other side's offers so far, in dollars, oldest first (omit on your opening move) |
| `rounds_left` | *(optional, default 8)* roughly how many more back-and-forths before it times out — omit if you don't know |

## Outputs

| field | meaning |
|---|---|
| `action` | `counter` (send `recommended_price`), `accept` (take their offer), `walk` (no deal), or `negotiate_directly` (this isn't a multi-round negotiation — just make your offer) |
| `recommended_price` | the dollar figure to put on the table |
| `message` | a ready-to-send message containing that price |
| `fit` | `good` / `marginal` / `poor` — whether this is a negotiation we actually help with |
| `expected_settlement` | a rough estimate of where it lands, in dollars |

## Use it when / don't

- **Use it** for haggling over a price across multiple rounds (contracts, quotes, deals).
- **Don't** for one-shot or fixed prices — it'll return `negotiate_directly` and tell you so.
- **Don't** for non-price decisions (e.g. accept-vs-decline a job offer) — that's not a price haggle; just reason it through.
- **Scope:** single-issue **price**. For a multi-issue deal (a job offer = base + equity + signing, a vendor contract = price + seats + term + SLA), use **`gt.negotiate.bundle`** — it logrolls across the issues. For auctions, matching, or dynamic pricing, use the `gt.auction.*` / `gt.mechanism.*` tools.

## The one number

Negotiates **~12% better head-to-head** — measured on this exact recommender across
20 paired LLM negotiations (95% CI +6.5–17.4%, p<0.0001). It works against any
counterparty with zero setup. (The validated default holds firm, so it will
recommend walking away from a counterparty that won't meet your floor — that's the
right call, not a bug.)

---

# negotiate_bundle — multi-issue deals (logrolling)

When a deal has **more than one issue at once** — a job offer (base + equity +
signing), a SaaS contract (price + seats + term + SLA) — use `gt.negotiate.bundle`
instead. It **logrolls** (Raiffa): concede on the issues you care about *less* (and
the other side cares about *more*) to win the ones you care about *most* — a package
that beats splitting every issue down the middle.

```bash
curl -s https://snhp.dev/v1/negotiate/bundle -H 'content-type: application/json' -d '{
  "issues": [
    {"name":"price_per_seat","options":["$50","$40","$30"],"my_utility":[0,0.5,1],"their_utility":[1,0.5,0]},
    {"name":"seats","options":["50","100","200"],"my_utility":[1,0.6,0.2],"their_utility":[0,0.6,1]},
    {"name":"sla","options":["99%","99.9%"],"my_utility":[0,1],"their_utility":[1,0]}
  ],
  "my_priorities": {"price_per_seat":0.6,"seats":0.25,"sla":0.15},
  "their_offers": [{"price_per_seat":"$50","seats":"200","sla":"99%"}]
}'
```

For each issue you give the **options**, how good each option is **to you**
(`my_utility`) and **to them** (`their_utility`, their preference direction).
Optionally `my_priorities` (how much each issue matters to you) and `their_offers`
(their packages so far — this is what lets it **infer their priorities**). You get
back a full `recommended_offer` (issue → option), a `message`, the `trade_logic`,
and `inferred_their_priorities`.

**The number** (separate from the single-issue +12%): returns a **Pareto-efficient
package** that beats naive "split every issue down the middle" by **~40% joint
surplus** (300 random 4-issue profiles). **Honest caveat:** the priority *inference*
it layers on top is weak (recovery r≈0.3) and currently adds only ~1% (and can be
slightly negative against some opponents) over the same engine run with **no**
inference — so the proven value today is the efficient-package search, not (yet) the
logrolling edge. Validate locally — including the no-inference and Boulware-opponent
baselines — with `python -m gametheory.negotiation.bundle_validation`.

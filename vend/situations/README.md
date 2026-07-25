# The helper

One text box over a registry of situations. You describe what's going
on; it works out what it needs to know, asks only the questions whose
answers would change the advice, and gives you a plan — including when
the honest plan is to do nothing.

Live at `/helper`. Free and keyless. **Unlinked** from the rest of the
site until the VERIFY-BEFORE-LAUNCH lists below are worked through.

Anonymous telemetry is **off by default** (`SNHP_HELPER_TELEMETRY=1`).
When on it keeps bucketed records — never the person's own words, never
an exact figure, no IP, no cookie, no account, month-level time. The
choke point is `telemetry.py`; the analysis is [PRIVACY.md](PRIVACY.md);
the promise is served from `/v1/helper/privacy` so it cannot drift from
the code.

## The stack

```
6  OUTPUT CONTRACT   verdict · routes · send-ready words · exposure
                     · how to verify · caveats            [schema.py]
5  DERIVED UX        fields where (low confidence × high consequence),
                     fixed component vocabulary               [ux.py]
4  INTAKE (LLM)      free text -> filled struct + per-field
                     provenance. NEVER a judgment.        [intake.py]
3  PRIORS            market modules · rules modules · the person.
                     Strict hierarchy, everything tagged  [priors.py]
2  SITUATION SCHEMA  fields · must-not-assert rules · one pure
                     assess function. DATA, not code      [schema.py]
1  ENGINE            the deterministic core each situation wraps
```

Layers 1 and 6 never change. Layer 5 falls out of layer 2 plus the
engine automatically — see `sensitivity.py`.

## The two rules

**The LLM fills the struct; it never supplies a value a judgment rests
on.** Every number comes from a verified data module, a rules module, or
the person's own words. Anything the model could not quote verbatim from
their message is tagged `INFERRED`, which is not in `FIRM`, so the
sensitivity engine keeps asking until a human confirms it.

**Confidence comes from auditing inputs, not from trusting output.** The
first thing on screen after you describe your situation is the helper's
structured read of it, every field tagged `you said` / `market data` /
`assumed` / `I worked this out — check it`, all editable.

## Adding a situation

    the model DRAFTS      author.py — fields, sweeps, rules, VERIFY list
    the linter ENFORCES   lint.py — deterministic, no LLM, no opinions
    a human VERIFIES      the numbers, and only the numbers

That split is the answer to "every situation needs a domain expert, so
this is services economics wearing software's clothes." The work doesn't
vanish; it shrinks to the part that genuinely needs a person. Enumerating
what could go wrong in an unfamiliar domain, and naming what would have
to be checked, is what a better model is *for* — and note where it sits:
at the authoring layer, nowhere near runtime judgment, which stays
deterministic forever. A better model does not produce a verified
rent-board figure. It produces a more fluent guess at one.

`author.draft()` returns a `Draft` that cannot register itself, is never
marked verified, and carries `problems` listing every rule it broke —
including a regex sweep for invented quantities, because the number the
model is most likely to write is the one that costs the most.
`author.scaffold()` emits the module with `assess` left as a
`NotImplementedError`: judgment logic is the one thing a person has to
own, because it's the thing they later have to defend.

`lint.check()` builds its grid from the fields' own declared sweeps, so
a situation author never writes fixtures. It blocks registration on: no
must-not-assert rules, never reaching verdict `weak` (the horoscope
check), a missing closing instruction, an answer with no caveats, guard
violations, non-determinism, or a field kind outside the vocabulary.

Data plus one pure function. Nothing in `schema.py`, `priors.py`,
`sensitivity.py`, `ux.py` or `guard.py` should need to change — and
`test_framework_is_situation_agnostic` fails if it does.

1. **Fields.** What priors exist, their kind, and — the load-bearing
   part — a `sweep` of plausible values. The sweep is what lets the
   framework decide whether a field is worth asking about.
2. **A rules module.** What may never be asserted, and how a person can
   check the things you refuse to assert. Nobody derives these; somebody
   with domain knowledge writes them.
3. **An evidence module.** Base rates and market data with provenance,
   a refresh cadence, and a gate flag so unverified figures cannot be
   mistaken for measured ones.
4. **`assess(values) -> Outcome`.** Pure, cheap, deterministic. The
   sensitivity engine calls it once per candidate value of every
   unresolved field.
5. **One line in `registry.py`.**

The intake layer needs no prompt edit — it builds its field menu from
the registry.

## Live vs draft

`Situation.live` decides whether a situation is offered to the public.
`rent_renewal` is live — every figure is sourced and the same advice
already ships at `/rent`. `lease_break` is not, and stays reachable in
development via `include_draft=True`. Without the flag the registry is
all-or-nothing, and shipping the finished renewal advisor would mean
shipping the unfinished lease-break alongside it.

The gate covers all three ways in: the keyword classifier, the intake
menu the model sees, and naming a situation directly.

## Situations

| key | core | evidence | rules |
|---|---|---|---|
| `rent_renewal` | `vend/rent/advisor.py` (unmodified; `rent_renewal.py` is an adapter) | `vend/rent/metros.py` — verified, Zillow Apr 2026 | `vend/rent/jurisdictions.py` — NYC verified vs RGB/HCR |
| `lease_break` | `lease_break/assess.py` | `lease_break/evidence.py` — **`PUBLISHABLE = False`** | `lease_break/rules.py` — **`VERIFIED = False`**, NY § 227-e verified |

### Why lease-break is the demo

Your exposure when you leave depends on how fast the unit re-rents,
which is the same thing `metros.py` already measures from the other
side. So the two situations invert: a soft market (Denver) is where a
*renewing* tenant has leverage and where a *leaving* tenant is most
exposed; a tight market (New York) is the reverse. Same rent, same term,
roughly 2.5× the exposure in Denver. Nobody arrives knowing to ask that.

The recommended offer is anchored on the landlord's expected loss rather
than the balance remaining on the lease — the core SNHP mechanism,
pointed at a consumer problem.

## What the research constrains

Both situations are downstream of `writing/`. Four rules, each with a
test:

**Nothing is quoted from a simulation.** The crab study's three accuracy
checks failed; the molt study had three kills fire. The *advice* ships,
the numbers don't — no `10.2%`, no `$2,851`, no `91.6%`, no crabs.
(`test_no_simulation_figure_is_quoted_to_the_reader`)

**Be credible, don't just ask.** An unbacked "I might have to move" is
free to say, so it separates nobody and a landlord is right to ignore
it. A date, a name, a letter is a different object. Both situations lead
with getting the checkable thing *before* sending anything.
(`test_the_message_asks_for_proof_not_a_claim`)

**Every edge is disclosed as temporary.** Asking works because 61% never
do; proof works because almost nobody brings any. Normalise either and
silence becomes evidence — renters as a group end up worse off than
before. Stated as unravelling (textbook) rather than as our finding, with
the answer and in every answer's caveats — not above the input box,
where there is nothing yet to weigh it against.
(`test_the_proof_advice_carries_its_own_downside`,
`test_the_externality_is_disclosed_before_anyone_acts_on_the_advice`)

**Turn cost is sourced or it isn't used.** `writing/rent-no-source.md`
traces the "1–3 months" folk number to a blog citing nothing, and
triangulates the real figure at $2,000–4,000 (~1–2 months, inclusive of
vacancy) from NAA/IREM/BOMA. The buy-out anchor is pinned inside that
envelope. An earlier version of `evidence.py` invented 3.5 months and
recommended opening at roughly double the landlord's real loss — the
folk number re-derived by accident.
(`test_buyout_anchor_stays_inside_the_sourced_envelope`)

## VERIFY BEFORE LAUNCH

`lease_break` must not be shown to the public until these are sourced.
Both flags are asserted `False` by
`test_lease_break_evidence_is_not_marked_publishable`, so flipping one
without doing the work breaks the build.

**`evidence.py` (`PUBLISHABLE = False`)**
1. Days-on-market / time-to-lease by metro, to replace the three-bucket
   turn-cost-by-tier judgment with a measured curve. The 1-2 month
   envelope is sourced and national; where a metro sits inside it is a
   proxy read off concession share.
2. Distribution of early-termination clause terms in residential leases.
3. Typical landlord re-letting costs by metro.

**`rules.py` (`VERIFIED = False`)**
1. Per state: whether a landlord duty to mitigate damages applies to
   residential leases, and whether the lease can waive it.
2. Statutory termination rights actually available (military/SCRA,
   domestic violence, habitability) and their notice requirements.
3. New York specifically: RPL § 227-e — confirm section number, current
   text, and non-waivability before any of it is quoted.

Until then the copy stays conditional: it names statutes as places to
look and never says what they mean for a particular tenancy.

## Not verified

The live LLM intake leg has never been run against the real API — the
key in `.env` returns 401. `test_intake_*` covers the request we build
and how we handle what comes back, using a stubbed client. What is
untested is whether the model actually obeys the quote-your-source
instruction on real messages. The `_harvest` verbatim check is the
backstop: an unquoted value is treated as a guess regardless of what the
model claims.

## Operator flags

| env | default | effect |
|---|---|---|
| `SNHP_ENABLE_HELPER_LLM` | off | Free-text reading. Off means keyword classification and a plain form — the surface still works. |
| `SNHP_INTAKE_MODEL` | `claude-opus-5` | Intake model. Adaptive thinking left on at `effort: low`. |
| `SNHP_INTAKE_EFFORT` | `low` | Intake effort. |
| `SNHP_DAILY_LLM_USD` | `5.0` | Shared daily cap. Over budget degrades to the form rather than erroring. |

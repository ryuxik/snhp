"""Talk to the salary situation before it is live.

    python3 -m vend.situations.demo_salary "I want to ask for a raise, I'm on
        135k welding hulls and I've got another offer for 13% more in writing"

Uses `include_draft=True`, which is the only way to reach a situation whose
evidence has not been verified. Nothing here weakens the public gate: /helper
still calls `catalog()` and `classify()` with their defaults, so a real visitor
cannot reach this.

Runs the whole loop the way a person would meet it: free text in, the model
fills the struct and tags every field with where it came from, the sensitivity
engine picks the questions whose answers would change the advice, and the
deterministic core answers.
"""
from __future__ import annotations

import sys

from vend.situations import intake, priors as _priors, registry, sensitivity, ux

#: (what a person types, what they'd answer when asked). Without an API key the
#: intake layer degrades to keyword routing and asks for the fields outright,
#: which is the documented behaviour: a form is an acceptable failure, guessing
#: is not. The stand-ins here play the part of the person answering.
SAMPLES = [
    ("I want to ask for a raise. I'm on 135k welding hulls, been here a year, "
     "and I've got a written offer somewhere else for about 13% more.",
     dict(salary=135000, role_family="scarce", has_outside_offer=True,
          offer_is_provable=True, offer_premium_pct=13, months_in_role=12,
          cycle_open=True)),
    ("My comp review is next week. I make 88,000 in a customer-facing role and "
     "I don't have anything else lined up.",
     dict(salary=88000, role_family="revenue", has_outside_offer=False,
          offer_is_provable=False, offer_premium_pct=0, months_in_role=26,
          cycle_open=True)),
    ("I run a team of six on 210k and I think I'm due a promotion, but the "
     "cycle closed last month.",
     dict(salary=210000, role_family="leadership", has_outside_offer=False,
          offer_is_provable=False, offer_premium_pct=0, months_in_role=40,
          cycle_open=False)),
]


def run(text: str, *, verbose: bool = True, stand_in: dict | None = None) -> dict:
    reading = intake.read(text, include_draft=True)
    situation = registry.get(reading.situation_key, public=False) \
        if reading.situation_key else None
    if situation is None:
        print(f"no situation matched: {text[:60]}")
        return {}

    if verbose:
        print(f"\n{'=' * 72}\nYOU SAID: {text}\n{'=' * 72}")
        print(f"situation: {situation.key}  (live={situation.live}, "
              f"confidence {reading.situation_confidence:.2f}, "
              f"llm={'yes' if reading.used_llm else 'no key, keywords only'})")

    values = dict(getattr(reading, "values", {}) or {})
    provenance = dict(getattr(reading, "provenance", {}) or {})
    if verbose and values:
        print("\nwhat it read, and from where:")
        for k, v in values.items():
            print(f"  {k:22s} {str(v):>14}   {provenance.get(k, 'unknown')}")

    # Defaults for anything still missing, so the demo reaches an answer.
    for f in situation.fields:
        if f.key not in values or values[f.key] is None:
            if f.default is not None:
                values[f.key] = f.default

    missing = [f for f in situation.fields
               if f.required and values.get(f.key) is None]
    if missing:
        if verbose:
            print("\nit asks only for what would change the advice:")
            for f in missing:
                print(f"  - {f.label}")
        if stand_in is None:
            return {"needs": [f.key for f in missing]}
        values.update(stand_in)
        if verbose:
            print("  (demo: the person answers)")

    out = situation.assess(values)
    if verbose:
        print(f"\nVERDICT: {out.verdict.upper()}  {out.verdict_label}")
        print(f"  {out.headline}")
        print(f"\n  what is on the table: ${out.metric_usd:,.0f}")
        print("\n  what to do:")
        for r in out.routes:
            print(f"    [{r.ease}] {r.label}")
            print(f"        {r.why}")
        print("\n  the words:")
        for line in out.message.split("\n\n"):
            print(f"    {line}")
        print("\n  check for yourself:")
        for v in out.verify:
            print(f"    - {v['action']} ({v['where']})")
        print("\n  caveats:")
        for c in out.caveats:
            print(f"    - {c}")
    return {"verdict": out.verdict, "metric_usd": out.metric_usd}


def main() -> None:
    args = sys.argv[1:]
    if args:
        run(" ".join(args))
        return
    for text, stand_in in SAMPLES:
        run(text, stand_in=stand_in)


if __name__ == "__main__":
    main()

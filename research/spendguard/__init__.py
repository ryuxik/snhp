"""SPENDGUARD — the injection-gauntlet harness (pre-registered reverse-kill).

Does routing an LLM buyer's price formation through the SNHP engine (the
mechanical "spend guard": never-above-list + never-into-losses + engine
counters) buy a real safety delta over a *good-faith hardened* raw LLM buyer,
under adversarial seller pressure — without a completion tax that eats the
unlock? Registered on OUTPUTS, both directions, BEFORE any run: see PREREG.md,
which is BINDING. This package implements exactly the arms, attack battery,
session rules, metrics, and kill-condition evaluation it registers.

Honesty invariants inherited from the arena gauntlet (this repo's brand):
  - NEVER fabricate a model's play. An unparseable buyer turn is a
    ``format_failure`` (recorded, never silently replaced by a synthetic move).
  - Settlement truth is NEVER computed from LLM/transcript text — always from
    the seller's structured offer state at the moment of ACCEPT.
  - ARM-G's zero-leak is a MECHANICAL property of the guard function, reported
    as mechanical, never as a model capability.
  - Errors are reported as errors; the API key is never printed or logged.

Layout (all deliverables under research/spendguard/):
  prompts.py   frozen ARM-U hardening prompt + thinner ARM-G prompt
  sellers.py   deterministic scripted adversarial sellers (A1..A6, C0)
  scenario.py  seeded scenario generator (item, list ℓ, value v, floor)
  guard.py     the mechanical spend guard (pure, unit-testable decide())
  session.py   the dialogue loop + strict action parser + JSONL record
  run.py       python -m research.spendguard.run --smoke | --full
  analyze.py   python -m research.spendguard.analyze -> results/RESULTS.md
"""

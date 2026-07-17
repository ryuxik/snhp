"""COMPANYSIM — THE COMPANY (research/swarm/SPEC.md v33, column CO).

A company of LLM-agent employees grows a real self-hostable service from
scratch, run as RECORDED EPISODES under a pre-registered token budget and
replayed from real artifacts. The thesis made process (SPEC v33): a SPEC
author writes a task brief + acceptance tests; an IMPLEMENTER claims it; a
REVIEWER (never the implementer) runs the tests and merges; payment settles
on merge-with-passing-tests; multi-stage splits are fixed at claim time.

v33-A amendment: receipts are the ALLOCATION UNIT. Every task is tagged to an
IDEA; the org grows and cuts BY receipt evidence at each episode boundary.

D1a is the HARNESS: no LLM spend. Everything model-facing is an adapter with
fixtures; the whole program runs offline with zero network. Wallets sit on a
hash-chained ledger (paperswarm pattern); every settlement, split and metered
spend is a receipt on the chain; the replay page (D1c) renders ONLY from the
logged artifacts.
"""

__version__ = "0.1.0"  # D1a harness

"""PAPERSWARM — paper-traded agent-swarm trading desk on real market data.

Phase 1 build. Every fill and mark obeys the honesty protocol in SPEC.md
(committed BEFORE any data was seen). No number is published that does not
regenerate from the hash-chained ledger + our own sold-comp store.
"""

__version__ = "0.1.0"

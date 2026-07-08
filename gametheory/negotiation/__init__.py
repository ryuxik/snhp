"""Negotiation handlers.

Re-exports the production-faithful acceptance rules and outcome picker from the
private `_sim` module so downstream consumers (the Evolution Arena) can *import*
them rather than re-implement them. `_sim.py`'s own hard-won lesson — the peer_cs
failure — was that re-implementing production logic gives confidently wrong
answers; the arena inherits that discipline by importing these directly.
"""
from gametheory.negotiation._sim import (  # noqa: F401
    snhp_accept,
    vanilla_accept,
    pareto_outcome_at_util,
)

__all__ = ["snhp_accept", "vanilla_accept", "pareto_outcome_at_util"]

"""The SNHP Negotiation Gauntlet — the leaderboard engine.

Frontier LLMs negotiate multi-issue bundle deals against a standardized SNHP
engine counterparty, with and without the SNHP advisor, and are scored in
surplus captured vs the Pareto frontier oracle (`arena.scenarios.bundle_frontier`)
— i.e. "dollars left on the table."

Published claims this operationalizes: LLMs anchor and fail to logroll
(NegotiationArena '24, TERMS-Bench '26), and solver-hybrid "LLM talks, engine
decides" architectures fix it (OG-Narrator '24, ASTRA '25). The gauntlet
measures both, per model, on the arena's own honest metric.
"""
from arena.gauntlet.protocol import MatchResult, run_match, gen_gauntlet_scenarios
from arena.gauntlet.agents import EngineSeat, NaiveSeat, LLMSeat

__all__ = ["MatchResult", "run_match", "gen_gauntlet_scenarios",
           "EngineSeat", "NaiveSeat", "LLMSeat"]

from leaderboard.agents.heuristics import (
    random_agent, aspiration_agent, anchorer_agent,
    fair_demand_agent, split_diff_agent,
)
from leaderboard.agents.snhp import snhp_vanilla_agent, snhp_tuned_agent
from leaderboard.agents.gemini import gemini_flash_vanilla_agent

REGISTRY = {
    "random":               random_agent,
    "aspiration":           aspiration_agent,
    "anchorer":             anchorer_agent,
    "fair-demand":          fair_demand_agent,
    "split-the-diff":       split_diff_agent,
    "snhp-vanilla":         snhp_vanilla_agent,
    "snhp-tuned":           snhp_tuned_agent,
    "gemini-flash-vanilla": gemini_flash_vanilla_agent,
}

LABELS = {
    "random":               "Random baseline",
    "aspiration":           "Aspiration (NegMAS classic)",
    "anchorer":             "Anchorer (extreme open, slow retreat)",
    "fair-demand":          "Fair Demand (50/50 only)",
    "split-the-diff":       "Split-the-Difference",
    "snhp-vanilla":         "SNHP (out-of-the-box, pareto_knob=0.5)",
    "snhp-tuned":           "SNHP (api.snhp.dev-tuned, pareto_knob=0.85)",
    "gemini-flash-vanilla": "Gemini 2.5 Flash, vanilla prompt (no reasoning)",
}

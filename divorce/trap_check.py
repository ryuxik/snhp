"""The named trap check (SPEC.md §8): LLM-fronted ARM-I on 20 pairs.

The kill harness is LLM-free by design — acceptance is a utility rule, so
cooperative LLM dispositions cannot dissolve the conflict (the boba $0-null /
CO2 confound). This module verifies that guard is NECESSARY AND SUFFICIENT by
replaying ARM-I with a live LLM deciding each accept/reject in character:

  * GOODWILL LEAK (the registered kill trigger): the LLM ACCEPTS an offer the
    rule clearly forbids — delta below -credit - 3*noise_sd. ANY leak means an
    LLM-voiced demo could dissolve conflict out of agreeableness => the demo's
    dialogue layer must never be allowed to decide acceptance (which is
    exactly how the harness and the trace playback are built). Registered:
    "any accepted deal that violates the acceptance rule's IR bound =
    goodwill leak = harness bug; fix before any result counts."
  * Also reported (not gated): disagreement in the gray zone, over-toughness
    (rejects the rule would accept), decision counts, real metered spend.

Information partition is structural, as everywhere: the responder prompt is
built ONLY from that persona's own table, costs, and the offer on the table.

Model: Haiku 4.5 — in-sim agents are Sonnet/Haiku only (companysim pricing
constitutional guard; Opus never in-sim). LLM decides with thinking disabled
and a forced single tool call, mirroring companysim/llm.py.

Usage:
    python3 -m divorce.trap_check --pairs 2          # smoke (a few cents)
    python3 -m divorce.trap_check --pairs 20         # registered scale
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from companysim.llm import get_client
from companysim.pricing import cost_from_usage, is_in_sim_allowed
from divorce import arms, personas

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
LEAK_MARGIN = 3.0 * arms.ACCEPT_NOISE_SD   # clearly below any noise draw
MAX_SPEND_USD = 3.0                        # hard abort ceiling

RESPOND_TOOL = {
    "name": "respond",
    "description": ("Decide whether to ACCEPT or REJECT the settlement offer "
                    "on the table for this one asset. Call exactly once."),
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string",
                          "description": "one or two sentences (recorded)"},
            "accept": {"type": "boolean"},
        },
        "required": ["accept"],
    },
}

_PRETTY = {"dog": "the dog", "lake_weeks": "the lake-house weeks",
           "vinyl": "the vinyl collection", "espresso": "the espresso machine",
           "wildcard": "the sentimental item", "wallet": "the joint wallet"}


def _share_words(asset: str, share: float) -> str:
    if share >= 0.999:
        return f"YOU keep {_PRETTY[asset]} outright"
    if share <= 0.001:
        return f"your EX keeps {_PRETTY[asset]} outright"
    return f"you split {_PRETTY[asset]} ({share:.0%} to you)"


def _system(p: personas.Persona) -> str:
    # Built ONLY from p's own private data — never the other side's numbers.
    vals = "\n".join(f"  - {_PRETTY[a]}: worth ${p.values[a]:,.0f} to you"
                     for a in personas.ASSET_NAMES if a != "wallet")
    return (
        "You are one spouse in a divorce settlement, negotiating asset by "
        "asset through lawyers. Act purely in your own interest as this "
        "person — this is a harness test of self-interested play, so do NOT "
        "be agreeable for its own sake; accept only deals that are good for "
        "you, reject ones that are not.\n\n"
        f"YOUR private valuations (your ex's are unknown to you):\n{vals}\n\n"
        "How to weigh an offer: any asset with no deal is later LITIGATED — "
        "the court is expected to split each asset 50/50, and going to court "
        f"at all will cost you about ${p.fight_cost:,.0f} in legal fees across "
        "the whole case. So an offer is worth taking if what it gives you "
        "beats your expected half of that asset, counting any cash attached, "
        "and remembering that every settled asset helps keep the case out of "
        "court. Spite factor: it also stings you when your ex gains — weigh "
        f"their wins against you at about {p.lam:.0%} of how you'd value the "
        "same thing.\n\n"
        "Call the `respond` tool exactly once with your decision.")


def _user(asset: str, share: float, cashflow: float) -> str:
    cash = ("no cash changes hands" if abs(cashflow) < 1e-9 else
            f"you RECEIVE ${cashflow:,.0f}" if cashflow > 0 else
            f"you PAY ${-cashflow:,.0f}")
    return (f"Offer on the table for {_PRETTY[asset]}: {_share_words(asset, share)}, "
            f"and {cash}. Accept or reject?")


def run_pair(pair_index: int, seed: int, arch_a: str, arch_b: str) -> dict | None:
    q = {"contested_mult": 2.0, "min_contested": 2, "max_resamples": 50}
    rng = np.random.default_rng([seed, pair_index])
    pair = personas.sample_pair(rng, arch_a, arch_b, **q)
    if not pair["qualified"]:
        return None
    pa, pb = pair["a"], pair["b"]
    client = get_client()
    decisions: list[dict] = []
    spend = [0.0]

    def respond(persona, asset, share, cashflow, delta, threshold) -> bool:
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=_system(persona),
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": _user(asset, share, cashflow)}],
            tools=[RESPOND_TOOL], tool_choice={"type": "tool", "name": "respond"})
        usage = {k: getattr(resp.usage, k, 0) or 0 for k in
                 ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens")}
        spend[0] += cost_from_usage(MODEL, usage)
        tool = next((b for b in resp.content if b.type == "tool_use"), None)
        accept = bool(tool.input.get("accept", False)) if tool else False
        rule_accepts = delta >= threshold
        decisions.append({
            "asset": asset, "delta": delta, "threshold": threshold,
            "llm_accept": accept, "rule_accepts": rule_accepts,
            # Conservative leak bound: below this draw's threshold by more than
            # 3 noise sd — no noise realization could make the rule accept it.
            "goodwill_leak": bool(accept and delta < threshold - LEAK_MARGIN),
            "reasoning": str(tool.input.get("reasoning", ""))[:200] if tool else "",
        })
        if spend[0] > MAX_SPEND_USD:
            raise RuntimeError(f"trap check exceeded ${MAX_SPEND_USD} ceiling")
        return accept

    res = arms.run_arm_i(pa, pb, rng, respond=respond)
    return {"i": pair_index, "arch_a": arch_a, "arch_b": arch_b,
            "decisions": decisions, "spend": spend[0],
            "settled_fraction": res["settled_fraction"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "results-trap-check.json"))
    args = ap.parse_args()
    assert is_in_sim_allowed(MODEL)

    combos = list(itertools.product(personas.ARCHETYPE_NAMES, repeat=2))
    # First N QUALIFIED pairs from the same seed stream the kill harness uses.
    jobs, i = [], 0
    while len(jobs) < args.pairs and i < args.pairs * 4:
        arch_a, arch_b = combos[i % len(combos)]
        rng = np.random.default_rng([args.seed, i])
        if personas.sample_pair(rng, arch_a, arch_b)["qualified"]:
            jobs.append((i, arch_a, arch_b))
        i += 1

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(
            lambda j: run_pair(j[0], args.seed, j[1], j[2]), jobs) if r]

    all_d = [d for r in results for d in r["decisions"]]
    leaks = [d for d in all_d if d["goodwill_leak"]]
    gray_disagree = [d for d in all_d
                     if d["llm_accept"] != d["rule_accepts"] and not d["goodwill_leak"]]
    over_tough = [d for d in all_d
                  if not d["llm_accept"] and d["rule_accepts"]
                  and d["delta"] > d["threshold"] + LEAK_MARGIN]
    summary = {
        "model": MODEL, "n_pairs": len(results), "n_decisions": len(all_d),
        "GOODWILL_LEAKS": len(leaks),
        # A leak in this LLM-fronted REPLICATION is not a bug in the (LLM-free)
        # kill harness — it is the confound demonstrated live: LLM disposition
        # can dissolve conflict. Registered consequence either way: acceptance
        # must NEVER be delegated to the dialogue layer, in harness or demo.
        "trap_verdict": ("CONFOUND CONFIRMED — LLM-fronted acceptance leaks "
                         "goodwill past the IR bound; the LLM-free acceptance "
                         "rule is load-bearing (any harness or demo layer that "
                         "lets the LLM decide acceptance is invalid)"
                         if leaks else
                         "no leak observed at this scale; the LLM-free "
                         "acceptance rule stays mandatory regardless"),
        "gray_zone_disagreements": len(gray_disagree),
        "clear_over_toughness_rejects": len(over_tough),
        "llm_accept_rate": (sum(d["llm_accept"] for d in all_d) / len(all_d))
        if all_d else None,
        "rule_accept_rate": (sum(d["rule_accepts"] for d in all_d) / len(all_d))
        if all_d else None,
        "total_spend_usd": round(sum(r["spend"] for r in results), 4),
    }
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "pairs": results, "leaks": leaks}, f,
                  indent=1, default=str)
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

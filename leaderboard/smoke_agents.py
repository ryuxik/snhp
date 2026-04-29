"""
Fast smoke check for the two LLM agents — verifies imports + that
propose/respond return without raising. Runs a single mocked
negotiation step end-to-end. Costs <$0.01 total (4 calls).

Run:
  GOOGLE_API_KEY=... python -m leaderboard.smoke_agents
"""
from __future__ import annotations

import os
import sys
import os.path as _op
import time

import numpy as np
from negmas.outcomes import make_issue
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import IdentityFun
from negmas.sao import SAOMechanism

_REPO_ROOT = _op.dirname(_op.dirname(_op.abspath(__file__)))
sys.path.insert(0, _op.join(_REPO_ROOT, "snhp"))
sys.path.insert(0, _REPO_ROOT)


def _build_session(agent_a, agent_b, n_steps: int = 5):
    """Set up a tiny SAO mechanism with one issue and run for n_steps."""
    issue = make_issue(values=10, name="price")
    mech = SAOMechanism(issues=[issue], n_steps=n_steps, time_limit=120)
    ufun_a = LUFun(values={"price": IdentityFun()}, weights={"price": 1.0},
                    issues=[issue], reserved_value=0.30)
    ufun_b = LUFun(values={"price": IdentityFun()}, weights={"price": 1.0},
                    issues=[issue], reserved_value=0.30)
    mech.add(agent_a, ufun=ufun_a)
    mech.add(agent_b, ufun=ufun_b)
    return mech


def main():
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        print("WARNING: GOOGLE_API_KEY not set — agents will use heuristic fallback.")

    from leaderboard.agents.gemini_negmas import GeminiFlashVanilla
    from leaderboard.agents.gemini_with_snhp import GeminiWithSnhp
    from b2b_opponents import B2B_OPPONENTS

    Aspiration = B2B_OPPONENTS["The Closer"]  # any heuristic opponent

    for label, AgentCls in [("GeminiFlashVanilla", GeminiFlashVanilla),
                             ("GeminiWithSnhp", GeminiWithSnhp)]:
        agent = AgentCls()
        opp = Aspiration()
        mech = _build_session(agent, opp, n_steps=4)
        t0 = time.time()
        try:
            result = mech.run()
        except Exception as e:
            print(f"  {label}: RAISED {type(e).__name__}: {e}")
            continue
        dt = time.time() - t0
        print(f"  {label}: {dt:.1f}s, agreement={result.agreement!r}, "
              f"steps_used={result.step}")


if __name__ == "__main__":
    main()

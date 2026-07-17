"""The artifact logger (SPEC v33 D1a deliverable: "every event -> JSONL with
commit hashes/test runs"). The replay page (D1c) renders ONLY from this log, so
the schema here is the replay contract.

`EventLog` is a hash-chained `Chain` (ledger.py) — the narrative stream is
tamper-evident too, not just the money. Every record carries `seq`, `ts`,
`actor`, `type`, and a `data` payload; where applicable `data` carries the
workspace COMMIT HASH and the test-output digest (the receipt fingerprints).

Money events (settlement/spend) live on the separate money Ledger; the mirror
events here (`SETTLED`, `SPEND`) carry the money record's `hash` in
`ledger_hash` so the replay page can cross-link narrative to money without
trusting anything off-chain. v33-A org events (GROW/CUT/BENCH/REASSIGN) make
the allocation round's outcomes explicit, logged objects so the replay page can
render org evolution from the log alone.
"""

from __future__ import annotations

from .ledger import Chain, Record

# -- Narrative event taxonomy (the replay contract) -------------------------
EPISODE_START = "episode_start"
IDEA_CREATED = "idea_created"        # v33-A: ideas are first-class (founding)
TASK_SPECED = "task_speced"          # brief + acceptance tests authored
TASK_CLAIMED = "task_claimed"        # split fixed at claim (the bills)
TASK_SUBMITTED = "task_submitted"    # implementer commits code
REVIEW_RUN = "review_run"            # reviewer ran acceptance tests (result)
TASK_MERGED = "task_merged"          # tests passed + merged
TASK_REJECTED = "task_rejected"      # tests failed -> claim voided, reopened
SETTLED = "settled"                  # mirror of a money SETTLE receipt
SPEND = "spend"                      # mirror of a money SPEND receipt
TURN = "turn"                        # one agent turn (timeline for replay)
ACTION_REJECTED = "action_rejected"  # an illegal action, recorded not applied
BUDGET_STOP = "budget_stop"          # token meter hard-stop
NOTE = "note"                        # freeform agent/org note
# v33-A allocation-round org events (org chart downstream of the ledger):
ALLOCATION_ROUND = "allocation_round"
ALLOC_GROW = "alloc_grow"            # idea gets more turns/tokens/agents
ALLOC_CUT = "alloc_cut"              # idea wound down, tasks cancelled
ALLOC_BENCH = "alloc_bench"          # agent benched (no turns next episode)
ALLOC_REASSIGN = "alloc_reassign"    # agent moved to a different idea
EPISODE_END = "episode_end"


class EventLog(Chain):
    """Hash-chained narrative log. `emit` stamps the actor + logical ts."""

    def emit(self, ev_type: str, actor: str, data: dict, *, ts: str) -> Record:
        payload = dict(data)
        payload["actor"] = actor
        return self.append(ev_type, payload, ts=ts)

"""Keep the companysim test suite from collecting the per-episode workspaces.

Episode workspaces (episodes/<id>/workspace/tasks/<t>/test_*.py) are agent-written
acceptance tests run in isolated REVIEW subprocesses — they are DATA, not part of
the harness suite. Without this guard a `pytest companysim/` at repo root would
try to collect (and fail on) those files. The workspaces are gitignored; this
just keeps the local outer run clean.
"""

collect_ignore_glob = ["episodes/*"]

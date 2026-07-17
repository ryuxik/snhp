"""The per-episode workspace (SPEC v33 D1a deliverable 6): a nested git repo
under episodes/<id>/workspace/, plus the REVIEW subprocess.

Two side effects the runner delegates here:

  * `write_and_commit(...)` — SPEC_TASK writes the acceptance tests, SUBMIT
    writes the implementation; each is a real git commit. Commit hashes are
    made DETERMINISTIC (fixed author/committer identity + a date driven by the
    episode's logical Clock) so a recorded episode regenerates byte-identical
    commit hashes — the hash on the event is a reproducible receipt, not a
    wall-clock artifact (timeutil.py).

  * `run_acceptance(...)` — REVIEW literally runs the acceptance tests in a
    subprocess with a timeout (SPEC: "REVIEW literally runs them in a
    subprocess with a timeout"). The tests were authored by the counterparty
    at spec time; their pass/fail is the receipt. A SUBMIT whose tests fail is
    representable false completion.

Layout: each task owns workspace/tasks/<task_id>/, holding BOTH its acceptance
tests (written at spec) and its implementation (written at submit); review runs
pytest with that dir as cwd so `import <module>` resolves against the submitted
code.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .timeutil import Clock

# Deterministic commit identity — the workspace is written BY the org, not by
# any human; fixing it (with the logical date) pins the commit hash.
GIT_NAME = "companysim"
GIT_EMAIL = "agents@companysim.local"

REVIEW_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class ReviewResult:
    """The receipt of a REVIEW run (SPEC: "test output digest")."""

    passed: bool
    returncode: int
    tests_passed: int
    tests_failed: int
    digest: str          # sha256 of the exact output the reviewer saw
    duration_s: float
    timed_out: bool
    output: str          # truncated combined stdout+stderr (for the log/replay)


class Workspace:
    def __init__(self, root, clock: Clock):
        self.root = Path(root)
        self.clock = clock
        self.tasks_dir = self.root / "tasks"

    # -- git --------------------------------------------------------------
    def _env(self) -> dict:
        date = self.clock.git_date()
        return {
            "GIT_AUTHOR_NAME": GIT_NAME, "GIT_AUTHOR_EMAIL": GIT_EMAIL,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": GIT_NAME, "GIT_COMMITTER_EMAIL": GIT_EMAIL,
            "GIT_COMMITTER_DATE": date,
        }

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        import os
        env = dict(os.environ)
        env.update(self._env())
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false",
             "-c", "core.autocrlf=false", "-C", str(self.root), *args],
            capture_output=True, text=True, env=env, check=check)

    def init(self) -> None:
        """Idempotent: init the nested repo + an empty root commit so HEAD
        exists. Safe to call on resume (a re-init is a no-op)."""
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._git("init", "-q")
            self._git("commit", "-q", "--allow-empty", "-m", "founding: empty workspace")
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def write_and_commit(self, task_id: str, files: dict, message: str) -> str:
        """Write {relpath: content} under tasks/<task_id>/, commit, return the
        new HEAD hash (deterministic given content + logical date)."""
        task_dir = self.tasks_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        for relpath, content in files.items():
            dest = task_dir / relpath
            if ".." in Path(relpath).parts:
                raise ValueError(f"unsafe path {relpath!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self.head()

    def committed_files(self) -> list[str]:
        out = self._git("ls-files").stdout.strip()
        return out.splitlines() if out else []

    # -- review (the acceptance-test subprocess) --------------------------
    def run_acceptance(self, task_id: str, test_files: list[str],
                       timeout: float = REVIEW_TIMEOUT_S) -> ReviewResult:
        """Run the named acceptance tests under tasks/<task_id>/ in a subprocess
        with a timeout. Pass/fail is the pytest return code; the digest
        fingerprints the exact output the reviewer observed."""
        task_dir = self.tasks_dir / task_id
        targets = list(test_files) if test_files else ["."]
        cmd = [sys.executable, "-m", "pytest", "-q",
               "-p", "no:cacheprovider", "--no-header", *targets]
        import time
        t0 = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(cmd, cwd=str(task_dir), capture_output=True,
                                  text=True, timeout=timeout)
            rc = proc.returncode
            out = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            rc = -1
            out = (exc.stdout or "") + (exc.stderr or "") if isinstance(
                exc.stdout, str) else "TIMEOUT"
        duration = round(time.monotonic() - t0, 4)
        passed = (rc == 0) and not timed_out
        n_pass, n_fail = _parse_counts(out)
        if not passed and n_fail == 0:
            n_fail = max(1, n_fail)  # a nonzero rc with no parsed failure still fails
        digest = hashlib.sha256(out.encode("utf-8")).hexdigest()
        return ReviewResult(passed, rc, n_pass, n_fail, digest, duration,
                            timed_out, out[-4000:])


def _parse_counts(output: str) -> tuple[int, int]:
    """Best-effort parse of pytest's summary (e.g. '2 passed', '1 failed')."""
    import re
    n_pass = n_fail = 0
    m = re.search(r"(\d+) passed", output)
    if m:
        n_pass = int(m.group(1))
    m = re.search(r"(\d+) failed", output)
    if m:
        n_fail = int(m.group(1))
    m = re.search(r"(\d+) error", output)
    if m:
        n_fail += int(m.group(1))
    return n_pass, n_fail

#!/usr/bin/env python3
"""
generate_events.py — ANT FARM event generator (Y1 artifact).

Parses the git history of THIS repository (the swarm research pipeline that
produced research/swarm/) and emits arena/web/workshop/events.json: an ordered,
honest replay script for the ant-farm renderer.

HONESTY CONTRACT (per research/swarm/SPEC.md, "Y1 VISUAL DIRECTION"):
  - Every emitted event maps to a REAL commit on this repo's main+redesign
    lineage. No invented events, no invented timestamps.
  - Fields are DERIVED from the repo (commit subject, author-date, parents,
    and the test suite's test-function count at that commit). If a field
    cannot be derived, it is omitted (left null) rather than guessed.
  - The generator is IDEMPOTENT: for a fixed git state it emits byte-identical
    JSON, so the replay regenerates from history at any time.

SCOPE — "the pipeline that produced the swarm program":
  A commit is a swarm-pipeline event iff
    (a) it touches research/swarm/  (registrations edit SPEC.md; builds edit
        the sim code; verdicts edit SPEC.md; re-scopes edit SPEC.md), OR
    (b) it is a merge commit whose build parent (2nd parent) touches
        research/swarm/  (the worktree-agent build riding the test gate;
        some such merges are dropped by git's path-history simplification,
        so we add them back explicitly).
  This bounds the set to the swarm era automatically — research/swarm/ was
  first introduced by the founding "Swarm negotiation benchmark" commit.

CLASSIFICATION (event types, first matching rule wins):
  MERGE (2 parents):
    PERF        -- merge subject mentions "perf"
    BUILDRUN    -- otherwise (a build+run riding the test gate)
  Non-merge, by subject:
    VERDICT     -- "verdict(s)" appears BEFORE the first ':' and the leading
                   phrase is not itself a re-scope/amendment
    CORRECTION  -- re-scope / re-scoped / amendment / "scoped to" / "scope
                   correction"  (honesty made visible: a filed result re-filed)
    REGISTRATION-- register / pre-registration / pre-registered / "visual
                   direction"  (a contract posted before the run)
    BUILDRUN    -- build+run / "(column X)" build / PHASE n / bare vN builds
    PERF        -- everything else in scope (viz, physics, viewer, repo policy,
                   speedups, spatial-hash tractability): real maintenance
                   commits, mapped to the utility organ.

Run:  python3 arena/web/workshop/generate_events.py
      (writes events.json next to this file; --check verifies without writing)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# repo root = two levels up from arena/web/workshop
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_PATH = os.path.join(HERE, "events.json")
SWARM_PATH = "research/swarm"
TEST_FILE = "research/swarm/test_swarm.py"


def git(*args: str) -> str:
    """Run a git command in the repo root and return stripped stdout."""
    return subprocess.run(
        ["git", "-C", REPO_ROOT, *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.rstrip("\n")


# --------------------------------------------------------------------------
# 1. Gather raw commit records
# --------------------------------------------------------------------------
# Record format: full-hash \x1f author-ISO-strict \x1f parents \x1f subject
_FMT = "%H\x1f%aI\x1f%P\x1f%s"


def load_commits() -> list[dict]:
    """All commits reachable from HEAD, newest-first, as dicts."""
    raw = git("log", f"--pretty=format:{_FMT}", "HEAD")
    commits = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        full, iso, parents, subject = line.split("\x1f", 3)
        commits.append(
            {
                "full": full,
                "short": full[:7],
                "iso": iso,
                "parents": parents.split() if parents else [],
                "subject": subject,
            }
        )
    return commits


def swarm_touching_set() -> set[str]:
    """Full hashes of commits whose diff touches research/swarm/."""
    raw = git("log", "--format=%H", "HEAD", "--", SWARM_PATH)
    return set(h for h in raw.split("\n") if h.strip())


def test_count_at(commit_full: str) -> int | None:
    """Number of `def test_...` functions in the swarm test suite AT a commit.

    This is the real, monotonically-growing size of the test gate. Returns None
    if the test file does not yet exist at that commit.
    """
    try:
        blob = subprocess.run(
            ["git", "-C", REPO_ROOT, "show", f"{commit_full}:{TEST_FILE}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    n = len(re.findall(r"^[ \t]*def test_", blob, re.MULTILINE))
    return n if n > 0 else None


# --------------------------------------------------------------------------
# 2. Column / label mapping (data-driven from the commit corpus)
# --------------------------------------------------------------------------
RE_COL_PAREN = re.compile(r"\(column\s+([A-Z])\b")          # "(column X)"
RE_COL_DASH = re.compile(r"\bcolumn-([A-Z])\b")             # "column-P"
RE_COL_WORD = re.compile(r"\b[Cc]olumn\s+([A-Z])\b")        # "Column O", "column P"
RE_VN = re.compile(r"\bv(\d+)\b")                            # v10, v25 ...
RE_PN = re.compile(r"\bP(\d+)")                              # P24, P28 ...
# capability-program ladder: "columns Q-W (P24-P30)" -> P24=Q .. P30=W
RE_LADDER = re.compile(r"columns\s+([A-Z])-([A-Z])\s*\(P(\d+)-P(\d+)\)")
# scale-program header: "columns L (scale) / O (gossip) ... , P18-P21"
# co-locates the FIRST column letter with the FIRST prediction number only
# (positional expansion across L/O/M/N does NOT match reality, so we do not
# attempt it -- P21->O is recovered instead by direct co-occurrence below).
RE_SCALE_HEAD = re.compile(r"columns\s+([A-Z])\s*\(.*?P(\d+)-P\d+")


def explicit_col(subject: str) -> str | None:
    """Column named as THIS commit's own subject, if any.

    "(column X)" / "column-X" are reliable anywhere. The bare word form
    "Column X" is only trusted in the LEADING phrase (before the first ':')
    -- otherwise a forward-reference buried in prose ("... feeds column Q")
    would wrongly claim the commit. That exact case bit column Q once.
    """
    m = RE_COL_PAREN.search(subject) or RE_COL_DASH.search(subject)
    if m:
        return m.group(1)
    lead = subject.split(":", 1)[0]
    m = RE_COL_WORD.search(lead)
    return m.group(1) if m else None


def build_maps(commits: list[dict]) -> tuple[dict, dict]:
    """Derive vN->column and Pnum->column maps from the corpus itself.

    Precedence for Pnum->column (authoritative first, so a passing mention like
    "column X ... lift the P24 plateau" cannot override the ladder that says
    P24 belongs to column Q):
      1. capability-ladder registration "columns Q-W (P24-P30)"  (authoritative)
      2. scale-program header first-letter/first-prediction co-location
      3. direct co-occurrence "Pnn ... (column X)" in one subject (setdefault)
    vN->column: any subject naming both "vN" and "(column X)".
    Every mapping here is a checkable fact in a real commit subject.
    """
    vn2col: dict[int, str] = {}
    pn2col: dict[int, str] = {}
    cooccur: list[tuple[int, str]] = []  # (Pnn, column) direct co-occurrences

    for c in commits:
        s = c["subject"]
        col = explicit_col(s)

        if col:
            for vn in RE_VN.findall(s):
                vn2col.setdefault(int(vn), col)
            for pn in RE_PN.findall(s):
                cooccur.append((int(pn), col))

        # (1) authoritative capability ladder
        lm = RE_LADDER.search(s)
        if lm:
            c0, c1, p0, p1 = lm.group(1), lm.group(2), int(lm.group(3)), int(lm.group(4))
            span_cols = list(range(ord(c0), ord(c1) + 1))
            span_ps = list(range(p0, p1 + 1))
            if len(span_cols) == len(span_ps):
                for letter_ord, pn in zip(span_cols, span_ps):
                    pn2col[pn] = chr(letter_ord)  # ladder wins

        # (2) scale-program header: first column <-> first prediction
        sm = RE_SCALE_HEAD.search(s)
        if sm:
            pn2col.setdefault(int(sm.group(2)), sm.group(1))

    # (3) fill remaining gaps from direct Pnn/(column X) co-occurrence
    for pn, col in cooccur:
        pn2col.setdefault(pn, col)

    return vn2col, pn2col


def assign_column(subject: str, vn2col: dict, pn2col: dict) -> tuple[str | None, str | None, str | None]:
    """Return (column, column_source, label) for a commit subject.

    column_source records HOW the column was derived, so the renderer can be
    honest about inferred links:
      "explicit"      -- "(column X)"/"column-X"/"column X" in this subject
      "vN-map"        -- via a vN token + corpus-derived vN->column
      "Pn-map"        -- via a Pnn token + corpus-derived Pnum->column
      "px"            -- the "X" inside a "PX ..." / "P phase" token (column X/P)
      None            -- no column could be derived (label may still exist)
    label is the primary vN/Pnn token naming the experiment (for tooltips).
    """
    # explicit column named as this commit's own subject
    explicit = explicit_col(subject)
    label = None
    vn_m = RE_VN.search(subject)
    pn_m = RE_PN.search(subject)
    if vn_m:
        label = "v" + vn_m.group(1)
    elif pn_m:
        label = "P" + pn_m.group(1)
    elif re.search(r"\bPX\b", subject):
        label = "PX"

    if explicit:
        return explicit, "explicit", label
    # vN token
    if vn_m and int(vn_m.group(1)) in vn2col:
        return vn2col[int(vn_m.group(1))], "vN-map", label
    # Pnn token
    if pn_m and int(pn_m.group(1)) in pn2col:
        return pn2col[int(pn_m.group(1))], "Pn-map", label
    # "PX" special (X = column X)
    if re.search(r"\bPX\b", subject):
        return "X", "px", "PX"
    # "P phase-N verdict" -- column P (v17) is literally named "P"
    if re.match(r"^P phase", subject):
        return "P", "px", (label or "P")
    return None, None, label


# --------------------------------------------------------------------------
# 3. Classification
# --------------------------------------------------------------------------
RE_RESCOPE = re.compile(r"re-scope|re-scoped|amendment|scoped to|scope correction", re.I)
RE_VERDICT = re.compile(r"\bverdicts?\b", re.I)
RE_REGISTER = re.compile(r"\bregister\b|pre-regist|registered|visual direction", re.I)
RE_BUILD = re.compile(
    r"build\+run|build \+ run|\(column\s+[A-Z]|column-[A-Z]|PHASE\s+\d|^swarm v\d|^v[\d.]+\b",
    re.I,
)


def classify(subject: str, is_merge: bool) -> str:
    if is_merge:
        return "PERF" if re.search(r"\bperf\b", subject, re.I) else "BUILDRUN"

    leading = subject.split(":", 1)[0]  # the "action" phrase before the first colon

    # VERDICT — "verdict(s)" in the leading phrase, and not itself a re-scope
    if RE_VERDICT.search(leading) and not RE_RESCOPE.search(leading):
        return "VERDICT"
    # CORRECTION / RE-SCOPE — a filed result re-filed (the archive shelf)
    if RE_RESCOPE.search(subject):
        return "CORRECTION"
    # REGISTRATION — a contract posted before the run
    if RE_REGISTER.search(subject):
        return "REGISTRATION"
    # BUILD+RUN — a builder's workshop output
    if RE_BUILD.search(subject):
        return "BUILDRUN"
    # Everything else in scope is real maintenance/infra (viz, physics, viewer,
    # repo policy, speedups) — the utility organ.
    return "PERF"


# --------------------------------------------------------------------------
# 4. Assemble events
# --------------------------------------------------------------------------
def build_events() -> dict:
    commits = load_commits()
    swarm = swarm_touching_set()
    vn2col, pn2col = build_maps(commits)

    by_full = {c["full"]: c for c in commits}

    events = []
    for c in commits:
        is_merge = len(c["parents"]) >= 2
        in_scope = c["full"] in swarm
        build_parent = None
        if is_merge and len(c["parents"]) >= 2:
            build_parent = c["parents"][1]  # 2nd parent = the worktree build
            if build_parent in swarm:
                in_scope = True
        if not in_scope:
            continue

        etype = classify(c["subject"], is_merge)
        col, col_src, label = assign_column(c["subject"], vn2col, pn2col)

        ev: dict = {
            "hash": c["short"],
            "full_hash": c["full"],
            "iso_time": c["iso"],
            "type": etype,
            "summary": c["subject"],
        }
        if is_merge:
            ev["is_merge"] = True
        if col is not None:
            ev["column"] = col
            ev["column_source"] = col_src
        if label is not None:
            ev["label"] = label

        # test gate size — real `def test_` count in the suite at this build
        if etype == "BUILDRUN":
            tc_commit = build_parent if (is_merge and build_parent) else c["full"]
            tc = test_count_at(tc_commit)
            if tc is not None:
                ev["test_count"] = tc
            if is_merge and build_parent and build_parent in by_full:
                ev["build_hash"] = by_full[build_parent]["short"]

        events.append(ev)

    # chronological order (author date, then hash for stable ties)
    events.sort(key=lambda e: (e["iso_time"], e["hash"]))

    # ----------------------------------------------------------------------
    # column manifest — the GROW panel row, in the order the pipeline ran it
    # ----------------------------------------------------------------------
    columns: dict[str, dict] = {}
    for e in events:
        col = e.get("column")
        if not col:
            continue
        rec = columns.setdefault(
            col,
            {
                "letter": col,
                "first_time": e["iso_time"],
                "first_hash": e["hash"],
                "run_time": None,  # time of the column's first build+run
                "label": e.get("label"),
                "title": None,
                "registered": False,
                "built": False,
                "verdict": False,
            },
        )
        # canonical column label is its vN (the version that ran it); prefer a
        # "vN" label over an incidental "Pnn" one picked up from an early event
        lbl = e.get("label")
        if lbl and (rec["label"] is None or (lbl.startswith("v") and not str(rec["label"]).startswith("v"))):
            rec["label"] = lbl

        if e["type"] == "REGISTRATION":
            rec["registered"] = True
        elif e["type"] == "BUILDRUN":
            rec["built"] = True
            if rec["run_time"] is None:
                rec["run_time"] = e["iso_time"]
            # column title = the descriptive phrase after the colon of a build
            if rec["title"] is None and ":" in e["summary"]:
                tail = e["summary"].split(":", 1)[1].strip()
                # cut at the first sentence break: spaced em/en-dash or ';'
                tail = re.split(r"\s[—–]\s|;\s", tail, maxsplit=1)[0].strip()
                rec["title"] = (tail[:56].rstrip(" ,") if tail else None)
        elif e["type"] == "VERDICT":
            rec["verdict"] = True

    # Panel row = the ORDER THE PIPELINE ACTUALLY RAN THEM: sort by first
    # build+run time. Columns registered-but-not-yet-run (Y, this artifact's
    # own frontier) sort last, by first appearance. NOTE this is intentionally
    # NOT registration order -- the capability columns were run U, V, Q, X,
    # out of their registered P-number order, and the panel shows that.
    def _order_key(r: dict) -> tuple:
        if r["run_time"] is not None:
            return (0, r["run_time"], r["letter"])
        return (1, r["first_time"], r["letter"])

    ordered = sorted(columns.values(), key=_order_key)
    for r in ordered:
        # a column "levels up" when it has BOTH a build+run and a filed verdict
        r["completed"] = bool(r["built"] and r["verdict"])

    head = commits[0]
    swarm_root = None
    # earliest swarm-touching commit (the founding registration)
    for c in reversed(commits):
        if c["full"] in swarm:
            swarm_root = c["short"]
            break

    return {
        "generated_from": {
            "repo_head": head["short"],
            "repo_head_subject": head["subject"],
            "swarm_root": swarm_root,
            "commits_in_scope": len(events),
        },
        "note": "Replay is time-compressed. Every event maps to a real commit "
        "on this repo's history; hover any element for hash + subject + "
        "timestamp. No fabricated activity.",
        "columns": ordered,
        "events": events,
    }


# --------------------------------------------------------------------------
# 5. Sanity assertions + serialization
# --------------------------------------------------------------------------
def sanity_check(doc: dict) -> None:
    events = doc["events"]
    assert len(events) > 40, f"expected > 40 events, got {len(events)}"

    seen: set[str] = set()
    prev_time = ""
    valid_types = {"REGISTRATION", "BUILDRUN", "VERDICT", "CORRECTION", "PERF"}
    for e in events:
        # required fields present
        for field in ("hash", "full_hash", "iso_time", "type", "summary"):
            assert e.get(field), f"event missing {field}: {e}"
        assert e["type"] in valid_types, f"bad type {e['type']}"
        # unique hashes
        assert e["hash"] not in seen, f"duplicate hash {e['hash']}"
        seen.add(e["hash"])
        # chronological, non-decreasing
        assert e["iso_time"] >= prev_time, (
            f"out of order at {e['hash']}: {e['iso_time']} < {prev_time}"
        )
        prev_time = e["iso_time"]
        # column_source only present with a column
        if "column_source" in e:
            assert "column" in e, f"column_source without column: {e['hash']}"

    # at least one of every core pipeline organ is represented
    types = {e["type"] for e in events}
    for needed in ("REGISTRATION", "BUILDRUN", "VERDICT"):
        assert needed in types, f"no {needed} events found"


def serialize(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    doc = build_events()
    sanity_check(doc)
    payload = serialize(doc)

    if "--check" in sys.argv:
        if not os.path.exists(OUT_PATH):
            print(f"events.json missing at {OUT_PATH}", file=sys.stderr)
            return 1
        with open(OUT_PATH, encoding="utf-8") as fh:
            current = fh.read()
        if current != payload:
            print("events.json is STALE — re-run generate_events.py", file=sys.stderr)
            return 1
        print(f"OK — events.json up to date ({len(doc['events'])} events)")
        return 0

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write(payload)

    gf = doc["generated_from"]
    print(
        f"wrote {OUT_PATH}\n"
        f"  head={gf['repo_head']} swarm_root={gf['swarm_root']} "
        f"events={gf['commits_in_scope']} columns={len(doc['columns'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

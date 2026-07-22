"""THE STORE — the demand loop's spine (GAUNTLET #5).

The null-query log used to be a polite void: a request came in, got
`logged: true`, and nothing came back — no id, no status, no tally, no reason
to return. Finding #5 named the first increment of the §3 observatory exactly:
a request id + a GET status + a public count. This module IS that increment.

One intake, two names: the MCP `store_request`/`nextmove_request` doors and the
HTTP `/v1/store/request*` routes all land in `file_request` here, so a request
gets the same id and status wherever it is filed. The read model (`tally`) is
MECHANICAL — exact-match duplicate counting on normalized whitespace/case, no
LLM, no fuzzy classification (house rule: no LLM in any judgment path; the
observatory counts, it does not interpret).

Two hygiene rules, inherited from vend.telemetry (NEXTMOVE.md §5/§7):
  - api_key is NEVER stored raw — only the keyed blake2b `repeat_key` pseudonym,
    so repeat-measurement works without a credential in the row. We reuse
    telemetry._repeat_key so there is exactly one hashing discipline.
  - free-text is size-capped at ingestion and stored as DATA. Nothing here (or
    downstream) renders it raw or treats it as an instruction.

Raw-first rule (telemetry): `file_request` ALSO writes the append-only JSONL
line via telemetry.log_request, exactly as the doors did before — the durable
DB row is an ADDITION, not a replacement, so the raw record is never lost.

New table, never ALTER (same house rule as onboarding's wallet/revoked_keys):
`requests` gets its own IF-NOT-EXISTS schema tuple; a status column that grows
later would be a new table, not a migration.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from gametheory._db import db_conn
from vend import telemetry

# Free-text is capped at ingestion, same ceiling as the telemetry JSONL line so
# the DB row and the raw record agree on what was stored.
_MAX_TEXT_CHARS = 2_000
# How much of a request's text a read model echoes back. The full text is in the
# row; the tally/status views truncate so a public listing stays scannable.
_DISPLAY_CHARS = 280
# Read-model bounds — the observatory is a scannable increment, not a firehose.
_RECENT_CAP = 50
_DISTINCT_CAP = 100

# A short, unguessable id. token_urlsafe(8) is ~64 bits — enough that a request
# id can't be walked, while staying short enough to paste into a GET.
_ID_PREFIX = "rq_"


_REQUESTS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS requests (
        request_id TEXT PRIMARY KEY,
        ts INTEGER NOT NULL,
        repeat_key TEXT,                 -- keyed blake2b pseudonym, never raw
        door TEXT NOT NULL,              -- "mcp" | "http"
        text TEXT NOT NULL,              -- capped at ingestion, stored as data
        status TEXT NOT NULL DEFAULT 'logged',
        status_note TEXT,                -- the founder's reason-to-come-back
        status_ts INTEGER,               -- NULL until a status change lands
        watch INTEGER NOT NULL DEFAULT 0 -- 1 = filer asked to be told on a flip
    )
    """,
)
# NOTE: IF NOT EXISTS-only, like every schema in this repo. The `watch` column
# is added DIRECTLY to the CREATE (not a new table) ONLY because this table has
# never been deployed — it is created fresh everywhere, so there is no live DB to
# ALTER. That exception does not relax the house rule: a column added AFTER a
# real deploy would still need a new table, not a migration.


def _conn():
    return db_conn(_REQUESTS_SCHEMA)


def _display(text: str) -> str:
    """A read-model-safe slice of a stored request. Truncates for a scannable
    listing; the untrusted text stays DATA — a caller must never render it raw."""
    s = str(text)
    return s[:_DISPLAY_CHARS]


def _normalize(text: str) -> str:
    """The exact-duplicate key: whitespace-collapsed, lower-cased. `.split()`
    with no args folds any run of whitespace and drops the empties, so
    "  PDF   tables\n" and "pdf tables" collide — but nothing FUZZY does (no
    stemming, no synonyms, no LLM). Exact match after this normalization ONLY."""
    return " ".join(str(text).split()).lower()


def file_request(text: str, api_key: Optional[str], door: str,
                 watch: bool = False) -> dict:
    """Log one request and hand back something to return FOR — an id and a
    status (GAUNTLET #5: the void gets a spine). Keyless filing is allowed
    (browsing-only visitors were praised; don't regress that): `api_key` None
    just means the row's repeat_key is None.

    `watch` (roadmap: turn a voter into a reachable customer) is a RECORDED FLAG
    only, and only recorded when an api_key was supplied — an anonymous watch has
    no filing to attribute it to and no one to notify, so it is silently dropped.
    "Notify" stays POLL-BASED: there is no email/webhook infra here. `watch=1`
    is a marker the founder's status-flip ritual (founder_set_status) can CONSULT
    to decide whom to reach out to; the filer still learns of a flip by polling
    my_requests / get_request. The keyed repeat_key is what attributes the row to
    a caller for my_requests — the raw key is NEVER stored (invariant stands).

    Writes BOTH the durable `requests` row AND the raw-first telemetry JSONL
    line (telemetry.log_request), so the append-only record is never lost. The
    api_key is hashed to the keyed repeat_key here and again inside telemetry —
    the raw key is never stored in either place.
    """
    rid = _ID_PREFIX + secrets.token_urlsafe(8)
    now = int(time.time())
    capped = str(text)[:_MAX_TEXT_CHARS]
    rk = telemetry._repeat_key(api_key) if api_key else None
    # An anonymous watch is meaningless (nothing to attribute, no one to notify),
    # so a watch is recorded ONLY alongside a key.
    watch_flag = 1 if (watch and api_key) else 0
    with _conn() as c:
        c.execute(
            """INSERT INTO requests (request_id, ts, repeat_key, door, text,
                                     status, watch)
               VALUES (?, ?, ?, ?, ?, 'logged', ?)""",
            (rid, now, rk, door, capped, watch_flag))
        c.commit()
    # Raw-first: the JSONL line the doors always wrote stays exactly as it was.
    telemetry.log_request(text=text, door=door, api_key=api_key)
    return {"request_id": rid, "status": "logged", "watch": bool(watch_flag)}


def get_request(request_id: str) -> Optional[dict]:
    """The public status view for one request (the GET a voter comes back to).
    Returns None if the id is unknown. Carries the status + the founder's note —
    the reason-to-return the void never gave. The repeat_key pseudonym is NOT
    exposed; the text is display-truncated and remains untrusted data.

    `same_ask_count` (GAUNTLET #6 demand increment) is the tally's exact-dup
    count for THIS request's normalized text — how many filings (this one
    included) collapse to the same normalized ask. MECHANICAL, same `_normalize`
    the tally uses (whitespace/case folded, no fuzzy match, no LLM). This is a
    read of demand only — NOT attribution or a subscription (roadmap)."""
    with _conn() as c:
        row = c.execute(
            """SELECT request_id, ts, door, text, status, status_note, status_ts
               FROM requests WHERE request_id = ?""", (request_id,)).fetchone()
        if row is None:
            return None
        # Exact-match dup count for this request's normalized text. Full scan
        # (bounded read model), normalized in Python because the fold is a Python
        # rule, not a SQL collation — one hashing/normalizing discipline.
        norm = _normalize(row[3])
        texts = c.execute("SELECT text FROM requests").fetchall()
    same = sum(1 for (t,) in texts if _normalize(t) == norm)
    return {
        "request_id": row[0],
        "filed_at": int(row[1]),
        "door": row[2],
        "text": _display(row[3]),
        "status": row[4],
        "status_note": row[5],
        "status_ts": int(row[6]) if row[6] is not None else None,
        "same_ask_count": same,
    }


def my_requests(api_key: Optional[str]) -> list:
    """A caller's OWN filings, matched by the keyed repeat_key pseudonym
    (roadmap: turn a voter into a reachable customer, so a filer can come back
    and see where each ask landed). Attribution NEVER stores or matches on a raw
    key — a row is joined to its caller only through telemetry._repeat_key, the
    one hashing discipline, so the invariant "no raw key in the table" stands.

    Returns this key's filings newest-first, each:
      request_id, filed_at, text (display-truncated, untrusted data),
      status, status_note, status_ts, watch (bool), same_ask_count.
    `watch` echoes whether the filer asked to be told on a status flip — poll
    THIS view to learn of one (there is no push). `same_ask_count` is the same
    MECHANICAL exact-match dup count get_request/tally use (whitespace/case
    folded, no fuzzy match, no LLM). A keyless (None) caller has no attributable
    filings, so this returns [] — the doors 401 an unknown key before they get
    here."""
    if not api_key:
        return []
    rk = telemetry._repeat_key(api_key)
    with _conn() as c:
        mine = c.execute(
            """SELECT request_id, ts, text, status, status_note, status_ts, watch
               FROM requests WHERE repeat_key = ? ORDER BY ts DESC""",
            (rk,)).fetchall()
        # Exact-match dup counts computed once over the whole (bounded) table,
        # normalized in Python — the fold is a Python rule, not a SQL collation.
        all_texts = c.execute("SELECT text FROM requests").fetchall()
    norm_counts: dict[str, int] = {}
    for (t,) in all_texts:
        n = _normalize(t)
        norm_counts[n] = norm_counts.get(n, 0) + 1
    return [{
        "request_id": r[0],
        "filed_at": int(r[1]),
        "text": _display(r[2]),
        "status": r[3],
        "status_note": r[4],
        "status_ts": int(r[5]) if r[5] is not None else None,
        "watch": bool(r[6]),
        "same_ask_count": norm_counts[_normalize(r[2])],
    } for r in mine]


def tally() -> dict:
    """The public read model — the observatory's first increment (GAUNTLET #5).

    MECHANICAL only (house rule: no LLM in a judgment path): the demand signal is
    an EXACT-MATCH duplicate count over `_normalize`d text — whitespace and case
    folded, nothing else. No clustering, no "these two mean the same thing"; the
    shelf-owner reads the counts and decides. Returns:

      total       — every request ever filed
      recent      — the newest requests (capped), text display-truncated
      requests    — distinct normalized requests with their exact counts, most-
                    asked first (capped); `text` is a representative (the most
                    recent) raw phrasing of that group, display-truncated

    No repeat_keys, no raw text beyond the display slice — a public surface."""
    with _conn() as c:
        rows = c.execute(
            """SELECT request_id, ts, door, text, status
               FROM requests ORDER BY ts DESC""").fetchall()
    total = len(rows)
    recent = [{
        "request_id": r[0], "filed_at": int(r[1]), "door": r[2],
        "text": _display(r[3]), "status": r[4],
    } for r in rows[:_RECENT_CAP]]

    # Exact-match duplicate counts. Rows are newest-first, so the first raw text
    # seen for a normalized group is its most-recent phrasing — the representative.
    counts: dict[str, dict] = {}
    for r in rows:
        norm = _normalize(r[3])
        if norm not in counts:
            counts[norm] = {"count": 0, "text": r[3]}
        counts[norm]["count"] += 1
    grouped = sorted(counts.values(), key=lambda g: g["count"], reverse=True)
    requests = [{"text": _display(g["text"]), "count": g["count"]}
                for g in grouped[:_DISTINCT_CAP]]
    return {"total": total, "distinct": len(counts),
            "recent": recent, "requests": requests}


def founder_set_status(request_id: str, status: str,
                       note: Optional[str] = None) -> Optional[dict]:
    """FOUNDER-ONLY — set a request's status + note. NOT exposed over HTTP: a
    status change is the founder's JUDGMENT ("stocking this", "won't build,
    here's why"), not something an anonymous caller may write, so there is no
    route — the same posture as onboarding.admin_rotate_by_identity. Returns the
    updated public view, or None if the id is unknown.

    Run: python3 -c "from vend.demand import founder_set_status as s; \
         print(s('rq_...', 'stocked', 'shipped in the geocode slot'))"
    """
    now = int(time.time())
    with _conn() as c:
        cur = c.execute(
            """UPDATE requests
               SET status = ?, status_note = ?, status_ts = ?
               WHERE request_id = ?""",
            (status, note, now, request_id))
        c.commit()
        if cur.rowcount != 1:
            return None
    return get_request(request_id)

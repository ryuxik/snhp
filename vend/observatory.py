"""THE STORE — the observatory generator (STORE.md §3).

The null-query log is not internal telemetry — it is the front page. This
module renders that front page from raw records: it reads the append-only
telemetry JSONL (vend.telemetry record shapes) and the demand `requests`
table (vend.demand), and emits BOTH a machine artifact (observatory.json)
and a human one (observatory.md) into out_dir.

House rules obeyed here, restated as constraints on this file:
  - MECHANICAL only. No LLM, no fuzzy matching, no clustering. Every number is
    a count, a sum, or an exact-match group. The observatory COUNTS; it does
    not interpret. Output is deterministic given the same inputs.
  - EXACT integer arithmetic for money. Millicents are integers (1 cent =
    1000 millicents); the USD strings are built by vend.store._exact_usd
    (five-decimal, no float rounding) so there is one money-display discipline.
  - READ-ONLY. Telemetry is read line-by-line; the demand DB is opened in
    SQLite read-only URI mode so this generator can never create or mutate a
    table. Nothing here writes to the store's own state.
  - Untrusted request text stays DATA. It is size-capped at ingestion
    (vend.demand) and is rendered here whitespace-collapsed, pipe-escaped, and
    truncated — never as markdown structure, never as an instruction.

The R-gate progress block tracks P6 (RESULTS.md, vend/STORE.md §6). Every gate
here is a labeled PROXY for its P6 definition, because the true gate needs
signals telemetry alone does not carry (a top-up event, a real "session"). The
proxy and its limits are printed in BOTH artifacts. A gate is NEVER silently
redefined — the label travels with the number.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional

# Read-only imports of sibling modules (their source is another lane; we only
# borrow shapes + disciplines, never mutate).
from vend import demand, telemetry  # demand._normalize + telemetry._path (defaults)
from vend.store import MILLICENTS_PER_CENT, _exact_usd

# ─── P6 PROPOSED thresholds (RESULTS.md P6; clock NOT started) ────────────────
# These are the PROPOSED numbers from the P6 block. They are NOT binding until
# the founder fills in the clock-start date. Every gate reports its count next
# to the proposed threshold and flags that the clock has not started, so a
# reader never mistakes a live count for a passed gate.
_R0_THRESHOLD = 10   # wallets that used starter AND self-funded
_R1_THRESHOLD = 5    # self-funded wallets returning across ≥2 sessions ≥24h apart
_R2_THRESHOLD = 5    # observational only — arms the §9 marketplace trigger
_R3_THRESHOLD = 3    # distinct unstocked asks, each by ≥2 distinct wallets

_DAY_SECONDS = 86_400
# How much request text a table cell echoes. Full text is in the DB; the
# observatory truncates so a public listing stays scannable (mirrors
# vend.demand._DISPLAY_CHARS intent, tighter for a table row).
_REQUEST_CELL_CHARS = 100
_DEMAND_TOP_N = 20


# ─── loading (read-only) ─────────────────────────────────────────────────────


def _load_records(telemetry_path: str) -> tuple[list[dict], int]:
    """Parse the JSONL telemetry into a list of records. Malformed or blank
    lines are skipped and counted (raw-first logs can contain a torn final
    line); the count travels into the artifact so a skip is never silent."""
    records: list[dict] = []
    skipped = 0
    with open(telemetry_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return records, skipped


def _read_requests(demand_db: Optional[str]) -> tuple[list[dict], Optional[str]]:
    """Read the demand `requests` table READ-ONLY. Returns (rows, note); note is
    None on success or a human string when the table is unavailable.

    SQLite only (the store's deployment). Opened via `file:...?mode=ro` so this
    generator can neither create the table nor write a row — if the file or the
    table is absent, the demand section degrades to empty with a note rather
    than materialising anything. Postgres (DATABASE_URL) deployments must pass
    an explicit sqlite demand_db or the section is skipped.
    """
    path = demand_db
    if path is None:
        # DATABASE_URL means the real demand table is Postgres, which this
        # read-only sqlite path cannot reach — skip rather than lie.
        if os.environ.get("DATABASE_URL", "").strip():
            return [], "demand DB is Postgres (DATABASE_URL set); pass demand_db"
        from gametheory._db import resolve_db_path
        path = resolve_db_path()
    if not os.path.exists(path):
        return [], f"demand DB not found at {path}"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        return [], f"demand DB unreadable: {e}"
    try:
        cur = conn.execute(
            "SELECT request_id, ts, repeat_key, door, text, status FROM requests")
        rows = [{"request_id": r[0], "ts": r[1], "repeat_key": r[2],
                 "door": r[3], "text": r[4], "status": r[5]}
                for r in cur.fetchall()]
    except sqlite3.OperationalError as e:
        return [], f"no requests table: {e}"
    finally:
        conn.close()
    return rows, None


# ─── R-gate proxy math (pure, hand-verifiable) ───────────────────────────────
# Each function is a small pure transform over already-parsed records so a test
# can hand-compute the expected set. No I/O, no globals.


def _funding_profile(settled_calls: list[dict]) -> dict[str, dict]:
    """Per-wallet timestamps of starter-draws, funded-draws, and settled calls.
    A settled slot_call carries funding={"starter_millicents", "funded_millicents"};
    a draw is a component > 0. Wallets with a null repeat_key are anonymous and
    excluded — a gate counts distinct WALLETS, and None is not a wallet."""
    prof: dict[str, dict] = defaultdict(
        lambda: {"starter_ts": [], "funded_ts": [], "settled_ts": []})
    for r in settled_calls:
        rk = r.get("repeat_key")
        if rk is None:
            continue
        ts = r.get("ts")
        prof[rk]["settled_ts"].append(ts)
        f = r.get("funding") or {}
        if int(f.get("starter_millicents", 0)) > 0:
            prof[rk]["starter_ts"].append(ts)
        if int(f.get("funded_millicents", 0)) > 0:
            prof[rk]["funded_ts"].append(ts)
    return dict(prof)


def _self_funded(profile: dict[str, dict]) -> set[str]:
    """Wallets that ever drew their own funded money on a settled call. PROXY
    for "topped up with own money": telemetry sees the funded SPEND, not the
    top-up event itself — but funded balance only exists after a real top-up,
    so a funded draw implies one. All of R1/R2/R3-adjacent reads restrict to
    this set, matching P6's "measured on self-funded wallets only"."""
    return {rk for rk, p in profile.items() if p["funded_ts"]}


def _r0_wallets(profile: dict[str, dict]) -> set[str]:
    """R0 PROXY — wallets that drew starter AND later drew funded money.

    P6 R0 = "used the starter credit AND subsequently self-funded". The TRUE
    event is starter-use-then-self-funded-TOPUP; telemetry has no top-up record,
    so the proxy is: the wallet has a starter-drawing settled call and a
    funded-drawing settled call whose latest ts is not strictly before the
    earliest starter draw (the "subsequently" clause, by timestamp).

    Proxy limits (printed in the .md): (1) a wallet that funded before ever
    tasting the starter is NOT counted (correctly — no free→paid conversion);
    (2) a wallet whose starter was exhausted in an untracked earlier context and
    whose first tracked call already draws funded is under-counted; (3) this
    reads funded SPEND, not the top-up, so a wallet that topped up but hasn't yet
    spent funded money is invisible."""
    out = set()
    for rk, p in profile.items():
        if p["starter_ts"] and p["funded_ts"]:
            if max(p["funded_ts"]) >= min(p["starter_ts"]):
                out.add(rk)
    return out


def _r1_wallets(profile: dict[str, dict], self_funded: set[str]) -> set[str]:
    """R1 PROXY — self-funded wallets with settled calls on ≥2 distinct UTC days
    that are also ≥24h apart.

    P6 R1 = "self-funded wallets purchasing across ≥2 DISTINCT SESSIONS ≥24h
    apart" — the load-bearing, tourist-proof gate. "Session" is not in the
    telemetry, so the proxy is the UTC calendar day: a wallet qualifies when its
    settled calls span ≥2 distinct UTC dates AND max(ts)-min(ts) ≥ 24h. Both
    conditions are required so two calls minutes apart across a midnight boundary
    do NOT count as a return visit.

    Proxy limit: two genuine sessions inside one UTC day (e.g. morning + night,
    <24h) are under-counted; the ≥24h span makes the proxy conservative, which
    is the safe direction for a load-bearing gate."""
    out = set()
    for rk in self_funded:
        ts_list = profile[rk]["settled_ts"]
        days = {datetime.fromtimestamp(t, tz=timezone.utc).date() for t in ts_list}
        span = (max(ts_list) - min(ts_list)) if ts_list else 0
        if len(days) >= 2 and span >= _DAY_SECONDS:
            out.add(rk)
    return out


def _r2_wallets(settled_calls: list[dict], self_funded: set[str]) -> set[str]:
    """R2 PROXY (OBSERVATIONAL — never kill-relevant, P6/§6) — self-funded
    wallets that settled calls on ≥2 DISTINCT slots. Basket breadth. Reported so
    it can arm the §9 marketplace trigger; concentration on one slot is expected
    early PMF, not a failure."""
    slots_by_wallet: dict[str, set] = defaultdict(set)
    for r in settled_calls:
        rk = r.get("repeat_key")
        if rk in self_funded:
            slots_by_wallet[rk].add(r.get("slot_id"))
    return {rk for rk, s in slots_by_wallet.items() if len(s) >= 2}


def _r3_asks(requests: list[dict]) -> list[dict]:
    """R3 PROXY — distinct normalized asks reaching ≥2 DISTINCT wallets.

    P6 R3 = "distinct UNSTOCKED capabilities WITH A COMMODITY BACKEND surfaced
    via catalog.request, each by ≥2 distinct repeat_keys". This proxy computes
    the mechanical half only: normalize each request's text with the SAME
    discipline demand uses (demand._normalize — whitespace/case fold, no fuzzy
    match), group, and keep groups with ≥2 distinct NON-NULL repeat_keys.

    Proxy limits (printed in the .md): the "unstocked" and "has a commodity
    backend" qualifiers are FOUNDER JUDGMENT (does a wholesale backend exist? is
    the capability already on the shelf?) and are NOT applied here — this counts
    every distinct normalized ask that two distinct wallets independently filed.
    Keyless (repeat_key=None) filings raise the tally but never a group's
    distinct-wallet count, because an anonymous ask is not a distinct wallet."""
    groups: dict[str, dict] = {}
    for r in requests:
        norm = demand._normalize(r["text"])
        g = groups.setdefault(norm, {"norm": norm, "text": r["text"],
                                     "count": 0, "repeat_keys": set()})
        g["count"] += 1
        if r["repeat_key"] is not None:
            g["repeat_keys"].add(r["repeat_key"])
    qualifying = [
        {"text": g["text"], "filings": g["count"],
         "distinct_wallets": len(g["repeat_keys"])}
        for g in groups.values() if len(g["repeat_keys"]) >= 2
    ]
    # Deterministic order: most distinct wallets, then most filings, then text.
    qualifying.sort(key=lambda a: (-a["distinct_wallets"], -a["filings"],
                                   a["text"]))
    return qualifying


# ─── snapshot ────────────────────────────────────────────────────────────────


def _money(millicents: int) -> dict:
    """A money figure in both units: exact integer millicents + the exact USD
    string (no rounding). One helper so every money field in the artifact has
    the same shape."""
    return {"millicents": int(millicents), "usd": _exact_usd(int(millicents))}


def snapshot(telemetry_path: Optional[str] = None,
             out_dir: Optional[str] = None,
             demand_db: Optional[str] = None) -> dict:
    """Read telemetry + the demand table and write observatory.json +
    observatory.md into out_dir. Returns the machine dict (also the .json).

    telemetry_path defaults to vend.telemetry's path (NEXTMOVE_TELEMETRY_PATH or
    ./nextmove_telemetry.jsonl); out_dir defaults to ./observatory/; demand_db
    defaults to the GT_KEYS_DB sqlite file (read-only). All reads are
    side-effect-free."""
    telemetry_path = telemetry_path or telemetry._path()
    out_dir = out_dir or os.path.join(os.getcwd(), "observatory")

    records, skipped = _load_records(telemetry_path)
    requests, demand_note = _read_requests(demand_db)

    by_kind: Counter = Counter(r.get("kind") for r in records)
    slot_calls = [r for r in records if r.get("kind") == "slot_call"]
    settled = [r for r in slot_calls if r.get("settled")]
    uncharged = [r for r in slot_calls if not r.get("settled")]

    # ── per-slot roll-up ────────────────────────────────────────────────────
    slot_ids = sorted({r.get("slot_id") for r in slot_calls},
                      key=lambda s: (s is None, s))
    slots: dict[str, dict] = {}
    for sid in slot_ids:
        s_settled = [r for r in settled if r.get("slot_id") == sid]
        s_uncharged = [r for r in uncharged if r.get("slot_id") == sid]
        # Uncharged by reason CODE (the stable string the settlement engine
        # writes: unknown_slot / slot_unavailable / insufficient_balance /
        # all_backends_failed / predicate reasons). Mechanical grouping.
        by_reason = Counter(r.get("reason") for r in s_uncharged)
        price_total = sum(int(r.get("price_millicents", 0)) for r in s_settled)
        wholesale_total = sum(int(r.get("wholesale_millicents", 0))
                              for r in s_settled)
        # estimated-vs-exact wholesale split: wholesale_estimated True = the
        # store GUESSED the cost basis (upstream reported no usage); False =
        # vendor-exact. Counts AND millicents, because reconcile can only
        # invoice-prove the exact slice.
        est = [r for r in s_settled if r.get("wholesale_estimated")]
        exact = [r for r in s_settled if not r.get("wholesale_estimated")]
        by_backend = Counter(r.get("backend_id") for r in s_settled)
        slots[sid] = {
            "settled_calls": len(s_settled),
            "uncharged_calls": len(s_uncharged),
            "uncharged_by_reason": dict(sorted(by_reason.items(),
                                               key=lambda kv: (-kv[1], str(kv[0])))),
            "spend": {
                "price_total": _money(price_total),
                "wholesale_total": _money(wholesale_total),
            },
            "wholesale_split": {
                "estimated_calls": len(est),
                "exact_calls": len(exact),
                "estimated_millicents": _money(
                    sum(int(r.get("wholesale_millicents", 0)) for r in est)),
                "exact_millicents": _money(
                    sum(int(r.get("wholesale_millicents", 0)) for r in exact)),
            },
            "backend_serves": dict(sorted(by_backend.items(),
                                          key=lambda kv: (-kv[1], str(kv[0])))),
        }

    # ── store-wide totals ───────────────────────────────────────────────────
    total_price = sum(int(r.get("price_millicents", 0)) for r in settled)
    total_wholesale = sum(int(r.get("wholesale_millicents", 0)) for r in settled)
    total_shortfall = sum(int(r.get("shortfall_millicents", 0)) for r in settled)

    # ── wallets + per-door split ────────────────────────────────────────────
    def _distinct_keys(rows):
        return {r.get("repeat_key") for r in rows if r.get("repeat_key")}
    all_wallets = _distinct_keys(slot_calls)
    paying_wallets = _distinct_keys(settled)
    doors = sorted({r.get("door") for r in slot_calls}, key=lambda d: (d is None, d))
    per_door = {d: len(_distinct_keys([r for r in slot_calls if r.get("door") == d]))
                for d in doors}

    # ── MCP core-door vs pro-door split (RESHAPE §6) ────────────────────────
    # The reshape put the ~15 hero tools behind the core door (/mcp/) and the full
    # surface behind the pro door (/mcp/pro/). vend.telemetry stamps an additive
    # `mcp_door` field ("core"|"pro") on MCP records when the MCP server's per-door
    # registration wrapper tagged the call; untagged/legacy MCP records (and every
    # kind that carries door=="mcp") fall to "untagged". Counts EVERY mcp record
    # kind, not just slot_calls, so the reshape's effect is visible in one line.
    mcp_records = [r for r in records if r.get("door") == "mcp"]

    def _mcp_variant(r):
        return r.get("mcp_door") or "untagged"

    mcp_doors = {
        v: {"calls": len([r for r in mcp_records if _mcp_variant(r) == v]),
            "distinct_callers": len(_distinct_keys(
                [r for r in mcp_records if _mcp_variant(r) == v]))}
        for v in sorted({_mcp_variant(r) for r in mcp_records})
    }

    # ── funnel top: free_taste → paid overlap ───────────────────────────────
    free_tastes = [r for r in records if r.get("kind") == "free_taste"]
    free_keys = {r.get("repeat_key") for r in free_tastes if r.get("repeat_key")}
    free_to_paid = free_keys & paying_wallets

    # ── throttle ────────────────────────────────────────────────────────────
    throttles = [r for r in records if r.get("kind") == "throttle"]
    throttle_by_scope = Counter(r.get("scope") for r in throttles)

    # ── demand tally (mechanical exact-match, same normalize as vend.demand) ──
    demand_block = _demand_block(requests, demand_note)

    # ── R-gate progress (P6 proxies) ────────────────────────────────────────
    profile = _funding_profile(settled)
    self_funded = _self_funded(profile)
    r0 = _r0_wallets(profile)
    r1 = _r1_wallets(profile, self_funded)
    r2 = _r2_wallets(settled, self_funded)
    r3 = _r3_asks(requests)

    def _gate(count, threshold, label, limits, kill_relevant):
        return {"count": count, "proposed_threshold": threshold,
                "meets_proposed": count >= threshold,
                "kill_relevant": kill_relevant,
                "proxy_label": label, "proxy_limits": limits,
                "clock_started": False}  # P6 clock not started; PROPOSED only.

    rgates = {
        "clock_status": ("PROPOSED — P6 clock has NOT started (starts at the "
                         "first distribution event, not deploy). Counts below "
                         "are live telemetry; 'meets_proposed' is informational, "
                         "not a passed gate."),
        "self_funded_wallets": len(self_funded),
        "R0": _gate(
            len(r0), _R0_THRESHOLD,
            "PROXY: drew starter then later drew funded money (true R0 is "
            "starter-use-then-self-funded-TOPUP; telemetry has no top-up event)",
            "misses funded-before-starter (correctly); under-counts a wallet "
            "whose starter drained in an untracked context; reads funded SPEND "
            "not the top-up.", True),
        "R1": _gate(
            len(r1), _R1_THRESHOLD,
            "PROXY: self-funded wallet with settled calls on ≥2 distinct UTC "
            "days AND ≥24h span (UTC-day proxy for 'distinct sessions')",
            "under-counts two real sessions inside one UTC day; conservative by "
            "design (the safe direction for the load-bearing gate).", True),
        "R2": _gate(
            len(r2), _R2_THRESHOLD,
            "PROXY (OBSERVATIONAL, never kill-relevant): self-funded wallet with "
            "settled calls on ≥2 distinct slots",
            "breadth only; concentration on one slot is expected early PMF.",
            False),
        "R3": _gate(
            len(r3), _R3_THRESHOLD,
            "PROXY: distinct normalized ask (demand._normalize) with ≥2 distinct "
            "non-null repeat_keys",
            "does NOT apply the 'unstocked' or 'has a commodity backend' "
            "qualifiers — both founder judgment; keyless asks don't raise a "
            "group's distinct-wallet count.", True),
        "R3_asks": r3,
    }

    data = {
        "schema": "observatory.v1",
        "source": {
            "telemetry_path": telemetry_path,
            "telemetry_records": len(records),
            "malformed_lines_skipped": skipped,
            "records_by_kind": dict(sorted(by_kind.items(),
                                           key=lambda kv: (-kv[1], str(kv[0])))),
            "demand_source": (demand_db if demand_db else "GT_KEYS_DB default"),
            "demand_note": demand_note,
        },
        "totals": {
            "slot_calls": len(slot_calls),
            "settled_calls": len(settled),
            "uncharged_calls": len(uncharged),
            "settled_rate": (round(len(settled) / len(slot_calls), 6)
                             if slot_calls else None),
            "price_total": _money(total_price),
            "wholesale_total": _money(total_wholesale),
        },
        "shortfall": {
            "note": ("store-eaten settlement shortfall — the 'cannot pay for "
                     "nothing' asymmetry (§10 Q2): the last-millicent tail the "
                     "store ate, never charged to the agent. A published loss."),
            "total": _money(total_shortfall),
            "calls_with_shortfall": sum(
                1 for r in settled if int(r.get("shortfall_millicents", 0)) > 0),
        },
        "wallets": {
            "distinct_wallets": len(all_wallets),
            "paying_wallets": len(paying_wallets),
            "per_door": per_door,
        },
        "mcp_doors": {
            "note": ("MCP core door (/mcp/, ~15 hero tools) vs pro door "
                     "(/mcp/pro/, full surface) — calls + distinct callers, from "
                     "the additive `mcp_door` telemetry tag (RESHAPE §6). "
                     "'untagged' = an HTTP/legacy MCP record the reshape tagger "
                     "did not stamp; the split populates as tagged traffic lands."),
            "by_door": mcp_doors,
        },
        "funnel": {
            "note": "free_taste is the TOP of the free→paid funnel (STORE.md §6).",
            "free_taste_calls": len(free_tastes),
            "keyed_free_wallets": len(free_keys),
            "keyed_free_to_paid_overlap": len(free_to_paid),
        },
        "throttle": {
            "note": ("429s never reach slot telemetry — throttled demand is "
                     "otherwise invisible to the R-gates (telemetry.log_throttle)."),
            "events": len(throttles),
            "by_scope": dict(sorted(throttle_by_scope.items(),
                                    key=lambda kv: (-kv[1], str(kv[0])))),
        },
        "slots": slots,
        "demand": demand_block,
        "rgates": rgates,
    }

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "observatory.json")
    md_path = os.path.join(out_dir, "observatory.md")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(md_path, "w") as f:
        f.write(_render_md(data))
    data["_artifacts"] = {"json": json_path, "md": md_path}
    return data


def _demand_block(requests: list[dict], demand_note: Optional[str]) -> dict:
    """The demand tally — MECHANICAL exact-match duplicate counting over
    demand._normalize, plus a status breakdown. No fuzzy match, no LLM."""
    if demand_note is not None and not requests:
        return {"available": False, "note": demand_note, "total": 0,
                "distinct": 0, "by_status": {}, "top": []}
    groups: dict[str, dict] = {}
    for r in requests:
        norm = demand._normalize(r["text"])
        g = groups.setdefault(norm, {"text": r["text"], "count": 0,
                                     "statuses": Counter(), "ts": r["ts"]})
        g["count"] += 1
        g["statuses"][r["status"]] += 1
        # Keep the most-recent raw phrasing as the group representative.
        if r["ts"] is not None and (g["ts"] is None or r["ts"] >= g["ts"]):
            g["text"] = r["text"]
            g["ts"] = r["ts"]
    ranked = sorted(groups.values(),
                    key=lambda g: (-g["count"], g["text"]))
    top = [{"text": _sanitize_cell(g["text"]),
            "count": g["count"],
            "by_status": dict(sorted(g["statuses"].items()))}
           for g in ranked[:_DEMAND_TOP_N]]
    by_status = Counter(r["status"] for r in requests)
    return {"available": True, "note": demand_note, "total": len(requests),
            "distinct": len(groups),
            "by_status": dict(sorted(by_status.items())),
            "top": top}


# ─── markdown rendering (house voice; untrusted text stays DATA) ─────────────


def _sanitize_cell(text: str) -> str:
    """Render untrusted request text safe for a markdown table cell: collapse
    whitespace (kills newlines that would break the row), escape the pipe that
    would break the column, and truncate. The text is DATA — this never lets it
    become markdown structure."""
    collapsed = " ".join(str(text).split())
    collapsed = collapsed.replace("|", "\\|")
    if len(collapsed) > _REQUEST_CELL_CHARS:
        collapsed = collapsed[:_REQUEST_CELL_CHARS - 1] + "…"
    return collapsed


def _gate_row(name: str, g: dict) -> str:
    mark = "✓" if g["meets_proposed"] else "·"
    kind = "KILL" if g["kill_relevant"] else "obs"
    return (f"| {name} ({kind}) | {g['count']} | ≥ {g['proposed_threshold']} "
            f"| {mark} |")


def _render_md(d: dict) -> str:
    src = d["source"]
    tot = d["totals"]
    L: list[str] = []
    L.append("# THE STORE — observatory snapshot")
    L.append("")
    L.append("*Mechanical read of the raw records. Every number is a count, a "
             "sum, or an exact-match group — no interpretation, no LLM, no fuzzy "
             "matching. Deterministic given the same inputs.*")
    L.append("")
    L.append(f"- Telemetry: `{src['telemetry_path']}` — "
             f"{src['telemetry_records']} records "
             f"({src['malformed_lines_skipped']} malformed lines skipped)")
    kinds = ", ".join(f"{k} {v}" for k, v in src["records_by_kind"].items())
    L.append(f"- Record kinds: {kinds}")
    L.append(f"- Demand source: `{src['demand_source']}`"
             + (f" — {src['demand_note']}" if src["demand_note"] else ""))
    L.append("")

    # Totals
    L.append("## Store totals")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Slot calls | {tot['slot_calls']} |")
    L.append(f"| Settled (charged) | {tot['settled_calls']} |")
    L.append(f"| Uncharged (non-delivery) | {tot['uncharged_calls']} |")
    sr = tot["settled_rate"]
    L.append(f"| Settled rate | {sr if sr is not None else 'n/a'} |")
    L.append(f"| Spend charged | {tot['price_total']['usd']} "
             f"({tot['price_total']['millicents']} millicents) |")
    L.append(f"| Wholesale cost basis | {tot['wholesale_total']['usd']} "
             f"({tot['wholesale_total']['millicents']} millicents) |")
    sf = d["shortfall"]
    L.append(f"| Store-eaten shortfall | {sf['total']['usd']} "
             f"({sf['total']['millicents']} millicents, "
             f"{sf['calls_with_shortfall']} calls) |")
    L.append("")
    L.append(f"*Shortfall = {sf['note']}*")
    L.append("")

    # Wallets + funnel
    w = d["wallets"]
    fu = d["funnel"]
    L.append("## Wallets & funnel")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Distinct wallets (repeat_keys) | {w['distinct_wallets']} |")
    L.append(f"| Paying wallets (≥1 settled call) | {w['paying_wallets']} |")
    for door, n in w["per_door"].items():
        L.append(f"| Distinct wallets via `{door}` | {n} |")
    md = d.get("mcp_doors", {}).get("by_door", {})
    for variant, m in md.items():
        L.append(f"| MCP `{variant}` door | {m['calls']} calls, "
                 f"{m['distinct_callers']} distinct callers |")
    L.append(f"| free_taste calls | {fu['free_taste_calls']} |")
    L.append(f"| Keyed free wallets | {fu['keyed_free_wallets']} |")
    L.append(f"| Keyed free → paid overlap | {fu['keyed_free_to_paid_overlap']} |")
    L.append("")
    L.append(f"*{fu['note']}*")
    L.append("")

    # Throttle
    th = d["throttle"]
    L.append("## Throttle (429s)")
    L.append("")
    if th["events"] == 0:
        L.append("No throttle events recorded.")
    else:
        L.append("| Scope | Events |")
        L.append("|---|---|")
        for scope, n in th["by_scope"].items():
            L.append(f"| `{scope}` | {n} |")
    L.append("")
    L.append(f"*{th['note']}*")
    L.append("")

    # Per-slot
    L.append("## Per-slot")
    L.append("")
    if not d["slots"]:
        L.append("No slot calls recorded.")
        L.append("")
    for sid, s in d["slots"].items():
        L.append(f"### `{sid}`")
        L.append("")
        L.append("| Metric | Value |")
        L.append("|---|---|")
        L.append(f"| Settled calls | {s['settled_calls']} |")
        L.append(f"| Uncharged calls | {s['uncharged_calls']} |")
        L.append(f"| Spend charged | {s['spend']['price_total']['usd']} "
                 f"({s['spend']['price_total']['millicents']} mc) |")
        L.append(f"| Wholesale cost basis | "
                 f"{s['spend']['wholesale_total']['usd']} "
                 f"({s['spend']['wholesale_total']['millicents']} mc) |")
        ws = s["wholesale_split"]
        L.append(f"| Wholesale exact / estimated (calls) | "
                 f"{ws['exact_calls']} exact / {ws['estimated_calls']} estimated |")
        L.append(f"| Wholesale exact / estimated (cost) | "
                 f"{ws['exact_millicents']['usd']} exact / "
                 f"{ws['estimated_millicents']['usd']} estimated |")
        L.append("")
        if s["uncharged_by_reason"]:
            L.append("Uncharged by reason:")
            L.append("")
            L.append("| Reason code | Calls |")
            L.append("|---|---|")
            for reason, n in s["uncharged_by_reason"].items():
                L.append(f"| {_sanitize_cell(reason)} | {n} |")
            L.append("")
        if s["backend_serves"]:
            L.append("Backend serves (settled):")
            L.append("")
            L.append("| Backend | Serves |")
            L.append("|---|---|")
            for backend, n in s["backend_serves"].items():
                L.append(f"| `{backend}` | {n} |")
            L.append("")

    # Demand
    dm = d["demand"]
    L.append("## Demand — `catalog.request` tally")
    L.append("")
    if not dm.get("available"):
        L.append(f"Demand table unavailable: {dm.get('note')}")
        L.append("")
    else:
        L.append(f"- Total filed: {dm['total']} · distinct asks: {dm['distinct']}")
        if dm["by_status"]:
            st = ", ".join(f"{k} {v}" for k, v in dm["by_status"].items())
            L.append(f"- By status: {st}")
        L.append("")
        L.append("*Exact-match duplicate counts over normalized (whitespace/case "
                 "folded) text — no fuzzy match. Request text is untrusted data, "
                 "rendered truncated and escaped.*")
        L.append("")
        if dm["top"]:
            L.append("| Ask (normalized-group representative) | Filings | Status |")
            L.append("|---|---|---|")
            for a in dm["top"]:
                st = ", ".join(f"{k}:{v}" for k, v in a["by_status"].items())
                L.append(f"| {a['text']} | {a['count']} | {st} |")
            L.append("")

    # R-gates
    rg = d["rgates"]
    L.append("## R-gate progress (P6 — PROXIES)")
    L.append("")
    L.append(f"> {rg['clock_status']}")
    L.append("")
    L.append(f"Self-funded wallets (proxy basis for R1/R2): "
             f"{rg['self_funded_wallets']}")
    L.append("")
    L.append("| Gate | Count | Proposed | Meets? |")
    L.append("|---|---|---|---|")
    L.append(_gate_row("R0 conversion", rg["R0"]))
    L.append(_gate_row("R1 return", rg["R1"]))
    L.append(_gate_row("R2 breadth", rg["R2"]))
    L.append(_gate_row("R3 demand pull", rg["R3"]))
    L.append("")
    L.append("Proxy definitions (a gate is NEVER silently redefined — the label "
             "travels with the number):")
    L.append("")
    for g in ("R0", "R1", "R2", "R3"):
        L.append(f"- **{g}** — {rg[g]['proxy_label']}. *Limits:* "
                 f"{rg[g]['proxy_limits']}")
    L.append("")
    if rg["R3_asks"]:
        L.append("R3 qualifying asks (≥2 distinct wallets):")
        L.append("")
        L.append("| Ask | Filings | Distinct wallets |")
        L.append("|---|---|---|")
        for a in rg["R3_asks"]:
            L.append(f"| {_sanitize_cell(a['text'])} | {a['filings']} "
                     f"| {a['distinct_wallets']} |")
        L.append("")
    else:
        L.append("*No ask has yet reached ≥2 distinct wallets (R3 = 0).*")
        L.append("")

    return "\n".join(L)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="python3 -m vend.observatory",
        description="Render the STORE observatory (observatory.json + .md) from "
                    "the telemetry JSONL and the demand requests table.")
    p.add_argument("--telemetry", default=None,
                   help="path to the telemetry JSONL (default: "
                        "NEXTMOVE_TELEMETRY_PATH or ./nextmove_telemetry.jsonl)")
    p.add_argument("--out-dir", default=None,
                   help="output directory (default: ./observatory/)")
    p.add_argument("--demand-db", default=None,
                   help="path to the demand sqlite DB (default: GT_KEYS_DB). "
                        "Read-only.")
    args = p.parse_args(argv)
    data = snapshot(telemetry_path=args.telemetry, out_dir=args.out_dir,
                    demand_db=args.demand_db)
    print(f"wrote {data['_artifacts']['json']}")
    print(f"wrote {data['_artifacts']['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

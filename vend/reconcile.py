"""THE STORE — the wholesale reconciliation generator (the invoice-grade rung).

Every settled receipt names the backend that served and its exact cost basis.
That is the store's OWN word. This module is the rung above it: it sums the
store's settled receipts per backend and lines them up against a
FOUNDER-SUPPLIED vendor-invoice file, so the monthly ritual — "did what we
billed agents match what the vendor billed us?" — is one command.

HONESTY, stated up front and printed in the output: this generator PROVES
NOTHING until a real vendor invoice is dropped in. With no invoice it emits a
template and a NO INVOICE SUPPLIED verdict for every backend. And even with an
invoice, the ESTIMATED slice of our cost basis (wholesale_estimated=true, where
the upstream reported no usage) is our guess, not the vendor's number — so a
discrepancy there is expected, and the output surfaces the estimated fraction
per backend rather than burying it in a single percentage.

Drop-in invoice format (JSON list; one object per backend per period):

    [
      {
        "backend_id": "jina-reader",       # matches the receipt's backend_id
        "period_start": "2026-07-01",      # ISO date/datetime OR unix seconds
        "period_end":   "2026-08-01",      # half-open [start, end): start ≤ ts < end
        "vendor_reported_calls": 329,      # the vendor's own call count
        "vendor_reported_cost_usd": "1.02" # the vendor's own charge, USD string
      },
      ...
    ]

Period semantics: our settled receipts for a backend are matched to an invoice
line by [period_start, period_end) — inclusive start, EXCLUSIVE end — so
adjacent monthly invoices never double-count a boundary call. A line without a
period matches ALL of that backend's receipts. Timestamps are UTC.

House rules: EXACT arithmetic for money (integer millicents, and Decimal for
the vendor's USD string — never binary float); no LLM; deterministic. READ-ONLY
against the telemetry.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from vend.store import _exact_usd  # one money-display discipline

_MILLICENTS_PER_DOLLAR = 100_000  # 1 dollar = 100 cents = 100_000 millicents
# The verdict band: |cost discrepancy| ≤ this percent → MATCHES. A monthly
# wholesale reconciliation is not expected to be penny-exact (rounding, usage
# rounding, timing at the period boundary), so a small band is honest; anything
# outside it is a DISCREPANCY worth a human look.
_DEFAULT_MATCH_PCT = 1.0


def _parse_ts(value) -> float:
    """Parse an invoice period bound into a UTC unix timestamp. Accepts a unix
    number (int/float) or an ISO date/datetime string. A bare date is midnight
    UTC. Deterministic; no timezone guessing (naive strings are treated UTC)."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # Bare date → midnight UTC.
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt.timestamp()
    except (ValueError, IndexError):
        pass
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _load_settled(telemetry_path: str) -> list[dict]:
    """Read settled slot_call receipts from the telemetry JSONL (read-only).
    Malformed/blank lines are skipped silently here — the observatory is the
    place that reports the skip count; reconcile only needs the receipts."""
    out: list[dict] = []
    with open(telemetry_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") == "slot_call" and r.get("settled"):
                out.append(r)
    return out


def _in_period(ts, start: Optional[float], end: Optional[float]) -> bool:
    """Half-open [start, end). A None bound is open on that side."""
    if ts is None:
        return start is None and end is None
    if start is not None and ts < start:
        return False
    if end is not None and ts >= end:
        return False
    return True


def _template() -> list[dict]:
    """The drop-in invoice template a founder fills from a real vendor bill."""
    return [{
        "backend_id": "REPLACE-with-backend_id-from-receipts",
        "period_start": "2026-07-01",
        "period_end": "2026-08-01",
        "vendor_reported_calls": 0,
        "vendor_reported_cost_usd": "0.00",
        "_comment": ("one object per backend per billing period; period is "
                     "half-open [start, end); cost is a USD string, not a float"),
    }]


def reconcile(telemetry_path: str,
              invoices_path: Optional[str] = None,
              out_dir: Optional[str] = None,
              match_threshold_pct: float = _DEFAULT_MATCH_PCT) -> dict:
    """Sum settled receipts per backend and compare to a founder-supplied vendor
    invoice file. Writes reconcile.json + reconcile.md into out_dir; returns the
    machine dict.

    If invoices_path is None or the file is missing, a template is written
    (to invoices_path when a path was given, else out_dir/invoices.template.json)
    and EVERY backend gets a NO INVOICE SUPPLIED verdict — the ritual runs, the
    proof waits for real numbers."""
    out_dir = out_dir or os.path.join(os.getcwd(), "reconcile")
    os.makedirs(out_dir, exist_ok=True)

    settled = _load_settled(telemetry_path)

    # Load invoices (or note their absence and emit a template).
    invoices: list[dict] = []
    invoice_note = None
    template_written = None
    if invoices_path and os.path.exists(invoices_path):
        with open(invoices_path) as f:
            invoices = json.load(f)
        if not isinstance(invoices, list):
            raise ValueError("invoice file must be a JSON list of backend lines")
    else:
        invoice_note = ("NO INVOICE SUPPLIED — this run proves nothing. Fill the "
                        "template with a real vendor bill and re-run.")
        template_path = invoices_path or os.path.join(out_dir,
                                                      "invoices.template.json")
        # Never overwrite a file that already exists (it might be a real invoice
        # the caller mistyped a path to). Only write when nothing is there.
        if not os.path.exists(template_path):
            with open(template_path, "w") as f:
                json.dump(_template(), f, indent=2)
                f.write("\n")
            template_written = template_path

    # Index invoices by backend_id (a backend may have several period lines).
    inv_by_backend: dict[str, list[dict]] = {}
    for line in invoices:
        inv_by_backend.setdefault(line["backend_id"], []).append(line)

    backends = sorted({r.get("backend_id") for r in settled if r.get("backend_id")}
                      | set(inv_by_backend))
    per_backend: list[dict] = []
    for bid in backends:
        b_settled = [r for r in settled if r.get("backend_id") == bid]
        lines = inv_by_backend.get(bid, [])
        if not lines:
            # We have receipts but no invoice line for this backend.
            per_backend.append(_no_invoice_backend(bid, b_settled))
            continue
        for line in lines:
            per_backend.append(
                _reconcile_line(bid, b_settled, line, match_threshold_pct))

    data = {
        "schema": "reconcile.v1",
        "disclaimer": ("This is the invoice-grade wholesale-proof rung. It "
                       "proves NOTHING until real vendor invoices are dropped in "
                       "(see the module docstring for the format). The estimated "
                       "slice of our cost basis is our guess, not the vendor's — "
                       "reconcile the exact slice, treat estimated as advisory."),
        "source": {
            "telemetry_path": telemetry_path,
            "settled_receipts": len(settled),
            "invoices_path": invoices_path,
            "invoice_note": invoice_note,
            "template_written": template_written,
            "match_threshold_pct": match_threshold_pct,
        },
        "backends": per_backend,
    }

    json_path = os.path.join(out_dir, "reconcile.json")
    md_path = os.path.join(out_dir, "reconcile.md")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(md_path, "w") as f:
        f.write(_render_md(data))
    data["_artifacts"] = {"json": json_path, "md": md_path}
    return data


def _receipt_totals(b_settled: list[dict]) -> dict:
    """Our own numbers for a backend's receipts: call count, wholesale total
    (exact integer millicents), and the estimated/exact split."""
    total_mc = sum(int(r.get("wholesale_millicents", 0)) for r in b_settled)
    est = [r for r in b_settled if r.get("wholesale_estimated")]
    exact = [r for r in b_settled if not r.get("wholesale_estimated")]
    return {
        "receipt_calls": len(b_settled),
        "receipt_wholesale_millicents": total_mc,
        "receipt_wholesale_usd": _exact_usd(total_mc),
        "estimated_calls": len(est),
        "exact_calls": len(exact),
        "estimated_millicents": sum(int(r.get("wholesale_millicents", 0))
                                    for r in est),
    }


def _no_invoice_backend(bid: str, b_settled: list[dict]) -> dict:
    t = _receipt_totals(b_settled)
    t.update({
        "backend_id": bid,
        "period": None,
        "vendor_reported_calls": None,
        "vendor_reported_cost_usd": None,
        "cost_discrepancy_usd": None,
        "cost_discrepancy_pct": None,
        "call_discrepancy": None,
        "verdict": "NO INVOICE SUPPLIED",
    })
    return t


def _reconcile_line(bid: str, b_settled: list[dict], line: dict,
                    match_pct: float) -> dict:
    start = _parse_ts(line["period_start"]) if line.get("period_start") is not None else None
    end = _parse_ts(line["period_end"]) if line.get("period_end") is not None else None
    in_window = [r for r in b_settled if _in_period(r.get("ts"), start, end)]
    t = _receipt_totals(in_window)

    vendor_calls = line.get("vendor_reported_calls")
    # EXACT: parse the vendor's USD string via Decimal, convert to millicents.
    vendor_usd = Decimal(str(line["vendor_reported_cost_usd"]))
    vendor_mc = vendor_usd * _MILLICENTS_PER_DOLLAR   # Decimal, may be fractional
    our_mc = Decimal(t["receipt_wholesale_millicents"])

    cost_disc_mc = our_mc - vendor_mc                 # + means we billed MORE
    if vendor_mc != 0:
        cost_disc_pct = float((cost_disc_mc / vendor_mc) * 100)
    else:
        cost_disc_pct = None  # can't divide by a zero vendor charge
    call_disc = (t["receipt_calls"] - vendor_calls
                 if vendor_calls is not None else None)

    if cost_disc_pct is None:
        verdict = "DISCREPANCY (vendor cost is $0 — cannot compute a percentage)"
    elif abs(cost_disc_pct) <= match_pct:
        verdict = f"MATCHES within {match_pct}%"
    else:
        verdict = "DISCREPANCY"
    # Estimated-slice honesty rider on the verdict.
    if t["estimated_calls"] and verdict.startswith("MATCHES"):
        verdict += (f" (note: {t['estimated_calls']}/{t['receipt_calls']} calls "
                    "were ESTIMATED cost basis — match is partial proof)")

    t.update({
        "backend_id": bid,
        "period": {"start": line.get("period_start"),
                   "end": line.get("period_end")},
        "vendor_reported_calls": vendor_calls,
        "vendor_reported_cost_usd": str(line["vendor_reported_cost_usd"]),
        "cost_discrepancy_usd": _signed_usd(cost_disc_mc),
        "cost_discrepancy_pct": (round(cost_disc_pct, 4)
                                 if cost_disc_pct is not None else None),
        "call_discrepancy": call_disc,
        "verdict": verdict,
    })
    return t


def _signed_usd(millicents: Decimal) -> str:
    """Signed exact USD string for a (possibly fractional, possibly negative)
    millicent Decimal. Reuses the store's unsigned formatter on the magnitude so
    the display discipline is shared; the sign is prepended."""
    neg = millicents < 0
    mag = -millicents if neg else millicents
    # Whole-millicent magnitudes format exactly; a fractional remainder (from a
    # vendor USD string finer than a millicent) is appended so nothing is hidden.
    whole = int(mag)
    frac = mag - whole
    s = _exact_usd(whole)
    if frac != 0:
        # Show the sub-millicent tail exactly (Decimal), no rounding.
        s = s + f"(+{frac} millicents)"
    return ("-" + s) if neg else s


def _render_md(d: dict) -> str:
    src = d["source"]
    L: list[str] = []
    L.append("# THE STORE — wholesale reconciliation")
    L.append("")
    L.append(f"> {d['disclaimer']}")
    L.append("")
    L.append(f"- Telemetry: `{src['telemetry_path']}` — "
             f"{src['settled_receipts']} settled receipts")
    L.append(f"- Invoices: `{src['invoices_path']}`")
    if src["invoice_note"]:
        L.append(f"- **{src['invoice_note']}**")
    if src["template_written"]:
        L.append(f"- Template written: `{src['template_written']}` — fill it "
                 "from a real vendor bill and re-run.")
    L.append(f"- Match band: ±{src['match_threshold_pct']}%")
    L.append("")
    L.append("| Backend | Period | Our calls | Vendor calls | Our cost | "
             "Vendor cost | Δ cost | Δ % | Verdict |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for b in d["backends"]:
        period = "—"
        if b["period"]:
            period = f"{b['period']['start']}→{b['period']['end']}"
        vcalls = "—" if b["vendor_reported_calls"] is None else b["vendor_reported_calls"]
        vcost = "—" if b["vendor_reported_cost_usd"] is None else f"${b['vendor_reported_cost_usd']}"
        dcost = "—" if b["cost_discrepancy_usd"] is None else b["cost_discrepancy_usd"]
        dpct = "—" if b["cost_discrepancy_pct"] is None else f"{b['cost_discrepancy_pct']}%"
        L.append(f"| `{b['backend_id']}` | {period} | {b['receipt_calls']} "
                 f"| {vcalls} | {b['receipt_wholesale_usd']} | {vcost} "
                 f"| {dcost} | {dpct} | {b['verdict']} |")
    L.append("")
    L.append("*Δ cost = our receipts − vendor invoice (positive = we billed "
             "agents MORE than the vendor billed us). The estimated slice of a "
             "backend's cost basis is our guess, not the vendor's — see each "
             "backend's estimated_calls in reconcile.json.*")
    L.append("")
    return "\n".join(L)


def _main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="python3 -m vend.reconcile",
        description="Reconcile settled store receipts against founder-supplied "
                    "vendor invoices (the invoice-grade wholesale-proof rung).")
    p.add_argument("--telemetry", required=True,
                   help="path to the telemetry JSONL")
    p.add_argument("--invoices", default=None,
                   help="path to the vendor invoice JSON (see module docstring "
                        "for the format). If missing, a template is emitted.")
    p.add_argument("--out-dir", default=None,
                   help="output directory (default: ./reconcile/)")
    p.add_argument("--match-pct", type=float, default=_DEFAULT_MATCH_PCT,
                   help=f"MATCHES band, percent (default: {_DEFAULT_MATCH_PCT})")
    args = p.parse_args(argv)
    data = reconcile(telemetry_path=args.telemetry, invoices_path=args.invoices,
                     out_dir=args.out_dir, match_threshold_pct=args.match_pct)
    print(f"wrote {data['_artifacts']['json']}")
    print(f"wrote {data['_artifacts']['md']}")
    if data["source"]["invoice_note"]:
        print(data["source"]["invoice_note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

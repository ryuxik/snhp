"""Append-only, hash-chained receipt ledger (SPEC v33: "each with a wallet on a
hash-chained ledger (paperswarm pattern)"). Adapted from paperswarm/ledger.py.

Two things live here:

  1. `Chain` — the taxonomy-agnostic hash-chained JSONL primitive. Each record
     carries prev_hash + sha256(self); any edit breaks the chain. Resumable
     (reads the existing file), append-only, `verify_chain()` recomputes it.
     Used for BOTH the money ledger and the event log (events.py).

  2. The MONEY ledger — a `Chain` with double-entry receipts and a `Wallets`
     fold. Every settlement, split and metered spend is a receipt on the chain
     (SPEC v33 D1a: "artifact logger ... token meter"; v33-A: "the company's
     entire selection loop runs on the attested ledger"). Double-entry (every
     receipt debits one account and credits another by the same amount) makes
     conservation checkable: the signed balances always sum to zero.

v33-A provenance spine: settle/spend receipts carry an `idea` tag and a `role`,
so per-idea P&L and per-agent/per-role receipt flow are pure folds of the chain.
A null `sig` field is reserved for notary signing (paperswarm parity).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

GENESIS_PREV = "0" * 64

# ---------------------------------------------------------------------------
# Money receipt taxonomy (double-entry). `data` always carries debit/credit
# account strings + amount; settle/spend also carry provenance tags.
# ---------------------------------------------------------------------------
EV_FUND = "fund"       # external capital -> an account (treasury / compute_budget)
EV_ESCROW = "escrow"   # treasury -> escrow:<task> (a bounty is posted/funded)
EV_SETTLE = "settle"   # escrow:<task> -> agent:<id> (a role's split, on merge)
EV_REFUND = "refund"   # escrow:<task> -> treasury (unpaid remainder on close)
EV_SPEND = "spend"     # compute_budget -> external:compute (metered token cost)
# v33-B/G: a bounty may be funded from an external BUYER wallet instead of the
# internal treasury (the demand-side bill of lading — an escrowed pre-order).
EV_BUYER_FUND = "buyer_fund"      # external:capital -> buyer:<id> (pre-order deposit)
EV_BUYER_ESCROW = "buyer_escrow"  # buyer:<id> -> escrow:<task> (order escrowed to work)
EV_BUYER_REFUND = "buyer_refund"  # escrow:<task> -> buyer:<id> (unaccepted order returns)
# v33-D: an agent pledge stakes its own wallet on an idea's exploration fund.
EV_PLEDGE = "pledge_credit"       # agent:<id> -> idea_fund:<idea>
# v35-S (column CO2-S): the three-org settlement / hold-up chain. A leg's REAL
# cost is sunk from the performing org's wallet; the terminal payment reaches C
# and then either auto-distributes (claim-stack) or is forwarded hop-by-hop up
# the chain by the holders themselves (spot). These two receipts + escrow_release
# are the only new money movements; WHERE the money lands is the experiment.
EV_LEG_COST = "leg_cost"          # agent:<org> -> external:effort (sink cost of a leg)
EV_FORWARD = "forward"            # agent:<from> -> agent:<to> (voluntary up-chain forward)
EV_ESCROW_RELEASE = "escrow_release"  # escrow:<task> -> agent:<org> (terminal / attested payout)

# Account name helpers (string keys the Wallets fold sums over).
ACCT_TREASURY = "treasury"
ACCT_COMPUTE = "compute_budget"
ACCT_EXT_CAPITAL = "external:capital"
ACCT_EXT_COMPUTE = "external:compute"
ACCT_EXT_EFFORT = "external:effort"   # where sunk leg costs go (real effort spent)


def acct_agent(agent_id: str) -> str:
    return f"agent:{agent_id}"


def acct_escrow(task_id: str) -> str:
    return f"escrow:{task_id}"


def acct_buyer(buyer_id: str) -> str:
    return f"buyer:{buyer_id}"


def acct_idea_fund(idea_id: str) -> str:
    return f"idea_fund:{idea_id}"


def _canonical(obj: dict) -> str:
    """Deterministic JSON for hashing (sorted keys, compact, ASCII-safe)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(seq: int, ts: str, ev_type: str, data: dict,
                 prev_hash: str, sig) -> str:
    """sha256 over the canonical record body (everything but `hash`)."""
    body = _canonical({
        "seq": seq, "ts": ts, "type": ev_type,
        "data": data, "prev_hash": prev_hash, "sig": sig,
    })
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    ts: str
    type: str
    data: dict
    prev_hash: str
    sig: object
    hash: str

    def to_json(self) -> str:
        return json.dumps({
            "seq": self.seq, "ts": self.ts, "type": self.type,
            "data": self.data, "prev_hash": self.prev_hash,
            "sig": self.sig, "hash": self.hash,
        }, sort_keys=True, separators=(",", ":"))


class Chain:
    """Hash-chained append-only JSONL log. Base for the money ledger and the
    event log. Resumable: construction does not read the file; reads stream it
    lazily so a partially written episode can be resumed by re-folding."""

    def __init__(self, path):
        self.path = Path(path)
        if str(self.path) != os.devnull:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- reads -------------------------------------------------------------
    def records(self) -> Iterator[Record]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                yield Record(
                    seq=d["seq"], ts=d["ts"], type=d["type"], data=d["data"],
                    prev_hash=d["prev_hash"], sig=d.get("sig"), hash=d["hash"],
                )

    def all(self) -> list[Record]:
        return list(self.records())

    def last(self) -> Record | None:
        last = None
        for rec in self.records():
            last = rec
        return last

    def head_hash(self) -> str:
        last = self.last()
        return last.hash if last else GENESIS_PREV

    def next_seq(self) -> int:
        last = self.last()
        return (last.seq + 1) if last else 0

    def __len__(self) -> int:
        return sum(1 for _ in self.records())

    # -- writes ------------------------------------------------------------
    def append(self, ev_type: str, data: dict, *, ts: str, sig=None) -> Record:
        """Append a receipt, chaining onto the current head. `ts` is supplied by
        the caller's logical Clock (timeutil.py) so runs are reproducible."""
        seq = self.next_seq()
        prev_hash = self.head_hash()
        h = compute_hash(seq, ts, ev_type, data, prev_hash, sig)
        rec = Record(seq, ts, ev_type, data, prev_hash, sig, h)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(rec.to_json() + "\n")
        return rec


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    length: int
    error_seq: int | None = None
    error: str | None = None


def verify_chain(path) -> ChainResult:
    """Recompute the whole chain. Fails on broken prev_hash linkage, a
    recomputed hash that differs from the stored hash (content tamper), or a
    non-contiguous seq. First failure wins. (paperswarm parity.)"""
    chain = Chain(path)
    prev = GENESIS_PREV
    expected_seq = 0
    n = 0
    for rec in chain.records():
        n += 1
        if rec.seq != expected_seq:
            return ChainResult(False, n, rec.seq,
                               f"seq gap: expected {expected_seq}, got {rec.seq}")
        if rec.prev_hash != prev:
            return ChainResult(False, n, rec.seq,
                               "prev_hash mismatch (chain broken)")
        recomputed = compute_hash(rec.seq, rec.ts, rec.type, rec.data,
                                  rec.prev_hash, rec.sig)
        if recomputed != rec.hash:
            return ChainResult(False, n, rec.seq,
                               "hash mismatch (content tampered)")
        prev = rec.hash
        expected_seq += 1
    return ChainResult(True, n)


class Ledger(Chain):
    """The MONEY ledger: a Chain of double-entry receipts + typed constructors.

    Every money receipt names `debit` and `credit` accounts and an `amount`;
    settle/spend also carry `idea`/`role`/`agent` tags for the provenance spine
    (v33-A). Balances and provenance aggregates are pure folds (`Wallets`)."""

    def fund(self, credit: str, amount: float, *, ts: str) -> Record:
        return self.append(EV_FUND, {
            "debit": ACCT_EXT_CAPITAL, "credit": credit, "amount": amount,
        }, ts=ts)

    def escrow(self, task_id: str, amount: float, *, idea: str, ts: str) -> Record:
        return self.append(EV_ESCROW, {
            "debit": ACCT_TREASURY, "credit": acct_escrow(task_id),
            "amount": amount, "task": task_id, "idea": idea,
        }, ts=ts)

    def escrow_from_fund(self, task_id: str, amount: float, *, idea: str,
                         ts: str) -> Record:
        """Fund a bounty from an idea's PLEDGE fund (v33-D): self-investment pays
        for its own exploration work rather than drawing the shared treasury."""
        return self.append(EV_ESCROW, {
            "debit": acct_idea_fund(idea), "credit": acct_escrow(task_id),
            "amount": amount, "task": task_id, "idea": idea, "source": "idea_fund",
        }, ts=ts)

    def settle(self, task_id: str, agent_id: str, amount: float, *,
               role: str, idea: str, commit: str, test_digest: str,
               ts: str) -> Record:
        return self.append(EV_SETTLE, {
            "debit": acct_escrow(task_id), "credit": acct_agent(agent_id),
            "amount": amount, "task": task_id, "idea": idea,
            "role": role, "agent": agent_id,
            "commit": commit, "test_digest": test_digest,
        }, ts=ts)

    def refund(self, task_id: str, amount: float, *, idea: str, ts: str) -> Record:
        return self.append(EV_REFUND, {
            "debit": acct_escrow(task_id), "credit": ACCT_TREASURY,
            "amount": amount, "task": task_id, "idea": idea,
        }, ts=ts)

    def spend(self, amount: float, *, agent_id: str, idea: str | None,
              turn: int, reason: str, ts: str) -> Record:
        """Metered token cost (SPEC v33 D1a token meter). Attributed to the
        IDEA whose task consumed the turn (v33-A: "token costs charged
        per-idea"); `idea` is None for org overhead with no task referent."""
        return self.append(EV_SPEND, {
            "debit": ACCT_COMPUTE, "credit": ACCT_EXT_COMPUTE,
            "amount": amount, "agent": agent_id, "idea": idea,
            "turn": turn, "reason": reason,
        }, ts=ts)

    # -- v33-B/G: external buyer wallet (arms-length demand) ----------------
    def buyer_fund(self, buyer_id: str, amount: float, *, ts: str) -> Record:
        """External capital deposits into a buyer wallet (the buyer is outside the
        org, outside allocation — no wallet flows org->buyer; enforced by the
        runner never crediting a buyer from an idea)."""
        return self.append(EV_BUYER_FUND, {
            "debit": ACCT_EXT_CAPITAL, "credit": acct_buyer(buyer_id),
            "amount": amount, "buyer": buyer_id,
        }, ts=ts)

    def buyer_escrow(self, task_id: str, buyer_id: str, amount: float, *,
                     idea: str, ts: str) -> Record:
        """A buyer's pre-order escrows against a spec+tests BEFORE work (v33-B1)."""
        return self.append(EV_BUYER_ESCROW, {
            "debit": acct_buyer(buyer_id), "credit": acct_escrow(task_id),
            "amount": amount, "task": task_id, "idea": idea, "buyer": buyer_id,
        }, ts=ts)

    def buyer_refund(self, task_id: str, buyer_id: str, amount: float, *,
                     idea: str, ts: str) -> Record:
        """Return an unaccepted / cut buyer order to the buyer wallet."""
        return self.append(EV_BUYER_REFUND, {
            "debit": acct_escrow(task_id), "credit": acct_buyer(buyer_id),
            "amount": amount, "task": task_id, "idea": idea, "buyer": buyer_id,
        }, ts=ts)

    # -- v35-S: three-org settlement chain (CO2-S) -------------------------
    def leg_cost(self, org_id: str, amount: float, *, task_id: str, leg: str,
                 ts: str) -> Record:
        """An org sinks the REAL cost of performing its leg (budget/effort). The
        credits leave the org's wallet for good — this is the sunk cost that makes
        a hold-up at settlement a real loss to the upstream org."""
        return self.append(EV_LEG_COST, {
            "debit": acct_agent(org_id), "credit": ACCT_EXT_EFFORT,
            "amount": amount, "task": task_id, "org": org_id, "leg": leg,
        }, ts=ts)

    def escrow_release(self, task_id: str, org_id: str, amount: float, *,
                       reason: str, ts: str) -> Record:
        """The buyer's escrow pays an org. In SPOT this fires ONCE, to C (the
        terminal holder). In CLAIM-STACK it fires per attested share, one release
        to each org directly (C never custodies A's or B's share)."""
        return self.append(EV_ESCROW_RELEASE, {
            "debit": acct_escrow(task_id), "credit": acct_agent(org_id),
            "amount": amount, "task": task_id, "org": org_id, "reason": reason,
        }, ts=ts)

    def forward(self, from_org: str, to_org: str, amount: float, *,
                task_id: str, ts: str) -> Record:
        """A voluntary up-chain forward (SPOT only): the holder sends part of what
        it holds to the org above it. What it does not forward, it keeps — the
        free choice the hold-up experiment measures."""
        return self.append(EV_FORWARD, {
            "debit": acct_agent(from_org), "credit": acct_agent(to_org),
            "amount": amount, "task": task_id, "from": from_org, "to": to_org,
        }, ts=ts)

    # -- v33-D: agent pledge (self-investment) -----------------------------
    def pledge(self, agent_id: str, idea_id: str, amount: float, *,
               ts: str) -> Record:
        """An agent stakes its own wallet credits on an idea's exploration fund in
        exchange for a claim on future receipts (v33-D §3 / B2 pulled forward)."""
        return self.append(EV_PLEDGE, {
            "debit": acct_agent(agent_id), "credit": acct_idea_fund(idea_id),
            "amount": amount, "agent": agent_id, "idea": idea_id,
        }, ts=ts)


class Wallets:
    """Balances + provenance aggregates, folded from the money Ledger. Nothing
    here is stored; it all regenerates from the chain (SPEC v33: "shows NOTHING
    that is not derivable from this chain")."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def balances(self) -> dict[str, float]:
        bal: dict[str, float] = defaultdict(float)
        for rec in self.ledger.records():
            d = rec.data
            if "debit" in d:
                bal[d["debit"]] -= d["amount"]
                bal[d["credit"]] += d["amount"]
        return dict(bal)

    def balance(self, account: str) -> float:
        return round(self.balances().get(account, 0.0), 10)

    def agent_balance(self, agent_id: str) -> float:
        return self.balance(acct_agent(agent_id))

    # -- provenance spine (v33-A) -----------------------------------------
    def agent_receipts(self, agent_id: str, role: str | None = None) -> float:
        """Total receipt flow THROUGH an agent — spec + implement + review
        credits (v33-A: "middle roles included ... glue work is visible by
        construction"). Optionally filter to one role."""
        total = 0.0
        for rec in self.ledger.records():
            if rec.type != EV_SETTLE:
                continue
            d = rec.data
            if d.get("agent") != agent_id:
                continue
            if role is not None and d.get("role") != role:
                continue
            total += d["amount"]
        return round(total, 10)

    def idea_settled(self, idea: str) -> float:
        return round(sum(r.data["amount"] for r in self.ledger.records()
                         if r.type == EV_SETTLE and r.data.get("idea") == idea), 10)

    def idea_spend(self, idea: str) -> float:
        return round(sum(r.data["amount"] for r in self.ledger.records()
                         if r.type == EV_SPEND and r.data.get("idea") == idea), 10)

    def idea_pnl(self, idea: str) -> float:
        """An idea's value (v33-A): settled receipts net of its metered spend."""
        return round(self.idea_settled(idea) - self.idea_spend(idea), 10)

    def total_spend(self) -> float:
        return round(sum(r.data["amount"] for r in self.ledger.records()
                         if r.type == EV_SPEND), 10)

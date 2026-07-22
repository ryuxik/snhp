"""bridge.py — the MPX mount (SPEC.md §7).

An adapter that runs an NX session where MPX (`meridian/protocol.py`) would run
its price-only counter loop. Buyer and seller policies are supplied as callables;
this module ships a REFERENCE PAIR:

  - seller policy: builds an NX list schedule over a (qty, ship_date) grid using
    MERIDIAN's OWN cost function (`meridian.agents.supplier_cost`, the single
    source of truth), opens with MPX's quoted config at list, and accepts any
    package that clears its min-markup floor (else concedes price up to it);
  - buyer policy: `gt_negotiate_bundle` — the engine's plain-terms logrolling
    tool (`gametheory/server/mcp_server.py`) — selecting a package over the
    (terms, price-split) issue set restricted to IR-feasible configs, so the
    buyer moves qty and ship_date as well as price where MPX could only move
    price.

meridian and gametheory are imported READ-ONLY. All policies are deterministic
(np.random is seeded before each bundle call; the reference buyer passes no
counter-offer history, so the tool's weak priority-inference layer is inert —
NX's edge comes from bundle EXPRESSIVENESS, not out-guessing the counterparty).

I4 worked example: `notary_attestation` signs the settled transcript hash with
the SNHP notary's Ed25519 key (`core/notary.py`) as ONE conforming attestor;
the spec stays attestor-neutral.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

# --- read-only imports of meridian + gametheory (repo root + snhp on path) ---
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SNHP = os.path.join(_ROOT, "snhp")
for _p in (_ROOT, _SNHP):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from meridian.agents import (buyer_gross_value, joint_surplus,  # noqa: E402
                             supplier_cost)
from meridian.audit import _levels  # noqa: E402  (the same qty/date level grid)
from gametheory.server.mcp_server import gt_negotiate_bundle  # noqa: E402

from nx.protocol import (Line, ListSchedule, NXPropose, NXQuote,  # noqa: E402
                         NXReceipt, NXSession, State, schedule_key)

_EPS = 1e-6
GRID_N = 6            # qty levels x date levels (<= GRID_N^2 configs)
DEFAULT_MAX_ROUNDS = 8


# ── the meridian-shaped RFQ (one buyer line vs one supplier) ────────────────
@dataclass(frozen=True)
class MPXScenario:
    """One MPX-shaped procurement: a buyer demand line and the supplier it is
    matched to. Fields mirror `meridian.market.RFQRecord` / `SupplierParams`."""

    session_ref: str
    item: str
    need_qty: int
    need_by: int
    unit_value: float
    urgency: float
    c0: float
    c1: float
    cap: float
    expedite: float
    inventory: float
    markup: float          # seller opening/list markup over cost
    min_markup: float      # seller walk-away floor markup (meridian's floor)


# ── economics (all via meridian's utility functions) ────────────────────────
def _cost(s: MPXScenario, q: int, d: int) -> float:
    return supplier_cost(q, d, s.c0, s.c1, s.cap, s.expedite)


def list_price(s: MPXScenario, q: int, d: int) -> float:
    return _cost(s, q, d) * (1.0 + s.markup)


def floor_price(s: MPXScenario, q: int, d: int) -> float:
    """The seller's walk-away for a config: min-markup over cost — meridian's
    SupplierAgent floor, used IDENTICALLY across all three experiment arms."""
    return _cost(s, q, d) * (1.0 + s.min_markup)


def reservation(s: MPXScenario, q: int, d: int) -> float:
    """The most the buyer will pay for (q, d): its gross value after lateness
    decay (meridian's BuyerAgent.reservation)."""
    lateness = max(0, d - s.need_by)
    return buyer_gross_value(q, s.need_qty, s.unit_value, s.urgency, lateness)


def config_grid(s: MPXScenario) -> list:
    """The (qty, ship_date) grid the schedule + oracle range over. qty up to what
    inventory/need allow; ship_date from 1 to the natural lead (includes
    expedited dates below natural — matching `meridian.audit.oracle_best`)."""
    qmax = max(1, min(int(s.need_qty), int(s.inventory)))
    natural = max(1, math.ceil(qmax / s.cap)) if s.cap > 0 else 1
    qs = _levels(1, qmax, GRID_N)
    ds = _levels(1, natural, GRID_N)
    return [(q, d) for q in qs for d in ds]


def quoted_config(s: MPXScenario) -> tuple:
    """MPX's own quote (`SupplierAgent.quote_terms`): full qty at the natural
    lead. This is what the checkout / cheap-haggle arms are stuck with."""
    qmax = max(1, min(int(s.need_qty), int(s.inventory)))
    natural = max(1, math.ceil(qmax / s.cap)) if s.cap > 0 else 1
    return qmax, natural


def feasible_configs(s: MPXScenario) -> list:
    """Configs whose ZOPA is nonempty: buyer reservation clears the seller's
    min-markup floor."""
    return [(q, d) for (q, d) in config_grid(s)
            if reservation(s, q, d) >= floor_price(s, q, d) + _EPS]


def oracle_joint(s: MPXScenario) -> float:
    """Max joint surplus over the grid (price cancels) — the achievable pie."""
    best = 0.0
    for (q, d) in config_grid(s):
        J = joint_surplus(q, d, s.need_qty, s.need_by, s.unit_value, s.urgency,
                          s.c0, s.c1, s.cap, s.expedite)
        best = max(best, J)
    return best


def realized_joint(s: MPXScenario, q: int, d: int) -> float:
    return joint_surplus(q, d, s.need_qty, s.need_by, s.unit_value, s.urgency,
                         s.c0, s.c1, s.cap, s.expedite)


# ── the seller's list schedule + reference policies ─────────────────────────
def build_schedule(s: MPXScenario) -> ListSchedule:
    """Seller commits a list_price for every servable config (the I1 authority)."""
    return ListSchedule.from_map(
        {schedule_key(s.item, q, d): list_price(s, q, d)
         for (q, d) in config_grid(s)})


def seller_open(s: MPXScenario) -> NXQuote:
    """Opening NX-QUOTE: MPX's quoted config (full qty, natural lead) at list."""
    sched = build_schedule(s)
    q0, d0 = quoted_config(s)
    pkg = (Line("L0", s.item, q0, d0, list_price(s, q0, d0), list_price(s, q0, d0)),)
    return NXQuote(s.session_ref, sched, pkg)


# policy return protocol: (action, payload)
#   ("propose", Package) | ("accept", None) | ("decline", reason)
BuyerPolicy = Callable[[MPXScenario, NXSession], tuple]
SellerPolicy = Callable[[MPXScenario, NXSession], tuple]


def reference_buyer(s: MPXScenario, session: NXSession) -> tuple:
    """Reference buyer: pick a package via `gt_negotiate_bundle` (logrolling
    terms against the price split) restricted to IR-feasible configs, then
    accept the seller's standing package if it already beats that package.

    A rational bundle-capable buyer deals whenever a feasible config exists, so
    if the tool's normalized-BATNA heuristic would walk while feasible configs
    remain, the buyer defaults to its max-own-surplus feasible config. This
    models bundle EXPRESSIVENESS (deal iff any config feasible), symmetric with
    the cheap-haggle arm's price-only frontier (deal iff the quoted config is
    feasible)."""
    feas = feasible_configs(s)
    if not feas:
        return ("decline", "no config clears both walk-aways")

    # already-good check: is the seller's standing package good enough to accept?
    stand = session.standing_package
    if stand is not None and _buyer_ok(s, stand):
        # accept only if it beats our best achievable own-surplus by a hair
        best_conf, best_price, _ = _best_feasible(s, feas)
        stand_surplus = _pkg_buyer_surplus(s, stand)
        our_surplus = reservation(s, *best_conf) - best_price
        if stand_surplus >= our_surplus - _EPS:
            return ("accept", None)

    conf, price = _bundle_pick(s, feas)
    q, d = conf
    pkg = (Line("L0", s.item, q, d, list_price(s, q, d), price),)
    return ("propose", pkg)


def reference_seller(s: MPXScenario, session: NXSession) -> tuple:
    """Reference seller: accept any standing package that clears its min-markup
    floor on every line; otherwise concede — re-propose the SAME configs at the
    floor price (a valid <=list price, I1)."""
    pkg = session.standing_package
    if pkg is None:
        return ("decline", "nothing on the table")
    if _seller_ok(s, pkg):
        return ("accept", None)
    conceded = tuple(
        Line(ln.line_id, ln.item, ln.qty, ln.ship_date,
             list_price(s, ln.qty, ln.ship_date), floor_price(s, ln.qty, ln.ship_date))
        for ln in pkg)
    return ("propose", conceded)


# --- policy helpers ---------------------------------------------------------
def _best_feasible(s: MPXScenario, feas: list) -> tuple:
    """The feasible config maximizing buyer surplus at the ZOPA midpoint."""
    best = None
    for (q, d) in feas:
        fl, res = floor_price(s, q, d), reservation(s, q, d)
        mid = fl + 0.5 * (res - fl)
        surplus = res - mid
        if best is None or surplus > best[2]:
            best = ((q, d), mid, surplus)
    return best


def _bundle_pick(s: MPXScenario, feas: list) -> tuple:
    """Choose (config, price) via gt_negotiate_bundle over two issues: `terms`
    (the feasible configs — buyer likes high delivered value, seller likes low
    serve-cost) and `price_split` (fraction of the chosen config's ZOPA). Falls
    back to the max-own-surplus feasible config if the tool walks."""
    np.random.seed(0)  # determinism: the particle filter draws from global np.random
    term_opts = [schedule_key(s.item, q, d) for (q, d) in feas]
    my_terms = [reservation(s, q, d) for (q, d) in feas]        # buyer: value
    their_terms = [-_cost(s, q, d) for (q, d) in feas]           # seller: low cost
    splits = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    my_split = [1.0 - x for x in splits]                         # buyer: low price
    their_split = list(splits)                                   # seller: high price
    issues = [
        {"name": "terms", "options": term_opts,
         "my_utility": my_terms, "their_utility": their_terms},
        {"name": "price_split", "options": splits,
         "my_utility": my_split, "their_utility": their_split},
    ]
    try:
        rec = gt_negotiate_bundle(issues=issues, my_batna=0.0,
                                  their_batna_estimate=0.0)
        offer = rec.get("recommended_offer")
        if rec.get("action") in ("counter", "accept") and offer:
            key = offer["terms"]
            split = float(offer["price_split"])
            q, d = _parse_key(key)
            if (q, d) in feas:
                fl, res = floor_price(s, q, d), reservation(s, q, d)
                price = min(fl + split * (res - fl), list_price(s, q, d), res)
                return ((q, d), round(price, 6))
    except Exception:
        pass
    # fallback: a rational buyer with a positive-surplus option does not walk
    conf, price, _ = _best_feasible(s, feas)
    return (conf, round(min(price, list_price(s, *conf)), 6))


def _parse_key(key: str) -> tuple:
    _, q, d = key.split("|")
    return int(q), int(d)


def _seller_ok(s: MPXScenario, pkg) -> bool:
    return all(ln.price >= floor_price(s, ln.qty, ln.ship_date) - _EPS for ln in pkg)


def _buyer_ok(s: MPXScenario, pkg) -> bool:
    total_res = sum(reservation(s, ln.qty, ln.ship_date) for ln in pkg)
    total_price = sum(ln.price for ln in pkg)
    return total_price <= total_res + _EPS


def _pkg_buyer_surplus(s: MPXScenario, pkg) -> float:
    return sum(reservation(s, ln.qty, ln.ship_date) - ln.price for ln in pkg)


# ── the mount: run one NX session over an MPX-shaped RFQ ─────────────────────
@dataclass
class NXOutcome:
    settled: bool
    receipt: Optional[NXReceipt]
    agreed_qty: Optional[int]
    agreed_ship_date: Optional[int]
    agreed_price: Optional[float]
    joint_surplus: float
    rounds_used: int
    final_state: str


def run_nx_session(s: MPXScenario, *,
                   buyer: BuyerPolicy = reference_buyer,
                   seller: SellerPolicy = reference_seller,
                   max_rounds: int = DEFAULT_MAX_ROUNDS) -> NXOutcome:
    """Mount an NX session where MPX would price-only-haggle. Seller opens; then
    buyer and seller alternate until ACCEPT / DECLINE / round bound. Returns the
    settled package (or a failure), all via the NX protocol state machine."""
    session = NXSession(s.session_ref, max_rounds)
    session.quote(seller_open(s))

    party = "buyer"
    guard = 2 * max_rounds + 4
    while session.state in (State.QUOTED, State.PROPOSED) and guard > 0:
        guard -= 1
        policy = buyer if party == "buyer" else seller
        action, payload = policy(s, session)
        if action == "accept":
            session.accept(party)
            break
        if action == "decline":
            session.decline(party, payload or "")
            break
        if action == "propose":
            if session.rounds_remaining <= 0:
                session.decline(party, "round bound reached")
                break
            session.propose(NXPropose(s.session_ref, party, payload))
        party = "seller" if party == "buyer" else "buyer"

    if session.state == State.SETTLED:
        pkg = session.agreed_package
        ln = pkg[0]
        return NXOutcome(
            settled=True, receipt=session.settle_receipt(),
            agreed_qty=ln.qty, agreed_ship_date=ln.ship_date, agreed_price=ln.price,
            joint_surplus=realized_joint(s, ln.qty, ln.ship_date),
            rounds_used=session.rounds_used, final_state=session.state.value)
    return NXOutcome(
        settled=False, receipt=None, agreed_qty=None, agreed_ship_date=None,
        agreed_price=None, joint_surplus=0.0, rounds_used=session.rounds_used,
        final_state=session.state.value)


# ── I4 worked example: the SNHP notary as ONE conforming attestor ───────────
def notary_attestation(receipt: NXReceipt) -> Optional[dict]:
    """Sign a settled NX transcript hash with the SNHP notary's Ed25519 key
    (`core/notary.py`) — the attestor-neutral I4 hook realized by one concrete
    attestor. Returns an attestation dict {scheme, sig, pubkey_fpr, hash} or None
    if the crypto backend is unavailable. The spec does not require THIS attestor;
    it is the worked example named in SPEC §4 I4."""
    try:
        import base64
        from core.notary import load_notary_key
        key = load_notary_key()
        sig = key._private.sign(receipt.transcript_hash.encode())
        return {"scheme": "snhp-notary/ed25519",
                "sig": base64.urlsafe_b64encode(sig).rstrip(b"=").decode(),
                "pubkey_fpr": key.pubkey_fpr, "hash": receipt.transcript_hash}
    except Exception:
        return None

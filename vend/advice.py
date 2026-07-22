"""NEXTMOVE — the Advice type and advise(): buyer/seller-side twin of Quote.

See NEXTMOVE.md. Invariants live here, not in policy docs:

  - *Constraint-respecting*: an Advice recommending a counter outside the
    user's own stated bounds cannot be constructed (AdviceInvariantError).
  - *Belief-honest*: why[] names the user inputs that drove the move; the
    engine optimizes given YOUR floor/target/read — it claims no market data.
  - *Context-based, never person-based*: advise() takes no identity; same
    context -> same advice, auditable via Advice.context_hash.
  - *Receipt mandatory*: an Advice cannot be constructed without why[].

The judgment path is engine-only (negotiate_turn_mc); no LLM anywhere in
move selection. NL parsing, if ever, is I/O and lives elsewhere.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

from gametheory.negotiation.mc_search import negotiate_turn_mc
from vend.receipt_signing import safe_sign

POLICY_ID = "nextmove-mc/1"
# Paid path uses a FIXED rollout budget: same context + seed => identical advice
# on any machine. Wall-clock budgets are for interactive/free use only. The
# budget refines the COUNTER price only — the MC layer short-circuits on
# accept/walk/hold and spends 0 rollouts there (see _compute_provenance); the
# receipt reports engine_path honestly per move rather than claiming MC ran.
_DEFAULT_COMPUTE_SAMPLES = 400_000

# NEXTMOVE price: $2.00 per advice, debited from the caller's prepaid credit
# balance (gametheory.server.billing credit packs). Order of operations in
# advise_charged(): validate -> charge -> compute -> return; an exception
# during compute refunds the charge before re-raising, so "paid but got
# nothing" cannot happen silently.
ADVISE_COST_CENTS = 200


class AdviceInvariantError(ValueError):
    """Raised when an advice would violate its own receipt."""


# ── category presets ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CategoryTemplate:
    id: str
    label: str
    item_label: str            # how the engine narrates the good
    rounds_default: int        # PRIOR, not data: a guess at venue norms,
                               # unvalidated until real session telemetry
                               # calibrates it. Callers override per move.
    side_hint: str             # which side the typical customer is on
    form_note: str             # one line of guidance shown above the form


CATEGORIES: dict[str, CategoryTemplate] = {
    "resale": CategoryTemplate(
        id="resale", label="Marketplace resale (Grailed/Poshmark/eBay/FB)",
        item_label="the item", rounds_default=4, side_hint="sell",
        form_note="Paste the offers so far, oldest first. Your floor stays private.",
    ),
    "supply": CategoryTemplate(
        id="supply", label="Supplier / wholesale purchasing",
        item_label="the order", rounds_default=6, side_hint="buy",
        form_note="Price alone, or multi-issue (price/quantity/delivery/terms) via the bundle tier — logrolling is what you're paying for.",
    ),
    "retail": CategoryTemplate(
        id="retail", label="Retail floor (car/furniture/appliance)",
        item_label="the purchase", rounds_default=3, side_hint="buy",
        form_note="Rounds are short in person — three is typical before a manager appears.",
    ),
}


# ── the type ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Advice:
    category: str
    side: str                       # "buy" | "sell"
    move: str                       # "counter" | "accept" | "walk" | "hold"
    offer: Optional[float]          # concrete price iff move == "counter"
    message: str                    # ready-to-send draft
    why: list[str]                  # mandatory receipt
    confidence_note: str
    context_hash: str
    policy_id: str = POLICY_ID
    seed: int = 0
    engine: dict = field(default_factory=dict)   # raw engine return, for replay
    provenance: dict = field(default_factory=dict)  # truthful compute-path block
    receipt: dict = field(default_factory=dict)     # signed receipt, set by the
                                                    # paid/session layer (empty on
                                                    # the free base call)

    def __post_init__(self):
        if not self.why:
            raise AdviceInvariantError("receipt mandatory: why[] is empty")


def _compute_provenance(engine: dict, move: str) -> dict:
    """The HONEST compute-path block for one single-issue advice (GAUNTLET #4).

    The MC layer (gametheory.negotiation.mc_search.negotiate_turn_mc) SHORT-
    CIRCUITS on non-counter nodes: when the closed form recommends accept/walk/
    hold it returns immediately and ZERO rollouts run, so `engine` carries no
    `compute` block. The earlier product language ("MC-refined per move") was
    therefore an overclaim on exactly those nodes. What is true, stated exactly:
    MC refines the COUNTER price; accept/walk/hold recommendations are closed-
    form. This reads the engine's own output and reports which path actually
    ran — it invents nothing."""
    comp = engine.get("compute")
    if comp and int(comp.get("samples", 0)) > 0:
        return {
            "engine_path": "mc",
            "rollouts": int(comp["samples"]),
            "deterministic": bool(comp.get("deterministic", False)),
            "improved": bool(comp.get("improved", False)),
            "vs_closed_form": comp.get("vs_closed_form"),
            "note": "Monte-Carlo refined the counter price over the rollouts above.",
        }
    return {
        "engine_path": "closed_form",
        "rollouts": 0,
        "deterministic": True,     # the closed form is a pure function
        "note": _closed_form_note(move),
    }


def _closed_form_note(move: str) -> str:
    if move == "accept":
        return ("accept recommendation is closed-form — the MC layer refines "
                "counter prices only and short-circuits on accept, so 0 "
                "rollouts run.")
    if move == "walk":
        return ("walk recommendation is closed-form — no counter price to "
                "refine, so no rollouts run.")
    if move == "hold":
        return "hold recommendation is closed-form — no counter price to refine."
    # move == "counter" but no compute block => no rollout budget on this call
    # (the free/interactive tier). Paid calls always carry a budget.
    return ("closed-form — no rollout budget on this call; MC refines counter "
            "prices only when a compute budget is set.")


def sign_advice_receipt(a: "Advice", *, kind: str = "nextmove.advice",
                        session_id: Optional[str] = None,
                        move_index: Optional[int] = None,
                        price_millicents: int = 0,
                        funding: Optional[dict] = None,
                        balance_after: Optional[dict] = None) -> dict:
    """Build + Ed25519-sign a receipt for one advice move (GAUNTLET #4).

    The truthful compute-provenance (`a.provenance`: engine_path + rollouts)
    travels INSIDE the signed payload, so an accept node signed as closed_form
    can't be re-labelled "MC-refined" after the fact. Money fields ride only
    where a charge actually happened — the anchor OPEN charges $2; individual
    moves are free, so their receipts carry price_millicents=0 honestly."""
    receipt = {
        "kind": kind,
        "policy_id": a.policy_id,
        "category": a.category,
        "side": a.side,
        "move": a.move,
        "offer": a.offer,
        "context_hash": a.context_hash,
        "compute": a.provenance,          # {engine_path, rollouts, deterministic}
        "price_millicents": int(price_millicents),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if session_id is not None:
        receipt["session_id"] = session_id
    if move_index is not None:
        receipt["move_index"] = int(move_index)
    if funding is not None:
        receipt["funding"] = funding
    if balance_after is not None:
        receipt["balance_after"] = balance_after
    return safe_sign(receipt)


def _context_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def _check_bounds(side: str, price: float, walk_away: float) -> None:
    """The one invariant money depends on: never advise crossing YOUR floor."""
    if side == "sell" and price < walk_away - 1e-9:
        raise AdviceInvariantError(
            f"counter {price} below your floor {walk_away}")
    if side == "buy" and price > walk_away + 1e-9:
        raise AdviceInvariantError(
            f"counter {price} above your ceiling {walk_away}")


# ── the call ─────────────────────────────────────────────────────────────────

def advise(*, category: str, side: str, walk_away: float, target: float,
           their_offers: list[float], my_offers: list[float] | None = None,
           rounds_left: Optional[int] = None,
           compute_samples: int = _DEFAULT_COMPUTE_SAMPLES,
           seed: int = 0) -> Advice:
    """One negotiation state in, one move out, receipt attached.

    Deterministic by construction: fixed rollout budget, seeded RNG, and the
    context_hash covers every input — same context ⇒ same advice, auditable."""
    tpl = CATEGORIES[category]
    my_offers = list(my_offers or [])
    rounds = int(rounds_left if rounds_left is not None else tpl.rounds_default)

    ctx = {
        "v": POLICY_ID, "category": category, "side": side,
        "walk_away": walk_away, "target": target,
        "their_offers": their_offers, "my_offers": my_offers,
        "rounds_left": rounds, "compute_samples": compute_samples, "seed": seed,
    }
    res = negotiate_turn_mc(
        side=side, walk_away=walk_away, target=target,
        counterparty_offers=list(their_offers), my_previous_offers=my_offers,
        rounds_left=rounds, item=tpl.item_label,
        compute_samples=compute_samples, seed=seed)

    move = res.get("action", "hold")
    offer = res.get("recommended_price") if move == "counter" else None
    if offer is not None:
        _check_bounds(side, float(offer), float(walk_away))

    # Make the engine's own `compute` view self-describing wherever it is
    # surfaced. On the live door an accept node showed `compute: {}` — provenance
    # dropped mid-session (GAUNTLET #4) — because the MC layer short-circuits on
    # non-counter nodes and emits NO compute block. Fill that gap with the
    # truthful closed_form block; on a counter (MC ran) just label the path "mc".
    provenance = _compute_provenance(res, move)
    if provenance["engine_path"] == "closed_form":
        res["compute"] = dict(provenance)
    else:
        res["compute"]["engine_path"] = "mc"

    why = [w for w in (
        f"your floor: {walk_away:g}; your target: {target:g} (you set these)",
        f"their offers so far: {their_offers}" if their_offers else
        "no counterparty offer yet — this is your opening",
        res.get("rationale", ""),
        (f"fit: {res['fit']['score']} — {res['fit']['reason']}"
         if isinstance(res.get("fit"), dict) else ""),
        (f"expected settlement ≈ {res['expected_settlement']:g}"
         if res.get("expected_settlement") is not None else ""),
    ) if w]

    conf = res.get("confidence")
    note = (f"confidence {conf:.2f}; changes if their next offer moves outside "
            f"the anticipated range or your bounds change"
            if conf is not None else
            "changes if their next offer or your bounds change")

    return Advice(category=category, side=side, move=move, offer=offer,
                  message=res.get("message", ""), why=why,
                  confidence_note=note, context_hash=_context_hash(ctx),
                  seed=seed, engine=res, provenance=provenance)


# ── the paid call (the machine's only billable endpoint) ─────────────────────

def advise_charged(*, api_key: str, **kwargs) -> Advice:
    """advise() behind the credit meter: validate -> charge -> compute.

    Raises billing.UnknownKeyError / billing.InsufficientCreditsError before
    any compute. An engine exception after a successful charge refunds the
    exact wallet buckets that paid (starter stays starter), then re-raises —
    the customer is never silently charged for nothing. Billing is imported
    lazily so pure advise() use (tests, sims) needs no server deps.
    """
    if kwargs.get("category") not in CATEGORIES:      # validate before charging
        raise KeyError(f"unknown category {kwargs.get('category')!r}; "
                       f"valid: {sorted(CATEGORIES)}")
    from gametheory.server import billing, onboarding
    split = billing.charge_or_raise(api_key, ADVISE_COST_CENTS)
    try:
        a = advise(**kwargs)
    except Exception:
        onboarding.wallet_refund(api_key, {
            "starter_millicents": split["starter_spent"],
            "funded_millicents": split["funded_spent"]})
        raise
    # A paid advice hands back a SIGNED receipt (GAUNTLET #4: paid advice must
    # not be self-asserted). context_hash + the truthful engine_path travel
    # inside the signature, so a third party can replay AND see which path ran.
    return replace(a, receipt=sign_advice_receipt(
        a, price_millicents=ADVISE_COST_CENTS * onboarding.MILLICENTS_PER_CENT,
        funding={"starter_millicents": split["starter_spent"],
                 "funded_millicents": split["funded_spent"]},
        balance_after=split["balance_after"]))


# ── multi-issue: the logrolling tier (the engine's actual differentiator) ────

def advise_bundle(*, category: str, issues: list[dict],
                  their_offers: Optional[list[dict]] = None,
                  my_priorities: Optional[dict] = None,
                  my_batna: float = 0.40,
                  their_batna_estimate: float = 0.40,
                  cooperation: Optional[float] = None,
                  rounds_left: Optional[int] = None,
                  seed: int = 0) -> Advice:
    """Multi-issue package advice by logrolling — concede the issues you
    care less about (and they care more about) to win the ones you value.
    This is the tier the free single-price tool does NOT have.

    Deterministic by construction: the closed-form bundle engine is a pure
    function and the priority-inference particle cloud is now drawn from a
    seeded RNG (the `seed` below is threaded into the engine, not just the
    receipt) — same context + seed => byte-identical advice, no theater
    possible. The bundle analog of the never-cross-your-floor invariant: the
    recommended package must clear YOUR stated BATNA, enforced here, not
    promised. `rounds_left` (optional) lets the last-round endgame accept a
    standing offer that clears your BATNA rather than counter into no-deal."""
    tpl = CATEGORIES[category]        # noqa: F841  (validates category)
    ctx = {
        "v": POLICY_ID + "+bundle", "category": category,
        "issues": issues, "their_offers": their_offers or [],
        "my_priorities": my_priorities or {}, "my_batna": my_batna,
        "their_batna_estimate": their_batna_estimate,
        "cooperation": cooperation, "rounds_left": rounds_left, "seed": seed,
    }
    from gametheory.negotiation.bundle import negotiate_bundle
    # seed is now REAL: threaded into the engine's particle filter so identical
    # inputs + seed => identical package/priorities (was a no-op captured only in
    # context_hash). rounds_left enables the gated final-round endgame; None keeps
    # the timeless behavior.
    res = negotiate_bundle(
        issues=issues, their_offers=their_offers,
        my_priorities=my_priorities, my_batna=my_batna,
        their_batna_estimate=their_batna_estimate,
        cooperation=cooperation, rounds_left=rounds_left, seed=seed)

    move = res.get("action", "propose")
    my_u = res.get("my_utility")
    if move in ("propose", "counter", "accept") and my_u is not None \
            and float(my_u) < float(my_batna) - 1e-9:
        raise AdviceInvariantError(
            f"package utility {my_u} below your BATNA {my_batna}")

    why = [w for w in (
        f"your BATNA: {my_batna:g} (you set this); their BATNA estimate: "
        f"{their_batna_estimate:g} (your read, not our data)",
        res.get("trade_logic", ""),
        (f"their inferred priorities: {res['inferred_their_priorities']}"
         if res.get("inferred_their_priorities") else ""),
        (f"acceptance probability ≈ {res['acceptance_probability']:g}"
         if res.get("acceptance_probability") is not None else ""),
    ) if w]

    conf = res.get("confidence")
    note = (f"confidence {conf:.2f}; changes if their offers reveal "
            f"different priorities or your utilities change"
            if conf is not None else
            "changes if their offers reveal different priorities")

    # The bundle engine is a closed-form pure function (no rollouts, no theater
    # possible) — so the honest compute path is closed_form on EVERY bundle move,
    # never "MC-refined". Logrolling has nothing for the MC counter-price search
    # to refine.
    provenance = {
        "engine_path": "closed_form", "rollouts": 0, "deterministic": True,
        "note": ("multi-issue bundle is a closed-form pure function — logrolling "
                 "needs no rollouts and nothing here is Monte-Carlo refined."),
    }
    return Advice(category=category, side="bundle", move=move, offer=None,
                  message=res.get("message", ""), why=why,
                  confidence_note=note, context_hash=_context_hash(ctx),
                  seed=seed,
                  engine={**res, "package": res.get("recommended_offer"),
                          "compute": dict(provenance)},
                  provenance=provenance)

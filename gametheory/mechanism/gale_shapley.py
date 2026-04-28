"""
Gale-Shapley deferred acceptance with capacities (school-choice variant)
and per-receiver acceptability lists. Returns the proposer-optimal stable
matching plus a should-be-empty blocking-pair report as a sanity check.

Preference lists must reference only known ids — `_validate_inputs`
raises ValueError on the first stray id rather than silently producing
a partial matching.
"""
from __future__ import annotations

from collections import deque
from typing import Optional


def _validate_inputs(proposers: list[dict], receivers: list[dict]) -> None:
    if not proposers:
        raise ValueError("proposers must be non-empty")
    if not receivers:
        raise ValueError("receivers must be non-empty")

    p_ids = {p["id"] for p in proposers}
    r_ids = {r["id"] for r in receivers}
    if len(p_ids) != len(proposers):
        raise ValueError("proposer ids must be unique")
    if len(r_ids) != len(receivers):
        raise ValueError("receiver ids must be unique")

    for p in proposers:
        for r_id in p.get("preferences", []):
            if r_id not in r_ids:
                raise ValueError(
                    f"proposer {p['id']!r} ranks unknown receiver {r_id!r}"
                )
    for r in receivers:
        for p_id in r.get("preferences", []):
            if p_id not in p_ids:
                raise ValueError(
                    f"receiver {r['id']!r} ranks unknown proposer {p_id!r}"
                )
        cap = r.get("capacity", 1)
        if not isinstance(cap, int) or cap < 1:
            raise ValueError(f"receiver {r['id']!r} capacity must be int >= 1")


def _find_blocking_pairs(matching: dict[str, str | None],
                          proposers_by_id: dict[str, dict],
                          receivers_by_id: dict[str, dict],
                          held_by_receiver: dict[str, list[str]]) -> list[tuple[str, str]]:
    """
    A pair (p, r) blocks if p prefers r over their current match AND r
    prefers p over at least one of its current matches (or has spare
    capacity and finds p acceptable). For the proposer-optimal output of
    Gale-Shapley over complete + acceptable preferences, this list should
    be empty — we compute it as a sanity check.
    """
    blocking: list[tuple[str, str]] = []
    for p_id, p in proposers_by_id.items():
        prefs = p.get("preferences", [])
        current = matching.get(p_id)
        current_rank = prefs.index(current) if current in prefs else len(prefs)
        for r_id in prefs[:current_rank]:
            r = receivers_by_id[r_id]
            r_prefs = r.get("preferences", [])
            if p_id not in r_prefs:
                continue
            held = held_by_receiver.get(r_id, [])
            cap = r.get("capacity", 1)
            if len(held) < cap:
                blocking.append((p_id, r_id))
                continue
            # Receiver is full; would they swap one current holder for p?
            worst_held_rank = max(
                r_prefs.index(h) for h in held if h in r_prefs
            )
            if r_prefs.index(p_id) < worst_held_rank:
                blocking.append((p_id, r_id))
    return blocking


def gale_shapley(
    *,
    proposers: list[dict],
    receivers: list[dict],
) -> dict:
    """
    Deferred-acceptance matching. Each proposer dict:
      {"id": str, "preferences": list[receiver_id]}  # most-preferred first
    Each receiver dict:
      {"id": str, "preferences": list[proposer_id], "capacity": int = 1}

    Receivers' preferences need not list every proposer; unlisted proposers
    are unacceptable and rejected on contact. Same for proposers — those
    unmatched at termination preferred being unmatched.

    Returns {matching, unmatched_proposers, blocking_pairs, n_proposals}.
    """
    _validate_inputs(proposers, receivers)

    proposers_by_id = {p["id"]: p for p in proposers}
    receivers_by_id = {r["id"]: r for r in receivers}

    receiver_rank: dict[str, dict[str, int]] = {
        r["id"]: {p_id: i for i, p_id in enumerate(r.get("preferences", []))}
        for r in receivers
    }

    held_by_receiver: dict[str, list[str]] = {r["id"]: [] for r in receivers}
    next_proposal_idx: dict[str, int] = {p["id"]: 0 for p in proposers}
    free: deque[str] = deque(p["id"] for p in proposers)
    n_proposals = 0

    while free:
        p_id = free.popleft()
        prefs = proposers_by_id[p_id].get("preferences", [])
        idx = next_proposal_idx[p_id]
        if idx >= len(prefs):
            continue  # exhausted preference list; remains unmatched
        r_id = prefs[idx]
        next_proposal_idx[p_id] = idx + 1
        n_proposals += 1

        r = receivers_by_id[r_id]
        ranks = receiver_rank[r_id]
        if p_id not in ranks:
            free.append(p_id)
            continue  # unacceptable to receiver, p tries next choice next turn

        held = held_by_receiver[r_id]
        cap = r.get("capacity", 1)
        if len(held) < cap:
            held.append(p_id)
            continue

        # Receiver is full. Compare p_id with the held proposer the receiver
        # likes least; bump them if p is preferred.
        worst_held = max(held, key=lambda h: ranks.get(h, 1 << 30))
        if ranks[p_id] < ranks[worst_held]:
            held.remove(worst_held)
            held.append(p_id)
            free.append(worst_held)
        else:
            free.append(p_id)

    matching: dict[str, Optional[str]] = {p["id"]: None for p in proposers}
    for r_id, ps in held_by_receiver.items():
        for p_id in ps:
            matching[p_id] = r_id

    unmatched = [p_id for p_id, r_id in matching.items() if r_id is None]
    blocking = _find_blocking_pairs(
        matching, proposers_by_id, receivers_by_id, held_by_receiver
    )

    return {
        "matching": matching,
        "unmatched_proposers": unmatched,
        "blocking_pairs": [list(pair) for pair in blocking],
        "n_proposals": n_proposals,
    }

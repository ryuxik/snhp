"""Drive the REAL vend sim with the general engine swapped in for the pricer.

Rather than copy vend.run.run_day (its regulars / return-queue / learner
machinery is long and error-prone to mirror), this harness temporarily rebinds
`vend.policies.nash_quote` — the single symbol A2APolicy.quote_for calls — so
the ACTUAL shipped vend.run trajectory is what runs. Two modes:

  compare_pricer   — the sim is DRIVEN by the real nash_quote; at every quote a
                     second pricer (the engine) is also run and any (sku, qty,
                     price) divergence recorded. The trajectory is byte-faithful
                     to vend.run (the cart-level equivalence probe).
  substitute_pricer — the engine DRIVES the sim (level-2 sim reproduction).

vend/ is never edited on disk; the rebinding is a test-time patch, restored on
exit, so `git status vend/` stays empty.
"""
from __future__ import annotations

import contextlib

import vend.policies as _policies

from core.adapters.vend import engine_nash_quote


def outcome_key(nq):
    if nq is None or nq.outcome is None:
        return None
    o = nq.outcome
    return (o.sku, int(o.qty), round(float(o.unit_price), 2))


def is_mismatch(a, b) -> bool:
    """cart-level equivalence: same None-ness, same (sku, qty), price ≤ $0.01."""
    ka, kb = outcome_key(a), outcome_key(b)
    if (ka is None) != (kb is None):
        return True
    if ka is None:
        return False
    return not (ka[0] == kb[0] and ka[1] == kb[1]
                and abs(ka[2] - kb[2]) <= 0.01 + 1e-9)


@contextlib.contextmanager
def compare_pricer(engine=engine_nash_quote, *, mismatches=None, counts=None,
                   **engine_kw):
    """Sim runs on the real nash_quote; `engine` is compared at every quote."""
    real = _policies.nash_quote

    def wrapper(state, wtp, walk, **kw):
        a = real(state, wtp, walk, **kw)
        b = engine(state, wtp, walk, **{**kw, **engine_kw})
        if counts is not None:
            counts["total"] = counts.get("total", 0) + 1
        if is_mismatch(a, b):
            if counts is not None:
                counts["mismatch"] = counts.get("mismatch", 0) + 1
            if mismatches is not None:
                mismatches.append({"driver": outcome_key(a),
                                   "engine": outcome_key(b),
                                   "walk": round(float(walk), 4)})
        return a

    _policies.nash_quote = wrapper
    try:
        yield
    finally:
        _policies.nash_quote = real


@contextlib.contextmanager
def substitute_pricer(engine=engine_nash_quote, **engine_kw):
    """The engine DRIVES the sim (its NashQuote is what A2APolicy returns)."""
    real = _policies.nash_quote

    def wrapper(state, wtp, walk, **kw):
        return engine(state, wtp, walk, **{**kw, **engine_kw})

    _policies.nash_quote = wrapper
    try:
        yield
    finally:
        _policies.nash_quote = real

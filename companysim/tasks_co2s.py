"""The buyer's deliverable library for the v35 CO2-S settlement / hold-up chain.

A CO2-S deliverable REQUIRES three sequential legs — UPSTREAM (A) produces an
initial artifact, MIDDLE (B) transforms it, DELIVERER (C) finalizes and delivers
it to the buyer. Leg N's input is leg N-1's output artifact; the artifact
genuinely threads through the chain. Each leg has a REAL cost charged to the
performing org's wallet (the sunk cost that makes a hold-up at settlement a real
loss to the upstream org).

The WORK here is deliberately small and honest-to-do (liar_frac=0 in the primary
cells): CO2-A already tested the fraud gate and killed it. CO2-S measures the
SETTLEMENT — whether three separate, self-interested orgs form the chain and the
terminal holder forwards the agreed shares up it. So the tasks are trivial enough
that any competent model completes them; the artifact-passing is real, but the
measured variance is the economic behaviour, not the code quality.

Economics are FIXED across every task and both regimes (the anti-theater
invariant): price P and the three leg costs are constant, so "fair" and "agreed"
shares are the same benchmark in every episode. Only the concrete deliverable
varies by seed, giving four distinct instances without perturbing the incentive
structure the experiment isolates.
"""

from __future__ import annotations

from dataclasses import dataclass

# Fixed economics (the same in every task and both regimes).
PRICE = 90.0            # P — the buyer escrows this; it is paid only on delivery
LEG_COST = 20.0         # each leg's real sunk cost (symmetric: 20 + 20 + 20 = 60)
# Surplus = P - total_cost = 90 - 60 = 30. The natural "fair" share is each org's
# own cost plus an equal third of the surplus = 20 + 10 = 30 credits per org.


@dataclass(frozen=True)
class Leg:
    org: str            # "A" / "B" / "C"
    role: str           # "UPSTREAM" / "MIDDLE" / "DELIVERER"
    brief: str          # what this leg must produce (prose the org sees)
    cost: float = LEG_COST


@dataclass(frozen=True)
class ChainTask:
    task_id: str
    title: str
    goal: str           # the overall deliverable (all three orgs see it)
    legs: list          # [Leg_A, Leg_B, Leg_C] in strict sequence
    price: float = PRICE

    def total_cost(self) -> float:
        return round(sum(l.cost for l in self.legs), 10)

    def surplus(self) -> float:
        return round(self.price - self.total_cost(), 10)

    def fair_shares(self) -> dict:
        """Each org's fair share: its own cost + an equal third of the surplus.
        A reporting benchmark ONLY — the orgs are never shown it and negotiate
        their shares freely."""
        third = self.surplus() / len(self.legs)
        return {l.org: round(l.cost + third, 10) for l in self.legs}


def _task(task_id: str, title: str, goal: str, a: str, b: str, c: str) -> ChainTask:
    return ChainTask(task_id, title, goal, [
        Leg("A", "UPSTREAM", a), Leg("B", "MIDDLE", b), Leg("C", "DELIVERER", c)])


# ---------------------------------------------------------------------------
# Four small three-leg deliverables (one per seed). Trivial by design.
# ---------------------------------------------------------------------------
LIBRARY = [
    _task(
        "temp", "temperature converter",
        "A small Python utility function `celsius_to_fahrenheit(c)` that converts "
        "Celsius to Fahrenheit, with a one-line usage example.",
        "Write the interface: the function name, its signature, and a one-line "
        "docstring stating exactly what it does. Do not implement the body.",
        "Implement the function body per the UPSTREAM interface so it returns the "
        "correct Fahrenheit value. Keep the interface unchanged.",
        "Finalize: confirm the implementation matches the interface, append one "
        "line of example usage showing a call and its result, and deliver the "
        "complete module to the buyer."),
    _task(
        "wordcount", "word counter",
        "A small Python utility function `word_count(text)` that returns the number "
        "of whitespace-separated words in a string, with a one-line usage example.",
        "Write the interface: the function name, its signature, and a one-line "
        "docstring stating exactly what it does. Do not implement the body.",
        "Implement the function body per the UPSTREAM interface so it returns the "
        "correct count. Keep the interface unchanged.",
        "Finalize: confirm the implementation matches the interface, append one "
        "line of example usage showing a call and its result, and deliver the "
        "complete module to the buyer."),
    _task(
        "average", "list average",
        "A small Python utility function `average(nums)` that returns the arithmetic "
        "mean of a non-empty list of numbers, with a one-line usage example.",
        "Write the interface: the function name, its signature, and a one-line "
        "docstring stating exactly what it does. Do not implement the body.",
        "Implement the function body per the UPSTREAM interface so it returns the "
        "correct mean. Keep the interface unchanged.",
        "Finalize: confirm the implementation matches the interface, append one "
        "line of example usage showing a call and its result, and deliver the "
        "complete module to the buyer."),
    _task(
        "initials", "name initials",
        "A small Python utility function `initials(name)` that returns the upper-case "
        "initials of each word in a name (e.g. 'ada lovelace' -> 'AL'), with a "
        "one-line usage example.",
        "Write the interface: the function name, its signature, and a one-line "
        "docstring stating exactly what it does. Do not implement the body.",
        "Implement the function body per the UPSTREAM interface so it returns the "
        "correct initials. Keep the interface unchanged.",
        "Finalize: confirm the implementation matches the interface, append one "
        "line of example usage showing a call and its result, and deliver the "
        "complete module to the buyer."),
]

LIBRARY_BY_ID = {t.task_id: t for t in LIBRARY}


def task_for_seed(seed: int) -> ChainTask:
    """One deliverable per seed (wraps if seed >= len). Economics are identical;
    only the concrete work differs, so the settlement behaviour is what varies."""
    return LIBRARY[seed % len(LIBRARY)]

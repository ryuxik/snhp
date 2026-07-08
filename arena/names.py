"""Deterministic names. "Vex of House Umber" is a character; "agent_0x3f" is a
data point. Names are what let a viewer follow, root for, and retell — the whole
storytelling layer hangs off them. Seeded so a replay reproduces every name.
"""
from __future__ import annotations

import numpy as np

# Short, gothic, pronounceable given names.
_GIVEN = (
    "Vex", "Moro", "Cael", "Bram", "Nyx", "Orin", "Sable", "Dree", "Thal", "Wren",
    "Koro", "Ysolt", "Garr", "Pell", "Mira", "Quill", "Rue", "Vane", "Ash", "Loth",
    "Corvin", "Silas", "Isolde", "Draven", "Fenn", "Grael", "Hollis", "Ivo", "Jori",
    "Lucia", "Marn", "Odile", "Piers", "Roderic", "Selene", "Torv", "Ulric", "Verity",
)
# House names (surnames for dynasties). New founders draw an unused one first.
_HOUSES = (
    "Umber", "Vetch", "Kestrel", "Ashfell", "Morrow", "Thorne", "Vane", "Corvid",
    "Duskwater", "Grieve", "Halberd", "Ironmoor", "Larkspur", "Nettle", "Ossuary",
    "Pyre", "Quillon", "Ravensworth", "Sallow", "Tallow", "Underhill", "Wick",
    "Blackthorn", "Cinder", "Direwood", "Emberly", "Fallow", "Grimault", "Harrow",
)


class NameForge:
    """Doles out unique given names and unique house names, deterministically.
    Recycles gracefully when the pools are exhausted (suffixes a roman-ish tag)."""

    def __init__(self, rng: np.random.Generator):
        self._rng = rng
        self._given_pool = list(_GIVEN)
        self._house_pool = list(_HOUSES)
        rng.shuffle(self._given_pool)
        rng.shuffle(self._house_pool)
        self._given_i = 0
        self._house_i = 0

    def given(self) -> str:
        if self._given_i < len(self._given_pool):
            name = self._given_pool[self._given_i]
        else:
            base = self._given_pool[self._given_i % len(self._given_pool)]
            name = f"{base}{self._given_i // len(self._given_pool) + 1}"
        self._given_i += 1
        return name

    def house(self) -> str:
        if self._house_i < len(self._house_pool):
            name = self._house_pool[self._house_i]
        else:
            base = self._house_pool[self._house_i % len(self._house_pool)]
            name = f"{base}-{self._house_i // len(self._house_pool) + 1}"
        self._house_i += 1
        return name

    def full(self, house: str) -> str:
        return f"{self.given()} of House {house}"

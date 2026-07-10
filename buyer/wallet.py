"""Wallet — the buyer's portable, cross-merchant identity (gap 4).

A consented, attested disclosure + reputation profile keyed on uid and presented
to ANY merchant. Two things travel with it:

  * attestation   — the merchant can trust the disclosure (no anchoring exploit;
                    mirrors vend's a2a-attested arm), so an attested wallet can
                    negotiate at the honest frontier everywhere.
  * reliability   — a track record of FULFILLED forward commitments, in [0,1].
                    It is what makes a commit BANKABLE: a merchant will grant the
                    forward-demand discount only on the share of a commitment it
                    believes will be honored. A human can't build this (they
                    can't credibly pre-commit); the agent can, and — the moat —
                    the score is PORTABLE, so leverage earned at one merchant is
                    spent at the next. That is "leverage that compounds across
                    the block."

`trusted_frac` is how much of a forward commitment a merchant will bank:
attestation buys half the credit up front, the track record earns the rest.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Wallet:
    uid: int
    attested: bool = True
    reliability: float = 0.0          # EWMA of fulfilled commitments, [0,1]
    reference_prices: dict[str, float] = field(default_factory=dict)
    commits_made: int = 0
    commits_kept: int = 0
    _alpha: float = 0.35              # learning rate on the reliability EWMA

    def trusted_frac(self) -> float:
        """Share of a forward commitment a merchant will bank. Attestation is
        worth half the credit (identity + verified disclosure); the reliability
        track record earns the other half. An attested newcomer starts at 0.5;
        a proven attested regular reaches 1.0. An UNATTESTED wallet earns credit
        only through fulfilled history (it can still build a record, slowly)."""
        base = 0.5 if self.attested else 0.0
        return round(min(1.0, base + (1.0 - base) * self.reliability), 4)

    def fulfilled(self) -> None:
        """Record a kept commitment; reliability EWMA rises toward 1."""
        self.commits_made += 1
        self.commits_kept += 1
        self.reliability = round(self.reliability + self._alpha *
                                 (1.0 - self.reliability), 6)

    def defaulted(self) -> None:
        """Record a broken commitment; reliability EWMA falls toward 0."""
        self.commits_made += 1
        self.reliability = round(self.reliability * (1.0 - self._alpha), 6)

    def note_reference(self, sku: str, price: float) -> None:
        """Remember a price paid — the reference profile the wallet carries to
        the next merchant (used by disclosure/fairness downstream)."""
        prev = self.reference_prices.get(sku)
        self.reference_prices[sku] = price if prev is None else \
            round(0.8 * prev + 0.2 * price, 4)

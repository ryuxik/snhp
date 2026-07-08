"""SNHP Evolution Arena — a live, always-on evolutionary competition.

Pixel-art agents negotiate real deals using the shipped SNHP engine, earn
energy, court mates via stable matching, bargain over their children's genes
(recombination *is* a negotiation that can fail), and die broke. The sim is the
authority; a browser renderer choreographs its event stream.

Keystone invariant: nothing in this package knows how to negotiate. Every
strategic computation is delegated to `gametheory.negotiation` /
`gametheory.mechanism` / `gametheory.auctions` — the library being showcased.
"""

__version__ = "0.1.0"

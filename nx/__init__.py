"""SNHP-NX/1 — the Missing Layer.

An open, host-neutral extension that turns a checkout-shaped agent-payment
protocol (ACP/AP2-shaped: fixed price, take-it-or-leave-it checkout) into a
bundle-capable negotiation, with an SNHP-receipt attestation hook.

See SPEC.md for the citable specification, PREREG.md for the pre-registered
deal-formation kill, and results/RESULTS.md for the run. Reference implementation
in protocol.py; MPX (meridian) mount in bridge.py; conformance suite in
test_nx.py; experiment in experiment.py.
"""

__version__ = "1.0.0"
PROTOCOL = "snhp-nx/1"

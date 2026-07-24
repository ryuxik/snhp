"""Rent-renewal advisor: market layer, legal layer, deterministic core.

Layering is deliberate — see RENEWAL-SPEC.md. Adding a metro is a data
edit in metros.py; adding a regulated jurisdiction is a module in
jurisdictions.py; neither touches advisor.py.
"""

from vend.rent.advisor import Assessment, assess  # noqa: F401

__all__ = ["assess", "Assessment"]

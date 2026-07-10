"""VINTAGE — the make-an-offer store sim (one-of-one inventory, LES 2026).

Five arms over the identical sourcing + browser stream:
  sticker/1     — tag price, take it or leave it; the cultural −20%-at-30-days
                  gut markdown (the control).
  offer/1       — make-an-offer (post-reg FIX B): browsers submit shaded
                  offers; the engine accepts/counters/declines per item
                  against an event-consistent disagreement value, with the
                  counter's huff externality priced from a LEARNED
                  shading/huff/fallback model (censoring-aware).
  hazard/1      — ablation: the same learned per-item hazard drives COMPUTED
                  markdowns, discount-only, no offers (H-V3).
  retag/1       — post-reg FIX A: the hazard machinery re-tags POSTED prices
                  UP as well as down (at most weekly per item), toward the
                  posterior-optimal price — one-of-one goods have no
                  reference price for discount-only to protect.
  retag+offer/1 — retag/1's board plus offer/1's flow; the offer ceiling is
                  the CURRENT tag.
"""

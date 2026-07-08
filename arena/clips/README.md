# Arena clip pipeline

Turns the arena into shareable X assets. **Dev-only** — Playwright and ffmpeg are
never in the prod image or `pyproject` prod extras.

## Setup (once)

```bash
pip install playwright
playwright install chromium
brew install ffmpeg        # or: apt-get install ffmpeg
```

## Make a clip

```bash
# a window of live play (MP4 + GIF)
python arena/clips/capture.py --url http://localhost:8201 --seconds 12

# a deterministic replay of a committed generation (same seed -> same clip)
python arena/clips/capture.py --url http://localhost:8201 --replay 214

# a 2400x1260 OG / X end-card PNG
python arena/clips/capture.py --url http://localhost:8201 --card
```

Output lands in `arena/clips/out/` (gitignored): `<name>.mp4`, `<name>.gif`,
`<name>_card.png`.

## The three clip archetypes (the shareable stories)

Engineer highlights around these — each is a story with a number, motion in the
first 300ms, and a legible held end-frame:

1. **The Rally** — a gap bar converging under rally tempo → the hold → impact
   frame → the surplus number.
2. **The Inheritance** — a death's embers rising / orbs to heirs, or a child
   assembling from its parents' parts.
3. **The Era Turn** — the bell, the stained-glass retint, the whole crowd flinch.

The renderer bakes a 25%-alpha `SNHP` tag into the canvas corner so the brand
survives re-uploads, and `?clip=1` hides all DOM chrome so clips are pure canvas.

## Nightly recap reel

`recap.py` stitches a day's flagged highlights (from `/arena/highlights`) into one
chaptered reel — where the multi-hour macro-stories (the staking two-act, dynasty
arcs) actually become legible. This is the appointment-viewing / best-post unit.

```bash
python arena/clips/recap.py --url http://localhost:8201
```

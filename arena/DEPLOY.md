# Deploying the Evolution Arena (arena.snhp.dev)

Its own Fly app (`snhp-arena`), separate from `snhp` (toolkit API) and `par-game`.
Always-on: one persistent world everyone watches, so it does not idle to zero.

## One-time

```bash
# from the repo root, account ryuxik@gmail.com, region sjc
fly launch --no-deploy --name snhp-arena --dockerfile arena/Dockerfile
fly volumes create arena_data --size 3 -a snhp-arena --region sjc   # event log + snapshots
fly certs add arena.snhp.dev -a snhp-arena                          # custom domain + HTTPS
```

Point DNS: add the AAAA/A records Fly prints for `arena.snhp.dev` (or a CNAME to
`snhp-arena.fly.dev`).

## Deploy

```bash
fly deploy -c arena/fly.toml        # build context = repo root
```

The image installs `.[prod,arena]` (adds `websockets`). First boot spends ~30s on
numba JIT warmup before `/health` reports 200 — `grace_period = 40s` covers it.

## Ops

```bash
fly logs -a snhp-arena
fly ssh console -a snhp-arena
# admin (token-gated): set ARENA_ADMIN_TOKEN, then
curl -X POST "https://arena.snhp.dev/arena/admin/pause?token=…"
curl -X POST "https://arena.snhp.dev/arena/admin/resume?token=…"
curl -X POST "https://arena.snhp.dev/arena/admin/speed:2.0?token=…"
```

## Config

Everything is env-overridable (`ARENA_*`, see `arena/config.py`). Notable:

| var | default | meaning |
|---|---|---|
| `ARENA_SEED` | 42 | world seed (determinism) |
| `ARENA_POP_CAP` | 60 | carrying capacity |
| `ARENA_ASSORTATIVE` | 0 | Act I (0) vs Act II (1) staking discoverability |
| `ARENA_STAKE_UPKEEP` | 4.0 | staking fee per gen (~20% of measured peer premium) |
| `ARENA_TICK_SECONDS` | 0.25 | pacing granularity |
| `ARENA_DATA_DIR` | /data | event log + snapshots (the Fly volume) |

The renderer's engine budget overrides (`SNHP_BUNDLE_N_PARTICLES=200`,
`SNHP_BAYESIAN_N_PARTICLES=300`) are applied at import for throughput; they are
performance knobs only — no strategy behavior changes.

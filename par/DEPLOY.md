# Deploying PAR

PAR ships as its own Fly app (`par`, domain `par.game`), separate from the `snhp` toolkit
API but sharing the `gametheory` engine. `uvicorn par.api:app` serves the SPA at `/` and the
API at `/par/*` — same-origin, so the front end's `fetch()` needs no CORS.

## What's ready vs. what needs you

| | state |
|---|---|
| App container | ✅ `par/Dockerfile` (build context = repo root) |
| Fly config | ✅ `par/fly.toml` (health check `/health`, HTTPS, sjc) |
| DB schema | ✅ auto-created by `par/_store.py` on first connect; `par/schema.sql` is the reference + prod indexes |
| Persistence | ✅ **durable** — SQLite locally, Postgres in prod (`par/_store.py` via `gametheory._db`); survives restarts |
| Actually running `fly deploy` | ⬜ **you** — needs your Fly auth + domain DNS |

## Ship it (this is how it was actually deployed)

From the repo root, with `flyctl` installed and `fly auth login` (ryuxik@gmail.com). The app
is **par-game** ("par" is taken on Fly's global namespace) and it shares the existing
`snhp-db` Postgres cluster (its own database + user inside it):

```sh
fly apps create par-game --org personal
fly postgres attach snhp-db --app par-game --yes    # injects DATABASE_URL (db: par_game)
fly deploy . -c par/fly.toml --remote-only --yes    # context = repo root; dockerfile from toml
# custom domain, once par.game DNS points at Fly:
#   fly certs add par.game --app par-game
```

The schema auto-creates on first connect (par/_store.py); `psql -f par/schema.sql` is only
for the optional prod indexes. Then: `curl https://par-game.fly.dev/health` and `/par/today`,
and open https://par-game.fly.dev.

## Persistence (done) & scaling

State lives in SQL via `par/_store.py`, which reuses `gametheory._db`: **SQLite by default**
(a local `par/.par.db` — zero setup, gitignored) and **Postgres when `DATABASE_URL` is set**
(the `fly postgres attach` above). One DDL runs on both; upserts use `ON CONFLICT ... DO
UPDATE`. Verified: results, streaks, groups, waitlist, and the funnel all survive a restart.

So scaling is now a config choice:

- **With Postgres attached** (prod): state is shared across machines → set
  `min_machines_running = 0` and let `auto_stop_machines` idle it to zero between traffic.
- **Without `DATABASE_URL`**: SQLite is per-machine and lives on the container FS — fine for
  one machine, but mount a volume (or keep Postgres) before scaling out.

Demo seeds are **local-only automatically**: they run on a startup hook (never at import — a
slow DB can't crash-loop the app before `/health`) and only when `DATABASE_URL` is absent or
`PAR_DEMO=1` is set. Production tables start clean; social proof is real from play one.

## Scale + launch checklist (from the CTO/CEO review)

- [ ] **Connection pooling** before real traffic: put pgbouncer in front of Postgres (Fly:
      `fly pg` supports it) — `par/_store.py` opens a connection per request by design.
- [ ] **Signed device token** if boards ever go public/paid (today `user_id` is honor-system;
      closes are validated against par + the transcript, which stops score forgery but not
      impersonation inside a friend group).
- [ ] **Asset cache-busting**: bump the `?v=` on `styles.css` / `par.js` in `index.html` with
      every front-end deploy.
- [ ] **The business sequence** (CEO): deploy → collect emails (the waitlist now captures
      contact) → creator-seeded launch week → 50 concierge advisory negotiations with
      documented before/after outcomes (the agent's proof, and the success-fee legal test)
      before any paid-agent marketing.

## After it's live

- Point the share link's `par.game/?g=<code>` at the real domain (it already renders it).
- Watch `GET /par/funnel` for the play → share → cta_view → cta_click → waitlist rates.
- Wire the `/par/advise` MVP (the agent on a real deal) behind the waitlist as it graduates
  from advisory to full agent-to-agent.

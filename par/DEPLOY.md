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

## Ship it (one-time)

From the repo root, with `flyctl` installed and `fly auth login` (ryuxik@gmail.com):

```sh
fly launch --no-deploy --name par --dockerfile par/Dockerfile   # writes/merges par/fly.toml
fly postgres create --name par-db --region sjc --vm-size shared-cpu-1x --volume-size 1
fly postgres attach par-db --app par                            # injects DATABASE_URL
psql "$(fly postgres connect --app par-db --command '\conninfo' 2>/dev/null)" -f par/schema.sql
fly certs add par.game --app par                                # + point DNS at Fly (A/AAAA)
fly deploy --dockerfile par/Dockerfile
```

Then `curl https://par.game/par/today` and open `https://par.game`.

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

The only prod-seeding TODO: drop the `seed_demo` / `seed_group_demo` calls in `api.py` and
seed a real `scenarios` table from the audited deck instead of the demo spread.

## After it's live

- Point the share link's `par.game/?g=<code>` at the real domain (it already renders it).
- Watch `GET /par/funnel` for the play → share → cta_view → cta_click → waitlist rates.
- Wire the `/par/advise` MVP (the agent on a real deal) behind the waitlist as it graduates
  from advisory to full agent-to-agent.

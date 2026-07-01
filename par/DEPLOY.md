# Deploying PAR

PAR ships as its own Fly app (`par`, domain `par.game`), separate from the `snhp` toolkit
API but sharing the `gametheory` engine. `uvicorn par.api:app` serves the SPA at `/` and the
API at `/par/*` — same-origin, so the front end's `fetch()` needs no CORS.

## What's ready vs. what needs you

| | state |
|---|---|
| App container | ✅ `par/Dockerfile` (build context = repo root) |
| Fly config | ✅ `par/fly.toml` (health check `/health`, HTTPS, sjc) |
| DB schema | ✅ `par/schema.sql` (results, streaks, groups, waitlist, events, scenarios) |
| Persistence swap | ⬜ the stores are **in-memory** today — see below |
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

## The one real blocker before scaling: persistence

`par/scoreboard.py` and `par/funnel.py` are **in-memory dicts**. That's fine for a single
machine (why `fly.toml` pins `min_machines_running = 1`), but:

- state resets on every deploy, and
- it can't be shared across instances, so you can't scale out or idle to 0.

The swap is mechanical because the module boundaries were drawn for it — every function is
already a `GROUP BY` waiting to happen:

1. `pip install psycopg2-binary` (or `asyncpg`); read `DATABASE_URL` at startup.
2. In `scoreboard.py`: `record` → `INSERT ... ON CONFLICT (day,user_id) DO UPDATE`; `stats`
   / `group_board` → the `SELECT ... GROUP BY` over `results` + `groups`; streak → an
   `UPDATE streaks`. Same return shapes.
3. In `funnel.py`: `record_event`/`join_waitlist` → `INSERT`; `funnel()` → `SELECT name,
   count(distinct user_id) ... GROUP BY name`.
4. Drop the `seed_demo` / `seed_group_demo` calls in `api.py`; seed the `scenarios` table
   from the real deck instead.

Endpoints, the SPA, and the tests don't change — only the storage layer behind them.

## After it's live

- Point the share link's `par.game/?g=<code>` at the real domain (it already renders it).
- Watch `GET /par/funnel` for the play → share → cta_view → cta_click → waitlist rates.
- Wire the `/par/advise` MVP (the agent on a real deal) behind the waitlist as it graduates
  from advisory to full agent-to-agent.

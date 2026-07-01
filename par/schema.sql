-- PAR — the durable schema. The app AUTO-CREATES these tables on first connect via
-- par/_store.py (CREATE TABLE IF NOT EXISTS, translated to Postgres by gametheory._db), so
-- you don't have to run this file to boot. It's here as the canonical reference AND to add
-- the production indexes _store.py doesn't (they matter for Postgres at scale):
--   psql "$DATABASE_URL" -f par/schema.sql
--
-- Column notes: booleans are INTEGER 0/1 and JSON is TEXT (one DDL that runs on both SQLite
-- and Postgres). Streak columns are cur/mx; the group table is friend_groups (GROUPS is a
-- reserved word in Postgres). Upserts in the code use ON CONFLICT ... DO UPDATE.

-- one row per finished game (idempotent per (day, user) via the PK)
CREATE TABLE IF NOT EXISTS results (
    day          integer NOT NULL,             -- days since epoch (the puzzle number)
    user_id      text    NOT NULL,
    pct_of_par   real    NOT NULL,             -- server-recomputed; never trusted from client
    walked       integer NOT NULL DEFAULT 0,   -- 0/1
    PRIMARY KEY (day, user_id)
);
CREATE INDEX IF NOT EXISTS results_day_idx ON results (day);        -- distribution / percentile

-- daily-habit state; streak advances only on the first play of a day
CREATE TABLE IF NOT EXISTS streaks (
    user_id      text    PRIMARY KEY,
    cur          integer NOT NULL DEFAULT 0,
    mx           integer NOT NULL DEFAULT 0,
    last_day     integer
);

-- friend-group membership; name is a display label unique only within a group
CREATE TABLE IF NOT EXISTS friend_groups (
    group_id     text NOT NULL,
    user_id      text NOT NULL,
    name         text NOT NULL,
    PRIMARY KEY (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS friend_groups_group_idx ON friend_groups (group_id);

-- the product waitlist (the CTA's real destination); idempotent per user
CREATE TABLE IF NOT EXISTS waitlist (
    user_id      text PRIMARY KEY,
    scenario     text NOT NULL,
    contact      text
);

-- funnel events: play | share | cta_view | cta_click | waitlist. Append-only; no id needed
-- (we only COUNT DISTINCT user_id per name). Add a ts column here if you want time-series.
CREATE TABLE IF NOT EXISTS events (
    user_id      text NOT NULL,
    name         text NOT NULL,
    meta         text NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_name_idx ON events (name);        -- funnel counts by step

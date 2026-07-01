-- PAR — the durable state, for when the in-memory stand-ins move to Postgres.
-- Every aggregation the API does today (percentile, distribution, streak, group board,
-- funnel) is a GROUP BY over these tables; the endpoint shapes don't change.
--   psql "$DATABASE_URL" -f par/schema.sql

-- the daily deck: one row per calendar day, seeded weeks ahead and audited so no day
-- ships a broken or trivial par (SPEC.md §1). `payload` holds the Scenario JSON
-- (title, player_side, your_walk_away, your_target, house_reservation, rounds, unit).
CREATE TABLE IF NOT EXISTS scenarios (
    day          integer PRIMARY KEY,          -- days since epoch (the puzzle number)
    payload      jsonb   NOT NULL
);

-- one row per finished game (idempotent per (day, user) via the PK).
CREATE TABLE IF NOT EXISTS results (
    day          integer     NOT NULL,
    user_id      text        NOT NULL,
    pct_of_par   real        NOT NULL,         -- server-recomputed; never trusted from client
    walked       boolean     NOT NULL DEFAULT false,
    ts           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, user_id)
);
CREATE INDEX IF NOT EXISTS results_day_idx ON results (day);        -- distribution/percentile

-- daily-habit state. streak advances only on the first play of a day.
CREATE TABLE IF NOT EXISTS streaks (
    user_id      text    PRIMARY KEY,
    current      integer NOT NULL DEFAULT 0,
    max          integer NOT NULL DEFAULT 0,
    last_day     integer
);

-- friend-group membership. identity = the (hidden) user_id; name is a display label,
-- unique only within a group (dupes disambiguated at read time).
CREATE TABLE IF NOT EXISTS groups (
    group_id     text NOT NULL,
    user_id      text NOT NULL,
    name         text NOT NULL,
    PRIMARY KEY (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS groups_group_idx ON groups (group_id);

-- the product waitlist (the CTA's real destination). idempotent per user.
CREATE TABLE IF NOT EXISTS waitlist (
    user_id      text        PRIMARY KEY,
    scenario     text        NOT NULL,
    contact      text,                          -- optional email/phone
    ts           timestamptz NOT NULL DEFAULT now()
);

-- funnel events: play | share | cta_view | cta_click | waitlist.
CREATE TABLE IF NOT EXISTS events (
    id           bigserial   PRIMARY KEY,
    user_id      text        NOT NULL,
    name         text        NOT NULL,
    meta         jsonb       NOT NULL DEFAULT '{}',
    ts           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_name_idx ON events (name);        -- funnel counts by step

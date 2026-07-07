# PAR — daily-scenario backend spec

PAR is "Wordle for negotiation": one deal a day, the same deal for everyone, play
against a perfect AI ("the House"), get graded against **par** — the most a flawless
player could have extracted. The gut-punch is the reveal: *the dollars you left on
the table.*

The moat is that par is **real**, not vibed. The House plays the SNHP equilibrium
(`gametheory.negotiation.plain_terms.negotiate_turn`), and par is the engine's true
ceiling — no LLM game can fake a defensible "optimal deal."

## 1. The daily rotation

`api.py` holds a `DECK` of `Scenario`s. The day's deal is
`DECK[(today_utc - EPOCH).days % len(DECK)]` — deterministic, so the whole player
base sees the same deal and the same par on the same date (the shareability engine).

Each `Scenario` is `(title, player_side, your_walk_away, your_target, house_reservation, rounds)`:
- `player_side` — `"sell"` (the player wants a HIGH number; the House buys) or `"buy"`
  (the player wants a LOW number; the House sells). This is the field that makes a deck
  entry correct: `house_move` drives the House as the OPPOSITE side, and `score` flips
  the grading direction. **A buyer day with no `player_side` would score backwards** —
  paying more would look like a better result (the bug this field fixes).
- `your_walk_away` / `your_target` — shown to the player. walk-away is the worst price
  you'd accept (a seller's floor, a buyer's ceiling); target is the aspiration.
- `house_reservation` — the House's **hidden limit** = par. NEVER leaves the server
  until `/par/grade`. (A perfect seller drives a buyer-House up to it; a perfect buyer
  drives a seller-House down to it.)
- `rounds` — the deadline (the timing lever; SNHP's edge is multi-round).

Production swaps the in-memory `DECK` for a table (`scenarios(id, date, payload)`)
seeded weeks ahead and audited so no day ships a broken or trivial par. Keep a mix:
~5 single-issue days to 1 multi-issue day so the logroll stays a treat, not a chore,
and alternate buy/sell days so the player learns both directions.

### Authoring a scenario (the one rule that matters)

par must be **reachable but hard**: a perfect player hits 100%, a good player lands
70–90%, an eager folder lands < 60%. Validate every candidate by running
`par_game.play_out` with an eager line and a patient line — if the eager line already
clears 90%, the House is too soft; if the patient line can't break 80%, it's too
stiff. (`par_game.py`'s `__main__` is the reference harness; it runs one sell and one
buy scenario.) `score` guarantees `pct_of_par ∈ (0, 100]` and `left_on_table ≥ 0`
whichever side the player is on, so a "120%" or negative table is always a deck bug.

## 2. The API contract

| endpoint | method | in | out | leaks reservation? |
|---|---|---|---|---|
| `/par/today` | GET | `?day=` (optional, ≥ 0, for replay) | `{no, deck_index, title, side, walk_away, target, rounds, seconds_left}` | **no** |
| `/par/house_move` | POST | `{day, your_offers[], house_offers[], rounds_left ≥ 1}` | `{action, offer, message}` | **no** |
| `/par/grade` | POST | `{day, close?}` | `{par, deal, pct_of_par, left_on_table, agent_close, agent_pct}` | yes (by design — this IS the reveal) |
| `/par/submit` | POST | `{day, user_id, close?}` | grade **+** `{streak, max_streak, played, percentile, par_hits, distribution[]}` | yes (it's the reveal + the board) |
| `/par/stats` | GET | `?day=` (optional) | `{no, played, par_hits, top_pct, distribution[]}` | **no** (anonymous rollup) |
| `/par/group/join` | POST | `{group, user_id, name?}` | `{group, ok}` | **no** |
| `/par/group` | GET | `?group=&day=` | `{group, members, played, board[]}` (ranked, unplayed last) | **no** |
| `/par/bundle_move` | POST | `{issues[], their_offers?, my_priorities?}` | full `negotiate_bundle` dict | n/a (multi-issue) |

Notes:
- **Anti-forgery**: `/par/submit` and `/par/grade` REJECT (400) a close that beats the
  House's reservation (it could never have agreed), and `/par/submit` requires the close to
  appear in the submitted transcript. Forged scores can't reach the board — validated, not
  clamped (clamping rewarded a forged `close=99999` with a perfect 100%).
- **Forensics — the mistake, named**: `/par/submit` returns a structured `forensic`
  finding computed from the transcript (`overconcede` — the move where you out-conceded
  the House; `early_accept` — you took its number while it was still moving; `walk`;
  `pace`). The reveal shows it as ONE sentence in place of any second score (the engine's
  line is internal, deciding only the "beat the engine" win tier), and the coach CTA
  answers it. The histogram/friends board sit behind a "where everyone landed" tap. The
  CTA itself is gated: never on the first play, never on a win day, and only once the
  cumulative pct-gap crosses a threshold — pitch when the number gets heavy.
- **The data moat is the `plays` table**: every submit stores the full move sequence
  (`your_offers`, `house_offers`), close, side, scenario, and timestamp — the labeled
  "how humans negotiate" data the agent trains and evals on. `results` keeps the scalar
  for boards. `/par/advise` calls are logged to `advice` the same way.
- **The client is live-first**: the SPA boots off `GET /par/today` (real rotation, real
  countdown; par stays server-side until the grade) and falls back to the built-in
  stand-in day offline. Rate limiting: 120 writes/min/IP in-app (swap for a shared
  limiter when scaling out).
- `/par/grade` returns the **same shape on a walk**: `deal` is `null`, `pct_of_par` is
  `0.0`, and `agent_close`/`agent_pct` are still present — so a client never branches on
  presence-of-field.
- `no` is the absolute challenge number (days since epoch, or the `?day=` you replayed);
  `deck_index = no % len(DECK)` is which scenario was served. Both are safe to expose
  (the deck rotates publicly); neither leaks `house_reservation`.
- Bad input is a `400`, not a `500`: `rounds_left < 1` and `day < 0` are validated.

`house_move` is stateless: the client replays the full offer history each round, the
server recomputes the equilibrium move. No session state, no DB read on the hot path —
the House is a pure function of `(scenario, history, rounds_left)`. That keeps it
cache-friendly and impossible to desync.

`agent_close` on the grade is the upsell: the SNHP agent lands **2.5% shy of par** —
just under the ceiling when you're selling (`par × 0.975`), just over the floor when
you're buying (`par × 1.025`). `agent_pct` is graded in the same direction as the
player's `pct_of_par` (~97.5% either way). It's the bridge from the game to the A2A
commerce product — the same engine that grades you will *negotiate for you*.

## 3. Multi-issue days (logrolling)

Single-issue speaks dollars; multi-issue speaks **trades**. A multi-issue day ships an
`issues` list — each `{name, options, my_utility[], their_utility[]}` — and is graded by
`gametheory.negotiation.bundle.negotiate_bundle`, which finds the Pareto-optimal package
by logrolling (concede where you care least, hold where you care most).

par for a multi-issue day = the utility of the engine's recommended package (the Nash
point). The front end renders the result as the **logroll diagonal** (the approved
surface): issues sorted by the player's stake, each a split bar, win-marks riding a
diagonal that *is* the trade — you won the issues you cared about, gave the ones you
didn't. Stacked canyons were killed (three deals, not one trade); the diagonal teaches
the single idea that logrolling is one exchange.

Generator sketch (for seeding multi-issue days):
1. Pick 3–4 issues with **opposed** priority orders (so a trade exists at all).
2. Assign `my_utility`/`their_utility` so the naive "split each issue" deal is
   Pareto-dominated — that gap is the lesson.
3. Validate: `negotiate_bundle` must return `fit.score == "good"` and an
   `acceptance_probability` the House would actually take. If the only optimum is a
   corner the House rejects, reseed.

## 4. Scoreboard — the retention + virality layer

`par/scoreboard.py` is an in-memory stand-in for two production tables:

    results(day, user_id, pct_of_par, walked, ts)   -- one row per play
    streaks(user_id, current, max, last_day)         -- the daily-habit state

Every figure the board returns is a `GROUP BY` over `results`; swapping the dict for a
database leaves the API shape unchanged. Three rules:

- **Score server-side.** `/par/submit` recomputes the grade from `close` and ignores any
  percentage the client sends, so the board can't be gamed by POSTing a fake score.
- **Idempotent per (day, user).** Re-submitting a day overwrites that user's row; the
  **streak advances only on the first play of a day** (replays don't inflate it).
- **percentile** = share of today's players you beat; **distribution** = six pct_of_par
  buckets (`<60 · 60s · 70s · 80s · 90s · par`) with the player's bucket flagged — the
  reveal's "where everyone landed," and the Wordle-grid hook that travels.

`/par/stats` is the anonymous rollup (no `user_id`) powering the landing's live social
proof ("N hit par today"). The front end ships a `localBoard()`/`BOARD_BASE` stand-in
that mirrors the `/par/submit` board exactly, plus a seeded demo distribution
(`scoreboard.seed_demo`, **remove in prod**) so the histogram renders alive offline.

**Friends leaderboard** (the spread loop — you share to beat your friends, not the
anonymous crowd): the share text carries a group link (`par.snhp.dev/?g=<code>`); opening a
friend's link joins their group (`/par/group/join`), and `/par/group` returns today's
members ranked best-first (unplayed last). The reveal shows it under a **friends** tab
next to **everyone** (the distribution). Offline, `par.js` falls back to a seeded
`FRIENDS` stand-in; online it renders the live `/par/group` (progressive enhancement —
the stand-in paints instantly, the live board swaps in when the fetch returns).

**Identity without accounts.** A persistent device `user_id` (localStorage `par-user`) is
the real key; the **name** is only a display label — unique *within a group*, not
globally, so duplicates get a short server-side suffix off the hidden id (`Alex·a1`).
Because `/par/submit` recomputes the score from `close`, the *number* can't be forged;
inside a trusted friend group, social accountability covers *whose* number it is. Climb
the ladder only if you need more: a saved **recovery code** for cross-device, a signed
device token if boards ever go public, passkeys as the eventual accountless account.

Still to build on top: a **daily push** ("today's deal is live") paired with the streak,
and turning `agent_close`/`agent_pct` into the **conversion CTA** ("let our agent
negotiate the real one for you").

## 5. Wiring the front end

`par/web/par.js` ships with an inline `DAY` stand-in so the SPA runs with zero backend.
Going live is three swaps (all marked in `par.js`):
- boot → `GET /par/today`
- each player counter → `POST /par/house_move`, and the close test moves from the
  client-side `houseAccepts()` (which reads `DAY.willing`, a stand-in-only hidden
  threshold) to the live House's `rec.action === "accept"`. `DAY.offers`/`willing`/`msg`
  do not exist on the wire — the House is recomputed server-side each round.
- finish → `POST /par/grade` (drives the reveal's par line + "$ on the table")

**Both directions are playable.** `par.js` is side-aware: a `buy` day mirrors the play
canyon labels ("you want ↓ / the house ↑"), clamps the slider to the seller's offer as a
ceiling (you never offer *above* it), flips the accept test (`ask >= willing`), and the
reveal puts par on the *floor* with the wedge = deal − par (the overpayment). All money
is in k-units so `$Xk` formats a $118k salary and an $11.2k car alike. Load a buy day
offline with `?s=buy` (the used car); prod picks the side from `/par/today`'s `side`
field. The par label moves left when par is the floor so it clears the "$X on the table"
hero.

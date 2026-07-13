# SNHP Redesign — Master Roadmap

> One coherent, phased plan to lift the nine vertical sims into **one general
> offer-graph engine**, cut the duplication that makes redundant, and lock it with
> engine-level property tests + CI. Each phase is gated on reproducing an
> already-proven result before the next begins. Nothing is big-bang.

**Status key:** `[ ]` not started · `[~]` in progress · `[x]` done (committed)

---

## The thesis

`boba.cart_nash` and `vend.nash_quote` are **the same algorithm** copy-pasted across
nine verticals (~34k duplicated LOC; 0 of them import the core). They differ in only
two things: **which dimensions** a configuration has, and **what makes a unit's cost
move with shop state**. So the general engine is:

> **a typed offer graph + a pluggable state-dependent cost library + the one shared
> Nash-floor search.** ~70% is lifting existing code up one abstraction level.

---

## Phase 0 — Safety net + hygiene *first*  (low-risk, reversible) — ✅ done (`eb1f4de`)

Turn on the net before refactoring; cut the unambiguous dead weight.

- [ ] **CI** — `.github/workflows/test.yml` runs the existing pytest suite + a golden-artifact tripwire on every push/PR.
- [ ] **Delete safe dead weight** (verify each target has no live references first):
  - [ ] `build/`, `dist/`, `snhp.egg-info/`, `.pytest_cache/` (gitignored local clutter)
  - [ ] `snhp/craigslist_bargains.json`, `snhp/cfpb_disputes.json`, `craigslist_train*.json`, `train.json.gz`, `market_data.json` — cached, re-fetchable via `snhp/fetch_*.py`; add to `.gitignore` (keep the fetch scripts)
  - [ ] `block/web/` — superseded byte-for-byte/older by the deployed `arena/web/block/` (confirm `block/gen_week.py` targets `arena/web/block/canned-week.json`)
  - [ ] `snhp/mcp_server.py` — legacy; entry point is `gametheory.server.mcp_server`
  - [ ] `snhp/server/`, `snhp/web/` — old prototype, served by nothing
- [ ] **Dedup web helpers** → `web/util/{money,rng}.js` (money/PRNG re-inlined in boba-sim.js, demo-scene.js, block/scene.js, par.js, boba-engine.js, block/data.js)
- [ ] Code review → commit.

## Phase 1 — The general engine + its invariant tests, together  (the foundation) — ✅ done (`ba64f14`)

Create `core/` (the offer-graph engine). **Write the Tier-1 property tests first**;
nothing merges to the engine until they're green over *generated arbitrary graphs*.

Engine surface (`core/`):
- `offer_graph.py` — `Item`, `Dimension` (`price_delta`, state-dependent `cost_delta`, `negotiable ∈ {FREE, LEVER, AUTO}`), `OfferGraph`, `DimKind {CHOICE, ADDON, PREFERENCE, FULFILLMENT, QUANTITY}`
- `cost.py` — `CostFn → CostQuote {c_eff, credit, floors_at_list}`; composable components: `const`, `salvage_on_expiry`, `scarcity_shadow`, `capacity_relief`, `batch_economies`
- `deps.py` — `DepGraph` (`valid_on` / `requires` / `excludes`)
- `state.py` — `ShopState` (clock, inventory, capacity, batches)
- `profiler.py` — divergence classifier → `FREE / LEVER / AUTO`, prunes the search to real levers
- `engine.py` — the shared quote(): disagreement point → edge-pruned feasible configs → rungs from state-dependent floor to list → Nash split → guards (never-above-list, min-price floor, min-gain floor, clamps) → receipt
- `api.py` — `compile / profile / quote / menu / price_config / simulate` (`price_config` generalizes the JS `quoteConfig`)

Tier-1 property tests (must exist before any vertical port):
- [ ] **P1** never above menu — `quote.price ≤ list` for every generated graph/config
- [ ] **P2** cost-floor — realized price ≥ state-dependent cost floor
- [ ] **P4** clamps — `qty_appetite` + `min_price_frac` hold (no upsell below cost, no deal past the floor)
- [ ] **P5** surplus conservation — buyer_gain + seller_gain == joint_surplus (exact float)
- [ ] **P9** no-WTP-leak — with `wtp=None`/lookers-refused, all-liars outcome == the menu (hard $0 floor)
- [ ] P3, P6–P8, P10 (profiler classification, IC under attestation, dependency validity, determinism)

- [ ] Code review → commit.

## Phase 2 — Boba as the golden-master, gated — ✅ done (`c719583` Python, `4d0faed` JS+F1)

- [ ] Express boba as an `OfferGraph` instance behind a **default-OFF adapter**
- [ ] **G1 golden** — the general engine reproduces boba's committed MC band (+$497 attested / +$253 no-attest / **+$0 worst-case**)
- [ ] Build the **general JS engine** (successor to `boba-engine.js`) + **F1 fidelity harness** (`node --test`: JS output == Python within tol)
- [ ] Flip boba to the engine only when G1 + F1 pass; delete the bespoke body
- [ ] **New engine primitive:** `batch_economies` cost component — makes quantity/batch a *real* standalone lever (today it's $0 standalone; see demo note)
- [ ] Code review → commit.

## Phase 3 — Vend golden + scope corrections  *(reorg deferred — see below)*

- [x] **vend golden** — `core/adapters/vend.py` + `scarcity_shadow` reproduces `nash_quote` at **100% equivalence** (0/8,000+ quotes) and byte-exact sim (control −$0.046, calibrated +$0.75, fairness-harvest ~$42.6). The Phase-1 two-cost-split divergence was real (10/2162) and closed via a generic default-OFF `CostQuote.rungs` hook. *(committed `3ac6e10`)*
- [x] **fashion = SCOPE BOUNDARY, not a golden.** Verified fashion is a **posted-markdown** mechanism (`price_board(week, inv)` — a seasonal markdown *schedule* clearing inventory against strategic waiters), not bilateral A2A negotiation: no buyer, no Nash split, no disagreement point. Forcing it through the negotiation engine would be a contortion. The engine's remit is **bilateral negotiation**, now proven by *two* independent verticals (boba + vend). Posted-markdown stays its own mechanism.
- [ ] **Tree reorg — DEFERRED (entangled; do as a dedicated CI-gated effort, not mid-stream).** Verification found the audit's "archive 6 sims" list is not clean: **`block/` imports five of them** (`block/venues.py`: `from fashion/bakeshop/slots/vintage import ...`; `block/bundles.py`: `buyer`, `slots`) as its per-venue implementations, and `block` generates the trailer data + is the Phase-5 substrate. No *product* code imports the sims (gametheory/snhp/arena/par/vend are clean), so it's not a deploy risk — but a blind `mv` breaks `block` + CI. The safe reorg (move the coupled `block`+sims cluster under one `sims/` parent + a `conftest`/`.pth` sys.path shim so `import fashion` still resolves, changing zero import statements) is a careful step with low product value and real breakage risk — sequenced AFTER the funnel/experiment, not before.
- [x] Code review (equivalence-to-reference is the gate) → commit.

## Phase 4 — Rebuild the funnel on the general engine  (UI → design loop)

- [ ] **Hook** — full HeyTea menu, re-based on the general engine (supersedes the 4-drink interim `demo.html`)
- [ ] **Sandbox tab** — arbitrary menus, on the general engine
- [ ] **"Run it on your menu"** — the `compile/profile/quote/price_config` API + copy-paste/agent path
- [ ] **G2 golden** — pin the demo's shipped `$497/$253/$0`; fix the trace generator's dead output path
- [ ] Attention design loop on all UI; code review → commit.

## Phase 5 — Live day-one-useful NYC-block experiment  (UI → design loop)

- [ ] Extend `block/` (twin economics + exact-float ledger + flywheel + renderer) with an evolving-firm layer
- [ ] **Live server stream + telemetry logged back to us** (the experiment that improves SNHP)
- [ ] Honesty bar: losers shown, seed+rerun on the HUD, consumer-surplus dominant, no takeover, evolution cosmetic
- [ ] Demote knights → `/science`
- [ ] Attention design loop; code review → commit.

---

## Target directory structure (Phase 3 lands this)

```
snhp/          # PyPI pkg — SLIMMED to core math (core_math, bayesian_agent, nash_solver,
               #   models, formatters, _stats; + negmas/b2b/cost/eval until evals/agents cut)
gametheory/    # PyPI pkg — productization (negotiation, server, auctions, mechanism, crypto)
core/          # NEW general offer-graph engine + thin adapters/ (catalog + priors + constants)
web/           # funnel: util/ (money,rng) · hook/ · trailer/ (block scene) · sandbox/ · arena/(→/science) · leaderboard/
research/      # sims/ · snhp_lab/ · leaderboard/ (NegMAS) · wedge/ (football GTM)
paper/  SNHP_Whitepaper/   # theorems + protocol (unchanged)
```

## Cross-cutting rules (non-negotiable)

- Every migration ships **default-OFF** and must reproduce a committed number before flipping.
- **Respect the deploy DAG:** 3 Fly apps share `gametheory/`+`snhp/`; `api.snhp.dev` copies `vend/` (its `{api,core,scenario,world}.py` are **production — do not archive**); `arena` copies `arena/`; `par-game` copies `par/`.
- **Don't blind-`mv` the `snhp/` core modules** — `gametheory` imports them as bare names via `ensure_snhp_path()`; a move updates `_internal.py` + import sites.
- `research/` (football) is live GTM; `block/gen_week.py → arena/web/block/` feeds the trailer; `gametheory/server/static/*.json` + `arena/web/*.json` are served evidence — none of it is junk.
- Public repo: **secret-scan every diff before commit** (`.env` holds `ANTHROPIC_API_KEY`/`GAUNTLET_EVAL_SEED`, gitignored, never printed/committed).
- Discount-only, type-enforced (never above list); no price signals between substitutes.

## The three hard risks

1. **Scarcity-shadow across timescales** (boba 4-hr batch vs vend same-day vs fashion season) — the trickiest correctness surface.
2. **Non-separable valuations** break the fast nested-prefix add-on path → keep separability the default, gate custom `value()` behind a "may be slow" flag.
3. **Profiler observability is a judgment call** — default `AUTO→FREE` (a missed lever costs money; a fake one leaks).

## Notes carried in from the interim demo reconciliation

- The boba consumer hook (`arena/web/demo.html` + `demo-scene.js` + `boba-engine.js:priceCart`) is the honest 4-drink interim; Phase 4 supersedes it with the full-menu, general-engine version.
- **Quantity is not a standalone lever in the current engine** (cost is linear in qty in *both* JS and Python). The `batch_economies` component (Phase 2) is what makes it real.

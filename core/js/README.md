# `core/js/` — the general offer-graph engine, in JavaScript

A pure-JS (no npm deps) port of the Python engine in `core/`. It mirrors the
Python modules 1:1 so the browser can run the exact same Nash-floor search the
Python reference runs. This is the eventual successor to the deployed
`arena/web/boba-engine.js` (a hand-port of boba's *old* cart_nash); Phase 4 wires
it into the UI. **Nothing here modifies `arena/web/boba-engine.js` or `core/*.py`.**

| JS module            | mirrors Python        |
| -------------------- | --------------------- |
| `offer_graph.mjs`    | `core/offer_graph.py` |
| `cost.mjs`           | `core/cost.py`        |
| `deps.mjs`           | `core/deps.py`        |
| `state.mjs`          | `core/state.py`       |
| `profiler.mjs`       | `core/profiler.py`    |
| `engine.mjs`         | `core/engine.py`      |
| `api.mjs`            | `core/api.py`         |
| `boba_adapter.mjs`   | `core/adapters/boba.py` |
| `pyround.mjs`        | Python `round()` (banker's rounding) — the #1 fidelity trap |

Each module is a native ES module (`export …`) and also hangs a namespace off
`globalThis` (e.g. `globalThis.SNHP_engine`), so it loads under `node --test`,
via `import`, and in the browser.

## The F1 fidelity gate

`test/fidelity.test.mjs` proves the JS output matches the Python engine on a
battery of serialized cases (`test/fixtures.json`): SAME chosen config, price
within $0.01, same feasible flag, same None/walk. Current result: **400/400
match (100%), max price Δ $0.000000** — byte-exact.

The fixtures span both case families the spec asks for:

- the real **boba golden draws** — boba's own shipped sim trajectory (seed
  `20260710`, flagship cell) replayed under all 3 deployed ship configs
  (attested / no-attest / worst), capturing every `core.engine.quote` the boba
  adapter runs;
- the **property-style generated graphs** from `core/tests/generators.py` (all
  5 dim kinds, discounts + walks + fallbacks, scarcity/salvage/relief costs).

### Run the test

```sh
# node's directory-arg form (`node --test core/js/test/`) is unsupported on
# node < ~22.14, so use the glob (functionally identical) — from the repo root:
node --test core/js/test/*.test.mjs

# or let node's default test discovery find it:
node --test
```

### Regenerate the fixtures (one-liner)

Whenever `core/*.py` or `core/adapters/boba.py` changes, regenerate so the
fixture can't silently rot:

```sh
python3 core/js/test/dump_fixtures.py
```

## Fidelity traps (why a naive port drifts)

- **Rounding** (`pyround.mjs`): Python `round()` is round-half-to-**even** of the
  exact binary value; `Math.round` is half-up. The rung/price rounding uses
  `pyround`, reproduced exactly with BigInt + correctly-rounded strtod
  (`Number(string)`). Without this the price drifts by a cent on tie cases.
- **Float compare** (`engine.mjs`): the exact `1e-9` / `1e-12` epsilons from
  `engine.py` are preserved.
- **Enumeration order** (`offer_graph.mjs`): config order mirrors
  `itertools.product` / `itertools.combinations`; the Nash search breaks score
  ties to the first-enumerated config, so order is load-bearing.
- **Sum order** (`engine.mjs`): value/list/cost sums iterate `graph.dims` in
  ORIGINAL order and addon options in SORTED order, matching Python's byte-level
  float sums. (The one exception — Python sums `buyer.value`'s addon term in
  frozenset-hash order, which JS can't reproduce — is a last-ULP difference that
  never crosses a decision boundary; JS sums it in sorted order and the fixtures
  confirm 100% match.)
- **Config serialization** (`test/fidelity.test.mjs`): frozensets ⇆ sorted
  arrays; `canonicalConfig` compares them.
- **`-inf` capacity slots**: a force-dropped fulfillment slot's capacity is
  `-Infinity`, which JSON/JS reject; the dumper encodes non-finite numbers as
  sentinel strings and the test decodes them.
- **`capacity_relief` / `search_filter` closures**: Python closures can't be
  serialized, so the dumper probes each into JSON-safe data (a per-(slot_ticks,
  qty) credit table; an allowed-drinks × allowed-topping-sets whitelist) that
  the JS reconstructs faithfully.

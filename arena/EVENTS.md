# Arena event schema v1 — the sim ↔ renderer contract

Every event is a JSON object with a common envelope:

```
{ "v": 1, "seq": <monotonic int>, "tick": <int>, "gen": <int>,
  "t": <epoch ms>, "type": <str>, ... }
```

- `seq` — strictly increasing; a reconnecting client resumes with `{"type":"hello","since_seq":N}`.
- `tick` — one sim round; the renderer/runner pace on tick changes.
- `t` — wall-clock ms; the renderer's jitter buffer keys on it. Excluded from the determinism hash.
- Unknown `type` ⇒ **renderer no-op** (forward compatible).

## Envelope-level lifecycle

| type | key fields |
|---|---|
| `world.snapshot` | `agents[]`, `era`, `era_label`, `gen`, `assortative`, `config` — sent first on connect and each generation |
| `gen.end` | `gen`, `pop`, `era` — triggers the generation-end census pull-back |

`agents[]` element: `{id, name, house, genome, energy, staked, species, age, lineage, reputation, deals}`.
`genome`: `{pareto_knob, open_aggression, walk_margin, patience, bundle_focus[4], mate_w[4], truncation, staked, tactic_family}`.

## Agents

| type | key fields |
|---|---|
| `agent.spawn` | `id, name, house, genome, species` (seed population) |
| `agent.birth` | `id, name, house, parents[2], genome, endowment, species, lineage` |
| `agent.critical` | `id, energy` — candle gutters (foreshadow death) |
| `agent.death` | `id, cause("starvation"\|"senescence"), age, lineage, deals, heirs[], house` |
| `immigration` | `id, name, house, genome, reason("population_floor"\|"challenger"), challenger?, sponsor_token?` — hall-of-fame reseed or a viewer-forged champion (the token lets the forging client recognize its agent) |

## Market negotiations (duels)

| type | key fields |
|---|---|
| `neg.start` | `neg, kind("price"\|"bundle"), a, b, house, peer(bool — a PACT: both sides attested), roles{seller,buyer}, stakes{rivalry{meetings,series},last_stand}` |
| `neg.offer` | `neg, turn, actor("seller"\|"buyer"), pos` (price) or `package` (bundle), `action`, `spread` |
| `neg.accept` | `neg, pos`/`package`, `surplus{seller,buyer}`, `rounds`, `kind` |
| `neg.walk` | `neg, actor, reason("below_floor"\|"timeout"\|"no_package")` |

`pos` ∈ [0,1] is the settled/ offered position; `spread` = |bid−ask| (drives the gap bar).

## Courtship & mating (the crossover operator)

| type | key fields |
|---|---|
| `mating.round` | `eligible[], matching{p→r}, proposer_rank, receiver_rank, n_proposals, blocking_pairs` |
| `court.start` | `a, b, stakes{a_energy,b_energy}` |
| `court.offer` | `turn, actor("a"\|"b"), package` |
| `court.accept` | `a, b, crossover{block→"pa"\|"pb"\|"blend"\|"extrap"}, child_preview(genome)` |
| `court.impasse` | `a, b, by("a"\|"b"\|"timeout")` |

`crossover` tells the renderer which parent each gene block came from → the child sprite is
assembled from parent parts on screen.

## Grand Auction (set piece)

| type | key fields |
|---|---|
| `auction.start` | `format, pot, n_bidders, bidders[{id,name}]` |
| `auction.bid` | `id, value, bid, shaded(value−bid), truthful` |
| `auction.hammer` | `winner, price, gain, format` |

## World state / metrics

| type | key fields |
|---|---|
| `energy.tick` | `deltas{id→ΔmilliE}` (batched once per upkeep) |
| `era.change` | `era, label, optimal_knob` |
| `species.update` | `species[{id,count,centroid[8],exemplar}]` |
| `census` | `pop, era, staked_frac, mean_knob, era_optimal_knob, mean_energy, n_species, peer_premium, adv_premium, peer_n, attest_lift, attest_n (paired-seed causal probe: same matchup, attestation on vs off), tactics{fam→{n,mean_e,income}}, genes{...}` |
| `leaderboard` | `top[{id,name,house,energy,species,lineage}]` |
| `bloom` | `id, name, house, genome, flower{species,warmth,showiness,height,luminance,layering,staked}, beauty, rarity, pollinator{name,glyph}` — the Bloom of the Generation (full-screen payoff) |
| `highlight` | `kind, refs{...}, blurb` — the director / cut-in triggers |

`world.snapshot` and `era.change` also carry `pollinator{name,glyph}` — the season's
aesthetic. The flower is the phenotype of the genome (see arena/flora.py); the renderer
draws it, so no flower data beyond `flower{...}` is transmitted for live crests.

`highlight.kind` ∈ `record_surplus, dynasty_founder_death, dynasty_founded, era_flip, grand_auction`.

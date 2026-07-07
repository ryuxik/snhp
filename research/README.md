# Transfer Market Mechanics — simulation code

Each piece at [snhp.dev/research](https://snhp.dev/research) is backed by one
script here. Run from the repo root:

```bash
pip install -e .
PYTHONPATH=. python3 research/tonali_sim.py      # No. 1 — the £100m Tonali replay
PYTHONPATH=. python3 research/mora_sim.py        # No. 2 — the Mora clause auction
PYTHONPATH=. python3 research/lira_sim.py        # No. 3 — the Lira promise, priced
PYTHONPATH=. python3 research/diomande_sim.py    # No. 4 — the Diomande ladder
PYTHONPATH=. python3 research/wcpremium_sim.py   # No. 5 — the World Cup premium
```

Everything is seeded; each script prints the JSON committed alongside it.
The engines used: `gametheory.negotiation` (single- and multi-issue bargaining),
`snhp.nash_solver` (Pareto/Nash), `snhp.core_math.rubinstein`,
`gametheory.mechanism.posted_price` (Gallego–van Ryzin), `gametheory.auctions`.

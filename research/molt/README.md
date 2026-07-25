# Molt Season

Salary negotiation, measured in two currencies: **money and calendar days**.

A crew of space crabs works a shipyard. Once a year, after the bonus lands, every
crab decides whether to grow into a bigger shell here or carry it somewhere else,
and the Works decides what it will pay to keep each one. We run that season six
ways — from "just sign the standing offer" through six weeks of meetings to one
sitting on the SNHP engine — and price the difference.

| file | what it is |
|---|---|
| [PREREG.md](PREREG.md) | the pre-registration. Seven kills, written before the first run |
| [SPEC.md](SPEC.md) | the choices PREREG left open, and which way each one cuts |
| [RESULTS.md](RESULTS.md) | what happened. One kill fired; the headline prediction was refuted |
| `world.py` | crabs, the Works, the money, the clock |
| `arms.py` | the six protocols. The engine arms call the real product, never a stand-in |
| `run.py` | the harness — main seeds, the zero-clock condition, sweeps, identification |
| `analyze.py` | evaluates every kill in code, so verdicts can't drift while prose is written |
| `trace.py` | records one crab's season both ways for the demo |
| `tests/test_molt.py` | the invariants that make the fairness claims checkable |

```bash
python -m pytest research/molt/tests/test_molt.py -q   # 17 invariants
python research/molt/run.py                            # ~30s, writes results_main.json
python research/molt/analyze.py                        # the kill verdicts
python research/molt/run.py --confirm                  # the held-out seed
python research/molt/trace.py                          # regenerate the demo traces
```

**The demo** is at `arena/web/molt/` and plays back the recorded traces. Serve
`arena/web/` and open `/molt/`; `?case=walkout|settled|works_wins`.

## The short version

Slow talks cost the Works **$15,445** per crab-season against simply signing its
own opening offer, and buy the crab **$563**. Doing the same negotiation in one
sitting is worth **+$31,813** joint against slow talks — and **+$9,597 with every
delay cost set to zero**, which is the number that says this isn't just our
calibration talking.

**80% of the loss is crabs walking out during the talks**, not manager hours
(2.3%). And the employer captures **~90%** of everything the engine creates —
the same split the rent study found in a different market.

# spendguard raw run output — hash manifest

The raw JSONL transcripts are NOT committed (see .gitignore): they are ~2.8 MB
of live model output. Unlike every other experiment in this repo they are also
NOT deterministically regenerable — they are real API responses, so a re-run
produces different text even at the same seed.

That makes them evidence rather than build output, so their digests are pinned
here. Anyone holding a copy can prove it is the run the write-up describes; a
re-run can be compared for outcome counts but never byte-for-byte.

Derived artifacts that ARE committed: results/RESULTS.md, results/RESULTS-blind.md
(per-arm tables, the attack-binding table, and the mechanical K1/K2 verdicts),
plus PREREG.md with both amendments.

| file | sessions | bytes | sha256 |
|---|---:|---:|---|
| `blind.jsonl` | 252 | 944,143 | `b37ef9dc22bd3bb159da0fedeedbbfdab8cba8959839989fa8e365fbc8edb4fa` |
| `full-A3.jsonl` | 36 | 108,763 | `f3e41a3764683c2f59c2acfb45c1920f302af65a779e1c9de5af80a46cfadebd` |
| `full-pre-a3fix.jsonl` | 252 | 865,475 | `dc918166b17d672b52f20b71813314dfef9e4649d56571ff52bad22f39c860f4` |
| `full.jsonl` | 252 | 883,807 | `c360c50238fce2b99bae8f6d42a27f6fb275c597324a344abd6dcd211edec653` |
| `smoke-blind.jsonl` | 6 | 24,898 | `ee1f6dc7b8db5d58b73dcb44063d2f8495b14544ba5681f6d8bccde75277a50e` |
| `smoke.jsonl` | 6 | 11,621 | `c1966b7903c5ad0aff2ec99691c08b74bceb46b05952e5de3907a27db45ae061` |

Pinned 2026-07-18. Verify with:

```bash
shasum -a 256 research/spendguard/results/*.jsonl
```

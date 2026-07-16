#!/usr/bin/env python3
"""Guards on the checked-in company diorama logs (arena/web/company/logs/*.json).

Runs stand-alone (`python3 arena/web/company/test_company_logs.py`) or under
pytest. No third-party deps. These assert the renderer's honesty contract on the
DATA it binds to: the logs parse, they carry every field index.html reads, their
per-frame counters are internally consistent, the summary counters the on-screen
HUD shows are derivable from the frames, and the three-way regime CONTRAST that
is the money shot is actually present in the numbers (not asserted by the UI).

If these fail after a mechanism/logger change, regenerate:
    python3 research/swarm/company_log.py --regime all
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(HERE, "logs")
REGIMES = ("spot", "claims", "director")
TOP_FIELDS = ("schema", "regime", "config", "grid", "refineries", "sources",
              "num_floors", "floor_edges", "floor_labels", "reach",
              "sample_every", "total_stock", "robots", "cite", "frames",
              "summary")


def _load(regime):
    with open(os.path.join(LOGDIR, f"{regime}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_logs_parse_and_have_fields():
    """Every checked-in log parses and carries the fields the renderer reads."""
    for r in REGIMES:
        path = os.path.join(LOGDIR, f"{r}.json")
        assert os.path.exists(path), f"missing checked-in log {r}.json"
        log = _load(r)
        for f in TOP_FIELDS:
            assert f in log, f"{r}.json missing field {f!r}"
        assert log["regime"] == r
        assert log["config"]["n_robots"] == len(log["robots"])
        assert len(log["floor_edges"]) + 1 == log["num_floors"] == \
            len(log["floor_labels"])
        for key in ("spec", "text", "numbers"):
            assert log["cite"][key], f"{r}.json cite missing {key!r}"


def test_frame_counters_consistent_and_match_summary():
    """The HUD reads f.d / f.h2 / f.ho and the summary. They must be monotone,
    well-formed (state in 0..3, one row per robot), and the LAST frame must equal
    the summary the counters cite. twohop_share == twohop/delivered."""
    for r in REGIMES:
        log = _load(r)
        n = log["config"]["n_robots"]
        prev_d = prev_h2 = prev_ho = -1
        for fr in log["frames"]:
            assert len(fr["r"]) == n, f"{r}: frame {fr['t']} lost robots"
            for x, y, st in fr["r"]:
                assert st in (0, 1, 2, 3), f"{r}: bad state {st}"
                assert 0 <= x < log["grid"] and 0 <= y < log["grid"]
            assert fr["d"] >= prev_d and fr["h2"] >= prev_h2 and fr["ho"] >= prev_ho, \
                f"{r}: cumulative counter went backwards at t={fr['t']}"
            assert fr["h2"] <= fr["d"], f"{r}: ≥2-hop exceeds delivered"
            prev_d, prev_h2, prev_ho = fr["d"], fr["h2"], fr["ho"]
        last, s = log["frames"][-1], log["summary"]
        assert last["d"] == s["delivered"], f"{r}: HUD delivered != summary"
        assert last["h2"] == s["twohop"], f"{r}: HUD twohop != summary"
        assert last["ho"] == s["handoffs"], f"{r}: HUD handoffs != summary"
        assert s["delivered"] <= log["total_stock"]
        assert s["twohop_share"] == round(s["twohop"] / max(1, s["delivered"]), 4)


def test_director_frames_carry_command_channel():
    """Only the director log carries the per-frame command-staleness channel the
    renderer surfaces (order age / on-order); spot & claims must not."""
    d = _load("director")
    assert all("cmd" in f and len(f["cmd"]) == 2 for f in d["frames"]), \
        "director frames missing cmd [commanded, plan_age]"
    for r in ("spot", "claims"):
        assert all("cmd" not in f for f in _load(r)["frames"]), \
            f"{r} frames carry a command channel they should not"


def test_money_shot_contrast_is_in_the_data():
    """The three-way contrast the renderer dramatizes is REAL, not scripted:
    claims forms the chains spot cannot and command forms none; claims ships
    most, command least. This mirrors the banked P23a/PXc/PXa signature."""
    S = {r: _load(r)["summary"] for r in REGIMES}
    # ≥2-hop chain share: spot ~2.5%, claims ~50%, director 0%
    assert S["spot"]["twohop_share"] < 0.10, "spot chains too high"
    assert S["claims"]["twohop_share"] > 0.40, "claims chains too low"
    assert S["director"]["twohop"] == 0, "command formed chains (should be 0)"
    # throughput ordering: claims > spot > director (claims wins, command loses)
    assert S["claims"]["delivered"] > S["spot"]["delivered"] > S["director"]["delivered"]
    # claims resolves deadlocks via hand-offs → far more hand-offs & entries
    assert S["claims"]["handoffs"] > 10 * S["spot"]["handoffs"]
    assert S["claims"]["deadlock_entries"] > S["spot"]["deadlock_entries"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} checks passed on {len(REGIMES)} logs")

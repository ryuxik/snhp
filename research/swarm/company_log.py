"""Pure-observer event logger for the v26-R Company diorama
(arena/web/company). Re-skins the swarm engine as a firm WITHOUT touching it.

This module CONSTRUCTS a World with an ALREADY-REGISTERED configuration (the
column-X regimes, run.py `column == "X"`) and OBSERVES it tick-by-tick through
public state only. It appends to its OWN buffers; it never writes World/Robot
state, never touches RNG / physics / Φ / any decision path. Therefore running
with the observer attached is BIT-IDENTICAL to running the same World plain
(test_company_log_observer_bit_identical / _differential_oracle). This is the
established external-replay pattern of trace.py, specialised to the company
building metaphor — NO new mechanism, NO engine edit (the FIDELITY KILL).

Registered mapping (SPEC v26-R "Y-A"):
    idea/project           = asteroid ore unit
    stage chain            = distance bands (floors) far edge -> refinery
      research (top floor) = far band (ore is mined at the frontier)
      design/build (middle)= mid bands (where hand-offs happen)
      shipping (ground)    = the refinery (delivery)
    stalled idea           = routing deadlock (loaded, can't deliver one-hop)
    pre-committed splits    = bills claim stacks (the notarised receipt)
    delivery / LAUNCH      = refine at the refinery
    budget / rest          = battery / chargers
    director               = command regime (central planner)
    carriers between stages= middlemen hand-offs (cargo transfers)
    stage workers          = ICs (the robots)

Regimes (X's arms on ONE information environment; same seed):
    spot     : baseline, no settlement mechanism  (P23/PX baseline)
    claims   : bills=True — the notarised claim stack (P23a / PXc)
    director : command=True — the central planner  (PXa)

Every quantitative claim the diorama makes is an ALREADY-BANKED number (the
`cite` block, copied verbatim from the SPEC verdicts). The live per-frame
counters are the REAL numbers of this seeded run.

Log schema (ONE json object per regime; the renderer loads one file/regime):
  {
    "schema": 2, "regime": "spot|claims|director",
    "config": {arm, n_robots, sigma, tau, seed, ticks, grid,
               belief_mode, gossip, r_radio, lineage, deadlock_track,
               bills, command, firm_relay},
    "grid": G, "refineries": [[x,y]...], "sources": [[x,y]...],
    "num_floors": F, "floor_edges": [...], "floor_labels": [...],
    "reach": R, "sample_every": K, "total_stock": T,
    "robots": [{"id":i,"cap":c,"company":co}, ...],
    "cite": {"spec": "...", "text": "...", "numbers": {...}},
    "frames": [
       {"t": t,
        "r": [[x, y, state], ...],   # state 0=empty 1=loaded 2=stuck 3=stranded
        "d": delivered_cum, "h2": twohop_delivered_cum,
        "ho": handoffs_cum, "dl": deals_cum, "bat": mean_battery,
        "cmd": [commanded_count, mean_plan_age]   # director regime only
       }, ...
    ],
    "summary": {delivered, deals, handoffs, twohop, twohop_share,
                deadlock_entries, stuck_peak, strandings, ticks, makespan}
  }

State per robot per frame is derived read-only:
    stranded            -> 3
    routing-deadlock    -> 2  (loaded & can't deliver one-hop; the "stuck idea")
    load > 0            -> 1  (carrying an idea folder)
    otherwise           -> 0
`floor(dist)` (renderer + logger agree) buckets a robot's Manhattan distance to
its nearest refinery into F floors via `floor_edges`; band 0 = ground/shipping,
band F-1 = top/research.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from swarm.arms import make_arm                                    # noqa: E402
from swarm.world import BATTERY_MAX, LOADED_MULT, World          # noqa: E402

SCHEMA = 2

# Single-hop LOADED reach — the same quantity the placement / deadlock code
# prices (SPEC: charger_band = BATTERY_MAX/(1+LOADED_MULT)). Floors are cut as
# fractions of it, so the building's storeys are the economy's real distance
# bands, not decorative.
REACH = BATTERY_MAX / (1.0 + LOADED_MULT)
FLOOR_FRACS = (0.25, 0.55, 0.90, 1.40)          # -> 5 floors (ground..top)
FLOOR_LABELS = ("shipping", "build", "design", "research", "frontier")

# The banked verdicts each regime illustrates. Text copied VERBATIM from the
# SPEC verdict blocks (P23 / PX). No invented numbers — the renderer shows
# these as the caption and the live log numbers as the counters.
CITES = {
    "spot": dict(
        spec="P23a / PXc (baseline)",
        text=("Spot bargaining forms almost no chains: ≥2-hop delivered share "
              "0.025 (2.5%). Ideas reach the middle floors and stall — the "
              "hold-up P24 diagnosed as the N=240 plateau."),
        numbers={"twohop_share_banked": 0.025,
                 "delivered_frac_banked": 0.825,
                 "note": "N=240, 2,500t, snhp+net baseline"}),
    "claims": dict(
        spec="P23a / PXc",
        text=("Negotiable delivery claims (bills of lading) lift ≥2-hop "
              "delivered share 0.025 -> 0.500 — a 20x rise in real relay "
              "chains; N=240 delivered_frac +0.0295. Claims -baseline "
              "delivered +91.8 @2,500t, +115.5 @7,500t. The notarised receipt "
              "is working capital: it makes the chains exist."),
        numbers={"twohop_share_banked": 0.500,
                 "delivered_frac_banked": 0.863,
                 "claims_minus_baseline_2500t": 91.8,
                 "claims_minus_baseline_7500t": 115.5,
                 "note": "P23a: 0.025->0.500; PXc N=240"}),
    "director": dict(
        spec="PXa / KILL",
        text=("Central command LOSES to its own information latency: the plan "
              "is ~50 ticks stale when computed and ~42 in transit, and forms "
              "NO opportunistic chains (≥2-hop share 0.000). N=240/7,500t: "
              "claims delivered 2096.0 vs command 1954.8 (Δ −141.2, p=0.001, "
              "0/8 seeds). Command never beats claims."),
        numbers={"twohop_share_banked": 0.000,
                 "claims_delivered_7500t": 2096.0,
                 "command_delivered_7500t": 1954.8,
                 "delta_command_minus_claims_7500t": -141.2,
                 "note": "PXa refuted; KILL does not fire"}),
}

REGIMES = {
    "spot": dict(),
    "claims": dict(bills=True),
    "director": dict(command=True),
}


def _floor_edges(reach: float = REACH):
    # written to the log so the RENDERER buckets each robot's logged (x,y)
    # distance-to-refinery into floors (the logger stores raw positions).
    return [round(reach * f, 3) for f in FLOOR_FRACS]


def make_world(regime: str, n_robots: int, seed: int, ticks: int,
               grid: int | None = None) -> tuple:
    """Construct the column-X World for `regime` EXACTLY as run.py does
    (arm snhp+net, belief+gossip r_radio=6, lineage + deadlock instrument),
    plus the regime flag. Returns (World, arm)."""
    if regime not in REGIMES:
        raise ValueError(f"unknown regime {regime!r} (want {list(REGIMES)})")
    if grid is None:
        grid = int(round(32 * math.sqrt(n_robots / 24)))
    kw = dict(n_robots=n_robots, sigma=0.5, seed=seed, hazard_phi=True,
              preset="v5", tau=(0.15, 0.15), grid=grid,
              belief_mode=True, gossip=True, r_radio=6,
              lineage=True, deadlock_track=True)
    kw.update(REGIMES[regime])
    w = World(**kw)
    arm = make_arm("snhp+net", w)
    return w, arm


def _robot_state(w: World, r) -> int:
    if r.stranded:
        return 3
    if w._in_deadlock[r.rid]:               # loaded & one-hop-unreachable
        return 2
    if r.load > 0:
        return 1
    return 0


def run_logged(regime: str, n_robots: int = 240, seed: int = 0,
               ticks: int = 2500, sample_every: int = 20,
               grid: int | None = None, observe=None) -> dict:
    """Run one regime and return its diorama log dict. PURE OBSERVER: only
    reads World/Robot state after each `arm.tick()`. `observe`, if given, is a
    read-only per-tick callback (used by the bit-identical test) — it must not
    mutate anything."""
    w, arm = make_world(regime, n_robots, seed, ticks, grid=grid)
    edges = _floor_edges(REACH)
    refs = [list(p) for p in w.refineries]
    frames = []
    stuck_peak = 0
    strand_entries = 0
    prev_stranded = [False] * len(w.robots)

    for t in range(ticks):
        arm.tick()
        if observe is not None:
            observe(w)
        # ---- rising-edge stranding tally (external, read-only) -------------
        cur_stuck = 0
        for r in w.robots:
            if r.stranded and not prev_stranded[r.rid]:
                strand_entries += 1
            prev_stranded[r.rid] = r.stranded
            if w._in_deadlock[r.rid]:
                cur_stuck += 1
        stuck_peak = max(stuck_peak, cur_stuck)
        # ---- sampled frame -------------------------------------------------
        if (t % sample_every == 0) or (t == ticks - 1) \
                or w.delivered >= w.total_stock:
            twohop = sum(1 for p in w.delivered_parcels if p["hops"] >= 2)
            handoffs = sum(1 for e in w.event_log if e["kind"] == "cargo")
            bat = sum(r.battery for r in w.robots) / max(1, len(w.robots))
            frame = dict(
                t=w.tick,
                r=[[r.pos[0], r.pos[1], _robot_state(w, r)] for r in w.robots],
                d=w.delivered, h2=twohop, ho=handoffs,
                dl=len(w.deal_log), bat=round(bat, 1))
            if regime == "director":
                held = [w.tick - w.cmd_held_tick[r.rid] for r in w.robots
                        if not r.stranded and w.cmd_held_tick[r.rid] >= 0]
                frame["cmd"] = [len(held),
                                round(sum(held) / len(held), 1) if held else 0.0]
            frames.append(frame)
        if w.delivered >= w.total_stock:
            break

    twohop = sum(1 for p in w.delivered_parcels if p["hops"] >= 2)
    handoffs = sum(1 for e in w.event_log if e["kind"] == "cargo")
    summary = dict(
        delivered=w.delivered, deals=len(w.deal_log), handoffs=handoffs,
        twohop=twohop,
        twohop_share=round(twohop / max(1, w.delivered), 4),
        deadlock_entries=w.deadlock_count, stuck_peak=stuck_peak,
        strandings=strand_entries, ticks=w.tick,
        makespan=w.tick if w.delivered >= w.total_stock else ticks)

    return dict(
        schema=SCHEMA, regime=regime,
        config=dict(arm="snhp+net", n_robots=n_robots, sigma=0.5, tau=0.15,
                    seed=seed, ticks=ticks, grid=w.grid,
                    belief_mode=True, gossip=True, r_radio=6, lineage=True,
                    deadlock_track=True,
                    bills=bool(REGIMES[regime].get("bills")),
                    command=bool(REGIMES[regime].get("command")),
                    firm_relay=bool(REGIMES[regime].get("firm_relay"))),
        grid=w.grid, refineries=refs,
        sources=[list(s) for s in w.sources],
        num_floors=len(edges) + 1, floor_edges=edges,
        floor_labels=list(FLOOR_LABELS), reach=round(REACH, 2),
        sample_every=sample_every, total_stock=w.total_stock,
        robots=[dict(id=r.rid, cap=r.cap, company=r.company) for r in w.robots],
        cite=CITES[regime], frames=frames, summary=summary)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate company diorama logs.")
    ap.add_argument("--regime", default="all",
                    help="spot|claims|director|all")
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ticks", type=int, default=2500)
    ap.add_argument("--sample-every", type=int, default=20)
    ap.add_argument("--out-dir", default=os.path.join(
        _ROOT, "arena", "web", "company", "logs"))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    regimes = list(REGIMES) if args.regime == "all" else [args.regime]
    for reg in regimes:
        log = run_logged(reg, n_robots=args.n, seed=args.seed,
                         ticks=args.ticks, sample_every=args.sample_every)
        path = os.path.join(args.out_dir, f"{reg}.json")
        with open(path, "w") as f:
            json.dump(log, f, separators=(",", ":"))
        sz = os.path.getsize(path)
        s = log["summary"]
        print(f"{reg:9s} -> {path}  ({sz/1e6:.2f} MB)  "
              f"delivered={s['delivered']} twohop={s['twohop']} "
              f"share={s['twohop_share']} entries={s['deadlock_entries']} "
              f"stuck_peak={s['stuck_peak']} frames={len(log['frames'])}")


if __name__ == "__main__":
    main()

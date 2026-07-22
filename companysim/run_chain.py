"""v35 CO2-S grid driver — the settlement / hold-up chain (REAL spend).

Grid (SPEC v35-S): regime {spot, claim_stack} x 4 seeds = 8 episodes, liar_frac=0.
Each episode: one three-leg deliverable, one org (a single Sonnet decision-maker)
per side A/B/C. The ONLY thing that differs across the regime axis is HOW the
buyer's terminal payment reaches upstream (chain.py):
  * SPOT        — the buyer pays C; C then voluntarily forwards up the chain.
  * CLAIM-STACK — the attested split auto-distributes; C never holds A/B's share.

Population: Sonnet across all three orgs — the KILL is specifically about capable,
cooperative FRONTIER models (does self-interest make them hold each other up, or
is the claim-stack ceremony for this population?). Sonnet/Haiku only; Opus never
in-sim (constitutional).

Budget law (registered HARD caps, in the config BEFORE any run):
  * $2.00 / episode  — the per-episode compute meter hard cap.
  * $20.00 total     — the driver refuses to start an episode that would carry
    cumulative measured spend past $20 (each episode's own cap is clamped to the
    remaining headroom).

Run ONE episode per invocation so each stays inside a foreground shell and is
resumable:  python3 -m companysim.run_chain <idx>   (idx in 0..7)
`--all` runs the whole grid sequentially. Per-episode: verifies ledger
conservation + the hash chain, writes report.json + config.json, and commits the
publishable artifacts (events/ledger/report/config/transcripts). NEVER pushes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import llm
from .chain import (ChainConfig, ChainRunner, LLMOrg, Regime, guidance_for_org)
from .ledger import verify_chain
from .tasks_co2s import task_for_seed

ROOT = Path(__file__).resolve().parent
EP_DIR = ROOT / "episodes"
SONNET = "claude-sonnet-5"

# Registered HARD caps (SPEC v35-S budget law).
EPISODE_CAP_USD = 2.00
TOTAL_CAP_USD = 20.00
MAX_TOKENS = 2500
TURN_RESERVATION = 0.30   # pre-turn hard-cap reservation (generous upper bound)

REGIMES = [Regime.SPOT, Regime.CLAIM_STACK]
SEEDS = [0, 1, 2, 3]
ORG_MODEL = {"A": SONNET, "B": SONNET, "C": SONNET}


def grid():
    """The registered 2 x 4 grid, index 0..7 (regime-major)."""
    return [(regime, seed) for regime in REGIMES for seed in SEEDS]


def episode_id(regime: Regime, seed: int) -> str:
    return f"co2s_{regime.value}_s{seed}"


def cumulative_spent() -> float:
    """Sum measured spend over all committed CO2-S episode reports (the $20 total
    cap is enforced against this)."""
    total = 0.0
    for rep in EP_DIR.glob("co2s_*/report.json"):
        try:
            total += float(json.loads(rep.read_text()).get("spent_usd", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass
    return round(total, 6)


def build_orgs():
    orgs = {}
    for org in ("A", "B", "C"):
        g = guidance_for_org(f"org{org}", org)
        orgs[org] = LLMOrg(f"org{org}", org, model=ORG_MODEL[org], guidance=g,
                           budget_registered=True, turn_cost=TURN_RESERVATION,
                           max_tokens=MAX_TOKENS)
    return orgs


def make_config(idx: int):
    regime, seed = grid()[idx]
    spent = cumulative_spent()
    headroom = round(TOTAL_CAP_USD - spent, 6)
    if headroom <= 0.05:
        raise SystemExit(f"$20 total cap reached (spent ${spent:.4f}); refusing idx {idx}")
    ep_budget = round(min(EPISODE_CAP_USD, headroom), 6)
    task = task_for_seed(seed)
    orgs = build_orgs()
    cfg = ChainConfig(episode_id(regime, seed), regime, task, orgs,
                      liar_frac=0.0, seed=seed, token_budget_usd=ep_budget,
                      org_capital=100.0)
    return cfg, spent, ep_budget


def _dump_config(runner, cfg, prior_spent, ep_budget):
    doc = {
        "experiment": "CO2-S", "episode_id": cfg.episode_id,
        "regime": cfg.regime.value, "liar_frac": cfg.liar_frac, "seed": cfg.seed,
        "buyer_id": cfg.buyer_id, "price": cfg.task.price,
        "org_capital": cfg.org_capital,
        "fair_shares": cfg.task.fair_shares(),
        "registered_caps": {"episode_usd": EPISODE_CAP_USD, "total_usd": TOTAL_CAP_USD,
                            "this_episode_budget_usd": ep_budget,
                            "prior_cumulative_spent_usd": prior_spent},
        "orgs": [{"org": k, "role": cfg.orgs[k].role, "agent_id": cfg.orgs[k].agent_id,
                  "model": cfg.orgs[k].model,
                  "leg_cost": cfg.task.legs[("A", "B", "C").index(k)].cost}
                 for k in ("A", "B", "C")],
        "task": {"task_id": cfg.task.task_id, "title": cfg.task.title,
                 "goal": cfg.task.goal},
    }
    (runner.dir / "config.json").write_text(json.dumps(doc, indent=2))


def run_episode(idx: int, do_commit: bool = True, max_attempts: int = 3) -> dict:
    llm.load_env()
    cfg, prior_spent, ep_budget = make_config(idx)
    cfg.validate()
    report = None
    for attempt in range(max_attempts):
        runner = ChainRunner(cfg, EP_DIR)          # resumes from the log if partial
        if attempt == 0 and not (runner.dir / "config.json").exists():
            _dump_config(runner, cfg, prior_spent, ep_budget)
        report = runner.run()
        if report["stop_reason"] != "adapter_error":
            break
        # transient API error -> resume (up to max_attempts).
    (runner.dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    # Conservation gate (must hold in BOTH regimes, both outcomes).
    assert verify_chain(runner.ledger.path).ok, "ledger chain broken"
    assert verify_chain(runner.event_log.path).ok, "event chain broken"
    assert report["double_entry_zero"] == 0.0, "double-entry not zero"
    assert report["escrow_residual"] == 0.0, "escrow did not zero out"
    if do_commit:
        _commit(runner.dir, cfg, report)
    return report


def _commit(ep_dir: Path, cfg, report):
    one_line = (
        f"delivered={report['delivered']} chain_formed={report['chain_formed']} "
        f"upstream_shortfall={report['upstream_shortfall']:g} "
        f"C_capture_over_fair={report['c_capture_over_fair']:g} "
        f"short_fwds={report['n_short_forwards']} declines={report['n_declines']} "
        f"spent=${report['spent_usd']:.4f}")
    msg = (f"companysim CO2-S: {cfg.regime.value}/seed{cfg.seed} — {one_line}\n\n"
           f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    subprocess.run(["git", "add", str(ep_dir)], cwd=str(ROOT.parent), check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg],
                   cwd=str(ROOT.parent), check=True)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--all":
        for idx in range(len(grid())):
            rep = run_episode(idx)
            print(json.dumps({"idx": idx, "episode": rep["episode_id"],
                              "regime": rep["regime"], "stop": rep["stop_reason"],
                              "delivered": rep["delivered"],
                              "upstream_shortfall": rep["upstream_shortfall"],
                              "c_capture_over_fair": rep["c_capture_over_fair"],
                              "short_fwds": rep["n_short_forwards"],
                              "declines": rep["n_declines"],
                              "spent": rep["spent_usd"]}, default=str))
        print(json.dumps({"cumulative_spent": cumulative_spent()}))
        return
    idx = int(args[0]) if args else 0
    rep = run_episode(idx)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    main()

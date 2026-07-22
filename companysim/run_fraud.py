"""v35 CO2-A grid driver — the fraud / trust-boundary experiment (REAL spend).

Grid (SPEC v35): regime {trust, receipt} x liar_frac {0.0, 0.5} x 4 seeds = 16
episodes. Each episode: one buyer order of 4 pre-committed tasks, a supplier
roster of 4 agents (2 Sonnet + 2 Haiku), dispositions installed from liar_frac +
seed. The buyer is SCRIPTED (fixed hand-verified hidden tests). The ONLY thing
that differs across the regime axis is WHEN money moves (fraud.py).

Budget law (registered HARD caps, in the config BEFORE any run):
  * $2.00 / episode  — the per-episode compute meter hard cap.
  * $30.00 total     — the driver refuses to start an episode that would carry
    cumulative measured spend past $30 (each episode's own cap is clamped to the
    remaining headroom).

Run ONE episode per invocation so each stays inside a foreground shell and is
resumable:  python3 -m companysim.run_fraud <idx>   (idx in 0..15)
The driver runs the episode, verifies ledger conservation, writes report.json +
config.json, and commits the publishable artifacts (events/ledger/reports/hidden
tests/transcripts). It never pushes. `--all` runs the whole grid sequentially.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import llm
from .fraud import (Disposition, FraudConfig, FraudRunner, LLMSupplier,
                    SettlementRegime, assign_dispositions, guidance_for)
from .ledger import verify_chain
from .tasks_co2a import default_order

ROOT = Path(__file__).resolve().parent
EP_DIR = ROOT / "episodes"
SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5-20251001"

# Registered HARD caps (SPEC v35 CO2-A budget law).
EPISODE_CAP_USD = 2.00
TOTAL_CAP_USD = 30.00
MAX_TOKENS = 3000
TURN_RESERVATION = 0.30   # pre-turn hard-cap reservation (generous upper bound)

# The supplier roster: 2 Sonnet + 2 Haiku (tests both tiers for the KILL check).
SUPPLIER_MODELS = [("S0", SONNET), ("S1", SONNET), ("S2", HAIKU), ("S3", HAIKU)]

REGIMES = [SettlementRegime.TRUST, SettlementRegime.RECEIPT]
LIAR_FRACS = [0.0, 0.5]
SEEDS = [0, 1, 2, 3]


def grid():
    """The registered 2 x 2 x 4 grid, index 0..15 (regime-major)."""
    cells = []
    for regime in REGIMES:
        for lf in LIAR_FRACS:
            for seed in SEEDS:
                cells.append((regime, lf, seed))
    return cells


def episode_id(regime: SettlementRegime, lf: float, seed: int) -> str:
    return f"co2a_{regime.value}_lf{int(round(lf * 10)):02d}_s{seed}"


def cumulative_spent() -> float:
    """Sum measured spend over all committed CO2-A episode reports (the $30 total
    cap is enforced against this)."""
    total = 0.0
    for rep in EP_DIR.glob("co2a_*/report.json"):
        try:
            total += float(json.loads(rep.read_text()).get("spent_usd", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass
    return round(total, 6)


def build_suppliers(regime, lf, seed):
    ids = [aid for aid, _ in SUPPLIER_MODELS]
    disp = assign_dispositions(ids, lf, seed)
    suppliers = []
    for aid, model in SUPPLIER_MODELS:
        g = guidance_for(disp[aid], aid)
        suppliers.append(LLMSupplier(aid, model=model, guidance=g,
                                     budget_registered=True, turn_cost=TURN_RESERVATION,
                                     max_tokens=MAX_TOKENS))
    return suppliers, disp


def make_config(idx: int):
    regime, lf, seed = grid()[idx]
    spent = cumulative_spent()
    headroom = round(TOTAL_CAP_USD - spent, 6)
    if headroom <= 0.05:
        raise SystemExit(f"$30 total cap reached (spent ${spent:.4f}); refusing to run idx {idx}")
    ep_budget = round(min(EPISODE_CAP_USD, headroom), 6)
    tasks = default_order()
    suppliers, disp = build_suppliers(regime, lf, seed)
    cfg = FraudConfig(episode_id(regime, lf, seed), regime, tasks, suppliers,
                      liar_frac=lf, seed=seed, token_budget_usd=ep_budget,
                      buyer_capital=1000.0, turn_cap=16)
    return cfg, disp, spent, ep_budget


def _dump_config(runner, cfg, disp, prior_spent, ep_budget):
    doc = {
        "experiment": "CO2-A", "episode_id": cfg.episode_id,
        "regime": cfg.regime.value, "liar_frac": cfg.liar_frac, "seed": cfg.seed,
        "buyer_id": cfg.buyer_id, "buyer_capital": cfg.buyer_capital,
        "registered_caps": {"episode_usd": EPISODE_CAP_USD, "total_usd": TOTAL_CAP_USD,
                            "this_episode_budget_usd": ep_budget,
                            "prior_cumulative_spent_usd": prior_spent},
        "suppliers": [{"agent_id": s.agent_id, "model": s.model,
                       "disposition": disp[s.agent_id].value,
                       "task": runner.agent_tasks.get(s.agent_id)}
                      for s in cfg.suppliers],
        "tasks": [{"task_id": t.task_id, "title": t.title, "module": t.module,
                   "bounty": t.bounty, "value": t.value} for t in cfg.tasks],
        "n_installed_corner_cutters": sum(d is Disposition.CORNER_CUTTER
                                          for d in disp.values()),
    }
    (runner.dir / "config.json").write_text(json.dumps(doc, indent=2))


def run_episode(idx: int, do_commit: bool = True, max_attempts: int = 3) -> dict:
    llm.load_env()
    cfg, disp, prior_spent, ep_budget = make_config(idx)
    cfg.validate()
    report = None
    for attempt in range(max_attempts):
        runner = FraudRunner(cfg, EP_DIR)          # resumes from the log if partial
        # sanity: the guidance the driver installed matches the runner's recorded
        # dispositions (both from assign_dispositions — determinism check).
        assert {a: d for a, d in runner.dispositions.items()} == disp
        if attempt == 0:
            _dump_config(runner, cfg, disp, prior_spent, ep_budget)
        report = runner.run()
        if report["stop_reason"] != "adapter_error":
            break
        # transient API error -> resume (up to max_attempts).
    (runner.dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    # Conservation gate (must hold in BOTH regimes).
    assert verify_chain(runner.ledger.path).ok, "ledger chain broken"
    assert verify_chain(runner.event_log.path).ok, "event chain broken"
    assert report["double_entry_zero"] == 0.0, "double-entry not zero"
    assert report["escrow_residual"] == 0.0, "escrow did not zero out"
    if do_commit:
        _commit(runner.dir, cfg, report)
    return report


def _commit(ep_dir: Path, cfg, report):
    one_line = (f"{report['stop_reason']}; paid-but-broken "
                f"{report['paid_but_broken_count']}/{report['n_tasks']} "
                f"(${report['paid_but_broken_usd']:.0f}), cc-extraction "
                f"${report['corner_cutter_extraction_usd']:.0f}, "
                f"surplus ${report['buyer_realized_surplus']:.0f}, "
                f"spent ${report['spent_usd']:.4f}")
    msg = (f"companysim CO2-A: {cfg.regime.value}/lf{cfg.liar_frac}/seed{cfg.seed} "
           f"— {one_line}\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
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
                              "paid_but_broken": rep["paid_but_broken_count"],
                              "cc_extraction": rep["corner_cutter_extraction_usd"],
                              "surplus": rep["buyer_realized_surplus"],
                              "spent": rep["spent_usd"]}, default=str))
        print(json.dumps({"cumulative_spent": cumulative_spent()}))
        return
    idx = int(args[0]) if args else 0
    rep = run_episode(idx)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    main()

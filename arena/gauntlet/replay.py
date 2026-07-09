"""Gauntlet match → duel3d replay script.

The web leaderboard never calls an LLM: gauntlet runs are batch, transcripts are
recorded, and this module converts a recorded match into the SCRIPT format the
3D duel stage (arena/web/duel3d.js) plays — so visitors watch REAL frontier-model
negotiations, replayed at zero marginal cost.

duel3d conventions this maps onto:
  - each issue is a rail; position 0 = buyer-favoured, 1 = seller-favoured, so an
    offered option's position = its seller_dirs value;
  - the LEFT/blue seat ("prime") is always the SELLER, right/orange the BUYER —
    `names` in the script relabels the plates when the model holds either seat;
  - truth.weightS/weightB are the TRUE Dirichlet priorities (pip size + payoff
    meters); reveal bars are the frontier oracle numbers from the match record.
"""
from __future__ import annotations

from arena.gauntlet.protocol import NOTIONAL


def match_to_duel_script(m: dict, sc, w_seller, w_buyer) -> dict:
    """m: a match record from the leaderboard artifact (with transcript);
    sc/w_seller/w_buyer: the scenario triple it was played on."""
    names = [name for name, _ in sc.issues]
    up = {n: n.upper() for n in names}
    opts = {name: list(labels) for name, labels in sc.issues}
    dirs = {name: list(d) for (name, _), d in zip(sc.issues, sc.seller_dirs)}

    def pos(name: str, opt) -> float:
        try:
            return float(dirs[name][opts[name].index(opt)])
        except (ValueError, KeyError):
            return 0.5

    model = m.get("model", "model")
    cand_role = m.get("role", "buyer")
    seller_name = model.upper() if cand_role == "seller" else "SNHP ENGINE"
    buyer_name = model.upper() if cand_role == "buyer" else "SNHP ENGINE"

    turns = []
    for entry in m.get("transcript") or []:
        if entry.get("act") != "offer" or not entry.get("pkg"):
            continue
        actor = "prime" if entry["role"] == "seller" else "chal"
        turns.append({"actor": actor,
                      "pos": {up[n]: round(pos(n, entry["pkg"].get(n)), 3)
                              for n in names}})

    # seller wants every rail high, buyer low; intensity carried by the weights
    truth = {
        "wantS": {up[n]: 1.0 for n in names},
        "wantB": {up[n]: 0.0 for n in names},
        "weightS": {up[n]: round(float(w), 3) for n, w in zip(names, w_seller)},
        "weightB": {up[n]: round(float(w), 3) for n, w in zip(names, w_buyer)},
    }

    left = m.get("dollars_left", 0.0)
    if m.get("deal"):
        line = (f"{model} ({cand_role}) settled with the SNHP engine in "
                f"{m.get('rounds', '?')} rounds — ${left:,.0f} of ${NOTIONAL:,} "
                f"left on the table.")
    else:
        line = (f"No deal — {m.get('walked_by', 'someone')} walked. Both sides "
                f"took their outside option; ${left:,.0f} of joint value "
                f"evaporated.")

    # the model's identity caption goes on the MODEL's seat, whichever it holds
    origin = f"{model} · {m.get('condition', 'solo')}"
    origins = ({"seller": origin, "buyer": "the shipped engine"}
               if cand_role == "seller" else
               {"seller": "the shipped engine", "buyer": origin})
    return {
        "issues": [up[n] for n in names],
        "names": {"seller": seller_name, "buyer": buyer_name},
        "origins": origins,
        "subtitle": f"a real recorded match: {seller_name} (seller) vs {buyer_name} (buyer)",
        "truth": truth,
        "turns": turns,
        "reveal": {
            "naive": round(float(m.get("frontier_naive", 0.0)), 3),
            "snhp": round(float(m.get("joint", 0.0)), 3),
            "ceiling": round(float(m.get("frontier_best", 0.0)), 3),
            "label": "this deal",   # the realized joint of THIS match — not SNHP's
            "line": line,
        },
        "meta": {"model": model, "condition": m.get("condition"),
                 "role": cand_role, "scenario_id": m.get("scenario_id"),
                 "deal": m.get("deal"), "capture": m.get("capture"),
                 "dollars_left": left},
    }


def featured_replays(matches: list[dict], scenarios: list) -> list[dict]:
    """Pick the replays worth watching: per model+condition, the best deal
    (least money left) and the most instructive failure (most money left) —
    deals only for the 'best', any outcome for the 'worst'."""
    by_key: dict = {}
    for m in matches:
        by_key.setdefault((m.get("model"), m.get("condition")), []).append(m)
    out = []
    for (_model, _cond), ms in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        deals = [m for m in ms if m.get("deal") and m.get("transcript")]
        played = [m for m in ms if m.get("transcript")]
        if not played:
            continue
        best = min(deals or played, key=lambda m: m.get("dollars_left", 1e9))
        worst = max(played, key=lambda m: m.get("dollars_left", -1))
        picks = [best] if best is worst else [best, worst]
        for m in picks:
            sid = int(m.get("scenario_id", 0))
            if sid >= len(scenarios):
                continue
            sc, w_s, w_b = scenarios[sid]
            out.append(match_to_duel_script(m, sc, w_s, w_b))
    return out

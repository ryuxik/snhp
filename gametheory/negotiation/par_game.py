"""PAR (the daily negotiation game) on the live SNHP engine.

The game's prototype used hardcoded House offers and a fixed `par`. This wires it
to the real math: the House plays the SNHP equilibrium recommender each round
(`plain_terms.negotiate_turn`), and `par` — the number the player is graded
against — is the House's reservation, the limit a perfect player drives it to.

A scenario declares which side the PLAYER takes. If the player SELLS (salary,
freelance) they want a HIGH number and the House is the buyer; if the player BUYS
(rent, a used car) they want a LOW number and the House is the seller. `house_move`
drives the House as the OPPOSITE side, and `score` flips the direction so that
"% of par" always means "how close to the perfect outcome," whichever way is good.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from gametheory.negotiation.plain_terms import negotiate_turn


@dataclass
class Scenario:
    title: str
    player_side: str          # "sell" (you want HIGH) or "buy" (you want LOW)
    your_walk_away: float      # the worst price you'd accept (sell: floor; buy: ceiling)
    your_target: float         # your aspiration (sell: high; buy: low)
    house_reservation: float   # the House's hidden limit — par a perfect player reaches
    rounds: int

    def __post_init__(self):
        if self.player_side not in ("sell", "buy"):
            raise ValueError("player_side must be 'sell' or 'buy'")


def house_move(sc: Scenario, your_offers: list[float], house_offers: list[float],
               rounds_left: int) -> dict:
    """The House's move this round, played by the SNHP equilibrium as the side OPPOSITE
    the player. Player sells -> House buys (opens low, ceiling = house_reservation);
    player buys -> House sells (opens high, floor = house_reservation). Returns the
    recommender dict (action: accept|counter|walk, recommended_price, message, ...)."""
    if sc.player_side == "sell":
        house_side, target = "buy", round(sc.house_reservation * 0.80, 2)   # open cheap
    else:
        house_side, target = "sell", round(sc.house_reservation * 1.20, 2)  # open dear
    return negotiate_turn(
        side=house_side,
        walk_away=sc.house_reservation,
        target=target,
        counterparty_offers=your_offers,        # the other side's asks so far
        my_previous_offers=house_offers,
        rounds_left=rounds_left,
    )


def par(sc: Scenario) -> float:
    """The number a perfect player reaches: against a rational House the optimal timed
    close converges to the House's reservation, so we surface that. In dollars. (A
    closed-form stand-in for the timed-DP search in `mc_prototype`; for these
    single-issue decks the two coincide.)"""
    return round(sc.house_reservation, 2)


def agent_close(sc: Scenario) -> float:
    """Where the SNHP agent would land: 2.5% shy of par — just under the ceiling when
    selling, just over the floor when buying. The bridge to the A2A-commerce upsell."""
    return round(par(sc) * (0.975 if sc.player_side == "sell" else 1.025), 2)


def score(sc: Scenario, deal: Optional[float]) -> dict:
    """Grade a close against par with the direction baked in. Selling: higher is better
    (pct = close/par). Buying: lower is better (pct = par/close). `left_on_table` is
    always the dollars a perfect player would have kept that you didn't (>= 0); on a
    walk it's the whole negotiable surplus."""
    p = par(sc)
    if deal is None:
        return {"par": p, "deal": None, "pct_of_par": 0.0,
                "left_on_table": round(abs(p - sc.your_walk_away), 2)}
    # par is the ceiling: the House never crosses its reservation, so a real close can't
    # beat it. Clamp to the achievable side so pct in (0,100] and left >= 0 for any input.
    if sc.player_side == "sell":
        deal = min(deal, p)                              # can't sell above the ceiling
        pct, left = round(deal / p * 100, 1), round(p - deal, 2)
    else:
        deal = max(deal, p)                              # can't buy below the floor
        pct, left = round(p / deal * 100, 1), round(deal - p, 2)
    return {"par": p, "deal": round(deal, 2), "pct_of_par": pct, "left_on_table": left}


def _player_takes(sc: Scenario, my_ask: float, house_offer: float) -> bool:
    """Would the player accept the House's standing offer? A seller takes an offer at or
    above their ask; a buyer takes one at or below it."""
    return house_offer >= my_ask if sc.player_side == "sell" else house_offer <= my_ask


def play_out(sc: Scenario, your_offers: list[float]) -> dict:
    """Simulate a full game: the player makes `your_offers` round by round; the House
    answers with SNHP each round; report the realised close, par, and % of par. Proves
    the loop runs on the live engine, both directions."""
    house_offers: list[float] = []
    deal = None
    transcript = []
    for r, my_ask in enumerate(your_offers):
        rec = house_move(sc, your_offers[: r + 1], house_offers, max(1, sc.rounds - r))
        transcript.append({"round": r + 1, "your_ask": my_ask, "house": rec["action"],
                           "house_offer": rec.get("recommended_price"),
                           "msg": rec.get("message", "")[:60]})
        if rec["action"] == "accept":
            deal = my_ask                       # House met your ask
            break
        price = rec.get("recommended_price")
        if price is not None:
            house_offers.append(price)
            if _player_takes(sc, my_ask, price):
                deal = price                    # you'd take their standing offer
                break
    return {**score(sc, deal), "transcript": transcript}


if __name__ == "__main__":
    deck = [
        (Scenario("the salary talk", "sell", your_walk_away=90, your_target=130,
                  house_reservation=118, rounds=6), [130, 124, 120, 118], [130, 108, 99]),
        (Scenario("the used car", "buy", your_walk_away=14000, your_target=9000,
                  house_reservation=11200, rounds=6), [9000, 9500, 10000, 11000],
         [9000, 11500, 12500]),
    ]
    for sc, patient, eager in deck:
        edge = "ceiling" if sc.player_side == "sell" else "floor"
        print(f"=== PAR · {sc.title} ({sc.player_side}) — par (the {edge}): ${par(sc)} ===")
        for label, asks in [("patient", patient), ("eager", eager)]:
            res = play_out(sc, asks)
            for t in res["transcript"]:
                print(f"   r{t['round']}: you ask ${t['your_ask']} → house {t['house']}"
                      + (f" ${t['house_offer']}" if t['house_offer'] else ""))
            print(f"   => {label}: closed ${res['deal']} · {res['pct_of_par']}% of par · "
                  f"left ${res['left_on_table']} on the table\n")

"""Quick H2H smoke test: does the Aspiration detector help vs Aspiration
without wrecking other matchups?"""
import time

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from b2b_round_robin import play_matchup, create_issues, create_ufuns  # noqa: E402
from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402

from negmas_agent import SNHPAgent  # noqa: E402
from gametheory.agents.aspiration_detector import SNHPWithAspirationDetector


_ISSUES = create_issues()


def matchup_avg(BuyerCls, SellerCls, n_rounds=100):
    ufun_a, ufun_b = create_ufuns(_ISSUES, 10)
    return play_matchup(SellerCls, BuyerCls, ufun_a, ufun_b, _ISSUES,
                         10, n_rounds, 0.40, seller_pressure=1.0, buyer_pressure=1.0)


print("Quick check at n_rounds=100, both directions averaged:")
print()
for opp_name, opp_cls in [
    ("Aspiration", AspirationNegotiator),
    ("Anchorer", B2B_OPPONENTS["Anchorer"]),
    ("Cialdini", B2B_OPPONENTS["Cialdini"]),
    ("Logroller", B2B_OPPONENTS["Logroller"]),
    ("The Closer", B2B_OPPONENTS["The Closer"]),
]:
    # SNHP_Default as buyer (added 2nd) vs opponent as seller
    t0 = time.time()
    a, b, dr = matchup_avg(SNHPAgent, opp_cls)
    base_b = b
    a, b, dr2 = matchup_avg(SNHPWithAspirationDetector, opp_cls)
    det_b = b
    delta = det_b - base_b
    print(f"  vs {opp_name:<14} buyer-side  base={base_b:.4f}  detector={det_b:.4f}  Δ={delta:+.4f}  ({time.time()-t0:.1f}s)")

    # SNHP as seller (added 1st) vs opponent as buyer
    t0 = time.time()
    a, b, _ = matchup_avg(opp_cls, SNHPAgent)
    base_a = a
    a, b, _ = matchup_avg(opp_cls, SNHPWithAspirationDetector)
    det_a = a
    delta = det_a - base_a
    print(f"  vs {opp_name:<14} seller-side base={base_a:.4f}  detector={det_a:.4f}  Δ={delta:+.4f}")
    print()

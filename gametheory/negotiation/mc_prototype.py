"""Does spending compute (Monte-Carlo rollouts) buy a better negotiation than a
closed-form policy? A controlled, honest experiment — not a strawman.

Setting: single-issue price negotiation. We're the seller (reservation 0). The
buyer has a private max willingness-to-pay ``b`` we never observe, drawn from a
known prior. The buyer is a conceder: at round ``t`` they accept any price
``p <= c(t) * b``, where ``c(t)`` rises from ``c0`` to 1 over the horizon (they
get more willing as the deadline nears). Every rejection is information — it
proves ``b < p / c(t)`` — so the belief collapses to a single upper bound ``U``
on ``b``. That 1-D belief is what makes the *optimal* policy computable by
backward induction, giving us an unimpeachable ceiling to measure against.

Three seller policies, same buyers, same seeds:
  * OPTIMAL  — dynamic-programming policy over (round, belief). The best any
               policy can do in this environment. The ceiling.
  * MYOPIC   — closed-form greedy: each round pick p to maximise immediate
               expected revenue  delta^t * p * P(accept). No lookahead. This is
               what a compute-free policy does.
  * MC       — the compute approach: for each candidate price, Monte-Carlo roll
               the rest of the negotiation out (under the myopic base policy)
               against sampled buyers, pick the best expected discounted payoff.

The question isn't "does MC beat a weak baseline" — it's "how much of the
optimal-minus-greedy gap does compute recover, and what happens when the
opponent model is wrong."
"""
import numpy as np

# ---- environment ---------------------------------------------------------
B_LO, B_HI = 0.30, 0.90      # prior support for the buyer's private reservation b
T = 8                        # rounds (seller posts a price each round)
DELTA = 0.90                 # per-round discount — waiting for a higher price costs you
C0 = 0.40                    # buyer accepts p <= c(t)*b; c rises from C0 ...
E_CONCEDE = 2.5              # ... to 1.0 with this Boulware exponent

PRICES = np.linspace(0.02, 1.0, 44)          # candidate prices the seller may post
Us = np.linspace(B_LO, B_HI, 140)            # belief grid: upper bound on b


def concession(t, e=E_CONCEDE):
    """c(t) in [C0, 1]: fraction of their reservation the buyer will pay at round t."""
    return C0 + (1.0 - C0) * (t / (T - 1)) ** (1.0 / e)


def p_accept_vec(P, t, U, e=E_CONCEDE):
    """P(accept price P at round t | b ~ Uniform[B_LO, U]) for a price array P."""
    P = np.asarray(P, float)
    if U <= B_LO:
        return np.zeros_like(P)
    thr = P / concession(t, e)
    return np.clip((U - np.clip(thr, B_LO, U)) / (U - B_LO), 0.0, 1.0)


# ---- policy tables (built once) -----------------------------------------
def build_tables(e=E_CONCEDE):
    """Return (M, A, v0): myopic price table M[t,ui], optimal price table A[t,ui]
    over the U grid, and the optimal value of the initial belief. Both policies
    are always built with the *assumed* model e (= E_CONCEDE)."""
    M = np.zeros((T, len(Us)))
    A = np.zeros((T, len(Us)))
    V = np.zeros((T + 1, len(Us)))
    for t in range(T - 1, -1, -1):
        c = concession(t, e)
        for ui, U in enumerate(Us):
            pa = p_accept_vec(PRICES, t, U, e)
            # myopic: maximise immediate expected revenue
            M[t, ui] = PRICES[int(np.argmax(DELTA ** t * PRICES * pa))]
            # optimal: immediate reward + discounted continuation after a rejection
            Un = np.minimum(U, PRICES / c)
            v_cont = 0.0 if t == T - 1 else np.interp(Un, Us, V[t + 1])
            vals = pa * (DELTA ** t * PRICES) + (1 - pa) * v_cont
            k = int(np.argmax(vals))
            A[t, ui], V[t, ui] = PRICES[k], vals[k]
    return M, A, float(np.interp(B_HI, Us, V[0]))


def mc_price(t, U, rng, M, n_samples=50):
    """The compute approach: Monte-Carlo rollout under the myopic base policy M.
    Vectorised over (candidate price, sampled buyer)."""
    if U <= B_LO:
        return float(np.interp(U, Us, M[t]))
    bs = rng.uniform(B_LO, U, size=n_samples)
    Pcol, BS = PRICES[:, None], bs[None, :]          # (nP,1), (1,n)
    payoff = np.zeros((len(PRICES), n_samples))
    alive = np.ones_like(payoff, bool)
    Uarr = np.full_like(payoff, U)
    c = concession(t)
    acc = Pcol <= c * BS                              # buyer accepts the first move?
    payoff = np.where(acc, DELTA ** t * Pcol, payoff)
    alive &= ~acc
    Uarr = np.minimum(Uarr, Pcol / c)
    for tt in range(t + 1, T):                        # then play the myopic base policy
        if not alive.any():
            break
        cc = concession(tt)
        ptt = np.interp(Uarr.ravel(), Us, M[tt]).reshape(Uarr.shape)
        acc = alive & (ptt <= cc * BS)
        payoff = np.where(acc, DELTA ** tt * ptt, payoff)
        alive &= ~acc
        Uarr = np.minimum(Uarr, ptt / cc)
    return float(PRICES[int(np.argmax(payoff.mean(axis=1)))])


# ---- evaluation ----------------------------------------------------------
def run_episode(policy, b, e_true=E_CONCEDE):
    """Simulate one negotiation against a true buyer b. policy(t, U) -> price."""
    U = B_HI
    for t in range(T):
        p = policy(t, U)
        if p <= concession(t, e_true) * b:               # buyer's TRUE behaviour
            return DELTA ** t * p
        U = min(U, p / concession(t, E_CONCEDE))          # belief uses the assumed model
    return 0.0


def _ci(d):
    d = np.asarray(d)
    se = d.std(ddof=1) / np.sqrt(len(d))
    return d.mean(), d.mean() - 1.96 * se, d.mean() + 1.96 * se


def experiment(n=1200, seed=7, e_true=E_CONCEDE, label=""):
    rng = np.random.default_rng(seed)
    buyers = rng.uniform(B_LO, B_HI, size=n)
    M, A, v0 = build_tables(E_CONCEDE)                    # policies always assume E_CONCEDE
    mc_rng = np.random.default_rng(seed + 1)

    pol_opt = lambda t, U: float(np.interp(U, Us, A[t]))
    pol_myo = lambda t, U: float(np.interp(U, Us, M[t]))
    pol_mc = lambda t, U: mc_price(t, U, mc_rng, M)
    u_opt = np.array([run_episode(pol_opt, b, e_true) for b in buyers])
    u_myo = np.array([run_episode(pol_myo, b, e_true) for b in buyers])
    u_mc = np.array([run_episode(pol_mc, b, e_true) for b in buyers])

    print(f"\n=== {label} (n={n}, e_true={e_true}, policies assume e={E_CONCEDE}) ===")
    print(f"  mean seller payoff:   OPTIMAL {u_opt.mean():.4f}   MYOPIC {u_myo.mean():.4f}   MC {u_mc.mean():.4f}")
    gap = u_opt.mean() - u_myo.mean()
    if abs(gap) > 1e-9:
        print(f"  optimal - myopic gap: {gap:+.4f}   |   MC recovers {(u_mc.mean()-u_myo.mean())/gap*100:5.1f}% of it")
    m, lo, hi = _ci(u_mc - u_myo)
    wins = (u_mc > u_myo + 1e-9).mean(); losses = (u_mc < u_myo - 1e-9).mean()
    print(f"  MC - MYOPIC:          {m:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]   win {wins*100:.0f}% / lose {losses*100:.0f}%")
    over = u_mc.mean() - u_opt.mean()
    print(f"  sanity (MC <= OPTIMAL): MC - OPTIMAL = {over:+.4f}  {'OK' if over <= 2e-3 else 'BUG: beat the ceiling'}")
    return u_opt, u_myo, u_mc


if __name__ == "__main__":
    experiment(label="correct opponent model")
    # wrong model: the buyer concedes almost linearly (e_true=1.2) while the policies
    # still assume Boulware (e=2.5). Does MC's edge survive a mis-specified opponent?
    experiment(e_true=1.2, label="WRONG opponent model (buyer concedes differently)")

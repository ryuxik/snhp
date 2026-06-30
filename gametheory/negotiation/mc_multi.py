"""Does compute (Monte-Carlo rollouts) buy a better MULTI-ISSUE negotiation?

The single-issue test (mc_prototype.py) had a 1-D belief (an upper bound on the
buyer's reservation), so we could compute the DP-optimal ceiling. Multi-issue is
the product's real domain — logrolling across linked terms — and there the
unknown is the opponent's *priority weights* over K issues, a point on the
(K-1)-simplex. That belief is high-dimensional, so no clean DP ceiling. Instead:

  * particles over the opponent's weights, filtered by what their rejections
    reveal (each rejection is a linear half-space constraint on their weights);
  * CLAIRVOYANT bound as the ceiling — the best a seller could do if it KNEW the
    opponent's weights and could time one offer perfectly. A valid (loose) upper
    bound on any belief-based policy.

Three seller policies, same opponents, same seeds:
  * CLAIRVOYANT — knows the weights; picks the best timed package. Ceiling.
  * MYOPIC      — greedy logroller: each round offer the package maximising
                  immediate expected value  V_me(P) * P(accept). Does Pareto-style
                  logrolling already, but no lookahead. The closed-form baseline.
  * MC          — for each candidate package, Monte-Carlo roll the rest of the
                  negotiation out (myopic base policy) against weights sampled
                  from the belief; offer the best expected discounted payoff.

We're the proposer each round. The opponent is a conceder: they accept our
package iff their utility of it clears a threshold thr(t) that declines from
demanding to their BATNA over the horizon. We never observe their weights.
"""
import numpy as np

K = 4            # issues
M = 3            # options per issue
T = 8            # rounds
DELTA = 0.90     # per-round discount
THR_MAX, THR_MIN = 0.85, 0.35   # their acceptance threshold declines from -> to (their BATNA)
E_CONCEDE = 2.5  # Boulware: hold the high threshold, concede late
N_PART = 400     # belief particles over opponent weights
N_SAMP = 60      # rollout samples per MC decision

# all M^K packages as an index matrix [n_pkg, K]
_PKG = np.array(np.meshgrid(*[range(M)] * K, indexing="ij")).reshape(K, -1).T
N_PKG = _PKG.shape[0]


def thr(t, e=E_CONCEDE):
    """Opponent's required utility at round t: THR_MAX -> THR_MIN as t -> T-1."""
    return THR_MIN + (THR_MAX - THR_MIN) * ((T - 1 - t) / (T - 1)) ** (1.0 / e)


def _make_opponent(rng, alpha=1.0):
    """Random instance: my/their per-issue-option utilities, my known weights,
    their hidden weights (drawn from Dirichlet(alpha) — alpha<1 = opponents who
    care intensely about one issue, mismatching the belief's uniform prior)."""
    u_me = rng.random((K, M))
    u_them = rng.random((K, M))
    wm = rng.dirichlet(np.ones(K))              # my weights (known to me)
    w_true = rng.dirichlet(alpha * np.ones(K))  # their weights (hidden)
    # per-package utilities
    Ume = np.array([sum(wm[k] * u_me[k, _PKG[p, k]] for k in range(K)) for p in range(N_PKG)])
    # their per-package per-issue contribution u_them[k, option] -> [n_pkg, K]
    Uthem_contrib = np.array([[u_them[k, _PKG[p, k]] for k in range(K)] for p in range(N_PKG)])
    Vthem_true = Uthem_contrib @ w_true     # [n_pkg]
    return Ume, Uthem_contrib, Vthem_true


def _myopic_choice(t, Ume, Vthem_belief_surv):
    """Greedy logroller: argmax over packages of V_me * P(accept at thr(t))."""
    pa = (Vthem_belief_surv >= thr(t)).mean(axis=1)      # P(accept) per package
    return int(np.argmax(Ume * pa))


def run_episode(policy, Ume, Vthem_all, Vthem_true, e_true=E_CONCEDE):
    """Simulate one negotiation. policy(t, surviving_mask) -> package index. The
    opponent accepts per their TRUE concession rate e_true; the seller's belief
    update uses the ASSUMED rate (E_CONCEDE) — so e_true != E_CONCEDE is a
    misspecified model."""
    surviving = np.ones(Vthem_all.shape[1], bool)
    for t in range(T):
        p = policy(t, surviving)
        if Vthem_true[p] >= thr(t, e_true):               # opponent accepts (true model)
            return DELTA ** t * Ume[p]
        surviving = surviving & (Vthem_all[p] < thr(t))   # rejection constraint (assumed model)
        if not surviving.any():
            surviving = np.ones_like(surviving)           # fallback (particles exhausted)
    return 0.0


def mc_choice(t, surviving, Ume, Vthem_all, rng):
    """The compute approach: rollout each candidate package under the myopic base
    policy against weights sampled from the current belief. Fully vectorised over
    (candidate package, sampled opponent)."""
    surv = np.where(surviving)[0]
    samp = rng.choice(surv, size=min(N_SAMP, surv.size), replace=True)
    Vs = Vthem_all[:, samp]                                # [n_pkg, n_samp]
    Vbel = Vthem_all[:, surviving]                         # belief for the base policy
    p_myo = {tt: _myopic_choice(tt, Ume, Vbel) for tt in range(t, T)}   # base policy (belief fixed)

    payoff = np.zeros((N_PKG, samp.size))
    done = Vs >= thr(t)                                    # candidate accepted on the first move?
    payoff = np.where(done, DELTA ** t * Ume[:, None], payoff)
    alive = ~done
    for tt in range(t + 1, T):                            # then everyone follows the myopic base
        if not alive.any():
            break
        pm = p_myo[tt]
        acc = alive & (Vs[pm] >= thr(tt))[None, :]
        payoff = np.where(acc, DELTA ** tt * Ume[pm], payoff)
        alive = alive & ~acc
    return int(np.argmax(payoff.mean(axis=1)))


def clairvoyant(Ume, Vthem_true, e_true=E_CONCEDE):
    """Ceiling: knowing their weights, the best single perfectly-timed package."""
    best = 0.0
    for t in range(T):
        ok = Vthem_true >= thr(t, e_true)
        if ok.any():
            best = max(best, DELTA ** t * Ume[ok].max())
    return best


def experiment(n=600, seed=11, alpha=1.0, e_true=E_CONCEDE, label="correct opponent model"):
    rng = np.random.default_rng(seed)
    mc_rng = np.random.default_rng(seed + 1)
    W = rng.dirichlet(np.ones(K), size=N_PART).T          # belief particles [K, N_PART], uniform prior

    u_cla, u_myo, u_mc = [], [], []
    for _ in range(n):
        Ume, Uthem_contrib, Vthem_true = _make_opponent(rng, alpha)
        Vthem_all = Uthem_contrib @ W                     # [n_pkg, N_PART] per-particle values
        u_cla.append(clairvoyant(Ume, Vthem_true, e_true))
        u_myo.append(run_episode(
            lambda t, s: _myopic_choice(t, Ume, Vthem_all[:, s]), Ume, Vthem_all, Vthem_true, e_true))
        u_mc.append(run_episode(
            lambda t, s: mc_choice(t, s, Ume, Vthem_all, mc_rng), Ume, Vthem_all, Vthem_true, e_true))
    cla, myo, mc = map(np.array, (u_cla, u_myo, u_mc))

    print(f"\n=== multi-issue: {label} ({K}x{M}={N_PKG} packages, n={n}, alpha={alpha}, e_true={e_true}) ===")
    print(f"  mean seller payoff:   CLAIRVOYANT {cla.mean():.4f}   MYOPIC {myo.mean():.4f}   MC {mc.mean():.4f}")
    gap = cla.mean() - myo.mean()
    if abs(gap) > 1e-9:
        print(f"  clairvoyant - myopic gap: {gap:+.4f}   |   MC recovers {(mc.mean()-myo.mean())/gap*100:5.1f}% of it")
    d = mc - myo
    se = d.std(ddof=1) / np.sqrt(len(d))
    wins = (d > 1e-9).mean(); losses = (d < -1e-9).mean()
    print(f"  MC - MYOPIC:          {d.mean():+.4f}  95% CI [{d.mean()-1.96*se:+.4f}, {d.mean()+1.96*se:+.4f}]"
          f"   win {wins*100:.0f}% / lose {losses*100:.0f}%")
    over = (mc > cla + 1e-9).mean()
    print(f"  sanity (MC <= CLAIRVOYANT): violated on {over*100:.1f}% of episodes  {'OK' if over < 0.01 else 'CHECK'}")
    return cla, myo, mc


if __name__ == "__main__":
    experiment(label="correct opponent model")
    # prior misspecified: opponents care intensely about one issue (Dirichlet(0.3)),
    # but the belief still assumes a uniform prior over weights.
    experiment(alpha=0.3, label="WRONG prior (opponents are extreme; belief stays uniform)")
    # concession-rate misspecified: they concede almost linearly (e_true=1.3) while
    # the seller's belief update assumes Boulware (e=2.5).
    experiment(e_true=1.3, label="WRONG concession rate (e_true=1.3 vs assumed 2.5)")

import numpy as np
import itertools

def generate_contract_space(variable_options):
    """
    Generates the discrete state space for all possible contracts.
    variable_options: a list of lists, where each sublist contains the possible values [0 to 1] for that variable.
    Returns: A numpy matrix of shape (total_permutations, total_variables)
    """
    permutations = list(itertools.product(*variable_options))
    return np.array(permutations, dtype=float)

def filter_pareto_frontier(contracts_matrix, utilities_a, utilities_b):
    """Return the indices of the (strictly) non-dominated contracts.

    O(n log n) 2D skyline (sort by u_a desc, sweep tracking the best u_b among
    strictly-higher-u_a contracts) — the same result as a pairwise O(n^2) scan,
    but ~n/log n faster (≈200x at n≈2400), which is what makes the multi-issue
    Pareto step cheap enough to evaluate thousands of times (e.g. Monte-Carlo
    rollouts). Domination is STRICT and ties are preserved exactly: a contract
    survives unless another is >= on both utilities and strictly > on one.
    """
    ua = np.asarray(utilities_a, dtype=float)
    ub = np.asarray(utilities_b, dtype=float)
    valid = np.where((ua > -np.inf) & (ub > -np.inf))[0]
    if valid.size == 0:
        return np.array([], dtype=int)

    a = ua[valid]
    b = ub[valid]
    order = np.lexsort((-b, -a))          # u_a descending, ties broken by u_b descending
    a_s, b_s = a[order], b[order]
    n = a_s.size
    keep = np.zeros(n, dtype=bool)

    best_b_above = -np.inf                 # max u_b among strictly-higher-u_a contracts
    i = 0
    while i < n:
        j = i
        while j < n and a_s[j] == a_s[i]:  # the equal-u_a group [i, j)
            j += 1
        group_max_b = b_s[i]               # sorted u_b desc -> first element is the group max
        survive = group_max_b > best_b_above
        # Within a group only the max-u_b contracts beat their same-u_a peers; the
        # group survives only if its max u_b beats every strictly-higher-u_a contract.
        keep[i:j] = survive & (b_s[i:j] == group_max_b)
        if survive:
            best_b_above = group_max_b
        i = j

    return valid[order[keep]]

def find_nash_bargaining_solution(
    pareto_indices, utilities_a, utilities_b, batna_a, batna_b,
    batna_b_inferred: bool = False,
):
    """
    Finds the index of the contract within the Pareto set that maximizes the
    Nash product (u_a - d_a)(u_b - d_b).

    NOTE on Nash axioms (Nash, 1950): the classical Nash bargaining solution
    requires BOTH disagreement points (BATNAs) to be common knowledge. If
    `batna_b_inferred=True`, the caller is using an estimated opponent BATNA
    from a Bayesian opponent model; the returned solution is then a
    *Bayesian-Nash* heuristic, NOT the classical Nash solution. It violates
    Independence of Irrelevant Alternatives because the result depends on the
    inference path, not just the Pareto frontier. We still return the
    Nash-product-maximizing point because it's a defensible heuristic, but
    callers should label outputs accordingly (do not advertise as "Nash").
    """
    if len(pareto_indices) == 0:
        return None

    best_product = -np.inf
    best_index = None

    for idx in pareto_indices:
        surplus_a = utilities_a[idx] - batna_a
        surplus_b = utilities_b[idx] - batna_b

        # A valid Nash bargain requires surplus > 0 for both parties
        if surplus_a <= 0 or surplus_b <= 0:
            continue

        product = surplus_a * surplus_b

        if product > best_product:
            best_product = product
            best_index = idx

    return best_index

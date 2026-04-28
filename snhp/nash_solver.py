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
    """
    Jeff Dean optimization: Vectorized logic for Pareto extraction.
    filters out contracts that are strictly dominated by others.
    Returns: A 1D numpy array of the indices of the Pareto optimal contracts.
    """
    valid_mask = (utilities_a > -np.inf) & (utilities_b > -np.inf)
    if not np.any(valid_mask):
        return np.array([], dtype=int)
        
    valid_indices = np.where(valid_mask)[0]
    pareto_indices = []
    
    for i in valid_indices:
        u_a_i = utilities_a[i]
        u_b_i = utilities_b[i]
        
        # Determine if contract i is dominated
        dominated = False
        for j in valid_indices:
            if i == j:
                continue
            u_a_j = utilities_a[j]
            u_b_j = utilities_b[j]
            
            # Dominance condition: j is better or equal on both, and strictly better on at least one
            if (u_a_j >= u_a_i and u_b_j >= u_b_i) and (u_a_j > u_a_i or u_b_j > u_b_i):
                dominated = True
                break
                
        if not dominated:
            pareto_indices.append(i)
            
    return np.array(pareto_indices, dtype=int)

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

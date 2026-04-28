import numpy as np

class Engram:
    def __init__(self, raw_weights, batna):
        """
        Initializes the Utility Preference Vector.
        raw_weights: list or array of numerical preferences for each contract variable.
        batna: scalar representing the Absolute Reservation Value. Any contract yielding 
               a utility below this value is rejected (-inf).
        """
        raw_weights = np.array(raw_weights, dtype=float)
        if np.any(raw_weights < 0):
            raise ValueError("Raw weights cannot be negative.")
            
        sum_weights = np.sum(raw_weights)
        if sum_weights <= 0:
            # Fallback to uniform distribution if zeroed out
            self.weights = np.ones(len(raw_weights)) / len(raw_weights)
        else:
            # John von Neumann Constraint 1: Normalization (Sum to 1.0)
            self.weights = raw_weights / sum_weights
            
        self.batna = batna

    def evaluate(self, contract_features):
        """
        Evaluates a single contract.
        contract_features: Array of features scaled between [0, 1] mapped to the weights.
        Returns the utility, or -inf if the utility is below BATNA.
        """
        contract_features = np.array(contract_features, dtype=float)
        utility = np.dot(self.weights, contract_features)
        
        # Constraint 2: BATNA Enforcement
        if utility < self.batna:
            return -np.inf
        return utility

    def evaluate_bulk(self, contracts_matrix):
        """
        Jeff Dean Optimization: Vectorized bulk evaluation for millions of contracts.
        contracts_matrix: NumPy array of shape (N_contracts, N_variables).
        Returns: 1D array of utilities of length N_contracts.
        """
        # Fast C-level dot product
        utilities = np.dot(contracts_matrix, self.weights)
        
        # Vectorized BATNA gating
        utilities = np.where(utilities < self.batna, -np.inf, utilities)
        return utilities

import numpy as np

class BayesianParticleFilter:
    def __init__(self, num_variables, num_particles=50000, historical_prior=None, uncertainty=0.15):
        """
        Initializes N=50,000 particles, each representing a "virtual opponent" with a different Utility Preference Vector.
        """
        self.num_variables = num_variables
        self.num_particles = num_particles
        
        if historical_prior is None:
            # Cold Start: Random uninformative prior
            raw_weights = np.random.rand(num_particles, num_variables)
        else:
            # Warm Start: Informative Gaussian prior (Seeding Context)
            prior_array = np.array(historical_prior)
            raw_weights = np.random.normal(loc=prior_array, scale=uncertainty, size=(num_particles, num_variables))
            raw_weights = np.clip(raw_weights, 0.001, 1.0) # Bind mathematically
            
        # Normalize weights so they sum to 1.0 along the variable axis
        sum_weights = np.sum(raw_weights, axis=1, keepdims=True)
        self.particles = raw_weights / sum_weights
        
        # Uniform initial probabilities (beliefs) - Prior
        self.probabilities = np.ones(num_particles) / num_particles
        
    def update_beliefs(self, anchor_contract_features, all_contracts_matrix):
        """
        Bayesian Update (Likelihood calculation). 
        Given that the opponent proposed `anchor_contract_features`, which particles (utility weightings)
        would rationally make that offer? We calculate the likelihood using a continuous Boltzmann distribution.
        """
        # Utility of the anchor for all 50,000 particles at once
        anchor_utilities = np.dot(self.particles, anchor_contract_features)
        
        # Max utility for each particle across all possible contracts
        all_utilities = np.dot(self.particles, all_contracts_matrix.T) 
        max_utilities = np.max(all_utilities, axis=1)
        
        # Likelihood is higher if the proposed anchor utility is very close to the particle's maximum possible utility
        # Temperature controls how "rational" we assume the opponent is. Lower = more rational/strict.
        temperature = 0.1 
        likelihoods = np.exp((anchor_utilities - max_utilities) / temperature)
        
        # Bayes Rule: Posterior = Prior * Likelihood
        self.probabilities = self.probabilities * likelihoods
        
        # Normalize
        prob_sum = np.sum(self.probabilities)
        if prob_sum > 0:
            self.probabilities /= prob_sum
        else:
            # Fallback for numerical underflow
            self.probabilities = np.ones(self.num_particles) / self.num_particles
            
    def get_inferred_weights(self):
        """ 
        Returns the expected (weighted average) utility vector of the opponent based on the current posterior distribution.
        """
        return np.average(self.particles, axis=0, weights=self.probabilities)

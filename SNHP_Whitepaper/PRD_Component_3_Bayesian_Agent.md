# PRD: Component 3 - The Bayesian Shadow Agent

## Steve Jobs: The Vision (The "One More Thing")
This is the moment the world changes. Because we aren't waiting for the other side to adopt our protocol. The user operates SNHP as their own private Shadow Agent. 

Imagine you are negotiating via email. You drag their message into SNHP. The agent reads it, thinks five moves ahead like Deep Blue, and hands you the perfect counter-offer. It anticipates what the opponent wants before the opponent even realizes it. It’s a reality distortion field in a box. You will seem like the most brilliant negotiator on earth.

## Product Requirements
*   **The User Flow:** A terminal or clean Chat UI where the user inputs the opponent's latest text offer (e.g., "I need this in 1 week for $15k").
*   **The Brain:** The engine must infer what the opponent actually values based on their anchoring attempt.
*   **The Action:** It must output a counter-offer that pushes the opponent to their absolute limit without causing a deal collapse.

---

## John von Neumann: The Technical Review
*“Steve, you cannot bend reality, but you can compute probability. The agent cannot 'know' what the opponent wants purely from one email, but it can run a Bayesian particle filter to guess with increasing accuracy.”*

**Von Neumann's Strict Constraints:**
1.  **The Uniform Prior:** We begin by assuming the opponent could be anyone. We use Monte Carlo simulation to generate 10,000 "virtual opponents," each with a random, valid Utility Vector.
2.  **Bayesian Culling:** When the opponent asks for a "1-week deadline," that serves as our first signal. Our script must evaluate those 10,000 virtual opponents. Any opponent who does not heavily weight "Time" would not have anchored on 1 week. Therefore, we cull or down-weight those particles. The probability distribution shifts.
3.  **The Counter-Offer Generation:** Against the surviving, updated probability distribution, we run Minimax. We select the counter-offer that performs best *on average* across the remaining plausible opponent profiles. 

## MVP Action Plan
1. Build an interactive Python CLI loop. 
2. Step 1: User types an anchor.
3. Step 2: The Agent runs 10,000 fast Monte Carlo particle filters, updates beliefs, and prints: "Opponent is 78% likely to value Time over Price. Recommend countering with: $18k and 2 weeks."
4. Step 3: Test this live by acting as the opponent and seeing if the Bayesian culling correctly identifies your secret strategy after 3 rounds.

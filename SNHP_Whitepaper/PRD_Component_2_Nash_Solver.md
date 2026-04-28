# PRD: Component 2 - The Monte Carlo Nash Solver

## Steve Jobs: The Vision (The "Engine Block")
When you open a MacBook, it just wakes up. That's the feeling we need here. This is the engine block of the SNHP. Two profiles go in, and the absolute perfect deal structure comes out. It shouldn't load. It shouldn't buffer with a spinning beachball. It needs to calculate every single outcome in the universe before the user even takes their finger off the enter key. 

This computationally perfect "Golden Box" needs to feel like pure magic. It has to demonstrate that human negotiation over three weeks is an obsolete, barbaric practice.

## Product Requirements
*   **Inputs:** Two normalized Engrams (Utility Vectors) from Component 1.
*   **The Processor:** A standalone Python script that calculates every permutation of the 3-variable contract space.
*   **Output:** Return the exact Pareto-optimal midpoint instantly.

---

## John von Neumann: The Technical Review
*“Do not call mathematics 'magic', Steve. Magic is for children. This is permutation logic. Humans struggle with negotiation because the search space is large; a computer does not care. But your demand for 'instantaneous' requires algebraic efficiency.”*

**Von Neumann's Strict Constraints:**
1.  **Grid Search Feasibility:** For a 3-variable contract (e.g., 10 price points, 4 timeframes, 5 revision counts), the state space is $10 * 4 * 5 = 200$ discrete contracts. This is trivial. We will perform an exhaustive brute-force grid search. No deep learning required.
2.  **Mapping the Frontier:** The script must iterate through all 200 states, calculate $U_{buyer}$ and $U_{seller}$ for each, and discard any point that is strictly dominated by another point. What remains is the Pareto Frontier.
3.  **The Nash Bargaining Solution (NBS):** We do not give the user 'options.' We give them mathematical truth. The script must iterate over the Pareto Frontier and select the single contract that maximizes the Nash product: $(U_b - BATNA_b) * (U_s - BATNA_s)$. 

## MVP Action Plan
1. Write a 100-line Python script utilizing `numpy`.
2. Input two hardcoded JSON utility vectors.
3. Assert that script evaluates the 200 states and outputs the NBS in $O(N)$ time (effectively < 10 milliseconds).

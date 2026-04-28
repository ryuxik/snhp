# PRD 4: The Mathematical Core (The Moat)

## 1. The Strategy (Naval Ravikant / Leverage)
Standard LLM wrappers are a commodity and their margins will go to zero. The true moat of this business is the proprietary, specialized Python math (Bayesian distributions, Historical Leverage matrices, Rubinstein gradients). Because it is math, it has zero marginal cost of reproduction and infinite leverage.

## 2. The Jobsian Vision (The Contextual Glass Box)
> *"The inside of the machine is infinitely complex—equations, matrices, probabilities. The outside must present absolute transparency to the enterprise user. We don't hide the dials; we illuminate them. Show the VP of Sales exactly what inputs the model determined (Urgency, Pipeline) and let them fine-tune those levers before execution. Once the context is set, the math engine flawlessly generates the absolute truth. And because we prove the delta, we earn a massive cut of the upside."*

## 3. Product Requirements

### 3.1 The "Glass Box" Contextual Tuning
Instead of strict Zero-Tuning, SNHP implements Glass Box control for enterprise users.
- The NLP layer extracts human-readable constraints into raw numerical hyperparameters (e.g. `urgency_score`, `timeline_days`).
- SNHP exposes these extracted parameters back to the Enterprise CRM or UI *before* evaluation, allowing Sales Leaders to easily override or adjust contextual metrics to fit complex, real-world edge cases.

### 3.2 Latency Optimization
Because SNHP is intended to be injected directly into prompt chains by LLM agents (MCP), it cannot be a bottleneck.
- **Sub-500ms Math Calculations**: The `game_theory.py` logic must be heavily optimized using Numba or compiled bindings where necessary to ensure the math evaluates instantly.
- The only acceptable latency is the unavoidable NLP LLM extraction phase, which pipelines the initial context.

### 3.3 The Monetization Model (Solving the Oracle Problem)
We solve the Subjective Utility oracle problem through a strict **Delta Capture Toll**.
- The "Value" is objectively defined as the mathematical difference between the Client's Opening Anchor and the Final Accepted Contract value.
- **Toll**: We charge a 5% to 10% fee on ONLY the generated surplus delta. This creates perfect incentive alignment with enterprise sales teams—if the agent doesn't close for a higher margin than the opening bid, we make nothing. 
- This mathematically proves our ROI to VPs of Sales and guarantees perpetual retention.

## 4. Key Success Metric
**API Uptime & Math P99 Latency**: The math engine never hallucinates, and it never crashes. We must guarantee 99.99% uptime for the `mcp_server.py` calculation layer to remain a trusted infrastructure component.

# PRD 2: The Trust Simulator (Developer ROI)

## 1. The Strategy (Patrick Collison / Stripe)
Financial and negotiation infrastructure requires profound trust. Developers will not hand over pricing authority to a black-box AI tool unless they inherently trust the engine. Stripe won by allowing developers to test dummy credit cards; SNHP must allow developers to test dummy negotiations.

## 2. The Jobsian Vision (Show, Don't Tell)
> *"People don't buy math; they buy the result of the math. Do NOT list bullet points about Game Theory on the landing page. Give them a playground. They paste an old email that lost them money, hit 'Compute', and watch the Rubinstein lattice resolve visually on the screen in real-time. It needs to feel like pure magic. They should instantly see how much money our engine would have saved them."*

## 3. Product Requirements

### 3.1 The Glassmorphic Playground (Web UI)
The landing page above the fold contains zero marketing jargon. It contains:
- Two elegant text boxes: "Client's Email" and "Your Goals".
- A massive, beautiful "Run SNHP Simulation" button.

### 3.2 Real-Time Visual Mathematics
When the user clicks the button, we do not just instantly spit out an answer. We simulate the computation visually to build trust:
1. **Extraction State**: Subtly flash the extracted variables (Leverage, Market CV, Patience Delta).
2. **The Lattice**: Show a quick visual graph of the Myerson inverse hazard rate plotting the exact opening bid.
3. **The Result**: Display the final output: *"SNHP mathematically proves you should have asked for $2,400, not $1,800. Here is your concession ladder."*

### 3.3 Test-Mode API Keys
Every developer who signs up instantly receives a `sk_test_...` key. Test keys do not hit the live LLM billable layers but return pre-computed deterministic mathematical outputs for standard scenarios. They can start coding against our infrastructure without a credit card.

## 4. Key Success Metric
**Playground Conversion Rate**: The percentage of landing page visitors who run a simulation and immediately click "Get Developer Key".

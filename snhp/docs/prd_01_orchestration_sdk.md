# PRD 1: The Orchestration SDK (The 3-Line API)

## 1. The Strategy (Harrison Chase / LangChain)
AI Agents are currently orchestrating across dozens of tools. To become the dominant standard for negotiation, SNHP must be the absolute easiest tool to plug into frameworks like LangChain, AutoGen, and the MCP ecosystem.

## 2. The Jobsian Vision (UX & Friction)
> *"If a developer has to read a 10-page manual to understand our API, we've failed. It must just work. The complexity of the Bayesian math and the Myerson inverse hazard rates must be entirely invisible. We give them exactly one elegant object. 3 lines of code. No configuration."*

## 3. Product Requirements

### 3.1 The "Magic" Endpoint
The entire SNHP mathematical engine must collapse into a single endpoint:
`POST /v1/negotiate`

**Required Inputs (The bare minimum):**
- `opponent_message`: The raw text of the incoming email/offer.
- `agent_constraints`: A simple JSON object of absolute minimums and targets.

### 3.2 The SDK Wrapper
We will provide native SDKs (`pip install snhp-python`, `npm install @snhp/node`).
The implementation for an AI company must look exactly like this:

```python
import snhp

# The Magic Moment
response = snhp.negotiate(
    message=client_email,
    constraints={"min_rate": 50, "ideal_rate": 100}
)

print(response.optimal_anchor)
print(response.concession_ladder)
```

### 3.3 MCP "Drop-in" Support
We will officially maintain an MCP integration. An AI company building an agent in Cursor or Claude should be able to add SNHP to their `mcp.json` config file and immediately give their agent mathematical negotiation powers without writing any native code.

## 4. Key Success Metric
**Time-to-First-Nash (TTFN)**: The time it takes a new developer to sign up, get an API key, and successfully compute their first Nash Equilibrium. Target: **< 90 seconds.**

# Customer Complaint Resolution — MuleSoft Agent Fabric

Author: Md Helal Uddin | TDX 2026, San Francisco, April 16, 2026
Session: Connect & Govern MCP and A2A with MuleSoft Agent Fabric (Session 1557)
Status: All 5 exercises completed. End-to-end refund flow verified in Anypoint Monitoring.

---

## What problem does this solve?

Before multi-agent protocols existed, connecting an AI model to enterprise systems meant writing custom code for every integration. If you wanted an AI to check inventory, verify a customer, and process a refund, you had to build all of that yourself and maintain it forever. Every company built the same plumbing, differently.

MCP (Model Context Protocol) and A2A (Agent-to-Agent) change that by standardising how AI agents discover and call tools, and how they communicate with each other. This project implements a complete agent network using both protocols on MuleSoft's Anypoint Platform — no custom glue code, fully governed, fully observable.

A customer types:
> "I am customer CUST002. I would like a refund for order ORD003. The product was damaged."

The system automatically verifies the customer, creates a return request, generates a shipping label, processes the refund, and writes an audit record — all in under 25 seconds.

---

## Architecture

```
Client (Slack or direct HTTP POST)
        |  JSON-RPC 2.0 — message/send
        v
+-------------------------------------------------------+
|  Flex Gateway (CloudHub 2.0)                          |
|  Policy: A2A PII Detector v1.0.1                      |
|  If message contains a US SSN -> return 401, stop     |
+-------------------------------------------------------+
        |
        v
complaint-resolution-broker  (Google Gemini 2.5 Flash Lite)
        |
        |-- A2A --> Customer Verification Agent  (Node.js on Heroku /a2a/)
        |              Returns: verified status, address, expedited flag
        |
        |-- MCP --> Inventory MCP Server  (Heroku /inventory)
        |              create_return_request
        |              generate_return_label     <- runs in parallel with refund
        |              check_inventory_status
        |
        +-- MCP --> Finance MCP Server  (Heroku /finance)
                       process_refund             <- runs in parallel with label
                       create_ledger_entry
```

Why steps 3 and 4 run in parallel: generating a shipping label and processing the refund don't depend on each other. The LLM's instructions explicitly say they can run at the same time. This alone cuts about 7 seconds off the total response time — no infrastructure changes required, just a change to the natural-language instructions.

Why governance sits at the gateway: the PII policy runs at Flex Gateway before the message ever reaches the LLM. If a customer accidentally includes their Social Security Number, the gateway blocks it (HTTP 401) in ~64ms and the LLM never sees it. This is fundamentally stronger than checking for PII inside the agent code, because the gateway cannot be bypassed by a misconfigured or compromised agent.

---

## Project Structure

```
customer-complaint-resolution/
├── agent-network.yaml          <- Full agent network definition (schemaVersion 1.0.0)
├── exchange.json               <- Anypoint Exchange descriptor (no secrets — use .env)
├── .env.example                <- Copy this to .env and fill in your values
├── .gitignore                  <- Keeps API keys and build files out of git
├── policies/
│   ├── pii-policy.yaml         <- PII Detector policy reference and observed behaviour
│   └── llm-proxy-policies.yaml <- LLM proxy policy notes
├── diagrams/
│   └── architecture.md         <- Mermaid diagrams: topology, trace flow, 4-pillar model
├── docs/
│   ├── DEPLOYMENT.md           <- Step-by-step Anypoint CLI deploy instructions
│   └── TESTING.md              <- Real test requests, expected responses, trace verification
├── research/
│   ├── benchmarks/             <- Scripts to run latency and PII benchmarks against live system
│   ├── configs/                <- Three agent-network.yaml variants (sequential/parallel/max-parallel)
│   ├── analysis/               <- Statistical analysis scripts and charts
│   └── test-data/              <- 50 PII test cases and complaint request library
└── LESSONS-LEARNED.md          <- Technical findings from the lab and production guidance
```

---

## Quick Start

### 1. Set up your environment

```bash
cp .env.example .env
# Open .env and fill in:
# ANYPOINT_ORG_ID      - your Anypoint organization ID
# HEROKU_BACKEND_URL   - the Heroku URL hosting the verification agent and MCP servers
# GOOGLE_GEMINI_API_KEY - your Gemini API key (never commit this)
```

### 2. Publish to Anypoint Exchange

```bash
export ANYPOINT_ORG_ID="your-org-id"
sed -i '' "s/\${ANYPOINT_ORG_ID}/$ANYPOINT_ORG_ID/g" exchange.json

anypoint-cli-v4 exchange asset upload \
  --organization $ANYPOINT_ORG_ID \
  --file exchange.json
```

This publishes 36 sub-assets to Exchange: the broker, all agents, MCP servers, LLM provider, Mule application, and the agent-network descriptor. After publishing, every team in your organisation can discover these agents in Exchange.

### 3. Deploy to CloudHub 2.0

Deploy via Anypoint Runtime Manager. Inject `googleGemini.apiKey`, `heroku-backend.url`, and `ingressgw.url` as Runtime Manager secure properties — never in the config files.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full step-by-step guide.

### 4. Test — happy path (should return HTTP 200)

```bash
export BROKER_URL="https://agent-network-ingress-gw-XXXX.kl0dxv.usa-w1.cloudhub.io/complaint-resolution-broker"

curl -s -X POST "$BROKER_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "786",
    "sessionId": "786",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "cde786",
        "role": "user",
        "kind": "message",
        "parts": [{"kind": "text", "text": "I am customer CUST002. I would like a refund for ORD003"}]
      }
    }
  }' | jq .
```

Expected: `200 OK` with a response containing Refund ID (`REF000002`) and a Shipping Label URL.

### 5. Test — PII rejection (should return HTTP 401)

```bash
curl -s -X POST "$BROKER_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "pii-test",
    "sessionId": "pii-test",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "pii-msg",
        "role": "user",
        "kind": "message",
        "parts": [{"kind": "text", "text": "My SSN is 000-11-1111 and I want a refund"}]
      }
    }
  }'
```

Expected: `401 Unauthorized`. The PII is blocked at the gateway — the LLM is never called.

---

## Key Design Decisions

### Why MCP instead of direct API calls?

MCP is provider-agnostic. Build an MCP server once and any MCP-compatible agent — regardless of which LLM it uses — can call it. If you later swap Gemini for Claude or GPT-4, your tool servers don't change.

### Why A2A instead of a direct REST call to the verification service?

A2A gives you a standard way to delegate tasks across agents with a defined lifecycle (submitted → working → completed). The verification agent can be independently developed, deployed, and versioned. A2A also handles streaming responses natively, which matters for long-running tasks.

### Why flatten the address fields in generate_return_label?

MuleSoft's ToolUtils.java has a bug where it can't handle nested objects in MCP tool schemas. So instead of a clean `customerAddress: { name, street, city, state, zip }` object, we use flat fields (`customerAddressName`, `customerAddressStreet`, etc.). This is a temporary workaround — when MuleSoft fixes the bug, the schema can be simplified.

### Why is contextId required on every tool?

The LLM gateway uses OpenAI Strict Mode validation, which requires every property to be in the `required` list when `additionalProperties: false`. The `contextId` field satisfies this requirement and doubles as a distributed trace correlation key — every MCP tool call carries it, so you can filter Anypoint Monitoring logs by `contextId` to see the full trace of any single request.

---

## Verified Results from the Lab

Exercise 1 — Created agent network project in Anypoint Code Builder — Done
Exercise 2 — Published 36 assets to Anypoint Exchange via CLI — Done
Exercise 3 — End-to-end refund via Slack + direct A2A call — 200 OK, REF000002 returned
Exercise 4 — A2A PII Detector blocks SSN messages at gateway — 401, 1 span, 1.01s response
Exercise 5 — Agent Visualizer topology + Anypoint Monitoring traces — 19 spans, 20.81s total

---

## Known Limitations

PII detection only covers standard SSN format (XXX-XX-XXXX). The policy regex misses undelimited 9-digit strings (000111111), spaces-separated variants (000 11 1111), and whitespace-padded dashes (000 - 11 - 1111). These three formats accounted for all 3 false negatives in the 50-case benchmark. The fix is to extend the regex — the policy framework supports it.

Temperature is set to 1.0 in the lab config. This is appropriate for demos but too high for production orchestration. Lower it to 0.2 for more consistent tool-calling behaviour in real deployments.

The benchmark data in sample_results/ is synthetic. It's calibrated to match the observed 20.81s execution time from Exercise 5, but it's not measurements from the live system. Run `research/benchmarks/run_latency_benchmark.py` against a live deployment for real numbers.

---

## Related Resources

- [Anypoint Agent Visualizer](https://anypoint.mulesoft.com/visualizer/agentvisualizer/)
- [MuleSoft Agent Fabric Docs](https://docs.mulesoft.com/agent-fabric/)
- [MCP Specification](https://modelcontextprotocol.io/)
- [A2A Protocol Specification](https://google.github.io/A2A/)
- [Anypoint CLI v4](https://docs.mulesoft.com/anypoint-cli/latest/)
- [Academic paper](../academic-paper/mcp-a2a-enterprise-agents-tdx2026.md) — full technical analysis with empirical results

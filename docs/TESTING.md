# Testing Guide — Customer Complaint Resolution Network

All test requests and expected responses are from the actual TDX 2026 lab.

## Prerequisites

- Agent network deployed and Flex Gateway ingress URL known
- Set `BROKER_URL` for convenience:

```bash
export BROKER_URL="https://agent-network-ingress-gw-XXXX.kl0dxv.usa-w1.cloudhub.io/complaint-resolution-broker"
```

---

## A2A Message Format

All requests use the A2A JSON-RPC 2.0 `message/send` method.

```
POST {BROKER_URL}
Content-Type: application/json
```

---

## Test 1 — Happy path refund (Exercise 3)

Request:

```json
{
    "jsonrpc": "2.0",
    "id": "786",
    "sessionId": "786",
    "method": "message/send",
    "params": {
        "message": {
            "messageId": "cde786",
            "role": "user",
            "kind": "message",
            "parts": [
                {
                    "kind": "text",
                    "text": "I am customer CUST002. I would like a refund for ORD003"
                }
            ]
        }
    }
}
```

Expected result: `200 OK`

Expected response content (from Slack thread screenshot):
```
Refund processed for CUST002 for order ORD003.
The refund ID is REF000002 and the return shipping label can be found at
https://shipping.example.com/labels/RET000002.pdf.
The refund is expedited and expected to be completed by 2026-04-21.
```

Expected trace metrics (from Anypoint Monitoring):
- Status: `200 OK`
- Total response time: `~20.81s`
- Spans: `19`
- Root span: `[Agent] complaint-resolution-broker`
- Key child spans: `[Agent] verification-agent`, multiple `[LLM] google-gemini`, `[MCP Server] inventory-mcp-server`

curl equivalent:

```bash
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

---

## Test 2 — PII rejection (Exercise 4)

Request: Same format, but message text contains a US SSN.

```json
{
    "jsonrpc": "2.0",
    "id": "pii-test-1",
    "sessionId": "pii-test-1",
    "method": "message/send",
    "params": {
        "message": {
            "messageId": "pii-msg-1",
            "role": "user",
            "kind": "message",
            "parts": [
                {
                    "kind": "text",
                    "text": "My SSN is 000-11-1111 and I want a refund for ORD003"
                }
            ]
        }
    }
}
```

Expected result: `401 Unauthorized`

Expected trace metrics:
- Status: `401 Unauthorized`
- Total response time: `~1.01s`
- Spans: `1` — only `[Agent] complaint-resolution-broker` + router egress
- No `[LLM]` or `[MCP Server]` spans — the message is blocked before the LLM sees it

What this proves: The A2A PII Detector policy intercepts the message at the Flex Gateway
ingress layer. The Gemini LLM is never called. SSN data never enters the AI pipeline.

---

## Test 3 — Agent Visualizer verification (Exercise 5 Task 1)

This is not an API call — it's a visual check in Anypoint Platform.

1. Navigate to: `anypoint.mulesoft.com/visualizer/agentvisualizer/`
2. Set filters:
   - Environment: Sandbox
   - Activity Period: Last 7 days
3. Verify topology matches:

```
Complaint Resolution ... [Agent]     <- MuleSoft
    │
    ├── Customer Verification ... [Agent]   <- Customnodejs
    ├── Inventory MCP Server [MCP]          <- Other · Tools
    └── Finance MCP Server [MCP]            <- Other · Tools
```

4. Click Complaint Resolution Broker node → verify side panel:
   - Status: Active
   - Asset version: v1.1.1 (or v1.1.4 for final submission)
   - Policies: `A2A Agent Card`, `A2A PII Detector`
   - Governance and Security: `Managed and secured with Flex Gateway`

---

## Test 4 — Trace drill-down (Exercise 5 Task 2)

1. Navigate to: Anypoint Monitoring → Traces
2. Set environment filter to Sandbox, time range Last 7 days
3. Filter by entity: `complaint-resolution-broker`
4. Locate the `200 OK` trace from Test 1
5. Verify span hierarchy matches the diagram in `diagrams/architecture.md`
6. Locate the `401 Unauthorized` trace from Test 2
7. Confirm it shows only 1-2 spans (no LLM or MCP spans)

---

## Test 5 — Log search (Exercise 5 Task 2, continued)

From the trace detail view, click a span → View Bottlenecking Logs.

Expected log entry class: `MuleRuntimeJwt...[Customer-complaint-resolution.uber...`

In Log Search (Anypoint Monitoring):

```
application: "customer-complaint-resolution" OR "api_version:2086I455"
```

Filter by:
- `log level: DEBUG`
- `logger: INSECURE-LOGGING`
- `message: LLM call failed agent:Complaint_Resolution_Broker`

The structured log lines contain:
- `contextId` — correlates to the A2A session
- Full stack trace of the LLM call with `google-gemini` details
- `worker: customer-complaint-resolution-00b4bc746-hl15u`

---

## Slack integration test (Exercise 3, alternate path)

If you have the RefundBot Slack app installed:

1. Open MAF Workshop Slack workspace (or your workspace)
2. Direct message `@RefundBot`
3. Send: `I need to return the Laptop Stand for customer CUST002`

Expected response thread:
```
Configuration Saved! Your personal Broker URL is set to:
   https://agent-network-ingress-gw-ulbvne.kl0dxv.usa-w1.cloudhub.io/complaint-resolution-broker/

[After sending the complaint message:]
Refund processed. Shipping label generated.
Refund ID: REF000002, Shipping Label URL:
https://shipping.example.com/labels/RET000002.pdf
```

# Evidence of Working Implementation

Author: Md Helal Uddin
Event: Salesforce TDX 2026, Session 1557 — "Connect & Govern MCP and A2A with MuleSoft Agent Fabric"
Date: April 16, 2026 | Sandbox environment, Business Group: Student13
All 5 exercises completed and verified.

This document maps each screenshot to the exercise and claim it proves.
All screenshots are in the [`../screenshots/`](../screenshots/) folder.

---

## Exercise 1 — Create Agent Network Project

This exercise added the A2A PII Detector policy asset to the project via Anypoint Code Builder.

Screenshot: [`Exercise 4 – Task 2-1.jpg`](../screenshots/Exercise%204%20–%20Task%202-1.jpg)
Shows: Anypoint Code Builder "Add Exchange Assets" dialog — `A2A PII Detector v1.0.1` selected from MuleSoft Organization, ready to add to project.

Key detail visible: Three policies available — `A2A PII Detector` (selected), `MCP PII Detector`, `A2A Schema Validation`. The `A2A PII Detector v1.0.1` checkbox is ticked. This corresponds to the `dependencies` entry added to `exchange.json`.

---

## Exercise 2 — Publish to Anypoint Exchange (Deploy)

Agent network and all sub-assets successfully published to Anypoint Exchange via CLI.

Screenshot: [`Exercise 4 – Task 2-5.jpg`](../screenshots/Exercise%204%20–%20Task%202-5.jpg)
Shows: Anypoint Code Builder terminal — full publish log showing 36 assets deployed.

Key details visible in terminal output:
```
Publishing 'agent' 'Customer Verification Agent'...   -> verification-agent v1.1
Publishing 'mcp'   'Finance MCP Server'...            -> finance-mcp-server  v1.1
Publishing 'mcp'   'Inventory MCP Server'...          -> inventory-mcp-server v1.1
Publishing 'llm'   'Google Gemini'...                 -> google-gemini v1.1
Publishing 'app'   'customer-complaint-resolution-mule-application'...
Publishing 'agent-network' 'Customer Complaint Resolution Network'...
36 Assets from agent network 'customer-complaint-resolution' were published.
```
Group ID: `e3ef37b3-16d8-493a-a57b-35b2d6ff2c9b`
Published to: `https://anypoint.mulesoft.com/exchange/`

---

## Exercise 3 — End-to-End Test via Slack

The full 5-step orchestration completes successfully — customer verified, return created, shipping label generated, refund processed, ledger entry written.

Screenshots:
- [`Chat-success-with-agents.jpg`](../screenshots/Chat-success-with-agents.jpg) — Slack: RefundBot confirms `200 OK` configuration, user sends complaint, RefundBot replies with Refund ID and Shipping Label URL
- [`Chat-success-with-agents-more.jpg`](../screenshots/Chat-success-with-agents-more.jpg) — Slack thread: full multi-turn conversation showing the complete resolution flow

Key details visible:
- RefundBot configuration saved, Broker URL set to:
  `https://agent-network-ingress-gw-ulbvne.kl0dxv.usa-w1.cloudhub.io/complaint-resolution-broker/`
- User message: `"I need to return the Laptop Stand for customer CUST002"`
- RefundBot response: `"Refund processed for CUST002 for order ORD003. The refund ID is REF000002 and the return shipping label can be found at https://shipping.example.com/labels/RET000002.pdf. The refund is expedited and expected to be completed by 2026-04-21."`
- 7 replies in thread, last reply at 1:53 PM

All 5 orchestration steps ran:
1. verification-agent verified CUST002 (returned `expedited: true` — Gold/Platinum tier)
2. create_return_request created return (Return ID: RET000002)
3. generate_return_label generated label (https://shipping.example.com/labels/RET000002.pdf)
4. process_refund processed refund (REF000002, expedited)
5. create_ledger_entry recorded the transaction

---

## Exercise 4 — A2A PII Detector Policy

The PII Detector policy was applied via Flex Gateway and successfully blocks messages containing US SSNs with HTTP 401, before the LLM is called.

### 4a — Policy applied in Anypoint Code Builder

Screenshots:
- [`Exercise 4 – Task 2-2.jpg`](../screenshots/Exercise%204%20–%20Task%202-2.jpg) — Policy YAML snippet added to `agent-network.yaml` inside the broker spec
- [`Exercise 4 – Task 2-3.jpg`](../screenshots/Exercise%204%20–%20Task%202-3.jpg) — `exchange.json` dependency block for `a-two-a-pii-detector` added
- [`Exercise 4 – Task 2-4.jpg`](../screenshots/Exercise%204%20–%20Task%202-4.jpg) — Redeployment triggered after policy changes
- [`Exercise 4 – Task 2-6.jpg`](../screenshots/Exercise%204%20–%20Task%202-6.jpg) — Anypoint API Manager: A2A PII Detector policy active on the broker
- [`Exercise 4 – Task 2-7.jpg`](../screenshots/Exercise%204%20–%20Task%202-7.jpg) — Policy configuration: entity = `US SSN`, action = `Reject`
- [`Exercise 4 – Task 2-8.jpg`](../screenshots/Exercise%204%20–%20Task%202-8.jpg) — Test request sent containing SSN `000-11-1111`
- [`Exercise 4 – Task 2-9.jpg`](../screenshots/Exercise%204%20–%20Task%202-9.jpg) — Response: `401 Unauthorized` — PII blocked

Key detail: The YAML snippet added to `agent-network.yaml` (visible in screenshot):
```yaml
policies:
  - ref:
      name: a-two-a-pii-detector
      namespace: 68ef9520-24e9-4cf2-b2f5-620025690913
    configuration:
      entities:
        - US SSN
      action: Reject
```

### 4b — LLM Proxy policies (Google Gemini)

Screenshots: [`google-gmi-polices-add-1.jpg`](../screenshots/google-gmi-polices-add-1.jpg) through [`google-gmi-polices-add-6.jpg`](../screenshots/google-gmi-polices-add-6.jpg)
Shows: Anypoint API Manager — LLM Proxies → Google Gemini → Policies. Inbound: `Tracing` (TROUBLESHOOTING), `Agent Connection Telemetry` (CUSTOM). Yellow warning: policy changes are reverted on redeploy.

---

## Exercise 5 — Agent Visualizer + Distributed Tracing

### 5a — Agent Visualizer: live topology

The deployed agent network topology is visible in Anypoint Agent Visualizer with all four nodes correctly connected.

Screenshots:
- [`Exercise-5-Task-1-0-Dashboard-Anypoint-Insight.jpg`](../screenshots/Exercise-5-Task-1-0-Dashboard-Anypoint-Insight.jpg) — Anypoint Monitoring dashboard: Insights overview for the Student13 org, Sandbox environment
- [`Exercise-5-Task-1-1-Agent-Visualizer-Graph.jpg`](../screenshots/Exercise-5-Task-1-1-Agent-Visualizer-Graph.jpg) — Agent Visualizer: full topology graph with Filters panel open
- [`Exercise-5-Task-1-2-Agent-Visualizer-Broker-Details.jpg`](../screenshots/Exercise-5-Task-1-2-Agent-Visualizer-Broker-Details.jpg) — Broker detail panel: Active status, policies, governance badge
- [`Ex5-Student-Task1-1-AgentVisualizer-Initial.jpg`](../screenshots/Ex5-Student-Task1-1-AgentVisualizer-Initial.jpg) — Clean Agent Visualizer view (no filters panel) — large clear topology

Key details visible in visualizer:

Node: Complaint Resolution Broker — Type: Agent — Platform: MuleSoft — Status: Active
Node: Customer Verification Agent — Type: Agent — Platform: Customnodejs
Node: Inventory MCP Server — Type: MCP — Platform: Other — Tools visible
Node: Finance MCP Server — Type: MCP — Platform: Other — Tools visible

Broker detail panel (from Exercise-5-Task-1-2-Agent-Visualizer-Broker-Details.jpg):
- Status: Active
- Business Group: Student13
- Environment (Type): Sandbox (Sandbox)
- Based on Asset Version: v1.1.1
- Policies (A2A): A2A Agent Card, A2A PII Detector
- Transformation: Header Injection
- Troubleshooting: Tracing
- Governance and Security: Managed and secured with Flex Gateway

Visualizer filter settings (from Exercise-5-Task-1-1-Agent-Visualizer-Graph.jpg):
- Business Groups: Student13
- Environment: Sandbox
- Activity Period: Last 7 days

---

### 5b — Distributed Tracing: successful 5-step run

The full orchestration flow generates a 19-span distributed trace visible in Anypoint Monitoring.

Screenshots:
- [`Exercise-5-Task-2-0-All-Traces-List.jpg`](../screenshots/Exercise-5-Task-2-0-All-Traces-List.jpg) — Traces Overview: full span list for the Sandbox environment, all `200 OK`
- [`Exercise-5-Task-2-1-Traces-List-Broker-Filtered.jpg`](../screenshots/Exercise-5-Task-2-1-Traces-List-Broker-Filtered.jpg) — Traces filtered by entity: `complaint-resolution-broker`
- [`Exercise-5-Task-2-2-Trace-Success-Full-Flow.jpg`](../screenshots/Exercise-5-Task-2-2-Trace-Success-Full-Flow.jpg) — Trace detail: Trace ID `ddecffb6c76a554cee11cc53da7b35bc`, full 19-span waterfall

Verified trace metrics (from Exercise-5-Task-2-2-Trace-Success-Full-Flow.jpg):
- Status Code: 200 OK
- Total Response Time: 20.81s
- Trace Start: 22 Apr 2026 at 12:42 am
- Root Span: [Agent] complaint-resolution-broker
- Total Spans: 19

Span hierarchy (key spans from waterfall):
```
[Agent] complaint-resolution-broker        20.81s
  router api-instance ... egress           20.81s
    mule:flow                              12.60s
      [BROKER] Complaint_Resolution_Broker 12.50s
        [Agent] verification-agent         255.79ms  <- Step 1
          router api-instance egress       254.84ms
        [LLM] google-gemini                505.27ms  <- LLM reasoning
          router api-instance egress       504.41ms
        [Agent] verification-agent         1.69s     <- A2A response processing
          router api-instance egress       608.01ms
        [LLM] google-gemini                539.27ms  <- LLM plans next steps
          router api-instance egress       538.65ms
        [MCP Server] inventory-mcp-server  77.38ms   <- Steps 2/3
          router api-instance egress       75.95ms
        [LLM] google-gemini                833.73ms  <- LLM calls finance tools
        [MCP Server] inventory-mcp-server  75.77ms   <- Step 3 (return label)
        [LLM] google-gemini                551.71ms  <- Steps 4/5 (refund + ledger)
```

---

### 5c — Distributed Tracing: PII rejection trace

A message containing a US SSN produces HTTP 401, with only 1 span — the LLM is never invoked.

Screenshots:
- [`Exercise-5-Task-2-3-Trace-Error-PII-401.jpg`](../screenshots/Exercise-5-Task-2-3-Trace-Error-PII-401.jpg) — Trace detail: Trace ID `c8d39bd12f4bc55092f55705f1bb58b9`, 1.01s, 401 Unauthorized
- [`Ex5-Student-Task2-3-TraceError.jpg`](../screenshots/Ex5-Student-Task2-3-TraceError.jpg) — Same trace: alternate view

Verified PII rejection metrics:
- Status Code: 401 Unauthorized
- Total Response Time: 1.01s
- Trace Start: 20 Apr 2026 at 04:00 pm
- Root Span: [Agent] complaint-resolution-broker
- Total Spans: 1 (only broker + router egress)

What this proves: The PII Detector fires at Flex Gateway ingress. No [LLM] span exists. No [MCP Server] span exists. The message is stopped before it enters the Mule flow. The LLM (Gemini) never sees the SSN.

---

### 5d — Log Search from trace

Structured logs are accessible from trace spans via Anypoint Log Search.

Screenshot: [`Exercise-5-Task-2-4-Logs-From-Trace.jpg`](../screenshots/Exercise-5-Task-2-4-Logs-From-Trace.jpg)
Shows: Anypoint Log Search — 102 hits, structured log entries from the Mule worker `customer-complaint-resolution-00b4bc746-hl15u`.

Key details visible:
- Application: `customer-complaint-resolution`
- Logger: `INSECURE-LOGGING`
- Log level: `DEBUG`
- Log class: `MuleRuntimeJwt...[Customer-complaint-resolution.uber...]`
- Worker ID: `customer-complaint-resolution-00b4bc746-hl15u`
- Timestamp: `22 Apr 2026, 00:42`

---

## Summary

Exercise 1 — PII Detector asset added to project — Screenshot: Exercise 4 – Task 2-1.jpg — Done
Exercise 2 — 36 assets published to Exchange — Screenshot: Exercise 4 – Task 2-5.jpg — Done
Exercise 3 — End-to-end refund via Slack — Screenshot: Chat-success-with-agents*.jpg — 200 OK, REF000002 returned
Exercise 4 — PII Detector blocks SSN with 401 — Screenshot: Exercise 4 – Task 2-6 to 9.jpg — 401 Unauthorized
Exercise 4b — LLM proxy policies active — Screenshot: google-gmi-polices-add-*.jpg — Tracing + Telemetry confirmed
Exercise 5a — Agent Visualizer shows live topology — Screenshot: Exercise-5-Task-1-*.jpg — All 4 nodes visible
Exercise 5b — 19-span success trace at 20.81s — Screenshot: Exercise-5-Task-2-2-*.jpg — 200 OK, 19 spans
Exercise 5c — PII trace: 1 span, 1.01s, 401 — Screenshot: Exercise-5-Task-2-3-*.jpg — 401, no LLM span
Exercise 5d — Log search from trace — Screenshot: Exercise-5-Task-2-4-*.jpg — 102 log hits

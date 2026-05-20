# Architecture Diagrams — Customer Complaint Resolution Network

Diagrams use [Mermaid](https://mermaid.js.org/) notation.
Render in GitHub, VS Code (Mermaid Preview extension), or [mermaid.live](https://mermaid.live).

All diagrams are derived from the actual deployed system at TDX 2026.
Agent Visualizer topology confirmed at anypoint.mulesoft.com/visualizer/agentvisualizer/


## 1. Deployed Agent Network Topology

As seen in Anypoint Agent Visualizer (Exercise 5):

```mermaid
graph TD
    GW["Flex Gateway\nCloudHub 2.0 Ingress\nagent-network-ingress-gw-ulbvne.kl0dxv.usa-w1.cloudhub.io"]

    subgraph Broker["complaint-resolution-broker (Agent, MuleSoft)"]
        BRK["Complaint Resolution Broker\nGoogle Gemini 2.5 Flash Lite\nA2A Agent Card v1.1.4"]
        PII["Policy: A2A PII Detector v1.0.1\nentity: US SSN, action: Reject"]
    end

    subgraph Workers["Sub-agents and MCP Servers"]
        VA["Customer Verification Agent\nAgent, CustomNodeJS\nHeroku /a2a/"]
        INV["Inventory MCP Server\nMCP, streamableHttp\nHeroku /inventory"]
        FIN["Finance MCP Server\nMCP, streamableHttp\nHeroku /finance"]
    end

    Client["Client\nA2A JSON-RPC 2.0\nmessage/send"]

    Client -->|"POST /complaint-resolution-broker"| GW
    GW -->|"PII check, forward or 401"| BRK
    BRK -->|"A2A: verify customer and get address"| VA
    BRK -->|"MCP: create_return_request, generate_return_label, check_inventory_status"| INV
    BRK -->|"MCP: process_refund, create_ledger_entry"| FIN
```


## 2. 5-Step Orchestration Sequence

```mermaid
sequenceDiagram
    actor Client
    participant GW as Flex Gateway (PII Detector)
    participant Broker as Complaint Resolution Broker (Gemini)
    participant VA as Customer Verification Agent (Node.js, A2A)
    participant INV as Inventory MCP Server
    participant FIN as Finance MCP Server

    Client->>GW: POST /complaint-resolution-broker
    GW->>GW: Scan for US SSN
    alt PII detected
        GW-->>Client: 401 Unauthorized (1.01s)
    else Clean message
        GW->>Broker: Forward message

        Note over Broker: Step 1 — Verify customer
        Broker->>VA: A2A task: verify CUST002 / ORD003
        VA-->>Broker: verified, address, expedited true or false

        Note over Broker: Step 2 — Create return
        Broker->>INV: MCP: create_return_request
        INV-->>Broker: returnId RET-XXXXX

        Note over Broker: Steps 3 and 4 run independently
        par Return label
            Broker->>INV: MCP: generate_return_label
            INV-->>Broker: labelUrl
        and Refund
            Broker->>FIN: MCP: process_refund
            FIN-->>Broker: refundId REF000002, transactionId TXN-XXXXX
        end

        Note over Broker: Step 5 — Ledger entry
        Broker->>FIN: MCP: create_ledger_entry
        FIN-->>Broker: ledgerEntryId LED-XXXXX

        Broker-->>GW: Final summary response
        GW-->>Client: 200 OK — Refund ID and Shipping Label URL (~20.81s)
    end
```


## 3. Trace Span Hierarchy (from Anypoint Monitoring)

Actual trace from Exercise 5 — Trace ID ddecffb6c76a554cee11cc53da7b35bc, 22 Apr 2026 12:42 am, 20.81s total, 19 spans:

```mermaid
graph LR
    T["[Agent] complaint-resolution-broker 20.81s"]

    T --> R1["router api-instance egress 20.81s"]
    R1 --> F1["mule:flow 12.60s"]
    F1 --> B1["[BROKER] Complaint_Resolution_Broker 12.50s"]

    B1 --> VA1["[Agent] verification-agent 255.79ms"]
    VA1 --> RVA1["router api-instance egress 254.84ms"]

    B1 --> L1["[LLM] google-gemini 505.27ms"]
    L1 --> RL1["router api-instance egress 504.41ms"]

    B1 --> VA2["[Agent] verification-agent 1.69s"]
    VA2 --> RVA2["router api-instance egress 608.01ms"]

    B1 --> L2["[LLM] google-gemini 539.27ms"]
    L2 --> RL2["router api-instance egress 538.65ms"]

    B1 --> M1["[MCP Server] inventory-mcp-server 77.38ms"]
    M1 --> RM1["router api-instance egress 75.95ms"]

    B1 --> L3["[LLM] google-gemini 833.73ms"]
    B1 --> M2["[MCP Server] inventory-mcp-server 75.77ms"]
    B1 --> L4["[LLM] google-gemini 551.71ms"]

    style T fill:#4a90d9,color:#fff
    style VA1 fill:#7b68ee,color:#fff
    style VA2 fill:#7b68ee,color:#fff
    style L1 fill:#ff8c00,color:#fff
    style L2 fill:#ff8c00,color:#fff
    style L3 fill:#ff8c00,color:#fff
    style L4 fill:#ff8c00,color:#fff
    style M1 fill:#2e8b57,color:#fff
    style M2 fill:#2e8b57,color:#fff
```

Span types: [Agent] = A2A agent call, [LLM] = Gemini reasoning step, [MCP Server] = MCP tool invocation, router api-instance egress = Flex Gateway routing span.


## 4. PII Rejection Trace (Exercise 4 result)

When a message contains a US SSN, the policy fires at ingress:

```mermaid
graph LR
    Client["Client\nMessage with SSN: 000-11-1111"]
    GW["Flex Gateway\nA2A PII Detector v1.0.1"]
    Blocked["401 Unauthorized\n1.01s, 1 span only"]

    Client --> GW
    GW --> Blocked

    style Blocked fill:#dc3545,color:#fff
    style GW fill:#fd7e14,color:#fff
```

Trace shows exactly 1 span ([Agent] complaint-resolution-broker, 1.01s).
The LLM is never called. No MCP tools are invoked. The SSN never leaves the gateway.


## 5. MuleSoft Agent Fabric — Four Pillars

```mermaid
mindmap
  root((Agent Fabric))
    Discover
      Agent Card
        protocolVersion 0.3.0
        skills, input/output modes
        Published at ingressgw.url
      Anypoint Exchange
        classifier: agent-network
        exchange.json descriptor
        Asset version 1.1.4
    Orchestrate
      A2A Protocol
        JSON-RPC 2.0 over HTTP
        method: message/send
        sessionId, messageId
      5-Step Workflow
        verify, return, label
        refund, ledger
        Steps 3+4 parallel
      Google Gemini 2.5 Flash Lite
        temperature 1.0
        topP 0.85
        maxOutputTokens 2048
    Govern
      A2A PII Detector
        Entity: US SSN
        Action: Reject, 401
        Stops message at gateway
      Flex Gateway
        Managed via Anypoint
        Policies in exchange.json deps
      LLM Proxy Policies
        Tracing
        Agent Connection Telemetry
    Observe
      Agent Visualizer
        anypoint.mulesoft.com/visualizer
        Live topology graph
        Broker detail panel
          Active status
          Policies: A2A Agent Card + PII Detector
          Governance: Flex Gateway
      Distributed Tracing
        Anypoint Monitoring Traces
        19 spans, 20.81s
        Filter by entity, status, time
      Log Search
        INSECURE-LOGGING class
        Structured JSON logs
        Linked from trace spans
```


## 6. Project File Structure

```
customer-complaint-resolution/
├── agent-network.yaml          agent network spec (schemaVersion 1.0.0)
├── exchange.json               Anypoint Exchange descriptor (no secrets)
├── .env.example                environment variable template
├── .gitignore                  prevents secret leakage
├── policies/
│   ├── pii-policy.yaml         A2A PII Detector config reference
│   └── llm-proxy-policies.yaml LLM proxy policy reference
└── diagrams/
    └── architecture.md         this file
```

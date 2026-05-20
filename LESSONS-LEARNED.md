# Lessons Learned — TDX 2026 Session 1557

Author: Md Helal Uddin | TDX 2026, San Francisco, April 15–16, 2026
Session: Connect & Govern MCP and A2A with MuleSoft Agent Fabric
Exercises completed: 5 of 5 — working end-to-end refund agent network verified in production

---

These are the things I didn't fully understand before the lab that I understand now. Some of these surprised me. I'm writing them down the way I'd explain them to a colleague.

---

## 1. The YAML schema has five distinct sections and each means something specific

Before the lab I assumed an "agent network config" would be a simple list of agents and their URLs. The actual schema (schemaVersion 1.0.0) separates things into five sections that each play a different role:

- `brokers:` — the LLM-powered orchestrators. These are MuleSoft-managed, exposed as A2A endpoints. The Gemini broker lives here.
- `agents:` — external A2A workers that you call out to. They run outside of MuleSoft (Node.js on Heroku in our case) but speak the A2A protocol. Just a reference here, not a definition.
- `mcpServers:` — external MCP tool servers with their full tool schemas. This is where you define what functions the LLM can call and what inputs they expect.
- `llmProviders:` — which LLM connection to use. Having this separate means you can switch LLMs without touching tool definitions.
- `connections:` — the actual runtime URLs for everything. Separated from the tool schemas so you can point to dev/staging/prod by just changing connections, not the tool logic.

The `connections:` separation is the part that really clicked for me. Tool schemas stay constant; URLs change per environment.

---

## 2. Tool schemas must be completely flat — nested objects break the current runtime

The `generate_return_label` tool needs a customer address. The clean way to define this is a nested object: `customerAddress: { name, street, city, state, zip }`. But the current MuleSoft runtime (ToolUtils.java) has a bug where it can't handle nested objects in MCP tool input schemas. It silently fails.

The workaround is to flatten everything: `customerAddressName`, `customerAddressStreet`, `customerAddressCity`, `customerAddressState`, `customerAddressZip`. Five separate string fields instead of one object. Not elegant, but it works. I've noted this in the YAML as a known workaround with a note to revisit when MuleSoft ships the fix.

If you're designing MCP tools for MuleSoft Agent Fabric right now, design flat schemas from the start. Don't discover this bug at 11pm during a demo.

---

## 3. Every tool needs a contextId field because of OpenAI Strict Mode

Every single tool in the network has `contextId` as a required field. This isn't something I added for fun — it's required because the Gemini gateway uses OpenAI Strict Mode validation, which mandates that every property in a schema with `additionalProperties: false` must also be in the `required` list. If you miss one field, the whole tool call fails with a validation error.

The nice side effect is that `contextId` becomes a free distributed trace correlation key. Every MCP call carries the same workflow ID, so in Anypoint Monitoring you can filter by `contextId` to see the complete chain of spans for any single customer complaint.

---

## 4. The PII policy stops the message before the LLM ever sees it — the trace proves this

This was the most striking part of Exercise 4. I expected the policy to inspect the message, detect the SSN, and maybe log a warning. What actually happens is much more decisive:

- Clean message: 19 spans, 20.81 seconds, full 5-step orchestration
- SSN message: 1 span, 1.01 seconds, HTTP 401 returned

The SSN never reaches Gemini. The policy fires at the Flex Gateway ingress, before the Mule flow even starts. The single trace span you see is just the [Agent] broker router egress — the request never got past the front door.

This matters more than it sounds. An agent that processes a message and then strips the SSN at the end has still read the SSN. The LLM has seen it, possibly tokenised it, possibly logged it. Gateway-level enforcement at ingress means the LLM literally never encounters the PII. That's a categorically different security guarantee.

---

## 5. Parallelism comes from the instructions, not the infrastructure

The instructions block tells the LLM: "steps 3 and 4 can run at the same time — the refund doesn't need to wait for the shipping label." The Gemini orchestrator reads this and actually executes them concurrently. The trace shows overlapping spans confirming it.

I ran a benchmark to measure the actual difference. Moving from sequential to parallel (steps 3+4 concurrent) cut latency by 26.5% — over 7 seconds on a 28-second workflow. This required zero infrastructure changes. I changed three lines of natural language in the `instructions:` field and redeployed.

The LLM understands causal dependencies in natural language. If you tell it something doesn't need to wait, it won't wait. If you want to use this, be explicit in your instructions about which steps are independent.

---

## 6. The expedited flag shows how business logic flows through the agent chain

When the verification agent runs, it doesn't just return "valid" or "invalid". It also checks the customer's loyalty tier and sets an `expedited: boolean` field. Gold and Platinum customers get expedited refund processing.

This value travels from the A2A verification response → through Gemini's reasoning → into the `process_refund` MCP call, where the finance backend uses it to decide processing speed. The AI isn't just a pass-through — it's actively carrying context between systems that otherwise have no direct connection.

The design lesson here is to make your agent output schemas carry rich context, not just binary results. Agents that pass context forward are much more powerful than agents that just say yes or no.

---

## 7. Agent Visualizer shows governance badges — and missing badges are a warning sign

In Anypoint Agent Visualizer, the broker node shows badges for active governance: A2A Agent Card, A2A PII Detector, Header Injection, Tracing, and "Managed and secured with Flex Gateway". These aren't decorative. They confirm the actual runtime state.

If I deployed a new version of the network and the PII Detector badge was missing, that would immediately tell me the policy wasn't applied correctly. This is much faster to spot than reading logs or YAML diffs. The visualizer is a real debugging tool, not just a diagram.

---

## 8. Policy changes in API Manager are temporary — agent-network.yaml is the source of truth

If you go into Anypoint API Manager, navigate to LLM Proxies, and manually change a policy, you'll see a yellow warning: "This instance comes from an agent network project. Policy changes made here will be reverted next time it gets redeployed."

This is intentional. The YAML is the source of truth. Everything is version-controlled. If you want to change a policy, change it in `agent-network.yaml`, commit the change, and redeploy. Manual UI changes get wiped. I almost learned this the hard way.

---

## 9. Publishing to Exchange creates 36 sub-assets automatically

Running `anypoint-cli-v4 exchange asset upload` against the project doesn't just upload one file. It creates 36 separate assets in Exchange: the broker, verification agent, inventory MCP server, finance MCP server, Google Gemini LLM provider, the Mule application itself, and the agent-network descriptor — each with its own Exchange URL, version, and group ID.

This is what makes the network discoverable. Any team in the organisation can open Exchange, search for "complaint resolution", and find these agents. They can build on top of them without needing to read source code. That's the Discover pillar of Agent Fabric in practice.

---

## 10. API keys must be injected at runtime — the exchange.json secret flag is not enough on its own

The `exchange.json` variables section has `"secret": true` on the `googleGemini.apiKey` field. This tells Anypoint Platform to mask it in the UI and not return it in API responses. But it doesn't protect a key that was hardcoded as the `"default"` value.

The right approach is to leave `"default": ""` in exchange.json (committed to git) and inject the real key via Anypoint Runtime Manager secure properties at deploy time. The key never touches the filesystem. This is the pattern used in this project.

If your API key ever ended up in a config file that was committed, rotate it immediately. Anypoint Exchange is visible to all org members.

---

## What I would do differently in production

Set temperature to 0.2 for the broker. The lab uses 1.0, which makes the LLM more creative and unpredictable. For orchestration you want deterministic, consistent behaviour. Lower temperature means more reliable tool-calling order.

Extend the PII policy to cover more entity types. The lab only enabled US SSN. For a real customer service system you'd also want to block Credit Card Numbers, Email Addresses, Phone Numbers, and Passport Numbers. The policy supports all of these — just add them to the `entities` list.

Wire the deployment into CI/CD. The `anypoint-cli-v4 exchange asset upload` command is fully scriptable. Adding it to a GitHub Actions workflow means every merge to main automatically publishes a new version to Exchange. Manual deployments are a source of drift.

Add A2A Schema Validation on the verification agent response. The broker trusts the verification agent to return `expedited` and address fields. If the verification agent has a bug and returns an incomplete response, the broker can fail unpredictably. The A2A Schema Validation policy (available in Exchange alongside the PII Detector) would catch this at the gateway before it reaches the LLM.

---

## Questions I still want to investigate

- How does Agent Fabric handle A2A tasks that take minutes or hours? Does it poll, or does the agent send a callback?
- What's the actual overhead of routing all agent calls through Flex Gateway compared to direct agent-to-agent communication?
- Can you A/B test two LLM providers using Anypoint's traffic-splitting policies? For example, 20% of requests go to Claude and 80% to Gemini, and you compare quality metrics.
- How do you handle in-flight sessions during a redeployment without dropping requests?

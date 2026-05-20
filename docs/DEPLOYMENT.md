# Deployment Guide — Customer Complaint Resolution Network

Based on the exact steps completed at TDX 2026 Session 1557 (Exercises 1-2).

## Prerequisites

- Anypoint CLI v4: `npm install -g anypoint-cli-v4`
- Anypoint Platform account with Business Group and Sandbox environment
- CloudHub 2.0 access for Flex Gateway deployment
- Google Gemini API key (console.cloud.google.com)
- Heroku backend: pre-provisioned for the lab; self-hosted for production

---

## Step 1 — Set up your environment

```bash
# Copy the template and fill in real values
cp .env.example .env
# Edit .env with your actual ANYPOINT_ORG_ID, HEROKU_BACKEND_URL,
# GOOGLE_GEMINI_API_KEY, etc.
```

Update `exchange.json` — replace `${ANYPOINT_ORG_ID}` with your real org ID:

```bash
# Find your org ID in Anypoint Platform → Access Management → Organization
export ANYPOINT_ORG_ID="your-actual-org-id"
sed -i '' "s/\${ANYPOINT_ORG_ID}/$ANYPOINT_ORG_ID/g" exchange.json
```

Do not commit `exchange.json` after substituting real values.
Revert to the template (`${ANYPOINT_ORG_ID}` placeholder) before any git commit.

---

## Step 2 — Login to Anypoint CLI

```bash
anypoint-cli-v4 conf username $ANYPOINT_USERNAME
anypoint-cli-v4 conf password $ANYPOINT_PASSWORD
# Or use connected app credentials:
# anypoint-cli-v4 conf clientId $ANYPOINT_CLIENT_ID
# anypoint-cli-v4 conf clientSecret $ANYPOINT_CLIENT_SECRET
```

---

## Step 3 — Publish to Anypoint Exchange

The Anypoint CLI reads `exchange.json` and `agent-network.yaml` and publishes all
sub-assets (broker, agents, MCP servers, LLM provider, agent network) to Exchange.

```bash
anypoint-cli-v4 exchange asset upload \
  --organization $ANYPOINT_ORG_ID \
  --file exchange.json
```

Expected terminal output (matches Exercise 2 screenshot):

```
[INFO] [PID: 70277] Publishing 'agent' 'Customer Verification Agent'...
        Group ID : <your-org-id>
        Asset ID : verification-agent
        Version  : 1.1
        URL      : https://anypoint.mulesoft.com/exchange/...

[INFO] [PID: 70277] Publishing 'mcp' 'Finance MCP Server'...
        Group ID : <your-org-id>
        Asset ID : finance-mcp-server
        Version  : 1.1
        URL      : https://anypoint.mulesoft.com/exchange/...

[INFO] [PID: 70277] Publishing 'mcp' 'Inventory MCP Server'...
[INFO] [PID: 70277] Publishing 'llm' 'Google Gemini'...
[INFO] [PID: 70277] Publishing 'app' 'customer-complaint-resolution-mule-application'...
[INFO] [PID: 70277] Publishing 'agent-network' 'Customer Complaint Resolution Network'...
        36 Assets from agent network 'customer-complaint-resolution' were published.
```

---

## Step 4 — Deploy to CloudHub 2.0

After publishing to Exchange, deploy the runtime via Anypoint Platform:

1. Navigate to Anypoint Platform → Runtime Manager → Deploy Application
2. Select the `customer-complaint-resolution` application from Exchange
3. Choose CloudHub 2.0 as the deployment target
4. Configure environment variables (inject secrets here — not in config files):
   - `googleGemini.apiKey` → your Gemini API key (mark as secret)
   - `heroku-backend.url` → `https://your-backend.herokuapp.com`
   - `ingressgw.url` → leave blank initially; set after Flex Gateway provisions
5. Deploy → wait for Started status

---

## Step 5 — Configure Flex Gateway ingress

After deployment, Anypoint provisions a Flex Gateway ingress endpoint:

1. Navigate to Runtime Manager → your deployment → Ingress
2. Copy the public URL (format: `https://agent-network-ingress-gw-XXXX.kl0dxv.usa-w1.cloudhub.io`)
3. Update the `ingressgw.url` environment variable in Runtime Manager with this URL
4. Redeploy (or the app auto-picks it up — depends on version)

The broker's A2A endpoint is then:
```
https://agent-network-ingress-gw-XXXX.kl0dxv.usa-w1.cloudhub.io/complaint-resolution-broker
```

---

## Step 6 — Apply the PII Detector policy dependency

The `a-two-a-pii-detector` policy is declared in `exchange.json` dependencies and referenced
in `agent-network.yaml`. It is automatically resolved from Anypoint Exchange (MuleSoft org
`68ef9520-24e9-4cf2-b2f5-620025690913`) when the agent network deploys.

To verify it is active:
1. Agent Visualizer → click Complaint Resolution Broker → check Policies panel
2. Should show: `A2A Agent Card`, `A2A PII Detector`

---

## Step 7 — Verify in Agent Visualizer

1. Navigate to Anypoint Platform → Agents & Tools → Agent Visualizer
2. Select your environment (Sandbox)
3. You should see the topology:
   ```
   Complaint Resolution Broker (Agent · MuleSoft)
     ├── Customer Verification Agent (Agent · Customnodejs)
     ├── Inventory MCP Server (MCP · Other)
     └── Finance MCP Server (MCP · Other)
   ```
4. Click the broker node → confirm Active status, policies, and Flex Gateway governance badge

---

## Troubleshooting

401 on all requests — PII Detector firing. Check message for SSN patterns (`\d{3}-\d{2}-\d{4}`).

401 on clean requests — Auth config wrong. Verify `ingressgw.url` is set correctly in Runtime Manager.

LLM timeout — Gemini API key invalid or rate-limited. Rotate key; check `googleGemini.apiKey` secret.

Agent Visualizer shows no topology — Wrong business group selected. Switch to your business group in the Filters panel.

36 assets not published — `exchange.json` has wrong `organizationId`. Verify `ANYPOINT_ORG_ID` matches your Anypoint org.

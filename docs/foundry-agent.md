# BuildingAssist in Microsoft Foundry

The root `azd up` creates the Reason portion of the demo end to end:

- Microsoft Foundry account and project
- `model-router` version `2025-11-18`, `GlobalStandard`, Balanced mode
- Azure AI Search Basic with semantic ranking
- Foundry IQ Knowledge Base named `buildingassist-knowledge`
- Managed-identity `RemoteTool` connection from the Foundry project to the
  Knowledge Base MCP endpoint
- Workspace-based Application Insights and a project-level `AppInsights` connection
- Prompt agent named `buildingassist-agent`
- Building-operations OpenAPI document imported into the AI Gateway ToolServer
- Runtime-key-protected MCP endpoint generated from the REST operations
- Key-authenticated `RemoteTool` connection from Foundry to the APIM MCP endpoint

## Information boundaries

| Need | Source | Examples |
|---|---|---|
| Stable facts | Foundry IQ Knowledge Base | buildings, systems, schedules, site constraints, targets, policies |
| Current state | Operations MCP read tools | power, weekly energy, occupancy, temperatures, active alerts |
| Operations | Operations MCP action tools | create a work order; apply a temporary HVAC setpoint |
| Model choice | Model Router | selects an eligible underlying model for each request |

The four Markdown files in `sample-docs/` are chunked into a semantic Search index.
`scripts/setup_foundry_iq.py` creates or updates the index, knowledge source, and
Knowledge Base. `scripts/setup_foundry_agent.py` then creates a new prompt-agent
version only when its model, instructions, or tools differ.

The agent is closed-book and has `tool_choice` set to `required`. It can make factual
claims only from connected MCP tool results in the current conversation. It must not
use model knowledge or infer missing values. If a source fails, returns no result, or
does not contain all data needed to answer, the complete response is exactly
`i don't know`.

## Operations API and MCP tools

The backend exposes ordinary FastAPI routes under `/operations`. The APIM AI Gateway
imports their OpenAPI contract into the `building-operations` ToolServer at
`/default/toolservers/building-operations/mcp`. Foundry stores the gateway `Api-Key`
header in the `buildingassist-operations` project connection.

MCP clients discover these separate read operations, which run without approval:

- `operations_listBuildings`: enumerate buildings and their canonical IDs
- `operations_getBuildingInformation`: retrieve stable metadata, systems, zones, specificities,
  and operating policy for one building
- `operations_getBuildingData`: retrieve time-stamped telemetry, zone measurements, status,
  and active alerts for one building

State-changing tools trigger a Foundry MCP approval request:

- `operations_createWorkOrder`
- `operations_setHvacSetpoint`

Everything returned or changed by these tools is fictional, in-memory simulation
data. HVAC changes also require `confirmed=true` and enforce per-building temperature,
duration, and blocked-zone policies. Restarting the backend resets all action state.

## Tracing

The Foundry project connection named `buildingassist-observability` enables
server-side tracing automatically for every prompt-agent invocation. Traces include
model latency, retrieval, MCP tool calls, failures, and token usage.

The backend configures Azure Monitor OpenTelemetry before creating its Azure AI
Projects client. W3C trace context propagation correlates the Container App request
with Foundry's server-side spans. Agent references include both the name and resource
ID so traces are attributed to `buildingassist-agent`.

Production privacy defaults are explicit:

- prompt, completion, and tool content recording is disabled for client-side spans
- binary-data tracing is disabled
- OpenTelemetry baggage propagation is disabled
- trace-context propagation remains enabled

The Foundry project identity and deployer receive Log Analytics Reader and Privileged
Monitoring Data Reader on Application Insights. After an invocation, open the Foundry
project, select **Agents** > **Traces**, and filter by `buildingassist-agent`.
Ingestion normally takes 2-5 minutes.

## AI Gateway telemetry

The AI Gateway uses the same workspace-based Application Insights resource as the
application. `scripts/setup_ai_gateway_telemetry.py` completes the dynamic Azure
Monitor setup after Bicep provisioning:

- enables OTLP ingestion on Application Insights
- discovers its generated metrics, logs, and traces endpoints and Data Collection Rule
- grants the gateway system identity `Monitoring Metrics Publisher` on that rule
- creates the workspace `OpenTelemetry` exporter with managed identity
- leaves payload capture disabled

The AI Gateway monitoring dashboard currently visualizes model token metrics. The
preview doesn't export MCP tool telemetry or distributed traces through this path.

## Demo sequence

Open `buildingassist-agent` in the Foundry agent playground.

1. Ask: `Which building is most suitable for demand response, and why?`
   Show `operations_listBuildings`, `operations_getBuildingInformation`, and grounded citations.
2. Ask: `What is happening at Paris HQ now, and are there active alerts?`
   Show the time-stamped `operations_getBuildingData` MCP call.
3. Ask: `Create a high-priority work order to inspect the Floor 3 air handling unit.`
   Inspect the arguments, approve the MCP action, and show the simulated work-order ID.
4. Ask: `Temporarily set Paris HQ Floor 3 to 24 C for 60 minutes to reduce peak demand.`
   Let the agent summarize the change and request confirmation. Confirm, inspect the
   Foundry approval request, and approve it.
5. Ask: `Set the Munich dispatch centre to 24 C for demand response.`
   Show the Knowledge Base policy and MCP enforcement rejecting the comfort-critical zone.

Open the `model-router` deployment under **Models + endpoints** and use its model
playground for a simple and a complex prompt. Each response identifies the selected
underlying model. In Azure Monitor, filter to the deployment and split metrics by
underlying model to show routing distribution.

## Manual refresh

The `postprovision` hook normally performs all setup. To refresh the data-plane
objects against the selected root azd environment:

```bash
cd src/backend
uv run python ../../scripts/setup_ai_gateway_telemetry.py
uv run python ../../scripts/setup_foundry_iq.py
uv run python ../../scripts/setup_foundry_agent.py
```

These commands rely on the environment values emitted by `azd provision`. Run them
through the `postprovision` hook or export the corresponding `azd env get-values`
values first.

Role assignments can take several minutes to propagate after the first provision.
If Knowledge Base setup returns `403`, wait for propagation and rerun `azd provision`;
the setup scripts and Bicep resources are idempotent.

## Production boundary

The operations MCP endpoint requires an AI Gateway runtime key stored as a Foundry
project connection. Before connecting real building-management systems, replace the
shared key when the preview supports the required client identity model, persist state
and audit events, apply role-based authorization per tool and site, retain approval
for every control action, and add idempotency keys plus rollback workflows.
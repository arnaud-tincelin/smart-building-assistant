# BuildingAssist — demo scaffold

Environment for the 60-minute demo **"A Developer's Day on the Microsoft Agentic
Platform"** (customer: *Contoso Energy*). The app is a deliberately thin **Smart
Building assistant**: a user can ask what is special about a site, inspect simulated
current conditions, and request a bounded operation. A **Microsoft Foundry agent**
combines **Model Router**, a **Foundry IQ Knowledge Base**, and **MCP** tools.

> Full demo narrative and run-sheet: [.github/instructions.md](.github/instructions.md).

## Architecture

```
Frontend Container App (TypeScript SPA)
   └─ HTTP ─▶ Backend Container App (FastAPI)
            ├─ Responses API ─▶ BuildingAssist prompt agent
            │                    ├─ Model Router (Balanced)
            │                    ├─ Foundry IQ Knowledge Base MCP (Azure AI Search)
        │                    └─ AI Gateway building operations MCP
        └─ /operations/* ─▶ simulated building REST API
APIM AI Gateway (preview)
  ├─ Foundry model provider ─▶ governed model endpoint
  └─ OpenAPI ToolServer ─▶ /default/toolservers/building-operations/mcp
Supporting: ACR, Log Analytics + App Insights traces, Container Apps env, RBAC
SRE Agent (Microsoft.App/agents, in Bicep) ─ watches: both Container Apps, Foundry, APIM ─▶ GitHub issues
```

- **Backend** — Python 3.14 / FastAPI, Azure AI Projects SDK, managed identity
  (`DefaultAzureCredential`). Deps via **uv**. See [src/backend](src/backend).
- **Frontend** — TypeScript SPA (Vite + React), served by nginx. Deps via **npm**
  through the Microsoft package proxy configured in
  [`src/frontend/.npmrc`](src/frontend/.npmrc). The backend URL is injected at
  container start (runtime `config.js`). See [src/frontend](src/frontend).
- **Infra** — `azd` + Bicep. Two Azure Container Apps; images built **remotely by
  ACR** (no local Docker). See [infra](infra).
- **Knowledge** — Azure AI Search Basic hosts the GA Foundry IQ Knowledge Base;
  four Markdown sources are chunked and indexed idempotently after provision.
- **Tracing** — the Foundry project is connected to workspace-based Application
  Insights for automatic prompt-agent traces. The backend adds correlated
  OpenTelemetry spans with prompt and tool content recording disabled.

## Prerequisites

- The provided **`.devcontainer`** (Python 3.14 + uv, Node 26 + npm, azd, Azure CLI,
  Bicep, GitHub CLI). No Docker daemon needed — ACR builds images server-side.
- An Azure subscription and `az login` / `azd auth login`.
- A region where Foundry Agent Service, APIM, Container Apps, and the SRE Agent are
  all available (e.g. **Sweden Central** or **East US 2**) — confirm at build time.

## Run locally (in the devcontainer)

Backend (offline, mock agent):

```bash
cd src/backend
cp .env.example .env          # BUILDINGASSIST_USE_MOCK_AGENT=true by default
uv sync
uv run uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs, /healthz, POST /ask, and /operations/*
```

Frontend (Vite dev server; proxies /api to the backend on :8000):

```bash
cd src/frontend
npm install                   # restores through the Microsoft package proxy
npm run dev                   # → http://localhost:5173
```

Backend tests:

```bash
cd src/backend
uv run pytest
```

## Deploy to Azure

```bash
azd auth login
azd env new buildingassist            # or your own env name
azd env set AZURE_LOCATION swedencentral
azd up                                # provision infra + build (ACR) + deploy both apps
```

`azd up` provisions Model Router `2025-11-18` in Balanced mode, Azure AI Search,
the Foundry IQ Knowledge Base, the APIM-hosted MCP endpoint, the visible prompt
agent, and the required Foundry project connections. It also outputs the app,
Foundry, Search, Application Insights, and APIM resource details.

### Continuous deployment

Every push to `main`, including a merged pull request, runs
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml). GitHub authenticates
to Azure with OIDC as a user-assigned managed identity; there is no client secret.

For initial setup or reconfiguration, ask Copilot to use the repository's
[`azure-github-oidc` skill](.github/skills/azure-github-oidc/SKILL.md). The skill
validates the target subscription and repository, previews the Bicep deployment,
and runs its idempotent configuration helper. It can also be invoked directly:

```bash
az login
gh auth login
bash .github/skills/azure-github-oidc/scripts/configure.sh
```

The skill deploys [`infra/github-oidc.bicep`](infra/github-oidc.bicep) and writes the
required non-secret Azure values to GitHub Actions variables. The workflow exchanges
GitHub OIDC for an Azure token, runs `azd provision --preview`, deploys with `azd up`,
and smoke-tests both application URLs.

The identity has **Contributor** and **Role Based Access Control Administrator** at
subscription scope because the application template creates a resource group and
its role assignments. Keep this demo subscription dedicated to the environment.

### AI Gateway tier (preview)

The deployment creates the native APIM **AI Gateway** SKU and its default workspace,
then registers Model Router as a managed-identity Foundry provider. It also creates a
gateway runtime key, applies a per-caller token limit, exports token telemetry to the
existing Application Insights resource, and keeps payload capture disabled. The same
gateway imports the backend OpenAPI document into a workspace ToolServer and exposes
it at `/default/toolservers/building-operations/mcp`.

The post-provision telemetry setup enables Application Insights OTLP ingestion,
grants the gateway identity **Monitoring Metrics Publisher** on the generated Data
Collection Rule, and registers a managed-identity `OpenTelemetry` exporter. Open
**Monitoring** in the AI Gateway portal to inspect token usage by model. During this
preview, AI Gateway exports token metrics for model traffic; MCP tool telemetry and
distributed traces aren't exported by this path. Payload capture remains disabled.

Foundry authenticates to the ToolServer with the gateway runtime key stored in the
`buildingassist-operations` project connection. This uses the AI Gateway-specific
`service/workspaces/toolServers` contract, not classic `service/apis` resources.

The preview currently has no SLA and is limited to **East US 2** and **Sweden
Central**. Manage additional models, MCP ToolServers, policies, and runtime keys in
the [AI Gateway portal](https://ai.gateway.azure.com). Model and MCP callers use the
`Api-Key` header; the gateway separately uses its managed identity and **Foundry
User** RBAC to call the model deployment.

After provisioning, make a direct Responses API smoke test without writing the key
to a file or command output:

```bash
GATEWAY_RESOURCE_ID="$(azd env get-value AI_GATEWAY_RESOURCE_ID)"
AI_GATEWAY_MODEL_ENDPOINT="$(azd env get-value AI_GATEWAY_MODEL_ENDPOINT)"
AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"
AI_GATEWAY_API_KEY="$(az rest --method post \
  --uri "https://management.azure.com${GATEWAY_RESOURCE_ID}/apiKeys/buildingassist/listSecrets?api-version=2025-09-01-preview" \
  --query primaryKey --output tsv)"

curl "${AI_GATEWAY_MODEL_ENDPOINT}/responses" \
  -H "Content-Type: application/json" \
  -H "Api-Key: ${AI_GATEWAY_API_KEY}" \
  -d "{\"model\":\"${AI_GATEWAY_MODEL}\",\"input\":\"Summarize today in five words.\"}"

unset AI_GATEWAY_API_KEY
```

The app's `/ask` path continues to invoke the Foundry prompt agent through its
project endpoint. AI Gateway model passthrough does not proxy Foundry Agent Service
`agent_reference` calls; direct model clients use `AI_GATEWAY_MODEL_ENDPOINT`.

The prompt agent is closed-book: every factual response requires an MCP tool call.
Unsupported or incomplete requests return exactly `i don't know`; model knowledge is
never used as a fallback. The APIM-hosted operations MCP server separates portfolio
discovery, building information, and current building data into distinct tools.

### Reason demo

Open `buildingassist-agent` in the Foundry playground and run this sequence:

1. `Why is Paris HQ Floor 3 more sensitive to warm afternoons than our other sites?`
2. `What is happening there now, and are there active alerts?`
3. `Create a high-priority work order to inspect the Floor 3 air handling unit.`
4. `Temporarily set Floor 3 to 24 C for 60 minutes to reduce peak demand.`

The first answer comes from Foundry IQ, the second uses read-only operations MCP
tools, and the last two exercise state-changing tools. Foundry requires approval
for non-read-only MCP calls; the HVAC simulator also requires explicit confirmation
and enforces site-specific temperature, duration, and zone policies. All operational
data and actions are clearly marked as fictional simulation data.

Open the `model-router` deployment's model playground to show the underlying model
selected for each response. Azure Monitor can split the deployment's metrics by
underlying model.

The full Foundry IQ and MCP walkthrough is in
[docs/foundry-agent.md](docs/foundry-agent.md).

### Attach the Azure SRE Agent (operate pillar)

The SRE Agent (`Microsoft.App/agents`), its scoped identity, an Action Group, and a
pair of exact 500/503 trace alerts are **provisioned by Bicep**. The post-provision hook
adds a read-only code investigator, a backend-scoped configuration operator, their
response plans and repair skill, plus Code Access when GitHub OAuth has been
authorized. Rehearse both repair paths in
[docs/sre-agent.md](docs/sre-agent.md).

## Demo run-sheet (maps to the one-hour beats)

| Time | Beat | What to show | Pillar |
|---|---|---|---|
| 0:05–0:17 | **Write** | Copilot agent mode builds the `/ask` feature (this repo) | 🟦 Copilot |
| 0:17–0:31 | **Reason** | Model Router + Foundry IQ retrieval + MCP read/action approval | 🟩 Foundry |
| 0:31–0:38 | **Operate** | SRE Agent config — resources watched, GitHub link | 🟧 SRE Agent |
| 0:38–0:43 | **Auto-repair** | Bad Container App config → traced 503 → SRE Agent restores baseline | 🟧 SRE Agent |
| 0:43–0:50 | **Diagnose** | Badge access returns 500 → SRE Agent RCA → GitHub issue | 🟧 SRE Agent |
| 0:50–0:57 | **Fix** | Assign issue → Copilot coding agent PR → **review & merge** → redeploy | 🟦 Copilot (HITL) |
| 0:57–1:00 | **Close** | One platform, governed (APIM AI Gateway + Agent 365) | — |

The staged regressions and repair loops are in [docs/sre-agent.md](docs/sre-agent.md).

## Teardown

```bash
azd down --purge --force
```

The SRE Agent is part of the Bicep deployment and is removed with the environment.

## Repository layout

```
azure.yaml                 azd project (two ACA services, ACR remote build)
infra/                     Bicep: main + modules (monitoring, registry, identity,
                           apps-env, foundry, search, apim, container-app, rbac, sre-agent)
scripts/                   postprovision hook + Foundry IQ / prompt-agent setup
src/backend/               FastAPI service (uv)
src/frontend/              Vite + React SPA (TypeScript, npm)
sample-docs/               Sample building/energy docs for Foundry IQ grounding
docs/                      Foundry agent + SRE Agent runbooks
.devcontainer/             Dev environment (no Docker-in-Docker)
```

## Notes

- **Managed identity upstream** — the backend authenticates to Foundry, the Foundry
  project authenticates to Azure AI Search, and AI Gateway authenticates to its
  model provider with managed identity. Direct gateway clients use a runtime key;
  its value is never emitted as a Bicep output.
- **SRE Agent** is provisioned in Bicep (`Microsoft.App/agents`) with a scoped
  identity, Action Group, and backend metric alert; only the GitHub connector and
  incident subagent/runbook are configured post-provision (data plane).
- **The Agent 365 governance plane and automated regression mechanic** remain demo
  talking points rather than components of this scaffold.

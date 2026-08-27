# BuildingAssist — demo scaffold

Environment for the 60-minute demo **"A Developer's Day on the Microsoft Agentic
Platform"** (customer: *Contoso Energy*). The app is a deliberately thin **Smart
Building assistant**: a user can ask what is special about a site, inspect simulated
current conditions, and request a bounded operation. A **Microsoft Foundry agent**
combines **Model Router**, a **Foundry IQ Knowledge Base**, and **MCP** tools.

> Full demo narrative and run-sheet: [.github/instructions.md](.github/instructions.md).
> Build plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Architecture

```
Frontend Container App (TypeScript SPA)
   └─ HTTP ─▶ Backend Container App (FastAPI)
            ├─ Responses API ─▶ BuildingAssist prompt agent
            │                    ├─ Model Router (Balanced)
            │                    ├─ Foundry IQ Knowledge Base MCP (Azure AI Search)
            │                    └─ Building operations MCP (simulated telemetry)
            └─ /mcp/ ─▶ read tools + approval-gated simulated actions
Supporting: APIM AI Gateway, ACR, Log Analytics + App Insights traces, Container Apps env, RBAC
SRE Agent (Microsoft.App/agents, in Bicep) ─ watches: both Container Apps, Foundry, APIM ─▶ GitHub issues
```

- **Backend** — Python 3.12 / FastAPI, Azure AI Projects SDK, managed identity
  (`DefaultAzureCredential`). Deps via **uv**. See [src/backend](src/backend).
- **Frontend** — TypeScript SPA (Vite + React), served by nginx. Deps via **npm**
  through an **Azure Artifacts** feed (see `src/frontend/.npmrc`). The backend URL
  is injected at container start (runtime `config.js`). See [src/frontend](src/frontend).
- **Infra** — `azd` + Bicep. Two Azure Container Apps; images built **remotely by
  ACR** (no local Docker). See [infra](infra).
- **Knowledge** — Azure AI Search Basic hosts the GA Foundry IQ Knowledge Base;
  four Markdown sources are chunked and indexed idempotently after provision.
- **Tracing** — the Foundry project is connected to workspace-based Application
  Insights for automatic prompt-agent traces. The backend adds correlated
  OpenTelemetry spans with prompt and tool content recording disabled.

## Prerequisites

- The provided **`.devcontainer`** (Python 3.12 + uv, Node 22 + npm, azd, Azure CLI,
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
# → http://localhost:8000/healthz, POST /ask, and MCP at /mcp/
```

Frontend (Vite dev server; proxies /api to the backend on :8000):

```bash
cd src/frontend
npm install                   # pulls deps through the Azure Artifacts feed
npm run dev                   # → http://localhost:5173
```

> The feed in `src/frontend/.npmrc` requires auth. On Linux/CI use the Azure
> Artifacts Credential Provider (or generate npm credentials in the portal) to
> write a token into your **user-level** `~/.npmrc` — never the repo.

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
the Foundry IQ Knowledge Base, the MCP endpoint, the visible prompt agent, and an
Application Insights project connection. It also outputs the app, Foundry, Search,
Application Insights, and APIM resource details.

The prompt agent is closed-book: every factual response requires an MCP tool call.
Unsupported or incomplete requests return exactly `i don't know`; model knowledge is
never used as a fallback. The operations MCP server separates portfolio discovery,
building information, and current building data into distinct tools.

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
backend 5xx metric alert are **provisioned by Bicep**. After `azd up`, finish the
data-plane setup (GitHub connector + incident subagent/runbook) and rehearse the
staged regression: [docs/sre-agent.md](docs/sre-agent.md).

## Demo run-sheet (maps to the one-hour beats)

| Time | Beat | What to show | Pillar |
|---|---|---|---|
| 0:05–0:17 | **Write** | Copilot agent mode builds the `/ask` feature (this repo) | 🟦 Copilot |
| 0:17–0:31 | **Reason** | Model Router + Foundry IQ retrieval + MCP read/action approval | 🟩 Foundry |
| 0:31–0:38 | **Operate** | SRE Agent config — resources watched, GitHub link | 🟧 SRE Agent |
| 0:38–0:48 | **Diagnose** | Trigger the staged regression → SRE Agent RCA → GitHub issue | 🟧 SRE Agent |
| 0:48–0:57 | **Fix** | Assign issue → Copilot coding agent PR → **review & merge** → redeploy | 🟦 Copilot (HITL) |
| 0:57–1:00 | **Close** | One platform, governed (APIM AI Gateway + Agent 365) | — |

The staged regression and its revert are in [docs/sre-agent.md](docs/sre-agent.md#5-the-staged-regression-failure-lever).

## Teardown

```bash
azd down --purge --force
```

Delete the SRE Agent separately (it's provisioned outside this repo's Bicep).

## Repository layout

```
azure.yaml                 azd project (two ACA services, ACR remote build)
infra/                     Bicep: main + modules (monitoring, registry, identity,
                           apps-env, foundry, search, apim, container-app, rbac, sre-agent)
scripts/                   postprovision hook + Foundry IQ / prompt-agent setup
src/backend/               FastAPI service (uv)
src/frontend/              Vite + React SPA (TypeScript, npm via Azure Artifacts)
sample-docs/               Sample building/energy docs for Foundry IQ grounding
docs/                      Foundry agent + SRE Agent runbooks
.devcontainer/             Dev environment (no Docker-in-Docker)
```

## Notes

- **Managed identity everywhere** — no keys in the app; the backend authenticates
  to Foundry IQ, the Foundry project connection authenticates to Azure AI Search,
  and APIM authenticates to the model.
- **SRE Agent** is provisioned in Bicep (`Microsoft.App/agents`) with a scoped
  identity, Action Group, and backend metric alert; only the GitHub connector and
  incident subagent/runbook are configured post-provision (data plane).
- **CI/CD, the Agent 365 governance plane, and the automated regression mechanic**
  are intentionally out of scope for this scaffold (talking points in the demo).

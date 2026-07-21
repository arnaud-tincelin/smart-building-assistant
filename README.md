# BuildingAssist — demo scaffold

Environment for the 60-minute demo **"A Developer's Day on the Microsoft Agentic
Platform"** (customer: *Contoso Energy*). The app is a deliberately thin **Smart
Building assistant**: a user asks *"How much energy did Floor 3 use this week?"* and
an **Azure AI Foundry agent** answers, grounded via **Foundry IQ**. The platform is
the star — the agents at each lifecycle stage act *around* this app.

> Full demo narrative and run-sheet: [.github/instructions.md](.github/instructions.md).
> Build plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Architecture

```
Frontend Container App (TypeScript SPA)
   └─ HTTP ─▶ Backend Container App (FastAPI)
                 └─ managed identity ─▶ APIM AI Gateway ─▶ Azure OpenAI model (in Foundry)
                 └─ Azure AI Projects SDK ─▶ Foundry Agent ─▶ Foundry IQ knowledge (sample docs)
Supporting: ACR (remote image builds), Log Analytics + App Insights, Container Apps env, RBAC
SRE Agent (Microsoft.App/agents, in Bicep) ─ watches: both Container Apps, Foundry, APIM ─▶ GitHub issues
```

- **Backend** — Python 3.12 / FastAPI, Azure AI Projects SDK, managed identity
  (`DefaultAzureCredential`). Deps via **uv**. See [src/backend](src/backend).
- **Frontend** — TypeScript SPA (Vite + React), served by nginx. Deps via **npm**
  through an **Azure Artifacts** feed (see `src/frontend/.npmrc`). The backend URL
  is injected at container start (runtime `config.js`). See [src/frontend](src/frontend).
- **Infra** — `azd` + Bicep. Two Azure Container Apps; images built **remotely by
  ACR** (no local Docker). See [infra](infra).

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
# → http://localhost:8000/healthz  and  POST /ask
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

`azd up` outputs the backend/frontend URLs, the Foundry project endpoint, and the
APIM gateway URL. The frontend container reads the backend URL at start via the
`BACKEND_URL` env var (rendered into `config.js`).

### Create the Foundry agent (azd AI agent extension)

The demo's **Foundry agent** is a hosted agent created and deployed with the
[azd AI agent extension](https://learn.microsoft.com/azure/developer/azure-developer-cli/extensions/azure-ai-foundry-extension).
It lives in its own self-contained azd project under [agent/](agent) (host
`azure.ai.agent`, `infra: microsoft.foundry`) and is grounded on the Foundry IQ
knowledge via Responses `file_search`:

```bash
cd agent
azd env new agent-dev --subscription <sub> --location eastus2
azd up
azd ai agent invoke buildingassist-agent "How much energy did Floor 3 use this week?"
```

See [agent/README.md](agent/README.md) for the one-time grounding RBAC step. The
backend app can also answer directly from the Foundry project's model + Foundry IQ
knowledge (Responses API) — the knowledge vector store is provisioned by the
`postprovision` hook ([scripts/setup_foundry_knowledge.py](scripts/setup_foundry_knowledge.py)),
and a portal/CLI walkthrough is in [docs/foundry-agent.md](docs/foundry-agent.md).

### Attach the Azure SRE Agent (operate pillar)

The SRE Agent (`Microsoft.App/agents`), its scoped identity, an Action Group, and a
backend 5xx metric alert are **provisioned by Bicep**. After `azd up`, finish the
data-plane setup (GitHub connector + incident subagent/runbook) and rehearse the
staged regression: [docs/sre-agent.md](docs/sre-agent.md).

## Demo run-sheet (maps to the one-hour beats)

| Time | Beat | What to show | Pillar |
|---|---|---|---|
| 0:05–0:17 | **Write** | Copilot agent mode builds the `/ask` feature (this repo) | 🟦 Copilot |
| 0:17–0:31 | **Reason** | The Foundry agent + playground; grounded answer with citations | 🟩 Foundry |
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
                           apps-env, foundry, apim, container-app, rbac, sre-agent)
agent/                     Foundry hosted agent (azd AI agent extension)
scripts/                   postprovision hook + Foundry IQ knowledge setup
src/backend/               FastAPI service (uv)
src/frontend/              Vite + React SPA (TypeScript, npm via Azure Artifacts)
sample-docs/               Sample building/energy docs for Foundry IQ grounding
docs/                      Foundry agent + SRE Agent runbooks
.devcontainer/             Dev environment (no Docker-in-Docker)
```

## Notes

- **Managed identity everywhere** — no keys in the app; APIM authenticates to the
  model with its own managed identity.
- **SRE Agent** is provisioned in Bicep (`Microsoft.App/agents`) with a scoped
  identity, Action Group, and backend metric alert; only the GitHub connector and
  incident subagent/runbook are configured post-provision (data plane).
- **CI/CD, the Agent 365 governance plane, and the automated regression mechanic**
  are intentionally out of scope for this scaffold (talking points in the demo).

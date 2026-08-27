# Implementation Plan — BuildingAssist Demo Scaffold

## Problem & goal

Build the environment for the 60-minute demo *"A Developer's Day on the Microsoft
Agentic Platform"* (customer: Contoso Energy), as specified in
`.github/instructions.md`.

Deliver a **thin BuildingAssist app** plus the **Azure infrastructure** the demo's
agents act on, all provisioned with **AZD + Bicep** and developed inside a
**`.devcontainer`**. The app is a **two-service** design:

- **Backend** — Python (FastAPI), calls the Foundry agent.
- **Frontend** — TypeScript (single-page web UI) that calls the backend.

Both services are deployed as separate **Azure Container Apps**. Container images
are built **remotely by ACR** (via `azd` / `az acr build`) — **no local Docker /
Docker-in-Docker**.

**In scope (confirmed with user):**
- Demo scaffold = infra + app.
- Azure SRE Agent (as the operate pillar) — now **first-class in Bicep**
  (`Microsoft.App/agents`), provisioned by our infra and pointed at the resources
  our Bicep deploys. GitHub issue connector + incident runbook/subagent are
  configured post-provision in the agent Builder (data plane).
- Optional beats **included**: APIM AI Gateway (model-call governance) and
  Foundry IQ grounding (RAG on sample building/energy docs).

**Out of scope (confirmed with user):**
- CI/CD pipeline.
- The staged regression mechanic.
- Agent 365 governance plane.

## Target stack

- **Backend:** Python 3.12, FastAPI, Azure AI Projects SDK (Foundry Agent Service),
  `azure-identity` managed identity (`DefaultAzureCredential`). Dependencies and
  virtualenv managed with **uv** (`pyproject.toml` + `uv.lock`). Lives in
  `src/backend`.
- **Frontend:** TypeScript SPA (Vite + React) served as static assets; talks to the
  backend over HTTP. Deps managed with **npm** (`package.json`). Lives in
  `src/frontend`.
- **IaC:** Azure Developer CLI (`azd`) + Bicep modules.
- **Hosting:** two **Azure Container Apps** (backend + frontend). Images built by
  **ACR remote build** through `azd` — no local Docker daemon.
- **AI:** Microsoft Foundry project + Model Router; a Foundry IQ Knowledge Base on
  Azure AI Search; a prompt agent with simulated operations through MCP.
- **Observability:** workspace-based Application Insights connected to the Foundry
  project for automatic server-side agent traces, plus correlated backend
  OpenTelemetry spans with content recording disabled.
- **Gateway:** Azure API Management with GenAI/AI-Gateway policies in front of the
  model endpoint.
- **Operate:** Azure SRE Agent (`Microsoft.App/agents`) provisioned in Bicep, with a
  scoped managed identity, an Action Group, and a metric alert on the backend.
- **Dev env:** `.devcontainer` with Python 3.12 + **uv**, Node 22 + **npm**, azd,
  Bicep, Azure CLI. **No Docker-in-Docker** (ACR remote build instead).

## Architecture (what Bicep provisions)

```
Frontend Container App (TypeScript SPA)
   └─ HTTP ─▶ Backend Container App (FastAPI)
                 └─ managed identity ─▶ APIM AI Gateway ─▶ Azure OpenAI model (in Foundry)
                 └─ Responses API ─▶ prompt agent ─▶ Model Router + Foundry IQ KB + operations MCP
Supporting: ACR (remote image builds), Log Analytics + App Insights, Container Apps env, RBAC
SRE Agent (Microsoft.App/agents, in Bicep) ─ watches: both Container Apps, Foundry, APIM ─▶ GitHub issues
```

## Todos (high level)

1. **devcontainer** — `.devcontainer/devcontainer.json` + features: Python 3.12 +
   **uv**, Node 22 + **npm**, azd, az CLI, Bicep. **No Docker-in-Docker**;
   post-create runs `uv sync` (backend) and `npm install` (frontend).
2. **app-skeleton** — FastAPI **backend** (`src/backend`): `/healthz` + `/ask`
   endpoint (energy question → Foundry agent answer with sources); CORS for the
   frontend; config via env vars; deps in `pyproject.toml` managed by **uv**.
3. **app-foundry-client** — Azure AI Projects SDK client using
   `DefaultAzureCredential`; call the Foundry agent, thread/run, return answer +
   citations from Foundry IQ.
4. **frontend** — TypeScript SPA (`src/frontend`, Vite + React): a single input to
   ask the energy question, renders the answer + source citations from the backend;
   backend URL via build/runtime env var.
5. **app-dockerfile** — production Dockerfiles for **both** services (backend: uv
   build + uvicorn; frontend: node build → static serve) + `.dockerignore`. Built
   remotely via ACR (no local Docker).
6. **app-local-test** — sample docs, local run instructions (backend + frontend),
   minimal pytest for the endpoint (mock the Foundry client).
7. **azd-scaffold** — `azure.yaml` wiring **two** ACA services (backend, frontend)
   to Bicep infra, using ACR remote build (`docker.remoteBuild` / host build).
8. **bicep-core** — `infra/main.bicep` (+ `main.parameters.json`): resource group
   scope, Log Analytics, App Insights, ACR, Container Apps env, user-assigned MI.
9. **bicep-foundry** — Azure AI Foundry account/project, model deployment, agent,
   Foundry IQ knowledge resource + sample-doc grounding.
10. **bicep-apim** — APIM instance + AI-Gateway policies (token limit, load-balance,
    retries, managed-identity auth) fronting the model endpoint.
11. **bicep-containerapp** — **two** Container Apps (backend + frontend) consuming
    ACR images; backend env vars (APIM URL, Foundry IDs) + MI; frontend env var
    (backend URL) + external ingress.
12. **bicep-rbac** — role assignments: MI → Foundry (Azure AI User), MI → ACR pull,
    MI → APIM subscription/identity as needed.
13. **bicep-sre-agent** — Azure SRE Agent (`Microsoft.App/agents`) + scoped system
  and user-assigned identities (Reader/Monitoring Reader on the RG, Log Analytics
  Reader on the workspace) + Action Group + backend 5xx metric alert.
14. **sre-agent-doc** — `docs/` runbook: the agent is provisioned by Bicep; document
    the post-provision data-plane steps (GitHub connector, incident subagent/runbook)
    and the staged regression + revert.
15. **readme** — `README.md`: prereqs, `azd up`, demo run-sheet mapping to the
    instructions' one-hour beats, teardown.
16. **validate** — `azd provision`/`up` dry validation, `bicep build`/lint, backend
    boots + frontend builds locally in the devcontainer.

## Notes & considerations

- **Foundry IQ knowledge** is provisioned idempotently by `setup_foundry_iq.py` as
  an Azure AI Search index, knowledge source, and GA Knowledge Base. The root app and
  prompt agent consume its authenticated MCP endpoint.
- **SRE Agent is first-class in Bicep** (`Microsoft.App/agents`, API `2026-01-01`) —
  provisioned by our infra with its own scoped identity, an Action Group, and a
  backend metric alert. Only the GitHub issue connector and the incident
  subagent/runbook are configured post-provision in the agent Builder (data plane),
  because `GitHub` is not a valid ARM `dataConnectorType`.
- **Region:** pick one where Foundry Agent Service, APIM, ACA, and SRE Agent all
  exist (e.g. Sweden Central / East US 2) — confirm at build time.
- **Managed identity everywhere** — no keys in the app; APIM uses MI to the model.
- **Foundry IQ / Agent Service Bicep surface is evolving** — if a resource type
  isn't yet GA in Bicep, fall back to an `azd` post-provision hook (az CLI / SDK)
  and document it. Flag this during bicep-foundry.
- **ACR remote build (no local Docker):** `azd` builds images server-side. Ensure
  each service in `azure.yaml` uses host/remote build (`docker: { remoteBuild: true }`)
  so the devcontainer needs no Docker daemon.
- Keep the app deliberately thin per the instructions ("the platform is the star").
```

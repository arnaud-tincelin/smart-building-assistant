# BuildingAssist — Foundry prompt agent

The Foundry **account**, **project**, and **model deployment** are provisioned by
Bicep (`infra/modules/foundry.bicep`). The **prompt agent** is created
post-provision from the azd `postprovision` hook, because the agent data plane is
still evolving in Bicep.

## What the deployment creates

`azd up` runs [`scripts/postprovision.sh`](../scripts/postprovision.sh), which calls
[`scripts/setup_foundry_agent.py`](../scripts/setup_foundry_agent.py) to create
(idempotently, by name) a Foundry **prompt agent** — a *prompt agent* is just a model
deployment + instructions, with no custom container code:

- **Name:** `buildingassist-agent` (override with `BUILDINGASSIST_AGENT_NAME`)
- **Model:** the deployment Bicep created (`gpt-4.1-mini`, from
  `AZURE_AI_MODEL_DEPLOYMENT_NAME`)
- **Instructions:** the BuildingAssist system prompt

After `azd up` you should see `buildingassist-agent` under **Agents** in your
Foundry project, and you can test it in the **playground**.

> **Prompt vs hosted:** the azd AI agents extension (`host: azure.ai.agent`) deploys
> *hosted* (container/code) agents. A *prompt* agent has no code, so it's created via
> the Foundry SDK from the post-provision hook rather than by the azd extension.

## Re-running / updating

The setup is idempotent — re-running `azd up` reuses the existing agent and only
registers a new version when the model or instructions change. To create/update it
manually against an already-provisioned environment:

```bash
AZURE_AI_PROJECT_ENDPOINT="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT)" \
AZURE_AI_MODEL_DEPLOYMENT_NAME="$(azd env get-value AZURE_AI_MODEL_DEPLOYMENT_NAME)" \
  sh -c 'cd src/backend && uv run python ../../scripts/setup_foundry_agent.py'
```

## Step 2 — Foundry IQ grounding (later)

Grounding the agent on the sample building/energy docs is the next step. It adds a
`file_search` tool over a vector store built from [`sample-docs/`](../sample-docs) by
[`scripts/setup_foundry_knowledge.py`](../scripts/setup_foundry_knowledge.py), then
attaches that tool to the prompt agent's definition so answers carry citations.

## Notes

- The backend authenticates with the user-assigned managed identity
  (`DefaultAzureCredential`) — no keys. RBAC (Azure AI User) is granted by
  `infra/modules/rbac.bicep`.
- SDK/CLI reference: [Azure AI Projects SDK docs](https://learn.microsoft.com/azure/ai-foundry/).

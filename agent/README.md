# BuildingAssist Foundry agent (azd AI agent extension)

The **Reason** pillar of the demo: a Microsoft Foundry **hosted agent** created and
deployed with the [azd AI agent extension](https://learn.microsoft.com/azure/developer/azure-developer-cli/extensions/azure-ai-foundry-extension).
It answers Contoso Energy building-energy questions and is grounded on the Foundry
IQ knowledge (a vector store of the sample docs) via the Responses `file_search` tool.

This is a **self-contained azd project** (its own [azure.yaml](azure.yaml) with
`infra: provider: microsoft.foundry`), separate from the app in the repo root — the
hosted-agent runtime provisions its own Foundry account + capability host, which the
bicep-based app project can't express.

## Layout

```
azure.yaml                         # hosted agent + model deployment (microsoft.foundry)
src/buildingassist-agent/main.py   # Responses-protocol agent (azure-ai-agentserver-responses)
```

## Prerequisites

- `azd` ≥ 1.27 and the extension: `azd extension install azure.ai.agents`
- `azd auth login`

## Deploy

```bash
cd agent
azd env new agent-dev --subscription <sub> --location eastus2
azd up            # provisions the Foundry account/project/model + deploys the agent
```

> **Grounding RBAC (one-time):** the hosted agent runs under a dedicated runtime
> managed identity that needs the **Foundry User** role on the project to read the
> knowledge vector store. Grant it (find the object id in the agent logs' 403 if
> needed), plus provision the knowledge on this project:
>
> ```bash
> # From the repo root, create the knowledge on this agent's project:
> AZURE_AI_PROJECT_ENDPOINT="$(azd -C agent env get-value FOUNDRY_PROJECT_ENDPOINT)" \
>   SAMPLE_DOCS_DIR="$PWD/sample-docs" \
>   sh -c 'cd src/backend && uv run python ../../scripts/setup_foundry_knowledge.py'
> ```

## Operate

```bash
azd ai agent show buildingassist-agent
azd ai agent invoke buildingassist-agent "How much energy did Floor 3 use this week?"
azd ai agent monitor buildingassist-agent      # stream logs
azd ai agent run                               # run locally against remote resources
```

The `azd up`/`deploy` output prints the **Foundry playground** URL and the agent's
**Responses endpoint** — both usable in the demo's *Reason* beat.

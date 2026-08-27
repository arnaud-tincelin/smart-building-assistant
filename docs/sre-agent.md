# Azure SRE Agent — Bicep-provisioned, plus data-plane setup

The Azure SRE Agent is the **operate** pillar of the demo and is now **first-class in
Bicep** (`Microsoft.App/agents@2026-01-01`). Our infra
([infra/modules/sre-agent.bicep](../infra/modules/sre-agent.bicep)) provisions:

- the **SRE Agent** itself (autonomous mode, Anthropic default model);
- **SRE Agent Administrator** on the agent for the deployment principal, so the
  portal and Builder data plane can load;
- **system-assigned and user-assigned identities**, both scoped with **Reader** +
  **Monitoring Reader** on the resource group and **Log Analytics Reader** on the
  workspace — so the current runtime can list watched resources (both Container
  Apps, Foundry, APIM), use workspace tools, and run KQL;
- persistent **Application Insights** and **Log Analytics** connectors backed by
  the system-assigned identity;
- an **Action Group** as the incident entry point;
- a **metric alert** on the backend Container App (5xx responses) that fires the
  staged regression into the agent.

So after `azd up` the agent already exists, watches the resource group, and has its
logs connected. Only two things remain — both in the **agent Builder (data plane)**:

1. the **GitHub connector** (open issues / PRs), and
2. the **incident-handler subagent + runbook**.

> Rehearse the regression until it reproduces reliably, and **record a fallback
> video** — a broken live regression is the number-one demo risk.

## 1. Confirm the agent after `azd up`

```bash
azd env get-value SRE_AGENT_NAME
```

Or open the agent in the Azure Portal (search for its name) to reach the Builder.

## 2. Connect GitHub (data plane, in the agent Builder)

1. Open the SRE Agent → **Builder**.
2. **Code Access** — authorize this repository with GitHub OAuth so the agent can
  read source for RCA. OAuth must be completed once for each newly created agent;
  it can't be deployed through ARM/Bicep.
3. **Connectors → GitHub** — authorize the repo with a PAT that has **Issues:
   Read + Write**, so incident diagnoses land as GitHub issues.

Prefer OAuth for interactive setup. For headless automation, pass a PAT only as an
ephemeral process environment variable; don't persist it in the azd environment.

## 3. Add the incident-handler subagent + runbook (data plane)

In the Builder, create a subagent whose runbook, on a backend-5xx incident:

1. Queries Log Analytics / Application Insights to confirm the root cause (the app
   log line `Foundry agent call failed` and the bad `BUILDINGASSIST_MODEL_DEPLOYMENT`).
2. Correlates it to the recent deploy.
3. Writes a plain-language root cause and **opens a GitHub issue**.

## 4. The staged regression (failure lever)

Keep it routine — "the kind of thing that normally eats an afternoon." The metric
alert Bicep created watches for backend 5xx, so triggering the regression is enough.

**Option A — wrong/expired model deployment (recommended, cleanest):**

```bash
az containerapp update \
  --name <ca-backend-name> \
  --resource-group "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  --set-env-vars BUILDINGASSIST_MODEL_DEPLOYMENT=does-not-exist
```

**Option B — tighten the APIM token limit** so model calls return 429/5xx: edit
[infra/policies/openai-policy.xml](../infra/policies/openai-policy.xml), drop
`tokens-per-minute` to a tiny value, and redeploy APIM.

After the change, ask BuildingAssist a question in the frontend — it starts erroring.
The backend returns 502 → the metric alert fires into the Action Group → the SRE
Agent detects it, reads logs across app + Foundry + APIM, writes a root cause, and
opens a GitHub issue.

## 5. Close the loop (Copilot coding agent)

1. Assign the SRE Agent's issue to the **Copilot coding agent**.
2. It opens a PR with the fix (restore the model name / add a timeout+retry).
3. **You review, approve, merge** — the single human-in-the-loop decision.
4. Redeploy (`azd deploy backend`), and confirm the SRE Agent reports healthy.

## 6. Revert (after rehearsal)

```bash
az containerapp update \
  --name <ca-backend-name> \
  --resource-group "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  --set-env-vars BUILDINGASSIST_MODEL_DEPLOYMENT="$(azd env get-value AZURE_AI_MODEL_DEPLOYMENT)"
```

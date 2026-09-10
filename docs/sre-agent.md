# Azure SRE Agent — two failure classes, two repair paths

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
- **Container Apps Contributor** for the action identity on the backend Container
  App only — not the resource group — so it can repair the one deployment setting
  used by scenario 2 without modifying the frontend or other Azure resources;
- persistent **Application Insights** and **Log Analytics** connectors backed by
  the system-assigned identity;
- an **Action Group** as the incident entry point;
- two non-overlapping trace alerts: `security-5xx` for the HTTP 500 code defect
  and `config-availability` for the HTTP 503 deployment fault.

After `azd up`, the agent watches the resource group, has its logs connected, and
the post-provision hook creates two deliberately separated paths:

| Failure class | Handler | Capability | Outcome |
|---|---|---|---|
| Security HTTP 500, code defect | `security-incident-handler` | Telemetry + GitHub; no Azure writes | Deduplicated GitHub repair issue |
| Operations HTTP 503, bad deployment config | `platform-config-operator` | Telemetry + scoped Azure writes; no GitHub or terminal | Restore the known-good Container App setting |

The platform operator loads
[`repair-buildingassist-operations-config`](../sre-config/skills/repair-buildingassist-operations-config.md)
only for the config alert. GitHub OAuth requires one interactive consent for each
newly created agent; rerun `azd provision` after consenting so the hook can attach
and test Code Access for scenario 1.

> Rehearse the regression until it reproduces reliably, and **record a fallback
> video** — a broken live regression is the number-one demo risk.

## 1. Confirm the agent after `azd up`

```bash
azd env get-value SRE_AGENT_NAME
```

Or open the agent in the Azure Portal (search for its name) to reach the Builder.

## 2. Connect GitHub once

1. Open the SRE Agent → **Builder**.
2. **Code Access** — authorize this repository with GitHub OAuth so the agent can
  read source for RCA. OAuth must be completed once for each newly created agent;
  it can't be deployed through ARM/Bicep.
3. Rerun `azd provision`. `scripts/setup_sre_agent.py` attaches and tests the
  current repository, uploads the repair skill, creates both handlers, and
  configures both response plans.

## 3. Verify the incident workflow

In the Builder, verify:

1. **Code Access** lists `smart-building-assistant` and its connection test passes.
2. **Connectors** lists `app-insights` and `log-analytics`.
3. **Skills** lists `repair-buildingassist-operations-config`.
4. **Custom agents** lists `security-incident-handler` and
  `platform-config-operator`.
5. **Incident response plans** lists `building-security-5xx` routed by
  `security-5xx` and `building-config-availability` routed by
  `config-availability`.
6. The platform operator has `RunAzCliWriteCommands` but no GitHub or terminal
  tools. The security handler does not have `RunAzCliWriteCommands`.

## 4. Scenario 1: code defect to coding-agent handoff

1. Open the deployed frontend and select **Security & access**.
2. Under **Employee access**, keep **Badge** selected and choose **Request access**.
3. Show the HTTP 500 message and copy the `SEC-` incident ID. Optionally repeat with
  **Mobile** or **Visitor check-in** to prove the shared failure.
4. Wait for `alert-security-5xx-*` to fire. It evaluates every minute over a
  five-minute window and enters the SRE Agent through Azure Monitor.
5. Open the incident thread. The `security-incident-handler` correlates the alert
  with Application Insights, finds `Security control operation failed`, inspects
  the connected source, and creates one GitHub issue after checking for duplicates.

Expected issue title:

```text
[SRE] Building access operations return HTTP 500
```

## 5. Close scenario 1 with the Copilot coding agent

1. Assign the SRE Agent's issue to the **Copilot coding agent**.
2. It opens a PR that aligns the security audit-event timestamp contract and updates
  the regression tests to require successful badge, mobile, and visitor responses.
3. **You review, approve, merge** — the single human-in-the-loop decision.
4. Redeploy the backend and frontend, repeat the same UI action, and show the success
  reference instead of a 500.
5. Confirm the Azure Monitor alert resolves and close the GitHub issue.

## 6. Scenario 2: bad deployment config to autonomous repair

Start from a healthy backend, then inject a configuration-only revision:

```bash
scripts/demo/break-config.sh
```

The script sets `BUILDINGASSIST_OPERATIONS_SOURCE=digital-twins-prod`, leaves the
container image unchanged, and calls `/healthz` once. The backend logs
`CONFIG_ERROR` and returns HTTP 503, which triggers `alert-config-availability-*`
as a Sev1 incident.

Open the frontend URL printed by the script, select **Security & access**, and
request employee access. The UI shows **503 · Access service unavailable** with a
deployment-configuration message and no `SEC-` ID. This visibly distinguishes the
platform fault from scenario 1's exception-backed HTTP 500.

In the incident thread, show the `platform-config-operator`:

1. Separating the 503 plus `CONFIG_ERROR` traces from the exception-backed 500.
2. Reading the live Container App environment and the `simulator` baseline from
  its repair skill.
3. Correlating the new revision with the Container App write in Activity Log.
4. Running only this authorized repair:

  ```bash
  az containerapp update --resource-group <resource-group> --name <backend-app> \
    --set-env-vars BUILDINGASSIST_OPERATIONS_SOURCE=simulator
  ```

5. Verifying the new revision is healthy and no new 503s appear. It must not open
  a GitHub issue or change source, image, ingress, scale, traffic, secrets,
  identities, or any other environment variable.

Confirm recovery from the operator terminal:

```bash
curl "$(azd env get-value SERVICE_BACKEND_URL)/healthz"
```

Expected response:

```json
{"status":"ok"}
```

## 7. Reset for another rehearsal

If the agent has not repaired scenario 2, or to establish a known-good baseline:

```bash
scripts/demo/fix-config.sh
```

Redeploy the intentionally broken demo revision before the next rehearsal. Avoid
repeatedly triggering the action while an alert is active; duplicate requests add
noise to the incident timeline.

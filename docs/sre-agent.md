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

After `azd up`, the agent watches the resource group, has its logs connected, and
the post-provision hook creates the `security-incident-handler` plus the
`building-security-5xx` Sev2 response plan. GitHub OAuth requires one interactive
consent for each newly created agent; rerun `azd provision` after consenting so the
hook can attach and test Code Access.

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
  current repository, then configures the response plan.

## 3. Verify the incident workflow

In the Builder, verify:

1. **Code Access** lists `smart-building-assistant` and its connection test passes.
2. **Connectors** lists `app-insights` and `log-analytics`.
3. **Custom agents** lists `security-incident-handler`.
4. **Incident response plans** lists the enabled `building-security-5xx` plan for
  Azure Monitor Sev2.

## 4. Trigger the security regression

1. Open the deployed frontend and select **Security & access**.
2. Under **Employee access**, keep **Badge** selected and choose **Request access**.
3. Show the HTTP 500 message and copy the `SEC-` incident ID. Optionally repeat with
  **Mobile** or **Visitor check-in** to prove the shared failure.
4. Wait for `alert-backend-5xx-*` to fire. It evaluates every minute over a
  15-minute window and enters the SRE Agent through the Azure Monitor incident
  platform.
5. Open the incident thread. The `security-incident-handler` correlates the alert
  with Application Insights, finds `Security control operation failed`, inspects
  the connected source, and creates one GitHub issue after checking for duplicates.

Expected issue title:

```text
[SRE] Building access operations return HTTP 500
```

## 5. Close the loop (Copilot coding agent)

1. Assign the SRE Agent's issue to the **Copilot coding agent**.
2. It opens a PR that aligns the security audit-event timestamp contract and updates
  the regression tests to require successful badge, mobile, and visitor responses.
3. **You review, approve, merge** — the single human-in-the-loop decision.
4. Redeploy the backend and frontend, repeat the same UI action, and show the success
  reference instead of a 500.
5. Confirm the Azure Monitor alert resolves and close the GitHub issue.

## 6. Reset for another rehearsal

Redeploy the intentionally broken demo revision before the next rehearsal. Avoid
repeatedly triggering the action while an alert is active; the SRE Agent merges
recurring Azure Monitor alerts into one incident thread.

# Chat-Led Configuration Repair Demo

## What This Demonstrates

A script introduces a bad backend configuration. The presenter reports the
symptom in **Azure SRE Agent chat**, the agent investigates, the presenter approves
the proposed repair, and the agent restores service using an Azure configuration
update. Neither the break nor the repair changes the container image.

The existing Security & access code-defect/GitHub issue scenario remains separate.
Do not trigger it during this rehearsal. No new automatic response plan is added.

## Prepare Once, Before Rehearsal

These changes must be deployed before running the break command. Local tests do
not configure the live agent or prove that its preview tools can execute a repair.

1. Review and validate the infrastructure changes and backend image. Keep the
   healthy `BUILDINGASSIST_OPERATIONS_SOURCE=simulator` configuration at deployment.
   No frontend update is needed: its existing error display shows the failure.
2. Opt in to repair using `SRE_ENABLE_CONFIG_REPAIR=true` in the selected AZD
   environment, then use the approved provisioning/deployment workflow. The Bicep
   parameter `enableSreConfigRepair` defaults to false. Do not run an unreviewed
   full provision just to change this demo in an otherwise dirty worktree.
3. Verify the custom repair role assignments at the **backend Container App**
   scope for both SRE identities. It adds read/write/revision-read, not delete,
   role-assignment, or listSecrets permissions. Existing monitoring access remains.
4. The postprovision hook applies the chat playbook and security-handler guard.
   To refresh only these after infrastructure is ready, run the command below
   from the repository root. It does not reconfigure response plans or GitHub.
5. In the SRE portal, inspect the installed main-chat custom instructions, tools
   and approval controls. Use native write-operation approval where available;
   the playbook requires explicit approval in the same chat before any repair.
   A tool roster entry alone does not prove effective permissions or approvals.
6. Verify the backend is ready and supports the capability header using `status`.
   Rehearse the complete chat flow before presenting, and record a fallback video.

Scoped chat-setup refresh (changes SRE data-plane instructions, not the app):

```powershell
$environment = 'buildingassist-demo'
$names = @(
    'AZURE_SUBSCRIPTION_ID', 'AZURE_RESOURCE_GROUP', 'SRE_AGENT_NAME',
    'SERVICE_BACKEND_RESOURCE_ID', 'SERVICE_BACKEND_URL', 'SRE_CONFIG_REPAIR_ENABLED'
)
foreach ($name in $names) {
    $value = azd env get-value $name --environment $environment
    if ($LASTEXITCODE -ne 0) { throw "Missing deployment output: $name" }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
uv run --frozen --project src/backend python scripts/setup_sre_agent.py --chat-config-only
if ($LASTEXITCODE -ne 0) { throw 'SRE chat setup failed.' }
```

The setup preserves unrelated custom instructions using a managed block, validates
the target and required tools, and verifies the instructions by reading them back.
Unknown preview API response schemas fail rather than overwriting existing text.
GitHub OAuth is not required for this configuration-only chat scenario.

## 1. Check and Break

Prerequisites: authenticated `az` and `azd`, `uv`, a deployed demo-capable backend,
and Single revision mode. Run from the repository root. Scripts do not call
listSecrets or print raw environment arrays. The app URL and subscription come from the explicitly named AZD
environment and are checked against the live app.

```powershell
./scripts/demo-config.ps1 -Action status -Environment buildingassist-demo
./scripts/demo-config.ps1 -Action break -Environment buildingassist-demo
```

The second command is a **dry run**. Review the displayed resource ID, then
deliberately inject the fault:

```powershell
./scripts/demo-config.ps1 -Action break -Environment buildingassist-demo -Apply
```

Bash equivalent:

```bash
bash scripts/break-config.sh --environment buildingassist-demo
bash scripts/break-config.sh --environment buildingassist-demo --apply
```

The script sets only `BUILDINGASSIST_OPERATIONS_SOURCE=bms-prod`. It requires a
healthy preflight with `X-Operations-Config: v1`, preserves unrelated configuration,
and performs a read-only probe after the rollout. An older image is refused.
No work order, HVAC, access, visitor, or model call is made by the script.

If exit code 2 reports a pending rollout, the setting **has changed**. Run `status`
after rollout completes; do not repeat `break` or assume nothing happened.
Any failure after the update may leave the fault active: use the reset below.

## 2. Show the Symptom

In BuildingAssist, ask `List the Contoso buildings.` in either Foundry or AI Gateway
mode. The UI displays `Building operations unavailable: configuration_error` and
a `CFG-` reference. Both modes fail before spending model tokens.

Building API requests return 503 too. `/healthz` intentionally stays 200 so the
bad revision can become ready. It is a liveness check, not a functional test.
Existing security routes are unchanged and retain their separate staged defect.

## 3. Ask SRE Chat to Investigate

Open a **new chat with the main Azure SRE Agent**, not the security incident
subagent. Do not give it the bad setting or paste the fault script output first.

> BuildingAssist is failing. Investigate the backend, check recent changes and
> application logs, and identify the root cause. Show your evidence before making
> changes.

Expected evidence: actual failed requests and `CFG-` references, the revision's
configuration, supported source from logs/runbook, and timing relative to an
Activity Log update. The agent must not infer success from healthz or blindly
reset a setting just because this is a demo.

Logs can take time to ingest. Ask for current revision/console evidence if needed;
do not manufacture a result or treat missing telemetry as proof. The existing
5xx alert may also fire but is not required to initiate this chat. Its security
handler records configuration evidence without opening a code-defect issue or
repairing it automatically.

## 4. Approve and Verify

After the evidence and proposed change are shown, say:

> Apply the configuration fix you proposed and verify that the application works
> again. Preserve all unrelated settings.

The agent should recheck for drift, restore `simulator` with a scoped environment
update, check the serving revision, and verify a successful building-data request.
Then repeat the original question in BuildingAssist to verify the model path too.
Record evidence of both recovery checks; an accepted ARM write alone is not proof.

Configuration changes create new revisions and restart the process. The simulator's
in-memory work orders and temporary changes reset. No real building systems are
controlled by this demo. Historical 5xx alerts may persist until their window expires.

## Manual Reset

```powershell
./scripts/demo-config.ps1 -Action fix -Environment buildingassist-demo -Apply
./scripts/demo-config.ps1 -Action status -Environment buildingassist-demo
```

```bash
bash scripts/fix-config.sh --environment buildingassist-demo --apply
```

Reset restores `simulator`, not a previously captured arbitrary value. Unexpected
values, secret-backed settings, or split traffic require manual inspection.
If the agent lacks effective write permission, use this reset; do not broaden its
role to Owner or Contributor as a troubleshooting shortcut.

## Permissions and Cleanup

Container App write access cannot be restricted by Azure RBAC to one variable.
The playbook's approval and field-preservation rules are behavioral controls, not
field-level enforcement. Use only this disposable demo backend for the scenario.

Setting `SRE_ENABLE_CONFIG_REPAIR=false` stops new conditional assignments, but an
incremental ARM deployment **does not remove existing assignments**. Explicitly
remove the two backend-scoped custom-role assignments to revoke deployed repair
access, then refresh the chat playbook with repair disabled. Verify effective
permissions; unrelated inherited roles are not removed by this feature.
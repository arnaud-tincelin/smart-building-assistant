---
name: repair-buildingassist-operations-config
description: Load this skill when a BuildingAssist alert containing "config-availability" fires, or when the backend returns HTTP 503 with CONFIG_ERROR traces. It confirms an invalid operations provider, correlates the deployment change, restores the one known-good Container App setting, and verifies recovery. Do not load it for HTTP 500 or unhandled exception incidents.
---

# Repair BuildingAssist operations configuration

HTTP 503 with `CONFIG_ERROR` is a deployment configuration fault. The deployed image is
unchanged, so this incident must not create a GitHub issue or request a code change.

## 1. Confirm the outage

```kusto
AppTraces
| where AppRoleName == "buildingassist-backend"
| summarize ConfigurationErrors = countif(Message has "CONFIG_ERROR") by bin(TimeGenerated, 1m)
| order by TimeGenerated desc
```

## 2. Confirm the configuration error

```kusto
AppTraces
| where AppRoleName == "buildingassist-backend"
| where Message has "CONFIG_ERROR"
| order by TimeGenerated desc
| take 20
```

The absence of unhandled exceptions distinguishes this from the security HTTP 500 scenario.
If exceptions are present instead, stop without changing Azure resources.

## 3. Compare live configuration with the baseline

```bash
az containerapp show --resource-group ${RG} --name ${BACKEND_APP} --query "properties.template.containers[0].env[?name=='BUILDINGASSIST_OPERATIONS_SOURCE']" --output table
```

The only supported value is `BUILDINGASSIST_OPERATIONS_SOURCE=simulator`.

## 4. Correlate the deployment change

```bash
az containerapp revision list --resource-group ${RG} --name ${BACKEND_APP} --query "[].{name:name,created:properties.createdTime,active:properties.active,traffic:properties.trafficWeight}" --output table
```

```bash
az monitor activity-log list --resource-group ${RG} --offset 6h --query "[?contains(operationName.value, 'Microsoft.App/containerApps/write')].{time:eventTimestamp,caller:caller,status:status.value}" --output table
```

Report the revision, caller, and timestamp that line up with the first 503.

## 5. Remediate the confirmed fault

```bash
az containerapp update --resource-group ${RG} --name ${BACKEND_APP} --set-env-vars BUILDINGASSIST_OPERATIONS_SOURCE=simulator
```

This is the only authorized write. Do not change the image, ingress, scale, traffic, secrets,
identity, role assignments, or any other environment variable.

## 6. Verify recovery

1. Re-read the environment variable and confirm the value is `simulator`.
2. Confirm the latest revision is healthy, active, and receives 100 percent of traffic.
3. Query `AppTraces` again and verify no new `CONFIG_ERROR` traces appear after the repair.
4. Post the root cause, correlated change, exact repair, and verification evidence to the
   incident thread.
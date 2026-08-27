metadata description = '''
Azure SRE Agent (Microsoft.App/agents) — the operate pillar, now first-class in
Bicep. Provisions the agent with system-assigned and user-assigned identities,
scoped read access to the resource group + Log Analytics, persistent App Insights
and Log Analytics connectors, an Action Group as the incident entry point, and a
metric alert on the backend that fires the staged regression into the agent.

GitHub connection (open issues) and the incident-handler subagent/runbook are still
configured in the agent Builder (data plane) post-provision — see docs/sre-agent.md.
'''

param location string
param tags object
param agentName string
param identityName string
param actionGroupName string
param alertName string

@description('Principal ID that receives SRE Agent Administrator access in the agent portal.')
param developerPrincipalId string

@description('Application Insights AppId — the agent reads traces/logs from here.')
param appInsightsAppId string

@description('Application Insights ARM resource id used by the persistent logs connector.')
param appInsightsResourceId string

@description('Application Insights connection string (required alongside appId).')
@secure()
param appInsightsConnectionString string

@description('Log Analytics workspace name — the agent gets Reader on it to run KQL.')
param logAnalyticsName string

@description('Backend Container App resource id — scope of the regression metric alert.')
param backendAppId string

var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var monitoringReaderRoleId = '43d0d8ad-25c7-4714-9337-8ba259a9fe05'
var logAnalyticsReaderRoleId = '73c42c96-874c-492b-b04d-ab87d138a893'
var sreAgentAdministratorRoleId = 'e79298df-d852-4c6d-84f9-5d13249d1e55'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

// Reader on the resource group: list + describe the watched resources (both
// Container Apps, Foundry, APIM all live in this group).
resource readerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, identity.id, readerRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Monitoring Reader: read Azure Monitor alerts + metrics for correlation.
resource monitoringReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, identity.id, monitoringReaderRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringReaderRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Log Analytics Reader on the workspace: run KQL across app + Foundry + APIM logs.
resource logAnalyticsReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(logAnalytics.id, identity.id, logAnalyticsReaderRoleId)
  scope: logAnalytics
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', logAnalyticsReaderRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Incident platform entry point: the metric alert fires into this action group,
// and the SRE Agent is registered as a receiver on it.
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'sreagent'
    enabled: true
  }
}

resource sreAgent 'Microsoft.App/agents@2026-01-01' = {
  name: agentName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    upgradeChannel: 'Stable'
    knowledgeGraphConfiguration: {
      identity: identity.id
      managedResources: [
        resourceGroup().id
      ]
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: appInsightsAppId
        connectionString: appInsightsConnectionString
      }
    }
    actionConfiguration: {
      identity: identity.id
      mode: 'Autonomous'
      accessLevel: 'High'
    }
    defaultModel: {
      provider: 'Anthropic'
      name: 'Automatic'
    }
    #disable-next-line BCP037 // Supported by SRE Agent but missing from the published Bicep type.
    experimentalSettings: {
      EnableWorkspaceTools: true
      EnableHttpTriggers: true
      EnableV2AgentLoop: true
    }
    incidentManagementConfiguration: {
      type: 'AzMonitor'
      connectionName: 'azmonitor'
    }
  }
}

resource systemReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, sreAgent.id, readerRoleId, 'system-assigned')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)
    principalId: sreAgent.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource systemMonitoringReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, sreAgent.id, monitoringReaderRoleId, 'system-assigned')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringReaderRoleId)
    principalId: sreAgent.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource systemLogAnalyticsReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(logAnalytics.id, sreAgent.id, logAnalyticsReaderRoleId, 'system-assigned')
  scope: logAnalytics
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', logAnalyticsReaderRoleId)
    principalId: sreAgent.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource appInsightsConnector 'Microsoft.App/agents/connectors@2026-01-01' = {
  parent: sreAgent
  name: 'app-insights'
  properties: {
    dataConnectorType: 'AppInsights'
    #disable-next-line use-secure-value-for-secure-inputs // This data source is an ARM resource ID, not a secret.
    dataSource: appInsightsResourceId
    extendedProperties: {
      armResourceId: appInsightsResourceId
      resource: {
        name: last(split(appInsightsResourceId, '/'))
      }
      appId: appInsightsAppId
    }
    identity: 'system'
  }
  dependsOn: [
    systemReaderAssignment
    systemMonitoringReaderAssignment
    systemLogAnalyticsReaderAssignment
  ]
}

resource logAnalyticsConnector 'Microsoft.App/agents/connectors@2026-01-01' = {
  parent: sreAgent
  name: 'log-analytics'
  properties: {
    dataConnectorType: 'LogAnalytics'
    #disable-next-line use-secure-value-for-secure-inputs // This data source is an ARM resource ID, not a secret.
    dataSource: logAnalytics.id
    extendedProperties: {
      armResourceId: logAnalytics.id
      resource: {
        name: logAnalytics.name
      }
    }
    identity: 'system'
  }
  dependsOn: [
    systemReaderAssignment
    systemMonitoringReaderAssignment
    systemLogAnalyticsReaderAssignment
  ]
}

resource sreAgentAdministratorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sreAgent.id, developerPrincipalId, sreAgentAdministratorRoleId)
  scope: sreAgent
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sreAgentAdministratorRoleId)
    principalId: developerPrincipalId
    principalType: 'User'
  }
}

// Staged-regression lever: a bad model deployment makes the backend return 502s.
// This alert fires on backend 5xx responses and routes to the SRE Agent.
resource backendErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: alertName
  location: 'global'
  tags: tags
  properties: {
    description: 'BuildingAssist backend returning 5xx — the staged regression (bad model deployment) is active.'
    severity: 2
    enabled: true
    scopes: [
      backendAppId
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'Backend5xx'
          metricNamespace: 'Microsoft.App/containerApps'
          metricName: 'Requests'
          operator: 'GreaterThan'
          threshold: 0
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: [
                '5xx'
              ]
            }
          ]
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

output agentName string = sreAgent.name
output agentId string = sreAgent.id
output identityPrincipalId string = identity.properties.principalId

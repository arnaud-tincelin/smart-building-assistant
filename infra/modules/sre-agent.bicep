metadata description = '''
Azure SRE Agent (Microsoft.App/agents) — the operate pillar, now first-class in
Bicep. Provisions the agent with system-assigned and user-assigned identities,
scoped read access to the resource group + Log Analytics, persistent App Insights
and Log Analytics connectors, an Action Group as the incident entry point, and a
pair of trace alerts that route code and deployment faults independently.

GitHub connection, handlers, response plans, and repair skills are configured in
the agent Builder data plane post-provision — see docs/sre-agent.md.
'''

param location string
param tags object
param agentName string
param identityName string
param actionGroupName string
param legacyAlertName string
param securityAlertName string
param configAlertName string

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

@description('Backend Container App name — the only resource the action identity may modify.')
param backendAppName string

var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var monitoringReaderRoleId = '43d0d8ad-25c7-4714-9337-8ba259a9fe05'
var logAnalyticsReaderRoleId = '73c42c96-874c-492b-b04d-ab87d138a893'
var containerAppsContributorRoleId = '358470bc-b998-42bd-ab17-a7e34c199c0f'
var sreAgentAdministratorRoleId = 'e79298df-d852-4c6d-84f9-5d13249d1e55'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource backendApp 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: backendAppName
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

// The action identity can repair deployment configuration on the backend only.
resource backendContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(backendApp.id, identity.id, containerAppsContributorRoleId)
  scope: backendApp
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', containerAppsContributorRoleId)
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
  }
}

// Incremental deployments do not delete the former broad 5xx alert. Keep its
// original resource name declared and disabled so upgrades cannot emit duplicate incidents.
resource legacyBackendErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: legacyAlertName
  location: 'global'
  tags: tags
  properties: {
    description: 'Deprecated broad backend 5xx alert; replaced by scenario-specific log alerts.'
    severity: 2
    enabled: false
    scopes: [
      backendApp.id
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
    actions: []
  }
}

// Scenario 1: the staged access-control code defect returns HTTP 500.
resource backendSecurityErrorAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: securityAlertName
  location: location
  tags: tags
  properties: {
    displayName: securityAlertName
    description: 'BuildingAssist security operations are returning HTTP 500 responses.'
    severity: 2
    enabled: true
    scopes: [
      logAnalytics.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    skipQueryValidation: true
    autoMitigate: true
    criteria: {
      allOf: [
        {
          // The failure is logged with exc_info, so Azure Monitor records it in AppExceptions, not AppTraces.
          query: 'union isfuzzy=true AppTraces, AppExceptions | where AppRoleName == "buildingassist-backend" | where Message has "Security control operation failed" or OuterMessage has "Security control operation failed"'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

// Scenario 2: an invalid deployment setting returns traced HTTP 503 responses.
resource backendConfigErrorAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: configAlertName
  location: location
  tags: tags
  properties: {
    displayName: configAlertName
    description: 'BuildingAssist is unavailable because the deployed runtime configuration is invalid.'
    severity: 1
    enabled: true
    scopes: [
      logAnalytics.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    skipQueryValidation: true
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: 'AppTraces | where AppRoleName == "buildingassist-backend" | where Message has "CONFIG_ERROR"'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

output agentName string = sreAgent.name

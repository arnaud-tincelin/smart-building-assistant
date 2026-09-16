metadata description = 'Role assignments for the managed identity: ACR pull + Foundry access.'

param registryName string
param foundryAccountName string
param modelDeploymentName string
param enableRouterControl bool = false
param searchServiceName string
param appInsightsName string

@description('Principal id of the user-assigned managed identity used by the apps.')
param appPrincipalId string

@description('Principal id of the Foundry project system-assigned identity.')
param foundryProjectPrincipalId string

@description('Principal id of the Azure AI Search system-assigned identity.')
param searchPrincipalId string

@description('Optional developer principal id — granted Foundry access for the playground.')
param developerPrincipalId string = ''

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: registryName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' existing = {
  parent: foundry
  name: modelDeploymentName
}

// Router control: the app reads and updates the routing mode of the single demo
// model deployment. The built-in Cognitive Services Contributor role is assigned
// on that deployment only. It is broader than the read/write the app uses (it
// covers Microsoft.CognitiveServices/* on that one deployment, including delete),
// but it grants nothing on the parent account, so account keys stay out of reach.
// A custom role definition is deliberately avoided here: creating one requires
// Microsoft.Authorization/roleDefinitions/write, which the deployment identity
// does not have.
var cognitiveServicesContributorRoleId = '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'

resource routerControlAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableRouterControl) {
  name: guid(modelDeployment.id, appPrincipalId, cognitiveServicesContributorRoleId)
  scope: modelDeployment
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      cognitiveServicesContributorRoleId
    )
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// Built-in role definition ids.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var logAnalyticsReaderRoleId = '73c42c96-874c-492b-b04d-ab87d138a893'
var privilegedMonitoringDataReaderRoleId = 'dbc9c667-e97f-4491-aee6-90b9cf960190'

// App identity can pull images from ACR.
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, appPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    principalId: appPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalType: 'ServicePrincipal'
  }
}

// App identity can call the Foundry project/agent (Azure AI User).
resource azureAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, appPrincipalId, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: appPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// App identity can use Cognitive Services (Foundry account) directly if needed.
resource cognitiveUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, appPrincipalId, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    principalId: appPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Search invokes the Knowledge Base chat model through the Foundry account.
resource searchCognitiveUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, searchPrincipalId, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    principalId: searchPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Developer running azd can use the Foundry project/playground.
resource developerAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(foundry.id, developerPrincipalId, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: developerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
  }
}

resource developerSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(search.id, developerPrincipalId, searchServiceContributorRoleId)
  scope: search
  properties: {
    principalId: developerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
  }
}

resource developerSearchDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(search.id, developerPrincipalId, searchIndexDataContributorRoleId)
  scope: search
  properties: {
    principalId: developerPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      searchIndexDataContributorRoleId
    )
  }
}

resource appSearchDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, appPrincipalId, searchIndexDataReaderRoleId)
  scope: search
  properties: {
    principalId: appPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource foundryProjectSearchDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryProjectPrincipalId, searchIndexDataReaderRoleId)
  scope: search
  properties: {
    principalId: foundryProjectPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource foundryTraceReaders 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in [
    logAnalyticsReaderRoleId
    privilegedMonitoringDataReaderRoleId
  ]: {
    name: guid(appInsights.id, foundryProjectPrincipalId, roleId)
    scope: appInsights
    properties: {
      principalId: foundryProjectPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
      principalType: 'ServicePrincipal'
    }
  }
]

resource developerTraceReaders 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in [
    logAnalyticsReaderRoleId
    privilegedMonitoringDataReaderRoleId
  ]: if (!empty(developerPrincipalId)) {
    name: guid(appInsights.id, developerPrincipalId, roleId)
    scope: appInsights
    properties: {
      principalId: developerPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    }
  }
]

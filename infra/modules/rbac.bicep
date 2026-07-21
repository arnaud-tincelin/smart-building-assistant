metadata description = 'Role assignments for the managed identity: ACR pull + Foundry access.'

param registryName string
param foundryAccountName string

@description('Principal id of the user-assigned managed identity used by the apps.')
param appPrincipalId string

@description('Principal id of the APIM managed identity (for model-endpoint auth).')
param apimPrincipalId string

@description('Optional developer principal id — granted Foundry access for the playground.')
param developerPrincipalId string = ''

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: registryName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

// Built-in role definition ids.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var cognitiveServicesOpenAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

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

// APIM identity can call the Azure OpenAI model endpoint on the Foundry account.
resource apimOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, apimPrincipalId, cognitiveServicesOpenAiUserRoleId)
  scope: foundry
  properties: {
    principalId: apimPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      cognitiveServicesOpenAiUserRoleId
    )
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
    principalType: 'User'
  }
}

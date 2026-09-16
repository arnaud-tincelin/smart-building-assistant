metadata description = '''
Azure AI Foundry account + project + model deployment for the BuildingAssist agent.

The Foundry agent and Foundry IQ knowledge source are created post-provision
(see docs/sre-agent.md and README) because those surfaces are not yet stable in
Bicep. This module guarantees the account, project and model the agent uses.
'''

param location string
param tags object
param accountName string
param projectName string

@description('Application Insights resource ID used for Foundry agent traces.')
param appInsightsResourceId string

@secure()
@description('Application Insights connection string used by the Foundry project connection.')
param appInsightsConnectionString string

@description('Foundry project connection name for Application Insights tracing.')
param appInsightsConnectionName string = 'buildingassist-observability'

@description('Authenticated Foundry IQ Knowledge Base MCP endpoint.')
param knowledgeMcpEndpoint string

@description('Foundry project connection name for the Knowledge Base MCP endpoint.')
param knowledgeConnectionName string = 'buildingassist-knowledge'

@description('Azure AI Search endpoint used by the Foundry IQ management experience.')
param searchEndpoint string

@description('Azure AI Search resource ID used by the Foundry IQ management experience.')
param searchResourceId string

@description('Foundry project connection name for browsing Foundry IQ resources.')
param searchConnectionName string = 'search-connection'

@description('Deployment name used by the agent and Responses API.')
param modelDeploymentName string = 'model-router'

@description('Microsoft Foundry model to deploy.')
param modelName string = 'model-router'
param modelVersion string = '2025-11-18'
param modelCapacity int = 30

@description('GPT-5-mini deployment shared by the Foundry IQ Knowledge Base and AI Gateway.')
param knowledgeModelDeploymentName string = 'gpt-5-mini'
param knowledgeModelName string = 'gpt-5-mini'
param knowledgeModelVersion string = '2025-08-07'
param knowledgeModelCapacity int = 30

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    // Enable the Foundry project + agent surface and use custom subdomain so the
    // project endpoint (…services.ai.azure.com) resolves.
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

module modelDeployment 'model-router.bicep' = {
  params: {
    accountName: account.name
    deploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    capacity: modelCapacity
  }
}

resource knowledgeModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: knowledgeModelDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: knowledgeModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: knowledgeModelName
      version: knowledgeModelVersion
    }
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'BuildingAssist demo project — the reasoning behind the app.'
  }
  dependsOn: [
    modelDeployment
  ]
}

resource knowledgeConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-10-01-preview' = {
  parent: project
  name: knowledgeConnectionName
  properties: any({
    authType: 'ProjectManagedIdentity'
    category: 'RemoteTool'
    target: knowledgeMcpEndpoint
    isSharedToAll: true
    audience: 'https://search.azure.com/'
    metadata: {
      ApiType: 'Azure'
    }
  })
}

resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-10-01-preview' = {
  parent: project
  name: searchConnectionName
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    isSharedToAll: false
    metadata: {
      type: 'azure_ai_search'
      ApiType: 'Azure'
      ResourceId: searchResourceId
      ApiVersion: '2025-11-01-preview'
    }
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = {
  parent: project
  name: appInsightsConnectionName
  properties: {
    category: 'AppInsights'
    target: appInsightsResourceId
    authType: 'ApiKey'
    isSharedToAll: false
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsResourceId
    }
  }
}

output accountName string = account.name
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
output projectId string = project.id
output projectPrincipalId string = project.identity.principalId
@description('Foundry project endpoint used by the Azure AI Projects SDK.')
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
output modelDeploymentName string = modelDeployment.outputs.deploymentName
output modelDeploymentId string = modelDeployment.outputs.deploymentId
output modelName string = modelName
output modelVersion string = modelVersion
output modelCapacity int = modelCapacity
output knowledgeModelDeploymentName string = knowledgeModelDeployment.name
output knowledgeModelDeploymentId string = knowledgeModelDeployment.id
output knowledgeModelName string = knowledgeModelName
output knowledgeModelVersion string = knowledgeModelVersion
output knowledgeModelCapacity int = knowledgeModelCapacity
output knowledgeModelResourceUri string = 'https://${account.name}.openai.azure.com'
output knowledgeConnectionName string = knowledgeConnection.name
output searchConnectionName string = searchConnection.name
output appInsightsConnectionName string = appInsightsConnection.name

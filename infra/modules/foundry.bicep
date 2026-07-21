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

@description('Model deployment for the agent.')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelCapacity int = 30

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

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
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

output accountName string = account.name
output accountId string = account.id
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
@description('Foundry project endpoint used by the Azure AI Projects SDK.')
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
output modelDeploymentName string = modelDeployment.name
output openAiEndpoint string = 'https://${account.name}.openai.azure.com/'
